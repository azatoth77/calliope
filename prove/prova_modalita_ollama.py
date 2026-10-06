import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""La modalità chiesta a voce, con il modello vero (Ollama, 05/10).

Caso della DGX (05/10): «la proviamo la modalità Star Trek» → cambia_voce(tono=
computer_di_bordo) e «Modalità computer di bordo attiva.» (solo il tono); poi «non sento i
suoni» → «Limitazione hardware rilevata». Qui «modalità Star Trek» deve chiamare cambia_voce
con modalita=startrek (da chi amministra: modalità accesa; da un familiare: rifiutata), «non
sento i suoni» non deve inventare limitazioni, «torna alla modalità normale» la spegne; i
contrari («parlami in modo formale», «parla a tutti come il computer di bordo») restano un tono.

    python prove\\prova_modalita_ollama.py        # 2 giri
    python prove\\prova_modalita_ollama.py 1      # 1 giro
"""

import tempfile
import time
from pathlib import Path

from calliope.agenda import Agenda
from calliope.brain import Brain
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from calliope.memory import Memory
from calliope.modalita import Modalita
from calliope.speaker_id import UserProfile
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ora_giusta import ora_giusta  # noqa: E402

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


class Speakers:
    def __init__(self, giro):
        # Un id per giro: la conversazione è per persona (calliope/corsie.py) e il giro dopo
        # ritroverebbe quella di prima
        self.p = {"Dario": UserProfile("Dario", admin=True), "Bianca": UserProfile("Bianca")}
        self.p["Dario"].id, self.p["Bianca"].id = f"dario-{giro}-{time.time()}", f"bianca-{giro}"

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)

    def save(self):
        pass


class SpeakerCtx:
    def __init__(self, name, level):
        self.current_speaker, self.current_level = name, level
        self.identified_by = "voce" if name else None
        self.profile_level = level
        self.sfida, self.sfida_superata, self.conferma_breve = None, False, False


class VoceFinta:
    def change_voice(self, p):
        return True


def chiamate(t, nome="cambia_voce"):
    return [x["argomenti"] for x in t if x["nome"] == nome]


def modalita_chiesta(t):
    return any(str(a.get("modalita") or "") == "startrek" for a in chiamate(t))


INVENTATE = ("hardware", "limitazion", "sensor", "non sono in grado di riprodurre")
reg = build_registry(documenti=FORMATI, schermi=True, agenti=True)

# (chi, livello, frase, controllo(last_tools, risposta, profili, cfg))
CASI = [
    ("Bianca", "familiare", "Parlami in modo formale, per favore.",
     lambda t, r, p, c: p["Bianca"].preferred_tone == "formale" and c.modalita is None
     and not modalita_chiesta(t)),
    ("Bianca", "familiare", "Passa alla modalità Star Trek.",
     lambda t, r, p, c: c.modalita is None and c.tono == "normale"),
    ("Dario", "amministra", "La proviamo la modalità Star Trek?",
     lambda t, r, p, c: c.modalita == "startrek" and modalita_chiesta(t)),
    ("Dario", "amministra", "Non sento i suoni.",
     lambda t, r, p, c: not any(w in r.lower() for w in INVENTATE) and c.modalita == "startrek"),
    ("Dario", "amministra", "Che ore sono?", None),
    ("Dario", "amministra", "Metti un timer di 2 minuti.",
     lambda t, r, p, c: bool(chiamate(t, "timer_imposta"))),
    ("Dario", "amministra", "Torna alla modalità normale.",
     lambda t, r, p, c: c.modalita is None and c.wake_names == ["Calliope"]),
    ("Dario", "amministra", "Mettiti in modalità Star Trek.",
     lambda t, r, p, c: c.modalita == "startrek"),
    ("Dario", "amministra", "Spegni la modalità Star Trek, torna come prima.",
     lambda t, r, p, c: c.modalita is None),
    # contrari: un tono resta un tono
    ("Dario", "amministra", "Da adesso parla a tutti in modo formale.",
     lambda t, r, p, c: c.tono == "formale" and c.modalita is None and not modalita_chiesta(t)),
    ("Dario", "amministra", "Torna al tono normale per tutti.",
     lambda t, r, p, c: c.tono == "normale" and c.modalita is None),
]

righe = []
for giro in range(1, GIRI + 1):
    tmp = Path(tempfile.mkdtemp())
    cfg = Config()
    cfg.config_dir = str(tmp)
    mod = Modalita(cfg, log=lambda *a: None)
    mem = Memory(str(tmp / "memoria.db"))
    ag = Agenda(str(tmp / "memoria.db"))
    spk = Speakers(giro)
    brains = {}
    for chi, livello, frase, controllo in CASI:
        if chi not in brains:
            ctx = ToolContext(cfg=cfg, speakers=spk, speaker_ctx=SpeakerCtx(chi, livello),
                              speaker=VoceFinta(), memory=mem, agenda=ag, modalita=mod)
            brains[chi] = Brain(cfg, reg, ctx)
        b = brains[chi]
        t0 = time.perf_counter()
        primo, parti = None, []
        for pezzo in b.stream_reply(frase, livello):
            if primo is None and pezzo.strip():
                primo = time.perf_counter() - t0
            parti.append(pezzo)
        totale = time.perf_counter() - t0
        risposta = "".join(parti).strip()
        if controllo is None:          # «Che ore sono?»: anche l'ora giusta senza tool
            ok = bool(chiamate(b.last_tools, "ora_attuale")) or ora_giusta(risposta)
        else:
            try:
                ok = bool(controllo(b.last_tools, risposta, spk.p, cfg))
            except Exception as e:  # noqa: BLE001
                ok, risposta = False, f"{risposta} [controllo: {e}]"
        argomenti = "; ".join(f"{t['nome']}({', '.join(f'{k}={v!r}' for k, v in t['argomenti'].items())})"
                              for t in b.last_tools) or "—"
        verifica(f"[{giro}] {chi}: «{frase}» → {argomenti}", ok,
                 f"{primo or 0:.2f}/{totale:.2f}s  {risposta[:140]!r}")
        righe.append((giro, frase, ok, primo or 0, totale))

prime = sorted(r[3] for r in righe)
print(f"\nprima frase: mediana {prime[len(prime) // 2]:.2f}s, massimo {prime[-1]:.2f}s; "
      f"riuscite {sum(r[2] for r in righe)}/{len(righe)}")
print(f"{errori} errori" if errori else "Tutto a posto.")
sys.exit(1 if errori else 0)
