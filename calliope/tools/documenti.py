"""
I tool documento_*: documenti Word, Excel e PDF creati e modificati a voce
(calliope/documenti/).

Il modello passa solo una richiesta breve (formato e cosa scrivere, come detto); il testo
lo scrive una seconda richiesta a Ollama con lo schema JSON, e il file lo fa il codice.
Il tool aspetta il file per `documenti_attesa_s`: se è pronto lo dice subito, altrimenti
risponde «te lo preparo» e Calliope lo annuncia a file pronto.

Il risultato ha `risposta_finale`: la frase si dice così com'è e il turno finisce senza
un'altra passata del modello (brain.py). Serve due volte: la conferma non passa da Ollama
(che magari sta ancora generando il documento, e la voce aspetterebbe la generazione
intera) e non c'è rischio che il modello legga il documento ad alta voce.

Permessi: familiare o chi amministra (scrive file sul PC), e solo con la voce di una
persona registrata: ogni documento ha un proprietario (UserProfile.id) e si modifica solo
l'ultimo della stessa persona. Gli ospiti ricevono il rifiuto «NON è stata eseguita».
"""

import re

from ..documenti.formato import is_letter
from .spec import ToolContext, ToolSpec, note_rule
from ..testi import FAMILY, NIENTE


_FORMAT_WORDS = {"word": "word", "docx": "word", "doc": "word", "documento": "word",
                 "lettera": "word", "testo": "word", "excel": "excel", "xlsx": "excel",
                 "foglio": "excel", "foglio excel": "excel", "foglio di calcolo": "excel",
                 "pdf": "pdf"}


def _person(ctx: ToolContext):
    name = getattr(ctx.speaker_ctx, "current_speaker", None)
    return ctx.speakers.get(name) if name and ctx.speakers else None


def _said_format(text: str) -> str | None:
    """Il formato nominato nella frase («in PDF», «un Excel», «un documento Word»), se
    ce n'è uno solo. Solo i nomi espliciti e non negati: «foglio» da solo era Excel anche
    in «una lettera su un foglio intestato», e «non in PDF» era PDF (rapporto del 01/10)."""
    t = (text or "").lower()
    neg = r"(?<!non )(?<!non in )(?<!non un )(?<!senza )(?<!no )"
    found = {f for f, pat in (("pdf", neg + r"\bpdf\b"),
                              ("excel", neg + r"\b(excel|xlsx|foglio di calcolo)\b"),
                              ("word", neg + r"\b(word|docx)\b")) if re.search(pat, t)}
    return found.pop() if len(found) == 1 else None


def _format(formato, *texts: str, ctx: ToolContext | None = None) -> str:
    """Il formato dal parametro, ma vince quello detto a voce se è esplicito: il modello
    a volte manda «word» per «fammi un PDF». Una lettera non è mai un foglio Excel."""
    said = _said_format(" ".join(texts))
    if said:
        if said != _FORMAT_WORDS.get(str(formato or "").strip().lower()):
            note_rule(ctx, "formato_detto")
        return said
    if is_letter(*texts) and _FORMAT_WORDS.get(str(formato or "").strip().lower()) == "excel":
        note_rule(ctx, "lettera_non_excel")
        return "word"
    f = _FORMAT_WORDS.get(str(formato or "").strip().lower())
    if f:
        return f
    t = " ".join(texts).lower()
    if re.search(r"\b(tabell|spes|conti|bilanc|budget|totale|somma)", t) and not is_letter(*texts):
        return "excel"
    return "word"


def _schermo_dopo(ctx: ToolContext, job):
    """Se il documento finisce in secondo piano, l'anteprima va agli schermi a file pronto,
    con chi l'ha chiesto adesso (per le schede personali conta chi parlava ora)."""
    hub = getattr(ctx, "schermi", None)
    if hub is None:
        return
    sender = hub.mittente(ctx)
    job.on_scheda = lambda card: hub.invia(card, sender)


def _rifiuto(motivo: str, cosa_dire: str) -> dict:
    return {"ok": False, "fatto": NIENTE, "motivo": motivo, "cosa_dire": cosa_dire}


