"""
Prova a secco dell'ospite dove un minore ha parlato da poco (16/10/2026, issue #102,
`minori_ospite_vicino`). Caso vero del 15/10 sera: una bambina appena registrata (impronta da 5
frasi corte) presa 6 volte per ospite, con punteggi 0,32–0,45 sul suo profilo (sotto la zona
grigia di `minori.piu_protetto`): risposte da adulto, senza il modo di parlare per la sua età.
Nomi di fantasia: Carlo amministra, Luca è il minore (le impronte di prova_voci_famiglia), Ada una
bambina piccola.

- Ciclo: un minore sentito 2 minuti fa su questa corsia → la frase d'ospite porta il suo nome in
  `minore_ospite` (non cambia chi parla né il livello); tra due minori il più protetto. Contrari:
  nessun minore negli ultimi `minori_avviso_privato_s`, un altro satellite (un'altra corsia), una
  voce riconosciuta, un conoscente, l'interruttore spento, la finestra a 0.
- Brain: nei dati del turno dell'ospite il modo di parlare della fascia, senza il nome e l'età
  precisa, con la regola `ospite_con_minore`; contrario: senza `minore_ospite` come prima.
- `minori.parla_minore` vale anche per l'ospite vicino al minore (con un minore parla il
  modello, non la frase pronta del tool); contrario: un ospite senza minori.

Ogni caso principale fallisce sulla versione di prima (9d4075e).
"""

import datetime
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prova_compagnia import ciclo_finto, frase
from prova_voci_famiglia import Job

from calliope import minori
from calliope.brain import Brain
from calliope.ciclo import Turno
from calliope.speaker_id import UserProfile

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""),
          flush=True)


def _anni(n: int) -> str:
    return (datetime.date.today() - datetime.timedelta(days=int(n * 365.25) + 30)).isoformat()


def casa(eta_luca: int = 8):
    """Il ciclo finto di una corsia, con Luca di `eta_luca` anni."""
    reg, sc, ciclo, regole = ciclo_finto()
    reg.users["Luca"].nascita = _anni(eta_luca)
    return reg, sc, ciclo, regole


def frase_di(ciclo, sc, emb, voiced_s=2.5):
    """Una frase intera dal ciclo (_chi_parla): chi parla e il segno per l'ospite."""
    t = Turno(text="Mi racconti una storia?", voiced_s=voiced_s, emb_job=Job(emb),
              prev_how=None)
    sc.current_speaker = None
    ciclo.rec = {}
    ciclo._chi_parla(t)
    return t.speaker_name, sc.current_level, getattr(sc, "minore_ospite", None)


def sentito(ciclo, pid, secondi_fa):
    ciclo._minori_sentiti[pid] = time.monotonic() - secondi_fa


# La frase del caso vero: 0,38 sulla bambina (sotto la zona grigia 0,42), 0,40 su un altro profilo
OSPITE_DEBOLE = dict(luca=0.38, carlo=0.40)


def prova_ciclo():
    reg, sc, ciclo, regole = casa()
    sentito(ciclo, "luca-id", 120)
    nome, livello, mo = frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    verifica("caso vero: minore sentito 2 minuti fa, la sua voce sotto la zona grigia → ospite "
             "con minore_ospite = Luca", nome is None and livello == "ospite" and mo == "Luca",
             f"{nome} {livello} {mo}")
    verifica("…e minori.piu_protetto non l'aveva data a lui (la causa)",
             "minore_piu_protetto" not in regole, str(regole))
    nome, livello, mo = frase_di(ciclo, sc, frase(carlo=0.10, amico=0.6))
    verifica("un ospite adulto vero, nello stesso momento → anche lui (scelta prudente di serie)",
             nome is None and mo == "Luca", f"{nome} {mo}")

    # Contrario: nessun minore negli ultimi minori_avviso_privato_s
    reg, sc, ciclo, regole = casa()
    sentito(ciclo, "luca-id", reg.cfg.minori_avviso_privato_s + 1)
    nome, livello, mo = frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    verifica("contrario: minore sentito oltre la finestra → niente segno",
             nome is None and mo is None, f"{nome} {mo}")
    ciclo._minori_sentiti.clear()
    nome, livello, mo = frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    verifica("contrario: nessun minore sentito → niente segno", mo is None, f"{mo}")

    # Contrario: il minore ha parlato su un altro satellite (un'altra corsia, un altro ciclo)
    reg, sc, ciclo, regole = casa()
    _r2, _sc2, altro, _reg2 = casa()
    sentito(altro, "luca-id", 60)
    nome, livello, mo = frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    verifica("contrario: minore sentito su un altro satellite → niente segno", mo is None,
             f"{mo}")

    # Contrario: una voce riconosciuta (Carlo sopra soglia)
    reg, sc, ciclo, regole = casa()
    sentito(ciclo, "luca-id", 60)
    nome, livello, mo = frase_di(ciclo, sc, frase(carlo=0.72, luca=0.2))
    verifica("contrario: Carlo riconosciuto dalla voce → niente segno",
             nome == "Carlo" and mo is None, f"{nome} {mo}")
    # Il minore stesso riconosciuto: ha già il suo preset
    nome, livello, mo = frase_di(ciclo, sc, frase(luca=0.72, carlo=0.2))
    verifica("contrario: Luca riconosciuto → è lui, niente segno da ospite",
             nome == "Luca" and mo is None, f"{nome} {mo}")

    # Contrario: interruttore spento, finestra a 0
    reg, sc, ciclo, regole = casa()
    sentito(ciclo, "luca-id", 60)
    reg.cfg.minori_ospite_vicino = False
    nome, livello, mo = frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    verifica("contrario: minori_ospite_vicino: false → come prima", mo is None, f"{mo}")
    reg.cfg.minori_ospite_vicino = True
    reg.cfg.minori_avviso_privato_s = 0.0
    nome, livello, mo = frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    verifica("contrario: minori_avviso_privato_s 0 → niente finestra, niente segno", mo is None)

    # Contrario: un conoscente (riconosciuto come persona di fuori casa)
    reg, sc, ciclo, regole = casa()
    sentito(ciclo, "luca-id", 60)
    per_ospite = getattr(ciclo, "_minore_per_ospite", lambda _n: None)
    sc.conoscente = {"id": "k1", "nome": "Gino"}
    verifica("contrario: un conoscente → niente segno", per_ospite(None) is None)
    sc.conoscente = None
    verifica("…e lo stesso ospite senza conoscente → Luca", per_ospite(None) == "Luca")

    # Due minori sentiti: vale il più protetto (la più giovane)
    reg, sc, ciclo, regole = casa(eta_luca=12)
    reg.users["Ada"] = UserProfile(name="Ada", voiceprint=None, nascita=_anni(5),
                                   tutori=["carlo-id"], id="ada-id")
    sentito(ciclo, "luca-id", 30)
    sentito(ciclo, "ada-id", 300)
    nome, livello, mo = frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    verifica("due minori sentiti → il più protetto (Ada, 5 anni)", mo == "Ada", f"{mo}")


