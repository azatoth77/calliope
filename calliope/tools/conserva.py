"""
Il tool dei dati conservati per le misure (12/10/2026, calliope/conserva.py, decisione 0028 T1).

dati_conservati(azione, persona):
- `consenso_voce`: «puoi tenere la mia voce», «sì, registra pure la mia voce». Il consenso è
  della persona che parla: solo con la sua voce riconosciuta sopra soglia in questa frase (mai
  scritto, mai la zona grigia), solo un adulto. Prima la domanda con cosa si tiene e per quanto,
  poi il «sì» nella risposta dopo (come conversazioni_dimentica).
- `revoca_voce`: «non tenere più la mia voce». Subito, senza domanda (è la direzione sicura), e
  le registrazioni che c'erano si cancellano. Basta essere riconosciuti (anche una frase breve).
- `stato`: cosa tengo di te, e per quanto (solo conteggi).
- `svuota`: solo chi amministra, con la voce: tutto, o i dati di una persona (`persona`), dopo
  la domanda e il «sì».

Per chi amministra la voce si tiene finché non dice di no; per gli altri adulti solo dopo il
loro «sì»; per i minori mai. Il dubbio lo scioglie calliope.conserva.decidi.
"""
from .spec import ToolContext, ToolSpec, note_rule
from ..testi import FAMILY, NIENTE

AZIONI = ("consenso_voce", "revoca_voce", "stato", "svuota")
_TURNI_PER_IL_SI = 3


def _final(frase: str, ok: bool = True, **extra) -> dict:
    return {"ok": ok, **({} if ok else {"fatto": NIENTE}), "conferma": frase,
            "risposta_finale": frase, **extra}


def _chi(ctx):
    sc = getattr(ctx, "speaker_ctx", None)
    nome = getattr(sc, "current_speaker", None)
    speakers = getattr(ctx, "speakers", None)
    prof = speakers.get(nome) if (nome and speakers is not None) else None
    return sc, prof


def _giorni(cons) -> int:
    return int(getattr(cons, "giorni", 60) or 60)


def _aperta(cons, chiave: str, turno: int) -> bool:
    """La domanda per `chiave` è stata fatta in una delle ultime risposte?"""
    p = cons.proposte.get(chiave)
    return p is not None and 0 < turno - p <= _TURNI_PER_IL_SI


def _proposta(cons, chiave: str, turno: int) -> bool:
    """True (e la consuma) se la domanda è aperta: questo è il «sì»; altrimenti la apre."""
    if _aperta(cons, chiave, turno):
        cons.proposte.pop(chiave, None)
        return True
    cons.proposte[chiave] = turno
    return False


