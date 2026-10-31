import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""La vista del tutore e le indicazioni nella pagina vera (31/10, passo 10, issue #250 e #285,
epic #251; schermi/pagina/studio.js, POST /api/studio/tutore).

Nel browser vero (Edge o Chromium senza finestra; senza si salta), il server degli schermi vero su
127.0.0.1, Leo (di fantasia) con la verifica di storia di `prova_studio_mappa_pagina.py`, tre
domande aperte e una verifica finta consegnata (tre risposte da rivedere); Andrea è il tutore:
- il telefono di Andrea a 390×844: sulla verifica di Leo «Per te che lo segui» e «Vista del
  tutore»; la padronanza in ombra senza cifre, i tre giudizi (uno toccato: il tentativo nel db),
  «Da guardare tu» con domanda, risposta e risposta attesa, «Era giusta» (fonte «tutore»), le
  prove, il ripasso, la mappa; un'indicazione scritta con dell'HTML (resta testo), cambiata e
  rimasta; a 320×693, anche col testo al 125 %, niente di lato e tocchi ≥ 44 px;
- il telefono di Leo: l'indicazione col testo e chi l'ha scritta, l'HTML come testo, nessuna
  «Vista del tutore»;
- il PC personale di Andrea: la vista del tutore nella colonna centrale;
- nessun errore JavaScript né violazione della CSP.
Con CALLIOPE_FOTO=<cartella> gli screenshot. ~25 s.

    python prove/prova_studio_tutore_pagina.py
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

import prova_studio_mappa_pagina as PMP

B = PMP.B
TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-tutore-pagina-"))
LEO, ANDREA, REG = PMP.LEO, PMP.ANDREA, PMP.REG
verifica, aspetta, misure = B.verifica, B.aspetta, PMP.misure
SALTATA = B.SALTATA
HTML = "<b>Insisti</b> sulle date <img src=x onerror=alert(1)>"
ATTESA = "Servivano a conservare i cibi"


class TT(B.T):
    """Prima di toccare un tasto della vista del tutore aspetta che la pagina non sia in attesa."""

    def tocca(self, sel):
        aspetta(lambda: not self.v("!!document.querySelector('.studio-t button:disabled')"), 6)
        return super().tocca(sel)


def testo(t) -> str:
    return t.v("(document.querySelector('.studio-t') || {}).innerText || ''") or ""


def prepara(st):
    vid, _sk = PMP.prepara(st)
    a = [x["id"] for x in st.argomenti(LEO, vid)]
    for i, (q, r) in enumerate((("Perché le spezie erano preziose?", ATTESA),
                                ("Chi finanziò Colombo?", "I re di Spagna"),
                                ("Cosa divise il trattato?", "Le terre nuove"))):
        st.aggiungi_domanda(ANDREA, vid, "aperta", q, r, argomento=a[i])
    p = st.inizia_prova(LEO, vid)
    for x in p["voci"]:
        st.rispondi_prova(LEO, p["id"], x["n"], "per il commercio")
    st.consegna_prova(LEO, p["id"])
    return vid


def apri_studio(t):
    t.v("location.hash = '#/cose'; 1")
    aspetta(lambda: t.v("!!document.querySelector('#tessere [data-tessera=\"studio\"]:not(.presto)')"), 10)
    t.tocca('#tessere [data-tessera="studio"]')
    return aspetta(lambda: t.v("!!document.querySelector('.studio-h-verifica')"), 8)


def scenario_tutore(t, st, vid):
    T_ = "window.calliopeTelefono"
    verifica("telefono di Andrea: pagina caricata e collegata",
             bool(aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)))
    ok = apri_studio(t) and aspetta(lambda: t.v("!!document.querySelector('.studio-t button[data-tutore=\"apri\"]')"), 6)
    verifica("la verifica di Leo: «Per te che lo segui» con «Vista del tutore»", bool(ok))
    t.tocca('.studio-t button[data-tutore="apri"]')
    ok = aspetta(lambda: "Da guardare tu" in testo(t), 8)
    el = testo(t)
    verifica("la vista del tutore: indicazioni, padronanza, da guardare, prove, ripasso",
             bool(ok) and all(x in el for x in ("Indicazioni per lo studio di Leo", "Padronanza",
                                                 "Da guardare tu", "Prove", "Ripasso")), el[:500])
    verifica("la padronanza in ombra: la nota, nessuna cifra", "ancora in prova" in el
             and "%)" not in el and "Livello di oggi" not in el)
    verifica("da guardare tu: la domanda, la risposta di Leo e quella attesa",
             "Perché le spezie erano preziose?" in el and "La risposta di Leo: per il commercio" in el
             and ATTESA in el)
    misure(t, "390×844 con la vista del tutore")
    B.foto(t, "studio-tutore-390x844.png")
    # Il giudizio su un argomento
    t.tocca('.studio-t-giudizi button[data-dati*="da studiare"]')
    ok = aspetta(lambda: st.dati.uno("SELECT * FROM studio_tentativi WHERE tipo = 'giudizio'"), 6)
    g = st.dati.uno("SELECT * FROM studio_tentativi WHERE tipo = 'giudizio'") or {}
    verifica("«Da studiare»: il giudizio del tutore nel db, il tasto premuto",
             bool(ok) and g.get("fonte") == "tutore" and g.get("esito") == "sbagliato"
             and aspetta(lambda: t.v("!!document.querySelector('.studio-t-giudizi button[aria-pressed=\"true\"]')"), 4))
    # «Era giusta» su una risposta da rivedere
    t.tocca('.studio-t-guarda button[data-tutore="rivedi"][data-dati*="giusto"]')
    ok = aspetta(lambda: st.dati.uno("SELECT * FROM studio_tentativi WHERE tipo = 'verifica_finta' "
                                     "AND fonte = 'tutore'"), 6)
    verifica("«Era giusta» dalla vista del tutore: un tentativo con la fonte «tutore»", bool(ok))
    # Un'indicazione con dell'HTML
    sel = ".studio-t-modulo textarea"
    aspetta(lambda: t.v(f"!!document.querySelector('{sel}')"), 4)
    t.v(f"(() => {{ const i = document.querySelector('{sel}'); i.value = {json.dumps(HTML)};"
        " i.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()")
    t.v("(() => { const s = document.querySelector('.studio-t-modulo select[data-tutore-campo=\"ambito\"]');"
        " s.value = 'tutto'; s.dispatchEvent(new Event('change', {bubbles: true})); return 1; })()")
    t.tocca('.studio-t-modulo button[data-tutore="indica"]')
    ok = aspetta(lambda: [x["testo"] for x in st.indicazioni(LEO)] == [HTML], 6)
    aspetta(lambda: "Indicazione scritta" in testo(t), 4)
    verifica("«Scrivi»: l'indicazione salvata per tutto lo studio, l'HTML resta testo",
             bool(ok) and HTML in testo(t)
             and not t.v("!!document.querySelector('.studio-t img, .studio-t-indicazioni b b')"))
    misure(t, "390×844 con l'indicazione")
    t.tocca('.studio-t button[data-tutore="modulo"]')
    aspetta(lambda: t.v("!!document.querySelector('.studio-t-modulo button[data-tutore=\"cambia\"]')"), 4)
    t.v(f"(() => {{ const i = document.querySelector('{sel}'); i.value = 'Insisti sulle date';"
        " i.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()")
    t.tocca('.studio-t-modulo button[data-tutore="cambia"]')
    ok = aspetta(lambda: [x["testo"] for x in st.indicazioni(LEO)] == ["Insisti sulle date"], 6)
    verifica("«Cambia» e «Salva»: il testo nuovo sul server", bool(ok))
    B.dimensione(t, 320, 693)
    t.v("document.querySelector('.studio-t').scrollIntoView({block: 'start'}); 1")
    misure(t, "320×693 con la vista del tutore")
    B.foto(t, "studio-tutore-320x693.png")
    t.v("document.documentElement.style.fontSize = '125%'; 1")
    t.v("document.querySelector('.studio-t').scrollIntoView({block: 'start'}); 1")
    misure(t, "320×693 con la vista del tutore e il testo grande")
    B.foto(t, "studio-tutore-320x693-125.png")
    t.v("document.documentElement.style.fontSize = ''; 1")
    B.dimensione(t, 390, 844)
    stato = t.v("window.CalliopeStudio.stato().tutore") or {}
    verifica("lo stato della pagina: la vista del tutore aperta sulla verifica", stato.get("vid") == vid)
    verifica("niente stato d'animo nella vista", "umore" not in json.dumps(stato.get("dati") or {}))


