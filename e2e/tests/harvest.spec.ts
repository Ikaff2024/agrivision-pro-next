import { test, expect } from '@playwright/test';

/**
 * Récolte avec n° de reçu d'achat (Point #4 du backlog).
 *
 * Vérifie de bout en bout le champ « numéro de reçu d'achat » (#h-receipt) et
 * « nombre de sacs » (#h-bags) ajoutés au formulaire de saisie : on saisit une
 * récolte et on confirme que le n° de reçu apparaît dans le tableau.
 */

const API = process.env.AVP_API_URL || 'https://agrivision-api-production.up.railway.app';
const STAMP = Date.now();
const COOP = process.env.AVP_TEST_COOP || `E2E Recolte ${STAMP}`;
const EMAIL = process.env.AVP_TEST_EMAIL || `e2e.recolte.${STAMP}@agrivision.test`;
const PASSWORD = process.env.AVP_TEST_PASSWORD || 'E2eDemo!234';
const REUSE = !!process.env.AVP_TEST_EMAIL;
const RECEIPT = `REC-E2E-${STAMP}`;

test("Récolte : saisie avec n° de reçu d'achat (Point #4)", async ({ page, request }) => {
  test.slow();

  // ── Setup API : compte admin + parcelle ──
  if (!REUSE) {
    const reg = await request.post(`${API}/auth/register`, {
      data: { email: EMAIL, password: PASSWORD, role: 'admin', cooperative_name: COOP, country: 'CI' },
    });
    expect(reg.ok(), `register (${reg.status()}): ${await reg.text()}`).toBeTruthy();
  }
  const login = await request.post(`${API}/auth/login`, { data: { email: EMAIL, password: PASSWORD } });
  expect(login.ok(), `login API (${login.status()})`).toBeTruthy();
  const token = (await login.json()).access_token as string;
  const plantRes = await request.post(`${API}/plantations`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: 'Parcelle Récolte', owner_name: 'Producteur Récolte',
      country: "Côte d'Ivoire", region: 'Yeyasso', hectares: 3.0,
      latitude: 6.2, longitude: -6.5,
    },
  });
  expect([200, 201], `création plantation (${plantRes.status()})`).toContain(plantRes.status());
  const plantId = String((await plantRes.json()).id);

  // ── Connexion UI ──
  await page.addInitScript((api) => {
    (window as any).AGRIVISION_API_BASE = api;
    (window as any).CG_API_BASE = api;
  }, API);
  await page.goto('/login.html');
  await page.fill('#email', EMAIL);
  await page.fill('#pass', PASSWORD);
  await page.click('#btn');
  await page.waitForURL('**/plantations.html', { timeout: 30_000 });

  // ── Page Récoltes : choisir la parcelle (révèle le bouton de saisie) ──
  await page.goto('/harvests.html');
  await page.waitForSelector(`#plantation-select option[value="${plantId}"]`, { state: 'attached', timeout: 20_000 });
  await page.selectOption('#plantation-select', plantId);

  // ── Modale de saisie : quantité + N° de reçu (Point #4) + nb de sacs ──
  await page.click('#add-btn'); // apparaît après sélection de la parcelle
  await page.fill('#h-quantity', '850');   // date + qualité ("Bonne") pré-remplies
  await page.fill('#h-receipt', RECEIPT);
  await page.fill('#h-bags', '12');
  await page.click('#h-submit-btn');

  // ── Le n° de reçu apparaît dans le tableau des récoltes ──
  await expect(page.getByText(RECEIPT).first()).toBeVisible({ timeout: 20_000 });
});
