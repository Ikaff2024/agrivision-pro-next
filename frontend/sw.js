/**
 * AgriVision Pro â€” Service Worker v2.0
 *
 * StratÃ©gies de cache :
 *  - HTML + JS applicatif  â†’ Network First  (toujours Ã  jour aprÃ¨s dÃ©ploiement)
 *  - API Railway           â†’ Network First avec fallback cache (donnÃ©es terrain)
 *  - CDN externes          â†’ Cache First    (Leaflet, Chart.js, fonts â€” immuables)
 *  - Autres                â†’ Network Only   (satellite, images ML)
 *
 * v2.0 : correction du bug de cache â€” les pages HTML et auth.js
 *        sont dÃ©sormais en Network First pour reflÃ©ter les dÃ©ploiements
 *        immÃ©diatement, sans que l'utilisateur ait Ã  vider son cache.
 */

const CACHE_VERSION = 'avp-v2.5';
const STATIC_CACHE  = `${CACHE_VERSION}-static`;
const API_CACHE     = `${CACHE_VERSION}-api`;

// Assets statiques Ã  prÃ©cacher Ã  l'installation
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
  '/ai-advice.js',
  '/offline.html',
];

// Pages HTML et JS applicatif â†’ Network First obligatoire
// (tout ce qui peut changer Ã  chaque dÃ©ploiement Netlify)
const NETWORK_FIRST_PATTERNS = [
  /\.html$/,
  /auth\.js$/,
  /config\.js$/,
  /ai-advice\.js$/,
];

// PrÃ©fixes API Railway Ã  mettre en cache pour le mode offline
const API_ORIGIN = 'https://handsome-wisdom-production-d83b.up.railway.app';
const CACHEABLE_API_PATHS = [
  '/plantations',
  '/map/plantations',
  '/map/stats',
  '/diagnostics',
  '/agroforestry/summary',
];

// â”€â”€ Installation : prÃ©cacher les assets â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => {
      console.log('[SW v2.0] PrÃ©cache des assets statiques');
      return cache.addAll(STATIC_ASSETS);
    }).then(() => self.skipWaiting())   // force activation immÃ©diate
  );
});

// â”€â”€ Activation : nettoyer TOUS les anciens caches â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
      console.log('[SW v2.0] ActivÃ© â€” contrÃ´le de tous les clients');
      return self.clients.claim();  // prendre le contrÃ´le immÃ©diatement
    })
  );
});

// â”€â”€ Fetch : intercepter toutes les requÃªtes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // 1. API Railway â†’ Network First avec fallback cache
  if (url.origin === API_ORIGIN) {
    const isCacheable = CACHEABLE_API_PATHS.some(p => url.pathname.startsWith(p));
    if (isCacheable && request.method === 'GET') {
      event.respondWith(networkFirstAPI(request));
    }
    // POST/PUT/DELETE â†’ Network Only (mutations non cachÃ©es)
    return;
  }

  // 2. Assets applicatifs (HTML + JS projet) â†’ Network First
  if (url.origin === self.location.origin) {
    const isAppAsset = NETWORK_FIRST_PATTERNS.some(p => p.test(url.pathname));
    if (isAppAsset) {
      event.respondWith(networkFirstStatic(request));
      return;
    }
    // Autres assets locaux (images, manifest, icons) â†’ Cache First
    event.respondWith(cacheFirstStatic(request));
    return;
  }

  // 3. CDN externes (Leaflet, Chart.js, Google Fonts) â†’ Cache First
  event.respondWith(cacheFirstStatic(request));
});

// â”€â”€ Network First (HTML + JS applicatif) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// Tente toujours le rÃ©seau en premier.
// Si hors ligne â†’ fallback sur le cache.
// Met Ã  jour le cache Ã  chaque rÃ©ponse rÃ©seau rÃ©ussie.
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

// â”€â”€ Cache First (CDN + assets immuables) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// Sert depuis le cache si disponible.
// TÃ©lÃ©charge et met en cache si absent.
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

// â”€â”€ Network First API (donnÃ©es terrain offline) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
      console.log('[SW v2.0] Offline â€” donnÃ©es cache:', request.url);
      return cached;
    }
    return new Response(
      JSON.stringify({ error: 'DonnÃ©es non disponibles hors ligne.' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}
