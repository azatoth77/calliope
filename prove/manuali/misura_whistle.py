"""Misura di Whistle (Cactus Compute, cactus-needle) contro Whisper sulla voce vera (10/10).

Rapporto: docs/ricerche/2026-10-10-whistle.md. NON fa parte del runner delle prove: si lancia a
mano e, senza i pacchetti o senza le registrazioni, esce con 77.

Due interpreti diversi, di proposito:
- `whistle` gira nel venv a parte di Whistle (mai in quello di Calliope), con `python -I` e la
  cartella di lavoro fuori dal pacchetto; telemetria spenta (NEEDLE_TELEMETRY=0, DO_NOT_TRACK=1,
  HF_HUB_OFFLINE=1) e motore e pesi scaricati e controllati a mano (NEEDLE3_LIB_PATH,
  NEEDLE_WHISTLE_WEIGHTS), così il pacchetto non scarica nulla da sé. Solo libreria standard.
- `whisper`, `riferimento`, `valuta` girano nel venv di Calliope (faster-whisper, numpy).

  (tutti i comandi che leggono audio: [--solo PEZZO] tiene le cartelle con PEZZO nel nome)

  misura_whistle.py whistle --uscita F.jsonl [--dati DIR] [--nomi FILE] [--ogni K]
     varianti: it (lingua imposta), it_calliope (keywords=["Calliope"]), it_nomi (Calliope e i
     nomi di FILE, uno per riga), auto (lingua da riconoscere), it_nots (senza tempi per parola,
     solo per la latenza)
  misura_whistle.py whisper --modello M --dispositivo cuda|cpu --uscita F.jsonl [--dati DIR]
        [--ogni K] [--nomi FILE] [--parole]
     come Transcriber sul portatile: beam 5, prompt «Conversazione con Calliope.», hotwords
     «Calliope» (con --nomi anche i nomi), condition_on_previous_text=False; --ogni K prende
     una frase ogni K (per la CPU); --parole aggiunge un secondo passaggio con le probabilità
  misura_whistle.py riferimento --v3 F.jsonl --turbo G.jsonl --pagina DIR [--dati DIR]
        [--motori nome=F.jsonl ...] [--massimo 40]
     riferimento: le 104 frasi verificate a mano (prove/riferimenti_whisper.tsv), per le altre
     large-v3; dubbie le frasi dove large-v3, large-v3-turbo e la trascrizione di allora non
     concordano. Scrive DIR/riferimento.json e DIR/dubbie.html (lettore audio sui wav
     originali, le trascrizioni di ogni motore e la scelta, che si scarica in correzioni.tsv)
  misura_whistle.py valuta --riferimento DIR/riferimento.json motore=F.jsonl ...
        [--correzioni FILE.tsv] [--nomi FILE] [--dettaglio OUT.tsv]

DIR (dati) = registrazioni/ (cartelle con i wav e trascrizioni.tsv): materiale privato, i file
di uscita con le trascrizioni vanno in privato/ (fuori da git).
"""
import array
import json
import os
import statistics
import sys
import time
import wave
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
SALTA = 77
PROMPT = "Conversazione con Calliope."


# ───────────────────────────── comuni (solo libreria standard) ─────────────────────────────
def opzioni(argv):
    o, i = {"_": []}, 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            k = a[2:].replace("-", "_")
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                o[k] = argv[i + 1]
                i += 2
            else:
                o[k] = True
                i += 1
        else:
            o["_"].append(a)
            i += 1
    return o


def clip(dati: Path, ogni: int = 1, solo: str | None = None):
    """Le registrazioni, in ordine: (id, percorso, durata in secondi); `solo` tiene le
    cartelle il cui nome lo contiene (per esempio «whistle», le frasi registrate apposta)."""
    out = []
    for p in sorted(dati.glob("2026-*/*.wav")):
        if solo and solo not in p.parent.name:
            continue
        with wave.open(str(p)) as w:
            out.append((f"{p.parent.name}__{p.stem}", p, w.getnframes() / w.getframerate()))
    return out[::ogni]


