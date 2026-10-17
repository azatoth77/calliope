"""Una prova in più corsie insieme, sotto carico (17/10, #5): per cercare le cadute che vengono
dalla prova (attese fisse, porte prese e rilasciate) e non dal codice.

    python prove/manuali/carico.py prova_satellite.py [--corsie 3] [--giri 20] [--carico 16]
                                   [--porte 0] [--uscita cartella]

Lancia la prova come la lancia il runner (`prove.__main__.lancia`: stesso ambiente, job object,
processi lasciati vivi contati come errore) dal repository (o worktree) di questo file, in
`--corsie` corsie parallele, `--giri` volte per corsia, mentre `--carico` processi Python girano a vuoto
(pieni: un core ciascuno) e, con `--porte N`, N thread aprono e chiudono porte effimere in
ascolto (come le altre prove di un `--completo`, per le corse sulle porte). I processi di
carico sono figli di questo script e finiscono con lui (anche con Ctrl+C).

Stampa ogni giro (verde o caduto, secondi, frasi ripetute perché la wake word non è scattata:
la riga «nota: N frasi ripetute» di prova_satellite, contata a parte per non confonderla con
una caduta) e alla fine il riepilogo; una prova saltata, anche in parte, ferma le corsie
ed esce con 2 (la misura non vale); l'uscita di ogni giro va in `--uscita` (di serie una
cartella temporanea), con le righe ERR in testa al file dei caduti.

Le misure del 15/10 (`prova_telefono_audio`, `prova_esercizi_voce`) e del 17/10
(`prova_satellite`) sono state prese così, sul portatile di sviluppo (24 core): 3 corsie e
16 processi di carico.
"""

import argparse
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RADICE))
from prove.__main__ import lancia  # noqa: E402
GIRA_A_VUOTO = "import time\nfine = time.time() + {s}\nwhile time.time() < fine: sum(range(10000))"


def porte_che_girano(fine: float):
    while time.time() < fine:
        try:
            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            s.listen(4)
            time.sleep(0.05)
            s.close()
        except OSError:
            time.sleep(0.01)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("prova", help="il file della prova, come per `python -m prove`")
    ap.add_argument("--corsie", type=int, default=3)
    ap.add_argument("--giri", type=int, default=20, help="giri per corsia")
    ap.add_argument("--carico", type=int, default=16, help="processi Python pieni")
    ap.add_argument("--porte", type=int, default=0, help="thread che girano porte effimere")
    ap.add_argument("--uscita", default=None, help="cartella delle uscite dei giri")
    ap.add_argument("--massimo", type=float, default=4 * 3600,
                    help="secondi oltre i quali il carico si ferma da solo")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    uscita = Path(a.uscita or tempfile.mkdtemp(prefix="calliope-carico-"))
    uscita.mkdir(parents=True, exist_ok=True)
    fine = time.time() + a.massimo
    carico = [subprocess.Popen([sys.executable, "-c", GIRA_A_VUOTO.format(s=fine)])
              for _ in range(a.carico)]
    for _ in range(a.porte):
        threading.Thread(target=porte_che_girano, args=(fine,), daemon=True).start()
    esiti, lock, saltati = [], threading.Lock(), []
    nome = Path(a.prova).stem

    def corsia(i: int):
        for g in range(a.giri):
            if saltati:
                return
            r = lancia(a.prova, [])
            dur, testo = r["dt"], r["out"]
            # Saltata (77) o saltata in parte (voci, modelli o CAM++ assenti nel worktree): il
            # giro non vale né come verde né come caduta, e le corsie si fermano (17/10)
            if r["esito"] == "saltata" or "SALTATA IN PARTE" in testo:
                riga = next((x for x in testo.splitlines() if "SALTATA" in x), r["esito"])
                with lock:
                    saltati.append(riga)
                    print(f"corsia {i} giro {g}: SALTATA, mi fermo — {riga.strip()}", flush=True)
                return
            verde = r["esito"] == "ok"
            m = re.search(r"nota: (\d+) frasi ripetute", testo)
            ripetute = int(m.group(1)) if m else 0
            err = [r for r in testo.splitlines() if r.startswith("ERR ")]
            f = uscita / f"{nome}.{i}.{g}{'' if verde else '.CADUTA'}.txt"
            f.write_text("\n".join(err + ["", testo]) if err else testo, encoding="utf-8")
            with lock:
                esiti.append((i, g, verde, dur, ripetute))
                print(f"corsia {i} giro {g}: {'verde' if verde else 'CADUTA'} {dur:.0f} s"
                      + (f", {ripetute} ripetute" if ripetute else "")
                      + ("" if verde else f" — {err[0][4:] if err else f.name}"), flush=True)

    fili = [threading.Thread(target=corsia, args=(i,)) for i in range(a.corsie)]
    try:
        for t in fili:
            t.start()
        for t in fili:
            t.join()
    finally:
        for c in carico:
            c.kill()
    if saltati:
        print(f"\n{nome}: prova saltata ({saltati[0].strip()}): la misura non vale. Mancano file "
              f"fuori da git nel worktree? (voices/, models/speaker/, wakeword/modelli/)")
        return 2
    verdi = sum(e[2] for e in esiti)
    durate = sorted(e[3] for e in esiti) or [0.0]
    print(f"\n{nome}: {verdi}/{len(esiti)} verdi con {a.corsie} corsie, {a.carico} processi di "
          f"carico{f', {a.porte} thread di porte' if a.porte else ''}; durata mediana "
          f"{durate[len(durate) // 2]:.0f} s (massima {durate[-1]:.0f}); frasi ripetute "
          f"{sum(e[4] for e in esiti)}; uscite in {uscita}")
    return 0 if verdi == len(esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
