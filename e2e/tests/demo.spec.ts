import { test, expect } from '@playwright/test';

/**
 * Parcours de démonstration / non-régression « bout en bout ».
 *
 * Couvre le chemin critique vendu au client :
 *   Connexion → Plantation → Producteur → Analyse satellite (NDVI réel) → EUDR.
 *
 * Stratégie : le SETUP (compte + parcelle géolocalisée) se fait via l'API
 * (rapide et fiable), puis le PARCOURS se fait via l'UI (ce que filme la vidéo).
 *
 * Par défaut, une coopérative jetable est créée à chaque exécution. Pour rejouer
 * sur un compte existant (démo « riche »), définir AVP_TEST_EMAIL / AVP_TEST_PASSWORD.
 */

const API = process.env.AVP_API_URL || 'https://agrivision-api-production.up.railway.app';
const STAMP = Date.now();
const COOP = process.env.AVP_TEST_COOP || `E2E Demo ${STAMP}`;
const EMAIL = process.env.AVP_TEST_EMAIL || `e2e.${STAMP}@agrivision.test`;
const PASSWORD = process.env.AVP_TEST_PASSWORD || 'E2eDemo!234';
const REUSE = !!process.env.AVP_TEST_EMAIL;

test('Parcours démo : connexion → producteur → satellite → EUDR', async ({ page, request }) => {
  test.slow(); // analyse satellite réelle = peut être longue

  // ── 1. SETUP via API : compte (coop fondatrice = admin) + 1 parcelle GPS ──
  if (!REUSE) {
    const reg = await request.post(`${API}/auth/register`, {
      data: { email: EMAIL, password: PASSWORD, role: 'admin', cooperative_name: COOP, country: 'CI' },
    });
    expect(reg.ok(), `register a échoué (${reg.status()}): ${await reg.text()}`).toBeTruthy();
  }
  const login = await request.post(`${API}/auth/login`, { data: { email: EMAIL, password: PASSWORD } });
  expect(login.ok(), `login API a échoué (${login.status()})`).toBeTruthy();
  const token = (await login.json()).access_token as string;

  const plantRes = await request.post(`${API}/plantations`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: 'Parcelle Démo', owner_name: 'Producteur Démo',
      country: "Côte d'Ivoire", region: 'Zone-Test', hectares: 3.0,
      latitude: 5.85, longitude: -7.35,
    },
  });
  expect([200, 201], `création plantation (${plantRes.status()})`).toContain(plantRes.status());
  const plantId = String((await plantRes.json()).id);

  // ── 2. Injecter l'API réelle même servi en local, puis CONNEXION via l'UI ──
  await page.addInitScript((api) => {
    (window as any).AGRIVISION_API_BASE = api;
    (window as any).CG_API_BASE = api;
  }, API);

  await page.goto('/login.html');
  await page.fill('#email', EMAIL);
  await page.fill('#pass', PASSWORD);
  await page.click('#btn');
  await page.waitForURL('**/plantations.html', { timeout: 30_000 });
  await expect(page.getByText('Parcelle Démo').first()).toBeVisible({ timeout: 20_000 });

  // ── 3. PRODUCTEURS (le producteur a été auto-créé avec la parcelle) ──
  await page.click('a.nav-link[data-mod="producers"]');
  await page.waitForURL('**/producers.html');
  await expect(page.getByText('Producteur Démo').first()).toBeVisible({ timeout: 20_000 });

  // ── 4. SATELLITE : sélection → coords auto-remplies → Analyser → NDVI réel ──
  await page.click('a.nav-link[data-mod="satellite"]');
  await page.waitForURL('**/satellite.html');
  // Les <option> d'un <select> fermé sont "hidden" → attendre 'attached', pas 'visible'.
  await page.waitForSelector('#p-select option[value="' + plantId + '"]', { state: 'attached', timeout: 20_000 });
  await page.selectOption('#p-select', plantId);
  await expect(page.locator('#lat')).not.toHaveValue(''); // autofill GPS
  await page.click('#p-btn');
  // Le NDVI affiche '—' au repos ; on attend une vraie valeur (Sentinel-2 / Copernicus)
  await expect(page.locator('#ndvi-num')).not.toHaveText('—', { timeout: 90_000 });

  // ── 5. EUDR : la page de conformité s'ouvre ──
  await page.click('a.nav-link[data-mod="eudr"]');
  await page.waitForURL('**/eudr.html');
  await expect(page.locator('#sidebar')).toBeVisible();
});
