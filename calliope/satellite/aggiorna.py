"""
Aggiornamenti automatici di un satellite installato dalla pagina /satellite (03/10/2026).

Solo per i satelliti avviati da `avvio.py` di un'installazione (installazione/avvio.py: le
variabili CALLIOPE_SATELLITE_INSTALLAZIONE e CALLIOPE_SATELLITE_VERSIONE). Il satellite del
repository (`python -m calliope.satellite` sul portatile di sviluppo) non si aggiorna mai da
solo: lì il codice lo cambia git.

Il server annuncia nel benvenuto la versione del pacchetto (impronta del contenuto), il suo
SHA-256 e la dimensione, sulla connessione già autenticata e con l'impronta del certificato
controllata. Se la versione è diversa da quella in uso, e non è stata rifiutata da poco:
  1. il pacchetto si scarica dalla stessa porta del server (HTTPS, impronta del certificato
     controllata prima di mandare la richiesta) e si verifica lo SHA-256;
  2. `avvio.py prepara --prova` lo prepara accanto (venv con uv, verifica a secco): la
     versione in uso non cambia;
  3. quando nessuno sta parlando il satellite esce con il codice 75 e avvio.py passa alla
     versione nuova; questa, appena il server le dà il benvenuto, lo conferma
     (`confermata-<versione>`); senza conferma entro il tempo avvio.py torna indietro.
"""

import hashlib
import http.client
import json
import os
import ssl
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from . import protocollo as P

RIAVVIA = 75                       # lo stesso di installazione/avvio.py
RIFIUTO_S = 6 * 3600.0
TRA_TENTATIVI_S = 3600.0           # un aggiornamento fallito qui si riprova dopo un'ora
BYTE_MAX = 64 * 1024 * 1024


