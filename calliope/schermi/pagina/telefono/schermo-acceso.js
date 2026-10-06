// Calliope · telefono: lo schermo resta acceso finché il microfono è acceso (04/10/2026).
// Una pagina web non può ascoltare a schermo spento: quando lo schermo si spegne iOS (e ogni
// browser) sospende la pagina e il microfono si ferma. Con la Screen Wake Lock API lo schermo
// non si spegne da solo; se il browser non la concede, o la toglie, la pagina lo dice.
//
// Cosa sappiamo di WebKit (iPhone e iPad: lì Edge e Chrome sono WebKit):
// - Safari ha la Screen Wake Lock API da iOS 16.4; WKWebView, cioè Edge e Chrome per iOS, da
//   iOS 18.4 (prima `navigator.wakeLock` non c'è);
// - nella web app aggiunta alla schermata Home, da 16.4 a 18.3 la richiesta riesce ma lo
//   schermo si spegne lo stesso (WebKit bug 254545, corretto in iOS 18.4): non si vede da
//   JavaScript, quindi si guarda la versione;
// - la prima richiesta vuole un gesto in corso (transient activation): va fatta subito nel
//   tocco, prima di aspettare il microfono; dopo una riuscita le richieste successive non
//   lo vogliono più (WebKit 263382@main, 2023), per esempio al ritorno in primo piano.

// iOS / iPadOS e la sua versione dall'user agent: [maggiore, minore] o null. Un iPad con
// l'user agent «da computer» (Macintosh con il touch) è iOS, ma la versione si legge solo
// da «Version/x.y» (Safari); Edge e Chrome lì non la dicono.
export function versioneIOS(ua, toccoMac) {
  ua = String(ua || "");
  let m = /\b(?:iPhone|iPad|iPod)\b.*?\bOS (\d+)[_.](\d+)/.exec(ua);
  if (m) return [Number(m[1]), Number(m[2])];
  if (/\b(?:iPhone|iPad|iPod)\b/.test(ua)) return [0, 0];       // iOS, versione ignota
  if (/Macintosh/.test(ua) && toccoMac) {
    m = /Version\/(\d+)\.(\d+)/.exec(ua);
    return m ? [Number(m[1]), Number(m[2])] : [0, 0];
  }
  return null;
}

const prima = (v, a, b) => v[0] < a || (v[0] === a && v[1] < b);

// Cosa aspettarsi su questo browser, prima di chiedere: {api, inaffidabile, motivo}.
// `inaffidabile`: la richiesta riesce ma lo schermo si spegne lo stesso (web app di iOS < 18.4).
export function diagnosi(o) {
  const ios = versioneIOS(o.ua, o.toccoMac);
  const nota = ios && ios[0] ? " (iOS " + ios[0] + "." + ios[1] + ")" : "";
  const regola = "imposta Blocco automatico su «Mai» (Impostazioni, Schermo e luminosità) finché guidi";
  if (!o.api) {
    if (ios && ios[0] && prima(ios, 18, 4)) {
      return { api: false, inaffidabile: false, motivo: "su iPhone Edge e Chrome tengono acceso lo schermo "
        + "solo da iOS 18.4" + nota + ": aggiorna iOS, apri Calliope in Safari, oppure " + regola };
    }
    if (ios) {
      return { api: false, inaffidabile: false, motivo: "questo browser non tiene acceso lo schermo"
        + nota + ": apri Calliope in Safari, oppure " + regola };
    }
    return { api: false, inaffidabile: false,
      motivo: "questo browser non sa tenere acceso lo schermo: allunga lo spegnimento automatico nelle impostazioni" };
  }
  if (ios && ios[0] && o.standalone && prima(ios, 18, 4)) {
    return { api: true, inaffidabile: true, motivo: "nella web app sulla schermata Home iOS prima della 18.4"
      + nota + " lascia spegnere lo schermo lo stesso: aggiorna iOS, apri Calliope nel browser, oppure " + regola };
  }
  return { api: true, inaffidabile: false, motivo: "" };
}

