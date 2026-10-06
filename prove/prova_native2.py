"""API nativa: effetto di think=true/false sulla chiamata dei tool."""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import urllib.request

from calliope.config import Config
from calliope.contesto import finestra
from calliope.tools.builtin import build_registry

cfg = Config()
reg = build_registry()
tools = reg.schemas_for("ospite", online=True)
URL = "http://127.0.0.1:11434/api/chat"


def chat(messages, think=None):
    body = {"model": cfg.llm_model, "messages": messages, "tools": tools,
            "options": {"num_ctx": finestra(cfg),
                        "temperature": cfg.llm_temperature},
            "stream": False}
    if think is not None:
        body["think"] = think
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


msgs = [{"role": "system", "content": cfg.system_prompt},
        {"role": "user", "content": "Che ore sono?"}]

for think in (None, False, True):
    try:
        out = chat(msgs, think=think)
    except Exception as e:
        print(f"think={think} → ERRORE: {e}")
        continue
    m = out["message"]
    nomi = [t["function"]["name"] for t in (m.get("tool_calls") or [])]
    print(f"think={think!r:5} → tool: {nomi or '—'}  "
          f"content: {(m.get('content') or '').strip()!r}  "
          f"thinking: {bool(m.get('thinking'))}")
