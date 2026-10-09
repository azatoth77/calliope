"""
Prova a secco della «modalità compagnia» (09/10/2026, calliope/compagnia.py, calliope/rivolta.py,
docs/ricerche/2026-10-09-piu-persone.md § 6). Impronte sintetiche costruite con i punteggi voluti
(come prova_voci_famiglia), nomi di fantasia: Carlo amministra, Luca è il minore, Bianca è
un'adulta di casa; Amico e Ospite sono voci senza profilo.

- F0, lo stato per corsia: profilo recente (in qualunque ordine), gruppi tra ospiti, due profili;
  i contrari: una voce sola, la voce variabile della stessa persona (anche su un altro canale),
  frasi sotto 1 s, finestra scaduta, un altro satellite, due ospiti uguali, la TV (crea
  compagnia: giusto), modo spento; riassunto di `calliope stato --turni`.
- I due episodi veri (DGX, telefono, 08/10 sera e 09/10 notte) riscritti in numeri.
- F1, gli effetti: niente frase breve né continuità in compagnia, voce non sicura per i due
  cancelli e l'avviso che lo dice, azioni con la voce nella frase (registry), finestra d'ascolto
  senza nome chiusa con una voce sconosciuta (il nome passa sempre, anche dopo il nome da solo),
  famiglia tutta riconosciuta (compagnia sì, nome obbligatorio no), ombra senza effetti.
- F2, il giudizio «rivolta a Calliope» con un giudice finto: ombra (registra e non tace), attiva
  (silenzio, la protezione passa sempre), guasto = rivolta, mai fuori dalla compagnia; nessun
  tool prima del giudizio; la storia del modello ripulita.
"""

import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import prova_voci_famiglia as VF
from prova_voci_famiglia import ALTRO, CARLO, LUCA, Job, VoceFinta

from calliope import cancelli as cancelli_mod
from calliope import compagnia as compagnia_mod
from calliope import guardiano as guardia
from calliope import rivolta as rivolta_mod
from calliope.brain import Brain
from calliope.ciclo import _FINE, Turno
from calliope.speaker_id import SpeakerContext, normalize
from calliope.tools.registry import COMPAGNIA_RIPETI, ToolRegistry
from calliope.tools.spec import ToolContext, ToolSpec

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""),
          flush=True)


# ─────────────────────────── impronte sintetiche ───────────────────────────

_rng = np.random.default_rng(11)
AMICO = VF._ortho(CARLO, LUCA, ALTRO)
OSPITE = VF._ortho(CARLO, LUCA, ALTRO, AMICO)
CANALE = VF._ortho(CARLO, LUCA, ALTRO, AMICO, OSPITE)   # un altro microfono (lo stesso Carlo)
TV = VF._ortho(CARLO, LUCA, ALTRO, AMICO, OSPITE, CANALE)
NOTI = [CARLO, LUCA, ALTRO, AMICO, OSPITE, CANALE, TV]


def _resto():
    x = _rng.standard_normal(CARLO.shape[0])
    q, _ = np.linalg.qr(np.stack(NOTI, axis=1))
    return normalize(x - q @ (q.T @ x))


def frase(**punteggi) -> np.ndarray:
    """Un'impronta con i punteggi voluti contro le voci nominate (carlo, luca, bianca, amico,
    ospite, canale, tv) e un resto casuale ortogonale a tutte."""
    nomi = {"carlo": CARLO, "luca": LUCA, "bianca": ALTRO, "amico": AMICO, "ospite": OSPITE,
            "canale": CANALE, "tv": TV}
    vs = [nomi[k] for k in punteggi]
    s = np.array(list(punteggi.values()), dtype=np.float64)
    G = np.array([[float(a @ b) for b in vs] for a in vs])
    c = np.linalg.solve(G, s)
    v = sum(ci * vi for ci, vi in zip(c, vs))
    resto = 1 - float(v @ v)
    assert resto > 0, punteggi
    return (v + np.sqrt(resto) * _resto()).astype(np.float32)


class Orologio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def compagnia_nuova(cfg=None):
    reg = VF.Reg()
    if cfg is not None:
        reg.cfg = cfg
    orol = Orologio()
    return compagnia_mod.Compagnia(reg.cfg, reg, orologio=orol), orol, reg


def dici(c, orol, emb, voce_s, nome=None, dopo_s=10.0):
    orol.t += dopo_s
    return c.osserva(emb, voce_s, nome)


# ─────────────────────────── F0: lo stato per corsia ───────────────────────────

