"""
Prova a secco della ritrascrizione a blocchi della corsia lenta (15/10/2026,
calliope/stanza/lenta.py, `stanza_lenta_blocchi`).

Caso vero del 15/10 (DGX, whisper-server dei turni): una frase di un ragazzo in auto spezzata
dalla stanza in tre segmenti (5,5, 4,5 e 2,9 s) trascritti male uno per uno e bene uniti. Qui
con i finti di prova_stanza_lenta.py (Whisper finto, impronte dall'ampiezza, orologio finto):

- i segmenti consecutivi della stessa persona sullo stesso satellite si uniscono (0,3 s di
  silenzio fra uno e l'altro) e si ritrascrivono una volta, senza prompt, con la precedenza
  LENTA; il turno passa davanti (la coda vera di `STTCondiviso`);
- il blocco si chiude quando parla un'altra persona, Calliope, una voce sconosciuta diversa, una
  riga qualunque in mezzo; dopo una pausa lunga della stessa persona
  (`stanza_lenta_blocchi_pausa_s`; con 0 no, e la pausa più lunga va nelle misure); al tetto
  (si spezza al confine di segmento); quando il satellite si scollega, la stanza va in pausa,
  dopo l'attesa massima; «dimentica» li butta;
- «ombra»: le righe restano quelle di prima, il testo del blocco nel banco; «attivo»: il testo
  ridistribuito sui segmenti è una versione nuova (2, o 3 sopra una 2) in sola aggiunta, col
  campo `blocco`, sul disco della tenuta e nella ricerca; il guardiano aspetta (`pendente`);
- contrari: spento, un segmento solo, allucinazione, meno parole che segmenti, voce sconosciuta
  e persona di casa, due persone alternate, misure senza parole e la riga di `stato --turni`,
  banco solo per le voci di casa, il banco manuale che salta i testi dei blocchi, configurazione.

Nomi di fantasia (Carlo amministra, Nicola ha 14 anni). ~3 s.
"""

import base64
import contextlib
import importlib.util
import io
import json
import os
import re
import wave
import shutil
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

import prova_stanza_lenta as B  # noqa: E402 — i finti della corsia lenta
from calliope.config import Config  # noqa: E402
from calliope.stanza import banco as banco_mod  # noqa: E402
from calliope.stanza import coda as coda_mod  # noqa: E402
from calliope.stanza import lenta as L  # noqa: E402
from calliope.stanza import misure as misure_mod  # noqa: E402
from calliope.stanza.registro import DETTO_CALLIOPE, RIGA  # noqa: E402

SR = 16000
errori = 0
BLOCCHI: dict = {}           # marcatore del primo segmento → testo del blocco


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio and not ok
                                                  else ""), flush=True)


class STTBlocchi(B.STTFinto):
    """Il Whisper finto: la corsia veloce come in prova_stanza_lenta, la precedenza LENTA (qui
    solo i blocchi: la ritrascrizione dei segmenti è spenta) dal testo del blocco."""

    def transcribe(self, audio, priorita=0, prompt=None, beam=None):
        if priorita != coda_mod.LENTA:
            return super().transcribe(audio, priorita, prompt, beam)
        m = int(round(float(audio[0]) * 1000))
        self.chiamate.append({"priorita": priorita, "prompt": prompt, "beam": beam, "m": m,
                              "s": len(audio) / SR})
        t = BLOCCHI.get(m, "")
        self.ultima_scartata = None
        if t.startswith("!"):
            self.ultima_scartata = t[1:]
            return ""
        return t


def cfg_b(modo="attivo", **k):
    k.setdefault("stanza_lenta_ritrascrivi", "no")
    return B.cfg_base(stanza_lenta_blocchi=modo, **k)


def nuova(cfg, **k):
    stt = STTBlocchi()
    st, le = B.nuova(cfg, stt, **k)
    return st, le, stt


def blocchi_mis(st, esito=None):
    return [r for r in st.misure.memoria if r["tipo"] == "lenta_blocco"
            and (esito is None or r.get("esito") == esito)]


def lente(stt):
    return [x for x in stt.chiamate if x["priorita"] == coda_mod.LENTA]


