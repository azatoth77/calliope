// Calliope · lo Studio: «Aggiungi materiali», l'importazione dei materiali scaricati (31/10/2026,
// issue #298, epic #251, decisione 0035). Sulla carta di una verifica della home dello Studio
// (studio.js la mette con window.CalliopeImporta.sezione), sul telefono e sul PC personale: si
// scelgono uno o più file (PDF, foto, Word, PowerPoint, Excel, OpenDocument, testo, Markdown, CSV,
// HTML o un archivio ZIP), partono uno alla volta (POST /api/studio/importa) e ognuno diventa
// un'importazione che il server lavora in sottofondo. La scheda mostra le fasi e i conti e si
// aggiorna ogni 2 s finché un'importazione è viva (POST /api/studio/importazioni), con «Ferma»,
// «Riprendi» e «Togli». I nomi dei file e i motivi arrivano dal server come dati: sempre
// textContent, mai innerHTML.
"use strict";

(function () {
  const sch = () => window.calliopeSchermo;
  const OGNI_MS = 2000;
  const ACCETTA = ".pdf,.jpg,.jpeg,.png,.webp,.docx,.pptx,.xlsx,.odt,.odp,.ods,.txt,.md,.csv,.html,.htm,.zip," +
    "application/pdf,image/jpeg,image/png,image/webp,application/zip,text/plain,text/markdown,text/csv,text/html";
  const FASI = { ricevuto: "Ricevuto", estratto: "Estratto", letto: "Pagine e testo letti",
    argomenti: "Argomenti trovati", preparato: "Carte e domande preparate" };
  const STATI_FASE = { fatta: "fatto", in_corso: "in corso", in_attesa: "da fare", ferma: "fermo", spenta: "spento" };
  const STATI = { in_coda: "in coda", in_corso: "in corso", fermata: "fermata", finita: "finita", errore: "non riuscita" };
  const AVVISI = { macro: "macro non eseguite", testo_nascosto: "con testo nascosto", tagliato: "tagliato",
    sfocata: "forse sfocata", piccola: "piccola", bordi: "bordi non trovati" };

  // Per verifica: {aperta, dati, esito, invio, timer}
  const st = {};
  function di(vid) { return st[vid] || (st[vid] = { aperta: false, dati: null, esito: "", invio: false, timer: null }); }

  function nodo(tag, cls, testo) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (testo !== undefined && testo !== null) n.textContent = String(testo);
    return n;
  }
  function tasto(testo, azione, extra, cls, etichetta) {
    const b = nodo("button", "tasto studio-h-tasto" + (cls ? " " + cls : ""), testo);
    b.type = "button";
    b.dataset.importa = azione;
    if (extra !== undefined && extra !== null) b.dataset.id = String(extra);
    if (etichetta) b.setAttribute("aria-label", etichetta);
    return b;
  }
  function nn(n, uno, tanti) { n = Number(n) || 0; return n + " " + (n === 1 ? uno : tanti); }

  function conti(x) {
    const c = x.conti || {};
    const pezzi = [nn(c.file, "file", "file")];
    if (Number(c.pagine)) pezzi.push(nn(c.pagine, "pagina", "pagine") + " (" + (Number(c.pagine_lette) || 0) + " lette)");
    if (c.argomenti !== null && c.argomenti !== undefined) pezzi.push(nn(c.argomenti, "argomento", "argomenti"));
    let t = pezzi.join(", ");
    if (Number(c.non_letti)) t += "; " + nn(c.non_letti, "non letto", "non letti");
    if (x.stato === "in_corso" && Number(x.voci)) t += " · al file " + Math.min(Number(x.voci), (Number(x.prossima) || 0) + 1) + " di " + Number(x.voci);
    return t;
  }

  function scheda(vid, x) {
    const li = nodo("li", "studio-h-voce studio-i-voce studio-i-" + String(x.stato || ""));
    li.dataset.importazione = String(x.id);
    const tx = nodo("div", "studio-testo");
    tx.append(nodo("b", "studio-i-nome", String(x.nome || "file")),
      nodo("span", "studio-h-riga", STATI[x.stato] || String(x.stato || "")));
    if (x.motivo) tx.append(nodo("span", "studio-avviso", String(x.motivo)));
    const ol = nodo("ol", "studio-i-fasi");
    ol.setAttribute("aria-label", "Fasi");
    for (const f of Array.isArray(x.fasi) ? x.fasi : []) {
      const s = String(f.stato || "");
      const fi = nodo("li", "studio-i-fase studio-i-f-" + s);
      fi.append(nodo("span", "studio-i-segno", s === "fatta" ? "✓" : s === "in_corso" ? "…" : ""),
        nodo("span", null, (FASI[f.fase] || String(f.fase)) + ": " + (STATI_FASE[s] || s)));
      fi.firstChild.setAttribute("aria-hidden", "true");
      ol.append(fi);
    }
    tx.append(ol, nodo("p", "studio-h-riga studio-i-conti", conti(x)));
    const righe = Array.isArray(x.righe) ? x.righe : [];
    if (righe.length) {
      const det = nodo("details", "studio-i-righe");
      const non = righe.filter((r) => r.esito !== "ok").length;
      det.append(nodo("summary", null, "I file" + (non ? " (" + nn(non, "non letto", "non letti") + ")" : "")));
      const ul = nodo("ul", "studio-h-elenco");
      for (const r of righe) {
        const ri = nodo("li", "studio-i-riga");
        ri.append(nodo("span", "studio-i-nome", String(r.nome || "file")));
        if (r.esito === "ok") {
          const av = (Array.isArray(r.avvisi) ? r.avvisi : []).map((a) => AVVISI[a] || String(a));
          ri.append(nodo("span", "studio-h-riga", " · " + nn(r.pagine, "pagina", "pagine") +
            (r.materiale ? " · materiale " + Number(r.materiale) : "") + (av.length ? " · " + av.join(", ") : "")));
        } else ri.append(nodo("span", "studio-avviso", " · non letto: " + String(r.motivo || "")));
        ul.append(ri);
      }
      if (Number(x.righe_altre)) ul.append(nodo("li", "studio-h-riga", "… e altri " + Number(x.righe_altre)));
      det.append(ul);
      tx.append(det);
    }
    const t = nodo("div", "studio-h-tasti");
    const puo = x.puo || {};
    const chi = "l'importazione di " + String(x.nome || "file");
    if (puo.ferma) t.append(tasto("Ferma", "ferma", x.id, "", "Ferma " + chi));
    if (puo.riprendi) t.append(tasto("Riprendi", "riprendi", x.id, "studio-h-primo", "Riprendi " + chi));
    // Toglie la riga (e il file arrivato, se c'è ancora); le pagine già fatte restano nella verifica
    if (puo.togli) t.append(tasto(x.stato === "finita" || x.stato === "errore" ? "Togli dall'elenco" : "Annulla",
      "togli", x.id, "", (x.stato === "finita" || x.stato === "errore" ? "Togli dall'elenco " : "Annulla ") + chi));
    li.append(tx, t);
    return li;
  }

  function sezione(v) {
    const vid = Number(v.id);
    const s = di(vid);
    const sez = nodo("section", "studio-h-gruppo studio-i");
    sez.dataset.verifica = String(vid);
    sez.dataset.importaVerifica = String(vid);
    sez.append(nodo("h4", "studio-h-sotto", "Aggiungi materiali"));
    if (!s.aperta) {
      sez.append(nodo("p", "studio-h-riga", "File scaricati dalla scuola: PDF, foto, Word, PowerPoint, Excel, testo o un archivio ZIP."));
      const t = nodo("div", "studio-h-tasti");
      t.append(tasto("Aggiungi materiali", "apri", null, "", "Aggiungi materiali a questa verifica"));
      sez.append(t);
      return sez;
    }
    const d = s.dati || {};
    const mb = Number(d.max_mb) || 100;
    sez.append(nodo("p", "studio-h-riga", "Scegli uno o più file, al più " + mb + " MB ciascuno: PDF, foto (JPEG, PNG, WebP), " +
      "Word, PowerPoint, Excel, OpenDocument, testo, Markdown, CSV, HTML o un archivio ZIP. Li preparo io in sottofondo; " +
      "puoi chiudere e tornare dopo."));
    const id = "studio-i-file-" + vid;
    // Un tasto vero (col fuoco e la tastiera) che apre il selettore dei file nascosto
    const scegli = tasto(s.invio ? "Sto mandando…" : "Scegli i file", "scegli", null, "studio-h-primo",
      "Scegli i file da aggiungere");
    scegli.disabled = s.invio;
    const inp = nodo("input", "studio-i-file");
    inp.type = "file";
    inp.id = id;
    inp.multiple = true;
    inp.accept = ACCETTA;
    inp.hidden = true;
    inp.tabIndex = -1;
    inp.dataset.importaFile = String(vid);
    const t = nodo("div", "studio-h-tasti");
    t.append(scegli, inp, tasto("Chiudi", "chiudi", null, "", "Chiudi «Aggiungi materiali»"));
    sez.append(t);
    if (s.esito) {
      const es = nodo("p", "pagina-esito studio-i-esito", s.esito);
      es.setAttribute("role", "status");
      sez.append(es);
    }
    const lista = Array.isArray(d.importazioni) ? d.importazioni : [];
    if (lista.length) {
      const ul = nodo("ul", "studio-h-elenco studio-i-elenco");
      for (const x of lista) ul.append(scheda(vid, x));
      sez.append(ul);
    } else if (s.dati) sez.append(nodo("p", "studio-h-riga", "Nessun materiale importato in questa verifica."));
    return sez;
  }

  // Ridisegna solo la sezione di una verifica (la home resta com'è: niente perde il fuoco altrove)
  function ridisegna(vid) {
    const vecchia = document.querySelector('section.studio-i[data-importa-verifica="' + vid + '"]');
    if (!vecchia) return false;
    const fuoco = document.activeElement && vecchia.contains(document.activeElement)
      ? [document.activeElement.dataset.importa, document.activeElement.dataset.id] : null;
    const nuova = sezione({ id: vid });
    vecchia.replaceWith(nuova);
    if (fuoco && fuoco[0]) {
      const b = nuova.querySelector('button[data-importa="' + fuoco[0] + '"]' + (fuoco[1] ? '[data-id="' + fuoco[1] + '"]' : ""));
      try { (b || nuova.querySelector("button")).focus(); } catch (e) { /* niente */ }
    }
    return true;
  }

  async function carica(vid, corpo) {
    const s = di(vid);
    clearTimeout(s.timer);
    s.timer = null;
    if (!sch() || !sch().studioImportazioni) return;
    const r = await sch().studioImportazioni(Object.assign({ verifica: vid }, corpo || {}));
    if (r.ok) s.dati = r.dati;
    else if (r.status === 429) { /* si riprova al giro dopo */ }
    else s.esito = String(r.dati.errore || "Non riesco a leggere le importazioni: riprovo.");
    if (!ridisegna(vid)) return;               // la sezione non c'è più (Studio chiuso)
    if (s.aperta && s.dati && s.dati.viva) s.timer = setTimeout(() => carica(vid), OGNI_MS);
  }

  async function manda(vid, files) {
    const s = di(vid);
    if (s.invio || !files.length) return;
    s.invio = true;
    let fatti = 0;
    const errori = [];
    try {
      const mb = Number(s.dati && s.dati.max_mb) || 100;
      for (const f of files) {
        const quale = "Mando " + (fatti + errori.length + 1) + " di " + files.length;
        // Il tetto anche qui, prima di mandare (revisione della PR #364): niente MB per un 413
        if (f.size > mb * 1000000) {
          errori.push(String(f.name || "file").slice(0, 60) + ": troppo grande (al più " + mb + " MB)");
          continue;
        }
        s.esito = quale + "…";
        ridisegna(vid);
        // L'avanzamento in byte dell'invio, sulla riga dell'esito (al più ogni 5 %)
        let ultimo = -1;
        const avanti = (mandati, tot) => {
          const pc = tot ? Math.floor((100 * mandati) / tot) : 0;
          if (pc - ultimo < 5 && pc < 100) return;
          ultimo = pc;
          s.esito = quale + ": " + pc + "%";
          const el = document.querySelector('section.studio-i[data-importa-verifica="' + vid + '"] .studio-i-esito');
          if (el) el.textContent = s.esito; else ridisegna(vid);
        };
        const r = await sch().studioImporta(f, { verifica: vid, nome: String(f.name || "file").slice(0, 120) }, avanti);
        if (r.ok) fatti++;
        else errori.push(String(f.name || "file").slice(0, 60) + ": " + String(r.dati.errore || "non mandato"));
      }
    } finally {
      s.invio = false;
    }
    s.esito = (fatti ? (fatti === 1 ? "Mandato: lo preparo in sottofondo." : "Mandati " + fatti + ": li preparo in sottofondo.") : "") +
      (errori.length ? (fatti ? " " : "") + "Non mandati: " + errori.join("; ") + "." : "");
    await carica(vid);
  }

  async function su(ev) {
    const b = ev.target.closest && ev.target.closest("button[data-importa]");
    if (!b || b.disabled) return;
    const sez = b.closest("section[data-importa-verifica]");
    const vid = Number(sez && sez.dataset.importaVerifica);
    if (!vid) return;
    const s = di(vid);
    const az = b.dataset.importa;
    if (az === "scegli") {
      // Subito, nel gesto del tocco (il browser apre il selettore solo così)
      const inp = sez.querySelector("input[data-importa-file]");
      if (inp && !s.invio) inp.click();
      return;
    }
    if (az === "apri") { s.aperta = true; s.esito = ""; ridisegna(vid); await carica(vid); return; }
    if (az === "chiudi") { s.aperta = false; clearTimeout(s.timer); s.timer = null; ridisegna(vid); return; }
    if (az === "ferma" || az === "riprendi" || az === "togli") {
      b.disabled = true;
      s.esito = "";
      await carica(vid, { azione: az, importazione: Number(b.dataset.id) });
    }
  }
  async function suFile(ev) {
    const inp = ev.target;
    if (!inp || !inp.dataset || !inp.dataset.importaFile) return;
    const vid = Number(inp.dataset.importaFile);
    const files = [...(inp.files || [])];
    inp.value = "";
    await manda(vid, files);
  }

  function avvia() {
    const home = document.getElementById("studio-home");
    if (!home) return;
    home.addEventListener("click", su);
    home.addEventListener("change", suFile);
  }

  window.CalliopeImporta = {
    sezione,
    // Per le prove: lo stato per verifica (mai i nomi dei file)
    stato() {
      const out = {};
      for (const [k, s] of Object.entries(st)) {
        out[k] = { aperta: s.aperta, invio: s.invio, esito: s.esito, viva: !!(s.dati && s.dati.viva),
          importazioni: s.dati && Array.isArray(s.dati.importazioni)
            ? s.dati.importazioni.map((x) => ({ id: x.id, stato: x.stato, conti: x.conti, fasi: x.fasi })) : [] };
      }
      return out;
    },
    manda,
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", avvia);
  else avvia();
})();
