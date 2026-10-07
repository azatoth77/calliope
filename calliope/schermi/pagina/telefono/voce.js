// Calliope · telefono: l'ascolto e la voce nel browser.
//
// - Vad: Silero VAD (lo stesso ONNX di calliope/vad.py), finestre da 512 campioni con i 64
//   della precedente davanti;
// - WakeWord: la catena di calliope/wakeword.py (melspectrogram → embedding → classificatore
//   «Calliope»), a blocchi da 1280 campioni (80 ms), con gli stessi buffer iniziali;
// - Ascolto: la logica di audio.Listener (pre-roll, fine frase dal VAD, finestra di follow-up,
//   wake word, barge-in) sui blocchi del microfono;
// - Riproduttore: la voce di Piper a pezzi con Web Audio, frase dopo frase, con l'arresto
//   immediato e l'elenco delle frasi dette per intero (turno_finito).
//
// onnxruntime-web si carica da /telefono/ort/ (servito da Calliope, niente CDN), in
// WebAssembly con un thread solo: nessun worker, nessun SharedArrayBuffer.
"use strict";

export const SR = 16000;
export const FRAME = 512;
const CHUNK = 1280;
const MEL_WINDOW = 76;
const N_EMB = 16;
const MEL_CONTEXT = 480;
const CONTESTO_VAD = 64;

let ort = null;
export const misure = { inferenzaMs: 0, inferenze: 0, dal: performance.now() };

async function corri(sess, ingressi) {
  const t0 = performance.now();
  const out = await sess.run(ingressi);
  misure.inferenzaMs += performance.now() - t0;
  misure.inferenze++;
  return out;
}

export async function caricaOrt(wasm) {
  if (ort) return ort;
  ort = await import("/telefono/ort/ort.wasm.min.mjs");
  ort.env.wasm.numThreads = 1;
  ort.env.wasm.proxy = false;
  ort.env.wasm.wasmPaths = "/telefono/ort/";
  if (wasm) ort.env.wasm.wasmBinary = wasm;
  ort.env.logLevel = "error";
  return ort;
}

export async function sessione(dati) {
  return ort.InferenceSession.create(dati, {
    executionProviders: ["wasm"], graphOptimizationLevel: "all",
    intraOpNumThreads: 1, interOpNumThreads: 1,
  });
}

// ───────────────────────────── Silero VAD ─────────────────────────────
export class Vad {
  constructor(sess) {
    this.s = sess;
    this.sr = new ort.Tensor("int64", BigInt64Array.from([16000n]), []);
    this.reset();
  }

  reset() {
    this.stato = new Float32Array(2 * 128);
    this.contesto = new Float32Array(CONTESTO_VAD);
  }

  async prob(frame) {
    const x = new Float32Array(CONTESTO_VAD + frame.length);
    x.set(this.contesto);
    x.set(frame, CONTESTO_VAD);
    const out = await corri(this.s, {
      input: new ort.Tensor("float32", x, [1, x.length]),
      state: new ort.Tensor("float32", this.stato, [2, 1, 128]),
      sr: this.sr,
    });
    this.stato = new Float32Array(out.stateN.data);
    this.contesto = x.slice(x.length - CONTESTO_VAD);
    return out.output.data[0];
  }
}

// ───────────────────────────── wake word ─────────────────────────────
export class WakeWord {
  // `clf`: un classificatore o più (05/10, modalità: «Computer» e «Calliope» insieme, sulle
  // stesse feature): il punteggio è il più alto
  constructor(mel, emb, clf) {
    this.mel = mel;
    this.emb = emb;
    this.clfs = Array.isArray(clf) ? clf : [clf];
    this.clf = this.clfs[0];
  }

