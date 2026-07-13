/**
 * AgriVision Pro — Service Worker v3.0
 *
 * Stratégies de cache :
 *  - HTML + JS applicatif  → Network First  (toujours à jour après déploiement)
 *  - API Railway           → Network First avec fallback cache (données terrain)
 *  - CDN externes          → Cache First    (Leaflet, Chart.js, fonts — immuables)
 *  - Autres                → Network Only   (satellite, images ML)
 *
 * v3.0 (Sprint Offline V1.6 Phase 3a-fix) — 3 corrections critiques :
 *   1. Filtre des schemes non-HTTP au début du fetch handler
 *      (ignore chrome-extension://, moz-extension://, data:, blob:)
 *   2. Wrap try/catch silencieux autour de cache.put pour les requêtes
 *      qui ne sont pas mises en cache (opaque, no-store, etc.)
 *   3. Match du cache avec ignoreSearch pour servir /plantation_detail.html
 *      même quand l'URL contient une query string (?id=42)
 *
 * v2.0 : correction du bug de cache — les pages HTML et auth.js
 *        sont en Network First pour refléter les déploiements
 *        immédiatement, sans que l'utilisateur ait à vider son cache.
 */

const CACHE_VERSION = 'avp-v4.97-anti-flash';
const STATIC_CACHE  = `${CACHE_VERSION}-static`;
const API_CACHE     = `${CACHE_VERSION}-api`;

// Assets statiques à précacher à l'installation
const STATIC_ASSETS = [
  '/',
  '/cacaoguard.html',
  '/children.html',
  '/achats.html',
  '/certification.html',
  '/direction.html',
  '/lots.html',
  '/reset_password.html',
  '/compliance.html',
  '/complaints.html',
  '/eudr.html',
  '/farmforce.html',
  '/index.html',
  '/monitoring.html',
  '/plantations.html',
  '/producers.html',
  '/guide.html',
  '/remediation.html',
  '/reports_cacaoguard.html',
  '/risk_assessment.html',
  '/diagnostic.html',
  '/map.html',
  '/analytics.html',
  '/satellite.html',
  '/veille.html',
  '/twin_risk.html',
  '/training.html',
  '/agroforestry.html',
  '/assistant.html',
  '/plantation_detail.html',
  '/producer_profile.html',
  '/config.js',
  '/auth.js',
  '/avp-offline.js',
  '/offline.html',
];

// Pages HTML et JS applicatif → Network First obligatoire
// (tout ce qui peut changer à chaque déploiement Netlify)
const NETWORK_FIRST_PATTERNS = [
  /\.html$/,
  /auth\.js$/,
  /config\.js$/,
  /avp-offline\.js$/,
];

// Fonds de carte (tuiles) → Network First : on ne fige jamais une tuile grise
// « Map data not yet available » d'Esri ; le cache ne sert qu'en secours hors ligne.
const MAP_TILE_HOSTS = ['arcgisonline.com', 'cartocdn.com'];

// Préfixes API Railway à mettre en cache pour le mode offline
const API_ORIGIN = 'https://agrivision-api-production.up.railway.app';
const LOCAL_API_ORIGINS = new Set([
  'http://127.0.0.1:8010',
  'http://localhost:8010',
]);
const CACHEABLE_API_PATHS = [
  '/plantations',
  '/map/plantations',
  '/map/stats',
  '/diagnostics',
  '/agroforestry/summary',
  '/children',
  '/monitoring/visits',
  '/producers',
  '/cacaoguard/summary',
  '/compliance/traceability',
  '/compliance/report',
  '/remediation/plans',
  '/training/sessions',
  '/purchases',
  '/complaints',
  '/ssrte',
  '/farmforce',
];

// ── Helper : mise en cache silencieuse (v3.0 fix #2) ──────────────────────
// Cache.put peut échouer pour plusieurs raisons :
//   - scheme chrome-extension:// non supporté
//   - réponse opaque (CORS no-cors)
//   - réponse avec Cache-Control: no-store
//   - quota dépassé
// Dans tous ces cas, on ignore silencieusement plutôt que de polluer la console.
async function safeCachePut(cacheName, request, response) {
  try {
    const cache = await caches.open(cacheName);
    await cache.put(request, response);
  } catch (e) {
    // Erreur attendue dans certains cas (extension, opaque, etc.) — silencieux
  }
}

// ── Helper : match cache avec ignoreSearch (v3.0 fix #3) ──────────────────
// Sert /plantation_detail.html?id=42 depuis le cache même si seul
// /plantation_detail.html est précaché (sans query string).
async function matchCache(request) {
  // 1. Tentative exacte (avec query string) — privilégiée si disponible
  const exact = await caches.match(request);
  if (exact) return exact;
  // 2. Fallback : ignorer la query string (utile pour les pages HTML précachées)
  return caches.match(request, { ignoreSearch: true });
}

// ── Installation : précacher les assets ───────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => {
      console.log('[SW v3.0] Précache des assets statiques');
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
            console.log('[SW v3.0] Suppression ancien cache:', k);
            return caches.delete(k);
          })
      )
    ).then(() => {
      console.log('[SW v3.0] Activé — contrôle de tous les clients');
      return self.clients.claim();  // prendre le contrôle immédiatement
    })
  );
});

