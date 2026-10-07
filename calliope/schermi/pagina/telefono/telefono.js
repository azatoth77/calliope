// Calliope · telefono: la web app che fa del telefono un satellite (03/10/2026).
// Protocollo: quello del satellite (calliope/satellite/protocollo.py) su un WebSocket del
// server degli schermi. Da addormentata l'audio non esce dal telefono finché la wake word
// «Calliope», che gira qui, non scatta; con «Parla» la frase parte subito.
// Tutto il testo che arriva dal server va in textContent: sono dati, mai HTML.
import { Ascolto, FRAME, Riproduttore, SR, Vad, WakeWord, caricaOrt, misure, sessione } from "./voce.js";
import { SchermoAcceso } from "./schermo-acceso.js";

const VERSIONE = 2;
const CHIAVE_TOKEN = "calliope.telefono.token";
const CHIAVE_NOME = "calliope.telefono.nome";
const CHIAVE_MIC = "calliope.telefono.microfono";
const CHIAVE_TIENI = "calliope.telefono.schermo_acceso";   // "0": lo schermo può spegnersi
const ATTESE_MS = [1000, 2000, 5000, 10000, 15000];
// Valori di riserva finché il server non manda i suoi (benvenuto: calliope.yaml del server)
const PARAMETRI = {
  name: "Calliope", wake_word: null, wake_anche_nome: true, sample_rate: 16000, vad_threshold: 0.5, silence_ms: 700, preroll_ms: 300,
  min_speech_ms: 250, max_utterance_s: 20, wake_threshold: 0.5, wake_consecutive: 2,
  barge_in_threshold: 0.5, barge_in_seed_s: 2.0,
};

const $ = (id) => document.getElementById(id);
const leggi = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };
const scrivi = (k, v) => {
  try { if (v === null || v === undefined) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { /* niente */ }
};
const aspetta = (ms) => new Promise((ok) => setTimeout(ok, ms));

const st = {
  ws: null, token: leggi(CHIAVE_TOKEN), collegato: false, attivo: false, altro: null,
  satellite: {}, tentativi: 0, sostituito: false,
  mic: false,            // «microfono acceso» (vivavoce, con la wake word)
  micVoluto: leggi(CHIAVE_MIC) === "1",
  L: null,               // richiesta di ascolto del server {id, wake, fino, sveglia}
  W: null,               // veglia (Calliope parla) {id, basta}
  corsa: null,           // ascolto o veglia in corso {basta, promessa}
  reg: null,             // registrazione da tocco {uscita, finisci}
  forza: false,          // tocco in vivavoce: la frase comincia adesso
  rilascio: false,       // fine della pressione lunga
  semi: null,            // il seme di un barge-in, per l'ascolto dopo
  pensa: false,
  modelli: "no",         // no | carico | pronti | errore
  inviato: 0,            // byte di audio mandati (misure)
  lasciaTimer: null,
  micDa: 0,              // performance.now() dell'accensione del microfono
  tocco: 0,              // ultimo tocco sulla pagina
  tieni: leggi(CHIAVE_TIENI) !== "0",
  risposta: { turno: -1, testo: "", ora: 0 },   // l'ultima risposta di Calliope (prima del carosello)
};
const param = Object.assign({}, PARAMETRI);
const ascolto = new Ascolto(param);
const player = new Riproduttore("Calliope");
// La voce comincia a sentirsi (07/10): come `suona` del satellite in Python, per `prima_voce_s`
player.onSuona = (id, uscita) => manda({ tipo: "suona", id, uscita_s: Math.round(uscita * 1000) / 1000 });
let suoni = {};          // {inizio, fine}: {pcm (Uint8Array, int16), rate} dal benvenuto
function suona(tipo) {
  const s = suoni[tipo];
  if (s) player.segnale(s.pcm, s.rate);
}
// Il microfono ha un AudioContext suo (03/10): quello della riproduzione nasce al primo tocco,
// prima che la sessione audio passi a «play-and-record». Su iOS quel passaggio può cambiare
// la frequenza dell'hardware sotto un contesto già aperto, e un MediaStreamSource a una
// frequenza diversa da quella del contesto dà audio accelerato, rallentato o rotto (al server
// arrivavano parole in islandese e impronte vocali a 0,1–0,2).
const mic = {
  stream: null, ctx: null, nodo: null, sorgente: null, zero: null,
  rate: 0, traccia: null, vincoli: null, conti: null, seq: -1, persi: 0, fuoriOrdine: 0,
  blocchi: 0, ritmo: null, fuoriRitmo: 0, ricostruito: 0, motivo: "", diag: null, orologio: null,
};
// Le correzioni del browser: accese di solito, spente dalla diagnostica (seconda prova)
const VINCOLI = { echoCancellation: true, noiseSuppression: true, autoGainControl: true };
const SENZA_CORREZIONI = { echoCancellation: false, noiseSuppression: false, autoGainControl: false };
// Solo per le prove: forzaRate crea il contesto del microfono a un'altra frequenza (il caso iOS)
const opzioniMic = { forzaRate: null };
const RITMO_TOLLERANZA = 0.06;      // ±6 % tra l'orologio del contesto e quello vero
const RITMO_FINESTRA_MS = 2500;

// ───────────────────────────── interfaccia ─────────────────────────────
// Dal 04/10 la pagina è una vista sola, quella che era la «vista da guida»: stato di questo
// telefono, il carosello (risposta e schede), «Parla», «Microfono» e «Scrivi». Il resto
// (impostazioni, «Prova il microfono», certificato, abbinamento) sta nel menu o compare
// quando serve (il modulo da compilare, la casella per scrivere).
function statoTel(cls, testo) {
  for (const [id, idt] of [["tel-stato", "tel-stato-testo"], ["tel-collegamento", "tel-collegamento-testo"]]) {
    const e = $(id);
    if (e) e.className = "stato " + cls;
    metti($(idt), testo);
  }
}

function avviso(testo) {
  for (const id of ["avviso-tel", "abbina-avviso"]) {
    const a = $(id);
    if (!a) continue;
    a.hidden = !testo;
    metti(a, testo || "");
  }
}

const TESTI = {
  dorme: "Dormo · di' «Calliope»", ascolta: "Ti ascolto", pensa: "Ci penso…", parla: "Parlo",
  tocca: "Tocca «Parla»", altrove: "Ascolto altrove", giu: "Non collegata",
};

function voceLocale() {
  if (!st.collegato) return ["dorme", TESTI.giu, ""];
  if (player.inCorso()) return ["parla", TESTI.parla, ""];
  if (st.reg || (st.corsa && st.corsa.tipo === "ascolto" && st.corsa.parla)) return ["ascolta", TESTI.ascolta, ""];
  if (st.pensa) return ["pensa", TESTI.pensa, ""];
  if (!st.attivo) return ["dorme", st.altro ? "In ascolto su «" + st.altro + "»" : TESTI.altrove, ""];
  const L = st.L;
  if (L && st.mic) {
    const resto = L.fino - performance.now();
    if (!L.wake || resto > 0) return ["ascolta", TESTI.ascolta, L.wake && isFinite(resto) ? Math.ceil(resto / 1000) + " s" : ""];
    return ["dorme", TESTI.dorme, ""];
  }
  if (L && L.wake && L.fino > performance.now()) return ["ascolta", TESTI.tocca, Math.ceil((L.fino - performance.now()) / 1000) + " s senza nome"];
  return ["dorme", TESTI.tocca, ""];
}

// Lo stato in alto riguarda QUESTO telefono (04/10: in auto «In ascolto su «studio»» col
// microfono del telefono spento confondeva): [classe, parola grande, riga piccola sotto]
function statoVista(cls) {
  const dove = st.altro ? "Il microfono attivo è su «" + st.altro + "»" : "";
  if (!st.collegato) return ["spento", "Non collegata", "Riprovo da sola"];
  if (cls === "parla") return ["parla", "Parlo", ""];
  if (cls === "pensa") return ["pensa", "Penso…", ""];
  if (cls === "ascolta" && (st.reg || st.mic || (st.corsa && st.corsa.parla))) return ["ascolta", "Ti ascolto", ""];
  if (!st.mic && !st.reg) return ["spento", "Microfono spento", dove || "Tocca «Parla» per parlare"];
  return ["dorme", TESTI.dorme, st.attivo ? "" : dove];
}

function disegna() {
  const [cls] = voceLocale();
  const [gc, parola, sotto] = statoVista(cls);
  const v = $("tel-voce");
  if (v.className !== "voce " + gc) v.className = "voce " + gc;
  metti(v.querySelector(".voce-testo"), parola);
  const d = $("tel-dove");
  d.hidden = !sotto;
  metti(d, sotto);
  $("vista").classList.toggle("mic-acceso", st.mic);
  const b = $("parla");
  metti(b.querySelector(".parla-testo"), st.reg ? "Ti ascolto · tocca per finire"
    : cls === "parla" ? "Interrompi e parla" : "Parla");
  b.disabled = !st.collegato;
  b.classList.toggle("in-corso", !!st.reg || st.forza || (cls === "ascolta" && !!st.corsa && st.corsa.parla));
  b.classList.toggle("parla-calliope", cls === "parla" && !st.reg);
  attr($("microfono"), "aria-checked", st.mic ? "true" : "false");
  metti($("mic-stato"), st.mic ? "acceso" : "spento");
  disegnaRisposta();
  segnaTagli();
}
setInterval(disegna, 250);

// Scrive solo se cambia: il giro ogni 250 ms non tocca il DOM per niente
function metti(el, testo) { if (el && el.textContent !== testo) el.textContent = testo; }
function attr(el, k, v) { if (el && el.getAttribute(k) !== v) el.setAttribute(k, v); }

// ───────────────────────────── schermo acceso (04/10) ─────────────────────────────
// Una pagina web non ascolta a schermo spento (iOS la sospende): finché il microfono è acceso
// lo schermo resta acceso (Screen Wake Lock API, schermo-acceso.js), e se il browser non lo
// concede la pagina lo dice invece di fermarsi in silenzio.
const schermo = new SchermoAcceso({ onCambio: () => disegnaSchermo() });
const PUO_SPEGNERSI = "Lo schermo può spegnersi, e allora Calliope smetterà di ascoltare";

// [classe, testo] dell'indicatore, o null se non serve (microfono spento)
function statoSchermo() {
  if (!st.mic) return null;
  if (!st.tieni) return ["avvisa", PUO_SPEGNERSI + " (lo hai scelto nelle impostazioni)."];
  const s = schermo.stato;
  if (s === "acceso" && !schermo.info.inaffidabile) return ["ok", "Schermo acceso"];
  if (s === "chiedo") return ["attesa", "Tengo acceso lo schermo…"];
  const m = schermo.motivo || schermo.info.motivo;
  return ["avvisa", PUO_SPEGNERSI + (m ? ": " + m : "") + "."];
}

// Nel menu l'indicatore discreto; nella vista solo l'avviso, quando lo schermo può spegnersi
function disegnaSchermo() {
  const r = statoSchermo();
  const box = $("schermo-stato");
  if (box) {
    box.hidden = !r;
    if (r) { box.className = "schermo-stato " + r[0]; metti($("schermo-testo"), r[1]); }
  }
  const g = $("schermo-avviso");
  if (g) {
    const avvisa = !!r && r[0] === "avvisa";
    g.hidden = !avvisa;
    metti(g, avvisa ? r[1] : "");
  }
}

function impostaTieni(v) {
  st.tieni = !!v;
  scrivi(CHIAVE_TIENI, st.tieni ? null : "0");
  attr($("schermo-tieni"), "aria-checked", st.tieni ? "true" : "false");
  // Dal tocco sull'interruttore: il gesto vale anche per la richiesta
  schermo.vuoi(st.tieni && st.mic);
  disegnaSchermo();
}

// ───────────────────────────── carosello (04/10) ─────────────────────────────
// La risposta e le schede (lista, timer, programma, documento, risposta scritta…) una per
// volta, la più recente per prima, scorrendo di lato (scroll-snap, niente librerie). Le schede
// le tiene schermo.js (sessione, cronologia, disegno): qui si mettono in fila. Una scheda
// aggiornata (stessa chiave) si allinea al suo posto, senza ricostruirla né spostarla; una
// scheda nuova, o mandata di nuovo («sposta»), va in testa e si mostra. La risposta di un
// turno nuovo va in testa e si mostra, a meno che Calliope abbia appena mostrato una scheda
// (che di solito è proprio il contenuto della risposta): allora resta la scheda. Chi scorre
// a mano non viene spostato per un po'.
const RISPOSTA = "__risposta";
const car = {
  seq: { [RISPOSTA]: 0 },   // chiave → ordine (più grande = più recente)
  n: 0,
  schede: {},               // chiave → dati della scheda
  ordine: [RISPOSTA],       // le chiavi mostrate, la più recente per prima
  vista: RISPOSTA,          // la chiave che si sta guardando
  atteso: null,             // dove deve arrivare lo scorrimento chiesto da qui (vaiA)
  toccato: -1e9,            // ultimo scorrimento a mano (performance.now)
  mostrataDa: -1e9,         // ultima scheda mostrata da Calliope
  modulo: null,             // chiave del modulo aperto nello strato
  moduloFirma: "",
  intera: null,             // chiave della scheda aperta a schermo intero (06/10)
};
// Le schede che hanno sempre «Espandi» (le altre solo se non ci stanno): sul telefono il
// cruscotto, il codice di un lavoro, un documento o l'uscita di un programma non si leggono
// nel riquadro del carosello (06/10, iPhone 13 mini)
const TIPI_LUNGHI = new Set(["cruscotto", "lavoro", "documento", "esecuzione", "biblioteca", "web", "allegato"]);
// Queste non si aprono a schermo intero: il modulo ha il suo strato, il gioco il suo riquadro
const TIPI_SENZA_INTERA = new Set(["modulo", "gioco"]);
const opzioniCarosello = { manoMs: 10000, schedaMs: 12000 };
const fmtOra = new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit" });
const sch = () => window.calliopeSchermo;

function chiaveDi(c) { return c.chiave || c.id; }

// L'ultima risposta (le frasi di un turno, in ordine), al più ~300 caratteri: la coda
function ricordaFrase(turno, testo) {
  const nuovo = turno !== st.risposta.turno;
  if (nuovo) st.risposta = { turno, testo: "", ora: Date.now() };
  let t = (st.risposta.testo ? st.risposta.testo + " " : "") + testo.trim();
  if (t.length > 300) t = "…" + t.slice(t.length - 299).replace(/^\S*\s/, "");
  st.risposta.testo = t;
  if (nuovo) {
    car.seq[RISPOSTA] = ++car.n;
    disponi();
    const ora = performance.now();
    if (ora - car.toccato > opzioniCarosello.manoMs && ora - car.mostrataDa > opzioniCarosello.schedaMs) vaiA(RISPOSTA);
  }
  disegnaRisposta();
  if (car.intera === RISPOSTA) disegnaIntera();
}

function disegnaRisposta() {
  const r = $("risposta-testo");
  if (!r) return;
  const vuota = !st.risposta.testo;
  metti(r, vuota ? "Di' «Calliope» o tocca «Parla»: le risposte e le schede compaiono qui." : st.risposta.testo);
  r.classList.toggle("vuota", vuota);
  const et = $("risposta").querySelector(".etichetta");
  metti(et, vuota ? "Calliope" : "Risposta · " + fmtOra.format(new Date(st.risposta.ora || Date.now())));
}

// La scheda per il carosello: quella di schermo.js, con l'ora; il modulo come riassunto con
// «Compila» (il modulo vero si apre nel suo strato, che ha posto per la tastiera)
function costruisciPagina(c) {
  let s;
  if (c.tipo === "modulo") {
    s = document.createElement("article");
    s.className = "scheda tipo-modulo modulo-car";
    s.dataset.chiave = chiaveDi(c);
    const et = document.createElement("div");
    et.className = "etichetta";
    et.textContent = "Da scrivere";
    s.append(et);
    const h = document.createElement("h1");
    h.className = "titolo";
    h.textContent = c.titolo || "";
    s.append(h);
    const corpo = document.createElement("div");
    corpo.className = "corpo";
    if (c.domanda) {
      const p = document.createElement("p");
      p.className = "domanda-modulo";
      p.textContent = c.domanda;
      corpo.append(p);
    }
    if (c.stato === "aperto" && c.campi && c.campi.length) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tasto apri-modulo";
      b.textContent = "Compila";
      corpo.append(b);
    } else {
      const p = document.createElement("p");
      p.className = "nota-modulo";
      p.textContent = c.nota || "Il modulo è chiuso.";
      corpo.append(p);
    }
    s.append(corpo);
  } else {
    s = sch().costruisci(c);
  }
  s.classList.add("pagina-car");
  s.setAttribute("aria-roledescription", "scheda");
  const et = s.querySelector(".etichetta");
  if (et && c.creata) {
    const q = document.createElement("span");
    q.className = "quando";
    q.textContent = fmtOra.format(new Date(c.creata * 1000));
    et.append(q);
  }
  // «Espandi» (06/10): in fondo alla scheda, sotto la dissolvenza; visibile sulle schede
  // lunghe (classe «lunga», da segnaTagli)
  if (!TIPI_SENZA_INTERA.has(c.tipo)) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "espandi";
    b.textContent = "Espandi";
    b.setAttribute("aria-label", "Apri a schermo intero: " + (c.titolo || sch().NOMI_TIPO[c.tipo] || "scheda"));
    s.append(b);
  }
  return s;
}

