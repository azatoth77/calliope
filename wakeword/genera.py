"""
Genera i campioni sintetici per addestrare la wake word «Calliope».

Positivi: «Calliope» (pronuncia ca-LLÌ-o-pe) detto da
  - le 10 voci Piper italiane in voices/ (accento giusto, pochi parlanti), variando
    length_scale / noise_scale / noise_w e alcune varianti fonetiche;
  - il modello Piper inglese multi-parlante LibriTTS-R (904 parlanti) pilotato con i
    FONEMI italiani (niente accento inglese nel testo, ma timbri molto più vari).
Negativi sintetici:
  - parole e frasi italiane simili al nome (cavallo, calle, Carlo, Cagliari, Penelope…);
  - frasi italiane generiche (trascrizioni di Multilingual LibriSpeech, senza il nome),
    dette dalle stesse voci: così il modello impara la parola, non il timbro di Piper.

Uscita: wakeword/dati/tts/{pos,neg_simili,neg_frasi}.pkl — liste di array int16 a 16 kHz.

    .\\wakeword\\.venv\\Scripts\\python.exe wakeword\\genera.py
"""
from __future__ import annotations

import glob
import os
import pickle
import random
import sys
import time
import zlib

import numpy as np
from scipy.signal import resample_poly

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "dati", "tts")
SR = 16000

# Varianti fonetiche del nome (espeak dà kallˈiʲope). Tutte con l'accento sulla «ì».
NAME_PHONEMES = ["kallˈiʲope", "kallˈiope", "kalˈiope", "kallˈiːope", "kallˈiʲɔpe",
                 "kalˈliʲope"]
NAME_TEXTS = ["Calliope.", "Calliope!", "Calliope?", "Calliope,", "Callìope."]
# Prefissi e seguiti: il nome si dice da solo o in testa a una richiesta
PREFIXES = ["", "", "", "ehi ", "senti ", "ok ", "ciao ", "allora ", "scusa "]
SUFFIXES = ["", "", "", " che ore sono?", " accendi la luce.", " esci.",
            " dimmi una cosa.", " quanto manca?", " metti la musica."]

SIMILAR = """cavallo calle callo calcio cappello Carlo collina Calimero Callisto calligrafia
calligrafo Cagliari Gallipoli Galileo Penelope Antiope Etiopia miope Europa Olimpo calla
calli colla cavalli cavolo capitolo caleidoscopio Carola carioca cariola Camilla Calabria
callista Callipo Callas Cariddi calipso caviale calamaio calendario allora gallo galoppo
Calì caliamo calpestio carrozza Carlotta collirio colloquio calzino cannella capolinea
Canopo Ninive Olimpia Ettore Achille Clio Talia Euterpe Tersicore Erato Polimnia Urania
Melpomene""".split()
SIMILAR_PHRASES = [
    "Il cavallo corre sulla collina.", "Carlo ha perso il cappello.", "Calle e callo.",
    "Ho un callo al piede.", "Guardiamo la partita di calcio.", "Vado a Cagliari domani.",
    "Aglio, olio e peperoncino.", "Cala il pepe nella pentola.", "Ciao Pepe, come stai?",
    "Carlo e Pietro sono usciti.", "Chi lo sa, forse domani.", "Alla pace e all'olio.",
    "Qualche pera e qualche mela.", "Gallo, pepe e sale.", "A lui piace il pepe.",
    "Calli, olio e pane.", "La calligrafia di Carlo è bella.", "Callisto è una luna.",
    "Penelope aspetta Ulisse.", "Sono un po' miope.", "Andiamo in Europa.",
    "Le muse erano nove: Clio, Euterpe, Talia, Melpomene, Tersicore, Erato, Polimnia e Urania.",
    "Colli, olio e pepe nero.", "Ca' lì, oltre il ponte.", "Quale opera vuoi sentire?",
    "Cavalli e poi pecore.", "Callo, pepe e basta.", "Ha preso il caviale.",
    "Il calendario è sul tavolo.", "Allora, ci vediamo dopo?", "Camilla è partita.",
]
# Pezzi del nome: non devono svegliarla da soli
PARTIALS = ["[[kallˈi]]", "[[kalˈiʲo]]", "[[ʲˈope]]", "[[lˈiʲope]]", "[[kˈalli]]"]