def _spoken(res: dict, ctx: ToolContext | None = None) -> dict:
    """Il risultato per il modello, con la frase da dire già pronta. L'anteprima per gli
    schermi («scheda») resta solo se ci sono gli schermi: Brain la toglie prima del modello,
    che il testo del documento non lo vede mai."""
    text = res.get("frase") or ""
    drop = {"frase", "annuncio"} | ({"scheda"} if getattr(ctx, "schermi", None) is None
                                    else set())
    out = {k: v for k, v in res.items() if k not in drop}
    if text:
        out["conferma"] = text
        out["risposta_finale"] = text
    return out


def _parla_del_lavoro(testo: str, parole_titolo) -> bool:
    """Il documento chiesto ha almeno 2 parole significative del titolo del lavoro, e sono
    almeno il 40% delle sue (forma della scelta del modello, non della frase della persona)."""
    from ..provenienza import parole
    mie = parole(testo)
    comuni = mie & set(parole_titolo)
    return len(comuni) >= 2 and len(comuni) >= 0.4 * len(mie)


def _documento_crea(ctx: ToolContext, formato: str = "", richiesta: str = "",
                    titolo: str = "") -> dict:
    # Il risultato di un lavoro dell'agente appena detto (07/10: «Me lo fai in Word?» dopo il
    # riassunto di una ricerca → documento_crea con la ricerca riassunta in una riga, 3 volte su
    # 3 col 4B, anche con la descrizione e i dati del turno). Una spinta, una volta per
    # risposta, e solo se il documento chiesto dal modello parla del lavoro (le sue parole
    # sono in buona parte quelle del titolo): una lettera qualunque si fa subito, e se il
    # modello richiama documento_crea il documento nuovo si fa
    rif = getattr(ctx, "lavoro_turno", None)
    if isinstance(rif, dict) and not rif.get("avvisato") and _parla_del_lavoro(
            f"{richiesta} {titolo}", rif.get("parole") or ()):
        rif["avvisato"] = True
        note_rule(ctx, "spinta_documento_lavoro")
        return {"ok": False, "fatto": NIENTE,
                "errore": f"c'è il risultato del lavoro «{rif.get('titolo')}» appena detto",
                "cosa_fare": f"se chi parla vuole quel risultato in Word o in PDF, chiama "
                             f"lavoro_risultato con modo word o pdf e lavoro "
                             f"{rif.get('lavoro')}; se vuole davvero un documento nuovo con "
                             f"altro contenuto, richiama documento_crea"}
    svc = getattr(ctx, "documenti", None)
    if svc is None:
        return {"ok": False, "errore": "documenti non disponibili"}
    prof = _person(ctx)
    if prof is None:
        return _rifiuto("chi sta parlando non è riconosciuto: i documenti si scrivono solo "
                        "per le persone registrate",
                        "spiega che non puoi farlo per questa persona")
    detto = getattr(ctx, "user_text", "") or ""
    richiesta = str(richiesta or "").strip() or detto
    if not richiesta:
        return {"ok": False, "fatto": NIENTE, "errore": "manca cosa scrivere",
                "cosa_fare": "chiedi in breve cosa deve contenere il documento"}
    fmt = _format(formato, detto, richiesta, ctx=ctx)
    if fmt not in svc.formati:
        return {"ok": False, "fatto": NIENTE, "errore": f"il formato {fmt} non è disponibile",
                "formati": list(svc.formati)}
    # Un minore (05/10): per un compito di scuola solo una scaletta (lo decide lo scrittore)
    from .. import minori
    richiesta = richiesta + minori.nota_documento(ctx)
    job = svc.crea(prof.id, prof.name, fmt, richiesta, detto, str(titolo or ""))
    _schermo_dopo(ctx, job)
    res = svc.wait(job, float(getattr(ctx.cfg, "documenti_attesa_s", 4.0)))
    if res is not None:
        return _spoken(res, ctx)
    fem =fmt != "excel" and is_letter(richiesta, detto, str(titolo or ""))
    text = (f"Te la preparo: ci vuole qualche secondo, ti avviso quando è pronta." if fem
            else "Te lo preparo: ci vuole qualche secondo, ti avviso quando è pronto.")
    return {"ok": True, "in_preparazione": True, "formato": fmt,
            "fatto": "il documento è in preparazione, NON è ancora pronto",
            "conferma": text, "risposta_finale": text}