// La fila: le chiavi in ordine di tempo; la risposta vuota solo se non c'è nient'altro
function disponi() {
  const bin = $("binario");
  const chiavi = Object.keys(car.schede);
  const conRisposta = !!st.risposta.testo || !chiavi.length;
  const ordine = (conRisposta ? [RISPOSTA] : []).concat(chiavi)
    .sort((a, b) => (car.seq[b] || 0) - (car.seq[a] || 0));
  const prima = car.vista;
  const r = $("risposta");
  r.hidden = !conRisposta;
  // In fila solo dove serve: spostare un elemento ne azzera lo scorrimento interno
  ordine.forEach((k, i) => {
    const e = k === RISPOSTA ? r : bin.querySelector(':scope > [data-chiave="' + CSS.escape(k) + '"]');
    if (e && bin.children[i] !== e) bin.insertBefore(e, bin.children[i] || null);
  });
  if (!conRisposta && r.parentNode === bin) bin.append(r);   // nascosta, in fondo
  car.ordine = ordine;
  disegnaPunti();
  if (ordine.includes(prima)) vaiA(prima); else vaiA(ordine[0]);
}

// Le schede di schermo.js nel binario: nuove, aggiornate al loro posto, tolte
function sincronizza(det) {
  const bin = $("binario");
  const lista = sch() ? sch().cronologia() : [];
  const viste = new Set();
  if (det && det.scheda && det.spostata) car.seq[chiaveDi(det.scheda)] = ++car.n;
  for (const c of lista) {
    const k = chiaveDi(c);
    viste.add(k);
    if (!(k in car.seq)) car.seq[k] = ++car.n;
    const vecchia = car.schede[k];
    car.schede[k] = c;
    const el = bin.querySelector(':scope > [data-chiave="' + CSS.escape(k) + '"]');
    if (el && vecchia === c) continue;
    const nuova = costruisciPagina(c);
    if (el && vecchia && vecchia.tipo === c.tipo) {
      const seguite = [...el.querySelectorAll("pre[data-segui]")].map((p) => p.scrollHeight - p.scrollTop - p.clientHeight < 24);
      sch().allinea(el, nuova);
      el.querySelectorAll("pre[data-segui]").forEach((p, i) => { if (seguite[i] !== false) p.scrollTop = p.scrollHeight; });
    } else if (el) {
      el.replaceWith(nuova);
    } else {
      bin.append(nuova);
      nuova.querySelectorAll("pre[data-segui]").forEach((p) => { p.scrollTop = p.scrollHeight; });
    }
    if (car.modulo === k) aggiornaModulo(c);
    if (car.intera === k) disegnaIntera();
  }
  for (const k of Object.keys(car.schede)) {
    if (viste.has(k)) continue;
    delete car.schede[k];
    const el = bin.querySelector(':scope > [data-chiave="' + CSS.escape(k) + '"]');
    if (el) el.remove();
    // Tolta da chi la guarda (il «Chiudi» del cruscotto) o da Calliope (revoca, non amministra
    // più): lo strato si chiude. Uscita dalla cronologia perché ne sono arrivate altre: resta
    // aperta con l'ultimo contenuto (una scheda nuova non chiude quella che si sta leggendo)
    if (car.intera === k && (k === "cruscotto" || !lista.length)) chiudiStrato("strato-scheda");
  }
  if (sch()) sch().aggiorna();          // timer e tempi dei lavori subito, non al giro dopo
  disponi();
  segnaTagli();                         // «Espandi» subito (allinea toglie le classi messe qui)
}

function suMostra(c) {
  const k = chiaveDi(c);
  car.mostrataDa = performance.now();
  sincronizza(null);
  if (c.tipo === "modulo" && c.stato === "aperto") apriModulo(k);
  if (performance.now() - car.toccato > opzioniCarosello.manoMs) vaiA(k);
}

function pagine() { return [...$("binario").children].filter((e) => !e.hidden); }

function vaiA(k) {
  const bin = $("binario");
  const i = car.ordine.indexOf(k);
  if (i < 0) return;
  car.vista = k;
  const el = pagine()[i];
  if (el) {
    const x = el.offsetLeft - pagine()[0].offsetLeft;
    car.atteso = x;
    if (Math.abs(bin.scrollLeft - x) > 1) bin.scrollTo({ left: x, behavior: "instant" });
  }
  disegnaPunti();
}

