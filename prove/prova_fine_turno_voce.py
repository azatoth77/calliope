import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""La fine del turno System 1 con il modello vero (14/10, livello 3): Smart Turn v3.2
(models/fine_turno/, `--installa modello_fine_turno`), Silero VAD in ONNX e frasi sintetiche
di Piper deterministiche (`prova_satellite.sintetizza(deterministica=True)`).

- frasi complete: alla chiusura «finito» sicuro, chiusura anticipata nell'ombra;
- frasi sospese con una pausa di 400 ms dopo «e poi,» e «poi,» (intonazione che resta su):
  la pausa interna è «non finito», nessun taglio;
- `audio.Listener` in «attiva» con un microfono finto a tempo reale: la frase completa si
  chiude prima dei 700 ms di silenzio;
- solo misura (stampata, non controllata): le frasi sospese dopo «in», «e», un numero, un
  elenco e dopo il nome. Con Piper ogni pezzo finisce con l'intonazione di fine frase, e il
  modello le prende per finite: la valutazione vera è sulla voce conservata della DGX
  (`prove/manuali/fine_turno_dgx.py`).

Si salta (77) senza il modello, senza le voci di Piper o senza il VAD in ONNX.
"""

import queue
import threading
import time
from pathlib import Path

import numpy as np

from calliope.config import Config
from calliope.system1 import fine_turno as ft

RADICE = Path(__file__).resolve().parent.parent
errori = 0


def verifica(nome, cond, info=""):
    global errori
    errori += not cond
    print(f"{'ok ' if cond else 'ERR'} {nome}" + (f"  {info}" if info and not cond else ""))


def main():
    modello = RADICE / ft.MODELLO_PREDEFINITO
    if not modello.is_file():
        print(f"SALTATA: manca il modello ({ft.MODELLO_PREDEFINITO}): python -m calliope.stato "
              f"--installa modello_fine_turno")
        return 77
    from calliope.vad import SileroOnnx, modello_onnx
    p = modello_onnx()
    if p is None:
        print("SALTATA: manca Silero VAD in ONNX")
        return 77
    from prova_satellite import sintetizza
    complete = ["Accendi la luce in cucina.", "Che ore sono?", "Metti il pane nella lista.",
                "Spegni tutto e poi accendi la radio."]
    sospese = [("Ricordami di comprare il latte, e poi,", "il pane."),
               ("Spegni tutto, poi,", "accendi la radio.")]
    misura = [("Accendi la luce in", "cucina."), ("Ricordami di comprare il latte e", "il pane."),
              ("Il numero è tre quattro sette,", "due nove uno."),
              ("Metti nella lista pane, latte,", "uova e biscotti."),
              ("Calliope,", "che ore sono?")]
    testi = sorted(set(complete) | {t for c in sospese + misura for t in c})
    au = sintetizza(testi, deterministica=True)
    if au is None:
        print("SALTATA: mancano le voci di Piper (voices/)")
        return 77
    rng = np.random.default_rng(0)

    def nudo(x):
        nz = np.nonzero(np.abs(x) > 0.01)[0]
        return x[nz[0]:nz[-1] + 1]

    def frase(*pezzi, pausa_ms=400, coda_ms=1000):
        parti = [np.zeros(4800, np.float32)]
        for i, t in enumerate(pezzi):
            if i:
                parti.append(np.zeros(pausa_ms * 16, np.float32))
            parti.append(nudo(au[t]))
        parti.append(np.zeros(coda_ms * 16, np.float32))
        y = np.concatenate(parti)
        return (y + rng.standard_normal(len(y)).astype(np.float32) * 0.002).astype(np.float32)

    cfg = Config()
    dec = ft.SmartTurn(modello)
    vad = SileroOnnx(p)
    o = ft.OmbraFineTurno(cfg, decisore=dec, vad=vad, log=lambda *_: None)

    def ombra(y):
        fut = o.valuta(y)
        a = {}
        o.chiudi(a, fut, attesa_s=30)
        return a["fine_turno"], fut.result()

    ms = []
    for t in complete:
        e, sim = ombra(frase(t))
        ms.append(e.get("ms_max") or 0)
        verifica(f"completa «{t}»: «finito» sicuro, chiusura anticipata",
                 e["esito"] == "anticipo" and (e.get("p") or 0) >= 0.9, e)
    for a, b in sospese:
        e, sim = ombra(frase(a, b))
        ms.append(e.get("ms_max") or 0)
        interne = sim.get("interne") or []
        verifica(f"sospesa «{a} … {b}»: la pausa di 400 ms è «non finito», nessun taglio",
                 interne and interne[0]["p"] is not None and interne[0]["p"] < 0.5
                 and e["esito"] != "taglio", sim)
    print("solo misura (Piper chiude ogni pezzo con l'intonazione di fine frase):")
    for a, b in misura:
        e, sim = ombra(frase(a, b))
        print(f"    «{a} … {b}»: pause interne p = "
              f"{[i['p'] for i in sim.get('interne') or []]}, esito {e['esito']}")
    print(f"decisore sul portatile: p50 {sorted(ms)[len(ms) // 2]:.0f} ms, massimo "
          f"{max(ms):.0f} ms")
    o.ferma()

    # Listener in «attiva»: microfono finto a tempo reale
    from calliope.audio import Listener
    mic: queue.Queue = queue.Queue()

    class Mic:
        def __init__(self, samplerate, channels, dtype, blocksize, device, callback):
            self.cb, self.n, self._stop = callback, blocksize, threading.Event()

        def start(self):
            def gira():
                prossimo = time.monotonic()
                while not self._stop.is_set():
                    try:
                        f = mic.get_nowait()
                    except queue.Empty:
                        f = np.zeros(self.n, np.float32)
                    self.cb(f.reshape(-1, 1), self.n, None, None)
                    prossimo += 0.032
                    time.sleep(max(0.0, prossimo - time.monotonic()))
            threading.Thread(target=gira, daemon=True).start()

        def abort(self):
            self._stop.set()

        close = abort

    cfg = Config()
    cfg.fine_turno, cfg.vad_motore = "attiva", "onnx"
    L = Listener(cfg, sorgente=Mic)
    L.misura_ripresa = False
    ft.prepara_listener(L, cfg, log=lambda *_: None, decisore=ft.SmartTurn(modello))
    y = frase("Accendi la luce in cucina.", coda_ms=1500)
    out = {}
    th = threading.Thread(target=lambda: out.setdefault("a", L.listen()), daemon=True)
    th.start()
    t0 = time.monotonic()
    while not L.active and time.monotonic() - t0 < 3:
        time.sleep(0.01)
    for i in range(len(y) // 512):
        mic.put(y[i * 512:(i + 1) * 512])
    th.join(15)
    e = L.fine_turno_esito or {}
    verifica("Listener in «attiva»: la frase completa si chiude prima dei 700 ms",
             L.chiusura == "anticipata" and e.get("silenzio_ms", 999) < 700, e)
    print(f"    chiusa dopo {e.get('silenzio_ms')} ms di silenzio (p {e.get('p')}, decisore "
          f"{e.get('ms')} ms)")
    L.stream.abort()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
