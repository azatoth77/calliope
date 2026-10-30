// Calliope · lo Studio sul telefono, pagina minima delle pagine dei materiali (29/10/2026, passo
// 4.2, issue #281, epic #251, decisione 0035). Si apre da Le mie cose › Studio quando lo Studio è
// acceso (in ombra solo per chi amministra, con la scritta «prova»): si sceglie la verifica, si
// fotografano le pagine con la fotocamera (più scatti di fila) o si prendono dalla galleria (anche
// un PDF), si guardano con i bordi trovati, si rifanno, si mettono in ordine (su e giù), si tolgono
// e si mandano. Dal 30/10 (passo 4.4, #283) sotto c'è la vista minima degli argomenti proposti
// della verifica scelta: «Tieni», «Togli», «Rinomina» e «Conferma gli argomenti»
// (POST /api/studio/argomenti). Dal 30/10 (passo 4.5, #284) la pagina si apre sulla home dello
// Studio (POST /api/studio/home), anche sul PC personale; le pagine dei materiali sono una vista
// sotto («Pagine»), solo sul telefono (la fotocamera e bordi.js).
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
    arg: null,                  // la vista degli argomenti della verifica scelta (passo 4.4)
    argInvio: false,
    rinomina: null,             // l'id dell'argomento che si sta rinominando
    materiali: false,           // c'è la vista delle pagine (il telefono)
    vidVoluta: null,            // la verifica scelta dalla home per «Pagine»
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
    if (st.vidVoluta && st.verifiche.some((v) => v.id === st.vidVoluta)) { sel.value = String(st.vidVoluta); st.vidVoluta = null; }
    const nessuna = !st.verifiche.length;
    $("studio-nessuna").hidden = !nessuna || !r.ok;
    sel.hidden = nessuna;
    document.querySelector('label[for="studio-verifica"]').hidden = nessuna;
    $("studio-azioni").hidden = nessuna;
    if (nessuna) chiudiCamera();
    disegna();
    caricaArgomenti();
  }

  // ── gli argomenti proposti e la conferma (30/10, passo 4.4, #283) ──
  // Il titolo è un dato (viene dalle pagine e dal modello): sempre textContent
  const STATI_ARG = { proposto: "proposto", tenuto: "tenuto", tolto: "tolto", aggiunto: "aggiunto da te" };
  const AVVISI_ARG = { da_controllare: "da controllare: non lo trovo nelle pagine che cita",
    pagina_con_istruzioni: "viene da una pagina con un messaggio per un assistente: non lo seguo",
    titolo_ordine: "il titolo sembra un ordine o un annuncio: controllalo",
    unito: "unito a un altro argomento" };
  function verificaScelta() {
    const v = Number($("studio-verifica") && $("studio-verifica").value);
    return Number.isInteger(v) && v > 0 ? v : null;
  }
  async function caricaArgomenti(dati) {
    const box = $("studio-argomenti");
    const vid = verificaScelta();
    if (!box || !sch() || !sch().studioArgomenti) return;
    if (!vid) { box.hidden = true; return; }
    st.argInvio = true;
    disegnaArgomenti();
    const r = await sch().studioArgomenti(Object.assign({ verifica: vid }, dati || {}));
    st.argInvio = false;
    if (!st.aperta || verificaScelta() !== vid) return;
    if (!r.ok) {
      metti($("studio-argomenti-esito"), String(r.dati.errore || "Non riesco a leggere gli argomenti: riprova tra poco."));
      disegnaArgomenti();
      return;
    }
    st.arg = r.dati;
    if (dati && dati.azione === "conferma") {
      const n = Number(r.dati.da_decidere) || 0;
      metti($("studio-argomenti-esito"), "Confermati: il piano è pronto." +
        (n ? " " + (n === 1 ? "Uno resta" : n + " restano") + " da decidere: tienili o toglili tu." : ""));
    } else if (dati) metti($("studio-argomenti-esito"), "");
    disegnaArgomenti();
  }
  function statoArgomenti(d) {
    const e = d.estrazione || {};
    const nl = Number(e.pagine_non_lette) || 0;
    // Le pagine illeggibili o da parte restano fuori dagli argomenti (revisione della PR #315)
    const fuori = nl && e.pagine_lette ? " " + (nl === 1 ? "Una pagina non l'ho letta" : nl + " pagine non le ho lette") +
      ": gli argomenti vengono dalle altre." : "";
    return (statoBase(d) + fuori).trim();
  }
  function statoBase(d) {
    const e = d.estrazione || {}, l = d.lettura || {};
    if ((d.argomenti || []).length) return "";
    if (!e.pagine_lette) return "Gli argomenti arrivano quando ho letto tutte le pagine (lette " +
      (Number(l.lette) || 0) + " di " + (Number(l.totali) || 0) + ").";
    if (e.esito === "rotto" || e.esito === "errore") return "Non sono riuscita a trovare gli argomenti: riprova più tardi.";
    if (e.da_fare && e.accesa) return "Sto cercando gli argomenti nelle pagine.";
    return "Non ho trovato argomenti in queste pagine.";
  }
  function tastoArg(testo, etichetta, azione, id, spento) {
    const b = tasto(testo, etichetta, azione, id, spento || st.argInvio);
    b.dataset.argomento = String(id);
    delete b.dataset.pagina;
    return b;
  }
  function disegnaArgomenti() {
    const box = $("studio-argomenti"), ol = $("studio-argomenti-elenco");
    if (!box || !ol) return;
    const d = st.arg;
    if (!d || !verificaScelta() || !d.verifica || d.verifica.id !== verificaScelta()) { box.hidden = !verificaScelta(); ol.replaceChildren(); return; }
    box.hidden = false;
    metti($("studio-argomenti-stato"), statoArgomenti(d));
    const args = Array.isArray(d.argomenti) ? d.argomenti : [];
    ol.replaceChildren(...args.map((a) => {
      const li = document.createElement("li");
      li.className = "studio-pagina studio-argomento" + (a.stato === "tolto" ? " studio-tolto" : "");
      const testo = document.createElement("div");
      testo.className = "studio-testo";
      if (st.rinomina === a.id) {
        const inp = document.createElement("input");
        inp.type = "text";
        inp.maxLength = 60;
        inp.className = "studio-rinomina";
        inp.value = String(a.titolo || "");
        inp.setAttribute("aria-label", "Nuovo titolo");
        inp.id = "studio-rinomina-" + a.id;
        testo.append(inp);
      } else {
        const t = document.createElement("b");
        t.textContent = String(a.titolo || "");
        testo.append(t);
      }
      const sotto = document.createElement("span");
      sotto.className = "studio-nota";
      sotto.textContent = [STATI_ARG[a.stato] || String(a.stato || ""),
        (Array.isArray(a.pagine) && a.pagine.length) ? a.pagine.map(String).join(", ") : ""].filter(Boolean).join(" · ");
      testo.append(sotto);
      for (const x of Array.isArray(a.avvisi) ? a.avvisi : []) {
        const av = document.createElement("span");
        av.className = "studio-avviso";
        av.textContent = AVVISI_ARG[x] || String(x);
        testo.append(av);
      }
      const tasti = document.createElement("div");
      tasti.className = "studio-tasti";
      const nome = "«" + String(a.titolo || "").slice(0, 60) + "»";
      if (st.rinomina === a.id) {
        tasti.append(tastoArg("Salva", "Salva il titolo", "salva", a.id), tastoArg("Annulla", "Annulla", "annulla", a.id));
      } else {
        tasti.append(tastoArg("Tieni", "Tieni " + nome, "tieni", a.id, a.stato === "tenuto" || a.stato === "aggiunto"),
          tastoArg("Togli", "Togli " + nome, "togli", a.id, a.stato === "tolto"),
          tastoArg("Rinomina", "Rinomina " + nome, "rinomina", a.id));
      }
      li.append(testo, tasti);
      return li;
    }));
    const conf = $("studio-argomenti-conferma");
    const daConfermare = args.some((a) => a.stato === "proposto") || (d.verifica.stato === "bozza" && args.length);
    conf.hidden = !daConfermare;
    conf.disabled = !!st.argInvio;
  }
  function suArgomenti(ev) {
    const b = ev.target.closest && ev.target.closest("button[data-argomento]");
    if (!b || st.argInvio) return;
    const id = Number(b.dataset.argomento);
    const az = b.dataset.azione;
    if (az === "rinomina") { st.rinomina = id; disegnaArgomenti(); try { $("studio-rinomina-" + id).focus(); } catch (e) { /* niente */ } return; }
    if (az === "annulla") { st.rinomina = null; disegnaArgomenti(); return; }
    if (az === "salva") {
      const inp = $("studio-rinomina-" + id);
      const titolo = inp ? inp.value.trim() : "";
      st.rinomina = null;
      if (titolo) caricaArgomenti({ azione: "rinomina", argomento: id, titolo });
      else disegnaArgomenti();
      return;
    }
    if (az === "tieni" || az === "togli") caricaArgomenti({ azione: az, argomento: id });
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
        } else { meta.nome = p.nome; meta.pdf = true; }     // il 429 prima del corpo (4.5)
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


  // ── la home dello Studio (30/10, passo 4.5, #284) ──
  // Dal canvas (StudioHome, StudioVerifica, PcStudio) e dagli spunti approvati il 28/10: la
  // prossima verifica con la data, i giorni che mancano, l'obiettivo e (solo dopo due misure) la
  // previsione; oggi; le tappe; Impara / Esercitati / Esame con ciò che c'è davvero (oggi solo
  // «leggi le pagine»: niente tasti finti); lo stato della lettura; gli argomenti da decidere col
  // perché e «Tieni»; le pagine messe da parte con «Riprova»; le due domande prima di cominciare.
  // Le azioni sono tocchi (POST /api/tocco → il ciclo, ToolRegistry.call): entrano nella
  // conversazione. Titoli e testi arrivano dalle pagine: sempre textContent.
  const MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
    "settembre", "ottobre", "novembre", "dicembre"];
  const GIORNI_S = ["domenica", "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato"];
  const PERCHE = { da_controllare: "non lo trovo nelle pagine che cita",
    pagina_con_istruzioni: "viene da una pagina con un messaggio per un assistente",
    titolo_ordine: "il titolo sembra un ordine o un annuncio" };
  const home = { dati: null, carica: false, domande: null, scelte: {}, esito: "", attesa: {} };

  function nodo(tag, cls, testo) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (testo !== undefined && testo !== null) n.textContent = String(testo);
    return n;
  }
  function dataDetta(iso) {
    const d = new Date(String(iso) + "T12:00:00");
    if (isNaN(d)) return String(iso || "");
    return GIORNI_S[d.getDay()] + " " + d.getDate() + " " + MESI[d.getMonth()];
  }
  function mancano(n) {
    n = Number(n);
    return n <= 0 ? "oggi" : n === 1 ? "domani" : "fra " + n + " giorni";
  }
  function tastoHome(testo, tocco, dati, cls) {
    const b = nodo("button", "tasto studio-h-tasto" + (cls ? " " + cls : ""), testo);
    b.type = "button";
    b.dataset.tocco = tocco;
    b.dataset.dati = JSON.stringify(dati);
    b.disabled = !home.dati || !home.dati.tocchi || !!home.attesa[tocco + JSON.stringify(dati)];
    return b;
  }

  async function caricaHome() {
    if (!sch() || !sch().studioHome) return;
    home.carica = true;
    const r = await sch().studioHome();
    home.carica = false;
    if (!st.aperta) return;
    if (!r.ok) { home.esito = String(r.dati.errore || "Non riesco a leggere lo Studio: riprova tra poco."); }
    else home.dati = r.dati;
    disegnaHome();
  }

  function cartaVerifica(v, prima) {
    const art = nodo("article", "studio-h-verifica" + (prima ? " studio-h-prima" : ""));
    art.dataset.verifica = String(v.id);
    const testa = nodo("div", "studio-h-testa");
    testa.append(nodo("span", "studio-h-etichetta", prima ? "Prossima verifica" : "Verifica"),
      nodo("span", "studio-h-quando", dataDetta(v.data) + " · " + mancano(v.giorni_mancanti)));
    art.append(testa);
    art.append(nodo("h3", "studio-h-titolo", [String(v.materia || ""), v.argomento ? String(v.argomento) : ""]
      .filter(Boolean).join(" · ") + (v.di ? " (di " + String(v.di) + ")" : "")));
    // Obiettivo e previsione: la previsione solo dopo due misure vere (spunto del 28/10)
    const ob = nodo("div", "studio-h-obiettivo");
    const barra = nodo("div", "studio-h-barra");
    const pieno = nodo("div", "studio-h-pieno");
    // La forbice dopo 3 prove in 2 giorni (0035 punto 9); prima l'ultima prova vera, se c'è
    const fb = Array.isArray(v.previsione) && v.previsione.length === 2 ? v.previsione.map(Number) : null;
    const ult = v.ultima === null || v.ultima === undefined ? null : Number(v.ultima);
    const prev = fb ? (fb[0] + fb[1]) / 2 : ult;
    pieno.style.width = (prev === null ? 0 : Math.max(0, Math.min(100, prev))) + "%";
    const segno = nodo("div", "studio-h-segno");
    segno.style.left = Math.max(0, Math.min(100, Number(v.obiettivo) || 75)) + "%";
    barra.append(pieno, segno);
    const ob_ = "obiettivo " + (Number(v.obiettivo) || 75) + "%";
    ob.append(barra, nodo("span", "studio-h-nota", fb ? "previsione fra " + fb[0] + " e " + fb[1] + "% · " + ob_
      : ult !== null ? "l'ultima prova: " + Math.round(ult) + "% · " + ob_
      : ob_ + " · la previsione arriva con gli esercizi"));
    art.append(ob);
    // La lettura delle pagine
    const l = v.lettura || {};
    const righe = [];
    if (l.frase) righe.push(String(l.frase));
    else if (Number(l.totali)) righe.push("Pagine lette " + (Number(l.lette) || 0) + " di " + Number(l.totali) +
      ((Number(l.da_leggere) || 0) + (Number(l.in_lettura) || 0) ? (l.in_attesa ? ": leggo le altre quando la DGX è libera." : ": leggo le altre.") : "."));
    else righe.push("Nessuna pagina: fotografale da «Pagine».");
    if (v.stato === "bozza" && v.argomenti && v.argomenti.proposti) righe.push("Gli argomenti aspettano la tua conferma.");
    for (const x of righe) art.append(nodo("p", "studio-h-riga", x));
    // Oggi
    if (v.oggi) {
      const o = nodo("div", "studio-h-oggi");
      o.append(nodo("span", "studio-h-oggi-cosa", "Oggi · " + (Number(v.oggi.minuti) || 0) + " minuti" + (v.oggi.fatto ? " · fatto" : "")),
        nodo("span", "studio-h-oggi-att", String(v.oggi.attivita || "")));
      art.append(o);
    } else if (v.stato === "aperta" && (v.avvisi_piano || []).length) {
      art.append(nodo("p", "studio-h-riga", "Oggi nel piano non c'è niente."));
    }
    for (const a of v.avvisi_piano || []) {
      if (a === "piano_non_aggiornato") art.append(nodo("p", "studio-avviso", "Il piano non sono riuscita ad aggiornarlo: è quello di prima."));
    }
    // I tasti di oggi: tocchi veri, solo quando servono
    const tasti = nodo("div", "studio-h-tasti");
    const sess = home.dati.sessione && home.dati.sessione.verifica === v.id;
    if (v.oggi && !v.oggi.fatto) {
      if (!sess) {
        const b = nodo("button", "tasto studio-h-tasto studio-h-primo", "Inizia");
        b.type = "button";
        b.dataset.domande = String(v.id);
        b.disabled = !home.dati.tocchi;
        tasti.append(b);
      }
      tasti.append(tastoHome("Fatto", "studio_fatto", { verifica: v.id }, sess ? "studio-h-primo" : ""),
        tastoHome("Non ce la faccio oggi", "studio_salta", { verifica: v.id }));
    }
    const pag = nodo("button", "tasto studio-h-tasto", "Pagine");
    pag.type = "button";
    pag.dataset.pagine = String(v.id);
    if (st.materiali) tasti.append(pag);
    if (tasti.childNodes.length) art.append(tasti);
    if (home.domande === v.id) art.append(pannelloDomande(v));
    // Impara / Esercitati / Esame: solo ciò che c'è (passo 4.5: «leggi le pagine»)
    if (v.oggi) {
      const imp = nodo("section", "studio-h-gruppo");
      imp.append(nodo("h4", "studio-h-sotto", "Impara"));
      imp.append(nodo("p", "studio-h-riga", String(v.oggi.attivita || "") + " Sul tuo libro; se una cosa non è chiara, chiedimela."));
      art.append(imp);
    }
    // Le tappe (gli argomenti del piano, uno dopo l'altro)
    if ((v.tappe || []).length) {
      const t = nodo("ol", "studio-h-tappe");
      t.setAttribute("aria-label", "Tappe");
      for (const x of v.tappe) {
        const li = nodo("li", "studio-h-tappa studio-h-" + String(x.stato || "chiusa"));
        li.append(nodo("span", "studio-h-pallino", x.stato === "fatta" ? "✓" : ""),
          nodo("span", "studio-h-tappa-nome", String(x.titolo || "")));
        t.append(li);
      }
      art.append(nodo("h4", "studio-h-sotto", "Tappe"), t);
    }
    // Gli argomenti da decidere, col perché, e «Tieni» con un tocco
    const dd = (v.argomenti && v.argomenti.da_decidere) || [];
    if (dd.length) {
      art.append(nodo("h4", "studio-h-sotto", "Da decidere"));
      const ul = nodo("ul", "studio-h-elenco");
      for (const a of dd) {
        const li = nodo("li", "studio-h-voce");
        const tx = nodo("div", "studio-testo");
        tx.append(nodo("b", null, String(a.titolo || "")),
          nodo("span", "studio-avviso", "Fuori dal piano: " + (a.avvisi || []).map((x) => PERCHE[x] || String(x)).join("; ") + "."));
        li.append(tx, tastoHome("Tieni", "studio_tieni", { verifica: v.id, argomento: a.id }));
        ul.append(li);
      }
      art.append(ul);
    }
    // Fuori dal piano: gli argomenti tolti, rimessi con «Tieni» (studio_tieni)
    const tolti = Array.isArray(v.tolti) ? v.tolti : [];
    if (tolti.length) {
      art.append(nodo("h4", "studio-h-sotto", "Fuori dal piano"));
      const ul = nodo("ul", "studio-h-elenco");
      for (const a of tolti) {
        const li = nodo("li", "studio-h-voce");
        const tx = nodo("div", "studio-testo");
        tx.append(nodo("b", null, String(a.titolo || "")));
        li.append(tx, tastoHome("Tieni", "studio_tieni", { verifica: v.id, argomento: a.id }));
        ul.append(li);
      }
      art.append(ul);
    }
    // Le pagine messe da parte («da_parte» detto a parole) con «Riprova»
    for (const p of v.da_parte || []) {
      const li = nodo("div", "studio-h-voce");
      li.append(nodo("p", "studio-h-riga", "La " + (p.numero ? "pagina " + p.numero : "foto " + p.ordine) +
        " l'ho messa da parte: leggendola il modello si fermava. La riprovo da sola una volta al giorno."),
      tastoHome("Riprova", "studio_riprova", { verifica: v.id, pagina: p.id }));
      art.append(li);
    }
    // La preparazione e le sessioni (passo 4b, #244): righe scritte dal server dai soli dati
    // salvati (eventi, piano, pagine), mai dal modello; qui solo textContent
    const rp = v.riepilogo;
    if (rp && Array.isArray(rp.righe) && rp.righe.length) {
      const sez = nodo("section", "studio-h-gruppo studio-h-preparazione");
      sez.append(nodo("h4", "studio-h-sotto", "La preparazione"));
      for (const x of rp.righe) sez.append(nodo("p", "studio-h-riga", String(x)));
      art.append(sez);
    }
    if (rp && Array.isArray(rp.sessioni) && rp.sessioni.length) {
      const det = nodo("details", "studio-h-sessioni");
      det.append(nodo("summary", null, "Le sessioni"));
      const ol = nodo("ol", "studio-h-giorni");
      for (const s of rp.sessioni) {
        ol.append(nodo("li", "studio-h-giorno studio-h-s-" + String(s.stato || ""), String(s.testo || "")));
      }
      det.append(ol);
      art.append(det);
    }
    // Il piano, giorno per giorno
    if ((v.giorni || []).length) {
      const det = nodo("details", "studio-h-piano");
      det.dataset.verifica = String(v.id);
      det.append(nodo("summary", null, "Il piano"));
      const ol = nodo("ol", "studio-h-giorni");
      for (const g of v.giorni) {
        const li = nodo("li", "studio-h-giorno" + (g.fatto ? " studio-h-fatto" : ""));
        li.append(nodo("span", "studio-h-g-quando", dataDetta(g.giorno) + (g.fase === "ripasso" ? " · ripasso" : "")),
          nodo("span", "studio-h-g-cosa", String(g.attivita || "") + " " + (Number(g.minuti) || 0) + " min" + (g.fatto ? " ✓" : "")));
        ol.append(li);
      }
      det.append(ol);
      art.append(det);
    }
    const es = nodo("p", "pagina-esito studio-h-esito");
    es.setAttribute("role", "status");
    es.dataset.verifica = String(v.id);
    es.textContent = home.esito && home.esitoDi === v.id ? home.esito : "";
    art.append(es);
    return art;
  }

  function pannelloDomande(v) {
    const p = nodo("div", "studio-h-domande");
    const s = home.scelte;
    const gruppo = (titolo, nome, voci, valori) => {
      const f = nodo("fieldset", "studio-h-scelte");
      f.append(nodo("legend", null, titolo));
      voci.forEach((t, i) => {
        const b = nodo("button", "tasto studio-h-chip", t);
        b.type = "button";
        b.dataset.scelta = nome;
        b.dataset.valore = String(valori[i]);
        b.setAttribute("aria-pressed", String(s[nome] === valori[i]));
        f.append(b);
      });
      return f;
    };
    const con = home.dati.conoscenza || [];
    p.append(gruppo("Quanto conosci l'argomento?", "conoscenza", con, con.map((_, i) => i + 1)),
      gruppo("Come ti senti oggi?", "umore", home.dati.umori || [], home.dati.umori || []));
    const via = tastoHome("Comincia", "studio_sessione", { verifica: v.id }, "studio-h-primo");
    via.disabled = via.disabled || (s.conoscenza === undefined && s.umore === undefined);
    p.append(via, nodo("p", "studio-h-nota", "Lo uso solo per oggi, per come ti parlo: non lo salvo e non lo dico a nessuno."));
    return p;
  }

  function disegnaHome() {
    const box = $("studio-home");
    if (!box) return;
    const d = home.dati;
    const fig = [];
    if (!d) {
      fig.push(nodo("p", "pagina-nota", home.carica ? "Un attimo…" : (home.esito || "")));
    } else {
      $("studio-prova").hidden = !d.prova;
      const vv = Array.isArray(d.verifiche) ? d.verifiche : [];
      vv.forEach((v, i) => fig.push(cartaVerifica(v, i === 0)));
      if (!vv.length) fig.push(nodo("p", "pagina-nota", "Non hai verifiche nello Studio."));
      fig.push(nodo("p", "studio-h-nuova", "Per una verifica nuova dimmelo: «Calliope, giovedì ho la verifica di storia»."));
    }
    box.replaceChildren(...fig);
  }

  async function suHome(ev) {
    const b = ev.target.closest && ev.target.closest("button");
    if (!b || b.disabled) return;
    if (b.dataset.pagine) { apriMateriali(Number(b.dataset.pagine)); return; }
    if (b.dataset.domande) {
      const id = Number(b.dataset.domande);
      home.domande = home.domande === id ? null : id;
      home.scelte = {};
      disegnaHome();
      vista({ vista: home.domande ? "sessione" : "home", verifica: home.domande || undefined });
      return;
    }
    if (b.dataset.scelta) {
      const n = b.dataset.scelta;
      home.scelte[n] = n === "conoscenza" ? Number(b.dataset.valore) : b.dataset.valore;
      disegnaHome();
      return;
    }
    const tocco = b.dataset.tocco;
    if (!tocco) return;
    let dati = {};
    try { dati = JSON.parse(b.dataset.dati || "{}"); } catch (e) { return; }
    if (tocco === "studio_sessione") Object.assign(dati, home.scelte);
    const k = tocco + JSON.stringify(dati);
    home.attesa[k] = true;
    home.esitoDi = dati.verifica;
    home.esito = "Un attimo…";
    disegnaHome();
    const r = await sch().studioTocco(Object.assign({ tocco }, dati));
    if (r.ok) return;                                  // l'esito arriva dal ciclo (evento «tocco»)
    delete home.attesa[k];
    home.esito = String(r.dati.errore || "Non ci sono riuscita: riprova o chiedimelo a voce.");
    disegnaHome();
  }

  // L'esito di un tocco dello Studio dal ciclo (evento SSE «tocco», schermo.js)
  function esitoHome(d) {
    home.attesa = {};
    home.esito = d.ok ? "" : String(d.errore || "Non ci sono riuscita: riprova.");
    if (d.ok && d.tocco === "studio_sessione") { home.domande = null; home.scelte = {}; vista({ vista: "home" }); }
    caricaHome();
  }

  // La vista aperta, al server al più una volta al secondo (studio/vista.py)
  let vistaUltima = "", vistaTimer = null;
  function vista(v) {
    const t = JSON.stringify(v || { vista: null });
    if (t === vistaUltima) return;
    vistaUltima = t;
    clearTimeout(vistaTimer);
    vistaTimer = setTimeout(() => { if (sch() && sch().vista) sch().vista(JSON.parse(vistaUltima)); }, 1000);
  }

  function apriHome() {
    st.materiali = !!$("studio-materiali");
    if ($("studio-materiali")) { $("studio-materiali").hidden = true; chiudiCamera(); }
    $("studio-home").hidden = false;
    disegnaHome();
    caricaHome();
    vista({ vista: "home" });
  }
  function apriMateriali(vid) {
    if (!$("studio-materiali")) return;
    $("studio-home").hidden = true;
    $("studio-materiali").hidden = false;
    st.vidVoluta = vid;
    caricaVerifiche();
    vista({ vista: "pagine", verifica: vid });
  }

  // ── apri e chiudi (sezioni.js, Le mie cose › Studio) ──
  function apri() {
    st.aperta = true;
    $("studio").hidden = false;
    if ($("studio-esito")) metti($("studio-esito"), "");
    if (st.materiali) disegna();
    apriHome();
  }
  function chiudi() {
    st.aperta = false;
    if (st.materiali) chiudiCamera();
    if ($("studio")) $("studio").hidden = true;
    vista({ vista: null });
  }

  function avvia() {
    if (!$("studio") || !$("studio-home")) return;
    $("studio-home").addEventListener("click", suHome);
    // «Il piano» aperto: la vista del piano (toggle non risale: in cattura)
    $("studio-home").addEventListener("toggle", (ev) => {
      const d = ev.target;
      if (d && d.classList && d.classList.contains("studio-h-piano")) {
        vista(d.open ? { vista: "piano", verifica: Number(d.dataset.verifica) } : { vista: "home" });
      }
    }, true);
    window.CalliopePagine = window.CalliopePagine || {};
    window.CalliopePagine.studio = { apri, chiudi };
    // Le pagine dei materiali solo dove ci sono (il telefono, con bordi.js)
    st.materiali = !!($("studio-materiali") && B());
    if (!st.materiali) return;
    $("studio-indietro").addEventListener("click", apriHome);
    $("studio-verifica").addEventListener("change", () => vista({ vista: "pagine", verifica: verificaScelta() || undefined }));
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
    if ($("studio-argomenti")) {
      $("studio-verifica").addEventListener("change", () => { st.arg = null; st.rinomina = null; metti($("studio-argomenti-esito"), ""); caricaArgomenti(); });
      $("studio-argomenti-elenco").addEventListener("click", suArgomenti);
      $("studio-argomenti-elenco").addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" && ev.target && ev.target.classList && ev.target.classList.contains("studio-rinomina")) {
          ev.preventDefault();
          const id = Number(String(ev.target.id).replace("studio-rinomina-", ""));
          const titolo = ev.target.value.trim();
          st.rinomina = null;
          if (titolo) caricaArgomenti({ azione: "rinomina", argomento: id, titolo }); else disegnaArgomenti();
        }
      });
      $("studio-argomenti-conferma").addEventListener("click", () => { if (!st.argInvio) caricaArgomenti({ azione: "conferma" }); });
    }
    // A pagina nascosta la fotocamera si spegne (batteria, e la luce della fotocamera)
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") chiudiCamera(); });
  }

  // Per le prove: le pagine in lista e lo stato
  window.CalliopeStudio = {
    esito: esitoHome,
    stato() {
      return { aperta: st.aperta, verifiche: st.verifiche.map((v) => v.id), invio: st.invio,
        home: home.dati ? { verifiche: (home.dati.verifiche || []).map((v) => v.id), sessione: home.dati.sessione,
          tocchi: !!home.dati.tocchi } : null, vista: vistaUltima,
        camera: !!st.flusso,
        argomenti: st.arg && Array.isArray(st.arg.argomenti) ? st.arg.argomenti.map((a) => ({ id: a.id, stato: a.stato, avvisi: (a.avvisi || []).slice() })) : [],
        pagine: st.pagine.map((p) => ({ id: p.id, tipo: p.tipo, angoli: p.angoli, intera: !!p.intera, avvisi: p.avvisi.slice(),
          nitidezza: p.nitidezza, kb: p.kb })) };
    },
    daFile,
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", avvia);
  else avvia();
})();
