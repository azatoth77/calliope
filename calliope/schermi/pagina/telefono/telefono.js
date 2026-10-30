// Calliope · telefono: la web app che fa del telefono un satellite (03/10/2026).
// Protocollo: quello del satellite (calliope/satellite/protocollo.py) su un WebSocket del
// server degli schermi. Da addormentata l'audio non esce dal telefono finché la wake word
// «Calliope», che gira qui, non scatta; con «Parla» la frase parte subito.
// Tutto il testo che arriva dal server va in textContent: sono dati, mai HTML.
import { Ascolto, AscoltoStanza, FRAME, Riproduttore, SR, Vad, WakeWord, caricaOrt, misure, sessione } from "./voce.js";
import { SchermoAcceso } from "./schermo-acceso.js";

// Versione 3 (13/10): l'ascolto della stanza (calliope/satellite/protocollo.py)
const VERSIONE = 3;
// La versione di questa pagina, nei log del server (28/10, #291): uguale alla cache di sw.js
// (prova_telefono_consapevole le confronta). Una costante della pagina che gira, non la cache
// più alta (revisione della PR #294: durante un aggiornamento è quella nuova), e pronta già al
// primo «ciao»
const PAGINA_VERSIONE = "calliope-telefono-pagina-v24";
const CHIAVE_TOKEN = "calliope.telefono.token";
const CHIAVE_NOME = "calliope.telefono.nome";
const CHIAVE_MIC = "calliope.telefono.microfono";
const CHIAVE_TIENI = "calliope.telefono.schermo_acceso";   // "0": lo schermo può spegnersi
const CHIAVE_STANZA = "calliope.telefono.stanza";          // "0": la stanza non si ascolta da qui
const ATTESE_MS = [1000, 2000, 5000, 10000, 15000];
// Valori di riserva finché il server non manda i suoi (benvenuto: calliope.yaml del server)
const PARAMETRI = {
  name: "Calliope", wake_word: null, wake_anche_nome: true, sample_rate: 16000, vad_threshold: 0.5, silence_ms: 700, preroll_ms: 300,
  min_speech_ms: 250, max_utterance_s: 120, wake_threshold: 0.5, wake_consecutive: 2,
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
  compagnia: "",         // «In compagnia: chiamami per nome» (09/10), dallo stato della voce
  // La conversazione di stanza (13/10, decisione 0029): lo stato del server ({attiva, motivo,
  // fino, segmento_max_s}, null se il server non la fa), l'interruttore di questo telefono
  // (acceso di serie, risposta 5 di chi amministra), i byte mandati (la banda)
  stanza: { server: null, voluta: leggi(CHIAVE_STANZA) !== "0", inviato: 0 },
  ultimoA: 0, ultimoLid: null,          // l'ultimo audio dei comandi (legame con la stanza)
};
const param = Object.assign({}, PARAMETRI);
const ascolto = new Ascolto(param);
const player = new Riproduttore("Calliope");
// L'ascolto della stanza (13/10): un secondo VAD sugli stessi blocchi, solo con la stanza accesa
// dal server, l'interruttore acceso e il microfono acceso; mentre Calliope parla solo con
// `durante_voce` dal server (passo 5, 14/10: i segmenti portano le frasi che suonavano)
const stanza = new AscoltoStanza(param, mandaStanza, () => player.inCorso(),
  () => (st.ultimoLid !== null ? { t: st.ultimoA, id: st.ultimoLid } : null),
  () => player.voceOra(1.0));
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
// Dal 27/10 la pagina ha cinque sezioni (Adesso, Conversazione, Le mie cose, Casa, Io) con la
// barra in basso, e sopra la barra la voce: stato di questo telefono, «Microfono», «Parla»,
// «Scrivi». Impostazioni, «Prova il microfono» e certificato stanno in Io; il modulo da
// compilare e la casella per scrivere sono strati che compaiono quando servono. La vista unica
// del 04/10 (la «vista da guida») è la modalità «In auto».
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
const SUGGERIMENTO = "Tocca «Parla» per parlare";
function statoVista(cls) {
  const dove = st.altro ? "Il microfono attivo è su «" + st.altro + "»" : "";
  if (!st.collegato) return ["spento", "Non collegata", "Riprovo da sola"];
  if (cls === "parla") return ["parla", "Parlo", ""];
  if (cls === "pensa") return ["pensa", "Penso…", ""];
  if (cls === "ascolta" && (st.reg || st.mic || (st.corsa && st.corsa.parla))) return ["ascolta", "Ti ascolto", ""];
  if (!st.mic && !st.reg) return ["spento", "Microfono spento", dove || SUGGERIMENTO];
  return ["dorme", TESTI.dorme, st.attivo ? "" : dove];
}

// Lo stato breve dentro «Parla» nel layout compatto (28/10, #277: sull'iPhone 13 mini la voce
// prendeva tre righe): la parola grande diventa più corta, quella che si capisce già dal
// microfono sbarrato o verde resta lì
function statoBreve(parola) {
  if (parola === TESTI.dorme) return "di' «Calliope»";
  return parola;
}

