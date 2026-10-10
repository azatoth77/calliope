"""
La frase lunga con la voce vera (10/10/2026): il caso della DGX delle 17:32 rifatto con una
dettatura sintetica di ~70 s (Piper, voce maschile, pause di 250–450 ms) che entra in un `audio.Listener` vero con
Silero VAD vero, il tetto a 30 s come prima del 10/10 (così arriva due volte), il seguito unito
da `Ciclo._seguito_del_tetto` e la trascrizione con faster-whisper (GPU se c'è, altrimenti CPU).

    python prove/prova_frase_lunga_voce.py

- la dettatura arriva al tetto e i pezzi si uniscono in un turno solo, con tutta la voce;
- il testo contiene intere le frasi intorno al primo taglio («…beccare più premi. Alla fine
  mostra una classifica…»: il 10/10 «…beccare più.» era già un turno nuovo) e la fine;
- contrario: il primo pezzo da solo finisce a metà (come il 10/10);
- Whisper trascrive l'audio unito oltre la sua finestra di 30 s: il tempo dell'STT stampato.
Si salta (77) senza la voce di Piper o senza il modello di Whisper. ~20 s con la GPU.
"""
import os
import sys
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from calliope.config import Config  # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
VOCE = RADICE / "voices" / "it_IT-giorgio-medium.onnx"
errori = 0

FRASI = [
    "Calliope, voglio un gioco nuovo da mettere sugli schermi.",
    "Il giocatore parte da una stanza con tre porte, e dietro ogni porta c'è un premio o una "
    "trappola.",
    "Ogni volta che apri una porta il punteggio cambia, e le porte possono aumentare o "
    "diminuire di numero.",
    "Però attenzione, queste porte non devono aumentare o diminuire troppo, al massimo una per "
    "turno.",
    "Il gioco dura quindici turni, e vince chi ha la fortuna di beccare più premi.",
    "Alla fine mostra una classifica con i nomi dei giocatori e il punteggio di ciascuno.",
    "I colori devono essere chiari, con caratteri grandi, perché lo useranno anche i bambini.",
    "Se un giocatore trova la trappola perde metà dei punti, ma può recuperarli nel turno dopo.",
    "Aggiungi anche un suono quando si apre una porta, uno allegro per il premio e uno basso "
    "per la trappola.",
    "Quando finisce il quindicesimo turno chiedi se vogliono fare un'altra partita.",
    "Tieni il punteggio migliore della giornata e mostralo in alto a destra.",
    "Per ora basta così, poi ti dico se voglio cambiare qualcosa.",
]


def verifica(nome, cond, info=""):
    global errori
    errori += not cond
    print(f"{'ok ' if cond else 'ERR'} {nome}" + (f"  {info}" if info and not cond else ""),
          flush=True)


def dettatura() -> np.ndarray:
    """Le frasi una dopo l'altra con pause di respiro (250–500 ms, sotto silence_ms)."""
    from piper import PiperVoice
    v = PiperVoice.load(str(VOCE))
    rng = np.random.default_rng(3)
    pezzi = []
    for f in FRASI:
        pcm = b"".join(ch.audio_int16_bytes for ch in v.synthesize(f))
        x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
        n = int(len(x) * 16000 / v.config.sample_rate)
        y = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
        # Senza il silenzio che Piper mette prima e dopo (varia da una sintesi all'altra): la
        # pausa tra due frasi è solo quella scelta qui, sempre sotto silence_ms
        voce = np.flatnonzero(np.abs(y) > 0.02)
        y = y[max(0, voce[0] - 800):voce[-1] + 800] if len(voce) else y
        pezzi += [y, np.zeros(int(16000 * rng.uniform(0.25, 0.45)), np.float32)]
    return np.concatenate(pezzi)


FRAME_MIC: list = []          # la dettatura, frame per frame
VIA = threading.Event()


