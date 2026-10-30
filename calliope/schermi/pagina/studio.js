// Calliope · lo Studio sul telefono, pagina minima delle pagine dei materiali (29/10/2026, passo
// 4.2, issue #281, epic #251, decisione 0035). Si apre da Le mie cose › Studio quando lo Studio è
// acceso (in ombra solo per chi amministra, con la scritta «prova»): si sceglie la verifica, si
// fotografano le pagine con la fotocamera (più scatti di fila) o si prendono dalla galleria (anche
// un PDF), si guardano con i bordi trovati, si rifanno, si mettono in ordine (su e giù), si tolgono
// e si mandano. Dal 30/10 (passo 4.4, #283) sotto c'è la vista minima degli argomenti proposti
// della verifica scelta: «Tieni», «Togli», «Rinomina» e «Conferma gli argomenti»
// (POST /api/studio/argomenti). Dal 30/10 (passo 4.5, #284) la pagina si apre sulla home dello
// Studio (POST /api/studio/home), anche sul PC personale; le pagine dei materiali sono una vista
// sotto («Pagine»), solo sul telefono (la fotocamera e bordi.js). Dal 30/10 (passo 6, #246) le
// carte: «Ripassa» una carta per volta (la domanda; «Mostra la risposta»; «Non la sapevo», «Quasi»,
// «La sapevo» con la prossima volta scritta dal server) e «Le carte» con «Scrivi una carta»,
// «Correggi», «Togli» (POST /api/studio/carte, fuori dalla conversazione come gli argomenti).
// Dal 30/10 (passo 7, #247) la mappa concettuale: lo scheletro, la mia mappa, a memoria, in SVG e
// a elenco (equivalenti), il controllo del codice e il PDF (POST /api/studio/mappa).
// Domanda e risposta sono un dato: solo textContent, come i titoli.
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
  // La parola della padronanza → la classe del colore (passo 5, #245)
  function PAROLA_CLASSE(p) {
    return p === "la sai" ? "sai" : p === "quasi" ? "quasi" : p === "da studiare" ? "studiare" : "nonmisurata";
  }
  const PERCHE = { da_controllare: "non lo trovo nelle pagine che cita",
    pagina_con_istruzioni: "viene da una pagina con un messaggio per un assistente",
    titolo_ordine: "il titolo sembra un ordine o un annuncio" };
  const home = { dati: null, carica: false, domande: null, scelte: {}, esito: "", attesa: {} };
  // Le carte aperte su una verifica (passo 6, #246): {vid, modo: ripasso|elenco, dati, mostra,
  // modulo: {carta?, domanda, risposta, argomento} | null, attesa, esito}
  let carte = null;

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
    if (v.stato === "aperta" || v.stato === "bozza") art.append(sezioneCarte(v));
    // La mappa concettuale (passo 7, #247): lo scheletro, la mia mappa, a memoria
    if (v.stato === "aperta" || v.stato === "bozza") art.append(sezioneMappa(v));
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
        // La padronanza (passo 5, #245), solo se il server la manda («mostrata»): sempre la
        // parola, col colore come aiuto in più (blu, oro, arancio)
        if (x.parola) li.append(nodo("span", "studio-h-parola studio-h-p-" + PAROLA_CLASSE(x.parola), String(x.parola)));
        t.append(li);
      }
      art.append(nodo("h4", "studio-h-sotto", "Tappe"), t);
    }
    // Le lacune: gli argomenti sotto l'obiettivo, dal più debole, con la lezione successiva
    if (Array.isArray(v.lacune) && v.lacune.length) {
      const sez = nodo("section", "studio-h-gruppo studio-h-lacune");
      sez.append(nodo("h4", "studio-h-sotto", "Da rinforzare"));
      const ul = nodo("ul", "studio-h-elenco");
      for (const x of v.lacune) {
        const li = nodo("li", "studio-h-voce");
        const tx = nodo("div", "studio-testo");
        tx.append(nodo("b", null, String(x.titolo || "")),
          nodo("span", "studio-h-riga", " · " + String(x.parola || "") + " · " + String(x.lezione || "")));
        li.append(tx);
        ul.append(li);
      }
      sez.append(ul);
      art.append(sez);
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

  // ── le carte (30/10, passo 6, #246) ──
  function tastoCarte(testo, azione, dati, cls, etichetta) {
    const b = nodo("button", "tasto studio-h-tasto" + (cls ? " " + cls : ""), testo);
    b.type = "button";
    b.dataset.carte = azione;
    b.dataset.dati = JSON.stringify(dati || {});
    if (etichetta) b.setAttribute("aria-label", etichetta);
    b.disabled = !!(carte && carte.attesa);
    return b;
  }
  function sezioneCarte(v) {
    const sez = nodo("section", "studio-h-gruppo studio-h-carte");
    sez.dataset.verifica = String(v.id);
    sez.append(nodo("h4", "studio-h-sotto", "Carte"));
    const c = v.carte || {};
    const n = Number(c.da_ripassare) || 0, tot = Number(c.totali) || 0;
    sez.append(nodo("p", "studio-h-riga", !tot ? "Nessuna carta: scrivi le domande che vuoi ripassare." :
      n ? (n === 1 ? "Una carta da ripassare adesso." : n + " carte da ripassare adesso.") :
      "Nessuna carta da ripassare adesso" + (c.prossima ? ": la prossima " + String(c.prossima) + "." : ".")));
    const t = nodo("div", "studio-h-tasti");
    const aperta = carte && carte.vid === v.id;
    if (n) t.append(tastoCarte("Ripassa", "ripassa", { verifica: v.id }, "studio-h-primo"));
    t.append(tastoCarte(aperta && carte.modo === "elenco" ? "Chiudi le carte" : "Le carte",
      aperta && carte.modo === "elenco" ? "chiudi" : "elenco", { verifica: v.id }));
    sez.append(t);
    if (aperta) sez.append(carte.modo === "ripasso" ? pannelloRipasso() : pannelloElenco());
    if (aperta && carte.esito) {
      const es = nodo("p", "pagina-esito studio-c-esito", carte.esito);
      es.setAttribute("role", "status");
      sez.append(es);
    }
    return sez;
  }
  function cartaDi(id) {
    const d = carte && carte.dati;
    return d && Array.isArray(d.carte) ? d.carte.find((c) => c.id === id) || null : null;
  }
  function pannelloRipasso() {
    const p = nodo("div", "studio-c-ripasso");
    const d = carte.dati;
    if (!d) { p.append(nodo("p", "pagina-nota", "Un attimo…")); return p; }
    const coda = Array.isArray(d.da_ripassare) ? d.da_ripassare : [];
    const c = coda.length ? cartaDi(coda[0]) : null;
    if (!c) {
      p.append(nodo("p", "studio-h-riga", "Per adesso le carte sono finite."),
        tastoCarte("Chiudi", "chiudi", {}));
      return p;
    }
    const carta = nodo("div", "studio-c-carta");
    carta.dataset.carta = String(c.id);
    carta.append(nodo("span", "studio-h-etichetta", "Carta · " + coda.length + " da ripassare"),
      nodo("p", "studio-c-domanda", String(c.domanda || "")));
    if (c.argomento_titolo) carta.append(nodo("span", "studio-nota", String(c.argomento_titolo)));
    if (carte.mostra) {
      carta.append(nodo("p", "studio-c-risposta", String(c.risposta || "")));
      if (Array.isArray(c.pagine) && c.pagine.length) carta.append(nodo("span", "studio-nota", c.pagine.map(String).join(", ")));
    }
    p.append(carta);
    const t = nodo("div", "studio-h-tasti studio-c-esiti");
    if (!carte.mostra) {
      t.append(tastoCarte("Mostra la risposta", "mostra", { carta: c.id }, "studio-h-primo"));
    } else {
      const k = c.tasti || {};
      t.append(tastoCarte("Non la sapevo · " + String(k.non_sapevo || ""), "esito", { carta: c.id, esito: "non_sapevo" }),
        tastoCarte("Quasi · " + String(k.quasi || ""), "esito", { carta: c.id, esito: "quasi" }),
        tastoCarte("La sapevo · " + String(k.sapevo || ""), "esito", { carta: c.id, esito: "sapevo" }, "studio-h-primo"));
    }
    t.append(tastoCarte("Basta così", "chiudi", {}));
    p.append(t);
    return p;
  }
  const STATI_CARTA = { attiva: "", proposta: "proposta da me dalle pagine: controllala", tolta: "tolta dal ripasso" };
  // Gli avvisi di una carta proposta (passo 6, seconda parte, #246): il perché, in parole
  const AVVISI_CARTA = { da_controllare: "non la trovo nelle pagine che cita",
    pagina_con_istruzioni: "viene da una pagina con un messaggio per un assistente",
    testo_ordine: "sembra un ordine o un annuncio" };
  function pannelloElenco() {
    const p = nodo("div", "studio-c-elenco");
    const d = carte.dati;
    if (!d) { p.append(nodo("p", "pagina-nota", "Un attimo…")); return p; }
    const m = carte.modulo;
    if (m) p.append(moduloCarta(m, d));
    else p.append(tastoCarte("Scrivi una carta", "scrivi", {}, "studio-h-primo"));
    // Le carte proposte dal modello: nessuna entra nel ripasso senza la persona o il tutore
    const prop = (Array.isArray(d.carte) ? d.carte : []).filter((c) => c.stato === "proposta");
    if (prop.length) {
      const pulite = prop.filter((c) => !(c.avvisi || []).length).length;
      p.append(nodo("p", "studio-h-riga", (prop.length === 1 ? "Una carta proposta" : prop.length + " carte proposte") +
        " dalle pagine: entrano nel ripasso quando le confermi." +
        (pulite < prop.length ? " Quelle con un avviso le tieni una per una." : "")));
      if (pulite) p.append(tastoCarte("Conferma le carte proposte", "conferma", {}, "studio-h-primo"));
    }
    const ul = nodo("ul", "studio-h-elenco");
    for (const c of Array.isArray(d.carte) ? d.carte : []) {
      const li = nodo("li", "studio-h-voce studio-c-voce" + (c.stato === "tolta" ? " studio-tolto" : ""));
      const tx = nodo("div", "studio-testo");
      tx.append(nodo("b", null, String(c.domanda || "")), nodo("span", "studio-c-risp", String(c.risposta || "")));
      const info = [c.argomento_numero ? "argomento " + c.argomento_numero : "",
        STATI_CARTA[c.stato] || "", c.stato === "attiva" && !c.nel_piano ? "argomento fuori dal piano" : "",
        c.stato === "attiva" && c.nel_piano ? (c.da_ripassare ? "da ripassare" : c.fra ? "di nuovo " + c.fra : "") : "",
        (Array.isArray(c.pagine) && c.pagine.length) ? c.pagine.map(String).join(", ") : ""].filter(Boolean).join(" · ");
      if (info) tx.append(nodo("span", "studio-nota", info));
      for (const x of Array.isArray(c.avvisi) ? c.avvisi : []) tx.append(nodo("span", "studio-avviso", AVVISI_CARTA[x] || String(x)));
      const nome = "«" + String(c.domanda || "").slice(0, 60) + "»";
      const t = nodo("div", "studio-tasti");
      t.append(tastoCarte("Correggi", "correggi", { carta: c.id }, "", "Correggi " + nome));
      if (c.stato === "proposta") t.append(tastoCarte("Tieni", "rimetti", { carta: c.id }, "", "Tieni " + nome));
      t.append(c.stato === "tolta" ? tastoCarte("Rimetti", "rimetti", { carta: c.id }, "", "Rimetti " + nome)
        : tastoCarte("Togli", "togli", { carta: c.id }, "", "Togli " + nome));
      li.append(tx, t);
      ul.append(li);
    }
    if (ul.childNodes.length) p.append(ul);
    return p;
  }
  function moduloCarta(m, d) {
    const f = nodo("div", "studio-c-modulo");
    const campo = (nome, etichetta, max) => {
      const id = "studio-c-" + nome;
      const l = nodo("label", "studio-campo", etichetta);
      l.htmlFor = id;
      const t = document.createElement("textarea");
      t.id = id;
      t.rows = 2;
      t.maxLength = max;
      t.className = "studio-c-campo";
      t.dataset.campo = nome;
      t.value = String(m[nome] || "");
      return [l, t];
    };
    const mx = d.massimi || {};
    f.append(...campo("domanda", "Domanda", Number(mx.domanda) || 240), ...campo("risposta", "Risposta", Number(mx.risposta) || 240));
    const l = nodo("label", "studio-campo", "Argomento");
    l.htmlFor = "studio-c-argomento";
    const sel = document.createElement("select");
    sel.id = "studio-c-argomento";
    sel.className = "studio-scelta";
    sel.dataset.campo = "argomento";
    const o0 = nodo("option", null, "Nessuno");
    o0.value = "";
    sel.append(o0);
    for (const a of Array.isArray(d.argomenti) ? d.argomenti : []) {
      const o = nodo("option", null, String(a.numero) + ". " + String(a.titolo || ""));
      o.value = String(a.id);
      sel.append(o);
    }
    sel.value = m.argomento ? String(m.argomento) : "";
    f.append(l, sel);
    const t = nodo("div", "studio-h-tasti");
    t.append(tastoCarte("Salva", "salva", {}, "studio-h-primo"), tastoCarte("Annulla", "annulla", {}));
    f.append(t);
    return f;
  }
  async function caricaCarte(vid, dati) {
    if (!sch() || !sch().studioCarte) return;
    carte.attesa = true;
    disegnaHome();
    const r = await sch().studioCarte(Object.assign({ verifica: vid }, dati || {}));
    if (!carte || carte.vid !== vid) return;
    carte.attesa = false;
    if (!r.ok) {
      carte.esito = String(r.dati.errore || "Non ci sono riuscita: riprova tra poco.");
      disegnaHome();
      return false;
    }
    carte.dati = r.dati;
    carte.esito = r.dati.ultimo ? (r.dati.ultimo.esito === "non_sapevo" ? "La rivedi " : "La prossima volta: ") + String(r.dati.ultimo.fra || "") + "." : "";
    disegnaHome();
    return true;
  }
  async function suCarte(b) {
    const art = b.closest("[data-verifica]");
    const vid = Number(art && art.dataset.verifica);
    let dati = {};
    try { dati = JSON.parse(b.dataset.dati || "{}"); } catch (e) { return; }
    const az = b.dataset.carte;
    if (az === "ripassa" || az === "elenco") {
      carte = { vid, modo: az === "ripassa" ? "ripasso" : "elenco", dati: null, mostra: false, modulo: null, attesa: false, esito: "" };
      vista({ vista: "carte", verifica: vid });
      await caricaCarte(vid);
      return;
    }
    if (!carte || carte.vid !== vid) return;
    if (az === "chiudi") { carte = null; vista({ vista: "home" }); caricaHome(); return; }
    if (az === "mostra") { carte.mostra = true; disegnaHome(); return; }
    if (az === "esito") {
      carte.mostra = false;
      await caricaCarte(vid, { azione: "esito", carta: dati.carta, esito: dati.esito });
      return;
    }
    if (az === "scrivi") { carte.modulo = { domanda: "", risposta: "", argomento: null }; disegnaHome(); return; }
    if (az === "correggi") {
      const c = cartaDi(dati.carta);
      if (!c) return;
      carte.modulo = { carta: c.id, domanda: c.domanda, risposta: c.risposta, argomento: c.argomento };
      disegnaHome();
      return;
    }
    if (az === "annulla") { carte.modulo = null; disegnaHome(); return; }
    if (az === "salva") {
      const m = carte.modulo;
      if (!m) return;
      const domanda = String(m.domanda || "").trim(), risposta = String(m.risposta || "").trim();
      if (!domanda || !risposta) { carte.esito = "Servono la domanda e la risposta."; disegnaHome(); return; }
      const corpo = m.carta ? { azione: "correggi", carta: m.carta, domanda, risposta, argomento: m.argomento || null }
        : { azione: "scrivi", domanda, risposta, argomento: m.argomento || null };
      if (await caricaCarte(vid, corpo)) { carte.modulo = null; carte.esito = m.carta ? "Corretta." : "Scritta: è fra quelle da ripassare."; disegnaHome(); }
      return;
    }
    if (az === "togli" || az === "rimetti") await caricaCarte(vid, { azione: az, carta: dati.carta });
    if (az === "conferma" && await caricaCarte(vid, { azione: "conferma" })) {
      const r = carte.dati.confermate || {};
      carte.esito = (Number(r.confermate) === 1 ? "Una carta confermata" : (Number(r.confermate) || 0) + " carte confermate") +
        (Number(r.da_decidere) ? "; " + Number(r.da_decidere) + " con un avviso restano da decidere." : ".");
      disegnaHome();
    }
  }
  function suCampoCarte(ev) {
    const t = ev.target;
    if (!t || !t.dataset || !t.dataset.campo || !carte || !carte.modulo) return;
    const k = t.dataset.campo;
    carte.modulo[k] = k === "argomento" ? (Number(t.value) || null) : t.value;
  }

  // ── la mappa concettuale (30/10, passo 7, #247) ──
  // Lo scheletro (proposto finché non lo si conferma), la mia mappa («con il libro»), a memoria;
  // la mappa in SVG e l'elenco, equivalenti: tutto si fa anche dall'elenco, niente solo
  // trascinando. Il testo dei concetti è un dato: textContent e testo SVG, mai HTML. Il controllo
  // è del server (il codice), mai del modello. POST /api/studio/mappa, fuori dalla conversazione.
  // {vid, quale: scheletro|mia|memoria, vista: mappa|elenco, dati, scelto, modulo, bozze, attesa,
  // esito, ricomincia, aiuto}
  let mappa = null;
  const NS = "http://www.w3.org/2000/svg";
  // «chiave» e «da_rivedere»: i concetti della mappa libera dopo «Ho finito» (passo 7c, #328)
  const ESITI_M = { giusta: "giusta", sbagliata: "da rivedere", vuota: "da riempire",
    chiave: "concetto chiave", da_rivedere: "concetto chiave col nome da rivedere" };
  const INDICATORI_M = { parti: ["parti staccate", "meno"], isolati: ["concetti senza collegamenti", "meno"],
    verbi_vuoti: ["collegamenti con un verbo vuoto", "meno"], lunghi: ["concetti lunghi come frasi", "meno"],
    profondita: ["livelli dal centro", "più"], trasversali: ["collegamenti fra rami diversi", "più"],
    copertura: ["concetti chiave trovati (%)", "più"] };
  const RISPETTO_M = { meglio: "meglio della volta scorsa", uguale: "come la volta scorsa", peggio: "da curare rispetto alla volta scorsa" };
  const AVVISI_M = { da_controllare: "non lo trovo nelle pagine che cita",
    pagina_con_istruzioni: "viene da una pagina con un messaggio per un assistente",
    testo_ordine: "sembra un ordine o un annuncio" };
  const AIUTI_M = { tanto: "Tanto aiuto", medio: "Aiuto medio", poco: "Poco aiuto" };
  const NOMI_M = { scheletro: "Lo scheletro", mia: "La mia mappa", memoria: "A memoria", libera: "Da zero" };

  function tastoMappa(testo, azione, dati, cls, etichetta) {
    const b = nodo("button", "tasto studio-h-tasto" + (cls ? " " + cls : ""), testo);
    b.type = "button";
    b.dataset.mappa = azione;
    b.dataset.dati = JSON.stringify(dati || {});
    if (etichetta) b.setAttribute("aria-label", etichetta);
    b.disabled = !!(mappa && mappa.attesa);
    return b;
  }
  // «1 giusta», «2 giuste»
  function nn(n, uno, tanti) { n = Number(n) || 0; return n + " " + (n === 1 ? uno : tanti); }
  function rigaMappa(v) {
    const c = v.mappa || {};
    const s = c.scheletro, mia = c.mia;
    if (!s) return "Nessuna mappa: lo scheletro lo puoi scrivere tu.";
    if (s.stato !== "confermata") return "Lo scheletro, " + Number(s.concetti || 0) + " concetti, aspetta la conferma.";
    if (!mia) return "Lo scheletro è pronto: fai la tua mappa.";
    const u = mia.ultimo;
    return "La tua mappa: " + Number(mia.concetti || 0) + " concetti" +
      (Number(mia.caselle_vuote) ? ", " + Number(mia.caselle_vuote) + " caselle da riempire" : "") +
      (u ? " · all'ultimo controllo " + nn(u.giusta, "giusta", "giuste") : " · non ancora controllata") + ".";
  }
  function sezioneMappa(v) {
    const sez = nodo("section", "studio-h-gruppo studio-h-mappa");
    sez.dataset.verifica = String(v.id);
    sez.append(nodo("h4", "studio-h-sotto", "Mappa"), nodo("p", "studio-h-riga", rigaMappa(v)));
    const aperta = mappa && mappa.vid === v.id;
    const t = nodo("div", "studio-h-tasti");
    t.append(tastoMappa(aperta ? "Chiudi la mappa" : "La mappa", aperta ? "chiudi" : "apri", { verifica: v.id }));
    sez.append(t);
    if (aperta) sez.append(pannelloMappa());
    if (aperta && mappa.esito) {
      const es = nodo("p", "pagina-esito studio-m-stato", mappa.esito);
      es.setAttribute("role", "status");
      sez.append(es);
    }
    return sez;
  }
  function mappaCorrente() { return mappa && mappa.dati ? mappa.dati[mappa.quale] || null : null; }
  function puoCambiare(m) {
    const d = mappa.dati;
    return !!(m && d && d.puo && (m.tipo === "scheletro" ? d.puo.scheletro : m.tipo === "libera" ? d.puo.libera : d.puo.mia));
  }
  function nodoDi(m, id) { return (m && Array.isArray(m.nodi) ? m.nodi.find((n) => n.id === id) : null) || null; }
  function testoNodo(n) { return String(n.testo || "") || (n.casella ? "…" : ""); }
  function chiMappa(m) {
    const d = mappa.dati;
    if (m.tipo === "scheletro") {
      return (m.origine === "modello" ? "Lo scheletro · di Calliope, dai materiali" : "Lo scheletro · scritto a mano") +
        (m.stato === "confermata" ? " · confermato" : " · da confermare");
    }
    const di = d.verifica && d.verifica.di ? String(d.verifica.di) : "";
    if (m.tipo === "libera") {
      return (di ? "La mappa da zero di " + di : "La tua mappa da zero") + (Number(m.giro) ? " · giro " + (Number(m.giro) + 1) : "") +
        (m.controllata ? " · finita " + dataDetta(String(m.controllata).slice(0, 10)) : " · in corso");
    }
    const quando = m.controllata ? " · controllata " + dataDetta(String(m.controllata).slice(0, 10)) : " · non ancora controllata";
    return (m.tipo === "studente" ? (di ? "La mappa di " + di : "La tua mappa") + " · con il libro"
      : "A memoria" + (di ? " · di " + di : "")) + quando;
  }

  function pannelloMappa() {
    const p = nodo("div", "studio-m");
    const d = mappa.dati;
    if (!d) { p.append(nodo("p", "pagina-nota", "Un attimo…")); return p; }
    const sch_ = d.scheletro;
    const pronto = sch_ && sch_.stato === "confermata";
    // Con la mappa a memoria aperta lo scheletro e la mia mappa arrivano senza testi e le loro
    // schede non si vedono fino a «Controlla» (revisione della PR #326)
    if (d.a_memoria) mappa.quale = "memoria";
    // La mappa libera aperta (passo 7c, #328): lo scheletro e le altre mappe tornano dopo «Ho finito»
    if (d.a_libera) mappa.quale = "libera";
    const schede = nodo("div", "studio-m-schede");
    schede.setAttribute("role", "group");
    schede.setAttribute("aria-label", "Quale mappa");
    for (const k of ["scheletro", "mia", "memoria", "libera"]) {
      if (k === "libera") { if (!d.libera && !(d.puo && d.puo.libera)) continue; }
      else if (k !== "scheletro" && !d[k] && !(pronto && d.puo && d.puo.mia)) continue;
      if (d.a_memoria && k !== "memoria") continue;
      if (d.a_libera && k !== "libera") continue;
      const b = tastoMappa(NOMI_M[k], "quale", { quale: k }, "studio-h-chip");
      b.setAttribute("aria-pressed", String(mappa.quale === k));
      schede.append(b);
    }
    p.append(schede);
    if (d.a_memoria) p.append(nodo("p", "studio-h-nota", "Lo scheletro e la tua mappa tornano dopo «Controlla»."));
    if (d.a_libera) p.append(nodo("p", "studio-h-nota", "Lo scheletro e le altre mappe tornano dopo «Ho finito»."));
    const m = mappaCorrente();
    if (!m && mappa.quale === "libera") {
      p.append(nodo("p", "studio-h-riga", "Fai la mappa da solo, dopo aver studiato: si parte dal concetto centrale, senza lo scheletro. Quando hai finito, il confronto ti dice se mancano concetti chiave e come migliorare il metodo."));
      if (d.puo && d.puo.libera) p.append(tastoMappa("Fai la tua mappa da zero", "libera", {}, "studio-h-primo"));
      return p;
    }
    if (!m) {
      if (mappa.quale === "scheletro") {
        p.append(nodo("p", "studio-h-riga", "Lo scheletro non c'è ancora: i concetti principali e come si collegano, ognuno con le sue pagine."));
        if (d.puo && d.puo.scheletro) p.append(tastoMappa("Scrivi lo scheletro", "scheletro", {}, "studio-h-primo"));
        return p;
      }
      if (!pronto) { p.append(nodo("p", "studio-h-riga", "Prima serve lo scheletro confermato.")); return p; }
      p.append(nodo("p", "studio-h-riga", mappa.quale === "mia"
        ? "La tua mappa parte dallo scheletro: alcune caselle sono vuote e dicono la pagina dove cercare; poi la allunghi con concetti tuoi."
        : "Rifai la mappa senza guardare: niente pagine, le caselle vuote da riempire a memoria."));
      p.append(sceltaAiuto(d));
      p.append(tastoMappa(mappa.quale === "mia" ? "Parti da qui: fai la tua" : "Rifai la mappa a memoria", "inizia",
        { tipo: mappa.quale === "mia" ? "studente" : "memoria" }, "studio-h-primo"));
      return p;
    }
    const puo = puoCambiare(m);
    // A memoria, dopo «Controlla», non si cambia più: si riparte con «Rifai» (seconda revisione
    // della PR #326)
    const chiusa = (m.tipo === "memoria" || m.tipo === "libera") && m.stato === "controllata";
    const modifica = puo && !chiusa;
    p.append(nodo("p", "studio-h-riga", chiMappa(m)));
    if (chiusa && puo) p.append(nodo("p", "studio-h-nota", m.tipo === "libera" ? "Finita: per rifarla da zero, «Rifai»." : "Controllata: per rifarla a memoria, «Rifai»."));
    if (m.tipo === "libera") p.append(...pannelloLibera(m, d, modifica));
    const daDecidere = (m.nodi || []).filter((n) => n.stato === "proposto").length + (m.collegamenti || []).filter((c) => c.stato === "proposto").length;
    if (m.tipo === "scheletro" && m.stato === "confermata" && d.puo && !d.puo.scheletro) {
      p.append(nodo("p", "studio-h-riga", "Lo scheletro è confermato e ci sono le mappe fatte da qui: per cambiarlo va riaperto, e la tua mappa e quella a memoria si rifanno dopo la nuova conferma."));
    }
    if (m.tipo === "scheletro" && daDecidere) p.append(nodo("p", "studio-avviso", daDecidere === 1 ? "Una voce proposta con un avviso: tienila o toglila." : daDecidere + " voci proposte con un avviso: tienile o toglile una per una."));
    // Mappa / Elenco: due viste della stessa cosa
    const viste = nodo("div", "studio-m-schede");
    viste.setAttribute("role", "group");
    viste.setAttribute("aria-label", "Come vederla");
    for (const [k, t] of [["mappa", "Mappa"], ["elenco", "Elenco"]]) {
      const b = tastoMappa(t, "vista", { vista: k }, "studio-h-chip");
      b.setAttribute("aria-pressed", String(mappa.vista === k));
      viste.append(b);
    }
    p.append(viste);
    if (Array.isArray(m.parole) && m.parole.length && m.tipo !== "scheletro") {
      p.append(nodo("p", "studio-m-parole", "Le parole da mettere (una è di troppo): " + m.parole.map(String).join(" · ")));
      const dl = document.createElement("datalist");
      dl.id = "studio-m-parole-" + m.id;
      for (const w of m.parole) { const o = document.createElement("option"); o.value = String(w); dl.append(o); }
      p.append(dl);
    }
    if (mappa.vista === "mappa") {
      p.append(telaMappa(m, modifica));
      const n = nodoDi(m, mappa.scelto);
      if (n) p.append(pannelloNodo(m, n, modifica));
      else p.append(nodo("p", "studio-h-nota", "Tocca un concetto per vederlo e cambiarlo; la stessa mappa è anche nell'elenco."));
    } else {
      p.append(elencoMappa(m, modifica));
    }
    if (mappa.modulo) p.append(moduloMappa(m));
    const t = nodo("div", "studio-h-tasti");
    if (modifica && !mappa.modulo) {
      t.append(tastoMappa("+ Concetto", "nuovo", {}, ""), tastoMappa("Collega", "collega", {}, ""));
      if (m.tipo === "scheletro" && m.stato !== "confermata") t.append(tastoMappa("Conferma lo scheletro", "conferma", {}, "studio-h-primo"));
      if (m.tipo === "libera") t.append(tastoMappa("Un indizio", "indizio", {}, "", "Un indizio: la pagina di un concetto chiave che manca"), tastoMappa("Ho finito", "finito", {}, "studio-h-primo", "Ho finito: confronta la mappa con lo scheletro"));
      else if (m.tipo !== "scheletro") t.append(tastoMappa("Controlla", "controlla", {}, "studio-h-primo"));
      t.append(tastoMappa("Riordina", "riordina", {}, ""));
    }
    if (m.tipo === "scheletro" && m.stato === "confermata" && d.puo && d.puo.riapri && !mappa.modulo) {
      t.append(mappa.riapri ? tastoMappa("Sì, riapri: le mappe ripartono", "riapri", {}, "", "Riapri lo scheletro: la mia mappa e quella a memoria si rifanno dopo la conferma")
        : tastoMappa("Riapri lo scheletro", "chiedi_riapri", {}, ""));
    }
    if ((m.tipo === "studente" || m.tipo === "libera") && (m.nodi || []).length) t.append(tastoMappa("Scarica PDF", "pdf", { tipo: m.tipo }, ""));
    if (puo && m.tipo === "libera" && chiusa) t.append(tastoMappa("Rifai", "rifai", {}, "", "Rifai la mappa da zero"));
    if (puo && m.tipo === "memoria") {
      t.append(tastoMappa("Rifai", "rifai", {}, ""));
      const c = m.conti || {};
      if (Number(c.sbagliata) + Number(c.vuota) > 0) t.append(tastoMappa("Fanne carte", "carte", {}, "", "Fai una carta per ogni casella da rivedere"));
    }
    if (puo && m.tipo === "studente") {
      t.append(mappa.ricomincia ? tastoMappa("Sì, ricomincia da capo", "rifai", {}, "", "Ricomincia la mappa dallo scheletro: i tuoi concetti vanno via")
        : tastoMappa("Ricomincia", "ricomincia", {}, ""));
    }
    if (t.childNodes.length) p.append(t);
    const c = m.conti;
    if (c && m.tipo !== "scheletro") {
      const r = [nn(c.giusta, "giusta", "giuste"), nn(c.sbagliata, "da rivedere", "da rivedere"), nn(c.vuota, "da riempire", "da riempire")];
      if (Number(c.mancanti)) r.push(nn(c.mancanti, "collegamento mancante", "collegamenti mancanti"));
      if (Number(c.in_piu)) r.push(nn(c.in_piu, "collegamento non nel quadro: controllalo sul libro", "collegamenti non nel quadro: controllali sul libro"));
      if (Number(c.verso_diverso)) r.push(nn(c.verso_diverso, "freccia col verso diverso", "frecce col verso diverso"));
      if (Number(c.verbo_diverso)) r.push(nn(c.verbo_diverso, "con un verbo diverso", "con un verbo diverso"));
      p.append(nodo("p", "studio-h-riga studio-m-conti", "L'ultimo controllo: " + r.join(", ") + "."));
    }
    return p;
  }
  // La mappa libera (passo 7c, #328): gli indizi chiesti mentre è aperta (la pagina, il testo solo
  // con «Mostra»), e dopo «Ho finito» il confronto del codice e gli indicatori del metodo, con la
  // volta scorsa. Il testo dei concetti dello scheletro arriva solo se mostrato (o già trovato)
  function rigaChiave(k, puo) {
    const li = nodo("li", "studio-m-voce");
    const pag = Array.isArray(k.pagine) && k.pagine.length ? k.pagine.map(String).join(", ") : "";
    if (k.esito === "presente") {
      li.append(nodo("span", "studio-m-esito giusta", "C'è"), nodo("b", null, String(k.testo || "")));
    } else {
      li.append(nodo("span", "studio-m-esito manca", k.esito === "diverso" ? "C'è con un nome diverso: da rivedere" + (pag ? " (" + pag + ")" : "")
        : "Ti manca un concetto chiave" + (pag ? " di " + pag : "")));
      if (k.testo) li.append(nodo("b", null, String(k.testo)));
      else if (puo) li.append(tastoMappa("Mostra", "mostra", { concetto: k.n }, "studio-h-chip", "Mostra il concetto chiave" + (pag ? " di " + pag : "")));
    }
    return li;
  }
  function pannelloLibera(m, d, modifica) {
    const out = [];
    const puo = puoCambiare(m);
    if (m.stato === "aperta") {
      const ind = Array.isArray(m.indizi) ? m.indizi : [];
      if (ind.length) {
        const ul = nodo("ul", "studio-m-elenco");
        ul.setAttribute("aria-label", "Gli indizi");
        for (const k of ind) ul.append(rigaChiave({ n: k.n, esito: "mancante", pagine: k.pagine, testo: k.testo }, modifica));
        out.push(ul);
      }
      return out;
    }
    const c = m.confronto;
    if (!c) {
      out.push(nodo("p", "studio-h-riga", "Lo scheletro per il confronto non c'è ancora: qui sotto come è venuta la tua mappa."));
    } else {
      const k = c.conti || {};
      out.push(nodo("p", "studio-h-riga studio-m-conti", "Concetti chiave: " + (Number(k.presente) + Number(k.diverso)) + " su " + Number(k.chiave) +
        (Number(k.diverso) ? ", " + nn(k.diverso, "col nome da rivedere", "col nome da rivedere") : "") +
        (Number(k.coll_mancanti) ? "; " + nn(k.coll_mancanti, "collegamento dello scheletro manca fra i tuoi concetti", "collegamenti dello scheletro mancano fra i tuoi concetti") : "") + "."));
      if (c.riferimento === "proposto") out.push(nodo("p", "studio-h-nota", "Rispetto alla mappa proposta, non ancora controllata."));
      const ul = nodo("ul", "studio-m-elenco");
      ul.setAttribute("aria-label", "I concetti chiave");
      for (const x of Array.isArray(c.chiave) ? c.chiave : []) ul.append(rigaChiave(x, puo));
      out.push(ul);
    }
    const ind = m.indicatori || {};
    const ri = m.rispetto || {};
    const ul = nodo("ul", "studio-m-elenco studio-m-indicatori");
    ul.setAttribute("aria-label", "Come è fatta la tua mappa");
    for (const key of Object.keys(INDICATORI_M)) {
      if (ind[key] === null || ind[key] === undefined) continue;
      ul.append(nodo("li", null, INDICATORI_M[key][0] + ": " + Number(ind[key]) + (ri[key] ? " · " + RISPETTO_M[ri[key]] : "")));
    }
    out.push(nodo("h5", "studio-h-sotto", "Il metodo" + (m.prima ? ", rispetto alla volta scorsa" : "")), ul);
    if (d.consigli && !(d.verifica && d.verifica.di)) out.push(nodo("p", "studio-h-nota", "Parliamone: chiedimelo a voce o scrivendo («parliamo della mia mappa»), e ti dico cosa va bene e come fare mappe migliori."));
    return out;
  }
  function sceltaAiuto(d) {
    const f = nodo("fieldset", "studio-h-scelte");
    f.append(nodo("legend", null, "Quanto aiuto?"));
    const scelto = mappa.aiuto || d.aiuto || "medio";
    for (const k of ["tanto", "medio", "poco"]) {
      const b = tastoMappa(AIUTI_M[k] + " · " + Number((d.aiuti || {})[k] || 0) + " caselle", "aiuto", { aiuto: k }, "studio-h-chip");
      b.setAttribute("aria-pressed", String(scelto === k));
      f.append(b);
    }
    return f;
  }

  // La mappa disegnata: un riquadro per concetto (il testo in <text>, a righe), le frecce col
  // verbo. Sul telefono in verticale. Un concetto si sceglie toccandolo o con Invio; si sposta
  // trascinandolo o con le frecce del pannello
  function righeDi(t, n) {
    const out = [];
    let cur = "";
    for (const w of String(t).split(/\s+/)) {
      if (!w) continue;
      if ((cur + " " + w).trim().length <= n || !cur) cur = (cur + " " + w).trim();
      else { out.push(cur); cur = w; }
    }
    if (cur) out.push(cur);
    if (out.length > 3) { out.length = 3; out[2] = out[2].slice(0, n - 1) + "…"; }
    return out.length ? out.map((x) => x.length > n + 2 ? x.slice(0, n) + "…" : x) : [""];
  }
  function svg(tag, attr) {
    const e = document.createElementNS(NS, tag);
    for (const k in attr || {}) e.setAttribute(k, String(attr[k]));
    return e;
  }
  function telaMappa(m, puo) {
    const box = $("studio-home");
    const stretta = !box || box.clientWidth < 640;
    const W = stretta ? 600 : 1000, H = stretta ? 840 : 620;
    const s = svg("svg", { viewBox: "0 0 " + W + " " + H, class: "studio-m-tela", role: "group" });
    s.setAttribute("aria-label", "La mappa: " + (m.nodi || []).length + " concetti e " + (m.collegamenti || []).length +
      " collegamenti. La stessa cosa è nell'elenco.");
    s.dataset.w = String(W);
    s.dataset.h = String(H);
    const defs = svg("defs");
    const mk = svg("marker", { id: "studio-m-punta", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 9, markerHeight: 9, orient: "auto-start-reverse" });
    mk.append(svg("path", { d: "M0,0 L10,5 L0,10 z", class: "studio-m-punta" }));
    defs.append(mk);
    s.append(defs);
    const nodi = Array.isArray(m.nodi) ? m.nodi : [];
    const pos = {};
    const bw = stretta ? 210 : 200, nc = stretta ? 15 : 15;
    for (const n of nodi) {
      const r = righeDi(testoNodo(n), nc);
      const h = Math.max(78, r.length * 27 + 26);
      const x = W * 0.12 + Math.max(0, Math.min(1, Number(n.x) || 0.5)) * W * 0.76;
      const y = H * 0.08 + Math.max(0, Math.min(1, Number(n.y) || 0.5)) * H * 0.84;
      pos[n.id] = { x, y, w: bw, h, r };
    }
    const bordo = (a, b) => {
      const dx = b.x - a.x, dy = b.y - a.y;
      if (!dx && !dy) return [a.x, a.y];
      const k = Math.min(dx ? (a.w / 2 + 4) / Math.abs(dx) : Infinity, dy ? (a.h / 2 + 4) / Math.abs(dy) : Infinity);
      return [a.x + dx * k, a.y + dy * k];
    };
    for (const c of Array.isArray(m.collegamenti) ? m.collegamenti : []) {
      const a = pos[c.da], b = pos[c.a];
      if (!a || !b) continue;
      const [x1, y1] = bordo(a, b), [x2, y2] = bordo(b, a);
      const l = svg("line", { x1, y1, x2, y2, "marker-end": "url(#studio-m-punta)" });
      if (c.esito) l.setAttribute("class", String(c.esito));
      s.append(l);
      const t = svg("text", { x: (x1 + x2) / 2, y: (y1 + y2) / 2 + 6, "text-anchor": "middle", class: "studio-m-verbo" });
      t.textContent = String(c.verbo || "").slice(0, 30);
      s.append(t);
    }
    for (const n of nodi) {
      const q = pos[n.id];
      const g = svg("g", { class: "studio-m-nodo" + (n.suo && (m.tipo === "studente" || m.tipo === "memoria") ? " suo" : "") + (n.casella ? " casella" : "") +
        (n.stato === "proposto" ? " proposto" : "") + (n.esito ? " " + n.esito : "") + (mappa.scelto === n.id ? " scelto" : ""),
        tabindex: 0, role: "button", transform: "translate(" + q.x + "," + q.y + ")" });
      g.dataset.nodo = String(n.id);
      g.setAttribute("aria-label", (n.casella && !n.testo ? "Casella vuota" : "Concetto: " + String(n.testo || "")) +
        (n.esito ? ", " + (ESITI_M[n.esito] || n.esito) : ""));
      g.setAttribute("aria-pressed", String(mappa.scelto === n.id));
      g.append(svg("rect", { x: -q.w / 2, y: -q.h / 2, width: q.w, height: q.h, rx: 14 }));
      const t = svg("text", { "text-anchor": "middle" });
      q.r.forEach((riga, i) => {
        const sp = svg("tspan", { x: 0, y: -q.h / 2 + 30 + i * 27 + (q.h - (q.r.length * 27 + 26)) / 2 });
        sp.textContent = riga;
        t.append(sp);
      });
      g.append(t);
      s.append(g);
    }
    s.dataset.cambia = puo ? "1" : "";
    return s;
  }

  function pannelloNodo(m, n, puo) {
    const p = nodo("div", "studio-m-pannello");
    p.dataset.nodo = String(n.id);
    p.append(nodo("b", null, n.casella && !n.testo ? "Casella vuota" : String(n.testo || "")));
    p.append(...infoNodo(m, n));
    if (puo && n.casella) p.append(...campoCasella(m, n));
    const t = nodo("div", "studio-h-tasti");
    t.append(...tastiNodo(m, n, puo));
    if (puo) {
      for (const [f, dx, dy, et] of [["←", -0.06, 0, "Sposta a sinistra"], ["↑", 0, -0.06, "Sposta in su"], ["↓", 0, 0.06, "Sposta in giù"], ["→", 0.06, 0, "Sposta a destra"]]) {
        t.append(tastoMappa(f, "sposta", { nodo: n.id, x: Math.max(0, Math.min(1, (Number(n.x) || 0.5) + dx)), y: Math.max(0, Math.min(1, (Number(n.y) || 0.5) + dy)) }, "studio-h-chip", et));
      }
    }
    p.append(t);
    const ul = collegamentiDi(m, n, puo);
    if (ul) p.append(ul);
    return p;
  }
  function infoNodo(m, n) {
    const out = [];
    const info = [n.stato === "proposto" ? "proposto" : "", n.suo && (m.tipo === "studente" || m.tipo === "memoria") ? "concetto tuo" : "",
      (Array.isArray(n.pagine) && n.pagine.length) ? (n.casella ? "cerca a " : "") + n.pagine.map(String).join(", ") : ""].filter(Boolean).join(" · ");
    if (info) out.push(nodo("span", "studio-nota", info));
    if (n.esito) out.push(nodo("span", "studio-m-esito " + String(n.esito), ESITI_M[n.esito] || String(n.esito)));
    if (Array.isArray(n.manca)) out.push(nodo("span", "studio-m-esito manca", "Manca un collegamento da qui" + (n.manca.length ? ": guarda a " + n.manca.map(String).join(", ") : "") + "."));
    for (const x of Array.isArray(n.avvisi) ? n.avvisi : []) out.push(nodo("span", "studio-avviso", AVVISI_M[x] || String(x)));
    return out;
  }
  function campoCasella(m, n) {
    const id = "studio-m-casella-" + n.id;
    const l = nodo("label", "studio-campo", "Cosa va qui?");
    l.htmlFor = id;
    const i = document.createElement("input");
    i.id = id;
    i.type = "text";
    i.className = "studio-m-campo";
    i.maxLength = Number(((mappa.dati || {}).massimi || {}).testo) || 60;
    i.dataset.casella = String(n.id);
    i.setAttribute("list", "studio-m-parole-" + m.id);
    i.value = mappa.bozze[n.id] !== undefined ? mappa.bozze[n.id] : String(n.testo || "");
    return [l, i, tastoMappa("Metti", "riempi", { nodo: n.id }, "", "Metti la parola nella casella")];
  }
  function tastiNodo(m, n, puo) {
    const out = [];
    if (!puo) return out;
    const nome = "«" + String(n.testo || "casella").slice(0, 40) + "»";
    if (m.tipo === "scheletro" || (n.suo && !n.casella)) {
      out.push(tastoMappa("Cambia", "cambia", { nodo: n.id }, "", "Cambia " + nome));
      out.push(tastoMappa("Togli", "togli_nodo", { nodo: n.id }, "", "Togli " + nome));
    }
    if (m.tipo === "scheletro" && n.stato === "proposto") out.push(tastoMappa("Tieni", "tieni", { nodo: n.id }, "", "Tieni " + nome));
    out.push(tastoMappa("Collega da qui", "collega", { da: n.id }, "", "Collega " + nome + " a un altro concetto"));
    return out;
  }
  function collegamentiDi(m, n, puo) {
    const coll = (Array.isArray(m.collegamenti) ? m.collegamenti : []).filter((c) => c.da === n.id);
    if (!coll.length) return null;
    const ul = nodo("ul", "studio-m-coll");
    for (const c of coll) {
      const altro = nodoDi(m, c.a);
      const li = nodo("li", null);
      const tx = nodo("span", null, "→ " + String(c.verbo || "") + " → " + (altro ? testoNodo(altro) || "…" : "…"));
      li.append(tx);
      if (c.esito === "in_piu") li.append(nodo("span", "studio-m-esito manca", "non è nel quadro: controlla" + (Array.isArray(c.guarda) && c.guarda.length ? " a " + c.guarda.map(String).join(", ") : " sul libro")));
      if (c.esito === "verbo_diverso") li.append(nodo("span", "studio-m-esito manca", "verbo diverso: controlla"));
      if (c.esito === "verso_diverso") li.append(nodo("span", "studio-m-esito manca", "verso diverso: da rivedere"));
      if (c.stato === "proposto") li.append(nodo("span", "studio-avviso", "proposto" + ((c.avvisi || []).length ? ": " + c.avvisi.map((x) => AVVISI_M[x] || String(x)).join("; ") : "")));
      if (puo) {
        const t = nodo("span", "studio-h-tasti");
        const nome = "«" + String(c.verbo || "").slice(0, 30) + "»";
        t.append(tastoMappa("Cambia", "cambia_coll", { collegamento: c.id }, "studio-h-chip", "Cambia il collegamento " + nome));
        if (m.tipo === "scheletro" && c.stato === "proposto") t.append(tastoMappa("Tieni", "tieni", { collegamento: c.id }, "studio-h-chip", "Tieni il collegamento " + nome));
        t.append(tastoMappa("Togli", "togli_collegamento", { collegamento: c.id }, "studio-h-chip", "Togli il collegamento " + nome));
        li.append(t);
      }
      ul.append(li);
    }
    return ul;
  }
  function elencoMappa(m, puo) {
    const ol = nodo("ol", "studio-m-elenco");
    ol.setAttribute("aria-label", "La mappa a elenco");
    for (const n of Array.isArray(m.nodi) ? m.nodi : []) {
      const li = nodo("li", "studio-m-voce");
      li.dataset.nodo = String(n.id);
      li.append(nodo("b", null, n.casella && !n.testo ? "Casella vuota" : String(n.testo || "")), ...infoNodo(m, n));
      if (puo && n.casella) li.append(...campoCasella(m, n));
      const t = nodo("div", "studio-h-tasti");
      t.append(...tastiNodo(m, n, puo));
      if (t.childNodes.length) li.append(t);
      const ul = collegamentiDi(m, n, puo);
      if (ul) li.append(ul);
      ol.append(li);
    }
    if (!ol.childNodes.length) ol.append(nodo("li", "studio-h-riga", "Ancora nessun concetto: aggiungine uno con «+ Concetto»."));
    return ol;
  }
  function moduloMappa(m) {
    const f = nodo("div", "studio-c-modulo studio-m-pannello");
    const mo = mappa.modulo;
    const d = mappa.dati || {};
    const mx = d.massimi || {};
    const scelta = (nome, etichetta, voci, valore) => {
      const id = "studio-m-" + nome;
      const l = nodo("label", "studio-campo", etichetta);
      l.htmlFor = id;
      const s = document.createElement("select");
      s.id = id;
      s.dataset.mcampo = nome;
      for (const [v, t] of voci) { const o = nodo("option", null, t); o.value = String(v); s.append(o); }
      s.value = valore === null || valore === undefined ? "" : String(valore);
      return [l, s];
    };
    const testo = (nome, etichetta, max) => {
      const id = "studio-m-" + nome;
      const l = nodo("label", "studio-campo", etichetta);
      l.htmlFor = id;
      const i = document.createElement("input");
      i.id = id;
      i.type = "text";
      i.className = "studio-m-campo";
      i.maxLength = max;
      i.dataset.mcampo = nome;
      i.value = String(mo[nome] || "");
      return [l, i];
    };
    if (mo.tipo === "nodo") {
      f.append(...testo("testo", mo.nodo ? "Il concetto" : "Un concetto nuovo", Number(mx.testo) || 60));
      if (m.tipo === "scheletro") {
        f.append(...scelta("argomento", "Argomento", [["", "Nessuno"], ...(d.argomenti || []).map((a) => [a.id, a.numero + ". " + String(a.titolo || "")])], mo.argomento));
        f.append(...scelta("pagina", "Pagina", [["", "Nessuna"], ...(d.pagine || []).map((x) => [x.id, String(x.nome || "")])], mo.pagina));
      }
    } else {
      const voci = (m.nodi || []).map((n) => [n.id, n.casella && !n.testo ? "casella vuota " + n.id : String(n.testo || "")]);
      if (!mo.collegamento) {
        f.append(...scelta("da", "Da", [["", "Scegli"], ...voci], mo.da), ...scelta("a", "A", [["", "Scegli"], ...voci], mo.a));
      }
      f.append(...testo("verbo", "Con quale verbo? («porta a», «è parte di»…)", Number(mx.verbo) || 40));
    }
    const t = nodo("div", "studio-h-tasti");
    t.append(tastoMappa("Salva", "salva", {}, "studio-h-primo"), tastoMappa("Annulla", "annulla", {}));
    f.append(t);
    return f;
  }

  async function caricaMappa(vid, dati) {
    if (!sch() || !sch().studioMappa || !mappa) return false;
    mappa.attesa = true;
    disegnaHome();
    const r = await sch().studioMappa(Object.assign({ verifica: vid }, dati || {}));
    if (!mappa || mappa.vid !== vid) return false;
    mappa.attesa = false;
    if (!r.ok) {
      mappa.esito = String(r.dati.errore || "Non ci sono riuscita: riprova tra poco.");
      disegnaHome();
      return false;
    }
    if (r.blob) {
      const u = URL.createObjectURL(r.blob);
      const a = document.createElement("a");
      a.href = u;
      a.download = "mappa-" + vid + ".pdf";
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(u), 15000);
      mappa.esito = "Ecco il PDF della mappa: lo trovi fra i file scaricati.";
      disegnaHome();
      return true;
    }
    mappa.dati = r.dati;
    // Senza una mappa scelta, la più avanti fra quelle che ci sono
    if (!mappa.quale || (!r.dati[mappa.quale] && dati === undefined)) mappa.quale = r.dati.mia ? "mia" : "scheletro";
    if (mappa.scelto && !nodoDi(mappaCorrente(), mappa.scelto)) mappa.scelto = null;
    disegnaHome();
    return true;
  }
  async function suMappa(b) {
    const art = b.closest("[data-verifica]");
    const vid = Number(art && art.dataset.verifica);
    let dati = {};
    try { dati = JSON.parse(b.dataset.dati || "{}"); } catch (e) { return; }
    const az = b.dataset.mappa;
    if (az === "apri") {
      mappa = { vid, quale: "", vista: "elenco", dati: null, scelto: null, modulo: null, bozze: {}, attesa: false, esito: "", ricomincia: false, aiuto: "" };
      vista({ vista: "mappa", verifica: vid });
      await caricaMappa(vid);
      return;
    }
    if (!mappa || mappa.vid !== vid) return;
    const m = mappaCorrente();
    mappa.esito = "";
    if (az === "chiudi") { mappa = null; vista({ vista: "home" }); caricaHome(); return; }
    if (az === "quale") { mappa.quale = dati.quale; mappa.scelto = null; mappa.modulo = null; mappa.ricomincia = false; mappa.riapri = false; disegnaHome(); return; }
    if (az === "vista") { mappa.vista = dati.vista; disegnaHome(); return; }
    if (az === "aiuto") { mappa.aiuto = dati.aiuto; disegnaHome(); return; }
    if (az === "nuovo") { mappa.modulo = { tipo: "nodo", testo: "", argomento: null, pagina: null }; disegnaHome(); return; }
    if (az === "collega") { mappa.modulo = { tipo: "collega", da: dati.da || null, a: null, verbo: "" }; disegnaHome(); return; }
    if (az === "cambia") {
      const n = nodoDi(m, dati.nodo);
      if (!n) return;
      mappa.modulo = { tipo: "nodo", nodo: n.id, testo: n.testo, argomento: n.argomento, pagina: null };
      disegnaHome();
      return;
    }
    if (az === "cambia_coll") {
      const c = (m && m.collegamenti || []).find((x) => x.id === dati.collegamento);
      if (!c) return;
      mappa.modulo = { tipo: "collega", collegamento: c.id, verbo: c.verbo };
      disegnaHome();
      return;
    }
    if (az === "annulla") { mappa.modulo = null; disegnaHome(); return; }
    if (az === "ricomincia") { mappa.ricomincia = true; disegnaHome(); return; }
    if (az === "chiedi_riapri") { mappa.riapri = true; disegnaHome(); return; }
    if (az === "scheletro") { if (await caricaMappa(vid, { azione: "scheletro" })) { mappa.quale = "scheletro"; mappa.modulo = { tipo: "nodo", testo: "", argomento: null, pagina: null }; disegnaHome(); } return; }
    if (az === "inizia") {
      if (await caricaMappa(vid, { azione: "inizia", tipo: dati.tipo, aiuto: mappa.aiuto || undefined })) {
        mappa.quale = dati.tipo === "studente" ? "mia" : "memoria";
        disegnaHome();
      }
      return;
    }
    if (az === "pdf") { await caricaMappa(vid, { azione: "pdf", tipo: dati.tipo || "studente" }); return; }
    if (az === "libera") { if (await caricaMappa(vid, { azione: "libera" })) { mappa.quale = "libera"; disegnaHome(); } return; }
    if (!m) return;
    if (az === "salva") {
      const mo = mappa.modulo;
      if (!mo) return;
      let corpo;
      if (mo.tipo === "nodo") {
        const testo = String(mo.testo || "").trim();
        if (!testo) { mappa.esito = "Scrivi il concetto."; disegnaHome(); return; }
        corpo = { azione: "nodo", mappa: m.id, testo };
        if (mo.nodo) corpo.nodo = mo.nodo;
        if (m.tipo === "scheletro") {
          corpo.argomento = mo.argomento ? Number(mo.argomento) : null;
          if (mo.pagina) corpo.pagine = [Number(mo.pagina)];
        }
      } else {
        const verbo = String(mo.verbo || "").trim();
        if (!verbo || (!mo.collegamento && (!mo.da || !mo.a))) { mappa.esito = "Scegli i due concetti e scrivi il verbo."; disegnaHome(); return; }
        corpo = mo.collegamento ? { azione: "collega", mappa: m.id, collegamento: mo.collegamento, verbo }
          : { azione: "collega", mappa: m.id, da: Number(mo.da), a: Number(mo.a), verbo };
      }
      if (await caricaMappa(vid, corpo)) { mappa.modulo = null; mappa.esito = "Fatto."; disegnaHome(); }
      return;
    }
    if (az === "riempi") {
      const testo = String(mappa.bozze[dati.nodo] !== undefined ? mappa.bozze[dati.nodo] : "").trim();
      if (await caricaMappa(vid, { azione: "riempi", mappa: m.id, nodo: dati.nodo, testo })) { delete mappa.bozze[dati.nodo]; mappa.esito = testo ? "Messa." : "Casella svuotata."; disegnaHome(); }
      return;
    }
    if (az === "controlla") {
      if (await caricaMappa(vid, { azione: "controlla", mappa: m.id })) {
        const c = mappa.dati.controllo || {};
        mappa.esito = "Controllata: " + nn(c.giusta, "giusta", "giuste") + ", " + nn(c.sbagliata, "da rivedere", "da rivedere") + ", " + nn(c.vuota, "da riempire", "da riempire") + ".";
        disegnaHome();
      }
      return;
    }
    // La mappa libera (passo 7c, #328): «Ho finito», «Un indizio», «Mostra»
    if (az === "finito") {
      if (await caricaMappa(vid, { azione: "finito", mappa: m.id })) {
        const f = (mappa.dati.finito || {}).conti;
        mappa.esito = f ? "Finita: " + (Number(f.presente) + Number(f.diverso)) + " concetti chiave su " + Number(f.chiave) + ". Qui sotto il confronto e il metodo." : "Finita: qui sotto come è fatta la tua mappa.";
        disegnaHome();
      }
      return;
    }
    if (az === "indizio") {
      if (await caricaMappa(vid, { azione: "indizio", mappa: m.id })) {
        const i = mappa.dati.indizio || {};
        mappa.esito = i.concetto ? "Ti manca un concetto chiave: la pagina è qui sotto." : "Non ti manca nessun altro concetto chiave.";
        disegnaHome();
      }
      return;
    }
    if (az === "mostra") { await caricaMappa(vid, { azione: "mostra", mappa: m.id, concetto: dati.concetto }); return; }
    if (az === "carte") {
      if (await caricaMappa(vid, { azione: "carte", mappa: m.id })) {
        const n = Number(mappa.dati.carte) || 0;
        mappa.esito = n ? (n === 1 ? "Una carta nuova" : n + " carte nuove") + " da ripassare." : "Nessuna carta nuova.";
        disegnaHome();
      }
      return;
    }
    if (az === "rifai") {
      if (await caricaMappa(vid, { azione: "rifai", mappa: m.id, aiuto: mappa.aiuto || undefined })) { mappa.ricomincia = false; mappa.scelto = null; disegnaHome(); }
      return;
    }
    if (az === "conferma") {
      if (await caricaMappa(vid, { azione: "conferma", mappa: m.id })) {
        const r = mappa.dati.confermato || {};
        mappa.esito = "Scheletro confermato: " + Number(r.tenuti || 0) + " concetti" + (Number(r.da_decidere) ? "; " + Number(r.da_decidere) + " voci con un avviso restano da decidere." : ".");
        disegnaHome();
      }
      return;
    }
    if (az === "riapri") {
      if (await caricaMappa(vid, { azione: "riapri", mappa: m.id })) {
        const n = Number((mappa.dati.riaperto || {}).copie_tolte) || 0;
        mappa.riapri = false;
        mappa.esito = "Lo scheletro è di nuovo da confermare" + (n ? ": la tua mappa e quella a memoria si rifanno dopo la conferma." : ".");
        disegnaHome();
      }
      return;
    }
    const semplici = { togli_nodo: ["nodo"], togli_collegamento: ["collegamento"], tieni: ["nodo", "collegamento"], sposta: ["nodo", "x", "y"], riordina: [] };
    if (az in semplici) {
      const corpo = { azione: az, mappa: m.id };
      for (const k of semplici[az]) if (dati[k] !== undefined) corpo[k] = dati[k];
      await caricaMappa(vid, corpo);
    }
  }
  function suCampoMappa(ev) {
    const t = ev.target;
    if (!t || !t.dataset || !mappa) return false;
    if (t.dataset.casella) { mappa.bozze[Number(t.dataset.casella)] = t.value; return true; }
    if (t.dataset.mcampo && mappa.modulo) { mappa.modulo[t.dataset.mcampo] = t.value; return true; }
    return false;
  }
  // Scegliere un concetto sulla mappa (tocco o Invio) e spostarlo trascinando
  let trascina = null;
  function giuSulNodo(ev) {
    const g = ev.target.closest && ev.target.closest(".studio-m-nodo");
    if (!g || !mappa) return;
    const s = g.ownerSVGElement;
    trascina = { g, s, id: Number(g.dataset.nodo), x0: ev.clientX, y0: ev.clientY, via: false, cambia: !!(s && s.dataset.cambia) };
    if (trascina.cambia && g.setPointerCapture) { try { g.setPointerCapture(ev.pointerId); } catch (e) { /* niente */ } }
  }
  function muoviNodo(ev) {
    if (!trascina || !trascina.cambia) return;
    const dx = ev.clientX - trascina.x0, dy = ev.clientY - trascina.y0;
    if (!trascina.via && Math.hypot(dx, dy) < 8) return;
    trascina.via = true;
    const r = trascina.s.getBoundingClientRect();
    const W = Number(trascina.s.dataset.w), H = Number(trascina.s.dataset.h);
    const n = nodoDi(mappaCorrente(), trascina.id);
    if (!n || !r.width) return;
    const x = W * 0.12 + (Number(n.x) || 0.5) * W * 0.76 + dx * W / r.width;
    const y = H * 0.08 + (Number(n.y) || 0.5) * H * 0.84 + dy * H / r.height;
    trascina.g.setAttribute("transform", "translate(" + x + "," + y + ")");
    trascina.fx = Math.max(0, Math.min(1, (x - W * 0.12) / (W * 0.76)));
    trascina.fy = Math.max(0, Math.min(1, (y - H * 0.08) / (H * 0.84)));
  }
  function suNodo(ev) {
    const t = trascina;
    trascina = null;
    if (!t || !mappa) return;
    const m = mappaCorrente();
    if (t.via && m && t.fx !== undefined) {
      caricaMappa(mappa.vid, { azione: "sposta", mappa: m.id, nodo: t.id, x: Math.round(t.fx * 1000) / 1000, y: Math.round(t.fy * 1000) / 1000 });
      return;
    }
    mappa.scelto = mappa.scelto === t.id ? null : t.id;
    disegnaHome();
  }
  function tastoSulNodo(ev) {
    if (ev.key !== "Enter" && ev.key !== " ") return;
    const g = ev.target.closest && ev.target.closest(".studio-m-nodo");
    if (!g || !mappa) return;
    ev.preventDefault();
    const id = Number(g.dataset.nodo);
    mappa.scelto = mappa.scelto === id ? null : id;
    disegnaHome();
    const di = document.querySelector('.studio-m-nodo[data-nodo="' + id + '"]');
    if (di) di.focus();
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
    if (b.dataset.carte) { suCarte(b); return; }
    if (b.dataset.mappa) { suMappa(b); return; }
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
    carte = null;
    mappa = null;
    if (st.materiali) chiudiCamera();
    if ($("studio")) $("studio").hidden = true;
    vista({ vista: null });
  }

  function avvia() {
    if (!$("studio") || !$("studio-home")) return;
    $("studio-home").addEventListener("click", suHome);
    // I campi di «Scrivi una carta»: restano anche quando la home si ridisegna
    $("studio-home").addEventListener("input", suCampoCarte);
    $("studio-home").addEventListener("change", suCampoCarte);
    // La mappa (passo 7, #247): i campi, il tocco e il trascinamento dei concetti, Invio
    $("studio-home").addEventListener("input", suCampoMappa);
    $("studio-home").addEventListener("change", suCampoMappa);
    $("studio-home").addEventListener("pointerdown", giuSulNodo);
    $("studio-home").addEventListener("pointermove", muoviNodo);
    $("studio-home").addEventListener("pointerup", suNodo);
    $("studio-home").addEventListener("pointercancel", () => { trascina = null; });
    $("studio-home").addEventListener("keydown", tastoSulNodo);
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
        carte: carte ? { vid: carte.vid, modo: carte.modo, mostra: carte.mostra, esito: carte.esito,
          da_ripassare: carte.dati ? (carte.dati.da_ripassare || []).slice() : [],
          carte: carte.dati ? (carte.dati.carte || []).map((c) => ({ id: c.id, stato: c.stato, scatola: c.scatola })) : [] } : null,
        mappa: mappa ? { vid: mappa.vid, quale: mappa.quale, vista: mappa.vista, scelto: mappa.scelto, esito: mappa.esito,
          modulo: mappa.modulo ? mappa.modulo.tipo : null,
          mappe: mappa.dati ? ["scheletro", "mia", "memoria", "libera"].filter((k) => mappa.dati[k]).map((k) => ({ quale: k, id: mappa.dati[k].id,
            stato: mappa.dati[k].stato, nodi: (mappa.dati[k].nodi || []).length, collegamenti: (mappa.dati[k].collegamenti || []).length })) : [] } : null,
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
