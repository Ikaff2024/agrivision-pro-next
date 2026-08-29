import { test, expect } from '@playwright/test';
import { API, loginViaUI, openSession, openModule, pickInCombo } from './helpers/session';

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

test('Parcours démo : connexion → producteur → satellite → EUDR', async ({ page, request }) => {
  test.slow(); // analyse satellite réelle = peut être longue

  // ── 1. SETUP via API : compte (coop fondatrice = admin) + 1 parcelle GPS ──
  const session = await openSession(request, 'demo');
  const { token } = session;

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

  // ── 2. CONNEXION via l'UI, puis navigation vers les PARCELLES ──
  // L'atterrissage post-connexion dépend du rôle : on rejoint la page voulue
  // par le menu, comme un utilisateur, au lieu de la supposer.
  await loginViaUI(page, session);
  await openModule(page, 'plantations');
  await page.waitForURL('**/plantations.html');
  await expect(page.getByText('Parcelle Démo').first()).toBeVisible({ timeout: 20_000 });

  // ── 3. PRODUCTEURS (le producteur a été auto-créé avec la parcelle) ──
  await openModule(page, 'producers');
  await page.waitForURL('**/producers.html');
  await expect(page.getByText('Producteur Démo').first()).toBeVisible({ timeout: 20_000 });

  // ── 4. SATELLITE : sélection → coords auto-remplies → Analyser → NDVI réel ──
  await openModule(page, 'satellite');
  await page.waitForURL('**/satellite.html');
  // Le <select> porte `data-searchable` : auth.js le masque et le remplace par
  // une liste cherchable insérée juste après lui. On pilote ce composant.
  await pickInCombo(page, '#p-select + .avp-combo', plantId);
  await expect(page.locator('#lat')).not.toHaveValue(''); // autofill GPS
  await page.click('#p-btn');
  // Le NDVI affiche '—' au repos ; on attend une vraie valeur (Sentinel-2 / Copernicus)
  await expect(page.locator('#ndvi-num')).not.toHaveText('—', { timeout: 90_000 });

  // ── 5. EUDR : la page de conformité s'ouvre ──
  await openModule(page, 'eudr');
  await page.waitForURL('**/eudr.html');
  await expect(page.locator('#sidebar')).toBeVisible();
});
