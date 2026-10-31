import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""La libreria dello Studio nella pagina vera (31/10, issue #297, epic #251;
schermi/pagina/libreria.js, studio.js, POST /api/studio/libreria).

Nel browser vero (Edge o Chromium senza finestra; senza si salta), server degli schermi veri su
127.0.0.1, `studio_modo: attivo`, Leo (di fantasia) con una verifica di chimica e due argomenti
confermati («Le reazioni chimiche», «La mole»):
- telefono a 390×844: la sezione «Dalla libreria» con scheda e carte per argomento, i titoli in
  textContent; «Apri» mostra la scheda (sezioni, da ricordare, prova tu) e la vista «libreria»
  arriva al server; le soluzioni non sono nella pagina prima di «Mostra la soluzione», poi c'è solo
  quella; «Aggiungi le carte» mette il mazzo fra le carte (origine «libreria») e la sezione Carte si
  aggiorna; un prerequisito si apre dalla scheda; «Chiudi la scheda»;
- 320×693 e col testo grande (125 %): niente fuori dallo schermo né di lato, tocchi ≥ 44 px;
- il PC personale: la stessa sezione nella colonna centrale;
- nessun errore JavaScript né violazione della CSP.
Con CALLIOPE_FOTO=<cartella> gli screenshot. ~20 s.

    python prove/prova_studio_libreria_pagina.py
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

import prova_studio_pagina_telefono as B

TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-libreria-pagina-"))
ANDREA = B.Prof("a1", "Andrea")
LEO = B.Prof("l1", "Leo", nascita="2012-03-01", tutori=["a1"])
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
    import datetime
    vid = st.crea_verifica(LEO, "Chimica", st._oggi() + datetime.timedelta(days=7),
                           argomento="Reazioni e moli")
    for t in ("Le reazioni chimiche", "La mole"):
        st.aggiungi_argomento(LEO, vid, t, [], proposto=False)
    st.conferma_argomenti(LEO, vid)
    return vid


