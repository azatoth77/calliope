import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Liste, appuntamenti e memoria della casa con il modello vero (Ollama).

Una ventina di richieste realistiche, in più «sessioni» (Brain nuovo = storia vuota), con
un contesto finto in cui la voce è riconosciuta: Dario e Bianca familiari, più un ospite
che prova a scrivere nella lista e deve sentirsi dire di no, senza bugie. In mezzo ci
sono i distrattori (promemoria, ricorda personale, timer) che non devono finire nei tool
nuovi. Per ogni frase: tool e argomenti, stato del database dopo, risposta e tempi
(prima frase e totale). Database temporanei, non memoria.db.

    python prove\\prova_casa.py        # 2 giri
    python prove\\prova_casa.py 1      # 1 giro
"""

import datetime
import re
import tempfile
import time
from pathlib import Path

from calliope.agenda import Agenda
from calliope.brain import Brain
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from calliope.liste import Liste
from calliope.memory import HOUSE, Memory
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


class Prof:
    def __init__(self, pid, name):
        self.id, self.name = pid, name


class Speakers:
    def __init__(self):
        self.p = {"Dario": Prof("dario-id", "Dario"), "Bianca": Prof("bianca-id", "Bianca")}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    def __init__(self, name, level):
        self.current_speaker, self.current_level = name, level


cfg = Config()
# Come in Calliope: con i tool dei documenti registrati (qui senza servizio: una chiamata
# a documento_* in queste frasi sarebbe comunque un errore della prova)
# Con i tool degli schermi e degli agenti, come in Calliope (schermi accesi di
# predefinito e agenti con dgx.yaml, 02/10)
reg = build_registry(documenti=FORMATI, schermi=True, agenti=True)


def spesa():
    return [v.lower() for v in liste.read("spesa")[1]]


def appuntamenti():
    return ag.db.execute("SELECT kind, label, due FROM agenda WHERE kind IN "
                         "('appuntamento', 'avviso') ORDER BY id").fetchall()


def martedi_17():
    return any(k == "appuntamento" and "dentista" in l.lower()
               and datetime.datetime.fromtimestamp(d).weekday() == 1
               and datetime.datetime.fromtimestamp(d).hour == 17 for k, l, d, in appuntamenti())


def per_tutti(args):
    return str(args.get("per_tutti")).lower() in ("true", "1", "sì", "si")


# (sessione, chi, livello, frase, tool atteso o None, controllo(risposta, argomenti))
# Una sessione nuova = un Brain nuovo, senza storia. Il controllo riceve il testo detto e
# gli argomenti dell'ultima chiamata del tool atteso.
CASI = [
    ("liste", "Dario", "familiare", "Aggiungi latte e uova alla lista della spesa.", "lista_aggiungi",
     lambda r, a: {"latte", "uova"} <= set(spesa())),
    ("liste", "Dario", "familiare", "Cosa c'è nella lista della spesa?", "lista_leggi",
     lambda r, a: "latte" in r.lower() and "uova" in r.lower()),
    ("liste", "Dario", "familiare", "Ho preso il latte.", "lista_togli",
     lambda r, a: spesa() == ["uova"]),
    ("liste", "Dario", "familiare", "Metti le lampadine nella lista delle cose da fare.", "lista_aggiungi",
     lambda r, a: any("lampadin" in v for v in liste.read("cose da fare")[1]) and spesa() == ["uova"]),
    ("liste", "Dario", "familiare", "Svuota la lista della spesa.", "lista_togli",
     lambda r, a: spesa() == [] and liste.read("cose da fare")[1]),
    ("appuntamenti", "Dario", "familiare", "Martedì alle 17 ho il dentista.", "appuntamento_aggiungi",
     lambda r, a: martedi_17()),
    ("appuntamenti", "Dario", "familiare", "Cosa ho martedì?", "appuntamenti_elenca",
     lambda r, a: "dentista" in r.lower()),
    ("appuntamenti", "Dario", "familiare", "Annulla il dentista.", "agenda_annulla",
     lambda r, a: appuntamenti() == []),
    ("casa", "Dario", "familiare", "Ricorda per tutti che la password del wifi è giardino42.", "ricorda",
     lambda r, a: per_tutti(a) and any("giardino42" in f for f in mem.facts(HOUSE))),
    ("casa", "Dario", "familiare", "Ricordati che mi piace il tè.", "ricorda",
     lambda r, a: not per_tutti(a) and any("tè" in f for f in mem.facts("dario-id"))),
    ("bianca", "Bianca", "familiare", "Qual è la password del wifi?", None,
     lambda r, a: "giardino42" in r.lower().replace(" ", "")),
    ("ospite", None, "ospite", "Aggiungi il pane alla lista della spesa.", None,
     lambda r, a: "pane" not in spesa()
     and not re.search(r"\b(ho aggiunto|aggiunto|fatto|messo)\b", r.lower())),
    ("distrattori", "Dario", "familiare", "Ricordami di chiamare la nonna alle 18.", "promemoria_imposta",
     lambda r, a: any("nonna" in v["label"] for v in ag.items("dario-id"))),
    ("distrattori", "Dario", "familiare", "Metti un timer di 10 minuti.", "timer_imposta",
     lambda r, a: any(v["kind"] == "timer" for v in ag.items("dario-id"))),
    ("distrattori", "Dario", "familiare", "Ricordati che il mio colore preferito è il blu.", "ricorda",
     lambda r, a: not per_tutti(a) and any("blu" in f for f in mem.facts("dario-id"))),
    ("distrattori", "Dario", "familiare",
     "La caldaia si resetta tenendo premuto il tasto rosso per 5 secondi: ricordalo per tutti.", "ricorda",
     lambda r, a: per_tutti(a) and any("caldaia" in f.lower() for f in mem.facts(HOUSE))),
    ("distrattori", "Dario", "familiare", "Domani alle 9 e mezza ho la riunione con il commercialista.",
     "appuntamento_aggiungi",
     lambda r, a: any(k == "appuntamento" and "commercialista" in l.lower()
                      and datetime.datetime.fromtimestamp(d).strftime("%H:%M") == "09:30"
                      for k, l, d in appuntamenti())),
    ("distrattori", "Dario", "familiare", "Cosa ho domani?", "appuntamenti_elenca",
     lambda r, a: "commercialista" in r.lower()),
    ("distrattori", "Dario", "familiare", "Aggiungi pane, pasta e pomodori alla spesa.", "lista_aggiungi",
     lambda r, a: {"pane", "pasta", "pomodori"} <= set(spesa())),
    ("distrattori", "Dario", "familiare", "Togli la pasta dalla lista.", "lista_togli",
     lambda r, a: "pasta" not in spesa() and "pane" in spesa()),
    ("distrattori", "Dario", "familiare", "Che ore sono?", "ora_attuale", lambda r, a: True),
]

righe = []
for giro in range(1, GIRI + 1):
    tmp = Path(tempfile.mkdtemp())
    mem = Memory(str(tmp / "memoria.db"))
    liste = Liste(str(tmp / "memoria.db"))
    ag = Agenda(str(tmp / "memoria.db"))
    brains = {}
    for sessione, chi, livello, frase, atteso, controllo in CASI:
        key = (sessione, chi)
        if key not in brains:
            ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(chi, livello),
                              speaker=None, memory=mem, agenda=ag, liste=liste)
            brains[key] = Brain(cfg, reg, ctx)
        b = brains[key]
        t0 = time.perf_counter()
        primo, parti = None, []
        for pezzo in b.stream_reply(frase, livello):
            if primo is None and pezzo.strip():
                primo = time.perf_counter() - t0
            parti.append(pezzo)
        totale = time.perf_counter() - t0
        risposta = "".join(parti).strip()
        tools = [t["nome"] for t in b.last_tools]
        args = next((t["argomenti"] for t in reversed(b.last_tools) if t["nome"] == atteso), {})
        nuovi = {"lista_aggiungi", "lista_leggi", "lista_togli", "appuntamento_aggiungi",
                 "appuntamenti_elenca"}
        if atteso is None:
            # Nessun tool obbligato, ma nessun tool nuovo riuscito: Bianca risponde dalla
            # memoria; l'ospite non li vede, e se il modello ne scrive uno come testo
            # (TextCallGuard) il registro lo rifiuta: conta la risposta onesta
            ok_tool = not any(t["nome"] in nuovi and t["ok"] for t in b.last_tools)
        else:
            ok_tool = atteso in tools
        try:
            ok_stato = bool(controllo(risposta, args))
        except Exception as e:                      # un controllo rotto è un errore, non un crash
            ok_stato, risposta = False, f"{risposta} [controllo: {e}]"
        ok = ok_tool and ok_stato
        argomenti = "; ".join(f"{t['nome']}({', '.join(f'{k}={v!r}' for k, v in t['argomenti'].items())})"
                              for t in b.last_tools) or "—"
        verifica(f"[{giro}] {chi or 'ospite'}: «{frase}» → {argomenti}", ok,
                 f"{primo or 0:.2f}/{totale:.2f}s  {risposta[:110]!r}")
        righe.append((giro, frase, ok, primo or 0, totale))

prime = sorted(r[3] for r in righe)
print(f"\nprima frase: mediana {prime[len(prime) // 2]:.2f}s, massimo {prime[-1]:.2f}s; "
      f"riuscite {sum(r[2] for r in righe)}/{len(righe)}")
print(f"{errori} errori" if errori else "Tutto a posto.")
sys.exit(1 if errori else 0)
