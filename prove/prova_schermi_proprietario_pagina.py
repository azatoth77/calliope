import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Il cambio di proprietario dello stesso schermo nella pagina vera (31/10/2026, revisione della PR
#341 per l'issue #338; area docs/aree/schermi-telefono.md).

Nel browser vero (Edge o Chromium senza finestra, DevTools; senza si salta), server degli schermi e
dei satelliti veri su 127.0.0.1. Dario ha aperto Le mie cose › Agenda, col suo promemoria; lo
schermo diventa di Bianca:
- PC personale (lo schermo reso di Bianca come fa «rendilo personale di Bianca»);
- telefono (il suo satellite reso di Bianca, come fa il tool sui satelliti: `_allinea_schermo`).
La pagina riceve «proprietario» e si ricarica da capo col token che resta: dopo il cambio nel DOM
non resta niente del promemoria di Dario, il percorso torna all'inizio, la pagina è collegata come
schermo di Bianca e la sua Agenda non ha il promemoria di Dario; nessun errore JavaScript né CSP.

    python prove/prova_schermi_proprietario_pagina.py
"""

import json
import shutil
import tempfile
import time
import types
from pathlib import Path

import prova_pc_pagina as PPC
import prova_telefono_pagina as PTP
import prova_telefono_schermo as PTS

TMP = Path(tempfile.mkdtemp(prefix="calliope-proprietario-pagina-"))
ERRORI = []
SALTATA = 77
DARIO = "chiamare il fabbro"            # il promemoria di Dario (PTS.prepara_raccolte)


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio and not ok else ""),
          flush=True)
    if not ok:
        ERRORI.append(nome)


def aspetta(cond, max_s=8.0, passo=0.1):
    fine = time.monotonic() + max_s
    while time.monotonic() < fine:
        try:
            v = cond()
        except Exception:  # noqa: BLE001 — la pagina si sta ricaricando
            v = None
        if v:
            return v
        time.sleep(passo)
    return None


def profili(hub):
    """Dario (amministra) e Bianca: tutte e due con un profilo, così le pagine di Bianca si leggono."""
    def profilo(pid):
        if pid not in ("dario", "bianca"):
            return None
        return types.SimpleNamespace(id=pid, name=pid.title(), admin=pid == "dario", nascita=None, fascia=None)
    hub.profilo = profilo


def nel_dom(p, testo) -> bool:
    return bool(p.valuta(f"document.body.textContent.includes({json.dumps(testo)})"))


def dopo_il_cambio(p, hub, sid, nome, vai_agenda):
    """Dopo il cambio: la pagina ricaricata, collegata come schermo di Bianca, senza niente di Dario."""
    ricaricata = aspetta(lambda: p.valuta("window.__primaDelCambio === undefined && document.readyState === 'complete'"), 10)
    verifica(f"{nome}: la pagina riceve «proprietario» e si ricarica da capo", bool(ricaricata))
    collegata = aspetta(lambda: any(s.get("id") == sid and s.get("proprietario") == "bianca"
                                    for s in hub.collegati()), 15)
    verifica(f"{nome}: il token vale ancora, collegata come schermo di Bianca", bool(collegata),
             json.dumps(hub.collegati(), default=str)[:300])
    time.sleep(1.0)
    verifica(f"{nome}: nel DOM non resta niente del promemoria di Dario, il percorso è all'inizio",
             not nel_dom(p, DARIO) and p.valuta("location.hash") in ("", "#", "#/", "#/adesso"),
             str(p.valuta("location.hash")))
    vai_agenda()
    ok = aspetta(lambda: "per la pasta" in (p.valuta("document.getElementById('pagina-schede').textContent") or ""), 8)
    verifica(f"{nome}: l'Agenda è quella di Bianca (il timer di casa sì, il promemoria di Dario no)",
             bool(ok) and not nel_dom(p, DARIO),
             (p.valuta("document.getElementById('pagina-schede').textContent") or "")[:200])
    p.pompa(0.3)
    errori = [r for r in p.log if r.startswith("ECCEZIONE") or "Content Security" in r]
    verifica(f"{nome}: nessun errore JavaScript né violazione della CSP", not errori, "; ".join(errori)[:300])


def pc(exe):
    PPC.TMP = TMP / "pc"
    PPC.TMP.mkdir(parents=True, exist_ok=True)
    cfg, srv, hub, web, coll, t_pc, _ = PPC.avvia_server()
    profili(hub)
    sid = next(s["id"] for s in hub.abbinati() if s.get("proprietario") == "dario")
    P = "window.calliopePC"
    S = f"({P}.stato() || {{}})"
    p = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/#t={t_pc}", profilo="profilo-proprietario-pc",
                   opzioni=("--window-size=1440,900",))
    try:
        ok = aspetta(lambda: p.valuta(f"!!{P} && !!{P}.stato() && document.body.classList.contains('con-sezioni')"), 15)
        verifica("PC: lo schermo personale di Dario con le sezioni", bool(ok))
        if not ok:
            return

        def agenda():
            p.valuta(f"{P}.vai('#/cose'); 1")
            aspetta(lambda: len(p.valuta(f"{S}.tessere") or []) >= 3, 5)
            p.valuta(f"{P}.vai('#/cose/agenda'); 1")
        agenda()
        ok = aspetta(lambda: DARIO in (p.valuta("document.getElementById('pagina-schede').textContent") or ""), 8)
        verifica("PC: Le mie cose › Agenda mostra il promemoria di Dario", bool(ok))
        p.valuta("window.__primaDelCambio = 1; 1")
        # «Rendilo personale di Bianca»: come fa il tool dopo il «sì»
        hub.archivio.imposta_proprietario(sid, "bianca", "Bianca")
        hub._rinfresca()
        hub.abbinati()
        dopo_il_cambio(p, hub, sid, "PC", agenda)
    finally:
        p.chiudi()
        web.ferma()
        srv.ferma()


def telefono(exe):
    cfg, srv, hub, web = PTS.avvia(TMP / "tel")
    PTS.prepara_raccolte(cfg, hub, TMP / "tel")
    profili(hub)
    sat, token = srv.archivio.crea_con_token("telefono", proprietario="dario", proprietario_nome="Dario")
    T = "window.calliopeTelefono"
    S = f"({T}.sezioni() || {{}})"
    p = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/telefono/", profilo="profilo-proprietario-tel",
                   opzioni=("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                            "--window-size=390,844"))
    try:
        p._chiama("Page.addScriptToEvaluateOnNewDocument", {"source": PTS.FINTA})
        aspetta(lambda: p.valuta("document.readyState") == "complete", 10)
        p.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
        p._chiama("Page.reload")
        time.sleep(0.5)
        ok = aspetta(lambda: p.valuta(f"!!{T} && {T}.st.collegato") and hub.collegati(), 15)
        verifica("telefono: collegato come satellite e come schermo di Dario", bool(ok))
        if not ok:
            return
        sid = next(s["id"] for s in hub.abbinati() if s.get("satellite") == sat["id"])

        def agenda():
            p.valuta(f"{T}.vai('#/cose'); 1")
            aspetta(lambda: any(x["id"] == "agenda" for x in p.valuta(f"{S}.tessere") or []), 8)
            p.valuta(f"{T}.vai('#/cose/agenda'); 1")
        agenda()
        ok = aspetta(lambda: DARIO in (p.valuta("document.getElementById('pagina-schede').textContent") or ""), 8)
        verifica("telefono: Le mie cose › Agenda mostra il promemoria di Dario", bool(ok))
        p.valuta("window.__primaDelCambio = 1; 1")
        # Il satellite reso di Bianca (il tool sui satelliti): lo schermo lo segue (_allinea_schermo)
        srv.imposta_proprietario(sat["id"], "bianca", "Bianca")
        dopo_il_cambio(p, hub, sid, "telefono", agenda)
    finally:
        p.chiudi()
        web.ferma()
        srv.ferma()


def main() -> int:
    shutil.rmtree(PTP.TMP, ignore_errors=True)
    PTP.TMP = TMP
    try:
        exe = PTP.browser()
        if exe is None:
            print("Nessun Edge né Chromium: prova saltata.")
            return SALTATA
        pc(exe)
        telefono(exe)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
