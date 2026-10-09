"""
Prova a secco delle voci di famiglia (07/10/2026, ciclo._confronta_voce, conferme.py): un
adulto che amministra e un minore con impronte vicine sul canale del telefono in
auto. Impronte sintetiche (vettori costruiti con i punteggi voluti), nomi di fantasia: Carlo
amministra, Luca è il minore.

I quattro casi veri (punteggi del registro dei turni, 06–07/10):
  1. una frase di 3,2 s di Carlo: migliore Carlo 0,489, il minore a meno di 0,05 → valeva Luca;
  2. la frase di sfida di Carlo: migliore Carlo 0,547 → Luca, sfida chiusa («solo chi ha
     fatto la richiesta»);
  3. «Sì, procedi.» (0,82 s): migliore Carlo 0,534 → Luca, l'azione proposta persa;
  4. «Sì, dovremmo…» (1,46 s): migliore Luca 0,483, modo «voce» → Luca dalla voce.
E il verso pericoloso: una frase di Luca presa per Carlo con i permessi di chi amministra.
"""

import datetime
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope import conferme as C
from calliope.brain import Brain
from calliope.ciclo import Ciclo, Servizi, Turno
from calliope.config import Config
from calliope.speaker_id import SpeakerContext, SpeakerRegistry, UserProfile, normalize
from calliope.tools.registry import REFUSAL, ToolRegistry
from calliope.tools.spec import ToolContext, ToolSpec

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


# ─────────────────────────── impronte sintetiche ───────────────────────────

DIM = 192
_rng = np.random.default_rng(7)


def _ortho(*vs):
    """Un vettore unitario ortogonale a `vs`."""
    x = _rng.standard_normal(DIM)
    q, _ = np.linalg.qr(np.stack(vs, axis=1))       # base ortonormale di `vs`
    return normalize(x - q @ (q.T @ x))


CARLO = normalize(_rng.standard_normal(DIM))
# Il coseno tra le due impronte vere era 0,17: qui lo stesso
LUCA = normalize(0.17 * CARLO + np.sqrt(1 - 0.17 ** 2) * _ortho(CARLO))
ALTRO = _ortho(CARLO, LUCA)                  # un'altra adulta di casa (Bianca), lontana


def frase_con(s_carlo: float, s_luca: float) -> np.ndarray:
    """Un'impronta di frase con i punteggi voluti contro Carlo e Luca (e ~0 contro Bianca)."""
    r = float(CARLO @ LUCA)
    b = (s_luca - r * s_carlo) / (1 - r * r)
    a = s_carlo - b * r
    v = a * CARLO + b * LUCA
    resto = 1 - float(v @ v)
    assert resto > 0, (s_carlo, s_luca)
    w = v + np.sqrt(resto) * _ortho(CARLO, LUCA, ALTRO)
    return w.astype(np.float32)


class Reg(SpeakerRegistry):
    """Il registro vero (classifica, best_match) senza il modello ONNX."""

    def __init__(self):
        self.cfg = Config()
        nascita = (datetime.date.today() - datetime.timedelta(days=14 * 366)).isoformat()
        self.users = {
            "Carlo": UserProfile(name="Carlo", voiceprint=CARLO, admin=True, id="carlo-id"),
            "Luca": UserProfile(name="Luca", voiceprint=LUCA, nascita=nascita,
                                tutori=["carlo-id"], id="luca-id"),
            "Bianca": UserProfile(name="Bianca", voiceprint=ALTRO, id="bianca-id"),
        }
        self._salvato, self._da_salvare = time.monotonic(), False   # adapt (impronta)

    def save(self):
        pass


class Corsia:
    conv = None


def ciclo_finto():
    reg = Reg()
    sc = SpeakerContext(reg)
    ciclo = Ciclo(Servizi(reg.cfg, registry=reg), Corsia(), None, None, sc, None, None, None,
                  None, None)
    ciclo.rec = {}
    regole = []
    ciclo.rule = regole.append
    return reg, sc, ciclo, regole


def chi(ciclo, sc, emb, voiced_s=2.5, in_session=True, prev="Carlo"):
    """La decisione del ciclo per una frase: (nome, come, livello)."""
    sc.current_speaker = prev
    sc.incerta = sc.minore_vicino = None
    t = Turno(voiced_s=voiced_s, in_session=in_session)
    name, how, _, _ = ciclo._confronta_voce(t, emb)
    sc.current_speaker = name
    return name, how, sc.current_level, t