def prova_stato():
    c, orol, reg = compagnia_nuova()
    cfg = reg.cfg
    verifica("predefiniti: attiva, 300 s, profilo 0,20 da 1 s, gruppi 0,25 da 1,5 s, lungo 3 s, "
             "nome obbligatorio, giudizio in ombra",
             (compagnia_mod.modo(cfg), cfg.compagnia_finestra_s, cfg.compagnia_soglia_profilo,
              cfg.compagnia_voce_min_s, cfg.compagnia_soglia_gruppi, cfg.compagnia_gruppi_min_s,
              cfg.compagnia_gruppo_lungo_s, cfg.compagnia_nome_obbligatorio,
              compagnia_mod.modo_rivolta(cfg))
             == ("attiva", 300.0, 0.20, 1.0, 0.25, 1.5, 3.0, True, "ombra"))
    # Una voce sola: Carlo riconosciuto, frasi lunghe e corte
    for s, d in ((0.70, 2.0), (0.62, 3.5), (0.55, 1.2), (0.40, 0.6), (0.66, 5.0)):
        st = dici(c, orol, frase(carlo=s), d, "Carlo" if s >= 0.48 and d >= 1.0 else None)
    verifica("contrario: una voce sola (Carlo, 0,40–0,70) → nessuna compagnia", st is None)
    # La voce variabile della stessa persona: frasi a 0,25–0,35 sul profilo, simili tra loro
    for s in (0.35, 0.28, 0.25, 0.31):
        st = dici(c, orol, frase(carlo=s, canale=0.55), 2.2)
    verifica("contrario: voce variabile di Carlo (0,25–0,35, sopra 0,20) con frasi sue "
             "riconosciute → nessuna compagnia", st is None, json.dumps(st))
    c2, orol2, _ = compagnia_nuova()
    for s, d, n in ((0.52, 2.0, "Carlo"), (0.30, 4.0, None), (0.27, 3.2, None),
                    (0.50, 2.5, "Carlo"), (0.33, 2.0, None)):
        st = dici(c2, orol2, frase(carlo=s, canale=0.60 if n is None else 0.30), d, n)
    verifica("contrario: Carlo su un altro microfono (frasi lunghe non riconosciute a 0,27–0,33,"
             " simili alle sue) → nessuna compagnia", st is None, json.dumps(st))
    # Frasi sotto 1 s lontanissime: l'impronta non decide
    c, orol, _ = compagnia_nuova()
    dici(c, orol, frase(carlo=0.70), 2.0, "Carlo")
    st = dici(c, orol, frase(carlo=0.05, amico=0.6), 0.8)
    verifica("contrario: una frase di 0,8 s a 0,05 → nessuna compagnia (sotto 1 s)", st is None)
    # Profilo recente: una frase di almeno 1 s sotto 0,20 su Carlo
    st = dici(c, orol, frase(carlo=0.12, amico=0.6), 1.1)
    verifica("profilo: 1,1 s a 0,12 su Carlo riconosciuto qui → 2 voci, una sconosciuta",
             st is not None and st["voci"] == 2 and st["prova"] == "profilo"
             and st["sconosciute"] and abs(st["distanza"] - 0.12) < 0.01, json.dumps(st))
    verifica("solo in memoria: impronte della corsia, niente vettori nello stato",
             len(c) == 3 and all(not isinstance(v, (list, np.ndarray)) for v in st.values()))
    # Finestra scaduta
    orol.t += 301
    verifica("contrario: dopo 5 minuti senza frasi → di nuovo una voce sola",
             c.stato() is None and len(c) == 0)
    # In qualunque ordine: l'ospite prima, poi Carlo
    c, orol, _ = compagnia_nuova()
    st = dici(c, orol, frase(carlo=0.13, amico=0.6), 1.0)
    verifica("prima l'ospite, nessuno riconosciuto ancora → niente", st is None)
    st = dici(c, orol, frase(carlo=0.71), 2.0, "Carlo")
    verifica("poi Carlo riconosciuto → compagnia (profilo, in qualunque ordine)",
             st is not None and st["prova"] == "profilo")
    # Un altro satellite non ha sentito niente
    c_altro, _, _ = compagnia_nuova()
    verifica("contrario: un altro satellite (un'altra corsia) → nessuna compagnia",
             c_altro.stato() is None)
    # Due ospiti uguali: una voce sola senza profilo
    c, orol, _ = compagnia_nuova()
    for d in (2.0, 3.5, 1.8):
        st = dici(c, orol, frase(ospite=0.65), d)
    verifica("contrario: lo stesso ospite tre volte → una voce sola", st is None)
    # Due ospiti diversi: i gruppi
    st = dici(c, orol, frase(amico=0.65), 2.0)
    verifica("un secondo ospite, una frase di 2 s → non ancora (gruppo non confermato)",
             st is None)
    st = dici(c, orol, frase(amico=0.60), 1.6)
    verifica("…la seconda frase → gruppi: 2 voci sconosciute", st is not None
             and st["prova"] == "gruppi" and st["voci"] == 2 and st["sconosciute"],
             json.dumps(st))
    c, orol, _ = compagnia_nuova()
    dici(c, orol, frase(ospite=0.65), 2.0)
    dici(c, orol, frase(ospite=0.60), 2.0)
    st = dici(c, orol, frase(amico=0.65), 3.4)
    verifica("una frase lunga (3,4 s) di un'altra voce conta da sola", st is not None
             and st["prova"] == "gruppi")
    # Due profili diversi: la famiglia tutta riconosciuta
    c, orol, _ = compagnia_nuova()
    dici(c, orol, frase(carlo=0.70, luca=0.20), 2.0, "Carlo")
    st = dici(c, orol, frase(luca=0.72, carlo=0.20), 2.0, "Luca")
    verifica("Carlo e Luca riconosciuti → due_profili, nessuna voce sconosciuta",
             st is not None and st["prova"] == "due_profili" and st["voci"] == 2
             and not st["sconosciute"], json.dumps(st))
    # La TV a 0,1: un'altra voce, compagnia (giusto: non va ascoltata)
    c, orol, _ = compagnia_nuova()
    dici(c, orol, frase(carlo=0.66), 2.0, "Carlo")
    st = dici(c, orol, frase(carlo=0.10, tv=0.7), 4.0)
    verifica("la TV a 0,10 su Carlo → compagnia con una voce sconosciuta (giusto)",
             st is not None and st["sconosciute"])
    # Spenta e ombra
    c, orol, reg = compagnia_nuova()
    reg.cfg.compagnia_enabled = "spenta"
    dici(c, orol, frase(carlo=0.70), 2.0, "Carlo")
    st = dici(c, orol, frase(carlo=0.10, amico=0.6), 2.0)
    verifica("spenta: nessuno stato e nessuna impronta tenuta", st is None and len(c) == 0)
    verifica("modi: True/False dal YAML, valori sconosciuti → attiva",
             [compagnia_mod.modo(type("C", (), {"compagnia_enabled": v})()) for v in
              (True, False, "OMBRA", "boh")] == ["attiva", "spenta", "ombra", "attiva"])


