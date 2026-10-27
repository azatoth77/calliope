"""
Il satellite: il programma leggero del portatile (`python -m calliope.satellite`).

Cosa gira qui e perché (docs/ricerche/2026-10-02-satellite.md):
- **microfono, VAD e wake word**: lo stesso `audio.Listener` di Calliope in locale, con il
  rilevatore «Calliope» (ONNX). Da addormentata l'audio resta qui: esce solo la frase in cui
  scatta la wake word (con il pre-roll, perché Whisper senta il nome), e da sveglia (finestra
  di follow-up) le frasi che il VAD riconosce. I frame partono mentre si parla, così a fine
  frase al server manca solo l'ultimo pezzo. CPU: Silero VAD con onnxruntime (niente torch)
  e la wake word, ~2–3 ms ogni 80 ms;
- **riproduzione**: le frasi sintetizzate dal server arrivano a pezzi e si riproducono
  appena c'è il primo, con le attenzioni per le cuffie Bluetooth (`tts_lead_s`,
  `tts_tail_s`, keepalive: tts.UscitaLocale);
- **barge-in**: mentre parla la wake word resta accesa qui, e «Calliope, basta» ferma la
  riproduzione entro un blocco da 100 ms senza aspettare la rete; il server lo sa dopo;
- **eco**: misurata mentre dice il saluto della prima connessione (come in locale): decide
  se anche la voce di chi è registrato può interromperla (livello B, l'impronta la calcola
  il server).

Whisper, chi parla, modello, voce (Piper) e tool restano sul server. Il satellite si
ricollega da solo (attese 1, 2, 5, 10, 15 s) e non ha porte in rete (l'inoltro per il telefono
di casa, `satellite_inoltro`, è stato tolto il 16/10, #61: il telefono raggiunge il server con la
sua VPN).

Su Windows il satellite è anche l'**esecutore del PC** (03/10, esecutore.py): annuncia nel
«ciao» le capacità del portatile (volume, musica, luminosità, ricerca di file, app del
catalogo…), esegue le richieste `pc_*` del server e riceve i documenti scritti sulla DGX.
"""

import collections
import json
import os
import queue
import socket
import ssl
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np

from ..tts import UscitaLocale, dice_nome
from . import protocollo as P

ATTESE_RICONNESSIONE = (1, 2, 5, 10, 15)
# Una sessione conta come «collegata» (e la caduta dopo riparte dalla prima attesa) solo se è
# rimasta su almeno tanto (17/10, #5, revisione della PR #145): più dell'ultima attesa, così una
# sessione accolta e chiusa subito (un errore del server dopo il benvenuto) non fa riprovare
# ogni secondo per sempre, e le attese continuano ad allungarsi
SESSIONE_STABILE_S = 30.0
# Chiusa con 4409 (sostituito): un altro satellite usa le stesse credenziali (la cartella copiata
# su un altro PC, due processi sulla stessa macchina). Riprovare subito vorrebbe dire togliersi
# il posto a vicenda per sempre (misurato: 40 connessioni in 40 s): si aspetta a lungo
ATTESA_SOSTITUITO_S = 60.0


class ImprontaDiversa(Exception):
    """Il certificato del server non è quello abbinato: non si manda il token."""


class NonAbbinato(Exception):
    """Il server non riconosce il token (mai abbinato, revocato, archivio diverso)."""


def percorso(cfg, nome: str) -> Path:
    p = Path(nome)
    if p.is_absolute():
        return p
    return Path(getattr(cfg, "config_dir", None) or os.getcwd()) / p


# ───────────────────────────── RIPRODUZIONE ─────────────────────────────
class _Frase:
    def __init__(self, sessione, turno, ident, testo, rate, totale):
        self.sessione = sessione
        self.turno, self.id, self.testo, self.rate, self.totale = turno, ident, testo, rate, totale
        self.buf = bytearray()
        self.cond = threading.Condition()

    @property
    def completa(self) -> bool:
        return len(self.buf) >= self.totale


