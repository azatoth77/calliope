"""
Le azioni dichiarate o promesse senza tool, e quante sono arrivate alla voce (22/10/2026,
issue #170).

Il caso vero del 18/10 (DGX): «Segno fatto, allora: d'ora in poi ti chiamerò così» e «allora mi
metto al lavoro… ti faccio sapere» in turni senza nessun tool. La rete `spinta_dichiarata`
(brain.ClaimHold) trattiene la prima frase che dichiara un'azione; una dichiarazione più avanti
arriva alla voce e la spinta parte a frase detta. `spinta_promessa` («ora controllo…») spinge
sempre a frase detta, ed è spenta nei profili del 26B. Prima di accendere
`voce_azione_non_fatta: attivo` servono i numeri: quante volte scattano le due reti, quante
frasi false arrivano a chi ascolta, quante ne avrebbe trattenute il seguito in ombra.

Dal registro dei turni (calliope/turnlog.py), solo le risposte del modello (`esito: risposta`):

- **dichiarate** (regola `spinta_dichiarata`): `dette` se la frase falsa era già alla voce
  (regola `dichiarata_detta`, dal 22/10), `trattenute` se non è stata detta
  (`dichiarata_trattenuta`, dal 22/10). Nei turni di prima le regole non ci sono: si guarda la
  risposta detta (`risposta`, ciò che si è sentito): se dichiara un'azione (brain.is_claim) e
  nessun tool è riuscito, `dette`; se un tool è riuscito dopo la spinta la frase vera e quella
  falsa non si distinguono, `incerte`; altrimenti `trattenute`. Senza il testo (minori, ospiti,
  risposte riservate) `senza_testo`;
- **promesse** (regola `spinta_promessa`): la spinta parte sempre a frase detta, quindi sono
  tutte `dette`;
- **senza scatto**: risposte senza nessun tool e senza le due regole, con la forma nella
  risposta detta (is_claim, ACTION_PROMISE senza «?» in fondo): la rete spenta (il 26B spegne
  `spinta_promessa`) o una forma che la rete non vede. Una stima: i ricordi («ho salvato che…»)
  qui non si distinguono;
- **seguito** (`voce_azione_non_fatta`): in ombra `azione_non_fatta_ombra` (avrebbe trattenuto),
  in attivo `azione_non_fatta` (trattenuta), `azione_non_fatta_onesta` (la frase onesta dopo la
  seconda dichiarazione), e quante volte il tool è arrivato dopo la spinta;
- gli **esempi**: le ultime frasi dette o che il seguito avrebbe trattenuto (ora e frase, dal
  testo della risposta già nel registro), da rileggere per i falsi positivi. Solo dei turni di
  chi amministra senza un minore vicino o una voce incerta (revisione della PR #220): mai le
  risposte ai minori, agli ospiti e agli altri familiari, che restano nei soli conteggi
  (`esempi_non_mostrati`).

Solo lettura, nessun modello. In `calliope stato --turni` (e `--json`, chiave `azioni_dette`).
"""
from __future__ import annotations

import re

ESEMPI = 6
_FRASE = re.compile(r"[^.!?…]*[.!?…]+|[^.!?…]+$")


def _frase_di(testo: str, cerca) -> str:
    """La prima frase di `testo` per cui `cerca(frase)` è vera, o ""."""
    for m in _FRASE.finditer(testo or ""):
        f = m.group(0).strip()
        if f and cerca(f):
            return f
    return ""


def _mostrabile(t: dict) -> bool:
    """Il testo di questo turno si può mostrare fra gli esempi? Solo chi amministra, senza un
    minore vicino né una voce incerta, e non una risposta riservata."""
    voce = t.get("voce") if isinstance(t.get("voce"), dict) else {}
    return (t.get("livello") == "amministra" and not t.get("riservato")
            and not voce.get("minore_vicino") and not voce.get("incerta"))


def _vuoto() -> dict:
    return {"risposte": 0,
            "dichiarate": {"scatti": 0, "dette": 0, "trattenute": 0, "incerte": 0,
                           "senza_testo": 0},
            "promesse": {"scatti": 0, "dette": 0, "senza_testo": 0},
            "senza_scatto": {"dichiarate": 0, "promesse": 0},
            "seguito": {"ombra": 0, "attivo": 0, "onesta": 0, "tool_dopo": 0},
            "esempi": [], "esempi_non_mostrati": 0}


