const test = require("node:test");
const assert = require("node:assert");
const { GIOCO, chiuse } = require("./logica.js");

test("aprire una porta toglie il suo comando", () => {
  const r = GIOCO.mosse.turno.porta(GIOCO.nuovaPartita(), { valore: 2 });
  assert.deepStrictEqual(chiuse(r.dati), [1, 3]);
  assert.strictEqual(r.esito, undefined);
});

test("trovato il premio la partita finisce", () => {
  const r = GIOCO.mosse.turno.porta(GIOCO.nuovaPartita(), { valore: 3 });
  assert.strictEqual(r.dopo, "fine");
  assert.strictEqual(r.punti, 1);
});
