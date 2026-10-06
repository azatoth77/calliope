"""
Prova del riconoscimento di chi parla: MFCC attuale (speaker_id.py) contro modelli
neurali di embedding del parlante in ONNX (sherpa-onnx).

Rapporto: docs/ricerche/2026-09-24-riconoscimento-parlante.md

Nota del 26/09/2026: dopo la scelta di CAM++ sono stati cancellati i modelli scartati, i
file parquet, il venv .venv-dati e sherpa-onnx dal .venv. In models/speaker/ restano
CAM++ e i WAV degli impostori. Per ripetere la misura completa bisogna riscaricare i
modelli e reinstallare sherpa-onnx. L'MFCC di prima è copiato qui dentro (MfccModel).

Sottocomandi (i dati finiscono in models/speaker/, ignorata da git):

  prepara   estrae gli impostori umani italiani (MLS e VoxPopuli) dai file parquet.
            Richiede pyarrow: si lancia con il venv separato models/speaker/.venv-dati
            (pip install pyarrow soundfile numpy huggingface_hub fsspec).
  piper     genera gli impostori sintetici con le 10 voci Piper di voices/ (16 kHz).
  misura    calcola gli embedding e le metriche (EER, rifiuti di Dario a FA <= 1 %,
            durata, famiglia simulata, aggiornamento dell'impronta, latenza, memoria).
            Argomenti facoltativi: nomi (anche parziali) dei modelli da misurare.
            --senza-latenza riusa la latenza già misurata (gli embedding sono in cache).
  latenza   solo latenza e memoria dei finalisti (o dei modelli nominati).
  fbank     verifica che un fbank in solo numpy + onnxruntime dia gli stessi
            embedding di sherpa-onnx (integrazione senza dipendenze nuove).

Esempio:
  models\\speaker\\.venv-dati\\Scripts\\python prove\\prova_speaker.py prepara
  .venv\\Scripts\\python prove\\prova_speaker.py piper
  .venv\\Scripts\\python prove\\prova_speaker.py misura
"""

import ctypes, io, json, sys, time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models" / "speaker"
DATI = MODELS / "dati"
RISULTATI = MODELS / "risultati"
SR = 16000

# Frasi della sessione dell'8° test (v03c) dette in una conversazione con un'altra
# persona: non è certo che siano di Dario. Escluse dal set di Dario, punteggi a parte.
INCERTE = {"20260924-135711", "20260924-135714", "20260924-135725", "20260924-135740"}

# Modelli candidati (release "speaker-recongition-models" di sherpa-onnx).
MODELLI = [
    "wespeaker_en_voxceleb_resnet34_LM",
    "wespeaker_en_voxceleb_CAM++_LM",
    "wespeaker_en_voxceleb_resnet152_LM",
    "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced",
    "3dspeaker_speech_eres2net_base_200k_sv_zh-cn_16k-common",
    "3dspeaker_speech_eres2netv2_sv_zh-cn_16k-common",
    "nemo_en_titanet_small",
    "nemo_en_titanet_large",
    # stessi pesi, ma fbank in numpy + onnxruntime con la media per frase (CMN) come
    # nell'addestramento di WeSpeaker e 3D-Speaker: sherpa-onnx non la applica ai WeSpeaker
    "np:wespeaker_en_voxceleb_resnet34_LM",
    "np:wespeaker_en_voxceleb_CAM++_LM",
    "np:3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced",
    "np:3dspeaker_speech_eres2netv2_sv_zh-cn_16k-common",
]


def make_model(name: str, threads: int = 4):
    if name == "mfcc":
        m = MfccModel()
    elif name.startswith("np:"):
        m = NumpyOnnxModel(name[3:], threads)
    else:
        m = SherpaModel(name, threads)
    m.name = name
    return m

FRASI_PIPER = [
    "Calliope.",
    "Che ore sono?",
    "Qual è la capitale della Francia?",
    "E quella della Spagna?",
    "Oggi è proprio una bella giornata.",
    "Puoi cambiare voce?",
    "Calliope, quanto dista la Luna dalla Terra?",
    "Perché il cielo è azzurro?",
    "Dimmi tre città della Toscana.",
    "Chi ha scritto i Promessi Sposi?",
    "Ricordati che il mio numero preferito è quarantasette.",
    "Senti, secondo te conviene prendere l'ombrello se il cielo è nuvoloso?",
    "Ieri sera ho visto un documentario sulla storia dell'Impero romano e mi sono "
    "chiesto quanto tempo ci volesse per andare da Roma a Costantinopoli a cavallo.",
    "Calliope, sai chi sono?",
    "Metti un po' di musica in cucina.",
    "Accendi la luce del soggiorno.",
    "Chiamami Dario.",
    "Calliope, esci.",
]


# ──────────────────────────── PREPARAZIONE DATI ────────────────────────────

def _save_wav(path: Path, audio: np.ndarray):
    import soundfile as sf
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio, SR, subtype="PCM_16")


