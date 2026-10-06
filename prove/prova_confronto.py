import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Isola la causa: reasoning_effort oppure il contesto."""

from openai import OpenAI

from calliope.config import Config
from calliope.tools.builtin import build_registry

cfg = Config()
reg = build_registry()
tools = reg.schemas_for("ospite", online=True)
c = OpenAI(base_url=cfg.llm_base_url, api_key="ollama")

msgs = [{"role": "system", "content": cfg.system_prompt},
        {"role": "user", "content": "Che ore sono?"}]


def prova(nome, **extra):
    r = c.chat.completions.create(
        model=cfg.llm_model, messages=msgs, tools=tools, stream=False,
        temperature=cfg.llm_temperature, **extra)
    m = r.choices[0].message
    chiamate = [t.function.name for t in (m.tool_calls or [])]
    print(f"[{nome}] tool: {chiamate or '—'}  testo: {(m.content or '').strip()!r}  "
          f"prompt={r.usage.prompt_tokens if r.usage else '?'}")


prova("senza reasoning_effort")
prova("reasoning_effort=none", reasoning_effort="none")
prova("reasoning_effort=low", reasoning_effort="low")

