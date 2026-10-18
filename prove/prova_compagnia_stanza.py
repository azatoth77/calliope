"""
Prova a secco della compagnia dai segmenti della stanza (18/10/2026, issue #147, caso vero del
17/10: telefono in cucina, chi amministra con il minore e quattro voci sconosciute sentite dalla
stanza, le sue domande «non in compagnia»; revisioni della PR #161). calliope/compagnia.py
(`osserva_stanza`, `stato_turno`, `stato_stanza`, `compagnia_da_stanza`), calliope/ciclo.py
(`_tutela_minori`, `_pericolo_vale`, il registro in ombra), calliope/stanza/ascolto.py
(`su_voce`), calliope/corsie.py (`corsia_del_satellite`), calliope/main.py
(`Avvio._compagnia_dalla_stanza`). Impronte sintetiche come prova_compagnia, nomi di fantasia:
Carlo amministra, Luca è il minore, Bianca un'adulta di casa; Amico e Ospite voci senza profilo.

- Ombra (di serie): la stanza non cambia niente per la voce; nel registro del turno lo stato con
  la stanza (`voce.compagnia_stanza`), le regole e la frase che sarebbe stata scartata;
  `calliope stato --turni` le conta.
- Attiva, il caso: segmenti di una voce sconosciuta, poi la frase di Carlo → in compagnia con una
  voce sconosciuta, `da_stanza`, finestra senza il nome chiusa.
- La regola rigida: sconosciuta solo sotto 0,20 su tutti i profili di casa (il familiare non
  riconosciuto, la zona grigia e la frase del turno di Carlo non riconosciuta non lo sono).
- `da_stanza` solo se cambia l'effetto; solo verso la prudenza (l'assorbimento, niente
  continuità).
- I minori: con un minore qui o un cancello aperto vale lo stato del turno (la frase senza il nome
  e la risposta al cancello passano); il giudizio «non rivolta» non spegne il pericolo se la
  compagnia viene solo dalla stanza.
- Il costo: lo stato tenuto da parte; l'istante nel futuro con una seconda voce.
- Corsie, la stanza vera, solo in memoria (0031), stato --turni; i contrari.
"""

import json
import os
import sys
import tempfile
import time
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import prova_voci_famiglia as VF
from prova_compagnia import Ascoltatore, Orologio, frase, riconosci
from prova_voci_famiglia import VoceFinta

from calliope import compagnia as compagnia_mod
from calliope import corsie as corsie_mod
from calliope import rivolta as rivolta_mod
from calliope.ciclo import _FINE, Turno

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""),
          flush=True)


def prova(nome, f):
    """Una sezione: un'eccezione (su main manca `osserva_stanza`) è un errore, non un arresto."""
    print(f"── {nome} ──", flush=True)
    try:
        f()
    except Exception as e:  # noqa: BLE001
        verifica(f"{nome}: senza eccezioni", False, f"{type(e).__name__}: {e}")


def ciclo_finto(modo="attiva", minore=False):
    """Il ciclo di prova_voci_famiglia. Con `minore` Luca è il minore di casa (la tutela vale
    sempre, 18/10); senza, è un adulto e in casa non ci sono minori."""
    reg, sc, ciclo, regole = VF.ciclo_finto()
    reg.cfg.compagnia_da_stanza = modo
    if not minore:
        reg.users["Luca"].nascita, reg.users["Luca"].tutori = None, []
    ciclo.speaker = VoceFinta()
    ciclo.listener = Ascoltatore()
    orol = Orologio()
    ciclo.compagnia.orologio = orol
    return reg, sc, ciclo, regole, orol


def dalla_stanza(ciclo, orol, emb, voce_s, nome=None, fa_s=0.0, dopo_s=5.0, **kw):
    """Un segmento della stanza detto `fa_s` secondi prima di adesso (dopo `dopo_s`)."""
    orol.t += dopo_s
    return ciclo.compagnia.osserva_stanza(emb, voce_s, nome, orol.t - fa_s, **kw)


def turno(ciclo, sc, orol, emb, voce_s, dopo_s=5.0, **kw):
    orol.t += dopo_s
    return riconosci(ciclo, sc, emb, voce_s, **kw)


def frase_in_finestra(ciclo, testo):
    ciclo.awake_until = time.monotonic() + 8
    ciclo.listener.started_at = time.monotonic()
    ciclo.rec = {"testo": testo}
    return ciclo._compagnia_senza_nome(Turno(text=testo))


def ignoto(k=0.0):
    """Una voce lontana da tutti i profili di casa (sotto 0,20 su ognuno)."""
    return frase(carlo=0.10 + k, ospite=0.62)


def carlo():
    return frase(carlo=0.70, luca=0.20)


# ─────────────────────────── ombra, di serie ───────────────────────────

