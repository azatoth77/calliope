"""
Prova a secco del passo 3 della conversazione di stanza (14/10/2026, decisione 0029, progetto
docs/ricerche/2026-10-13-conversazione-di-stanza.md § 3.2, § 5.1, § 5.2, § 5.4, § 6 riga 3): la
corsia lenta (calliope/stanza/lenta.py, `stanza_lenta`) e l'eccezione dell'audio del banco
(calliope/stanza/banco.py, `stanza_audio_banco_giorni`).

Con un Whisper finto (il testo dal primo campione, un altro testo con la precedenza LENTA) e
impronte finte (l'ampiezza dice chi parla):

- spenta: niente corsia, l'audio non resta;
- ritrascrizione: la riga cambiata diventa versione 2 (la 1 resta nel registro), quella uguale
  ha l'evento «uguale», il prompt con i nomi dello scambio e le parole di prima (corto), la
  precedenza LENTA dentro `STTCondiviso` dopo il turno;
- chi parla: la zona grigia corretta dalla voce della persona nello scambio (mai verso l'alto:
  niente presenze), un blocco di due voci spezzato in due righe con i tempi, le voci che si
  alternano «più voci»;
- allucinazioni: famiglia, ripetizione, riga corta vuota scartate; contrario: riga lunga che
  la ritrascrizione dà vuota resta;
- TV a strati: stanza vuota con voce sconosciuta lunga e senza pause → una riga «[TV o radio,
  N s]» senza parole nel blocco, fuori dalla ricerca e dal disco; la pubblicità già sentita;
  contrari: telefonata in vivavoce, ospite che racconta con la famiglia presente, persona di casa
  che legge ad alta voce, Home Assistant che dice spento;
- conseguenze: le righe già nella storia del modello non si rimandano, la tenuta su disco
  sostituisce la versione 1 (e la toglie per la TV), `stanza_cerca` trova la versione 2, il
  guardiano a posteriori aspetta la corsia lenta e non rigiudica una versione 2 quasi uguale (sì
  con un cambio sostanziale);
- riassunto progressivo: ogni N righe, nel blocco solo se lo scambio è più vecchio della
  finestra, in busta; DGX occupata: niente passo; audio oltre `stanza_audio_min`: scaduto;
  «dimentica» durante l'attesa;
- l'audio del banco: solo voci di casa riconosciute (adulti e minori), file 600; contrari: ospite
  nel segmento, zona grigia, conoscente, pausa, scaduta, spenta, senza corsia lenta;
  «dimentica», svuota di tutto e di una persona (anche da `Conservazione.svuota`);
- misure senza parole e la riga di `calliope stato --turni`; il piano dei modelli; la
  configurazione.

Nomi di fantasia (Carlo amministra, Nicola ha 14 anni). ~5 s.
"""

import json
import os
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from calliope import provenienza
from calliope.config import Config
from calliope.stanza import banco as banco_mod
from calliope.stanza import coda as coda_mod
from calliope.stanza import contesto as ctx
from calliope.stanza import lenta as L
from calliope.stanza import misure as misure_mod
from calliope.stanza.ascolto import Stanza
from calliope.stanza.registro import LENTA, RIASSUNTO, RIGA, RIGA_SCARTATA

TMP = Path(tempfile.mkdtemp(prefix="calliope-lenta-"))
SR = 16000
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio and not ok
                                                  else ""), flush=True)


def aspetta(cond, max_s=5.0):
    fine = time.monotonic() + max_s
    while time.monotonic() < fine:
        if cond():
            return True
        time.sleep(0.02)
    return False


# ─────────────────────────── i finti ───────────────────────────
# Chi parla dall'ampiezza: 0,1 Carlo, 0,12 Carlo «debole» (zona grigia), 0,2 Nicola, 0,35 una
# voce che nessuno conosce. Il primo campione è il marcatore della frase.
VOCI = {0.1: (0, False), 0.12: (0, True), 0.2: (1, False), 0.35: (2, False)}
NOMI = ["Carlo", "Nicola"]


def _amp(audio) -> float:
    return float(np.median(np.abs(audio[1:]))) if len(audio) > 1 else 0.0


class Voci:
    def __init__(self):
        self.users = {"Carlo": SimpleNamespace(id="p-carlo", name="Carlo", nascita=None,
                                               fascia=None, admin=True, tutori=[]),
                      "Nicola": SimpleNamespace(id="p-nicola", name="Nicola",
                                                nascita="2012-05-01", fascia=None, admin=False,
                                                tutori=["p-carlo"])}
        self.adattate = 0

    def get(self, n):
        return self.users.get(n)

    def embed(self, audio, sr):
        a = _amp(audio)
        k = min(VOCI, key=lambda x: abs(x - a))
        if abs(k - a) > 0.015:
            return np.array([0.3, 0.3, 0.3, 0.0])          # due voci insieme: nessuna
        i, debole = VOCI[k]
        v = np.zeros(4)
        v[i] = 1.0
        v[3] = 0.01 if debole else 0.0
        return v

    def classifica(self, emb):
        e = np.asarray(emb)
        out = []
        for i, n in enumerate(NOMI):
            if e[i] > 0.9:
                out.append((n, 0.45 if e[3] > 0.005 else 0.8))
            else:
                out.append((n, 0.1))
        return sorted(out, key=lambda x: -x[1])

    def adapt(self, *a, **k):
        self.adattate += 1


TESTI = {}       # marcatore → (v1, v2)


