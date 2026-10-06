import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova varie forme di num_ctx; poi si controlla con `ollama ps`."""

import sys

from openai import OpenAI

from calliope.config import Config

cfg = Config()
c = OpenAI(base_url=cfg.llm_base_url, api_key="ollama")

forma = sys.argv[1] if len(sys.argv) > 1 else "num_ctx"
n = int(sys.argv[2]) if len(sys.argv) > 2 else 131072

if forma == "num_ctx":
    extra = {"num_ctx": n}
elif forma == "options":
    extra = {"options": {"num_ctx": n}}
else:
    extra = {}

c.chat.completions.create(
    model=cfg.llm_model, max_tokens=1, stream=False,
    messages=[{"role": "user", "content": "ciao"}], extra_body=extra)
print(f"forma={forma} num_ctx={n}")

