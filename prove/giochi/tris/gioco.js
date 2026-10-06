// Tris: disegno e tocchi nel riquadro. Da solo contro il computer; con un secondo schermo
// nella partita (condivisa) le mosse passano da Calliope con calliope.manda
"use strict";
(function () {
  const box = document.getElementById("gioco");
  let stato = nuovaPartita();
  let io = "X";
  let giocatori = 1;
  let record = { vinte: 0, perse: 0 };

  const titolo = document.createElement("p");
  titolo.className = "titolo";
  const griglia = document.createElement("div");
  griglia.className = "griglia";
  const celle = [];
  for (let i = 0; i < 9; i++) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "cella";
    b.addEventListener("click", () => tocca(i));
    celle.push(b);
    griglia.append(b);
  }
  const ancora = document.createElement("button");
  ancora.type = "button";
  ancora.className = "ancora";
  ancora.textContent = "Ancora";
  ancora.addEventListener("click", () => { stato = nuovaPartita(); disegna(); });
  box.append(titolo, griglia, ancora);

  function disegna() {
    stato.celle.forEach((x, i) => { celle[i].textContent = x; celle[i].disabled = !!x || stato.finita; });
    if (stato.finita) {
      titolo.textContent = stato.vincitore ? (stato.vincitore === io ? "Hai vinto!" : "Ha vinto " + stato.vincitore) : "Pareggio";
    } else {
      titolo.textContent = stato.turno === io ? "Tocca a te (" + io + ")" : "Tocca a " + stato.turno;
    }
    ancora.hidden = !stato.finita;
  }

  function fine() {
    if (!stato.finita) return;
    if (stato.vincitore === io) record.vinte++; else if (stato.vincitore) record.perse++;
    calliope.salva("record", record).catch(() => {});
    if (stato.vincitore === io) calliope.di("Hai vinto a tris, brava!").catch(() => {});
    calliope.fine(stato.vincitore || "pareggio");
  }

  function tocca(i) {
    if (stato.finita || stato.turno !== io || stato.celle[i]) return;
    stato = mossa(stato, i);
    if (giocatori > 1) calliope.manda({ mossa: i });
    disegna();
    fine();
    if (giocatori === 1 && !stato.finita) {
      setTimeout(() => { stato = mossa(stato, mossaComputer(stato)); disegna(); fine(); }, 300);
    }
  }

  calliope.quandoPronto((a) => {
    giocatori = Math.max(1, a.giocatori || 1);
    io = a.giocatore === 2 ? "O" : "X";
    stato = nuovaPartita();
    (a.storia || []).forEach((m) => { if (m.dati && Number.isInteger(m.dati.mossa)) stato = mossa(stato, m.dati.mossa); });
    calliope.leggi("record").then((r) => { if (r) record = r; }).catch(() => {});
    disegna();
  });
  calliope.quandoGiocatori((g) => { giocatori = Math.max(giocatori, g.giocatori || 1); disegna(); });
  calliope.quandoMessaggio((m) => {
    if (m.dati && Number.isInteger(m.dati.mossa)) { stato = mossa(stato, m.dati.mossa); disegna(); fine(); }
  });
  disegna();
})();