def prova_ombra():
    reg, sc, ciclo, regole, orol = ciclo_finto(modo=None)
    del reg.cfg.compagnia_da_stanza                    # il valore di serie della Config
    verifica("di serie compagnia_da_stanza è «ombra»",
             compagnia_mod.modo_stanza(reg.cfg) == "ombra", reg.cfg.compagnia_da_stanza)
    dalla_stanza(ciclo, orol, ignoto(), 2.4)
    dalla_stanza(ciclo, orol, ignoto(0.02), 1.9)
    n, how, v, t = turno(ciclo, sc, orol, carlo(), 2.2)
    cs = v.get("compagnia_stanza") or {}
    verifica("ombra: la voce non cambia (nessuna compagnia, Carlo amministra come prima)",
             "compagnia" not in v and not sc.compagnia and (n, how) == ("Carlo", "voce")
             and sc.current_level == "amministra", json.dumps(v.get("compagnia")))
    verifica("ombra: nel registro lo stato con la stanza (voce.compagnia_stanza) e la regola",
             cs.get("sconosciute") is True and cs.get("da_stanza") is True
             and "compagnia_da_stanza_ombra" in regole and "compagnia_da_stanza" not in regole,
             json.dumps(cs))
    verifica("ombra: la finestra resta aperta, la frase senza il nome passa e si conta",
             not ciclo._chiede_nome() and frase_in_finestra(ciclo, "E domani?") is None
             and "compagnia_da_stanza_ombra_nome" in regole and "compagnia_nome" not in regole)
    # In ombra con la frase breve: vale come prima
    n, how, v, t = turno(ciclo, sc, orol, frase(carlo=0.40, luca=0.1), 0.6, in_session=True,
                         prev="Carlo")
    verifica("ombra: la frase breve vale ancora chi parlava", (n, how) == ("Carlo", "breve"))
    # Spenta: i segmenti non entrano
    reg, sc, ciclo, regole, orol = ciclo_finto("spenta")
    ok = dalla_stanza(ciclo, orol, ignoto(), 3.5)
    n, how, v, t = turno(ciclo, sc, orol, carlo(), 2.2)
    verifica("contrario: compagnia_da_stanza spenta → nessun segmento, niente nel registro",
             ok is False and ciclo.compagnia.segmenti_stanza() == 0
             and "compagnia_stanza" not in v and "compagnia" not in v)
    # Un valore sconosciuto vale ombra (il più prudente fra quelli con la misura)
    verifica("un valore sconosciuto vale ombra",
             compagnia_mod.modo_stanza(SimpleNamespace(compagnia_da_stanza="boh")) == "ombra")


# ─────────────────────────── attiva: il caso del 17/10 ───────────────────────────

def prova_caso():
    reg, sc, ciclo, regole, orol = ciclo_finto()
    # L'ospite chiacchiera in cucina: due segmenti della stanza, nessuno dice il nome
    dalla_stanza(ciclo, orol, ignoto(), 2.4)
    dalla_stanza(ciclo, orol, ignoto(0.02), 1.9)
    verifica("i segmenti della stanza sono nella memoria della corsia (solo lì)",
             ciclo.compagnia.segmenti_stanza() == 2 and len(ciclo.compagnia) == 0)
    n, how, v, t = turno(ciclo, sc, orol, carlo(), 2.2)
    c = v.get("compagnia") or {}
    verifica("Carlo chiede con il nome: in compagnia con una voce sconosciuta, dalla stanza",
             c.get("voci") == 2 and c.get("sconosciute") is True and c.get("da_stanza") is True,
             json.dumps(v.get("compagnia")))
    verifica("regole voci_compagnia e compagnia_da_stanza; niente «non applicata»",
             "voci_compagnia" in regole and "compagnia_da_stanza" in regole
             and "compagnia_stanza" not in v, str(regole))
    verifica("Carlo resta Carlo dalla voce (la stanza non cambia chi parla)",
             (n, how) == ("Carlo", "voce") and sc.compagnia and sc.compagnia_sconosciute)
    verifica("serve il nome a ogni frase: la finestra senza il nome si chiude",
             ciclo._chiede_nome() and frase_in_finestra(ciclo, "E domani?") is _FINE
             and "compagnia_nome" in regole)
    verifica("il nome passa sempre", frase_in_finestra(ciclo, "Calliope, e domani?") is None)
    verifica("nel registro dei turni solo numeri (niente impronte)",
             all(not isinstance(x, (list, np.ndarray)) for x in c.values())
             and set(c) == {"voci", "prova", "distanza", "sconosciute", "da_stanza"},
             json.dumps(c))
    reg, sc, ciclo, regole, orol = ciclo_finto()
    turno(ciclo, sc, orol, carlo(), 2.2)
    verifica("contrario: Carlo da solo, senza stanza → nessuna compagnia (come prima)",
             ciclo._stato_compagnia() is None and not ciclo._chiede_nome())
    dalla_stanza(ciclo, orol, frase(carlo=0.10, amico=0.6), 3.2)
    verifica("un segmento lungo di una voce lontana dopo la risposta → la finestra si chiude "
             "subito, senza aspettare un altro turno",
             ciclo._chiede_nome() and (ciclo._stato_compagnia() or {}).get("da_stanza"))


# ─────────────────────────── la regola rigida ───────────────────────────

