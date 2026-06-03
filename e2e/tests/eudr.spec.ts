import { test, expect } from '@playwright/test';
import fs from 'fs';

/**
 * Conformité EUDR — génération + téléchargement du DDS (Due Diligence Statement) PDF.
 *
 * C'est le livrable réglementaire central : le document remis à un auditeur/importateur.
 * On vérifie le parcours UI (page EUDR → bouton DDS → téléchargement) ET que le fichier
 * téléchargé est un vrai PDF (signature %PDF).
 */

const API = process.env.AVP_API_URL || 'https://agrivision-api-production.up.railway.app';
const STAMP = Date.now();
const COOP = process.env.AVP_TEST_COOP || `E2E DDS ${STAMP}`;
const EMAIL = process.env.AVP_TEST_EMAIL || `e2e.dds.${STAMP}@agrivision.test`;
const PASSWORD = process.env.AVP_TEST_PASSWORD || 'E2eDemo!234';
const REUSE = !!process.env.AVP_TEST_EMAIL;

test('EUDR : génération et téléchargement du DDS PDF', async ({ page, request }) => {
  test.slow();

  // ── Setup API : compte admin + parcelle géolocalisée ──
  if (!REUSE) {
    const reg = await request.post(`${API}/auth/register`, {
      data: { email: EMAIL, password: PASSWORD, role: 'admin', cooperative_name: COOP, country: 'CI' },
    });
    expect(reg.ok(), `register (${reg.status()}): ${await reg.text()}`).toBeTruthy();
  }
  const login = await request.post(`${API}/auth/login`, { data: { email: EMAIL, password: PASSWORD } });
  expect(login.ok(), `login API (${login.status()})`).toBeTruthy();
  const token = (await login.json()).access_token as string;
  const plantRes = await request.post(`${API}/plantations`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: 'Parcelle DDS', owner_name: 'Producteur DDS',
      country: "Côte d'Ivoire", region: 'Yeyasso', hectares: 2.5,
      latitude: 6.1, longitude: -6.8,
    },
  });
  expect([200, 201], `création plantation (${plantRes.status()})`).toContain(plantRes.status());

  // ── Injecter l'API réelle + connexion UI ──
  await page.addInitScript((api) => {
    (window as any).AGRIVISION_API_BASE = api;
    (window as any).CG_API_BASE = api;
  }, API);
  await page.goto('/login.html');
  await page.fill('#email', EMAIL);
  await page.fill('#pass', PASSWORD);
  await page.click('#btn');
  await page.waitForURL('**/plantations.html', { timeout: 30_000 });

  // ── Page EUDR : la parcelle apparaît avec son statut de conformité ──
  await page.click('a.nav-link[data-mod="eudr"]');
  await page.waitForURL('**/eudr.html');
  await expect(page.getByText('Parcelle DDS').first()).toBeVisible({ timeout: 20_000 });

  // ── Téléchargement du DDS PDF (cgFetch → blob → ancre <a download>) ──
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 60_000 }),
    page.click('button:has-text("DDS")'),
  ]);
  expect(download.suggestedFilename(), 'nom de fichier').toMatch(/\.pdf$/i);

  // ── C'est bien un PDF valide (signature %PDF) ──
  const path = await download.path();
  expect(path, 'fichier téléchargé').toBeTruthy();
  const head = fs.readFileSync(path!).subarray(0, 5).toString('latin1');
  expect(head, `entête fichier = ${head}`).toMatch(/^%PDF/);
});
