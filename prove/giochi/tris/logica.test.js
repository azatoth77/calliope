const test = require("node:test");
const assert = require("node:assert");
const { GIOCO, vincitore, mossaComputer } = require("./logica.js");

test("tre in riga vince", () => {
  assert.strictEqual(vincitore(["X", "X", "X", "", "", "", "", "", ""]), "X");
});

test("in due la casella va a chi tocca, poi il segno cambia", () => {
  const r = GIOCO.mosse.turno.casella(GIOCO.nuovaPartita({ giocatori: 2 }), { valore: 5 });
  assert.strictEqual(r.dati.celle[4], "X");
  assert.strictEqual(r.dati.segno, "O");
});

test("il computer blocca", () => {
  assert.strictEqual(mossaComputer(["X", "X", "", "", "O", "", "", "", ""], "O"), 2);
});

test("da solo il computer risponde subito", () => {
  const r = GIOCO.mosse.turno.casella(GIOCO.nuovaPartita({ giocatori: 1 }), { valore: 1 });
  assert.strictEqual(r.dati.celle.filter(Boolean).length, 2);
});
