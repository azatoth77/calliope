"""
Un satellite FINTO a livello di protocollo (06/10, prove delle corsie): si collega al server
dei satelliti di una Calliope vera con un token, e «dice» una frase mandando il suo audio
quando il server ascolta, come farebbe un satellite dopo la wake word. Niente microfono, VAD
né wake word: serve a far parlare più satelliti insieme, a comando, e a misurare quando
arriva la voce di Calliope. Tiene le frasi ricevute (testo e istante) e risponde a
«fine_turno», «sveglia» e «fine_veglia» come il satellite vero (calliope/satellite/client.py).
Come il vero (dal 10/10, quarto giro) scarta le frasi di un turno che non supera l'ultimo
fermato (`Riproduttore._scartata`: al turno 0, o dopo un «ferma» di quel turno): non finiscono
in `frasi` né tra le dette, ma in `scartate`. Prima le teneva tutte, e «ricominciamo» al turno
0, muto sulla DGX, qui si sentiva.

    s = SatelliteFinto("ws://127.0.0.1:8771", token, "studio")
    s.avvia()
    t = s.di(pcm_int16)               # aspetta che il server ascolti, manda la frase
    s.frasi_dopo(t)                   # [(istante, testo)] delle frasi di Calliope dopo t
"""
import json
import sys
import threading
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

from calliope.satellite import protocollo as P  # noqa: E402


