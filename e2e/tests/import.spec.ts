import { test, expect } from '@playwright/test';
import { loginViaUI, openSession } from './helpers/session';
import path from 'path';

/**
 * Import d'un registre + ANNULATION du lot (Point #3 du backlog).
 *
 * Parcours complet dans l'UI : on téléverse un vrai fichier Excel (fixture), on
 * lance l'import, puis on annule le lot depuis l'« Historique des imports » via
 * la confirmation `avpConfirm`. On vérifie que le statut passe à « Annulé ».
 *
 * Vérifie de bout en bout la fonctionnalité d'annulation d'import (6d47701).
 */

const FIXTURE = path.join(__dirname, '..', 'fixtures', 'registre_demo_e2e.xlsx');

test("Import de registre + annulation du lot (Point #3)", async ({ page, request }) => {
  test.slow();

  // ── Setup API : compte admin (coop vierge) ──
  const session = await openSession(request, 'import');

  await loginViaUI(page, session);

  // ── Page Import : téléverser le fichier, prévisualiser, lancer l'import ──
  await page.goto('/import.html');
  await page.setInputFiles('#file-input', FIXTURE);
  await page.click('#btn-preview');
  await expect(page.locator('#btn-import')).toBeEnabled({ timeout: 30_000 });
  await page.click('#btn-import');

  // Rapport d'import : 3 producteurs + 3 plantations créés
  await expect(page.locator('#import-result')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('#rep-producers')).toHaveText('3');
  await expect(page.locator('#rep-plantations')).toHaveText('3');

  // ── Historique : le lot apparaît, on l'annule (assertions scopées à l'historique
  //    pour ne pas matcher le nom de fichier affiché dans le panneau d'upload) ──
  await page.click('button:has-text("Actualiser")');
  const history = page.locator('#import-history');
  await expect(history.getByText('registre_demo_e2e.xlsx')).toBeVisible({ timeout: 15_000 });
  await history.locator('button:has-text("Annuler cet import")').click();

  // Confirmation (avpConfirm) → DELETE /import/batches/{uuid}
  const [delResp] = await Promise.all([
    page.waitForResponse(r => r.request().method() === 'DELETE' && r.url().includes('/import/batches/')),
    page.getByRole('button', { name: "Annuler l'import", exact: true }).click(),
  ]);
  expect(delResp.ok(), `DELETE batch (${delResp.status()})`).toBeTruthy();

  // Le lot est désormais « Annulé » (et le bouton d'annulation a disparu).
  await expect(history.getByText('Annulé')).toBeVisible({ timeout: 15_000 });
  await expect(history.locator('button:has-text("Annuler cet import")')).toHaveCount(0);
});