def scenario_telefono(t, hub, st, vid):
    from calliope.studio.libreria import Libreria
    lib = Libreria.carica()
    T_ = "window.calliopeTelefono"
    verifica("pagina caricata e collegata", bool(aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)))
    t.v("location.hash = '#/cose'; 1")
    aspetta(lambda: t.v("!!document.querySelector('#tessere [data-tessera=\"studio\"]:not(.presto)')"), 10)
    t.tocca('#tessere [data-tessera="studio"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('#studio-home .studio-l')"), 8)
    testo = t.v("(document.querySelector('.studio-l') || {}).innerText || ''") or ""
    verifica("la sezione «Dalla libreria» con scheda e carte degli argomenti 1 e 2",
             bool(ok) and "DALLA LIBRERIA" in testo.upper()
             and lib.contenuti["chimica-reazioni"]["titolo"] in testo
             and lib.contenuti["chimica-mole-carte"]["titolo"] in testo
             and "argomento 1" in testo and "argomento 2" in testo, testo[:400])
    verifica("i titoli sono testo, mai HTML (textContent)",
             t.v("[...document.querySelectorAll('.studio-l b, .studio-l .studio-nota')]"
                 ".every((e) => e.children.length === 0)"))
    t.v("document.querySelector('.studio-l').scrollIntoView({block: 'start'}); 1")
    misure(t, "390×844 con la libreria")
    B.foto(t, "studio-libreria-390x844.png")
    # Apri la scheda della mole
    t.tocca('button[data-libreria="apri"][data-dati*="chimica-mole\\""]')
    ok = aspetta(lambda: t.v("!!document.querySelector('.studio-l-scheda .studio-l-nome')"), 6)
    sch = t.v("(document.querySelector('.studio-l-scheda') || {}).innerText || ''") or ""
    s = lib.contenuti["chimica-mole"]
    verifica("«Apri»: la scheda con le sezioni, «Da ricordare» e «Prova tu»",
             bool(ok) and s["titolo"] in sch and s["scheda"]["sezioni"][0]["titolo"] in sch
             and "Da ricordare" in sch and "Prova tu" in sch, sch[:300])
    sol = s["scheda"]["prova_tu"][0]["risposta"]
    verifica("le soluzioni non sono nella pagina prima di «Mostra la soluzione»",
             sol not in (t.v("document.documentElement.outerHTML") or ""))
    vs = aspetta(lambda: any((hub.viste_studio.di(k) or [{}])[0].get("vista") == "libreria"
                             for k in list(hub.viste_studio._d)), 4)
    verifica("la vista «libreria» arriva al server", bool(vs))
    misure(t, "390×844 con la scheda")
    B.foto(t, "studio-libreria-scheda-390x844.png")
    t.tocca('button[data-libreria="soluzione"][data-dati="{\\"n\\":1}"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('.studio-l-soluzione')"), 6)
    sols = t.v("[...document.querySelectorAll('.studio-l-soluzione')].map((e) => e.textContent)") or []
    verifica("«Mostra la soluzione»: quella della domanda 1, e solo quella",
             bool(ok) and sols == [sol]
             and (s["scheda"]["prova_tu"][1]["risposta"] not in (t.v("document.documentElement.outerHTML") or "")
                  if len(s["scheda"]["prova_tu"]) > 1 else True), str(sols))
    # Aggiungi le carte dalla scheda
    t.tocca('.studio-l-scheda button[data-libreria="carte"]')
    ok = aspetta(lambda: len([c for c in st.carte(LEO, vid) if c["origine"] == "libreria"])
                 == len(lib.contenuti["chimica-mole-carte"]["carte"]), 6)
    verifica("«Aggiungi le carte»: il mazzo fra le carte della verifica, origine «libreria»", bool(ok))
    ok = aspetta(lambda: "carte da ripassare adesso" in (t.v("(document.querySelector('.studio-h-carte') || {}).innerText || ''") or ""), 6)
    es = t.v("(document.querySelector('.studio-l-esito') || {}).textContent || ''") or ""
    verifica("la sezione Carte si aggiorna e l'esito dice quante", bool(ok) and "aggiunte" in es, es)
    verifica("il mazzo aggiunto non ha più «Aggiungi le carte» e dice «già fra le carte»",
             bool(aspetta(lambda: "già fra le carte" in (t.v("(document.querySelector('.studio-l-elenco') || {}).innerText || ''") or ""), 6)))
    # Un prerequisito dalla scheda
    pre = s["prerequisiti"][0]
    t.tocca(f'.studio-l-scheda button[data-libreria="apri"][data-dati*="{pre}"]')
    ok = aspetta(lambda: (t.v("(document.querySelector('.studio-l-nome') || {}).textContent") or "")
                 == lib.contenuti[pre]["titolo"], 6)
    verifica("un prerequisito si apre dalla scheda", bool(ok))
    B.dimensione(t, 320, 693)
    misure(t, "320×693 con la scheda")
    B.foto(t, "studio-libreria-320x693.png")
    t.v("document.documentElement.style.fontSize = '125%'; 1")
    t.v("new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(() => ok(1))))")
    misure(t, "320×693 col testo grande")
    B.foto(t, "studio-libreria-320x693-grande.png")
    t.v("document.documentElement.style.fontSize = ''; 1")
    t.tocca('.studio-l-scheda button[data-libreria="chiudi"]')
    ok = aspetta(lambda: not t.v("!!document.querySelector('.studio-l-scheda')"), 4)
    verifica("«Chiudi la scheda»", bool(ok))


def scenario_pc(t, hub):
    B.dimensione(t, 1440, 900)
    ok = aspetta(lambda: t.v("document.body.classList.contains('con-sezioni')"), 15)
    verifica("PC: lo schermo personale con le sezioni", bool(ok))
    aspetta(lambda: hub.collegati(), 10)
    t.v("location.hash = '#/cose'; 1")
    aspetta(lambda: t.v("!!document.querySelector('#tessere [data-tessera=\"studio\"]:not(.presto)')"), 15)
    t.tocca('#tessere [data-tessera="studio"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('#studio-home .studio-l')"), 8)
    verifica("PC: la sezione «Dalla libreria»", bool(ok))
    t.tocca('button[data-libreria="apri"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('.studio-l-scheda .studio-l-nome')"), 6)
    m = t.v(MISURA_HOME) or {}
    verifica("PC: la scheda si apre, niente di lato", bool(ok) and not m.get("fuori") and not m.get("lato"),
             json.dumps(m.get("fuori")))
    B.foto(t, "studio-libreria-pc.png")


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
        pagina = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/telefono/", profilo="profilo-studio-libreria",
                            opzioni=("--window-size=390,844",))
        t = B.T(pagina)
        try:
            pagina._chiama("DOM.enable")
            aspetta(lambda: pagina.valuta("document.readyState") == "complete", 10)
            pagina.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
            pagina._chiama("Page.reload")
            time.sleep(0.5)
            B.dimensione(t, 390, 844)
            scenario_telefono(t, hub, st, vid)
            pagina.pompa(0.3)
            errori = [r for r in pagina.log if r.startswith("ECCEZIONE") or "Content Security" in r]
            verifica("telefono: nessun errore JavaScript né violazione della CSP", not errori, "; ".join(errori)[:300])
        finally:
            pagina.chiudi()
        pc = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/#t={t_pc}", profilo="profilo-studio-libreria-pc",
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
