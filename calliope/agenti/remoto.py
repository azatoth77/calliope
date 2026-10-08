"""
Il client dell'Ollama dell'agente: API nativa (/api/chat, /api/tags, /api/version, /api/ps).

Diverso da `brain.OllamaBackend` per tre motivi:
- il modello, il contesto e il thinking sono quelli dell'agente, non della voce;
- lo stream si può **interrompere da un altro thread** (`interrompi`): l'annullo di un
  lavoro e l'arbitro (stesso Ollama della voce) chiudono la connessione, e Ollama smette
  di generare (misura del 26/09: la chiusura ferma davvero la generazione);
- conta i token (generati e letti) di ogni passata, per il tetto del lavoro.
"""

import json
import threading
import time


class Interrotto(Exception):
    """Lo stream è stato chiuso da fuori (annullo o precedenza alla voce)."""


class ErroreOllama(Exception):
    def __init__(self, codice: str, messaggio: str = ""):
        super().__init__(messaggio or codice)
        self.codice = codice


class ClienteOllama:
    motore = "ollama"

    def __init__(self, url: str, timeout_connessione: float = 5.0, timeout_lettura: float = 600.0):
        import httpx
        self.url = url.rstrip("/")
        self.http = httpx.Client(base_url=self.url,
                                 timeout=httpx.Timeout(timeout_lettura,
                                                       connect=timeout_connessione))
        # Uno stream per thread (04/10): agente, archivio e ufficio possono usare lo stesso
        # client insieme, e l'arbitro ne chiude uno senza toccare gli altri
        self._risposte: dict[int, object] = {}
        self._lock = threading.Lock()
        self._interrotti: set[int] = set()
        self.senza_think: set[str] = set()   # modelli che hanno rifiutato `think`

    # ── informazioni ──
    def _get(self, path: str, timeout: float = 5.0):
        import httpx
        try:
            r = self.http.get(path, timeout=timeout)
        except httpx.HTTPError as e:
            raise ErroreOllama("ollama_giu", type(e).__name__) from None
        if r.status_code >= 400:
            raise ErroreOllama("ollama_errore", f"HTTP {r.status_code}")
        try:
            return r.json()
        except ValueError:
            raise ErroreOllama("ollama_errore", "risposta non JSON") from None

    def versione(self, timeout: float = 5.0) -> str:
        return str(self._get("/api/version", timeout).get("version") or "?")

    def modelli(self, timeout: float = 5.0) -> list[str]:
        return [m.get("name") or m.get("model") or ""
                for m in self._get("/api/tags", timeout).get("models", [])]

    def caricati(self, timeout: float = 5.0) -> list[str]:
        try:
            return [m.get("name") or m.get("model") or ""
                    for m in self._get("/api/ps", timeout).get("models", [])]
        except ErroreOllama:
            return []

    @staticmethod
    def ha(nomi: list[str], modello: str) -> bool:
        m = modello.strip()
        return m in nomi or (":" not in m and f"{m}:latest" in nomi)

    # ── chat ──
    def interrompi(self, tid: int | None = None):
        """Chiude lo stream in corso (da qualunque thread). Non aspetta niente.
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
        """Una passata in streaming. Restituisce {"content", "thinking", "tool_calls",
        "eval", "prompt", "s"}. `su_pezzo(testo)` riceve il contenuto man mano;
        `controlla()` (a ogni riga) può sollevare Interrotto. Un modello che non sa
        pensare riceve di nuovo la richiesta senza `think`."""
        model = body.get("model", "")
        # Il tetto del ragionamento della passata è di vLLM (thinking_token_budget): Ollama non
        # lo conosce, lì vale solo num_predict. Il presence_penalty dell'agente (08/10 sera) è
        # per vLLM: con Ollama non si manda (stesso modello della voce, niente ricarichi)
        body = {k: v for k, v in body.items() if k not in ("thinking_budget", "presence_penalty")}
        if model in self.senza_think:
            body = {k: v for k, v in body.items() if k != "think"}
        try:
            return self._chat(body, su_pezzo, controlla, su_flusso)
        except ErroreOllama as e:
            if "think" in body and "think" in str(e).lower():
                self.senza_think.add(model)
                return self._chat({k: v for k, v in body.items() if k != "think"},
                                  su_pezzo, controlla, su_flusso)
            raise

    def _chat(self, body: dict, su_pezzo, controlla, su_flusso=None) -> dict:
        import httpx
        body = dict(body, stream=True)
        out = {"content": "", "thinking": "", "tool_calls": [], "eval": 0, "prompt": 0, "s": 0.0}
        t0 = time.perf_counter()
        tid = threading.get_ident()
        with self._lock:
            self._interrotti.discard(tid)
        try:
            with self.http.stream("POST", "/api/chat", json=body) as r:
                with self._lock:
                    self._risposte[tid] = r
                    if tid in self._interrotti:
                        raise Interrotto()
                if r.status_code >= 400:
                    r.read()
                    msg = r.text[:300]
                    if r.status_code == 404 and "not found" in msg.lower():
                        raise ErroreOllama("modello_mancante", msg)
                    raise ErroreOllama("ollama_errore", f"HTTP {r.status_code}: {msg}")
                for line in r.iter_lines():
                    if controlla is not None:
                        controlla()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if obj.get("error"):
                        raise ErroreOllama("ollama_errore", str(obj["error"])[:300])
                    msg = obj.get("message") or {}
                    if msg.get("thinking"):
                        out["thinking"] += msg["thinking"]
                        if su_flusso is not None:
                            su_flusso("pensiero", msg["thinking"])
                    if msg.get("content"):
                        out["content"] += msg["content"]
                        if su_pezzo is not None:
                            su_pezzo(msg["content"])
                        if su_flusso is not None:
                            su_flusso("testo", msg["content"])
                    for tc in msg.get("tool_calls") or []:
                        fn = tc.get("function") or {}
                        args = fn.get("arguments") or {}
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except ValueError:
                                args = {}
                        out["tool_calls"].append({"name": fn.get("name", ""),
                                                  "arguments": args if isinstance(args, dict)
                                                  else {}})
                    if obj.get("done"):
                        out["eval"] = int(obj.get("eval_count") or 0)
                        out["prompt"] = int(obj.get("prompt_eval_count") or 0)
                        break
        except (httpx.HTTPError, OSError, ValueError) as e:
            with self._lock:
                interrotto = tid in self._interrotti
            if interrotto:
                raise Interrotto() from None
            if isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout)):
                raise ErroreOllama("ollama_giu", type(e).__name__) from None
            raise ErroreOllama("ollama_errore", type(e).__name__) from None
        finally:
            with self._lock:
                self._risposte.pop(tid, None)
        with self._lock:
            if tid in self._interrotti:
                raise Interrotto()
        out["s"] = round(time.perf_counter() - t0, 2)
        return out

    def close(self):
        try:
            self.http.close()
        except Exception:  # noqa: BLE001
            pass


def crea_cliente(imp, timeout_lettura: float = 600.0):
    """Il client giusto per il motore dell'agente: «ollama» (API nativa) oppure «openai»
    (vLLM, llama.cpp: `remoto_openai.ClienteOpenAI`)."""
    if getattr(imp, "motore", "ollama") == "openai":
        from .remoto_openai import ClienteOpenAI
        return ClienteOpenAI(imp.url, timeout_connessione=imp.timeout_s,
                             timeout_lettura=timeout_lettura)
    return ClienteOllama(imp.url, timeout_connessione=imp.timeout_s,
                         timeout_lettura=timeout_lettura)
