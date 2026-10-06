"""Il browser senza finestra delle prove (Edge o Chromium), comandato con il protocollo
DevTools (06/10, P5 dell'analisi complessiva).

Due cause d'instabilità tolte, comuni a tutte le prove con il browser:
- la porta di DevTools la sceglie il browser (`--remote-debugging-port=0`) e la scrive in
  `DevToolsActivePort` nel profilo: prima la prova liberava una porta e la passava a Edge, e
  nel frattempo un altro processo poteva prenderla;
- la chiusura: `Browser.close` via DevTools (Edge chiude da sé i suoi processi), poi si
  uccide l'albero dei processi rimasto. Prima si uccideva solo il processo principale, e
  crashpad e le utility restavano vivi: il runner segnava la prova come fallita per i
  processi lasciati vivi (13 log su 18 di prova_scritto_pagina). I processi si riconoscono
  anche dal profilo (`--user-data-dir`): alcune utility di Edge (ProfileImport) partono tardi,
  dopo l'elenco dei figli, e restano orfane quando il principale esce.
"""

import json
import subprocess
import time
import urllib.request
from pathlib import Path

OPZIONI_BASE = ("--headless=new", "--remote-debugging-port=0", "--no-first-run",
                "--no-default-browser-check", "--disable-sync", "--disable-gpu",
                "--remote-allow-origins=*", "--disable-crash-reporter", "--disable-breakpad")


class Browser:
    """Un processo del browser con il suo profilo. `ws_pagina(...)` dà l'indirizzo DevTools
    di una scheda; `chiudi()` lo chiude per intero (si può chiamare più volte)."""

    def __init__(self, exe: str, profilo: Path, opzioni=(), url: str = "about:blank",
                 attesa_s: float = 30):
        profilo = Path(profilo)
        self.profilo = str(profilo)
        profilo.mkdir(parents=True, exist_ok=True)
        file_porta = profilo / "DevToolsActivePort"
        try:
            file_porta.unlink()             # quello di un avvio precedente con lo stesso profilo
        except OSError:
            pass
        self.proc = subprocess.Popen(
            [exe, *OPZIONI_BASE, f"--user-data-dir={profilo}", *opzioni, url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.porta: int | None = None
        self.ws_browser: str | None = None
        fine = time.monotonic() + attesa_s
        while time.monotonic() < fine and self.proc.poll() is None:
            try:
                righe = file_porta.read_text(encoding="utf-8").split()
                if len(righe) >= 2 and righe[0].isdigit():
                    self.porta = int(righe[0])
                    self.ws_browser = f"ws://127.0.0.1:{self.porta}{righe[1]}"
                    break
            except OSError:
                pass
            time.sleep(0.05)
        if self.porta is None:
            self.chiudi()
            raise RuntimeError("DevTools non risponde (DevToolsActivePort assente)")

    def schede(self) -> list[dict]:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.porta}/json", timeout=5) as r:
            return [t for t in json.load(r) if t.get("type") == "page"]

    def ws_pagina(self, prefisso: str | None = None, attesa_s: float = 15) -> str:
        """L'indirizzo DevTools della prima scheda (con `prefisso`, solo una il cui URL
        comincia così: Edge apre a volte anche schede sue al primo avvio di un profilo)."""
        fine = time.monotonic() + attesa_s
        while time.monotonic() < fine:
            try:
                pag = [t for t in self.schede()
                       if prefisso is None or str(t.get("url", "")).startswith(prefisso)]
                if pag:
                    return pag[0]["webSocketDebuggerUrl"]
            except OSError:
                pass
            time.sleep(0.1)
        raise RuntimeError("DevTools non risponde (nessuna scheda)")

    def chiudi(self):
        proc = self.proc
        try:
            import psutil
        except ImportError:
            psutil = None
        figli = []
        if psutil is not None:
            try:
                figli = psutil.Process(proc.pid).children(recursive=True)
            except Exception:  # noqa: BLE001 — già uscito
                pass
        if proc.poll() is None and self.ws_browser:
            try:
                from websockets.sync.client import connect
                with connect(self.ws_browser, open_timeout=3, close_timeout=1,
                             max_size=2 ** 24) as ws:
                    ws.send(json.dumps({"id": 1, "method": "Browser.close"}))
                    try:
                        ws.recv(timeout=3)
                    except Exception:  # noqa: BLE001 — il browser chiude la connessione
                        pass
            except Exception:  # noqa: BLE001
                pass
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                pass
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
        if psutil is None:
            return
        # I figli visti prima della chiusura e ogni processo con questo profilo (anche quelli
        # nati dopo, rimasti orfani): si aspetta che escano da soli, poi si chiudono
        fine = time.monotonic() + 3
        while True:
            vivi = [f for f in figli if f.is_running()] + _del_profilo(psutil, self.profilo)
            if not vivi:
                return
            if time.monotonic() > fine:
                break
            time.sleep(0.2)
        for f in vivi:
            try:
                f.kill()
            except Exception:  # noqa: BLE001
                pass
        psutil.wait_procs(vivi, timeout=5)


def _del_profilo(psutil, profilo: str) -> list:
    """I processi del browser avviati con questo profilo (il percorso intero: «foto» non è
    «foto2»)."""
    import os

    def norma(x: str) -> str:
        return os.path.normcase(os.path.normpath(x.strip('"')))
    voluto = norma(profilo)
    out = []
    for p in psutil.process_iter(["cmdline"]):
        try:
            for c in p.info.get("cmdline") or []:
                if c.startswith("--user-data-dir=") and norma(c[16:]) == voluto:
                    out.append(p)
                    break
        except Exception:  # noqa: BLE001
            pass
    return out
