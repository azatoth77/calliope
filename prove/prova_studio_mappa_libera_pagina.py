import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""La mappa libera dello Studio nella pagina vera (30/10, passo 7c, issue #328, epic #251;
schermi/pagina/studio.js, POST /api/studio/mappa).

Nel browser vero (Edge o Chromium senza finestra; senza si salta), il server degli schermi vero su
127.0.0.1, Leo (di fantasia) con la verifica di storia e lo scheletro confermato di
`prova_studio_mappa_pagina.py`:
- telefono a 390×844: la scheda «Da zero», «Fai la tua mappa da zero»: parte dalla radice, solo la
  sua scheda, **lo scheletro nascosto** (nessun suo concetto nella pagina né nello stato); «+
  Concetto» (l'HTML resta testo) e «Collega» coi moduli; «Un indizio»: la pagina, il testo solo con
  «Mostra»; a 320×693 niente di lato, tocchi ≥ 44 px; «Ho finito»: il confronto a parole, i
  tentativi del codice nel db, gli indicatori del metodo, le schede che tornano, «Parliamone»;
- il PC personale: la mappa libera disegnata in orizzontale;
- nessun errore JavaScript né violazione della CSP.
Con CALLIOPE_FOTO=<cartella> gli screenshot. ~20 s.

    python prove/prova_studio_mappa_libera_pagina.py
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

import prova_studio_mappa_pagina as PMP

B = PMP.B
TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-libera-pagina-"))
LEO, ANDREA, REG = PMP.LEO, PMP.ANDREA, PMP.REG
verifica, aspetta, misure = B.verifica, B.aspetta, PMP.misure
SALTATA = B.SALTATA
HTML = "<b>Le</b> spezie"
NASCOSTI = ("Cristoforo Colombo", "Il trattato di Tordesillas", "Il Portogallo", "America")


def testo(t) -> str:
    return t.v("(document.querySelector('.studio-m') || {}).innerText || ''") or ""


def scegli(t, quale):
    t.tocca(f'button[data-mappa="quale"][data-dati*="{quale}"]')


def scenario_telefono(t, st, vid):
    T_ = "window.calliopeTelefono"
    verifica("pagina caricata e collegata", bool(aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)))
    verifica("«La mappa»: il pannello", bool(PMP.apri_mappa(t)))
    scegli(t, "libera")
    ok = aspetta(lambda: t.v("!!document.querySelector('button[data-mappa=\"libera\"]')"), 6)
    verifica("la scheda «Da zero»: cosa è e «Fai la tua mappa da zero»",
             bool(ok) and "senza lo scheletro" in testo(t))
    t.tocca('button[data-mappa="libera"]')
    ok = aspetta(lambda: st.vista_mappe(LEO, vid)["a_libera"]
                 and t.v("!!document.querySelector('button[data-mappa=\"finito\"]')"), 8)
    schede = t.v("[...document.querySelectorAll('button[data-mappa=\"quale\"]')].map((b) => b.textContent)") or []
    el = testo(t)
    stato = t.v("window.CalliopeStudio.stato().mappa") or {}
    verifica("aperta: solo la sua scheda, parte dalla radice, lo scheletro nascosto (pagina e stato)",
             bool(ok) and schede == ["Da zero"] and "Le scoperte geografiche" in el
             and "tornano dopo «Ho finito»" in el and not any(x in el for x in NASCOSTI)
             and all(x["nodi"] == 0 for x in stato.get("mappe", []) if x["quale"] != "libera"),
             f"{schede} {el[:300]}")
    # + Concetto (con l'HTML, che resta testo) e Collega coi moduli
    t.tocca('button[data-mappa="nuovo"]')
    aspetta(lambda: t.v("!!document.getElementById('studio-m-testo')"), 4)
    t.v(f"(() => {{ const i = document.getElementById('studio-m-testo'); i.value = {json.dumps(HTML)};"
        " i.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()")
    t.tocca('button[data-mappa="salva"]')
    lib = lambda: st.vista_mappe(LEO, vid)["libera"]  # noqa: E731
    ok = aspetta(lambda: any(n["testo"] == HTML for n in lib()["nodi"]), 6)
    verifica("«+ Concetto»: il concetto nella mappa libera; l'HTML resta testo",
             bool(ok) and HTML in testo(t) and not t.v("!!document.querySelector('.studio-m-elenco li b b')"))
    radice = lib()["nodi"][0]["id"]
    nuovo = next(n["id"] for n in lib()["nodi"] if n["testo"] == HTML)
    t.tocca('button[data-mappa="collega"]')
    aspetta(lambda: t.v("!!document.getElementById('studio-m-da')"), 4)
    t.v(f"(() => {{ for (const [id, v] of [['studio-m-da', '{radice}'], ['studio-m-a', '{nuovo}'], ['studio-m-verbo', 'per cercare']]) {{"
        " const e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event(e.tagName === 'SELECT' ? 'change' : 'input', {bubbles: true})); }"
        " return 1; })()")
    t.tocca('button[data-mappa="salva"]')
    ok = aspetta(lambda: any(c["verbo"] == "per cercare" for c in lib()["collegamenti"]), 6)
    verifica("«Collega» coi due elenchi e il verbo", bool(ok))
    # Un indizio e «Mostra»
    t.tocca('button[data-mappa="indizio"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('button[data-mappa=\"mostra\"]')"), 6)
    el = testo(t)
    verifica("«Un indizio»: la pagina del concetto chiave che manca, senza il testo",
             bool(ok) and "Ti manca un concetto chiave di p. 114" in el
             and not any(x in el for x in NASCOSTI), el[-300:])
    misure(t, "390×844 con la mappa libera e un indizio")
    B.foto(t, "studio-libera-390x844.png")
    t.tocca('button[data-mappa="mostra"]')
    ok = aspetta(lambda: "Cristoforo Colombo" in testo(t), 6)
    verifica("«Mostra»: il testo di quel concetto soltanto",
             bool(ok) and not any(x in testo(t) for x in NASCOSTI[1:]))
    B.dimensione(t, 320, 693)
    t.v("document.querySelector('.studio-h-mappa').scrollIntoView({block: 'start'}); 1")
    misure(t, "320×693 con la mappa libera")
    B.foto(t, "studio-libera-320x693.png")
    B.dimensione(t, 390, 844)
    # Ho finito
    t.tocca('button[data-mappa="finito"]')
    ok = aspetta(lambda: "Finita" in (t.v("(document.querySelector('.studio-m-stato') || {}).textContent || ''") or ""), 8)
    el = testo(t)
    tent = st.dati.tutti("SELECT * FROM studio_tentativi")
    verifica("«Ho finito»: il confronto a parole, gli indicatori del metodo, «Parliamone»",
             bool(ok) and "Concetti chiave: 1 su 2" in el and "il metodo" in el.lower()
             and "concetti senza collegamenti: 0" in el and "Parliamone" in el
             and "Rifai" in el, el[:600])
    verifica("«Ho finito»: i tentativi dal codice (la radice «giusto»; Colombo mostrato non conta)",
             [(x["tipo"], x["esito"], x["fonte"]) for x in tent] == [("mappa", "giusto", "codice")],
             str(tent))
    schede = t.v("[...document.querySelectorAll('button[data-mappa=\"quale\"]')].map((b) => b.textContent)") or []
    verifica("dopo «Ho finito» le schede tornano", schede == ["Lo scheletro", "La mia mappa", "A memoria", "Da zero"],
             str(schede))
    misure(t, "390×844 dopo «Ho finito»")
    B.foto(t, "studio-libera-finita-390x844.png")