def _decode(b: bytes) -> np.ndarray:
    import soundfile as sf
    a, sr = sf.read(io.BytesIO(b), dtype="float32", always_2d=True)
    a = a.mean(axis=1)
    if sr != SR:
        import soxr
        a = soxr.resample(a, sr, SR)
    return a.astype(np.float32)


def cmd_prepara(max_per_spk: int = 12):
    """Estrae gli impostori umani in models/speaker/dati/{mls,voxpopuli}/<parlante>/."""
    import pyarrow.parquet as pq
    rng = np.random.default_rng(0)
    meta = []

    # Multilingual LibriSpeech italiano, test + dev: 20 lettori di audiolibri (CC BY 4.0)
    for split in ("test", "dev"):
        f = DATI / f"mls_it_{split}.parquet"
        if not f.exists():
            print(f"manca {f}: scaricalo da huggingface.co/datasets/facebook/"
                  f"multilingual_librispeech (italian/{split}-00000-of-00001.parquet)")
            continue
        t = pq.read_table(f, columns=["audio", "speaker_id", "id"])
        by_spk = defaultdict(list)
        for i, s in enumerate(t.column("speaker_id").to_pylist()):
            by_spk[s].append(i)
        for spk, idx in by_spk.items():
            for i in rng.permutation(idx)[:max_per_spk]:
                row = t.slice(int(i), 1).to_pylist()[0]
                a = _decode(row["audio"]["bytes"])
                out = DATI / "mls" / f"mls{spk}" / f"{row['id']}.wav"
                _save_wav(out, a)
                meta.append(("mls", f"mls{spk}", "", out.name, len(a) / SR))
        print(f"MLS {split}: {len(by_spk)} parlanti")

    # VoxPopuli italiano, solo il secondo row group del test (~150 MB, CC0)
    from huggingface_hub import HfFileSystem
    fs = HfFileSystem()
    pf = pq.ParquetFile(fs.open("datasets/facebook/voxpopuli/it/test-00000-of-00001.parquet"))
    t = pf.read_row_group(1, columns=["audio", "speaker_id", "gender", "audio_id"])
    by_spk = defaultdict(list)
    for i, s in enumerate(t.column("speaker_id").to_pylist()):
        if s and s != "None":
            by_spk[s].append(i)
    n = 0
    for spk, idx in by_spk.items():
        if len(idx) < 2:
            continue
        n += 1
        for i in rng.permutation(idx)[:max_per_spk]:
            row = t.slice(int(i), 1).to_pylist()[0]
            a = _decode(row["audio"]["bytes"])
            out = DATI / "voxpopuli" / f"vp{spk}" / f"{row['audio_id'].replace(':', '-')}.wav"
            _save_wav(out, a)
            meta.append(("voxpopuli", f"vp{spk}", row["gender"], out.name, len(a) / SR))
    print(f"VoxPopuli: {n} parlanti con almeno 2 frasi")

    with open(DATI / "impostori_umani.tsv", "w", encoding="utf-8") as fo:
        fo.write("corpus\tparlante\tgenere\tfile\tdurata_s\n")
        for m in meta:
            fo.write("\t".join(map(str, m[:4])) + f"\t{m[4]:.2f}\n")
    print(f"{len(meta)} frasi salvate in {DATI}")


def cmd_piper():
    """Genera le frasi di FRASI_PIPER con tutte le voci di voices/, a 16 kHz."""
    import soxr
    from piper import PiperVoice
    for onnx in sorted((ROOT / "voices").glob("*.onnx")):
        voice = PiperVoice.load(str(onnx))
        sr = voice.config.sample_rate
        for k, text in enumerate(FRASI_PIPER):
            pcm = b"".join(ch.audio_int16_bytes for ch in voice.synthesize(text))
            a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
            if sr != SR:
                a = soxr.resample(a, sr, SR).astype(np.float32)
            # un po' di silenzio attorno, come nelle frasi captate dal VAD
            a = np.concatenate([np.zeros(int(0.3 * SR), np.float32), a,
                                np.zeros(int(0.2 * SR), np.float32)])
            _save_wav(DATI / "piper" / onnx.stem / f"{k:02d}.wav", a)
        print(f"{onnx.stem}: {len(FRASI_PIPER)} frasi")


# ──────────────────────────── CARICAMENTO ────────────────────────────

def _read(path: Path) -> np.ndarray:
    import soundfile as sf
    a, sr = sf.read(str(path), dtype="float32", always_2d=True)
    a = a.mean(axis=1)
    if sr != SR:
        import soxr
        a = soxr.resample(a, sr, SR)
    return a.astype(np.float32)