class Installazione:
    """L'installazione da cui è partito questo satellite (avvio.py), o None."""

    def __init__(self, radice: Path, versione: str):
        self.radice = Path(radice)
        self.versione = versione

    @classmethod
    def da_ambiente(cls, env=None) -> "Installazione | None":
        env = os.environ if env is None else env
        radice = env.get("CALLIOPE_SATELLITE_INSTALLAZIONE")
        versione = env.get("CALLIOPE_SATELLITE_VERSIONE")
        if not radice or not versione or not (Path(radice) / "avvio.py").is_file():
            return None
        return cls(Path(radice), versione)

    def conferma(self, log=print) -> bool:
        """Questa versione è in prova e si è appena collegata: lo dice ad avvio.py."""
        try:
            p = json.loads((self.radice / "prova.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(p, dict) or p.get("versione") != self.versione:
            return False
        (self.radice / f"confermata-{self.versione}").write_text(
            time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
        log(f"[AGGIORNA] Versione {self.versione} collegata al server: confermata.")
        return True

    def rifiutata(self, versione: str) -> bool:
        try:
            d = json.loads((self.radice / "rifiutate.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        quando = d.get(versione) if isinstance(d, dict) else None
        return isinstance(quando, (int, float)) and time.time() - quando < RIFIUTO_S


def scarica(server_url: str, percorso: str, impronta: str, dest: Path, sha256: str,
            byte_max: int = BYTE_MAX, timeout: float = 30.0):
    """Scarica `percorso` dal server dei satelliti (lo stesso host e la stessa porta di
    satellite_server) in `dest` e controlla lo SHA-256. Con wss:// il certificato deve avere
    l'impronta attesa, controllata prima di mandare la richiesta. ValueError se qualcosa
    non va (il file a metà si cancella)."""
    u = urlsplit(server_url)
    if not u.hostname or u.scheme not in ("ws", "wss"):
        raise ValueError(f"indirizzo del server non valido: {server_url}")
    porta = u.port or (443 if u.scheme == "wss" else 80)
    if u.scheme == "wss":
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE         # niente CA: vale l'impronta, qui sotto
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        conn = http.client.HTTPSConnection(u.hostname, porta, context=ctx, timeout=timeout)
    else:
        conn = http.client.HTTPConnection(u.hostname, porta, timeout=timeout)
    dest = Path(dest)
    tmp = dest.with_name(dest.name + ".part")
    try:
        conn.connect()
        if u.scheme == "wss":
            visto = P.norm_impronta(P.impronta_der(conn.sock.getpeercert(binary_form=True)))
            if not impronta or visto != P.norm_impronta(impronta):
                raise ValueError("il certificato del server non è quello abbinato")
        conn.request("GET", percorso, headers={"User-Agent": "calliope-satellite"})
        r = conn.getresponse()
        if r.status != 200:
            raise ValueError(f"il server risponde {r.status}")
        h, n = hashlib.sha256(), 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "wb") as f:
            while True:
                blocco = r.read(1 << 16)
                if not blocco:
                    break
                n += len(blocco)
                if n > byte_max:
                    raise ValueError("pacchetto troppo grande")
                h.update(blocco)
                f.write(blocco)
        if h.hexdigest() != sha256.lower():
            raise ValueError("lo SHA-256 del pacchetto non è quello annunciato")
        os.replace(tmp, dest)
    except (OSError, http.client.HTTPException) as e:
        raise ValueError(f"download non riuscito ({e})") from e
    finally:
        conn.close()
        tmp.unlink(missing_ok=True)


class Aggiornatore:
    """Prepara in secondo piano la versione annunciata dal server; `pronto` si accende
    quando c'è da riavviarsi."""

    def __init__(self, inst: Installazione, log=print, prepara=None):
        self.inst = inst
        self.log = log
        self.pronto = threading.Event()
        self.in_corso = False
        self._tentativi: dict[str, float] = {}
        self._prepara = prepara or self._prepara_con_avvio

    def proponi(self, annuncio: dict, server_url: str, impronta: str) -> bool:
        """Parte (in un thread) se l'annuncio è una versione diversa da questa, non rifiutata
        da poco e non già tentata nell'ultima ora. True se è partito."""
        v = str((annuncio or {}).get("versione") or "")
        sha = str(annuncio.get("sha256") or "")
        if (not v or v == self.inst.versione or self.in_corso or self.pronto.is_set()
                or len(sha) != 64 or self.inst.rifiutata(v)):
            return False
        ultimo = self._tentativi.get(v)
        if ultimo is not None and time.monotonic() - ultimo < TRA_TENTATIVI_S:
            return False
        self._tentativi[v] = time.monotonic()
        self.in_corso = True
        threading.Thread(target=self._lavora, args=(dict(annuncio), server_url, impronta),
                         name="aggiorna", daemon=True).start()
        return True

    def _lavora(self, annuncio: dict, server_url: str, impronta: str):
        v = annuncio["versione"]
        try:
            self.log(f"[AGGIORNA] Il server ha la versione {v} del satellite (qui "
                     f"{self.inst.versione}): la scarico e la preparo accanto.")
            dest = self.inst.radice / "scaricati" / f"{v}.zip"
            byte = int(annuncio.get("byte") or 0)
            scarica(server_url, str(annuncio.get("percorso") or "/installa/pacchetto.zip"),
                    impronta, dest, annuncio["sha256"],
                    byte_max=min(BYTE_MAX, byte or BYTE_MAX))
            self._prepara(dest, annuncio["sha256"])
            dest.unlink(missing_ok=True)
            self.log(f"[AGGIORNA] Versione {v} pronta: mi riavvio appena nessuno parla.")
            self.pronto.set()
        except Exception as e:  # noqa: BLE001 — l'aggiornamento non ferma mai il satellite
            self.log(f"[AGGIORNA] Aggiornamento a {v} non riuscito ({e}): resto sulla "
                     f"versione {self.inst.versione} e riprovo più tardi.")
        finally:
            self.in_corso = False

    def _prepara_con_avvio(self, pacchetto: Path, sha256: str):
        """`avvio.py prepara --prova` dell'installazione, con questo Python."""
        r = subprocess.run([sys.executable, str(self.inst.radice / "avvio.py"), "prepara",
                            "--pacchetto", str(pacchetto), "--sha256", sha256, "--prova"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=1800)
        if r.returncode != 0:
            righe = (r.stderr or r.stdout or "").strip().splitlines()
            raise ValueError(righe[-1] if righe else f"codice {r.returncode}")