class STTFinto:
    def __init__(self):
        self.chiamate = []
        self.ultima_scartata = None
        self.ultima_confidenza = None

    def transcribe(self, audio, priorita=0, prompt=None, beam=None):
        m = int(round(float(audio[0]) * 1000))
        self.chiamate.append({"priorita": priorita, "prompt": prompt, "beam": beam, "m": m,
                              "s": len(audio) / SR})
        self.ultima_scartata = None
        v1, v2 = TESTI.get(m, (f"frase {m}", "PARTI" if m >= 100 else f"frase {m}"))
        if priorita != coda_mod.LENTA:
            return v1
        if v2 == "PARTI":
            a = _amp(audio)
            k = min(VOCI, key=lambda x: abs(x - a))
            return {0.1: "Io porto le bibite.", 0.2: "E io la torta di mele.",
                    0.35: "Buonasera a tutti."}.get(k, "boh")
        if v2.startswith("!"):
            self.ultima_scartata = v2[1:]
            return ""
        return v2


class Coll:
    def __init__(self, sat, nome):
        self.satellite = {"id": sat, "nome": nome}
        self.canale, self.stanza = "satellite", nome
        self.frasi_voce, self.suonate = {}, {}

    def ritardo(self):
        return 0.0


def cfg_base(**k) -> Config:
    c = Config()
    c.stanza, c.stanza_lenta = "ombra", True
    c.turn_log_dir = str(TMP / k.pop("registro", "registro"))
    c.speaker_min_voice_s = 0.5
    c.stanza_lenta_libera_s = 0.0
    for a, v in k.items():
        setattr(c, a, v)
    return c


def nuova(cfg, stt=None, **k):
    st = Stanza(cfg, stt or STTFinto(), registry=Voci(),
                misure=misure_mod.Misure(cfg.turn_log_dir), log=lambda m: None)
    le = L.Lenta(cfg, st, log=LOG.append, avvia=False, **k)
    st.lenta = le
    return st, le


LOG: list = []
_ID = iter(range(1, 10 ** 6))
# Un orologio finto per la stanza: i segmenti uno dopo l'altro come nella realtà (inizio, fine,
# pausa di 0,3 s), senza aspettare davvero i secondi di parlato
OFF = [0.0]
V = [0.0]


def _patch_orologio():
    import calliope.stanza.ascolto as asc
    asc.time = SimpleNamespace(time=lambda: time.time() + OFF[0], monotonic=time.monotonic,
                               sleep=time.sleep)


def adesso() -> float:
    return time.time() + V[0]