def load_items():
    """Restituisce un elenco di dict: id, parlante, gruppo, sessione, durata, audio."""
    items = []
    for wav in sorted((ROOT / "registrazioni").glob("*/*.wav")):
        a = _read(wav)
        items.append(dict(id=wav.stem, spk="Dario" if wav.stem not in INCERTE else "incerta",
                          group="dario" if wav.stem not in INCERTE else "incerta",
                          session=wav.parent.name, dur=len(a) / SR, audio=a))
    dario_durs = np.array([it["dur"] for it in items if it["group"] == "dario"])

    # Impostori umani: due ritagli per frase, uno con la durata presa dalla
    # distribuzione delle frasi di Dario e uno breve (1,6–2,5 s, come «Calliope.» o
    # «Che ore sono?» captate dal VAD, silenzi compresi).
    # In più, per ogni frase (Dario compreso) il secondo più energico: parlato vero di 1 s.
    rng = np.random.default_rng(1)
    for corpus in ("mls", "voxpopuli"):
        for wav in sorted((DATI / corpus).glob("*/*.wav")):
            a = _read(wav)
            for kind in ("come_dario", "breve"):
                d = float(rng.choice(dario_durs)) if kind == "come_dario" else float(rng.uniform(1.6, 2.5))
                n = min(len(a), int(d * SR))
                start = int(rng.integers(0, len(a) - n + 1))
                items.append(dict(id=f"{wav.stem}:{kind}", spk=wav.parent.name, group="umani",
                                  session=corpus, dur=n / SR, audio=a[start:start + n]))
            items.append(dict(id=f"{wav.stem}:1s", spk=wav.parent.name, group="umani_1s",
                              session=corpus, dur=1.0, audio=loudest_second(a)))
    for wav in sorted((DATI / "piper").glob("*/*.wav")):
        a = _read(wav)
        items.append(dict(id=f"{wav.parent.name}:{wav.stem}", spk=wav.parent.name, group="piper",
                          session="piper", dur=len(a) / SR, audio=a))
        items.append(dict(id=f"{wav.parent.name}:{wav.stem}:1s", spk=wav.parent.name, group="piper_1s",
                          session="piper", dur=1.0, audio=loudest_second(a)))
    for it in [it for it in items if it["group"] == "dario"]:
        items.append(dict(id=f"{it['id']}:1s", spk="Dario", group="dario_1s", session=it["session"],
                          dur=1.0, audio=loudest_second(it["audio"])))
    return items


def loudest_second(a: np.ndarray) -> np.ndarray:
    """Il secondo di audio con più energia (parlato vero, senza i silenzi del VAD)."""
    if len(a) <= SR:
        return a
    c = np.concatenate([[0.0], np.cumsum(a.astype(np.float64) ** 2)])
    e = c[SR::160] - c[:len(c) - SR:160][:len(c[SR::160])]
    start = int(np.argmax(e)) * 160
    return a[start:start + SR]


# ──────────────────────────── EMBEDDING ────────────────────────────

class MfccModel:
    name = "MFCC (attuale)"

    def __init__(self):
        sys.path.insert(0, str(ROOT))
        import torch
        torch.set_num_threads(1)     # con la CPU contesa i thread di torch girano a vuoto
        self.torch = torch

    def embed(self, audio):
        """Copia dell'impronta MFCC usata fino al 24/09 (speaker_id.mfcc_embedding, tolta
        con il passaggio a CAM++): serve a ripetere il confronto del rapporto."""
        import torchaudio
        if len(audio) < SR // 2:
            audio = np.pad(audio, (0, SR // 2 - len(audio)))
        wave = self.torch.from_numpy(np.asarray(audio, dtype=np.float32)).unsqueeze(0)
        feats = torchaudio.compliance.kaldi.mfcc(wave, SR, num_mel_bins=23, num_ceps=13,
                                                 high_freq=7600, low_freq=20)
        return feats.mean(dim=0).numpy().astype(np.float32)


class SherpaModel:
    def __init__(self, name: str, threads: int = 4):
        import sherpa_onnx as so
        self.name = name
        cfg = so.SpeakerEmbeddingExtractorConfig(model=str(MODELS / f"{name}.onnx"),
                                                 num_threads=threads, provider="cpu")
        self.ex = so.SpeakerEmbeddingExtractor(cfg)

    def embed(self, audio):
        if len(audio) < int(0.5 * SR):     # troppo corto per il modello: si allunga col silenzio
            audio = np.pad(audio, (0, int(0.5 * SR) - len(audio)))
        s = self.ex.create_stream()
        s.accept_waveform(SR, audio)
        s.input_finished()
        return np.array(self.ex.compute(s), dtype=np.float32)


def embed_all(model, items):
    cache = RISULTATI / f"emb_{model.name.replace(':', '_')}.npz"
    ids = [it["id"] for it in items]
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        if list(z["ids"]) == ids:
            return z["emb"]
    t0 = time.perf_counter()
    emb = np.stack([model.embed(it["audio"]) for it in items])
    print(f"   {len(items)} embedding in {time.perf_counter() - t0:.1f} s")
    RISULTATI.mkdir(parents=True, exist_ok=True)
    np.savez(cache, ids=np.array(ids), emb=emb)
    return emb


def norm(x):
    return x / (np.linalg.norm(x, axis=-1, keepdims=True) + 1e-10)


def profile(emb_rows, raw_mean: bool):
    # MFCC: come speaker_id.py (media degli embedding grezzi); neurali: media dei normalizzati
    return np.mean(emb_rows, axis=0) if raw_mean else np.mean(norm(emb_rows), axis=0)


def cos(a, p):
    return norm(a) @ norm(p)


# ──────────────────────────── METRICHE ────────────────────────────

def eer(tgt, imp):
    s = np.concatenate([tgt, imp])
    y = np.concatenate([np.ones(len(tgt)), np.zeros(len(imp))])
    o = np.argsort(-s)
    y = y[o]
    far = np.cumsum(1 - y) / len(imp)
    frr = 1 - np.cumsum(y) / len(tgt)
    i = np.argmin(np.abs(far - frr))
    return float((far[i] + frr[i]) / 2)


def thr_at_far(imp, far=0.01):
    """Soglia minima con falsi accettati <= far (punteggio >= soglia = accettato)."""
    s = np.sort(imp)[::-1]
    k = int(np.floor(far * len(s)))       # quanti impostori possiamo accettare
    return float(s[k] + 1e-6) if k < len(s) else float(s[-1])


def frr_at(tgt, thr):
    return float(np.mean(tgt < thr))


def far_at(imp, thr):
    return float(np.mean(imp >= thr))


# ──────────────────────────── MISURA ────────────────────────────

def private_bytes() -> int:
    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t)]
    c = PMC(); c.cb = ctypes.sizeof(PMC)
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    k32.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(PMC), ctypes.c_ulong]
    k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.PrivateUsage