# ─────────────────────────── i quattro casi e i contrari ───────────────────────────

def prova_casi():
    reg, sc, ciclo, regole = ciclo_finto()
    cfg = reg.cfg
    verifica("predefiniti: margine 0,08, chi amministra 0,12",
             (cfg.speaker_id_margine, cfg.minori_margine_amministra) == (0.08, 0.12))
    verifica("impronte sintetiche come le vere: coseno 0,17", abs(float(CARLO @ LUCA) - 0.17)
             < 1e-6)
    e = frase_con(0.489, 0.46)
    verifica("frase sintetica con i punteggi voluti", abs(float(e @ CARLO) - 0.489) < 1e-4
             and abs(float(e @ LUCA) - 0.46) < 1e-4 and abs(float(e @ ALTRO)) < 1e-4)

    # Caso 1: incerta, vale il minore (prudente), ma si sa tra chi
    n, how, lv, t = chi(ciclo, sc, frase_con(0.489, 0.46), 3.19)
    verifica("caso 1: Carlo 0,489 e Luca 0,46 → Luca, incerta tra i due", (n, how) ==
             ("Luca", "conversazione") and sc.incerta == ("Carlo", "Luca")
             and "voce_margine" in regole and "minore_piu_protetto" in regole, f"{n} {how}")
    verifica("caso 1: il secondo profilo e il margine nel turno", t.voce_secondo[0] == "Luca"
             and abs(t.voce_secondo[1] - 0.46) < 1e-3)
    # Caso 2 e 3
    n, how, lv, _ = chi(ciclo, sc, frase_con(0.547, 0.51), 2.84)
    verifica("caso 2: Carlo 0,547 e Luca 0,51 → Luca, incerta", n == "Luca"
             and sc.incerta == ("Carlo", "Luca"))
    n, how, lv, _ = chi(ciclo, sc, frase_con(0.534, 0.50), 0.82)
    verifica("caso 3: «Sì, procedi.» breve con Luca sopra soglia → Luca, incerta", n == "Luca"
             and sc.incerta == ("Carlo", "Luca"), f"{n} {how} {sc.incerta}")
    # Caso 4: il minore primo sopra soglia, ma a meno del margine da Carlo → non «voce»
    regole.clear()
    n, how, lv, _ = chi(ciclo, sc, frase_con(0.45, 0.483), 1.46)
    verifica("caso 4: Luca 0,483 e Carlo 0,45 → non più «voce», incerta (vale Luca)",
             n == "Luca" and how == "conversazione" and sc.incerta == ("Carlo", "Luca")
             and "voce_margine" in regole, f"{n} {how}")
    # Contrari: voci nette
    n, how, lv, _ = chi(ciclo, sc, frase_con(0.20, 0.70), 2.0, prev="Luca")
    verifica("contrario: Luca netto (0,70 contro 0,20) → Luca dalla voce", (n, how) ==
             ("Luca", "voce") and sc.incerta is None)
    n, how, lv, _ = chi(ciclo, sc, frase_con(0.65, 0.30), 2.0)
    verifica("contrario: Carlo netto (0,65 contro 0,30) → amministra", (n, how, lv) ==
             ("Carlo", "voce", "amministra") and sc.minore_vicino is None)
    n, how, lv, _ = chi(ciclo, sc, frase_con(0.60, 0.15), 2.0, in_session=False, prev=None)
    verifica("contrario: fuori conversazione, Carlo netto → amministra", lv == "amministra")


