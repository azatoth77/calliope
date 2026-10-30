import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""La home dello Studio nella pagina vera (30/10, passo 4.5, issue #284, epic #251;
schermi/pagina/studio.js, POST /api/studio/home, /api/tocco, /api/vista).

Nel browser vero (Edge o Chromium senza finestra; senza si salta), server degli schermi veri su
127.0.0.1, `studio_modo: attivo`, Leo (seconda media, di fantasia) con una verifica aperta di storia
(pagine lette, argomenti confermati, uno da decidere, una pagina da parte, due misure):
- telefono a 390×844, a 320×693 e col testo grande (125 %): la home con la prossima verifica, data
  e giorni che mancano, obiettivo e previsione, oggi, tappe, «Impara» (solo «leggi le pagine»: niente
  Esercitati né Esame), «Da decidere» col perché, la pagina da parte detta a parole; niente di lato,
  tocchi ≥ 44 px, testo ≥ 16 px (le note piccole a parte);
- «Tieni» e «Riprova»: il tocco va al ciclo (l'ingresso) col tool `studio`, l'azione fissa e il
  bersaglio; eseguito come lo esegue il ciclo, la home si rilegge e l'argomento esce da «Da decidere»;
- «Inizia»: le due domande (5 livelli e 6 stati), «Comincia» manda `studio_sessione` con lo stato
  d'animo solo nei dati del tocco;
- «Fatto» (30/10, #244): il resoconto nella risposta del tool; la home mostra «La preparazione» e
  «Le sessioni» (righe scritte dal server dai soli dati, textContent, mai lo stato d'animo);
- le carte (30/10, passo 6, #246): «Ripassa», la domanda sola, «Mostra la risposta», i tre esiti
  con la prossima volta scritta dal server, il tentativo della persona; «Le carte», «Scrivi una
  carta» (una domanda con l'HTML resta testo), tutto in textContent e con tocchi ≥ 44 px;
- la vista aperta: la home, «Il piano» e le carte arrivano al server (`hub.viste_studio`);
- il PC personale: la stessa home nella colonna centrale, senza «Pagine» (la fotocamera è del
  telefono);
- nessun errore JavaScript né violazione della CSP.
Con CALLIOPE_FOTO=<cartella> gli screenshot. ~25 s.

    python prove/prova_studio_home_pagina.py
"""

import datetime
import json
import shutil
import tempfile
import time
from pathlib import Path

import prova_studio_pagina_telefono as B

TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-home-"))
QUI = Path(__file__).resolve().parent
MAT = json.loads((QUI / "manuali" / "studio" / "storia.json").read_text("utf-8"))
ANDREA = B.Prof("a1", "Andrea")
LEO = B.Prof("l1", "Leo", nascita="2014-03-01", tutori=["a1"])
REG = B.Registro(ANDREA, LEO)
verifica, aspetta = B.verifica, B.aspetta
SALTATA = B.SALTATA

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


def prepara(st):
    vid = st.crea_verifica(LEO, "Storia", st._oggi() + datetime.timedelta(days=7),
                           argomento="Le scoperte geografiche")
    mid = st.aggiungi_materiale(LEO, vid, "foto", "Libro")
    ids = [st.aggiungi_pagina(LEO, mid, numero=p["numero"], stato="letta", testo=p["testo"],
                              metodo="ocr") for p in MAT["pagine"]]
    for a in MAT["argomenti"][:4]:
        st.aggiungi_argomento(LEO, vid, a["titolo"], [ids[MAT["pagine"].index(p)] for p in MAT["pagine"]
                                                      if p["id"] in a["pagine"]])
    aid = st.aggiungi_argomento(LEO, vid, "Verifica annullata", [ids[-1]], avvisi=["titolo_ordine"])
    st.conferma_argomenti(LEO, vid)
    st.dati.scrivi("UPDATE studio_pagine SET stato = 'da_parte' WHERE id = ?", (ids[2],))
    st.aggiungi_misura(LEO, vid, 40, "carte", giorno=st._oggi() - datetime.timedelta(days=2))
    st.aggiungi_misura(LEO, vid, 55, "carte", giorno=st._oggi() - datetime.timedelta(days=1))
    a0 = st.argomenti(LEO, vid)[0]["id"]
    st.aggiungi_carta(LEO, vid, MAT["domande"][0]["domanda"], "1453", argomento=a0)
    st.aggiungi_carta(LEO, vid, "Chi scoprì l'America?", "Cristoforo Colombo")
    return vid, aid, ids[2]


def esegui_tocco(hub, st, ctx_fn):
    """Il tocco messo nell'ingresso, eseguito come lo esegue il ciclo (ToolRegistry.call col
    bersaglio), poi l'esito alla pagina con l'evento «tocco»."""
    from calliope.tools.registry import ToolRegistry
    from calliope.tools.studio import studio_specs
    item = aspetta(lambda: hub.ingresso.prendi(), 5)
    if not item:
        return None, None
    reg = ToolRegistry()
    for s in studio_specs():
        reg.register(s)
    ctx = ctx_fn()
    ctx.tocco_bersaglio = item.get("bersaglio")
    r = json.loads(reg.call(item["tool"], item["argomenti"], ctx, "familiare"))
    hub.evento_a(item["schermo_id"], "tocco", {"tocco": item["tocco"], "ok": bool(r.get("ok")),
                                               "pagina": item.get("pagina") or {}})
    return item, r


def scenario_telefono(t, hub, st, vid, aid, pid, ctx_fn):
    T_ = "window.calliopeTelefono"
    verifica("pagina caricata e collegata", bool(aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)))
    t.v("location.hash = '#/cose'; 1")
    aspetta(lambda: t.v("!!document.querySelector('#tessere [data-tessera=\"studio\"]:not(.presto)')"), 10)
    tess = t.v("document.querySelector('#tessere [data-tessera=\"studio\"]').textContent") or ""
    verifica("la tessera dice «1 verifica · <giorno>»", "1 verifica" in tess, tess)
    t.tocca('#tessere [data-tessera="studio"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('#studio-home .studio-h-prima')"), 8)
    verifica("la home si apre con la prossima verifica", bool(ok))
    testo = t.v("document.getElementById('studio-home').innerText") or ""
    verifica("data, giorni che mancano, obiettivo e, con due misure, l'ultima prova (non la previsione)",
             "fra 7 giorni" in testo and "obiettivo 75%" in testo and "ultima prova: 55%" in testo
             and "previsione" not in testo, testo[:300])
    verifica("oggi e «Impara» con «leggi le pagine»; niente Esercitati né Esame (non ci sono ancora)",
             "Oggi ·" in testo and "Impara" in testo.title() and "Esercitati" not in testo.title()
             and "Esame" not in testo.title(), testo[:400])
    verifica("da decidere: col perché e «Tieni»; la pagina da parte detta a parole con «Riprova»",
             "Fuori dal piano" in testo and "ordine o un annuncio" in testo and "messa da parte" in testo
             and t.v(f"!!document.querySelector('button[data-tocco=\"studio_tieni\"]')")
             and t.v(f"!!document.querySelector('button[data-tocco=\"studio_riprova\"]')"))
    verifica("i titoli sono testo, mai HTML (textContent)",
             t.v("[...document.querySelectorAll('#studio-home b, #studio-home .studio-h-tappa-nome')]"
                 ".every((e) => e.children.length === 0)"))
    vs = aspetta(lambda: next((hub.viste_studio.di(k) for k in list(hub.viste_studio._d)
                               if hub.viste_studio.di(k)), None), 4)
    verifica("la vista aperta (la home) arriva al server", bool(vs) and vs[0]["vista"] == "home", str(vs))
    t.v("document.getElementById('pagina-racc').scrollIntoView({block: 'start'}); 1")
    misure(t, "390×844")
    B.foto(t, "studio-home-390x844.png")
    # Tieni
    t.tocca('button[data-tocco="studio_tieni"]')
    item, r = esegui_tocco(hub, st, ctx_fn)
    verifica("«Tieni»: il tocco al ciclo col tool studio, l'azione fissa e il bersaglio",
             item and item["tool"] == "studio" and item["argomenti"]["azione"] == "tieni"
             and item["bersaglio"]["studio"]["argomento"] == aid and r and r["ok"], str(item)[:300])
    ok = aspetta(lambda: not t.v("!!document.querySelector('button[data-tocco=\"studio_tieni\"]')"), 6)
    verifica("«Tieni»: la home si rilegge e l'argomento esce da «Da decidere»", bool(ok))
    # Riprova
    t.tocca('button[data-tocco="studio_riprova"]')
    item, r = esegui_tocco(hub, st, ctx_fn)
    verifica("«Riprova»: la pagina da parte torna da leggere",
             item and item["argomenti"]["azione"] == "riprova" and r and r["ok"]
             and next(p for p in st.pagine(LEO, vid) if p["id"] == pid)["stato"] == "da_leggere")
    # Inizia: le due domande
    aspetta(lambda: t.v("!!document.querySelector('button[data-domande]')"), 6)
    t.tocca("button[data-domande]")
    ok = aspetta(lambda: t.v("document.querySelectorAll('.studio-h-chip').length === 11"), 4)
    verifica("«Inizia»: le due domande, 5 livelli e 6 stati", bool(ok))
    misure(t, "390×844 con le domande")
    # Ogni scelta si aspetta segnata: sotto carico una rilettura della home arrivata in ritardo
    # (l'esito di «Riprova») ridisegnava sotto il tocco (30/10, hook della #244)
    for sel in ('.studio-h-chip[data-valore="2"]', '.studio-h-chip[data-valore="poca energia"]'):
        for _ in range(3):
            t.tocca(sel)
            if aspetta(lambda: t.v(f"(document.querySelector('{sel}') || {{}}).getAttribute"
                                   f" && document.querySelector('{sel}').getAttribute('aria-pressed') === 'true'"), 2):
                break
    t.tocca('button[data-tocco="studio_sessione"]')
    item, r = esegui_tocco(hub, st, ctx_fn)
    verifica("«Comincia»: studio_sessione, lo stato d'animo solo nel bersaglio",
             item and item["argomenti"] == {"azione": "sessione", "verifica": vid}
             and item["bersaglio"]["studio"]["umore"] == "poca energia"
             and "poca energia" not in item["descrizione"] and st.sessione("l1"), str(item)[:300])
    # «Fatto» dopo «Comincia»: la preparazione e le sessioni (passo 4b, #244), dai soli dati
    aspetta(lambda: t.v("!document.querySelector('.studio-h-domande') && !!document.querySelector('button[data-tocco=\"studio_fatto\"]')"), 6)
    t.tocca('button[data-tocco="studio_fatto"]')
    item, r = esegui_tocco(hub, st, ctx_fn)
    verifica("«Fatto»: il tocco al ciclo e il resoconto nella risposta",
             item and item["argomenti"]["azione"] == "fatto" and r and r["ok"]
             and str(r.get("risposta_finale", "")).startswith("Segnato fatto: oggi hai letto"), str(r)[:300])
    # La home si rilegge dopo l'esito del tocco: si aspetta il giorno fatto (prima c'era già la
    # sessione cominciata). Inizio e fine nello stesso secondo non sono una misura: il tempo lo dice
    ok = aspetta(lambda: "1 fatto" in (t.v("(document.querySelector('.studio-h-preparazione') || {}).textContent || ''") or ""), 8)
    prep = t.v("(document.querySelector('.studio-h-preparazione') || {}).innerText || ''") or ""
    verifica("la home: «La preparazione» con i giorni fatti e il tempo",
             bool(ok) and "LA PREPARAZIONE" in prep.upper() and "Giorni del piano: 1 fatto" in prep
             and "Tempo misurato" in prep, prep[:300])
    t.v("document.querySelector('.studio-h-sessioni').open = true; 1")
    sess = t.v("[...document.querySelectorAll('.studio-h-sessioni li')].map((e) => e.textContent)") or []
    verifica("«Le sessioni»: oggi fatto con l'attività, testo e mai HTML",
             len(sess) == 1 and " min" in sess[0] and "· Leggi " in sess[0]
             and t.v("[...document.querySelectorAll('.studio-h-sessioni li, .studio-h-preparazione p')]"
                     ".every((e) => e.children.length === 0)")
             and "poca energia" not in prep + " ".join(sess), str(sess))
    misure(t, "390×844 con le sessioni")
    scenario_carte(t, hub, st, vid)
    # Il piano aperto: la vista del piano
    aspetta(lambda: t.v("!document.querySelector('.studio-h-domande') && !!document.querySelector('.studio-h-piano')"), 6)
    time.sleep(0.3)
    t.v("document.querySelector('.studio-h-piano').open = true; 1")
    ok = aspetta(lambda: any((hub.viste_studio.di(k) or [{}])[0].get("vista") == "piano" for k in list(hub.viste_studio._d)), 6)
    verifica("«Il piano» aperto: la vista del piano arriva al server", bool(ok))
    B.dimensione(t, 320, 693)
    misure(t, "320×693")
    B.foto(t, "studio-home-320x693.png")
    t.v("document.documentElement.style.fontSize = '125%'; 1")
    t.v("new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(() => ok(1))))")
    misure(t, "320×693 col testo grande")
    B.foto(t, "studio-home-320x693-grande.png")
    t.v("document.documentElement.style.fontSize = ''; 1")


def scenario_carte(t, hub, st, vid):
    """Le carte (passo 6, #246): il ripasso una carta per volta e «Scrivi una carta»."""
    testo = t.v("(document.querySelector('.studio-h-carte') || {}).innerText || ''") or ""
    verifica("le carte: «2 carte da ripassare adesso» e «Ripassa»",
             "2 carte da ripassare adesso" in testo
             and t.v("!!document.querySelector('button[data-carte=\"ripassa\"]')"), testo[:200])
    t.tocca('button[data-carte="ripassa"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('.studio-c-domanda')"), 6)
    dom = t.v("(document.querySelector('.studio-c-domanda') || {}).textContent || ''") or ""
    verifica("«Ripassa»: la domanda sola, la risposta no",
             bool(ok) and dom == MAT["domande"][0]["domanda"]
             and not t.v("!!document.querySelector('.studio-c-risposta')"), dom)
    vs = aspetta(lambda: any((hub.viste_studio.di(k) or [{}])[0].get("vista") == "carte"
                             for k in list(hub.viste_studio._d)), 4)
    verifica("le carte aperte: la vista arriva al server", bool(vs))
    t.tocca('button[data-carte="mostra"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('.studio-c-risposta')"), 4)
    tasti = t.v("[...document.querySelectorAll('.studio-c-esiti button')].map((b) => b.textContent)") or []
    verifica("«Mostra la risposta»: la risposta e i tre esiti con la prossima volta",
             bool(ok) and t.v("document.querySelector('.studio-c-risposta').textContent") == "1453"
             and tasti[:3] == ["Non la sapevo · fra 10 minuti", "Quasi · domani",
                               "La sapevo · fra 2 giorni"], str(tasti))
    misure(t, "390×844 con una carta")
    B.foto(t, "studio-carta-390x844.png")
    t.tocca('button[data-carte="esito"][data-dati*="sapevo"]:not([data-dati*="non_sapevo"])')
    ok = aspetta(lambda: len(st.dati.tutti("SELECT * FROM studio_tentativi")) == 1, 6)
    tent = st.dati.tutti("SELECT * FROM studio_tentativi")
    verifica("«La sapevo»: un tentativo «giusto» della persona sull'argomento della carta",
             bool(ok) and tent and tent[0]["esito"] == "giusto" and tent[0]["fonte"] == "persona",
             str(tent))
    ok = aspetta(lambda: t.v("(document.querySelector('.studio-c-domanda') || {}).textContent")
                 == "Chi scoprì l'America?", 6)
    esito = t.v("(document.querySelector('.studio-c-esito') || {}).textContent || ''") or ""
    verifica("poi la carta dopo, e l'esito detto («La prossima volta: fra 2 giorni.»)",
             bool(ok) and "fra 2 giorni" in esito, esito)
    t.tocca('button[data-carte="mostra"]')
    aspetta(lambda: t.v("!!document.querySelector('.studio-c-risposta')"), 4)
    t.tocca('button[data-carte="esito"][data-dati*="non_sapevo"]')
    ok = aspetta(lambda: "finite" in (t.v("(document.querySelector('.studio-c-ripasso') || {}).textContent || ''") or ""), 6)
    verifica("«Non la sapevo» sull'ultima: per adesso finite (torna fra 10 minuti)", bool(ok))
    # Le carte: l'elenco e «Scrivi una carta» (una domanda con l'HTML resta testo)
    t.tocca('button[data-carte="elenco"]')
    aspetta(lambda: t.v("!!document.querySelector('button[data-carte=\"scrivi\"]')"), 6)
    t.tocca('button[data-carte="scrivi"]')
    aspetta(lambda: t.v("!!document.getElementById('studio-c-domanda')"), 4)
    t.v("""(() => { const d = document.getElementById('studio-c-domanda');
      d.value = '<img src=x onerror=window.__x=1> Chi era Magellano?';
      d.dispatchEvent(new Event('input', { bubbles: true }));
      const r = document.getElementById('studio-c-risposta');
      r.value = 'Un navigatore'; r.dispatchEvent(new Event('input', { bubbles: true }));
      const s = document.getElementById('studio-c-argomento');
      s.selectedIndex = 1; s.dispatchEvent(new Event('change', { bubbles: true })); return 1; })()""")
    misure(t, "390×844 con «Scrivi una carta»")
    t.tocca('button[data-carte="salva"]')
    ok = aspetta(lambda: any("Magellano" in c["domanda"] for c in st.carte(LEO, vid)), 6)
    nuova = next((c for c in st.carte(LEO, vid) if "Magellano" in c["domanda"]), {})
    verifica("«Scrivi una carta»: la carta col suo argomento, attiva",
             bool(ok) and nuova.get("argomento") == st.argomenti(LEO, vid)[0]["id"]
             and nuova.get("stato") == "attiva", str(nuova))
    aspetta(lambda: t.v("[...document.querySelectorAll('.studio-c-voce b')].some((b) => b.textContent.includes('Magellano'))"), 6)
    verifica("la domanda con l'HTML resta testo: nessuna immagine, nessuno script",
             t.v("!document.querySelector('.studio-c-elenco img') && !window.__x")
             and t.v("[...document.querySelectorAll('.studio-c-voce b, .studio-c-voce .studio-c-risp')]"
                     ".every((e) => e.children.length === 0)"))
    misure(t, "390×844 con l'elenco delle carte")
    t.tocca('button[data-carte="chiudi"]')
    aspetta(lambda: not t.v("!!document.querySelector('.studio-c-elenco')"), 4)


def scenario_pc(t, hub):
    B.dimensione(t, 1440, 900)
    ok = aspetta(lambda: t.v("document.body.classList.contains('con-sezioni')"), 15)
    verifica("PC: lo schermo personale con le sezioni", bool(ok))
    aspetta(lambda: hub.collegati(), 10)
    t.v("location.hash = '#/cose'; 1")
    ok = aspetta(lambda: t.v("!!document.querySelector('#tessere [data-tessera=\"studio\"]:not(.presto)')"), 15)
    verifica("PC: la tessera Studio apre la home", bool(ok))
    t.tocca('#tessere [data-tessera="studio"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('#studio-home .studio-h-prima')"), 8)
    verifica("PC: la stessa home nella colonna centrale, senza «Pagine» (sono del telefono)",
             bool(ok) and not t.v("!!document.querySelector('#studio-home [data-pagine]')"))
    m = t.v(MISURA_HOME) or {}
    verifica("PC: niente di lato", not m.get("fuori") and not m.get("lato"), json.dumps(m.get("fuori")))
    B.foto(t, "studio-home-pc.png")


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
        from calliope.tools.spec import ToolContext
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
        vid, aid, pid = prepara(st)

        def ctx_fn():
            sc = types.SimpleNamespace(current_speaker="Leo", identified_by="schermo",
                                       minore_incerto=None, current_level="familiare",
                                       profile_level="familiare")
            c = ToolContext(cfg=cfg, speakers=REG, speaker_ctx=sc, speaker=None)
            c.studio = st
            return c
        _, token = srv.archivio.crea_con_token("telefono", proprietario="l1", proprietario_nome="Leo")
        # Il PC personale: uno schermo dell'archivio degli schermi legato a un satellite collegato
        # (come prova_pc_pagina)
        from prova_parla_pc import CollFinto
        cfg.schermi_sezioni = True
        srv.collegati.append(CollFinto(5, "cameretta"))
        s_pc, t_pc = hub.archivio.crea_con_token("cameretta", proprietario="l1", proprietario_nome="Leo")
        hub.archivio.lega_satellite(s_pc["id"], 5)
        hub._rinfresca()
        # Fuori dagli orari di riposo di un minore la prova non dipende dall'ora: Leo senza orari
        pagina = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/telefono/", profilo="profilo-studio-home",
                            opzioni=("--window-size=390,844",))
        t = B.T(pagina)
        try:
            pagina._chiama("DOM.enable")
            aspetta(lambda: pagina.valuta("document.readyState") == "complete", 10)
            pagina.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
            pagina._chiama("Page.reload")
            time.sleep(0.5)
            B.dimensione(t, 390, 844)
            scenario_telefono(t, hub, st, vid, aid, pid, ctx_fn)
            pagina.pompa(0.3)
            errori = [r for r in pagina.log if r.startswith("ECCEZIONE") or "Content Security" in r]
            verifica("telefono: nessun errore JavaScript né violazione della CSP", not errori, "; ".join(errori)[:300])
        finally:
            pagina.chiudi()
        pc = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/#t={t_pc}", profilo="profilo-studio-pc",
                        opzioni=("--window-size=1440,900",))
        tp = B.T(pc)
        try:
            pc._chiama("DOM.enable")
            scenario_pc(tp, hub)
            pc.pompa(0.3)
            errori = [r for r in pc.log if r.startswith("ECCEZIONE") or "Content Security" in r]
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
