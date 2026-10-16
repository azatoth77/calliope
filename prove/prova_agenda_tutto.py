import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Annullare tutta l'agenda si conferma (16/10/2026, #99; caso vero della DGX del 15/10 sera,
riscritto con nomi di fantasia). In auto chi amministra si fa leggere la lista della spesa (due
voci) e dice «cancellare entrambi»: il modello chiama agenda_annulla(cosa=tutti), eseguito
senza domanda. L'agenda era vuota; con appuntamenti e promemoria li avrebbe persi tutti.

A secco, con l'agenda vera in un database temporaneo:

1. **Il tool**: con più voci da annullare (non soli timer) niente si annulla, la risposta dice
   che cosa c'è e chiede («Annullo tutti e 2?», regola `agenda_tutto_chiede`), con la proposta
   in sospeso; la richiamata con la proposta di agenda_annulla per chi parla annulla tutto.
   Contrari: una voce sola, «il timer della pasta», «tutti i timer», la proposta in sospeso di
   un altro tool o di una voce sola, la conferma già data alla politica.
2. **Con Brain vero** e un modello finto: «Cancellali tutti.» → la domanda; «Sì.» → annullati;
   «No.» → niente annullato, anche se il modello richiama il tool.
3. **La classe d'effetto** (calliope/valore.py): E3 per «tutto», E2 per una voce e per «tutti
   i timer».

    python prove\\prova_agenda_tutto.py