  async prepara() {
    // Come WakeWordDetector.reset: buffer pieni di «silenzio», poi ~2 s di rumore minimo
    // (senza, il passaggio all'audio vero poteva far scattare il classificatore). Lo stato
    // dopo il riscaldamento si tiene da parte: reset() lo ricopia senza rifare i conti
    const uni = new Float32Array(MEL_WINDOW * 32).fill(1);
    const zero = await this._embedding(uni);
    this.raw = new Float32Array(0);
    this.coda = new Float32Array(MEL_CONTEXT);
    this.melBuf = [];
    for (let i = 0; i < MEL_WINDOW; i++) this.melBuf.push(new Float32Array(32).fill(1));
    this.embBuf = [];
    for (let i = 0; i < N_EMB; i++) this.embBuf.push(zero);
    let seme = 12345;
    const caso = () => {                 // gaussiana approssimata, ripetibile
      let s = 0;
      for (let k = 0; k < 6; k++) { seme = (seme * 1103515245 + 12345) & 0x7fffffff; s += seme / 0x7fffffff; }
      return (s - 3) * 1.414;
    };
    for (let i = 0; i < 25; i++) {
      const b = new Float32Array(CHUNK);
      for (let j = 0; j < CHUNK; j++) b[j] = caso() * 3e-4;
      await this._passo(b);
    }
    this.iniziale = { coda: this.coda.slice(), mel: this.melBuf.map((a) => a), emb: this.embBuf.map((a) => a) };
    this.reset();
  }

  reset() {
    const s = this.iniziale;
    this.raw = new Float32Array(0);
    this.coda = s.coda.slice();
    this.melBuf = s.mel.slice();
    this.embBuf = s.emb.slice();
  }

  async _embedding(mel76) {
    const out = await corri(this.emb, { input_1: new ort.Tensor("float32", mel76, [1, MEL_WINDOW, 32, 1]) });
    const v = out[this.emb.outputNames[0]].data;
    return new Float32Array(v.subarray ? v.subarray(0, 96) : v.slice(0, 96));
  }

  async _passo(blocco) {
    const x = new Float32Array(MEL_CONTEXT + CHUNK);
    x.set(this.coda);
    x.set(blocco, MEL_CONTEXT);
    this.coda = x.slice(x.length - MEL_CONTEXT);
    const s = new Float32Array(x.length);
    for (let i = 0; i < x.length; i++) s[i] = x[i] * 32767;
    const m = await corri(this.mel, { input: new ort.Tensor("float32", s, [1, s.length]) });
    const md = m[this.mel.outputNames[0]].data;
    const nf = md.length / 32;
    for (let f = 0; f < nf; f++) {
      const r = new Float32Array(32);
      for (let j = 0; j < 32; j++) r[j] = md[f * 32 + j] / 10 + 2;
      this.melBuf.push(r);
    }
    while (this.melBuf.length > MEL_WINDOW) this.melBuf.shift();
    const finestra = new Float32Array(MEL_WINDOW * 32);
    for (let i = 0; i < MEL_WINDOW; i++) finestra.set(this.melBuf[i], i * 32);
    this.embBuf.push(await this._embedding(finestra));
    while (this.embBuf.length > N_EMB) this.embBuf.shift();
    const feats = new Float32Array(N_EMB * 96);
    for (let i = 0; i < N_EMB; i++) feats.set(this.embBuf[i], i * 96);
    let best = -Infinity;
    for (const c of this.clfs) {
      const o = await corri(c, { [c.inputNames[0]]: new ort.Tensor("float32", feats, [1, N_EMB, 96]) });
      best = Math.max(best, o[c.outputNames[0]].data[0]);
    }
    return best;
  }

  // Blocchi di qualunque lunghezza: il punteggio più alto dei blocchi da 80 ms completati,
  // oppure null se non ne è finito nessuno
  async process(frame) {
    const r = new Float32Array(this.raw.length + frame.length);
    r.set(this.raw);
    r.set(frame, this.raw.length);
    this.raw = r;
    let best = null;
    while (this.raw.length >= CHUNK) {
      const b = this.raw.slice(0, CHUNK);
      this.raw = this.raw.slice(CHUNK);
      const s = await this._passo(b);
      best = best === null ? s : Math.max(best, s);
    }
    return best;
  }
}

