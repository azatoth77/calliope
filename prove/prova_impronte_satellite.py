"""
Prova a secco delle impronte della voce per satellite (15/10/2026, calliope/impronte_satellite.py,
speaker_id.py, ciclo._riconosci_voce, stanza/conoscenti.py, conserva.py). Impronte sintetiche
(vettori costruiti con i punteggi voluti), nomi di fantasia: Carlo amministra, Luca è il minore
(14 anni, tutore Carlo), Bianca è di famiglia, Marco è un conoscente.

Il canale del telefono è una direzione P ortogonale alle voci: una frase di Carlo al telefono è
a·CARLO + b·P. Il caso vero del 15/10 in numeri: Carlo 0,444 sull'impronta di sempre, Luca
0,358, mentre le sue frasi sicure sullo stesso telefono stavano a 0,60–0,76.

- l'apprendimento solo dalle frasi sicure (soglia, margine, voce lunga; mai zona grigia, frase
  breve, compagnia, voce incerta, minore vicino, continuità), il seme dopo N frasi (mai la prima),
  la deriva limitata dall'arruolamento e dal seme, il ripiego sul canale, il massimo dei
  satelliti per persona;
- spento: niente cambia; ombra: si impara e si salva, la decisione resta quella di oggi, nel
  registro dei turni la decisione con e senza; attivo: il caso del 15/10 riconosciuto;
- simmetria: con l'impronta del telefono solo per chi amministra una frase debole del minore va a
  lui (al più familiare: `amministra_minore_vicino`); con quella del minore torna al minore; le
  regole di protezione (`piu_protetto`, minore vicino) sui punteggi nuovi;
- i casi del 07/10 di prova_voci_famiglia uguali in ombra e attivo;
- tenuta: speakers.json (con e senza il campo, modello diverso), nuova registrazione, rinomina,
  «svuota» di una persona e di tutti (dal processo e da terminale, copia .bak compresa);
- conoscenti: apprendimento, riconoscimento al telefono, file, promozione e ritorno, «dimentica»;
- la sezione di `calliope stato --turni`; configurazione.
"""

import datetime
import json
import os
import sys
import tempfile
import time
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope import impronte_satellite as IS
from calliope.ciclo import Ciclo, Servizi, Turno
from calliope.config import Config
from calliope.speaker_id import SpeakerContext, SpeakerRegistry, UserProfile, normalize
from calliope.stanza import conoscenti as con_mod

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio and not ok
                                                  else ""), flush=True)


# ─────────────────────────── impronte sintetiche ───────────────────────────

DIM = 192
_rng = np.random.default_rng(15)


def _ortho(*vs):
    x = _rng.standard_normal(DIM)
    q, _ = np.linalg.qr(np.stack(vs, axis=1))
    return normalize(x - q @ (q.T @ x))


CARLO = normalize(_rng.standard_normal(DIM))
LUCA = normalize(0.17 * CARLO + np.sqrt(1 - 0.17 ** 2) * _ortho(CARLO))
BIANCA = _ortho(CARLO, LUCA)
MARCO = _ortho(CARLO, LUCA, BIANCA)
P = _ortho(CARLO, LUCA, BIANCA, MARCO)            # il canale del telefono in auto
BASE = [CARLO, LUCA, BIANCA, MARCO, P]


def frase(carlo=0.0, luca=0.0, bianca=0.0, marco=0.0, tel=0.0, seme=None) -> np.ndarray:
    """Un'impronta di frase con i punteggi voluti contro le impronte di sempre e la componente
    del telefono `tel` (P è ortogonale a tutte)."""
    r = float(CARLO @ LUCA)
    b = (luca - r * carlo) / (1 - r * r)
    a = carlo - b * r
    v = a * CARLO + b * LUCA + bianca * BIANCA + marco * MARCO + tel * P
    resto = 1 - float(v @ v)
    assert resto > 0, (carlo, luca, tel)
    rng = np.random.default_rng(seme) if seme is not None else _rng
    x = rng.standard_normal(DIM)
    q, _ = np.linalg.qr(np.stack(BASE, axis=1))
    o = normalize(x - q @ (q.T @ x))
    return (v + np.sqrt(resto) * o).astype(np.float32)


def cfg_modo(modo: str, **kw) -> Config:
    c = Config()
    c.speaker_impronte_satellite = modo
    for k, v in kw.items():
        setattr(c, k, v)
    return c