TESTO_VERO = ("Italiani WMO 2025 argento, mondiali WMO 2025 argento, europei WMO 2026 euro. "
              "C'è mondiale argento, i mondiali.")


def parla_ragazzo(st, c, base, amp=0.2, prima=None):
    """I tre segmenti del caso vero (5,5, 4,5 e 2,9 s) con i testi di allora."""
    BLOCCHI[base] = TESTO_VERO
    testi = prima or ("italiani WMO 2.500, mondiali WMO 2.500.",
                      "2025 ARCENTO, europei WMO 2026 OR.", "c'è mondiale argento i mondiali")
    return [B.parla(st, c, base + 2 * i, [(amp, d)], testi=(t, t))
            for i, (d, t) in enumerate(zip((5.5, 4.5, 2.9), testi))]


# ─────────────────────────── 1. ombra e attivo ───────────────────────────
def prova_ombra():
    cfg = cfg_b("ombra")
    st, le, stt = nuova(cfg)
    c = B.Coll(41, "auto")
    segs = parla_ragazzo(st, c, 401)
    s_c = B.parla(st, c, 407, [(0.1, 2.0)], testi=("Bravo.",) * 2)
    le.giro(B.tardi(cfg))
    ch = lente(stt)
    verifica("ombra: un blocco solo ritrascritto, i tre segmenti uniti con 0,3 s fra uno e "
             "l'altro, senza prompt, precedenza LENTA",
             len(ch) == 1 and abs(ch[0]["s"] - (5.5 + 4.5 + 2.9 + 0.6)) < 0.05
             and ch[0]["prompt"] == "", str(ch))
    righe = [B.riga_di(st, 41, s)[0] for s in segs]
    verifica("ombra: le righe restano quelle di prima (versione 1)",
             all(r["versione"] == 1 for r in righe)
             and righe[1]["testo"] == "2025 ARCENTO, europei WMO 2026 OR.", str(righe))
    m = blocchi_mis(st, "cambiato")
    verifica("ombra: misura del blocco (3 segmenti, durata, chiuso dalla voce di Carlo, non "
             "applicato, senza parole)",
             len(m) == 1 and m[0]["segmenti"] == 3 and m[0]["modo"] == "ombra"
             and m[0]["chiusura"] == "altra_voce" and not m[0]["applicato"]
             and abs(m[0]["durata_s"] - 13.5) < 0.05 and m[0]["pausa_max_s"] < 1.5
             and m[0]["testo_cambiato"] and "testo" not in m[0], str(m))
    verifica("ombra: il segmento di Carlo da solo non è un blocco (misura «singolo»)",
             len(blocchi_mis(st, "singolo")) == 1 and B.riga_di(st, 41, s_c)[0]["versione"] == 1)
    verifica("ombra: il guardiano non aspetta i blocchi (pendente solo in attivo)",
             not any(le.pendente(41, s) for s in segs))
    st.chiudi()