def prova_riassunto():
    turni = [
        {"inizio": "2026-10-09T10:00:00", "voce": {"punteggio": 0.7}},
        {"inizio": "2026-10-09T10:01:00", "voce": {"punteggio": 0.1, "compagnia": {
            "voci": 2, "prova": "profilo", "distanza": 0.1, "sconosciute": True}},
         "regole": ["voci_compagnia", "compagnia_nome"]},
        {"inizio": "2026-10-09T10:02:00", "voce": {"punteggio": 0.6, "compagnia": {
            "voci": 2, "prova": "due_profili", "distanza": None, "sconosciute": False}},
         "regole": ["voci_compagnia", "non_rivolta_ombra"],
         "rivolta": {"per_calliope": False, "ms": 310, "modo": "ombra"}},
        {"inizio": "2026-10-09T10:03:00", "rivolta": {"per_calliope": None, "ms": 2000,
                                                      "guasto": "tempo"}},
    ]
    r = compagnia_mod.riassunto(turni)
    d = r.get("2026-10-09", {})
    verifica("stato --turni: frasi, in compagnia, prove, regole, giudizi",
             d.get("frasi") == 3 and d.get("in_compagnia") == 2 and d.get("sconosciute") == 1
             and d.get("prove") == {"profilo": 1, "due_profili": 1}
             and d.get("regole", {}).get("voci_compagnia") == 2 and d.get("giudizi") == 2
             and d.get("no") == 1 and d.get("guasti") == 1, json.dumps(d))
    t = compagnia_mod.testo(r)
    verifica("stato --turni: il testo, solo numeri", "in compagnia 2" in t
             and "non rivolte 1" in t)
    verifica("stato --turni: registro vuoto", "nessun turno" in compagnia_mod.testo({}))


# ─────────────────────────── il ciclo ───────────────────────────

class Ascoltatore:
    remoto = True
    started_at = 0.0


def ciclo_finto():
    reg, sc, ciclo, regole = VF.ciclo_finto()
    ciclo.speaker = VoceFinta()
    ciclo.listener = Ascoltatore()
    return reg, sc, ciclo, regole


def riconosci(ciclo, sc, emb, voiced_s, in_session=False, prev=None):
    sc.current_speaker = prev
    t = Turno(voiced_s=voiced_s, in_session=in_session, emb_job=Job(emb), prev_how=None)
    ciclo.rec = {}
    ciclo._riconosci_voce(t)
    return sc.current_speaker, sc.identified_by, ciclo.rec["voce"], t


