# Il lavoro di MOSS-TTSD dentro il suo container (04/11/2026, issue #387): un solo caricamento, poi le richieste
# una alla volta, come file. Niente rete, niente capacità, pesi e codice in sola lettura: lo avvia
# calliope/studio/podcast_motore.py. trust_remote_code resta in questo processo. Nel registro solo conti, mai il
# copione: è il materiale di studio di una persona.
#
#   /pv/pesi/moss-ttsd, /pv/pesi/moss-tokenizer, /pv/src/MOSS-TTSD   sola lettura, a versione fissata
#   /lavoro/riferimenti.json, rif-a.wav, rif-b.wav                   le due voci (generate con Piper)
#   /lavoro/richieste/<id>.json {id, testo, seme}  →  /lavoro/uscite/<id>.wav, poi <id>.json con le misure
#   /lavoro/pronto.json {rate, carico_s}, scritto a modello caricato
import json
import os
import resource
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, "/pv/src/MOSS-TTSD")

import numpy as np  # noqa: E402,F401
import soundfile as sf  # noqa: E402
import torch  # noqa: E402
from generation_utils import prepare_sample  # noqa: E402
from transformers import AutoModel, AutoProcessor  # noqa: E402

DEV = "cuda"
L = Path("/lavoro")
MODO = "voice_clone_and_continuation"


def scrivi(p: Path, d: dict) -> None:
    t = p.with_name(p.name + ".tmp")
    t.write_text(json.dumps(d), encoding="utf-8")
    os.replace(t, p)


t0 = time.time()
proc = AutoProcessor.from_pretrained("/pv/pesi/moss-ttsd", trust_remote_code=True, codec_path="/pv/pesi/moss-tokenizer")
proc.audio_tokenizer = proc.audio_tokenizer.to(DEV).eval()
model = AutoModel.from_pretrained("/pv/pesi/moss-ttsd", trust_remote_code=True, attn_implementation="sdpa",
                                  torch_dtype=torch.bfloat16).to(DEV).eval()
carico = round(time.time() - t0, 1)
sr = int(proc.model_config.sampling_rate)
rif = json.loads((L / "riferimenti.json").read_text(encoding="utf-8"))["testo"]
CAMPI = {"prompt_audio_speaker1": str(L / "rif-a.wav"), "prompt_text_speaker1": rif,
         "prompt_audio_speaker2": str(L / "rif-b.wav"), "prompt_text_speaker2": rif}
scrivi(L / "pronto.json", {"rate": sr, "carico_s": carico})
print("caricato", carico, "s; GPU MB", torch.cuda.max_memory_allocated() // 2**20, flush=True)

fatte = 0
while True:
    richieste = sorted((L / "richieste").glob("*.json"))
    if not richieste:
        time.sleep(0.2)
        continue
    f = richieste[0]
    q = json.loads(f.read_text(encoding="utf-8"))
    f.unlink()
    rid = str(q["id"])
    t = time.time()
    torch.manual_seed(int(q.get("seme", 42)))
    torch.cuda.reset_peak_memory_stats()
    try:
        _, _, conv = prepare_sample(0, {"text": q["testo"], **CAMPI}, MODO, proc, sr, True, True)
        ingr = proc([conv], mode="continuation")
        with torch.no_grad():
            out = model.generate(input_ids=ingr["input_ids"].to(DEV), attention_mask=ingr["attention_mask"].to(DEV),
                                 max_new_tokens=2800, audio_temperature=1.1, audio_top_p=0.9, audio_top_k=50,
                                 audio_repetition_penalty=1.1)
        msg = proc.decode(out)[0]
        pezzi = [w.detach().to(dtype=torch.float32, device="cpu").reshape(-1) for w in msg.audio_codes_list]
        x = torch.cat(pezzi).numpy()
        tmp = L / "uscite" / f"{rid}.tmp.wav"
        sf.write(str(tmp), x, sr, subtype="PCM_16")
        os.replace(tmp, L / "uscite" / f"{rid}.wav")
        gen = time.time() - t
        d = len(x) / sr
        m = {"gen_s": round(gen, 1), "durata_s": round(d, 1), "fattore": round(gen / max(d, 0.1), 2),
             "gpu_mb": torch.cuda.max_memory_allocated() // 2**20,
             "rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024}
    except Exception as e:  # noqa: BLE001 — il tipo e il punto: il messaggio può citare il testo
        tb = traceback.extract_tb(e.__traceback__)[-1]
        m = {"errore": type(e).__name__, "dove": f"{Path(tb.filename).name}:{tb.lineno}"}
        if os.environ.get("MOSS_PROVA"):       # solo col banco, sul materiale di fantasia
            m["messaggio"] = str(e)[:500]
    scrivi(L / "uscite" / f"{rid}.json", m)
    fatte += 1
    print("fatta", rid, json.dumps(m), flush=True)