def prova_verso_pericoloso():
    reg, sc, ciclo, regole = ciclo_finto()
    # Una frase di Luca (al telefono) che somiglia a Carlo più che a lui
    n, how, lv, _ = chi(ciclo, sc, frase_con(0.55, 0.50), 2.0, prev="Luca")
    verifica("Luca preso vicino a Carlo (0,55 contro 0,50) → mai chi amministra: Luca",
             n == "Luca" and lv != "amministra", f"{n} {how} {lv}")
    regole.clear()
    n, how, lv, _ = chi(ciclo, sc, frase_con(0.62, 0.52), 2.0, prev="Luca")
    verifica("Carlo a 0,10 dal minore → Carlo, ma solo familiare (amministra_minore_vicino)",
             (n, how, lv) == ("Carlo", "conversazione", "familiare")
             and sc.minore_vicino == "Luca" and "amministra_minore_vicino" in regole,
             f"{n} {how} {lv}")
    n, how, lv, _ = chi(ciclo, sc, frase_con(0.66, 0.52), 2.0)
    verifica("Carlo a 0,14 dal minore → amministra (sopra minori_margine_amministra)",
             lv == "amministra")
    # Due adulti vicini: la voce non decide, nessun minore in mezzo
    reg.users["Bianca"].voiceprint = normalize(0.6 * CARLO + 0.8 * ALTRO)
    e = normalize(CARLO + reg.users["Bianca"].voiceprint)
    sb, sca = float(e @ reg.users["Bianca"].voiceprint), float(e @ CARLO)
    n, how, lv, _ = chi(ciclo, sc, e, 2.0, in_session=False, prev=None)
    verifica("due adulti a meno del margine, fuori conversazione → ospite", n is None
             and lv == "ospite", f"{sca:.2f} {sb:.2f} {n}")
    n, how, lv, _ = chi(ciclo, sc, e, 2.0, prev="Carlo")
    verifica("due adulti vicini, nella conversazione di Carlo → Carlo come familiare",
             (n, how, lv) == ("Carlo", "conversazione", "familiare"), f"{n} {how} {lv}")


def prova_conferma_breve():
    reg = Reg()
    sc = SpeakerContext(reg)
    sc.aggiorna_conversazione("Carlo", "voce", False, 0.7)
    sc.aggiorna_conversazione("Carlo", "breve", True, 0.435, True)
    verifica("«Sì, riproviamoci.»: Luca 0,47 più vicino di Carlo 0,435 → non conferma",
             not sc.conferma_breve)
    sc.aggiorna_conversazione("Carlo", "breve", True, 0.50, False)
    verifica("contrario: Carlo 0,50 e nessuno più vicino → conferma", sc.conferma_breve)
    # Nel ciclo: il punteggio di chi vale contro il migliore
    reg, sc, ciclo, regole = ciclo_finto()
    sc.aggiorna_conversazione("Carlo", "voce", False, 0.7)

    class Job:
        def __init__(self, e):
            self.e = e

        def result(self):
            return self.e

    class Voce:
        _current_voice_path = None

    ciclo.speaker = Voce()
    for (sca, slu), atteso in (((0.435, 0.47), False), ((0.50, 0.30), True)):
        sc.current_speaker = "Carlo"
        t = Turno(voiced_s=0.6, in_session=True, emb_job=Job(frase_con(sca, slu)),
                  prev_how="voce")
        ciclo._riconosci_voce(t)
        v = ciclo.rec["voce"]
        verifica(f"ciclo: «sì» breve Carlo {sca} Luca {slu} → conferma {atteso}",
                 sc.conferma_breve is atteso and v["modo"] == "breve"
                 and "secondo" in v and "margine" in v, json.dumps(v))


# ─────────────────────────── continuità (08/10) ───────────────────────────
# Caso vero della DGX (08/10 17:26, nomi di fantasia): 13 minuti dopo l'ultima frase di chi
# amministra, «Calliope.» (0,5 s di voce, 0,44, il secondo a 0,11) e la frase dopo (0,6 s, 0,40)
# sotto la soglia 0,48 → ospite, e la ricerca nelle sue conversazioni negata.

class Job:
    def __init__(self, e):
        self.e = e

    def result(self):
        return self.e


class VoceFinta:
    _current_voice_path = None


def frase_bianca(s_bianca: float, s_carlo: float) -> np.ndarray:
    """Un'impronta con i punteggi voluti contro Bianca e Carlo (e ~0 contro Luca: Bianca e
    Carlo sono ortogonali a Luca solo in parte, qui basta che Luca resti lontano)."""
    v = s_bianca * ALTRO + s_carlo * CARLO
    resto = 1 - float(v @ v)
    w = v + np.sqrt(resto) * _ortho(CARLO, LUCA, ALTRO)
    return w.astype(np.float32)


def riconosci(ciclo, sc, emb, voiced_s, in_session=False, prev=None):
    sc.current_speaker = prev
    t = Turno(voiced_s=voiced_s, in_session=in_session, emb_job=Job(emb), prev_how=None)
    ciclo.rec = {}
    ciclo._riconosci_voce(t)
    return sc.current_speaker, sc.identified_by, sc.current_level, ciclo.rec["voce"], t


