"""
Prova a secco del passo 1 della conversazione di stanza (13/10/2026, decisione 0029, progetto
docs/ricerche/2026-10-13-conversazione-di-stanza.md § 3.1–3.3, § 3.5 ter, § 3.10, § 3.11, § 6):
stanza in ombra, sola trascrizione veloce, niente al modello.

- Segmentatore del satellite (calliope/satellite/stanza.py): segmenti chiusi dal silenzio e dal
  tetto corto, niente sotto `min_speech_ms`, half-duplex (la voce di Calliope butta il segmento),
  legame con l'ascolto dei comandi; lo stesso Segmentatore del telefono (voce.js, con Node) dà
  gli stessi messaggi;
- la coda di Whisper con la precedenza (stanza/coda.py): turno > recupero > stanza;
- il server dei satelliti vero su 127.0.0.1 con un satellite finto a livello di protocollo: la
  versione 3 col «ciao» `stanza: true` riceve lo stato nel benvenuto e manda segmenti che
  diventano righe (testo, chi parla con l'impronta, minore), un segmento legato a un turno non si
  trascrive (il testo viene dal turno, «rivolta: sì»), mentre qualcuno parla a Calliope i
  segmenti normali aspettano e quelli del recupero passano davanti, la copertura
  all'interpellazione (dette, pronte, recupero_ms); i contrari: satellite versione 2 (niente
  stanza, il b"R" ignorato), satellite fuori da `stanza_satelliti`, `stanza: spenta`;
- registro in sola aggiunta, in memoria, con la proiezione delle righe; presenza per persona con
  il cambio di stanza (§ 3.5 ter); pausa, ospiti per 4 ore e ripresa (solo un adulto riconosciuto
  dalla voce) col messaggio al satellite e il segno sugli schermi; «dimentica» che svuota anche
  la stanza;
- le misure su disco senza parole (stanza-AAAA-MM-GG.jsonl) e la sezione «Stanza» di
  `calliope stato --turni` con la copertura e i tempi dei turni con e senza stanza;
- la configurazione: `stanza: spenta` di serie, `ombra` dal file locale (anche nella sezione).

Nomi di fantasia (Carlo amministra, Nicola ha 14 anni). Cartella temporanea, ~10 s.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from calliope.config import Config
from calliope.satellite import protocollo as P
from calliope.satellite.stanza import Segmentatore
from calliope.stanza import coda as coda_mod
from calliope.stanza import misure as misure_mod
from calliope.stanza.ascolto import Stanza
from calliope.stanza.registro import RegistroStanza

RADICE = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="calliope-stanza-"))
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio else ""),
          flush=True)


def aspetta(cond, max_s=5.0, passo=0.02):
    fine = time.monotonic() + max_s
    while time.monotonic() < fine:
        v = cond()
        if v:
            return v
        time.sleep(passo)
    return None


def cfg_base(**k) -> Config:
    c = Config()
    c.stanza = "ombra"
    c.turn_log_dir = str(TMP / "registro")
    c.speaker_min_voice_s = 0.5
    for a, v in k.items():
        setattr(c, a, v)
    return c


# ─────────────────────────── 1. il segmentatore ───────────────────────────
def probs(*pezzi):
    """[(secondi, prob)] → probabilità per frame da 32 ms."""
    out = []
    for s, p in pezzi:
        out += [p] * int(round(s * 1000 / 32))
    return out


def corri_seg(seq, occupato_da=None, ultimo=None, max_s=None):
    cfg = Config()
    seg = Segmentatore(cfg, ultimo_comando=ultimo, max_s=max_s)
    msg = []
    ora = 1000.0
    for i, p in enumerate(seq):
        fr = np.full(512, 0.01, np.float32)
        occ = occupato_da is not None and i >= occupato_da
        msg += seg.passo(fr, p, occ, ora)
        ora += 0.032
    return seg, msg


def prova_segmentatore():
    seg, m = corri_seg(probs((0.5, 0.0), (1.5, 0.9), (1.0, 0.0)))
    tipi = [x[0] for x in m]
    fine = [x[1] for x in m if x[0] == "fine"]
    verifica("segmentatore: parlato e silenzio → inizio, pezzi e fine «silenzio»",
             tipi[0] == "inizio" and tipi[-1] == "fine" and fine and
             fine[0]["chiusura"] == "silenzio" and fine[0]["ascolto"] is None, str(tipi[:4]))
    campioni = sum(len(f) for x in m if x[0] == "audio" for f in x[2])
    verifica("segmentatore: tutto il parlato parte (pre-roll compreso), a pezzi",
             campioni >= 512 * int(1.5 * 1000 / 32) and sum(x[0] == "audio" for x in m) > 3,
             f"{campioni} campioni")
    seg, m = corri_seg(probs((0.5, 0.0), (0.15, 0.9), (1.0, 0.0)))
    verifica("segmentatore: sotto min_speech_ms niente parte (contrario)",
             m == [] and seg.buttati["corto"] == 1)
    seg, m = corri_seg(probs((0.3, 0.0), (2.0, 0.9), (1.0, 0.0)), occupato_da=30)
    fine = [x[1] for x in m if x[0] == "fine"]
    verifica("segmentatore: la voce di Calliope butta il segmento (half-duplex)",
             fine and fine[-1]["chiusura"] == "voce" and seg.buttati["voce"] == 1)
    seg, m = corri_seg(probs((0.2, 0.0), (5.0, 0.9), (1.0, 0.0)), max_s=2.0)
    chiusure = [x[1]["chiusura"] for x in m if x[0] == "fine"]
    verifica("segmentatore: il tetto corto taglia e riparte", chiusure[:2] == ["lunga", "lunga"]
             and chiusure[-1] == "silenzio", str(chiusure))
    seg, m = corri_seg(probs((0.2, 0.0), (1.5, 0.9), (1.0, 0.0)),
                       ultimo=lambda: (1000.5, 7))
    fine = [x[1] for x in m if x[0] == "fine"]
    verifica("segmentatore: sovrapposto all'audio dei comandi porta l'ascolto (legame)",
             fine and fine[0]["ascolto"] == 7)
    seg, m = corri_seg(probs((0.2, 0.0), (1.5, 0.9), (1.0, 0.0)),
                       ultimo=lambda: (900.0, 7))
    fine = [x[1] for x in m if x[0] == "fine"]
    verifica("segmentatore: audio dei comandi di prima non lega (contrario)",
             fine and fine[0]["ascolto"] is None)
    return m


def prova_telefono_uguale():
    """Il Segmentatore di voce.js (Node) con la stessa sequenza: stessi messaggi."""
    node = shutil.which("node")
    if node is None:
        print("SALTATA IN PARTE: Node assente, niente confronto col Segmentatore del telefono")
        return
    seq = probs((0.4, 0.0), (1.2, 0.8), (0.3, 0.2), (0.9, 0.9), (1.0, 0.0), (0.1, 0.9),
                (0.8, 0.0), (3.0, 0.9), (1.0, 0.0))
    cfg = Config()
    _, py = corri_seg(seq, max_s=2.0)
    voce = (RADICE / "calliope" / "schermi" / "pagina" / "telefono" / "voce.js").as_uri()
    js = f"""