// ── Fetch : intercepter toutes les requêtes ───────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // v3.0 fix #1 : ignorer les schemes non-HTTP (chrome-extension, data, blob, etc.)
  // Le SW ne peut rien faire d'utile avec ces requêtes et cache.put plante dessus.
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    return;
  }

  if (LOCAL_API_ORIGINS.has(url.origin)) {
    event.respondWith(fetch(request));
    return;
  }

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
    // Pages : requetes de navigation / documents HTML — Y COMPRIS les URLs
    // "propres" sans extension .html (Netlify sert /owner, /producers, /direction
    // sans .html). Sans ceci, ces URLs tombaient en Cache First et restaient
    // figees apres un deploiement. On force Network First pour tout document.
    const isDocument = request.mode === 'navigate'
      || request.destination === 'document'
      || (request.headers.get('accept') || '').includes('text/html');
    const isAppAsset = NETWORK_FIRST_PATTERNS.some(p => p.test(url.pathname));
    if (isDocument || isAppAsset) {
      // Stale-While-Revalidate : on sert IMMÉDIATEMENT la page précachée (zéro
      // page blanche à la navigation entre menus), puis on rafraîchit le cache en
      // arrière-plan pour la visite suivante. Avant, on faisait Network First
      // (await fetch avant tout rendu) → ~1 s de blanc à chaque changement de menu.
      // La fraîcheur après déploiement reste garantie par le bump de CACHE_VERSION
      // (nouveau SW → réinstall → précache neuf → ancien cache supprimé).
      event.respondWith(staleWhileRevalidate(request, event));
      return;
    }
    // Autres assets locaux (images, manifest, icons) → Cache First
    event.respondWith(cacheFirstStatic(request));
    return;
  }

  // 3. Tuiles de fond de carte (satellite Esri / CARTO) → Network First.
  //    Esri renvoie parfois une fausse tuile grise « Map data not yet available »
  //    (transitoire ou zone non couverte). En cache-first, cette tuile grise
  //    restait figée par parcelle. En network-first, on retente toujours le
  //    réseau (image réelle dès qu'Esri l'a) ; le cache ne sert qu'en secours
  //    hors ligne (terrain).
  if (MAP_TILE_HOSTS.some(h => url.hostname.endsWith(h))) {
    event.respondWith(networkFirstStatic(request));
    return;
  }

  // 4. CDN externes (Leaflet, Chart.js, Google Fonts) → Cache First
  event.respondWith(cacheFirstStatic(request));
});

// ── Network First (HTML + JS applicatif) ─────────────────────────────────
// Tente toujours le réseau en premier.
// Si hors ligne → fallback sur le cache (avec ignoreSearch pour les pages avec query).
// Met à jour le cache à chaque réponse réseau réussie.
async function networkFirstStatic(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      // v3.0 fix #2 : safeCachePut au lieu de cache.put direct
      safeCachePut(STATIC_CACHE, request, response.clone());
    }
    return response;
  } catch {
    // Hors ligne : fallback sur le cache, avec ignoreSearch pour matcher les
    // pages précachées sans query string (ex: /plantation_detail.html?id=6)
    const cached = await matchCache(request);
    if (cached) return cached;
    if (request.headers.get('accept')?.includes('text/html')) {
      const offlinePage = await caches.match('/offline.html');
      if (offlinePage) return offlinePage;
    }
    return new Response('Hors ligne', { status: 503 });
  }
}

// ── Stale-While-Revalidate (pages HTML + JS applicatif) ──────────────────
// Sert la version en cache IMMÉDIATEMENT (aucune page blanche à la navigation),
// puis rafraîchit le cache en arrière-plan pour la visite suivante. La fraîcheur
// après déploiement est assurée par le bump de CACHE_VERSION (réinstall → précache
// neuf, ancien cache purgé à l'activation) ET par cette revalidation à chaque visite.
// Hors ligne : on garde le cache ; à défaut, la page offline.
async function staleWhileRevalidate(request, event) {
  const cached = await matchCache(request);
  const networkPromise = fetch(request)
    .then((response) => {
      if (response && response.ok) {
        safeCachePut(STATIC_CACHE, request, response.clone());
      }
      return response;
    })
    .catch(() => null);

  if (cached) {
    // On maintient le SW en vie le temps de la revalidation, sans bloquer le rendu.
    if (event && event.waitUntil) event.waitUntil(networkPromise);
    return cached;
  }

  // Pas en cache (1re visite / page non précachée) → réseau, avec repli hors ligne.
  const network = await networkPromise;
  if (network) return network;
  if (request.headers.get('accept')?.includes('text/html')) {
    const offlinePage = await caches.match('/offline.html');
    if (offlinePage) return offlinePage;
  }
  return new Response('Hors ligne', { status: 503 });
}

