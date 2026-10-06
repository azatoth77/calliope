"""Scarica una parte di Multilingual LibriSpeech italiano (CC-BY 4.0) da Hugging Face.

dev + alcuni blocchi di train -> negativi per l'addestramento
test                           -> negativi tenuti da parte (falsi risvegli per ora)
"""
import os, random, tarfile
from huggingface_hub import HfApi, hf_hub_download

REPO = "facebook/multilingual_librispeech"
DEST = os.path.join(os.path.dirname(__file__), "dati", "mls")
TRAIN_BYTES = 1_200_000_000   # ~1,2 GB di train, scelti a caso tra blocchi medi

api = HfApi()
info = api.dataset_info(REPO, files_metadata=True)
files = [s for s in info.siblings if s.rfilename.startswith("data/mls_italian/")]
want = [s.rfilename for s in files if s.rfilename.split("/")[2] in ("dev", "test")
        and s.rfilename.endswith(".tar.gz")]
train = [s for s in files if s.rfilename.split("/")[2] == "train"
         and s.rfilename.endswith(".tar.gz") and 20e6 < (s.size or 0) < 120e6]
random.Random(0).shuffle(train)
tot = 0
for s in train:
    if tot > TRAIN_BYTES:
        break
    want.append(s.rfilename); tot += s.size
want += [f"data/mls_italian/{sp}/transcripts.txt" for sp in ("dev", "test", "train")]
for f in want:
    split = f.split("/")[2]
    out = os.path.join(DEST, split)
    os.makedirs(out, exist_ok=True)
    p = hf_hub_download(REPO, f, repo_type="dataset")
    if f.endswith(".tar.gz"):
        with tarfile.open(p) as t:
            t.extractall(out, filter="data")
    else:
        import shutil; shutil.copy(p, out)
    print("ok", f, flush=True)