def prova_rigida():
    # Il caso della revisione: Carlo al turno, Bianca riconosciuta dalla stanza, poi Carlo non
    # riconosciuto (lontano dal microfono: 0,35 su di sé, 0,10 su Bianca). Con la prova
    # «profilo» di prima, sotto 0,20 sul profilo di Bianca → «sconosciuta»
    reg, sc, ciclo, regole, orol = ciclo_finto()
    turno(ciclo, sc, orol, carlo(), 2.2)
    dalla_stanza(ciclo, orol, frase(bianca=0.72, carlo=0.20), 2.5, "Bianca")
    tenuto = dalla_stanza(ciclo, orol, frase(carlo=0.35, bianca=0.10), 3.5)
    st = ciclo.compagnia.stato()
    verifica("famiglia: Carlo non riconosciuto dalla stanza (0,35 su di sé, 0,10 su Bianca) non "
             "è una voce sconosciuta", tenuto is True and st is not None
             and st.get("sconosciute") is False and st.get("prova") == "due_profili",
             json.dumps(st))
    verifica("…e la finestra senza il nome resta (compagnia di sole voci di casa)",
             not ciclo._chiede_nome())
    # La frase del turno di Carlo non riconosciuta, con Luca dalla stanza: nemmeno lei
    reg, sc, ciclo, regole, orol = ciclo_finto()
    turno(ciclo, sc, orol, carlo(), 2.2)
    dalla_stanza(ciclo, orol, frase(bianca=0.72, carlo=0.20), 2.5, "Bianca")
    n, how, v, t = turno(ciclo, sc, orol, frase(carlo=0.36, bianca=0.10), 2.4)
    c = v.get("compagnia") or {}
    verifica("la frase del turno di Carlo non riconosciuta con Bianca dalla stanza → due profili, "
             "nessuna sconosciuta", c.get("prova") == "due_profili"
             and c.get("sconosciute") is False, json.dumps(c))
    # Zona grigia: non entra
    reg, sc, ciclo, regole, orol = ciclo_finto()
    turno(ciclo, sc, orol, carlo(), 2.2)
    ok = dalla_stanza(ciclo, orol, frase(carlo=0.10, ospite=0.6), 3.5, grigia=True)
    verifica("contrario: un segmento in zona grigia non conta sconosciuto (non entra)",
             ok is False and ciclo._stato_compagnia() is None)
    # Sotto 0,20 su uno solo dei profili di casa non basta alla prova «profilo» (Bianca a 0,30)
    ok = dalla_stanza(ciclo, orol, frase(carlo=0.05, bianca=0.30, ospite=0.5), 2.0)
    verifica("contrario: un segmento lontano da Carlo ma a 0,30 da Bianca → la prova «profilo» "
             "non vale (può essere Bianca), nessuna compagnia", ok is True
             and ciclo._stato_compagnia() is None)
    # Il conoscente riconosciuto è sconosciuto anche vicino a un profilo
    reg, sc, ciclo, regole, orol = ciclo_finto()
    turno(ciclo, sc, orol, carlo(), 2.2)
    dalla_stanza(ciclo, orol, frase(carlo=0.05, bianca=0.30, ospite=0.5), 2.0, conoscente=True)
    st = ciclo._stato_compagnia() or {}
    verifica("un conoscente riconosciuto (0030) vale la prova «profilo» anche vicino a Bianca",
             st.get("sconosciute") is True and st.get("prova") == "profilo", json.dumps(st))
    # La prova «gruppi» resta quella di sempre: l'amico del 09/10 (0,22–0,33 su Carlo, frasi
    # lunghe) sentito solo dalla stanza
    reg, sc, ciclo, regole, orol = ciclo_finto()
    turno(ciclo, sc, orol, carlo(), 2.2)
    for s_, d in ((0.22, 6.1), (0.30, 4.9), (0.26, 14.3), (0.33, 8.0)):
        dalla_stanza(ciclo, orol, frase(carlo=s_, ospite=0.65), d)
    st = ciclo._stato_compagnia() or {}
    verifica("l'amico del 09/10 sentito solo dalla stanza (0,22–0,33 su Carlo) → voce "
             "sconosciuta dai gruppi, come al turno", st.get("sconosciute") is True
             and st.get("prova") == "gruppi" and ciclo._chiede_nome(), json.dumps(st))
    # Un segmento lungo vicino a Bianca (non riconosciuta nella finestra) fa un gruppo da solo,
    # come al turno: la regola rigida riguarda solo la prova «profilo»
    reg, sc, ciclo, regole, orol = ciclo_finto()
    turno(ciclo, sc, orol, carlo(), 2.2)
    dalla_stanza(ciclo, orol, frase(carlo=0.05, bianca=0.30, ospite=0.5), 3.5)
    st = ciclo._stato_compagnia() or {}
    verifica("un segmento di 3,5 s a 0,30 da Bianca → gruppo lungo, sconosciuta (gruppi come al "
             "turno)", st.get("sconosciute") is True and st.get("prova") == "gruppi",
             json.dumps(st))
    # Solo voci di casa: compagnia sì, sconosciute no
    reg, sc, ciclo, regole, orol = ciclo_finto()
    dalla_stanza(ciclo, orol, frase(bianca=0.72, carlo=0.20), 2.5, "Bianca")
    n, how, v, t = turno(ciclo, sc, orol, carlo(), 2.2)
    c = v.get("compagnia") or {}
    verifica("solo voci di casa (Bianca dalla stanza, Carlo al turno) → compagnia sì (due "
             "profili), sconosciute no, la finestra resta",
             c.get("prova") == "due_profili" and c.get("sconosciute") is False
             and c.get("da_stanza") is True and not ciclo._chiede_nome(), json.dumps(c))


# ─────────────────────────── da_stanza solo se cambia l'effetto ───────────────────────────

def prova_effetto():
    reg, sc, ciclo, regole, orol = ciclo_finto()
    turno(ciclo, sc, orol, carlo(), 2.2)
    turno(ciclo, sc, orol, frase(carlo=0.10, amico=0.6), 2.0)      # l'ospite al turno
    base = dict(ciclo.compagnia.stato_turno() or {})
    dalla_stanza(ciclo, orol, frase(bianca=0.72, carlo=0.20), 3.0, "Bianca")
    n, how, v, t = turno(ciclo, sc, orol, carlo(), 2.2)
    c = v.get("compagnia") or {}
    verifica("la stanza aggiunge solo una voce (Bianca) a una compagnia già con la sconosciuta "
             "→ niente da_stanza, prova e distanza del turno",
             "da_stanza" not in c and c.get("prova") == base.get("prova")
             and c.get("distanza") == base.get("distanza")
             and "compagnia_da_stanza" not in regole and "compagnia_stanza" not in v,
             json.dumps({"base": base, "c": c}))
    verifica("stato_stanza: None quando l'effetto non cambia",
             ciclo.compagnia.stato_stanza() is None)


# ─────────────────────────── solo verso la prudenza ───────────────────────────