import {{ Segmentatore }} from "{voce}";
const p = {{vad_threshold: {cfg.vad_threshold}, silence_ms: {cfg.silence_ms},
  preroll_ms: {cfg.preroll_ms}, min_speech_ms: {cfg.min_speech_ms}}};
const s = new Segmentatore(p, 2.0, null);
const seq = {json.dumps(seq)};
const out = []; let ora = 1000000;
for (const pr of seq) {{
  for (const m of s.passo(new Float32Array(512), pr, false, ora)) {{
    out.push(m[0] === "audio" ? ["audio", m[1], m[2].length] : [m[0], m[1]]);
  }}
  ora += 32;
}}
console.log(JSON.stringify(out));
"""
    r = subprocess.run([node, "--input-type=module", "-e", js], capture_output=True, text=True,
                       timeout=60)
    if r.returncode != 0:
        verifica("telefono: voce.js si carica in Node", False, r.stderr[-300:])
        return
    out = json.loads(r.stdout.strip().splitlines()[-1])
    a = [(x[0], x[1] if x[0] == "audio" else x[1].get("chiusura") or x[1].get("id"),
          x[2] if x[0] == "audio" else None) for x in out]
    b = [(x[0], x[1] if x[0] == "audio" else x[1].get("chiusura") or x[1].get("id"),
          len(x[2]) if x[0] == "audio" else None) for x in py]
    verifica("telefono: il Segmentatore di voce.js dà gli stessi messaggi del Python",
             a == b, f"{len(a)} contro {len(b)}")


# ─────────────────────────── 2. la precedenza ───────────────────────────
def prova_precedenza():
    pr = coda_mod.Precedenza()
    ordine = []
    entrato = threading.Event()

    def tiene():
        with pr.tieni(coda_mod.STANZA):
            entrato.set()
            time.sleep(0.3)

    def chi(p, nome):
        with pr.tieni(p):
            ordine.append(nome)

    t0 = threading.Thread(target=tiene)
    t0.start()
    entrato.wait(2)
    ts = []
    for p, n in ((coda_mod.STANZA, "stanza"), (coda_mod.RECUPERO, "recupero"),
                 (coda_mod.TURNO, "turno")):
        t = threading.Thread(target=chi, args=(p, n))
        t.start()
        ts.append(t)
        time.sleep(0.03)
    verifica("precedenza: una frase di un turno in attesa si vede", pr.aspetta_turno())
    for t in ts + [t0]:
        t.join(3)
    verifica("precedenza: turno, poi recupero, poi stanza (non l'ordine d'arrivo)",
             ordine == ["turno", "recupero", "stanza"], str(ordine))


# ─────────────────────────── 3. server e satellite finto ───────────────────────────
class STTFinto:
    """Whisper finto: «testo» dal primo campione (marcatore), con un ritardo; tiene l'ordine."""

    def __init__(self, ritardo=0.05):
        self.ritardo, self.ordine, self.prompt = ritardo, [], []
        self.ultima_scartata = None

    def transcribe(self, audio, prompt=None):
        time.sleep(self.ritardo)
        self.prompt.append(prompt)
        m = int(round(float(audio[0]) * 1000))
        self.ordine.append(m)
        self.ultima_scartata = "sottotitoli" if m == 999 else None
        return "" if m == 999 else f"frase {m}"