class Riproduttore:
    """Le frasi del server, una dopo l'altra, a blocchi da 100 ms. Un turno interrotto
    (`ferma`) si scarta tutto, anche le frasi che arrivano dopo."""

    BLOCCO_S = 0.1
    ATTESA_PEZZO_S = 3.0       # oltre, la frase si considera persa (server caduto)

    def __init__(self, cfg, apri_flusso=None, turno_finito=None, rate: int = 22050,
                 suonata=None):
        self.cfg = cfg
        self.out = UscitaLocale(cfg, rate, apri_flusso)
        self.turno_finito = turno_finito          # funzione(id, dette)
        # funzione(id della frase, uscita_s): la frase comincia a suonare adesso (06/10, la
        # latenza che si sente: il server la scrive nel registro dei turni, `prima_voce_s`)
        self.suonata = suonata
        self.q: queue.Queue = queue.Queue()
        self._frasi: dict[int, _Frase] = {}
        self.scarta_fino = 0                      # turni interrotti (≤ questo)
        self.ultimo_turno = 0
        # Ogni connessione ha i suoi turni (un server riavviato riparte da 1): ciò che resta
        # di una connessione vecchia non si riproduce
        self.sessione = 0
        self.dette: list[str] = []
        self._now_text = ""
        self._name_until = 0.0
        self.in_corso = False                     # sta riproducendo una frase
        # La frase che suona (o l'ultima) e quando è finita: la stanza segna i segmenti detti
        # durante la voce (14/10, passo 5, satellite/stanza.py)
        self._frase_id = None
        self._frase_fine = 0.0
        self.interrotta_a = None                  # monotonic dell'ultima interruzione
        self.ultima_scrittura = 0.0               # monotonic della fine dell'ultima scrittura
        self.byte_riprodotti = 0
        self._pcm_fino = 0.0                      # monotonic: fine dell'ultimo suono locale
        threading.Thread(target=self._lavora, name="riproduttore", daemon=True).start()

    # ── dal server ──
    def frase(self, turno: int, ident: int, testo: str, rate: int, totale: int):
        f = _Frase(self.sessione, turno, ident, testo, rate, totale)
        self._frasi[ident] = f
        self.ultimo_turno = max(self.ultimo_turno, turno)
        self.q.put(f)

    def pezzo(self, ident: int, pcm: bytes):
        f = self._frasi.get(ident)
        if f is None:
            return
        with f.cond:
            f.buf += pcm
            f.cond.notify_all()

    def fine_turno(self, ident: int):
        self.q.put(("fine", ident, self.sessione))

    def ferma(self, turno: int | None = None):
        """Smette subito (al prossimo blocco) e scarta il turno, anche ciò che arriverà."""
        self.scarta_fino = max(self.scarta_fino, self.ultimo_turno if turno is None else turno)
        self.interrotta_a = time.monotonic()
        for f in list(self._frasi.values()):
            with f.cond:
                f.cond.notify_all()

    def suona(self, pcm: bytes, rate: int) -> threading.Event:
        """Audio locale (il saluto, il segnale): l'evento si accende a fine riproduzione."""
        fatto = threading.Event()
        self.q.put(("pcm", pcm, rate, fatto))
        return fatto

    def svuota(self):
        """Connessione caduta: niente più frasi a metà, niente turni in sospeso."""
        self.ferma()
        self.dette = []

    def nuova_sessione(self):
        """Connessione nuova: i turni ripartono da capo, quelli vecchi non valgono più."""
        self.sessione += 1
        self.scarta_fino = self.ultimo_turno = 0
        self._frasi.clear()
        self.dette = []

    def occupato(self, margine: float = 0.4) -> bool:
        """Sta suonando qualcosa (una frase, un segnale), o l'ha appena finito: la misura
        della ripresa dopo la frase (calliope/pause.py) non deve sentire le casse."""
        ora = time.monotonic()
        return (self.in_corso or not self.q.empty() or ora < self._pcm_fino + margine
                or ora - self.ultima_scrittura < margine)

    def voce_ora(self, coda_s: float = 1.0):
        """L'id della frase che suona adesso o finita da meno di `coda_s` (l'eco dura un po'
        dopo), 0 per un suono senza testo (saluto, segnale), None se le casse tacciono."""
        ora = time.monotonic()
        fid = self._frase_id
        if fid is not None and (self.in_corso or ora < self._frase_fine + coda_s):
            return fid
        if ora < self._pcm_fino + coda_s:
            return 0
        return None

    def saying_name(self) -> bool:
        """Come Speaker.saying_name: la wake word va ignorata mentre dice il suo nome."""
        return dice_nome(self.cfg, self._now_text) or time.monotonic() < self._name_until

    # ── thread ──
    def _lavora(self):
        keepalive = self.cfg.tts_keepalive
        while True:
            try:
                item = self.q.get(timeout=0.02 if keepalive else 1.0)
            except queue.Empty:
                # Keepalive; con l'uscita guasta (cuffie sparite) prova a riaprirla
                if keepalive or self.out.guasta:
                    self.out.mantieni()
                continue
            # Un errore non deve mai fermare il thread (03/10): prima le cuffie sparite a metà
            # frase lo uccidevano e il satellite restava muto fino al riavvio
            try:
                self._lavora_uno(item)
            except Exception as e:  # noqa: BLE001
                self.in_corso, self._now_text = False, ""
                print(f"   [SATELLITE] Riproduzione: {type(e).__name__}: {e}", flush=True)
                if isinstance(item, tuple) and item and item[0] == "pcm":
                    item[3].set()

    def _lavora_uno(self, item):
        if isinstance(item, _Frase):
            try:
                self._riproduci(item)
            finally:
                self._frasi.pop(item.id, None)
        elif item[0] == "fine":
            if item[2] != self.sessione:
                return
            time.sleep(self.out.latency)
            dette, self.dette = self.dette, []
            if self.turno_finito is not None:
                self.turno_finito(item[1], dette)
        elif item[0] == "pcm":
            _, pcm, rate, fatto = item
            try:
                if rate != self.out.rate and self.out.rate and len(pcm) < rate * 4:
                    # Un segnale a un'altra frequenza si ricampiona: riaprire l'uscita
                    # costerebbe l'attacco con le cuffie Bluetooth
                    from ..suoni import ricampiona
                    x = np.frombuffer(pcm, "<i2").astype(np.float32) / 32768
                    pcm = (ricampiona(x, rate, self.out.rate) * 32767).astype("<i2").tobytes()
                    rate = self.out.rate
                if rate != self.out.rate:
                    self.out.apri(rate)
                step = int(rate * self.BLOCCO_S) * 2
                self._pcm_fino = time.monotonic() + len(pcm) / 2 / max(1, rate)
                for i in range(0, len(pcm), step):
                    if self.out.scrivi(pcm[i:i + step]) is False:
                        break
                time.sleep(self.out.latency)
            finally:
                self._pcm_fino = max(self._pcm_fino, time.monotonic())
                fatto.set()

    def _scartata(self, f: _Frase) -> bool:
        return f.sessione != self.sessione or f.turno <= self.scarta_fino

    def _riproduci(self, f: _Frase):
        if self._scartata(f):
            return
        if f.rate != self.out.rate:
            self.out.apri(f.rate)
        mentions_name = dice_nome(self.cfg, f.testo)
        self._now_text = f.testo
        self.in_corso = True
        self._frase_id = f.id
        step = int(f.rate * self.BLOCCO_S) * 2
        pos, intera = 0, False
        try:
            while True:
                if self._scartata(f):
                    break
                with f.cond:
                    fine = time.monotonic() + self.ATTESA_PEZZO_S
                    # Un blocco intero, o quel che resta se la frase è arrivata tutta
                    while (len(f.buf) - pos < step and not f.completa
                           and not self._scartata(f)):
                        resto = fine - time.monotonic()
                        if resto <= 0:
                            break
                        f.cond.wait(resto)
                    blocco = bytes(f.buf[pos:pos + step])
                if self._scartata(f):
                    break
                if not blocco:
                    intera = f.completa
                    break
                if self.out.scrivi(blocco) is False:
                    break                 # uscita guasta: la frase non è stata detta
                if pos == 0 and self.suonata is not None:
                    try:
                        self.suonata(f.id, self.out.latency)
                    except Exception:  # noqa: BLE001 — la misura non ferma mai la voce
                        pass
                self.ultima_scrittura = time.monotonic()
                self.byte_riprodotti += len(blocco)
                pos += len(blocco)
                if pos >= f.totale:
                    intera = True
                    break
        finally:
            self.in_corso = False
            self._now_text = ""
            self._frase_fine = time.monotonic() + self.out.latency
        if intera and f.testo:
            self.dette.append(f.testo)
        if mentions_name:
            self._name_until = time.monotonic() + self.out.latency + 0.8