function disegna() {
  const [cls] = voceLocale();
  const [gc, parola, dove] = statoVista(cls);
  // In compagnia con una voce sconosciuta (09/10): la riga piccola lo dice, sotto il resto
  let sotto = st.compagnia && st.collegato ? (dove ? dove + " · " : "") + st.compagnia : dove;
  const ts = testoStanza();                // la stanza ascolta (13/10)
  if (ts) sotto = sotto ? sotto + " · " + ts : ts;
  const v = $("tel-voce");
  if (v.className !== "voce " + gc) v.className = "voce " + gc;
  metti(v.querySelector(".voce-testo"), parola);
  const d = $("tel-dove");
  d.hidden = !sotto;
  metti(d, sotto);
  // Il suggerimento di sempre: nel compatto non si mostra (resta la descrizione di «Parla»)
  attr(d, "data-ovvio", sotto === SUGGERIMENTO ? "1" : "0");
  descriviParla();
  $("vista").classList.toggle("mic-acceso", st.mic);
  const b = $("parla");
  metti(b.querySelector(".parla-testo"), st.reg ? "Ti ascolto · tocca per finire"
    : cls === "parla" ? "Interrompi e parla" : "Parla");
  metti(b.querySelector(".parla-breve"), st.reg ? "Tocca per finire" : cls === "parla" ? "Interrompi" : "Parla");
  metti(b.querySelector(".parla-stato"), statoBreve(parola));
  attr(b, "data-stato", gc);
  b.disabled = !st.collegato;
  b.classList.toggle("in-corso", !!st.reg || st.forza || (cls === "ascolta" && !!st.corsa && st.corsa.parla));
  b.classList.toggle("parla-calliope", cls === "parla" && !st.reg);
  attr($("microfono"), "aria-checked", st.mic ? "true" : "false");
  metti($("mic-stato"), st.mic ? "acceso" : "spento");
  disegnaRisposta();
  segnaTagli();
  disegnaOra();
  // Il pallino sopra un gioco (11/10, modalità gioco di schermo.js): lo stato di QUESTO telefono
  if (sch() && sch().voceGioco) sch().voceGioco(gc);
}
setInterval(disegna, 250);

// Scrive solo se cambia: il giro ogni 250 ms non tocca il DOM per niente
function metti(el, testo) { if (el && el.textContent !== testo) el.textContent = testo; }
function attr(el, k, v) { if (el && el.getAttribute(k) !== v) el.setAttribute(k, v); }

// «Parla» descritto dal suggerimento solo quando il suggerimento non si vede (29/10, #287): nel
// compatto, dove «Tocca «Parla» per parlare» è nascosto (data-ovvio). Fuori dal compatto, o quando la
// riga piccola si vede, la riga si legge già nel suo posto e VoiceOver la diceva due volte. Si
// rifà a ogni disegno, al cambio del compatto (media query) e al cambio di modo (In auto)
function descriviParla() {
  const d = $("tel-dove"), b = $("parla");
  if (!d || !b) return;
  const nascosta = !d.hidden && !!d.textContent && getComputedStyle(d).display === "none";
  if (nascosta) attr(b, "aria-describedby", "tel-dove");
  else if (b.hasAttribute("aria-describedby")) b.removeAttribute("aria-describedby");
}
const COMPATTO = window.matchMedia
  ? window.matchMedia("(orientation: portrait) and (max-width: 389px), (orientation: portrait) and (max-height: 719px)")
  : null;
if (COMPATTO) {
  const cambia = () => descriviParla();
  if (COMPATTO.addEventListener) COMPATTO.addEventListener("change", cambia);
  else if (COMPATTO.addListener) COMPATTO.addListener(cambia);
}

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

// In Io l'indicatore discreto; nella vista solo l'avviso, quando lo schermo può spegnersi
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

// ───────────────────────────── sezioni (27/10) ─────────────────────────────
// docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md, passo 1: al posto del carosello cinque
// sezioni (Adesso, Conversazione, Le mie cose, Casa, Io) con la barra in basso e la voce sopra.
// Lo smistamento delle schede per sezione, il router sul frammento, le novità e i rimandi sono
// in ../sezioni.js (dal passo 1b lo usa anche la pagina degli schermi personali sul PC); qui le
// parti del telefono: l'ultima risposta, la scheda nell'elenco con «Espandi», gli strati (modulo,
// scheda a schermo intero), la vista dello sviluppo. La vista unica di prima resta come modalità
// «In auto», che si accende a mano (decisione del 27/10): stato grande, l'ultima risposta,
// «Parla» e il microfono, niente barra.
const RISPOSTA = "__risposta";
const CHIAVE_AUTO = "calliope.telefono.auto";              // "1": la modalità In auto
// Le schede che hanno sempre «Espandi» (le altre solo se non ci stanno): sul telefono il
// cruscotto, il codice di un lavoro, un documento o l'uscita di un programma non si leggono
// nel riquadro (06/10, iPhone 13 mini)
const TIPI_LUNGHI = new Set(["cruscotto", "lavoro", "documento", "esecuzione", "biblioteca", "web", "allegato", "sviluppo", "chat"]);
// Queste non si aprono a schermo intero: il modulo ha il suo strato, il gioco il suo riquadro
const TIPI_SENZA_INTERA = new Set(["modulo", "gioco"]);
const fmtOra = new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit" });
const sch = () => window.calliopeSchermo;

