"""Un vLLM finto che ridà le uscite vere del banco dello Studio (31/10, issue #344).

Il banco del 31/10 04:29 (`prove/manuali/banco_studio.py --fasi prove,mappa`, qwen3.6-35b sulla
DGX, versione aa1dd29) aveva salvato lo scheletro già controllato dal codice e le domande già
preparate, non le uscite grezze del modello. Le uscite di `manuali/studio/uscite_banco_3110.json`
sono **ricostruite** da quei risultati, sui materiali di fantasia del banco:
- le triple della mappa dai collegamenti tenuti (pagine P…, argomento A… del concetto nuovo), più
  ciò che il codice aveva cambiato e che si rimette com'era (scritto in `ricostruito`: il composto
  «Spagna e Portogallo» sciolto, la tripla di «Foglie» col capo tagliato dal tetto dei concetti);
- la seconda passata dai collegamenti con `unisce`, coi **testi** dei concetti al posto dei codici
  C…: il finto li ritrova nello scheletro della richiesta (`codici_dalla_richiesta`), così la stessa
  uscita vale anche quando il codice cambia lo scheletro (concetti uniti o rinumerati);
- le domande come le aveva scritte il modello (tipo, domanda, opzioni, risposta, pagine).
Dal 31/10 il banco salva anche le uscite grezze (`grezzo`, `grezzo_connessione`):
`manuali/studio/uscite_banco_3110_0702.json` ha quelle **vere** del banco del 31/10 07:02 (#349),
con la seconda passata tradotta dai codici C… di allora ai testi dei concetti
(`VllmFinto(uscite=carica(percorso))`).

Uso: `cli = VllmFinto(); banco_studio.fase_mappa(cli, materiali, {}, uscita, log)`; il finto
riconosce la verifica dall'intestazione («Verifica di Storia…») e la richiesta dallo schema.
"""

import json
import re
from pathlib import Path

USCITE = Path(__file__).resolve().parent / "manuali" / "studio" / "uscite_banco_3110.json"

_RIGA_CODICE = re.compile(r"^\s+(C\d+): (.*?)(?: \(P\d+(?:, P\d+)*\))?$", re.M)


def carica(path: Path = USCITE) -> dict:
    return json.loads(Path(path).read_text("utf-8"))


def codici_dalla_richiesta(testo: str) -> dict[str, str]:
    """Il testo del concetto → il codice C… scritto nello scheletro della seconda richiesta."""
    return {m.group(2).strip(): m.group(1) for m in _RIGA_CODICE.finditer(testo)}


class VllmFinto:
    """`chat(messaggi, schema=…, **kw)` come il `Cliente` del banco: le uscite del 31/10."""

    def __init__(self, uscite: dict | None = None, materiali: dict | None = None):
        self.uscite = uscite or carica()
        self.materiali = materiali or {}
        self.richieste: list[tuple[str, str]] = []      # (verifica, «mappa» | «connessione» | …)

    def _verifica(self, testo: str) -> str:
        for vid, ver in self.materiali.items():
            if f"Verifica di {ver['materia']}" in testo:
                return vid
        for vid in self.uscite["mappa"]:
            if f"Verifica di {vid}".lower() in testo.lower():
                return vid
        raise KeyError("verifica non riconosciuta")

    def chat(self, messaggi, *, schema=None, **kw):
        from calliope.studio import mappa as M
        testo = messaggi[-1]["content"]
        vid = self._verifica(testo)
        chiavi = set((schema or {}).get("properties", {}))
        if "triple" in chiavi:
            self.richieste.append((vid, "mappa"))
            out = {"triple": self.uscite["mappa"][vid]["triple"]}
        elif "collegamenti" in chiavi:
            self.richieste.append((vid, "connessione"))
            cod = codici_dalla_richiesta(testo)

            def trova(t):
                # Prima il concetto con lo stesso testo, poi singolare o plurale (`uguale`)
                return next((c for x, c in cod.items() if M.chiave(t) == M.chiave(x)),
                            next((c for x, c in cod.items() if M.uguale(t, x)), t))
            out = {"collegamenti": [{**c, "da": trova(c["da"]), "a": trova(c["a"])}
                                    for c in self.uscite["mappa"][vid]["connessione"]]}
        elif "domande" in chiavi:
            self.richieste.append((vid, "domande"))
            out = {"domande": self.uscite["prove"][vid]["domande"]}
        else:
            raise KeyError(f"richiesta non riconosciuta: {sorted(chiavi)}")
        return {"testo": json.dumps(out, ensure_ascii=False), "secondi": 0.0, "token_out": 0}