def scenario_pc(t):
    B.dimensione(t, 1440, 900)
    aspetta(lambda: t.v("!!window.calliopeSchermo"), 10)
    t.v("location.hash = '#/cose'; 1")
    aspetta(lambda: t.v("!!document.querySelector('#tessere [data-tessera=\"studio\"]:not(.presto)')"), 10)
    t.tocca('#tessere [data-tessera="studio"]')
    aspetta(lambda: t.v("!!document.querySelector('.studio-h-mappa button[data-mappa=\"apri\"]')"), 8)
    t.tocca('.studio-h-mappa button[data-mappa="apri"]')
    aspetta(lambda: t.v("!!document.querySelector('.studio-m')"), 8)
    scegli(t, "libera")
    aspetta(lambda: t.v("!!document.querySelector('button[data-mappa=\"vista\"]')"), 6)
    t.tocca('button[data-mappa="vista"][data-dati*="mappa"]')
    ok = aspetta(lambda: t.v("!!document.querySelector('svg.studio-m-tela')"), 6)
    verifica("PC: la mappa libera disegnata in orizzontale, i concetti chiave segnati",
             bool(ok) and t.v("document.querySelector('svg.studio-m-tela').getAttribute('viewBox')") == "0 0 1000 620"
             and t.v("!!document.querySelector('svg.studio-m-tela .studio-m-nodo.chiave')"))
    t.v("document.querySelector('svg.studio-m-tela').scrollIntoView({block: 'start'}); 1")
    B.foto(t, "studio-libera-pc.png")


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
        vid, _sk = PMP.prepara(st)
        _, token = srv.archivio.crea_con_token("telefono", proprietario="l1", proprietario_nome="Leo")
        from prova_parla_pc import CollFinto
        cfg.schermi_sezioni = True
        srv.collegati.append(CollFinto(5, "cameretta"))
        s_pc, t_pc = hub.archivio.crea_con_token("cameretta", proprietario="l1", proprietario_nome="Leo")
        hub.archivio.lega_satellite(s_pc["id"], 5)
        hub._rinfresca()
        pagina = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/telefono/", profilo="profilo-studio-libera",
                            opzioni=("--window-size=390,844",))
        t = PMP.TM(pagina)
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
        pc = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/#t={t_pc}", profilo="profilo-studio-libera-pc",
                        opzioni=("--window-size=1440,900",))
        tp = PMP.TM(pc)
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
