import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Misura i token del prompt e prova ad alzare num_ctx."""

from openai import OpenAI

from calliope.config import Config
from calliope.tools.builtin import build_registry

cfg = Config()
reg = build_registry()
tools = reg.schemas_for("ospite", online=True)
c = OpenAI(base_url="http://127.0.0.1:11434/v1", api_key="ollama")

lungo = cfg.system_prompt
breve = ("Sei un assistente vocale. Hai alcuni tool: usali quando servono davvero, "
         "senza annunciarli. Per sapere l'ora chiama il tool ora_attuale.")

msgs_lungo = [{"role": "system", "content": lungo},
              {"role": "user", "content": "Che ore sono?"}]
msgs_breve = [{"role": "system", "content": breve},
              {"role": "user", "content": "Che ore sono?"}]


def chiama(nome, msgs, **extra):
    r = c.chat.completions.create(
        model=cfg.llm_model, messages=msgs, tools=tools,
        stream=False, temperature=cfg.llm_temperature, **extra)
    m = r.choices[0].message
    chiamate = [t.function.name for t in (m.tool_calls or [])]
    print(f"[{nome}] prompt={r.usage.prompt_tokens if r.usage else '?'} "
          f"completion={r.usage.completion_tokens if r.usage else '?'} "
          f"→ tool: {chiamate or '—'}  testo: {(m.content or '').strip()!r}")


print("num_ctx predefinito (4096):")
chiama("lungo", msgs_lungo, reasoning_effort="none")
chiama("breve", msgs_breve, reasoning_effort="none")

print("\nnum_ctx=8192 via extra_body:")
try:
    chiama("lungo", msgs_lungo, reasoning_effort="none", extra_body={"num_ctx": 8192})
    chiama("breve", msgs_breve, reasoning_effort="none", extra_body={"num_ctx": 8192})
except Exception as e:
    print("extra_body num_ctx non accettato:", e)

