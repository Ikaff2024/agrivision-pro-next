/* ──────────────────────────────────────────────────────────────────────
 * avp-offline.js — Module IndexedDB centralisé pour le mode hors ligne
 * Sprint Offline V1.6 — Phase 1
 *
 * Fournit :
 *  - Cache local des reponses GET (Stale-While-Revalidate)
 *  - Queue de synchronisation pour les ecritures (POST/PUT/DELETE)
 *  - Compression automatique des images avant stockage
 *
 * API publique : window.AVPOffline (voir bas du fichier)
 *
 * Aucune dependance externe. IndexedDB natif uniquement.
 * Sentinel chargee en premier dans toutes les pages, AVANT auth.js.
 * ──────────────────────────────────────────────────────────────────────
 */

(function () {
  'use strict';

  // ─── Configuration ────────────────────────────────────────────────
  const DB_NAME = 'avp_offline_db';
  const DB_VERSION = 1;

  const STORES = {
    CACHE_GET: 'cache_get',           // Cache des lectures (clé = endpoint URL)
    QUEUE_WRITES: 'queue_writes',      // File d'attente des écritures
    PHOTOS: 'photos',                  // Photos compressées (Blob)
    META: 'meta',                      // Metadonnees (last_sync, version, etc.)
  };

  const SWR_MAX_AGE_MS = 5 * 60 * 1000;  // Cache valide 5 minutes (sinon revalidate forcee)

  // ─── Etat interne ─────────────────────────────────────────────────
  let dbInstance = null;
  let dbReadyPromise = null;

  // ─── Helpers IndexedDB de bas niveau ──────────────────────────────

  function openDB() {
    if (dbReadyPromise) return dbReadyPromise;

    dbReadyPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);

      req.onupgradeneeded = function (event) {
        const db = event.target.result;

        if (!db.objectStoreNames.contains(STORES.CACHE_GET)) {
          const store = db.createObjectStore(STORES.CACHE_GET, { keyPath: 'endpoint' });
          store.createIndex('cached_at', 'cached_at', { unique: false });
        }

        if (!db.objectStoreNames.contains(STORES.QUEUE_WRITES)) {
          const store = db.createObjectStore(STORES.QUEUE_WRITES, { keyPath: 'local_id' });
          store.createIndex('status', 'status', { unique: false });
          store.createIndex('created_at', 'created_at', { unique: false });
        }

        if (!db.objectStoreNames.contains(STORES.PHOTOS)) {
          db.createObjectStore(STORES.PHOTOS, { keyPath: 'photo_id' });
        }

        if (!db.objectStoreNames.contains(STORES.META)) {
          db.createObjectStore(STORES.META, { keyPath: 'key' });
        }
      };

      req.onsuccess = function (event) {
        dbInstance = event.target.result;
        resolve(dbInstance);
      };

      req.onerror = function (event) {
        console.error('[AVPOffline] Echec ouverture IndexedDB:', event.target.error);
        reject(event.target.error);
      };
    });

    return dbReadyPromise;
  }

  function tx(storeName, mode) {
    return openDB().then((db) => db.transaction(storeName, mode).objectStore(storeName));
  }

  function reqAsPromise(req) {
    return new Promise((resolve, reject) => {
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  // ─── Cache GET (Stale While Revalidate) ───────────────────────────

  // CLOISONNEMENT MULTI-TENANT : la clé de cache est préfixée par le COMPTE
  // connecté (coopérative + email). Sans ce préfixe, sur un appareil partagé, le
  // cache de « /plantations » de la coop A s'affichait quelques secondes pour la
  // coop B avant le rafraîchissement réseau. Le préfixe garantit qu'un compte ne
  // lit jamais le cache d'un autre. Les entrées d'un autre compte deviennent
  // simplement des « miss » (re-fetch), aucune fuite.
  function _scope() {
    try {
      if (typeof window.getCurrentUser === 'function') {
        const u = window.getCurrentUser();
        if (u) return 'c' + (u.coop_id == null ? 'x' : u.coop_id) + ':' + (u.email || '');
      }
    } catch (e) { /* ignore */ }
    return 'anon';
  }
  function _nsKey(endpoint) { return _scope() + '§' + endpoint; }

  async function cacheGet(endpoint) {
    try {
      const store = await tx(STORES.CACHE_GET, 'readonly');
      const entry = await reqAsPromise(store.get(_nsKey(endpoint)));
      return entry ? entry.data : null;
    } catch (err) {
      console.warn('[AVPOffline] cacheGet failed:', err);
      return null;
    }
  }

  async function cacheSet(endpoint, data) {
    try {
      const store = await tx(STORES.CACHE_GET, 'readwrite');
      await reqAsPromise(store.put({
        endpoint: _nsKey(endpoint),
        data: data,
        cached_at: Date.now(),
      }));
      return true;
    } catch (err) {
      console.warn('[AVPOffline] cacheSet failed:', err);
      return false;
    }
  }

  async function cacheClear() {
    const store = await tx(STORES.CACHE_GET, 'readwrite');
    return reqAsPromise(store.clear());
  }

  /**
   * Stale While Revalidate fetch.
   * - Renvoie immediatement le cache si dispo (donnees affichees instantanement)
   * - Lance en parallele un fetch reseau qui met a jour le cache
   * - Si pas de cache et offline, throw OfflineError
   *
   * Usage typique :
   *   const { cached, fresh } = await AVPOffline.swrFetch('/plantations');
   *   render(cached);                 // affichage instantane
   *   fresh.then(data => render(data)); // refresh quand le serveur repond
   */
  function swrFetch(endpoint, options = {}) {
    options = options || {};

    // 1. Recuperer le cache
    const cachedPromise = cacheGet(endpoint);

    // 2. Lancer le fetch reseau en parallele (peut echouer)
    const freshPromise = (async () => {
      // On prefere passer par window.authFetch si disponible (gestion JWT)
      // sinon fallback sur fetch natif (utile pour les tests unitaires)
      let res;
      if (typeof window.authFetch === 'function') {
        res = await window.authFetch(endpoint, options);
      } else {
        res = await fetch(endpoint, options);
      }

      if (!res || !res.ok) {
        throw new Error(`HTTP ${res ? res.status : 'no response'}`);
      }

      const data = await res.json();
      // Mettre a jour le cache uniquement pour les GET reussis
      if (!options.method || options.method.toUpperCase() === 'GET') {
        await cacheSet(endpoint, data);
      }
      return data;
    })().catch((err) => {
      // En cas d'echec reseau, on swallow ici pour ne pas casser swrFetch.
      // L'appelant peut consulter le state via .catch sur la promesse retournee.
      console.warn(`[AVPOffline] Network fetch failed for ${endpoint}:`, err.message);
      throw err;
    });

    return {
      cached: cachedPromise,
      fresh: freshPromise,
    };
  }

  // ─── Queue des ecritures offline ──────────────────────────────────

  function generateUUID() {
    // UUID v4 simple. Suffisant pour identifier des ecritures locales.
    return 'local_' + 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  /**
   * Ajouter une ecriture (POST/PUT/DELETE) a la queue.
   *
   * @param {string} method   "POST" | "PUT" | "DELETE"
   * @param {string} endpoint Ex: "/plantations/12/diagnostics"
   * @param {object} body     Corps de la requete (sera serialise en JSON)
   * @param {string} label    Description humaine pour l'UI ("Diagnostic Plantation Soubre")
   * @returns {Promise<string>} local_id genere pour cet element
   */
  async function enqueueWrite(method, endpoint, body, label, meta) {
    const local_id = generateUUID();
    const entry = {
      local_id: local_id,
      method: method,
      endpoint: endpoint,
      body: body,
      label: label || endpoint,
      meta: meta || {},
      owner: _scope(),                      // COMPTE createur : on ne synchronisera JAMAIS
                                            // cette ecriture sous un autre compte (appareil partage)
      status: 'pending',                    // pending | syncing | error
      error_message: null,
      created_at: Date.now(),
      attempts: 0,
    };
    const store = await tx(STORES.QUEUE_WRITES, 'readwrite');
    await reqAsPromise(store.add(entry));

    // Notifier l'UI (pour mettre a jour le compteur)
    window.dispatchEvent(new CustomEvent('avp-queue-changed'));

    // Tenter une synchro immediate si on est en ligne (best effort)
    if (navigator.onLine) {
      syncQueue().catch(() => { /* swallow, sera rejoue plus tard */ });
    }

    return local_id;
  }

  async function offlineFetch(endpoint, options = {}, label, meta) {
    const method = (options.method || 'GET').toUpperCase();
    if (method === 'GET') {
      return swrFetch(endpoint, options).fresh;
    }

    let body = options.body || null;
    if (typeof body === 'string') {
      try { body = JSON.parse(body); } catch (_) {}
    }

    try {
      if (!navigator.onLine) throw new Error('offline');
      const fetcher = typeof window.authFetch === 'function' ? window.authFetch : fetch;
      const res = await fetcher(endpoint, options);
      if (res && !res.ok && res.status < 500) {
        return { queued: false, response: res };
      }
      if (!res || !res.ok) {
        throw new Error(`HTTP ${res ? res.status : 'no response'}`);
      }
      return { queued: false, response: res };
    } catch (err) {
      const local_id = await enqueueWrite(method, endpoint, body, label, meta);
      return { queued: true, local_id, error: err.message || String(err) };
    }
  }

  async function getQueue() {
    const store = await tx(STORES.QUEUE_WRITES, 'readonly');
    return reqAsPromise(store.getAll());
  }

  // Une écriture appartient au compte courant si son `owner` correspond, ou si elle
  // est ANTÉRIEURE à cette fonctionnalité (pas d'`owner`) — dans ce cas elle a été
  // créée par l'unique session locale d'alors, on l'adopte.
  function _ownedByMe(entry) {
    return !entry.owner || entry.owner === _scope();
  }

  async function getQueueByEndpoint(prefix) {
    const queue = await getQueue();
    return queue
      .filter((entry) => _ownedByMe(entry) && (!prefix || String(entry.endpoint || '').startsWith(prefix)))
      .sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
  }

  async function getQueueStats() {
    // Compteur cloisonné : on n'affiche que les écritures du compte courant.
    const queue = (await getQueue()).filter(_ownedByMe);
    return {
      pending: queue.filter((e) => e.status === 'pending').length,
      syncing: queue.filter((e) => e.status === 'syncing').length,
      errors: queue.filter((e) => e.status === 'error').length,
      total: queue.length,
    };
  }

  async function updateQueueEntry(local_id, updates) {
    const store = await tx(STORES.QUEUE_WRITES, 'readwrite');
    const entry = await reqAsPromise(store.get(local_id));
    if (!entry) return false;
    Object.assign(entry, updates);
    await reqAsPromise(store.put(entry));
    return true;
  }

  async function deleteQueueEntry(local_id) {
    const store = await tx(STORES.QUEUE_WRITES, 'readwrite');
    return reqAsPromise(store.delete(local_id));
  }

  /**
   * Synchroniser la queue avec le backend.
   * Strategie C2 : skip and continue (les erreurs ne stoppent pas les autres).
   *
   * Cette implementation Phase 1 envoie les requetes UNE PAR UNE via authFetch.
   * En Phase 5, on basculera sur l'endpoint /api/sync/batch pour reduire la latence.
   */
  let syncInProgress = false;

  async function syncQueue() {
    if (syncInProgress) return { skipped: true, reason: 'sync_in_progress' };
    if (!navigator.onLine) return { skipped: true, reason: 'offline' };

    syncInProgress = true;
    try {
      const queue = await getQueue();
      // On ne synchronise QUE les écritures du compte courant : une saisie faite
      // hors-ligne par un autre compte (appareil partagé) reste en attente jusqu'à
      // ce que SON auteur se reconnecte — jamais envoyée sous le mauvais compte.
      const pending = queue.filter((e) => (e.status === 'pending' || e.status === 'error') && _ownedByMe(e));

      if (pending.length === 0) {
        return { synced: 0, errors: 0, skipped: false };
      }

      let synced = 0;
      let errors = 0;

      for (const entry of pending) {
        await updateQueueEntry(entry.local_id, { status: 'syncing' });

        try {
          const fetcher = typeof window.authFetch === 'function' ? window.authFetch : fetch;
          // Sprint P1 : envoyer un Idempotency-Key UUID v4 pour permettre au
          // backend de dedupliquer si la reponse reseau est perdue. Le serveur
          // peut choisir d'honorer ou d'ignorer cet en-tete. Pour les routes
          // qui ne le gerent pas, c'est un no-op cote serveur.
          const op_id = entry.op_id || ('local-' + (crypto.randomUUID ? crypto.randomUUID() : entry.local_id));
          if (!entry.op_id) {
            await updateQueueEntry(entry.local_id, { op_id });
          }
          const res = await fetcher(entry.endpoint, {
            method: entry.method,
            headers: { 'Content-Type': 'application/json', 'Idempotency-Key': op_id },
            body: entry.body ? JSON.stringify(entry.body) : undefined,
          });
          if (!res || !res.ok) {
            throw new Error(`HTTP ${res ? res.status : 'no response'}`);
          }
          // Succes : on supprime de la queue
          await deleteQueueEntry(entry.local_id);
          synced++;
        } catch (err) {
          // Strategie C2 : on garde l'erreur en queue pour correction utilisateur
          await updateQueueEntry(entry.local_id, {
            status: 'error',
            error_message: err.message || String(err),
            attempts: (entry.attempts || 0) + 1,
          });
          errors++;
        }
      }

      window.dispatchEvent(new CustomEvent('avp-queue-changed'));
      return { synced, errors, skipped: false };
    } finally {
      syncInProgress = false;
    }
  }

  // ─── Compression d'images (Photos offline, decision D1) ──────────

  /**
   * Compresse une image (File ou Blob) en JPEG <=800px et qualite ~70%.
   * Renvoie un Blob compresse (~100-200 KB typique).
   */
  async function compressImage(fileOrBlob, maxDim = 800, quality = 0.7) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      const reader = new FileReader();

      reader.onload = function (e) {
        img.onload = function () {
          // Calculer dimensions cibles en preservant le ratio
          let w = img.width;
          let h = img.height;
          if (w > maxDim || h > maxDim) {
            if (w > h) {
              h = Math.round((h * maxDim) / w);
              w = maxDim;
            } else {
              w = Math.round((w * maxDim) / h);
              h = maxDim;
            }
          }

          const canvas = document.createElement('canvas');
          canvas.width = w;
          canvas.height = h;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(img, 0, 0, w, h);

          canvas.toBlob(
            (blob) => {
              if (blob) resolve(blob);
              else reject(new Error('compressImage: toBlob returned null'));
            },
            'image/jpeg',
            quality
          );
        };
        img.onerror = () => reject(new Error('compressImage: image load failed'));
        img.src = e.target.result;
      };
      reader.onerror = () => reject(new Error('compressImage: file read failed'));
      reader.readAsDataURL(fileOrBlob);
    });
  }

  async function savePhoto(photo_id, blob) {
    const store = await tx(STORES.PHOTOS, 'readwrite');
    return reqAsPromise(store.put({ photo_id, blob, saved_at: Date.now() }));
  }

  async function getPhoto(photo_id) {
    const store = await tx(STORES.PHOTOS, 'readonly');
    const entry = await reqAsPromise(store.get(photo_id));
    return entry ? entry.blob : null;
  }

  async function deletePhoto(photo_id) {
    const store = await tx(STORES.PHOTOS, 'readwrite');
    return reqAsPromise(store.delete(photo_id));
  }

  // ─── Stats globales pour debug ─────────────────────────────────────

  async function getStats() {
    const cacheStore = await tx(STORES.CACHE_GET, 'readonly');
    const cacheCount = await reqAsPromise(cacheStore.count());

    const queueStats = await getQueueStats();

    const photosStore = await tx(STORES.PHOTOS, 'readonly');
    const photosCount = await reqAsPromise(photosStore.count());

    return {
      cache_entries: cacheCount,
      queue_pending: queueStats.pending,
      queue_errors: queueStats.errors,
      photos_stored: photosCount,
      online: navigator.onLine,
      db_version: DB_VERSION,
    };
  }

  async function clearAll() {
    if (!confirm('Effacer TOUTES les donnees offline locales ? Cette action est irreversible.')) {
      return false;
    }
    await cacheClear();
    const queueStore = await tx(STORES.QUEUE_WRITES, 'readwrite');
    await reqAsPromise(queueStore.clear());
    const photosStore = await tx(STORES.PHOTOS, 'readwrite');
    await reqAsPromise(photosStore.clear());
    console.log('[AVPOffline] Toutes les donnees offline ont ete effacees');
    window.dispatchEvent(new CustomEvent('avp-queue-changed'));
    return true;
  }

  // ─── Auto-sync au retour en ligne ─────────────────────────────────

  window.addEventListener('online', () => {
    console.log('[AVPOffline] Connexion retablie, synchronisation automatique...');
    syncQueue().then((result) => {
      if (result && !result.skipped && result.synced > 0) {
        console.log(`[AVPOffline] ${result.synced} saisie(s) synchronisee(s)`);
        // Toast utilisateur si helper dispo
        if (typeof window.toast === 'function') {
          window.toast(`${result.synced} saisie(s) envoyee(s) au serveur.`, 'success');
        }
      }
      window.dispatchEvent(new CustomEvent('avp-queue-changed'));
    });
  });

  // ─── Exposition publique ──────────────────────────────────────────

  window.AVPOffline = {
    // Lectures
    swrFetch: swrFetch,
    cacheGet: cacheGet,
    cacheSet: cacheSet,
    cacheClear: cacheClear,

    // Ecritures
    enqueueWrite: enqueueWrite,
    getQueue: getQueue,
    getQueueByEndpoint: getQueueByEndpoint,
    getQueueStats: getQueueStats,
    syncQueue: syncQueue,
    offlineFetch: offlineFetch,

    // Photos
    compressImage: compressImage,
    savePhoto: savePhoto,
    getPhoto: getPhoto,
    deletePhoto: deletePhoto,

    // Utilitaires
    getStats: getStats,
    clearAll: clearAll,
    isReady: openDB(),

    // Constantes (pour debug/inspection)
    _DB_NAME: DB_NAME,
    _DB_VERSION: DB_VERSION,
    _STORES: STORES,
  };

  // Initialisation : on ouvre la DB des le chargement
  openDB().then(() => {
    console.log('[AVPOffline] Module pret. IndexedDB ouverte (' + DB_NAME + ' v' + DB_VERSION + ').');
  }).catch((err) => {
    console.error('[AVPOffline] Echec initialisation:', err);
  });

})();