def latency(name, items):
    """Latenza per frase a 1 e 4 thread (mediana di 10), su frasi vere di Dario."""
    dario = [it for it in items if it["group"] == "dario"]
    samples = {}
    for target in (1.0, 3.0, 8.0):
        it = min(dario, key=lambda x: abs(x["dur"] - target))
        samples[target] = it["audio"]
    out = {}
    for threads in (1, 4):
        mem0 = private_bytes()
        m = make_model(name, threads)
        m.embed(samples[3.0])
        mem = (private_bytes() - mem0) / 2**20
        for target, a in samples.items():
            ts = []
            for _ in range(10):
                t0 = time.perf_counter(); m.embed(a); ts.append(time.perf_counter() - t0)
            out[f"{threads}t_{target:g}s"] = float(np.median(ts) * 1000)
        out[f"mem_{threads}t_MiB"] = mem
        del m
    return out


def evaluate(emb, items, raw_mean, rng, draws=30):
    groups = np.array([it["group"] for it in items])
    spk = np.array([it["spk"] for it in items])
    durs = np.array([it["dur"] for it in items])
    sess = np.array([it["session"] for it in items])
    dario = np.where(groups == "dario")[0]
    umani = np.where(groups == "umani")[0]
    piper = np.where(groups == "piper")[0]
    imp = np.concatenate([umani, piper])
    d1s = np.where(groups == "dario_1s")[0]
    i1s = np.where((groups == "umani_1s") | (groups == "piper_1s"))[0]
    enroll_pool = dario[durs[dario] >= 1.5]
    res = {}

    for k in (3, 5, 10):
        rows = []
        for _ in range(draws):
            enr = rng.choice(enroll_pool, size=k, replace=False)
            p = profile(emb[enr], raw_mean)
            test = np.setdiff1d(dario, enr)
            st, si = cos(emb[test], p), cos(emb[imp], p)
            su, sp = cos(emb[umani], p), cos(emb[piper], p)
            thr = thr_at_far(si, 0.01)
            short_t = durs[test] < 2.5
            short_i = durs[imp] < 2.5
            enr_ids = {items[i]["id"] + ":1s" for i in enr}
            t1 = np.array([i for i in d1s if items[i]["id"] not in enr_ids])
            s1t, s1i = cos(emb[t1], p), cos(emb[i1s], p)
            rows.append(dict(
                eer=eer(st, si), eer_umani=eer(st, su), eer_piper=eer(st, sp),
                thr1=thr, frr1=frr_at(st, thr),
                frr1_brevi=frr_at(st[short_t], thr), frr1_lunghe=frr_at(st[~short_t], thr),
                far_brevi=far_at(si[short_i], thr), far_lunghe=far_at(si[~short_i], thr),
                eer_brevi=eer(st[short_t], si[short_i]), eer_lunghe=eer(st[~short_t], si[~short_i]),
                eer_1s=eer(s1t, s1i), frr_1s=frr_at(s1t, thr), far_1s=far_at(s1i, thr),
                dario_min=float(st.min()), dario_p5=float(np.percentile(st, 5)),
                dario_med=float(np.median(st)), dario_max=float(st.max()),
                umani_max=float(su.max()), umani_p99=float(np.percentile(su, 99)),
                umani_med=float(np.median(su)),
                piper_max=float(sp.max()), piper_med=float(np.median(sp)),
            ))
        agg = {key: dict(media=float(np.mean([r[key] for r in rows])),
                         peggiore=float(np.max([r[key] for r in rows])) if key.startswith(("eer", "frr", "far", "umani", "piper"))
                         else float(np.min([r[key] for r in rows])))
               for key in rows[0]}
        res[f"enr{k}"] = agg

    # Soglia fissa (mediana delle soglie a FA 1 % con 3 frasi): cosa succede a un valore unico
    ths = []
    for _ in range(draws):
        enr = rng.choice(enroll_pool, size=3, replace=False)
        p = profile(emb[enr], raw_mean)
        ths.append(thr_at_far(cos(emb[imp], p), 0.01))
    res["soglia_dario"] = float(np.median(ths))

    # Stesso canale: gli impostori di Dario vengono da altri microfoni, e il canale li
    # rende facili da scartare. Qui ogni parlante di MLS/VoxPopuli viene arruolato con 3
    # frasi e messo contro gli altri parlanti dello stesso corpus (stesso tipo di canale):
    # è la situazione di una famiglia registrata con lo stesso microfono. La soglia a
    # FA 1 % calcolata qui è quella usata nel resto (sessioni, aggiornamento, famiglia).
    stem = np.array([it["id"].split(":")[0] for it in items])
    sc_t, sc_i, sc_tb, sc_ib, sc_t1, sc_i1 = [], [], [], [], [], []
    rng_sc = np.random.default_rng(3)
    for corpus in ("mls", "voxpopuli"):
        cu = [i for i in umani if sess[i] == corpus]
        c1 = np.array([i for i in np.where(groups == "umani_1s")[0] if sess[i] == corpus])
        spks = sorted({spk[i] for i in cu})
        for sp in spks:
            stems = sorted({stem[i] for i in cu if spk[i] == sp})
            if len(stems) < 6:
                continue
            for _ in range(5):
                es = set(rng_sc.choice(stems, size=3, replace=False))
                enr = [i for i in cu if spk[i] == sp and stem[i] in es and items[i]["id"].endswith("come_dario")]
                p = profile(emb[enr], raw_mean)
                tg = np.array([i for i in cu if spk[i] == sp and stem[i] not in es])
                im = np.array([i for i in cu if spk[i] != sp])
                t_s, i_s = cos(emb[tg], p), cos(emb[im], p)
                sc_t.append(t_s); sc_i.append(i_s)
                sc_tb.append(t_s[durs[tg] < 2.5]); sc_ib.append(i_s[durs[im] < 2.5])
                t1 = np.array([i for i in c1 if spk[i] == sp and stem[i] not in es])
                i1 = np.array([i for i in c1 if spk[i] != sp])
                sc_t1.append(cos(emb[t1], p)); sc_i1.append(cos(emb[i1], p))
    T, I = np.concatenate(sc_t), np.concatenate(sc_i)
    thr_fixed = thr_at_far(I, 0.01)
    thr_01 = thr_at_far(I, 0.001)
    Tb, Ib, T1, I1 = map(np.concatenate, (sc_tb, sc_ib, sc_t1, sc_i1))
    # Dario alla soglia «stesso canale», con 3 e 10 frasi di arruolamento
    dr = {}
    for k in (3, 5, 10):
        f1, f01, fb, f1s = [], [], [], []
        for _ in range(draws):
            enr = rng.choice(enroll_pool, size=k, replace=False)
            p = profile(emb[enr], raw_mean)
            test = np.setdiff1d(dario, enr)
            st = cos(emb[test], p)
            enr_ids = {items[i]["id"] + ":1s" for i in enr}
            t1 = np.array([i for i in d1s if items[i]["id"] not in enr_ids])
            f1.append(frr_at(st, thr_fixed)); f01.append(frr_at(st, thr_01))
            fb.append(frr_at(st[durs[test] < 2.5], thr_fixed)); f1s.append(frr_at(cos(emb[t1], p), thr_fixed))
        dr[f"enr{k}"] = dict(frr=float(np.mean(f1)), frr_peggiore=float(np.max(f1)),
                             frr_far01=float(np.mean(f01)), frr_brevi=float(np.mean(fb)),
                             frr_1s=float(np.mean(f1s)))
    p = profile(emb[rng.choice(enroll_pool, size=3, replace=False)], raw_mean)
    res["stesso_canale"] = dict(
        prove_bersaglio=int(len(T)), prove_impostore=int(len(I)),
        eer=eer(T, I), soglia_far1=thr_fixed, soglia_far01=thr_01,
        frr_far1=frr_at(T, thr_fixed), frr_far01=frr_at(T, thr_01),
        eer_brevi=eer(Tb, Ib), frr_brevi=frr_at(Tb, thr_fixed), far_brevi=far_at(Ib, thr_fixed),
        eer_1s=eer(T1, I1), frr_1s=frr_at(T1, thr_fixed), far_1s=far_at(I1, thr_fixed),
        bersaglio_p5=float(np.percentile(T, 5)), bersaglio_med=float(np.median(T)),
        impostore_p99=float(np.percentile(I, 99)), impostore_max=float(I.max()),
        dario=dr, piper_far=far_at(cos(emb[piper], p), thr_fixed),
        piper_max=float(cos(emb[piper], p).max()))
    res["soglia_fissa"] = thr_fixed

    # Due sessioni: arruolamento con le prime 3 frasi (>= 1,5 s) del 21/09, verifica sul 24/09
    d21 = [i for i in dario if sess[i].startswith("2026-09-21") and durs[i] >= 1.5][:3]
    d24 = np.array([i for i in dario if sess[i].startswith("2026-09-24")])
    p = profile(emb[d21], raw_mean)
    st, si = cos(emb[d24], p), cos(emb[imp], p)
    res["sessioni"] = dict(eer=eer(st, si), frr_soglia_fissa=frr_at(st, thr_fixed),
                           far_soglia_fissa=far_at(si, thr_fixed), dario_min=float(st.min()))

    # Frasi incerte (v03c, conversazione con un'altra persona): punteggio contro il profilo del 21/09
    inc = np.where(groups == "incerta")[0]
    res["incerte"] = {items[i]["id"]: round(float(cos(emb[i], p)), 3) for i in inc}

    # Aggiornamento dell'impronta: profilo del 21/09 aggiornato con le frasi del 21/09
    # accettate con margine (media mobile, alfa 0,1, ancorata all'impronta iniziale);
    # si confronta sul 24/09 con il profilo fermo.
    p0 = norm(profile(emb[d21], raw_mean))
    pu = p0.copy()
    t_upd = thr_fixed + 0.10
    n_upd = 0
    for i in [i for i in dario if sess[i].startswith("2026-09-21") and i not in d21]:
        if cos(emb[i], pu) >= t_upd:
            cand = norm(0.9 * pu + 0.1 * norm(emb[i]))
            if float(cand @ p0) >= 0.90:          # ancora: non allontanarsi dall'impronta di partenza
                pu, n_upd = cand, n_upd + 1
    st_u, si_u = cos(emb[d24], pu), cos(emb[imp], pu)
    # Avvelenamento: le frasi del parlante umano più simile a Dario passano mai la soglia di aggiornamento?
    su0 = cos(emb[umani], p0)
    worst_spk = spk[umani][np.argmax(su0)]
    wi = [i for i in umani if spk[i] == worst_spk]
    pp, n_pois = p0.copy(), 0
    for _ in range(3):
        for i in wi:
            if cos(emb[i], pp) >= t_upd:
                cand = norm(0.9 * pp + 0.1 * norm(emb[i]))
                if float(cand @ p0) >= 0.90:
                    pp, n_pois = cand, n_pois + 1
    res["aggiornamento"] = dict(
        soglia_aggiornamento=t_upd, aggiornamenti=n_upd,
        deriva_cos=float(pu @ p0),
        eer_fermo=eer(st, si), eer_aggiornato=eer(st_u, si_u),
        frr_fermo=frr_at(st, thr_fixed), frr_aggiornato=frr_at(st_u, thr_fixed),
        far_fermo=far_at(si, thr_fixed), far_aggiornato=far_at(si_u, thr_fixed),
        impostore_piu_simile=str(worst_spk), aggiornamenti_impostore=n_pois)

    # Curva: soglie a diversi falsi accettati «stesso canale» → rifiuti di Dario (3, 5, 10
    # frasi) e famiglia simulata (Dario + 6 parlanti umani arruolati con 3 frasi; tutti
    # gli altri, Piper compresi, sono ospiti). Con più profili in casa un ospite ha più
    # occasioni di somigliare a qualcuno: per questo la famiglia accetta più ospiti del
    # singolo confronto.
    curve = []
    for far_t in (0.02, 0.01, 0.005, 0.002, 0.001):
        thr = thr_at_far(I, far_t)
        row = dict(far_obiettivo=far_t, soglia=thr, frr_stesso_canale=frr_at(T, thr))
        for k in (3, 5, 10):
            fr = []
            rngc = np.random.default_rng(11)
            for _ in range(draws):
                enr = rngc.choice(enroll_pool, size=k, replace=False)
                fr.append(frr_at(cos(emb[np.setdiff1d(dario, enr)], profile(emb[enr], raw_mean)), thr))
            row[f"frr_dario_{k}"] = float(np.mean(fr))
        row.update(family(emb, items, raw_mean, thr, enroll_pool, groups, spk, umani, stem))
        curve.append(row)
    res["curva"] = curve
    res["famiglia"] = family(emb, items, raw_mean, thr_fixed, enroll_pool, groups, spk, umani, stem)
    return res


