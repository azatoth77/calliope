"""
I tool dell'ufficio (calliope/ufficio/, 03/10/2026): modelli da compilare, rubrica, fatture.

Tre tool soli, per non allungare il prefisso del prompt:
- modello_compila(modello, dati, proposta): compila un modello (fattura, nota di credito,
  preventivo, DDT e i modelli Word, PowerPoint o JSON dell'utente). I campi li estrae una
  richiesta a parte con lo schema del modello; quelli obbligatori mancanti diventano una
  domanda; i documenti numerati si propongono («… La preparo?») e si emettono con
  `proposta` = l'id, nella risposta dopo e dalla stessa persona.
- anagrafica_cerca(testo): un cliente, fornitore o contatto della rubrica.
- anagrafica_salva(azione, nome, dati, proposta): aggiunge, cambia o toglie un contatto,
  sempre con la proposta e il «sì».

Permessi nel codice: familiari e chi amministra, riconosciuti dalla voce; fatture e note di
credito solo `ufficio_livello_fiscale` (predefinito chi amministra). Gli ospiti non vedono i
tool. La frase da dire è sempre pronta (`risposta_finale`).
"""

import re

from ..schermi.moduli import chiudi_per_voce, offri
from ..conferme import serve_conferma
from .spec import ToolContext, ToolSpec, note_rule, serve_la_voce
from ..testi import FAMILY, NIENTE, RANK

_WAIT = ("Un attimo.", "Vediamo.")


def _person(ctx):
    name = getattr(ctx.speaker_ctx, "current_speaker", None)
    return ctx.speakers.get(name) if name and ctx.speakers else None


def _level(ctx) -> str:
    return getattr(ctx.speaker_ctx, "current_level", "ospite") or "ospite"


def _spoken(res: dict, ctx) -> dict:
    """Il risultato per il modello: la frase pronta, l'anteprima solo con gli schermi."""
    res = dict(res)
    regola = res.pop("regola", None)
    if regola:
        note_rule(ctx, regola)
    text = res.pop("frase", "") or ""
    res.pop("annuncio", None)
    if getattr(ctx, "schermi", None) is None:
        res.pop("scheda", None)
    if text:
        res["conferma"] = text
        res["risposta_finale"] = text
    return res


def _proposta(ctx, proposta) -> str:
    """Solo un id di proposta («U3») conferma: gemma4 manda anche «None» o «sì» alla prima
    richiesta (prova a voce del 03/10), e un valore così vale come richiesta nuova."""
    p = str(proposta or "").strip()
    if p and not re.fullmatch(r"U\d+", p):
        note_rule(ctx, "ufficio_proposta_non_id")
        return ""
    return p


def _non_disponibile() -> dict:
    t = "Qui non posso compilare modelli né usare la rubrica."
    return {"ok": False, "fatto": NIENTE, "conferma": t, "risposta_finale": t}


def _sconosciuto() -> dict:
    t = "Non so chi sei: modelli e rubrica li uso solo per le persone registrate."
    return {"ok": False, "fatto": NIENTE, "conferma": t, "risposta_finale": t}


def _on_scheda(ctx):
    hub = getattr(ctx, "schermi", None)
    if hub is None:
        return None
    sender = hub.mittente(ctx)
    return lambda card: hub.invia(card, sender)


def _modello_compila(ctx: ToolContext, modello: str = "", dati: str = "", proposta: str = "",
                     **_altro) -> dict:
    svc = getattr(ctx, "ufficio", None)
    if svc is None:
        return _non_disponibile()
    prof = _person(ctx)
    if prof is None:
        return _sconosciuto()
    # Scritto da uno schermo personale: le fatture di chi amministra vogliono la voce (03/10)
    from ..ufficio.modelli import risolvi
    m = risolvi(svc.catalogo, str(modello or "")) if modello else None
    serve = getattr(ctx.cfg, "ufficio_livello_fiscale", "amministra")
    if m is not None and m.fiscale and RANK.get(_level(ctx), 0) < RANK.get(serve, 2):
        cosa = "preparare " + ("una nota di credito" if m.tipo == "nota_di_credito"
                               else "una fattura")
        voce = serve_la_voce(ctx, "modello_compila", {"modello": m.nome, "dati": dati}, cosa,
                             serve)
        if voce is not None:
            return voce
        # Chi amministra con una frase che non basta: la frase di sfida (04/10, conferme.py)
        args = {"modello": m.nome, "dati": dati, **({"proposta": proposta} if proposta else {})}
        sfida = serve_conferma(ctx, "modello_compila", args, cosa)
        if sfida is not None:
            return sfida
    # La risposta è arrivata a voce (o scritta nella casella): il modulo aperto si chiude
    chiudi_per_voce(ctx, "modello_compila")
    detto = getattr(ctx, "user_text", "") or ""
    testo = str(dati or "").strip()
    if detto.strip() and detto.strip() not in testo:
        testo = f"{testo}\nFrase detta: {detto.strip()}" if testo else detto.strip()
    livello, on_scheda = _level(ctx), _on_scheda(ctx)
    res = svc.compila(prof.id, prof.name, livello, str(modello or ""), testo,
                      int(getattr(ctx, "turno", 0) or 0), _proposta(ctx, proposta),
                      on_scheda=on_scheda)

    def riprendi(valori, turno, pid=prof.id, nome=prof.name):
        # I dati scritti nel modulo sullo schermo, senza il modello (calliope/schermi/moduli.py)
        return svc.completa_modulo(pid, nome, livello, valori, turno, on_scheda)
    return _spoken(offri(ctx, res, "modello_compila", riprendi, livello), ctx)