def prova_prudenza():
    def ospite(k):
        return frase(carlo=0.22, luca=0.30, amico=0.62 + k)

    reg, sc, ciclo, regole, orol = ciclo_finto()
    turno(ciclo, sc, orol, carlo(), 2.2)
    turno(ciclo, sc, orol, ospite(0.0), 2.0)
    n, how, v, t = turno(ciclo, sc, orol, ospite(0.02), 2.1)
    base = v.get("compagnia") or {}
    verifica("le frasi del turno: Carlo e un ospite → sconosciuta", base.get("sconosciute"),
             json.dumps(base))
    dalla_stanza(ciclo, orol, frase(luca=0.72, carlo=0.20), 3.4, "Luca")
    dalla_stanza(ciclo, orol, frase(luca=0.70, carlo=0.20), 2.6, "Luca")
    c = ciclo.compagnia
    tutte = sorted(c._frasi + c._stanza, key=lambda f: f.ora)
    da_sola = c._calcola_su(tutte)
    verifica("(il motivo: calcolato su tutte insieme la voce dell'ospite finirebbe con Luca)",
             da_sola is not None and not da_sola["sconosciute"], json.dumps(da_sola))
    st = ciclo.compagnia.stato()
    verifica("con Luca sentito dalla stanza la voce sconosciuta resta (mai meno prudente)",
             st is not None and st["sconosciute"] and st["voci"] >= 2, json.dumps(st))
    verifica("…e la finestra senza il nome resta chiusa (stato del turno)",
             ciclo._chiede_nome())
    reg, sc, ciclo, regole, orol = ciclo_finto()
    dalla_stanza(ciclo, orol, carlo(), 3.0, "Carlo")
    n, how, v, t = turno(ciclo, sc, orol, frase(carlo=0.44, luca=0.11), 0.5)
    verifica("la stanza non dà continuità: Carlo solo dalla stanza, frase di 0,5 s → nessuno",
             n is None and not t.continuita)
    reg, sc, ciclo, regole, orol = ciclo_finto()
    turno(ciclo, sc, orol, frase(carlo=0.72, luca=0.20), 2.0)
    n, how, v, t = turno(ciclo, sc, orol, frase(carlo=0.40, luca=0.1), 0.6, in_session=True,
                         prev="Carlo")
    verifica("contrario: Carlo da solo → la frase breve vale lui", (n, how) == ("Carlo", "breve"))
    dalla_stanza(ciclo, orol, ignoto(), 3.5)
    n, how, v, t = turno(ciclo, sc, orol, frase(carlo=0.40, luca=0.1), 0.6, in_session=True,
                         prev="Carlo")
    verifica("attiva, con un ospite sentito dalla stanza la frase breve non vale più Carlo",
             n is None and "compagnia_senza_breve" in regole and sc.current_level == "ospite")
    n, how, v, t = turno(ciclo, sc, orol, frase(carlo=0.70, luca=0.2), 2.0)
    verifica("…Carlo riconosciuto nella frase amministra come prima",
             (n, how) == ("Carlo", "voce") and sc.current_level == "amministra")


# ─────────────────────────── i minori ───────────────────────────

class CancelliFinti:
    def __init__(self, aperto=False):
        self.aperto = aperto

    def aperto_su(self, corsia):
        return self.aperto


def prova_minori():
    # Luca (minore) riconosciuto dalla stanza, l'ospite pure: con la stanza la finestra si
    # chiuderebbe, e la frase senza il nome di Luca non arriverebbe al guardiano
    reg, sc, ciclo, regole, orol = ciclo_finto(minore=True)
    dalla_stanza(ciclo, orol, frase(luca=0.72, carlo=0.20), 2.5, "Luca")
    dalla_stanza(ciclo, orol, ignoto(), 3.4)
    n, how, v, t = turno(ciclo, sc, orol, carlo(), 2.2)
    cs = v.get("compagnia_stanza") or {}
    verifica("un minore qui: la stanza non chiude la finestra (vale lo stato del turno)",
             not ciclo._chiede_nome() and frase_in_finestra(ciclo, "Mi aiuti?") is None
             and "compagnia" not in v, json.dumps(v.get("compagnia")))
    verifica("…nel registro cosa sarebbe cambiato, col segno dei minori, e la regola",
             cs.get("minori") is True and cs.get("sconosciute") is True
             and "compagnia_da_stanza_minori" in regole, json.dumps(cs))
    # Il minore che parla al turno (chi parla)
    reg, sc, ciclo, regole, orol = ciclo_finto(minore=True)
    dalla_stanza(ciclo, orol, ignoto(), 3.4)
    turno(ciclo, sc, orol, frase(luca=0.72, carlo=0.20), 2.2)
    verifica("il minore che parla al turno: la finestra resta per la sua risposta",
             not ciclo._chiede_nome() and frase_in_finestra(ciclo, "Sì, tutto bene.") is None)
    # Un cancello aperto su questa corsia
    reg, sc, ciclo, regole, orol = ciclo_finto()
    ciclo.s.cancelli = CancelliFinti(aperto=True)
    dalla_stanza(ciclo, orol, ignoto(), 3.4)
    turno(ciclo, sc, orol, carlo(), 2.2)
    verifica("un cancello aperto: la risposta senza il nome passa (arriva al cancello 2)",
             not ciclo._chiede_nome() and frase_in_finestra(ciclo, "Sì, tutto bene.") is None)
    ciclo.s.cancelli.aperto = False
    verifica("contrario: cancello chiuso, nessun minore → la finestra si chiude",
             ciclo._chiede_nome() and frase_in_finestra(ciclo, "E domani?") is _FINE)
    # Il minore lontano dal microfono che la voce non riconosce (terza revisione della PR #161):
    # Luca a 0,35 sul suo profilo, Carlo a 0,26; un ospite sentito solo dalla stanza
    for minore in (True, False):
        reg, sc, ciclo, regole, orol = ciclo_finto(minore=minore)
        turno(ciclo, sc, orol, carlo(), 2.2)
        dalla_stanza(ciclo, orol, ignoto(), 3.4)
        n, how, v, t = turno(ciclo, sc, orol, frase(luca=0.35, carlo=0.26), 2.0)
        scartata = frase_in_finestra(ciclo, "Mi aiuti? Non sto bene.") is _FINE
        if minore:
            verifica("un minore in casa, lontano (0,35 sul suo profilo, non riconosciuto): la sua "
                     "frase senza il nome non si butta, arriva al cancello 2 e al rilevatore",
                     n is None and not scartata and not ciclo._chiede_nome()
                     and "compagnia_da_stanza_minori" in regole, f"{n} {regole}")
        else:
            verifica("contrario: la stessa frase in una casa senza minori → si butta (serve il "
                     "nome)", scartata and ciclo._chiede_nome())
    # Un minore con una voce sconosciuta già al turno: come prima (lo stato del turno vale)
    reg, sc, ciclo, regole, orol = ciclo_finto(minore=True)
    turno(ciclo, sc, orol, frase(luca=0.72, carlo=0.20), 2.2)
    turno(ciclo, sc, orol, frase(carlo=0.10, luca=0.05, amico=0.6), 2.2)
    verifica("contrario: la voce sconosciuta al turno col minore → la finestra si chiude come "
             "prima (la tutela riguarda solo la stanza)", ciclo._chiede_nome())

    # _pericolo_vale: il giudizio «non rivolta» con la compagnia della sola stanza
    def con_giudizio(ciclo, per_calliope):
        t = Turno(text="Mi voglio fare male.", senza_nome=True)
        t.rivolta = {"fut": None, "modo": "ombra",
                     "esito": rivolta_mod.Giudizio(per_calliope, 120.0)}
        return t

    reg, sc, ciclo, regole, orol = ciclo_finto()
    turno(ciclo, sc, orol, carlo(), 2.2)
    dalla_stanza(ciclo, orol, ignoto(), 3.4)
    verifica("pericolo: compagnia solo dalla stanza, giudizio «non rivolta» → il segnale vale",
             ciclo._pericolo_vale(con_giudizio(ciclo, False)) is True
             and "pericolo_solo_stanza" in regole and "pericolo_non_rivolta" not in regole)
    turno(ciclo, sc, orol, frase(carlo=0.10, amico=0.6), 2.2)       # l'ospite al turno
    regole.clear()
    verifica("contrario: compagnia del turno, «non rivolta» → non vale come prima",
             ciclo._pericolo_vale(con_giudizio(ciclo, False)) is False
             and "pericolo_non_rivolta" in regole)
    verifica("contrario: «rivolta» → vale, senza regole nuove",
             ciclo._pericolo_vale(con_giudizio(ciclo, True)) is True
             and "pericolo_solo_stanza" not in regole)


