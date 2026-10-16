import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Annullare tutta l'agenda si conferma (16/10/2026, #99; caso vero della DGX del 15/10 sera,
riscritto con nomi di fantasia). In auto chi amministra si fa leggere la lista della spesa (due
voci) e dice «cancellare entrambi»: il modello chiama agenda_annulla(cosa=tutti), eseguito
senza domanda. L'agenda era vuota; con appuntamenti e promemoria li avrebbe persi tutti.

A secco, con l'agenda vera in un database temporaneo:

1. **Il tool**: con più voci da annullare (non soli timer che scadono entro un'ora) niente si
   annulla, la risposta dice che cosa c'è e chiede («Annullo tutti e 2?», regola
   `agenda_tutto_chiede`), con la proposta in sospeso e gli id delle voci nominate. Al «sì»
   (proposta di agenda_annulla per chi parla **e** una frase di consenso, o la sfida) si annullano
   solo le voci nominate. Contrari (revisione della PR #110): la richiamata con «Intendevo quelli
   della lista della spesa.» o «Cancella le zucchine dalla lista.», una voce aggiunta dopo la
   domanda, un appuntamento fuori da «tutti i promemoria», una sveglia di 8 ore fra i timer; e
   una voce sola, «il timer della pasta», i timer brevi, la proposta di un altro tool o di una
   voce sola, l'agenda vuota.
2. **Con Brain vero** e un modello finto: «Cancellali tutti.» → la domanda; «Sì.» → annullati;
   «No.» e le frasi che non acconsentono → niente annullato, anche se il modello richiama il
   tool; con la stanza accesa la domanda è quella del tool e il «Sì.» annulla senza sfida.
3. **La classe d'effetto** resta E2 (decisione della revisione: chiede il tool, niente sfida).

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

try:
    sys.stdout.reconfigure(encoding="utf-8")    # «→» e accenti anche nella console cp1252
except (AttributeError, ValueError):
    pass

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    if not ok:
        errori += 1
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok else ""),
          flush=True)


DARIO = "dario"            # l'id del profilo di Dario in prove/prova_politica.Persone


def agenda_con(voci) -> Agenda:
    """Voci (tipo, etichetta[, secondi da adesso]) di Dario, in un database nuovo."""
    ag = Agenda(str(Path(tempfile.mkdtemp(prefix="calliope_agenda_tutto_")) / "agenda.db"))
    for kind, label, *tra in voci:
        ag.add(kind, label, time.time() + (tra[0] if tra else 3600), owner=DARIO,
               owner_name="Dario")
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


