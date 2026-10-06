"""
Un satellite vero (calliope/satellite/client.py: VAD Silero, wake word acustica, protocollo,
riproduzione) con il microfono e le casse finti (06/10/2026). Il microfono «sente» un filo di
rumore e le frasi messe in coda, in tempo reale; le casse tengono l'audio che Calliope dice
(per ritrascriverlo con Whisper) e l'istante di ogni scrittura. Le frasi che il server manda
(testo), i fine turno e i suoni d'ascolto si registrano con l'istante.
"""
from __future__ import annotations

import collections
import json
import threading
import time
from pathlib import Path

import numpy as np

RATE = 16000


class Scena:
    """Ciò che sente il microfono finto: rumore leggero e le frasi in coda."""

    def __init__(self, seme: int = 1):
        self._q = collections.deque()
        self._lock = threading.Lock()
        self._buf = np.zeros(0, np.float32)
        self._evento = None
        self.rng = np.random.default_rng(seme)

    def di(self, audio: np.ndarray) -> threading.Event:
        ev = threading.Event()
        ev.t = None
        # Silenzio intorno, come una persona che comincia a parlare
        x = np.concatenate([np.zeros(int(0.3 * RATE), np.float32), audio.astype(np.float32),
                            np.zeros(int(0.1 * RATE), np.float32)])
        with self._lock:
            self._q.append((x, ev, len(x) - int(0.1 * RATE)))
        return ev

    def frame(self, n=512) -> np.ndarray:
        rumore = self.rng.normal(0, 3e-4, n).astype(np.float32)
        with self._lock:
            if len(self._buf) == 0 and self._q:
                self._buf, self._evento, self._resto = self._q.popleft()
                self._fatti = 0
            if len(self._buf):
                out, self._buf = self._buf[:n], self._buf[n:]
                self._fatti += len(out)
                if len(out) < n:
                    out = np.concatenate([out, np.zeros(n - len(out), np.float32)])
                if self._evento is not None and self._fatti >= self._resto:
                    # Istante della fine del parlato (l'ultimo campione di voce)
                    self._evento.t = time.monotonic()
                    self._evento.set()
                    self._evento = None
                return out + rumore
        return rumore


class MicFinto:
    """Come sd.InputStream: la callback ogni 32 ms con 512 campioni, al ritmo vero."""

    def __init__(self, scena, samplerate, channels, dtype, blocksize, device, callback):
        self.scena, self.cb, self.n = scena, callback, blocksize
        self._stop = threading.Event()

    def start(self):
        def gira():
            t0, i = time.monotonic(), 0
            while not self._stop.is_set():
                self.cb(self.scena.frame(self.n).reshape(-1, 1), self.n, None, None)
                i += 1
                attesa = t0 + i * self.n / RATE - time.monotonic()
                if attesa > 0:
                    time.sleep(attesa)
        threading.Thread(target=gira, daemon=True, name="mic-finto").start()

    def abort(self):
        self._stop.set()

    close = abort


class Casse:
    """Le scritture delle casse: (inizio, fine, pcm, rate, voce?)."""

    def __init__(self):
        self.scritture = []
        self.lock = threading.Lock()

    def flusso(self, samplerate, channels, dtype, device):
        return _Uscita(self, samplerate)

    def ultima_voce(self) -> float:
        with self.lock:
            v = [b for a, b, _, _, voce in self.scritture if voce]
        return max(v) if v else 0.0

    def prima_voce_dopo(self, t: float) -> float | None:
        with self.lock:
            for a, b, _, _, voce in self.scritture:
                if voce and a >= t:
                    return a
        return None

    def audio_tra(self, t0: float, t1: float) -> tuple[np.ndarray, int]:
        with self.lock:
            pezzi = [(p, r) for a, b, p, r, voce in self.scritture if t0 <= a <= t1]
        if not pezzi:
            return np.zeros(0, np.float32), RATE
        rate = pezzi[-1][1]
        x = np.concatenate([np.frombuffer(p, "<i2").astype(np.float32) / 32768
                            for p, r in pezzi if r == rate])
        return x, rate


class _Uscita:
    def __init__(self, casse, samplerate):
        self.casse, self.samplerate, self.latency = casse, samplerate, 0.05

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        pass

    def write(self, data):
        a = time.monotonic()
        data = bytes(data)
        dur = len(data) / 2 / self.samplerate
        voce = bool(np.any(np.abs(np.frombuffer(data, "<i2")) > 30))
        time.sleep(dur)
        with self.casse.lock:
            self.casse.scritture.append((a, a + dur, data if voce else b"", self.samplerate,
                                         voce))
            # Il silenzio dei keepalive non serve: si tengono solo le scritture con voce
            if len(self.casse.scritture) > 200000:
                del self.casse.scritture[:100000]