def prova_attivo():
    from calliope.stanza.cerca import Chi, cerca
    from calliope.stanza.tenuta import Tenuta
    cfg = cfg_b("attivo")
    st, le, stt = nuova(cfg)
    st.tenuta = Tenuta(B.TMP / "blocchi.db", registry=None, log=lambda m: None)
    c = B.Coll(42, "auto")
    st._info[42] = {"nome": "auto", "stanza": "auto", "canale": "satellite"}
    # Il primo segmento con la voce di Carlo debole (zona grigia → v2 dalla corsia lenta)
    BLOCCHI[411] = ("Domani andiamo al lago con la barca nuova. Porto io le canne da pesca e "
                    "anche il cestino.")
    s1 = B.parla(st, c, 411, [(0.12, 3.0)], testi=("Domani andiamo al lago con la",) * 2)
    s2 = B.parla(st, c, 413, [(0.1, 3.0)], testi=("barca nova. Porto io le cane",) * 2)
    s3 = B.parla(st, c, 415, [(0.1, 3.0)], testi=("da pesca e anche il cestino.",) * 2)
    st.tenuta.attendi()
    verifica("attivo: i segmenti in un blocco aperto sono «pendenti» per il guardiano",
             le.pendente(42, s1) and le.pendente(42, s3))
    le.giro(B.tardi(cfg))
    st.tenuta.attendi()
    rr = [B.riga_di(st, 42, s) for s in (s1, s2, s3)]
    verifica("attivo: una riga per segmento", all(len(x) == 1 for x in rr), str(rr))
    rr = [x[0] for x in rr]
    unito = " ".join(r["testo"] for r in rr)
    verifica("attivo: il testo del blocco ridistribuito sui segmenti (nessuna parola persa né "
             "ripetuta)", unito == BLOCCHI[411], unito)
    verifica("attivo: versione nuova sopra l'ultima (3 sopra la 2 della zona grigia, 2 sopra "
             "la 1, il terzo pezzo uguale resta), col campo blocco e sostituisce",
             [r["versione"] for r in rr] == [3, 2, 1]
             and all(r["blocco"]["id"] == s1 and r["blocco"]["segmenti"] == 3 for r in rr[:2])
             and [r["blocco"]["parte"] for r in rr[:2]] == [0, 1] and "blocco" not in rr[2]
             and all(r["sostituisce"] and r["rivista"]["testo"] for r in rr[:2])
             and rr[0]["sicurezza"] == "voce" and rr[0]["nome"] == "Carlo", str(rr))
    v = [e.dati["versione"] for e in st.registro(42).eventi(RIGA)
         if e.dati.get("segmento") == s2]
    verifica("attivo: in sola aggiunta (la versione 1 resta nel registro)", v == [1, 2], str(v))
    verifica("attivo: dopo la ritrascrizione niente più pendente",
             not le.pendente(42, s1) and le.blocchi_in_attesa() == 0)
    db = st.tenuta.db.execute("SELECT segmento, versione, testo FROM righe ORDER BY inizio")
    db = db.fetchall()
    verifica("tenuta: su disco la versione del blocco al posto di quella di prima",
             [x[1] for x in db] == [3, 2, 1]
             and " ".join(x[2] for x in db) == BLOCCHI[411], str(db))
    es = cerca(st, cfg, Chi("p-carlo", "Carlo", tutore_di={"p-nicola"}, sat=42),
               "barca nuova", aspetta=False)
    verifica("stanza_cerca trova il testo del blocco", es.esito == "trovato"
             and "barca nuova" in es.testo and "nova" not in es.testo, es.testo)
    m = blocchi_mis(st, "cambiato")
    verifica("attivo: misura applicato con 2 righe nuove, chiuso dalla pausa lunga (8 s di "
             "serie, nessun seguito)", len(m) == 1 and m[0]["applicato"] and m[0]["righe"] == 2
             and m[0]["chiusura"] == "pausa_lunga", str(m))
    st.tenuta.chiudi()
    st.chiudi()


