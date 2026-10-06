"""
Un'esecuzione di un'estensione (04/10/2026): un container usa-e-getta, il protocollo
JSON-RPC su stdin/stdout, le richieste alla porta stretta e la sospensione per la conferma.

Il thread dell'esecuzione legge le righe del container. Una richiesta «calliope/<azione>» va
alla porta (porta.py), che risponde subito (sicura o vietata) oppure chiede una conferma:
allora l'esecuzione passa «in_attesa», chi aspetta (il tool, nel turno a voce) riceve la
domanda, e il thread resta fermo finché la persona non decide (`decidi`) o scade il tempo.
Il tempo di lavoro (`limiti.tempo_s`) si ferma mentre si aspetta la persona; un orologio a
parte uccide il container se lo supera. Conta dal momento in cui il runtime nel container è
pronto (`notifications/calliope/pronta`): l'avvio del container (docker run, un'immagine
fredda, il disco della DGX occupato) ha il suo margine, `AVVIO_S` (06/10, prova e2e: alla
prima chiamata dopo l'approvazione un'estensione con 5 s di tetto si è fermata).
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import threading
import time
from pathlib import Path

_RUNTIME = Path(__file__).with_name("_ospite.py")
_LAVORO_C = "/lavoro"
_RUNTIME_C = "/opt/calliope/calliope_estensione.py"
MAX_RIGA = 1_000_000
# Il tempo massimo per far partire il container (non conta nel tetto del manifesto)
AVVIO_S = 20.0
PRONTA = "notifications/calliope/pronta"


class Esecuzione:
    def __init__(self, ident: str, nome: str, versione: int, manifesto: dict, cartella: Path,
                 argomenti: dict, persona=None, persona_nome=None, livello: str = "familiare",
                 isolamento=None, porta=None, conferma_s: float = 120.0, log=print,
                 avvio_s: float | None = None):
        self.id = ident
        self.nome = nome
        self.versione = versione
        self.manifesto = manifesto
        self.cartella = Path(cartella)
        self.argomenti = dict(argomenti or {})
        self.persona, self.persona_nome, self.livello = persona, persona_nome, livello
        self.isolamento = isolamento
        self.porta = porta
        self.conferma_s = float(conferma_s)
        self.log = log
        lim = manifesto.get("limiti") or {}
        self.tempo_s = float(lim.get("tempo_s", 10))
        self.memoria_mb = int(lim.get("memoria_mb", 256))
        # in_corso | in_attesa (una conferma) | finita | errore | negata
        self.stato = "in_corso"
        self.risultato: dict | None = None
        self.errore: str = ""
        self.richiesta: dict | None = None     # la richiesta che aspetta la conferma
        self.decisioni: list[dict] = []        # ogni richiesta alla porta, con l'esito
        self.stderr = ""
        self.inizio = time.monotonic()
        self.avvio_s = float(AVVIO_S if avvio_s is None else avvio_s)
        self.pronta_t: float | None = None     # quando il runtime nel container è pronto
        self.attesa_s = 0.0
        self._cambio = threading.Condition()
        self._decisione: dict | None = None
        self._proc = None
        self._nome_c = "calliope-estensione-" + secrets.token_hex(6)
        self.da_annunciare = False     # il tool non l'ha aspettata: il risultato si annuncia
        from ..guardrail import StatoEsecuzione
        self.storia = StatoEsecuzione()

    # ── per chi aspetta ──
    def avvia(self):
        threading.Thread(target=self._corri, daemon=True, name=f"estensione-{self.id}").start()
        threading.Thread(target=self._orologio, daemon=True,
                         name=f"estensione-orologio-{self.id}").start()

    def attendi(self, timeout: float) -> str:
        """Aspetta fino a `timeout` che l'esecuzione finisca o chieda una conferma. Lo stato."""
        fine = time.monotonic() + timeout
        with self._cambio:
            while self.stato == "in_corso" or (self.stato == "in_attesa"
                                                and self.richiesta is None):
                resto = fine - time.monotonic()
                if resto <= 0:
                    break
                self._cambio.wait(resto)
            return self.stato

    def decidi(self, si: bool, chi=None, sempre: bool = False) -> bool:
        """La risposta della persona alla conferma in corso. False se non c'è nessuna attesa."""
        with self._cambio:
            if self.stato != "in_attesa" or self.richiesta is None:
                return False
            self._decisione = {"si": bool(si), "chi": chi, "sempre": bool(sempre)}
            self.stato = "in_corso"
            self.richiesta = None
            self._cambio.notify_all()
            return True

    def lavoro_s(self) -> float:
        """Il tempo di lavoro dell'estensione: da quando il runtime è pronto, senza le attese
        della persona (0 finché il container parte)."""
        if self.pronta_t is None:
            return 0.0
        return time.monotonic() - self.pronta_t - self.attesa_s

    def avvio_trascorso_s(self) -> float:
        return (self.pronta_t or time.monotonic()) - self.inizio

    def _pronta(self):
        if self.pronta_t is None:
            self.pronta_t = time.monotonic()

    # ── il container ──
    def comando(self) -> list[str]:
        iso = self.isolamento
        mem = max(64, self.memoria_mb)
        try:
            utente = f"{os.getuid()}:{os.getgid()}"
            if os.getuid() == 0:
                utente = "65534:65534"
        except AttributeError:
            utente = "65534:65534"
        if "," in str(self.cartella) or "," in str(_RUNTIME):
            raise RuntimeError("la cartella dell'estensione non può contenere virgole")
        dentro = int(self.tempo_s + self.conferma_s * 3 + self.avvio_s) + 10
        cmd = [*(iso.docker or ["docker"]), "run", "--rm", "-i", "--name", self._nome_c,
               "--label", "calliope.estensione=1", "--pull", "never", "--log-driver", "none",
               "--network", "none", "--hostname", "estensione", "--read-only",
               "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=8m",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--user", utente, "--memory", f"{mem}m", "--memory-swap", f"{mem}m",
               "--ulimit", f"data={mem * 1024 * 1024}", "--pids-limit", "16",
               "--cpus", "1", "--cpu-shares", "256",
               "--mount", f"type=bind,src={self.cartella},dst={_LAVORO_C},readonly",
               "--mount", f"type=bind,src={_RUNTIME},dst={_RUNTIME_C},readonly",
               "-w", _LAVORO_C]
        for k, v in {"HOME": "/tmp", "TMPDIR": "/tmp", "PYTHONIOENCODING": "utf-8",
                     "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1",
                     "OPENBLAS_NUM_THREADS": "1"}.items():
            cmd += ["-e", f"{k}={v}"]
        cmd += [iso.immagine or "calliope-sandbox", "timeout", "-s", "KILL", str(dentro),
                "python", "-I", "-B", "-X", "utf8", _RUNTIME_C, _LAVORO_C]
        return cmd

    def _cambia(self, stato: str, **campi):
        with self._cambio:
            self.stato = stato
            for k, v in campi.items():
                setattr(self, k, v)
            self._cambio.notify_all()

    def _scrivi(self, msg: dict):
        p = self._proc
        if p is None or p.stdin is None:
            return
        try:
            p.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
            p.stdin.flush()
        except (OSError, ValueError):
            pass

    def _corri(self):
        kw = dict(stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if os.name != "nt":
            from ..agenti.sandbox import _figlio_docker
            kw.update(start_new_session=True, preexec_fn=_figlio_docker)
        try:
            self._proc = subprocess.Popen(self.comando(), **kw)
        except (OSError, RuntimeError) as e:
            self._cambia("errore", errore=f"il container non parte: {e}")
            return
        err = []

        def leggi_err():
            try:
                for riga in self._proc.stderr:
                    if sum(len(x) for x in err) < 20_000:
                        err.append(riga.decode("utf-8", "replace"))
            except (OSError, ValueError):
                pass
        threading.Thread(target=leggi_err, daemon=True).start()
        self._scrivi({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": self.nome, "arguments": self.argomenti}})
        finito = False
        try:
            while True:
                riga = self._proc.stdout.readline(MAX_RIGA)
                if not riga:
                    break
                try:
                    msg = json.loads(riga.decode("utf-8", "replace"))
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                self._pronta()             # anche un runtime senza l'avviso è partito
                if msg.get("method") == PRONTA:
                    continue
                if msg.get("id") == 1 and ("result" in msg or "error" in msg):
                    self._fine(msg)
                    finito = True
                    break
                metodo = str(msg.get("method") or "")
                if metodo.startswith("calliope/") and msg.get("id") is not None:
                    self._richiesta(msg["id"], metodo[len("calliope/"):],
                                    msg.get("params") or {})
        finally:
            self._ferma()
            self.stderr = "".join(err)[-4000:]
            if not finito and self.stato not in ("errore", "negata"):
                motivo = ("tempo scaduto" if self.lavoro_s() > self.tempo_s
                          else "l'estensione si è fermata senza risposta")
                # Per capire perché (e2e del 06/10: «senza risposta» e nient'altro): la coda
                # dell'errore del container va nel log, mai alla voce
                coda = [r.strip() for r in self.stderr.splitlines() if r.strip()][-3:]
                self.log(f"[ESTENSIONI] {self.nome}: {motivo} dopo "
                         f"{self.avvio_trascorso_s():.2f} s di avvio e {self.lavoro_s():.2f} s "
                         f"di lavoro" + (f"; il container dice: {' | '.join(coda)[:300]}"
                                         if coda else ""))
                self._cambia("errore", errore=motivo)

    def _fine(self, msg: dict):
        if "error" in msg:
            self._cambia("errore", errore=str((msg["error"] or {}).get("message") or "errore"))
            return
        res = msg.get("result") or {}
        if res.get("isError"):
            testo = " ".join(str(c.get("text") or "") for c in res.get("content") or [])
            self._cambia("errore", errore=testo[:500] or "errore dell'estensione")
            return
        out = res.get("structuredContent")
        if not isinstance(out, dict):
            try:
                out = json.loads(" ".join(str(c.get("text") or "")
                                          for c in res.get("content") or []))
            except ValueError:
                out = {"testo": " ".join(str(c.get("text") or "")
                                         for c in res.get("content") or [])}
        self._cambia("finita", risultato=out if isinstance(out, dict) else {"valore": out})

    def _richiesta(self, rid, azione: str, params: dict):
        if self.porta is None:
            self._scrivi({"jsonrpc": "2.0", "id": rid,
                          "error": {"code": -32000, "message": "nessuna porta"}})
            return
        esito = self.porta.gestisci(self, azione, params)
        if esito.get("conferma"):
            # Si ferma qui: la persona decide (decidi), il tempo di lavoro non conta
            t0 = time.monotonic()
            with self._cambio:
                self._decisione = None
                self.richiesta = {"id": rid, "azione": azione, "argomenti": params, **esito}
                self.stato = "in_attesa"
                self._cambio.notify_all()
                fine = t0 + self.conferma_s
                while self._decisione is None and self.stato == "in_attesa":
                    resto = fine - time.monotonic()
                    if resto <= 0:
                        break
                    self._cambio.wait(resto)
                dec = self._decisione
                if dec is None:
                    self.richiesta = None
                    self.stato = "in_corso"
            self.attesa_s += time.monotonic() - t0
            esito = self.porta.dopo_conferma(self, azione, params, esito, dec)
        if "errore" in esito:
            self._scrivi({"jsonrpc": "2.0", "id": rid,
                          "error": {"code": -32001, "message": esito["errore"]}})
        else:
            self._scrivi({"jsonrpc": "2.0", "id": rid, "result": esito.get("risultato") or {}})

    def _orologio(self):
        while True:
            time.sleep(0.2)
            if self.stato in ("finita", "errore", "negata"):
                return
            if self.stato == "in_corso" and self.lavoro_s() > self.tempo_s:
                self._cambia("errore", errore=f"tempo scaduto ({self.tempo_s:g} s)")
                self._ferma(gentile=False)
                return
            if (self.stato == "in_corso" and self.pronta_t is None
                    and time.monotonic() - self.inizio > self.avvio_s):
                self.log(f"[ESTENSIONI] {self.nome}: il container non è partito in "
                         f"{self.avvio_s:g} s")
                self._cambia("errore", errore=f"il contenitore non è partito in "
                                              f"{self.avvio_s:g} s")
                self._ferma(gentile=False)
                return

    def _ferma(self, gentile: bool = True):
        p = self._proc
        if p is None:
            return
        try:
            p.stdin.close()            # il runtime legge la fine e esce da solo
        except (OSError, ValueError, AttributeError):
            pass
        if gentile:
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        if p.poll() is None:
            try:
                subprocess.run([*(self.isolamento.docker or ["docker"]), "kill", self._nome_c],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                pass
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        for s in (p.stdin, p.stdout):
            try:
                s.close()
            except (OSError, ValueError, AttributeError):
                pass

    def annulla(self):
        with self._cambio:
            if self.stato in ("in_corso", "in_attesa"):
                self.stato = "negata"
                self.errore = "annullata"
                self._cambio.notify_all()
        self._ferma(gentile=False)
