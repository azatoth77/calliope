"""
Le notizie dette restano nel contesto (13/10/2026, decisione 7 di chi amministra): i fatti
numerati, con titolo, testate e sommario, restano nella storia **in busta** come dato non
fidato, così «dimmi di più sulla seconda», «chi l'ha detto?», «e poi cos'è successo?» arrivano
al modello con i fatti davanti (a differenza dei risultati di web_cerca, che a risposta finita
escono dalla storia: brain.WEB_TOLTO).

Il risultato intero resta per il turno dopo, come tutti (Brain._compact_old_results). Dai turni
ancora dopo, invece della traccia generica («risultato ridotto: richiama il tool») resta la
**forma ridotta** di questo modulo: numero, titolo, testate e quando di ogni fatto, sempre nella
busta. Niente import di Brain: la usano anche le proiezioni del registro degli eventi.
"""
from __future__ import annotations

import json

TOOL = "notizie"
NOTA_RIDOTTA = ("notizie dette in un turno precedente, qui solo titoli e testate: per i "
                "dettagli di una richiama notizie con fatto = il suo numero")
CAMPI_RIDOTTI = ("n", "titolo", "testate", "quando")


def riduci(contenuto: str) -> str | None:
    """La forma ridotta del risultato di notizie (JSON), o None se non c'è niente da ridurre
    (allora vale la forma di sempre)."""
    try:
        res = json.loads(contenuto)
    except (TypeError, ValueError):
        return None
    if not isinstance(res, dict):
        return None
    busta = res.get("dato_non_fidato")
    dentro = busta.get("contenuto") if isinstance(busta, dict) else None
    if not isinstance(dentro, dict):
        return None
    fatti = dentro.get("fatti")
    if isinstance(fatti, list):
        ridotti = [{k: f[k] for k in CAMPI_RIDOTTI if k in f}
                   for f in fatti if isinstance(f, dict)]
        nuovo = {"fatti": ridotti}
    elif isinstance(dentro.get("notizia"), dict):
        n = dentro["notizia"]
        nuovo = {"notizia": {k: n[k] for k in CAMPI_RIDOTTI if k in n}}
    else:
        return None
    out = {"ok": res.get("ok", True), "nota": NOTA_RIDOTTA,
           "dato_non_fidato": {"avviso": busta.get("avviso", ""), "contenuto": nuovo}}
    return json.dumps(out, ensure_ascii=False)
