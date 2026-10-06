"""
Il protocollo tra Calliope (server) e un satellite: messaggi JSON e audio binario su un
WebSocket (docs/ricerche/2026-10-02-satellite.md). Solo libreria standard e numpy: lo
importano entrambi i lati.

Messaggi di testo: un oggetto JSON con «tipo». Messaggi binari: un byte di tipo, 4 byte con
un identificativo (intero senza segno, big-endian) e il PCM int16 mono:

    b"A" + id ascolto + PCM 16 kHz      satellite → server: la frase, mentre si parla
    b"V" + id verifica + PCM 16 kHz     satellite → server: parlato durante una risposta,
                                        per l'impronta (barge-in di livello B)
    b"T" + id frase + PCM della voce    server → satellite: un pezzo di una frase da dire
    b"S" + frequenza + PCM              server → satellite: il saluto, alla connessione
    b"F" + id consegna + byte del file  server → satellite: un pezzo di un documento
                                        (versione 2, esecutore del PC)
    b"G" + id richiesta + byte del file satellite → server: un pezzo di un file del PC
                                        chiesto per un lavoro dell'agente (03/10)
    b"M" + 0 + byte del file            server → satellite: un classificatore della wake
                                        word che il satellite non ha (05/10, modalità)

Il satellite apre la connessione (nessuna porta in ascolto sul portatile) e si presenta con
il token nel primo messaggio, dopo aver controllato l'impronta del certificato: così il token
non parte mai verso un server sbagliato. Senza token si può solo chiedere un abbinamento.

Il PCM non si comprime: 16 kHz × 16 bit = 256 kbit/s verso il server e solo mentre si parla
a Calliope; la voce (22 050 Hz con serena-high) 353 kbit/s verso il satellite, in pezzi da
0,2 s mandati appena pronti. In VPN e in LAN la banda c'è; Opus vorrebbe una libreria nativa
(libopus) da verificare su Windows ARM, e la latenza conta più dei byte.
"""

import json
import struct

import numpy as np

# Versione 2 (03/10/2026): l'esecutore del PC. Il satellite lo annuncia nel «ciao»
# (`esecutore`: nome, capacità, app, consegna dei file); il server manda `pc_richiesta`
# (id, metodo, argomenti, scadenza_s) e riceve `pc_esito` (id, esito o errore); un
# documento arriva come `file` (id, nome, estensione, byte, sha256, sostituisci, mtime) più
# i pezzi binari b"F", e il satellite risponde `file_esito`. Il server accetta anche la
# versione 1 (un satellite vecchio: niente esecutore); un satellite nuovo davanti a un
# server vecchio riprova con la 1.
# Sempre nella versione 2 (03/10, i file della persona all'agente): un satellite che sa
# mandare file lo dice nel «ciao» (`esecutore.invio`); il server manda `file_richiesta` (id,
# maniglia di una ricerca, max_byte, estensioni, scadenza_s) e il satellite risponde con
# `file_dati` (id, ok, nome, estensione, byte, sha256, oppure errore) seguito dai pezzi b"G".
# Sempre nella versione 2 (05/10, la modalità cambiata a voce): un satellite che la segue
# senza riconnettersi lo dice nel «ciao» (`modalita: true`, con `wake_presenti`: i
# classificatori della wake word che ha); il server manda allora `modalita` (parametri,
# wake_modello, wake_modelli, suoni: gli stessi campi del benvenuto) quando cambia. Un
# satellite a cui manca un classificatore lo chiede con `wake_richiesta` (nome); il server
# risponde `wake_file` (nome, sha256, byte, oppure errore) seguito da un b"M" con il file.
# Un satellite vecchio ignora i tipi che non conosce e prende la modalità alla connessione dopo.
# Sempre nella versione 2 (06/10, la latenza che si sente): il satellite manda `suona` (id della
# frase, uscita_s: il ritardo della sua uscita audio) quando comincia a riprodurre una frase; il
# server la segna (`prima_voce_s` nel registro dei turni). Un server vecchio ignora il tipo, un
# satellite vecchio non lo manda: niente misura, nient'altro cambia.
VERSIONE = 2
VERSIONI = (1, 2)                      # quelle che il server accetta
PERCORSO_AUDIO = "/satellite"          # connessione con il token
PERCORSO_ABBINA = "/abbina"            # senza token: solo la richiesta di abbinamento