def parla(st, coll, marcatore, pezzi, chiusura="silenzio", testi=None):
    """Un segmento: `pezzi` = [(ampiezza, secondi)]; `testi` = (v1, v2) del Whisper finto."""
    if testi is not None:
        TESTI[marcatore] = testi
    x = np.concatenate([np.full(int(s * SR), a, np.float32) for a, s in pezzi])
    x[0] = marcatore / 1000
    ident = next(_ID)
    durata = sum(s for _, s in pezzi)
    OFF[0] = V[0]
    st.inizio(coll, {"id": ident, "fa_s": 0.0})
    OFF[0] = V[0] + durata + 0.7
    st.pezzo(coll, ident, (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    st.fine(coll, {"id": ident, "chiusura": chiusura, "parlato_ms": int(durata * 1000),
                   "durata_s": durata})
    V[0] += durata + 1.0
    ok = aspetta(lambda: any(e.dati.get("segmento") == ident
                             for e in st.registro(coll.satellite["id"]).eventi()
                             if e.tipo in (RIGA, RIGA_SCARTATA)))
    if not ok:
        print(f"   (segmento {ident} non trascritto)")
    time.sleep(0.01)
    return ident


def tardi(cfg):
    return adesso() + float(cfg.stanza_lenta_quiete_s) + 1


def riga_di(st, sat, seg):
    return [r for r in st.registro(sat).righe() if r.get("segmento") == seg]


# ─────────────────────────── 1. spenta ───────────────────────────
def prova_spenta():
    from calliope.stanza import load_lenta
    cfg = cfg_base(stanza_lenta=False)
    st = Stanza(cfg, STTFinto(), registry=Voci(), misure=None, log=lambda m: None)
    verifica("spenta: load_lenta non crea niente", load_lenta(cfg, st) is None
             and st.lenta is None)
    c = Coll(1, "cucina")
    seg = parla(st, c, 11, [(0.1, 2.0)])
    verifica("spenta: la riga c'è e nessun audio resta (niente corsia lenta)",
             len(riga_di(st, 1, seg)) == 1 and st.lenta is None)
    st.chiudi()
    cfg2 = cfg_base(stanza="spenta")
    verifica("con la stanza spenta la corsia lenta non c'è", load_lenta(cfg2, st) is None)
    cfg3 = cfg_base()
    le = load_lenta(cfg3, st, log=lambda m: None)
    verifica("accesa: load_lenta la lega alla stanza, senza riassunto senza guardiano",
             le is not None and st.lenta is le and le.riassuntore is None and le.banco is None)
    le.chiudi()


# ─────────────────────────── 2. ritrascrizione ───────────────────────────
def prova_ritrascrizione():
    cfg = cfg_base(stanza_lenta_prompt_caratteri=40, stanza_lenta_prompt="si")
    stt = STTFinto()
    st, le = nuova(cfg, stt)
    c = Coll(1, "cucina")
    s1 = parla(st, c, 21, [(0.1, 2.0)], testi=("Domani andiamo al lago.",
                                               "Domani andiamo al lago."))
    s2 = parla(st, c, 23, [(0.2, 2.0)], testi=("Porto la cana da pesca nova.",
                                               "Porto la canna da pesca nuova."))
    verifica("in attesa: i due segmenti aspettano la corsia lenta",
             le.pendente(1, s1) and le.pendente(1, s2) and le.in_attesa() == 2)
    verifica("lo scambio parla ancora: niente di dovuto", le.dovuti() == [])
    n = le.giro(tardi(cfg))
    verifica("lo scambio tace: due segmenti rivisti", n == 2 and le.in_attesa() == 0, str(n))
    r2 = riga_di(st, 1, s2)
    verifica("la riga cambiata è la versione 2 nella proiezione",
             len(r2) == 1 and r2[0]["versione"] == 2
             and r2[0]["testo"] == "Porto la canna da pesca nuova."
             and r2[0]["sostituisce"] and r2[0]["rivista"]["testo"]
             and not r2[0]["rivista"]["chi"], str(r2))
    v1 = [e for e in st.registro(1).eventi(RIGA) if e.dati.get("segmento") == s2]
    verifica("in sola aggiunta: la versione 1 resta nel registro",
             [e.dati["versione"] for e in v1] == [1, 2])
    r1 = riga_di(st, 1, s1)
    verifica("la riga uguale resta la versione 1, con l'evento «uguale»",
             r1[0]["versione"] == 1 and any(e.dati.get("segmento") == s1
                                            and e.dati.get("esito") == "uguale"
                                            for e in st.registro(1).eventi(LENTA)))
    lente = [x for x in stt.chiamate if x["priorita"] == coda_mod.LENTA]
    verifica("la ritrascrizione ha la precedenza LENTA e il beam della corsia lenta",
             len(lente) == 2 and all(x["beam"] == 8 for x in lente))
    p2 = lente[1]["prompt"]
    verifica("il prompt dice chi parla nello scambio e le parole di prima, corto",
             p2.startswith("Parlano Carlo e Nicola.") and "lago" in p2
             and len(p2) <= len("Parlano Carlo e Nicola.") + 41, p2)
    le_auto = L.Lenta(cfg_base(), st, log=LOG.append, avvia=False)
    verifica("prompt «auto»: spento con lo stesso Whisper dei turni, acceso con uno suo",
             not le_auto.prompt_acceso()
             and L.Lenta(cfg_base(), st, stt=stt, avvia=False).prompt_acceso()
             and L.Lenta(cfg_base(stanza_lenta_stt_url="http://127.0.0.1:9"), st,
                         avvia=False).prompt_acceso()
             and not L.Lenta(cfg_base(stanza_lenta_prompt="no"), st, stt=stt,
                             avvia=False).prompt_acceso())
    verifica("i segmenti rivisti non tornano", le.giro(tardi(cfg)) == 0
             and st.registro(1).rivisti() >= {s1, s2})
    # STTCondiviso: la precedenza vera
    from calliope.corsie import STTCondiviso
    sc = STTCondiviso(stt)
    sc.transcribe(np.zeros(SR, np.float32), priorita=coda_mod.LENTA, prompt="x", beam=3)
    verifica("STTCondiviso passa la precedenza LENTA, il prompt e il beam",
             stt.chiamate[-1]["prompt"] == "x" and stt.chiamate[-1]["beam"] == 3)
    st.chiudi()
    return cfg


# ─────────────────────────── 3. chi parla ───────────────────────────
def prova_chi():
    cfg = cfg_base()
    st, le = nuova(cfg)
    c = Coll(2, "sala")
    sentite = []
    vera = st._sentita
    st._sentita = lambda *a, **k: (sentite.append(a), vera(*a, **k))
    s0 = parla(st, c, 31, [(0.1, 3.0)], testi=("Allora ci vediamo alle otto.",) * 2)
    s1 = parla(st, c, 33, [(0.12, 2.0)], testi=("Va bene per tutti.",) * 2)
    g = riga_di(st, 2, s1)[0]
    verifica("la corsia veloce: Carlo debole in zona grigia", g["sicurezza"] == "grigia"
             and g["nome"] == "Carlo", str(g))
    s2 = parla(st, c, 35, [(0.1, 4.0), (0.2, 4.0)],
               testi=("Io porto le bibite e io la torta di mele.",
                        "Io porto le bibite. E io la torta di mele."))
    s3 = parla(st, c, 37, [(0.1, 3.0), (0.2, 3.0), (0.1, 3.0), (0.2, 3.0)],
               testi=("Sì no sì no.", "Sì no sì no ma dai."))
    prima = len(sentite)
    le.giro(tardi(cfg))
    g2 = riga_di(st, 2, s1)[0]
    verifica("zona grigia corretta dalla voce di Carlo nello scambio: versione 2 «voce»",
             g2["versione"] == 2 and g2["sicurezza"] == "voce" and g2["nome"] == "Carlo"
             and g2["rivista"]["chi"] and not g2["rivista"]["testo"], str(g2))
    verifica("mai verso l'alto: nessuna presenza aperta, nessuna impronta aggiornata",
             len(sentite) == prima and st.registry.adattate == 0)
    d = riga_di(st, 2, s2)
    verifica("blocco con due voci: spezzato in due righe, Carlo poi Nicola, coi tempi",
             len(d) == 2 and [x["nome"] for x in d] == ["Carlo", "Nicola"]
             and d[0]["testo"] == "Io porto le bibite." and d[1]["testo"] == "E io la torta di mele."
             and d[0]["parte"] == 0 and d[1]["parte"] == 1 and d[1]["minore"]
             and d[0]["fine"] <= d[1]["inizio"] + 1.0, str(d))
    p = riga_di(st, 2, s3)
    verifica("voci che si alternano: una riga «più voci (Carlo, Nicola?)», nessuna sicurezza",
             len(p) == 1 and p[0]["chi"] == "piu_voci" and p[0]["sicurezza"] == "nessuna"
             and ctx.etichetta(p[0]) == "più voci (Carlo, Nicola?)" and p[0]["minore"], str(p))
    mis = [r for r in st.misure.memoria if r["tipo"] == "lenta"]
    es = {r["esito"] for r in mis}
    verifica("misure: divisa, più voci, attribuzione corretta, tempi, senza parole",
             {"divisa", "piu_voci", "cambiata"} <= es
             and sum(1 for r in mis if r.get("attribuzione")) >= 3
             and all("testo" not in r and "nome" not in r for r in mis)
             and all(r.get("stt_s") is not None for r in mis), str(mis))
    st.chiudi()


# ─────────────────────────── 4. allucinazioni ───────────────────────────
def prova_allucinazioni():
    cfg = cfg_base()
    st, le = nuova(cfg)
    c = Coll(3, "studio")
    a = parla(st, c, 41, [(0.1, 1.5)], testi=("Grazie a tutti.", "!saluti_video"))
    b = parla(st, c, 43, [(0.1, 2.0)], testi=("Sì sì.", "sì sì sì sì sì sì"))
    d = parla(st, c, 45, [(0.1, 1.0)], testi=("Eh.", ""))
    e = parla(st, c, 47, [(0.1, 3.0)], testi=("Domani porto io il pane fresco.", ""))
    le.giro(tardi(cfg))
    vive = {r.get("segmento") for r in st.registro(3).righe()}
    scart = {x.dati.get("segmento"): x.dati for x in st.registro(3).eventi(RIGA_SCARTATA)}
    verifica("famiglia di Whisper sulla ritrascrizione: scartata «allucinazione»",
             a not in vive and scart.get(a, {}).get("motivo") == "allucinazione"
             and scart[a].get("lenta"))
    verifica("la stessa parola sei volte: scartata (ripetizione)", b not in vive
             and scart.get(b, {}).get("regola") == "ripetizione")
    verifica("riga corta vuota alla ritrascrizione: scartata", d not in vive)
    verifica("contrario: riga lunga vuota alla ritrascrizione resta com'era (v2_vuota)",
             e in vive and riga_di(st, 3, e)[0]["versione"] == 1
             and any(x.dati.get("esito") == "v2_vuota" for x in st.registro(3).eventi(LENTA)))
    verifica("allucinazione: contrari della regola", L.allucinazione("sì, sì, va bene") is None
             and L.allucinazione("no no no no") == "ripetizione"
             and L.allucinazione("ciao ciao ciao ciao ciao ciao ciao ciao ciao ciao") is not None
             and L.allucinazione("Domani andiamo tutti al mare con la macchina di Carlo.")
             is None)
    st.chiudi()


# ─────────────────────────── 5. TV ───────────────────────────
def prova_tv():
    cfg = cfg_base(stanza_contesto=True)
    st, le = nuova(cfg)
    sala = Coll(5, "sala")
    tv = [parla(st, sala, 51 + 2 * i, [(0.35, 10.0)], chiusura="lunga",
                testi=(f"Notizia numero {i} del telegiornale della sera.",) * 2)
          for i in range(4)]
    le.giro(tardi(cfg))
    rr = [riga_di(st, 5, s)[0] for s in tv]
    verifica("stanza vuota, voce sconosciuta lunga e senza pause: righe «tv»",
             all(r["chi"] == "tv" and r["versione"] == 2 for r in rr)
             and {"voci", "continua", "nessuno_presente"} <= set(rr[0]["tv"]), str(rr[0]))
    st._info[5] = {"nome": "sala", "stanza": "sala", "canale": "satellite"}
    b = ctx.costruisci(st, 5, cfg, adesso() + 5)
    verifica("nel blocco caldo una riga sola col tempo, senza parole",
             b is not None and "[TV o radio," in b.testo and "telegiornale" not in b.testo
             and b.testo.count("[TV o radio") == 1 and "telegiornale" not in b.esterno,
             b.testo if b else "")
    from calliope.stanza.cerca import Chi, cerca
    es = cerca(st, cfg, Chi("p-carlo", "Carlo", sat=5), "telegiornale", aspetta=False)
    verifica("la TV non è nella ricerca", es.esito == "niente", es.esito)
    # Contrari
    tel = Coll(6, "studio")
    t1 = parla(st, tel, 61, [(0.35, 10.0)], chiusura="lunga", testi=("Pronto, sono io.",) * 2)
    parla(st, tel, 63, [(0.1, 2.0)], testi=("Sì, ti sento.",) * 2)
    t3 = parla(st, tel, 65, [(0.35, 10.0)], chiusura="lunga",
               testi=("Allora domani passo da voi.",) * 2)
    t4 = parla(st, tel, 67, [(0.35, 10.0)], chiusura="lunga", testi=("Va bene, a dopo.",) * 2)
    osp = Coll(7, "cucina")
    parla(st, osp, 71, [(0.1, 2.0)], testi=("Raccontaci del viaggio.",) * 2)
    o = [parla(st, osp, 73 + 2 * i, [(0.35, 10.0)], testi=(f"Poi siamo andati al porto {i}.",) * 2)
         for i in range(3)]
    legge = [parla(st, osp, 81 + 2 * i, [(0.1, 10.0)], chiusura="lunga",
                   testi=(f"C'era una volta un re {i}.",) * 2) for i in range(3)]
    le.giro(tardi(cfg))
    verifica("contrario: telefonata in vivavoce (la persona di casa risponde in mezzo) non è TV",
             all(riga_di(st, 6, s)[0]["chi"] != "tv" for s in (t1, t3, t4)))
    verifica("contrario: ospite che racconta con la famiglia presente non è TV",
             all(riga_di(st, 7, s)[0]["chi"] != "tv" for s in o))
    verifica("contrario: Carlo che legge ad alta voce a lungo non è mai TV",
             all(riga_di(st, 7, s)[0]["chi"] == "persona:p-carlo" for s in legge))
    # La pubblicità già sentita (su un altro satellite) e Home Assistant spento
    st2, le2 = nuova(cfg_base(registro="tv2"), media=lambda sat: False if sat == 9 else None)
    a = Coll(8, "cucina")
    q1 = parla(st2, a, 91, [(0.35, 4.0)], testi=("Compra oggi il nuovo detersivo super bianco.",) * 2)
    le2.giro(tardi(cfg))
    q2 = parla(st2, a, 93, [(0.35, 4.0)], testi=("Compra oggi il nuovo detersivo super bianco!",) * 2)
    le2.giro(tardi(cfg))
    verifica("pubblicità: la prima volta no, la stessa frase sentita di nuovo è TV",
             riga_di(st2, 8, q1)[0]["chi"] != "tv" and riga_di(st2, 8, q2)[0]["chi"] == "tv"
             and "gia_sentita" in riga_di(st2, 8, q2)[0]["tv"])
    h = Coll(9, "taverna")
    hh = [parla(st2, h, 95 + 2 * i, [(0.35, 10.0)], testi=(f"Parla il presentatore {i}.",) * 2)
          for i in range(3)]
    le2.giro(tardi(cfg))
    verifica("contrario: Home Assistant dice spento: voci e nessuno presente non bastano",
             all(riga_di(st2, 9, s)[0]["chi"] != "tv" for s in hh))
    st.chiudi()
    st2.chiudi()


# ─────────────────────────── 6. storia, disco, ricerca ───────────────────────────
def prova_conseguenze():
    from calliope.stanza.tenuta import Tenuta
    cfg = cfg_base(stanza_contesto=True)
    st, le = nuova(cfg)
    st.tenuta = Tenuta(TMP / "stanza.db", registry=None, log=lambda m: None)
    c = Coll(10, "cucina")
    st._info[10] = {"nome": "cucina", "stanza": "cucina", "canale": "satellite"}
    s1 = parla(st, c, 101, [(0.1, 2.0)], testi=("Il treno parte alle nove e mezo.",
                                                 "Il treno parte alle nove e mezzo."))
    b = ctx.costruisci(st, 10, cfg, adesso() + 1)
    pz = ctx.pezzo(b, set(), cfg, 1, primo=True)
    mandate = set(pz.ids | pz.segmenti)
    s2 = parla(st, c, 103, [(0.2, 2.0)], testi=("E il ritorno alle sei.",
                                                 "E il ritorno alle sette."))
    s3 = parla(st, c, 105, [(0.35, 2.0)], testi=("Buonasera.",) * 2)
    st.tenuta.attendi()
    le.giro(tardi(cfg))
    st.tenuta.attendi()
    b2 = ctx.costruisci(st, 10, cfg, adesso() + 1)
    pz2 = ctx.pezzo(b2, mandate, cfg, 2, primo=False)
    verifica("storia: la versione 2 di una riga già mandata non si rimanda, la nuova va "
             "già corretta", pz2 is not None and "mezzo" not in pz2.testo
             and "alle sette" in pz2.testo and "alle sei" not in pz2.testo, pz2.testo if pz2 else "")
    righe = {r[0]: r for r in st.tenuta.db.execute(
        "SELECT testo, versione, segmento FROM righe").fetchall()}
    verifica("disco: la versione 2 sostituisce la 1 (una riga per segmento)",
             "Il treno parte alle nove e mezzo." in righe
             and "Il treno parte alle nove e mezo." not in righe
             and righe["Il treno parte alle nove e mezzo."][1] == 2
             and "E il ritorno alle sette." in righe, str(righe))
    from calliope.stanza.cerca import Chi, cerca
    es = cerca(st, cfg, Chi("p-carlo", "Carlo", tutore_di={"p-nicola"}, sat=10),
               "ritorno sette", aspetta=False)
    verifica("stanza_cerca trova la versione 2", es.esito == "trovato"
             and "alle sette" in es.testo and "alle sei" not in es.testo, es.testo)
    # La TV toglie dal disco la riga di prima; un segmento spezzato tiene tutte e due le parti
    s4 = parla(st, c, 107, [(0.1, 4.0), (0.2, 4.0)], testi=("Io e io.", "Io porto il vino. E io il pane."))
    st.tenuta.attendi()
    le.giro(tardi(cfg))
    st.tenuta.attendi()
    n4 = st.tenuta.db.execute("SELECT count(*) FROM righe WHERE segmento = ?", (s4,)).fetchone()[0]
    verifica("disco: le due parti di un segmento spezzato ci sono tutte e due", n4 == 2, str(n4))
    lid = 0
    for i in range(3):
        lid = parla(st, c, 111 + 2 * i, [(0.1, 2.0)], testi=(f"Riga di Carlo {i}.",) * 2)
    st.tenuta.attendi()
    # A mano: una riga di Carlo su disco che la corsia lenta segna TV (v2 non tenuta)
    reg = st.registro(10)
    v1 = riga_di(st, 10, lid)[0]
    reg.aggiungi(RIGA, segmento=lid, versione=2, inizio=v1["inizio"], fine=v1["fine"],
                 testo=v1["testo"], chi="tv", nome=None, sicurezza="nessuna", minore=False)
    st.tenuta.attendi()
    n = st.tenuta.db.execute("SELECT count(*) FROM righe WHERE segmento = ?", (lid,)).fetchone()[0]
    verifica("disco: una versione 2 che non si tiene (TV) toglie la versione 1", n == 0)
    st.tenuta.chiudi()
    st.chiudi()


# ─────────────────────────── 7. guardiano a posteriori ───────────────────────────
class Giudice:
    def __init__(self):
        self.visti = []

    def __call__(self, b):
        from calliope.stanza import guardia as gm
        self.visti.append([r.get("testo") for r in b.giudicate])
        return gm.leggi_esito({"livello": "NIENTE", "categoria": "nessuna", "contesto": "serio",
                               "righe": []})


def prova_guardia():
    from calliope.stanza import guardia as gm
    cfg = cfg_base(stanza_guardia="ombra", stanza_guardia_attesa_s=0.0,
                   stanza_guardia_quiete_s=0.0)
    st, le = nuova(cfg)
    c = Coll(11, "camera")
    st._info[11] = {"nome": "camera", "stanza": "camera", "canale": "satellite"}
    giud = Giudice()
    g = gm.Guardia(cfg, st, giud, log=LOG.append, avvia=False)
    s1 = parla(st, c, 121, [(0.2, 2.0)], testi=("Domani gita al lak.", "Domani gita al lago."))
    n = g.raccogli(adesso() + 5)
    verifica("guardiano: la riga aspetta la corsia lenta (niente blocco)", n == 0)
    le.giro(tardi(cfg))
    g.giro(adesso() + 5)
    verifica("dopo la corsia lenta: giudicata una volta, sulla versione 2",
             giud.visti == [["Domani gita al lago."]], str(giud.visti))
    # Raccolta prima della corsia lenta (assente in quel momento), poi la versione 2
    st.lenta = None
    s2 = parla(st, c, 123, [(0.2, 2.0)], testi=("Mi piace la pizza margerita.",
                                                 "Mi piace la pizza margherita."))
    s3 = parla(st, c, 125, [(0.2, 2.0)], testi=("Mmh boh.", "Non voglio più mangiare."))
    # Senza corsia lenta l'audio non è in attesa: lo rimetto a mano
    st.lenta = le
    for s in (s2, s3):
        pass
    giud.visti.clear()
    g.giro(adesso() + 5)
    prima = list(giud.visti)
    # ora la corsia lenta, con l'audio messo dopo (come se fosse arrivato prima)
    x2 = np.full(2 * SR, 0.2, np.float32)
    for s, mm in ((s2, 123), (s3, 125)):
        x = x2.copy()
        x[0] = mm / 1000
        seg = SimpleNamespace(sat=11, id=s, scambio=riga_di(st, 11, s)[0].get("scambio"),
                              inizio_epoch=riga_di(st, 11, s)[0]["inizio"],
                              fine_epoch=riga_di(st, 11, s)[0]["fine"], voce_s=2.0,
                              chiusura="silenzio")
        le.metti(seg, x, riga_di(st, 11, s)[0]["seq"])
    le.giro(tardi(cfg))
    giud.visti.clear()
    g.giro(adesso() + 5)
    verifica("prima: le due righe giudicate sulla versione 1", len(prima) == 1
             and set(prima[0]) == {"Mi piace la pizza margerita.", "Mmh boh."}, str(prima))
    verifica("versione 2 quasi uguale non rigiudicata; cambio sostanziale sì",
             giud.visti == [["Non voglio più mangiare."]], str(giud.visti))
    mis = [r for r in st.misure.memoria if r["tipo"] == "guardia" and r.get("esito") == "versione"]
    verifica("misure della guardia: versione rigiudicata e saltata, senza parole",
             any(r.get("rigiudicata") for r in mis) and any(not r.get("rigiudicata") for r in mis)
             and all("testo" not in r for r in mis))
    verifica("cambio sostanziale: contrari", not L.cambio_sostanziale(
        {"testo": "ciao a tutti quanti", "minore": False},
        {"testo": "ciao a tutti quanti voi", "minore": False})
        and L.cambio_sostanziale({"testo": "ciao a tutti", "minore": False},
                                 {"testo": "ciao a tutti", "minore": True}))
    st.chiudi()


# ─────────────────────────── 8. riassunto, carico, RAM, dimentica ───────────────────────────
def prova_riassunto_carico():
    cfg = cfg_base(stanza_contesto=True, stanza_lenta_riassunto_righe=2, stanza_caldo_min=1.0)
    chiesti = []

    def riass(prima, righe, presenti):
        chiesti.append((prima, list(righe), list(presenti)))
        return "Si parla della gita al lago di domenica."
    st, le = nuova(cfg, riassuntore=riass)
    c = Coll(12, "cucina")
    st._info[12] = {"nome": "cucina", "stanza": "cucina", "canale": "satellite"}
    parla(st, c, 131, [(0.1, 2.0)], testi=("Domenica gita al lago.",) * 2)
    parla(st, c, 133, [(0.2, 2.0)], testi=("Porto il pallone.",) * 2)
    le.giro(tardi(cfg))
    r = st.registro(12).riassunto()
    verifica("riassunto progressivo dopo due righe, col rilevatore finto",
             r is not None and "gita" in r["testo"] and len(chiesti) == 1
             and chiesti[0][0] is None and len(chiesti[0][1]) == 2, str(r))
    sc = r["scambio"]
    reg = st.registro(12)
    t = adesso()
    reg.aggiungi(RIGA, segmento=None, scambio=sc, versione=1, inizio=t + 89, fine=t + 90,
                 testo="E chi porta la merenda?", chi="persona:p-carlo", nome="Carlo",
                 sicurezza="voce", rivolta="ignoto", minore=False)
    b = ctx.costruisci(st, 12, cfg, t + 100)
    nota = ctx.nota_turno(b)
    verifica("scambio più vecchio della finestra: il riassunto nel blocco e nella nota, in busta",
             b is not None and b.riassunto and "Riassunto automatico" in b.testo
             and provenienza.racchiudi(ctx.FONTE, ctx.RIASSUNTO.format(
                 dove="cucina", testo=b.riassunto), "riassunto della stanza") in nota
             and "gita" in b.esterno, nota)
    b2 = ctx.costruisci(st, 12, cfg, t + 5)
    verifica("contrario: lo scambio è tutto nella finestra: niente riassunto",
             b2 is not None and not b2.riassunto and "Riassunto" not in b2.testo)
    # La DGX occupata: niente passo nel thread
    occ = [True]
    st2, le2 = nuova(cfg_base(registro="carico"), occupato=[lambda: occ[0]])
    c2 = Coll(13, "sala")
    s = parla(st2, c2, 141, [(0.1, 2.0)], testi=("Una frase.", "Una frase corretta."))
    verifica("DGX occupata (una risposta, un turno in Whisper): non è libera",
             not le2.libera())
    occ[0] = False
    st2._comando[13] = time.monotonic()
    verifica("qualcuno parla a Calliope: non è libera", not le2.libera())
    st2._comando.clear()
    verifica("tutto fermo: libera", le2.libera())
    st2._pause[13] = {"motivo": "ospiti", "fino": None}
    verifica("in pausa (ospiti): niente di dovuto", le2.dovuti(tardi(cfg)) == [])
    st2._pause.clear()
    # «dimentica» butta l'audio in attesa
    st2.dimentica(13)
    verifica("«dimentica»: l'audio in attesa non c'è più", not le2.pendente(13, s)
             and le2.in_attesa() == 0)
    # Oltre stanza_audio_min: scaduto
    cfg3 = cfg_base(registro="ram", stanza_audio_min=0.05)
    st3, le3 = nuova(cfg3)
    c3 = Coll(14, "bagno")
    parla(st3, c3, 151, [(0.1, 2.0)])
    parla(st3, c3, 153, [(0.1, 2.0)])
    verifica("RAM: oltre stanza_audio_min i segmenti più vecchi escono (contati)",
             le3.in_attesa() == 1 and any(r.get("esito") == "scaduto"
                                          for r in st3.misure.memoria if r["tipo"] == "lenta"))
    for x in (st, st2, st3):
        x.chiudi()


# ─────────────────────────── 9. audio del banco ───────────────────────────
def prova_banco():
    from calliope.conserva import Conservazione
    cfg = cfg_base(registro="banco", stanza_audio_banco_giorni=7)
    b = banco_mod.Banco(cfg, log=LOG.append)
    st, le = nuova(cfg, banco=b)
    c = Coll(15, "cucina")
    st._info[15] = {"nome": "cucina", "stanza": "cucina", "canale": "satellite"}
    s_c = parla(st, c, 161, [(0.1, 2.0)], testi=("Ciao Nicola.", "Ciao Nicola, vieni."))
    s_n = parla(st, c, 163, [(0.2, 2.0)], testi=("Ciao papà.",) * 2)
    s_o = parla(st, c, 165, [(0.35, 2.0)], testi=("Buonasera.",) * 2)
    s_g = parla(st, c, 167, [(0.12, 1.5)], testi=("Eh già.",) * 2)
    s_m = parla(st, c, 169, [(0.1, 4.0), (0.35, 4.0)], testi=("Io e lui.", "Ciao a tutti. Buonasera."))
    le.giro(tardi(cfg))
    d = banco_mod.cartella(cfg)
    wav = sorted(d.rglob("*.wav"))
    meta = [json.loads(p.with_suffix(".json").read_text(encoding="utf-8")) for p in wav]
    segs = sorted(m["segmento"] for m in meta)
    verifica("banco: salvati solo i segmenti di Carlo e del minore della famiglia",
             segs == sorted([s_c, s_n]), str(segs))
    m_c = next(m for m in meta if m["segmento"] == s_c)
    verifica("banco: accanto le trascrizioni v1 e v2 e le persone, niente altro",
             m_c["v1"]["testo"] == "Ciao Nicola." and m_c["v2"][0]["testo"] == "Ciao Nicola, vieni."
             and m_c["persone"] == ["p-carlo"] and m_c["esito_lenta"] == "cambiata")
    if os.name != "nt":
        verifica("banco: file 600", stat.S_IMODE(wav[0].stat().st_mode) == 0o600)
    verifica("banco: contrari (voce sconosciuta, zona grigia, ospite dentro un segmento misto)",
             s_o not in segs and s_g not in segs and s_m not in segs)
    ok, mot = banco_mod.Banco.ammesso([{"chi": "conoscente:k1", "sicurezza": "voce"}], 0)
    verifica("banco: un conoscente no", not ok and mot == "conoscente")
    verifica("banco: in pausa no", b.salva(15, {}, {"segmento": 999}, b"\0\0" * SR, SR,
                                           {"chi": "persona:p-carlo", "sicurezza": "voce",
                                            "testo": "x"}, [], in_pausa=True) is None
             and b.saltati.get("pausa") == 1)
    verifica("banco: scaduta dopo 7 giorni (lo dice una volta)",
             b.salva(15, {}, {"segmento": 998, "inizio": time.time()}, b"\0\0" * SR, SR,
                     {"chi": "persona:p-carlo", "sicurezza": "voce", "testo": "x"}, [],
                     ora=time.time() + 8 * 86400) is None
             and any("scaduta" in m for m in LOG))
    sf = banco_mod.stato_file(cfg)
    verifica("banco: stato --turni (accesa fino al…, file, MB)", sf["file"] == 2
             and not sf["scaduta"] and "accesa fino al" in banco_mod.testo_stato(sf))
    verifica("banco: spento (0 giorni) e senza corsia lenta non salva",
             not banco_mod.Banco(cfg_base(registro="b0"), log=LOG.append).attivo()
             and not banco_mod.Banco(cfg_base(registro="b1", stanza_audio_banco_giorni=7,
                                              stanza_lenta=False), log=LOG.append).attivo())
    # «dimentica», svuota di una persona e di tutto
    c2 = Coll(16, "sala")
    st._info[16] = {"nome": "sala", "stanza": "sala", "canale": "satellite"}
    parla(st, c2, 171, [(0.1, 2.0)], testi=("Ecco.",) * 2)
    parla(st, c2, 173, [(0.2, 2.0)], testi=("Pronto.",) * 2)
    le.giro(tardi(cfg))
    verifica("banco: quattro segmenti su due satelliti", len(list(d.rglob("*.wav"))) == 4)
    st.dimentica(16)
    verifica("«dimentica» toglie i file del satellite", len(list(d.rglob("*.wav"))) == 2)
    cons = Conservazione(cfg, registry=None, log=lambda m: None)
    r = cons.svuota("p-nicola")
    verifica("svuota di una persona: i segmenti con la sua voce",
             r.get("stanza_banco") == 1 and len(list(d.rglob("*.wav"))) == 1)
    r = cons.svuota()
    verifica("svuota di tutto (anche il segno dell'accensione)",
             r.get("stanza_banco") == 1 and not d.exists())
    st.chiudi()


# ─────────────────────────── 10. misure, stato, piano, configurazione ───────────────────────────
def prova_misure_piano():
    cfg = cfg_base()
    righe = misure_mod.leggi(cfg.turn_log_dir)
    r = misure_mod.riassunto(righe)
    t = misure_mod.testo(r)
    verifica("stato --turni: la riga della corsia lenta, solo numeri",
             "Corsia lenta (passo 3)" in t and "rivisti" in t and "Whisper" in t
             and r["lenta"]["riviste"] > 0 and r["lenta"]["cambiate"] > 0, t)
    from calliope import piano as P
    inv = {"os": "linux", "arch": "aarch64", "ram_gb": 128,
           "gpu": {"nome": "GB10", "memoria_gb": 119.0, "banda_gbs": 273, "unificata": True,
                   "produttore": "nvidia", "chiave": "GB10"}, "motori": {}}
    p = P.piano(inv, P.Funzioni(stanza_lenta=True))
    s = p.scelta("stanza_lenta")
    verifica("piano: con tanta memoria un secondo Whisper per la corsia lenta",
             s is not None and "secondo server" in s.scelta and s.memoria_gb > 0, str(s))
    inv8 = {"os": "windows", "arch": "x86_64", "ram_gb": 32,
            "gpu": {"nome": "RTX 5070 Laptop", "memoria_gb": 8.0, "banda_gbs": 384,
                    "produttore": "nvidia"}, "motori": {}}
    s8 = P.piano(inv8, P.Funzioni(stanza_lenta=True)).scelta("stanza_lenta")
    verifica("piano: 8 GB, lo stesso Whisper dei turni (taglia ridotta)",
             s8 is not None and s8.scelta == "lo stesso Whisper dei turni"
             and s8.memoria_gb == 0, str(s8))
    verifica("piano: spenta, nessuna scelta", P.piano(inv, P.Funzioni()).scelta(
        "stanza_lenta") is None)
    c = Config()
    verifica("configurazione: corsia lenta spenta e banco a 0 di serie",
             c.stanza_lenta is False and c.stanza_audio_banco_giorni == 0
             and c.stanza_lenta_stt_url == "")
    from calliope.config import SEZIONI
    sez = next((k for k, v in SEZIONI.items() if "stanza_lenta" in v), None)
    verifica("configurazione: nella sezione della stanza", sez is not None
             and "stanza_audio_banco_giorni" in SEZIONI[sez] and "stanza" in SEZIONI[sez])


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    _patch_orologio()
    try:
        prova_spenta()
        prova_ritrascrizione()
        prova_chi()
        prova_allucinazioni()
        prova_tv()
        prova_conseguenze()
        prova_guardia()
        prova_riassunto_carico()
        prova_banco()
        prova_misure_piano()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not errori else f"\n{errori} prove non riuscite.")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