# Un'altra parola (04/10, parole.py): WW_PAROLA=computer. Si legge all'import, così vale
# anche nei processi di lavoro (multiprocessing «spawn» reimporta il modulo)
PAROLA = os.environ.get("WW_PAROLA", "").strip().lower()
if PAROLA == "calliope":
    PAROLA = ""
if PAROLA:
    sys.path.insert(0, HERE)
    from parole import PAROLE
    _p = PAROLE[PAROLA]
    NAME_PHONEMES, NAME_TEXTS = _p["fonemi"], _p["testi"]
    SIMILAR, SIMILAR_PHRASES, PARTIALS = _p["simili"], _p["frasi"], _p["pezzi"]
    OUT = os.path.join(HERE, "dati", f"tts-{PAROLA}")


def load_voice(path):
    from piper import PiperVoice
    return PiperVoice.load(path)


def synth_ids(voice, phonemes: list[str], length_scale, noise_scale, noise_w, speaker=None):
    from piper import SynthesisConfig
    ids = voice.phonemes_to_ids(phonemes)
    cfg = SynthesisConfig(speaker_id=speaker, length_scale=length_scale,
                          noise_scale=noise_scale, noise_w_scale=noise_w)
    audio = voice.phoneme_ids_to_audio(ids, cfg)
    if isinstance(audio, tuple):
        audio = audio[0]
    return np.asarray(audio, np.float32)


