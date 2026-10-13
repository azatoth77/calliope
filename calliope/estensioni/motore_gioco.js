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
(function (G) {
  "use strict";
  var STANDARD = { preparazione: 1, esito: 1, fine: 1 };
  var CHIAVI_MOSSA = ["dati", "punti", "esito", "fase", "dopo", "ancora"];
  var CHIAVI_VISTA = ["titolo", "sottotitolo", "testo"];
  var ETICHETTE = { inizia: "Inizia", avanti: "Avanti", ancora: "Ancora", fine_partita: "Fine partita" };

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
      out.fasi[nome] = { pagina: f.pagina || "scelte", turni: f.turni !== false, verso: (f.verso || []).slice(), comandi: comandi };
    });
    if (!out.inizio) out.inizio = Object.keys(out.fasi)[0];
    return out;
  }

  function piatto(nome, v) { return v === null || v === undefined ? nome : nome + "_" + v; }

  // ── il nucleo: funzioni pure sullo stato (S), senza DOM. Lo usano il riquadro e la prova di
  // fumo per fasi (l'esploratore di fumo_js.mjs) ──
  function crea(GIOCO, Mgrezza, giocatori) {
    if (!GIOCO || typeof GIOCO !== "object" || typeof GIOCO.nuovaPartita !== "function") {
      throw errore("logica.js deve dichiarare const GIOCO = { nuovaPartita(…), mosse: { fase: { comando(…) } }, … } (la macchina a stati di Calliope)");
    }
    var M = normalizza(Mgrezza, giocatori);
    if (!M.fasi[M.inizio]) throw errore("la macchina non ha la fase d'inizio «" + M.inizio + "»");

    function nuovo() {
      return { n: 0, fase: "preparazione", numero: M.gmin, giocatori: [], tocca: 0, turno: 0,
               dati: null, esito: null, dopo: null, passa: false };
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
        out.inizia = true;
        return out;
      }
      if (S.fase === "esito") return { avanti: true };
      if (S.fase === "fine") return { ancora: true };
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
      return out;
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
      if (s === "inizia" || s === "avanti" || s === "ancora" || s === "fine_partita") return [s, null];
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
    function avviaPartita(S, numero) {
      var nomi = [];
      for (var i = 1; i <= numero; i++) nomi.push("Giocatore " + i);
      var dati = GIOCO.nuovaPartita({ giocatori: numero, nomi: nomi.slice() });
      if (dati === undefined || dati === null || typeof dati !== "object") {
        throw errore("GIOCO.nuovaPartita restituisce " + tipo(dati) + ": deve restituire i dati della partita (un oggetto)");
      }
      S.numero = numero;
      S.giocatori = nomi.map(function (n) { return { nome: n, punti: 0 }; });
      S.tocca = 0; S.turno = 1; S.dati = copia(dati, "GIOCO.nuovaPartita");
      S.esito = null; S.dopo = null; S.passa = false;
      S.fase = M.inizio;
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
    }
    // Applica un comando: lo stato nuovo (S non cambia). Un errore della logica o della forma
    // lancia, con fase e comando nel messaggio
    function applica(S0, c, v, extra) {
      if (v === undefined) v = null;
      var att = attivi(S0);
      if (!attivo(att, c, v)) {
        throw errore("il comando «" + piatto(c, v) + "» adesso non vale (fase «" + S0.fase + "», attivi: " + (piatti(att).join(", ") || "nessuno") + ")");
      }
      var S = copia(S0, "stato");
      S.n = S0.n + 1;
      if (S0.fase === "preparazione") { avviaPartita(S, c === "giocatori" ? v : S0.numero); return S; }
      if (S0.fase === "esito") {
        S.fase = S0.dopo || M.inizio;
        if (S0.passa) avanzaTurno(S);
        S.esito = null; S.dopo = null; S.passa = false;
        return S;
      }
      if (S0.fase === "fine") { avviaPartita(S, S0.numero); return S; }
      if (c === "fine_partita") { S.fase = "fine"; return S; }
      var fn = GIOCO.mosse && GIOCO.mosse[S0.fase] && GIOCO.mosse[S0.fase][c];
      var dove = "GIOCO.mosse." + S0.fase + "." + c + (v === null ? "" : " (valore " + JSON.stringify(v) + ")");
      if (typeof fn !== "function") throw errore("manca GIOCO.mosse." + S0.fase + "." + c + "(dati, { valore, chi }): la funzione della mossa");
      var ctx = contesto(S0);
      ctx.valore = v;
      ctx.giocatore = extra && extra.giocatore || null;
      var ris = fn(copia(S0.dati, "dati"), ctx);
      return risultato(S0, S, ris, dove);
    }
    // L'uscita da una fase «tela» (il gioco libero): come il risultato di una mossa
    function esciTela(S0, ris) {
      var f = M.fasi[S0.fase];
      if (!f || f.pagina !== "tela") throw errore("tela.esci fuori da una fase «tela» (fase «" + S0.fase + "»)");
      var S = copia(S0, "stato");
      S.n = S0.n + 1;
      return risultato(S0, S, ris, "tela.esci nella fase «" + S0.fase + "»");
    }
    function risultato(S0, S, ris, dove) {
      var chi = S0.giocatori[S0.tocca] ? S0.giocatori[S0.tocca].nome : null;
      controlla(ris, dove, S0);
      S.dati = copia(ris.dati, dove + ", dati");
      var guadagno = 0;
      if (Array.isArray(ris.punti)) ris.punti.forEach(function (p, i) { S.giocatori[i].punti += p; });
      else if (typeof ris.punti === "number" && S.giocatori[S0.tocca]) { S.giocatori[S0.tocca].punti += ris.punti; guadagno = ris.punti; }
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
    function vista(S) {
      var fn = GIOCO.vista && GIOCO.vista[S.fase];
      if (typeof fn !== "function") return {};
      var v = fn(copia(S.dati, "vista"), contesto(S));
      if (v === undefined || v === null) return {};
      if (typeof v !== "object" || Array.isArray(v)) throw errore("GIOCO.vista." + S.fase + " restituisce " + tipo(v) + ": un oggetto { titolo, sottotitolo, testo }");
      var altri = Object.keys(v).filter(function (k) { return CHIAVI_VISTA.indexOf(k) < 0; });
      if (altri.length) throw errore("GIOCO.vista." + S.fase + " restituisce campi che il motore non conosce: " + altri.join(", ") + " (solo titolo, sottotitolo, testo: il disegno è del motore)");
      var out = {};
      CHIAVI_VISTA.forEach(function (k) {
        if (v[k] === undefined || v[k] === null) return;
        if (typeof v[k] !== "string" && typeof v[k] !== "number") throw errore("GIOCO.vista." + S.fase + "." + k + " è " + tipo(v[k]) + ": un testo");
        if (typeof v[k] === "number" && !isFinite(v[k])) throw errore("GIOCO.vista." + S.fase + "." + k + " è " + v[k]);
        out[k] = String(v[k]);
      });
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
      return { n: S.n, fase: S.fase, tocca: S.giocatori[S.tocca] ? S.giocatori[S.tocca].nome : null,
               turno: S.turno, giocatori: S.giocatori.map(function (g) { return { nome: g.nome, punti: g.punti }; }),
               esito: S.esito ? S.esito.testo : null, comandi: att };
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
    return { M: M, nuovo: nuovo, attivi: attivi, piatti: piatti, daPiatto: daPiatto, applica: applica, esciTela: esciTela,
             vista: vista, istantanea: istantanea, classifica: classifica, etichetta: etichetta,
             contesto: contesto, piatto: piatto };
  }

  // ── nel riquadro (e nel DOM finto della prova): disegno, pulsanti, voce ──
  function avvia(GIOCO, conf, opzioni) {
    opzioni = opzioni || {};
    var doc = G.document;
    var radice = doc.getElementById("gioco");
    var cal = G.calliope;
    var segnala = opzioni.errore || function (e) { setTimeout(function () { throw e; }, 0); };
    var nucleo, S, timerEsito = null, ultimoErrore = "";
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
    try { nucleo = crea(GIOCO, conf && conf.macchina, conf && conf.giocatori); }
    catch (e) { radice.replaceChildren(el("div", "motore")); mostraErrore(e); return null; }
    S = nucleo.nuovo();
    function pulsante(c, v) {
      var b = el("button", "comando", nucleo.etichetta(S.fase, c, v));
      b.type = "button";
      b.dataset.comando = c;
      if (v !== null && v !== undefined) b.dataset.valore = String(v);
      b.addEventListener("click", function () { mossa(c, v === undefined ? null : v, {}); });
      return b;
    }
    function punti(box) {
      if (!S.giocatori.length) return;
      var p = el("div", "punti");
      S.giocatori.forEach(function (g, i) {
        var s = el("span", "giocatore" + (i === S.tocca && S.fase !== "fine" && S.giocatori.length > 1 ? " tocca" : ""), g.nome + ": " + g.punti);
        p.appendChild(s);
      });
      box.appendChild(p);
    }
    function disegna() {
      var box = el("div", "motore fase-" + S.fase);
      var att = nucleo.attivi(S);
      var v = nucleo.vista(S);
      var titolo = v.titolo;
      if (S.fase === "preparazione") titolo = titolo || opzioni.titolo || "Nuova partita";
      if (S.fase === "esito" && !titolo && S.esito) titolo = S.esito.testo;
      if (S.fase === "fine") titolo = titolo || "Partita finita";
      if (titolo) box.appendChild(el("h1", "titolo", titolo));
      if (v.sottotitolo) box.appendChild(el("p", "sottotitolo", v.sottotitolo));
      else if (S.giocatori.length > 1 && M().fasi[S.fase] && M().fasi[S.fase].turni) box.appendChild(el("p", "sottotitolo", "Tocca a " + S.giocatori[S.tocca].nome));
      if (S.fase === "preparazione" && !v.testo && M().gmin < M().gmax) box.appendChild(el("p", "testo", "Quanti giocatori?"));
      if (S.fase === "esito" && S.esito && S.esito.punti) box.appendChild(el("p", "testo", (S.esito.punti > 0 ? "+" : "") + S.esito.punti + (Math.abs(S.esito.punti) === 1 ? " punto" : " punti") + (S.giocatori.length > 1 ? " a " + S.esito.chi : "")));
      if (v.testo) box.appendChild(el("p", "testo", v.testo));
      if (S.fase === "fine") {
        var ol = el("ol", "classifica");
        nucleo.classifica(S).forEach(function (g, i) { ol.appendChild(el("li", i === 0 ? "primo" : "", g.nome + ": " + g.punti + (g.punti === 1 ? " punto" : " punti"))); });
        box.appendChild(ol);
      }
      var f = M().fasi[S.fase];
      if (f && f.pagina === "tela") {
        var area = el("div", "tela");
        box.appendChild(area);
        tela(area);
      }
      var scelte = el("div", "scelte");
      Object.keys(att).forEach(function (c) {
        if (att[c] === true) scelte.appendChild(pulsante(c, null));
        else att[c].forEach(function (x) { scelte.appendChild(pulsante(c, x)); });
      });
      box.appendChild(scelte);
      if (S.fase !== "preparazione") punti(box);
      radice.replaceChildren(box);
      return att;
    }
    function M() { return nucleo.M; }
    function tela(area) {
      var fn = GIOCO.tela && GIOCO.tela[S.fase];
      if (typeof fn !== "function") { mostraErrore(errore("manca GIOCO.tela." + S.fase + "(area, dati, tela): la fase ha la pagina «tela»")); return; }
      var fase = S.fase, n = S.n;
      fn(area, JSON.parse(JSON.stringify(S.dati)), {
        giocatori: nucleo.contesto(S).giocatori,
        esci: function (ris) {
          if (S.fase !== fase || S.n !== n) return false;
          var S2;
          try { S2 = nucleo.esciTela(S, ris); } catch (e) { mostraErrore(e); return false; }
          aggiorna(S2);
          return true;
        },
      });
    }
    function voce(att) {
      try { cal.comandiAttivi(nucleo.piatti(att)); } catch (e) { /* senza voce si gioca toccando */ }
    }
    function aggiorna(S2) {
      S = S2;
      if (timerEsito) { clearTimeout(timerEsito); timerEsito = null; }
      var att;
      try { att = disegna(); }
      catch (e) { radice.replaceChildren(el("div", "motore")); mostraErrore(e); voce({}); return; }
      voce(att);
      if (S.fase === "esito" && M().esito_s > 0) {
        var n = S.n;
        timerEsito = setTimeout(function () { if (S.n === n && S.fase === "esito") mossa("avanti", null, {}); }, M().esito_s * 1000);
      }
      if (S.fase === "fine" && cal && typeof cal.fine === "function") {
        try { cal.fine({ classifica: nucleo.classifica(S).map(function (g) { return { nome: g.nome, punti: g.punti }; }) }); } catch (e) { /* niente */ }
      }
    }
    function mossa(c, v, extra) {
      var S2;
      try { S2 = nucleo.applica(S, c, v, extra || {}); }
      catch (e) { mostraErrore(e); return false; }
      aggiorna(S2);
      return true;
    }
    if (cal && typeof cal.quandoComando === "function") {
      cal.quandoComando(function (m) {
        var p = m && nucleo.daPiatto(m.comando);
        if (!p) return;
        // Un comando arrivato dopo un tocco che ha cambiato la fase («vecchio»): si ignora, come
        // farebbe il server con un'istantanea vecchia
        var att;
        try { att = nucleo.piatti(nucleo.attivi(S)); } catch (e) { return; }
        if (att.indexOf(String(m.comando)) < 0) return;
        mossa(p[0], p[1], { giocatore: m.giocatore || null });
      });
    }
    var partita = {
      istantanea: function () { return nucleo.istantanea(S); },
      mossa: function (c, v) { return mossa(c, v === undefined ? null : v, {}); },
      errore: function () { return ultimoErrore; },
    };
    G.CalliopeMotore.partita = partita;
    if (cal && typeof cal.quandoPronto === "function") cal.quandoPronto(function () { aggiorna(S); });
    else aggiorna(S);
    return partita;
  }

  var api = { crea: crea, avvia: avvia, normalizza: normalizza, piatto: piatto, partita: null };
  Object.defineProperty(G, "CalliopeMotore", { value: api, writable: false, configurable: false });
})(typeof window !== "undefined" ? window : globalThis);
