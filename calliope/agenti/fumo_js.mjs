// La prova di fumo di una scheda interattiva (05/10/2026, calliope/estensioni/scheda.py): gli
// script del gioco caricati con un DOM finto semplice e l'oggetto `calliope` finto, poi
// centinaia di tocchi a caso sugli elementi che ascoltano, con il tempo che scorre. Un errore
// (variabile mai dichiarata, funzione sbagliata) diventa un test fallito: i test di logica.js
// non lo vedono, perché girano senza il disegno (prima prova vera sulla DGX: il memory
// dell'agente aveva «attesaRigira» mai dichiarata e nessun tocco funzionava).
// Usato da test_js.mjs; restituisce l'elenco degli errori.
import { readFileSync } from "node:fs";
import vm from "node:vm";

export async function fumo(file, opzioni = {}) {
  // Le promesse del gioco (async, await calliope.leggi) si risolvono solo tornando al ciclo
  const respira = () => new Promise((ok) => setImmediate(ok));
  const errori = [];
  // Un consiglio per gli errori che vengono dal modo in cui il riquadro carica gli script (seconda
  // prova vera sulla DGX, 05/10: gioco.js rifaceva «const { … } = require("./logica.js")», e
  // l'agente ha finito le passate senza capire perché)
  const CONSIGLI = [
    [/already been declared|require is not defined|Cannot use import|import statement|module is not defined/,
     " (nel riquadro gli script di «scheda.file» si caricano uno dopo l'altro nello stesso spazio "
     + "globale, come i <script> del browser: in gioco.js usa direttamente le funzioni di "
     + "logica.js, senza require, import né const { … } = …; require serve solo nei test)"],
    [/is not defined/, " (dichiara la variabile con let o const prima di usarla)"],
  ];
  const nota = (dove, e) => {
    const msg = String(e && e.message || e);
    const consiglio = (CONSIGLI.find(([rx]) => rx.test(msg)) || [null, ""])[1];
    if (errori.length < 5) errori.push(`${dove}: ${e && e.name ? e.name + ": " : ""}${msg.slice(0, 200)}${consiglio}`);
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
      for (const f of [...((x._h || {})[tipo] || [])]) {
        try { ev.currentTarget = x; const r = f.call(x, ev); if (r && typeof r.catch === "function") r.catch((e) => nota(`tocco (${tipo}, promessa)`, e)); }
        catch (e) { nota(`tocco (${tipo})`, e); }
      }
      if (x === doc.documentElement) {
        for (const f of [...(doc._h[tipo] || []), ...(finestra._h[tipo] || [])]) {
          try { const r = f(ev); if (r && typeof r.catch === "function") r.catch((e) => nota(`${tipo} (promessa)`, e)); } catch (e) { nota(tipo, e); }
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
  const ascolti = { avvio: [], messaggio: [], chat: [], giocatori: [], pausa: [], fine_tempo: [] };
  const avvio = { partita: "P1", giocatore: 1, giocatori: 1, massimo: opzioni.massimo || 1, condivisa: false, storia: [], lingua: "it" };
  const dati = {};
  const quando = (t) => (f) => { if (typeof f === "function") ascolti[t].push(f); };
  const calliope = Object.freeze({
    quandoPronto: (f) => { if (typeof f === "function") ascolti.avvio.push(f); },
    quandoMessaggio: quando("messaggio"), quandoChat: quando("chat"), quandoGiocatori: quando("giocatori"),
    quandoPausa: quando("pausa"), quandoFineTempo: quando("fine_tempo"),
    salva: (k, v) => { dati[k] = JSON.parse(JSON.stringify(v ?? null)); return Promise.resolve(null); },
    leggi: (k) => Promise.resolve(k in dati ? dati[k] : null),
    manda: () => {}, chat: () => Promise.resolve(null), di: () => Promise.resolve(null),
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
  const contesto = vm.createContext(g, { codeGeneration: { strings: false, wasm: false } });
  process.on("unhandledRejection", (e) => nota("promessa", e));
  for (const f of file) {
    try { vm.runInContext(readFileSync(f, "utf8"), contesto, { filename: f, timeout: 2000 }); }
    catch (e) { nota(`caricamento di ${f}`, e); return errori; }
  }
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
  // Tocchi a caso, con il tempo che scorre (seme fisso: ripetibile)
  let seme = 12345;
  const caso = (n) => { seme = (seme * 1103515245 + 12345) % 2147483648; return seme % n; };
  const TOCCHI = ["click", "pointerdown", "pointerup", "mousedown", "mouseup", "touchstart", "touchend"];
  for (let i = 0; i < (opzioni.tocchi || 300); i++) {
    const vivi = nodi.filter((n) => n.isConnected && TOCCHI.some((t) => (n._h[t] || []).length));
    if (!vivi.length) break;
    const n = vivi[caso(vivi.length)];
    for (const t of TOCCHI) if ((n._h[t] || []).length) lancia(n, t, evento(t, n));
    if (i % 25 === 0) for (const k of ["keydown", "keyup"]) lancia(doc.documentElement, k, evento(k, doc.body, { key: ["ArrowUp", "ArrowLeft", " ", "Enter"][caso(4)] }));
    await respira();
    avanza(caso(3) === 0 ? 1200 : 150);
    await respira();
    if (errori.length) break;
  }
  return errori;
}
