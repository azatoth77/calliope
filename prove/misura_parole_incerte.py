import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Parole incerte: la probabilità per parola di Whisper riconosce le parole sbagliate, e i nomi
in particolare? (08/10, docs/ricerche/2026-10-08-parole-incerte.md). Manuale, non nel runner.

  misura_parole_incerte.py sintetizza --uscita DIR [--voci CARTELLA]
     le 40 frasi di prove/riferimenti_nomi.tsv (nomi di fantasia: città di due parole,
     contatti, entità, estensioni, conferme, frasi libere) con le tre voci di Piper di
     sintetizza_dominio.py (rumore rosa a 20 dB, seme fisso): DIR/<voce>__<id>.wav
  misura_parole_incerte.py trascrivi --dati DIR_STT [--nomi DIR] --motore whispercpp|faster
        [--url U] [--modello M] --uscita F.jsonl [--senza-parole]
     DIR_STT come per misura_stt.py (riferimenti_whisper.tsv + rif/, riferimenti_dominio.tsv
     + dominio/); salva TUTTE le parole con la probabilità (whisper-server: verbose_json;
     faster-whisper: word_timestamps=True, le opzioni di calliope/stt.py)
  misura_parole_incerte.py valuta F.jsonl [--elenco]
     per insieme: WER senza il nome, parole sbagliate con p alta, precisione e richiamo della
     soglia sulla parola (0,2–0,9), frasi segnalate; per i nomi negli argomenti: nomi sbagliati
     segnalati, nomi giusti segnalati, frasi libere segnalate. Una differenza di soli spazi
     («Prato Fiorito» per «Pratofiorito») non è un errore
  misura_parole_incerte.py vocabolario F.jsonl
     il nome noto più simile (lettere, doppie ridotte) a ogni nome sbagliato: proposte giuste
     e sbagliate per soglia di somiglianza; quante frasi vere avrebbero un «forse intendevi»
     spurio se il confronto si facesse sull'intera frase; provenienza.vicina sugli stessi nomi