def dati_o_salta(o) -> Path:
    d = Path(o.get("dati") or RADICE / "registrazioni")
    if not d.is_dir() or not list(d.glob("2026-*/*.wav")):
        print(f"Registrazioni non trovate in {d}: misura saltata.")
        sys.exit(SALTA)
    return d


def leggi_float(p: Path) -> array.array:
    with wave.open(str(p)) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
        a = array.array("h")
        a.frombytes(w.readframes(w.getnframes()))
    if sys.byteorder == "big":
        a.byteswap()
    return array.array("f", (v / 32768.0 for v in a))


def nomi_da(o) -> list[str]:
    f = o.get("nomi")
    if not f:
        return []
    return [r.strip() for r in Path(f).read_text(encoding="utf-8").splitlines()
            if r.strip() and not r.startswith("#")]


def scrivi(f, riga):
    f.write(json.dumps(riga, ensure_ascii=False) + "\n")
    f.flush()


# ───────────────────────────────────────── WHISTLE ─────────────────────────────────────────
def cmd_whistle(o):
    for k, v in (("NEEDLE_TELEMETRY", "0"), ("DO_NOT_TRACK", "1"), ("HF_HUB_OFFLINE", "1")):
        os.environ[k] = v
    if not os.environ.get("NEEDLE3_LIB_PATH") or not os.environ.get("NEEDLE_WHISTLE_WEIGHTS"):
        print("Servono NEEDLE3_LIB_PATH e NEEDLE_WHISTLE_WEIGHTS (motore e pesi controllati a mano).")
        sys.exit(SALTA)
    try:
        import needle
    except ImportError:
        print("cactus-needle non installato in questo interprete: misura saltata.")
        sys.exit(SALTA)
    dati = dati_o_salta(o)
    nomi = nomi_da(o)
    varianti = [("it", "it", None, True), ("it_calliope", "it", ["Calliope"], True),
                ("auto", None, None, True), ("it_nots", "it", None, False)]
    if nomi:
        varianti.insert(2, ("it_nomi", "it", ["Calliope"] + nomi, True))
    w = needle.Whistle()
    elenco = clip(dati, int(o.get("ogni", 1)), o.get("solo"))
    riscaldo = leggi_float(elenco[0][1])
    for _ in range(3):
        w.transcribe(riscaldo, language="it")
    with open(o["uscita"], "w", encoding="utf-8") as f:
        for n, (cid, p, dur) in enumerate(elenco):
            x = leggi_float(p)
            for nome, lingua, kw, ts in varianti:
                t = time.perf_counter()
                r = w.transcribe(x, language=lingua, keywords=kw, word_timestamps=ts)
                dt = time.perf_counter() - t
                scrivi(f, dict(id=cid, motore=f"whistle_{nome}", testo=r.get("text", ""),
                               lingua=r.get("language"), t=round(dt, 4), durata=round(dur, 3),
                               ttft_ms=r.get("ttft_ms"), parole=[(x["word"], x["probability"], x["start"], x["end"])
                                                                 for x in r.get("words", [])]))
            if n % 25 == 0:
                print(n, cid, r.get("text", ""), flush=True)


