/* Test de non-régression — file d'écritures hors-ligne & cloisonnement multi-tenant.
 *
 * Charge le VRAI frontend/avp-offline.js dans un mock IndexedDB en mémoire et
 * vérifie que :
 *   [1] une écriture hors-ligne est mise en file (queued),
 *   [2] une écriture en ligne part directement au réseau,
 *   [3] la synchro ne prend QUE les écritures du compte courant (appareil partagé),
 *   [4] chaque compte envoie ensuite ses propres saisies, puis la file se vide.
 *
 * Aucune dépendance externe : `node tests/offline_queue.test.js`.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

// ── Mock IndexedDB minimal (suffisant pour avp-offline.js) ──────────────────
function makeIDB() {
  const dbs = {};
  function reqOf(fn) {
    const r = {};
    setTimeout(() => {
      try { r.result = fn(); if (r.onsuccess) r.onsuccess({ target: r }); }
      catch (e) { r.error = e; if (r.onerror) r.onerror({ target: r }); }
    }, 0);
    return r;
  }
  function Store(keyPath) { this.keyPath = keyPath; this.data = new Map(); this.indexes = {}; }
  Store.prototype.createIndex = function (n) { this.indexes[n] = true; };
  Store.prototype.get = function (k) { const s = this; return reqOf(() => s.data.get(k)); };
  Store.prototype.getAll = function () { const s = this; return reqOf(() => [...s.data.values()]); };
  Store.prototype.put = function (v) { const s = this; return reqOf(() => { s.data.set(v[s.keyPath], v); return v[s.keyPath]; }); };
  Store.prototype.add = function (v) { const s = this; return reqOf(() => { s.data.set(v[s.keyPath], v); return v[s.keyPath]; }); };
  Store.prototype.delete = function (k) { const s = this; return reqOf(() => { s.data.delete(k); }); };
  Store.prototype.clear = function () { const s = this; return reqOf(() => { s.data.clear(); }); };
  Store.prototype.count = function () { const s = this; return reqOf(() => s.data.size); };
  function DB() { this.stores = {}; this.objectStoreNames = { contains: (n) => n in this.stores }; }
  DB.prototype.createObjectStore = function (n, o) { const st = new Store(o.keyPath); this.stores[n] = st; return st; };
  DB.prototype.transaction = function (n) { const self = this; return { objectStore: (nm) => self.stores[nm] }; };
  return {
    open(name) {
      const req = {};
      setTimeout(() => {
        let db = dbs[name];
        const isNew = !db;
        if (isNew) db = dbs[name] = new DB();
        if (isNew && req.onupgradeneeded) req.onupgradeneeded({ target: { result: db } });
        req.result = db;
        if (req.onsuccess) req.onsuccess({ target: { result: db } });
      }, 0);
      return req;
    },
  };
}

// ── Faux environnement navigateur ───────────────────────────────────────────
const listeners = {};
const win = {
  addEventListener: (t, f) => { (listeners[t] = listeners[t] || []).push(f); },
  dispatchEvent: (e) => { (listeners[e.type] || []).forEach(f => f(e)); },
};
win.CustomEvent = function (type, o) { this.type = type; this.detail = o && o.detail; };
const navigatorMock = { onLine: true };
let currentUser = { coop_id: 1, email: 'a@coop1' };

let fetchCalls = [];
function fetchMock(url, opts) {
  fetchCalls.push({ url, opts });
  if (!navigatorMock.onLine) return Promise.reject(new Error('network down'));
  return Promise.resolve({ ok: true, status: 200, json: async () => ({ ok: true }) });
}

const sandbox = {
  window: win, navigator: navigatorMock, indexedDB: makeIDB(),
  console, setTimeout, clearTimeout,
  crypto: { randomUUID: () => 'uuid-' + Math.random().toString(16).slice(2) },
  CustomEvent: win.CustomEvent,
};
sandbox.window.getCurrentUser = () => currentUser;
sandbox.window.authFetch = fetchMock;
sandbox.global = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.resolve(__dirname, '..', 'avp-offline.js'), 'utf8'), sandbox);
const AVP = sandbox.window.AVPOffline;

let pass = 0, fail = 0;
function assert(cond, msg) { if (cond) { pass++; console.log('  OK  ' + msg); } else { fail++; console.log('  XX  ECHEC: ' + msg); } }

(async () => {
  await AVP.isReady;

  console.log('\n[1] Ecriture HORS-LIGNE -> mise en file');
  navigatorMock.onLine = false;
  const r1 = await AVP.offlineFetch('/purchases', { method: 'POST', body: JSON.stringify({ x: 1 }) }, 'Achat', { module: 'achats' });
  assert(r1.queued === true, 'offlineFetch renvoie queued=true hors-ligne');
  assert((await AVP.getQueueStats()).pending === 1, '1 ecriture en attente dans la file');

  console.log('\n[2] Ecriture EN LIGNE -> envoi direct');
  navigatorMock.onLine = true;
  fetchCalls = [];
  const r2 = await AVP.offlineFetch('/children', { method: 'POST', body: JSON.stringify({ y: 2 }) }, 'Enfant', { module: 'children' });
  assert(r2.queued === false, 'offlineFetch renvoie queued=false en ligne');
  assert(fetchCalls.some(c => String(c.url).includes('/children')), 'la requete /children part au reseau');

  console.log('\n[3] Cloisonnement multi-tenant : la synchro ne prend QUE le compte courant');
  navigatorMock.onLine = false;
  currentUser = { coop_id: 1, email: 'a@coop1' };
  await AVP.enqueueWrite('POST', '/complaints', { a: 1 }, 'Signalement A', {});
  currentUser = { coop_id: 2, email: 'b@coop2' };   // changement de compte (appareil partage)
  await AVP.enqueueWrite('POST', '/complaints', { b: 1 }, 'Signalement B', {});
  assert((await AVP.getQueueStats()).pending === 1, 'Compte B ne voit QUE sa propre ecriture en attente');

  navigatorMock.onLine = true;
  fetchCalls = [];
  assert((await AVP.syncQueue()).synced === 1, 'Compte B synchronise UNIQUEMENT sa saisie (1)');
  currentUser = { coop_id: 1, email: 'a@coop1' };
  assert((await AVP.getQueueStats()).pending >= 2, 'Les ecritures du compte A restent en attente');

  console.log('\n[4] Compte A synchronise ses propres ecritures');
  assert((await AVP.syncQueue()).synced >= 2, 'Compte A envoie ses saisies');
  assert((await AVP.getQueueStats()).pending === 0, 'File du compte A videe apres synchro');

  console.log(`\n  => ${pass} OK, ${fail} echec(s)`);
  process.exit(fail ? 1 : 0);
})();
