"""
Prova a secco dell'ospite dove un minore ha parlato da poco (16/10/2026, issue #102,
`minori_ospite_vicino`). Caso vero del 15/10 sera: una bambina appena registrata (impronta da 5
frasi corte) presa 6 volte per ospite, con punteggi 0,32–0,45 sul suo profilo (sotto la zona
grigia di `minori.piu_protetto`): risposte da adulto, senza il modo di parlare per la sua età.
Nomi di fantasia: Carlo amministra, Luca è il minore (le impronte di prova_voci_famiglia), Ada una
bambina piccola.

- Ciclo: un minore sentito 2 minuti fa su questa corsia → la frase d'ospite porta il suo nome in
  `minore_ospite` (non cambia chi parla né il livello); tra due minori il più protetto; un ospite
  adulto con la voce vicina al minore (tra i primi due profili o ≥ 0,30 sul suo) anche lui; lo
  scritto da uno schermo di stanza (senza voce) anche lui. Nel turno `minore_sentito_s` (secondi,
  senza nomi), anche quando la nota non scatta. Contrari: un adulto lontano dal profilo del minore
  (revisione della PR #116), nessun minore negli ultimi `minori_ospite_vicino_s`, un altro
  satellite, una voce riconosciuta, un conoscente, l'interruttore spento, la finestra a 0.
- Brain: nei dati del turno dell'ospite «potrebbe essere un minorenne: nel caso …» con il tono
  della fascia e la regola `ospite_con_minore`; nessun fatto sul minore (nome, età, fascia detta,
  «ha parlato qui», compiti); contrario: senza `minore_ospite` come prima.
- `minori.parla_minore` vale anche per l'ospite vicino al minore; contrario: ospite senza minori.
- `calliope stato --turni`: turni d'ospite con un minore sentito, con e senza la nota.

Ogni caso principale fallisce sulla versione di prima (main 3bbc674: 17 errori).
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


def finestra(cfg, secondi):
    cfg.minori_ospite_vicino_s = secondi


# La frase del caso vero: 0,38 sulla bambina (sotto la zona grigia 0,42), 0,40 su un altro profilo
OSPITE_DEBOLE = dict(luca=0.38, carlo=0.40)
# Un adulto vicino al minore: 0,31 su Luca (sopra 0,30), più vicino a Bianca e a Carlo
ADULTO_VICINO = dict(luca=0.31, carlo=0.33, bianca=0.36, amico=0.5)
# Un adulto lontano: Luca terzo dei tre profili e a 0,05
ADULTO_LONTANO = dict(carlo=0.30, bianca=0.35, luca=0.05, amico=0.5)


def prova_ciclo():
    reg, sc, ciclo, regole = casa()
    sentito(ciclo, "luca-id", 120)
    nome, livello, mo = frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    verifica("caso vero: minore sentito 2 minuti fa, la sua voce sotto la zona grigia → ospite "
             "con minore_ospite = Luca", nome is None and livello == "ospite" and mo == "Luca",
             f"{nome} {livello} {mo}")
    verifica("…e minori.piu_protetto non l'aveva data a lui (la causa)",
             "minore_piu_protetto" not in regole, str(regole))
    sentito_s = ciclo.rec.get("minore_sentito_s")
    verifica("…nel turno minore_sentito_s (secondi, senza nomi)",
             isinstance(sentito_s, float) and 119 <= sentito_s <= 125, str(sentito_s))
    nome, livello, mo = frase_di(ciclo, sc, frase(**ADULTO_VICINO))
    verifica("un ospite adulto con la voce vicina al minore (0,31 sul suo profilo) → anche lui "
             "(scelta prudente di serie)", nome is None and mo == "Luca", f"{nome} {mo}")
    nome, livello, mo = frase_di(ciclo, sc, frase(**ADULTO_LONTANO))
    verifica("contrario: un ospite adulto lontano dal profilo del minore (terzo, 0,05) → niente "
             "nota", nome is None and mo is None, f"{nome} {mo}")
    verifica("…ma il turno conta il minore sentito (per la misura)",
             ciclo.rec.get("minore_sentito_s") is not None, str(ciclo.rec))
    reg.cfg.minori_ospite_vicino_punteggio = 0.0
    nome, livello, mo = frase_di(ciclo, sc, frase(**ADULTO_LONTANO))
    verifica("…con minori_ospite_vicino_punteggio 0 anche lui", mo == "Luca", f"{mo}")
    reg.cfg.minori_ospite_vicino_punteggio = 0.30

    # Lo scritto da uno schermo di stanza: nessuna voce da confrontare, vale la prudenza
    per_ospite = getattr(ciclo, "_minore_per_ospite", lambda _t: None)
    ciclo.rec = {}
    verifica("scritto da uno schermo di stanza (senza voce) → Luca",
             per_ospite(Turno(text="Ciao")) == "Luca")

    # Contrario: nessun minore negli ultimi minori_ospite_vicino_s
    reg, sc, ciclo, regole = casa()
    sentito(ciclo, "luca-id", reg.cfg.minori_avviso_privato_s + 1)
    nome, livello, mo = frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    verifica("contrario: minore sentito oltre la finestra → niente segno né minore_sentito_s",
             nome is None and mo is None and "minore_sentito_s" not in ciclo.rec, f"{nome} {mo}")
    ciclo._minori_sentiti.clear()
    nome, livello, mo = frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    verifica("contrario: nessun minore sentito → niente segno", mo is None, f"{mo}")

    # La finestra è sua, non quella degli avvisi
    reg, sc, ciclo, regole = casa()
    sentito(ciclo, "luca-id", 120)
    reg.cfg.minori_avviso_privato_s = 0.0
    finestra(reg.cfg, 60.0)
    nome, livello, mo = frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    verifica("contrario: minori_ospite_vicino_s 60 (gli avvisi a 0) e minore sentito 2 minuti fa "
             "→ niente segno", mo is None, f"{mo}")
    finestra(reg.cfg, 600.0)
    nome, livello, mo = frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    verifica("…minori_ospite_vicino_s 600 con gli avvisi a 0 → Luca", mo == "Luca", f"{mo}")

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
    verifica("contrario: Carlo riconosciuto dalla voce → niente segno né minore_sentito_s",
             nome == "Carlo" and mo is None and "minore_sentito_s" not in ciclo.rec,
             f"{nome} {mo}")
    nome, livello, mo = frase_di(ciclo, sc, frase(luca=0.72, carlo=0.2))
    verifica("contrario: Luca riconosciuto → è lui, niente segno da ospite",
             nome == "Luca" and mo is None, f"{nome} {mo}")

    # Contrario: interruttore spento, finestra a 0
    reg, sc, ciclo, regole = casa()
    sentito(ciclo, "luca-id", 60)
    reg.cfg.minori_ospite_vicino = False
    nome, livello, mo = frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    verifica("contrario: minori_ospite_vicino: false → come prima (la misura resta)",
             mo is None and ciclo.rec.get("minore_sentito_s") is not None, f"{mo}")
    reg.cfg.minori_ospite_vicino = True
    finestra(reg.cfg, 0.0)
    nome, livello, mo = frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    verifica("contrario: minori_ospite_vicino_s 0 → niente finestra, niente segno", mo is None)

    # Contrario: un conoscente (riconosciuto come persona di fuori casa)
    reg, sc, ciclo, regole = casa()
    sentito(ciclo, "luca-id", 60)
    per_ospite = getattr(ciclo, "_minore_per_ospite", lambda _t: None)
    sc.conoscente = {"id": "k1", "nome": "Gino"}
    verifica("contrario: un conoscente → niente segno", per_ospite(Turno(text="Ciao")) is None)
    sc.conoscente = None
    verifica("…e lo stesso ospite senza conoscente → Luca", per_ospite(Turno(text="Ciao"))
             == "Luca")

    # Due minori sentiti: vale il più protetto (la più giovane)
    reg, sc, ciclo, regole = casa(eta_luca=12)
    reg.users["Ada"] = UserProfile(name="Ada", voiceprint=None, nascita=_anni(5),
                                   tutori=["carlo-id"], id="ada-id")
    sentito(ciclo, "luca-id", 30)
    sentito(ciclo, "ada-id", 300)
    ciclo.rec = {}
    verifica("due minori sentiti (scritto, senza voce) → il più protetto (Ada, 5 anni)",
             getattr(ciclo, "_minore_per_ospite", lambda _t: None)(Turno(text="Ciao")) == "Ada")
    nome, livello, mo = frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    verifica("…con la voce vicina solo a Luca (Ada senza impronta) → Luca", mo == "Luca",
             f"{mo}")


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
    reg.users["Luca"].gender = "f"
    sentito(ciclo, "luca-id", 120)
    frase_di(ciclo, sc, frase(**OSPITE_DEBOLE))
    b = brain_di(sc, reg)
    msg = b._turn_context()[0]["content"]
    verifica("Brain: l'ospite vicino al minore ha «potrebbe essere un minorenne: nel caso» e il "
             "tono della fascia", "un ospite" in msg
             and "potrebbe essere un minorenne: nel caso un bambino delle elementari" in msg
             and "niente contenuti per adulti" in msg
             and "ospite_con_minore" in b.last_rules, msg)
    verifica("contrario: nessun fatto sul minore (nome, età, fascia detta, «ha parlato qui», "
             "genere, compiti)",
             not any(x in msg for x in ("Luca", "8 anni", "7–10", "anni", "ha parlato",
                                        "satellite", "bambina", "compiti"))
             and "minore_preset" not in b.last_rules, msg)
    sc.minore_ospite = None
    b = brain_di(sc, reg)
    msg = b._turn_context()[0]["content"]
    verifica("contrario Brain: ospite senza minori → come prima", "minorenne" not in msg
             and "ospite_con_minore" not in b.last_rules
             and "persona: un ospite, non riconosciuto dalla voce." in msg, msg)
    sc.minore_ospite = "Carlo"
    b = brain_di(sc, reg)
    verifica("contrario Brain: un adulto non dà la nota",
             "minorenne" not in b._turn_context()[0]["content"])
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
    verifica("dato_ospite: piccoli, frasi cortissime, nessun fatto sul minore",
             t.startswith("potrebbe essere un minorenne: nel caso un bambino piccolo")
             and "frasi cortissime" in t and "Luca" not in t and "anni" not in t, t)
    verifica("contrario dato_ospite: un adulto → vuoto",
             getattr(minori, "dato_ospite", lambda _p: "")(reg.get("Carlo")) == "")


def prova_stato():
    turni = [
        {"inizio": "2026-10-16T20:06:49", "livello": "ospite", "minore_sentito_s": 120.0,
         "regole": ["ospite_con_minore"]},
        {"inizio": "2026-10-16T20:11:29", "livello": "ospite", "minore_sentito_s": 400.0,
         "regole": []},
        {"inizio": "2026-10-16T20:30:00", "livello": "ospite", "regole": []},
        {"inizio": "2026-10-16T20:31:00", "livello": "familiare", "regole": []},
    ]
    r = getattr(minori, "riassunto_ospite", lambda _t: {})(turni)
    verifica("stato --turni: 2 turni d'ospite con un minore sentito, 1 con la nota",
             r == {"2026-10-16": {"turni": 2, "con_nota": 1}}, str(r))
    testo = getattr(minori, "testo_ospite", lambda _r: "")(r)
    verifica("…la riga dice con e senza la nota", "con la nota per i minori 1, senza 1" in testo,
             testo)
    verifica("contrario: nessun turno con un minore sentito → riga vuota",
             getattr(minori, "riassunto_ospite", lambda _t: None)(turni[2:]) == {})


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    for nome, f in (("ciclo: il segno per l'ospite", prova_ciclo),
                    ("Brain: i dati del turno", prova_brain),
                    ("parla_minore", prova_parla_minore),
                    ("dato_ospite", prova_dato),
                    ("stato --turni", prova_stato)):
        print(f"── {nome} ──", flush=True)
        f()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    sys.exit(1 if errori else 0)
