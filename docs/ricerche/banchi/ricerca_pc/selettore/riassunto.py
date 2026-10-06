"""Riassunto dei risultati del banco del selettore: accuratezza, «nessuno», calibrazione,
trappole, latenza. Legge risultati/sel_*.jsonl e scrive risultati/riassunto.json + tabelle
in markdown su stdout.
"""

import json
import statistics
from pathlib import Path

QUI = Path(__file__).resolve().parent
RIS = QUI / "risultati"

GRUPPI = {"barra_applicazioni": "barra", "esplora_download": "esplora",
          "esplora_documenti": "esplora", "blocco_note": "blocco note",
          "impostazioni_home": "impostazioni", "impostazioni_personalizzazione": "impostazioni",
          "impostazioni_audio": "impostazioni", "impostazioni_bluetooth": "impostazioni",
          "vscode": "vscode", "edge": "edge"}


def carica(tag):
    p = RIS / f"sel_{tag}.jsonl"
    return [json.loads(r) for r in p.read_text(encoding="utf-8").splitlines() if r.strip()]


def auroc(pos, neg):
    if not pos or not neg:
        return None
    tot = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return tot / (len(pos) * len(neg))


def pct(x):
    return f"{100 * x:.0f} %"


def calibrazione(righe, soglie=(0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95)):
    """Soglie sulla confidenza: sopra si esegue, sotto si chiede conferma.
    Un «nessuno» sopra soglia vale «non faccio nulla» (giusto o sbagliato come gli altri)."""
    ok = [r for r in righe if r.get("conf") is not None]
    if not ok:
        return None
    giusti = [r["conf"] for r in ok if r["giusto"]]
    sbagli = [r["conf"] for r in ok if not r["giusto"]]
    tab = []
    for s in soglie:
        auto = [r for r in ok if r["conf"] >= s]
        err_auto = sum(1 for r in auto if not r["giusto"])
        tab.append({"soglia": s, "automatiche": len(auto) / len(ok),
                    "accuratezza_automatiche": (len(auto) - err_auto) / len(auto) if auto else None,
                    "errori_automatici": err_auto,
                    "errori_automatici_azione": sum(1 for r in auto if not r["giusto"]
                                                    and r["scelta"] != "nessuno"),
                    "a_conferma": len(ok) - len(auto)})
    return {"auroc": auroc(giusti, sbagli), "tabella": tab}


def riassumi(tag):
    righe = carica(tag)
    n = len(righe)
    ris = [r for r in righe if r["tipo"] != "nessuno"]
    nes = [r for r in righe if r["tipo"] == "nessuno"]
    per_tipo = {t: [r for r in righe if r["tipo"] == t] for t in ("diretto", "passo", "nessuno")}
    per_gruppo = {}
    for r in righe:
        per_gruppo.setdefault(GRUPPI[r["schermata"]], []).append(r)
    ms = sorted(r["ms"] for r in righe)
    tr = {}
    for r in righe:
        if r.get("trappola"):
            tr[r["trappola"]] = tr.get(r["trappola"], 0) + 1
    return {
        "tag": tag, "n": n,
        "accuratezza": sum(r["giusto"] for r in righe) / n,
        "per_tipo": {t: (sum(r["giusto"] for r in v), len(v)) for t, v in per_tipo.items()},
        "per_gruppo": {g: (sum(r["giusto"] for r in v), len(v)) for g, v in per_gruppo.items()},
        "nessuno_detti": sum(1 for r in righe if r["scelta"] == "nessuno"),
        "falsi_nessuno": sum(1 for r in ris if r["scelta"] == "nessuno"),
        "nessuno_giusti": (sum(r["giusto"] for r in nes), len(nes)),
        "non_validi": sum(1 for r in righe if r.get("non_valido")),
        "trappole": tr,
        "ms_mediana": statistics.median(ms), "ms_p95": ms[int(0.95 * (n - 1))],
        "calibrazione": calibrazione(righe, (0.0, 1.0, 1.1, 1.2, 1.25, 1.3)
                                     if tag.startswith("lessicale") else
                                     (0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95)),
    }


def main():
    tags = sorted(p.stem[4:] for p in RIS.glob("sel_*.jsonl"))
    tutti = {t: riassumi(t) for t in tags}
    (RIS / "riassunto.json").write_text(json.dumps(tutti, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    print("| selettore | accuratezza | diretti | passi | nessuno | falsi «nessuno» | "
          "trappole | ms mediana | ms p95 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for t, d in tutti.items():
        pt = d["per_tipo"]
        print(f"| {t} | {pct(d['accuratezza'])} | {pt['diretto'][0]}/{pt['diretto'][1]} | "
              f"{pt['passo'][0]}/{pt['passo'][1]} | {pt['nessuno'][0]}/{pt['nessuno'][1]} | "
              f"{d['falsi_nessuno']} | {sum(d['trappole'].values()) or '–'} "
              f"{d['trappole'] or ''} | {d['ms_mediana']:.0f} | {d['ms_p95']:.0f} |")
    print()
    print("| selettore | " + " | ".join(sorted({g for d in tutti.values()
                                                 for g in d['per_gruppo']})) + " |")
    gruppi = sorted({g for d in tutti.values() for g in d['per_gruppo']})
    print("|---|" + "---|" * len(gruppi))
    for t, d in tutti.items():
        print(f"| {t} | " + " | ".join(f"{d['per_gruppo'][g][0]}/{d['per_gruppo'][g][1]}"
                                        for g in gruppi) + " |")
    print()
    for t, d in tutti.items():
        c = d["calibrazione"]
        if not c:
            continue
        print(f"**{t}**: AUROC {c['auroc']:.2f}" if c["auroc"] is not None else f"**{t}**")
        print("| soglia | eseguite da sole | giuste tra quelle | errori automatici "
              "(di cui azioni) | a conferma |")
        print("|---|---|---|---|---|")
        for r in c["tabella"]:
            acc = "–" if r["accuratezza_automatiche"] is None else pct(r["accuratezza_automatiche"])
            print(f"| {r['soglia']} | {pct(r['automatiche'])} | {acc} | "
                  f"{r['errori_automatici']} ({r['errori_automatici_azione']}) | "
                  f"{r['a_conferma']} |")
        print()


if __name__ == "__main__":
    main()
