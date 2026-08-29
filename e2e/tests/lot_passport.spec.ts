import { test, expect } from '@playwright/test';
import { API, loginViaUI, openSession } from './helpers/session';
import fs from 'fs';

/**
 * Traçabilité : passeport de lot PDF.
 *
 * Setup via API : parcelle → récolte → lot (composé de cette récolte). Puis dans
 * l'UI : ouverture du lot et téléchargement du passeport PDF (signature %PDF).
 */

test('Traçabilité : passeport de lot PDF', async ({ page, request }) => {
  test.slow();

  const session = await openSession(request, 'lot');
  const { token, headers } = session;

  // Parcelle → récolte → lot
  const plantRes = await request.post(`${API}/plantations`, {
    headers,
    data: {
      name: 'Parcelle Lot', owner_name: 'Producteur Lot',
      country: "Côte d'Ivoire", region: 'Zone-Test', hectares: 2.0,
      latitude: 6.2, longitude: -6.7,
    },
  });
  expect([200, 201]).toContain(plantRes.status());
  const plantId = (await plantRes.json()).id;

  const harvestRes = await request.post(`${API}/plantations/${plantId}/harvests`, {
    headers,
    data: { harvest_date: '2026-02-01T08:00:00', quantity_kg: 500, quality: 'Bonne' },
  });
  expect([200, 201], `récolte (${harvestRes.status()})`).toContain(harvestRes.status());
  const harvestId = (await harvestRes.json()).id;

  const lotRes = await request.post(`${API}/lots`, {
    headers,
    data: { season: '2025-2026', harvest_ids: [harvestId] },
  });
  expect([200, 201], `lot (${lotRes.status()}): ${await lotRes.text()}`).toContain(lotRes.status());
  const lotCode = (await lotRes.json()).code as string;

  // ── UI : ouvrir le lot et télécharger le passeport ──
  await loginViaUI(page, session);

  await page.goto('/lots.html');
  await page.locator('.lot-item').first().click();        // openLot
  await expect(page.locator('#detail')).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('#d-code')).toContainText(lotCode);

  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 60_000 }),
    page.click('button:has-text("Passeport")'),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.pdf$/i);
  const path = await download.path();
  const head = fs.readFileSync(path!).subarray(0, 5).toString('latin1');
  expect(head, `entête = ${head}`).toMatch(/^%PDF/);
});