"""

import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from calliope import valore
from calliope.agenda import Agenda
from calliope.brain import Brain
from calliope.config import Config
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

from prove.prova_politica import ChiParla, Persone, chiama, testo

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    if not ok:
        errori += 1
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok else ""),
          flush=True)


DARIO = "dario"            # l'id del profilo di Dario in prove/prova_politica.Persone


def agenda_con(voci) -> Agenda:
    ag = Agenda(str(Path(tempfile.mkdtemp(prefix="calliope_agenda_tutto_")) / "agenda.db"))
    for kind, label in voci:
        ag.add(kind, label, time.time() + 3600, owner=DARIO, owner_name="Dario")
    return ag


def etichette(ag) -> list[str]:
    return sorted(it["label"] for it in ag.items(DARIO))


REG = build_registry()


def ctx_per(ag, **kw) -> ToolContext:
    ctx = ToolContext(cfg=Config(), speakers=Persone(), speaker_ctx=ChiParla("Dario", "amministra"),
                      speaker=None, agenda=ag)
    for k, v in kw.items():
        setattr(ctx, k, v)
    return ctx


def annulla(ctx, cosa):
    return json.loads(REG.call("agenda_annulla", {"cosa": cosa}, ctx, "amministra"))


DUE = [("promemoria", "innaffiare il basilico"), ("appuntamento", "dal veterinario")]


# ─────────────────────────── 1. il tool ───────────────────────────

def prova_tool():
    for cosa in ("tutti", "tutto", "annulla tutto", "tutti e due"):
        ag = agenda_con(DUE)
        ctx = ctx_per(ag)
        r = annulla(ctx, cosa)
        frase = r.get("risposta_finale", "")
        sosp = r.get("in_sospeso") or {}
        verifica(f"2 voci e «{cosa}»: niente annullato, chiede con l'elenco",
                 etichette(ag) == ["dal veterinario", "innaffiare il basilico"]
                 and r.get("ok") is False and frase.endswith("Annullo tutti e 2?")
                 and "il promemoria di innaffiare il basilico" in frase
                 and "l'appuntamento «dal veterinario»" in frase
                 and sosp.get("tool") == "agenda_annulla"
                 and sosp.get("argomenti") == {"cosa": cosa}
                 and sosp.get("domanda") == "Annullo tutti e 2?"
                 and "agenda_tutto_chiede" in ctx.regole and "agenda_tutto" not in ctx.regole,
                 f"{etichette(ag)} {r} {ctx.regole}")
    # Il «sì»: la proposta in sospeso per chi parla è di agenda_annulla e annullava tutto
    ag = agenda_con(DUE)
    ctx = ctx_per(ag, tool_in_sospeso="agenda_annulla",
                  politica=SimpleNamespace(args_sospeso={"cosa": "tutti"}))
    r = annulla(ctx, "tutti")
    verifica("al «sì» (proposta di agenda_annulla su «tutti»): annullati entrambi",
             etichette(ag) == [] and r.get("ok") is True and "agenda_tutto" in ctx.regole
             and "agenda_tutto_chiede" not in ctx.regole
             and r.get("conferma", "").startswith("Ho annullato "), f"{r} {ctx.regole}")
    # Senza la politica del turno (chiamate del codice): basta il tool in sospeso
    ag = agenda_con(DUE)
    r = annulla(ctx_per(ag, tool_in_sospeso="agenda_annulla"), "tutto")
    verifica("al «sì» senza gli argomenti proposti: annullati", etichette(ag) == [], str(r))
    # La conferma già data alla politica (politica_accettata, la imposta la politica solo per
    # la durata della chiamata: qui la funzione del tool chiamata direttamente)
    ag = agenda_con(DUE)
    r = REG.get("agenda_annulla").func(ctx_per(ag, politica_accettata=True), cosa="tutto")
    verifica("confermata alla politica: annullati senza un'altra domanda", etichette(ag) == [],
             str(r))
    # Più di 4 voci: l'elenco si accorcia
    ag = agenda_con([("promemoria", f"voce {i}") for i in range(6)])
    r = annulla(ctx_per(ag), "tutto")
    verifica("6 voci: elenco di 4 e «altre 2 voci», niente annullato",
             len(etichette(ag)) == 6 and "altre 2 voci" in r.get("risposta_finale", "")
             and r.get("risposta_finale", "").endswith("Annullo tutti e 6?"), str(r))

    # ── contrari ──
    ag = agenda_con([("promemoria", "innaffiare il basilico")])
    ctx = ctx_per(ag)
    r = annulla(ctx, "tutto")
    verifica("contrario: 1 promemoria e «tutto» → annullato senza domanda",
             etichette(ag) == [] and r.get("ok") is True and "in_sospeso" not in r
             and "agenda_tutto_chiede" not in ctx.regole, f"{r} {ctx.regole}")
    ag = agenda_con(DUE + [("timer", "della pasta")])
    ctx = ctx_per(ag)
    r = annulla(ctx, "il timer della pasta")
    verifica("contrario: «il timer della pasta» → solo quello, come prima",
             etichette(ag) == ["dal veterinario", "innaffiare il basilico"]
             and r.get("ok") is True and "in_sospeso" not in r
             and "agenda_tutto_chiede" not in ctx.regole, f"{r} {ctx.regole}")
    ag = agenda_con([("timer", "della pasta"), ("timer", "delle uova"),
                     ("promemoria", "innaffiare il basilico")])
    r = annulla(ctx_per(ag), "tutti i timer")
    verifica("contrario: «tutti i timer» (soli timer, durano minuti) → annullati senza domanda",
             etichette(ag) == ["innaffiare il basilico"] and r.get("ok") is True, str(r))
    ag = agenda_con(DUE)
    r = annulla(ctx_per(ag, tool_in_sospeso="lista_togli"), "tutti")
    verifica("contrario: la proposta in sospeso è di un altro tool → chiede, niente annullato",
             len(etichette(ag)) == 2 and "in_sospeso" in r, str(r))
    ag = agenda_con(DUE)
    r = annulla(ctx_per(ag, tool_in_sospeso="agenda_annulla",
                        politica=SimpleNamespace(args_sospeso={"cosa": "dal veterinario"})),
                "tutti")
    verifica("contrario: la proposta era di una voce sola («Annullo l'appuntamento…?»), il "
             "modello chiama «tutti» → chiede, niente annullato",
             len(etichette(ag)) == 2 and "in_sospeso" in r, str(r))
    ag = agenda_con([])
    r = annulla(ctx_per(ag), "tutto")
    verifica("contrario: agenda vuota → la frase di sempre, nessuna proposta",
             "non c'è nessun timer" in r.get("risposta_finale", "") and "in_sospeso" not in r,
             str(r))


# ─────────────────────────── 2. con Brain vero ───────────────────────────

class Copione:
    """Il modello finto: risponde dal copione."""
    def __init__(self):
        self.risposte = []

    def stream(self, messages, tools):
        if not self.risposte:
            yield ("text", "Va bene.")
            return
        yield from self.risposte.pop(0)


def brain_con(ag) -> Brain:
    cfg = Config()
    cfg.storia_inattiva_s = 0
    b = Brain(cfg, REG, ctx_per(ag))
    b.backend = Copione()
    return b


def turno(b, frase, *risposte):
    b.backend.risposte = list(risposte)
    return "".join(b.stream_reply(frase, "amministra"))


TUTTI = {"cosa": "tutti"}


def prova_brain():
    ag = agenda_con(DUE)
    b = brain_con(ag)
    r = turno(b, "Cancellali tutti.", chiama("agenda_annulla", TUTTI))
    verifica("Brain: «Cancellali tutti.» → la domanda, niente annullato, proposta in sospeso",
             len(etichette(ag)) == 2 and r.rstrip().endswith("Annullo tutti e 2?")
             and b.has_pending() and "agenda_tutto_chiede" in b.rules_fired(),
             f"{r} {b.rules_fired()}")
    r = turno(b, "Sì.", chiama("agenda_annulla", TUTTI), testo("Fatto, annullati tutti e due."))
    verifica("Brain: «Sì.» → annullati entrambi", etichette(ag) == []
             and "agenda_tutto" in b.rules_fired() and not b.has_pending(),
             f"{r} {etichette(ag)} {b.rules_fired()}")

    # Contrario: «No.» e il modello non chiama niente
    ag = agenda_con(DUE)
    b = brain_con(ag)
    turno(b, "Cancellali tutti.", chiama("agenda_annulla", TUTTI))
    turno(b, "No.", testo("Va bene, non annullo niente."))
    verifica("Brain: «No.» → niente annullato", len(etichette(ag)) == 2, str(etichette(ag)))
    # …e anche se il modello richiama il tool dopo il «no»: la proposta è chiusa, si richiede
    ag = agenda_con(DUE)
    b = brain_con(ag)
    turno(b, "Cancellali tutti.", chiama("agenda_annulla", TUTTI))
    r = turno(b, "No.", chiama("agenda_annulla", TUTTI), testo("Va bene."))
    verifica("Brain: «No.» con il modello che richiama il tool → niente annullato",
             len(etichette(ag)) == 2, f"{r} {etichette(ag)} {b.rules_fired()}")
    # Contrario: una voce sola, nessuna domanda
    ag = agenda_con([("promemoria", "innaffiare il basilico")])
    b = brain_con(ag)
    r = turno(b, "Cancellali tutti.", chiama("agenda_annulla", TUTTI), testo("Fatto."))
    verifica("Brain: una voce sola → annullata subito", etichette(ag) == []
             and not b.has_pending() and "agenda_tutto_chiede" not in b.rules_fired(),
             f"{r} {b.rules_fired()}")


# ─────────────────────────── 3. la classe d'effetto ───────────────────────────

def prova_effetto():
    for cosa, atteso in (("tutti", valore.E3), ("tutto quanto", valore.E3),
                         ("tutti i promemoria", valore.E3), ("tutti gli appuntamenti", valore.E3),
                         ("il timer della pasta", valore.E2), ("il dentista", valore.E2),
                         ("tutti i timer", valore.E2), ("tutte le sveglie", valore.E2),
                         ("il promemoria di salutare tutti", valore.E2)):
        e = valore.effetto("agenda_annulla", {"cosa": cosa}, REG.get("agenda_annulla"))
        verifica(f"effetto di agenda_annulla(«{cosa}») = E{atteso}", e == atteso, f"E{e}")


if __name__ == "__main__":
    prova_tool()
    prova_brain()
    prova_effetto()
    print(f"\n{errori} errori" if errori else "\nTutto a posto.")
    sys.exit(1 if errori else 0)