def prova_continuita():
    reg, sc, ciclo, regole = ciclo_finto()
    ciclo.speaker = VoceFinta()
    cfg = reg.cfg
    verifica("predefiniti: 900 s, 0,36, margine 0,20", (cfg.speaker_continuita_s,
             cfg.speaker_continuita_soglia, cfg.speaker_continuita_margine) == (900.0, 0.36, 0.20))
    # Carlo riconosciuto dalla voce su questo satellite
    n, how, lv, v, _ = riconosci(ciclo, sc, frase_con(0.72, 0.20), 2.1)
    verifica("Carlo dalla voce: ricordato per la continuità", n == "Carlo"
             and ciclo._voce_recente[0] == "Carlo")
    # Il caso vero: fuori dalla finestra d'ascolto, 0,5 s, 0,44 con Luca lontano
    regole.clear()
    n, how, lv, v, t = riconosci(ciclo, sc, frase_con(0.44, 0.11), 0.5)
    verifica("caso vero: «Calliope.» 0,5 s a 0,44 → Carlo per continuità, solo familiare",
             (n, how, lv) == ("Carlo", "conversazione", "familiare") and t.continuita
             and v["modo"] == "continuita" and "voce_continuita" in regole, json.dumps(v))
    verifica("per continuità: niente conferma breve né voce sicura",
             not sc.conferma_breve and sc.voce_sicura is None)
    n, how, lv, v, t = riconosci(ciclo, sc, frase_con(0.40, 0.08), 0.63, in_session=True,
                                 prev=None)
    verifica("caso vero: la frase dopo, 0,6 s a 0,40 dopo un ospite → Carlo per continuità",
             n == "Carlo" and t.continuita, json.dumps(v))
    # Contrari
    regole.clear()
    n, how, lv, v, t = riconosci(ciclo, sc, frase_con(0.34, 0.05), 0.5)
    verifica("contrario: sotto 0,36 → ospite", n is None and not t.continuita
             and "voce_continuita" not in regole)
    n, how, lv, v, t = riconosci(ciclo, sc, frase_con(0.44, 0.30), 0.5)
    verifica("contrario: il minore a 0,14 dal migliore (margine sotto 0,20) → non per "
             "continuità", not t.continuita and n != "Carlo", f"{n} {how}")
    n, how, lv, v, t = riconosci(ciclo, sc, frase_con(0.44, 0.11), 1.4)
    verifica("contrario: frase lunga sotto soglia → ospite come prima (solo sotto 1 s)",
             n is None and not t.continuita)
    # Un'altra persona vicina: il migliore è Bianca, non chi è stato riconosciuto qui
    n, how, lv, v, t = riconosci(ciclo, sc, frase_bianca(0.44, 0.10), 0.5)
    verifica("contrario: il migliore è un'altra persona → ospite", n is None
             and not t.continuita, f"{n} {json.dumps(v)}")
    # Finestra scaduta
    ciclo._voce_recente = ("Carlo", time.monotonic() - 901)
    n, how, lv, v, t = riconosci(ciclo, sc, frase_con(0.44, 0.11), 0.5)
    verifica("contrario: finestra scaduta (15 minuti) → ospite", n is None and not t.continuita)
    # Satellite diverso: un'altra corsia non ha visto Carlo
    reg2, sc2, ciclo2, regole2 = ciclo_finto()
    ciclo2.speaker = VoceFinta()
    n, how, lv, v, t = riconosci(ciclo2, sc2, frase_con(0.44, 0.11), 0.5)
    verifica("contrario: satellite diverso (nessuno riconosciuto qui) → ospite",
             n is None and not t.continuita)
    # Spenta
    ciclo._voce_recente = ("Carlo", time.monotonic())
    cfg.speaker_continuita_s = 0
    n, how, lv, v, t = riconosci(ciclo, sc, frase_con(0.44, 0.11), 0.5)
    verifica("contrario: speaker_continuita_s 0 → spenta", n is None)
    cfg.speaker_continuita_s = 900.0
    # Un ospite che parla a lungo qui toglie la continuità
    riconosci(ciclo, sc, frase_bianca(0.10, 0.10), 2.0)
    n, how, lv, v, t = riconosci(ciclo, sc, frase_con(0.44, 0.11), 0.5)
    verifica("contrario: dopo una frase lunga di un'altra voce → ospite",
             ciclo._voce_recente is None and n is None)
    # Il minore: riconosciuto dalla voce, poi una frase cortissima sua → vale lui. La voce
    # dell'ospite qui sopra ha acceso la compagnia (09/10), che spegne la continuità: qui si
    # prova la continuità da sola (la compagnia è in prova_compagnia.py)
    ciclo.compagnia.dimentica()
    riconosci(ciclo, sc, frase_con(0.20, 0.70), 2.0)
    n, how, lv, v, t = riconosci(ciclo, sc, frase_con(0.08, 0.42), 0.5)
    verifica("minore riconosciuto qui, frase cortissima sua → il minore per continuità",
             n == "Luca" and t.continuita and lv == "familiare", f"{n} {how}")
    # Carlo ricordato, ma la frase è più vicina al minore (verso pericoloso) → mai Carlo
    riconosci(ciclo, sc, frase_con(0.72, 0.20), 2.0)
    n, how, lv, v, t = riconosci(ciclo, sc, frase_con(0.40, 0.43), 0.5)
    verifica("minore più vicino di Carlo → mai Carlo per continuità", n != "Carlo"
             and not t.continuita, f"{n} {how}")
    # Chi amministra con il minore vicino non resta ricordato (la sua frase non bastava)
    ciclo._voce_recente = None
    riconosci(ciclo, sc, frase_con(0.62, 0.52), 2.0)
    verifica("Carlo con il minore vicino: non ricordato per la continuità",
             sc.minore_vicino == "Luca" and ciclo._voce_recente is None,
             str(ciclo._voce_recente))