class RegistroVoci:
    """Impronte finte: l'ampiezza del segmento dice chi parla (0,1 Carlo, 0,2 Nicola)."""

    def __init__(self):
        self.p = {"Carlo": SimpleNamespace(id="p-carlo", name="Carlo"),
                  "Nicola": SimpleNamespace(id="p-nicola", name="Nicola", fascia="adolescenti")}

    def embed(self, audio, sr):
        return np.array([float(np.mean(np.abs(audio[100:])))])

    def classifica(self, emb):
        a = emb[0]
        if abs(a - 0.1) < 0.02:
            return [("Carlo", 0.8), ("Nicola", 0.2)]
        if abs(a - 0.2) < 0.02:
            return [("Nicola", 0.8), ("Carlo", 0.2)]
        return [("Carlo", 0.1)]

    def get(self, n):
        return self.p.get(n)


class HubFinto:
    def __init__(self):
        self.segni = []

    def stanza_segno(self, stanza, sorgente, testo):
        self.segni.append((stanza, sorgente, testo))


class Finto:
    """Un satellite a livello di protocollo, versione 3 o 2."""

    def __init__(self, url, token, versione=3):
        from websockets.sync.client import connect
        self.ws = connect(url + P.PERCORSO_AUDIO, compression=None, max_size=2 ** 22)
        self.ws.send(P.testo(tipo="ciao", versione=versione, token=token, primo=False,
                             nome="finto", stanza=versione >= 3))
        self.benvenuto = None
        while self.benvenuto is None:
            m = P.leggi(self.ws.recv(timeout=10))
            if m.get("tipo") == "benvenuto":
                self.benvenuto = m
        self.ws.send(P.testo(tipo="pronto", eco=0.0))
        self.messaggi = []
        self.ids = iter(range(1, 10 ** 6))
        threading.Thread(target=self._leggi, daemon=True).start()

    def _leggi(self):
        try:
            while True:
                m = self.ws.recv()
                if isinstance(m, str):
                    self.messaggi.append(P.leggi(m))
        except Exception:  # noqa: BLE001
            pass

    def segmento(self, marcatore: int, ampiezza=0.1, secondi=1.0, ascolto=None,
                 chiusura="silenzio") -> int:
        sid = next(self.ids)
        x = np.full(int(16000 * secondi), ampiezza, np.float32)
        x[0] = marcatore / 1000
        self.ws.send(P.testo(tipo="stanza_inizio", id=sid, fa_s=0.4))
        self.ws.send(P.binario(P.STANZA, sid, P.a_pcm(x)))
        self.ws.send(P.testo(tipo="stanza_fine", id=sid, durata_s=secondi,
                             parlato_ms=int(secondi * 1000), chiusura=chiusura, ascolto=ascolto))
        return sid

    def comando(self, lid=1, n=5):
        for _ in range(n):
            self.ws.send(P.binario(P.AUDIO, lid, P.a_pcm(np.zeros(512, np.float32))))

    def chiudi(self):
        self.ws.close()