const SEZ = window.CalliopeSezioni.crea({
  radice: () => $("vista"),
  chiaveVisti: "calliope.telefono.visti",
  costruisci: (c) => costruisciPagina(c),
  // Il modulo aperto nel suo strato e la scheda a schermo intero si aggiornano al loro posto
  aggiornata(k, c) {
    if (car.modulo === k) aggiornaModulo(c);
    if (car.intera === k) disegnaIntera();
  },
  dopoSincronizza: (det) => sviluppoAperto(det),
  // Tolta da chi la guarda (il «Chiudi» del cruscotto) o da Calliope (revoca, non amministra
  // più): lo strato si chiude. Uscita dalla cronologia perché ne sono arrivate altre: resta
  // aperta con l'ultimo contenuto (una scheda nuova non chiude quella che si sta leggendo)
  tolta(k, lista) {
    if (car.intera === k && (k === "cruscotto" || k === "chat" || !lista.length)) chiudiStrato("strato-scheda");
  },
  dopoDisponi: () => segnaTagli(),
  // Uscendo dalla Conversazione la modalità scrittura si chiude (risposta 4 del 28/10, #301)
  dopoPercorso: () => {
    if (vis.sezione !== "conversazione") { impostaScrittura(false); delete $("vista").dataset.filtri; }
    segnaLente();
  },
  // Con la conversazione nella sezione (28/10, #242) l'elenco sotto tiene solo le schede che la
  // conversazione non mostra già: non le risposte scritte (sono il testo del turno), non le schede
  // dentro un turno; in Adesso restano come prima
  fuoriDaCasa: (k, c) => !!car.chatEl && (c.tipo === "risposta" || chatHaScheda(c)),
  // Con la scheda a schermo intero aperta la sua voce nella cronologia del browser si sostituisce
  primaDiVai() {
    if ($("strato-scheda").hidden) return false;
    const sua = !!(history.state && history.state.calliopeStrato === "scheda");
    chiudiStrato("strato-scheda");
    return sua;
  },
});
const { car, vis, chiaveDi, sezioneDi, etichettaOra, disponi, sincronizza, mostraIn, vaiA, vai,
  applicaPercorso, applicaNascoste } = SEZ;
const opzioniVista = SEZ.opzioni;
const TITOLI_SEZIONE = SEZ.TITOLI_SEZIONE;
car.seq[RISPOSTA] = 0;
car.modulo = null;              // chiave del modulo aperto nello strato
car.moduloFirma = "";
car.intera = null;              // chiave della scheda aperta a schermo intero (06/10)
car.chatSchede = {};            // la scheda piccola della conversazione aperta a schermo intero (28/10)
car.chatEl = null;              // la conversazione nella sua sezione (28/10, #242)
car.svil = null;                // lo sviluppo aperto già mostrato nella sua vista (08/10)
vis.modo = leggi(CHIAVE_AUTO) === "1" ? "auto" : "sezioni";

// ───────────────────────────── la conversazione nella sua sezione (28/10, #242) ─────────────────────────────
// La scheda «chat» di schermo.js (frasi con ora e canale, risposte con le schede piccole, filtri e
// ricerca) dentro la sezione Conversazione, allineata al suo posto quando arrivano turni nuovi
function chatHaScheda(c) {
  const ch = sch() && sch().schedaChat ? sch().schedaChat() : null;
  if (!ch || !c) return false;
  return ch.turni.some((t) => Array.isArray(t.schede) && t.schede.some((x) => x && x.id && x.id === c.id));
}
function disegnaChatTel() {
  const posto = $("conv-tel");
  if (!posto || !sch()) return;
  const c = sch().schedaChat ? sch().schedaChat() : null;
  posto.hidden = !c;
  if (!c) { posto.replaceChildren(); car.chatEl = null; disponi(); return; }
  const nuova = sch().costruisci(c);
  nuova.classList.add("conv-tel-scheda");
  const prima = car.chatEl;
  if (prima && prima.isConnected && prima.dataset.chiave === nuova.dataset.chiave) {
    const seguite = sch().misuraSegui(prima);
    sch().allinea(prima, nuova);
    sch().ripristinaSegui(prima, seguite);
  } else {
    posto.replaceChildren(nuova);
    car.chatEl = nuova;
    sch().ripristinaSegui(nuova, null);
  }
  // L'elenco sotto perde le schede che un turno nuovo mostra già
  disponi();
  segnaLente();
}

// La conversazione disegnata mentre la sezione era nascosta non è scesa in fondo (nascosta, lo
// scorrimento non vale): entrando nella sezione va all'ultimo turno, se chi legge non era risalito
function chatInFondo() {
  if (vis.sezione !== "conversazione" || !car.chatEl) return;
  requestAnimationFrame(() => {
    for (const b of car.chatEl.querySelectorAll("[data-segui]")) if (!b.classList.contains("staccato")) b.scrollTop = b.scrollHeight;
  });
}
window.addEventListener("hashchange", chatInFondo);

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
  }
  disegnaRisposta();
  if (car.intera === RISPOSTA) disegnaIntera();
}

function disegnaRisposta() {
  const r = $("risposta-testo");
  if (!r) return;
  const vuota = !st.risposta.testo;
  metti(r, vuota ? "Di' «Calliope» o tocca «Parla»: le risposte compaiono qui, le schede nelle sezioni in basso." : st.risposta.testo);
  r.classList.toggle("vuota", vuota);
  const et = $("risposta").querySelector(".etichetta");
  metti(et, vuota ? "Calliope" : "Risposta · " + fmtOra.format(new Date(st.risposta.ora || Date.now())));
}

// La scheda in un elenco: quella di schermo.js, con l'ora; il modulo come riassunto con
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
  etichettaOra(s, c);
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

// La vista dello sviluppo (08/10): a schermo intero quando uno sviluppo si apre (se non c'è
// un altro strato aperto: lo scritto, un modulo), chiusa quando si chiude o si sospende;
// aperta, si ridisegna anche quando cambia il suo lavoro (il flusso, i tetti)
function sviluppoAperto(det) {
  const d = det && det.scheda;
  if (d && d.tipo === "sviluppo") {
    const k = chiaveDi(d);
    const aperto = !!(d.sviluppo && d.sviluppo.stato === "aperta");
    if (aperto && car.svil !== k) {
      car.svil = k;
      const altri = STRATI.some((x) => x !== "strato-scheda" && !$(x).hidden);
      if (!altri) apriIntera(k);
    } else if (!aperto && car.svil === k) {
      car.svil = null;
      if (car.intera === k) chiudiIntera();
    }
  }
  if (car.intera && car.schede[car.intera] && car.schede[car.intera].tipo === "sviluppo") disegnaIntera();
}