def _documento_modifica(ctx: ToolContext, modifica: str = "") -> dict:
    svc = getattr(ctx, "documenti", None)
    if svc is None:
        return {"ok": False, "errore": "documenti non disponibili"}
    prof = _person(ctx)
    if prof is None:
        return _rifiuto("chi sta parlando non è riconosciuto: può cambiare un documento solo "
                        "chi lo ha fatto preparare",
                        "spiega che non puoi farlo per questa persona")
    detto = getattr(ctx, "user_text", "") or ""
    modifica = str(modifica or "").strip() or detto
    if not modifica:
        return {"ok": False, "fatto": NIENTE, "errore": "manca cosa cambiare",
                "cosa_fare": "chiedi in breve cosa cambiare"}
    # Solo l'ultimo documento della stessa persona: quello di un altro non si tocca. Se
    # la creazione è ancora in corso la modifica si mette in coda dietro (un lavoro alla
    # volta) e legge il documento quando parte.
    if svc.archive.last(prof.id) is None and not svc.busy():
        return {"ok": False, "fatto": NIENTE,
                "errore": "chi parla non ha ancora creato documenti",
                "conferma": "Non trovo un tuo documento da cambiare: prima dimmi cosa preparare.",
                "risposta_finale": "Non trovo un tuo documento da cambiare: prima dimmi cosa "
                                   "preparare."}
    job = svc.modifica(prof.id, prof.name, modifica, detto)
    _schermo_dopo(ctx, job)
    res = svc.wait(job, float(getattr(ctx.cfg, "documenti_attesa_s", 4.0)))
    if res is not None:
        return _spoken(res, ctx)
    text = "Lo sto aggiornando: ti avviso quando è pronto."
    return {"ok": True, "in_preparazione": True,
            "fatto": "la modifica è in corso, NON è ancora pronta",
            "conferma": text, "risposta_finale": text}


_WAIT = ("Subito.", "Va bene.", "Certo, un attimo.")

_LABELS = {"word": "word (lettere, testi, documenti)", "excel": "excel (tabelle con numeri, "
           "spese, totali)", "pdf": "pdf"}


def documenti_specs(formati, agenti: bool = False) -> list[ToolSpec]:
    """I due tool, con l'enum dei formati che ci sono davvero (librerie installate). Con
    `agenti` (c'è lavoro_risultato) documento_crea dice che il risultato di un lavoro
    dell'agente in PDF o in Word non è un documento nuovo (07/10: «Me lo fai in Word?» dopo il
    risultato di una ricerca → documento_crea con la richiesta riassunta, 3 su 3 col 4B)."""
    formati = [f for f in ("word", "excel", "pdf") if f in set(formati or ())]
    if not formati:
        return []
    kinds = ", ".join(_LABELS[f] for f in formati)
    return [
        ToolSpec(
            name="documento_crea",
            description=(f"Crea un documento nuovo e lo salva sul PC: formato {kinds}. "
                         f"richiesta: cosa deve contenere, con TUTTI i dati detti (nomi, "
                         f"cifre, date), come detti a voce: «lettera di disdetta della "
                         f"palestra», «spese di settembre: affitto 800, luce 90, gas 60, con "
                         f"il totale». Il testo lo scrive il programma: tu non scriverlo e non "
                         f"leggerlo. titolo facoltativo."
                         + (" NON per mettere in PDF o in Word il risultato di un lavoro "
                            "dell'agente (una ricerca, una relazione): lavoro_risultato."
                            if agenti else "")),
            parameters={"type": "object",
                        "properties": {"formato": {"type": "string", "enum": formati},
                                       "richiesta": {"type": "string"},
                                       "titolo": {"type": "string"}},
                        "required": ["formato", "richiesta"]},
            func=_documento_crea, risk="azione", levels=FAMILY, announce=_WAIT),
        ToolSpec(
            name="documento_modifica",
            description=("Cambia l'ultimo documento creato da chi parla (lettera, tabella, "
                         "PDF): modifica è il cambiamento come detto a voce, con i dati: "
                         "«cambia la data in 15 ottobre», «aggiungi una riga: internet 30», "
                         "«togli il secondo punto», «il titolo è Spese di casa». Per un "
                         "documento nuovo usa documento_crea."),
            parameters={"type": "object",
                        "properties": {"modifica": {"type": "string"}},
                        "required": ["modifica"]},
            func=_documento_modifica, risk="azione", levels=FAMILY, announce=_WAIT),
    ]
