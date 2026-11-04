import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Le mappe delle parti dello Studio nella pagina vera (04/11, issue #385, epic #251;
schermi/pagina/studio.js «Le parti», POST /api/studio/mappa).

Nel browser vero (Edge o Chromium senza finestra; senza si salta), il server degli schermi vero su
127.0.0.1, Leo (di fantasia) con la verifica di storia e le mappe generate col lettore finto:
- telefono a 390×844: la generale con quanti argomenti ha e quello che resta fuori; la scheda
  «Le parti» con un tasto per argomento; una parte si apre e si chiude, lo schema coi livelli e i
  verbi; l'HTML nel testo resta testo; niente da cambiare (né «+ Concetto», né «Cambia», né
  «Conferma»); la vista «Mappa» in SVG allungata con 16 concetti, un concetto si legge toccandolo; la
  parte senza mappa lo dice (pagine con istruzioni, non riuscita);
- a 320×693 anche col testo al 125 %: niente di lato, tocchi ≥ 44 px, testo ≥ 16 px;
- mentre fa una mappa da zero le parti non ci sono (né nella pagina né nello stato);
- il PC personale: la parte disegnata in orizzontale;
- nessun errore JavaScript né violazione della CSP.
Con CALLIOPE_FOTO=<cartella> gli screenshot. ~25 s.

    python prove/prova_studio_mappa_parti_pagina.py
