// Tris (prove dei giochi, 05/10; dal 14/10 con la macchina a stati di Calliope e la pagina
// «griglia»): in due a turno, o da solo contro il computer. Le regole senza DOM: la griglia, i
// pulsanti delle caselle libere, i turni, i punti e la fine li disegna e li tiene Calliope
"use strict";

const LINEE = [[0, 1, 2], [3, 4, 5], [6, 7, 8], [0, 3, 6], [1, 4, 7], [2, 5, 8],
  [0, 4, 8], [2, 4, 6]];

function vincitore(celle) {
  for (const [a, b, c] of LINEE) {
    if (celle[a] && celle[a] === celle[b] && celle[a] === celle[c]) return celle[a];
  }
  return "";
}

function libere(celle) {
  return celle.map((x, i) => (x ? 0 : i + 1)).filter(Boolean);
}

// Il computer: vince se può, altrimenti blocca, altrimenti il centro, poi la prima libera
function mossaComputer(celle, io) {
  const tu = io === "X" ? "O" : "X";
  const vuote = libere(celle).map((n) => n - 1);
  for (const segno of [io, tu]) {
    for (const i of vuote) {
      const c = celle.slice();
      c[i] = segno;
      if (vincitore(c) === segno) return i;
    }
  }
  if (vuote.includes(4)) return 4;
  return vuote.length ? vuote[0] : -1;
}

const GIOCO = {
  nuovaPartita({ giocatori }) {
    return { celle: Array(9).fill(""), segno: "X", computer: giocatori === 1 };
  },
  attivi: {
    turno: (d) => ({ casella: libere(d.celle) }),
  },
  mosse: {
    turno: {
      casella(d, { valore }) {
        const celle = d.celle.slice();
        celle[valore - 1] = d.segno;
        let altro = d.segno === "X" ? "O" : "X";
        if (d.computer && !vincitore(celle) && libere(celle).length) {
          celle[mossaComputer(celle, altro)] = altro;
          altro = d.segno;
        }
        const v = vincitore(celle);
        const dati = { ...d, celle, segno: d.computer ? d.segno : altro };
        if (v) return { dati, punti: v === d.segno ? 1 : 0, esito: d.computer && v !== d.segno ? "Ha vinto il computer" : `Ha vinto ${v}!`, dopo: "fine" };
        if (!libere(celle).length) return { dati, esito: "Pareggio", dopo: "fine" };
        return { dati };
      },
    },
  },
  vista: {
    turno: (d) => ({
      titolo: "Tris",
      testo: d.computer ? `Tu sei ${d.segno}` : `Mette ${d.segno}`,
      caselle: [0, 1, 2].map((r) => [0, 1, 2].map((c) => {
        const i = r * 3 + c;
        return d.celle[i] ? { testo: d.celle[i] } : { comando: "casella", valore: i + 1 };
      })),
    }),
  },
};

if (typeof module !== "undefined") module.exports = { GIOCO, vincitore, mossaComputer, libere };
