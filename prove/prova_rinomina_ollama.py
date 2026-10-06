import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Rinominare chi parla con il modello vero (Ollama), 02/10.

Il 02/10 Whisper sulla DGX ha trascritto «Calliope, chiamami Davio, ma vorrei sapere chi
sono» e il modello ha rinominato subito il profilo di chi amministra. Ora la prima chiamata
a rinomina_interlocutore propone e basta (azione in sospeso), il nome cambia solo con la
stessa chiamata nella risposta dopo, decisa dal modello. Casi, per giro:

  - la frase sbagliata di quella sera: nessun nome cambiato nel primo turno;
  - «Chiamami Davide» → domanda → «Sì» → rinominato;
  - «Chiamami Davide» → domanda → «No, lascia stare» → non rinominato.

    python prove\\prova_rinomina_ollama.py        # 3 giri
    python prove\\prova_rinomina_ollama.py 1      # 1 giro
"""

from calliope.brain import Brain
from calliope.config import Config
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


class Prof:
    def __init__(self, n):
        self.id, self.name, self.admin = n.lower() + "-id", n, n == "Dario"
        self.gender, self.preferred_voice = "m", None


class Speakers:
    def __init__(self):
        self.users = {"Dario": Prof("Dario"), "Bianca": Prof("Bianca")}

    def get(self, n):
        return self.users.get(n)

    def known_speakers(self):
        return list(self.users)

    def save(self):
        pass

    def rename(self, old, new):
        prof = self.users.pop(old, None)
        if prof is None:
            return None
        prof.name = new
        self.users[new] = prof
        return prof


class SpeakerCtx:
    def __init__(self):
        self.current_speaker, self.current_level = "Dario", "amministra"
        self.from_session, self.identified_by = False, "voce"


# (nome del caso, [(frase, controllo dopo quel turno(utenti, risposta))])
CASI = [
    ("frase della DGX", [("Calliope, chiamami Davio, ma vorrei sapere chi sono",
                          lambda u, r: "Dario" in u)]),
    ("sì", [("Chiamami Davide.", lambda u, r: "Dario" in u and r.rstrip().endswith("?")),
            ("Sì.", lambda u, r: "Davide" in u and "Dario" not in u)]),
    ("no", [("Chiamami Davide.", lambda u, r: "Dario" in u and r.rstrip().endswith("?")),
            ("No, lascia stare.", lambda u, r: "Dario" in u and "Davide" not in u)]),
]

cfg = Config()
reg = build_registry()
for giro in range(1, GIRI + 1):
    for nome, turni in CASI:
        sp = Speakers()
        ctx = ToolContext(cfg=cfg, speakers=sp, speaker_ctx=SpeakerCtx(), speaker=None)
        b = Brain(cfg, reg, ctx)
        for frase, controllo in turni:
            risposta = "".join(b.stream_reply(frase, "amministra")).strip()
            tools = "; ".join(f"{t['nome']}({t['argomenti']})" for t in b.last_tools) or "—"
            verifica(f"[{giro}] {nome}: «{frase}»", controllo(set(sp.users), risposta),
                     f"→ {risposta!r} | {tools} | utenti {sorted(sp.users)}")

print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
