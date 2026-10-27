// Calliope · lo schermo personale del PC a sezioni (27/10/2026, passo 1b di
// docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md, § 3.6; decisioni del 27/10 sera: solo
// sugli schermi personali, con «Parla»).
// La pagina degli schermi è la stessa per la TV della cucina e per il PC di una persona: quando
// schermo.js dice che lo schermo è personale (evento «calliope:pc»), qui si accendono le sezioni
// del telefono (sezioni.js) in colonne: a sinistra le sezioni e la voce con «Parla», al centro la
// sezione, a destra la conversazione sempre aperta con la casella per scrivere (sotto i 1100 px
// dietro un pulsante; sotto i 760 px la barra va in basso, come sul telefono). Le viste di
// schermo.js restano: la scheda a schermo intero (strato sopra la pagina), la vista dello
// sviluppo (in #principale, sopra la sezione), la modalità gioco.
// Tutto il testo che arriva dal server va in textContent: sono dati, mai HTML.
"use strict";

(function () {
  if (document.body.dataset.sezioni !== "1") return;
  const $ = (id) => document.getElementById(id);
  const sch = () => window.calliopeSchermo;
  const CHAT = "chat";
  let SEZ = null;
  let chatEl = null;                    // la scheda della conversazione nella colonna a destra
  let parlaTimer = null;

  function metti(el, testo) { if (el && el.textContent !== testo) el.textContent = testo; }

  function crea() {
    SEZ = window.CalliopeSezioni.crea({
      radice: () => $("pc"),
      chiaveVisti: "calliope.schermo.visti",
      // La conversazione sta nella sua colonna, non tra le sezioni
      escludi: (k, c) => c.tipo === "chat",
      aggiornata(k, c) { if (c.tipo === "chat") disegnaChat(); },
      tolta(k) { if (k === CHAT) disegnaChat(); },
    });
  }

  // La conversazione a destra: la scheda «chat» di schermo.js, allineata al suo posto quando
  // arrivano turni nuovi (resta in fondo solo se chi legge era in fondo)
  function disegnaChat() {
    const posto = $("pc-chat");
    // Dalla pagina, non dalla cronologia: lì la conversazione esce dopo 6 schede (revisione #255)
    const c = sch() && sch().schedaChat ? sch().schedaChat() : null;
    if (!c) {
      const p = document.createElement("p");
      p.className = "pc-nota pc-chat-vuota";
      p.textContent = "Qui c'è la nostra conversazione: le frasi dette e scritte, con le risposte.";
      posto.replaceChildren(p);
      chatEl = null;
      return;
    }
    const nuova = sch().costruisci(c);
    nuova.classList.add("pc-chat-scheda");
    if (chatEl && chatEl.isConnected && chatEl.dataset.chiave === nuova.dataset.chiave) {
      const seguite = sch().misuraSegui(chatEl);
      sch().allinea(chatEl, nuova);
      sch().ripristinaSegui(chatEl, seguite);
    } else {
      posto.replaceChildren(nuova);
      chatEl = nuova;
      sch().ripristinaSegui(nuova, null);
    }
  }

  // Lo schermo è personale (o non più): la disposizione a sezioni si accende o si spegne
  function suPc(d) {
    const attiva = !!(d && d.attiva);
    for (const id of ["barra", "pc-voce", "pc", "pc-conv"]) $(id).hidden = !attiva;
    if (!attiva) return;
    // Lo stato della voce in fondo alla colonna delle sezioni, sopra «Parla»
    const voce = $("voce");
    if (voce && voce.parentElement !== $("pc-voce")) $("pc-voce").prepend(voce);
    $("pc-parla").hidden = !d.parla;
    metti($("pc-nome"), d.nome || "—");
    metti($("pc-luogo"), d.luogo || "—");
    if (!SEZ) { crea(); SEZ.avvia(); }
    spostaScrivi();
    SEZ.sincronizza(null);
    disegnaChat();
  }

  // La casella per scrivere (di schermo.js) sotto la conversazione
  function spostaScrivi() {
    const f = $("scrivi");
    if (f && f.parentElement !== $("scrivi-posto")) $("scrivi-posto").append(f);
  }

  // `segnale` false: la stessa scheda ridisegnata (il cruscotto ogni 30 s), non aperta adesso
  function suMostra(c, segnale) {
    if (!SEZ) return;
    SEZ.sincronizza(null);
    if (c.tipo === "chat") { disegnaChat(); return; }
    // Il cruscotto aperto dal suo pulsante nella testa sta in Io: ci si va (revisione #255)
    // Solo quando si apre: il ridisegno ogni 30 s non deve riportare la pagina in Io (seconda
    // revisione della PR #255)
    if (c.tipo === "cruscotto") { if (segnale !== false) SEZ.vaiA(SEZ.chiaveDi(c)); return; }
    // Un gioco o gli esercizi che Calliope apre si usano subito: la loro sezione si apre da sola
    if (SEZ.apriSeServe(c)) return;
    if (performance.now() - SEZ.car.toccato > SEZ.opzioni.manoMs) SEZ.mostraIn(SEZ.chiaveDi(c), SEZ.vis.sezione);
  }

  // «Parla»: il satellite di questo PC ascolta senza il nome per qualche secondo
  async function parla() {
    const b = $("pc-parla"), esito = $("pc-parla-esito");
    if (!sch()) return;
    b.disabled = true;
    const r = await sch().parla();
    b.disabled = false;
    clearTimeout(parlaTimer);
    if (r.ok) {
      b.classList.add("in-corso");
      metti(b.querySelector(".parla-testo"), "Ti ascolto: parla pure");
      metti(esito, "");
      parlaTimer = setTimeout(() => {
        b.classList.remove("in-corso");
        metti(b.querySelector(".parla-testo"), "Parla");
      }, Math.max(1, r.secondi || 8) * 1000);
    } else {
      metti(esito, r.errore || "Non ci sono riuscita: riprova.");
    }
  }

  // «Pulisci le mie schede» (08/10): due tocchi, come sul telefono; c'era solo nella fila in
  // basso, che con le sezioni non c'è (revisione #255)
  let pulisciArmato = 0;
  async function pulisci() {
    const b = $("pc-pulisci"), esito = $("pc-pulisci-esito");
    if (Date.now() >= pulisciArmato) {
      pulisciArmato = Date.now() + 4000;
      metti(b, "Clicca di nuovo per pulire");
      setTimeout(() => { if (Date.now() >= pulisciArmato) metti(b, "Pulisci le mie schede"); }, 4100);
      return;
    }
    pulisciArmato = 0;
    b.disabled = true;
    const r = sch() ? await sch().pulisci() : { ok: false };
    b.disabled = false;
    metti(b, "Pulisci le mie schede");
    metti(esito, r.ok ? (r.frase || "Schede tolte.") : (r.errore || "Non ci sono riuscita: riprova."));
  }

  // Sotto i 1100 px la conversazione si apre e si chiude col suo pulsante, sopra la pagina come
  // un dialogo; chiusa, il fuoco torna al pulsante
  function conversazione(aperta) {
    const prima = document.body.classList.contains("conv-aperta");
    document.body.classList.toggle("conv-aperta", aperta);
    $("pc-conv-apri").setAttribute("aria-expanded", aperta ? "true" : "false");
    const sopra = getComputedStyle($("pc-conv")).position === "fixed";
    if (sopra && aperta) { $("pc-conv").setAttribute("role", "dialog"); $("pc-conv").setAttribute("aria-modal", "true"); }
    else { $("pc-conv").removeAttribute("role"); $("pc-conv").removeAttribute("aria-modal"); }
    if (aperta) { const ch = $("pc-conv-chiudi"); if (ch) ch.focus({ preventScroll: true }); }
    else if (prima) { try { $("pc-conv-apri").focus({ preventScroll: true }); } catch (e) { /* niente */ } }
  }

  document.addEventListener("calliope:pc", (ev) => suPc(ev.detail));
  document.addEventListener("calliope:schede", (ev) => { if (SEZ) SEZ.sincronizza(ev.detail); });
  document.addEventListener("calliope:mostra", (ev) => { if (ev.detail && ev.detail.scheda) suMostra(ev.detail.scheda, ev.detail.segnale); });
  document.addEventListener("calliope:nascoste", (ev) => { if (SEZ) SEZ.applicaNascoste(ev.detail); });
  document.addEventListener("calliope:aspetto", (ev) => window.CalliopeSezioni.disegnaAccenti(ev.detail, $("accenti"), $("io-aspetto")));
  document.addEventListener("calliope:scrivi", () => requestAnimationFrame(spostaScrivi));
  // La conversazione disponibile o con turni nuovi: nella sua colonna
  document.addEventListener("calliope:chat", () => { if (SEZ) disegnaChat(); });
  document.addEventListener("calliope:chatturni", () => { if (SEZ) disegnaChat(); });
  // Un gioco chiuso esce subito da Adesso
  document.addEventListener("calliope:gioco", (ev) => { if (SEZ && !(ev.detail || {}).partita) requestAnimationFrame(() => SEZ.disponi()); });

  document.addEventListener("DOMContentLoaded", () => {
    $("pc-parla").addEventListener("click", parla);
    $("pc-pulisci").addEventListener("click", pulisci);
    $("accenti").addEventListener("click", (ev) => window.CalliopeSezioni.suAccento(ev, $("accento-esito")));
    $("pc-conv-apri").addEventListener("click", () => conversazione(!document.body.classList.contains("conv-aperta")));
    $("pc-conv-chiudi").addEventListener("click", () => conversazione(false));
    $("sezioni").addEventListener("click", (ev) => {
      const t = ev.target;
      const r = t.closest && t.closest("#sezioni [data-rimando]");
      if (r && SEZ) SEZ.vaiA(r.dataset.chiave);
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape" && document.body.classList.contains("conv-aperta")) conversazione(false);
    });
  });

  // Per le prove: dove sta ogni scheda
  window.calliopePC = {
    stato: () => SEZ ? SEZ.stato() : null,
    vai: (h) => SEZ && SEZ.vai(h),
    vaiA: (k) => SEZ && SEZ.vaiA(k),
    chat: () => !!chatEl,
  };
})();
