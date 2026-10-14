// La prova di fumo di una scheda interattiva (05/10/2026, calliope/estensioni/scheda.py): gli
// script del gioco caricati con un DOM finto semplice e l'oggetto `calliope` finto, poi
// centinaia di tocchi a caso sugli elementi che ascoltano, con il tempo che scorre. Un errore
// (variabile mai dichiarata, funzione sbagliata) diventa un test fallito: i test di logica.js
// non lo vedono, perché girano senza il disegno (prima prova vera sulla DGX: il memory
// dell'agente aveva «attesaRigira» mai dichiarata e nessun tocco funzionava).
// Usato da test_js.mjs; restituisce l'elenco degli errori.
//
// Dal 12/10 sera (flusso dell'agente a fasi, parte 1; ricerca 2026-10-12-flusso-agente-fasi
// § 5.1, passo 2) lo stesso ambiente serve anche ai test del disegno: apriGioco() carica il gioco
// vero nel DOM finto e lo restituisce da guidare (tocca un elemento per testo o selettore, legge
// il testo visibile, fa passare il tempo, manda un comando a voce). Il caso vero del 12/10:
// logica.js restituiva l'esito annidato ({ ...stato, risultato }) e gioco.js lo leggeva al primo
// livello: sempre «Nessun punto!», con i test della logica verdi. Un test che tocca una porta e
// legge cosa compare lo prende alla prima versione. Il caso del gioco (Math.random) ha un seme
// fisso, nella prova di fumo e in apriGioco (opzione «seme»): esiti ripetibili.
//
// Dal 13/10 (macchina a stati dei giochi, calliope/estensioni/motore_gioco.js) un gioco con
// «scheda.macchina» si carica con il motore davanti, come nel riquadro, e la prova di fumo è
// **per fasi**: l'esploratore percorre la macchina dichiarata (ogni comando con ogni valore, da
// ogni numero di giocatori), dice le fasi senza uscita e quelle mai raggiunte, i comandi mai
// attivi, le mosse che lanciano o restituiscono una forma sbagliata, e gioca partite intere fino
// alla fine; poi i tocchi a caso sui pulsanti del motore.
//
// Dal 14/10 (passo 4, il palco fisso) la prova di fumo misura anche il PALCO: per ogni pagina che
// la macchina raggiunge, nei due orientamenti (1280×720 e 720×1280), ciò che esce dal palco, ciò
// che si sovrappone e il testo che non ci sta neanche al corpo minimo (l'impaginazione è una
// funzione pura del motore, la stessa del riquadro: CalliopeMotore.impagina e controllaPalco).
// Un difetto è un errore della prova, con la fase, la pagina e la strada. Ed è l'unico formato:
// un gioco senza «scheda.macchina» (gioco.js libero, «ascolta» piatto) non passa.
import { existsSync, readFileSync } from "node:fs";
import vm from "node:vm";

// Il motore della macchina a stati: accanto a questo file nel container (/opt/calliope), in
// calliope/estensioni nel repository
const MOTORE = [new URL("./motore_gioco.js", import.meta.url), new URL("../estensioni/motore_gioco.js", import.meta.url)]
  .find((u) => existsSync(u));
export function testoMotore() {
  if (!MOTORE) throw new Error("il motore dei giochi (motore_gioco.js) non c'è");
  return readFileSync(MOTORE, "utf8");
}

