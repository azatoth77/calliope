import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Gli esercizi guidati nella pagina vera (31/10, issue #278, epic #251; schermi/pagina/
esercizio.js, studio.js, POST /api/studio/esercizio, la foto in POST /api/studio/pagina).

Nel browser vero (Edge o Chromium senza finestra; senza si salta), server degli schermi veri su
127.0.0.1, `studio_modo: attivo`, `studio_esercizi: attiva`, Leo (di fantasia) con una verifica di
matematica e un problema con la guida pronta:
- telefono a 390×844: la sezione «Esercizi guidati»; «I miei esercizi», «Comincia»: il testo del
  problema (solo testo), il passo 1, la risposta nel campo e «Controlla» con l'esito del server;
  la scelta multipla sbagliata due volte e «Aiutami» con l'indizio; mai le risposte attese nella
  pagina; «Scrivi un problema» e «Salva»; «Foto di un problema» dal campo file (la foto arriva al
  server come esercizio, non come pagina); la prova aperta che ferma la guida;
- 320×693 e col testo al 125 %: niente fuori dallo schermo né di lato, tocchi ≥ 44 px;
- il PC personale: la stessa sezione e il passo nella colonna centrale;
- nessun errore JavaScript né violazione della CSP.
Con CALLIOPE_FOTO=<cartella> gli screenshot. ~20 s.

    python prove/prova_studio_esercizi_pagina.py
