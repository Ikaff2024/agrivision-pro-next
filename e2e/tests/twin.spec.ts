import { test, expect } from '@playwright/test';

/**
 * Jumeau de parcelle (FEATURE-PARCEL-360) : la fiche plantation affiche la
 * synthèse « Jumeau » + les alertes par règles (vue agrégée sur l'existant).
 */

const API = process.env.AVP_API_URL || 'https://agrivision-api-production.up.railway.app';
const STAMP = Date.now();
const COOP = process.env.AVP_TEST_COOP || `E2E Twin ${STAMP}`;
const EMAIL = process.env.AVP_TEST_EMAIL || `e2e.twin.${STAMP}@agrivision.test`;
const PASSWORD = process.env.AVP_TEST_PASSWORD || 'E2eDemo!234';
const REUSE = !!process.env.AVP_TEST_EMAIL;

test('Jumeau de parcelle : synthèse + alertes sur la fiche plantation', async ({ page, request }) => {
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

  // Parcelle nue (sans délimitation) → doit générer des alertes.
  const plantRes = await request.post(`${API}/plantations`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: 'Parcelle Twin', owner_name: 'Producteur Twin',
      country: "Côte d'Ivoire", region: 'Yeyasso', hectares: 2.0, latitude: 6.0, longitude: -6.6,
    },
  });
  expect([200, 201]).toContain(plantRes.status());
  const plantId = (await plantRes.json()).id;

  // ── UI : fiche plantation ──
  await page.addInitScript((api) => {
    (window as any).AGRIVISION_API_BASE = api;
    (window as any).CG_API_BASE = api;
  }, API);
  await page.goto('/login.html');
  await page.fill('#email', EMAIL);
  await page.fill('#pass', PASSWORD);
  await page.click('#btn');
  await page.waitForURL('**/plantations.html', { timeout: 30_000 });

  await page.goto(`/plantation_detail.html?id=${plantId}`);

  const twin = page.locator('#twin-container');
  await expect(twin).toContainText('Jumeau de la parcelle', { timeout: 20_000 });
  // Parcelle sans polygone → alerte de délimitation présente.
  await expect(twin).toContainText('Parcelle non délimitée');
  // Les chips de synthèse sont là.
  await expect(twin).toContainText('Conformité EUDR');
});
