import { test, expect } from '@playwright/test';
import { loginViaUI, openSession } from './helpers/session';

/**
 * Veille Marché Cacao : la page se charge via notre stack (initApp + authFetch),
 * affiche le compteur EUDR et le prix CCC officiel, et dégrade gracieusement
 * quand le service IA n'est pas configuré (cas CI : pas de clé → fallback).
 */

test('Veille Marché : chargement + dégradation gracieuse', async ({ page, request }) => {
  test.slow();

  const session = await openSession(request, 'veille');

  await loginViaUI(page, session);

  // Le lien Veille Marché est visible (plan enterprise par défaut → premium inclus).
  await page.click('a.nav-link[data-mod="veille"]');
  await page.waitForURL('**/veille.html');

  // Compteur EUDR (calcul client) : un nombre, pas le tiret initial.
  await expect(page.locator('#vm-eudr-days')).not.toHaveText('—', { timeout: 20_000 });
  // Prix CCC officiel (vient de la config serveur, présent même en fallback).
  await expect(page.locator('#vm-ccc')).toContainText('FCFA/kg', { timeout: 20_000 });
  // Sans clé IA (CI), la page affiche un message d'indisponibilité — pas d'erreur brutale.
  await expect(page.locator('#vm-info')).toBeVisible();
});
