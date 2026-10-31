// Dentro la cellula (libreria dello Studio, 31/10, issue #297, parte 2; quiz): prima si
// esplorano otto strutture della cellula, cosa fanno e in quali cellule ci sono (animale,
// vegetale, batterica), poi un quiz di sei domande, un punto per ogni risposta giusta. Logica
// pura: pagina, pulsanti e voce sono del motore di Calliope. I dati li controlla la prova di
// verità (prove/prova_studio_miniapp.py).
//
// Forma di DATI:
//   DATI.cellule: ["animale", "vegetale", "batterica"]  (l'ordine in cui si elencano)
//   DATI.strutture: [{ id, art, nome, funzione, in }]
//     id: testo breve; art: "il" | "la" (l'articolo di nome); nome: con l'iniziale maiuscola;
//     funzione: una frase su cosa fa; in: elenco fra "animale", "vegetale", "batterica" (le
//     cellule in cui la struttura c'è)
//   DATI.domande: sei domande, di due forme
//     { struttura: id, cellula: "animale" | "vegetale" | "batterica", risposta: true | false }
//       «<art> <nome> c'è nella cellula <cellula>?»; risposta deve valere
//       strutture[id].in.includes(cellula)
//     { testo, opzioni: [tre id di strutture], giusta: id }  (a scelta fra tre: a, b, c)
// Ciò che si mostra viene tutto da DATI: nome, funzione e «c'è nella cellula …» (da «in»)
// nell'esplorazione; domanda, opzioni ed esito (giusto o sbagliato, con il perché costruito
// da «in» o da «funzione») nel quiz; il totale delle risposte giuste alla fine.
"use strict";

const DATI = {
  cellule: ["animale", "vegetale", "batterica"],
  strutture: [
    { id: "nucleo", art: "il", nome: "Nucleo",
      funzione: "Custodisce il DNA e dirige la vita della cellula.",
      in: ["animale", "vegetale"] },
    { id: "mitocondrio", art: "il", nome: "Mitocondrio",
      funzione: "Con la respirazione cellulare produce l'ATP dagli zuccheri.",
      in: ["animale", "vegetale"] },
    { id: "cloroplasto", art: "il", nome: "Cloroplasto",
      funzione: "Fa la fotosintesi: con la luce produce zuccheri.",
      in: ["vegetale"] },
    { id: "ribosoma", art: "il", nome: "Ribosoma",
      funzione: "Costruisce le proteine.",
      in: ["animale", "vegetale", "batterica"] },
    { id: "parete", art: "la", nome: "Parete cellulare",
      funzione: "Involucro rigido fuori dalla membrana: sostiene e protegge.",
      in: ["vegetale", "batterica"] },
    { id: "vacuolo", art: "il", nome: "Vacuolo centrale",
      funzione: "Grande sacco di acqua e sostanze: tiene la cellula turgida.",
      in: ["vegetale"] },
    { id: "membrana", art: "la", nome: "Membrana plasmatica",
      funzione: "Il confine della cellula: decide cosa entra e cosa esce.",
      in: ["animale", "vegetale", "batterica"] },
    { id: "reticolo", art: "il", nome: "Reticolo endoplasmatico",
      funzione: "Rete di membrane che produce e trasporta proteine e lipidi.",
      in: ["animale", "vegetale"] },
  ],
  domande: [
    { struttura: "cloroplasto", cellula: "animale", risposta: false },
    { struttura: "ribosoma", cellula: "batterica", risposta: true },
    { testo: "Quale struttura fa la fotosintesi?", opzioni: ["mitocondrio", "cloroplasto", "vacuolo"],
      giusta: "cloroplasto" },
    { struttura: "nucleo", cellula: "batterica", risposta: false },
    { testo: "Chi decide cosa entra ed esce dalla cellula?", opzioni: ["parete", "ribosoma", "membrana"],
      giusta: "membrana" },
    { struttura: "mitocondrio", cellula: "vegetale", risposta: true },
  ],
};

const LETTERE = ["a", "b", "c"];

