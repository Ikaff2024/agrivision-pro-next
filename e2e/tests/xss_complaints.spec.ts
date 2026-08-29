import { test, expect } from '@playwright/test';
import { API, loginViaUI, openSession } from './helpers/session';

/**
 * Non-régression SÉCURITÉ — XSS stocké via le formulaire public de signalement.
 *
 * Chaîne d'attaque fermée par ce test :
 *   POST /public/complaints (SANS COMPTE, jeton affiché dans les villages)
 *     -> description persistée verbatim
 *     -> page d'administration Signalements
 *     -> innerHTML
 *     -> JavaScript exécuté dans la session de l'administrateur
 *     -> vol de avp_token / avp_refresh_token (localStorage)
 *
 * Le test échoue si le navigateur INTERPRÈTE la charge utile ; il exige aussi
 * que le texte soit bien AFFICHÉ (une correction par suppression du champ
 * casserait la valeur probante du signalement et ne doit pas passer).
 *
 * Backend éphémère attendu sur AVP_API_URL (défaut : instance locale 8010).
 */

// Balise directe, attribut d'événement, sortie d'attribut, sortie de <option>.
const PAYLOADS = [
  '<script>window.__xss=1</script>',
  '<img src=x onerror=window.__xss=1>',
  '"><svg onload=window.__xss=1>',
  '</option><script>window.__xss=1</script>',
];

test('Un signalement public piégé ne s\'exécute pas dans la console admin', async ({ page }) => {
  // ── 1. Coopérative + admin jetables, via l'API ────────────────────────────
  const session = await openSession(page.request, 'xss');
  const auth = session.headers;

  const me = await page.request.get(`${API}/me`, { headers: auth });
  const coopId = (await me.json()).cooperative_id;
  const tok = await page.request.post(`${API}/cooperatives/${coopId}/public-report-token`, { headers: auth });
  const coopToken = (await tok.json()).public_report_token;

  // ── 2. Signalements piégés, déposés SANS AUCUNE AUTHENTIFICATION ──────────
  for (const payload of PAYLOADS) {
    const r = await page.request.post(`${API}/public/complaints`, {
      data: {
        coop_token: coopToken,
        description: `Travail des enfants signale. ${payload}`,
        reporter_name: payload,
        reporter_contact: payload,
        location_description: payload,
      },
    });
    expect(r.ok(), await r.text()).toBeTruthy();
  }

  // ── 3. L'administrateur ouvre sa console ──────────────────────────────────
  // Un dialog natif déclenché par une charge utile ferait passer le test sans
  // ce garde-fou : on considère toute boîte de dialogue comme un échec.
  let dialogSeen = false;
  page.on('dialog', async (d) => { dialogSeen = true; await d.dismiss(); });

  await loginViaUI(page, session);
  await page.goto('/complaints.html');
  await expect(page.locator('#rows tr').first()).toBeVisible({ timeout: 20_000 });

  // ── 4. La liste : aucune exécution, mais le texte est bien là ─────────────
  expect(await page.evaluate(() => (window as any).__xss)).toBeUndefined();
  expect(dialogSeen).toBeFalsy();
  await expect(page.locator('#rows')).toContainText('Travail des enfants signale.');
  // La charge utile ne doit avoir produit AUCUN élément : elle reste du texte.
  expect(await page.locator('#rows script, #rows svg, #rows iframe, #rows img[src="x"]').count()).toBe(0);

  // ── 5. La modale de détail : le point d'injection principal ───────────────
  await page.locator('#rows .action-btn').first().click();
  await expect(page.locator('#d-body')).toBeVisible();
  await expect(page.locator('#d-body')).toContainText('Travail des enfants signale.');

  expect(await page.evaluate(() => (window as any).__xss)).toBeUndefined();
  expect(dialogSeen).toBeFalsy();
  expect(await page.locator('#d-body script, #d-body svg, #d-body iframe, #d-body img').count()).toBe(0);

  // Le texte brut de la charge utile doit apparaître TEL QUEL à l'écran :
  // preuve qu'il a été échappé (affiché) et non interprété ni supprimé.
  await expect(page.locator('#d-body')).toContainText('<script>window.__xss=1</script>');
});
