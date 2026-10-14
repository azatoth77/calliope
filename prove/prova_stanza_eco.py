"""
Prova a secco del passo 5 della conversazione di stanza (14/10/2026, decisione 0029, progetto
docs/ricerche/2026-10-13-conversazione-di-stanza.md § 5.3 e § 6): la stanza ascolta anche mentre
Calliope parla (`stanza_durante_voce`), con il filtro dell'eco (calliope/stanza/eco.py, regola
`eco_stanza`).

- il filtro sul testo: sola eco (esatta e storpiata da Whisper, con le cifre) → niente riga; una
  persona che parla sopra → riga intera; persona più eco → solo le parole della persona; i
  contrari: chi ripete una parola di Calliope dentro la sua frase, «grazie» detto sopra la sua
  voce, «Torino?» ripetuto fuori dal tempo della frase, tempi ignoti (vale il testo);
- il Segmentatore del satellite e quello del telefono (voce.js, con Node): spento come prima (la
  voce butta il segmento), acceso il segmento continua e porta le frasi che suonavano
  (`durante_voce`), il segnale senza testo come 0, nessuna frase → messaggio uguale a prima;
  `Riproduttore.voce_ora` con la coda dopo la frase; `AscoltoStanza.imposta`;
- il server dei satelliti vero con un satellite finto (protocollo 3): lo stato `durante_voce`
  nel benvenuto e dopo il saluto, le frasi mandate con `UscitaRemota` e il loro `suona`, la sola
  eco scartata («eco»), la persona tenuta (segnata `durante_voce`), il misto ripulito, la frase
  di lei citata molto dopo tenuta, il segmento legato al turno non trascritto; contrari: spento
  (segmento buttato come prima, «voce»), cancello dell'eco sul saluto (stato spento, segmento
  buttato «eco_cancello»), pausa per ospiti (niente righe);
- misure senza parole su disco e la riga «durante la voce» di `calliope stato --turni` con l'eco
  residua ogni 100 parole dette;
- la configurazione: spenta di serie, nella sezione della stanza.

Nomi di fantasia (Carlo). ~3 s.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

import prova_stanza as PS  # noqa: E402 — i satelliti finti e l'ambiente del passo 1
from calliope.config import Config  # noqa: E402
from calliope.satellite import protocollo as P  # noqa: E402
from calliope.satellite.stanza import AscoltoStanza, Segmentatore  # noqa: E402
from calliope.stanza import eco as E  # noqa: E402
from calliope.stanza import misure as misure_mod  # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
errori = 0

LEI = "Domani a Torino ci sarà il sole, con diciannove gradi di massima."
PERSONA = "Senti, io domani vado al mare con Carlo."


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio else ""),
          flush=True)


# ─────────────────────────── 1. il filtro sul testo ───────────────────────────
def prova_filtro():
    d = [E.Detta(LEI, 100.0, 4.0)]
    e = E.filtra("Domani a Torino ci sarà il sole con diciannove gradi di massima", d, 100, 104)
    verifica("sola eco, uguale: tutta eco, nessuna parola resta", e.tutta_eco and e.testo == ""
             and e.tolte == e.parole == 12, f"{e}")
    e = E.filtra("domani torino c'è sole con 19 gradi", d, 100.2, 104.3)
    verifica("eco storpiata da Whisper (c'è, 19 in cifre): tutta eco per la quota del 60 %",
             e.tutta_eco and "eco_stanza_quota" in e.regole, f"{e}")
    e = E.filtra(PERSONA, d, 100.5, 103)
    verifica("persona che parla sopra la sua voce: riga intera, niente tolto",
             not e.tutta_eco and e.testo == PERSONA and e.tolte == 0, e.testo)
    e = E.filtra(PERSONA + " Ci sarà il sole con diciannove gradi", d, 100, 106)
    verifica("persona più eco: tolte le 7 parole di lei di fila, restano quelle della persona",
             e.testo == "Senti io domani vado al mare con Carlo" and e.tolte == 7
             and "eco_stanza_fila" in e.regole, f"{e.testo!r} {e.tolte}")
    e = E.filtra("Ma davvero domani nevica? Io non ci credo.", d, 101, 103)
    verifica("contrario: ripete una parola di Calliope dentro la sua frase → intera",
             e.testo == "Ma davvero domani nevica? Io non ci credo." and e.tolte == 0
             and e.residua == 2, f"{e}")
    e = E.filtra("Grazie!", d, 101, 102)
    verifica("contrario: «grazie» detto sopra la sua voce resta", e.testo == "Grazie!"
             and not e.tutta_eco)
    e = E.filtra("Torino?", d, 107.5, 108)
    verifica("contrario: «Torino?» ripetuto tre secondi dopo la frase non è eco (tempo)",
             e.testo == "Torino?" and not e.tutta_eco)
    e = E.filtra("Torino?", d, 100.4, 101.2)
    verifica("«Torino?» nel momento in cui lei lo dice: eco (limite noto, una parola sola)",
             e.tutta_eco)
    e = E.filtra("ci sarà il sole con diciannove gradi", [E.Detta(LEI, 50.0, 4.0)], 100, 103)
    verifica("contrario: la sua frase citata quando lei non la diceva (fuori tempo) resta",
             not e.tutta_eco and e.tolte == 0)
    e = E.filtra("ci sarà il sole con diciannove gradi", [E.Detta(LEI)], None, None)
    verifica("tempi ignoti: vale il testo", e.tutta_eco)
    e = E.filtra(PERSONA, [], 100, 103)
    verifica("nessuna frase di Calliope: la riga resta com'è", e.testo == PERSONA
             and e.detto == 0)
    w = [x for x, _ in E.parole("Perché c’è l'Università? 21 e 1000")]
    verifica("normalizzazione: accenti, apostrofi, cifre in lettere",
             w == ["perche", "c", "e", "l", "universita", "ventuno", "e", "mille"], str(w))


# ─────────────────────────── 2. satellite e telefono ───────────────────────────
def corri(seq, occupato, voci, durante):
    cfg = Config()
    seg = Segmentatore(cfg)
    seg.durante = durante
    msg, ora = [], 1000.0
    for i, p in enumerate(seq):
        msg += seg.passo(np.full(512, 0.01, np.float32), p, occupato[i], ora, voce=voci[i])
        ora += 0.032
    return seg, msg


def prova_segmentatore():
    seq = PS.probs((0.3, 0.0), (2.0, 0.9), (1.0, 0.0))
    n = len(seq)
    occ = [20 <= i < 50 for i in range(n)]
    voci = [(3 if 20 <= i < 50 else (3 if 50 <= i < 60 else None)) for i in range(n)]
    seg, m = corri(seq, occ, voci, False)
    fine = [x[1] for x in m if x[0] == "fine"]
    verifica("spento: la voce di Calliope butta il segmento come prima (half-duplex)",
             fine and fine[0]["chiusura"] == "voce" and seg.buttati["voce"] == 1
             and "durante_voce" not in fine[0])
    seg, m = corri(seq, occ, voci, True)
    fine = [x[1] for x in m if x[0] == "fine"]
    verifica("acceso: il segmento continua sopra la sua voce e porta la frase che suonava",
             len(fine) == 1 and fine[0]["chiusura"] == "silenzio"
             and fine[0]["durante_voce"] == [3] and seg.buttati["voce"] == 0, str(fine))
    voci2 = [(0 if i < 30 else 4) if 20 <= i < 50 else None for i in range(n)]
    _, m = corri(seq, occ, voci2, True)
    fine = [x[1] for x in m if x[0] == "fine"]
    verifica("acceso: il segnale senza testo come 0, più frasi in ordine",
             fine and fine[0]["durante_voce"] == [0, 4], str(fine))
    _, m0 = corri(seq, [False] * n, [None] * n, False)
    _, m1 = corri(seq, [False] * n, [None] * n, True)
    verifica("acceso senza la sua voce: gli stessi messaggi di prima (niente campo nuovo)",
             [(x[0], x[1] if x[0] != "audio" else len(x[2])) for x in m0]
             == [(x[0], x[1] if x[0] != "audio" else len(x[2])) for x in m1])
    # Il pre-roll con la sua voce resta (spento si svuotava)
    seq2 = PS.probs((0.5, 0.0), (1.0, 0.9), (1.0, 0.0))
    occ2 = [True] * len(seq2)
    s_on, m_on = corri(seq2, occ2, [5] * len(seq2), True)
    campioni = sum(len(f) for x in m_on if x[0] == "audio" for f in x[2])
    verifica("acceso: il pre-roll non si svuota mentre lei parla",
             campioni >= 512 * int(1.0 * 1000 / 32) + 512 * 5, f"{campioni}")
    return seq, occ, voci


def prova_telefono(seq, occ, voci):
    node = shutil.which("node")
    if node is None:
        print("SALTATA IN PARTE: Node assente, niente confronto col Segmentatore del telefono")
        return
    cfg = Config()
    voce = (RADICE / "calliope" / "schermi" / "pagina" / "telefono" / "voce.js").as_uri()
    js = f"""
