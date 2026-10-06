import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Conversazione multi-turno con il Brain vero (backend di Config) e un contesto finto:
verifica del prompt di sistema dopo il test vocale del 24/09/2026.

Conta avvertenze non richieste, uso del «lei», memoria della conversazione, tool,
limiti dichiarati e tempo alla prima frase. Uso: prova_prompt_conversazione.py [giri]
"""

import re
import time

import tempfile
from pathlib import Path

from calliope.brain import Brain
from calliope.memory import Memory
from calliope.config import Config
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ora_giusta import ora_giusta  # noqa: E402


class FakeProfile:
    id, name, preferred_voice, admin, gender = "dario-prova", "Dario", None, True, None


class FakeSpeakers:
    """Dal 26/09 serve un profilo vero: senza, `ricorda` rispondeva «non so chi sei» e il
    modello smetteva di chiamare tool per il resto della conversazione."""
    def known_speakers(self):
        return ["Dario"]

    def get(self, n):
        return FakeProfile() if n == "Dario" else None

    def save(self):
        pass


class FakeCtx:
    current_speaker = "Dario"
    current_level = "amministra"
    enroll_needed = 3

    def start_enroll(self, n):
        pass


class FakeSpeaker:
    def change_voice(self, p):
        return True


_WARN = re.compile(r"non ho accesso|in tempo reale|non ho (dati|informazioni)|aggiornat|"
                   r"non (posso|sono in grado)|non ho la capacità|non ho memorizzato", re.I)
_LEI = re.compile(r"\blei\b|\b\w+rle\b|\bdesidera\b|\bsuo\b|\bsua\b|\bpuò dirmi\b", re.I)
_NEG = re.compile(r"\bnon\b", re.I)


def ok_memoria(t, calls):
    return bool(re.search(r"\b47\b|quarantasette", t, re.I))


# (frase, nome della verifica, funzione(testo, tool chiamati) → bool)
CONVERSAZIONE = [
    ("Qual è la capitale della Francia?", "senza avvertenze",
     lambda t, c: "parigi" in t.lower() and not _WARN.search(t)),
    ("E quella della Spagna?", "senza avvertenze",
     lambda t, c: "madrid" in t.lower() and not _WARN.search(t)),
    ("Quanto dista la Luna dalla Terra?", "senza avvertenze",
     lambda t, c: bool(re.search(r"\d|mila", t)) and not _WARN.search(t)),
    ("Ricordati che il mio numero preferito è quarantasette.", "memoria (presa)",
     lambda t, c: not re.search(r"non (posso|riesco|ho (la capacità|la possibilità|memoria))",
                                t, re.I)),
    ("Qual è il mio numero preferito?", "memoria (ricordo)", ok_memoria),
    ("Sai chi sono?", "Dario, senza livello",
     lambda t, c: "dario" in t.lower() and "amministr" not in t.lower()),
    ("Che voci hai?", "nomi puliti",
     lambda t, c: "elenca_voci" in c and not re.search(r"-hd|\bhd\b", t, re.I)),
    ("Che tempo fa domani?", "limite: meteo",
     lambda t, c: bool(_NEG.search(t)) and not re.search(r"\bgradi\b|sole|pioverà", t, re.I)),
    ("Puoi accendere la luce?", "limite: luce",
     lambda t, c: bool(_NEG.search(t)) and not re.search(r"ho acceso|accesa", t, re.I)),
    # Dal 03/10 l'ora è nel contesto del turno: vale anche l'ora giusta senza il tool, ma
    # mai il nome del tool detto («Ad ora_attuale sono le 10:06.»)
    ("Che ore sono?", "tool ora",
     lambda t, c: ("ora_attuale" in c or ora_giusta(t)) and "ora_attuale" not in t),
]

if "--graffe" in sys.argv:
    # Simula una guardia che riconosce anche «chi_parla{}» (senza «call:»), la forma
    # vista il 24/09 in conversazioni lunghe. Da portare in brain.TextCallGuard.
    import calliope.brain as _brain
    _init = _brain.TextCallGuard.__init__

    def _init_graffe(self, schemas):
        _init(self, schemas)
        for key, (name, params, _) in list(self.prefixes.items()):
            if key.endswith("("):
                self.prefixes[key[:-1] + "{"] = (name, params, "}")
        if self.prefixes:
            self.state = "probe"

    _brain.TextCallGuard.__init__ = _init_graffe
    sys.argv.remove("--graffe")

# --biblioteca: con il tool biblioteca_cerca e il prompt che lo nomina (se i file ci sono)
CON_BIBLIOTECA = "--biblioteca" in sys.argv
if CON_BIBLIOTECA:
    sys.argv.remove("--biblioteca")
giri = int(sys.argv[1]) if len(sys.argv) > 1 else 3
cfg = Config()
from calliope.biblioteca import load_biblioteca
bib = load_biblioteca(cfg) if CON_BIBLIOTECA else None
reg = build_registry(biblioteca=bib is not None)
chiamati = []
chiama = reg.call
reg.call = lambda nome, args, ctx, level=None: (chiamati.append(nome),
                                                chiama(nome, args, ctx, level))[1]
ctx = ToolContext(cfg=cfg, speakers=FakeSpeakers(), speaker_ctx=FakeCtx(),
                  speaker=FakeSpeaker(),
                  memory=Memory(str(Path(tempfile.mkdtemp()) / "memoria-prova.db")),
                  biblioteca=bib)
brain = Brain(cfg, reg, ctx)
brain.warmup()

totali = {"verifiche": 0, "lei": 0, "tempi": []}
for g in range(giri):
    print(f"\n=== giro {g + 1} ===")
    brain.history = []                     # una conversazione per giro: la storia conta
    for frase, nome, verifica in CONVERSAZIONE:
        chiamati.clear()
        t0 = time.perf_counter()
        primo, pezzi = None, []
        for pezzo in brain.stream_reply(frase, "amministra"):
            if primo is None and pezzo.strip():
                primo = time.perf_counter() - t0
            pezzi.append(pezzo)
        testo = "".join(pezzi).strip()
        ok = verifica(testo, list(chiamati))
        lei = bool(_LEI.search(testo))
        totali["verifiche"] += ok
        totali["lei"] += lei
        if primo is not None:
            totali["tempi"].append(primo)
        print(f"{'ok ' if ok else 'NO '}{' LEI' if lei else '    '} {primo or 0:.2f}s "
              f"[{nome}] «{frase}» → {','.join(chiamati) or '—'} | {testo!r}")

n = giri * len(CONVERSAZIONE)
t = sorted(totali["tempi"])
print(f"\nVerifiche superate: {totali['verifiche']}/{n}   risposte con il «lei»: {totali['lei']}/{n}")
if t:
    print(f"Prima frase: mediana {t[len(t) // 2]:.2f}s, massimo {t[-1]:.2f}s")