# ─────────────────────────── 2. chi chiude il blocco ───────────────────────────
def prova_chiusure():
    # Due persone alternate: nessun blocco
    cfg = cfg_b("attivo")
    st, le, stt = nuova(cfg)
    c = B.Coll(43, "sala")
    B.parla(st, c, 421, [(0.1, 2.0)], testi=("Allora.",) * 2)
    B.parla(st, c, 423, [(0.2, 2.0)], testi=("Sì.",) * 2)
    B.parla(st, c, 425, [(0.1, 2.0)], testi=("Va bene.",) * 2)
    le.giro(B.tardi(cfg))
    verifica("persona diversa che spezza: Carlo, Nicola, Carlo → nessun blocco",
             lente(stt) == [] and len(blocchi_mis(st, "singolo")) == 3)
    # Calliope in mezzo
    BLOCCHI[431] = "Che tempo fa domani? Grazie."
    a = B.parla(st, c, 431, [(0.1, 2.0)], testi=("Che tempo fa domani?",) * 2)
    st.registro(43).aggiungi(DETTO_CALLIOPE, testo="Domani sole.", inizio=B.adesso() - 0.25,
                             fine=B.adesso() - 0.1)
    b = B.parla(st, c, 433, [(0.1, 2.0)], testi=("Grazie.",) * 2)
    le.giro(B.tardi(cfg))
    verifica("Calliope in mezzo chiude il blocco: nessuna ritrascrizione unita",
             lente(stt) == [] and B.riga_di(st, 43, a)[0]["versione"] == 1
             and B.riga_di(st, 43, b)[0]["versione"] == 1)
    st.chiudi()
    # Il tetto: cinque segmenti di 8 s → 3 (24,6 s) + 2 (16,3 s)
    cfg = cfg_b("ombra")
    st, le, stt = nuova(cfg)
    c = B.Coll(44, "studio")
    BLOCCHI[441] = "Primo pezzo lungo."
    BLOCCHI[447] = "Secondo pezzo lungo."
    for i in range(5):
        B.parla(st, c, 441 + 2 * i, [(0.1, 8.0)], testi=(f"pezzo {i}",) * 2)
    le.giro(B.tardi(cfg))
    ch = lente(stt)
    verifica("tetto: il blocco si spezza al confine di segmento (24,6 s e 16,3 s, sotto i 25)",
             [round(x["s"], 1) for x in ch] == [24.6, 16.3], str(ch))
    ch_m = [m["chiusura"] for m in blocchi_mis(st) if m.get("esito") != "singolo"]
    verifica("tetto: chiusura «tetto» nelle misure", "tetto" in ch_m, str(ch_m))
    st.chiudi()
    # La pausa lunga: 5 s; con 0 la stessa fila resta un blocco e la pausa va nelle misure
    for pausa, attesi in ((5.0, [1]), (0.0, [2])):
        cfg = cfg_b("ombra", stanza_lenta_blocchi_pausa_s=pausa)
        st, le, stt = nuova(cfg)
        c = B.Coll(45, "cucina")
        BLOCCHI[451] = "Uno, anzi due."
        BLOCCHI[455] = "Tre, anzi quattro."
        B.parla(st, c, 451, [(0.1, 2.0)], testi=("uno",) * 2)
        B.parla(st, c, 453, [(0.1, 2.0)], testi=("due",) * 2)
        B.V[0] += 10.0
        B.parla(st, c, 455, [(0.1, 2.0)], testi=("tre",) * 2)
        B.parla(st, c, 457, [(0.1, 2.0)], testi=("quattro",) * 2)
        if pausa == 0.0:
            le.giro(B.tardi(cfg))
            verifica("pausa 0: senza seguito il blocco resta aperto (non per il silenzio)",
                     lente(stt) == [] and le.blocchi_in_attesa() == 4)
            le.giro(B.adesso() + 700)
        else:
            le.giro(B.tardi(cfg))
        mis = [m for m in blocchi_mis(st) if m.get("esito") not in ("singolo", None)]
        if pausa:
            verifica("pausa lunga (5 s): 10 s della stessa persona separano due blocchi",
                     [m["segmenti"] for m in mis] == [2, 2]
                     and mis[0]["chiusura"] == "pausa_lunga", str(mis))
        else:
            verifica("pausa 0: un blocco di quattro, chiuso dall'attesa massima, con la pausa "
                     "più lunga (~11 s) nelle misure",
                     [m["segmenti"] for m in mis] == [4] and mis[0]["chiusura"] == "attesa"
                     and 10.0 <= mis[0]["pausa_max_s"] < 12.0, str(mis))
        st.chiudi()
    # Voce sconosciuta: la stessa dall'impronta sì, poi Carlo no
    cfg = cfg_b("ombra")
    st, le, stt = nuova(cfg)
    c = B.Coll(46, "ingresso")
    BLOCCHI[461] = "Buonasera, sono il vicino."
    B.parla(st, c, 461, [(0.35, 2.0)], testi=("Buonasera",) * 2)
    B.parla(st, c, 463, [(0.35, 2.0)], testi=("sono il vicino",) * 2)
    B.parla(st, c, 465, [(0.1, 2.0)], testi=("Prego.",) * 2)
    le.giro(B.tardi(cfg))
    ch = lente(stt)
    verifica("voce sconosciuta: due segmenti della stessa impronta in un blocco, Carlo fuori",
             len(ch) == 1 and abs(ch[0]["s"] - 4.3) < 0.05, str(ch))
    st.chiudi()
    # Scollegato, pausa della stanza, «dimentica»
    cfg = cfg_b("attivo", stanza_lenta_blocchi_pausa_s=0.0)
    st, le, stt = nuova(cfg)
    c = B.Coll(47, "camera")
    BLOCCHI[471] = "A b."
    B.parla(st, c, 471, [(0.1, 2.0)], testi=("a",) * 2)
    B.parla(st, c, 473, [(0.1, 2.0)], testi=("b",) * 2)
    le.giro(B.tardi(cfg))
    verifica("aperto finché non succede niente", le.blocchi_in_attesa() == 2)
    le.scollegato(47)
    le.giro(B.tardi(cfg))
    m = blocchi_mis(st, "uguale")
    verifica("satellite scollegato: il blocco si chiude e si ritrascrive",
             len(lente(stt)) == 1 and m and m[-1]["chiusura"] == "scollegato", str(m))
    B.parla(st, c, 475, [(0.1, 2.0)], testi=("c",) * 2)
    B.parla(st, c, 477, [(0.1, 2.0)], testi=("d",) * 2)
    le.giro(B.tardi(cfg))
    st.pausa(47, "ospiti")
    verifica("pausa della stanza: il blocco si chiude e non si ritrascrive in pausa",
             not le.passo_blocco(B.tardi(cfg)) and len(lente(stt)) == 1)
    st.dimentica(47)
    verifica("«dimentica» butta i blocchi", le.blocchi_in_attesa() == 0)
    st.chiudi()