class SatelliteE2E:
    def __init__(self, stanza: str, url: str, token: str, cartella: Path, wake_model: str,
                 esecutore=None, log=None):
        from calliope.config import Config
        from calliope.satellite.client import Satellite
        self.stanza = stanza
        cartella.mkdir(parents=True, exist_ok=True)
        cred = cartella / "satellite.json"
        cred.write_text(json.dumps({"token": token}), encoding="utf-8")
        cfg = Config()
        cfg.config_dir = str(cartella)
        cfg.memory_db = str(cartella / "memoria.db")
        cfg.wake_model = wake_model
        cfg.input_device = cfg.output_device = None
        cfg.satellite_schermo = "no"
        cfg.satellite_esecutore = esecutore is not None
        cfg.satellite_credenziali = str(cred)
        cfg.satellite_server = url
        cfg.satellite_nome = stanza
        cfg.satellite_inoltro = None
        self.scena = Scena(seme=len(stanza))
        self.casse = Casse()
        self.eventi: list[tuple[float, str, object]] = []
        self._cond = threading.Condition()
        self.log_righe: list[str] = []
        self.sat = Satellite(cfg, sorgente=lambda **kw: MicFinto(self.scena, **kw),
                             apri_uscita=self.casse.flusso, log=self.log_righe.append,
                             esecutore=esecutore if esecutore is not None else False)
        self._aggancia()
        self.thread = threading.Thread(target=self.sat.esegui, daemon=True,
                                       name=f"sat-{stanza}")

    def _evento(self, tipo, dati=None):
        with self._cond:
            self.eventi.append((time.monotonic(), tipo, dati))
            self._cond.notify_all()

    def _aggancia(self):
        p, s = self.sat.player, self.sat
        frase0, fine0, suona0 = p.frase, p.fine_turno, s._suona

        def frase(turno, ident, testo, rate, totale):
            self._evento("frase", testo)
            return frase0(turno, ident, testo, rate, totale)

        def fine_turno(ident):
            self._evento("fine_turno", ident)
            return fine0(ident)

        def suona(tipo):
            self._evento("suono", tipo)
            return suona0(tipo)
        p.frase, p.fine_turno, s._suona = frase, fine_turno, suona

    def avvia(self, timeout: float = 120.0) -> bool:
        self.thread.start()
        return self.sat.collegato.wait(timeout)

    def ferma(self):
        try:
            self.sat.ferma()
        except Exception:  # noqa: BLE001
            pass

    # ── stato ──
    def zitta(self, s: float = 1.2) -> bool:
        p = self.sat.player
        return (not p.in_corso and p.q.empty()
                and time.monotonic() - self.casse.ultima_voce() > s)

    def aspetta_zitta(self, timeout: float = 120.0, s: float = 1.2) -> bool:
        fine = time.monotonic() + timeout
        while time.monotonic() < fine:
            if self.zitta(s):
                return True
            time.sleep(0.1)
        return False

    def eventi_dopo(self, t: float, tipo: str | None = None) -> list:
        with self._cond:
            return [(x, k, d) for x, k, d in self.eventi if x > t and (tipo is None or k == tipo)]

    # ── parlare ──
    def di(self, audio: np.ndarray, attesa: float = 4.0) -> tuple[float | None, bool]:
        """Dice una frase (16 kHz) al microfono finto. (istante della fine del parlato,
        frase mandata al server?)."""
        prima = self.sat.frasi_inviate
        ev = self.scena.di(audio)
        durata = len(audio) / RATE + 1.0
        if not ev.wait(durata + 10):
            return None, False
        fine = time.monotonic() + attesa
        while time.monotonic() < fine:
            if self.sat.frasi_inviate > prima:
                return ev.t, True
            time.sleep(0.05)
        return ev.t, False

    def risposta(self, t: float, timeout: float = 60.0, quiete: float = 1.5) -> dict:
        """Ciò che Calliope ha detto dopo `t`: frasi (testo), prima voce, fine del turno."""
        fine = time.monotonic() + timeout
        fatto = None
        while time.monotonic() < fine:
            fini = self.eventi_dopo(t, "fine_turno")
            if fini and self.zitta(quiete):
                fatto = fini[-1][0]
                break
            time.sleep(0.1)
        ev = self.eventi_dopo(t, "frase")
        frasi = [d for _, _, d in ev]
        # La prima voce di una frase del server (non i suoni d'inizio e fine ascolto, che il
        # satellite suona da sé)
        prima = self.casse.prima_voce_dopo(ev[0][0]) if ev else None
        return {"frasi": frasi, "testo": " ".join(x for x in frasi if x),
                "prima_voce": prima, "fine": fatto,
                "fine_audio": self.casse.ultima_voce(),
                "suoni": [d for _, _, d in self.eventi_dopo(t, "suono")]}
