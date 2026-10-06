import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Ispeziona schemi, prompt e risposta grezza di Ollama."""

import json

from calliope.brain import Brain
from calliope.config import Config
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext


class FakeCtx:
    current_speaker = None
    current_level = "ospite"
    enroll_needed = 3

    def start_enroll(self, n):
        pass


class FakeSpeakers:
    def known_speakers(self):
        return []

    def get(self, n):
        return None

    def save(self):
        pass


class FakeSpeaker:
    def change_voice(self, p):
        return True


cfg = Config()
cfg.llm_backend = "openai"   # diagnostica dell'endpoint /v1: usa il client OpenAI di Brain
reg = build_registry()
ctx = ToolContext(cfg=cfg, speakers=FakeSpeakers(), speaker_ctx=FakeCtx(),
                  speaker=FakeSpeaker())
b = Brain(cfg, reg, ctx)

schemas = reg.schemas_for("ospite", online=cfg.online)
print("N schemi ospite:", len(schemas))
print("nomi:", [s["function"]["name"] for s in schemas])
print("\nprimo schema:")
print(json.dumps(schemas[0], ensure_ascii=False, indent=1))

msgs = [{"role": "system", "content": cfg.system_prompt},
        {"role": "user", "content": "Che ore sono?"}]
print("\nprompt di sistema:")
print(cfg.system_prompt)

print("\n=== 5 tool (come Brain) ===")
st = b.backend.client.chat.completions.create(
    model=cfg.llm_model, messages=msgs, temperature=cfg.llm_temperature,
    stream=True, reasoning_effort="none", tools=schemas)
for chunk in st:
    if chunk.choices:
        d = chunk.choices[0].delta
        if d.content or d.tool_calls:
            print("content:", repr(d.content), "| calls:", d.tool_calls)

print("\n=== 1 tool (ora_attuale) ===")
solo = [s for s in schemas if s["function"]["name"] == "ora_attuale"]
st = b.backend.client.chat.completions.create(
    model=cfg.llm_model, messages=msgs, temperature=cfg.llm_temperature,
    stream=True, reasoning_effort="none", tools=solo)
for chunk in st:
    if chunk.choices:
        d = chunk.choices[0].delta
        if d.content or d.tool_calls:
            print("content:", repr(d.content), "| calls:", d.tool_calls)