def to16k(audio: np.ndarray, sr: int, speed: float = 1.0) -> np.ndarray:
    """Ricampiona a 16 kHz; speed ≠ 1 cambia anche l'altezza (come un nastro)."""
    target = int(round(SR / speed))
    g = np.gcd(target, sr)
    return resample_poly(audio, target // g, sr // g).astype(np.float32)


def trim(a: np.ndarray, thr=0.01) -> np.ndarray:
    idx = np.where(np.abs(a) > thr * max(1e-6, np.abs(a).max()))[0]
    return a[max(0, idx[0] - 160): idx[-1] + 160] if len(idx) else a


def to_int16(a: np.ndarray) -> np.ndarray:
    a = a / max(1e-6, np.abs(a).max()) * 0.9
    return (a * 32767).astype(np.int16)


def phonemize_it(voice_it, text: str) -> list[str]:
    ph = []
    for s in voice_it.phonemize(text):
        ph.extend(s + [" "])
    return ph[:-1]


def rand_params(rng):
    ls = rng.uniform(0.85, 1.35)     # sotto 0,85 il nome dura meno di 0,4 s: irrealistico
    ns = rng.uniform(0.3, 1.0)
    nw = rng.uniform(0.3, 1.1)
    return ls, ns, nw


_V = {}   # voci caricate nel processo di lavoro


def _init_worker():
    # Una sessione ONNX con tutti i core per ogni processo satura la CPU: 2 thread a testa
    import onnxruntime as ort
    orig = ort.InferenceSession

    def session(path_or_bytes, sess_options=None, *a, **kw):
        so = sess_options or ort.SessionOptions()
        so.intra_op_num_threads = 2
        so.inter_op_num_threads = 1
        return orig(path_or_bytes, so, *a, **kw)
    ort.InferenceSession = session
    _V["it"] = [load_voice(p) for p in sorted(glob.glob(os.path.join(ROOT, "voices", "*.onnx")))]
    _V["en"] = load_voice(os.path.join(HERE, "modelli", "en_US-libritts_r-medium.onnx"))


def _work(job):
    kind, seed, count, extra = job
    rng = random.Random(seed)
    it_voices, en = _V["it"], _V["en"]
    n_spk, ref_it = en.config.num_speakers, it_voices[0]

    def say(text, v, spk):
        """Sintetizza `text` (testo italiano, può contenere [[fonemi]])."""
        ph = phonemize_it(ref_it, text)        # fonemi italiani anche per la voce inglese
        a = synth_ids(v, ph, *rand_params(rng), spk)
        return to_int16(trim(to16k(a, v.config.sample_rate, rng.uniform(0.92, 1.08))))

    def any_voice():
        if rng.random() < 0.5:
            return rng.choice(it_voices), None
        return en, rng.randrange(n_spk)

    out = []
    for _ in range(count):
        if kind in ("pos_it", "pos_en"):
            v, spk = (rng.choice(it_voices), None) if kind == "pos_it" else (en, rng.randrange(n_spk))
            name_txt = (f"[[{rng.choice(NAME_PHONEMES)}]]" if rng.random() < 0.5
                        else rng.choice(NAME_TEXTS))
            # il nome si sintetizza da solo: così si sa dove finisce (serve per allineare)
            clip = say(name_txt, v, spk)
            if rng.random() < 0.3:
                pre = say(rng.choice(PREFIXES[3:]), v, spk)
                clip = np.concatenate([pre, np.zeros(rng.randint(0, 1600), np.int16), clip])
            end = len(clip)
            if rng.random() < 0.3:
                gap = np.zeros(rng.randint(0, 2400), np.int16)
                clip = np.concatenate([clip, gap, say(rng.choice(SUFFIXES[3:]), v, spk)])
            out.append((clip, end))                  # (audio, campione di fine nome)
        elif kind == "sim":
            v, spk = any_voice()
            items = SIMILAR + SIMILAR_PHRASES + PARTIALS
            t = rng.choice(items)
            if rng.random() < 0.3 and t in SIMILAR:
                t = f"{t} {rng.choice(SIMILAR)}"
            out.append(say(t, v, spk))
        else:  # frasi generiche
            v, spk = any_voice()
            words = rng.choice(extra).split()
            k = rng.randint(3, min(12, len(words)))  # pezzi brevi: 1–4 secondi
            st = rng.randint(0, len(words) - k)
            out.append(say(" ".join(words[st:st + k]), v, spk))
    return kind, out


def main(n_pos_it=8000, n_pos_en=8000, n_sim=6000, n_phr=6000, procs=12):
    from multiprocessing import Pool
    os.makedirs(OUT, exist_ok=True)
    lines = []
    for p in glob.glob(os.path.join(HERE, "dati", "mls", "*", "transcripts.txt")):
        if os.sep + "test" + os.sep in p:
            continue                      # il test di MLS resta fuori dall'addestramento
        with open(p, encoding="utf-8") as f:
            for line in f:
                txt = line.split("\t", 1)[-1].strip()
                if ("callio" not in txt.lower() and (not PAROLA or PAROLA not in txt.lower())
                        and 20 < len(txt) < 200):
                    lines.append(txt)
    random.Random(0).shuffle(lines)
    lines = lines[:20000]
    step = 250
    jobs = []
    for kind, n in (("pos_it", n_pos_it), ("pos_en", n_pos_en), ("sim", n_sim), ("phr", n_phr)):
        for k in range(0, n, step):
            jobs.append((kind, zlib.crc32(f"{kind}{k}".encode()), min(step, n - k),
                         lines if kind == "phr" else None))
    res = {"pos_it": [], "pos_en": [], "sim": [], "phr": []}
    t0 = time.time()
    with Pool(procs, initializer=_init_worker) as pool:
        for kind, out in pool.imap_unordered(_work, jobs):
            res[kind].extend(out)
            print(f"  {kind}: {len(res[kind])} ({time.time() - t0:.0f} s)", flush=True)
    for name, data in (("pos", res["pos_it"] + res["pos_en"]), ("neg_simili", res["sim"]),
                       ("neg_frasi", res["phr"])):
        with open(os.path.join(OUT, name + ".pkl"), "wb") as f:
            pickle.dump(data, f)
    print(f"fatto in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main(*[int(x) for x in sys.argv[1:]])