# ─────────────────────────── la frase che chiede chi parla ───────────────────────────

class Persone:
    def __init__(self):
        self.reg = Reg()
        self.cfg = self.reg.cfg
        self.users = self.reg.users

    def get(self, n):
        return self.users.get(n)


def prova_frasi():
    p = Persone()
    sc = SpeakerContext(p)
    ctx = ToolContext(cfg=p.cfg, speakers=p, speaker_ctx=sc, speaker=None)
    reg = ToolRegistry()
    fatti = []
    reg.register(ToolSpec(name="azione_admin", description="", parameters={},
                          func=lambda ctx, **a: fatti.append(a) or {"ok": True,
                                                                    "conferma": "Fatto."},
                          risk="azione", levels=frozenset({"amministra"})))
    # Luca incerto con Carlo chiede un'azione di chi amministra: la sfida per Carlo
    sc.current_speaker, sc.identified_by, sc.from_session = "Luca", "conversazione", True
    sc.incerta = ("Carlo", "Luca")
    out = json.loads(reg.call("azione_admin", {"x": 1}, ctx, sc.current_level))
    verifica("incerta: azione di chi amministra → chiede chi parla, sfida per Carlo",
             not fatti and "Non sono sicura di chi parla: Carlo o Luca" in out["risposta_finale"]
             and sc.sfida is not None and sc.sfida.persona == "carlo-id"
             and "voce_incerta_chiede" in ctx.regole, out["risposta_finale"])
    # Contrario: Luca riconosciuto con certezza → il rifiuto di sempre, nessuna domanda
    sc.sfida, sc.incerta, ctx.regole = None, None, []
    sc.identified_by, sc.from_session = "voce", False
    out = json.loads(reg.call("azione_admin", {"x": 1}, ctx, sc.current_level))
    verifica("contrario: Luca sicuro → il rifiuto di sempre", not fatti
             and out["risposta_finale"] == REFUSAL["familiare"] and sc.sfida is None)
    # Carlo con il minore vicino: la sfida, e la frase dice perché
    sc.current_speaker, sc.identified_by, sc.from_session = "Carlo", "conversazione", True
    sc.minore_vicino = "Luca"
    out = json.loads(reg.call("azione_admin", {"x": 1}, ctx, sc.current_level))
    verifica("Carlo con Luca vicino → sfida con la domanda", not fatti
             and "Carlo o Luca" in out["risposta_finale"] and sc.sfida.persona == "carlo-id",
             out["risposta_finale"])
    sc.minore_vicino = None

    # La risposta alla sfida con la voce incerta (caso 2): non «solo chi ha fatto la
    # richiesta», ma parole nuove e la domanda; la seconda volta non procede
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = p.cfg, reg, []
    b.tool_ctx = ctx

    class Backend:
        def stream(self, messages, tools):
            yield ("text", "Ok.")
    b.backend = Backend()
    s = C.nuova_sfida(p.cfg, "carlo-id", "azione_admin", {"x": 1})
    s.parole, s.numero = ("girasole", "treno", "limone"), 42
    sc.sfida = s
    sc.current_speaker, sc.identified_by, sc.from_session = "Luca", "conversazione", True
    sc.incerta = ("Carlo", "Luca")
    detto = "".join(b.stream_reply("Girasole, treno, limone, quarantadue.", "familiare"))
    verifica("caso 2: sfida con la voce incerta → parole nuove e la domanda", not fatti
             and detto.startswith("Non sono sicura di chi parla: Carlo o Luca")
             and sc.sfida is not None and sc.sfida.parole != s.parole, detto)
    s2 = sc.sfida
    detto = "".join(b.stream_reply(s2.testo + ".", "familiare"))
    verifica("caso 2: di nuovo incerta → non procede", not fatti
             and detto == C.SFIDA_VOCE_FALLITA and sc.sfida is None, detto)
    # Poi Carlo, riconosciuto bene, la ripete: eseguita
    s3 = C.nuova_sfida(p.cfg, "carlo-id", "azione_admin", {"x": 1})
    sc.sfida = s3
    sc.current_speaker, sc.identified_by, sc.from_session = "Carlo", "voce", False
    sc.incerta = None
    b.conv_owner = "carlo-id"                         # la stessa conversazione
    detto = "".join(b.stream_reply(s3.testo + ".", "amministra"))
    verifica("Carlo riconosciuto bene ripete la sfida → eseguita", fatti == [{"x": 1}], detto)
    # Contrario: una voce sicura di Luca ripete le parole → mai
    fatti.clear()
    sc.sfida = C.nuova_sfida(p.cfg, "carlo-id", "azione_admin", {"x": 1})
    sc.current_speaker, sc.identified_by, sc.from_session = "Luca", "voce", False
    b.conv_owner = "luca-id"
    detto = "".join(b.stream_reply(sc.sfida.testo + ".", "familiare"))
    verifica("contrario: Luca sicuro ripete le parole → «solo chi ha fatto la richiesta»",
             not fatti and detto == C.SFIDA_ALTRA_VOCE, detto)