// ───────────────────────────── pause (solo misura) ─────────────────────────────
// Come calliope/pause.py MisuraPause (07/10): le pause dentro la frase (silenzi tra
// PAUSA_MIN_MS e silence_ms) e il parlato, dal conteggio dei frame silenziosi dello stesso VAD
// che chiude il turno. Vanno al server con «frase_finita»; non cambiano nulla dell'ascolto.
export const PAUSA_MIN_MS = 120;
export class MisuraPause {
  constructor(frameMs) { this.fms = frameMs; this.pause = []; this.frames = 0; this.corsa = 0; }
  frame(silenzioso) {
    this.frames++;
    if (silenzioso) { this.corsa++; return; }
    if (this.corsa) {
      const ms = this.corsa * this.fms;
      if (ms >= PAUSA_MIN_MS && this.pause.length < 60) this.pause.push(Math.round(ms));
      this.corsa = 0;
    }
  }
  parlatoMs(silenzioFinale) { return Math.round(Math.max(0, this.frames - silenzioFinale) * this.fms); }
}

// ───────────────────────────── ascolto ─────────────────────────────
// I blocchi del microfono arrivano con push(); listen/registra/veglia li consumano in ordine.
export class Ascolto {
  constructor(param) {
    this.p = param;            // parametri del server (calliope.yaml): soglie e tempi
    this.coda = [];
    this.attesa = null;
    this.recenti = [];         // pre-roll: gli ultimi blocchi anche fuori dall'ascolto
    this.vad = null;
    this.wake = null;
    this.occupato = false;
    this.scartati = 0;         // blocchi persi perché l'inferenza non stava dietro (diagnostica)
  }

  get frameMs() { return FRAME / SR * 1000; }

  push(frame) {
    const maxPre = Math.max(1, Math.round(this.p.preroll_ms / this.frameMs));
    this.recenti.push(frame);
    if (this.recenti.length > maxPre) this.recenti.shift();
    if (!this.occupato) return;
    this.coda.push(frame);
    if (this.coda.length > 400) { this.coda.shift(); this.scartati++; }   // ~13 s: l'inferenza non sta dietro
    if (this.attesa) { const f = this.attesa; this.attesa = null; f(); }
  }

  _prossimo(ms) {
    if (this.coda.length) return Promise.resolve(this.coda.shift());
    return new Promise((ok) => {
      const t = setTimeout(() => { this.attesa = null; ok(null); }, ms);
      this.attesa = () => { clearTimeout(t); ok(this.coda.shift() || null); };
    });
  }

  _inizia(svuota) {
    if (svuota) this.coda = [];
    this.occupato = true;
  }

  ferma() {
    this.occupato = false;
    this.coda = [];
    if (this.attesa) { const f = this.attesa; this.attesa = null; f(); }
  }

