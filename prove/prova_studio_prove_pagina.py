import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Le prove dello Studio nella pagina vera (31/10, passo 8, issue #248, epic #251;
schermi/pagina/studio.js, POST /api/studio/prova).

Nel browser vero (Edge o Chromium senza finestra; senza si salta), il server degli schermi vero su
127.0.0.1, Leo (di fantasia) con la verifica di storia di `prova_studio_mappa_pagina.py` e cinque
domande, una per tipo:
- telefono a 390×844: la sezione «Prove» con «Verifica finta»; la prova aperta con le domande e
  **nessuna risposta attesa** nella pagina né nello stato; le risposte (le scelte coi tasti, il
  testo nei campi) salvate sul server; a 320×693, anche col testo al 125 %, niente di lato e tocchi
  ≥ 44 px; «Consegna»: la correzione con l'esito a parole e la risposta attesa, i tentativi del
  codice nel db; «Era giusta» su una risposta da rivedere (fonte «persona»); «Le domande» e
  «Scrivi una domanda» (l'HTML resta testo);
- il PC personale: la sezione «Prove» e l'elenco delle domande;
- nessun errore JavaScript né violazione della CSP.
Con CALLIOPE_FOTO=<cartella> gli screenshot. ~20 s.

    python prove/prova_studio_prove_pagina.py
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

import prova_studio_mappa_pagina as PMP

B = PMP.B
TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-prove-pagina-"))
LEO, ANDREA, REG = PMP.LEO, PMP.ANDREA, PMP.REG
verifica, aspetta, misure = B.verifica, B.aspetta, PMP.misure
SALTATA = B.SALTATA
HTML = "<b>Chi</b> era Magellano?"
ATTESE = ("Juan Sebastián Elcano", "Servivano a conservare")


class TP(B.T):
    """Prima di toccare un tasto delle prove aspetta che la pagina non sia in attesa."""

    def tocca(self, sel):
        aspetta(lambda: not self.v("!!document.querySelector('.studio-h-prove button:disabled')"), 6)
        return super().tocca(sel)


def testo(t) -> str:
    return t.v("(document.querySelector('.studio-h-prove') || {}).innerText || ''") or ""


def prepara(st):
    vid, _sk = PMP.prepara(st)
    a = [x["id"] for x in st.argomenti(LEO, vid)]
    st.aggiungi_domanda(LEO, vid, "scelta", "Da dove partì Colombo?", "Palos",
                        ["Palos", "Lisbona", "Genova"], argomento=a[2])
    st.aggiungi_domanda(LEO, vid, "vero_falso", "Magellano finì il giro del mondo.", "falso",
                        argomento=a[4])
    st.aggiungi_domanda(LEO, vid, "numero", "In che anno partì Colombo?", "1492", argomento=a[2])
    st.aggiungi_domanda(LEO, vid, "parole", "Chi completò il giro?", ATTESE[0],
                        chiave=["Elcano"], argomento=a[4])
    st.aggiungi_domanda(LEO, vid, "aperta", "Perché le spezie erano preziose?",
                        ATTESE[1] + " i cibi", argomento=a[0])
    return vid


RISPOSTE = {"Da dove partì Colombo?": ("radio", "a"), "Magellano finì il giro del mondo.":
            ("radio", "falso"), "In che anno partì Colombo?": ("campo", "1492"),
            "Chi completò il giro?": ("campo", "Elcano"),
            "Perché le spezie erano preziose?": ("campo", "per conservare il cibo")}


def apri(t):
    t.v("location.hash = '#/cose'; 1")
    aspetta(lambda: t.v("!!document.querySelector('#tessere [data-tessera=\"studio\"]:not(.presto)')"), 10)
    t.tocca('#tessere [data-tessera="studio"]')
    return aspetta(lambda: t.v("!!document.querySelector('.studio-h-prove')"), 8)


def scenario_telefono(t, st, vid):
    T_ = "window.calliopeTelefono"
    verifica("pagina caricata e collegata", bool(aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)))
    verifica("la home: la sezione «Prove» con «Verifica finta»", bool(apri(t))
             and t.v("!!document.querySelector('.studio-h-prove button[data-prove=\"inizia\"]')"),
             testo(t))
    t.tocca('.studio-h-prove button[data-prove="inizia"]')
    ok = aspetta(lambda: t.v("document.querySelectorAll('.studio-p-prova .studio-p-voce').length") == 5, 8)
    el = testo(t)
    stato = json.dumps(t.v("window.CalliopeStudio && window.CalliopeStudio.stato ? "
                           "window.CalliopeStudio.stato() : {}") or {}, ensure_ascii=False)
    verifica("la prova aperta: cinque domande, il tempo, nessuna risposta attesa (pagina e stato)",
             bool(ok) and "Mancano 20 minuti" in el and not any(x in el for x in ATTESE)
             and not any(x in stato for x in ATTESE), el[:400])
    misure(t, "390×844 con la verifica finta")
    B.foto(t, "studio-prove-390x844.png")
    for dom, (come, val) in RISPOSTE.items():
        sel = json.dumps(dom)
        if come == "radio":
            t.v(f"(() => {{ const li = [...document.querySelectorAll('.studio-p-voce')].find((x) => "
                f"x.querySelector('.studio-c-domanda').textContent === {sel}); const r = li.querySelector("
                f"'input[value=\"{val}\"]'); r.click(); return 1; }})()")
        else:
            t.v(f"(() => {{ const li = [...document.querySelectorAll('.studio-p-voce')].find((x) => "
                f"x.querySelector('.studio-c-domanda').textContent === {sel}); const c = li.querySelector("
                f"'.studio-c-campo'); c.value = {json.dumps(val)}; c.dispatchEvent(new Event('input', "
                f"{{bubbles: true}})); c.dispatchEvent(new Event('change', {{bubbles: true}})); return 1; }})()")
    pid = st.dati.uno("SELECT id FROM studio_prove")["id"]
    ok = aspetta(lambda: all(x["risposta"] for x in st.vista_prova(LEO, pid)["voci"]), 8)
    verifica("le risposte salvate sul server, senza esito", bool(ok)
             and all("esito" not in x for x in st.vista_prova(LEO, pid)["voci"]))
    B.dimensione(t, 320, 693)
    t.v("document.querySelector('.studio-h-prove').scrollIntoView({block: 'start'}); 1")
    misure(t, "320×693 con la verifica finta")
    B.foto(t, "studio-prove-320x693.png")
    t.v("document.documentElement.style.fontSize = '125%'; 1")
    t.v("document.querySelector('.studio-h-prove').scrollIntoView({block: 'start'}); 1")
    misure(t, "320×693 con la verifica finta e il testo grande")
    t.v("document.documentElement.style.fontSize = ''; 1")
    B.dimensione(t, 390, 844)
    t.tocca('.studio-h-prove button[data-prove="consegna"]')
    ok = aspetta(lambda: "Risposta attesa" in testo(t), 8)
    el = testo(t)
    tent = st.dati.tutti("SELECT * FROM studio_tentativi")
    verifica("«Consegna»: la correzione con l'esito a parole e la risposta attesa",
             bool(ok) and "risposto giusto a 4 domande su 5" in el and "da rivedere" in el
             and ATTESE[0] in el, el[:500])
    verifica("i tentativi del codice nel db", len(tent) == 4
             and all(x["fonte"] == "codice" and x["tipo"] == "verifica_finta" for x in tent), str(tent))
    misure(t, "390×844 con la correzione")
    B.foto(t, "studio-prove-correzione-390x844.png")
    # Dopo la consegna la home si ricarica e si ridisegna: si tocca a pagina ferma
    aspetta(lambda: t.v("!!document.querySelector('.studio-h-prove button[data-prove=\"rivedi\"]')"), 6)
    time.sleep(0.6)
    t.tocca('.studio-h-prove button[data-prove="rivedi"][data-dati*="giusto"]')
    ok = aspetta(lambda: len(st.dati.tutti("SELECT * FROM studio_tentativi")) == 5, 8)
    tent = st.dati.tutti("SELECT * FROM studio_tentativi")
    verifica("«Era giusta» sulla risposta da rivedere: un tentativo della persona, i tasti spariscono",
             bool(ok) and tent[-1]["fonte"] == "persona"
             and not t.v("!!document.querySelector('.studio-h-prove button[data-prove=\"rivedi\"]')"))
    t.tocca('.studio-h-prove button[data-prove="chiudi"]')
    aspetta(lambda: t.v("!!document.querySelector('.studio-h-prove button[data-prove=\"domande\"]')"), 6)
    t.tocca('.studio-h-prove button[data-prove="domande"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('.studio-h-prove button[data-prove=\"scrivi\"]')"), 8)
    verifica("«Le domande»: l'elenco con le risposte, il tipo della prova vera", bool(ok)
             and "La prova vera: scritta" in testo(t) and ATTESE[0] in testo(t))
    t.tocca('.studio-h-prove button[data-prove="scrivi"]')
    aspetta(lambda: t.v("!!document.getElementById('studio-p-testo')"), 4)
    t.v("(() => { const s = document.getElementById('studio-p-tipo'); s.value = 'vero_falso';"
        " s.dispatchEvent(new Event('change', {bubbles: true})); return 1; })()")
    aspetta(lambda: t.v("!!document.getElementById('studio-p-vf')"), 4)
    t.v(f"(() => {{ const i = document.getElementById('studio-p-testo'); i.value = {json.dumps(HTML)};"
        " i.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()")
    # A pagina ferma (il cambio di tipo ridisegna il modulo), poi «Salva»
    time.sleep(0.4)
    t.tocca('.studio-h-prove button[data-prove="salva"]')
    ok = aspetta(lambda: any(d["testo"] == HTML for d in st.domande(LEO, vid)["domande"]), 10)
    verifica("«Scrivi una domanda»: salvata; l'HTML resta testo", bool(ok) and HTML in testo(t)
             and not t.v("!!document.querySelector('.studio-h-prove .studio-testo b b')"),
             f"{bool(ok)} {testo(t)[-300:]}")
    misure(t, "390×844 con le domande")


