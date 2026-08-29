import { test, expect } from '@playwright/test';
import { API, loginViaUI, openSession } from './helpers/session';
import fs from 'fs';

/**
 * Conformité EUDR — génération + téléchargement du DDS (Due Diligence Statement) PDF.
 *
 * C'est le livrable réglementaire central : le document remis à un auditeur/importateur.
 * On vérifie le parcours UI (page EUDR → bouton DDS → téléchargement) ET que le fichier
 * téléchargé est un vrai PDF (signature %PDF).
 */

test('EUDR : génération et téléchargement du DDS PDF', async ({ page, request }) => {
  test.slow();

  // ── Setup API : compte admin + parcelle géolocalisée ──
  const session = await openSession(request, 'dds');
  const { token } = session;
  const plantRes = await request.post(`${API}/plantations`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: 'Parcelle DDS', owner_name: 'Producteur DDS',
      country: "Côte d'Ivoire", region: 'Zone-Test', hectares: 2.5,
      latitude: 6.1, longitude: -6.8,
    },
  });
  expect([200, 201], `création plantation (${plantRes.status()})`).toContain(plantRes.status());

  // ── Injecter l'API réelle + connexion UI ──
  await loginViaUI(page, session);

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
