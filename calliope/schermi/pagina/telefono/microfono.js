// Calliope · telefono: AudioWorklet del microfono. Riceve l'audio alla frequenza del
// contesto (di solito 48 000 o 44 100 Hz), lo filtra (passa-basso a ~7,2 kHz, sinc con
// finestra di Blackman) e lo ricampiona a 16 kHz; manda al thread della pagina blocchi da
// 512 campioni (32 ms), quelli che vogliono Silero VAD e la wake word.
//
// Dal 03/10 conta anche cosa arriva, per la pagina e per la diagnostica: i campioni
// d'ingresso (la pagina li confronta con l'orologio vero: un contesto che gira al ritmo
// sbagliato si vede subito), i blocchi da 128 tutti a zero (buchi) e quelli uguali al
// precedente (blocchi ripetuti), con un numero progressivo su ogni blocco da 512. Con
// {grezzo: true} manda anche il segnale com'è arrivato, prima del filtro.
"use strict";

const USCITA = 16000;
const BLOCCO = 512;
const GREZZO = 4096;

function filtro(rapporto) {
  if (rapporto <= 1.0001) return null;
  const n = Math.max(15, Math.round(rapporto * 10) | 1);   // dispari
  const taglio = 0.45 / rapporto;                          // in frazioni della frequenza d'ingresso
  const h = new Float32Array(n);
  const m = (n - 1) / 2;
  let somma = 0;
  for (let i = 0; i < n; i++) {
    const x = i - m;
    const sinc = x === 0 ? 2 * taglio : Math.sin(2 * Math.PI * taglio * x) / (Math.PI * x);
    const w = 0.42 - 0.5 * Math.cos(2 * Math.PI * i / (n - 1)) + 0.08 * Math.cos(4 * Math.PI * i / (n - 1));
    h[i] = sinc * w;
    somma += h[i];
  }
  for (let i = 0; i < n; i++) h[i] /= somma;
  return h;
}

class Microfono extends AudioWorkletProcessor {
  constructor() {
    super();
    this.passo = sampleRate / USCITA;
    this.h = filtro(this.passo);
    this.storia = new Float32Array(this.h ? this.h.length : 1);   // ultimi campioni grezzi
    this.k = 0;                                                    // indice circolare
    this.filtrati = new Float32Array(4096);
    this.nf = 0;                // campioni filtrati validi
    this.pos = 0;               // posizione (frazionaria) del prossimo campione in uscita
    this.uscita = new Float32Array(BLOCCO);
    this.nu = 0;
    this.picco = 0;
    this.n = 0;                 // blocchi da 512 mandati
    // conti per la pagina
    this.ingresso = 0;
    this.quanti = 0;
    this.zeri = 0;
    this.doppi = 0;
    this.vuoti = 0;             // chiamate senza ingresso (traccia ferma o scollegata)
    this.precedente = new Float32Array(128);
    this.ultimoConto = 0;
    this.grezzo = null;
    this.ng = 0;
    this.port.onmessage = (ev) => {
      const d = ev.data || {};
      if ("grezzo" in d) {
        // Marca d'inizio e di fine della registrazione (diagnostica): il primo blocco da 512
        // che ne fa parte e i campioni d'ingresso, così la pagina tiene esattamente quelli
        if (!d.grezzo && this.grezzo && this.ng) this.port.postMessage({ tipo: "grezzo", dati: this.grezzo.slice(0, this.ng) });
        this.grezzo = d.grezzo ? new Float32Array(GREZZO) : null;
        this.ng = 0;
        this.port.postMessage({ tipo: "marca", inizio: !!d.grezzo, n: this.n, ingresso: this.ingresso, t: currentTime });
      }
    };
    this.port.postMessage({ tipo: "pronto", rate: sampleRate });
  }

  conta(ch) {
    this.ingresso += ch.length;
    this.quanti++;
    let zero = true;
    for (let i = 0; i < ch.length; i++) if (ch[i] !== 0) { zero = false; break; }
    if (zero) this.zeri++;
    else if (this.precedente.length === ch.length) {
      let uguale = true;
      const p = this.precedente;
      for (let i = 0; i < ch.length; i++) if (ch[i] !== p[i]) { uguale = false; break; }
      if (uguale) this.doppi++;
    }
    if (this.precedente.length !== ch.length) this.precedente = new Float32Array(ch.length);
    this.precedente.set(ch);
    if (this.grezzo) {
      let i = 0;
      while (i < ch.length) {
        const n = Math.min(ch.length - i, GREZZO - this.ng);
        this.grezzo.set(ch.subarray(i, i + n), this.ng);
        this.ng += n;
        i += n;
        if (this.ng === GREZZO) {
          this.port.postMessage({ tipo: "grezzo", dati: this.grezzo });
          this.grezzo = new Float32Array(GREZZO);
          this.ng = 0;
        }
      }
    }
    // Ogni ~0,25 s di audio: i conti, con l'orologio del contesto
    if (this.ingresso - this.ultimoConto >= sampleRate / 4) {
      this.ultimoConto = this.ingresso;
      this.port.postMessage({ tipo: "conti", ingresso: this.ingresso, quanti: this.quanti,
        zeri: this.zeri, doppi: this.doppi, vuoti: this.vuoti, t: currentTime, n: this.n });
    }
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) { this.vuoti++; return true; }
    this.conta(ch);
    const h = this.h;
    for (let i = 0; i < ch.length; i++) {
      let y = ch[i];
      if (h) {
        const L = h.length;
        this.storia[this.k] = y;
        let acc = 0;
        let j = this.k;
        for (let t = 0; t < L; t++) {
          acc += h[t] * this.storia[j];
          j = j === 0 ? L - 1 : j - 1;
        }
        this.k = this.k + 1 === L ? 0 : this.k + 1;
        y = acc;
      }
      if (this.nf === this.filtrati.length) {
        const nuovo = new Float32Array(this.filtrati.length * 2);
        nuovo.set(this.filtrati);
        this.filtrati = nuovo;
      }
      this.filtrati[this.nf++] = y;
    }
    // Interpolazione lineare sul segnale già filtrato
    while (this.pos + 1 < this.nf) {
      const i = Math.floor(this.pos);
      const f = this.pos - i;
      const v = this.filtrati[i] * (1 - f) + this.filtrati[i + 1] * f;
      this.uscita[this.nu++] = v;
      const a = v < 0 ? -v : v;
      if (a > this.picco) this.picco = a;
      this.pos += this.passo;
      if (this.nu === BLOCCO) {
        this.port.postMessage({ frame: this.uscita, picco: this.picco, n: this.n++ });
        this.uscita = new Float32Array(BLOCCO);
        this.nu = 0;
        this.picco = 0;
      }
    }
    const via = Math.floor(this.pos);
    if (via > 0) {
      this.filtrati.copyWithin(0, via, this.nf);
      this.nf -= via;
      this.pos -= via;
    }
    return true;
  }
}

registerProcessor("calliope-microfono", Microfono);
