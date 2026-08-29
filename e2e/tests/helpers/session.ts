/**
 * Socle commun des tests E2E : ouverture de session et pilotage des widgets
 * maison. Un seul point de vérité pour les gestes que TOUS les parcours
 * répètent — sans quoi un changement produit sur la connexion casse la suite
 * entière, spec par spec (c'est exactement ce qui est arrivé le 04/07/2026 avec
 * l'atterrissage par rôle).
 *
 * Chaque test ouvre sa PROPRE coopérative jetable : aucun test ne dépend des
 * données d'un autre, ni d'une base pré-peuplée, ni d'un compte de production.
 * Les valeurs sont entièrement synthétiques (domaine `.test`, réservé RFC 2606).
 */
import { expect, type APIRequestContext, type Page } from '@playwright/test';

/**
 * Backend visé. Par défaut l'instance LOCALE éphémère : un test ne doit jamais
 * créer de coopérative jetable dans la production par simple oubli de variable
 * d'environnement. Viser un autre environnement reste explicite (AVP_API_URL).
 */
export const API = process.env.AVP_API_URL || 'http://127.0.0.1:8010';

/** Compte + coopérative jetables, et le jeton API associé. */
export type Session = {
  email: string;
  password: string;
  coop: string;
  token: string;
  headers: { Authorization: string };
};

/**
 * Crée une coopérative jetable et renvoie une session authentifiée.
 *
 * `slug` sert uniquement à rendre les objets créés reconnaissables dans les
 * traces (« E2E pay 1756…»). Définir AVP_TEST_EMAIL/AVP_TEST_PASSWORD réutilise
 * un compte existant au lieu d'en créer un (démo sur un environnement peuplé).
 */
export async function openSession(request: APIRequestContext, slug: string): Promise<Session> {
  const stamp = Date.now();
  const reuse = !!process.env.AVP_TEST_EMAIL;
  const email = process.env.AVP_TEST_EMAIL || `e2e.${slug}.${stamp}@agrivision.test`;
  const password = process.env.AVP_TEST_PASSWORD || 'E2eDemo!234';
  const coop = process.env.AVP_TEST_COOP || `E2E ${slug} ${stamp}`;

  if (!reuse) {
    const reg = await request.post(`${API}/auth/register`, {
      data: { email, password, role: 'admin', cooperative_name: coop, country: 'CI' },
    });
    expect(reg.ok(), `register (${reg.status()}): ${await reg.text()}`).toBeTruthy();
  }
  const login = await request.post(`${API}/auth/login`, { data: { email, password } });
  expect(login.ok(), `login API (${login.status()})`).toBeTruthy();
  const token = (await login.json()).access_token as string;
  return { email, password, coop, token, headers: { Authorization: `Bearer ${token}` } };
}

/**
 * Pointe la page servie en local vers l'API visée par le test.
 *
 * À appeler AVANT toute navigation : `config.js` lit ces globales au chargement.
 */
export async function useApiBase(page: Page): Promise<void> {
  await page.addInitScript((api) => {
    (window as any).AGRIVISION_API_BASE = api;
    (window as any).CG_API_BASE = api;
  }, API);
}

/**
 * Connexion par le formulaire, comme un utilisateur.
 *
 * On ne vise volontairement AUCUNE page d'arrivée : depuis `feat(ux)` 3baaef1,
 * l'atterrissage dépend du rôle (technicien → parcelles, pilotage → tableau de
 * bord) et le figer dans quinze specs les a toutes cassées. Ce qui est vérifié
 * ici est ce que « être connecté » veut dire, et c'est plus fort qu'une URL :
 *   1. l'API a bien répondu 200 au POST /auth/login déclenché par le clic ;
 *   2. la page a quitté l'écran de connexion ;
 *   3. le jeton de session est posé côté navigateur.
 * Une régression sur l'un des trois fait échouer le test.
 */
export async function loginViaUI(page: Page, session: Session): Promise<void> {
  await useApiBase(page);
  await page.goto('/login.html');
  await page.fill('#email', session.email);
  await page.fill('#pass', session.password);

  const [res] = await Promise.all([
    page.waitForResponse(
      (r) => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith('/auth/login'),
      { timeout: 30_000 },
    ),
    page.click('#btn'),
  ]);
  expect(res.status(), `POST /auth/login depuis l'UI`).toBe(200);

  await page.waitForURL((url) => !url.pathname.endsWith('/login.html'), { timeout: 30_000 });
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('avp_token')), { timeout: 10_000 })
    .toBeTruthy();
}