NASCITA = (datetime.date.today() - datetime.timedelta(days=14 * 366)).isoformat()


class Reg(SpeakerRegistry):
    """Il registro vero senza il modello ONNX; save conta e basta."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.users = {
            "Carlo": UserProfile(name="Carlo", voiceprint=CARLO.copy(),
                                 initial_voiceprint=CARLO.copy(), admin=True, id="carlo-id"),
            "Luca": UserProfile(name="Luca", voiceprint=LUCA.copy(),
                                initial_voiceprint=LUCA.copy(), nascita=NASCITA,
                                tutori=["carlo-id"], id="luca-id"),
            "Bianca": UserProfile(name="Bianca", voiceprint=BIANCA.copy(),
                                  initial_voiceprint=BIANCA.copy(), id="bianca-id"),
        }
        self._salvato, self._da_salvare = time.monotonic(), False
        self.illeggibile = None
        self.salvataggi = 0

    def save(self):
        self.salvataggi += 1


class Job:
    def __init__(self, e):
        self.e = e

    def result(self):
        return self.e


class Telefono:
    """Il listener di un satellite: il telefono in auto."""
    remoto = True
    started_at = 0.0
    canale = "telefono"
    satellite_nome = "telefono di prova"


class VoceFinta:
    _current_voice_path = None


class Corsia:
    conv = None


def ciclo_finto(modo: str, listener=None, **kw):
    # L'impronta di sempre ferma dalla deriva, come quella di chi amministra al 07/10
    kw.setdefault("speaker_adapt_max_drift", 0.9999)
    cfg = cfg_modo(modo, **kw)
    reg = Reg(cfg)
    sc = SpeakerContext(reg)
    ciclo = Ciclo(Servizi(cfg, registry=reg), Corsia(), None, None, sc, None, None, None,
                  None, None)
    ciclo.speaker = VoceFinta()
    ciclo.listener = listener if listener is not None else Telefono()
    regole = []
    ciclo.rule = regole.append
    ciclo.rec = {}
    return reg, sc, ciclo, regole


def riconosci(ciclo, sc, emb, voiced_s=2.5, in_session=False, prev=None):
    """Come ciclo._chi_parla: i segni della frase di prima valgono una frase."""
    sc.current_speaker = prev
    sc.incerta = sc.minore_vicino = sc.minore_incerto = sc.conoscente = None
    sc.compagnia = sc.compagnia_sconosciute = False
    t = Turno(voiced_s=voiced_s, in_session=in_session, emb_job=Job(emb), prev_how=None)
    ciclo.rec = {}
    ciclo._riconosci_voce(t)
    return sc.current_speaker, sc.identified_by, sc.current_level, ciclo.rec["voce"], t


def sicure_di_carlo(ciclo, sc, n=4, tel=0.6, carlo=0.65):
    """Frasi sicure di Carlo al telefono (come le sei del 15/10, 0,60–0,76)."""
    for i in range(n):
        riconosci(ciclo, sc, frase(carlo=carlo, luca=0.12, tel=tel, seme=100 + i), 3.0)


def sicure_di_luca(ciclo, sc, n=4, tel=0.35, luca=0.8):
    """Frasi sicure di Luca sullo stesso telefono, da solo: con Carlo sentito da poco sarebbe
    compagnia (due profili), e in compagnia non si impara."""
    ciclo.compagnia.dimentica()
    for i in range(n):
        riconosci(ciclo, sc, frase(carlo=0.12, luca=luca, tel=tel, seme=200 + i), 3.0)
    ciclo.compagnia.dimentica()


# ─────────────────────────── il modulo ───────────────────────────

def prova_modulo():
    cfg = Config()
    verifica("predefiniti: spento, seme 3, margine 0,15, voce 1,5 s, deriva 0,70 e 0,85",
             (IS.modo(cfg), cfg.speaker_impronte_seme_frasi, cfg.speaker_impronte_margine,
              cfg.speaker_impronte_min_voce_s, cfg.speaker_impronte_deriva_arruolamento,
              cfg.speaker_impronte_deriva_seme) == ("spento", 3, 0.15, 1.5, 0.70, 0.85))
    for v, att in ((False, "spento"), (True, "attivo"), ("OMBRA", "ombra"), ("boh", "spento"),
                   (None, "spento")):
        verifica(f"modo: {v!r} → {att}", IS.modo(SimpleNamespace(speaker_impronte_satellite=v))
                 == att)
    verifica("chiavi: satellite per nome, poi il canale",
             IS.chiavi("telefono  di prova", "Telefono") == ("sat:telefono di prova",
                                                             "canale:telefono"))
    verifica("chiavi: senza nome solo il canale", IS.chiavi(None, None) == ("canale:satellite",))
    # sicura e i contrari
    s = lambda **k: IS.sicura(cfg, k.pop("come", "voce"), k.pop("sim", 0.70),
                              k.pop("sim2", 0.30), k.pop("voce_s", 2.0), **k)
    verifica("sicura: voce netta e lunga", s())
    for nome, kw in (("zona grigia", {"come": "conversazione"}), ("frase breve", {"come": "breve"}),
                     ("ospite", {"come": None}), ("sotto speaker_adapt_threshold", {"sim": 0.55}),
                     ("margine stretto", {"sim2": 0.58}), ("voce corta", {"voce_s": 1.2}),
                     ("compagnia", {"compagnia": True}), ("voce incerta", {"incerta": True}),
                     ("minore vicino", {"minore_vicino": True}),
                     ("continuità", {"continuita": True})):
        verifica(f"contrario: non sicura con {nome}", not s(**kw))
    # seme e deriva
    imp: dict = {}
    ch = IS.chiavi("tel", "telefono")
    y = [frase(carlo=0.65, luca=0.1, tel=0.6, seme=10 + i) for i in range(4)]
    verifica("la prima frase sicura non fa l'impronta",
             IS.impara(imp, y[0], ch, CARLO, cfg) == [] and not imp["sat:tel"].pronta
             and IS.scrivi(imp) == {})
    IS.impara(imp, y[1], ch, CARLO, cfg)
    cambiate = IS.impara(imp, y[2], ch, CARLO, cfg)
    verifica("alla terza nasce il seme, del satellite e del canale",
             cambiate == ["sat:tel", "canale:telefono"] and imp["sat:tel"].pronta
             and imp["sat:tel"].n == 3 and imp["sat:tel"].attesa == [])
    verifica("il seme è la media delle tre", float(imp["sat:tel"].v @ normalize(
        np.mean(np.stack(y[:3]), axis=0))) > 0.999)
    verifica("il punteggio è il massimo fra le due impronte",
             IS.punteggio(frase(carlo=0.44, luca=0.35, tel=0.75, seme=1), CARLO, imp, ch)[1]
             == "sat:tel")
    verifica("ripiego sul canale per un satellite nuovo",
             IS.migliore(y[3], imp, IS.chiavi("tel nuovo", "telefono"))[1] == "canale:telefono")
    verifica("un altro canale: niente", IS.migliore(y[3], imp, IS.chiavi("studio",
                                                                           "satellite")) ==
             (None, None))
    # deriva dall'arruolamento: frasi lontane dall'impronta di sempre non fanno il seme
    imp2: dict = {}
    lontane = [frase(carlo=0.45, luca=0.1, tel=0.85, seme=30 + i) for i in range(5)]
    for x in lontane:
        IS.impara(imp2, x, ch, CARLO, cfg)
    verifica("contrario: seme troppo lontano dall'arruolamento, niente impronta",
             not imp2["sat:tel"].pronta)
    # deriva dal seme: una frase molto diversa non sposta l'impronta oltre il limite
    prima = imp["sat:tel"].v.copy()
    altra = frase(carlo=0.70, luca=0.1, tel=-0.6, seme=40)
    c2 = IS.impara(imp, altra, ch, CARLO, cfg_modo("attivo", speaker_impronte_alpha=0.5))
    verifica("contrario: la deriva dal seme ferma l'aggiornamento",
             "sat:tel" not in c2 and float(imp["sat:tel"].v @ prima) > 0.999)
    c3 = IS.impara(imp, y[3], ch, CARLO, cfg)
    verifica("una frase vicina la aggiorna (media mobile)", "sat:tel" in c3
             and imp["sat:tel"].n == 4 and float(imp["sat:tel"].v @ prima) < 0.99999)
    # file: andata e ritorno; le frasi in attesa no
    d = IS.scrivi(imp2) | IS.scrivi(imp)
    letti = IS.leggi(json.loads(json.dumps(d)))
    verifica("su disco e di nuovo in memoria, senza le frasi in attesa",
             set(letti) == {"sat:tel", "canale:telefono"}
             and float(letti["sat:tel"].v @ imp["sat:tel"].v) > 0.9999
             and float(letti["sat:tel"].seme @ imp["sat:tel"].seme) > 0.9999)
    verifica("un campo rovinato: nessuna impronta", IS.leggi({"sat:x": {"v": "no"}, 3: {}})
             == {} and IS.leggi(None) == {})
    # al più `speaker_impronte_max` satelliti
    imp3: dict = {}
    cfgm = cfg_modo("attivo", speaker_impronte_max=3, speaker_impronte_seme_frasi=1)
    for i in range(5):
        IS.impara(imp3, y[0], (f"sat:s{i}",), CARLO, cfgm)
    verifica("al più speaker_impronte_max satelliti per persona", len(imp3) == 3
             and "sat:s4" in imp3)


# ─────────────────────────── il ciclo ───────────────────────────

def prova_spento():
    reg, sc, ciclo, regole = ciclo_finto("spento")
    sicure_di_carlo(ciclo, sc)
    n, how, lv, v, t = riconosci(ciclo, sc, frase(carlo=0.444, luca=0.358, tel=0.75), 2.4)
    verifica("spento: nessuna impronta imparata, niente nel registro, il 15/10 resta ospite",
             not reg.users["Carlo"].impronte_satellite and "impronte_satellite" not in v
             and n is None and t.chiavi_impronte is None)


def prova_ombra():
    reg, sc, ciclo, regole = ciclo_finto("ombra")
    sicure_di_carlo(ciclo, sc, n=2)
    verifica("ombra: due frasi sicure, l'impronta non c'è ancora",
             not any(i.pronta for i in reg.users["Carlo"].impronte_satellite.values()))
    _n, _h, _l, v, _t = riconosci(ciclo, sc, frase(carlo=0.65, luca=0.12, tel=0.6, seme=102),
                                  3.0)
    verifica("ombra: alla terza nasce, e il registro lo dice", reg.users["Carlo"]
             .impronte_satellite["sat:telefono di prova"].pronta
             and v["impronte_satellite"].get("imparata") == ["sat:telefono di prova",
                                                             "canale:telefono"]
             and reg._da_salvare)
    # Il caso vero del 15/10
    n, how, lv, v, t = riconosci(ciclo, sc, frase(carlo=0.444, luca=0.358, tel=0.75), 2.4)
    b = v.get("impronte_satellite") or {}
    verifica("ombra, caso del 15/10: decide quella di oggi (ospite)", n is None
             and lv == "ospite" and v["punteggio"] == 0.444, str(v))
    verifica("ombra, caso del 15/10: con l'impronta del satellite sarebbe Carlo dalla voce",
             b.get("modo") == "ombra" and b["con"]["nome"] == "Carlo"
             and b["con"]["come"] == "voce" and b["con"].get("amministra")
             and b["con"]["fonte"] == "sat" and b["con"]["punteggio"] > 0.75
             and b["senza"]["nome"] is None, json.dumps(b))
    verifica("ombra: la decisione alternativa non lascia tracce (chi parla, zona grigia)",
             sc.current_speaker is None and sc.identified_by is None and not sc.from_session
             and sc.minore_vicino is None and t.voce_secondo[0] == "Luca")
    verifica("ombra: la frase rifiutata non insegna niente", "imparata" not in b)
    # Luca, che non ha ancora un'impronta del telefono, resta Luca
    n, how, lv, v, _t = riconosci(ciclo, sc, frase(carlo=0.12, luca=0.66, tel=0.6, seme=7), 3.0)
    verifica("ombra: una frase netta di Luca resta sua con e senza",
             n == "Luca" and v["impronte_satellite"]["con"]["nome"] == "Luca"
             and v["impronte_satellite"]["con"].get("minore"))
    # il riassunto di stato --turni (Luca e Carlo appena sentiti sarebbero compagnia)
    ciclo.compagnia.dimentica()
    turni = []
    for emb, vs in ((frase(carlo=0.444, luca=0.358, tel=0.75), 2.4),
                    (frase(carlo=0.399, luca=0.354, tel=0.75, seme=3), 2.0),
                    (frase(carlo=0.66, luca=0.1, tel=0.6, seme=4), 3.0)):
        riconosci(ciclo, sc, emb, vs)
        turni.append({"voce": ciclo.rec["voce"], "ascolto": {"satellite": "telefono di prova",
                                                             "canale": "telefono"}})
    r = IS.riassunto(turni)
    d = r["satelliti"]["telefono di prova"]
    verifica("stato --turni: due rifiutate riconosciute, nessuno scambio, una che insegna",
             (d["frasi"], d["recuperate"], d["perse"], d["scambi"], d["imparate"])
             == (3, 2, 0, 0, 1), str(d))
    tx = IS.testo(r)
    verifica("stato --turni: il testo, per satellite", "telefono di prova (ombra)" in tx
             and "rifiutate → riconosciute 2" in tx, tx)
    verifica("stato --turni: senza misura lo dice", "spento" in IS.testo(IS.riassunto([])))


def prova_attivo():
    reg, sc, ciclo, regole = ciclo_finto("attivo")
    sicure_di_carlo(ciclo, sc)
    n, how, lv, v, t = riconosci(ciclo, sc, frase(carlo=0.444, luca=0.358, tel=0.75), 2.4)
    b = v["impronte_satellite"]
    verifica("attivo, caso del 15/10: Carlo dalla voce, amministra", (n, how, lv) ==
             ("Carlo", "voce", "amministra") and v["punteggio"] > 0.75, f"{n} {how} {lv}")
    verifica("attivo: nel registro la decisione senza (ospite)", b["senza"]["nome"] is None
             and b["con"]["nome"] == "Carlo" and b["modo"] == "attivo")
    n2, _h, _l, v2, _t = riconosci(ciclo, sc, frase(carlo=0.399, luca=0.354, tel=0.75, seme=9),
                                   2.0)
    verifica("attivo: anche la seconda frase del 15/10", n2 == "Carlo")
    # un altro satellite non ha l'impronta del telefono: lì non cambia niente (canale diverso)
    studio = SimpleNamespace(remoto=True, started_at=0.0, canale="satellite",
                             satellite_nome="studio")
    ciclo.listener = studio
    n3, _h, _l, v3, _t = riconosci(ciclo, sc, frase(carlo=0.444, luca=0.358, tel=0.75), 2.4)
    verifica("attivo: sullo studio (altro canale) la frase del telefono resta ospite",
             n3 is None and v3["impronte_satellite"]["con"]["nome"] is None)
    # un altro telefono, nuovo: vale il ripiego sul canale
    ciclo.listener = SimpleNamespace(remoto=True, started_at=0.0, canale="telefono",
                                     satellite_nome="telefono nuovo")
    n4, _h, _l, v4, _t = riconosci(ciclo, sc, frase(carlo=0.444, luca=0.358, tel=0.75), 2.4)
    verifica("attivo: un telefono nuovo usa l'impronta del canale", n4 == "Carlo"
             and v4["impronte_satellite"]["con"]["fonte"] == "canale")
    # zona grigia, frase breve, compagnia: non insegnano
    ciclo.listener = Telefono()
    prima = {k: (i.n if i.pronta else -len(i.attesa))
             for k, i in reg.users["Carlo"].impronte_satellite.items()}
    riconosci(ciclo, sc, frase(carlo=0.47, luca=0.1, tel=0.0, seme=11), 2.5, in_session=True,
              prev="Carlo")                                      # zona grigia
    riconosci(ciclo, sc, frase(carlo=0.70, luca=0.1, tel=0.6, seme=12), 0.8)   # breve
    riconosci(ciclo, sc, frase(carlo=0.70, luca=0.1, tel=0.6, seme=13), 1.3)   # corta
    dopo = {k: (i.n if i.pronta else -len(i.attesa))
            for k, i in reg.users["Carlo"].impronte_satellite.items()}
    verifica("contrari: zona grigia e frasi corte non insegnano", prima == dopo, f"{prima} {dopo}")
    # Dal 18/10 (#147) il ciclo chiede lo stato e il cambio dalla stanza insieme
    ciclo.compagnia.osserva_con_stanza = lambda emb, vs, nome: ({"voci": 2, "prova": "profilo"},
                                                                None)
    riconosci(ciclo, sc, frase(carlo=0.70, luca=0.1, tel=0.6, seme=14), 3.0)
    dopo2 = {k: (i.n if i.pronta else -len(i.attesa))
             for k, i in reg.users["Carlo"].impronte_satellite.items()}
    verifica("contrario: in compagnia non insegna", dopo2 == prima, f"{prima} {dopo2}")


def prova_simmetria():
    """Il verso pericoloso: una frase debole del minore al telefono."""
    debole = frase(carlo=0.17 * 0.45, luca=0.45, tel=0.75, seme=50)
    reg, sc, ciclo, regole = ciclo_finto("attivo")
    sicure_di_carlo(ciclo, sc)
    regole.clear()
    n, how, lv, v, _t = riconosci(ciclo, sc, debole, 2.5)
    verifica("solo Carlo ha l'impronta del telefono: la frase di Luca va a Carlo, ma al più "
             "familiare (minore vicino)", n == "Carlo" and how == "conversazione"
             and lv == "familiare" and "amministra_minore_vicino" in regole
             and v["impronte_satellite"]["con"].get("amministra")
             and v["impronte_satellite"]["senza"]["nome"] in (None, "Luca"), f"{n} {how} {lv}")
    # simmetrico: anche Luca impara dal telefono (prima, senza dimenticare la compagnia)
    for i in range(4):
        riconosci(ciclo, sc, frase(carlo=0.12, luca=0.8, tel=0.35, seme=250 + i), 3.0)
    verifica("contrario: con Carlo sentito da poco (compagnia) Luca non impara",
             "sat:telefono di prova" not in reg.users["Luca"].impronte_satellite
             or not reg.users["Luca"].impronte_satellite["sat:telefono di prova"].pronta)
    sicure_di_luca(ciclo, sc)
    verifica("simmetria: anche il minore ha l'impronta del telefono",
             reg.users["Luca"].impronte_satellite["sat:telefono di prova"].pronta)
    n, how, lv, v, _t = riconosci(ciclo, sc, debole, 2.5)
    verifica("simmetria: con le due impronte la frase debole torna a Luca", n == "Luca"
             and lv == "familiare", f"{n} {how} {lv}")
    # e il caso del 15/10 resta di Carlo anche con l'impronta del telefono di Luca
    n, how, lv, _v, _t = riconosci(ciclo, sc, frase(carlo=0.444, luca=0.358, tel=0.75), 2.4)
    verifica("simmetria: il caso del 15/10 resta di Carlo", (n, lv) == ("Carlo", "amministra"),
             f"{n} {how} {lv}")
    # piu_protetto sui punteggi nuovi: Carlo e Luca vicini con le impronte del telefono
    vicina = frase(carlo=0.38, luca=0.42, tel=0.40, seme=60)
    regole.clear()
    n, how, lv, v, _t = riconosci(ciclo, sc, vicina, 2.5)
    pc = reg.punteggio("Carlo", vicina, IS.chiavi("telefono di prova", "telefono"))
    pl = reg.punteggio("Luca", vicina, IS.chiavi("telefono di prova", "telefono"))
    verifica("protezione sui punteggi nuovi: incerta fra Carlo e Luca vale Luca",
             abs(pc - pl) < 0.05 and n == "Luca" and "minore_piu_protetto" in regole,
             f"{pc:.3f} {pl:.3f} {n} {how}")
    # in ombra con le stesse impronte la decisione resta quella senza
    reg_o, sc_o, ciclo_o, _r = ciclo_finto("ombra")
    sicure_di_carlo(ciclo_o, sc_o)
    n, how, lv, v, _t = riconosci(ciclo_o, sc_o, debole, 2.5)
    verifica("ombra: lo scambio Luca → Carlo si vede nel registro e non decide",
             n != "Carlo" and v["impronte_satellite"]["con"]["nome"] == "Carlo")


def prova_voci_famiglia_uguali():
    """I casi del 07/10 (prova_voci_famiglia) con le impronte in ombra e attive: uguali."""
    import io
    import contextlib
    import prova_voci_famiglia as VF
    originale = VF.Reg.__init__
    for modo in ("ombra", "attivo"):
        def init(self, _m=modo):
            originale(self)
            self.cfg.speaker_impronte_satellite = _m
        VF.Reg.__init__ = init
        VF.errori = 0
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                VF.prova_proprietario()
                VF.prova_casi()
                VF.prova_verso_pericoloso()
                VF.prova_conferma_breve()
                VF.prova_continuita()
                VF.prova_frasi()
                VF.prova_azione_in_sospeso()
        finally:
            VF.Reg.__init__ = originale
        righe = [r for r in out.getvalue().splitlines() if r.startswith("ERR")]
        verifica(f"i casi del 07/10 (prova_voci_famiglia) uguali in {modo}",
                 VF.errori == 0 and not righe, "; ".join(righe[:3]))


# ─────────────────────────── tenuta ───────────────────────────

def prova_tenuta():
    reg, sc, ciclo, _r = ciclo_finto("ombra")
    sicure_di_carlo(ciclo, sc)
    sicure_di_luca(ciclo, sc)
    carlo = reg.users["Carlo"]
    d = carlo.to_dict()
    verifica("speakers.json: le impronte del satellite con il profilo",
             set(d.get("impronte_satellite") or {}) == {"sat:telefono di prova",
                                                        "canale:telefono"})
    p2 = UserProfile.from_dict(json.loads(json.dumps(d)), None)
    verifica("riletto: le stesse impronte", float(
        p2.impronte_satellite["sat:telefono di prova"].v
        @ carlo.impronte_satellite["sat:telefono di prova"].v) > 0.9999)
    d0 = dict(d)
    d0.pop("impronte_satellite")
    verifica("un profilo di prima, senza il campo: nessuna",
             UserProfile.from_dict(d0, None).impronte_satellite == {})
    verifica("un altro modello dell'impronta: via anche queste",
             UserProfile.from_dict(json.loads(json.dumps(d)), "altro").impronte_satellite == {})
    verifica("Bianca, mai sentita al telefono: niente campo",
             "impronte_satellite" not in reg.users["Bianca"].to_dict())
    reg.rename("Carlo", "Carlo Rossi")
    verifica("rinomina: le impronte restano con la persona",
             reg.users["Carlo Rossi"].impronte_satellite)
    reg.rename("Carlo Rossi", "Carlo")
    n = reg.svuota_impronte_satellite("luca-id")
    verifica("svuota di una persona: solo le sue", n == 2 and not reg.users["Luca"]
             .impronte_satellite and reg.users["Carlo"].impronte_satellite)
    n = reg.svuota_impronte_satellite(None)
    verifica("svuota di tutti", n == 2 and not reg.users["Carlo"].impronte_satellite)
    sicure_di_carlo(ciclo, sc)
    reg.set_voiceprint = SpeakerRegistry.set_voiceprint.__get__(reg)
    reg.embedder = SimpleNamespace(model_name=None)
    reg.set_voiceprint("Carlo", [CARLO, CARLO])
    verifica("una nuova registrazione della voce le toglie",
             reg.users["Carlo"].impronte_satellite == {})
    # Da terminale: il file e la copia
    with tempfile.TemporaryDirectory() as cart:
        f = os.path.join(cart, "speakers.json")
        sicure_di_carlo(ciclo, sc)
        dati = [u.to_dict() for u in reg.users.values()]
        for nome in (f, f + ".bak"):
            with open(nome, "w", encoding="utf-8") as fh:
                json.dump(dati, fh)
        n = IS.svuota_file(f, "carlo-id")
        letti = [json.load(open(x, encoding="utf-8")) for x in (f, f + ".bak")]
        verifica("da terminale: via dal file e dalla copia .bak, il resto intatto",
                 n == 2 and all("impronte_satellite" not in u for x in letti for u in x)
                 and all(u.get("voiceprint") for x in letti for u in x))
    # conserva.svuota dal processo
    from calliope import conserva as conserva_mod
    with tempfile.TemporaryDirectory() as cart:
        sicure_di_carlo(ciclo, sc)
        cfg = cfg_modo("ombra", turn_log_dir=cart, conoscenti_file=os.path.join(cart, "k.json"),
                       memory_db=os.path.join(cart, "m.db"))
        c = conserva_mod.Conservazione(cfg, reg, log=lambda m: None)
        r = c.svuota("carlo-id", "Carlo")
        verifica("calliope conserva --svuota --persona: anche le impronte per satellite",
                 r.get("impronte_satellite") == 2 and not reg.users["Carlo"].impronte_satellite,
                 str(r))


# ─────────────────────────── conoscenti ───────────────────────────

def prova_conoscenti():
    with tempfile.TemporaryDirectory() as cart:
        reg, sc, ciclo, regole = ciclo_finto("attivo", stanza_conoscenti=True)
        cfg = reg.cfg
        con = con_mod.Conoscenti(cfg, path=os.path.join(cart, "conoscenti.json"),
                                 registry=reg, log=lambda m: None)
        k = con_mod.Conoscente("marco-id", "Marco", "Neri", "collega di Carlo", MARCO.copy(),
                               None, "2026-10-15", time.time())
        con._conoscenti[k.id] = k
        con.salva()
        ciclo.s.stanza = SimpleNamespace(conoscenti=con)
        for i in range(4):
            riconosci(ciclo, sc, frase(marco=0.66, carlo=0.05, tel=0.6, seme=300 + i), 3.0)
        verifica("conoscente: impara l'impronta del telefono dalle frasi sicure",
                 k.impronte_satellite.get("sat:telefono di prova") is not None
                 and k.impronte_satellite["sat:telefono di prova"].pronta)
        debole = frase(marco=0.42, carlo=0.05, tel=0.78, seme=320)
        n, how, lv, v, _t = riconosci(ciclo, sc, debole, 2.5)
        b = v.get("impronte_satellite") or {}
        verifica("conoscente al telefono: riconosciuto con l'impronta del satellite, ospite",
                 n is None and lv == "ospite" and v.get("conoscente") and v.get("id") == "marco-id"
                 and b.get("con", {}).get("conoscente") == "marco-id"
                 and not b.get("senza", {}).get("conoscente"), json.dumps(v))
        # contrari: frase corta e in compagnia non insegnano
        prima = k.impronte_satellite["sat:telefono di prova"].n
        riconosci(ciclo, sc, frase(marco=0.70, carlo=0.05, tel=0.6, seme=330), 1.2)
        verifica("contrario: la frase corta del conoscente non insegna",
                 k.impronte_satellite["sat:telefono di prova"].n == prima)
        # sul file e riletto
        con.salva()
        con2 = con_mod.Conoscenti(cfg, path=os.path.join(cart, "conoscenti.json"),
                                  registry=reg, log=lambda m: None)
        verifica("conoscente: le impronte per satellite nel suo file",
                 con2.per_id("marco-id").impronte_satellite.get("sat:telefono di prova")
                 is not None)
        # promozione e ritorno: le impronte seguono la persona
        reg.find = SpeakerRegistry.find.__get__(reg)
        prof = con.promuovi("marco-id", "Marco Neri")
        verifica("promosso a familiare: le impronte per satellite con lui",
                 prof.impronte_satellite.get("sat:telefono di prova") is not None
                 and "impronte_satellite" in prof.to_dict())
        c2 = con.declassa(prof)
        verifica("di nuovo conoscente: le impronte tornano con lui",
                 c2.impronte_satellite.get("sat:telefono di prova") is not None
                 and "Marco Neri" not in reg.users)
        verifica("svuota del conoscente: via le impronte, l'impronta salvata resta",
                 con.svuota_impronte_satellite("marco-id") == 2
                 and con.per_id("marco-id").impronta is not None
                 and not con.per_id("marco-id").impronte_satellite)
        for i in range(4):
            riconosci(ciclo, sc, frase(marco=0.66, carlo=0.05, tel=0.6, seme=400 + i), 3.0)
        con.dimentica("marco-id")
        testo_file = open(os.path.join(cart, "conoscenti.json"), encoding="utf-8").read()
        verifica("«dimentica»: via con il conoscente, anche dal file",
                 con.per_id("marco-id") is None and "impronte_satellite" not in testo_file)


def prova_config():
    from calliope.config import SEZIONI
    voci = [v for s in SEZIONI.values() for v in s]
    nuovi = [f for f in vars(Config()) if f.startswith("speaker_impronte")]
    verifica("configurazione: i campi nuovi nella sezione chi_parla",
             len(nuovi) == 8 and all(f in SEZIONI["chi_parla"] for f in nuovi)
             and all(voci.count(f) == 1 for f in nuovi), str(nuovi))
    testo = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "calliope.yaml"), encoding="utf-8").read()
    verifica("calliope.yaml rigenerato: spento di serie",
             "speaker_impronte_satellite: spento" in testo)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    print("── il modulo ──")
    prova_modulo()
    print("── spento, ombra, attivo ──")
    prova_spento()
    prova_ombra()
    prova_attivo()
    print("── simmetria e protezioni ──")
    prova_simmetria()
    prova_voci_famiglia_uguali()
    print("── tenuta ──")
    prova_tenuta()
    print("── conoscenti ──")
    prova_conoscenti()
    prova_config()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    sys.exit(1 if errori else 0)