# ─────────────────────────── 3. contrari ───────────────────────────
def prova_contrari():
    cfg = cfg_b("spento")
    st, le, stt = nuova(cfg)
    c = B.Coll(48, "sala")
    segs = parla_ragazzo(st, c, 481)
    le.giro(B.tardi(cfg))
    verifica("spento: nessun blocco, nessuna chiamata, nessuna misura",
             lente(stt) == [] and blocchi_mis(st) == [] and le.blocchi_in_attesa() == 0
             and all(B.riga_di(st, 48, s)[0]["versione"] == 1 for s in segs))
    st.chiudi()
    for testo, esito in (("!sottotitoli", "allucinazione"),
                         ("sì sì sì sì sì sì sì", "allucinazione"),
                         ("Argento.", "non_distribuibile"),
                         ("italiani WMO 2.500, mondiali WMO 2.500. 2025 ARCENTO, europei WMO "
                          "2026 OR. c'è mondiale argento i mondiali", "uguale")):
        cfg = cfg_b("attivo")
        st, le, stt = nuova(cfg)
        c = B.Coll(49, "auto")
        segs = parla_ragazzo(st, c, 491)
        BLOCCHI[491] = testo
        le.giro(B.tardi(cfg))
        m = blocchi_mis(st)
        verifica(f"contrario «{testo[:20]}»: esito {esito}, righe di prima",
                 m and m[-1]["esito"] == esito and not m[-1]["applicato"]
                 and all(B.riga_di(st, 49, s)[0]["versione"] == 1 for s in segs), str(m))
        st.chiudi()


# ─────────────────────────── 4. il turno passa davanti ───────────────────────────
def prova_precedenza():
    from calliope.corsie import STTCondiviso

    class Lento:
        def __init__(self):
            self.ordine = []

        def transcribe(self, audio, prompt=None, **k):
            self.ordine.append(round(len(audio) / SR, 1))
            return "x"
    finto = Lento()
    sc = STTCondiviso(finto)
    cfg = cfg_b("attivo")
    st, le, _ = nuova(cfg)
    le.stt = sc
    tieni = threading.Event()

    def occupa():
        with sc._lock.tieni(coda_mod.STANZA):
            tieni.wait(5)
    t0 = threading.Thread(target=occupa)
    t0.start()
    B.aspetta(lambda: sc._lock.chi is not None)
    tb = threading.Thread(target=lambda: le._trascrivi_blocco(np.zeros(2 * SR, np.float32)))
    tb.start()
    B.aspetta(lambda: len(sc._lock._attese) == 1)
    tt = threading.Thread(target=lambda: sc.transcribe(np.zeros(SR, np.float32)))
    tt.start()
    B.aspetta(lambda: len(sc._lock._attese) == 2)
    verifica("un turno che aspetta: la DGX non è libera (niente blocchi nuovi)",
             sc.aspetta_turno() and not le.libera())
    tieni.set()
    for t in (t0, tb, tt):
        t.join(5)
    verifica("il turno passa davanti al blocco che aspettava prima di lui",
             finto.ordine == [1.0, 2.0], str(finto.ordine))
    st.chiudi()


