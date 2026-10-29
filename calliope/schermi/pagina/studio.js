// Calliope · lo Studio sul telefono, pagina minima delle pagine dei materiali (29/10/2026, passo
// 4.2, issue #281, epic #251, decisione 0035). Si apre da Le mie cose › Studio quando lo Studio è
// acceso (in ombra solo per chi amministra, con la scritta «prova»): si sceglie la verifica, si
// fotografano le pagine con la fotocamera (più scatti di fila) o si prendono dalla galleria (anche
// un PDF), si guardano con i bordi trovati, si rifanno, si mettono in ordine (su e giù), si tolgono
// e si mandano. La home vera dello Studio arriva con la 4.5.
// I bordi li trova bordi.js su un fotogramma di 320 px; la foto parte intera (JPEG, lato ≤ 3000)
// con i quattro angoli, e il server li ricontrolla, la raddrizza e decide (studio/pagine.py).
// Tutto ciò che arriva dal server va in textContent. Niente URL blob: la CSP del telefono non li
// ammette per le immagini; le miniature sono canvas.
"use strict";

(function () {
  const $ = (id) => document.getElementById(id);
  const sch = () => window.calliopeSchermo;
  const B = () => window.CalliopeBordi;
  const LATO_INVIO = 3000;
  const MINI = 96;
  const fmtGiorno = new Intl.DateTimeFormat("it-IT", { weekday: "short", day: "numeric", month: "numeric" });

  const st = {
    aperta: false,
    verifiche: [],
    pagine: [],                 // {id, tipo: foto|pdf, blob, angoli, intera, avvisi, nitidezza, mini, nome, kb, da}
    n: 0,
    flusso: null,               // MediaStream della fotocamera
    guida: null,                // il giro dei bordi sull'anteprima
    sostituisci: null,          // l'id della pagina da rifare
    invio: false,
    soglia: 150,                // la nitidezza sotto cui la pagina sembra sfocata (come il server)
  };

  function metti(el, t) { if (el && el.textContent !== t) el.textContent = t; }

  // ── la scelta della verifica ──
  async function caricaVerifiche() {
    if (!sch() || !sch().studio) return;
    const r = await sch().studio();
    if (!st.aperta) return;
    if (!r.ok) {
      metti($("studio-esito"), String(r.dati.errore || "Non riesco a leggere le verifiche: riprova tra poco."));
      st.verifiche = [];
    } else {
      st.verifiche = Array.isArray(r.dati.verifiche) ? r.dati.verifiche.filter((v) => v && Number.isInteger(v.id)) : [];
      $("studio-prova").hidden = !r.dati.prova;
    }
    const sel = $("studio-verifica");
    const prima = sel.value;
    sel.replaceChildren();
    for (const v of st.verifiche) {
      const o = document.createElement("option");
      o.value = String(v.id);
      let quando = "";
      try { quando = fmtGiorno.format(new Date(String(v.data) + "T12:00:00")); } catch (e) { quando = String(v.data || ""); }
      o.textContent = [String(v.materia || "Verifica"), quando, v.di ? "di " + String(v.di) : "",
        (Number(v.pagine) || 0) + " pag."].filter(Boolean).join(" · ");
      sel.append(o);
    }
    if (prima && st.verifiche.some((v) => String(v.id) === prima)) sel.value = prima;
    const nessuna = !st.verifiche.length;
    $("studio-nessuna").hidden = !nessuna || !r.ok;
    sel.hidden = nessuna;
    document.querySelector('label[for="studio-verifica"]').hidden = nessuna;
    $("studio-azioni").hidden = nessuna;
    if (nessuna) chiudiCamera();
    disegna();
  }

  // ── una foto in una pagina da mandare ──
  function tela(w, h) {
    const c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(w));
    c.height = Math.max(1, Math.round(h));
    return c;
  }
  function riduci(sorgente, w, h, lato) {
    const k = Math.min(1, lato / Math.max(w, h));
    const c = tela(w * k, h * k);
    const x = c.getContext("2d", { willReadFrequently: true });
    x.imageSmoothingEnabled = true;
    x.imageSmoothingQuality = "high";
    x.drawImage(sorgente, 0, 0, c.width, c.height);
    return c;
  }
  function grigiDi(c) {
    const d = c.getContext("2d", { willReadFrequently: true }).getImageData(0, 0, c.width, c.height).data;
    return B().grigio(d, c.width, c.height);
  }
  // I bordi e la nitidezza di una foto (come il server, che li ricontrolla)
  function esamina(sorgente, w, h) {
    const piccola = riduci(sorgente, w, h, B().LATO);
    const r = B().rileva(grigiDi(piccola), piccola.width, piccola.height);
    const media = riduci(sorgente, w, h, B().LATO_NITIDEZZA);
    const nit = B().nitidezza(grigiDi(media), media.width, media.height);
    return { angoli: r.angoli, intera: r.intera, nitidezza: nit };
  }
  function disegnaQuadro(ctx, angoli, w, h, colore) {
    if (!angoli) return;
    ctx.strokeStyle = colore;
    ctx.lineWidth = Math.max(2, w / 60);
    ctx.beginPath();
    angoli.forEach((a, i) => { const x = a[0] * w, y = a[1] * h; if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); });
    ctx.closePath();
    ctx.stroke();
  }
  function accento() {
    try { return getComputedStyle(document.documentElement).getPropertyValue("--accento").trim() || "#b9a3e8"; }
    catch (e) { return "#b9a3e8"; }
  }
  function miniatura(sorgente, w, h, angoli) {
    const c = riduci(sorgente, w, h, MINI);
    c.className = "studio-mini";
    c.setAttribute("aria-hidden", "true");
    disegnaQuadro(c.getContext("2d"), angoli, c.width, c.height, accento());
    return c;
  }
  function inBlob(c) {
    return new Promise((ok) => c.toBlob((b) => ok(b), "image/jpeg", 0.92));
  }
  // Una foto (canvas, bitmap o video) → la pagina pronta da mandare
  async function daFoto(sorgente, w, h, da) {
    const grande = riduci(sorgente, w, h, LATO_INVIO);
    const blob = await inBlob(grande);
    if (!blob) throw new Error("foto");
    const e = esamina(grande, grande.width, grande.height);
    const avvisi = [];
    if (!e.angoli && !e.intera) avvisi.push("bordi");
    if (e.nitidezza < st.soglia) avvisi.push("sfocata");
    return { id: ++st.n, tipo: "foto", blob, angoli: e.angoli, intera: e.intera, avvisi, nitidezza: e.nitidezza,
      mini: miniatura(grande, grande.width, grande.height, e.angoli), kb: Math.round(blob.size / 1024), da };
  }
  function aggiungi(p) {
    if (st.sostituisci !== null) {
      const i = st.pagine.findIndex((x) => x.id === st.sostituisci);
      st.sostituisci = null;
      if (i >= 0) { st.pagine[i] = p; disegna(); return; }
    }
    st.pagine.push(p);
    disegna();
  }

  // ── galleria e PDF ──
  async function bitmapDi(file) {
    if (window.createImageBitmap) {
      try { return await createImageBitmap(file, { imageOrientation: "from-image" }); } catch (e) { /* sotto */ }
      try { return await createImageBitmap(file); } catch (e) { /* sotto */ }
    }
    // Ripiego: un data URL (la CSP ammette data: per le immagini)
    const url = await new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = no; r.readAsDataURL(file); });
    const img = new Image();
    img.src = url;
    await img.decode();
    return img;
  }
  async function eUnPdf(file) {
    if (file.type === "application/pdf" || /\.pdf$/i.test(file.name || "")) return true;
    try { return new TextDecoder().decode(await file.slice(0, 5).arrayBuffer()) === "%PDF-"; } catch (e) { return false; }
  }
  async function daFile(files) {
    const esito = $("studio-esito");
    for (const f of files) {
      try {
        if (await eUnPdf(f)) {
          aggiungi({ id: ++st.n, tipo: "pdf", blob: f, nome: String(f.name || "documento.pdf").slice(0, 60),
            avvisi: [], kb: Math.round(f.size / 1024), da: "file" });
          continue;
        }
        const bm = await bitmapDi(f);
        const w = bm.width || bm.naturalWidth, h = bm.height || bm.naturalHeight;
        aggiungi(await daFoto(bm, w, h, "file"));
        if (bm.close) bm.close();
      } catch (e) {
        metti(esito, "Non riesco ad aprire «" + String(f.name || "il file").slice(0, 40) + "»: manda una foto JPEG o PNG, o un PDF.");
      }
    }
  }

  // ── la fotocamera ──
  async function apriCamera() {
    const esito = $("studio-esito");
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      metti(esito, "Qui la fotocamera non si apre: usa «Galleria o PDF».");
      return false;
    }
    if (!st.flusso) {
      try {
        st.flusso = await navigator.mediaDevices.getUserMedia({ audio: false,
          video: { facingMode: { ideal: "environment" }, width: { ideal: 2560 }, height: { ideal: 1920 } } });
      } catch (e) {
        metti(esito, "La fotocamera non si apre (permesso negato?): usa «Galleria o PDF».");
        return false;
      }
    }
    if (!st.aperta) { chiudiCamera(); return false; }
    const v = $("studio-video");
    v.srcObject = st.flusso;
    try { await v.play(); } catch (e) { /* parte da sé */ }
    $("studio-camera").hidden = false;
    $("studio-azioni").hidden = true;
    metti($("studio-camera-stato"), st.sostituisci !== null ? "Rifai la pagina: inquadrala tutta." : "Inquadra la pagina intera, poi «Scatta».");
    guida();
    try { $("studio-scatta").focus(); } catch (e) { /* niente */ }
    return true;
  }
  function chiudiCamera() {
    clearTimeout(st.guida);
    st.guida = null;
    if (st.flusso) { for (const t of st.flusso.getTracks()) t.stop(); st.flusso = null; }
    const v = $("studio-video");
    if (v) v.srcObject = null;
    if ($("studio-camera")) $("studio-camera").hidden = true;
    if ($("studio-azioni")) $("studio-azioni").hidden = !st.verifiche.length;
  }
  // I bordi sull'anteprima, ogni mezzo secondo
  function guida() {
    clearTimeout(st.guida);
    const v = $("studio-video"), c = $("studio-guida");
    if (!st.flusso || !v || !c) return;
    if (v.videoWidth) {
      const piccola = riduci(v, v.videoWidth, v.videoHeight, B().LATO);
      const r = B().rileva(grigiDi(piccola), piccola.width, piccola.height);
      c.width = v.clientWidth || piccola.width;
      c.height = v.clientHeight || piccola.height;
      const ctx = c.getContext("2d");
      ctx.clearRect(0, 0, c.width, c.height);
      disegnaQuadro(ctx, r.angoli, c.width, c.height, accento());
      metti($("studio-camera-stato"), r.angoli ? "Bordi trovati: «Scatta»." : (r.intera ? "La pagina riempie la foto: va bene." : "Non vedo i bordi: avvicinati o metti la pagina su un fondo scuro."));
    }
    st.guida = setTimeout(guida, 500);
  }
  async function scatta() {
    const v = $("studio-video");
    if (!v || !v.videoWidth) return;
    const b = $("studio-scatta");
    b.disabled = true;
    try {
      const rifai = st.sostituisci !== null;
      aggiungi(await daFoto(v, v.videoWidth, v.videoHeight, "camera"));
      metti($("studio-camera-stato"), "Pagina " + st.pagine.length + " presa. La prossima, oppure «Fatto».");
      if (rifai) chiudiCamera();
    } catch (e) {
      metti($("studio-camera-stato"), "Lo scatto non è riuscito: riprova.");
    } finally { b.disabled = false; }
  }

  // ── l'elenco ──
  const AVVISI = { bordi: "bordi non trovati: mando la foto intera", sfocata: "forse sfocata: rifalla",
    piccola: "foto piccola: i numeri si leggono male" };
  function tasto(testo, etichetta, azione, id, spento) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "tasto studio-tasto";
    b.textContent = testo;
    b.dataset.azione = azione;
    b.dataset.pagina = String(id);
    if (etichetta) b.setAttribute("aria-label", etichetta);
    b.disabled = !!spento || st.invio;
    return b;
  }
  function disegna() {
    const ol = $("studio-elenco");
    if (!ol) return;
    const n = st.pagine.length;
    ol.replaceChildren(...st.pagine.map((p, i) => {
      const li = document.createElement("li");
      li.className = "studio-pagina";
      li.dataset.pagina = String(p.id);
      const fig = document.createElement("div");
      fig.className = "studio-fig";
      if (p.tipo === "pdf") {
        const s = document.createElement("span");
        s.className = "studio-pdf";
        s.textContent = "PDF";
        s.setAttribute("aria-hidden", "true");
        fig.append(s);
      } else fig.append(p.mini);
      const testo = document.createElement("div");
      testo.className = "studio-testo";
      const t = document.createElement("b");
      t.textContent = p.tipo === "pdf" ? (i + 1) + ". " + p.nome : "Pagina " + (i + 1);
      const sotto = document.createElement("span");
      sotto.className = "studio-nota";
      sotto.textContent = p.tipo === "pdf" ? "PDF · " + p.kb + " kB: lo divido in pagine"
        : (p.angoli ? "bordi trovati" : (p.intera ? "pagina intera" : "")) ;
      testo.append(t, sotto);
      for (const a of p.avvisi || []) {
        const av = document.createElement("span");
        av.className = "studio-avviso";
        av.textContent = AVVISI[a] || String(a);
        testo.append(av);
      }
      const tasti = document.createElement("div");
      tasti.className = "studio-tasti";
      const nome = p.tipo === "pdf" ? p.nome : "la pagina " + (i + 1);
      tasti.append(tasto("↑", "Sposta su " + nome, "su", p.id, i === 0),
        tasto("↓", "Sposta giù " + nome, "giu", p.id, i === n - 1),
        tasto(p.tipo === "pdf" ? "Cambia" : "Rifai", (p.tipo === "pdf" ? "Cambia " : "Rifai ") + nome, "rifai", p.id),
        tasto("Togli", "Togli " + nome, "togli", p.id));
      li.append(fig, testo, tasti);
      return li;
    }));
    $("studio-titolo-elenco").hidden = !n;
    const invia = $("studio-invia");
    invia.hidden = !n;
    invia.disabled = st.invio || !n || !st.verifiche.length;
    metti(invia, n === 1 ? "Manda la pagina" : "Manda " + n + (st.pagine.some((p) => p.tipo === "pdf") ? " file" : " pagine"));
  }
  function suElenco(ev) {
    const b = ev.target.closest && ev.target.closest("button[data-azione]");
    if (!b || st.invio) return;
    const id = Number(b.dataset.pagina);
    const i = st.pagine.findIndex((p) => p.id === id);
    if (i < 0) return;
    const az = b.dataset.azione;
    let fuoco = null;
    if (az === "su" && i > 0) { [st.pagine[i - 1], st.pagine[i]] = [st.pagine[i], st.pagine[i - 1]]; fuoco = [id, "su"]; }
    else if (az === "giu" && i < st.pagine.length - 1) { [st.pagine[i + 1], st.pagine[i]] = [st.pagine[i], st.pagine[i + 1]]; fuoco = [id, "giu"]; }
    else if (az === "togli") { st.pagine.splice(i, 1); }
    else if (az === "rifai") {
      st.sostituisci = id;
      if (st.pagine[i].da === "camera") { apriCamera().then((ok) => { if (!ok) { st.sostituisci = id; $("studio-file").click(); } }); }
      else $("studio-file").click();
      return;
    }
    disegna();
    metti($("studio-esito"), "");
    // Il fuoco resta sul tasto appena toccato, se c'è ancora (chi usa un lettore non si perde)
    if (fuoco) {
      const nb = document.querySelector('#studio-elenco button[data-pagina="' + fuoco[0] + '"][data-azione="' + fuoco[1] + '"]');
      const alt = document.querySelector('#studio-elenco button[data-pagina="' + fuoco[0] + '"][data-azione="' + (fuoco[1] === "su" ? "giu" : "su") + '"]');
      try { ((nb && !nb.disabled) ? nb : alt).focus(); } catch (e) { /* niente */ }
    }
  }

  // ── l'invio, una pagina alla volta e nell'ordine ──
  async function invia() {
    if (st.invio || !st.pagine.length) return;
    const vid = Number($("studio-verifica").value);
    if (!Number.isInteger(vid) || vid < 1) return;
    st.invio = true;
    chiudiCamera();
    disegna();
    const esito = $("studio-esito");
    const tot = st.pagine.length;
    let materiale = null, mandate = 0, avvisi = 0;
    try {
      while (st.pagine.length) {
        const p = st.pagine[0];
        metti(esito, "Mando " + (mandate + 1) + " di " + tot + "…");
        const meta = { verifica: vid };
        if (p.tipo === "foto") {
          if (materiale) meta.materiale = materiale;
          if (p.angoli) meta.angoli = p.angoli.map((a) => [Number(a[0].toFixed(4)), Number(a[1].toFixed(4))]);
        } else meta.nome = p.nome;
        const r = await sch().studio(p.blob, meta);
        if (!r.ok) {
          metti(esito, String(r.dati.errore || "Non sono riuscita a mandarla: riprova.") +
            (mandate ? " Mandate " + mandate + " su " + tot + "." : ""));
          return;
        }
        if (p.tipo === "foto" && Number.isInteger(r.dati.materiale)) materiale = r.dati.materiale;
        for (const x of Array.isArray(r.dati.pagine) ? r.dati.pagine : []) avvisi += (x && Array.isArray(x.avvisi) && x.avvisi.length) ? 1 : 0;
        st.pagine.shift();
        mandate++;
        disegna();
      }
      metti(esito, (mandate === 1 ? "Mandata." : "Mandate tutte (" + mandate + ").") + " Le leggo più avanti." +
        (avvisi ? " " + (avvisi === 1 ? "Una pagina ha" : avvisi + " pagine hanno") + " un avviso: le guardi dopo." : ""));
    } finally {
      st.invio = false;
      disegna();
      caricaVerifiche();
    }
  }

  // ── apri e chiudi (sezioni.js, Le mie cose › Studio) ──
  function apri() {
    st.aperta = true;
    $("studio").hidden = false;
    metti($("studio-esito"), "");
    disegna();
    caricaVerifiche();
  }
  function chiudi() {
    st.aperta = false;
    chiudiCamera();
    if ($("studio")) $("studio").hidden = true;
  }

  function avvia() {
    if (!$("studio") || !B()) return;
    $("studio-camera-apri").addEventListener("click", () => { st.sostituisci = null; apriCamera(); });
    $("studio-file-apri").addEventListener("click", () => { st.sostituisci = null; $("studio-file").click(); });
    $("studio-file").addEventListener("change", async (ev) => {
      const files = [...(ev.target.files || [])];
      ev.target.value = "";
      const sost = st.sostituisci;
      if (sost !== null && files.length > 1) files.length = 1;
      await daFile(files);
      if (sost !== null) st.sostituisci = null;
    });
    $("studio-scatta").addEventListener("click", scatta);
    $("studio-camera-fine").addEventListener("click", () => { st.sostituisci = null; chiudiCamera(); });
    $("studio-elenco").addEventListener("click", suElenco);
    $("studio-invia").addEventListener("click", invia);
    // A pagina nascosta la fotocamera si spegne (batteria, e la luce della fotocamera)
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") chiudiCamera(); });
    window.CalliopePagine = window.CalliopePagine || {};
    window.CalliopePagine.studio = { apri, chiudi };
  }

  // Per le prove: le pagine in lista e lo stato
  window.CalliopeStudio = {
    stato() {
      return { aperta: st.aperta, verifiche: st.verifiche.map((v) => v.id), invio: st.invio,
        camera: !!st.flusso,
        pagine: st.pagine.map((p) => ({ id: p.id, tipo: p.tipo, angoli: p.angoli, intera: !!p.intera, avvisi: p.avvisi.slice(),
          nitidezza: p.nitidezza, kb: p.kb })) };
    },
    daFile,
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", avvia);
  else avvia();
})();
