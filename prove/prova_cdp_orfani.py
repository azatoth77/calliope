import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Il browser delle prove non resta vivo quando la prova muore (14/10/2026).

Il 14/10 sul portatile c'erano decine di processi msedge con i profili temporanei delle prove
(15 per ogni browser: il principale e i suoi figli) e le prove con il browser cadevano perché
Edge non partiva in tempo. Una prova lanciata fuori dal runner (a mano, da un agente) e fermata
da un tempo massimo o da Ctrl+C non arriva a `Browser.chiudi()`, e su Windows i figli non
muoiono con il padre. Da qui `prove/cdp.py` avvia il browser in un job object della prova.

- una prova che apre il browser e muore senza chiudi() (os._exit): nessun processo con il suo
  profilo pochi secondi dopo;
- contrario: senza il job (come prima del 14/10) il browser resta vivo (e la prova lo chiude);
- chiudi() di sempre: il browser si chiude, il job anche.
Solo su Windows (altrove 77), serve Edge o Chromium (senza, 77). ~10 s.
"""

import subprocess
import tempfile
import time
from pathlib import Path

errori = 0
TMP = Path(tempfile.mkdtemp(prefix="calliope-cdp-orfani-"))

FIGLIO = r"""
import os, sys
sys.path.insert(0, {radice!r}); sys.path.insert(0, {prove!r})
import cdp
if {senza_job}:
    import calliope.agenti.winjob as W
    W.JobObject = None                     # come prima del 14/10: niente job
b = cdp.Browser({exe!r}, {profilo!r})
print("avviato", b.proc.pid, b.job is not None, flush=True)
os._exit(3)                                # la prova muore senza chiudi()
"""


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(("ok  " if ok else "ERR ") + nome + (f"  ({dettaglio})" if dettaglio else ""),
          flush=True)


def del_profilo(profilo: Path) -> list:
    import psutil
    import cdp
    return cdp._del_profilo(psutil, str(profilo))


def muore(senza_job: bool, exe: str) -> tuple[str, list]:
    profilo = TMP / ("senza-job" if senza_job else "con-job")
    radice = str(Path(__file__).resolve().parent.parent)
    codice = FIGLIO.format(radice=radice, prove=str(Path(__file__).resolve().parent),
                           senza_job=senza_job, exe=exe, profilo=str(profilo))
    r = subprocess.run([sys.executable, "-c", codice], capture_output=True, text=True,
                       timeout=60)
    fine = time.monotonic() + 5
    vivi = del_profilo(profilo)
    while vivi and not senza_job and time.monotonic() < fine:
        time.sleep(0.2)
        vivi = del_profilo(profilo)
    if senza_job:
        time.sleep(2)
        vivi = del_profilo(profilo)
    return r.stdout.strip(), vivi


def main() -> int:
    if sys.platform != "win32":
        print("salto: i job object ci sono solo su Windows")
        return 77
    from prova_schermi_pagina import browser
    exe = browser()
    if exe is None:
        print("salto: nessun Edge o Chromium")
        return 77
    import psutil
    import cdp
    out, vivi = muore(False, exe)
    verifica("la prova muore senza chiudi(): nessun processo del browser con il suo profilo",
             out.startswith("avviato") and out.endswith("True") and not vivi,
             f"{out}; vivi {len(vivi)}")
    out, vivi = muore(True, exe)
    verifica("contrario: senza il job il browser resta vivo dopo la prova",
             out.startswith("avviato") and len(vivi) > 0, f"{out}; vivi {len(vivi)}")
    for p in vivi:                       # solo quelli con il profilo di questa prova
        try:
            p.kill()
        except Exception:  # noqa: BLE001
            pass
    psutil.wait_procs(vivi, timeout=5)
    b = cdp.Browser(exe, TMP / "normale")
    pid = b.proc.pid
    b.chiudi()
    verifica("chiudi() di sempre: browser e figli chiusi, job chiuso",
             not psutil.pid_exists(pid) and b.job is None and not del_profilo(TMP / "normale"))
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
