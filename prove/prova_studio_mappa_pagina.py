import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""La mappa concettuale dello Studio nella pagina vera (30/10, passo 7, issue #247, epic #251;
schermi/pagina/studio.js, POST /api/studio/mappa, /api/vista).

Nel browser vero (Edge o Chromium senza finestra; senza si salta), server degli schermi veri su
127.0.0.1, `studio_modo: attivo`, Leo (seconda media, di fantasia) con una verifica di storia e lo
scheletro scritto a mano dal tutore Andrea e confermato (un concetto con dell'HTML):
- telefono a 390×844 e a 320×693: «Mappa» nella home, «La mappa» apre il pannello con l'elenco
  (lo scheletro); «La mia mappa» → «Parti da qui»: le caselle vuote coi campi, le parole da mettere;
  «Metti» e «Controlla» dall'elenco: gli esiti a parole e i tentativi nel db, dal codice;
  «+ Concetto» e «Collega» coi moduli (due elenchi, niente trascinamento); la vista «Mappa»: l'SVG
  con un gruppo per concetto, il testo con textContent (l'HTML resta testo), il tocco su un concetto
  apre il suo pannello con le frecce per spostarlo; «Scarica PDF»; niente di lato, tocchi ≥ 44 px,
  testo ≥ 16 px (le note e le etichette a parte);
- la vista «mappa» arriva al server (`hub.viste_studio`);
- il PC personale: la mappa in orizzontale nella colonna centrale;
- nessun errore JavaScript né violazione della CSP.
Con CALLIOPE_FOTO=<cartella> gli screenshot. ~20 s.

    python prove/prova_studio_mappa_pagina.py
"""

import datetime
import json
import shutil
import tempfile
import time
from pathlib import Path

import prova_studio_pagina_telefono as B

TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-mappa-pagina-"))
QUI = Path(__file__).resolve().parent
MAT = json.loads((QUI / "manuali" / "studio" / "storia.json").read_text("utf-8"))
ANDREA = B.Prof("a1", "Andrea")
LEO = B.Prof("l1", "Leo", nascita="2014-03-01", tutori=["a1"])
REG = B.Registro(ANDREA, LEO)
verifica, aspetta = B.verifica, B.aspetta
SALTATA = B.SALTATA
HTML = "<img src=x onerror=alert(1)>Le spezie"

MISURA_HOME = B.MISURA.replace("document.getElementById('studio')",
                               "document.getElementById('studio-home')")


def misure(t, etichetta):
    m = t.v(MISURA_HOME) or {}
    verifica(f"{etichetta}: niente fuori dallo schermo né di lato", not m.get("fuori") and not m.get("lato"),
             json.dumps(m.get("fuori")))
    verifica(f"{etichetta}: tocchi ≥ 44 px", not m.get("tocchi"), json.dumps(m.get("tocchi")))
    piccoli = [x for x in (m.get("piccoli") or []) if "nota" not in str(x[0]) and "quando" not in str(x[0])
               and "etichetta" not in str(x[0]) and "studio-h-" not in str(x[0])]
    verifica(f"{etichetta}: testo ≥ 16 px (le note e le etichette a parte)", not piccoli, json.dumps(piccoli))


class TM(B.T):
    """Come B.T, ma prima di toccare un tasto della mappa aspetta che la pagina non sia in attesa
    di una risposta (i tasti sono spenti finché il server non risponde)."""

    def tocca(self, sel):
        aspetta(lambda: not self.v("!!document.querySelector('.studio-h-mappa button:disabled')"), 6)
        return super().tocca(sel)


def prepara(st):
    vid = st.crea_verifica(LEO, "Storia", st._oggi() + datetime.timedelta(days=7),
                           argomento="Le scoperte geografiche")
    mid = st.aggiungi_materiale(LEO, vid, "foto", "Libro")
    ids = {p["id"]: st.aggiungi_pagina(LEO, mid, numero=p["numero"], stato="letta", testo=p["testo"],
                                       metodo="ocr") for p in MAT["pagine"]}
    for a in MAT["argomenti"][:6]:
        st.aggiungi_argomento(LEO, vid, a["titolo"], [ids[x] for x in a["pagine"]])
    st.conferma_argomenti(LEO, vid)
    aids = [a["id"] for a in st.argomenti(LEO, vid)]
    sk = st.scrivi_scheletro(ANDREA, vid)
    n = {}
    for t, a, p in (("Le scoperte geografiche", 0, "p112"), ("Cristoforo Colombo", 2, "p114"),
                    ("America", 3, "p115"), (HTML, 0, "p112"), ("Il Portogallo", 1, "p113"),
                    ("Il trattato di Tordesillas", 4, "p115")):
        n[t] = st.nodo_mappa(ANDREA, sk, t, argomento=aids[a], pagine=[ids[p]])
    for da, a, vb in (("Le scoperte geografiche", "Cristoforo Colombo", "con"),
                      ("Cristoforo Colombo", "America", "arriva in"),
                      ("Le scoperte geografiche", HTML, "per cercare"),
                      ("Il Portogallo", "Le scoperte geografiche", "comincia"),
                      ("Il trattato di Tordesillas", "America", "divide")):
        st.collega(ANDREA, sk, n[da], n[a], vb)
    st.conferma_scheletro(ANDREA, sk)
    st.riordina_mappa(ANDREA, sk)
    return vid, sk


def apri_mappa(t):
    t.v("location.hash = '#/cose'; 1")
    aspetta(lambda: t.v("!!document.querySelector('#tessere [data-tessera=\"studio\"]:not(.presto)')"), 10)
    t.tocca('#tessere [data-tessera="studio"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('.studio-h-mappa button[data-mappa=\"apri\"]')"), 8)
    verifica("la home: la sezione «Mappa» con «La mappa»", bool(ok))
    riga = t.v("(document.querySelector('.studio-h-mappa') || {}).innerText || ''") or ""
    verifica("la riga della mappa: «Lo scheletro è pronto: fai la tua mappa.»",
             "Lo scheletro è pronto" in riga, riga)
    t.tocca('.studio-h-mappa button[data-mappa="apri"]')
    return aspetta(lambda: t.v("!!document.querySelector('.studio-m .studio-m-elenco')"), 8)


def scenario_telefono(t, hub, st, vid, sk):
    T_ = "window.calliopeTelefono"
    verifica("pagina caricata e collegata", bool(aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)))
    verifica("«La mappa»: il pannello con lo scheletro a elenco", bool(apri_mappa(t)))
    el = t.v("document.querySelector('.studio-m').innerText") or ""
    verifica("lo scheletro: chi l'ha fatto, i concetti e i collegamenti a parole",
             "scritto a mano" in el and "confermato" in el and "→ arriva in → America" in el, el[:300])
    verifica("l'HTML di un concetto resta testo (nessuna immagine, il testo intero)",
             HTML in el and not t.v("!!document.querySelector('.studio-m img')"))
    vs = aspetta(lambda: any((hub.viste_studio.di(k) or [{}])[0].get("vista") == "mappa"
                             for k in list(hub.viste_studio._d)), 4)
    verifica("la vista «mappa» arriva al server", bool(vs))
    # La mia mappa, dall'elenco
    t.tocca('button[data-mappa="quale"][data-dati*="mia"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('button[data-mappa=\"inizia\"]')"), 6)
    verifica("«La mia mappa»: l'aiuto e «Parti da qui: fai la tua»", bool(ok) and "Quanto aiuto" in
             (t.v("document.querySelector('.studio-m').innerText") or ""))
    t.tocca('button[data-mappa="aiuto"][data-dati*="tanto"]')
    t.tocca('button[data-mappa="inizia"]')
    ok = aspetta(lambda: t.v("document.querySelectorAll('.studio-m-elenco input[data-casella]').length === 2"), 8)
    verifica("«Parti da qui» con «Tanto aiuto»: due caselle coi campi e le parole da mettere",
             bool(ok) and "Le parole da mettere" in (t.v("document.querySelector('.studio-m').innerText") or ""))
    mia = st.vista_mappe(LEO, vid)["mia"]
    atteso = {x["id"]: x["testo"] for x in st.vista_mappe(LEO, vid)["scheletro"]["nodi"]}
    cas = [x["id"] for x in mia["nodi"] if x["casella"]]
    # La prima giusta, la seconda sbagliata: si scrive nel campo, poi «Metti»
    for cid, testo in ((cas[0], atteso[cas[0]]), (cas[1], "Vasco da Gama")):
        t.v(f"(() => {{ const i = document.querySelector('input[data-casella=\"{cid}\"]'); i.value = {json.dumps(testo)};"
            " i.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()")
        t.tocca(f'button[data-mappa="riempi"][data-dati*="{cid}"]')
        aspetta(lambda c=cid, x=testo: next((n["testo"] for n in st.vista_mappe(LEO, vid)["mia"]["nodi"]
                                              if n["id"] == c), "") == x, 6)
    verifica("«Metti»: le parole nelle caselle, sul server",
             [n["testo"] for n in st.vista_mappe(LEO, vid)["mia"]["nodi"] if n["id"] in cas]
             == [atteso[cas[0]], "Vasco da Gama"])
    misure(t, "390×844 con la mia mappa a elenco")
    B.foto(t, "studio-mappa-elenco-390x844.png")
    t.tocca('button[data-mappa="controlla"]')
    ok = aspetta(lambda: "Controllata" in (t.v("(document.querySelector('.studio-m-stato') || {}).textContent || ''") or ""), 8)
    el = t.v("document.querySelector('.studio-m').innerText") or ""
    tent = st.dati.tutti("SELECT * FROM studio_tentativi")
    verifica("«Controlla»: gli esiti a parole («giusta», «da rivedere») e i tentativi del codice",
             bool(ok) and "giusta" in el and "da rivedere" in el and len(tent) == 2
             and {x["fonte"] for x in tent} == {"codice"}, el[:400])
    # + Concetto e Collega coi moduli
    t.tocca('button[data-mappa="nuovo"]')
    aspetta(lambda: t.v("!!document.getElementById('studio-m-testo')"), 4)
    t.v("(() => { const i = document.getElementById('studio-m-testo'); i.value = 'Amerigo Vespucci';"
        " i.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()")
    t.tocca('button[data-mappa="salva"]')
    ok = aspetta(lambda: any(n["testo"] == "Amerigo Vespucci" for n in st.vista_mappe(LEO, vid)["mia"]["nodi"]), 6)
    verifica("«+ Concetto»: il concetto suo nella mappa", bool(ok))
    nuovo = next(n["id"] for n in st.vista_mappe(LEO, vid)["mia"]["nodi"] if n["testo"] == "Amerigo Vespucci")
    america = next(n["id"] for n in st.vista_mappe(LEO, vid)["mia"]["nodi"] if n["testo"] == "America"
                   or atteso.get(n["id"]) == "America")
    t.tocca('button[data-mappa="collega"]')
    aspetta(lambda: t.v("!!document.getElementById('studio-m-da')"), 4)
    t.v(f"(() => {{ for (const [id, v] of [['studio-m-da', '{nuovo}'], ['studio-m-a', '{america}'], ['studio-m-verbo', 'dà il nome a']]) {{"
        " const e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event(e.tagName === 'SELECT' ? 'change' : 'input', {bubbles: true})); }"
        " return 1; })()")
    misure(t, "390×844 col modulo «Collega»")
    t.tocca('button[data-mappa="salva"]')
    ok = aspetta(lambda: any(c["verbo"] == "dà il nome a" for c in st.vista_mappe(LEO, vid)["mia"]["collegamenti"]), 6)
    verifica("«Collega» con due elenchi e il verbo (niente trascinamento)", bool(ok))
    # La vista «Mappa»
    t.tocca('button[data-mappa="vista"][data-dati*="mappa"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('svg.studio-m-tela')"), 6)
    n_g = t.v("document.querySelectorAll('svg.studio-m-tela .studio-m-nodo').length")
    verifica("la vista «Mappa»: l'SVG con un gruppo per concetto, in verticale sul telefono",
             bool(ok) and n_g == len(st.vista_mappe(LEO, vid)["mia"]["nodi"])
             and t.v("document.querySelector('svg.studio-m-tela').getAttribute('viewBox')") == "0 0 600 840", str(n_g))
    verifica("nella mappa il testo è testo SVG (textContent), l'HTML resta testo",
             t.v("[...document.querySelectorAll('svg.studio-m-tela tspan')].some((s) => s.textContent.includes('<img'))")
             and not t.v("!!document.querySelector('svg.studio-m-tela img, svg.studio-m-tela foreignObject')"))
    t.tocca(f'svg.studio-m-tela .studio-m-nodo[data-nodo="{nuovo}"]')
    ok = aspetta(lambda: t.v(f"!!document.querySelector('.studio-m-pannello[data-nodo=\"{nuovo}\"]')"), 4)
    verifica("il tocco su un concetto apre il suo pannello, con le frecce per spostarlo",
             bool(ok) and t.v("document.querySelectorAll('.studio-m-pannello button[data-mappa=\"sposta\"]').length") == 4)
    prima = next(n["x"] for n in st._riga_mappa(st.vista_mappe(LEO, vid)["mia"]["id"])["nodi"] if n["id"] == nuovo)
    t.tocca('.studio-m-pannello button[data-mappa="sposta"][aria-label="Sposta a destra"]')
    ok = aspetta(lambda: next(n["x"] for n in st._riga_mappa(st.vista_mappe(LEO, vid)["mia"]["id"])["nodi"]
                              if n["id"] == nuovo) != prima, 6)
    verifica("«Sposta a destra» (senza trascinare): il concetto si sposta sul server", bool(ok))
    misure(t, "390×844 con la mappa disegnata")
    B.foto(t, "studio-mappa-390x844.png")
    t.tocca('button[data-mappa="pdf"]')
    ok = aspetta(lambda: "PDF" in (t.v("(document.querySelector('.studio-m-stato') || {}).textContent || ''") or ""), 8)
    verifica("«Scarica PDF»: il PDF della mia mappa", bool(ok))
    B.dimensione(t, 320, 693)
    t.v("document.querySelector('.studio-h-mappa').scrollIntoView({block: 'start'}); 1")
    misure(t, "320×693 con la mappa disegnata")
    t.tocca('button[data-mappa="vista"][data-dati*="elenco"]')
    aspetta(lambda: t.v("!!document.querySelector('.studio-m-elenco')"), 4)
    misure(t, "320×693 con l'elenco")
    B.foto(t, "studio-mappa-elenco-320x693.png")
    B.dimensione(t, 390, 844)
    st_js = t.v("window.CalliopeStudio.stato().mappa") or {}
    verifica("lo stato della pagina: la mappa aperta, l'elenco", st_js.get("vista") == "elenco"
             and st_js.get("quale") == "mia", str(st_js))
    # A memoria (revisione della PR #326): mentre è aperta lo scheletro e la mia mappa non si vedono
    t.tocca('button[data-mappa="quale"][data-dati*="memoria"]')
    aspetta(lambda: t.v("!!document.querySelector('button[data-mappa=\"inizia\"]')"), 6)
    t.tocca('button[data-mappa="inizia"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('.studio-m-elenco input[data-casella]')"), 8)
    schede = t.v("[...document.querySelectorAll('button[data-mappa=\"quale\"]')].map((b) => b.textContent)") or []
    el = t.v("document.querySelector('.studio-m').innerText") or ""
    nomi = [x["testo"] for x in st._riga_mappa(sk)["nodi"]]
    verifica("a memoria aperta: solo la sua scheda, lo scheletro e la mia mappa nascosti, nessun testo "
             "atteso nella pagina", bool(ok) and schede == ["A memoria"]
             and st.vista_mappe(LEO, vid)["a_memoria"]
             and all(x["nodi"] == 0 for x in (t.v("window.CalliopeStudio.stato().mappa.mappe") or [])
                     if x["quale"] in ("scheletro", "mia"))
             and "tornano dopo «Controlla»" in el, f"{schede} {el[:200]} {nomi}")
    t.tocca('button[data-mappa="controlla"]')
    ok = aspetta(lambda: len(t.v("[...document.querySelectorAll('button[data-mappa=\"quale\"]')]"
                                  ".map((b) => b.textContent)") or []) == 4, 8)
    verifica("dopo «Controlla» le schede tornano (con «Da zero», dal passo 7c)", bool(ok))
    t.tocca('button[data-mappa="quale"][data-dati*="scheletro"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('button[data-mappa=\"chiedi_riapri\"]')"), 6)
    verifica("lo scheletro confermato con le copie: niente «+ Concetto», c'è «Riapri lo scheletro»",
             bool(ok) and not t.v("!!document.querySelector('button[data-mappa=\"nuovo\"]')"))


def scenario_pc(t, hub):
    B.dimensione(t, 1440, 900)
    T_ = "window.calliopeSchermo"
    aspetta(lambda: t.v(f"!!{T_}"), 10)
    t.v("location.hash = '#/cose'; 1")
    aspetta(lambda: t.v("!!document.querySelector('#tessere [data-tessera=\"studio\"]:not(.presto)')"), 10)
    t.tocca('#tessere [data-tessera="studio"]')
    aspetta(lambda: t.v("!!document.querySelector('.studio-h-mappa button[data-mappa=\"apri\"]')"), 8)
    t.tocca('.studio-h-mappa button[data-mappa="apri"]')
    aspetta(lambda: t.v("!!document.querySelector('.studio-m')"), 8)
    t.tocca('button[data-mappa="vista"][data-dati*="mappa"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('svg.studio-m-tela')"), 6)
    verifica("PC: la mappa disegnata in orizzontale nella colonna centrale", bool(ok)
             and t.v("document.querySelector('svg.studio-m-tela').getAttribute('viewBox')") == "0 0 1000 620")
    t.v("document.querySelector('svg.studio-m-tela').scrollIntoView({block: 'start'}); 1")
    B.foto(t, "studio-mappa-pc.png")


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
        vid, sk = prepara(st)
        _, token = srv.archivio.crea_con_token("telefono", proprietario="l1", proprietario_nome="Leo")
        from prova_parla_pc import CollFinto
        cfg.schermi_sezioni = True
        srv.collegati.append(CollFinto(5, "cameretta"))
        s_pc, t_pc = hub.archivio.crea_con_token("cameretta", proprietario="l1", proprietario_nome="Leo")
        hub.archivio.lega_satellite(s_pc["id"], 5)
        hub._rinfresca()
        pagina = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/telefono/", profilo="profilo-studio-mappa",
                            opzioni=("--window-size=390,844",))
        t = TM(pagina)
        try:
            pagina._chiama("DOM.enable")
            aspetta(lambda: pagina.valuta("document.readyState") == "complete", 10)
            pagina.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
            pagina._chiama("Page.reload")
            time.sleep(0.5)
            B.dimensione(t, 390, 844)
            scenario_telefono(t, hub, st, vid, sk)
            pagina.pompa(0.3)
            errori = [r for r in pagina.log if r.startswith(("ECCEZIONE", "ERROR")) or "Content Security" in r]
            verifica("telefono: nessun errore JavaScript né violazione della CSP", not errori, "; ".join(errori)[:300])
        finally:
            pagina.chiudi()
        pc = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/#t={t_pc}", profilo="profilo-studio-mappa-pc",
                        opzioni=("--window-size=1440,900",))
        tp = TM(pc)
        try:
            pc._chiama("DOM.enable")
            scenario_pc(tp, hub)
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