def scenario_leo(t, st, vid):
    T_ = "window.calliopeTelefono"
    verifica("telefono di Leo: pagina caricata e collegata",
             bool(aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)))
    ok = apri_studio(t) and aspetta(lambda: t.v("!!document.querySelector('.studio-t-per-te')"), 6)
    el = t.v("(document.querySelector('.studio-t-per-te') || {}).innerText || ''") or ""
    verifica("Leo vede l'indicazione col testo e chi l'ha scritta", bool(ok)
             and "Insisti sulle date" in el and "da Andrea" in el, el[:300])
    verifica("Leo non ha la vista del tutore", not t.v("!!document.querySelector('.studio-t')"))
    misure(t, "390×844 di Leo con le indicazioni")
    B.foto(t, "studio-tutore-leo-390x844.png")


def scenario_pc(t, vid):
    B.dimensione(t, 1440, 900)
    aspetta(lambda: t.v("!!window.calliopeSchermo"), 10)
    ok = apri_studio(t) and aspetta(lambda: t.v("!!document.querySelector('.studio-t button[data-tutore=\"apri\"]')"), 6)
    verifica("PC di Andrea: «Vista del tutore» sulla verifica di Leo", bool(ok))
    t.tocca('.studio-t button[data-tutore="apri"]')
    ok = aspetta(lambda: "Da guardare tu" in testo(t), 8)
    verifica("PC: la vista del tutore con la padronanza e le indicazioni", bool(ok)
             and "Insisti sulle date" in testo(t), testo(t)[:300])
    t.v("document.querySelector('.studio-t').scrollIntoView({block: 'start'}); 1")
    B.foto(t, "studio-tutore-pc.png")


