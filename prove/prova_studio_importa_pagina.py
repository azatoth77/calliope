import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""«Aggiungi materiali» dello Studio nella pagina vera (31/10, issue #298, epic #251;
schermi/pagina/studio_importa.js, POST /api/studio/importa e /api/studio/importazioni).

Nel browser vero (Edge o Chromium senza finestra; senza si salta), il server degli schermi vero su
127.0.0.1 col lavoro di sfondo vero (il sottoprocesso), Leo (di fantasia) con una verifica di storia:
- il telefono di Leo a 390×844: sulla carta della verifica «Aggiungi materiali», poi «Scegli i
  file» (un tasto vero che apre il selettore nascosto); tre file mandati dalla pagina (un ZIP di
  fantasia con Markdown, PDF e Word, un testo e un file col nome in HTML), la scheda con le fasi e
  i conti che si aggiorna da sola fino a «Estratto: fatto»; il nome in HTML resta testo (nessun
  elemento creato); «I file» con le righe; a 320×693, anche col testo al 125 %, niente di lato e
  tocchi ≥ 44 px;
- il PC personale di Leo: «Aggiungi materiali» nella colonna centrale con le importazioni;
- nessun errore JavaScript né violazione della CSP.
Con CALLIOPE_FOTO=<cartella> gli screenshot. ~30 s.

    python prove/prova_studio_importa_pagina.py