def scenario_pc(t):
    B.dimensione(t, 1440, 900)
    aspetta(lambda: t.v("!!window.calliopeSchermo"), 10)
    ok = apri(t)
    verifica("PC: la sezione «Prove»", bool(ok) and "L'ultima verifica finta" in testo(t), testo(t)[:300])
    t.tocca('.studio-h-prove button[data-prove="domande"]')
    ok = aspetta(lambda: t.v("document.querySelectorAll('.studio-h-prove .studio-c-voce').length") >= 5, 8)
    verifica("PC: l'elenco delle domande", bool(ok))
    t.v("document.querySelector('.studio-h-prove').scrollIntoView({block: 'start'}); 1")
    B.foto(t, "studio-prove-pc.png")


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
        _, token = srv.archivio.crea_con_token("telefono", proprietario="l1", proprietario_nome="Leo")
        from prova_parla_pc import CollFinto
        cfg.schermi_sezioni = True
        srv.collegati.append(CollFinto(5, "cameretta"))
        s_pc, t_pc = hub.archivio.crea_con_token("cameretta", proprietario="l1", proprietario_nome="Leo")
        hub.archivio.lega_satellite(s_pc["id"], 5)
        hub._rinfresca()
        pagina = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/telefono/", profilo="profilo-studio-prove",
                            opzioni=("--window-size=390,844",))
        t = TP(pagina)
        try:
            pagina._chiama("DOM.enable")
            aspetta(lambda: pagina.valuta("document.readyState") == "complete", 10)
            pagina.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
            pagina._chiama("Page.reload")
            time.sleep(0.5)
            B.dimensione(t, 390, 844)
            scenario_telefono(t, st, vid)
            pagina.pompa(0.3)
            errori = [r for r in pagina.log if r.startswith(("ECCEZIONE", "ERROR")) or "Content Security" in r]
            verifica("telefono: nessun errore JavaScript né violazione della CSP", not errori, "; ".join(errori)[:300])
        finally:
            pagina.chiudi()
        pc = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/#t={t_pc}", profilo="profilo-studio-prove-pc",
                        opzioni=("--window-size=1440,900",))
        tp = TP(pc)
        try:
            pc._chiama("DOM.enable")
            scenario_pc(tp)
            pc.pompa(0.3)
            errori = [r for r in pc.log if r.startswith(("ECCEZIONE", "ERROR")) or "Content Security" in r]
            verifica("PC: nessun errore JavaScript né violazione della CSP", not errori, "; ".join(errori)[:300])
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