function struttura(id) { return DATI.strutture.find((s) => s.id === id); }
function maiuscola(t) { return t.charAt(0).toUpperCase() + t.slice(1); }
// «il ribosoma», «la parete cellulare»
function conArticolo(s) { return `${s.art} ${s.nome.toLowerCase()}`; }
// «animale e vegetale», «animale, vegetale e batterica»
function elenco(v) { return v.length === 1 ? v[0] : `${v.slice(0, -1).join(", ")} e ${v[v.length - 1]}`; }
// Le cellule in cui c'è, nell'ordine di DATI.cellule
function dove(s) { return DATI.cellule.filter((c) => s.in.includes(c)); }
function doveTesto(s) {
  const d = dove(s);
  return d.length === DATI.cellule.length ? "C'è in tutte e tre le cellule: animale, vegetale e batterica."
    : `C'è nella cellula ${elenco(d)}.`;
}
function siNo(q) { return q.struttura !== undefined; }
function testoDomanda(q) {
  return siNo(q) ? `${maiuscola(conArticolo(struttura(q.struttura)))} c'è nella cellula ${q.cellula}?` : q.testo;
}
// Il perché dell'esito
function perche(q) {
  if (siNo(q)) {
    const s = struttura(q.struttura);
    const d = dove(s);
    return `${maiuscola(conArticolo(s))} c'è ${d.length === DATI.cellule.length ? "in tutte e tre le cellule" : `solo nella cellula ${elenco(d)}`}.`;
  }
  const s = struttura(q.giusta);
  return `È ${conArticolo(s)}: ${s.funzione.charAt(0).toLowerCase()}${s.funzione.slice(1)}`;
}

function rispondi(d, giusto) {
  const q = DATI.domande[d.q];
  const giuste = d.giuste + (giusto ? 1 : 0);
  const ultima = d.q + 1 >= DATI.domande.length;
  let esito = `${giusto ? "Giusto!" : "Sbagliato."} ${perche(q)}`;
  if (ultima) esito += ` Hai risposto giusto a ${giuste} domande su ${DATI.domande.length}.`;
  return { dati: { ...d, q: d.q + 1, giuste }, punti: giusto ? 1 : 0, esito,
           dopo: ultima ? "fine" : "domanda" };
}

function vai(d, i) { return { ...d, i, visti: d.visti.includes(i) ? d.visti : [...d.visti, i] }; }

const finito = (d) => ({ dati: d,
  esito: d.q > 0 ? `Quiz lasciato a metà: ${d.giuste} giuste su ${d.q}.`
    : `Hai visto ${d.visti.length} strutture su ${DATI.strutture.length}.`,
  dopo: "fine" });

const GIOCO = {
  nuovaPartita() { return { i: 0, visti: [0], q: 0, giuste: 0 }; },
  attivi: {
    esplora: (d) => {
      const a = { quiz: true, finito: true };
      if (d.i < DATI.strutture.length - 1) a.prossima = true;
      if (d.i > 0) a.precedente = true;
      return a;
    },
    domanda: (d) => (siNo(DATI.domande[d.q]) ? { si: true, no: true, finito: true }
      : { risposta: LETTERE.slice(), finito: true }),
  },
  mosse: {
    esplora: {
      prossima: (d) => ({ dati: vai(d, d.i + 1) }),
      precedente: (d) => ({ dati: vai(d, d.i - 1) }),
      quiz: (d) => ({ dati: d, fase: "domanda" }),
      finito,
    },
    domanda: {
      si: (d) => rispondi(d, DATI.domande[d.q].risposta === true),
      no: (d) => rispondi(d, DATI.domande[d.q].risposta === false),
      risposta: (d, { valore }) => {
        const q = DATI.domande[d.q];
        return rispondi(d, q.opzioni[LETTERE.indexOf(valore)] === q.giusta);
      },
      finito,
    },
  },
  vista: {
    esplora: (d) => {
      const s = DATI.strutture[d.i];
      return { titolo: s.nome, sottotitolo: `Struttura ${d.i + 1} di ${DATI.strutture.length}`,
               testo: `${s.funzione} ${doveTesto(s)}` };
    },
    domanda: (d) => {
      const q = DATI.domande[d.q];
      const v = { titolo: `Domanda ${d.q + 1} di ${DATI.domande.length}`, sottotitolo: testoDomanda(q) };
      if (!siNo(q)) v.testo = q.opzioni.map((id, k) => `${LETTERE[k]}) ${struttura(id).nome}`).join("   ");
      return v;
    },
  },
};

if (typeof module !== "undefined") module.exports = { GIOCO, DATI, dove, testoDomanda, perche };
