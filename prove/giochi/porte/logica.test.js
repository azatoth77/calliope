const test = require("node:test");
const assert = require("node:assert");
const { nuovaPartita, apri, comandiAdesso } = require("./logica.js");

test("aprire una porta toglie il suo comando", () => {
  const s = apri(nuovaPartita("tre"), "due");
  assert.deepStrictEqual(comandiAdesso(s), ["uno", "tre", "ricomincia"]);
});

test("trovato il premio resta solo ricomincia", () => {
  assert.deepStrictEqual(comandiAdesso(apri(nuovaPartita("tre"), "tre")), ["ricomincia"]);
});
