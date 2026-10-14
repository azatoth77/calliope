"""Valutazione a secco della fine del turno System 1 sulla voce conservata (14/10/2026,
calliope/system1/fine_turno.py; ricerca docs/ricerche/2026-10-14-system1-fine-turno.md).

Da lanciare **sulla DGX**, nella cartella dei dati, con l'interprete di Calliope (prima, una
volta, il modello: `calliope stato --installa modello_fine_turno`, 8,7 MB):

    cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale) \\
        && $V/.venv/bin/python -m calliope.stato --installa modello_fine_turno \\
        && $V/.venv/bin/python $V/prove/manuali/fine_turno_dgx.py [--giorni N] [--json FILE]

Rigioca le frasi conservate (decisione 0028: la voce dei soli adulti riconosciuti che hanno
detto sì, `<turn_log_dir>/voce/…`, il turno la indica con `voce_file`) come farebbe l'ombra:
Silero VAD in ONNX ritrova le pause con la regola di `Listener.listen`, e a
`fine_turno_sonda_ms` di ogni pausa Smart Turn dice la probabilità che il turno sia finito.
Le pause **interne** (la persona ha continuato) sono i «non finito» veri; la **chiusura** è un
«finito» vero se nessuno ha ripreso entro 2 s (`ascolto.ripresa_s`, `OsservaRipresa`: solo per
il portatile in locale e i satelliti in Python), altrimenti un taglio del silenzio fisso.

Stampa, **solo numeri** (mai parole, nomi o percorsi di file):
- l'accordo del modello a 0,5 con ciò che è successo (pause interne e chiusure), per canale;
- per una griglia di soglie e di parlato minimo: frasi chiuse prima e ms risparmiati, frasi
  che avrebbe tagliato (pausa interna presa per la fine), «finito» con la ripresa, attese più
  lunghe (tagli evitati, attese inutili);
- i tempi del decisore sulla CPU della DGX (p50, p90).
Non scrive niente nel registro né nella configurazione; `--json` salva i numeri dove si dice.
"""

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from calliope import latenza  # noqa: E402
from calliope.conserva import CARTELLA_VOCE, leggi_wav  # noqa: E402
from calliope.system1 import fine_turno as ft  # noqa: E402

SOGLIE = (0.5, 0.7, 0.8, 0.9, 0.95, 0.98)
MIN_PARLATO = (0, 800, 1200)


def _canale(t: dict) -> str:
    a = t.get("ascolto") or {}
    return a.get("canale") or "?"


def rigioca(cfg, turni, limite=None, log=print):
    """Per ogni turno con la voce conservata: le sonde (a_ms, pausa_ms, p) e la chiusura."""
    from calliope.vad import SileroOnnx, carica_vad, modello_onnx
    p = modello_onnx(getattr(cfg, "vad_modello", None))
    vad = SileroOnnx(p) if p is not None else carica_vad(cfg.vad_motore, cfg.vad_modello)
    dec = ft.carica(cfg, log)
    if dec is None:
        return None
    base = Path(cfg.turn_log_dir) / CARTELLA_VOCE
    # Una politica che chiede sempre (la soglia si sceglie dopo, sui numeri)
    pol = ft.Politica(silence_ms=int(cfg.silence_ms), sonda_ms=int(cfg.fine_turno_sonda_ms),
                      soglia=0.5, soglia_attesa=0.5, attesa_max_ms=int(cfg.fine_turno_attesa_max_ms),
                      min_parlato_ms=0)
    out, ms = [], []
    for t in turni:
        f = t.get("voce_file")
        if not f or not isinstance(t.get("ascolto"), dict):
            continue
        try:
            audio, sr = leggi_wav(base / f)
        except (OSError, ValueError):
            continue
        if sr != ft.SR:
            continue
        inizio, flag = ft.silenzi(audio, vad, float(cfg.vad_threshold))

        def decide(x):
            d = dec.decide(x)
            ms.append(d.ms)
            return d
        sim = ft.simula(audio, decide, pol, inizio, flag)
        a = t["ascolto"]
        out.append({"canale": _canale(t), "ripresa_s": a.get("ripresa_s"),
                    "chiusura_vad": a.get("chiusura"), "segnale": bool(a.get("inizio_ripresa")),
                    "interne": [(i["a_ms"], i["p"]) for i in sim["interne"]],
                    "chiusura": (sim["chiusura"]["a_ms"], sim["chiusura"]["p"])
                    if sim.get("chiusura") else None})
        if limite and len(out) >= limite:
            break
    return out, ms


def accordo(frasi) -> dict:
    """A 0,5: pause interne dette «non finito», chiusure senza ripresa dette «finito»."""
    per = {}
    for f in frasi:
        g = per.setdefault(f["canale"], {"interne": 0, "interne_ok": 0, "chiusure": 0,
                                         "chiusure_ok": 0, "riprese": 0, "riprese_ok": 0})
        for _, p in f["interne"]:
            g["interne"] += 1
            g["interne_ok"] += p < 0.5
        if f["chiusura"]:
            p = f["chiusura"][1]
            if f["ripresa_s"] is None and not f["segnale"]:
                g["chiusure"] += 1
                g["chiusure_ok"] += p >= 0.5
            else:
                g["riprese"] += 1
                g["riprese_ok"] += p < 0.5
    return per