import {{ Segmentatore, AscoltoStanza }} from "{voce}";
const p = {{vad_threshold: {cfg.vad_threshold}, silence_ms: {cfg.silence_ms},
  preroll_ms: {cfg.preroll_ms}, min_speech_ms: {cfg.min_speech_ms}}};
const seq = {json.dumps(seq)}, occ = {json.dumps(occ)}, voci = {json.dumps(voci)};
const ris = {{}};
for (const durante of [false, true]) {{
  const s = new Segmentatore(p, 20, null);
  s.durante = durante;
  const out = []; let ora = 1000000;
  for (let i = 0; i < seq.length; i++) {{
    for (const m of s.passo(new Float32Array(512), seq[i], occ[i], ora, voci[i])) {{
      if (m[0] === "fine") out.push(m[1]);
    }}
    ora += 32;
  }}
  ris[durante ? "si" : "no"] = out;
}}
const a = new AscoltoStanza(p, () => {{}}, () => false, null, () => 7);
a.vad = {{}};
a.imposta(true, 20, true); ris.imposta_si = a.seg.durante;
a.imposta(true, 20, false); ris.imposta_no = a.seg.durante;
a.imposta(false, 20, true); ris.imposta_spenta = a.seg.durante;
console.log(JSON.stringify(ris));
"""
    r = subprocess.run([node, "--input-type=module", "-e", js], capture_output=True, text=True,
                       timeout=60)
    if r.returncode != 0:
        verifica("telefono: voce.js si carica in Node", False, r.stderr[-300:])
        return
    o = json.loads(r.stdout.strip().splitlines()[-1])
    verifica("telefono spento: la sua voce butta il segmento (come il satellite)",
             o["no"] and o["no"][0]["chiusura"] == "voce"
             and "durante_voce" not in o["no"][0], str(o["no"]))
    verifica("telefono acceso: segmento intero con la frase che suonava (come il satellite)",
             len(o["si"]) == 1 and o["si"][0]["chiusura"] == "silenzio"
             and o["si"][0]["durante_voce"] == [3], str(o["si"]))
    verifica("telefono: AscoltoStanza.imposta accende durante solo con la stanza attiva",
             o["imposta_si"] is True and o["imposta_no"] is False
             and o["imposta_spenta"] is False)


def prova_riproduttore():
    from calliope.satellite.client import Riproduttore
    r = Riproduttore.__new__(Riproduttore)
    r.in_corso, r._frase_id, r._frase_fine, r._pcm_fino = False, None, 0.0, 0.0
    verifica("voce_ora: casse ferme → None", r.voce_ora() is None)
    r.in_corso, r._frase_id = True, 9
    verifica("voce_ora: durante la frase → il suo id", r.voce_ora() == 9)
    r.in_corso, r._frase_fine = False, time.monotonic() - 0.5
    verifica("voce_ora: mezzo secondo dopo la fine → ancora lei (coda dell'eco)",
             r.voce_ora(1.0) == 9)
    r._frase_fine = time.monotonic() - 2.0
    verifica("voce_ora: due secondi dopo → None", r.voce_ora(1.0) is None)
    r._pcm_fino = time.monotonic() + 0.3
    verifica("voce_ora: un segnale o il saluto (senza testo) → 0", r.voce_ora() == 0)
    a = AscoltoStanza(Config(), lambda **k: None, lambda b: True, lambda: False, log=lambda m: None)
    a._thread = object()                       # niente thread né VAD veri
    a.imposta({"attiva": True, "durante_voce": True})
    si = a.seg.durante
    a.imposta({"attiva": True})
    no = a.seg.durante
    a.imposta({"attiva": False, "durante_voce": True})
    verifica("AscoltoStanza.imposta: durante solo se il server lo dice e la stanza è attiva",
             si is True and no is False and a.seg.durante is False)


# ─────────────────────────── 3. server con il satellite finto ───────────────────────────
class STTTesti:
    """Whisper finto: il marcatore nel primo campione sceglie il testo."""

    def __init__(self, testi):
        self.testi, self.ordine = testi, []
        self.ultima_scartata = None

    def transcribe(self, audio, prompt=None):
        m = int(round(float(audio[0]) * 1000))
        self.ordine.append(m)
        return self.testi.get(m, f"frase {m}")


def segmento(f, marcatore, durante=None, ascolto=None, secondi=1.0, fa_s=0.4):
    sid = next(f.ids)
    x = np.full(int(16000 * secondi), 0.05, np.float32)
    x[0] = marcatore / 1000
    f.ws.send(P.testo(tipo="stanza_inizio", id=sid, fa_s=fa_s))
    f.ws.send(P.binario(P.STANZA, sid, P.a_pcm(x)))
    fine = {"tipo": "stanza_fine", "id": sid, "durata_s": secondi,
            "parlato_ms": int(secondi * 1000), "chiusura": "silenzio", "ascolto": ascolto}
    if durante is not None:
        fine["durante_voce"] = durante
    f.ws.send(P.testo(**fine))
    return sid


USCITE: dict = {}
FRASE_S = 2.0


def frase_di_calliope(srv, sat_id, f, testo, secondi=FRASE_S):
    """Calliope dice `testo` sul satellite: la frase mandata con UscitaRemota (una per
    satellite, come una corsia) e il «suona» del satellite finto, poi finita adesso (cominciata
    `secondi` fa). L'id della frase."""
    from calliope.satellite.server import UscitaRemota
    u = USCITE.setdefault((id(srv), sat_id), UscitaRemota(srv, sat_id))
    n = len(f.messaggi)
    u.invia(1, testo, b"\0\0" * int(22050 * secondi), 22050)
    m = PS.aspetta(lambda: [x for x in f.messaggi[n:] if x.get("tipo") == "frase"])
    fid = m[0]["id"]
    f.ws.send(P.testo(tipo="suona", id=fid, uscita_s=0.0))
    coll = srv.per_id(sat_id)
    PS.aspetta(lambda: fid in coll.suonate)
    coll.suonate[fid] = time.monotonic() - secondi
    return fid


