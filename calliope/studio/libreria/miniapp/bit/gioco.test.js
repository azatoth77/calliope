const { test } = require("node:test");
const assert = require("node:assert");
// I comandi attivi dell'istantanea (un elenco o un oggetto con i nomi)
const ha = (g, k) => { const c = g.stato().comandi; return Array.isArray(c) ? c.includes(k) : Object.prototype.hasOwnProperty.call(c || {}, k); };

test("45 = 32 + 8 + 4 + 1, poi spegni tutto e ho finito", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  assert.deepStrictEqual(g.palco(), []);
  assert.match(g.testo(), /00000000 = 0/);
  assert.ok(!ha(g, "spegni"));
  for (const n of [5, 3, 2, 0]) await g.comando("bit", n);
  assert.match(g.testo(), /00101101 = 32 \+ 8 \+ 4 \+ 1 = 45/);
  assert.deepStrictEqual(g.palco(), []);
  await g.comando("bit", 3);
  assert.match(g.testo(), /00100101 = 32 \+ 4 \+ 1 = 37/);
  assert.ok(ha(g, "spegni"));
  await g.tocca("Spegni tutto");
  assert.match(g.testo(), /00000000 = 0/);
  await g.tocca("Ho finito");
  // 0, 32, 40, 44, 45, 37
  assert.match(g.testo(), /Hai formato 6 numeri diversi/);
  assert.deepStrictEqual(g.palco(), []);
});

test("tutti accesi fanno 255, un bit solo il suo peso", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  await g.comando("bit", 7);
  assert.match(g.testo(), /10000000 = 128/);
  for (let n = 0; n < 7; n++) await g.comando("bit", n);
  assert.match(g.testo(), /11111111 = 128 \+ 64 \+ 32 \+ 16 \+ 8 \+ 4 \+ 2 \+ 1 = 255/);
  assert.ok(!ha(g, "accendi"));
  assert.deepStrictEqual(g.palco(), []);
  await g.tocca("Spegni tutto");
  await g.tocca("Accendi tutto");
  assert.match(g.testo(), /11111111 = .* = 255/);
});
