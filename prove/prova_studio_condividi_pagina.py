import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""La condivisione dal telefono allo Studio nella pagina vera (31/10, issue #298 parte 3, epic #251;
share_target, telefono/sw.js, telefono/condividi.js).

Nel browser vero (Edge o Chromium senza finestra; senza si salta), col server degli schermi vero e
il service worker vero, Leo (di fantasia) con una verifica di storia. Android manda la condivisione
come un POST multipart all'azione del manifest: qui lo stesso POST lo fa la pagina, e lo prende il
service worker (il «Condividi» del sistema non si può emulare):
- il service worker tiene i file sul telefono e apre «?condividi=1»: il riquadro «Condiviso con
  Calliope» in Le mie cose coi nomi (uno in HTML resta testo), «Aggiungi ai materiali» spento finché
  la persona non sceglie la verifica; a 390×844 e a 320×693 col testo al 125 %, niente di lato e
  tocchi ≥ 44 px;
- scelta la verifica, i file passano dalla stessa importazione (POST /api/studio/importa): due
  importazioni sul server, i file tolti dal telefono; «Apri lo Studio» apre «Aggiungi materiali»
  della verifica con le importazioni;
- una condivisione arrivata al server senza il service worker («?condividi=0») lo dice;
- nessun errore JavaScript né violazione della CSP.
Con CALLIOPE_FOTO=<cartella> gli screenshot. ~30 s.

    python prove/prova_studio_condividi_pagina.py
"""

import base64
import datetime
import json
import shutil
import tempfile
import time
from pathlib import Path

import prova_studio_mappa_pagina as PMP
import prova_studio_tutore_pagina as PTU

B = PMP.B
TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-condividi-pagina-"))
LEO, REG = PMP.LEO, PMP.REG
verifica, aspetta, misure = B.verifica, B.aspetta, PMP.misure
SALTATA = B.SALTATA
NOME_HTML = "<img src=x onerror=alert(1)>appunti.txt"


def stato(t) -> dict:
    return json.loads(t.v("JSON.stringify(window.CalliopeCondividi ? window.CalliopeCondividi.stato() : {})")
                      or "{}")


def condividi_js(file: list) -> str:
    """Il POST multipart che Android manda all'azione del manifest, fatto dalla pagina."""
    parti = "".join(
        f"fd.append('file', new File([Uint8Array.from(atob({json.dumps(base64.b64encode(d).decode())}), "
        f"c => c.charCodeAt(0))], {json.dumps(n)}));" for n, d in file)
    return ("(async () => { const fd = new FormData(); fd.append('titolo', 'Condiviso');" + parti +
            " const r = await fetch('/telefono/condividi', {method: 'POST', body: fd});"
            " window.__condiviso = r.url; })(); 1")


