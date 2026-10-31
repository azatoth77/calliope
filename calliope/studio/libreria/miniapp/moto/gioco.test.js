const { test } = require("node:test");
const assert = require("node:assert");
// I comandi attivi dell'istantanea (un elenco o un oggetto con i nomi)
const ha = (g, k) => { const c = g.stato().comandi; return Array.isArray(c) ? c.includes(k) : Object.prototype.hasOwnProperty.call(c || {}, k); };
const punti = (g) => g.stato().giocatori[0].punti;

test("giusta, sbagliata e poi giusta, due errori e la soluzione, fine", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  assert.deepStrictEqual(g.palco(), []);
  assert.match(g.testo(), /Passo 1 di 4/);
  assert.match(g.testo(), /Una bici va a 5 m\/s costanti/);
  assert.match(g.testo(), /B\) 60 m/);
  // 1: giusta al primo tentativo
  await g.tocca("B");
  assert.match(g.testo(), /Giusto!/);
  assert.match(g.testo(), /s = 5 m\/s × 12 s = 60 m/);
  assert.deepStrictEqual(g.palco(), []);
  assert.strictEqual(punti(g), 2);
  await g.tocca("Prossima");
  // 2: la tartaruga, sbagliata e poi giusta con l'aiuto dei minuti
  await g.comando("risposta", "b");
  assert.match(g.testo(), /48 cm non torna/);
  assert.ok(ha(g, "riprova") && !ha(g, "prossima"));
  assert.deepStrictEqual(g.palco(), []);
  await g.tocca("Riprovo");
  assert.match(g.testo(), /1 min = 60 s/);
  assert.deepStrictEqual(g.palco(), []);
  await g.comando("risposta", "c");
  assert.match(g.testo(), /2 min = 2 × 60 = 120 s; s = 4 cm\/s × 120 s = 480 cm/);
  assert.strictEqual(punti(g), 3);
  await g.comando("prossima");
  // 3: il treno, due errori e la soluzione con i km/h in m/s
  await g.comando("risposta", "b");
  await g.comando("riprova");
  await g.comando("risposta", "d");
  assert.match(g.testo(), /La soluzione/);
  assert.match(g.testo(), /108 km\/h = 108 : 3,6 = 30 m\/s; s = 30 m\/s × 20 s = 600 m/);
  assert.deepStrictEqual(g.palco(), []);
  assert.strictEqual(punti(g), 3);
  await g.comando("prossima");
  // 4: l'auto, mezz'ora
  await g.comando("risposta", "d");
  assert.match(g.testo(), /30 min = 30 : 60 = 0,5 h; s = 90 km\/h × 0,5 h = 45 km/);
  await g.comando("prossima");
  assert.match(g.testo(), /Hai fatto 5 punti su 8/);
  assert.deepStrictEqual(g.palco(), []);
});

test("ho finito dalla domanda e dalla verifica", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  await g.tocca("Ho finito");
  assert.match(g.testo(), /Hai fatto 0 punti su 8/);
  const h = await apriGioco({ seme: 1, inizia: true });
  await h.comando("risposta", "a");
  assert.ok(ha(h, "finito"));
  await h.comando("finito");
  assert.match(h.testo(), /Hai fatto 0 punti su 8/);
});
