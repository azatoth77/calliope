"""
`proposta_rispondi`: la risposta della persona a una proposta aperta, in forma strutturata
(10/10/2026, passo 1 del progetto «lo stato del dialogo come macchina a stati»,
docs/ricerche/2026-10-10-macchina-stati.md § 3.4).

È un tool **di servizio del dialogo**: sempre negli schemi, uguale per ogni livello (la cache
del prefisso non cambia con lo stato). Il significato della risposta lo dà il modello
(principio 10); la macchina (calliope/stato_dialogo.py) tiene la proposta e i suoi argomenti, e
decide se un sì basta. La chiamata la gestisce Brain (`Brain._proposta_rispondi`): vale solo
nella prima passata della risposta e prima che un tool legga un dato non fidato (difesa: un dato
appena letto non può «rispondere» alla proposta).

Dal passo 1 è **in ombra** (`dialogo_interprete: ombra`): l'esito `si` diventa la chiamata del
tool proposto con gli argomenti proposti, attraverso i controlli di sempre (livello, politica,
minori): decide ancora la politica di oggi. Gli altri esiti non fanno niente. La funzione qui
sotto risponde solo a chi chiama il registro senza Brain (prove, agenti): nessuna proposta.
"""
from ..stato_dialogo import ESITI, TOOL
from ..testi import NIENTE
from .spec import ToolSpec

TUTTI = frozenset({"ospite", "familiare", "amministra"})

DESCRIZIONE = (
    "La risposta di chi parla alla proposta aperta che vedi nello «Stato del dialogo». Quando "
    "c'è una proposta aperta e la frase le risponde, chiama questo al posto del tool proposto: "
    "esito «si» (sì, ok, va bene, certo, procedi…: l'azione la esegue il sistema con gli "
    "argomenti già proposti), «no» (rifiuta), «correzione» (la stessa cosa con un dato diverso, "
    "«no, quella del bagno»: poi chiama il tool giusto con il dato corretto), «rinvio» (la vuole "
    "più tardi), «altro» (la frase parla d'altro). Senza una proposta aperta non chiamarlo.")


def _senza_brain(ctx, esito: str = "", proposta: str = "", correzione: str = "",
                 quando: str = "") -> dict:
    return {"ok": False, "fatto": NIENTE, "errore": "nessuna proposta aperta",
            "cosa_fare": "rispondi a quello che chiede chi parla, chiamando i tool come sempre"}


def proposta_spec() -> ToolSpec:
    return ToolSpec(
        name=TOOL,
        description=DESCRIZIONE,
        parameters={"type": "object",
                    "properties": {
                        "esito": {"type": "string", "enum": list(ESITI),
                                  "description": "si, no, correzione, rinvio o altro"},
                        "proposta": {"type": "string",
                                     "description": "l'id della proposta (p1, p2…) dallo stato "
                                                    "del dialogo; vuoto = quella aperta"},
                        "correzione": {"type": "string",
                                       "description": "con esito correzione: che cosa cambia, "
                                                      "con le parole di chi parla"},
                        "quando": {"type": "string",
                                   "description": "con esito rinvio: quando («stasera», «tra "
                                                  "dieci minuti»)"}},
                    "required": ["esito"]},
        func=_senza_brain, risk="lettura", levels=TUTTI)
