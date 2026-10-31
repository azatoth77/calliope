// La verità delle mini-app della libreria dello Studio (31/10, issue #297, parte 2): carica
// logica.js di ogni mini-app con Node e stampa in JSON i dati (DATI) e ciò che la logica mostra
// (i conti, le frasi), così prova_studio_miniapp.py li ricontrolla con i suoi conti e le sue
// tabelle, scritti a parte. Uso: node verita_miniapp.mjs <cartella delle mini-app>
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const base = process.argv[2];
const carica = (n) => require(path.join(base, n, "logica.js"));
const out = {};

{
  const m = carica("atomo");
  out.atomo = { elementi: m.DATI.elementi, descrizioni: m.DATI.elementi.map((_, i) => m.descrivi(i + 1)) };
}
{
  const m = carica("bilancia");
  out.bilancia = m.DATI.reazioni.map((r) => {
    const el = m.elementoChiave(r);
    const prove = [1, 2, 3, 4].map((c) => ({ c, sinistra: m.conta(r, "sinistra", el, c), destra: m.conta(r, "destra", el, c),
      equazione: m.equazione(r, c), riga: m.rigaConto(r, c) }));
    return { r, elemento: el, equazione: m.equazione(r, null), prove, aiuto: m.aiuto(r) };
  });
}
{
  const m = carica("densita");
  const tutti = [...m.DATI.oggetti, ...m.DATI.domande];
  out.densita = { acqua: m.DATI.acqua, oggetti: m.DATI.oggetti, domande: m.DATI.domande,
    conti: tutti.map((o) => ({ materiale: o.materiale, m: o.m, V: o.V, d: m.densita(o.m, o.V), cifre: m.cifre(m.densita(o.m, o.V)),
      destino: m.destino(o.m, o.V), conto: m.conto(o.m, o.V) })) };
}
{
  const m = carica("moto");
  out.moto = m.DATI.passi.map((p) => ({ p, risolto: m.risolvi(p), conto: m.conto(p) }));
}
{
  const m = carica("bit");
  const stati = [[1, 0, 1, 1, 0, 1, 0, 0], [0, 0, 0, 0, 0, 0, 0, 1], [1, 1, 1, 1, 1, 1, 1, 1], [0, 0, 0, 0, 0, 0, 0, 0]]
    .map((s) => s.map(Boolean));
  out.bit = { dati: m.DATI, stati: stati.map((a) => ({ acceso: a, valore: m.valore(a), cifre: m.cifre(a), somma: m.somma(a) })) };
}
{
  const m = carica("binario");
  out.binario = { esempi: m.DATI.esempi.map((e) => ({ decimale: e.decimale, binario: m.binario(e.decimale),
    divisioni: m.divisioni(e.decimale), conPesi: m.conPesi(m.binario(e.decimale)) })),
    domande: m.DATI.domande.map((q) => ({ ...q, perche: q.opzioni.map((o, i) => i === q.giusta ? "" : m.perche(q, o)) })) };
}
{
  const m = carica("cellula");
  out.cellula = { strutture: m.DATI.strutture, cellule: m.DATI.cellule,
    domande: m.DATI.domande.map((q) => ({ ...q, testo_detto: m.testoDomanda(q), perche: m.perche(q) })) };
}
{
  const m = carica("osmosi");
  out.osmosi = { interna: m.DATI.interna, passi: m.DATI.passi.map((p) => ({ ...p, verso: m.verso(p.concentrazione),
    soluzione: m.soluzione(p.concentrazione), perche: m.perche(p) })) };
}
process.stdout.write(JSON.stringify(out));
