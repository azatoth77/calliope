const { test } = require("node:test");
const assert = require("node:assert");
// I comandi attivi dell'istantanea (un elenco o un oggetto con i nomi)
const ha = (g, k) => { const c = g.stato().comandi; return Array.isArray(c) ? c.includes(k) : Object.prototype.hasOwnProperty.call(c || {}, k); };
const punti = (g) => g.stato().giocatori[0].punti;

test("si esplorano gli oggetti e poi tutto il quiz", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  assert.deepStrictEqual(g.palco(), []);
  assert.match(g.testo(), /Scegli un oggetto/);
  await g.tocca("Sughero");
  assert.match(g.testo(), /Tappo di sughero/);
  assert.match(g.testo(), /d = 6 : 25 = 0,24 g\/cm³, meno di 1: galleggia/);
  assert.deepStrictEqual(g.palco(), []);
  await g.comando("oggetto", "ferro");
  assert.match(g.testo(), /d = 118 : 15 = 7,87 g\/cm³, più di 1: affonda/);
  await g.comando("oggetto", "pvc");
  assert.match(g.testo(), /d = 69 : 50 = 1,38 g\/cm³, più di 1: affonda/);
  await g.tocca("Al quiz");
  assert.match(g.testo(), /Domanda 1 di 5/);
  assert.match(g.testo(), /Cera d'api: m = 48 g, V = 50 cm³/);
  assert.deepStrictEqual(g.palco(), []);
  await g.tocca("Galleggia");
  assert.match(g.testo(), /Giusto: d = 48 : 50 = 0,96 g\/cm³, meno di 1: galleggia/);
  assert.deepStrictEqual(g.palco(), []);
  await g.comando("avanti");
  await g.comando("galleggia");        // il vetro affonda
  assert.match(g.testo(), /No: d = 125 : 50 = 2,50 g\/cm³, più di 1: affonda/);
  await g.comando("avanti");
  await g.comando("galleggia");
  await g.comando("avanti");
  await g.comando("galleggia");
  await g.comando("avanti");
  await g.comando("affonda");          // la gomma
  assert.match(g.testo(), /d = 58 : 50 = 1,16 g\/cm³/);
  assert.strictEqual(punti(g), 4);
  await g.comando("avanti");
  assert.strictEqual(g.stato().fase, "fine");
  assert.deepStrictEqual(g.palco(), []);
});

test("ho finito a metà quiz", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  await g.comando("quiz");
  assert.ok(ha(g, "finito") && ha(g, "affonda"));
  await g.comando("affonda");
  await g.comando("avanti");
  await g.tocca("Ho finito");
  assert.match(g.testo(), /Hai risposto giusto a 0 su 1/);
  await g.comando("avanti");
  assert.strictEqual(g.stato().fase, "fine");
});