# ───────────────────────────────────────── WHISPER ─────────────────────────────────────────
def cmd_whisper(o):
    sys.path.insert(0, str(RADICE))
    try:
        import numpy as np
        from faster_whisper import WhisperModel
        from calliope.stt import _add_cuda_dlls
    except ImportError:
        print("faster-whisper non installato: misura saltata.")
        sys.exit(SALTA)
    dati = dati_o_salta(o)
    disp = o.get("dispositivo", "cuda")
    if disp == "cuda":
        _add_cuda_dlls()
    modello = o["modello"]
    m = WhisperModel(modello, device=disp, compute_type="int8_float16" if disp == "cuda" else "int8")
    hot = " ".join(["Calliope"] + nomi_da(o))
    kw = dict(language="it", beam_size=5, hotwords=hot, initial_prompt=PROMPT,
              condition_on_previous_text=False)
    elenco = clip(dati, int(o.get("ogni", 1)), o.get("solo"))

    def a(p):
        return np.frombuffer(leggi_float(p).tobytes(), dtype=np.float32)

    for _ in range(2):
        list(m.transcribe(a(elenco[0][1]), **kw)[0])
    etichetta = o.get("etichetta") or f"{modello}_{disp}"
    with open(o["uscita"], "w", encoding="utf-8") as f:
        for n, (cid, p, dur) in enumerate(elenco):
            x = a(p)
            t = time.perf_counter()
            seg, _ = m.transcribe(x, **kw)
            testo = " ".join(s.text.strip() for s in seg).strip()
            dt = time.perf_counter() - t
            riga = dict(id=cid, motore=etichetta, testo=testo, t=round(dt, 4), durata=round(dur, 3))
            if o.get("parole"):
                seg, _ = m.transcribe(x, word_timestamps=True, **kw)
                riga["parole"] = [(w.word.strip(), round(float(w.probability), 3), w.start, w.end)
                                  for s in seg for w in (s.words or ()) if any(c.isalnum() for c in w.word)]
            scrivi(f, riga)
            if n % 25 == 0:
                print(n, cid, round(dt, 3), testo, flush=True)


# ────────────────────────────────────────── TESTO ──────────────────────────────────────────
def _norm():
    sys.path.insert(0, str(RADICE))
    from prove.misura_stt import norm, allinea
    return norm, allinea


def leggi_jsonl(f) -> dict:
    out = {}
    for r in open(f, encoding="utf-8"):
        r = json.loads(r)
        out[r["id"]] = r
    return out


def tsv_di_allora(dati: Path) -> dict:
    out = {}
    for t in dati.glob("2026-*/trascrizioni.tsv"):
        for riga in t.read_text(encoding="utf-8").splitlines():
            c = riga.split("\t")
            if len(c) >= 3:
                out[f"{t.parent.name}__{c[0]}"] = c[2]
    return out


