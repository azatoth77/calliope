"""Banco della corsia lenta della stanza (14/10, conversazione di stanza, passo 3; progetto
docs/ricerche/2026-10-13-conversazione-di-stanza.md § 6 riga 3: «WER e attribuzione su un set di
scambi registrati da adulti consenzienti in privato/, riferimento scritto a mano»).

NON fa parte del runner. Quattro modi:

1. **Sintetico** (si può lanciare oggi, sul portatile o sulla DGX):

       python prove/manuali/banco_stanza_lenta.py --sintetico [--rumore 20] [--salva DIR]
              [--cache FILE.npz] [--modello-lento large-v3] [--senza-prompt] [--dettagli]

   Scambi di fantasia con voci di Piper diverse (Carlo giorgio, Bianca paola, Nicola riccardo;
   un ospite leonardo; la TV con miro e aurora), impronte CAM++ vere fatte da altre frasi delle
   stesse voci, un po' di riverbero e rumore (`--rumore` SNR in dB, di serie 20) perché la
   corsia veloce sbagli qualcosa. Ogni segmento passa dalla `Stanza` vera (corsia veloce, Whisper
   vero con `make_transcriber`) e poi dalla `Lenta` vera. Ci sono segmenti di una voce, segmenti
   con due voci di fila (da spezzare), voci che si alternano, una fila di TV in una stanza vuota
   e un ospite che racconta con la famiglia presente (contrario della TV). Piper non è
   deterministico: `--cache FILE.npz` salva l'audio del set la prima volta e lo rilegge dopo,
   per confrontare due giri sulle stesse frasi. `--modello-lento NOME` dà alla corsia lenta un
   suo faster-whisper (per esempio large-v3, se la GPU ce l'ha accanto a quello dei turni: è
   la scelta del piano con `stanza_lenta_stt_url` sulla DGX); `--senza-prompt` toglie il prompt
   della corsia lenta, per misurarne l'effetto.

2. **Registrazioni vere** in `privato/` (adulti che lo sanno; non ci sono ancora):

       python prove/manuali/banco_stanza_lenta.py --cartella privato/banco-stanza [--salva DIR]

   Una sottocartella per scambio, con `scambio.json`:

       {"stanza": "cucina",
        "profili": {"Carlo": ["iscrizione/carlo-1.wav", "iscrizione/carlo-2.wav"]},
        "segmenti": [
          {"file": "s01.wav", "chiusura": "silenzio",
           "riferimento": [{"chi": "Carlo", "testo": "Allora sabato si parte alle otto."}]},
          {"file": "s02.wav",
           "riferimento": [{"chi": "Carlo", "testo": "Porto io i panini"},
                           {"chi": "Bianca", "testo": "e io le bibite."}]},
          {"file": "s03.wav", "riferimento": [{"chi": "tv", "testo": ""}]},
          {"file": "s04.wav", "riferimento": [{"chi": "?", "testo": "Buonasera a tutti."}]}]}

   WAV mono a 16 kHz (altri campionamenti si convertono), un file per segmento come lo chiude
   il VAD del satellite; `chi`: il nome del profilo, «?» per una voce che nessun profilo
   conosce, «tv» per una trasmissione (il testo non conta). Senza `profili` si usano i profili
   veri dell'installazione (`speakers.json`). I segmenti di uno scambio sono nell'ordine detto.

3. **L'audio del banco della stanza** (eccezione del 14/10 sera, `stanza_audio_banco_giorni`,
   calliope/stanza/banco.py), sulla DGX:

       python prove/manuali/banco_stanza_lenta.py --banco [registro/stanza_banco]

   La prima volta scrive accanto `riferimento.tsv` (file, v1, v2, riferimento vuoto): chi
   amministra scrive a mano la frase giusta nell'ultima colonna (vuota = da fare, «?» = non si
   capisce). Le volte dopo calcola WER della corsia veloce (v1) e della lenta (v2) sui segmenti
   col riferimento. (L'attribuzione qui è sempre di persone di casa: il banco salva solo quelle.)

4. **Le registrazioni conservate** ritrascritte (`prove/manuali/ritrascrivi_conservati.py`,
   sulla DGX), dopo che chi amministra ha segnato le scelte:

       python prove/manuali/banco_stanza_lenta.py --conservati privato/ritrascrizione-conservati-….md
              [--scelte scelte-ritrascrizione-….json]

   WER dell'originale e della lenta sul set intero (i casi uguali contano come giusti) e sui
   soli casi diversi, casi vinti dall'una e dall'altra. Le scelte (o, l, c col testo, ?) dal
   .md o dal JSON della pagina di revisione (`[{"n", "file", "scelta", "corretto"}]`, vince sul
   .md). Misura vera del 14/10 sera: originale 3,0 %, lenta 4,8 %.

   Con `--ritrascrivi` (sulla DGX, dalla cartella dei dati, col registro dei turni e la voce
   conservata) ogni registrazione del giro (fino all'ora nel nome del file; il riferimento è la
   scelta per i casi diversi e l'originale per quelli uguali) si ritrascrive con ciascun sistema:

       … --conservati FILE.md --scelte FILE.json --ritrascrivi [--url-lento URL]
              [--sistemi originale,turni,…] [--max N] [--persona ID] [--audio DIR] [--salva DIR]

   `originale` (il testo del registro), `turni` (il Whisper dei turni col suo prompt),
   `turni_senza_prompt` (la corsia lenta di prima sulla DGX), `lento_senza_prompt`,
   `lento_nomi` («Parla Carlo.»), `lento_nomi_parole` (il nome e le parole di prima, come
   `Lenta.prompt`), `lento_prompt_turni` (il secondo servizio col prompt dei turni). Il secondo
   servizio: `--url-lento`, o `stanza_lenta_stt_url`, o la porta di
   `setup/linux/motore/whisper-lento.sh` (8005). Stampa solo numeri: WER sul set e sui casi
   diversi, casi vinti, persi e pari contro `turni`, tempo mediano. L'obiettivo per riaccendere
   la ritrascrizione (`stanza_lenta_ritrascrivi`): un `lento*` con la WER sotto `turni`. Senza il
   registro dei turni (il portatile) i soli casi diversi, con l'audio da `--audio DIR`.

Misure (stampate, e in `--salva DIR/banco-stanza-lenta-AAAAMMGG-HHMM.json`, solo numeri): WER
della corsia veloce e della lenta (parole normalizzate, cifre in lettere), attribuzione giusta
per segmento di una voce (v1 e v2), blocchi con due voci spezzati e con le voci giuste, «più
voci», righe TV prese come TV e persone prese come TV (obiettivo 0), tempo di Whisper e di CAM++
della corsia lenta. Senza Piper, Whisper o il modello CAM++ esce con 77.
"""
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))
SALTA = 77
SR = 16000