// Calliope mostra una scheda: il modulo si apre nel suo strato; in Adesso la scheda viva va in
// vista (se chi guarda non sta scorrendo); altrove resta il pallino sulla sua sezione
function suMostra(c) {
  const k = chiaveDi(c);
  sincronizza(null);
  if (c.tipo === "modulo" && c.stato === "aperto") apriModulo(k);
  // In auto niente giochi: il riquadro non si vedrebbe ma ascolterebbe i comandi a voce
  if (vis.modo === "auto" && c.tipo === "gioco" && sch().viva(c)) {
    setTimeout(() => sch().chiudiPartita(c.partita), 0);
    return;
  }
  // Un gioco che Calliope apre si usa subito: la sua sezione si apre da sola
  if (vis.modo === "sezioni" && SEZ.apriSeServe(c)) return;
  if (performance.now() - car.toccato > opzioniVista.manoMs) mostraIn(k, vis.sezione);
}

// Io › Aspetto (27/10): il disegno e il tocco sono in ../sezioni.js, comuni col PC
function disegnaAccenti(a) { window.CalliopeSezioni.disegnaAccenti(a, $("accenti"), $("io-aspetto")); }
function suAccento(ev) { return window.CalliopeSezioni.suAccento(ev, $("accento-esito")); }

// La modalità In auto (decisione del 27/10: a mano): «In auto» in Adesso e in Io, «Esci» la chiude
function segnaModo() {
  const acceso = vis.modo === "auto";
  $("vista").dataset.modo = vis.modo;
  $("auto-segno").hidden = !acceso;
  $("auto-esci").hidden = !acceso;
  $("auto-apri").hidden = acceso;
  descriviParla();
}

function impostaAuto(acceso) {
  vis.modo = acceso ? "auto" : "sezioni";
  scrivi(CHIAVE_AUTO, acceso ? "1" : null);
  segnaModo();
  if (acceso) {
    for (const s of STRATI) { if (s === "strato-scheda") chiudiIntera(); else chiudiStrato(s); }
    impostaScrittura(false);           // in auto la tastiera non c'è (28/10, #301)
  }
  if (!acceso && vis.sezione !== "adesso") vai("#/adesso");
  else applicaPercorso();
}

// All'avvio: l'indirizzo com'è (una sezione sconosciuta diventa Adesso) e il modo salvato
function avviaVista() {
  segnaModo();
  SEZ.avvia();
}

// La dissolvenza in fondo solo dove il testo non ci sta; «Espandi» dove non ci sta (in alto o
// di lato) e sulle schede lunghe per tipo
function pagine() { return [...document.querySelectorAll("#sezioni .pagina-car")].filter((e) => !e.closest("[hidden]")); }

function segnaTagli() {
  const r = $("risposta-testo");
  if (r) {
    $("risposta").classList.toggle("taglia", r.scrollHeight > r.clientHeight + 1
      && r.scrollTop + r.clientHeight < r.scrollHeight - 2);
    $("risposta").classList.toggle("lunga", !!st.risposta.testo && r.scrollHeight > r.clientHeight + 1);
  }
  for (const e of pagine()) {
    if (e.dataset.rimando) continue;
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
// Sul telefono il riquadro di una scheda è piccolo: il cruscotto, il codice di un lavoro, un
// documento non si leggevano. Un tocco sulla scheda (o «Espandi») la apre in uno strato sopra
// la vista, con il testo grande, le tabelle e il codice che scorrono di lato nel loro riquadro.
// La scheda aperta si aggiorna al suo posto (stessa chiave: il cruscotto ogni 30 s, un lavoro in
// diretta) senza perdere il punto in cui si legge. Si chiude con «Chiudi», Esc o il gesto
// indietro (una voce nella cronologia del browser, con lo stesso indirizzo della sezione).
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
    const c = schedaIntera(k);
    if (!c) return null;
    s = sch().costruisci(c, { intera: true });
  }
  s.dataset.tipo = k === RISPOSTA ? "risposta" : schedaIntera(k).tipo;
  return s;
}

// La scheda di una sezione, o la copia di un turno aperta dalla conversazione (28/10, #242)
function schedaIntera(k) { return car.schede[k] || car.chatSchede[k] || null; }

function titoloIntera(k) {
  if (k === RISPOSTA) return "Risposta";
  const c = schedaIntera(k);
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
    const seguite = sch().misuraSegui(vecchia);
    sch().allinea(vecchia, nuova);
    sch().ripristinaSegui(vecchia, seguite);
  } else {
    posto.replaceChildren(nuova);
    posto.scrollTop = 0;
    sch().ripristinaSegui(nuova, null);
  }
  if (sch()) sch().aggiorna();
}

