import { test, expect } from '@playwright/test';

/**
 * Achats producteurs : enregistrement d'un achat depuis l'UI.
 *
 * Sélection du producteur, saisie du poids / prix / n° de bon d'achat, puis
 * vérification que le compteur d'achats passe à 1.
 */

const API = process.env.AVP_API_URL || 'https://agrivision-api-production.up.railway.app';
const STAMP = Date.now();
const COOP = process.env.AVP_TEST_COOP || `E2E Achat ${STAMP}`;
const EMAIL = process.env.AVP_TEST_EMAIL || `e2e.achat.${STAMP}@agrivision.test`;
const PASSWORD = process.env.AVP_TEST_PASSWORD || 'E2eDemo!234';
const REUSE = !!process.env.AVP_TEST_EMAIL;

test('Achats : enregistrer un achat producteur', async ({ page, request }) => {
  test.slow();

  if (!REUSE) {
    const reg = await request.post(`${API}/auth/register`, {
      data: { email: EMAIL, password: PASSWORD, role: 'admin', cooperative_name: COOP, country: 'CI' },
    });
    expect(reg.ok(), `register (${reg.status()}): ${await reg.text()}`).toBeTruthy();
  }
  const login = await request.post(`${API}/auth/login`, { data: { email: EMAIL, password: PASSWORD } });
  expect(login.ok()).toBeTruthy();
  const token = (await login.json()).access_token as string;
  const headers = { Authorization: `Bearer ${token}` };

  // Une parcelle crée automatiquement un producteur.
  const plantRes = await request.post(`${API}/plantations`, {
    headers,
    data: {
      name: 'Parcelle Achat', owner_name: 'Producteur Achat',
      country: "Côte d'Ivoire", region: 'Zone-Test', hectares: 2.0,
    },
  });
  expect([200, 201]).toContain(plantRes.status());
  const producers = await (await request.get(`${API}/producers?limit=50`, { headers })).json();
  expect(producers.length, 'producteur auto-créé').toBeGreaterThan(0);
  const producerId = String(producers[0].id);

  // ── UI : connexion puis saisie de l'achat ──
  await page.addInitScript((api) => {
    (window as any).AGRIVISION_API_BASE = api;
    (window as any).CG_API_BASE = api;
  }, API);
  await page.goto('/login.html');
  await page.fill('#email', EMAIL);
  await page.fill('#pass', PASSWORD);
  await page.click('#btn');
  await page.waitForURL('**/plantations.html', { timeout: 30_000 });

  await page.goto('/achats.html');
  await page.waitForSelector(`#b-producer option[value="${producerId}"]`, { state: 'attached', timeout: 20_000 });
  await page.selectOption('#b-producer', producerId);
  await page.fill('#b-gross', '100');
  await page.fill('#b-net', '100');
  await page.fill('#b-price', '1000');
  await page.fill('#b-receipt', `BON-E2E-${STAMP}`);
  await page.click("button:has-text(\"Enregistrer l'achat\")");

  // Le compteur d'achats passe à 1.
  await expect(page.locator('#k-count')).toHaveText('1', { timeout: 15_000 });
});