def risposta(ag, frase, cosa="tutti", sospeso="tutti", sfida=False):
    """La richiamata nel turno dopo la domanda: proposta di agenda_annulla su `sospeso`, la frase
    di chi parla nella politica del turno."""
    ctx = ctx_per(ag, tool_in_sospeso="agenda_annulla",
                  politica=SimpleNamespace(args_sospeso={"cosa": sospeso}, testo=frase,
                                           sfida=sfida))
    return annulla(ctx, cosa), ctx


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
                 and len(getattr(ag, "proposte_tutto", {}).get(DARIO, ())) == 2
                 and "agenda_tutto_chiede" in ctx.regole and "agenda_tutto" not in ctx.regole,
                 f"{etichette(ag)} {r} {ctx.regole}")
    # Il «sì»: proposta di agenda_annulla su «tutti» e una frase di consenso (o la sfida)
    for frase, sfida in (("Sì.", False), ("Sì, annullali pure.", False), ("Va bene.", False),
                         ("girasole, treno, limone", True)):
        ag = agenda_con(DUE)
        annulla(ctx_per(ag), "tutti")
        r, ctx = risposta(ag, frase, sfida=sfida)
        verifica(f"al «{frase}»{' (sfida)' if sfida else ''}: annullati entrambi",
                 etichette(ag) == [] and r.get("ok") is True and "agenda_tutto" in ctx.regole
                 and "agenda_tutto_chiede" not in ctx.regole and DARIO not in getattr(ag, "proposte_tutto", {})
                 and r.get("conferma", "").startswith("Ho annullato "), f"{r} {ctx.regole}")
    # Senza la politica del turno (chiamate del codice): la frase di chi parla dal contesto
    ag = agenda_con(DUE)
    annulla(ctx_per(ag), "tutto")
    r = annulla(ctx_per(ag, tool_in_sospeso="agenda_annulla", user_text="Sì, certo."), "tutto")
    verifica("al «sì» senza la politica del turno (frase nel contesto): annullati",
             etichette(ag) == [], str(r))
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

    # ── contrari: la richiamata senza un consenso (revisione della PR #110) ──
    for frase in ("Intendevo quelli della lista della spesa.",
                  "Cancella le zucchine dalla lista.", "No.", "Sì, però ascolta, era la lista."):
        ag = agenda_con(DUE)
        annulla(ctx_per(ag), "tutti")
        r, ctx = risposta(ag, frase)
        verifica(f"contrario: richiamata con «{frase}» → niente annullato, chiede di nuovo",
                 len(etichette(ag)) == 2 and "in_sospeso" in r
                 and "agenda_tutto" not in ctx.regole, f"{r} {ctx.regole}")
    # ── contrari: al «sì» solo le voci nominate nella domanda ──
    ag = agenda_con([("promemoria", "innaffiare il basilico"), ("promemoria", "ritirare il pane"),
                     ("appuntamento", "dal veterinario")])
    r = annulla(ctx_per(ag), "tutti i promemoria")
    verifica("«tutti i promemoria»: la domanda nomina i 2 promemoria",
             r.get("risposta_finale", "").endswith("Annullo tutti e 2?")
             and "veterinario" not in r.get("risposta_finale", ""), str(r))
    r, _ = risposta(ag, "Sì.", cosa="tutto", sospeso="tutti i promemoria")
    verifica("contrario: «Sì.» con la richiamata «tutto» → solo i 2 promemoria, l'appuntamento "
             "mai nominato resta", etichette(ag) == ["dal veterinario"], f"{etichette(ag)} {r}")
    ag = agenda_con(DUE)
    annulla(ctx_per(ag), "tutti")
    ag.add("promemoria", "chiamare l'idraulico", time.time() + 7200, owner=DARIO,
           owner_name="Dario")
    r, _ = risposta(ag, "Sì.")
    verifica("contrario: una voce aggiunta dopo la domanda non si annulla al «sì»",
             etichette(ag) == ["chiamare l'idraulico"], f"{etichette(ag)} {r}")
    # ── contrari di sempre ──
    ag = agenda_con([("promemoria", "innaffiare il basilico")])
    ctx = ctx_per(ag)
    r = annulla(ctx, "tutto")
    verifica("contrario: 1 promemoria e «tutto» → annullato senza domanda",
             etichette(ag) == [] and r.get("ok") is True and "in_sospeso" not in r
             and "agenda_tutto_chiede" not in ctx.regole, f"{r} {ctx.regole}")
    ag = agenda_con(DUE + [("timer", "della pasta", 600)])
    ctx = ctx_per(ag)
    r = annulla(ctx, "il timer della pasta")
    verifica("contrario: «il timer della pasta» → solo quello, come prima",
             etichette(ag) == ["dal veterinario", "innaffiare il basilico"]
             and r.get("ok") is True and "in_sospeso" not in r
             and "agenda_tutto_chiede" not in ctx.regole, f"{r} {ctx.regole}")
    ag = agenda_con([("timer", "della pasta", 600), ("timer", "delle uova", 300),
                     ("promemoria", "innaffiare il basilico")])
    r = annulla(ctx_per(ag), "tutti i timer")
    verifica("contrario: «tutti i timer» che scadono entro un'ora → annullati senza domanda",
             etichette(ag) == ["innaffiare il basilico"] and r.get("ok") is True, str(r))
    ag = agenda_con([("timer", "della pasta", 600), ("timer", "di 8 ore", 8 * 3600)])
    r = annulla(ctx_per(ag), "tutti i timer")
    verifica("«tutti i timer» con una sveglia di 8 ore → chiede, niente annullato",
             len(etichette(ag)) == 2 and r.get("risposta_finale", "").endswith(
                 "Annullo tutti e 2?"), str(r))
    ag = agenda_con(DUE)
    annulla(ctx_per(ag), "tutti")
    r = annulla(ctx_per(ag, tool_in_sospeso="lista_togli",
                        politica=SimpleNamespace(testo="Sì.", sfida=False)), "tutti")
    verifica("contrario: la proposta in sospeso è di un altro tool → chiede, niente annullato",
             len(etichette(ag)) == 2 and "in_sospeso" in r, str(r))
    ag = agenda_con(DUE)
    annulla(ctx_per(ag), "tutti")
    r, _ = risposta(ag, "Sì.", sospeso="dal veterinario")
    verifica("contrario: la proposta era di una voce sola («Annullo l'appuntamento…?»), il "
             "modello chiama «tutti» → chiede, niente annullato",
             len(etichette(ag)) == 2 and "in_sospeso" in r, str(r))
    ag = agenda_con(DUE)
    r, _ = risposta(ag, "Sì.")
    verifica("contrario: un «sì» senza la domanda del tool prima (niente id) → chiede",
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


def turno(b, frase, *risposte, stanza=False):
    b.backend.risposte = list(risposte)
    if stanza:
        # La conversazione di stanza accesa: le sue righe sono un dato non fidato del turno
        b.stanza_turno = SimpleNamespace(
            testo="Conversazione della stanza: Nicola: domani porto io la torta.",
            esterno="Nicola: domani porto io la torta.", riassunto="")
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

    # Contrari: frasi che non acconsentono, con o senza la richiamata del modello (revisione
    # della PR #110: anche con un turno in mezzo)
    for frasi in (("No.",), ("Intendevo quelli della lista della spesa.",),
                  ("Che ore sono?", "Cancella le zucchine dalla lista.")):
        for richiama in (False, True):
            ag = agenda_con(DUE)
            b = brain_con(ag)
            turno(b, "Cancellali tutti.", chiama("agenda_annulla", TUTTI))
            for f in frasi:
                r = turno(b, f, *((chiama("agenda_annulla", TUTTI), testo("Va bene."))
                                  if richiama else (testo("Va bene."),)))
            verifica(f"Brain: {' → '.join(frasi)}{' con la richiamata' if richiama else ''} "
                     f"→ niente annullato", len(etichette(ag)) == 2,
                     f"{r} {etichette(ag)} {b.rules_fired()}")
    # Seconda revisione della PR #110: il «Sì.» passa dalla politica (politica_conferma_unica,
    # ACCETTATA) e una voce aggiunta dopo la domanda non si annulla lo stesso; la proposta si toglie
    ag = agenda_con(DUE)
    b = brain_con(ag)
    turno(b, "Cancellali tutti.", chiama("agenda_annulla", TUTTI))
    ag.add("promemoria", "chiamare l'idraulico", time.time() + 7200, owner=DARIO,
           owner_name="Dario")
    r = turno(b, "Sì.", chiama("agenda_annulla", TUTTI), testo("Fatto."))
    verifica("Brain: voce aggiunta dopo la domanda, «Sì.» accettato dalla politica → solo le 2 "
             "nominate, la proposta tolta",
             etichette(ag) == ["chiamare l'idraulico"] and DARIO not in getattr(ag, "proposte_tutto", {})
             and "politica_conferma_unica" in b.rules_fired(),
             f"{r} {etichette(ag)} {b.rules_fired()} {getattr(ag, "proposte_tutto", {})}")
    # «Sì, ma solo il promemoria.»: con la richiamata «tutti» niente annullato; il modello poi
    # chiama la voce indicata
    ag = agenda_con(DUE)
    b = brain_con(ag)
    turno(b, "Cancellali tutti.", chiama("agenda_annulla", TUTTI))
    r = turno(b, "Sì, ma solo il promemoria.", chiama("agenda_annulla", TUTTI),
              chiama("agenda_annulla", {"cosa": "il promemoria di innaffiare il basilico"}),
              testo("Fatto."))
    verifica("Brain: «Sì, ma solo il promemoria.» con la richiamata «tutti» → solo il promemoria",
             etichette(ag) == ["dal veterinario"] and "agenda_tutto_parziale" in b.rules_fired()
             and DARIO not in getattr(ag, "proposte_tutto", {}), f"{r} {etichette(ag)} {b.rules_fired()}")
    for frase in ("Sì, tranne l'appuntamento.", "Va bene, soltanto il promemoria."):
        ag = agenda_con(DUE)
        b = brain_con(ag)
        turno(b, "Cancellali tutti.", chiama("agenda_annulla", TUTTI))
        r = turno(b, frase, chiama("agenda_annulla", TUTTI), testo("Quale annullo?"))
        verifica(f"Brain: «{frase}» con la richiamata «tutti» → niente annullato",
                 len(etichette(ag)) == 2 and "agenda_tutto_parziale" in b.rules_fired(),
                 f"{r} {etichette(ag)} {b.rules_fired()}")
    # Contrario: una voce sola, nessuna domanda
    ag = agenda_con([("promemoria", "innaffiare il basilico")])
    b = brain_con(ag)
    r = turno(b, "Cancellali tutti.", chiama("agenda_annulla", TUTTI), testo("Fatto."))
    verifica("Brain: una voce sola → annullata subito", etichette(ag) == []
             and not b.has_pending() and "agenda_tutto_chiede" not in b.rules_fired(),
             f"{r} {b.rules_fired()}")
    # La stanza accesa: chiede il tool con l'elenco, e il «Sì.» annulla senza la frase di sfida
    ag = agenda_con(DUE)
    b = brain_con(ag)
    r = turno(b, "Cancellali tutti.", chiama("agenda_annulla", TUTTI), stanza=True)
    verifica("Brain, stanza accesa: «Cancellali tutti.» → la domanda del tool con l'elenco",
             len(etichette(ag)) == 2 and r.rstrip().endswith("Annullo tutti e 2?")
             and "basilico" in r and "ripeti" not in r and "stanza_contesto" in b.rules_fired(),
             f"{r} {b.rules_fired()}")
    r = turno(b, "Sì.", chiama("agenda_annulla", TUTTI), testo("Fatto."), stanza=True)
    verifica("Brain, stanza accesa: «Sì.» → annullati, senza sfida", etichette(ag) == []
             and "ripeti" not in r and b.tool_ctx.speaker_ctx.sfida is None,
             f"{r} {etichette(ag)} {b.rules_fired()}")


# ─────────────────────────── 3. la classe d'effetto ───────────────────────────

def prova_effetto():
    for cosa in ("tutti", "tutti i promemoria", "il timer della pasta", "tutti i timer"):
        e = valore.effetto("agenda_annulla", {"cosa": cosa}, REG.get("agenda_annulla"))
        verifica(f"effetto di agenda_annulla(«{cosa}») = E2 (chiede il tool, niente sfida)",
                 e == valore.E2, f"E{e}")


if __name__ == "__main__":
    prova_tool()
    prova_brain()
    prova_effetto()
    print(f"\n{errori} errori" if errori else "\nTutto a posto.")
    sys.exit(1 if errori else 0)
