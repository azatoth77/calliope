const { test } = require("node:test");
const assert = require("node:assert");
// I comandi attivi dell'istantanea (un elenco o un oggetto con i nomi)
const ha = (g, k) => { const c = g.stato().comandi; return Array.isArray(c) ? c.includes(k) : Object.prototype.hasOwnProperty.call(c || {}, k); };

test("quattro passi: giusto, secondo tentativo, soluzione, emolisi e fine", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  assert.deepStrictEqual(g.palco(), []);
  assert.match(g.testo(), /Passo 1 di 4: NaCl allo 0,9 %/);
  // passo 1, isotonica: giusto al primo tentativo (2 punti)
  await g.tocca("Resta com'è");
  assert.match(g.testo(), /Giusto: resta com'è!/);
  assert.match(g.testo(), /Fuori 0,9 %, dentro 0,9 %: soluzione isotonica/);
  assert.deepStrictEqual(g.palco(), []);
  await g.tocca("Prossimo passo");
  // passo 2, ipotonica: sbagliato, poi giusto con l'aiuto (1 punto)
  assert.match(g.testo(), /Passo 2 di 4: NaCl allo 0,6 %/);
  await g.tocca("Si raggrinzisce");
  assert.match(g.testo(), /Non proprio: riprova/);
  assert.match(g.testo(), /Aiuto: fuori c'è 0,6 %, dentro 0,9 %/);
  assert.ok(!ha(g, "raggrinzisce") && ha(g, "gonfia"));
  assert.deepStrictEqual(g.palco(), []);
  await g.tocca("Si gonfia");
  assert.match(g.testo(), /Giusto: si gonfia!/);
  assert.match(g.testo(), /soluzione ipotonica\. L'acqua entra/);
  await g.tocca("Prossimo passo");
  // passo 3, ipertonica: due errori, la soluzione (0 punti)
  assert.match(g.testo(), /Passo 3 di 4: NaCl al 3 %/);
  await g.tocca("Si gonfia");
  await g.tocca("Resta com'è");
  assert.match(g.testo(), /La risposta: si raggrinzisce/);
  assert.match(g.testo(), /soluzione ipertonica\. L'acqua esce/);
  assert.deepStrictEqual(g.palco(), []);
  await g.tocca("Prossimo passo");
  // passo 4, acqua distillata: emolisi
  assert.match(g.testo(), /Passo 4 di 4: Acqua distillata/);
  await g.tocca("Si gonfia");
  assert.match(g.testo(), /fino a rompersi \(emolisi\)/);
  assert.deepStrictEqual(g.palco(), []);
  await g.tocca("Prossimo passo");
  assert.match(g.testo(), /Hai finito i 4 passi\. Hai fatto 5 punti su 8/);
  await g.comando("avanti");
  assert.strictEqual(g.stato().fase, "fine");
});

test("ho finito a metà porta alla fine", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  await g.tocca("Resta com'è");
  await g.tocca("Ho finito");
  assert.match(g.testo(), /Percorso interrotto al passo 1 di 4\. Hai fatto 2 punti su 8/);
  await g.comando("avanti");
  assert.strictEqual(g.stato().fase, "fine");
});

test("i passi sono coerenti con la concentrazione interna", async () => {
  const { DATI } = require("./logica.js");
  for (const p of DATI.passi) {
    const atteso = p.concentrazione < DATI.interna ? ["gonfia", "ipotonica"]
      : p.concentrazione > DATI.interna ? ["raggrinzisce", "ipertonica"] : ["uguale", "isotonica"];
    assert.deepStrictEqual([p.risposta, p.tipo], atteso);
  }
});
