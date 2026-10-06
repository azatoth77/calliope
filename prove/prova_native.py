import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova l'API nativa /api/chat: tool + options.num_ctx."""

import json
import urllib.request

from calliope.config import Config
from calliope.contesto import finestra
from calliope.tools.builtin import build_registry

cfg = Config()
reg = build_registry()
tools = reg.schemas_for("ospite", online=True)

body = {
    "model": cfg.llm_model,
    "messages": [{"role": "system", "content": cfg.system_prompt},
                 {"role": "user", "content": "Che ore sono?"}],
    "tools": tools,
    "options": {"num_ctx": finestra(cfg), "temperature": cfg.llm_temperature},
    "stream": False,
}
req = urllib.request.Request(
    "http://127.0.0.1:11434/api/chat",
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=180) as r:
    out = json.load(r)

print("message:")
print(json.dumps(out["message"], ensure_ascii=False, indent=1))
print("\nusage:", {k: out.get(k) for k in
                   ("prompt_eval_count", "eval_count", "done_reason")})

