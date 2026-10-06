import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Liste della casa e memoria della casa, a secco (niente Ollama).

Liste: nome normalizzato, divisione delle voci, doppioni, rimozione tollerante, «tutto»,
chi ha aggiunto. Tool: conferme già pronte, errori espliciti, lettura lunga troncata.
Memoria della casa: `ricorda` con per_tutti, `dimentica` che ripiega sulla casa, e il
messaggio di Brain con il blocco «Cose della casa» (mai per gli ospiti).

    python prove\\prova_liste.py
"""

import json
import tempfile
from pathlib import Path

from calliope.brain import Brain
from calliope.config import Config
from calliope.liste import Liste, list_key, split_items
from calliope.memory import HOUSE, Memory
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


# ── modulo ──
for detto, atteso in (("lista della spesa", "spesa"), ("della spesa", "spesa"), ("Spesa", "spesa"),
                      ("", "spesa"), (None, "spesa"), ("la lista delle cose da fare", "cose da fare"),
                      ("cose da fare", "cose da fare"), ("nella lista dei regali", "regali")):
    verifica(f"nome lista «{detto}» → {atteso}", list_key(detto) == atteso, list_key(detto))
verifica("divisione «latte, pane e uova»", split_items("latte, pane e uova") == ["latte", "pane", "uova"],
         str(split_items("latte, pane e uova")))

tmp = Path(tempfile.mkdtemp())
li = Liste(str(tmp / "liste.db"))
key, added, already = li.add("spesa", ["il latte", "le uova", "un po' di zucchero"], "Dario")
verifica("aggiunte senza articoli", added == ["latte", "uova", "zucchero"], str(added))
key, added, already = li.add("lista della spesa", ["Latte", "uovo", "pane"], "Bianca")
verifica("doppioni riconosciuti (maiuscole, plurale)", added == ["pane"] and already == ["Latte", "uovo"],
         f"{added} {already}")
added_by = li.db.execute("SELECT added_by FROM liste WHERE voce='pane'").fetchone()[0]
verifica("si annota chi ha aggiunto", added_by == "Bianca", str(added_by))
key, removed, missing = li.remove("spesa", ["il latte", "le banane"])
verifica("togli tollerante, e ciò che non c'è", removed == ["latte"] and missing == ["le banane"],
         f"{removed} {missing}")
li.add("cose da fare", ["cambiare le lampadine"], "Dario")
verifica("liste separate", li.read("spesa")[1] == ["uova", "zucchero", "pane"]
         and li.read("cose da fare")[1] == ["cambiare le lampadine"], str(li.names()))
key, removed, missing = li.remove("spesa", ["tutto"])
verifica("«tutto» svuota solo quella lista", li.read("spesa")[1] == [] and len(removed) == 3
         and li.read("cose da fare")[1], str(removed))


# ── tool ──
class Prof:
    def __init__(self, pid, name):
        self.id, self.name = pid, name


class Speakers:
    def __init__(self):
        self.p = {"Dario": Prof("dario-id", "Dario"), "Bianca": Prof("bianca-id", "Bianca")}

    def get(self, n):
        return self.p.get(n)


class SpeakerCtx:
    def __init__(self, name, level):
        self.current_speaker, self.current_level = name, level


cfg = Config()
reg = build_registry()
mem = Memory(str(tmp / "memoria.db"))
liste = Liste(str(tmp / "memoria.db"))


def contesto(name="Dario", level="familiare"):
    return ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(name, level),
                       speaker=None, memory=mem, liste=liste)


def chiama(nome, args, name="Dario", level="familiare"):
    return json.loads(reg.call(nome, args, contesto(name, level), level))


r = chiama("lista_aggiungi", {"cose": "latte e uova"})
verifica("lista_aggiungi: conferma", r.get("conferma") == "Ho aggiunto latte e uova alla lista della spesa.",
         r.get("conferma"))
r = chiama("lista_aggiungi", {"cose": "il latte, il pane"})
verifica("lista_aggiungi: doppione detto", r.get("conferma") ==
         "Ho aggiunto pane alla lista della spesa. Latte c'era già.", r.get("conferma"))
r = chiama("lista_leggi", {})
verifica("lista_leggi: conteggio", r.get("conferma") ==
         "Nella lista della spesa ci sono 3 cose: latte, uova e pane.", r.get("conferma"))
r = chiama("lista_togli", {"cose": "latte"})
verifica("lista_togli", r.get("conferma") == "Ho tolto latte dalla lista della spesa.", r.get("conferma"))
r = chiama("lista_togli", {"cose": "banane"})
verifica("lista_togli: non c'è → errore esplicito", r.get("ok") is False and "cosa_fare" in r, str(r))
# Voci ben diverse: «cosa1» e «cosa11» sarebbero lo stesso doppione
chiama("lista_aggiungi", {"cose": "libro, sciarpa, guanti, profumo, orologio, borsa, cravatta, "
                                  "tazza, candela, puzzle, ombrello, portafoglio", "lista": "regali"})
r = chiama("lista_leggi", {"lista": "lista dei regali"})
verifica("lista lunga: prime 8 e «e altre 4»", r.get("numero") == 12 and "e altre 4" in r.get("conferma", ""),
         r.get("conferma"))
r = chiama("lista_togli", {"cose": "tutto", "lista": "regali"})
verifica("svuota", r.get("conferma") == "Fatto, ho svuotato la lista regali.", r.get("conferma"))
r = chiama("lista_leggi", {"lista": "regali"})
verifica("lista vuota", r.get("conferma") == "La lista regali è vuota.", r.get("conferma"))
r = chiama("lista_aggiungi", {"cose": "latte"}, name=None, level="ospite")
verifica("ospite: rifiutato in modo esplicito", r.get("ok") is False and "NON" in r.get("fatto", ""), str(r))

# ── memoria della casa ──
r = chiama("ricorda", {"fatto": "la password del wifi è giardino42", "per_tutti": True})
verifica("ricorda per tutti → casa", r.get("per_tutti") and mem.facts(HOUSE) == ["la password del wifi è giardino42."],
         str(r))
r = chiama("ricorda", {"fatto": "gli piace il tè", "per_tutti": "false"})
verifica("ricorda personale (per_tutti come stringa «false»)", mem.facts("dario-id") == ["gli piace il tè."]
         and len(mem.facts(HOUSE)) == 1, str(mem.facts("dario-id")))


def messaggio(name, level):
    b = Brain(cfg, reg, contesto(name, level))
    m = b._memory_message()
    return m[0]["content"] if m else ""


m = messaggio("Bianca", "familiare")
verifica("un altro familiare vede la casa, non i fatti di Dario",
         "Della casa" in m and "giardino42" in m and "tè" not in m, m)
m = messaggio("Dario", "familiare")
verifica("Dario vede i suoi e quelli della casa", "tè" in m and "giardino42" in m, m)
verifica("ospite: niente", messaggio(None, "ospite") == "")
r = chiama("dimentica", {"fatto": "password del wifi"}, name="Bianca")
verifica("dimentica ripiega sulla casa", r.get("ok") and r.get("per_tutti") and mem.facts(HOUSE) == [], str(r))
r = chiama("dimentica", {"fatto": "tè"})
verifica("dimentica personale", r.get("ok") and not r.get("per_tutti") and mem.facts("dario-id") == [], str(r))

print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
