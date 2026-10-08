import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della taratura della macchina, fasi 1 e 2 (08/10/2026,
docs/ricerche/2026-10-07-taratura-macchina.md).

- inventario (`macchina.inventario`) con sonde finte: portatile Windows con nvidia-smi, DGX con
  memoria unificata («[N/A]»), Linux senza GPU, Windows con la sola VRAM del registro, GPU fuori
  catalogo, un modello in parte sulla CPU in /api/ps, variabili di Ollama dal servizio, vLLM con
  `gpu_memory_utilization` da /metrics, server di Whisper;
- catalogo (`calliope/modelli.py`): ogni modello con fonte, scale fatte di modelli provati,
  tabella delle GPU;
- piano (`calliope/piano.py`) su macchine finte: solo CPU, 8, 16, 24, 32 GB, memoria unificata
  128 GB (la DGX di oggi: deve ritrovare le scelte fatte a mano), Windows su ARM; casi
  contrari: guardiano mai tolto in silenzio, voce mai sotto un modello secondario, un modello
  «da provare» mai scelto, niente applicato;
- `calliope stato --piano`, `--json` e `--inventario`.
"""

import contextlib
import copy
import io
import json
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="calliope-piano-"))
os.environ["CALLIOPE_CONTESTO"] = str(TMP / "contesto.json")

from calliope import macchina, modelli as cat, piano  # noqa: E402
from calliope.config import Config  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {str(dettaglio)[:600]}" if not ok
                                                  and dettaglio else ""), flush=True)


# ─────────────────────────── 1. inventario con sonde finte ───────────────────────────
class SondeFinte(macchina.Sonde):
    def __init__(self, os_="windows", arch="x86_64", base=None, smi=None, meminfo="",
                 http=None, servizio="", librerie=None, libera_win=None):
        self.os, self.arch = os_, arch
        self._base, self._smi, self._meminfo = base or {}, smi, meminfo
        self._http, self._servizio = http or {}, servizio
        self._lib = librerie or {"onnxruntime_cuda": False, "ctranslate2_cuda": 1}
        self._libera_win = libera_win
        self.chiamate = []

    def base(self):
        return self._base

    def comando(self, argv, timeout=5):
        self.chiamate.append(argv[0])
        if argv[0] == "nvidia-smi":
            return self._smi
        if argv[0] == "systemctl" and "--user" not in argv:
            return self._servizio
        return None

    def leggi(self, path):
        return self._meminfo if path == "/proc/meminfo" else ""

    def get(self, url, timeout=1.5):
        for k, v in self._http.items():
            if url.endswith(k):
                return v if isinstance(v, str) else json.dumps(v)
        return None

    def libera_windows(self):
        return self._libera_win

    def librerie(self):
        return dict(self._lib)


OLLAMA_PORTATILE = {
    "11434/api/version": {"version": "0.35.1"},
    "11434/api/tags": {"models": [{"name": "gemma4:e4b-it-qat", "size": 6146501801},
                                  {"name": "llama-guard3:1b", "size": 1600181919}]},
    "11434/api/ps": {"models": [
        {"name": "gemma4:e4b-it-qat", "size": 3_100_000_000, "size_vram": 3_100_000_000,
         "context_length": 16384},
        # Il caso vero del 07/10: qwen3:8b caricato da altri a 32 768, 59 % sulla GPU
        {"name": "qwen3:8b", "size": 10_360_000_000, "size_vram": 6_140_000_000,
         "context_length": 32768}]},
}
s = SondeFinte(base={"modello": "Portatile", "processore": "Intel Core Ultra 9", "core": 24,
                     "memoria_gb": 31.46, "sistema": "Windows 11",
                     "gpu": [("NVIDIA GeForce RTX 5070 Laptop GPU", 7.96)]},
               smi="NVIDIA GeForce RTX 5070 Laptop GPU, 8151, 547, 616.92\n",
               http=OLLAMA_PORTATILE, libera_win=6.5)
inv8 = macchina.inventario(Config(), s)
g = inv8["gpu"]
verifica("portatile: nvidia-smi in MiB → GB, GPU dedicata, banda dalla tabella",
         g["memoria_gb"] == 8.55 and g["libera_gb"] == 0.57 and not g["unificata"]
         and g["banda_gbs"] == 384 and g["chiave"] == "RTX 5070 Laptop", g)
verifica("portatile: RAM da GlobalMemoryStatusEx, libera da Windows",
         inv8["ram_gb"] == 33.78 and inv8["ram_libera_gb"] == 6.5, inv8)
o = inv8["motori"]["ollama"]
verifica("Ollama: versione, installati, caricati con contesto",
         o["versione"] == "0.35.1" and len(o["installati"]) == 2
         and o["caricati"][0]["contesto"] == 16384, o)
verifica("modello in parte sulla CPU (size_vram < size): avviso",
         o["caricati"][1]["in_parte_cpu"] and not o["caricati"][0]["in_parte_cpu"]
         and any("qwen3:8b" in a and "CPU" in a for a in inv8["avvisi"]), inv8["avvisi"])
verifica("Windows: niente systemctl", "systemctl" not in s.chiamate, s.chiamate)
verifica("nessun vLLM né server di Whisper", inv8["motori"]["vllm"] == []
         and inv8["motori"]["whisper_server"] is None)
verifica("JSON serializzabile", json.loads(json.dumps(inv8)) == inv8)

MEMINFO_DGX = "MemTotal:       125439440 kB\nMemFree: 1 kB\nMemAvailable:   21300000 kB\n"
METRICHE = ('vllm:cache_config_info{block_size="2096",cache_dtype="fp8",'
            'gpu_memory_utilization="0.4",kv_cache_size_tokens="2116147"} 1.0\n')
HTTP_DGX = {
    "11434/api/version": {"version": "0.35.0"},
    "11434/api/tags": {"models": [{"name": n, "size": 1} for n in (
        "gemma4:26b-a4b-it-qat", "gemma4:e4b-it-qat", "llama-guard3:8b",
        "qwen3-embedding:0.6b")]},
    "11434/api/ps": {"models": [
        {"name": "gemma4:26b-a4b-it-qat", "size": 16557140867, "size_vram": 16557140867,
         "context_length": 28672},
        {"name": "llama-guard3:8b", "size": 5269618687, "size_vram": 5269618687,
         "context_length": 2048},
        {"name": "gemma4:e4b-it-qat", "size": 3126088170, "size_vram": 3126088170,
         "context_length": 2048}]},
    "8000/v1/models": {"data": [{"id": "qwen3.6-35b", "root": "nvidia/Qwen3.6-35B-A3B-NVFP4",
                                 "max_model_len": 131072}]},
    "8000/version": {"version": "0.29.0"},
    "8000/metrics": METRICHE,
    "8003/": "<html>whisper.cpp</html>",
}
cfg_dgx = Config()
cfg_dgx.stt_motore, cfg_dgx.stt_url = "server", "http://127.0.0.1:8003/v1"
s = SondeFinte("linux", "aarch64", base={"modello": "DGX Spark", "core": 20,
                                         "sistema": "Ubuntu 24.04",
                                         "gpu": [("NVIDIA GB10", None)]},
               smi="NVIDIA GB10, [N/A], [N/A], 580.178.04\n", meminfo=MEMINFO_DGX,
               http=HTTP_DGX, servizio="Environment=OLLAMA_HOST=0.0.0.0 OLLAMA_NUM_PARALLEL=2 "
                                       "OLLAMA_MAX_LOADED_MODELS=4\n",
               librerie={"onnxruntime_cuda": True, "ctranslate2_cuda": 0})
inv_dgx = macchina.inventario(cfg_dgx, s)
g = inv_dgx["gpu"]
verifica("DGX: nvidia-smi «[N/A]» → memoria unificata, il pool è la RAM di /proc/meminfo",
         g["unificata"] and g["memoria_gb"] == 128.45 and g["libera_gb"] == 21.81
         and g["banda_gbs"] == 273 and g["chiave"] == "GB10", g)
verifica("DGX: variabili di Ollama dal servizio systemd",
         inv_dgx["motori"]["ollama"]["variabili"] == {"OLLAMA_NUM_PARALLEL": "2",
                                                      "OLLAMA_MAX_LOADED_MODELS": "4"},
         inv_dgx["motori"]["ollama"]["variabili"])
v = inv_dgx["motori"]["vllm"]
verifica("DGX: vLLM con modello, versione, cache e gpu_memory_utilization da /metrics",
         len(v) == 1 and v[0]["modelli"][0]["id"] == "qwen3.6-35b" and v[0]["versione"] ==
         "0.29.0" and v[0]["cache_token"] == 2116147 and v[0]["gpu_memory_utilization"] == 0.4,
         v)
verifica("DGX: server di Whisper locale che risponde, CUDA per onnxruntime sì e CTranslate2 no",
         inv_dgx["motori"]["whisper_server"] == {"locale": True, "attivo": True}
         and inv_dgx["motori"]["onnxruntime_cuda"] is True
         and inv_dgx["motori"]["ctranslate2_cuda"] == 0, inv_dgx["motori"])
verifica("DGX: nessun avviso", inv_dgx["avvisi"] == [], inv_dgx["avvisi"])

s = SondeFinte("linux", "x86_64", base={"core": 16, "sistema": "Debian 13", "gpu": []},
               smi=None, meminfo="MemTotal: 32000000 kB\nMemAvailable: 20000000 kB\n")
inv_cpu = macchina.inventario(Config(), s)
verifica("Linux senza GPU né Ollama: gpu None, motori vuoti, niente crash",
         inv_cpu["gpu"] is None and inv_cpu["motori"]["ollama"] is None
         and inv_cpu["ram_gb"] == 32.77, inv_cpu)
s = SondeFinte(base={"memoria_gb": 63.7, "gpu": [("NVIDIA GeForce RTX 5090", 31.5)]}, smi=None)
inv = macchina.inventario(Config(), s)
verifica("Windows senza nvidia-smi: la VRAM dal registro (fonte detta)",
         inv["gpu"]["memoria_gb"] == 33.82 and inv["gpu"]["fonte"] == "registro"
         and inv["gpu"]["banda_gbs"] == 1792, inv["gpu"])
s = SondeFinte(smi="NVIDIA RTX A4000, 16376, 16000, 580\n")
inv = macchina.inventario(Config(), s)
verifica("GPU fuori catalogo: banda prudente e avviso «da misurare»",
         inv["gpu"]["chiave"] == "ignota" and any("non nel catalogo" in a
                                                   for a in inv["avvisi"]), inv)
verifica("contrario: nessuna sonda solleva, base rotta compresa", macchina.inventario(
    None, type("Rotta", (SondeFinte,), {"base": lambda self: 1 / 0})()) is not None)

# ─────────────────────────── 2. catalogo ───────────────────────────
verifica("catalogo versionato", cat.VERSIONE == "2026-10-08")
verifica("ogni modello ha fonte, licenza e cache", all(m.fonte and m.licenza and m.kv_kib > 0
                                                      for m in cat.MODELLI.values()))
verifica("le scale sono fatte solo di modelli provati col banco",
         all(cat.MODELLI[n].provato for n in cat.SCALA_VOCE + cat.SCALA_GUARDIANO))
verifica("i candidati della voce non sono provati (decisione aperta 2)",
         all(not cat.MODELLI[n].provato for n in cat.CANDIDATI_VOCE))
verifica("tabella delle GPU: fonte per ogni riga, nomi più lunghi prima",
         all(g.fonte for _, g in cat.GPU) and cat.gpu_da_nome("RTX 5070 Ti").chiave ==
         "RTX 5070 Ti" and cat.gpu_da_nome("RTX 5070 Laptop GPU").chiave == "RTX 5070 Laptop"
         and cat.gpu_da_nome(None) is None)


# ─────────────────────────── 3. il piano su macchine finte ───────────────────────────
def finta(nome_gpu=None, vram=None, ram=32.0, os_="windows", arch="x86_64", unificata=False,
          vllm=None, ollama=True, variabili=None, libera=None, whisper_server=None):
    inv = {"os": os_, "arch": arch, "ram_gb": ram, "ram_libera_gb": None,
           "sistema": "Windows 11" if os_ == "windows" else "Linux", "avvisi": [],
           "motori": {"ollama": {"versione": "0.35.1", "caricati": [], "installati": [],
                                 "variabili": variabili or {}} if ollama else None,
                      "vllm": vllm or [], "whisper_server": whisper_server,
                      "onnxruntime_cuda": True, "ctranslate2_cuda": 1}}
    if nome_gpu:
        r = cat.gpu_da_nome(nome_gpu)
        inv["gpu"] = {"nome": nome_gpu, "memoria_gb": ram if unificata else vram,
                      "libera_gb": libera, "unificata": unificata or r.unificata,
                      "chiave": r.chiave, "banda_gbs": r.banda_gbs, "lettura_rel": r.lettura_rel,
                      "produttore": r.produttore}
    else:
        inv["gpu"] = None
    return inv


def scelte(p):
    return {s.ruolo: s for s in p.scelte}


def riga(p):
    return "; ".join(f"{s.ruolo}={s.scelta}/{s.dove}/{s.stato}" for s in p.scelte)


# Solo CPU
p = piano.piano(finta(None, ram=32.0, os_="linux"), piano.Funzioni())
sc = scelte(p)
verifica("solo CPU: classe, voce e Whisper sulla CPU, voce con l'avviso fuori soglia",
         p.classe == "solo CPU" and sc["voce"].dove == "CPU" and sc["voce"].stato == "avviso"
         and sc["whisper"].dove == "CPU" and sc["whisper"].scelta.startswith("small"), riga(p))
verifica("solo CPU: decisione 5 aperta (satellite o Calliope ridotta), non scelta",
         any(d["numero"] == 5 and len(d["opzioni"]) == 2 for d in p.decisioni)
         and any("satellite" in a for a in p.avvisi), p.decisioni)

# GPU 8 GB: il portatile
f8 = piano.Funzioni(agente_remoto=True)
p = piano.piano(finta("NVIDIA GeForce RTX 5070 Laptop GPU", 8.55), f8)
sc = scelte(p)
verifica("8 GB: voce e4b, Whisper sulla GPU, guardiano 1B sulla CPU con avviso, rilevatore = "
         "voce, agente remoto",
         p.classe == "GPU 8 GB" and sc["voce"].scelta == "gemma4:e4b-it-qat"
         and sc["whisper"].dove == "GPU" and sc["guardiano"].scelta == "llama-guard3:1b"
         and sc["guardiano"].dove == "CPU" and sc["guardiano"].stato == "avviso"
         and sc["rilevatore"].scelta.startswith("la voce stessa")
         and sc["agente"].dove == "remoto", riga(p))
verifica("8 GB: misura del portatile usata (76 token/s), il 26B scartato perché non ci sta",
         "76 token/s (misurata)" in sc["voce"].stima and "26b" in sc["voce"].motivo
         and "non ci sta" in sc["voce"].motivo, sc["voce"])
verifica("8 GB: decisione 3 con le due opzioni; immagini non sostenibili; Piper sulla CPU",
         any(d["numero"] == 3 for d in p.decisioni) and sc["piper"].dove == "CPU"
         and any(x.startswith("immagini") for x in p.non_sostenibili), p.non_sostenibili)
verifica("8 GB: memoria dentro il pool", p.usati_gb <= p.pool_gb and p.liberi_gb >= 0,
         (p.usati_gb, p.pool_gb))

# GPU 16 GB
p = piano.piano(finta("NVIDIA GeForce RTX 5060 Ti", 17.18), piano.Funzioni())
sc = scelte(p)
verifica("16 GB: voce e4b (il 26B non ci sta), guardiano 8B sulla GPU, rilevatore = voce",
         sc["voce"].scelta == "gemma4:e4b-it-qat" and sc["guardiano"].scelta ==
         "llama-guard3:8b" and sc["guardiano"].dove == "GPU"
         and sc["rilevatore"].scelta.startswith("la voce stessa"), riga(p))
verifica("16 GB: senza un altro computer l'agente è «da configurare» con il motivo",
         sc["agente"].scelta == "da configurare" and "altro computer" in sc["agente"].motivo,
         sc["agente"])

# GPU 24 GB
p = piano.piano(finta("NVIDIA GeForce RTX 4090", 25.77, os_="linux", ram=64), piano.Funzioni())
sc = scelte(p)
verifica("24 GB: voce 26B, Whisper sulla GPU, guardiano sulla GPU, rilevatore = la voce "
         "(e4b separato non ci sta), agente = la voce sul secondo posto",
         sc["voce"].scelta == "gemma4:26b-a4b-it-qat" and sc["whisper"].dove == "GPU"
         and sc["guardiano"].dove == "GPU" and sc["rilevatore"].scelta.startswith(
             "la voce stessa") and "secondo posto" in sc["agente"].scelta, riga(p))
verifica("24 GB: decisione 4 e la proposta di OLLAMA_NUM_PARALLEL=2",
         any(d["numero"] == 4 for d in p.decisioni)
         and any("NUM_PARALLEL=2" in x for x in p.ollama.get("proposte", [])), p.ollama)

# GPU 32 GB: la «signora macchina» (§4.8, esempio 2)
p = piano.piano(finta("NVIDIA GeForce RTX 5090", 34.36, ram=64), piano.Funzioni(satelliti=2))
sc = scelte(p)
verifica("32 GB: 26B, guardiano 8B, rilevatore e4b separato, agente = la voce sul secondo "
         "posto (Qwen3.6 separato non ci sta)",
         sc["voce"].scelta == "gemma4:26b-a4b-it-qat" and sc["guardiano"].scelta ==
         "llama-guard3:8b" and sc["rilevatore"].scelta == "gemma4:e4b-it-qat"
         and "secondo posto" in sc["agente"].scelta, riga(p))
verifica("32 GB: generazione stimata al tetto (250 token/s), memoria ~28–31 GB",
         "250 token/s (stimata)" in sc["voce"].stima and 27 <= p.usati_gb <= 33, (
             sc["voce"].stima, p.usati_gb))
verifica("32 GB: due satelliti con un posto solo → non sostenibile finché non c'è il secondo",
         any("2 satelliti" in x for x in p.non_sostenibili), p.non_sostenibili)

# Memoria unificata 128 GB: la DGX di oggi (§4.8, esempio 3)
f_dgx = piano.da_config(cfg_dgx, inv_dgx)
f_dgx.oggi.update(voce="gemma4:26b-a4b-it-qat", guardiano="llama-guard3:8b",
                  rilevatore="gemma4:e4b-it-qat")
f_dgx.rilettura_s = 3
f_dgx.contesto = {"finestra": 28672, "motivo": "tempo", "modello_voce": "gemma4:26b-a4b-it-qat"}
f_dgx.oggi["contesto"] = "28.672 token"
p = piano.piano(inv_dgx, f_dgx)
sc = scelte(p)
verifica("DGX: ritrova le scelte di oggi (26B su Ollama, whisper.cpp, guardiano 8B, rilevatore "
         "e4b separato, embedding, Qwen3.6 su vLLM, 28 672 token)",
         sc["voce"].scelta == "gemma4:26b-a4b-it-qat" and sc["voce"].oggi == "come oggi"
         and "whisper.cpp" in sc["whisper"].scelta and sc["whisper"].oggi == "come oggi"
         and sc["guardiano"].scelta == "llama-guard3:8b" and sc["guardiano"].oggi == "come oggi"
         and sc["rilevatore"].scelta == "gemma4:e4b-it-qat"
         and sc["embedding"].scelta == "qwen3-embedding:0.6b"
         and sc["agente"].scelta == "qwen3.6-35b su vLLM" and sc["agente"].dove == "vLLM"
         and sc["contesto"].scelta == "28.672 token" and sc["contesto"].oggi == "come oggi",
         riga(p))
verifica("DGX: Piper sulla GPU (c'è posto, onnxruntime con CUDA), immagini a richiesta",
         sc["piper"].dove == "GPU" and sc["immagini"].scelta.endswith("a richiesta"), riga(p))
verifica("DGX: 4 residenti su Ollama e 2 posti letti dal servizio, nessuna proposta",
         p.ollama["max_loaded_models"] == 4 and p.ollama["num_parallel"] == 2
         and not p.ollama.get("proposte"), p.ollama)
verifica("DGX: le velocità misurate (76 token/s voce e agente), prima frase pulita ≤ 0,8 s",
         "76 token/s (misurata)" in sc["voce"].stima and "76 token/s" in sc["agente"].stima
         and sc["voce"].stato == "ok", (sc["voce"].stima, sc["agente"].stima))
verifica("DGX: memoria di oggi — 21,8 GB liberi, altri programmi oltre la riserva: avviso",
         any("altri programmi" in a for a in p.avvisi), p.avvisi)
# Senza contesto.json la finestra si stima dal tempo: 24–28k con rilettura 3 s
f2 = copy.deepcopy(f_dgx)
f2.contesto = {}
p2 = piano.piano(inv_dgx, f2)
fin = int(scelte(p2)["contesto"].scelta.split()[0].replace(".", ""))
verifica("DGX senza contesto.json: finestra stimata dal tempo tra 24 e 28k", 24576 <= fin
         <= 28672, fin)

# Windows su ARM con memoria unificata (RTX Spark): niente vLLM, agente su Ollama
p = piano.piano(finta("NVIDIA RTX Spark", ram=128.0, os_="windows", arch="aarch64",
                      unificata=True), piano.Funzioni())
sc = scelte(p)
verifica("Windows su ARM: la GPU vede l'80 % dopo la riserva, Whisper con whisper.cpp, agente "
         "Qwen3.6 separato su Ollama",
         p.classe.startswith("Windows su ARM") and p.pool_gb < 110
         and "whisper.cpp" in sc["whisper"].scelta and "Ollama" in sc["agente"].scelta, riga(p))

# ─────────────────────────── 4. casi contrari ───────────────────────────
# Il guardiano non si toglie mai in silenzio: GPU piccola e poca RAM
p = piano.piano(finta("NVIDIA GeForce RTX 5070 Laptop GPU", 8.55, ram=8.0), piano.Funzioni())
sc = scelte(p)
verifica("contrario: né GPU né RAM per il guardiano → «nessun modello» con avviso, non sparito",
         sc["guardiano"].scelta == "nessun modello" and sc["guardiano"].stato == "avviso"
         and "mai spento in silenzio" in sc["guardiano"].motivo, sc["guardiano"])
verifica("contrario: la voce resta e4b (il guardiano non le toglie memoria)",
         sc["voce"].scelta == "gemma4:e4b-it-qat", riga(p))
p = piano.piano(finta("NVIDIA GeForce RTX 5090", 34.36), piano.Funzioni(guardiano=False))
sc = scelte(p)
verifica("contrario: senza minori né ospiti col guardiano → «spento», nessun rilevatore",
         sc["guardiano"].scelta == "spento" and "rilevatore" not in sc, riga(p))
verifica("contrario: un modello «da provare» non è mai scelto, anche dove ci starebbe",
         all(s.scelta not in cat.CANDIDATI_VOCE for s in p.scelte)
         and {c["modello"] for c in p.candidati} == set(cat.CANDIDATI_VOCE), p.candidati)
p = piano.piano(finta("NVIDIA GeForce RTX 5090", 34.36), piano.Funzioni(agenti=False))
verifica("contrario: agenti spenti → agente «spento», non proposto",
         scelte(p)["agente"].scelta == "spento", riga(p))
p = piano.piano(finta("NVIDIA GeForce RTX 5090", 34.36, ollama=False), piano.Funzioni())
verifica("contrario: Ollama assente → il piano c'è e lo dice", any("Ollama non risponde" in a
                                                                    for a in p.avvisi))
p = piano.piano(finta("NVIDIA GeForce RTX 4090", 25.77, variabili={
    "OLLAMA_MAX_LOADED_MODELS": "2"}), piano.Funzioni())
verifica("variabili di Ollama: limite più basso dei residenti → proposta di comando e "
         "decisione 6, nessuna modifica",
         any("OLLAMA_MAX_LOADED_MODELS=" in x for x in p.ollama.get("proposte", []))
         and any(d["numero"] == 6 for d in p.decisioni), p.ollama)
verifica("le decisioni 1 e 2 sono sempre scritte, senza doppioni",
         [d["numero"] for d in p.decisioni][:2] == [1, 2]
         and len({d["numero"] for d in p.decisioni}) == len(p.decisioni), p.decisioni)

# ─────────────────────────── 5. calliope stato --piano ───────────────────────────
from calliope import stato  # noqa: E402

file_inv = TMP / "dgx.json"
file_inv.write_text(json.dumps({"inventario": inv_dgx}), encoding="utf-8")
prima = sorted(p.name for p in TMP.iterdir())
vecchio = stato._config
stato._config = lambda quiet: cfg_dgx
try:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = stato.main(["--piano", "--inventario", str(file_inv)])
    uscita = buf.getvalue()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc2 = stato.main(["--piano", "--json", "--inventario", str(file_inv)])
    js = json.loads(buf.getvalue())
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc3 = stato.main(["--piano", "--inventario", str(TMP / "manca.json")])
finally:
    stato._config = vecchio
verifica("calliope stato --piano: macchina, classe, ruoli e «non applica niente»",
         rc == 0 and "classe «memoria unificata 128 GB»" in uscita and "Voce" in uscita
         and "gemma4:26b-a4b-it-qat" in uscita and "non applica niente" in uscita, uscita)
verifica("calliope stato --piano --json: inventario e piano",
         rc2 == 0 and js["inventario"]["gpu"]["chiave"] == "GB10"
         and any(s["ruolo"] == "voce" for s in js["piano"]["scelte"]), js.keys())
verifica("--inventario con un file che manca: errore detto, codice 1", rc3 == 1)
verifica("sola lettura: nessun file nuovo (né contesto.json né altro)",
         sorted(p.name for p in TMP.iterdir()) == prima, list(TMP.iterdir()))

print()
print("tutto ok" if not errori else f"{errori} errori")
sys.exit(1 if errori else 0)
