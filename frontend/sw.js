/**
 * AgriVision Pro — Service Worker v1.0
 *
 * Stratégies de cache :
 *  - STATIC assets  → Cache First  (HTML, JS, fonts, icons CDN)
 *  - API Railway    → Network First avec fallback cache (données terrain)
 *  - Autres         → Network Only (satellite, images ML)
 */

const CACHE_VERSION   = 'avp-v1.0';
const STATIC_CACHE    = `${CACHE_VERSION}-static`;
const API_CACHE       = `${CACHE_VERSION}-api`;

// Assets statiques à précacher à l'installation
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/plantations.html',
  '/diagnostic.html',
  '/map.html',
  '/analytics.html',
  '/auth.js',
  '/offline.html',
];

// Préfixes d'URL Railway pour les requêtes API à cacher
const API_ORIGIN = 'https://handsome-wisdom-production-d83b.up.railway.app';
const CACHEABLE_API_PATHS = [
  '/plantations',
  '/map/plantations',
  '/map/stats',
  '/diagnostics',
];

// ── Installation : précacher les assets statiques ─────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => {
      console.log('[SW] Précache des assets statiques');
      return cache.addAll(STATIC_ASSETS);
    }).then(() => self.skipWaiting())
  );
});

// ── Activation : nettoyer les anciens caches ──────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k.startsWith('avp-') && k !== STATIC_CACHE && k !== API_CACHE)
          .map(k => {
            console.log('[SW] Suppression ancien cache:', k);
            return caches.delete(k);
          })
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch : intercepter toutes les requêtes ───────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // 1. Requêtes API Railway → Network First avec fallback cache
  if (url.origin === API_ORIGIN) {
    const isCacheable = CACHEABLE_API_PATHS.some(p => url.pathname.startsWith(p));
    if (isCacheable && request.method === 'GET') {
      event.respondWith(networkFirstAPI(request));
      return;
    }
    // POST/PUT/DELETE → Network Only (on ne cache pas les mutations)
    return;
  }

  // 2. Assets statiques → Cache First
  if (url.origin === self.location.origin) {
    event.respondWith(cacheFirstStatic(request));
    return;
  }

  // 3. CDN externes (fonts, Leaflet, Chart.js) → Cache First
  event.respondWith(cacheFirstStatic(request));
});

// ── Stratégie : Cache First (assets statiques + CDN) ─────────────────────
async function cacheFirstStatic(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    // Fallback page offline si on demande un HTML
    if (request.headers.get('accept')?.includes('text/html')) {
      return caches.match('/offline.html');
    }
    return new Response('Hors ligne', { status: 503 });
  }
}

// ── Stratégie : Network First avec fallback cache (API) ───────────────────
async function networkFirstAPI(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(API_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    // Réseau indisponible → retourner les données en cache si disponibles
    const cached = await caches.match(request);
    if (cached) {
      console.log('[SW] Offline — données cache pour:', request.url);
      return cached;
    }
    return new Response(
      JSON.stringify({ error: 'Données non disponibles hors ligne.' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}
