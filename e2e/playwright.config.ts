import { defineConfig, devices } from '@playwright/test';

/**
 * Configuration Playwright — AgriVision Pro
 *
 * Deux modes :
 *  1) LOCAL (défaut) : on sert `../frontend` via un petit serveur statique Python
 *     et on injecte l'API Railway réelle dans la page (voir demo.spec.ts).
 *     → teste exactement les fichiers de la branche, contre le vrai backend.
 *  2) DISTANT : si AVP_BASE_URL est défini (ex. l'URL Netlify de staging),
 *     on tape directement dessus et on ne lance pas de serveur local.
 *
 * Variables d'environnement utiles :
 *   AVP_BASE_URL   URL du frontend (défaut http://127.0.0.1:8080, servi localement)
 *   AVP_API_URL    URL du backend  (défaut https://agrivision-api-production.up.railway.app)
 *   AVP_PORT       port du serveur statique local (défaut 8080)
 *   AVP_TEST_EMAIL / AVP_TEST_PASSWORD  réutiliser un compte existant (sinon coop jetable)
 */

// 5510 est déjà dans l'allowlist CORS du backend (cf. main.py) → la connexion
// navigateur → API Railway passe sans changement serveur. Override via AVP_PORT
// (pensez alors à ajouter l'origine à CORS_ALLOWED_ORIGINS côté backend).
const PORT = process.env.AVP_PORT || '5510';
const BASE_URL = process.env.AVP_BASE_URL || `http://127.0.0.1:${PORT}`;
const SERVE_LOCAL = !process.env.AVP_BASE_URL;

export default defineConfig({
  testDir: './tests',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: BASE_URL,
    video: 'on',                 // vidéo de chaque test (pour la démo)
    screenshot: 'only-on-failure',
    trace: 'on-first-retry',
    actionTimeout: 20_000,
    viewport: { width: 1366, height: 820 },
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  // Sert le frontend local uniquement quand on ne vise pas un staging distant.
  webServer: SERVE_LOCAL
    ? {
        command: `python -m http.server ${PORT} -d ../frontend`,
        url: BASE_URL,
        reuseExistingServer: true,
        timeout: 30_000,
      }
    : undefined,
});
