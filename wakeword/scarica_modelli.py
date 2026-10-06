"""
Scarica i modelli e i dati piccoli che servono alla wake word.

Per l'INFERENZA bastano i primi due (in wakeword/modelli/):
  melspectrogram.onnx, embedding_model.onnx — openWakeWord v0.5.1, Apache 2.0
Per l'ADDESTRAMENTO servono anche:
  en_US-libritts_r-medium.onnx(.json) — voce Piper multi-parlante (904 parlanti)
  dati/validation_set_features.npy    — ~10,7 h di feature di validazione di openWakeWord
Il resto dei dati si scarica con scarica_mls.py e scarica_acav.py.

    python wakeword\\scarica_modelli.py [--addestramento]
"""
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OWW = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/"
PIPER = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts_r/medium/"
FEAT = "https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/"

FILES = [(OWW + "melspectrogram.onnx", "modelli/melspectrogram.onnx"),
         (OWW + "embedding_model.onnx", "modelli/embedding_model.onnx")]
TRAIN = [(PIPER + "en_US-libritts_r-medium.onnx", "modelli/en_US-libritts_r-medium.onnx"),
         (PIPER + "en_US-libritts_r-medium.onnx.json", "modelli/en_US-libritts_r-medium.onnx.json"),
         (FEAT + "validation_set_features.npy", "dati/validation_set_features.npy")]


def main():
    todo = FILES + (TRAIN if "--addestramento" in sys.argv else [])
    for url, rel in todo:
        dest = os.path.join(HERE, rel)
        if os.path.exists(dest):
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        print("scarico", rel, flush=True)
        urllib.request.urlretrieve(url, dest)


if __name__ == "__main__":
    main()
