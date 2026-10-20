const { test } = require("node:test");
const assert = require("node:assert");
const { nuovaPartita, mossa, vincitore, pareggio, aChiTocca } = require("./tris.js");

function gioca(...caselle) {
  return caselle.reduce((s, n) => mossa(s, n), nuovaPartita());
}

test("comincia X, poi O", () => {
  assert.strictEqual(aChiTocca(nuovaPartita()), "X");
  assert.strictEqual(aChiTocca(gioca(5)), "O");
});

test("tre in fila vince", () => {
  assert.strictEqual(vincitore(gioca(1, 4, 2, 5, 3)), "X");
});

test("la casella occupata è rifiutata", () => {
  assert.throws(() => gioca(5, 5));
});

test("griglia piena senza tre in fila: pareggio", () => {
  assert.strictEqual(pareggio(gioca(1, 2, 3, 5, 4, 6, 8, 7, 9)), true);
});
