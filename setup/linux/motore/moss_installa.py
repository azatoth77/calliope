# Installa MOSS-TTSD dentro un container usa e getta (04/11/2026, issue #387): lo lancia `moss.sh installa`. Nell'immagine di
# vLLM ci sono python3, uv e hf, non git: il codice viene dall'archivio di GitHub a quel commit. Tutto a versione fissata;
# la prova che è quello giusto è `moss.sha256`, controllato dopo da `moss.sh`, fuori da qui.
#
#   /pv        la cartella di MOSS, scrivibile solo durante l'installazione
#   --senza-pesi   solo codice e ambiente (per riprovare l'installazione senza 24 GB)
import io
import os
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

CODICE = "46973e425da227bfa3b315dcd7a4aba8b6be5574"
PESI = "c7cd852d87aff71cab5bd2b9b05509cedc0ef1ba"
TOKENIZER = "3cd226ba2947efa357ef453bcad111b6eafba782"
# `--no-deps`: torch e il resto sono quelli dell'immagine, a sua volta fissata. Il freeze del banco del 04/11
VERSIONI = ["audioread==3.1.0", "decorator==5.3.1", "einops==0.8.2", "joblib==1.6.0", "lazy-loader==0.6", "librosa==0.11.0",
            "llvmlite==0.50.0", "msgpack==1.2.4", "narwhals==2.28.0", "numba==0.68.1", "orjson==3.13.0", "platformdirs==4.14.4", "pooch==1.9.0",
            "pybase64==1.5.1", "scikit-learn==1.9.1", "scipy==1.18.1", "soundfile==0.14.0", "soxr==1.1.0",
            "threadpoolctl==3.7.0", "tiktoken==0.12.0", "tokenizers==0.22.2", "transformers==5.0.0"]
PV = Path("/pv")
AMB = {**os.environ, "HF_HOME": "/tmp/hf", "TMPDIR": "/tmp", "HF_HUB_DISABLE_XET": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
       "UV_CACHE_DIR": "/tmp/uv", "HOME": "/tmp"}


def fai(*argv):
    print("+", " ".join(argv[:4]), "…", flush=True)
    subprocess.run(argv, env=AMB, check=True)


def codice():
    """Solo ciò che si esegue e la licenza, per nome esatto: i campioni di voce del progetto non vengono nemmeno scaricati."""
    dati = urllib.request.urlopen(f"https://codeload.github.com/OpenMOSS/MOSS-TTSD/tar.gz/{CODICE}", timeout=300).read()
    dest = PV / "src" / "MOSS-TTSD"
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(dati)) as t:
        for nome in ("generation_utils.py", "LICENSE"):
            (dest / nome).write_bytes(t.extractfile(f"MOSS-TTSD-{CODICE}/{nome}").read())


def ambiente():
    fai("uv", "venv", "-q", "--system-site-packages", "--python", "/usr/bin/python3", "/pv/venv/moss")
    fai("uv", "pip", "install", "-q", "--python", "/pv/venv/moss/bin/python", "--only-binary", ":all:", "--no-deps", *VERSIONI)


def pesi():
    for repo, rev, d in (("OpenMOSS-Team/MOSS-TTSD-v1.0", PESI, "moss-ttsd"), ("OpenMOSS-Team/MOSS-Audio-Tokenizer", TOKENIZER, "moss-tokenizer")):
        fai("hf", "download", repo, "--revision", rev, "--local-dir", f"/pv/pesi/{d}", "--max-workers", "2")


if __name__ == "__main__":
    codice()
    ambiente()
    if "--senza-pesi" not in sys.argv:
        pesi()
    print("FATTO", flush=True)
