"""
Prova a secco della compagnia dai segmenti della stanza (18/10/2026, issue #147, caso vero del
17/10: telefono in cucina, chi amministra con il minore e quattro voci sconosciute sentite dalla
stanza, le sue domande «non in compagnia»). calliope/compagnia.py (`osserva_stanza`, lo stato più
prudente fra turno e stanza), calliope/stanza/ascolto.py (`su_voce`, l'impronta già calcolata per
chi parla), calliope/corsie.py (`corsia_del_satellite`), calliope/main.py
(`Avvio._compagnia_dalla_stanza`). Impronte sintetiche come prova_compagnia, nomi di fantasia:
Carlo amministra, Luca è il minore; Amico e Ospite sono voci senza profilo.

- Il caso: segmenti della stanza di una voce sconosciuta, poi una frase di Carlo al turno → in
  compagnia con una voce sconosciuta, `da_stanza`, regola `compagnia_da_stanza`, finestra senza
  il nome chiusa; Carlo resta Carlo dalla voce.
- Contrari: niente stanza (come prima), segmenti sotto `speaker_min_voice_s`, solo voci di casa
  (compagnia sì, sconosciute no), segmenti più vecchi della finestra o usciti dalla finestra,
  compagnia spenta.
- Solo verso la prudenza: un profilo di casa sentito dalla stanza non assorbe la voce di un
  ospite (la sconosciuta resta), la stanza non dà continuità né frase breve.
- Le corsie: il segmento va solo alla corsia del satellite che l'ha sentito, con i satelliti
  insieme e con una corsia sola (solo se l'attivo è quel satellite).
- La stanza: l'impronta di `_chi` passa alla compagnia (CAM++ una volta per segmento), il nome
  solo per la voce di casa sopra soglia; non i segmenti detti durante la voce di Calliope, non
  quelli sotto la soglia di voce; niente impronta nella riga.
- Solo in memoria (decisione 0031): con la tenuta su disco accesa, nessun file della cartella
  contiene l'impronta della voce sconosciuta, il registro dei turni ha solo numeri.
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
from prova_compagnia import AMICO, OSPITE, Ascoltatore, Orologio, frase, riconosci
from prova_voci_famiglia import VoceFinta

from calliope import compagnia as compagnia_mod
from calliope import corsie as corsie_mod
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


def ciclo_finto():
    reg, sc, ciclo, regole = VF.ciclo_finto()
    ciclo.speaker = VoceFinta()
    ciclo.listener = Ascoltatore()
    orol = Orologio()
    ciclo.compagnia.orologio = orol
    return reg, sc, ciclo, regole, orol


def dalla_stanza(ciclo, orol, emb, voce_s, nome=None, fa_s=0.0, dopo_s=5.0):
    """Un segmento della stanza detto `fa_s` secondi prima di adesso (dopo `dopo_s`)."""
    orol.t += dopo_s
    return ciclo.compagnia.osserva_stanza(emb, voce_s, nome, orol.t - fa_s)


def turno(ciclo, sc, orol, emb, voce_s, dopo_s=5.0, **kw):
    orol.t += dopo_s
    return riconosci(ciclo, sc, emb, voce_s, **kw)


def frase_in_finestra(ciclo, testo):
    ciclo.awake_until = time.monotonic() + 8
    ciclo.listener.started_at = time.monotonic()
    ciclo.rec = {"testo": testo}
    return ciclo._compagnia_senza_nome(Turno(text=testo))


# ─────────────────────────── il caso del 17/10 ───────────────────────────

def prova_caso():
    reg, sc, ciclo, regole, orol = ciclo_finto()
    # L'ospite chiacchiera in cucina: due segmenti della stanza, nessuno dice il nome
    dalla_stanza(ciclo, orol, frase(carlo=0.22, ospite=0.65), 2.4)
    dalla_stanza(ciclo, orol, frase(carlo=0.24, ospite=0.62), 1.9)
    verifica("i segmenti della stanza sono nella memoria della corsia (solo lì)",
             ciclo.compagnia.segmenti_stanza() == 2 and len(ciclo.compagnia) == 0)
    n, how, v, t = turno(ciclo, sc, orol, frase(carlo=0.70, luca=0.20), 2.2)
    c = v.get("compagnia") or {}
    verifica("Carlo chiede con il nome: in compagnia con una voce sconosciuta, dalla stanza",
             c.get("voci") == 2 and c.get("sconosciute") is True and c.get("da_stanza") is True,
             json.dumps(v.get("compagnia")))
    verifica("regole voci_compagnia e compagnia_da_stanza nel registro dei turni",
             "voci_compagnia" in regole and "compagnia_da_stanza" in regole, str(regole))
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
    # Il segno sugli schermi: anche prima di un altro turno, lo stato lo vede
    reg, sc, ciclo, regole, orol = ciclo_finto()
    turno(ciclo, sc, orol, frase(carlo=0.70, luca=0.20), 2.2)
    verifica("contrario: Carlo da solo, senza stanza → nessuna compagnia (come prima)",
             ciclo._stato_compagnia() is None and not ciclo._chiede_nome())
    dalla_stanza(ciclo, orol, frase(carlo=0.10, amico=0.6), 3.2)
    verifica("un segmento lungo di una voce lontana dopo la risposta → la finestra si chiude "
             "subito, senza aspettare un altro turno",
             ciclo._chiede_nome() and (ciclo._stato_compagnia() or {}).get("da_stanza"))


# ─────────────────────────── i contrari ───────────────────────────

def prova_contrari():
    # Sotto la soglia di voce: ignorati
    reg, sc, ciclo, regole, orol = ciclo_finto()
    tenuto = [dalla_stanza(ciclo, orol, frase(carlo=0.10, amico=0.6), d)
              for d in (0.6, 0.9, 0.95)]
    n, how, v, t = turno(ciclo, sc, orol, frase(carlo=0.70, luca=0.20), 2.2)
    verifica("contrario: segmenti sotto speaker_min_voice_s (1 s) → ignorati, nessuna compagnia",
             tenuto == [False] * 3 and "compagnia" not in v
             and ciclo.compagnia.segmenti_stanza() == 0, json.dumps(v.get("compagnia")))
    # Solo voci di casa: compagnia sì, sconosciute no
    reg, sc, ciclo, regole, orol = ciclo_finto()
    dalla_stanza(ciclo, orol, frase(luca=0.72, carlo=0.20), 2.5, "Luca")
    n, how, v, t = turno(ciclo, sc, orol, frase(carlo=0.70, luca=0.20), 2.2)
    c = v.get("compagnia") or {}
    verifica("solo voci di casa (Luca dalla stanza, Carlo al turno) → compagnia sì (due profili),"
             " sconosciute no, la finestra resta",
             c.get("prova") == "due_profili" and c.get("sconosciute") is False
             and c.get("da_stanza") is True and not ciclo._chiede_nome(), json.dumps(c))
    # Più vecchi della finestra: nessun effetto
    reg, sc, ciclo, regole, orol = ciclo_finto()
    ok = dalla_stanza(ciclo, orol, frase(carlo=0.10, amico=0.6), 3.5, fa_s=301)
    n, how, v, t = turno(ciclo, sc, orol, frase(carlo=0.70, luca=0.20), 2.2)
    verifica("contrario: un segmento detto più di 5 minuti fa → non tenuto, nessuna compagnia",
             ok is False and "compagnia" not in v)
    reg, sc, ciclo, regole, orol = ciclo_finto()
    dalla_stanza(ciclo, orol, frase(carlo=0.10, amico=0.6), 3.5)
    orol.t += 301
    n, how, v, t = turno(ciclo, sc, orol, frase(carlo=0.70, luca=0.20), 2.2)
    verifica("contrario: un segmento uscito dalla finestra → nessun effetto",
             "compagnia" not in v and ciclo.compagnia.segmenti_stanza() == 0)
    # Un istante nel futuro (orologi diversi) non allunga la finestra
    reg, sc, ciclo, regole, orol = ciclo_finto()
    dalla_stanza(ciclo, orol, frase(carlo=0.10, amico=0.6), 3.5, fa_s=-500)
    orol.t += 301
    verifica("un istante oltre adesso vale adesso (non resta oltre la finestra)",
             ciclo.compagnia.stato() is None)
    # La stanza da sola, una voce: niente
    reg, sc, ciclo, regole, orol = ciclo_finto()
    for d in (2.0, 3.5, 1.8):
        dalla_stanza(ciclo, orol, frase(ospite=0.65), d)
    verifica("contrario: lo stesso ospite tre volte nella stanza → una voce sola",
             ciclo.compagnia.stato() is None)
    # Compagnia spenta: niente tenuto
    reg, sc, ciclo, regole, orol = ciclo_finto()
    reg.cfg.compagnia_enabled = "spenta"
    ok = dalla_stanza(ciclo, orol, frase(carlo=0.10, amico=0.6), 3.5)
    n, how, v, t = turno(ciclo, sc, orol, frase(carlo=0.70, luca=0.20), 2.2)
    verifica("contrario: compagnia spenta → nessun segmento tenuto, nessuno stato",
             ok is False and ciclo.compagnia.segmenti_stanza() == 0 and "compagnia" not in v)
    # Ombra: lo stato nel registro, nessun effetto
    reg, sc, ciclo, regole, orol = ciclo_finto()
    reg.cfg.compagnia_enabled = "ombra"
    dalla_stanza(ciclo, orol, frase(carlo=0.10, amico=0.6), 3.5)
    n, how, v, t = turno(ciclo, sc, orol, frase(carlo=0.70, luca=0.20), 2.2)
    verifica("ombra: dalla stanza nel registro, ma nessun effetto (la finestra resta)",
             (v.get("compagnia") or {}).get("da_stanza") and not sc.compagnia
             and not ciclo._chiede_nome())
    # dimentica: via anche i segmenti
    reg, sc, ciclo, regole, orol = ciclo_finto()
    dalla_stanza(ciclo, orol, frase(carlo=0.10, amico=0.6), 3.5)
    ciclo.compagnia.dimentica()
    verifica("dimentica: via anche i segmenti della stanza", ciclo.compagnia.segmenti_stanza() == 0)


# ─────────────────────────── solo verso la prudenza ───────────────────────────

def prova_prudenza():
    # L'ospite ha la voce a 0,30 da quella di Luca e a 0,22 da Carlo: le frasi del turno lo
    # contano sconosciuto (gruppi). Luca riconosciuto dalla stanza porterebbe il suo profilo fra i
    # gruppi e l'ospite ci finirebbe dentro: la sconosciuta non deve sparire
    def ospite(k):
        return frase(carlo=0.22, luca=0.30, amico=0.62 + k)

    reg, sc, ciclo, regole, orol = ciclo_finto()
    turno(ciclo, sc, orol, frase(carlo=0.70, luca=0.20), 2.2)
    turno(ciclo, sc, orol, ospite(0.0), 2.0)
    n, how, v, t = turno(ciclo, sc, orol, ospite(0.02), 2.1)
    base = v.get("compagnia") or {}
    verifica("le frasi del turno: Carlo e un ospite → sconosciuta", base.get("sconosciute"),
             json.dumps(base))
    calcola_su = getattr(ciclo.compagnia, "_calcola_su", None)
    dalla_stanza(ciclo, orol, frase(luca=0.72, carlo=0.20), 3.4, "Luca")
    dalla_stanza(ciclo, orol, frase(luca=0.70, carlo=0.20), 2.6, "Luca")
    if calcola_su is not None:
        c = ciclo.compagnia
        tutte = sorted(c._frasi + c._stanza, key=lambda f: f.ora)
        da_sola = calcola_su(tutte)
        verifica("(il motivo: calcolato su tutte insieme la voce dell'ospite finirebbe con Luca)",
                 da_sola is not None and not da_sola["sconosciute"], json.dumps(da_sola))
    st = ciclo.compagnia.stato()
    verifica("con Luca sentito dalla stanza la voce sconosciuta resta (mai meno prudente)",
             st is not None and st["sconosciute"] and st["voci"] >= 2, json.dumps(st))
    verifica("…e la finestra senza il nome resta chiusa", ciclo._chiede_nome())
    # La stanza non dà continuità: Carlo sentito solo dalla stanza, poi una frase cortissima
    reg, sc, ciclo, regole, orol = ciclo_finto()
    dalla_stanza(ciclo, orol, frase(carlo=0.72, luca=0.20), 3.0, "Carlo")
    n, how, v, t = turno(ciclo, sc, orol, frase(carlo=0.44, luca=0.11), 0.5)
    verifica("la stanza non dà continuità: Carlo solo dalla stanza, frase di 0,5 s → nessuno",
             n is None and not t.continuita)
    # In compagnia dalla stanza la frase breve non vale più chi parlava (più prudente)
    reg, sc, ciclo, regole, orol = ciclo_finto()
    turno(ciclo, sc, orol, frase(carlo=0.72, luca=0.20), 2.0)
    n, how, v, t = turno(ciclo, sc, orol, frase(carlo=0.40, luca=0.1), 0.6, in_session=True,
                         prev="Carlo")
    verifica("contrario: Carlo da solo → la frase breve vale lui", (n, how) == ("Carlo", "breve"))
    dalla_stanza(ciclo, orol, frase(carlo=0.10, amico=0.6), 3.5)
    n, how, v, t = turno(ciclo, sc, orol, frase(carlo=0.40, luca=0.1), 0.6, in_session=True,
                         prev="Carlo")
    verifica("con un ospite sentito dalla stanza la frase breve non vale più Carlo (ospite)",
             n is None and "compagnia_senza_breve" in regole and sc.current_level == "ospite")
    n, how, v, t = turno(ciclo, sc, orol, frase(carlo=0.70, luca=0.2), 2.0)
    verifica("…Carlo riconosciuto nella frase amministra come prima (la stanza non toglie e non "
             "dà)", (n, how) == ("Carlo", "voce") and sc.current_level == "amministra")


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
    # Avvio._compagnia_dalla_stanza: solo la compagnia di quella corsia
    from calliope.main import Avvio
    finto = SimpleNamespace(corsie_tutte=tutte, insieme=True, s=SimpleNamespace(satelliti=None))
    Avvio._compagnia_dalla_stanza(finto, 1, frase(carlo=0.10, amico=0.6), 3.0, None,
                                  time.monotonic())
    verifica("Avvio: il segmento del satellite 1 solo nella compagnia della sua corsia",
             c1.ciclo.compagnia.segmenti_stanza() == 1
             and c2.ciclo.compagnia.segmenti_stanza() == 0
             and loc.ciclo.compagnia.segmenti_stanza() == 0)
    Avvio._compagnia_dalla_stanza(finto, 9, frase(carlo=0.10, amico=0.6), 3.0, None,
                                  time.monotonic())
    verifica("Avvio: un satellite senza corsia → nessuna compagnia toccata",
             c1.ciclo.compagnia.segmenti_stanza() == 1
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
    st.su_voce = lambda *a: chiamate.append(a)
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
        ignoto = frase(carlo=0.10, amico=0.6)
        reg.prossima = ignoto
        st._trascrivi(segmento(1, 2.5))
        verifica("voce sconosciuta: alla compagnia una volta, con l'impronta di chi parla (CAM++ "
                 "una volta sola) e senza nome",
                 len(chiamate) == 1 and reg.chiamate == 1 and chiamate[0][0] == 1
                 and chiamate[0][1] is ignoto and chiamate[0][3] is None
                 and abs(chiamate[0][2] - 2.5) < 1e-6, str([c[0] for c in chiamate]))
        s_fine = chiamate[0][4] if chiamate else None
        verifica("con l'istante del segmento (monotonic, prima di adesso)",
                 s_fine is not None and s_fine <= time.monotonic())
        righe = st.registro(1).righe()
        verifica("niente impronta nella riga della stanza",
                 righe and all("emb" not in r for r in righe), str(righe and list(righe[-1])))
        reg.prossima = frase(carlo=0.72, luca=0.20)
        st._trascrivi(segmento(2, 2.0))
        verifica("Carlo riconosciuto dalla voce → alla compagnia con il nome",
                 len(chiamate) == 2 and chiamate[1][3] == "Carlo")
        reg.prossima = frase(carlo=0.44, luca=0.10)
        st._trascrivi(segmento(3, 2.0))
        verifica("zona grigia → senza nome (sconosciuta, come al turno)",
                 len(chiamate) == 3 and chiamate[2][3] is None)
        reg.prossima, prima = ignoto, reg.chiamate
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
        st.su_voce = lambda *a: 1 / 0
        st._trascrivi(segmento(7, 2.5))
        verifica("un guasto della compagnia non ferma la stanza",
                 any(r.get("segmento") == 7 for r in st.registro(1).righe()))
    finally:
        st.chiudi()
    # Stanza spenta: niente Stanza, quindi niente segmenti (come prima)
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
    st.su_voce = lambda sat, emb, voce_s, nome, ora: ciclo.compagnia.osserva_stanza(
        emb, voce_s, nome, ora)
    try:
        ignoto = frase(carlo=0.10, amico=0.6).astype(np.float32)
        reg.prossima = ignoto
        for i in range(3):
            st._trascrivi(segmento(10 + i, 2.5))
        reg.prossima = frase(carlo=0.72, luca=0.20)
        st._trascrivi(segmento(20, 2.5))         # Carlo: la sua riga va su disco (tenuta)
        st.tenuta.attendi()
        n, how, v, t = riconosci(ciclo, sc, frase(carlo=0.70, luca=0.20), 2.2)
        c = v.get("compagnia") or {}
        verifica("la voce sconosciuta della stanza conta (con la stanza vera)",
                 c.get("sconosciute") and c.get("da_stanza"), json.dumps(c))
        firme = [np.asarray(ignoto, dtype=np.float32).tobytes()[:64],
                 (ignoto / np.linalg.norm(ignoto)).astype(np.float32).tobytes()[:64],
                 np.asarray(ignoto, dtype=np.float64).tobytes()[:64]]
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
         "regole": ["voci_compagnia"]}]
    d = compagnia_mod.riassunto(turni).get("2026-10-17", {})
    verifica("stato --turni: quante dalla stanza e la regola",
             d.get("in_compagnia") == 2 and d.get("da_stanza") == 1
             and d.get("regole", {}).get("compagnia_da_stanza") == 1, json.dumps(d))
    t = compagnia_mod.testo(compagnia_mod.riassunto(turni))
    verifica("stato --turni: il testo dice «dalla stanza 1»", "dalla stanza 1" in t, t)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    for nome, f in (("il caso del 17/10", prova_caso), ("i contrari", prova_contrari),
                    ("solo verso la prudenza", prova_prudenza), ("le corsie", prova_corsie),
                    ("la stanza", prova_stanza), ("solo in memoria", prova_solo_memoria),
                    ("stato --turni", prova_riassunto)):
        prova(nome, f)
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    sys.exit(1 if errori else 0)
