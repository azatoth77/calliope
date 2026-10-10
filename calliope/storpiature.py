"""
Le forme chiuse brevi storpiate da Whisper (10/10/2026, casi veri della DGX con whisper.cpp).

«Annulla», «chiudilo», «sospendilo», «Calliope, ok» detti da soli arrivano come «Annullahi.»,
«Am nulla il lavoro.», «Nulla è lavoro.», «Chiudin.», «Giudino.», «Spendilo.», «Alla ora, ok.»;
il modello li indovinava (il 10/10 «Am nulla il lavoro» ha RIFATTO il lavoro dell'agente invece
di annullarlo) o non li capiva. Il modello non sente l'audio (principio 10: la trascrizione è ciò
che il modello non vede), ma una storpiatura non è una forma chiusa sicura: «Spendilo» è anche
una parola vera. Quindi:

- **un dato del turno** (`suggerisci`, regola `forma_storpiata`): «la trascrizione di «Spendilo»
  potrebbe essere «sospendilo»: se non è chiaro cosa intende, chiedi». Non decide niente: il
  significato lo sceglie il modello, e un'azione che fa partire un lavoro senza le sue parole
  chiede comunque conferma (politica `politica_avvio_non_chiesto`);
- **la corsia veloce** (calliope/risposte.py, in ombra) solo per «annulla» senza oggetto, che a
  una proposta vale «no» (effetto reversibile: la proposta resta chiusa, si richiede).

Sempre la frase **intera** (tolti il nome, anche storpiato in testa, e i riempitivi): mai una
parola dentro una frase («annulla la sveglia delle 7», «chiudi la finestra», «spendi meno», «non
serve a nulla» vanno al modello così come sono). «Ricominciamo» storpiato è una regola vera, con
il suo effetto (wakeword.nuova_conversazione_come): la conversazione si chiude e resta
nell'archivio. Casi e contrari in prove/prova_storpiature.py.
"""
from __future__ import annotations

import re

from .wakeword import _NAME_MARK, _plain_words, prefisso_nome

# Riempitivi e forme chiuse che possono precedere la forma storpiata («Anzi, no, a nulla.»,
# «No, niente, a nulla.»: «annulla» detto dopo un «no»)
_TESTA = frozenset({"anzi", "no", "niente", "allora", "ok", "okay", "e", "ma", "beh", "be",
                    "eh", "ehm", "si", "dai", "ecco", "ah", "oh"})
_CODA = frozenset({"pure", "grazie", "subito", "adesso", "ora", "allora", "dai"})

# Le cose che si annullano, si chiudono, si sospendono dette con la forma («annulla il lavoro»,
# «chiudi lo sviluppo», «sospendilo sviluppo»); «tutto» solo per annullare e chiudere («spendi
# tutto» è una frase vera)
_NOMI_COSE = "lavoro|sviluppo|programma"
_COSE = r"(?:" + _NOMI_COSE + r")"
_OGGETTO = r"(?: (?:il |lo |la |l |e )?" + _COSE + r")?"
_OGGETTO_TUTTO = r"(?: (?:il |lo |la |l |e )?(?:" + _NOMI_COSE + r"|tutto))?"

# (forma suggerita, espressione sulla frase intera)
FORME = (
    # «Annullahi.» (06:10:40), «Am nulla il lavoro.» (07:12:53), «Nulla è lavoro.» (06:13:05),
    # «Anzi, no a nulla.» (02/10), «No, niente a nulla.» (09/10). Non «nulla» da solo (è una
    # risposta: «niente»), non «annullato», «annullata» (parole vere)
    ("annulla", re.compile(r"(?:annull(?:ahi|ai|aj|ahe|ae|e|ia)|(?:am|an|ham|han|a|in|un) nulla)"
                           + _OGGETTO_TUTTO + r"|nulla (?:il |lo |la |l |e )(?:"
                           + _NOMI_COSE + r"|tutto)")),
    # «Chiudin.» (06:14:08), «Giudino.» (06:11:52), «Chiudino sviluppo.» (07:17:03). Non le forme
    # vere («chiudi», «chiudilo», «chiudo») né «giudice», «giudizio», «Giuditta»
    ("chiudilo", re.compile(r"(?:chi|ghi|gi)ud(?:in|ino|ini|ina|en|eno|ilo|ila|i)"
                            + _OGGETTO_TUTTO)),
    # «Spendilo.» (07:14:44), «Spendilo pure.» (07:21:06): è anche una parola vera, quindi solo
    # il dato del turno
    ("sospendilo", re.compile(r"(?:so )?spendi(?: ?l[oa])?" + _OGGETTO)),
)
_VERBO = {"annulla": "annulla", "chiudilo": "chiudi", "sospendilo": "sospendi"}
# Le forme vere: nessun suggerimento
_VERE = re.compile(r"chiudi(?:l[oa])?" + _OGGETTO_TUTTO)


def _nucleo(testo: str, name) -> tuple[list[str], bool]:
    """Le parole della frase senza il nome (anche storpiato in testa: «Alla ora, ok»), i
    riempitivi in testa e in coda; e se in testa c'era il nome storpiato."""
    parole = [w for w in _plain_words(testo, name) if w != _NAME_MARK]
    while parole and parole[-1] in _CODA:
        parole.pop()
    storpiato = False
    for k in (3, 2, 1):
        if len(parole) > k and prefisso_nome(parole[:k]):
            parole, storpiato = parole[k:], True
            break
    while len(parole) > 1 and parole[0] in _TESTA:
        parole.pop(0)
    return parole, storpiato


def suggerisci(testo: str, name="Calliope") -> dict | None:
    """La forma chiusa che la frase intera forse voleva dire: {"forma", "detto", "forse",
    "corsia"} o None. Solo frasi brevi (al più 4 parole, tolti nome e riempitivi). `corsia`:
    vale «no» nella corsia veloce (solo «annulla» senza oggetto)."""
    t = (testo or "").strip()
    if not t:
        return None
    parole, nome_storpiato = _nucleo(t, name)
    if not parole or len(parole) > 4:
        return None
    nucleo = " ".join(parole)
    if not _VERE.fullmatch(nucleo):
        for forma, rx in FORME:
            if rx.fullmatch(nucleo):
                cosa = re.search(r"(?:" + _NOMI_COSE + r"|tutto)$", nucleo)
                forse = forma
                if cosa:
                    c = cosa.group(0)
                    art = {"sviluppo": "lo ", "tutto": ""}.get(c, "il ")
                    forse = f"{_VERBO[forma]} {art}{c}"
                return {"forma": forma, "detto": t.strip(" .!?…"), "forse": forse,
                        "corsia": forma == "annulla" and not cosa}
    # Il nome storpiato in testa e una forma chiusa dopo («Alla ora, ok.»): il nome
    if nome_storpiato:
        from .risposte import tipo_pezzo
        if tipo_pezzo(nucleo, name):
            return {"forma": "nome", "detto": t.strip(" .!?"), "forse": f"Calliope, {nucleo}",
                    "corsia": False}
    return None


STORPIATA_MSG = ("La frase è una trascrizione automatica e forse è storpiata: «{detto}» "
                 "potrebbe essere «{forse}». Se così ha senso, intendila così; se non è chiaro "
                 "cosa vuole, chiedilo prima di fare qualcosa.")


def nota(sugg: dict | None) -> str:
    """La riga per i dati del turno, "" senza suggerimento."""
    if not sugg:
        return ""
    return STORPIATA_MSG.format(detto=sugg["detto"], forse=sugg["forse"])