function apriIntera(k) {
  if (k !== RISPOSTA && (!schedaIntera(k) || TIPI_SENZA_INTERA.has(schedaIntera(k).tipo))) return false;
  if (k === RISPOSTA && !st.risposta.testo) return false;
  const gia = !$("strato-scheda").hidden;
  if (car.intera !== k) $("intera-posto").replaceChildren();
  car.intera = k;
  disegnaIntera();
  apriStrato("strato-scheda");
  // Le aree che seguono la coda (la conversazione, il flusso dell'agente) vanno in fondo quando
  // lo strato è visibile: nascosto, lo scorrimento non vale (08/10)
  if (!gia) requestAnimationFrame(() => { if (car.intera === k && sch()) sch().ripristinaSegui($("intera-posto"), null); });
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

// Un tocco su una scheda la apre (non sui suoi pulsanti, né sulla risposta, che ha «Espandi»
// quando è lunga, né su modulo e gioco); «Apri» di un rimando porta alla sua sezione
function suToccoScheda(ev) {
  const t = ev.target;
  if (!t.closest) return;
  // La conversazione nella sua sezione (28/10, #242) ha i suoi tocchi: filtri, schede piccole
  if (t.closest(".conv-tel")) return;
  const pag = t.closest("#sezioni [data-chiave]");
  if (!pag) return;
  if (t.closest(".apri-modulo")) { apriModulo(pag.dataset.chiave); return; }
  if (pag.dataset.rimando) { if (t.closest(".apri-rimando") || !t.closest("button, a")) vaiA(pag.dataset.chiave); return; }
  if (t.closest(".espandi")) { apriIntera(pag.dataset.chiave); return; }
  if (pag.dataset.chiave === RISPOSTA) return;
  if (t.closest("button, a, input, textarea, select, summary, label, iframe")) return;
  const sel = window.getSelection && window.getSelection();
  if (sel && !sel.isCollapsed && pag.contains(sel.anchorNode)) return;   // si stava selezionando
  apriIntera(pag.dataset.chiave);
}

// ───────────────────────────── strati: modulo, scrivi ─────────────────────────────
let ritornoFuoco = null;
const STRATI = ["strato-scheda", "strato-modulo"];
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
  if (id === "strato-scheda") { car.intera = null; car.chatSchede = {}; $("intera-posto").replaceChildren(); }
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
  b.closest(".voce-riga").classList.toggle("con-scrivi", !b.hidden);
  if (!det.attiva) impostaScrittura(false);
  else preparaRigaScrivi();
  // Da uno schermo di stanza senza una conversazione a voce (05/10) il tasto resta, attenuato:
  // apre la casella spenta, che dice la parola da dire. Dallo schermo personale si scrive sempre
  // (28/10, #301)
  const spento = !!det.attiva && !det.abilitata;
  b.classList.toggle("spento", spento);
  if (spento) b.title = "Di' «" + (det.parola || "Calliope") + "» per scrivermi";
  else b.removeAttribute("title");
  segnaLente();
}

// ───────────────────────────── scrivere nella Conversazione (28/10, #301) ─────────────────────────────
// Il tocco sulla tastiera porta alla Conversazione in modalità scrittura, nella stessa schermata: la
// riga della voce diventa la casella («Torna alla voce», Allega, il testo, Invia), la conversazione è
// solo chat (le schede un rimando di una riga), i filtri dietro la lente. Resta finché non si tocca il
// microfono o si esce dalla Conversazione; la wake word resta accesa. In auto no
vis.scrittura = false;
function preparaRigaScrivi() {
  const f = $("scrivi");
  if (!f || $("scrivi-voce")) return;
  const b = document.createElement("button");
  b.type = "button";
  b.id = "scrivi-voce";
  b.className = "scrivi-voce";
  b.setAttribute("aria-label", "Torna alla voce");
  if (window.calliopeIcona) b.append(window.calliopeIcona("voce-icona", "microfono"));
  b.addEventListener("click", tornaAllaVoce);
  f.insertBefore(b, $("scrivi-foto") || f.firstChild);
}

function impostaScrittura(v) {
  v = !!v && vis.modo !== "auto" && !!$("scrivi") && !$("scrivi-apri").hidden;
  const vista = $("vista");
  if (vis.scrittura === v) return;
  vis.scrittura = v;
  if (v) vista.dataset.scrittura = "1"; else delete vista.dataset.scrittura;
  $("scrivi-posto").hidden = !v;
  attr($("scrivi-apri"), "aria-pressed", v ? "true" : "false");
  // Scrivendo la risposta è solo scritta (decisione del 28/10 dopo la revisione della PR #304):
  // Calliope torna a parlare con «Torna alla voce» o quando si dice il suo nome
  if (sch() && sch().soloScritto) sch().soloScritto(v);
  if (!v) {
    const i = $("scrivi-testo");
    if (i && document.activeElement === i) i.blur();
  }
  segnaLente();
  misuraTastiera();
  disegnaOra();
  chatInFondo();
}

// Il tocco sulla tastiera: la Conversazione, la casella e il cursore nello stesso gesto (iOS apre la
// tastiera solo dentro il tocco)
function entraScrittura() {
  if (!$("scrivi") || vis.modo === "auto") return false;
  if (vis.sezione !== "conversazione") vai("#/conversazione");
  impostaScrittura(true);
  const i = $("scrivi-testo");
  if (i && !i.disabled) { try { i.focus({ preventScroll: true }); } catch (e) { i.focus(); } }
  return vis.scrittura;
}

// «Torna alla voce» fa partire subito l'ascolto, come «Parla» (risposta 1 del 28/10). Se Calliope
// sta parlando non la interrompe (revisione della PR #304): scrivendo le risposte sono solo
// scritte, quindi ciò che suona è un avviso (il timer, un pericolo) che un tocco per cambiare modo
// non deve zittire; per interromperla c'è «Parla», che subito dopo dice «Interrompi e parla»
function tornaAllaVoce() {
  impostaScrittura(false);
  const p = $("parla");
  if (p) { try { p.focus({ preventScroll: true }); } catch (e) { /* niente */ } }
  if (st.collegato && !player.inCorso()) tocca();
}