# ─────────────────────────── il costo e il tempo ───────────────────────────

def prova_costo():
    reg, sc, ciclo, regole, orol = ciclo_finto()
    comp = ciclo.compagnia
    turno(ciclo, sc, orol, carlo(), 2.2)
    for k in range(40):
        dalla_stanza(ciclo, orol, frase(carlo=0.05, ospite=0.3, amico=0.3 + 0.01 * (k % 5)),
                     2.0, dopo_s=1.0)
    conta = [0]
    vero = comp._calcola_su

    def contato(*a, **k):
        conta[0] += bool(k.get("rigido"))       # il calcolo con la stanza (il turno: sempre)
        return vero(*a, **k)

    comp._calcola_su = contato
    for _ in range(20):
        ciclo._stato_compagnia()
        ciclo._chiede_nome()
    verifica("il calcolo con la stanza tenuto da parte: 40 chiamate senza segmenti nuovi → "
             "nessun calcolo (già fatto all'arrivo del segmento)", conta[0] == 0,
             str(conta[0]))
    dalla_stanza(ciclo, orol, ignoto(), 2.0, dopo_s=0.5)
    dopo_segmento = conta[0]
    ciclo._stato_compagnia()
    ciclo._stato_compagnia()
    verifica("un segmento nuovo → il calcolo con la stanza si rifà una volta, all'arrivo; le "
             "chiamate dopo lo trovano pronto", dopo_segmento == 1 and conta[0] == 1,
             f"{dopo_segmento} {conta[0]}")
    # L'impronta di Carlo che si adatta (registry.adapt assegna un array nuovo): si rifà
    vp = reg.users["Carlo"].voiceprint
    reg.users["Carlo"].voiceprint = (vp + 0.05 * VF.ALTRO) / np.linalg.norm(vp + 0.05 * VF.ALTRO)
    ciclo._stato_compagnia()
    verifica("l'impronta di casa cambiata (adapt) → il calcolo con la stanza si rifà",
             conta[0] == 2, str(conta[0]))
    orol.t += 301
    verifica("una frase uscita dalla finestra → torna una voce sola",
             ciclo._stato_compagnia() is None, str(conta[0]))
    # adapt dopo osserva (terza revisione della PR #161): lo stato del turno si calcola al
    # momento, come su main. Carlo e una frase di nessuno a 0,22 su di lui: niente; poi l'impronta
    # di Carlo si adatta e la frase scende sotto 0,20 → su main in compagnia subito
    for modo in ("ombra", "spenta", "attiva"):
        reg, sc, ciclo, regole, orol = ciclo_finto(modo)
        turno(ciclo, sc, orol, carlo(), 2.2)
        dalla_stanza(ciclo, orol, frase(bianca=0.72, carlo=0.20), 2.0, "Bianca")
        f = frase(carlo=0.22, amico=0.6)
        turno(ciclo, sc, orol, f, 2.0)
        prima = ciclo._stato_compagnia()
        vp = reg.users["Carlo"].voiceprint - 0.5 * f
        reg.users["Carlo"].voiceprint = (vp / np.linalg.norm(vp)).astype(np.float32)
        comp = ciclo.compagnia
        main = comp._calcola_su(list(comp._frasi))           # lo stato di main, al momento
        dopo = comp.stato_turno()
        verifica(f"{modo}: adapt dopo osserva → lo stato del turno è quello di main, subito",
                 (prima is None or not prima.get("sconosciute")) and main is not None
                 and dopo == main and (modo == "attiva" or ciclo._stato_compagnia() == main)
                 and ciclo._chiede_nome(), json.dumps({"prima": prima, "main": main,
                                                       "dopo": dopo}))
    # Il tempo: 200 segmenti di voci tutte diverse (la TV), lo stato a ogni chiamata
    reg, sc, ciclo, regole, orol = ciclo_finto()
    turno(ciclo, sc, orol, carlo(), 2.2)
    rng = np.random.default_rng(3)
    for _ in range(200):
        v = rng.standard_normal(192).astype(np.float32)
        v -= float(v @ VF.CARLO) * VF.CARLO
        dalla_stanza(ciclo, orol, v, 2.0, dopo_s=1.0)
    t0 = time.perf_counter()
    dalla_stanza(ciclo, orol, ignoto(), 2.0, dopo_s=0.5)
    stanza_ms = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    for _ in range(10):
        ciclo._stato_compagnia()
    voce_ms = (time.perf_counter() - t0) * 100
    verifica(f"200 segmenti di voci diverse (la TV), tenuti al più {compagnia_mod.STANZA_MAX}: "
             f"il calcolo nel thread della stanza {stanza_ms:.1f} ms, nel thread della voce "
             f"{voce_ms:.2f} ms a chiamata", ciclo.compagnia.segmenti_stanza()
             <= compagnia_mod.STANZA_MAX and voce_ms < 1.0 and stanza_ms < 100,
             f"{stanza_ms:.1f} / {voce_ms:.2f} ms")


