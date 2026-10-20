// Il motore della macchina a stati dei giochi (13/10/2026; progetto
// docs/ricerche/2026-10-12-giochi-macchina-stati.md, area docs/aree/giochi.md). Gira nel riquadro
// del gioco prima degli script dell'agente (calliope/estensioni/scheda.py, documento) e, lo
// stesso file, nella prova di fumo e nei test (calliope/agenti/fumo_js.mjs): un codice solo.
//
// Il gioco dichiara le fasi nel manifesto (scheda.macchina, validata da macchina.py) e scrive in
// logica.js solo la logica pura:
//   const GIOCO = {
//     nuovaPartita({ giocatori }) { return { porte: 3 + giocatori, aperte: [] }; },
//     attivi: { turno: (dati, ctx) => ({ porta: [1, 3] }) },          // restringe, mai allarga
//     mosse: { turno: { porta(dati, { valore, chi }) {
//       return { dati: { ...dati, aperte: [...] }, punti: 1, esito: "Una zucca!", dopo: "turno" };
//     } } },
//     vista: { turno: (dati, ctx) => ({ titolo: "Quale porta apri?" }) },
//   };
// Il motore tiene lo stato (un solo scrittore), le fasi standard (preparazione, esito, fine), i
// turni e i punti, controlla la forma di ciò che la logica restituisce (una mossa che restituisce
// campi sconosciuti è un errore detto con fase e comando: il caso del 12/10 dell'esito annidato
// non passa), disegna la pagina, fa di ogni comando un pulsante e dice a Calliope quali comandi a
// voce valgono adesso.
//
// Dal 14/10 (passo 4 del progetto, il palco fisso): ogni pagina si disegna su un PALCO di misura
// fissa, 1280×720 in orizzontale e 720×1280 in verticale (telefono), scalato e centrato nella
// finestra, mai scroll. I modelli di pagina sono sei più la tela: titolo, scelte, griglia,
// messaggio, punteggi, classifica (e tela, la via libera). L'impaginazione è una funzione PURA
// (impagina: contenuto della pagina → scatole con posizione, misura e corpo del testo), uguale nel
// riquadro e in Node: così la prova di fumo misura, per ogni pagina che la macchina raggiunge e in
// entrambi gli orientamenti, ciò che esce dal palco, ciò che si sovrappone e il testo che non ci
// sta neanche al corpo minimo (controllaPalco). Nel browser il motore misura anche il disegno vero
// (getBoundingClientRect, scrollHeight) e lo manda a Calliope come diagnosi («palco»).
(function (G) {
  "use strict";
  var CHIAVI_MOSSA = ["dati", "punti", "esito", "fase", "dopo", "ancora"];
  var CHIAVI_VISTA = ["titolo", "sottotitolo", "testo", "caselle"];
  var CHIAVI_CASELLA = ["testo", "colore", "risorsa", "comando", "valore"];
  var ETICHETTE = { inizia: "Inizia", avanti: "Avanti", ancora: "Ancora", fine_partita: "Fine partita",
                    anchio: "Gioco anch'io" };
  // Il nome di chi gioca (14/10, passo 4 del progetto: «gioco anch'io» e i nomi scritti): la forma
  // chiusa che Calliope può dire (lettere, spazi e apostrofo; al più 20 caratteri e due parole)
  var NOME_CHIUSO = /^[A-Za-zÀ-ÖØ-öø-ÿ']+( [A-Za-zÀ-ÖØ-öø-ÿ']+)?$/;
  function nomeChiuso(t) {
    t = String(t === undefined || t === null ? "" : t).replace(/\s+/g, " ").trim();
    return t && t.length <= 20 && NOME_CHIUSO.test(t) ? t : null;
  }
  var MODELLI = ["titolo", "scelte", "griglia", "messaggio", "punteggi", "classifica", "tela"];
  // I colori di una casella: un nome di questo elenco o #rgb / #rrggbb
  var COLORI = { rosso: "#d93a3a", verde: "#2f9e44", blu: "#3557c9", giallo: "#f2c94c",
                 arancio: "#f39a2e", viola: "#8e44ad", azzurro: "#4aa3df", rosa: "#e87fb0",
                 marrone: "#8b5a2b", grigio: "#9e9e9e", nero: "#222222", bianco: "#ffffff" };
  var COLORE_HEX = /^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/;
  var RISORSA = /^[a-z0-9_\-]{1,30}(\/[a-z0-9_\-]{1,30})?\.svg$/;
  var MAX_LATO = 12;            // una griglia al più 12×12

  // Il canale riservato al motore (scheda.RUNTIME_JS): i comandi a voce attivi, le mosse a voce,
  // la diagnosi del palco. Il runtime lo mette prima del motore, il motore lo prende e lo toglie:
  // il codice del gioco, che viene dopo, non lo vede (non è un confine: tutto ciò che esce dal
  // riquadro lo ricontrollano la pagina e il server)
  var CANALE = null;
  try { CANALE = G.__calliopeMotore || null; delete G.__calliopeMotore; } catch (e) { /* niente */ }

  function errore(testo) { var e = new Error(testo); e.name = "ErroreGioco"; return e; }
  function copia(x, dove) {
    if (x === undefined) return undefined;
    try { return JSON.parse(JSON.stringify(x)); }
    catch (e) { throw errore(dove + ": i dati devono essere semplici (numeri, testi, elenchi, oggetti), " + e.message); }
  }
  function tipo(x) {
    return x === null ? "null" : Array.isArray(x) ? "un elenco" : typeof x === "object" ? "un oggetto"
      : typeof x === "string" ? "un testo" : typeof x === "number" ? "un numero" : String(typeof x);
  }
  function corto(t, n) { t = String(t).replace(/\s+/g, " ").trim(); n = n || 30; return t.length > n ? t.slice(0, n - 1) + "…" : t; }

  // ═══════════════════════════ il palco: impaginazione pura ═══════════════════════════
  var PALCHI = { orizzontale: { W: 1280, H: 720 }, verticale: { W: 720, H: 1280 } };
  var BORDO = 32, SPAZIO = 16, RIGA = 1.2;
  // [corpo massimo, corpo minimo, altezza massima] dei testi, per orientamento
  var TESTI = {
    orizzontale: { titolo: [60, 30, 150], sottotitolo: [34, 22, 82], testo: [38, 22, 138],
                   grande: [84, 36, 330], extra: [36, 24, 90], titolone: [96, 44, 270] },
    verticale: { titolo: [60, 30, 230], sottotitolo: [36, 22, 130], testo: [40, 22, 300],
                 grande: [84, 36, 560], extra: [38, 24, 140], titolone: [96, 44, 430] },
  };
  // La fascia dei pulsanti in fondo alle pagine con pochi comandi (titolo, messaggio, punteggi,
  // classifica, tela, i comandi fuori dalle caselle di una griglia)
  var FONDO = { orizzontale: 104, verticale: 196 };
  // Un pulsante: almeno 150×80 sul palco (sul telefono in verticale, scala ~0,54, ~44 px veri)
  var PULSANTE = { hMin: 80, hMax: 128, wMin: 150, wMax: 460, fMax: 40, fMin: 22, dentro: 18 };
  var FASCIA = { riga: 52, fMax: 28, fMin: 20, spazio: 10, dentro: 18, righe: 3 };
  // Una casella della griglia: almeno 32 px sul palco (una scacchiera 12×12 ci sta con il solo
  // titolo; con più testo la misura dice di accorciarlo o di usare meno caselle)
  var CASELLA = { min: 32, spazio: 8 };

  // La larghezza stimata di un testo (system-ui; un po' più larga del vero, così ciò che «sta»
  // qui sta anche sullo schermo: la misura vera del browser fa il resto)
  var STRETTE = " .,;:!'|il1Ijtf()[]«»\"-";
  function peso(c) {
    if (STRETTE.indexOf(c) >= 0) return 0.34;
    if (c === "r") return 0.42;
    if ("mwMW@".indexOf(c) >= 0) return 0.92;
    if (c >= "0" && c <= "9") return 0.6;
    if (c >= "A" && c <= "Z") return 0.7;
    return c.charCodeAt(0) < 0x250 ? 0.58 : 1.05;
  }
  function larghezza(t, f) {
    var w = 0, cs = Array.from(String(t));
    for (var i = 0; i < cs.length; i++) w += peso(cs[i]);
    return w * f;
  }
  // Le righe di un testo a corpo f in una larghezza w (a capo tra le parole; una parola più
  // larga della riga va a capo dentro, come overflow-wrap: anywhere). k: 1,08 per il grassetto
  function righe(t, f, w, k) {
    var n = 0;
    String(t).split("\n").forEach(function (par) {
      var parole = par.split(/\s+/).filter(Boolean);
      if (!parole.length) { n++; return; }
      var r = 1, usata = 0, sp = larghezza(" ", f) * k;
      parole.forEach(function (p) {
        var lp = larghezza(p, f) * k;
        if (lp > w) {
          if (usata > 0) { r++; usata = 0; }
          var pezzi = Math.ceil(lp / w);
          r += pezzi - 1;
          usata = lp - (pezzi - 1) * w;
          return;
        }
        if (usata === 0) usata = lp;
        else if (usata + sp + lp <= w) usata += sp + lp;
        else { r++; usata = lp; }
      });
      n += r;
    });
    return n;
  }
  // Il corpo più grande (a passi di 2 px, da fMax a fMin) a cui il testo sta in w × hMax
  function adatta(t, w, hMax, fMax, fMin, k, righeMax) {
    k = k || 1;
    fMax = Math.max(fMin, Math.floor(fMax));
    for (var f = fMax; ; f = Math.max(fMin, f - 2)) {
      var n = righe(t, f, w, k);
      if (n * f * RIGA <= hMax + 0.5 && (!righeMax || n <= righeMax)) return { f: f, n: n, h: Math.ceil(n * f * RIGA), ok: true };
      if (f === fMin) break;
    }
    var n2 = righe(t, fMin, w, k);
    var max = Math.max(1, Math.floor(hMax / (fMin * RIGA)));
    if (righeMax) max = Math.min(max, righeMax);
    return { f: fMin, n: n2, h: Math.ceil(n2 * fMin * RIGA), ok: false, max: max,
             caratteri: Math.max(1, Math.floor(max * w / (fMin * 0.6 * k))) };
  }
  function tondo(b) { b.x = Math.round(b.x); b.y = Math.round(b.y); b.w = Math.round(b.w); b.h = Math.round(b.h); return b; }
  function metti(out, b) { out.scatole.push(tondo(b)); return b; }

  function scatolaTesto(out, tipoS, testo, x, y, w, mis, k, fonte) {
    var a = adatta(testo, w, mis[2], mis[0], mis[1], k);
    var b = { tipo: tipoS, testo: testo, x: x, y: y, w: w, h: a.ok ? a.h : mis[2], f: a.f, scritta: true };
    if (fonte) b.fonte = fonte;
    if (!a.ok) b.tagliato = { righe: a.n, max: a.max, fMin: mis[1], caratteri: a.caratteri };
    return metti(out, b);
  }

  // I pulsanti in una zona: la disposizione (colonne × righe) con il corpo più grande che fa
  // stare ogni etichetta; se non ce n'è una con pulsanti di almeno 150×80, la più fitta, che esce
  // dalla zona (e la misura lo dice: «troppi»)
  function corpoPulsanti(lista, w, h, fMax) {
    for (var f = Math.max(PULSANTE.fMin, Math.floor(fMax)); ; f = Math.max(PULSANTE.fMin, f - 2)) {
      var ok = true;
      for (var i = 0; i < lista.length && ok; i++) {
        var n = righe(lista[i].etichetta, f, w, 1);
        if (n > 2 || n * f * RIGA > h) ok = false;
      }
      if (ok) return f;
      if (f === PULSANTE.fMin) return null;
    }
  }
  function pulsanti(out, lista, x, y, w, h) {
    var n = lista.length, P = PULSANTE, meglio = null;
    if (!n) return;
    for (var col = 1; col <= n; col++) {
      var rr = Math.ceil(n / col);
      var bw = Math.min(P.wMax, (w - (col - 1) * SPAZIO) / col);
      var bh = Math.min(P.hMax, (h - (rr - 1) * SPAZIO) / rr);
      if (bw < P.wMin) break;
      if (bh < P.hMin) continue;
      var f = corpoPulsanti(lista, bw - 2 * P.dentro, bh - 12, Math.min(P.fMax, bh * 0.45));
      if (f === null) continue;
      // il corpo più grande; a parità, meno righe (una fila di porte), poi i pulsanti più grandi
      var voto = f * 1e6 - rr * 1e3 + bw * bh / 1e3;
      if (!meglio || voto > meglio.voto) meglio = { col: col, rr: rr, bw: bw, bh: bh, f: f, voto: voto };
    }
    if (!meglio) {
      var cmax = Math.max(1, Math.floor((w + SPAZIO) / (P.wMin + SPAZIO)));
      var rmax = Math.max(0, Math.floor((h + SPAZIO) / (P.hMin + SPAZIO)));
      var c2 = Math.min(cmax, n);
      meglio = { col: c2, rr: Math.ceil(n / c2), bw: Math.min(P.wMax, (w - (c2 - 1) * SPAZIO) / c2), bh: P.hMin, f: P.fMin };
      if (cmax * rmax < n) out.note.push({ tipo: "troppi", n: n, max: cmax * rmax });
    }
    var gh = meglio.rr * meglio.bh + (meglio.rr - 1) * SPAZIO;
    var y0 = gh <= h ? y + (h - gh) / 2 : y;
    for (var i = 0; i < n; i++) {
      var r = Math.floor(i / meglio.col), c = i % meglio.col;
      var inRiga = Math.min(meglio.col, n - r * meglio.col);
      var rw = inRiga * meglio.bw + (inRiga - 1) * SPAZIO;
      var p = lista[i];
      var a = adatta(p.etichetta, meglio.bw - 2 * P.dentro, meglio.bh - 12, meglio.f, P.fMin, 1, 2);
      var b = { tipo: "pulsante", testo: p.etichetta, comando: p.c, valore: p.v, scritta: true,
                x: x + (w - rw) / 2 + c * (meglio.bw + SPAZIO), y: y0 + r * (meglio.bh + SPAZIO),
                w: meglio.bw, h: meglio.bh, f: a.f, fonte: p.fonte };
      if (!a.ok) b.tagliato = { righe: a.n, max: a.max, fMin: P.fMin, caratteri: a.caratteri };
      metti(out, b);
    }
  }

  // La fascia dei punti in fondo: «Nome: punti», chi tocca sottolineato. Restituisce il suo bordo alto
  function fascia(out, pag, x, w, basso) {
    var voci = pag.giocatori.map(function (g, i) { return { testo: g.nome + ": " + g.punti, tocca: i === pag.tocca && pag.mostraTocca, i: i }; });
    var f, file;
    for (f = FASCIA.fMax; ; f -= 2) {
      file = [[]];
      var usata = 0;
      voci.forEach(function (v) {
        v.w = Math.min(w, larghezza(v.testo, f) * 1.08 + 2 * FASCIA.dentro);
        if (usata > 0 && usata + FASCIA.spazio + v.w > w) { file.push([]); usata = 0; }
        usata += (usata > 0 ? FASCIA.spazio : 0) + v.w;
        file[file.length - 1].push(v);
      });
      if (file.length <= FASCIA.righe || f <= FASCIA.fMin) break;
    }
    var h = file.length * FASCIA.riga + (file.length - 1) * 6;
    var top = basso - h;
    metti(out, { tipo: "fascia", sfondo: true, x: x, y: top, w: w, h: h });
    file.forEach(function (fila, r) {
      var tot = fila.reduce(function (s, v) { return s + v.w; }, 0) + (fila.length - 1) * FASCIA.spazio;
      var xx = x + (w - tot) / 2;
      fila.forEach(function (v) {
        metti(out, { tipo: "giocatore", testo: v.testo, tocca: v.tocca, scritta: true, x: xx, y: top + r * (FASCIA.riga + 6),
                     w: v.w, h: FASCIA.riga, f: f, indice: v.i });
        xx += v.w + FASCIA.spazio;
      });
    });
    return top;
  }

  function griglia(out, pag, x, y, w, h) {
    var cs = pag.caselle, R = cs.length, C = cs[0].length, g = CASELLA.spazio;
    var lato = Math.floor(Math.min((w - (C - 1) * g) / C, (h - (R - 1) * g) / R));
    if (lato < CASELLA.min) {
      out.note.push({ tipo: "caselle", R: R, C: C, lato: lato,
                      maxR: Math.max(1, Math.floor((h + g) / (CASELLA.min + g))),
                      maxC: Math.max(1, Math.floor((w + g) / (CASELLA.min + g))) });
      lato = CASELLA.min;
    }
    var gw = C * lato + (C - 1) * g, gh = R * lato + (R - 1) * g;
    var x0 = x + (w - gw) / 2, y0 = gh <= h ? y + (h - gh) / 2 : y;
    cs.forEach(function (riga, r) {
      riga.forEach(function (k, c) {
        var b = { tipo: "casella", r: r, c: c, x: x0 + c * (lato + g), y: y0 + r * (lato + g), w: lato, h: lato };
        if (k.testo) {
          var a = adatta(k.testo, lato - 10, lato - 10, Math.min(96, lato * 0.6), 14, 1);
          b.testo = k.testo; b.f = a.f; b.scritta = true;
          b.fonte = "GIOCO.vista." + pag.fase + ".caselle";
          if (!a.ok) b.tagliato = { righe: a.n, max: a.max, fMin: 14, caratteri: a.caratteri };
        }
        if (k.colore) b.colore = k.colore;
        if (k.risorsa) b.risorsa = k.risorsa;
        if (k.pulsante) { b.comando = k.comando; b.valore = k.valore; b.etichetta = k.etichetta; }
        metti(out, b);
      });
    });
  }

  // Le righe dei giocatori (punteggi) o della classifica, in una zona
  function righeGiocatori(out, voci, x, y, w, h, tipoS) {
    var n = voci.length;
    if (!n) return;
    var g = 8, primo = tipoS === "classifica" ? 1.3 : 1;
    var unita = (h - (n - 1) * g) / (n - 1 + primo);
    var rh = Math.min(84, unita);
    if (rh < 48) { out.note.push({ tipo: "righe", n: n }); rh = 48; }
    var tot = rh * (n - 1 + primo) + (n - 1) * g;
    var yy = tot <= h ? y + (h - tot) / 2 : y;
    var larga = Math.min(w, 900);
    voci.forEach(function (v, i) {
      var hh = i === 0 ? rh * primo : rh;
      var a = adatta(v.testo, larga - 32, hh - 8, Math.min(i === 0 && primo > 1 ? 52 : 40, hh * 0.55), 20, 1.08, 1);
      var b = { tipo: "riga", testo: v.testo, tocca: !!v.tocca, primo: i === 0 && primo > 1, scritta: true,
                x: x + (w - larga) / 2, y: yy, w: larga, h: hh, f: a.f };
      if (!a.ok) b.tagliato = { righe: a.n, max: a.max, fMin: 20, caratteri: a.caratteri };
      metti(out, b);
      yy += hh + g;
    });
  }

  // Il contenuto di una pagina (dal nucleo: pagina(S)) → le scatole sul palco, in ordine di
  // lettura (dall'alto, da sinistra: così le legge chi usa un lettore di schermo, e il testo
  // visibile dei test esce nell'ordine in cui si vede)
  function impagina(pag, orientamento) {
    var out = componi(pag, orientamento);
    out.scatole = out.scatole.map(function (b, i) { return [b, i]; })
      .sort(function (a, b) { return a[0].y - b[0].y || a[0].x - b[0].x || a[1] - b[1]; })
      .map(function (x) { return x[0]; });
    return out;
  }
  function componi(pag, orientamento) {
    var O = orientamento === "verticale" ? "verticale" : "orizzontale";
    var W = PALCHI[O].W, H = PALCHI[O].H, D = TESTI[O], F = FONDO[O];
    var out = { orientamento: O, W: W, H: H, modello: pag.modello, fase: pag.fase, scatole: [], note: [] };
    var x = BORDO, w = W - 2 * BORDO, y = BORDO, basso = H - BORDO;
    var mod = pag.modello;
    if (pag.fascia && pag.giocatori && pag.giocatori.length) basso = fascia(out, pag, x, w, basso) - SPAZIO;
    var fonti = pag.fonti || {};
    // i pulsanti in fondo (le pagine con pochi comandi)
    var inFondo = mod !== "scelte" && pag.pulsanti.length > 0;
    if (inFondo) {
      pulsanti(out, pag.pulsanti, x, basso - F, w, F);
      basso -= F + SPAZIO;
    }
    if (mod === "titolo") {
      // il titolo grande al centro, sotto il sottotitolo e il testo
      var pezzi = [];
      if (pag.titolo) pezzi.push(["titolo", pag.titolo, D.titolone, 1.08]);
      if (pag.sottotitolo) pezzi.push(["sottotitolo", pag.sottotitolo, D.sottotitolo, 1]);
      if (pag.testo) pezzi.push(["testo", pag.testo, D.testo, 1]);
      var alto = pezzi.reduce(function (s, p) {
        var a = adatta(p[1], w, p[2][2], p[2][0], p[2][1], p[3]);
        return s + (a.ok ? a.h : p[2][2]) + SPAZIO;
      }, -SPAZIO);
      var yy = Math.max(y, y + (basso - y - alto) / 2);
      pezzi.forEach(function (p) {
        var b = scatolaTesto(out, p[0], p[1], x, yy, w, p[2], p[3], fonti[p[0]]);
        yy = b.y + b.h + SPAZIO;
      });
      return out;
    }
    // la testata: titolo, sottotitolo, testo
    [["titolo", D.titolo, 1.08], ["sottotitolo", D.sottotitolo, 1], ["testo", D.testo, 1]].forEach(function (t) {
      if (!pag[t[0]]) return;
      var b = scatolaTesto(out, t[0], pag[t[0]], x, y, w, t[1], t[2], fonti[t[0]]);
      y = b.y + b.h + SPAZIO;
    });
    var h = basso - y;
    if (mod === "scelte") pulsanti(out, pag.pulsanti, x, y, w, h);
    else if (mod === "griglia") griglia(out, pag, x, y, w, h);
    else if (mod === "messaggio") {
      var parti = [];
      if (pag.grande) parti.push(["grande", pag.grande, D.grande, 1.08]);
      if (pag.extra) parti.push(["extra", pag.extra, D.extra, 1]);
      var tot = parti.reduce(function (s, p) {
        var a = adatta(p[1], w, p[2][2], p[2][0], p[2][1], p[3]);
        return s + (a.ok ? a.h : p[2][2]) + SPAZIO;
      }, -SPAZIO);
      var y2 = Math.max(y, y + (h - tot) / 2);
      parti.forEach(function (p) {
        var b = scatolaTesto(out, p[0], p[1], x, y2, w, p[2], p[3], fonti[p[0]]);
        y2 = b.y + b.h + SPAZIO;
      });
    } else if (mod === "punteggi") {
      righeGiocatori(out, pag.giocatori.map(function (g, i) {
        return { testo: g.nome + ": " + g.punti + (g.punti === 1 ? " punto" : " punti"), tocca: i === pag.tocca && pag.mostraTocca };
      }), x, y, w, h, "punteggi");
    } else if (mod === "classifica") {
      righeGiocatori(out, (pag.classifica || []).map(function (g, i) {
        return { testo: (i + 1) + ". " + g.nome + ": " + g.punti + (g.punti === 1 ? " punto" : " punti") };
      }), x, y, w, h, "classifica");
    } else if (mod === "tela") {
      metti(out, { tipo: "tela", x: x, y: y, w: w, h: Math.max(0, h) });
      if (h < 200) out.note.push({ tipo: "tela_piccola", h: Math.round(h) });
    }
    return out;
  }

  // ── la misura: ciò che esce dal palco, ciò che si sovrappone, il testo che non ci sta ──
  function nomeScatola(b) {
    var nomi = { titolo: "il titolo", sottotitolo: "il sottotitolo", testo: "il testo", grande: "il messaggio",
                 extra: "la riga dei punti", pulsante: "il pulsante", casella: "la casella", giocatore: "il nome nella fascia",
                 riga: "la riga", tela: "la tela", fascia: "la fascia dei punti" };
    var t = b.testo ? " «" + corto(b.testo) + "»" : (b.etichetta ? " «" + corto(b.etichetta) + "»" : "");
    return (nomi[b.tipo] || b.tipo) + t + (b.tipo === "casella" ? " (riga " + (b.r + 1) + ", colonna " + (b.c + 1) + ")" : "");
  }
  function controllaPalco(imp) {
    var d = [];
    imp.note.forEach(function (n) { d.push(n); });
    imp.scatole.forEach(function (b) {
      var lati = {};
      if (b.x < -0.5) lati["a sinistra"] = Math.round(-b.x);
      if (b.y < -0.5) lati["in alto"] = Math.round(-b.y);
      if (b.x + b.w > imp.W + 0.5) lati["a destra"] = Math.round(b.x + b.w - imp.W);
      if (b.y + b.h > imp.H + 0.5) lati["in basso"] = Math.round(b.y + b.h - imp.H);
      if (Object.keys(lati).length) d.push({ tipo: "fuori", b: b, lati: lati });
      if (b.tagliato) d.push({ tipo: "tagliato", b: b });
    });
    // sovrapposti (le scatole di sfondo, come la fascia, contengono altre scatole: non contano)
    var l = imp.scatole.filter(function (b) { return !b.sfondo && b.w > 0 && b.h > 0; })
      .slice().sort(function (a, b) { return a.y - b.y; });
    for (var i = 0; i < l.length; i++) {
      for (var j = i + 1; j < l.length && l[j].y < l[i].y + l[i].h - 1; j++) {
        var a = l[i], b = l[j];
        var dx = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
        var dy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
        if (dx > 1 && dy > 1) d.push({ tipo: "sovrapposti", a: a, b: b });
      }
    }
    return d;
  }
  // I difetti in parole, per l'agente: cosa, dove e cosa fare. Prima le cause (troppi pulsanti,
  // griglia troppo grande, testo che non ci sta), poi gli effetti raggruppati per tipo di
  // scatola («il pulsante «Porta 29» e altri 11 escono dal palco in basso, fino a 48 px»)
  function difettiInParole(imp, d) {
    var out = [];
    var dove = "nella pagina «" + imp.modello + "» (" + imp.orientamento + " " + imp.W + "×" + imp.H + ")";
    function aggiungi(t) { if (t && out.indexOf(t) < 0) out.push(t); }
    d.forEach(function (x) {
      // nella griglia (20/10, #192: tris2 L3 del banco) la pagina c'è già: i pulsanti in fondo
      // sono i comandi che nessuna casella mostra
      if (x.tipo === "troppi") aggiungi(x.n + " pulsanti non ci stanno " + dove + ": al più " + x.max + " di almeno " + PULSANTE.wMin + "×" + PULSANTE.hMin + " px. Restringi i comandi attivi (GIOCO.attivi), accorcia le etichette o "
        + (imp.modello === "griglia" ? "metti comando e valore nelle caselle (in vista, { testo, comando, valore }): la casella diventa il pulsante della mossa, e in fondo restano solo gli altri comandi" : "usa la pagina «griglia»"));
      else if (x.tipo === "caselle") aggiungi("la griglia " + x.R + "×" + x.C + " non ci sta " + dove + ": le caselle verrebbero di " + x.lato + " px (al più " + x.maxR + " righe e " + x.maxC + " colonne da " + CASELLA.min + " px). Usa meno righe o colonne");
      else if (x.tipo === "righe") aggiungi(x.n + " righe non ci stanno " + dove);
      else if (x.tipo === "tela_piccola") aggiungi("la tela resta alta solo " + x.h + " px " + dove + ": accorcia titolo e testo della fase");
    });
    d.forEach(function (x) {
      if (x.tipo !== "tagliato") return;
      aggiungi(nomeScatola(x.b) + " non ci sta " + dove + " neanche a " + x.b.tagliato.fMin + " px ("
        + x.b.tagliato.righe + " righe dove ne stanno " + x.b.tagliato.max + "): accorcialo, al più circa " + x.b.tagliato.caratteri + " caratteri"
        + (x.b.fonte ? " (" + x.b.fonte + ")" : ""));
    });
    var gruppi = {}, ordine = [];
    d.forEach(function (x) {
      var k = x.tipo === "fuori" ? "fuori:" + x.b.tipo : x.tipo === "sovrapposti" ? "sopra:" + x.a.tipo + ":" + x.b.tipo : null;
      if (!k) return;
      if (!gruppi[k]) { gruppi[k] = { primo: x, n: 0, lati: {} }; ordine.push(k); }
      gruppi[k].n++;
      if (x.lati) Object.keys(x.lati).forEach(function (l) { gruppi[k].lati[l] = Math.max(gruppi[k].lati[l] || 0, x.lati[l]); });
    });
    ordine.forEach(function (k) {
      var g = gruppi[k], x = g.primo, altri = g.n > 1 ? (g.n === 2 ? " e un altro" : " e altri " + (g.n - 1)) : "";
      if (x.tipo === "fuori") {
        aggiungi(nomeScatola(x.b) + altri + (g.n > 1 ? " escono" : " esce") + " dal palco " + Object.keys(g.lati).map(function (l) {
          return l + (g.n > 1 ? " fino a " : " di ") + g.lati[l] + " px";
        }).join(" e ") + " " + dove);
      } else {
        aggiungi(nomeScatola(x.a) + " si sovrappone " + nomeScatola(x.b).replace(/^il /, "al ").replace(/^la /, "alla ")
          + (g.n > 1 ? " (e altre " + (g.n - 1) + " scatole così)" : "") + " " + dove);
      }
    });
    // Una causa sola fa uscire molte scatole: si dicono le prime
    return out.slice(0, 3);
  }
  function difettiPalco(pag, orientamento) {
    var imp = impagina(pag, orientamento);
    return difettiInParole(imp, controllaPalco(imp));
  }

  // ═══════════════════════════ la macchina ═══════════════════════════
  // La macchina come la scrive il manifesto (o come la dà macchina.py, uguale ma pulita)
  function normalizza(M, giocatori) {
    M = M || {};
    var g = giocatori || {};
    var out = { inizio: M.inizio, fasi: {}, esito_s: M.esito_s === undefined ? 4 : Number(M.esito_s),
                gmin: Math.max(1, Number(g.min || 1)), gmax: Math.max(1, Number(g.max || g.min || 1)) };
    var fasi = M.fasi || {};
    Object.keys(fasi).forEach(function (nome) {
      var f = fasi[nome] || {};
      var comandi = {};
      Object.keys(f.comandi || {}).forEach(function (c) {
        var d = f.comandi[c] || {};
        if (Array.isArray(d)) d = { forme: d };
        var n = d.n || null, valori = null, sinonimi = null;
        if (n && n.valori) {
          sinonimi = Array.isArray(n.valori) ? n.valori.reduce(function (o, v) { o[v] = [String(v)]; return o; }, {}) : n.valori;
          valori = Object.keys(sinonimi);
        } else if (n) {
          valori = [];
          for (var i = Number(n.da); i <= Number(n.a); i++) valori.push(i);
        }
        comandi[c] = { forme: (d.forme || []).slice(), etichetta: d.etichetta || "", valori: valori, sinonimi: sinonimi };
      });
      var pagina = MODELLI.indexOf(f.pagina) >= 0 ? f.pagina : "scelte";
      // Una tela può dichiarare un orientamento solo (15/10, «Gira il telefono»): il palco è
      // sempre quello, e sul telefono girato dall'altra parte lo schermo lo dice
      var orient = pagina === "tela" && PALCHI[f.orientamento] ? f.orientamento : null;
      out.fasi[nome] = { pagina: pagina, turni: f.turni !== false, verso: (f.verso || []).slice(), comandi: comandi,
                         orientamento: orient };
    });
    if (!out.inizio) out.inizio = Object.keys(out.fasi)[0];
    return out;
  }

  function piatto(nome, v) { return v === null || v === undefined ? nome : nome + "_" + v; }

  // ── il nucleo: funzioni pure sullo stato (S), senza DOM. Lo usano il riquadro e la prova di
  // fumo per fasi (l'esploratore di fumo_js.mjs) ──
  function crea(GIOCO, Mgrezza, giocatori, opzioni) {
    if (!GIOCO || typeof GIOCO !== "object" || typeof GIOCO.nuovaPartita !== "function") {
      throw errore("logica.js deve dichiarare const GIOCO = { nuovaPartita(…), mosse: { fase: { comando(…) } }, … } (la macchina a stati di Calliope)");
    }
    var M = normalizza(Mgrezza, giocatori);
    var titoloGioco = String((opzioni && opzioni.titolo) || "");
    if (!M.fasi[M.inizio]) throw errore("la macchina non ha la fase d'inizio «" + M.inizio + "»");

    function nuovo() {
      // iscritti: chi ha detto «gioco anch'io» nella preparazione, con il nome dalla voce (o
      // null), lo schermo da cui l'ha detto o toccato e la sua voce (15/10, chi è quale
      // giocatore); entrano: chi l'ha detto a partita cominciata e gioca dalla prossima
      return { n: 0, fase: "preparazione", numero: M.gmin, giocatori: [], tocca: 0, turno: 0,
               dati: null, esito: null, dopo: null, passa: false, iscritti: [], entrano: [] };
    }
    // ── chi è quale giocatore (15/10) ──
    // Un giocatore può essere legato a uno SCHERMO (il numero del posto della partita: lo dà
    // Calliope all'avvio del riquadro, e lo aggiunge il server alle mosse che arrivano da un altro
    // schermo) e a una VOCE (un segno opaco, «v1», che Calliope dà a ogni persona riconosciuta
    // dalla voce nella partita: il riquadro non sa chi è). Il legame nasce con «gioco anch'io»
    // (detto o toccato). Una mossa del gioco in una fase a turni vale solo per chi è di turno:
    // dalla sua voce, o dal suo schermo; una voce di un altro giocatore o un altro schermo no.
    // Senza legami (nessun «gioco anch'io») chiunque muove quando tocca a qualcuno, come prima
    var COMANDI_CALLIOPE = { inizia: 1, avanti: 1, ancora: 1, fine_partita: 1, anchio: 1, giocatori: 1 };
    function legame(x) {
      var o = {};
      var s = x && x.schermo, v = x && x.voce;
      if (typeof s === "number" && s >= 1 && s <= 99 && Math.floor(s) === s) o.schermo = s;
      if (typeof v === "string" && /^v[1-9][0-9]?$/.test(v)) o.voce = v;
      return o;
    }
    function nomeDi(S, i) { var g = S.giocatori[i]; return g ? String(g.nome) : ""; }
    function aChi(nome) { return (/^[aA]/.test(nome) ? "ad " : "a ") + nome; }
    // {ok, motivo, da, testo}: se il comando `c` mandato da `extra` ({schermo, voce}) vale per
    // chi lo manda, e quale giocatore muove (da: la posizione, o null se non si sa)
    function chiMuove(S, c, extra) {
      var e = legame(extra);
      var gs = S.giocatori || [];
      var perVoce = -1, perSchermo = [];
      gs.forEach(function (g, i) {
        if (e.voce && g.voce === e.voce) perVoce = i;
        if (e.schermo && g.schermo === e.schermo) perSchermo.push(i);
      });
      if (c === "anchio") {
        var giaPrep = e.voce && (S.iscritti || []).concat(S.entrano || []).some(function (x) { return x && x.voce === e.voce; });
        if (S.fase !== "preparazione" && (perVoce >= 0 || giaPrep)) {
          return { ok: false, motivo: "gia", da: perVoce, testo: perVoce >= 0 ? "Sei già nella partita: sei " + nomeDi(S, perVoce) + "." : "Sei già nella partita." };
        }
        return { ok: true, da: null };
      }
      var f = M.fasi[S.fase];
      if (COMANDI_CALLIOPE[c] || !f) return { ok: true, da: null };
      var unoSolo = perSchermo.length === 1 ? perSchermo[0] : null;
      if (!f.turni || gs.length <= 1) return { ok: true, da: perVoce >= 0 ? perVoce : unoSolo };
      var t = S.tocca, g = gs[t] || {};
      if (perVoce >= 0 && perVoce !== t) {
        return { ok: false, motivo: "turno", da: perVoce, testo: "Tocca " + aChi(nomeDi(S, t)) + "." };
      }
      if (perVoce === t) return { ok: true, da: t };
      if (g.schermo && e.schermo && g.schermo !== e.schermo) {
        return { ok: false, motivo: "schermo", da: unoSolo, testo: "Tocca " + aChi(nomeDi(S, t)) + ", sull'altro schermo." };
      }
      return { ok: true, da: t };
    }
    function nonTua(r) {
      var e = new Error(r.testo || "Adesso non tocca a te.");
      e.name = "MossaNonTua";
      e.motivo = r.motivo;
      return e;
    }
    function contesto(S) {
      var g = S.giocatori.map(function (x) { return { nome: x.nome, punti: x.punti }; });
      return { giocatori: g, numero: g.length, tocca: S.tocca, turno: S.turno,
               chi: g[S.tocca] ? g[S.tocca].nome : null };
    }
    function comando(fase, nome) {
      var f = M.fasi[fase];
      return f && f.comandi[nome] || null;
    }
    // {comando: true | [valori]}: i comandi che valgono adesso
    function attivi(S) {
      var out = {};
      if (S.fase === "preparazione") {
        if (M.gmin < M.gmax) {
          var v = [];
          for (var i = M.gmin; i <= M.gmax; i++) v.push(i);
          out.giocatori = v;
        }
        if ((S.iscritti || []).length < M.gmax) out.anchio = true;
        out.inizia = true;
        return out;
      }
      if (S.fase === "esito") return { avanti: true };
      if (S.fase === "fine") {
        var fin = { ancora: true };
        if (postoLibero(S)) fin.anchio = true;
        return fin;
      }
      var f = M.fasi[S.fase];
      if (!f) throw errore("fase «" + S.fase + "» non dichiarata nella macchina");
      var scelti = null;
      var fn = GIOCO.attivi && GIOCO.attivi[S.fase];
      if (typeof fn === "function") {
        scelti = fn(copia(S.dati, "attivi"), contesto(S));
        if (scelti === null || typeof scelti !== "object" || Array.isArray(scelti)) {
          throw errore("GIOCO.attivi." + S.fase + " restituisce " + tipo(scelti) + ": deve restituire un oggetto { comando: true | false | [valori] }");
        }
      }
      Object.keys(f.comandi).forEach(function (c) {
        var d = f.comandi[c];
        var s = scelti ? scelti[c] : true;
        if (s === undefined || s === false || s === null) return;
        if (s === true) { out[c] = d.valori ? d.valori.slice() : true; return; }
        if (!Array.isArray(s)) throw errore("GIOCO.attivi." + S.fase + "." + c + " vale " + tipo(s) + ": true, false o un elenco di valori");
        if (!d.valori) throw errore("GIOCO.attivi." + S.fase + "." + c + ": il comando non ha valori (manca «n» nel manifesto), usa true o false");
        var fuori = s.filter(function (x) { return d.valori.indexOf(x) < 0; });
        if (fuori.length) throw errore("GIOCO.attivi." + S.fase + "." + c + ": valori fuori da quelli dichiarati nel manifesto: " + JSON.stringify(fuori.slice(0, 5)) + " (ammessi " + JSON.stringify(d.valori.slice(0, 12)) + ")");
        if (s.length) out[c] = s.slice();
      });
      if (scelti) {
        var nuovi = Object.keys(scelti).filter(function (c) { return !f.comandi[c]; });
        if (nuovi.length) throw errore("GIOCO.attivi." + S.fase + ": comandi che la fase non dichiara: " + nuovi.join(", ") + " (dichiarali nel manifesto, scheda.macchina.fasi." + S.fase + ".comandi)");
      }
      if (f.pagina === "tela") out.fine_partita = true;
      // «Gioco anch'io» a partita cominciata (15/10): solo a voce (nessun pulsante: la pagina
      // del gioco non cambia), non in una tela (il tempo reale)
      else if (postoLibero(S)) out.anchio = true;
      return out;
    }
    // C'è posto per chi entra a partita cominciata (contando chi aspetta la prossima)
    function postoLibero(S) {
      return M.gmax > 1 && (S.giocatori || []).length + (S.entrano || []).length < M.gmax;
    }
    function piatti(att) {
      var out = [];
      Object.keys(att).forEach(function (c) {
        if (att[c] === true) out.push(c);
        else att[c].forEach(function (v) { out.push(piatto(c, v)); });
      });
      return out;
    }
    // Il comando a voce piatto («porta_3») → [comando, valore]
    function daPiatto(nome) {
      var s = String(nome);
      if (s === "inizia" || s === "avanti" || s === "ancora" || s === "fine_partita" || s === "anchio") return [s, null];
      var m = s.match(/^giocatori_(\d+)$/);
      if (m) return ["giocatori", Number(m[1])];
      for (var fn in M.fasi) {
        var cs = M.fasi[fn].comandi;
        for (var c in cs) {
          if (!cs[c].valori) { if (c === s) return [c, null]; continue; }
          for (var i = 0; i < cs[c].valori.length; i++) if (piatto(c, cs[c].valori[i]) === s) return [c, cs[c].valori[i]];
        }
      }
      return null;
    }
    function attivo(att, c, v) {
      if (!(c in att)) return false;
      if (att[c] === true) return v === null || v === undefined;
      return att[c].indexOf(v) >= 0;
    }
    function avanzaTurno(S) {
      if (!S.giocatori.length) return;
      S.tocca = (S.tocca + 1) % S.giocatori.length;
      if (S.tocca === 0) S.turno++;
    }
    // La partita nuova con `numero` giocatori; `prima`: i giocatori che c'erano (nome e se è
    // scritto), dalla preparazione («gioco anch'io») o dalla partita di prima («ancora»)
    function avviaPartita(S, numero, prima) {
      var gs = [];
      for (var i = 0; i < numero; i++) {
        var p = (prima || [])[i];
        var g = p && p.nome ? { nome: p.nome, punti: 0, scritto: !!p.scritto } : { nome: "Giocatore " + (i + 1), punti: 0, scritto: false };
        var l = legame(p);
        if (l.schermo) g.schermo = l.schermo;
        if (l.voce) g.voce = l.voce;
        gs.push(g);
      }
      var nomi = gs.map(function (g) { return g.nome; });
      var dati = GIOCO.nuovaPartita({ giocatori: numero, nomi: nomi.slice() });
      if (dati === undefined || dati === null || typeof dati !== "object") {
        throw errore("GIOCO.nuovaPartita restituisce " + tipo(dati) + ": deve restituire i dati della partita (un oggetto)");
      }
      S.numero = numero;
      S.giocatori = gs;
      S.tocca = 0; S.turno = 1; S.dati = copia(dati, "GIOCO.nuovaPartita");
      S.esito = null; S.dopo = null; S.passa = false;
      S.fase = M.inizio;
      S.entrano = [];
    }
    function verso(fase) {
      var f = M.fasi[fase];
      return (f ? f.verso : []).concat(["esito", "fine", fase]);
    }
    // Il risultato di una mossa: { dati, punti?, esito?, fase?, dopo?, ancora? }
    function controlla(ris, dove, S) {
      if (ris === null || typeof ris !== "object" || Array.isArray(ris)) {
        throw errore(dove + " restituisce " + tipo(ris) + ": una mossa restituisce { dati, punti, esito, fase, dopo, ancora }");
      }
      var altri = Object.keys(ris).filter(function (k) { return CHIAVI_MOSSA.indexOf(k) < 0; });
      if (altri.length) {
        throw errore(dove + " restituisce campi che il motore non conosce: " + altri.slice(0, 6).join(", ")
          + ". Una mossa restituisce { dati, punti, esito, fase, dopo, ancora }: lo stato del gioco va tutto dentro «dati», il testo da mostrare in «esito»");
      }
      if (!("dati" in ris) || ris.dati === undefined || ris.dati === null || typeof ris.dati !== "object") {
        throw errore(dove + ": manca «dati» (i dati della partita dopo la mossa, un oggetto; se non cambiano restituisci quelli ricevuti)");
      }
      if (ris.punti !== undefined && ris.punti !== null) {
        var ok = typeof ris.punti === "number" && isFinite(ris.punti)
          || Array.isArray(ris.punti) && ris.punti.length === S.giocatori.length && ris.punti.every(function (p) { return typeof p === "number" && isFinite(p); });
        if (!ok) throw errore(dove + ": «punti» è un numero (a chi ha mosso) o un elenco di " + S.giocatori.length + " numeri, non " + JSON.stringify(ris.punti));
      }
      if (ris.esito !== undefined && ris.esito !== null && typeof ris.esito !== "string") {
        throw errore(dove + ": «esito» è un testo da mostrare, non " + tipo(ris.esito));
      }
      ["fase", "dopo"].forEach(function (k) {
        if (ris[k] === undefined || ris[k] === null) return;
        if (typeof ris[k] !== "string" || !(ris[k] in M.fasi || ris[k] === "esito" || ris[k] === "fine")) {
          throw errore(dove + ": «" + k + "» vale " + JSON.stringify(ris[k]) + ", che non è una fase (fasi: " + Object.keys(M.fasi).concat(["esito", "fine"]).join(", ") + ")");
        }
        if (verso(S.fase).indexOf(ris[k]) < 0) {
          throw errore(dove + ": «" + k + "» porta a «" + ris[k] + "», che non è in «verso» della fase «" + S.fase + "» nel manifesto (" + (M.fasi[S.fase].verso.join(", ") || "vuoto") + ")");
        }
      });
      if (ris.dopo === "esito") throw errore(dove + ": «dopo» è la fase dopo l'esito, non «esito»");
      // Le due forme che perdevano qualcosa senza dirlo (19/10, #186): con «fase» il motore va
      // subito lì e l'esito non si vedeva; «dopo» vale solo dopo un esito e senza era ignorato
      var conEsito = typeof ris.esito === "string" && ris.esito !== "";
      var fase = ris.fase === undefined || ris.fase === null ? null : ris.fase;
      var dopo = ris.dopo === undefined || ris.dopo === null ? null : ris.dopo;
      if (conEsito && fase !== null && fase !== "esito") {
        throw errore(dove + ": «esito» con «fase»: \"" + fase + "\" non si vede, perché «fase» va subito a «" + fase + "». "
          + "Per mostrare il testo e poi andare a «" + fase + "»: { esito: \"…\", dopo: \"" + fase + "\" }; per andarci subito senza testo: { fase: \"" + fase + "\" }");
      }
      if (!conEsito && dopo !== null && fase !== "esito") {
        throw errore(dove + ": «dopo»: \"" + dopo + "\" senza «esito» non fa niente («dopo» è la fase dopo il testo dell'esito). "
          + "Per andare subito a «" + dopo + "»: { fase: \"" + dopo + "\" }; per mostrare un testo e poi andarci: { esito: \"…\", dopo: \"" + dopo + "\" }");
      }
    }
    // Applica un comando: lo stato nuovo (S non cambia). Un errore della logica o della forma
    // lancia, con fase e comando nel messaggio
    function applica(S0, c, v, extra) {
      if (v === undefined) v = null;
      var att = attivi(S0);
      if (!attivo(att, c, v)) {
        throw errore("il comando «" + piatto(c, v) + "» adesso non vale (fase «" + S0.fase + "», attivi: " + (piatti(att).join(", ") || "nessuno") + ")");
      }
      // Chi è quale giocatore (15/10): la mossa vale per chi la manda? (una mossa del gioco in una
      // fase a turni solo per chi è di turno; «gioco anch'io» non due volte dalla stessa voce)
      var chi = chiMuove(S0, c, extra);
      if (!chi.ok) throw nonTua(chi);
      var S = copia(S0, "stato");
      S.n = S0.n + 1;
      var nome = nomeChiuso(extra && extra.giocatore);
      var nuovoPosto = legame(extra);
      nuovoPosto.nome = nome;
      if (S0.fase === "preparazione") {
        var gia = (S0.iscritti || []).map(function (x) { var o = legame(x); o.nome = x && x.nome || null; o.scritto = false; return o; });
        if (c === "anchio") {
          // «gioco anch'io»: un posto in più, con il nome di chi l'ha detto se la voce è
          // riconosciuta (lo manda Calliope), altrimenti «Giocatore N», legato allo schermo e
          // alla voce di chi l'ha detto o toccato; la stessa voce (o lo stesso nome) due volte
          // non prende due posti
          var stesso = (S0.iscritti || []).some(function (x) {
            return x && (nome && x.nome && x.nome.toLowerCase() === nome.toLowerCase() || nuovoPosto.voce && x.voce === nuovoPosto.voce);
          });
          if (!stesso) S.iscritti = (S0.iscritti || []).concat([nuovoPosto]);
          S.numero = Math.max(M.gmin, S.iscritti.length);
          return S;
        }
        avviaPartita(S, c === "giocatori" ? v : Math.max(S0.numero, gia.length), gia);
        return S;
      }
      if (c === "anchio") {
        // A partita cominciata (15/10, «una persona che entra a metà»): con GIOCO.entra il nuovo
        // giocatore entra adesso, a zero punti, e gioca quando arriva il suo turno; senza, entra
        // dalla prossima partita («ancora»), perché la logica ha già preparato i dati per chi
        // c'era
        if (S0.fase !== "fine" && typeof GIOCO.entra === "function") {
          var gnuovo = { nome: nome || "Giocatore " + (S0.giocatori.length + 1), punti: 0, scritto: false };
          if (nuovoPosto.schermo) gnuovo.schermo = nuovoPosto.schermo;
          if (nuovoPosto.voce) gnuovo.voce = nuovoPosto.voce;
          S.giocatori = S0.giocatori.concat([gnuovo]);
          S.numero = S.giocatori.length;
          var cx = contesto(S);
          cx.nuovo = S.giocatori.length - 1;
          var d2 = GIOCO.entra(copia(S0.dati, "dati"), cx);
          if (d2 === undefined || d2 === null || typeof d2 !== "object" || Array.isArray(d2)) {
            throw errore("GIOCO.entra restituisce " + tipo(d2) + ": deve restituire i dati della partita con il giocatore nuovo (un oggetto)");
          }
          S.dati = copia(d2, "GIOCO.entra");
          return S;
        }
        S.entrano = (S0.entrano || []).concat([nuovoPosto]);
        return S;
      }
      if (S0.fase === "esito") {
        S.fase = S0.dopo || M.inizio;
        if (S0.passa) avanzaTurno(S);
        S.esito = null; S.dopo = null; S.passa = false;
        return S;
      }
      if (S0.fase === "fine") {
        var poi = S0.giocatori.concat(S0.entrano || []).slice(0, M.gmax);
        avviaPartita(S, Math.min(M.gmax, S0.numero + (S0.entrano || []).length), poi);
        return S;
      }
      if (c === "fine_partita") { S.fase = "fine"; return S; }
      var fn = GIOCO.mosse && GIOCO.mosse[S0.fase] && GIOCO.mosse[S0.fase][c];
      var dove = "GIOCO.mosse." + S0.fase + "." + c + (v === null ? "" : " (valore " + JSON.stringify(v) + ")");
      if (typeof fn !== "function") throw errore("manca GIOCO.mosse." + S0.fase + "." + c + "(dati, { valore, chi }): la funzione della mossa");
      var ctx = contesto(S0);
      ctx.valore = v;
      ctx.giocatore = extra && extra.giocatore || null;
      // In una fase senza turni muove chiunque: «chi» e i punti sono di chi ha mosso, se si sa
      // (la sua voce, o il suo schermo con un giocatore solo)
      var daChi = !M.fasi[S0.fase].turni && chi.da !== null && chi.da !== undefined && S0.giocatori[chi.da] ? chi.da : null;
      if (daChi !== null) ctx.chi = S0.giocatori[daChi].nome;
      // Senza turni, con più giocatori e senza sapere chi ha mosso (20/10, #197, revisione
      // dell'analisi della PR #200): prima «chi» e i punti erano del giocatore di «tocca», che
      // senza turni resta il primo: i punti di chiunque andavano al Giocatore 1. Ora chi è null
      else if (ignoto(S0, null)) ctx.chi = null;
      var ris = fn(copia(S0.dati, "dati"), ctx);
      return risultato(S0, S, ris, dove, daChi);
    }
    // L'uscita da una fase «tela» (il gioco libero): come il risultato di una mossa
    function esciTela(S0, ris) {
      var f = M.fasi[S0.fase];
      if (!f || f.pagina !== "tela") throw errore("tela.esci fuori da una fase «tela» (fase «" + S0.fase + "»)");
      var S = copia(S0, "stato");
      S.n = S0.n + 1;
      return risultato(S0, S, ris, "tela.esci nella fase «" + S0.fase + "»");
    }
    // Una fase senza turni, con più giocatori, in cui non si sa chi ha mosso (la voce non
    // riconosciuta, nessuno schermo con un giocatore solo, la tela)
    var puntiPersi = [];
    function ignoto(S0, daChi) {
      return !M.fasi[S0.fase].turni && (daChi === null || daChi === undefined) && S0.giocatori.length > 1;
    }
    function risultato(S0, S, ris, dove, daChi) {
      // Lì un numero di punti non va a nessuno (20/10, #197; prima andava al Giocatore 1): se
      // vanno a chi muove serve una fase con i turni, e la prova di fumo lo avvisa
      var chiPos = daChi !== null && daChi !== undefined ? daChi : ignoto(S0, daChi) ? -1 : S0.tocca;
      var chi = S0.giocatori[chiPos] ? S0.giocatori[chiPos].nome : null;
      controlla(ris, dove, S0);
      S.dati = copia(ris.dati, dove + ", dati");
      var guadagno = 0;
      if (Array.isArray(ris.punti)) ris.punti.forEach(function (p, i) { S.giocatori[i].punti += p; });
      else if (typeof ris.punti === "number" && S.giocatori[chiPos]) { S.giocatori[chiPos].punti += ris.punti; guadagno = ris.punti; }
      // Un numero di punti che non va a nessuno (senza turni e chi non si sa, revisione della
      // PR #201): contato, perché la prova di fumo lo dica (nel riquadro non cambia niente)
      else if (typeof ris.punti === "number" && ris.punti !== 0 && chiPos === -1 && !puntiPersi.length) puntiPersi.push(dove);   // basta il primo
      var meta = ris.fase || (ris.esito ? "esito" : S0.fase);
      var passa = M.fasi[S0.fase].turni && !ris.ancora && S.giocatori.length > 1;
      if (meta === "esito") {
        S.esito = { testo: String(ris.esito || ""), punti: guadagno, chi: chi };
        S.dopo = ris.dopo || S0.fase;
        S.passa = passa;
      } else {
        S.esito = null;
        if (passa) avanzaTurno(S);
      }
      S.fase = meta;
      return S;
    }
    // Una casella della griglia, controllata: {testo, colore, risorsa, comando, valore}
    function casella(fase, k, r, c) {
      var dove = "GIOCO.vista." + fase + ".caselle[" + r + "][" + c + "]";
      if (k === null || k === undefined || k === "") return {};
      if (typeof k === "string" || typeof k === "number") return { testo: String(k) };
      if (typeof k !== "object" || Array.isArray(k)) throw errore(dove + " è " + tipo(k) + ": un testo o un oggetto { testo, colore, risorsa, comando, valore }");
      var altri = Object.keys(k).filter(function (x) { return CHIAVI_CASELLA.indexOf(x) < 0; });
      if (altri.length) throw errore(dove + ": campi che il motore non conosce: " + altri.join(", ") + " (solo testo, colore, risorsa, comando, valore)");
      var out = {};
      if (k.testo !== undefined && k.testo !== null && k.testo !== "") {
        if (typeof k.testo !== "string" && typeof k.testo !== "number") throw errore(dove + ".testo è " + tipo(k.testo) + ": un testo");
        out.testo = String(k.testo);
      }
      if (k.colore) {
        var col = String(k.colore).toLowerCase();
        if (COLORI[col]) out.colore = COLORI[col];
        else if (COLORE_HEX.test(col)) out.colore = col;
        else throw errore(dove + ".colore «" + corto(k.colore, 20) + "»: un nome (" + Object.keys(COLORI).join(", ") + ") o #rrggbb");
      }
      if (k.risorsa) {
        if (typeof k.risorsa !== "string" || !RISORSA.test(k.risorsa)) throw errore(dove + ".risorsa «" + corto(k.risorsa, 30) + "»: il nome di un disegno .svg di «scheda.risorse»");
        out.risorsa = k.risorsa;
      }
      if (k.comando !== undefined && k.comando !== null) {
        var d = comando(fase, k.comando);
        if (!d) throw errore(dove + ".comando «" + corto(k.comando, 20) + "»: non è un comando della fase «" + fase + "» nel manifesto");
        var v = k.valore === undefined ? null : k.valore;
        if (d.valori && d.valori.indexOf(v) < 0) throw errore(dove + ".valore " + JSON.stringify(v) + ": fuori da quelli dichiarati per «" + k.comando + "» (" + JSON.stringify(d.valori.slice(0, 12)) + ")");
        if (!d.valori && v !== null) throw errore(dove + ": il comando «" + k.comando + "» non ha valori (togli «valore»)");
        out.comando = k.comando; out.valore = v;
      }
      return out;
    }
    function vista(S) {
      var fn = GIOCO.vista && GIOCO.vista[S.fase];
      var f = M.fasi[S.fase];
      var griglia = !!(f && f.pagina === "griglia");
      if (typeof fn !== "function") {
        if (griglia) throw errore("manca GIOCO.vista." + S.fase + "(dati, ctx) con «caselle»: la fase ha la pagina «griglia»");
        return {};
      }
      var v = fn(copia(S.dati, "vista"), contesto(S));
      if (v === undefined || v === null) v = {};
      if (typeof v !== "object" || Array.isArray(v)) throw errore("GIOCO.vista." + S.fase + " restituisce " + tipo(v) + ": un oggetto { titolo, sottotitolo, testo" + (griglia ? ", caselle" : "") + " }");
      var altri = Object.keys(v).filter(function (k) { return CHIAVI_VISTA.indexOf(k) < 0; });
      if (altri.length) throw errore("GIOCO.vista." + S.fase + " restituisce campi che il motore non conosce: " + altri.join(", ") + " (solo titolo, sottotitolo, testo" + (griglia ? ", caselle" : "") + ": il disegno è del motore)");
      var out = {};
      ["titolo", "sottotitolo", "testo"].forEach(function (k) {
        if (v[k] === undefined || v[k] === null) return;
        if (typeof v[k] !== "string" && typeof v[k] !== "number") throw errore("GIOCO.vista." + S.fase + "." + k + " è " + tipo(v[k]) + ": un testo");
        if (typeof v[k] === "number" && !isFinite(v[k])) throw errore("GIOCO.vista." + S.fase + "." + k + " è " + v[k]);
        out[k] = String(v[k]);
      });
      if (v.caselle !== undefined && v.caselle !== null && !griglia) {
        throw errore("GIOCO.vista." + S.fase + ".caselle: solo in una fase con la pagina «griglia» (la fase «" + S.fase + "» ha «" + (f ? f.pagina : S.fase) + "»)");
      }
      if (griglia) {
        var cs = v.caselle;
        if (!Array.isArray(cs) || !cs.length || cs.length > MAX_LATO || !cs.every(Array.isArray)) {
          throw errore("GIOCO.vista." + S.fase + ".caselle: un elenco di righe, ognuna un elenco di caselle (da 1×1 a " + MAX_LATO + "×" + MAX_LATO + "), per esempio [[\"X\", \"\", \"O\"], …]");
        }
        var C = cs[0].length;
        if (!C || C > MAX_LATO || !cs.every(function (r) { return r.length === C; })) {
          throw errore("GIOCO.vista." + S.fase + ".caselle: tutte le righe con lo stesso numero di caselle, da 1 a " + MAX_LATO + " (ne ha " + cs.map(function (r) { return r.length; }).join(", ") + ")");
        }
        out.caselle = cs.map(function (r, i) { return r.map(function (k, j) { return casella(S.fase, k, i, j); }); });
      }
      return out;
    }
    function classifica(S) {
      return S.giocatori.map(function (g, i) { return { nome: g.nome, punti: g.punti, i: i }; })
        .sort(function (a, b) { return b.punti - a.punti || a.i - b.i; });
    }
    // L'istantanea: ciò che si sa della partita, per i test e (dopo) per Calliope
    function istantanea(S) {
      var att = {};
      try { att = attivi(S); } catch (e) { att = {}; }
      // «gioco anch'io» a partita cominciata è di Calliope (solo a voce): i test del gioco non
      // lo vedono
      if (S.fase !== "preparazione") delete att.anchio;
      return { n: S.n, fase: S.fase, tocca: S.giocatori[S.tocca] ? S.giocatori[S.tocca].nome : null,
               turno: S.turno, giocatori: S.giocatori.map(function (g) { return { nome: g.nome, punti: g.punti }; }),
               esito: S.esito ? S.esito.testo : null, comandi: att };
    }
    // Il nome scritto sullo schermo (14/10, passo 4 del progetto): chi gioca tocca il suo nome
    // nella fascia dei punti e lo scrive. La forma chiusa (lettere, spazi e apostrofo, al più 20
    // caratteri e due parole), diverso dagli altri; lo stato nuovo, o un errore per chi scrive
    function rinomina(S0, i, testo) {
      if (!S0.giocatori[i]) throw errore("nessun giocatore " + (i + 1));
      var nome = nomeChiuso(testo);
      if (!nome) {
        var e = new Error("Un nome di una o due parole, solo lettere (al più 20).");
        e.name = "NomeNonValido";
        throw e;
      }
      var doppio = S0.giocatori.some(function (g, k) { return k !== i && String(g.nome).toLowerCase() === nome.toLowerCase(); });
      if (doppio) {
        var e2 = new Error("C'è già un giocatore che si chiama così.");
        e2.name = "NomeNonValido";
        throw e2;
      }
      var S = copia(S0, "stato");
      S.n = S0.n + 1;
      S.giocatori[i].nome = nome;
      S.giocatori[i].scritto = true;
      return S;
    }
    // La ripresa dopo «Riapri» (14/10, decisione 7 di chi amministra): lo stato intero della
    // partita che il motore ha mandato a Calliope con l'ultima istantanea valida, e che Calliope
    // gli restituisce all'avvio di un riquadro nuovo. Si controlla prima di usarlo (la forma, la
    // fase, i giocatori; comandi attivi e pagina calcolabili): se non va, partita nuova
    function riprendi(R) {
      if (!R || typeof R !== "object" || Array.isArray(R)) throw errore("ripresa: non è uno stato");
      if (typeof R.n !== "number" || !(R.n >= 0) || Math.floor(R.n) !== R.n) throw errore("ripresa: «n»");
      var standard = ["preparazione", "esito", "fine"];
      if (typeof R.fase !== "string" || !(R.fase in M.fasi || standard.indexOf(R.fase) >= 0)) throw errore("ripresa: fase");
      if (!Array.isArray(R.giocatori) || R.giocatori.length > Math.max(M.gmax, 1)) throw errore("ripresa: giocatori");
      R.giocatori.forEach(function (g) {
        if (!g || typeof g.nome !== "string" || typeof g.punti !== "number" || !isFinite(g.punti)) throw errore("ripresa: un giocatore");
      });
      if (R.fase !== "preparazione" && (!R.giocatori.length || typeof R.dati !== "object" || R.dati === null)) throw errore("ripresa: dati");
      if (typeof R.tocca !== "number" || R.tocca < 0 || (R.giocatori.length && R.tocca >= R.giocatori.length)) throw errore("ripresa: tocca");
      var S = copia(R, "ripresa");
      // gli iscritti e chi entra dalla prossima partita: solo nome e legami (15/10)
      ["iscritti", "entrano"].forEach(function (k) {
        S[k] = (Array.isArray(S[k]) ? S[k] : []).slice(0, M.gmax).map(function (x) {
          var o = legame(x); o.nome = nomeChiuso(x && x.nome); return o;
        });
      });
      S.giocatori = S.giocatori.map(function (g) {
        var o = { nome: g.nome, punti: g.punti, scritto: !!g.scritto }, l = legame(g);
        if (l.schermo) o.schermo = l.schermo;
        if (l.voce) o.voce = l.voce;
        return o;
      });
      attivi(S);
      pagina(S);
      return S;
    }
    // L'istantanea per Calliope (14/10, passo 2 del progetto): numerata, con a chi tocca come
    // posizione, i punti, l'esito (al più 160 caratteri: Calliope non lo dice, è del gioco) e i
    // comandi a voce piatti che valgono adesso. Il server la valida contro il manifesto e la
    // tiene come stato della partita (calliope/estensioni/macchina.py, valida_istantanea)
    function perCalliope(S, senzaComandi) {
      var att = {};
      if (!senzaComandi) { try { att = attivi(S); } catch (e) { att = {}; } }
      var conTurni = S.fase !== "preparazione" && S.giocatori.length > 0;
      return { n: S.n, fase: S.fase, tocca: conTurni ? S.tocca : null, turno: S.turno,
               giocatori: S.giocatori.map(function (g) {
                 var x = { nome: String(g.nome), punti: g.punti };
                 if (g.scritto) x.scritto = true;
                 // chi è quale giocatore (15/10): lo schermo e la voce (un segno opaco) legati
                 if (g.schermo) x.schermo = g.schermo;
                 if (g.voce) x.voce = g.voce;
                 return x;
               }),
               esito: S.esito && S.esito.testo ? String(S.esito.testo).slice(0, 160) : null,
               comandi: piatti(att) };
    }
    // L'etichetta di un pulsante
    function etichetta(fase, c, v) {
      if (c === "giocatori") return v === 1 ? "1 giocatore" : v + " giocatori";
      if (ETICHETTE[c]) return ETICHETTE[c];
      var d = comando(fase, c) || { forme: [c], etichetta: "" };
      var testoV = v === null ? "" : d.sinonimi ? d.sinonimi[v][0] : String(v);
      var base = d.etichetta || d.forme[0] || c;
      var t = base.indexOf("{n}") >= 0 ? base.replace("{n}", testoV) : (v === null ? base : base + " " + testoV);
      return t.charAt(0).toUpperCase() + t.slice(1);
    }
    // Il contenuto della pagina di adesso: modello, testi, pulsanti, caselle, giocatori. Lo
    // disegna il riquadro e lo misura la prova di fumo (impagina, controllaPalco)
    function pagina(S) {
      var att = attivi(S), v = vista(S), f = M.fasi[S.fase];
      var modello = S.fase === "preparazione" ? (M.gmin < M.gmax ? "scelte" : "titolo")
        : S.fase === "esito" ? "messaggio" : S.fase === "fine" ? "classifica" : f.pagina;
      var p = { fase: S.fase, modello: modello, titolo: "", sottotitolo: "", testo: "", grande: "", extra: "",
                pulsanti: [], caselle: null, giocatori: S.giocatori.map(function (g) { return { nome: g.nome, punti: g.punti }; }),
                tocca: S.tocca, mostraTocca: S.giocatori.length > 1 && !!(f && f.turni), fascia: false, classifica: null,
                fonti: {}, attivi: att };
      ["titolo", "sottotitolo", "testo"].forEach(function (k) {
        if (v[k]) { p[k] = v[k]; p.fonti[k] = "GIOCO.vista." + S.fase + "." + k; }
      });
      if (S.fase === "preparazione") {
        if (!p.titolo) { p.titolo = titoloGioco || "Nuova partita"; p.fonti.titolo = titoloGioco ? "il titolo nel manifesto" : ""; }
        var gioca = (S.iscritti || []).map(function (x, k) { return x && x.nome || "Giocatore " + (k + 1); });
        if (!p.testo && (M.gmin < M.gmax || gioca.length)) {
          p.testo = (M.gmin < M.gmax ? "Quanti giocatori?" : "") + (gioca.length ? (M.gmin < M.gmax ? " " : "") + "Giocano: " + gioca.join(", ") : "");
        }
      } else if (S.fase === "esito") {
        if (S.esito) {
          p.grande = S.esito.testo; p.fonti.grande = "«esito» della mossa";
          if (S.esito.punti) p.extra = (S.esito.punti > 0 ? "+" : "") + S.esito.punti + (Math.abs(S.esito.punti) === 1 ? " punto" : " punti") + (S.giocatori.length > 1 && S.esito.chi ? " a " + S.esito.chi : "");
        }
      } else if (S.fase === "fine") {
        if (!p.titolo) p.titolo = "Partita finita";
        p.classifica = classifica(S).map(function (g) { return { nome: g.nome, punti: g.punti }; });
      } else if (!p.sottotitolo && p.mostraTocca) {
        var chiTocca = String(S.giocatori[S.tocca].nome);
        p.sottotitolo = (/^[aA]/.test(chiTocca) ? "Tocca ad " : "Tocca a ") + chiTocca;
      }
      if (modello === "messaggio" && S.fase !== "esito" && p.testo && !p.grande) {
        p.grande = p.testo; p.fonti.grande = p.fonti.testo; p.testo = ""; delete p.fonti.testo;
      }
      p.fascia = S.fase !== "preparazione" && ["scelte", "griglia", "messaggio", "tela"].indexOf(modello) >= 0;
      // i pulsanti: un comando attivo per valore; in una griglia quelli che una casella mostra
      // diventano la casella stessa
      var nelleCaselle = {};
      if (v.caselle) {
        p.caselle = v.caselle.map(function (r) {
          return r.map(function (k) {
            var x = { testo: k.testo || "", colore: k.colore || "", risorsa: k.risorsa || "" };
            if (k.comando !== undefined) {
              nelleCaselle[piatto(k.comando, k.valore)] = true;
              if (attivo(att, k.comando, k.valore)) {
                x.pulsante = true; x.comando = k.comando; x.valore = k.valore;
                x.etichetta = etichetta(S.fase, k.comando, k.valore);
              }
            }
            return x;
          });
        });
      }
      // «gioco anch'io» a partita cominciata è solo a voce: la pagina del gioco non cambia
      var conPulsante = Object.keys(att).filter(function (c) { return c !== "anchio" || S.fase === "preparazione"; });
      // una tela con un orientamento solo (15/10): il palco è sempre quello
      p.orientamento = f && f.pagina === "tela" && f.orientamento && S.fase !== "preparazione"
        && S.fase !== "esito" && S.fase !== "fine" ? f.orientamento : null;
      conPulsante.forEach(function (c) {
        (att[c] === true ? [null] : att[c]).forEach(function (x) {
          if (nelleCaselle[piatto(c, x)]) return;
          p.pulsanti.push({ c: c, v: x, etichetta: etichetta(S.fase, c, x),
                            fonte: comando(S.fase, c) ? "l'etichetta del comando «" + c + "» nel manifesto" : "" });
        });
      });
      return p;
    }
    return { M: M, nuovo: nuovo, attivi: attivi, piatti: piatti, daPiatto: daPiatto, applica: applica, esciTela: esciTela,
             puntiPersi: function () { return puntiPersi.slice(); },
             vista: vista, istantanea: istantanea, perCalliope: perCalliope, classifica: classifica, etichetta: etichetta,
             pagina: pagina, contesto: contesto, piatto: piatto, rinomina: rinomina, riprendi: riprendi,
             chiMuove: chiMuove };
  }

  // ═══════════════════ nel riquadro (e nel DOM finto della prova): disegno, pulsanti, voce ═══════════════════
  function avvia(GIOCO, conf, opzioni) {
    opzioni = opzioni || {};
    var doc = G.document;
    var radice = doc.getElementById("gioco");
    var cal = G.calliope;
    var finto = !!opzioni.finto;
    var segnala = opzioni.errore || function (e) { setTimeout(function () { throw e; }, 0); };
    var nucleo, S, timerEsito = null, ultimoErrore = "", orientamento = null, palco = null, imp = null;
    // La partita condivisa con il motore (14/10): «autorevole» (questo motore tiene la partita:
    // il solo caso fuori da una partita condivisa) o «specchio» (disegna lo stato che arriva e
    // manda le mosse a chi la tiene)
    var ruolo = "autorevole";
    var firmaPalco = null;
    // Il numero del posto di questo schermo nella partita (15/10, chi è quale giocatore: lo dà
    // Calliope all'avvio); «Gira il telefono» detto a Calliope una volta per riquadro
    var mioPosto = null, giraDetto = false, avvioTocco = false;
    function el(tag, classe, testo) {
      var n = doc.createElement(tag);
      if (classe) n.className = classe;
      if (testo !== undefined) n.textContent = testo;
      return n;
    }
    function mostraErrore(e) {
      ultimoErrore = String(e && e.message || e);
      var p = el("p", "errore-gioco", "Errore nel gioco: " + ultimoErrore.slice(0, 300));
      radice.appendChild(p);
      segnala(e);
    }
    try { nucleo = crea(GIOCO, conf && conf.macchina, conf && conf.giocatori, { titolo: opzioni.titolo || (conf && conf.titolo) || "" }); }
    catch (e) { radice.replaceChildren(el("div", "motore")); mostraErrore(e); return null; }
    S = nucleo.nuovo();
    function M() { return nucleo.M; }
    function finestra() { return [Number(G.innerWidth) || 0, Number(G.innerHeight) || 0]; }
    function orientamentoAdesso() { var f = finestra(); return f[1] > f[0] ? "verticale" : "orizzontale"; }
    function scala() {
      if (!palco || !imp) return;
      var f = finestra();
      var s = f[0] && f[1] ? Math.min(f[0] / imp.W, f[1] / imp.H) : 1;
      palco.style.cssText = "width:" + imp.W + "px!important;height:" + imp.H + "px!important;"
        + "transform:translate(-50%,-50%) scale(" + s.toFixed(4) + ")!important";
    }
    function stile(n, b) {
      var css = "left:" + b.x + "px!important;top:" + b.y + "px!important;width:" + b.w + "px!important;height:" + b.h + "px!important";
      if (b.f) css += ";font-size:" + b.f + "px!important";
      if (b.colore) css += ";background:" + b.colore + "!important";
      n.style.cssText = css;
    }
    function elemento(b) {
      var n;
      if (b.tipo === "pulsante" || (b.tipo === "casella" && b.comando !== undefined)) {
        n = el("button", b.tipo === "casella" ? "casella comando" : "comando", b.testo || "");
        n.type = "button";
        n.dataset.comando = b.comando;
        if (b.valore !== null && b.valore !== undefined) n.dataset.valore = String(b.valore);
        n.setAttribute("aria-label", b.etichetta || b.testo || "");
        var c = b.comando, v = b.valore === undefined ? null : b.valore;
        n.addEventListener("click", function () { mossa(c, v, { schermo: mioPosto }); });
      } else if (b.tipo === "titolo") n = el("h1", "titolo", b.testo);
      else if (b.tipo === "giocatore") {
        // Il nome nella fascia dei punti: un tocco e si scrive il proprio (14/10, passo 4).
        // «mio»: il giocatore di questo schermo, quando i giocatori sono su più schermi (15/10)
        n = el("button", "giocatore nome" + (b.tocca ? " tocca" : "") + (mio(b.indice) ? " mio" : ""), b.testo);
        n.type = "button";
        n.setAttribute("aria-label", "Cambia il nome: " + b.testo);
        var ind = b.indice, box = b;
        n.addEventListener("click", function () { scriviNome(ind, box); });
      }
      else if (b.tipo === "fascia") n = el("div", "punti");
      else if (b.tipo === "riga") n = el("div", "riga" + (b.tocca ? " tocca" : "") + (b.primo ? " primo" : ""), b.testo);
      else if (b.tipo === "casella") n = el("div", "casella", b.testo || "");
      else if (b.tipo === "tela") n = el("div", "tela");
      else n = el("p", b.tipo, b.testo);
      if (b.risorsa) {
        var src = null;
        try { src = cal && typeof cal.risorsa === "function" ? cal.risorsa(b.risorsa) : null; } catch (e) { src = null; }
        if (src) { var im = el("img", "risorsa"); im.alt = ""; im.src = src; n.appendChild(im); }
      }
      n.dataset.scatola = b.tipo;
      if (b.scritta) n.dataset.scritta = "1";
      stile(n, b);
      return n;
    }
    function mio(i) {
      var gs = S.giocatori || [];
      if (!mioPosto || !gs[i] || gs[i].schermo !== mioPosto) return false;
      return gs.some(function (g) { return g.schermo && g.schermo !== mioPosto; });
    }
    // Un telefono o un tablet: lo dice la pagina degli schermi all'avvio, o il riquadro stesso
    function alTocco() {
      if (avvioTocco) return true;
      try { return !!(G.matchMedia && G.matchMedia("(pointer: coarse)").matches); } catch (e) { return false; }
    }
    function disegna() {
      var pag = nucleo.pagina(S);
      var prima = orientamento;
      orientamento = orientamentoAdesso();
      // girato lo schermo, la misura vera si rimanda anche se non cambia (Calliope sa che la
      // pagina ci sta anche nell'altro orientamento)
      if (prima !== null && prima !== orientamento) firmaPalco = null;
      // Una tela con un orientamento solo (15/10): il palco è quello dichiarato, anche se la
      // finestra è girata dall'altra parte (il gioco non si ferma: è solo più piccolo)
      imp = impagina(pag, pag.orientamento || orientamento);
      palco = el("div", "motore palco " + imp.orientamento + " fase-" + S.fase + " pagina-" + pag.modello);
      scala();
      var area = null;
      imp.scatole.forEach(function (b) {
        var n = elemento(b);
        if (b.tipo === "tela") area = n;
        palco.appendChild(n);
      });
      radice.replaceChildren(palco);
      gira(pag.orientamento && pag.orientamento !== orientamento ? pag.orientamento : null);
      if (area) tela(area, imp.scatole.filter(function (b) { return b.tipo === "tela"; })[0]);
      misuraVera(pag);
      return pag.attivi;
    }
    // «Gira il telefono» (15/10, decisione 3 del 12/10): sul telefono (o un tablet) girato
    // dall'altra parte rispetto alla tela, una fascia in alto lo dice, sopra il gioco ma senza
    // prendere i tocchi; a Calliope lo si dice una volta per riquadro (lo dice a voce una volta
    // per schermo). Su un PC o una TV la finestra non si gira: niente fascia
    function gira(o) {
      if (!o || !alTocco()) return;
      var f = el("div", "gira-telefono", "Gira il telefono " + (o === "orizzontale" ? "in orizzontale" : "in verticale"));
      f.setAttribute("role", "status");
      radice.appendChild(f);
      if (!giraDetto && CANALE && typeof CANALE.gira === "function") {
        giraDetto = true;
        try { CANALE.gira(o); } catch (e) { /* niente */ }
      }
    }
    // Il campo per scrivere il nome sopra la fascia (non è una scatola del palco: sparisce al
    // prossimo disegno). Invio o uscita dal campo confermano, Esc annulla
    function scriviNome(i, b) {
      if (!palco || !S.giocatori[i]) return;
      var vecchio = palco.querySelector ? palco.querySelector(".scrivi-nome") : null;
      if (vecchio && vecchio.parentNode) vecchio.parentNode.removeChild(vecchio);
      var campo = el("input", "scrivi-nome");
      campo.type = "text";
      campo.value = S.giocatori[i].nome;
      try { campo.maxLength = 20; campo.setAttribute("maxlength", "20"); } catch (e) { /* niente */ }
      campo.setAttribute("aria-label", "Il nome di chi gioca");
      campo.setAttribute("autocomplete", "off");
      var w = Math.max(360, b.w), x = Math.max(0, Math.min(imp.W - w, b.x - (w - b.w) / 2));
      campo.style.cssText = "position:absolute!important;left:" + x + "px!important;top:" + Math.max(0, b.y - 12)
        + "px!important;width:" + w + "px!important;height:" + (b.h + 24) + "px!important;font-size:30px!important;z-index:5";
      var fatto = false, n0 = S.n;
      function chiudi(conferma) {
        if (fatto) return;
        fatto = true;
        if (campo.parentNode) campo.parentNode.removeChild(campo);
        if (!conferma || S.n !== n0) return;
        var S2;
        try { S2 = nucleo.rinomina(S, i, campo.value); }
        catch (e) {
          if (e && e.name === "NomeNonValido") { avviso(e.message); return; }
          mostraErrore(e); return;
        }
        if (ruolo === "specchio") {
          // il nome lo scrive il motore che tiene la partita
          try { if (CANALE && typeof CANALE.mossa === "function") CANALE.mossa({ rinomina: i, nome: S2.giocatori[i].nome }); } catch (e) { /* niente */ }
          return;
        }
        aggiorna(S2);
      }
      campo.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") { ev.preventDefault && ev.preventDefault(); chiudi(true); }
        else if (ev.key === "Escape") chiudi(false);
      });
      campo.addEventListener("change", function () { chiudi(true); });
      campo.addEventListener("blur", function () { chiudi(true); });
      palco.appendChild(campo);
      try { campo.focus(); campo.select(); } catch (e) { /* niente */ }
    }
    function avviso(t) {
      if (!palco) return;
      var a = el("p", "avviso-nome", t);
      a.style.cssText = "position:absolute!important;left:0!important;right:0!important;top:0!important;font-size:28px!important;z-index:6";
      palco.appendChild(a);
      setTimeout(function () { if (a.parentNode) a.parentNode.removeChild(a); }, 3000);
    }
    function tela(area, b) {
      var fn = GIOCO.tela && GIOCO.tela[S.fase];
      if (typeof fn !== "function") { mostraErrore(errore("manca GIOCO.tela." + S.fase + "(area, dati, tela): la fase ha la pagina «tela»")); return; }
      var fase = S.fase, n = S.n;
      fn(area, JSON.parse(JSON.stringify(S.dati)), {
        giocatori: nucleo.contesto(S).giocatori,
        larghezza: b ? b.w : 0, altezza: b ? b.h : 0,
        esci: function (ris) {
          if (S.fase !== fase || S.n !== n) return false;
          var S2;
          try { S2 = nucleo.esciTela(S, ris); } catch (e) { mostraErrore(e); return false; }
          aggiorna(S2);
          return true;
        },
      });
    }
    // La misura vera (nel browser): dopo il disegno, ciò che esce dal palco o ha il testo
    // tagliato sullo schermo di adesso; a Calliope solo quando cambia (anche «nessun difetto»)
    function misuraVera(pag) {
      if (finto || !CANALE || typeof CANALE.palco !== "function") return;
      var p0 = palco, imp0 = imp;
      var dopo = G.requestAnimationFrame ? function (f) { G.requestAnimationFrame(function () { G.requestAnimationFrame(f); }); }
        : function (f) { setTimeout(f, 50); };
      dopo(function () {
        if (p0 !== palco || !p0.isConnected) return;
        var d = [];
        try {
          difettiInParole(imp0, controllaPalco(imp0)).forEach(function (t) { d.push(t); });
          var pr = p0.getBoundingClientRect(), s = pr.width / imp0.W;
          if (!(s > 0)) return;
          var figli = p0.children;
          for (var i = 0; i < figli.length && d.length < 3; i++) {
            var n = figli[i];
            if (!n.dataset || !n.dataset.scatola) continue;
            var r = n.getBoundingClientRect();
            var desc = "<" + n.tagName.toLowerCase() + " class=\"" + corto(n.className, 30) + "\">" + (n.textContent ? " «" + corto(n.textContent) + "»" : "");
            if ((r.left - pr.left) / s < -1 || (r.top - pr.top) / s < -1 || (r.right - pr.left) / s > imp0.W + 1 || (r.bottom - pr.top) / s > imp0.H + 1) {
              d.push("fuori dal palco sullo schermo: " + desc);
            } else if ((n.dataset.scritta || n.dataset.scatola === "tela") && (n.scrollHeight > n.clientHeight + tolleranza(n) || n.scrollWidth > n.clientWidth + tolleranza(n))) {
              d.push((n.dataset.scatola === "tela" ? "il disegno della tela esce dalla tela" : "testo tagliato sullo schermo") + ": " + desc);
            }
          }
        } catch (e) { return; }
        var firma = JSON.stringify(d);
        if (firma === firmaPalco) return;
        firmaPalco = firma;
        try { CANALE.palco(d.slice(0, 3)); } catch (e) { /* niente */ }
      });
    }
    // Il margine della misura vera: con line-height 1,2 i caratteri (ascendenti e discendenti
    // del carattere di sistema, ~1,33 em) sporgono un poco dalla riga e lo scroll li conta; una
    // riga in più o una parola che esce sono molto di più
    function tolleranza(n) {
      var f = 16;
      try { f = parseFloat(G.getComputedStyle(n).fontSize) || 16; } catch (e) { /* niente */ }
      return Math.max(2, f * 0.3);
    }
    // L'istantanea a Calliope dopo ogni disegno (14/10): i comandi a voce che valgono adesso,
    // a chi tocca, i punti; con `muto` (un errore nel disegno) senza comandi
    // Con l'istantanea va lo stato intero per la ripresa dopo «Riapri» (decisione 7), se sta in
    // 16 000 caratteri (come `salva`): oltre, Calliope non può riprendere quella partita
    var MAX_RIPRESA = 16000;
    function voce(muto) {
      if (!CANALE || typeof CANALE.stato !== "function" || ruolo !== "autorevole") return;
      var r = null;
      if (!muto) {
        try { var t = JSON.stringify(S); if (t.length <= MAX_RIPRESA) r = JSON.parse(t); } catch (e) { r = null; }
      }
      try { CANALE.stato(nucleo.perCalliope(S, !!muto), r); } catch (e) { /* senza voce si gioca toccando */ }
    }
    function aggiorna(S2) {
      S = S2;
      if (timerEsito) { clearTimeout(timerEsito); timerEsito = null; }
      var att;
      try { att = disegna(); }
      catch (e) { radice.replaceChildren(el("div", "motore")); mostraErrore(e); voce(true); return; }
      voce(false);
      if (ruolo !== "autorevole") return;
      if (S.fase === "esito" && M().esito_s > 0) {
        var n = S.n;
        timerEsito = setTimeout(function () { if (S.n === n && S.fase === "esito") mossa("avanti", null, {}); }, M().esito_s * 1000);
      }
      if (S.fase === "fine" && cal && typeof cal.fine === "function" && ruolo === "autorevole") {
        try { cal.fine({ classifica: nucleo.classifica(S).map(function (g) { return { nome: g.nome, punti: g.punti }; }) }); } catch (e) { /* niente */ }
      }
    }
    function mossa(c, v, extra) {
      if (ruolo === "specchio") {
        // Uno specchio non scrive lo stato: manda la mossa al motore che tiene la partita (il
        // server ci aggiunge il numero di questo schermo). Una mossa del giocatore di un altro
        // schermo non parte: lo dice un avviso (15/10)
        var flat = nucleo.piatto(c, v), att = [];
        try { att = nucleo.piatti(nucleo.attivi(S)); } catch (e) { att = []; }
        if (att.indexOf(flat) < 0) return false;
        var r = nucleo.chiMuove(S, c, extra);
        if (!r.ok) { avviso(r.testo || "Adesso non tocca a te."); return false; }
        try { if (CANALE && typeof CANALE.mossa === "function") CANALE.mossa({ comando: flat, n: S.n }); } catch (e) { /* niente */ }
        return true;
      }
      var S2, aspettano = (S.entrano || []).length;
      try { S2 = nucleo.applica(S, c, v, extra || {}); }
      catch (e) {
        // Non è il turno di chi ha toccato (15/10): un avviso sul palco, non un errore del gioco
        if (e && e.name === "MossaNonTua") { avviso(e.message); return false; }
        mostraErrore(e); return false;
      }
      aggiorna(S2);
      // «gioco anch'io» a partita cominciata, in un gioco che non sa far entrare nessuno a metà
      if ((S.entrano || []).length > aspettano) avviso("Si gioca in più dalla prossima partita.");
      return true;
    }
    function rifiuta(m, motivo) {
      try { if (CANALE && typeof CANALE.rifiutato === "function") CANALE.rifiutato({ comando: m && m.comando, motivo: motivo, n: m && m.n }); }
      catch (e) { /* niente */ }
    }
    if (CANALE && typeof CANALE.quandoComando === "function") {
      CANALE.quandoComando(function (m) {
        var p = m && nucleo.daPiatto(m.comando);
        if (!p) { rifiuta(m, "sconosciuto"); return; }
        // Un comando riconosciuto su un'istantanea che nel frattempo è cambiata (un tocco
        // arrivato prima, l'esito che è andato avanti da solo): «vecchio», si rifiuta e si dice
        // a Calliope (14/10, passo 2: ogni comando a voce porta il numero dell'istantanea)
        if (typeof m.n === "number" && m.n !== S.n) { rifiuta(m, "vecchio"); return; }
        var att;
        try { att = nucleo.piatti(nucleo.attivi(S)); } catch (e) { rifiuta(m, "non_attivo"); return; }
        if (att.indexOf(String(m.comando)) < 0) { rifiuta(m, "non_attivo"); return; }
        // Chi l'ha mandata (15/10): lo schermo da cui arriva (se non è questo, lo dice il
        // server) e la voce riconosciuta (un segno opaco). Una mossa per il giocatore di un
        // altro schermo o di un'altra voce si rifiuta e si dice a Calliope
        var extra = { giocatore: m.giocatore || null, schermo: m.schermo || mioPosto, voce: m.voce || null };
        var r = nucleo.chiMuove(S, p[0], extra);
        if (!r.ok) { rifiuta(m, r.motivo); return; }
        mossa(p[0], p[1], extra);
      });
    }
    // La finestra che cambia: la scala sempre, il disegno se cambia l'orientamento
    if (typeof G.addEventListener === "function") {
      G.addEventListener("resize", function () {
        if (!palco) return;
        if (orientamentoAdesso() !== orientamento) aggiorna(S); else scala();
      });
    }
    var partita = {
      istantanea: function () { return nucleo.istantanea(S); },
      mossa: function (c, v) { return mossa(c, v === undefined ? null : v, {}); },
      errore: function () { return ultimoErrore; },
      // I difetti del palco della pagina di adesso, nei due orientamenti
      palco: function () {
        var pag = nucleo.pagina(S), out = [];
        (pag.orientamento ? [pag.orientamento] : ["orizzontale", "verticale"]).forEach(function (O) { difettiPalco(pag, O).forEach(function (t) { out.push(t); }); });
        return out;
      },
    };
    G.CalliopeMotore.partita = partita;
    if (CANALE && typeof CANALE.quandoPartita === "function") {
      // Uno specchio disegna lo stato che manda il motore che tiene la partita
      CANALE.quandoPartita(function (d) {
        if (ruolo !== "specchio" || !d || !d.stato) return;
        var S2;
        try { S2 = nucleo.riprendi(d.stato); } catch (e) { return; }
        aggiorna(S2);
      });
      // La partita passa a questo schermo (chi la teneva si è chiuso): riparte dall'ultimo stato
      CANALE.quandoAutorevole(function (d) {
        ruolo = "autorevole";
        if (d && d.stato) { try { S = nucleo.riprendi(d.stato); } catch (e) { /* resta com'è */ } }
        aggiorna(S);
      });
      // La partita la tiene un altro schermo (questa pagina taceva): si torna specchio
      if (typeof CANALE.quandoSpecchio === "function") {
        CANALE.quandoSpecchio(function (d) {
          ruolo = "specchio";
          if (timerEsito) { clearTimeout(timerEsito); timerEsito = null; }
          if (d && d.stato) { try { S = nucleo.riprendi(d.stato); } catch (e) { /* resta com'è */ } }
          aggiorna(S);
        });
      }
      // Un nome scritto su uno specchio
      CANALE.quandoNome(function (d) {
        if (ruolo !== "autorevole" || !d) return;
        var S2;
        try { S2 = nucleo.rinomina(S, d.i, d.nome); } catch (e) { return; }
        aggiorna(S2);
      });
    }
    if (cal && typeof cal.quandoPronto === "function") {
      cal.quandoPronto(function (avvio) {
        // il numero dello schermo conta solo in una partita tra più schermi
        var k = avvio && avvio.condivisa ? avvio.giocatore : null;
        mioPosto = typeof k === "number" && k >= 1 && k <= 99 && Math.floor(k) === k ? k : null;
        avvioTocco = !!(avvio && avvio.tocco === true);
        if (avvio && avvio.ruolo === "specchio") {
          // Uno schermo che si unisce a una partita condivisa: disegna lo stato di chi la tiene
          ruolo = "specchio";
          if (avvio.stato) { try { S = nucleo.riprendi(avvio.stato); } catch (e) { /* la preparazione */ } }
          aggiorna(S);
          return;
        }
        // «Riapri» o la pagina ricaricata: la partita riparte dall'ultima istantanea valida
        var R = avvio && avvio.ripresa;
        if (R) {
          try { S = nucleo.riprendi(R); }
          catch (e) { S = nucleo.nuovo(); if (typeof console !== "undefined") console.warn("ripresa non valida: " + e.message); }
        }
        aggiorna(S);
      });
    } else aggiorna(S);
    return partita;
  }

  var api = { crea: crea, avvia: avvia, normalizza: normalizza, piatto: piatto, partita: null,
              impagina: impagina, controllaPalco: controllaPalco, difettiPalco: difettiPalco,
              difettiInParole: difettiInParole, PALCHI: PALCHI, MODELLI: MODELLI };
  Object.defineProperty(G, "CalliopeMotore", { value: api, writable: false, configurable: false });
})(typeof window !== "undefined" ? window : globalThis);
