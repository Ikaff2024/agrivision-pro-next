import { test, expect } from '@playwright/test';
import { API, loginViaUI, openSession } from './helpers/session';
import fs from 'fs';

/**
 * Pack de diligence raisonnée EUDR par lot (livrable acheteur).
 *
 * Setup API : parcelle → récolte → lot. UI : ouverture du lot, bouton « Pack EUDR »,
 * téléchargement du ZIP. On vérifie la signature ZIP (PK) du fichier téléchargé.
 */

test('Pack de diligence raisonnée EUDR par lot (ZIP)', async ({ page, request }) => {
  test.slow();

  const session = await openSession(request, 'pack');
  const { token, headers } = session;

  const plantRes = await request.post(`${API}/plantations`, {
    headers,
    data: {
      name: 'Parcelle Pack', owner_name: 'Producteur Pack',
      country: "Côte d'Ivoire", region: 'Zone-Test', hectares: 2.0, latitude: 6.1, longitude: -6.7,
    },
  });
  expect([200, 201]).toContain(plantRes.status());
  const plantId = (await plantRes.json()).id;
  const harvestRes = await request.post(`${API}/plantations/${plantId}/harvests`, {
    headers, data: { harvest_date: '2026-02-01T08:00:00', quantity_kg: 500, quality: 'Bonne' },
  });
  expect([200, 201]).toContain(harvestRes.status());
  const lotRes = await request.post(`${API}/lots`, {
    headers, data: { season: '2025-2026', harvest_ids: [(await harvestRes.json()).id] },
  });
  expect([200, 201], `lot (${lotRes.status()})`).toContain(lotRes.status());

  // ── UI : ouvrir le lot et télécharger le pack EUDR ──
  await loginViaUI(page, session);

  await page.goto('/lots.html');
  await page.locator('.lot-item').first().click();
  await expect(page.locator('#detail')).toBeVisible({ timeout: 20_000 });

  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 60_000 }),
    page.click('button:has-text("Pack EUDR")'),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.zip$/i);
  const path = await download.path();
  const head = fs.readFileSync(path!).subarray(0, 2).toString('latin1');
  expect(head, `entête = ${head}`).toBe('PK'); // signature ZIP
});
