"""Ciclo completo sull'API nativa: tool call, risultato, risposta finale."""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import urllib.request

from calliope.config import Config
from calliope.contesto import finestra
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

cfg = Config()
reg = build_registry()
tools = reg.schemas_for("ospite", online=True)
URL = "http://127.0.0.1:11434/api/chat"


class FakeSpeakers:
    def known_speakers(self):
        return []

    def get(self, n):
        return None

    def save(self):
        pass


class FakeCtx:
    current_speaker = None
    current_level = "ospite"
    enroll_needed = 3

    def start_enroll(self, n):
        pass


class FakeSpeaker:
    def change_voice(self, p):
        return True


ctx = ToolContext(cfg=cfg, speakers=FakeSpeakers(), speaker_ctx=FakeCtx(),
                  speaker=FakeSpeaker())


def chat(messages):
    body = {"model": cfg.llm_model, "messages": messages, "tools": tools,
            "options": {"num_ctx": finestra(cfg),
                        "temperature": cfg.llm_temperature},
            "stream": False}
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


msgs = [{"role": "system", "content": cfg.system_prompt},
        {"role": "user", "content": "Che ore sono?"}]
out = chat(msgs)
m = out["message"]
print("1° giro tool_calls:", json.dumps(m.get("tool_calls"), ensure_ascii=False))

msgs.append({"role": "assistant", "content": m.get("content") or "",
             "tool_calls": m.get("tool_calls")})
for tc in m.get("tool_calls") or []:
    fn = tc["function"]
    res = reg.call(fn["name"], fn.get("arguments") or {}, ctx)
    print("   risultato:", res)
    msgs.append({"role": "tool", "content": res})

out = chat(msgs)
print("2° giro content:", repr(out["message"].get("content")))
print("2° giro tool_calls:", out["message"].get("tool_calls"))