def ambiente(cfg, stt):
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.server import ServerSatelliti
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / f"memoria-{time.monotonic_ns()}.db")
    cfg.satellite_porta = 0
    cfg.audio_modo = "satellite"
    srv = ServerSatelliti(cfg, ArchivioSatelliti(cfg.memory_db), log=lambda m: None)
    srv.avvia()
    srv.avviato.set()
    srv.insieme = True
    st = None
    if stt is not None:
        st = Stanza(cfg, stt, registry=RegistroVoci(),
                    misure=misure_mod.Misure(cfg.turn_log_dir, 60), log=lambda m: None)
        st.server, st.schermi = srv, HubFinto()
        srv.conversazione_stanza = st
    return srv, st


def abbina(srv, nome):
    req = srv.archivio.nuova_richiesta()
    srv.archivio.abbina(req["codice"], nome)
    return req["richiesta"], srv.archivio.per_token(req["richiesta"])


def prova_server():
    from calliope.corsie import STTCondiviso
    cfg = cfg_base(stanza_satelliti=["cucina", "telefono"])
    stt = STTCondiviso(STTFinto(0.05))
    srv, st = ambiente(cfg, stt)
    url = f"ws://127.0.0.1:{srv.port}"
    try:
        tok, sat = abbina(srv, "cucina")
        f = Finto(url, tok)
        verifica("versione 3: il benvenuto dice che la stanza è accesa, col tetto del segmento",
                 (f.benvenuto.get("stanza") or {}).get("attiva") is True
                 and f.benvenuto["stanza"].get("segmento_max_s") == 20.0)
        aspetta(lambda: srv.per_id(sat["id"]))
        verifica("segno sugli schermi della stanza: «Ascolto la stanza»",
                 aspetta(lambda: any(t == "Ascolto la stanza" for _, _, t in st.schermi.segni))
                 is not None)
        f.segmento(1, 0.1)
        f.segmento(2, 0.2)
        reg = st.registro(sat["id"])
        aspetta(lambda: len(reg.righe()) >= 2)
        righe = reg.righe()
        verifica("due segmenti → due righe con testo, chi parla e minore",
                 [r["testo"] for r in righe] == ["frase 1", "frase 2"]
                 and righe[0]["nome"] == "Carlo" and righe[0]["sicurezza"] == "voce"
                 and righe[1]["nome"] == "Nicola" and righe[1]["minore"] is True
                 and righe[0]["rivolta"] == "ignoto", str([(r["testo"], r["nome"]) for r in righe]))
        verifica("la stanza trascrive senza il prompt col nome (§ 5.4)",
                 set(stt._stt.prompt) == {""}, str(stt._stt.prompt))
        verifica("registro: scambio aperto, segmenti, righe, presenze (in sola aggiunta)",
                 {"scambio_aperto", "segmento", "riga", "presenza_inizio"}
                 <= set(reg.conteggi()) and [e.seq for e in reg.eventi()]
                 == list(range(1, len(reg) + 1)))
        # Allucinazione: riga scartata, fuori dalla proiezione
        f.segmento(999, 0.1)
        aspetta(lambda: reg.conteggi().get("riga_scartata"))
        verifica("frase tipica delle allucinazioni: riga scartata, non nella proiezione",
                 reg.conteggi().get("riga_scartata") == 1 and len(reg.righe()) == 2)
        # Segmento legato a un turno: niente Whisper, il testo viene dal ciclo
        n_prima = len(stt._stt.ordine)
        f.comando(lid=5, n=3)
        f.segmento(50, 0.1, ascolto=5)
        aspetta(lambda: any(e.dati.get("turno") == 5 for e in reg.eventi("segmento")))
        time.sleep(0.2)
        verifica("segmento legato a un turno: non si trascrive due volte",
                 len(stt._stt.ordine) == n_prima)
        st.turno_testo(sat["id"], 5, "Calliope, che ore sono?",
                       {"chi": "persona:p-carlo", "persona": "p-carlo", "nome": "Carlo",
                        "sicurezza": "voce"})
        ultima = reg.righe()[-1]
        verifica("la frase del turno entra nella stanza, «rivolta: sì», legata al segmento",
                 ultima["testo"] == "Calliope, che ore sono?" and ultima["rivolta"] == "si"
                 and ultima["segmento"] is not None)
        # Mentre qualcuno parla a Calliope i segmenti normali aspettano
        time.sleep(1.0)
        stt._stt.ritardo = 0.2
        ordine0 = len(stt._stt.ordine)
        for _ in range(12):                  # la frase dei comandi dura già 1,2 s
            f.comando(lid=6, n=1)
            time.sleep(0.1)
        f.segmento(60, 0.1)                  # chiuso dopo l'inizio del comando: non recupero
        for _ in range(6):
            f.comando(lid=6, n=1)
            time.sleep(0.1)
        verifica("mentre si parla a Calliope (audio dei comandi) la stanza non comincia "
                 "segmenti nuovi", len(stt._stt.ordine) == ordine0)
        aspetta(lambda: len(stt._stt.ordine) > ordine0, 3)
        # Recupero: tre segmenti in coda, poi l'interpellazione su questo satellite
        stt._stt.ritardo = 0.15
        time.sleep(1.0)
        tok2, sat2 = abbina(srv, "telefono")
        g = Finto(url, tok2)
        aspetta(lambda: srv.per_id(sat2["id"]))
        for k in (71, 72, 73):
            g.segmento(k, 0.1)
        for k in (81, 82):
            f.segmento(k, 0.1)
        time.sleep(0.05)
        f.comando(lid=8, n=1)
        aspetta(lambda: {81, 82} <= set(stt._stt.ordine), 5)
        o = stt._stt.ordine
        pos = lambda k: o.index(k) if k in o else len(o) + 1  # noqa: E731
        verifica("recupero all'interpellazione: i segmenti del satellite interpellato passano "
                 "davanti a quelli degli altri", max(pos(81), pos(82)) < min(pos(72), pos(73)),
                 str(o[-6:]))
        aspetta(lambda: {71, 72, 73} <= set(o), 5)
        # Copertura: due segmenti detti prima della domanda, uno già pronto e uno in coda
        stt._stt.ritardo = 0.4
        time.sleep(0.8)
        f.segmento(91, 0.1)
        aspetta(lambda: 91 in stt._stt.ordine, 3)
        f.segmento(92, 0.1)
        time.sleep(0.05)
        cop = st.copertura(sat["id"], time.monotonic())
        d0 = cop.a_dict()
        aspetta(lambda: cop.a_dict()["recupero_ms"] is not None, 3)
        d1 = cop.a_dict()
        verifica("copertura all'interpellazione: dette, pronte, poi il recupero misurato",
                 d0["dette"] >= 2 and d0["pronte"] < d0["dette"] and d0["recupero_ms"] is None
                 and d1["recupero_ms"] is not None and d1["recupero_ms"] > 0, f"{d0} → {d1}")
        cop2 = st.copertura(sat["id"], time.monotonic())
        verifica("copertura: tutte pronte → recupero 0, non oltre il tetto",
                 cop2.a_dict()["recupero_ms"] == 0 and cop2.a_dict()["oltre"] is False)
        # Presenza: Carlo si sposta sul telefono
        g.segmento(95, 0.1)
        aspetta(lambda: 95 in stt._stt.ordine and any(
            p["nome"] == "Carlo" for p in st.presenti(sat2["id"])), 3)
        pres = reg.eventi("presenza")
        verifica("presenza: Carlo sentito su un altro satellite chiude la presenza in cucina "
                 "(inizio e fine) e la apre là",
                 pres and pres[0].dati["nome"] == "Carlo" and pres[0].dati["fine"]
                 >= pres[0].dati["inizio"] and any(p["nome"] == "Carlo"
                                                   for p in st.presenti(sat2["id"])))
        verifica("presenze per persona con satellite e intervallo (§ 3.5 ter)",
                 {x[0] for x in st.presenze("p-carlo")} >= {sat["id"], sat2["id"]})
        # Pausa e ospiti
        f.messaggi.clear()
        r = st.pausa(sat["id"], "ospiti", 240)
        m = aspetta(lambda: [x for x in f.messaggi if x.get("tipo") == "stanza"])
        verifica("«abbiamo ospiti»: il satellite riceve «stanza» spenta per ospiti, fino a 4 h",
                 m and m[-1]["attiva"] is False and m[-1]["motivo"] == "ospiti"
                 and abs(r["fino"] - time.time() - 4 * 3600) < 5)
        verifica("segno sugli schermi: «Stanza in pausa: ospiti, fino alle …»",
                 st.schermi.segni[-1][2].startswith("Stanza in pausa: ospiti, fino alle"))
        n_ev = len(reg)
        st.turno_testo(sat["id"], None, "Calliope, che tempo fa?", {"chi": "ignoto"})
        verifica("in pausa nemmeno la frase di un turno entra nella stanza", len(reg) == n_ev)
        n = len(stt._stt.ordine)
        f.segmento(100, 0.1)
        time.sleep(0.3)
        verifica("in pausa i segmenti non si trascrivono", len(stt._stt.ordine) == n)
        st.riprendi(sat["id"])
        m = aspetta(lambda: [x for x in f.messaggi if x.get("tipo") == "stanza"
                             and x.get("attiva")])
        verifica("ripresa: il satellite riceve «stanza» accesa", bool(m))
        # «Dimentica»
        n_ev = len(reg)
        st.dimentica(sat["id"])
        verifica("«dimentica» svuota il registro della stanza del satellite",
                 n_ev > 0 and len(reg) == 0 and reg.righe() == [])
        # Contrari: versione 2 e satellite fuori dall'elenco
        tok3, sat3 = abbina(srv, "studio")
        h = Finto(url, tok3, versione=3)
        verifica("satellite fuori da stanza_satelliti: «stanza» spenta nel benvenuto",
                 (h.benvenuto.get("stanza") or {}).get("attiva") is False)
        tok4, sat4 = abbina(srv, "cucina2")
        cfg.stanza_satelliti.append("cucina2")
        v2 = Finto(url, tok4, versione=2)
        verifica("satellite versione 2: niente «stanza» nel benvenuto",
                 "stanza" not in v2.benvenuto)
        n = len(stt._stt.ordine)
        v2.segmento(110, 0.1)
        time.sleep(0.3)
        verifica("satellite versione 2: il b\"R\" si ignora (compatibilità)",
                 len(stt._stt.ordine) == n and sat4["id"] not in st._registri,
                 f"{stt._stt.ordine[n:]} {list(st._registri)} {sat4['id']}")
        for x in (f, g, h, v2):
            x.chiudi()
        time.sleep(0.3)
        # Le misure: solo numeri
        righe = misure_mod.leggi(cfg.turn_log_dir)
        testo = json.dumps(righe, ensure_ascii=False)
        verifica("misure su disco: segmenti, presenze, cambi di stanza, pause, dimentica",
                 {"segmento", "presenza", "cambio_stanza", "pausa", "dimentica"}
                 <= {r["tipo"] for r in righe})
        verifica("misure su disco: mai le parole né i nomi di chi parla",
                 "frase" not in testo and "Carlo" not in testo and "che ore" not in testo)
        turni = [{"stt_s": 0.2, "durata_s": 2.0, "prima_frase_s": 1.2,
                  "stanza": {"copertura": d1}},
                 {"stt_s": 0.18, "durata_s": 2.0, "prima_frase_s": 1.1}]
        ria = misure_mod.riassunto(righe, turni)
        t = misure_mod.testo(ria)
        oggi = next(iter(ria["giorni"].values()))["satelliti"]
        verifica("stato --turni: sezione «Stanza» con ore, coda, banda, copertura e tempi",
                 "Stanza" in t and "Copertura all'interpellazione" in t
                 and "Turni con la stanza" in t and oggi["cucina"]["segmenti"] > 0
                 and oggi["cucina"]["ritardo_p90_s"] is not None
                 and oggi["cucina"]["byte"] > 0, t)
        verifica("stato --turni: righe scartate per motivo e cambi di stanza entro 10 minuti",
                 oggi["cucina"]["scartate"].get("allucinazione") == 1
                 and next(iter(ria["giorni"].values()))["cambi_10min"] >= 1)
    finally:
        st.chiudi()
        srv.ferma()


