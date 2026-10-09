import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Approfondire dopo una ricerca, con il modello vero (Ollama) e il SearXNG finto (09/10).

Caso vero della DGX del 09/10, 10:21: le notizie con web_cerca (re di Norvegia, proteste,
festival di fotografia), poi «Approfondiamo le condizioni reale» (= «del re») → «non ho
informazioni più dettagliate oltre a quelle che ti ho riportato», senza cercare. Il ciclo
faceva cercare nella biblioteca la frase di prima («altre news…»): passaggi fuori tema e
l'istruzione «se non contengono la risposta dillo».

Ogni caso parte da una conversazione nuova con lo stesso primo turno («Dimmi le ultime
notizie», web_cerca finto con tre titoli), poi la frase di seguito:
1. Seguiti (devono cercare di nuovo con una domanda mirata): «Approfondiamo il primo»,
   «Dimmi di più sul festival», «E le condizioni del re?», «Approfondiamo le condizioni reale».
2. Contrari: «Approfondiamo» in una chiacchierata senza ricerca (nessuna ricerca su internet);
   «E cosa c'è nella mia lista della spesa?» dopo le notizie (lista_leggi, non il web);
   internet spento dopo le notizie (nessuna ricerca, lo dice onestamente).

Due configurazioni: «prima» (rete `ricerca_recente` spenta e, per le frasi di DEEPEN_WORDS, il
contesto della biblioteca con la domanda di prima come faceva il ciclo fino al 09/10) e «dopo».

    python prove\\prova_ricerca_seguito_ollama.py        # 2 giri
    python prove\\prova_ricerca_seguito_ollama.py 1      # 1 giro