def prova_tempo():
    # Un istante nel futuro (orologi diversi) vale adesso: con una seconda voce nella finestra
    # (Carlo al turno) il segmento deve uscire dopo 5 minuti da adesso, non da quell'istante
    reg, sc, ciclo, regole, orol = ciclo_finto()
    turno(ciclo, sc, orol, carlo(), 2.2)
    dalla_stanza(ciclo, orol, ignoto(), 3.5, fa_s=-500)
    verifica("(precondizione: Carlo e il segmento → in compagnia)",
             (ciclo._stato_compagnia() or {}).get("sconosciute") is True)
    orol.t += 301
    n, how, v, t = turno(ciclo, sc, orol, carlo(), 2.2, dopo_s=0.0)
    verifica("un istante oltre adesso vale adesso: dopo 5 minuti il segmento è uscito",
             "compagnia" not in v and ciclo.compagnia.segmenti_stanza() == 0,
             json.dumps(v.get("compagnia")))
    reg, sc, ciclo, regole, orol = ciclo_finto()
    ok = dalla_stanza(ciclo, orol, ignoto(), 3.5, fa_s=301)
    n, how, v, t = turno(ciclo, sc, orol, carlo(), 2.2)
    verifica("contrario: un segmento detto più di 5 minuti fa → non tenuto, nessuna compagnia",
             ok is False and "compagnia" not in v)
    reg, sc, ciclo, regole, orol = ciclo_finto()
    dalla_stanza(ciclo, orol, ignoto(), 3.5)
    orol.t += 301
    n, how, v, t = turno(ciclo, sc, orol, carlo(), 2.2)
    verifica("contrario: un segmento uscito dalla finestra → nessun effetto",
             "compagnia" not in v and ciclo.compagnia.segmenti_stanza() == 0)
    reg, sc, ciclo, regole, orol = ciclo_finto()
    tenuto = [dalla_stanza(ciclo, orol, ignoto(), d) for d in (0.6, 0.9, 0.95)]
    n, how, v, t = turno(ciclo, sc, orol, carlo(), 2.2)
    verifica("contrario: segmenti sotto speaker_min_voice_s (1 s) → ignorati",
             tenuto == [False] * 3 and "compagnia" not in v)
    reg, sc, ciclo, regole, orol = ciclo_finto()
    for d in (2.0, 3.5, 1.8):
        dalla_stanza(ciclo, orol, frase(ospite=0.65), d)
    verifica("contrario: lo stesso ospite tre volte nella stanza → una voce sola",
             ciclo.compagnia.stato() is None)
    reg, sc, ciclo, regole, orol = ciclo_finto()
    reg.cfg.compagnia_enabled = "spenta"
    ok = dalla_stanza(ciclo, orol, ignoto(), 3.5)
    verifica("contrario: compagnia spenta → nessun segmento tenuto", ok is False)
    reg, sc, ciclo, regole, orol = ciclo_finto()
    dalla_stanza(ciclo, orol, ignoto(), 3.5)
    ciclo.compagnia.dimentica()
    verifica("dimentica: via anche i segmenti della stanza",
             ciclo.compagnia.segmenti_stanza() == 0 and ciclo.compagnia.stato() is None)


# ─────────────────────────── le corsie ───────────────────────────