// Quale pagina si vede, dallo scorrimento
function suScorri() {
  const bin = $("binario");
  const p = pagine();
  if (!p.length) return;
  // Uno scorrimento che non è quello chiesto da vaiA è di chi guarda: per un po' non lo si sposta
  if (car.atteso === null || Math.abs(bin.scrollLeft - car.atteso) > 2) { car.toccato = performance.now(); car.atteso = null; }
  const passo = p.length > 1 ? p[1].offsetLeft - p[0].offsetLeft : bin.clientWidth;
  const i = Math.max(0, Math.min(p.length - 1, Math.round(bin.scrollLeft / Math.max(1, passo))));
  if (car.ordine[i] && car.ordine[i] !== car.vista) {
    car.vista = car.ordine[i];
    disegnaPunti();
  }
}

function disegnaPunti() {
  const box = $("punti");
  const n = car.ordine.length;
  const i = Math.max(0, car.ordine.indexOf(car.vista));
  if (box.querySelectorAll("i").length !== n) {
    box.querySelectorAll("i").forEach((x) => x.remove());
    for (let j = 0; j < n; j++) box.append(document.createElement("i"));
  }
  box.querySelectorAll("i").forEach((x, j) => { x.className = j === i ? "qui" : ""; x.setAttribute("aria-hidden", "true"); });
  box.classList.toggle("nascosti", n < 2);
  const c = car.schede[car.vista];
  const nome = car.vista === RISPOSTA ? "risposta" : (c && (sch().NOMI_TIPO[c.tipo] || c.tipo) || "scheda").toLowerCase();
  metti($("punti-testo"), n < 2 ? "" : nome + ", " + (i + 1) + " di " + n);
}

// La dissolvenza in fondo solo dove il testo non ci sta; «Espandi» dove non ci sta (in alto o
// di lato) e sulle schede lunghe per tipo
function segnaTagli() {
  const r = $("risposta-testo");
  if (r) {
    $("risposta").classList.toggle("taglia", r.scrollHeight > r.clientHeight + 1
      && r.scrollTop + r.clientHeight < r.scrollHeight - 2);
    $("risposta").classList.toggle("lunga", !!st.risposta.testo && r.scrollHeight > r.clientHeight + 1);
  }
  for (const e of pagine()) {
    const corpo = e.querySelector(":scope > .corpo");
    if (!corpo) continue;
    e.classList.toggle("taglia", corpo.scrollHeight > corpo.clientHeight + 1
      && corpo.scrollTop + corpo.clientHeight < corpo.scrollHeight - 2);
    const c = car.schede[e.dataset.chiave];
    e.classList.toggle("lunga", !!c && !TIPI_SENZA_INTERA.has(c.tipo) && (TIPI_LUNGHI.has(c.tipo)
      || corpo.scrollHeight > corpo.clientHeight + 1 || corpo.scrollWidth > corpo.clientWidth + 1
      || [...corpo.querySelectorAll("pre, table")].some((x) => x.scrollWidth > x.clientWidth + 1)));
  }
}

// ───────────────────────────── una scheda a schermo intero (06/10) ─────────────────────────────
// Sul telefono il riquadro del carosello è piccolo: il cruscotto, il codice di un lavoro, un
// documento non si leggevano. Un tocco sulla scheda (o «Espandi») la apre in uno strato sopra
// la vista, con il testo grande, le tabelle e il codice che scorrono di lato nel loro riquadro.
// La scheda aperta si aggiorna al suo posto (stessa chiave: il cruscotto ogni 30 s, un lavoro in
// diretta) senza perdere il punto in cui si legge; le schede nuove vanno nel carosello. Si chiude
// con «Chiudi», Esc o il gesto indietro (una voce nella cronologia del browser).
function costruisciIntera(k) {
  let s;
  if (k === RISPOSTA) {
    s = document.createElement("article");
    s.className = "scheda tipo-risposta";
    const et = document.createElement("div");
    et.className = "etichetta";
    et.textContent = "Risposta · " + fmtOra.format(new Date(st.risposta.ora || Date.now()));
    const t = document.createElement("div");
    t.className = "corpo";
    const p = document.createElement("div");
    p.className = "testo-lungo";
    p.textContent = st.risposta.testo;
    t.append(p);
    s.append(et, t);
  } else {
    const c = car.schede[k];
    if (!c) return null;
    s = sch().costruisci(c);
  }
  s.dataset.tipo = k === RISPOSTA ? "risposta" : car.schede[k].tipo;
  return s;
}

function titoloIntera(k) {
  if (k === RISPOSTA) return "Risposta";
  const c = car.schede[k];
  return (c && (c.titolo || sch().NOMI_TIPO[c.tipo] || c.tipo)) || "Scheda";
}

// Disegna (o allinea al suo posto) la scheda aperta: stessi elementi, stesso scorrimento
function disegnaIntera() {
  const k = car.intera;
  if (k === null) return;
  const posto = $("intera-posto");
  const nuova = costruisciIntera(k);
  if (!nuova) return;                    // uscita dalla cronologia: resta l'ultimo contenuto
  metti($("intera-titolo"), titoloIntera(k));
  const vecchia = posto.firstElementChild;
  if (vecchia && vecchia.dataset.chiave === nuova.dataset.chiave && vecchia.dataset.tipo === nuova.dataset.tipo) {
    const seguite = [...vecchia.querySelectorAll("pre[data-segui]")].map((p) => p.scrollHeight - p.scrollTop - p.clientHeight < 24);
    sch().allinea(vecchia, nuova);
    vecchia.querySelectorAll("pre[data-segui]").forEach((p, i) => { if (seguite[i] !== false) p.scrollTop = p.scrollHeight; });
  } else {
    posto.replaceChildren(nuova);
    posto.scrollTop = 0;
    nuova.querySelectorAll("pre[data-segui]").forEach((p) => { p.scrollTop = p.scrollHeight; });
  }
  if (sch()) sch().aggiorna();
}

function apriIntera(k) {
  if (k !== RISPOSTA && (!car.schede[k] || TIPI_SENZA_INTERA.has(car.schede[k].tipo))) return false;
  if (k === RISPOSTA && !st.risposta.testo) return false;
  const gia = !$("strato-scheda").hidden;
  if (car.intera !== k) $("intera-posto").replaceChildren();
  car.intera = k;
  disegnaIntera();
  apriStrato("strato-scheda");
  // Il gesto indietro (Android, Edge) chiude lo strato invece di lasciare la pagina
  if (!gia) { try { history.pushState({ calliopeStrato: "scheda" }, ""); } catch (e) { /* niente */ } }
  return true;
}

// Chiude lo strato e toglie la sua voce dalla cronologia del browser (se è ancora in cima)
function chiudiIntera() {
  if ($("strato-scheda").hidden) return;
  chiudiStrato("strato-scheda");
  if (history.state && history.state.calliopeStrato === "scheda") { try { history.back(); } catch (e) { /* niente */ } }
}

// Un tocco su una scheda del carosello la apre (non sui suoi pulsanti, né sulla risposta, che
// ha «Espandi» quando è lunga, né su modulo e gioco)
function suToccoCarosello(ev) {
  const t = ev.target;
  if (!t.closest) return;
  const pag = t.closest("#binario > [data-chiave]");
  if (!pag) return;
  if (t.closest(".espandi")) { apriIntera(pag.dataset.chiave); return; }
  if (pag.dataset.chiave === RISPOSTA) return;
  if (t.closest("button, a, input, textarea, select, summary, label, iframe")) return;
  const sel = window.getSelection && window.getSelection();
  if (sel && !sel.isCollapsed && pag.contains(sel.anchorNode)) return;   // si stava selezionando
  apriIntera(pag.dataset.chiave);
}

// ───────────────────────────── strati: menu, modulo, scrivi ─────────────────────────────
let ritornoFuoco = null;
const STRATI = ["strato-scheda", "strato-modulo", "strato-scrivi", "menu"];
function apriStrato(id, fuoco) {
  for (const s of STRATI) {
    if (s === id || $(s).hidden) continue;
    if (s === "strato-scheda") chiudiIntera(); else $(s).hidden = true;
  }
  const s = $(id);
  if (s.hidden) ritornoFuoco = document.activeElement;
  s.hidden = false;
  const f = fuoco ? $(fuoco) : s.querySelector(".chiudi");
  if (f) { try { f.focus({ preventScroll: true }); } catch (e) { f.focus(); } }
}

function chiudiStrato(id) {
  const s = $(id);
  if (s.hidden) return;
  s.hidden = true;
  if (id === "strato-modulo") { car.modulo = null; car.moduloFirma = ""; $("modulo-posto").replaceChildren(); }
  if (id === "strato-scheda") { car.intera = null; $("intera-posto").replaceChildren(); }
  const r = ritornoFuoco;
  ritornoFuoco = null;
  if (r && document.contains(r) && !r.closest("[hidden]")) { try { r.focus({ preventScroll: true }); } catch (e) { /* niente */ } }
}

// Il modulo intero (campi, controlli, «Invia»: quello di schermo.js) nel suo strato
function apriModulo(k) {
  const c = car.schede[k];
  if (!c) return;
  car.modulo = k;
  car.moduloFirma = "";
  aggiornaModulo(c);
  apriStrato("strato-modulo");
}

let chiudiModuloTimer = null;
function aggiornaModulo(c) {
  const firma = JSON.stringify(c);
  if (firma === car.moduloFirma) return;
  const posto = $("modulo-posto");
  // Mentre si scrive non si ricostruisce (le bozze restano in schermo.js comunque), salvo che
  // il modulo si chiuda o torni con gli errori del server
  if (car.moduloFirma && c.stato === "aperto" && posto.contains(document.activeElement) && !c.campi.some((x) => x.errore)) return;
  car.moduloFirma = firma;
  posto.replaceChildren(sch().costruisci(c));
  clearTimeout(chiudiModuloTimer);
  if (c.stato !== "aperto") {
    // Inviato o chiuso da Calliope: lo strato si toglie da solo, la scheda resta nel carosello
    chiudiModuloTimer = setTimeout(() => { if (car.modulo === chiaveDi(c)) chiudiStrato("strato-modulo"); }, 2500);
  }
}

function suScrivi(det) {
  const b = $("scrivi-apri");
  b.hidden = !det.attiva;
  b.closest(".vista-fondo").classList.toggle("solo-mic", !det.attiva);
  // «Allega» (foto o file, 05/10): solo da un telefono personale (il server rifiuta le altre)
  const f = $("foto-apri");
  f.hidden = !(det.attiva && det.personale);
  b.closest(".vista-fondo").classList.toggle("con-foto", !f.hidden);
  if (!det.attiva) chiudiStrato("strato-scrivi");
  // Senza una conversazione a voce (05/10) il tasto resta, attenuato: apre la casella spenta,
  // che dice la parola da dire; tutto si riaccende da solo appena la conversazione comincia
  const spento = !!det.attiva && !det.abilitata;
  b.classList.toggle("spento", spento);
  f.classList.toggle("spento", spento);           // «Foto» come «Scrivi»
  if (spento) {
    b.setAttribute("aria-disabled", "true");
    b.title = "Di' «" + (det.parola || "Calliope") + "» per scrivermi";
  } else {
    b.removeAttribute("aria-disabled");
    b.removeAttribute("title");
  }
}

