import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Tono di voce chiesto a voce, con il modello vero (Ollama, 04/10).

«Parlami in modo più formale», «sii più ironica», «rispondi in modo essenziale», «torna
normale», «da adesso parla a tutti in modo formale» devono chiamare cambia_voce con il tono
giusto (e per_tutti solo nell'ultimo caso); i contrari («usa la voce di Paola», «che voci
hai?», «che ore sono?», «parla più forte») no, o non con un tono. Poi, con il tono salvato,
le risposte successive devono ancora chiamare i tool (l'ora, un timer).

    python prove\\prova_personalita_ollama.py        # 2 giri
    python prove\\prova_personalita_ollama.py 1      # 1 giro
"""

import tempfile
import time
from pathlib import Path

from calliope.agenda import Agenda
from calliope.brain import Brain
from calliope.config import Config, nome_tono
from calliope.documenti.formato import FORMATI
from calliope.memory import Memory
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
    def __init__(self):
        self.p = {"Dario": UserProfile("Dario", admin=True), "Bianca": UserProfile("Bianca")}
        self.p["Dario"].id, self.p["Bianca"].id = "dario-id", "bianca-id"

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


class VoceFinta:
    def change_voice(self, p):
        return True


def tono_args(a):
    return nome_tono(a.get("tono") or a.get("voce") or "")


reg = build_registry(documenti=FORMATI, schermi=True, agenti=True)

# (chi, livello, frase, controllo(last_tools, profili, cfg))
CASI = [
    ("Bianca", "familiare", "Parlami in modo più formale, per favore.",
     lambda t, p, c: p["Bianca"].preferred_tone == "formale" and c.tono == "normale"),
    ("Bianca", "familiare", "Che ore sono?",
     lambda t, p, c: any(x["nome"] == "ora_attuale" for x in t) or True),
    ("Bianca", "familiare", "Metti un timer di 3 minuti.",
     lambda t, p, c: any(x["nome"] == "timer_imposta" for x in t)),
    ("Bianca", "familiare", "Da adesso sii più ironica con me.",
     lambda t, p, c: p["Bianca"].preferred_tone == "ironico"),
    ("Bianca", "familiare", "Rispondimi in modo essenziale.",
     lambda t, p, c: p["Bianca"].preferred_tone == "essenziale"),
    ("Bianca", "familiare", "Torna a parlarmi come sempre.",
     lambda t, p, c: p["Bianca"].preferred_tone is None),
    # contrari
    ("Bianca", "familiare", "Usa la voce di Paola.",
     lambda t, p, c: any(x["nome"] == "cambia_voce" and "paola" in str(x["argomenti"]).lower()
                         and not x["argomenti"].get("tono") for x in t)
     and p["Bianca"].preferred_tone is None),
    ("Bianca", "familiare", "Che voci hai?",
     lambda t, p, c: not any(x["nome"] == "cambia_voce" for x in t)),
    ("Bianca", "familiare", "Raccontami una barzelletta.",
     lambda t, p, c: not any(x["nome"] == "cambia_voce" for x in t)),
    # la casa: solo chi amministra
    ("Bianca", "familiare", "Parla a tutti in modo formale.",
     lambda t, p, c: c.tono == "normale"),
    ("Dario", "amministra", "Da adesso parla a tutti come il computer di bordo di un'astronave.",
     lambda t, p, c: c.tono == "computer_di_bordo"),
    ("Dario", "amministra", "Che ore sono?",
     lambda t, p, c: any(x["nome"] == "ora_attuale" for x in t) or True),
    ("Dario", "amministra", "Ricordami di chiamare la nonna alle 18.",
     lambda t, p, c: any(x["nome"] == "promemoria_imposta" for x in t)),
    ("Dario", "amministra", "Torna al tono normale per tutti.",
     lambda t, p, c: c.tono == "normale" and any(x["nome"] == "cambia_voce" for x in t)),
]

righe = []
for giro in range(1, GIRI + 1):
    tmp = Path(tempfile.mkdtemp())
    cfg = Config()
    cfg.config_dir = str(tmp)
    mem = Memory(str(tmp / "memoria.db"))
    ag = Agenda(str(tmp / "memoria.db"))
    spk = Speakers()
    brains = {}
    for chi, livello, frase, controllo in CASI:
        if chi not in brains:
            ctx = ToolContext(cfg=cfg, speakers=spk, speaker_ctx=SpeakerCtx(chi, livello),
                              speaker=VoceFinta(), memory=mem, agenda=ag)
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
        try:
            ok = bool(controllo(b.last_tools, spk.p, cfg))
        except Exception as e:  # noqa: BLE001
            ok, risposta = False, f"{risposta} [controllo: {e}]"
        # «Che ore sono?»: l'ora giusta anche senza tool va bene (prove/ora_giusta.py)
        if frase == "Che ore sono?":
            ok = any(t["nome"] == "ora_attuale" for t in b.last_tools) or ora_giusta(risposta)
        argomenti = "; ".join(f"{t['nome']}({', '.join(f'{k}={v!r}' for k, v in t['argomenti'].items())})"
                              for t in b.last_tools) or "—"
        verifica(f"[{giro}] {chi}: «{frase}» → {argomenti}", ok,
                 f"{primo or 0:.2f}/{totale:.2f}s  {risposta[:110]!r}")
        righe.append((giro, frase, ok, primo or 0, totale))

prime = sorted(r[3] for r in righe)
print(f"\nprima frase: mediana {prime[len(prime) // 2]:.2f}s, massimo {prime[-1]:.2f}s; "
      f"riuscite {sum(r[2] for r in righe)}/{len(righe)}")
print(f"{errori} errori" if errori else "Tutto a posto.")
sys.exit(1 if errori else 0)
