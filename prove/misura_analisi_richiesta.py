import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Misura dell'analisi della richiesta (06/10, calliope/agenti/richiesta.py) sul banco di
prove/banco_richieste.py, con il modello vero dell'agente. Manuale, non nel runner.

    python prove/misura_analisi_richiesta.py --url http://127.0.0.1:11446/v1 --modello qwen3.6-35b
    python prove/misura_analisi_richiesta.py ... --giri 3 --solo E1,E11 --json esiti.json

`--url` con «/v1» = server compatibile OpenAI (vLLM), senza = API nativa di Ollama. La fonte web
si verifica davvero (rete pubblica di Calliope: serve internet), salvo `--senza-rete`. Il
tempo massimo è quello della configurazione (`--tempo`, 10 s).

Stampa per caso esito, punti mancanti, domande o specifica, fonte e tempo; poi gli obiettivi:
vaghe prese (≥ 80 %), domande inutili sulle chiare (≤ 10 %), raffinabili, «c'è già»,
«impossibile qui», tempo mediano, p90 e massimo, ripieghi (tempo scaduto o errore)."""

import argparse
import json
import statistics
import tempfile
import time
from types import SimpleNamespace

from calliope.agenti import carica
from calliope.agenti import richiesta as ar
from calliope.agenti.remoto import crea_cliente
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from calliope.tools.builtin import build_registry
from calliope.tools.estensioni import estensioni_specs
from prove.banco_richieste import CASI, FUORI


def registro():
    """I tool di un'installazione tipica (casa, liste, agenda, documenti, web, agenti)."""
    reg = build_registry(documenti=FORMATI, agenti=True, casa=True, schermi=True,
                         archivio=True, conversazioni=True, web=Config())
    for s in estensioni_specs():
        reg.register(s)
    return reg


def giusto(atteso: str, e: ar.Esito) -> bool:
    if atteso == "chiara_o_vaga":
        return (e.esito == "chiara" and e.fonte_ok is True) or (
            e.esito == "vaga" and e.fonte_ok is not True)
    return e.esito == atteso


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--modello", required=True)
    ap.add_argument("--giri", type=int, default=1)
    ap.add_argument("--solo", default="")
    ap.add_argument("--tempo", type=float, default=10.0)
    ap.add_argument("--senza-rete", action="store_true")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    cfg = Config()
    cfg.agenti_url, cfg.agenti_modello = a.url, a.modello
    cfg.agenti_analisi_s = a.tempo
    cfg.estensioni_cartella = tempfile.mkdtemp(prefix="calliope-misura-analisi-")
    imp = carica(cfg)
    lavori = SimpleNamespace(imp=imp, cliente=crea_cliente(imp, timeout_lettura=60.0),
                             arbitro=None, isolamenti={"python": 1, "csharp": 1}, agente=None)
    an = ar.Analizzatore(cfg, lavori)
    if a.senza_rete:
        an.verifica_fonte = lambda url, t: None
    reg = registro()
    solo = {x.strip() for x in a.solo.split(",") if x.strip()}
    righe = []
    for giro in range(a.giri):
        for cid, tipo, testo, storia, atteso, nota in CASI:
            if solo and cid not in solo:
                continue
            e = an.analizza(tipo, testo, storia, testo, reg)
            ok = giusto(atteso, e)
            righe.append({"id": cid, "giro": giro, "atteso": atteso, "ok": ok, **e.per_registro(),
                          "nome": e.nome, "fonte_url": e.fonte_url, "motivo": e.motivo,
                          "come": e.come_chiederlo})
            det = (" | ".join(e.domande) if e.esito == "vaga" else e.specifica if e.esito in (
                "chiara", "raffinabile") else f"{e.tool}: {e.come_chiederlo}"
                if e.esito == "gia_fatto" else e.motivo or e.errore)
            fonte = f" fonte={e.fonte_url} ({e.fonte_ok})" if e.fonte_url else ""
            print(f"{'ok ' if ok else 'NO '} {cid:4} {atteso:13} → {e.esito:11} {e.secondi:5.2f}s "
                  f"mancano={','.join(e.mancano) or '-'}{fonte}\n      {det}", flush=True)
    for fid, tipo, testo in FUORI:
        print(f"--  {fid:4} fuori ambito ({tipo}): l'analizzatore non è chiamato")

    def quota(filtro, cond):
        sel = [r for r in righe if filtro(r)]
        return sum(1 for r in sel if cond(r)), len(sel)
    print("\n— obiettivi")
    p, n = quota(lambda r: r["atteso"] == "vaga", lambda r: r["esito"] == "vaga")
    print(f"vaghe prese: {p}/{n} ({100 * p / max(1, n):.0f} %, obiettivo ≥ 80 %)")
    p, n = quota(lambda r: r["atteso"] == "chiara", lambda r: r["esito"] == "vaga")
    print(f"domande inutili sulle chiare: {p}/{n} ({100 * p / max(1, n):.0f} %, obiettivo ≤ 10 %)")
    p, n = quota(lambda r: r["atteso"] == "raffinabile", lambda r: r["esito"] == "vaga")
    print(f"domande sulle raffinabili (il contesto bastava): {p}/{n}")
    for et in ("chiara", "raffinabile", "gia_fatto", "impossibile", "chiara_o_vaga"):
        p, n = quota(lambda r, et=et: r["atteso"] == et, lambda r: r["ok"])
        print(f"{et}: {p}/{n} giuste")
    p, n = quota(lambda r: True, lambda r: r["ok"])
    print(f"in tutto: {p}/{n} giuste")
    tempi = sorted(r["s"] for r in righe)
    if tempi:
        p90 = tempi[min(len(tempi) - 1, int(0.9 * len(tempi)))]
        print(f"tempo: mediana {statistics.median(tempi):.2f} s, p90 {p90:.2f} s, "
              f"massimo {tempi[-1]:.2f} s")
    rip = [r for r in righe if r["esito"] == "nessuna"]
    print(f"ripieghi (tempo scaduto o errore): {len(rip)}"
          + (f" — {rip[0].get('errore')}" if rip else ""))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(righe, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