# ───────────────────────────── SATELLITE ─────────────────────────────
class Satellite:
    """Un satellite: si collega al server, si abbina se serve, ascolta e riproduce."""

    def __init__(self, cfg, sorgente=None, apri_uscita=None, log=print, apri_schermo=None,
                 rilevatore=None, esecutore=None):
        from ..audio import Listener
        self.cfg = cfg
        self.log = log
        # Sul satellite Silero VAD con onnxruntime: torch (centinaia di MB, secondi
        # all'avvio) non serve per decidere se in 32 ms c'è voce
        if str(getattr(cfg, "vad_motore", "auto")).lower() == "auto":
            cfg.vad_motore = "onnx"
        if rilevatore is None:
            from ..wakeword import WakeWordDetector
            # Senza wake word acustica il satellite dovrebbe mandare al server tutto ciò che
            # sente: non parte (il modello è in wakeword/modelli, ~3 MB)
            rilevatore = WakeWordDetector(cfg.wake_model)
        self.wake = rilevatore
        # Il file del modello in uso: se il server ne usa un altro (wake word cambiata, 04/10)
        # e qui c'è, si passa a quello (_cambia_wake)
        self._wake_file = os.path.basename(str(getattr(cfg, "wake_model", "") or ""))
        self._wake_su_misura = not hasattr(rilevatore, "fx")     # quello finto delle prove
        # I classificatori in uso (il primo è quello principale) e la cartella dei modelli,
        # dove arrivano anche quelli mandati dal server (modalità cambiata a voce, 05/10)
        self._wake_in_uso = [self._wake_file]
        self._cartella_wake = os.path.dirname(os.path.abspath(str(getattr(cfg, "wake_model",
                                                                          "") or "x")))
        self._crea_rilevatore = None              # funzione(principale, altri); None = vero
        self._wake_voluti: tuple[str, list[str]] | None = None
        self._wake_annunciati: dict[str, dict] = {}   # nome → {sha256, byte} dal server
        self._wake_in_arrivo: dict | None = None      # l'intestazione wake_file in attesa
        self._wake_chiesti: set[str] = set()
        # Suoni di inizio e fine ascolto mandati dal server nel benvenuto: {tipo: (pcm, rate)}
        self.suoni: dict = {}
        self.listener = Listener(cfg, sorgente=sorgente)
        self.listener.on_wake = lambda: self._suona("inizio")
        # L'esecutore del PC (None = quello di questo PC se è Windows; False = nessuno, come
        # su Linux; le prove ne passano uno con un PC finto)
        if esecutore is None:
            from .esecutore import crea_esecutore
            esecutore = crea_esecutore(cfg, log=log)
        self.esecutore = esecutore or None
        # Protocollo: il 2 annuncia l'esecutore; davanti a un server vecchio si torna all'1
        self.versione = P.VERSIONE
        self.player = Riproduttore(cfg, apri_uscita, self._turno_finito,
                                   suonata=self._suonata)
        self.apri_schermo = apri_schermo          # None = Edge/Chromium; funzione(url) nelle prove
        self.cred_path = percorso(cfg, cfg.satellite_credenziali)
        self.cred = self._leggi_cred()
        self.ws = None
        self._ws_lock = threading.Lock()
        self.primo = True                         # il saluto si dice solo la prima volta
        self.eco = None
        self.satellite = {}
        self.collegato = threading.Event()
        self._fermo = threading.Event()
        self._lavoro = None                       # thread di ascolto o di veglia
        self._wakeup = threading.Event()
        self._stop_veglia = threading.Event()
        self._id_corrente = None
        self._seed = None
        self._esiti: queue.Queue = queue.Queue()
        self._schermo_aperto = False
        self._ponte = None                        # ponte TLS verso la pagina in HTTPS
        # Misure (prove e terminale)
        self.audio_inviato = 0                    # byte di audio del microfono mandati
        self.ricevuti = 0                         # byte ricevuti dal server (voce compresa)
        self.frasi_inviate = 0
        self.connessioni = 0
        self.codice = None                        # ultimo codice di abbinamento mostrato
        # Gli ultimi comandi e risultati, con l'istante (diagnostica e prove)
        self.traccia = collections.deque(maxlen=300)
        # Gli ultimi ascolti aperti (17/10, #5): (istante, id, con la wake word, fino a quando
        # sveglia). Dice alle prove quando il satellite si è riaddormentato, senza attese fisse
        self.ascolti = collections.deque(maxlen=50)
        # Aggiornamenti automatici: solo se avviato da un'installazione (avvio.py della pagina
        # /satellite), mai dal repository (aggiorna.py)
        from .aggiorna import Aggiornatore, Installazione
        self.installazione = Installazione.da_ambiente()
        self.aggiornatore = (Aggiornatore(self.installazione, log=log)
                             if self.installazione is not None
                             and getattr(cfg, "satellite_aggiornamenti", True) else None)
        self.riavvio = False                      # uscire con 75: c'è una versione nuova
        self._ultimo_audio = 0.0                  # monotonic dell'ultimo audio mandato
        self._ultimo_lid = None                   # l'ascolto di quell'audio (stanza: legame)
        # L'ascolto della stanza (13/10, protocollo 3, satellite/stanza.py): nasce la prima
        # volta che il server lo accende per questo satellite; spento non costa niente
        self.stanza = None

    # ── credenziali ──
    def _leggi_cred(self) -> dict:
        try:
            d = json.loads(self.cred_path.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _salva_cred(self):
        tmp = self.cred_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cred, ensure_ascii=False, indent=2), encoding="utf-8")
        if os.name != "nt":
            os.chmod(tmp, 0o600)
        os.replace(tmp, self.cred_path)

    # ── rete ──
    def _url(self, path: str) -> str:
        return str(self.cfg.satellite_server).rstrip("/") + path

    def _connetti(self, path: str):
        from websockets.sync.client import connect
        url = self._url(path)
        ctx = None
        if url.startswith("wss://"):
            # Certificato del server senza CA (fatto con --certificato): niente verifica del
            # nome, si controlla l'impronta SHA-256 prima di mandare qualunque cosa
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            # websockets legge da un thread suo e scrive da altri: con l'SSLSocket normale la
            # richiesta di apertura ogni tanto non partiva e dopo 5 s arrivava «timed out
            # while waiting for handshake response» (03/10, calliope/tls_sicuro.py)
            from ..tls_sicuro import sicuro
            sicuro(ctx)
        ws = connect(url, ssl=ctx, compression=None, open_timeout=5, max_size=2 ** 22,
                     ping_interval=10, ping_timeout=10, close_timeout=2,
                     user_agent_header=None, logger=P.logger_websockets("client"))
        impronta = ""
        if ctx is not None:
            impronta = P.impronta_der(ws.socket.getpeercert(binary_form=True))
            attesa = P.norm_impronta(self.cfg.satellite_impronta or self.cred.get("impronta"))
            if attesa and P.norm_impronta(impronta) != attesa:
                ws.close(1008, "certificato inatteso")
                raise ImprontaDiversa(impronta)
        return ws, impronta

    def _manda(self, **campi) -> bool:
        return self._manda_raw(P.testo(**campi))

    def _manda_raw(self, dati) -> bool:
        ws = self.ws
        if ws is None:
            return False
        try:
            with self._ws_lock:
                ws.send(dati)
            return True
        except Exception:  # noqa: BLE001 — se ne accorge il ciclo di ricezione
            return False

    # ── ciclo principale ──
    def esegui(self):
        """Fino a `ferma()`: abbinamento se serve, sessione, riconnessione."""
        if self.aggiornatore is not None:
            threading.Thread(target=self._sorveglia_aggiornamento, name="riavvio",
                             daemon=True).start()
        self._esegui()

    def _esegui(self):
        tentativi = 0
        while not self._fermo.is_set():
            prima, self._collegato_dal = self.connessioni, None
            try:
                if not self.cred.get("token"):
                    self.abbina()
                    tentativi = 0
                    continue
                self._sessione()
                tentativi = 0
            except ImprontaDiversa as e:
                self.log(f"[SATELLITE] Il certificato del server è cambiato (impronta {e}): "
                         f"non mando il token. Se l'hai rifatto tu, abbina di nuovo il "
                         f"satellite (cancella {self.cred_path.name}); altrimenti controlla "
                         f"la rete.")
                self._attendi(60)
                continue
            except NonAbbinato:
                self.log("[SATELLITE] Il server non riconosce questo satellite (revocato o mai "
                         "abbinato lì): chiedo un abbinamento nuovo.")
                self.cred.pop("token", None)
                self._salva_cred()
                continue
            except Exception as e:  # noqa: BLE001 — rete giù, server spento, VPN spenta
                if not self._fermo.is_set():
                    rcvd = getattr(e, "rcvd", None)
                    if getattr(rcvd, "code", None) == P.CHIUSO_SOSTITUITO:
                        self.log("[SATELLITE] Un altro satellite si è collegato con le stesse "
                                 f"credenziali ({self.cred_path.name}, cartella copiata o due "
                                 f"programmi avviati?) e il server ha tenuto quello: riprovo tra "
                                 f"{self.ATTESA_SOSTITUITO_S:.0f} s.")
                        tentativi = 0
                        self._attendi(self.ATTESA_SOSTITUITO_S)
                        continue
                    dal = getattr(self, "_collegato_dal", None)
                    if (self.connessioni > prima and dal is not None
                            and time.monotonic() - dal >= self.SESSIONE_STABILE_S):
                        # La sessione era collegata da un po' (17/10, #5): una caduta dopo
                        # riparte dalla prima attesa. Prima valevano i tentativi falliti di
                        # prima del collegamento: dopo un riavvio lungo del server, la caduta
                        # seguente aspettava 10–15 s invece di 1
                        tentativi = 0
                    attesa = ATTESE_RICONNESSIONE[min(tentativi, len(ATTESE_RICONNESSIONE) - 1)]
                    self.log(f"[SATELLITE] Server non raggiungibile ({_breve(e)}): riprovo tra "
                             f"{attesa} s")
                    tentativi += 1
                    self._attendi(attesa)
            finally:
                self._chiudi_sessione()

    def ferma(self):
        self._fermo.set()
        self._wakeup.set()
        self._stop_veglia.set()
        if self._ponte is not None:
            self._ponte.ferma()
        ws = self.ws
        if ws is not None:
            try:
                ws.close(1000, "satellite spento")
            except Exception:  # noqa: BLE001
                pass

    SESSIONE_STABILE_S = SESSIONE_STABILE_S
    ATTESA_SOSTITUITO_S = ATTESA_SOSTITUITO_S

    def _attendi(self, s: float):
        self._fermo.wait(s)

    def abbina(self):
        """Chiede un codice al server e aspetta che chi amministra lo scriva lì."""
        ws, impronta = self._connetti(P.PERCORSO_ABBINA)
        self.ws = ws
        try:
            # satellite_schermo_personale: solo una richiesta, la conferma chi abbina
            ws.send(P.testo(tipo="abbina", versione=self.versione, nome=socket.gethostname(),
                            personale=(getattr(self.cfg, "satellite_schermo_personale", "")
                                       or None)))
            while not self._fermo.is_set():
                m = P.leggi(self._ricevi_o_versione(ws))
                if m.get("tipo") == "codice":
                    self.codice = m["codice"]
                    c = m["codice"]
                    self.log("")
                    self.log(f"[SATELLITE] Codice di abbinamento:  {c[:3]} {c[3:]}")
                    pers = getattr(self.cfg, "satellite_schermo_personale", "")
                    self.log(f"            Sul server: python -m calliope.satellite --abbina "
                             f"{c} --stanza <stanza>"
                             + (f" --personale {pers}" if pers else "")
                             + f"   (vale {m.get('scade_s', 600) // 60} minuti)")
                    if impronta:
                        self.log(f"            Impronta del server: {impronta[:23]}… "
                                 f"(la stampa anche --abbina sul server: devono coincidere)")
                elif m.get("tipo") == "abbinato":
                    self.cred = {"token": m["token"], "server": self.cfg.satellite_server,
                                 "impronta": impronta or None,
                                 "satellite": m.get("satellite") or {}}
                    self._salva_cred()
                    s = m.get("satellite") or {}
                    self.log(f"[SATELLITE] Abbinato come «{s.get('nome')}» (stanza "
                             f"{s.get('stanza')}). Token salvato in {self.cred_path.name}.")
                    return
                elif m.get("tipo") == "scaduto":
                    self.log("[SATELLITE] Codice scaduto: ne chiedo un altro.")
                    return
        finally:
            self.ws = None
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass

    def _sessione(self):
        from websockets.exceptions import ConnectionClosed
        ws, impronta = self._connetti(P.PERCORSO_AUDIO)
        self.ws = ws
        esecutore = (self.esecutore.descrizione()
                     if self.esecutore is not None and self.versione >= 2 else None)
        ws.send(P.testo(tipo="ciao", versione=self.versione, token=self.cred["token"],
                        primo=self.primo, nome=socket.gethostname(), esecutore=esecutore,
                        modalita=True, wake_presenti=self._wake_presenti(),
                        stanza=self.versione >= 3))
        try:
            # Il server risponde quando Calliope ha finito di avviarsi (modelli, saluto)
            m = P.leggi(self._ricevi_o_versione(ws, timeout=180))
        except ConnectionClosed as e:
            code = e.rcvd.code if e.rcvd is not None else None
            if code == P.CHIUSO_TOKEN:
                raise NonAbbinato() from e
            raise
        if m.get("tipo") != "benvenuto":
            raise ConnectionError("risposta inattesa dal server")
        for k, v in (m.get("parametri") or {}).items():
            if k in P.PARAMETRI:
                setattr(self.cfg, k, v)
        self._wake_chiesti.clear()
        self._fine_turno()
        self._modalita(m, parametri=False)
        self._stanza(m.get("stanza"))
        self.satellite = m.get("satellite") or {}
        self.player.nuova_sessione()
        self.connessioni += 1
        self._collegato_dal = time.monotonic()
        self.log(f"[SATELLITE] Collegato a {self.cfg.satellite_server} come «"
                 f"{self.satellite.get('nome')}» (stanza {self.satellite.get('stanza')})")
        if m.get("saluto"):
            dati = ws.recv(timeout=10)
            tipo, rate, pcm = P.apri_binario(dati if isinstance(dati, bytes) else b"")
            if tipo == P.SALUTO:
                self.eco = self._saluto(pcm, rate)
        self.primo = False
        ws.send(P.testo(tipo="pronto", eco=self.eco))
        self.collegato.set()
        if self.installazione is not None:
            # Una versione in prova si conferma qui: si è ricollegata e il server l'ha accolta
            self.installazione.conferma(self.log)
            if self.aggiornatore is not None and m.get("aggiornamento"):
                self.aggiornatore.proponi(m["aggiornamento"], str(self.cfg.satellite_server),
                                          impronta)
        # A ogni sessione, anche con la pagina già aperta: se sul server il certificato degli
        # schermi è stato rifatto (calliope schermi --certificato --forza), l'impronta nuova
        # arriva qui e il ponte la usa. Fino al 03/10 si chiedeva solo la prima volta: dopo il
        # riavvio del server con il certificato nuovo il ponte rifiutava la pagina per sempre
        if m.get("schermi") and str(self.cfg.satellite_schermo).lower() != "no":
            ws.send(P.testo(tipo="schermo", token=self.cred.get("schermo_token") or ""))
        while not self._fermo.is_set():
            msg = ws.recv()
            self.ricevuti += len(msg)
            if isinstance(msg, bytes):
                tipo, ident, pcm = P.apri_binario(msg)
                if tipo == P.VOCE:
                    self.player.pezzo(ident, pcm)
                elif tipo == P.FILE and self.esecutore is not None:
                    self.esecutore.file_pezzo(ident, pcm)
                elif tipo == P.MODELLO:
                    self._ricevi_modello(pcm)
                continue
            self._comando(P.leggi(msg))

    # ── modalità (05/10): wake word e suoni del server, alla connessione e quando cambiano ──
    GENERICI = ("melspectrogram.onnx", "embedding_model.onnx")

    def _wake_presenti(self) -> list[str]:
        """I classificatori della wake word in questa cartella (per il «ciao»)."""
        try:
            nomi = os.listdir(self._cartella_wake)
        except OSError:
            return []
        return sorted(n for n in nomi if P.nome_modello(n) and n not in self.GENERICI)[:40]

    def _fine_turno(self):
        """La fine del turno System 1 (14/10): con «attiva» dal server e il modello qui
        (fine_turno_modello, o models/fine_turno/), il Listener chiude prima le frasi finite;
        altrimenti silenzio fisso. Non ferma mai la sessione."""
        try:
            from ..system1.fine_turno import prepara_listener
            prepara_listener(self.listener, self.cfg, self.log)
        except Exception as e:  # noqa: BLE001
            self.listener.fine_turno = None
            self.log(f"[SATELLITE] Fine del turno System 1 non disponibile ({e}): silenzio "
                     f"fisso.")

    def _modalita(self, m: dict, parametri: bool = True):
        """Benvenuto o messaggio «modalita»: parametri (parole che svegliano), suoni e
        modelli della wake word del server."""
        if parametri:
            for k, v in (m.get("parametri") or {}).items():
                if k in P.PARAMETRI:
                    setattr(self.cfg, k, v)
        from ..suoni import da_benvenuto
        self.suoni = da_benvenuto(m.get("suoni"))
        self._wake_annunciati = {}
        altri = []
        for x in m.get("wake_modelli") or []:
            if (isinstance(x, dict) and P.nome_modello(x.get("nome"))
                    and x["nome"] not in self.GENERICI):
                self._wake_annunciati[x["nome"]] = {"sha256": str(x.get("sha256") or ""),
                                                    "byte": x.get("byte")}
                altri.append(x["nome"])
        principale = os.path.basename(str(m.get("wake_modello") or ""))
        self._cambia_wake(principale, [n for n in altri if n != principale])
        if m.get("tipo") == "modalita":
            parola = getattr(self.cfg, "wake_word", None) or getattr(self.cfg, "name", "")
            self.log(f"[SATELLITE] Modalità cambiata sul server: wake word «{parola}», suoni "
                     f"{'accesi' if self.suoni else 'spenti'}.")

    def _cambia_wake(self, nome, altri=()):
        """Il server usa altri modelli della wake word (wake_word cambiata, modalità startrek:
        «computer.onnx», con «calliope.onnx» insieme): si usano quelli che sono qui, nella
        cartella del modello di sempre. Uno che manca si chiede al server (wake_richiesta:
        arriva con SHA-256 e dimensione controllati); intanto si tiene il rilevatore di prima
        (il server accetta anche il nome dell'assistente, wake_anche_nome) e lo si dice."""
        nome = os.path.basename(str(nome or ""))
        if not nome or not nome.endswith(".onnx") or nome in self.GENERICI:
            return
        if self._wake_su_misura and self._crea_rilevatore is None:
            return                                # il rilevatore finto delle prove
        self._wake_voluti = (nome, list(altri))
        voluti = [nome, *altri]
        mancano = [n for n in voluti
                   if not os.path.isfile(os.path.join(self._cartella_wake, n))]
        for n in mancano:
            self._chiedi_modello(n)
        if nome in mancano:
            if nome != self._wake_file:
                self.log(f"[SATELLITE] Il server usa la wake word «{nome}», che qui manca "
                         f"({self._cartella_wake}): resto su «{self._wake_file}»"
                         + (" e la chiedo al server." if nome in self._wake_chiesti else "."))
            return
        presenti = [n for n in voluti if n not in mancano]
        if presenti == self._wake_in_uso:
            return
        try:
            percorsi = [os.path.join(self._cartella_wake, n) for n in presenti]
            if self._crea_rilevatore is not None:
                nuovo = self._crea_rilevatore(percorsi[0], percorsi[1:])
            else:
                from ..wakeword import WakeWordDetector
                nuovo = WakeWordDetector(percorsi[0], extra=percorsi[1:])
        except Exception as e:  # noqa: BLE001
            self.log(f"[SATELLITE] La wake word «{nome}» non si carica ({e}): resto su "
                     f"«{self._wake_file}».")
            return
        self.wake = nuovo
        self._wake_file, self._wake_in_uso = nome, presenti
        self.log(f"[SATELLITE] Wake word del server: {', '.join(f'«{n}»' for n in presenti)}.")

    def _chiedi_modello(self, nome: str):
        """Chiede al server un classificatore che qui manca (una volta per connessione)."""
        if nome in self._wake_chiesti or nome not in self._wake_annunciati:
            return
        info = self._wake_annunciati[nome]
        try:
            byte = int(info.get("byte") or 0)
        except (TypeError, ValueError):
            byte = 0
        if not info.get("sha256") or not 0 < byte <= P.MODELLO_MAX:
            return
        self._wake_chiesti.add(nome)
        self._manda(tipo="wake_richiesta", nome=nome)

    def _ricevi_modello(self, dati: bytes):
        """Il file del classificatore dopo «wake_file»: si tiene solo se nome, dimensione e
        SHA-256 sono quelli annunciati dal server, e si scrive accanto agli altri modelli."""
        import hashlib
        testa, self._wake_in_arrivo = self._wake_in_arrivo, None
        if not testa:
            return
        nome = P.nome_modello(testa.get("nome"))
        atteso = self._wake_annunciati.get(nome or "") or {}
        sha = hashlib.sha256(dati).hexdigest()
        if (nome is None or nome in self.GENERICI or len(dati) > P.MODELLO_MAX
                or len(dati) != testa.get("byte") or sha != testa.get("sha256")
                or sha != atteso.get("sha256")):
            self.log(f"[SATELLITE] Modello della wake word «{nome}» rifiutato: dimensione o "
                     "impronta diverse da quelle annunciate.")
            return
        dest = os.path.join(self._cartella_wake, nome)
        tmp = dest + ".part"
        try:
            with open(tmp, "wb") as f:
                f.write(dati)
            os.replace(tmp, dest)
        except OSError as e:
            self.log(f"[SATELLITE] Non riesco a salvare il modello «{nome}» ({e}): resto su "
                     f"«{self._wake_file}».")
            return
        self.log(f"[SATELLITE] Ricevuto dal server il modello della wake word «{nome}» "
                 f"({len(dati) // 1024} kB).")
        if self._wake_voluti is not None:
            self._cambia_wake(*self._wake_voluti)

    def _suona(self, tipo: str):
        """Il suono d'inizio o fine ascolto, sulle casse di qui (subito: niente rete)."""
        s = self.suoni.get(tipo)
        if s is not None:
            self.player.suona(*s)

    def _ricevi_o_versione(self, ws, timeout=None):
        """ws.recv; se il server chiude per la versione del protocollo, si scende alla 1
        (server non ancora aggiornato: niente esecutore) o, già lì, si avvisa e si aspetta."""
        from websockets.exceptions import ConnectionClosed
        try:
            return ws.recv(timeout=timeout)
        except ConnectionClosed as e:
            if (e.rcvd.code if e.rcvd is not None else None) == P.CHIUSO_VERSIONE:
                if self.versione > 1:
                    # Una versione alla volta (13/10, la 3): davanti a un server con la 2 si
                    # perde solo l'ascolto della stanza, con la 1 anche l'esecutore del PC
                    self.versione -= 1
                    self.log("[SATELLITE] Il server ha il protocollo vecchio: mi collego con la "
                             f"versione {self.versione}"
                             + (" (senza l'ascolto della stanza)" if self.versione == 2 else
                                " (senza l'esecutore del PC)")
                             + ": aggiorna Calliope sul server per averla completa.")
                else:
                    self.log("[SATELLITE] Server e satellite hanno versioni diverse del "
                             "protocollo: aggiorna il codice del satellite.")
                    self._attendi(60)
            raise

    def _saluto(self, pcm: bytes, rate: int) -> float:
        """Dice il saluto e intanto misura quanto il microfono sente la sua voce."""
        stop, eco = threading.Event(), {}
        t = threading.Thread(target=lambda: eco.setdefault(
            "q", self.listener.measure_echo(stop)), daemon=True)
        t.start()
        self.player.suona(pcm, rate).wait(timeout=len(pcm) / 2 / rate + 5)
        stop.set()
        t.join(timeout=2)
        q = eco.get("q", 1.0)
        self.log(f"[SATELLITE] Eco sentita durante il saluto: {q * 100:.0f} % dei frame")
        return q

    def _chiudi_sessione(self):
        self.collegato.clear()
        ws, self.ws = self.ws, None
        if ws is not None:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass
        # Ascolto e veglia in corso: finiscono (l'ascolto appena nessuno parla)
        self._wakeup.set()
        self._stop_veglia.set()
        self.player.svuota()
        if self.stanza is not None:
            self.stanza.imposta(None)             # senza server la stanza non ascolta
        if self.esecutore is not None:
            self.esecutore.azzera_consegne()
        if self._lavoro is not None:
            self._lavoro.join(timeout=2)

    # ── comandi dal server ──
    def _comando(self, m: dict):
        t = m.get("tipo")
        if t not in ("frase",):
            self.traccia.append((time.monotonic(), t, m.get("id")))
        if t == "frase":
            # Calliope risponde: finisce la misura della ripresa dopo la frase (pause.py)
            ferma = getattr(self.listener, "ferma_ripresa", None)
            if ferma is not None:
                ferma()
            self.player.frase(int(m["turno"]), int(m["id"]), m.get("testo") or "",
                              int(m["rate"]), int(m["byte"]))
        elif t == "fine_turno":
            self.player.fine_turno(int(m["id"]))
        elif t == "ferma":
            self.player.ferma(int(m.get("turno") or 0))
        elif t == "ascolta":
            self._avvia(self._ascolta, m)
        elif t == "sveglia":
            if m.get("id") == self._id_corrente:
                self._wakeup.set()
        elif t == "tocco":
            # «Parla» dalla pagina dello schermo personale (27/10): per qualche secondo si
            # ascolta senza il nome, come «Parla» del telefono; il suono d'inizio lo dice
            secondi = max(1.0, min(30.0, float(m.get("secondi") or 8.0)))
            self.listener.sveglio_fino = time.monotonic() + secondi
            # Mentre Calliope parla il tocco la interrompe, come sul telefono: la voce si ferma
            # subito e la veglia finisce con «interruzione» (revisione della PR #255)
            wid = getattr(self, "_veglia_id", None)
            if wid is not None:
                self._toccata = wid
                self.player.ferma()
                self._stop_veglia.set()
            self._suona("inizio")
        elif t == "veglia":
            self._avvia(self._veglia, m)
        elif t == "fine_veglia":
            if m.get("id") == self._id_corrente:
                self._stop_veglia.set()
        elif t == "esito_voce":
            self._esiti.put(m)
        elif t == "modalita":
            self._modalita(m)
        elif t == "stanza":
            self._stanza(m)
        elif t == "wake_file":
            if m.get("errore"):
                self.log(f"[SATELLITE] Il server non manda il modello «{m.get('nome')}»: "
                         f"{m.get('errore')}.")
            else:
                self._wake_in_arrivo = m
        elif t == "schermo":
            self._apri_schermo(m)
        elif t == "pc_richiesta":
            if self.esecutore is None:
                self._manda(tipo="pc_esito", id=m.get("id"),
                            errore="questo satellite non controlla il PC")
            else:
                self.esecutore.richiesta(m, self._manda)
        elif t == "file_richiesta":
            if self.esecutore is None:
                self._manda(tipo="file_dati", id=m.get("id"), ok=False,
                            errore="questo satellite non manda file")
            else:
                self.esecutore.file_richiesta(m, self._manda, self._manda_raw)
        elif t == "file":
            if self.esecutore is None:
                self._manda(tipo="file_esito", id=m.get("id"), ok=False,
                            errore="questo satellite non riceve documenti")
            else:
                self.esecutore.file_inizio(m, self._manda)

    # ── la stanza (13/10, protocollo 3, satellite/stanza.py) ──
    def _stanza(self, stato):
        """Lo stato della stanza dal server: accesa crea l'ascolto e apre il rubinetto sul
        microfono; spenta (o assente) lo chiude."""
        attiva = isinstance(stato, dict) and bool(stato.get("attiva"))
        if self.stanza is None:
            if not attiva:
                return
            from .stanza import AscoltoStanza
            self.stanza = AscoltoStanza(
                self.cfg, self._manda, self._manda_raw, self.player.occupato,
                ultimo_comando=lambda: (self._ultimo_audio, self._ultimo_lid)
                if self._ultimo_lid is not None else None, log=self.log,
                voce=self.player.voce_ora)
        self.stanza.imposta(stato if isinstance(stato, dict) else None)
        self.listener.rubinetto = self.stanza.frame if attiva else None

    def _turno_finito(self, ident: int, dette: list[str]):
        self._manda(tipo="turno_finito", id=ident, dette=dette)

    def _suonata(self, ident: int, uscita_s: float):
        """La frase `ident` comincia a suonare: il server segna l'ora (più il ritardo
        dell'uscita audio, `uscita_s`). Un server vecchio ignora il tipo."""
        self._manda(tipo="suona", id=ident, uscita_s=round(float(uscita_s or 0.0), 3))

    def _avvia(self, fn, m: dict):
        prima = self._lavoro
        if prima is not None and prima.is_alive():
            # Il server non chiede due cose insieme; se succede (riconnessione), la vecchia
            # finisce prima
            self._wakeup.set()
            self._stop_veglia.set()
            prima.join(timeout=5)
        self._id_corrente = m.get("id")
        self._wakeup.clear()
        self._stop_veglia.clear()
        self._lavoro = threading.Thread(target=fn, args=(m,), daemon=True)
        self._lavoro.start()

    def _ascolta(self, m: dict):
        lid = m["id"]
        L = self.listener
        resto = m.get("sveglia_per_s")
        awake_until = float("inf") if resto is None else time.monotonic() + float(resto)
        seed, self._seed = (self._seed if m.get("seed") else None), None

        def on_audio(frames):
            pcm = P.a_pcm(frames)
            self._ultimo_audio, self._ultimo_lid = time.monotonic(), lid
            if self._manda_raw(P.binario(P.AUDIO, lid, pcm)):
                self.audio_inviato += len(pcm)

        L.on_audio = on_audio
        L.on_speech_end = lambda: self._manda(tipo="scartata", id=lid)
        # Solo misura (07/10, calliope/pause.py): qualcuno ricomincia a parlare entro 2 s dalla
        # fine della frase? Le casse di qui (segnale di fine, risposta) non contano. Un server
        # vecchio ignora il tipo «ripresa»
        L.ripresa_muto = self.player.occupato
        L.ripresa_avviso = lambda s, lid=lid: self._manda(tipo="ripresa", id=lid, dopo_s=s)
        self.ascolti.append((time.monotonic(), lid, bool(m.get("wake")), awake_until))
        try:
            audio = L.listen(self.wake if m.get("wake") else None, awake_until, seed=seed,
                             wakeup=self._wakeup)
        finally:
            L.on_audio = None
            L.on_speech_end = None
        self.traccia.append((time.monotonic(), "fine_ascolto", lid))
        if audio is None:
            self._manda(tipo="nessuna_frase", id=lid)
            return
        if getattr(L, "chiusura", None) != "lunga":
            # Frase presa: il segnale prima della rete. Non al tetto (10/10): la persona parla
            # ancora e il server ascolta subito il seguito (Ciclo._seguito_del_tetto)
            self._suona("fine")
        self.frasi_inviate += 1
        # Le pause dentro la frase, il parlato e come si è chiusa (07/10, solo misura): campi
        # facoltativi, un server vecchio li ignora
        self._manda(tipo="frase_finita", id=lid, fa_s=round(time.monotonic() - L.started_at, 3),
                    woke=bool(L.woke), wake_score=round(float(L.wake_score), 3),
                    campioni=len(audio), pause_ms=list(getattr(L, "pause_ms", []) or []),
                    parlato_ms=getattr(L, "parlato_ms", None),
                    chiusura=getattr(L, "chiusura", None),
                    # System 1 «attiva» (14/10): com'è andata la fine del turno, solo numeri
                    **({"fine_turno": L.fine_turno_esito}
                       if getattr(L, "fine_turno_esito", None) else {}))

    def _veglia(self, m: dict):
        wid = m["id"]
        self._veglia_id = wid               # «tocco» mentre Calliope parla la interrompe (27/10)
        voice_ok = None
        if m.get("livello_b"):
            def voice_ok(audio, wid=wid):
                # L'impronta la calcola il server (CAM++ e le persone registrate sono lì)
                while not self._esiti.empty():
                    self._esiti.get_nowait()
                if not self._manda_raw(P.binario(P.VERIFICA, wid, P.a_pcm(audio))):
                    return False
                try:
                    r = self._esiti.get(timeout=3.0)
                except queue.Empty:
                    return False
                return bool(r.get("ok")) and r.get("id") == wid
        seed = self.listener.watch_for_name(self.wake, self._stop_veglia,
                                            self.player.saying_name, voice_ok=voice_ok)
        if seed:
            # Subito qui, senza aspettare il server: è questo che tiene il barge-in entro
            # un blocco da 100 ms anche con la VPN in mezzo
            self.player.ferma()
            self._seed = seed
            self._manda(tipo="interruzione", id=wid, motivo="nome sentito")
        elif getattr(self, "_toccata", None) == wid:
            # «Parla» dalla pagina mentre Calliope parlava (27/10): come il tocco del telefono
            self._toccata = None
            self._manda(tipo="interruzione", id=wid, motivo="tocco")
        else:
            self._manda(tipo="veglia_finita", id=wid)
        if getattr(self, "_veglia_id", None) == wid:
            self._veglia_id = None

    # ── aggiornamenti (aggiorna.py) ──
    QUIETE_S = 20.0                     # niente voce né frasi da tanto: si può riavviare

    def inattivo(self) -> bool:
        """Nessuno sta parlando con Calliope: niente riproduzione né audio mandato da
        QUIETE_S secondi, e la connessione c'è (la versione nuova deve ricollegarsi)."""
        ora = time.monotonic()
        return (self.collegato.is_set() and not self.player.in_corso
                and ora - self.player.ultima_scrittura > self.QUIETE_S
                and ora - self._ultimo_audio > self.QUIETE_S)

    def _sorveglia_aggiornamento(self):
        while not self._fermo.wait(2.0):
            if self.aggiornatore.pronto.is_set() and self.inattivo():
                self.log("[AGGIORNA] Mi riavvio sulla versione nuova.")
                self.riavvio = True
                self.ferma()
                return

    # ── schermo ──
    def _apri_schermo(self, m: dict):
        if not m.get("porta"):
            self.log(f"[SATELLITE] Niente schermo: {m.get('motivo') or 'non disponibile'}")
            return
        if m.get("token"):
            if m["token"] != self.cred.get("schermo_token") and self._schermo_aperto:
                # Token nuovo per lo stesso schermo (05/10: il server lo rinnova se quello
                # conservato qui non vale più): la pagina aperta con il vecchio riceverebbe
                # 401 e chiederebbe un codice, cioè un altro abbinamento. Si riapre
                self.log("[SATELLITE] Lo schermo ha un token nuovo: riapro la pagina.")
                self._schermo_aperto = False
            self.cred["schermo_token"] = m["token"]
            self._salva_cred()
        token = self.cred.get("schermo_token")
        host = urlsplit(self.cfg.satellite_server).hostname or "127.0.0.1"
        if m.get("locale") and host not in ("127.0.0.1", "localhost", "::1"):
            self.log("[SATELLITE] La pagina degli schermi sul server ascolta solo lì "
                     "(schermi_indirizzo: 127.0.0.1): sul server metti schermi_indirizzo: "
                     "0.0.0.0 in calliope.locale.yaml per vederla da qui.")
            return
        if m.get("https"):
            # Pagina in HTTPS con il certificato autofirmato del server (02/10): il browser
            # passa dal ponte TLS su 127.0.0.1, che verifica l'impronta (schermi/ponte.py)
            from ..schermi.ponte import PonteTLS
            try:
                if self._ponte is None or self._ponte.porta != int(m["porta"]):
                    if self._ponte is not None:
                        self._ponte.ferma()
                    self._ponte = PonteTLS(host, int(m["porta"]), m.get("impronta") or "",
                                           log=self.log)
                    self._schermo_aperto = False       # porta locale nuova: pagina da riaprire
                elif self._ponte.aggiorna_impronta(m.get("impronta") or ""):
                    self.log("[SATELLITE] Il certificato della pagina degli schermi è cambiato "
                             "sul server: il ponte usa quello nuovo.")
            except (ValueError, OSError) as e:
                self.log(f"[SATELLITE] Niente schermo: il ponte verso la pagina non parte "
                         f"({_breve(e)})")
                return
            url = f"{self._ponte.url}/#t={token}"
        else:
            if ":" in host:
                host = f"[{host}]"
            url = f"http://{host}:{m['porta']}/#t={token}"
        if self._schermo_aperto:
            return                  # la pagina aperta si ricollega da sola, anche dal ponte
        self._schermo_aperto = True
        if self.apri_schermo is not None:
            self.apri_schermo(url)
            return
        apri_pagina(url, str(self.cfg.satellite_schermo).lower())
        self.log("[SATELLITE] Pagina degli schermi aperta.")


def apri_pagina(url: str, modo: str = "finestra"):
    """Edge (Windows) o Chromium (Linux) con la pagina degli schermi. «finestra»: una finestra
    senza barre accanto alle altre; «kiosk»: schermo intero. Il token sta dopo «#»: non va al
    server nelle richieste e non resta nella barra (la pagina lo toglie)."""
    import subprocess
    if sys.platform == "win32":
        args = (f'--kiosk "{url}" --edge-kiosk-type=fullscreen --no-first-run'
                if modo == "kiosk" else f'--app="{url}" --no-first-run')
        os.startfile("msedge", arguments=args)      # Edge si trova da App Paths
        return
    exe = next((e for e in ("chromium", "chromium-browser", "google-chrome")
                if __import__("shutil").which(e)), None)
    if exe is None:
        print(f"[SATELLITE] Apri a mano: {url.split('#')[0]} (il token è in satellite.json)")
        return
    extra = ["--kiosk", url] if modo == "kiosk" else [f"--app={url}"]
    subprocess.Popen([exe, "--no-first-run", *extra], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


def _breve(e: Exception) -> str:
    s = str(e) or type(e).__name__
    return s if len(s) < 120 else s[:117] + "…"