Solo httpx e numpy (Piper e faster-whisper per sintetizza e per il motore faster). Le richieste
a whisper-server sono quelle di Calliope (prompt corto, temperature 0), con 0,2 s di pausa.
"""
import csv
import difflib
import json
import re
import time
import unicodedata
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PROMPT = "Conversazione con Calliope."
VOCI = ["it_IT-giorgio-medium", "it_IT-paola-medium", "it_IT-riccardo-x_low"]
SOGLIE = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
NUM = {"uno": "1", "due": "2", "tre": "3", "quattro": "4", "cinque": "5", "sei": "6",
       "sette": "7", "otto": "8", "nove": "9", "dieci": "10"}


def opzioni(argv):
    o = {}
    for i, a in enumerate(argv):
        if a.startswith("--") and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            o[a[2:].replace("-", "_")] = argv[i + 1]
    return o


def frasi_nomi():
    with open(ROOT / "prove" / "riferimenti_nomi.tsv", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


# ─────────────────────────────── SINTESI ───────────────────────────────
def sintetizza(o):
    from piper import PiperVoice
    from scipy.signal import resample_poly
    from prove.sintetizza_dominio import SR, SNR_DB, rumore_rosa, sintetizza as sint
    out = Path(o["uscita"])
    out.mkdir(parents=True, exist_ok=True)
    voci = Path(o.get("voci") or ROOT / "voices")
    rng = np.random.default_rng(8)
    for nome in VOCI:
        voce = PiperVoice.load(str(voci / f"{nome}.onnx"))
        sr = voce.config.sample_rate
        for r in frasi_nomi():
            audio = sint(voce, r["riferimento"], float(rng.uniform(0.9, 1.1)))
            g = np.gcd(sr, SR)
            audio = resample_poly(audio, SR // g, sr // g).astype(np.float32)
            pad = np.zeros(int(0.3 * SR), np.float32)
            audio = np.concatenate([pad, audio, pad])
            p = np.sqrt(np.mean(audio ** 2)) + 1e-9
            audio = audio + rumore_rosa(len(audio), rng) * p / (10 ** (SNR_DB / 20))
            audio *= float(rng.uniform(0.3, 0.6)) / (np.max(np.abs(audio)) + 1e-9)
            with wave.open(str(out / f"{nome}__{r['id']}.wav"), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
        print(nome, "fatto", flush=True)


# ─────────────────────────────── TRASCRIZIONE ───────────────────────────────
def elenco(dati: Path, nomi):
    out = []
    with open(dati / "riferimenti_whisper.tsv", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            out.append(dict(id=f"{r['cartella']}__{r['stem']}", insieme="rif", tipo="vera",
                            rif=r["riferimento"], nomi="",
                            wav=dati / "rif" / f"{r['cartella']}__{r['stem']}.wav"))
    with open(dati / "riferimenti_dominio.tsv", encoding="utf-8") as f:
        dom = list(csv.DictReader(f, delimiter="\t"))
    for voce in VOCI:
        for r in dom:
            out.append(dict(id=f"{voce}__{r['id']}", insieme="dominio", tipo=r["conversazione"],
                            rif=r["riferimento"], nomi="",
                            wav=dati / "dominio" / f"{voce}__{r['id']}.wav"))
        if nomi is not None:
            for r in frasi_nomi():
                out.append(dict(id=f"{voce}__{r['id']}", insieme="nomi", tipo=r["tipo"],
                                rif=r["riferimento"], nomi=r["nomi"] or "",
                                wav=nomi / f"{voce}__{r['id']}.wav"))
    return [x for x in out if Path(x["wav"]).exists()]


def motore_whispercpp(url):
    import httpx
    from calliope.stt import unisci_righe
    from calliope.stt_correzione import parole_whisper
    http = httpx.Client(timeout=60)

    def f(fr, verbose=True):
        data = {"model": "whisper", "language": "it", "prompt": PROMPT, "temperature": "0",
                "response_format": "verbose_json" if verbose else "json"}
        r = http.post(url.rstrip("/") + "/audio/transcriptions",
                      files={"file": ("f.wav", open(fr["wav"], "rb").read(), "audio/wav")},
                      data=data)
        r.raise_for_status()
        v = r.json()
        return unisci_righe(v.get("text", "")).strip(), (parole_whisper(v) if verbose else [])
    return f


def motore_faster(modello):
    from calliope.stt import _add_cuda_dlls
    _add_cuda_dlls()
    from faster_whisper import WhisperModel
    m = WhisperModel(modello, device="cuda", compute_type="int8_float16")

    def leggi(p):
        with wave.open(str(p)) as w:
            return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768

    def f(fr, verbose=True):
        segs, _ = m.transcribe(leggi(fr["wav"]), language="it", beam_size=5,
                               hotwords="Calliope", initial_prompt=PROMPT,
                               condition_on_previous_text=False, word_timestamps=verbose)
        segs = list(segs)
        parole = [(w.word.strip(), float(w.probability)) for s in segs for w in (s.words or [])
                  if any(c.isalnum() for c in w.word)] if verbose else []
        return " ".join(s.text.strip() for s in segs).strip(), parole
    return f


def trascrivi(o, argv):
    verbose = "--senza-parole" not in argv
    f = (motore_whispercpp(o.get("url") or "http://127.0.0.1:8003/v1")
         if o["motore"] == "whispercpp" else motore_faster(o.get("modello") or "large-v3-turbo"))
    el = elenco(Path(o["dati"]), Path(o["nomi"]) if o.get("nomi") else None)
    f(el[0], verbose)
    f(el[0], verbose)                                      # riscaldamento
    with open(o["uscita"], "w", encoding="utf-8") as out:
        for fr in el:
            t0 = time.perf_counter()
            testo, parole = f(fr, verbose)
            t = time.perf_counter() - t0
            out.write(json.dumps(dict({k: v for k, v in fr.items() if k != "wav"}, testo=testo,
                                      parole=parole, t=round(t, 4)), ensure_ascii=False) + "\n")
            if o["motore"] == "whispercpp":
                time.sleep(0.2)
    print("fatto", o["uscita"], len(el))


# ─────────────────────────────── VALUTAZIONE ───────────────────────────────
def tok(s):
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return [NUM.get(t, t) for t in re.findall(r"[a-z0-9]+", s)]


def allinea(r):
    """Le parole di Whisper (senza il nome), giuste o sbagliate rispetto al riferimento, e
    quali cadono sul nome dell'argomento (`nomi`)."""
    rif = [t for t in tok(r["rif"]) if t != "calliope"]
    hyp = [(t, p) for w, p in r["parole"] for t in tok(w) if t != "calliope"]
    nomi = set(tok(r.get("nomi") or ""))
    sm = difflib.SequenceMatcher(a=rif, b=[t for t, _ in hyp], autojunk=False)
    ops = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "replace" and "".join(rif[i1:i2]) == "".join(t for t, _ in hyp[j1:j2]):
            op = "equal"                                   # solo spazi diversi
        ops.append((op, i1, i2, j1, j2))
    giusta, nel_nome, nome_errato, errori = [False] * len(hyp), [False] * len(hyp), False, 0
    for op, i1, i2, j1, j2 in ops:
        tocca = any(t in nomi for t in rif[i1:i2])
        for j in range(j1, j2):
            giusta[j], nel_nome[j] = op == "equal", tocca
        if op != "equal":
            nome_errato |= tocca
            errori += max(i2 - i1, j2 - j1)
    return dict(hyp=hyp, giusta=giusta, nel_nome=nel_nome, nome_errato=nome_errato,
                nomi=bool(nomi), errori=errori, parole_rif=len(rif))