// «Allega»: la casella di scrittura si apre con la scelta del file, nello stesso tocco (iOS
// apre fotocamera o libreria solo dentro il gesto); la domanda si scrive lì o si dice a voce
function apriFoto() {
  if (!$("scrivi")) return;
  // Senza conversazione (05/10): si apre la casella spenta, che dice la parola da dire
  if ($("foto-apri").classList.contains("spento")) { apriStrato("strato-scrivi", null); return; }
  apriStrato("strato-scrivi", null);
  const sc = window.calliopeSchermo;
  if (!sc || !sc.foto || !sc.foto()) chiudiStrato("strato-scrivi");
}

function apriScrivi() {
  if (!$("scrivi")) return;
  apriStrato("strato-scrivi", "scrivi-testo");
}

// ───────────────────────────── rete ─────────────────────────────
function urlWs(percorso) {
  return (location.protocol === "https:" ? "wss://" : "ws://") + location.host + percorso;
}

function manda(o) {
  const ws = st.ws;
  if (!ws || ws.readyState !== 1) return false;
  ws.send(JSON.stringify(o));
  return true;
}

function mandaAudio(id, blocchi) {
  const ws = st.ws;
  if (!ws || ws.readyState !== 1 || !blocchi.length) return;
  const n = blocchi.reduce((a, b) => a + b.length, 0);
  const buf = new ArrayBuffer(5 + n * 2);
  const dv = new DataView(buf);
  dv.setUint8(0, 65);                 // «A»
  dv.setUint32(1, id >>> 0, false);
  let o = 5;
  for (const b of blocchi) {
    for (let i = 0; i < b.length; i++) {
      const v = Math.max(-1, Math.min(1, b[i]));
      dv.setInt16(o, Math.round(v * 32767), true);
      o += 2;
    }
  }
  ws.send(buf);
  st.inviato += n * 2;
}

// L'audio di una frase verso il server: subito se si conosce già l'id dell'ascolto,
// altrimenti in attesa (tocco prima che il telefono fosse quello attivo)
class Uscita {
  constructor() { this.lid = null; this.buf = []; this.coda = null; }
  audio(blocchi) { if (this.lid !== null) mandaAudio(this.lid, blocchi); else this.buf.push(...blocchi); }
  lega(id) {
    this.lid = id;
    if (this.buf.length) { mandaAudio(id, this.buf); this.buf = []; }
    if (this.coda) { manda(Object.assign({}, this.coda, { id })); this.coda = null; }
  }
  fine(msg) { if (this.lid !== null) manda(Object.assign({}, msg, { id: this.lid })); else this.coda = msg; }
}

// ───────────────────────────── abbinamento ─────────────────────────────
function mostraVista() {
  $("abbina-tel").hidden = true;
  $("vista").hidden = false;
}

function mostraAbbinamento() {
  for (const s of STRATI) chiudiStrato(s);
  $("vista").hidden = true;
  $("abbina-tel").hidden = false;
  statoTel("attesa", "da abbinare");
  $("tel-nome").value = leggi(CHIAVE_NOME) || "";
}

// Abbinamento che riprende (03/10): per dire il codice la persona esce dal browser, e iOS
// sospende la pagina e chiude il WebSocket. Il server manda con il codice una «ripresa»
// segreta, che resta qui (localStorage) insieme al codice: tornando in primo piano la pagina
// la presenta su una connessione nuova e ritrova lo stesso codice, o il token se nel
// frattempo è stata abbinata (consegnato una volta sola). Vale quanto il codice.
const CHIAVE_ABBINA = "calliope.telefono.abbinamento";
let abbinaWs = null;
let abbinaTentativi = 0;

function abbinamentoSalvato() {
  try {
    const a = JSON.parse(leggi(CHIAVE_ABBINA) || "null");
    if (a && a.ripresa && a.codice && Number(a.scade) > Date.now()) return a;
  } catch (e) { /* niente */ }
  if (leggi(CHIAVE_ABBINA)) scrivi(CHIAVE_ABBINA, null);
  return null;
}

function mostraCodice(c, scadeS, nome) {
  c = String(c);
  $("tel-codice").hidden = false;
  $("tel-codice-cifre").textContent = c.slice(0, 3) + " " + c.slice(3);
  $("tel-comando").textContent = "calliope satellite --abbina " + c + " --stanza telefono"
    + (nome ? " --personale " + nome : "");
  $("tel-scade").textContent = "Il codice vale ancora " + Math.max(1, Math.round((scadeS || 600) / 60)) + " minuti."
    + (nome ? " Con --personale le schede personali di " + nome + " arrivano qui." : "");
}

function apriAbbina(primo, nome) {
  if (abbinaWs) { const v = abbinaWs; abbinaWs = null; try { v.close(); } catch (e) { /* niente */ } }
  const ws = new WebSocket(urlWs("/telefono/ws/abbina"));
  abbinaWs = ws;
  let ripresa = primo ? null : (abbinamentoSalvato() || {}).ripresa;
  ws.onopen = () => {
    statoTel("attesa", primo ? "chiedo il codice…" : "riprendo l'abbinamento…");
    ws.send(JSON.stringify(primo
      ? { tipo: "abbina", versione: VERSIONE, nome: "telefono", personale: nome || null, ripresa: true }
      : { tipo: "riprendi", versione: VERSIONE, ripresa }));
  };
  ws.onmessage = (ev) => {
    if (abbinaWs !== ws) return;
    let m = {};
    try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (m.tipo === "codice") {
      abbinaTentativi = 0;
      const vecchio = abbinamentoSalvato();
      if (m.ripresa) {
        ripresa = m.ripresa;
        scrivi(CHIAVE_ABBINA, JSON.stringify({ ripresa: m.ripresa, codice: String(m.codice), nome: nome || "",
          scade: Date.now() + 1000 * Number(m.scade_s || 600) }));
      }
      mostraCodice(m.codice, m.scade_s, primo ? nome : (vecchio && vecchio.nome));
      statoTel("attesa", "aspetto l'abbinamento");
    } else if (m.tipo === "abbinato") {
      st.token = m.token;
      scrivi(CHIAVE_TOKEN, m.token);
      scrivi(CHIAVE_ABBINA, null);
      // Salvato: la ripresa non serve più (il server la cancella)
      try { ws.send(JSON.stringify({ tipo: "ricevuto" })); } catch (e) { /* niente */ }
      $("abbina-tel").hidden = true;
      $("tel-codice").hidden = true;
      abbinaWs = null;
      st.tentativi = 0;
      connetti();
    } else if (m.tipo === "scaduto") {
      scrivi(CHIAVE_ABBINA, null);
      abbinaWs = null;
      $("tel-codice").hidden = true;
      statoTel("attesa", "codice scaduto: chiedine un altro");
    } else if (m.tipo === "errore") {
      avvisoAbbina(m.motivo);
    }
  };
  ws.onerror = () => { if (abbinaWs === ws) statoTel("giu", "Calliope non risponde"); };
  ws.onclose = (ev) => {
    if (abbinaWs !== ws) return;
    abbinaWs = null;
    if (ev.code === 1000 || ev.code === 4503) return;
    if (abbinamentoSalvato()) {
      // Connessione persa con un codice in attesa: si riprende subito al ritorno in primo
      // piano, oppure dopo un po' se la pagina è visibile
      statoTel("attesa", "collegamento perso: riprendo…");
      const attesa = ATTESE_MS[Math.min(abbinaTentativi++, ATTESE_MS.length - 1)];
      setTimeout(() => {
        if (!abbinaWs && !st.token && document.visibilityState === "visible" && abbinamentoSalvato()) apriAbbina(false);
      }, attesa);
    } else {
      statoTel("giu", "Calliope non risponde: riprova");
    }
  };
}

function chiediCodice() {
  const nome = $("tel-nome").value.trim().slice(0, 40);
  scrivi(CHIAVE_NOME, nome || null);
  scrivi(CHIAVE_ABBINA, null);
  abbinaTentativi = 0;
  apriAbbina(true, nome);
}

// Ritorno in primo piano o pagina riaperta con un codice in attesa
function riprendiAbbinamento() {
  if (st.token || !abbinamentoSalvato()) return false;
  // Aperta per il browser, ma dopo una sospensione può essere morta: se ne apre una nuova
  if (abbinaWs && abbinaWs.readyState <= 1 && !sospesoAbbastanza()) return true;
  abbinaTentativi = 0;
  apriAbbina(false);
  return true;
}

function avvisoAbbina(testo) {
  statoTel("giu", "voce non disponibile");
  avviso(testo);
}

// ───────────────────────────── sessione ─────────────────────────────
function connetti(ripresa) {
  if (!st.token) { mostraAbbinamento(); return; }
  mostraVista();
  if (st.ws) { try { st.ws.close(); } catch (e) { /* niente */ } }
  statoTel("attesa", ripresa ? "riprendo il collegamento…" : st.tentativi ? "riconnessione…" : "collegamento…");
  const ws = new WebSocket(urlWs("/telefono/ws/sessione"));
  ws.binaryType = "arraybuffer";
  st.ws = ws;
  st.sostituito = false;
  ws.onopen = () => {
    ws.send(JSON.stringify({ tipo: "ciao", versione: VERSIONE, token: st.token, primo: false,
      nome: "telefono", esecutore: null, modalita: true }));
  };
  ws.onmessage = (ev) => {
    if (ws !== st.ws) return;
    if (typeof ev.data !== "string") { binario(new Uint8Array(ev.data)); return; }
    let m = {};
    try { m = JSON.parse(ev.data); } catch (e) { return; }
    comando(m);
  };
  ws.onclose = (ev) => {
    if (ws !== st.ws) return;
    st.collegato = false;
    st.attivo = false;
    fineSessione();
    if (ev.code === 4401) {                 // revocato o mai abbinato qui
      st.token = null;
      scrivi(CHIAVE_TOKEN, null);
      if (window.calliopeSchermo) window.calliopeSchermo.dimentica();
      avviso("Questo telefono non è più abbinato: chiedi un codice nuovo.");
      mostraAbbinamento();
      return;
    }
    if (ev.code === 4409) {                 // un'altra scheda (o lo stesso telefono, di nuovo)
      st.sostituito = true;
      statoTel("giu", "aperta altrove");
      avviso("Calliope è aperta in un'altra scheda o finestra: tocca «Parla» per riprenderla qui.");
      return;
    }
    if (ev.code === 4503) {
      statoTel("giu", "voce non disponibile");
      return;
    }
    const attesa = ATTESE_MS[Math.min(st.tentativi, ATTESE_MS.length - 1)];
    st.tentativi++;
    statoTel("giu", "Calliope non risponde · riprovo");
    setTimeout(() => { if (st.ws === ws) connetti(); }, attesa);
  };
}

function fineSessione() {
  // Connessione caduta: niente frasi a metà, niente ascolti in sospeso
  player.ferma(Infinity);
  fermaCorsa();
  st.L = null;
  st.W = null;
  st.pensa = false;
}

function binario(b) {
  if (b.length < 5) return;
  const dv = new DataView(b.buffer, b.byteOffset, b.length);
  const tipo = String.fromCharCode(b[0]);
  const id = dv.getUint32(1, false);
  if (tipo === "T") player.pezzo(id, b.subarray(5));
}