"""

import datetime
import json
import shutil
import tempfile
import time
from pathlib import Path

import prova_studio_pagina_telefono as B

TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-esercizi-pagina-"))
ANDREA = B.Prof("a1", "Andrea")
LEO = B.Prof("l1", "Leo", nascita="2012-03-01", tutori=["a1"])
REG = B.Registro(ANDREA, LEO)
verifica, aspetta = B.verifica, B.aspetta
SALTATA = B.SALTATA

MISURA_HOME = B.MISURA.replace("document.getElementById('studio')",
                               "document.getElementById('studio-home')")
PROBLEMA = ("Un rettangolo ha la base di 8 cm e l'altezza di 5 cm.\nCalcola l'area e il "
            "perimetro. <b>non grassetto</b>")
GUIDA = {"passi": [
    {"domanda": "Quanto è lunga la base?", "tipo": "numero", "risposta": "8 cm",
     "indizio": "Rileggi la prima riga."},
    {"domanda": "Con quale formula si calcola l'area di un rettangolo?", "tipo": "scelta",
     "opzioni": ["base per altezza", "base più altezza", "base per altezza diviso due"],
     "risposta": "base per altezza", "indizio": "Pensa a quanti quadretti ci stanno."},
    {"domanda": "Quanto vale l'area?", "tipo": "numero", "risposta": "40 cm²",
     "indizio": "Moltiplica i due lati."},
    {"domanda": "Quanto vale il perimetro?", "tipo": "numero", "risposta": "26 cm",
     "indizio": "Somma i quattro lati."}], "risultato": "26 cm"}


def misure(t, etichetta):
    m = t.v(MISURA_HOME) or {}
    verifica(f"{etichetta}: niente fuori dallo schermo né di lato", not m.get("fuori") and not m.get("lato"),
             json.dumps(m.get("fuori")))
    verifica(f"{etichetta}: tocchi ≥ 44 px", not m.get("tocchi"), json.dumps(m.get("tocchi")))
    piccoli = [x for x in (m.get("piccoli") or []) if "nota" not in str(x[0]) and "quando" not in str(x[0])
               and "etichetta" not in str(x[0]) and "studio-h-" not in str(x[0])]
    verifica(f"{etichetta}: testo ≥ 16 px (le note e le etichette a parte)", not piccoli, json.dumps(piccoli))


def prepara(st):
    from calliope.studio import esercizi_genera as EG
    vid = st.crea_verifica(LEO, "Matematica", st._oggi() + datetime.timedelta(days=7),
                           argomento="Geometria")
    st.aggiungi_argomento(LEO, vid, "Il rettangolo", [], proposto=False)
    st.conferma_argomenti(LEO, vid)
    eid = st.aggiungi_esercizio(LEO, vid, PROBLEMA)["esercizio"]
    passi, ris, av = EG.proposte(GUIDA, PROBLEMA)
    st.scrivi_guida(eid, EG.firma(st._riga_es(eid)["testo"], "guida"), passi, ris, av)
    return vid, eid


def scrivi(t, sel, testo):
    t.v(f"(() => {{ const e = document.querySelector({json.dumps(sel)}); e.focus(); "
        f"e.value = {json.dumps(testo)}; e.dispatchEvent(new Event('input', {{bubbles: true}})); "
        f"return 1; }})()")


def testo_di(t, sel):
    # textContent: le etichette in maiuscolo sono solo stile
    return t.v(f"(document.querySelector({json.dumps(sel)}) || {{}}).textContent || ''") or ""


def scenario_telefono(t, hub, st, vid, eid):
    T_ = "window.calliopeTelefono"
    verifica("pagina caricata e collegata", bool(aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)))
    t.v("location.hash = '#/cose'; 1")
    aspetta(lambda: t.v("!!document.querySelector('#tessere [data-tessera=\"studio\"]:not(.presto)')"), 10)
    t.tocca('#tessere [data-tessera="studio"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('#studio-home .studio-e')"), 8)
    verifica("la sezione «Esercizi guidati» con la foto e lo scritto",
             bool(ok) and "ESERCIZI GUIDATI" in testo_di(t, ".studio-e").upper()
             and t.v("!!document.querySelector('.studio-e input[type=file][capture]')"),
             testo_di(t, ".studio-e")[:200])
    t.tocca('button[data-esercizio="elenco"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('button[data-esercizio=\"apri\"]')"), 6)
    verifica("«I miei esercizi»: l'elenco col problema pronto", bool(ok), testo_di(t, ".studio-e")[:200])
    t.tocca('button[data-esercizio="apri"]')
    ok = aspetta(lambda: "Quanto è lunga la base?" in testo_di(t, ".studio-e-passo"), 6)
    verifica("«Comincia»: il testo del problema e il passo 1 di 4",
             bool(ok) and "Passo 1 di 4" in testo_di(t, ".studio-e-passo")
             and "<b>non grassetto</b>" in testo_di(t, ".studio-e-testo")
             and t.v("document.querySelector('.studio-e-testo').children.length === 0"),
             testo_di(t, ".studio-e-esercizio")[:300])
    html = t.v("document.documentElement.outerHTML") or ""
    verifica("mai le risposte attese né il risultato nella pagina",
             "26 cm" not in html and "40 cm" not in html and "attesa" not in html)
    misure(t, "390×844 col passo")
    B.foto(t, "studio-esercizi-390x844.png")
    scrivi(t, ".studio-e-passo input.studio-c-campo", "8 centimetri")
    t.tocca('button[data-esercizio="rispondi"]')
    ok = aspetta(lambda: "Passo 2 di 4" in testo_di(t, ".studio-e-passo"), 6)
    verifica("«Controlla»: giusto dal server, il passo 2 con le opzioni",
             bool(ok) and "Giusto!" in testo_di(t, ".studio-e-esito")
             and t.v("document.querySelectorAll('.studio-e-passo input[type=radio]').length") == 3,
             testo_di(t, ".studio-e")[:300])
    for _ in range(2):
        t.tocca('.studio-e-passo input[type=radio][value="b"]')
        t.tocca('button[data-esercizio="rispondi"]')
        aspetta(lambda: "Non ancora" in testo_di(t, ".studio-e-esito"), 5)
    verifica("due risposte sbagliate: «Non ancora» e «Vuoi un indizio?», e il tasto «Aiutami»",
             "indizio" in testo_di(t, ".studio-e-esito")
             and t.v("!!document.querySelector('button[data-esercizio=\"indizio\"]')"),
             testo_di(t, ".studio-e-esito"))
    t.tocca('button[data-esercizio="indizio"]')
    ok = aspetta(lambda: "quadretti" in testo_di(t, ".studio-e-indizio"), 5)
    verifica("«Aiutami»: l'indizio del passo, non la risposta", bool(ok)
             and "base per altezza" not in testo_di(t, ".studio-e-indizio"))
    B.dimensione(t, 320, 693)
    misure(t, "320×693 col passo e l'indizio")
    t.v("document.documentElement.style.fontSize = '125%'; 1")
    t.v("new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(() => ok(1))))")
    misure(t, "320×693 col testo al 125 %")
    B.foto(t, "studio-esercizi-320x693-grande.png")
    t.v("document.documentElement.style.fontSize = ''; 1")
    B.dimensione(t, 390, 844)
    # «Scrivi un problema»
    t.tocca('button[data-esercizio="indietro"]')
    # L'elenco di nuovo, coi tasti attivi (durante una richiesta sono spenti)
    aspetta(lambda: t.v("!!document.querySelector('button[data-esercizio=\"apri\"]:not([disabled])')"), 5)
    t.tocca('button[data-esercizio="scrivi"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('textarea[data-esercizio-campo=\"testo\"]')"), 5)
    verifica("«Scrivi un problema»: il campo del testo", bool(ok), testo_di(t, ".studio-e")[:200])
    if not ok:
        return
    scrivi(t, 'textarea[data-esercizio-campo="testo"]', "Un quadrato ha il lato di 3 cm. Calcola l'area.")
    t.tocca('button[data-esercizio="salva"]')
    due = lambda: len(st.dati.tutti("SELECT id FROM studio_esercizi WHERE verifica = ?", (vid,))) == 2  # noqa: E731
    ok = aspetta(due, 3)
    if not ok:
        # Sotto carico il tocco può cadere mentre la home si ridisegna (un evento del server): il
        # tasto si preme di nuovo dal DOM, una volta
        t.v("(document.querySelector('button[data-esercizio=\"salva\"]') || {click() {}}).click(); 1")
        ok = aspetta(due, 6)
    # La riga c'è prima che la risposta arrivi alla pagina: si aspetta anche l'esito
    detto = aspetta(lambda: "preparo i passi" in testo_di(t, ".studio-e-esito"), 6)
    verifica("«Scrivi un problema» e «Salva»: l'esercizio nuovo, «preparo i passi»",
             bool(ok) and bool(detto), json.dumps(t.v("window.CalliopeEsercizio.stato()"))
             + " | " + testo_di(t, ".studio-e"))
    # «Foto di un problema» dal campo file (CDP): arriva come esercizio, non come pagina
    from PIL import Image
    foto = TMP / "problema.jpg"
    Image.new("RGB", (900, 1200), (250, 250, 247)).save(foto, "JPEG")
    doc = t.p._chiama("DOM.getDocument", {"depth": -1})
    nodo = t.p._chiama("DOM.querySelector", {"nodeId": doc["result"]["root"]["nodeId"],
                                             "selector": "input.studio-e-file"})
    t.p._chiama("DOM.setFileInputFiles", {"files": [str(foto)], "nodeId": nodo["result"]["nodeId"]})
    ok = aspetta(lambda: st.dati.uno("SELECT id FROM studio_esercizi WHERE origine = 'foto'") is not None, 10)
    verifica("«Foto di un problema»: un esercizio «da leggere», nessuna pagina nuova",
             bool(ok) and not st.pagine(LEO, vid)
             and bool(aspetta(lambda: "Arrivata" in testo_di(t, ".studio-e-esito"), 5)),
             testo_di(t, ".studio-e-esito"))
    # La prova aperta ferma la guida
    st.dati.scrivi("INSERT INTO studio_prove (verifica, persona, modalita, stato, inizio, scade) "
                   "VALUES (?, 'l1', 'scritta', 'aperta', ?, ?)",
                   (vid, datetime.datetime.now().isoformat(timespec="seconds"),
                    (datetime.datetime.now() + datetime.timedelta(hours=2)).isoformat(timespec="seconds")))
    t.tocca('button[data-esercizio="chiudi"]')
    aspetta(lambda: t.v("!!document.querySelector('button[data-esercizio=\"elenco\"]')"), 5)
    t.tocca('button[data-esercizio="elenco"]')
    ok = aspetta(lambda: "prova aperta" in testo_di(t, ".studio-e"), 6)
    verifica("con una prova aperta la sezione lo dice", bool(ok), testo_di(t, ".studio-e")[:200])
    st.dati.scrivi("UPDATE studio_prove SET stato = 'consegnata' WHERE verifica = ?", (vid,))


def scenario_pc(t, hub):
    B.dimensione(t, 1440, 900)
    ok = aspetta(lambda: t.v("document.body.classList.contains('con-sezioni')"), 15)
    verifica("PC: lo schermo personale con le sezioni", bool(ok))
    aspetta(lambda: hub.collegati(), 10)
    t.v("location.hash = '#/cose'; 1")
    aspetta(lambda: t.v("!!document.querySelector('#tessere [data-tessera=\"studio\"]:not(.presto)')"), 15)
    t.tocca('#tessere [data-tessera="studio"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('#studio-home .studio-e')"), 8)
    verifica("PC: la sezione «Esercizi guidati»", bool(ok))
    t.tocca('button[data-esercizio="elenco"]')
    aspetta(lambda: t.v("!!document.querySelector('button[data-esercizio=\"apri\"]')"), 6)
    t.tocca('button[data-esercizio="apri"]')
    ok = aspetta(lambda: "Passo 2 di 4" in testo_di(t, ".studio-e-passo"), 6)
    m = t.v(MISURA_HOME) or {}
    verifica("PC: il passo dove l'aveva lasciato, niente di lato", bool(ok) and not m.get("fuori")
             and not m.get("lato"), json.dumps(m.get("fuori")))
    B.foto(t, "studio-esercizi-pc.png")


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
        cfg.studio_esercizi = "attiva"
        minori.prepara(cfg, registry=REG)
        st = S.Studio(cfg, registry=REG, log=lambda m: None)
        st.avvia_lettura(None, avvia=False)
        serv = B.Servizi()
        serv.studio = st
        hub.servizi = serv
        hub.profilo = REG.by_id
        hub.tool_ctx = types.SimpleNamespace(studio=st)
        vid, eid = prepara(st)
        _, token = srv.archivio.crea_con_token("telefono", proprietario="l1", proprietario_nome="Leo")
        from prova_parla_pc import CollFinto
        cfg.schermi_sezioni = True
        srv.collegati.append(CollFinto(5, "cameretta"))
        s_pc, t_pc = hub.archivio.crea_con_token("cameretta", proprietario="l1", proprietario_nome="Leo")
        hub.archivio.lega_satellite(s_pc["id"], 5)
        hub._rinfresca()
        pagina = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/telefono/", profilo="profilo-studio-esercizi",
                            opzioni=("--window-size=390,844",))
        t = B.T(pagina)
        try:
            pagina._chiama("DOM.enable")
            aspetta(lambda: pagina.valuta("document.readyState") == "complete", 10)
            pagina.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
            pagina._chiama("Page.reload")
            time.sleep(0.5)
            B.dimensione(t, 390, 844)
            scenario_telefono(t, hub, st, vid, eid)
            pagina.pompa(0.3)
            errori = [r for r in pagina.log if r.startswith("ECCEZIONE") or "Content Security" in r]
            verifica("telefono: nessun errore JavaScript né violazione della CSP", not errori, "; ".join(errori)[:300])
        finally:
            pagina.chiudi()
        pc = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/#t={t_pc}", profilo="profilo-studio-esercizi-pc",
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
