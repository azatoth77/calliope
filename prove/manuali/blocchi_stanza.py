"""Banco della ritrascrizione a blocchi della corsia lenta (15/10, `stanza_lenta_blocchi`,
calliope/stanza/lenta.py). NON fa parte del runner: si lancia sulla DGX, dove c'è l'audio del banco
della stanza (`stanza_audio_banco_giorni`, calliope/stanza/banco.py: accanto a ogni `.wav` il
`.json` con v1 e v2).

    python prove/manuali/blocchi_stanza.py [--banco DIR] [--dal AAAA-MM-GG]
           [--solo-pause] [--pausa S] [--max S] [--ignora-buchi]
           [--url URL] [--n 20] [--senza-ripresa] [--html FILE]

1. **Ricostruisce i blocchi** dai segmenti del banco come la corsia lenta: segmenti consecutivi
   dello stesso satellite e della stessa persona (chi dalla v2, o dalla v1 se la v2 non c'è; un
   segmento spezzato fra due voci non entra), fino al tetto `--max` (di serie quello della
   configurazione, 25 s con 0,3 s di silenzio fra un segmento e l'altro; oltre si spezza al
   confine di segmento), chiusi da una pausa più lunga di `--pausa` (di serie
   `stanza_lenta_blocchi_pausa_s`; 0 = mai). Il banco salva solo le voci di casa: una persona
   diversa non salvata (un ospite, una voce sconosciuta, un segmento scartato) si vede solo dal
   numero del segmento, che il satellite conta di uno in uno; un buco nella numerazione (o una
   riconnessione, che la fa ripartire) chiude il blocco. `--ignora-buchi` non lo fa (più blocchi,
   ma forse con un'altra voce in mezzo che nel blocco non c'è).
2. **Le pause**: la distribuzione delle pause fra segmenti consecutivi della stessa persona
   (senza tetto né soglia), e quanti blocchi cambiano con una soglia di 3, 5, 8 e 15 s rispetto a
   nessuna soglia: per scegliere `stanza_lenta_blocchi_pausa_s` sui dati veri. Con
   `--solo-pause` finisce qui (non serve Whisper).
3. **Ritrascrive** i blocchi di almeno due segmenti col Whisper dei turni (`--url`, di serie
   `stt_url` della configurazione + `/audio/transcriptions`), audio unito, senza prompt,
   temperatura 0, come la corsia lenta. Per i blocchi spezzati dal tetto prova anche la
   **ripresa**: il pezzo dopo con davanti l'ultimo segmento del pezzo prima (se resta sotto i
   30 s), da confrontare a orecchio (il testo ripetuto all'inizio non si toglie da sé).
4. **Scrive una pagina HTML locale di revisione** (di serie `privato/revisione-blocchi-
   AAAAMMGG-HHMM.html`, file 600: contiene voci vere, **mai nel repository**): per `--n` blocchi
   (prima quelli col testo cambiato) l'audio unito (WAV PCM 16 bit in data URI), il testo dei
   segmenti di allora e quello del blocco, la scelta «meglio allora / meglio il blocco / uguali»,
   una nota, e «Scarica le scelte» (JSON). Le scelte restano nel browser (localStorage) fra una
   visita e l'altra.

Stampa solo numeri e le frasi dei blocchi scelti (sul terminale della DGX).
"""

from __future__ import annotations

import argparse
import base64
import datetime
import io
import json
import os
import sys
import time
import wave
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))

import numpy as np  # noqa: E402

SR = 16000
SIL = 0.3
SOGLIE = (3.0, 5.0, 8.0, 15.0)
FASCE = (0.5, 1, 2, 3, 5, 8, 15, 30, 60)


def opzioni(argv):
    p = argparse.ArgumentParser(description="Banco dei blocchi della corsia lenta (15/10)")
    p.add_argument("--banco", help="cartella del banco (di serie <turn_log_dir>/stanza_banco)")
    p.add_argument("--dal", help="solo i giorni da questo (AAAA-MM-GG)")
    p.add_argument("--solo-pause", action="store_true", help="solo la distribuzione delle pause")
    p.add_argument("--pausa", type=float, help="pausa lunga che chiude il blocco (s; 0 = mai)")
    p.add_argument("--max", type=float, help="tetto di un blocco (s)")
    p.add_argument("--ignora-buchi", action="store_true",
                   help="non chiudere il blocco a un buco nella numerazione dei segmenti")
    p.add_argument("--url", help="Whisper (…/audio/transcriptions)")
    p.add_argument("--n", type=int, default=20, help="blocchi nella pagina (di serie 20)")
    p.add_argument("--senza-ripresa", action="store_true")
    p.add_argument("--html", help="la pagina (di serie privato/revisione-blocchi-….html)")
    return p.parse_args(argv)


