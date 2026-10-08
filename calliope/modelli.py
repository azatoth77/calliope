"""
Catalogo dei modelli e delle macchine per il piano (08/10/2026, fase 1 della taratura della
macchina: docs/ricerche/2026-10-07-taratura-macchina.md, §2–§3).

Solo dati, versionati (`VERSIONE`): niente codice di decisione (quello è calliope/piano.py) e
niente testo per il prompt del modello. Ogni numero ha accanto la fonte e la data, con la
legenda della ricerca:

- **[M]** misurato da noi (portatile o DGX), con il giorno;
- **[V]** verificato su fonte primaria (scheda del modello, config.json, libreria Ollama,
  scheda tecnica del produttore);
- **[A]** dichiarato dal produttore, non verificato da altri;
- **[Agg]** aggregatori, blog, forum;
- **[D]** deduzione o stima, da misurare.

Un modello installato vale più del catalogo: la forma della cache si legge da `/api/show`
(`contesto.kv_ollama`) e la memoria vera da `/api/ps`. La **qualità** si decide solo col
nostro banco (`prove/prova_regressione.py`, `prova_*_ollama`): un modello «da provare» si
mostra con la stima, ma il piano non lo sceglie da solo (§4.2).

I modelli cambiano ogni mese: il catalogo si rivede a ogni cambio del modello della voce.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

VERSIONE = "2026-10-08"
GB = 1e9

# Efficienza della generazione (η della §3.5) finché la macchina non ha una misura sua: le
# nostre misure danno 0,45–0,68, i banchi pubblicati di llama.cpp 0,65–0,85
ETA = 0.55
# Sopra ~250 token/s il costo fisso di Ollama per token conta più della banda [D]
TETTO_TPS = 250.0
# Lettura del prompt (prefill) di riferimento, sulla DGX (GB10) con il 26B [M 05/10]: per i
# modelli mai misurati la si scala con i parametri attivi e con `lettura_rel` della GPU
LETTURA_RIF = 3164.0
ATTIVI_RIF = 3.8


@dataclass(frozen=True)
class Misura:
    """Una misura nostra di un modello su una macchina (chiave della GPU in GPU, o «cpu»)."""
    tps: float | None = None            # generazione, token/s
    lettura: float | None = None        # lettura del prompt, token/s
    prima_frase_s: float | None = None  # prima frase «pulita» del banco
    fonte: str = ""


@dataclass(frozen=True)
class Modello:
    nome: str                     # tag di Ollama (o nome servito da vLLM)
    ruoli: tuple[str, ...]        # voce, agente, guardiano, rilevatore, embedding
    motore: str                   # "ollama" | "vllm"
    parametri_b: float            # miliardi di parametri
    attivi_b: float               # attivi a ogni token (MoE), o effettivi
    file_gb: float                # file dichiarato
    pesi_gb: float                # in memoria senza cache (misurato dove si può)
    letti_gb: float               # W della §3.5: byte letti a ogni token
    kv_kib: float                 # cache per token, f16, senza FATTORE_KV (§3.4)
    kv_fissi_mib: float = 0.0     # strati «sliding»: costo fisso a posto
    contesto_max: int = 131072
    licenza: str = ""
    # Posto nella scala del banco (più alto = più bravo); None = mai provato col banco: «da
    # provare», il piano non lo sceglie da solo
    banco: int | None = None
    banco_nota: str = ""
    misure: dict = field(default_factory=dict)   # chiave GPU → Misura
    fonte: str = ""
    nota: str = ""

    @property
    def provato(self) -> bool:
        return self.banco is not None


# ─────────────────────────── modelli (§3.1 e §3.2) ───────────────────────────
# Memoria: `pesi_gb` = /api/ps meno cache (con i posti di OLLAMA_NUM_PARALLEL) e buffer, dove
# il modello è caricato da noi; altrimenti file × 0,95 [D]. Il piano aggiunge cache, buffer e
# contesto CUDA (piano.memoria_modello).
MODELLI: dict[str, Modello] = {m.nome: m for m in (
    # Voce: gli unici tre provati col banco e con le reti (PROFILI_LLM)
    Modello("gemma4:26b-a4b-it-qat", ("voce", "agente", "rilevatore"), "ollama", 25.2, 3.8,
            16.0, 14.6, 2.3, 20, 200, 262144, "Apache 2.0", banco=3,
            banco_nota="banco 110/116 e 143/144 con le reti (03/10)",
            misure={"GB10": Misura(76, 3164, 0.70, "[M] DGX 03–05/10: 74–79 token/s, lettura "
                                   "3 164, prima frase 0,68–0,73 s")},
            fonte="[V] ollama.com/library/gemma4 (07/10); [M] DGX /api/ps 16,6 GB a 28 672 "
                  "token con due posti (07/10)",
            nota="voce della DGX dal 06/10"),
    Modello("gemma4:e4b-it-qat", ("voce", "rilevatore"), "ollama", 8.0, 4.5, 6.1, 2.67, 2.6,
            16, 20, 131072, "Apache 2.0", banco=2,
            banco_nota="banco 98–101/116 e 139/144 con le reti (02–03/10)",
            misure={"RTX 5070 Laptop": Misura(76, 2670, 0.47, "[M] portatile 02–05/10: 64–88 "
                                              "token/s, lettura 2 670–4 600, prima frase "
                                              "0,45–0,48 s"),
                    "GB10": Misura(65, None, None, "[M] DGX 03/10: 60–71 token/s")},
            fonte="[V] ollama.com/library/gemma4 (07/10); [M] DGX /api/ps 3,1 GB a 2 048 "
                  "(07/10)",
            nota="voce del portatile; rilevatore di pericolo sulla DGX"),
    Modello("gemma4:e2b-it-qat", ("voce",), "ollama", 5.1, 2.3, 4.3, 2.0, 1.4, 6, 6, 131072,
            "Apache 2.0", banco=1, banco_nota="delega 15/22 contro 22/22 del 4B (02/10)",
            misure={"RTX 5070 Laptop": Misura(None, None, 0.23, "[M] portatile 02/10: prima "
                                              "frase 0,23 s")},
            fonte="[V] ollama.com/library/gemma4 (07/10); pesi in memoria [D]"),
    # Voce: candidati da provare (§3.1), mai scelti da soli
    Modello("gemma4:12b-it-qat", ("voce",), "ollama", 11.95, 11.95, 7.2, 6.9, 6.7, 48, 0,
            262144, "Apache 2.0", fonte="[V] ollama.com/library/gemma4 (07/10); cache [D]",
            nota="denso: passa la soglia solo da ~672 GB/s in su (§4.2)"),
    Modello("qwen3.5:9b", ("voce",), "ollama", 9.7, 9.7, 6.6, 6.3, 6.0, 32, 0, 262144,
            "Apache 2.0", fonte="[V] ollama.com/library/qwen3.5 (07/10); cache dalla forma "
                                "[M] (qwen3.5:4b, portatile)",
            nota="thinking acceso di serie; il 4B delegava 17/22 (02/10)"),
    Modello("gpt-oss:20b", ("agente",), "ollama", 21.0, 3.6, 14.0, 13.3, 2.2, 24, 3, 131072,
            "Apache 2.0",
            misure={"GB10": Misura(50, None, None, "[Agg] LMSYS: 49,7 token/s su Ollama")},
            fonte="[V] ollama.com/library/gpt-oss (07/10); cache dalla forma [M] (DGX)",
            nota="thinking non spegnibile: mai come voce"),
    Modello("qwen3.6:35b", ("agente",), "ollama", 35.0, 3.0, 24.0, 22.6, 1.8, 20, 0, 262144,
            "Apache 2.0", fonte="[V] ollama.com/library/qwen3.6 (07/10); cache dalla forma [M] "
                                "(DGX, 08/10)",
            nota="su Ollama errore 500 del parser nelle conversazioni lunghe (issue #16383, "
                 "02/10): meglio su vLLM dove c'è"),
    # Agente su vLLM: memoria = gpu_memory_utilization × memoria (prenotata all'avvio)
    Modello("qwen3.6-35b", ("agente",), "vllm", 35.0, 3.0, 24.0, 24.0, 1.8, 20, 0, 131072,
            "Apache 2.0", banco=2, banco_nota="banco codice 11/12, documenti 10–11/12 (02/10)",
            misure={"GB10": Misura(76, None, None, "[M] DGX 03/10, vLLM NVFP4")},
            fonte="nvidia/Qwen3.6-35B-A3B-NVFP4; [M] DGX: gpu_memory_utilization 0,4, cache "
                  "fp8 da 2,1 M token (07/10)"),
    # Guardiano e rilevatore (§3.2)
    Modello("llama-guard3:8b", ("guardiano",), "ollama", 8.0, 8.0, 4.9, 4.4, 4.9, 128, 0,
            131072, "Llama 3.1 Community", banco=2,
            banco_nota="0 falsi su 33 frasi giuste, 12/14 vietate fermate (05/10)",
            fonte="[M] DGX /api/ps 5,3 GB a 2 048 con due posti (07/10)"),
    Modello("llama-guard3:1b", ("guardiano",), "ollama", 1.5, 1.5, 1.6, 1.5, 1.6, 32, 0,
            131072, "Llama 3.2 Community", banco=1,
            banco_nota="qualità sul banco dei minori non misurata",
            fonte="[V] ollama.com/library/llama-guard3 (07/10); pesi in memoria [D]"),
    # Embedding delle conversazioni: sulla CPU, a Calliope inattiva
    Modello("qwen3-embedding:0.6b", ("embedding",), "ollama", 0.6, 0.6, 0.64, 0.64, 0.64,
            112, 0, 32768, "Apache 2.0", banco=1, banco_nota="17/18 contro 15/18 (05/10)",
            fonte="[V] ollama.com/library/qwen3-embedding (07/10)"),
)}

# Le scale dei ripieghi (§4.4), dalla più bella alla più piccola. Solo i modelli provati
SCALA_VOCE = ("gemma4:26b-a4b-it-qat", "gemma4:e4b-it-qat", "gemma4:e2b-it-qat")
CANDIDATI_VOCE = ("gemma4:12b-it-qat", "qwen3.5:9b")      # da provare (decisione aperta 2)
SCALA_GUARDIANO = ("llama-guard3:8b", "llama-guard3:1b")
RILEVATORE = "gemma4:e4b-it-qat"
EMBEDDING = "qwen3-embedding:0.6b"
AGENTE_VLLM = "qwen3.6-35b"
AGENTE_OLLAMA = "qwen3.6:35b"


# ─────────────────────────── Whisper e Piper (§3.3) ───────────────────────────
@dataclass(frozen=True)
class Trascrizione:
    nome: str
    motore: str          # "faster-whisper" | "whisper.cpp"
    dispositivo: str     # "gpu" | "cpu"
    memoria_gb: float    # memoria del processo (GPU, o RAM sulla CPU)
    frase_s: float       # tempo a frase
    fonte: str


WHISPER = {
    "fw-gpu": Trascrizione("large-v3-turbo", "faster-whisper", "gpu", 1.27, 0.2,
                           "[M] portatile 24/09: +1,18 GiB, 0,19–0,24 s a frase, WER 10,6–11,5 %"),
    "cpp-gpu": Trascrizione("large-v3-turbo", "whisper.cpp", "gpu", 2.1, 0.17,
                            "[M] DGX 05–07/10: ~2,1 GB, 0,16–0,17 s di mediana"),
    "turbo-cpu": Trascrizione("large-v3-turbo", "faster-whisper", "cpu", 1.6, 5.0,
                              "[M] portatile: ~5 s a frase sulla CPU (ripiego visto)"),
    "small-cpu": Trascrizione("small", "faster-whisper", "cpu", 1.0, 1.0,
                              "[D] da misurare con misura_stt.py; README di faster-whisper: "
                              "small int8 su i7-12700K 13 min di audio in 1 min 42 s [V]"),
}
# Piper sulla GPU (07/10, calliope/taratura_voce.py): 1,34–1,45 GiB nel processo [M DGX]
PIPER_GPU_GB = 1.5
# Immagini a richiesta: FLUX.2 [klein] 4B con l'encoder, ~13 GB [V, scheda] (ricerca del 06/10)
IMMAGINI_GB = 13.0


# ─────────────────────────── macchine (§2) ───────────────────────────
@dataclass(frozen=True)
class Gpu:
    chiave: str              # nome breve, chiave delle misure
    banda_gbs: float
    memoria_gb: float | None  # dichiarata (la VRAM vera si legge)
    unificata: bool
    lettura_rel: float       # lettura del prompt rispetto alla DGX [D]
    produttore: str          # "nvidia" | "amd" | "apple"
    fonte: str


# In ordine: il primo modello che corrisponde vince (i nomi più lunghi prima)
GPU: list[tuple[str, Gpu]] = [
    (r"GB10|DGX Spark", Gpu("GB10", 273, 128, True, 1.0, "nvidia",
                            "[V] docs.nvidia.com DGX Spark (07/10)")),
    (r"RTX Spark|N1X", Gpu("RTX Spark", 300, 128, True, 0.9, "nvidia",
                           "[V] nvidia.com/rtx-spark per la memoria; banda ~300 GB/s [Agg], "
                           "non ufficiale (07/10)")),
    (r"RTX PRO 6000", Gpu("RTX PRO 6000", 1792, 96, False, 4.5, "nvidia",
                          "[V] nvidia.com (07/10)")),
    (r"RTX 6000 Ada", Gpu("RTX 6000 Ada", 960, 48, False, 3.0, "nvidia",
                          "[V] Lenovo Press LP1940 (07/10)")),
    (r"RTX 5090", Gpu("RTX 5090", 1792, 32, False, 4.0, "nvidia",
                      "[Agg] Wikipedia RTX 50 (07/10)")),
    (r"RTX 4090", Gpu("RTX 4090", 1008, 24, False, 3.0, "nvidia",
                      "[Agg] Wikipedia RTX 40 (07/10)")),
    (r"RTX 3090", Gpu("RTX 3090", 936, 24, False, 1.4, "nvidia",
                      "[Agg] Wikipedia RTX 30 (07/10)")),
    (r"RTX 5070 Ti", Gpu("RTX 5070 Ti", 896, 16, False, 1.8, "nvidia",
                         "[Agg] Wikipedia RTX 50, kitguru (07/10)")),
    (r"RTX 4070 Ti SUPER", Gpu("RTX 4070 Ti SUPER", 672, 16, False, 1.6, "nvidia",
                               "[Agg] Wikipedia RTX 40 (07/10)")),
    (r"RTX 5060 Ti", Gpu("RTX 5060 Ti", 448, 16, False, 1.0, "nvidia",
                         "[Agg] Wikipedia RTX 50, pcper (07/10)")),
    (r"RTX 4060 Ti", Gpu("RTX 4060 Ti", 288, 16, False, 0.9, "nvidia",
                         "[Agg] Wikipedia RTX 40 (07/10)")),
    (r"RTX 5070 Laptop", Gpu("RTX 5070 Laptop", 384, 8, False, 1.0, "nvidia",
                             "[Agg] notebookcheck, laptopmedia (07/10): 128 bit GDDR7")),
    (r"Radeon 8060S|Ryzen AI Max", Gpu("Strix Halo", 256, 128, True, 0.5, "amd",
                                       "[Agg] AMD, level1techs: ~215 misurati dalla GPU "
                                       "(07/10)")),
    (r"Apple M\d Max", Gpu("Apple Max", 546, 128, True, 0.5, "apple", "[V] Apple (07/10)")),
    (r"Apple M\d Pro", Gpu("Apple Pro", 273, 64, True, 0.4, "apple", "[V] Apple (07/10)")),
]
# GPU NVIDIA non in tabella: banda prudente, detta come stima
GPU_IGNOTA = Gpu("ignota", 300, None, False, 0.8, "nvidia",
                 "[D] GPU non in tabella: banda e lettura prudenti, da misurare")
# Solo CPU: DDR5-5600 a due canali, 89,6 GB/s teorici [D: 2 canali × 8 byte × MT/s]; la
# lettura del prompt sulla CPU è 10–50 volte più lenta che sulla GPU [D]
BANDA_RAM_GBS = 89.6
LETTURA_REL_CPU = 0.03


def gpu_da_nome(nome: str | None) -> Gpu | None:
    """La riga della tabella per il nome della GPU (None se non c'è un nome)."""
    if not nome:
        return None
    for modello, g in GPU:
        if re.search(modello, nome, re.I):
            return g
    return GPU_IGNOTA


def misura(modello: str, gpu: str | None) -> Misura | None:
    m = MODELLI.get(modello)
    return m.misure.get(gpu or "cpu") if m else None
