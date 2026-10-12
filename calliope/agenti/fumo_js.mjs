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
      if (d.length) consiglio = ` («${doppio[1]}» è dichiarato in ${d.join(" e ")}: tienilo in un file solo, o cambia nome in gioco.js)` + consiglio;
    }
    let t = dove + (ctx.elemento ? ` su ${descrivi(ctx.elemento)}` : "")
      + (ctx.bersaglio && ctx.bersaglio !== ctx.elemento ? ` (toccato ${descrivi(ctx.bersaglio)})` : "")
      + `: ${e && e.name ? e.name + ": " : ""}${msg.slice(0, 200)}`
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
  const ascolti = { avvio: [], messaggio: [], chat: [], giocatori: [], pausa: [], fine_tempo: [], comando: [] };
  // I comandi a voce (11/10, «ascolta» nel manifesto): quelli dichiarati, e quelli che il gioco
  // dice attivi adesso con comandiAttivi (all'inizio tutti); un nome non dichiarato è un errore
  const dichiarati = Object.keys(opzioni.comandi || {});
  let attivi = dichiarati.slice();
  const avvio = { partita: "P1", giocatore: 1, giocatori: 1, massimo: opzioni.massimo || 1, condivisa: false, storia: [], lingua: "it",
    ...(dichiarati.length ? { comandi: dichiarati.slice() } : {}) };
  const dati = {};
  const quando = (t) => (f) => { if (typeof f === "function") ascolti[t].push(f); };
  const calliope = Object.freeze({
    quandoPronto: (f) => { if (typeof f === "function") ascolti.avvio.push(f); },
    quandoMessaggio: quando("messaggio"), quandoChat: quando("chat"), quandoGiocatori: quando("giocatori"),
    quandoPausa: quando("pausa"), quandoFineTempo: quando("fine_tempo"), quandoComando: quando("comando"),
    comandiAttivi: (nomi) => {
      const l = Array.isArray(nomi) ? nomi.map(String) : [];
      const fuori = l.filter((x) => !dichiarati.includes(x));
      if (fuori.length && !dichiarati.length) nota("comandiAttivi", new Error("il manifesto non ha «ascolta.comandi»: dichiara lì i comandi a voce (scheda.ascolta), o togli comandiAttivi"));
      else if (fuori.length) nota("comandiAttivi", new Error(`comandi non dichiarati in «ascolta.comandi» del manifesto: ${fuori.join(", ")} (solo un sottoinsieme di ${dichiarati.join(", ")})`));
      else attivi = l;
    },
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
    try { testi[base(f)] = readFileSync(f, "utf8"); } catch (e) { testi[base(f)] = ""; }
  }
  for (const f of file) {
    try { vm.runInContext(testi[base(f)], contesto, { filename: f, timeout: 2000 }); }
    catch (e) { nota(`caricamento di ${base(f)}`, e, { file: base(f) }); return errori; }
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
    const visibile = String(radice.textContent || "") + " " + String(radice._html || "");
    const strano = visibile.match(/\bundefined\b|\bNaN\b|\[object Object\]/);
    if (strano) {
      nota("disegno", `dopo il tocco su ${tocchi[tocchi.length - 1] || "il gioco"} nel testo visibile c'è «${strano[0]}»: gioco.js mostra un campo che la logica non dà in quel posto (controlla la forma di ciò che restituisce logica.js)`);
    }
    if (errori.length) break;
  }
  return errori;
}
