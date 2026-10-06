"""
Tunnel SSH verso l'Ollama della DGX (02/10/2026).

    ssh -N -L 127.0.0.1:<porta_locale>:127.0.0.1:<porta_remota> <alias>
        -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 …

- **OpenSSH di Windows** (o qualunque `ssh` nel PATH; `CALLIOPE_SSH` per le prove). Utente,
  indirizzo e chiave stanno in `.ssh\\config` sotto l'alias: qui si passa solo l'alias.
- **Nessuna richiesta interattiva**: `BatchMode=yes` fa fallire subito una password, una
  passphrase che ssh-agent non ha, un'impronta dell'host sconosciuta. Lo stdin è chiuso.
- `ExitOnForwardFailure=yes`: se la porta locale è occupata ssh esce invece di restare
  collegato senza tunnel. Il tunnel è pronto quando la porta locale accetta connessioni.
- Ollama sulla DGX resta su 127.0.0.1: non è esposto alla rete dell'ufficio.
- Aperto a richiesta (`assicura`) o all'avvio in secondo piano (`apri_in_secondo_piano`),
  **riaperto se cade** (un thread lo sorveglia, con attese crescenti), chiuso all'uscita.
  Su Windows il processo sta in un job object con KILL_ON_JOB_CLOSE: se Calliope muore,
  ssh muore con lei e non tiene occupata la porta (winjob.py).
- **Mai stampare** l'host, l'utente o l'indirizzo: l'errore di ssh («utente@10.0.0.5:
  Permission denied») si riduce a un codice (`classifica`), e il testo non si conserva.
"""

import re
import socket
import subprocess
import threading
import time

from . import winjob

# Codici d'errore del collegamento, dal testo di ssh. L'ordine conta: il primo che combacia.
_REGOLE = [
    ("porta_locale", r"address already in use|cannot listen to port|could not request local "
                     r"forwarding|bind \["),
    ("host_sconosciuto", r"host key verification failed|remote host identification has "
                         r"changed|no matching host key|host key for .* has changed"),
    ("chiave", r"permission denied|too many authentication failures|no more authentication "
               r"methods|authentications that can continue|load key .*: (invalid|bad)|"
               r"passphrase"),
    ("nome", r"could not resolve hostname|name or service not known|nodename nor servname|"
             r"no such host|host sconosciuto|temporary failure in name resolution"),
    ("rifiutato", r"connection refused"),
    ("vpn", r"timed out|no route to host|network is unreachable|host is unreachable|"
            r"connection reset|connection closed by|kex_exchange_identification|"
            r"broken pipe|operation timed out"),
    ("config_ssh", r"bad configuration option|bad owner or permissions|"
                   r"unsupported option|garbage at end of line|keyword .* extra arguments"),
]


def classifica(stderr: str, codice_uscita: int | None = None) -> str:
    """Il codice dell'errore di ssh dal suo testo (minuscolo). Mai il testo stesso."""
    t = (stderr or "").lower()
    for code, pat in _REGOLE:
        if re.search(pat, t):
            return code
    return "ssh_errore"