def _anagrafica_cerca(ctx: ToolContext, testo: str = "", **_altro) -> dict:
    svc = getattr(ctx, "ufficio", None)
    if svc is None:
        return _non_disponibile()
    prof = _person(ctx)
    if prof is None:
        return _sconosciuto()
    return _spoken(svc.rubrica_cerca(prof.id, str(testo or getattr(ctx, "user_text", ""))),
                   ctx)


def _anagrafica_salva(ctx: ToolContext, azione: str = "aggiungi", nome: str = "",
                      dati: str = "", proposta: str = "", **_altro) -> dict:
    svc = getattr(ctx, "ufficio", None)
    if svc is None:
        return _non_disponibile()
    prof = _person(ctx)
    if prof is None:
        return _sconosciuto()
    detto = getattr(ctx, "user_text", "") or ""
    testo = str(dati or "").strip()
    if detto.strip() and detto.strip() not in testo:
        testo = f"{testo}\nFrase detta: {detto.strip()}" if testo else detto.strip()
    chiudi_per_voce(ctx, "anagrafica_salva")
    res = svc.rubrica_salva(prof.id, _level(ctx), str(azione or "aggiungi"), str(nome or ""),
                            testo, int(getattr(ctx, "turno", 0) or 0), _proposta(ctx, proposta))
    ambito = (res.get("modulo") or {}).pop("ambito", "casa")

    def riprendi(valori, turno, pid=prof.id, ambito=ambito):
        # Il contatto scritto nel modulo sullo schermo, senza il modello
        return svc.rubrica_da_modulo(pid, valori, ambito)
    return _spoken(offri(ctx, res, "anagrafica_salva", riprendi), ctx)


def ufficio_specs(modelli) -> list[ToolSpec]:
    """I tre tool; `modelli`: i nomi dei modelli che si possono compilare qui."""
    modelli = list(modelli or ())
    if not modelli:
        return []
    return [
        ToolSpec(
            name="modello_compila",
            description=(
                "Compila un modello di documento: fattura (elettronica, anche il file XML), "
                "nota di credito, preventivo, ddt (documento di trasporto, bolla) e i modelli "
                "dell'utente. Chiamalo subito con quello che è stato detto, senza chiedere "
                "prima nessun dato: partita IVA, indirizzi, data, numero e scadenza li prende "
                "il programma dalla rubrica e dai dati di chi emette, e quello che manca lo "
                "chiede il risultato. dati: tutto quello che è stato detto, come detto (cliente, "
                "voci, quantità, prezzi). Se mancano dati il risultato è una domanda: alla "
                "risposta richiamalo con lo stesso modello e i dati nuovi. Se il risultato "
                "finisce con «La preparo?» o «Lo preparo?», solo quando chi parla dice sì "
                "richiamalo con proposta = l'id proposto (per esempio «U3»); altrimenti "
                "lascia proposta vuoto. I conti li fa il programma."),
            parameters={"type": "object",
                        "properties": {"modello": {"type": "string", "enum": modelli},
                                       "dati": {"type": "string"},
                                       "proposta": {"type": "string"}},
                        "required": ["modello", "dati"]},
            func=_modello_compila, risk="azione", levels=FAMILY, announce=_WAIT,
            # Dati di terzi (clienti, partite IVA, importi): fuori dal registro dei turni e
            # dal terminale (03/10, analisi di sicurezza S9)
            riservato=True),
        ToolSpec(
            name="anagrafica_cerca",
            description=("Cerca un cliente, fornitore o contatto nella rubrica («che dati ho "
                         "di Rossi?», «la partita IVA di Bianchi»)."),
            parameters={"type": "object", "properties": {"testo": {"type": "string"}},
                        "required": ["testo"]},
            func=_anagrafica_cerca, risk="lettura", levels=FAMILY, riservato=True),
        ToolSpec(
            name="anagrafica_salva",
            description=("Aggiunge, modifica o toglie un cliente, fornitore o contatto della "
                         "rubrica. nome: di chi; dati: quello che è stato detto (partita IVA, "
                         "codice fiscale, indirizzo, CAP, comune, provincia, email, PEC, codice "
                         "destinatario). Il risultato è una proposta con una domanda: solo se "
                         "chi parla dice sì richiamalo con proposta = l'id proposto."),
            parameters={"type": "object",
                        "properties": {"azione": {"type": "string",
                                                  "enum": ["aggiungi", "modifica", "elimina"]},
                                       "nome": {"type": "string"},
                                       "dati": {"type": "string"},
                                       "proposta": {"type": "string"}},
                        "required": ["azione", "nome"]},
            func=_anagrafica_salva, risk="azione", levels=FAMILY, riservato=True),
    ]