def opzioni(argv):
    o, i = {"_": []}, 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            k = a[2:].replace("-", "_")
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                o[k] = argv[i + 1]
                i += 2
            else:
                o[k] = True
                i += 1
        else:
            o["_"].append(a)
            i += 1
    return o


def norm(t) -> list[str]:
    from calliope.stanza.eco import parole
    return [w for w, _ in parole(str(t or "").replace("%", " per cento"))]


def errori_parole(rif: list[str], ipo: list[str]) -> int:
    n, m = len(rif), len(ipo)
    d = list(range(m + 1))
    for i in range(1, n + 1):
        prima, d[0] = d[0], i
        for j in range(1, m + 1):
            c = min(d[j] + 1, d[j - 1] + 1, prima + (rif[i - 1] != ipo[j - 1]))
            prima, d[j] = d[j], c
    return d[m]


def wer_set(coppie) -> float | None:
    """WER sul set: errori totali / parole del riferimento."""
    err = tot = 0
    for rif, ipo in coppie:
        r = norm(rif)
        err += errori_parole(r, norm(ipo))
        tot += len(r)
    return round(100 * err / tot, 2) if tot else None


# ─────────────────────────── i profili in memoria ───────────────────────────
class Profili:
    """Un registro delle voci in memoria (niente speakers.json): CAM++ vero, profili dalla media
    delle impronte delle frasi d'iscrizione."""

    def __init__(self, cfg):
        from calliope.speaker_id import SpeakerEmbedder, normalize
        self.emb = SpeakerEmbedder(cfg.speaker_model, int(getattr(cfg, "speaker_threads", 2)))
        self._norm = normalize
        self.users: dict = {}

    def iscrivi(self, nome, audii, minore=False):
        import numpy as np
        vp = self._norm(np.mean([self.emb.embed(a, SR) for a in audii], axis=0))
        self.users[nome] = SimpleNamespace(id=f"p-{nome.lower()}", name=nome, voiceprint=vp,
                                           nascita="2012-05-01" if minore else None,
                                           fascia=None, admin=False, tutori=[])

    def embed(self, audio, sr=SR):
        return self.emb.embed(audio, sr)

    def classifica(self, e):
        import numpy as np
        return sorted([(n, float(np.dot(e, p.voiceprint))) for n, p in self.users.items()],
                      key=lambda x: -x[1])

    def get(self, n):
        return self.users.get(n)


# ─────────────────────────── il set sintetico ───────────────────────────
VOCI = {"Carlo": "it_IT-giorgio-medium", "Bianca": "it_IT-paola-medium",
        "Nicola": "it_IT-riccardo-x_low", "?": "it_IT-leonardo-medium",
        "tv": "it_IT-miro-medium", "tv2": "it_IT-aurora-medium"}
ISCRIZIONE = ["Oggi il cielo è sereno e fa abbastanza caldo per stare fuori.",
              "Ho letto un libro interessante sulla storia delle montagne.",
              "La mattina preparo sempre il caffè prima di uscire di casa.",
              "Il mercato del sabato ha la frutta più buona della città.",
              "Mi piace camminare lungo il fiume quando c'è poco vento."]