def prova_episodi():
    """I due episodi veri della DGX, in numeri (docs/ricerche/2026-10-09-piu-persone.md § 1)."""
    # 08/10 22:22–22:25, telefono in un locale: l'amico preso per il minore, poi l'avviso
    reg, sc, ciclo, regole = ciclo_finto()
    riconosci(ciclo, sc, frase(carlo=0.13, amico=0.6), 1.0)
    riconosci(ciclo, sc, frase(carlo=0.12, amico=0.6), 1.1)
    n, how, v, t = riconosci(ciclo, sc, frase(carlo=0.70, luca=0.20), 2.0)
    verifica("episodio 1: Carlo riconosciuto dopo due frasi lontane dell'amico → in compagnia "
             "(profilo), Carlo resta Carlo dalla voce",
             n == "Carlo" and how == "voce" and v.get("compagnia", {}).get("prova") == "profilo"
             and "voci_compagnia" in regole and sc.compagnia, json.dumps(v))
    verifica("episodio 1: nel registro solo numeri", set(v["compagnia"]) ==
             {"voci", "prova", "distanza", "sconosciute"})
    regole.clear()
    n, how, v, t = riconosci(ciclo, sc, frase(carlo=0.425, luca=0.433, amico=0.4), 2.8,
                             in_session=True, prev="Carlo")
    verifica("episodio 1, 22:23: l'amico a 0,433 sul minore e 0,425 su Carlo → vale il minore "
             "(prudenza, come prima) ma la voce non è sicura", n == "Luca"
             and ciclo._voce_incerta() and ciclo._in_compagnia(), f"{n} {how}")
    regole.clear()
    n, how, v, t = riconosci(ciclo, sc, frase(luca=0.45, carlo=0.30, amico=0.4), 0.57,
                             in_session=True, prev="Luca")
    verifica("episodio 1, 22:24: 0,57 s «breve, vale la conversazione» → in compagnia "
             "ospite, non il minore (niente guardiano del minore né avviso)",
             n is None and "compagnia_senza_breve" in regole, f"{n} {how} {regole}")
    # 09/10 01:29–01:45: frasi lunghe dell'amico a 0,22–0,33 su Carlo, quelle di Carlo sopra 0,49
    reg, sc, ciclo, regole = ciclo_finto()
    sequenza = [("carlo", 0.62, 2.5), ("ospite", 0.22, 6.1), ("carlo", 0.55, 1.8),
                ("ospite", 0.30, 4.9), ("ospite", 0.26, 14.3), ("carlo", 0.71, 2.2),
                ("ospite", 0.33, 8.0)]
    stati = []
    for chi, s, d in sequenza:
        e = frase(carlo=s, luca=0.15) if chi == "carlo" else frase(carlo=s, ospite=0.65)
        n, how, v, t = riconosci(ciclo, sc, e, d)
        stati.append(v.get("compagnia"))
    verifica("episodio 2: le frasi lunghe dell'ospite a 0,22–0,33 → in compagnia dai gruppi "
             "dalla seconda, con una voce sconosciuta",
             stati[0] is None and all(x and x["sconosciute"] for x in stati[3:]),
             json.dumps([x and x["prova"] for x in stati]))
    verifica("episodio 2: serve il nome a ogni frase", ciclo._chiede_nome())
    # Le frasi senza il nome nella finestra d'ascolto: 20 delle 23 dell'ospite, 18 con risposta
    prese = 0
    for testo in ("Non lo portavo in giro.", "Ma dai, davvero?", "E poi cosa ha detto?"):
        # Ognuna come se la finestra fosse aperta (prima del 09/10 la riapriva la risposta)
        ciclo.awake_until = time.monotonic() + 8
        ciclo.listener.started_at = time.monotonic()
        ciclo.rec = {"testo": testo}
        t = Turno(text=testo)
        if ciclo._compagnia_senza_nome(t) is not _FINE:
            prese += 1
    verifica("episodio 2: le frasi senza il nome nella finestra non si prendono (regola "
             "compagnia_nome, niente testo nel registro, finestra chiusa)",
             prese == 0 and "compagnia_nome" in regole and ciclo.rec["testo"] is None
             and ciclo.rec["esito"] == "ignorato" and ciclo.awake_until == 0.0)


