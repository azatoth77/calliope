import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""I premi dello Studio nella pagina vera (31/10, issue #296, epic #251; schermi/pagina/studio.js,
POST /api/studio/premi e /api/studio/duello).

Nel browser vero (Edge o Chromium senza finestra; senza si salta), il server degli schermi vero su
127.0.0.1, Leo (di fantasia) con la verifica di storia di `prova_studio_mappa_pagina.py`, cinque
carte ripassate oggi e una verifica finta consegnata e superata dal codice; Andrea è il tutore e
`studio_duelli` è acceso:
- il telefono di Andrea a 390×844: nella vista del tutore il blocco «Premi» con la serie di Leo,
  la stella e gli interruttori; «Duelli: spenti» toccato li accende (sul server); a 320×693 col
  testo al 125 % niente di lato e tocchi ≥ 44 px;
- il telefono di Leo: «I tuoi traguardi» con «Serie di studio: 1 giorno» e «Stelle: 1» (mai «0» né
  «persa»); «Proponi un duello» con Andrea (sul server); Andrea accetta e consegna; Leo apre il
  duello, nella pagina nessuna risposta attesa, risponde con dell'HTML (resta testo), consegna e
  vede i punti e le risposte attese; a 390, 320 e 125 %;
- nessun errore JavaScript né violazione della CSP.
Con CALLIOPE_FOTO=<cartella> gli screenshot. ~25 s.

    python prove/prova_studio_premi_pagina.py