def _dati_conservati(ctx: ToolContext, azione: str = "", persona: str = "") -> dict:
    from .. import conserva as C
    cons = getattr(ctx, "conserva", None)
    if cons is None:
        return _final("Qui non conservo niente per le misure.", ok=False)
    azione = str(azione or "").strip().lower()
    if azione not in AZIONI:
        return {"ok": False, "fatto": NIENTE, "correggibile": True,
                "errore": f"azione sconosciuta: {azione!r}",
                "cosa_fare": f"usa una di queste: {', '.join(AZIONI)}"}
    sc, prof = _chi(ctx)
    if prof is None:
        return _final("Tengo i dati solo delle persone di casa che riconosco dalla voce; di chi "
                      "non riconosco non conservo niente.", ok=False)
    come = getattr(sc, "identified_by", None)
    turno = int(getattr(ctx, "turno", 0) or 0)
    cat = C.categoria(prof)
    giorni = _giorni(cons)

    if azione == "stato":
        if cat == "minore":
            return _final("Di te non conservo niente: né le parole né la voce.")
        n = cons.registrazioni(prof.id)
        voce = (f"la tua voce sì, {n} registrazioni" if C.consenso_voce(prof)
                and getattr(ctx.cfg, "conserva_voce", True)
                else "la tua voce no")
        return _final(f"Tengo per {giorni} giorni, solo qui, i testi delle nostre conversazioni "
                      f"per migliorare; {voce}.", registrazioni=n)

    if azione == "revoca_voce":
        if come not in ("voce", "breve", "continuita"):
            return _final("Per questo mi serve la tua voce: dimmelo a voce.", ok=False)
        n = cons.imposta_consenso(prof, False)
        note_rule(ctx, "voce_revocata")
        detto = f" e ho cancellato le {n} registrazioni che avevo" if n else ""
        return _final(f"Va bene: non tengo più la tua voce{detto}.", cancellate=n)

    if azione == "consenso_voce":
        if cat == "minore":
            return _final("La voce dei ragazzi non la tengo mai.", ok=False)
        # La richiesta con la voce riconosciuta sopra soglia; il «sì» alla domanda può essere
        # breve: arriva nella conversazione della stessa persona (le conversazioni seguono la
        # voce), mai scritto né dalla zona grigia
        breve_ok = come in ("breve", "continuita") and _aperta(cons, f"voce:{prof.id}", turno)
        if come != "voce" and not breve_ok:
            return _final("Il sì per la tua voce me lo devi dire a voce, dopo avermi chiamata "
                          "per nome, così so che sei proprio tu.", ok=False)
        if not getattr(ctx.cfg, "conserva_voce", True):
            return _final("In questa casa la voce non la tengo per nessuno.", ok=False)
        if C.consenso_voce(prof):
            return _final(f"La tua voce la tengo già, per {giorni} giorni. Se non vuoi più, "
                          "dimmelo.")
        if _proposta(cons, f"voce:{prof.id}", turno):
            cons.imposta_consenso(prof, True)
            note_rule(ctx, "voce_consenso")
            return _final("Grazie: da adesso tengo la tua voce. Se cambi idea, dimmelo e la "
                          "cancello.")
        domanda = (f"Posso tenere le registrazioni della tua voce per {giorni} giorni, solo "
                   "qui in casa, per capirti meglio? Puoi dirmi di smettere quando vuoi.")
        return _final(domanda, ok=False,
                      in_sospeso={"domanda": domanda, "cosa": "tenere la tua voce",
                                  "tool": "dati_conservati",
                                  "argomenti": {"azione": "consenso_voce"}})

    # svuota: solo chi amministra, con la voce (il «sì» breve vale con l'impronta compatibile,
    # come le conferme di chi amministra: conferme.py)
    voce_ok = come == "voce" or (come == "breve" and getattr(sc, "conferma_breve", False))
    if not getattr(prof, "admin", False) or not voce_ok:
        return _final("Svuotare i dati conservati lo può chiedere solo chi amministra, a voce.",
                      ok=False)
    bersaglio = None
    nome = str(persona or "").strip()
    if nome and nome.lower() not in ("tutti", "tutto", "tutte", "di tutti"):
        speakers = getattr(ctx, "speakers", None)
        trova = getattr(speakers, "find", None)
        vero = trova(nome) if callable(trova) else None
        bersaglio = speakers.get(vero or nome) if speakers is not None else None
        if bersaglio is None:
            return _final(f"Non conosco nessuno che si chiami {nome}.", ok=False)
    chiave = f"svuota:{getattr(bersaglio, 'id', '*')}"
    di_chi = f"di {bersaglio.name}" if bersaglio else "di tutti"
    if _proposta(cons, chiave, turno):
        r = (cons.svuota(bersaglio.id, bersaglio.name) if bersaglio else cons.svuota())
        note_rule(ctx, "conservati_svuotati")
        return _final(f"Fatto: ho cancellato i dati conservati {di_chi}.", **r)
    domanda = (f"Cancello i dati conservati {di_chi}: testi dei turni, eventi e registrazioni "
               "della voce? Le conversazioni archiviate e i ricordi restano.")
    return _final(domanda, ok=False,
                  in_sospeso={"domanda": domanda, "cosa": f"cancellare i dati conservati {di_chi}",
                              "tool": "dati_conservati",
                              "argomenti": {"azione": "svuota",
                                            **({"persona": bersaglio.name} if bersaglio else {})}})


def _classe():
    """Per la politica dei tool (calliope/politica.py): «stato» legge; svuotare è distruttivo."""
    from ..politica import AZIONE, Classe
    return Classe(AZIONE, sola_lettura=("azione", frozenset({"stato"})),
                  cosa=lambda a: {"consenso_voce": "tenga la tua voce",
                                  "revoca_voce": "smetta di tenere la tua voce"}.get(
                      str(a.get("azione") or ""), "cancelli i dati conservati"),
                  verbi=r"voce|registr|conserv|ten|tien|salv|cancell|svuot|elimin|dati",
                  distruttiva={"svuota": (
                      lambda a: "cancellare i dati conservati" + (
                          f" di {a.get('persona')}" if a.get("persona") else ""),
                      "Così testi, eventi e registrazioni per le misure non si recuperano.")})


def conserva_specs() -> list[ToolSpec]:
    return [ToolSpec(
        name="dati_conservati",
        description=(
            "I dati che tengo per migliorare (testi dei turni e registrazioni della voce, solo "
            "degli adulti). azione: consenso_voce quando chi parla mi permette di tenere la sua "
            "voce («puoi registrare la mia voce»); revoca_voce quando non vuole più («non "
            "tenere la mia voce»); stato per «cosa tieni di me?»; svuota solo se chi amministra "
            "chiede di cancellare questi dati (persona: di chi, vuoto per tutti). Non per le "
            "conversazioni archiviate (conversazioni_dimentica) né per i ricordi."),
        parameters={"type": "object",
                    "properties": {"azione": {"type": "string", "enum": list(AZIONI)},
                                   "persona": {"type": "string"}},
                    "required": ["azione"]},
        func=_dati_conservati, risk="azione", levels=FAMILY, classe=_classe())]