class SatelliteFinto:
    def __init__(self, url: str, token: str, nome: str = "finto", ssl=None):
        self.url, self.token, self.nome, self.ssl = url.rstrip("/"), token, nome, ssl
        self.ws = None
        self._cond = threading.Condition()
        self._lid = None                     # «ascolta» in corso (id), None se non ascolta
        self._dette: list[str] = []          # frasi del turno, per «turno_finito»
        self.frasi: list[tuple[float, str]] = []      # (monotonic, testo) ricevute e dette
        self.scartate: list[tuple[int, str]] = []     # (turno, testo) scartate come il vero
        self.scarta_fino = 0                 # come Riproduttore.scarta_fino
        self.voce: list[float] = []          # istanti dei pezzi di voce ricevuti
        self.turni_finiti: list[float] = []
        self.ascolti = 0
        self.chiuso = threading.Event()
        self._invio = threading.Lock()

    # ── connessione ──
    def avvia(self, timeout: float = 30.0) -> "SatelliteFinto":
        from websockets.sync.client import connect
        fine = time.monotonic() + timeout
        while True:
            try:
                self.ws = connect(self.url + P.PERCORSO_AUDIO, ssl=self.ssl, compression=None,
                                  max_size=2 ** 22, open_timeout=5)
                break
            except Exception:  # noqa: BLE001 — Calliope non è ancora pronta
                if time.monotonic() > fine:
                    raise
                time.sleep(0.3)
        self.ws.send(P.testo(tipo="ciao", versione=1, token=self.token, primo=False,
                             nome=self.nome))
        while True:
            m = self.ws.recv(timeout=max(1.0, fine - time.monotonic()))
            if isinstance(m, str) and P.leggi(m).get("tipo") == "benvenuto":
                break
        self.ws.send(P.testo(tipo="pronto", eco=0.0))
        threading.Thread(target=self._leggi, daemon=True, name=f"finto-{self.nome}").start()
        return self

    def chiudi(self):
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001
            pass

    def _manda(self, **campi):
        with self._invio:
            self.ws.send(P.testo(**campi))

    def _leggi(self):
        try:
            for m in self.ws:
                ora = time.monotonic()
                if isinstance(m, (bytes, bytearray)):
                    if m[:1] == P.VOCE:
                        with self._cond:
                            self.voce.append(ora)
                    continue
                d = P.leggi(m)
                t = d.get("tipo")
                if t == "ascolta":
                    with self._cond:
                        self._lid = d.get("id")
                        self.ascolti += 1
                        self._cond.notify_all()
                elif t == "sveglia":
                    with self._cond:
                        mio = d.get("id") == self._lid
                        if mio:
                            self._lid = None
                    if mio:
                        self._manda(tipo="nessuna_frase", id=d.get("id"))
                elif t == "frase":
                    with self._cond:
                        turno = int(d.get("turno") or 0)
                        if turno <= self.scarta_fino:
                            self.scartate.append((turno, str(d.get("testo") or "")))
                        else:
                            self.frasi.append((ora, str(d.get("testo") or "")))
                            self._dette.append(str(d.get("testo") or ""))
                        self._cond.notify_all()
                elif t == "ferma":
                    with self._cond:
                        self.scarta_fino = max(self.scarta_fino, int(d.get("turno") or 0))
                elif t == "fine_turno":
                    with self._cond:
                        dette, self._dette = self._dette, []
                        self.turni_finiti.append(ora)
                        self._cond.notify_all()
                    self._manda(tipo="turno_finito", id=d.get("id"), dette=dette)
                elif t == "fine_veglia":
                    self._manda(tipo="veglia_finita", id=d.get("id"))
        except Exception:  # noqa: BLE001 — connessione chiusa
            pass
        finally:
            self.chiuso.set()
            with self._cond:
                self._cond.notify_all()

    # ── parlare ──
    def ascolta(self, timeout: float = 15.0) -> bool:
        """Aspetta che il server ascolti (un «ascolta» non ancora usato)."""
        fine = time.monotonic() + timeout
        with self._cond:
            while self._lid is None and not self.chiuso.is_set():
                resto = fine - time.monotonic()
                if resto <= 0:
                    return False
                self._cond.wait(resto)
            return self._lid is not None

    def di(self, pcm: bytes, rate: int = 16000, timeout: float = 15.0) -> float | None:
        """Manda una frase (PCM int16 a 16 kHz) come dopo la wake word; l'istante della fine
        (monotonic), o None se il server non ascolta."""
        if not self.ascolta(timeout):
            return None
        with self._cond:
            lid, self._lid = self._lid, None
        dur = len(pcm) / 2 / rate
        passo = int(rate * 0.1) * 2
        with self._invio:
            for i in range(0, len(pcm), passo):
                self.ws.send(P.binario(P.AUDIO, lid, pcm[i:i + passo]))
            self.ws.send(P.testo(tipo="frase_finita", id=lid, fa_s=round(dur, 3), woke=True,
                                 wake_score=0.95))
        return time.monotonic()

    def frasi_dopo(self, t: float) -> list[tuple[float, str]]:
        with self._cond:
            return [(x, s) for x, s in self.frasi if x > t]

    def aspetta_frase(self, t: float, timeout: float = 20.0, contiene: str | None = None):
        """La prima frase di Calliope arrivata dopo `t` (che contiene `contiene`, se dato):
        (istante, testo) o None."""
        fine = time.monotonic() + timeout
        with self._cond:
            while True:
                for x, s in self.frasi:
                    if x > t and (contiene is None or contiene.lower() in s.lower()):
                        return x, s
                resto = fine - time.monotonic()
                if resto <= 0 or self.chiuso.is_set():
                    return None
                self._cond.wait(min(resto, 0.5))

    def aspetta_fine_turno(self, t: float, timeout: float = 30.0) -> bool:
        fine = time.monotonic() + timeout
        with self._cond:
            while not any(x > t for x in self.turni_finiti):
                resto = fine - time.monotonic()
                if resto <= 0 or self.chiuso.is_set():
                    return False
                self._cond.wait(min(resto, 0.5))
            return True


def pcm_di(audio_float) -> bytes:
    """Float32 in [-1, 1] → PCM int16 (come P.a_pcm)."""
    return P.a_pcm(audio_float)


def json_testo(m) -> dict:
    return json.loads(m) if isinstance(m, str) else {}
