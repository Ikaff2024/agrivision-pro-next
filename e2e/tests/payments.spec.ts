import { test, expect } from '@playwright/test';

/**
 * Suivi des paiements producteurs : soldes dûs + règlement groupé depuis l'UI.
 *
 * Setup API : producteur + 2 achats « en attente ». UI (page Achats) : la section
 * « Soldes à payer par producteur » affiche le dû, on règle, le solde tombe à 0.
 */

const API = process.env.AVP_API_URL || 'https://agrivision-api-production.up.railway.app';
const STAMP = Date.now();
const COOP = process.env.AVP_TEST_COOP || `E2E Pay ${STAMP}`;
const EMAIL = process.env.AVP_TEST_EMAIL || `e2e.pay.${STAMP}@agrivision.test`;
const PASSWORD = process.env.AVP_TEST_PASSWORD || 'E2eDemo!234';
const REUSE = !!process.env.AVP_TEST_EMAIL;

test('Paiements producteurs : solde dû puis règlement groupé', async ({ page, request }) => {
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

  // Parcelle (auto-crée un producteur) → récupérer le producteur.
  await request.post(`${API}/plantations`, {
    headers,
    data: {
      name: 'Parcelle Pay', owner_name: 'Producteur Pay',
      country: "Côte d'Ivoire", region: 'Yeyasso', hectares: 2.0,
    },
  });
  const producers = await (await request.get(`${API}/producers?limit=50`, { headers })).json();
  expect(producers.length).toBeGreaterThan(0);
  const producerId = producers[0].id;

  // Deux achats en attente (100 000 + 50 000 = 150 000 FCFA dûs).
  for (const net of [100, 50]) {
    const r = await request.post(`${API}/purchases`, {
      headers, data: { producer_id: producerId, net_weight_kg: net, price_per_kg_fcfa: 1000, payment_status: 'pending' },
    });
    expect([200, 201], `achat (${r.status()})`).toContain(r.status());
  }

  // ── UI : page Achats ──
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
  const balances = page.locator('#bal-tbody');
  await expect(balances.getByText('Producteur Pay')).toBeVisible({ timeout: 20_000 });
  await expect(balances.getByText('150 000').first()).toBeVisible();   // solde dû (format fr-FR)

  // Régler le solde → confirmation avpConfirm → OK.
  await balances.locator('button:has-text("Régler le solde")').click();
  const [resp] = await Promise.all([
    page.waitForResponse(r => r.request().method() === 'POST' && /\/purchases\/producer\/\d+\/settle$/.test(new URL(r.url()).pathname)),
    page.getByRole('button', { name: 'Régler', exact: true }).click(),
  ]);
  expect(resp.ok(), `settle (${resp.status()})`).toBeTruthy();

  // Le solde dû tombe à 0 : plus de bouton « Régler le solde ».
  await expect(balances.locator('button:has-text("Régler le solde")')).toHaveCount(0, { timeout: 15_000 });
  await expect(page.locator('#k-pending')).toHaveText('0');
});
