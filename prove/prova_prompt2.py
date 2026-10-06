import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Altre varianti di prompt: brevi e con i tool nominati."""

from openai import OpenAI

from calliope.config import Config
from calliope.tools.builtin import build_registry

cfg = Config()
reg = build_registry()
tools = reg.schemas_for("ospite", online=True)
c = OpenAI(base_url="http://127.0.0.1:11434/v1", api_key="ollama")

varianti = {
    "D": ("Sei Calliope, un'assistente vocale locale. Rispondi in italiano, caldo e "
          "conciso, da una a tre frasi. Niente markdown, elenchi, emoji, codice o URL: "
          "il testo verrà letto ad alta voce. Hai dei tool e li chiami tu: per chi ti "
          "parla chi_parla, per l'ora ora_attuale, per la data data_oggi. Quando ti "
          "chiedono qualcosa di questi, chiama il tool e poi rispondi."),
    "E": ("Sei Calliope, un'assistente vocale locale. Parli in italiano, calda e "
          "conciso. Il testo verrà letto ad alta voce: niente markdown, elenchi, "
          "emoji, codice o URL. Hai dei tool: chi_parla, ora_attuale, data_oggi. "
          "Per sapere l'ora chiama ora_attuale, per la data chiama data_oggi, per "
          "chi parla chiama chi_parla."),
    "F": ("Sei Calliope, un'assistente vocale locale. Rispondi in italiano, da una a "
          "tre frasi, senza markdown (il testo va letto ad alta voce). Per l'ora "
          "chiama ora_attuale, per la data chiama data_oggi, per sapere chi parla "
          "chiama chi_parla."),
    "G": ("Sei un assistente vocale. Hai alcuni tool: usali quando servono davvero, "
          "senza annunciarli. Per sapere l'ora chiama il tool ora_attuale."),
}


def prova(nome, system, frase):
    st = c.chat.completions.create(
        model=cfg.llm_model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": frase}],
        tools=tools, stream=True, temperature=cfg.llm_temperature,
        reasoning_effort="none")
    testo, chiamate = "", []
    for chunk in st:
        if not chunk.choices:
            continue
        d = chunk.choices[0].delta
        if d.content:
            testo += d.content
        if d.tool_calls:
            for t in d.tool_calls:
                chiamate.append(t.function.name)
    print(f"[{nome}] «{frase}» → tool: {chiamate or '—'}  testo: {testo.strip()!r}")


for nome, sys_prompt in varianti.items():
    prova(nome, sys_prompt, "Che ore sono?")
    prova(nome, sys_prompt, "Chi ti sta parlando?")
    print()