AUDIO, VERIFICA, VOCE, SALUTO, FILE = b"A", b"V", b"T", b"S", b"F"
FILE_SU = b"G"                         # satellite → server: un file per l'agente
MODELLO = b"M"                         # server → satellite: un classificatore della wake word
MODELLO_MAX = 4 * 1024 * 1024          # i classificatori sono ~0,9 MB; oltre non si mandano
# Pezzi di un file verso il satellite: piccoli, perché tra un pezzo e l'altro passino le
# frasi della voce (stessa connessione, un messaggio alla volta)
PEZZO_FILE = 64 * 1024
FILE_MAX = 64 * 1024 * 1024            # un documento più grande non si consegna
# Cosa il satellite accetta di salvare (documenti e risultati degli agenti, sempre file nuovi
# nella cartella Calliope dei Documenti) e cosa accetta di mandare all'agente. Niente
# eseguibili né script che Windows esegue con un doppio clic (.js, .vbs, .bat, .cmd, .hta):
# un risultato con quelle estensioni arriva come «.txt» (calliope/agenti/servizio.py)
ESTENSIONI_TESTO = ("py", "txt", "md", "csv", "tsv", "json", "html", "htm", "css", "ps1",
                    "psm1", "sql", "toml", "yaml", "yml", "ini", "cfg", "xml", "log")
# Dal 03/10 (analisi di sicurezza, rete, difetto 1) anche script e pagine (.py, .ps1, .htm)
# arrivano come «<nome>.py.txt»: con un doppio clic, o con «apri», Windows li eseguirebbe
ESTENSIONI_ATTIVE = ("py", "html", "htm", "ps1", "psm1")
ESTENSIONI_RICEVUTE = ("docx", "xlsx", "pdf") + tuple(e for e in ESTENSIONI_TESTO
                                                      if e not in ESTENSIONI_ATTIVE)
ESTENSIONI_INVIO = ("docx", "xlsx", "pdf", "js") + ESTENSIONI_TESTO
# I metodi che il server può chiedere all'esecutore del satellite (nient'altro: elenco
# consentito, argomenti controllati sul satellite)
METODI_PC = ("volume_leggi", "volume_imposta", "volume_muto", "media_info", "media_comando",
             "luminosita_leggi", "luminosita_imposta", "batteria", "schermo", "blocca",
             "programmi", "avvia", "cerca", "apri", "cattura")
PEZZO_VOCE_S = 0.2                     # pezzi della frase verso il satellite
ATTESA_CIAO_S = 5.0                    # il primo messaggio deve arrivare entro

# Codici di chiusura (4000–4999: dell'applicazione)
CHIUSO_TOKEN = 4401                    # token mancante, sbagliato o revocato
CHIUSO_SOSTITUITO = 4409               # è arrivato un altro satellite (o lo stesso, di nuovo)
CHIUSO_VERSIONE = 4426                 # protocollo diverso: va aggiornato un lato

# Parametri che il server manda al satellite all'avvio: la taratura resta in un posto solo
# (calliope.yaml del server), mentre dispositivi e attenzioni per le cuffie sono del satellite
PARAMETRI = ("name", "wake_word", "wake_anche_nome", "sample_rate", "vad_threshold", "silence_ms", "preroll_ms",
             "min_speech_ms", "max_utterance_s", "wake_threshold", "wake_consecutive",
             "barge_in_threshold", "barge_in_seed_s", "barge_in_voice_min_s",
             "barge_in_echo_max")


