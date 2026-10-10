"""
`argomento`: chi parla cambia argomento o torna a uno messo da parte (10/10/2026, § 13 del
progetto docs/ricerche/2026-10-10-registro-eventi.md, passo 3 del registro degli eventi).

Al posto della «conversazione nuova»: una conversazione non si azzera (non si dimentica niente:
l'unica dimenticanza vera resta «dimentica»), cambia **argomento**. Lo decide il modello dal
contenuto (principio 10): «ricominciamo», «parliamo d'altro», «torniamo a…» sono indizi, non
comandi. È un tool di servizio del dialogo come `proposta_rispondi`: uguale per ogni livello, e
la chiamata la gestisce Brain (`Brain._argomento`), che mette da parte ciò che era aperto (lo
sviluppo in pausa, la proposta scaduta «da parte»), dice la mezza frase fissa e lascia l'evento
`argomento_nuovo`/`argomento_ripreso` al registro. Solo con `eventi: attivo`: con «ombra» o
«spento» Brain non lo mette negli schemi (e al suo posto resta `conversazione_nuova`).

La forma (tool e non un campo di `proposta_rispondi`): misura del 10/10 col 4B in
docs/aree/contesto-conversazione.md; un campo vale solo con una proposta aperta, mentre un
argomento cambia anche senza.
"""
from ..testi import NIENTE
from .spec import ToolSpec

TOOL = "argomento"
AZIONI = ("nuovo", "riprendi")
TUTTI = frozenset({"ospite", "familiare", "amministra"})

DESCRIZIONE = (
    "Chi parla cambia argomento. Chiamalo solo quando la frase lascia il discorso di adesso per "
    "un altro lontano (azione «nuovo», con un titolo breve dell'argomento nuovo), o torna a un "
    "argomento messo da parte (azione «riprendi», con il suo titolo; anche «no, parlavo ancora "
    "di…» per annullare un cambio sbagliato). Ciò che era aperto nell'argomento lasciato (uno "
    "sviluppo, una tua domanda) va da parte, non si chiude. «Ricominciamo», «parliamo d'altro», "
    "«lasciamo perdere», «da capo» di solito vogliono un argomento nuovo; «riprendiamo», «dove "
    "eravamo?», «torniamo a…» uno ripreso; se non è chiaro, chiedilo. NON chiamarlo per una "
    "domanda sullo stesso argomento, un seguito («e poi?»), la risposta a una tua domanda, o "
    "una richiesta breve che non cambia il discorso (l'ora, il meteo). Chiama insieme anche i "
    "tool che servono alla richiesta.")


def _senza_brain(ctx, azione: str = "", titolo: str = "") -> dict:
    return {"ok": False, "fatto": NIENTE, "errore": "gli argomenti non sono attivi qui",
            "cosa_fare": "rispondi a quello che chiede chi parla, chiamando i tool come sempre"}


def argomento_spec() -> ToolSpec:
    return ToolSpec(
        name=TOOL,
        description=DESCRIZIONE,
        parameters={"type": "object",
                    "properties": {
                        "azione": {"type": "string", "enum": list(AZIONI),
                                   "description": "nuovo (un argomento nuovo) o riprendi (uno "
                                                  "messo da parte)"},
                        "titolo": {"type": "string",
                                   "description": "il titolo breve dell'argomento, 2–6 parole "
                                                  "(«chilometri in miglia», «consigli per "
                                                  "dormire»)"}},
                    "required": ["azione", "titolo"]},
        func=_senza_brain, risk="lettura", levels=TUTTI)
