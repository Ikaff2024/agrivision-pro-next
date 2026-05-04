/**
 * AgriVision Pro — Service Worker v2.0
 *
 * Stratégies de cache :
 *  - HTML + JS applicatif  → Network First  (toujours à jour après déploiement)
 *  - API Railway           → Network First avec fallback cache (données terrain)
 *  - CDN externes          → Cache First    (Leaflet, Chart.js, fonts — immuables)
 *  - Autres                → Network Only   (satellite, images ML)
 *
 * v2.0 : correction du bug de cache — les pages HTML et auth.js
 *        sont désormais en Network First pour refléter les déploiements
 *        immédiatement, sans que l'utilisateur ait à vider son cache.
 */

const CACHE_VERSION = 'avp-v2.9';
const STATIC_CACHE  = `${CACHE_VERSION}-static`;
const API_CACHE     = `${CACHE_VERSION}-api`;

// Assets statiques à précacher à l'installation
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/plantations.html',
  '/diagnostic.html',
  '/map.html',
  '/analytics.html',
  '/satellite.html',
  '/agroforestry.html',
  '/plantation_detail.html',
  '/auth.js',
  '/offline.html',
];

// Pages HTML et JS applicatif → Network First obligatoire
// (tout ce qui peut changer à chaque déploiement Netlify)
const NETWORK_FIRST_PATTERNS = [
  /\.html$/,
  /auth\.js$/,
  /config\.js$/,
];

// Préfixes API Railway à mettre en cache pour le mode offline
const API_ORIGIN = 'https://handsome-wisdom-production-d83b.up.railway.app';
const CACHEABLE_API_PATHS = [
  '/plantations',
  '/map/plantations',
  '/map/stats',
  '/diagnostics',
  '/agroforestry/summary',
];

// ── Installation : précacher les assets ───────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => {
      console.log('[SW v2.0] Précache des assets statiques');
      return cache.addAll(STATIC_ASSETS);
    }).then(() => self.skipWaiting())   // force activation immédiate
  );
});

// ── Activation : nettoyer TOUS les anciens caches ─────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== STATIC_CACHE && k !== API_CACHE)
          .map(k => {
            console.log('[SW v2.0] Suppression ancien cache:', k);
            return caches.delete(k);
          })
      )
    ).then(() => {
      console.log('[SW v2.0] Activé — contrôle de tous les clients');
      return self.clients.claim();  // prendre le contrôle immédiatement
    })
  );
});

// ── Fetch : intercepter toutes les requêtes ───────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // 1. API Railway → Network First avec fallback cache
  if (url.origin === API_ORIGIN) {
    const isCacheable = CACHEABLE_API_PATHS.some(p => url.pathname.startsWith(p));
    if (isCacheable && request.method === 'GET') {
      event.respondWith(networkFirstAPI(request));
    }
    // POST/PUT/DELETE → Network Only (mutations non cachées)
    return;
  }

  // 2. Assets applicatifs (HTML + JS projet) → Network First
  if (url.origin === self.location.origin) {
    const isAppAsset = NETWORK_FIRST_PATTERNS.some(p => p.test(url.pathname));
    if (isAppAsset) {
      event.respondWith(networkFirstStatic(request));
      return;
    }
    // Autres assets locaux (images, manifest, icons) → Cache First
    event.respondWith(cacheFirstStatic(request));
    return;
  }

  // 3. CDN externes (Leaflet, Chart.js, Google Fonts) → Cache First
  event.respondWith(cacheFirstStatic(request));
});

// ── Network First (HTML + JS applicatif) ─────────────────────────────────
// Tente toujours le réseau en premier.
// Si hors ligne → fallback sur le cache.
// Met à jour le cache à chaque réponse réseau réussie.
async function networkFirstStatic(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    if (request.headers.get('accept')?.includes('text/html')) {
      return caches.match('/offline.html');
    }
    return new Response('Hors ligne', { status: 503 });
  }
}

// ── Cache First (CDN + assets immuables) ─────────────────────────────────
// Sert depuis le cache si disponible.
// Télécharge et met en cache si absent.
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
    if (request.headers.get('accept')?.includes('text/html')) {
      return caches.match('/offline.html');
    }
    return new Response('Hors ligne', { status: 503 });
  }
}

// ── Network First API (données terrain offline) ───────────────────────────
async function networkFirstAPI(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(API_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) {
      console.log('[SW v2.0] Offline — données cache:', request.url);
      return cached;
    }
    return new Response(
      JSON.stringify({ error: 'Données non disponibles hors ligne.' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}
