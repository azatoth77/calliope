"""
Prova a secco del passo 0 della conversazione di stanza (13/10/2026,
docs/ricerche/2026-10-13-conversazione-di-stanza.md § 6, decisione 0029). Utile già senza la
stanza: chiude i difetti del caso vero del 12/10 in auto (telefono come satellite, chi amministra
e il ragazzo registrati, voci tutte riconosciute). Nomi di fantasia: Carlo amministra, Luca è il
minore (le impronte di prova_voci_famiglia).

- (a) In compagnia una frase senza il nome nella finestra d'ascolto ha risposte e letture, mai
  azioni (regola `compagnia_azioni_col_nome`): il «sì» della stessa persona alla proposta passa;
  contrari: una persona sola, col nome, dopo il nome da solo, interruttore spento.
- (b) La conversazione anonima del satellite non si chiude a ogni cambio di persona in compagnia
  (regola `compagnia_anonima_continua`), con chi ha detto cosa nei dati del turno; contrari: una
  persona sola, una voce sconosciuta di mezzo (il caso della password del wifi del 03/10), la
  conversazione di una persona, interruttore spento. Con `eventi: attivo` (15/10, issue #12: la
  storia rifatta dalla proiezione a ogni risposta) i nomi arrivano dagli eventi delle frasi;
  contrario: senza il nome nell'evento resta solo «conversazione di gruppo».
- (c) Il rilevatore di pericolo non vale sulle frasi giudicate non rivolte a Calliope, anche col
  giudizio in ombra (regola `pericolo_non_rivolta`); contrari: frase rivolta, giudizio guasto,
  una persona sola (nessun giudizio), interruttore spento; il guardiano sulle frasi resta.

Ogni caso principale fallisce sulla versione di prima (cd49f11).
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import prova_compagnia as PC
from prova_compagnia import ciclo_finto, frase, riconosci
import prova_voci_famiglia as VF

from calliope import guardiano as guardia
from calliope import rivolta as rivolta_mod
from calliope.brain import Brain
from calliope.ciclo import Turno
from calliope.config import Config
from calliope.conversazione import Conversazione
from calliope.speaker_id import SpeakerContext
from calliope.tools.registry import ToolRegistry
from calliope.tools.spec import ToolContext, ToolSpec

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""),
          flush=True)


# ─────────────────────────── (a) azioni col nome ───────────────────────────

def _registro():
    p = VF.Persone()
    sc = SpeakerContext(p)
    ctx = ToolContext(cfg=p.cfg, speakers=p, speaker_ctx=sc, speaker=None)
    reg = ToolRegistry()
    fatti = []
    tutti = frozenset({"ospite", "familiare", "amministra"})
    # timer_imposta: E1 (azione locale); ora_attuale: lettura (classe «sicuro», E0)
    for nome, classe in (("timer_imposta", None), ("ora_attuale", "sicuro")):
        reg.register(ToolSpec(name=nome, description="", parameters={},
                              func=lambda ctx, _n=nome, **a: fatti.append(_n) or {
                                  "ok": True, "conferma": "Fatto."},
                              risk="azione" if classe is None else "lettura",
                              levels=tutti, classe=classe))
    return p, sc, ctx, reg, fatti


def prova_azioni():
    p, sc, ctx, reg, fatti = _registro()
    # Carlo riconosciuto dalla voce nella frase, in compagnia con il ragazzo (due profili)
    sc.current_speaker, sc.identified_by, sc.from_session = "Carlo", "voce", False
    sc.compagnia, sc.senza_nome = True, True
    ctx.regole = []
    out = json.loads(reg.call("timer_imposta", {"durata": "5 minuti"}, ctx, sc.current_level))
    verifica("in compagnia, senza il nome, voce riconosciuta: l'azione non parte",
             not fatti and out.get("ok") is False
             and "compagnia_azioni_col_nome" in ctx.regole, json.dumps(out, ensure_ascii=False))
    verifica("…e la frase chiede il nome", out.get("risposta_finale")
             == "Dimmi pure «Calliope, …» e lo faccio.", out.get("risposta_finale"))
    out = json.loads(reg.call("ora_attuale", {}, ctx, sc.current_level))
    verifica("in compagnia, senza il nome: una lettura passa", fatti == ["ora_attuale"])
    fatti.clear()
    ctx.tool_in_sospeso = "timer_imposta"
    reg.call("timer_imposta", {"durata": "5 minuti"}, ctx, sc.current_level)
    verifica("in compagnia, senza il nome: il «sì» alla proposta della stessa persona passa",
             fatti == ["timer_imposta"])
    ctx.tool_in_sospeso = None
    fatti.clear()
    sc.senza_nome = False
    reg.call("timer_imposta", {"durata": "5 minuti"}, ctx, sc.current_level)
    verifica("contrario: in compagnia col nome l'azione passa", fatti == ["timer_imposta"])
    fatti.clear()
    sc.compagnia, sc.senza_nome = False, True
    reg.call("timer_imposta", {"durata": "5 minuti"}, ctx, sc.current_level)
    verifica("contrario: una persona sola, senza il nome nella finestra → come oggi",
             fatti == ["timer_imposta"])
    fatti.clear()
    sc.compagnia = True
    p.cfg.compagnia_azioni_col_nome = False
    reg.call("timer_imposta", {"durata": "5 minuti"}, ctx, sc.current_level)
    verifica("interruttore spento (compagnia_azioni_col_nome: false) → come oggi",
             fatti == ["timer_imposta"])
    p.cfg.compagnia_azioni_col_nome = True
    fatti.clear()
    p.cfg.wake_word = "computer"
    out = json.loads(reg.call("timer_imposta", {"durata": "5 minuti"}, ctx, sc.current_level))
    verifica("modalità startrek: la frase dice il nome che sveglia",
             out.get("risposta_finale") == "Dimmi pure «Computer, …» e lo faccio.",
             out.get("risposta_finale"))


def prova_senza_nome_dal_ciclo():
    """Il ciclo segna la frase senza il nome (fase del nome) e la azzera a ogni frase."""
    reg, sc, ciclo, regole = ciclo_finto()
    cfg = reg.cfg
    cfg.wake_word_enabled = True
    ciclo.s.wake = None
    ciclo.s.suoni = None
    ciclo.awake_until = time.monotonic() + 8
    ciclo.listener.started_at = time.monotonic()
    ciclo.rec = {}
    t = Turno(text="Cinque minuti di timer.")
    ciclo._cerca_il_nome(t)
    verifica("ciclo: nella finestra senza il nome → senza_nome", sc.senza_nome is True)
    t = Turno(text="Cinque minuti di timer.", dal_nome=True)
    ciclo._cerca_il_nome(t)
    verifica("ciclo: dopo il nome da solo vale col nome", sc.senza_nome is False)
    t = Turno(text="Calliope, cinque minuti di timer.")
    ciclo._cerca_il_nome(t)
    verifica("ciclo: col nome davanti → non senza_nome", sc.senza_nome is False)
    sc.senza_nome = True
    ciclo.rec = {}
    ciclo._chi_parla(Turno(text="x"))
    verifica("ciclo: chi parla azzera il segno a ogni frase", sc.senza_nome is False
             and sc.compagnia_sconosciute is False)
    # In compagnia con le voci tutte riconosciute: niente voci sconosciute
    riconosci(ciclo, sc, frase(carlo=0.72, luca=0.2), 2.0)
    riconosci(ciclo, sc, frase(luca=0.70, carlo=0.2), 2.0)
    verifica("ciclo: famiglia tutta riconosciuta → compagnia senza voci sconosciute",
             sc.compagnia and sc.compagnia_sconosciute is False)
    riconosci(ciclo, sc, frase(carlo=0.10, amico=0.6), 2.0)
    riconosci(ciclo, sc, frase(carlo=0.72, luca=0.2), 2.0)
    verifica("ciclo: con l'amico → compagnia con voci sconosciute",
             sc.compagnia and sc.compagnia_sconosciute is True)


# ─────────────────────────── (b) la conversazione anonima ───────────────────────────

class Backend:
    def __init__(self, risposte):
        self.risposte = list(risposte)
        self.visti = []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        yield ("text", self.risposte.pop(0) if self.risposte else "Va bene.")


class Prof:
    def __init__(self, pid, name):
        self.id, self.name = pid, name


class Voci:
    def get(self, n):
        return {"Carlo": Prof("carlo-id", "Carlo"), "Luca": Prof("luca-id", "Luca")}.get(n)


class Chi:
    current_speaker, current_level, identified_by = "Carlo", "familiare", "conversazione"
    compagnia, compagnia_sconosciute = True, False


def brain_anonimo(chiave="ospite:telefono"):
    from calliope.tools.builtin import build_registry
    cfg = Config()
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = cfg, build_registry(), []
    b.conv = Conversazione(chiave)
    chi = Chi()
    b.tool_ctx = type("T", (), {"speaker_ctx": chi, "speakers": Voci()})()
    b.backend = Backend([])
    return b, chi


def _di(b, testo, livello="familiare"):
    return "".join(b.stream_reply(testo, livello))


def prova_anonima():
    # Il caso del 12/10: frasi incerte di Carlo e Luca nella conversazione anonima del telefono
    b, chi = brain_anonimo()
    _di(b, "Hai preso il caricabatterie?")
    chi.current_speaker = "Luca"
    _di(b, "Sì, è nello zaino.")
    verifica("in compagnia, Carlo poi Luca: la conversazione anonima continua",
             len([m for m in b.history if m["role"] == "user"]) == 2
             and "compagnia_anonima_continua" in b.last_rules
             and "conversazione_altra_persona" not in b.last_rules,
             f"{[m['role'] for m in b.history]} {b.last_rules}")
    visti = b.backend.visti[-1]
    dati = " ".join(m.get("content") or "" for m in visti if m.get("role") == "system")
    verifica("…e nei dati del turno chi ha detto le frasi di prima",
             "Conversazione di gruppo" in dati and "dalla più vecchia: Carlo" in dati, dati[-300:])
    verifica("…le etichette fuori dal testo delle frasi",
             [m.get("_chi") for m in b.history if m["role"] == "user"] == ["Carlo", "Luca"]
             and all(not (m.get("content") or "").startswith(("Carlo", "Luca"))
                     for m in b.history if m["role"] == "user"))
    # Una frase breve in compagnia vale ospite (None): con le voci tutte riconosciute continua
    chi.current_speaker, chi.current_level = None, "ospite"
    _di(b, "Vediamo.", "ospite")
    verifica("in compagnia senza voci sconosciute: la frase «ospite» (breve) continua",
             len([m for m in b.history if m["role"] == "user"]) == 3,
             f"{b.last_rules}")
    # Con una voce sconosciuta: da una persona a «ospite» si chiude, come il 03/10
    b, chi = brain_anonimo()
    chi.compagnia_sconosciute = True
    _di(b, "Qual è la password del wifi?")
    chi.current_speaker, chi.current_level = None, "ospite"
    _di(b, "Scusa, me la ripeti?", "ospite")
    verifica("contrario: voce sconosciuta di mezzo → si chiude come prima",
             len([m for m in b.history if m["role"] == "user"]) == 1
             and "conversazione_altra_persona" in b.last_rules, f"{b.last_rules}")
    # …ma tra due persone registrate continua anche con una voce sconosciuta nella stanza
    b, chi = brain_anonimo()
    chi.compagnia_sconosciute = True
    _di(b, "Hai preso il caricabatterie?")
    chi.current_speaker = "Luca"
    _di(b, "Sì.")
    verifica("con una voce sconosciuta nella stanza, tra due persone registrate continua",
             "compagnia_anonima_continua" in b.last_rules)
    # Una persona sola: come oggi
    b, chi = brain_anonimo()
    chi.compagnia = False
    _di(b, "Hai preso il caricabatterie?")
    chi.current_speaker = "Luca"
    _di(b, "Sì, è nello zaino.")
    verifica("contrario: senza compagnia si chiude come oggi",
             "conversazione_altra_persona" in b.last_rules
             and len([m for m in b.history if m["role"] == "user"]) == 1)
    # La conversazione di una persona non è condivisa (corsie: una per persona)
    b, chi = brain_anonimo("persona:carlo-id")
    _di(b, "Hai preso il caricabatterie?")
    chi.current_speaker = "Luca"
    _di(b, "Sì.")
    verifica("contrario: la conversazione di una persona si chiude come oggi",
             "conversazione_altra_persona" in b.last_rules)
    # Interruttore spento
    b, chi = brain_anonimo()
    b.cfg.compagnia_anonima_condivisa = False
    _di(b, "Hai preso il caricabatterie?")
    chi.current_speaker = "Luca"
    _di(b, "Sì.")
    verifica("interruttore spento (compagnia_anonima_condivisa: false) → si chiude",
             "conversazione_altra_persona" in b.last_rules)
    # La proposta di Carlo non la conferma Luca nella conversazione condivisa
    b, chi = brain_anonimo()
    _di(b, "Metti un timer.")
    b.set_pending({"tool": "timer_imposta", "argomenti": {"durata": "5 minuti"},
                   "domanda": "Lo metto?"})
    chi.current_speaker = "Luca"
    _di(b, "Sì.")
    verifica("conversazione condivisa: il «sì» di Luca non vale per la proposta di Carlo",
             getattr(b, "turn_pending_tool", None) is None, str(b.last_rules))
    # Dopo la chiusura per tempo la conversazione nuova non è più condivisa
    b.end_conversation("conversazione_scaduta")
    verifica("conversazione nuova: non condivisa", b.conv.condivisa is False)


def prova_anonima_attivo():
    """Con `eventi: attivo` (15/10, issue #12) la storia si rifà dalla proiezione a ogni risposta:
    chi ha detto cosa deve arrivare dall'evento della frase (`detto_persona.chi`)."""
    from calliope.eventi import ombra as ombra_mod
    from calliope.eventi.tipi import senza_parole
    from prova_eventi_attivo import GiroAttivo

    def conversazione():
        b, chi = brain_anonimo()
        g = GiroAttivo(b)
        g.turno("Hai preso il caricabatterie?", "familiare")
        chi.current_speaker = "Luca"
        g.turno("Sì, è nello zaino.", "familiare")
        chi.current_speaker = "Carlo"
        g.turno("Allora possiamo partire.", "familiare")
        dati = " ".join(m.get("content") or "" for m in b.backend.visti[-1]
                        if m.get("role") == "system")
        return b, g, dati
    b, g, dati = conversazione()
    vivo = b.conv.vivo_da
    verifica("attivo: la storia è la proiezione degli eventi, con chi ha detto ogni frase",
             b.proiettore is g.ombra and vivo >= 4
             and all("_seq" in m for m in b.history[:vivo])
             and [m.get("_chi") for m in b.history if m["role"] == "user"]
             == ["Carlo", "Luca", "Carlo"], str([(m["role"], m.get("_chi")) for m in b.history]))
    verifica("attivo: nei dati del turno in compagnia i nomi (dalla più vecchia: Carlo, Luca)",
             "Conversazione di gruppo" in dati and "dalla più vecchia: Carlo, Luca" in dati,
             dati[-300:])
    reg = g.registri.della_corsia(b.conv.chiave)
    dette = [e for e in reg.eventi() if e.tipo == "detto_persona"]
    verifica("attivo: il nome nell'evento della frase, fuori dal testo",
             [e.dati.get("chi") for e in dette] == ["Carlo", "Luca", "Carlo"]
             and all(not e.dati["testo"].startswith(("Carlo", "Luca")) for e in dette))
    verifica("…in un turno da non conservare il nome resta in memoria con le parole",
             senza_parole("detto_persona", {"testo": "Sì.", "chi": "Luca"})["_non_su_disco"]
             == ["testo", "chi"])
    # Contrario: senza il nome nell'evento (com'era fino al 14/10) solo «di gruppo»
    vecchio = ombra_mod.Ombra._segni_persona
    ombra_mod.Ombra._segni_persona = lambda self, conv: {}
    try:
        _, _, dati2 = conversazione()
    finally:
        ombra_mod.Ombra._segni_persona = vecchio
    verifica("contrario: senza il nome nell'evento i dati del turno non dicono chi",
             "Conversazione di gruppo" in dati2 and "dalla più vecchia" not in dati2, dati2[-300:])


# ─────────────────────────── (c) il rilevatore e le chiacchiere ───────────────────────────

class GuardianoFinto:
    """Domanda: pericolo (il rilevatore); frasi: sicure."""
    timeout_s = 1.0

    def __init__(self, domanda=guardia.PERICOLO):
        self.cfg = Config()
        self.domanda = domanda

    def condivide_voce(self):
        return False

    def in_parallelo(self, domanda, frase, categorie=None):
        import concurrent.futures
        f = concurrent.futures.Future()
        if frase is None:
            f.set_result(guardia.Giudizio(self.domanda, ("autolesionismo",)
                                          if self.domanda == guardia.PERICOLO else (), 10.0))
        else:
            f.set_result(guardia.Giudizio(guardia.OK, (), 5.0))
        return f


def prova_pericolo():
    # filtra: senza `pericolo_vale` come prima
    es = guardia.Esito()
    detto = list(guardia.filtra(GuardianoFinto(), iter(["Ok."]), "frase", True, es))
    verifica("contrario: filtra senza pericolo_vale → la protezione", detto ==
             [guardia.PROTEZIONE] and es.fermata == guardia.PERICOLO)
    es = guardia.Esito()
    detto = list(guardia.filtra(GuardianoFinto(), iter(["Ok."]), "frase", True, es,
                                pericolo_vale=lambda g: False))
    verifica("filtra: pericolo che non vale → si risponde, ogni frase giudicata",
             detto == ["Ok."] and es.fermata is None and es.pericolo_ignorato is True
             and len(es.frasi) == 1)
    es = guardia.Esito()
    detto = list(guardia.filtra(GuardianoFinto(), iter(["Ok."]), "frase", True, es,
                                pericolo_vale=lambda g: 1 / 0))
    verifica("filtra: pericolo_vale guasto → la protezione", detto == [guardia.PROTEZIONE])
    # Il ciclo: compagnia (famiglia), frase senza il nome, giudizio in ombra
    reg, sc, ciclo, regole = ciclo_finto()
    cfg = reg.cfg
    giudizio = ['{"per_calliope": false}']
    ciclo._giudice = rivolta_mod.Giudice(cfg, chiama=lambda m, to: giudizio[0])
    riconosci(ciclo, sc, frase(carlo=0.72, luca=0.2), 2.0)
    riconosci(ciclo, sc, frase(luca=0.70, carlo=0.2), 2.0)

    def turno(testo="Ma no, mi ammazzo dal ridere."):
        t = Turno(text=testo, senza_nome=True)
        t.rivolta = ciclo._avvia_rivolta(t)
        return t

    t = turno()
    verifica("ombra: il giudizio parte (precondizione)", t.rivolta is not None
             and t.rivolta["modo"] == "ombra")
    verifica("ombra, non rivolta: il pericolo non vale (regola pericolo_non_rivolta)",
             ciclo._pericolo_vale(t) is False and "pericolo_non_rivolta" in regole)
    regole.clear()
    giudizio[0] = '{"per_calliope": true}'
    verifica("contrario: rivolta → il pericolo vale", ciclo._pericolo_vale(turno()) is True
             and "pericolo_non_rivolta" not in regole)
    giudizio[0] = "non è JSON"
    verifica("contrario: giudizio guasto → vale «rivolta», il pericolo vale",
             ciclo._pericolo_vale(turno()) is True)
    giudizio[0] = '{"per_calliope": false}'
    cfg.compagnia_pericolo_solo_rivolte = False
    verifica("interruttore spento (compagnia_pericolo_solo_rivolte: false) → vale",
             ciclo._pericolo_vale(turno()) is True)
    cfg.compagnia_pericolo_solo_rivolte = True
    t = Turno(text="Ma no, mi ammazzo dal ridere.", senza_nome=False)
    t.rivolta = ciclo._avvia_rivolta(t)
    verifica("contrario: col nome nessun giudizio, il pericolo vale",
             t.rivolta is None and ciclo._pericolo_vale(t) is True)
    reg2, sc2, ciclo2, _ = ciclo_finto()
    ciclo2._giudice = rivolta_mod.Giudice(reg2.cfg, chiama=lambda m, to: '{"per_calliope": false}')
    t = Turno(text="Ma no, mi ammazzo dal ridere.", senza_nome=True)
    t.rivolta = ciclo2._avvia_rivolta(t)
    verifica("contrario: una persona sola → nessun giudizio, il pericolo vale come oggi",
             t.rivolta is None and ciclo2._pericolo_vale(t) is True)
    # Il registro dei turni: il segnale non valso, con le categorie e senza parole del minore
    t = turno()
    t.usa_guardia, t.minore_turno = True, True
    t.esito_u = __import__("calliope.riferire", fromlist=["Esito"]).Esito()
    t.esito_g = guardia.Esito()
    list(guardia.filtra(GuardianoFinto(), iter(["Ok."]), "frase", True, t.esito_g,
                        pericolo_vale=lambda g: ciclo._pericolo_vale(t)))
    ciclo.rec = {"testo": "Ma no, mi ammazzo dal ridere.", "richiesta": "x"}
    ciclo.brain = type("B", (), {"schede_attesa_ms": None})()
    ciclo._registra_controlli(t)
    g = ciclo.rec.get("guardiano") or {}
    verifica("registro: pericolo_non_rivolta con le categorie, niente parole del minore",
             g.get("pericolo_non_rivolta") == ["autolesionismo"] and ciclo.rec["testo"] is None
             and "fermata" not in g, json.dumps(ciclo.rec, ensure_ascii=False))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    for nome, f in (("(a) azioni col nome", prova_azioni),
                    ("(a) il segno dal ciclo", prova_senza_nome_dal_ciclo),
                    ("(b) la conversazione anonima condivisa", prova_anonima),
                    ("(b) …con eventi: attivo", prova_anonima_attivo),
                    ("(c) il rilevatore e le chiacchiere", prova_pericolo)):
        print(f"── {nome} ──", flush=True)
        f()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    sys.exit(1 if errori else 0)
