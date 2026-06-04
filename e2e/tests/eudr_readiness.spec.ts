import { test, expect } from '@playwright/test';

/**
 * Tableau « Prêt pour l'EUDR » : le panneau de blocages s'affiche et filtre la table.
 *
 * Une parcelle sans délimitation apparaît dans le gap « Parcelles à délimiter » ;
 * cliquer la carte filtre la table sur cette parcelle.
 */

const API = process.env.AVP_API_URL || 'https://agrivision-api-production.up.railway.app';
const STAMP = Date.now();
const COOP = process.env.AVP_TEST_COOP || `E2E Readiness ${STAMP}`;
const EMAIL = process.env.AVP_TEST_EMAIL || `e2e.readiness.${STAMP}@agrivision.test`;
const PASSWORD = process.env.AVP_TEST_PASSWORD || 'E2eDemo!234';
const REUSE = !!process.env.AVP_TEST_EMAIL;

test("EUDR : panneau « Prêt pour l'EUDR » et filtre par blocage", async ({ page, request }) => {
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

  // Une parcelle SANS délimitation → bloquée sur « Parcelles à délimiter ».
  const plantRes = await request.post(`${API}/plantations`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: 'Parcelle Readiness', owner_name: 'Producteur Readiness',
      country: "Côte d'Ivoire", region: 'Yeyasso', hectares: 2.0, latitude: 6.0, longitude: -6.6,
    },
  });
  expect([200, 201]).toContain(plantRes.status());

  // ── UI ──
  await page.addInitScript((api) => {
    (window as any).AGRIVISION_API_BASE = api;
    (window as any).CG_API_BASE = api;
  }, API);
  await page.goto('/login.html');
  await page.fill('#email', EMAIL);
  await page.fill('#pass', PASSWORD);
  await page.click('#btn');
  await page.waitForURL('**/plantations.html', { timeout: 30_000 });

  await page.click('a.nav-link[data-mod="eudr"]');
  await page.waitForURL('**/eudr.html');

  // Panneau readiness : 0 conforme sur 1, carte « Parcelles à délimiter ».
  await expect(page.locator('#ready-count')).toHaveText('0/1', { timeout: 20_000 });
  const gapCards = page.locator('#gap-cards');
  await expect(gapCards.getByText('Parcelles à délimiter')).toBeVisible();

  // Cliquer le gap filtre la table sur la parcelle concernée.
  await gapCards.getByText('Parcelles à délimiter').click();
  await expect(page.locator('button:has-text("Tout afficher")')).toBeVisible();
  await expect(page.locator('#rows').getByText('Parcelle Readiness')).toBeVisible();
});
