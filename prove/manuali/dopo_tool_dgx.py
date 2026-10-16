"""La frase dopo il tool, System 1, sui turni conservati della DGX (15/10/2026,
calliope/system1/dopo_tool.py; roadmap 3.12).

Da lanciare **sulla DGX**, nella cartella dei dati, con l'interprete di Calliope (sola lettura,
nessun modello, si può lanciare con Calliope accesa):

    cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale) \\
        && $V/.venv/bin/python $V/prove/manuali/dopo_tool_dgx.py [--giorni 14]

Rigioca il decisore sul registro dei turni (le parole degli adulti, decisione 0028): per ogni
risposta con tool la frase della persona, i tool chiamati e il loro esito, i segnali di
struttura che il registro ha (proposta aperta, spinte, correzioni, contesto). Il registro **non
ha** il risultato del tool, il testo detto dal modello prima del tool né il tono: un tool riuscito
dell'elenco vale come «con la sua frase» (dal 16/10 anche la lista e l'agenda lette, che il
decisore copre solo fino a due voci: il registro non ha quante erano), il tono come «normale».
È quindi una **stima per
eccesso** dei turni coperti; l'ombra (`system1_dopo_tool: ombra`) dà il numero vero.

Stampa, **solo numeri e nomi di tool**:

- risposte con le parole, con tool, coperte dal codice (per tool), già pronte (`casa_comando`:
  già senza seconda passata), i perché delle altre;
- la prima frase mediana dei turni senza tool, coperti, già pronti e degli altri con tool;
- il tempo risparmiabile stimato per turno coperto: la sua prima frase meno la mediana dei turni
  senza tool dello stesso giorno (al minimo 0), p50, p90 e in tutto;
- se nel registro c'è già il campo `dopo_tool` (ombra o attivo), il riassunto di
  `calliope stato --turni`.

`--prova`: lo stesso calcolo su pochi turni finti (nomi di fantasia), a secco.
"""

import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from calliope.system1 import dopo_tool as dt  # noqa: E402

# I segnali del registro (regole del turno) che per Brain sono dubbi di struttura
_DUBBI = (("azione_in_sospeso", "proposta"), ("sospeso_altrui_consenso", "proposta_altrui"),
          ("correzione_tool", "correzione"), ("domanda_insistita", "insistenza"),
          ("sviluppo_modalita", "sviluppo"), ("foto_davanti", "foto"))


def _dubbi(t: dict) -> tuple:
    regole = [str(r) for r in t.get("regole") or ()]
    out = [nome for r, nome in _DUBBI if r in regole]
    if any(r.startswith("spinta_") or r in ("dichiarata_taciuta", "richiesta_trattenuta")
           for r in regole):
        out.append("spinta")
    if t.get("allegati"):
        out.append("foto")
    return tuple(out)


def _risultato(nome: str, ok: bool) -> dict:
    """Il risultato che il registro non ha: riuscito con la sua frase, oppure fallito."""
    if not ok:
        return {"ok": False, "errore": "(dal registro: fallito)"}
    cop = dt.COPERTI.get(nome)
    if cop is None:
        return {"ok": True}
    # Le letture brevi (16/10, issue #103): il registro non ha quante voci c'erano, si contano
    # come brevi (stima per eccesso, come il resto)
    voci = {"voci": []} if cop.voci_max >= 0 else {}
    return {"ok": True, **voci, **({cop.campi[0]: "x"} if cop.campi else {})}


