import { test, expect } from '@playwright/test';
import { API, loginViaUI, openSession } from './helpers/session';

/**
 * Tableau « Prêt pour l'EUDR » : le panneau de blocages s'affiche et filtre la table.
 *
 * Une parcelle sans délimitation apparaît dans le gap « Parcelles à délimiter » ;
 * cliquer la carte filtre la table sur cette parcelle.
 */

test("EUDR : panneau « Prêt pour l'EUDR » et filtre par blocage", async ({ page, request }) => {
  test.slow();

  const session = await openSession(request, 'readiness');
  const { token } = session;

  // Une parcelle SANS délimitation → bloquée sur « Parcelles à délimiter ».
  const plantRes = await request.post(`${API}/plantations`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: 'Parcelle Readiness', owner_name: 'Producteur Readiness',
      country: "Côte d'Ivoire", region: 'Zone-Test', hectares: 2.0, latitude: 6.0, longitude: -6.6,
    },
  });
  expect([200, 201]).toContain(plantRes.status());

  // ── UI ──
  await loginViaUI(page, session);

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
