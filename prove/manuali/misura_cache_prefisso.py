"""La cache del prefisso dal registro dei turni della DGX, prima e dopo (16/10/2026, issue #95).

Sola lettura del registro dei turni (`turni-*.jsonl`), nessun modello, solo numeri: niente frasi,
nomi o voci. Per ogni gruppo di turni (`--dal` divide in «prima» e «dopo»; senza, un gruppo per
giorno):

- **cache persa**: turni in cui il motore ha riletto molto più dei messaggi cambiati
  (`cache.riletti` oltre 1,3 × `cache.riletti_stimati` + 300, come `latenza.cache_persa`), la
  quota sui turni con la misura;
- **punto fisso**: fra turni consecutivi della stessa conversazione (stessa voce entro
  `--pausa` secondi), quante volte i token ripresi dalla cache (`cache.ripresi`, o contesto −
  riletti nei registri di prima del 16/10) restano quasi fermi (crescono meno di 0,3 volte il
  contesto, cresciuto di almeno 100): è il segno del motore che riparte sempre dallo stesso
  checkpoint;
- la cache persa divisa fra i turni **dopo un turno con un tool** della stessa voce (la richiesta
  di prima è la seconda passata, più lunga) e quelli dopo un turno senza;
- mediana del rapporto `riletti / riletti_stimati`, rilettura (`lettura_s`) mediana e p90, prima
  frase mediana e p90;
- i **dati del turno** (`dati_turno_token`, dal 16/10) mediana, p90 e turni oltre il tetto, e i
  turni con i dati fissi rifatti (regola `dati_stabili_rifatti`).

I criteri di chiusura dell'issue #95: mediana `riletti/riletti_stimati` ≤ 1,3, `lettura_s` p90
≤ 1,2 s, nessun punto fisso, «cache persa» sotto il 10 % dei turni, prima frase mediana ≤ 1,5 s.

Sulla DGX:

    cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale) \\
        && $V/.venv/bin/python $V/prove/manuali/misura_cache_prefisso.py --giorni 3 \\
           --dal 2026-10-16T12:00

`--cartella` sceglie un'altra cartella del registro (di serie `registro` nella cartella di
lavoro, come `turn_log_dir`); `--prova` gira su turni finti, a secco.
"""

import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from calliope import latenza  # noqa: E402

# Ripresi «fermi»: il contesto cresce di almeno CRESCE token e i ripresi di meno di FERMO volte
# tanto (con la cache che regge crescono quasi quanto il contesto; col punto fisso restano lì)
FERMO = 0.3
CRESCE = 100


def _quando(t):
    try:
        return datetime.datetime.fromisoformat(str(t.get("inizio"))).timestamp()
    except (TypeError, ValueError):
        return None


def _chi(t):
    v = t.get("voce") if isinstance(t.get("voce"), dict) else {}
    return v.get("id") or v.get("nome") or "?"


def _ripresi(t):
    c = t.get("cache") if isinstance(t.get("cache"), dict) else {}
    if isinstance(c.get("ripresi"), int):
        return c["ripresi"]
    tok = (t.get("contesto") or {}).get("token") if isinstance(t.get("contesto"), dict) else None
    if isinstance(tok, int) and isinstance(c.get("riletti"), int) and not t.get("tool"):
        return tok - c["riletti"]     # registri di prima: solo i turni senza tool (una passata)
    return None


def misura(turni: list[dict], pausa_s: float = 300.0) -> dict:
    r = [t for t in turni if t.get("esito") == "risposta"
         and isinstance(t.get("prima_frase_s"), (int, float))]
    persa = [x for x in (latenza.cache_persa(t) for t in r) if x is not None]
    rapporti = []
    for t in r:
        c = t.get("cache") if isinstance(t.get("cache"), dict) else {}
        if (not c.get("prima") and isinstance(c.get("riletti"), int)
                and isinstance(c.get("riletti_stimati"), int) and c["riletti_stimati"] > 0):
            rapporti.append(c["riletti"] / c["riletti_stimati"])
    letture = [x for x in (latenza._lettura(t) for t in r) if x is not None]
    pf = [t["prima_frase_s"] for t in r]
    dati = [t["dati_turno_token"] for t in r if isinstance(t.get("dati_turno_token"), int)]
    # Il punto fisso, fra turni consecutivi della stessa voce
    coppie = fermi = 0
    ultimo: dict = {}
    # La cache persa divisa fra i turni dopo un turno con un tool della stessa voce (la richiesta
    # di prima è la seconda passata, con la chiamata e il risultato) e gli altri
    dopo_tool = {"n": 0, "perse": 0}
    senza_tool = {"n": 0, "perse": 0}
    for t in sorted(r, key=lambda x: str(x.get("inizio") or "")):
        q, chi = _quando(t), _chi(t)
        rip = _ripresi(t)
        tok = (t.get("contesto") or {}).get("token") if isinstance(t.get("contesto"), dict) \
            else None
        prec = ultimo.get(chi)
        cp = latenza.cache_persa(t)
        if cp is not None and prec and q is not None and prec["q"] is not None                 and q - prec["q"] <= pausa_s:
            gruppo = dopo_tool if prec["tool"] else senza_tool
            gruppo["n"] += 1
            gruppo["perse"] += int(cp)
        if (prec and q is not None and prec["q"] is not None and q - prec["q"] <= pausa_s
                and rip is not None and prec["rip"] is not None
                and isinstance(tok, int) and isinstance(prec["tok"], int)
                and not (t.get("cache") or {}).get("prima")):
            coppie += 1
            cresce = tok - prec["tok"]
            if cresce >= CRESCE and rip - prec["rip"] <= FERMO * cresce:
                fermi += 1
        ultimo[chi] = {"q": q, "rip": rip, "tok": tok, "tool": bool(t.get("tool"))}
    return {
        "risposte": len(r),
        "cache": {"n": len(persa), "perse": sum(persa),
                  "quota": round(sum(persa) / len(persa), 3) if persa else None},
        "riletti_su_stimati": {"n": len(rapporti), "mediana": latenza._med(rapporti)},
        "punto_fisso": {"coppie": coppie, "fermi": fermi},
        "dopo_tool": dopo_tool, "senza_tool": senza_tool,
        "lettura": {"n": len(letture), "mediana": latenza._med(letture),
                    "p90": latenza._q(letture, .9)},
        "prima_frase": {"mediana": latenza._med(pf), "p90": latenza._q(pf, .9)},
        "dati_turno": {"n": len(dati), "mediana": latenza._med(dati), "p90": latenza._q(dati, .9),
                       "oltre": sum(1 for t in r if t.get("dati_turno_oltre"))},
        "rifatti": sum(1 for t in r if "dati_stabili_rifatti" in (t.get("regole") or ())),
    }