def valuta(turni: list[dict], parole_max: int = dt.PAROLE_MAX) -> dict:
    d = dt.DopoTool(parole_max)
    senza_tool: dict[str, list] = {}
    righe = []
    for t in turni:
        if t.get("esito") != "risposta":
            continue
        giorno = str(t.get("inizio") or "")[:10]
        pf = t.get("prima_frase_s")
        tool = [x for x in t.get("tool") or () if isinstance(x, dict) and x.get("nome")]
        if not tool:
            if isinstance(pf, (int, float)):
                senza_tool.setdefault(giorno, []).append(pf)
            continue
        testo = t.get("testo")
        if not isinstance(testo, str) or not testo.strip():
            righe.append(("senza_parole", None, giorno, pf))
            continue
        nomi = tuple(x["nome"] for x in tool)
        if len(nomi) == 1 and nomi[0] == "casa_comando" and tool[0].get("ok"):
            righe.append(("gia_pronta", "casa_comando", giorno, pf))
            continue
        e = dt.Esito(testo=testo, chiamate=nomi,
                     risultati=tuple(_risultato(x["nome"], bool(x.get("ok"))) for x in tool),
                     dubbi=_dubbi(t))
        s = d.decide(e)
        righe.append((dt.CODICE if s.scelta == dt.CODICE else s.perche, s.tool, giorno, pf))
    med = {g: statistics.median(v) for g, v in senza_tool.items() if v}
    tutti_senza = [x for v in senza_tool.values() for x in v]
    coperti = [r for r in righe if r[0] == dt.CODICE]
    risp = sorted(max(0.0, r[3] - med[r[2]]) for r in coperti
                  if isinstance(r[3], (int, float)) and r[2] in med)
    perche, per_tool = {}, {}
    for r in righe:
        if r[0] == dt.CODICE:
            per_tool[r[1]] = per_tool.get(r[1], 0) + 1
        elif r[0] not in ("gia_pronta", "senza_parole"):
            perche[r[0]] = perche.get(r[0], 0) + 1

    def mediana(sel):
        v = [r[3] for r in righe if sel(r) and isinstance(r[3], (int, float))]
        return round(statistics.median(v), 2) if v else None

    return {"risposte_con_tool": len(righe), "coperti": len(coperti),
            "gia_pronte": sum(1 for r in righe if r[0] == "gia_pronta"),
            "senza_parole": sum(1 for r in righe if r[0] == "senza_parole"),
            "per_tool": sorted(per_tool.items(), key=lambda kv: -kv[1]),
            "perche": sorted(perche.items(), key=lambda kv: -kv[1]),
            "prima_frase_senza_tool": (round(statistics.median(tutti_senza), 2)
                                       if tutti_senza else None),
            "prima_frase_coperti": mediana(lambda r: r[0] == dt.CODICE),
            "prima_frase_gia_pronte": mediana(lambda r: r[0] == "gia_pronta"),
            "prima_frase_altri": mediana(lambda r: r[0] not in (dt.CODICE, "gia_pronta")),
            "risparmio_p50_s": round(risp[len(risp) // 2], 2) if risp else None,
            "risparmio_p90_s": round(risp[min(len(risp) - 1, int(.9 * len(risp)))], 2)
            if risp else None,
            "risparmio_totale_s": round(sum(risp), 1)}


def stampa(r: dict, turni: list[dict]):
    n = r["risposte_con_tool"]
    print(f"Risposte con tool: {n} (senza le parole, quindi non valutate: {r['senza_parole']})")
    print(f"  coperte dal codice: {r['coperti']} ({100 * r['coperti'] / max(1, n):.0f} %)"
          + (": " + ", ".join(f"{k} ×{v}" for k, v in r["per_tool"]) if r["per_tool"] else ""))
    print(f"  già pronte (casa_comando): {r['gia_pronte']}")
    if r["perche"]:
        print("  al modello: " + ", ".join(f"{k} ×{v}" for k, v in r["perche"]))
    print(f"Prima frase mediana: senza tool {r['prima_frase_senza_tool']} s, coperte "
          f"{r['prima_frase_coperti']} s, già pronte {r['prima_frase_gia_pronte']} s, altre con "
          f"tool {r['prima_frase_altri']} s")
    print(f"Risparmio stimato per turno coperto: p50 {r['risparmio_p50_s']} s, p90 "
          f"{r['risparmio_p90_s']} s, in tutto {r['risparmio_totale_s']} s")
    if any(isinstance(t.get("dopo_tool"), dict) for t in turni):
        print()
        print(dt.testo(dt.riassunto(turni)))


def _finti() -> list[dict]:
    def t(testo, tool, pf, regole=(), giorno="2026-10-15"):
        return {"inizio": f"{giorno}T10:00:00", "esito": "risposta", "testo": testo,
                "tool": [{"nome": n, "ok": ok} for n, ok in tool], "prima_frase_s": pf,
                "regole": list(regole)}
    return [
        t("Che ore sono?", [], 1.7), t("Raccontami una storia breve", [], 1.9),
        t("Chi era Garibaldi?", [], 1.8),
        t("Metti un timer di dieci minuti", [("timer_imposta", True)], 2.7),
        t("Che ore sono?", [("ora_attuale", True)], 2.6),
        t("Quanto fa 17 per 6?", [("calcola", True)], 2.8),
        t("Accendi la luce in cucina", [("casa_comando", True)], 1.9),
        t("Metti un timer e dimmi che ore sono", [("timer_imposta", True),
                                                  ("ora_attuale", True)], 3.1),
        t("Cosa c'è nella lista della spesa?", [("lista_leggi", True)], 2.9),
        t("Ricorda che a Ugo piace il tè", [("ricorda", True)], 2.9),
        t("Metti un timer", [("timer_imposta", False)], 2.5),
        t("Sì", [("timer_imposta", True)], 2.6, regole=["azione_in_sospeso"]),
        {"inizio": "2026-10-15T11:00:00", "esito": "risposta", "testo": None,
         "tool": [{"nome": "ora_attuale", "ok": True}], "prima_frase_s": 2.6},
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--giorni", type=int, default=14)
    ap.add_argument("--cartella", help="la cartella del registro (di serie: turn_log_dir)")
    ap.add_argument("--prova", action="store_true", help="a secco, su turni finti")
    args = ap.parse_args()
    if args.prova:
        turni = _finti()
        parole_max = dt.PAROLE_MAX
    else:
        from calliope import latenza
        from calliope.config import load_config
        cfg = load_config()
        turni = latenza.leggi(args.cartella or cfg.turn_log_dir, args.giorni)
        parole_max = int(getattr(cfg, "system1_dopo_tool_parole_max", dt.PAROLE_MAX))
    r = valuta(turni, parole_max)
    stampa(r, turni)
    if args.prova:
        atteso = (r["coperti"], r["gia_pronte"], r["senza_parole"], dict(r["perche"]))
        voluto = (3, 1, 1, {"piu_tool": 1, "non_coperto": 1, "tool_fallito": 1,
                            "dubbio_proposta": 1})
        print("\nprova a secco:", "ok" if atteso == voluto else f"ERR {atteso} invece di {voluto}")
        return 0 if atteso == voluto else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
