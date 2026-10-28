// Calliope · le sezioni degli schermi personali (27/10/2026): Adesso, Conversazione, Le mie cose,
// Casa, Io. docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md, passi 1 e 1b.
// Lo usano il telefono (telefono/telefono.js) e la pagina degli schermi su uno schermo personale
// (pc.js): le schede le tiene schermo.js (sessione, cronologia, disegno); qui si smistano. Ognuna
// va nella sua sezione (`sezione` dal server, o SEZIONE_DI_TIPO), la più recente per prima, e
// quelle vive (il timer corre, il lavoro non è finito, il modulo è da compilare: `viva`) compaiono
// anche in Adesso. Una scheda aggiornata (stessa chiave) si allinea al suo posto, senza
// ricostruirla né spostarla. Ogni vista ha il suo indirizzo nel frammento (#/cose/liste), e il
// gesto indietro torna alla vista di prima.
// Ciò che cambia da una pagina all'altra arriva in `opz`: come si costruisce una scheda
// nell'elenco, cosa fare quando una scheda cambia o sparisce (gli strati del telefono, la vista
// dello sviluppo), prima di cambiare sezione e dopo aver disposto le schede.
// Tutto il testo che arriva dal server va in textContent: sono dati, mai HTML.
"use strict";

(function () {
  const TITOLI_SEZIONE = { adesso: "Adesso", conversazione: "Conversazione", cose: "Le mie cose", casa: "Casa", io: "Io" };
  // In Adesso non si copiano (un gioco o un esercizio aperti due volte, con due stati; la voce
  // nuova ha i suoi campi): un rimando con «Apri», che porta alla scheda nella sua sezione
  const TIPI_RIMANDO = new Set(["gioco", "esercizio", "esercizi_riepilogo", "sviluppo", "cassetto", "chat",
    "conoscente"]);
  // Questi, quando Calliope li mostra, aprono la loro sezione: si usano con le mani
  const TIPI_APRONO = new Set(["gioco", "esercizio"]);
  // In Adesso sotto «Aspetta te» invece che «In corso»
  const ASPETTA_TE = (c) => c.tipo === "modulo" || c.tipo === "conoscente" || c.tipo === "avviso"
    || (c.tipo === "lavoro" && c.stato === "in_attesa");
  const fmtOra = new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit" });
  const sch = () => window.calliopeSchermo;
  const $ = (id) => document.getElementById(id);
  // Scrive solo se cambia: i giri frequenti non toccano il DOM per niente
  function metti(el, testo) { if (el && el.textContent !== testo) el.textContent = testo; }
  function attr(el, k, v) { if (el && el.getAttribute(k) !== v) el.setAttribute(k, v); }
  function leggi(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function scrivi(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* niente */ } }

  function crea(opz) {
    opz = opz || {};
    const radice = () => opz.radice ? opz.radice() : document.body;
    const car = {
      seq: {},                  // chiave → ordine (più grande = più recente)
      n: 0,
      schede: {},               // chiave → dati della scheda
      el: {},                   // chiave → {casa, adesso}: l'elemento nella sua sezione e quello in Adesso
      toccato: -1e9,            // ultimo scorrimento a mano (performance.now)
      aperte: new Set(),        // giochi ed esercizi già aperti da Calliope (non si riaprono a ogni mossa)
      novita: { conversazione: new Set(), cose: new Set(), casa: new Set() },
      visti: new Set(),         // gli avvisi già guardati (non restano più in Adesso)
    };
    const vis = {
      sezione: "adesso", percorso: ["adesso"],
      modo: "sezioni",          // «auto» sul telefono in auto: solo Adesso, niente barra
      // Sul satellite di un minore (27/10, decisione 2): sezioni e raccolte da non mostrare, dal server
      nascoste: { sezioni: [], raccolte: [] },
    };
    const opzioni = { manoMs: 10000, recenteS: 600, rinfrescaMs: 1500, rinfrescaMinMs: 10000 };
    try { for (const k of JSON.parse(leggi(opz.chiaveVisti) || "[]")) car.visti.add(String(k)); } catch (e) { /* niente */ }

    function chiaveDi(c) { return c.chiave || c.id; }
    // Una scheda di una sezione o di una raccolta nascosta va nella conversazione: niente sparisce
    function sezioneDi(c) {
      const s = sch() ? sch().sezioneDi(c) : "conversazione";
      const [sez, racc] = s.split("/");
      return vis.nascoste.sezioni.includes(sez) || (racc && vis.nascoste.raccolte.includes(racc)) ? "conversazione" : s;
    }

    function etichettaOra(s, c) {
      const et = s.querySelector(".etichetta");
      if (et && c.creata && !et.querySelector(".quando")) {
        const q = document.createElement("span");
        q.className = "quando";
        q.textContent = fmtOra.format(new Date(c.creata * 1000));
        et.append(q);
      }
    }

    // La scheda nell'elenco: quella della pagina (opz.costruisci) o quella di schermo.js con l'ora
    function costruisciScheda(c) {
      if (opz.costruisci) return opz.costruisci(c);
      const s = sch().costruisci(c);
      s.classList.add("pagina-car");
      s.setAttribute("aria-roledescription", "scheda");
      etichettaOra(s, c);
      return s;
    }

    // In Adesso, per i tipi che non si copiano: tipo, titolo e «Apri»
    function costruisciRimando(c) {
      const s = document.createElement("article");
      s.className = "scheda pagina-car rimando-car tipo-" + c.tipo;
      s.dataset.chiave = chiaveDi(c);
      s.dataset.rimando = "1";
      s.setAttribute("aria-roledescription", "scheda");
      const et = document.createElement("div");
      et.className = "etichetta";
      et.textContent = sch().NOMI_TIPO[c.tipo] || c.tipo;
      const h = document.createElement("h1");
      h.className = "titolo";
      h.textContent = c.titolo || "";
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tasto apri-rimando";
      b.textContent = "Apri";
      b.setAttribute("aria-label", "Apri in " + TITOLI_SEZIONE[sezioneDi(c).split("/")[0]] + ": " + (c.titolo || et.textContent));
      s.append(et, h, b);
      etichettaOra(s, c);
      return s;
    }

    // Costruisce o allinea al suo posto l'elemento di una scheda (stessi nodi, stesso scorrimento)
    function aggiornaElemento(el, c, vecchia, rimando) {
      const nuova = rimando ? costruisciRimando(c) : costruisciScheda(c);
      if (!el) { sch().ripristinaSegui(nuova, null); return nuova; }
      if (vecchia && vecchia.tipo === c.tipo && c.tipo !== "esercizio") {
        const seguite = sch().misuraSegui(el);
        sch().allinea(el, nuova);
        sch().ripristinaSegui(el, seguite);
        return el;
      }
      el.replaceWith(nuova);
      sch().ripristinaSegui(nuova, null);
      return nuova;
    }

    // L'ultima scheda della conversazione (biblioteca, internet, un calcolo…) è l'ultima risposta:
    // sta in Adesso sotto il testo, finché è recente
    function ultimaConversazione() {
      let best = null;
      for (const [k, c] of Object.entries(car.schede)) {
        if (c.tipo === "chat" || sezioneDi(c).split("/")[0] !== "conversazione") continue;
        if (!best || (car.seq[k] || 0) > (car.seq[best] || 0)) best = k;
      }
      if (!best) return null;
      const c = car.schede[best];
      return (Number(c.creata) || 0) > Date.now() / 1000 - opzioni.recenteS ? best : null;
    }

    // Dove va ogni scheda: [posto nella sua sezione, posto in Adesso o null]
    function postiDi(k, ultima) {
      const c = car.schede[k];
      // Una scheda che la pagina mostra altrove (la conversazione nella colonna a destra del PC)
      if (opz.escludi && opz.escludi(k, c)) return [null, null];
      // Una scheda che la sua sezione mostra già altrove (28/10, #242: dentro un turno della
      // conversazione sul telefono): non nell'elenco, ma in Adesso come prima
      const casa = opz.fuoriDaCasa && opz.fuoriDaCasa(k, c) ? null : sezioneDi(c);
      let adesso = null;
      if (k === ultima) adesso = "adesso/risposta";
      else if (sch().viva(c) && !(c.tipo === "avviso" && car.visti.has(k))) adesso = ASPETTA_TE(c) ? "adesso/aspetta" : "adesso/corso";
      return [casa, adesso];
    }

    function posto(nome) {
      return document.querySelector('#sezioni [data-posto="' + CSS.escape(nome) + '"]')
        || document.querySelector('#sezioni [data-posto="' + CSS.escape(nome.split("/")[0]) + '"]');
    }

    // Mette ogni elemento nel suo elenco, il più recente per primo; nasconde i gruppi vuoti
    function disponi() {
      const ultima = ultimaConversazione();
      const elenchi = new Map();
      for (const k of Object.keys(car.schede)) {
        const [casa, adesso] = postiDi(k, ultima);
        const e = car.el[k] || (car.el[k] = { casa: null, adesso: null });
        for (const [chi, dove] of [["casa", casa], ["adesso", adesso]]) {
          const box = dove ? posto(dove) : null;
          if (!box) {
            if (e[chi]) { e[chi].remove(); e[chi] = null; }
            continue;
          }
          if (!e[chi]) e[chi] = aggiornaElemento(null, car.schede[k], null, chi === "adesso" && TIPI_RIMANDO.has(car.schede[k].tipo));
          if (!elenchi.has(box)) elenchi.set(box, []);
          elenchi.get(box).push([car.seq[k] || 0, e[chi]]);
        }
      }
      for (const box of document.querySelectorAll("#sezioni [data-posto]")) {
        const fila = (elenchi.get(box) || []).sort((a, b) => b[0] - a[0]).map((x) => x[1]);
        // In fila solo dove serve: spostare un elemento ne azzera lo scorrimento interno
        fila.forEach((el, i) => { if (box.children[i] !== el) box.insertBefore(el, box.children[i] || null); });
        for (const x of [...box.children]) if (!fila.includes(x)) x.remove();
        const r = box.closest(".raccolta");
        if (r) r.hidden = !fila.length;
        const g = box.previousElementSibling;
        if (g && g.matches("h2.gruppo[data-gruppo]")) g.hidden = !fila.length;
      }
      for (const s of document.querySelectorAll("#sezioni .sezione")) {
        const v = s.querySelector(".vuoto-sez");
        if (v) v.hidden = !!s.querySelector("[data-posto] > *, .tessere > *, .conv-tel:not([hidden]) > *");
      }
      disegnaNovita();
      if (opz.dopoDisponi) opz.dopoDisponi();
    }

    // Le schede di schermo.js nelle sezioni: nuove, aggiornate al loro posto, tolte
    function sincronizza(det) {
      const lista = sch() ? sch().cronologia() : [];
      const viste = new Set();
      const spostata = det && det.scheda && det.spostata ? chiaveDi(det.scheda) : null;
      // La scheda appena arrivata dal flusso, non quella della cronologia ripresa al (ri)collegamento
      const arrivata = det && det.scheda && !det.ripresa ? chiaveDi(det.scheda) : null;
      if (spostata) car.seq[spostata] = ++car.n;
      for (const c of lista) {
        const k = chiaveDi(c);
        viste.add(k);
        const nuova = !(k in car.seq);
        if (nuova) car.seq[k] = ++car.n;
        const vecchia = car.schede[k];
        car.schede[k] = c;
        // Una novità sulla sezione (il pallino nella barra) se arriva mentre si guarda altrove
        if (k === arrivata && (nuova || k === spostata)) segnaNovita(k, c);
        const e = car.el[k];
        if (e && vecchia !== c) {
          for (const chi of ["casa", "adesso"]) {
            if (e[chi]) e[chi] = aggiornaElemento(e[chi], c, vecchia, chi === "adesso" && TIPI_RIMANDO.has(c.tipo));
          }
        }
        if (vecchia !== c && opz.aggiornata) opz.aggiornata(k, c);
      }
      if (opz.dopoSincronizza) opz.dopoSincronizza(det, lista);
      for (const k of Object.keys(car.schede)) {
        if (viste.has(k)) continue;
        delete car.schede[k];
        const e = car.el[k];
        if (e) { for (const x of [e.casa, e.adesso]) if (x) x.remove(); delete car.el[k]; }
        for (const s of Object.values(car.novita)) s.delete(k);
        if (opz.tolta) opz.tolta(k, lista);
      }
      if (sch()) sch().aggiorna();          // timer e tempi dei lavori subito, non al giro dopo
      disponi();
      raccolteDopoSchede(det);
    }

    // Non è una novità ciò che si vede già: la sezione aperta, o Adesso quando la scheda è lì
    function segnaNovita(k, c) {
      const s = sezioneDi(c).split("/")[0];
      if (!(s in car.novita) || (s === vis.sezione && vis.modo === "sezioni")) return;
      if (vis.sezione === "adesso" && postiDi(k, ultimaConversazione())[1]) return;
      car.novita[s].add(k);
    }

    function disegnaNovita() {
      for (const a of document.querySelectorAll("#barra a[data-sezione]")) {
        const s = a.dataset.sezione;
        const n = car.novita[s] ? car.novita[s].size : 0;
        const b = a.querySelector(".novita");
        if (!b) continue;
        b.hidden = !n;
        metti(b, n ? String(n) : "");
        attr(a, "aria-label", TITOLI_SEZIONE[s] + (n ? ", " + n + " novità" : ""));
      }
    }

    // Un gioco o gli esercizi che Calliope apre si usano subito: la loro sezione si apre da sola,
    // una volta sola per scheda (il gioco va a tutta la finestra, 11/10: schermo.js ci entra
    // appena dopo, e una scheda in una sezione nascosta non la prende). true se se ne è occupato
    function apriSeServe(c) {
      const k = chiaveDi(c);
      if (!TIPI_APRONO.has(c.tipo)) return false;
      if (!sch().viva(c)) { car.aperte.delete(k); return false; }
      if (car.aperte.has(k)) return true;
      car.aperte.add(k);
      const p = sezioneDi(c);
      if (vis.sezione !== p.split("/")[0]) vai("#/" + p);
      mostraIn(k, vis.sezione);
      return true;
    }

    // Porta in vista l'elemento di una scheda nella sezione indicata, se c'è
    function mostraIn(k, sezione) {
      const e = car.el[k];
      const el = e && (sezione === "adesso" ? e.adesso : (e.casa && e.casa.closest('.sezione[data-sezione="' + sezione + '"]') ? e.casa : null));
      // (anche nascosta dal CSS: il gruppo della raccolta sotto la sua pagina, dal 28/10)
      if (!el || el.closest("[hidden]") || !el.getClientRects().length) return false;
      try { el.scrollIntoView({ block: "nearest", behavior: "instant" }); } catch (e2) { el.scrollIntoView(); }
      return true;
    }

    // Apre la sezione di una scheda e la mostra (l'«Apri» di un rimando, il server domani)
    function vaiA(k) {
      const c = car.schede[k];
      if (!c) return false;
      const p = sezioneDi(c);
      // Una raccolta con la sua pagina (28/10: le Liste): la scheda sta lì, con il suo indirizzo
      const t = p.split("/")[1] ? tessera(p.split("/")[1]) : null;
      if (t && t.pagina) { vai("#/" + p + "/" + encodeURIComponent(k)); return true; }
      vai("#/" + p);
      requestAnimationFrame(() => mostraIn(k, p.split("/")[0]));
      return true;
    }

    // ── router sul frammento: #/adesso, #/conversazione, #/cose/liste, #/casa, #/io ──
    function percorsoDa(hash) {
      const parti = String(hash || "").replace(/^#\/?/, "").split("/").filter(Boolean).map((x) => decodeURIComponent(x));
      if (!parti.length || !(parti[0] in TITOLI_SEZIONE) || vis.nascoste.sezioni.includes(parti[0])) return ["adesso"];
      return parti;
    }

    function vai(hash, sostituisci) {
      const p = percorsoDa(hash);
      const nuovo = "#/" + p.map(encodeURIComponent).join("/");
      // Uno strato della pagina con una sua voce nella cronologia del browser (la scheda a schermo
      // intero del telefono) si chiude e la sua voce si sostituisce: resterebbe una voce morta
      const sua = !!(opz.primaDiVai && opz.primaDiVai());
      if (sua) sostituisci = true;
      if (location.hash === nuovo) { applicaPercorso(); return; }
      try {
        // Lo stato dello strato chiuso non passa alla sezione nuova (il gesto indietro dopo non la
        // riconoscerebbe come sua: seconda revisione della PR #252)
        if (sostituisci) history.replaceState(sua ? null : history.state, "", nuovo);
        else history.pushState(null, "", nuovo);
      } catch (e) { location.hash = nuovo; return; }
      applicaPercorso();
    }

    function applicaPercorso() {
      const p = percorsoDa(location.hash);
      const prima = vis.sezione;
      vis.percorso = p;
      vis.sezione = p[0];
      const v = radice();
      if (v && v.dataset.sezione !== vis.sezione) v.dataset.sezione = vis.sezione;
      for (const s of document.querySelectorAll("#sezioni .sezione")) {
        s.hidden = vis.modo === "auto" ? s.dataset.sezione !== "adesso" : s.dataset.sezione !== vis.sezione;
      }
      metti($("sez-titolo"), vis.modo === "auto" ? "In auto" : TITOLI_SEZIONE[vis.sezione]);
      for (const a of document.querySelectorAll("#barra a[data-sezione]")) {
        if (a.dataset.sezione === vis.sezione) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
      }
      // Il gesto indietro durante un gioco (la sua scheda sta in Le mie cose) lo chiude, come ✕
      if (vis.sezione !== "cose" && sch() && sch().gioco && sch().gioco().partita) sch().chiudiGioco();
      // Guardare la sezione toglie le sue novità; in Casa gli avvisi diventano visti
      if (vis.modo === "sezioni" && car.novita[vis.sezione]) car.novita[vis.sezione].clear();
      if (vis.modo === "sezioni" && vis.sezione === "casa") segnaVisti();
      // #/cose/liste: la raccolta in vista; un percorso più lungo (#/cose/liste/lista:spesa) la scheda
      if (p.length > 1 && vis.modo === "sezioni") {
        requestAnimationFrame(() => {
          const chiave = p.slice(2).join("/");
          if (chiave && mostraIn(chiave, vis.sezione)) return;
          const r = document.querySelector('#sez-' + vis.sezione + ' [data-raccolta="' + CSS.escape(p[1]) + '"]');
          if (r && !r.hidden) r.scrollIntoView({ block: "start", behavior: "instant" });
        });
      } else if (prima !== vis.sezione) {
        const s = $("sez-" + vis.sezione);
        if (s) s.scrollTop = 0;
      }
      disponi();
      raccolteVista();
    }

    // ── le tessere e le pagine di «Le mie cose» (28/10, passo 2a: POST /api/raccolte) ──
    // In cima a Le mie cose le tessere (conto, stato, il pallino se è cambiato qualcosa dopo
    // l'ultima visita), lette dal server all'ingresso nella sezione e ogni 60 s mentre è aperta.
    // Un tocco su una tessera con la sua pagina apre #/cose/<id>: le schede che dà il server
    // (dai servizi: anche ciò che non è passato da questo schermo), disegnate da schermo.js; il
    // gesto indietro torna alle tessere. Le altre tessere dicono «presto» e portano, come prima,
    // al gruppo delle schede di quella raccolta.
    const racc = { tessere: [], timer: null, aperta: null, richiesta: 0, daTessere: false, rinfresca: null, rinfrescata: 0,
      cerca: "", riprova: null };
    // Le pagine con la ricerca (28/10, passo 2d: i Documenti; 2e: l'Ufficio, POST
    // /api/raccolte/cerca; le stesse di raccolte.CON_RICERCA), con il suggerimento della casella
    const CON_RICERCA = new Set(["documenti", "ufficio"]);
    const SUGGERIMENTO_RICERCA = {
      documenti: ["Cerca nei documenti", "Cerca: bolletta, garanzia, lettera…"],
      ufficio: ["Cerca nell'ufficio", "Cerca: cliente, numero, comune…"],
    };
    const CHIAVE_RACC = opz.chiaveRaccolte || "calliope.raccolte.viste";
    function vistePrima() {
      try {
        const v = JSON.parse(leggi(CHIAVE_RACC) || "{}");
        return v && typeof v === "object" ? v : {};
      } catch (e) { return {}; }
    }
    // L'ultima visita di una tessera è il suo «ultimo» di allora (l'ora del server: niente
    // orologi diversi). Una tessera mai vista prende quello di adesso: niente pallini ovunque
    // alla prima apertura
    function segnaVista(t) {
      const v = vistePrima();
      if (v[t.id] === (Number(t.ultimo) || 0)) return;
      v[t.id] = Number(t.ultimo) || 0;
      scrivi(CHIAVE_RACC, JSON.stringify(v));
    }
    function nuovaTessera(id) {
      const a = document.createElement("a");
      a.className = "tessera";
      a.dataset.tessera = id;
      a.href = "#/cose/" + encodeURIComponent(id);
      const testa = document.createElement("span");
      testa.className = "tessera-testa";
      const nome = document.createElement("span");
      nome.className = "tessera-nome";
      const pallino = document.createElement("span");
      pallino.className = "tessera-pallino";
      pallino.setAttribute("aria-hidden", "true");
      testa.append(nome, pallino);
      const conto = document.createElement("span");
      conto.className = "tessera-conto";
      const stato = document.createElement("span");
      stato.className = "tessera-stato";
      a.append(testa, conto, stato);
      a.addEventListener("click", (ev) => {
        ev.preventDefault();
        racc.daTessere = true;
        vai("#/cose/" + encodeURIComponent(id));
      });
      return a;
    }
    function disegnaTessere() {
      const box = $("tessere");
      if (!box) return;
      const v = vistePrima();
      let nuove = false;
      const fila = [];
      for (const t of racc.tessere) {
        if (!t || typeof t.id !== "string" || vis.nascoste.raccolte.includes(t.id)) continue;
        if (!(t.id in v)) { v[t.id] = Number(t.ultimo) || 0; nuove = true; }
        const a = box.querySelector('[data-tessera="' + CSS.escape(t.id) + '"]') || nuovaTessera(t.id);
        const novita = (Number(t.ultimo) || 0) > (Number(v[t.id]) || 0);
        const conto = t.conto === null || t.conto === undefined ? "—" : String(t.conto);
        const stato = String(t.stato || "") + (t.pagina ? "" : " · pagina presto");
        const nome = String(t.nome || t.id);
        metti(a.querySelector(".tessera-nome"), nome);
        metti(a.querySelector(".tessera-conto"), conto);
        metti(a.querySelector(".tessera-stato"), stato);
        a.querySelector(".tessera-pallino").hidden = !novita;
        a.classList.toggle("presto", !t.pagina);
        attr(a, "aria-label", nome + ": " + (conto === "—" ? "" : conto + ", ") + stato + (novita ? ", novità" : ""));
        fila.push(a);
      }
      if (nuove) scrivi(CHIAVE_RACC, JSON.stringify(v));
      fila.forEach((a, i) => { if (box.children[i] !== a) box.insertBefore(a, box.children[i] || null); });
      for (const x of [...box.children]) if (!fila.includes(x)) x.remove();
    }
    function tessera(id) { return racc.tessere.find((t) => t && t.id === id) || null; }
    async function aggiornaRaccolte() {
      if (!sch() || !sch().raccolte) return;
      const prima = racc.aperta;
      const r = await sch().raccolte({});
      if (!r.ok || !Array.isArray(r.dati.tessere)) return;
      racc.tessere = r.dati.tessere;
      disegnaTessere();
      raccolteVista();
      if (prima && racc.aperta === prima) caricaPagina(prima);
      disponi();
    }
    // La vista di Le mie cose secondo l'indirizzo: le tessere (#/cose) o la pagina (#/cose/liste)
    function raccolteVista() {
      const sez = $("sez-cose"), box = $("tessere"), pag = $("pagina-racc");
      if (!sez || !box || !pag) return;
      const dentro = vis.modo === "sezioni" && vis.sezione === "cose";
      if (!dentro) {
        if (racc.timer) { clearInterval(racc.timer); racc.timer = null; }
        racc.aperta = null;
        return;
      }
      if (!racc.timer) {
        racc.timer = setInterval(aggiornaRaccolte, 60000);
        aggiornaRaccolte();
      }
      const id = vis.percorso[1] || null;
      const t = id ? tessera(id) : null;
      const pagina = !!(t && t.pagina && !vis.nascoste.raccolte.includes(id));
      const vista = pagina ? "pagina" : "tessere";
      if (sez.dataset.vista !== vista) sez.dataset.vista = vista;
      // Quale pagina (28/10, #258): in Giochi il gruppo delle schede «gioco» di questo schermo resta
      // visibile sotto la pagina (il riquadro è uno solo, e un gioco che arriva ci si apre)
      const qualePagina = pagina ? id : "";
      if ((sez.dataset.pagina || "") !== qualePagina) {
        if (qualePagina) sez.dataset.pagina = qualePagina; else delete sez.dataset.pagina;
      }
      pag.hidden = !pagina;
      box.hidden = pagina || !box.children.length;
      if (!pagina) { racc.aperta = null; return; }
      segnaVista(t);
      disegnaTessere();
      if (racc.aperta !== id) {
        racc.aperta = id;
        racc.cerca = "";
        metti($("pagina-titolo"), String(t.nome || id));
        // Le schede dell'altra pagina restano finché arriva la risposta, ma nascoste e segnate
        // «occupate» (revisione della PR #269: prima la pagina si svuotava subito, e un 429 la
        // lasciava vuota); caricaPagina le sostituisce
        const box = $("pagina-schede");
        box.dataset.di = "";
        box.hidden = true;
        box.setAttribute("aria-busy", "true");
        disegnaRicerca();
        caricaPagina(id);
      } else requestAnimationFrame(scorriAllaScheda);
    }
    // #/cose/liste/lista:spesa: la scheda in vista nella pagina
    function scorriAllaScheda() {
      const chiave = vis.percorso.slice(2).join("/");
      const box = $("pagina-schede");
      let el = chiave && box ? [...box.children].find((e) => e.dataset.chiave === chiave) : null;
      // Una scheda del gruppo che resta sotto la pagina (il gioco in Giochi)
      const casa = chiave && car.el[chiave] ? car.el[chiave].casa : null;
      if (!el && casa && casa.closest("#sez-cose") && casa.getClientRects().length) el = casa;
      if (el) { try { el.scrollIntoView({ block: "nearest", behavior: "instant" }); } catch (e) { el.scrollIntoView(); } }
    }
    async function caricaPagina(id, ripresa) {
      const n = ++racc.richiesta;
      const cercato = CON_RICERCA.has(id) ? racc.cerca : "";
      const r = cercato && sch().cerca ? await sch().cerca({ raccolta: id, testo: cercato })
        : await sch().raccolte({ raccolta: id });
      if (n !== racc.richiesta || racc.aperta !== id || (CON_RICERCA.has(id) ? racc.cerca : "") !== cercato) return;
      const box = $("pagina-schede"), nota = $("pagina-nota");
      if (!r.ok && r.status === 429 && !ripresa) {
        // Troppe letture (revisione della PR #269): lo dice e riprova da sola, una volta, dopo i
        // secondi di Retry-After; intanto la pagina resta com'era
        const s = Math.min(Math.max(Number(r.riprova || (r.dati && r.dati.riprova_s)) || 5, 1), 60);
        metti($("pagina-esito"), String(r.dati.errore || "Troppe richieste in poco tempo: riprovo fra qualche secondo."));
        clearTimeout(racc.riprova);
        racc.riprova = setTimeout(() => {
          if (racc.aperta === id && n === racc.richiesta) caricaPagina(id, true);
        }, s * 1000);
        return;
      }
      if (box.dataset.di !== id) {
        // La prima risposta della pagina appena aperta (anche un errore): via le schede dell'altra
        box.replaceChildren();
        box.dataset.di = r.ok ? id : "";
        box.hidden = false;
        box.removeAttribute("aria-busy");
      }
      if (!r.ok) {
        metti($("pagina-esito"), String(r.dati.errore || (cercato ? "Non riesco a cercare adesso: riprova tra poco."
          : "Non riesco a leggere questa pagina: riprova tra poco.")));
        return;
      }
      metti($("pagina-esito"), "");
      const schede = Array.isArray(r.dati.schede) ? r.dati.schede.filter((c) => c && typeof c === "object") : [];
      const vecchie = new Map([...box.children].filter((e) => e.dataset.chiave).map((e) => [e.dataset.chiave, e]));
      const nuove = [];
      let gruppo = "";
      for (const c of schede) {
        // Il titolo del gruppo sopra la sua prima scheda (28/10, #259: «Fatti da Calliope per te»,
        // «Archivio di casa», «Lavori di …» per chi amministra): solo testo
        const g = typeof c.gruppo === "string" ? c.gruppo : "";
        if (g && g !== gruppo) {
          const h = document.createElement("h3");
          h.className = "gruppo-pagina";
          h.textContent = g;
          nuove.push(h);
        }
        gruppo = g;
        const e = vecchie.get(String(chiaveDi(c)));
        const s = costruisciScheda(c);
        if (e) { sch().allinea(e, s); nuove.push(e); } else nuove.push(s);
      }
      box.replaceChildren(...nuove);
      const testo = r.dati.nota ? String(r.dati.nota) : (schede.length ? "" : "Niente qui, per ora.");
      metti(nota, testo);
      nota.hidden = !testo;
      scorriAllaScheda();
    }
    // La casella della ricerca (28/10, #259): solo nelle pagine che la hanno; il testo resta
    // nella pagina finché la si cambia o si tocca «Tutti»; le riletture rifanno la ricerca
    function disegnaRicerca() {
      const f = $("pagina-cerca");
      if (!f) return;
      const si = !!racc.aperta && CON_RICERCA.has(racc.aperta);
      f.hidden = !si;
      const i = $("pagina-cerca-testo"), via = $("pagina-cerca-via");
      const sugg = SUGGERIMENTO_RICERCA[racc.aperta];
      if (i && sugg) { i.setAttribute("aria-label", sugg[0]); i.placeholder = sugg[1]; }
      if (i && !racc.cerca) i.value = "";
      if (via) via.hidden = !racc.cerca;
    }
    const formCerca = $("pagina-cerca");
    if (formCerca) {
      formCerca.addEventListener("submit", (ev) => {
        ev.preventDefault();
        if (!racc.aperta || !CON_RICERCA.has(racc.aperta)) return;
        const i = $("pagina-cerca-testo");
        racc.cerca = String(i ? i.value : "").trim().slice(0, 120);
        disegnaRicerca();
        caricaPagina(racc.aperta);
      });
      const via = $("pagina-cerca-via");
      if (via) via.addEventListener("click", () => {
        racc.cerca = "";
        disegnaRicerca();
        if (racc.aperta) caricaPagina(racc.aperta);
      });
    }
    // Una scheda arrivata (la lista aggiornata da un tocco o a voce): nella pagina aperta si
    // allinea al suo posto; le tessere (e la pagina aperta, che così prende anche le schede che non
    // aveva) si rileggono poco dopo, una volta per raffica e al più una ogni `rinfrescaMinMs`
    // (revisione della PR #267: le schede in diretta di un lavoro arrivano ogni pochi secondi, e una
    // raffica di programmi rileggeva la pagina per ogni scheda, fino al limite di 30 letture al minuto)
    function raccolteDopoSchede(det) {
      if (!$("tessere") || vis.sezione !== "cose") return;
      const c = det && det.scheda;
      if (c) {
        const sez = sezioneDi(c);
        if (racc.aperta && sez === "cose/" + racc.aperta) {
          const box = $("pagina-schede");
          const e = [...box.children].find((x) => x.dataset.chiave === String(chiaveDi(c)));
          if (e) sch().allinea(e, costruisciScheda(c));
        }
        if (sez.split("/")[0] !== "cose") return;
      } else if (racc.tessere.length) return;
      // Le tessere poco dopo; anche la prima volta, se si è entrati prima della sessione
      if (racc.rinfresca) return;
      const attesa = Math.max(opzioni.rinfrescaMs, opzioni.rinfrescaMinMs - (Date.now() - racc.rinfrescata));
      racc.rinfresca = setTimeout(() => {
        racc.rinfresca = null;
        racc.rinfrescata = Date.now();
        aggiornaRaccolte();
      }, attesa);
    }
    function tornaAlleTessere() {
      if (racc.daTessere) { racc.daTessere = false; history.back(); return; }
      vai("#/cose", true);
    }
    // Un tasto del cassetto riuscito (2d, seconda revisione della PR #267): la pagina Cassetto
    // aperta si rilegge subito, fuori dall'attesa delle schede
    document.addEventListener("calliope:cassetto", () => {
      if (racc.aperta === "cassetto" && sch() && sch().raccolte) caricaPagina("cassetto");
    });
    const indietro = $("pagina-indietro");
    if (indietro) indietro.addEventListener("click", tornaAlleTessere);

    function segnaVisti() {
      let cambia = false;
      for (const [k, c] of Object.entries(car.schede)) {
        if (c.tipo === "avviso" && !car.visti.has(k)) { car.visti.add(k); cambia = true; }
      }
      if (!cambia || !opz.chiaveVisti) return;
      scrivi(opz.chiaveVisti, JSON.stringify([...car.visti].slice(-100)));
    }

    // Le sezioni nascoste sul satellite di un minore (27/10: Casa sotto i 13 anni, Ufficio
    // sempre): le dice il server a ogni accesso; la barra perde la voce e le schede vanno in
    // Conversazione
    function applicaNascoste(n) {
      const sezioni = (Array.isArray(n && n.sezioni) ? n.sezioni : []).filter((x) => x in TITOLI_SEZIONE && x !== "adesso");
      const raccolte = (Array.isArray(n && n.raccolte) ? n.raccolte : []).map(String);
      vis.nascoste = { sezioni, raccolte };
      for (const a of document.querySelectorAll("#barra a[data-sezione]")) a.hidden = sezioni.includes(a.dataset.sezione);
      for (const r of document.querySelectorAll("#sez-cose .raccolta[data-raccolta]")) {
        if (raccolte.includes(r.dataset.raccolta)) r.dataset.nascosta = "1"; else delete r.dataset.nascosta;
      }
      disegnaTessere();
      if (sezioni.includes(vis.sezione)) vai("#/adesso", true);
      else applicaPercorso();
    }

    // All'avvio: l'indirizzo com'è (una sezione sconosciuta diventa Adesso)
    function avvia() {
      const p = percorsoDa(location.hash);
      try { history.replaceState(history.state, "", "#/" + p.map(encodeURIComponent).join("/")); } catch (e) { /* niente */ }
      applicaPercorso();
    }

    // Le schede vive cambiano col tempo (il timer finisce, il promemoria si avvicina): ogni 5 s si
    // ricontrolla dove stanno, e si ridispone solo se qualcosa è cambiato
    let firmaVive = "";
    setInterval(() => {
      if (!sch() || !sch().viva) return;
      const ultima = ultimaConversazione();
      const f = Object.keys(car.schede).map((k) => k + ":" + postiDi(k, ultima)[1]).join("|");
      if (f !== firmaVive) { firmaVive = f; disponi(); }
    }, 5000);

    window.addEventListener("hashchange", applicaPercorso);
    const contenitore = $("sezioni");
    if (contenitore) contenitore.addEventListener("scroll", () => { car.toccato = performance.now(); }, { capture: true, passive: true });

    return {
      car, vis, opzioni, TITOLI_SEZIONE, TIPI_RIMANDO, TIPI_APRONO,
      chiaveDi, sezioneDi, etichettaOra, ultimaConversazione, postiDi, disponi, sincronizza,
      apriSeServe, mostraIn, vaiA, percorsoDa, vai, applicaPercorso, applicaNascoste, avvia,
      aggiornaRaccolte, raccolte: () => ({ tessere: racc.tessere.slice(), aperta: racc.aperta }),
      // Per le prove: dove sta ogni scheda, la sezione guardata, le novità
      stato() {
        const posti = {};
        for (const b of document.querySelectorAll("#sezioni [data-posto]")) posti[b.dataset.posto] = [...b.children].map((e) => e.dataset.chiave);
        const novita = {};
        for (const [k, v] of Object.entries(car.novita)) novita[k] = v.size;
        const tessere = [...document.querySelectorAll("#tessere .tessera")].map((a) => ({ id: a.dataset.tessera,
          conto: a.querySelector(".tessera-conto").textContent, novita: !a.querySelector(".tessera-pallino").hidden }));
        const pagina = [...document.querySelectorAll("#pagina-schede > :not(.gruppo-pagina)")].map((e) => e.dataset.chiave);
        const gruppi = [...document.querySelectorAll("#pagina-schede > .gruppo-pagina")].map((e) => e.textContent);
        const sc = $("sez-cose");
        return { sezione: vis.sezione, percorso: vis.percorso.slice(), modo: vis.modo, posti, novita, tessere, pagina, gruppi,
          cerca: racc.cerca,
          vistaCose: sc ? sc.dataset.vista || null : null,
          nascoste: { sezioni: vis.nascoste.sezioni.slice(), raccolte: vis.nascoste.raccolte.slice() } };
      },
    };
  }

  // Io › Aspetto (27/10): le scelte dell'accento dal server, quella in uso segnata; un tocco la
  // salva per la persona e vale su tutti i suoi satelliti personali. Comune al telefono e al PC
  function disegnaAccenti(a, box, titolo) {
    const scelte = (a && Array.isArray(a.scelte)) ? a.scelte : [];
    box.hidden = !scelte.length;
    if (titolo) titolo.hidden = !scelte.length;
    if (!scelte.length) return;
    const firma = scelte.map((x) => x.id).join(",");
    if (box.dataset.firma !== firma) {
      box.replaceChildren();
      for (const x of scelte) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "accento-scelta";
        b.dataset.accento = String(x.id);
        const tinta = document.createElement("span");
        tinta.className = "tinta";
        tinta.setAttribute("aria-hidden", "true");
        if (/^#[0-9a-f]{6}$/i.test(String(x.colore))) tinta.style.background = x.colore;
        const nome = document.createElement("span");
        nome.textContent = String(x.nome || x.id);
        b.append(tinta, nome);
        box.append(b);
      }
      box.dataset.firma = firma;
    }
    for (const b of box.querySelectorAll(".accento-scelta")) attr(b, "aria-pressed", b.dataset.accento === a.accento ? "true" : "false");
  }

  async function suAccento(ev, esito) {
    const b = ev.target.closest && ev.target.closest(".accento-scelta");
    if (!b || !sch()) return;
    const r = await sch().scegliAccento(b.dataset.accento);
    // La regione resta nel DOM (role="status": VoiceOver legge i cambi di una regione già lì)
    metti(esito, r.ok ? "" : (r.errore || "Non ci sono riuscita: riprova."));
  }

  window.CalliopeSezioni = { crea, TITOLI_SEZIONE, disegnaAccenti, suAccento };
})();
