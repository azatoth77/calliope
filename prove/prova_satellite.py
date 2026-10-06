import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco dei satelliti (calliope/satellite/, docs/ricerche/2026-10-02-satellite.md).

Parte 1, server dei satelliti nel processo (niente Calliope):
- protocollo (audio binario, PCM, impronte), archivio separato da quello degli schermi;
- rifiuto senza token, con un token sbagliato e da un browser (Origin);
- abbinamento a codice con un satellite vero: codice, `--abbina`, token salvato;
- TLS con un certificato fatto da openssl (se c'è): impronta vista all'abbinamento, connessione
  cifrata, e con un'impronta diversa il token non parte; revoca che chiude la connessione;
  una seconda connessione dello stesso satellite sostituisce la prima.

Parte 2, Calliope vera (`python -m calliope` in un sottoprocesso, audio_modo: satellite) con
un Ollama finto e un server di trascrizione finto, e un satellite vero in questo processo
con un microfono finto (frasi sintetizzate da Piper con un'altra voce) e casse finte (scritture
in tempo reale):
- saluto alla prima connessione, con la misura dell'eco;
- da addormentata una frase senza nome non lascia il satellite (0 byte, nessuna trascrizione);
- «Calliope, che ore sono?»: la frase intera (con il nome) arriva a Whisper, la risposta torna a
  pezzi e si riproduce; tempo dalla fine della frase alla prima voce;
- barge-in: «Calliope, basta» mentre racconta una storia ferma la riproduzione entro un blocco
  da 100 ms, senza aspettare il server; poi niente più voce di quel turno;
- caduta del server: il satellite si ricollega da solo quando Calliope riparte (senza saluto);
- latenza aggiunta da una rete tipo VPN (proxy TCP con 25 ms per verso, giro di 50 ms);
- CPU del satellite in ascolto e banda.

Servono le voci di Piper (voices/) e i modelli della wake word (wakeword/modelli/), fuori da
git: se mancano la parte 2 si salta (esce con 0). Tutto in una cartella temporanea.
"""

import collections
import io
import json
import re
import socket
import statistics
import subprocess
import tempfile
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

RADICE = Path(__file__).resolve().parent.parent
errori = 0


def ok(msg, cond, extra=""):
    global errori
    print(("ok  " if cond else "ERR ") + msg + (f"  ({extra})" if extra else ""), flush=True)
    if not cond:
        errori += 1


def porta_libera() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def attacco(x: np.ndarray, soglia: float = 0.01) -> float | None:
    """Secondi prima del primo tratto di 10 ms con energia di parlato (None: niente)."""
    n = 160
    for k in range(0, max(0, len(x) - n), n):
        if np.sqrt(np.mean(x[k:k + n] ** 2)) > soglia:
            return round(k / 16000, 2)
    return None


def aspetta(cond, timeout=10.0, passo=0.02) -> bool:
    fine = time.monotonic() + timeout
    while time.monotonic() < fine:
        if cond():
            return True
        time.sleep(passo)
    return bool(cond())


# ───────────────────────── microfono e casse finti ─────────────────────────
class Scena:
    """Ciò che sente il microfono finto: un filo di rumore e le frasi messe in coda."""

    def __init__(self):
        self._q = collections.deque()
        self._lock = threading.Lock()
        self._buf = np.zeros(0, np.float32)
        self._evento = None
        self.rng = np.random.default_rng(1)

    def di(self, audio: np.ndarray) -> threading.Event:
        """Mette una frase in coda; l'evento si accende quando l'ultimo campione è passato
        (l'istante sta in `evento.t`)."""
        ev = threading.Event()
        with self._lock:
            self._q.append((audio.astype(np.float32), ev))
        return ev

    def frame(self, n=512) -> np.ndarray:
        with self._lock:
            if len(self._buf) == 0 and self._q:
                self._buf, self._evento = self._q.popleft()
            if len(self._buf):
                out, self._buf = self._buf[:n], self._buf[n:]
                if len(out) < n:
                    out = np.concatenate([out, np.zeros(n - len(out), np.float32)])
                if len(self._buf) == 0 and self._evento is not None:
                    self._evento.t = time.monotonic()
                    self._evento.set()
                    self._evento = None
                return out + self.rng.normal(0, 3e-4, n).astype(np.float32)
        return self.rng.normal(0, 3e-4, n).astype(np.float32)


class MicFinto:
    """Come sd.InputStream: un thread chiama la callback ogni 32 ms con 512 campioni."""

    def __init__(self, scena, samplerate, channels, dtype, blocksize, device, callback):
        self.scena, self.cb, self.n = scena, callback, blocksize
        self._stop = threading.Event()

    def start(self):
        def gira():
            t0, i = time.monotonic(), 0
            while not self._stop.is_set():
                self.cb(self.scena.frame(self.n).reshape(-1, 1), self.n, None, None)
                i += 1
                attesa = t0 + i * self.n / 16000 - time.monotonic()
                if attesa > 0:
                    time.sleep(attesa)
        threading.Thread(target=gira, daemon=True).start()

    def abort(self):
        self._stop.set()

    close = abort


class Casse:
    """Il registro di ciò che le casse finte hanno «suonato»: (inizio, fine, voce?)."""

    def __init__(self):
        self.scritture = []
        self._lock = threading.Lock()

    def voce_dopo(self, t: float) -> float | None:
        """L'inizio della prima scrittura non silenziosa dopo t."""
        with self._lock:
            for a, b, v in self.scritture:
                if v and a >= t:
                    return a
        return None

    def secondi_di_voce(self, da: float, a: float = float("inf")) -> float:
        with self._lock:
            return sum(b - x for x, b, v in self.scritture if v and x >= da and x < a)

    def flusso(self, samplerate, channels, dtype, device):
        return UscitaFinta(self, samplerate)


class UscitaFinta:
    """Come sd.RawOutputStream: ogni scrittura dura quanto l'audio che contiene."""

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
        dur = len(data) / 2 / self.samplerate
        voce = bool(np.any(np.frombuffer(bytes(data), dtype="<i2") != 0))
        time.sleep(dur)
        with self.casse._lock:
            self.casse.scritture.append((a, a + dur, voce))


# ───────────────────────── voce di chi parla ─────────────────────────
def sintetizza(testi: list[str]) -> dict[str, np.ndarray] | None:
    """Le frasi di «chi parla», con una voce diversa da quella di Calliope, a 16 kHz."""
    path = RADICE / "voices" / "it_IT-riccardo-x_low.onnx"
    if not path.is_file():
        return None
    from piper import PiperVoice
    voice = PiperVoice.load(str(path))
    out = {}
    for t in testi:
        # Tre pronunce diverse (Piper sceglie a caso durate e timbro): la prima è la frase,
        # le altre servono quando la wake word non scatta e la frase si ripete. Ripetere la
        # stessa identica pronuncia falliva tutte e 4 le volte (03/10, 1 giro su ~10 con
        # più prove insieme): una persona la ridirebbe in un altro modo
        VARIANTI[t] = []
        for _ in range(3):
            pcm = b"".join(ch.audio_int16_bytes for ch in voice.synthesize(t))
            x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
            rate = voice.config.sample_rate
            n = int(len(x) * 16000 / rate)
            VARIANTI[t].append(np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)),
                                         x).astype(np.float32))
        out[t] = VARIANTI[t][0]
    return out