  // Come Listener.listen. o: {wake (bool), fino (ms, performance.now), seme (blocchi già
  // della frase), forza() (tocco: la frase comincia ora), sveglia() (smettere se nessuno
  // parla), basta() (fermare tutto), onAudio(blocchi), onInizio(), onFine()}.
  // Restituisce {audio: [blocchi], inizio, woke, punteggio, pause, parlato, chiusura} oppure
  // null (pause, parlato e chiusura: solo misura, 07/10).
  async listen(o) {
    const p = this.p;
    const fms = this.frameMs;
    const maxPre = Math.max(1, Math.round(p.preroll_ms / fms));
    const wake = o.wake ? this.wake : null;
    let preroll = this.recenti.slice(-maxPre);
    this.recenti = [];
    this._inizia(!o.seme);
    if (wake) wake.reset();
    if (this.vad) this.vad.reset();
    let parlato = [], silenzio = 0, parla = false, sentito = false, forzata = false;
    let segnalata = false, inviati = 0, streak = 0;
    let misura = new MisuraPause(fms);
    const r = { inizio: 0, woke: false, punteggio: 0 };
    if (o.seme && o.seme.length) {
      parla = true; sentito = true; parlato = o.seme.slice();
      misura.frames = parlato.length;
      r.inizio = performance.now() - parlato.length * fms;
      r.woke = true; r.punteggio = 1;
    }
    const perMe = () => !wake || r.inizio <= o.fino || r.woke;
    try {
      for (;;) {
        if (o.basta && o.basta()) return null;
        if (!parla && o.sveglia && o.sveglia()) return null;
        if (!parla && o.forza && o.forza()) {
          // Tocco: la frase comincia adesso (con il pre-roll), e vale come il nome
          parla = true; forzata = true; parlato = preroll.slice(); silenzio = 0;
          r.inizio = performance.now() - parlato.length * fms;
          r.woke = true; r.punteggio = 1;
        }
        const frame = await this._prossimo(1000);
        if (frame === null) continue;          // microfono fermo: si aspetta (lo dice la pagina)
        const prob = this.vad ? await this.vad.prob(frame) : 0;
        if (wake) {
          const s = await wake.process(frame);
          if (s !== null) {
            streak = s >= p.wake_threshold ? streak + 1 : 0;
            if (parla) {
              r.punteggio = Math.max(r.punteggio, s);
              if (streak >= p.wake_consecutive) {
                // Suono d'inizio ascolto (04/10): solo allo scatto a Calliope addormentata
                if (!r.woke && r.inizio > o.fino && o.onSveglia) {
                  try { o.onSveglia(); } catch (e) { /* un suono non ferma l'ascolto */ }
                }
                r.woke = true;
              }
            }
          }
        }
        if (!parla) {
          preroll.push(frame);
          if (preroll.length > maxPre) preroll.shift();
          if (prob >= p.vad_threshold) {
            parla = true; sentito = true; parlato = preroll.slice(); silenzio = 0;
            misura = new MisuraPause(fms); misura.frames = 1;   // il frame che l'ha fatta partire
            r.inizio = performance.now() - parlato.length * fms;
            r.woke = false; r.punteggio = 0;
          }
          continue;
        }
        parlato.push(frame);
        if (prob >= p.vad_threshold && !sentito) { sentito = true; misura = new MisuraPause(fms); }
        if (!segnalata && perMe()) {
          segnalata = true;
          if (o.onInizio) o.onInizio();
        }
        if (segnalata && o.onAudio) {
          o.onAudio(parlato.slice(inviati));
          inviati = parlato.length;
        }
        // Dopo un tocco il silenzio conta solo da quando si è sentita la voce: la persona ha
        // bisogno di un attimo per cominciare
        if (!forzata || sentito) {
          silenzio = prob < p.vad_threshold - 0.15 ? silenzio + 1 : 0;
          misura.frame(silenzio > 0);
        }
        const lunga = parlato.length * fms >= p.max_utterance_s * 1000;
        const muta = forzata && !sentito && parlato.length * fms >= 6000;
        const rilascio = !!(o.fine && o.fine());
        const fine = rilascio || lunga || muta || silenzio * fms >= p.silence_ms;
        if (fine) {
          const abbastanza = !muta && (parlato.length - silenzio) * fms >= p.min_speech_ms;
          if (abbastanza && perMe()) {
            r.audio = parlato;
            r.pause = misura.pause.slice();
            r.parlato = misura.parlatoMs(silenzio);
            r.chiusura = rilascio ? "rilascio" : silenzio * fms >= p.silence_ms ? "silenzio" : "lunga";
            return r;
          }
          if (segnalata && o.onFine) o.onFine();
          segnalata = false; inviati = 0;
          if (forzata) return null;            // tocco senza voce: finita
          parla = false; parlato = []; silenzio = 0; preroll = [];
          misura = new MisuraPause(fms);
          if (this.vad) this.vad.reset();
        }
      }
    } finally {
      this.ferma();
    }
  }