def _n(x, f="{:.2f}"):
    return "—" if x is None else f.format(x).replace(".", ",")


def testo(nome: str, m: dict) -> str:
    c, rs, pfx, le, pf, dt = (m["cache"], m["riletti_su_stimati"], m["punto_fisso"],
                              m["lettura"], m["prima_frase"], m["dati_turno"])
    righe = [f"{nome}: {m['risposte']} risposte",
             f"  cache del prefisso persa in {c['perse']} turni su {c['n']}"
             + (f" ({_n(100 * c['quota'], '{:.0f}')} %)" if c["quota"] is not None else ""),
             f"  dopo un turno con un tool persa in {m['dopo_tool']['perse']} su "
             f"{m['dopo_tool']['n']}, dopo un turno senza in {m['senza_tool']['perse']} su "
             f"{m['senza_tool']['n']}",
             f"  riletti/stimati mediana {_n(rs['mediana'])} su {rs['n']} turni; punto fisso "
             f"in {pfx['fermi']} coppie di turni su {pfx['coppie']}",
             f"  rilettura mediana {_n(le['mediana'])} s, p90 {_n(le['p90'])} s; prima frase "
             f"mediana {_n(pf['mediana'])} s, p90 {_n(pf['p90'])} s"]
    if dt["n"]:
        righe.append(f"  dati del turno {_n(dt['mediana'], '{:.0f}')} token (p90 "
                     f"{_n(dt['p90'], '{:.0f}')}), oltre il tetto in {dt['oltre']} turni; dati "
                     f"fissi rifatti in {m['rifatti']} turni")
    return "\n".join(righe)


def _finti() -> list[dict]:
    """Due conversazioni finte: prima il punto fisso (ripresi fermi, riletti che crescono),
    dopo la cache che regge."""
    out = []
    t0 = datetime.datetime(2026, 10, 15, 18, 0)
    for i in range(10):
        tok = 18000 + 600 * i
        out.append({"inizio": (t0 + datetime.timedelta(seconds=40 * i)).isoformat(),
                    "esito": "risposta", "prima_frase_s": 2.5 + i / 10, "lettura_s": 1.0 + i / 5,
                    "voce": {"id": "a"}, "contesto": {"token": tok},
                    "cache": ({"prima": True} if i == 0 else
                              {"riletti": tok - 18000, "riletti_stimati": 1500})})
    t1 = datetime.datetime(2026, 10, 16, 18, 0)
    for i in range(10):
        tok = 18000 + 600 * i
        out.append({"inizio": (t1 + datetime.timedelta(seconds=40 * i)).isoformat(),
                    "esito": "risposta", "prima_frase_s": 1.1, "lettura_s": 0.2,
                    "voce": {"id": "a"}, "contesto": {"token": tok}, "dati_turno_token": 120,
                    "cache": ({"prima": True} if i == 0 else
                              {"riletti": 450, "riletti_stimati": 400, "ripresi": tok - 450})})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cartella", default="registro")
    ap.add_argument("--giorni", type=int, default=3)
    ap.add_argument("--dal", default="", help="ISO: i turni da qui sono «dopo», prima «prima»")
    ap.add_argument("--pausa", type=float, default=300.0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--prova", action="store_true", help="a secco, su turni finti")
    a = ap.parse_args()
    turni = _finti() if a.prova else latenza.leggi(a.cartella, a.giorni)
    dal = "2026-10-16" if a.prova and not a.dal else a.dal
    if dal:
        gruppi = {"prima": [t for t in turni if str(t.get("inizio") or "") < dal],
                  "dopo": [t for t in turni if str(t.get("inizio") or "") >= dal]}
    else:
        gruppi = {}
        for t in turni:
            gruppi.setdefault(str(t.get("inizio") or "")[:10], []).append(t)
    ordine = sorted(gruppi, key=lambda k: (k != "prima", k))
    ris = {k: misura(gruppi[k], a.pausa) for k in ordine if gruppi[k]}
    if a.json:
        print(json.dumps(ris, ensure_ascii=False, indent=1))
    else:
        for k, m in ris.items():
            print(testo(k, m) + "\n")
    if a.prova:
        p, d = ris.get("prima"), ris.get("dopo")
        ok = (p and d and p["punto_fisso"]["fermi"] >= 8 and d["punto_fisso"]["fermi"] == 0
              and p["cache"]["perse"] >= 5 and d["cache"]["perse"] == 0)
        print("prova a secco:", "ok" if ok else "ERRORE")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