def prova_spenta():
    from calliope.stanza import load_stanza
    c = Config()
    verifica("di serie la stanza è spenta", c.stanza == "spenta" and c.stanza_satelliti == [])
    c.audio_modo = "satellite"
    verifica("spenta: niente stanza (nessun thread, nessun flusso)",
             load_stanza(c, STTFinto()) is None)
    srv, _ = ambiente(cfg_base(stanza="spenta"), None)
    try:
        tok, _sat = abbina(srv, "cucina")
        f = Finto(f"ws://127.0.0.1:{srv.port}", tok)
        verifica("spenta: un satellite versione 3 non riceve la stanza nel benvenuto",
                 "stanza" not in f.benvenuto)
        f.chiudi()
    finally:
        srv.ferma()


def prova_registro():
    r = RegistroStanza("stanza:1", tenuta_s=10, max_eventi=5)
    for i in range(8):
        r.aggiungi("riga", segmento=i, versione=1, testo=f"t{i}", inizio=time.time())
    verifica("registro in memoria con il tetto degli eventi", len(r) == 5 and r.tolti == 3)
    r.aggiungi("riga", segmento=7, versione=2, testo="t7 rivista", inizio=time.time())
    verifica("proiezione: la versione 2 sostituisce la 1 dello stesso segmento",
             [x["testo"] for x in r.righe()][-1] == "t7 rivista"
             and sum(x["segmento"] == 7 for x in r.righe()) == 1)
    vecchio = RegistroStanza("stanza:2", tenuta_s=1)
    vecchio.aggiungi("riga", t=time.time() - 5, segmento=1, testo="vecchia")
    vecchio.aggiungi("riga", segmento=2, testo="nuova")
    verifica("registro: tenuta in memoria (al più 24 h di serie)", len(vecchio) == 1)
    try:
        r.aggiungi("inventato")
        ok = False
    except ValueError:
        ok = True
    verifica("registro: tipi fuori dallo schema rifiutati", ok)
    e = r.eventi()[-1].a_dict("stanza:1")
    verifica("registro: la riga per il disco è pronta (chiave, seq, tipo, dati)",
             set(e) == {"registro", "seq", "t", "tipo", "dati"})


