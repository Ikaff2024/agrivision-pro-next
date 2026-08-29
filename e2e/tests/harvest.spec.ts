import { test, expect } from '@playwright/test';
import { API, loginViaUI, openSession, pickInCombo } from './helpers/session';

/**
 * Récolte avec n° de reçu d'achat (Point #4 du backlog).
 *
 * Vérifie de bout en bout le champ « numéro de reçu d'achat » (#h-receipt) et
 * « nombre de sacs » (#h-bags) ajoutés au formulaire de saisie : on saisit une
 * récolte et on confirme que le n° de reçu apparaît dans le tableau.
 */

const STAMP = Date.now();
const RECEIPT = `REC-E2E-${STAMP}`;

test("Récolte : saisie avec n° de reçu d'achat (Point #4)", async ({ page, request }) => {
  test.slow();

  // ── Setup API : compte admin + parcelle ──
  const session = await openSession(request, 'recolte');
  const { token } = session;
  const plantRes = await request.post(`${API}/plantations`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: 'Parcelle Récolte', owner_name: 'Producteur Récolte',
      country: "Côte d'Ivoire", region: 'Zone-Test', hectares: 3.0,
      latitude: 6.2, longitude: -6.5,
    },
  });
  expect([200, 201], `création plantation (${plantRes.status()})`).toContain(plantRes.status());
  const plantId = String((await plantRes.json()).id);

  // ── Connexion UI ──
  await loginViaUI(page, session);

  // ── Page Récoltes : choisir la parcelle (révèle le bouton de saisie) ──
  await page.goto('/harvests.html');
  await pickInCombo(page, '#plantation-combo', plantId);

  // ── Modale de saisie : quantité + N° de reçu (Point #4) + nb de sacs ──
  await page.click('#add-btn'); // apparaît après sélection de la parcelle
  await page.fill('#h-quantity', '850');   // date + qualité ("Bonne") pré-remplies
  await page.fill('#h-receipt', RECEIPT);
  await page.fill('#h-bags', '12');
  await page.click('#h-submit-btn');

  // ── Le n° de reçu apparaît dans le tableau des récoltes ──
  await expect(page.getByText(RECEIPT).first()).toBeVisible({ timeout: 20_000 });
});

/**
 * Non-régression : le tableau des récoltes survit à l'absence du graphique.
 *
 * `harvests.html` charge Chart.js depuis un CDN. Quand cette requête échoue —
 * tournée hors ligne (le cœur du produit), réseau filtré, CDN indisponible —
 * `new Chart` levait une exception AVANT le rendu du tableau : la page perdait
 * silencieusement toute sa donnée métier. Ce test coupe le CDN et exige que la
 * récolte reste lisible.
 */
test('Récolte : le tableau reste affiché quand le CDN du graphique tombe', async ({ page, request }) => {
  test.slow();

  const session = await openSession(request, 'recolte-nocdn');
  const { token, headers } = session;
  const plantRes = await request.post(`${API}/plantations`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: 'Parcelle Sans CDN', owner_name: 'Producteur Sans CDN',
      country: "Côte d'Ivoire", region: 'Zone-Test', hectares: 2.0,
    },
  });
  expect([200, 201], `création plantation (${plantRes.status()})`).toContain(plantRes.status());
  const plantId = String((await plantRes.json()).id);

  // Une récolte existe déjà : c'est ce qui déclenche le rendu du graphique.
  const recu = `REC-NOCDN-${Date.now()}`;
  const harvest = await request.post(`${API}/plantations/${plantId}/harvests`, {
    headers,
    data: { harvest_date: '2026-08-01T08:00:00', quantity_kg: 640, quality: 'Bonne', numero_recu_achat: recu },
  });
  expect([200, 201], `récolte (${harvest.status()})`).toContain(harvest.status());

  // Le CDN du graphique est injoignable.
  await page.route(/cdn\.jsdelivr\.net\/.*chart/i, (route) => route.abort());

  await loginViaUI(page, session);
  await page.goto('/harvests.html');
  await pickInCombo(page, '#plantation-combo', plantId);

  // La bibliothèque n'est effectivement pas chargée…
  expect(await page.evaluate(() => typeof (window as any).Chart)).toBe('undefined');
  // …et la donnée métier reste néanmoins affichée.
  await expect(page.locator('#table-wrap table')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(recu).first()).toBeVisible({ timeout: 20_000 });
});