# ─────────────────────────── i segmenti del banco ───────────────────────────
def _durata_wav(p: Path) -> float:
    from calliope.conserva import _pezzi_wav
    w = _pezzi_wav(p.read_bytes())
    return len(w["dati"] or b"") / (1 if w["fmt"] == 7 else 2) / float(w["sr"] or SR)


def chiave(m: dict) -> str | None:
    """Chi parla nel segmento (la v2 se c'è): None se spezzato fra più voci."""
    v2 = m.get("v2") or []
    if len(v2) > 1:
        return None
    r = v2[0] if v2 else (m.get("v1") or {})
    return str(r.get("chi") or "") or None


def testo_allora(m: dict) -> str:
    v2 = m.get("v2") or []
    return " ".join(str(r.get("testo") or "") for r in v2).strip() if v2 else str(
        (m.get("v1") or {}).get("testo") or "").strip()


def carica(base: Path, dal: str | None = None) -> list[dict]:
    out = []
    for p in sorted(base.rglob("*.json")):
        if p.name in ("acceso.json",) or "-blocco-" in p.name:
            continue
        w = p.with_suffix(".wav")
        if not w.exists():
            continue
        if dal and p.parent.name < dal:
            continue
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
            d = _durata_wav(w)
        except (OSError, ValueError):
            continue
        out.append({"sat": str(m.get("sat") or p.parent.parent.name),
                    "segmento": int(m.get("segmento") or 0), "inizio": float(m["inizio"]),
                    "fine": float(m.get("fine") or m["inizio"]), "durata": d,
                    "chi": chiave(m), "allora": testo_allora(m), "wav": w,
                    "rel": str(w.relative_to(base)).replace("\\", "/")})
    out.sort(key=lambda s: (s["sat"], s["inizio"]))
    return out


def blocchi(segs: list[dict], pausa: float, tetto: float, buchi: bool = True,
            motivi: dict | None = None) -> tuple[list[list[dict]], dict]:
    """[[segmento, …], …] (anche di uno solo) e le chiusure per motivo; in `motivi`
    id(blocco) → perché si è chiuso."""
    out, chiusure, cur = [], {}, []
    motivi = {} if motivi is None else motivi

    def chiudi(motivo):
        nonlocal cur
        if cur:
            out.append(cur)
            chiusure[motivo] = chiusure.get(motivo, 0) + 1
            motivi[id(cur)] = motivo
        cur = []
    for s in segs:
        if s["chi"] is None:
            chiudi("altra_voce")
            out.append([s])
            continue
        if cur:
            u = cur[-1]
            dur = sum(x["durata"] for x in cur) + len(cur) * SIL + s["durata"]
            if s["sat"] != u["sat"]:
                chiudi("satellite")
            elif s["chi"] != u["chi"]:
                chiudi("altra_voce")
            elif buchi and s["segmento"] != u["segmento"] + 1:
                chiudi("buco" if s["segmento"] > u["segmento"] else "scollegato")
            elif pausa > 0 and s["inizio"] - u["fine"] > pausa:
                chiudi("pausa_lunga")
            elif dur > tetto:
                chiudi("tetto")
        cur.append(s)
    chiudi("fine")
    return out, chiusure


def pause_stessa_persona(segs: list[dict], buchi: bool) -> list[float]:
    bb, _ = blocchi(segs, 0.0, 1e9, buchi)
    return [max(0.0, b[i + 1]["inizio"] - b[i]["fine"]) for b in bb for i in range(len(b) - 1)]


def _p(v: list[float], q: float):
    if not v:
        return None
    v = sorted(v)
    return round(v[min(len(v) - 1, int(q * (len(v) - 1) + 0.5))], 2)