def prova_effetti():
    reg, sc, ciclo, regole = ciclo_finto()
    cfg = reg.cfg
    # Continuità: Carlo riconosciuto, poi una frase cortissima sua → senza compagnia vale lui
    riconosci(ciclo, sc, frase(carlo=0.72, luca=0.2), 2.0)
    n, how, v, t = riconosci(ciclo, sc, frase(carlo=0.44, luca=0.11), 0.5)
    verifica("contrario: una persona sola → la continuità come prima", n == "Carlo"
             and t.continuita and not sc.compagnia)
    n, how, v, t = riconosci(ciclo, sc, frase(carlo=0.40, luca=0.1), 0.6, in_session=True,
                             prev="Carlo")
    verifica("contrario: una persona sola → la frase breve vale chi parlava", n == "Carlo"
             and how == "breve")
    # Un'altra voce lontana: compagnia
    riconosci(ciclo, sc, frase(carlo=0.10, amico=0.6), 2.0)
    regole.clear()
    n, how, v, t = riconosci(ciclo, sc, frase(carlo=0.44, luca=0.11), 0.5)
    verifica("in compagnia: niente continuità", n is None and not t.continuita
             and "voce_continuita" not in regole)
    n, how, v, t = riconosci(ciclo, sc, frase(carlo=0.40, luca=0.1), 0.6, in_session=True,
                             prev="Carlo")
    verifica("in compagnia: niente frase breve (né conferma breve)", n is None
             and not sc.conferma_breve and sc.current_level == "ospite")
    n, how, v, t = riconosci(ciclo, sc, frase(carlo=0.70, luca=0.2), 2.0)
    verifica("in compagnia: Carlo riconosciuto nella frase → amministra come prima",
             n == "Carlo" and how == "voce" and sc.current_level == "amministra")
    n, how, v, t = riconosci(ciclo, sc, frase(carlo=0.44, luca=0.1), 2.0, in_session=True,
                             prev="Carlo")
    verifica("in compagnia: la zona grigia resta per la conversazione (familiare)",
             (n, how) == ("Carlo", "conversazione") and sc.compagnia)
    # Il minore con la frase cortissima sopra la soglia piena resta il minore (mai un adulto)
    n, how, v, t = riconosci(ciclo, sc, frase(luca=0.55, carlo=0.1), 0.6, in_session=True,
                             prev="Carlo")
    verifica("in compagnia: frase cortissima con il minore sopra la soglia piena → il minore",
             n == "Luca", f"{n} {how}")
    # Ombra: nessun effetto, solo il registro
    reg, sc, ciclo, regole = ciclo_finto()
    reg.cfg.compagnia_enabled = "ombra"
    riconosci(ciclo, sc, frase(carlo=0.72, luca=0.2), 2.0)
    riconosci(ciclo, sc, frase(carlo=0.10, amico=0.6), 2.0)
    n, how, v, t = riconosci(ciclo, sc, frase(carlo=0.40, luca=0.1), 0.6, in_session=True,
                             prev="Carlo")
    verifica("ombra: stato nel registro e regola, ma la frase breve come prima",
             (n, how) == ("Carlo", "breve") and v.get("compagnia") and not sc.compagnia
             and "voci_compagnia" in regole and not ciclo._chiede_nome(), f"{n} {how}")
    # Spenta: niente di niente
    reg, sc, ciclo, regole = ciclo_finto()
    reg.cfg.compagnia_enabled = "spenta"
    riconosci(ciclo, sc, frase(carlo=0.72, luca=0.2), 2.0)
    n, how, v, t = riconosci(ciclo, sc, frase(carlo=0.10, amico=0.6), 2.0)
    verifica("spenta: nessuna compagnia nel registro", "compagnia" not in v
             and "voci_compagnia" not in regole)


def prova_finestra():
    reg, sc, ciclo, regole = ciclo_finto()
    cfg = reg.cfg
    ora = time.monotonic()

    def frase_in_finestra(testo, **kw):
        ciclo.awake_until = time.monotonic() + 8
        ciclo.listener.started_at = time.monotonic()
        ciclo.rec = {"testo": testo}
        return ciclo._compagnia_senza_nome(Turno(text=testo, **kw))

    verifica("contrario: una persona sola → la frase senza nome nella finestra passa",
             frase_in_finestra("E domani?") is None)
    riconosci(ciclo, sc, frase(carlo=0.72, luca=0.2), 2.0)
    riconosci(ciclo, sc, frase(carlo=0.10, amico=0.6), 2.0)
    verifica("voce sconosciuta: la frase senza nome nella finestra non passa",
             frase_in_finestra("E domani?") is _FINE)
    verifica("il nome passa sempre", frase_in_finestra("Calliope, e domani?") is None)
    verifica("il nome storpiato passa (tolleranza larga)",
             frase_in_finestra("Caliope che ore sono") is None)
    verifica("la domanda dopo il nome da solo passa",
             frase_in_finestra("Che ore sono?", dal_nome=True) is None)
    verifica("lo scritto passa", frase_in_finestra("E domani?", scritto={"x": 1}) is None)
    ciclo.awake_until = time.monotonic() - 1
    ciclo.listener.started_at = time.monotonic()
    ciclo.rec = {"testo": "ciao"}
    verifica("fuori dalla finestra: decide il nome come sempre (non questa regola)",
             ciclo._compagnia_senza_nome(Turno(text="ciao")) is None)
    cfg.compagnia_nome_obbligatorio = False
    verifica("compagnia_nome_obbligatorio spento → passa", frase_in_finestra("E domani?") is None)
    cfg.compagnia_nome_obbligatorio = True
    # Lo schermo: il segno con la voce sconosciuta
    class Schermi:
        def __init__(self):
            self.ultimo = None

        def voce(self, stato, fino=None, **kw):
            self.ultimo = (stato, kw)

    ciclo.s.schermi = Schermi()
    ciclo.stanza_voce = lambda: None
    ciclo.voce("ascolta", time.time() + 8)
    verifica("schermi: «compagnia» nello stato della voce", ciclo.s.schermi.ultimo[1].get(
        "compagnia") is True)
    # Famiglia tutta riconosciuta: compagnia sì, nome obbligatorio no
    reg, sc, ciclo, regole = ciclo_finto()
    riconosci(ciclo, sc, frase(carlo=0.72, luca=0.2), 2.0)
    riconosci(ciclo, sc, frase(luca=0.70, carlo=0.2), 2.0)
    ciclo.s.schermi = Schermi()
    ciclo.stanza_voce = lambda: None
    ciclo.voce("ascolta", time.time() + 8)
    verifica("famiglia tutta riconosciuta: in compagnia, ma la finestra resta",
             ciclo._stato_compagnia() is not None and not ciclo._chiede_nome()
             and frase_in_finestra("E domani?") is None
             and "compagnia" not in ciclo.s.schermi.ultimo[1])
    # Una voce sola per 5 minuti: il nome non serve più
    reg, sc, ciclo, regole = ciclo_finto()
    orol = Orologio()
    ciclo.compagnia.orologio = orol
    riconosci(ciclo, sc, frase(carlo=0.72, luca=0.2), 2.0)
    riconosci(ciclo, sc, frase(carlo=0.10, amico=0.6), 2.0)
    verifica("con la voce sconosciuta il nome serve", ciclo._chiede_nome())
    orol.t += 301
    verifica("…5 minuti dopo l'ultima frase dell'altra voce non serve più",
             not ciclo._chiede_nome())


