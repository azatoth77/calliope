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
  // Sezioni (27/10, passo 1b): la pagina degli schermi su uno schermo personale (il PC che fa da
  // satellite) ha le sezioni come il telefono (pc.js e sezioni.js): stessi eventi del carosello.
  // Gli schermi di stanza restano come prima (decisione del 27/10 sera)
  const CON_SEZIONI = document.body.dataset.sezioni === "1";
  function emetti(nome, dati) {
    if (!CAROSELLO && !S.sezioni) return;
    try { document.dispatchEvent(new CustomEvent("calliope:" + nome, { detail: dati || {} })); }
    catch (e) { console.error(e); }
  }
  const NOMI_TIPO = {
    lista: "Lista", timer: "Timer", promemoria: "Agenda", biblioteca: "Biblioteca",
    documento: "Documento", casa: "Casa", calcolo: "Calcolo", testo: "Da leggere",
    lavoro: "Lavoro", modulo: "Da scrivere", web: "Internet", esecuzione: "Programma",
    risposta: "Risposta", foto: "Foto", allegato: "File", gioco: "Gioco", giochi: "Giochi",
    cruscotto: "Cruscotto", cassetto: "Cassetto", sviluppo: "Sviluppo", chat: "Conversazione",
    conoscente: "Voce nuova", avviso: "Avviso", archivio: "Archivio di casa", ufficio: "Ufficio",
  };
  // Il telefono a sezioni (27/10, docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md, 3.2):
  // la casa fissa di ogni tipo, «sezione» o «sezione/raccolta». La stessa tabella è in
  // calliope/schermi/schede.py, che la scrive nella scheda (`sezione`): vale quella del server,
  // questa serve per le schede che non la portano (prove/prova_sezioni.py le confronta)
  const SEZIONE_DI_TIPO = {
    risposta: "conversazione", calcolo: "conversazione", biblioteca: "conversazione",
    web: "conversazione", testo: "conversazione", chat: "conversazione",
    timer: "cose/agenda", promemoria: "cose/agenda", lista: "cose/liste",
    lavoro: "cose/lavori", esecuzione: "cose/lavori", sviluppo: "cose/lavori",
    documento: "cose/documenti", archivio: "cose/documenti", ufficio: "cose/ufficio",
    foto: "cose/cassetto", allegato: "cose/cassetto",
    cassetto: "cose/cassetto", modulo: "cose", gioco: "cose/giochi", giochi: "cose/giochi",
    casa: "casa", conoscente: "casa", avviso: "casa", cruscotto: "io",
  };
  const SEZIONI = ["adesso", "conversazione", "cose", "casa", "io"];
  function sezioneDi(c) {
    const s = String((c && (c.sezione || SEZIONE_DI_TIPO[c.tipo])) || "conversazione");
    return SEZIONI.includes(s.split("/")[0]) ? s : "conversazione";
  }
  // Quanto resta «appena cambiata» in Adesso una lista, un documento, la casa
  const RECENTE_S = 120;
  // Una scheda viva compare anche in Adesso (3.2): il timer corre, il lavoro non è finito, il
  // modulo è da compilare, il promemoria scade entro un'ora. `ora` in secondi (epoch);
  // `chiusa(partita)`: il gioco è chiuso su questa pagina (✕, finito: la scheda del server non
  // cambia)
  function viva(c, ora, chiusa) {
    if (!c) return false;
    const t = ora === undefined ? Date.now() / 1000 : ora;
    const recente = (Number(c.creata) || 0) > t - RECENTE_S;
    switch (c.tipo) {
      case "timer": return (c.timer || []).some((x) => (!x.stato || x.stato === "attivo") && x.fine > t);
      case "promemoria": return (c.voci || []).some((v) => v.ts > t && v.ts <= t + 3600);
      case "lavoro": return ["in_coda", "in_corso", "in_attesa"].includes(c.stato);
      case "esecuzione": return c.stato === "in_corso";
      case "sviluppo": return !!(c.sviluppo && c.sviluppo.stato === "aperta");
      case "modulo": return c.stato === "aperto";
      case "gioco": return c.stato !== "chiuso" && !(chiusa && chiusa(c.partita));
      case "conoscente": return !!c.aperta;
      case "avviso": return true;               // finché non è visto (lo tiene il telefono)
      case "lista": case "documento": case "casa": return recente;
      default: return false;
    }
  }
  // Il programma di un lavoro mentre gira (04/10, calliope/agenti/esecuzione.py)
  const STATI_ESECUZIONE = {
    in_corso: "in esecuzione", fatto: "finito", errore: "finito con un errore",
    scaduto: "fermato: tempo scaduto", fermato: "fermato",
  };
  const STATI_LAVORO = {
    in_coda: "in coda", in_corso: "in corso", in_attesa: "aspetta la tua risposta",
    fatto: "finito", errore: "non riuscito", mancano_dati: "mancano dati",
    annullato: "annullato", scaduto: "chiuso senza risposta",
    // Gli sviluppi degli altri nella pagina di chi amministra (28/10, #259)
    aperta: "aperto", sospesa: "sospeso", fermato: "fermato",
  };
  const fmtOraSec = new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const S = {
    token: null, sessione: null, es: null, scarto: 0, corrente: null,
    cronologia: [], vista: "avvio", abbinamento: null, giri: 0,
    voce: null, voceTotale: 0,
    // Si può scrivere adesso? (05/10) Il server lo dice all'accesso, nel benvenuto e con
    // l'evento «scrittura». Dal 28/10 (#301) `attiva` (casella, foto, file) dallo schermo
    // personale è sempre vera; `moduli` (l'invio di un modulo) solo durante una conversazione
    // cominciata a voce
    scrittura: { attiva: false, moduli: false, testo: "Di' «Calliope» per scrivermi.", testoModuli: "Di' «Calliope» per mandarmi il modulo." },
    // Il nome di questo schermo (e del satellite che lo porta, dal telefono): nella Conversazione
    // il posto di un turno detto o scritto da qui non si ripete (28/10, #301)
    nomiPropri: [],
    capace: false, personale: false, parola: "Calliope",
    // Le sezioni sullo schermo personale della pagina degli schermi (27/10, passo 1b)
    sezioni: false,
    // Il proprietario di questo schermo personale amministra (06/10: il cruscotto)
    amministra: false,
    // Quello che si sta scrivendo nei moduli, per id del modulo: resta se la scheda si
    // ridisegna o si riapre dalla cronologia
    bozze: {},
    // Ricollegamento (02/10): un solo ciclo alla volta, e l'ora dell'ultimo segno di vita
    // del flusso (anche i «ping» del server, ogni 15 s)
    ricollego: false, ultimoSegno: 0, tentativi: 0,
    // La vista dello sviluppo (08/10): la scheda `sviluppo:<id>` aperta su questo schermo
    // personale, e la chiave di quella lasciata con «Vista normale» (si torna con «Torna allo
    // sviluppo»). Sulla pagina degli schermi; il telefono la apre a schermo intero
    svil: null, svilLasciata: null,
    // Una scheda a schermo intero sulla pagina degli schermi (08/10): la sua chiave
    intera: null,
    // Quante schede tiene la cronologia della pagina (schermi_cronologia, dal benvenuto)
    max: 6,
    // La scheda «Conversazione» (08/10, solo schermi personali): i turni della persona
    // dall'archivio (benvenuto ed evento «chat»), per id; chatOk: il server la dà
    chat: [], chatOk: false, chatMax: 80, chatGiorni: 0,
    // I filtri e la ricerca della Conversazione (28/10, #242): senza filtri la vista è quella viva
    // (S.chat); con un filtro i turni vengono dal server (POST /api/conversazione) e un turno nuovo
    // entra solo se passa il filtro. `n` scarta le risposte vecchie
    chatVista: { giorno: "", schede: false, testo: "", turni: null, nota: "", attesa: false, n: 0, cercaAperta: false },
    // La scheda piccola aperta a schermo intero dalla conversazione, per chiave (sul PC), e la
    // vista a cui tornare quando si chiude
    schedeChat: {}, interaTorna: null,
    // «Pulisci»: il primo tocco arma il secondo per qualche secondo
    pulisciArmato: 0,
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
  // In compagnia con una voce sconosciuta (09/10, calliope/compagnia.py): la finestra d'ascolto
  // senza il nome è chiusa, serve il nome a ogni frase
  const TESTO_COMPAGNIA = "In compagnia: chiamami per nome";
  const $ = (id) => document.getElementById(id);

  // ─── piccoli aiuti ───
  function el(tag, cls, testo) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (testo !== undefined && testo !== null) e.textContent = String(testo);
    return e;
  }
  const ora = () => Date.now() + S.scarto;           // orologio del server

  // ─── il flusso dell'agente come una chat (08/10, calliope/agenti/avanzamento.py) ───
  // Il server manda solo i pezzi nuovi, numerati (n) e con la loro sezione (s); la cronologia
  // rimandata a una pagina che si ricollega ne ha l'ultima finestra (finestra: true). Qui si
  // accumulano per chiave del lavoro: un pezzo già visto non si aggiunge di nuovo, un buco
  // (un invio perso) fa chiedere la finestra con un ricollegamento (al più due volte di fila;
  // poi si va avanti segnando il taglio). Tetto: FLUSSO_PAGINA caratteri, come la finestra del
  // server; il resto è nel registro completo («Scarica il registro»). Solo testo: textContent
  const FLUSSO_PAGINA = 40000;
  const FLUSSI = {};
  const BUCHI = {};
  let chiestaFinestra = 0;
  function nuovoFlusso(id) { return { id: String(id || ""), fino: 0, sezioni: [], car: 0, taglio: false }; }
  function chiediFinestra() {
    if (Date.now() - chiestaFinestra < 4000) return;
    chiestaFinestra = Date.now();
    ricollega();
  }
  function assorbiFlusso(c) {
    const av = c && c.avanzamento;
    const f = av && av.flusso;
    if (!f || !Array.isArray(f.pezzi)) return;
    const k = chiaveDi(c);
    let st = FLUSSI[k];
    if (st && st.id !== String(f.id || "")) st = null;  // un altro lavoro con lo stesso id
    const pezzi = f.pezzi.filter((p) => p && Number.isInteger(p.n) && typeof p.x === "string")
      .sort((a, b) => a.n - b.n);
    const fino = st ? st.fino : 0;
    const primo = pezzi.length ? pezzi[0].n : (Number(f.fino) || 0) + 1;
    if (primo > fino + 1) {
      if (f.finestra) {
        st = nuovoFlusso(f.id);
        st.taglio = !!f.taglio || primo > 1;
      } else if ((BUCHI[k] || 0) < 2) {
        BUCHI[k] = (BUCHI[k] || 0) + 1;
        chiediFinestra();
        return;
      } else {
        if (!st) st = nuovoFlusso(f.id);
        st.taglio = true;
      }
    }
    if (!st) st = nuovoFlusso(f.id);
    for (const p of pezzi) {
      if (p.n <= st.fino) continue;                     // già qui: niente doppioni
      const u = st.sezioni[st.sezioni.length - 1];
      if (u && u.s === p.s && u.t === p.t) u.x += p.x;
      else st.sezioni.push({ s: p.s, t: String(p.t || "testo"), f: typeof p.f === "string" ? p.f : "", x: p.x });
      st.car += p.x.length;
      st.fino = p.n;
    }
    while (st.car > FLUSSO_PAGINA && st.sezioni.length > 1) { st.car -= st.sezioni.shift().x.length; st.taglio = true; }
    if (st.car > FLUSSO_PAGINA && st.sezioni.length) {
      const u = st.sezioni[0];
      u.x = u.x.slice(u.x.length - FLUSSO_PAGINA);
      st.car = u.x.length;
      st.taglio = true;
    }
    BUCHI[k] = 0;
    delete FLUSSI[k];
    FLUSSI[k] = st;                                     // in fondo: i più vecchi escono per primi
    const chiavi = Object.keys(FLUSSI);
    if (chiavi.length > 8) delete FLUSSI[chiavi[0]];
  }
  const fmtOra = new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit" });
  const fmtData = new Intl.DateTimeFormat("it-IT", { weekday: "long", day: "numeric", month: "long" });
  const fmtGiornoBreve = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "long" });

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
    // I nomi di questo schermo: il telefono aggiunge quello del suo satellite (28/10, #301)
    nomiPropri(lista) { nomiPropri(lista); },
    // La modalità scrittura del telefono (28/10): le risposte a ciò che si manda sono solo scritte
    soloScritto(v) { S.soloScritto = !!v; },
    // Il pulsante «Foto» del telefono (05/10): apre la scelta della foto nello stesso tocco
    foto() { const x = $("scrivi-foto-file"); if (x && S.fotoAmmessa && S.scrittura.attiva) { x.click(); return true; } return false; },
    dimentica() { chiudiEventi(); salvaToken(null); S.sessione = null; },
    // Per il carosello del telefono: le schede costruite e allineate come qui
    costruisci(c, opz) { return costruisci(c, opz); },
    allinea(a, b) { allinea(a, b); },
    // Le aree che seguono la coda (flusso dell'agente, uscita di un programma): prima e dopo
    // un allineamento, per restare in fondo solo se chi guarda era in fondo (08/10)
    misuraSegui(r) { return misuraSegui(r); },
    ripristinaSegui(r, m) { ripristinaSegui(r, m); },
    chiaveDi(c) { return chiaveDi(c); },
    cronologia() { return S.cronologia.slice(); },
    corrente() { return S.corrente; },
    aggiorna() { aggiornaTimer(); aggiornaLavori(); },
    // Il cruscotto di chi amministra (06/10): sul telefono si apre da Io (27/10)
    cruscotto() { return apriCruscotto(); },
    amministra() { return S.amministra; },
    // La scheda «Conversazione» e «Pulisci le mie schede» (08/10): sul telefono in
    // Conversazione e in Io (27/10)
    chat() { return apriChat(); },
    haChat() { return S.chatOk; },
    pulisci() { return pulisciSchede(); },
    // La modalità gioco (11/10): il telefono passa lo stato della sua voce per il pallino;
    // `gioco()` dice quale partita è a tutto schermo (per le prove e per il carosello)
    voceGioco(stato) { voceGioco(stato); },
    gioco() { return { partita: GIOCO.attivo, schermoIntero: !!document.fullscreenElement, voce: GIOCO.voce }; },
    chiudiGioco() { if (GIOCO.attivo) chiudiGiocoDaTe(GIOCO.attivo); },
    NOMI_TIPO, SEZIONE_DI_TIPO, SEZIONI, sezioneDi,
    viva(c, ora) { return viva(c, ora, (p) => !!(GIOCHI_CHIUSI[p] || CHIUSI_DA_TE[p])); },
    // Un gioco da chiudere senza mostrarlo (il telefono in auto, 27/10): il riquadro si toglie e
    // il server smette di ascoltare i suoi comandi a voce
    chiudiPartita(p) { if (p) chiudiGiocoDaTe(String(p)); },
    // L'accento (27/10): quello in uso e la scelta da Io › Aspetto del telefono
    aspetto() { return S.aspetto || null; },
    // La conversazione per la colonna del PC personale, fuori dalla cronologia (27/10)
    schedaChat() { return S.chatOk ? schedaChat() : null; },
    // «Parla» sul PC personale (27/10, passo 1b): il satellite legato a questo schermo ascolta
    // senza il nome
    async parla() {
      let r;
      try { r = await postSessione("/api/parla", {}); }
      catch (e) { return { ok: false, errore: "Calliope non risponde: riprova tra poco." }; }
      return { ok: r.status === 200, secondi: r.dati.secondi || 0, errore: r.dati.errore || MESSAGGI[r.status] || "" };
    },
    sezioni() { return !!S.sezioni; },
    scegliAccento(nome) { return scegliAccento(nome); },
    // La spunta della lista (28/10): l'attesa massima dell'esito (le prove la accorciano)
    get spunta() { return SPUNTA; },
    // Le tessere e le pagine di «Le mie cose» (28/10, passo 2a): {} → {tessere}, {raccolta} →
    // {schede, nota}
    async raccolte(dati) {
      if (!S.sessione) return { ok: false, status: 0, dati: {} };
      try {
        const r = await postSessione("/api/raccolte", dati || {});
        return { ok: r.status === 200, status: r.status, dati: r.dati || {}, riprova: r.riprova };
      } catch (e) { return { ok: false, status: 0, dati: {} }; }
    },
    // La ricerca di una pagina (28/10, passo 2d: i Documenti): {raccolta, testo} → {schede, nota}
    async cerca(dati) {
      if (!S.sessione) return { ok: false, status: 0, dati: {} };
      try {
        const r = await postSessione("/api/raccolte/cerca", dati || {});
        return { ok: r.status === 200, status: r.status, dati: r.dati || {}, riprova: r.riprova };
      } catch (e) { return { ok: false, status: 0, dati: {} }; }
    },
    // Lo Studio (29/10, passo 4.2, #281, studio.js): senza blob le verifiche a cui mandare pagine;
    // con il blob l'invio di una pagina (foto o PDF nei byte nudi, i dati in «X-Calliope-Studio»)
    async studio(blob, meta) {
      if (!S.sessione) return { ok: false, status: 0, dati: {} };
      try {
        let r;
        if (!blob) r = await postSessione("/api/studio/verifiche", {});
        else {
          const f = await fetch("/api/studio/pagina", {
            method: "POST", cache: "no-store", body: blob,
            headers: { "Content-Type": "application/octet-stream", "X-Calliope-Sessione": S.sessione || "",
              "X-Calliope-Studio": encodeURIComponent(JSON.stringify(meta || {})) },
          });
          let d = {};
          try { d = await f.json(); } catch (e) { /* vuota */ }
          r = { status: f.status, dati: d };
        }
        return { ok: r.status === 200, status: r.status, dati: r.dati || {} };
      } catch (e) { return { ok: false, status: 0, dati: {} }; }
    },
    // Gli argomenti di una verifica e la conferma (30/10, passo 4.4, #283, studio.js):
    // {verifica, azione?, argomento?, titolo?} → {argomenti, verifica, estrazione, lettura, prova}
    // La home dello Studio (30/10, passo 4.5, #284, studio.js): {} → verifiche, piano, lettura…
    async studioHome() {
      if (!S.sessione) return { ok: false, status: 0, dati: {} };
      try {
        const r = await postSessione("/api/studio/home", {});
        return { ok: r.status === 200, status: r.status, dati: r.dati || {} };
      } catch (e) { return { ok: false, status: 0, dati: {} }; }
    },
    // Un tocco dello Studio (POST /api/tocco): l'esito arriva dal ciclo con l'evento «tocco»
    async studioTocco(dati) {
      if (!S.sessione) return { ok: false, status: 0, dati: {} };
      try {
        const r = await postSessione("/api/tocco", dati || {});
        return { ok: r.status === 200, status: r.status, dati: r.dati || {} };
      } catch (e) { return { ok: false, status: 0, dati: {} }; }
    },
    // La vista dello Studio aperta (POST /api/vista): per la riga dei dati del turno
    async vista(dati) {
      if (!S.sessione) return;
      try { await postSessione("/api/vista", dati || { vista: null }); } catch (e) { /* niente */ }
    },
    async studioArgomenti(dati) {
      if (!S.sessione) return { ok: false, status: 0, dati: {} };
      try {
        const r = await postSessione("/api/studio/argomenti", dati || {});
        return { ok: r.status === 200, status: r.status, dati: r.dati || {} };
      } catch (e) { return { ok: false, status: 0, dati: {} }; }
    },
    // Le carte di una verifica e il loro ripasso (30/10, passo 6, #246, studio.js):
    // {verifica, azione?, carta?, domanda?, risposta?, argomento?, esito?} → {carte, da_ripassare…}
    async studioCarte(dati) {
      if (!S.sessione) return { ok: false, status: 0, dati: {} };
      try {
        const r = await postSessione("/api/studio/carte", dati || {});
        return { ok: r.status === 200, status: r.status, dati: r.dati || {} };
      } catch (e) { return { ok: false, status: 0, dati: {} }; }
    },
    // Le mappe concettuali di una verifica (30/10, passo 7, #247, studio.js): {verifica, azione?,
    // mappa?, …} → {scheletro, mia, memoria, argomenti…}; con azione «pdf» il PDF in un blob
    async studioMappa(dati) {
      if (!S.sessione) return { ok: false, status: 0, dati: {} };
      try {
        if (dati && dati.azione === "pdf") {
          const f = await fetch("/api/studio/mappa", {
            method: "POST", cache: "no-store", body: JSON.stringify(dati),
            headers: { "Content-Type": "application/json", "X-Calliope-Sessione": S.sessione || "" },
          });
          if (f.status !== 200) {
            let d = {};
            try { d = await f.json(); } catch (e) { /* vuota */ }
            return { ok: false, status: f.status, dati: d };
          }
          return { ok: true, status: 200, dati: {}, blob: await f.blob() };
        }
        const r = await postSessione("/api/studio/mappa", dati || {});
        return { ok: r.status === 200, status: r.status, dati: r.dati || {} };
      } catch (e) { return { ok: false, status: 0, dati: {} }; }
    },
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
    // Le sezioni solo sullo schermo personale, e solo sulla pagina che le ha (non sul telefono:
    // lì è il carosello di telefono.js)
    S.sezioni = CON_SEZIONI && !INCORPORATA && !!r.dati.personale && r.dati.sezioni !== false;
    document.body.classList.toggle("con-sezioni", S.sezioni);
    emetti("pc", { attiva: S.sezioni, parla: !!r.dati.parla, luogo: r.dati.stanza || "", nome: r.dati.nome || "" });
    if (r.dati.scrittura) leggiScrittura(r.dati.scrittura);
    if (r.dati.nome) nomiPropri([r.dati.nome]);
    casellaScrivi(!!r.dati.scrivi, !!r.dati.personale);
    impostaAmministra(!!r.dati.amministra);
    applicaAspetto(r.dati.aspetto);
    emetti("nascoste", r.dati.nascoste || {});
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
      if (Number.isInteger(d.cronologia_max) && d.cronologia_max > 0) S.max = d.cronologia_max;
      impostaChat(d.chat || null);
      stato("ok", "collegato");
      // Le schede della cronologia del server, nell'ordine del server: una scheda già qui
      // con la stessa identità (o lo stesso id) si sostituisce, mai un doppione
      (d.cronologia || []).forEach((c) => { assorbiFlusso(c); aggiungiCronologia(c, true); });
      mostraVoce(d.voce || null);       // null: questa pagina non mostra lo stato
      mostraStanza(d.stanza || null);
      if (d.scrittura) applicaScrittura(d.scrittura);
      mostraContesto(d.contesto || null);
      // Uno sviluppo aperto nella cronologia (08/10): lo schermo torna nella sua vista
      const svil = (d.cronologia || []).filter((c) => c.tipo === "sviluppo").pop();
      if (!CAROSELLO && svil) {
        if (svilAperto(svil)) {
          if (!S.svil || chiaveDi(S.svil) !== chiaveDi(svil)) S.svilLasciata = null;
          S.svil = svil;
        } else if (S.svil && chiaveDi(S.svil) === chiaveDi(svil)) S.svil = null;
      }
      const ultima = d.cronologia && d.cronologia[d.cronologia.length - 1];
      if (vistaAttiva()) disegnaVista();
      else if (ultima && valida(ultima)) mostra(ultima);
      else if (!S.corrente) mostraInattiva();
      segnaTorna();
      if (S.intera) disegnaInteroPC();
    });
    es.addEventListener("scheda", (ev) => {
      vivo();
      const c = JSON.parse(ev.data);
      assorbiFlusso(c);
      if (!CAROSELLO && vistaSviluppo(c)) { if (S.intera) disegnaInteroPC(); return; }
      if (S.intera && chiaveDi(c) === S.intera) setTimeout(disegnaInteroPC, 0);
      if (c.tipo === "vuota") {
        // «Calliope, chiudi il gioco» (11/10): la scheda vuota di schermo_mostra chiude anche
        // la modalità gioco, sul telefono come qui
        if (GIOCO.attivo) chiudiGiocoDaTe(GIOCO.attivo);
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
      // Un gioco appena arrivato (11/10) si apre nella modalità gioco: GIOCO.attivo prima di
      // mostra, così la scheda nasce già a tutto schermo
      const gioca = c.tipo === "gioco" && c.stato !== "chiuso" && !GIOCHI_CHIUSI[c.partita]
        && !CHIUSI_DA_TE[c.partita];
      if (gioca) GIOCO.attivo = c.partita;
      mostra(c);
      if (gioca) entraModoGioco(c.partita, false);
    });
    es.addEventListener("voce", (ev) => { vivo(); mostraVoce(JSON.parse(ev.data)); });
    es.addEventListener("stanza", (ev) => { vivo(); mostraStanza(JSON.parse(ev.data)); });
    es.addEventListener("scrittura", (ev) => { vivo(); applicaScrittura(JSON.parse(ev.data)); });
    es.addEventListener("aspetto", (ev) => { vivo(); applicaAspetto(JSON.parse(ev.data)); });
    es.addEventListener("tocco", (ev) => { vivo(); esitoTocco(JSON.parse(ev.data)); });
    // Calliope apre una pagina di Le mie cose (28/10, #289: schermo_mostra con cosa=pagina)
    es.addEventListener("pagina", (ev) => { vivo(); let d = {}; try { d = JSON.parse(ev.data); } catch (e) { return; } emetti("pagina", d); });
    es.addEventListener("contesto", (ev) => { vivo(); mostraContesto(JSON.parse(ev.data)); });
    es.addEventListener("gioco", (ev) => { vivo(); daServerGioco(JSON.parse(ev.data)); });
    es.addEventListener("chat", (ev) => { vivo(); chatDalServer(JSON.parse(ev.data)); });
    es.addEventListener("pulisci", () => { vivo(); pulisciLocale(); });
    // Via tutto ciò che la pagina mostra dello schermo di prima (revocato, o di un'altra persona)
    function svuotaSchermo() {
      mostraVoce(null);
      mostraContesto(null);
      chiudiEventi();
      casellaScrivi(false);
      S.cronologia = [];
      S.corrente = null;
      impostaChat(null);
      emetti("schede", {});
      disegnaCronologia();
    }
    es.addEventListener("revocato", () => {
      svuotaSchermo();
      salvaToken(null);
      if (INCORPORATA) { S.sessione = null; stato("attesa", "schede in attesa"); return; }
      abbina();
    });
    // Lo stesso schermo è diventato di un'altra persona (31/10, #338): niente di ciò che mostrava
    // resta, il token vale ancora e un accesso nuovo porta lo schermo di adesso
    es.addEventListener("proprietario", () => {
      if (es !== S.es) return;
      svuotaSchermo();
      mostraInattiva();
      ricollega();
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
      while (S.cronologia.length > Math.max(S.max, 2)) S.cronologia.shift();
    }
    // `ripresa`: la cronologia rimandata dal server al (ri)collegamento, già vista (il telefono
    // non la conta come novità, 27/10)
    emetti("schede", { scheda: c, spostata: !(i >= 0 && c.sposta === false && !ordine), ripresa: !!ordine });
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
    // «Pulisci» (08/10): solo sugli schermi personali, le schede del proprietario
    if (S.personale && !CAROSELLO && S.cronologia.some((c) => !SOLO_PAGINA.has(c.tipo))) {
      const p = el("button", "pulisci-schede", Date.now() < S.pulisciArmato ? "Tocca di nuovo per pulire" : "Pulisci");
      p.type = "button";
      p.dataset.pulisci = "1";
      p.title = "Toglie le tue schede da questo schermo e dagli altri tuoi schermi";
      f.append(p);
    }
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
      if (a.getAttribute(at.name) === at.value) continue;
      // Lo stile (le barre dei tetti) per il CSSOM: setAttribute("style") viola la CSP
      // (style-src 'self'), cssText no (08/10, la barra del tempo in diretta)
      if (at.name === "style") a.style.cssText = b.style.cssText;
      else a.setAttribute(at.name, at.value);
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

  // `opz.intera` (08/10): la scheda a schermo intero (sulla pagina degli schermi nel suo
  // strato, sul telefono nel suo): per un lavoro due colonne, a destra il flusso dell'agente;
  // per uno sviluppo la vista dello sviluppo. Nella scheda normale il flusso non c'è
  const TIPI_INTERA_PC = new Set(["lavoro", "documento", "esecuzione", "chat"]);
  function costruisci(c, opz) {
    opz = opz || {};
    const s = el("article", "scheda tipo-" + c.tipo + (opz.intera ? " intera" : ""));
    s.dataset.chiave = chiaveDi(c);
    const et = el("div", "etichetta", NOMI_TIPO[c.tipo] || c.tipo);
    if (c.visibilita === "personale") et.append(el("span", "badge personale", "personale"));
    if (c.fonte) et.append(el("span", "badge", c.fonte));
    // Una copia dalla conversazione (28/10, #242): com'era allora, non lo stato di adesso
    if (c.storica && c.creata) {
      // Con il giorno quando non è di oggi (revisione della PR #271: una copia di settimane fa
      // sembrava di oggi)
      const d = new Date(c.creata * 1000), oggi = new Date(ora());
      const giorno = d.toDateString() === oggi.toDateString() ? "" : fmtGiornoBreve.format(d) + " ";
      et.append(el("span", "badge storica", "com'era " + giorno + "alle " + fmtOra.format(d)));
    }
    if (c.formato && c.tipo !== "sviluppo") et.append(el("span", "badge", c.formato.toUpperCase()));
    if (!CAROSELLO && !opz.intera && TIPI_INTERA_PC.has(c.tipo)) {
      const b = el("button", "piccolo-bottone tasto-intero", "Schermo intero");
      b.type = "button";
      b.dataset.intero = chiaveDi(c);
      b.setAttribute("aria-label", "Apri a schermo intero: " + (c.titolo || NOMI_TIPO[c.tipo] || "scheda"));
      et.append(b);
    }
    s.append(et);
    if (c.tipo !== "calcolo") s.append(el("h1", "titolo", c.titolo));
    const corpo = el("div", "corpo");
    (DISEGNA[c.tipo] || DISEGNA.testo)(c, corpo, s, opz);
    s.append(corpo);
    return s;
  }

  // Le aree che seguono la coda del testo ([data-segui]: il flusso dell'agente, l'uscita di un
  // programma): prima di allineare si guarda chi era in fondo, dopo lo si riporta in fondo; chi
  // è tornato indietro a leggere resta dov'è (e il flusso mostra «In fondo»)
  function misuraSegui(r) { return r ? [...r.querySelectorAll("[data-segui]")].map(inFondo) : []; }
  function ripristinaSegui(r, m) {
    if (!r) return;
    r.querySelectorAll("[data-segui]").forEach((p, i) => {
      const segue = !m || m[i] !== false;
      if (segue) p.scrollTop = p.scrollHeight;
      p.classList.toggle("staccato", !segue);
    });
  }

  // `segnale`: la stessa scheda cambiata per un evento (sposta: true, un cambio di stato):
  // un segno leggero sul bordo, non l'animazione di entrata
  function mostra(c, segnale = true) {
    if (!CAROSELLO && c.tipo === "sviluppo" && svilAperto(c)) {
      // La scheda dello sviluppo aperto (dalla cronologia o da Calliope): la sua vista
      S.svil = c;
      S.svilLasciata = null;
      disegnaVista();
      return;
    }
    if (!CAROSELLO && S.svil && S.svilLasciata !== chiaveDi(S.svil)) S.svilLasciata = chiaveDi(S.svil);
    const prima = S.corrente;
    S.corrente = c;
    S.vista = "scheda";
    if (CAROSELLO) { emetti("mostra", { scheda: c, segnale }); return; }
    // Con le sezioni la scheda va nella sua sezione; il centro torna alle sezioni (lascia la
    // vista dello sviluppo, che sta in #principale sopra di loro)
    if (S.sezioni) {
      $("principale").replaceChildren();
      document.body.classList.remove("in-vista-sviluppo");
      emetti("mostra", { scheda: c, segnale });
      aggiornaTimer();
      aggiornaLavori();
      segnaTorna();
      return;
    }
    const m = $("principale");
    const vecchia = m.querySelector(":scope > article.scheda");
    const nuova = costruisci(c);
    if (vecchia && prima && chiaveDi(prima) === chiaveDi(c) && vecchia.dataset.chiave === chiaveDi(c)
        && c.tipo !== "modulo" && prima.tipo === c.tipo) {
      const seguite = misuraSegui(vecchia);
      // Il segno di prima resta com'è (togliere e rimettere la classe lo farebbe ripartire)
      if (vecchia.classList.contains("cambiata")) nuova.classList.add("cambiata");
      allinea(vecchia, nuova);
      ripristinaSegui(vecchia, seguite);
      if (segnale) {
        vecchia.classList.remove("cambiata");
        void vecchia.offsetWidth;          // il segno riparte anche se c'era già
        vecchia.classList.add("cambiata");
      }
    } else {
      m.replaceChildren(nuova);
      ripristinaSegui(nuova, null);
    }
    document.body.classList.remove("in-vista-sviluppo");
    disegnaCronologia();
    aggiornaTimer();
    aggiornaLavori();
    segnaTorna();
  }

  // ─── lettore Markdown (07/10, calliope/documenti/markdown.py) ───
  // I testi dell'agente (ricerche, relazioni) arrivano in Markdown: un sottoinsieme letto qui,
  // costruito con createElement e textContent, MAI come HTML (il testo dell'agente non è
  // fidato). Titoli, paragrafi, elenchi (anche annidati), tabelle, codice, citazioni, righe; nelle
  // righe grassetto, corsivo, barrato, codice. I collegamenti restano testo non cliccabile
  // (con l'indirizzo tra parentesi), le immagini un segnaposto: niente rete, niente navigazione.
  // Un HTML scritto nel testo resta testo. Limiti contro i testi ostili: lunghezza, blocchi,
  // righe e colonne delle tabelle, rientri, citazioni annidate, enfasi annidate e corte.
  const MD = { caratteri: 120000, blocchi: 1500, righe: 200, colonne: 20, livelli: 6, citazioni: 4, inLinea: 3, enfasi: 400 };
  const MD_TITOLO = /^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$/;
  const MD_RIGA = /^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$/;
  const MD_RECINTO = /^ {0,3}(`{3,}|~{3,})(.*)$/;
  const MD_VOCE = /^([ \t]*)([-*+]|\d{1,9}[.)])[ \t]+(.*)$/;
  const MD_SEP = /^[ \t]*\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$/;
  const MD_CIT = /^ {0,3}>[ ]?(.*)$/;
  const MD_SOTTO1 = /^ {0,3}=+[ \t]*$/;
  const MD_SOTTO2 = /^ {0,3}-+[ \t]*$/;

  function mdCelle(riga) {
    let r = riga.trim();
    if (r.startsWith("|")) r = r.slice(1);
    if (r.endsWith("|") && !r.endsWith("\\|")) r = r.slice(0, -1);
    const out = [];
    let cur = "";
    for (let i = 0; i < r.length; i++) {
      if (r[i] === "\\" && r[i + 1] === "|") { cur += "|"; i++; continue; }
      if (r[i] === "|") { out.push(cur.trim()); cur = ""; } else cur += r[i];
    }
    out.push(cur.trim());
    return out;
  }

  function mdApre(r, dopo) {
    return MD_TITOLO.test(r) || MD_RIGA.test(r) || MD_RECINTO.test(r) || MD_VOCE.test(r) || MD_CIT.test(r)
      || (r.includes("|") && dopo != null && MD_SEP.test(dopo) && dopo.includes("-"));
  }

  // I blocchi, come markdown.analizza in Python
  function mdBlocchi(testo, livello) {
    const righe = String(testo).split("\n");
    const out = [];
    let i = 0;
    const n = righe.length;
    while (i < n && out.length < MD.blocchi) {
      const r = righe[i];
      if (!r.trim()) { i++; continue; }
      let m = r.match(MD_RECINTO);
      if (m) {
        const f = m[1];
        const chiude = new RegExp("^ {0,3}" + (f[0] === "`" ? "`" : "~") + "{" + f.length + ",}[ \\t]*$");
        const corpo = [];
        i++;
        while (i < n && !chiude.test(righe[i])) corpo.push(righe[i++]);
        i++;
        out.push({ tipo: "codice", testo: corpo.join("\n") });
        continue;
      }
      m = r.match(MD_TITOLO);
      if (m) { out.push({ tipo: "titolo", livello: m[1].length, testo: (m[2] || "").trim() }); i++; continue; }
      if (MD_RIGA.test(r)) { out.push({ tipo: "riga" }); i++; continue; }
      const dopo = i + 1 < n ? righe[i + 1] : null;
      if (r.includes("|") && dopo != null && MD_SEP.test(dopo) && dopo.includes("-")) {
        const colonne = mdCelle(r).slice(0, MD.colonne);
        const corpo = [];
        let altre = 0;
        i += 2;
        while (i < n && righe[i].trim() && righe[i].includes("|")) {
          if (corpo.length < MD.righe) {
            const c = mdCelle(righe[i]).slice(0, colonne.length);
            while (c.length < colonne.length) c.push("");
            corpo.push(c);
          } else altre++;
          i++;
        }
        out.push({ tipo: "tabella", colonne, righe: corpo, altre });
        continue;
      }
      if (MD_CIT.test(r)) {
        const dentro = [];
        while (i < n && righe[i].trim()) {
          const q = righe[i].match(MD_CIT);
          if (!q && !dentro.length) break;
          dentro.push(q ? q[1] : righe[i]);
          i++;
        }
        if (livello + 1 >= MD.citazioni) {
          out.push({ tipo: "citazione", blocchi: [{ tipo: "paragrafo", testo: dentro.map((x) => x.replace(/^(?:\s*>)+\s?/, "")).join(" ") }] });
        } else out.push({ tipo: "citazione", blocchi: mdBlocchi(dentro.join("\n"), livello + 1) });
        continue;
      }
      if (MD_VOCE.test(r)) {
        const voci = [];
        let base = null;
        while (i < n) {
          const riga = righe[i];
          const v = riga.match(MD_VOCE);
          if (v) {
            if (base === null) base = v[1].length;
            const liv = Math.max(0, Math.min(MD.livelli - 1, Math.floor((v[1].length - base) / 2)));
            const num = /\d/.test(v[2][0]);
            if (liv === 0 && voci.length && voci[0].numerato !== num) break;
            voci.push({ testo: v[3].trim(), livello: liv, numerato: num });
            i++;
            continue;
          }
          if (riga.trim() && voci.length && /^[ \t]/.test(riga) && !mdApre(riga.trim(), null)) {
            voci[voci.length - 1].testo += " " + riga.trim();
            i++;
            continue;
          }
          if (!riga.trim() && i + 1 < n && MD_VOCE.test(righe[i + 1])) { i++; continue; }
          break;
        }
        out.push({ tipo: "elenco", voci });
        continue;
      }
      const par = [r.trim()];
      i++;
      while (i < n && righe[i].trim()) {
        if (MD_SOTTO1.test(righe[i]) || (MD_SOTTO2.test(righe[i]) && par.length === 1)) break;
        if (mdApre(righe[i], i + 1 < n ? righe[i + 1] : null)) break;
        par.push(righe[i].trim());
        i++;
      }
      if (i < n && righe[i].trim() && (MD_SOTTO1.test(righe[i]) || MD_SOTTO2.test(righe[i]))) {
        out.push({ tipo: "titolo", livello: MD_SOTTO1.test(righe[i]) ? 1 : 2, testo: par.join(" ") });
        i++;
        continue;
      }
      out.push({ tipo: "paragrafo", testo: par.join("\n") });
    }
    return out;
  }

  // Dentro una riga: nodi di testo e pochi elementi (strong, em, s, code, span). `prof`: quante
  // enfasi annidate (oltre, il resto è testo)
  const MD_FUGA = "\\`*_{}[]()#+-.!|~>";
  const mdParola = (c) => !!c && /[\p{L}\p{N}_]/u.test(c);
  function mdInLinea(dest, s, prof) {
    let buf = "";
    const fuori = () => { if (buf) { dest.append(document.createTextNode(buf)); buf = ""; } };
    let i = 0;
    while (i < s.length) {
      const c = s[i];
      if (c === "\\" && i + 1 < s.length && MD_FUGA.includes(s[i + 1])) { buf += s[i + 1]; i += 2; continue; }
      if (c === "\n") {
        // due spazi in fondo: a capo; altrimenti uno spazio
        if (buf.endsWith("  ")) { buf = buf.replace(/ +$/, ""); fuori(); dest.append(el("br")); } else buf += " ";
        i++;
        continue;
      }
      if (c === "`") {
        let k = i;
        while (s[k] === "`") k++;
        const apri = s.slice(i, k);
        const j = s.indexOf(apri, k);
        if (j > 0 && j - k <= 2000 && s[j + apri.length] !== "`") {
          fuori();
          dest.append(el("code", "", s.slice(k, j).trim()));
          i = j + apri.length;
          continue;
        }
        buf += apri; i = k; continue;
      }
      if ((c === "!" && s[i + 1] === "[") || c === "[") {
        const img = c === "!";
        const a = img ? i + 2 : i + 1;
        const fine = s.indexOf("]", a);
        if (fine > 0 && fine - a <= 500 && s[fine + 1] === "(" && !s.slice(a, fine).includes("\n")) {
          const chiusa = s.indexOf(")", fine + 2);
          if (chiusa > 0 && chiusa - fine <= 700) {
            const testo = s.slice(a, fine);
            const indirizzo = s.slice(fine + 2, chiusa).trim().split(/\s+/)[0] || "";
            fuori();
            if (img) {
              dest.append(el("span", "md-immagine", testo ? "[immagine: " + testo + "]" : "[immagine]"));
            } else {
              // Un collegamento resta testo: niente <a>, niente navigazione
              const l = el("span", "md-link");
              if (prof < MD.inLinea) mdInLinea(l, testo, prof + 1); else l.textContent = testo;
              dest.append(l);
              if (indirizzo && indirizzo !== testo) dest.append(el("span", "md-indirizzo", " (" + indirizzo + ")"));
            }
            i = chiusa + 1;
            continue;
          }
        }
        buf += img ? "![" : "["; i = a; continue;
      }
      const due = s.slice(i, i + 2);
      if ((due === "**" || due === "__" || due === "~~") && prof < MD.inLinea) {
        const okInizio = due !== "__" || !mdParola(s[i - 1]);
        const j = s.indexOf(due, i + 2);
        if (okInizio && j > i + 2 && j - i <= MD.enfasi && !/\s/.test(s[i + 2]) && !/\s/.test(s[j - 1])
            && !s.slice(i + 2, j).includes("\n") && (due !== "__" || !mdParola(s[j + 2]))) {
          fuori();
          const e = el(due === "~~" ? "s" : "strong");
          mdInLinea(e, s.slice(i + 2, j), prof + 1);
          dest.append(e);
          i = j + 2;
          continue;
        }
        buf += due; i += 2; continue;
      }
      if ((c === "*" || c === "_") && prof < MD.inLinea && s[i + 1] && !/\s/.test(s[i + 1]) && s[i + 1] !== c
          && !mdParola(s[i - 1])) {
        let j = s.indexOf(c, i + 1);
        while (j > 0 && j - i <= MD.enfasi && (s[j + 1] === c || /\s/.test(s[j - 1]) || s[j - 1] === "\\")) j = s.indexOf(c, j + 2);
        if (j > i + 1 && j - i <= MD.enfasi && !mdParola(s[j + 1]) && !s.slice(i + 1, j).includes("\n")) {
          fuori();
          const e = el("em");
          mdInLinea(e, s.slice(i + 1, j), prof + 1);
          dest.append(e);
          i = j + 1;
          continue;
        }
      }
      buf += c;
      i++;
    }
    fuori();
  }

  function mdTabella(b) {
    const box = el("div", "tabella-md");
    const t = el("table");
    const num = b.colonne.map((_, i) => b.righe.length > 0 && b.righe.every((r) => !r[i] || NUMERO.test(r[i])));
    const tr = el("tr");
    b.colonne.forEach((c, i) => { const th = el("th", num[i] ? "num" : ""); mdInLinea(th, c, 0); tr.append(th); });
    const th = el("thead"); th.append(tr); t.append(th);
    const tb = el("tbody");
    b.righe.forEach((r) => {
      const x = el("tr");
      b.colonne.forEach((_, i) => { const td = el("td", num[i] ? "num" : ""); mdInLinea(td, r[i] || "", 0); x.append(td); });
      tb.append(x);
    });
    t.append(tb);
    box.append(t);
    return box;
  }

  function mdElenco(voci) {
    // I livelli diventano elenchi annidati: una pila di <ul>/<ol>
    const radice = el(voci[0].numerato ? "ol" : "ul");
    const pila = [radice];
    let ultimo = null;
    voci.forEach((v) => {
      while (pila.length - 1 > v.livello) pila.pop();
      while (pila.length - 1 < v.livello && ultimo) {
        const sotto = el(v.numerato ? "ol" : "ul");
        ultimo.append(sotto);
        pila.push(sotto);
      }
      const li = el("li");
      mdInLinea(li, v.testo, 0);
      pila[pila.length - 1].append(li);
      ultimo = li;
    });
    return radice;
  }

  function mdDisegna(dest, blocchi, titoli) {
    blocchi.forEach((b) => {
      if (b.tipo === "titolo") {
        const h = el("h" + Math.min(6, b.livello + 1), "md-titolo");
        mdInLinea(h, b.testo, 0);
        h.dataset.mdAncora = String(titoli.length);
        titoli.push({ livello: b.livello, testo: h.textContent });
        dest.append(h);
      } else if (b.tipo === "paragrafo") {
        const p = el("p");
        mdInLinea(p, b.testo, 0);
        dest.append(p);
      } else if (b.tipo === "elenco") {
        if (b.voci.length) dest.append(mdElenco(b.voci));
      } else if (b.tipo === "tabella") {
        dest.append(mdTabella(b));
        if (b.altre) dest.append(el("p", "nota", "… e altre " + b.altre + " righe"));
      } else if (b.tipo === "codice") {
        dest.append(el("pre", "codice md-codice", b.testo));
      } else if (b.tipo === "citazione") {
        const q = el("blockquote", "md-citazione");
        mdDisegna(q, b.blocchi, titoli);
        dest.append(q);
      } else if (b.tipo === "riga") {
        dest.append(el("hr"));
      }
    });
  }

  // {nodo, sommario}: il testo disegnato e, con due titoli o più, il sommario da toccare
  function leggiMarkdown(testo) {
    const t = String(testo || "").replace(/\r\n?/g, "\n").replace(/\t/g, "    ")
      .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f​-‏‪-‮⁦-⁩]/g, "")
      .slice(0, MD.caratteri);
    const nodo = el("div", "documento markdown");
    const titoli = [];
    mdDisegna(nodo, mdBlocchi(t, 0), titoli);
    let sommario = null;
    const voci = titoli.filter((x) => x.livello <= 3);
    if (voci.length >= 2) {
      sommario = el("nav", "sommario-md");
      sommario.setAttribute("aria-label", "Sommario");
      sommario.append(el("div", "sommario-titolo", "Sommario"));
      const min = Math.min(...voci.map((x) => x.livello));
      titoli.forEach((x, k) => {
        if (x.livello > 3) return;
        const b = el("button", "voce-sommario livello-" + (x.livello - min), x.testo);
        b.type = "button";
        b.dataset.mdVai = String(k);
        sommario.append(b);
      });
    }
    return { nodo, sommario };
  }

  // Il sommario porta al titolo, dentro la stessa scheda (anche nello strato del telefono)
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest && ev.target.closest("button[data-md-vai]");
    if (!b) return;
    const s = b.closest("article.scheda");
    const h = s && s.querySelector('.markdown [data-md-ancora="' + CSS.escape(b.dataset.mdVai) + '"]');
    if (h) h.scrollIntoView({ block: "start", behavior: "instant" });
  });

  // ─── «Scarica» nella scheda del documento (07/10, calliope/schermi/scarica.py) ───
  // Il server dà un indirizzo di pochi minuti, solo a uno schermo personale a cui la scheda è
  // arrivata; il browser salva il file (sul telefono negli scaricamenti)
  const NOMI_SCARICA = { md: "Markdown", pdf: "PDF", word: "Word", excel: "Excel", audio: "l'audio" };
  function pulsantiScarica(c) {
    const box = el("div", "scarica");
    (c.scarica || []).forEach((f) => {
      if (!NOMI_SCARICA[f]) return;
      const b = el("button", "piccolo-bottone tasto-scarica", "Scarica " + NOMI_SCARICA[f]);
      b.type = "button";
      b.dataset.scarica = f;
      b.dataset.chiaveScheda = chiaveDi(c);
      box.append(b);
    });
    box.append(el("span", "esito-scarica", ""));
    return box;
  }
  document.addEventListener("click", async (ev) => {
    const b = ev.target.closest && ev.target.closest("button[data-scarica]");
    if (!b || b.disabled) return;
    const esito = b.parentElement && b.parentElement.querySelector(".esito-scarica");
    const dire = (t) => { if (esito) esito.textContent = t; };
    if (!S.sessione) { dire("Non collegato: riprova tra poco."); return; }
    b.disabled = true;
    dire("Preparo il file…");
    try {
      const r = await fetch("/api/scarica", {
        method: "POST", cache: "no-store",
        headers: { "Content-Type": "application/json", "X-Calliope-Sessione": S.sessione },
        body: JSON.stringify({ chiave: b.dataset.chiaveScheda, formato: b.dataset.scarica }),
      });
      let d = {};
      try { d = await r.json(); } catch (e) { /* niente */ }
      if (r.status !== 200 || typeof d.url !== "string" || !/^\/scarica\/[\w-]+$/.test(d.url)) {
        dire(d.errore || ("Non riesco a scaricarlo (" + r.status + ")."));
        return;
      }
      const a = el("a");
      a.href = d.url;
      a.download = d.nome || "";
      a.hidden = true;
      document.body.append(a);
      a.click();
      a.remove();
      dire("Scaricato: " + (d.nome || "file") + ".");
    } catch (e) {
      dire("Calliope non risponde: riprova.");
    } finally {
      b.disabled = false;
    }
  });

  // ─── la spunta della lista (28/10, passo 2a: POST /api/tocco, schermi/tocchi.py) ───
  // Sugli schermi personali con le sezioni (il telefono e il PC personale) ogni voce è un tasto
  // «checkbox»: il tocco va al server, che lo passa al ciclo della voce come una frase del
  // proprietario (ToolRegistry.call). La voce resta segnata in attesa finché arriva l'esito
  // (evento SSE «tocco») o la lista aggiornata (la scheda che manda il tool); riuscita senza la
  // lista nuova resta spuntata finché una lista la toglie o la rimette; un errore la rimette
  // com'era e si dice accanto, nella regione role="status" della scheda. Senza esito entro
  // SPUNTA.attesaMs il tocco è ancora nella coda del ciclo (un turno a voce in corso): la pagina
  // lo dice com'è e non lo rimanda (revisioni della PR #261).
  const SPUNTE = new Map();          // lista e voce → ms: tocchi mandati, esito non ancora arrivato
  const TOLTE = new Map();           // lista e voce → {t, srv}: tolte, la lista nuova non è arrivata
  const SPUNTA = { attesaMs: 30000, tettoMs: 600000 };
  const OCCUPATA = "Calliope è occupata: la spunta arriva appena finisce.";
  function spuntabile() { return !!(S.personale && (S.sezioni || CAROSELLO)); }
  function chiaveSpunta(lista, voce) { return String(lista) + "\n" + String(voce); }
  function mandata(lista, voce) {
    const t = SPUNTE.get(chiaveSpunta(lista, voce));
    return t !== undefined && Date.now() - t < SPUNTA.tettoMs;
  }
  function tolta(lista, voce) {
    const x = TOLTE.get(chiaveSpunta(lista, voce));
    return !!x && Date.now() - x.t < SPUNTA.attesaMs;
  }
  function vociDaSpuntare(c) {
    const ul = el("ul", "voci spunte");
    ul.setAttribute("aria-label", "Voci: tocca quella che hai preso per toglierla");
    const presenti = new Set();
    c.voci.forEach((v) => {
      presenti.add(String(v.testo));
      // Una lista più recente dell'esito che la contiene ancora: la voce è stata rimessa
      // («rimettilo» a voce), e si tocca di nuovo
      const k = chiaveSpunta(c.lista, v.testo), x = TOLTE.get(k);
      if (x && Number(c.creata) > x.srv) TOLTE.delete(k);
      const li = el("li", v.nuova ? "nuova" : "");
      const b = el("button", "spunta");
      b.type = "button";
      b.setAttribute("role", "checkbox");
      b.dataset.lista = String(c.lista);
      b.dataset.voce = String(v.testo);
      statoSpunta(b, tolta(c.lista, v.testo) ? "tolta" : mandata(c.lista, v.testo) ? "attesa" : "libera");
      const casella = el("span", "casella");
      casella.setAttribute("aria-hidden", "true");
      b.append(casella, el("span", "testo-voce", v.testo));
      li.append(b);
      ul.append(li);
    });
    // Le voci toccate che non ci sono più (la lista aggiornata è arrivata): finita l'attesa
    for (const m of [SPUNTE, TOLTE]) {
      for (const k of [...m.keys()]) {
        const [l, v] = k.split("\n");
        if (l === String(c.lista) && !presenti.has(v)) m.delete(k);
      }
    }
    return ul;
  }
  // libera | attesa | tolta (riuscita, la lista nuova non è ancora arrivata: non si ritocca)
  function statoSpunta(b, stato) {
    b.setAttribute("aria-checked", stato === "libera" ? "false" : "true");
    b.classList.toggle("in-attesa", stato === "attesa");
    if (stato === "attesa") b.setAttribute("aria-busy", "true"); else b.removeAttribute("aria-busy");
    if (stato === "tolta") b.setAttribute("aria-disabled", "true"); else b.removeAttribute("aria-disabled");
  }
  // Restituisce quanti tasti di quella voce ci sono adesso nella pagina
  function segnaSpunta(lista, voce, stato, testo, errore) {
    const carte = new Set();
    let n = 0;
    for (const b of document.querySelectorAll("button.spunta")) {
      if (b.dataset.lista !== lista) continue;
      const card = b.closest(".scheda");
      if (card) carte.add(card);
      if (b.dataset.voce === voce) { statoSpunta(b, stato); n++; }
    }
    for (const card of carte) {
      const es = card.querySelector(".esito-tocco");
      if (!es) continue;
      if (es.textContent !== testo) es.textContent = testo;
      // L'attesa in tono tenue, un errore nel colore dell'allarme
      es.classList.toggle("errore", !!errore);
    }
    return n;
  }
  document.addEventListener("click", async (ev) => {
    const b = ev.target.closest && ev.target.closest("button.spunta");
    if (!b) return;
    const lista = b.dataset.lista, voce = b.dataset.voce;
    const k = chiaveSpunta(lista, voce);
    if (mandata(lista, voce)) {
      // Il primo tocco aspetta ancora nella coda del ciclo: un altro direbbe «non c'è»
      segnaSpunta(lista, voce, "attesa", OCCUPATA, false);
      return;
    }
    if (b.getAttribute("aria-checked") === "true") return;
    const t0 = Date.now();
    SPUNTE.set(k, t0);
    segnaSpunta(lista, voce, "attesa", "Tolgo «" + voce + "»…", false);
    setTimeout(() => {
      if (SPUNTE.get(k) === t0) segnaSpunta(lista, voce, "attesa", OCCUPATA, false);
    }, SPUNTA.attesaMs);
    let r;
    try { r = await postSessione("/api/tocco", { tocco: "spunta_lista", lista, voce }); }
    catch (e) { r = { status: 0, dati: {} }; }
    if (r.status === 200 || SPUNTE.get(k) !== t0) return;    // l'esito arriva dal ciclo
    SPUNTE.delete(k);
    segnaSpunta(lista, voce, "libera", String(r.dati.errore || MESSAGGI[r.status] || "Calliope non risponde: riprova tra poco."), true);
  });
  // L'esito dal ciclo (evento «tocco»): riuscito, se la voce è ancora nella pagina (la lista
  // aggiornata non è arrivata) resta spuntata finché una lista nuova non la toglie o la rimette;
  // rifiutato (permesso, orari, una voce sparita nel frattempo) la voce torna com'era con il
  // motivo accanto
  function esitoTocco(d) {
    if (d && d.tocco in TASTI_TIMER) { esitoTimer(d); return; }
    // I tocchi dello Studio (30/10, #284): la home si rilegge
    if (d && String(d.tocco || "").startsWith("studio_")) {
      if (window.CalliopeStudio && window.CalliopeStudio.esito) window.CalliopeStudio.esito(d);
      return;
    }
    if (!d || d.tocco !== "spunta_lista") return;
    const p = d.pagina || {};
    const lista = String(p.lista || ""), voce = String(p.voce || "");
    const k = chiaveSpunta(lista, voce);
    SPUNTE.delete(k);
    if (d.ok) {
      if (segnaSpunta(lista, voce, "tolta", "", false)) TOLTE.set(k, { t: Date.now(), srv: ora() / 1000 });
    } else {
      segnaSpunta(lista, voce, "libera", String(d.errore || "Non ci sono riuscita: riprova."), true);
    }
  }

  // ─── i tasti del timer (28/10, passo 2b, #257: «+1 minuto» e «Ferma», POST /api/tocco) ───
  // Solo sugli schermi personali con le sezioni, in Adesso e nella pagina Agenda, su una scheda
  // con un timer solo e ancora attivo. La pagina manda la chiave della scheda (timer:<id>-<creazione>):
  // il server controlla che quel timer ci sia ancora e il ciclo cambia proprio lui (timer_imposta
  // «aggiungi» o agenda_annulla). La scheda aggiornata (stessa chiave) arriva prima dell'esito;
  // l'esito (evento «tocco») chiude l'attesa, un errore si dice accanto nella regione
  // role="status" della scheda. Come la spunta: senza esito entro SPUNTA.attesaMs lo dice, e
  // finché il primo tocco aspetta nella coda del ciclo un altro non parte. Il nome per chi non
  // vede comincia col testo visibile (WCAG 2.5.3: «tocca +1 minuto» col controllo vocale)
  const TASTI_TIMER = {
    timer_piu: { testo: "+1 minuto", nome: "+1 minuto al timer", attesa: "Aggiungo un minuto…" },
    timer_ferma: { testo: "Ferma", nome: "Ferma il timer", attesa: "Fermo il timer…" },
  };
  const OCCUPATA_TIMER = "Calliope è occupata: il timer cambia appena finisce.";
  const TIMER_MANDATI = new Map();   // chiave della scheda → {tocco, t}: esito non ancora arrivato
  function timerMandato(chiave) {
    const x = TIMER_MANDATI.get(String(chiave));
    return x && Date.now() - x.t < SPUNTA.tettoMs ? x : null;
  }
  function tastiTimer(c, t) {
    const box = el("div", "tasti-timer");
    const m = timerMandato(c.chiave);
    for (const [tocco, v] of Object.entries(TASTI_TIMER)) {
      const b = el("button", "tasto-timer", v.testo);
      b.type = "button";
      b.dataset.tocco = tocco;
      b.dataset.chiave = String(c.chiave);
      b.setAttribute("aria-label", v.nome + (t.etichetta ? " " + t.etichetta : ""));
      if (m) {
        b.setAttribute("aria-busy", "true");
        b.classList.toggle("in-attesa", m.tocco === tocco);
      }
      box.append(b);
    }
    return box;
  }
  // L'attesa o l'esito sui tasti di un timer (in ogni scheda dove c'è: Adesso e Agenda)
  function segnaTimer(chiave, attesa, testo, errore) {
    const carte = new Set();
    const x = TIMER_MANDATI.get(String(chiave));
    for (const b of document.querySelectorAll("button.tasto-timer")) {
      if (b.dataset.chiave !== String(chiave)) continue;
      const card = b.closest(".scheda");
      if (card) carte.add(card);
      if (attesa) b.setAttribute("aria-busy", "true"); else b.removeAttribute("aria-busy");
      b.classList.toggle("in-attesa", !!(attesa && x && x.tocco === b.dataset.tocco));
    }
    for (const card of carte) {
      const es = card.querySelector(".esito-tocco");
      if (!es) continue;
      if (es.textContent !== testo) es.textContent = testo;
      es.classList.toggle("errore", !!errore);
    }
  }
  document.addEventListener("click", async (ev) => {
    const b = ev.target.closest && ev.target.closest("button.tasto-timer");
    if (!b) return;
    const chiave = b.dataset.chiave, tocco = b.dataset.tocco;
    if (!(tocco in TASTI_TIMER)) return;
    if (timerMandato(chiave)) { segnaTimer(chiave, true, OCCUPATA_TIMER, false); return; }
    const t0 = Date.now();
    TIMER_MANDATI.set(chiave, { tocco, t: t0 });
    segnaTimer(chiave, true, TASTI_TIMER[tocco].attesa, false);
    setTimeout(() => {
      const x = TIMER_MANDATI.get(chiave);
      if (x && x.t === t0) segnaTimer(chiave, true, OCCUPATA_TIMER, false);
    }, SPUNTA.attesaMs);
    let r;
    try { r = await postSessione("/api/tocco", { tocco, chiave }); }
    catch (e) { r = { status: 0, dati: {} }; }
    const x = TIMER_MANDATI.get(chiave);
    if (r.status === 200 || !x || x.t !== t0) return;      // l'esito arriva dal ciclo
    TIMER_MANDATI.delete(chiave);
    segnaTimer(chiave, false, String(r.dati.errore || MESSAGGI[r.status] || "Calliope non risponde: riprova tra poco."), true);
  });
  // L'esito dal ciclo: riuscito, la scheda aggiornata è già arrivata (o il timer è fermato e i
  // tasti non ci sono più); rifiutato (il timer è suonato nel frattempo, gli orari dei tutori)
  // i tasti tornano liberi con il motivo accanto
  function esitoTimer(d) {
    const chiave = String((d.pagina || {}).chiave || "");
    TIMER_MANDATI.delete(chiave);
    if (d.ok) segnaTimer(chiave, false, "", false);
    else segnaTimer(chiave, false, String(d.errore || "Non ci sono riuscita: riprova."), true);
  }

  const DISEGNA = {
    lista(c, corpo) {
      if (!c.voci || !c.voci.length) { corpo.append(el("p", "vuoto", "La lista è vuota.")); }
      else if (spuntabile() && c.lista && !c.storica) {
        // La spunta (28/10, passo 2a: schermi/tocchi.py): solo sugli schermi personali con le
        // sezioni, toccare vale come dire «ho preso il latte»
        corpo.append(vociDaSpuntare(c));
      } else {
        const ul = el("ul", "voci");
        c.voci.forEach((v) => ul.append(el("li", v.nuova ? "nuova" : "", v.testo)));
        corpo.append(ul);
      }
      if (c.altre) corpo.append(el("p", "nota", "e altre " + c.altre));
      if (c.tolti && c.tolti.length) corpo.append(el("p", "nota", "Tolto: " + c.tolti.join(", ")));
      if (spuntabile() && c.lista && !c.storica) {
        // Sempre nel DOM: VoiceOver legge i cambi di una regione role="status" già lì
        const es = el("p", "esito-tocco", "");
        es.setAttribute("role", "status");
        corpo.append(es);
      }
    },
    timer(c, corpo) {
      if (!c.timer || !c.timer.length) { corpo.append(el("p", "vuoto", "Nessun timer attivo.")); return; }
      const g = el("div", "timer");
      // I tasti (28/10, #257): sugli schermi personali con le sezioni, una scheda con un timer solo
      // Una copia vecchia dalla conversazione (28/10, #242, `storica`): niente tasti né conto
      const tasti = spuntabile() && !c.storica && !!c.chiave && c.timer.length === 1;
      let conTasti = false;
      c.timer.forEach((t) => {
        const r = el("div", "riga" + (c.timer.length === 1 ? " solo" : ""));
        r.append(el("div", "nome", t.etichetta));
        // Chi l'ha messo: solo sugli schermi personali (la TV di casa la vedono anche gli ospiti)
        if (t.chi && spuntabile()) r.append(el("div", "chi", "messo da " + t.chi));
        if (t.stato && t.stato !== "attivo") {
          // Annullato o scaduto: la stessa scheda con lo stato e l'ora, niente conto
          r.classList.add("finito");
          r.append(el("div", "resto", t.nota || t.stato));
          g.append(r);
          return;
        }
        if (c.storica) {
          r.append(el("div", "resto storico", "alle " + fmtOra.format(new Date(Number(t.fine) * 1000))));
          g.append(r);
          return;
        }
        const resto = el("div", "resto", "");
        resto.dataset.fine = String(t.fine * 1000);
        r.append(resto);
        if (tasti) { r.append(tastiTimer(c, t)); conTasti = true; }
        g.append(r);
      });
      corpo.append(g);
      if (conTasti) {
        // Sempre nel DOM, come per la spunta: VoiceOver legge i cambi di una regione già lì
        const es = el("p", "esito-tocco", "");
        es.setAttribute("role", "status");
        corpo.append(es);
      }
    },
    promemoria(c, corpo) {
      // Un giorno della pagina Agenda (28/10, #257) ha la sua frase del vuoto e le voci oltre
      if (!c.voci || !c.voci.length) corpo.append(el("p", "vuoto", c.vuoto ? String(c.vuoto) : "Niente in agenda."));
      else {
        const g = el("div", "agenda");
        c.voci.forEach((v) => {
          const r = el("div", "riga");
          r.append(el("div", "quando", v.quando));
          r.append(el("div", "cosa", v.testo + (v.tipo === "appuntamento" ? "" : " (promemoria)")));
          g.append(r);
        });
        corpo.append(g);
      }
      if (c.altre) corpo.append(el("p", "nota", "e altre " + c.altre + " più avanti"));
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
      // `di`: di chi è, nella pagina Documenti di chi amministra (28/10, #259)
      const meta = el("p", "sotto", [c.di ? "Di " + c.di : "", c.file, c.cartella].filter(Boolean).join(" · "));
      if (c.modifica) meta.textContent += " · cambiato: " + c.modifica;
      corpo.append(meta);
      if (Array.isArray(c.scarica) && c.scarica.length) corpo.append(pulsantiScarica(c));
      if (c.riassunto) corpo.append(el("p", "riassunto-lavoro", c.riassunto));
      if (typeof c.markdown === "string") {
        // Il testo in Markdown dell'agente (07/10): il lettore di questa pagina, mai HTML
        const md = leggiMarkdown(c.markdown);
        if (md.sommario) corpo.append(md.sommario);
        corpo.append(md.nodo);
        if (c.tagliato) corpo.append(el("p", "nota", "Il testo continua nel file: «Scarica» lo dà intero."));
        return;
      }
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
    // Un avviso di pericolo per il tutore (14/10, minori.Avvisi.scheda_di): il testo senza
    // parole con quando e da dove; la trascrizione e l'audio si aprono solo qui, a richiesta
    avviso(c, corpo) {
      corpo.append(el("div", "testo-lungo", c.testo || ""));
      if (c.falso) corpo.append(el("p", "nota", "Segnato falso da chi amministra."));
      if (Array.isArray(c.trascrizione) && c.trascrizione.length) {
        const d = el("details", "trascrizione-avviso");
        d.append(el("summary", "", "Leggi cosa si è detto"));
        c.trascrizione.forEach((r) => {
          const p = el("p", r.segnale ? "segnale" : "", "");
          const chi = [r.ora, r.chi].filter(Boolean).join(" · ");
          p.append(el("strong", "", chi + ": "), document.createTextNode(String(r.testo || "")));
          d.append(p);
        });
        corpo.append(d);
      }
      if (c.nota) corpo.append(el("p", "nota", c.nota));
      if (Array.isArray(c.scarica) && c.scarica.length) corpo.append(pulsantiScarica(c));
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
      if (typeof c.fotoIntera === "string" && /^\/scarica\/[A-Za-z0-9_-]{16,}$/.test(c.fotoIntera)) {
        img.src = c.fotoIntera;
        // Il gettone vale 180 s e poche richieste: se il browser la ricarica dopo, se ne chiede uno
        // nuovo, una volta (seconda revisione della PR #273)
        if (Number.isInteger(c.cassetto)) img.addEventListener("error", () => rigettoneFoto(img, c.cassetto));
      }
      else if (typeof c.src === "string" && c.src.startsWith("data:image/jpeg;base64,")) img.src = c.src;
      corpo.append(img);
      if (c.didascalia) corpo.append(el("p", "didascalia", c.didascalia));
      // Lo stato della foto tenuta (28/10, decisione 0034), nel dettaglio dalla Conversazione
      const riga = rigaFoto(c);
      if (riga) {
        const p = el("p", "stato-foto stato-foto-" + c.statoFoto, riga);
        if (c.statoFoto === "archiviata") {
          const a = el("button", "piccolo-bottone vai-documenti", "Apri i tuoi documenti");
          a.type = "button";
          a.dataset.chatVai = "cose/documenti";
          p.append(" ", a);
        }
        corpo.append(p);
      }
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
    lavoro(c, corpo, s, opz) {
      const av = c.avanzamento;
      const intera = !!(opz && opz.intera);
      if (av && ["in_coda", "in_corso"].includes(c.stato)) {
        if (!intera) { disegnaAvanzamento(c, av, corpo, false); return; }
        const sx = el("div", "col-riepilogo");
        disegnaAvanzamento(c, av, sx, true);
        corpo.append(dueColonne(sx, colonnaFlusso(c)));
        return;
      }
      if (intera && (FLUSSI[chiaveDi(c)] || c.registro)) {
        // A lavoro finito, a schermo intero: il risultato a sinistra, il flusso a destra
        const sx = el("div", "col-riepilogo");
        DISEGNA.lavoro(c, sx, s, null);
        corpo.append(dueColonne(sx, colonnaFlusso(c)));
        return;
      }
      // `di`: il lavoro di un'altra persona nella pagina di chi amministra (28/10, #259)
      const stato = c.di && c.stato === "in_attesa" ? "aspetta la risposta di " + c.di : (STATI_LAVORO[c.stato] || c.stato || "");
      const meta = el("p", "sotto", (c.di ? "Di " + c.di + " · " : "") + stato);
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
        if (av.sviluppo) corpo.append(righeSviluppo(av.sviluppo));
        if (av.passi && av.passi.length) corpo.append(passiLavoro(av.passi));
      }
    },
  };

  // ─── Il cassetto dei file (08/10, calliope/cassetto.py) ───
  // Un carosello: anteprima (solo un data URL JPEG per le foto, altrimenti la sigla), nome,
  // quando e da dove, scadenza; Tieni e Tieni ancora; in alto Tieni tutti. Tutto come testo. I
  // pulsanti vanno a /api/cassetto; la scheda aggiornata arriva dal server (stessa chiave).
  // Eliminare si fa a voce (28/10 sera, seguito della #301: non si disfa, e dallo schermo
  // personale di un altro non deve bastare un tocco): niente «Elimina» né «Elimina tutti», la
  // nota lo dice. *Storico: fino al 28/10 sera «Elimina» e «Elimina tutti» (due tocchi)*
  // Difesa in più (29/10, #307): un pulsante che non sia «tieni» o «ancora» non si disegna, e il
  // tocco non lo manda (dietro c'è il 403 del server e il rifiuto di Cassetto.da_pagina)
  const AZIONI_CASSETTO = ["tieni", "ancora"];
  function bottoneCassetto(testo, azione, ids, cls) {
    if (!AZIONI_CASSETTO.includes(azione)) return document.createDocumentFragment();
    const b = el("button", "piccolo-bottone tasto-cassetto" + (cls ? " " + cls : ""), testo);
    b.type = "button";
    b.dataset.cassetto = azione;
    b.dataset.ids = ids.join(",");
    return b;
  }
  DISEGNA.cassetto = function (c, corpo, s) {
    s.classList.add("scheda-cassetto");
    const voci = Array.isArray(c.voci) ? c.voci : [];
    if (c.nota) corpo.append(el("p", "sotto", c.nota));
    if (!voci.length) {
      if (!c.nota) corpo.append(el("p", "vuoto", c.vuoto || "Nessun file."));
      return;
    }
    const ids = voci.map((v) => v.id).filter((i) => Number.isInteger(i));
    const giorni = Number.isInteger(c.giorni) ? c.giorni : 7;
    // In sola lettura (28/10, #267: i file del figlio nella pagina del tutore) niente tasti
    const tasti = c.sola_lettura !== true;
    const tutti = el("div", "cassetto-tutti");
    if (tasti) {
      tutti.append(el("span", "nota-cassetto", "Per eliminare un file dimmelo a voce."));
      if (voci.some((v) => v.tieni)) {
        tutti.append(bottoneCassetto("Tieni tutti", "tieni", ids.filter((i, k) => voci[k].tieni)));
      }
      tutti.append(el("span", "esito-cassetto", ""));
      corpo.append(tutti);
    }
    const car = el("div", "cassetto-carosello");
    voci.forEach((v) => {
      if (!Number.isInteger(v.id)) return;
      const f = el("section", "cassetto-voce");
      const ant = el("div", "cassetto-anteprima");
      if (typeof v.src === "string" && v.src.startsWith("data:image/jpeg;base64,")) {
        const img = el("img");
        img.alt = v.tipo || "foto";
        img.src = v.src;
        ant.append(img);
      } else {
        ant.append(el("span", "cassetto-sigla", v.sigla || "FILE"));
      }
      f.append(ant);
      f.append(el("p", "cassetto-nome", v.nome || "file"));
      f.append(el("p", "sotto", [v.tipo, v.dimensione].filter(Boolean).join(" · ")));
      f.append(el("p", "sotto", "Arrivato " + [v.arrivato, v.da].filter(Boolean).join(" ")));
      if (v.scade) f.append(el("p", "cassetto-scade", "Scade " + v.scade));
      if (tasti) {
        const p = el("div", "cassetto-pulsanti");
        if (v.tieni) p.append(bottoneCassetto("Tieni", "tieni", [v.id]));
        p.append(bottoneCassetto("Tieni ancora " + giorni + " giorni", "ancora", [v.id]));
        f.append(p);
      }
      car.append(f);
    });
    corpo.append(car);
    if (c.altri) corpo.append(el("p", "nota", "e altri " + c.altri));
  };
  document.addEventListener("click", async (ev) => {
    const b = ev.target.closest && ev.target.closest("button[data-cassetto]");
    if (!b || b.disabled) return;
    const s = b.closest("article.scheda");
    const esito = s && s.querySelector(".esito-cassetto");
    const dire = (t) => { if (esito) esito.textContent = t; };
    if (!AZIONI_CASSETTO.includes(b.dataset.cassetto)) {
      dire("Per eliminare un file dimmelo a voce.");
      return;
    }
    if (!S.sessione) { dire("Non collegato: riprova tra poco."); return; }
    const ids = (b.dataset.ids || "").split(",").map((x) => parseInt(x, 10)).filter(Number.isInteger);
    if (!ids.length) return;
    b.disabled = true;
    dire("…");
    try {
      const r = await fetch("/api/cassetto", {
        method: "POST", cache: "no-store",
        headers: { "Content-Type": "application/json", "X-Calliope-Sessione": S.sessione },
        body: JSON.stringify({ azione: b.dataset.cassetto, id: ids }),
      });
      let d = {};
      try { d = await r.json(); } catch (e) { /* niente */ }
      dire(r.status === 200 ? (d.frase || "Fatto.") : (d.errore || ("Non ci sono riuscita (" + r.status + ").")));
      // La pagina Cassetto aperta si rilegge subito (2d, seconda revisione della PR #267: prima
      // aspettava la raffica delle schede o il giro dei 60 s)
      if (r.status === 200) emetti("cassetto", { azione: b.dataset.cassetto });
    } catch (e) {
      dire("Calliope non risponde: riprova.");
    } finally {
      b.disabled = false;
    }
  });

  // ─── Una voce nuova da salvare come conoscente (14/10, calliope/stanza/conoscenti.py) ───
  // Solo sugli schermi personali di chi amministra: la domanda, un pezzo breve di trascrizione,
  // gli avvisi (omonimi, età), il nome proposto (si può cambiare), cognome e nota facoltativi;
  // Sì e No vanno a /api/conoscenti, la scheda aggiornata arriva dal server (stessa chiave).
  // Tutto come testo
  DISEGNA.conoscente = function (c, corpo, s) {
    s.classList.add("scheda-conoscente");
    corpo.append(el("p", "domanda-modulo", c.domanda || ""));
    (Array.isArray(c.estratto) ? c.estratto : []).forEach((r) => {
      corpo.append(el("p", "estratto-conoscente", r));
    });
    (Array.isArray(c.avvisi) ? c.avvisi : []).forEach((a) => {
      corpo.append(el("p", "nota", a));
    });
    if (!c.aperta) return;
    const f = el("div", "modulo modulo-conoscente");
    f.dataset.proposta = String(c.proposta || "");
    [["nome", "Nome", c.nome || ""], ["cognome", "Cognome (se lo sai)", ""],
     ["nota", "Una nota per distinguerlo (es. collega di…)", ""]].forEach(([k, et, v]) => {
      const campo = el("div", "campo-modulo");
      const id = "conoscente-" + (c.proposta || "") + "-" + k;
      const l = el("label", "", et);
      l.htmlFor = id;
      const i = el("input");
      i.id = id;
      i.name = k;
      i.maxLength = k === "nota" ? 80 : 40;
      i.autocomplete = "off";
      i.value = v;
      campo.append(l, i);
      f.append(campo);
    });
    const p = el("div", "cassetto-tutti");
    const si = el("button", "invia-modulo", "Sì, salvalo");
    si.type = "button";
    si.dataset.conoscente = "si";
    const no = el("button", "piccolo-bottone", "No");
    no.type = "button";
    no.dataset.conoscente = "no";
    p.append(si, no, el("span", "esito-cassetto esito-conoscente", ""));
    f.append(p);
    corpo.append(f);
  };
  document.addEventListener("click", async (ev) => {
    const b = ev.target.closest && ev.target.closest("button[data-conoscente]");
    if (!b || b.disabled) return;
    const f = b.closest(".modulo-conoscente");
    if (!f) return;
    const esito = f.querySelector(".esito-conoscente");
    const dire = (t) => { if (esito) esito.textContent = t; };
    if (!S.sessione) { dire("Non collegato: riprova tra poco."); return; }
    const val = (k) => { const i = f.querySelector("input[name=" + k + "]"); return i ? i.value.trim() : ""; };
    b.disabled = true;
    dire("…");
    try {
      const r = await fetch("/api/conoscenti", {
        method: "POST", cache: "no-store",
        headers: { "Content-Type": "application/json", "X-Calliope-Sessione": S.sessione },
        body: JSON.stringify({ azione: b.dataset.conoscente, proposta: f.dataset.proposta,
          nome: val("nome"), cognome: val("cognome"), nota: val("nota") }),
      });
      let d = {};
      try { d = await r.json(); } catch (e) { /* niente */ }
      dire(r.status === 200 ? (d.frase || "Fatto.") : (d.errore || ("Non ci sono riuscita (" + r.status + ").")));
      // *Storico: fino al 29/10 qui c'era anche emetti("cassetto"), copiato dal gestore del
      // cassetto (revisione della PR #309): rileggeva la pagina Cassetto dopo un conoscente*
    } catch (e) {
      dire("Calliope non risponde: riprova.");
    } finally {
      b.disabled = false;
    }
  });

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

  // ─── le azioni del cruscotto sulla ricerca web (09/10, calliope/web/motore.py) ───
  // «Controlla» e «Aggiorna» di SearXNG, con due tocchi: il primo chiede al server un gettone
  // (legato a questo schermo e all'azione, scade in un minuto) e il pulsante diventa «Tocca
  // ancora…»; il secondo lo usa e l'azione parte. Mentre gira, il cruscotto si aggiorna ogni
  // 2 s per mostrarne la fase e l'esito. Il server ricontrolla tutto a ogni richiesta
  S.motore = { armato: null, msg: "", corsa: null };

  async function chiediMotore(corpo) {
    try {
      const x = await fetch("/api/motore", { method: "POST", cache: "no-store",
        headers: { "X-Calliope-Sessione": S.sessione, "Content-Type": "application/json" },
        body: JSON.stringify(corpo) });
      return { status: x.status, dati: await x.json().catch(() => ({})) };
    } catch (e) {
      return { status: 0, dati: { errore: "Calliope non risponde" } };
    }
  }

  function ridisegnaCruscotto() {
    const c = S.cronologia.find((x) => chiaveDi(x) === CRUSCOTTO);
    if (c && S.corrente && chiaveDi(S.corrente) === CRUSCOTTO) ridisegna(c);
    else if (c) emetti("schede", {});
  }

  async function toccaMotore(azione) {
    if (!S.sessione || !S.amministra) return;
    const a = S.motore.armato;
    if (a && a.azione === azione && ora() < a.fino) {
      S.motore.armato = null;
      const r = await chiediMotore({ azione, gettone: a.gettone });
      S.motore.msg = r.status === 200 ? (r.dati.frase || "Partito.") : (r.dati.frase || r.dati.errore || "errore " + r.status);
      if (r.status === 200) seguiMotore();
      await apriCruscotto(false, true);
      ridisegnaCruscotto();
      return;
    }
    const r = await chiediMotore({ azione });
    if (r.status === 403 || r.status === 401) { impostaAmministra(false); return; }
    if (r.status !== 200) { S.motore.msg = r.dati.errore || "errore " + r.status; ridisegnaCruscotto(); return; }
    const fino = ora() + Math.min(60, r.dati.scade_s || 60) * 1000 - 1500;
    S.motore.armato = { azione, gettone: r.dati.gettone, fino };
    S.motore.msg = "";
    ridisegnaCruscotto();
    setTimeout(() => {
      if (S.motore.armato && S.motore.armato.gettone === r.dati.gettone) { S.motore.armato = null; ridisegnaCruscotto(); }
    }, Math.max(1000, fino - ora()));
  }

  // Finché un controllo o un aggiornamento gira: il cruscotto ogni 2 s (al più 20 minuti)
  function seguiMotore() {
    if (S.motore.corsa) return;
    const fine = ora() + 20 * 60 * 1000;
    S.motore.corsa = setInterval(async () => {
      if (!cruscottoAperto() || ora() > fine) { clearInterval(S.motore.corsa); S.motore.corsa = null; return; }
      await apriCruscotto(false);
      const c = S.cronologia.find((x) => chiaveDi(x) === CRUSCOTTO);
      const m = c && c.dati && c.dati.motore;
      if (m && !m.in_corso) { clearInterval(S.motore.corsa); S.motore.corsa = null; S.motore.msg = ""; ridisegnaCruscotto(); }
    }, 2000);
  }

  document.addEventListener("click", (ev) => {
    const b = ev.target.closest && ev.target.closest("[data-motore]");
    if (!b || b.disabled) return;
    toccaMotore(b.dataset.motore);
  });

  // ─── la scheda «Conversazione» (08/10, calliope/conversazioni.py) ───
  // Le frasi della persona (come trascritte o scritte) e le risposte di Calliope, con l'ora e il
  // satellite, dall'archivio delle conversazioni: solo sugli schermi personali del proprietario
  // (il server la manda solo lì). Una scheda di questa pagina, come il cruscotto: i turni
  // nuovi arrivano con l'evento «chat» e si aggiungono in fondo (allinea tocca solo i nodi
  // nuovi). Tutto come testo (textContent): le frasi e le risposte non sono HTML
  const CHAT = "chat";
  // Le schede che vivono solo nella pagina: «Pulisci» non le tocca
  const SOLO_PAGINA = new Set([CRUSCOTTO, CHAT]);
  const fmtGiorno = new Intl.DateTimeFormat("it-IT", { weekday: "long", day: "numeric", month: "long" });

  function turnoValido(t) {
    return t && Number.isInteger(t.id) && typeof t.quando === "number"
      && (typeof t.domanda === "string" || typeof t.risposta === "string");
  }
  function potaChat() {
    if (S.chatGiorni > 0) {
      const limite = ora() / 1000 - S.chatGiorni * 86400;
      S.chat = S.chat.filter((t) => t.quando >= limite);
    }
    if (S.chat.length > S.chatMax) S.chat = S.chat.slice(S.chat.length - S.chatMax);
  }

  function impostaChat(d) {
    if (!d) {
      S.chatOk = false;
      S.chat = [];
      togliScheda(CHAT);
    } else {
      S.chatOk = true;
      if (Number.isInteger(d.max) && d.max > 0) S.chatMax = d.max;
      if (typeof d.giorni === "number") S.chatGiorni = d.giorni;
      // L'archivio è la fonte: la lista del server sostituisce quella di prima
      S.chat = (Array.isArray(d.turni) ? d.turni : []).filter(turnoValido).sort((a, b) => a.id - b.id);
      potaChat();
      aggiornaChat();
    }
    emetti("chat", { attiva: S.chatOk });
    segnaChat();
  }

  function chatDalServer(d) {
    if (!S.chatOk || !d) return;
    if (d.reset) S.chat = [];
    const visti = new Set(S.chat.map((t) => t.id));
    for (const t of (Array.isArray(d.turni) ? d.turni : [])) {
      if (!turnoValido(t) || visti.has(t.id)) continue;   // un doppione per id non entra
      S.chat.push(t);
      visti.add(t.id);
    }
    S.chat.sort((a, b) => a.id - b.id);
    potaChat();
    const v = S.chatVista;
    if (d.reset) { v.turni = null; v.giorno = ""; v.schede = false; v.testo = ""; v.nota = ""; v.n++; svuotaCercaChat(); }
    else if (v.turni) {
      // Con un filtro: il turno nuovo entra se lo passa (oggi, solo schede); mai in una ricerca
      const gia = new Set(v.turni.map((t) => t.id));
      for (const t of (Array.isArray(d.turni) ? d.turni : [])) {
        if (turnoValido(t) && !gia.has(t.id) && passaFiltro(t)) { v.turni.push(t); v.nota = ""; }
      }
    }
    aggiornaChat();
  }

  // ── i filtri e la ricerca della Conversazione (28/10, #242) ──
  function giornoDi(ms) { const d = new Date(ms); return d.getFullYear() + "-" + d.getMonth() + "-" + d.getDate(); }
  function passaFiltro(t) {
    const v = S.chatVista;
    if (v.testo || v.giorno === "ieri") return false;
    if (v.giorno === "oggi" && giornoDi(t.quando * 1000) !== giornoDi(ora())) return false;
    if (v.schede && !(Array.isArray(t.schede) && t.schede.length)) return false;
    return true;
  }
  function filtroAcceso() { const v = S.chatVista; return !!(v.giorno || v.schede || v.testo); }
  function turniChat() { return S.chatVista.turni || S.chat; }
  function trovaTurno(id) {
    return turniChat().find((t) => t.id === id) || S.chat.find((t) => t.id === id) || null;
  }
  async function filtraChat() {
    const v = S.chatVista;
    const n = ++v.n;
    if (!filtroAcceso()) {
      v.turni = null; v.nota = ""; v.attesa = false;
      aggiornaChat();
      return;
    }
    v.attesa = true;
    aggiornaChat();
    let r;
    try { r = await postSessione("/api/conversazione", { giorno: v.giorno || null, schede: v.schede, testo: v.testo }); }
    catch (e) { r = { status: 0, dati: {} }; }
    if (n !== v.n) return;
    v.attesa = false;
    if (r.status === 200 && Array.isArray(r.dati.turni)) {
      v.turni = r.dati.turni.filter(turnoValido).sort((a, b) => a.id - b.id);
      // Un turno arrivato dal vivo mentre si aspettava la risposta (revisione della PR #271)
      const gia = new Set(v.turni.map((x) => x.id));
      const ultimo = v.turni.length ? v.turni[v.turni.length - 1].id : 0;
      for (const x of S.chat) if (x.id > ultimo && !gia.has(x.id) && passaFiltro(x)) v.turni.push(x);
      v.nota = typeof r.dati.nota === "string" ? r.dati.nota : "";
    } else {
      v.turni = v.turni || [];
      v.nota = String((r.dati && r.dati.errore) || MESSAGGI[r.status] || "Non riesco a leggere la conversazione adesso: riprova tra poco.");
    }
    aggiornaChat();
  }
  // Oggi e Ieri si escludono (un secondo tocco toglie il filtro); Solo schede si somma
  function suFiltroChat(quale) {
    const v = S.chatVista;
    if (quale === "schede") v.schede = !v.schede;
    else if (quale === "oggi" || quale === "ieri") v.giorno = v.giorno === quale ? "" : quale;
    else if (quale === "tutto") { v.giorno = ""; v.schede = false; v.testo = ""; v.cercaAperta = false; svuotaCercaChat(); }
    else if (quale === "cerca") {
      // Il tasto apre la casella (e ci mette il cursore); chiusa, la ricerca si toglie
      v.cercaAperta = !(v.cercaAperta || v.testo);
      if (v.cercaAperta) {
        aggiornaChat();
        requestAnimationFrame(() => {
          const i = [...document.querySelectorAll(".chat-cerca input")].find((x) => x.getClientRects().length);
          if (i) { try { i.focus({ preventScroll: true }); } catch (e) { i.focus(); } }
        });
        return;
      }
      if (!v.testo) { aggiornaChat(); return; }
      v.testo = "";
      svuotaCercaChat();
    }
    filtraChat();
  }
  function svuotaCercaChat() { document.querySelectorAll(".chat-cerca input").forEach((i) => { i.value = ""; }); }

  // La scheda piccola dentro la risposta: tipo e titolo in un pulsante, sotto un'anteprima della
  // scheda vera (DISEGNA del suo tipo con `compatta`), inerte e tagliata dal CSS. Un rimando (un
  // lavoro, un gioco: cose vive) ha solo il pulsante e porta alla scheda nella sua sezione
  function costruisciPiccola(c, tid, i) {
    const box = el("div", "scheda-piccola tipo-" + c.tipo + (c.rimando ? " rimando" : ""));
    box.dataset.chatScheda = tid + ":" + i;
    const b = el("button", "piccola-apri");
    b.type = "button";
    const nome = NOMI_TIPO[c.tipo] || String(c.tipo);
    b.append(el("span", "piccola-tipo", nome), el("span", "piccola-titolo", c.titolo || ""));
    const fr = el("span", "piccola-freccia", "›");
    fr.setAttribute("aria-hidden", "true");
    b.append(fr);
    b.setAttribute("aria-label", (c.rimando ? "Vai a " : "Apri ") + nome + (c.titolo ? ": " + c.titolo : ""));
    box.append(b);
    if (!c.rimando && !c.leggera) {
      const ant = el("div", "piccola-anteprima");
      ant.setAttribute("inert", "");
      ant.setAttribute("aria-hidden", "true");
      const finta = el("div", "scheda-mini tipo-" + c.tipo);
      const corpo = el("div", "corpo");
      try { (DISEGNA[c.tipo] || DISEGNA.testo)(c, corpo, finta, { compatta: true }); }
      catch (e) { corpo.replaceChildren(); }
      finta.append(corpo);
      ant.append(finta);
      box.append(ant);
    }
    return box;
  }
  async function apriPiccola(rif) {
    const [tid, i] = String(rif || "").split(":").map(Number);
    const t = trovaTurno(tid);
    let c = t && Array.isArray(t.schede) ? t.schede[i] : null;
    if (!c || typeof c !== "object") return false;
    if (c.rimando) { emetti("vai", { scheda: c }); return true; }
    if (c.leggera) {
      // Una scheda di un turno vecchio arriva leggera (revisione della PR #271): la copia intera
      // si chiede al tocco, solo dai turni del proprietario di questo schermo
      let r;
      try { r = await postSessione("/api/conversazione", { turno: tid, indice: i }); }
      catch (e) { r = { status: 0, dati: {} }; }
      if (r.status !== 200 || !r.dati.scheda || typeof r.dati.scheda !== "object") {
        S.chatVista.nota = String((r.dati && r.dati.errore) || MESSAGGI[r.status] || "Non riesco ad aprire la scheda adesso: riprova tra poco.");
        aggiornaChat();
        return false;
      }
      c = r.dati.scheda;
    }
    if (c.tipo === "foto" && Number.isInteger(c.cassetto)) {
      // La foto tenuta (28/10, decisione 0034): finché c'è, il dettaglio mostra la foto intera
      // e quanto resta; poi «Archiviata.» o «Non c'è più»
      let r;
      try { r = await postSessione("/api/conversazione", { foto: c.cassetto }); }
      catch (e) { r = { status: 0, dati: {} }; }
      const d = r.status === 200 && r.dati ? r.dati : { stato: "sconosciuto" };
      // La foto intera da «Scarica» (un gettone di questo schermo), mai un indirizzo d'altro
      const url = typeof d.url === "string" && /^\/scarica\/[A-Za-z0-9_-]{16,}$/.test(d.url) ? d.url : null;
      c = Object.assign({}, c, { statoFoto: String(d.stato || ""), scadeFoto: Number(d.scade) || 0 },
        url ? { fotoIntera: url } : {});
    }
    // La copia del turno, con una chiave sua: la scheda viva con la stessa chiave (la lista di
    // adesso) resta un'altra cosa
    const copia = Object.assign({}, c, { chiave: "chat:" + tid + ":" + i, scade: null, storica: true });
    if (CAROSELLO) { emetti("intera", { scheda: copia }); return true; }
    // Si torna alla conversazione a schermo intero se era lì (anche passando da un'altra copia)
    if (!S.schedeChat[S.intera]) S.interaTorna = S.intera === CHAT ? CHAT : null;
    S.schedeChat = { [copia.chiave]: copia };
    apriInteroPC(copia.chiave);
    return true;
  }

  function schedaChat() {
    return { tipo: CHAT, id: CHAT, chiave: CHAT, titolo: "La nostra conversazione",
      visibilita: "personale", creata: ora() / 1000, turni: S.chat.slice(), scarica: ["md"] };
  }
  function chatAperta() { return S.cronologia.some((c) => chiaveDi(c) === CHAT); }

  // La scheda già aperta (nella cronologia, mostrata o nel carosello) prende i turni nuovi
  function aggiornaChat() {
    // Il PC personale a sezioni (27/10) la tiene sempre nella sua colonna, anche quando esce
    // dalla cronologia (al più 6 schede): i turni nuovi arrivano lì comunque (revisione #255)
    // Il telefono la tiene nella sezione Conversazione (28/10, #242)
    if ((S.sezioni || CAROSELLO) && S.chatOk) emetti("chatturni", { scheda: schedaChat() });
    // Lo strato a schermo intero aperto sulla conversazione prende i turni nuovi anche quando la
    // conversazione non è nella cronologia (il PC a sezioni: terza revisione della PR #255)
    if (S.intera === CHAT && !CAROSELLO) setTimeout(disegnaInteroPC, 0);
    if (!chatAperta()) return;
    const c = Object.assign(schedaChat(), { sposta: false });
    aggiungiCronologia(c);
    if (S.corrente && chiaveDi(S.corrente) === CHAT) ridisegna(c);
  }

  function apriChat() {
    if (!S.chatOk || !S.sessione) return false;
    const c = schedaChat();
    aggiungiCronologia(c);
    mostra(c);
    return true;
  }

  function togliScheda(k) {
    const i = S.cronologia.findIndex((c) => chiaveDi(c) === k);
    if (i < 0) return;
    S.cronologia.splice(i, 1);
    emetti("schede", {});
    disegnaCronologia();
    if (S.corrente && chiaveDi(S.corrente) === k) {
      S.corrente = null;
      const ultima = S.cronologia[S.cronologia.length - 1];
      if (ultima && valida(ultima) && !CAROSELLO) mostra(ultima); else mostraInattiva();
    }
  }

  // Il pulsante «Conversazione» nella testa (non nel telefono: lì è nella sua sezione)
  function segnaChat() {
    if (CAROSELLO || INCORPORATA) return;
    let b = $("chat-apri");
    if (!b && S.chatOk) {
      b = el("button", "piccolo-bottone apri-chat", "Conversazione");
      b.id = "chat-apri";
      b.type = "button";
      b.title = "Quello che ci siamo detti, con l'ora e il satellite";
      b.addEventListener("click", () => apriChat());
      const testa = $("testa");
      if (testa) testa.insertBefore(b, $("cruscotto-apri") || $("stato"));
    }
    if (b) b.hidden = !S.chatOk;
  }

  async function rigettoneFoto(img, fid) {
    if (img.dataset.riprovata) return;
    img.dataset.riprovata = "1";
    let r;
    try { r = await postSessione("/api/conversazione", { foto: fid }); }
    catch (e) { return; }
    const url = r.status === 200 && r.dati && typeof r.dati.url === "string" ? r.dati.url : "";
    if (/^\/scarica\/[A-Za-z0-9_-]{16,}$/.test(url)) img.src = url;
  }

  // La riga dello stato di una foto tenuta (decisione 0034)
  const fmtGiornoMese = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "long" });
  function rigaFoto(c) {
    switch (c && c.statoFoto) {
      case "tenuta": return "La tengo fino al " + fmtGiornoMese.format(new Date(c.scadeFoto * 1000))
        + ": di' «archiviala» per tenerla sempre.";
      case "archiviata": return "Archiviata.";
      case "eliminata": return "Non c'è più: è stata eliminata dal cassetto.";
      case "persa": return "Non c'è più: non era stata archiviata.";
      default: return "";
    }
  }

  // Il posto di un turno è questo schermo (o il satellite che lo porta)?
  const normaNome = (x) => String(x || "").trim().toLocaleLowerCase("it-IT");
  function luogoProprio(luogo) { return !!luogo && S.nomiPropri.includes(normaNome(luogo)); }
  function nomiPropri(lista) {
    let cambiati = false;
    for (const x of lista || []) {
      const n = normaNome(x);
      if (n && !S.nomiPropri.includes(n)) { S.nomiPropri.push(n); cambiati = true; }
    }
    if (cambiati && S.chatOk) aggiornaChat();
  }

  // I canali di un turno (28/10, #242): detto, scritto, un tocco sullo schermo, un modulo inviato
  const CANALI = { voce: "a voce", scritto: "scritto", tocco: "con un tocco", modulo: "modulo" };
  const FILTRI_CHAT = [["oggi", "Oggi"], ["ieri", "Ieri"], ["schede", "Solo schede"]];
  function testaChat() {
    const v = S.chatVista;
    const t = el("div", "chat-filtri");
    const f = el("div", "chat-chips");
    f.setAttribute("role", "group");
    f.setAttribute("aria-label", "Filtri della conversazione");
    for (const [id, nome] of FILTRI_CHAT) {
      const b = el("button", "chat-chip", nome);
      b.type = "button";
      b.dataset.chatFiltro = id;
      b.setAttribute("aria-pressed", (id === "schede" ? v.schede : v.giorno === id) ? "true" : "false");
      f.append(b);
    }
    // La ricerca si apre col suo tasto (sul telefono lo spazio è dei turni); resta aperta con un
    // testo cercato. «Tutto» toglie filtri e ricerca
    const aperta = v.cercaAperta || !!v.testo;
    const apri = el("button", "chat-chip chat-cerca-apri", "Cerca");
    apri.type = "button";
    apri.dataset.chatFiltro = "cerca";
    apri.setAttribute("aria-expanded", aperta ? "true" : "false");
    const via = el("button", "chat-chip chat-cerca-via", "Tutto");
    via.type = "button";
    via.dataset.chatFiltro = "tutto";
    via.setAttribute("aria-label", "Togli i filtri e la ricerca");
    via.hidden = !filtroAcceso();
    f.append(apri);
    const form = el("form", "chat-cerca");
    form.setAttribute("role", "search");
    form.hidden = !aperta;
    const inp = el("input");
    inp.type = "search";
    inp.name = "testo";
    inp.maxLength = 120;
    inp.autocomplete = "off";
    inp.setAttribute("enterkeyhint", "search");
    inp.setAttribute("aria-label", "Cerca nella conversazione");
    inp.placeholder = "Cerca nella conversazione…";
    inp.value = v.testo;
    const vai = el("button", "chat-chip chat-cerca-vai", "Vai");
    vai.type = "submit";
    vai.setAttribute("aria-label", "Cerca");
    form.append(inp, vai);
    t.append(f, form);
    // Sempre nel DOM: VoiceOver legge i cambi di una regione role="status" già lì
    // L'esito (sempre nel DOM: VoiceOver legge i cambi di una regione role="status" già lì) e,
    // con un filtro, «Tutto» accanto
    const riga = el("div", "chat-stato");
    // Senza una nota del server, che cosa si sta guardando: «Ieri, solo schede: 2 turni»
    let detto = v.attesa ? "Cerco…" : v.nota;
    if (!detto && filtroAcceso() && v.turni) {
      const cosa = [v.giorno === "oggi" ? "Oggi" : v.giorno === "ieri" ? "Ieri" : "", v.schede ? "solo schede" : "",
        v.testo ? "«" + v.testo + "»" : ""].filter(Boolean).join(", ");
      detto = cosa.charAt(0).toUpperCase() + cosa.slice(1) + ": " + v.turni.length + (v.turni.length === 1 ? " turno" : " turni");
    }
    const es = el("p", "chat-esito", detto);
    es.setAttribute("role", "status");
    riga.append(es, via);
    riga.hidden = !filtroAcceso() && !es.textContent;
    t.append(riga);
    return t;
  }

  DISEGNA.chat = function (c, corpo, s, opz) {
    s.classList.add("scheda-chat");
    corpo.append(testaChat());
    const v = S.chatVista;
    // Con un filtro i turni del server; senza, quelli della scheda (la vista viva)
    const turni = v.turni || (Array.isArray(c.turni) ? c.turni : []);
    const box = el("div", "flusso-chat conv-chat");
    box.dataset.segui = "1";
    box.setAttribute("role", "log");
    box.setAttribute("aria-label", "La nostra conversazione");
    box.tabIndex = 0;
    const lista = el("div", "conv-turni");
    if (!turni.length && !v.turni) lista.append(el("p", "fl-vuoto", "Ancora niente: quello che ci diciamo compare qui."));
    let giorno = "";
    turni.forEach((t) => {
      const d = new Date(t.quando * 1000);
      const g = fmtGiorno.format(d);
      if (g !== giorno) { giorno = g; lista.append(el("div", "conv-giorno", g)); }
      const canale = CANALI[t.canale] ? t.canale : "voce";
      const r = el("div", "conv-turno canale-" + canale);
      r.dataset.turno = String(t.id);
      // «10:40 · cucina, a voce», «10:44 · scritto», «10:50 · con un tocco»; il posto solo se
      // non è questo schermo (28/10, #301: «10:46 · a voce» detto dal telefono che si guarda)
      const luogo = luogoProprio(t.luogo) ? "" : t.luogo;
      const dove = [luogo, CANALI[canale]].filter(Boolean).join(canale === "scritto" ? " · " : ", ");
      r.append(el("div", "conv-meta", fmtOra.format(d) + " · " + dove));
      if (t.domanda && (canale === "tocco" || canale === "modulo")) {
        // Un gesto sullo schermo, non una frase: al centro, senza le parentesi della storia
        r.append(el("div", "conv-gesto", String(t.domanda).replace(/^\(([\s\S]*)\)$/, "$1")));
      } else if (t.domanda) {
        const tu = el("div", "conv-tu");
        tu.append(el("div", "conv-chi", "Tu"), el("div", "conv-x", t.domanda));
        r.append(tu);
      }
      const schede = Array.isArray(t.schede) ? t.schede.filter((x) => x && typeof x === "object" && typeof x.tipo === "string") : [];
      if (t.risposta || schede.length) {
        const ca = el("div", "conv-calliope");
        ca.append(el("div", "conv-chi", "Calliope"));
        if (t.risposta) ca.append(el("div", "conv-x", t.risposta));
        schede.forEach((x) => ca.append(costruisciPiccola(x, t.id, t.schede.indexOf(x))));
        r.append(ca);
      }
      lista.append(r);
    });
    box.append(lista);
    const giu = el("button", "fl-fondo", "In fondo");
    giu.type = "button";
    giu.dataset.flussoFondo = "1";
    box.append(giu);
    corpo.append(box);
    // «Scarica Markdown» sotto i turni (28/10, #242: sopra c'erano i filtri e lo spazio dei turni)
    corpo.append(pulsantiScarica(c));
    if (opz && opz.intera) s.classList.add("chat-intera");
  };

  // I filtri, la ricerca e le schede piccole: un ascoltatore solo per tutte le copie della scheda
  // (la colonna del PC, la sezione del telefono, lo schermo intero)
  document.addEventListener("click", (ev) => {
    const t = ev.target;
    if (!t || !t.closest) return;
    const f = t.closest("[data-chat-filtro]");
    if (f) { suFiltroChat(f.dataset.chatFiltro); return; }
    const p = t.closest(".scheda-piccola[data-chat-scheda]");
    if (p) { apriPiccola(p.dataset.chatScheda); return; }
    // «Apri i tuoi documenti» dal dettaglio di una foto archiviata
    const v = t.closest("[data-chat-vai]");
    if (v) {
      if (!CAROSELLO && S.intera) chiudiInteroPC();
      emetti("vai", { scheda: { sezione: v.dataset.chatVai } });
    }
  });
  document.addEventListener("submit", (ev) => {
    const form = ev.target;
    if (!form || !form.classList || !form.classList.contains("chat-cerca")) return;
    ev.preventDefault();
    const inp = form.querySelector("input");
    S.chatVista.testo = String(inp ? inp.value : "").trim().slice(0, 120);
    filtraChat();
  });

  // ─── «Pulisci le mie schede» (08/10, POST /api/schede) ───
  // Il server toglie le schede del proprietario da disco e dai suoi schermi (evento «pulisci»);
  // la pagina tiene solo le sue (cruscotto e conversazione)
  function pulisciLocale() {
    S.cronologia = S.cronologia.filter((c) => SOLO_PAGINA.has(c.tipo));
    S.svil = null;
    S.svilLasciata = null;
    Object.keys(FLUSSI).forEach((k) => { delete FLUSSI[k]; });
    emetti("schede", {});
    if (S.corrente && !SOLO_PAGINA.has(S.corrente.tipo)) { S.corrente = null; mostraInattiva(); }
    else disegnaCronologia();
    segnaTorna();
    if (S.intera && !CAROSELLO && !SOLO_PAGINA.has(S.intera)) chiudiInteroPC();
  }

  async function pulisciSchede() {
    if (!S.sessione || !S.personale) return { ok: false };
    let r;
    try { r = await postSessione("/api/schede", { azione: "pulisci" }); }
    catch (e) { r = { status: 0, dati: { errore: "Calliope non risponde: riprova." } }; }
    if (r.status === 200) pulisciLocale();
    return Object.assign({ ok: r.status === 200 }, r.dati || {});
  }

  document.addEventListener("click", async (ev) => {
    const b = ev.target.closest && ev.target.closest("button[data-pulisci]");
    if (!b || b.disabled) return;
    if (Date.now() >= S.pulisciArmato) {
      // Il primo tocco chiede il secondo: le schede non tornano
      S.pulisciArmato = Date.now() + 4000;
      b.textContent = "Tocca di nuovo per pulire";
      setTimeout(() => { if (Date.now() >= S.pulisciArmato) disegnaCronologia(); }, 4100);
      return;
    }
    S.pulisciArmato = 0;
    b.disabled = true;
    const r = await pulisciSchede();
    if (!r.ok) { b.disabled = false; b.textContent = r.errore || "Non ci sono riuscita"; }
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

  const STATI_MOTORE = { buona: "va bene", degradata: "degradata", "giù": "non risponde", mai: "mai controllata" };
  const ESITI_MOTORE = { aggiornata: "aggiornata", tenuta: "tenuta la vecchia", indietro: "tornata indietro",
    ultima: "già all'ultima", rinviato: "rinviato", errore: "errore", occupato: "occupato" };

  function disegnaMotore(s, m) {
    if (m.errore) { s.append(el("p", "cr-avviso", m.errore)); return; }
    const g = m.giudizio || {};
    const r1 = el("div", "cr-riga1");
    r1.append(el("span", "cr-nome", m.immagine ? "Immagine " + m.immagine : "Immagine non letta"));
    r1.append(el("span", "badge cr-stato", STATI_MOTORE[g.stato] || g.stato || "?"));
    s.append(r1);
    if (g.motivo) s.append(el("p", "cr-motivo", g.motivo));
    const u = m.ultimo;
    if (u) {
      s.append(el("p", "cr-tenue", "Ultimo controllo " + fa(u.quando) + ": " + u.risultati + " risultati, "
        + (u.motori || []).length + " motori che rispondono" + (u.ms_max ? ", la più lenta " + secondiDetti(u.ms_max / 1000) : "")));
      const ul = el("ul", "cr-lista");
      (u.prove || []).forEach((x) => {
        const giu = (x.giu || []).map((y) => y[0] + (y[1] ? " (" + y[1] + ")" : "")).join(", ");
        ul.append(el("li", "cr-tenue", x.categoria + " «" + x.domanda + "»: " + (x.errore ? "errore " + x.errore
          : x.risultati + " risultati") + (giu ? " · non rispondono " + giu : "")));
      });
      s.append(ul);
    } else s.append(el("p", "cr-tenue", "Nessun controllo ancora."));
    if (m.novita && m.novita.tag) {
      s.append(el("p", "cr-tenue", "Più recente nel registro: " + m.novita.tag + " (pubblicata " + fa(m.novita.pubblicata) + ")"
        + (m.novita.tag === m.immagine ? ", in uso" : "")));
    }
    s.append(el("p", "cr-tenue", m.modo === "automatico" && m.aggiornabile
      ? "Aggiornamento automatico: se è degradata, o con un'immagine nuova da almeno " + m.giorni + " giorni, a Calliope ferma."
      : "Aggiornamento " + (m.aggiornabile ? "manuale" : "non disponibile qui: " + m.perche) + "."));
    if (m.in_corso) s.append(el("p", "cr-avviso", (m.in_corso.azione === "aggiorna" ? "Aggiornamento" : "Controllo")
      + " in corso: " + m.in_corso.fase + "…"));
    const e = m.esito;
    if (e && e.frase) s.append(el("p", e.esito === "aggiornata" || e.esito === "ultima" ? "cr-motivo" : "cr-avviso",
      "Ultimo esito (" + (ESITI_MOTORE[e.esito] || e.esito) + ", " + fa(e.quando) + "): " + e.frase));
    // I pulsanti: la pagina li disegna solo nel cruscotto (solo chi amministra lo vede); il
    // server lo ricontrolla a ogni tocco
    const riga = el("div", "cr-azioni");
    const arm = S.motore.armato && ora() < S.motore.armato.fino ? S.motore.armato.azione : null;
    for (const [az, t, conf, si] of [["controlla", "Controlla", "Tocca ancora: controlla", m.controllabile],
      ["aggiorna", "Aggiorna", "Tocca ancora: aggiorna", m.aggiornabile]]) {
      if (!si) continue;
      const b = el("button", "piccolo-bottone" + (arm === az ? " armato" : ""), arm === az ? conf : t);
      b.type = "button";
      b.dataset.motore = az;
      b.disabled = !!m.in_corso;
      riga.append(b);
    }
    if (riga.children.length) s.append(riga);
    if (S.motore.msg) s.append(el("p", "cr-motivo", S.motore.msg));
    if (m.storia && m.storia.length) {
      s.append(el("h3", "cr-sotto", "Decisioni recenti"));
      const ul = el("ul", "cr-lista");
      m.storia.forEach((x) => ul.append(el("li", "cr-tenue", fa(x.quando) + " · " + (x.chi || "") + " · " + (x.frase || x.evento))));
      s.append(ul);
    }
    comando(s, "Da terminale: " + m.comando);
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
    corpo.append(el("p", "cr-nota", d.motore
      ? "Solo lettura, salvo la ricerca web: per il resto usa la voce o il terminale."
      : "Solo lettura: per cambiare qualcosa usa la voce o il terminale."));
    if (c.errore) corpo.append(el("p", "cr-avviso", "Non riesco a leggere lo stato: " + c.errore));
    if (!c.dati) return;
    // La valutazione (18/10, decisione 0032): si conserva tutto, ospiti compresi, fino alla data
    if (d.valutazione && d.valutazione.testo) {
      corpo.append(el("p", d.valutazione.attiva ? "cr-avviso" : "cr-tenue", d.valutazione.testo));
    }

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

    // Ricerca web (09/10): il controllo di SearXNG e i suoi due pulsanti
    if (d.motore) disegnaMotore(sezione(corpo, "Ricerca web (SearXNG)"), d.motore);

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

    // La stanza (13/10, conversazione di stanza, passo 1 in ombra): solo numeri, mai parole
    const sz = d.stanza;
    if (sz) {
      s = sezione(corpo, "Stanza (in ombra)");
      if (!nonLetto(s, sz)) {
        const sat = sz.satelliti || {};
        const nomi = Object.keys(sat);
        if (!nomi.length) s.append(el("p", "cr-tenue", "Nessun satellite ascolta la stanza adesso."));
        nomi.forEach((n) => {
          const x = sat[n] || {};
          s.append(el("p", "", n + (x.stanza ? " (" + x.stanza + ")" : "") + ": "
            + (x.pausa ? "in pausa" + (x.pausa.motivo === "ospiti" ? " per ospiti" : "") : "ascolta")
            + " · righe in memoria " + (x.righe || 0) + " · presenti " + (x.presenti || 0)));
        });
        const o = sz.oggi || {};
        Object.keys(o).forEach((n) => {
          const x = o[n] || {};
          s.append(el("p", "cr-tenue", "Oggi " + n + ": parlato " + x.ore_parlato + " h, coda p90 "
            + (x.ritardo_p90_s === null || x.ritardo_p90_s === undefined ? "—" : x.ritardo_p90_s + " s")
            + ", banda " + x.mb + " MB"));
        });
        if (sz.in_coda) s.append(el("p", "", "Segmenti in coda: " + sz.in_coda));
        comando(s, "Dettagli da terminale: " + sz.comando);
      }
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

  // ─── l'aspetto (27/10, calliope/schermi/aspetto.py) ───
  // I colori dell'accento vengono dal server: quello scelto dal proprietario sugli schermi
  // personali, il lilla di serie altrove (è anche nei CSS). Solo colori nella forma attesa: le
  // variabili non prendono altro
  const VARIABILI_ACCENTO = {
    accento: "--accento", chiaro: "--accento-chiaro", bordo: "--accento-bordo",
    selezione: "--accento-selezione", fondo: "--accento-fondo", su: "--su-accento",
  };
  function applicaAspetto(a) {
    if (!a || !a.colori) return;
    const st = document.documentElement.style;
    for (const [k, v] of Object.entries(VARIABILI_ACCENTO)) {
      const c = a.colori[k];
      if (typeof c === "string" && /^#[0-9a-f]{6}$/i.test(c)) st.setProperty(v, c);
    }
    const rgb = a.colori.tenue;
    if (typeof rgb === "string" && /^\d{1,3}, \d{1,3}, \d{1,3}$/.test(rgb)) st.setProperty("--accento-rgb", rgb);
    S.aspetto = a;
    emetti("aspetto", a);
  }
  // Io › Aspetto: l'accento scelto vale su tutti gli schermi personali della persona (il
  // server lo manda anche alle altre sue pagine aperte)
  async function scegliAccento(nome) {
    let r;
    try { r = await postSessione("/api/aspetto", { accento: String(nome || "") }); }
    catch (e) { return { ok: false, errore: "Calliope non risponde: riprova tra poco." }; }
    if (r.status === 200 && r.dati.aspetto) applicaAspetto(r.dati.aspetto);
    return { ok: r.status === 200, errore: r.dati.errore || MESSAGGI[r.status] || "" };
  }

  async function postSessione(url, dati) {
    const r = await fetch(url, {
      method: "POST", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-Calliope-Sessione": S.sessione || "" },
      body: JSON.stringify(dati),
    });
    let d = {};
    try { d = await r.json(); } catch (e) { /* vuota */ }
    // I secondi di Retry-After di un 429 (revisione della PR #269: la pagina di Le mie cose riprova)
    const ra = Number(r.headers && r.headers.get ? r.headers.get("Retry-After") : NaN);
    return { status: r.status, dati: d, riprova: Number.isFinite(ra) && ra > 0 ? ra : 0 };
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
      if (!S.scrittura.moduli) { statoModulo(f); return; }
      invia.disabled = true;
      esito.textContent = "Invio…";
      let r;
      try { r = await postSessione("/api/modulo", { modulo: c.modulo, valori }); }
      catch (e) { r = null; }
      invia.disabled = !S.scrittura.moduli;
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
        applicaScrittura({ moduli: false, testo_moduli: r.dati.errore });
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
  // Dal 28/10 (#301) la casella dello schermo personale è sempre accesa: la nota resta per i moduli
  // e per gli schermi di stanza
  function notaScrittura(dentro, prima, attiva, testo) {
    let n = dentro.querySelector(":scope > .nota-scrittura");
    if (!n) {
      n = el("p", "nota-scrittura");
      n.setAttribute("role", "status");
      if (prima) dentro.insertBefore(n, prima); else dentro.append(n);
    }
    n.textContent = attiva ? "" : (testo || "Di' «Calliope» per scrivermi.");
    n.hidden = !!attiva;
  }

  function statoModulo(f) {
    if (f.classList.contains("inviato")) return;
    const b = f.querySelector(".invia-modulo");
    const ok = !!S.scrittura.moduli;
    if (b) b.disabled = !ok;
    f.classList.toggle("spento", !ok);
    notaScrittura(f, f.querySelector(".piede-modulo"), ok, S.scrittura.testoModuli);
  }

  // Lo stato dal server (o una parte: un 403 dice solo quella che si è spenta)
  function leggiScrittura(st) {
    st = st || {};
    const prima = S.scrittura || {};
    S.scrittura = {
      attiva: "attiva" in st ? !!st.attiva : !!prima.attiva,
      moduli: "moduli" in st ? !!st.moduli : !!prima.moduli,
      testo: "testo" in st ? String(st.testo || "") : (prima.testo || ""),
      testoModuli: "testo_moduli" in st ? String(st.testo_moduli || "") : (prima.testoModuli || ""),
    };
  }

  function applicaScrittura(st) {
    leggiScrittura(st);
    document.querySelectorAll("form.modulo").forEach(statoModulo);
    document.querySelectorAll(".comandi-svil [data-svil-invia], .comandi-svil [data-svil-scrivi]")
      .forEach((b) => { b.disabled = !S.scrittura.attiva; });
    const f = $("scrivi");
    if (f) {
      const i = $("scrivi-testo");
      i.disabled = !S.scrittura.attiva;
      // La foto come la casella: «Foto» spento, e una foto pronta e non mandata si toglie
      const bf = $("scrivi-foto");
      if (bf) bf.disabled = !S.scrittura.attiva;
      if (!S.scrittura.attiva && (S.foto || S.file) && S.togliFoto) S.togliFoto();
      if (S.prontoScrivi) S.prontoScrivi();
      f.classList.toggle("spento", !S.scrittura.attiva);
      if (!S.foto && !S.file && S.segnaScrivi) S.segnaScrivi(segnaposto());
      notaScrittura(f, null, S.scrittura.attiva, S.scrittura.testo);
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
  async function postFile(file, testo, solo) {
    const r = await fetch("/api/allegato", {
      method: "POST", cache: "no-store", body: file,
      headers: { "Content-Type": "application/octet-stream", "X-Calliope-Sessione": S.sessione || "",
                 "X-Calliope-Nome": encodeURIComponent(file.name || "file"),
                 "X-Calliope-Testo": encodeURIComponent(testo || ""),
                 "X-Calliope-Fonte": INCORPORATA ? "telefono" : "schermo",
                 "X-Calliope-Solo-Scritto": solo ? "1" : "0" },
    });
    let d = {};
    try { d = await r.json(); } catch (e) { /* vuota */ }
    return { status: r.status, dati: d };
  }

  // La casella «scrivi invece di parlare»: sotto le schede, sugli schermi personali (e su
  // quelli di stanza se la configurazione lo vuole: lì chi scrive conta come ospite).
  // Dal 28/10 (#301) è una riga: Allega, il testo su più righe e Invia (sul telefono anche
  // «Torna alla voce», messo da telefono.js), sopra l'anteprima di ciò che si allega. Il testo a
  // 16 px almeno, perché iOS non ingrandisca la pagina; Invio manda, Maiusc+Invio va a capo; Invia
  // è spento con la casella vuota
  // Le icone dal <template id="icone"> della pagina (niente HTML scritto qui); senza, uno spazio vuoto
  function icona(cls, nome) {
    const t = $("icone");
    const s = t && t.content ? t.content.querySelector('[data-icona="' + nome + '"]') : null;
    const x = s ? s.cloneNode(true) : el("span");
    x.setAttribute("aria-hidden", "true");
    x.setAttribute("class", cls);
    return x;
  }
  window.calliopeIcona = icona;
  const SEGNO_BREVE = { "Scrivi a Calliope…": "Scrivi…", "Cosa vuoi sapere di questa foto?": "Cosa vuoi sapere?",
    "Cosa vuoi sapere di questo file?": "Cosa vuoi sapere?" };
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
      f.setAttribute("aria-label", "Scrivi a Calliope");
      const i = el("textarea");
      i.id = "scrivi-testo";
      i.rows = 1;
      i.maxLength = 500;
      i.autocomplete = "off";
      i.setAttribute("enterkeyhint", "send");
      i.setAttribute("aria-label", "Messaggio per Calliope");
      const b = el("button", "scrivi-invia");
      b.type = "submit";
      b.id = "scrivi-invia";
      b.setAttribute("aria-label", "Invia");
      b.append(icona("invia-icona", "invia"), el("span", "invia-testo", "Invia"));
      const esito = el("span", "esito-scrivi");
      esito.setAttribute("role", "status");
      // «Allega» (05/10): input nascosto senza «accept» (su iOS e Android offre fotocamera,
      // libreria e file; niente getUserMedia), pulsante e anteprima con «Togli». Una foto si
      // riduce qui (canvas); un altro file mostra nome, tipo e dimensione e parte intero
      const file = el("input");
      file.type = "file";
      file.id = "scrivi-foto-file";
      file.hidden = true;
      const bf = el("button", "foto-apri");
      bf.type = "button";
      bf.id = "scrivi-foto";
      bf.setAttribute("aria-label", "Allega una foto o un file per Calliope");
      bf.append(icona("allega-icona", "graffetta"), el("span", "allega-testo", "Allega"));
      const ante = el("div", "foto-anteprima");
      ante.id = "scrivi-anteprima";
      ante.hidden = true;
      const mini = el("img");
      mini.alt = "La foto da mandare";
      const info = el("span", "allegato-info");
      const togli = el("button", "piccolo-bottone togli-allegato");
      togli.type = "button";
      togli.setAttribute("aria-label", "Togli la foto o il file");
      togli.append(icona("togli-icona", "togli"), el("span", "togli-testo", "Togli"));
      ante.append(mini, info, togli);
      // Una riga sola che cresce fino a cinque righe mentre si scrive (vuota, una riga: Chrome
      // conta nell'altezza anche il segnaposto, che non deve allungarla)
      const cresci = () => {
        i.style.height = "";
        if (!i.value) { segna(); return; }
        const alto = Math.min(i.scrollHeight, parseFloat(getComputedStyle(i).lineHeight || "20") * 5 + 24);
        if (i.scrollHeight > i.clientHeight + 1) i.style.height = Math.ceil(alto + 2) + "px";
      };
      // Il segnaposto: quello breve se il lungo non ci sta su una riga (la casella stretta del
      // telefono a 320 px). Si misura la larghezza del testo col font della casella (revisione
      // della PR #304: l'altezza col segnaposto la conta Chrome, WebKit forse no)
      const misura = document.createElement("canvas").getContext("2d");
      const largo = (testo) => {
        const cs = getComputedStyle(i);
        if (!misura) return 0;
        misura.font = cs.font || (cs.fontWeight + " " + cs.fontSize + " " + cs.fontFamily);
        return misura.measureText(testo).width;
      };
      const spazioTesto = () => {
        const cs = getComputedStyle(i);
        return i.clientWidth - parseFloat(cs.paddingLeft || "0") - parseFloat(cs.paddingRight || "0");
      };
      const segna = (testo) => {
        if (testo !== undefined) i.dataset.segno = testo;
        const lungo = i.dataset.segno || "";
        let scelto = lungo;
        const w = i.clientWidth ? spazioTesto() : 0;
        if (w > 0) {
          for (const corto of [SEGNO_BREVE[lungo], "Scrivi…"]) {
            if (!corto || largo(scelto) <= w) break;
            scelto = corto;
          }
        }
        if (i.placeholder !== scelto) i.placeholder = scelto;
      };
      S.segnaScrivi = segna;
      if (typeof ResizeObserver === "function") new ResizeObserver(() => segna()).observe(i);
      const dire = (testo, errore) => { esito.textContent = testo; esito.classList.toggle("errore", !!errore); };
      const pronto = () => {
        b.disabled = !S.scrittura.attiva || (!i.value.trim() && !S.foto && !S.file);
        f.classList.toggle("con-allegato", !ante.hidden);
      };
      S.prontoScrivi = pronto;
      const via = () => {
        S.foto = null; S.file = null; ante.hidden = true;
        mini.hidden = false; mini.removeAttribute("src");
        info.textContent = "";
        pronto();
      };
      S.togliFoto = via;
      const metti = async (fl) => {
        if (!fl || !S.fotoAmmessa) return;
        // Come la casella: dallo schermo personale sempre (28/10, #301)
        if (!S.scrittura.attiva) { dire(S.scrittura.testo || "Di' «" + S.parola + "» per scrivermi.", true); return; }
        via();
        if (fl.size > FILE_MAX_BYTE) { dire("Il file è troppo grande (al massimo 25 MB).", true); return; }
        if (eFoto(fl)) {
          dire("Preparo la foto…");
          try {
            S.foto = await leggiFoto(fl);
            mini.src = S.foto.url;
            info.textContent = "Foto allegata · " + dimensione(fl.size);
            togli.setAttribute("aria-label", "Togli la foto");
            ante.hidden = false;
            dire("Foto allegata: scrivi cosa vuoi sapere (o dimmelo a voce) e premi Invia.");
            segna("Cosa vuoi sapere di questa foto?");
            pronto();
            i.focus();
          } catch (e) {
            via();
            dire(e.message, true);
          }
          return;
        }
        S.file = fl;
        mini.hidden = true;
        info.textContent = (fl.name || "file") + " · " + dimensione(fl.size);
        togli.setAttribute("aria-label", "Togli il file");
        ante.hidden = false;
        dire("File allegato: scrivi cosa vuoi sapere (o dimmelo a voce) e premi Invia.");
        segna("Cosa vuoi sapere di questo file?");
        pronto();
        i.focus();
      };
      bf.addEventListener("click", () => file.click());
      file.addEventListener("change", () => { const fl = file.files && file.files[0]; file.value = ""; metti(fl); });
      togli.addEventListener("click", () => { via(); dire(""); segna(segnaposto()); i.focus(); });
      i.addEventListener("input", () => { cresci(); pronto(); });
      // Invio manda, Maiusc+Invio va a capo (non mentre si compone una parola con l'IME)
      i.addEventListener("keydown", (ev) => {
        if (ev.key !== "Enter" || ev.shiftKey || ev.isComposing) return;
        ev.preventDefault();
        if (typeof f.requestSubmit === "function") f.requestSubmit(); else f.dispatchEvent(new Event("submit", { cancelable: true }));
      });
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
      // L'ordine è quello in cui si legge e si tocca: l'anteprima sopra, poi Allega, il testo,
      // Invia (sul telefono telefono.js mette «Torna alla voce» per primo); l'esito sotto
      const nota = el("span", "nota-invio", "Invio per mandare, Maiusc+Invio per andare a capo · trascina qui un file");
      nota.setAttribute("aria-hidden", "true");
      f.append(ante, bf, i, b, nota, esito, file);
      f.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const testo = i.value.trim();
        const foto = S.foto, allegato = S.file;
        if ((!testo && !foto && !allegato) || !S.scrittura.attiva || f.classList.contains("in-invio")) return;
        f.classList.add("in-invio");
        b.disabled = true;
        if (allegato) dire("Mando il file…");
        let r;
        try {
          // Dalla modalità scrittura del telefono la risposta è solo scritta (S.soloScritto)
          const solo = !!S.soloScritto;
          r = foto ? await postSessione("/api/immagine", { immagine: foto.url, testo, solo_scritto: solo,
                                                           fonte: INCORPORATA ? "telefono" : "schermo" })
            : allegato ? await postFile(allegato, testo, solo)
              : await postSessione("/api/scrivi", { testo, solo_scritto: solo });
        } catch (e) { r = null; }
        f.classList.remove("in-invio");
        if (r && r.dati && r.dati.codice === "senza_conversazione") {
          applicaScrittura({ attiva: false, testo: r.dati.errore });
          return;
        }
        if (r && r.status === 200) {
          i.value = "";
          if (foto || allegato) via();
          i.dataset.segno = segnaposto();
          cresci();
          dire((foto || allegato) && !testo
            ? (foto ? "Foto inviata" : "File inviato") + ": dimmi o scrivi cosa vuoi sapere."
            : "Inviato: ti rispondo qui.");
          emetti("scritto", { testo, foto: !!foto, file: !!allegato });
          setTimeout(() => { if (esito.textContent.startsWith("Inviato")) esito.textContent = ""; }, 5000);
        } else {
          dire(r ? (r.dati.errore || MESSAGGI[r.status] || "Non è andato.") : "Calliope non risponde.", true);
        }
        pronto();
      });
      // Il posto della pagina (la Conversazione del telefono, la colonna della conversazione del
      // PC personale), se si vede; altrimenti in fondo, sotto la cronologia
      const posto = $("scrivi-posto");
      const dopo = $("cronologia");
      if (posto && (INCORPORATA || !posto.closest("[hidden]"))) posto.append(f);
      else if (dopo && dopo.parentNode) dopo.after(f); else document.body.append(f);
    }
    $("scrivi-foto").hidden = !personale;
    f.hidden = false;
    applicaScrittura(S.scrittura);
  }
  function segnaposto() {
    return !S.scrittura.attiva ? "Di' «" + S.parola + "» per scrivermi"
      : S.personale ? "Scrivi a Calliope…" : "Scrivi a Calliope (da qui vale come un ospite)…";
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
    // I token (08/10, decisione di Dario): la barra è quella del giro sul tetto di un giro, che
    // non cresce; il totale del lavoro a parte. Sono quelli generati, ragionamento compreso
    const giro2 = (av.giro || 1) > 1;
    const tg = giro2 && av.token_giro != null ? av.token_giro : (av.token || 0);
    barra(giro2 ? "Token del giro" : "Token", tg, av.max_token,
      tg.toLocaleString("it-IT") + " di " + (av.max_token || 0).toLocaleString("it-IT") + " al massimo");
    // Passate e minuti sono cumulativi (al giro 2 di uno sviluppo il doppio)
    if (giro2) g.append(el("p", "tetti-nota", "Giro " + av.giro + ": passate e minuti sono quelli di "
      + av.giro + " giri; " + (av.token || 0).toLocaleString("it-IT") + " token in tutto il lavoro."));
    return g;
  }

  const mig = (n) => (Number(n) || 0).toLocaleString("it-IT");
  // Il lavoro di uno sviluppo (08/10): fase, correzione, e i numeri dello sviluppo intero
  // (somma dei lavori e delle correzioni)
  function righeSviluppo(v) {
    const b = el("section", "svil-lavoro");
    if (v.id) {
      b.append(el("p", "svil-fase", "Sviluppo " + v.id + " · " + (v.fase_nome || v.fase || "")
        + (v.n_fase ? " (" + v.n_fase + " di " + v.fasi + ")" : "")));
    }
    if (v.correzione) b.append(el("p", "svil-correzione", "Correzione " + v.correzione + ", riparte dalla versione provata"));
    const t = v.totali || {};
    if (t.lavori) {
      b.append(el("p", "svil-totali", "Sviluppo intero: " + t.lavori + (t.lavori === 1 ? " lavoro" : " lavori")
        + (t.correzioni ? " (" + t.correzioni + (t.correzioni === 1 ? " correzione" : " correzioni") + ")" : "")
        + ", " + mig(t.token) + " token, " + mig(t.passate) + " passate, "
        + Math.round((t.secondi || 0) / 60) + " min di lavoro"));
    }
    return b;
  }

  function dueColonne(sx, dx) {
    const g = el("div", "due-colonne");
    g.append(sx, dx);
    return g;
  }

  // La colonna del «codice che gira»: il flusso accumulato del lavoro `k`, con «Scarica il
  // registro» quando c'è
  function colonnaFlusso(c, k) {
    k = k || chiaveDi(c);
    const col = el("section", "col-flusso");
    const testa = el("div", "testa-flusso");
    testa.append(el("div", "nome-file", "Il codice che gira"));
    if (c && c.registro && c.registro.chiave) {
      const box = el("div", "scarica");
      const b = el("button", "piccolo-bottone tasto-scarica", "Scarica il registro");
      b.type = "button";
      b.dataset.scarica = "md";
      b.dataset.chiaveScheda = String(c.registro.chiave);
      box.append(b, el("span", "esito-scarica", ""));
      testa.append(box);
    }
    col.append(testa, chatFlusso(k, c && c.stato === "in_corso"));
    return col;
  }

  function chatFlusso(k, corre) {
    const st = FLUSSI[k];
    const box = el("div", "flusso-chat");
    box.dataset.segui = "1";
    box.setAttribute("role", "log");
    box.setAttribute("aria-label", "Il lavoro dell'agente, in diretta");
    box.tabIndex = 0;
    if (!st || !st.sezioni.length) {
      box.append(el("p", "fl-vuoto", corre ? "Aspetto che l'agente scriva…" : "Qui compare il lavoro dell'agente mentre lavora."));
      return box;
    }
    if (st.taglio) box.append(el("p", "fl-taglio", "L'inizio non è qui: è nel registro completo («Scarica il registro»)."));
    st.sezioni.forEach((z) => box.append(sezioneFlusso(z)));
    const giu = el("button", "fl-fondo", "In fondo");
    giu.type = "button";
    giu.dataset.flussoFondo = "1";
    box.append(giu);
    return box;
  }

  function sezioneFlusso(z) {
    if (z.t === "passata") return el("div", "fl-passata", z.x);
    if (z.t === "strumento" || z.t === "esito") {
      const d = el("div", "fl-" + z.t);
      d.append(el("span", "fl-freccia", z.t === "strumento" ? "→" : "←"), el("span", "", z.x));
      return d;
    }
    const codice = z.t === "codice";
    const d = el("div", "fl-sez fl-" + (codice ? "codice" : z.t === "pensiero" ? "pensiero" : "testo"));
    d.append(el("div", "fl-chi", codice ? "Scrive il codice" + (z.f ? " · " + z.f : "")
      : z.t === "pensiero" ? "Ragiona" : "Scrive"));
    d.append(el(codice ? "pre" : "div", codice ? "fl-x codice-flusso" : "fl-x", z.x));
    return d;
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

  // Il riepilogo del lavoro in corso: stato (e giro), passo, test, tetti, sviluppo, file
  // scritti, ultimi passi. Il flusso dell'agente (il «codice che gira») solo a schermo intero,
  // nella colonna di destra (08/10); l'anteprima del codice solo lì
  function disegnaAvanzamento(c, av, corpo, intera) {
    const meta = el("p", "sotto", (STATI_LAVORO[c.stato] || c.stato || "")
      + ((av.giro || 1) > 1 ? " · giro " + av.giro : ""));
    if (av.pausa) meta.append(el("span", "badge pausa", "in pausa: sto rispondendo a voce"));
    corpo.append(meta);
    if (av.passo) corpo.append(el("p", "passo-lavoro" + (av.pausa ? " fermo" : ""), "Adesso: " + av.passo));
    if (c.test) {
      const t = c.test, ko = (t.falliti || 0) + (t.errori || 0), n = Math.max(t.eseguiti || 0, ko);
      corpo.append(el("p", "test-lavoro" + (ko ? " ko" : " ok"),
        "Test: " + (n ? (n - ko) + " su " + n + " passano" : "nessuno trovato")));
    }
    if (c.stato === "in_corso" || (c.stato !== "in_coda" && av.trascorso_s)) corpo.append(tettiLavoro(av, c.stato === "in_corso" && !av.pausa));
    if (av.sviluppo) corpo.append(righeSviluppo(av.sviluppo));
    if (av.file && av.file.length) {
      const b = el("section", "file-lavoro");
      b.append(el("div", "nome-file", "File scritti finora"));
      const ul = el("ul", "elenco-file");
      av.file.forEach((f) => ul.append(el("li", "", f.nome + (f.righe ? " · " + f.righe + (f.righe === 1 ? " riga" : " righe") : ""))));
      b.append(ul);
      if (av.anteprima && intera) {
        b.append(el("div", "nome-file", "Inizio di " + av.anteprima.nome));
        b.append(el("pre", "codice anteprima", av.anteprima.testo));
      }
      corpo.append(b);
    }
    if (av.passi && av.passi.length) corpo.append(passiLavoro(av.passi));
  }

  // ─── la vista dello sviluppo (08/10, calliope/sviluppo.py: Sviluppi.dati_vista) ───
  // Sugli schermi personali di chi sviluppa, finché lo sviluppo è aperto: la barra delle fasi
  // con nome, versione e giro; al centro il riepilogo del lavoro (a sinistra) e il flusso
  // dell'agente (a destra); sotto l'analisi, il collaudo, le domande a chi l'ha scritto, la
  // revisione; in fondo i comandi a tocco, solo innocui, che mandano una frase come se fosse
  // scritta. Approvare e attivare restano a voce, con la frase di conferma: nessun pulsante.
  // Sulla pagina degli schermi prende l'area delle schede; il telefono la apre a schermo intero
  function svilAperto(c) { return !!(c && c.tipo === "sviluppo" && c.sviluppo && c.sviluppo.stato === "aperta"); }
  function vistaAttiva() { return !CAROSELLO && !!S.svil && S.svilLasciata !== chiaveDi(S.svil); }
  function schedaDi(k) {
    if (!k) return null;
    for (let i = S.cronologia.length - 1; i >= 0; i--) if (chiaveDi(S.cronologia[i]) === k) return S.cronologia[i];
    return null;
  }
  const fmtGiornoOra = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

  function barraFasi(v) {
    const ol = el("ol", "fasi-svil");
    ol.setAttribute("aria-label", "Fasi dello sviluppo");
    (v.fasi || []).forEach((f, i) => {
      const li = el("li", "fase " + (f.stato === "adesso" ? "adesso" : f.stato === "fatta" ? "fatta" : "manca"));
      li.append(el("span", "fase-n", String(i + 1)), el("span", "fase-nome", f.nome));
      if (f.stato === "adesso") li.setAttribute("aria-current", "step");
      li.append(el("span", "fase-stato", f.stato === "adesso" ? "adesso" : f.stato === "fatta" ? "fatta" : ""));
      ol.append(li);
    });
    return ol;
  }

  function righeTitoloSvil(v) {
    const parti = [(v.titolo ? v.titolo + " — " : "") + (v.cosa || "sviluppo")];
    if (v.nome) parti.push(v.nome);
    if (v.versione) parti.push("versione " + v.versione);
    if (v.giro > 1) parti.push("giro " + v.giro);
    if (v.correzioni) parti.push(v.correzioni + (v.correzioni === 1 ? " correzione" : " correzioni"));
    parti.push(v.id || "");
    return parti.filter(Boolean).join(" · ");
  }

  DISEGNA.sviluppo = function (c, corpo, s, opz) {
    const v = c.sviluppo || {};
    s.classList.add("scheda-sviluppo");
    const intera = !!(opz && opz.intera);
    corpo.append(barraFasi(v));
    corpo.append(el("p", "svil-titolo", righeTitoloSvil(v)));
    if (v.stato !== "aperta") {
      corpo.append(el("p", "svil-chiuso", (v.stato === "sospesa" ? "Sviluppo sospeso" : "Sviluppo chiuso")
        + (v.motivo ? ": " + v.motivo : "") + "."));
    }
    const lav = schedaDi(v.lavoro);
    const av = lav && lav.avanzamento;
    if (!intera) {
      if (av && ["in_coda", "in_corso"].includes(lav.stato)) corpo.append(el("p", "passo-lavoro", "Adesso: " + (av.passo || STATI_LAVORO[lav.stato])));
      else if (v.tappa) corpo.append(el("p", "passo-lavoro", "Fermo a una tappa: aspetta che tu dica se continuare."));
      const ult = (v.collaudi || []).slice(-1)[0];
      if (ult) corpo.append(el("p", "sotto", "Ultima prova: «" + ult.dati + "», " + (ult.ok ? "riuscita" : "non riuscita")));
      // Rispetto alla richiesta (11/10, revisione onesta): quante cose mancano
      const mancano = (v.requisiti || []).filter((x) => x.si_puo && (x.stato === "manca" || x.stato === "parziale")).length;
      if (mancano) corpo.append(el("p", "sotto", "Rispetto alla richiesta: " + (mancano === 1 ? "manca una cosa" : "mancano " + mancano + " cose") + "."));
      if (!CAROSELLO && v.stato === "aperta") {
        const b = el("button", "piccolo-bottone tasto-svil", "Apri la vista dello sviluppo");
        b.type = "button";
        b.dataset.svilVista = "1";
        corpo.append(b);
      }
      return;
    }
    // Al centro: il riepilogo del lavoro e il flusso dell'agente
    const sx = el("div", "col-riepilogo");
    if (av) {
      // Il riepilogo del lavoro, con la fase e i numeri dello sviluppo di adesso (quelli nella
      // scheda del lavoro sono dell'ultimo invio)
      sx.append(el("div", "nome-file", "Il lavoro dell'agente"));
      disegnaAvanzamento(lav, Object.assign({}, av, { sviluppo: null }), sx, false);
    } else {
      sx.append(el("p", "sotto", v.tappa ? "Il lavoro è fermo a una tappa: aspetta che tu dica se continuare."
        : v.lavoro_stato === "in_corso" || v.lavoro_stato === "in_coda" ? "L'agente sta lavorando."
          : "L'agente non sta lavorando adesso."));
      if (v.nota && v.fase === "sviluppo") sx.append(el("p", "test-lavoro ko", "L'ultimo lavoro non è andato: " + v.nota + "."));
    }
    // I numeri dello sviluppo: con il lavoro in corso quelli del suo ultimo invio (il lavoro si
    // aggiorna due volte al secondo, la scheda dello sviluppo solo a ogni fase)
    const vivo = av && av.sviluppo && av.sviluppo.totali && ["in_coda", "in_corso"].includes(lav.stato);
    const t = (vivo ? av.sviluppo.totali : v.totali) || {};
    if (t.lavori || (av && av.sviluppo && av.sviluppo.correzione)) {
      sx.append(righeSviluppo({ correzione: av && av.sviluppo ? av.sviluppo.correzione : 0, totali: t }));
    }
    // Le sezioni: quella della fase di adesso per prima
    const sez = {
      analisi: () => {
        const b = el("section", "svil-sez");
        b.append(el("h2", "", "Analisi: cosa si è capito"));
        if (v.richiesta) b.append(el("p", "svil-richiesta", "Richiesta: «" + v.richiesta + "»"));
        // La specifica rigenerata dai requisiti va a capo per requisito (12/10, la specifica viva)
        (v.specifica || "La specifica non è ancora decisa.").split("\n").forEach((riga) => {
          if (riga.trim()) b.append(el("p", "", riga));
        });
        // Lo storico delle modifiche, a parte dalla specifica (12/10)
        const mod = (v.modifiche || []).slice().reverse();
        if (mod.length) {
          b.append(el("h3", "", "Modifiche chieste"));
          const ol = el("ol", "prove-svil");
          mod.forEach((m) => {
            const li = el("li", "prova");
            const t = el("div", "prova-testa");
            t.append(el("span", "prova-dati", "«" + (m.detto || "") + "»"),
              el("span", "prova-quando", m.ora ? fmtGiornoOra.format(new Date(m.ora * 1000)) : ""));
            li.append(t);
            (m.cambi || []).forEach((c) => li.append(el("p", "prova-esito", c)));
            ol.append(li);
          });
          b.append(ol);
        }
        return b;
      },
      collaudo: () => {
        const b = el("section", "svil-sez");
        b.append(el("h2", "", "Collaudo: le prove"));
        const prove = (v.collaudi || []).slice().reverse();
        if (!prove.length) { b.append(el("p", "sotto", "Nessuna prova ancora.")); return b; }
        const ol = el("ol", "prove-svil");
        prove.forEach((p) => {
          const li = el("li", "prova " + (p.ok ? "ok" : "ko"));
          const r = el("div", "prova-testa");
          r.append(el("span", "badge " + (p.ok ? "ok" : "ko"), p.ok ? "riuscita" : "non riuscita"),
            el("span", "prova-dati", "«" + (p.dati || "senza dati") + "»"),
            el("span", "prova-quando", (p.versione ? "versione " + p.versione + " · " : "") + (p.ora ? fmtGiornoOra.format(new Date(p.ora * 1000)) : "")));
          li.append(r);
          if (p.esito) li.append(el("p", "prova-esito", p.esito));
          if (p.giudizio) li.append(el("p", "prova-giudizio", "Secondo te: " + p.giudizio));
          ol.append(li);
        });
        b.append(ol);
        return b;
      },
      domande: () => {
        const q = (v.chiesti || []).slice().reverse();
        if (!q.length) return null;
        const b = el("section", "svil-sez");
        b.append(el("h2", "", "Domande a chi l'ha scritto"));
        q.forEach((x) => {
          const d = el("div", "domanda-svil");
          d.append(el("p", "domanda-testo", "«" + x.domanda + "»"));
          if (x.voce) d.append(el("p", "", x.voce));
          if (x.dettagli && x.dettagli !== x.voce) {
            const det = el("details");
            det.append(el("summary", "", "I dettagli"), el("p", "domanda-dettagli", x.dettagli));
            d.append(det);
          }
          b.append(d);
        });
        return b;
      },
      // Requisito per requisito rispetto alla richiesta (11/10, revisione onesta): il confronto
      // fatto da Calliope tra la specifica approvata e il codice consegnato
      requisiti: () => {
        const r = v.requisiti || [];
        if (!r.length) return null;
        const b = el("section", "svil-sez");
        b.append(el("h2", "", "Rispetto alla richiesta"));
        if (v.tappa_n) b.append(el("p", "sotto", "A tappe: adesso la tappa " + v.tappa_n + "."));
        if (v.confronto !== "fatto") b.append(el("p", "sotto", "Il confronto con il codice non c'è ancora: i requisiti sono questi."));
        const ol = el("ol", "prove-svil");
        r.forEach((x) => {
          const dopo = !!(v.tappa_n && x.tappa > v.tappa_n);
          const stato = !x.si_puo ? "non si può" : x.stato === "fatto" ? "fatto" : x.stato === "parziale" ? "in parte"
            : x.stato === "manca" ? "manca" : dopo ? "tappa dopo" : "da controllare";
          const ok = x.si_puo && x.stato === "fatto";
          const li = el("li", "prova " + (ok ? "ok" : "ko"));
          const t = el("div", "prova-testa");
          t.append(el("span", "badge " + (ok ? "ok" : "ko"), stato), el("span", "prova-dati", x.testo || ""));
          if (dopo && x.stato) t.append(el("span", "prova-quando", "tappa dopo"));
          li.append(t);
          const nota = x.nota || (!x.si_puo ? x.limite : "");
          if (nota) li.append(el("p", "prova-esito", nota));
          if (x.dettaglio) li.append(el("p", "sotto", x.dettaglio));
          ol.append(li);
        });
        b.append(ol);
        return b;
      },
      revisione: () => {
        if (!v.revisione) return null;
        const b = el("section", "svil-sez");
        b.append(el("h2", "", "Revisione: permessi e analisi del codice"));
        b.append(leggiMarkdown(v.revisione).nodo);
        return b;
      },
    };
    const prima = { analisi: "analisi", sviluppo: "analisi", collaudo: "collaudo", revisione: "revisione", attivazione: "revisione" }[v.fase] || "analisi";
    const ordine = [prima, "requisiti"].concat(["collaudo", "domande", "revisione", "analisi"].filter((x) => x !== prima));
    const g = el("div", "svil-sezioni");
    ordine.forEach((k) => { const n = sez[k](); if (n) g.append(n); });
    // Al centro: a sinistra il riepilogo e sotto le sezioni (sul computer scorrono insieme), a
    // destra il flusso. In una colonna sola (telefono, finestre strette) il flusso viene dopo
    // il riepilogo e prima delle sezioni (col-sinistra con display: contents)
    const sinistra = el("div", "col-sinistra");
    sinistra.append(sx, g);
    const centro = el("div", "due-colonne vista-centro");
    centro.append(sinistra, colonnaFlusso(lav || { stato: v.lavoro_stato }, v.lavoro || ("svil:" + v.id)));
    corpo.append(centro);
    corpo.append(comandiSviluppo(v));
  };

  // I comandi a tocco: solo azioni innocue, come frasi scritte (passano dal modello e dalla
  // politica come lo scritto: niente che lo scritto non possa già fare). Testi fissi della
  // pagina, mai testo della scheda
  function comandiSviluppo(v) {
    const bar = el("div", "comandi-svil");
    bar.setAttribute("role", "group");
    bar.setAttribute("aria-label", "Comandi dello sviluppo");
    const attivo = !!S.scrittura.attiva;
    const tasto = (testo, k, val) => {
      const b = el("button", "tasto-svil", testo);
      b.type = "button";
      b.dataset[k] = val;
      if (k !== "svilEsci" && !attivo) b.disabled = true;
      bar.append(b);
    };
    if (v.stato === "aperta") {
      tasto("A che punto siamo?", "svilInvia", "A che punto è lo sviluppo?");
      // «Prova con…» non c'è più (28/10 sera, seguito della #301): provare esegue codice (E3) e
      // dallo schermo si conferma solo a voce
      if (v.fase !== "analisi") tasto("Chiedi all'agente…", "svilScrivi", "Perché ");
    } else if (v.stato === "sospesa" && /^S\d+$/.test(v.id || "")) {
      tasto("Riprendi lo sviluppo", "svilInvia", "Riprendiamo lo sviluppo " + v.id);
    }
    if (!CAROSELLO) tasto("Vista normale", "svilEsci", "1");
    const nota = el("p", "nota-svil", (attivo ? "" : "I comandi si accendono in una conversazione: di' «" + S.parola + "». ")
      + "Provare, approvare e attivare si fa a voce.");
    nota.setAttribute("role", "status");
    const box = el("div", "piede-svil");
    box.append(bar, nota);
    return box;
  }

  // La vista sulla pagina degli schermi: nell'area delle schede, al posto della scheda
  function disegnaVista() {
    if (!S.svil) return;
    const m = $("principale");
    if (!m) return;
    S.corrente = S.svil;
    S.vista = "sviluppo";
    const nuova = costruisci(S.svil, { intera: true });
    nuova.classList.add("vista-svil");
    const vecchia = m.querySelector(":scope > article.scheda");
    if (vecchia && vecchia.dataset.chiave === nuova.dataset.chiave && vecchia.classList.contains("vista-svil")) {
      const seg = misuraSegui(vecchia);
      const sc = vecchia.querySelector(":scope > .corpo");
      const top = sc ? sc.scrollTop : 0;
      allinea(vecchia, nuova);
      ripristinaSegui(vecchia, seg);
      if (sc) sc.scrollTop = top;
    } else {
      m.replaceChildren(nuova);
      ripristinaSegui(nuova, null);
    }
    document.body.classList.add("in-vista-sviluppo");
    disegnaCronologia();
    aggiornaLavori();
    segnaTorna();
  }

  // Una scheda arrivata mentre c'è uno sviluppo (pagina degli schermi): true se l'ha gestita
  // la vista. Lo sviluppo che si apre fa entrare nella vista, quello chiuso o sospeso fa
  // uscire; con la vista attiva le altre schede vanno nella cronologia (un modulo, un gioco si
  // mostrano: vogliono una risposta, e «Torna allo sviluppo» riporta qui)
  function vistaSviluppo(c) {
    if (c.tipo === "sviluppo") {
      if (svilAperto(c)) {
        if (!S.svil || chiaveDi(S.svil) !== chiaveDi(c)) S.svilLasciata = null;
        S.svil = c;
        aggiungiCronologia(c);
        if (vistaAttiva()) disegnaVista(); else segnaTorna();
        return true;
      }
      if (S.svil && chiaveDi(S.svil) === chiaveDi(c)) {
        S.svil = null;
        S.svilLasciata = null;
        aggiungiCronologia(c);
        mostra(c);
        return true;
      }
      return false;
    }
    if (!vistaAttiva()) return false;
    if (c.tipo === "vuota") return true;
    if (["modulo", "gioco"].includes(c.tipo) && c.sposta !== false) return false;
    aggiungiCronologia(c);
    if (chiaveDi(c) === (S.svil.sviluppo || {}).lavoro) disegnaVista();
    return true;
  }

  // «Torna allo sviluppo» nella testa, quando lo sviluppo è aperto e si guarda altro
  function segnaTorna() {
    if (CAROSELLO || INCORPORATA) return;
    const testa = $("testa");
    if (!testa) return;
    let b = $("torna-svil");
    if (!b) {
      b = el("button", "piccolo-bottone torna-svil", "Torna allo sviluppo");
      b.type = "button";
      b.id = "torna-svil";
      b.dataset.svilVista = "1";
      testa.insertBefore(b, $("orologio-piccolo"));
    }
    b.hidden = !(S.svil && !vistaAttiva());
  }

  // ─── una scheda a schermo intero sulla pagina degli schermi (08/10) ───
  // Il lavoro (due colonne, con il flusso dell'agente), il documento, l'uscita di un
  // programma: uno strato sopra la pagina, alto quanto lo schermo, che si aggiorna al suo
  // posto con la stessa chiave. Si chiude con «Chiudi» o Esc
  function stratoInteroPC() {
    let st = $("strato-intero");
    if (st) return st;
    st = el("section", "strato-intero");
    st.id = "strato-intero";
    st.setAttribute("role", "dialog");
    st.setAttribute("aria-modal", "true");
    st.setAttribute("aria-labelledby", "intero-titolo");
    st.hidden = true;
    const testa = el("div", "intero-testa");
    const h = el("h2", "intero-titolo", "");
    h.id = "intero-titolo";
    const ch = el("button", "tasto-chiudi-intero", "Chiudi");
    ch.type = "button";
    ch.id = "intero-chiudi";
    ch.addEventListener("click", chiudiInteroPC);
    testa.append(h, ch);
    const posto = el("div", "intero-posto");
    posto.id = "intero-posto";
    st.append(testa, posto);
    document.body.append(st);
    return st;
  }
  function disegnaInteroPC() {
    if (!S.intera) return;
    // La conversazione del PC personale a sezioni sta nella sua colonna, non nella cronologia
    // (27/10, seconda revisione della PR #255)
    const c = schedaDi(S.intera) || (S.corrente && chiaveDi(S.corrente) === S.intera ? S.corrente : null)
      || (S.intera === CHAT && S.chatOk ? schedaChat() : null) || S.schedeChat[S.intera] || null;
    if (!c) return;                       // uscita dalla cronologia: resta l'ultimo contenuto
    const st = stratoInteroPC();
    $("intero-titolo").textContent = c.titolo || NOMI_TIPO[c.tipo] || "Scheda";
    const posto = $("intero-posto");
    const nuova = costruisci(c, { intera: true });
    const vecchia = posto.firstElementChild;
    if (vecchia && vecchia.dataset.chiave === nuova.dataset.chiave && vecchia.className === nuova.className) {
      const seg = misuraSegui(vecchia);
      allinea(vecchia, nuova);
      ripristinaSegui(vecchia, seg);
    } else {
      posto.replaceChildren(nuova);
      ripristinaSegui(nuova, null);
    }
    st.hidden = false;
    aggiornaLavori();
  }
  function apriInteroPC(k) {
    const prima = S.intera;
    S.intera = k;
    disegnaInteroPC();
    if (!prima) { const ch = $("intero-chiudi"); if (ch) ch.focus({ preventScroll: true }); }
  }
  function chiudiInteroPC() {
    // La scheda piccola aperta dalla conversazione a schermo intero: si torna lì (28/10, #242)
    const torna = S.intera && S.schedeChat[S.intera] ? S.interaTorna : null;
    S.interaTorna = null;
    if (torna && S.chatOk) { S.intera = torna; disegnaInteroPC(); return; }
    S.intera = null;
    const st = $("strato-intero");
    if (st) { st.hidden = true; $("intero-posto").replaceChildren(); }
  }
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && S.intera && !CAROSELLO) chiudiInteroPC();
  });

  // Il flusso: chi torna indietro a leggere ferma lo scorrimento; «In fondo» lo riprende
  // Un cambio di dimensione (il telefono girato, la finestra) sposta lo scorrimento senza che
  // nessuno l'abbia chiesto: chi seguiva la coda resta in fondo
  let ridimensionato = 0;
  window.addEventListener("resize", () => {
    ridimensionato = Date.now();
    const seguono = [...document.querySelectorAll(".flusso-chat:not(.staccato)")];
    requestAnimationFrame(() => seguono.forEach((c) => { c.scrollTop = c.scrollHeight; }));
  });
  document.addEventListener("scroll", (ev) => {
    const t = ev.target;
    if (!t || !t.classList || !t.classList.contains("flusso-chat")) return;
    if (Date.now() - ridimensionato < 400 && !t.classList.contains("staccato")) return;
    t.classList.toggle("staccato", !inFondo(t));
  }, true);

  document.addEventListener("click", async (ev) => {
    const b = ev.target.closest && ev.target.closest("[data-intero], [data-flusso-fondo], [data-svil-vista], [data-svil-esci], [data-svil-invia], [data-svil-scrivi]");
    if (!b || b.disabled) return;
    if (b.dataset.intero) { apriInteroPC(b.dataset.intero); return; }
    if (b.dataset.flussoFondo) {
      const box = b.closest(".flusso-chat");
      if (box) { box.scrollTop = box.scrollHeight; box.classList.remove("staccato"); }
      return;
    }
    if (b.dataset.svilVista) { if (S.svil) { S.svilLasciata = null; chiudiInteroPC(); disegnaVista(); } return; }
    if (b.dataset.svilEsci) {
      S.svilLasciata = S.svil ? chiaveDi(S.svil) : null;
      document.body.classList.remove("in-vista-sviluppo");
      const altra = S.cronologia.slice().reverse().find((x) => x.tipo !== "sviluppo" && valida(x));
      if (altra) mostra(altra); else { S.corrente = null; mostraInattiva(); }
      segnaTorna();
      return;
    }
    const piede = b.closest(".piede-svil");
    const esito = piede && piede.querySelector(".nota-svil");
    const dire = (t) => { if (esito) esito.textContent = t; };
    if (!S.scrittura.attiva) { dire(S.scrittura.testo || "Di' «" + S.parola + "» per usare i comandi."); return; }
    if (b.dataset.svilScrivi) {
      // «Prova con…», «Chiedi all'agente…»: la frase da finire nella casella dello scritto
      const testo = b.dataset.svilScrivi;
      if (CAROSELLO) { emetti("prefill", { testo }); return; }
      const i = $("scrivi-testo");
      if (!i || i.disabled) { dire("Qui non si può scrivere."); return; }
      i.value = testo;
      i.focus();
      try { i.setSelectionRange(testo.length, testo.length); } catch (e) { /* niente */ }
      dire("Finisci la frase qui sotto e premi Invia.");
      return;
    }
    b.disabled = true;
    let r = null;
    try { r = await postSessione("/api/scrivi", { testo: b.dataset.svilInvia }); } catch (e) { r = null; }
    b.disabled = !S.scrittura.attiva;
    if (r && r.dati && r.dati.codice === "senza_conversazione") { applicaScrittura({ attiva: false, testo: r.dati.errore }); dire(r.dati.errore || ""); return; }
    dire(r && r.status === 200 ? "Inviato: ti rispondo qui." : r ? (r.dati.errore || MESSAGGI[r.status] || "Non è andato.") : "Calliope non risponde.");
    if (r && r.status === 200) emetti("scritto", {});
  });

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
    if (INCORPORATA) {                    // lo stato lo disegna il telefono, anche la compagnia
      emetti("compagnia", { attiva: !!(v && v.compagnia), testo: TESTO_COMPAGNIA });
      return;
    }
    const box = $("voce");
    S.voce = v && TESTI_VOCE[v.stato] ? v : null;
    if (!S.voce) { box.hidden = true; voceGioco(""); return; }
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
        S.voce = { stato: "dorme", fino: null, compagnia: !!v.compagnia };
        stato = "dorme";
      } else {
        resto = Math.ceil(ms / 1000) + " s";
        box.querySelector(".voce-barra span").style.width =
          Math.max(0, Math.min(100, (ms / S.voceTotale) * 100)) + "%";
      }
    }
    voceGioco(stato);
    box.className = "voce " + stato + (resto ? " conta" : "");
    box.querySelector(".voce-testo").textContent = TESTI_VOCE[stato];
    box.querySelector(".voce-resto").textContent = resto;
    const comp = box.querySelector(".voce-compagnia");
    if (comp) {
      comp.hidden = !v.compagnia;
      comp.textContent = v.compagnia ? TESTO_COMPAGNIA : "";
    }
  }

  // ─── la stanza ascolta (13/10, conversazione di stanza) ───
  // «Ascolto la stanza», «Stanza in pausa: ospiti, fino alle 22:15»: lo dice il server per la
  // stanza di questo schermo. Sul telefono lo disegna la sua pagina (dal protocollo)
  function mostraStanza(d) {
    const box = $("stanza-segno");
    if (!box || INCORPORATA) return;
    const t = d && d.testo ? String(d.testo) : "";
    box.hidden = !t;
    box.textContent = t;
    box.classList.toggle("pausa", /pausa/i.test(t));
  }

  // ─── orologio e conti alla rovescia ───
  function mostraInattiva() {
    S.vista = "inattiva";
    const m = $("principale");
    if (m) m.replaceChildren();
    if (CAROSELLO || S.sezioni) { emetti("schede", {}); return; }
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
    // L'istantanea della partita (14/10, il motore dei giochi): fase, a chi tocca, punti,
    // comandi a voce attivi, numerata; con lo stato per la ripresa dopo «Riapri». E i comandi a
    // voce che il motore ha rifiutato perché arrivati su un'istantanea vecchia
    stato: ["istantanea", "ripresa"], rifiutato: ["comando", "motivo", "n"],
    // Una mossa o un nome da uno «specchio» di una partita condivisa con il motore (14/10): al
    // server, che la manda al motore che tiene la partita
    mossa: ["comando", "n", "rinomina", "nome"],
    // La diagnosi del palco (14/10, il motore dei giochi): al più tre frasi su ciò che esce
    palco: ["difetti"],
    // «Gira il telefono» (15/10): la tela del gioco vuole l'altro orientamento
    gira: ["orientamento"],
  };
  // Una mossa a voce (11/10, «ascolta» nel manifesto) verso il riquadro: solo il nome del
  // comando e, al più, il nome di chi gioca (il server li ha già scelti dall'elenco); dal 15/10
  // anche il numero dello schermo e il segno della voce
  const COMANDO_GIOCO = /^[a-z0-9][a-z0-9_]{0,23}$/;
  const CON_RISPOSTA = ["salva", "leggi", "chat", "di", "azione"];
  const GIOCO_MAX = 8192;            // caratteri di un messaggio (il server ha il suo tetto)
  const GIOCO_MAX_STATO = 24576;     // «stato» porta anche la ripresa (al più 16 000 sul server)
  const GIOCO_AL_SECONDO = 25;       // oltre: il riquadro si chiude
  const BATTITO_MS = 15000;          // tempo di gioco (minori): un battito mentre si vede
  const STATO_GIOCHI = new WeakMap();
  const GIOCHI_CHIUSI = {};          // partita → nota (resta chiuso anche se si ridisegna)

  function riquadri() { return [...document.querySelectorAll("iframe.riquadro-gioco")]; }
  function statoGioco(f) {
    let st = STATO_GIOCHI.get(f);
    if (!st) {
      // attesa: quando è partito il primo «ping» ancora senza risposta (0: nessuno)
      st = { finestra: null, pronto: null, pong: 0, nPing: 0, ultimoPing: 0, attesa: 0, inviati: [],
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
    togliComandiGioco(box);
    if (box) box.replaceChildren(el("p", "nota gioco-chiuso", nota));
    if (GIOCO.attivo === partita) esciModoGioco();
    if (motivo) alServerGioco(partita, { tipo: "guasto", motivo });
    if (motivo === "non risponde") {
      // Un riquadro bloccato in un ciclo infinito tiene occupato il suo processo, e il
      // browser lo riusa per il riquadro dopo: la pagina si ricarica (la cronologia torna dal
      // server, con la scheda chiusa). Sul telefono no: si perderebbero voce e microfono
      if (!INCORPORATA) setTimeout(() => location.reload(), 3000);
      else box && box.append(el("p", "nota", "Per giocare ancora, riapri Calliope."));
    }
  }

  // ─── la modalità gioco (11/10) ───
  // Nel riquadro della scheda un gioco era troppo piccolo per giocarci davvero. Quando arriva
  // un gioco la sua scheda occupa tutta la finestra (position: fixed: il riquadro NON si
  // sposta nella pagina, perché un iframe spostato si ricarica e la partita ripartirebbe) e,
  // dove il browser lo permette, la pagina va a schermo intero vero (requestFullscreen vuole
  // un gesto: se il gioco arriva dalla voce senza un tocco recente, ⛶ lo fa con un tocco; su
  // iPhone l'API non c'è e basta la finestra piena). Sopra il gioco, negli angoli: il pallino
  // della voce (ascolto, serve il nome, penso, parlo), ⛶ e ✕ per chiudere. Si esce con ✕, Esc,
  // «Calliope, chiudi il gioco» (la scheda vuota di schermo_mostra) o quando il gioco si chiude.
  // La voce non c'entra: è una vista della pagina, il microfono e la riproduzione (telefono) o
  // il satellite (PC) continuano come prima. Il riquadro, la sua sandbox e la CSP non cambiano.
  const GIOCO = { attivo: null, fs: false, voce: "", ultimo: null };
  const CHIUSI_DA_TE = {};           // partita → true: chiuso con ✕, «Riapri» lo rimette
  // Il pallino: [etichetta minima, descrizione per il title e i lettori di schermo]
  const VOCE_GIOCO = {
    ascolta: ["ascolto", "Calliope ti ascolta"],
    dorme: ["dormo", "Calliope è a disposizione: chiamala per nome"],
    pensa: ["penso", "Calliope ci sta pensando"],
    parla: ["parlo", "Calliope sta parlando"],
    spento: ["spento", "Il microfono di questo telefono è spento"],
  };

  function schermoInteroPossibile() {
    return !!(document.fullscreenEnabled && document.documentElement.requestFullscreen);
  }
  function chiediSchermoIntero() {
    if (!schermoInteroPossibile() || document.fullscreenElement) return;
    try {
      const p = document.documentElement.requestFullscreen({ navigationUI: "hide" });
      GIOCO.fs = true;
      if (p && p.catch) p.catch(() => { GIOCO.fs = false; aggiornaModoGioco(); });
    } catch (e) { GIOCO.fs = false; }
  }
  function lasciaSchermoIntero() {
    if (!GIOCO.fs) return;               // lo schermo intero chiesto da altri resta
    GIOCO.fs = false;
    if (document.fullscreenElement && document.exitFullscreen) {
      try { const p = document.exitFullscreen(); if (p && p.catch) p.catch(() => {}); } catch (e) { /* niente */ }
    }
  }

  function comandiGioco(c) {
    const box = el("div", "gioco-comandi");
    // Sul telefono il pallino è anche «Parla» (tocca e parla, tieni premuto per parlare a
    // lungo: telefono.js): sopra il gioco il pulsante grande non si vede
    const v = el(INCORPORATA ? "button" : "span", "gioco-voce");
    if (INCORPORATA) v.type = "button"; else v.setAttribute("role", "status");
    v.append(el("i", "gioco-pallino"), el("span", "gioco-voce-testo", ""));
    disegnaVoceGioco(v);
    const tutto = el("button", "gioco-tasto gioco-tutto", "⛶");
    tutto.type = "button";
    tutto.dataset.giocoTutto = "1";
    tutto.title = "Schermo intero";
    tutto.setAttribute("aria-label", "Schermo intero");
    tutto.hidden = !schermoInteroPossibile() || !!document.fullscreenElement;
    const ch = el("button", "gioco-tasto gioco-chiudi", "✕");
    ch.type = "button";
    ch.dataset.giocoChiudi = String(c.partita || "");
    ch.title = "Chiudi il gioco";
    ch.setAttribute("aria-label", "Chiudi il gioco");
    const entra = el("button", "piccolo-bottone gioco-entra", "Gioca a tutto schermo");
    entra.type = "button";
    entra.dataset.giocoEntra = String(c.partita || "");
    box.append(v);
    if (c.prova === true) {
      const pr = el("span", "gioco-prova-etichetta", "PROVA");
      pr.title = "Gioco in prova: non ancora approvato";
      box.append(pr);
    }
    box.append(tutto, ch, entra);
    return box;
  }
  function togliComandiGioco(box) {
    const corpo = box && box.parentElement;
    if (corpo) corpo.querySelectorAll(":scope > .gioco-comandi").forEach((x) => x.remove());
  }

  // Lo stato della voce per il pallino: sulla pagina degli schermi quello del server (evento
  // «voce», come la fascia in alto), sul telefono quello del telefono (telefono.js lo passa
  // con calliopeSchermo.voceGioco). Vuoto: questa pagina non lo conosce, il pallino non c'è
  function disegnaVoceGioco(v) {
    const st = GIOCO.voce;
    const d = VOCE_GIOCO[st];
    v.className = "gioco-voce" + (d ? " " + st : "");
    v.hidden = !d;
    const t = v.querySelector(".gioco-voce-testo");
    if (t && t.textContent !== (d ? d[0] : "")) t.textContent = d ? d[0] : "";
    const descr = d ? d[1] + (v.tagName === "BUTTON" ? ". Tocca per parlarle" : "") : "";
    if (v.title !== descr) { v.title = descr; v.setAttribute("aria-label", descr); }
  }
  function voceGioco(stato) {
    const nuovo = VOCE_GIOCO[stato] ? stato : "";
    if (nuovo === GIOCO.voce) return;
    GIOCO.voce = nuovo;
    document.querySelectorAll(".gioco-voce").forEach(disegnaVoceGioco);
  }

  function articoloGioco(p) {
    if (!p) return null;
    return [...document.querySelectorAll("article.scheda-gioco")].find((a) => a.dataset.partita === p
      && a.querySelector("iframe.riquadro-gioco") && !a.closest("[hidden]")) || null;
  }
  // Mette la pagina d'accordo con GIOCO.attivo: la classe sulla scheda e sul body, ⛶ visibile
  // solo dove serve; il telefono lo sa con l'evento «calliope:gioco»
  function aggiornaModoGioco() {
    let art = articoloGioco(GIOCO.attivo);
    if (GIOCO.attivo && !art) { GIOCO.attivo = null; lasciaSchermoIntero(); }
    document.querySelectorAll("article.scheda-gioco.modo-gioco").forEach((a) => {
      if (a !== art) a.classList.remove("modo-gioco");
    });
    if (art && !art.classList.contains("modo-gioco")) art.classList.add("modo-gioco");
    document.body.classList.toggle("in-modo-gioco", !!art);
    const fs = !!document.fullscreenElement;
    document.querySelectorAll(".gioco-tutto").forEach((b) => { b.hidden = !schermoInteroPossibile() || fs; });
    if (GIOCO.ultimo !== GIOCO.attivo) {
      GIOCO.ultimo = GIOCO.attivo;
      emetti("gioco", { partita: GIOCO.attivo });
    }
  }
  function entraModoGioco(p, gesto) {
    if (!p || GIOCHI_CHIUSI[p]) return;
    GIOCO.attivo = p;
    // Un gesto di chi guarda (un tocco su «Riapri», o «Parla» appena toccato): schermo intero vero
    if (gesto || (navigator.userActivation && navigator.userActivation.isActive)) chiediSchermoIntero();
    aggiornaModoGioco();
  }
  function esciModoGioco() {
    GIOCO.attivo = null;
    lasciaSchermoIntero();
    aggiornaModoGioco();
  }
  // ✕, Esc, la voce: il gioco si chiude davvero (il riquadro sparisce, il suo codice non
  // gira più e il tempo di gioco non conta); «Riapri» sulla scheda lo rimette
  function chiudiGiocoDaTe(p) {
    if (!p) return;
    CHIUSI_DA_TE[p] = true;
    const aperti = riquadri().filter((f) => f.dataset.partita === p);
    // Il gioco non ascolta più i comandi a voce (11/10) finché «Riapri» non lo rimette
    if (aperti.length) alServerGioco(p, { tipo: "chiuso" });
    aperti.forEach((f) => {
      const st = statoGioco(f);
      st.chiuso = true;
      const box = f.parentElement;
      f.remove();
      togliComandiGioco(box);
      if (box) {
        const corpo = box.parentElement;
        const b = el("button", "piccolo-bottone gioco-riapri", "Riapri");
        b.type = "button";
        b.dataset.giocoRiapri = p;
        box.replaceWith(el("p", "nota gioco-chiuso", "Hai chiuso il gioco."));
        if (corpo) corpo.append(b);
      }
    });
    if (GIOCO.attivo === p) esciModoGioco();
  }
  function riapriGioco(p, bottone) {
    delete CHIUSI_DA_TE[p];
    const s = bottone && bottone.closest("article.scheda-gioco");
    const c = (s && schedaDi(s.dataset.chiave))
      || (S.corrente && S.corrente.tipo === "gioco" && S.corrente.partita === p ? S.corrente : null);
    if (!s || !c) return;
    GIOCO.attivo = p;
    const corpo = el("div", "corpo");
    DISEGNA.gioco(c, corpo, s);
    const vecchio = s.querySelector(":scope > .corpo");
    if (vecchio) vecchio.replaceWith(corpo); else s.append(corpo);
    entraModoGioco(p, true);
  }

  document.addEventListener("click", (ev) => {
    const t = ev.target && ev.target.closest ? ev.target.closest("[data-gioco-chiudi], [data-gioco-tutto], [data-gioco-entra], [data-gioco-riapri]") : null;
    if (!t) return;
    if (t.dataset.giocoChiudi !== undefined) chiudiGiocoDaTe(t.dataset.giocoChiudi || GIOCO.attivo);
    else if (t.dataset.giocoTutto !== undefined) chiediSchermoIntero();
    else if (t.dataset.giocoEntra !== undefined) entraModoGioco(t.dataset.giocoEntra, true);
    else if (t.dataset.giocoRiapri !== undefined) riapriGioco(t.dataset.giocoRiapri, t);
    aggiornaModoGioco();
  });
  // Esc (quando il tasto arriva alla pagina: dentro il riquadro lo tiene il gioco), se sopra
  // il gioco non c'è uno strato aperto (il telefono e la pagina degli schermi chiudono prima quello)
  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape" || !GIOCO.attivo) return;
    if (document.querySelector(".strato:not([hidden]), .strato-intero:not([hidden])")) return;
    chiudiGiocoDaTe(GIOCO.attivo);
  });
  // Lo schermo intero lasciato dal browser (Esc, il gesto indietro): la modalità gioco resta,
  // a finestra piena, e ⛶ torna
  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement) GIOCO.fs = false;
    aggiornaModoGioco();
  });

  // ─── Le partite aperte e i giochi di casa (28/10, passo 2c, #258: la pagina Giochi) ───
  // Solo testo, nessun tasto: un gioco si apre a voce, e il riquadro vero è la scheda «gioco»
  // (una copia sola: la pagina la mostra sotto). Tutto in textContent
  // ─── L'archivio di casa nella pagina Documenti (28/10, passo 2d, #259, raccolte.py) ───
  // Una riga per documento: nome, data, importo, di chi è, e «Scarica» del file originale (la
  // chiave della riga; la sorgente resta sul server). Il nome viene dai dati estratti dal
  // documento: un dato non fidato, solo testo (el → textContent), mai HTML
  const NOMI_ORIGINALE = { pdf: "PDF", jpg: "foto", jpeg: "foto", png: "immagine", webp: "immagine", tif: "immagine",
    tiff: "immagine", bmp: "immagine", docx: "Word", txt: "testo" };
  DISEGNA.archivio = function (c, corpo, s) {
    s.classList.add("scheda-archivio");
    const voci = Array.isArray(c.voci) ? c.voci.filter((v) => v && typeof v === "object") : [];
    if (!voci.length) {
      corpo.append(el("p", "vuoto", c.vuoto || "Nessun documento."));
      if (c.nota) corpo.append(el("p", "nota", c.nota));
      return;
    }
    const ul = el("ul", "voci-archivio");
    for (const v of voci) {
      const li = el("li", "documento-archivio");
      li.append(el("p", "nome-documento", String(v.nome || "Documento")));
      const meta = [v.data, v.importo, v.di].map((x) => String(x || "")).filter(Boolean);
      if (meta.length) li.append(el("p", "sotto", meta.join(" · ")));
      const est = String(v.estensione || "").toLowerCase();
      if (v.chiave && NOMI_ORIGINALE[est]) {
        const box = el("div", "scarica");
        const b = el("button", "piccolo-bottone tasto-scarica", "Scarica " + NOMI_ORIGINALE[est]);
        b.type = "button";
        b.dataset.scarica = "originale";
        b.dataset.chiaveScheda = String(v.chiave);
        box.append(b, el("span", "esito-scarica", ""));
        li.append(box);
      }
      ul.append(li);
    }
    corpo.append(ul);
    if (c.nota) corpo.append(el("p", "nota", c.nota));
  };

  // ─── L'ufficio nella pagina Ufficio (28/10, passo 2e, #260, raccolte.py): solo chi amministra ───
  // Una riga per documento (numero, data, cliente, importo, stato e «Scarica» di ogni file
  // generato) o per contatto della rubrica (nome, dettagli, di casa o solo sua). Nomi e recapiti
  // dei clienti sono dati non fidati: solo testo (el → textContent), mai HTML
  const NOMI_UFFICIO = { pdf: "PDF", xml: "XML", docx: "Word", pptx: "PowerPoint" };
  DISEGNA.ufficio = function (c, corpo, s) {
    s.classList.add("scheda-ufficio");
    const voci = Array.isArray(c.voci) ? c.voci.filter((v) => v && typeof v === "object") : [];
    if (!voci.length) {
      corpo.append(el("p", "vuoto", c.vuoto || "Niente qui, per ora."));
      if (c.nota) corpo.append(el("p", "nota", c.nota));
      return;
    }
    const ul = el("ul", "voci-archivio voci-ufficio");
    for (const v of voci) {
      const li = el("li", "documento-archivio voce-ufficio" + (v.annullato ? " annullata" : ""));
      li.append(el("p", "nome-documento", String(v.nome || "Documento")));
      const dett = (Array.isArray(v.dettagli) ? v.dettagli : []).map((x) => String(x || "")).filter(Boolean);
      if (dett.length) li.append(el("p", "sotto", dett.join(" · ")));
      if (v.stato) li.append(el("p", "stato-ufficio", String(v.stato)));
      const file = (Array.isArray(v.file) ? v.file : []).filter((f) => f && f.chiave
        && NOMI_UFFICIO[String(f.estensione || "").toLowerCase()]);
      if (file.length) {
        const box = el("div", "scarica");
        for (const f of file) {
          const b = el("button", "piccolo-bottone tasto-scarica",
            "Scarica " + NOMI_UFFICIO[String(f.estensione).toLowerCase()]);
          b.type = "button";
          b.dataset.scarica = "originale";
          b.dataset.chiaveScheda = String(f.chiave);
          box.append(b);
        }
        box.append(el("span", "esito-scarica", ""));
        li.append(box);
      }
      ul.append(li);
    }
    corpo.append(ul);
    if (c.nota) corpo.append(el("p", "nota", c.nota));
  };

  DISEGNA.giochi = function (c, corpo, s) {
    s.classList.add("scheda-giochi");
    const partite = Array.isArray(c.partite) ? c.partite.filter((p) => p && typeof p === "object") : [];
    const giochi = Array.isArray(c.giochi) ? c.giochi.filter((g) => g && typeof g === "object") : [];
    if (c.nota) corpo.append(el("p", "sotto", c.nota));
    if (!partite.length && !giochi.length) {
      corpo.append(el("p", "vuoto", c.vuoto || "Niente qui, per ora."));
      return;
    }
    const ul = el("ul", "voci-giochi");
    for (const p of partite) {
      const li = el("li", "partita");
      li.append(el("p", "nome-gioco", String(p.titolo || "Gioco") + (p.prova ? " (prova)" : "")));
      const dove = (Array.isArray(p.dove) ? p.dove : []).map(String).filter(Boolean);
      li.append(el("p", "sotto", p.qui ? "Su questo schermo: è qui sotto."
        : "Sullo schermo " + (dove.length ? dove.join(", ") : "di un'altra stanza") + "."));
      const punti = (Array.isArray(p.punti) ? p.punti : []).filter((x) => x && x.nome)
        .map((x) => String(x.nome) + " " + (Number(x.punti) || 0));
      if (p.esito) li.append(el("p", "riassunto-lavoro", String(p.esito)));
      else if (p.tocca) li.append(el("p", "riassunto-lavoro", "Tocca a " + String(p.tocca) + "."));
      if (punti.length) li.append(el("p", "sotto", "Punti: " + punti.join(" · ")));
      ul.append(li);
    }
    for (const g of giochi) {
      const li = el("li", "gioco-casa");
      li.append(el("p", "nome-gioco", String(g.titolo || "Gioco")));
      const meta = [g.giocatori, g.descrizione].map((x) => String(x || "")).filter(Boolean);
      if (meta.length) li.append(el("p", "sotto", meta.join(" · ")));
      if (g.dire) li.append(el("p", "sotto dire-gioco", "Per giocare: " + String(g.dire)));
      ul.append(li);
    }
    corpo.append(ul);
  };

  DISEGNA.gioco = function (c, corpo, s) {
    s.classList.add("scheda-gioco");
    s.dataset.partita = String(c.partita || "");
    const chiuso = GIOCHI_CHIUSI[c.partita];
    if (chiuso || c.stato === "chiuso") {
      corpo.append(el("p", "nota gioco-chiuso", chiuso || c.nota || "Il gioco è chiuso."));
      return;
    }
    if (typeof c.doc !== "string" || !/^\/gioco\/[A-Za-z0-9_-]{20,}$/.test(c.doc)) {
      corpo.append(el("p", "nota", "Questo gioco non si può aprire."));
      return;
    }
    if (CHIUSI_DA_TE[c.partita]) {
      // Chiuso con ✕ (11/10): il riquadro non c'è più; «Riapri» lo rimette, a tutto schermo
      corpo.append(el("p", "nota gioco-chiuso", "Hai chiuso il gioco."));
      const b = el("button", "piccolo-bottone gioco-riapri", "Riapri");
      b.type = "button";
      b.dataset.giocoRiapri = String(c.partita || "");
      corpo.append(b);
      return;
    }
    // La modalità gioco (11/10): la classe nasce con la scheda, così un allineamento
    // (allinea copia le classi della scheda nuova) non la toglie a metà partita
    if (GIOCO.attivo && GIOCO.attivo === c.partita) s.classList.add("modo-gioco");
    // La variante «collaudo» (11/10): un gioco non ancora approvato, aperto per provarlo (il
    // server mette "prova": true nella scheda): cornice ambra e «PROVA» sopra il gioco
    if (c.prova === true) s.classList.add("gioco-prova");
    corpo.append(comandiGioco(c));
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
        || !Object.prototype.hasOwnProperty.call(TIPI_DAL_RIQUADRO, m.tipo)
        || n > (m.tipo === "stato" ? GIOCO_MAX_STATO : GIOCO_MAX)) {
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
    if (m.tipo === "pong") { st.pong = adesso; st.attesa = 0; return; }
    // «pronto» vale per la finestra che l'ha mandato (un riquadro spostato riparte da capo)
    if (m.tipo === "pronto") { st.pronto = ev.source; st.pong = adesso; st.attesa = 0; }
    dalRiquadro(f, st, m);
  });

  function alDito() {
    try { return !!(window.matchMedia && matchMedia("(pointer: coarse)").matches); } catch (e) { return false; }
  }

  async function dalRiquadro(f, st, m) {
    // Solo i campi noti per tipo: nient'altro arriva al server
    const dati = { tipo: m.tipo, id: Number.isInteger(m.id) ? m.id : null };
    TIPI_DAL_RIQUADRO[m.tipo].forEach((k) => { if (m[k] !== undefined) dati[k] = m[k]; });
    const r = await alServerGioco(f.dataset.partita, dati);
    if (st.chiuso) return;
    const d = r.dati || {};
    if (m.tipo === "pronto") {
      if (d.fine_tempo) { chiudiGioco(f, d.nota || "Per oggi il tempo dei giochi è finito."); return; }
      // «tocco»: questa pagina è su un telefono o un tablet (15/10, «Gira il telefono»: il
      // riquadro, in un processo suo, non sempre lo sa da sé)
      if (d.avvio) versoRiquadro(f, { tipo: "avvio", dati: { ...d.avvio, tocco: alDito() } });
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
    if (d.tipo === "comando") {
      // Una mossa a voce (11/10): solo un nome di comando, il numero dell'istantanea su cui è
      // stato riconosciuto (14/10) e, al più, il nome di chi gioca
      if (typeof x.comando !== "string" || !COMANDO_GIOCO.test(x.comando)) return;
      const dati = { comando: x.comando };
      if (Number.isInteger(x.n) && x.n >= 0) dati.n = x.n;
      if (typeof x.giocatore === "string" && x.giocatore.length <= 40) dati.giocatore = x.giocatore;
      // Chi è quale giocatore (15/10): il numero dello schermo da cui arriva la mossa e la voce
      // riconosciuta, un segno opaco («v1»)
      if (Number.isInteger(x.schermo) && x.schermo >= 1 && x.schermo <= 99) dati.schermo = x.schermo;
      if (typeof x.voce === "string" && /^v[1-9][0-9]?$/.test(x.voce)) dati.voce = x.voce;
      fs.forEach((f) => { if (!statoGioco(f).chiuso) versoRiquadro(f, { tipo: "comando", dati }); });
      return;
    }
    if (d.tipo === "partita" || d.tipo === "autorevole" || d.tipo === "specchio") {
      // Lo stato della partita condivisa con il motore (14/10): uno specchio lo disegna,
      // «autorevole» passa la partita a questo schermo. Solo un oggetto, entro il tetto
      let n = Infinity;
      try { n = JSON.stringify(x.stato === undefined ? null : x.stato).length; } catch (e) { /* no */ }
      if (n > GIOCO_MAX_STATO || (x.stato !== null && x.stato !== undefined
          && (typeof x.stato !== "object" || Array.isArray(x.stato)))) return;
      fs.forEach((f) => { if (!statoGioco(f).chiuso) versoRiquadro(f, { tipo: d.tipo, dati: { stato: x.stato || null } }); });
      return;
    }
    if (d.tipo === "nome") {
      // Un nome scritto su uno specchio, per il motore che tiene la partita (14/10)
      if (!Number.isInteger(x.i) || x.i < 0 || typeof x.nome !== "string" || x.nome.length > 20) return;
      fs.forEach((f) => { if (!statoGioco(f).chiuso) versoRiquadro(f, { tipo: "nome", dati: { i: x.i, nome: x.nome } }); });
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
      // Il limite conta dal primo «ping» rimasto senza risposta, non dall'ultimo «pong» (14/10):
      // prima un gioco sano sembrava muto per tutto l'intervallo tra due ping (2 s, che con il
      // giro da 1 s diventano 3 s quando il giro arriva un attimo prima dei 2000 ms), e con
      // giochi_watchdog_s = 3 bastava un giro in ritardo di pochi ms per chiuderlo
      // («non risponde» a caso nelle prove, anche senza carico); una pagina rallentata (scheda
      // nascosta: un giro al minuto) chiudeva il gioco senza averlo nemmeno interrogato
      if (st.attesa && adesso - st.attesa > lim) {
        chiudiGioco(f, "Il gioco non rispondeva più: l'ho chiuso.", "non risponde");
        return;
      }
      if (adesso - st.ultimoPing >= 2000) {
        st.ultimoPing = adesso;
        if (!st.attesa) st.attesa = adesso;
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
    if (GIOCO.attivo) aggiornaModoGioco();
    if (S.vista === "scheda" && S.corrente && !valida(S.corrente) && !vistaAttiva()) {
      S.corrente = null;
      mostraInattiva();
    }
  }, 250);

  document.addEventListener("DOMContentLoaded", () => {
    mostraInattiva();
    avvio();
  });
})();
