const { test } = require("node:test");
const assert = require("node:assert");
// I comandi attivi dell'istantanea (un elenco o un oggetto con i nomi)
const ha = (g, k) => { const c = g.stato().comandi; return Array.isArray(c) ? c.includes(k) : Object.prototype.hasOwnProperty.call(c || {}, k); };

test("l'esempio di 13 passo passo, poi un altro esempio", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  assert.deepStrictEqual(g.palco(), []);
  assert.match(g.testo(), /13 : 2 = 6, resto 1/);
  for (let i = 0; i < 4; i++) await g.tocca("Passo dopo");
  assert.match(g.testo(), /13 in binario è 1101/);
  assert.match(g.testo(), /1101 = 8 \+ 4 \+ 1 = 13/);
  assert.ok(!ha(g, "passo"));
  assert.deepStrictEqual(g.palco(), []);
  await g.tocca("Un altro esempio");
  assert.match(g.testo(), /22 : 2 = 11, resto 0/);
  await g.tocca("Ho finito");
  assert.match(g.testo(), /Hai visto 2 esempi/);
  assert.deepStrictEqual(g.palco(), []);
});

test("il quiz: giusto, sbagliato con il perché, fino alla fine", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  await g.tocca("Alle domande");
  assert.match(g.testo(), /Quanto vale 1011 in decimale\?/);
  assert.deepStrictEqual(g.palco(), []);
  await g.comando("risposta", "b");
  assert.match(g.testo(), /Giusto! 1011 = 8 \+ 2 \+ 1 = 11/);
  assert.deepStrictEqual(g.palco(), []);
  await g.comando("avanti");
  assert.match(g.testo(), /Come si scrive 13 in binario\?/);
  await g.comando("risposta", "a");
  assert.match(g.testo(), /Sbagliato: 1101 = 8 \+ 4 \+ 1 = 13/);
  assert.match(g.testo(), /resti dall'alto/);
  assert.deepStrictEqual(g.palco(), []);
  await g.comando("avanti");
  await g.comando("risposta", "c");
  assert.match(g.testo(), /Hai dimenticato il peso 4/);
  await g.comando("avanti");
  for (const r of ["b", "c", "a"]) { await g.comando("risposta", r); await g.comando("avanti"); }
  assert.strictEqual(g.stato().fase, "fine");
  assert.deepStrictEqual(g.palco(), []);
});
