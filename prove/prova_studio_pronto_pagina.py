import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""La generazione a lettura finita nella pagina vera (04/11, issue #384, epic #251, decisione 0035
punto 58; schermi/pagina/studio.js).

Nel browser vero (Edge o Chromium senza finestra; senza si salta), il server degli schermi vero su
127.0.0.1, Leo (di fantasia) con una verifica di storia in bozza, pagine ancora da leggere, sul telefono:
- la scheda dice «Sto preparando» e che non c'è niente da fare, **senza un tasto da confermare**;
- il lavoro del lettore finisce (dal lato del server, come il giro) e la scheda si aggiorna **da sola, senza
  toccare niente**: «Cosa è pronto», con i conti di carte e domande;
- «Ripassa»: la carta con «Fatta da me» e la pagina d'origine già prima della risposta, «Togli questa carta»
  la toglie davvero; «Le carte»: l'origine e quella da guardare, fuori dal ripasso; l'HTML resta testo;
- «Le domande»: l'origine e la pagina; «Verifica finta» si apre anche con poche domande generate;
- a 390×844 e 320×693, anche col testo al 125 %: niente di lato, tocchi ≥ 44 px;
- Andrea, il tutore, sul suo schermo vede quante ne ho preparate e toglie una carta;
- nessun errore JavaScript né violazione della CSP.
Con CALLIOPE_FOTO=<cartella> gli screenshot. ~50 s (l'aggiornamento della scheda è ogni 15 s).

    python prove/prova_studio_pronto_pagina.py
"""

import datetime
import json
import shutil
import tempfile
import time
from pathlib import Path

import prova_studio_pagina_telefono as B
import prova_studio_mappa_pagina as PMP

TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-pronto-"))
QUI = Path(__file__).resolve().parent
MAT = json.loads((QUI / "manuali" / "studio" / "storia.json").read_text("utf-8"))
LEO, ANDREA, REG = PMP.LEO, PMP.ANDREA, PMP.REG
verifica, aspetta, misure = B.verifica, B.aspetta, PMP.misure
SALTATA = B.SALTATA
HTML = "<b>Chi</b> partì nel 1492?"


def prepara(st):
    """Una verifica in bozza con le pagine da leggere: {id del materiale: riga}."""
    vid = st.crea_verifica(LEO, "Storia", st._oggi() + datetime.timedelta(days=7),
                           argomento="Le scoperte geografiche")
    mid = st.aggiungi_materiale(LEO, vid, "foto", "Libro")
    ids = {p["id"]: st.aggiungi_pagina(LEO, mid, numero=p["numero"], stato="da_leggere",
                                       testo=None, metodo=None) for p in MAT["pagine"]}
    return vid, ids


def finisci_lettura(st, vid, ids):
    """Quello che fa il lettore: le pagine lette, gli argomenti proposti, si apre da sola, carte e domande."""
    from calliope.studio import argomenti as A
    from calliope.studio import domande_genera as DG
    from calliope.studio import genera as G
    for p in MAT["pagine"]:
        st.dati.scrivi("UPDATE studio_pagine SET stato = 'letta', testo = ?, metodo = 'ocr' WHERE id = ?",
                       (p["testo"], ids[p["id"]]))
    pagine = st._pagine_di(vid)
    st.proponi_argomenti(vid, A.firma(pagine), [
        {"titolo": a["titolo"], "pagine": [ids[x] for x in a["pagine"]], "avvisi": []}
        for a in MAT["argomenti"][:3]], A.PROPOSTI)
    aperte = st.apri_pronte()
    args = st._argomenti_per_carte(vid)
    a0, p0 = args[0]["id"], args[0]["pagine"][0]
    st.proponi_carte(vid, G.firma(args, pagine, "attiva"), [
        {"domanda": HTML, "risposta": "Colombo", "argomento": a0, "pagine": [p0], "avvisi": []},
        {"domanda": "Quando cadde Costantinopoli?", "risposta": "Nel 1453", "argomento": a0,
         "pagine": [p0], "avvisi": []},
        {"domanda": "Chi inventò il vapore?", "risposta": "Watt", "argomento": a0, "pagine": [p0],
         "avvisi": [G.DA_CONTROLLARE]}], G.PROPOSTE, "attiva")
    st.proponi_domande(vid, DG.firma(args, pagine, "attiva"), [
        {"tipo": "numero", "testo": "In che anno partì Colombo?", "opzioni": [], "attesa": "1492",
         "chiave": [], "argomento": a0, "pagine": [p0], "avvisi": []}], DG.PROPOSTE, "attiva")
    return aperte


def home(t) -> str:
    # textContent: le intestazioni sono in maiuscolo solo per il CSS
    return t.v("(document.getElementById('studio-home') || {}).textContent || ''") or ""


def scenario_telefono(t, st, vid, ids):
    T_ = "window.calliopeTelefono"
    verifica("pagina caricata e collegata", bool(aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)))
    t.v("location.hash = '#/cose'; 1")
    aspetta(lambda: t.v("!!document.querySelector('#tessere [data-tessera=\"studio\"]:not(.presto)')"), 10)
    t.tocca('#tessere [data-tessera="studio"]')
    ok = aspetta(lambda: "Sto preparando" in home(t), 8)
    el = home(t)
    verifica("mentre legge: «Sto preparando», «non devi fare niente», e niente da confermare",
             bool(ok) and "Sto leggendo le pagine" in el and "non devi fare niente" in el
             and "aspettano la tua conferma" not in el, el[:400])
    misure(t, "390×844 mentre prepara")
    B.foto(t, "studio-pronto-prepara-390x844.png")
    aperte = finisci_lettura(st, vid, ids)
    verifica("il lettore ha finito: la verifica si è aperta da sola", aperte == [vid], aperte)
    ok = aspetta(lambda: "Cosa è pronto" in home(t), 25)
    el = home(t)
    verifica("la scheda si aggiorna da sola, senza toccare niente: carte e domande pronte, una da guardare",
             bool(ok) and "Carte: 2 pronte, 1 da guardare" in el and "Domande: 1 pronta" in el, el[:600])
    verifica("niente testo delle carte nelle righe di ciò che è pronto",
             "Costantinopoli" not in (t.v("document.querySelector('.studio-h-pronto').innerText") or ""))
    t.v("document.querySelector('.studio-h-pronto').scrollIntoView({block: 'start'}); 1")
    B.foto(t, "studio-pronto-390x844.png")
    misure(t, "390×844 con ciò che è pronto")
    t.tocca('.studio-h-carte button[data-carte="ripassa"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('.studio-c-carta')"), 8)
    origine = t.v("(document.querySelector('.studio-c-origine') || {}).textContent || ''") or ""
    verifica("«Ripassa» senza una conferma: la carta con chi l'ha fatta e la pagina, già prima della risposta",
             bool(ok) and origine.startswith("Fatta da me: ") and "p. " in origine, origine)
    dom = t.v("(document.querySelector('.studio-c-domanda') || {}).textContent || ''") or ""
    html = t.v("(document.querySelector('.studio-c-domanda') || {}).innerHTML || ''") or ""
    verifica("il testo generato resta un dato: l'HTML è testo",
             dom != HTML or "&lt;b&gt;" in html, html)
    B.foto(t, "studio-pronto-ripasso-390x844.png")
    B.dimensione(t, 320, 693)
    misure(t, "320×693 sulla carta")
    t.v("document.documentElement.style.fontSize = '125%'; 1")
    misure(t, "320×693 sulla carta col testo grande")
    t.v("document.documentElement.style.fontSize = ''; 1")
    B.dimensione(t, 390, 844)
    prima = {c["id"] for c in st.da_ripassare(LEO, vid)}
    t.tocca('.studio-c-ripasso button[data-carte="togli"]')
    ok = aspetta(lambda: len(st.da_ripassare(LEO, vid)) == len(prima) - 1, 8)
    verifica("«Togli questa carta»: fuori dal ripasso", bool(ok), st.da_ripassare(LEO, vid))
    t.tocca('.studio-c-ripasso button[data-carte="chiudi"]')
    aspetta(lambda: not t.v("!!document.querySelector('.studio-c-ripasso')"), 8)
    aspetta(lambda: t.v("!!document.querySelector('.studio-h-carte button[data-carte=\"elenco\"]')"), 8)
    t.tocca('.studio-h-carte button[data-carte="elenco"]')
    ok = aspetta(lambda: t.v("document.querySelectorAll('.studio-h-carte .studio-c-voce').length") == 3, 8)
    el = t.v("document.querySelector('.studio-h-carte').innerText") or ""
    verifica("«Le carte»: l'origine, quella da guardare col suo perché, fuori dal ripasso, «Tieni»",
             bool(ok) and "fatta da me dalle pagine" in el and "da guardare" in el
             and "non la trovo nelle pagine" in el and "Tieni" in el
             and "Conferma le carte" not in el, el[:600])
    t.tocca('.studio-h-carte button[data-carte="chiudi"]')
    aspetta(lambda: t.v("!!document.querySelector('.studio-h-prove button[data-prove=\"domande\"]')"), 8)
    verifica("«Verifica finta» c'è, con le poche domande generate",
             t.v("!!document.querySelector('.studio-h-prove button[data-prove=\"inizia\"]')"),
             t.v("document.querySelector('.studio-h-prove').innerText"))
    t.tocca('.studio-h-prove button[data-prove="domande"]')
    ok = aspetta(lambda: t.v("document.querySelectorAll('.studio-h-prove .studio-c-voce').length") >= 1, 8)
    el = t.v("document.querySelector('.studio-h-prove').innerText") or ""
    verifica("«Le domande»: l'origine e la pagina", bool(ok) and "fatta da me dalle pagine" in el
             and "p. " in el, el[:500])
    misure(t, "390×844 con le domande aperte")


def scenario_tutore(t, st, vid):
    aspetta(lambda: t.v("!!window.CalliopeStudio || !!document.getElementById('studio-home')"), 10)
    t.v("location.hash = '#/cose'; 1")
    aspetta(lambda: t.v("!!document.querySelector('#tessere [data-tessera=\"studio\"]:not(.presto)')"), 10)
    t.tocca('#tessere [data-tessera="studio"]')
    ok = aspetta(lambda: "Fra carte e domande ne ho preparate" in home(t), 10)
    verifica("il tutore vede quante ne ho preparate", bool(ok), home(t)[:500])
    aspetta(lambda: t.v("!!document.querySelector('.studio-h-carte button[data-carte=\"elenco\"]')"), 8)
    t.tocca('.studio-h-carte button[data-carte="elenco"]')
    aspetta(lambda: t.v("document.querySelectorAll('.studio-h-carte .studio-c-voce').length") >= 3, 8)
    prima = len(st.da_ripassare(LEO, vid))
    t.v("[...document.querySelectorAll('.studio-h-carte .studio-c-voce')].find((li) => "
        "/fatta da me/.test(li.innerText) && li.querySelector('button[data-carte=\"togli\"]'))"
        ".querySelector('button[data-carte=\"togli\"]').click(); 1")
    ok = aspetta(lambda: len(st.da_ripassare(LEO, vid)) == prima - 1, 8)
    verifica("il tutore toglie una carta generata: fuori dal ripasso di Leo", bool(ok), prima)


def main() -> int:
    import types
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
        cfg.studio_modo, cfg.studio_cartella, cfg.studio_lettura = "attivo", "studio", False
        cfg.studio_carte_genera, cfg.studio_domande_genera = "attiva", "attiva"
        cfg.studio_mappa_genera = "spenta"
        minori.prepara(cfg, registry=REG)
        st = S.Studio(cfg, registry=REG, log=lambda m: None)
        st.avvia_lettura(None, avvia=False)
        st.lettore = types.SimpleNamespace(in_attesa=None, sveglia=lambda: None, stato=lambda: {},
                                           close=lambda: None)
        serv = B.Servizi()
        serv.studio = st
        hub.servizi = serv
        hub.profilo = REG.by_id
        hub.tool_ctx = types.SimpleNamespace(studio=st)
        vid, ids = prepara(st)
        _, token = srv.archivio.crea_con_token("telefono", proprietario="l1", proprietario_nome="Leo")
        _, tok_a = srv.archivio.crea_con_token("telefono", proprietario="a1", proprietario_nome="Andrea")
        pagina = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/telefono/", profilo="profilo-studio-pronto",
                            opzioni=("--window-size=390,844",))
        t = B.T(pagina)
        try:
            pagina._chiama("DOM.enable")
            aspetta(lambda: pagina.valuta("document.readyState") == "complete", 10)
            pagina.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
            pagina._chiama("Page.reload")
            time.sleep(0.5)
            B.dimensione(t, 390, 844)
            scenario_telefono(t, st, vid, ids)
            pagina.pompa(0.3)
            errori = [r for r in pagina.log if r.startswith(("ECCEZIONE", "ERROR")) or "Content Security" in r]
            verifica("telefono: nessun errore JavaScript né violazione della CSP", not errori, "; ".join(errori)[:300])
        finally:
            pagina.chiudi()
        p2 = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/telefono/", profilo="profilo-studio-pronto-t",
                        opzioni=("--window-size=390,844",))
        t2 = B.T(p2)
        try:
            p2._chiama("DOM.enable")
            aspetta(lambda: p2.valuta("document.readyState") == "complete", 10)
            p2.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(tok_a)}); 1")
            p2._chiama("Page.reload")
            time.sleep(0.5)
            B.dimensione(t2, 390, 844)
            scenario_tutore(t2, st, vid)
            p2.pompa(0.3)
            errori = [r for r in p2.log if r.startswith(("ECCEZIONE", "ERROR")) or "Content Security" in r]
            verifica("tutore: nessun errore JavaScript né violazione della CSP", not errori, "; ".join(errori)[:300])
        finally:
            p2.chiudi()
            web.ferma()
            srv.ferma()
            st.close()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not B.ERRORI else f"\n{len(B.ERRORI)} prove non riuscite.")
    return 1 if B.ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