function comando(m) {
  switch (m.tipo) {
    case "benvenuto": benvenuto(m); break;
    case "modalita": suModalita(m); break;
    case "attivo":
      st.attivo = !!m.attivo;
      st.altro = m.altro || null;
      if (!st.attivo) { fermaCorsa(); st.L = null; }
      break;
    case "ascolta": suAscolta(m); break;
    case "sveglia": suSveglia(m); break;
    case "veglia": suVeglia(m); break;
    case "fine_veglia": suFineVeglia(m); break;
    case "esito_voce": break;
    case "frase":
      st.pensa = false;
      ricordaFrase(Number(m.turno), String(m.testo || ""));
      player.frase(Number(m.turno), Number(m.id), String(m.testo || ""), Number(m.rate), Number(m.byte));
      break;
    case "fine_turno": fineTurno(Number(m.id)); break;
    case "ferma": player.ferma(Number(m.turno || 0)); st.pensa = false; break;
    case "schermo":
      if (m.token) scrivi("calliope.telefono.schermo", m.token);
      if (window.calliopeSchermo) window.calliopeSchermo.usa(m.token || window.calliopeSchermo.token());
      break;
    case "errore": avviso(String(m.motivo || "")); break;
    case "pc_richiesta": manda({ tipo: "pc_esito", id: m.id, errore: "il telefono non controlla il PC" }); break;
    case "file_richiesta": manda({ tipo: "file_dati", id: m.id, ok: false, errore: "il telefono non manda file" }); break;
    case "file": manda({ tipo: "file_esito", id: m.id, ok: false, errore: "il telefono non riceve documenti" }); break;
    default: break;
  }
}

// Parole che svegliano e suoni (benvenuto, e il messaggio «modalita» quando chi amministra
// cambia la modalità a voce, 05/10)
function applicaModalita(m) {
  for (const [k, v] of Object.entries(m.parametri || {})) if (k in PARAMETRI) param[k] = v;
  // Le parole che svegliano (04/10): mentre Calliope le dice, la wake word si ignora
  const parola = String(param.wake_word || param.name || "Calliope");
  player.nomi = [parola, ...(param.wake_anche_nome && param.name ? [String(param.name)] : [])]
    .map((n) => n.toLowerCase());
  TESTI.dorme = "Dormo · di' «" + parola + "»";
  // Suoni di inizio e fine ascolto (modalità startrek): li suona il telefono, subito
  suoni = {};
  if (m.suoni && m.suoni.rate) {
    for (const k of ["inizio", "fine"]) {
      try {
        if (typeof m.suoni[k] === "string") {
          const b = atob(m.suoni[k]);
          const u = new Uint8Array(b.length);
          for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i);
          suoni[k] = { pcm: u, rate: Number(m.suoni.rate) };
        }
      } catch (e) { /* suono rotto: niente segnale */ }
    }
  }
}

// La modalità cambiata a voce: parole, suoni e, se sono cambiati, i modelli della wake word
// (gli stessi /telefono/modelli, con la versione nuova nell'URL)
async function suModalita(m) {
  applicaModalita(m);
  const wake = (m.wake_modelli || []).map((x) => x && x.nome).join(",");
  if (wake === st.wakeModelli) return;
  st.wakeModelli = wake;
  if (st.modelli === "pronti" || st.modelli === "errore") {
    st.modelli = null;
    await preparaModelli();
  }
}

async function benvenuto(m) {
  applicaModalita(m);
  st.wakeModelli = (m.wake_modelli || []).map((x) => x && x.nome).join(",");
  st.satellite = m.satellite || {};
  st.collegato = true;
  st.tentativi = 0;
  player.nuovaSessione();
  metti($("luogo"), st.satellite.nome || "—");
  statoTel("ok", "collegata");
  manda({ tipo: "pronto", eco: null });
  if (m.schermi) manda({ tipo: "schermo", token: (window.calliopeSchermo && window.calliopeSchermo.token()) || "" });
  preparaModelli();
  if (st.mic) manda({ tipo: "prendi" });
}

// ───────────────────────────── modelli ─────────────────────────────
async function scaricaInCache(url, intestazioni) {
  let cache = null;
  try { cache = await caches.open("calliope-telefono-modelli"); } catch (e) { cache = null; }
  if (cache) {
    const r = await cache.match(url);
    if (r) return new Uint8Array(await r.arrayBuffer());
  }
  const r = await fetch(url, { headers: intestazioni || {}, cache: "no-store" });
  if (!r.ok) throw new Error(url.split("?")[0] + ": " + r.status);
  if (cache) { try { await cache.put(url, r.clone()); } catch (e) { /* spazio pieno */ } }
  return new Uint8Array(await r.arrayBuffer());
}

async function pulisciCache(tenere) {
  try {
    const cache = await caches.open("calliope-telefono-modelli");
    for (const req of await cache.keys()) {
      const u = new URL(req.url);
      if (!tenere.includes(u.pathname + u.search)) await cache.delete(req);
    }
  } catch (e) { /* niente cache: niente da pulire */ }
}

async function preparaModelli() {
  if (st.modelli === "carico" || st.modelli === "pronti") return;
  st.modelli = "carico";
  const t0 = performance.now();
  try {
    const s = await (await fetch("/telefono/api/stato", { cache: "no-store" })).json();
    if (!Object.values(s.ort || {}).every(Boolean)) throw new Error("manca onnxruntime-web sul server");
    const v = s.versioni || {};
    const urlWasm = "/telefono/ort/ort-wasm-simd-threaded.wasm?v=" + s.ort_versione;
    const nomi = ["vad", "melspectrogram", "embedding_model", "calliope"];
    // Il classificatore del nome accanto a quello della parola della modalità (05/10)
    if (s.modelli && s.modelli.nome) nomi.push("nome");
    const urls = nomi.map((n) => "/telefono/modelli/" + n + ".onnx?v=" + (v[n] || "0"));
    const wasm = await scaricaInCache(urlWasm);
    await caricaOrt(wasm);
    const auth = { Authorization: "Bearer " + st.token };
    const dati = [];
    for (const u of urls) dati.push(await scaricaInCache(u, auth));
    pulisciCache([urlWasm, ...urls]);
    ascolto.vad = new Vad(await sessione(dati[0]));
    if (s.modelli && s.modelli.calliope && s.modelli.melspectrogram && s.modelli.embedding_model) {
      const clf = [await sessione(dati[3])];
      if (dati[4]) clf.push(await sessione(dati[4]));
      const w = new WakeWord(await sessione(dati[1]), await sessione(dati[2]), clf);
      await w.prepara();
      ascolto.wake = w;
    }
    st.modelli = "pronti";
    st.tempoModelli = Math.round(performance.now() - t0);
    if ((st.micVoluto || st.micChiesto) && !st.mic) {
      // Il tocco arrivato mentre scaricavo i modelli non apre il microfono (serve un gesto
      // nuovo per audio e schermo acceso): lo dico, invece di lasciare «Preparo…» (04/10)
      avviso(st.micChiesto ? "Wake word pronta: tocca di nuovo «Microfono acceso»."
        : "Il microfono era acceso: toccalo per riaccenderlo.");
    }
    st.micChiesto = false;
  } catch (e) {
    st.modelli = "errore";
    st.erroreModelli = String(e && e.message || e);
    avviso("Wake word non disponibile (" + st.erroreModelli + "): «Parla» funziona, il microfono acceso no.");
  }
}

// ───────────────────────────── microfono ─────────────────────────────
// Ordine voluto: sessione audio → getUserMedia → contesto del microfono alla frequenza della
// traccia. Il contesto nasce quando l'hardware ha già la sua frequenza di registrazione.
async function apriMic(vincoli) {
  if (mic.stream) return true;
  player.sblocca();                      // la voce di Calliope: nel gesto, senza aspettare
  try {
    if (navigator.audioSession) navigator.audioSession.type = "play-and-record";
  } catch (e) { /* Safari < 17 */ }
  const v = Object.assign({}, VINCOLI, vincoli || {});
  try {
    mic.stream = await navigator.mediaDevices.getUserMedia({ audio: Object.assign({ channelCount: 1 }, v) });
  } catch (e) {
    avviso("Non posso usare il microfono (" + (e && e.name || e) + "): permettilo nelle impostazioni del browser.");
    return false;
  }
  mic.vincoli = v;
  mic.ricostruito = 0;
  mic.motivo = "";
  const t = mic.stream.getAudioTracks()[0];
  mic.traccia = impostazioniTraccia(t);
  try {
    await creaContesto(mic.traccia.sampleRate || null, true);
  } catch (e) {
    chiudiMic();
    avviso("Non posso leggere il microfono (" + (e && e.message || e) + ").");
    return false;
  }
  mic.stream.getAudioTracks().forEach((x) => { x.onended = () => micSpento("il microfono si è fermato"); });
  return true;
}

function impostazioniTraccia(t) {
  let s = {};
  try { s = (t && t.getSettings) ? t.getSettings() : {}; } catch (e) { s = {}; }
  const out = {};
  for (const k of ["sampleRate", "channelCount", "sampleSize", "echoCancellation", "noiseSuppression",
    "autoGainControl", "latency", "deviceId", "groupId"]) {
    if (s[k] !== undefined) out[k] = (k === "deviceId" || k === "groupId") ? String(s[k]).slice(0, 8) : s[k];
  }
  if (t) out.etichetta = String(t.label || "").slice(0, 60);
  return out;
}

function chiudiContesto() {
  for (const n of [mic.sorgente, mic.nodo, mic.zero]) { try { if (n) n.disconnect(); } catch (e) { /* niente */ } }
  if (mic.nodo) mic.nodo.port.onmessage = null;
  if (mic.ctx) { try { mic.ctx.close(); } catch (e) { /* già chiuso */ } }
  mic.ctx = mic.sorgente = mic.nodo = mic.zero = null;
}

// iOS (iPhone e iPad): tutti i browser, Edge e Chrome compresi, usano WebKit. Lì la cattura
// passa dall'unità VoiceProcessingIO, che può portare l'hardware a 24 o 16 kHz: un contesto
// nato prima (o forzato a un'altra frequenza) legge il microfono al ritmo sbagliato.
const IOS = /iP(hone|ad|od)/.test(navigator.userAgent)
  || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