def prova_tool():
    from calliope.tools.spec import ToolContext
    from calliope.tools.stanza import _stanza_pausa, stanza_specs
    cfg = cfg_base()
    stanza = Stanza(cfg, STTFinto(), log=lambda m: None)
    stanza._info[3] = {"nome": "cucina", "stanza": "cucina", "canale": "satellite"}
    stanza.server = SimpleNamespace(attivo=SimpleNamespace(satellite={"id": 3}),
                                    per_id=lambda s: None)
    sc = SimpleNamespace(current_level="ospite", identified_by=None, current_speaker=None)
    ctx = ToolContext(cfg=cfg, speakers=RegistroVoci(), speaker_ctx=sc, speaker=None,
                      stanza=stanza)
    r = _stanza_pausa(ctx, "ospiti")
    verifica("tool: «abbiamo ospiti» lo può dire anche un ospite (spegne, 4 ore)",
             r["ok"] and stanza.stato_pausa(3)["motivo"] == "ospiti" and "fino alle" in
             r["risposta_finale"])
    r = _stanza_pausa(ctx, "riprendi")
    verifica("tool: riprendere non lo può un ospite (accende: contrario)",
             not r["ok"] and stanza.stato_pausa(3) is not None)
    sc.current_level, sc.identified_by, sc.current_speaker = "familiare", "voce", "Nicola"
    r = _stanza_pausa(ctx, "riprendi")
    verifica("tool: riprendere non lo può un minore (contrario)", not r["ok"])
    sc.current_level, sc.identified_by, sc.current_speaker = "familiare", "conversazione", "Carlo"
    r = _stanza_pausa(ctx, "riprendi")
    verifica("tool: riprendere non vale con la voce in zona grigia (contrario)", not r["ok"])
    sc.identified_by = "voce"
    r = _stanza_pausa(ctx, "riprendi")
    verifica("tool: un adulto riconosciuto dalla voce riprende", r["ok"]
             and stanza.stato_pausa(3) is None)
    r = _stanza_pausa(ctx, "pausa", 30)
    p = stanza.stato_pausa(3)
    verifica("tool: pausa per 30 minuti", r["ok"] and p["motivo"] == "pausa"
             and abs(p["fino"] - time.time() - 1800) < 5)
    verifica("tool: stato in lettura", "non ascolto" in _stanza_pausa(ctx, "stato")
             ["risposta_finale"].lower())
    spec = stanza_specs()[0]
    from calliope import politica, valore
    verifica("tool: classe e valore registrati (politica, valore)",
             spec.name in politica.CLASSI and spec.name in valore.EFFETTI)
    # «dimentica» svuota anche la stanza
    from calliope.tools.conversazioni import _conversazioni_dimentica
    stanza.registro(3).aggiungi("riga", segmento=1, testo="qualcosa")

    class Arch:
        proposte_dimentica = {}

        def dimentica(self, persona):
            return 1
    sc.current_speaker = "Carlo"
    ctx.conversazioni, ctx.turno = Arch(), 1
    import calliope.tools.conversazioni as tc
    vecchio = tc._chi
    tc._chi = lambda c: ("p-carlo", "Carlo")
    try:
        _conversazioni_dimentica(ctx)
        ctx.turno = 2
        _conversazioni_dimentica(ctx)
    finally:
        tc._chi = vecchio
    verifica("«dimentica le nostre conversazioni» (al «sì») svuota anche la stanza",
             len(stanza.registro(3)) == 0)
    stanza.chiudi()


