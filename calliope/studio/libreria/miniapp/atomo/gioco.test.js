const { test } = require("node:test");
const assert = require("node:assert");
// I comandi attivi dell'istantanea (un elenco o un oggetto con i nomi)
const ha = (g, k) => { const c = g.stato().comandi; return Array.isArray(c) ? c.includes(k) : Object.prototype.hasOwnProperty.call(c || {}, k); };

test("dall'idrogeno al sodio, e ogni pagina sta nel palco", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  assert.deepStrictEqual(g.palco(), []);
  assert.match(g.testo(), /Idrogeno \(H\)/);
  assert.match(g.testo(), /1 elettrone: 1 nel primo livello/);
  for (let i = 0; i < 10; i++) await g.tocca("Un protone in più");
  assert.match(g.testo(), /Sodio \(Na\)/);
  assert.match(g.testo(), /11 protoni e 12 neutroni/);
  assert.match(g.testo(), /2 nel primo livello, 8 nel secondo livello, 1 nel terzo livello/);
  assert.deepStrictEqual(g.palco(), []);
  await g.tocca("Un protone in meno");
  assert.match(g.testo(), /Neon \(Ne\)/);
  await g.tocca("Ho finito");
  assert.match(g.testo(), /Hai visto 11 elementi diversi/);
  assert.deepStrictEqual(g.palco(), []);
});

test("il calcio è l'ultimo: niente protone in più; l'idrogeno il primo", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  assert.ok(!ha(g, "meno"));
  for (let i = 0; i < 19; i++) await g.comando("piu");
  assert.match(g.testo(), /Calcio \(Ca\)/);
  assert.match(g.testo(), /2 nel primo livello, 8 nel secondo livello, 8 nel terzo livello, 2 nel quarto livello/);
  assert.ok(!ha(g, "piu"));
  assert.deepStrictEqual(g.palco(), []);
});
