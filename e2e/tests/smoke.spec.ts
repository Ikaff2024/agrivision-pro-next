import { test, expect } from '@playwright/test';

/** Smoke ultra-rapide : la page de connexion se charge et a ses champs. */
test('La page de connexion se charge', async ({ page }) => {
  await page.goto('/login.html');
  await expect(page).toHaveTitle(/Connexion/i);
  await expect(page.locator('#email')).toBeVisible();
  await expect(page.locator('#pass')).toBeVisible();
  await expect(page.locator('#btn')).toContainText('Se connecter');
});