def scenario(t, pagina, st, vid):
    T_ = "window.calliopeTelefono"
    verifica("pagina caricata e collegata", bool(aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)))
    ok = aspetta(lambda: t.v("!!(navigator.serviceWorker && navigator.serviceWorker.controller)"), 10)
    if not ok:
        # Il primo caricamento registra il service worker; il secondo è suo
        pagina._chiama("Page.reload")
        time.sleep(0.5)
        ok = aspetta(lambda: t.v("!!(navigator.serviceWorker && navigator.serviceWorker.controller)"), 15)
    verifica("il service worker controlla la pagina", bool(ok))
    import prova_studio_importa as PI
    z = PI.zip_di([("corso/1 appunti.md", "Le caravelle e il quadrante.".encode()),
                   ("corso/2 libro.pdf", PI.pdf(1))])
    t.v(condividi_js([("Classroom.zip", z), (NOME_HTML, "Il testo col nome strano.".encode())]))
    ok = aspetta(lambda: "condividi=1" in (t.v("window.__condiviso || ''") or ""), 10)
    verifica("il POST della condivisione lo prende il service worker e manda a «?condividi=1»", bool(ok),
             t.v("window.__condiviso || ''"))
    verifica("niente arrivato al server prima della scelta della verifica",
             not st.dati.tutti("SELECT id FROM studio_importazioni"))
    t.v("location.href = '/telefono/?condividi=1#/cose'; 1")
    time.sleep(0.5)
    aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)
    ok = aspetta(lambda: (stato(t).get("aperto") and len(stato(t).get("file") or []) == 2
                          and stato(t).get("verifiche") == [vid]), 15)
    s = stato(t)
    verifica("il riquadro «Condiviso con Calliope» coi due file e la verifica di Leo", bool(ok), json.dumps(s))
    verifica("l'indirizzo torna quello della pagina (senza «?condividi»)",
             "condividi" not in (t.v("location.search") or ""))
    testo = t.v("document.getElementById('condividi').innerText") or ""
    verifica("il nome in HTML resta testo: nessun elemento creato",
             "<img src=x" in testo and not t.v("!!document.querySelector('#condividi img')"), testo[:200])
    verifica("«Aggiungi ai materiali» spento finché la persona non sceglie la verifica",
             t.v("document.getElementById('condividi-manda').disabled")
             and t.v("document.getElementById('condividi-verifica').value") == "")
    misure(t, "390×844 col riquadro della condivisione")
    B.foto(t, "studio-condividi-390x844.png")
    B.dimensione(t, 320, 693)
    t.v("document.documentElement.style.fontSize = '125%'; 1")
    misure(t, "320×693 col riquadro della condivisione e il testo grande")
    B.foto(t, "studio-condividi-320x693-125.png")
    t.v("document.documentElement.style.fontSize = ''; 1")
    B.dimensione(t, 390, 844)
    t.v(f"const s = document.getElementById('condividi-verifica'); s.value = '{vid}'; "
        "s.dispatchEvent(new Event('change')); 1")
    verifica("scelta la verifica, il tasto si accende", not t.v("document.getElementById('condividi-manda').disabled"))
    t.tocca("#condividi-manda")
    ok = aspetta(lambda: (stato(t).get("fatto") or {}).get("fatti") == 2, 20)
    verifica("i due file mandati con la stessa importazione", bool(ok), json.dumps(stato(t)))
    righe = st.dati.tutti("SELECT nome, chi FROM studio_importazioni WHERE verifica = ?", (vid,))
    verifica("sul server due importazioni di Leo nella verifica scelta",
             len(righe) == 2 and all(r["chi"] == "l1" for r in righe), righe)
    n = t.v("(async () => { const r = indexedDB.open('calliope-condivisi', 1); const db = await new Promise(ok => "
            "r.onsuccess = () => ok(r.result)); const c = await new Promise(ok => { const q = db.transaction('file')"
            ".objectStore('file').count(); q.onsuccess = () => ok(q.result); }); db.close(); window.__restano = c; })(); 1")
    del n
    aspetta(lambda: t.v("window.__restano !== undefined"), 5)
    verifica("i file condivisi tolti dal telefono dopo l'invio", t.v("window.__restano") == 0)
    t.tocca("#condividi-studio")
    ok = aspetta(lambda: "Estratto" in (t.v("(document.querySelector('section.studio-i') || {}).innerText || ''") or ""), 30)
    verifica("«Apri lo Studio»: «Aggiungi materiali» della verifica con le importazioni", bool(ok),
             json.dumps({"tessere": t.v("[...document.querySelectorAll('#tessere [data-tessera]')].map(x => x.dataset.tessera + ':' + x.className)"),
                         "studio": t.v("!document.getElementById('studio').hidden"),
                         "sezione": t.v("(document.querySelector('section.studio-i') || {}).innerText || ''"),
                         "hash": t.v("location.hash")})[:600])
    # La condivisione arrivata al server senza il service worker
    t.v("location.href = '/telefono/?condividi=0#/cose'; 1")
    time.sleep(0.5)
    ok = aspetta(lambda: "non è arrivata" in (stato(t).get("motivo") or ""), 10)
    verifica("«?condividi=0»: la pagina dice di aprire Calliope e condividere di nuovo", bool(ok))


def main() -> int:
    import prova_telefono_pagina as PTP
    import prova_telefono_schermo as PTS
    shutil.rmtree(PTP.TMP, ignore_errors=True)
    PTP.TMP = TMP
    try:
        exe = PTP.browser()
        if exe is None:
            print("Nessun Edge né Chromium: prova saltata.")
            return SALTATA
        cfg, srv, hub, web = PTS.avvia(TMP / "server")
        from calliope import minori
        from calliope import studio as S
        import types
        cfg.studio_modo, cfg.studio_cartella, cfg.studio_lettura = "attivo", "studio", False
        minori.prepara(cfg, registry=REG)
        st = S.Studio(cfg, registry=REG, log=lambda m: None)
        st.avvia_lettura(None, avvia=False)
        serv = B.Servizi()
        serv.studio = st
        hub.servizi = serv
        hub.profilo = REG.by_id
        hub.tool_ctx = types.SimpleNamespace(studio=st)
        vid = st.crea_verifica(LEO, "Storia", st._oggi() + datetime.timedelta(days=7),
                               argomento="Le scoperte geografiche")
        _, tok_l = srv.archivio.crea_con_token("telefono di Leo", proprietario="l1",
                                               proprietario_nome="Leo")
        hub._rinfresca()
        url = f"http://127.0.0.1:{web.port}/telefono/"
        try:
            pagina = PTU.apri_pagina(PTP, exe, url, "profilo-studio-condividi", tok_l, 390)
            try:
                t = B.T(pagina)
                B.dimensione(t, 390, 844)
                scenario(t, pagina, st, vid)
                PTU.errori_di(pagina, "telefono di Leo")
            finally:
                pagina.chiudi()
        finally:
            web.ferma()
            srv.ferma()
            st.close()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
        if "prova_studio_importa" in sys.modules:
            sys.modules["prova_studio_importa"].pulisci()
    print("\nTutto bene." if not B.ERRORI else f"\n{len(B.ERRORI)} prove non riuscite.")
    return 1 if B.ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