def prova_corsie():
    def corsia(remoto=True):
        c = compagnia_mod.Compagnia(VF.Reg().cfg, VF.Reg())
        return SimpleNamespace(ciclo=SimpleNamespace(compagnia=c),
                               listener=SimpleNamespace(remoto=remoto))

    c1, c2, loc = corsia(), corsia(), corsia()
    tutte = {"sat:1": c1, "sat:2": c2, "locale": loc}
    verifica("satelliti insieme: il satellite 1 → la sua corsia",
             corsie_mod.corsia_del_satellite(tutte, 1, True) is c1)
    verifica("satelliti insieme: un satellite senza corsia → nessuna (mai la locale)",
             corsie_mod.corsia_del_satellite({"locale": loc}, 3, True) is None)
    sat = SimpleNamespace(attivo_pronto=lambda: SimpleNamespace(satellite={"id": 2}))
    sola = {"locale": loc}
    verifica("una corsia sola: il segmento del satellite attivo → la corsia che lo segue",
             corsie_mod.corsia_del_satellite(sola, 2, False, sat) is loc)
    verifica("una corsia sola: un altro satellite (un'altra stanza) → nessuna",
             corsie_mod.corsia_del_satellite(sola, 1, False, sat) is None)
    verifica("una corsia sola con l'audio locale → nessuna",
             corsie_mod.corsia_del_satellite({"locale": corsia(False)}, 2, False, sat) is None)
    from calliope.main import Avvio
    finto = SimpleNamespace(corsie_tutte=tutte, insieme=True, s=SimpleNamespace(satelliti=None))
    Avvio._compagnia_dalla_stanza(finto, 1, ignoto(), 3.0, None, time.monotonic())
    verifica("Avvio: il segmento del satellite 1 solo nella compagnia della sua corsia",
             c1.ciclo.compagnia.segmenti_stanza() == 1
             and c2.ciclo.compagnia.segmenti_stanza() == 0
             and loc.ciclo.compagnia.segmenti_stanza() == 0)
    Avvio._compagnia_dalla_stanza(finto, 9, ignoto(), 3.0, None, time.monotonic())
    Avvio._compagnia_dalla_stanza(finto, 2, ignoto(), 3.0, None, time.monotonic(), grigia=True)
    verifica("Avvio: un satellite senza corsia → nessuna compagnia toccata; la zona grigia "
             "passa il suo segno (non entra)", c1.ciclo.compagnia.segmenti_stanza() == 1
             and c2.ciclo.compagnia.segmenti_stanza() == 0)


# ─────────────────────────── la stanza ───────────────────────────

class STTFinto:
    ultima_scartata = None

    def transcribe(self, audio, **k):
        return "Passami il sale, per favore."


class RegConta(VF.Reg):
    """Il registro vero (classifica) con l'impronta del segmento decisa dalla prova; conta le
    chiamate a CAM++."""

    def __init__(self):
        super().__init__()
        self.prossima, self.chiamate = None, 0

    def embed(self, audio, sr=16000):
        self.chiamate += 1
        return self.prossima


def stanza_nuova(cartella=None):
    from calliope.stanza.ascolto import Stanza
    reg = RegConta()
    cfg = reg.cfg
    cfg.stanza = "ombra"
    if cartella is not None:
        cfg.stanza_tenuta = True
        cfg.config_dir = cartella
        cfg.stanza_tenuta_db = os.path.join(cartella, "stanza.db")
        cfg.turn_log_dir = os.path.join(cartella, "registro")
    st = Stanza(cfg, STTFinto(), registry=reg, log=lambda m: None)
    if cartella is not None:
        from calliope.stanza import load_tenuta
        st.tenuta = load_tenuta(cfg, reg, log=lambda m: None)
    st._info[1] = {"nome": "telefono cucina", "stanza": "cucina", "canale": "telefono"}
    chiamate = []
    st.su_voce = lambda *a, **k: chiamate.append((a, k))
    return st, reg, chiamate


def segmento(ident, voce_s, durante=None):
    from calliope.stanza.ascolto import Segmento
    ora = time.monotonic()
    s = Segmento(1, "telefono cucina", "telefono", ident, ora - voce_s - 0.5)
    s.pezzi = [(np.full(int(16000 * voce_s), 3000, dtype="<i2")).tobytes()]
    s.voce_s, s.fine, s.chiuso = voce_s, ora - 0.2, ora
    s.inizio_epoch, s.fine_epoch = time.time() - voce_s - 0.5, time.time() - 0.2
    s.durante = durante
    return s


def prova_stanza():
    st, reg, chiamate = stanza_nuova()
    try:
        ig = ignoto()
        reg.prossima = ig
        st._trascrivi(segmento(1, 2.5))
        a, k = chiamate[0] if chiamate else ((None,) * 5, {})
        verifica("voce sconosciuta: alla compagnia una volta, con l'impronta di chi parla (CAM++ "
                 "una volta sola) e senza nome",
                 len(chiamate) == 1 and reg.chiamate == 1 and a[0] == 1 and a[1] is ig
                 and a[3] is None and abs(a[2] - 2.5) < 1e-6
                 and k == {"grigia": False, "conoscente": False}, str(k))
        verifica("con l'istante del segmento (monotonic, prima di adesso)",
                 a[4] is not None and a[4] <= time.monotonic())
        righe = st.registro(1).righe()
        verifica("niente impronta nella riga della stanza",
                 righe and all("emb" not in r for r in righe), str(righe and list(righe[-1])))
        reg.prossima = carlo()
        st._trascrivi(segmento(2, 2.0))
        verifica("Carlo riconosciuto dalla voce → alla compagnia con il nome",
                 len(chiamate) == 2 and chiamate[1][0][3] == "Carlo")
        reg.prossima = frase(carlo=0.44, luca=0.10)
        st._trascrivi(segmento(3, 2.0))
        verifica("zona grigia → senza nome e col segno della zona grigia",
                 len(chiamate) == 3 and chiamate[2][0][3] is None
                 and chiamate[2][1].get("grigia") is True)
        reg.prossima, prima = ig, reg.chiamate
        st._trascrivi(segmento(4, 0.7))
        verifica("contrario: sotto speaker_min_voice_s → niente CAM++, niente compagnia",
                 len(chiamate) == 3 and reg.chiamate == prima)
        st._trascrivi(segmento(5, 2.5, durante=[7]))
        verifica("contrario: detto mentre Calliope parlava → non alla compagnia",
                 len(chiamate) == 3)
        st.su_voce = None
        st._trascrivi(segmento(6, 2.5))
        verifica("contrario: senza corsie collegate (su_voce None) → la stanza come prima",
                 len(chiamate) == 3 and len(st.registro(1).righe()) >= 5)
        st.su_voce = lambda *a, **k: 1 / 0
        st._trascrivi(segmento(7, 2.5))
        verifica("un guasto della compagnia non ferma la stanza",
                 any(r.get("segmento") == 7 for r in st.registro(1).righe()))
    finally:
        st.chiudi()
    from calliope.config import Config
    from calliope.stanza import load_stanza
    c = Config()
    c.stanza = "spenta"
    verifica("contrario: stanza spenta → nessuna stanza, nessun segmento alla compagnia",
             load_stanza(c, STTFinto()) is None)


