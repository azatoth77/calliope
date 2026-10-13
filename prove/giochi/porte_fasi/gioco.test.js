const { test } = require("node:test");
const assert = require("node:assert");

test("toccando una porta si vede cosa c'è dietro, poi tocca all'altro", async () => {
  const g = await apriGioco({ seme: 3 });
  await g.tocca("2 giocatori");
  assert.strictEqual(g.stato().fase, "turno");
  await g.tocca("Porta 1");
  assert.match(g.testo(), /Dietro la porta 1/);
  assert.strictEqual(g.stato().fase, "esito");
  await g.avanza(4500);
  const s = g.stato();
  assert.strictEqual(s.tocca, "Giocatore 2");
  assert.deepStrictEqual(s.comandi.porta, [2, 3, 4]);
  await g.comando("porta", 3);
  assert.strictEqual(g.stato().fase, "esito");
});
