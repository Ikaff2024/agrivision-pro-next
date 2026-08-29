import { test, expect } from '@playwright/test';
import { API, loginViaUI, openSession, pickInCombo } from './helpers/session';

/**
 * Achats producteurs : enregistrement d'un achat depuis l'UI.
 *
 * Sélection du producteur, saisie du poids / prix / n° de bon d'achat, puis
 * vérification que le compteur d'achats passe à 1.
 */

const STAMP = Date.now();

test('Achats : enregistrer un achat producteur', async ({ page, request }) => {
  test.slow();

  const session = await openSession(request, 'achat');
  const { token, headers } = session;

  // L'achat vise les NON-MEMBRES (verrou métier 59eab40 : pour un membre, la
  // coop saisit une récolte). Le producteur auto-créé avec une parcelle est un
  // membre : on crée donc explicitement le non-membre auquel on achète.
  const prodRes = await request.post(`${API}/producers`, {
    headers, data: { nom_complet: 'Producteur Achat', type_producteur: 'non_membre' },
  });
  expect([200, 201], `producteur (${prodRes.status()}): ${await prodRes.text()}`)
    .toContain(prodRes.status());
  const producerId = String((await prodRes.json()).id);

  // ── UI : connexion puis saisie de l'achat ──
  await loginViaUI(page, session);

  await page.goto('/achats.html');
  await pickInCombo(page, '#b-producer-combo', producerId);
  await page.fill('#b-gross', '100');
  await page.fill('#b-net', '100');
  await page.fill('#b-price', '1000');
  await page.fill('#b-receipt', `BON-E2E-${STAMP}`);
  await page.click("button:has-text(\"Enregistrer l'achat\")");

  // Le compteur d'achats passe à 1.
  await expect(page.locator('#k-count')).toHaveText('1', { timeout: 15_000 });
});