# ───────────────────────── server finti ─────────────────────────
class STTFinto:
    """Server di trascrizione con l'API di OpenAI: risponde `risposta` (la prima richiesta è
    il riscaldamento di Calliope: testo vuoto) e tiene la durata di ogni audio ricevuto."""

    def __init__(self):
        self.risposta = ""
        self.durate = []
        self.ultimo = np.zeros(0, np.int16)          # l'ultimo audio ricevuto
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                i = corpo.find(b"RIFF")
                dur = 0.0
                if i >= 0:
                    with wave.open(io.BytesIO(corpo[i:]), "rb") as w:
                        dur = w.getnframes() / w.getframerate()
                srv.durate.append(dur)
                if i >= 0:
                    with wave.open(io.BytesIO(corpo[i:]), "rb") as w:
                        srv.ultimo = np.frombuffer(w.readframes(w.getnframes()), "<i2")
                testo = srv.risposta if len(srv.durate) > 1 else ""
                data = json.dumps({"text": testo}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.porta = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


STORIA = ("C'era una volta una musa che amava le parole. Ogni mattina saliva sul monte "
          "Elicona a guardare il mare. Un giorno incontrò un pastore che non sapeva cantare. "
          "Gli insegnò una canzone lunga e lenta, piena di nomi di stelle. Il pastore la cantò "
          "per tutta la vita, e i suoi figli la cantano ancora oggi.")


def risposta_llm(body):
    utente = next((m.get("content") or "" for m in reversed(body.get("messages") or [])
                   if m.get("role") == "user"), "").lower()
    if "storia" in utente:
        return {"content": STORIA}
    # «che ore sono» e non la sottostringa «ore» (03/10, analisi di robustezza): «per
    # favore», «ancora», «colore» ricevevano l'ora, e una prova poteva passare per il motivo
    # sbagliato
    if re.search(r"\bche ore\b|\bore sono\b|\bche ora\b", utente):
        return {"content": "Sono le dieci e un quarto. Ti serve altro?"}
    return {"content": "Va bene."}


class Proxy:
    """Un proxy TCP che ritarda ogni pezzo di `ritardo` secondi per verso (una VPN finta)."""

    def __init__(self, porta_dest: int, ritardo: float):
        self.dest, self.ritardo = porta_dest, ritardo
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.porta = self.sock.getsockname()[1]
        self.conn = []
        threading.Thread(target=self._accetta, daemon=True).start()

    def _accetta(self):
        while True:
            try:
                a, _ = self.sock.accept()
            except OSError:
                return
            b = socket.create_connection(("127.0.0.1", self.dest))
            for s in (a, b):
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.conn += [a, b]
            for x, y in ((a, b), (b, a)):
                q = collections.deque()
                cond = threading.Condition()
                threading.Thread(target=self._leggi, args=(x, q, cond), daemon=True).start()
                threading.Thread(target=self._scrivi, args=(y, q, cond), daemon=True).start()

    def _leggi(self, s, q, cond):
        while True:
            try:
                d = s.recv(65536)
            except OSError:
                d = b""
            with cond:
                q.append((time.monotonic() + self.ritardo, d))
                cond.notify()
            if not d:
                return

    def _scrivi(self, s, q, cond):
        while True:
            with cond:
                while not q:
                    cond.wait()
                t, d = q.popleft()
            attesa = t - time.monotonic()
            if attesa > 0:
                time.sleep(attesa)
            try:
                if not d:
                    s.shutdown(socket.SHUT_WR)
                    return
                s.sendall(d)
            except OSError:
                return

    def chiudi(self):
        for s in [self.sock, *self.conn]:
            try:
                s.close()
            except OSError:
                pass


# ───────────────────────── parte 1 ─────────────────────────
def cfg_prova(tmp: Path, **campi):
    from calliope.config import Config
    cfg = Config()
    cfg.config_dir = str(tmp)
    cfg.memory_db = str(tmp / "memoria.db")
    cfg.satellite_porta = 0
    cfg.wake_model = str(RADICE / "wakeword" / "modelli" / "calliope.onnx")
    cfg.input_device = cfg.output_device = None
    cfg.satellite_schermo = "no"
    # Niente esecutore del PC vero nelle prove (su Windows leggerebbe volume e schermo):
    # quello finto è in prova_esecutore.py
    cfg.satellite_esecutore = False
    cfg.satellite_credenziali = str(tmp / "satellite.json")
    for k, v in campi.items():
        setattr(cfg, k, v)
    return cfg


def parte_protocollo(tmp: Path):
    from calliope.satellite import protocollo as P
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.schermi.archivio import ArchivioSchermi
    t, i, pcm = P.apri_binario(P.binario(P.AUDIO, 7, b"\x01\x02"))
    ok("binario: tipo, id e PCM tornano uguali", (t, i, pcm) == (P.AUDIO, 7, b"\x01\x02"))
    x = np.array([0.0, 0.5, -0.5, 1.2], np.float32)
    y = P.da_pcm(P.a_pcm([x]))
    ok("PCM int16: andata e ritorno (con il taglio a ±1)",
       np.allclose(y, np.clip(x, -1, 1), atol=1e-4))
    ok("impronte normalizzate", P.norm_impronta("sha256 Fingerprint=ab:CD:01") == "ABCD01")
    db = str(tmp / "arch.db")
    sat, scr = ArchivioSatelliti(db), ArchivioSchermi(db)
    s, tok = sat.crea_con_token("studio")
    ok("archivio dei satelliti separato da quello degli schermi",
       sat.per_token(tok) is not None and scr.per_token(tok) is None and not scr.elenco())
    req = sat.nuova_richiesta()
    res = sat.abbina(req["codice"], "allo studio")
    ok("abbinamento a codice: la richiesta diventa il token, la stanza si normalizza",
       res["ok"] and sat.per_token(req["richiesta"])["stanza"] == "studio")
    raw = Path(db).read_bytes()
    ok("sul disco solo l'hash dei token", tok.encode() not in raw
       and req["richiesta"].encode() not in raw)
    sat.close()
    scr.close()


def parte_server(tmp: Path, voce_ok: bool):
    from websockets.exceptions import ConnectionClosed, InvalidStatus
    from websockets.sync.client import connect
    from calliope.satellite import protocollo as P
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.client import ImprontaDiversa, Satellite
    from calliope.satellite.server import ServerSatelliti

    cfg = cfg_prova(tmp)
    arch = ArchivioSatelliti(cfg.memory_db)
    srv = ServerSatelliti(cfg, arch, log=lambda m: None).avvia()
    srv.avviato.set()
    url = f"ws://127.0.0.1:{srv.port}"

    # Senza token, con un token sbagliato, da un browser
    with connect(url + P.PERCORSO_AUDIO, compression=None) as ws:
        ws.send(P.testo(tipo="ciao", versione=P.VERSIONE, token="sbagliato"))
        try:
            ws.recv(timeout=3)
            codice = None
        except ConnectionClosed as e:
            codice = e.rcvd.code if e.rcvd else None
    ok("token sbagliato: chiuso con 4401, nessun dettaglio", codice == P.CHIUSO_TOKEN)
    with connect(url + P.PERCORSO_AUDIO, compression=None) as ws:
        ws.send(P.testo(tipo="ciao", versione=P.VERSIONE))
        try:
            ws.recv(timeout=3)
            codice = None
        except ConnectionClosed as e:
            codice = e.rcvd.code if e.rcvd else None
    ok("senza token: chiuso con 4401", codice == P.CHIUSO_TOKEN)
    try:
        connect(url + P.PERCORSO_AUDIO, additional_headers={"Origin": "http://esempio.it"},
                open_timeout=3).close()
        rifiutato = False
    except InvalidStatus as e:
        rifiutato = e.response.status_code == 403
    ok("una pagina web (con Origin) non apre il WebSocket: 403", rifiutato)
    ok("nessun satellite attivo dopo i rifiuti", srv.attivo is None)

    if not voce_ok:
        srv.ferma()
        arch.close()
        return
    # Abbinamento con un satellite vero (microfono e casse finti)
    scena, casse = Scena(), Casse()
    cfg_s = cfg_prova(tmp, satellite_server=url)
    sat = Satellite(cfg_s, sorgente=lambda **kw: MicFinto(scena, **kw),
                    apri_uscita=casse.flusso, log=lambda m: None)
    t = threading.Thread(target=sat.esegui, daemon=True)
    t.start()
    ok("il satellite nuovo mostra un codice di 6 cifre",
       aspetta(lambda: sat.codice is not None, 5) and len(sat.codice) == 6)
    from calliope.satellite.__main__ import gestione
    righe = []
    rc = gestione(["--abbina", sat.codice, "--stanza", "studio"], out=righe.append, cfg=cfg)
    ok("--abbina dal terminale del server", rc == 0 and "studio" in righe[0], righe[0])
    ok("il satellite riceve il token e si collega",
       aspetta(lambda: sat.collegato.is_set(), 8)
       and json.loads(Path(cfg_s.satellite_credenziali).read_text())["token"])
    ok("stanza del satellite attivo", srv.stanza() == "studio")
    # Seconda connessione con lo stesso token: sostituisce la prima
    token = sat.cred["token"]
    vecchio = srv.attivo
    with connect(url + P.PERCORSO_AUDIO, compression=None) as ws:
        ws.send(P.testo(tipo="ciao", versione=P.VERSIONE, token=token, primo=False))
        m = P.leggi(ws.recv(timeout=3))
        ws.send(P.testo(tipo="pronto", eco=None))
        ok("seconda connessione: benvenuto e sostituzione della prima",
           m.get("tipo") == "benvenuto" and aspetta(lambda: srv.attivo is not vecchio, 3))
    ok("il satellite vero si ricollega dopo essere stato sostituito",
       aspetta(lambda: sat.connessioni >= 2 and srv.attivo_pronto() is not None, 10))
    # Revoca: la connessione si chiude e il satellite torna a chiedere un codice
    srv.CONTROLLO_REVOCA_S = 0.3
    sat.codice = None
    gestione(["--revoca", "studio"], out=righe.append, cfg=cfg)
    ok("revoca: connessione chiusa, il satellite chiede un abbinamento nuovo",
       aspetta(lambda: sat.codice is not None, 10) and not sat.cred.get("token"))
    sat.ferma()
    srv.ferma()
    arch.close()

    # TLS: certificato con openssl, impronta fissata all'abbinamento
    from calliope.satellite.__main__ import certificato, _openssl
    if _openssl() is None:
        print("SALTATA IN PARTE: openssl non c'è: salto la parte del TLS")
        return
    tls = tmp / "tls"
    tls.mkdir()
    cfg_t = cfg_prova(tls)
    out = []
    ok("--certificato crea certificato e chiave", certificato(cfg_t, out=out.append) == 0
       and (tls / "satellite.crt").is_file(), out[-1] if out else "")
    arch = ArchivioSatelliti(cfg_t.memory_db)
    srv = ServerSatelliti(cfg_t, arch, log=lambda m: None).avvia()
    srv.avviato.set()
    ok("con il certificato il server parla TLS", srv.schema == "wss" and srv.impronta)
    cfg_s = cfg_prova(tls, satellite_server=f"wss://127.0.0.1:{srv.port}")
    log_t = []
    sat = Satellite(cfg_s, sorgente=lambda **kw: MicFinto(scena, **kw),
                    apri_uscita=casse.flusso, log=log_t.append)
    threading.Thread(target=sat.esegui, daemon=True).start()
    ok("TLS: il satellite chiede il codice sulla connessione cifrata",
       aspetta(lambda: sat.codice is not None, 15),
       "" if sat.codice else " / ".join(log_t[-3:]))
    res = arch.abbina(sat.codice or "", "cucina")
    collegato = aspetta(lambda: sat.collegato.is_set(), 15)
    ok("TLS: abbinato e collegato, impronta salvata", res["ok"] and collegato
       and P.norm_impronta(sat.cred.get("impronta")) == P.norm_impronta(srv.impronta),
       "" if collegato else f"{res['esito']}; " + " / ".join(log_t[-4:]))
    sat.ferma()
    aspetta(lambda: srv.attivo is None, 3)
    visti = srv.collegati_in_tutto
    cfg_s.satellite_impronta = "00:" * 31 + "00"
    sat2 = Satellite(cfg_s, sorgente=lambda **kw: MicFinto(scena, **kw),
                     apri_uscita=casse.flusso, log=lambda m: None)
    try:
        sat2._connetti(P.PERCORSO_AUDIO)
        rifiutato = False
    except ImprontaDiversa:
        rifiutato = True
    time.sleep(0.3)
    ok("impronta diversa: il satellite si ferma prima di mandare il token",
       rifiutato and srv.collegati_in_tutto == visti)
    # websockets legge da un thread suo e scrive da altri: con l'SSLSocket normale ogni
    # tanto la richiesta di apertura non partiva (9 su 300, 03/10) e il passo qui sopra
    # finiva in «timed out while waiting for handshake response». Con calliope/tls_sicuro.py
    # nessuna apertura deve restare senza risposta
    cfg_s.satellite_impronta = srv.impronta
    esiti = []

    def apri_chiudi():
        for _ in range(15):
            t0 = time.monotonic()
            try:
                ws, _ = sat2._connetti(P.PERCORSO_ABBINA)
                ws.close()
                esiti.append(time.monotonic() - t0)
            except Exception as e:  # noqa: BLE001
                esiti.append(f"{type(e).__name__}: {e}")
    fili = [threading.Thread(target=apri_chiudi) for _ in range(8)]
    for f in fili:
        f.start()
    for f in fili:
        f.join(60)
    tempi = [x for x in esiti if isinstance(x, float)]
    ok("TLS: 120 aperture (8 in parallelo), nessuna senza risposta",
       len(tempi) == 120, f"{len(tempi)}/120, più lenta {max(tempi, default=0):.2f} s; "
       + "; ".join(sorted({x for x in esiti if isinstance(x, str)}))[:200])
    srv.ferma()
    arch.close()
    tls_sicuro_tempi(tls / "satellite.crt", tls / "satellite.key")


def tls_sicuro_tempi(cert: Path, chiave: Path):
    """SocketTLS rispetta il tempo massimo di settimeout e una lettura ferma finisce quando
    un altro thread chiude il socket (websockets lo fa con shutdown + close)."""
    import ssl
    from calliope.tls_sicuro import SocketTLS, sicuro
    sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sctx.load_cert_chain(str(cert), str(chiave))
    lsock = socket.create_server(("127.0.0.1", 0))
    lato = {}

    def accetta():
        c, _ = lsock.accept()
        lato["s"] = sctx.wrap_socket(c, server_side=True)
    th = threading.Thread(target=accetta, daemon=True)
    th.start()
    cctx = sicuro(ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
    cctx.check_hostname, cctx.verify_mode = False, ssl.CERT_NONE
    c = cctx.wrap_socket(socket.create_connection(lsock.getsockname(), timeout=5))
    th.join(5)
    c.settimeout(0.3)
    t0 = time.monotonic()
    try:
        c.recv(10)
        scaduto = False
    except TimeoutError:
        scaduto = True
    dt = time.monotonic() - t0
    ok("SocketTLS: settimeout vale (TimeoutError dopo 0,3 s)",
       isinstance(c, SocketTLS) and scaduto and 0.25 < dt < 1.5 and c.gettimeout() == 0.3,
       f"{dt:.2f} s")
    c.settimeout(None)
    lato["s"].sendall(b"ciao")
    ok("SocketTLS: i dati arrivano", c.recv(10) == b"ciao")
    letto = []
    t = threading.Thread(target=lambda: letto.append(c.recv(10)), daemon=True)
    t.start()
    time.sleep(0.2)
    t0 = time.monotonic()
    try:
        c.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    c.close()
    t.join(3)
    ok("SocketTLS: una lettura ferma finisce quando un altro thread chiude",
       not t.is_alive(), f"{time.monotonic() - t0:.2f} s")
    lato["s"].close()
    lsock.close()


LEGGERO = r"""
import sys, importlib.abc
BLOCCATI = {"torch", "torchaudio", "faster_whisper", "ctranslate2", "piper", "httpx", "openai",
            "starlette", "uvicorn", "docx", "openpyxl", "fpdf", "pycaw", "comtypes", "win32com"}
class Blocca(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCCATI:
            raise ImportError(f"bloccato: {name}", name=name)
sys.meta_path.insert(0, Blocca())
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1] + "/prove")
import prova_satellite as T
from pathlib import Path
from calliope.satellite.__main__ import main
from calliope.satellite.client import Satellite
cfg = T.cfg_prova(Path(sys.argv[2]))
sat = Satellite(cfg, sorgente=lambda **kw: T.MicFinto(T.Scena(), **kw),
                apri_uscita=T.Casse().flusso, log=lambda m: None)
print("VAD", type(sat.listener.model).__name__)
print("MODULI", sorted({m.split(".")[0] for m in sys.modules}))
"""


def parte_leggera(tmp: Path):
    """Il satellite su un PC senza Calliope completa: con Whisper, Piper, torch, httpx e le
    librerie facoltative bloccate si costruisce lo stesso (e il VAD è quello ONNX)."""
    r = subprocess.run([sys.executable, "-c", LEGGERO, str(RADICE), str(tmp)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ, PYTHONUTF8="1"), timeout=120)
    buono = r.returncode == 0 and "VAD SileroOnnx" in r.stdout
    ok("satellite leggero: parte senza Whisper, Piper, torch, httpx", buono,
       "" if buono else (r.stdout + r.stderr).strip()[-300:])


USCITA = """
import atexit, sys
from concurrent.futures import ThreadPoolExecutor   # importato come in main (embed_pool)
from pathlib import Path
sys.path.insert(0, sys.argv[3])
from calliope.config import Config
from calliope.satellite import protocollo as P
from calliope.satellite.archivio import ArchivioSatelliti
from calliope.satellite.server import ServerSatelliti
from websockets.sync.client import connect
cfg = Config()
cfg.satellite_porta, cfg.memory_db = 0, str(Path(sys.argv[2]) / "uscita.db")
srv = ServerSatelliti(cfg, ArchivioSatelliti(cfg.memory_db), log=lambda m: None).avvia()
srv.avviato.set()
if sys.argv[1] == "atexit":
    atexit.register(srv.ferma)
else:
    srv.ferma_alla_chiusura()
ws = connect(f"ws://127.0.0.1:{srv.port}" + P.PERCORSO_ABBINA, compression=None)
ws.send(P.testo(tipo="abbina", versione=P.VERSIONE, nome="prova"))
print(P.leggi(ws.recv(timeout=5))["tipo"], flush=True)
sys.exit(0)              # una connessione ancora aperta, senza ferma() esplicito
"""


class Muto:
    """Un proxy TCP che a comando smette di inoltrare senza chiudere niente: come una VPN
    che cade (i pacchetti spariscono, nessun FIN né RST)."""

    def __init__(self, porta_dest: int):
        self.dest, self.muto = porta_dest, False
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.porta = self.sock.getsockname()[1]
        self.conn = []
        threading.Thread(target=self._accetta, daemon=True).start()

    def _accetta(self):
        try:
            a, _ = self.sock.accept()
        except OSError:
            return
        b = socket.create_connection(("127.0.0.1", self.dest))
        self.conn += [a, b]
        for x, y in ((a, b), (b, a)):
            threading.Thread(target=self._copia, args=(x, y), daemon=True).start()

    def _copia(self, x, y):
        try:
            while True:
                dati = x.recv(65536)
                if not dati:
                    return
                if not self.muto:
                    y.sendall(dati)
        except OSError:
            pass

    def chiudi(self):
        for s in [self.sock, *self.conn]:
            try:
                s.close()
            except OSError:
                pass


def parte_rete(tmp: Path):
    """VPN spenta (02/10): il keepalive di websockets scriveva «keepalive ping failed» con il
    traceback intero (TimeoutError, ConnectionClosedError 1011). Con il logger di
    protocollo.logger_websockets la caduta di rete non scrive niente; un errore vero sì."""
    import logging
    from websockets.exceptions import ConnectionClosed
    from websockets.sync.client import connect
    from websockets.sync.server import serve
    from calliope.satellite import protocollo as P

    class Raccogli(logging.Handler):
        def __init__(self):
            super().__init__()
            self.righe = []

        def emit(self, record):
            self.righe.append(record.getMessage())

    def caduta(logger) -> tuple[list, object]:
        rac = Raccogli()
        logger.addHandler(rac)
        logger.propagate = False
        chiusa = {}

        def gestisci(ws):
            try:
                for _ in ws:
                    pass
            except ConnectionClosed:
                pass
            chiusa["rcvd"] = ws.protocol.close_rcvd
            chiusa["fine"] = True
        srv = serve(gestisci, "127.0.0.1", 0, ping_interval=0.2, ping_timeout=0.3,
                    close_timeout=0.3, logger=logger)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        muto = Muto(srv.socket.getsockname()[1])
        cli = connect(f"ws://127.0.0.1:{muto.porta}", ping_interval=None, close_timeout=0.3)
        cli.send("ciao")
        time.sleep(0.3)
        muto.muto = True
        aspetta(lambda: chiusa.get("fine"), 5)
        time.sleep(0.3)
        srv.shutdown()
        muto.chiudi()
        try:
            cli.close_socket()
        except Exception:  # noqa: BLE001
            pass
        logger.removeHandler(rac)
        return rac.righe, chiusa

    righe, _ = caduta(logging.getLogger("prova.websockets.senza_filtro"))
    ok("rete muta: senza filtro websockets scrive «keepalive ping failed»",
       any("keepalive ping failed" in r for r in righe), "" if righe else "nessuna riga")
    righe, chiusa = caduta(P.logger_websockets("prova"))
    ok("rete muta: con logger_websockets nessuna riga di websockets", not righe,
       str(righe) if righe else "")
    ok("rete muta: nessun saluto di chiusura ricevuto (→ «scollegato (rete)»)",
       chiusa.get("fine") and chiusa.get("rcvd") is None)
    rac = []
    log = P.logger_websockets("prova")
    h = logging.Handler()
    h.emit = lambda r: rac.append(r.getMessage())
    log.addHandler(h)
    try:
        raise ValueError("difetto vero")
    except ValueError:
        log.error("connection handler failed", exc_info=True)
    log.removeHandler(h)
    ok("un errore vero (non di rete) resta nel log", rac == ["connection handler failed"])


def parte_personale(tmp: Path):
    """Schermo personale del satellite (02/10): il portatile di Dario è suo. Il satellite lo
    chiede (satellite_schermo_personale) ma da solo non vale: lo conferma chi amministra, da
    terminale, all'abbinamento (--personale) o dopo (--modifica). Lo schermo del satellite
    eredita il proprietario e riceve le schede personali di Dario, non quelle di altri."""
    from calliope.satellite.__main__ import gestione
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.client import Satellite
    from calliope.satellite.server import ServerSatelliti
    from calliope.schermi.archivio import ArchivioSchermi
    from calliope.schermi.hub import Mittente, Schermi, destinatari
    from calliope.schermi.schede import PERSONALE

    d = tmp / "personale"
    d.mkdir()
    (d / "speakers.json").write_text(json.dumps([
        {"id": "dario-id", "name": "Dario", "admin": True},
        {"id": "bianca-id", "name": "Bianca"}]), encoding="utf-8")
    cfg = cfg_prova(d)
    righe_log = []
    arch = ArchivioSatelliti(cfg.memory_db)
    srv = ServerSatelliti(cfg, arch, log=righe_log.append)
    srv.CONTROLLO_REVOCA_S = 0.3
    srv.avvia()
    srv.avviato.set()
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    srv.schermi = hub
    url = f"ws://127.0.0.1:{srv.port}"
    pagine = []
    scena, casse = Scena(), Casse()
    cfg_s = cfg_prova(d, satellite_server=url, satellite_schermo="finestra",
                      satellite_schermo_personale="Dario",
                      satellite_credenziali=str(d / "sat.json"))
    sat = Satellite(cfg_s, sorgente=lambda **kw: MicFinto(scena, **kw),
                    apri_uscita=casse.flusso, log=lambda m: None, apri_schermo=pagine.append)
    threading.Thread(target=sat.esegui, daemon=True).start()
    try:
        ok("personale: il satellite mostra il codice", aspetta(lambda: sat.codice, 5))
        ok("personale: il server dice che il satellite chiede uno schermo di Dario",
           any("personale di Dario" in r for r in righe_log), " / ".join(righe_log[-2:]))
        out = []
        rc = gestione(["--abbina", sat.codice, "--stanza", "studio"], out=out.append, cfg=cfg)
        s = arch.trova("studio")[0]
        ok("personale: senza --personale la richiesta del satellite non vale",
           rc == 0 and s["proprietario"] is None
           and any("non l'ho fatto" in r for r in out), " / ".join(out))
        ok("personale: il satellite si collega e ha la sua pagina",
           aspetta(lambda: sat.collegato.is_set() and pagine, 8))
        dario = Mittente("dario-id", "Dario", "amministra", True)
        bianca = Mittente("bianca-id", "Bianca", "familiare", True)
        scheda = {"tipo": "promemoria", "visibilita": PERSONALE}

        def a_chi(m):
            return [x["nome"] for x in destinatari(PERSONALE, m, hub.abbinati(), "studio")[0]]
        ok("personale: schermo della stanza, niente schede personali", a_chi(dario) == [])
        out = []
        rc = gestione(["--modifica", "studio", "--personale", "Dario"], out=out.append, cfg=cfg)
        ok("personale: --modifica rende personale il satellite", rc == 0
           and arch.trova("studio")[0]["proprietario"] == "dario-id", " / ".join(out))
        ok("personale: lo schermo del satellite eredita il proprietario (senza riabbinare)",
           aspetta(lambda: a_chi(dario) != [], 5), str(hub.abbinati()))
        ok("personale: la scheda personale di Dario arriva al suo schermo",
           hub.invia(scheda, dario)["destinatari"] == a_chi(dario) != [])
        ok("personale: quella di Bianca no", a_chi(bianca) == []
           and hub.invia(scheda, bianca)["motivo"] == "personale")
        grigio = Mittente("dario-id", "Dario", "familiare", False)
        ok("personale: zona grigia, niente", hub.invia(scheda, grigio)["motivo"] == "zona_grigia")
        out = []
        gestione(["--modifica", "studio", "--condiviso"], out=out.append, cfg=cfg)
        ok("personale: --condiviso lo riporta della stanza",
           aspetta(lambda: a_chi(dario) == [], 5))
        # Una richiesta del satellite per Bianca, ma chi abbina dice Dario: vale chi abbina
        req = arch.nuova_richiesta(personale_chiesto="Bianca")
        out = []
        gestione(["--abbina", req["codice"], "--stanza", "cucina", "--personale", "Dario"],
                 out=out.append, cfg=cfg)
        c = arch.trova("cucina")[0]
        ok("personale: --personale di chi abbina vince sulla richiesta del satellite",
           c["proprietario"] == "dario-id" and c["nome"] == "cucina di dario", str(c))
        out = []
        rc = gestione(["--modifica", "cucina", "--personale", "Sconosciuto"], out=out.append,
                      cfg=cfg)
        ok("personale: un nome senza voce registrata si rifiuta", rc == 1, " / ".join(out))
    finally:
        sat.ferma()
        srv.ferma()
        arch.close()


def parte_dispositivi(tmp: Path):
    """avvia_satellite.py chiede «C920 MME» e «I52 MME»: senza la webcam il satellite
    ripeteva all'infinito «microfono non disponibile» (02/10). Ora vale il predefinito."""
    from calliope.satellite.__main__ import scegli_dispositivi
    presenti = {"input": {"I52 MME": "Cuffie I52"}, "output": {"I52 MME": "Cuffie I52"}}
    predefiniti = {"input": "Microfono interno", "output": "Altoparlanti"}

    def query(dev=None, kind=None):
        if dev is None:
            return {"name": predefiniti[kind]}
        if dev not in presenti[kind]:
            raise ValueError(f"No {kind} device matching {dev!r}")
        return {"name": presenti[kind][dev]}
    cfg = cfg_prova(tmp, input_device="C920 MME", output_device="I52 MME")
    righe = []
    nomi = scegli_dispositivi(cfg, righe.append, query=query)
    ok("dispositivi: la webcam manca → microfono predefinito, cuffie trovate per nome",
       nomi == {"microfono": "Microfono interno", "uscita": "Cuffie I52"}
       and cfg.input_device is None and cfg.output_device == "I52 MME", " / ".join(righe))
    ok("dispositivi: il messaggio dice quale si usa e perché",
       any("Microfono interno" in r and "C920 MME" in r and "predefinito" in r for r in righe))


def parte_uscita(tmp: Path):
    """Uscita del processo con un satellite collegato (02/10): da atexit `shutdown` di
    websockets dava «cannot schedule new futures after interpreter shutdown»."""
    script = tmp / "uscita.py"
    script.write_text(USCITA, encoding="utf-8")
    for modo in ("chiusura", "atexit"):
        t = time.monotonic()
        r = subprocess.run([sys.executable, "-W", "ignore", str(script), modo, str(tmp),
                            str(RADICE)], capture_output=True, text=True, timeout=60,
                           env={**os.environ, "PYTHONUTF8": "1"})
        dur = time.monotonic() - t
        pulita = (r.returncode == 0 and "codice" in r.stdout and "Traceback" not in r.stderr
                  and "Exception ignored" not in r.stderr)
        ok(f"uscita con un satellite collegato ({modo}): niente errori, {dur:.1f} s",
           pulita and dur < 15, "" if pulita else r.stderr.strip()[-400:])


# ───────────────────────── parte 2 ─────────────────────────
class Calliope:
    """`python -m calliope` vero in un sottoprocesso, con audio_modo: satellite."""

    def __init__(self, tmp: Path, env: dict):
        self.tmp, self.env, self.proc, self.log = tmp, env, None, None

    def avvia(self):
        if self.log:
            self.log.close()
        self.log = open(self.tmp / f"calliope-{int(time.time() * 1000)}.log", "w",
                        encoding="utf-8")
        self.proc = subprocess.Popen([sys.executable, "-u", "-m", "calliope"], cwd=self.tmp,
                                     env=self.env, stdout=self.log, stderr=subprocess.STDOUT)

    def ferma(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(10)
        if self.log:
            self.log.close()

    def testo(self) -> str:
        out = []
        for p in sorted(self.tmp.glob("calliope-*.log")):
            out.append(p.read_text(encoding="utf-8", errors="replace"))
        return "\n".join(out)


def parte_calliope(tmp: Path, frasi: dict):
    sys.path.insert(0, str(RADICE / "prove"))
    from ollama_finto import FakeOllama
    from calliope.config import Config
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.client import Satellite

    ollama = FakeOllama(modelli=(Config().llm_model,))
    ollama.predefinita = risposta_llm
    ollama.avvia()
    stt = STTFinto()
    porta_sat = porta_libera()
    voce = RADICE / "voices" / "it_IT-paola-medium.onnx"
    righe = {
        "audio_modo": "satellite", "satellite_porta": porta_sat,
        "llm_native_url": f"http://127.0.0.1:{ollama.porta}",
        "stt_motore": "server", "stt_url": f"http://127.0.0.1:{stt.porta}/v1",
        "piper_voice": str(voce), "speaker_model": str(RADICE / Config().speaker_model),
        "memory_db": str(tmp / "memoria.db"), "turn_log_dir": str(tmp / "registro"),
        "followup_s": 1.0, "biblioteca_enabled": False, "pc_enabled": False,
        "documenti_enabled": False, "casa_enabled": False, "schermi_enabled": False,
        "agenti_enabled": False, "installa_enabled": False,
    }
    (tmp / "calliope.yaml").write_text(json.dumps(righe), encoding="utf-8")   # JSON è YAML
    # Una persona registrata senza impronta: niente primo avvio (arruolamento)
    (tmp / "speakers.json").write_text(json.dumps([{"name": "Prova", "admin": True}]),
                                       encoding="utf-8")
    arch = ArchivioSatelliti(str(tmp / "memoria.db"))
    _, token = arch.crea_con_token("studio", ruolo="pc")
    arch.close()
    (tmp / "satellite.json").write_text(json.dumps({"token": token}), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("CALLIOPE_")}
    env.update(PYTHONPATH=str(RADICE), PYTHONUTF8="1",
               CALLIOPE_CONFIG=str(tmp / "calliope.yaml"),
               CALLIOPE_CONFIG_LOCALE=str(tmp / "nessun-file-locale.yaml"),
               CALLIOPE_AGENTI_CONFIG=str(tmp / "nessun-file-dgx.yaml"),
               CALLIOPE_PORTA_ISTANZA=str(porta_libera()))
    cal = Calliope(tmp, env)
    cal.avvia()

    scena, casse = Scena(), Casse()
    cfg = cfg_prova(tmp, satellite_server=f"ws://127.0.0.1:{porta_sat}")
    log = []
    sat = Satellite(cfg, sorgente=lambda **kw: MicFinto(scena, **kw), apri_uscita=casse.flusso,
                    log=log.append)
    # Gli istanti in cui il satellite dice al server «turno finito»: la fine vera della
    # risposta. Una pausa di 0,3 s tra due frasi (Piper lento con più prove insieme) non lo è
    sat.turni_finiti = []
    _finito = sat.player.turno_finito

    def finito(ident, dette):
        sat.turni_finiti.append(time.monotonic())
        _finito(ident, dette)
    sat.player.turno_finito = finito
    # Nella traccia anche l'inizio vero di ogni ascolto (dopo l'«ascolta» del server), con
    # quanti frame recenti diventano pre-roll: per capire un attacco perso
    _listen = sat.listener.listen

    def listen(*a, **kw):
        with sat.listener._recent_lock:
            n = len(sat.listener._recent)
        sat.traccia.append((time.monotonic(), "listen", n))
        return _listen(*a, **kw)
    sat.listener.listen = listen
    threading.Thread(target=sat.esegui, daemon=True).start()
    try:
        _scenario(cal, sat, scena, casse, stt, frasi, porta_sat, log)
    finally:
        sat.ferma()
        cal.ferma()
        if errori:
            print("---- uscita di Calliope ----")
            print(cal.testo()[-4000:])
            print("---- satellite ----")
            print("\n".join(log[-30:]))


RIPETUTE = []          # frasi ripetute perché la wake word non è scattata (misura)
VARIANTI: dict[str, list] = {}   # pronunce diverse della stessa frase (sintetizza)
ULTIMA: dict[str, np.ndarray] = {}   # la pronuncia detta l'ultima volta


def _di(sat, scena, frasi, testo, tentativi=4):
    """Dice una frase rivolta a Calliope e aspetta che il satellite la mandi; se la wake word
    non scatta (succede anche con le voci vere: 48 su 52 sulle registrazioni, e qui circa una
    volta su venti con la voce sintetica) la ripete, come farebbe una persona. L'evento della
    fine della frase mandata, o None."""
    for k in range(tentativi):
        prima = sat.frasi_inviate
        varianti = VARIANTI.get(testo) or [frasi[testo]]
        ULTIMA[testo] = varianti[k % len(varianti)]
        fine = scena.di(ULTIMA[testo])
        if not fine.wait(15):
            return None
        if aspetta(lambda: sat.frasi_inviate > prima, 2.5):
            return fine
        RIPETUTE.append(testo)
        print(f"    (wake word non scattata su «{testo}»: la ripeto)", flush=True)
        if os.environ.get("PROVA_DEBUG"):
            print("      traccia:", [(round(t - fine.t, 2), k, i) for t, k, i in
                                   list(sat.traccia)[-8:]],
                  [t.name for t in threading.enumerate()], flush=True)
    return None


def _domanda(sat, scena, casse, stt, frasi, testo, risposta_stt) -> float | None:
    """Dice una frase e restituisce il tempo dalla sua fine alla prima voce di Calliope."""
    stt.risposta = risposta_stt
    fine = _di(sat, scena, frasi, testo)
    if fine is None:
        return None
    if not aspetta(lambda: casse.voce_dopo(fine.t) is not None, 15):
        return None
    return casse.voce_dopo(fine.t) - fine.t


def _scenario(cal, sat, scena, casse, stt, frasi, porta_sat, log):
    ok("Calliope parte e il satellite si collega (saluto e misura dell'eco)",
       aspetta(lambda: sat.collegato.is_set(), 60),
       "" if sat.collegato.is_set() else " / ".join(log[-3:]))
    ok("il saluto si sente sul satellite", casse.secondi_di_voce(0) > 1.0,
       f"{casse.secondi_di_voce(0):.1f} s")
    ok("eco misurata sul saluto (microfono finto: niente eco)",
       sat.eco is not None and sat.eco < 0.05, str(sat.eco))
    aspetta(lambda: "In ascolto" in cal.testo() or "svegliarmi" in cal.testo(), 10)
    time.sleep(0.5)

    # Da addormentata: una frase senza nome non esce dal satellite
    n_stt = len(stt.durate)
    fine = scena.di(frasi["Che tempo fa domani pomeriggio?"])
    fine.wait(15)
    time.sleep(1.2)
    ok("da addormentata: frase senza nome, 0 byte mandati, nessuna trascrizione",
       sat.audio_inviato == 0 and len(stt.durate) == n_stt,
       f"{sat.audio_inviato} byte, {len(stt.durate) - n_stt} trascrizioni")

    # Sveglia con il nome: frase intera a Whisper, risposta che torna in streaming
    n_turni = len(sat.turni_finiti)
    lat = _domanda(sat, scena, casse, stt, frasi, "Calliope, che ore sono?",
                   "Calliope, che ore sono?")
    dur = len(ULTIMA.get("Calliope, che ore sono?", frasi["Calliope, che ore sono?"])) / 16000
    ok("«Calliope, che ore sono?»: la voce di Calliope arriva sul satellite",
       lat is not None, f"{lat:.2f} s dalla fine della frase" if lat else "")
    ok("a Whisper arriva la frase intera, con il nome (e il pre-roll)",
       len(stt.durate) > n_stt and stt.durate[-1] >= dur, f"{stt.durate[-1]:.2f} s audio, "
       f"frase {dur:.2f} s" if len(stt.durate) > n_stt else "")
    inviati = sat.audio_inviato
    ok("audio mandato solo dopo lo scatto: circa la frase (16 kHz × 16 bit)",
       0 < inviati <= (dur + 1.5) * 32000, f"{inviati / 1000:.0f} kB")
    # Qui la voce non è registrata (ospite): dal 03/10 il terminale non stampa né la sua
    # frase né la risposta (analisi di sicurezza S9), ma la risposta c'è
    ok("Calliope ha risposto (nel terminale senza il testo dell'ospite)",
       "[prima frase" in cal.testo() and "Sono le dieci" not in cal.testo()
       and "una frase di un ospite" in cal.testo())
    # La risposta è finita quando il satellite manda «turno finito», non dopo 0,3 s di
    # silenzio: sotto carico la seconda frase («Ti serve altro?») arrivava 2,3 s dopo la
    # prima, la domanda di follow-up cadeva nella pausa e la sentiva solo il barge-in (03/10)
    aspetta(lambda: len(sat.turni_finiti) > n_turni, 15)
    latenze = [lat] if lat else []

    # Domanda breve senza nome subito dopo la risposta (follow-up), 02/10: dalla DGX «che ore
    # sono» diventava «che sono», «Che re sono». L'attacco non si perde tra la fine della voce
    # sul satellite e l'«ascolta» del server: arriva a Whisper con il pre-roll, come in locale
    with casse._lock:
        fine_voce = max((b for a, b, v in casse.scritture if v), default=time.monotonic())
    while time.monotonic() < fine_voce + 0.1:
        time.sleep(0.005)
    stt.risposta = "Che ore sono?"
    n_stt = len(stt.durate)
    f = frasi["Che ore sono?"]
    detta = scena.di(f)
    detta.wait(15)
    arrivata = aspetta(lambda: len(stt.durate) > n_stt, 8)
    x = stt.ultimo.astype(np.float32) / 32768 if arrivata else np.zeros(0, np.float32)
    prima_r, prima_f = attacco(x), attacco(f)
    # Il pre-roll dipende da quando parte l'ascolto sul satellite («listen» nella traccia)
    # rispetto all'inizio della frase (03/10, misurato): partito prima, 0,19–0,27 s; partito
    # dopo, il VAD appena azzerato riconosce il parlato già in corso con qualche frame di
    # ritardo e i 300 ms tenuti scorrono: +0,03 s → 0,18 s, +0,07 → 0,14, +0,14 → 0,04 (la
    # frase da 0,04 s: attacco appena intero). Con la CPU piena (tre prove insieme e 14
    # processi che girano a vuoto) l'attacco si è anche perso (0,0 s). Nell'hook, con altre
    # prove in corso sulla macchina, i 0,15 s di prima fallivano con la frase intera: si
    # controlla l'attacco (tutto il parlato, dal primo campione della frase). Il silenzio
    # prima del parlato basta che ci sia (0,05 s, o quello della frase se è meno): pretendere
    # tutto quello del file era più severo dello scopo e falliva sotto carico (06/10)
    inizio = getattr(detta, "t", fine_voce) - len(f) / 16000
    asc = next((t for t, k, _ in list(sat.traccia) if k == "ascolta" and t > fine_voce - 0.5),
               None)
    quando = (f"«ascolta» {asc - inizio:+.2f} s dall'inizio della frase" if asc
              else "«ascolta» non visto")
    ok("follow-up subito dopo la risposta: a Whisper la frase intera con il pre-roll",
       arrivata and prima_r is not None and prima_f is not None
       and prima_r >= min(prima_f, 0.05)
       and len(x) - prima_r * 16000 >= len(f) - prima_f * 16000,
       f"{prima_r} s prima del parlato, {len(x) / 16000:.2f} s in tutto (frase "
       f"{len(f) / 16000:.2f} s, parlato da {prima_f} s); {quando}; traccia dall'inizio "
       f"della frase: " + ", ".join(f"{t - inizio:+.2f} {k} {i}" for t, k, i in
                                    list(sat.traccia) if t > fine_voce - 2)
       if arrivata else
       "nessuna frase; "
       "traccia dalla fine della voce: " + ", ".join(
           f"{t - fine_voce:+.2f} {k} {i}" for t, k, i in list(sat.traccia)
           if t > fine_voce - 2))
    aspetta(lambda: casse.secondi_di_voce(time.monotonic() - 0.3) == 0, 10)

    # CPU del satellite in ascolto (Calliope sveglia per followup_s, poi addormentata)
    time.sleep(1.5)
    c0, w0 = time.process_time(), time.monotonic()
    time.sleep(2.0)
    cpu = (time.process_time() - c0) / (time.monotonic() - w0) * 100
    print(f"    misura: CPU del processo del satellite in ascolto {cpu:.1f} % di un core "
          f"(VAD, wake word, microfono e casse finti, server finti fermi)")

    # Barge-in mentre racconta una storia
    stt.risposta = "Calliope, raccontami una storia."
    t_storia = time.monotonic()
    fine = _di(sat, scena, frasi, "Calliope, raccontami una storia.")
    ok("la storia comincia", fine is not None
       and aspetta(lambda: casse.voce_dopo(fine.t) is not None, 15),
       "" if fine and casse.voce_dopo(fine.t) else "traccia: " + ", ".join(
           f"{t - t_storia:+.2f} {k} {i}" for t, k, i in list(sat.traccia)[-12:]))
    inizio = (casse.voce_dopo(fine.t) if fine else None) or time.monotonic()
    aspetta(lambda: time.monotonic() > inizio + 1.0, 3)
    stt.risposta = "Calliope, basta."
    fermata = False
    for k in range(3):
        varianti = VARIANTI.get("Calliope, basta.") or [frasi["Calliope, basta."]]
        stop = scena.di(varianti[k % len(varianti)])
        stop.wait(10)
        if aspetta(lambda: sat.player.interrotta_a is not None
                   and sat.player.interrotta_a > inizio, 1.5):
            fermata = True
            break
        RIPETUTE.append("Calliope, basta.")
        print("    (wake word non scattata su «Calliope, basta.»: la ripeto)", flush=True)
    ok("barge-in: il satellite si ferma da solo", fermata)
    t_int = sat.player.interrotta_a or time.monotonic()
    time.sleep(1.0)
    coda = max(0.0, sat.player.ultima_scrittura - t_int)
    # Fermo entro un blocco = nessun blocco di voce **cominciato** dopo lo scatto (30 ms di
    # margine: il controllo e la scrittura non sono atomici). La fine dell'ultima scrittura
    # non è il criterio: è il blocco già in corso, che sotto carico (più prove insieme)
    # finiva 118 ms dopo per la sola imprecisione di time.sleep delle casse finte (03/10)
    with casse._lock:
        dopo = [round((x - t_int) * 1000) for x, _, v in casse.scritture if v and x > t_int + 0.03]
    ok("barge-in: riproduzione ferma entro un blocco da 100 ms (nessun blocco nuovo)",
       not dopo, f"ultima scrittura finita {coda * 1000:.0f} ms dopo lo scatto"
       + (f"; blocchi cominciati dopo: {dopo[:5]} ms" if dopo else ""))
    time.sleep(2.0)
    ok("dopo il barge-in nessun'altra frase della storia",
       casse.secondi_di_voce(t_int + 0.15) == 0, f"{casse.secondi_di_voce(t_int + 0.15):.1f} s")
    ok("Calliope registra l'interruzione e resta in ascolto",
       aspetta(lambda: "interruzione: resto in ascolto" in cal.testo(), 5))
    detta = casse.secondi_di_voce(inizio, t_int + 0.15)
    print(f"    misura: storia interrotta dopo {detta:.1f} s di voce")
    time.sleep(1.5)                              # si riaddormenta (followup_s: 1)

    # Caduta del server: il satellite si ricollega quando Calliope riparte
    cal.ferma()
    ok("caduta del server: il satellite se ne accorge",
       aspetta(lambda: not sat.collegato.is_set(), 10))
    voce_prima = casse.secondi_di_voce(0)
    cal.avvia()
    ok("Calliope riparte e il satellite si ricollega da solo",
       aspetta(lambda: sat.collegato.is_set() and sat.connessioni >= 2, 60),
       f"connessioni {sat.connessioni}")
    time.sleep(1.0)
    ok("alla riconnessione niente saluto", casse.secondi_di_voce(0) - voce_prima < 0.2)
    lat = _domanda(sat, scena, casse, stt, frasi, "Calliope, che ore sono?",
                   "Calliope, che ore sono?")
    ok("dopo la riconnessione risponde", lat is not None)
    if lat:
        latenze.append(lat)
    aspetta(lambda: casse.secondi_di_voce(time.monotonic() - 0.3) == 0, 10)
    time.sleep(1.5)

    # Latenza aggiunta da una rete tipo VPN: proxy con 25 ms per verso (giro di 50 ms)
    proxy = Proxy(porta_sat, 0.025)
    sat.cfg.satellite_server = f"ws://127.0.0.1:{proxy.porta}"
    n = sat.connessioni
    sat.ws.close()
    ok("il satellite si ricollega attraverso la «VPN»",
       aspetta(lambda: sat.collegato.is_set() and sat.connessioni > n, 15))
    time.sleep(0.5)
    lat_vpn = []
    for k in range(2):
        if k:
            aspetta(lambda: casse.secondi_di_voce(time.monotonic() - 0.3) == 0, 10)
            time.sleep(1.5)
        lat = _domanda(sat, scena, casse, stt, frasi, "Calliope, che ore sono?",
                       "Calliope, che ore sono?")
        if lat:
            lat_vpn.append(lat)
    ok("con la «VPN» risponde", len(lat_vpn) == 2)
    if latenze and lat_vpn:
        diretta, vpn = statistics.median(latenze), statistics.median(lat_vpn)
        print(f"    misura: dalla fine della frase alla prima voce {diretta:.2f} s in locale, "
              f"{vpn:.2f} s con 50 ms di giro (+{(vpn - diretta) * 1000:.0f} ms); comprende "
              f"la pausa che chiude la frase (silence_ms)")
        # Atteso circa un giro (50 ms); con la macchina carica (tutte le prove insieme) un
        # campione può arrivare a +160 ms: il limite controlla solo che non si aggiungano
        # attese (un ack, un buffer) di qualche decimo
        ok("latenza aggiunta dalla rete: meno di 0,4 s", vpn - diretta < 0.4,
           f"+{(vpn - diretta) * 1000:.0f} ms")
    # «Spegniti» da un satellite (02/10): sulla DGX spegneva il servizio, che systemd non
    # riavvia. Ora addormenta: il processo resta vivo, la regola finisce nel registro
    aspetta(lambda: casse.secondi_di_voce(time.monotonic() - 0.3) == 0, 10)
    time.sleep(1.5)
    lat = _domanda(sat, scena, casse, stt, frasi, "Calliope, spegniti.", "Calliope, spegniti.")
    ok("«Calliope, spegniti.» dal satellite: risponde a voce", lat is not None)
    ok("«spegniti» dal satellite addormenta e il server resta acceso",
       aspetta(lambda: "il server resta acceso" in cal.testo(), 10)
       and (time.sleep(1.0) or cal.proc.poll() is None),
       f"uscita {cal.proc.poll()}" if cal.proc.poll() is not None else "")
    def registro() -> str:
        return "".join(f.read_text(encoding="utf-8")
                       for f in (cal.tmp / "registro").glob("*.jsonl"))
    ok("regola uscita_spegni_satellite nel registro dei turni",
       aspetta(lambda: "uscita_spegni_satellite" in registro(), 5),
       "" if "uscita_spegni_satellite" in registro() else registro()[-300:])
    if RIPETUTE:
        print(f"    nota: {len(RIPETUTE)} frasi ripetute (wake word non scattata)")
    print(f"    misura: banda verso il server {sat.audio_inviato / 1000:.0f} kB di microfono in "
          f"tutto; dal server {sat.ricevuti / 1000:.0f} kB (voce di Calliope compresa)")
    proxy.chiudi()


def main():
    from calliope import capacita
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if not capacita.presente("websockets"):
        print("websockets non c'è: salto la prova dei satelliti")
        return 77           # saltata per intero: il runner la conta a parte (prima 0, «ok»)
    modelli = all((RADICE / "wakeword" / "modelli" / f).is_file()
                  for f in ("calliope.onnx", "melspectrogram.onnx", "embedding_model.onnx"))
    with tempfile.TemporaryDirectory(prefix="calliope-satellite-",
                                     ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        solo = os.environ.get("PROVA_DEBUG")
        if not solo:
            parte_protocollo(tmp)
        frasi = None
        # Anche CAM++: senza, Calliope vera non parte e la prova riprovava per 60 s (06/10)
        from calliope.config import Config
        cam = (RADICE / Config().speaker_model).is_file()
        if modelli and cam and (RADICE / "voices" / "it_IT-paola-medium.onnx").is_file():
            frasi = sintetizza(["Che tempo fa domani pomeriggio?", "Calliope, che ore sono?",
                                "Che ore sono?",
                                "Calliope, raccontami una storia.", "Calliope, basta.",
                                "Calliope, spegniti."])
        if not solo:
            parte_server(tmp, voce_ok=frasi is not None)
            parte_uscita(tmp)
            if frasi is not None:
                parte_personale(tmp)
            parte_dispositivi(tmp)
            parte_rete(tmp)
            if frasi is not None:
                parte_leggera(tmp)
        if frasi is None:
            print("SALTATA IN PARTE: voci di Piper, CAM++ o modelli della wake word assenti, "
                  "niente parte con Calliope vera")
        else:
            e2e = tmp / "e2e"
            e2e.mkdir()
            parte_calliope(e2e, frasi)
    print(f"\n{'Tutto ok' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