def porta_in_uso(porta: int, host: str = "127.0.0.1", timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection((host, porta), timeout=timeout):
            return True
    except OSError:
        return False


class Tunnel:
    """Il processo ssh del tunnel, con lo stato del collegamento.

    `codice`: «chiuso», «apertura», «ok», «caduto», o un codice d'errore di `classifica`
    («vpn», «nome», «chiave», «host_sconosciuto», «porta_locale», «rifiutato»,
    «config_ssh», «ssh_errore»), più «ssh_mancante» e «timeout»."""

    # Attese tra un tentativo e l'altro quando il tunnel cade (secondi)
    ATTESE = (2.0, 5.0, 15.0, 30.0, 60.0)

    def __init__(self, alias: str, porta_locale: int, porta_remota: int,
                 timeout_s: float = 5.0, ssh: str | None = None, log=print):
        self.alias, self.lp, self.rp = alias, int(porta_locale), int(porta_remota)
        self.timeout_s = float(timeout_s)
        self.ssh = ssh
        self.log = log
        self.proc: subprocess.Popen | None = None
        self.job = None
        self.codice = "chiuso"
        self.quando = 0.0              # monotonic dell'ultimo cambio di stato
        self.tentativi = 0             # aperture riuscite (per le prove e la diagnosi)
        self._lock = threading.Lock()  # una sola apertura alla volta
        self._stderr: list[str] = []
        self._voluto = False           # aperto almeno una volta e non chiuso: va tenuto su
        self._fermo = threading.Event()
        self._guardia: threading.Thread | None = None

    # ── comando ──
    def comando(self) -> list[str]:
        t = max(1, int(round(self.timeout_s)))
        return [self.ssh or "ssh", "-N",
                "-L", f"127.0.0.1:{self.lp}:127.0.0.1:{self.rp}",
                "-o", "BatchMode=yes",
                "-o", "ExitOnForwardFailure=yes",
                "-o", f"ConnectTimeout={t}",
                "-o", "ServerAliveInterval=15",
                "-o", "ServerAliveCountMax=3",
                "-o", "ConnectionAttempts=1",
                # Niente agent forwarding, X11 o pseudo-terminale: solo il tunnel
                "-o", "ForwardAgent=no", "-o", "ForwardX11=no", "-T",
                "--", self.alias]

    def _stato(self, codice: str):
        self.codice, self.quando = codice, time.monotonic()

    def vivo(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def aperto(self) -> bool:
        return self.codice == "ok" and self.vivo()

    # ── apertura ──
    def assicura(self, timeout: float | None = None) -> str:
        """Apre il tunnel se non è aperto (aspettando al più `timeout`), e restituisce il
        codice: «ok» o il motivo per cui non si apre."""
        if self.aperto():
            return "ok"
        # Un'altra apertura in corso (la guardia, o il primo tentativo all'avvio) dura al più
        # il suo tempo massimo + 1 s: si aspetta quella, poi si guarda com'è andata
        if not self._lock.acquire(timeout=2 * (timeout or self.timeout_s) + 2.0):
            return self.codice if self.codice != "ok" else "apertura"
        try:
            if self.aperto():
                return "ok"
            return self._apri(timeout)
        finally:
            self._lock.release()

    def apri_in_secondo_piano(self):
        """All'avvio di Calliope: il primo tentativo non ritarda niente."""
        self._voluto = True
        threading.Thread(target=self.assicura, daemon=True, name="tunnel-apri").start()
        self._avvia_guardia()

    def _apri(self, timeout: float | None) -> str:
        self._ferma_processo()
        self._voluto = True
        self._avvia_guardia()
        if not self.ssh:
            self._stato("ssh_mancante")
            return self.codice
        # La porta locale occupata da un altro programma: con ExitOnForwardFailure ssh
        # uscirebbe comunque, ma qui si sa subito perché (e un Ollama locale su quella porta
        # verrebbe scambiato per la DGX)
        if porta_in_uso(self.lp):
            self._stato("porta_locale")
            return self.codice
        self._stato("apertura")
        self._stderr = []
        kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            if winjob.disponibile():
                self.job = winjob.JobObject()          # muore con Calliope
                self.proc = winjob.avvia_nel_job(self.comando(), self.job,
                                                 creationflags=winjob.CREATE_NO_WINDOW, **kw)
            else:
                # Linux: niente PR_SET_PDEATHSIG, che scatta alla fine del *thread* che ha
                # creato il figlio (qui un thread breve, «tunnel-apri»): ssh morirebbe
                # subito. Sotto systemd lo ferma il cgroup del servizio (02/10)
                self.proc = subprocess.Popen(self.comando(), start_new_session=True, **kw)
        except FileNotFoundError:
            self._stato("ssh_mancante")
            return self.codice
        except OSError as e:
            self.log(f"[AGENTI] il client ssh non parte ({type(e).__name__})")
            self._stato("ssh_errore")
            return self.codice
        threading.Thread(target=self._leggi_stderr, args=(self.proc,), daemon=True,
                         name="tunnel-stderr").start()
        limite = time.monotonic() + (timeout if timeout is not None else self.timeout_s) + 1.0
        while time.monotonic() < limite:
            rc = self.proc.poll()
            if rc is not None:
                time.sleep(0.05)                     # l'ultimo pezzo di stderr
                self._stato(classifica("\n".join(self._stderr), rc))
                self._ferma_processo()
                return self.codice
            if porta_in_uso(self.lp, timeout=0.1):
                self.tentativi += 1
                self._stato("ok")
                return self.codice
            time.sleep(0.1)
        # Né collegato né uscito: di solito la VPN è spenta e ssh aspetta la rete
        self._ferma_processo()
        self._stato("timeout")
        return self.codice

    def _leggi_stderr(self, proc):
        try:
            for raw in iter(proc.stderr.readline, b""):
                line = raw.decode("utf-8", "replace").strip()
                if line:
                    self._stderr = (self._stderr + [line])[-20:]
        except (OSError, ValueError):
            pass

    # ── sorveglianza ──
    def _avvia_guardia(self):
        if self._guardia is None or not self._guardia.is_alive():
            self._fermo.clear()
            self._guardia = threading.Thread(target=self._guarda, daemon=True,
                                             name="tunnel-guardia")
            self._guardia.start()

    def _guarda(self):
        """Se il tunnel cade lo si riapre, con attese crescenti; finché non si chiude."""
        falliti = 0
        while not self._fermo.wait(1.0):
            if not self._voluto:
                continue
            if self.codice == "ok" and not self.vivo():
                self.log("[AGENTI] il tunnel verso la DGX è caduto: lo riapro")
                self._stato("caduto")
                falliti = 0
            if self.codice in ("ok", "apertura"):
                falliti = 0
                continue
            # Mai aperto (VPN spenta dall'avvio): niente tentativi ogni minuto per tutto il
            # giorno; ci riprova il prossimo lavoro
            if not self.tentativi:
                continue
            attesa = self.ATTESE[min(falliti, len(self.ATTESE) - 1)]
            if time.monotonic() - self.quando < attesa:
                continue
            codice = self.assicura()
            falliti = 0 if codice == "ok" else falliti + 1

    # ── chiusura ──
    def _ferma_processo(self):
        proc, job = self.proc, self.job
        self.proc, self.job = None, None
        if job is not None:
            job.termina()
            job.close()
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()
        if proc is not None and proc.stderr is not None:
            try:
                proc.stderr.close()
            except OSError:
                pass

    def chiudi(self):
        self._voluto = False
        self._fermo.set()
        with self._lock:
            self._ferma_processo()
            self._stato("chiuso")


def descrivi_comando(t: Tunnel) -> str:
    """Il comando per i messaggi: con l'alias, che non è un dato personale."""
    return "ssh " + " ".join(t.comando()[1:])