def prova_solo_memoria():
    cartella = tempfile.mkdtemp(prefix="calliope-compagnia-stanza-")
    st, reg, chiamate = stanza_nuova(cartella)
    reg2, sc, ciclo, regole, orol = ciclo_finto()
    ciclo.compagnia.orologio = time.monotonic
    st.su_voce = lambda sat, emb, voce_s, nome, ora, **k: ciclo.compagnia.osserva_stanza(
        emb, voce_s, nome, ora, **k)
    try:
        ig = ignoto().astype(np.float32)
        reg.prossima = ig
        for i in range(3):
            st._trascrivi(segmento(10 + i, 2.5))
        reg.prossima = carlo()
        st._trascrivi(segmento(20, 2.5))         # Carlo: la sua riga va su disco (tenuta)
        st.tenuta.attendi()
        n, how, v, t = riconosci(ciclo, sc, carlo(), 2.2)
        c = v.get("compagnia") or {}
        verifica("la voce sconosciuta della stanza conta (con la stanza vera)",
                 c.get("sconosciute") and c.get("da_stanza"), json.dumps(c))
        firme = [np.asarray(ig, dtype=np.float32).tobytes()[:64],
                 (ig / np.linalg.norm(ig)).astype(np.float32).tobytes()[:64],
                 np.asarray(ig, dtype=np.float64).tobytes()[:64]]
        trovati, file_visti = [], 0
        for radice, _d, nomi in os.walk(cartella):
            for nm in nomi:
                file_visti += 1
                with open(os.path.join(radice, nm), "rb") as f:
                    dati = f.read()
                if any(fm in dati for fm in firme):
                    trovati.append(nm)
        verifica("solo in memoria (0031): nessun file della cartella ha l'impronta della voce "
                 "sconosciuta (tenuta accesa: la riga di Carlo sì)", file_visti > 0
                 and not trovati, f"file {file_visti}, con l'impronta {trovati}")
        rec = json.dumps(ciclo.rec, default=str)
        verifica("il registro del turno: solo numeri, nessun vettore",
                 "da_stanza" in rec and len(rec) < 2000 and "[" not in json.dumps(c))
        import sqlite3
        db = sqlite3.connect(os.path.join(cartella, "stanza.db"))
        try:
            tab = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            colonne = {t: [r[1] for r in db.execute(f"PRAGMA table_info({t})")] for t in tab}
        finally:
            db.close()
        verifica("nessuna colonna di impronte nel disco della stanza",
                 not any("emb" in x or "impront" in x for cs in colonne.values() for x in cs),
                 json.dumps(colonne))
    finally:
        st.chiudi()


def prova_riassunto():
    turni = [{"inizio": "2026-10-17T21:00:00", "voce": {"punteggio": 0.7, "compagnia": {
        "voci": 2, "prova": "gruppi", "distanza": 0.2, "sconosciute": True, "da_stanza": True}},
        "regole": ["voci_compagnia", "compagnia_da_stanza"]},
        {"inizio": "2026-10-17T21:05:00", "voce": {"punteggio": 0.1, "compagnia": {
            "voci": 2, "prova": "profilo", "distanza": 0.1, "sconosciute": True}},
         "regole": ["voci_compagnia"]},
        {"inizio": "2026-10-17T21:06:00", "voce": {"punteggio": 0.7, "compagnia_stanza": {
            "voci": 2, "prova": "profilo", "distanza": 0.1, "sconosciute": True,
            "da_stanza": True}}, "regole": ["compagnia_da_stanza_ombra"]},
        {"inizio": "2026-10-17T21:07:00", "voce": {"punteggio": 0.7, "compagnia_stanza": {
            "voci": 2, "prova": "gruppi", "distanza": 0.2, "sconosciute": True,
            "da_stanza": True, "minori": True}}, "regole": ["compagnia_da_stanza_minori"]},
        {"inizio": "2026-10-17T21:08:00", "regole": ["compagnia_da_stanza_ombra_nome"]}]
    d = compagnia_mod.riassunto(turni).get("2026-10-17", {})
    verifica("stato --turni: dalla stanza, non applicata, per i minori, le regole",
             d.get("in_compagnia") == 2 and d.get("da_stanza") == 1
             and d.get("stanza_non_applicata") == 2 and d.get("stanza_compagnia") == 2
             and d.get("stanza_sconosciute") == 2 and d.get("stanza_minori") == 1
             and d.get("regole", {}).get("compagnia_da_stanza_ombra_nome") == 1, json.dumps(d))
    t = compagnia_mod.testo(compagnia_mod.riassunto(turni))
    verifica("stato --turni: il testo dice «dalla stanza 1» e «non applicata: 2 frasi»",
             "dalla stanza 1" in t and "non applicata: 2 frasi" in t, t)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    for nome, f in (("ombra, di serie", prova_ombra), ("attiva: il caso del 17/10", prova_caso),
                    ("la regola rigida", prova_rigida), ("da_stanza e l'effetto", prova_effetto),
                    ("solo verso la prudenza", prova_prudenza), ("i minori", prova_minori),
                    ("il costo", prova_costo), ("il tempo e i contrari", prova_tempo),
                    ("le corsie", prova_corsie), ("la stanza", prova_stanza),
                    ("solo in memoria", prova_solo_memoria), ("stato --turni", prova_riassunto)):
        prova(nome, f)
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    sys.exit(1 if errori else 0)
