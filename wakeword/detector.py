"""
Compatibilità per gli script di addestramento della wake word (feature.py, valuta.py…).

Il rilevatore vive ora nel package: calliope/wakeword.py (roadmap 2, 26/09/2026). Qui si
re-importa, con i modelli di questa cartella (modelli/) come predefinito, così
`from detector import FeatureExtractor` e `WakeWordDetector()` funzionano come prima.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "modelli")
_ROOT = os.path.dirname(HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from calliope.wakeword import (  # noqa: E402
    CHUNK, MEL_CONTEXT, MEL_STEP, MEL_WINDOW, N_EMB, _session,
    FeatureExtractor as _FeatureExtractor, WakeWordDetector as _WakeWordDetector)

__all__ = ["CHUNK", "MEL_CONTEXT", "MEL_STEP", "MEL_WINDOW", "N_EMB", "MODELS",
           "FeatureExtractor", "WakeWordDetector", "_session"]


class FeatureExtractor(_FeatureExtractor):
    """Come nel package, con i modelli di wakeword/modelli se non si indica altro."""

    def __init__(self, threads: int = 1, models_dir: str = MODELS):
        super().__init__(models_dir, threads)


class WakeWordDetector(_WakeWordDetector):
    """Come nel package, con wakeword/modelli/calliope.onnx se non si indica altro."""

    def __init__(self, model_path: str | None = None, threads: int = 1):
        super().__init__(model_path or os.path.join(MODELS, "calliope.onnx"), threads)
