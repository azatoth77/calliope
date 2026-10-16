"""L'esito detto dal modello dopo la frase di sfida superata (16/10/2026, issue #94;
docs/aree/voce-e-regole.md e sicurezza-politica.md), a secco con un backend finto.

Caso vero del 15/10 sera (nomi di fantasia): chi amministra registra una familiare,
`registra_utente` parte dalla sfida e riesce con `cosa_fare` e senza frase pronta; il modello
dice «Ho registrato Ada come familiare…» e la rete delle azioni dichiarate, che dentro la
passata non vedeva più il tool (`_reply` azzerava `last_tools`), lo cambiava in «Non ho salvato
niente». Dal 16/10 `_reply(gia_fatti=…)` tiene l'esito riuscito del tool della sfida.

1. sfida → tool riuscito con `cosa_fare` → la frase del modello detta, una passata sola, né
   `spinta_dichiarata` né `dichiarata_onesta`; nel registro il tool una volta; con la prima
   passata vuota la seconda passata, non «Fatto.» (revisione della PR #105);
2. contrario: la stessa frase senza nessun tool resta fermata (spinta, poi la frase onesta);
3. contrario: dopo la sfida un tool di sola lettura non rende vera un'azione dichiarata;
4. contrario: il tool della sfida fallito → la frase dell'errore, senza il modello.

    python prove\\prova_sfida_esito.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from calliope.tools.spec import ToolSpec  # noqa: E402

errori = 0
NOME = "Ada"                                     # di fantasia
FRASE = (f"Ho registrato {NOME} come familiare. Adesso deve parlare lei, con un adulto "
         "accanto.")
SFIDA_DETTA = "Girasole, treno, limone, quarantadue."
RETI = ("spinta_dichiarata", "dichiarata_onesta", "dichiarata_taciuta")


class _Prof:
    def __init__(self, nome, admin=False):
        self.name, self.id, self.admin = nome, nome.lower() + "-id", admin


class _Persone:
    def __init__(self):
        from calliope.config import Config
        self.cfg = Config()
        self.users = {"Dario": _Prof("Dario", True)}

    def get(self, n):
        return self.users.get(n)


class _Backend:
    def __init__(self, copione):
        self.copione, self.visti = list(copione), []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        yield from (self.copione.pop(0) if self.copione else [("text", "Ok.")])


def _brain(copione, tool, sfida=True):
    """Una Brain minima (come prove/prova_sviluppo_giro3.py), con la sfida aperta su `tool`."""
    from calliope.brain import Brain
    from calliope.speaker_id import SpeakerContext
    from calliope.tools.registry import ToolRegistry
    from calliope.tools.spec import ToolContext
    p = _Persone()
    b = Brain.__new__(Brain)
    reg = ToolRegistry()
    reg.register(tool)
    b.cfg, b.tools, b.history = p.cfg, reg, []
    sc = SpeakerContext(p)
    b.tool_ctx = ToolContext(cfg=p.cfg, speakers=p, speaker_ctx=sc, speaker=None)
    b.backend = _Backend(copione)
    sc.identified_by, sc.from_session, sc.current_speaker = "voce", False, "Dario"
    sc.aggiorna_conversazione("Dario", "voce", True, 0.7)
    if sfida:
        from calliope import conferme as C
        sf = C.nuova_sfida(b.cfg, "dario-id", tool.name, {"nome": NOME})
        sf.parole, sf.numero = ("girasole", "treno", "limone"), 42
        sf.scade = time.monotonic() + 60
        sc.sfida = sf
    return b


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


def _registra(fatti, risk="azione", ok=True):
    def func(ctx, **a):
        fatti.append(a)
        if not ok:
            return {"ok": False, "errore": "il nome c'è già"}
        return {"ok": True, "frasi_necessarie": 5,
                "cosa_fare": f"Di' che adesso deve parlare {NOME}, con un adulto accanto"}
    return ToolSpec(name="registra_utente", description="", parameters={}, func=func,
                    risk=risk, levels=frozenset({"amministra"}))


def prova_caso_vero():
    print("— 1. sfida superata, registra_utente riuscito con cosa_fare: la frase del modello")
    fatti = []
    # Due passate uguali nel copione: prima della correzione la rete tratteneva la prima,
    # spingeva, e alla seconda diceva la frase onesta
    b = _brain([[("text", FRASE)], [("text", FRASE)]], _registra(fatti))
    detto = "".join(b.stream_reply(SFIDA_DETTA, "amministra")).strip()
    regole = b.rules_fired()
    verifica("il tool eseguito una volta dalla sfida", fatti == [{"nome": NOME}], str(fatti))
    verifica("la frase vera del modello arriva all'uscita", detto == FRASE, detto)
    verifica("…con sfida_esito_modello e nessuna rete delle azioni dichiarate",
             "sfida_esito_modello" in regole and not any(r in regole for r in RETI),
             str(regole))
    verifica("…una passata sola del modello", len(b.backend.visti) == 1,
             str(len(b.backend.visti)))
    verifica("nel registro dei turni il tool una volta, riuscito",
             [(t["nome"], t["ok"]) for t in b.last_tools] == [("registra_utente", True)],
             str(b.last_tools))
    verifica("nella storia: la frase, la chiamata, il risultato, la risposta",
             [m["role"] for m in b.history][-4:] == ["user", "assistant", "tool", "assistant"]
             and b.history[-1]["content"].strip() == FRASE, str(b.history[-1:]))


def prova_vuota():
    print("— 1b. dopo la sfida la prima passata vuota: la seconda passata, non «Fatto.»")
    fatti = []
    b = _brain([[("text", "")], [("text", FRASE)]], _registra(fatti))
    detto = "".join(b.stream_reply(SFIDA_DETTA, "amministra")).strip()
    regole = b.rules_fired()
    verifica("la seconda passata (vuoto_seconda_passata) e la frase del modello",
             detto == FRASE and "vuoto_seconda_passata" in regole
             and len(b.backend.visti) == 2, f"{regole} {detto!r}")
    verifica("…il tool una volta, nel registro una volta", fatti == [{"nome": NOME}]
             and [t["nome"] for t in b.last_tools] == ["registra_utente"], str(b.last_tools))


def prova_senza_tool():
    print("— 2. contrario: la stessa frase senza nessun tool resta fermata")
    fatti = []
    b = _brain([[("text", FRASE)], [("text", FRASE)]], _registra(fatti), sfida=False)
    detto = "".join(b.stream_reply(f"Registra {NOME} come familiare.", "amministra"))
    regole = b.rules_fired()
    verifica("nessun tool, la frase falsa non si dice", not fatti and "Ho registrato"
             not in detto, detto)
    verifica("…spinta e poi la frase onesta", "spinta_dichiarata" in regole
             and "dichiarata_onesta" in regole and "sfida_esito_modello" not in regole,
             str(regole))


def prova_lettura():
    print("— 3. contrario: dopo la sfida un tool di sola lettura non rende vera l'azione")
    fatti = []
    b = _brain([[("text", FRASE)], [("text", FRASE)]], _registra(fatti, risk="lettura"))
    detto = "".join(b.stream_reply(SFIDA_DETTA, "amministra"))
    regole = b.rules_fired()
    verifica("la dichiarazione d'azione dopo una lettura resta fermata",
             "sfida_esito_modello" in regole and "spinta_dichiarata" in regole
             and "Ho registrato" not in detto, f"{regole} {detto!r}")


def prova_fallito():
    print("— 4. contrario: il tool della sfida fallito")
    fatti = []
    b = _brain([[("text", FRASE)]], _registra(fatti, ok=False))
    detto = "".join(b.stream_reply(SFIDA_DETTA, "amministra"))
    regole = b.rules_fired()
    verifica("la frase dell'errore, senza il modello e senza «Ho registrato»",
             fatti == [{"nome": NOME}] and not b.backend.visti
             and "sfida_esito_fallito" in regole and "sfida_esito_modello" not in regole
             and "Ho registrato" not in detto, f"{regole} {detto!r}")


def main():
    prova_caso_vero()
    prova_vuota()
    prova_senza_tool()
    prova_lettura()
    prova_fallito()
    print(f"\n{'OK' if not errori else f'{errori} ERRORI'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
