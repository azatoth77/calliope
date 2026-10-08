"""
Il client dell'agente per un motore con l'**API compatibile OpenAI** (02/10/2026): vLLM
sulla DGX (`/v1/chat/completions`, `/v1/models`, `/version`), ma anche llama.cpp
(`llama-server`) o lo stesso Ollama su `/v1`.

Perché: sulla DGX Ollama 0.35.0 va in «CUDA error: an illegal memory access» con la
richiesta vera dell'agente (6 strumenti, qwen3.6:35b); senza strumenti la stessa richiesta
va. L'agente passa a vLLM, la voce resta su Ollama.

Stessa interfaccia di `remoto.ClienteOllama` (`versione`, `modelli`, `caricati`, `ha`,
`chat`, `interrompi`, `close`), e `chat` riceve **lo stesso corpo nel formato di Ollama**
che costruisce `ciclo.Agente.passata`: la traduzione sta tutta qui, così ciclo, arbitro,
sandbox e permessi non cambiano.

Traduzione del corpo:
- `messages`: le chiamate degli strumenti ricevono un id (`call_<n>`) e i messaggi `tool`
  il `tool_call_id` corrispondente, in ordine (Ollama non usa id); gli argomenti diventano
  una stringa JSON;
- `options.temperature` → `temperature`, `options.num_predict` → `max_tokens`;
  `presence_penalty` (08/10 sera, Config.agenti_presence_penalty) passa com'è;
  `num_ctx` e `keep_alive` non servono (il contesto lo fissa il server all'avvio);
- `think` vero/falso → `chat_template_kwargs.enable_thinking` (Qwen3, vLLM e llama.cpp);
  una stringa («low», «medium», «high», gpt-oss) → `reasoning_effort`;
- `format` (schema JSON) → `response_format` di tipo `json_schema` (decodifica guidata:
  xgrammar in vLLM, grammatica in llama.cpp); `"json"` → `json_object`;
- `thinking_budget` (05/10, il tetto del ragionamento di una passata) →
  `thinking_token_budget` di vLLM (verificato con vLLM 0.29.0 e qwen3.6, parser «qwen3»:
  finito il budget il modello chiude il ragionamento e risponde). Un server che non lo
  conosce lo rifiuta una volta e poi non lo riceve più.

I token: `usage.completion_tokens` (ragionamento compreso) e, con vLLM,
`usage.completion_tokens_details.reasoning_tokens` → `ragionamento`.

Lo stream: `delta.content`, il ragionamento in `delta.reasoning_content` o
`delta.reasoning` (secondo la versione di vLLM), le chiamate in `delta.tool_calls` a pezzi
(per `index`: nome e argomenti si accumulano), i token nell'ultimo pezzo
(`stream_options.include_usage`).
"""

import json
import threading
import time

from .remoto import ErroreOllama, Interrotto


def _args_str(args) -> str:
    if isinstance(args, str):
        return args
    return json.dumps(args if isinstance(args, dict) else {}, ensure_ascii=False)


def traduci_messaggi(messages: list) -> list:
    """Messaggi nel formato di Ollama → formato OpenAI (id delle chiamate, argomenti in
    stringa, tool_call_id nelle risposte degli strumenti)."""
    out, in_attesa, n = [], [], 0
    for m in messages:
        role = m.get("role")
        if role == "assistant":
            msg = {"role": "assistant", "content": m.get("content") or ""}
            calls = []
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                n += 1
                cid = tc.get("id") or f"call_{n}"
                calls.append({"id": cid, "type": "function",
                              "function": {"name": fn.get("name", ""),
                                           "arguments": _args_str(fn.get("arguments"))}})
            if calls:
                msg["tool_calls"] = calls
                in_attesa = [(c["id"], c["function"]["name"]) for c in calls]
            out.append(msg)
        elif role == "tool":
            name = m.get("tool_name") or m.get("name") or ""
            cid = m.get("tool_call_id")
            if not cid:
                # la prima chiamata in attesa con lo stesso nome, altrimenti la prima
                idx = next((i for i, (_, nm) in enumerate(in_attesa) if nm == name), 0)
                if in_attesa:
                    cid = in_attesa.pop(idx)[0]
                else:
                    n += 1
                    cid = f"call_{n}"
            out.append({"role": "tool", "tool_call_id": cid, "content": m.get("content") or ""})
        else:
            out.append({"role": role, "content": m.get("content") or ""})
    return out


