import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della finestra di contesto calcolata dal setup (calliope/contesto.py, 05/10).

- forma della cache di Gemma 4 e4b e 26B (dal model_info vero di /api/show), token della
  cache di vLLM da /metrics, memoria libera da nvidia-smi o da /proc/meminfo finti;
- scelta della finestra: minimo dei tre limiti, multipli di 4096, mai sotto 8192 né sopra il
  massimo, dati mancanti → contesto_ripiego (detto), pavimento del tempo (fase 1);
- `llm_num_ctx`: «auto», un numero che vince (anche su un profilo), un valore sbagliato;
- `prepara` con un Ollama finto e una Brain vera: misura della lettura, ricarica con la
  finestra nuova (num_ctx uguale in ogni richiesta dopo), contesto.json, velocità riusata;
- token veri a ogni turno (Ollama `prompt_eval_count` + `eval_count`; API OpenAI con
  `stream_options.include_usage`) → Brain.last_context;
- la barra sugli schermi: solo agli schermi personali di chi parla, mai a un ospite.
"""

import contextlib
import io
import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp())
os.environ["CALLIOPE_CONTESTO"] = str(TMP / "contesto.json")

from calliope import contesto  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.config import Config, load_config  # noqa: E402
from calliope.tools.registry import ToolRegistry  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""),
          flush=True)


# ─────────────────────────── 1. forma della cache ───────────────────────────
PAT_E4B = [True] * 5 + [False]
E4B = {"general.architecture": "gemma4", "gemma4.block_count": 42,
       "gemma4.attention.head_count": 8, "gemma4.attention.head_count_kv": 2,
       "gemma4.attention.key_length": 512, "gemma4.attention.value_length": 512,
       "gemma4.attention.key_length_swa": 256, "gemma4.attention.value_length_swa": 256,
       "gemma4.attention.shared_kv_layers": 18, "gemma4.attention.sliding_window": 512,
       "gemma4.attention.sliding_window_pattern": PAT_E4B * 7,
       "gemma4.context_length": 131072, "gemma4.embedding_length": 2560}
B26 = {"general.architecture": "gemma4", "gemma4.block_count": 30,
       "gemma4.attention.head_count": 16,
       "gemma4.attention.head_count_kv": [8, 8, 8, 8, 8, 2] * 5,
       "gemma4.attention.key_length": 512, "gemma4.attention.value_length": 512,
       "gemma4.attention.key_length_swa": 256, "gemma4.attention.value_length_swa": 256,
       "gemma4.attention.shared_kv_layers": 0, "gemma4.attention.sliding_window": 1024,
       "gemma4.attention.sliding_window_pattern": PAT_E4B * 5,
       "gemma4.context_length": 262144, "gemma4.embedding_length": 2816}
LLAMA = {"general.architecture": "llama", "llama.block_count": 32,
         "llama.attention.head_count": 32, "llama.attention.head_count_kv": 8,
         "llama.embedding_length": 4096, "llama.context_length": 131072}
kv = contesto.kv_ollama(E4B)
verifica("e4b: 4 strati globali con cache propria (gli ultimi 18 la condividono) → 16 KiB "
         "a token × 1,1", kv and round(kv[0]) == round(16384 * 1.1), kv)
verifica("e4b: 20 strati «sliding» con 512 token fissi",
         kv and round(kv[1]) == round(20 * 2 * 512 * 2 * 512 * 1.1), kv)
kv = contesto.kv_ollama(B26)
verifica("26B: 5 strati globali con 2 teste KV (elenco per strato) → 20 KiB a token × 1,1",
         kv and round(kv[0]) == round(20480 * 1.1), kv)
kv = contesto.kv_ollama(LLAMA)
verifica("llama senza finestra: tutti globali, dimensione della testa dall'embedding",
         kv and round(kv[0]) == round(32 * 8 * 256 * 2 * 1.1) and kv[1] == 0, kv)
verifica("model_info vuoto → None", contesto.kv_ollama({}) is None)
# Famiglie che il calcolo sovrastimava (08/10, taratura della macchina §3.4): forma vera da
# /api/show (qwen3.6 e gpt-oss della DGX, gemma3 e qwen3.5 del portatile)
QWEN36 = {"general.architecture": "qwen35moe", "qwen35moe.block_count": 41,
          "qwen35moe.attention.head_count": 16, "qwen35moe.attention.head_count_kv": 2,
          "qwen35moe.attention.key_length": 256, "qwen35moe.attention.value_length": 256,
          "qwen35moe.full_attention_interval": 4, "qwen35moe.nextn_predict_layers": 1,
          "qwen35moe.embedding_length": 2048, "qwen35moe.context_length": 262144}
GPTOSS = {"general.architecture": "gptoss", "gptoss.block_count": 24,
          "gptoss.attention.head_count": 64, "gptoss.attention.head_count_kv": 8,
          "gptoss.attention.key_length": 64, "gptoss.attention.value_length": 64,
          "gptoss.attention.sliding_window": 128, "gptoss.embedding_length": 2880}
GEMMA3 = {"general.architecture": "gemma3", "gemma3.block_count": 34,
          "gemma3.attention.head_count": 8, "gemma3.attention.head_count_kv": 4,
          "gemma3.attention.key_length": 256, "gemma3.attention.value_length": 256,
          "gemma3.attention.sliding_window": 1024, "gemma3.embedding_length": 2560}
QWEN35 = {"general.architecture": "qwen35", "qwen35.block_count": 32,
          "qwen35.attention.head_count": 16,
          "qwen35.attention.head_count_kv": [0, 0, 0, 4] * 8,
          "qwen35.attention.key_length": 256, "qwen35.attention.value_length": 256,
          "qwen35.full_attention_interval": 4, "qwen35.embedding_length": 2560}
kv = contesto.kv_ollama(QWEN36)
verifica("qwen3.6: uno strato su 4 con attenzione (10 su 41) → 20 KiB, non 82",
         kv and round(kv[0]) == round(10 * 2 * 512 * 2 * 1.1) and kv[1] == 0, kv)
kv = contesto.kv_ollama(GPTOSS)
verifica("gpt-oss: metà strati sliding da 128 → 24 KiB a token e 3 MiB fissi, non 48",
         kv and round(kv[0]) == round(12 * 8 * 128 * 2 * 1.1)
         and round(kv[1]) == round(12 * 8 * 128 * 2 * 128 * 1.1), kv)
kv = contesto.kv_ollama(GEMMA3)
verifica("gemma3: 5 sliding e 1 globale → 5 strati globali, 20 KiB e ~110 MiB fissi, non 136",
         kv and round(kv[0]) == round(5 * 4 * 512 * 2 * 1.1)
         and 100 * 2**20 < kv[1] < 130 * 2**20, kv)
kv = contesto.kv_ollama(QWEN35)
verifica("contrario: qwen3.5 con le teste per strato resta 32 KiB (l'intervallo non conta "
         "due volte)", kv and round(kv[0]) == round(8 * 4 * 512 * 2 * 1.1), kv)
senza = {k: v for k, v in GEMMA3.items() if "sliding" not in k}
kv = contesto.kv_ollama(senza)
verifica("contrario: gemma3 senza sliding_window → tutti globali, prudente",
         kv and round(kv[0]) == round(34 * 4 * 512 * 2 * 1.1), kv)
altro = {k.replace("gptoss", "ignoto"): v for k, v in GPTOSS.items()}
altro["general.architecture"] = "ignoto"
kv = contesto.kv_ollama(altro)
verifica("contrario: architettura non elencata con la finestra ma senza schema → prudente",
         kv and round(kv[0]) == round(24 * 8 * 128 * 2 * 1.1), kv)
verifica("contesto massimo del modello", (contesto.contesto_ollama(E4B),
         contesto.contesto_ollama(B26), contesto.contesto_ollama({})) == (131072, 262144, None))
METRICHE = ('# HELP vllm:cache_config_info x\nvllm:cache_config_info{block_size="16",'
            'cache_dtype="fp8",kv_cache_size_tokens="684374",num_gpu_blocks="49817"} 1.0\n')
verifica("vLLM: token della cache da /metrics", contesto.token_cache_vllm(METRICHE) == 684374)
verifica("vLLM: blocchi × dimensione se manca kv_cache_size_tokens",
         contesto.token_cache_vllm('vllm:cache_config_info{block_size="16",'
                                   'num_gpu_blocks="100"} 1') == 1600)
verifica("vLLM: niente metrica → None", contesto.token_cache_vllm("altro 1\n") is None)

def fase1():
    """La configurazione della fase 1: senza compressione, 1,5 s di rilettura (le misure del
    05/10 mattina)."""
    c = Config()
    c.contesto_riassuntore, c.contesto_rilettura_max_s = "spento", 1.5
    return c


# ─────────────────────────── 2. memoria libera ───────────────────────────
meminfo = TMP / "meminfo"
meminfo.write_text("MemTotal:       125439440 kB\nMemAvailable:   36816576 kB\n", "ascii")
lib = contesto.memoria_libera(str(meminfo), smi=lambda: "2543\n")
verifica("nvidia-smi con i numeri (portatile)", lib == (2543 * 1024 * 1024, "nvidia-smi"), lib)
lib = contesto.memoria_libera(str(meminfo), smi=lambda: "[N/A]\n")
verifica("nvidia-smi [N/A] (DGX, memoria unificata) → MemAvailable",
         lib == (36816576 * 1024, "meminfo"), lib)
verifica("niente dei due → None", contesto.memoria_libera(str(TMP / "manca"),
                                                         smi=lambda: "") is None)

# ─────────────────────────── 3. scelta ───────────────────────────
cfg = fase1()
note: list = []
verifica("minimo dei tre, a multipli di 4096 per difetto",
         contesto.scegli(cfg, modello=131072, memoria=50000, tempo=40000, note=note)
         == (36864, "tempo"))
verifica("la memoria più stretta vince", contesto.scegli(cfg, modello=131072, memoria=20000,
                                                         tempo=40000) == (16384, "memoria"))
verifica("mai sotto 8192", contesto.scegli(cfg, modello=131072, memoria=3000, tempo=40000)
         == (8192, "minimo"))
verifica("mai sopra il massimo del modello (anche se è sotto 8192)",
         contesto.scegli(cfg, modello=4096, memoria=3000, tempo=40000)[0] == 4096)
note = []
fin, mot = contesto.scegli(cfg, modello=131072, memoria=106000, tempo=14278, note=note)
verifica("fase 1: il tempo non scende sotto contesto_ripiego, e lo dice",
         (fin, mot) == (16384, "tempo") and any("darebbe 12.288" in n for n in note), note)
note = []
fin, mot = contesto.scegli(cfg, modello=None, memoria=None, tempo=None, note=note)
verifica("nessun dato → contesto_ripiego, motivo «ripiego», detto",
         (fin, mot) == (16384, "ripiego") and len(note) == 3, (fin, mot, note))
note = ["memoria: la cache del server non si legge (/metrics)"]
contesto.scegli(cfg, modello=131072, memoria=None, tempo=60000, note=note)
verifica("una nota già precisa non si ripete", len(note) == 1, note)

srv = {"modello": 131072, "kv": contesto.kv_ollama(E4B), "caricato": 16384}
b = contesto.calcola(cfg, srv, velocita=2700.0, prefisso=7258,
                     libera=(1.6e9, "nvidia-smi"), riserva=3000)
atteso_mem = int(16384 + (1.6e9 - 0.5e9) / (16384 * 1.1))
verifica("Ollama locale: memoria = finestra caricata + (libera − margine) / byte a token",
         b.memoria == atteso_mem and b.memoria_fonte == "nvidia-smi", b)
verifica("tempo = prefisso + velocità × 1,5 s + riserva", b.tempo == int(7258 + 4050 + 3000),
         b.tempo)
verifica("portatile come il 05/10: 16 384 (tempo, col pavimento)", (b.finestra, b.motivo)
         == (16384, "tempo"), b.frase())
cfg2 = fase1()
cfg2.contesto_conversazioni = 2
b2 = contesto.calcola(cfg2, srv, velocita=2700.0, prefisso=7258,
                      libera=(1.6e9, "nvidia-smi"), riserva=3000)
verifica("due conversazioni: la memoria si divide", b2.memoria == atteso_mem // 2, b2.memoria)
cfg3 = fase1()
cfg3.llm_native_url = "http://192.168.1.50:11434"
b3 = contesto.calcola(cfg3, srv, velocita=2700.0, prefisso=7258,
                      libera=(1.6e9, "nvidia-smi"), riserva=3000)
verifica("Ollama su un'altra macchina: la memoria di qui non conta, e lo dice",
         b3.memoria is None and any("altra macchina" in n for n in b3.note), b3.note)
cfg4 = fase1()
cfg4.llm_backend, cfg4.llm_base_url, cfg4.llm_model = "openai", "http://127.0.0.1:8001/v1", "g"
b4 = contesto.calcola(cfg4, {"modello": 131072, "cache": 684374}, velocita=2800.0,
                      prefisso=7263, libera=None, riserva=3000)
verifica("vLLM: memoria dai token della cache del server", b4.memoria == 684374 and
         b4.finestra == 16384, b4.frase())
cfg5 = fase1()
cfg5.contesto_rilettura_max_s = 10.0
b5 = contesto.calcola(cfg5, {"modello": 262144, "kv": contesto.kv_ollama(B26),
                             "caricato": 16384}, velocita=3200.0, prefisso=7262,
                      libera=(36e9, "meminfo"), riserva=3000)
verifica("DGX con 10 s di rilettura: limita il tempo (42 262 → 40 960)",
         (b5.finestra, b5.motivo) == (40960, "tempo"), b5.frase())

# Fase 2 (compressione accesa, il predefinito): la storia si ferma alla soglia morbida, e la
# finestra è quella in cui la storia alla soglia si rilegge in contesto_rilettura_max_s (4 s)
cfg6 = Config()
verifica("predefiniti: compressione accesa, 4 s di rilettura", contesto.compressione(cfg6)
         and cfg6.contesto_rilettura_max_s == 4.0)
b6 = contesto.calcola(cfg6, srv, velocita=2670.0, prefisso=7300,
                      libera=(2.1e9, "nvidia-smi"), riserva=3000)
verifica("portatile (2 670 token/s): (7 300 + 2 670 × 4) / 0,75 = 23 973 → 20 480",
         b6.tempo == int((7300 + 2670 * 4) / 0.75) and b6.finestra == 20480, b6.frase())
b7 = contesto.calcola(cfg6, {"modello": 262144, "kv": contesto.kv_ollama(B26),
                             "caricato": 16384}, velocita=3265.0, prefisso=7258,
                      libera=(49e9, "meminfo"), riserva=3000)
verifica("DGX (26B, 3 265 token/s): (7 258 + 3 265 × 4) / 0,75 = 27 087 → 24 576",
         b7.finestra == 24576 and b7.motivo == "tempo", b7.frase())
cfg8 = Config()
cfg8.contesto_soglia_morbida = 0.5
b8 = contesto.calcola(cfg8, {"modello": 262144, "kv": contesto.kv_ollama(B26),
                             "caricato": 16384}, velocita=3265.0, prefisso=7258,
                      libera=(49e9, "meminfo"), riserva=3000)
verifica("soglia morbida più bassa: la finestra cresce (la storia si ferma prima)",
         b8.finestra == 36864, b8.frase())


# ─────────────────────────── 4. llm_num_ctx ───────────────────────────
verifica("predefinito «auto»", Config().llm_num_ctx == "auto")
verifica("numero(): intero, «auto», «32768» come testo",
         (contesto.numero(16384), contesto.numero(" Auto "), contesto.numero("32768"))
         == (16384, "auto", 32768))
for cattivo in ("tanti", True, 3.5, None):
    try:
        contesto.numero(cattivo)
        verifica(f"numero({cattivo!r}) rifiutato", False)
    except ValueError:
        verifica(f"numero({cattivo!r}) rifiutato", True)


def carica(testo: str, locale_txt: str | None = None):
    f = TMP / "c.yaml"
    f.write_text(testo, encoding="utf-8")
    loc = TMP / "c.locale.yaml"
    if locale_txt is None:
        loc.unlink(missing_ok=True)
    else:
        loc.write_text(locale_txt, encoding="utf-8")
    vecchio = os.environ.get("CALLIOPE_CONFIG_LOCALE")
    os.environ["CALLIOPE_CONFIG_LOCALE"] = str(loc)
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            c = load_config(str(f))
    finally:
        if vecchio is None:
            os.environ.pop("CALLIOPE_CONFIG_LOCALE", None)
        else:
            os.environ["CALLIOPE_CONFIG_LOCALE"] = vecchio
    return c, out.getvalue()


c, log = carica("llm:\n  llm_num_ctx: auto\n")
verifica("«auto» dal file", c.llm_num_ctx == "auto", log)
c, log = carica("llm:\n  llm_num_ctx: 32768\n")
verifica("un numero dal file", c.llm_num_ctx == 32768 and contesto.finestra(c) == 32768)
c, log = carica("llm:\n  llm_num_ctx: tanti\n")
verifica("«tanti» segnalato, resta «auto»", c.llm_num_ctx == "auto" and "llm_num_ctx" in log,
         log.strip())
c, log = carica("llm:\n  llm_profilo: gemma4-26b-ollama\n", "llm:\n  llm_num_ctx: 65536\n")
verifica("il numero del file locale vince sul profilo (prima il profilo lo sovrascriveva)",
         c.llm_num_ctx == 65536 and c.llm_model == "gemma4:26b-a4b-it-qat", c.llm_num_ctx)
c, log = carica("llm:\n  llm_profilo: gemma4-e4b-ollama\n")
verifica("profilo senza numero: «auto»", c.llm_num_ctx == "auto")

# ─────────────────────────── 5. finestra() ───────────────────────────
c = Config()
verifica("«auto» senza calcolo né file: contesto_ripiego", contesto.finestra(c) == 16384)
c._contesto_scelto = 24576
verifica("«auto» dopo il calcolo di questo processo", contesto.finestra(c) == 24576)
c = Config()
c.llm_num_ctx = 12288
c._contesto_scelto = 24576
verifica("un numero scritto vince sempre", contesto.finestra(c) == 12288)

# ─────────────────────────── 6. Ollama finto: prepara e token veri ───────────────────────────
class Finto:
    richieste: list = []
    caricato = 16384
    usage_openai = True


class Gestore(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/api/ps":
            return self._json({"models": [{"name": "gemma4:e4b-it-qat",
                                           "context_length": Finto.caricato}]})
        if self.path == "/v1/models":
            return self._json({"data": [{"id": "g", "max_model_len": 131072}]})
        if self.path == "/metrics":
            raw = METRICHE.encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            return self.wfile.write(raw)
        self._json({}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        Finto.richieste.append((self.path, body))
        if self.path == "/api/show":
            return self._json({"model_info": E4B})
        if self.path == "/api/chat":
            Finto.caricato = body["options"]["num_ctx"]
            misura = body["messages"][0]["content"].startswith("[misura")
            if not body.get("stream", True):
                return self._json({"message": {"content": "c"}, "done": True,
                                   "prompt_eval_count": 7300,
                                   "prompt_eval_duration": int(2.5e9 if misura else 0.05e9),
                                   "eval_count": 1})
            righe = [{"message": {"content": "Ciao, "}, "done": False},
                     {"message": {"content": "tutto bene."}, "done": False},
                     {"message": {"content": ""}, "done": True,
                      "prompt_eval_count": 9000, "eval_count": 12,
                      "eval_duration": 150_000_000}]
            raw = "".join(json.dumps(r) + "\n" for r in righe).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            return self.wfile.write(raw)
        if self.path == "/v1/chat/completions":
            if not body.get("stream"):
                return self._json({"id": "x", "object": "chat.completion", "created": 0,
                                   "model": "g", "choices": [{"index": 0, "finish_reason":
                                                             "length", "message": {
                                                                 "role": "assistant",
                                                                 "content": "c"}}],
                                   "usage": {"prompt_tokens": 7300, "completion_tokens": 1,
                                             "total_tokens": 7301}})
            pezzi = [{"choices": [{"index": 0, "delta": {"role": "assistant",
                                                         "content": "Ciao."}}]},
                     {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}]
            if Finto.usage_openai and body.get("stream_options", {}).get("include_usage"):
                pezzi.append({"choices": [], "usage": {"prompt_tokens": 8000,
                                                       "completion_tokens": 5,
                                                       "total_tokens": 8005}})
            raw = "".join("data: " + json.dumps({"id": "x", "object": "chat.completion.chunk",
                                                 "created": 0, "model": "g", **p}) + "\n\n"
                          for p in pezzi) + "data: [DONE]\n\n"
            raw = raw.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            return self.wfile.write(raw)
        self._json({}, 404)


server = ThreadingHTTPServer(("127.0.0.1", 0), Gestore)
threading.Thread(target=server.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{server.server_address[1]}"

cfg = fase1()
cfg.llm_native_url = URL
cfg.llm_keep_alive = None
brain = Brain(cfg, ToolRegistry(), None)
brain.warmup()
verifica("riscaldamento: token del prefisso dal motore", brain.prefix_tokens == 7300)
righe: list = []
GB = 1e9
bud = contesto.prepara(cfg, brain, log=righe.append,
                       libera_fn=lambda: (16384 * 1.1 * 40000 + 0.5 * GB, "nvidia-smi"))
# velocità 7300 / 2,5 s = 2920 token/s; con il pavimento resta 16384 → nessuna ricarica.
verifica("prepara: velocità misurata con il prefisso cambiato in testa",
         bud.velocita and round(bud.velocita) == 2920 and any(
             p == "/api/chat" and b["messages"][0]["content"].startswith("[misura")
             for p, b in Finto.richieste), bud)
verifica("prepara: memoria (16 384 caricati + 40 000) e finestra 16 384 (tempo)",
         bud.memoria == 56384 and (bud.finestra, bud.motivo) == (16384, "tempo"), bud.frase())
verifica("prepara: contesto.json con la scelta e la velocità",
         json.loads((TMP / "contesto.json").read_text(encoding="utf-8"))[contesto.chiave(cfg)]
         ["finestra"] == 16384)
# Rilettura più lunga: la finestra cresce, il modello si ricarica con il num_ctx nuovo
cfg.contesto_rilettura_max_s = 8.0
Finto.richieste.clear()
bud = contesto.prepara(cfg, brain, log=righe.append,
                       libera_fn=lambda: (16384 * 1.1 * 40000 + 0.5 * GB, "nvidia-smi"))
chat = [b for p, b in Finto.richieste if p == "/api/chat"]
verifica("velocità riusata da contesto.json (nessuna misura nuova)",
         not any(b["messages"][0]["content"].startswith("[misura") for b in chat), len(chat))
# 7300 + 2920 × 8 + 3000 = 33 660 → 32 768
verifica("finestra nuova (tempo 8 s): 32 768, e riscaldamento con quel num_ctx",
         bud.finestra == 32768 and chat and chat[-1]["options"]["num_ctx"] == 32768,
         (bud.frase(), [b["options"]["num_ctx"] for b in chat]))
verifica("dopo: ogni richiesta con lo stesso num_ctx", contesto.finestra(cfg) == 32768)
cfg_altro = Config()
cfg_altro.llm_native_url = URL
verifica("un altro processo (prove, scrittore) legge la scelta da contesto.json",
         contesto.finestra(cfg_altro) == 32768)
from calliope.agenti.impostazioni import opzioni_voce  # noqa: E402
verifica("agenti e archivio sullo stesso Ollama: num_ctx della voce",
         opzioni_voce(cfg, URL, cfg.llm_model)["options"]["num_ctx"] == 32768)
# Un numero scritto vince: niente ricarica, il calcolo resta per calliope stato
cfg.llm_num_ctx = 16384
Finto.richieste.clear()
bud = contesto.prepara(cfg, brain, log=righe.append,
                       libera_fn=lambda: (16384 * 1.1 * 40000 + 0.5 * GB, "nvidia-smi"))
chat = [b for p, b in Finto.richieste if p == "/api/chat"]
verifica("numero scritto: fonte configurazione, «auto» darebbe 32 768, nessuna ricarica",
         (bud.finestra, bud.fonte, bud.auto, len(chat)) == (16384, "configurazione", 32768, 0),
         bud.frase())
verifica("calliope stato: la scelta e perché", "scritta in llm_num_ctx" in
         (contesto.testo_stato(cfg) or ""), contesto.testo_stato(cfg))

# Token veri a ogni turno (Ollama nativo)
cfg.llm_num_ctx = "auto"
detto = "".join(brain.stream_reply("Ciao, come stai?", "amministra"))
verifica("Ollama: token del turno = prompt_eval_count + eval_count, sulla finestra",
         brain.last_context == {"token": 9012, "finestra": 32768, "percento": 28},
         (detto, brain.last_context))
verifica("Ollama: generazione del turno da eval_count ed eval_duration (fase 0, 08/10)",
         brain.last_generazione == {"token": 12, "ns": 150_000_000}, brain.last_generazione)
verifica("riga per la console", contesto.riga(brain.last_context)
         == "[CONTESTO] 9.012 token su 32.768 (28 %)")
# API OpenAI (vLLM): stream_options.include_usage e l'ultimo pezzo con usage
cfg_o = Config()
cfg_o.llm_backend, cfg_o.llm_base_url, cfg_o.llm_model = "openai", URL + "/v1", "g"
cfg_o.llm_num_ctx = 16384
bo = Brain(cfg_o, ToolRegistry(), None)
Finto.richieste.clear()
"".join(bo.stream_reply("Ciao", "amministra"))
corpo = next(b for p, b in Finto.richieste if p == "/v1/chat/completions")
verifica("API OpenAI: chiede include_usage e conta i token",
         corpo.get("stream_options") == {"include_usage": True}
         and bo.last_context == {"token": 8005, "finestra": 16384, "percento": 49},
         bo.last_context)
Finto.usage_openai = False
"".join(bo.stream_reply("Ciao", "amministra"))
verifica("server senza usage: nessun conteggio, la risposta c'è", bo.last_context is None)
cfg_o.llm_num_ctx = "auto"
bud = contesto.prepara(cfg_o, bo, log=righe.append)
verifica("vLLM: massimo da /v1/models, memoria da /metrics",
         (bud.modello, bud.memoria) == (131072, 684374), bud.frase())
server.shutdown()

# ─────────────────────────── 7. schermi ───────────────────────────
from calliope.schermi.hub import Mittente, Schermi  # noqa: E402


class Archivio:
    versione = 1

    def elenco(self):
        return [{"id": 1, "nome": "studio", "stanza": "studio", "proprietario": "dario-id"},
                {"id": 2, "nome": "cucina", "stanza": "cucina", "proprietario": None},
                {"id": 3, "nome": "telefono di Bianca", "stanza": "telefono",
                 "proprietario": "bianca-id"}]


hub = Schermi(Config(), Archivio(), log=lambda *a: None)
ricevuti = {1: [], 2: [], 3: []}
for sid in (1, 2, 3):
    conn, _ = hub.collega(next(s for s in Archivio().elenco() if s["id"] == sid), None)
    conn.consegna = (lambda item, sid=sid: ricevuti[sid].append(item) or True)
uso = {"token": 9012, "finestra": 32768, "percento": 28}
n = hub.contesto(Mittente(persona="dario-id", nome="Dario", livello="amministra", certo=True),
                 uso)
verifica("barra: solo allo schermo personale di chi parla",
         n == 1 and [t for t, _ in ricevuti[1]] == ["contesto"] and not ricevuti[2]
         and not ricevuti[3], ricevuti)
verifica("barra: non entra nella cronologia", hub.storia(1) == [])
verifica("barra: rimandata alla pagina che si ricollega",
         hub.contesto_per({"proprietario": "dario-id"}) == uso
         and hub.contesto_per({"proprietario": None}) is None)
for k in ricevuti:
    ricevuti[k].clear()
verifica("barra: mai a un ospite né nella zona grigia",
         hub.contesto(Mittente(livello="ospite"), uso) == 0
         and hub.contesto(Mittente(persona="dario-id", livello="amministra", certo=False),
                          uso) == 0 and not any(ricevuti.values()))
pagina = (Path(__file__).resolve().parent.parent / "calliope" / "schermi" / "pagina")
js = (pagina / "schermo.js").read_text(encoding="utf-8")
verifica("pagina: la barra nella testa, il telefono (incorporata) non la disegna",
         'id="contesto"' in (pagina / "index.html").read_text(encoding="utf-8")
         and 'addEventListener("contesto"' in js and "if (INCORPORATA || !box) return;" in js)

print(f"\n{errori} errori" if errori else "\ntutto ok")
sys.exit(1 if errori else 0)
