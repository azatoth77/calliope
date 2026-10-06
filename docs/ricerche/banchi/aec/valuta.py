r"""Valuta le uscite degli AEC: falsi barge-in del VAD, voce dell'utente che sopravvive.

Va lanciato con il .venv PRINCIPALE (silero-vad e faster-whisper sono lì):
    .\.venv\Scripts\python.exe docs\ricerche\banchi\aec\valuta.py [--senza-whisper]

Legge aec/dati/sim/<condizione>/ (da simula.py) e aec/dati/reale/out/ (da reale_aec.py).
Il VAD è Silero con le stesse regole di Listener (soglia 0,5, fine a 0,35 dopo 700 ms,
minimo 250 ms di parlato). Whisper è large-v3-turbo con i parametri di Transcriber.
Scrive aec/dati/valutazione.json e stampa le tabelle del rapporto.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[4]   # radice del repository (docs/ricerche/banchi/aec)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "prove"))
DATI = ROOT / "docs" / "ricerche" / "banchi" / "aec" / "dati"
SR = 16000
FRAME = 512


class Vad:
    def __init__(self):
        import torch
        from silero_vad import load_silero_vad
        from calliope.config import Config
        self.torch, self.model, self.cfg = torch, load_silero_vad(), Config()

    def frasi(self, x: np.ndarray, min_ms=None) -> list[tuple[float, float]]:
        """Frasi che Listener restituirebbe (inizio, fine in secondi dal primo campione)."""
        cfg = self.cfg
        min_ms = cfg.min_speech_ms if min_ms is None else min_ms
        fms = FRAME / SR * 1000
        self.model.reset_states()
        out, talking, n, silent, start = [], False, 0, 0, 0
        for i in range(len(x) // FRAME):
            p = self.model(self.torch.from_numpy(np.ascontiguousarray(
                x[i * FRAME:(i + 1) * FRAME], np.float32)), SR).item()
            if not talking:
                if p >= cfg.vad_threshold:
                    talking, n, silent, start = True, 1, 0, i
                continue
            n += 1
            silent = silent + 1 if p < cfg.vad_threshold - 0.15 else 0
            if silent * fms >= cfg.silence_ms:
                if (n - silent) * fms >= min_ms:
                    out.append((start * fms / 1000, (i - silent) * fms / 1000))
                talking = False
        if talking and (n - silent) * fms >= min_ms:
            out.append((start * fms / 1000, len(x) / SR))
        return out


class Stt:
    def __init__(self):
        from calliope.stt import _add_cuda_dlls
        from calliope.config import Config
        from faster_whisper import WhisperModel
        from prova_whisper import norm, wer_counts
        _add_cuda_dlls()
        self.cfg = Config()
        self.norm, self.wer_counts = norm, wer_counts
        self.model = WhisperModel(self.cfg.whisper_model, device="cuda",
                                  compute_type=self.cfg.whisper_compute_type)

    def testo(self, x):
        seg, _ = self.model.transcribe(x, language=self.cfg.language,
                                       beam_size=self.cfg.whisper_beam_size,
                                       hotwords=self.cfg.whisper_hotwords,
                                       initial_prompt=f"Conversazione con {self.cfg.name}.",
                                       condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in seg).strip()

    def errori(self, ref, hyp):
        r = self.norm(ref)
        return self.wer_counts(r, self.norm(hyp)), len(r)


def cut(x, a, b):
    return x[max(0, int(a * SR)):int(b * SR)]


def valuta_condizione(cond, vad, stt):
    d = DATI / "sim" / cond
    segs = json.load(open(d / "segmenti.json", encoding="utf-8"))["segmenti"]
    res = []
    pulito = {}
    if stt:
        for s in segs:
            if s["tipo"] == "utente" and s["file"] not in pulito:
                x, _ = sf.read(ROOT / "registrazioni" / f"{s['file']}.wav", dtype="float32")
                pulito[s["file"]] = stt.errori(s["testo"], stt.testo(x))
    for f in sorted(d.glob("*.wav")):
        if f.stem in ("mic", "rif"):
            continue
        out, _ = sf.read(f, dtype="float32")
        r = {"condizione": cond, "motore": f.stem, "eco_min": 0.0, "falsi": 0, "falsi_500": 0,
             "doppi": 0, "rilevati": 0, "anticipati": 0, "latenze": [],
             "err_doppio": 0, "err_utente": 0, "parole": 0, "utente_rilevati": 0, "utenti": 0,
             "esempi": []}
        for s in segs:
            if s["tipo"] == "eco":
                x = cut(out, s["inizio"], s["fine"])
                r["eco_min"] += len(x) / SR / 60
                r["falsi"] += len(vad.frasi(x))
                r["falsi_500"] += len(vad.frasi(x, min_ms=500))
            elif s["tipo"] == "doppio":
                x = cut(out, s["inizio"], s["fine"] + 0.8)
                fr = vad.frasi(x)
                u0 = s["u_inizio"] - s["inizio"]
                r["doppi"] += 1
                if fr and fr[0][0] < u0 - 0.1:
                    r["anticipati"] += 1           # il VAD scatta sull'eco prima dell'utente
                ok = [a for a, b in fr if u0 - 0.1 <= a <= s["u_fine"] - s["inizio"]
                      or (a < u0 - 0.1 and b > u0 + 0.3)]
                if ok:
                    r["rilevati"] += 1
                    r["latenze"].append(max(0.0, ok[0] - u0))
                if stt:
                    h = stt.testo(cut(out, s["u_inizio"] - 0.3, s["u_fine"] + 0.5))
                    e, n = stt.errori(s["testo"], h)
                    r["err_doppio"] += e
                    r["parole"] += n
                    if len(r["esempi"]) < 6:
                        r["esempi"].append((s["testo"], h))
            else:
                x = cut(out, s["inizio"] - 0.3, s["fine"] + 0.8)
                r["utenti"] += 1
                r["utente_rilevati"] += bool(vad.frasi(x))
                if stt:
                    e, _ = stt.errori(s["testo"], stt.testo(x))
                    r["err_utente"] += e
        r["falsi_min"] = r["falsi"] / r["eco_min"]
        r["falsi_500_min"] = r["falsi_500"] / r["eco_min"]
        r["latenza_mediana_s"] = float(np.median(r["latenze"])) if r["latenze"] else None
        if stt:
            r["wer_doppio"] = r["err_doppio"] / r["parole"]
            r["wer_utente"] = r["err_utente"] / r["parole"]
            r["wer_pulito"] = sum(e for e, _ in pulito.values()) / sum(n for _, n in pulito.values())
        del r["latenze"]
        res.append(r)
        print(f"{cond:10s} {f.stem:15s} falsi/min {r['falsi_min']:5.1f} (≥500ms {r['falsi_500_min']:4.1f})"
              f" | doppio rilevati {r['rilevati']}/{r['doppi']} anticipati {r['anticipati']}"
              f" lat {r['latenza_mediana_s']}"
              + (f" | WER doppio {r['wer_doppio']:.1%} utente {r['wer_utente']:.1%}"
                 f" pulito {r['wer_pulito']:.1%}" if stt else ""), flush=True)
    return res


def valuta_reale(vad):
    res = []
    for f in sorted((DATI / "reale").glob("eco_*.wav")):
        x, _ = sf.read(f, dtype="float32")
        res.append({"file": f.name, "motore": "nessuna", "frasi_vad": len(vad.frasi(x))})
    for f in sorted((DATI / "reale" / "out").glob("*.wav")):
        x, _ = sf.read(f, dtype="float32")
        res.append({"file": f.name, "frasi_vad": len(vad.frasi(x)),
                    "frasi_vad_500": len(vad.frasi(x, min_ms=500))})
    for r in res:
        print(r)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--senza-whisper", action="store_true")
    ap.add_argument("--condizioni", default="")
    a = ap.parse_args()
    vad = Vad()
    stt = None if a.senza_whisper else Stt()
    conds = a.condizioni.split(",") if a.condizioni else \
        sorted(p.name for p in (DATI / "sim").iterdir() if p.is_dir())
    path = DATI / "valutazione.json"
    old = json.load(open(path, encoding="utf-8")) if path.exists() else {"sim": []}
    out = {"reale": valuta_reale(vad),
           "sim": [r for r in old["sim"] if r["condizione"] not in conds]}
    for c in conds:
        out["sim"] += valuta_condizione(c, vad, stt)
        json.dump(out, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    main()