class MicFinto:
    """Il microfono: i frame della dettatura, ~10 volte più veloce del tempo reale. Va avanti
    solo mentre il Listener ascolta e ha letto i frame di prima: in tempo reale il VAD sta dietro
    al microfono e il buco tra un ascolto e l'altro è coperto dal pre-roll (provato a secco in
    prova_frase_lunga.py); qui, 10 volte più veloce e sotto carico (l'hook), toglierebbero voce
    a caso."""

    def __init__(self, samplerate, channels, dtype, blocksize, device, callback):
        self.cb, self.n, self._stop = callback, blocksize, threading.Event()
        self.listener = None

    def start(self):
        def gira():
            i = 0
            while not self._stop.is_set():
                L = self.listener
                if VIA.is_set() and L is not None and (not L.active or L.frames.qsize() > 2):
                    time.sleep(0.001)        # come in tempo reale: il VAD sta dietro
                    continue
                if VIA.is_set() and i < len(FRAME_MIC):
                    f, i = FRAME_MIC[i], i + 1
                else:
                    f = np.zeros(self.n, np.float32)
                self.cb(f.reshape(-1, 1), self.n, None, None)
                time.sleep(0.003)
        threading.Thread(target=gira, daemon=True).start()

    def abort(self):
        self._stop.set()

    close = abort


def parole(s: str) -> list[str]:
    import re
    return re.findall(r"\w+", s.lower())


def main():
    if not VOCE.exists():
        print(f"salto: manca la voce {VOCE.name} (voices/)")
        return 77
    from calliope.audio import Listener
    from calliope.ciclo import Ciclo
    from calliope.stt import Transcriber
    cfg = Config()
    cfg.max_utterance_s = 30                 # il tetto di prima del 10/10: arriva due volte
    try:
        stt = Transcriber(cfg)
    except Exception as e:  # noqa: BLE001 — niente modello di Whisper qui
        print(f"salto: Whisper non si carica ({type(e).__name__}: {e})")
        return 77
    audio = dettatura()
    durata = len(audio) / 16000
    print(f"   dettatura sintetica: {durata:.1f} s, Whisper su {stt.device}")

    coda = np.zeros(16000 * 2 + (-len(audio) - 16000 * 2) % 512, np.float32)  # 2 s di silenzio
    FRAME_MIC.extend(np.concatenate([audio, coda]).reshape(-1, 512))
    L = Listener(cfg, sorgente=MicFinto)
    L.stream.listener = L
    L.misura_ripresa = False
    c = object.__new__(Ciclo)
    c.listener = L
    c.s = types.SimpleNamespace(cfg=cfg, wake=None)
    out = {}

    def ascolta():
        a = L.listen()
        out["primo"] = a
        out["r"] = c._seguito_del_tetto(types.SimpleNamespace(guided=False), a)
    th = threading.Thread(target=ascolta, daemon=True)
    th.start()
    fine = time.monotonic() + 5
    while not L.active and time.monotonic() < fine:
        time.sleep(0.01)
    VIA.set()
    th.join(60)
    L.stream.abort()
    unito, tetto = out.get("r", (None, None))
    verifica("la dettatura arriva al tetto: pezzi uniti in un turno solo",
             tetto is not None and tetto["pezzi"] >= 2 and not tetto["tagliata"], tetto)
    verifica("tutta la voce nel turno (al più 0,5 s in meno: il silenzio in testa)",
             unito is not None and len(unito) / 16000 >= durata - 0.5,
             None if unito is None else round(len(unito) / 16000, 2))
    if unito is None:
        return 1
    t0 = time.perf_counter()
    testo = stt.transcribe(unito)
    dt = time.perf_counter() - t0
    print(f"   STT dell'audio unito ({len(unito) / 16000:.1f} s): {dt:.2f} s")
    p = " ".join(parole(testo))
    # Il primo taglio cade a 30 s, su «beccare più | premi» (il 10/10 «beccare più.» era già un
    # turno a sé): la parola sull'unione può uscire storpiata («paemi»), la frase dopo c'è
    import re
    verifica("il testo ha le frasi intorno al primo taglio, intere",
             "diminuire troppo" in p and "una per turno" in p
             and re.search(r"beccare più \w+ alla fine mostra una classifica", p) is not None,
             testo[150:650])
    verifica("…e la fine della dettatura", "voglio cambiare qualcosa" in p, testo[-200:])
    primo = " ".join(parole(stt.transcribe(out["primo"])))
    verifica("contrario: il primo pezzo da solo finisce a metà (come il 10/10)",
             "voglio cambiare qualcosa" not in primo, primo[-120:])
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
