import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della rete `ciclo_ripetuto` (14/10, calliope/ciclo_ripetuto.py): la risposta che
gira in tondo («Allora allora, allora... allora...» per centinaia di volte, caso vero in auto).

Il filtro da solo, a token: il ciclo di una parola, di un gruppo di parole e di una frase intera
si ferma e non passa avanti, la parte sana sì; i contrari passano uguali, parola per parola («no
no no», «sì sì», tre volte per enfasi, numeri e IBAN dettati, «Fra Martino», «tanti auguri»,
«ripeti tre volte…», elenchi con la stessa forma, «la la la»). Con Brain e un motore finto che
genera all'infinito: lo stream si chiude (il motore smette), il ciclo non si dice e non entra
nella storia, la regola nel registro, niente seconda passata; con la parte sana compiuta basta
quella, altrimenti la frase pronta `scusa.incartata`; con la rete spenta passa tutto. La prima
frase di una risposta normale esce prima che il modello finisca (latenza invariata). Sotto i
50 µs a token in media.
"""

import re
import time

from calliope.brain import Brain
from calliope.ciclo_ripetuto import CicloRipetuto, coda_periodica
from calliope.config import Config
from calliope.frasi import CATALOGO
from calliope.tools.builtin import build_registry

errori = 0


def verifica(nome, ottenuto, atteso):
    global errori
    ok = ottenuto == atteso
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome} → {ottenuto!r}" + ("" if ok else f"  (atteso {atteso!r})"))


def a_token(testo):
    """Come arrivano dal modello: una parola (con lo spazio davanti) alla volta, a volte la
    punteggiatura a parte."""
    out = []
    for t in re.findall(r"\s*[^\s.,!?…]+|[.,!?…]+", testo):
        out.append(t)
    return out


def filtra(testo, active=True):
    c = CicloRipetuto(active)
    out = ""
    usati = 0
    for t in a_token(testo):
        out += c.feed(t)
        usati += 1
        if c.fermata:
            break
    out += c.flush()
    return out, c.fermata, usati


# ── il filtro ──
caso = "Grazie per l'aggiornamento, ora ho capito! Allora allora, " + "allora... " * 400
out, fermo, usati = filtra(caso)
verifica("caso vero: si ferma, detta solo la frase sana",
         (out.strip(), fermo, usati < 40), ("Grazie per l'aggiornamento, ora ho capito!", True, True))
out, fermo, _ = filtra("E quindi la risposta è " + "e poi " * 50)
verifica("gruppo di due parole: si ferma, il ciclo non passa",
         (fermo, out.count("poi") <= 1), (True, True))
frase = "Non so cosa dire su questo. "
out, fermo, _ = filtra("Ecco. " + frase * 20)
verifica("frase intera ripetuta: si ferma dopo poche copie", (fermo, out.count("Non so") <= 2),
         (True, True))
out, fermo, _ = filtra("Ciao " + "uno due tre quattro cinque sei sette otto nove dieci " * 10)
verifica("ritornello di dieci parole ripetuto dieci volte: si ferma", fermo, True)
verifica("coda_periodica: «a b a b a» è 2,5 volte «a b»",
         [(p, v) for p, v, _ in coda_periodica("x a b a b a".split())], [(2, 2.5)])

CONTRARI = [
    "No no no, non è così.",
    "Sì sì, va bene, lo faccio subito.",
    "È molto, molto, molto bello!",
    "Il codice è zero zero zero zero zero zero zero uno due tre.",
    "L'IBAN è IT 0 0 0 0 0 0 0 0 0 0 1 2 3 4 5.",
    "Fra Martino campanaro, dormi tu? dormi tu? Suona le campane! Suona le campane! "
    "Din don dan, din don dan.",
    "Tanti auguri a te, tanti auguri a te, tanti auguri cara Marta, tanti auguri a te!",
    "Eccola tre volte: oggi è una bella giornata, oggi è una bella giornata, oggi è una bella "
    "giornata.",
    "Ti serve un chilo di mele, un chilo di pere, un chilo di arance e un chilo di patate.",
    "La canzone fa così: la la la la la la, e poi riparte.",
    "Ciao ciao, a presto!",
    "Uno, due, tre, quattro, cinque, sei, sette, otto, nove, dieci.",
    "Bene bene bene, allora cominciamo.",
]
verifica("contrari: passano uguali, parola per parola",
         [t for t in CONTRARI if filtra(t) != (t, False, len(a_token(t)))], [])
verifica("rete spenta: passa anche il ciclo", filtra(caso, active=False)[0], caso.rstrip())

# Latenza: una frase che finisce col suo segno va avanti subito; una parola di ritardo nel mezzo
c = CicloRipetuto()
verifica("frase compiuta rilasciata subito", (c.feed("Sono le dieci"), c.feed(".")),
         ("Sono ", "le dieci."))
c = CicloRipetuto()
dentro = [c.feed(t) for t in a_token("Oggi c'è il sole e fa caldo")]
verifica("una parola di ritardo, non di più", "".join(dentro), "Oggi c'è il sole e ")

c = CicloRipetuto()
toks = a_token("Questa è una risposta lunga e normale, con tante parole diverse e altre ancora. " * 30)
t0 = time.perf_counter()
for t in toks:
    c.feed(t)
us = (time.perf_counter() - t0) / len(toks) * 1e6
verifica(f"costo per token sotto 50 µs ({us:.1f} µs, {len(toks)} token)", us < 50, True)

# ── la frase pronta ──
v = CATALOGO["scusa.incartata"]
verifica("frase pronta: in ogni tono, senza domanda", all(v.forme(t) for t in
         ("normale", "formale", "amichevole", "ironico", "essenziale", "computer_di_bordo"))
         and not any("?" in f for t in v.toni for f in v.toni[t]), True)


# ── con Brain ──
class Infinito:
    """Un motore che genera all'infinito dopo un inizio: conta i token mandati e se lo stream
    è stato chiuso (il client ha chiuso la richiesta)."""

    def __init__(self, inizio, giro, copione_dopo=None):
        self.inizio, self.giro = inizio, giro
        self.mandati, self.chiuso, self.passate = 0, False, 0
        self.dopo = list(copione_dopo or [])

    def stream(self, messages, tools):
        self.passate += 1
        if self.passate > 1:
            yield from (self.dopo.pop(0) if self.dopo else [("text", "Altro.")])
            return
        try:
            for t in re.findall(r"\S+\s*", self.inizio):
                self.mandati += 1
                yield "text", t
            for _ in range(100000):
                for t in re.findall(r"\S+\s*", self.giro):
                    self.mandati += 1
                    yield "text", t
        finally:
            self.chiuso = True


class CtxFinto:
    current_speaker = None
    current_level = "ospite"


def brain(backend):
    cfg = Config()
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = cfg, build_registry(), []
    b.tool_ctx = type("T", (), {"speaker_ctx": CtxFinto()})()
    b.backend = backend
    return b


m = Infinito("Grazie per l'aggiornamento, ora ho capito! Allora allora, ", "allora... ")
b = brain(m)
detto = "".join(b.stream_reply("Troppo aura vuol dire che è tanta roba.", "familiare"))
verifica("Brain: detta la parte sana, stream chiuso presto, una passata",
         (detto.strip(), m.chiuso, m.mandati < 60, m.passate),
         ("Grazie per l'aggiornamento, ora ho capito!", True, True, 1))
verifica("Brain: nella storia la parte sana, la regola nel registro",
         (b.history[-1], "ciclo_ripetuto" in b.last_rules),
         ({"role": "assistant", "content": "Grazie per l'aggiornamento, ora ho capito!"}, True))

m = Infinito("Il numero che cerchi è il ", "tre e ")
b = brain(m)
detto = "".join(b.stream_reply("Che numero era?", "familiare"))
forme = {f for t in v.toni for f in v.toni[t]} | {v.base}
coda = next((f for f in forme if detto.endswith(f)), None)
verifica("Brain: parte sana non compiuta → la frase pronta dopo",
         (detto.startswith("Il numero che cerchi è il "), coda is not None, m.chiuso,
          b.history[-1]["content"].endswith(coda or "?")), (True, True, True, True))

m = Infinito("", "sì ")
b = brain(m)
detto = "".join(b.stream_reply("Mi senti?", "familiare"))
verifica("Brain: solo ciclo → solo la frase pronta", detto.strip() in forme, True)

# Rete spenta: il ciclo passerebbe (qui il motore finto si ferma dopo un po': lo si vede)
m = Infinito("Ecco: ", "allora ")
m_giri = 200


class Finito(Infinito):
    def stream(self, messages, tools):
        self.passate += 1
        yield "text", "Ecco: "
        for _ in range(m_giri):
            yield "text", "allora "


b = brain(Finito("", ""))
b.cfg.llm_reti_spente = ["ciclo_ripetuto"]
detto = "".join(b.stream_reply("Dimmi.", "familiare"))
verifica("rete spenta da profilo: il testo passa intero", detto.count("allora"), m_giri)


# Latenza invariata: la prima frase esce prima che il modello finisca
class Lento:
    def __init__(self):
        self.finito = False

    def stream(self, messages, tools):
        yield "text", "Sono le dieci e un quarto, "
        yield "text", "una bella serata. "
        yield "text", "Altro?"
        self.finito = True


b = brain(Lento())
g = b.stream_reply("Che ore sono?", "familiare")
primo = next(g)
verifica("latenza: il primo pezzo esce prima della fine del modello",
         (bool(primo.strip()), b.backend.finito), (True, False))
"".join(g)

print("\nTutto bene." if not errori else f"\n{errori} errori.")
sys.exit(1 if errori else 0)
