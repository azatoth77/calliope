// Il globulo rosso e l'osmosi (libreria dello Studio, 31/10, issue #297, parte 2; percorso):
// quattro passi, un globulo rosso in soluzioni di cloruro di sodio diverse. A ogni passo prima la
// previsione (si gonfia, resta com'è, si raggrinzisce), poi la verifica con il perché; se la
// previsione è sbagliata un secondo tentativo con un aiuto, dopo il secondo errore la soluzione.
// Punti: 2 al primo tentativo, 1 al secondo. Logica pura: pagina, pulsanti e voce sono del
// motore di Calliope. I dati li controlla la prova di verità (prove/prova_studio_miniapp.py).
//
// Forma di DATI:
//   DATI.interna: 0.9    la concentrazione di NaCl (in %, massa su volume) equivalente
//                        all'interno del globulo rosso, il riferimento di ogni passo
//   DATI.passi: [{ concentrazione, risposta, tipo }]
//     concentrazione: NaCl fuori dal globulo, in % (0 = acqua distillata)
//     risposta: "gonfia" | "uguale" | "raggrinzisce"
//     tipo: "ipotonica" | "isotonica" | "ipertonica"  (rispetto a DATI.interna)
//   Deve valere: concentrazione < interna → ipotonica e gonfia; = → isotonica e uguale;
//   > → ipertonica e raggrinzisce.
// Ciò che si mostra viene da DATI: la concentrazione fuori e dentro (scritte con la virgola),
// il nome della soluzione (tipo), da che parte va l'acqua (dal confronto delle due
// concentrazioni), la risposta giusta; con concentrazione 0 l'emolisi (il globulo si rompe); alla
// fine i punti su 2 × il numero dei passi.
"use strict";

const DATI = {
  interna: 0.9,
  passi: [
    { concentrazione: 0.9, risposta: "uguale", tipo: "isotonica" },
    { concentrazione: 0.6, risposta: "gonfia", tipo: "ipotonica" },
    { concentrazione: 3, risposta: "raggrinzisce", tipo: "ipertonica" },
    { concentrazione: 0, risposta: "gonfia", tipo: "ipotonica" },
  ],
};

const RISPOSTE = { gonfia: "si gonfia", uguale: "resta com'è", raggrinzisce: "si raggrinzisce" };

// 0.9 → «0,9»
function numero(x) { return String(x).replace(".", ","); }
// «NaCl allo 0,9 %», «NaCl al 3 %», «Acqua distillata»
function soluzione(c) {
  if (c === 0) return "Acqua distillata";
  return `NaCl ${c < 1 ? "allo" : "al"} ${numero(c)} %`;
}
// Da che parte va l'acqua: "entra" | "pari" | "esce"
function verso(c) { return c < DATI.interna ? "entra" : c > DATI.interna ? "esce" : "pari"; }

function perche(p) {
  const fuori = p.concentrazione === 0 ? "Fuori niente sale" : `Fuori ${numero(p.concentrazione)} %`;
  const intro = `${fuori}, dentro l'equivalente dello ${numero(DATI.interna)} %: soluzione ${p.tipo}.`;
  const v = verso(p.concentrazione);
  if (v === "pari") return `${intro} I soluti sono pari dentro e fuori: l'acqua entra ed esce allo stesso modo e il globulo resta com'è.`;
  if (v === "esce") return `${intro} L'acqua esce verso il lato più concentrato di soluti: il globulo si raggrinzisce (crenatura).`;
  if (p.concentrazione === 0) return `${intro} Entra tanta acqua verso il lato con i soluti: il globulo si gonfia fino a rompersi (emolisi).`;
  return `${intro} L'acqua entra verso il lato più concentrato di soluti: il globulo si gonfia.`;
}

function aiuto(p) {
  const fuori = p.concentrazione === 0 ? "fuori non c'è sale" : `fuori c'è ${numero(p.concentrazione)} %`;
  return `Aiuto: ${fuori}, dentro l'equivalente dello ${numero(DATI.interna)} %. L'acqua passa dal lato meno concentrato di soluti a quello più concentrato.`;
}

function prevedi(d, scelta) {
  const p = DATI.passi[d.passo];
  if (scelta === p.risposta) {
    const punti = d.tentativo === 1 ? 2 : 1;
    return { dati: { ...d, giusto: true, punti: d.punti + punti }, punti, fase: "verifica" };
  }
  if (d.tentativo === 1) return { dati: { ...d, tentativo: 2, sbagliata: scelta }, fase: "previsione" };
  return { dati: { ...d, giusto: false }, fase: "verifica" };
}

function totale(d) { return `Hai fatto ${d.punti} punti su ${2 * DATI.passi.length}.`; }

const finito = (d) => ({ dati: d, esito: `Percorso interrotto al passo ${d.passo + 1} di ${DATI.passi.length}. ${totale(d)}`,
                         dopo: "fine" });

const GIOCO = {
  nuovaPartita() { return { passo: 0, tentativo: 1, sbagliata: null, giusto: null, punti: 0 }; },
  attivi: {
    // al secondo tentativo la previsione sbagliata non si ripete
    previsione: (d) => {
      const a = { gonfia: true, uguale: true, raggrinzisce: true, finito: true };
      if (d.sbagliata) a[d.sbagliata] = false;
      return a;
    },
  },
  mosse: {
    previsione: {
      gonfia: (d) => prevedi(d, "gonfia"),
      uguale: (d) => prevedi(d, "uguale"),
      raggrinzisce: (d) => prevedi(d, "raggrinzisce"),
      finito,
    },
    verifica: {
      prossimo: (d) => {
        if (d.passo + 1 >= DATI.passi.length) {
          return { dati: d, esito: `Hai finito i ${DATI.passi.length} passi. ${totale(d)}`, dopo: "fine" };
        }
        return { dati: { ...d, passo: d.passo + 1, tentativo: 1, sbagliata: null, giusto: null },
                 fase: "previsione" };
      },
      finito,
    },
  },
  vista: {
    previsione: (d) => {
      const p = DATI.passi[d.passo];
      return { titolo: `Passo ${d.passo + 1} di ${DATI.passi.length}: ${soluzione(p.concentrazione)}`,
               sottotitolo: d.tentativo === 1 ? "Cosa fa il globulo rosso?" : "Non proprio: riprova.",
               testo: d.tentativo === 1
                 ? `Dentro il globulo la concentrazione di soluti equivale a una soluzione di NaCl allo ${numero(DATI.interna)} %.`
                 : aiuto(p) };
    },
    verifica: (d) => {
      const p = DATI.passi[d.passo];
      const giusta = RISPOSTE[p.risposta];
      const titolo = d.giusto ? `Giusto: ${giusta}!` : `La risposta: ${giusta}`;
      return { titolo: titolo.charAt(0).toUpperCase() + titolo.slice(1),
               sottotitolo: soluzione(p.concentrazione), testo: perche(p) };
    },
  },
};

if (typeof module !== "undefined") module.exports = { GIOCO, DATI, numero, soluzione, verso, perche };