def valuta_insieme(righe, titolo, elenco_nomi=False):
    A = [(r, allinea(r)) for r in righe]
    if not A:
        return
    print(f"\n=== {titolo}: {len(A)} frasi")
    wer = sum(a["errori"] for _, a in A) / sum(a["parole_rif"] for _, a in A)
    print(f"WER senza il nome {wer:.1%}; frasi con errori {sum(a['errori'] > 0 for _, a in A)}")
    P = [(p, g) for _, a in A for (_, p), g in zip(a["hyp"], a["giusta"])]
    sb = [p for p, g in P if not g]
    print(f"parole {len(P)}, sbagliate {len(sb)}; sbagliate con p >= 0,9: "
          f"{sum(p >= .9 for p in sb)}, >= 0,7: {sum(p >= .7 for p in sb)}, "
          f">= 0,5: {sum(p >= .5 for p in sb)}")
    print("soglia | parole segnalate | sbagliate fra queste | sbagliate trovate | frasi segnalate"
          " | frasi con errore segnalate | frasi giuste segnalate")
    for s in SOGLIE:
        fl = [g for p, g in P if p < s]
        tp = sum(not g for g in fl)
        fs = [(a["errori"] > 0, any(p < s for _, p in a["hyp"])) for _, a in A]
        print(f"{s:.1f} | {len(fl)} | {tp} ({tp / max(len(fl), 1):.0%}) | {tp}/{len(sb)} "
              f"({tp / max(len(sb), 1):.0%}) | {sum(f for _, f in fs)}/{len(fs)} | "
              f"{sum(e and f for e, f in fs)}/{sum(e for e, _ in fs)} | "
              f"{sum((not e) and f for e, f in fs)}/{sum(not e for e, _ in fs)}")
    con = [(r, a) for r, a in A if a["nomi"]]
    if not con:
        return
    ne = [(r, a) for r, a in con if a["nome_errato"]]
    lib = [a for r, a in A if r.get("tipo") == "libera"]
    print(f"-- nomi negli argomenti: {len(con)} frasi, nome sbagliato in {len(ne)}")
    print("soglia | nomi sbagliati segnalati | nomi giusti segnalati | frasi libere segnalate")

    def segn(a, s):
        return any(p < s for (_, p), n in zip(a["hyp"], a["nel_nome"]) if n)
    for s in SOGLIE:
        print(f"{s:.1f} | {sum(segn(a, s) for _, a in ne)}/{len(ne)} | "
              f"{sum(segn(a, s) for _, a in con if not a['nome_errato'])}/{len(con) - len(ne)} | "
              f"{sum(any(p < s for _, p in a['hyp']) for a in lib)}/{len(lib)}")
    if elenco_nomi:
        for r, a in ne:
            nn = [f"{t}:{p:.2f}" for (t, p), n in zip(a["hyp"], a["nel_nome"]) if n]
            print(f"   {r['id']:<34} «{r['rif']}» → «{r['testo']}»  [{' '.join(nn) or 'perso'}]")


