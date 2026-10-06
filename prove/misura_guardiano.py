"""
Misura dei modelli guardiani in italiano (05/10, docs/ricerche/2026-10-05-minori.md §4).

    python prove/misura_guardiano.py llama-guard3:1b [shieldgemma:2b …] [--url URL] [--giri 2]
        [--json uscita.json] [--adattatore llama_guard_std]

Per ogni modello: i casi di prove/casi_guardiano.py (domande e frasi di risposta), l'esito
(ok / vietato / pericolo) contro l'atteso, e il tempo di ogni giudizio (prima un giudizio di
riscaldamento). Riassunto:
- pericolo: quante domande di pericolo riconosciute (deve essere alto) e quante domande
  normali prese per pericolo (deve essere ~0);
- risposte: quante frasi vietate fermate e quante frasi giuste fermate per sbaglio;
- tempo mediano e p90 di un giudizio (il costo sulla prima frase).
"""

import json
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from calliope import guardiano as G  # noqa: E402
from prove.casi_guardiano import CASI  # noqa: E402


def misura(modello: str, url: str, giri: int, adattatore: str | None = None) -> dict:
    cfg = SimpleNamespace(guardiano_modello=modello, guardiano_url=url, guardiano_timeout_s=60,
                          guardiano_keep_alive="10m", guardiano_num_ctx=2048,
                          guardiano_enabled=True)
    g = G.Guardiano(cfg)
    if adattatore:
        g.adattatore = {"llama_guard_std": G.LlamaGuardStd(), "llama_guard": G.LlamaGuard(),
                        "qwen3guard": G.QwenGuard(), "shieldgemma": G.ShieldGemma(),
                        "granite": G.GraniteGuardian()}[adattatore]
    g.giudica("Ciao, come stai?")                         # caricamento
    righe, tempi = [], []
    for giro in range(giri):
        for cid, dom, ris, atteso in CASI:
            gz = g.giudica(dom, ris)
            tempi.append(gz.ms)
            esito = gz.esito
            if ris is None and atteso == "vietato":
                giusto = esito in ("vietato", "pericolo")
            else:
                giusto = esito == atteso
            righe.append({"id": cid, "giro": giro, "atteso": atteso, "esito": esito,
                          "cat": list(gz.categorie), "ms": gz.ms, "giusto": giusto,
                          "grezzo": gz.grezzo})
    p = [r for r in righe if r["id"].startswith("p_")]
    d_ok = [r for r in righe if r["id"].startswith("d_") and r["atteso"] == "ok"]
    d_v = [r for r in righe if r["id"].startswith("d_") and r["atteso"] == "vietato"]
    v = [r for r in righe if r["id"].startswith("v_")]
    r_ok = [r for r in righe if r["id"].startswith("r_")]
    q = sorted(tempi)
    out = {
        "modello": modello + (f" ({adattatore})" if adattatore else ""),
        "pericolo_trovati": f"{sum(r['esito'] == 'pericolo' for r in p)}/{len(p)}",
        "pericolo_o_vietato": f"{sum(r['esito'] in ('pericolo', 'vietato') for r in p)}/{len(p)}",
        "domande_ok_prese_per_pericolo": f"{sum(r['esito'] == 'pericolo' for r in d_ok)}/{len(d_ok)}",
        "domande_ok_segnate": f"{sum(r['esito'] != 'ok' for r in d_ok)}/{len(d_ok)}",
        "domande_vietate_segnate": f"{sum(r['esito'] != 'ok' for r in d_v)}/{len(d_v)}",
        "risposte_vietate_fermate": f"{sum(r['esito'] != 'ok' for r in v)}/{len(v)}",
        "risposte_giuste_fermate": f"{sum(r['esito'] != 'ok' for r in r_ok)}/{len(r_ok)}",
        "ms_mediana": round(statistics.median(q), 1),
        "ms_p90": round(q[int(len(q) * 0.9) - 1], 1),
        "ms_max": round(q[-1], 1),
        "sbagliati": sorted({f"{r['id']}→{r['esito']}" for r in righe if not r["giusto"]}),
    }
    g.close()
    return {"riassunto": out, "righe": righe}


def main():
    args = sys.argv[1:]
    url = "http://127.0.0.1:11434"
    giri, uscita, adatt = 1, None, None
    if "--url" in args:
        i = args.index("--url"); url = args[i + 1]; del args[i:i + 2]
    if "--giri" in args:
        i = args.index("--giri"); giri = int(args[i + 1]); del args[i:i + 2]
    if "--json" in args:
        i = args.index("--json"); uscita = args[i + 1]; del args[i:i + 2]
    if "--adattatore" in args:
        i = args.index("--adattatore"); adatt = args[i + 1]; del args[i:i + 2]
    tutti = []
    for m in args:
        t0 = time.perf_counter()
        r = misura(m, url, giri, adatt)
        tutti.append(r)
        print(json.dumps(r["riassunto"], ensure_ascii=False, indent=1))
        print(f"   ({time.perf_counter() - t0:.0f} s)", flush=True)
    if uscita:
        Path(uscita).write_text(json.dumps(tutti, ensure_ascii=False, indent=1),
                                encoding="utf-8")


if __name__ == "__main__":
    main()
