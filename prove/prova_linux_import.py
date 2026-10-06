"""
Solo gli import della DGX simulata (06/10, Q7 della seconda analisi): il passo 2 di
prova_linux.py (sys.platform = linux, macchina aarch64, librerie di Windows e torch bloccate,
calliope.locale.yaml d'esempio della DGX) in ~5 s, legato nel hook a brain.py, ciclo.py,
main.py e config.py: un import solo-Windows in uno di questi file prima passava l'hook (il
livello 1 non la fa, e prova_linux intera è legata solo a vad, stt e setup/linux).

    python prove/prova_linux_import.py
"""

import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_linux as L  # noqa: E402


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    tmp = Path(tempfile.mkdtemp(prefix="calliope-linux-import-"))
    t0 = time.perf_counter()
    try:
        L.prova_dgx_simulata(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{time.perf_counter() - t0:.1f} s. " + ("Tutto a posto." if not L.errori
                                                     else f"{L.errori} errori."))
    return 1 if L.errori else 0


if __name__ == "__main__":
    sys.exit(main())
