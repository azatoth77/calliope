import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Il segno della compagnia nelle pagine vere (09/10/2026, calliope/compagnia.py): Edge o
Chromium senza finestra comandato con DevTools (senza browser si salta), server degli schermi e
dei satelliti veri su 127.0.0.1.

- schermo di stanza: con lo stato della voce «compagnia» (più voci vicino al satellite, una
  sconosciuta) la riga discreta «In compagnia: chiamami per nome» sotto lo stato; resta quando la
  finestra d'ascolto finisce (dorme), sparisce quando la compagnia finisce; contrario: un'altra
  stanza non la vede;
- telefono: la stessa riga, piccola, sotto lo stato della voce, e sparisce;
- nessun errore JavaScript né violazione della CSP. ~15 s.
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

import prova_cruscotto_pagina as PCP
import prova_telefono_pagina as PTP

TMP = Path(tempfile.mkdtemp(prefix="calliope-compagnia-pagina-"))
ERRORI = []
SALTATA = 77
TESTO = "In compagnia: chiamami per nome"


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


aspetta = PCP.aspetta


def avvia():
    from calliope.config import Config
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.server import ServerSatelliti
    from calliope.schermi import ArchivioSchermi, Schermi
    from calliope.schermi.server import ServerSchermi
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "memoria.db")
    cfg.turn_log_dir = str(TMP / "registro")
    cfg.satellite_porta = 0
    cfg.audio_modo = "satellite"
    cfg.telefono_web = str(TMP / "web")
    srv = ServerSatelliti(cfg, ArchivioSatelliti(cfg.memory_db), log=lambda m: None).avvia()
    srv.avviato.set()
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    web = ServerSchermi(hub, "127.0.0.1", PTP.porta_libera(), attesa_porta_s=5).avvia()
    hub.server = web
    hub.satelliti = srv
    srv.schermi = hub
    hub.stanza_corrente = srv.stanza
    return cfg, srv, hub, web


RIGA = ("(() => { const e = document.querySelector('#voce .voce-compagnia');"
        " if (!e) return null; return {vista: !e.hidden && e.offsetParent !== null,"
        " testo: e.textContent}; })()")


def schermo(exe, hub, web):
    arch = hub.archivio
    _, t_cucina = arch.crea_con_token("cucina")
    _, t_studio = arch.crea_con_token("studio")
    hub._rinfresca()
    base = f"http://127.0.0.1:{web.port}/"
    p = PTP.Pagina(exe, base + f"#t={t_cucina}", profilo="profilo-cucina",
                   opzioni=("--window-size=1280,800",))
    q = PTP.Pagina(exe, base + f"#t={t_studio}", profilo="profilo-studio",
                   opzioni=("--window-size=1280,800",))
    try:
        for pag in (p, q):
            aspetta(lambda: pag.valuta("document.getElementById('stato-testo').textContent")
                    == "collegato", 10)
        hub.voce("ascolta", time.time() + 8, stanza="cucina")
        ok = aspetta(lambda: p.valuta("!document.getElementById('voce').hidden"), 5)
        r = p.valuta(RIGA)
        verifica("contrario: in ascolto senza compagnia → nessuna riga", bool(ok) and r
                 and not r["vista"], r)
        hub.voce("ascolta", time.time() + 8, stanza="cucina", compagnia=True)
        r = aspetta(lambda: (lambda x: x if x and x["vista"] else None)(p.valuta(RIGA)), 5)
        verifica("in compagnia: «In compagnia: chiamami per nome» sotto lo stato",
                 bool(r) and r["testo"] == TESTO, r)
        PCP.foto(p, "compagnia-schermo.png", 1280, 800)
        r2 = q.valuta(RIGA)
        verifica("contrario: lo schermo di un'altra stanza non la vede", not (r2 and r2["vista"]),
                 r2)
        hub.voce("dorme", stanza="cucina", compagnia=True)
        time.sleep(0.6)
        r = p.valuta(RIGA)
        verifica("addormentata, ancora in compagnia: la riga resta", bool(r and r["vista"]), r)
        hub.voce("dorme", stanza="cucina")
        r = aspetta(lambda: (lambda x: x if x and not x["vista"] else None)(p.valuta(RIGA)), 5)
        verifica("una voce sola di nuovo: la riga sparisce", bool(r), r)
        for nome, pag in (("cucina", p), ("studio", q)):
            pag.pompa(0.3)
            errori = [x for x in pag.log if x.startswith("ECCEZIONE") or "Content Security" in x]
            verifica(f"schermo {nome}: nessun errore JS né CSP", not errori, "; ".join(errori)[:300])
    finally:
        p.chiudi()
        q.chiudi()


def telefono(exe, srv, hub, web):
    _, token = srv.archivio.crea_con_token("telefono-dario", proprietario="dario",
                                           proprietario_nome="Dario")
    p = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/telefono/", profilo="profilo-tel",
                   opzioni=("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                            "--window-size=390,844"))
    try:
        aspetta(lambda: p.valuta("document.readyState") == "complete", 10)
        p.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
        p._chiama("Page.reload")
        time.sleep(0.5)
        ok = aspetta(lambda: p.valuta("!!window.calliopeTelefono && "
                                      "window.calliopeTelefono.st.collegato"), 15)
        verifica("telefono: collegato", bool(ok))
        aspetta(lambda: p.valuta("!!window.calliopeSchermo && document.getElementById('stato')"
                                 ".className.includes('ok')"), 10)
        time.sleep(0.5)
        riga = "(() => { const d = document.getElementById('tel-dove'); return d.hidden ? '' : d.textContent; })()"
        verifica("telefono, una voce sola: nessuna riga della compagnia",
                 TESTO not in (p.valuta(riga) or ""))
        hub.voce("ascolta", time.time() + 8, stanza="telefono-dario", compagnia=True)
        r = aspetta(lambda: (lambda x: x if TESTO in (x or "") else None)(p.valuta(riga)), 5)
        verifica("telefono in compagnia: la riga piccola sotto lo stato", bool(r), r)
        PCP.foto(p, "compagnia-telefono.png", 390, 844, mobile=True)
        hub.voce("ascolta", time.time() + 8, stanza="telefono-dario")
        r = aspetta(lambda: (lambda x: True if TESTO not in (x or "") else None)(p.valuta(riga)), 5)
        verifica("telefono: la riga sparisce con la compagnia", bool(r), p.valuta(riga))
        p.pompa(0.3)
        errori = [x for x in p.log if x.startswith("ECCEZIONE") or "Content Security" in x]
        verifica("telefono: nessun errore JS né CSP", not errori, "; ".join(errori)[:300])
    finally:
        p.chiudi()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    exe = PTP.browser()
    if exe is None:
        print("Nessun Edge né Chromium: prova saltata.")
        return SALTATA
    shutil.rmtree(PTP.TMP, ignore_errors=True)
    PTP.TMP = TMP
    try:
        cfg, srv, hub, web = avvia()
        try:
            schermo(exe, hub, web)
            telefono(exe, srv, hub, web)
        finally:
            web.ferma()
            srv.ferma()
            hub.archivio.close()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