// Il contesto del microfono nasce dopo getUserMedia. Su iOS senza frequenza imposta: prende
// quella dell'hardware in registrazione, l'unica che WebKit legge bene. Altrove alla frequenza
// della traccia se il browser la dice. Se contesto e traccia non coincidono (fuori da iOS) lo
// si rifà una volta alla frequenza della traccia, con un avviso.
async function creaContesto(rateTraccia, primo) {
  chiudiContesto();
  const C = window.AudioContext || window.webkitAudioContext;
  const voluto = (primo && opzioniMic.forzaRate) || (IOS ? null : rateTraccia) || null;
  let ctx;
  try {
    ctx = voluto ? new C({ latencyHint: "interactive", sampleRate: voluto }) : new C({ latencyHint: "interactive" });
  } catch (e) {
    ctx = new C({ latencyHint: "interactive" });       // frequenza non ammessa: quella del browser
  }
  mic.ctx = ctx;
  if (ctx.state !== "running") { try { await ctx.resume(); } catch (e) { /* lo dirà il ritmo */ } }
  if (ctx.state !== "running") avviso("Il browser tiene fermo il microfono: tocca di nuovo «Parla».");
  await ctx.audioWorklet.addModule("/telefono/microfono.js");
  if (mic.ctx !== ctx) throw new Error("microfono chiuso");
  mic.sorgente = ctx.createMediaStreamSource(mic.stream);
  mic.nodo = new AudioWorkletNode(ctx, "calliope-microfono", { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1] });
  mic.zero = ctx.createGain();
  mic.zero.gain.value = 0;
  mic.sorgente.connect(mic.nodo);
  mic.nodo.connect(mic.zero);
  mic.zero.connect(ctx.destination);
  mic.rate = ctx.sampleRate;
  mic.conti = null;
  mic.seq = -1;
  mic.orologio = null;
  mic.ritmo = null;
  mic.fuoriRitmo = 0;
  mic.nodo.port.onmessage = suMessaggioMic;
  const diversa = rateTraccia && Math.abs(ctx.sampleRate - rateTraccia) > 1;
  if (diversa && IOS) {
    // Su iOS vale l'hardware (il contesto senza frequenza imposta): lo si annota e basta
    mic.motivo = "iOS: contesto " + ctx.sampleRate + " Hz, traccia " + rateTraccia + " Hz";
  } else if (diversa && mic.ricostruito < 1) {
    mic.ricostruito++;
    mic.motivo = "frequenza del contesto " + ctx.sampleRate + " Hz, della traccia " + rateTraccia + " Hz";
    console.warn("[microfono] " + mic.motivo + ": rifaccio il contesto");
    return creaContesto(rateTraccia, false);
  }
  if (IOS) allineaRiproduzione(ctx.sampleRate);    // lì il contesto del microfono = l'hardware
  if (diversa && !IOS) {
    avviso("Il microfono registra a " + rateTraccia + " Hz ma il browser lo legge a " + ctx.sampleRate
      + " Hz: la voce potrebbe arrivare storpiata. Prova «Prova il microfono» nelle impostazioni (in alto a destra).");
  }
  return ctx;
}

function suMessaggioMic(ev) {
  const d = ev.data || {};
  if (d.frame) {
    if (mic.seq >= 0 && d.n !== mic.seq + 1) {
      if (d.n > mic.seq + 1) mic.persi += d.n - mic.seq - 1; else mic.fuoriOrdine++;
    }
    mic.seq = d.n;
    mic.blocchi++;
    const g = mic.diag;
    if (g && g.inizio && d.n >= g.inizio.n && (!g.fine || d.n < g.fine.n)) g.uscita.push(d.frame);
    ascolto.push(d.frame);
    return;
  }
  if (d.tipo === "conti") { mic.conti = d; controllaRitmo(); return; }
  if (d.tipo === "grezzo") { if (mic.diag) mic.diag.grezzo.push(d.dati); return; }
  if (d.tipo === "marca") { if (mic.diag) mic.diag[d.inizio ? "inizio" : "fine"] = d; return; }
}

// L'orologio del contesto contro quello vero: se l'hardware gira a una frequenza diversa da
// quella che il contesto crede, l'audio scorre al ritmo sbagliato (×0,33, ×1,5…) e la voce
// arriva al server accelerata o rallentata. Si misura su finestre di 2,5 s.
function controllaRitmo() {
  const ctx = mic.ctx;
  if (!ctx || ctx.state !== "running") return;
  const ora = performance.now();
  const t = ctx.currentTime;
  if (!mic.orologio) { mic.orologio = { t, ora, scarta: true }; return; }
  const dt = ora - mic.orologio.ora;
  if (dt < RITMO_FINESTRA_MS) return;
  const r = (t - mic.orologio.t) * 1000 / dt;
  const primo = mic.orologio.scarta;          // la prima finestra comprende l'avvio: non conta
  mic.orologio = { t, ora, scarta: false };
  if (primo) return;
  mic.ritmo = Math.round(r * 1000) / 1000;
  if (Math.abs(r - 1) <= RITMO_TOLLERANZA) { mic.fuoriRitmo = 0; return; }
  mic.fuoriRitmo++;
  if (mic.fuoriRitmo < 2 || mic.diag) return;
  const testo = "×" + r.toFixed(2).replace(".", ",");
  if (mic.ricostruito < 2) {
    mic.ricostruito = 2;
    mic.motivo = "ritmo del microfono " + testo;
    console.warn("[microfono] " + mic.motivo + ": rifaccio il contesto");
    creaContesto(null, false).catch(() => {});
    return;
  }
  avviso("Il microfono arriva al ritmo sbagliato (" + testo + "): la voce non si capirà. "
    + "Usa «Prova il microfono» nelle impostazioni (in alto a destra) e manda il risultato a chi amministra.");
}

// Il contesto della voce di Calliope nasce al primo tocco, prima della registrazione: se
// l'hardware ha cambiato frequenza (iOS), a riproduzione ferma lo si rifà alla frequenza
// nuova. Durante la cattura WebKit lascia partire l'audio anche senza un gesto.
function allineaRiproduzione(rate) {
  const p = player.ctx;
  if (!p || !rate || Math.abs(p.sampleRate - rate) <= 1 || player.inCorso()) return;
  console.warn("[voce] contesto della riproduzione a " + p.sampleRate + " Hz, hardware a " + rate + " Hz: lo rifaccio");
  player.rifai();
  player.sblocca();
}

// La sessione audio resta «play-and-record» dopo il primo uso del microfono: tornare a
// «playback» a ogni frase farebbe cambiare frequenza all'hardware di iOS avanti e indietro,
// sotto i contesti già aperti (la causa della voce storpiata)
function chiudiMic() {
  if (mic.stream) mic.stream.getTracks().forEach((t) => t.stop());
  chiudiContesto();
  mic.stream = null;
}

function micSpento(perche) {
  if (!st.mic) return;
  impostaMic(false);
  avviso("Microfono spento: " + perche + ". Toccalo per riaccenderlo.");
}

async function impostaMic(acceso) {
  if (acceso === st.mic) return;
  if (acceso) {
    if (st.modelli !== "pronti" || !ascolto.wake) {
      if (st.modelli === "carico") st.micChiesto = true;
      avviso(st.modelli === "carico"
        ? "Preparo la wake word (la prima volta scarico circa 20 MB, qualche secondo)…"
        : "La wake word non è pronta: usa «Parla».");
      return;
    }
    if (!(await apriMic())) return;
    st.mic = true;
    st.micDa = performance.now();
    scrivi(CHIAVE_MIC, "1");
    avviso("");
    // Di solito già chiesto nel tocco (impostaMicDaTocco): allora qui non fa niente
    schermo.vuoi(st.tieni);
    manda({ tipo: "prendi" });
    if (st.attivo && st.L && !st.corsa) avviaAscolto(st.L, null);
  } else {
    st.mic = false;
    scrivi(CHIAVE_MIC, null);
    schermo.vuoi(false);
    fermaCorsa();
    if (!st.reg) chiudiMic();
    pianificaLascia();
  }
  disegna();
  disegnaSchermo();
}

// Il tocco sull'interruttore: lo schermo si chiede SUBITO, nel gesto (WebKit vuole il gesto
// in corso per la prima richiesta, e aprire il microfono può durare più di un secondo; prima
// la richiesta partiva dopo, e su iPhone poteva non valere)
async function impostaMicDaTocco(acceso) {
  if (acceso && st.tieni) schermo.vuoi(true);
  await player.sblocca();
  await impostaMic(acceso);
  if (!st.mic) schermo.vuoi(false);
  disegnaSchermo();
}

// ───────────────────────────── ascolto ─────────────────────────────
function fermaCorsa() {
  if (st.corsa) st.corsa.basta = true;
  ascolto.ferma();
}

async function avviaAscolto(L, seme) {
  if (st.corsa) { st.corsa.basta = true; await st.corsa.promessa; }
  const corsa = { tipo: "ascolto", basta: false, parla: false };
  st.corsa = corsa;
  const u = new Uscita();
  u.lega(L.id);
  corsa.promessa = (async () => {
    const r = await ascolto.listen({
      wake: L.wake, fino: L.fino, seme,
      forza: () => { if (st.forza) { st.forza = false; return true; } return false; },
      fine: () => { if (st.rilascio) { st.rilascio = false; return true; } return false; },
      sveglia: () => L.sveglia || st.L !== L,
      basta: () => corsa.basta,
      onInizio: () => { corsa.parla = true; },
      onSveglia: () => suona("inizio"),
      onAudio: (b) => u.audio(b),
      onFine: () => { corsa.parla = false; u.fine({ tipo: "scartata" }); },
    });
    if (st.corsa === corsa) st.corsa = null;
    if (st.L !== L) return;                    // un'altra richiesta l'ha sostituita
    st.L = null;
    if (!r) { manda({ tipo: "nessuna_frase", id: L.id }); return; }
    mandaFine(u, r);
  })();
}

function mandaFine(u, r) {
  st.pensa = true;
  suona("fine");                    // frase presa: il segnale prima della rete
  u.fine({ tipo: "frase_finita", fa_s: Math.round(performance.now() - r.inizio) / 1000,
    woke: !!r.woke, wake_score: Math.round(r.punteggio * 1000) / 1000,
    campioni: r.audio.length * FRAME });
}

function suAscolta(m) {
  clearTimeout(st.lasciaTimer);
  const L = { id: m.id, wake: !!m.wake, sveglia: false,
    fino: m.sveglia_per_s === null || m.sveglia_per_s === undefined ? Infinity
      : performance.now() + Number(m.sveglia_per_s) * 1000 };
  st.L = L;
  st.pensa = false;
  st.attivo = true;              // il server chiede di ascoltare solo al satellite attivo
  const seme = m.seed ? st.semi : null;
  st.semi = null;
  if (st.reg && st.reg.uscita.lid === null) {    // il tocco è arrivato prima della richiesta
    st.reg.uscita.lega(L.id);
    L.preso = true;
    return;
  }
  if (st.mic && st.attivo) { avviaAscolto(L, seme); return; }
  pianificaLascia();
}

function suSveglia(m) {
  const L = st.L;
  if (!L || L.id !== m.id) return;
  L.sveglia = true;
  // Niente in ascolto per questa richiesta (microfono spento): il server può annunciare
  if (!st.corsa && !(st.reg && st.reg.uscita.lid === L.id)) {
    st.L = null;
    manda({ tipo: "nessuna_frase", id: L.id });
  }
}

function suVeglia(m) {
  const W = { id: m.id, basta: false };
  st.W = W;
  st.attivo = true;
  if (!st.mic || !ascolto.wake) return;           // senza microfono si interrompe col tocco
  (async () => {
    if (st.corsa) { st.corsa.basta = true; await st.corsa.promessa; }
    const corsa = { tipo: "veglia", basta: false };
    st.corsa = corsa;
    corsa.promessa = (async () => {
      const seme = await ascolto.veglia({ basta: () => corsa.basta || W.basta, muto: () => player.diceNome() });
      if (st.corsa === corsa) st.corsa = null;
      if (seme) {
        // Subito qui, senza aspettare il server: è questo che tiene il barge-in entro un blocco
        player.ferma();
        st.semi = seme;
        manda({ tipo: "interruzione", id: W.id, motivo: "nome sentito" });
      } else if (st.W === W && !W.inviata) {
        manda({ tipo: "veglia_finita", id: W.id });
      }
      W.inviata = true;
      if (st.W === W) st.W = null;
    })();
  })();
}