def traduci_corpo(body: dict) -> dict:
    """Il corpo di /api/chat di Ollama → quello di /v1/chat/completions."""
    opts = body.get("options") or {}
    req = {"model": body.get("model", ""), "messages": traduci_messaggi(body.get("messages") or []),
           "stream": True, "stream_options": {"include_usage": True}}
    if "temperature" in opts:
        req["temperature"] = opts["temperature"]
    # Contro le ripetizioni senza fine di Qwen3 (08/10 sera): Config.agenti_presence_penalty
    if body.get("presence_penalty"):
        req["presence_penalty"] = float(body["presence_penalty"])
    if opts.get("num_predict"):
        req["max_tokens"] = int(opts["num_predict"])
    elif opts.get("num_ctx"):
        # Con Ollama una passata non va oltre num_ctx; vLLM invece genera fino a
        # --max-model-len (131072): un ragionamento che gira a vuoto durerebbe mezz'ora
        # (visto nel banco del 02/10). Metà del contesto dell'agente come tetto per passata.
        req["max_tokens"] = max(1024, int(opts["num_ctx"]) // 2)
    th = body.get("think")
    if isinstance(th, bool):
        req["chat_template_kwargs"] = {"enable_thinking": th}
    elif isinstance(th, str) and th:
        req["reasoning_effort"] = th
    if th and body.get("thinking_budget"):
        req["thinking_token_budget"] = int(body["thinking_budget"])
    if body.get("tools"):
        req["tools"] = body["tools"]
        req["tool_choice"] = "auto"
    fmt = body.get("format")
    if isinstance(fmt, dict):
        req["response_format"] = {"type": "json_schema",
                                  "json_schema": {"name": "risposta", "schema": fmt,
                                                  "strict": True}}
    elif fmt == "json":
        req["response_format"] = {"type": "json_object"}
    return req


class ClienteOpenAI:
    """Client dell'agente per un server compatibile OpenAI. `url` è la radice del server
    (http://127.0.0.1:8000); un «/v1» finale si toglie."""

    motore = "openai"

    def __init__(self, url: str, timeout_connessione: float = 5.0,
                 timeout_lettura: float = 600.0, chiave: str | None = None):
        import httpx
        u = url.rstrip("/")
        if u.endswith("/v1"):
            u = u[:-3]
        self.url = u
        headers = {"Authorization": f"Bearer {chiave}"} if chiave else {}
        self.http = httpx.Client(base_url=self.url, headers=headers,
                                 timeout=httpx.Timeout(timeout_lettura,
                                                       connect=timeout_connessione))
        # Uno stream per thread (04/10): agente, archivio e ufficio possono usare lo stesso
        # client insieme, e l'arbitro ne chiude uno senza toccare gli altri
        self._risposte: dict[int, object] = {}
        self._lock = threading.Lock()
        self._interrotti: set[int] = set()
        self.senza_think: set[str] = set()   # modelli che hanno rifiutato il thinking
        self.senza_budget: set[str] = set()  # modelli (server) senza thinking_token_budget

    # ── informazioni ──
    def _get(self, path: str, timeout: float = 5.0):
        import httpx
        try:
            r = self.http.get(path, timeout=timeout)
        except httpx.HTTPError as e:
            raise ErroreOllama("motore_giu", type(e).__name__) from None
        if r.status_code >= 400:
            raise ErroreOllama("motore_errore", f"HTTP {r.status_code}")
        try:
            return r.json()
        except ValueError:
            raise ErroreOllama("motore_errore", "risposta non JSON") from None

    def versione(self, timeout: float = 5.0) -> str:
        """vLLM ha /version; gli altri (llama.cpp) no: allora basta che /v1/models
        risponda, e la versione è «?»."""
        try:
            v = self._get("/version", timeout).get("version")
            if v:
                return f"vLLM {v}"
        except ErroreOllama as e:
            if e.codice == "motore_giu":
                raise
        self._get("/v1/models", timeout)
        return "?"

    def modelli(self, timeout: float = 5.0) -> list[str]:
        data = self._get("/v1/models", timeout).get("data") or []
        return [m.get("id") or "" for m in data if isinstance(m, dict)]

    def caricati(self, timeout: float = 5.0) -> list[str]:
        """Un server OpenAI serve solo i modelli che ha già in memoria."""
        try:
            return self.modelli(timeout)
        except ErroreOllama:
            return []

    @staticmethod
    def ha(nomi: list[str], modello: str) -> bool:
        return modello.strip() in nomi

    # ── chat ──
    def interrompi(self, tid: int | None = None):
        """Chiude lo stream in corso (da qualunque thread): vLLM annulla la richiesta.
        `tid`: solo lo stream di quel thread (anche se non è ancora aperto); senza, tutti
        quelli aperti."""
        with self._lock:
            tids = [tid] if tid is not None else list(self._risposte)
            self._interrotti.update(tids)
            rs = [self._risposte.get(t) for t in tids]
        for r in rs:
            if r is None:
                continue
            try:
                r.close()
            except Exception:  # noqa: BLE001 — chiusura da un altro thread: va bene così
                pass

    def chat(self, body: dict, su_pezzo=None, controlla=None, su_flusso=None) -> dict:
        """Una passata in streaming, come `ClienteOllama.chat`: restituisce {"content",
        "thinking", "tool_calls", "eval", "prompt", "s"}."""
        req = traduci_corpo(body)
        model = req["model"]
        if model in self.senza_think:
            req.pop("chat_template_kwargs", None)
            req.pop("reasoning_effort", None)
            req.pop("thinking_token_budget", None)
        if model in self.senza_budget:
            req.pop("thinking_token_budget", None)
        try:
            return self._chat(req, su_pezzo, controlla, su_flusso)
        except ErroreOllama as e:
            msg = str(e).lower()
            if ("thinking_token_budget" in req and e.codice == "motore_errore"
                    and "thinking_token_budget" in msg):
                self.senza_budget.add(model)
                req.pop("thinking_token_budget", None)
                return self._chat(req, su_pezzo, controlla, su_flusso)
            if (("chat_template_kwargs" in req or "reasoning_effort" in req)
                    and e.codice == "motore_errore"
                    and ("enable_thinking" in msg or "reasoning" in msg
                         or "chat_template_kwargs" in msg)):
                self.senza_think.add(model)
                req.pop("chat_template_kwargs", None)
                req.pop("reasoning_effort", None)
                return self._chat(req, su_pezzo, controlla, su_flusso)
            raise

    def _chat(self, req: dict, su_pezzo, controlla, su_flusso=None) -> dict:
        import httpx
        out = {"content": "", "thinking": "", "tool_calls": [], "eval": 0, "prompt": 0, "s": 0.0}
        calls: dict[int, dict] = {}
        t0 = time.perf_counter()
        tid = threading.get_ident()
        with self._lock:
            self._interrotti.discard(tid)
        try:
            with self.http.stream("POST", "/v1/chat/completions", json=req) as r:
                with self._lock:
                    self._risposte[tid] = r
                    if tid in self._interrotti:
                        raise Interrotto()
                if r.status_code >= 400:
                    r.read()
                    msg = r.text[:300]
                    low = msg.lower()
                    if r.status_code == 404 and ("does not exist" in low or "not found" in low):
                        raise ErroreOllama("modello_mancante", msg)
                    raise ErroreOllama("motore_errore", f"HTTP {r.status_code}: {msg}")
                for line in r.iter_lines():
                    if controlla is not None:
                        controlla()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    obj = json.loads(data)
                    if obj.get("error"):
                        err = obj["error"]
                        txt = err.get("message") if isinstance(err, dict) else err
                        raise ErroreOllama("motore_errore", str(txt)[:300])
                    usage = obj.get("usage")
                    if usage:
                        out["eval"] = int(usage.get("completion_tokens") or 0)
                        out["prompt"] = int(usage.get("prompt_tokens") or 0)
                        det = usage.get("completion_tokens_details") or {}
                        if isinstance(det, dict) and det.get("reasoning_tokens") is not None:
                            out["ragionamento"] = int(det.get("reasoning_tokens") or 0)
                    for ch in obj.get("choices") or []:
                        d = ch.get("delta") or {}
                        th = d.get("reasoning_content") or d.get("reasoning")
                        if th:
                            out["thinking"] += th
                            if su_flusso is not None:
                                su_flusso("pensiero", th)
                        if d.get("content"):
                            out["content"] += d["content"]
                            if su_pezzo is not None:
                                su_pezzo(d["content"])
                            if su_flusso is not None:
                                su_flusso("testo", d["content"])
                        for tc in d.get("tool_calls") or []:
                            i = tc.get("index", len(calls))
                            c = calls.setdefault(i, {"name": "", "arguments": ""})
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                c["name"] += fn["name"]
                            a = fn.get("arguments")
                            if isinstance(a, dict):
                                c["arguments"] = json.dumps(a)
                            elif a:
                                c["arguments"] += a
                                # Gli argomenti a pezzi (vLLM): il codice che l'agente sta
                                # scrivendo, per l'avanzamento sugli schermi
                                if su_flusso is not None:
                                    su_flusso("chiamata", a)
        except (httpx.HTTPError, OSError, ValueError) as e:
            with self._lock:
                interrotto = tid in self._interrotti
            if interrotto:
                raise Interrotto() from None
            if isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout)):
                raise ErroreOllama("motore_giu", type(e).__name__) from None
            raise ErroreOllama("motore_errore", type(e).__name__) from None
        finally:
            with self._lock:
                self._risposte.pop(tid, None)
        with self._lock:
            if tid in self._interrotti:
                raise Interrotto()
        for i in sorted(calls):
            c = calls[i]
            try:
                args = json.loads(c["arguments"]) if c["arguments"].strip() else {}
            except ValueError:
                args = {}
            out["tool_calls"].append({"name": c["name"],
                                      "arguments": args if isinstance(args, dict) else {}})
        out["s"] = round(time.perf_counter() - t0, 2)
        return out

    def close(self):
        try:
            self.http.close()
        except Exception:  # noqa: BLE001
            pass
