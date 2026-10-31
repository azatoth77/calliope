// Calliope · telefono: i file condivisi con Calliope da un'altra app (31/10/2026, issue #298,
// parte 3, epic #251, decisione 0035). Su Android la PWA installata compare in «Condividi»
// (share_target nel manifest): il service worker (sw.js) riceve il POST, tiene i file in IndexedDB
// sul telefono e apre la pagina con «?condividi=1». Qui la persona vede i file, **sceglie la
// verifica** (mai in automatico) e li manda con la stessa importazione di «Aggiungi materiali»
// (POST /api/studio/importa, con la sessione dello schermo personale: tetti, orari, permessi e
// controlli del server sono gli stessi). I file condivisi restano solo sul telefono e al più
// un'ora; una condivisione nuova sostituisce quella di prima. iOS non ha lo share target per le
// PWA: lì resta «Scegli i file». Nomi dei file e risposte del server: solo textContent.
"use strict";

(function () {
  const DB = "calliope-condivisi", STORE = "file";
  const DURATA_MS = 3600 * 1000;
  const $ = (id) => document.getElementById(id);
  const sch = () => window.calliopeSchermo;
  const st = { file: [], verifiche: [], invio: false, fatto: null, motivo: "" };

  function apriDb() {
    return new Promise((ok, no) => {
      const r = indexedDB.open(DB, 1);
      r.onupgradeneeded = () => r.result.createObjectStore(STORE, { keyPath: "id", autoIncrement: true });
      r.onsuccess = () => ok(r.result);
      r.onerror = () => no(r.error);
    });
  }
  async function tutti() {
    const db = await apriDb();
    try {
      return await new Promise((ok, no) => {
        const r = db.transaction(STORE, "readonly").objectStore(STORE).getAll();
        r.onsuccess = () => ok(r.result || []);
        r.onerror = () => no(r.error);
      });
    } finally { db.close(); }
  }
  async function svuota() {
    try {
      const db = await apriDb();
      await new Promise((ok) => {
        const t = db.transaction(STORE, "readwrite");
        t.objectStore(STORE).clear();
        t.oncomplete = ok; t.onerror = ok; t.onabort = ok;
      });
      db.close();
    } catch (e) { /* niente */ }
  }

  function metti(el, t) { if (el && el.textContent !== t) el.textContent = t; }
  function kb(n) { n = Number(n) || 0; return n < 1048576 ? Math.max(1, Math.round(n / 1024)) + " kB" : (n / 1048576).toFixed(1).replace(".", ",") + " MB"; }

  function disegna() {
    const box = $("condividi");
    if (!box) return;
    box.hidden = !st.file.length && !st.motivo && !st.fatto;
    if (box.hidden) return;
    metti($("condividi-nota"), st.motivo || (st.fatto ? "" : st.file.length === 1
      ? "Un file da un'altra app. Scegli la verifica in cui metterlo."
      : st.file.length + " file da un'altra app. Scegli la verifica in cui metterli."));
    $("condividi-file").replaceChildren(...st.file.map((f) => {
      const li = document.createElement("li");
      li.className = "condividi-voce";
      const b = document.createElement("b");
      b.className = "studio-i-nome";
      b.textContent = String(f.nome || "file");
      const s = document.createElement("span");
      s.className = "studio-h-riga";
      s.textContent = " · " + kb(f.dim);
      li.append(b, s);
      return li;
    }));
    const sel = $("condividi-verifica");
    const scelta = sel.value;
    const opzioni = [new Option("Scegli la verifica…", "")].concat(st.verifiche.map((v) => {
      const o = new Option("", String(v.id));
      o.textContent = [String(v.materia || "Verifica"), String(v.data || ""), v.di ? "di " + String(v.di) : ""].filter(Boolean).join(" · ");
      return o;
    }));
    sel.replaceChildren(...opzioni);
    if (st.verifiche.some((v) => String(v.id) === scelta)) sel.value = scelta;
    const conVerifiche = st.file.length > 0 && st.verifiche.length > 0 && !st.fatto;
    sel.hidden = $("condividi-etichetta").hidden = !conVerifiche;
    sel.disabled = st.invio;
    $("condividi-manda").hidden = !conVerifiche;
    $("condividi-manda").disabled = st.invio || !sel.value;
    $("condividi-studio").hidden = !st.fatto;
    metti($("condividi-annulla"), st.fatto || !st.file.length ? "Chiudi" : "Annulla");
    $("condividi-annulla").disabled = st.invio;
  }

  // Le verifiche a cui mandare: le proprie e, da tutore, quelle dei minori (/api/studio/verifiche).
  // La sessione dello schermo arriva dopo l'accesso: si riprova per un po'
  async function caricaVerifiche() {
    for (let i = 0; i < 40; i++) {
      if (sch() && sch().studio) {
        const r = await sch().studio();
        if (r.ok) {
          st.verifiche = Array.isArray(r.dati.verifiche) ? r.dati.verifiche.filter((v) => v && Number.isInteger(v.id)) : [];
          if (!st.verifiche.length) st.motivo = "Non c'è una verifica aperta a cui aggiungerli: creala a voce, poi condividi di nuovo.";
          return disegna();
        }
        if (r.status && r.status !== 401) {
          st.motivo = String(r.dati.errore || "Lo Studio qui non c'è.");
          return disegna();
        }
      }
      await new Promise((ok) => setTimeout(ok, 500));
    }
    st.motivo = "Non riesco a collegarmi a Calliope: riprova fra poco.";
    disegna();
  }

  async function manda() {
    const vid = Number($("condividi-verifica").value);
    if (st.invio || !Number.isInteger(vid) || vid < 1 || !st.file.length) return;
    st.invio = true;
    disegna();
    const esito = $("condividi-esito");
    let fatti = 0;
    const errori = [];
    try {
      for (const f of st.file) {
        const quale = "Mando " + (fatti + errori.length + 1) + " di " + st.file.length;
        metti(esito, quale + "…");
        let ultimo = -1;
        const r = await sch().studioImporta(f.blob, { verifica: vid, nome: String(f.nome || "file").slice(0, 120) },
          (mandati, tot) => {
            // Ogni 25 %: è un role="status" e il lettore di schermo lo ripete
            const pc = tot ? Math.floor((100 * mandati) / tot) : 0;
            if (pc - ultimo < 25 && pc < 100) return;
            ultimo = pc;
            metti(esito, quale + ": " + pc + "%");
          });
        if (r.ok) fatti++;
        else errori.push(String(f.nome || "file").slice(0, 60) + ": " + String(r.dati.errore || "non mandato"));
      }
    } finally {
      st.invio = false;
    }
    // Mandati o no, i file condivisi non restano sul telefono: si ricondividono
    await svuota();
    st.file = [];
    st.fatto = { vid, fatti };
    metti(esito, (fatti ? (fatti === 1 ? "Mandato: lo preparo in sottofondo." : "Mandati " + fatti + ": li preparo in sottofondo.") : "") +
      (errori.length ? (fatti ? " " : "") + "Non mandati: " + errori.join("; ") + "." : ""));
    disegna();
  }

  function apriStudio() {
    const vid = st.fatto && st.fatto.vid;
    chiudi();
    if (window.CalliopeImporta && window.CalliopeImporta.apri && vid) window.CalliopeImporta.apri(vid);
    // La pagina dello Studio di Le mie cose (sezioni.js), come il tocco sulla sua tessera
    location.hash = "#/cose/studio";
  }
  function chiudi() {
    st.file = [];
    st.motivo = "";
    st.fatto = null;
    metti($("condividi-esito"), "");
    svuota();
    disegna();
  }

  async function avvia() {
    if (!$("condividi")) return;
    $("condividi-verifica").addEventListener("change", disegna);
    $("condividi-manda").addEventListener("click", manda);
    $("condividi-annulla").addEventListener("click", chiudi);
    $("condividi-studio").addEventListener("click", apriStudio);
    const q = new URLSearchParams(location.search);
    const arrivo = q.get("condividi");
    if (arrivo !== null) {
      // L'indirizzo torna quello della pagina (un ricaricamento non rimostra niente)
      try { history.replaceState(null, "", "/telefono/" + (location.hash || "#/cose")); } catch (e) { /* niente */ }
    }
    let file = [];
    try { file = await tutti(); } catch (e) { file = []; }
    // Più vecchi di un'ora: via, senza mostrarli
    const ora = Date.now();
    if (file.some((f) => !(ora - Number(f.quando) < DURATA_MS))) {
      file = file.filter((f) => ora - Number(f.quando) < DURATA_MS);
      if (!file.length) await svuota();
    }
    if (arrivo === null) return;                    // solo quando si arriva da «Condividi»
    st.file = file;
    if (!file.length) {
      st.motivo = arrivo === "0"
        ? "La condivisione non è arrivata: apri Calliope una volta, poi condividi di nuovo."
        : "Non è arrivato nessun file: condividi un file (PDF, foto, documento o ZIP).";
      return disegna();
    }
    disegna();
    try { $("condividi-titolo").focus(); } catch (e) { /* niente */ }
    caricaVerifiche();
  }

  // Per le prove: lo stato senza i byte
  window.CalliopeCondividi = {
    stato() {
      return { file: st.file.map((f) => ({ nome: f.nome, dim: f.dim })), verifiche: st.verifiche.map((v) => v.id),
        invio: st.invio, fatto: st.fatto, motivo: st.motivo, aperto: !!($("condividi") && !$("condividi").hidden) };
    },
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", avvia);
  else avvia();
})();