"""

import base64
import datetime
import json
import shutil
import tempfile
from pathlib import Path

import prova_studio_mappa_pagina as PMP
import prova_studio_tutore_pagina as PTU

B = PMP.B
TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-importa-pagina-"))
LEO, ANDREA, REG = PMP.LEO, PMP.ANDREA, PMP.REG
verifica, aspetta, misure = B.verifica, B.aspetta, PMP.misure
SALTATA = B.SALTATA
NOME_HTML = "<img src=x onerror=alert(1)>appunti.txt"


def stato(t) -> dict:
    return json.loads(t.v("JSON.stringify(window.CalliopeImporta ? window.CalliopeImporta.stato() : {})")
                      or "{}")


def sezione_testo(t) -> str:
    return t.v("(document.querySelector('section.studio-i') || {}).innerText || ''") or ""


def file_js(nome: str, dati: bytes) -> str:
    return (f"new File([Uint8Array.from(atob({json.dumps(base64.b64encode(dati).decode())}), "
            f"c => c.charCodeAt(0))], {json.dumps(nome)})")


def manda(t, vid, files):
    elenco = ", ".join(file_js(n, d) for n, d in files)
    t.v(f"window.CalliopeImporta.manda({vid}, [{elenco}]); 1")


def finite(t, vid, n) -> bool:
    s = (stato(t) or {}).get(str(vid)) or {}
    imp = s.get("importazioni") or []
    return len(imp) >= n and all(x["stato"] in ("finita", "errore") for x in imp) and not s.get("invio")


def apri_sezione(t):
    ok = PTU.apri_studio(t) and aspetta(lambda: t.v("!!document.querySelector('button[data-importa=\"apri\"]')"), 8)
    verifica("la carta della verifica ha «Aggiungi materiali»", bool(ok))
    t.tocca('button[data-importa="apri"]')
    return aspetta(lambda: t.v("!!document.querySelector('button[data-importa=\"scegli\"]')"), 8)


def scenario_telefono(t, st, vid):
    import prova_studio_importa as PI
    T_ = "window.calliopeTelefono"
    verifica("pagina caricata e collegata", bool(aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)))
    verifica("«Scegli i file» c'è, il selettore è nascosto e accetta i formati",
             bool(apri_sezione(t)) and t.v("document.querySelector('input[data-importa-file]').hidden")
             and ".zip" in (t.v("document.querySelector('input[data-importa-file]').accept") or ""))
    z = PI.zip_di([("corso/1 appunti.md", "Le caravelle portoghesi e il quadrante.".encode()),
                   ("corso/2 libro.pdf", PI.pdf(1)), ("corso/3 lezione.docx", PI.docx())])
    manda(t, vid, [("Classroom.zip", z), ("note.txt", "Vasco da Gama, 1498.".encode()),
                   (NOME_HTML, "Il testo del file col nome strano.".encode())])
    ok = aspetta(lambda: finite(t, vid, 3), 90)
    s = (stato(t) or {}).get(str(vid)) or {}
    verifica("tre file mandati dalla pagina, la scheda si aggiorna da sola fino alla fine",
             bool(ok) and len(s.get("importazioni") or []) == 3, json.dumps(s)[:400])
    testo = sezione_testo(t)
    verifica("le fasi e i conti sulla scheda («Estratto: fatto», «3 file»)",
             "Estratto: fatto" in testo and "3 file" in testo and "Ricevuto: fatto" in testo, testo[:500])
    verifica("il nome in HTML resta testo: nessun elemento creato dentro la sezione",
             not t.v("!!document.querySelector('section.studio-i img, section.studio-i b b')")
             and "<img src=x" in testo, testo[:300])
    righe = st.dati.tutti("SELECT stato FROM studio_importazioni WHERE verifica = ?", (vid,))
    verifica("sul server tre importazioni finite", len(righe) == 3
             and all(r["stato"] == "finita" for r in righe), righe)
    misure(t, "390×844 con «Aggiungi materiali»")
    B.foto(t, "studio-importa-390x844.png")
    t.v("document.querySelectorAll('section.studio-i details').forEach(d => d.open = true); 1")
    verifica("«I file»: le righe del ZIP coi nomi ripuliti",
             "corso/2 libro.pdf" in sezione_testo(t), sezione_testo(t)[:400])
    B.dimensione(t, 320, 693)
    misure(t, "320×693 con «Aggiungi materiali»")
    t.v("document.documentElement.style.fontSize = '125%'; 1")
    misure(t, "320×693 con «Aggiungi materiali» e il testo grande")
    B.foto(t, "studio-importa-320x693-125.png")
    t.v("document.documentElement.style.fontSize = ''; 1")
    B.dimensione(t, 390, 844)


def scenario_pc(t, vid):
    B.dimensione(t, 1440, 900)
    aspetta(lambda: t.v("!!window.calliopeSchermo"), 10)
    ok = apri_sezione(t)
    verifica("PC di Leo: «Aggiungi materiali» con «Scegli i file»", bool(ok))
    ok = aspetta(lambda: "Estratto: fatto" in sezione_testo(t), 8)
    verifica("PC: le importazioni con le fasi", bool(ok), sezione_testo(t)[:300])
    t.v("document.querySelector('section.studio-i').scrollIntoView({block: 'start'}); 1")
    B.foto(t, "studio-importa-pc.png")


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
        from prova_parla_pc import CollFinto
        cfg.schermi_sezioni = True
        srv.collegati.append(CollFinto(7, "cameretta"))
        s_pc, t_pc = hub.archivio.crea_con_token("cameretta", proprietario="l1", proprietario_nome="Leo")
        hub.archivio.lega_satellite(s_pc["id"], 7)
        hub._rinfresca()
        url = f"http://127.0.0.1:{web.port}/telefono/"
        try:
            pagina = PTU.apri_pagina(PTP, exe, url, "profilo-studio-importa", tok_l, 390)
            try:
                t = B.T(pagina)
                B.dimensione(t, 390, 844)
                scenario_telefono(t, st, vid)
                PTU.errori_di(pagina, "telefono di Leo")
            finally:
                pagina.chiudi()
            pc = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/#t={t_pc}", profilo="profilo-studio-importa-pc",
                            opzioni=("--window-size=1440,900",))
            try:
                pc._chiama("DOM.enable")
                scenario_pc(B.T(pc), vid)
                PTU.errori_di(pc, "PC di Leo")
            finally:
                pc.chiudi()
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
