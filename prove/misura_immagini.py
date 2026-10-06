import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""
Misura delle foto nella conversazione (05/10/2026, docs/ricerche/2026-10-05-immagini.md § 5):
Brain vero con Ollama locale (gemma4:e4b-it-qat), i due modi di `immagini_storia`:

- «messaggio»: ogni foto resta nel messaggio dove è arrivata per tutta la conversazione;
- «descrizione»: nei turni dopo solo una frase fatta dal modello (descrivi_immagini, dopo la
  risposta) e immagine_guarda per riguardarla.

Per ogni turno: token del prompt elaborati davvero (prompt_eval_count: la cache del prefisso
li toglie), tempo alla prima frase, tool chiamati e risposta. Uso:

    python prove/misura_immagini.py [giri] [modo…]
"""

import json
import time

from prove import immagini_finte as F
from calliope.brain import Brain, OllamaBackend, _loads_dict
from calliope.config import Config
from calliope.immagini import Immagine, prepara
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

STATS: list[dict] = []


def stream(self, messages, tools):
    """OllamaBackend.stream con le statistiche di Ollama (prompt_eval_count…)."""
    n = 0
    with self.http.stream("POST", "/api/chat", json=self._body(messages, tools)) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            obj = json.loads(line)
            msg = obj.get("message") or {}
            if msg.get("content"):
                yield "text", msg["content"]
            calls = []
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function") or {}
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    args = _loads_dict(args)
                calls.append({"id": f"call_{n}", "name": fn.get("name", ""),
                              "arguments": args})
                n += 1
            if calls:
                yield "calls", calls
            if obj.get("done"):
                STATS.append({"prompt": obj.get("prompt_eval_count", 0),
                              "prompt_s": obj.get("prompt_eval_duration", 0) / 1e9,
                              "tot": obj.get("prompt_eval_count", 0)})
                break


OllamaBackend.stream = stream


class Prof:
    def __init__(self, name):
        self.id, self.name, self.admin = name.lower(), name, True
        self.gender, self.preferred_voice, self.giovane, self.tono = "m", None, False, None


class Speakers:
    def __init__(self):
        self.p = Prof("Dario")

    def get(self, n):
        return self.p if n == "Dario" else None

    def by_id(self, i):
        return self.p if i == "dario" else None

    def known_speakers(self):
        return ["Dario"]

    def save(self):
        pass


class SC:
    current_speaker = "Dario"
    current_level = "familiare"
    identified_by = "voce"
    from_session = False
    enroll_needed = 3
    is_enrolling = False
    sfida = None


def foto(nome, lato):
    jpeg, w, h = prepara(F.jpeg(F.TUTTE[nome]().resize(
        (F.TUTTE[nome]().width * 2, F.TUTTE[nome]().height * 2))), lato)
    return Immagine(jpeg, w, h, fonte="telefono", persona="dario")


TURNI = [("scontrino", "Cosa c'è in questa foto?"),
         (None, "Quanto costano le uova?"),
         ("foto", "E in questa?"),
         (None, "Nella prima foto, qual era il totale?"),
         (None, "Di che colore è la tazza?"),
         (None, "Che ore sono?")]


def giro(modo: str, lato: int):
    cfg = Config()
    cfg.immagini_storia = modo
    cfg.immagini_lato_max = lato
    reg = build_registry(immagini={"storia": modo})
    ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SC(), speaker=None)
    b = Brain(cfg, reg, ctx)
    b.warmup()
    righe = []
    for img, testo in TURNI:
        STATS.clear()
        t0 = time.perf_counter()
        first, out = None, ""
        for piece in b.stream_reply(testo, "familiare",
                                    immagini=[foto(img, lato)] if img else None):
            if first is None and piece.strip():
                first = time.perf_counter() - t0
            out += piece
        tot = time.perf_counter() - t0
        stats = list(STATS)
        desc_s = None
        if modo == "descrizione":
            STATS.clear()
            t1 = time.perf_counter()
            if b.descrivi_immagini():
                desc_s = time.perf_counter() - t1
            dstats = list(STATS)
        righe.append({"testo": testo, "prima_s": round(first or tot, 2),
                      "prompt": [s["prompt"] for s in stats],
                      "prompt_s": round(sum(s["prompt_s"] for s in stats), 2),
                      "tool": [t["nome"] for t in b.last_tools],
                      "risposta": " ".join(out.split())[:160],
                      **({"descrizione_s": round(desc_s, 2),
                          "descrizione_prompt": [s["prompt"] for s in dstats]}
                         if desc_s else {})})
    return righe


if __name__ == "__main__":
    giri = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    modi = sys.argv[2:] or ["messaggio", "descrizione"]
    for g in range(giri):
        for modo in modi:
            print(f"\n=== {modo}, giro {g + 1} ===")
            for r in giro(modo, 1280):
                print(json.dumps(r, ensure_ascii=False))