def riassunto(turni) -> dict:
    from .brain import ACTION_PROMISE, dichiara_azione, is_claim
    r = _vuoto()
    esempi = []
    nascosti = [0]
    for t in turni or ():
        if not isinstance(t, dict) or t.get("esito") != "risposta":
            continue
        r["risposte"] += 1
        regole = set(t.get("regole") or ())
        risposta = t.get("risposta") if isinstance(t.get("risposta"), str) else None
        tool = [x for x in t.get("tool") or () if isinstance(x, dict)]
        riuscito = any(x.get("ok") for x in tool)
        quando = str(t.get("inizio") or "")[:16].replace("T", " ")
        mostra = _mostrabile(t)

        def aggiungi(quando, tipo, frase, mostra=mostra):
            if not frase:
                return
            if mostra:
                esempi.append((quando, tipo, frase))
            else:
                nascosti[0] += 1

        d = r["dichiarate"]
        if "spinta_dichiarata" in regole:
            d["scatti"] += 1
            if "dichiarata_detta" in regole:
                d["dette"] += 1
                if risposta:
                    aggiungi(quando, "detta", _frase_di(risposta, is_claim))
            elif "dichiarata_trattenuta" in regole:
                d["trattenute"] += 1
            elif risposta is None:
                d["senza_testo"] += 1
            elif is_claim(risposta) and not riuscito:
                d["dette"] += 1
                aggiungi(quando, "detta", _frase_di(risposta, is_claim))
            elif is_claim(risposta):
                d["incerte"] += 1
            else:
                d["trattenute"] += 1
        p = r["promesse"]
        if "spinta_promessa" in regole:
            p["scatti"] += 1
            if risposta is None:
                p["senza_testo"] += 1
            else:
                p["dette"] += 1
                aggiungi(quando, "promessa",
                         _frase_di(risposta, lambda f: bool(ACTION_PROMISE.search(f))))
        if (not tool and risposta and not {"spinta_dichiarata", "spinta_promessa"} & regole):
            if dichiara_azione(risposta, nuove=True):
                r["senza_scatto"]["dichiarate"] += 1
                aggiungi(quando, "senza scatto",
                         _frase_di(risposta, lambda f: dichiara_azione(f, nuove=True)))
            elif ACTION_PROMISE.search(risposta) and not risposta.rstrip().endswith("?"):
                r["senza_scatto"]["promesse"] += 1
                aggiungi(quando, "promessa senza scatto",
                         _frase_di(risposta, lambda f: bool(ACTION_PROMISE.search(f))))
        s = r["seguito"]
        if "azione_non_fatta_ombra" in regole:
            s["ombra"] += 1
            if risposta and "dichiarata_detta" not in regole:
                aggiungi(quando, "ombra",
                         _frase_di(risposta, lambda f: dichiara_azione(f, nuove=True)))
        if "azione_non_fatta" in regole:
            s["attivo"] += 1
            if riuscito:
                s["tool_dopo"] += 1
        if "azione_non_fatta_onesta" in regole:
            s["onesta"] += 1
    r["esempi"] = [{"quando": q, "tipo": k, "frase": f[:120]} for q, k, f in esempi][-ESEMPI:]
    r["esempi_non_mostrati"] = nascosti[0]
    return r


def testo(r: dict) -> str:
    """Le righe per `calliope stato --turni`."""
    titolo = "Azioni dichiarate o promesse senza tool (22/10, issue #170)"
    if not r or not r.get("risposte"):
        return f"{titolo}: nessuna risposta nel registro."
    d, p, n, s = r["dichiarate"], r["promesse"], r["senza_scatto"], r["seguito"]
    righe = [titolo,
             f"    su {r['risposte']} risposte: spinta_dichiarata {d['scatti']} (alla voce "
             f"{d['dette']}, trattenute {d['trattenute']}"
             + (f", incerte {d['incerte']}" if d["incerte"] else "")
             + (f", senza testo {d['senza_testo']}" if d["senza_testo"] else "") + "); "
             f"spinta_promessa {p['scatti']} (tutte alla voce"
             + (f", senza testo {p['senza_testo']}" if p["senza_testo"] else "") + ")",
             f"    alla voce senza nessuna rete scattata (stima): dichiarate {n['dichiarate']}, "
             f"promesse {n['promesse']}",
             f"    voce_azione_non_fatta: in ombra avrebbe trattenuto {s['ombra']}; in attivo "
             f"trattenute {s['attivo']} (poi il tool {s['tool_dopo']}, frase onesta "
             f"{s['onesta']})"]
    if r.get("esempi"):
        righe.append("    ultime frasi da rileggere:")
        righe += [f"      {e['quando']} [{e['tipo']}] «{e['frase']}»" for e in r["esempi"]]
    if r.get("esempi_non_mostrati"):
        righe.append(f"    frasi di minori, ospiti e familiari non mostrate: "
                     f"{r['esempi_non_mostrati']} (solo nei conteggi)")
    return "\n".join(righe)