def testo(**campi) -> str:
    return json.dumps(campi, ensure_ascii=False, separators=(",", ":"))


def leggi(messaggio: str) -> dict:
    """Un messaggio di testo: dict con «tipo», oppure {} se non è JSON valido."""
    try:
        d = json.loads(messaggio)
    except (TypeError, ValueError):
        return {}
    return d if isinstance(d, dict) and isinstance(d.get("tipo"), str) else {}


def nome_modello(nome) -> str | None:
    """Il nome di un classificatore della wake word se è sicuro come nome di file nella
    cartella dei modelli («computer.onnx»), altrimenti None: niente percorsi né altro."""
    import re
    n = str(nome or "")
    return n if re.fullmatch(r"[A-Za-z0-9_-]{1,40}\.onnx", n) else None


def binario(tipo: bytes, ident: int, pcm: bytes) -> bytes:
    return tipo + struct.pack(">I", ident & 0xFFFFFFFF) + pcm


def apri_binario(dati: bytes) -> tuple[bytes, int, bytes]:
    """(tipo, id, pcm); tipo b"" se il messaggio è troppo corto."""
    if len(dati) < 5:
        return b"", 0, b""
    return dati[:1], struct.unpack(">I", dati[1:5])[0], dati[5:]


def a_pcm(frames) -> bytes:
    """Frame float32 in [-1, 1] → PCM int16 (quello che si manda in rete)."""
    x = np.concatenate(frames) if isinstance(frames, (list, tuple)) else np.asarray(frames)
    return (np.clip(x, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def da_pcm(pcm: bytes) -> np.ndarray:
    """PCM int16 → float32 in [-1, 1], come i frame del microfono locale."""
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


def impronta_der(der: bytes) -> str:
    """SHA-256 di un certificato (DER), in esadecimale con i due punti come la stampa
    openssl: AB:CD:…"""
    import hashlib
    h = hashlib.sha256(der).hexdigest().upper()
    return ":".join(h[i:i + 2] for i in range(0, len(h), 2))


def norm_impronta(testo_: str | None) -> str:
    """«ab:cd…», «ABCD…», «sha256 Fingerprint=AB:CD…» → «ABCD…» (solo le cifre esadecimali)."""
    t = str(testo_ or "")
    if "=" in t:
        t = t.split("=", 1)[1]
    return "".join(ch for ch in t.upper() if ch in "0123456789ABCDEF")


# ── log di websockets ──
def _di_rete(exc: BaseException | None) -> bool:
    """L'eccezione (o una della sua catena) è una caduta di rete: timeout, socket chiuso,
    connessione WebSocket chiusa senza saluto."""
    try:
        from websockets.exceptions import ConnectionClosed
    except ImportError:            # pragma: no cover — senza websockets non c'è nessun log
        ConnectionClosed = ()
    visti = set()
    while exc is not None and id(exc) not in visti:
        visti.add(id(exc))
        if isinstance(exc, (OSError, EOFError, ConnectionClosed)):   # TimeoutError compreso
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def logger_websockets(lato: str):
    """Il logger da dare a websockets (serve, connect). Quando la rete cade (VPN spenta, Wi-Fi
    perso) il thread del keepalive scrive «keepalive ping failed» con il traceback intero
    (TimeoutError, ConnectionClosedError 1011): è una caduta attesa, e la dice già una riga
    di Calliope («[SATELLITE] studio scollegato (rete)», 02/10). Quei record si scartano;
    gli altri errori, quelli veri, restano."""
    import logging
    log = logging.getLogger(f"calliope.satellite.websockets.{lato}")
    if not any(isinstance(f, _FiltroRete) for f in log.filters):
        log.addFilter(_FiltroRete())
    return log


class _FiltroRete:
    def filter(self, record) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        return not _di_rete(exc)
