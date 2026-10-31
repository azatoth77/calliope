const { test } = require("node:test");
const assert = require("node:assert");
// I comandi attivi dell'istantanea (un elenco o un oggetto con i nomi)
const ha = (g, k) => { const c = g.stato().comandi; return Array.isArray(c) ? c.includes(k) : Object.prototype.hasOwnProperty.call(c || {}, k); };
const punti = (g) => g.stato().giocatori[0].punti;

test("giusta al primo, sbagliata e poi giusta, due errori e la soluzione", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  assert.deepStrictEqual(g.palco(), []);
  assert.match(g.testo(), /Reazione 1 di 4/);
  assert.match(g.testo(), /2 H₂ \+ \? O₂ → 2 H₂O/);
  // 1: giusto al primo tentativo, 2 punti
  await g.comando("coeff", 1);
  assert.match(g.testo(), /Giusto!/);
  assert.match(g.testo(), /O: 2 a sinistra, 2 a destra/);
  assert.deepStrictEqual(g.palco(), []);
  assert.strictEqual(punti(g), 2);
  assert.ok(!ha(g, "riprova"));
  await g.tocca("Prossima");
  // 2: sbagliato, poi giusto con l'aiuto (1 punto)
  assert.match(g.testo(), /N₂ \+ \? H₂ → 2 NH₃/);
  await g.comando("coeff", 2);
  assert.match(g.testo(), /Non torna/);
  assert.match(g.testo(), /H: 4 a sinistra, 6 a destra/);
  assert.ok(ha(g, "riprova") && !ha(g, "prossima"));
  assert.deepStrictEqual(g.palco(), []);
  await g.tocca("Riprovo");
  assert.match(g.testo(), /Aiuto: a destra ci sono 6 atomi di H, e ogni H₂ ne ha 2\. Il coefficiente 1 non si scrive/);
  assert.deepStrictEqual(g.palco(), []);
  await g.comando("coeff", 3);
  assert.match(g.testo(), /H: 6 a sinistra, 6 a destra/);
  assert.strictEqual(punti(g), 3);
  await g.comando("prossima");
  // 3: due errori, la soluzione
  assert.match(g.testo(), /CH₄ \+ \? O₂ → CO₂ \+ 2 H₂O/);
  await g.comando("coeff", 1);
  await g.comando("riprova");
  await g.comando("coeff", 4);
  assert.match(g.testo(), /La soluzione/);
  assert.match(g.testo(), /Con 4: O: 8 a sinistra, 4 a destra/);
  assert.match(g.testo(), /Serve 2: O: 4 a sinistra, 4 a destra/);
  assert.deepStrictEqual(g.palco(), []);
  assert.strictEqual(punti(g), 3);
  await g.comando("prossima");
  // 4: il sodio, giusto; poi la fine
  assert.match(g.testo(), /\? Na \+ O₂ → 2 Na₂O/);
  await g.comando("coeff", 4);
  assert.match(g.testo(), /Na: 4 a sinistra, 4 a destra/);
  await g.comando("prossima");
  assert.match(g.testo(), /Hai fatto 5 punti su 8/);
  assert.deepStrictEqual(g.palco(), []);
});

test("ho finito porta alla fine da ogni pagina", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  await g.tocca("Ho finito");
  assert.match(g.testo(), /Hai fatto 0 punti su 8/);
  assert.strictEqual(g.stato().fase, "esito");
  const h = await apriGioco({ seme: 1, inizia: true });
  await h.comando("coeff", 3);
  assert.ok(ha(h, "finito"));
  await h.comando("finito");
  assert.match(h.testo(), /Hai fatto 0 punti su 8/);
});

test("i pedici sono solo dello schermo: l'esito resta in testo semplice", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  await g.tocca("Ho finito");
  const e = g.stato().esito || "";
  assert.ok(!/[₀-₉]/.test(e), e);
});