// La lente in alto nella Conversazione (a voce e scrivendo, come nelle tavole): apre e chiude i
// filtri e la ricerca; un filtro acceso resta detto nella riga sotto («Ieri: 2 turni», «Tutto»)
function segnaLente() {
  const l = $("conv-lente");
  if (!l) return;
  l.hidden = !(vis.modo === "sezioni" && vis.sezione === "conversazione" && !!car.chatEl);
  attr(l, "aria-expanded", $("vista").dataset.filtri ? "true" : "false");
}
function suLente() {
  const vista = $("vista");
  if (vista.dataset.filtri) delete vista.dataset.filtri; else vista.dataset.filtri = "1";
  segnaLente();
}

// La tastiera di sistema (28/10, #301, e #287): con interactive-widget=resizes-visual né iOS né
// Android ridimensionano la pagina, quindi il layout compatto (media query sull'altezza) non scatta;
// la parte visibile la dice visualViewport. Con un campo di testo col fuoco e la parte visibile più
// bassa di 120 px della finestra, la vista si stringe a quella parte e la barra delle sezioni si
// nasconde; chiusa la tastiera, tutto torna com'era
function campoDiTesto(e) {
  return !!e && !!e.matches && e.matches("textarea, [contenteditable=''], [contenteditable='true'], input:not([type]), input[type='text'], input[type='search'], input[type='email'], input[type='number'], input[type='tel'], input[type='url']");
}
function misuraTastiera() {
  const vv = window.visualViewport;
  const vista = $("vista");
  let aperta = false;
  if (vv && campoDiTesto(document.activeElement)) {
    const coperto = window.innerHeight - vv.height * (vv.scale || 1);
    aperta = coperto > 120;
  }
  if (aperta) {
    vista.style.setProperty("--alto-visibile", Math.round(vv.height) + "px");
    vista.style.setProperty("--su-visibile", Math.round(vv.offsetTop || 0) + "px");
  } else {
    vista.style.removeProperty("--alto-visibile");
    vista.style.removeProperty("--su-visibile");
  }
  if (st.tastiera !== aperta) {
    st.tastiera = aperta;
    vista.classList.toggle("tastiera", aperta);
    if (aperta) chatInFondo();
  }
}
function ascoltaTastiera() {
  const vv = window.visualViewport;
  if (vv) { vv.addEventListener("resize", misuraTastiera); vv.addEventListener("scroll", misuraTastiera); }
  window.addEventListener("resize", misuraTastiera);
  document.addEventListener("focusin", misuraTastiera);
  // Col fuoco che se ne va l'elemento attivo cambia dopo l'evento
  document.addEventListener("focusout", () => setTimeout(misuraTastiera, 0));
}

// «ti ascolto…» mentre si parla (risposta 5 del 28/10), «Calliope sta scrivendo…» dopo un invio
// finché non arriva il turno, «Calliope sta rispondendo…» mentre pensa: in fondo alla chat
st.attesaScritto = 0;
function disegnaOra() {
  const o = $("conv-ora");
  if (!o) return;
  const [cls] = voceLocale();
  const [, parola] = statoVista(cls);
  if (st.attesaScritto && (cls === "parla" || performance.now() - st.attesaScritto > 30000)) st.attesaScritto = 0;
  let t = "";
  if (parola === "Ti ascolto") t = "ti ascolto…";
  else if (st.attesaScritto) t = "Calliope sta scrivendo…";
  else if (cls === "pensa") t = "Calliope sta rispondendo…";
  // Scrivendo la riga della voce non c'è: lo stato si legge da qui; a voce lo dice già lei.
  // role="status" resta sempre (nell'HTML): una regione già nel DOM, che VoiceOver legge, e
  // l'aria-hidden cambia prima del testo, così la prima frase scrivendo si sente
  if (vis.scrittura) o.removeAttribute("aria-hidden"); else attr(o, "aria-hidden", "true");
  metti(o.querySelector(".conv-ora-testo"), t);
  attr(o, "data-vuoto", t ? "0" : "1");
  attr(o, "data-ascolto", parola === "Ti ascolto" ? "1" : "0");
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
  st.ultimoA = performance.now();
  st.ultimoLid = id;
}

// ───────────────────────────── la stanza (13/10) ─────────────────────────────
function mandaStanza(m) {
  if (m[0] === "inizio") { manda(Object.assign({ tipo: "stanza_inizio" }, m[1])); return; }
  if (m[0] === "fine") { manda(Object.assign({ tipo: "stanza_fine" }, m[1])); return; }
  const ws = st.ws;
  const blocchi = m[2];
  if (!ws || ws.readyState !== 1 || !blocchi.length) return;
  const n = blocchi.reduce((a, b) => a + b.length, 0);
  const buf = new ArrayBuffer(5 + n * 2);
  const dv = new DataView(buf);
  dv.setUint8(0, 82);                 // «R»
  dv.setUint32(1, m[1] >>> 0, false);
  let o = 5;
  for (const b of blocchi) {
    for (let i = 0; i < b.length; i++) {
      dv.setInt16(o, Math.round(Math.max(-1, Math.min(1, b[i])) * 32767), true);
      o += 2;
    }
  }
  ws.send(buf);
  st.stanza.inviato += n * 2;
}

function aggiornaStanza() {
  const s = st.stanza.server;
  stanza.imposta(!!(st.collegato && s && s.attiva && st.stanza.voluta && st.mic),
    s && s.segmento_max_s, !!(s && s.durante_voce === true), s);
  const box = $("stanza-interruttore");
  if (box) box.hidden = !(s && s.motivo !== "spenta");
  attr($("stanza-tieni"), "aria-checked", st.stanza.voluta ? "true" : "false");
}

