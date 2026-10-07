"""
Il lato server dei satelliti, dentro Calliope (audio_modo: satellite).

- `ServerSatelliti`: il WebSocket (libreria `websockets`, API sincrona: un thread per
  connessione, niente asyncio nel resto di Calliope), con TLS se ascolta in rete;
  abbinamento a codice, token, un satellite attivo alla volta.
- `AscoltoRemoto`: lo stesso contratto di `audio.Listener` (`listen`, `watch_for_name`,
  `started_at`, `woke`, `wake_score`, `on_speech_start`/`on_speech_end`), così il ciclo di
  main.py resta quello di sempre. VAD, wake word e pre-roll girano sul satellite (lo stesso
  codice di Listener): qui arrivano solo le frasi rivolte a Calliope, già a pezzi mentre si
  parla.
- `UscitaRemota`: l'uscita di `tts.Speaker` verso il satellite. Le frasi si sintetizzano
  qui (Piper) e partono a pezzi da 0,2 s; il satellite le riproduce con le attenzioni per
  le cuffie Bluetooth, le ferma da solo al barge-in e dice quali ha detto per intero.

Più satelliti (03/10, con il telefono): possono essere collegati insieme, ma uno solo è
**attivo** (ascolta e parla): il primo che si collega, finché non se ne va o finché un altro
non lo **prende** (`prendi`: il telefono quando si tocca «Parla» o si accende il microfono);
`lascia` lo restituisce all'ultimo degli altri. Una riconnessione dello stesso satellite
sostituisce la sua connessione vecchia (4409), che magari il sistema non ha ancora visto
cadere. Il controllo del PC va al satellite che ha l'esecutore (`per_pc`), anche se in quel
momento è attivo il telefono. La stanza del satellite attivo va agli schermi
(`Mittente.stanza`).

Il telefono (web app, calliope/schermi/telefono.py) parla lo stesso protocollo attraverso il
server degli schermi: `_gestisci` riceve lì una facciata sincrona del WebSocket del browser.

**Tutti insieme** (06/10, `insieme`, calliope/corsie.py): con `satelliti_insieme` (il
predefinito di main.py) ogni satellite collegato ascolta e parla per conto suo, con la sua
corsia (un `AscoltoRemoto` e una `UscitaRemota` legati al suo id, gli eventi nella sua coda).
Non c'è più un attivo da prendere o prestare: `attivo` è il satellite della corsia del thread
che chiede (la stanza per gli schermi, l'origine della richiesta, il PC); `prendi` dice solo
«attivo» al satellite, `lascia` e i prestiti non fanno niente.
"""

import hashlib
import itertools
import math
import os
import queue
import re
import socket
import ssl
import threading
import time
from pathlib import Path

from ..pc.remoto import PCNonCollegato
from . import protocollo as P
from .archivio import ArchivioSatelliti, hash_token
from ..testi import solo_locale


def percorso(cfg, nome: str) -> Path:
    """Un file relativo alla cartella del file di configurazione (come segreti.yaml)."""
    p = Path(nome)
    if p.is_absolute():
        return p
    return Path(getattr(cfg, "config_dir", None) or os.getcwd()) / p


def contesto_tls(cfg):
    """(contesto SSL, impronta) del server, oppure (None, "") se i file non ci sono.
    Solleva ValueError con un messaggio chiaro se ci sono ma non si caricano."""
    cert, chiave = percorso(cfg, cfg.satellite_tls_cert), percorso(cfg, cfg.satellite_tls_chiave)
    if not (cert.is_file() and chiave.is_file()):
        return None, ""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        ctx.load_cert_chain(str(cert), str(chiave))
    except (ssl.SSLError, OSError) as e:
        raise ValueError(f"certificato o chiave non validi ({e.__class__.__name__})") from e
    der = ssl.PEM_cert_to_DER_cert(cert.read_text(encoding="ascii"))
    # websockets legge e scrive da thread diversi: con l'SSLSocket normale ogni tanto un
    # messaggio non partiva (03/10, calliope/tls_sicuro.py)
    from ..tls_sicuro import sicuro
    return sicuro(ctx), P.impronta_der(der)


class SeedRemoto(list):
    """Il barge-in è avvenuto sul satellite, che tiene l'audio con il nome: qui basta un
    segnale vero da passare a `listen(seed=…)`, che lo chiede al satellite."""

    def __init__(self):
        super().__init__([True])


