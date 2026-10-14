const { test } = require("node:test");
const assert = require("node:assert");

test("ogni pagina sta nel palco, nei due orientamenti", async () => {
  const g = await apriGioco({ seme: 2 });
  const viste = [];
  const guarda = () => { viste.push(g.stato().fase); assert.deepStrictEqual(g.palco(), []); };
  guarda();
  await g.tocca("2 giocatori"); guarda();
  await g.tocca("Parti"); guarda();
  await g.tocca("Rosso"); guarda();
  await g.avanza(4500); guarda();
  await g.tocca("Casella 7"); guarda();
  await g.tocca("Prosegui"); guarda();
  await g.tocca("Vediamo"); guarda();
  assert.match(g.testo(), /Area libera di \d+×\d+/);
  await g.tocca("Fine partita"); guarda();
  assert.deepStrictEqual(viste, ["preparazione", "benvenuto", "domanda", "esito", "tabellone",
                                 "annuncio", "punti_parziali", "libera", "fine"]);
});
