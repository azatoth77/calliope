// Calliope · gli esercizi guidati dello Studio (31/10/2026, issue #278, epic #251, decisione 0035).
// La sezione «Esercizi guidati» di ogni verifica nella home dello Studio (studio.js la chiama):
// «Foto di un problema» o «Scrivi un problema», e i passi uno alla volta. Il testo del problema,
// le domande e gli indizi vengono da una foto e da un modello: sono dati, la pagina li scrive solo
// con textContent, mai innerHTML. L'esito di ogni passo lo decide il server (il codice); le
// risposte attese non arrivano mai alla pagina di chi studia (POST /api/studio/esercizio).
"use strict";

(function () {
  const sch = () => window.calliopeSchermo;
  // es: {vid, dati, aperto (id), modulo (testo) | null, risposta, esito, attesa, richiesta}
  let es = { vid: null, dati: null, aperto: null, modulo: null, risposta: "", esito: "",
    attesa: false, richiesta: 0 };
  let ctx = { ridisegna() {}, ricarica() {}, vista() {} };

  const STATI = { da_leggere: "da leggere", in_lettura: "lo sto leggendo", letto: "preparo i passi",
    pronto: "pronto", senza_guida: "senza guida: guardalo con chi ti segue",
    illeggibile: "non sono riuscita a leggerlo: rifai la foto", in_corso: "in corso",
    pausa: "in pausa", finito: "finito" };
  const ESITI = { giusto: "giusta", indizio: "manca l'unità", sbagliato: "non ancora",
    da_rivedere: "da rivedere", saltato: "saltato", vuota: "senza risposta" };
  const AVVISI = { istruzioni: "Nel testo c'è un messaggio per un assistente: non lo seguo.",
    controlla_numeri: "Controlla i numeri: la foto non era chiarissima." };
  const LETTERE = "abcde";

  function nodo(tag, cls, testo) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (testo !== undefined && testo !== null) el.textContent = String(testo);
    return el;
  }
  function tasto(testo, azione, dati, cls, etichetta) {
    const b = nodo("button", "tasto studio-h-tasto" + (cls ? " " + cls : ""), testo);
    b.type = "button";
    b.dataset.esercizio = azione;
    b.dataset.dati = JSON.stringify(dati || {});
    if (etichetta) b.setAttribute("aria-label", etichetta);
    b.disabled = !!es.attesa;
    return b;
  }

  function riga(c) {
    if (!c || !c.totali) return "Fotografa un problema o scrivilo: lo facciamo a passi, e la soluzione la trovi tu.";
    const pezzi = [];
    if (c.in_corso) pezzi.push(c.in_corso === 1 ? "uno in corso" : c.in_corso + " in corso");
    if (c.pronti) pezzi.push(c.pronti === 1 ? "uno pronto" : c.pronti + " pronti");
    if (c.da_leggere) pezzi.push(c.da_leggere === 1 ? "uno da preparare" : c.da_leggere + " da preparare");
    if (c.finiti) pezzi.push(c.finiti === 1 ? "uno finito" : c.finiti + " finiti");
    return (c.totali === 1 ? "Un esercizio" : c.totali + " esercizi") + (pezzi.length ? ": " + pezzi.join(", ") + "." : ".");
  }

  // La sezione di una verifica: v.esercizi sono i conti del server (null: spenti per chi guarda)
  function sezione(v, funzioni) {
    if (funzioni) ctx = Object.assign(ctx, funzioni);
    const sez = nodo("section", "studio-h-gruppo studio-e");
    sez.dataset.verifica = String(v.id);
    sez.append(nodo("h4", "studio-h-sotto", "Esercizi guidati"));
    sez.append(nodo("p", "studio-h-riga", riga(v.esercizi)));
    const aperta = es.vid === v.id;
    const t = nodo("div", "studio-h-tasti");
    // La foto: un campo file dentro un'etichetta che sembra un tasto (la fotocamera del telefono)
    const id = "studio-e-foto-" + v.id;
    const l = nodo("label", "tasto studio-h-tasto studio-h-primo studio-e-foto", "Foto di un problema");
    l.htmlFor = id;
    const f = document.createElement("input");
    f.type = "file";
    f.id = id;
    f.accept = "image/jpeg,image/png,image/webp";
    f.setAttribute("capture", "environment");
    f.className = "studio-e-file";
    f.dataset.esercizioFoto = String(v.id);
    f.disabled = !!es.attesa;
    t.append(l, f);
    t.append(tasto("Scrivi un problema", "scrivi", { verifica: v.id }));
    t.append(tasto(aperta ? "Chiudi" : "I miei esercizi", aperta ? "chiudi" : "elenco", { verifica: v.id }));
    sez.append(t);
    if (aperta) sez.append(pannello());
    if (aperta && es.esito) {
      const p = nodo("p", "pagina-esito studio-e-esito", es.esito);
      p.setAttribute("role", "status");
      sez.append(p);
    }
    return sez;
  }

  function pannello() {
    const p = nodo("div", "studio-e-pannello");
    if (es.modulo !== null) {
      const id = "studio-e-testo-" + es.vid;
      const l = nodo("label", "studio-campo", "Il testo del problema");
      l.htmlFor = id;
      const ta = document.createElement("textarea");
      ta.id = id;
      ta.rows = 5;
      ta.maxLength = Number(((es.dati || {}).massimi || {}).testo) || 1500;
      ta.className = "studio-c-campo";
      ta.dataset.esercizioCampo = "testo";
      ta.value = es.modulo;
      const t = nodo("div", "studio-h-tasti");
      t.append(tasto("Salva", "salva", {}, "studio-h-primo"), tasto("Annulla", "annulla", {}));
      p.append(l, ta, t);
    }
    const d = es.dati;
    if (!d) { p.append(nodo("p", "pagina-nota", "Un attimo…")); return p; }
    if (d.ferma) p.append(nodo("p", "studio-h-riga", "C'è una prova aperta su questa verifica: gli esercizi guidati tornano dopo la consegna."));
    const lista = Array.isArray(d.esercizi) ? d.esercizi : [];
    const aperto = lista.find((x) => x.id === es.aperto);
    if (aperto) { p.append(esercizio(aperto)); return p; }
    if (!lista.length) p.append(nodo("p", "studio-h-riga", "Nessun esercizio: fotografa o scrivi un problema."));
    const ul = nodo("ul", "studio-h-elenco studio-e-elenco");
    lista.forEach((x, i) => {
      const li = nodo("li", "studio-h-voce studio-e-voce");
      const tx = nodo("div", "studio-testo");
      tx.append(nodo("b", null, "Esercizio " + (lista.length - i)),
        nodo("span", "studio-nota studio-e-anteprima", String(x.testo || (x.origine === "foto" ? "Una foto" : "")).slice(0, 140)),
        nodo("span", "studio-nota", STATI[x.stato] || String(x.stato)));
      const t = nodo("div", "studio-tasti");
      const nome = "esercizio " + (lista.length - i);
      if (["pronto", "in_corso", "pausa", "finito"].includes(x.stato)) {
        t.append(tasto(x.stato === "finito" ? "Rivedi" : x.stato === "pronto" ? "Comincia" : "Continua", "apri",
          { esercizio: x.id }, x.stato === "finito" ? "" : "studio-h-primo", "Apri " + nome));
      }
      t.append(tasto("Togli", "togli", { esercizio: x.id }, "", "Togli " + nome));
      li.append(tx, t);
      ul.append(li);
    });
    if (ul.childNodes.length) p.append(ul);
    return p;
  }

  function esercizio(x) {
    const box = nodo("div", "studio-e-esercizio");
    box.dataset.esercizioId = String(x.id);
    box.append(nodo("span", "studio-h-etichetta", "Il problema"));
    box.append(nodo("p", "studio-e-testo", String(x.testo || "")));
    for (const a of Array.isArray(x.avvisi) ? x.avvisi : []) if (AVVISI[a]) box.append(nodo("span", "studio-avviso", AVVISI[a]));
    // I passi già fatti, coi soli esiti del server (al tutore, a esercizio finito, anche l'atteso)
    const fatti = (x.voci || []).filter((v) => v.fatto || v.esito);
    if (fatti.length) {
      const ol = nodo("ol", "studio-e-fatti");
      for (const v of fatti) {
        const li = nodo("li", "studio-e-fatto");
        li.append(nodo("span", null, String(v.domanda || "Passo " + v.n)),
          nodo("span", "studio-nota", ESITI[v.esito] || ""));
        if (v.attesa) li.append(nodo("span", "studio-nota", "Risposta attesa: " + String(v.attesa)));
        ol.append(li);
      }
      box.append(ol);
    }
    const c = x.corrente;
    if (x.stato === "finito") {
      box.append(nodo("p", "studio-h-riga", "Finito: " + x.giusti + " passi giusti" +
        (x.da_rivedere ? ", " + x.da_rivedere + " da rivedere" : "") + (x.saltati ? ", " + x.saltati + " saltati" : "") + "."));
    } else if (c) {
      const q = nodo("div", "studio-e-passo");
      q.append(nodo("span", "studio-h-etichetta", "Passo " + c.n + " di " + c.di),
        nodo("p", "studio-c-domanda", String(c.domanda || "")));
      if (c.indizio) q.append(nodo("p", "studio-e-indizio", "Indizio: " + String(c.indizio)));
      if (x.puo_rispondere) {
        const scelte = c.tipo === "scelta" ? (c.opzioni || []).map((o, i) => [LETTERE[i], LETTERE[i] + ") " + String(o)])
          : c.tipo === "vero_falso" ? [["vero", "Vero"], ["falso", "Falso"]] : null;
        if (scelte) {
          const g = nodo("fieldset", "studio-p-scelte");
          g.append(nodo("legend", "studio-nota", "Scegli una risposta"));
          for (const [val, testo] of scelte) {
            const l = nodo("label", "studio-p-opzione");
            const r = document.createElement("input");
            r.type = "radio";
            r.name = "studio-e-" + x.id + "-" + c.n;
            r.value = val;
            r.dataset.esercizioCampo = "risposta";
            r.checked = es.risposta === val;
            l.append(r, nodo("span", null, testo));
            g.append(l);
          }
          q.append(g);
        } else {
          const id = "studio-e-risposta-" + x.id;
          const l = nodo("label", "studio-campo", c.tipo === "numero" ? "La tua risposta (con l'unità, se c'è)" : "La tua risposta");
          l.htmlFor = id;
          const inp = document.createElement(c.tipo === "aperta" ? "textarea" : "input");
          inp.id = id;
          if (inp.tagName === "TEXTAREA") inp.rows = 3;
          else inp.setAttribute("enterkeyhint", "done");
          inp.maxLength = 600;
          inp.className = "studio-c-campo";
          inp.dataset.esercizioCampo = "risposta";
          inp.value = es.risposta;
          q.append(l, inp);
        }
        const t = nodo("div", "studio-h-tasti");
        t.append(tasto("Controlla", "rispondi", { esercizio: x.id }, "studio-h-primo"));
        if (c.ha_indizio && !c.indizio) t.append(tasto("Aiutami", "indizio", { esercizio: x.id }));
        if (c.puo_saltare) t.append(tasto("Salta il passo", "salta", { esercizio: x.id }));
        q.append(t);
      } else if (x.ruolo === "tutore") {
        q.append(nodo("p", "studio-nota", "Ai passi risponde chi studia: qui vedi a che punto è."));
      }
      box.append(q);
    }
    const t = nodo("div", "studio-h-tasti");
    t.append(tasto("Torna agli esercizi", "indietro", {}));
    box.append(t);
    return box;
  }

  async function chiedi(vid, dati) {
    if (!sch() || !sch().studioEsercizio) return null;
    const n = ++es.richiesta;
    es.attesa = true;
    ctx.ridisegna();
    const r = await sch().studioEsercizio(Object.assign({ verifica: vid }, dati || {}));
    if (n !== es.richiesta || es.vid !== vid) return null;      // una risposta vecchia: si butta
    es.attesa = false;
    if (!r.ok) {
      es.esito = String(r.dati.errore || "Non ci sono riuscita: riprova tra poco.");
      ctx.ridisegna();
      return null;
    }
    es.dati = r.dati;
    return r.dati;
  }

  async function su(b) {
    const art = b.closest("[data-verifica]");
    const vid = Number(art && art.dataset.verifica);
    let dati = {};
    try { dati = JSON.parse(b.dataset.dati || "{}"); } catch (e) { return; }
    const az = b.dataset.esercizio;
    es.esito = "";
    if (az === "chiudi") { chiudi(); ctx.vista({ vista: "home" }); ctx.ricarica(); return; }
    if (az === "elenco" || az === "scrivi") {
      Object.assign(es, { vid, dati: null, aperto: null, modulo: az === "scrivi" ? "" : null, risposta: "" });
      ctx.vista({ vista: "esercizi", verifica: vid });
      await chiedi(vid, {});
      ctx.ridisegna();
      return;
    }
    if (es.vid !== vid) return;
    if (az === "annulla") { es.modulo = null; ctx.ridisegna(); return; }
    if (az === "indietro") { es.aperto = null; es.risposta = ""; await chiedi(vid, {}); ctx.ridisegna(); return; }
    if (az === "salva") {
      const testo = String(es.modulo || "").trim();
      if (testo.length < 5) { es.esito = "Scrivi il testo del problema."; ctx.ridisegna(); return; }
      if (await chiedi(vid, { azione: "scrivi", testo })) {
        es.modulo = null;
        es.esito = "Salvato: preparo i passi, ci vuole un momento.";
      }
      ctx.ridisegna();
      return;
    }
    if (az === "apri") {
      es.aperto = Number(dati.esercizio);
      es.risposta = "";
      const x = (es.dati.esercizi || []).find((e) => e.id === es.aperto);
      if (x && x.stato !== "finito" && x.puo_rispondere) await chiedi(vid, { azione: "passo", esercizio: es.aperto });
      ctx.ridisegna();
      return;
    }
    if (az === "rispondi") {
      const risposta = String(es.risposta || "").trim();
      if (!risposta) { es.esito = "Scrivi o scegli la tua risposta."; ctx.ridisegna(); return; }
      const r = await chiedi(vid, { azione: "rispondi", esercizio: Number(dati.esercizio), risposta });
      if (r && r.ultimo) {
        es.esito = String(r.ultimo.frase || ESITI[r.ultimo.esito] || "");
        if (["giusto", "da_rivedere"].includes(r.ultimo.esito)) es.risposta = "";
      }
      ctx.ridisegna();
      return;
    }
    if (az === "indizio" || az === "salta" || az === "togli") {
      const r = await chiedi(vid, { azione: az, esercizio: Number(dati.esercizio) });
      if (r && az === "indizio" && r.indizio && !r.indizio.indizio) es.esito = "Per questo passo non ho un indizio: rileggi il testo.";
      if (r && az === "salta") { es.risposta = ""; es.esito = r.saltato && r.saltato.finito ? "Era l'ultimo passo: rivedilo con chi ti segue." : "Saltato."; }
      if (r && az === "togli") { es.aperto = null; es.esito = "Tolto."; ctx.ricarica(); }
      ctx.ridisegna();
    }
  }

  // I campi: il testo da scrivere, la risposta; la foto da mandare
  async function campo(ev) {
    const t = ev.target;
    if (!t || !t.dataset) return;
    if (t.dataset.esercizioCampo === "testo") { es.modulo = t.value; return; }
    if (t.dataset.esercizioCampo === "risposta") { es.risposta = t.value; return; }
    if (t.dataset.esercizioFoto && ev.type === "change" && t.files && t.files[0]) {
      const vid = Number(t.dataset.esercizioFoto);
      const file = t.files[0];
      t.value = "";
      if (!sch() || !sch().studio) return;
      Object.assign(es, { vid, dati: es.vid === vid ? es.dati : null, aperto: null, modulo: null, risposta: "" });
      es.esito = "Mando la foto…";
      es.attesa = true;
      ctx.ridisegna();
      const r = await sch().studio(file, { verifica: vid, esercizio: true });
      es.attesa = false;
      es.esito = r.ok ? "Arrivata: la leggo e preparo i passi, ci vuole qualche momento." +
        ((r.dati.avvisi || []).length ? " La foto non è chiarissima: se non la leggo, rifalla." : "")
        : String(r.dati.errore || "Non sono riuscita a mandarla: riprova.");
      ctx.vista({ vista: "esercizi", verifica: vid });
      await chiedi(vid, {});
      ctx.ridisegna();
      ctx.ricarica();
    }
  }

  function chiudi() {
    es = { vid: null, dati: null, aperto: null, modulo: null, risposta: "", esito: "", attesa: false,
      richiesta: es.richiesta + 1 };
  }

  // Invio nel campo della risposta: «Controlla»
  function tasti(ev) {
    const t = ev.target;
    if (ev.key !== "Enter" || !t || !t.dataset || t.dataset.esercizioCampo !== "risposta" || t.tagName !== "INPUT") return;
    const box = t.closest(".studio-e-esercizio");
    const b = box && box.querySelector('button[data-esercizio="rispondi"]');
    if (b && !b.disabled) { ev.preventDefault(); b.click(); }
  }

  // Lo stato senza i dati del server, per le prove (mai testi del problema né risposte attese)
  function stato() {
    return { vid: es.vid, aperto: es.aperto, modulo: es.modulo, esito: es.esito, attesa: es.attesa,
      richiesta: es.richiesta };
  }

  window.CalliopeEsercizio = { sezione, su, campo, tasti, chiudi, stato };
})();
