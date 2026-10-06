// Calliope · schermo (calliope/schermi/). Riceve le schede con SSE e le disegna.
// Tutto il contenuto passa da textContent: le schede sono dati, mai HTML.
"use strict";

(function () {
  // Incorporata (03/10): la pagina del telefono (/telefono) usa questo stesso codice per le
  // schede. Lì l'abbinamento è quello del satellite: il token di schermo arriva dalla sua
  // connessione (window.calliopeSchermo.usa), la pagina non chiede codici suoi e lo stato
  // della voce lo disegna il telefono
  const INCORPORATA = document.body.dataset.incorporata === "1";
  const CHIAVE = document.body.dataset.chiave || "calliope.schermo.token";
  // Carosello (04/10): la pagina del telefono disegna le schede da sé, in un carosello. Qui
  // restano la sessione, la cronologia e il disegno delle singole schede; ogni cambiamento
  // esce come evento sul documento («calliope:schede», «calliope:mostra», «calliope:scrivi»,
  // «calliope:scritto») e le schede si costruiscono con window.calliopeSchermo.costruisci
  const CAROSELLO = document.body.dataset.carosello === "1";
  function emetti(nome, dati) {
    if (!CAROSELLO) return;
    try { document.dispatchEvent(new CustomEvent("calliope:" + nome, { detail: dati || {} })); }
    catch (e) { console.error(e); }
  }
  const NOMI_TIPO = {
    lista: "Lista", timer: "Timer", promemoria: "Agenda", biblioteca: "Biblioteca",
    documento: "Documento", casa: "Casa", calcolo: "Calcolo", testo: "Da leggere",
    lavoro: "Lavoro", modulo: "Da scrivere", web: "Internet", esecuzione: "Programma",
    risposta: "Risposta", foto: "Foto", allegato: "File", gioco: "Gioco",
    cruscotto: "Cruscotto",
  };
  // Il programma di un lavoro mentre gira (04/10, calliope/agenti/esecuzione.py)
  const STATI_ESECUZIONE = {
    in_corso: "in esecuzione", fatto: "finito", errore: "finito con un errore",
    scaduto: "fermato: tempo scaduto", fermato: "fermato",
  };
  const STATI_LAVORO = {
    in_coda: "in coda", in_corso: "in corso", in_attesa: "aspetta la tua risposta",
    fatto: "finito", errore: "non riuscito", mancano_dati: "mancano dati",
    annullato: "annullato", scaduto: "chiuso senza risposta",
  };
  const FLUSSO_LAVORO = { testo: "Sta scrivendo", pensiero: "Sta ragionando", codice: "Sta scrivendo il codice" };
  const fmtOraSec = new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const S = {
    token: null, sessione: null, es: null, scarto: 0, corrente: null,
    cronologia: [], vista: "avvio", abbinamento: null, giri: 0,
    voce: null, voceTotale: 0,
    // Si può scrivere adesso? (05/10) Solo durante una conversazione cominciata a voce: il
    // server lo dice all'accesso, nel benvenuto e con l'evento «scrittura»
    scrittura: { attiva: false, testo: "Di' «Calliope» per scrivermi." },
    capace: false, personale: false, parola: "Calliope",
    // Il proprietario di questo schermo personale amministra (06/10: il cruscotto)
    amministra: false,
    // Quello che si sta scrivendo nei moduli, per id del modulo: resta se la scheda si
    // ridisegna o si riapre dalla cronologia
    bozze: {},
    // Ricollegamento (02/10): un solo ciclo alla volta, e l'ora dell'ultimo segno di vita
    // del flusso (anche i «ping» del server, ogni 15 s)
    ricollego: false, ultimoSegno: 0, tentativi: 0,
  };
  // Attese tra un tentativo e l'altro quando Calliope non risponde: crescono fino a 15 s e
  // poi restano lì, per sempre (mai un arresto definitivo: dopo un riavvio del server, o
  // un'assenza di minuti, la pagina torna da sola)
  const ATTESE_MS = [1000, 2000, 4000, 8000, 15000];
  // Senza nessun evento per questo tempo (il server manda un ping ogni 15 s) il flusso si
  // considera morto anche se il browser non se ne accorge (rete caduta senza chiusura)
  const SILENZIO_MAX_MS = 40000;
  // Stato della voce: testo grande accanto alla forma (colore e forma insieme)
  const TESTI_VOCE = {
    dorme: "Dormo · di' «Calliope»",
    ascolta: "Ti ascolto",
    pensa: "Ci penso…",
    parla: "Parlo",
  };
  const $ = (id) => document.getElementById(id);

  // ─── piccoli aiuti ───
  function el(tag, cls, testo) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (testo !== undefined && testo !== null) e.textContent = String(testo);
    return e;
  }
  const ora = () => Date.now() + S.scarto;           // orologio del server
  const fmtOra = new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit" });
  const fmtData = new Intl.DateTimeFormat("it-IT", { weekday: "long", day: "numeric", month: "long" });

  function leggiToken() {
    // Kiosk di Edge (InPrivate): il token arriva nell'URL dopo «#t=» e non resta nella barra
    const m = location.hash.match(/[#&]t=([A-Za-z0-9_-]{20,})/);
    if (m) {
      try { history.replaceState(null, "", location.pathname); } catch (e) { /* niente */ }
      salvaToken(m[1]);
      return m[1];
    }
    try { return localStorage.getItem(CHIAVE); } catch (e) { return S.token; }
  }
  function salvaToken(t) {
    S.token = t;
    try {
      if (t) localStorage.setItem(CHIAVE, t); else localStorage.removeItem(CHIAVE);
    } catch (e) { /* storage bloccato: resta in memoria */ }
  }

  function stato(cls, testo) {
    const s = $("stato");
    s.className = "stato " + cls;
    $("stato-testo").textContent = testo;
  }

  async function post(url, token) {
    const h = { "Content-Type": "application/json" };
    if (token) h.Authorization = "Bearer " + token;
    const r = await fetch(url, { method: "POST", headers: h, body: "{}", cache: "no-store" });
    let dati = {};
    try { dati = await r.json(); } catch (e) { /* risposta vuota */ }
    return { status: r.status, dati };
  }

  const aspetta = (ms) => new Promise((ok) => setTimeout(ok, ms));

  // ─── avvio e accesso ───
  async function avvio() {
    S.token = leggiToken();
    if (S.token) await accedi(); else if (INCORPORATA) stato("attesa", "schede in attesa");
    else await abbina();
  }

  // Per la pagina che incorpora: un token nuovo (o quello di prima) da usare subito
  window.calliopeSchermo = {
    usa(t) {
      if (!t) return;
      if (t === S.token && S.sessione && S.es) return;
      salvaToken(t);
      S.tentativi = 0;
      if (!S.ricollego) accedi();
    },
    token() { return leggiToken(); },
    // Il pulsante «Foto» del telefono (05/10): apre la scelta della foto nello stesso tocco
    foto() { const x = $("scrivi-foto-file"); if (x && S.fotoAmmessa && S.scrittura.attiva) { x.click(); return true; } return false; },
    dimentica() { chiudiEventi(); salvaToken(null); S.sessione = null; },
    // Per il carosello del telefono: le schede costruite e allineate come qui
    costruisci(c) { return costruisci(c); },
    allinea(a, b) { allinea(a, b); },
    chiaveDi(c) { return chiaveDi(c); },
    cronologia() { return S.cronologia.slice(); },
    corrente() { return S.corrente; },
    aggiorna() { aggiornaTimer(); aggiornaLavori(); },
    // Il cruscotto di chi amministra (06/10): il menu del telefono lo apre nel carosello
    cruscotto() { return apriCruscotto(); },
    amministra() { return S.amministra; },
    NOMI_TIPO,
  };

  // Nuovo accesso con il token, finché non riesce. Le sessioni del server sono in memoria:
  // dopo un suo riavvio la sessione vecchia non vale più (e EventSource, su una risposta
  // d'errore HTTP, si ferma per sempre), quindi ogni ricollegamento rifà /api/accedi.
  async function accedi() {
    chiudiEventi();
    let r;
    for (;;) {
      stato("attesa", S.tentativi ? "riconnessione…" : "collegamento…");
      try {
        r = await post("/api/accedi", S.token);
      } catch (e) {
        r = null;                         // rete o server giù
      }
      if (r && r.status === 401) {        // revocato, o mai abbinato su questo server
        salvaToken(null);
        S.tentativi = 0;
        if (INCORPORATA) { stato("attesa", "schede in attesa"); return; }
        return abbina();
      }
      if (r && r.status === 200) break;
      const attesa = ATTESE_MS[Math.min(S.tentativi, ATTESE_MS.length - 1)];
      S.tentativi++;
      stato("giu", (r ? "errore " + r.status : "Calliope non risponde") + " · riconnessione…");
      if (S.vista === "avvio") mostraInattiva();
      await aspetta(attesa);
    }
    S.tentativi = 0;
    S.sessione = r.dati.sessione;
    S.scarto = r.dati.ora_server * 1000 - Date.now();
    if (r.dati.scrittura) S.scrittura = r.dati.scrittura;
    casellaScrivi(!!r.dati.scrivi, !!r.dati.personale);
    impostaAmministra(!!r.dati.amministra);
    if (!CAROSELLO) $("luogo").textContent = r.dati.stanza || "Calliope";
    document.title = "Calliope · " + (r.dati.stanza || "schermo");
    collegaEventi();
  }

  function chiudiEventi() {
    if (S.es) { S.es.close(); S.es = null; }
  }

  // Un solo ciclo di ricollegamento alla volta, da qualunque causa (errore del flusso,
  // silenzio troppo lungo, flusso chiuso)
  function ricollega() {
    if (S.ricollego || S.abbinamento) return;
    S.ricollego = true;
    chiudiEventi();
    stato("attesa", "riconnessione…");
    S.tentativi = Math.max(S.tentativi, 1);
    accedi().finally(() => { S.ricollego = false; });
  }

  function vivo() { S.ultimoSegno = Date.now(); }

  function collegaEventi() {
    chiudiEventi();
    const es = new EventSource("/eventi?sessione=" + encodeURIComponent(S.sessione));
    S.es = es;
    vivo();
    es.addEventListener("open", () => { vivo(); stato("ok", "collegato"); });
    es.addEventListener("ping", vivo);
    es.addEventListener("benvenuto", (ev) => {
      vivo();
      const d = JSON.parse(ev.data);
      S.scarto = d.ora_server * 1000 - Date.now();
      if (d.parola) { TESTI_VOCE.dorme = "Dormo · di' «" + d.parola + "»"; S.parola = d.parola; }
      stato("ok", "collegato");
      // Le schede della cronologia del server, nell'ordine del server: una scheda già qui
      // con la stessa identità (o lo stesso id) si sostituisce, mai un doppione
      (d.cronologia || []).forEach((c) => aggiungiCronologia(c, true));
      mostraVoce(d.voce || null);       // null: questa pagina non mostra lo stato
      if (d.scrittura) applicaScrittura(d.scrittura);
      mostraContesto(d.contesto || null);
      const ultima = d.cronologia && d.cronologia[d.cronologia.length - 1];
      if (ultima && valida(ultima)) mostra(ultima);
      else if (!S.corrente) mostraInattiva();
    });
    es.addEventListener("scheda", (ev) => {
      vivo();
      const c = JSON.parse(ev.data);
      if (c.tipo === "vuota") {
        if (moduloInCorso()) return;       // non si cancella un modulo mentre si scrive
        S.corrente = null; mostraInattiva(); return;
      }
      if (moduloInCorso() && chiaveDi(c) !== chiaveDi(S.corrente)) {
        // Si sta scrivendo in un modulo: l'altra scheda va nella cronologia, il modulo resta
        aggiungiCronologia(c);
        return;
      }
      if (giocoInCorso() && chiaveDi(c) !== chiaveDi(S.corrente) && c.tipo !== "gioco") {
        // Si sta giocando (05/10): l'altra scheda va nella cronologia, il gioco resta
        aggiungiCronologia(c);
        return;
      }
      if (c.sposta === false) {
        // Aggiornamento automatico: resta al suo posto e non passa in primo piano; se è
        // quella mostrata si ridisegna, senza perdere il punto in cui si stava leggendo
        aggiungiCronologia(c);
        if (S.corrente && chiaveDi(S.corrente) === chiaveDi(c)) ridisegna(c);
        return;
      }
      aggiungiCronologia(c);
      mostra(c);
    });
    es.addEventListener("voce", (ev) => { vivo(); mostraVoce(JSON.parse(ev.data)); });
    es.addEventListener("scrittura", (ev) => { vivo(); applicaScrittura(JSON.parse(ev.data)); });
    es.addEventListener("contesto", (ev) => { vivo(); mostraContesto(JSON.parse(ev.data)); });
    es.addEventListener("gioco", (ev) => { vivo(); daServerGioco(JSON.parse(ev.data)); });
    es.addEventListener("revocato", () => {
      mostraVoce(null);
      mostraContesto(null);
      chiudiEventi();
      casellaScrivi(false);
      salvaToken(null);
      S.cronologia = [];
      emetti("schede", {});
      disegnaCronologia();
      if (INCORPORATA) { S.sessione = null; stato("attesa", "schede in attesa"); return; }
      abbina();
    });
    es.addEventListener("error", () => {
      if (es !== S.es) return;
      // Server giù, riavviato (sessione non più valida: 401 e EventSource chiuso per
      // sempre) o rete caduta: non si lascia fare a EventSource, che riproverebbe con la
      // sessione vecchia. Si chiude e si rifà l'accesso con il token, con attese crescenti
      stato("attesa", "riconnessione…");
      ricollega();
    });
  }

  // Il cane da guardia: un flusso chiuso, o muto da troppo (nemmeno i ping), si rifà
  setInterval(() => {
    if (S.ricollego || S.abbinamento || !S.sessione) return;
    if (!S.es || S.es.readyState === EventSource.CLOSED
        || Date.now() - S.ultimoSegno > SILENZIO_MAX_MS) ricollega();
  }, 2000);

  // ─── abbinamento ───
  async function abbina() {
    chiudiEventi();
    S.corrente = null;
    $("luogo").textContent = "Calliope";
    stato("attesa", "da abbinare");
    S.sessione = null;
    let r;
    try {
      r = await post("/api/abbinamento");
    } catch (e) {
      stato("giu", "Calliope non risponde · riconnessione…");
      await aspetta(ATTESE_MS[Math.min(S.giri++, ATTESE_MS.length - 1)]);
      return abbina();
    }
    if (r.status !== 200) { await aspetta(5000); return abbina(); }
    S.giri = 0;
    S.scarto = r.dati.ora_server * 1000 - Date.now();
    const a = { codice: r.dati.codice, richiesta: r.dati.richiesta, scade: r.dati.scade * 1000 };
    S.abbinamento = a;
    mostraCodice(a);
    while (S.abbinamento === a) {
      await aspetta(1500);
      if (S.abbinamento !== a) return;
      let s;
      try {
        s = await post("/api/abbinamento/stato", a.richiesta);
      } catch (e) {
        stato("giu", "Calliope non risponde");
        continue;
      }
      if (s.dati.stato === "abbinato") {
        S.abbinamento = null;
        salvaToken(a.richiesta);          // la richiesta diventa il token dello schermo
        return accedi();
      }
      if (s.dati.stato === "scaduto" || ora() > a.scade) {
        S.abbinamento = null;
        return abbina();                  // codice nuovo
      }
      stato("attesa", "da abbinare");
      aggiornaScadenza(a);
    }
  }

  function mostraCodice(a) {
    S.vista = "abbina";
    const m = $("principale");
    m.replaceChildren();
    const box = el("section", "abbina");
    box.append(el("h1", "", "Abbina questo schermo"));
    const c = a.codice.slice(0, 3) + " " + a.codice.slice(3);
    box.append(el("div", "codice", c));
    const ist = el("p", "istruzioni");
    ist.append("Di' a Calliope: ");
    ist.append(el("q", "", "abbina lo schermo " + c + " al soggiorno"));
    ist.append(" (con il nome della stanza).");
    box.append(ist);
    box.append(el("p", "piccolo", ""));
    m.append(box);
    aggiornaScadenza(a);
  }

  function aggiornaScadenza(a) {
    const p = document.querySelector(".abbina .piccolo");
    if (!p) return;
    const min = Math.max(0, Math.ceil((a.scade - ora()) / 60000));
    p.textContent = min > 1 ? "Il codice vale ancora " + min + " minuti." : "Il codice sta per scadere: poi ne compare uno nuovo.";
  }

  // ─── schede ───
  function valida(c) { return !c.scade || ora() < c.scade * 1000; }

  // L'identità di una scheda: la chiave dell'oggetto (timer:12, documento:3, lista:spesa)
  // o, per le schede senza oggetto (calcoli, biblioteca), l'id di quell'invio
  function chiaveDi(c) { return c.chiave || c.id; }

  // ordine: true al riaggancio, dove vale l'ordine della cronologia del server (anche per
  // le schede che lì erano aggiornamenti automatici)
  function aggiungiCronologia(c, ordine) {
    if (c.tipo === "vuota") return;
    const k = chiaveDi(c);
    const i = S.cronologia.findIndex((x) => chiaveDi(x) === k || x.id === c.id);
    if (i >= 0 && c.sposta === false && !ordine) {
      S.cronologia[i] = c;               // al suo posto
    } else {
      if (i >= 0) S.cronologia.splice(i, 1);
      S.cronologia.push(c);              // in cima, come l'ultima arrivata
      if (S.cronologia.length > 6) S.cronologia.shift();
    }
    emetti("schede", { scheda: c, spostata: !(i >= 0 && c.sposta === false && !ordine) });
    disegnaCronologia();
  }

  function disegnaCronologia() {
    const f = $("cronologia");
    if (!f) return;
    f.replaceChildren();
    S.cronologia.slice().reverse().forEach((c) => {
      const b = el("button");
      b.type = "button";
      if (S.corrente && chiaveDi(S.corrente) === chiaveDi(c)) b.classList.add("attiva");
      b.append(el("span", "", (NOMI_TIPO[c.tipo] || c.tipo) + " · " + fmtOra.format(new Date(c.creata * 1000))));
      b.append(el("span", "t-titolo", c.titolo));
      b.addEventListener("click", () => mostra(Object.assign({}, c, { scade: (ora() + 300000) / 1000 })));
      f.append(b);
    });
  }

  // La stessa scheda aggiornata (l'avanzamento di un lavoro, l'uscita di un programma: anche
  // più volte al secondo): si aggiorna al suo posto, senza segnale (04/10)
  function ridisegna(c) { mostra(c, false); }

  // Aggiorna `a` (nel documento) perché diventi come `b` (appena costruito), toccando solo i
  // nodi che cambiano: stessi elementi, stessi scorrimenti, nessuna animazione che riparte
  // (04/10: la scheda dell'avanzamento, ricostruita due volte al secondo, lampeggiava)
  function allinea(a, b) {
    if (a.nodeType === 3) { if (a.data !== b.data) a.data = b.data; return; }
    if (a.tagName !== b.tagName) { a.replaceWith(b); return; }
    for (const at of [...b.attributes]) {
      if (a.getAttribute(at.name) !== at.value) a.setAttribute(at.name, at.value);
    }
    for (const at of [...a.attributes]) if (!b.hasAttribute(at.name)) a.removeAttribute(at.name);
    const nuovi = [...b.childNodes];
    nuovi.forEach((n, i) => {
      const v = a.childNodes[i];
      if (!v) a.appendChild(n);
      else if (v.nodeType !== n.nodeType || (n.nodeType !== 1 && n.nodeType !== 3)) a.replaceChild(n, v);
      else allinea(v, n);
    });
    while (a.childNodes.length > nuovi.length) a.removeChild(a.lastChild);
  }

  // Le aree che seguono la coda del testo (uscita di un programma, testo in arrivo): restano
  // in fondo solo se chi guarda era in fondo
  function inFondo(e) { return e.scrollHeight - e.scrollTop - e.clientHeight < 24; }

  function costruisci(c) {
    const s = el("article", "scheda tipo-" + c.tipo);
    s.dataset.chiave = chiaveDi(c);
    const et = el("div", "etichetta", NOMI_TIPO[c.tipo] || c.tipo);
    if (c.visibilita === "personale") et.append(el("span", "badge personale", "personale"));
    if (c.fonte) et.append(el("span", "badge", c.fonte));
    if (c.formato) et.append(el("span", "badge", c.formato.toUpperCase()));
    s.append(et);
    if (c.tipo !== "calcolo") s.append(el("h1", "titolo", c.titolo));
    const corpo = el("div", "corpo");
    (DISEGNA[c.tipo] || DISEGNA.testo)(c, corpo, s);
    s.append(corpo);
    return s;
  }

  // `segnale`: la stessa scheda cambiata per un evento (sposta: true, un cambio di stato):
  // un segno leggero sul bordo, non l'animazione di entrata
  function mostra(c, segnale = true) {
    const prima = S.corrente;
    S.corrente = c;
    S.vista = "scheda";
    if (CAROSELLO) { emetti("mostra", { scheda: c, segnale }); return; }
    const m = $("principale");
    const vecchia = m.querySelector(":scope > article.scheda");
    const nuova = costruisci(c);
    if (vecchia && prima && chiaveDi(prima) === chiaveDi(c) && vecchia.dataset.chiave === chiaveDi(c)
        && c.tipo !== "modulo" && prima.tipo === c.tipo) {
      const seguite = [...vecchia.querySelectorAll("pre[data-segui]")].map(inFondo);
      // Il segno di prima resta com'è (togliere e rimettere la classe lo farebbe ripartire)
      if (vecchia.classList.contains("cambiata")) nuova.classList.add("cambiata");
      allinea(vecchia, nuova);
      vecchia.querySelectorAll("pre[data-segui]").forEach((p, i) => {
        if (seguite[i] !== false) p.scrollTop = p.scrollHeight;
      });
      if (segnale) {
        vecchia.classList.remove("cambiata");
        void vecchia.offsetWidth;          // il segno riparte anche se c'era già
        vecchia.classList.add("cambiata");
      }
    } else {
      m.replaceChildren(nuova);
      nuova.querySelectorAll("pre[data-segui]").forEach((p) => { p.scrollTop = p.scrollHeight; });
    }
    disegnaCronologia();
    aggiornaTimer();
    aggiornaLavori();
  }

  const DISEGNA = {
    lista(c, corpo) {
      if (!c.voci || !c.voci.length) { corpo.append(el("p", "vuoto", "La lista è vuota.")); }
      else {
        const ul = el("ul", "voci");
        c.voci.forEach((v) => ul.append(el("li", v.nuova ? "nuova" : "", v.testo)));
        corpo.append(ul);
      }
      if (c.altre) corpo.append(el("p", "nota", "e altre " + c.altre));
      if (c.tolti && c.tolti.length) corpo.append(el("p", "nota", "Tolto: " + c.tolti.join(", ")));
    },
    timer(c, corpo) {
      if (!c.timer || !c.timer.length) { corpo.append(el("p", "vuoto", "Nessun timer attivo.")); return; }
      const g = el("div", "timer");
      c.timer.forEach((t) => {
        const r = el("div", "riga" + (c.timer.length === 1 ? " solo" : ""));
        r.append(el("div", "nome", t.etichetta));
        if (t.stato && t.stato !== "attivo") {
          // Annullato o scaduto: la stessa scheda con lo stato e l'ora, niente conto
          r.classList.add("finito");
          r.append(el("div", "resto", t.nota || t.stato));
          g.append(r);
          return;
        }
        const resto = el("div", "resto", "");
        resto.dataset.fine = String(t.fine * 1000);
        r.append(resto);
        g.append(r);
      });
      corpo.append(g);
    },
    promemoria(c, corpo) {
      if (!c.voci || !c.voci.length) { corpo.append(el("p", "vuoto", "Niente in agenda.")); return; }
      const g = el("div", "agenda");
      c.voci.forEach((v) => {
        const r = el("div", "riga");
        r.append(el("div", "quando", v.quando));
        r.append(el("div", "cosa", v.testo + (v.tipo === "appuntamento" ? "" : " (promemoria)")));
        g.append(r);
      });
      corpo.append(g);
    },
    biblioteca(c, corpo) {
      if (c.domanda) corpo.append(el("p", "sotto", "«" + c.domanda + "»"));
      corpo.append(el("blockquote", "passaggio", c.passaggio));
      if (c.testo) {
        const l = el("div", "lungo");
        c.testo.split(/\n\n+/).forEach((p) => l.append(el("p", "", p)));
        corpo.append(l);
      }
      if (c.altre && c.altre.length) corpo.append(el("p", "altre", "Anche: " + c.altre.join(", ")));
    },
    documento(c, corpo) {
      const meta = el("p", "sotto", c.file || "");
      if (c.modifica) meta.textContent += " · cambiato: " + c.modifica;
      corpo.append(meta);
      const d = el("div", "documento");
      (c.blocchi || []).forEach((b) => {
        if (b.tipo === "titolo") d.append(el("h2", "", b.testo));
        else if (b.tipo === "paragrafo") d.append(el("p", b.allinea === "destra" ? "destra" : "", b.testo));
        else if (b.tipo === "elenco") {
          const l = el(b.numerato ? "ol" : "ul");
          (b.voci || []).forEach((v) => l.append(el("li", "", v)));
          d.append(l);
        } else if (b.tipo === "tabella") {
          if (b.nome) d.append(el("div", "foglio", b.nome));
          d.append(tabella(b));
        }
      });
      corpo.append(d);
    },
    casa(c, corpo) {
      const g = el("div", "casa");
      (c.righe || []).forEach((r) => {
        const x = el("div", "riga" + (r.acceso ? " acceso" : ""));
        x.append(el("div", "nome", r.nome));
        if (r.stanza) x.append(el("div", "dove", r.stanza));
        x.append(el("div", "stato-dispositivo", r.stato));
        g.append(x);
      });
      corpo.append(g);
    },
    web(c, corpo) {
      // Testo di siti internet: solo textContent (el), niente collegamenti
      if (c.domanda) corpo.append(el("p", "sotto", "«" + c.domanda + "»"));
      (c.voci || []).forEach((v) => {
        const r = el("div", "risultato-web");
        r.append(el("div", "sito", v.sito + (v.dominio ? " · " + v.dominio : "") + (v.data ? " · " + v.data : "")));
        r.append(el("div", "titolo", v.titolo));
        if (v.testo) r.append(el("p", "", v.testo));
        corpo.append(r);
      });
    },
    calcolo(c, corpo) {
      const b = el("div", "calcolo");
      b.append(el("div", "espressione", c.espressione + " ="));
      b.append(el("div", "risultato", c.risultato));
      corpo.append(b);
    },
    testo(c, corpo) {
      corpo.append(el("div", "testo-lungo", c.testo || ""));
    },
    // La risposta a una frase scritta da qui (04/10): la domanda piccola sopra, poi il testo
    risposta(c, corpo) {
      if (c.domanda) corpo.append(el("div", "domanda-scritta", c.domanda));
      corpo.append(el("div", "testo-lungo", c.testo || ""));
    },
    // Una foto della conversazione (05/10): la miniatura, solo un data URL JPEG (CSP img-src)
    foto(c, corpo, s) {
      s.classList.add("scheda-foto");
      const img = el("img");
      img.alt = c.titolo || "Foto";
      if (typeof c.src === "string" && c.src.startsWith("data:image/jpeg;base64,")) img.src = c.src;
      corpo.append(img);
      if (c.didascalia) corpo.append(el("p", "didascalia", c.didascalia));
    },
    // Un file allegato alla conversazione (05/10): nome, tipo, dimensione, note e l'inizio del
    // testo; tutto come testo (textContent), mai HTML del file
    allegato(c, corpo, s) {
      s.classList.add("scheda-allegato");
      corpo.append(el("p", "nome-allegato", c.nome || "file"));
      corpo.append(el("p", "sotto", [c.tipo_file, c.struttura, c.dimensione].filter(Boolean).join(" · ")));
      for (const n of (Array.isArray(c.note) ? c.note : [])) corpo.append(el("p", "sotto", n));
      if (c.anteprima) corpo.append(el("div", "testo-lungo anteprima-allegato", c.anteprima));
    },
    lavoro(c, corpo) {
      const av = c.avanzamento;
      if (av && ["in_coda", "in_corso"].includes(c.stato)) { disegnaAvanzamento(c, av, corpo); return; }
      const meta = el("p", "sotto", STATI_LAVORO[c.stato] || c.stato || "");
      if (c.test) {
        const t = c.test, ko = (t.falliti || 0) + (t.errori || 0);
        meta.textContent += " · test: " + (ko ? ko + " non passano su " + Math.max(t.eseguiti, ko)
          : (t.eseguiti || 0) + " passano");
      }
      if (c.cartella) meta.textContent += " · " + c.cartella;
      corpo.append(meta);
      if (c.riassunto) corpo.append(el("p", "riassunto-lavoro", c.riassunto));
      if (c.domanda) corpo.append(el("p", "domanda-lavoro", c.domanda));
      (c.file || []).forEach((f) => {
        const b = el("section", "file-lavoro");
        b.append(el("div", "nome-file", f.nome));
        b.append(el("pre", "codice", f.testo));       // textContent: il codice non è HTML
        corpo.append(b);
      });
      if (av) {
        // A lavoro finito: quanto ha consumato e gli ultimi passi, sotto il risultato
        corpo.append(tettiLavoro(av, false));
        if (av.passi && av.passi.length) corpo.append(passiLavoro(av.passi));
      }
    },
  };

  // L'uscita di un programma: stdout e stderr (in rosso) mentre arrivano, sempre come testo
  DISEGNA.esecuzione = function (c, corpo) {
    const meta = el("p", "sotto", (c.linguaggio ? c.linguaggio + " · " : "") + (c.programma || "")
      + " · " + (STATI_ESECUZIONE[c.stato] || c.stato || ""));
    if (c.stato !== "in_corso" && c.codice_uscita !== null && c.codice_uscita !== undefined) {
      meta.textContent += " · codice d'uscita " + c.codice_uscita;
    }
    corpo.append(meta);
    const t = el("p", "tempo-esecuzione" + (c.stato === "in_corso" ? " vivo" : ""),
      secondiDetti(c.trascorso_s || 0) + (c.stato === "in_corso" ? " di " + c.max_s + " s al massimo" : ""));
    if (c.stato === "in_corso" && c.dal) { t.dataset.dalEsec = String(c.dal * 1000); t.dataset.max = String(c.max_s); }
    corpo.append(t);
    if (c.dati && c.dati.length) corpo.append(el("p", "dati-esecuzione", "Dati: " + c.dati.join("  ")));
    const pre = el("pre", "uscita-esecuzione");
    if (c.omessi) pre.append(el("span", "omessi", "[… " + c.omessi.toLocaleString("it-IT") + " caratteri omessi …]\n"));
    (c.righe || []).forEach((r) => pre.append(el("span", r.tipo === "err" ? "err" : "out", r.testo)));
    if (!(c.righe || []).length) {
      pre.append(el("span", "vuoto", c.stato === "in_corso" ? "Aspetto quello che scrive il programma…" : "Il programma non ha scritto niente."));
    }
    corpo.append(pre);
    if (c.file) corpo.append(el("p", "nota", "Uscita intera nella cartella del lavoro: " + c.file));
    pre.dataset.segui = "1";              // resta in fondo se chi guarda era in fondo
  };

  function secondiDetti(s) {
    s = Math.max(0, s);
    return (s < 60 ? s.toFixed(1).replace(".", ",") + " s" : durata(s));
  }

  // ─── cruscotto di chi amministra (06/10, calliope/schermi/cruscotto.py) ───
  // Sola lettura: versione, capacità, latenza, satelliti e schermi, regole, errori, richieste in
  // attesa. Una scheda di questa pagina (mai dal server, mai nella sua cronologia), solo sugli
  // schermi personali di chi amministra: il server lo ricontrolla a ogni richiesta. Si aggiorna
  // da sola ogni 30 s finché la scheda c'è; nessun pulsante cambia qualcosa (revoche e
  // approvazioni restano a voce o da terminale: qui solo il comando, come testo).
  const CRUSCOTTO = "cruscotto";
  const CRUSCOTTO_MS = 30000;

  function impostaAmministra(si) {
    S.amministra = !!si;
    emetti("amministra", { attiva: S.amministra });
    if (!S.amministra) togliCruscotto();
    if (CAROSELLO || INCORPORATA) return;
    let b = $("cruscotto-apri");
    if (!b && S.amministra) {
      b = el("button", "piccolo-bottone apri-cruscotto", "Cruscotto");
      b.id = "cruscotto-apri";
      b.type = "button";
      b.title = "Lo stato di Calliope, solo per chi amministra";
      b.addEventListener("click", () => apriCruscotto());
      const testa = $("testa");
      if (testa) testa.insertBefore(b, $("stato"));
    }
    if (b) b.hidden = !S.amministra;
  }

  function cruscottoAperto() { return S.cronologia.some((c) => chiaveDi(c) === CRUSCOTTO); }

  // primo: la scheda si apre e passa davanti; altrimenti si aggiorna al suo posto
  async function apriCruscotto(primo = true, forza = false) {
    if (!S.sessione || !S.amministra) return false;
    let r;
    try {
      const x = await fetch("/api/cruscotto" + (forza ? "?aggiorna=1" : ""), {
        headers: { "X-Calliope-Sessione": S.sessione }, cache: "no-store" });
      r = { status: x.status, dati: await x.json().catch(() => ({})) };
    } catch (e) {
      r = { status: 0, dati: { errore: "Calliope non risponde" } };
    }
    if (r.status === 403 || r.status === 404) {   // non amministra più, o cruscotto spento
      impostaAmministra(false);
      return false;
    }
    if (!primo && !cruscottoAperto()) return false;  // chiuso mentre aspettava
    const c = { tipo: CRUSCOTTO, id: CRUSCOTTO, chiave: CRUSCOTTO, titolo: "Stato di Calliope",
      visibilita: "personale", creata: ora() / 1000, dati: r.status === 200 ? r.dati : null,
      errore: r.status === 200 ? null : (r.dati.errore || "errore " + r.status) };
    if (!primo) c.sposta = false;
    // Un errore momentaneo non cancella i dati di prima
    if (!c.dati && !primo) {
      const prima = S.cronologia.find((x) => chiaveDi(x) === CRUSCOTTO);
      if (prima && prima.dati) c.dati = prima.dati;
    }
    aggiungiCronologia(c);
    if (primo) mostra(c);
    else if (S.corrente && chiaveDi(S.corrente) === CRUSCOTTO) ridisegna(c);
    return true;
  }

  function togliCruscotto() {
    const i = S.cronologia.findIndex((c) => chiaveDi(c) === CRUSCOTTO);
    if (i < 0) return;
    S.cronologia.splice(i, 1);
    emetti("schede", {});
    disegnaCronologia();
    if (S.corrente && chiaveDi(S.corrente) === CRUSCOTTO) {
      S.corrente = null;
      const ultima = S.cronologia[S.cronologia.length - 1];
      if (ultima && valida(ultima) && !CAROSELLO) mostra(ultima); else mostraInattiva();
    }
  }

  setInterval(() => {
    if (cruscottoAperto() && S.sessione && document.visibilityState === "visible") apriCruscotto(false);
  }, CRUSCOTTO_MS);

  // I due pulsanti della scheda (Aggiorna e Chiudi) per delega: la scheda si ridisegna
  // allineando i nodi, e nel carosello del telefono è un altro elemento
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest && ev.target.closest("[data-cruscotto]");
    if (!b) return;
    if (b.dataset.cruscotto === "aggiorna") apriCruscotto(false, true);
    else if (b.dataset.cruscotto === "chiudi") togliCruscotto();
  });

  const fmtS = (x) => (x === null || x === undefined) ? "—" : x.toFixed(2).replace(".", ",") + " s";
  function fa(epoch) {
    if (!epoch) return "mai";
    const s = Math.max(0, (ora() / 1000) - epoch);
    if (s < 90) return "ora";
    if (s < 3600) return Math.round(s / 60) + " min fa";
    if (s < 86400 * 2) return Math.round(s / 3600) + " h fa";
    return Math.round(s / 86400) + " giorni fa";
  }
  function sezione(corpo, titolo) {
    const s = el("section", "cr-sezione");
    s.append(el("h2", "cr-titolo", titolo));
    corpo.append(s);
    return s;
  }
  function comando(box, testo) { if (testo) box.append(el("p", "cr-comando", testo)); }
  function nonLetto(box, parte) {
    if (parte && parte.errore) { box.append(el("p", "cr-avviso", parte.errore)); return true; }
    return !parte;
  }

  DISEGNA.cruscotto = function (c, corpo) {
    const d = c.dati || {};
    const testa = el("div", "cr-testa");
    const quando = d.ora ? "aggiornato alle " + fmtOraSec.format(new Date(d.ora * 1000))
      + (d.calcolo_ms !== undefined ? " · calcolo " + Math.round(d.calcolo_ms) + " ms" : "") : "";
    testa.append(el("span", "cr-quando", quando));
    for (const [az, t] of [["aggiorna", "Aggiorna"], ["chiudi", "Chiudi"]]) {
      const b = el("button", "piccolo-bottone", t);
      b.type = "button";
      b.dataset.cruscotto = az;
      testa.append(b);
    }
    corpo.append(testa);
    corpo.append(el("p", "cr-nota", "Solo lettura: per cambiare qualcosa usa la voce o il terminale."));
    if (c.errore) corpo.append(el("p", "cr-avviso", "Non riesco a leggere lo stato: " + c.errore));
    if (!c.dati) return;

    // Versione
    let s = sezione(corpo, "Versione");
    const v = d.versione || {};
    if (!nonLetto(s, d.versione)) {
      s.append(el("p", "", (v.descrizione || v.commit || "sconosciuta")
        + (v.commit && v.descrizione && !v.descrizione.includes(v.commit) ? " (" + v.commit + ")" : "")
        + (v.installata ? " · " + (v.origine === "installata" ? "installata il " : "del ")
          + v.installata.replace("T", " ").slice(0, 16) : "")));
    }

    // Capacità
    s = sezione(corpo, "Capacità");
    const cap = d.capacita || {};
    if (!nonLetto(s, d.capacita)) {
      s.append(el("p", "cr-sintesi", cap.attive + " attive su " + cap.totale));
      const ul = el("ul", "cr-lista");
      (cap.voci || []).filter((x) => x.stato !== "attiva").forEach((x) => {
        const li = el("li", "cr-voce " + x.stato);
        const r1 = el("div", "cr-riga1");
        r1.append(el("span", "cr-nome", x.breve));
        r1.append(el("span", "badge cr-stato", x.stato.replace("_", " ")));
        li.append(r1);
        if (x.motivo) li.append(el("div", "cr-motivo", x.motivo));
        if (x.prossimo_passo) li.append(el("div", "cr-passo", x.prossimo_passo));
        ul.append(li);
      });
      if (ul.children.length) s.append(ul);
      const attive = (cap.voci || []).filter((x) => x.stato === "attiva").map((x) => x.breve);
      if (attive.length) s.append(el("p", "cr-tenue", "Attive: " + attive.join(", ")));
      comando(s, "Da terminale: " + cap.comando);
    }

    // Latenza
    s = sezione(corpo, "Latenza della voce");
    const lat = d.latenza || {};
    if (!nonLetto(s, d.latenza)) {
      if (!(lat.giorni || []).length) s.append(el("p", "cr-tenue", "Nessun turno nel registro."));
      (lat.giorni || []).forEach((g) => {
        const r = el("div", "cr-giorno");
        const pf = g.prima_frase || {};
        r.append(el("div", "cr-riga", g.data + " · " + g.risposte + " risposte · prima frase "
          + fmtS(pf.mediana) + " (p90 " + fmtS(pf.p90) + ") · base " + fmtS((g.base || {}).mediana)
          + ((g.fine_parlato || {}).n ? " · dalla fine " + fmtS(g.fine_parlato.mediana) : "")));
        // La prima voce sentita (06/10): quando il satellite o le casse cominciano a suonare
        const pv = g.prima_voce || {};
        if (pv.n) r.append(el("div", "cr-riga", "prima voce sentita " + fmtS(pv.mediana)
          + " (p90 " + fmtS(pv.p90) + ")"
          + (pv.sentita !== null && pv.sentita !== undefined
            ? " · dalla fine del parlato " + fmtS(pv.sentita) + " (p90 " + fmtS(pv.sentita_p90) + ")" : "")));
        const cause = [];
        const stt = (g.stt || {}).mediana;
        if (stt !== null && stt !== undefined) cause.push("STT " + fmtS(stt));
        if ((g.tool || {}).n) cause.push("tool in " + g.tool.n + " turni (" + fmtS(g.tool.con) + " contro " + fmtS(g.tool.senza) + ")");
        if ((g.guardiano || {}).n) cause.push("guardiano " + g.guardiano.n + " turni (" + fmtS(g.guardiano.prima_frase) + ")"
          + (g.guardiano.guasti ? ", " + g.guardiano.guasti + " senza giudizio" : ""));
        if ((g.correzione || {}).n) cause.push("correzione " + g.correzione.n + " frasi");
        if ((g.lettura || {}).lente) cause.push("cache persa in " + g.lettura.lente + " turni");
        if ((g.coda || {}).n) cause.push("in coda " + g.coda.n + " volte");
        if ((g.schede_attesa || {}).n) cause.push("schede trattenute " + g.schede_attesa.n + " volte, "
          + Math.round(g.schede_attesa.ms_mediana) + " ms (massimo " + Math.round(g.schede_attesa.ms_max) + ")");
        if (cause.length) r.append(el("div", "cr-tenue", cause.join(" · ")));
        if (g.avviso) r.append(el("div", "cr-avviso", g.avviso));
        if (g.avviso_guasti) r.append(el("div", "cr-avviso", "Attenzione: " + g.avviso_guasti));
        s.append(r);
      });
      comando(s, "Da terminale: " + lat.comando);
    }

    // Satelliti e schermi
    s = sezione(corpo, "Satelliti e schermi");
    const ab = d.abbinamenti || {};
    if (!nonLetto(s, d.abbinamenti)) {
      const elenchi = [["Satelliti", ab.satelliti, (ab.comandi || {}).satelliti],
        ["Schermi", ab.schermi, (ab.comandi || {}).schermi]];
      for (const [nome, righe, cmd] of elenchi) {
        s.append(el("h3", "cr-sotto", nome + " (" + (righe || []).length + ")"));
        const ul = el("ul", "cr-lista");
        (righe || []).forEach((x) => {
          const li = el("li", "cr-abbinato" + (x.collegato ? " collegato" : "") + (x.inattivo ? " inattivo" : ""));
          const r1 = el("div", "cr-riga1");
          r1.append(el("span", "punto", ""));
          r1.append(el("span", "cr-nome", x.nome || "?"));
          if (x.inattivo) r1.append(el("span", "badge cr-stato", "inattivo"));
          li.append(r1);
          const det = [x.stanza, x.personale_di ? "personale di " + x.personale_di : "di stanza"];
          if (x.ruolo) det.push(x.ruolo);
          if (x.attivo) det.push("attivo");
          det.push(x.collegato ? "collegato" : "ultimo collegamento " + fa(x.visto));
          li.append(el("div", "cr-motivo", det.filter(Boolean).join(" · ")));
          ul.append(li);
        });
        if (ul.children.length) s.append(ul);
        if ((righe || []).some((x) => x.inattivo)) {
          comando(s, "Inattivi da più di " + Math.round(ab.inattivi_giorni) + " giorni; per toglierne uno: " + cmd);
        }
      }
      if (!ab.server_satelliti) s.append(el("p", "cr-tenue", "Audio di questo computer: i collegamenti dei satelliti non si vedono da qui."));
    }

    // Regole
    s = sezione(corpo, "Regole scattate");
    const reg = d.regole || {};
    if (!nonLetto(s, d.regole)) {
      const tot = reg.totali || [];
      s.append(el("p", "cr-sintesi", (tot.length ? "Negli ultimi " : "Nessuna regola negli ultimi ") + reg.giorni + " giorni"));
      if (tot.length) {
        const ul = el("ul", "cr-conti");
        tot.slice(0, 15).forEach((x) => {
          const li = el("li");
          li.append(el("span", "cr-nome", x.regola));
          li.append(el("span", "cr-n", x.n));
          ul.append(li);
        });
        s.append(ul);
        if (tot.length > 15) s.append(el("p", "cr-tenue", "e altre " + (tot.length - 15)));
      }
      (reg.per_profilo || []).forEach((p) => {
        const top = (p.regole || []).slice(0, 5).map((x) => x.regola + " " + x.n).join(", ");
        s.append(el("p", "cr-tenue", p.profilo + ": " + p.turni + " turni" + (top ? " · " + top : "")));
      });
    }

    // Errori
    s = sezione(corpo, "Errori del ciclo");
    const er = d.errori || {};
    if (!nonLetto(s, d.errori)) {
      if (!er.n) s.append(el("p", "cr-tenue", "Nessun errore negli ultimi " + er.giorni + " giorni."));
      else {
        s.append(el("p", "cr-sintesi", er.n + " negli ultimi " + er.giorni + " giorni: "
          + (er.per_tipo || []).map((x) => x.tipo + " " + x.n).join(", ")));
        const ul = el("ul", "cr-lista");
        (er.recenti || []).forEach((x) => ul.append(el("li", "cr-tenue", x.quando.replace("T", " ") + " · " + x.tipo)));
        s.append(ul);
        comando(s, "Dettagli da terminale: " + er.comando);
      }
    }

    // Richieste in attesa
    s = sezione(corpo, "In attesa");
    const at = d.attesa || {};
    if (!nonLetto(s, d.attesa)) {
      const t = at.tutori || {};
      s.append(el("p", t.n ? "" : "cr-tenue", "Avvisi ai tutori non ancora detti: " + (t.n || 0)
        + (t.urgenti ? " (" + t.urgenti + " importanti)" : "") + (t.n ? ": " + t.nota : "")));
      const es = (at.estensioni || {}).da_approvare || [];
      s.append(el("p", es.length ? "" : "cr-tenue", "Estensioni da approvare: " + (es.length
        ? es.map((x) => x.nome + " (versione " + x.versione + (x.test_passano ? "" : ", test che non passano") + ")").join(", ")
        : "nessuna")));
      if (es.length) comando(s, at.estensioni.comando);
      const lv = at.lavori;
      if (lv && !lv.errore) {
        s.append(el("p", lv.in_attesa ? "" : "cr-tenue", "Lavori che aspettano una risposta: " + lv.in_attesa
          + " · in coda o in corso: " + lv.attivi));
        if (lv.in_attesa) comando(s, lv.comando);
      } else if (lv && lv.errore) s.append(el("p", "cr-avviso", "Lavori: " + lv.errore));
      else s.append(el("p", "cr-tenue", "Agenti non configurati."));
    }
  };

  // ─── scrivere invece di parlare (03/10, calliope/schermi/moduli.py) ───
  // I controlli dei codici sono gli stessi del server (controlla_campo): qui servono a
  // vedere l'errore mentre si scrive, là decidono
  const CF_DISPARI = [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14,
    16, 10, 22, 25, 24, 23];
  const IBAN_LUNGHEZZA = { IT: 27, SM: 27, VA: 22, DE: 22, FR: 27, ES: 24, AT: 20, CH: 21,
    BE: 16, NL: 18, PT: 25, GB: 22, IE: 22, LU: 20, SI: 19, HR: 21, MT: 31, GR: 27, PL: 28 };
  const compatto = (v) => String(v || "").replace(/[\s.\-/]/g, "").toUpperCase();

  function pivaOk(p) {
    if (!/^\d{11}$/.test(p) || p === "00000000000") return false;
    let s = 0;
    for (let i = 0; i < 10; i++) {
      let d = Number(p[i]);
      if (i % 2 === 1) { d *= 2; if (d > 9) d -= 9; }
      s += d;
    }
    return (10 - (s % 10)) % 10 === Number(p[10]);
  }
  function cfOk(cf) {
    let s = 0;
    for (let i = 0; i < 15; i++) {
      const ch = cf[i];
      const dig = ch >= "0" && ch <= "9";
      if (i % 2 === 0) s += dig ? CF_DISPARI[Number(ch)] : CF_DISPARI[ch.charCodeAt(0) - 65];
      else s += dig ? Number(ch) : ch.charCodeAt(0) - 65;
    }
    return String.fromCharCode(65 + (s % 26)) === cf[15];
  }
  function ibanOk(t) {
    const r = t.slice(4) + t.slice(0, 4);
    let m = 0;
    for (const ch of r) {
      for (const d of String(parseInt(ch, 36))) m = (m * 10 + Number(d)) % 97;
    }
    return m === 1;
  }
  function numeroDetto(v) {
    let t = String(v == null ? "" : v).trim().toLowerCase().replace(/[\s€]|euro/g, "");
    if (!t) return null;
    if (/^-?\d{1,3}(\.\d{3})+(,\d+)?$/.test(t)) t = t.replace(/\./g, "").replace(",", ".");
    else t = t.replace(",", ".");
    return /^-?\d+(\.\d+)?$/.test(t) ? Number(t) : null;
  }

  // L'errore di un campo ("" = va bene). `v`: il valore com'è nella pagina
  function erroreCampo(c, v) {
    const vuoto = v == null || (typeof v === "string" && !v.trim()) || (Array.isArray(v) && !v.length);
    if (vuoto) return c.obbligatorio ? "Manca" : "";
    const t = String(v).trim();
    switch (c.tipo) {
      case "testo": return t.length > 200 ? "Al massimo 200 caratteri" : "";
      case "testo_lungo": return t.length > 2000 ? "Al massimo 2000 caratteri" : "";
      case "numero": return numeroDetto(t) === null ? "Scrivi un numero" : "";
      case "importo": {
        const x = numeroDetto(t);
        if (x === null) return "Scrivi un importo, per esempio 1.234,50";
        if (x < 0) return "L'importo non può essere negativo";
        return Math.abs(Math.round(x * 100) - x * 100) > 1e-6 ? "Al massimo due decimali" : "";
      }
      case "data": return /^\d{4}-\d{2}-\d{2}$/.test(t) && !isNaN(Date.parse(t)) ? "" : "Data non valida";
      case "codice_fiscale": {
        const x = compatto(t);
        if (/^\d{11}$/.test(x)) return pivaOk(x) ? "" : "La cifra di controllo non torna";
        if (!/^[A-Z]{6}[0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]$/.test(x))
          return "Servono 16 caratteri (o le 11 cifre di una ditta)";
        return cfOk(x) ? "" : "Il carattere di controllo non torna";
      }
      case "partita_iva": {
        let x = compatto(t);
        if (x.startsWith("IT") && x.length === 13) x = x.slice(2);
        if (!/^\d{11}$/.test(x)) return "Servono 11 cifre";
        return pivaOk(x) ? "" : "La cifra di controllo non torna";
      }
      case "iban": {
        const x = compatto(t);
        if (!/^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$/.test(x)) return "Un IBAN comincia con il paese (IT) e due cifre";
        const n = IBAN_LUNGHEZZA[x.slice(0, 2)];
        if (n && x.length !== n) return "Un IBAN " + x.slice(0, 2) + " ha " + n + " caratteri (qui " + x.length + ")";
        return ibanOk(x) ? "" : "Il codice di controllo non torna";
      }
      case "cap": return /^\d{5}$/.test(t.replace(/\s/g, "")) ? "" : "Il CAP ha 5 cifre";
      case "provincia": return /^[A-Za-z]{2}$/.test(t) || t.length > 2 ? "" : "La sigla ha 2 lettere";
      case "email": return /^[^@\s]+@[^@\s.]+(\.[^@\s.]+)*\.[a-z]{2,}$/i.test(t) ? "" : "Indirizzo email non valido";
      case "codice_destinatario": return /^[A-Z0-9]{7}$/.test(compatto(t)) ? "" : "Il codice destinatario ha 7 caratteri";
      default: return "";
    }
  }
  // Codici di lunghezza nota: l'errore si vede appena si arriva in fondo, senza aspettare
  const LUNGHEZZA = { codice_fiscale: 16, partita_iva: 11, cap: 5, codice_destinatario: 7 };

  async function postSessione(url, dati) {
    const r = await fetch(url, {
      method: "POST", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-Calliope-Sessione": S.sessione || "" },
      body: JSON.stringify(dati),
    });
    let d = {};
    try { d = await r.json(); } catch (e) { /* vuota */ }
    return { status: r.status, dati: d };
  }

  const MESSAGGI = {
    401: "Lo schermo si sta ricollegando: riprova tra un attimo.",
    403: "Da questo schermo non si può.", 409: "Questo modulo non è più aperto.",
    413: "Troppo lungo.", 429: "Troppi invii: aspetta un momento.",
    503: "Calliope è occupata: riprova tra poco.",
  };

  function moduloInCorso() {
    const c = S.corrente;
    if (!c || c.tipo !== "modulo" || c.stato !== "aperto") return false;
    const b = S.bozze[c.modulo];
    return !!(b && Object.keys(b).length) || !!document.activeElement?.closest?.(".modulo");
  }

  function leggiCampo(box, c) {
    if (c.tipo === "righe") {
      return [...box.querySelectorAll(".riga-modulo")].map((r) => {
        const o = {};
        r.querySelectorAll("[data-k]").forEach((i) => { o[i.dataset.k] = i.value; });
        return o;
      }).filter((o) => Object.values(o).some((x) => String(x).trim()));
    }
    const i = box.querySelector("[data-campo]");
    if (!i) return null;
    if (c.tipo === "elenco") return i.value.split("\n").map((x) => x.trim()).filter(Boolean);
    if (c.tipo === "booleano") return i.value === "" ? null : i.value === "si";
    return i.value;
  }

  function erroreRighe(c, righe) {
    if (!righe.length) return c.obbligatorio ? "Manca almeno una riga" : "";
    for (let i = 0; i < righe.length; i++) {
      const r = righe[i];
      if (!String(r.descrizione || "").trim()) return "Riga " + (i + 1) + ": manca la descrizione";
      if (String(r.quantita || "").trim()) {
        const q = numeroDetto(r.quantita);
        if (q === null || q <= 0) return "Riga " + (i + 1) + ": quantità non valida";
      } else if (c.prezzi === false) return "Riga " + (i + 1) + ": manca la quantità";
      if (c.prezzi !== false) {
        const p = numeroDetto(r.prezzo);
        if (p === null || p < 0) return "Riga " + (i + 1) + ": manca il prezzo";
      }
    }
    return "";
  }

  function rigaModulo(c, valori) {
    const r = el("div", "riga-modulo");
    const campi = c.prezzi === false
      ? [["descrizione", "Descrizione"], ["quantita", "Quantità"], ["unita", "Unità"]]
      : [["descrizione", "Descrizione"], ["quantita", "Quantità"], ["prezzo", "Prezzo €"]];
    campi.forEach(([k, et]) => {
      const i = el("input");
      i.type = "text";
      i.dataset.k = k;
      i.placeholder = et;
      i.setAttribute("aria-label", et);
      if (k !== "descrizione" && k !== "unita") i.inputMode = "decimal";
      i.value = valori && valori[k] != null ? valori[k] : "";
      r.append(i);
    });
    return r;
  }

  function campoModulo(c, bozza) {
    const box = el("div", "campo-modulo tipo-" + c.tipo);
    box.dataset.nome = c.nome;
    const id = "m-" + c.nome + "-" + Math.random().toString(36).slice(2, 8);
    const lab = el("label", "", c.etichetta + (c.obbligatorio ? "" : " (facoltativo)"));
    lab.htmlFor = id;
    box.append(lab);
    const valore = bozza && c.nome in bozza ? bozza[c.nome] : c.valore;
    let input;
    if (c.tipo === "righe") {
      const g = el("div", "righe-modulo");
      g.id = id;
      const iniziali = Array.isArray(valore) && valore.length ? valore : [null, null];
      iniziali.forEach((v) => g.append(rigaModulo(c, v)));
      box.append(g);
      const piu = el("button", "piccolo-bottone", "Aggiungi una riga");
      piu.type = "button";
      piu.addEventListener("click", () => { g.append(rigaModulo(c, null)); });
      box.append(piu);
    } else if (c.tipo === "testo_lungo" || c.tipo === "elenco") {
      input = el("textarea");
      input.rows = c.tipo === "elenco" ? 4 : 3;
      input.maxLength = 2000;
      input.value = Array.isArray(valore) ? valore.join("\n") : (valore || "");
      if (c.tipo === "elenco") input.placeholder = "Una voce per riga";
    } else if (c.tipo === "scelta" || c.tipo === "booleano") {
      input = el("select");
      const opz = c.tipo === "booleano" ? [["", "—"], ["si", "sì"], ["no", "no"]]
        : [["", "Scegli…"]].concat((c.opzioni || []).map((o) => [o, o]));
      opz.forEach(([v, t]) => { const o = el("option", "", t); o.value = v; input.append(o); });
      input.value = c.tipo === "booleano" ? (valore === true ? "si" : valore === false ? "no" : (valore || ""))
        : (valore || "");
    } else {
      input = el("input");
      input.type = c.tipo === "data" ? "date" : c.tipo === "email" ? "email" : "text";
      input.value = valore == null ? "" : String(valore);
      input.maxLength = c.tipo === "iban" ? 42 : 200;
      if (["numero", "importo"].includes(c.tipo)) input.inputMode = "decimal";
      if (["partita_iva", "cap"].includes(c.tipo)) input.inputMode = "numeric";
      if (["codice_fiscale", "iban", "codice_destinatario", "provincia"].includes(c.tipo)) {
        input.autocapitalize = "characters";
        input.spellcheck = false;
        input.autocomplete = "off";
      }
      if (c.suggerimenti && c.suggerimenti.length) {
        const dl = el("datalist");
        dl.id = id + "-elenco";
        c.suggerimenti.forEach((s) => { const o = el("option"); o.value = s; dl.append(o); });
        box.append(dl);
        input.setAttribute("list", dl.id);
      }
    }
    if (input) {
      input.id = id;
      input.dataset.campo = c.nome;
      box.append(input);
    }
    const err = el("div", "errore-campo", c.errore || "");
    err.id = id + "-errore";
    err.setAttribute("aria-live", "polite");
    if (input) input.setAttribute("aria-describedby", err.id);
    if (c.errore) box.classList.add("sbagliato");
    box.append(err);
    return box;
  }

  function mostraErrore(box, testo) {
    box.querySelector(".errore-campo").textContent = testo || "";
    box.classList.toggle("sbagliato", !!testo);
  }

  DISEGNA.modulo = function (c, corpo) {
    if (c.domanda) corpo.append(el("p", "domanda-modulo", c.domanda));
    if (c.stato !== "aperto" || !c.campi || !c.campi.length) {
      corpo.append(el("p", "nota-modulo", c.nota || "Il modulo è chiuso."));
      return;
    }
    const bozza = S.bozze[c.modulo] || (S.bozze[c.modulo] = {});
    const f = el("form", "modulo");
    f.noValidate = true;
    const campi = c.campi.map((x) => {
      const box = campoModulo(x, bozza);
      f.append(box);
      let toccato = !!x.errore;
      const controlla = (subito) => {
        const v = leggiCampo(box, x);
        bozza[x.nome] = v;
        const e = x.tipo === "righe" ? erroreRighe(x, v) : erroreCampo(x, v);
        const pieno = LUNGHEZZA[x.tipo] && compatto(v).length >= LUNGHEZZA[x.tipo];
        if (subito || toccato || pieno) { toccato = toccato || subito || pieno; mostraErrore(box, e); }
        return e;
      };
      box.addEventListener("input", () => controlla(false));
      box.addEventListener("change", () => controlla(false));
      box.addEventListener("focusout", () => { if (String(leggiCampo(box, x) || "").length) controlla(true); });
      return { x, box, controlla };
    });
    const piede = el("div", "piede-modulo");
    const invia = el("button", "invia-modulo", "Invia");
    invia.type = "submit";
    const esito = el("p", "esito-modulo");
    esito.setAttribute("role", "status");
    piede.append(invia, esito);
    f.append(piede);
    statoModulo(f);
    f.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const errori = campi.map((k) => [k, k.controlla(true)]).filter(([, e]) => e);
      if (errori.length) {
        esito.textContent = "Controlla i campi segnati.";
        const primo = errori[0][0].box.querySelector("input, textarea, select");
        if (primo) primo.focus();
        return;
      }
      const valori = {};
      campi.forEach(({ x, box }) => { valori[x.nome] = leggiCampo(box, x); });
      if (!S.scrittura.attiva) { statoModulo(f); return; }
      invia.disabled = true;
      esito.textContent = "Invio…";
      let r;
      try { r = await postSessione("/api/modulo", { modulo: c.modulo, valori }); }
      catch (e) { r = null; }
      invia.disabled = !S.scrittura.attiva;
      if (r && r.status === 200) {
        delete S.bozze[c.modulo];
        f.querySelectorAll("input, textarea, select, button").forEach((i) => { i.disabled = true; });
        esito.textContent = "Inviato: ti rispondo.";
        f.classList.add("inviato");
        return;
      }
      if (r && r.status === 422 && r.dati.errori) {
        campi.forEach(({ x, box }) => mostraErrore(box, r.dati.errori[x.nome] || ""));
        esito.textContent = "Controlla i campi segnati.";
        return;
      }
      if (r && r.dati && r.dati.codice === "senza_conversazione") {
        applicaScrittura({ attiva: false, testo: r.dati.errore });
        return;
      }
      esito.textContent = r ? (r.dati.errore || MESSAGGI[r.status] || "Non è andato: riprova.")
        : "Calliope non risponde: riprova.";
    });
    corpo.append(f);
  };

  // ─── scrivere solo durante una conversazione (05/10) ───
  // Senza una conversazione cominciata a voce la casella e «Invia» dei moduli sono spenti,
  // con «Di' «Calliope» per scrivermi»; si riaccendono da soli all'evento «scrittura». I campi
  // dei moduli restano scrivibili (la bozza non si perde): si spegne solo l'invio
  function notaScrittura(dentro, prima) {
    let n = dentro.querySelector(":scope > .nota-scrittura");
    if (!n) {
      n = el("p", "nota-scrittura");
      n.setAttribute("role", "status");
      if (prima) dentro.insertBefore(n, prima); else dentro.append(n);
    }
    n.textContent = S.scrittura.attiva ? "" : (S.scrittura.testo || "Di' «Calliope» per scrivermi.");
    n.hidden = !!S.scrittura.attiva;
  }

  function statoModulo(f) {
    if (f.classList.contains("inviato")) return;
    const b = f.querySelector(".invia-modulo");
    if (b) b.disabled = !S.scrittura.attiva;
    f.classList.toggle("spento", !S.scrittura.attiva);
    notaScrittura(f, f.querySelector(".piede-modulo"));
  }

  function applicaScrittura(st) {
    S.scrittura = { attiva: !!(st && st.attiva), testo: (st && st.testo) || "" };
    document.querySelectorAll("form.modulo").forEach(statoModulo);
    const f = $("scrivi");
    if (f) {
      const i = $("scrivi-testo");
      const b = f.querySelector("button");
      i.disabled = b.disabled = !S.scrittura.attiva;
      // La foto come la casella: «Foto» spento, e una foto pronta e non mandata si toglie
      const bf = $("scrivi-foto");
      if (bf) bf.disabled = !S.scrittura.attiva;
      if (!S.scrittura.attiva && (S.foto || S.file) && S.togliFoto) S.togliFoto();
      f.classList.toggle("spento", !S.scrittura.attiva);
      i.placeholder = !S.scrittura.attiva ? "Di' «" + S.parola + "» per scrivermi"
        : S.personale ? "Scrivi a Calliope invece di parlare…"
          : "Scrivi a Calliope (da qui vale come un ospite)…";
      notaScrittura(f);
    }
    emetti("scrivi", { attiva: S.capace, personale: S.personale, abilitata: S.scrittura.attiva,
      testo: S.scrittura.testo, parola: S.parola });
  }

  // Foto (05/10, calliope/immagini.py): dal pulsante «Foto» (sul telefono fotocamera o
  // libreria), trascinando un file sulla pagina o incollandola con Ctrl+V. Si riduce qui
  // (lato lungo FOTO_LATO, JPEG) prima di mandarla: il server la ricontrolla e la riduce
  // di nuovo. Solo dagli schermi personali; la foto non resta nella pagina dopo l'invio
  const FOTO_LATO = 1600;
  const FOTO_MAX_BYTE = 30 * 1024 * 1024;
  function leggiFoto(file) {
    return new Promise((ok, no) => {
      if (!file || !/^image\//.test(file.type || "image/") || /svg/i.test(file.type || "")) {
        no(new Error("Questo file non è una foto.")); return;
      }
      if (file.size > FOTO_MAX_BYTE) { no(new Error("La foto è troppo grande.")); return; }
      const rd = new FileReader();
      rd.onerror = () => no(new Error("Non riesco a leggere la foto."));
      rd.onload = () => {
        const img = new Image();
        img.onerror = () => no(new Error("Formato non leggibile: prova con un JPEG o un PNG."));
        img.onload = () => {
          const k = Math.min(1, FOTO_LATO / Math.max(img.naturalWidth, img.naturalHeight));
          const w = Math.max(1, Math.round(img.naturalWidth * k));
          const h = Math.max(1, Math.round(img.naturalHeight * k));
          const cv = document.createElement("canvas");
          cv.width = w; cv.height = h;
          const g = cv.getContext("2d");
          g.fillStyle = "#fff"; g.fillRect(0, 0, w, h);      // PNG trasparenti: fondo bianco
          g.drawImage(img, 0, 0, w, h);
          ok({ url: cv.toDataURL("image/jpeg", 0.85), w, h });
        };
        img.src = rd.result;
      };
      rd.readAsDataURL(file);
    });
  }
  // Allegati (05/10, calliope/allegati.py): qualsiasi file. Le foto (image/*, non SVG) si
  // riducono qui come prima; gli altri file partono com'erano, byte nudi verso
  // /api/allegato, e il server ne riconosce il tipo vero dai byte
  const FILE_MAX_BYTE = 25 * 1000 * 1000;
  function eFoto(file) {
    return /^image\//.test(file.type || "") && !/svg/i.test(file.type || "");
  }
  function dimensione(n) {
    if (n < 1024) return n + " byte";
    if (n < 1048576) return Math.round(n / 1024) + " kB";
    return (n / 1048576).toFixed(1).replace(".", ",") + " MB";
  }
  function fotoDaEvento(lista) {
    for (const it of Array.from(lista || [])) {
      const file = it.kind ? (it.kind === "file" ? it.getAsFile() : null) : it;
      if (file) return file;
    }
    return null;
  }
  async function postFile(file, testo) {
    const r = await fetch("/api/allegato", {
      method: "POST", cache: "no-store", body: file,
      headers: { "Content-Type": "application/octet-stream", "X-Calliope-Sessione": S.sessione || "",
                 "X-Calliope-Nome": encodeURIComponent(file.name || "file"),
                 "X-Calliope-Testo": encodeURIComponent(testo || ""),
                 "X-Calliope-Fonte": INCORPORATA ? "telefono" : "schermo" },
    });
    let d = {};
    try { d = await r.json(); } catch (e) { /* vuota */ }
    return { status: r.status, dati: d };
  }

  // La casella «scrivi invece di parlare»: sotto le schede, sugli schermi personali (e su
  // quelli di stanza se la configurazione lo vuole: lì chi scrive conta come ospite)
  function casellaScrivi(attiva, personale) {
    let f = $("scrivi");
    S.capace = !!attiva;
    S.personale = !!personale;
    S.fotoAmmessa = !!(attiva && personale);
    if (!attiva) {
      emetti("scrivi", { attiva: false, personale: !!personale, abilitata: false });
      if (f) f.hidden = true;
      return;
    }
    if (!f) {
      f = el("form", "scrivi");
      f.id = "scrivi";
      f.noValidate = true;
      const i = el("input");
      i.type = "text";
      i.id = "scrivi-testo";
      i.maxLength = 500;
      i.autocomplete = "off";
      i.setAttribute("aria-label", "Scrivi a Calliope");
      const b = el("button", "", "Invia");
      b.type = "submit";
      const esito = el("span", "esito-scrivi");
      esito.setAttribute("role", "status");
      // «Allega» (05/10): input nascosto senza «accept» (su iOS e Android offre fotocamera,
      // libreria e file; niente getUserMedia), pulsante e anteprima con «Togli». Una foto si
      // riduce qui (canvas); un altro file mostra nome, tipo e dimensione e parte intero
      const file = el("input");
      file.type = "file";
      file.id = "scrivi-foto-file";
      file.hidden = true;
      const bf = el("button", "foto-apri", "Allega");
      bf.type = "button";
      bf.id = "scrivi-foto";
      bf.setAttribute("aria-label", "Allega una foto o un file per Calliope");
      const ante = el("div", "foto-anteprima");
      ante.id = "scrivi-anteprima";
      ante.hidden = true;
      const mini = el("img");
      mini.alt = "La foto da mandare";
      const info = el("span", "allegato-info");
      info.hidden = true;
      const togli = el("button", "piccolo-bottone", "Togli");
      togli.type = "button";
      ante.append(mini, info, togli);
      const via = () => {
        S.foto = null; S.file = null; ante.hidden = true; info.hidden = true;
        mini.hidden = false; mini.removeAttribute("src");
      };
      S.togliFoto = via;
      const metti = async (fl) => {
        if (!fl || !S.fotoAmmessa) return;
        // Solo durante una conversazione a voce (05/10), come la casella
        if (!S.scrittura.attiva) { esito.textContent = S.scrittura.testo || "Di' «" + S.parola + "» per scrivermi."; return; }
        via();
        if (fl.size > FILE_MAX_BYTE) { esito.textContent = "Il file è troppo grande (al massimo 25 MB)."; return; }
        if (eFoto(fl)) {
          esito.textContent = "Preparo la foto…";
          try {
            S.foto = await leggiFoto(fl);
            mini.src = S.foto.url;
            ante.hidden = false;
            esito.textContent = "Scrivi cosa vuoi sapere (o dimmelo a voce) e premi Invia.";
            i.placeholder = "Cosa vuoi sapere di questa foto?";
            i.focus();
          } catch (e) {
            via();
            esito.textContent = e.message;
          }
          return;
        }
        S.file = fl;
        mini.hidden = true;
        info.textContent = (fl.name || "file") + " · " + dimensione(fl.size);
        info.hidden = false;
        ante.hidden = false;
        esito.textContent = "Scrivi cosa vuoi sapere (o dimmelo a voce) e premi Invia.";
        i.placeholder = "Cosa vuoi sapere di questo file?";
        i.focus();
      };
      bf.addEventListener("click", () => file.click());
      file.addEventListener("change", () => { const fl = file.files && file.files[0]; file.value = ""; metti(fl); });
      togli.addEventListener("click", () => { via(); esito.textContent = ""; });
      // Trascina e rilascia e incolla, su tutta la pagina
      document.addEventListener("dragover", (ev) => {
        if (!S.fotoAmmessa || !ev.dataTransfer || !Array.from(ev.dataTransfer.types || []).includes("Files")) return;
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "copy";
        document.body.classList.add("trascina-foto");
      });
      document.addEventListener("dragleave", (ev) => { if (!ev.relatedTarget) document.body.classList.remove("trascina-foto"); });
      document.addEventListener("drop", (ev) => {
        document.body.classList.remove("trascina-foto");
        if (!S.fotoAmmessa || !ev.dataTransfer) return;
        const fl = fotoDaEvento(ev.dataTransfer.files);
        if (!fl) return;
        ev.preventDefault();
        metti(fl);
      });
      document.addEventListener("paste", (ev) => {
        if (!S.fotoAmmessa || !ev.clipboardData) return;
        const fl = fotoDaEvento(ev.clipboardData.items);
        if (!fl) return;
        ev.preventDefault();
        metti(fl);
      });
      // Invia resta il primo pulsante del modulo (le prove e chi lo cerca con «#scrivi
      // button»); l'anteprima va sopra con l'«order» del CSS
      f.append(i, b, bf, esito, ante, file);
      f.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const testo = i.value.trim();
        const foto = S.foto, allegato = S.file;
        if ((!testo && !foto && !allegato) || !S.scrittura.attiva) return;
        b.disabled = true;
        if (allegato) esito.textContent = "Mando il file…";
        let r;
        try {
          r = foto ? await postSessione("/api/immagine", { immagine: foto.url, testo,
                                                           fonte: INCORPORATA ? "telefono" : "schermo" })
            : allegato ? await postFile(allegato, testo)
              : await postSessione("/api/scrivi", { testo });
        } catch (e) { r = null; }
        b.disabled = !S.scrittura.attiva;
        if (r && r.dati && r.dati.codice === "senza_conversazione") {
          applicaScrittura({ attiva: false, testo: r.dati.errore });
          return;
        }
        if (r && r.status === 200) {
          i.value = "";
          if (foto || allegato) { via(); i.placeholder = "Scrivi a Calliope invece di parlare…"; }
          esito.textContent = (foto || allegato) && !testo
            ? (foto ? "Foto inviata" : "File inviato") + ": dimmi o scrivi cosa vuoi sapere."
            : "Inviato: ti rispondo qui.";
          emetti("scritto", {});
          setTimeout(() => { if (esito.textContent.startsWith("Inviato")) esito.textContent = ""; }, 5000);
        } else {
          esito.textContent = r ? (r.dati.errore || MESSAGGI[r.status] || "Non è andato.") : "Calliope non risponde.";
        }
      });
      const posto = $("scrivi-posto");
      const dopo = $("cronologia");
      if (posto) posto.append(f);
      else if (dopo && dopo.parentNode) dopo.after(f); else document.body.append(f);
    }
    $("scrivi-foto").hidden = !personale;
    f.hidden = false;
    applicaScrittura(S.scrittura);
  }

  // ─── l'avanzamento di un lavoro dell'agente (03/10) ───
  function durata(s) {
    s = Math.max(0, Math.floor(s));
    return Math.floor(s / 60) + ":" + dueCifre(s % 60);
  }

  // I tetti del lavoro: le sole barre oneste (quanto ne ha usato su quanto gliene è concesso
  // al massimo), non una percentuale di «quanto manca», che nessuno conosce
  function tettiLavoro(av, vivo) {
    const g = el("div", "tetti-lavoro");
    function barra(nome, val, max, testo, dal) {
      const r = el("div", "tetto");
      r.append(el("div", "tetto-nome", nome));
      const b = el("div", "tetto-barra");
      const sp = el("span");
      sp.style.width = (max > 0 ? Math.min(100, (val / max) * 100) : 0) + "%";
      b.append(sp);
      r.append(b);
      const t = el("div", "tetto-valore", testo);
      if (dal) { t.dataset.dal = String(dal * 1000); t.dataset.max = String(max); }
      r.append(t);
      g.append(r);
    }
    const tr = av.trascorso_s || 0;
    barra("Tempo", tr, av.max_s, durata(tr) + " di " + Math.round(av.max_s / 60) + " min al massimo",
      vivo && av.dal ? av.dal : null);
    barra("Passate", av.passate || 0, av.max_passate, (av.passate || 0) + " di " + av.max_passate + " al massimo");
    barra("Token", av.token || 0, av.max_token,
      (av.token || 0).toLocaleString("it-IT") + " di " + (av.max_token || 0).toLocaleString("it-IT") + " al massimo");
    return g;
  }

  function passiLavoro(passi) {
    const box = el("section", "passi-lavoro");
    box.append(el("div", "nome-file", "Ultimi passi"));
    const ul = el("ol");
    passi.slice().reverse().forEach((p) => {
      const li = el("li");
      li.append(el("span", "ora-passo", fmtOraSec.format(new Date(p.ora * 1000))));
      li.append(el("span", "", p.testo));
      ul.append(li);
    });
    box.append(ul);
    return box;
  }

  function disegnaAvanzamento(c, av, corpo) {
    const meta = el("p", "sotto", STATI_LAVORO[c.stato] || c.stato || "");
    if (av.pausa) meta.append(el("span", "badge pausa", "in pausa: sto rispondendo a voce"));
    corpo.append(meta);
    if (av.passo) corpo.append(el("p", "passo-lavoro" + (av.pausa ? " fermo" : ""), "Adesso: " + av.passo));
    if (c.test) {
      const t = c.test, ko = (t.falliti || 0) + (t.errori || 0), n = Math.max(t.eseguiti || 0, ko);
      corpo.append(el("p", "test-lavoro" + (ko ? " ko" : " ok"),
        "Test: " + (n ? (n - ko) + " su " + n + " passano" : "nessuno trovato")));
    }
    if (c.stato === "in_corso") corpo.append(tettiLavoro(av, !av.pausa));
    if (av.flusso && av.flusso.testo) {
      const b = el("section", "flusso-lavoro");
      b.append(el("div", "nome-file", FLUSSO_LAVORO[av.flusso.tipo] || "Sta scrivendo"));
      const pre = el("pre", "flusso " + av.flusso.tipo, av.flusso.testo);
      b.append(pre);
      corpo.append(b);
      pre.dataset.segui = "1";
    }
    if (av.file && av.file.length) {
      const b = el("section", "file-lavoro");
      b.append(el("div", "nome-file", "File scritti finora"));
      const ul = el("ul", "elenco-file");
      av.file.forEach((f) => ul.append(el("li", "", f.nome + (f.righe ? " · " + f.righe + (f.righe === 1 ? " riga" : " righe") : ""))));
      b.append(ul);
      if (av.anteprima) {
        b.append(el("div", "nome-file", "Inizio di " + av.anteprima.nome));
        b.append(el("pre", "codice anteprima", av.anteprima.testo));
      }
      corpo.append(b);
    }
    if (av.passi && av.passi.length) corpo.append(passiLavoro(av.passi));
  }

  const NUMERO = /^\s*-?(€\s*)?[\d.]+(,\d+)?\s*(€|%)?\s*$/;
  function tabella(b) {
    const t = el("table");
    const cols = b.colonne || [];
    const righe = b.righe || [];
    const num = cols.map((_, i) => righe.length > 0 && righe.every((r) => r[i] === undefined || r[i] === "" || NUMERO.test(String(r[i]))));
    const th = el("tr");
    cols.forEach((c, i) => th.append(el("th", num[i] ? "num" : "", c)));
    const thead = el("thead"); thead.append(th); t.append(thead);
    const tb = el("tbody");
    righe.forEach((r) => {
      const tr = el("tr");
      cols.forEach((_, i) => tr.append(el("td", num[i] ? "num" : "", r[i] === undefined ? "" : r[i])));
      tb.append(tr);
    });
    if (b.totale) {
      const tr = el("tr", "totale");
      cols.forEach((_, i) => tr.append(el("td", num[i] ? "num" : "", b.totale[i] || "")));
      tb.append(tr);
    }
    t.append(tb);
    return t;
  }

  // ─── uso del contesto (05/10): barra discreta nella testa, solo schermi personali ───
  function mostraContesto(c) {
    const box = $("contesto");
    if (INCORPORATA || !box) return;       // il telefono non la disegna
    const p = c && Number.isFinite(c.percento) ? Math.max(0, Math.min(100, c.percento)) : null;
    if (p === null) { box.hidden = true; return; }
    box.hidden = false;
    box.classList.toggle("alto", p >= 75);
    box.querySelector(".contesto-barra span").style.width = p + "%";
    $("contesto-testo").textContent = "memoria " + p + "%";
    box.title = "Conversazione: " + c.token.toLocaleString("it-IT") + " token su " +
      c.finestra.toLocaleString("it-IT");
  }

  // ─── stato della voce ───
  function mostraVoce(v) {
    if (INCORPORATA) return;              // lo stato lo disegna il telefono
    const box = $("voce");
    S.voce = v && TESTI_VOCE[v.stato] ? v : null;
    if (!S.voce) { box.hidden = true; return; }
    S.voceTotale = S.voce.fino ? Math.max(1, S.voce.fino * 1000 - ora()) : 0;
    box.hidden = false;
    disegnaVoce();
  }

  function disegnaVoce() {
    const v = S.voce;
    if (!v) return;
    let stato = v.stato;
    let resto = "";
    const box = $("voce");
    if (stato === "ascolta" && v.fino) {
      const ms = v.fino * 1000 - ora();
      if (ms <= 0) {                     // finestra di follow-up finita: si riaddormenta
        S.voce = { stato: "dorme", fino: null };
        stato = "dorme";
      } else {
        resto = Math.ceil(ms / 1000) + " s";
        box.querySelector(".voce-barra span").style.width =
          Math.max(0, Math.min(100, (ms / S.voceTotale) * 100)) + "%";
      }
    }
    box.className = "voce " + stato + (resto ? " conta" : "");
    box.querySelector(".voce-testo").textContent = TESTI_VOCE[stato];
    box.querySelector(".voce-resto").textContent = resto;
  }

  // ─── orologio e conti alla rovescia ───
  function mostraInattiva() {
    S.vista = "inattiva";
    const m = $("principale");
    if (m) m.replaceChildren();
    if (CAROSELLO) { emetti("schede", {}); return; }
    if (INCORPORATA) { disegnaCronologia(); return; }   // niente orologio grande
    const box = el("section", "inattiva");
    box.append(el("div", "ora", ""));
    box.append(el("div", "data", ""));
    m.append(box);
    disegnaCronologia();
    aggiornaOrologio();
  }

  function aggiornaOrologio() {
    const d = new Date(ora());
    if (!$("orologio-piccolo")) return;
    $("orologio-piccolo").textContent = S.vista === "inattiva" ? "" : fmtOra.format(d);
    const o = document.querySelector(".inattiva .ora");
    if (o) {
      o.textContent = fmtOra.format(d);
      document.querySelector(".inattiva .data").textContent = fmtData.format(d);
    }
  }

  function dueCifre(n) { return String(n).padStart(2, "0"); }

  // Il tempo di un lavoro in corso conta da solo tra un aggiornamento e l'altro
  function aggiornaLavori() {
    document.querySelectorAll(".tempo-esecuzione[data-dal-esec]").forEach((e) => {
      const s = (ora() - Number(e.dataset.dalEsec)) / 1000;
      e.textContent = secondiDetti(s) + " di " + e.dataset.max + " s al massimo";
    });
    document.querySelectorAll(".tetto-valore[data-dal]").forEach((e) => {
      const s = (ora() - Number(e.dataset.dal)) / 1000;
      const max = Number(e.dataset.max) || 0;
      e.textContent = durata(s) + " di " + Math.round(max / 60) + " min al massimo";
      const sp = e.parentElement.querySelector(".tetto-barra span");
      if (sp && max > 0) sp.style.width = Math.min(100, (s / max) * 100) + "%";
    });
  }

  function aggiornaTimer() {
    document.querySelectorAll(".resto[data-fine]").forEach((e) => {
      const ms = Number(e.dataset.fine) - ora();
      const riga = e.parentElement;
      if (ms <= 0) {
        e.textContent = "Finito";
        riga.classList.add("finito");
        return;
      }
      const s = Math.ceil(ms / 1000);
      const h = Math.floor(s / 3600);
      const m = Math.floor((s % 3600) / 60);
      e.textContent = (h ? h + ":" + dueCifre(m) : m) + ":" + dueCifre(s % 60);
    });
  }

  // ─── giochi (05/10, calliope/schermi/giochi.py, calliope/estensioni/scheda.py) ───
  // Il riquadro di un gioco: <iframe sandbox="allow-scripts"> senza allow-same-origin, con il
  // documento da /gioco/<gettone> (origine opaca, la sua CSP: niente rete). Non vede questa
  // pagina, la sessione, le altre schede né localStorage. Parla solo con postMessage: qui ogni
  // messaggio si controlla (sorgente, forma, campi, dimensione, frequenza) e va al server
  // (POST /api/gioco), che lo ricontrolla. Il cane da guardia chiude un riquadro che non
  // risponde ai «ping», che manda troppi messaggi o che prova a cambiare pagina.
  const TIPI_DAL_RIQUADRO = {
    pronto: [], pong: ["n"], salva: ["chiave", "valore"], leggi: ["chiave"], manda: ["dati"],
    chat: ["testo"], di: ["testo"], azione: ["nome", "argomenti"], fine: ["esito"],
    errore: ["testo"],
  };
  const CON_RISPOSTA = ["salva", "leggi", "chat", "di", "azione"];
  const GIOCO_MAX = 8192;            // caratteri di un messaggio (il server ha il suo tetto)
  const GIOCO_AL_SECONDO = 25;       // oltre: il riquadro si chiude
  const BATTITO_MS = 15000;          // tempo di gioco (minori): un battito mentre si vede
  const STATO_GIOCHI = new WeakMap();
  const GIOCHI_CHIUSI = {};          // partita → nota (resta chiuso anche se si ridisegna)

  function riquadri() { return [...document.querySelectorAll("iframe.riquadro-gioco")]; }
  function statoGioco(f) {
    let st = STATO_GIOCHI.get(f);
    if (!st) {
      st = { finestra: null, pronto: null, pong: 0, nPing: 0, ultimoPing: 0, inviati: [],
             scartati: 0, chiuso: false, nascita: Date.now(), battito: Date.now() };
      STATO_GIOCHI.set(f, st);
    }
    return st;
  }
  function versoRiquadro(f, m) {
    try { f.contentWindow.postMessage(Object.assign({ calliope: 1 }, m), "*"); } catch (e) { /* chiuso */ }
  }
  async function alServerGioco(partita, dati) {
    try {
      return await postSessione("/api/gioco", Object.assign({ partita }, dati));
    } catch (e) {
      return { status: 0, dati: { errore: "Calliope non risponde" } };
    }
  }
  function giocoInCorso() {
    const c = S.corrente;
    return !!(c && c.tipo === "gioco" && !GIOCHI_CHIUSI[c.partita]
      && document.querySelector("#principale iframe.riquadro-gioco"));
  }
  function chiudiGioco(f, nota, motivo) {
    const st = statoGioco(f);
    if (st.chiuso) return;
    st.chiuso = true;
    const partita = f.dataset.partita;
    GIOCHI_CHIUSI[partita] = nota;
    const box = f.parentElement;
    f.remove();                       // il riquadro sparisce: niente più codice del gioco
    if (box) box.replaceChildren(el("p", "nota gioco-chiuso", nota));
    if (motivo) alServerGioco(partita, { tipo: "guasto", motivo });
    if (motivo === "non risponde") {
      // Un riquadro bloccato in un ciclo infinito tiene occupato il suo processo, e il
      // browser lo riusa per il riquadro dopo: la pagina si ricarica (la cronologia torna dal
      // server, con la scheda chiusa). Sul telefono no: si perderebbero voce e microfono
      if (!INCORPORATA) setTimeout(() => location.reload(), 3000);
      else box && box.append(el("p", "nota", "Per giocare ancora, riapri Calliope."));
    }
  }

  DISEGNA.gioco = function (c, corpo, s) {
    s.classList.add("scheda-gioco");
    const chiuso = GIOCHI_CHIUSI[c.partita];
    if (chiuso || c.stato === "chiuso") {
      corpo.append(el("p", "nota gioco-chiuso", chiuso || c.nota || "Il gioco è chiuso."));
      return;
    }
    if (typeof c.doc !== "string" || !/^\/gioco\/[A-Za-z0-9_-]{20,}$/.test(c.doc)) {
      corpo.append(el("p", "nota", "Questo gioco non si può aprire."));
      return;
    }
    const box = el("div", "riquadro-box");
    const f = document.createElement("iframe");
    f.className = "riquadro-gioco";
    f.setAttribute("sandbox", "allow-scripts");
    f.setAttribute("allow", "camera 'none'; microphone 'none'; geolocation 'none'; "
      + "autoplay 'none'; fullscreen 'none'; payment 'none'; usb 'none'; serial 'none'; "
      + "display-capture 'none'; clipboard-read 'none'; clipboard-write 'none'");
    f.setAttribute("referrerpolicy", "no-referrer");
    f.setAttribute("title", c.titolo || "Gioco");
    f.dataset.partita = String(c.partita || "");
    f.dataset.watchdog = String(Number(c.watchdog_s) || 6);
    f.setAttribute("src", c.doc);
    f.addEventListener("load", () => {
      const st = statoGioco(f);
      // Spostato nella pagina (il carosello): un riquadro nuovo, si riparte. Lo stesso che
      // carica un'altra pagina: ha provato a navigare, si chiude
      if (st.finestra && st.finestra === f.contentWindow) {
        chiudiGioco(f, "Il gioco ha provato a cambiare pagina: l'ho chiuso.", "navigazione");
        return;
      }
      if (st.finestra) st.nascita = Date.now();     // spostato: un riquadro nuovo
      st.finestra = f.contentWindow;
    });
    box.append(f);
    corpo.append(box);
  };

  window.addEventListener("message", (ev) => {
    const f = riquadri().find((x) => x.contentWindow === ev.source);
    if (!f) return;                       // non è un nostro riquadro
    const st = statoGioco(f);
    if (st.chiuso) return;
    const m = ev.data;
    let n = Infinity;
    try { n = JSON.stringify(m).length; } catch (e) { /* non serializzabile */ }
    if (!m || typeof m !== "object" || m.calliope !== 1 || typeof m.tipo !== "string"
        || !Object.prototype.hasOwnProperty.call(TIPI_DAL_RIQUADRO, m.tipo) || n > GIOCO_MAX) {
      if (++st.scartati > 20) chiudiGioco(f, "Il gioco mandava messaggi non validi: l'ho chiuso.", "messaggi non validi");
      return;
    }
    const adesso = Date.now();
    st.inviati = st.inviati.filter((t) => adesso - t < 1000);
    st.inviati.push(adesso);
    if (st.inviati.length > GIOCO_AL_SECONDO) {
      chiudiGioco(f, "Il gioco mandava troppi messaggi: l'ho chiuso.", "troppi messaggi");
      return;
    }
    if (m.tipo === "pong") { st.pong = adesso; return; }
    // «pronto» vale per la finestra che l'ha mandato (un riquadro spostato riparte da capo)
    if (m.tipo === "pronto") { st.pronto = ev.source; st.pong = adesso; }
    dalRiquadro(f, st, m);
  });

  async function dalRiquadro(f, st, m) {
    // Solo i campi noti per tipo: nient'altro arriva al server
    const dati = { tipo: m.tipo, id: Number.isInteger(m.id) ? m.id : null };
    TIPI_DAL_RIQUADRO[m.tipo].forEach((k) => { if (m[k] !== undefined) dati[k] = m[k]; });
    const r = await alServerGioco(f.dataset.partita, dati);
    if (st.chiuso) return;
    const d = r.dati || {};
    if (m.tipo === "pronto") {
      if (d.fine_tempo) { chiudiGioco(f, d.nota || "Per oggi il tempo dei giochi è finito."); return; }
      if (d.avvio) versoRiquadro(f, { tipo: "avvio", dati: d.avvio });
      return;
    }
    if (dati.id !== null && CON_RISPOSTA.includes(m.tipo)) {
      if (d.in_attesa) return;            // la risposta arriva dopo (evento «gioco»)
      const ok = r.status === 200 && d.ok !== false;
      versoRiquadro(f, { tipo: "risposta", rif: dati.id, ok,
                         valore: ok && d.valore !== undefined ? d.valore : null,
                         errore: ok ? null : (d.errore || "errore " + r.status) });
    }
  }

  // Dal server (evento SSE «gioco»): messaggi degli altri schermi, chat, giocatori, risposte
  // arrivate dopo, fine del tempo di gioco
  function daServerGioco(d) {
    if (!d || typeof d.partita !== "string") return;
    const fs = riquadri().filter((f) => f.dataset.partita === d.partita);
    const x = d.dati || {};
    if (d.tipo === "fine_tempo" || d.tipo === "chiudi") {
      const nota = x.nota || "Il gioco è chiuso.";
      GIOCHI_CHIUSI[d.partita] = nota;
      fs.forEach((f) => { versoRiquadro(f, { tipo: d.tipo, dati: x }); chiudiGioco(f, nota); });
      return;
    }
    if (d.tipo === "risposta") {
      fs.forEach((f) => versoRiquadro(f, { tipo: "risposta", rif: x.rif, ok: !!x.ok,
                                           valore: x.valore === undefined ? null : x.valore,
                                           errore: x.errore || null }));
      return;
    }
    if (!["messaggio", "chat", "giocatori", "pausa"].includes(d.tipo)) return;
    fs.forEach((f) => versoRiquadro(f, { tipo: d.tipo, dati: x }));
  }

  // Un riquadro che prova a navigare verso un altro sito: la regola frame-src di questa pagina
  // lo ferma prima della richiesta e lo segnala qui (il riquadro non lo dice a nessuno)
  document.addEventListener("securitypolicyviolation", (e) => {
    if (!/^(frame-src|child-src|default-src)/.test(e.effectiveDirective || e.violatedDirective || "")) return;
    riquadri().forEach((f) => chiudiGioco(f, "Il gioco ha provato a cambiare pagina: l'ho chiuso.", "navigazione"));
  });

  function visibile(f) {
    const r = f.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.right > 0 && r.bottom > 0
      && r.left < innerWidth && r.top < innerHeight;
  }

  // Il cane da guardia e il battito del tempo di gioco
  setInterval(() => {
    const adesso = Date.now();
    riquadri().forEach((f) => {
      const st = statoGioco(f);
      if (st.chiuso) return;
      const lim = (Number(f.dataset.watchdog) || 6) * 1000;
      if (st.pronto !== f.contentWindow) {
        if (adesso - st.nascita > Math.max(15000, lim * 2)) chiudiGioco(f, "Il gioco non è partito: l'ho chiuso.", "non parte");
        return;
      }
      if (adesso - st.pong > lim) {
        chiudiGioco(f, "Il gioco non rispondeva più: l'ho chiuso.", "non risponde");
        return;
      }
      if (adesso - st.ultimoPing >= 2000) {
        st.ultimoPing = adesso;
        versoRiquadro(f, { tipo: "ping", n: ++st.nPing });
      }
      if (adesso - st.battito >= BATTITO_MS) {
        const sec = (adesso - st.battito) / 1000;
        st.battito = adesso;
        if (document.visibilityState === "visible" && visibile(f)) {
          alServerGioco(f.dataset.partita, { tipo: "battito", secondi: Math.min(30, sec) }).then((r) => {
            const d = r.dati || {};
            if (d.fine_tempo) daServerGioco({ partita: f.dataset.partita, tipo: "fine_tempo", dati: { nota: d.nota } });
          });
        }
      }
    });
  }, 1000);

  setInterval(() => {
    aggiornaOrologio();
    aggiornaTimer();
    aggiornaLavori();
    disegnaVoce();
    if (S.vista === "scheda" && S.corrente && !valida(S.corrente)) {
      S.corrente = null;
      mostraInattiva();
    }
  }, 250);

  document.addEventListener("DOMContentLoaded", () => {
    mostraInattiva();
    avvio();
  });
})();