function suFineVeglia(m) {
  const W = st.W;
  if (!W || W.id !== m.id) { manda({ tipo: "veglia_finita", id: m.id }); return; }
  W.basta = true;
  if (!st.corsa || st.corsa.tipo !== "veglia") {
    if (!W.inviata) manda({ tipo: "veglia_finita", id: W.id });
    W.inviata = true;
    st.W = null;
  }
}

function fineTurno(id) {
  const t0 = performance.now();
  const giro = () => {
    const d = player.dette();
    if (d !== null || performance.now() - t0 > 120000) {
      manda({ tipo: "turno_finito", id, dette: d || [] });
      return;
    }
    setTimeout(giro, 50);
  };
  giro();
}

// Microfono spento e nessuna conversazione aperta: il posto torna all'altro satellite (il
// portatile), così «Calliope» detto in casa funziona di nuovo
function pianificaLascia() {
  clearTimeout(st.lasciaTimer);
  if (st.mic || st.reg || !st.attivo) return;
  const L = st.L;
  const resto = L && L.wake && isFinite(L.fino) ? L.fino - performance.now() : (L && !L.wake ? Infinity : 0);
  if (!isFinite(resto)) return;
  st.lasciaTimer = setTimeout(() => {
    if (!st.mic && !st.reg && st.attivo && !player.inCorso()) manda({ tipo: "lascia" });
  }, Math.max(0, resto) + 300);
}

// ───────────────────────────── «Parla» ─────────────────────────────
async function tocca() {
  await player.sblocca();
  if (st.diag) return;                               // «Prova il microfono» in corso
  if (st.sostituito) { st.sostituito = false; avviso(""); connetti(); return; }
  if (st.reg) { st.reg.finisci = true; return; }          // secondo tocco: fine della frase
  clearTimeout(st.lasciaTimer);
  if (player.inCorso()) {
    player.ferma();
    if (st.W) {
      st.W.basta = true;
      manda({ tipo: "interruzione", id: st.W.id, motivo: "tocco" });
      st.W.inviata = true;
    }
  }
  if (st.mic) {                       // vivavoce: la frase comincia adesso, senza il nome
    if (!st.attivo) manda({ tipo: "prendi" });
    st.forza = true;
    return;
  }
  const reg = { uscita: new Uscita(), finisci: false };
  st.reg = reg;
  if (st.attivo && st.L && !st.L.preso && !st.corsa) { reg.uscita.lega(st.L.id); st.L.preso = true; }
  else if (!st.attivo) manda({ tipo: "prendi" });
  if (!(await apriMic())) { st.reg = null; return; }
  disegna();
  const r = await ascolto.listen({
    wake: false, fino: Infinity, seme: null,
    forza: () => true, fine: () => reg.finisci || (st.rilascio && !(st.rilascio = false)),
    basta: () => !st.collegato, onAudio: (b) => reg.uscita.audio(b),
  });
  st.reg = null;
  if (!st.mic) chiudiMic();
  if (r) mandaFine(reg.uscita, r);
  else reg.uscita.fine({ tipo: "scartata" });
  if (st.L && reg.uscita.lid === st.L.id) st.L = null;
  disegna();
}

function preparaPulsante(b) {
  let premuto = 0;
  let lungo = false;
  b.addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    premuto = performance.now();
    lungo = false;
    tocca();
  });
  const su = () => {
    if (!premuto) return;
    // Pressione lunga (oltre 0,6 s): lasciando il pulsante la frase finisce
    if (performance.now() - premuto > 600) { lungo = true; st.rilascio = true; }
    premuto = 0;
  };
  b.addEventListener("pointerup", su);
  b.addEventListener("pointercancel", su);
  b.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); tocca(); } });
  b.addEventListener("contextmenu", (ev) => ev.preventDefault());
  return () => lungo;
}

// ───────────────────────────── diagnostica del microfono ─────────────────────────────
// «Prova il microfono» (03/10): due registrazioni da DIAG_S secondi, la prima con le
// correzioni del browser (eco, rumore, guadagno), la seconda senza. Di ognuna si tengono il
// segnale come arriva al worklet (alla frequenza del contesto) e l'uscita a 16 kHz, quella
// che andrebbe a Calliope, con i metadati; tutto va al server (POST con il token del
// telefono, solo se è personale), che salva i WAV e risponde con un riassunto leggibile.
const DIAG_S = 5;
const DIAG_FRASE = "Calliope, che ore sono? Oggi è una bella giornata.";

function concatena(pezzi) {
  const n = pezzi.reduce((a, b) => a + b.length, 0);
  const out = new Float32Array(n);
  let o = 0;
  for (const p of pezzi) { out.set(p, o); o += p.length; }
  return out;
}

function livelli(x) {
  let picco = 0, somma = 0, saturi = 0;
  for (let i = 0; i < x.length; i++) {
    const a = Math.abs(x[i]);
    if (a > picco) picco = a;
    if (a >= 0.999) saturi++;
    somma += x[i] * x[i];
  }
  const db = (v) => v > 0 ? Math.round(200 * Math.log10(v)) / 10 : -120;
  return { picco_db: db(picco), rms_db: db(Math.sqrt(somma / Math.max(1, x.length))), saturi };
}

function diagMostra(righe) {
  const e = $("diag-esito");
  if (!e) return;
  e.hidden = false;
  e.textContent = Array.isArray(righe) ? righe.join("\n") : String(righe);
}

async function registraDiag(vincoli, secondi, etichetta) {
  chiudiMic();
  const t0 = performance.now();
  if (!(await apriMic(vincoli))) throw new Error("microfono non disponibile");
  const apertura = Math.round(performance.now() - t0);
  // Un attimo perché il contesto parta e l'hardware si assesti
  await aspetta(300);
  const ctx = mic.ctx;
  const iniz = { ora: performance.now(), ctx: ctx.currentTime, blocchi: mic.blocchi, persi: mic.persi,
    fuori: mic.fuoriOrdine, conti: Object.assign({}, mic.conti || {}), scartati: ascolto.scartati };
  // Le marche del worklet dicono esattamente quali blocchi fanno parte della registrazione:
  // quelli ancora in coda da prima (la pagina era occupata) non contano
  mic.diag = { grezzo: [], uscita: [], inizio: null, fine: null };
  mic.nodo.port.postMessage({ grezzo: true });
  iniz.ora = performance.now();
  for (let s = secondi; s > 0; s--) {
    diagMostra([etichetta, "Parla adesso: «" + DIAG_FRASE + "»", "… " + s]);
    await aspetta(1000);
  }
  if (mic.nodo) mic.nodo.port.postMessage({ grezzo: false });
  const fine = { ora: performance.now() };
  const d = mic.diag;
  // Gli ultimi blocchi in viaggio: fino alla marca di fine e al blocco prima di lei
  for (let i = 0; i < 40 && !(d.fine && d.inizio && mic.seq >= d.fine.n - 1); i++) await aspetta(50);
  mic.diag = null;
  fine.conti = mic.conti || {};
  const campioni = d.inizio && d.fine ? d.fine.ingresso - d.inizio.ingresso : 0;
  const grezzo = concatena(d.grezzo);
  const uscita = concatena(d.uscita);
  const meta = {
    etichetta,
    vincoli_chiesti: vincoli,
    traccia: mic.traccia,
    rate_contesto: mic.rate,
    stato_contesto: ctx.state,
    latenza_base: ctx.baseLatency || null,
    rate_riproduzione: player.ctx ? player.ctx.sampleRate : null,
    stato_riproduzione: player.ctx ? player.ctx.state : null,
    audio_session: navigator.audioSession ? String(navigator.audioSession.type) : null,
    apertura_ms: apertura,
    ricostruito: mic.ricostruito, motivo_ricostruzione: mic.motivo || null,
    durata_vera_s: (fine.ora - iniz.ora) / 1000,
    durata_contesto_s: campioni / (mic.rate || 1),
    marche: !!(d.inizio && d.fine),
    ritmo: mic.ritmo,
    blocchi: d.uscita.length,
    persi: mic.persi - iniz.persi,
    fuori_ordine: mic.fuoriOrdine - iniz.fuori,
    quanti_zero: (fine.conti.zeri || 0) - (iniz.conti.zeri || 0),
    quanti_doppi: (fine.conti.doppi || 0) - (iniz.conti.doppi || 0),
    quanti: (fine.conti.quanti || 0) - (iniz.conti.quanti || 0),
    vuoti: (fine.conti.vuoti || 0) - (iniz.conti.vuoti || 0),
    scartati_inferenza: ascolto.scartati - iniz.scartati,
    livelli_grezzo: livelli(grezzo),
    livelli_uscita: livelli(uscita),
  };
  chiudiMic();
  return { meta, grezzo, uscita };
}

function int16(x) {
  const out = new Int16Array(x.length);
  for (let i = 0; i < x.length; i++) out[i] = Math.round(Math.max(-1, Math.min(1, x[i])) * 32767);
  return out;
}

async function diagnostica(o) {
  o = o || {};
  if (st.diag) return null;
  if (!st.token) { diagMostra("Prima abbina il telefono."); return null; }
  if (st.reg) { diagMostra("Aspetta che finisca la frase in corso."); return null; }
  st.diag = true;
  const eraMic = st.mic;
  const secondi = Math.max(1, Math.min(8, Number(o.secondi) || DIAG_S));
  const prove = o.prove || [
    { etichetta: "1 di 2 · con le correzioni del browser", vincoli: VINCOLI },
    { etichetta: "2 di 2 · senza correzioni (eco, rumore, guadagno spenti)", vincoli: SENZA_CORREZIONI },
  ];
  try {
    if (st.mic) await impostaMic(false);
    fermaCorsa();
    const fatte = [];
    for (const p of prove) fatte.push(await registraDiag(p.vincoli, secondi, p.etichetta));
    diagMostra("Mando le registrazioni a Calliope…");
    const segmenti = [];
    const dati = [];
    fatte.forEach((f, i) => {
      for (const [tipo, x, rate] of [["grezzo", f.grezzo, f.meta.rate_contesto], ["uscita", f.uscita, SR]]) {
        segmenti.push({ prova: i, tipo, rate, campioni: x.length });
        dati.push(int16(x));
      }
    });
    const meta = {
      versione: 1, ios: IOS, ua: navigator.userAgent.slice(0, 300), piattaforma: (navigator.platform || "").slice(0, 40),
      secondi, frase: DIAG_FRASE, prove: fatte.map((f) => f.meta), segmenti,
      cpu_inferenza: Math.round(1000 * misure.inferenzaMs / Math.max(1, performance.now() - misure.dal)) / 1000,
      modelli: st.modelli,
    };
    const js = new TextEncoder().encode(JSON.stringify(meta));
    const testa = new Uint8Array(8);
    testa.set([67, 68, 71, 49]);            // «CDG1»
    new DataView(testa.buffer).setUint32(4, js.length, false);
    const corpo = new Blob([testa, js, ...dati.map((d) => new Uint8Array(d.buffer))]);
    const r = await fetch("/telefono/api/diagnostica", {
      method: "POST", cache: "no-store", body: corpo,
      headers: { "Content-Type": "application/octet-stream", Authorization: "Bearer " + st.token },
    });
    let esito = {};
    try { esito = await r.json(); } catch (e) { esito = {}; }
    if (!r.ok) {
      diagMostra("Calliope non ha accettato la prova: " + (esito.errore || r.status) + ".");
      return { ok: false, stato: r.status, esito, meta };
    }
    diagMostra(esito.riassunto || ["Fatto."]);
    return { ok: true, esito, meta };
  } catch (e) {
    diagMostra("La prova non è riuscita: " + (e && e.message || e) + ".");
    return { ok: false, errore: String(e && e.message || e) };
  } finally {
    chiudiMic();
    st.diag = false;
    if (eraMic) impostaMic(true);
  }
}