def valuta(path, argv):
    righe = [json.loads(x) for x in open(path, encoding="utf-8")]
    for ins in ("rif", "dominio", "nomi"):
        valuta_insieme([r for r in righe if r["insieme"] == ins], f"{Path(path).name} [{ins}]",
                       "--elenco" in argv and ins == "nomi")
    t = sorted(r["t"] for r in righe)
    print(f"\ntempo per frase: mediana {t[len(t) // 2]:.3f} s, p90 {t[int(len(t) * .9)]:.3f} s")


# ─────────────────────────────── VOCABOLARIO ───────────────────────────────
def lettere(s):
    s = unicodedata.normalize("NFKD", str(s).lower())
    s = "".join(c for c in s if c.isalpha() and not unicodedata.combining(c))
    return re.sub(r"(.)\1+", r"\1", s)


def vocabolario(path):
    from calliope.provenienza import vicina
    import importlib.util
    spec = importlib.util.spec_from_file_location("misura_stt", ROOT / "prove" / "misura_stt.py")
    ms = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ms)
    tsv = {r["id"]: r for r in frasi_nomi()}
    voc = [r["nomi"] for r in tsv.values() if r["tipo"] not in ("conferma", "libera") and r["nomi"]]
    voc += list(ms.SATELLITI) + list(ms.SCHERMI) + list(ms.PERSONE) + list(ms.CASA)
    VL = [(v, lettere(v)) for v in dict.fromkeys(v for v in voc if v)]

    def migliore(s):
        ls = lettere(s)
        b = max(VL, key=lambda x: difflib.SequenceMatcher(None, ls, x[1]).ratio())
        return b[0], difflib.SequenceMatcher(None, ls, b[1]).ratio()

    righe = [json.loads(x) for x in open(path, encoding="utf-8")]
    soglie = [0.6, 0.7, 0.8]
    ris = {s: [0, 0, 0] for s in soglie}                  # giusta, sbagliata, nessuna
    n_err = vic = 0
    for r in righe:
        t = tsv.get(r["id"].split("__")[-1]) if r["insieme"] == "nomi" else None
        if not t or t["tipo"] in ("conferma", "libera") or not t["nomi"]:
            continue
        a = allinea(dict(r, nomi=t["nomi"]))
        if not a["nome_errato"]:
            continue
        n_err += 1
        regione = " ".join(tk for (tk, _), n in zip(a["hyp"], a["nel_nome"]) if n)
        b, q = migliore(regione or "x")
        for s in soglie:
            ris[s][2 if q < s else (0 if lettere(b) == lettere(t["nomi"]) else 1)] += 1
        vic += any(vicina(w, set(tok(t["nomi"]))) for w in tok(regione))
    print(f"nomi sbagliati {n_err} (vocabolario di {len(VL)} nomi, quelli giusti compresi)")
    for s in soglie:
        print(f"somiglianza >= {s}: proposta giusta {ris[s][0]}, sbagliata {ris[s][1]}, "
              f"nessuna {ris[s][2]}")
    print(f"provenienza.vicina riconosce una parola del nome giusto in {vic}/{n_err}")
    vere = [r for r in righe if r["insieme"] == "rif"]
    for s in soglie:
        spurie = 0
        for r in vere:
            tk = [x for x in tok(r["testo"]) if x != "calliope"]
            trovata = False
            for n in (1, 2, 3):
                for i in range(len(tk) - n + 1):
                    g = " ".join(tk[i:i + n])
                    if len(lettere(g)) >= 5:
                        b, q = migliore(g)
                        if q >= s and lettere(b) != lettere(g):
                            trovata = True
                            break
                if trovata:
                    break
            spurie += trovata
        print(f"frasi vere con un «forse intendevi» spurio sull'intera frase a {s}: "
              f"{spurie}/{len(vere)}")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, o = argv[1], opzioni(argv)
    if cmd == "sintetizza":
        sintetizza(o)
    elif cmd == "trascrivi":
        trascrivi(o, argv)
    elif cmd == "valuta":
        valuta(argv[2], argv)
    elif cmd == "vocabolario":
        vocabolario(argv[2])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
