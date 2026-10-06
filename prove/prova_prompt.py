import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Confronta varianti di prompt per capire quale fa chiamare i tool a gemma4."""

import json

from openai import OpenAI

from calliope.config import Config
from calliope.tools.builtin import build_registry

cfg = Config()
reg = build_registry()
tools = reg.schemas_for("ospite", online=True)
c = OpenAI(base_url="http://127.0.0.1:11434/v1", api_key="ollama")

base = (
    "Sei Calliope, un'assistente vocale che gira in locale sul computer dell'utente. "
    "Il tuo nome viene dalla musa dell'eloquenza. Parli di te al femminile. "
    "Il genere di chi ti parla non è noto: rivolgiti a chi parla con formule neutre. "
    "Rispondi sempre in italiano, in modo naturale, caldo e conciso: di solito da una "
    "a tre frasi. Il tuo testo verrà letto ad alta voce, quindi niente markdown, "
    "elenchi puntati, emoji, codice o URL. Vai dritta al punto: non presentarti e non "
    "offrire altro aiuto a ogni risposta. Non hai accesso a internet, al meteo o ai file; "
    "non puoi compiere azioni sul computer. Se ti chiedono qualcosa che non puoi fare, "
    "dillo con semplicità, senza inventare."
)

tool_mid = ("Hai alcuni tool: usali quando servono davvero, senza annunciarli. "
            "Per sapere chi ti parla, l'ora o la data, per cambiare voce o registrare "
            "qualcuno, chiama il tool giusto. ")

tool_end = ("Hai dei tool e devi chiamarli, senza annunciare che lo farai: per sapere "
            "chi ti parla usa chi_parla, per l'ora usa ora_attuale, per la data usa "
            "data_oggi, per le voci usa elenca_voci, per cambiare voce usa cambia_voce, "
            "per cambiare il nome usa rinomina_interlocutore, per registrare qualcuno "
            "usa registra_utente. Dopo il tool, rispondi con quello che ti ha dato.")


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
    print(f"[{nome}] «{frase}»")
    print(f"   tool chiamati: {chiamate or '—'}   testo: {testo.strip()!r}")


# A: istruzione sui tool nel mezzo (com'è adesso in config.py)
a = base.replace("formule neutre. ", "formule neutre. " + tool_mid)
# B: istruzione sui tool in coda
b = base + " " + tool_end
# C: nel mezzo + in coda
d = base.replace("formule neutre. ", "formule neutre. " + tool_mid) + " " + tool_end

for nome, sys_prompt in (("A-mezzo", a), ("B-coda", b), ("C-mezzo+coda", d)):
    prova(nome, sys_prompt, "Che ore sono?")
    prova(nome, sys_prompt, "Chi ti sta parlando?")
    print()

