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