def griglia(frasi, cfg, ms_decisore: float = 0.0) -> list[dict]:
    """Gli esiti per ogni soglia e parlato minimo; il risparmio toglie i ms del decisore."""
    righe = []
    for s in SOGLIE:
        for mp in MIN_PARLATO:
            pol = ft.Politica(silence_ms=int(cfg.silence_ms), sonda_ms=int(cfg.fine_turno_sonda_ms),
                              soglia=s, soglia_attesa=s,
                              attesa_max_ms=int(cfg.fine_turno_attesa_max_ms), min_parlato_ms=mp)
            conta = {k: 0 for k in ft.ESITI}
            risparmio = costo = 0
            for f in frasi:
                sim = {"sonde": 1, "interne": [{"a_ms": a, "p": p} for a, p in f["interne"]],
                       "taglio_ms": next((a for a, p in f["interne"] if p is not None
                                          and pol.verdetto(ft.Decisione(
                                              ft.FINITO if p >= .5 else ft.NON_FINITO,
                                              p if p >= .5 else 1 - p), a) == "chiudi"), None),
                       "chiusura": None}
                if f["chiusura"] and f["chiusura"][1] is not None:
                    a, p = f["chiusura"]
                    d = ft.Decisione(ft.FINITO if p >= .5 else ft.NON_FINITO,
                                     p if p >= .5 else 1 - p, 0.0)
                    sim["chiusura"] = {"a_ms": a, "p": p, "verdetto": pol.verdetto(d, a),
                                       "ms": ms_decisore}
                e = ft.esito(sim, f["ripresa_s"], pol)
                conta[e["esito"]] += 1
                risparmio += e.get("risparmio_ms", 0)
                costo += e.get("costo_ms", 0)
            righe.append({"soglia": s, "min_parlato_ms": mp, "esiti": conta,
                          "risparmio_s": round(risparmio / 1000, 1), "costo_s": round(costo / 1000, 1)})
    return righe


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fine del turno System 1 sulla voce conservata")
    ap.add_argument("--giorni", type=int, default=None)
    ap.add_argument("--limite", type=int, default=None, help="al più tante frasi")
    ap.add_argument("--json", default=None, help="salva i numeri in questo file")
    args = ap.parse_args(argv)
    from calliope.config import load_config
    cfg = load_config()
    turni = latenza.leggi(cfg.turn_log_dir, args.giorni)
    con_voce = sum(1 for t in turni if t.get("voce_file"))
    print(f"Turni nel registro: {len(turni)}, con la voce conservata: {con_voce}")
    t0 = time.monotonic()
    r = rigioca(cfg, turni, args.limite)
    if r is None:
        return 1
    frasi, ms = r
    print(f"Frasi rigiocate: {len(frasi)} in {time.monotonic() - t0:.1f} s; pause interne "
          f"{sum(len(f['interne']) for f in frasi)}, chiusure "
          f"{sum(1 for f in frasi if f['chiusura'])}, con la ripresa misurata "
          f"{sum(1 for f in frasi if f['ripresa_s'] is not None)}")
    if ms:
        q = sorted(ms)
        print(f"Decisore sulla CPU: p50 {q[len(q) // 2]:.0f} ms, p90 {q[int(.9 * len(q))]:.0f} "
              f"ms, media {statistics.mean(q):.0f} ms ({len(q)} domande)")
    acc = accordo(frasi)
    print("\nAccordo a 0,5 (giusti/totale):")
    for c, g in sorted(acc.items()):
        print(f"  {c}: pause interne «non finito» {g['interne_ok']}/{g['interne']}, chiusure "
              f"«finito» {g['chiusure_ok']}/{g['chiusure']}, riprese «non finito» "
              f"{g['riprese_ok']}/{g['riprese']}")
    righe = griglia(frasi, cfg, sorted(ms)[len(ms) // 2] if ms else 0.0)
    print(f"\nGriglia (sonda {cfg.fine_turno_sonda_ms} ms, silenzio fisso {cfg.silence_ms} ms, "
          f"attesa fino a {cfg.fine_turno_attesa_max_ms} ms):")
    print("  soglia  min_parl  prima  risparmio  tagli  fin+ripr  att.lunghe  evitati  "
          "costo  come_prima")
    for x in righe:
        e = x["esiti"]
        print(f"  {x['soglia']:<6}  {x['min_parlato_ms']:>8}  {e['anticipo']:>5}  "
              f"{x['risparmio_s']:>7} s  {e['taglio']:>5}  {e['anticipo_ripresa']:>8}  "
              f"{e['attesa'] + e['taglio_evitato']:>10}  {e['taglio_evitato']:>7}  "
              f"{x['costo_s']:>4} s  {e['come_prima']:>10}")
    if args.json:
        Path(args.json).write_text(json.dumps({"frasi": len(frasi), "accordo": acc,
                                               "griglia": righe,
                                               "decisore_ms": {"p50": q[len(q) // 2] if ms else None}},
                                              ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nNumeri salvati in {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