def prova_ciclo():
    """I due ganci del ciclo (calliope/ciclo.py): la copertura alla frase trascritta, la riga del
    turno con chi parla, e i numeri finali nel registro dei turni."""
    from calliope.ciclo import Ciclo, Servizi
    cfg = cfg_base()
    stanza = Stanza(cfg, STTFinto(), registry=RegistroVoci(), log=lambda m: None)
    stanza._info[4] = {"nome": "studio", "stanza": "studio", "canale": "satellite"}
    scritti = []
    s = Servizi(cfg)
    s.stanza, s.registry = stanza, RegistroVoci()
    s.turns = SimpleNamespace(write=scritti.append)
    coll = SimpleNamespace(satellite={"id": 4})
    ora = time.monotonic()
    finto = SimpleNamespace(s=s, corsia=SimpleNamespace(satellite_id=None), ombra=None,
                            listener=SimpleNamespace(_ultima=(coll, 9), started_at=ora - 2.0,
                                                     ended_at=ora - 0.5),
                            rec={"voce": {"nome": "Carlo", "modo": "voce"}}, _turno=None)
    finto._stanza_dove = lambda: Ciclo._stanza_dove(finto)
    finto._stanza_esito = lambda t, rec: Ciclo._stanza_esito(finto, t, rec)   # passo 2
    t = SimpleNamespace(scritto=None, text="Calliope, accendi la luce")
    Ciclo._stanza_copertura(finto, t)
    Ciclo._stanza_turno(finto, t)
    riga = stanza.registro(4).righe()[-1]
    verifica("ciclo: la frase del turno nella stanza del satellite, con chi parla e «rivolta»",
             riga["testo"] == "Calliope, accendi la luce" and riga["nome"] == "Carlo"
             and riga["rivolta"] == "si" and riga["sicurezza"] == "voce")
    rec = dict(finto.rec)
    Ciclo._scrivi_turno(finto, rec)
    verifica("ciclo: nel registro dei turni la copertura in numeri (`stanza.copertura`)",
             scritti and scritti[-1]["stanza"]["copertura"] == {"dette": 0, "pronte": 0,
                                                                 "recupero_ms": 0,
                                                                 "oltre": False},
             str(scritti[-1].get("stanza") if scritti else None))
    finto.listener = SimpleNamespace(started_at=ora)          # audio locale: niente stanza
    finto.rec = {}
    Ciclo._stanza_copertura(finto, t)
    verifica("ciclo: senza satellite (audio locale) niente copertura (contrario)",
             "stanza" not in finto.rec)
    stanza.chiudi()


