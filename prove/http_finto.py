"""
Server HTTP finto per le prove delle installazioni (prove/prova_installa.py): niente
internet, file piccoli, tutto su 127.0.0.1.

Fa la parte di:
- il sito di Kiwix: indice Apache di /zim/<cartella>/ con i file .zim, <nome>.sha256
  accanto, GET e HEAD con Range (206), come download.kiwix.org e il mirror;
- Hugging Face e GitHub: file serviti per percorso, anche dopo un reindirizzamento;
- Ollama: /api/tags e /api/pull in NDJSON.

Comportamenti per le prove: `taglia` (manda solo i primi N byte di un file e chiude: la
ripresa), `lento` (pausa per blocco: annullo e avanzamento), `sha_sbagliato` (il .sha256
ufficiale non corrisponde), `rimanda` (301 verso un altro host), `ignora_range` (risponde
200 anche con Range).
"""

import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeHTTP:
    def __init__(self):
        self.files: dict[str, bytes] = {}          # percorso → contenuto
        self.taglia: dict[str, int] = {}           # percorso → byte da mandare, poi chiude
        self.lento: dict[str, float] = {}          # percorso → secondi di pausa per blocco
        self.sha_sbagliato: set[str] = set()       # percorsi .zim con .sha256 sbagliato
        self.rimanda: dict[str, str] = {}          # percorso → URL di destinazione
        self.ignora_range = False
        self.richieste: list[tuple[str, str, str | None]] = []   # (metodo, percorso, Range)
        self.ollama_modelli: list[dict] = []
        self.pull_errore: str | None = None
        self.pull_fatti: list[str] = []
        self.server = None

    # ── contenuti ──
    def zim(self, cartella: str, nome: str, dati: bytes):
        """Un file ZIM del sito di Kiwix, con il suo .sha256 ufficiale."""
        path = f"/zim/{cartella}/{nome}"
        self.files[path] = dati
        sha = hashlib.sha256(dati).hexdigest()
        if path in self.sha_sbagliato:
            sha = "0" * 64
        self.files[path + ".sha256"] = f"{sha}  {nome}\n".encode()

    def file(self, path: str, dati: bytes):
        self.files[path] = dati

    # ── server ──
    def avvia(self) -> "FakeHTTP":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):        # silenzio
                pass

            def do_HEAD(self):
                self._serve(head=True)

            def do_GET(self):
                self._serve(head=False)

            def do_POST(self):
                outer.richieste.append(("POST", self.path, None))
                length = int(self.headers.get("content-length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                if self.path == "/api/pull":
                    return outer._pull(self, body)
                self.send_error(404)

            def _serve(self, head: bool):
                rng = self.headers.get("Range")
                outer.richieste.append(("HEAD" if head else "GET", self.path, rng))
                if self.path == "/api/tags":
                    return outer._json(self, {"models": outer.ollama_modelli})
                if self.path in outer.rimanda:
                    self.send_response(301)
                    self.send_header("Location", outer.rimanda[self.path])
                    self.end_headers()
                    return
                if self.path.endswith("/") and self.path.startswith("/zim/"):
                    return outer._indice(self, self.path)
                data = outer.files.get(self.path)
                if data is None:
                    self.send_error(404)
                    return
                start = 0
                if rng and not outer.ignora_range and rng.startswith("bytes="):
                    start = int(rng[6:].split("-")[0] or 0)
                    if start >= len(data):
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{len(data)}")
                        self.end_headers()
                        return
                    self.send_response(206)
                    self.send_header("Content-Range",
                                     f"bytes {start}-{len(data) - 1}/{len(data)}")
                else:
                    self.send_response(200)
                body = data[start:]
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if head:
                    return
                cut = outer.taglia.pop(self.path, None)
                pause = outer.lento.get(self.path, 0.0)
                sent = 0
                step = 4096
                try:
                    while sent < len(body):
                        if cut is not None and start + sent >= cut:
                            break                       # connessione chiusa a metà
                        chunk = body[sent:sent + step]
                        if cut is not None:
                            chunk = chunk[:max(0, cut - start - sent)]
                        self.wfile.write(chunk)
                        self.wfile.flush()
                        sent += len(chunk)
                        if pause:
                            time.sleep(pause)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
                if cut is not None:
                    self.close_connection = True

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def ferma(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()

    # ── risposte ──
    @staticmethod
    def _json(h, obj, code=200):
        body = json.dumps(obj).encode()
        h.send_response(code)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", str(len(body)))
        h.end_headers()
        h.wfile.write(body)

    def _indice(self, h, path):
        """Un indice come quello di Apache su download.kiwix.org."""
        rows = []
        for p in sorted(self.files):
            if p.startswith(path) and "/" not in p[len(path):] and p.endswith(".zim"):
                name = p[len(path):]
                rows.append(f'<a href="{name}">{name}</a>   2026-09-01 10:00  '
                            f'{len(self.files[p])}')
        # Rumore che non deve contare: un altro prefisso e un nome quasi uguale
        rows.append('<a href="wikipedia_it_all_mini_extra_2099-01.zim">x</a>')
        rows.append('<a href="wikipedia_en_all_mini_2099-01.zim">x</a>')
        body = ("<html><body><pre>" + "\n".join(rows) + "</pre></body></html>").encode()
        h.send_response(200)
        h.send_header("Content-Type", "text/html")
        h.send_header("Content-Length", str(len(body)))
        h.end_headers()
        h.wfile.write(body)

    def _pull(self, h, body):
        model = body.get("model")
        self.pull_fatti.append(model)
        h.send_response(200)
        h.send_header("Content-Type", "application/x-ndjson")
        h.end_headers()
        lines = [{"status": "pulling manifest"}]
        if self.pull_errore:
            lines.append({"error": self.pull_errore})
        else:
            for done in (0, 500, 1000):
                lines.append({"status": "pulling abc", "digest": "sha256:abc", "total": 1000,
                              "completed": done})
            lines += [{"status": "verifying sha256 digest"}, {"status": "success"}]
        for obj in lines:
            h.wfile.write((json.dumps(obj) + "\n").encode())
            h.wfile.flush()
        if not self.pull_errore:
            self.ollama_modelli.append({"name": model, "size": 1000})