// ── Cache First (CDN + assets immuables) ─────────────────────────────────
// Sert depuis le cache si disponible.
// Télécharge et met en cache si absent.
async function cacheFirstStatic(request) {
  const cached = await matchCache(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      // v3.0 fix #2 : safeCachePut
      safeCachePut(STATIC_CACHE, request, response.clone());
    }
    return response;
  } catch {
    if (request.headers.get('accept')?.includes('text/html')) {
      const offlinePage = await caches.match('/offline.html');
      if (offlinePage) return offlinePage;
    }
    return new Response('Hors ligne', { status: 503 });
  }
}

// ── Network First API (données terrain offline) ───────────────────────────
async function networkFirstAPI(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      // v3.0 fix #2 : safeCachePut
      safeCachePut(API_CACHE, request, response.clone());
    }
    return response;
  } catch {
    const cached = await matchCache(request);
    if (cached) {
      console.log('[SW v3.0] Offline — données cache:', request.url);
      return cached;
    }
    return new Response(
      JSON.stringify({ error: 'Données non disponibles hors ligne.' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}

// ── Background Sync : rejouer la file d'écritures même APP FERMÉE ──────────────
// Déclenché par le navigateur (Chromium) au retour du réseau, après que la page a
// appelé registration.sync.register('avp-sync-queue'). On lit directement la même
// base IndexedDB que avp-offline.js et on rejoue les écritures — mais UNIQUEMENT
// celles du compte dont le jeton+scope ont été stockés (sécurité multi-tenant sur
// appareil partagé). Le jeton d'accès dure ~2 h : au-delà, l'écriture reste en file
// et sera renvoyée à la réouverture de l'app (aucune perte).
const OFFLINE_DB_NAME = 'avp_offline_db';
const OFFLINE_DB_VERSION = 1;

function idbOpen() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(OFFLINE_DB_NAME, OFFLINE_DB_VERSION);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
function idbReq(r) {
  return new Promise((resolve, reject) => { r.onsuccess = () => resolve(r.result); r.onerror = () => reject(r.error); });
}
async function idbGetAll(db, storeName) {
  const store = db.transaction(storeName, 'readonly').objectStore(storeName);
  return idbReq(store.getAll());
}
async function idbGet(db, storeName, key) {
  const store = db.transaction(storeName, 'readonly').objectStore(storeName);
  return idbReq(store.get(key));
}
async function idbPut(db, storeName, value) {
  const store = db.transaction(storeName, 'readwrite').objectStore(storeName);
  return idbReq(store.put(value));
}
async function idbDelete(db, storeName, key) {
  const store = db.transaction(storeName, 'readwrite').objectStore(storeName);
  return idbReq(store.delete(key));
}

async function replayQueue() {
  let db;
  try { db = await idbOpen(); } catch (e) { return; }

  let scopeEntry, tokenEntry;
  try {
    scopeEntry = await idbGet(db, 'meta', 'auth_scope');
    tokenEntry = await idbGet(db, 'meta', 'auth_token');
  } catch (e) { return; }
  const scope = scopeEntry && scopeEntry.value;
  const token = tokenEntry && tokenEntry.value;
  if (!scope) return;   // aucun compte connecté : on ne rejoue rien (sécurité)

  let queue;
  try { queue = await idbGetAll(db, 'queue_writes'); } catch (e) { return; }
  // On ne rejoue QUE les écritures du compte courant (owner === scope stocké).
  const pending = (queue || []).filter(e =>
    (e.status === 'pending' || e.status === 'error') && e.owner === scope);
  if (pending.length === 0) return;

  let synced = 0;
  for (const entry of pending) {
    try {
      const op_id = entry.op_id || ('sw-' + (self.crypto && crypto.randomUUID ? crypto.randomUUID() : entry.local_id));
      if (!entry.op_id) { entry.op_id = op_id; try { await idbPut(db, 'queue_writes', entry); } catch (e) {} }
      const url = /^https?:/i.test(entry.endpoint) ? entry.endpoint : (API_ORIGIN + entry.endpoint);
      const res = await fetch(url, {
        method: entry.method,
        headers: Object.assign(
          { 'Content-Type': 'application/json', 'Idempotency-Key': op_id },
          token ? { 'Authorization': 'Bearer ' + token } : {}
        ),
        body: entry.body ? JSON.stringify(entry.body) : undefined,
      });
      if (!res || !res.ok) throw new Error('HTTP ' + (res ? res.status : 'none'));
      await idbDelete(db, 'queue_writes', entry.local_id);
      synced++;
    } catch (err) {
      entry.status = 'error';
      entry.error_message = (err && err.message) || String(err);
      entry.attempts = (entry.attempts || 0) + 1;
      try { await idbPut(db, 'queue_writes', entry); } catch (e) {}
    }
  }

  // Prévenir les pages ouvertes pour rafraîchir la pastille « à envoyer ».
  try {
    const clis = await self.clients.matchAll({ includeUncontrolled: true });
    clis.forEach(c => c.postMessage({ type: 'avp-queue-synced', synced }));
  } catch (e) { /* ignore */ }
}

self.addEventListener('sync', event => {
  if (event.tag === 'avp-sync-queue') {
    event.waitUntil(replayQueue());
  }
});