// Un generatore con seme (mulberry32): lo stesso seme, la stessa sequenza
export function creaCaso(seme = 1) {
  let a = (Number(seme) >>> 0) || 1;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Le promesse rifiutate senza gestore vanno all'ambiente aperto per ultimo (un ascoltatore solo
// per processo: con un ambiente per test Node avviserebbe di troppi ascoltatori)
let notaCorrente = null;
let ascolto = false;

async function prepara(file, opzioni = {}) {
  // Le promesse del gioco (async, await calliope.leggi) si risolvono solo tornando al ciclo
  const respira = () => new Promise((ok) => setImmediate(ok));
  const errori = [];
  // Un consiglio per gli errori che vengono dal modo in cui il riquadro carica gli script (seconda
  // prova vera sulla DGX, 05/10: gioco.js rifaceva «const { … } = require("./logica.js")», e
  // l'agente ha finito le passate senza capire perché)
  const CONSIGLI = [
    [/already been declared|require is not defined|Cannot use import|import statement|module is not defined/,
     " (nel riquadro gli script di «scheda.file» si caricano uno dopo l'altro nello stesso spazio "
     + "globale, come i <script> del browser: negli altri file usa direttamente le funzioni di "
     + "logica.js, senza require, import né const { … } = …; require serve solo nei test)"],
    [/is not defined/, " (dichiara la variabile con let o const prima di usarla)"],
  ];
  // Dove e perché (11/10, giro vero della DGX: «tocco (click): Error: Devi inserire da 1 a 4
  // giocatori» senza elemento né riga, e l'agente ha riscritto gioco.js intero nove volte): le
  // righe degli script della scheda nello stack, l'elemento toccato, gli ultimi tocchi
  const base = (p) => String(p).replace(/\\/g, "/").split("/").pop();
  const suoi = new Set(file.map(base));
  const testi = {};
  const frame = (e) => {
    const out = [];
    for (const m of String(e && e.stack || "").matchAll(/(?:at (?:async )?([^\s()]+) \()?([^\s()]+?\.js):(\d+)(?::\d+)?/g)) {
      const f = base(m[2]);
      if (!suoi.has(f)) continue;
      const s = `${f}:${m[3]}` + (m[1] && !m[1].includes("<anonymous>") && !m[1].startsWith("<") ? ` (${m[1]})` : "");
      if (!out.includes(s)) out.push(s);
      if (out.length >= 3) break;
    }
    return out;
  };
  const descrivi = (n) => {
    if (!n || !n.tagName) return "il documento";
    let s = "<" + n.tagName.toLowerCase() + (n.id ? ` id="${n.id}"` : "");
    const c = n.className;
    if (c) s += ` class="${c.slice(0, 40)}"`;
    s += ">";
    const t = String(n.textContent || n.value || "").trim().replace(/\s+/g, " ");
    return t ? `${s} «${t.slice(0, 40)}${t.length > 40 ? "…" : ""}»` : s;
  };
  const tocchi = [];               // gli ultimi tocchi, per dire cosa c'era prima dell'errore
  const dichiarato = (nome) => {
    const rx = new RegExp(`^\\s*(?:export\\s+)?(?:const|let|var|class|(?:async\\s+)?function\\*?)\\s+${nome.replace(/[$]/g, "\\$")}\\b`);
    const dove = [];
    for (const [f, t] of Object.entries(testi)) {
      t.split("\n").forEach((r, i) => { if (rx.test(r)) dove.push(`${f}:${i + 1}`); });
    }
    return dove;
  };
  const nota = (dove, e, ctx = {}) => {
    if (errori.length >= 5) return;
    const msg = String(e && e.message || e);
    let consiglio = (CONSIGLI.find(([rx]) => rx.test(msg)) || [null, ""])[1];
    let fr = frame(e);
    const doppio = msg.match(/Identifier '([^']+)' has already been declared/);
    if (doppio) {
      // Node dice la riga 1 dello script: le righe vere sono quelle delle dichiarazioni
      const d = dichiarato(doppio[1]);
      fr = d.filter((x) => ctx.file && x.startsWith(ctx.file + ":"));
      if (d.length) consiglio = ` («${doppio[1]}» è dichiarato in ${d.join(" e ")}: tienilo in un file solo, o cambia nome nell'altro)` + consiglio;
    }
    const lungo = e && e.name === "ErrorePalco" ? 900 : e && e.name === "ErroreGioco" ? 420 : 200;
    let t = dove + (ctx.elemento ? ` su ${descrivi(ctx.elemento)}` : "")
      + (ctx.bersaglio && ctx.bersaglio !== ctx.elemento ? ` (toccato ${descrivi(ctx.bersaglio)})` : "")
      + `: ${e && e.name && e.name !== "ErrorePalco" ? e.name + ": " : ""}${msg.slice(0, lungo)}`
      + (fr.length ? ` [in ${fr.join(" ← ")}]` : "");
    if (ctx.gestore) {
      t += ". Un gestore di evento ha lanciato un'eccezione: ogni gestore deve catturare gli "
        + "errori della logica (try/catch) e mostrarli nel gioco, senza lasciarli uscire";
      const prima = tocchi.slice(-6, -1);
      if (prima.length) t += `. Tocchi prima: ${prima.join(", ")}`;
    }
    errori.push(t + consiglio);
  };
  // ── tempo finto ──
  let adesso = 0, nTimer = 0;
  const timer = new Map();
  const metti = (fn, ms, ripeti) => { const id = ++nTimer; timer.set(id, { t: adesso + Math.max(0, +ms || 0), fn, ripeti: ripeti ? Math.max(1, +ms || 1) : 0 }); return id; };
  function avanza(ms) {
    const fine = adesso + ms;
    for (let giri = 0; giri < 2000; giri++) {
      let prossimo = null;
      for (const [id, x] of timer) if (x.t <= fine && (!prossimo || x.t < prossimo[1].t)) prossimo = [id, x];
      if (!prossimo) break;
      const [id, x] = prossimo;
      adesso = Math.max(adesso, x.t);
      if (x.ripeti) x.t = adesso + x.ripeti; else timer.delete(id);
      try { typeof x.fn === "function" ? x.fn(adesso) : null; } catch (e) { nota("timer", e); }
    }
    adesso = fine;
  }
  // ── DOM finto ──
  const nodi = [];
  const ctx2d = new Proxy({}, { get: (o, k) => (k in o ? o[k] : (k === "measureText" ? () => ({ width: 10 }) : (k === "createLinearGradient" || k === "createRadialGradient" || k === "createPattern") ? () => ({ addColorStop() {} }) : (k === "getImageData") ? () => ({ data: new Uint8ClampedArray(4) }) : () => {})), set: (o, k, v) => { o[k] = v; return true; } });
  class Lista { constructor(n) { this.n = n; this.s = new Set(); } add(...c) { c.forEach((x) => this.s.add(x)); } remove(...c) { c.forEach((x) => this.s.delete(x)); } toggle(c, f) { const on = f === undefined ? !this.s.has(c) : !!f; if (on) this.s.add(c); else this.s.delete(c); return on; } contains(c) { return this.s.has(c); } get length() { return this.s.size; } }
  class Nodo {
    constructor(tag, tipo = 1) {
      this.nodeType = tipo; this.tagName = String(tag).toUpperCase(); this.nodeName = this.tagName;
      this.childNodes = []; this.parentNode = null; this._h = {}; this.attributes = {};
      this._testo = ""; this.style = { setProperty() {}, removeProperty() {}, getPropertyValue() { return ""; } };
      this.dataset = {}; this.classList = new Lista(this); this.id = ""; this.value = ""; this.checked = false;
      this.disabled = false; this.hidden = false; this.width = 300; this.height = 150; this.scrollTop = 0;
      this.offsetWidth = 100; this.offsetHeight = 100; this.clientWidth = 100; this.clientHeight = 100;
      this.scrollHeight = 100; this.scrollWidth = 100; this.tabIndex = 0; this.src = ""; this.alt = "";
      nodi.push(this);
    }
    get children() { return this.childNodes.filter((c) => c.nodeType === 1); }
    get firstChild() { return this.childNodes[0] || null; }
    get lastChild() { return this.childNodes[this.childNodes.length - 1] || null; }
    get firstElementChild() { return this.children[0] || null; }
    get lastElementChild() { const c = this.children; return c[c.length - 1] || null; }
    get parentElement() { return this.parentNode; }
    get childElementCount() { return this.children.length; }
    get nextSibling() { const p = this.parentNode; return p ? p.childNodes[p.childNodes.indexOf(this) + 1] || null : null; }
    get previousSibling() { const p = this.parentNode; return p ? p.childNodes[p.childNodes.indexOf(this) - 1] || null : null; }
    get nextElementSibling() { return this.nextSibling; }
    get previousElementSibling() { return this.previousSibling; }
    get isConnected() { let n = this; while (n.parentNode) n = n.parentNode; return n === doc.documentElement || n === doc; }
    get className() { return [...this.classList.s].join(" "); }
    set className(v) { this.classList.s = new Set(String(v).split(/\s+/).filter(Boolean)); }
    get textContent() { return this._testo + this.childNodes.map((c) => c.textContent).join(""); }
    set textContent(v) { this.childNodes = []; this._testo = String(v ?? ""); }
    get innerText() { return this.textContent; } set innerText(v) { this.textContent = v; }
    get innerHTML() { return this._html || ""; } set innerHTML(v) { this.childNodes = []; this._testo = ""; this._html = String(v); }
    get outerHTML() { return ""; }
    appendChild(c) { if (c.parentNode) c.parentNode.removeChild(c); c.parentNode = this; this.childNodes.push(c); return c; }
    append(...cs) { cs.forEach((c) => this.appendChild(typeof c === "object" ? c : doc.createTextNode(c))); }
    prepend(...cs) { cs.reverse().forEach((c) => this.insertBefore(typeof c === "object" ? c : doc.createTextNode(c), this.firstChild)); }
    insertBefore(c, rif) { if (c.parentNode) c.parentNode.removeChild(c); c.parentNode = this; const i = rif ? this.childNodes.indexOf(rif) : -1; if (i < 0) this.childNodes.push(c); else this.childNodes.splice(i, 0, c); return c; }
    removeChild(c) { const i = this.childNodes.indexOf(c); if (i >= 0) this.childNodes.splice(i, 1); c.parentNode = null; return c; }
    replaceChild(n, v) { this.insertBefore(n, v); this.removeChild(v); return v; }
    replaceChildren(...cs) { this.childNodes.forEach((c) => { c.parentNode = null; }); this.childNodes = []; this._testo = ""; this.append(...cs); }
    replaceWith(n) { if (this.parentNode) this.parentNode.replaceChild(n, this); }
    remove() { if (this.parentNode) this.parentNode.removeChild(this); }
    before(n) { if (this.parentNode) this.parentNode.insertBefore(n, this); }
    after(n) { if (this.parentNode) this.parentNode.insertBefore(n, this.nextSibling); }
    cloneNode() { const c = new Nodo(this.tagName); c._testo = this._testo; return c; }
    contains(n) { while (n) { if (n === this) return true; n = n.parentNode; } return false; }
    closest(sel) { let n = this; while (n && n.nodeType === 1) { if (combacia(n, sel)) return n; n = n.parentNode; } return null; }
    matches(sel) { return combacia(this, sel); }
    setAttribute(k, v) { this.attributes[k] = String(v); if (k === "id") this.id = String(v); if (k === "class") this.className = v; if (k.startsWith("data-")) this.dataset[k.slice(5).replace(/-(.)/g, (_, x) => x.toUpperCase())] = String(v); }
    getAttribute(k) { return k === "id" ? this.id || null : k === "class" ? this.className : (k in this.attributes ? this.attributes[k] : null); }
    hasAttribute(k) { return this.getAttribute(k) !== null; }
    removeAttribute(k) { delete this.attributes[k]; }
    toggleAttribute(k, f) { const on = f === undefined ? !this.hasAttribute(k) : !!f; if (on) this.attributes[k] = ""; else delete this.attributes[k]; return on; }
    addEventListener(t, f) { (this._h[t] = this._h[t] || []).push(f); }
    removeEventListener(t, f) { this._h[t] = (this._h[t] || []).filter((x) => x !== f); }
    dispatchEvent(ev) { lancia(this, ev.type, ev); return true; }
    click() { lancia(this, "click", evento("click", this)); }
    focus() {} blur() {} select() {} scrollIntoView() {} scrollTo() {} animate() { return { finished: Promise.resolve(), cancel() {}, onfinish: null }; }
    setPointerCapture() {} releasePointerCapture() {} requestFullscreen() { return Promise.resolve(); }
    getContext() { return ctx2d; }
    getBoundingClientRect() { return { left: 0, top: 0, right: 100, bottom: 100, width: 100, height: 100, x: 0, y: 0 }; }
    getClientRects() { return [this.getBoundingClientRect()]; }
    querySelector(s) { return this.querySelectorAll(s)[0] || null; }
    querySelectorAll(s) { const out = []; const visita = (n) => n.childNodes.forEach((c) => { if (c.nodeType === 1 && s.split(",").some((x) => combacia(c, x.trim()))) out.push(c); visita(c); }); visita(this); return out; }
    getElementsByTagName(t) { return this.querySelectorAll(t); }
    getElementsByClassName(c) { return this.querySelectorAll("." + c); }
    insertAdjacentElement(_, n) { this.appendChild(n); return n; }
    insertAdjacentText(_, t) { this.append(t); }
  }
  function combacia(n, sel) {
    sel = String(sel || "").trim().split(/\s+/).pop();
    if (!sel || sel === "*") return true;
    const m = sel.match(/^([a-zA-Z0-9-]*)((?:[#.][\w-]+)*)(\[.*\])?/);
    if (!m) return false;
    if (m[1] && n.tagName !== m[1].toUpperCase()) return false;
    for (const p of (m[2] || "").match(/[#.][\w-]+/g) || []) {
      if (p[0] === "#" && n.id !== p.slice(1)) return false;
      if (p[0] === "." && !n.classList.contains(p.slice(1))) return false;
    }
    return true;
  }
  function evento(tipo, bersaglio, extra = {}) {
    return Object.assign({ type: tipo, target: bersaglio, currentTarget: bersaglio, clientX: 50, clientY: 50, pageX: 50, pageY: 50, offsetX: 50, offsetY: 50, button: 0, buttons: 1, pointerId: 1, key: "Enter", code: "Enter", keyCode: 13, which: 13, touches: [{ clientX: 50, clientY: 50, pageX: 50, pageY: 50 }], changedTouches: [{ clientX: 50, clientY: 50, pageX: 50, pageY: 50 }], defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, stopPropagation() {}, stopImmediatePropagation() {} }, extra);
  }
  function lancia(n, tipo, ev) {
    for (let x = n; x; x = x.parentNode) {
      const ctx = { elemento: x, bersaglio: n, gestore: true };
      for (const f of [...((x._h || {})[tipo] || [])]) {
        try { ev.currentTarget = x; const r = f.call(x, ev); if (r && typeof r.catch === "function") r.catch((e) => nota(`tocco (${tipo}, promessa)`, e, ctx)); }
        catch (e) { nota(`tocco (${tipo})`, e, ctx); }
      }
      if (x === doc.documentElement) {
        const c2 = { bersaglio: n, gestore: true };
        for (const f of [...(doc._h[tipo] || []), ...(finestra._h[tipo] || [])]) {
          try { const r = f(ev); if (r && typeof r.catch === "function") r.catch((e) => nota(`${tipo} (promessa)`, e, c2)); } catch (e) { nota(tipo, e, c2); }
        }
      }
    }
  }
  const doc = { _h: {}, nodeType: 9, readyState: "complete", visibilityState: "visible", hidden: false, title: "",
    createElement: (t) => new Nodo(t), createElementNS: (_, t) => new Nodo(t),
    createTextNode: (t) => { const n = new Nodo("#text", 3); n._testo = String(t); return n; },
    createDocumentFragment: () => new Nodo("#fragment", 11),
    addEventListener(t, f) { (this._h[t] = this._h[t] || []).push(f); }, removeEventListener() {},
    getElementById: (id) => [doc.documentElement, ...doc.documentElement.querySelectorAll("*")].find((n) => n.id === id) || null,
    querySelector: (s) => doc.documentElement.querySelector(s), querySelectorAll: (s) => doc.documentElement.querySelectorAll(s),
    getElementsByTagName: (t) => doc.documentElement.querySelectorAll(t), getElementsByClassName: (c) => doc.documentElement.querySelectorAll("." + c),
    hasFocus: () => true, activeElement: null, fonts: { ready: Promise.resolve() } };
  doc.documentElement = new Nodo("html");
  doc.head = doc.documentElement.appendChild(new Nodo("head"));
  doc.body = doc.documentElement.appendChild(new Nodo("body"));
  doc.activeElement = doc.body;
  const radice = doc.body.appendChild(new Nodo("div"));
  radice.id = "gioco";
  // ── calliope finto ──
  const ascolti = { avvio: [], messaggio: [], chat: [], giocatori: [], pausa: [], fine_tempo: [], comando: [],
                    partita: [], autorevole: [], specchio: [], nome: [] };
  // I comandi a voce: quelli che Calliope ricava dalla macchina, e quelli che il motore dice
  // attivi adesso (all'inizio tutti); un nome non dichiarato è un errore
  const dichiarati = opzioni.macchina ? tuttiPiatti(opzioni.macchina, opzioni.minimo || 1, opzioni.massimo || 1) : [];
  let attivi = dichiarati.slice();
  const avvio = { partita: "P1", giocatore: 1, giocatori: opzioni.giocatori || 1, massimo: Math.max(opzioni.massimo || 1, opzioni.giocatori || 1), condivisa: false, storia: [], lingua: "it",
    // la ripresa dopo «Riapri» e la partita condivisa con il motore (14/10), per le prove di
    // Calliope
    ...(opzioni.ripresa ? { ripresa: opzioni.ripresa } : {}),
    ...(opzioni.ruolo ? { ruolo: opzioni.ruolo } : {}), ...(opzioni.stato ? { stato: opzioni.stato } : {}) };
  const dati = {};
  const detti = [];                // le frasi che il gioco fa dire a Calliope (calliope.di)
  const quando = (t) => (f) => { if (typeof f === "function") ascolti[t].push(f); };
  const calliope = Object.freeze({
    quandoPronto: (f) => { if (typeof f === "function") ascolti.avvio.push(f); },
    quandoMessaggio: quando("messaggio"), quandoChat: quando("chat"), quandoGiocatori: quando("giocatori"),
    quandoPausa: quando("pausa"), quandoFineTempo: quando("fine_tempo"),
    salva: (k, v) => { dati[k] = JSON.parse(JSON.stringify(v ?? null)); return Promise.resolve(null); },
    leggi: (k) => Promise.resolve(k in dati ? dati[k] : null),
    manda: () => {}, chat: () => Promise.resolve(null), di: (t) => { detti.push(String(t ?? "")); return Promise.resolve(null); },
    azione: () => Promise.resolve(null), fine: () => {}, risorsa: () => "data:image/svg+xml;base64,PHN2Zy8+",
  });
  // ── finestra ──
  const finestra = { _h: {}, addEventListener(t, f) { (this._h[t] = this._h[t] || []).push(f); }, removeEventListener() {} };
  const g = Object.assign(Object.create(null), {
    window: null, self: null, document: doc, calliope, console,
    setTimeout: (f, ms) => metti(f, ms, false), clearTimeout: (id) => timer.delete(id),
    setInterval: (f, ms) => metti(f, ms, true), clearInterval: (id) => timer.delete(id),
    requestAnimationFrame: (f) => metti(f, 16, false), cancelAnimationFrame: (id) => timer.delete(id),
    queueMicrotask, structuredClone,
    performance: { now: () => adesso }, innerWidth: 1024, innerHeight: 768, devicePixelRatio: 1,
    navigator: { language: "it-IT", userAgent: "fumo", maxTouchPoints: 5 }, location: { href: "about:srcdoc", hash: "" },
    getComputedStyle: () => ({ getPropertyValue: () => "" }), matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
    addEventListener: (t, f) => finestra.addEventListener(t, f), removeEventListener() {},
    Image: function () { return new Nodo("img"); }, Audio: function () { return { play: () => Promise.resolve(), pause() {}, load() {}, addEventListener() {} }; },
    AudioContext: function () { return new Proxy({ currentTime: 0, sampleRate: 48000, destination: {}, state: "running", resume: () => Promise.resolve() }, { get: (o, k) => (k in o ? o[k] : () => new Proxy({ connect() {}, disconnect() {}, start() {}, stop() {}, frequency: { value: 0, setValueAtTime() {}, linearRampToValueAtTime() {}, exponentialRampToValueAtTime() {} }, gain: { value: 1, setValueAtTime() {}, linearRampToValueAtTime() {}, exponentialRampToValueAtTime() {} } }, { get: (x, kk) => (kk in x ? x[kk] : () => {}) })) }); },
    HTMLElement: Nodo, Element: Nodo, Node: Nodo, Event: function (t, o) { return evento(t, null, o || {}); }, CustomEvent: function (t, o) { return evento(t, null, { detail: (o || {}).detail }); },
  });
  g.window = g.self = g.globalThis = g;
  g.webkitAudioContext = g.AudioContext;
  // Il canale riservato al motore, come nel riquadro (scheda.RUNTIME_JS): il motore lo prende e
  // lo toglie prima del codice del gioco
  const palchi = [];
  const istantanee = [];           // le istantanee mandate a Calliope (14/10), le ultime
  const riprese = [];              // lo stato per la ripresa mandato con ognuna
  const mosse = [];                // le mosse di uno specchio (partita condivisa)
  const rifiutati = [];
  g.__calliopeMotore = Object.freeze({
    // L'istantanea (14/10, passo 2): i comandi a voce attivi sono i suoi; un nome non
    // dichiarato è un errore (il server la scarterebbe)
    stato: (ist, ripresa) => {
      riprese.push(ripresa === undefined ? null : JSON.parse(JSON.stringify(ripresa)));
      riprese.splice(0, Math.max(0, riprese.length - 50));
      const l = ist && Array.isArray(ist.comandi) ? ist.comandi.map(String) : [];
      const fuori = l.filter((x) => !dichiarati.includes(x));
      if (fuori.length) nota("istantanea", new Error(`comandi che la macchina del manifesto non ha: ${fuori.join(", ")}`));
      else attivi = l;
      istantanee.push(JSON.parse(JSON.stringify(ist)));
      istantanee.splice(0, Math.max(0, istantanee.length - 50));
    },
    rifiutato: (x) => { rifiutati.push(JSON.parse(JSON.stringify(x || {}))); },
    quandoComando: quando("comando"),
    quandoPartita: quando("partita"), quandoAutorevole: quando("autorevole"), quandoSpecchio: quando("specchio"),
    quandoNome: quando("nome"),
    mossa: (x) => { mosse.push(JSON.parse(JSON.stringify(x || {}))); },
    palco: (d) => { palchi.push(d); },
  });
  const contesto = vm.createContext(g, { codeGeneration: { strings: false, wasm: false } });
  // Il caso del gioco con un seme fisso (12/10 sera): la stessa partita a ogni esecuzione
  vm.runInContext("Math", contesto).random = creaCaso(opzioni.seme ?? 12345);
  notaCorrente = nota;
  if (!ascolto) {
    process.on("unhandledRejection", (e) => { if (notaCorrente) notaCorrente("promessa", e); });
    ascolto = true;
  }
  const amb = { errori, nota, nodi, radice, doc, tocchi, descrivi, lancia, evento, avanza,
                respira, ascolti, attivi: () => attivi, dati, detti, caricato: false,
                motore: null, giocoLogica: undefined, contesto, palchi, istantanee, rifiutati, riprese, mosse };
  for (const f of file) {
    try { testi[base(f)] = readFileSync(f, "utf8"); } catch (e) { testi[base(f)] = ""; }
  }
  // La macchina a stati (13/10): il motore prima degli script del gioco, l'avvio dopo, come nel
  // riquadro (scheda.documento); gli errori del motore (una mossa che lancia, una forma
  // sbagliata) arrivano qui invece che al riquadro. Dal 14/10 un gioco senza macchina non c'è più
  const macchina = opzioni.macchina || null;
  if (!macchina) {
    nota("manifesto", new Error("nel manifesto manca «scheda.macchina»: un gioco si scrive con la "
      + "macchina a stati di Calliope (le fasi e i comandi nel manifesto, const GIOCO = {…} in "
      + "logica.js; niente gioco.js né «ascolta»: il disegno, i pulsanti e la voce sono di Calliope)"));
    return amb;
  }
  g.__notaMotore = (e) => nota("motore", e);
  try { vm.runInContext(testoMotore(), contesto, { filename: "motore_gioco.js", timeout: 2000 }); }
  catch (e) { nota("caricamento del motore", e); return amb; }
  for (const f of file) {
    try { vm.runInContext(testi[base(f)], contesto, { filename: f, timeout: 2000 }); }
    catch (e) { nota(`caricamento di ${base(f)}`, e, { file: base(f) }); return amb; }
  }
  {
    const conf = JSON.stringify({ macchina, giocatori: { min: opzioni.minimo || 1, max: opzioni.massimo || 1 } });
    try {
      vm.runInContext(`CalliopeMotore.avvia(typeof GIOCO === "undefined" ? undefined : GIOCO, ${conf}, { errore: __notaMotore, titolo: ${JSON.stringify(opzioni.titolo || "")}, finto: true });`,
        contesto, { filename: "avvio", timeout: 2000 });
      amb.motore = vm.runInContext("CalliopeMotore", contesto);
      amb.giocoLogica = vm.runInContext("typeof GIOCO === 'undefined' ? undefined : GIOCO", contesto);
    } catch (e) { nota("avvio del motore", e); return amb; }
  }
  amb.caricato = true;
  lancia(doc.documentElement, "DOMContentLoaded", evento("DOMContentLoaded", doc));
  lancia(doc.documentElement, "load", evento("load", doc));
  for (const f of ascolti.avvio) {
    try { const r = f(avvio); if (r && typeof r.catch === "function") r.catch((e) => nota("quandoPronto (promessa)", e)); }
    catch (e) { nota("quandoPronto", e); }
  }
  await respira();
  avanza(1500);
  await respira();
  if (!nodi.some((n) => n !== radice && n.nodeType === 1 && n.isConnected && n.tagName !== "BODY" && n.tagName !== "HEAD" && n.tagName !== "HTML")
      && !radice._html && !radice._testo) {
    nota("disegno", "dopo l'avvio nel riquadro non c'è niente (il gioco disegna dentro <div id=\"gioco\">, dopo calliope.quandoPronto?)");
  }
  return amb;
}

// Tutti i comandi a voce piatti di una macchina («porta_3», «giocatori_2», «avanti»…): quelli che
// Calliope ricava dal manifesto (calliope/estensioni/macchina.py, ascolta)
export function tuttiPiatti(m, gmin, gmax) {
  const out = [];
  if (gmin < gmax) for (let i = gmin; i <= gmax; i++) out.push(`giocatori_${i}`);
  out.push("inizia", "avanti", "ancora", "anchio");
  const fasi = (m && m.fasi) || {};
  if (Object.values(fasi).some((f) => (f || {}).pagina === "tela")) out.push("fine_partita");
  for (const f of Object.values(fasi)) {
    for (const [c, d0] of Object.entries((f || {}).comandi || {})) {
      const d = Array.isArray(d0) ? {} : (d0 || {});
      let valori = null;
      if (d.n && d.n.valori) valori = Array.isArray(d.n.valori) ? d.n.valori : Object.keys(d.n.valori);
      else if (d.n) { valori = []; for (let i = Number(d.n.da); i <= Number(d.n.a); i++) valori.push(i); }
      for (const v of valori || [null]) {
        const p = v === null ? c : `${c}_${v}`;
        if (!out.includes(p)) out.push(p);
      }
    }
  }
  return out;
}

// Il testo che si vede nel riquadro (con quello scritto con innerHTML, senza i tag). Un elemento
// per pezzo, separati da uno spazio (dal 14/10 le scatole del palco sono elementi fratelli:
// «Porta 1» e «Porta 2» non diventano «Porta 1Porta 2»)
function testoNodo(n) {
  if (!n) return "";
  const figli = n.childNodes || [];
  return [String(n._testo || ""), String(n._html || "").replace(/<[^>]*>/g, " ")]
    .concat(figli.map(testoNodo)).join(" ");
}
function visibile(amb) {
  return testoNodo(amb.radice).replace(/\s+/g, " ").trim();
}

const TOCCHI = ["click", "pointerdown", "pointerup", "mousedown", "mouseup", "touchstart", "touchend"];

// ── La prova di fumo per fasi (13/10): l'esploratore della macchina dichiarata ──
// Visita in ampiezza gli stati (fase, turno, punti, dati) da ogni numero di giocatori, con ogni
// comando attivo e ogni valore (al più 5000 stati); poi 20 partite a caso (seme fisso) fino alla
// fine entro 500 passi. Gli errori dicono fase, comando, la strada (gli ultimi passi) e, se
// l'eccezione viene dalla logica, file:riga.
export function esplora(amb, opzioni = {}) {
  const { motore, giocoLogica } = amb;
  const errori = amb.errori;
  const nota = (dove, e) => amb.nota(dove, e);
  let nu;
  try {
    nu = motore.crea(giocoLogica, opzioni.macchina, { min: opzioni.minimo || 1, max: opzioni.massimo || 1 },
                     { titolo: opzioni.titolo || "" });
  } catch (e) { nota("macchina", e); return errori; }
  const M = nu.M;
  const strada = (s) => s.slice(-4).join(" → ") || "all'inizio";
  // Il palco (14/10): ogni pagina diversa, nei due orientamenti, una volta sola. Il primo
  // difetto ferma la prova (correggi quel punto), con la fase, la pagina e la strada
  const pagineViste = new Set();
  const palco = (S, s) => {
    let pag;
    try { pag = nu.pagina(S); } catch (e) { nota(`pagina della fase «${S.fase}» (strada: ${strada(s)})`, e); return false; }
    const k = JSON.stringify(pag);
    if (pagineViste.has(k)) return true;
    pagineViste.add(k);
    for (const O of ["orizzontale", "verticale"]) {
      const d = motore.difettiPalco(pag, O);
      if (d.length) {
        const e = new Error(d.join("; ") + ". La pagina la disegna Calliope: cambia i testi, i comandi attivi o il modello di pagina, non il disegno");
        e.name = "ErrorePalco";
        nota(`palco: fase «${S.fase}» (strada: ${strada(s)})`, e);
        return false;
      }
    }
    return true;
  };
  if (!palco(nu.nuovo(), [])) return errori;
  const chiave = (S) => JSON.stringify([S.fase, S.tocca, S.giocatori.map((x) => x.punti), S.dati, S.dopo, S.passa, S.giocatori.length]);
  const raggiunte = new Set();
  const attiviVisti = new Set();
  const visti = new Set();
  const coda = [];
  const coppie = (att) => {
    const out = [];
    for (const c of Object.keys(att)) {
      if (att[c] === true) out.push([c, null]); else for (const v of att[c]) out.push([c, v]);
    }
    return out;
  };
  const partenze = [];
  for (let n = M.gmin; n <= M.gmax; n++) partenze.push(M.gmin < M.gmax ? ["giocatori", n] : ["inizia", null]);
  for (const [c, v] of partenze) {
    try { coda.push({ S: nu.applica(nu.nuovo(), c, v), s: [nu.piatto(c, v)] }); }
    catch (e) { nota(`all'inizio della partita (${nu.piatto(c, v)})`, e); }
  }
  let completa = true;
  while (coda.length && !errori.length) {
    if (visti.size >= (opzioni.stati || 5000)) { completa = false; break; }
    const { S, s } = coda.shift();
    const k = chiave(S);
    if (visti.has(k)) continue;
    visti.add(k);
    raggiunte.add(S.fase);
    let att;
    try { att = nu.attivi(S); } catch (e) { nota(`fase «${S.fase}» (strada: ${strada(s)})`, e); continue; }
    try { nu.vista(S); } catch (e) { nota(`vista della fase «${S.fase}» (strada: ${strada(s)})`, e); continue; }
    if (!palco(S, s)) break;
    const cs = coppie(att);
    if (!cs.length && S.fase !== "fine") {
      nota(`fase «${S.fase}» senza uscita`, `nessun comando attivo (strada: ${strada(s)}): ogni fase che non è la fine deve avere almeno un comando attivo (GIOCO.attivi.${S.fase})`);
      continue;
    }
    for (const [c, v] of cs) {
      attiviVisti.add(`${S.fase}.${c}`);
      let S2;
      try { S2 = nu.applica(S, c, v, {}); }
      catch (e) { nota(`fase «${S.fase}», comando «${nu.piatto(c, v)}» (strada: ${strada(s)})`, e); break; }
      if (!visti.has(chiave(S2))) coda.push({ S: S2, s: s.concat([nu.piatto(c, v)]) });
    }
  }
  if (errori.length) return errori;
  // Partite intere, a caso con il seme fisso del caso del gioco
  const caso = vm.runInContext("Math", amb.contesto).random;
  // Con la visita in ampiezza al tetto (troppi stati) le fasi e i comandi si cercano anche in
  // molte più partite a caso, prima di dirli «mai raggiunti»
  const partite = (opzioni.partite || 20) + (completa ? 0 : (opzioni.partite_in_piu || 300));
  for (let i = 0; i < partite && !errori.length; i++) {
    const [c0, v0] = partenze[i % partenze.length];
    const s = [nu.piatto(c0, v0)];
    let S;
    try { S = nu.applica(nu.nuovo(), c0, v0); } catch (e) { nota("partita", e); break; }
    let passi = 0;
    while (S.fase !== "fine" && passi < 500) {
      raggiunte.add(S.fase);
      let cs;
      try { cs = coppie(nu.attivi(S)); } catch (e) { nota(`partita ${i + 1}, fase «${S.fase}» (strada: ${strada(s)})`, e); break; }
      if (!cs.length) break;
      for (const [c] of cs) attiviVisti.add(`${S.fase}.${c}`);
      if (!palco(S, s)) break;
      const [c, v] = cs[Math.floor(caso() * cs.length)];
      try { S = nu.applica(S, c, v, {}); } catch (e) { nota(`partita ${i + 1}, comando «${nu.piatto(c, v)}» (strada: ${strada(s)})`, e); break; }
      s.push(nu.piatto(c, v));
      passi++;
    }
    if (errori.length) break;
    raggiunte.add(S.fase);
    if (S.fase !== "fine") {
      nota(`partita ${i + 1}`, `non arriva alla fine in 500 passi, ferma in «${S.fase}» (strada: ${strada(s)}): quando la partita è finita una mossa deve portare alla fine (fase o dopo: "fine")`);
    }
  }
  if (errori.length) return errori;
  for (const f of Object.keys(M.fasi).concat(["fine"])) {
    if (!raggiunte.has(f)) nota(`fase «${f}»`, `dichiarata ma mai raggiunta: nessuna mossa ci porta (fase o dopo: "${f}", e «verso» nel manifesto)`);
  }
  for (const [f, d] of Object.entries(M.fasi)) {
    for (const c of Object.keys(d.comandi)) {
      if (raggiunte.has(f) && !attiviVisti.has(`${f}.${c}`)) nota(`comando «${f}.${c}»`, "dichiarato ma mai attivo (GIOCO.attivi lo esclude sempre)");
    }
  }
  return errori;
}

export async function fumo(file, opzioni = {}) {
  const amb = await prepara(file, opzioni);
  const { errori, nota, nodi, radice, doc, tocchi, descrivi, lancia, evento, avanza, respira, ascolti } = amb;
  if (!amb.caricato) return errori;
  if (opzioni.macchina) {
    if (!amb.motore) return errori;
    esplora(amb, opzioni);
    if (errori.length) return errori;
  }
  // Tocchi a caso, con il tempo che scorre (seme fisso: ripetibile)
  // (14/10: prima un generatore lineare con «seme % n», che con due elementi li alternava
  // sempre: con una tela e «Fine partita» il pulsante della tela non si toccava due volte)
  const casuale = creaCaso(12345);
  const caso = (n) => Math.floor(casuale() * n);
  for (let i = 0; i < (opzioni.tocchi || 300); i++) {
    const attivi = amb.attivi();
    const vivi = nodi.filter((n) => n.isConnected && TOCCHI.some((t) => (n._h[t] || []).length));
    if (!vivi.length && !(attivi.length && ascolti.comando.length)) break;
    if (!vivi.length) vivi.push(radice);
    const n = vivi[caso(vivi.length)];
    tocchi.push(descrivi(n));
    if (tocchi.length > 8) tocchi.shift();
    for (const t of TOCCHI) if ((n._h[t] || []).length) lancia(n, t, evento(t, n));
    if (attivi.length && ascolti.comando.length && caso(4) === 0) {
      // Una mossa a voce a caso tra i comandi attivi (11/10), come arriva dalla pagina
      const c = attivi[caso(attivi.length)];
      tocchi.push(`comando a voce «${c}»`);
      if (tocchi.length > 8) tocchi.shift();
      const dati = Object.freeze({ comando: c, ...(opzioni.giocatore ? { giocatore: "Ada" } : {}) });
      for (const f of [...ascolti.comando]) {
        try { const r = f(dati); if (r && typeof r.catch === "function") r.catch((e) => nota(`comando «${c}» (promessa)`, e, { gestore: true })); }
        catch (e) { nota(`comando «${c}»`, e, { gestore: true }); }
      }
    }
    if (i % 25 === 0) {
      const tasto = ["ArrowUp", "ArrowLeft", " ", "Enter"][caso(4)];
      tocchi.push(`tasto «${tasto}»`);
      for (const k of ["keydown", "keyup"]) lancia(doc.documentElement, k, evento(k, doc.body, { key: tasto }));
    }
    await respira();
    avanza(caso(3) === 0 ? 1200 : 150);
    await respira();
    // Il disegno leggibile (12/10 sera, ricerca 2026-10-12-flusso-agente-fasi): un campo che la
    // logica non dà («undefined», «NaN», «[object Object]») nel testo visibile è un errore, non
    // solo un'eccezione. Il caso vero del 12/10 mostrava «Nessun punto!» (non lo prende), ma è la
    // stessa classe: gioco.js che legge un campo nel posto sbagliato
    const strano = visibile(amb).match(/\bundefined\b|\bNaN\b|\[object Object\]/);
    if (strano) {
      nota("disegno", `dopo il tocco su ${tocchi[tocchi.length - 1] || "il gioco"} nel testo visibile c'è «${strano[0]}»: la pagina mostra un campo che la logica non dà (controlla i testi di GIOCO.vista e l'«esito» delle mosse in logica.js: la forma di ciò che restituisce logica.js)`);
    }
    if (errori.length) break;
  }
  return errori;
}

// ── I test del disegno (12/10 sera, ricerca 2026-10-12-flusso-agente-fasi § 5.1, passo 2) ──
// Il gioco vero (gli script di «scheda.file») nel DOM finto, da guidare in un test: nei test dei
// giochi c'è apriGioco(opzioni) (test_js.mjs), che chiama questa con i file del manifesto.
//   const g = await apriGioco({ giocatori: 2, seme: 7 });
//   await g.tocca("Inizia");               // per testo visibile, o un selettore (#id, .classe)
//   await g.tocca(".porta", 1);            // il secondo elemento che combacia
//   await g.scrivi("input", "Ada");         // un campo di testo (input e change)
//   await g.comando("porta", 3);           // un comando a voce attivo, con il valore dello slot
//   await g.avanza(1000);                  // il tempo finto passa (animazioni, timer)
//   g.testo()                              // il testo visibile nel riquadro, su una riga
//   g.stato(), g.palco()                   // l'istantanea della partita; i difetti del palco
//   g.trova(".punti")                      // gli elementi (textContent, disabled, className…)
//   g.detti, g.dati                        // le frasi fatte dire a Calliope, i dati salvati
// Un'eccezione che esce da un gestore durante tocca/comando/avanza fa fallire il test con
// file:riga, come nella prova di fumo. Un elemento disabilitato non riceve il tocco (come nel
// browser).
export async function apriGioco(file, opzioni = {}) {
  const amb = await prepara(file, opzioni);
  const { errori, nodi, radice, lancia, evento, avanza, respira, ascolti } = amb;
  const fallisci = (dove, da) => {
    if (errori.length > da) throw new Error(`${dove}: ${errori.slice(da).join(" | ")}`);
  };
  fallisci("all'avvio del gioco", 0);
  const vivo = (n) => n && n.nodeType === 1 && n.isConnected && radice.contains(n);
  const testoDi = (n) => String(n.textContent || n.value || n.getAttribute("aria-label")
    || n.getAttribute("title") || "").replace(/\s+/g, " ").trim();
  const gestori = (n, tipi) => {
    for (let x = n; x; x = x.parentNode) if (tipi.some((t) => ((x._h || {})[t] || []).length)) return true;
    return false;
  };
  function trova(cosa) {
    if (cosa && typeof cosa === "object" && cosa.tagName) return vivo(cosa) ? [cosa] : [];
    const s = String(cosa ?? "").trim();
    if (!s) return [];
    if (/^([#.][\w-]+|[a-z][a-z0-9-]*([#.][\w-]+)*)$/.test(s)) {
      const r = radice.querySelectorAll(s).filter(vivo);
      if (r.length) return r;
    }
    const tutti = nodi.filter(vivo);
    let c = tutti.filter((n) => testoDi(n) === s);
    if (!c.length) c = tutti.filter((n) => testoDi(n).includes(s));
    // Il più interno (il testo di un pulsante è anche quello del suo contenitore)
    return c.filter((n) => !c.some((m) => m !== n && n.contains(m)));
  }
  const DITO = ["pointerdown", "mousedown", "pointerup", "mouseup", "click"];
  const TOCCO = ["touchstart", "touchend"];
  async function passa(ms) {
    await respira();
    avanza(ms);
    await respira();
  }
  const g = {
    errori, detti: amb.detti, dati: amb.dati,
    testo: () => visibile(amb),
    trova,
    async tocca(cosa, indice = 0) {
      const tutti = trova(cosa);
      const ascoltano = tutti.filter((n) => gestori(n, [...DITO, ...TOCCO]));
      const n = (ascoltano.length ? ascoltano : tutti)[indice];
      if (!n) {
        throw new Error(`nessun elemento da toccare con «${cosa}»`
          + (tutti.length ? ` (ce ne sono ${tutti.length})` : "")
          + `: nel riquadro si legge «${visibile(amb).slice(0, 300)}»`);
      }
      if (n.disabled) return g;
      const da = errori.length;
      amb.tocchi.push(amb.descrivi(n));
      const tipi = gestori(n, TOCCO) && !gestori(n, DITO) ? TOCCO : DITO;
      for (const t of tipi) lancia(n, t, evento(t, n));
      await passa(opzioni.passo ?? 50);
      fallisci(`toccando «${cosa}»`, da);
      return g;
    },
    async scrivi(cosa, testo, indice = 0) {
      const n = trova(cosa)[indice];
      if (!n) throw new Error(`nessun campo «${cosa}»: nel riquadro si legge «${visibile(amb).slice(0, 300)}»`);
      const da = errori.length;
      n.value = String(testo ?? "");
      for (const t of ["input", "change"]) lancia(n, t, evento(t, n));
      await passa(opzioni.passo ?? 50);
      fallisci(`scrivendo in «${cosa}»`, da);
      return g;
    },
    // Con la macchina a stati (13/10): l'istantanea della partita (fase, a chi tocca, punti,
    // esito, comandi attivi), e i comandi con il valore: g.comando("porta", 3)
    stato() {
      if (!amb.motore || !amb.motore.partita) throw new Error("g.stato(): solo per un gioco con «scheda.macchina» nel manifesto");
      return JSON.parse(JSON.stringify(amb.motore.partita.istantanea()));
    },
    // Il palco (14/10): i difetti della pagina di adesso nei due orientamenti ([] = ci sta)
    palco() {
      if (!amb.motore || !amb.motore.partita) throw new Error("g.palco(): solo per un gioco con «scheda.macchina» nel manifesto");
      // (un elenco di questo contesto: quello del riquadro finto ha un altro Array, e
      // assert.deepStrictEqual(g.palco(), []) fallirebbe)
      return JSON.parse(JSON.stringify(amb.motore.partita.palco()));
    },
    async comando(nome, giocatore = "") {
      if (amb.motore && giocatore !== "" && (typeof giocatore === "number"
          || tuttiPiatti(opzioni.macchina, opzioni.minimo || 1, opzioni.massimo || 1).includes(`${nome}_${giocatore}`))) {
        nome = `${nome}_${giocatore}`;
        giocatore = "";
      }
      const attivi = amb.attivi();
      if (!attivi.includes(String(nome))) {
        // La fase di adesso (14/10 sera, banco delle porte L7 e L10: l'agente credeva che dopo
        // «2 giocatori» servisse «avanti», riscriveva la macchina e girava a vuoto)
        let fase = "";
        try { fase = amb.motore && amb.motore.partita ? amb.motore.partita.istantanea().fase : ""; } catch (e) { fase = ""; }
        const perche = String(nome) === "avanti" && fase && fase !== "esito"
          ? ": «avanti» vale solo nella fase «esito», dopo una mossa con un esito; dopo la scelta dei giocatori la partita è già nella fase d'inizio della macchina"
          : "";
        throw new Error(`il comando «${nome}» adesso non è attivo (${fase ? `fase «${fase}», ` : ""}attivi: ${attivi.join(", ") || "nessuno"})${perche}`);
      }
      const da = errori.length;
      const dati = Object.freeze({ comando: String(nome), ...(giocatore ? { giocatore: String(giocatore) } : {}) });
      for (const f of [...ascolti.comando]) {
        try { const r = f(dati); if (r && typeof r.catch === "function") r.catch((e) => amb.nota(`comando «${nome}» (promessa)`, e, { gestore: true })); }
        catch (e) { amb.nota(`comando «${nome}»`, e, { gestore: true }); }
      }
      await passa(opzioni.passo ?? 50);
      fallisci(`con il comando «${nome}»`, da);
      return g;
    },
    async avanza(ms = 1000) {
      const da = errori.length;
      await passa(ms);
      fallisci(`facendo passare ${ms} ms`, da);
      return g;
    },
  };
  // Per le prove di Calliope (14/10, non nel contratto dell'agente): le istantanee che il motore
  // ha mandato a Calliope, i comandi che ha rifiutato, e un comando a voce come lo manda il
  // server (con il numero dell'istantanea e il nome di chi gioca)
  Object.defineProperty(g, "calliope", { enumerable: false, value: Object.freeze({
    istantanee: () => JSON.parse(JSON.stringify(amb.istantanee)),
    rifiutati: () => JSON.parse(JSON.stringify(amb.rifiutati)),
    riprese: () => JSON.parse(JSON.stringify(amb.riprese)),
    mosse: () => JSON.parse(JSON.stringify(amb.mosse)),
    // un evento dal server sul canale del motore («partita», «autorevole», «nome»)
    async evento(tipo, dati) {
      for (const f of [...(ascolti[tipo] || [])]) {
        try { f(Object.freeze({ ...dati })); } catch (e) { amb.nota(tipo, e, { gestore: true }); }
      }
      await passa(opzioni.passo ?? 50);
      return g;
    },
    async comando(dati) {
      for (const f of [...ascolti.comando]) {
        try { f(Object.freeze({ ...dati })); } catch (e) { amb.nota("comando", e, { gestore: true }); }
      }
      await passa(opzioni.passo ?? 50);
      return g;
    },
  }) });
  return g;
}
