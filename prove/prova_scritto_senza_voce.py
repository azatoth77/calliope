"""Prova a secco: dallo schermo personale si scrive senza aver parlato (28/10, issue #301, epic
#251; area docs/aree/schermi-telefono.md e docs/aree/sicurezza-politica.md).

Il ciclo vero (`Ciclo.giro` con l'ingresso degli schermi, un `ToolRegistry` vero e il backend a
copione di prova_stati_buchi), senza nessuna conversazione a voce aperta:

- lo scritto di un familiare passa da `_prendi_scritto` (niente `scritto_senza_conversazione`),
  arriva al modello col testo e vale «familiare»; quello di chi amministra vale al più
  «familiare»;
- un'azione che vuole la voce (`registra_utente`) scritta da chi amministra è rifiutata
  (`scritto_serve_voce`), come prima;
- un minore fuori dagli orari dei tutori: rifiutato con la frase degli orari, il modello non lo
  vede; dentro gli orari passa, col suo livello;
- l'ospite: lo schermo di stanza senza una conversazione nella sua stanza resta rifiutato;
- il modulo dallo schermo personale senza conversazione resta rifiutato (canale «modulo»).

Nomi e dati di fantasia, niente rete né modelli.

    python prove/prova_scritto_senza_voce.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from calliope.schermi import Schermi  # noqa: E402

import prova_raccolte as pr  # noqa: E402  (il ciclo con i finti degli schermi)
import prova_stati_buchi as sb  # noqa: E402

ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  {dettaglio}" if dettaglio and not ok else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


class HubScritto(pr.HubFinto):
    """Gli schermi per il ciclo con la regola vera dello scritto (`Schermi.scritto_consentito`)
    e nessuna conversazione a voce aperta (`scrittura_consentita` dice sempre di no)."""

    def __init__(self):
        super().__init__()
        self.proprietari = {}

    def schermo(self, sid):
        return {"id": sid, "proprietario": self.proprietari.get(sid), "nome": f"schermo {sid}"}

    def scritto_consentito(self, schermo, canale="scritto"):
        return Schermi.scritto_consentito(self, schermo, canale)


def prepara():
    b, c, sc, liste, turni, voce, _, _ = pr.prepara_ciclo()
    hub = HubScritto()
    # Lo stesso ingresso che il ciclo guarda
    hub.ingresso = c.s.schermi.ingresso
    c.s.schermi = b.tool_ctx.schermi = hub
    hub.proprietari = {1: "dario", 2: "bianca", 3: "lia", 4: None}
    from calliope.immagini import InAttesa
    c.s.foto_attesa = InAttesa(60)
    c.s.barge_in = False                # niente ascolto del nome mentre risponde (finti)
    return b, c, sc, turni, hub


def scritto(c, sid, persona, testo):
    item = {"tipo": "scritto", "testo": testo, "persona": persona, "schermo": f"schermo {sid}",
            "stanza": "studio", "schermo_id": sid, "arrivato": time.time()}
    pr.tocca(c, item)


def visti(b):
    """Le frasi della persona arrivate al modello nell'ultima richiesta."""
    if not b.backend.visti:
        return []
    return [m.get("content") for m in b.backend.visti[-1] if m.get("role") == "user"]