def verificate(dati: Path) -> tuple[dict, set]:
    """Le 104 frasi verificate a mano il 24/09 e le frasi registrate apposta (atteso.tsv,
    scritto da registra_whistle.py: il testo che si doveva dire)."""
    import csv
    ok, incerte = {}, set()
    for t in dati.glob("2026-*/atteso.tsv"):
        for riga in t.read_text(encoding="utf-8").splitlines()[1:]:
            c = riga.split("	")
            if len(c) >= 2:
                ok[f"{t.parent.name}__{c[0]}"] = c[1]
    with open(RADICE / "prove" / "riferimenti_whisper.tsv", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            k = f"{r['cartella']}__{r['stem']}"
            (ok.__setitem__(k, r["riferimento"]) if r["sicurezza"] == "sicura" else incerte.add(k))
    return ok, incerte


def wer_di(norm, allinea, rif, hyp) -> float:
    r, h = norm(rif), norm(hyp)
    s, d, i = allinea(r, h)
    return (s + d + i) / max(len(r), 1)


def cmd_riferimento(o):
    norm, allinea = _norm()
    dati = dati_o_salta(o)
    v3, turbo = leggi_jsonl(o["v3"]), leggi_jsonl(o["turbo"])
    allora = tsv_di_allora(dati)
    ok, incerte = verificate(dati)
    motori = {}
    for coppia in o["_"]:
        nome, f = coppia.split("=", 1)
        motori[nome] = leggi_jsonl(f)
    rif, dubbie = {}, []
    for cid, p, dur in clip(dati, 1, o.get("solo")):
        if cid in incerte:
            rif[cid] = dict(rif=None, fonte="incerta (esclusa)", wav=str(p))
            continue
        if cid in ok:
            rif[cid] = dict(rif=ok[cid], fonte="verificata", wav=str(p))
            continue
        if cid not in v3 or cid not in turbo:
            continue
        a, b, c = v3[cid]["testo"], turbo[cid]["testo"], allora.get(cid, "")
        d = not (norm(a) == norm(b) == norm(c))
        rif[cid] = dict(rif=a, fonte="large-v3", dubbia=d, wav=str(p))
        if d:
            dubbie.append((max(wer_di(norm, allinea, a, b), wer_di(norm, allinea, a, c)), cid))
    dubbie.sort(reverse=True)
    massimo = int(o.get("massimo", 40))
    for _, cid in dubbie[:massimo]:
        rif[cid]["in_pagina"] = True
    out = Path(o["pagina"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "riferimento.json").write_text(json.dumps(rif, ensure_ascii=False, indent=1), encoding="utf-8")
    righe = []
    for _, cid in dubbie[:massimo]:
        voci = [("large-v3", v3[cid]["testo"]), ("large-v3-turbo", turbo[cid]["testo"]),
                ("allora (tsv)", allora.get(cid, ""))]
        voci += [(n, m[cid]["testo"]) for n, m in motori.items() if cid in m]
        righe.append(dict(id=cid, wav=Path(rif[cid]["wav"]).resolve().as_uri(), voci=voci))
    (out / "dubbie.html").write_text(PAGINA.replace("__DATI__", json.dumps(righe, ensure_ascii=False)),
                                     encoding="utf-8")
    n_auto = sum(1 for r in rif.values() if r["fonte"] == "large-v3")
    print(f"verificate {len(ok)}, incerte escluse {len(incerte)}, large-v3 {n_auto}, dubbie {len(dubbie)}, "
          f"nella pagina {min(len(dubbie), massimo)} → {out / 'dubbie.html'}")


PAGINA = r"""<!doctype html>
<html lang="it"><head><meta charset="utf-8"><title>Frasi dubbie</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{--sf:#fafaf7;--testo:#1d1d1b;--tenue:#6b6b66;--riga:#e4e2da;--acc:#2f5d8a;--scelta:#e8f0f8}
@media (prefers-color-scheme: dark){:root{--sf:#1b1b1a;--testo:#ecebe6;--tenue:#9d9c95;--riga:#34332f;--acc:#8fb5dc;--scelta:#24303c}}
body{background:var(--sf);color:var(--testo);font:15px/1.45 system-ui,sans-serif;margin:0 auto;max-width:980px;padding:16px}
h1{font-size:20px;margin:0 0 4px} p.n{color:var(--tenue);margin:0 0 16px}
.f{border-top:1px solid var(--riga);padding:12px 0} .id{font:12px ui-monospace,monospace;color:var(--tenue)}
audio{width:100%;max-width:420px;height:34px;margin:6px 0}
label{display:block;padding:3px 6px;border-radius:4px;cursor:pointer} label:has(input:checked){background:var(--scelta)}
label b{display:inline-block;min-width:150px;font-weight:600;color:var(--tenue)}
input[type=text]{width:100%;box-sizing:border-box;padding:5px;margin-top:4px;background:transparent;color:var(--testo);border:1px solid var(--riga);border-radius:4px}
.barra{position:sticky;bottom:0;background:var(--sf);border-top:1px solid var(--riga);padding:10px 0;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
button{background:var(--acc);color:var(--sf);border:0;border-radius:4px;padding:8px 14px;font-weight:600;cursor:pointer}
</style></head><body>
<h1>Frasi dubbie: chi ha ragione?</h1>
<p class="n">Riascolta ogni frase e scegli la trascrizione giusta, oppure scrivila nel campo sotto (il campo vince
sulla scelta). Le scelte restano in questo browser; alla fine «Scarica correzioni.tsv» e mettilo accanto a questa
pagina. Se il lettore non parte, apri la pagina con Edge o Chrome direttamente dal disco.</p>
<div id="elenco"></div>
<div class="barra"><button id="scarica">Scarica correzioni.tsv</button><span id="conto" class="n"></span></div>
<script>
const DATI = __DATI__;
const CHIAVE = "dubbie-whistle";
let stato = {};
try { stato = JSON.parse(localStorage.getItem(CHIAVE) || "{}"); } catch (e) {}
const salva = () => { try { localStorage.setItem(CHIAVE, JSON.stringify(stato)); } catch (e) {} conta(); };
const conta = () => { document.getElementById("conto").textContent =
  Object.values(stato).filter(s => (s.testo || "").trim() || s.scelta).length + " di " + DATI.length + " decise"; };
const el = document.getElementById("elenco");
DATI.forEach((d, i) => {
  const s = stato[d.id] || (stato[d.id] = {});
  const div = document.createElement("div"); div.className = "f";
  div.innerHTML = `<div class="id">${i + 1}. ${d.id}</div><audio controls preload="none" src="${d.wav}"></audio>`;
  d.voci.forEach(([nome, testo]) => {
    const l = document.createElement("label");
    const r = document.createElement("input"); r.type = "radio"; r.name = "r" + i; r.value = nome;
    r.checked = s.scelta === nome;
    r.onchange = () => { s.scelta = nome; s.scelto = testo; salva(); };
    const b = document.createElement("b"); b.textContent = nome;
    l.append(r, " ", b, document.createTextNode(testo || "(vuota)")); div.append(l);
  });
  const t = document.createElement("input"); t.type = "text"; t.placeholder = "testo giusto, se nessuna va bene";
  t.value = s.testo || ""; t.oninput = () => { s.testo = t.value; salva(); }; div.append(t);
  el.append(div);
});
conta();
document.getElementById("scarica").onclick = () => {
  const righe = ["id\tcorretto\tscelta"];
  DATI.forEach(d => { const s = stato[d.id] || {};
    const testo = (s.testo || "").trim() || s.scelto || "";
    if (testo) righe.push([d.id, testo.replace(/\t|\n/g, " "), (s.testo || "").trim() ? "scritta" : s.scelta].join("\t")); });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([righe.join("\n") + "\n"], {type: "text/tab-separated-values"}));
  a.download = "correzioni.tsv"; a.click();
};
</script></body></html>
"""


# ────────────────────────────────────────── VALUTA ─────────────────────────────────────────
def lev(a, b) -> int:
    prec = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prec[j] + 1, cur[j - 1] + 1, prec[j - 1] + (x != y)))
        prec = cur
    return prec[-1]


