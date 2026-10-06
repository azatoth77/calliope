"""
Misura dell'OCR per l'archivio dei documenti di casa (03/10/2026): qualità e tempo, sui
documenti finti di prove/archivio_finto.py, di tre motori senza cloud:

- **visivo**: un modello multimodale servito con l'API compatibile OpenAI (vLLM sulla DGX:
  qwen3.6-35b sulla 8000, gemma4-26b sulla 8001), con l'immagine in un messaggio;
- **rapidocr**: RapidOCR 3 con onnxruntime (PP-OCR, riconoscimento «latin» per gli accenti).

Non è una prova del runner: serve la DGX (o un server multimodale) e, per RapidOCR, un venv
con `rapidocr`, `opencv-python-headless`, `pyclipper`, `shapely`. Le immagini sono le foto
(JPG storti) e le pagine dei PDF scansionati, a piena risoluzione e a metà (telefono vecchio).

    python prove/archivio_misura_ocr.py <cartella dei documenti finti> \
        [--visivo http://127.0.0.1:8000=qwen3.6-35b] [--visivo http://127.0.0.1:8001=gemma4-26b] \
        [--rapidocr]

Stampa per ogni motore e immagine: secondi, CER (errori di carattere sul testo vero, dopo
minuscole e spazi), e quanti dei valori chiave (importi, date, numeri) si leggono esatti.
"""

import argparse
import base64
import io
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archivio_finto  # noqa: E402

PROMPT = ("Trascrivi fedelmente tutto il testo di questa immagine di un documento, riga per "
          "riga, nell'ordine. Non correggere, non riassumere, non aggiungere commenti né "
          "markdown: solo il testo.")


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").lower()).strip()


def cer(rif: str, ipo: str) -> float:
    a, b = norm(rif), norm(ipo)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / max(1, len(a))


def chiavi(doc: dict) -> list[str]:
    """I valori che contano per l'estrazione, come stampati: importi, date, codici."""
    t = archivio_finto.testo(doc)
    vals = re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}|\d{2}/\d{2}/\d{4}|\b[A-Z]{2}[\w-]*\d{3,}\w*\b",
                      t)
    return list(dict.fromkeys(vals))


def immagini(cartella: Path):
    """[(nome, doc, PIL.Image)] per le foto e le pagine dei PDF scansionati."""
    from PIL import Image
    out = []
    for doc in archivio_finto.DOCUMENTI:
        p = cartella / doc["file"]
        if doc["formato"] == "foto":
            out.append((doc["file"], doc, Image.open(p).convert("RGB")))
        elif doc["formato"] == "scansione":
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(str(p))
            out.append((doc["file"], doc, pdf[0].render(scale=2).to_pil().convert("RGB")))
    return out


def jpeg_b64(img) -> str:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def visivo(url: str, modello: str):
    import httpx
    http = httpx.Client(base_url=url.rstrip("/"), timeout=300)

    def leggi(img) -> str:
        body = {"model": modello, "temperature": 0, "max_tokens": 2000,
                "chat_template_kwargs": {"enable_thinking": False},
                "messages": [{"role": "user", "content": [
                    {"type": "image_url",
                     "image_url": {"url": "data:image/jpeg;base64," + jpeg_b64(img)}},
                    {"type": "text", "text": PROMPT}]}]}
        r = http.post("/v1/chat/completions", json=body)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"] or ""
    return leggi


def rapid():
    from rapidocr import LangRec, RapidOCR
    from rapidocr import ModelType, OCRVersion
    eng = RapidOCR(params={"Rec.lang_type": LangRec.LATIN, "Rec.ocr_version": OCRVersion.PPOCRV5,
                           "Rec.model_type": ModelType.MOBILE})

    def leggi(img) -> str:
        import numpy as np
        res = eng(np.array(img))
        txts = list(res.txts or ())
        boxes = res.boxes if res.boxes is not None else []
        # ordine di lettura: per riga (y del centro), poi x
        righe = sorted(zip(boxes, txts), key=lambda bt: (round(sum(p[1] for p in bt[0]) / 4 / 25),
                                                          bt[0][0][0]))
        return "\n".join(t for _, t in righe)
    return leggi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cartella")
    ap.add_argument("--visivo", action="append", default=[], help="url=modello")
    ap.add_argument("--rapidocr", action="store_true")
    ap.add_argument("--json", help="scrive qui i risultati")
    a = ap.parse_args()
    motori = []
    for v in a.visivo:
        url, mod = v.split("=", 1)
        motori.append((mod, visivo(url, mod)))
    if a.rapidocr:
        t0 = time.perf_counter()
        motori.append(("rapidocr-latin", rapid()))
        print(f"rapidocr caricato in {time.perf_counter() - t0:.1f} s")
    imgs = immagini(Path(a.cartella))
    risultati = []
    for nome_m, leggi in motori:
        leggi(imgs[0][2])                      # riscaldamento
        for nome, doc, img in imgs:
            for scala in (1.0, 0.5, "dura"):
                im = (img if scala == 1.0 else archivio_finto.degrada(img) if scala == "dura"
                      else img.resize((int(img.width * scala), int(img.height * scala))))
                t0 = time.perf_counter()
                try:
                    txt = leggi(im)
                except Exception as e:  # noqa: BLE001
                    txt = f"ERRORE {type(e).__name__}: {e}"
                s = time.perf_counter() - t0
                ks = chiavi(doc)
                presi = sum(1 for k in ks if k in txt)
                c = cer(archivio_finto.testo(doc), txt)
                risultati.append({"motore": nome_m, "file": nome, "scala": scala,
                                  "s": round(s, 2), "cer": round(c, 4), "chiavi": presi,
                                  "chiavi_tot": len(ks), "testo": txt})
                print(f"{nome_m:16} {nome[:26]:26} x{scala!s:<4} {s:6.2f} s  CER {c:6.1%}  "
                      f"chiavi {presi}/{len(ks)}", flush=True)
    print("\nRiassunto (mediana dei secondi, CER medio, chiavi esatte):")
    for nome_m, _ in motori:
        for scala in (1.0, 0.5, "dura"):
            rs = [r for r in risultati if r["motore"] == nome_m and r["scala"] == scala]
            ss = sorted(r["s"] for r in rs)
            print(f"  {nome_m:16} x{scala!s:<4} {ss[len(ss) // 2]:.2f} s  "
                  f"CER {sum(r['cer'] for r in rs) / len(rs):.1%}  chiavi "
                  f"{sum(r['chiavi'] for r in rs)}/{sum(r['chiavi_tot'] for r in rs)}")
    if a.json:
        Path(a.json).write_text(json.dumps(risultati, ensure_ascii=False, indent=1),
                                encoding="utf-8")


if __name__ == "__main__":
    main()
