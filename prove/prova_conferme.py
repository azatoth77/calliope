"""
Prova a secco delle conferme (04/10/2026, calliope/conferme.py): il «sì» breve di chi
amministra, la proposta valida per più turni, la frase di sfida.

Il caso vero (DGX, 04/10 07:11): Dario chiede uno script, «Procedo?», «Sì, procedi pure.»
(0,9 s di voce, punteggio 0,515) → «chiedi a chi amministra»; poi un turno in mezzo e la
proposta non valeva più. Qui la stessa sequenza con un backend finto, e i casi contrari:
conversazione di un familiare, zona grigia, scritto, impronta incompatibile, conversazione
nuova, un ospite o la TV che dicono «sì» o le parole della sfida.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope import conferme as C
from calliope.brain import Brain
from calliope.config import Config
from calliope.speaker_id import SpeakerContext
from calliope.tools.registry import REFUSAL, ToolRegistry
from calliope.tools.spec import ToolContext, ToolSpec

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


class Prof:
    def __init__(self, nome, admin=False):
        self.name, self.id, self.admin = nome, nome.lower() + "-id", admin


class Persone:
    """Fa da SpeakerRegistry (per SpeakerContext) e da speakers del ToolContext."""

    def __init__(self):
        self.cfg = Config()
        self.users = {"Dario": Prof("Dario", True), "Bianca": Prof("Bianca")}

    def get(self, n):
        return self.users.get(n)


def frase(sc, nome, come, punteggio=0.7, in_session=True):
    """Una frase riconosciuta come in main.py: chi, come, e il punteggio contro il suo profilo."""
    sc.identified_by = come
    sc.from_session = come in ("breve", "conversazione")
    sc.current_speaker = nome
    sc.aggiorna_conversazione(nome, come, in_session, punteggio)


# ─────────────────────────── chi può confermare con una frase breve ───────────────────────────

def prova_conversazione():
    p = Persone()
    sc = SpeakerContext(p)
    ctx = ToolContext(cfg=p.cfg, speakers=p, speaker_ctx=sc, speaker=None)
    frase(sc, "Dario", "voce", 0.71, in_session=False)
    frase(sc, "Dario", "breve", 0.515)
    verifica("frase breve con conversazione di chi amministra → conferma",
             sc.conferma_breve and C.admin_confermato(ctx) and sc.current_level == "familiare")
    frase(sc, "Dario", "breve", 0.30)
    verifica("frase breve con l'impronta incompatibile (0,30 < 0,40) → no",
             not sc.conferma_breve and C.admin_da_sentire(ctx))
    frase(sc, "Dario", "breve", 0.52, in_session=False)
    verifica("conversazione nuova (dopo il nome): la voce di prima non vale → no",
             not sc.conferma_breve and sc.voce_sicura is None)
    frase(sc, "Dario", "voce", 0.7)
    frase(sc, None, None, 0.1)
    frase(sc, "Dario", "breve", 0.6)
    verifica("un ospite in mezzo: si riparte → no", not sc.conferma_breve)
    frase(sc, "Bianca", "voce", 0.7, in_session=False)
    frase(sc, "Bianca", "breve", 0.7)
    verifica("conversazione di un familiare → no (Bianca non amministra)",
             not sc.conferma_breve and not C.admin_confermato(ctx))
    frase(sc, "Dario", "conversazione", 0.45, in_session=False)
    frase(sc, "Dario", "breve", 0.6)
    verifica("solo zona grigia nella conversazione → no", not sc.conferma_breve)
    frase(sc, "Dario", "voce", 0.7)
    frase(sc, "Dario", "conversazione", 0.45)
    verifica("frase in zona grigia → non conferma, è chi amministra da sentire",
             not C.admin_confermato(ctx) and C.admin_da_sentire(ctx))
    frase(sc, "Dario", "breve", 0.55)
    verifica("dopo la zona grigia la voce sicura resta: il «sì» breve conferma", sc.conferma_breve)


# ─────────────────────────── il registro dei tool ───────────────────────────

def registro():
    reg = ToolRegistry()
    fatti = []
    reg.register(ToolSpec(name="azione_admin", description="", parameters={},
                          func=lambda ctx, **a: fatti.append(a) or {"ok": True, "conferma": "Fatto."},
                          risk="azione", levels=frozenset({"amministra"})))
    return reg, fatti


def prova_registro():
    p = Persone()
    sc = SpeakerContext(p)
    ctx = ToolContext(cfg=p.cfg, speakers=p, speaker_ctx=sc, speaker=None)
    reg, fatti = registro()

    def call(level=None):
        out = json.loads(reg.call("azione_admin", {"x": 1}, ctx, level or sc.current_level))
        return out

    frase(sc, "Dario", "voce", 0.7, in_session=False)
    frase(sc, "Dario", "breve", 0.515)
    ctx.tool_in_sospeso = "azione_admin"
    ctx.regole = []
    out = call()
    verifica("«sì» breve al tool proposto, conversazione sicura → eseguito",
             out.get("ok") and fatti and "conferma_breve" in ctx.regole, str(out))
    verifica("dopo la chiamata la frase resta «breve» (solo per quel tool)",
             sc.identified_by == "breve" and sc.current_level == "familiare")
    fatti.clear()
    ctx.tool_in_sospeso = None
    out = call()
    verifica("lo stesso «sì» breve per un tool non proposto → frase di sfida, mai «chiedi a chi "
             "amministra»", not fatti and "ripeti:" in out["risposta_finale"]
             and "chiedi a chi amministra" not in out["risposta_finale"], out["risposta_finale"])
    sc.sfida = None
    ctx.tool_in_sospeso = "azione_admin"
    frase(sc, "Dario", "breve", 0.30)
    out = call()
    verifica("«sì» breve con l'impronta incompatibile → frase di sfida", not fatti
             and "ripeti:" in out["risposta_finale"], out["risposta_finale"])
    s1 = sc.sfida
    out = call()
    verifica("chiesta di nuovo, la stessa sfida (stesse parole)", sc.sfida is s1
             and s1.testo in out["risposta_finale"])
    sc.sfida = None
    frase(sc, "Dario", "conversazione", 0.45)
    out = call()
    verifica("zona grigia → frase di sfida", not fatti and "ripeti:"
             in out["risposta_finale"], out["risposta_finale"])
    p.cfg.conferma_sfida = False
    out = call()
    verifica("sfida spenta → «mi serve sentirti meglio», mai «chiedi a chi amministra»",
             out["risposta_finale"] == C.SENTIRTI_MEGLIO, out["risposta_finale"])
    p.cfg.conferma_sfida = True
    sc.sfida = None
    frase(sc, "Bianca", "voce", 0.7, in_session=False)
    frase(sc, "Bianca", "breve", 0.7)
    out = call()
    verifica("familiare: il rifiuto di sempre", not fatti
             and out["risposta_finale"] == REFUSAL["familiare"], out["risposta_finale"])
    frase(sc, None, None, 0.1)
    out = call()
    verifica("ospite: il rifiuto di sempre", not fatti
             and out["risposta_finale"] == REFUSAL["ospite"], out["risposta_finale"])
    # Scritto da uno schermo personale: serve la voce (03/10), non la sfida
    sc.current_speaker, sc.identified_by, sc.from_session = "Dario", "schermo", False
    out = call()
    verifica("scritto → serve la voce", not fatti and "mi serve la tua voce"
             in out["risposta_finale"], out["risposta_finale"])


# ─────────────────────────── proposta valida per più turni ───────────────────────────

def prova_validita():
    cfg = Config()
    verifica("proposta: mai nello stesso turno", not C.proposta_valida(cfg, 5, 5))
    verifica("proposta: valida 1, 2 e 3 turni dopo",
             all(C.proposta_valida(cfg, 5, t) for t in (6, 7, 8)))
    verifica("proposta: non 4 turni dopo", not C.proposta_valida(cfg, 5, 9))
    verifica("predefiniti: 3 turni, 120 s, sfida 60 s",
             (cfg.azione_in_sospeso_turni, cfg.azione_in_sospeso_s, cfg.conferma_sfida_s)
             == (3, 120.0, 60.0))

    # Offerte dei lavori (agenti/servizio.py)
    import threading
    from calliope.agenti.servizio import Lavori

    class Lav:
        id, tipo, compito = "L1", "codice", "script"
    svc = Lavori.__new__(Lavori)
    svc._lock, svc._offerte, svc.cfg = threading.Lock(), {}, cfg
    svc._offerte["dario-id"] = {"lavoro": Lav(), "turno": 1, "scade": time.monotonic() + 120}
    verifica("lavoro: un altro id non consuma la proposta",
             svc.conferma("dario-id", "L9", 2) is None and "dario-id" in svc._offerte)
    verifica("lavoro: un'altra persona non la conferma mai", svc.conferma("bianca-id", "L1", 2)
             is None and "dario-id" in svc._offerte)
    verifica("lavoro: confermata 3 turni dopo", svc.conferma("dario-id", "L1", 4) is not None
             and "dario-id" not in svc._offerte)
    svc._offerte["dario-id"] = {"lavoro": Lav(), "turno": 1, "scade": time.monotonic() + 120}
    verifica("lavoro: non 4 turni dopo", svc.conferma("dario-id", "L1", 5) is None)
    svc._offerte["dario-id"] = {"lavoro": Lav(), "turno": 1, "scade": time.monotonic() - 1}
    verifica("lavoro: scaduta dopo 120 s", svc.conferma("dario-id", "L1", 2) is None
             and "dario-id" not in svc._offerte)

    # Azione in sospeso di Brain: resta per 3 turni della stessa persona
    b = brain([[("text", "Ok.")]] * 6)
    sc = b.tool_ctx.speaker_ctx
    frase(sc, "Dario", "voce", 0.7, in_session=False)
    b.turn_number = 1
    b.set_pending({"tool": "azione_admin", "domanda": "Procedo?", "cosa": "x",
                   "argomenti": {"x": 1}})
    visti = []
    for _ in range(4):
        "".join(b.stream_reply("Parliamo d'altro.", "amministra"))
        visti.append(any("Azione in sospeso" in m.get("content", "")
                         for m in b.backend.visti[-1] if m["role"] == "system"))
    verifica("azione in sospeso: nei 3 turni dopo sì, al quarto no", visti
             == [True, True, True, False], str(visti))
    b.turn_number = 10
    b.set_pending({"tool": "azione_admin", "domanda": "Procedo?", "cosa": "x",
                   "argomenti": {"x": 1}})
    b.pending["scade"] = time.monotonic() - 1
    "".join(b.stream_reply("Sì.", "amministra"))
    verifica("azione in sospeso: scaduta dopo i secondi", not any(
        "Azione in sospeso" in m.get("content", "") for m in b.backend.visti[-1]))
    b.set_pending({"tool": "azione_admin", "domanda": "Procedo?", "cosa": "x",
                   "argomenti": {"x": 1}})
    frase(sc, "Bianca", "voce", 0.7)
    "".join(b.stream_reply("Sì.", "familiare"))
    verifica("azione in sospeso: il «sì» di un'altra persona no", not any(
        "Azione in sospeso" in m.get("content", "") for m in b.backend.visti[-1])
             and b.pending is None)


# ─────────────────────────── frase di sfida ───────────────────────────

class BackendFinto:
    """Risponde a copione (come in prova_brain.py)."""

    def __init__(self, copione):
        self.copione = list(copione)
        self.visti = []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        yield from (self.copione.pop(0) if self.copione else [("text", "Ok.")])


def brain(copione):
    p = Persone()
    b = Brain.__new__(Brain)
    reg, fatti = registro()
    b.cfg, b.tools, b.history = p.cfg, reg, []
    b.tool_ctx = ToolContext(cfg=p.cfg, speakers=p, speaker_ctx=SpeakerContext(p), speaker=None)
    b.backend = BackendFinto(copione)
    b.fatti = fatti
    return b


def sfida_per(b, nome="Dario", tool="azione_admin", argomenti=None, scade_tra=60):
    s = C.nuova_sfida(b.cfg, b.tool_ctx.speakers.get(nome).id, tool, argomenti or {"x": 1})
    s.parole, s.numero = ("girasole", "treno", "limone"), 42
    s.scade = time.monotonic() + scade_tra
    b.tool_ctx.speaker_ctx.sfida = s
    return s


def prova_sfida():
    s = C.Sfida("d", ("girasole", "treno", "limone"), 42, "t")
    verifica("numeri in lettere", [C.numero_in_lettere(n) for n in (21, 28, 33, 42, 99)]
             == ["ventuno", "ventotto", "trentatré", "quarantadue", "novantanove"])
    verifica("testo della sfida", s.testo == "girasole, treno, limone, quarantadue", s.testo)
    for testo, atteso in (("Girasole, treno, limone, 42.", "ok"),
                          ("girasole treno limone quarantadue", "ok"),
                          ("Calliope, girasoli, treno, limoni, quaranta due", "ok"),
                          ("girasole, treno, 42", "parziale"),
                          ("girasole e treno", "parziale"),
                          ("sì, procedi pure", "no"), ("treno", "no"),
                          ("girasole treno limone 43", "parziale")):
        verifica(f"confronto «{testo}» → {atteso}", C.confronta(s, testo) == atteso,
                 C.confronta(s, testo))
    verifica("parole dell'elenco tutte diverse e lontane tra loro", len(set(C.PAROLE))
             == len(C.PAROLE) and all(
                 __import__("difflib").SequenceMatcher(None, a, b).ratio() < 0.8
                 for i, a in enumerate(C.PAROLE) for b in C.PAROLE[i + 1:]))

    # Parole giuste e voce giusta → l'azione proposta si esegue, senza il modello
    b = brain([])
    sc = b.tool_ctx.speaker_ctx
    frase(sc, "Dario", "voce", 0.68)
    sfida_per(b)
    detto = "".join(b.stream_reply("Girasole, treno, limone, quarantadue.", "amministra"))
    verifica("parole giuste e voce giusta → eseguita", b.fatti == [{"x": 1}] and detto == "Fatto."
             and "sfida_risposta" in b.rules_fired() and sc.sfida is None, detto)
    verifica("sfida: nella storia la frase detta e il risultato", [m["role"] for m in b.history]
             == ["user", "assistant", "tool", "assistant"])
    # Parole giuste e voce sconosciuta (la TV, un ospite) → no
    b = brain([])
    sc = b.tool_ctx.speaker_ctx
    frase(sc, None, None, 0.12)
    sfida_per(b)
    detto = "".join(b.stream_reply("Girasole, treno, limone, quarantadue.", "ospite"))
    verifica("parole giuste e voce sconosciuta → no", not b.fatti and detto == C.SFIDA_ALTRA_VOCE
             and sc.sfida is None, detto)
    # Parole giuste, voce di un'altra persona di casa → no
    b = brain([])
    sc = b.tool_ctx.speaker_ctx
    frase(sc, "Bianca", "voce", 0.7)
    sfida_per(b)
    detto = "".join(b.stream_reply("Girasole, treno, limone, quarantadue.", "familiare"))
    verifica("parole giuste e voce di un'altra persona → no", not b.fatti
             and detto == C.SFIDA_ALTRA_VOCE, detto)
    # Voce giusta ma parole mancanti → ripeti; due volte → non procedo
    b = brain([])
    sc = b.tool_ctx.speaker_ctx
    frase(sc, "Dario", "voce", 0.7)
    sfida_per(b)
    detto = "".join(b.stream_reply("Girasole, treno, quarantadue.", "amministra"))
    verifica("voce giusta ma una parola mancante → ripeti, niente eseguito", not b.fatti
             and detto.startswith("Non ho sentito tutte le parole") and sc.sfida is not None,
             detto)
    detto = "".join(b.stream_reply("Girasole e treno.", "amministra"))
    verifica("di nuovo sbagliate → non procedo", not b.fatti and detto == C.SFIDA_FALLITA
             and sc.sfida is None, detto)
    # Voce giusta, parole sbagliate del tutto: non è una risposta alla sfida (va al modello)
    b = brain([[("text", "Va bene.")]])
    sc = b.tool_ctx.speaker_ctx
    frase(sc, "Dario", "voce", 0.7)
    sfida_per(b)
    detto = "".join(b.stream_reply("Che ore sono?", "amministra"))
    verifica("parole sbagliate → niente eseguito, la frase va al modello", not b.fatti
             and detto == "Va bene." and sc.sfida is not None, detto)
    # Scaduta
    b = brain([])
    sc = b.tool_ctx.speaker_ctx
    frase(sc, "Dario", "voce", 0.7)
    sfida_per(b, scade_tra=-1)
    detto = "".join(b.stream_reply("Girasole, treno, limone, quarantadue.", "amministra"))
    verifica("sfida scaduta → no", not b.fatti and detto == C.SFIDA_SCADUTA, detto)
    # Parole giuste ma impronta incerta (zona grigia) → parole nuove, una volta
    b = brain([])
    sc = b.tool_ctx.speaker_ctx
    frase(sc, "Dario", "voce", 0.7)
    frase(sc, "Dario", "conversazione", 0.44)
    vecchia = sfida_per(b)
    detto = "".join(b.stream_reply("Girasole, treno, limone, quarantadue.", "familiare"))
    verifica("parole giuste, voce incerta → parole nuove", not b.fatti and sc.sfida is not None
             and sc.sfida is not vecchia and detto.startswith("Non ho riconosciuto bene"), detto)
    # Il «sì» dopo la sfida, con la voce: vale come sempre
    verifica("una sfida chiesta non blocca le altre conferme a voce", C.serve_conferma(
        b.tool_ctx, "azione_admin", {"x": 1}, "x") is not None)   # ancora zona grigia


# ─────────────────────────── il caso vero del 04/10, in 4 turni ───────────────────────────

def prova_caso_vero():
    """Dario chiede uno script (voce), «Procedo?»; «Sì, procedi pure.» (0,9 s, 0,515): ora
    parte. Variante con l'impronta breve incompatibile: sfida, poi un turno in mezzo, poi
    la sfida ripetuta (2,7 s, 0,706) → parte, e la proposta vale ancora."""
    def nuovo(copione):
        b = brain(copione)
        stato = {"offerta": None}

        def lavoro(ctx, conferma=False, **_):
            if not conferma:
                stato["offerta"] = ctx.turno
                return {"ok": True, "fatto": "proposta", "risposta_finale": "Procedo?",
                        "in_sospeso": {"domanda": "Procedo?", "cosa": "lo script",
                                       "tool": "lavoro_finto", "argomenti": {"conferma": True}}}
            if stato["offerta"] is None or not C.proposta_valida(ctx.cfg, stato["offerta"],
                                                                  ctx.turno):
                return {"ok": False, "risposta_finale": "Prima devo dirti cosa affido."}
            if not C.admin_confermato(ctx):
                sf = C.serve_conferma(ctx, "lavoro_finto", {"conferma": True}, "lo script")
                return sf or {"ok": False, "risposta_finale": "Solo chi amministra."}
            stato["offerta"] = None
            b.fatti.append("avviato")
            return {"ok": True, "risposta_finale": "Ci lavoro in secondo piano."}
        b.tools.register(ToolSpec(name="lavoro_finto", description="", parameters={},
                                  func=lavoro, risk="azione", classe="pericoloso",
                                  levels=frozenset({"familiare", "amministra"})))
        return b

    chiama = [("calls", [{"id": "c0", "name": "lavoro_finto", "arguments": {}}])]
    conferma = [("calls", [{"id": "c1", "name": "lavoro_finto",
                            "arguments": {"conferma": True}}])]
    b = nuovo([chiama, conferma])
    sc = b.tool_ctx.speaker_ctx
    frase(sc, "Dario", "voce", 0.71, in_session=False)
    d1 = "".join(b.stream_reply("Calliope, scrivimi uno script che rinomina le foto", "amministra"))
    frase(sc, "Dario", "breve", 0.515)
    d2 = "".join(b.stream_reply("Sì, procedi pure.", sc.current_level))
    verifica("caso vero: «Sì, procedi pure.» breve (0,515) dopo la proposta → parte",
             (d1, d2, b.fatti) == ("Procedo?", "Ci lavoro in secondo piano.", ["avviato"])
             and "conferma_breve" in b.rules_fired(), f"{d1} / {d2}")

    # Variante: impronta breve incompatibile → sfida; turno in mezzo; sfida → parte
    b = nuovo([chiama, conferma, [("text", "Certo, ti ascolto.")]])
    sc = b.tool_ctx.speaker_ctx
    frase(sc, "Dario", "voce", 0.71, in_session=False)
    "".join(b.stream_reply("Calliope, scrivimi uno script", "amministra"))
    frase(sc, "Dario", "breve", 0.31)
    d2 = "".join(b.stream_reply("Sì, procedi pure.", sc.current_level))
    s = sc.sfida
    frase(sc, "Dario", "voce", 0.51)
    d3 = "".join(b.stream_reply("Scusa, io sono chi amministra.", sc.current_level))
    frase(sc, "Dario", "voce", 0.706)
    d4 = "".join(b.stream_reply(s.testo.replace(",", "") if s else "", sc.current_level))
    verifica("variante: sfida, turno in mezzo, sfida ripetuta → parte (proposta ancora valida)",
             "ripeti:" in d2 and b.fatti == ["avviato"]
             and d4 == "Ci lavoro in secondo piano.", f"{d2} / {d3} / {d4}")

    # Contrario: dopo la proposta a Dario, un ospite dice «sì» → rifiutato
    b = nuovo([chiama, conferma])
    sc = b.tool_ctx.speaker_ctx
    frase(sc, "Dario", "voce", 0.71, in_session=False)
    "".join(b.stream_reply("Calliope, scrivimi uno script", "amministra"))
    frase(sc, None, None, 0.15)
    d2 = "".join(b.stream_reply("Sì.", sc.current_level))
    verifica("contrario: l'ospite dice «sì» dopo la proposta a Dario → niente",
             not b.fatti and b.pending is None, d2)
    # Contrario: la TV (voce sconosciuta) dice le parole della sfida → rifiutata
    b = nuovo([chiama, conferma])
    sc = b.tool_ctx.speaker_ctx
    frase(sc, "Dario", "voce", 0.71, in_session=False)
    "".join(b.stream_reply("Calliope, scrivimi uno script", "amministra"))
    frase(sc, "Dario", "breve", 0.2)
    "".join(b.stream_reply("Sì.", sc.current_level))
    s = sc.sfida
    frase(sc, None, None, 0.18)
    b.tool_ctx.speaker_ctx.sfida = s     # la conversazione si chiude, ma anche se restasse
    b.conv_owner = None
    d4 = "".join(b.stream_reply(s.testo, sc.current_level))
    verifica("contrario: la TV ripete le parole della sfida → rifiutata",
             not b.fatti and d4 == C.SFIDA_ALTRA_VOCE, d4)


prova_conversazione()
prova_registro()
prova_validita()
prova_sfida()
prova_caso_vero()
print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
