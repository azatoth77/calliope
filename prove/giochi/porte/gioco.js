// Apri le porte: a voce («la porta due», «ricomincia») o toccando. Dopo ogni mossa dice a
// Calliope quali comandi valgono adesso; le mosse ricevute (comando, giocatore e i campi
// arrivati) le salva per le prove
"use strict";
const radice = document.getElementById("gioco");
let stato = nuovaPartita("tre");
const ricevute = [];

function sicuro(f) {
  return (x) => { try { f(x); } catch (e) { radice.append(String(e.message)); } };
}

function disegna() {
  radice.replaceChildren();
  const t = document.createElement("p");
  t.className = "titolo";
  t.textContent = stato.finita ? "Trovato!" : "Quale porta apri?";
  radice.appendChild(t);
  PORTE.forEach((p) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "porta";
    b.dataset.porta = p;
    b.textContent = stato.aperte.includes(p) ? (p === stato.premio ? "★" : "—") : p;
    b.disabled = stato.finita || stato.aperte.includes(p);
    b.addEventListener("click", sicuro(() => mossa(p, null)));
    radice.appendChild(b);
  });
}

function mossa(comando, giocatore) {
  if (comando === "ricomincia") stato = nuovaPartita("tre");
  else stato = apri(stato, comando);
  calliope.comandiAttivi(comandiAdesso(stato));
  disegna();
}

calliope.quandoPronto(() => disegna());
calliope.quandoComando(sicuro((m) => {
  ricevute.push({ comando: m.comando, giocatore: m.giocatore || null, campi: Object.keys(m).sort() });
  calliope.salva("mosse", ricevute).catch(() => {});
  mossa(m.comando, m.giocatore);
}));
