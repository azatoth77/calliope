import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova del ciclo di tool calling contro Ollama (senza audio)."""

from calliope.brain import Brain
from calliope.config import Config
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext


class FakeProfile:
    def __init__(self, name):
        self.name = name
        self.gender = None
        self.preferred_voice = None


class FakeSpeakers:
    def __init__(self, names):
        self.users = {n: FakeProfile(n) for n in names}

    def known_speakers(self):
        return list(self.users)

    def get(self, n):
        return self.users.get(n)

    def save(self):
        pass

    def rename(self, old, new):
        prof = self.users.pop(old, None)
        if prof is None:
            return None
        prof.name = new
        self.users[new] = prof
        return prof


class FakeCtx:
    def __init__(self, current_speaker):
        self.current_speaker = current_speaker
        self._enroll_needed = 3

    @property
    def enroll_needed(self):
        return self._enroll_needed

    @property
    def current_level(self):
        if self.current_speaker is None:
            return "ospite"
        if self.current_speaker in ("Primo", "Prima"):
            return "amministra"
        return "familiare"

    def start_enroll(self, name):
        self._enrolling = name


class FakeSpeaker:
    def change_voice(self, p):
        return True


def prova(frase, speaker, nomi):
    cfg = Config()
    reg = build_registry()
    ctx = ToolContext(cfg=cfg, speakers=FakeSpeakers(nomi),
                      speaker_ctx=FakeCtx(speaker), speaker=FakeSpeaker())
    b = Brain(cfg, reg, ctx)
    testo = "".join(b.stream_reply(frase, ctx.speaker_ctx.current_level))
    print(f"\n[{frase}] → {testo}\n")
    print("storia:", [(m.get("role"),
                       (m.get("tool_calls") or [{}])[0].get("function", {}).get("name")
                       if m.get("tool_calls") else None)
                      for m in b.history])


prova("Che ore sono?", None, [])
prova("Mi chiamo Marco, chiamami così.", "Dario", ["Dario"])

