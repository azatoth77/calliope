// Le pagine (prove del palco fisso, 14/10): un gioco finto che passa per tutti i modelli di
// pagina di Calliope, uno per fase: titolo, scelte, griglia, messaggio, punteggi e tela (la
// classifica è la fine, la preparazione e l'esito sono di Calliope). Serve alle prove a secco
// (la misura del palco in Node) e a quelle nel browser vero (la misura sullo schermo)
"use strict";

const GIOCO = {
  nuovaPartita() { return { scelto: null, casella: null }; },
  // la casella 1 è la stella: non si sceglie
  attivi: { tabellone: () => ({ casella: [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] }) },
  mosse: {
    benvenuto: { parti: (d) => ({ dati: d, fase: "domanda" }) },
    domanda: {
      colore(d, { valore }) {
        return { dati: { ...d, scelto: valore }, punti: valore === "rosso" ? 1 : 0,
                 esito: `Hai scelto il ${valore}`, dopo: "tabellone" };
      },
    },
    tabellone: {
      casella: (d, { valore }) => ({ dati: { ...d, casella: valore }, fase: "annuncio" }),
    },
    annuncio: { prosegui: (d) => ({ dati: d, fase: "punti_parziali" }) },
    punti_parziali: { vediamo: (d) => ({ dati: d, fase: "libera" }) },
  },
  vista: {
    benvenuto: () => ({ titolo: "Le pagine", sottotitolo: "Un giro per tutti i modelli" }),
    domanda: () => ({ titolo: "Che colore scegli?" }),
    tabellone: (d) => ({
      titolo: "Scegli una casella",
      caselle: [0, 1, 2].map((r) => [0, 1, 2, 3].map((c) => {
        const n = r * 4 + c + 1;
        return r === 0 && c === 0 ? { testo: "★", colore: "giallo" } : { comando: "casella", valore: n };
      })),
    }),
    annuncio: (d) => ({ titolo: "Un annuncio", testo: `Hai preso la casella ${d.casella}` }),
    punti_parziali: () => ({ titolo: "Come siamo messi" }),
  },
  tela: {
    libera(area, dati, tela) {
      const p = document.createElement("p");
      p.textContent = `Area libera di ${tela.larghezza}×${tela.altezza}`;
      area.appendChild(p);
    },
  },
};

if (typeof module !== "undefined") module.exports = { GIOCO };
