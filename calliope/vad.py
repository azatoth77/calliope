"""
Silero VAD con due motori: PyTorch (il pacchetto silero-vad, come dal 21/09) oppure
onnxruntime con un involucro in numpy (02/10/2026, impacchettamento per la DGX Linux).

Perché: il pacchetto silero-vad dichiara torch e torchaudio come dipendenze obbligatorie, e
anche il suo `OnnxWrapper` usa i tensori di torch. Su Linux aarch64 il wheel di torch su
PyPI (2.14.1, 30/09/2026) è quello con CUDA 13: 454 MB più cuda-toolkit e cuDNN, qualche GB
solo per decidere se in 32 ms c'è voce. Il modello ONNX è già dentro il pacchetto
(`silero_vad/data/silero_vad.onnx`) e onnxruntime c'è già (wake word, CAM++, Piper): qui lo
si carica senza importare silero_vad, quindi senza torch.

Interfaccia comune: `prob(frame) -> float` (512 campioni a 16 kHz, float32) e
`reset_states()`. Lo stato è quello del modello ufficiale: `state` (2, 1, 128) e i 64
campioni di contesto della finestra precedente messi davanti a ogni finestra.

Motore (`Config.vad_motore`): «auto» usa torch se c'è (Windows resta com'era) e onnxruntime
altrimenti; «torch» e «onnx» lo forzano. Equivalenza misurata il 02/10 sulle registrazioni
vere: vedi `prove/prova_linux.py` e il rapporto
docs/ricerche/2026-10-02-impacchettamento-dgx-linux.md.
"""

import importlib.util
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
CONTESTO = 64            # campioni della finestra precedente (16 kHz), come utils_vad.py


def modello_onnx(percorso: str | None = None) -> Path | None:
    """Il file ONNX: quello indicato, altrimenti quello del pacchetto silero-vad, trovato
    **senza importarlo** (il suo __init__ importa torch). None se non c'è."""
    if percorso:
        p = Path(percorso)
        return p if p.is_file() else None
    try:
        spec = importlib.util.find_spec("silero_vad")
    except (ImportError, ValueError):
        spec = None
    for base in (spec.submodule_search_locations or []) if spec else []:
        p = Path(base) / "data" / "silero_vad.onnx"
        if p.is_file():
            return p
    return None


class SileroOnnx:
    """Silero VAD v5/v6 con onnxruntime e numpy, senza torch."""

    motore = "onnx"

    def __init__(self, percorso: str | Path):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        # Come OnnxWrapper: un thread, la finestra è minuscola (0,1–0,3 ms) e la CPU serve
        # a Whisper, alla wake word e a Piper
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.session = ort.InferenceSession(str(percorso), sess_options=opts,
                                            providers=["CPUExecutionProvider"])
        self._sr = np.array(SAMPLE_RATE, dtype=np.int64)
        self.reset_states()

    def reset_states(self):
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, CONTESTO), dtype=np.float32)

    def prob(self, frame: np.ndarray) -> float:
        x = np.asarray(frame, dtype=np.float32).reshape(1, -1)
        x = np.concatenate([self._context, x], axis=1)
        out, self._state = self.session.run(None, {"input": x, "state": self._state,
                                                   "sr": self._sr})
        self._context = x[:, -CONTESTO:]
        return float(out.reshape(-1)[0])


class SileroTorch:
    """Il modello del pacchetto silero-vad (JIT, PyTorch): il motore di sempre."""

    motore = "torch"

    def __init__(self):
        import torch
        from silero_vad import load_silero_vad
        self.torch = torch
        self.model = load_silero_vad()

    def reset_states(self):
        self.model.reset_states()

    def prob(self, frame: np.ndarray) -> float:
        return self.model(self.torch.from_numpy(frame), SAMPLE_RATE).item()


def carica_vad(motore: str = "auto", percorso: str | None = None):
    """Il VAD con il motore chiesto. «auto»: torch se si importa, altrimenti onnxruntime.
    Solleva RuntimeError con un messaggio chiaro se nessuno dei due è disponibile."""
    motore = (motore or "auto").lower()
    if motore not in ("auto", "torch", "onnx"):
        raise ValueError(f"vad_motore sconosciuto: {motore!r} (auto | torch | onnx)")
    if motore in ("auto", "torch"):
        try:
            return SileroTorch()
        except ImportError:
            if motore == "torch":
                raise
    path = modello_onnx(percorso)
    if path is None:
        raise RuntimeError("manca il modello di Silero VAD: va installato il pacchetto "
                           "silero-vad (basta senza torch) oppure indicato vad_modello")
    return SileroOnnx(path)
