"""
Un Ollama FINTO per le prove degli agenti (calliope/agenti/): un server HTTP vero, in un
thread, con l'API nativa che serve all'agente.

    GET  /api/version  /api/tags  /api/ps
    POST /api/chat     (stream NDJSON) risposte a copione: testo, thinking, tool_calls

`copione` è una lista: ogni elemento è un dict ({"content", "thinking", "tool_calls":
[{"name", "arguments"}], "errore", "status"}) o una funzione(body) → dict. Si consuma in
ordine; finito il copione risponde `predefinita`. `ritardo_pezzo` rallenta lo stream (un
pezzo ogni tanti secondi): serve all'annullo e all'arbitro. `richieste` tiene i corpi
ricevuti, `interrotte` conta gli stream chiusi dal client prima della fine.

Serve anche l'**API compatibile OpenAI** di vLLM (02/10, motore «openai» dell'agente), con
lo stesso copione e lo stesso elenco di richieste:

    GET  /version  /v1/models
    POST /v1/chat/completions  (stream SSE: delta.content, delta.reasoning_content, poi le
         tool_calls a pezzi per `index`, l'ultimo pezzo con `usage`, infine [DONE])

Un modello che non c'è dà 404 come vLLM («The model `x` does not exist.»); un modello in
`senza_think` dà 400 se la richiesta ha `chat_template_kwargs`. `vllm = False` toglie
`/version` (come llama.cpp).

**Modalità sviluppo di vLLM** (04/10, `dev = True`): `POST /pause?mode=keep`, `POST /resume`,
`GET /is_paused`. In pausa gli stream dell'API OpenAI non mandano pezzi (si fermano prima del
prossimo) e le richieste nuove aspettano: come vLLM con `mode=keep`. `ritardo_pausa` rallenta
la risposta a /pause (una pausa che non risponde), `stato_pausa` (es. 500) la fa fallire;
`chiamate_pausa` elenca «pausa»/«ripresa» in ordine; `pezzi_tempi` tiene l'istante
(monotonic) di ogni pezzo mandato dall'API OpenAI. Senza `dev` sono 404, come vLLM normale.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeOllama:
    def __init__(self, modelli=("qwen3.6:35b",), caricati=(), versione="0.35.0-finto"):
        self.modelli = list(modelli)
        self.caricati = list(caricati)
        self.versione = versione
        self.copione: list = []
        self.predefinita = {"content": "Fatto."}
        self.ritardo_pezzo = 0.0
        self.pezzi = 4
        self.pezzi_argomenti = 2             # API OpenAI: in quanti pezzi gli argomenti
        self.richieste: list[dict] = []
        self.interrotte = 0
        self.senza_think: set[str] = set()   # modelli che rispondono 400 a think
        # /api/show: le capacità del modello (05/10: «vision» per le foto, calliope/immagini.py)
        self.capacita = ["completion", "tools", "vision"]
        self.vllm = True                     # /version presente (vLLM); False: come llama.cpp
        # La finestra dal setup (05/10, fase 2b): max_model_len in /v1/models e i token della
        # cache in /metrics (vLLM), context_length in /api/show (Ollama). None: non detti
        self.max_model_len = None
        self.cache_token = None
        self.contesto_ollama = None
        self.dev = False                     # VLLM_SERVER_DEV_MODE=1: /pause, /resume
        self.ritardo_pausa = 0.0
        self.stato_pausa = 200
        self.chiamate_pausa: list[str] = []
        self.pezzi_tempi: list[float] = []
        self._libero = threading.Event()      # non in pausa
        self._libero.set()
        self._lock = threading.Lock()
        self.srv = None

    # ── server ──
    def avvia(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _json(self, code, obj):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/api/version":
                    return self._json(200, {"version": fake.versione})
                if self.path == "/api/tags":
                    return self._json(200, {"models": [{"name": m, "model": m, "size": 1}
                                                       for m in fake.modelli]})
                if self.path == "/api/ps":
                    return self._json(200, {"models": [{"name": m, "model": m}
                                                       for m in fake.caricati]})
                if self.path == "/version" and fake.vllm:
                    return self._json(200, {"version": fake.versione})
                if self.path == "/is_paused" and fake.dev:
                    return self._json(200, {"is_paused": not fake._libero.is_set()})
                if self.path == "/v1/models":
                    return self._json(200, {"object": "list", "data": [
                        {"id": m, "object": "model", "owned_by": "vllm",
                         **({"max_model_len": fake.max_model_len} if fake.max_model_len else {})}
                        for m in fake.modelli]})
                if self.path == "/metrics" and fake.cache_token:
                    testo = ('vllm:cache_config_info{block_size="16",kv_cache_size_tokens="%d"} '
                             '1.0\n' % fake.cache_token).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Content-Length", str(len(testo)))
                    self.end_headers()
                    self.wfile.write(testo)
                    return None
                return self._json(404, {"error": "not found"})

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                if self.path == "/v1/chat/completions":
                    return self._openai(body)
                if fake.dev and self.path.split("?")[0] in ("/pause", "/resume"):
                    if self.path.startswith("/pause"):
                        if fake.ritardo_pausa:
                            time.sleep(fake.ritardo_pausa)
                        with fake._lock:
                            fake.chiamate_pausa.append("pausa")
                        if fake.stato_pausa != 200:
                            return self._json(fake.stato_pausa, {"error": "pausa fallita"})
                        fake._libero.clear()
                        return self._json(200, {"status": "paused"})
                    with fake._lock:
                        fake.chiamate_pausa.append("ripresa")
                    fake._libero.set()
                    return self._json(200, {"status": "resumed"})
                if self.path == "/api/show":
                    if body.get("model") not in fake.modelli:
                        return self._json(404, {"error": "model not found"})
                    info = ({"general.architecture": "finto",
                             "finto.context_length": fake.contesto_ollama}
                            if fake.contesto_ollama else {})
                    return self._json(200, {"capabilities": list(fake.capacita),
                                            "model_info": info})
                if self.path != "/api/chat":
                    return self._json(404, {"error": "not found"})
                with fake._lock:
                    fake.richieste.append(body)
                    step = fake.copione.pop(0) if fake.copione else fake.predefinita
                model = body.get("model")
                if model not in fake.modelli:
                    return self._json(404, {"error": f"model '{model}' not found"})
                if "think" in body and model in fake.senza_think:
                    return self._json(400, {"error": f"\"{model}\" does not support thinking"})
                if callable(step):
                    step = step(body)
                if step.get("status"):
                    return self._json(step["status"], {"error": step.get("errore", "errore")})
                if body.get("stream") is False:
                    # Una risposta sola (Writer._ask con lo schema: estrazioni dell'ufficio)
                    msg = {"role": "assistant", "content": step.get("content") or ""}
                    if step.get("tool_calls"):
                        msg["tool_calls"] = [{"function": {"name": c["name"], "arguments":
                                                           c.get("arguments", {})}}
                                             for c in step["tool_calls"]]
                    return self._json(200, {"message": msg, "done": True,
                                            "eval_count": step.get("eval", 50),
                                            "prompt_eval_count": step.get("prompt", 200)})
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()

                def chunk(obj):
                    data = (json.dumps(obj) + "\n").encode()
                    self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
                    self.wfile.flush()
                try:
                    if step.get("thinking"):
                        chunk({"message": {"role": "assistant", "content": "",
                                           "thinking": step["thinking"]}, "done": False})
                    text = step.get("content") or ""
                    k = max(1, fake.pezzi)
                    size = max(1, len(text) // k + 1)
                    parts = [text[i:i + size] for i in range(0, len(text), size)] or [""]
                    for p in parts:
                        if fake.ritardo_pezzo:
                            time.sleep(fake.ritardo_pezzo)
                        chunk({"message": {"role": "assistant", "content": p}, "done": False})
                    if step.get("tool_calls"):
                        chunk({"message": {"role": "assistant", "content": "", "tool_calls": [
                            {"function": {"name": c["name"], "arguments": c.get("arguments", {})}}
                            for c in step["tool_calls"]]}, "done": False})
                    chunk({"message": {"role": "assistant", "content": ""}, "done": True,
                           "eval_count": step.get("eval", 50),
                           "prompt_eval_count": step.get("prompt", 200)})
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                except (ConnectionError, OSError):
                    with fake._lock:
                        fake.interrotte += 1

            def _openai(self, body):
                with fake._lock:
                    fake.richieste.append(body)
                model = body.get("model")
                if model not in fake.modelli:
                    return self._json(404, {"object": "error", "type": "NotFoundError",
                                            "message": f"The model `{model}` does not exist.",
                                            "code": 404})
                if "chat_template_kwargs" in body and model in fake.senza_think:
                    return self._json(400, {"object": "error", "type": "BadRequestError",
                                            "message": "chat_template_kwargs: enable_thinking "
                                                       "non supportato", "code": 400})
                # il copione si consuma solo se la richiesta arriva al «modello»
                with fake._lock:
                    step = fake.copione.pop(0) if fake.copione else fake.predefinita
                if callable(step):
                    step = step(body)
                if step.get("status"):
                    return self._json(step["status"], {"object": "error",
                                                       "message": step.get("errore", "errore"),
                                                       "code": step["status"]})
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()

                def chunk(obj):
                    # In pausa (modalità sviluppo) lo stream si ferma prima del pezzo dopo
                    fake._libero.wait()
                    fake.pezzi_tempi.append(time.monotonic())
                    data = (f"data: {json.dumps(obj)}\n\n").encode()
                    self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
                    self.wfile.flush()

                def delta(d, finish=None):
                    chunk({"id": "chatcmpl-finto", "object": "chat.completion.chunk",
                           "model": model, "choices": [{"index": 0, "delta": d,
                                                        "finish_reason": finish}]})
                try:
                    delta({"role": "assistant", "content": ""})
                    if step.get("thinking"):
                        delta({"reasoning_content": step["thinking"]})
                    text = step.get("content") or ""
                    k = max(1, fake.pezzi)
                    size = max(1, len(text) // k + 1)
                    for i in range(0, len(text), size):
                        if fake.ritardo_pezzo:
                            time.sleep(fake.ritardo_pezzo)
                        delta({"content": text[i:i + size]})
                    for i, c in enumerate(step.get("tool_calls") or []):
                        args = json.dumps(c.get("arguments", {}), ensure_ascii=False)
                        half = len(args) // 2
                        # come vLLM: prima id e nome, poi gli argomenti in due pezzi
                        delta({"tool_calls": [{"index": i, "id": f"chatcmpl-tool-{i}",
                                               "type": "function",
                                               "function": {"name": c["name"],
                                                            "arguments": ""}}]})
                        if fake.pezzi_argomenti > 2:
                            # Argomenti lunghi a molti pezzi, con il ritardo: il codice che
                            # arriva sugli schermi (prova_avanzamento.py)
                            n = fake.pezzi_argomenti
                            sz = max(1, len(args) // n + 1)
                            for j in range(0, len(args), sz):
                                if fake.ritardo_pezzo:
                                    time.sleep(fake.ritardo_pezzo)
                                delta({"tool_calls": [{"index": i, "function": {
                                    "arguments": args[j:j + sz]}}]})
                            continue
                        delta({"tool_calls": [{"index": i,
                                               "function": {"arguments": args[:half]}}]})
                        delta({"tool_calls": [{"index": i,
                                               "function": {"arguments": args[half:]}}]})
                    delta({}, "tool_calls" if step.get("tool_calls") else "stop")
                    chunk({"id": "chatcmpl-finto", "object": "chat.completion.chunk",
                           "model": model, "choices": [],
                           "usage": {"prompt_tokens": step.get("prompt", 200),
                                     "completion_tokens": step.get("eval", 50),
                                     "total_tokens": step.get("prompt", 200)
                                     + step.get("eval", 50),
                                     **({"completion_tokens_details": {
                                         "reasoning_tokens": step["ragionamento"]}}
                                        if "ragionamento" in step else {})}})
                    data = b"data: [DONE]\n\n"
                    self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                except (ConnectionError, OSError):
                    with fake._lock:
                        fake.interrotte += 1

        class S(ThreadingHTTPServer):
            daemon_threads = True

            def handle_error(self, request, client_address):
                pass                     # connessioni chiuse dal tunnel o dal client: normale

        self.srv = S(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        threading.Thread(target=self.srv.serve_forever, daemon=True, name="ollama-finto").start()
        return self

    @property
    def porta(self) -> int:
        return self.srv.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.porta}"

    def ferma(self):
        self._libero.set()
        if self.srv is not None:
            self.srv.shutdown()
            self.srv.server_close()