"""

import json
import shutil
import tempfile
from pathlib import Path

import prova_studio_mappa_pagina as PMP
import prova_studio_tutore_pagina as PTU

B = PMP.B
TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-premi-pagina-"))
LEO, ANDREA, REG = PMP.LEO, PMP.ANDREA, PMP.REG
verifica, aspetta, misure = B.verifica, B.aspetta, PMP.misure
SALTATA = B.SALTATA
HTML = "<b>1490</b><img src=x onerror=alert(1)>"


class TT(B.T):
    """Prima di toccare un tasto aspetta che la pagina non sia in attesa."""

    def tocca(self, sel):
        aspetta(lambda: not self.v("!!document.querySelector('.studio-r button:disabled, "
                                   ".studio-t button:disabled')"), 6)
        return super().tocca(sel)


def testo(t, sel) -> str:
    return t.v(f"(document.querySelector({json.dumps(sel)}) || {{}}).innerText || ''") or ""


def prepara(st):
    vid, _sk = PMP.prepara(st)
    a = st._argomenti_numerati(vid)
    carte = [st.aggiungi_carta(LEO, vid, f"Carta {i}?", f"risposta {i}", argomento=a[i % len(a)]["id"])
             for i in range(5)]
    for c in carte:
        st.esito_carta(LEO, c, "non_sapevo")
    for i in range(3):
        st.aggiungi_domanda(LEO, vid, "numero", f"In che anno {i}?", str(1490 + i),
                            argomento=a[i]["id"])
    p = st.inizia_prova(LEO, vid)
    for x in p["voci"]:
        i = int(x["testo"].split()[-1][:-1])
        st.rispondi_prova(LEO, p["id"], x["n"], str(1490 + i) if x["testo"].startswith("In che")
                          else f"risposta {i}")
    st.consegna_prova(LEO, p["id"])
    return vid


def scenario_tutore(t, st, vid):
    T_ = "window.calliopeTelefono"
    verifica("telefono di Andrea: pagina caricata e collegata",
             bool(aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)))
    ok = PTU.apri_studio(t) and aspetta(lambda: t.v("!!document.querySelector('.studio-t button[data-tutore=\"apri\"]')"), 6)
    verifica("la verifica di Leo con «Vista del tutore»", bool(ok))
    t.tocca('.studio-t button[data-tutore="apri"]')
    ok = aspetta(lambda: "Premi" in testo(t, ".studio-t-premi"), 8)
    el = testo(t, ".studio-t-premi")
    verifica("la vista del tutore: «Premi» con la serie di Leo, la stella e gli interruttori",
             bool(ok) and "Serie di studio: 1 giorno" in el and "Stelle: 1" in el
             and "Duelli: spenti" in el and "Serie: accesa" in el, el[:400])
    misure(t, "390×844 col blocco dei premi")
    B.foto(t, "studio-premi-tutore-390x844.png")
    t.tocca('.studio-t-interruttori button[data-dati*="duelli"]')
    ok = aspetta(lambda: st.impostazioni_premi("l1")["duelli"], 6)
    aspetta(lambda: "Duelli: accesi" in testo(t, ".studio-t-premi"), 6)
    verifica("«Duelli: spenti» toccato: accesi per Leo sul server e sulla pagina",
             bool(ok) and "Duelli: accesi" in testo(t, ".studio-t-premi"))
    B.dimensione(t, 320, 693)
    t.v("document.querySelector('.studio-t-premi').scrollIntoView({block: 'start'}); 1")
    misure(t, "320×693 col blocco dei premi")
    t.v("document.documentElement.style.fontSize = '125%'; 1")
    misure(t, "320×693 col blocco dei premi e il testo grande")
    B.foto(t, "studio-premi-tutore-320x693-125.png")
    t.v("document.documentElement.style.fontSize = ''; 1")
    B.dimensione(t, 390, 844)


def scenario_leo(t, st, vid):
    T_ = "window.calliopeTelefono"
    verifica("telefono di Leo: pagina caricata e collegata",
             bool(aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)))
    ok = PTU.apri_studio(t) and aspetta(lambda: t.v("!!document.querySelector('.studio-r')"), 6)
    el = testo(t, ".studio-r")
    verifica("«I tuoi traguardi»: la serie e le stelle, mai «0» né «persa»", bool(ok)
             and "Serie di studio: 1 giorno" in el and "Stelle: 1" in el
             and "persa" not in el.lower() and "0 giorni" not in el, el[:400])
    verifica("la proposta di un duello: la verifica e Andrea",
             "con Andrea" in el and bool(t.v("!!document.querySelector('.studio-r button[data-premi=\"proponi\"]')")))
    misure(t, "390×844 di Leo coi premi")
    B.foto(t, "studio-premi-leo-390x844.png")
    t.tocca('.studio-r button[data-premi="proponi"]')
    ok = aspetta(lambda: st.dati.uno("SELECT * FROM studio_duelli WHERE da = 'l1' AND a = 'a1'"), 6)
    verifica("«Proponi un duello»: il duello nel db, proposto ad Andrea", bool(ok))
    did = (ok or {}).get("id")
    d = st.accetta_duello(ANDREA, did)
    for x in d["voci"]:
        st.rispondi_duello(ANDREA, did, x["n"], "1300")
    st.consegna_duello(ANDREA, did)
    t.v("window.CalliopePagine.studio.chiudi(); window.CalliopePagine.studio.apri(); 1")
    aspetta(lambda: t.v(f"!!document.querySelector('.studio-r-duello[data-duello=\"{did}\"] button[data-premi=\"apri\"]')"), 8)
    t.tocca(f'.studio-r-duello[data-duello="{did}"] button[data-premi="apri"]')
    ok = aspetta(lambda: t.v("document.querySelectorAll('[data-voce-duello]').length") or 0, 8)
    stato = t.v("window.CalliopeStudio.stato().premi") or {}
    verifica("il duello aperto da Leo: le domande, nessuna risposta attesa nella pagina",
             bool(ok) and (stato.get("dati") or {}).get("voci")
             and all("attesa" not in x and "esito" not in x for x in stato["dati"]["voci"])
             and "punti" not in (stato.get("dati") or {}))
    misure(t, "390×844 col duello aperto")
    n = int(ok or 0)
    for i in range(n):
        t.v(f"(() => {{ const i = document.querySelectorAll('[data-voce-duello]')[{i}]; i.value = {json.dumps(HTML)};"
            " i.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()")
    t.tocca(f'.studio-r-duello[data-duello="{did}"] button[data-premi="consegna"]')
    ok = aspetta(lambda: (st.dati.uno("SELECT stato FROM studio_duelli WHERE id = ?", (did,)) or {})
                 .get("stato") == "finito", 8)
    verifica("«Consegna»: il duello finito sul server", bool(ok))
    aspetta(lambda: "Risposta attesa" in testo(t, ".studio-r-pannello"), 8)
    el = testo(t, ".studio-r-pannello")
    verifica("a duello finito: i punti di tutti e due e le risposte attese, l'HTML resta testo",
             "Tu: " in el and "Andrea: 0 su" in el and "Risposta attesa" in el
             and "<b>1490</b>" in el and not t.v("!!document.querySelector('.studio-r img, .studio-r-pannello b')")
             and "vint" not in el and "pers" not in el, el[:400])
    B.dimensione(t, 320, 693)
    t.v("document.querySelector('.studio-r').scrollIntoView({block: 'start'}); 1")
    misure(t, "320×693 di Leo coi premi e il duello")
    t.v("document.documentElement.style.fontSize = '125%'; 1")
    misure(t, "320×693 di Leo coi premi e il testo grande")
    B.foto(t, "studio-premi-leo-320x693-125.png")
    t.v("document.documentElement.style.fontSize = ''; 1")


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
        cfg.studio_duelli = True
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
        hub._rinfresca()
        url = f"http://127.0.0.1:{web.port}/telefono/"
        try:
            pagina = PTU.apri_pagina(PTP, exe, url, "profilo-studio-premi-a", tok_a, 390)
            try:
                t = TT(pagina)
                B.dimensione(t, 390, 844)
                scenario_tutore(t, st, vid)
                PTU.errori_di(pagina, "telefono di Andrea")
            finally:
                pagina.chiudi()
            pagina = PTU.apri_pagina(PTP, exe, url, "profilo-studio-premi-l", tok_l, 390)
            try:
                t = TT(pagina)
                B.dimensione(t, 390, 844)
                scenario_leo(t, st, vid)
                PTU.errori_di(pagina, "telefono di Leo")
            finally:
                pagina.chiudi()
        finally:
            web.ferma()
            srv.ferma()
            st.close()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not B.ERRORI else f"\n{len(B.ERRORI)} prove non riuscite.")
    return 1 if B.ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
