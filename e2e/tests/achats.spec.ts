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

  // Une parcelle crée automatiquement un producteur.
  const plantRes = await request.post(`${API}/plantations`, {
    headers,
    data: {
      name: 'Parcelle Achat', owner_name: 'Producteur Achat',
      country: "Côte d'Ivoire", region: 'Zone-Test', hectares: 2.0,
    },
  });
  expect([200, 201]).toContain(plantRes.status());
  const producers = await (await request.get(`${API}/producers?limit=50`, { headers })).json();
  expect(producers.length, 'producteur auto-créé').toBeGreaterThan(0);
  const producerId = String(producers[0].id);

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