"""

import datetime
import json
import shutil
import tempfile
import time
from pathlib import Path

import prova_studio_mappa_pagina as PMP

B = PMP.B
TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-parti-pagina-"))
LEO, ANDREA, REG = PMP.LEO, PMP.ANDREA, PMP.REG
verifica, aspetta, misure = B.verifica, B.aspetta, PMP.misure
SALTATA = B.SALTATA
HTML = "<img src=x onerror=alert(1)>Spezie"
MOLTI = [f"Concetto lungo numero {i}" for i in range(2, 17)]


def n_(i, testo, livello_radice=False):
    return {"id": i, "testo": testo, "pagine": [], "argomento": None, "autore": "modello",
            "stato": "proposto", "avvisi": [], "da": None, "casella": False,
            **({"radice": True} if livello_radice else {})}


def prepara(st):
    """La verifica di storia coi suoi argomenti, la generale e le parti scritte da `proponi_*`,
    come le scrive il lettore: un argomento fuori dalla generale, uno senza pagine pulite, uno non
    riuscito, uno con 16 concetti."""
    from calliope.studio import argomenti as A
    from calliope.studio import genera as G
    from calliope.studio import mappa_genera as MG
    MAT = PMP.MAT
    vid = st.crea_verifica(LEO, "Storia", st._oggi() + datetime.timedelta(days=7),
                           argomento="Le scoperte geografiche")
    mid = st.aggiungi_materiale(LEO, vid, "foto", "Libro")
    ids = {p["id"]: st.aggiungi_pagina(LEO, mid, numero=p["numero"], stato="letta", testo=p["testo"],
                                       metodo="ocr") for p in MAT["pagine"]}
    st.dati.scrivi("UPDATE studio_pagine SET avvisi = ? WHERE id = ?",
                   (json.dumps(["istruzioni"]), ids["p117"]))
    for titolo, pag in (("Le cause delle scoperte geografiche", "p112"), ("Il Portogallo e la rotta africana", "p113"),
                        ("Cristoforo Colombo e il Nuovo Mondo", "p114"), ("I diari di bordo", "p117"),
                        ("Il trattato di Tordesillas", "p115")):
        st.aggiungi_argomento(LEO, vid, titolo, [ids[pag]])
    st.conferma_argomenti(LEO, vid)
    args = st._argomenti_per_carte(vid)
    pagine = st._pagine_di(vid)
    rif, arif = A.riferimenti(pagine), G.argomenti_rif(args)
    triple = [{"da": "Le scoperte geografiche", "relazione": "nascono da", "a": "Le spezie",
               "argomento": "A1", "pagine": ["P2"]},
              {"da": "Le scoperte geografiche", "relazione": "cominciano con", "a": "Il Portogallo",
               "argomento": "A2", "pagine": ["P3"]},
              {"da": "Le scoperte geografiche", "relazione": "portano a", "a": "Cristoforo Colombo",
               "argomento": "A3", "pagine": ["P4"]}]
    nodi, coll = MG.scheletro(triple, rif, arif, 20, titolo="Le scoperte geografiche")
    firma = MG.firma(args, pagine, "attiva")
    assert st.proponi_mappa(vid, firma, nodi, coll, MG.PROPOSTO, "attiva") is not None

    def parte(a, nodi_, coll_, esito=MG.PROPOSTO, esclusi=0, fuori=0):
        MG.disponi(nodi_, coll_)
        assert st.proponi_parte(vid, a["id"], MG.firma_parte(a, pagine, "attiva"), nodi_, coll_, esito,
                                "attiva", esclusi=esclusi, fuori=fuori) is not None
    n1 = [n_(1, args[0]["titolo"], True), n_(2, "Costantinopoli"), n_(3, HTML), n_(4, "Le caravelle")]
    c1 = [{"id": 1, "da": 1, "a": 2, "verbo": "nascono dalla caduta di", "pagine": [ids["p112"]],
           "autore": "modello", "stato": "proposto", "avvisi": []},
          {"id": 2, "da": 2, "a": 3, "verbo": "blocca il commercio di", "pagine": [], "autore": "modello",
           "stato": "proposto", "avvisi": []},
          {"id": 3, "da": 4, "a": 1, "verbo": "rendono possibili", "pagine": [], "autore": "modello",
           "stato": "proposto", "avvisi": []}]
    parte(args[0], n1, c1, esclusi=2, fuori=3)
    molti = [n_(1, args[2]["titolo"], True)] + [n_(i, t) for i, t in enumerate(MOLTI, 2)]
    cm = [{"id": i, "da": 1 if i < 7 else i - 5, "a": i + 1, "verbo": f"porta al {i}", "pagine": [],
           "autore": "modello", "stato": "proposto", "avvisi": []} for i in range(1, 16)]
    parte(args[2], molti, cm)
    parte(args[1], [], [], esito=MG.ERRORE)
    parte(args[3], [], [], esito=MG.SOLO_ISTRUZIONI)
    parte(args[4], [], [], esito=MG.VUOTO, fuori=4)
    return vid, args


def testo(t) -> str:
    return t.v("(document.querySelector('.studio-m') || {}).innerText || ''") or ""


def apri_parti(t):
    t.v("location.hash = '#/cose'; 1")
    aspetta(lambda: t.v("!!document.querySelector('#tessere [data-tessera=\"studio\"]:not(.presto)')"), 10)
    t.tocca('#tessere [data-tessera="studio"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('.studio-h-mappa button[data-mappa=\"apri\"]')"), 8)
    t.tocca('.studio-h-mappa button[data-mappa="apri"]')
    return bool(ok) and aspetta(lambda: t.v("!!document.querySelector('.studio-m .studio-m-elenco')"), 8)


def apri(t, argomento):
    t.tocca(f'button[data-mappa="parte"][data-dati*=\'"argomento":{argomento}\']')


def scenario_telefono(t, st, vid, args):
    T_ = "window.calliopeTelefono"
    verifica("pagina caricata e collegata", bool(aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)))
    riga = ""
    verifica("«La mappa»: il pannello", bool(apri_parti(t)), "; ".join(t.p.log)[:400])
    riga = t.v("(document.querySelector('.studio-h-mappa') || {}).innerText || ''") or ""
    el = testo(t)
    verifica("la generale dice quanti argomenti ha e quali no; quello con le sole pagine con istruzioni a parte",
             "La mappa generale" in el and "Ci sono 3 argomenti su 4" in el
             and "Fuori da questa mappa: Il trattato di Tordesillas" in el
             and "messaggio per un assistente: I diari di bordo" in el, el[:500])
    verifica("la riga nella home conta le parti", "le mappe di 2 parti" in riga, riga)
    misure(t, "390×844 con la generale")
    t.tocca('button[data-mappa="quale"][data-dati*="parti"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('.studio-m-parte button')"), 6)
    voci = t.v("[...document.querySelectorAll('.studio-m-parte-tasto')].map((b) => b.textContent)") or []
    verifica("«Le parti»: un tasto per argomento coi concetti, chiuse",
             bool(ok) and len(voci) == 5 and "Le cause delle scoperte geografiche · 4 concetti" in voci[0]
             and voci[0].startswith("▸") and "2 pronte su 5" in testo(t), str(voci))
    # La parte non ancora fatta: la più nuova, ancora senza riga
    st.aggiungi_argomento(LEO, vid, "Un argomento nuovo", [st._pagine_di(vid)[1]["id"]])
    apri(t, args[0]["id"])
    ok = aspetta(lambda: "Costantinopoli" in testo(t), 6)
    el = testo(t)
    verifica("una parte si apre: lo schema, coi verbi, l'avviso e la nota delle voci tolte",
             bool(ok) and "nascono dalla caduta di" in el and "3 voci tolte: non stanno nelle pagine" in el
             and "2 voci non messe" in el, el[:600])
    verifica("nella parte non c'è «proposto»: nessuno decide, si legge",
             "proposto" not in el.lower().replace("proposta", ""), el[:600])
    verifica("aria-expanded sul tasto aperto",
             t.v(f"document.querySelector('button[data-mappa=\"parte\"][data-dati*=\\'\"argomento\":{args[0]['id']}\\']').getAttribute('aria-expanded')") == "true")
    verifica("l'HTML nel testo resta testo", HTML in el and not t.v("!!document.querySelector('.studio-m img')"))
    verifica("rientrata per livello", bool(t.v("!!document.querySelector('.studio-m-voce.studio-m-liv1')")))
    verifica("si legge e basta: né «+ Concetto», né «Cambia», né «Conferma», né «Tieni»",
             not t.v("!!document.querySelector('.studio-m button[data-mappa=\"nuovo\"], .studio-m button[data-mappa=\"cambia\"], "
                     ".studio-m button[data-mappa=\"conferma\"], .studio-m button[data-mappa=\"tieni\"], .studio-m button[data-mappa=\"collega\"]')"))
    misure(t, "390×844 con una parte aperta")
    B.foto(t, "studio-parti-390x844.png")
    apri(t, args[0]["id"])
    verifica("si richiude", bool(aspetta(lambda: "Costantinopoli" not in testo(t), 4)))
    apri(t, args[1]["id"])
    verifica("la pagina con istruzioni non usata si dice dove non c'è una mappa: solo le parti con la mappa",
             "non usata" not in testo(t))
    verifica("una parte non riuscita lo dice", bool(aspetta(lambda: "riprovo da sola" in testo(t), 4)))
    apri(t, args[3]["id"])
    verifica("una parte su pagine con istruzioni lo dice",
             bool(aspetta(lambda: "questa parte guardala sul libro" in testo(t), 4)))
    apri(t, args[4]["id"])
    verifica("una parte vuota perché tutto è stato tolto lo dice, non «le pagine non bastano»",
             bool(aspetta(lambda: "Ho tolto tutte le voci" in testo(t), 4)) and "non bastano" not in testo(t))
    apri(t, args[2]["id"])
    aspetta(lambda: "Concetto lungo numero 2" in testo(t), 4)
    t.tocca('button[data-mappa="vista"][data-dati*="mappa"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('svg.studio-m-tela')"), 6)
    vb = t.v("document.querySelector('svg.studio-m-tela').getAttribute('viewBox')")
    verifica("16 concetti: il disegno si allunga, un gruppo per concetto, in textContent",
             bool(ok) and vb == "0 0 600 1680"
             and t.v("document.querySelectorAll('svg.studio-m-tela .studio-m-nodo').length") == 16, vb)
    sov = t.v("(() => { const r = [...document.querySelectorAll('svg.studio-m-tela .studio-m-nodo rect')].map((e) => e.getBoundingClientRect());"
              " let n = 0; for (let i = 0; i < r.length; i++) for (let j = i + 1; j < r.length; j++)"
              " if (r[i].left < r[j].right && r[j].left < r[i].right && r[i].top < r[j].bottom && r[j].top < r[i].bottom) n++; return n; })()")
    verifica("i riquadri non si sovrappongono", sov == 0, str(sov))
    t.v("document.querySelector('svg.studio-m-tela').scrollIntoView({block: 'start'}); 1")
    t.tocca('svg.studio-m-tela .studio-m-nodo[data-nodo="2"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('.studio-m-pannello')"), 4)
    verifica("toccando un concetto si legge, coi collegamenti, senza tasti per cambiarlo",
             bool(ok) and "Concetto lungo numero 2" in (t.v("document.querySelector('.studio-m-pannello').innerText") or "")
             and not t.v("!!document.querySelector('.studio-m-pannello button[data-mappa=\"sposta\"], .studio-m-pannello button[data-mappa=\"cambia\"]')"))
    misure(t, "390×844 con 16 concetti disegnati")
    B.foto(t, "studio-parti-disegno-390x844.png")
    t.tocca('button[data-mappa="vista"][data-dati*="elenco"]')
    B.dimensione(t, 320, 693)
    t.v("document.querySelector('.studio-h-mappa').scrollIntoView({block: 'start'}); 1")
    misure(t, "320×693 con 16 concetti a schema")
    B.foto(t, "studio-parti-320x693.png")
    t.v("document.documentElement.style.fontSize = '125%'; 1")
    misure(t, "320×693 col testo grande")
    t.v("document.documentElement.style.fontSize = ''; 1")
    B.dimensione(t, 390, 844)
    # Da zero: le parti spariscono, dalla pagina e dallo stato
    t.tocca('button[data-mappa="quale"][data-dati*="libera"]')
    aspetta(lambda: t.v("!!document.querySelector('button[data-mappa=\"libera\"]')"), 6)
    t.tocca('button[data-mappa="libera"]')
    ok = aspetta(lambda: st.vista_mappe(LEO, vid)["a_libera"]
                 and t.v("!!document.querySelector('button[data-mappa=\"finito\"]')"), 8)
    schede = t.v("[...document.querySelectorAll('button[data-mappa=\"quale\"]')].map((b) => b.textContent)") or []
    tutto = t.v("document.body.innerText") or ""
    verifica("con la mappa da zero aperta le parti non ci sono",
             bool(ok) and schede == ["Da zero"] and "Costantinopoli" not in tutto
             and "Concetto lungo" not in tutto, f"{schede}")
    st.finisci_libera(LEO, st.vista_mappe(LEO, vid)["libera"]["id"])


def scenario_pc(t, args):
    B.dimensione(t, 1440, 900)
    aspetta(lambda: t.v("!!window.calliopeSchermo"), 10)
    verifica("PC: «La mappa»", bool(apri_parti(t)))
    t.tocca('button[data-mappa="quale"][data-dati*="parti"]')
    aspetta(lambda: t.v("!!document.querySelector('.studio-m-parte button')"), 6)
    apri(t, args[2]["id"])
    aspetta(lambda: "Concetto lungo numero 2" in testo(t), 4)
    t.tocca('button[data-mappa="vista"][data-dati*="mappa"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('svg.studio-m-tela')"), 6)
    vb = t.v("document.querySelector('svg.studio-m-tela').getAttribute('viewBox')")
    verifica("PC: la parte disegnata in orizzontale, allungata per i 16 concetti", bool(ok) and vb == "0 0 1000 1240", vb)
    t.v("document.querySelector('svg.studio-m-tela').scrollIntoView({block: 'start'}); 1")
    B.foto(t, "studio-parti-pc.png")


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
        cfg.studio_mappa_genera = "attiva"
        minori.prepara(cfg, registry=REG)
        st = S.Studio(cfg, registry=REG, log=lambda m: None)
        st.avvia_lettura(None, avvia=False)
        serv = B.Servizi()
        serv.studio = st
        hub.servizi = serv
        hub.profilo = REG.by_id
        hub.tool_ctx = types.SimpleNamespace(studio=st)
        vid, args = prepara(st)
        _, token = srv.archivio.crea_con_token("telefono", proprietario="l1", proprietario_nome="Leo")
        from prova_parla_pc import CollFinto
        cfg.schermi_sezioni = True
        srv.collegati.append(CollFinto(5, "cameretta"))
        s_pc, t_pc = hub.archivio.crea_con_token("cameretta", proprietario="l1", proprietario_nome="Leo")
        hub.archivio.lega_satellite(s_pc["id"], 5)
        hub._rinfresca()
        pagina = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/telefono/", profilo="profilo-studio-parti",
                            opzioni=("--window-size=390,844",))
        t = PMP.TM(pagina)
        try:
            pagina._chiama("DOM.enable")
            aspetta(lambda: pagina.valuta("document.readyState") == "complete", 10)
            pagina.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
            pagina._chiama("Page.reload")
            time.sleep(0.5)
            B.dimensione(t, 390, 844)
            scenario_telefono(t, st, vid, args)
            pagina.pompa(0.3)
            errori = [r for r in pagina.log if r.startswith(("ECCEZIONE", "ERROR")) or "Content Security" in r]
            verifica("telefono: nessun errore JavaScript né violazione della CSP", not errori, "; ".join(errori)[:300])
        finally:
            pagina.chiudi()
        pc = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/#t={t_pc}", profilo="profilo-studio-parti-pc",
                        opzioni=("--window-size=1440,900",))
        tp = PMP.TM(pc)
        try:
            pc._chiama("DOM.enable")
            scenario_pc(tp, args)
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
