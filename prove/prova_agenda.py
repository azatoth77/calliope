import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Timer e promemoria: agenda a secco (scadenza, annullo, riavvio), poi Brain su Ollama.

    python prove\\prova_agenda.py            # a secco + Ollama
    python prove\\prova_agenda.py --secco
"""

import re
import tempfile
import time
from pathlib import Path

from calliope.agenda import Agenda, announcement

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


def aspetta(condizione, max_s=6.0) -> bool:
    """Aspetta la condizione invece di un tempo fisso (03/10): sotto carico 0,5 s o il
    margine di 0,7 s su un timer non bastavano sempre."""
    fine = time.monotonic() + max_s
    while time.monotonic() < fine:
        if condizione():
            return True
        time.sleep(0.02)
    return bool(condizione())


db = str(Path(tempfile.mkdtemp()) / "agenda-prova.db")
avvisi = []
ag = Agenda(db, on_due=lambda: avvisi.append(time.time()))
t0 = time.time()
ag.add("timer", "della pasta", t0 + 1.5, owner="p1", owner_name="Dario")
ag.add("promemoria", "chiamare la nonna", t0 + 3600, owner="p1", owner_name="Dario")
ag.add("promemoria", "segreto di un altro", t0 + 3600, owner="p2", owner_name="Bianca")
voci = ag.items("p1")
verifica("elenco: timer + propri promemoria, non quelli degli altri",
         [v["label"] for v in voci] == ["della pasta", "chiamare la nonna"], str([v["label"] for v in voci]))
aspetta(lambda: not ag.due.empty() and avvisi)
scaduto = ag.due.get_nowait() if not ag.due.empty() else None
verifica("il timer scade e sveglia", scaduto is not None and avvisi, str(scaduto))
verifica("annuncio del timer", scaduto and announcement(scaduto) == "Dario, è scaduto il timer della pasta.",
         scaduto and announcement(scaduto))
verifica("annulla per descrizione", [g["label"] for g in ag.cancel("il promemoria della nonna", "p1")]
         == ["chiamare la nonna"])
ag.add("timer", "di 10 minuti", time.time() + 600)
ag.add("timer", "del forno", time.time() + 900)
verifica("annulla tutti i timer", len(ag.cancel("tutti i timer", "p1")) == 2)
# «tutti» dentro il testo di un promemoria non vuol dire «tutti i promemoria» (01/10)
for etichetta in ("salutare tutti", "comprare il latte", "chiamare tutti i nonni"):
    ag.add("promemoria", etichetta, time.time() + 3600, owner="p1", owner_name="Dario")
tolti = [g["label"] for g in ag.cancel("il promemoria di salutare tutti", "p1")]
verifica("«il promemoria di salutare tutti» annulla solo quello", tolti == ["salutare tutti"], str(tolti))
tolti = [g["label"] for g in ag.cancel("chiamare tutti i nonni", "p1")]
verifica("«chiamare tutti i nonni» annulla solo quello", tolti == ["chiamare tutti i nonni"], str(tolti))
ag.add("promemoria", "pagare tutto l'affitto", time.time() + 3600, owner="p1", owner_name="Dario")
tolti = [g["label"] for g in ag.cancel("pagare tutto l'affitto", "p1")]
verifica("«pagare tutto l'affitto» annulla solo quello", tolti == ["pagare tutto l'affitto"], str(tolti))
ag.cancel("tutto", "p1")
for frase, attesi in (("annulla tutti i promemoria", ["uno"]), ("Tutti i promemoria.", ["uno"]),
                      ("tutti e tre i promemoria", ["uno"]), ("tutte le sveglie", ["due"]),
                      ("tutto", ["due", "uno"]), ("tutto quanto", ["due", "uno"])):
    ag.add("promemoria", "uno", time.time() + 3600, owner="p1", owner_name="Dario")
    ag.add("timer", "due", time.time() + 600)
    tolti = sorted(g["label"] for g in ag.cancel(frase, "p1"))
    verifica(f"forma intera «{frase}»", tolti == attesi, str(tolti))
    ag.cancel("tutto", "p1")
# Annullare solo con una parola vera in comune (03/10, analisi del comportamento): prima
# bastavano la somiglianza a 0,35 o il solo tipo, e «annulla il dentista» con un solo timer
# annullava il timer
def annulla_solo(voci, frase):
    ag.cancel("tutto", "p1")
    for kind, label in voci:
        ag.add(kind, label, time.time() + 3600, owner="p1", owner_name="Dario")
    tolti = sorted(g["label"] for g in ag.cancel(frase, "p1"))
    ag.cancel("tutto", "p1")
    return tolti
for voci, frase, attesi in (
        ([("timer", "di 5 minuti")], "il dentista", []),
        ([("promemoria", "chiamare la mamma")], "il promemoria della palestra", []),
        ([("timer", "delle uova")], "il timer della pasta", []),
        ([("appuntamento", "dentista")], "l'appuntamento col commercialista", []),
        ([("timer", "delle uova")], "il timer", ["delle uova"]),
        ([("timer", "delle uova")], "annulla", ["delle uova"]),
        ([("promemoria", "andare a dormire")], "anzi annulla quello", ["andare a dormire"]),
        ([("timer", "delle uova"), ("promemoria", "pane")], "il timer", ["delle uova"]),
        ([("timer", "delle uova"), ("timer", "della pasta")], "il timer", []),
        ([("timer", "delle uova"), ("timer", "della pasta")], "il timer della pasta",
         ["della pasta"]),
        ([("timer", "di 5 minuti"), ("timer", "di 10 minuti")], "il timer di 10 minuti",
         ["di 10 minuti"]),
        ([("appuntamento", "dentista")], "il dentisa", ["dentista"]),
        ([("promemoria", "bere un bicchiere d'acqua")], "il promemoria dell'acqua",
         ["bere un bicchiere d'acqua"])):
    tolti = annulla_solo(voci, frase)
    verifica(f"annulla «{frase}» tra {[l for _, l in voci]}", tolti == attesi, str(tolti))

# Riavvio: un promemoria scaduto a Calliope spenta si annuncia all'avvio
db2 = str(Path(tempfile.mkdtemp()) / "agenda-riavvio.db")
import sqlite3
con = sqlite3.connect(db2)
con.execute("CREATE TABLE agenda (id INTEGER PRIMARY KEY, kind TEXT, owner TEXT, owner_name TEXT, "
            "label TEXT, due REAL, created REAL)")
con.execute("INSERT INTO agenda (kind, owner, owner_name, label, due, created) VALUES "
            "('promemoria', 'p1', 'Dario', 'prendere le medicine', ?, ?)", (time.time() - 600, time.time()))
con.commit(); con.close()
ag2 = Agenda(db2)
aspetta(lambda: ag2.due.qsize() > 0)
tardi = [ag2.due.get_nowait() for _ in range(ag2.due.qsize())]
verifica("promemoria scaduto a Calliope spenta", any("medicine" in t["label"] for t in tardi),
         announcement(tardi[0]) if tardi else "")

# ── appuntamenti: tool, avviso collegato, elenco per giorno, annullo, annunci ──
import datetime
import json

from calliope.config import Config
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext


class _Prof:
    id, name = "dario-id", "Dario"


class _Speakers:
    def get(self, n):
        return _Prof() if n == "Dario" else None


class _Ctx:
    current_speaker, current_level = "Dario", "familiare"


ag3 = Agenda(str(Path(tempfile.mkdtemp()) / "agenda-appuntamenti.db"))
reg = build_registry()
tctx = ToolContext(cfg=Config(), speakers=_Speakers(), speaker_ctx=_Ctx(), speaker=None, agenda=ag3)


def chiama(nome, args):
    return json.loads(reg.call(nome, args, tctx, "familiare"))


r = chiama("appuntamento_aggiungi", {"cosa": "il dentista", "quando": "dopodomani alle 17"})
righe = ag3.db.execute("SELECT kind, label, due, parent FROM agenda ORDER BY id").fetchall()
verifica("appuntamento + avviso 60 minuti prima, collegato",
         [k for k, *_ in righe] == ["appuntamento", "avviso"] and righe[1][3] is not None
         and abs(righe[0][2] - righe[1][2] - 3600) < 1, str(righe))
verifica("conferma dell'appuntamento", r.get("conferma") ==
         "Segnato: dentista, dopodomani alle 17. Te lo ricordo un'ora prima.", r.get("conferma"))
verifica("l'avviso non compare nell'elenco", [v["kind"] for v in ag3.items("dario-id")] == ["appuntamento"])
r = chiama("appuntamento_aggiungi", {"cosa": "riunione", "quando": "ieri alle 9"})
verifica("orario passato o non capito → errore esplicito", r.get("ok") is False and "cosa_fare" in r, str(r))
presto = datetime.datetime.now() + datetime.timedelta(minutes=30)
r = chiama("appuntamento_aggiungi", {"cosa": "idraulico",
                                     "quando": f"oggi alle {presto.hour} e {presto.minute}"})
n_avvisi = ag3.db.execute("SELECT COUNT(*) FROM agenda WHERE kind='avviso'").fetchone()[0]
verifica("tra meno di un'ora: niente avviso", r.get("ok") is True and n_avvisi == 1
         and "ricordo" not in r.get("conferma", ""), str(r))
r = chiama("appuntamenti_elenca", {"quando": "dopodomani"})
verifica("elenco di dopodomani", r.get("conferma") == "Dopodomani hai: dentista alle 17.", r.get("conferma"))
r = chiama("appuntamenti_elenca", {})
verifica("elenco dei prossimi 7 giorni", len(r.get("appuntamenti", [])) == 2, r.get("conferma"))
r = chiama("appuntamenti_elenca", {"quando": "domani"})
# Vicino a mezzanotte l'appuntamento «tra 30 minuti» cade domani (01/10, alle 23:48 la
# prova falliva con «Domani hai: idraulico alle 0 e 18»): allora domani non è vuoto
if presto.date() == datetime.datetime.now().date():
    verifica("giorno vuoto", r.get("conferma") == "Domani non hai appuntamenti.", r.get("conferma"))
else:
    verifica("giorno vuoto (dopo mezzanotte: c'è l'idraulico)", "idraulico" in r.get("conferma", ""),
             r.get("conferma"))
r = chiama("agenda_annulla", {"cosa": "il dentista"})
resto = ag3.db.execute("SELECT kind, label FROM agenda ORDER BY id").fetchall()
verifica("annullare il dentista toglie anche il suo avviso", resto == [("appuntamento", "idraulico")],
         str(resto))
# Niente in comune: non si annulla, si chiede (con una voce sola, azione in sospeso)
r = chiama("agenda_annulla", {"cosa": "il commercialista"})
resto = ag3.db.execute("SELECT kind, label FROM agenda WHERE kind != 'avviso'").fetchall()
verifica("«il commercialista» con il solo idraulico: niente annullato, chiede",
         r.get("ok") is False and resto == [("appuntamento", "idraulico")]
         and r.get("risposta_finale", "").endswith("Annullo l'appuntamento «idraulico»?")
         and r.get("in_sospeso", {}).get("argomenti") == {"cosa": "idraulico"}, str(r))
r = chiama("agenda_annulla", {"cosa": "idraulico"})
verifica("al «sì»: annullato, con la conferma", r.get("ok") is True
         and r.get("conferma") == "Ho annullato l'appuntamento «idraulico».", str(r))
r = chiama("agenda_annulla", {"cosa": "il dentista"})
verifica("niente da annullare: frase pronta", r.get("ok") is False
         and "non c'è nessun timer" in r.get("risposta_finale", ""), str(r))
# Conversioni che inventavano (analisi del 03/10): passato, durata vaga, cambia sconosciuto
r = chiama("promemoria_imposta", {"testo": "pane", "quando": "ieri alle 9"})
verifica("promemoria «ieri alle 9»: rifiutato", r.get("ok") is False and "passato" in r.get("errore", ""),
         str(r))
r = chiama("timer_imposta", {"durata": "un po'"})
verifica("timer «un po'»: chiede quanto", r.get("ok") is False
         and r.get("risposta_finale") == "Quanto deve durare il timer?", str(r))
r = chiama("timer_imposta", {"durata": "qualche minuto"})
verifica("timer «qualche minuto»: chiede quanto", r.get("ok") is False, str(r))
r = chiama("timer_imposta", {"durata": "boh", "cambia": "nuovo timer"})
verifica("cambia sconosciuto: errore, non «imposta»", r.get("ok") is False
         and "non è un valore valido" in r.get("errore", ""), str(r))
r = chiama("timer_imposta", {"durata": "2 minuti", "cambia": "nessuno"})
verifica("cambia «nessuno»: timer nuovo", r.get("ok") is True and not r.get("cambiato"), str(r))
chiama("agenda_annulla", {"cosa": "tutti i timer"})
ora = time.time()
verifica("annuncio all'ora", announcement({"kind": "appuntamento", "label": "dentista", "owner_name": "Dario",
                                           "due": ora}) == "Dario, adesso hai: dentista.")
verifica("annuncio dell'avviso", announcement({"kind": "avviso", "label": "dentista", "owner_name": "Dario",
                                               "due": ora, "target_due": ora + 3600})
         == "Dario, tra un'ora hai: dentista.")

# ── cambiare una voce già messa (03/10: «impostalo di un minuto» avviava un secondo timer) ──
ag4 = Agenda(str(Path(tempfile.mkdtemp()) / "agenda-cambia.db"))
tctx4 = ToolContext(cfg=Config(), speakers=_Speakers(), speaker_ctx=_Ctx(), speaker=None, agenda=ag4)


def chiama4(nome, args):
    return json.loads(reg.call(nome, args, tctx4, "familiare"))


def timer4():
    return sorted((it["label"], round(it["due"] - time.time())) for it in ag4.items("dario-id")
                  if it["kind"] == "timer")


r = chiama4("timer_imposta", {"durata": "10 minuti"})
verifica("timer nuovo: riferimento per i turni dopo", r.get("riferimento_agenda", {}).get("tool")
         == "timer_imposta", str(r))
primo = ag4.items("dario-id")[0]
r = chiama4("timer_imposta", {"durata": "un minuto", "cambia": "imposta"})
verifica("«impostalo di un minuto»: lo stesso timer, niente secondo timer",
         timer4() == [("di 1 minuto", 60)] and ag4.items("dario-id")[0]["id"] == primo["id"]
         and r.get("conferma") == "Fatto, ho cambiato il timer: ora scade tra 1 minuto.", f"{timer4()} {r}")
r = chiama4("timer_imposta", {"durata": "cinque minuti", "cambia": "aggiungi"})
verifica("«aggiungi cinque minuti»: alla scadenza attuale", timer4() == [("di 6 minuti", 360)],
         f"{timer4()} {r.get('conferma')}")
r = chiama4("timer_imposta", {"durata": "2 minuti in meno", "cambia": "imposta"})
verifica("«imposta» con «2 minuti in meno» vale togli (forma corretta, regola nel registro)",
         timer4() == [("di 4 minuti", 240)] and "durata_relativa" in tctx4.regole, str(timer4()))
r = chiama4("timer_imposta", {"durata": "un'ora", "cambia": "togli"})
verifica("togliere più di quanto manca: errore, timer intatto", r.get("ok") is False
         and timer4() == [("di 4 minuti", 240)], str(r))
chiama4("timer_imposta", {"durata": "2 minuti", "nome": "pasta"})
verifica("caso contrario: un altro timer (senza cambia) è un secondo timer",
         timer4() == [("di 4 minuti", 240), ("per pasta", 120)], str(timer4()))
chiama4("timer_imposta", {"durata": "mezz'ora", "cambia": "imposta"})
verifica("senza nome cambia l'ultimo messo (la pasta)",
         timer4() == [("di 4 minuti", 240), ("per pasta", 1800)], str(timer4()))
chiama4("timer_imposta", {"durata": "un minuto", "nome": "quello di 4 minuti", "cambia": "aggiungi"})
verifica("«quello di 4 minuti» non è un nome: resta l'ultimo (la pasta)",
         timer4() == [("di 4 minuti", 240), ("per pasta", 1860)], str(timer4()))
chiama4("timer_imposta", {"durata": "10 minuti", "nome": "la pasta", "cambia": "imposta"})
chiama4("timer_imposta", {"durata": "3 minuti", "nome": "uova", "cambia": ""})
chiama4("timer_imposta", {"durata": "5 minuti", "nome": "pasta", "cambia": "imposta"})
verifica("con il nome cambia quello, anche se non è l'ultimo",
         timer4() == [("di 4 minuti", 240), ("per pasta", 300), ("per uova", 180)], str(timer4()))
ag4.cancel("tutti i timer", "dario-id")
chiama4("timer_imposta", {"durata": "un secondo"})
aspetta(lambda: not timer4())
r = chiama4("timer_imposta", {"durata": "un minuto", "cambia": "imposta"})
verifica("il timer di un secondo è già suonato: se ne avvia uno nuovo e lo dice",
         timer4() == [("di 1 minuto", 60)] and "Non c'era più" in r.get("conferma", ""), str(r))
ag4.cancel("tutti i timer", "dario-id")
r = chiama4("timer_imposta", {"durata": "2 minuti", "cambia": "togli"})
verifica("niente da accorciare: errore, nessun timer", r.get("ok") is False and timer4() == [], str(r))
domani = (datetime.datetime.now() + datetime.timedelta(days=1)).date()
chiama4("promemoria_imposta", {"testo": "chiamare la nonna", "quando": "domani alle 18"})
chiama4("promemoria_imposta", {"testo": "comprare il pane", "quando": "domani alle 8"})
r = chiama4("promemoria_imposta", {"testo": "chiamare la nonna", "quando": "alle 9", "cambia": "imposta"})
nonna = [it for it in ag4.items("dario-id") if "nonna" in it["label"]]
verifica("promemoria spostato «alle 9»: stesso giorno (domani), stessa voce",
         len(nonna) == 1 and datetime.datetime.fromtimestamp(nonna[0]["due"])
         == datetime.datetime.combine(domani, datetime.time(9)), f"{r.get('conferma')}")
r = chiama4("promemoria_imposta", {"testo": "lo", "quando": "mezz'ora", "cambia": "aggiungi"})
nonna = [it for it in ag4.items("dario-id") if "nonna" in it["label"]]
verifica("«rimandalo di mezz'ora» senza nome: l'ultimo cambiato",
         datetime.datetime.fromtimestamp(nonna[0]["due"]).time() == datetime.time(9, 30), r.get("conferma"))
r = chiama4("promemoria_imposta", {"testo": "comprare il pane", "quando": "ieri alle 7", "cambia": "imposta"})
verifica("promemoria nel passato: errore", r.get("ok") is False, str(r))
chiama4("appuntamento_aggiungi", {"cosa": "dentista", "quando": "dopodomani alle 17"})
r = chiama4("appuntamento_aggiungi", {"cosa": "dentista", "quando": "alle 11", "cambia": "imposta"})
righe = ag4.db.execute("SELECT kind, due, parent FROM agenda WHERE kind IN ('appuntamento', 'avviso') "
                       "ORDER BY kind").fetchall()
dopodomani = datetime.datetime.combine(domani + datetime.timedelta(days=1), datetime.time(11))
verifica("appuntamento spostato: l'avviso si sposta con lui (un'ora prima, uno solo)",
         len(righe) == 2 and datetime.datetime.fromtimestamp(righe[0][1]) == dopodomani
         and righe[0][1] - righe[1][1] == 3600 and righe[1][2] is not None, f"{righe} {r.get('conferma')}")

if "--secco" in sys.argv:
    print(f"\n{errori} errori" if errori else "\nTutto a posto (a secco).")
    sys.exit(1 if errori else 0)

# ── Brain vero contro Ollama ──
from calliope.brain import Brain
from calliope.config import Config
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext


class Prof:
    id, name = "dario-id", "Dario"


class Speakers:
    def get(self, n):
        return Prof() if n == "Dario" else None


class SpeakerCtx:
    def __init__(self, name, level):
        self.current_speaker, self.current_level = name, level


from calliope.brain import ACTION_CLAIM  # noqa: E402
from calliope.memory import Memory  # noqa: E402

cfg = Config()
_tmp_ollama = Path(tempfile.mkdtemp())
ag = Agenda(str(_tmp_ollama / "agenda-ollama.db"))
# La memoria c'è, come in Calliope (04/10: senza, «ricorda» diceva «non so chi sei» mentre
# chi_parla diceva «Dario, riconosciuto», e il 26B dopo quattro tentativi «Ho salvato…»)
mem = Memory(str(_tmp_ollama / "memoria.db"))


def dichiarazione_falsa(b, risposta: str) -> bool:
    """Un'azione dichiarata («Ho salvato…») senza nessun tool d'azione riuscito nel turno."""
    return bool(ACTION_CLAIM.search(risposta)) and not any(
        t.get("ok") and t.get("azione", True) for t in b.last_tools)


CASI = [  # (frase, livello, tool atteso, controllo sull'agenda dopo la frase)
    ("Metti un timer di mezz'ora per la pasta.", "amministra", "timer_imposta",
     lambda: any(abs(v["due"] - time.time() - 1800) < 60 for v in ag.items("dario-id"))),
    ("Ricordami di chiamare la nonna alle 18.", "amministra", "promemoria_imposta",
     lambda: any("nonna" in v["label"] for v in ag.items("dario-id"))),
    ("Ricordami tra 10 minuti di girare l'arrosto.", "amministra", "promemoria_imposta",
     lambda: any("arrosto" in v["label"] and abs(v["due"] - time.time() - 600) < 60
                 for v in ag.items("dario-id"))),
    # Timer e promemoria attivi: la risposta li deve dire (04/10, 26B: solo
    # appuntamenti_elenca e «non hai appuntamenti»)
    ("Cosa ho in agenda?", "amministra", ("agenda_elenca", "appuntamenti_elenca"), "nonna|arrosto|pasta"),
    ("Annulla il timer della pasta.", "amministra", "agenda_annulla",
     lambda: not any(v["kind"] == "timer" for v in ag.items("dario-id"))),
    ("Ricordati che mi piace la pizza.", "amministra", "ricorda",
     lambda: any("pizza" in f for f in mem.facts("dario-id"))),
    ("Metti un timer di 3 minuti.", "ospite", "timer_imposta",
     lambda: any(v["kind"] == "timer" for v in ag.items(None))),
]
for giro in (1, 2):
    for frase, livello, atteso, controllo in CASI:
        name = "Dario" if livello != "ospite" else None
        ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(name, livello),
                          speaker=None, agenda=ag, memory=mem)
        b = Brain(cfg, build_registry(), ctx)
        risposta = "".join(b.stream_reply(frase, livello)).strip()
        tools = [t["nome"] for t in b.last_tools]
        attesi = atteso if isinstance(atteso, tuple) else (atteso,)
        # Un controllo testuale: parole (regex) che la risposta deve contenere
        ok_dopo = (bool(re.search(controllo, risposta, re.I)) if isinstance(controllo, str)
                   else controllo())
        falsa = dichiarazione_falsa(b, risposta)
        ok = any(a in tools for a in attesi) and ok_dopo and not falsa
        verifica(f"[{giro}] «{frase}» → {tools or '—'}", ok,
                 ("dichiarazione falsa " if falsa else "") + repr(risposta[:90]))
    ag.cancel("tutto", "dario-id")
    ag.cancel("tutti i timer", None)


# ── Cambiare una voce già messa, in conversazione (03/10) ──
# Stessa Brain per le due frasi; il controllo guarda l'agenda dopo la seconda
def _timer_attivi():
    return sorted(round(v["due"] - time.time()) for v in ag.items("dario-id") if v["kind"] == "timer")


def _vicini(attesi, tolleranza=20):
    got = _timer_attivi()
    return len(got) == len(attesi) and all(abs(g - a) <= tolleranza for g, a in zip(got, sorted(attesi)))


def _promemoria_alle(parola, giorno, ora):
    voci = [v for v in ag.items("dario-id") if v["kind"] == "promemoria" and parola in v["label"]]
    return len(voci) == 1 and datetime.datetime.fromtimestamp(voci[0]["due"]) == \
        datetime.datetime.combine(giorno, datetime.time(ora))


_domani = (datetime.datetime.now() + datetime.timedelta(days=1)).date()
CAMBI = [  # (frasi, pausa tra le due in s, controllo)
    (["Mettimi un timer di un secondo.", "Adesso impostalo di un minuto."], 2.0,
     lambda: _vicini([60])),
    (["Metti un timer di un minuto.", "Adesso impostalo di cinque minuti."], 0, lambda: _vicini([300])),
    (["Metti un timer di 10 minuti.", "Aggiungi cinque minuti."], 0, lambda: _vicini([900])),
    (["Metti un timer di 10 minuti.", "Toglici due minuti."], 0, lambda: _vicini([480])),
    (["Metti un timer di 5 minuti.", "Fallo diventare di mezz'ora."], 0, lambda: _vicini([1800])),
    (["Ricordami di chiamare la nonna domani alle 18.", "Spostalo alle 9."], 0,
     lambda: _promemoria_alle("nonna", _domani, 9)),
    # casi contrari: un altro timer è un secondo timer; una domanda non cambia niente
    (["Metti un timer di un minuto.", "Metti un altro timer di 2 minuti."], 0,
     lambda: _vicini([60, 120])),
    (["Metti un timer di 10 minuti per la pasta.", "Che ore sono?"], 0, lambda: _vicini([600])),
    (["Metti un timer di 10 minuti per la pasta.", "Metti anche un timer di 3 minuti per le uova."], 0,
     lambda: _vicini([600, 180])),
]
for giro in (1, 2):
    for frasi, pausa, controllo in CAMBI:
        ag.cancel("tutto", "dario-id")
        ag.cancel("tutti i timer", None)
        ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx("Dario", "amministra"),
                          speaker=None, agenda=ag, memory=mem)
        b = Brain(cfg, build_registry(), ctx)
        visti = []
        for i, frase in enumerate(frasi):
            if i and pausa:
                time.sleep(pausa)
            risposta = "".join(b.stream_reply(frase, "amministra")).strip()
            visti.append(f"{[t['argomenti'] for t in b.last_tools] or '—'} {risposta[:70]!r}")
        verifica(f"[{giro}] «{frasi[1]}» dopo «{frasi[0]}»", controllo(),
                 f"{visti[-1]}  timer {_timer_attivi()}")
    ag.cancel("tutto", "dario-id")
    ag.cancel("tutti i timer", None)

print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
