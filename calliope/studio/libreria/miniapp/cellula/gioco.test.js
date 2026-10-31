const { test } = require("node:test");
const assert = require("node:assert");
// I comandi attivi dell'istantanea (un elenco o un oggetto con i nomi)
const ha = (g, k) => { const c = g.stato().comandi; return Array.isArray(c) ? c.includes(k) : Object.prototype.hasOwnProperty.call(c || {}, k); };

test("si esplora dal nucleo al reticolo, ogni pagina sta nel palco", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  assert.deepStrictEqual(g.palco(), []);
  assert.match(g.testo(), /Nucleo/);
  assert.match(g.testo(), /C'è nella cellula animale e vegetale/);
  assert.ok(!ha(g, "precedente"));
  await g.tocca("La prossima");
  await g.tocca("La prossima");
  assert.match(g.testo(), /Cloroplasto/);
  assert.match(g.testo(), /C'è nella cellula vegetale\./);
  await g.tocca("La prossima");
  assert.match(g.testo(), /Ribosoma/);
  assert.match(g.testo(), /tutte e tre le cellule/);
  for (let i = 0; i < 4; i++) await g.tocca("La prossima");
  assert.match(g.testo(), /Reticolo endoplasmatico/);
  assert.ok(!ha(g, "prossima"));
  assert.deepStrictEqual(g.palco(), []);
  await g.tocca("Quella prima");
  assert.match(g.testo(), /Membrana plasmatica/);
  await g.tocca("Ho finito");
  assert.match(g.testo(), /Hai visto 8 strutture su 8/);
});

test("il quiz: sì e no, a scelta fra tre, giusto e sbagliato, fino alla fine", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  await g.tocca("Al quiz");
  assert.match(g.testo(), /Il cloroplasto c'è nella cellula animale\?/);
  assert.ok(ha(g, "si") && ha(g, "no") && !ha(g, "risposta"));
  assert.deepStrictEqual(g.palco(), []);
  await g.tocca("No, non c'è");
  assert.match(g.testo(), /Giusto! Il cloroplasto c'è solo nella cellula vegetale/);
  assert.deepStrictEqual(g.palco(), []);
  await g.comando("avanti");
  assert.match(g.testo(), /Il ribosoma c'è nella cellula batterica\?/);
  await g.tocca("No, non c'è");
  assert.match(g.testo(), /Sbagliato\. Il ribosoma c'è in tutte e tre le cellule/);
  await g.comando("avanti");
  assert.match(g.testo(), /Quale struttura fa la fotosintesi\?/);
  assert.ok(ha(g, "risposta") && !ha(g, "si"));
  assert.deepStrictEqual(g.palco(), []);
  await g.tocca("Risposta b");
  assert.match(g.testo(), /Giusto! È il cloroplasto/);
  await g.comando("avanti");
  await g.tocca("No, non c'è");               // nucleo nella batterica: giusto
  await g.comando("avanti");
  await g.tocca("Risposta a");                // la parete: sbagliato
  assert.match(g.testo(), /Sbagliato\. È la membrana plasmatica/);
  await g.comando("avanti");
  await g.tocca("Sì, c'è");                   // mitocondrio nella vegetale: giusto
  assert.match(g.testo(), /Hai risposto giusto a 4 domande su 6/);
  assert.deepStrictEqual(g.palco(), []);
  await g.comando("avanti");
  assert.strictEqual(g.stato().fase, "fine");
});

test("le risposte dei sì e no sono quelle delle strutture", async () => {
  const { DATI } = require("./logica.js");
  for (const q of DATI.domande) {
    if (q.struttura === undefined) {
      assert.ok(q.opzioni.includes(q.giusta));
      continue;
    }
    const s = DATI.strutture.find((x) => x.id === q.struttura);
    assert.strictEqual(q.risposta, s.in.includes(q.cellula));
  }
});
