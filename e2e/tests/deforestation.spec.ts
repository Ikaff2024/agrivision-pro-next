import { test, expect } from '@playwright/test';
import { API, loginViaUI, openSession, openModule } from './helpers/session';

/**
 * Contrôle de déforestation automatique (satellite GFW → EUDR R6) depuis l'UI.
 *
 * Parcelle délimitée → page EUDR → bouton « Déforestation » → un contrôle est
 * enregistré (source `gfw*`) et le score EUDR est recalculé.
 *
 * Verdict selon l'environnement : avec clé GFW → clear/deforestation_detected ;
 * sans clé (CI) → inconclusive (jamais de faux « clear »). Le test reste donc
 * agnostique : il vérifie qu'un contrôle est créé via une source satellite.
 */

const LAT = 6.05, LNG = -6.95, HA = 3.0;

function squareGeometry() {
  const half = Math.sqrt(HA * 10000) / 2;
  const dLat = half / 111320;
  const dLng = half / (111320 * Math.cos(LAT * Math.PI / 180));
  return {
    type: 'Polygon',
    coordinates: [[
      [LNG - dLng, LAT - dLat], [LNG + dLng, LAT - dLat],
      [LNG + dLng, LAT + dLat], [LNG - dLng, LAT + dLat], [LNG - dLng, LAT - dLat],
    ]],
  };
}

test('Déforestation satellite (GFW → EUDR R6) depuis la page EUDR', async ({ page, request }) => {
  test.slow();

  const session = await openSession(request, 'defo');
  const { token, headers } = session;

  const plantRes = await request.post(`${API}/plantations`, {
    headers,
    data: {
      name: 'Parcelle Defo', owner_name: 'Producteur Defo',
      country: "Côte d'Ivoire", region: 'Zone-Test', hectares: HA, latitude: LAT, longitude: LNG,
    },
  });
  expect([200, 201]).toContain(plantRes.status());
  const plantId = String((await plantRes.json()).id);

  // Délimitation (prérequis du contrôle satellite).
  const bound = await request.post(`${API}/plantations/${plantId}/boundary`, {
    headers, data: { geojson: JSON.stringify(squareGeometry()), method: 'manual' },
  });
  expect(bound.ok(), `boundary (${bound.status()})`).toBeTruthy();

  // Avant : aucun contrôle de déforestation.
  const before = await (await request.get(`${API}/plantations/${plantId}/deforestation-checks`, { headers })).json();
  expect(before.count).toBe(0);

  // ── UI : page EUDR → bouton Déforestation ──
  await loginViaUI(page, session);

  await openModule(page, 'eudr');
  await page.waitForURL('**/eudr.html');
  await expect(page.getByText('Parcelle Defo').first()).toBeVisible({ timeout: 20_000 });

  const [resp] = await Promise.all([
    page.waitForResponse(r =>
      r.request().method() === 'POST' &&
      new URL(r.url()).pathname.endsWith(`/plantations/${plantId}/deforestation-check/auto`),
    ),
    page.click('button:has-text("Déforestation")'),
  ]);
  expect(resp.status(), 'auto-check 201').toBe(201);

  // Après : un contrôle issu d'une source satellite (gfw*) est enregistré.
  const after = await (await request.get(`${API}/plantations/${plantId}/deforestation-checks`, { headers })).json();
  expect(after.count).toBe(1);
  expect(after.checks[0].source).toMatch(/^gfw/);
  expect(['clear', 'deforestation_detected', 'inconclusive']).toContain(after.checks[0].verdict);
});