def family(emb, items, raw_mean, thr, enroll_pool, groups, spk, umani, stem, draws=5):
    """Famiglia simulata: Dario + 6 parlanti umani con 3 frasi; il resto sono ospiti."""
    rng2 = np.random.default_rng(7)
    cand_spk = sorted({s for s in spk[umani] if len({stem[i] for i in umani if spk[i] == s}) >= 8})
    ok = wrong = rej = guest_ok = guest_in = 0
    for _ in range(draws):
        fam = list(rng2.choice(cand_spk, size=min(6, len(cand_spk)), replace=False))
        profiles, excl_stems = {}, set()
        d_enr = list(rng2.choice(enroll_pool, size=3, replace=False))
        profiles["Dario"] = profile(emb[d_enr], raw_mean)
        excl_stems |= {stem[i] for i in d_enr}
        for s in fam:
            idx = [i for i in umani if spk[i] == s and items[i]["id"].endswith("come_dario")]
            e = list(rng2.choice(idx, size=3, replace=False))
            profiles[s] = profile(emb[e], raw_mean)
            excl_stems |= {stem[i] for i in e}
        names = list(profiles)
        P = np.stack([norm(profiles[n]) for n in names])
        for i in range(len(items)):
            if stem[i] in excl_stems or groups[i] not in ("dario", "umani", "piper"):
                continue
            sc = norm(emb[i]) @ P.T
            j = int(np.argmax(sc))
            who = names[j] if sc[j] >= thr else None
            true = spk[i] if spk[i] in profiles else None
            if true is None:
                guest_ok += who is None; guest_in += who is not None
            else:
                ok += who == true; wrong += (who is not None and who != true); rej += who is None
    fam_tot = ok + wrong + rej
    return dict(familiari_giusti=ok / fam_tot, scambiati=wrong / fam_tot, rifiutati=rej / fam_tot,
                ospiti_accettati=guest_in / (guest_ok + guest_in),
                prove_familiari=fam_tot, prove_ospiti=guest_ok + guest_in)


