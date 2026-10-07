"""
Attrito della politica di sicurezza sul registro dei turni (07/10/2026,
docs/ricerche/2026-10-07-sicurezza-per-valore.md § 2).

Legge una cartella di `turni-*.jsonl` (il registro dei turni, calliope/turnlog.py) e stampa, per
giorno, solo numeri aggregati: turni con una frase, domande di sicurezza (conferme, sfide,
«non me l'hai chiesto», blocchi, frasi fermate da riferire), le stesse per regola, per tool e
per fonte del dato di mezzo, quante sono state seguite dall'esecuzione dello stesso tool entro
tre turni (la persona voleva l'azione: indizio di falso positivo), quante si ripetono per lo
stesso tool entro 5 minuti, e le frasi del tipo «te l'ho già detto». Nessun testo esce: le
frasi restano dove sono. La classificazione a mano del documento è fatta a parte.

Uso:  python attrito.py CARTELLA_DEL_REGISTRO [giorno ...]   (giorno = 2026-10-07)
"""

import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

DOMANDE = {
    "politica_conferma", "politica_sfida", "politica_azione_non_chiesta",
    "politica_azione_non_giustificata", "politica_argomento_esterno",
    "politica_argomento_non_detto", "politica_delega", "politica_cancellazione_non_chiesta",
    "politica_cambio_non_chiesto", "politica_azione_incoerente", "politica_bersaglio_assente",
    "azione_non_chiesta", "immagine_azione_non_chiesta", "web_azione_bloccata"}
RIFERIRE = {"uscita_istruzione", "uscita_contatto", "uscita_segreti", "uscita_soldi",
            "uscita_numero_pagamento"}
FONTI = {"una pagina internet": "web", "una foto": "foto", "il lavoro di un agente": "agente",
         "il risultato di un'estensione": "estensione", "un file allegato": "allegato",
         "un audio allegato": "audio", "un documento dell'archivio": "archivio",
         "una pagina scaricata": "pagina"}
GIA_DETTO = re.compile(r"quante volte|già detto|gia detto|ti ho detto|te l.ho detto|"
                       r"ho detto di s[iì]|me lo chiedi", re.I)


def _tool(r):
    return [(t.get("nome") or t.get("name"), t.get("ok")) for t in (r.get("tool") or [])
            if isinstance(t, dict)]


def giorno(path: Path) -> dict:
    righe = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    out = collections.Counter()
    per_regola, per_tool, per_fonte = (collections.Counter() for _ in range(3))
    ultima = {}
    for i, r in enumerate(righe):
        if (r.get("testo") or "").strip() and r.get("esito") == "risposta":
            out["turni"] += 1
        if GIA_DETTO.search(r.get("testo") or ""):
            out["gia_detto"] += 1
        reg = set(r.get("regole") or [])
        risposta = (r.get("risposta") or "")
        sfida = "sfida_voce" in reg and "ripeti" in risposta.lower()
        d, u = reg & DOMANDE, reg & RIFERIRE
        if not (d or u or sfida):
            continue
        out["domande"] += 1
        out["riferire"] += bool(u)
        out["sfide"] += sfida
        for x in sorted(d | u):
            per_regola[x] += 1
        for nome, fonte in FONTI.items():
            if f"di mezzo {nome}" in risposta:
                per_fonte[fonte] += 1
        fermati = [t for t, ok in _tool(r) if not ok]
        if not d or not fermati:
            continue
        tool = fermati[-1]
        per_tool[tool] += 1
        t0 = dt.datetime.fromisoformat(str(r["inizio"]))
        if tool in ultima and (t0 - ultima[tool]).total_seconds() < 300:
            out["ripetute_5min"] += 1
        ultima[tool] = t0
        if any(t == tool and ok for rr in righe[i + 1:i + 4] for t, ok in _tool(rr)):
            out["poi_eseguite"] += 1
    return {"conti": dict(out), "regole": dict(per_regola), "tool": dict(per_tool),
            "fonti": dict(per_fonte)}


def main():
    cartella = Path(sys.argv[1])
    giorni = sys.argv[2:]
    for f in sorted(cartella.glob("turni-*.jsonl")):
        g = f.stem[len("turni-"):]
        if giorni and g not in giorni:
            continue
        ris = giorno(f)
        c = ris["conti"]
        turni = max(1, c.get("turni", 0))
        print(f"{g}: {c.get('turni', 0)} turni, {c.get('domande', 0)} domande di sicurezza "
              f"({100 * c.get('domande', 0) / turni:.1f} ogni 100 turni), "
              f"poi eseguite {c.get('poi_eseguite', 0)}, ripetute entro 5 min "
              f"{c.get('ripetute_5min', 0)}, «già detto» {c.get('gia_detto', 0)}")
        for k in ("regole", "tool", "fonti"):
            if ris[k]:
                print(f"   {k}: " + ", ".join(f"{a} {b}" for a, b in
                                             sorted(ris[k].items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
