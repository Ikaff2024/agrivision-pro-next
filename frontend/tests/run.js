/* Runner sans dépendance : exécute chaque *.test.js dans un process isolé et
 * agrège les codes de sortie. `node tests/run.js` (ou `npm test`). */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const dir = __dirname;
const tests = fs.readdirSync(dir).filter(f => f.endsWith('.test.js')).sort();
let failed = 0;

for (const t of tests) {
  console.log('\n===== ' + t + ' =====');
  const res = spawnSync(process.execPath, [path.join(dir, t)], { stdio: 'inherit' });
  if (res.status !== 0) failed++;
}

console.log('\n=========================================');
console.log(failed === 0
  ? `TOUS LES TESTS PASSENT (${tests.length} fichier(s)).`
  : `${failed}/${tests.length} fichier(s) de test EN ECHEC.`);
process.exit(failed ? 1 : 0);