def cmd_misura(filtri):
    items = load_items()
    g = defaultdict(int)
    for it in items:
        g[it["group"]] += 1
    spk_n = {grp: len({it["spk"] for it in items if it["group"] == grp}) for grp in g}
    print(f"Frasi: {dict(g)}; parlanti: {spk_n}")
    d = np.array([it["dur"] for it in items if it["group"] == "dario"])
    print(f"Dario: {len(d)} frasi, durata {d.min():.1f}–{d.max():.1f} s, "
          f"{np.mean(d < 2.5) * 100:.0f} % sotto 2,5 s")

    names = ["mfcc"] + MODELLI
    if filtri:
        filtri = [f for f in filtri if not f.startswith("--")]
    if filtri:
        names = [n for n in names if any(f.lower() in n.lower() for f in filtri)]
    RISULTATI.mkdir(parents=True, exist_ok=True)
    allres = {}
    out_json = RISULTATI / "risultati.json"
    if out_json.exists():
        allres = json.loads(out_json.read_text(encoding="utf-8"))
    for name in names:
        print(f"\n== {name}")
        m = make_model(name)
        emb = embed_all(m, items)
        del m
        r = evaluate(emb, items, raw_mean=(name == "mfcc"), rng=np.random.default_rng(42))
        if "--senza-latenza" in sys.argv and "latenza" in allres.get(name, {}):
            r["latenza"] = allres[name]["latenza"]     # si tiene la misura precedente
        else:
            r["latenza"] = latency(name, items)
        r["dim"] = int(emb.shape[1])
        r["mb"] = round((MODELS / f"{name.removeprefix('np:')}.onnx").stat().st_size / 1e6, 1) if name != "mfcc" else 0
        allres[name] = r
        e3, e10 = r["enr3"], r["enr10"]
        print(f"   EER 3 frasi {e3['eer']['media']*100:.2f} % (peggiore {e3['eer']['peggiore']*100:.2f}), "
              f"10 frasi {e10['eer']['media']*100:.2f} %; rifiuti Dario a FA 1 %: "
              f"{e3['frr1']['media']*100:.1f} % / {e10['frr1']['media']*100:.1f} %; soglia fissa {r['soglia_fissa']:.3f}")
        sc = r["stesso_canale"]
        print(f"   stesso canale: EER {sc['eer']*100:.2f} %, soglia FA 1 % {sc['soglia_far1']:.3f} "
              f"(bersagli rifiutati {sc['frr_far1']*100:.1f} %); Dario rifiutato a quella soglia: "
              f"{sc['dario']['enr3']['frr']*100:.1f} % (3 frasi), {sc['dario']['enr10']['frr']*100:.1f} % (10)")
        print(f"   latenza 1 thread 3 s: {r['latenza']['1t_3s']:.1f} ms; famiglia: {r['famiglia']}")
        out_json.write_text(json.dumps(allres, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nRisultati in {out_json}")


# ──────────────────────────── FBANK IN NUMPY ────────────────────────────

def kaldi_fbank(audio: np.ndarray, num_mel=80, sr=SR) -> np.ndarray:
    """Fbank «alla Kaldi» (dither 0, finestra povey, preenfasi 0,97, snip edges) in solo numpy."""
    flen, fshift, nfft = int(0.025 * sr), int(0.010 * sr), 512
    n = 1 + (len(audio) - flen) // fshift
    idx = np.arange(flen)[None, :] + fshift * np.arange(n)[:, None]
    fr = audio[idx].astype(np.float64)
    fr -= fr.mean(axis=1, keepdims=True)
    fr = np.concatenate([fr[:, :1] - 0.97 * fr[:, :1], fr[:, 1:] - 0.97 * fr[:, :-1]], axis=1)
    win = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(flen) / (flen - 1))) ** 0.85
    spec = np.abs(np.fft.rfft(fr * win, nfft)) ** 2
    mel = lambda f: 1127.0 * np.log(1 + f / 700.0)
    lo, hi = mel(20.0), mel(sr / 2)
    centers = np.linspace(lo, hi, num_mel + 2)
    fft_mel = mel(np.arange(nfft // 2 + 1) * sr / nfft)
    fb = np.zeros((num_mel, nfft // 2 + 1))
    for m in range(num_mel):
        l, c, r = centers[m], centers[m + 1], centers[m + 2]
        up = (fft_mel - l) / (c - l); down = (r - fft_mel) / (r - c)
        fb[m] = np.maximum(0, np.minimum(up, down))
    return np.log(np.maximum(spec @ fb.T, np.finfo(np.float32).eps)).astype(np.float32)


class NumpyOnnxModel:
    """Embedding con onnxruntime + fbank numpy (solo modelli WeSpeaker e 3D-Speaker)."""

    def __init__(self, name, threads=1):
        import onnxruntime as ort
        self.name = name
        so = ort.SessionOptions(); so.intra_op_num_threads = threads
        self.s = ort.InferenceSession(str(MODELS / f"{name}.onnx"), so, providers=["CPUExecutionProvider"])
        meta = self.s.get_modelmeta().custom_metadata_map
        self.scale = 32768.0 if meta.get("normalize_samples", "1") == "0" else 1.0
        self.inp = self.s.get_inputs()[0].name

    def embed(self, audio):
        f = kaldi_fbank(audio * self.scale)
        f -= f.mean(axis=0, keepdims=True)          # media per frase (CMN)
        return self.s.run(None, {self.inp: f[None]})[0][0]


def cmd_fbank():
    items = [it for it in load_items() if it["group"] == "dario"][:20]
    for name in ("wespeaker_en_voxceleb_resnet34_LM", "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced",
                 "3dspeaker_speech_eres2netv2_sv_zh-cn_16k-common"):
        a, b = SherpaModel(name, 1), NumpyOnnxModel(name, 1)
        c = [float(cos(a.embed(it["audio"]), b.embed(it["audio"]))) for it in items]
        t0 = time.perf_counter()
        for it in items: b.embed(it["audio"])
        t_np = (time.perf_counter() - t0) / len(items) * 1000
        t0 = time.perf_counter()
        for it in items: a.embed(it["audio"])
        t_sh = (time.perf_counter() - t0) / len(items) * 1000
        print(f"{name}: coseno sherpa/numpy min {min(c):.5f} media {np.mean(c):.5f}; "
              f"ms per frase numpy {t_np:.1f}, sherpa {t_sh:.1f}")


def cmd_latenza(filtri):
    """Solo latenza e memoria, sui modelli indicati (predefiniti: i finalisti)."""
    names = filtri or ["mfcc", "np:3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced",
                       "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced",
                       "3dspeaker_speech_eres2net_base_200k_sv_zh-cn_16k-common",
                       "np:3dspeaker_speech_eres2netv2_sv_zh-cn_16k-common",
                       "np:wespeaker_en_voxceleb_resnet34_LM", "nemo_en_titanet_small"]
    items = [it for it in load_items() if it["group"] == "dario"]
    try:
        import os
        load = os.popen('powershell -NoProfile -c "(Get-CimInstance Win32_Processor).LoadPercentage"').read().strip()
        print(f"Carico CPU all'avvio: {load} %")
    except Exception:
        pass
    print("modello | 1 thread: 1 s / 3 s / 8 s | 4 thread: 1 s / 3 s / 8 s | memoria MiB (1 t)")
    out = {}
    for n in names:
        r = latency(n, items)
        out[n] = r
        print(f"{n} | {r['1t_1s']:.0f} / {r['1t_3s']:.0f} / {r['1t_8s']:.0f} ms | "
              f"{r['4t_1s']:.0f} / {r['4t_3s']:.0f} / {r['4t_8s']:.0f} ms | {r['mem_1t_MiB']:.0f}")
    RISULTATI.mkdir(parents=True, exist_ok=True)
    (RISULTATI / "latenza.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "misura"
    if cmd == "prepara":
        cmd_prepara()
    elif cmd == "piper":
        cmd_piper()
    elif cmd == "fbank":
        cmd_fbank()
    elif cmd == "latenza":
        cmd_latenza(sys.argv[2:])
    else:
        cmd_misura(sys.argv[2:] if cmd == "misura" else sys.argv[1:])