def p(vals, q):
    v = sorted(vals)
    return v[min(len(v) - 1, int(q * len(v)))] if v else float("nan")


def cmd_valuta(o):
    import difflib
    from collections import Counter
    norm, allinea = _norm()
    rif = json.loads(Path(o["riferimento"]).read_text(encoding="utf-8"))
    if o.get("correzioni") and Path(o["correzioni"]).exists():
        for riga in Path(o["correzioni"]).read_text(encoding="utf-8").splitlines()[1:]:
            c = riga.split("\t")
            if len(c) >= 2 and c[0] in rif and c[1].strip():
                rif[c[0]].update(rif=c[1].strip(), fonte="corretta a mano", dubbia=False)
    nomi = {n.lower() for n in nomi_da(o)}
    insiemi = {
        "verificate": [k for k, r in rif.items() if r["fonte"] in ("verificata", "corretta a mano")],
        "tutte": [k for k, r in rif.items() if r["rif"]],
        "senza_dubbie": [k for k, r in rif.items() if r["rif"] and not r.get("dubbia")],
    }
    det = []
    print("insiemi:", {k: len(v) for k, v in insiemi.items()})
    for coppia in o["_"]:
        nome, f = coppia.split("=", 1)
        m = leggi_jsonl(f)
        res = {}
        for ins, chiavi in insiemi.items():
            chiavi = [k for k in chiavi if k in m]
            S = D = I = N = C = Nc = esatte = 0
            for k in chiavi:
                r, h = norm(rif[k]["rif"]), norm(m[k]["testo"])
                s, d, i = allinea(r, h)
                S, D, I, N = S + s, D + d, I + i, N + len(r)
                C += lev(" ".join(r), " ".join(h))
                Nc += len(" ".join(r))
                esatte += r == h
            res[ins] = (len(chiavi), (S + D + I) / max(N, 1), C / max(Nc, 1), esatte, S, D, I)
        # il nome: frasi del riferimento che cominciano con «calliope»
        tutte = [k for k in insiemi["tutte"] if k in m]
        col_nome = [k for k in tutte if norm(rif[k]["rif"])[:1] == ["calliope"]]
        trovato = sum(1 for k in col_nome if "calliope" in norm(m[k]["testo"])[:2])
        senza = [k for k in tutte if "calliope" not in norm(rif[k]["rif"])]
        inventato = sum(1 for k in senza if "calliope" in norm(m[k]["testo"]))
        # nomi propri (dal file privato)
        nr = nt = 0
        for k in tutte:
            r, h = norm(rif[k]["rif"]), set(norm(m[k]["testo"]))
            for w in r:
                if w in nomi:
                    nr += 1
                    nt += w in h
        tempi = [m[k]["t"] for k in m]
        rtf = [m[k]["t"] / m[k]["durata"] for k in m]
        lingue = Counter(m[k].get("lingua") for k in m if "lingua" in m[k])
        # probabilità per parola: le parole sbagliate hanno p bassa?
        pr = None
        if any(m[k].get("parole") for k in tutte):
            giu, sba = [], []
            for k in tutte:
                pw = m[k].get("parole") or []
                r = norm(rif[k]["rif"])
                toks, owner = [], []
                for j, (w, prob, *_x) in enumerate(pw):
                    for t in norm(w):
                        toks.append(t)
                        owner.append(j)
                bad = set()
                for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, r, toks, autojunk=False).get_opcodes():
                    if op != "equal":
                        bad.update(owner[j] for j in range(j1, j2))
                for j, (w, prob, *_x) in enumerate(pw):
                    if norm(w):
                        (sba if j in bad else giu).append(prob)
            soglie = {}
            for s in (0.3, 0.5, 0.7):
                soglie[s] = (sum(x < s for x in sba), len(sba), sum(x < s for x in giu), len(giu))
            pr = soglie
        print(f"\n== {nome}  (frasi {len(m)}; tempo mediana {statistics.median(tempi):.3f} s, p90 {p(tempi, .9):.3f} s, "
              f"RTF mediana {statistics.median(rtf):.3f})")
        for ins, (n, wer, cer, es, S, D, I) in res.items():
            print(f"   {ins:13s} n={n:3d}  WER {wer * 100:5.1f} %  CER {cer * 100:5.1f} %  esatte {es:3d}  (S {S} D {D} I {I})")
        print(f"   nome in testa {trovato}/{len(col_nome)}, «calliope» inventato {inventato}/{len(senza)}, nomi propri {nt}/{nr}")
        if lingue:
            print(f"   lingua: {dict(lingue)}")
        if pr:
            for s, (a, b, c, d) in pr.items():
                print(f"   p<{s}: segnala {a}/{b} parole sbagliate ({a / max(b, 1) * 100:.0f} %) e {c}/{d} giuste ({c / max(d, 1) * 100:.1f} %)")
        for k in tutte:
            det.append((nome, k, rif[k]["fonte"] + ("*" if rif[k].get("dubbia") else ""), rif[k]["rif"], m[k]["testo"],
                        f"{wer_di(norm, allinea, rif[k]['rif'], m[k]['testo']):.2f}"))
    if o.get("dettaglio"):
        with open(o["dettaglio"], "w", encoding="utf-8") as f:
            f.write("motore\tid\tfonte\triferimento\ttrascrizione\twer\n")
            for r in det:
                f.write("\t".join(r) + "\n")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if len(sys.argv) < 2 or sys.argv[1] not in ("whistle", "whisper", "riferimento", "valuta"):
        print(__doc__)
        sys.exit(2)
    o = opzioni(sys.argv[2:])
    {"whistle": cmd_whistle, "whisper": cmd_whisper, "riferimento": cmd_riferimento,
     "valuta": cmd_valuta}[sys.argv[1]](o)


if __name__ == "__main__":
    main()