// Stati: «spento» (non serve), «chiedo», «acceso», «negato» (il browser ha detto no),
// «manca» (niente API), «caduto» (tolto dal sistema e non ripreso).
export class SchermoAcceso {
  constructor(o) {
    o = o || {};
    this.nav = o.nav || navigator;
    this.doc = o.doc || document;
    this.onCambio = o.onCambio || (() => {});
    const standalone = o.standalone !== undefined ? o.standalone
      : (this.nav.standalone === true
        || (typeof matchMedia === "function" && matchMedia("(display-mode: standalone)").matches));
    this.info = diagnosi({
      api: !!(this.nav.wakeLock && typeof this.nav.wakeLock.request === "function"),
      ua: o.ua !== undefined ? o.ua : this.nav.userAgent,
      toccoMac: (this.nav.maxTouchPoints || 0) > 1, standalone,
    });
    this.voluto = false;
    this.stato = "spento";
    this.motivo = "";
    this.sentinella = null;
    this.inCorso = null;           // la richiesta partita e non ancora finita
    this.richieste = 0;            // per le prove e la diagnostica
    this.cadute = 0;
    this.daQuando = null;          // performance.now() dell'ultima riuscita
  }

  _imposta(stato, motivo) {
    if (stato === this.stato && (motivo || "") === this.motivo) return;
    this.stato = stato;
    this.motivo = motivo || "";
    try { this.onCambio(this); } catch (e) { /* l'interfaccia non ferma lo schermo */ }
  }

  // Da chiamare SUBITO nel gestore del tocco (prima di ogni await): la prima richiesta di
  // WebKit vuole il gesto in corso
  vuoi(acceso) {
    if (!acceso) {
      this.voluto = false;
      const s = this.sentinella;
      this.sentinella = null;
      if (s) { try { s.release(); } catch (e) { /* già tolto */ } }
      this._imposta("spento", "");
      return;
    }
    this.voluto = true;
    this._chiedi();
  }

  // Ritorno in primo piano, pagina ripresa, un tocco qualsiasi: se serve, si richiede
  riprova() {
    if (this.voluto && !this.sentinella && !this.inCorso) this._chiedi();
  }

  _chiedi() {
    if (this.sentinella || this.inCorso) return;
    if (!this.info.api) { this._imposta("manca", this.info.motivo); return; }
    if (this.doc.visibilityState && this.doc.visibilityState !== "visible") return;   // al ritorno
    if (this.stato !== "acceso") this._imposta("chiedo", "");
    let p;
    this.richieste++;
    try {
      p = this.nav.wakeLock.request("screen");     // sincrona: il gesto è ancora valido
    } catch (e) {
      p = Promise.reject(e);
    }
    const prom = Promise.resolve(p).then((s) => {
      if (this.inCorso === prom) this.inCorso = null;
      if (!this.voluto) { try { s.release(); } catch (e) { /* niente */ } return; }
      this.sentinella = s;
      this.daQuando = typeof performance !== "undefined" ? performance.now() : Date.now();
      s.addEventListener("release", () => this._tolto(s));
      this._imposta("acceso", this.info.inaffidabile ? this.info.motivo : "");
    }, (e) => {
      if (this.inCorso === prom) this.inCorso = null;
      if (!this.voluto) return;
      const nome = (e && e.name) || String(e);
      this._imposta("negato", nome === "NotAllowedError"
        ? "il browser non mi lascia tenere acceso lo schermo (risparmio energetico, o serve un tocco): tocca lo schermo per riprovare"
        : "il browser non tiene acceso lo schermo (" + nome + ")");
    });
    this.inCorso = prom;
  }

  // Il browser o il sistema hanno tolto il blocco: pagina nascosta (normale, si riprende al
  // ritorno) oppure a pagina visibile (batteria, risparmio energetico): si riprova una volta
  _tolto(s) {
    if (this.sentinella !== s) return;
    this.sentinella = null;
    if (!this.voluto) return;
    this.cadute++;
    if (this.doc.visibilityState && this.doc.visibilityState !== "visible") {
      this._imposta("caduto", "");
      return;
    }
    this._imposta("caduto", "lo schermo non è più tenuto acceso: tocca lo schermo per riprovare");
    this._chiedi();
  }

  // Lo schermo è davvero tenuto acceso (per quanto si può sapere)
  tenuto() { return this.stato === "acceso" && !this.info.inaffidabile; }
}
