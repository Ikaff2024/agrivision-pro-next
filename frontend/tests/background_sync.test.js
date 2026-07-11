/* Test de non-régression — Background Sync du Service Worker (frontend/sw.js).
 *
 * Charge le VRAI sw.js et déclenche l'événement 'sync' pour vérifier que
 * replayQueue :
 *   [1] ne rejoue QUE les écritures dont owner === scope stocké (auth_scope),
 *       avec le bon jeton, et laisse celles des autres comptes en file,
 *   [2] ne rejoue RIEN quand aucun compte n'est connecté (scope absent).
 *
 * Aucune dépendance externe : `node tests/background_sync.test.js`.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

function makeIDB() {
  const dbs = {};
  function reqOf(fn) { const r = {}; setTimeout(() => { try { r.result = fn(); r.onsuccess && r.onsuccess({ target: r }); } catch (e) { r.error = e; r.onerror && r.onerror({ target: r }); } }, 0); return r; }
  function Store(keyPath) { this.keyPath = keyPath; this.data = new Map(); }
  Store.prototype.get = function (k) { const s = this; return reqOf(() => s.data.get(k)); };
  Store.prototype.getAll = function () { const s = this; return reqOf(() => [...s.data.values()]); };
  Store.prototype.put = function (v) { const s = this; return reqOf(() => { s.data.set(v[s.keyPath], v); return v[s.keyPath]; }); };
  Store.prototype.delete = function (k) { const s = this; return reqOf(() => { s.data.delete(k); }); };
  function DB() { this.stores = { queue_writes: new Store('local_id'), meta: new Store('key'), cache_get: new Store('endpoint'), photos: new Store('photo_id') }; this.objectStoreNames = { contains: (n) => n in this.stores }; }
  DB.prototype.createObjectStore = function (n, o) { return this.stores[n] || (this.stores[n] = new Store(o.keyPath)); };
  DB.prototype.transaction = function () { const self = this; return { objectStore: (nm) => self.stores[nm] }; };
  const api = { open() { const req = {}; const db = dbs.avp_offline_db || (dbs.avp_offline_db = new DB()); setTimeout(() => { req.result = db; req.onsuccess && req.onsuccess({ target: { result: db } }); }, 0); return req; }, _dbs: dbs };
  return api;
}

const idb = makeIDB();
const db = idb._dbs.avp_offline_db || idb.open().result;
// forcer la création du DB de suite
idb.open();

let fetchLog = [];
function fetchMock(url, opts) { fetchLog.push({ url, method: opts.method, auth: (opts.headers || {}).Authorization }); return Promise.resolve({ ok: true, status: 200 }); }

const handlers = {};
const self = {
  addEventListener: (t, f) => { (handlers[t] = handlers[t] || []).push(f); },
  clients: { matchAll: async () => [{ postMessage: () => {} }] },
  crypto: { randomUUID: () => 'sw-uuid' },
  skipWaiting: () => {}, location: { origin: 'https://app' },
};
const sandbox = { self, indexedDB: idb, fetch: fetchMock, console, setTimeout, clearTimeout, URL, caches: { keys: async () => [], match: async () => null }, crypto: self.crypto };
sandbox.global = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.resolve(__dirname, '..', 'sw.js'), 'utf8'), sandbox);

const wait = (ms) => new Promise(r => setTimeout(r, ms));
let pass = 0, fail = 0;
const assert = (c, m) => { if (c) { pass++; console.log('  OK  ' + m); } else { fail++; console.log('  XX  ECHEC: ' + m); } };

function getDB() { return idb._dbs.avp_offline_db; }
async function seed(scope, token, entries) {
  const d = getDB();
  d.stores.queue_writes.data.clear();
  d.stores.meta.data.clear();
  if (scope !== undefined) d.stores.meta.data.set('auth_scope', { key: 'auth_scope', value: scope });
  if (token !== undefined) d.stores.meta.data.set('auth_token', { key: 'auth_token', value: token });
  entries.forEach(e => d.stores.queue_writes.data.set(e.local_id, e));
}
function triggerSync() {
  let done; const p = new Promise(r => done = r);
  handlers['sync'].forEach(h => h({ tag: 'avp-sync-queue', waitUntil: (pr) => Promise.resolve(pr).then(done) }));
  return p;
}

(async () => {
  await wait(10);
  const d = getDB();

  console.log('\n[1] Rejeu cloisonne : seules les ecritures owner === scope stocke partent');
  await seed('c1:a@coop1', 'tokA', [
    { local_id: 'L1', method: 'POST', endpoint: '/purchases', body: { a: 1 }, owner: 'c1:a@coop1', status: 'pending' },
    { local_id: 'L2', method: 'POST', endpoint: '/complaints', body: { b: 1 }, owner: 'c2:b@coop2', status: 'pending' },
  ]);
  fetchLog = [];
  await triggerSync();
  await wait(10);
  assert(fetchLog.length === 1, 'Une seule requete envoyee (compte courant)');
  assert(fetchLog[0] && String(fetchLog[0].url).includes('/purchases'), "C'est /purchases (compte A), pas /complaints (compte B)");
  assert(fetchLog[0] && fetchLog[0].auth === 'Bearer tokA', 'Envoyee avec le jeton du compte stocke');
  assert(d.stores.queue_writes.data.has('L2'), "L'ecriture du compte B reste en file");
  assert(!d.stores.queue_writes.data.has('L1'), "L'ecriture envoyee du compte A est retiree");

  console.log('\n[2] Aucun compte connecte (scope absent) -> le SW ne rejoue RIEN');
  await seed(undefined, undefined, [
    { local_id: 'L3', method: 'POST', endpoint: '/children', body: { c: 1 }, owner: 'c1:a@coop1', status: 'pending' },
  ]);
  fetchLog = [];
  await triggerSync();
  await wait(10);
  assert(fetchLog.length === 0, 'Aucune requete sans scope stocke (securite deconnexion)');
  assert(getDB().stores.queue_writes.data.has('L3'), 'La saisie reste en file');

  console.log(`\n  => ${pass} OK, ${fail} echec(s)`);
  process.exit(fail ? 1 : 0);
})();