# ─────────────────────────── 5. banco, misure, configurazione ───────────────────────────
def prova_banco_misure():
    cfg = cfg_b("ombra", registro="banco-blocchi", stanza_audio_banco_giorni=7)
    b = banco_mod.Banco(cfg, log=lambda m: None)
    st, le, stt = nuova(cfg, banco=b)
    c = B.Coll(50, "auto")
    st._info[50] = {"nome": "auto", "stanza": "auto", "canale": "satellite"}
    segs = parla_ragazzo(st, c, 501)
    BLOCCHI[507] = "Buonasera a tutti."
    B.parla(st, c, 507, [(0.35, 2.0)], testi=("Buonasera",) * 2)
    B.parla(st, c, 509, [(0.35, 2.0)], testi=("a tutti",) * 2)
    le.giro(B.tardi(cfg))
    d = banco_mod.cartella(cfg)
    bj = sorted(d.rglob("*-blocco-*.json"))
    meta = json.loads(bj[0].read_text(encoding="utf-8")) if bj else {}
    verifica("banco: il testo del blocco accanto ai segmenti (allora, blocco, pezzi), solo per "
             "le voci di casa (la voce sconosciuta no)",
             len(bj) == 1 and meta.get("testo_blocco") == TESTO_VERO
             and [x["testo"] for x in meta["allora"]][0].startswith("italiani")
             and meta["segmenti"] == segs and len(meta["pezzi"]) == 3
             and meta["persone"] == ["p-nicola"] and meta["modo"] == "ombra"
             and len(list(d.rglob("*.wav"))) == 3, str(meta))
    spec = importlib.util.spec_from_file_location(
        "banco_stanza_lenta", Path(B.__file__).resolve().parent / "manuali" /
        "banco_stanza_lenta.py")
    M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)
    M.modo_banco({"banco": str(d)}, cfg)
    tsv = (d / "riferimento.tsv").read_text(encoding="utf-8").splitlines()
    verifica("il banco manuale salta i testi dei blocchi (solo i segmenti col loro audio)",
             len(tsv) == 1 + 3, str(tsv))
    # Lo script di revisione (prove/manuali/blocchi_stanza.py) con un Whisper finto
    spec = importlib.util.spec_from_file_location(
        "blocchi_stanza", Path(B.__file__).resolve().parent / "manuali" / "blocchi_stanza.py")
    S = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(S)
    S.trascrivi = lambda url, modello, lingua, a: ("Testo del blocco finto.", 0.01)
    out = B.TMP / "privato" / "revisione.html"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = S.main(["--banco", str(d), "--html", str(out), "--url", "http://127.0.0.1:9/x"])
    stampato = buf.getvalue()
    h = out.read_text(encoding="utf-8") if out.exists() else ""
    a64 = re.search(r'"audio": "([A-Za-z0-9+/=]+)"', h)
    ok_wav = False
    if a64:
        with wave.open(io.BytesIO(base64.b64decode(a64.group(1)))) as w:
            ok_wav = (w.getsampwidth() == 2 and w.getframerate() == SR
                      and abs(w.getnframes() / SR - 13.5) < 0.1)
    verifica("script: un blocco dai tre segmenti del banco, la pagina con l'audio unito in WAV "
             "PCM 16 bit, il testo di allora e del blocco, le tre scelte e lo scarico",
             rc == 0 and ok_wav and "Meglio il blocco" in h and "Testo del blocco finto." in h
             and "italiani WMO" in h and "Scarica le scelte" in h
             and "Pause fra segmenti consecutivi" in stampato and "pausa    8 s" in stampato,
             stampato[-800:])

    def sg(sat, n, ini, dur, chi="persona:p-carlo"):
        return {"sat": sat, "segmento": n, "inizio": ini, "fine": ini + dur, "durata": dur,
                "chi": chi, "rel": f"{sat}/{n}"}
    fila = [sg("a", 1, 0, 5), sg("a", 2, 5.5, 5), sg("a", 3, 20, 8), sg("a", 4, 28.5, 9),
            sg("a", 5, 38, 9), sg("a", 7, 48, 2), sg("a", 8, 50.5, 2, "persona:p-nicola"),
            sg("a", 1, 53, 2, "persona:p-nicola"), sg("b", 2, 55.5, 2, "persona:p-nicola")]
    motivi: dict = {}
    bb, ch = S.blocchi(fila, 8.0, 25.0, True, motivi)
    verifica("script: blocchi chiusi da pausa lunga, tetto, buco nella numerazione, altra "
             "voce, riconnessione, altro satellite",
             [[x["segmento"] for x in b] for b in bb] == [[1, 2], [3, 4], [5], [7], [8], [1],
                                                          [2]]
             and ch.get("pausa_lunga") == 1 and ch.get("tetto") == 1 and ch.get("buco") == 1
             and ch.get("altra_voce") == 1 and ch.get("scollegato") == 1, str((bb, ch)))
    verifica("script: senza soglia la pausa lunga non separa, le pause della stessa persona",
             [[x["segmento"] for x in b] for b in S.blocchi(fila, 0.0, 1e9, True)[0]][0]
             == [1, 2, 3, 4, 5] and max(S.pause_stessa_persona(fila, True)) == 9.5)
    mis = [r for r in st.misure.memoria if r["tipo"] == "lenta_blocco"]
    rr = misure_mod.riassunto(mis)
    t = misure_mod.testo(rr)
    verifica("stato --turni: la riga dei blocchi (ritrascritti, segmenti per blocco, durata, "
             "testo cambiato, Whisper, attesa, pausa più lunga, chiusure)",
             "Blocchi della corsia lenta: 2 ritrascritti" in t and "media 2.5" in t
             and "testo cambiato in 1 (50 %)" in t and "pausa più lunga" in t
             and "altra_voce" in t, t)
    verifica("misure senza parole", all("testo" not in r and "nome" not in r for r in mis))
    st.chiudi()
    # Configurazione
    from calliope.config import LIMITI, SEZIONI, VALIDATORI
    v = VALIDATORI["stanza_lenta_blocchi"]
    ok = v(False) == "spento" and v(" Ombra ") == "ombra" and v("attivo") == "attivo"
    try:
        v("acceso")
        ok = False
    except ValueError:
        pass
    sez = next((k for k, x in SEZIONI.items() if "stanza_lenta_blocchi" in x), None)
    c0 = Config()
    verifica("configurazione: spento di serie, «no» di YAML, «acceso» rifiutato, tetto sotto "
             "i 30 s di Whisper, nella sezione della stanza",
             ok and c0.stanza_lenta_blocchi == "spento" and c0.stanza_lenta_blocchi_max_s == 25.0
             and LIMITI["stanza_lenta_blocchi_max_s"][1] < 30 and sez is not None
             and "stanza_lenta_blocchi_pausa_s" in SEZIONI[sez]
             and L.Lenta(cfg_b("forse"), st, avvia=False).blocchi_modo() == "spento")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    B._patch_orologio()
    t0 = time.monotonic()
    try:
        prova_ombra()
        prova_attivo()
        prova_chiusure()
        prova_contrari()
        prova_precedenza()
        prova_banco_misure()
    finally:
        shutil.rmtree(B.TMP, ignore_errors=True)
    tot = errori + B.errori
    print(f"\n({time.monotonic() - t0:.1f} s)")
    print("\nTutto bene." if not tot else f"\n{tot} prove non riuscite.")
    return 1 if tot else 0


if __name__ == "__main__":
    sys.exit(main())
