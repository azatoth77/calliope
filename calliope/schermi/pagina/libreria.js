// Calliope · la libreria dello Studio (31/10/2026, issue #297, epic #251, decisione 0035).
// La sezione «Dalla libreria» di ogni verifica nella home dello Studio (studio.js la chiama):
// le proposte scelte dal server (studio/libreria/, il codice, mai il modello), una scheda da
// leggere, «Aggiungi le carte». I contenuti sono nostri e fidati, ma la pagina li scrive lo stesso
// solo con textContent, mai innerHTML. Le soluzioni di «Prova tu» non arrivano con la scheda: il
// server le dà una per volta a «Mostra la soluzione» (POST /api/studio/libreria).
"use strict";

(function () {
  const sch = () => window.calliopeSchermo;
  // Lo stato di una scheda aperta (una sola alla volta) e delle richieste: ogni risposta porta il
  // numero della sua richiesta, e una risposta vecchia (un'altra scheda aperta nel frattempo) si
  // butta (niente corse)
  // lib: {vid, scheda, dati, soluzioni: {n: testo}, attesa, esito, esitoDi, richiesta}
  let lib = { vid: null, scheda: null, dati: null, soluzioni: {}, attesa: false, esito: "",
    esitoDi: null, richiesta: 0, lezione: null };
  // Le funzioni della home (studio.js): ridisegna, ricarica, vista
  let ctx = { ridisegna() {}, ricarica() {}, vista() {}, tocchi: false };

  const TIPI = { scheda: "Scheda", mazzo: "Carte", miniapp: "Attività" };
  const MOTIVI = { lacuna: "da rinforzare", prerequisito: "per ripartire da prima" };
  // Le mini-app (parte 2 della #297): il tipo detto in parole
  const TIPI_APP = { esplora: "da esplorare", quiz: "con il quiz", percorso: "percorso guidato" };
  // «Apri» su un'attività: un tocco vero (studio_attivita, il bersaglio lo sceglie il server), che
  // studio.js manda come gli altri tocchi della home (data-tocco); l'esito arriva dal ciclo
  function tastoAttivita(vid, id, titolo, cls) {
    const b = nodo("button", "tasto studio-h-tasto" + (cls ? " " + cls : ""), "Apri");
    b.type = "button";
    b.dataset.tocco = "studio_attivita";
    b.dataset.dati = JSON.stringify({ verifica: vid, contenuto: id });
    b.setAttribute("aria-label", "Apri l'attività «" + String(titolo || "") + "»");
    b.disabled = !ctx.tocchi;
    return b;
  }

  function nodo(tag, cls, testo) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (testo !== undefined && testo !== null) el.textContent = String(testo);
    return el;
  }
  function tasto(testo, azione, dati, cls, etichetta) {
    const b = nodo("button", "tasto studio-h-tasto" + (cls ? " " + cls : ""), testo);
    b.type = "button";
    b.dataset.libreria = azione;
    b.dataset.dati = JSON.stringify(dati || {});
    if (etichetta) b.setAttribute("aria-label", etichetta);
    b.disabled = !!lib.attesa;
    return b;
  }

  function infoProposta(p) {
    const pezzi = [TIPI[p.tipo] || "Contenuto"];
    if (p.tipo === "miniapp" && TIPI_APP[p.tipo_app]) pezzi.push(TIPI_APP[p.tipo_app]);
    if (p.tipo === "mazzo") pezzi.push((Number(p.carte) || 0) + " carte");
    else pezzi.push((Number(p.durata) || 0) + " min");
    pezzi.push(p.numero ? "argomento " + Number(p.numero) : "argomento della verifica");
    if (MOTIVI[p.motivo]) pezzi.push(MOTIVI[p.motivo]);
    if (p.tipo === "mazzo" && p.aggiunto) pezzi.push("già fra le carte");
    else if (p.tipo === "mazzo" && Number(p.aggiunte)) pezzi.push(Number(p.aggiunte) + " già fra le carte");
    return pezzi.join(" · ");
  }

  // La sezione di una verifica: v.libreria è l'elenco del server (null: spenta, in ombra o con
  // una prova aperta, e allora la sezione non c'è)
  function sezione(v, funzioni) {
    if (funzioni) ctx = Object.assign(ctx, funzioni);
    const sez = nodo("section", "studio-h-gruppo studio-l");
    sez.dataset.verifica = String(v.id);
    sez.append(nodo("h4", "studio-h-sotto", "Dalla libreria"));
    const prop = Array.isArray(v.libreria) ? v.libreria : [];
    if (!prop.length) {
      sez.append(nodo("p", "studio-h-riga", "Nella libreria non c'è niente per questi argomenti."));
    } else {
      const ul = nodo("ul", "studio-h-elenco studio-l-elenco");
      for (const p of prop) {
        const li = nodo("li", "studio-h-voce studio-l-voce");
        li.dataset.contenuto = String(p.contenuto || "");
        const tx = nodo("div", "studio-testo");
        tx.append(nodo("b", null, String(p.titolo || "")), nodo("span", "studio-nota", infoProposta(p)));
        const t = nodo("div", "studio-tasti");
        const nome = "«" + String(p.titolo || "") + "»";
        if (p.tipo === "scheda") {
          const aperta = lib.vid === v.id && lib.scheda === p.contenuto;
          t.append(tasto(aperta ? "Chiudi" : "Apri", aperta ? "chiudi" : "apri", { scheda: p.contenuto },
            aperta ? "" : "studio-h-primo", (aperta ? "Chiudi " : "Apri ") + nome));
        } else if (p.tipo === "miniapp") {
          t.append(tastoAttivita(v.id, p.contenuto, p.titolo));
        } else if (p.tipo === "mazzo" && !p.aggiunto) {
          t.append(tasto("Aggiungi le carte", "carte", { mazzo: p.contenuto, argomento: p.argomento },
            "", "Aggiungi le carte " + nome));
        }
        li.append(tx);
        if (t.childNodes.length) li.append(t);
        ul.append(li);
      }
      sez.append(ul);
    }
    // La preparazione dietro le quinte (#297, parte 3): «in preparazione» o «pronto», con le
    // lezioni dalle pagine (testo del modello: textContent) e le attività adattate ai materiali
    const pr = v.preparazione;
    if (pr && pr.stato === "in_preparazione") {
      sez.append(nodo("p", "studio-h-riga studio-l-prep", "In preparazione: una lezione dalle tue pagine e gli esempi per le attività. La trovi qui quando è pronta."));
    } else if (pr && pr.stato === "pronta") {
      const box = nodo("div", "studio-l-prep");
      box.append(nodo("p", "studio-h-riga", "Pronto dalle tue pagine" +
        (Array.isArray(pr.attivita) && pr.attivita.length ? ": anche " + pr.attivita.map((x) => "«" + String(x) + "»").join(", ") + " con i loro esempi." : ".")));
      const t = nodo("div", "studio-h-tasti");
      for (const a of Array.isArray(pr.argomenti) ? pr.argomenti : []) {
        const aperta = lib.lezione && lib.lezione.vid === v.id && lib.lezione.aid === a.id;
        t.append(tasto((aperta ? "Chiudi la lezione " : "Lezione dell'argomento ") + (Number(a.numero) || ""),
          aperta ? "lezione_chiudi" : "lezione", { argomento: a.id }));
      }
      if (t.childNodes.length) box.append(t);
      if (lib.lezione && lib.lezione.vid === v.id && lib.lezione.dati) {
        const art = nodo("article", "studio-l-scheda studio-l-lezione");
        art.append(nodo("h4", "studio-l-nome", "Lezione dell'argomento " + (Number(lib.lezione.dati.numero) || "")),
          nodo("p", "studio-nota", "Preparata dalle tue pagine: controllala sul libro."));
        for (const x of Array.isArray(lib.lezione.dati.paragrafi) ? lib.lezione.dati.paragrafi : []) {
          art.append(nodo("p", "studio-l-testo", String(x)));
        }
        box.append(art);
      }
      sez.append(box);
    }
    if (lib.vid === v.id && lib.scheda) sez.append(pannello(v));
    if (lib.esitoDi === v.id && lib.esito) {
      const es = nodo("p", "pagina-esito studio-l-esito", lib.esito);
      es.setAttribute("role", "status");
      sez.append(es);
    }
    return sez;
  }

  // Il testo di una sezione può avere più paragrafi, separati da una riga vuota
  function paragrafi(testo) {
    return String(testo || "").split(/\n\s*\n/).map((x) => x.trim()).filter(Boolean)
      .map((x) => nodo("p", "studio-l-testo", x));
  }
  function elenco(titolo, righe, cls) {
    const out = [];
    if (!righe.length) return out;
    out.push(nodo("h5", "studio-l-titoletto", titolo));
    const ul = nodo("ul", "studio-l-righe" + (cls ? " " + cls : ""));
    for (const r of righe) ul.append(nodo("li", null, String(r)));
    out.push(ul);
    return out;
  }

  function pannello(v) {
    const box = nodo("article", "studio-l-scheda");
    const d = lib.dati;
    if (!d) { box.append(nodo("p", "pagina-nota", "Un attimo…")); return box; }
    box.setAttribute("aria-label", "Scheda " + String(d.titolo || ""));
    box.append(nodo("h4", "studio-l-nome", String(d.titolo || "")),
      nodo("p", "studio-nota", [String(d.materia || ""), (Number(d.durata) || 0) + " minuti"].join(" · ")),
      ...paragrafi(d.introduzione));
    for (const s of Array.isArray(d.sezioni) ? d.sezioni : []) {
      box.append(nodo("h5", "studio-l-titoletto", String(s.titolo || "")), ...paragrafi(s.testo));
    }
    box.append(...elenco("Da ricordare", Array.isArray(d.ricorda) ? d.ricorda : [], "studio-l-ricorda"));
    box.append(...elenco("Esempi", Array.isArray(d.esempi) ? d.esempi : []));
    box.append(...elenco("Errori tipici", Array.isArray(d.errori) ? d.errori : []));
    const pt = Array.isArray(d.prova_tu) ? d.prova_tu : [];
    if (pt.length) {
      box.append(nodo("h5", "studio-l-titoletto", "Prova tu"));
      const ol = nodo("ol", "studio-l-prova");
      for (const q of pt) {
        const li = nodo("li", "studio-l-domanda");
        li.append(nodo("p", "studio-l-testo", String(q.domanda || "")));
        const sol = lib.soluzioni[q.n];
        if (sol !== undefined) li.append(nodo("p", "studio-l-soluzione", String(sol)));
        else li.append(tasto("Mostra la soluzione", "soluzione", { n: q.n }, "", "Mostra la soluzione della domanda " + q.n));
        ol.append(li);
      }
      box.append(ol);
    }
    const pre = Array.isArray(d.prerequisiti) ? d.prerequisiti : [];
    if (pre.length) {
      box.append(nodo("h5", "studio-l-titoletto", "Prima di questa"));
      const t = nodo("div", "studio-h-tasti");
      for (const p of pre) t.append(tasto(String(p.titolo || ""), "apri", { scheda: p.id }, "", "Apri la scheda «" + String(p.titolo || "") + "»"));
      box.append(t);
    }
    const app = Array.isArray(d.attivita) ? d.attivita : [];
    if (app.length) {
      box.append(nodo("h5", "studio-l-titoletto", "Attività"));
      const ul = nodo("ul", "studio-h-elenco studio-l-elenco");
      for (const a of app) {
        const li = nodo("li", "studio-h-voce studio-l-voce");
        const tx = nodo("div", "studio-testo");
        tx.append(nodo("b", null, String(a.titolo || "")),
          nodo("span", "studio-nota", [TIPI_APP[a.tipo_app] || "", (Number(a.durata) || 0) + " min"].filter(Boolean).join(" · ")));
        const tt = nodo("div", "studio-tasti");
        tt.append(tastoAttivita(v.id, a.id, a.titolo, "studio-h-primo"));
        li.append(tx, tt);
        ul.append(li);
      }
      box.append(ul);
    }
    const t = nodo("div", "studio-h-tasti");
    for (const m of Array.isArray(d.mazzi) ? d.mazzi : []) {
      const gia = (Array.isArray(v.libreria) ? v.libreria : []).find((p) => p.contenuto === m.id);
      if (!gia || !gia.aggiunto) t.append(tasto("Aggiungi le carte", "carte", { mazzo: m.id, argomento: gia ? gia.argomento : null }, "studio-h-primo"));
    }
    t.append(tasto("Chiudi la scheda", "chiudi", {}));
    box.append(t);
    return box;
  }

  async function chiedi(vid, dati) {
    const n = ++lib.richiesta;
    lib.attesa = true;
    ctx.ridisegna();
    const r = await sch().studioLibreria(Object.assign({ verifica: vid }, dati));
    if (n !== lib.richiesta) return null;              // una risposta vecchia: si butta
    lib.attesa = false;
    if (!r.ok) {
      lib.esito = String(r.dati.errore || "Non ci sono riuscita: riprova tra poco.");
      lib.esitoDi = vid;
      ctx.ridisegna();
      return null;
    }
    return r.dati;
  }

  async function su(b) {
    if (!sch() || !sch().studioLibreria) return;
    const art = b.closest("[data-verifica]");
    const vid = Number(art && art.dataset.verifica);
    let dati = {};
    try { dati = JSON.parse(b.dataset.dati || "{}"); } catch (e) { return; }
    const az = b.dataset.libreria;
    lib.esito = "";
    if (az === "chiudi") {
      lib = Object.assign(lib, { vid: null, scheda: null, dati: null, soluzioni: {}, attesa: false });
      lib.richiesta++;
      ctx.vista({ vista: "home" });
      ctx.ridisegna();
      return;
    }
    if (az === "apri") {
      Object.assign(lib, { vid, scheda: String(dati.scheda || ""), dati: null, soluzioni: {} });
      ctx.vista({ vista: "libreria", verifica: vid });
      const r = await chiedi(vid, { azione: "scheda", contenuto: lib.scheda });
      if (r && r.scheda && r.scheda.id === lib.scheda) lib.dati = r.scheda;
      else if (!r) { lib.scheda = null; }
      ctx.ridisegna();
      return;
    }
    if (az === "lezione") {
      const aid = Number(dati.argomento);
      lib.lezione = { vid, aid, dati: null };
      const r = await chiedi(vid, { azione: "lezione", argomento: aid });
      if (r && r.lezione && lib.lezione && lib.lezione.aid === r.lezione.argomento) lib.lezione.dati = r.lezione;
      else if (!r) lib.lezione = null;
      ctx.ridisegna();
      return;
    }
    if (az === "lezione_chiudi") { lib.lezione = null; lib.richiesta++; ctx.ridisegna(); return; }
    if (az === "soluzione") {
      const sid = lib.scheda;
      const r = await chiedi(vid, { azione: "soluzione", contenuto: sid, n: Number(dati.n) });
      if (r && r.soluzione && lib.scheda === sid && r.soluzione.scheda === sid) {
        lib.soluzioni[r.soluzione.n] = r.soluzione.risposta;
      }
      ctx.ridisegna();
      return;
    }
    if (az === "carte") {
      const r = await chiedi(vid, { azione: "carte", contenuto: String(dati.mazzo || ""),
        argomento: Number.isInteger(dati.argomento) ? dati.argomento : null });
      if (!r) return;
      const a = r.aggiunte || {};
      const n = Number(a.aggiunte) || 0, g = Number(a.gia) || 0, f = Number(a.fuori) || 0;
      lib.esito = (n === 1 ? "Una carta aggiunta" : n + " carte aggiunte") + ": sono fra quelle da ripassare." +
        (g ? " " + (g === 1 ? "Una c'era già." : g + " c'erano già.") : "") +
        (f ? " " + f + " non ci stanno: le carte della verifica sono al massimo." : "");
      lib.esitoDi = vid;
      ctx.ricarica();
    }
  }

  function chiudi() {
    lib = { vid: null, scheda: null, dati: null, soluzioni: {}, attesa: false, esito: "", esitoDi: null,
      richiesta: lib.richiesta + 1, lezione: null };
  }

  window.CalliopeLibreria = { sezione, su, chiudi };
})();
