import { test, expect } from '@playwright/test';
import fs from 'fs';

/**
 * Parcours à forte valeur : DÉLIMITATION de parcelle → CONFORMITÉ EUDR → DDS PDF.
 *
 * On enregistre le polygone via le MÊME endpoint que le bouton « Enregistrer » de
 * l'outil de délimitation de la carte (`POST /plantations/{id}/boundary`, payload
 * GeoJSON identique à `saveBoundary()` dans map.html), puis on prouve par l'UI que :
 *   1) la conformité EUDR bascule : `has_polygon` false → true (règle R1 satisfaite) ;
 *   2) le DDS PDF de la parcelle se télécharge (signature %PDF).
 *
 * NB : le dessin Leaflet lui-même (clics carte / carré rapide) relève du test manuel ;
 * ici on couvre de bout en bout la chaîne métier déterministe (tracé→conformité→DDS).
 */

const API = process.env.AVP_API_URL || 'https://agrivision-api-production.up.railway.app';
const STAMP = Date.now();
const COOP = process.env.AVP_TEST_COOP || `E2E Trace ${STAMP}`;
const EMAIL = process.env.AVP_TEST_EMAIL || `e2e.trace.${STAMP}@agrivision.test`;
const PASSWORD = process.env.AVP_TEST_PASSWORD || 'E2eDemo!234';
const REUSE = !!process.env.AVP_TEST_EMAIL;

const LAT = 6.05, LNG = -6.95, HA = 3.0;

async function eudrHasPolygon(request: any, token: string, plantId: string): Promise<boolean> {
  const r = await request.get(`${API}/plantations/${plantId}/eudr-status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.ok(), `eudr-status (${r.status()})`).toBeTruthy();
  return (await r.json()).has_polygon === true;
}

/** Carré ~HA hectares centré sur (LAT,LNG), anneau GeoJSON fermé [lng,lat]. */
function squareGeometry() {
  const half = Math.sqrt(HA * 10000) / 2;
  const dLat = half / 111320;
  const dLng = half / (111320 * Math.cos(LAT * Math.PI / 180));
  const ring = [
    [LNG - dLng, LAT - dLat], [LNG + dLng, LAT - dLat],
    [LNG + dLng, LAT + dLat], [LNG - dLng, LAT + dLat],
    [LNG - dLng, LAT - dLat],
  ];
  return { type: 'Polygon', coordinates: [ring] };
}

test('Délimitation de parcelle → conformité EUDR → DDS PDF', async ({ page, request }) => {
  test.slow();

  // ── Setup API : compte admin + parcelle (avec surface, SANS polygone) ──
  if (!REUSE) {
    const reg = await request.post(`${API}/auth/register`, {
      data: { email: EMAIL, password: PASSWORD, role: 'admin', cooperative_name: COOP, country: 'CI' },
    });
    expect(reg.ok(), `register (${reg.status()}): ${await reg.text()}`).toBeTruthy();
  }
  const login = await request.post(`${API}/auth/login`, { data: { email: EMAIL, password: PASSWORD } });
  expect(login.ok(), `login API (${login.status()})`).toBeTruthy();
  const token = (await login.json()).access_token as string;
  const plantRes = await request.post(`${API}/plantations`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: 'Parcelle Tracé', owner_name: 'Producteur Tracé',
      country: "Côte d'Ivoire", region: 'Zone-Test', hectares: HA,
      latitude: LAT, longitude: LNG,
    },
  });
  expect([200, 201], `création plantation (${plantRes.status()})`).toContain(plantRes.status());
  const plantId = String((await plantRes.json()).id);

  // AVANT le tracé : pas de polygone (règle EUDR R1 non satisfaite).
  expect(await eudrHasPolygon(request, token, plantId), 'has_polygon avant tracé').toBe(false);

  // ── « Tracé » : enregistrement du polygone via l'endpoint de délimitation ──
  const saveRes = await request.post(`${API}/plantations/${plantId}/boundary`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { geojson: JSON.stringify(squareGeometry()), method: 'manual' },
  });
  expect(saveRes.ok(), `POST boundary (${saveRes.status()}): ${await saveRes.text()}`).toBeTruthy();

  // APRÈS le tracé : le polygone est pris en compte (conformité améliorée).
  expect(await eudrHasPolygon(request, token, plantId), 'has_polygon après tracé').toBe(true);

  // ── UI : connexion puis téléchargement du DDS PDF de la parcelle délimitée ──
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
  await expect(page.getByText('Parcelle Tracé').first()).toBeVisible({ timeout: 20_000 });

  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 60_000 }),
    page.click('button:has-text("DDS")'),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.pdf$/i);
  const path = await download.path();
  const head = fs.readFileSync(path!).subarray(0, 5).toString('latin1');
  expect(head, `entête = ${head}`).toMatch(/^%PDF/);
});