SOPRA = FRASE_S + 0.5          # un segmento cominciato prima della frase e chiuso dopo


def prova_server():
    from calliope.corsie import STTCondiviso
    testi = {1: LEI.replace(",", ""), 2: PERSONA, 3: PERSONA + " ci sarà il sole con diciannove",
             4: "Ci sarà il sole con diciannove gradi di massima", 5: "Calliope basta",
             6: "frase in pausa", 7: LEI, 8: LEI}
    cfg = PS.cfg_base(stanza_satelliti=[], stanza_durante_voce=True)
    stt = STTCondiviso(STTTesti(testi))
    srv, st = PS.ambiente(cfg, stt)
    url = f"ws://127.0.0.1:{srv.port}"
    try:
        tok, sat = PS.abbina(srv, "cucina")
        f = PS.Finto(url, tok)
        verifica("benvenuto: la stanza è accesa anche durante la voce",
                 (f.benvenuto.get("stanza") or {}).get("durante_voce") is True,
                 str(f.benvenuto.get("stanza")))
        m = PS.aspetta(lambda: [x for x in f.messaggi if x.get("tipo") == "stanza"])
        verifica("dopo il saluto (eco 0): lo stato di nuovo, durante_voce acceso",
                 m and m[-1].get("durante_voce") is True)
        reg = st.registro(sat["id"])
        fid = frase_di_calliope(srv, sat["id"], f, LEI)
        coll = srv.per_id(sat["id"])
        verifica("il server tiene la frase mandata (testo e durata) per il filtro",
                 coll.frasi_voce.get(fid, ("", 0))[0] == LEI
                 and abs(coll.frasi_voce[fid][1] - FRASE_S) < 0.01)
        segmento(f, 1, durante=[fid], fa_s=SOPRA)
        PS.aspetta(lambda: reg.conteggi().get("riga_scartata"))
        sc = reg.eventi("riga_scartata")
        verifica("sola eco durante la voce: niente riga, scartata «eco»",
                 sc and sc[-1].dati["motivo"] == "eco" and not reg.righe(), str(reg.conteggi()))
        segs = reg.eventi("segmento")
        verifica("il segmento nel registro porta le frasi che suonavano",
                 segs and segs[-1].dati["durante_voce"] == [fid])
        segmento(f, 2, durante=[fid], fa_s=SOPRA)
        PS.aspetta(lambda: len(reg.righe()) >= 1)
        r = reg.righe()[-1]
        verifica("persona che parla sopra: riga intera, segnata durante la voce",
                 r["testo"] == PERSONA and r.get("durante_voce") is True
                 and r.get("eco_tolte") == 0, str(r))
        segmento(f, 3, durante=[fid], fa_s=SOPRA)
        PS.aspetta(lambda: len(reg.righe()) >= 2)
        r = reg.righe()[-1]
        verifica("persona più eco: restano solo le parole della persona",
                 r["testo"] == "Senti io domani vado al mare con Carlo" and r["eco_tolte"] == 6,
                 str(r.get("testo")))
        # La frase di lei citata molto dopo (fuori dal tempo, e il satellite non la segna)
        fid2 = frase_di_calliope(srv, sat["id"], f, LEI)
        coll.suonate[fid2] = time.monotonic() - 30
        coll.suonate[fid] = time.monotonic() - 30
        segmento(f, 4)
        PS.aspetta(lambda: len(reg.righe()) >= 3)
        verifica("contrario: la sua frase citata mezzo minuto dopo resta una riga",
                 reg.righe()[-1]["testo"].startswith("Ci sarà il sole")
                 and "durante_voce" not in reg.righe()[-1])
        # Segmento non segnato ma nel tempo di una frase appena suonata: il server lo confronta
        fid3 = frase_di_calliope(srv, sat["id"], f, LEI)
        segmento(f, 7, fa_s=SOPRA)
        PS.aspetta(lambda: len(reg.eventi("riga_scartata")) >= 2)
        verifica("eco di coda (non segnata dal satellite, nel tempo della frase): scartata",
                 len(reg.eventi("riga_scartata")) == 2 and len(reg.righe()) == 3)
        # Legato a un turno («Calliope, basta» detto sopra la voce): non si trascrive
        n = len(stt._stt.ordine)
        f.comando(lid=11, n=3)
        segmento(f, 5, durante=[fid3], ascolto=11)
        PS.aspetta(lambda: any(e.dati.get("turno") == 11 for e in reg.eventi("segmento")))
        time.sleep(0.2)
        verifica("barge-in sopra la voce: il segmento legato al turno non si trascrive",
                 len(stt._stt.ordine) == n)
        # Pausa per ospiti: niente
        st.pausa(sat["id"], "ospiti", 240)
        n_righe = len(reg.righe())
        segmento(f, 6, durante=[fid3])
        time.sleep(0.4)
        verifica("contrario: in pausa per ospiti niente righe, nemmeno durante la voce",
                 len(reg.righe()) == n_righe and 6 not in stt._stt.ordine)
        st.riprendi(sat["id"])
        # Cancello: un satellite con l'eco sul saluto
        tok2, sat2 = PS.abbina(srv, "salotto")
        g = PS.Finto(url, tok2)
        PS.aspetta(lambda: [x for x in g.messaggi if x.get("tipo") == "stanza"])
        g.messaggi.clear()
        # Il saluto misurato con le casse senza cancellazione: il 30 % dei frame «parlato»
        g.ws.send(P.testo(tipo="pronto", eco=0.3))
        m = PS.aspetta(lambda: [x for x in g.messaggi if x.get("tipo") == "stanza"])
        verifica("cancello: eco sul saluto oltre la soglia → durante_voce spento per quel "
                 "satellite", m and m[-1].get("durante_voce") is False and m[-1]["attiva"])
        segmento(g, 8, durante=[1])
        time.sleep(0.4)
        mis = [x for x in st.misure.memoria if x.get("tipo") == "buttato"]
        verifica("cancello: il segmento detto durante la voce si butta («eco_cancello»)",
                 mis and mis[-1]["motivo"] == "eco_cancello" and 8 not in stt._stt.ordine)
        g.ws.close()
        # Misure
        seg_d = [x for x in st.misure.memoria if x.get("tipo") == "segmento" and x.get("durante")]
        verifica("misure: i segmenti durante la voce con i numeri dell'eco",
                 len(seg_d) >= 4 and all("detto_nuove" in x for x in seg_d)
                 and any(x.get("motivo") == "eco" for x in seg_d), str(len(seg_d)))
        disco = "".join(p.read_text(encoding="utf-8")
                        for p in Path(cfg.turn_log_dir).glob("stanza-*.jsonl"))
        verifica("misure su disco senza parole (né di lei né della persona)",
                 disco and not any(w in disco for w in ("Torino", "mare", "diciannove",
                                                       "Carlo", "sole")))
        rias = misure_mod.riassunto(misure_mod.leggi(cfg.turn_log_dir))
        cuc = next(iter(rias["giorni"].values()))["satelliti"]["cucina"]["durante"]
        verifica("riassunto: segmenti, righe tenute, scartate per eco, eco residua per 100",
                 cuc["segmenti"] >= 4 and cuc["righe"] == 2 and cuc["eco"] == 2
                 and cuc["detto"] == 2 * len(E.parole(LEI))
                 and cuc["residua_100"] is not None, str(cuc))
        txt = misure_mod.testo(rias)
        verifica("stato --turni: la riga «durante la voce» con l'eco residua e l'obiettivo",
                 "durante la voce (passo 5)" in txt and "ogni 100 parole dette" in txt
                 and "obiettivo < 2" in txt, txt[-300:])
        f.chiudi()
    finally:
        st.chiudi()
        srv.ferma()


