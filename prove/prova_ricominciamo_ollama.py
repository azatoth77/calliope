import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""La conversazione con il modello vero della voce (Ollama locale, `llm_model`), casi veri della
DGX del 09/10 con argomenti di fantasia:

A. «Ricominciamo» detto con parole sue (21:04: «No, voglio che ricominciamo da capo, quindi
   Calliope ricominciamo.» → «Certamente, ricominciamo pure» senza farlo): il modello chiama
   conversazione_nuova; nei contrari («ricominciamo il collaudo dall'inizio», «ricominciamo da
   dove eravamo», «ricomincia la lista della spesa») la conversazione non ricomincia (il tool
   non chiamato, o chiamato con la cosa nominata in `cosa`, che lo ferma).
B. Dopo una pausa (19:06): la conversazione della pizza e del foglio delle spese chiusa per
   tempo; «scusami, ma cos'è che ti ho chiesto esattamente?» → la risposta nomina la pizza o
   il foglio (dalla coda degli ultimi scambi), mai i video della conversazione vecchia.
C. La risposta uguale alla precedente (19:06:49): dopo la frase lunga su Christopher Nolan,
   «Punto prima.»: quante volte il modello la ripete (la rete la trattiene) e cosa dice dopo
   (solo misura, stampato).

    python prove\\prova_ricominciamo_ollama.py      # 3 giri
    python prove\\prova_ricominciamo_ollama.py 1    # 1 giro
"""

import re
import tempfile
import time
from pathlib import Path

from calliope.brain import Brain
from calliope.config import Config
from calliope.conversazione import Conversazione, turni
from calliope.conversazioni import ArchivioConversazioni
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
conteggi: dict = {}
NOLAN = ("Mi hai chiesto esattamente cos'è che mi avevi chiesto un attimo fa. Un loop degno di "
         "un film di Christopher Nolan, ma con meno effetti speciali.")


class Prof:
    def __init__(self, pid, name, admin=False):
        self.id, self.name, self.admin = pid, name, admin
        self.nascita = self.fascia = self.tono = self.preferred_tone = None
        self.tutori = []


class Speakers:
    def __init__(self):
        self.p = {"Carlo": Prof("carlo-id", "Carlo", True)}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    def __init__(self):
        self.current_speaker, self.current_level, self.from_session = "Carlo", "amministra", False
        self.identified_by = "voce"
        self.sfida = self.incerta = self.minore_vicino = self.minore_incerto = None
        self.voce_sicura, self.conferma_breve, self.sfida_superata = "Carlo", False, False


CARTELLA = tempfile.mkdtemp(prefix="calliope-ricomincia-")


def archivio():
    """Un archivio con la conversazione delle 12:41 del caso vero (qui: i video, con
    «esattamente» in più turni)."""
    a = ArchivioConversazioni(Path(CARTELLA) / f"a-{time.time_ns()}.db", embedder=None,
                              log=lambda s: None, avvia=False)
    c = Conversazione()
    c.luogo = "telefono"
    msgs = []
    for d, r in (("Riesci a vedere i video esattamente?", "No, i video non li vedo."),
                 ("Esattamente cosa vedi allora?", "Le foto che mi mandi.")):
        msgs += [{"role": "user", "content": d}, {"role": "assistant", "content": r}]
    a.archivia(c, turni(msgs, quando=time.time() - 6 * 3600), "carlo-id", "Carlo", False)
    a.attendi()
    return a


def nuovo(arch=None):
    cfg = Config()
    reg = build_registry(conversazioni=True)
    ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(), speaker=None,
                      conversazioni=arch)
    b = Brain(cfg, reg, ctx)
    b.archivio_conv = arch
    b.compressore = None
    b.chiamate = []
    vera = reg.call

    def call(nome, args, ctx_, level=None, **kw):
        b.chiamate.append(nome if nome != "conversazione_nuova"
                          else f"{nome}({(args or {}).get('cosa', '')!r})")
        return vera(nome, args, ctx_, level, **kw)
    reg.call = call
    b.luogo_fn = lambda: "telefono"
    return b


def parla(b, frase):
    b.chiamate = []
    r = "".join(b.stream_reply(frase, "amministra")).strip()
    return r, list(b.chiamate)


def conta(chiave, ok, giro, frase, ch, r):
    c = conteggi.setdefault(chiave, [0, 0])
    c[0] += bool(ok)
    c[1] += 1
    print(f"{'ok ' if ok else '-- '} [{giro}] {chiave}: «{frase[:50]}» → {ch or '—'}  "
          f"{r[:160]!r}", flush=True)


def storia(b):
    parla(b, "Che pizza mi consigli stasera?")
    parla(b, "E una birra da abbinarci?")


def giro(g):
    # A. ricominciare
    for frase in ("No, voglio che ricominciamo da capo, quindi Calliope ricominciamo.",
                  "Basta, facciamo finta di niente e ripartiamo da zero.",
                  "Dimentica quello che ci siamo detti adesso e ricominciamo."):
        b = nuovo()
        storia(b)
        r, ch = parla(b, frase)
        conta("A ricomincia", getattr(b.tool_ctx, "conversazione_nuova", False), g, frase, ch,
              r)
    for frase in ("Ricominciamo il collaudo dall'inizio.", "Ricominciamo da dove eravamo.",
                  "Ricomincia la lista della spesa da capo."):
        b = nuovo()
        storia(b)
        r, ch = parla(b, frase)
        # Conta che la conversazione non ricominci (il tool può essere chiamato con la cosa
        # nominata in «cosa», e allora non fa niente)
        conta("A contrario", not getattr(b.tool_ctx, "conversazione_nuova", False), g, frase,
              ch, r)
    # B. dopo una pausa
    a = archivio()
    b = nuovo(a)
    parla(b, "Che pizza mi consigli stasera?")
    parla(b, "Fammi un foglio Excel con le spese della settimana")
    b.end_conversation("conversazione_scaduta")
    a.attendi()
    frase = "Scusami, ma cos'è che ti ho chiesto esattamente?"
    r, ch = parla(b, frase)
    conta("B dopo la pausa", bool(re.search(r"pizz|excel|foglio|spese", r, re.I))
          and "video" not in r.lower(), g, frase, ch, r)
    # C. la risposta uguale (solo misura)
    b = nuovo()
    parla(b, "Cos'è che ti ho chiesto?")
    b.history[-1]["content"] = NOLAN
    r, ch = parla(b, "Punto prima.")
    conta("C ripetuta trattenuta (misura)", "spinta_ripetuta" in b.rules_fired(), g,
          "Punto prima.", ch, r)


t0 = time.time()
for g in range(1, GIRI + 1):
    giro(g)
print("\n── riepilogo ──")
for k, (ok, n) in conteggi.items():
    print(f"{k}: {ok}/{n}")
print(f"{time.time() - t0:.0f} s")
gravi = sum(n - ok for k, (ok, n) in conteggi.items() if not k.startswith("C"))
sys.exit(1 if gravi > GIRI else 0)