  // Come Listener.watch_for_name (livello A): mentre Calliope parla si ascolta solo il nome.
  // Restituisce gli ultimi barge_in_seed_s secondi (il seme della frase) o null.
  async veglia(o) {
    const p = this.p;
    const fms = this.frameMs;
    const anello = [];
    const maxAnello = Math.round(p.barge_in_seed_s * 1000 / fms);
    if (!this.wake) return null;
    this.wake.reset();
    this._inizia(true);
    let streak = 0;
    try {
      while (!o.basta()) {
        const frame = await this._prossimo(100);
        if (frame === null) continue;
        anello.push(frame);
        if (anello.length > maxAnello) anello.shift();
        const s = await this.wake.process(frame);
        if (s === null) continue;
        if (o.muto()) { streak = 0; continue; }
        streak = s >= p.barge_in_threshold ? streak + 1 : 0;
        if (streak >= p.wake_consecutive) return anello;
      }
      return null;
    } finally {
      this.ferma();
    }
  }
}

// ───────────────────────────── riproduzione ─────────────────────────────
export class Riproduttore {
  constructor(nome) {
    this.nomi = [(nome || "Calliope").toLowerCase()];   // le parole che svegliano
    this.ctx = null;
    this.frasi = new Map();
    this.ordine = [];
    this.prossimo = 0;
    this.sorgenti = [];
    this.scartaFino = 0;
    this.ultimoTurno = 0;
    this.byte = 0;
    // (id della frase, secondi a quando si sentirà) al primo pezzo messo in coda (07/10):
    // la pagina manda «suona» come il satellite, e il server scrive `prima_voce_s`
    this.onSuona = null;
  }

  contesto() {
    if (!this.ctx) {
      const C = window.AudioContext || window.webkitAudioContext;
      this.ctx = new C({ latencyHint: "interactive" });
    }
    return this.ctx;
  }

  attivo() { return !!this.ctx && this.ctx.state === "running"; }

  // Un contesto nuovo alla prossima frase (a riproduzione ferma): su iOS l'hardware può aver
  // cambiato frequenza quando è partito il microfono
  rifai() {
    if (!this.ctx) return;
    try { this.ctx.close(); } catch (e) { /* già chiuso */ }
    this.ctx = null;
    this.sorgenti = [];
    this.prossimo = 0;
    for (const f of this.ordine) { f.inizio = null; f.fine = 0; }
  }

  async sblocca() {
    const c = this.contesto();
    if (c.state !== "running") { try { await c.resume(); } catch (e) { /* serve un tocco */ } }
    return c.state === "running";
  }

  nuovaSessione() {
    this.ferma(Infinity);
    this.frasi.clear();
    this.ordine = [];
    this.scartaFino = 0;
    this.ultimoTurno = 0;
  }

  frase(turno, id, testo, rate, totale) {
    this.ultimoTurno = Math.max(this.ultimoTurno, turno);
    const f = { turno, id, testo, rate, totale, ricevuti: 0, inizio: null, fine: 0, interrotta: false, avanzo: null };
    this.frasi.set(id, f);
    this.ordine.push(f);
  }

