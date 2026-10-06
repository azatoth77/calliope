import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Interroga Ollama direttamente per capire se e come tornano i tool_calls."""

import json

from openai import OpenAI

c = OpenAI(base_url="http://127.0.0.1:11434/v1", api_key="ollama")

tools = [{
    "type": "function",
    "function": {
        "name": "ora_attuale",
        "description": "Restituisce l'ora locale adesso.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}]

sys = ("Sei un assistente vocale. Hai alcuni tool: usali quando servono davvero, "
       "senza annunciarli. Per sapere l'ora chiama il tool ora_attuale.")

print("=== stream=False ===")
r = c.chat.completions.create(
    model="gemma4:e4b-it-qat",
    messages=[{"role": "system", "content": sys},
              {"role": "user", "content": "Che ore sono?"}],
    tools=tools, stream=False, reasoning_effort="none")
m = r.choices[0].message
print("content:", repr(m.content))
print("tool_calls:", m.tool_calls)

print("\n=== stream=True ===")
st = c.chat.completions.create(
    model="gemma4:e4b-it-qat",
    messages=[{"role": "system", "content": sys},
              {"role": "user", "content": "Che ore sono?"}],
    tools=tools, stream=True, reasoning_effort="none")
for chunk in st:
    if chunk.choices:
        d = chunk.choices[0].delta
        print("delta.content:", repr(d.content),
              "| tool_calls:", d.tool_calls)

