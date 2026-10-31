// Affonda o galleggia? (libreria dello Studio, 31/10, issue #297, parte 2; quiz): prima si
// esplorano oggetti di materiali veri, per ognuno la densità d = m / V e se in acqua galleggia o
// affonda; poi un quiz con massa e volume, un punto per risposta giusta, e l'esito dice il conto.
// Logica pura: pagina, pulsanti e voce sono del motore di Calliope. I dati li controlla la prova
// di verità (prove/prova_studio_miniapp.py).
//
// Forma di DATI:
//   DATI.acqua: la densità dell'acqua in g/cm³ (1)
//   DATI.oggetti: elenco di { id, nome, materiale, m, V } (m in grammi, V in cm³; massa e volume
//     di fantasia ma con m / V uguale, a due cifre, alla densità vera del materiale); `id` è il
//     valore del comando «oggetto» nel manifesto
//   DATI.domande: elenco di { m, V, materiale } (stesse unità; m / V mai uguale all'acqua)
// Ciò che si mostra: d = m : V con la virgola e due cifre (densita, cifre), «galleggia» se
// d < acqua, «affonda» se d > acqua (destino).
"use strict";

const DATI = {
  acqua: 1,
  oggetti: [
    { id: "sughero", nome: "Tappo di sughero", materiale: "sughero", m: 6, V: 25 },
    { id: "abete", nome: "Tavoletta di abete", materiale: "legno di abete", m: 225, V: 500 },
    { id: "ghiaccio", nome: "Cubetto di ghiaccio", materiale: "ghiaccio", m: 23, V: 25 },
    { id: "pvc", nome: "Pezzo di tubo in PVC", materiale: "plastica PVC", m: 69, V: 50 },
    { id: "alluminio", nome: "Cubetto di alluminio", materiale: "alluminio", m: 27, V: 10 },
    { id: "ferro", nome: "Bullone di ferro", materiale: "ferro", m: 118, V: 15 },
    { id: "rame", nome: "Cilindretto di rame", materiale: "rame", m: 448, V: 50 },
  ],
  domande: [
    { m: 48, V: 50, materiale: "cera d'api" },
    { m: 125, V: 50, materiale: "vetro" },
    { m: 3, V: 100, materiale: "polistirolo espanso" },
    { m: 91, V: 100, materiale: "olio d'oliva" },
    { m: 58, V: 50, materiale: "gomma" },
  ],
};

function densita(m, V) { return m / V; }
// Un numero con la virgola e due cifre: 0.24 → «0,24»
function cifre(x) { return x.toFixed(2).replace(".", ","); }
function numero(x) { return String(x).replace(".", ","); }
function destino(m, V) { return densita(m, V) < DATI.acqua ? "galleggia" : "affonda"; }
// Il conto: «d = 6 : 25 = 0,24 g/cm³, meno di 1: galleggia»
function conto(m, V) {
  const d = densita(m, V);
  const rispetto = d < DATI.acqua ? "meno" : "più";
  return `d = ${numero(m)} : ${numero(V)} = ${cifre(d)} g/cm³, ${rispetto} di ${numero(DATI.acqua)}: ${destino(m, V)}`;
}

const N = DATI.domande.length;

const GIOCO = {
  nuovaPartita() { return { scelto: null, domanda: 0, giuste: 0 }; },
  mosse: {
    esplora: {
      oggetto: (d, { valore }) => ({ dati: { ...d, scelto: valore } }),
      quiz: (d) => ({ dati: d, fase: "quiz" }),
    },
    quiz: {
      galleggia: (d) => risposta(d, "galleggia"),
      affonda: (d) => risposta(d, "affonda"),
      finito: (d) => ({ dati: d, esito: `Hai risposto giusto a ${d.giuste} su ${d.domanda}.`, dopo: "fine" }),
    },
  },
  vista: {
    esplora: (d) => {
      const o = DATI.oggetti.find((x) => x.id === d.scelto);
      if (!o) {
        return { titolo: "Affonda o galleggia?",
                 testo: `Scegli un oggetto: vedi la sua densità d = m : V e cosa fa in acqua (${numero(DATI.acqua)} g/cm³).` };
      }
      return { titolo: o.nome, sottotitolo: `m = ${numero(o.m)} g, V = ${numero(o.V)} cm³`,
               testo: conto(o.m, o.V) + "." };
    },
    quiz: (d) => {
      const q = DATI.domande[d.domanda];
      return { titolo: `Domanda ${d.domanda + 1} di ${N}`,
               sottotitolo: `${q.materiale.charAt(0).toUpperCase() + q.materiale.slice(1)}: m = ${numero(q.m)} g, V = ${numero(q.V)} cm³`,
               testo: "In acqua affonda o galleggia?" };
    },
  },
};

function risposta(d, detta) {
  const q = DATI.domande[d.domanda];
  const giusta = detta === destino(q.m, q.V);
  const dati = { ...d, domanda: d.domanda + 1, giuste: d.giuste + (giusta ? 1 : 0) };
  const esito = `${giusta ? "Giusto" : "No"}: ${conto(q.m, q.V)}.`;
  return { dati, punti: giusta ? 1 : 0, esito, dopo: dati.domanda >= N ? "fine" : "quiz" };
}

if (typeof module !== "undefined") module.exports = { GIOCO, DATI, densita, cifre, destino, conto };