def _numero(v, minimo: float, massimo: float, predefinito: float = 0.0) -> float:
    """Un numero dal satellite, finito e dentro i limiti; altrimenti `predefinito`."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return predefinito
    if not math.isfinite(x):
        return predefinito
    return min(massimo, max(minimo, x))


def _intero(v) -> int | None:
    """Un identificativo dal satellite: un intero, o None."""
    if isinstance(v, bool):
        return None
    try:
        return int(v)
    except (TypeError, ValueError, OverflowError):
        return None


def valida_evento(t: str, m: dict) -> dict | None:
    """Un messaggio del satellite per il ciclo principale, con i campi controllati: tipi e
    limiti giusti, o None se non si usa. Prima un «fa_s» non numerico arrivava a
    `AscoltoRemoto.listen`, nel thread della voce, e faceva cadere Calliope (analisi di
    sicurezza del 03/10, rete, difetto 2)."""
    if not isinstance(m, dict):
        return None
    ident = _intero(m.get("id"))
    if ident is None:
        return None
    out = {"id": ident}
    if t == "frase_finita":
        out.update(fa_s=_numero(m.get("fa_s"), 0.0, 120.0), woke=m.get("woke") is True,
                   wake_score=_numero(m.get("wake_score"), 0.0, 1.0))
        # Pause dentro la frase, parlato, chiusura (07/10, solo misura: calliope/pause.py):
        # facoltativi, un satellite vecchio non li manda
        from ..pause import campi_frase
        out.update(campi_frase(m.get("pause_ms"), m.get("parlato_ms"), m.get("chiusura")))
    elif t == "interruzione":
        out["motivo"] = str(m.get("motivo") or "")[:80]
    return out


def pulisci_esecutore(d) -> dict | None:
    """L'esecutore dichiarato nel «ciao», ridotto a ciò che il server sa usare: capacità
    note, nomi di app brevi. Dati del satellite, mai istruzioni."""
    if not isinstance(d, dict):
        return None
    from ..pc.base import CAPACITA
    caps = [c for c in (d.get("capacita") or []) if c in CAPACITA]
    app = [str(a).strip().lower()[:40] for a in (d.get("app") or [])
           if isinstance(a, str) and a.strip()][:50]
    return {"nome": str(d.get("nome") or "")[:40], "capacita": caps, "app": app,
            "file": bool(d.get("file")), "invio": bool(d.get("invio")),
            "sistema": str(d.get("sistema") or "")[:20]}


# ───────────────────────────── CONNESSIONE ─────────────────────────────
class Collegamento:
    """Un satellite autenticato, con la sua connessione."""

    def __init__(self, ws, satellite: dict, token_hash: str):
        self.ws = ws
        self.satellite = satellite              # id, nome, stanza (dall'archivio)
        self.token_hash = token_hash
        self.pronto = False                     # ha detto il saluto (o non serviva)
        self.eco = None                         # quota di frame «parlato» sul saluto
        self.schermo_id = None                  # lo schermo del satellite (pagina), se c'è
        self.chiuso = threading.Event()
        self._lock = threading.Lock()
        self._invii: dict[int, float] = {}       # thread che stanno mandando → da quando
        self._invii_lock = threading.Lock()
        self._sorvegliante = None
        self._turni: dict[int, list[str]] = {}
        self._turni_cond = threading.Condition()
        # Quando il satellite ha cominciato a suonare ogni frase (monotonic di qui, più il
        # ritardo della sua uscita audio): la latenza che si sente (06/10). Un satellite
        # vecchio non lo dice: resta vuoto
        self.suonate: dict[int, float] = {}
        # Gli eventi di questo satellite per la sua corsia (tutti insieme, 06/10)
        self.eventi: queue.Queue = queue.Queue()
        self.inviati = 0                        # byte mandati (misure)
        self.ricevuti = 0
        self.versione = 1                       # protocollo detto nel «ciao»
        self.modalita = False                   # segue la modalità cambiata a voce (05/10)
        self.wake_presenti: set | None = None   # i classificatori che ha, se lo dice
        # L'esecutore del PC del satellite (versione 2, solo Windows): {"nome", "capacita",
        # "app", "file"} come l'ha dichiarato, già ripulito; None = non c'è
        self.esecutore: dict | None = None
        self._rpc_ids = itertools.count(1)
        self._rpc: dict[int, dict | None] = {}  # richieste in corso → esito (None: in attesa)
        self._rpc_cond = threading.Condition()
        # File in arrivo dal satellite per un lavoro dell'agente: id → stato del trasferimento
        self._in_arrivo: dict[int, dict] = {}
        # Riprese dopo la frase misurate dal satellite (07/10, calliope/pause.py): id
        # dell'ascolto → secondi dalla fine della voce. Solo le ultime
        self.riprese: dict[int, float] = {}

    @property
    def canale(self) -> str:
        """«telefono» (la web app, attraverso il server degli schermi) o «satellite»."""
        return "telefono" if getattr(self.ws, "telefono", False) else "satellite"

    def ripresa(self, ident: int, dopo_s: float):
        self.riprese[ident] = dopo_s
        while len(self.riprese) > 20:
            self.riprese.pop(min(self.riprese))

    @property
    def stanza(self) -> str:
        return self.satellite.get("stanza") or ""

    def ritardo(self) -> float:
        """Metà del giro misurato dai ping del WebSocket (0 finché non ce n'è uno)."""
        try:
            return max(0.0, float(self.ws.latency or 0.0)) / 2
        except Exception:  # noqa: BLE001
            return 0.0

    def invia(self, **campi) -> bool:
        return self._manda(P.testo(**campi))

    def invia_bin(self, dati: bytes) -> bool:
        return self._manda(dati)

    # Un invio (attesa del lock compresa) che dura più di così vuol dire un satellite che non
    # legge più (Wi-Fi lento, buffer TCP pieno): la connessione si chiude invece di fermare il
    # thread principale fino al keepalive di websockets (~20 s). 03/10, analisi di robustezza
    INVIO_MAX_S = 8.0

    def _manda(self, dati) -> bool:
        if self.chiuso.is_set():
            return False
        chi = threading.get_ident()
        with self._invii_lock:
            self._invii[chi] = time.monotonic()
            if self._sorvegliante is None:
                self._sorvegliante = threading.Thread(target=self._sorveglia, daemon=True,
                                                      name="satellite-invii")
                self._sorvegliante.start()
        try:
            with self._lock:
                if self.chiuso.is_set():
                    return False
                self.ws.send(dati)
            self.inviati += len(dati)
            return True
        except Exception:  # noqa: BLE001 — connessione caduta: se ne accorge il thread che legge
            self.chiuso.set()
            return False
        finally:
            with self._invii_lock:
                self._invii.pop(chi, None)

    def _sorveglia(self):
        """Chiude la connessione se un invio resta fermo oltre INVIO_MAX_S: lo shutdown del
        socket sblocca la send, che solleva, e chi mandava riceve False."""
        while not self.chiuso.wait(min(1.0, self.INVIO_MAX_S / 4)):
            with self._invii_lock:
                dal = min(self._invii.values(), default=None)
            if dal is not None and time.monotonic() - dal > self.INVIO_MAX_S:
                nome = self.satellite.get("nome") or self.satellite.get("id") or "?"
                print(f"   [SATELLITE] «{nome}» non riceve da {self.INVIO_MAX_S:.0f} s: chiudo "
                      f"la connessione (si ricollegherà da solo)", flush=True)
                self.chiuso.set()
                try:
                    self.ws.socket.shutdown(socket.SHUT_RDWR)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    self.ws.socket.close()
                except Exception:  # noqa: BLE001
                    pass
                break

    def chiudi(self, codice: int = 1000, motivo: str = ""):
        try:
            self.ws.close(codice, motivo)
        except Exception:  # noqa: BLE001
            pass
        self.chiuso.set()
        self.sveglia_attese()

    def sveglia_attese(self):
        """Connessione chiusa: chi aspetta un turno o un esito lo sa subito."""
        with self._turni_cond:
            self._turni_cond.notify_all()
        with self._rpc_cond:
            self._rpc_cond.notify_all()

    # ── esecutore del PC (versione 2) ──
    def esito(self, ident, m: dict):
        """Un `pc_esito` o un `file_esito` dal satellite. Quelli di richieste già lasciate
        (tempo scaduto) si buttano."""
        try:
            ident = int(ident)
        except (TypeError, ValueError):
            return
        with self._rpc_cond:
            if ident in self._rpc:
                self._rpc[ident] = m
                self._rpc_cond.notify_all()

    def _aspetta_esito(self, ident: int, timeout: float) -> dict:
        fine = time.monotonic() + timeout
        with self._rpc_cond:
            try:
                while self._rpc.get(ident) is None:
                    if self.chiuso.is_set():
                        raise PCNonCollegato("il satellite si è scollegato")
                    resto = fine - time.monotonic()
                    if resto <= 0:
                        raise TimeoutError("non ha risposto in tempo")
                    self._rpc_cond.wait(min(resto, 0.5))
                return self._rpc[ident]
            finally:
                self._rpc.pop(ident, None)

    def chiama_pc(self, metodo: str, argomenti: dict, timeout: float) -> dict:
        """Chiede un metodo all'esecutore del satellite e aspetta l'esito, al più `timeout`
        secondi. Solleva PCNonCollegato (niente esecutore, connessione caduta prima o
        durante) o TimeoutError; l'esito è il dict del satellite ({"ok", …})."""
        if self.esecutore is None:
            raise PCNonCollegato("il satellite collegato non offre il controllo del PC")
        ident = next(self._rpc_ids)
        with self._rpc_cond:
            self._rpc[ident] = None
        if not self.invia(tipo="pc_richiesta", id=ident, metodo=metodo,
                          argomenti=argomenti or {}, scadenza_s=round(timeout, 2)):
            with self._rpc_cond:
                self._rpc.pop(ident, None)
            raise PCNonCollegato("il satellite si è scollegato")
        m = self._aspetta_esito(ident, timeout)
        esito = m.get("esito")
        if not isinstance(esito, dict):
            return {"ok": False, "errore": str(m.get("errore") or "risposta non valida")}
        return esito

    def consegna_file(self, nome: str, estensione: str, dati: bytes,
                      sostituisci: str | None = None, mtime: float | None = None,
                      timeout: float = 10.0, sha256: str | None = None) -> dict:
        """Manda un documento al satellite a pezzi, con lo SHA-256 da controllare all'arrivo.
        L'esito del satellite: {"ok", "rif", "nome_file", "mtime", "motivo", "maniglia"} o
        {"ok": False, "errore"}. Solleva PCNonCollegato o TimeoutError. `sha256` serve solo
        alle prove (un checksum sbagliato apposta)."""
        if not (self.esecutore or {}).get("file"):
            raise PCNonCollegato("il satellite collegato non riceve documenti")
        ident = next(self._rpc_ids)
        with self._rpc_cond:
            self._rpc[ident] = None
        try:
            if not self.invia(tipo="file", id=ident, nome=nome, estensione=estensione,
                              byte=len(dati), sha256=sha256 or hashlib.sha256(dati).hexdigest(),
                              sostituisci=sostituisci, mtime=mtime):
                raise PCNonCollegato("il satellite si è scollegato")
            for i in range(0, len(dati), P.PEZZO_FILE):
                if not self.invia_bin(P.binario(P.FILE, ident, dati[i:i + P.PEZZO_FILE])):
                    raise PCNonCollegato("il satellite si è scollegato durante l'invio")
        except PCNonCollegato:
            with self._rpc_cond:
                self._rpc.pop(ident, None)
            raise
        return self._aspetta_esito(ident, timeout)

    # ── file del PC per l'agente (satellite → server, 03/10) ──
    def ricevi_file(self, maniglia: str, max_byte: int, estensioni, timeout: float) -> dict:
        """Chiede al satellite una copia del file della `maniglia` (una sua ricerca). Esito
        {"ok", "nome", "estensione", "dati"} oppure {"ok": False, "errore", …}. Solleva
        PCNonCollegato o TimeoutError. Si chiama solo dal thread dei lavori: la voce non
        aspetta mai un trasferimento."""
        if not (self.esecutore or {}).get("invio"):
            raise PCNonCollegato("il satellite collegato non sa mandare file all'agente "
                                 "(va aggiornato)")
        ident = next(self._rpc_ids)
        with self._rpc_cond:
            self._rpc[ident] = None
            self._in_arrivo[ident] = {"max": min(int(max_byte), P.FILE_MAX)}
        try:
            if not self.invia(tipo="file_richiesta", id=ident, maniglia=str(maniglia),
                              max_byte=int(max_byte), estensioni=list(estensioni),
                              scadenza_s=round(timeout, 2)):
                with self._rpc_cond:
                    self._rpc.pop(ident, None)
                raise PCNonCollegato("il satellite si è scollegato")
            return self._aspetta_esito(ident, timeout)
        finally:
            with self._rpc_cond:
                self._in_arrivo.pop(ident, None)

    def _fine_arrivo(self, ident: int, esito: dict):
        """Con _rpc_cond preso: l'esito del trasferimento a chi aspetta."""
        self._in_arrivo.pop(ident, None)
        if ident in self._rpc:
            self._rpc[ident] = esito
            self._rpc_cond.notify_all()

    def file_dati(self, m: dict):
        """L'intestazione `file_dati` del satellite (o il suo rifiuto)."""
        try:
            ident = int(m.get("id"))
        except (TypeError, ValueError):
            return
        with self._rpc_cond:
            voce = self._in_arrivo.get(ident)
            if voce is None or "buf" in voce:
                return
            if not m.get("ok"):
                self._fine_arrivo(ident, {"ok": False, "errore": str(m.get("errore") or
                                                                    "non l'ha mandato")[:200],
                                          **{k: True for k in ("troppo_grande", "bloccato",
                                                               "serve_ricerca") if m.get(k)}})
                return
            try:
                byte = int(m.get("byte"))
            except (TypeError, ValueError):
                byte = -1
            sha = str(m.get("sha256") or "").lower()
            nome = str(m.get("nome") or "").replace("\\", "/").rsplit("/", 1)[-1][:120]
            est = str(m.get("estensione") or "").lower()[:10]
            if not 0 <= byte <= voce["max"]:
                self._fine_arrivo(ident, {"ok": False, "troppo_grande": True,
                                          "errore": "il file è più grande del massimo"})
                return
            if not re.fullmatch(r"[0-9a-f]{64}", sha) or not nome:
                self._fine_arrivo(ident, {"ok": False, "errore": "intestazione non valida"})
                return
            voce.update(byte=byte, sha=sha, nome=nome, est=est, buf=bytearray(),
                        h=hashlib.sha256())
            if byte == 0:
                self._completa(ident, voce)

    def file_pezzo(self, ident: int, dati: bytes):
        with self._rpc_cond:
            voce = self._in_arrivo.get(ident)
            if voce is None or "buf" not in voce:
                return
            if len(voce["buf"]) + len(dati) > voce["byte"]:
                self._fine_arrivo(ident, {"ok": False,
                                          "errore": "il file è arrivato più lungo del previsto"})
                return
            voce["buf"] += dati
            voce["h"].update(dati)
            if len(voce["buf"]) == voce["byte"]:
                self._completa(ident, voce)

    def _completa(self, ident: int, voce: dict):
        if voce["h"].hexdigest() != voce["sha"]:
            self._fine_arrivo(ident, {"ok": False,
                                      "errore": "il file è arrivato rovinato (checksum diverso)"})
            return
        self._fine_arrivo(ident, {"ok": True, "nome": voce["nome"], "estensione": voce["est"],
                                  "dati": bytes(voce["buf"])})

    def suonata(self, ident: int, uscita_s: float):
        """Il satellite ha cominciato a suonare la frase `ident`: arriva dopo un giro di rete
        (sbaglia per eccesso di mezzo giro, pochi ms in LAN e in VPN)."""
        if len(self.suonate) > 500:
            for k in sorted(self.suonate)[:250]:
                self.suonate.pop(k, None)
        self.suonate[ident] = time.monotonic() + uscita_s

    def turno_finito(self, ident: int, dette: list[str]):
        with self._turni_cond:
            self._turni[ident] = dette
            self._turni_cond.notify_all()

    def aspetta_turno(self, ident: int, timeout: float) -> list[str] | None:
        fine = time.monotonic() + timeout
        with self._turni_cond:
            while ident not in self._turni:
                resto = fine - time.monotonic()
                if self.chiuso.is_set() or resto <= 0:
                    return None
                self._turni_cond.wait(min(resto, 0.5))
            return self._turni.pop(ident)


# ───────────────────────────── SERVER ─────────────────────────────
class ServerSatelliti:
    CONTROLLO_REVOCA_S = 5.0

    def __init__(self, cfg, archivio: ArchivioSatelliti, log=print):
        self.cfg = cfg
        self.archivio = archivio
        self.log = log
        self.host = str(cfg.satellite_indirizzo or "127.0.0.1")
        self.port = int(cfg.satellite_porta)
        self.ssl, self.impronta = (None, "")
        from ..porte import ATTESA_S
        self.attesa_porta_s = ATTESA_S
        self.eventi: queue.Queue = queue.Queue()
        self._attivo: Collegamento | None = None
        # Tutti i satelliti insieme, una corsia ciascuno (06/10): lo accende main.py
        self.insieme = False
        # Tutte le connessioni autenticate, in ordine di arrivo (l'attivo è una di queste)
        self.collegati: list[Collegamento] = []
        # «Rispondi dove ti ho chiesto» (04/10, calliope/rispondi.py): un satellite attivo in
        # prestito per un turno (frase scritta dal suo schermo, annuncio per una sua richiesta).
        # {"coll", "prima", "fino"}: `prima` torna attivo quando la finestra di follow-up
        # (`fino`, monotonic; None = turno in corso) è finita. Un `prendi` o un `lascia` del
        # satellite stesso chiude il prestito: da lì è una sua scelta
        self.prestito: dict | None = None
        self._prestito_thread = None
        self._cond = threading.Condition()
        self.saluto: tuple[bytes, int] | None = None   # (PCM, frequenza) detto alla connessione
        # Suoni di inizio e fine ascolto (calliope/suoni.py, SuoniAscolto), se accesi (main):
        # vanno nel benvenuto e li suona il satellite, in locale
        self.suoni = None
        self.schermi = None                     # hub degli schermi, se c'è (main)
        # La porta si apre subito (una porta occupata si scopre all'avvio), ma i satelliti
        # si accolgono quando Calliope ha finito di avviarsi: prima non c'è il saluto e
        # nessuno ascolterebbe. main.py lo accende prima del ciclo principale
        self.avviato = threading.Event()
        self._server = None
        self.collegati_in_tutto = 0
        self._fermato = False
        # Connessioni aperte insieme (anche anonime, in attesa del saluto): oltre il tetto
        # si chiudono subito. Senza, 300 connessioni mute davano 600 thread (03/10)
        self.max_connessioni = int(getattr(cfg, "satellite_max_connessioni", 16) or 16)
        self._aperte = 0
        self._aperte_lock = threading.Lock()
        # Il pacchetto per i PC nuovi e per gli aggiornamenti dei satelliti installati
        # (pacchetto.py, web.py): si costruisce in un thread all'avvio
        self.distributore = None

    # ── avvio ──
    def avvia(self) -> "ServerSatelliti":
        """Apre la porta e parte in un thread. OSError se la porta è occupata; ValueError
        se in rete manca il TLS (e non è stato tolto apposta) o il certificato è rovinato."""
        from websockets.sync.server import serve
        # Con il certificato il TLS vale anche su 127.0.0.1 (le prove lo usano così); in rete
        # è obbligatorio, salvo satellite_senza_tls
        self.ssl, self.impronta = contesto_tls(self.cfg)
        if self.ssl is None and not solo_locale(self.host) and not self.cfg.satellite_senza_tls:
            raise ValueError("in rete serve il certificato: python -m calliope.satellite "
                             "--certificato")
        # Come per gli schermi (calliope/porte.py): SO_REUSEADDR fuori da Windows (c'era già),
        # SO_EXCLUSIVEADDRUSE su Windows e qualche tentativo se il processo di prima sta
        # ancora chiudendo. OSError se la porta resta occupata
        from ..porte import socket_in_ascolto
        sock = socket_in_ascolto(self.host, self.port, 8, attesa_s=self.attesa_porta_s,
                                 log=self.log)
        self.port = sock.getsockname()[1]
        self._server = serve(
            self._gestisci, sock=sock, ssl=self.ssl,
            # L'audio PCM non si comprime quasi (−10 %): deflate costerebbe solo CPU
            compression=None,
            # Solo client senza Origin: un browser (anche una pagina web qualunque aperta sul
            # portatile) manda sempre l'Origin e viene rifiutato
            origins=[None],
            max_size=2 ** 20, ping_interval=10, ping_timeout=10, close_timeout=2,
            # Una connessione che non finisce la stretta di mano non tiene un thread a lungo
            open_timeout=3,
            server_header=None,
            # Una caduta di rete è una riga sola («scollegato (rete)»), senza traceback
            logger=P.logger_websockets("server"),
            # Le richieste HTTP normali (non WebSocket): pagina, script e pacchetto per
            # installare un PC nuovo e aggiornare i satelliti (web.py)
            process_request=self._http)
        if self.ssl is not None and getattr(self.cfg, "satellite_installazione", True):
            from .pacchetto import Distributore
            self.distributore = Distributore(self.cfg, log=self.log)
            self.distributore.prepara_in_background()
        threading.Thread(target=self._server.serve_forever, name="satelliti",
                         daemon=True).start()
        return self

    def ferma(self):
        """Chiude le connessioni e la porta. Idempotente, e innocua anche alla chiusura
        dell'interprete (02/10): `Server.shutdown` di websockets chiude le connessioni aperte
        con un ThreadPoolExecutor, che a interprete in chiusura dà «cannot schedule new
        futures after interpreter shutdown». Per questo le connessioni si chiudono prima qui,
        una alla volta, e shutdown trova solo da aspettare i thread."""
        if self._fermato:
            return
        self._fermato = True
        c = self._attivo
        if c is not None:
            c.chiudi(1001, "Calliope si spegne")
        srv = self._server
        if srv is None:
            return
        try:
            for ws in list(srv.connections):
                try:
                    ws.close(1001, "Calliope si spegne")
                except Exception:  # noqa: BLE001 — già chiusa o rete caduta
                    pass
            srv.shutdown()
        except RuntimeError:
            # Interprete in chiusura (atexit): basta chiudere la porta, i thread delle
            # connessioni finiscono con il processo
            try:
                srv.socket.close()
            except OSError:
                pass

    def ferma_alla_chiusura(self):
        """Registra ferma per l'uscita del processo (sys.exit, Ctrl+C). Con
        threading._register_atexit gira prima che l'interprete aspetti i thread non daemon
        (quelli delle connessioni di websockets: con un satellite collegato l'uscita restava
        appesa) e prima che concurrent.futures rifiuti nuovi lavori; atexit come riserva."""
        reg = getattr(threading, "_register_atexit", None)
        if reg is not None:
            try:
                reg(self.ferma)
                return
            except RuntimeError:
                pass
        import atexit
        atexit.register(self.ferma)

    def _http(self, connection, request):
        from .web import risposta
        return risposta(self, request)

    @property
    def schema(self) -> str:
        return "wss" if self.ssl is not None else "ws"

    # ── satellite attivo ──
    def _evento(self, coll: Collegamento, tipo: str, d: dict):
        """Un evento di un satellite per chi lo ascolta: nella coda comune (un attivo alla
        volta) o nella sua (tutti insieme)."""
        if self.insieme:
            coll.eventi.put((tipo, d))
        else:
            self.eventi.put((coll, tipo, d))

    def _della_corsia(self):
        """Tutti insieme: (True, il satellite della corsia del thread, o None se non è
        collegato); (False, None) fuori da una corsia."""
        if not self.insieme:
            return False, None
        from ..corsie import corrente
        c = corrente()
        sid = getattr(c, "satellite_id", None) if c is not None else None
        if sid is None:
            return False, None
        with self._cond:
            via = [x for x in reversed(self.collegati)
                   if x.satellite.get("id") == sid and not x.chiuso.is_set()]
        return True, (via[0] if via else None)

    @property
    def attivo(self) -> Collegamento | None:
        """Il satellite che ascolta e parla adesso: con tutti insieme quello della corsia del
        thread che chiede (fuori da una corsia l'ultimo collegato)."""
        in_corsia, c = self._della_corsia()
        return c if in_corsia else self._attivo

    @attivo.setter
    def attivo(self, coll):
        self._attivo = coll

    def attivo_pronto(self, sat_id=None) -> Collegamento | None:
        if sat_id is not None:
            return self.per_id(sat_id)
        c = self.attivo
        return c if c is not None and c.pronto and not c.chiuso.is_set() else None

    def attendi_pronto(self, timeout: float | None = None,
                       sat_id=None) -> Collegamento | None:
        fine = None if timeout is None else time.monotonic() + timeout
        with self._cond:
            while True:
                c = self.attivo_pronto(sat_id)
                if c is not None:
                    return c
                resto = None if fine is None else fine - time.monotonic()
                if resto is not None and resto <= 0:
                    return None
                self._cond.wait(0.5 if resto is None else min(resto, 0.5))

    def stanza(self) -> str | None:
        c = self.attivo
        return (c.stanza or None) if c is not None else None

    def per_pc(self) -> Collegamento | None:
        """Il satellite che offre il controllo del PC: l'attivo se ce l'ha, altrimenti un
        altro collegato e pronto (il telefono può essere attivo mentre il portatile resta
        collegato: volume, file e documenti restano del portatile)."""
        c = self.attivo_pronto()
        if c is not None and c.esecutore is not None:
            return c
        with self._cond:
            altri = [x for x in reversed(self.collegati)
                     if x.pronto and not x.chiuso.is_set() and x.esecutore is not None]
        return altri[0] if altri else c

    def stato(self) -> dict:
        c = self._attivo
        return {"indirizzo": f"{self.schema}://{self.host}:{self.port}",
                "abbinati": [{"nome": s["nome"], "stanza": s["stanza"]}
                             for s in self.archivio.elenco()],
                "collegato": ({"nome": c.satellite["nome"], "stanza": c.stanza,
                               "pronto": c.pronto, "versione": c.versione,
                               "esecutore": c.esecutore} if c is not None else None),
                "in_attesa": [{"nome": x.satellite["nome"], "stanza": x.stanza}
                              for x in list(self.collegati) if x is not c],
                "tls": self.ssl is not None, "impronta": self.impronta}

    def _registra(self, nuovo: Collegamento):
        """Una connessione nuova e autenticata. Sostituisce quelle vecchie dello stesso
        satellite; diventa l'attiva se non c'è un altro satellite attivo (così il portatile
        che si ricollega non toglie il posto al telefono, e viceversa)."""
        with self._cond:
            stessi = [c for c in self.collegati if c.satellite["id"] == nuovo.satellite["id"]]
            for c in stessi:
                self.collegati.remove(c)
            self.collegati.append(nuovo)
            prima = self._attivo
            attiva = prima is None or prima in stessi or prima.chiuso.is_set() or self.insieme
            if attiva:
                self._attivo = nuovo
            self._cond.notify_all()
        for c in stessi:
            if c is prima or self.insieme:
                self._evento(c, "chiuso", {})
            c.chiudi(P.CHIUSO_SOSTITUITO, "sostituito da un'altra connessione")
        nuovo.invia(tipo="attivo", attivo=attiva,
                    altro=None if attiva else prima.satellite.get("nome"))

    def _togli(self, vecchio: Collegamento):
        """La connessione è finita: se era l'attiva, il posto va all'ultimo degli altri."""
        with self._cond:
            if vecchio in self.collegati:
                self.collegati.remove(vecchio)
            nuovo = None
            if self.prestito is not None and self.prestito["coll"] is vecchio:
                prima = self.prestito["prima"]
                self.prestito = None
                if (self._attivo is vecchio and prima is not None and prima in self.collegati
                        and not prima.chiuso.is_set()):
                    nuovo = self._attivo = prima        # torna com'era prima del prestito
            if self._attivo is vecchio:
                altri = [c for c in reversed(self.collegati) if not c.chiuso.is_set()]
                nuovo = self._attivo = altri[0] if altri else None
            self._cond.notify_all()
        if nuovo is not None and not self.insieme:
            self.log(f"   [SATELLITE] attivo ora: {nuovo.satellite['nome']}")
            nuovo.invia(tipo="attivo", attivo=True, altro=None)

    def prendi(self, coll: Collegamento, prestito: bool = False) -> bool:
        """Il satellite diventa l'attivo (il telefono quando si tocca «Parla» o si accende il
        microfono). L'ascolto in corso sull'altro finisce (evento «cambio»). Chiesto dal
        satellite (`prestito` False) chiude un prestito in corso: è una sua scelta."""
        with self._cond:
            if coll.chiuso.is_set() or coll not in self.collegati:
                return False
            if not prestito:
                self.prestito = None
            prima = self._attivo
            self._attivo = coll
            self._cond.notify_all()
        if prima is coll or self.insieme:
            # Tutti insieme: il telefono che tocca «Parla» non toglie il posto a nessuno
            coll.invia(tipo="attivo", attivo=True, altro=None)
            return True
        if prima is not None:
            self._evento(prima, "cambio", {})
            prima.invia(tipo="attivo", attivo=False, altro=coll.satellite.get("nome"))
        coll.invia(tipo="attivo", attivo=True, altro=None)
        self.log(f"   [SATELLITE] attivo ora: {coll.satellite['nome']}"
                 + (f" (al posto di {prima.satellite['nome']})" if prima is not None else ""))
        return True

    def lascia(self, coll: Collegamento) -> bool:
        """Il satellite restituisce il posto all'ultimo degli altri collegati e pronti; se non
        ce ne sono resta attivo (qualcuno deve pur sentire gli annunci). Tutti insieme: non
        c'è un posto da restituire."""
        if self.insieme:
            return False
        with self._cond:
            if self._attivo is not coll:
                return False
            altri = [c for c in reversed(self.collegati)
                     if c is not coll and c.pronto and not c.chiuso.is_set()]
            if not altri:
                return False
            # Lasciato durante un prestito: il posto torna a chi l'aveva prima
            p, self.prestito = self.prestito, None
            if p is not None and p["coll"] is coll and p["prima"] in altri:
                nuovo = self._attivo = p["prima"]
            else:
                nuovo = self._attivo = altri[0]
            self._cond.notify_all()
        self._evento(coll, "cambio", {})
        coll.invia(tipo="attivo", attivo=False, altro=nuovo.satellite.get("nome"))
        nuovo.invia(tipo="attivo", attivo=True, altro=None)
        self.log(f"   [SATELLITE] attivo ora: {nuovo.satellite['nome']} "
                 f"({coll.satellite['nome']} l'ha lasciato)")
        return True

    # ── rispondi dove ti ho chiesto (04/10, calliope/rispondi.py) ──
    def per_schermo(self, sid) -> Collegamento | None:
        """Il satellite collegato e pronto che ha aperto lo schermo `sid` (il telefono, la
        pagina del portatile), o None: quello schermo non ha audio."""
        if sid is None:
            return None
        with self._cond:
            via = [c for c in reversed(self.collegati)
                   if c.schermo_id == sid and c.pronto and not c.chiuso.is_set()]
        return via[0] if via else None

    def per_id(self, sat_id) -> Collegamento | None:
        """Il satellite collegato e pronto con questo id d'archivio, o None."""
        if sat_id is None:
            return None
        with self._cond:
            via = [c for c in reversed(self.collegati)
                   if c.satellite.get("id") == sat_id and c.pronto and not c.chiuso.is_set()]
        return via[0] if via else None

    def presta(self, coll: Collegamento) -> bool:
        """`coll` diventa l'attivo per questo turno (la risposta si dice da lui, il follow-up
        si ascolta da lui); `restituisci` o la fine della finestra (`proroga_prestito`) lo
        rimettono com'era. Già attivo per sua scelta: non c'è niente da restituire.
        Tutti insieme: la frase la prende già la corsia di `coll` (corsie.Smistatore), che è
        l'unica a cui il prestito «riesce»."""
        if self.insieme:
            return self._della_corsia()[1] is coll
        with self._cond:
            if coll.chiuso.is_set() or coll not in self.collegati or not coll.pronto:
                return False
            p = self.prestito
            if self._attivo is coll:
                if p is not None and p["coll"] is coll:
                    p["fino"] = None                 # il turno è in corso: niente scadenza
                return True
            # Un prestito sopra un altro: si torna comunque al primo attivo
            prima = p["prima"] if p is not None else self._attivo
            self.prestito = {"coll": coll, "prima": prima, "fino": None}
        self.prendi(coll, prestito=True)
        return True

    def trattieni_prestito(self):
        """Un turno comincia sul satellite in prestito: niente scadenza finché non finisce."""
        if self.insieme:
            return
        with self._cond:
            if self.prestito is not None and self._attivo is self.prestito["coll"]:
                self.prestito["fino"] = None

    def proroga_prestito(self, fino: float):
        """Il prestito dura fino a `fino` (monotonic: la fine della finestra di follow-up),
        poi il posto torna a chi l'aveva. Già passata: subito."""
        if self.insieme:
            return
        with self._cond:
            if self.prestito is None:
                return
            if fino > time.monotonic():
                self.prestito["fino"] = fino
                if self._prestito_thread is None:
                    self._prestito_thread = threading.Thread(
                        target=self._scadenza_prestito, name="satelliti-prestito", daemon=True)
                    self._prestito_thread.start()
                self._cond.notify_all()
                return
        self.restituisci()

    def _scadenza_prestito(self):
        while not self._fermato:
            with self._cond:
                p = self.prestito
                fino = p["fino"] if p is not None else None
                if fino is None or fino > time.monotonic():
                    self._cond.wait(0.5 if fino is None
                                    else max(0.05, min(0.5, fino - time.monotonic())))
                    continue
            self.restituisci()

    def restituisci(self) -> bool:
        """Fine del prestito: l'attivo torna quello di prima, se è ancora collegato e pronto
        (altrimenti resta il prestato: qualcuno deve pur sentire gli annunci)."""
        if self.insieme:
            return False
        with self._cond:
            p, self.prestito = self.prestito, None
            if p is None or self._attivo is not p["coll"]:
                return False
            prima = p["prima"]
            if (prima is None or prima not in self.collegati or prima.chiuso.is_set()
                    or not prima.pronto):
                return False
            coll = p["coll"]
            self._attivo = prima
            self._cond.notify_all()
        self._evento(coll, "cambio", {})
        coll.invia(tipo="attivo", attivo=False, altro=prima.satellite.get("nome"))
        prima.invia(tipo="attivo", attivo=True, altro=None)
        self.log(f"   [SATELLITE] attivo ora: {prima.satellite['nome']} (finito il turno "
                 f"chiesto da {coll.satellite['nome']})")
        return True

    # ── connessioni ──
    def _gestisci(self, ws):
        with self._aperte_lock:
            troppe = self._aperte >= self.max_connessioni
            if not troppe:
                self._aperte += 1
        if troppe:
            try:
                ws.close(1013, "troppe connessioni")
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            self._gestisci_una(ws)
        finally:
            with self._aperte_lock:
                self._aperte -= 1

    def _gestisci_una(self, ws):
        path = (ws.request.path if ws.request is not None else "").split("?", 1)[0]
        try:
            if path == P.PERCORSO_ABBINA:
                self._abbina(ws)
            elif path == P.PERCORSO_AUDIO:
                self._sessione(ws)
            else:
                ws.close(1008, "percorso sconosciuto")
        except Exception as e:  # noqa: BLE001 — una connessione rotta non ferma il server
            from websockets.exceptions import ConnectionClosed
            if not isinstance(e, (ConnectionClosed, TimeoutError)):
                self.log(f"   [SATELLITE] errore nella connessione: {type(e).__name__}: {e}")

    def _primo(self, ws) -> dict:
        try:
            msg = ws.recv(timeout=P.ATTESA_CIAO_S)
        except TimeoutError:
            ws.close(1008, "nessun saluto")
            return {}
        d = P.leggi(msg) if isinstance(msg, str) else {}
        if d.get("versione") not in P.VERSIONI:
            ws.close(P.CHIUSO_VERSIONE, f"protocollo {P.VERSIONE}")
            return {}
        return d

    def _abbina(self, ws):
        """Satellite senza token: un codice da mostrare, poi si aspetta che chi amministra
        lo scriva sul server (o che scada).

        Con `ripresa: true` (la web app del telefono, 03/10) arriva anche una ripresa
        segreta: se la pagina viene sospesa mentre la persona dice il codice da un'altra app,
        su una connessione nuova manda {"tipo": "riprendi", "ripresa": …} e ritrova lo stesso
        codice, o il token se nel frattempo è stata abbinata (archivio.ritira)."""
        d = self._primo(ws)
        tipo = d.get("tipo")
        ripresa = None
        if tipo == "riprendi":
            ripresa = str(d.get("ripresa") or "")[:100]
            rip = self.archivio.ritira(ripresa)
            if rip["stato"] == "abbinato":
                self._consegna(ws, rip["token"], rip["schermo"], None, "ripreso")
                return
            if rip["stato"] != "attesa":
                ws.send(P.testo(tipo="scaduto"))
                ws.close(1000, "codice scaduto")
                return
            req = rip
        elif tipo == "abbina":
            chiesto = str(d.get("personale") or "").strip()[:40] or None
            req = self.archivio.nuova_richiesta(personale_chiesto=chiesto,
                                                ripresa=bool(d.get("ripresa")))
            ripresa = req.get("ripresa")
            self.log(f"   [SATELLITE] un satellite chiede l'abbinamento: python -m calliope."
                     f"satellite --abbina <codice> --stanza <stanza>"
                     + (f" (chiede uno schermo personale di {chiesto}: per confermarlo "
                        f"--personale {chiesto})" if chiesto else ""))
        else:
            ws.close(1008, "atteso «abbina»")
            return
        campi = {"ripresa": ripresa} if (ripresa and tipo == "abbina") else {}
        ws.send(P.testo(tipo="codice", codice=req["codice"],
                        scade_s=round(req["scade"] - time.time()), impronta=self.impronta,
                        **campi))
        while True:
            st = self.archivio.stato_richiesta(req["richiesta"])
            if st["stato"] == "abbinato":
                self._consegna(ws, req["richiesta"], st["schermo"], ripresa, "abbinato")
                return
            if st["stato"] == "scaduto":
                ws.send(P.testo(tipo="scaduto"))
                ws.close(1000, "codice scaduto")
                return
            try:
                ws.recv(timeout=1.0)            # il satellite non dice niente: si aspetta
            except TimeoutError:
                pass

    def _consegna(self, ws, token: str, s: dict, ripresa: str | None, come: str):
        """Il token al satellite. Con una ripresa ancora valida si aspetta (poco) che la
        pagina dica di averlo salvato: solo allora la ripresa non serve più. Se il messaggio
        finisce in una connessione morta, la ripresa lo ritira alla connessione dopo."""
        ws.send(P.testo(tipo="abbinato", token=token,
                        satellite={"nome": s["nome"], "stanza": s["stanza"]}))
        self.log(f"   [SATELLITE] {come}: {s['nome']} (stanza {s['stanza']})")
        if ripresa:
            fine = time.monotonic() + 5.0
            while time.monotonic() < fine:
                try:
                    msg = ws.recv(timeout=max(0.1, fine - time.monotonic()))
                except TimeoutError:
                    break
                m = P.leggi(msg) if isinstance(msg, str) else {}
                if m.get("tipo") == "ricevuto":
                    self.archivio.ricevuto(ripresa)
                    break
        ws.close(1000, "abbinato")

    def _sessione(self, ws):
        d = self._primo(ws)
        token = str(d.get("token") or "") if d.get("tipo") == "ciao" else ""
        sat = self.archivio.per_token(token) if token else None
        if sat is None:
            # Nessun dettaglio sul perché: token assente, sbagliato o revocato sono uguali
            ws.close(P.CHIUSO_TOKEN, "non abbinato")
            return
        # Il token è arrivato: l'abbinamento non scade più (archivio, abbinamenti orfani)
        self.archivio.segna_consegnato(token)
        while not self.avviato.wait(1.0):
            ws.ping()                           # il satellite aspetta: la connessione resta viva
        coll = Collegamento(ws, sat, hash_token(token))
        coll.versione = int(d.get("versione") or 1)
        # Segue la modalità cambiata a voce senza riconnettersi (05/10), con i classificatori
        # della wake word che ha
        coll.modalita = d.get("modalita") is True
        presenti = d.get("wake_presenti")
        coll.wake_presenti = ({n for n in (P.nome_modello(x) for x in presenti[:40]) if n}
                              if isinstance(presenti, list) else None)
        if coll.versione >= 2:
            coll.esecutore = pulisci_esecutore(d.get("esecutore"))
            # Solo un satellite con il ruolo «pc», deciso da chi abbina, comanda il PC: un
            # telefono abbinato che dichiara un esecutore non prende volume, file e
            # documenti di casa (analisi di sicurezza del 03/10, rete, difetto 3)
            if coll.esecutore is not None and sat.get("ruolo") != "pc":
                self.log(f"   [SATELLITE] {sat['nome']} dichiara il controllo del PC ma non "
                         f"ha il ruolo «pc»: lo ignoro (calliope satellite --modifica "
                         f"{sat['nome']} --pc)")
                coll.esecutore = None
        self.archivio.segna_visto(sat["id"])
        self.collegati_in_tutto += 1
        parametri = {k: getattr(self.cfg, k) for k in P.PARAMETRI}
        schermi = None
        if self.schermi is not None:
            from ..schermi import solo_locale as schermi_locali
            schermi = {"porta": int(getattr(self.cfg, "schermi_porta", 8770)),
                       "locale": schermi_locali(self.cfg)}
        ws.send(P.testo(tipo="benvenuto", versione=coll.versione,
                        satellite={"nome": sat["nome"],
                                                      "stanza": sat["stanza"]},
                        parametri=parametri, schermi=schermi,
                        saluto=bool(d.get("primo") and self.saluto),
                        # La wake word del server (04/10): il nome del file del modello, che il
                        # satellite usa se ce l'ha (altrimenti tiene il suo), e i suoni
                        **self._campi_modalita(),
                        # La versione del satellite che il server distribuisce: un satellite
                        # installato che è indietro si aggiorna da solo (aggiorna.py)
                        aggiornamento=self._annuncio()))
        if d.get("primo") and self.saluto:
            pcm, rate = self.saluto
            ws.send(P.binario(P.SALUTO, rate, pcm))
        self._registra(coll)
        ese = coll.esecutore
        self.log(f"   [SATELLITE] collegato: {sat['nome']} (stanza {sat['stanza']})"
                 + (f", giro {coll.ws.latency * 1000:.0f} ms" if coll.ws.latency else "")
                 + ((", esecutore del PC: " + (", ".join(ese["capacita"]) or "nessuna capacità")
                     + (", documenti" if ese["file"] else "")) if ese else ""))
        ultimo_controllo = time.monotonic()
        try:
            while True:
                try:
                    msg = ws.recv(timeout=1.0)
                except TimeoutError:
                    msg = None
                if time.monotonic() - ultimo_controllo > self.CONTROLLO_REVOCA_S:
                    ultimo_controllo = time.monotonic()
                    riga = self.archivio.per_token(token)
                    if riga is None:
                        self.log(f"   [SATELLITE] {sat['nome']} revocato: chiudo")
                        coll.chiudi(P.CHIUSO_TOKEN, "revocato")
                        return
                    if riga.get("proprietario") != coll.satellite.get("proprietario"):
                        # Reso personale (o della stanza) da terminale: il suo schermo segue
                        coll.satellite = riga
                        self._allinea_schermo(coll)
                if msg is None:
                    continue
                if isinstance(msg, (bytes, bytearray)):
                    coll.ricevuti += len(msg)
                    tipo, ident, pcm = P.apri_binario(bytes(msg))
                    if tipo == P.AUDIO:
                        self._evento(coll, "audio", {"id": ident, "pcm": pcm})
                    elif tipo == P.VERIFICA:
                        self._evento(coll, "voce", {"id": ident, "pcm": pcm})
                    elif tipo == P.FILE_SU:
                        coll.file_pezzo(ident, pcm)
                    continue
                m = P.leggi(msg)
                t = m.get("tipo") if isinstance(m, dict) else None
                try:
                    self._messaggio(coll, sat, t, m)
                except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as e:
                    # Un messaggio rotto si scarta: né la connessione né Calliope cadono
                    self.log(f"   [SATELLITE] {sat['nome']}: messaggio «{str(t)[:20]}» non "
                             f"valido, scartato ({type(e).__name__})")
        finally:
            coll.chiuso.set()
            coll.sveglia_attese()
            if self._attivo is coll or self.insieme:
                self._evento(coll, "chiuso", {})
                # Nessun saluto di chiusura dal satellite: la rete è caduta (VPN, Wi-Fi)
                rete = getattr(ws.protocol, "close_rcvd", True) is None
                self.log(f"   [SATELLITE] {sat['nome']} scollegato"
                         + (" (rete)" if rete else ""))
            self._togli(coll)

    def _messaggio(self, coll: Collegamento, sat: dict, t, m: dict):
        """Un messaggio di testo di un satellite autenticato, già decodificato."""
        if t == "pronto":
            eco = m.get("eco")
            coll.eco = (None if eco is None or isinstance(eco, bool)
                        else _numero(eco, 0.0, 1.0, None))
            coll.pronto = True
            with self._cond:
                self._cond.notify_all()
            eco = ("non misurata" if coll.eco is None
                   else f"{coll.eco * 100:.0f} % dei frame")
            self.log(f"   [SATELLITE] {sat['nome']} pronto (eco sul saluto: {eco})")
        elif t == "turno_finito":
            dette = m.get("dette")
            coll.turno_finito(_intero(m.get("id")) or 0,
                              [str(x)[:500] for x in dette][:50]
                              if isinstance(dette, list) else [])
        elif t == "ripresa":
            # Qualcuno ha ricominciato a parlare subito dopo la frase (07/10, solo misura)
            ident = _intero(m.get("id"))
            dopo = _numero(m.get("dopo_s"), 0.0, 10.0, None)
            if ident is not None and dopo is not None:
                coll.ripresa(ident, round(dopo, 2))
        elif t == "suona":
            ident = _intero(m.get("id"))
            if ident is not None:
                coll.suonata(ident, _numero(m.get("uscita_s"), 0.0, 2.0, 0.0))
        elif t == "schermo":
            self._schermo(coll, m)
        elif t in ("pc_esito", "file_esito"):
            coll.esito(m.get("id"), m)
        elif t == "file_dati":
            coll.file_dati(m)
        elif t == "wake_richiesta":
            # In un thread: ~0,9 MB non fermano la lettura dei messaggi del satellite
            threading.Thread(target=self._manda_modello, args=(coll, m.get("nome")),
                             daemon=True, name="satellite-modello").start()
        elif t == "prendi":
            self.prendi(coll)
        elif t == "lascia":
            self.lascia(coll)
        elif t in ("frase_finita", "scartata", "nessuna_frase", "interruzione",
                   "veglia_finita"):
            ev = valida_evento(t, m)
            if ev is not None:
                self._evento(coll, t, ev)

    # ── modalità (05/10): wake word e suoni, nel benvenuto e quando cambiano a voce ──
    def _wake_file(self) -> list[tuple[str, str]]:
        """[(nome, percorso)] dei classificatori della wake word in uso (Config.wake_models),
        solo quelli che ci sono."""
        out = []
        for m in getattr(self.cfg, "wake_models", None) or [self.cfg.wake_model]:
            nome = P.nome_modello(os.path.basename(str(m or "")))
            if nome and os.path.isfile(str(m)):
                out.append((nome, str(m)))
        return out

    def _impronte(self) -> list[dict]:
        """{nome, sha256, byte} dei classificatori in uso (tenuti finché il file non cambia)."""
        import hashlib
        cache = self.__dict__.setdefault("_cache_impronte", {})
        out = []
        for nome, path in self._wake_file():
            st = os.stat(path)
            chiave = (path, st.st_mtime, st.st_size)
            if chiave not in cache:
                with open(path, "rb") as f:
                    cache[chiave] = hashlib.sha256(f.read()).hexdigest()
            out.append({"nome": nome, "sha256": cache[chiave], "byte": st.st_size})
        return out

    def _campi_modalita(self) -> dict:
        """Wake word e suoni del server: nel benvenuto e nel messaggio «modalita». Il
        satellite usa il modello di `wake_modello` se ce l'ha (il primo di `wake_modelli`,
        con gli altri insieme: «Computer» e «Calliope»), e suona i suoni."""
        suoni = self.suoni
        return {"wake_modello": os.path.basename(str(self.cfg.wake_model or "")),
                "wake_modelli": self._impronte(),
                "suoni": (suoni.per_satellite(self.saluto[1] if self.saluto else 22050)
                          if suoni is not None else None)}

    def annuncia_modalita(self) -> dict:
        """La modalità è cambiata a voce: ai satelliti collegati che la seguono va il
        messaggio «modalita»; gli altri (versione vecchia) la prendono alla connessione dopo.
        Note per la risposta: chi va riavviato, a chi manca un modello (lo chiederà)."""
        parametri = {k: getattr(self.cfg, k) for k in P.PARAMETRI}
        campi = self._campi_modalita()
        nomi = {m["nome"] for m in campi["wake_modelli"]}
        with self._cond:
            colls = [c for c in self.collegati if c.pronto and not c.chiuso.is_set()]
        vecchi, senza, aggiornati = [], [], 0
        for c in colls:
            nome = c.satellite.get("nome") or str(c.satellite.get("id"))
            if not getattr(c, "modalita", False):
                vecchi.append(nome)
                continue
            if c.invia(tipo="modalita", parametri=parametri, **campi):
                aggiornati += 1
            pres = getattr(c, "wake_presenti", None)
            if pres is not None and campi["wake_modello"] not in pres and                     campi["wake_modello"] in nomi:
                senza.append(nome)
        self.log(f"   [SATELLITE] modalità mandata a {aggiornati} satelliti"
                 + (f"; da riavviare (versione vecchia): {', '.join(vecchi)}" if vecchi else ""))
        return {"satelliti_aggiornati": aggiornati, "satelliti_da_riavviare": vecchi,
                "satelliti_senza_modello": senza}

    def _manda_modello(self, coll, nome) -> None:
        """Un classificatore chiesto dal satellite (wake_richiesta): solo uno di quelli in uso,
        dai file del server, al più P.MODELLO_MAX."""
        nome = P.nome_modello(nome)
        trovati = dict(self._wake_file())
        imp = {m["nome"]: m for m in self._impronte()}
        if nome is None or nome not in trovati:
            coll.invia(tipo="wake_file", nome=str(nome or "")[:40], errore="non disponibile")
            return
        if imp[nome]["byte"] > P.MODELLO_MAX:
            coll.invia(tipo="wake_file", nome=nome, errore="troppo grande")
            return
        with open(trovati[nome], "rb") as f:
            dati = f.read(P.MODELLO_MAX + 1)
        import hashlib
        sha = hashlib.sha256(dati).hexdigest()
        if coll.invia(tipo="wake_file", nome=nome, sha256=sha, byte=len(dati)):
            coll.invia_bin(P.binario(P.MODELLO, 0, dati))
            self.log(f"   [SATELLITE] {coll.satellite.get('nome')}: mandato il modello della "
                     f"wake word «{nome}» ({len(dati) // 1024} kB)")

    def _annuncio(self) -> dict | None:
        p = self.distributore.pronto() if self.distributore is not None else None
        return p.annuncio() if p is not None else None

    def _schermo(self, coll: Collegamento, m: dict):
        """Il satellite vuole aprire la pagina degli schermi: le serve un token di schermo.
        Il token passa sulla connessione autenticata (cifrata in rete).

        **Uno schermo per satellite** (05/10): sulla DGX ogni ricollegamento dopo un
        aggiornamento faceva nascere un abbinamento nuovo («studio di dario 2», mai
        collegato) appena il token conservato dal satellite non valeva più. Ora lo schermo
        sa di chi è (colonna `satellite`), e nell'ordine:
        1. il token che il satellite ripresenta, se è ancora abbinato e non è di un altro
           satellite (uno schermo di prima del 05/10 si lega qui a questo satellite);
        2. lo schermo già legato al satellite, con un token nuovo (il satellite aveva perso
           il suo: credenziali rifatte, pagina del telefono ripulita): stesso schermo, stesso
           nome, il token vecchio non vale più;
        3. solo se non ne ha nessuno, uno schermo nuovo nella stanza del satellite."""
        hub = self.schermi
        if hub is None:
            coll.invia(tipo="schermo", porta=None, motivo="schermi spenti sul server")
            return
        from ..schermi import solo_locale as schermi_locali
        porta = int(getattr(self.cfg, "schermi_porta", 8770))
        arch = hub.archivio
        sat = coll.satellite
        sat_id = sat.get("id")
        vecchio = str(m.get("token") or "")
        s = arch.per_token(vecchio) if vecchio else None
        if s is not None and s.get("satellite") not in (None, sat_id):
            s = None                      # lo schermo di un altro satellite: non si prende
        token = None
        if s is not None:
            if s.get("satellite") is None and sat_id is not None:
                arch.lega_satellite(s["id"], sat_id)
                hub._rinfresca()
                self.log(f"   [SATELLITE] schermo «{s['nome']}» legato al satellite "
                         f"«{sat.get('nome')}»")
        else:
            s = arch.per_satellite(sat_id) if sat_id is not None else None
            if s is not None:
                token = arch.rinnova_token(s["id"])
                hub._rinfresca()
                self.log(f"   [SATELLITE] schermo «{s['nome']}» ritrovato per il satellite "
                         f"«{sat.get('nome')}»: token nuovo")
            else:
                # Lo schermo del satellite eredita il proprietario: personale se il satellite
                # lo è
                s, token = arch.crea_con_token(coll.stanza or "satellite",
                                               sat.get("proprietario"),
                                               sat.get("proprietario_nome"),
                                               satellite=sat_id)
                hub._rinfresca()
                self.log(f"   [SATELLITE] schermo «{s['nome']}» abbinato per il satellite"
                         + (f" (personale di {s['proprietario_nome']})"
                            if s.get("proprietario_nome") else ""))
        coll.schermo_id = s["id"]
        self._allinea_schermo(coll)
        coll.invia(tipo="schermo", porta=porta, locale=schermi_locali(self.cfg), token=token,
                   **self._tls_schermi(hub))

    @staticmethod
    def _tls_schermi(hub) -> dict:
        """La pagina è in HTTPS? Con l'impronta SHA-256 del suo certificato, che il ponte
        TLS del satellite controlla (schermi/ponte.py). Arriva sulla connessione già
        verificata con l'impronta dell'abbinamento."""
        t = getattr(hub, "tls", None)
        return {"https": True, "impronta": t["impronta"]} if t else {"https": False}

    def imposta_proprietario(self, sat_id: int, proprietario: str | None,
                             proprietario_nome: str | None) -> dict | None:
        """Rende personale (o della stanza, con None) un satellite già abbinato, come
        `--modifica` da terminale ma subito: se è quello collegato il suo schermo cambia ora,
        senza aspettare il controllo periodico (schermo_gestisci a voce, 03/10)."""
        s = self.archivio.imposta_proprietario(sat_id, proprietario, proprietario_nome)
        if s is None:
            return None
        with self._cond:
            stessi = [c for c in self.collegati if c.satellite.get("id") == sat_id]
        a = self._attivo
        if a is not None and a not in stessi and a.satellite.get("id") == sat_id:
            stessi.append(a)
        for c in stessi:
            c.satellite = s
            self._allinea_schermo(c)
        return s

    def _allinea_schermo(self, coll: Collegamento):
        """Lo schermo del satellite ha lo stesso proprietario del satellite (o nessuno)."""
        hub, sid = self.schermi, getattr(coll, "schermo_id", None)
        if hub is None or sid is None:
            return
        sat = coll.satellite
        s = next((x for x in hub.archivio.elenco() if x["id"] == sid), None)
        if s is None or s.get("proprietario") == sat.get("proprietario"):
            return
        hub.archivio.imposta_proprietario(sid, sat.get("proprietario"),
                                          sat.get("proprietario_nome"))
        hub._rinfresca()
        self.log(f"   [SATELLITE] schermo «{s['nome']}»: "
                 + (f"personale di {sat['proprietario_nome']}" if sat.get("proprietario")
                    else "della stanza"))


# ───────────────────────────── ASCOLTO REMOTO ─────────────────────────────
class AscoltoRemoto:
    """Il microfono di un satellite, con il contratto di `audio.Listener`."""

    remoto = True
    FRAME = 512

    def __init__(self, server: ServerSatelliti, cfg, log=print, sat_id=None):
        self.server = server
        self.cfg = cfg
        self.log = log
        # Il satellite di questa corsia (tutti insieme, 06/10); None = l'attivo
        self.sat_id = sat_id
        self.started_at = 0.0
        self.ended_at = 0.0       # fine della voce (fine_parlato_s), come Listener
        self.woke, self.wake_score = False, 0.0
        self.on_speech_start = None
        self.on_speech_end = None
        self._ids = itertools.count(1)
        self._in_attesa = False
        # Come Listener (07/10, calliope/pause.py): le misure dell'ultima frase, dal satellite
        # (None se è un satellite vecchio), e il canale da cui è arrivata
        self.pause_ms: list[int] | None = None
        self.parlato_ms: int | None = None
        self.chiusura: str | None = None
        self.canale: str | None = None
        self.satellite_nome: str | None = None
        self._ultima: tuple | None = None       # (collegamento, id) dell'ultima frase

    def attendi(self):
        """Blocca finché non c'è un satellite pronto. Il ciclo principale la chiama prima
        degli annunci: un timer scaduto a portatile spento si annuncia quando torna."""
        if self.server.attivo_pronto(self.sat_id) is not None:
            self._in_attesa = False
            return
        if not self._in_attesa and self.sat_id is None:
            self.log(f"   [SATELLITE] aspetto un satellite su {self.server.schema}://"
                     f"{self.server.host}:{self.server.port}…")
            self._in_attesa = True
        self.server.attendi_pronto(sat_id=self.sat_id)
        self._in_attesa = False

    def _evento(self, coll, timeout=0.05):
        if self.server.insieme:
            try:
                return coll.eventi.get(timeout=timeout)
            except queue.Empty:
                return None, None
        try:
            c, tipo, d = self.server.eventi.get(timeout=timeout)
        except queue.Empty:
            return None, None
        if c is not coll:
            return None, None
        return tipo, d

    def listen(self, wake=None, awake_until: float = float("inf"), seed=None,
               wakeup: threading.Event | None = None):
        """Come Listener.listen: la prossima frase rivolta a Calliope, o None se `wakeup`
        arriva mentre nessuno parla. Il satellite decide sveglia/addormentata con la sua
        wake word; qui arriva solo ciò che lascerebbe passare Listener in locale."""
        on_start = self.on_speech_start
        on_end = self.on_speech_end
        while True:
            coll = self.server.attendi_pronto(sat_id=self.sat_id)
            lid = next(self._ids)
            resto = None if math.isinf(awake_until) else round(awake_until - time.monotonic(), 3)
            coll.invia(tipo="ascolta", id=lid, wake=wake is not None, sveglia_per_s=resto,
                       seed=bool(seed))
            seed = None              # vale una volta: dopo una riconnessione non c'è più
            pezzi, iniziata, sveglia = [], False, False
            while True:
                if wakeup is not None and wakeup.is_set() and not sveglia:
                    sveglia = coll.invia(tipo="sveglia", id=lid) or True
                tipo, d = self._evento(coll)
                if tipo is None:
                    continue
                if tipo in ("chiuso", "cambio"):
                    if tipo == "cambio":
                        # Un altro satellite ha preso il posto: questo smette di ascoltare
                        # appena nessuno gli parla (una sua frase, se arriva, si ignora)
                        coll.invia(tipo="sveglia", id=lid)
                    if iniziata and on_end is not None:
                        on_end()
                    break                         # si riparte con il satellite nuovo
                if d.get("id") != lid:
                    continue
                if tipo == "audio":
                    if not iniziata:
                        iniziata = True
                        if on_start is not None:
                            on_start()
                    pezzi.append(d["pcm"])
                elif tipo == "scartata":
                    pezzi = []
                    if iniziata and on_end is not None:
                        on_end()
                    iniziata = False
                elif tipo == "nessuna_frase":
                    return None
                elif tipo == "frase_finita":
                    audio = P.da_pcm(b"".join(pezzi))
                    # Il satellite dice quanto fa è iniziata: l'istante qui, meno metà giro
                    self.started_at = (time.monotonic() - float(d.get("fa_s") or 0.0)
                                       - coll.ritardo())
                    # La voce è finita il silenzio di chiusura del VAD prima dell'invio, più
                    # metà giro (stessa stima di started_at)
                    self.ended_at = (time.monotonic() - self.cfg.silence_ms / 1000
                                     - coll.ritardo())
                    self.woke = bool(d.get("woke"))
                    self.wake_score = float(d.get("wake_score") or 0.0)
                    self.pause_ms = d.get("pause_ms")
                    self.parlato_ms = d.get("parlato_ms")
                    self.chiusura = d.get("chiusura")
                    self.canale = coll.canale
                    self.satellite_nome = coll.satellite.get("nome")
                    self._ultima = (coll, lid)
                    return audio

    def ripresa_s(self) -> float | None:
        """La ripresa dopo l'ultima frase, se il satellite l'ha misurata (pause.py)."""
        if self._ultima is None:
            return None
        coll, lid = self._ultima
        return coll.riprese.get(lid)

    def ferma_ripresa(self):
        """La misura la ferma il satellite da sé, quando arriva la risposta."""

    def watch_for_name(self, wake, stop: threading.Event, muted, voice_ok=None):
        """Barge-in: la wake word (e il livello B) girano sul satellite, che ferma da solo
        la riproduzione entro un blocco da 100 ms; qui si riceve l'avviso. `muted` non serve
        (il satellite sa cosa sta dicendo). L'impronta della voce, per il livello B, si
        calcola qui: il satellite manda il parlato e aspetta la risposta."""
        coll = self.server.attivo_pronto(self.sat_id)
        if coll is None:
            stop.wait()
            return None
        wid = next(self._ids)
        livello_b = (voice_ok is not None and coll.eco is not None
                     and coll.eco <= self.cfg.barge_in_echo_max)
        coll.invia(tipo="veglia", id=wid, livello_b=livello_b)
        fine = None
        while True:
            if stop.is_set() and fine is None:
                coll.invia(tipo="fine_veglia", id=wid)
                fine = time.monotonic() + 2.0
            if fine is not None and time.monotonic() > fine:
                return None
            tipo, d = self._evento(coll)
            if tipo is None:
                continue
            if tipo == "chiuso":
                return None
            if tipo == "cambio":
                coll.invia(tipo="fine_veglia", id=wid)
                return None
            if d.get("id") != wid:
                continue
            if tipo == "voce":
                ok = bool(voice_ok(P.da_pcm(d["pcm"]))) if voice_ok is not None else False
                coll.invia(tipo="esito_voce", id=wid, ok=ok)
            elif tipo == "interruzione":
                print(f"\n   [BARGE-IN] {d.get('motivo') or 'interrotta'} sul satellite",
                      flush=True)
                return SeedRemoto()
            elif tipo == "veglia_finita":
                return None

    def measure_echo(self, stop: threading.Event) -> float:
        """L'eco la misura il satellite mentre dice il saluto (la manda con «pronto»)."""
        stop.wait()
        c = self.server.attivo_pronto(self.sat_id)
        return c.eco if c is not None and c.eco is not None else 1.0


# ───────────────────────────── USCITA REMOTA ─────────────────────────────
class UscitaRemota:
    """Dove `tts.Speaker` manda le frasi quando le casse sono di un satellite."""

    def __init__(self, server: ServerSatelliti, sat_id=None):
        self.server = server
        # Il satellite di questa corsia (tutti insieme, 06/10); None = l'attivo
        self.sat_id = sat_id
        self._ids = itertools.count(1)
        self._in_coda_s = 0.0          # audio mandato dall'ultima fine del turno
        self._prime: dict[int, tuple] = {}     # turno di Speaker → (collegamento, id frase)

    def invia(self, turno: int, testo: str, audio: bytes, rate: int):
        coll = self.server.attivo_pronto(self.sat_id)
        if coll is None:
            return                      # nessuno ascolta: la frase si perde (lo dice il log)
        fid = next(self._ids)
        if turno not in self._prime:
            if len(self._prime) > 50:
                self._prime.pop(min(self._prime), None)
            self._prime[turno] = (coll, fid)
        coll.invia(tipo="frase", turno=turno, id=fid, testo=testo, rate=rate, byte=len(audio))
        # A pezzi: il satellite comincia a riprodurre al primo, anche se la connessione è in
        # partenza lenta (TCP dopo una pausa riparte con una finestra piccola)
        step = int(rate * P.PEZZO_VOCE_S) * 2
        for i in range(0, len(audio), step):
            if not coll.invia_bin(P.binario(P.VOCE, fid, audio[i:i + step])):
                return
        self._in_coda_s += len(audio) / 2 / rate

    def prima_voce(self, turno: int) -> float | None:
        """Il monotonic in cui il satellite ha cominciato a suonare la prima frase del turno
        (None se non lo sa: satellite vecchio, frase non suonata)."""
        coll, fid = self._prime.get(turno, (None, None))
        return coll.suonate.get(fid) if coll is not None else None

    def fine_turno(self) -> list[str] | None:
        """Aspetta che il satellite abbia detto tutto; le frasi dette per intero."""
        attesa, self._in_coda_s = self._in_coda_s + 10.0, 0.0
        coll = self.server.attivo_pronto(self.sat_id)
        if coll is None:
            return None
        k = next(self._ids)
        if not coll.invia(tipo="fine_turno", id=k):
            return None
        return coll.aspetta_turno(k, attesa)

    def ferma(self, turno: int):
        coll = self.server.attivo_pronto(self.sat_id)
        if coll is not None:
            coll.invia(tipo="ferma", turno=turno)