// ───────────────────────────── visibilità ─────────────────────────────
// Quando la pagina è stata nascosta: al ritorno, se è passato più di qualche secondo, il
// WebSocket può sembrare aperto ed essere morto (iOS lo congela), quindi si riapre subito
let nascostaDa = null;
const SOSPESA_MS = 3000;
function sospesoAbbastanza() {
  return nascostaDa !== null && performance.now() - nascostaDa > SOSPESA_MS;
}

function tornaInPrimoPiano() {
  if (st.micVoluto && st.modelli === "pronti" && !st.mic) {
    avviso("Il microfono si è spento quando hai lasciato la pagina: toccalo per riaccenderlo.");
  }
  schermo.riprova();
  if (!st.token) {
    riprendiAbbinamento();
  } else if (!st.ws || st.ws.readyState > 1 || sospesoAbbastanza()) {
    // Subito, senza le attese crescenti della riconnessione
    st.tentativi = 0;
    if (st.ws && st.ws.readyState <= 1) {
      const v = st.ws;
      st.ws = null;
      st.collegato = false;
      fineSessione();
      try { v.close(); } catch (e) { /* niente */ }
    }
    statoTel("attesa", "riprendo il collegamento…");
    connetti(true);
  }
  nascostaDa = null;
}

document.addEventListener("visibilitychange", async () => {
  if (document.visibilityState === "hidden") {
    nascostaDa = performance.now();
    // Il browser spegne comunque il microfono: lo si dice, e il posto torna all'altro satellite
    if (st.mic) {
      st.micVoluto = true;
      impostaMic(false);
      scrivi(CHIAVE_MIC, "1");
    }
  } else {
    tornaInPrimoPiano();
  }
});
// Pagina ripresa dalla cache avanti/indietro (Safari): come un ritorno in primo piano
window.addEventListener("pageshow", (ev) => {
  if (!ev.persisted) return;
  if (nascostaDa === null) nascostaDa = -Infinity;
  tornaInPrimoPiano();
});

// ───────────────────────────── avvio ─────────────────────────────
async function avvio() {
  if (!window.isSecureContext) {
    avviso("Il microfono vuole una pagina sicura (https): apri l'indirizzo https:// di Calliope.");
  }
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/telefono/sw.js", { scope: "/telefono/" }).catch(() => {
      // Con il certificato non fidato (CA di casa non installata) il service worker non
      // parte: la pagina funziona lo stesso, ma non si apre senza rete
    });
  }
  $("tel-chiedi").addEventListener("click", chiediCodice);
  $("microfono").addEventListener("click", () => impostaMicDaTocco(!st.mic));
  $("schermo-tieni").addEventListener("click", () => impostaTieni(!st.tieni));
  attr($("schermo-tieni"), "aria-checked", st.tieni ? "true" : "false");
  // Menu, modulo e casella per scrivere: strati sopra la vista (Esc li chiude)
  $("menu-apri").addEventListener("click", () => apriStrato("menu"));
  $("menu-chiudi").addEventListener("click", () => chiudiStrato("menu"));
  $("modulo-chiudi").addEventListener("click", () => chiudiStrato("strato-modulo"));
  $("scrivi-apri").addEventListener("click", apriScrivi);
  $("foto-apri").addEventListener("click", apriFoto);
  $("scrivi-chiudi").addEventListener("click", () => chiudiStrato("strato-scrivi"));
  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape") return;
    for (const s of STRATI) {
      if ($(s).hidden) continue;
      if (s === "strato-scheda") chiudiIntera(); else chiudiStrato(s);
      break;
    }
  });
  // La scheda a schermo intero: «Chiudi» e il gesto indietro (la voce messa da apriIntera)
  $("intera-chiudi").addEventListener("click", chiudiIntera);
  window.addEventListener("popstate", () => { if (!$("strato-scheda").hidden) chiudiStrato("strato-scheda"); });
  // Un avviso si toglie toccandolo (quello dello schermo no: il tocco lo riprova)
  $("avviso-tel").addEventListener("click", () => avviso(""));
  // Il carosello: le schede di schermo.js, chi scorre a mano, «Compila» di un modulo
  document.addEventListener("calliope:schede", (ev) => sincronizza(ev.detail));
  document.addEventListener("calliope:mostra", (ev) => { if (ev.detail.scheda) suMostra(ev.detail.scheda); });
  document.addEventListener("calliope:scrivi", (ev) => suScrivi(ev.detail));
  document.addEventListener("calliope:scritto", () => setTimeout(() => chiudiStrato("strato-scrivi"), 1200));
  // Il cruscotto di chi amministra (06/10): la voce del menu solo se il proprietario di questo
  // telefono amministra (lo ricontrolla il server); la scheda va nel carosello
  document.addEventListener("calliope:amministra", (ev) => { $("cruscotto-tel").hidden = !ev.detail.attiva; });
  // Dal menu il cruscotto si apre subito a schermo intero (resta anche nel carosello)
  $("cruscotto-tel").addEventListener("click", async () => {
    chiudiStrato("menu");
    if (sch() && await sch().cruscotto()) apriIntera("cruscotto");
  });
  const bin = $("binario");
  bin.addEventListener("scroll", suScorri, { passive: true });
  bin.addEventListener("click", (ev) => {
    const b = ev.target.closest && ev.target.closest(".apri-modulo");
    if (b) { apriModulo(b.closest("[data-chiave]").dataset.chiave); return; }
    suToccoCarosello(ev);
  });
  window.addEventListener("resize", () => vaiA(car.vista));
  // Ogni tocco, se il browser aveva tolto lo schermo acceso, lo richiede con il gesto in corso
  document.addEventListener("pointerdown", () => { st.tocco = performance.now(); schermo.riprova(); }, true);
  $("dimentica").addEventListener("click", () => {
    if (!confirm("Dimentico l'abbinamento di questo telefono?")) return;
    scrivi(CHIAVE_TOKEN, null);
    scrivi(CHIAVE_ABBINA, null);
    st.token = null;
    if (window.calliopeSchermo) window.calliopeSchermo.dimentica();
    if (st.ws) st.ws.close();
    mostraAbbinamento();
  });
  preparaPulsante($("parla"));
  const bd = $("diag-prova");
  if (bd) bd.addEventListener("click", async () => {
    player.sblocca();
    bd.disabled = true;
    try { await diagnostica(); } finally { bd.disabled = false; }
  });
  // Il primo tocco ovunque sblocca l'audio (iOS lo vuole da un gesto)
  document.addEventListener("pointerdown", () => player.sblocca(), { once: true });
  try {
    const s = await (await fetch("/telefono/api/stato", { cache: "no-store" })).json();
    if (!s.ca) $("link-ca").hidden = true;
    if (s.manca && s.manca.length) avviso("Sul server: " + s.manca.join("; ") + ".");
  } catch (e) { /* lo dirà il collegamento */ }
  if (st.token) connetti();
  else {
    mostraAbbinamento();
    const a = abbinamentoSalvato();
    if (a) {
      // Pagina riaperta mentre un codice è in attesa: lo stesso codice, o il token
      mostraCodice(a.codice, (a.scade - Date.now()) / 1000, a.nome);
      riprendiAbbinamento();
    }
  }
  disegna();
}

// Per le prove (prove/prova_telefono_pagina.py) e per guardare dentro dal browser
window.calliopeTelefono = {
  st, param, misure, player, ascolto,
  stato: () => ({
    collegato: st.collegato, attivo: st.attivo, mic: st.mic, modelli: st.modelli,
    erroreModelli: st.erroreModelli || null, tempoModelli: st.tempoModelli || null,
    inviato: st.inviato, voce: voceLocale()[0], ricevuti: player.byte,
    cpu: misure.inferenzaMs / Math.max(1, performance.now() - misure.dal),
    contesto: player.ctx ? player.ctx.state : null, rate: player.ctx ? player.ctx.sampleRate : null,
  }),
  impostaMic, tocca, diagnostica, opzioniMic, mic,
  schermo, comando, opzioniCarosello, apriStrato, chiudiStrato, apriModulo, vaiA, apriIntera, chiudiIntera,
  carosello: () => ({ ordine: car.ordine.slice(), vista: car.vista, modulo: car.modulo, intera: car.intera }),
  schermoStato: () => ({ stato: schermo.stato, motivo: schermo.motivo, voluto: schermo.voluto,
    richieste: schermo.richieste, cadute: schermo.cadute, info: schermo.info,
    indicatore: statoSchermo(), tieni: st.tieni }),
  abbinamento: () => ({ salvato: abbinamentoSalvato(), aperto: !!abbinaWs, token: !!st.token }),
  // Per le prove: le connessioni chiuse come fa iOS con la pagina sospesa
  chiudiAbbina: () => { if (abbinaWs) abbinaWs.close(4000, "sospesa"); },
  chiudiSessione: () => { if (st.ws) st.ws.close(4000, "sospesa"); },
  micStato: () => ({
    aperto: !!mic.stream, rate: mic.rate, traccia: mic.traccia, ritmo: mic.ritmo, blocchi: mic.blocchi,
    persi: mic.persi, fuoriOrdine: mic.fuoriOrdine, ricostruito: mic.ricostruito, motivo: mic.motivo,
    contesto: mic.ctx ? mic.ctx.state : null, scartati: ascolto.scartati,
  }),
  // Punteggi della wake word su un audio a 16 kHz (Float32Array), fuori dal microfono
  async provaWake(campioni) {
    const w = ascolto.wake;
    if (!w) return null;
    w.reset();
    const out = [];
    for (let i = 0; i + 1280 <= campioni.length; i += 1280) {
      const s = await w.process(campioni.subarray(i, i + 1280));
      if (s !== null) out.push(s);
    }
    w.reset();
    return out;
  },
  async provaVad(campioni) {
    const v = ascolto.vad;
    if (!v) return null;
    v.reset();
    const out = [];
    for (let i = 0; i + FRAME <= campioni.length; i += FRAME) out.push(await v.prob(campioni.subarray(i, i + FRAME)));
    v.reset();
    return out;
  },
  SR,
};

avvio();