class _Voci:
    def __init__(self, reg):
        self.reg = reg

    def get(self, n):
        return self.reg.get(n)


def brain_di(sc, reg):
    b = Brain.__new__(Brain)
    b.cfg, b.last_rules = reg.cfg, []
    b.tool_ctx = type("T", (), {"speaker_ctx": sc, "speakers": _Voci(reg)})()
    return b


def prova_brain():
    reg, sc, ciclo, regole = casa(eta_luca=8)
    sentito(ciclo, "luca-id", 120)
    frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    b = brain_di(sc, reg)
    msg = b._turn_context()[0]["content"]
    verifica("Brain: l'ospite vicino al minore ha il modo di parlare della fascia (7–10 anni)",
             "un ospite" in msg and "forse un minorenne (7–10 anni" in msg
             and "parole semplici" in msg and "niente contenuti per adulti" in msg
             and "ospite_con_minore" in b.last_rules, msg)
    verifica("…senza il nome, l'età precisa, i compiti", "Luca" not in msg
             and "8 anni" not in msg and "compiti" not in msg and "minore_preset"
             not in b.last_rules, msg)
    # Contrario: nessun minore vicino
    sc.minore_ospite = None
    b = brain_di(sc, reg)
    msg = b._turn_context()[0]["content"]
    verifica("contrario Brain: ospite senza minori → come prima", "minorenne" not in msg
             and "ospite_con_minore" not in b.last_rules
             and "persona: un ospite, non riconosciuto dalla voce." in msg, msg)
    # Contrario: il nome di un adulto in minore_ospite (non può capitare, ma niente nota)
    sc.minore_ospite = "Carlo"
    b = brain_di(sc, reg)
    verifica("contrario Brain: un adulto non dà la nota",
             "minorenne" not in b._turn_context()[0]["content"])
    # Il minore vero riconosciuto: il suo preset di sempre, non quello da ospite
    sc.minore_ospite = None
    sc.current_speaker, sc.identified_by = "Luca", "voce"
    b = brain_di(sc, reg)
    msg = b._turn_context()[0]["content"]
    verifica("contrario Brain: Luca riconosciuto → il suo preset (minore_preset), non la nota "
             "da ospite", "minore_preset" in b.last_rules and "ospite_con_minore"
             not in b.last_rules, msg)


def prova_parla_minore():
    reg, sc, ciclo, regole = casa()
    sentito(ciclo, "luca-id", 120)
    frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    verifica("parla_minore: l'ospite vicino al minore vale come nel dubbio con un minore",
             minori.parla_minore(sc, reg) is True)
    sc.minore_ospite = None
    verifica("contrario parla_minore: un ospite senza minori", minori.parla_minore(sc, reg)
             is False)


def prova_dato():
    reg, sc, ciclo, regole = casa(eta_luca=5)
    t = getattr(minori, "dato_ospite", lambda _p: "")(reg.get("Luca"))
    verifica("dato_ospite: piccoli, frasi cortissime", "meno di 7 anni" in t
             and "frasi cortissime" in t and "Luca" not in t, t)
    verifica("contrario dato_ospite: un adulto → vuoto", getattr(minori, "dato_ospite", lambda _p: "")(reg.get("Carlo"))
             == "")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    for nome, f in (("ciclo: il segno per l'ospite", prova_ciclo),
                    ("Brain: i dati del turno", prova_brain),
                    ("parla_minore", prova_parla_minore),
                    ("dato_ospite", prova_dato)):
        print(f"── {nome} ──", flush=True)
        f()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    sys.exit(1 if errori else 0)
