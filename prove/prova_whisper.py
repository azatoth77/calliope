import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Taratura di Whisper sulle registrazioni dei test vocali (docs/test-vocale.md).

Uso:
  prova_whisper.py --controllo            trascrive tutto con beam_size=5 (per i riferimenti)
  prova_whisper.py [nome_config ...]      misura le configurazioni sui riferimenti
                                          (prove/riferimenti_whisper.tsv); senza nomi, tutte
  prova_whisper.py --server URL           le stesse misure con un server di trascrizione
                                          (stt_motore: server, es. whisper.cpp sulla DGX
                                          via tunnel: http://127.0.0.1:<porta>/v1), con la
                                          richiesta vera di ServerTranscriber (02/10: dal
                                          satellite «che ore sono» diventava «che sono»)
      [--prompt TESTO | --senza-prompt] [--beam N] [--campo nome=valore]
                                          varianti per richiesta (whisper-server)

Non modifica nulla: legge le registrazioni e stampa i risultati (anche in
prove/risultati_whisper.tsv). Rapporto: docs/ricerche/2026-09-24-taratura-whisper.md.
"""

import csv
import glob
import re
import time
import wave
from pathlib import Path

import numpy as np

from calliope.stt import _add_cuda_dlls

from calliope.wakeword import find_wake_word
from calliope.config import HALLUCINATIONS

ROOT = Path(__file__).resolve().parent.parent
REC = ROOT / "registrazioni"
REFS = ROOT / "prove" / "riferimenti_whisper.tsv"
OUT = ROOT / "prove" / "risultati_whisper.tsv"
FOLDERS = ["2026-09-21-webcam", "2026-09-21-webcam-mic-sempre-aperto",
           "2026-09-21-webcam-mic-sempre-aperto-2", "2026-09-21-webcam-mic-sempre-aperto-3",
           "2026-09-24-v03", "2026-09-24-v03b"]

BASE_PROMPT = "Conversazione con Calliope."
# Parole frequenti nei comandi, senza frasi intere del copione
RICH_PROMPT = ("Conversazione con Calliope, un'assistente vocale. Comandi: Calliope, esci; "
               "cambia voce, Paola, Serena; che ore sono; numero preferito.")

# Solo il vocabolario dei comandi veri di Calliope (nome, uscita, voci): niente frasi
# del copione, così il guadagno non è gonfiato dal test
CMD_PROMPT = ("Conversazione con Calliope, un'assistente vocale. "
              "Parole frequenti: Calliope, esci, voce, Paola, Serena.")
# Solo contesto, nessuna parola del copione oltre al nome
CTX_PROMPT = "Conversazione in italiano con Calliope, un'assistente vocale di casa."

BASE = dict(model="large-v3-turbo", compute_type="int8_float16", beam_size=1,
            initial_prompt=BASE_PROMPT, condition_on_previous_text=False)

# Un fattore alla volta rispetto alla baseline, poi le combinazioni
CONFIGS = {
    "baseline":        {},
    "beam5":           dict(beam_size=5),
    "float16":         dict(compute_type="float16"),
    "prompt_ricco":    dict(initial_prompt=RICH_PROMPT),
    "senza_prompt":    dict(initial_prompt=None),
    "hotwords":        dict(hotwords="Calliope"),
    "temp0":           dict(temperature=0.0),
    "vad":             dict(vad_filter=True),
    "no_timestamps":   dict(without_timestamps=True),
    "prompt_comandi":  dict(initial_prompt=CMD_PROMPT),
    "prompt_contesto": dict(initial_prompt=CTX_PROMPT),
    "beam5_comandi":   dict(beam_size=5, initial_prompt=CMD_PROMPT),
    "beam5_contesto":  dict(beam_size=5, initial_prompt=CTX_PROMPT),
    "beam5_comandi_hot": dict(beam_size=5, initial_prompt=CMD_PROMPT, hotwords="Calliope"),
    "beam5_comandi_temp0": dict(beam_size=5, initial_prompt=CMD_PROMPT, temperature=0.0),
    # Solo parole, senza «assistente vocale» che veniva ricopiato nella trascrizione
    "beam5_hot_parole": dict(beam_size=5, hotwords="Calliope",
                             initial_prompt="Conversazione con Calliope. Esci, voce, Paola, Serena."),
    "large-v3_comandi": dict(model="large-v3", beam_size=5, initial_prompt=CMD_PROMPT),
    "beam5_prompt":    dict(beam_size=5, initial_prompt=RICH_PROMPT),
    "beam5_hotwords":  dict(beam_size=5, hotwords="Calliope"),
    "beam5_notime":    dict(beam_size=5, without_timestamps=True),
    "beam5_prompt_notime": dict(beam_size=5, initial_prompt=RICH_PROMPT, without_timestamps=True),
    "large-v3":        dict(model="large-v3"),
    "large-v3_beam5":  dict(model="large-v3", beam_size=5),
}

_NUM = {"47": "quarantasette", "384400": "trecentottantaquattromilaquattrocento"}


def load_wav(path) -> np.ndarray:
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


def norm(text: str) -> list[str]:
    t = text.lower().replace("’", "'")
    t = re.sub(r"[^\w'àèéìòù ]", " ", t)
    t = t.replace("'", " ")
    words = []
    for w in t.split():
        words.append(_NUM.get(w, w))
    return words


def wer_counts(ref: list[str], hyp: list[str]) -> int:
    """Distanza di Levenshtein sulle parole."""
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
            prev, d[j] = d[j], cur
    return d[len(hyp)]


def all_wavs():
    for folder in FOLDERS:
        for p in sorted((REC / folder).glob("*.wav")):
            yield folder, p


def old_transcripts():
    old = {}
    for folder in FOLDERS:
        with open(REC / folder / "trascrizioni.tsv", encoding="utf-8") as f:
            for row in csv.reader(f, delimiter="\t"):
                if row:
                    old[(folder, row[0])] = row[2] if len(row) > 2 else ""
    return old


_models = {}


def get_model(name, compute_type):
    from faster_whisper import WhisperModel
    key = (name, compute_type)
    if key not in _models:
        _models.clear()                       # uno alla volta in VRAM
        import gc; gc.collect()
        _models[key] = WhisperModel(name, device="cuda", compute_type=compute_type)
    return _models[key]


def transcribe(model, audio, opts) -> str:
    kw = dict(language="it", beam_size=opts["beam_size"],
              initial_prompt=opts["initial_prompt"],
              condition_on_previous_text=opts["condition_on_previous_text"])
    for k in ("hotwords", "temperature", "vad_filter", "without_timestamps"):
        if k in opts:
            kw[k] = opts[k]
    segments, _ = model.transcribe(audio, **kw)
    return " ".join(s.text.strip() for s in segments).strip()


def controllo():
    old = old_transcripts()
    model = get_model("large-v3-turbo", "int8_float16")
    opts = dict(BASE, beam_size=5)
    for folder, p in all_wavs():
        text = transcribe(model, load_wav(p), opts)
        print(f"{folder}\t{p.stem}\t{old.get((folder, p.stem), '')}\t{text}", flush=True)


def load_refs():
    refs = []
    with open(REFS, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            refs.append(row)
    return refs


def measure(name, refs, trascrivi=None):
    """Misura una configurazione; con `trascrivi(audio) -> testo` (il server) al posto del
    modello locale."""
    if trascrivi is None:
        opts = dict(BASE, **CONFIGS[name])
        model = get_model(opts["model"], opts["compute_type"])
        transcribe(model, np.zeros(16000, np.float32), opts)          # warm-up

        def trascrivi(audio):
            return transcribe(model, audio, opts)
    errs = words = exact = 0
    wake_ok = wake_tot = wake_false = halluc = 0
    times = []
    by_when = {}
    rows = []
    for r in refs:
        audio = load_wav(REC / r["cartella"] / f"{r['stem']}.wav")
        t0 = time.perf_counter()
        hyp = trascrivi(audio)
        times.append(time.perf_counter() - t0)
        ref_w, hyp_w = norm(r["riferimento"]), norm(hyp)
        e = wer_counts(ref_w, hyp_w)
        errs += e
        words += len(ref_w)
        exact += e == 0
        w = by_when.setdefault(r["quando"], [0, 0, 0, 0])
        w[0] += e; w[1] += len(ref_w); w[2] += e == 0; w[3] += 1
        if hyp.lower().strip(" .!?…") in HALLUCINATIONS:
            halluc += 1
        has_name = r["riferimento"].lower().startswith("calliope")
        found = find_wake_word(hyp, "Calliope", 0.65) is not None
        if has_name:
            wake_tot += 1
            wake_ok += found
        elif found:
            wake_false += 1
        rows.append((name, r["cartella"], r["stem"], r["riferimento"], hyp, e))
    t = np.array(times)
    res = dict(config=name, wer=errs / max(words, 1), esatte=exact, frasi=len(refs),
               wake=f"{wake_ok}/{wake_tot}", wake_falsi=wake_false, allucinazioni=halluc,
               t_medio=t.mean(), t_p95=np.percentile(t, 95))
    for k, (e, n, ex, c) in sorted(by_when.items()):
        res[f"wer_{k}"] = e / max(n, 1)
        res[f"esatte_{k}"] = f"{ex}/{c}"
    return res, rows


def main():
    if "--server" in sys.argv:
        from calliope.config import Config
        from calliope.stt import ServerTranscriber
        cfg = Config()
        cfg.stt_url = sys.argv[sys.argv.index("--server") + 1]
        cfg.stt_timeout_s = 30.0
        srv = ServerTranscriber(cfg)
        if srv.device != "server" or srv.error:
            sys.exit(f"Il server di trascrizione non risponde: {srv.error}")
        refs = [r for r in load_refs() if r["sicurezza"] == "sicura"]
        trascrivi, nome = srv._chiedi, "server"
        # Varianti per richiesta: whisper-server legge i campi del modulo multipart a ogni
        # richiesta, partendo ogni volta dai valori della riga di comando (server.cpp:
        # `whisper_params params = default_params`), quindi non resta niente sul servizio.
        # --prompt TESTO, --senza-prompt (prompt vuoto), --beam N, --campo nome=valore
        # (ripetibile: temperature_inc, suppress_nst, no_speech_thold…)
        extra = {}
        if "--prompt" in sys.argv:
            extra["prompt"] = sys.argv[sys.argv.index("--prompt") + 1]
        if "--senza-prompt" in sys.argv:
            extra["prompt"] = ""
        if "--beam" in sys.argv:
            extra["beam_size"] = sys.argv[sys.argv.index("--beam") + 1]
        for i, a in enumerate(sys.argv):
            if a == "--campo":
                k, _, v = sys.argv[i + 1].partition("=")
                extra[k] = v
        if extra:
            from calliope.stt import wav_bytes

            def trascrivi(audio, extra=extra):
                files = {"file": ("frase.wav", wav_bytes(audio, cfg.sample_rate), "audio/wav")}
                data = {"model": cfg.stt_modello, "language": cfg.language,
                        "prompt": srv.prompt, "temperature": "0",
                        "response_format": "json", **extra}
                r = srv.http.post(srv.url, files=files, data=data)
                r.raise_for_status()
                return str(r.json().get("text") or "").strip()
            nome = "server " + " ".join(f"{k}={v!r}" for k, v in extra.items())
        res, rows = measure(nome, refs, trascrivi=trascrivi)
        for row in rows:
            if row[5]:
                print(f"  {row[3]!r} → {row[4]!r}", flush=True)
        print("RIS	" + "	".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}"
                                    for k, v in res.items()), flush=True)
        return
    _add_cuda_dlls()
    if "--controllo" in sys.argv:
        controllo()
        return
    names = [a for a in sys.argv[1:] if not a.startswith("-")] or list(CONFIGS)
    refs = [r for r in load_refs() if r["sicurezza"] == "sicura"]
    print(f"{len(refs)} registrazioni con riferimento sicuro", flush=True)
    new_file = not OUT.exists()
    with open(OUT, "a", encoding="utf-8", newline="") as f:
        out = csv.writer(f, delimiter="\t")
        if new_file:
            out.writerow(["config", "cartella", "stem", "riferimento", "trascrizione", "errori"])
        for name in names:
            res, rows = measure(name, refs)
            out.writerows(rows)
            f.flush()
            print("RIS\t" + "\t".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}"
                                        for k, v in res.items()), flush=True)


if __name__ == "__main__":
    main()