def main() -> int:
    b, c, sc, turni, hub = prepara()

    n = len(b.backend.visti)
    scritto(c, 2, "bianca", "Che ore sono a Tokyo?")
    r = turni[-1] if turni else {}
    verifica("familiare senza conversazione a voce: lo scritto arriva al modello",
             len(b.backend.visti) > n and any("Tokyo" in (x or "") for x in visti(b)),
             json.dumps(r, ensure_ascii=False)[:300])
    verifica("…senza la regola scritto_senza_conversazione, al livello «familiare», chi scrive dallo schermo",
             r.get("esito") != "rifiutato" and "scritto_senza_conversazione" not in (r.get("regole") or [])
             and r.get("livello") == "familiare" and (r.get("voce") or {}).get("modo") == "schermo"
             and (r.get("voce") or {}).get("nome") == "Bianca", json.dumps(r, ensure_ascii=False)[:300])

    scritto(c, 1, "dario", "Come sta andando la giornata?")
    r = turni[-1]
    verifica("chi amministra, scrivendo senza aver parlato: al più «familiare»",
             r.get("esito") != "rifiutato" and r.get("livello") == "familiare"
             and (r.get("voce") or {}).get("nome") == "Dario", json.dumps(r, ensure_ascii=False)[:300])

    # Un'azione che vuole la voce, scritta da chi amministra: il tool risponde che serve la voce
    b.backend.copione.append([("calls", [{"id": "c-reg", "name": "registra_utente", "arguments": {"nome": "Ugo"}}])])
    scritto(c, 1, "dario", "Registra la voce di Ugo.")
    r = turni[-1]
    tool = (r.get("tool") or [{}])[0]
    verifica("contrario: un'azione che vuole la voce, scritta, è rifiutata (scritto_serve_voce)",
             tool.get("nome") == "registra_utente" and tool.get("ok") is False
             and "scritto_serve_voce" in (r.get("regole") or []), json.dumps(r, ensure_ascii=False)[:400])

    # Un minore fuori dagli orari dei tutori
    import calliope.ciclo as ciclo_mod
    vero = ciclo_mod.minori.fuori_orario
    ciclo_mod.minori.fuori_orario = lambda prof, adesso=None: ("21:00-07:00" if getattr(prof, "id", "") == "lia"
                                                               else vero(prof, adesso))
    try:
        n = len(b.backend.visti)
        scritto(c, 3, "lia", "Mi racconti una storia?")
        r = turni[-1]
        verifica("contrario: un minore che scrive fuori orario, rifiutato con la regola degli orari",
                 r.get("esito") == "fuori_orario" and "minore_fuori_orario" in (r.get("regole") or [])
                 and len(b.backend.visti) == n, json.dumps(r, ensure_ascii=False)[:300])
    finally:
        ciclo_mod.minori.fuori_orario = vero
    n = len(b.backend.visti)
    scritto(c, 3, "lia", "Mi racconti una storia?")
    r = turni[-1]
    verifica("un minore dentro gli orari: passa, col suo livello (mai sopra «familiare»)",
             r.get("esito") not in ("rifiutato", "fuori_orario") and len(b.backend.visti) > n
             and r.get("livello") in ("familiare", "minore", "ospite")
             and (r.get("voce") or {}).get("nome") == "Lia", json.dumps(r, ensure_ascii=False)[:300])

    # L'ospite: lo schermo di stanza senza una conversazione nella sua stanza
    n = len(b.backend.visti)
    scritto(c, 4, None, "Che tempo fa?")
    r = turni[-1]
    verifica("contrario: l'ospite da uno schermo di stanza senza conversazione, rifiutato",
             r.get("esito") == "rifiutato" and r.get("regole") == ["scritto_senza_conversazione"]
             and len(b.backend.visti) == n and "tempo" not in json.dumps(r, ensure_ascii=False),
             json.dumps(r, ensure_ascii=False)[:300])

    # Il modulo dallo schermo personale vuole ancora la conversazione a voce
    pr.tocca(c, {"tipo": "modulo", "_modulo": object(), "valori": {}, "schermo": "schermo 1",
                 "stanza": "studio", "schermo_id": 1, "arrivato": time.time()})
    r = turni[-1]
    verifica("contrario: il modulo senza conversazione, rifiutato col canale «modulo»",
             r.get("esito") == "rifiutato" and r.get("canale") == "modulo"
             and r.get("regole") == ["scritto_senza_conversazione"], json.dumps(r, default=str)[:300])

    print(f"\n{'Tutto bene' if not ERRORI else f'{len(ERRORI)} errori'}")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