  pezzo(id, byte) {
    const f = this.frasi.get(id);
    if (!f || f.turno <= this.scartaFino || f.interrotta) return;
    const c = this.contesto();
    let b = byte;
    if (f.avanzo) { const u = new Uint8Array(f.avanzo.length + b.length); u.set(f.avanzo); u.set(b, f.avanzo.length); b = u; f.avanzo = null; }
    if (b.length % 2) { f.avanzo = b.slice(b.length - 1); b = b.slice(0, b.length - 1); }
    f.ricevuti += byte.length;
    this.byte += byte.length;
    const n = b.length / 2;
    if (!n) return;
    const dv = new DataView(b.buffer, b.byteOffset, b.length);
    const buf = c.createBuffer(1, n, f.rate);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < n; i++) ch[i] = dv.getInt16(i * 2, true) / 32768;
    const src = c.createBufferSource();
    src.buffer = buf;
    src.connect(c.destination);
    const t = Math.max(this.prossimo, c.currentTime + 0.03);
    src.start(t);
    this.prossimo = t + n / f.rate;
    if (f.inizio === null) {
      f.inizio = t;
      if (this.onSuona) {
        // Quanto manca all'inizio programmato, più il ritardo dell'uscita del browser
        const uscita = Math.max(0, t - c.currentTime) + (c.outputLatency || c.baseLatency || 0);
        try { this.onSuona(f.id, uscita); } catch (e) { /* la misura non ferma la voce */ }
      }
    }
    f.fine = this.prossimo;
    const voce = { src, turno: f.turno, fine: this.prossimo };
    this.sorgenti.push(voce);
    src.onended = () => { const i = this.sorgenti.indexOf(voce); if (i >= 0) this.sorgenti.splice(i, 1); };
  }

  inCorso() { return !!this.ctx && this.prossimo > this.ctx.currentTime; }

  // Un segnale breve (inizio o fine ascolto), subito, fuori dalle frasi del turno
  segnale(byte, rate) {
    if (!this.attivo()) return;
    const c = this.ctx;
    const n = Math.floor(byte.length / 2);
    if (!n) return;
    const dv = new DataView(byte.buffer, byte.byteOffset, n * 2);
    const buf = c.createBuffer(1, n, rate);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < n; i++) ch[i] = dv.getInt16(i * 2, true) / 32768;
    const src = c.createBufferSource();
    src.buffer = buf;
    src.connect(c.destination);
    src.start(c.currentTime + 0.01);
  }

  // Smette subito e scarta il turno, anche ciò che arriverà dopo
  ferma(turno) {
    this.scartaFino = Math.max(this.scartaFino, turno === undefined ? this.ultimoTurno : turno);
    const ora = this.ctx ? this.ctx.currentTime : 0;
    for (const v of this.sorgenti.slice()) {
      if (v.turno <= this.scartaFino) { try { v.src.stop(); } catch (e) { /* già finita */ } }
    }
    this.sorgenti = this.sorgenti.filter((v) => v.turno > this.scartaFino);
    for (const f of this.ordine) {
      if (f.turno <= this.scartaFino && (f.fine > ora || f.ricevuti < f.totale)) f.interrotta = true;
    }
    if (!this.sorgenti.length) this.prossimo = ora;
  }

  // Come Riproduttore.saying_name del satellite: mentre dice il proprio nome (e 0,8 s dopo)
  // la wake word si ignora
  diceNome() {
    if (!this.ctx) return false;
    const ora = this.ctx.currentTime;
    return this.ordine.some((f) => f.inizio !== null
      && this.nomi.some((n) => f.testo.toLowerCase().includes(n))
      && f.inizio <= ora + 0.05 && ora <= f.fine + 0.8);
  }

  // Le frasi dette per intero da quando è finito il turno di prima; null finché suona
  dette() {
    const ora = this.ctx ? this.ctx.currentTime : Infinity;
    if (this.ctx && this.ctx.state === "running" && this.prossimo > ora + 0.01) return null;
    const out = this.ordine.filter((f) => !f.interrotta && f.ricevuti >= f.totale && f.testo
      && f.turno > this.scartaFino && f.fine <= ora + 0.01 && this.attivo()).map((f) => f.testo);
    this.ordine = this.ordine.filter((f) => f.fine > ora + 0.01);
    for (const [k, f] of this.frasi) if (!this.ordine.includes(f)) this.frasi.delete(k);
    return out;
  }
}
