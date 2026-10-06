import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Memoria persistente: modulo a secco, poi Brain vero contro Ollama in due «sessioni».

Sessione 1: «ricordati che…» deve chiamare `ricorda`. Sessione 2 (Brain nuovo, storia
vuota): deve rispondere dal ricordo; poi aggiornamento, oblio e un ospite che non può
salvare nulla. Usa un database temporaneo, non memoria.db.

    python prove\\prova_memoria.py            # a secco + Ollama
    python prove\\prova_memoria.py --secco    # solo a secco
"""

import tempfile
from pathlib import Path

from calliope.brain import Brain
from calliope.config import Config
from calliope.memory import Memory
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


db = Path(tempfile.mkdtemp()) / "memoria-prova.db"
mem = Memory(str(db), max_facts=3)

# ── a secco ──
mem.remember("p1", "il suo numero preferito è 47")
r = mem.remember("p1", "il suo numero preferito è 12")
verifica("fatto simile → aggiornato", r.get("aggiornato") and mem.facts("p1") == ["il suo numero preferito è 12."],
         str(mem.facts("p1")))
mem.remember("p1", "è allergico alle noci")
mem.remember("p1", "si alza alle sette")
mem.remember("p1", "tifa per il Genoa")
verifica("tetto di 3 fatti", len(mem.facts("p1")) == 3, str(mem.facts("p1")))
verifica("altra persona non vede", mem.facts("p2") == [])
mem2 = Memory(str(db.with_name("m2.db")))
mem2.remember("p", "il suo numero preferito è quarantasette")
mem2.remember("p", "il suo numero preferito è dodici")
mem2.remember("p", "il suo colore preferito è il verde")
verifica("stesso soggetto, valore lungo → aggiornato; soggetto diverso → nuovo",
         mem2.facts("p") == ["il suo numero preferito è dodici.", "il suo colore preferito è il verde."],
         str(mem2.facts("p")))
r = mem.forget("p1", "allergia noci")
verifica("dimentica per parole chiave", r.get("ok"), str(r))
r = mem.forget("p1", "tutto")
verifica("dimentica tutto", r.get("ok") and mem.facts("p1") == [], str(r))

# Ricordo cancellato recuperabile per qualche minuto (06/10, prova e2e: «Qual è il mio
# numero preferito?» → dimentica, e il ricordo era perso)
import json  # noqa: E402
import types  # noqa: E402

mem3 = Memory(str(db.with_name("m3.db")))
mem3.remember("p", "il suo numero preferito è 47")
mem3.remember("p", "tifa per il Genoa")
creato = mem3.db.execute("SELECT created FROM facts WHERE text LIKE '%47%'").fetchone()[0]
mem3.forget("p", "numero preferito")
verifica("recupero, contrario: un valore diverso è un fatto nuovo, non un recupero",
         mem3.recupera("p", "il suo numero preferito è 12") == [], str(mem3.facts("p")))
verifica("recupero, contrario: un'altra persona non recupera", mem3.recupera("q") == [])
rip = mem3.recupera("p", "il suo numero preferito è 47.")
verifica("recupero: il ricordo torna com'era, con la sua data",
         rip == ["il suo numero preferito è 47."]
         and "il suo numero preferito è 47." in mem3.facts("p")
         and mem3.db.execute("SELECT created FROM facts WHERE text LIKE '%47%'").fetchone()[0]
         == creato, f"{rip} {mem3.facts('p')}")
verifica("recupero: una volta sola", mem3.recupera("p") == [])
mem3.forget("p", "tutto")
verifica("recupero di «tutto» con «annulla»",
         sorted(mem3.recupera("p", "annulla")) == sorted(["il suo numero preferito è 47.",
                                                          "tifa per il Genoa."]), str(mem3.facts("p")))
mem3.forget("p", "Genoa")
q, righe = mem3._cancellati["p"]
mem3._cancellati["p"] = (q - mem3.RECUPERO_S - 1, righe)
verifica("recupero, contrario: oltre RECUPERO_S è cancellato", mem3.recupera("p") == []
         and mem3.facts("p") == ["il suo numero preferito è 47."], str(mem3.facts("p")))
# Dai tool: dimentica dice come annullare, ricorda con lo stesso fatto lo rimette
reg_m = build_registry()
prof = types.SimpleNamespace(id="p", name="Dario")
ctx_m = ToolContext(cfg=Config(), memory=mem3,
                    speakers=types.SimpleNamespace(get=lambda n: prof if n == "Dario" else None),
                    speaker_ctx=types.SimpleNamespace(current_speaker="Dario"), speaker=None)
ctx_m.regole = []
r = json.loads(reg_m.call("dimentica", {"fatto": "numero preferito"}, ctx_m))
verifica("dimentica: la conferma dice come annullare",
         r.get("ok") and "annulla" in r.get("conferma", "") and "ricorda" in r.get("se_annulla", ""),
         str(r))
ctx_m.user_text = "Annulla, ricordalo."
r = json.loads(reg_m.call("ricorda", {"fatto": "il suo numero preferito è 47"}, ctx_m))
verifica("«annulla»: ricorda con lo stesso fatto lo rimette (regola ricordo_recuperato)",
         r.get("ok") and r.get("recuperato") and "ricordo_recuperato" in ctx_m.regole
         and "il suo numero preferito è 47." in mem3.facts("p"), f"{r} {ctx_m.regole}")

if "--secco" in sys.argv:
    print(f"\n{errori} errori" if errori else "\nTutto a posto (a secco).")
    sys.exit(1 if errori else 0)


# ── Brain vero contro Ollama ──
class Prof:
    def __init__(self, pid, name):
        self.id, self.name = pid, name


class Speakers:
    def __init__(self):
        self.p = {"Dario": Prof("dario-id", "Dario")}

    def get(self, n):
        return self.p.get(n)


class SpeakerCtx:
    def __init__(self, name, level):
        self.current_speaker, self.current_level = name, level


cfg = Config()
mem = Memory(str(db))


def sessione(frasi, name="Dario", level="amministra"):
    ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(name, level),
                      speaker=None, memory=mem)
    b = Brain(cfg, build_registry(), ctx)
    out = []
    for f in frasi:
        risposta = "".join(b.stream_reply(f, level)).strip()
        out.append((f, [t["nome"] for t in b.last_tools], risposta))
        print(f"   «{f}» → {[t['nome'] for t in b.last_tools] or '—'} | {risposta[:90]!r}")
    return out


print("\nSessione 1")
s1 = sessione(["Ricordati che il mio numero preferito è quarantasette."])
verifica("ricorda chiamato", "ricorda" in s1[0][1])
verifica("salvato", any("47" in f or "quarantasette" in f for f in mem.facts("dario-id")),
         str(mem.facts("dario-id")))

print("\nSessione 2 (Brain nuovo)")
s2 = sessione(["Qual è il mio numero preferito?"])
verifica("risponde dal ricordo", "47" in s2[0][2] or "quarantasette" in s2[0][2].lower())
# 06/10 (prova e2e, giro 1247): a una domanda il ricordo non si cancella; anche con la frase
# come l'aveva trascritta Whisper sulla DGX
s2b = sessione(["O no è il mio numero preferito."])
verifica("domanda sul ricordo: niente cancellato", "dimentica" not in s2[0][1] + s2b[0][1]
         and any("47" in f or "quarantasette" in f for f in mem.facts("dario-id")),
         str(mem.facts("dario-id")))

print("\nSessione 3: aggiornamento")
sessione(["Ho cambiato idea: ora il mio numero preferito è dodici, ricordalo."])
fatti = mem.facts("dario-id")
verifica("aggiornato, non duplicato",
         len(fatti) == 1 and ("12" in fatti[0] or "dodici" in fatti[0]), str(fatti))

print("\nSessione 4: oblio")
sessione(["Dimentica il mio numero preferito."])
verifica("dimenticato", mem.facts("dario-id") == [], str(mem.facts("dario-id")))

print("\nSessione 5: ospite")
s5 = sessione(["Ricordati che il mio colore preferito è il verde."], name=None, level="ospite")
# Dal 03/10 l'ospite vede ricorda come tutti: se il modello lo chiama (anche scritto come
# testo) il registro lo rifiuta con la frase pronta. Conta che non si salvi nulla
verifica("ospite: niente salvato", mem.facts("dario-id") == [] and
         not any(r[1] for r in mem.db.execute("SELECT person, text FROM facts").fetchall()))
detto = s5[0][2].lower()
verifica("ospite: non dice di averlo salvato",
         not any(w in detto for w in ("ho registrato", "ho salvato", "ho annotato",
                                      "ho memorizzato", "me lo ricorderò", "ricorderò")),
         repr(s5[0][2]))

print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
