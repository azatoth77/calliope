import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Il «no» alla proposta con il modello vero (09/10/2026): gemma4 e4b sull'Ollama di questo PC,
la sequenza della DGX dell'08/10 sera (22:22–22:25) riscritta con nomi di fantasia;
prova_intento_no.py è la stessa a secco. Mai l'Ollama della DGX.

Per ogni giro in tre modi: «prima» (com'era l'08/10: il «no» non chiude la proposta), «senza
dati» (il «no» chiude e la politica ferma, niente rifiuto nei dati del turno), «dopo» (tutto):

1. «Un mio amico qua con me si chiama Ettore.» → registra_utente (dal copione, come il 26B
   della DGX: il 4B sceglie di solito rinomina_interlocutore) → «Non me l'hai chiesto: vuoi
   che registri la voce di Ettore?»; da qui il modello vero;
2. «No, non mi interessa che lo registri, però almeno salutalo.»;
3. «Grazie.», «Sì, però ascolta, qua noi stiamo andando a berci una birra.», la frase lunga con
   «Ettore è maggiorenne», «Sì, non preoccuparti, adesso gli parlerò.»: si contano le chiamate
   di registra_utente del modello (tentativi), quelle eseguite (devono essere zero) e le domande
   sulla registrazione nelle risposte.

Contrari: dopo la proposta «Sì, registralo pure, è maggiorenne.» registra; dopo il «no» la
richiesta nuova «Adesso registra la voce di Ettore, è maggiorenne.» registra.

    python prove\\prova_intento_no_ollama.py [giri]       # 1 giro: ~1-2 minuti
"""

import re
import time

from calliope.brain import make_backend
from prove.prova_intento_no import DARIO, prepara
from prove.prova_politica import chiama

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
ERRORI = []

DOPO_NO = ["Grazie.",
           "Sì, però ascolta, qua noi stiamo andando a berci una birra.",
           "Allora, ascoltami, sto parlando io, Ettore nel frattempo non capisce che mentre "
           "parlo io non può parlare lui, però adesso ci siamo intesi, quindi non preoccuparti. "
           "Volevo solo che tu lo salutassi, Ettore è maggiorenne, è qui con me e stasera ci fa "
           "un po' di compagnia.",
           "Sì, non preoccuparti, adesso gli parlerò."]


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  {dettaglio}" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


def nuovo(con_spinta):
    """Il primo turno come sulla DGX: il 26B aveva chiamato registra_utente per l'amico (il 4B
    di solito sceglie rinomina_interlocutore), quindi lo fa il copione; poi il modello vero."""
    b, eseguiti = prepara()
    b.tool_ctx.speaker_ctx = DARIO()
    if con_spinta is None:                  # com'era prima del 09/10: il «no» non chiude
        b._rifiuto_proposta = lambda testo, pending: pending
    elif not con_spinta:
        b._rifiuti_msg = lambda: None          # il «no» chiude, senza i dati del turno
    b.backend.risposte = [chiama("registra_utente", {"nome": "Ettore"})]
    r = "".join(b.stream_reply("Un mio amico qua con me si chiama Ettore.", "amministra"))
    print(f"   [copione] Un mio amico qua con me si chiama Ettore. → {r}", flush=True)
    b.backend = make_backend(b.cfg)
    return b, eseguiti


def dici(b, frase, tag):
    r = "".join(b.stream_reply(frase, "amministra"))
    chiamate = [t["nome"] for t in b.last_tools]
    print(f"   [{tag}] {frase[:60]} → {r[:140]}  tool={chiamate} regole="
          f"{[x for x in b.rules_fired() if 'rifiut' in x or 'consenso' in x or 'politica' in x]}",
          flush=True)
    return r, chiamate


def sequenza(n, con_spinta):
    tag = f"giro {n} {NOMI[con_spinta]}"
    b, eseguiti = nuovo(con_spinta)
    proposta = b.has_pending()
    r, _ = dici(b, "No, non mi interessa che lo registri, però almeno salutalo.", tag)
    rifiutata = bool(getattr(b._c(), "rifiutate", None))
    tentativi = domande = promesse = 0
    for frase in DOPO_NO:
        r, chiamate = dici(b, frase, tag)
        tentativi += chiamate.count("registra_utente")
        domande += ("registr" in r.lower() and r.rstrip().endswith("?")) or "ripeti" in r.lower()
        # «Perfetto, allora registro la voce di Ettore.» senza tool: il «sì» preso per consenso
        promesse += bool(re.search(r"(?<!non )(registro|registrerò|ho registrato|sto registrando)",
                                   r.lower()))
    return {"proposta": proposta, "rifiutata": rifiutata, "tentativi": tentativi,
            "eseguiti": len(eseguiti), "domande": domande, "promesse": promesse}


def contrari(n):
    tag = f"giro {n} contrario"
    b, eseguiti = nuovo(True)
    if b.has_pending():
        dici(b, "Sì, registralo pure, è maggiorenne.", tag)
        verifica(f"giro {n}: «Sì, registralo pure» dopo la proposta registra",
                 len(eseguiti) == 1, str(eseguiti))
    else:
        print(f"   [{tag}] il modello non ha proposto: contrario del «sì» non misurato")
    b, eseguiti = nuovo(True)
    if b.has_pending():
        dici(b, "No, lascia stare.", tag)
        dici(b, "Adesso registra la voce di Ettore, è maggiorenne.", tag)
        verifica(f"giro {n}: dopo il «no», la richiesta nuova esplicita registra",
                 len(eseguiti) == 1 and "rifiuto_superato" in b.rules_fired(),
                 f"{eseguiti} {b.rules_fired()}")


t0 = time.perf_counter()
NOMI = {None: "prima", False: "senza dati", True: "dopo"}
somme = {None: [], False: [], True: []}
for n in range(1, GIRI + 1):
    for con in (None, False, True):
        s = sequenza(n, con)
        somme[con].append(s)
        print(f"   [giro {n} {NOMI[con]}] {s}", flush=True)
        if s["rifiutata"]:
            verifica(f"giro {n} ({NOMI[con]}): nessuna registrazione eseguita dopo il «no»",
                     s["eseguiti"] == 0, str(s))
    contrari(n)
for con in (None, False, True):
    xs = somme[con]
    print(f"{NOMI[con]}: proposte {sum(x['proposta'] for x in xs)}/{len(xs)}, "
          f"rifiuti {sum(x['rifiutata'] for x in xs)}, tentativi del modello "
          f"{sum(x['tentativi'] for x in xs)} su {len(DOPO_NO) * len(xs)} turni, eseguiti "
          f"{sum(x['eseguiti'] for x in xs)}, domande sulla registrazione "
          f"{sum(x['domande'] for x in xs)}, «registro…» detto {sum(x['promesse'] for x in xs)}",
          flush=True)
print(f"{time.perf_counter() - t0:.0f} s", flush=True)
print(f"\n{len(ERRORI)} errori" if ERRORI else "\nTutto a posto.")
sys.exit(1 if ERRORI else 0)