def stampa_pause(segs: list[dict], tetto: float, buchi: bool):
    pp = pause_stessa_persona(segs, buchi)
    print(f"\nPause fra segmenti consecutivi della stessa persona ({len(pp)}): "
          + ", ".join(f"p{int(q * 100)} {_p(pp, q)} s" for q in (0.1, 0.25, 0.5, 0.75, 0.9,
                                                                   0.95))
          + f", al più {round(max(pp), 1) if pp else None} s")
    prima = 0.0
    for f in FASCE + (float("inf"),):
        n = sum(1 for x in pp if prima <= x < f)
        etich = f"{prima:g}–{f:g} s" if f != float("inf") else f"oltre {prima:g} s"
        print(f"  {etich:>12}: {n:5d} {'#' * min(60, n)}")
        prima = f
    base, _ = blocchi(segs, 0.0, tetto, buchi)
    base2 = [b for b in base if len(b) >= 2]
    chiavi = {tuple(s["rel"] for s in b) for b in base2}
    print(f"\nBlocchi (≥ 2 segmenti) col tetto di {tetto:g} s: senza soglia di pausa "
          f"{len(base2)} ({sum(len(b) for b in base2)} segmenti)")
    for s_ in SOGLIE:
        bb, _ = blocchi(segs, s_, tetto, buchi)
        b2 = [b for b in bb if len(b) >= 2]
        k2 = {tuple(s["rel"] for s in b) for b in b2}
        print(f"  pausa {s_:4g} s: {len(b2)} blocchi ({sum(len(b) for b in b2)} segmenti); "
              f"blocchi senza soglia che cambiano {len(chiavi - k2)}")


# ─────────────────────────── Whisper e audio ───────────────────────────
def audio_di(b: list[dict]) -> np.ndarray:
    from calliope.conserva import leggi_wav
    sil = np.zeros(int(SIL * SR), np.float32)
    parti = []
    for i, s in enumerate(b):
        a, sr = leggi_wav(s["wav"])
        if sr != SR:
            a = np.interp(np.linspace(0, len(a), int(len(a) * SR / sr), endpoint=False),
                          np.arange(len(a)), a).astype(np.float32)
        if i:
            parti.append(sil)
        parti.append(a.astype(np.float32))
    return np.concatenate(parti) if parti else np.zeros(0, np.float32)