def prova_spento():
    from calliope.corsie import STTCondiviso
    cfg = PS.cfg_base(stanza_satelliti=[])
    stt = STTCondiviso(STTTesti({1: LEI}))
    srv, st = PS.ambiente(cfg, stt)
    try:
        tok, sat = PS.abbina(srv, "cucina")
        f = PS.Finto(f"ws://127.0.0.1:{srv.port}", tok)
        verifica("spento (di serie): il benvenuto dice durante_voce falso",
                 (f.benvenuto.get("stanza") or {}).get("durante_voce") is False)
        PS.aspetta(lambda: srv.per_id(sat["id"]))
        segmento(f, 1, durante=[1])
        time.sleep(0.4)
        mis = [x for x in st.misure.memoria if x.get("tipo") == "buttato"]
        verifica("spento: un segmento segnato durante la voce si butta come prima («voce»)",
                 mis and mis[-1]["motivo"] == "voce" and not stt._stt.ordine
                 and not st.registro(sat["id"]).righe())
        segmento(f, 2)
        PS.aspetta(lambda: st.registro(sat["id"]).righe())
        r = st.registro(sat["id"]).righe()
        verifica("spento: un segmento normale resta una riga, senza i campi del passo 5",
                 r and "durante_voce" not in r[-1] and "eco_tolte" not in r[-1])
        f.chiudi()
    finally:
        st.chiudi()


def prova_config():
    c = Config()
    from calliope.config import SEZIONI
    verifica("configurazione: stanza_durante_voce spento di serie, nella sezione della stanza",
             c.stanza_durante_voce is False
             and "stanza_durante_voce" in SEZIONI["conversazione_stanza"])


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        prova_filtro()
        seq, occ, voci = prova_segmentatore()
        prova_telefono(seq, occ, voci)
        prova_riproduttore()
        prova_server()
        prova_spento()
        prova_config()
    finally:
        shutil.rmtree(PS.TMP, ignore_errors=True)
    print("\nTutto bene." if not errori else f"\n{errori} prove non riuscite.")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
