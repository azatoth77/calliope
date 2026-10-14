// Segnali (prove delle partite condivise, 14/10): un gioco della macchina a stati con una TELA,
// la via libera per eccezione. La tela è un pulsante grande: ogni tocco manda un segnale agli
// altri schermi della partita (calliope.manda, passando da Calliope) con il numero del segnale e
// l'ultimo ricevuto. Le partite condivise del motore sono rimandate (decisione 6 del 12/10): qui
// la condivisione è tutta della tela, con i messaggi di sempre
"use strict";
let inviati = 0;
let visto = null;
let pulsante = null;

calliope.quandoPronto((a) => {
  (a.storia || []).forEach((m) => { if (m.dati && Number.isInteger(m.dati.segnale)) visto = m.dati.segnale; });
});
calliope.quandoMessaggio((m) => {
  if (m && m.dati && Number.isInteger(m.dati.segnale)) visto = m.dati.segnale;
  if (pulsante) pulsante.textContent = testo();
});

function testo() {
  return visto === null ? "Tocca per mandare un segnale" : `Ricevuto il segnale ${visto}: tocca per rispondere`;
}

const GIOCO = {
  nuovaPartita() { return {}; },
  tela: {
    gioco(area) {
      pulsante = document.createElement("button");
      pulsante.type = "button";
      pulsante.className = "segnale";
      pulsante.style.cssText = "width:100%;height:100%;font-size:40px;border:0;border-radius:16px";
      pulsante.textContent = testo();
      pulsante.addEventListener("click", () => {
        inviati++;
        calliope.manda({ segnale: inviati, visto });
      });
      area.appendChild(pulsante);
    },
  },
  vista: {
    gioco: () => ({ titolo: "Segnali" }),
  },
};