def prova_cancelli():
    t = cancelli_mod.testo_avviso("Luca", ["autolesionismo"], cancelli_mod.CONFERMATO, "acuto",
                                  True, compagnia=True)
    verifica("avviso in compagnia: lo dice (altre persone, voce non sicura)",
             "altre persone" in t and "potrebbe non essere stato lui" in t and t.count(
                 "Attenzione") == 1, t)
    t2 = cancelli_mod.testo_avviso("Luca", ["autolesionismo"], cancelli_mod.CONFERMATO, "acuto",
                                   False)
    verifica("contrario: senza compagnia né voce incerta l'avviso è quello di prima",
             "Attenzione" not in t2)
    t3 = cancelli_mod.testo_avviso("Luca", ["autolesionismo"], cancelli_mod.DA_VERIFICARE,
                                   "silenzio", False, compagnia=True)
    verifica("avviso da verificare in compagnia: lo dice anche lui", "altre persone" in t3)
    # Il segnale del primo cancello ricorda la compagnia fino al secondo
    reg, sc, ciclo, regole = ciclo_finto()
    riconosci(ciclo, sc, frase(luca=0.72, carlo=0.2), 2.0)
    riconosci(ciclo, sc, frase(luca=0.10, amico=0.6), 2.0)
    n, how, v, t = riconosci(ciclo, sc, frase(luca=0.70, carlo=0.2), 2.0)
    verifica("il minore riconosciuto dalla voce in compagnia: voce non sicura per i cancelli",
             n == "Luca" and how == "voce" and ciclo._voce_incerta())
    c = cancelli_mod.Cancelli(reg.cfg)
    seg = c.apri(reg.users["Luca"], "frase", ["autolesionismo"], True, "sat:x", compagnia=True)
    verifica("cancello 1: il segnale aperto ricorda la compagnia", seg.compagnia is True)
    reg2, sc2, ciclo2, _ = ciclo_finto()
    riconosci(ciclo2, sc2, frase(luca=0.70, carlo=0.2), 2.0)
    verifica("contrario: il minore da solo, riconosciuto dalla voce → voce sicura",
             not ciclo2._voce_incerta())


def prova_registry():
    p = VF.Persone()
    sc = SpeakerContext(p)
    ctx = ToolContext(cfg=p.cfg, speakers=p, speaker_ctx=sc, speaker=None)
    reg = ToolRegistry()
    fatti = []
    for nome, livelli in (("azione_famiglia", {"familiare", "amministra"}),
                          ("azione_admin", {"amministra"}),
                          ("lettura", {"ospite", "familiare", "amministra"})):
        reg.register(ToolSpec(name=nome, description="", parameters={},
                              func=lambda ctx, _n=nome, **a: fatti.append(_n) or {
                                  "ok": True, "conferma": "Fatto."},
                              risk="azione" if nome != "lettura" else "lettura",
                              levels=frozenset(livelli)))
    sc.current_speaker, sc.identified_by, sc.from_session = "Bianca", "conversazione", True
    sc.compagnia = True
    out = json.loads(reg.call("azione_famiglia", {}, ctx, sc.current_level))
    verifica("in compagnia, zona grigia: un'azione chiede la voce nella frase",
             not fatti and out["risposta_finale"] == COMPAGNIA_RIPETI
             and "compagnia_voce_nella_frase" in ctx.regole, out.get("risposta_finale"))
    out = json.loads(reg.call("lettura", {}, ctx, sc.current_level))
    verifica("in compagnia, zona grigia: ciò che può fare un ospite passa", fatti == ["lettura"])
    fatti.clear()
    sc.identified_by, sc.from_session = "voce", False
    out = json.loads(reg.call("azione_famiglia", {}, ctx, sc.current_level))
    verifica("in compagnia, voce riconosciuta nella frase: l'azione passa",
             fatti == ["azione_famiglia"])
    fatti.clear()
    sc.compagnia, sc.identified_by, sc.from_session = False, "conversazione", True
    out = json.loads(reg.call("azione_famiglia", {}, ctx, sc.current_level))
    verifica("contrario: senza compagnia la zona grigia vale come prima",
             fatti == ["azione_famiglia"])
    # Chi amministra nella zona grigia in compagnia: la frase di sfida
    fatti.clear()
    ctx.regole = []
    sc.current_speaker, sc.identified_by, sc.from_session = "Carlo", "conversazione", True
    sc.compagnia = True
    out = json.loads(reg.call("azione_admin", {}, ctx, sc.current_level))
    verifica("in compagnia, chi amministra nella zona grigia → la frase di sfida",
             not fatti and sc.sfida is not None and "compagnia_voce_nella_frase" in ctx.regole,
             out.get("risposta_finale"))