def wav_pcm16(a: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def trascrivi(url: str, modello: str, lingua: str, a: np.ndarray) -> tuple[str, float]:
    import httpx

    from calliope.stt import unisci_righe
    t0 = time.perf_counter()
    r = httpx.post(url, files={"file": ("blocco.wav", wav_pcm16(a), "audio/wav")},
                   data={"model": modello, "language": lingua, "prompt": "",
                         "temperature": "0", "response_format": "json"},
                   timeout=max(30.0, 4.0 * len(a) / SR))
    r.raise_for_status()
    return unisci_righe(str(r.json().get("text") or "")).strip(), time.perf_counter() - t0


# ─────────────────────────── la pagina ───────────────────────────
PAGINA = """<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Revisione blocchi</title>
<style>
:root{--bg:#f7f6f3;--card:#fff;--ink:#1d1d1b;--mute:#6b6a66;--line:#e2e0da;--acc:#2f6f5e;--sel:#e6f1ed}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#1f1f1d;--ink:#ecebe7;--mute:#9a9893;--line:#33322f;--acc:#7cc4ad;--sel:#203a33}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;z-index:2}
h1{font-size:17px;margin:0;flex:1}main{max-width:860px;margin:0 auto;padding:16px}
.c{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:0 0 14px}
.m{color:var(--mute);font-size:13px;margin-bottom:8px}audio{width:100%;margin:4px 0 10px}
ol.seg{margin:4px 0 10px;padding-left:22px}ol.seg li{margin:2px 0}
.blocco{border-left:3px solid var(--acc);padding:4px 10px;margin:6px 0 10px}
.ripresa{color:var(--mute);font-size:14px;margin:0 0 10px}
.t{font-weight:600;font-size:12px;color:var(--mute);display:block}
.scelte{display:flex;gap:8px;flex-wrap:wrap}
label.o{flex:1;min-width:140px;border:1px solid var(--line);border-radius:8px;padding:8px 10px;cursor:pointer}
label.o:has(input:checked){background:var(--sel);border-color:var(--acc)}
textarea{width:100%;min-height:40px;margin-top:8px;font:inherit;background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:6px}
button{font:inherit;background:var(--acc);color:#fff;border:0;border-radius:8px;padding:8px 14px;cursor:pointer}
.fatto{font-size:13px;color:var(--mute)}
</style></head><body>
<header><h1>Revisione: segmenti di allora o blocco unito</h1><span class="fatto" id="conta"></span>
<button id="esporta">Scarica le scelte</button></header>
<main id="casi"></main>
<script>
const CASI = __CASI__;
const CH = "__CHIAVE__";
let scelte = {};
try { scelte = JSON.parse(localStorage.getItem(CH) || "{}"); } catch (e) {}
const salva = () => { try { localStorage.setItem(CH, JSON.stringify(scelte)); } catch (e) {} conta(); };
const conta = () => { const n = CASI.filter(c => (scelte[c.n] || {}).s).length;
  document.getElementById("conta").textContent = n + " di " + CASI.length + " segnati"; };
const main = document.getElementById("casi");
for (const c of CASI) {
  const s = scelte[c.n] || {};
  const d = document.createElement("section"); d.className = "c";
  d.innerHTML = `<div class="m"></div>
   <audio controls preload="none" src="data:audio/wav;base64,${c.audio}"></audio>
   <span class="t">Allora, segmento per segmento</span><ol class="seg"></ol>
   <span class="t">Il blocco unito</span><div class="blocco"></div>
   <div class="ripresa" hidden></div>
   <div class="scelte">
    <label class="o"><input type="radio" name="s${c.n}" value="allora"> Meglio allora</label>
    <label class="o"><input type="radio" name="s${c.n}" value="blocco"> Meglio il blocco</label>
    <label class="o"><input type="radio" name="s${c.n}" value="uguali"> Uguali</label></div>
   <textarea placeholder="Nota (facoltativa): il testo giusto, cosa non va"></textarea>`;
  d.querySelector(".m").textContent = `${c.n} · ${c.quando} · ${c.satellite} · ${c.durata} · ` +
    `${c.segmenti.length} segmenti · pause ${c.pause} · chiuso: ${c.chiusura}` +
    (c.cambiato ? "" : " · testo uguale");
  const ol = d.querySelector("ol.seg");
  for (const t of c.allora) { const li = document.createElement("li"); li.textContent = t || "(vuoto)"; ol.appendChild(li); }
  d.querySelector(".blocco").textContent = c.blocco || "(vuoto)";
  if (c.ripresa) { const r = d.querySelector(".ripresa"); r.hidden = false;
    r.textContent = "Con la ripresa dell'ultimo segmento del pezzo prima: " + c.ripresa; }
  const ta = d.querySelector("textarea"); ta.value = s.nota || "";
  d.querySelectorAll("input").forEach(i => { if (i.value === s.s) i.checked = true;
    i.addEventListener("change", () => { scelte[c.n] = Object.assign(scelte[c.n] || {}, {s: i.value}); salva(); }); });
  ta.addEventListener("input", () => { scelte[c.n] = Object.assign(scelte[c.n] || {}, {nota: ta.value}); salva(); });
  main.appendChild(d);
}
conta();
document.getElementById("esporta").onclick = () => {
  const out = CASI.map(c => ({n: c.n, segmenti: c.segmenti, scelta: (scelte[c.n] || {}).s || "",
    nota: (scelte[c.n] || {}).nota || "", cambiato: c.cambiato}));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], {type: "application/json"}));
  a.download = CH + ".json"; a.click();
};
</script></body></html>
"""


def pagina(casi: list[dict], chiave_: str) -> str:
    js = json.dumps(casi, ensure_ascii=False).replace("</", "<\\/")
    return PAGINA.replace("__CASI__", js).replace("__CHIAVE__", chiave_)


def scrivi_privato(p: Path, testo: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(p.parent, 0o700)
    except OSError:
        pass
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(testo)


# ─────────────────────────── main ───────────────────────────
def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    o = opzioni(argv)
    from calliope.config import load_config
    from calliope.stanza.lenta import norm_parole, somiglianza
    cfg = load_config()
    base = Path(o.banco) if o.banco else Path(cfg.turn_log_dir or "registro") / "stanza_banco"
    if not base.exists():
        print(f"Nessun banco in {base} (stanza_audio_banco_giorni spento?).")
        return 77
    segs = carica(base, o.dal)
    if not segs:
        print(f"Nessun segmento in {base}.")
        return 77
    pausa = float(cfg.stanza_lenta_blocchi_pausa_s if o.pausa is None else o.pausa)
    tetto = float(cfg.stanza_lenta_blocchi_max_s if o.max is None else o.max)
    buchi = not o.ignora_buchi
    per_sat: dict = {}
    for s in segs:
        per_sat[s["sat"]] = per_sat.get(s["sat"], 0) + 1
    print(f"{len(segs)} segmenti del banco in {base} ({len(per_sat)} satelliti), "
          f"{sum(s['durata'] for s in segs) / 60:.1f} minuti di audio")
    stampa_pause(segs, tetto, buchi)
    if o.solo_pause:
        return 0
    motivi: dict = {}
    bb, chiusure = blocchi(segs, pausa, tetto, buchi, motivi)
    b2 = [b for b in bb if len(b) >= 2]
    print(f"\nCon pausa {pausa:g} s e tetto {tetto:g} s: {len(b2)} blocchi di almeno due "
          f"segmenti (media {sum(len(b) for b in b2) / max(1, len(b2)):.1f} segmenti), "
          f"segmenti da soli {sum(1 for b in bb if len(b) == 1)}; chiusure {chiusure}")
    if not b2:
        return 0
    url = o.url or (str(cfg.stt_url or "").rstrip("/") + "/audio/transcriptions")
    if not url.startswith("http"):
        print("Manca l'indirizzo di Whisper (--url o stt_url).")
        return 77
    # Il pezzo prima di ogni blocco spezzato dal tetto (per la ripresa)
    prima_di: dict = {}
    for i in range(1, len(bb)):
        a_, b_ = bb[i - 1], bb[i]
        if motivi.get(id(a_)) == "tetto":
            prima_di[id(b_)] = a_[-1]
    risultati, tempi = [], []
    for k, b in enumerate(b2):
        a = audio_di(b)
        try:
            testo, t = trascrivi(url, cfg.stt_modello, cfg.language, a)
        except Exception as e:  # noqa: BLE001
            print(f"  blocco {k + 1}: Whisper non risponde ({type(e).__name__})")
            continue
        tempi.append(t)
        allora = [s["allora"] for s in b]
        cambiato = norm_parole(testo) != norm_parole(" ".join(allora))
        ripresa = None
        u = prima_di.get(id(b))
        if u is not None and not o.senza_ripresa:
            ar = audio_di([u] + b)
            if len(ar) / SR <= 30.0:
                try:
                    ripresa, _ = trascrivi(url, cfg.stt_modello, cfg.language, ar)
                except Exception:  # noqa: BLE001
                    ripresa = None
        risultati.append({"b": b, "testo": testo, "allora": allora, "cambiato": cambiato,
                          "somiglianza": somiglianza(" ".join(allora), testo), "audio": a,
                          "ripresa": ripresa})
        print(f"\n== blocco {k + 1}: {len(b)} segmenti, {len(a) / SR:.1f} s, Whisper {t:.2f} s"
              + ("" if cambiato else " (uguale)"))
        for s in allora:
            print(f"   allora: {s}")
        print(f"   blocco: {testo}")
        if ripresa:
            print(f"   con la ripresa: {ripresa}")
    n_c = sum(1 for r in risultati if r["cambiato"])
    print(f"\nRitrascritti {len(risultati)} blocchi: testo cambiato in {n_c}; Whisper p50 "
          f"{_p(tempi, 0.5)} s, p90 {_p(tempi, 0.9)} s; somiglianza p50 "
          f"{_p([r['somiglianza'] for r in risultati], 0.5)}")
    scelti = ([r for r in risultati if r["cambiato"]] + [r for r in risultati
                                                          if not r["cambiato"]])[:o.n]
    scelti.sort(key=lambda r: r["b"][0]["inizio"])
    casi = []
    for n, r in enumerate(scelti, 1):
        b = r["b"]
        pause = [round(max(0.0, b[i + 1]["inizio"] - b[i]["fine"]), 1) for i in range(len(b) - 1)]
        casi.append({
            "n": n, "quando": datetime.datetime.fromtimestamp(b[0]["inizio"]).strftime(
                "%Y-%m-%d %H:%M:%S"),
            "satellite": b[0]["sat"], "durata": f"{len(r['audio']) / SR:.1f} s".replace(".", ","),
            "segmenti": [s["rel"] for s in b], "pause": " · ".join(f"{x:g} s" for x in pause),
            "chiusura": motivi.get(id(b), ""), "allora": r["allora"], "blocco": r["testo"],
            "ripresa": r["ripresa"], "cambiato": r["cambiato"],
            "audio": base64.b64encode(wav_pcm16(r["audio"])).decode("ascii")})
    ora = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    out = Path(o.html) if o.html else RADICE / "privato" / f"revisione-blocchi-{ora}.html"
    scrivi_privato(out, pagina(casi, f"revisione-blocchi-{ora}"))
    print(f"\nPagina di revisione con {len(casi)} blocchi: {out} "
          f"({out.stat().st_size / 1e6:.1f} MB; voci vere: non metterla nel repository)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