def prova_azione_in_sospeso():
    """Caso 3: «Sì, procedi.» incerto con un'azione proposta a Carlo in sospeso."""
    reg, sc, ciclo, regole = ciclo_finto()

    class Conv:
        chiave = "persona:carlo-id"
        pending = {"chi": "carlo-id", "scade": time.monotonic() + 60, "tool": "x"}

    class Voce:
        detto = []

        def start_turn(self):
            pass

        def say(self, f):
            self.detto.append(f)

        def wait(self):
            pass

    ciclo.corsia.conv = Conv()
    ciclo.speaker = Voce()
    sc.incerta = ("Carlo", "Luca")
    t = Turno(in_session=True, text="Sì, procedi.")
    verifica("caso 3: «Sì, procedi.» incerto con l'azione di Carlo in sospeso → chiede",
             ciclo._chiedi_chi_parla(t) and ciclo.speaker.detto
             and ciclo.speaker.detto[-1].startswith("Non sono sicura di chi parla: Carlo o Luca")
             and "voce_incerta_chiede" in regole and Conv.pending is not None)
    # Contrari: niente in sospeso, voce sicura, scritto, conversazione di un altro
    Conv.pending = None
    verifica("contrario: nessuna azione in sospeso → niente domanda",
             not ciclo._chiedi_chi_parla(t))
    Conv.pending = {"chi": "carlo-id", "scade": time.monotonic() + 60}
    sc.incerta = None
    verifica("contrario: voce sicura → niente domanda", not ciclo._chiedi_chi_parla(t))
    sc.incerta = ("Carlo", "Luca")
    Conv.pending = {"chi": "carlo-id", "scade": time.monotonic() - 1}
    verifica("contrario: azione scaduta → niente domanda", not ciclo._chiedi_chi_parla(t))
    Conv.pending = {"chi": "carlo-id", "scade": time.monotonic() + 60}
    verifica("contrario: fuori dalla finestra d'ascolto → niente domanda",
             not ciclo._chiedi_chi_parla(Turno(in_session=False, text="Sì, procedi.")))


# ─────────────────────────── il proprietario del telefono (09/10) ───────────────────────────

class Collegato:
    def __init__(self, proprietario):
        self.satellite = {"id": 7, "nome": "telefono di Carlo", "proprietario": proprietario}


