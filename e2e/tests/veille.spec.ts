import { test, expect } from '@playwright/test';

/**
 * Veille Marché Cacao : la page se charge via notre stack (initApp + authFetch),
 * affiche le compteur EUDR et le prix CCC officiel, et dégrade gracieusement
 * quand le service IA n'est pas configuré (cas CI : pas de clé → fallback).
 */

const API = process.env.AVP_API_URL || 'https://agrivision-api-production.up.railway.app';
const STAMP = Date.now();
const COOP = process.env.AVP_TEST_COOP || `E2E Veille ${STAMP}`;
const EMAIL = process.env.AVP_TEST_EMAIL || `e2e.veille.${STAMP}@agrivision.test`;
const PASSWORD = process.env.AVP_TEST_PASSWORD || 'E2eDemo!234';
const REUSE = !!process.env.AVP_TEST_EMAIL;

test('Veille Marché : chargement + dégradation gracieuse', async ({ page, request }) => {
  test.slow();

  if (!REUSE) {
    const reg = await request.post(`${API}/auth/register`, {
      data: { email: EMAIL, password: PASSWORD, role: 'admin', cooperative_name: COOP, country: 'CI' },
    });
    expect(reg.ok(), `register (${reg.status()}): ${await reg.text()}`).toBeTruthy();
  }

  await page.addInitScript((api) => {
    (window as any).AGRIVISION_API_BASE = api;
    (window as any).CG_API_BASE = api;
  }, API);
  await page.goto('/login.html');
  await page.fill('#email', EMAIL);
  await page.fill('#pass', PASSWORD);
  await page.click('#btn');
  await page.waitForURL('**/plantations.html', { timeout: 30_000 });

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