# ─────────────────────────── F2: «rivolta a Calliope» ───────────────────────────

def prova_rivolta():
    reg, sc, ciclo, regole = ciclo_finto()
    cfg = reg.cfg
    risposte = []

    def chiama(msgs, timeout):
        risposte.append(msgs)
        return giudizio[0]

    giudizio = ['{"per_calliope": false}']
    ciclo._giudice = rivolta_mod.Giudice(cfg, chiama=chiama)
    # Fuori dalla compagnia il giudizio non scatta mai
    t = Turno(text="Non lo portavo in giro.", senza_nome=True)
    verifica("una persona sola: nessun giudizio", ciclo._avvia_rivolta(t) is None)
    riconosci(ciclo, sc, frase(carlo=0.72, luca=0.2), 2.0)
    riconosci(ciclo, sc, frase(luca=0.70, carlo=0.2), 2.0)       # famiglia: compagnia
    verifica("contrario: con il nome (o dopo il nome da solo) nessun giudizio",
             ciclo._avvia_rivolta(Turno(text="x", senza_nome=False)) is None
             and ciclo._avvia_rivolta(Turno(text="x", senza_nome=True, dal_nome=True)) is None)
    # Ombra: registra, non tace
    t = Turno(text="Non lo portavo in giro.", senza_nome=True)
    t.rivolta = ciclo._avvia_rivolta(t)
    verifica("ombra: il giudizio parte in compagnia", t.rivolta is not None
             and t.rivolta["modo"] == "ombra")
    verifica("ombra: le frasi della risposta passano", ciclo._rivolta_ok(t))
    ciclo.rec = {}
    ciclo._registra_rivolta(t)
    verifica("ombra: nel registro il giudizio e la regola non_rivolta_ombra",
             ciclo.rec.get("rivolta", {}).get("per_calliope") is False
             and "non_rivolta_ombra" in regole, json.dumps(ciclo.rec.get("rivolta")))
    verifica("il giudizio vede il prompt e la frase, non la voce",
             "Frase nuova: Non lo portavo in giro." in risposte[-1][1]["content"]
             and "voce" not in risposte[-1][1]["content"].lower())
    # Nel contesto il nome di chi ha la conversazione, se è registrato
    class BrainCarlo:
        conv_owner = "carlo-id"
        history = [{"role": "user", "content": "Calliope, che ore sono?"},
                   {"role": "assistant", "content": "Le dieci."}]
    ciclo.brain = BrainCarlo()
    t = Turno(text="Questa era terribile, Carlo.", senza_nome=True)
    t.rivolta = ciclo._avvia_rivolta(t)
    ciclo._giudizio_rivolta(t)
    verifica("il contesto con il nome di chi ha la conversazione",
             "Carlo (registrato): Calliope, che ore sono?" in risposte[-1][1]["content"]
             and "Calliope: Le dieci." in risposte[-1][1]["content"])
    ciclo.brain = None
    # Attiva: silenzio
    cfg.compagnia_rivolta = "attiva"
    t = Turno(text="Non lo portavo in giro.", senza_nome=True)
    t.rivolta = ciclo._avvia_rivolta(t)
    chiuso = []

    def risposta():
        try:
            yield "Capito."
            yield "Altro."
        finally:
            chiuso.append(True)

    detto = list(ciclo._solo_se_rivolta(t, risposta()))
    verifica("attiva, non rivolta: nessuna frase detta e lo stream chiuso",
             detto == [] and chiuso and t.non_rivolta)
    t = Turno(text="Non lo portavo in giro.", senza_nome=True)
    t.rivolta = ciclo._avvia_rivolta(t)

    def protezione():
        yield guardia.PROTEZIONE
    detto = list(ciclo._solo_se_rivolta(t, protezione()))
    verifica("attiva: la protezione si dice sempre", detto == [guardia.PROTEZIONE])
    giudizio[0] = '{"per_calliope": true}'
    t = Turno(text="E domani?", senza_nome=True)
    t.rivolta = ciclo._avvia_rivolta(t)
    verifica("attiva, rivolta: la risposta passa", list(ciclo._solo_se_rivolta(
        t, iter(["Domani sole."]))) == ["Domani sole."] and not t.non_rivolta)
    giudizio[0] = "non è JSON"
    t = Turno(text="E domani?", senza_nome=True)
    t.rivolta = ciclo._avvia_rivolta(t)
    verifica("attiva, giudizio guasto → vale rivolta", ciclo._rivolta_ok(t)
             and ciclo._giudizio_rivolta(t).guasto is not None)
    # Il registro di una frase non rivolta: niente testo, regola, storia ripulita
    giudizio[0] = '{"per_calliope": false}'
    t = Turno(text="Non lo portavo in giro.", senza_nome=True)
    t.rivolta = ciclo._avvia_rivolta(t)
    ciclo._rivolta_ok(t)

    class B:
        history = [{"role": "user", "content": "Calliope, che ore sono?"},
                   {"role": "assistant", "content": "Le dieci."},
                   {"role": "user", "content": "Non lo portavo in giro."},
                   {"role": "assistant", "content": "Capito."}]
        salva_conversazione = lambda self: None
        dimentica_ultimo_turno = Brain.dimentica_ultimo_turno
    ciclo.brain = B()
    ciclo.rec = {"testo": "Non lo portavo in giro."}
    ciclo._registra_non_rivolta(t)
    verifica("non rivolta: esito, regola, nessun testo nel registro",
             ciclo.rec["esito"] == "non_rivolta" and ciclo.rec["testo"] is None
             and "non_rivolta" in regole)
    verifica("non rivolta: via dalla storia la frase e la risposta taciuta",
             [m["content"] for m in ciclo.brain.history]
             == ["Calliope, che ore sono?", "Le dieci."])
    # Nessun tool prima del giudizio (Brain._run_tool)
    p = VF.Persone()
    sc2 = SpeakerContext(p)
    ctx = ToolContext(cfg=p.cfg, speakers=p, speaker_ctx=sc2, speaker=None)
    treg = ToolRegistry()
    fatti = []
    treg.register(ToolSpec(name="azione", description="", parameters={},
                           func=lambda ctx, **a: fatti.append(1) or {"ok": True},
                           risk="azione", levels=frozenset({"familiare", "amministra"})))
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history, b.tool_ctx = p.cfg, treg, [], ctx
    b.prima_del_tool = lambda: False
    try:
        out = json.loads(b._run_tool({"name": "azione", "arguments": {}}, "familiare"))
        verifica("nessun tool se la frase non era rivolta a Calliope", not fatti
                 and out.get("ok") is False, json.dumps(out))
    except Exception as e:  # noqa: BLE001
        verifica("nessun tool se la frase non era rivolta a Calliope", False,
                 f"{type(e).__name__}: {e}")
    # Il giudice: messaggi, contesto, guasto
    g = rivolta_mod.Giudice(cfg, chiama=lambda m, to: '{"per_calliope": true}').giudica(
        [("Persona", "Calliope, che tempo fa?"), ("Calliope", "Sole.")], "E domani?")
    verifica("giudice: rivolta", g.per_calliope is True and g.rivolta and g.guasto is None)
    g = rivolta_mod.Giudice(cfg, chiama=lambda m, to: (_ for _ in ()).throw(TimeoutError())
                            ).giudica([], "x")
    verifica("giudice: scaduto → guasto, vale rivolta", g.per_calliope is None and g.rivolta
             and g.guasto == "TimeoutError")
    h = [{"role": "system", "content": "s"}, {"role": "user", "content": "a"},
         {"role": "assistant", "content": None, "tool_calls": [{}]},
         {"role": "tool", "content": "{}"}, {"role": "assistant", "content": "b"}]
    verifica("giudice: il contesto solo dai testi della persona e di Calliope",
             rivolta_mod.righe_contesto(h) == [("Persona", "a"), ("Calliope", "b")])
    verifica("giudice: il modello del rilevatore di pericolo, se c'è",
             rivolta_mod.dove(type("C", (), {"guardiano_pericolo_modello": "m1",
                                             "guardiano_pericolo_url": "http://127.0.0.1:1/",
                                             "compagnia_rivolta_modello": ""})())
             == ("http://127.0.0.1:1", "m1"))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    for nome, f in (("lo stato per corsia", prova_stato), ("stato --turni", prova_riassunto),
                    ("i due episodi veri", prova_episodi), ("gli effetti (F1)", prova_effetti),
                    ("la finestra d'ascolto", prova_finestra), ("i due cancelli", prova_cancelli),
                    ("le azioni", prova_registry), ("rivolta a Calliope (F2)", prova_rivolta)):
        print(f"── {nome} ──", flush=True)
        f()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    sys.exit(1 if errori else 0)