# Scambi di fantasia: (stanza, [(chiusura, [(chi, testo), …])]); due voci in un segmento = due
# persone di fila senza la pausa che chiude il segmento
SCAMBI = [
    ("cucina", [
        ("silenzio", [("Carlo", "Allora sabato partiamo presto per la gita al lago di Valfonda.")]),
        ("silenzio", [("Bianca", "Io direi alle otto, così troviamo parcheggio vicino al molo.")]),
        ("silenzio", [("Carlo", "Porto io i panini col prosciutto e la frittata di zucchine.")]),
        ("silenzio", [("Bianca", "Allora io penso alle bibite e alla torta di mele.")]),
        ("silenzio", [("Carlo", "Se piove andiamo al museo delle carrozze in città."),
                      ("Bianca", "Va bene, ma il museo chiude alle sei di sera.")]),
        ("silenzio", [("?", "Scusate il disturbo, sono il vicino del terzo piano.")]),
        ("silenzio", [("Carlo", "Prego, entri pure, stavamo organizzando la gita di sabato.")]),
    ]),
    ("sala", [
        ("silenzio", [("Nicola", "Papà, domani ho la verifica di matematica sulle frazioni.")]),
        ("silenzio", [("Carlo", "Hai ripassato gli esercizi del libro a pagina quarantadue?")]),
        ("silenzio", [("Nicola", "Sì, ma il problema del serbatoio non mi viene proprio.")]),
        ("silenzio", [("Carlo", "Dopo cena lo guardiamo insieme con calma."),
                      ("Nicola", "Grazie, però prima finisco la partita con Luca.")]),
        ("pausa_breve", [("Nicola", "Allora."), ("Carlo", "Prima i compiti."),
                         ("Nicola", "Ma dai."), ("Carlo", "Niente storie."),
                         ("Nicola", "Va bene.")]),
    ]),
    ("salotto", [
        ("lunga", [("tv", "Buonasera, apriamo questa edizione con le notizie dal mondo. "
                          "Il vertice internazionale si è chiuso con un accordo sul clima.")]),
        ("lunga", [("tv2", "Passiamo allo sport: la squadra di casa ha vinto la partita di ieri "
                           "sera con due reti nel secondo tempo davanti al pubblico.")]),
        ("lunga", [("tv", "E ora le previsioni del tempo: domani sole al nord, qualche nuvola "
                          "al centro e piogge sparse sulle isole maggiori.")]),
        ("lunga", [("tv2", "Grazie per averci seguito, il prossimo appuntamento è alle venti "
                           "e trenta con l'edizione della sera e gli approfondimenti.")]),
    ]),
    ("studio", [
        ("silenzio", [("Bianca", "Allora, com'è andato il viaggio in Portogallo?")]),
        ("silenzio", [("?", "Benissimo, siamo partiti da Lisbona e abbiamo girato tutta la costa "
                            "fino all'Algarve in macchina.")]),
        ("silenzio", [("?", "Le spiagge erano bellissime e il pesce alla griglia buonissimo, "
                            "soprattutto le sardine del mercato.")]),
        ("silenzio", [("?", "L'ultimo giorno siamo tornati a Lisbona e abbiamo preso il tram "
                            "giallo fino al castello.")]),
        ("silenzio", [("Bianca", "Che bello, l'anno prossimo ci andiamo anche noi.")]),
    ]),
]


def piper_16k(nome_voce: str, testo: str):
    import numpy as np
    from piper import PiperVoice
    cache = piper_16k.__dict__.setdefault("voci", {})
    v = cache.get(nome_voce)
    if v is None:
        # Le voci nel repository (portatile) o nella cartella dei dati (DGX: ~/calliope/voices)
        f = next((d / "voices" / f"{nome_voce}.onnx" for d in (RADICE, Path.cwd())
                  if (d / "voices" / f"{nome_voce}.onnx").exists()),
                 RADICE / "voices" / f"{nome_voce}.onnx")
        v = cache[nome_voce] = PiperVoice.load(str(f))
    x = np.frombuffer(b"".join(c.audio_int16_bytes for c in v.synthesize(testo)),
                      "<i2").astype(np.float32) / 32768
    r = v.config.sample_rate
    n = int(len(x) * SR / r)
    return (0.5 * np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)).astype(
        np.float32)


def stanza_vera(audio, snr_db: float, rng):
    """Un po' di stanza: riverbero breve e rumore a `snr_db`."""
    import numpy as np
    ir = np.exp(-np.arange(int(0.12 * SR)) / (0.03 * SR)) * rng.normal(0, 1, int(0.12 * SR))
    ir[0] = 1.0
    y = np.convolve(audio, ir * 0.25)[:len(audio)]
    y = y / max(1e-6, np.max(np.abs(y))) * 0.5
    p = float(np.mean(y ** 2)) or 1e-9
    y = y + rng.normal(0, np.sqrt(p / 10 ** (snr_db / 10)), len(y))
    return np.clip(y, -1, 1).astype(np.float32)


def set_sintetico(o, cfg):
    import numpy as np
    cache = Path(o["cache"]) if isinstance(o.get("cache"), str) else None
    if cache is not None and cache.exists():
        z = np.load(cache, allow_pickle=False)
        meta = json.loads(str(z["meta"]))
        prof = Profili(cfg)
        for nome in ("Carlo", "Bianca", "Nicola"):
            prof.iscrivi(nome, [z[f"isc_{nome}_{i}"] for i in range(len(ISCRIZIONE))],
                         minore=nome == "Nicola")
        scambi = [{"stanza": sc["stanza"],
                   "segmenti": [dict(sg, audio=z[f"seg_{k}_{j}"])
                                for j, sg in enumerate(sc["segmenti"])]}
                  for k, sc in enumerate(meta)]
        print(f"Set letto da {cache}")
        return scambi, prof
    rng = np.random.default_rng(14)
    arr: dict = {}
    snr = float(o.get("rumore") or 20)
    prof = Profili(cfg)
    for nome in ("Carlo", "Bianca", "Nicola"):
        isc = [stanza_vera(piper_16k(VOCI[nome], t), snr, rng) for t in ISCRIZIONE]
        for i, a in enumerate(isc):
            arr[f"isc_{nome}_{i}"] = a
        prof.iscrivi(nome, isc, minore=nome == "Nicola")
    scambi = []
    for stanza, segs in SCAMBI:
        out = []
        for chiusura, parti in segs:
            pezzi = []
            for chi, testo in parti:
                pezzi.append(piper_16k(VOCI[chi], testo))
                pezzi.append(np.zeros(int(0.25 * SR), np.float32))
            audio = stanza_vera(np.concatenate(pezzi), snr, rng)
            rif = [{"chi": "tv" if chi.startswith("tv") else chi, "testo": testo}
                   for chi, testo in parti]
            out.append({"audio": audio, "chiusura": chiusura, "riferimento": rif})
        scambi.append({"stanza": stanza, "segmenti": out})
    if cache is not None:
        meta = []
        for k, sc in enumerate(scambi):
            meta.append({"stanza": sc["stanza"], "segmenti": []})
            for j, sg in enumerate(sc["segmenti"]):
                arr[f"seg_{k}_{j}"] = sg["audio"]
                meta[-1]["segmenti"].append({x: sg[x] for x in ("chiusura", "riferimento")})
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache, meta=json.dumps(meta, ensure_ascii=False), **arr)
        print(f"Set salvato in {cache}")
    return scambi, prof