def prova_config():
    from calliope.config import load_config
    base = TMP / "conf"
    base.mkdir()
    (base / "calliope.yaml").write_text("{}\n", encoding="utf-8")
    for nome, testo in (("piatta", "stanza: ombra\nstanza_satelliti: [cucina]\n"),
                        ("sezione", "conversazione_stanza:\n  stanza: ombra\n"
                                    "  stanza_satelliti: [cucina]\n")):
        loc = base / f"{nome}.yaml"
        loc.write_text(testo, encoding="utf-8")
        vecchio = os.environ.get("CALLIOPE_CONFIG_LOCALE")
        os.environ["CALLIOPE_CONFIG_LOCALE"] = str(loc)
        try:
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                c = load_config(str(base / "calliope.yaml"))
        finally:
            if vecchio is None:
                os.environ.pop("CALLIOPE_CONFIG_LOCALE", None)
            else:
                os.environ["CALLIOPE_CONFIG_LOCALE"] = vecchio
        verifica(f"configurazione: stanza accesa dal file locale ({nome})",
                 c.stanza == "ombra" and c.stanza_satelliti == ["cucina"])


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        prova_segmentatore()
        prova_telefono_uguale()
        prova_precedenza()
        prova_registro()
        prova_spenta()
        prova_server()
        prova_tool()
        prova_ciclo()
        prova_config()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not errori else f"\n{errori} prove non riuscite.")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