function impostaStanza(v) {
  st.stanza.voluta = !!v;
  scrivi(CHIAVE_STANZA, st.stanza.voluta ? null : "0");
  aggiornaStanza();
  disegna();
}

// Il segno sotto lo stato: la stanza ascolta (o è in pausa), sempre visibile
function testoStanza() {
  const s = st.stanza.server;
  if (!st.collegato || !s || s.motivo === "spenta") return "";
  if (!s.attiva) {
    const fino = s.fino ? ", fino alle " + fmtOra.format(new Date(s.fino * 1000)) : "";
    return (s.motivo === "ospiti" ? "Stanza in pausa: ospiti" : "Ascolto della stanza in pausa") + fino;
  }
  if (!st.stanza.voluta) return "Ascolto della stanza spento su questo telefono";
  return st.mic ? "Ascolto la stanza" : "";
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
      nome: "telefono", esecutore: null, modalita: true, stanza: true,
      pagina: PAGINA_VERSIONE }));
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
  st.stanza.server = null;
  aggiornaStanza();
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
    case "stanza": st.stanza.server = m; aggiornaStanza(); break;
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
  // Nella Conversazione il posto di ciò che si è detto da qui non si ripete (28/10, #301)
  if (sch() && sch().nomiPropri && st.satellite.nome) sch().nomiPropri([st.satellite.nome]);
  statoTel("ok", "collegata");
  manda({ tipo: "pronto", eco: null });
  st.stanza.server = m.stanza || null;
  aggiornaStanza();
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
    stanza.vad = new Vad(await sessione(dati[0]));     // il VAD della stanza: suo (13/10)
    aggiornaStanza();
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
    stanza.push(d.frame);
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
  aggiornaStanza();
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
  // Frase presa: il segnale prima della rete. Non al tetto (10/10): la persona parla ancora e
  // il server chiede subito il seguito (Ciclo._seguito_del_tetto)
  if (r.chiusura !== "lunga") { st.pensa = true; suona("fine"); }
  // pause_ms, parlato_ms, chiusura: solo misura (07/10, calliope/pause.py), un server vecchio
  // li ignora
  u.fine({ tipo: "frase_finita", fa_s: Math.round(performance.now() - r.inizio) / 1000,
    woke: !!r.woke, wake_score: Math.round(r.punteggio * 1000) / 1000,
    campioni: r.audio.length * FRAME, pause_ms: r.pause || [], parlato_ms: r.parlato,
    chiusura: r.chiusura });
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
  const bs = $("stanza-tieni");
  if (bs) bs.addEventListener("click", () => impostaStanza(!st.stanza.voluta));
  aggiornaStanza();
  // Le sezioni: il frammento dice quale (#/cose/liste), il gesto indietro torna a quella di prima;
  // «In auto» a mano, «Esci» torna ad Adesso
  // L'accento e le sezioni nascoste (27/10): da schermo.js, all'accesso e quando cambiano
  document.addEventListener("calliope:aspetto", (ev) => disegnaAccenti(ev.detail));
  document.addEventListener("calliope:nascoste", (ev) => applicaNascoste(ev.detail));
  $("accenti").addEventListener("click", suAccento);
  $("auto-apri").addEventListener("click", () => impostaAuto(true));
  $("auto-io").addEventListener("click", () => impostaAuto(true));
  $("auto-esci").addEventListener("click", () => impostaAuto(false));
  // Modulo e casella per scrivere: strati sopra la vista (Esc li chiude)
  $("modulo-chiudi").addEventListener("click", () => chiudiStrato("strato-modulo"));
  // Scrivere nella Conversazione (28/10, #301): la tastiera, la lente, la tastiera di sistema
  $("scrivi-apri").addEventListener("click", entraScrittura);
  $("conv-lente").addEventListener("click", suLente);
  ascoltaTastiera();
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
  window.addEventListener("popstate", (ev) => {
    if (!$("strato-scheda").hidden && !(ev.state && ev.state.calliopeStrato === "scheda")) chiudiStrato("strato-scheda");
  });
  // Un avviso si toglie toccandolo (quello dello schermo no: il tocco lo riprova)
  $("avviso-tel").addEventListener("click", () => avviso(""));
  // Il carosello: le schede di schermo.js, chi scorre a mano, «Compila» di un modulo
  document.addEventListener("calliope:schede", (ev) => sincronizza(ev.detail));
  document.addEventListener("calliope:mostra", (ev) => { if (ev.detail.scheda) suMostra(ev.detail.scheda); });
  document.addEventListener("calliope:scrivi", (ev) => suScrivi(ev.detail));
  // Lo stato della voce della stanza del telefono dice se è in compagnia (09/10)
  document.addEventListener("calliope:compagnia", (ev) => {
    const d = ev.detail || {};
    st.compagnia = d.attiva ? String(d.testo || "In compagnia: chiamami per nome") : "";
    disegna();
  });
  // La modalità gioco (11/10): il gioco copre la pagina; uscendo, le dissolvenze si rifanno e
  // un gioco chiuso esce subito da Adesso (non è più vivo)
  document.addEventListener("calliope:gioco", (ev) => {
    if (!(ev.detail || {}).partita) requestAnimationFrame(() => { disponi(); });
  });
  // Il pallino della voce sopra il gioco è anche «Parla»: tocca e parla, tieni premuto per
  // parlare a lungo (come preparaPulsante, ma per delega: schermo.js ridisegna il pallino)
  let giocoPremuto = 0;
  document.addEventListener("pointerdown", (ev) => {
    const b = ev.target && ev.target.closest ? ev.target.closest("button.gioco-voce") : null;
    if (!b) return;
    ev.preventDefault();
    giocoPremuto = performance.now();
    tocca();
  });
  const giocoSu = () => {
    if (!giocoPremuto) return;
    if (performance.now() - giocoPremuto > 600) st.rilascio = true;
    giocoPremuto = 0;
  };
  document.addEventListener("pointerup", giocoSu);
  document.addEventListener("pointercancel", giocoSu);
  document.addEventListener("calliope:scritto", () => { st.attesaScritto = performance.now(); disegnaOra(); });
  // «Prova con…», «Chiedi all'agente…» della vista dello sviluppo (08/10): la frase da finire
  // nella casella dello scritto (lo strato dello sviluppo si chiude, e si riapre dalla scheda)
  document.addEventListener("calliope:prefill", (ev) => {
    const testo = String((ev.detail && ev.detail.testo) || "");
    entraScrittura();
    const i = $("scrivi-testo");
    if (i && !i.disabled) {
      i.value = testo;
      try { i.setSelectionRange(testo.length, testo.length); } catch (e) { /* niente */ }
    }
  });
  // Il cruscotto di chi amministra (06/10): in Io solo se il proprietario di questo telefono
  // amministra (lo ricontrolla il server); la scheda resta in Io
  document.addEventListener("calliope:amministra", (ev) => {
    $("cruscotto-tel").hidden = !ev.detail.attiva;
    $("io-amministra").hidden = !ev.detail.attiva;
  });
  // Il cruscotto si apre subito a schermo intero
  $("cruscotto-tel").addEventListener("click", async () => {
    if (sch() && await sch().cruscotto()) apriIntera("cruscotto");
  });
  // La conversazione (08/10): da Conversazione a schermo intero, e resta lì; «Pulisci le mie
  // schede» con due tocchi (le schede non tornano). Solo su un telefono personale
  // Dal 28/10 (#242) la conversazione sta nella sezione, con le schede piccole, i filtri e la ricerca
  document.addEventListener("calliope:chat", () => disegnaChatTel());
  // Il turno arrivato toglie «Calliope sta scrivendo…»
  document.addEventListener("calliope:chatturni", () => { disegnaChatTel(); st.attesaScritto = 0; disegnaOra(); segnaLente(); });
  // Una scheda piccola della conversazione: la copia del turno a schermo intero; un rimando porta
  // alla scheda nella sua sezione, o alla sezione se la scheda non c'è più
  document.addEventListener("calliope:intera", (ev) => {
    const c = ev.detail && ev.detail.scheda;
    if (!c || !c.chiave) return;
    car.chatSchede = { [c.chiave]: c };
    apriIntera(c.chiave);
  });
  document.addEventListener("calliope:vai", (ev) => {
    const c = ev.detail && ev.detail.scheda;
    if (!c) return;
    if (!(c.chiave && vaiA(c.chiave))) vai("#/" + sezioneDi(c));
  });
  document.addEventListener("calliope:scrivi", (ev) => { $("pulisci-tel").hidden = !(ev.detail && ev.detail.personale); });
  // Calliope apre una pagina di Le mie cose (28/10, #289): solo un nome di raccolta, mai un indirizzo
  document.addEventListener("calliope:pagina", (ev) => {
    const p = ev.detail && ev.detail.pagina;
    if (typeof p === "string" && /^[a-z]{1,20}$/.test(p)) vai("#/cose/" + p);
  });
  let pulisciArmato = 0;
  $("pulisci-tel").addEventListener("click", async () => {
    const b = $("pulisci-tel"), esito = $("pulisci-esito");
    if (Date.now() >= pulisciArmato) {
      pulisciArmato = Date.now() + 4000;
      b.textContent = "Tocca di nuovo per pulire";
      setTimeout(() => { if (Date.now() >= pulisciArmato) b.textContent = "Pulisci le mie schede"; }, 4100);
      return;
    }
    pulisciArmato = 0;
    b.disabled = true;
    const r = sch() ? await sch().pulisci() : { ok: false };
    b.disabled = false;
    b.textContent = "Pulisci le mie schede";
    esito.hidden = false;
    esito.textContent = r.ok ? (r.frase || "Schede tolte.") : (r.errore || "Non ci sono riuscita: riprova.");
  });
  $("sezioni").addEventListener("click", suToccoScheda);
  avviaVista();
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
    stanza: { server: st.stanza.server, voluta: st.stanza.voluta, attiva: stanza.attiva,
      inviato: st.stanza.inviato, segmenti: stanza.seg.segmenti, buttati: stanza.seg.buttati,
      persi: stanza.persi, segno: testoStanza() },
  }),
  impostaStanza, stanzaAscolto: stanza,
  impostaMic, tocca, diagnostica, opzioniMic, mic,
  // Scrivere nella Conversazione (28/10, #301)
  entraScrittura, impostaScrittura, tornaAllaVoce, misuraTastiera,
  scrittura: () => ({ attiva: vis.scrittura, tastiera: !!st.tastiera, filtri: !!$("vista").dataset.filtri }),
  schermo, comando, opzioniVista, apriStrato, chiudiStrato, apriModulo, vaiA, vai, impostaAuto, apriIntera, chiudiIntera,
  // Dove sta ogni scheda (per le prove): la sezione guardata, il modo, le chiavi per elenco
  sezioni: () => Object.assign(SEZ.stato(), { modulo: car.modulo, intera: car.intera }),
  // Le tessere di Le mie cose rilette subito (28/10), senza aspettare il minuto
  aggiornaRaccolte: () => SEZ.aggiornaRaccolte(),
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