def leggi_wav16(p: Path):
    import numpy as np
    import soundfile as sf
    a, sr = sf.read(str(p), dtype="float32", always_2d=True)
    a = a.mean(axis=1)
    if sr != SR:
        n = int(len(a) * SR / sr)
        a = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)
    return a


def set_cartella(o, cfg):
    base = Path(o["cartella"])
    scambi, prof = [], None
    for d in sorted(p for p in base.iterdir() if (p / "scambio.json").exists()):
        js = json.loads((d / "scambio.json").read_text(encoding="utf-8"))
        if js.get("profili"):
            if prof is None:
                prof = Profili(cfg)
            for nome, files in js["profili"].items():
                if nome not in prof.users:
                    prof.iscrivi(nome, [leggi_wav16(d / f) for f in files])
        scambi.append({"stanza": js.get("stanza") or d.name,
                       "segmenti": [{"audio": leggi_wav16(d / s["file"]),
                                     "chiusura": s.get("chiusura") or "silenzio",
                                     "riferimento": s.get("riferimento") or []}
                                    for s in js.get("segmenti") or []]})
    if prof is None:
        from calliope.speaker_id import SpeakerRegistry
        prof = SpeakerRegistry(cfg)
    return scambi, prof


# ─────────────────────────── il giro vero ───────────────────────────
def esegui(cfg, scambi, prof, o=None) -> list[dict]:
    """Ogni segmento nella Stanza vera (corsia veloce) e poi nella Lenta vera: per segmento il
    riferimento, la riga v1 e le righe della proiezione dopo la corsia lenta."""
    import numpy as np

    import calliope.stanza.ascolto as asc
    from calliope.corsie import STTCondiviso
    from calliope.stanza import misure as misure_mod
    from calliope.stanza.ascolto import Stanza
    from calliope.stanza.lenta import Lenta
    from calliope.stanza.registro import RIGA, RIGA_SCARTATA
    from calliope.stt import make_transcriber
    stt = STTCondiviso(make_transcriber(cfg))
    mis = misure_mod.Misure(None)
    st = Stanza(cfg, stt, registry=prof, misure=mis, log=lambda m: None)
    o = o or {}
    stt_lento = None
    if isinstance(o.get("modello_lento"), str):
        import copy

        from calliope.stt import Transcriber
        c2 = copy.copy(cfg)
        c2.whisper_model = o["modello_lento"]
        stt_lento = STTCondiviso(Transcriber(c2))
        print(f"Corsia lenta con faster-whisper {o['modello_lento']} ({stt_lento.device})")
    le = Lenta(cfg, st, stt=stt_lento, registry=prof, log=print, avvia=False)
    if o.get("senza_prompt"):
        le.prompt = lambda a, righe: ""
    st.lenta = le
    off, v = [0.0], [0.0]
    asc.time = SimpleNamespace(time=lambda: time.time() + off[0], monotonic=time.monotonic,
                               sleep=time.sleep)
    out = []
    for k, sc in enumerate(scambi, 1):
        coll = SimpleNamespace(satellite={"id": k, "nome": sc["stanza"]}, canale="satellite",
                               stanza=sc["stanza"], frasi_voce={}, suonate={},
                               ritardo=lambda: 0.0)
        ids = []
        for j, seg in enumerate(sc["segmenti"], 1):
            a = seg["audio"]
            dur = len(a) / SR
            off[0] = v[0]
            st.inizio(coll, {"id": j, "fa_s": 0.0})
            st.pezzo(coll, j, (np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())
            off[0] = v[0] + dur + 0.7
            st.fine(coll, {"id": j, "chiusura": seg["chiusura"], "parlato_ms": int(dur * 1000),
                           "durata_s": dur})
            v[0] += dur + 1.5
            t0 = time.monotonic()
            while time.monotonic() - t0 < 120 and not any(
                    e.dati.get("segmento") == j for e in st.registro(k).eventi()
                    if e.tipo in (RIGA, RIGA_SCARTATA)):
                time.sleep(0.05)
            ids.append(j)
        v1 = {e.dati.get("segmento"): dict(e.dati) for e in st.registro(k).eventi(RIGA)
              if int(e.dati.get("versione") or 1) == 1}
        le.giro(time.time() + v[0] + 3600)
        proiez = st.registro(k).righe()
        for j, seg in zip(ids, sc["segmenti"]):
            out.append({"stanza": sc["stanza"], "segmento": j, "riferimento": seg["riferimento"],
                        "durata_s": round(len(seg["audio"]) / SR, 2), "v1": v1.get(j),
                        "v2": [r for r in proiez if r.get("segmento") == j]})
        print(f"  {sc['stanza']}: {len(ids)} segmenti")
    out_m = [r for r in mis.memoria if r["tipo"] == "lenta"]
    st.chiudi()
    return out, out_m


def giusto(r: dict | None, chi: str) -> bool:
    if r is None:
        return False
    if chi == "?":
        return r.get("chi") in ("ignoto", None) or r.get("sicurezza") == "nessuna"
    if chi == "tv":
        return r.get("chi") == "tv"
    return r.get("nome") == chi and r.get("sicurezza") == "voce"


def misura(righe: list[dict], lente: list[dict]) -> dict:
    coppie_v1, coppie_v2 = [], []
    uno = {"segmenti": 0, "v1": 0, "v2": 0}
    due = {"segmenti": 0, "spezzati": 0, "voci_giuste": 0, "piu_voci": 0}
    tv = {"righe_tv": 0, "prese": 0, "persone": 0, "persone_prese": 0}
    for r in righe:
        rif = r["riferimento"]
        chi = [x["chi"] for x in rif]
        testo_rif = " ".join(x["testo"] for x in rif if x["chi"] != "tv")
        v1 = r["v1"] or {}
        v2 = r["v2"]
        if "tv" in chi:
            tv["righe_tv"] += 1
            tv["prese"] += 1 if v2 and all(x.get("chi") == "tv" for x in v2) else 0
            continue
        tv["persone"] += 1
        tv["persone_prese"] += 1 if any(x.get("chi") == "tv" for x in v2) else 0
        coppie_v1.append((testo_rif, v1.get("testo") or ""))
        coppie_v2.append((testo_rif, " ".join(x.get("testo") or "" for x in v2)))
        nomi = list(dict.fromkeys(chi))
        if len(nomi) == 1:
            uno["segmenti"] += 1
            uno["v1"] += giusto(v1, nomi[0])
            uno["v2"] += len(v2) == 1 and giusto(v2[0], nomi[0])
        else:
            due["segmenti"] += 1
            if len(v2) >= 2:
                due["spezzati"] += 1
                due["voci_giuste"] += [x.get("nome") for x in v2] == [
                    c if c != "?" else None for c in nomi][:len(v2)]
            elif v2 and v2[0].get("chi") == "piu_voci":
                due["piu_voci"] += 1
    stt = [float(x.get("stt_s") or 0) for x in lente]
    return {"wer_v1": wer_set(coppie_v1), "wer_v2": wer_set(coppie_v2),
            "una_voce": uno, "due_voci": due, "tv": tv,
            "lenta": {"segmenti": len(lente), "whisper_s": round(sum(stt), 2),
                      "cam_s": round(sum(float(x.get("cam_ms") or 0) for x in lente) / 1000, 2),
                      "esiti": {e: sum(1 for x in lente if x.get("esito") == e)
                                for e in sorted({x.get("esito") for x in lente})}}}


def stampa(m: dict):
    u, d, t, le = m["una_voce"], m["due_voci"], m["tv"], m["lenta"]
    print(f"\nWER corsia veloce {m['wer_v1']} %, corsia lenta {m['wer_v2']} %")
    print(f"Una voce: chi parla giusto {u['v1']}/{u['segmenti']} (veloce), "
          f"{u['v2']}/{u['segmenti']} (lenta)")
    print(f"Due voci in un segmento: {d['segmenti']}, spezzati {d['spezzati']} (voci giuste "
          f"{d['voci_giuste']}), «più voci» {d['piu_voci']}")
    print(f"TV: {t['prese']}/{t['righe_tv']} righe della TV prese come TV; persone prese come TV "
          f"{t['persone_prese']}/{t['persone']} (obiettivo 0)")
    print(f"Corsia lenta: {le['segmenti']} segmenti, Whisper {le['whisper_s']} s, CAM++ "
          f"{le['cam_s']} s, esiti {le['esiti']}")


# ─────────────────────────── il banco della stanza e i conservati ───────────────────────────
def modo_banco(o, cfg) -> int:
    base = Path(o["banco"] if isinstance(o.get("banco"), str) else
                Path(cfg.turn_log_dir or "registro") / "stanza_banco")
    # Senza i testi dei blocchi (15/10, `<ora>-blocco-<id>.json`: niente audio loro)
    metas = sorted(p for p in base.rglob("*.json")
                   if p.name != "acceso.json" and "-blocco-" not in p.name)
    if not metas:
        print(f"Nessun segmento in {base}.")
        return SALTA
    tsv = base / "riferimento.tsv"
    rif: dict = {}
    if tsv.exists():
        for riga in tsv.read_text(encoding="utf-8").splitlines()[1:]:
            c = riga.split("\t")
            if len(c) >= 4 and c[3].strip():
                rif[c[0]] = c[3].strip()
    nuove = []
    coppie1, coppie2 = [], []
    for p in metas:
        m = json.loads(p.read_text(encoding="utf-8"))
        k = str(p.relative_to(base).with_suffix(".wav")).replace("\\", "/")
        t1 = (m.get("v1") or {}).get("testo") or ""
        t2 = " ".join(x.get("testo") or "" for x in m.get("v2") or []) or t1
        if k not in rif:
            nuove.append(f"{k}\t{t1}\t{t2}\t")
        elif rif[k] != "?":
            coppie1.append((rif[k], t1))
            coppie2.append((rif[k], t2))
    if nuove:
        nuovo = not tsv.exists()
        fd = os.open(tsv, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            if nuovo:
                fh.write("file\tv1\tv2\triferimento\n")
            fh.write("\n".join(nuove) + "\n")
        print(f"{len(nuove)} segmenti nuovi in {tsv}: scrivi la frase giusta nell'ultima colonna.")
    print(f"Con il riferimento: {len(coppie1)} segmenti; WER corsia veloce {wer_set(coppie1)} %, "
          f"corsia lenta {wer_set(coppie2)} %")
    return 0


def leggi_scelte(md: Path, scelte: Path | None = None) -> tuple[dict, list[dict]]:
    """(testa, casi) dal file di `ritrascrivi_conservati.py`: per ogni caso diverso n, file,
    originale, lenta, scelta, corretto. Con `scelte` (il JSON scaricato dalla pagina di
    revisione: [{"n", "file", "scelta", "corretto"}], 14/10 sera) le scelte vengono da lì (per
    file, o per n se il file manca) e vincono su quelle scritte nel .md."""
    testo = md.read_text(encoding="utf-8")
    m = re.search(r"<!-- banco: (\{.*?\}) -->", testo)
    testa = json.loads(m.group(1)) if m else {}
    casi = []
    for blocco in re.split(r"\n## ", testo)[1:]:
        intest = blocco.splitlines()[0]
        pezzi = [x.strip() for x in intest.split("·")]
        campi = dict(re.findall(r"^- (originale|lenta|scelta|corretto):[ \t]*(.*)$", blocco,
                                re.M))
        try:
            n = int(pezzi[0])
        except (ValueError, IndexError):
            n = len(casi) + 1
        casi.append({"n": n, "file": pezzi[-1] if len(pezzi) >= 4 else "",
                     "originale": campi.get("originale") or "", "lenta": campi.get("lenta") or "",
                     "scelta": (campi.get("scelta") or "").strip(),
                     "corretto": (campi.get("corretto") or "").strip()})
    if scelte is not None:
        js = json.loads(scelte.read_text(encoding="utf-8"))
        if isinstance(js, dict):                     # {"scelte": […]} o {n: {…}}
            js = js.get("scelte") or [dict(v, n=int(k)) for k, v in js.items()
                                      if str(k).isdigit() and isinstance(v, dict)]
        per_file = {str(x.get("file") or ""): x for x in js if x.get("file")}
        per_n = {int(x["n"]): x for x in js if str(x.get("n", "")).isdigit()}
        for c in casi:
            x = per_file.get(c["file"]) or per_n.get(c["n"])
            if x is not None:
                c["scelta"] = str(x.get("scelta") or "").strip()
                c["corretto"] = str(x.get("corretto") or "").strip()
    return testa, casi


def riferimento(caso: dict) -> str | None:
    """La frase giusta del caso: «?» = non si capisce (fuori dal conto), None = da fare."""
    s = (caso.get("scelta") or "").strip().lower()
    if not s:
        return None
    if s.startswith("?"):
        return "?"
    giusta = {"o": caso.get("originale"), "l": caso.get("lenta")}.get(s[0], caso.get("corretto"))
    return giusta or None


def confronto(errori: list[tuple[int, int]]) -> dict:
    """Per caso, gli errori di A e di B: quanti ne vince A, quanti B, quanti pari."""
    return {"vince_a": sum(1 for a, b in errori if a < b),
            "vince_b": sum(1 for a, b in errori if b < a),
            "pari": sum(1 for a, b in errori if a == b)}


def modo_conservati(o) -> int:
    """WER dell'originale e della lenta dal file dei casi diversi (i casi uguali contano come
    giusti): il conto del 14/10 sera, senza audio."""
    sc = Path(o["scelte"]) if isinstance(o.get("scelte"), str) else None
    testa, casi = leggi_scelte(Path(o["conservati"]), sc)
    coppie_o, coppie_l, per_caso, da_fare, non_capite = [], [], [], 0, 0
    for c in casi:
        rif = riferimento(c)
        if rif is None:
            da_fare += 1
            continue
        if rif == "?":
            non_capite += 1
            continue
        coppie_o.append((rif, c["originale"]))
        coppie_l.append((rif, c["lenta"]))
        r = norm(rif)
        per_caso.append((errori_parole(r, norm(c["originale"])),
                         errori_parole(r, norm(c["lenta"]))))
    parole_uguali = int(testa.get("parole_uguali") or 0)

    def wer(coppie, piu=0):
        err = sum(errori_parole(norm(r), norm(i)) for r, i in coppie)
        tot = sum(len(norm(r)) for r, _ in coppie) + piu
        return round(100 * err / tot, 2) if tot else None
    v = confronto(per_caso)
    print(f"Casi segnati {len(coppie_o)} (da fare {da_fare}, non capiti {non_capite}); uguali "
          f"{testa.get('uguali', '?')} ({parole_uguali} parole, contate come giuste)"
          + (f"; scelte da {sc.name}" if sc else ""))
    print(f"WER sul set: originale {wer(coppie_o, parole_uguali)} %, corsia lenta "
          f"{wer(coppie_l, parole_uguali)} %")
    print(f"Sui soli casi diversi: originale {wer(coppie_o)} %, corsia lenta {wer(coppie_l)} %; "
          f"per caso vince l'originale {v['vince_a']}, la lenta {v['vince_b']}, pari {v['pari']}")
    if o.get("ritrascrivi"):
        return modo_conservati_audio(o, testa, casi)
    return 0


# I sistemi confrontati sulle registrazioni conservate (14/10 sera): il Whisper dei turni come
# nei turni, quello dei turni senza prompt (la corsia lenta di prima sulla DGX: deve rifare il
# 4,8 %), e il secondo servizio (whisper-lento.sh) senza prompt, col nome di chi parla, col nome
# e le parole di prima (il prompt di Lenta.prompt), col prompt dei turni
SISTEMI = ("originale", "turni", "turni_senza_prompt", "lento_senza_prompt", "lento_nomi",
           "lento_nomi_parole", "lento_prompt_turni")


def _post_whisper(url: str, modello: str, lingua: str):
    import httpx

    from calliope.stt import unisci_righe, wav_bytes
    cli = httpx.Client(timeout=httpx.Timeout(60.0, connect=2.0))

    def f(audio, prompt):
        r = cli.post(url.rstrip("/") + "/audio/transcriptions",
                     files={"file": ("frase.wav", wav_bytes(audio, SR), "audio/wav")},
                     data={"model": modello, "language": lingua, "prompt": prompt,
                           "temperature": "0", "response_format": "json"})
        r.raise_for_status()
        return unisci_righe(str(r.json().get("text") or "")).strip()
    return f


def _vivo(url: str) -> bool:
    import urllib.request
    radice = re.sub(r"/v1/?$", "", url.rstrip("/"))
    try:
        with urllib.request.urlopen(radice + "/", timeout=2) as r:  # noqa: S310 — 127.0.0.1
            return r.status < 500
    except Exception:  # noqa: BLE001
        return False


def insieme_conservati(cfg, o, testa: dict, casi: list[dict]) -> tuple[list[dict], str]:
    """Le registrazioni del file dei casi: tutte quelle del giro di ritrascrivi_conservati.py
    (dal registro dei turni, fino all'ora nel nome del file), col riferimento: la scelta per i
    casi diversi, l'originale per quelli uguali (le due trascrizioni d'accordo). Senza il
    registro (il portatile) i soli casi diversi, con l'audio da `--audio DIR`."""
    from calliope.conserva import CARTELLA_VOCE
    per_file = {c["file"]: c for c in casi if c.get("file")}
    voce_dir = Path(o["audio"]) if isinstance(o.get("audio"), str) else \
        Path(cfg.turn_log_dir or "registro") / CARTELLA_VOCE
    turni = []
    try:
        from calliope.latenza import leggi
        turni = [r for r in leggi(str(Path(cfg.turn_log_dir or "registro")), None)
                 if r.get("voce_file") and str(r.get("testo") or "").strip()
                 and r.get("testo") != "(frase di conferma)"]
    except Exception:  # noqa: BLE001
        turni = []
    m = re.search(r"(\d{8})-(\d{4})", Path(o["conservati"]).name)
    if m and turni:
        fino = datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M")
        fino = fino.replace(second=59)

        def prima_di(r):
            try:
                return datetime.datetime.fromisoformat(str(r.get("inizio"))[:19]) <= fino
            except ValueError:
                return False
        turni = [r for r in turni if prima_di(r)]
    chi = str(o.get("persona") or "").strip().lower()
    if chi and turni:
        turni = [r for r in turni if chi in (str((r.get("voce") or {}).get("id") or "").lower(),
                                             str((r.get("voce") or {}).get("nome") or "").lower())]
    turni.sort(key=lambda r: str(r.get("inizio") or ""))
    out, ultimo = [], {}
    if turni:
        come = f"registro dei turni ({len(turni)} registrazioni con la voce)"
        for r in turni:
            v = r.get("voce") or {}
            pid = str(v.get("id") or v.get("nome") or "?")
            try:
                quando = datetime.datetime.fromisoformat(str(r.get("inizio"))[:23])
            except ValueError:
                quando = None
            prima = None
            if quando is not None and pid in ultimo and \
                    (quando - ultimo[pid][0]).total_seconds() < 300:
                prima = ultimo[pid][1]
            if quando is not None:
                ultimo[pid] = (quando, str(r.get("testo")))
            c = per_file.get(str(r["voce_file"]))
            rif = riferimento(c) if c is not None else str(r.get("testo"))
            out.append({"file": voce_dir / str(r["voce_file"]), "originale": str(r.get("testo")),
                        "riferimento": rif, "nome": v.get("nome"), "prima": prima,
                        "diverso": c is not None})
    else:
        come = "solo i casi diversi (nessun registro dei turni qui)"
        for c in casi:
            out.append({"file": voce_dir / c["file"], "originale": c["originale"],
                        "riferimento": riferimento(c), "nome": None, "prima": None,
                        "diverso": True})
    tot = int(testa.get("totale") or 0)
    if turni and tot and len(out) != tot:
        come += f"; ATTENZIONE: il file dei casi ne contava {tot}"
    return out, come


def modo_conservati_audio(o, testa: dict, casi: list[dict]) -> int:
    """`--conservati FILE.md --scelte FILE.json --ritrascrivi`: ogni registrazione ritrascritta
    da ciascun sistema; WER sul set e casi vinti contro il Whisper dei turni. Solo numeri."""
    import numpy as np

    from calliope.config import load_config
    from calliope.conserva import leggi_wav
    from calliope.stt import prompt_whisper
    cfg = load_config()
    reg, come = insieme_conservati(cfg, o, testa, casi)
    reg = [x for x in reg if x["riferimento"] not in (None, "?") and Path(x["file"]).exists()]
    if o.get("max"):
        reg = reg[:int(o["max"])]
    if not reg:
        print("Nessuna registrazione con riferimento e audio: salto.")
        return SALTA
    print(f"\nRitrascrizione di {len(reg)} registrazioni con riferimento ({come})")
    chiesti = [s.strip() for s in str(o.get("sistemi") or ",".join(SISTEMI)).split(",")
               if s.strip()]
    from calliope.macchina import whisper_lento_url
    url_lento = (o["url_lento"] if isinstance(o.get("url_lento"), str) else
                 whisper_lento_url(cfg))
    fun: dict = {}
    stt = None
    if any(s.startswith("turni") for s in chiesti):
        try:
            from calliope.stt import make_transcriber
            stt = make_transcriber(cfg)
        except Exception as e:  # noqa: BLE001
            print(f"Whisper dei turni non disponibile ({type(e).__name__}): niente «turni*»")
    if stt is not None:
        fun["turni"] = lambda a, x: stt.transcribe(a)
        fun["turni_senza_prompt"] = lambda a, x: stt.transcribe(a, prompt="")
    if any(s.startswith("lento") for s in chiesti):
        if _vivo(url_lento):
            mod = str(getattr(cfg, "stanza_lenta_stt_modello", "") or "") or cfg.stt_modello
            lento = _post_whisper(url_lento, mod, cfg.language)
            car = int(getattr(cfg, "stanza_lenta_prompt_caratteri", 160) or 0)

            def nomi(x):
                return f"Parla {str(x['nome']).split()[0]}." if x.get("nome") else ""

            def nomi_parole(x):
                coda = " ".join(str(x.get("prima") or "").split())[-car:] if car else ""
                if coda and len(coda) == car and " " in coda:
                    coda = coda.split(" ", 1)[1]
                return " ".join(y for y in (nomi(x), coda) if y)
            fun["lento_senza_prompt"] = lambda a, x: lento(a, "")
            fun["lento_nomi"] = lambda a, x: lento(a, nomi(x))
            fun["lento_nomi_parole"] = lambda a, x: lento(a, nomi_parole(x))
            fun["lento_prompt_turni"] = lambda a, x: lento(a, prompt_whisper(cfg))
            print(f"Secondo servizio su {url_lento}")
        else:
            print(f"Il secondo servizio non risponde su {url_lento}: niente «lento*» "
                  "(calliope motore whisper-lento stato)")
    sistemi = [s for s in chiesti if s == "originale" or s in fun]
    ipotesi = {s: [] for s in sistemi}
    tempi = {s: [] for s in sistemi}
    pausa = float(o.get("pausa") or 0.2)
    for i, x in enumerate(reg, 1):
        audio, sr = leggi_wav(Path(x["file"]))
        if sr != SR:
            n = int(len(audio) * SR / sr)
            audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)),
                              audio).astype("float32")
        for s in sistemi:
            if s == "originale":
                ipotesi[s].append(x["originale"])
                continue
            t0 = time.perf_counter()
            try:
                ipotesi[s].append(fun[s](audio, x) or "")
            except Exception as e:  # noqa: BLE001
                print(f"  {i}: {s} errore {type(e).__name__}")
                ipotesi[s].append("")
            tempi[s].append(time.perf_counter() - t0)
            time.sleep(pausa)
        if i % 10 == 0:
            print(f"  {i}/{len(reg)}")
    rif = [norm(x["riferimento"]) for x in reg]
    tot = sum(len(r) for r in rif)
    err = {s: [errori_parole(r, norm(h)) for r, h in zip(rif, ipotesi[s])] for s in sistemi}
    base = "turni" if "turni" in err else "originale"
    diversi = [k for k, x in enumerate(reg) if x["diverso"]]
    tot_d = sum(len(rif[k]) for k in diversi)
    risultati = {}
    print(f"\n{len(reg)} registrazioni ({tot} parole di riferimento; casi diversi del file "
          f"{len(diversi)}). Contro «{base}»: vinti / persi / pari per caso.")
    print(f"{'sistema':22} {'WER':>7} {'WER diversi':>12} {'vinti':>6} {'persi':>6} "
          f"{'pari':>5} {'p50 s':>6}")
    for s in sistemi:
        w = round(100 * sum(err[s]) / tot, 2) if tot else None
        wd = round(100 * sum(err[s][k] for k in diversi) / tot_d, 2) if tot_d else None
        v = confronto(list(zip(err[s], err[base])))
        p50 = round(float(np.median(tempi[s])), 2) if tempi[s] else None
        risultati[s] = {"wer": w, "wer_diversi": wd, "vinti": v["vince_a"], "persi": v["vince_b"],
                        "pari": v["pari"], "p50_s": p50}
        print(f"{s:22} {w if w is not None else '-':>7} {wd if wd is not None else '-':>12} "
              f"{v['vince_a']:>6} {v['vince_b']:>6} {v['pari']:>5} "
              f"{p50 if p50 is not None else '-':>6}")
    if base in risultati:
        meglio = [s for s in risultati if s.startswith("lento")
                  and (risultati[s]["wer"] or 1e9) < (risultati[base]["wer"] or 0)]
        print("\nObiettivo per riaccendere la ritrascrizione: WER sotto «" + base + "» ("
              + str(risultati[base]["wer"]) + " %). "
              + ("Lo passano: " + ", ".join(meglio) if meglio else "Nessun «lento» lo passa."))
    if o.get("salva"):
        d = Path(o["salva"])
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"banco-conservati-{datetime.datetime.now():%Y%m%d-%H%M}.json"
        p.write_text(json.dumps({"modo": "conservati", "registrazioni": len(reg),
                                 "parole": tot, "diversi": len(diversi), "base": base,
                                 "url_lento": url_lento, "sistemi": risultati},
                                ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Numeri in {p}")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    o = opzioni(sys.argv[1:])
    if o.get("conservati"):
        return modo_conservati(o)
    from calliope.config import load_config
    cfg = load_config()
    if o.get("banco"):
        return modo_banco(o, cfg)
    if not (o.get("sintetico") or o.get("cartella")):
        print(__doc__)
        return 2
    cfg.stanza, cfg.stanza_lenta = "ombra", True
    cfg.stanza_satelliti = []
    cfg.speaker_min_voice_s = 0.5
    cfg.stanza_lenta_riassunto_righe = 0
    try:
        scambi, prof = set_sintetico(o, cfg) if o.get("sintetico") else set_cartella(o, cfg)
    except Exception as e:  # noqa: BLE001
        print(f"Set non pronto ({type(e).__name__}: {e}): salto.")
        return SALTA
    print(f"{sum(len(s['segmenti']) for s in scambi)} segmenti in {len(scambi)} scambi")
    try:
        righe, lente = esegui(cfg, scambi, prof, o)
    except Exception as e:  # noqa: BLE001
        print(f"Whisper o la stanza non pronti ({type(e).__name__}: {e}): salto.")
        return SALTA
    m = misura(righe, lente)
    stampa(m)
    if o.get("dettagli"):
        for r in righe:
            print(f"- {r['stanza']} {r['segmento']}: rif {[x['chi'] for x in r['riferimento']]} "
                  f"| v1 {(r['v1'] or {}).get('nome') or (r['v1'] or {}).get('chi')}: "
                  f"{(r['v1'] or {}).get('testo')} | v2 "
                  + " / ".join(f"{x.get('nome') or x.get('chi')}: {x.get('testo')}"
                               for x in r["v2"]))
    if o.get("salva"):
        d = Path(o["salva"])
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"banco-stanza-lenta-{datetime.datetime.now():%Y%m%d-%H%M}.json"
        p.write_text(json.dumps({"modo": "sintetico" if o.get("sintetico") else "cartella",
                                 "rumore_db": o.get("rumore"),
                                 "modello_lento": o.get("modello_lento"),
                                 "senza_prompt": bool(o.get("senza_prompt")), **m},
                                ensure_ascii=False,
                                indent=1), encoding="utf-8")
        print(f"Numeri in {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
