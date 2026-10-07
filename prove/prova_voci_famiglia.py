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


if __name__ == "__main__":
    print("── i quattro casi ──")
    prova_casi()
    print("── il verso pericoloso ──")
    prova_verso_pericoloso()
    print("── conferma breve ──")
    prova_conferma_breve()
    print("── la frase che chiede chi parla ──")
    prova_frasi()
    prova_azione_in_sospeso()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    sys.exit(1 if errori else 0)
