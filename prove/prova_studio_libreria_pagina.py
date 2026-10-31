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
- le attività (31/10, parte 2): «Apri» su una mini-app manda il tocco `studio_attivita` col
  bersaglio; eseguito come lo esegue il ciclo, il gioco arriva sul telefono nel riquadro, il motore
  gira (l'istantanea della partita arriva al server) e la pagina sta nel palco;
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
    # La preparazione dietro le quinte, pronta (#297, parte 3): una lezione per l'argomento 1 e
    # due reazioni validate per «Bilancia la reazione», scritte come le scrive il lettore
    from calliope.studio import preparazione as PR
    aid = st.argomenti(LEO, vid)[0]["id"]
    f = PR.firma(st._argomenti_per_carte(vid), st._pagine_di(vid), "attiva")
    st.proponi_preparazione(vid, f, {
        "lezioni": [{"argomento": aid, "paragrafi": [
            {"testo": "<b>Gli atomi</b> si conservano: si contano a sinistra e a destra.",
             "pagine": [], "avvisi": []},
            {"testo": "Un paragrafo con un avviso non si mostra.", "pagine": [],
             "avvisi": ["da_controllare"]}]}],
        "valori": {"reazioni": [
            {"sinistra": [[None, "C"], [1, "O2"]], "destra": [[1, "CO2"]], "giusto": 1},
            {"sinistra": [[2, "Mg"], [1, "O2"]], "destra": [[None, "MgO"]], "giusto": 2}],
            "misure": []}}, PR.PRONTE, "attiva")
    return vid


def scenario_telefono(t, hub, st, vid):
    from calliope.studio.libreria import Libreria
    lib = Libreria.carica()
    T_ = "window.calliopeTelefono"
    verifica("pagina caricata e collegata", bool(aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)))
    t.v("location.hash = '#/cose'; 1")
    aspetta(lambda: t.v("!!document.querySelector('#tessere [data-tessera=\"studio\"]:not(.presto)')"), 10)
    t.tocca('#tessere [data-tessera="studio"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('#studio-home .studio-l')"), 15)
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


def scenario_attivita(t, hub, st, vid):
    """«Apri» su un'attività della libreria: il tocco al ciclo, eseguito come lo esegue il ciclo
    (ToolRegistry.call col bersaglio), poi il gioco sul telefono."""
    import types
    from calliope.config import Config  # noqa: F401
    from calliope.tools.registry import ToolRegistry
    from calliope.tools.spec import ToolContext
    from calliope.tools.studio import studio_specs
    t.v("document.querySelector('.studio-l').scrollIntoView({block: 'start'}); 1")
    sel = 'button[data-tocco="studio_attivita"][data-dati*="chimica-reazioni-app"]'
    ok = aspetta(lambda: t.v(f"!!document.querySelector('{sel}')"), 6)
    verifica("«Dalla libreria»: l'attività «Bilancia la reazione» con «Apri»", bool(ok))
    t.tocca(sel)
    item = aspetta(lambda: hub.ingresso.prendi(), 5)
    verifica("«Apri»: il tocco al ciclo con studio_attivita e il bersaglio",
             bool(item) and item["tool"] == "studio_attivita"
             and item["bersaglio"]["studio"] == {"verifica": vid, "contenuto": "chimica-reazioni-app"},
             str(item)[:300])
    if not item:
        return
    reg = ToolRegistry()
    for s in studio_specs():
        reg.register(s)
    sc = types.SimpleNamespace(current_speaker="Leo", identified_by="schermo", minore_incerto=None,
                               current_level="familiare", profile_level="familiare")
    ctx = ToolContext(cfg=hub.cfg, speakers=REG, speaker_ctx=sc, speaker=None)
    ctx.studio, ctx.schermi = st, hub
    ctx.tocco_bersaglio = item.get("bersaglio")
    hub.origine_corrente = lambda: {"schermo": item["schermo_id"]}
    r = json.loads(reg.call(item["tool"], item["argomenti"], ctx, "familiare"))
    hub.evento_a(item["schermo_id"], "tocco", {"tocco": item["tocco"], "ok": bool(r.get("ok", True)),
                                               "pagina": item.get("pagina") or {}})
    verifica("il tool apre la mini-app, coi parametri preparati dai materiali", r.get("ok") is not False and any(
        p.nome == "libreria_bilancia" and p.parametri and len(p.parametri["reazioni"]) == 2
        for p in hub.giochi.partite.values()), str(r)[:200])
    ok = aspetta(lambda: t.v("!!document.querySelector('iframe.riquadro-gioco')"), 10)
    verifica("il gioco arriva sul telefono nel riquadro", bool(ok))
    p = next((x for x in hub.giochi.partite.values() if x.nome == "libreria_bilancia"), None)
    ok = aspetta(lambda: p is not None and any(x.attivi for x in p.posti.values()), 15)
    verifica("il motore gira nel riquadro: la partita arriva al server coi comandi attivi",
             bool(ok), str([x.attivi for x in p.posti.values()]) if p else "")
    ok = aspetta(lambda: p is not None and any(getattr(x, "palco", None) is not None for x in p.posti.values()), 20)
    ok = ok and all(x.palco in (None, []) for x in p.posti.values())
    verifica("la pagina del gioco sta nel palco sul telefono vero (la misura del motore)", bool(ok),
             str([getattr(x, "palco", None) for x in p.posti.values()]) if p else "")
    # «Inizia» (la stessa strada della voce): la prima domanda del percorso, misurata anche lei
    if p is not None and p.posti:
        sid = next(iter(p.posti))
        verifica("la preparazione di una mini-app per uno: «Inizia» senza «Gioco anch'io»",
                 "inizia" in (p.posti[sid].attivi or []) and "anchio" not in (p.posti[sid].attivi or []),
                 str(p.posti[sid].attivi))
        hub.giochi.comando(p.id, sid, "inizia")
        ok = aspetta(lambda: "coeff_1" in (p.posti[sid].attivi or []), 15)
        time.sleep(1.0)            # la misura del motore arriva dopo due fotogrammi, se cambia
        verifica("«Inizia»: la prima domanda del percorso coi coefficienti, nel palco",
                 bool(ok) and p.posti[sid].palco == [], f"{p.posti[sid].attivi} {p.posti[sid].palco}")
    B.foto(t, "studio-libreria-attivita-390x844.png")
    # A 320×693 col testo al 125 %: il palco si riscala, la pagina del gioco ci sta ancora
    if p is not None and p.posti:
        B.dimensione(t, 320, 693)
        t.v("document.documentElement.style.fontSize = '125%'; 1")
        time.sleep(1.5)
        r = t.v("(() => { const f = document.querySelector('iframe.riquadro-gioco'); if (!f) return null; "
                "const r = f.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom, "
                "innerWidth, innerHeight]; })()") or []
        dentro = bool(r) and r[0] >= -1 and r[1] >= -1 and r[2] <= r[4] + 1 and r[3] <= r[5] + 1
        verifica("320×693 col testo al 125 %: il riquadro dentro lo schermo e la pagina nel palco",
                 dentro and all(x.palco in (None, []) for x in p.posti.values()),
                 f"{r} {[x.palco for x in p.posti.values()]}")
        B.foto(t, "studio-libreria-attivita-320x693-grande.png")
        t.v("document.documentElement.style.fontSize = ''; 1")
        B.dimensione(t, 390, 844)


def scenario_preparazione(t, hub, st, vid):
    """La preparazione pronta nella home (#297, parte 3): «Pronto dalle tue pagine», la lezione
    con textContent, il paragrafo con un avviso nascosto."""
    ok = aspetta(lambda: t.v("!!document.querySelector('.studio-l-prep')"), 10)
    pr = t.v("(document.querySelector('.studio-l-prep') || {}).innerText || ''") or ""
    verifica("la preparazione pronta: «Pronto dalle tue pagine» con l'attività adattata",
             bool(ok) and "Pronto dalle tue pagine" in pr and "«Bilancia la reazione»" in pr, pr[:200])
    t.tocca('button[data-libreria="lezione"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('.studio-l-lezione .studio-l-testo')"), 6)
    testi = t.v("[...document.querySelectorAll('.studio-l-lezione .studio-l-testo')].map((e) => e.textContent)") or []
    verifica("la lezione: i paragrafi senza avvisi, scritti come testo (l'HTML resta testo)",
             bool(ok) and testi == ["<b>Gli atomi</b> si conservano: si contano a sinistra e a destra."]
             and not t.v("!!document.querySelector('.studio-l-lezione b')"), str(testi))
    misure(t, "390×844 con la lezione preparata")
    t.tocca('button[data-libreria="lezione_chiudi"]')
    aspetta(lambda: not t.v("!!document.querySelector('.studio-l-lezione')"), 4)


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
        cfg.studio_preparazione = "attiva"
        minori.prepara(cfg, registry=REG)
        st = S.Studio(cfg, registry=REG, log=lambda m: None)
        st.avvia_lettura(None, avvia=False)
        serv = B.Servizi()
        serv.studio = st
        hub.servizi = serv
        hub.profilo = REG.by_id
        hub.tool_ctx = types.SimpleNamespace(studio=st)
        # I giochi (le attività della libreria, parte 2): senza le estensioni, coi file della libreria
        from calliope.schermi.giochi import Giochi
        hub.giochi = Giochi(cfg, hub, None, log=lambda *a: None)
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
            B.dimensione(t, 390, 844)
            scenario_preparazione(t, hub, st, vid)
            scenario_attivita(t, hub, st, vid)
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
