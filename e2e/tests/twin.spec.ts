import { test, expect } from '@playwright/test';
import { API, loginViaUI, openSession } from './helpers/session';

/**
 * Jumeau de parcelle (FEATURE-PARCEL-360) : la fiche plantation affiche la
 * synthèse « Jumeau » + les alertes par règles (vue agrégée sur l'existant).
 */

test('Jumeau de parcelle : synthèse + alertes sur la fiche plantation', async ({ page, request }) => {
  test.slow();

  const session = await openSession(request, 'twin');
  const { token } = session;

  // Parcelle nue (sans délimitation) → doit générer des alertes.
  const plantRes = await request.post(`${API}/plantations`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: 'Parcelle Twin', owner_name: 'Producteur Twin',
      country: "Côte d'Ivoire", region: 'Zone-Test', hectares: 2.0, latitude: 6.0, longitude: -6.6,
    },
  });
  expect([200, 201]).toContain(plantRes.status());
  const plantId = (await plantRes.json()).id;

  // ── UI : fiche plantation ──
  await loginViaUI(page, session);

  await page.goto(`/plantation_detail.html?id=${plantId}`);

  const twin = page.locator('#twin-container');
  await expect(twin).toContainText('Jumeau de la parcelle', { timeout: 20_000 });
  // Parcelle sans polygone → alerte de délimitation présente.
  await expect(twin).toContainText('Parcelle non délimitée');
  // Les chips de synthèse sont là.
  await expect(twin).toContainText('Conformité EUDR');
});