"""

import re
import tempfile
import time

from calliope.biblioteca import Passaggio
from calliope.brain import Brain
from calliope.config import Config, DEEPEN_WORDS
from calliope.liste import Liste
from calliope.tools.builtin import biblioteca_contesto, build_registry
from calliope.tools.spec import ToolContext
from calliope.web import Web
from calliope.web.privacy import Ripulitore, nomi_da, privati_da_config
from prove.searxng_finto import SearxngFinto, risultato

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


class Prof:
    def __init__(self, pid, name, admin=False):
        self.id, self.name, self.admin = pid, name, admin
        self.preferred_voice = None


class Speakers:
    def __init__(self):
        self.p = {"Dario": Prof("dario-id", "Dario", True)}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    def __init__(self, name, level):
        self.current_speaker, self.current_level, self.from_session = name, level, False
        self.identified_by = "voce" if name else None


class BibliotecaFinta:
    """Trova un passaggio fuori tema, come la frase «altre news» del caso vero."""
    citazioni = False

    def cerca(self, domanda, semplice=False):
        return [Passaggio("Una notizia è un'informazione su un fatto recente, diffusa da "
                          "giornali, radio, televisione e siti internet.", "Notizia",
                          "Wikipedia", 3.0)]

    def richieste(self, d):
        return set()

    def opzioni(self, d):
        return []

    def testo_voce(self, p, max_caratteri=2500):
        return ""


TITOLI = [
    risultato("https://www.ansa.it/sito/notizie/mondo/re.html",
              "Norvegia, gravi le condizioni di salute di re Harald V | ANSA",
              "Le condizioni del sovrano norvegese sono peggiorate nella notte."),
    risultato("https://www.ansa.it/sito/notizie/mondo/israele.html",
              "Israele, proteste a Tel Aviv | ANSA", "Migliaia in piazza nella capitale."),
    risultato("https://www.ansa.it/lombardia/festival.html",
              "Lodi, al via il Festival della Fotografia Etica | ANSA",
              "La rassegna apre sabato con venti mostre in città."),
]
RE = [risultato("https://www.ansa.it/sito/notizie/mondo/re-dettagli.html",
                "Re Harald V ricoverato in terapia intensiva a Oslo | ANSA",
                "Il re, 89 anni, è ricoverato in terapia intensiva all'ospedale di Oslo per "
                "un'infezione; la famiglia reale è al suo fianco.")]
FESTIVAL = [risultato("https://www.ansa.it/lombardia/festival-dettagli.html",
                      "Festival della Fotografia Etica, il programma | ANSA",
                      "Dal 10 ottobre al 2 novembre, ventidue mostre in dieci sedi del centro "
                      "di Lodi; biglietto unico 18 euro.")]

sx = SearxngFinto().avvia()
# La prima chiave contenuta nella domanda vince: prima le più specifiche (le predefinite dopo,
# senza la loro «notizie»: con `**` in fondo avrebbe preso il posto di TITOLI)
_base = {k: v for k, v in sx.risposte.items() if k not in ("notizie",)}
sx.risposte = {"harald": RE, "norveg": RE, "sovrano": RE, "del re": RE, "il re": RE,
               "re di": RE, "reale": RE, "festival": FESTIVAL, "fotografia": FESTIVAL,
               "lodi": FESTIVAL, "notizie": TITOLI, "news": TITOLI, "ansa": TITOLI, **_base}
cfg = Config()
cfg.web_searxng_url = sx.url
cfg.web_max_minuto = 1000
cfg.memory_db = os.path.join(tempfile.mkdtemp(prefix="calliope-seguito-"), "m.db")
speakers = Speakers()
web = Web(cfg, Ripulitore(nomi_da(cfg, speakers), lambda: privati_da_config(cfg)))
assert web.prova(), "SearXNG finto non risponde"
liste = Liste(cfg.memory_db)
liste.add("spesa", ["latte", "pane", "mele"], "Dario")
reg = build_registry(biblioteca=True, web=cfg, casa=True)
bib = BibliotecaFinta()


def nuovo_brain():
    ctx = ToolContext(cfg=cfg, speakers=speakers, speaker_ctx=SpeakerCtx("Dario", "familiare"),
                      speaker=None, biblioteca=bib, web=web, liste=liste)
    return Brain(cfg, reg, ctx), ctx


def esegui(b, frase, context=None):
    t0 = time.perf_counter()
    primo, parti = None, []
    for pezzo in b.stream_reply(frase, "familiare", context):
        if primo is None and pezzo.strip():
            primo = time.perf_counter() - t0
        parti.append(pezzo)
    return re.sub(r"\s+", " ", "".join(parti)).strip(), primo or 0.0


def domande(n):
    return [q.lower() for q in sx.domande()[n:]]


def mirata(*parole):
    """Una nuova ricerca su internet con una delle parole nella domanda, e la risposta con il
    dato del risultato giusto."""
    def f(tools, qs, risposta, dato):
        return ("web_cerca" in tools and any(any(p in q for p in parole) for q in qs)
                and dato.lower() in risposta.lower())
    return f


SEGUITI = [
    ("Approfondiamo il primo", mirata("harald", "norveg", "re ", "sovrano"), "terapia intensiva"),
    ("Dimmi di più sul festival", mirata("festival", "fotografia", "lodi"), "18 euro"),
    ("E le condizioni del re?", mirata("harald", "norveg", "re ", "sovrano"), "terapia intensiva"),
    ("Approfondiamo le condizioni reale.", mirata("harald", "norveg", "re ", "sovrano"),
     "terapia intensiva"),
]
PRIMO = "Dimmi le ultime notizie"

risultati = {}
for modo in ("prima", "dopo"):
    cfg.llm_reti_spente = ["ricerca_recente"] if modo == "prima" else []
    conti = {"seguiti": [0, 0], "contrari": [0, 0]}
    for giro in range(1, GIRI + 1):
        for frase, controllo, dato in SEGUITI:
            b, ctx = nuovo_brain()
            r1, _ = esegui(b, PRIMO)
            n = len(sx.domande())
            # Prima del 09/10 il ciclo, per le frasi di DEEPEN_WORDS, passava la biblioteca
            # cercata con la domanda di prima
            context = (biblioteca_contesto(ctx, PRIMO) if modo == "prima"
                       and DEEPEN_WORDS.search(frase) and len(frase.split()) <= 6 else None)
            risposta, primo = esegui(b, frase, context)
            tools = [t["nome"] for t in b.last_tools]
            ok = controllo(tools, domande(n), risposta, dato)
            conti["seguiti"][0] += ok
            conti["seguiti"][1] += 1
            verifica(f"[{modo} {giro}] «{frase}»", ok,
                     f"{tools} {domande(n)} regole {b.rules_fired()} → {risposta[:150]!r} "
                     f"({primo:.2f} s)")

        # ── contrari ──
        # 1. chiacchierata senza ricerca: niente web, niente dati sulla ricerca
        b, ctx = nuovo_brain()
        esegui(b, "Sai che mi piacciono tanto i gatti siamesi?")
        n = len(sx.domande())
        risposta, _ = esegui(b, "Approfondiamo")
        ok = not domande(n) and "ricerca_recente" not in b.rules_fired()
        conti["contrari"][0] += ok
        conti["contrari"][1] += 1
        verifica(f"[{modo} {giro}] contrario: «Approfondiamo» senza ricerca prima", ok,
                 f"{[t['nome'] for t in b.last_tools]} → {risposta[:120]!r}")
        # 2. dopo le notizie, una cosa personale: il suo tool
        b, ctx = nuovo_brain()
        esegui(b, PRIMO)
        n = len(sx.domande())
        risposta, _ = esegui(b, "E cosa c'è nella mia lista della spesa?")
        tools = [t["nome"] for t in b.last_tools]
        ok = "lista_leggi" in tools and not domande(n) and "latte" in risposta.lower()
        conti["contrari"][0] += ok
        conti["contrari"][1] += 1
        verifica(f"[{modo} {giro}] contrario: la lista della spesa dopo le notizie", ok,
                 f"{tools} → {risposta[:120]!r}")
        # 3. internet spento dopo le notizie (senza rete: il tool esce dall'elenco e i motori
        # non rispondono): lo dice, non inventa
        b, ctx = nuovo_brain()
        esegui(b, PRIMO)
        cfg.online, sx.senza_internet = False, True
        try:
            risposta, _ = esegui(b, "Dimmi di più sul festival")
        finally:
            cfg.online, sx.senza_internet = True, False
        ok = ("18 euro" not in risposta and "ventidue" not in risposta
              and bool(re.search(r"internet|cercare|non (posso|riesco)", risposta, re.I)))
        conti["contrari"][0] += ok
        conti["contrari"][1] += 1
        verifica(f"[{modo} {giro}] contrario: internet spento", ok,
                 f"{[t['nome'] for t in b.last_tools]} → {risposta[:150]!r}")
    risultati[modo] = conti

sx.ferma()
print()
for modo, conti in risultati.items():
    print(f"{modo}: " + ", ".join(f"{g} {ok}/{n}" for g, (ok, n) in conti.items()))
# Si giudica il «dopo»; il «prima» è la misura di confronto
ok_dopo = all(ok == n for ok, n in risultati["dopo"].values())
errori_dopo = sum(n - ok for ok, n in risultati["dopo"].values())
print(f"{'Tutto bene' if ok_dopo else f'{errori_dopo} errori nel «dopo»'}.")
sys.exit(0 if ok_dopo else 1)
