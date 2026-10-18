"""Parti comuni degli script di prove/arm/: cartella dei dati e memoria del processo (18/10, #64).

Sulla DGX codice e dati stanno in cartelle diverse (codice nella versione installata, dati in
~/calliope) e `psutil` non c'è su Linux (dipendenza solo di Windows): gli script prima facevano
`chdir` sulla cartella del codice, non trovavano la biblioteca, e uscivano con ImportError.
"""
import os
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]


def prepara(argv: list[str]) -> list[str]:
    """Toglie `--dati <cartella>` dagli argomenti e sceglie la cartella di lavoro.

    Con `--dati` si lavora nella cartella dei dati (calliope.yaml, il file locale e i percorsi
    relativi della biblioteca sono quelli di lì, locale compreso: serve per trovare i file
    veri). Senza, come prima: la cartella del codice e niente calliope.locale.yaml, come le
    altre prove. Restituisce gli argomenti senza `--dati`."""
    argv = list(argv)
    dati = None
    if "--dati" in argv:
        i = argv.index("--dati")
        if i + 1 >= len(argv):
            sys.exit("--dati vuole una cartella")
        dati = Path(argv[i + 1]).expanduser().resolve()
        del argv[i:i + 2]
        if not dati.is_dir():
            sys.exit(f"Cartella dei dati assente: {dati}")
    if str(RADICE) not in sys.path:
        sys.path.insert(0, str(RADICE))
    if dati:
        os.chdir(dati)
    else:
        os.chdir(RADICE)
        os.environ.setdefault("CALLIOPE_CONFIG_LOCALE",
                              str(RADICE / "prove" / "nessun-file-locale.yaml"))
    return argv


def _status_linux() -> dict[str, int]:
    """Campi in kB di /proc/self/status (Linux); vuoto altrove."""
    out = {}
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            for riga in f:
                nome, _, valore = riga.partition(":")
                parti = valore.split()
                if len(parti) == 2 and parti[1] == "kB":
                    out[nome] = int(parti[0])
    except OSError:
        pass
    return out


def memoria() -> dict[str, float]:
    """Memoria del processo in MB: `rss_mb`, `privata_mb` e `picco_mb`.

    Windows: psutil (memoria privata e picco del working set). Linux, solo libreria standard:
    `RssAnon` di /proc/self/status come memoria privata (le pagine anonime: senza le pagine dei
    file ZIM e degli indici mappate o in cache, che sono condivise) e `ru_maxrss` per il
    picco."""
    try:
        import psutil
        info = psutil.Process().memory_info()
        if getattr(info, "private", 0):
            return dict(rss_mb=round(info.rss / 2**20, 1),
                        privata_mb=round(info.private / 2**20, 1),
                        picco_mb=round(getattr(info, "peak_wset", 0) / 2**20, 1))
    except ImportError:
        pass
    st = _status_linux()
    picco = 0.0
    try:
        import resource
        picco = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024   # kB su Linux
    except ImportError:
        pass
    return dict(rss_mb=round(st.get("VmRSS", 0) / 1024, 1),
                privata_mb=round(st.get("RssAnon", 0) / 1024, 1),
                picco_mb=round(picco or st.get("VmHWM", 0) / 1024, 1))
