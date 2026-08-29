import { test, expect } from '@playwright/test';
import { API, loginViaUI, openSession } from './helpers/session';

/**
 * Suivi des paiements producteurs : soldes dûs + règlement groupé depuis l'UI.
 *
 * Setup API : producteur + 2 achats « en attente ». UI (page Achats) : la section
 * « Soldes à payer par producteur » affiche le dû, on règle, le solde tombe à 0.
 */

test('Paiements producteurs : solde dû puis règlement groupé', async ({ page, request }) => {
  test.slow();

  const session = await openSession(request, 'pay');
  const { token, headers } = session;

  // Un achat ne concerne QUE les producteurs NON-MEMBRES : depuis le verrou
  // métier 59eab40, la production d'un membre se saisit en récolte et l'API
  // refuse l'achat (409). Le producteur créé automatiquement avec une parcelle
  // est un « membre » — on crée donc explicitement le non-membre concerné.
  const prodRes = await request.post(`${API}/producers`, {
    headers, data: { nom_complet: 'Producteur Pay', type_producteur: 'non_membre' },
  });
  expect([200, 201], `producteur (${prodRes.status()}): ${await prodRes.text()}`)
    .toContain(prodRes.status());
  const producerId = (await prodRes.json()).id;

  // Deux achats en attente (100 000 + 50 000 = 150 000 FCFA dûs).
  for (const net of [100, 50]) {
    const r = await request.post(`${API}/purchases`, {
      headers, data: { producer_id: producerId, net_weight_kg: net, price_per_kg_fcfa: 1000, payment_status: 'pending' },
    });
    expect([200, 201], `achat (${r.status()})`).toContain(r.status());
  }

  // ── UI : page Achats ──
  await loginViaUI(page, session);

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