def apri_pagina(PTP, exe, url, profilo, token, larghezza):
    pagina = PTP.Pagina(exe, url, profilo=profilo, opzioni=(f"--window-size={larghezza},844",))
    pagina._chiama("DOM.enable")
    aspetta(lambda: pagina.valuta("document.readyState") == "complete", 10)
    if token:
        pagina.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
        pagina._chiama("Page.reload")
        time.sleep(0.5)
    return pagina


def errori_di(pagina, chi):
    pagina.pompa(0.3)
    e = [r for r in pagina.log if r.startswith(("ECCEZIONE", "ERROR")) or "Content Security" in r]
    verifica(f"{chi}: nessun errore JavaScript né violazione della CSP", not e, "; ".join(e)[:300])


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
        vid = prepara(st)
        _, tok_a = srv.archivio.crea_con_token("telefono di Andrea", proprietario="a1",
                                               proprietario_nome="Andrea")
        _, tok_l = srv.archivio.crea_con_token("telefono di Leo", proprietario="l1",
                                               proprietario_nome="Leo")
        from prova_parla_pc import CollFinto
        cfg.schermi_sezioni = True
        srv.collegati.append(CollFinto(6, "studio"))
        s_pc, t_pc = hub.archivio.crea_con_token("studio", proprietario="a1", proprietario_nome="Andrea")
        hub.archivio.lega_satellite(s_pc["id"], 6)
        hub._rinfresca()
        url = f"http://127.0.0.1:{web.port}/telefono/"
        pagina = apri_pagina(PTP, exe, url, "profilo-studio-tutore-a", tok_a, 390)
        try:
            t = TT(pagina)
            B.dimensione(t, 390, 844)
            scenario_tutore(t, st, vid)
            errori_di(pagina, "telefono di Andrea")
        finally:
            pagina.chiudi()
        pagina = apri_pagina(PTP, exe, url, "profilo-studio-tutore-l", tok_l, 390)
        try:
            t = TT(pagina)
            B.dimensione(t, 390, 844)
            scenario_leo(t, st, vid)
            errori_di(pagina, "telefono di Leo")
        finally:
            pagina.chiudi()
        pc = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/#t={t_pc}", profilo="profilo-studio-tutore-pc",
                        opzioni=("--window-size=1440,900",))
        try:
            pc._chiama("DOM.enable")
            scenario_pc(TT(pc), vid)
            errori_di(pc, "PC di Andrea")
        finally:
            pc.chiudi()
            web.ferma()
            srv.ferma()
            st.close()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not B.ERRORI else f"\n{len(B.ERRORI)} prove non riuscite.")
    return 1 if B.ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
