const { test } = require("node:test");
const assert = require("node:assert");
const { GIOCO, chiuse } = require("./logica.js");

test("una porta aperta non è più chiusa", () => {
  const d = GIOCO.nuovaPartita({ giocatori: 2 });
  const r = GIOCO.mosse.turno.porta(d, { valore: 2 });
  assert.deepStrictEqual(chiuse(r.dati), [1, 3, 4]);
});