class Satelliti:
    def __init__(self, proprietario="carlo-id"):
        self.proprietario = proprietario

    def per_id(self, sid):
        return Collegato(self.proprietario) if sid == 7 else None


class CorsiaTelefono:
    conv = None
    satellite_id = 7
    chiave = "sat:7"


def ciclo_telefono(proprietario="carlo-id"):
    """Il ciclo della corsia del telefono di Carlo (satellite personale)."""
    reg = Reg()
    sc = SpeakerContext(reg)
    ciclo = Ciclo(Servizi(reg.cfg, registry=reg, satelliti=Satelliti(proprietario)),
                  CorsiaTelefono(), None, None, sc, None, None, None, None, None)
    ciclo.speaker = VoceFinta()
    regole = []
    ciclo.rule = regole.append
    ciclo.rec = {}
    return reg, sc, ciclo, regole


def prova_proprietario():
    """Caso vero della DGX del 09/10 alle 18:48 (telefono personale di Dario, qui Carlo): dopo
    frasi sue riconosciute dalla voce, «Sì, sì, grazie.» (0,79 s: Carlo 0,50, il minore 0,485) e
    «Io volevo che tu facessi la ricerca…» (3,0 s: 0,61 contro 0,54) valevano il minore, con una
    conversazione nuova e quella di prima persa. Regola `voce_proprietario`."""
    from calliope import minori
    from calliope.corsie import RegistroConversazioni
    reg, sc, ciclo, regole = ciclo_telefono()
    verifica("predefinito: speaker_proprietario_s 180", reg.cfg.speaker_proprietario_s == 180.0)
    n, *_ = riconosci(ciclo, sc, frase_con(0.70, 0.37), 6.0, in_session=True, prev="Carlo")
    verifica("Carlo dalla voce sul suo telefono", n == "Carlo" and ciclo._voce_recente[0] == "Carlo")
    regole.clear()
    n, how, lv, v, t = riconosci(ciclo, sc, frase_con(0.50, 0.485), 0.79, in_session=True,
                                 prev="Carlo")
    verifica("caso vero 1: frase breve incerta col minore → resta Carlo, al più familiare",
             (n, how, lv) == ("Carlo", "conversazione", "familiare") and t.proprietario
             and v["modo"] == "proprietario" and "voce_proprietario" in regole
             and "minore_piu_protetto" not in regole, f"{n} {how} {lv} {regole}")
    verifica("caso vero 1: si sa tra chi (le azioni chiedono chi parla), prudenza per Luca",
             sc.incerta == ("Carlo", "Luca") and sc.minore_incerto == "Luca"
             and C.incerta_con_admin(ToolContext(cfg=reg.cfg, speakers=reg, speaker_ctx=sc,
                                                 speaker=None)) == ("Carlo", "Luca"))
    ctx = ToolContext(cfg=reg.cfg, speakers=reg, speaker_ctx=sc, speaker=None)
    verifica("prudenza: i preset dei tool e dei contenuti guardano Luca",
             getattr(minori.profilo(ctx), "name", None) == "Luca")
    regole.clear()
    n, how, lv, v, t = riconosci(ciclo, sc, frase_con(0.606, 0.544), 3.03, in_session=True,
                                 prev="Carlo")
    verifica("caso vero 2: frase lunga incerta (margine 0,06) → resta Carlo",
             n == "Carlo" and t.proprietario and "voce_proprietario" in regole, f"{n} {regole}")
    # La conversazione: «continuita» continua quella di Carlo su questo satellite
    rc = RegistroConversazioni(reg.cfg, log=lambda *a: None)

    class Cors:
        chiave = "sat:7"
        conv = None
    cors = Cors()
    c1, come = rc.scegli(cors, "carlo-id", "voce", True)
    cors.conv = c1
    c2, come2 = rc.scegli(cors, "carlo-id", "continuita", True)
    verifica("la frase resta nella conversazione di Carlo (non una nuova anonima)",
             c2 is c1 and come2 == "continuita", come2)
    # Il minore riconosciuto con sicurezza prende il posto
    regole.clear()
    n, how, lv, v, t = riconosci(ciclo, sc, frase_con(0.25, 0.70), 2.5, in_session=True,
                                 prev="Carlo")
    verifica("contrario: Luca riconosciuto con sicurezza → Luca", n == "Luca" and how == "voce"
             and not t.proprietario and "voce_proprietario" not in regole, f"{n} {how}")
    # Contrari, ognuno su un ciclo nuovo con Carlo appena riconosciuto
    def dopo_carlo(**kw):
        r_, sc_, ci_, reg_ = ciclo_telefono(**kw)
        riconosci(ci_, sc_, frase_con(0.70, 0.37), 6.0, in_session=True, prev="Carlo")
        reg_.clear()
        return r_, sc_, ci_, reg_
    r_, sc_, ci_, reg_ = dopo_carlo()
    n, how, lv, v, t = riconosci(ci_, sc_, frase_con(0.47, 0.52), 1.5, in_session=True,
                                 prev="Carlo")
    verifica("contrario: il più simile è il minore → il minore (il più protetto)",
             n == "Luca" and not t.proprietario, f"{n}")
    r_, sc_, ci_, reg_ = dopo_carlo(proprietario=None)
    n, how, lv, v, t = riconosci(ci_, sc_, frase_con(0.50, 0.485), 0.79, in_session=True,
                                 prev="Carlo")
    verifica("contrario: satellite di stanza (nessun proprietario) → il minore",
             n == "Luca" and "minore_piu_protetto" in reg_, f"{n}")
    r_, sc_, ci_, reg_ = dopo_carlo(proprietario="bianca-id")
    n, how, lv, v, t = riconosci(ci_, sc_, frase_con(0.50, 0.485), 0.79, in_session=True,
                                 prev="Carlo")
    verifica("contrario: telefono di un'altra persona → il minore", n == "Luca", f"{n}")
    r_, sc_, ci_, reg_ = dopo_carlo()
    ci_._voce_recente = ("Carlo", time.monotonic() - 181)
    n, how, lv, v, t = riconosci(ci_, sc_, frase_con(0.50, 0.485), 0.79, in_session=True,
                                 prev="Carlo")
    verifica("contrario: finestra scaduta (oltre 180 s) → il minore", n == "Luca", f"{n}")
    r_, sc_, ci_, reg_ = dopo_carlo()
    r_.cfg.storia_inattiva_s = 100.0
    ci_._voce_recente = ("Carlo", time.monotonic() - 150)
    n, how, lv, v, t = riconosci(ci_, sc_, frase_con(0.50, 0.485), 0.79, in_session=True,
                                 prev="Carlo")
    verifica("contrario: mai oltre la vita della conversazione (storia_inattiva_s 100 s)",
             n == "Luca", f"{n}")
    r_, sc_, ci_, reg_ = dopo_carlo()
    ci_._compagnia_attiva = lambda: True
    n, how, lv, v, t = riconosci(ci_, sc_, frase_con(0.606, 0.544), 3.03, in_session=True,
                                 prev="Carlo")
    verifica("contrario: in compagnia → il minore", n == "Luca" and not t.proprietario, f"{n}")
    r_, sc_, ci_, reg_ = dopo_carlo()
    r_.cfg.speaker_proprietario_s = 0
    n, how, lv, v, t = riconosci(ci_, sc_, frase_con(0.50, 0.485), 0.79, in_session=True,
                                 prev="Carlo")
    verifica("contrario: speaker_proprietario_s 0 → spenta, il minore", n == "Luca", f"{n}")
    r_, sc_, ci_, reg_ = ciclo_telefono()
    n, how, lv, v, t = riconosci(ci_, sc_, frase_con(0.50, 0.485), 0.79, in_session=True,
                                 prev="Carlo")
    verifica("contrario: Carlo mai riconosciuto qui dalla voce → il minore", n == "Luca", f"{n}")
    # La frase dopo, sicura, toglie la prudenza
    riconosci(ciclo, sc, frase_con(0.70, 0.37), 6.0, in_session=True, prev="Carlo")
    t = Turno()
    ciclo.rec = {}
    sc.minore_incerto = "Luca"
    ciclo._chi_parla(t)
    verifica("la prudenza vale una frase (azzerata a ogni frase)", sc.minore_incerto is None)


if __name__ == "__main__":
    print("── il proprietario del telefono ──")
    prova_proprietario()
    print("── i quattro casi ──")
    prova_casi()
    print("── il verso pericoloso ──")
    prova_verso_pericoloso()
    print("── conferma breve ──")
    prova_conferma_breve()
    print("── continuità ──")
    prova_continuita()
    print("── la frase che chiede chi parla ──")
    prova_frasi()
    prova_azione_in_sospeso()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    sys.exit(1 if errori else 0)
