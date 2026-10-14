// Apri le porte (prove dei comandi a voce, 11/10; dal 14/10 con la macchina a stati di Calliope):
// tre porte, una nasconde il premio. Si gioca a voce («la porta due», «tre») o toccando; il nome
// di chi gioca arriva alla mossa («giocatore»: true nella macchina). Le mosse ricevute (comando e
// giocatore) le salva per le prove, le ultime venti
"use strict";
const ricevute = [];

const GIOCO = {
  nuovaPartita() { return { aperte: [], premio: 3 }; },
  attivi: {
    turno: (d) => ({ porta: chiuse(d) }),
  },
  mosse: {
    turno: {
      porta(d, { valore, giocatore }) {
        registra(valore, giocatore);
        const aperte = d.aperte.concat([valore]);
        if (valore !== d.premio) return { dati: { ...d, aperte } };
        return { dati: { ...d, aperte }, punti: 1, esito: "Trovato!", dopo: "fine" };
      },
    },
  },
  vista: {
    turno: () => ({ titolo: "Quale porta apri?" }),
  },
};

function chiuse(d) {
  return [1, 2, 3].filter((p) => !d.aperte.includes(p));
}

function registra(valore, giocatore) {
  if (typeof calliope === "undefined" || !calliope || typeof calliope.salva !== "function") return;
  ricevute.push({ comando: "porta_" + valore, giocatore: giocatore || null });
  ricevute.splice(0, Math.max(0, ricevute.length - 20));
  calliope.salva("mosse", ricevute).catch(() => {});
}

if (typeof module !== "undefined") module.exports = { GIOCO, chiuse };
