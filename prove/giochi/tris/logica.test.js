const test = require("node:test");
const assert = require("node:assert");
const { nuovaPartita, vincitore, mossa, mossaComputer } = require("./logica.js");

test("tre in riga vince", () => {
  assert.strictEqual(vincitore(["X", "X", "X", "", "", "", "", "", ""]), "X");
});

test("cella occupata non cambia niente", () => {
  const s = mossa(nuovaPartita(), 4);
  assert.strictEqual(mossa(s, 4), s);
});

test("il computer blocca", () => {
  let s = nuovaPartita();
  s = mossa(s, 0); s = mossa(s, 4); s = mossa(s, 1);
  assert.strictEqual(mossaComputer(s), 2);
});

test("pareggio", () => {
  let s = nuovaPartita();
  for (const i of [0, 1, 2, 4, 3, 5, 7, 6, 8]) s = mossa(s, i);
  assert.ok(s.finita);
  assert.strictEqual(s.vincitore, "");
});
