"""
Il tool dei dati conservati per le misure (12/10/2026, calliope/conserva.py, decisione 0028 T1;
dal 16/10 decisione 0031 per i minori).

dati_conservati(azione, persona):
- `consenso_voce`: «puoi tenere la mia voce», «sì, registra pure la mia voce». Il consenso è
  della persona che parla: solo con la sua voce riconosciuta sopra soglia in questa frase (mai
  scritto, mai la zona grigia). Prima la domanda con cosa si tiene e per quanto, poi il «sì» nella
  risposta dopo (come conversazioni_dimentica). **Per un minore** (16/10, decisione 0031) il
  consenso è implicito nella registrazione (lo dà chi amministra registrandolo); dopo una revoca
  lo ridà a mano un suo tutore, con il minore in `persona` («puoi tenere la voce di Leo»), la
  voce sopra soglia e il «sì» con la stessa conferma di `svuota` (breve solo con l'impronta
  compatibile: un minore accanto che dice «sì» non vale); il minore da solo no.
- `revoca_voce`: «non tenere più la mia voce». Subito, senza domanda (è la direzione sicura), e
  le registrazioni che c'erano si cancellano. Basta essere riconosciuti (anche una frase breve).
  Per un minore la revoca un suo tutore (`persona`), con la conferma di `svuota`; non il minore
  da solo.
- `stato`: cosa tengo di te, e per quanto (solo conteggi). Dal 14/10 con `stanza_tenuta` anche
  le righe della conversazione di stanza su disco (per tutta la famiglia, minori compresi). A un
  minore dice che i testi si tengono e che i genitori li possono rileggere.
- `svuota`: solo chi amministra, con la voce: tutto, o i dati di una persona (`persona`), dopo
  la domanda e il «sì». Dal 12/10 sera anche l'archivio delle conversazioni.

Per chi amministra la voce si tiene finché non dice di no; per gli altri adulti solo dopo il
loro «sì»; per i minori finché un tutore non dice di no (consenso implicito nella registrazione,
dal 16/10; fino al 16/10 mai). Il dubbio lo scioglie calliope.conserva.decidi.
"""
from .. import impronte_satellite as _imp_sat
from .. import minori as _minori
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
        stanza = _stanza(cons, prof)
        n = cons.registrazioni(prof.id)
        speakers = getattr(ctx, "speakers", None)
        voce_si = C.consenso_voce(prof, speakers) and getattr(ctx.cfg, "conserva_voce", True)
        extra = ({"righe_stanza": stanza[0]} if stanza is not None else {})
        in_stanza = (f"; per {stanza[1]} giorni anche le tue frasi nella stanza, {stanza[0]}"
                     if stanza is not None else "")
        if cat == "minore":
            # Un minore (16/10, decisione 0031): i testi come per un adulto, e i tutori li
            # possono rileggere; la voce decisa alla registrazione, i tutori la possono togliere
            voce = (f"la tua voce sì, {n} registrazioni, decisa alla registrazione dai tuoi "
                    "genitori" if voce_si else
                    "la tua voce no, l'hanno deciso i tuoi genitori")
            return _final(f"Tengo per {giorni} giorni, solo qui, i testi delle nostre "
                          f"conversazioni, e i tuoi genitori li possono rileggere{in_stanza}; "
                          f"{voce}.", registrazioni=n, **extra)
        voce = f"la tua voce sì, {n} registrazioni" if voce_si else "la tua voce no"
        return _final(f"Tengo per {giorni} giorni, solo qui, i testi delle nostre conversazioni "
                      f"per migliorare{in_stanza}; {voce}.", registrazioni=n, **extra)

    # La voce di chi (16/10, decisione 0031): la persona che parla, o un minore di cui è tutore
    # (`persona`). Il minore da solo non dà né revoca il consenso alla sua voce
    if azione in ("consenso_voce", "revoca_voce"):
        minore_di = None
        nome = str(persona or "").strip()
        if nome:
            b = _trova(ctx, nome)
            if b is None:
                return _final(f"Non conosco nessuno che si chiami {nome}.", ok=False)
            if getattr(b, "id", None) != getattr(prof, "id", None):
                if C.categoria(b) != "minore":
                    return _final(f"Per la voce di {b.name} decide solo {b.name}, a voce.",
                                  ok=False)
                if not _minori.e_tutore(prof, b):
                    return _final(f"Per la voce di {b.name} decidono solo i suoi genitori.",
                                  ok=False)
                minore_di = b
        if minore_di is None and cat == "minore":
            return _final("Per la tua voce decidono i tuoi genitori: chiedi a loro di dirmelo.",
                          ok=False)
        chi = minore_di or prof
        di_chi = f"la voce di {chi.name}" if minore_di is not None else "la tua voce"
        da = prof.id if minore_di is not None else None
        arg_persona = {"persona": chi.name} if minore_di is not None else {}

    # Per la voce di un minore (consenso dato a mano o revoca) la stessa conferma di «svuota»:
    # la voce sopra soglia, o un «sì» breve con l'impronta compatibile (conferma_breve). Così un
    # minore accanto che dice «sì», o il tutore nel dubbio col minore, non decide
    tutore_ok = come == "voce" or (come == "breve" and getattr(sc, "conferma_breve", False))

    if azione == "revoca_voce":
        if minore_di is not None and not tutore_ok:
            return _final(f"Per {di_chi} mi serve la tua voce: dimmelo a voce, dopo avermi "
                          "chiamata per nome.", ok=False)
        if come not in ("voce", "breve", "continuita"):
            return _final("Per questo mi serve la tua voce: dimmelo a voce.", ok=False)
        n = cons.imposta_consenso(chi, False, da=da)
        note_rule(ctx, "voce_revocata")
        detto = f" e ho cancellato le {n} registrazioni che avevo" if n else ""
        return _final(f"Va bene: non tengo più {di_chi}{detto}.", cancellate=n)

    if azione == "consenso_voce":
        # La richiesta con la voce riconosciuta sopra soglia; il «sì» alla domanda può essere
        # breve: arriva nella conversazione della stessa persona (le conversazioni seguono la
        # voce), mai scritto né dalla zona grigia
        chiave = f"voce:{chi.id}" + (f":{prof.id}" if minore_di is not None else "")
        breve_ok = ((tutore_ok if minore_di is not None else come in ("breve", "continuita"))
                    and _aperta(cons, chiave, turno))
        if come != "voce" and not breve_ok:
            return _final(f"Il sì per {di_chi} me lo devi dire a voce, dopo avermi chiamata "
                          "per nome, così so che sei proprio tu.", ok=False)
        if not getattr(ctx.cfg, "conserva_voce", True):
            return _final("In questa casa la voce non la tengo per nessuno.", ok=False)
        if C.consenso_voce(chi, getattr(ctx, "speakers", None)):
            return _final(f"{di_chi[0].upper()}{di_chi[1:]} la tengo già, per {giorni} giorni. "
                          "Se non volete più, ditemelo." if minore_di is not None else
                          f"La tua voce la tengo già, per {giorni} giorni. Se non vuoi più, "
                          "dimmelo.")
        if _proposta(cons, chiave, turno):
            cons.imposta_consenso(chi, True, da=da)
            note_rule(ctx, "voce_consenso")
            if minore_di is not None:
                return _final(f"Grazie: da adesso tengo la voce di {chi.name}. Se cambiate "
                              "idea, ditemelo e la cancello.")
            return _final("Grazie: da adesso tengo la tua voce. Se cambi idea, dimmelo e la "
                          "cancello.")
        if minore_di is not None:
            domanda = (f"Posso tenere le registrazioni della voce di {chi.name} per {giorni} "
                       "giorni, solo qui in casa, per capire meglio come parla? Voi tutori potete "
                       "dirmi di smettere quando volete.")
        else:
            domanda = (f"Posso tenere le registrazioni della tua voce per {giorni} giorni, solo "
                       "qui in casa, per capirti meglio? Puoi dirmi di smettere quando vuoi.")
        return _final(domanda, ok=False,
                      in_sospeso={"domanda": domanda, "cosa": f"tenere {di_chi}",
                                  "tool": "dati_conservati",
                                  "argomenti": {"azione": "consenso_voce", **arg_persona}})

    # svuota: solo chi amministra, con la voce (il «sì» breve vale con l'impronta compatibile,
    # come le conferme di chi amministra: conferme.py)
    voce_ok = come == "voce" or (come == "breve" and getattr(sc, "conferma_breve", False))
    if not getattr(prof, "admin", False) or not voce_ok:
        return _final("Svuotare i dati conservati lo può chiedere solo chi amministra, a voce.",
                      ok=False)
    bersaglio = None
    nome = str(persona or "").strip()
    if nome and nome.lower() not in ("tutti", "tutto", "tutte", "di tutti"):
        bersaglio = _trova(ctx, nome)
        if bersaglio is None:
            # Un conoscente (14/10 sera, decisione 0030 aggiornata): i suoi dati conservati
            # come quelli di un adulto (il profilo resta: «dimentica» col tool conoscenti)
            trova_k = getattr(cons, "trova_conoscenti", None)
            kk = trova_k(nome) if callable(trova_k) else []
            if len(kk) > 1:
                return _final(f"Conosco più di un {nome}: "
                              + ", ".join(k.descrizione() for k in kk[:3])
                              + ". Dimmi il cognome o chi è.", ok=False)
            bersaglio = kk[0] if kk else None
        if bersaglio is None:
            return _final(f"Non conosco nessuno che si chiami {nome}.", ok=False)
    chiave = f"svuota:{getattr(bersaglio, 'id', '*')}"
    di_chi = f"di {bersaglio.name}" if bersaglio else "di tutti"
    if _proposta(cons, chiave, turno):
        nome_b = (None if C.categoria(bersaglio) == "conoscente" else bersaglio.name) \
            if bersaglio else None
        r = (cons.svuota(bersaglio.id, nome_b) if bersaglio else cons.svuota())
        note_rule(ctx, "conservati_svuotati")
        return _final(f"Fatto: ho cancellato i dati conservati {di_chi}.", **r)
    domanda = (f"Cancello i dati conservati {di_chi}: testi dei turni, conversazioni "
               "archiviate, eventi, registrazioni della voce, esercizi e richieste ai tutori"
               + (", conversazione della stanza" if _stanza(cons, None) is not None else "")
               + (", impronte della voce imparate sui satelliti"
                  if _imp_sat.modo(getattr(cons, "cfg", None)) != _imp_sat.SPENTO else "")
               + "? I ricordi restano.")
    return _final(domanda, ok=False,
                  in_sospeso={"domanda": domanda, "cosa": f"cancellare i dati conservati {di_chi}",
                              "tool": "dati_conservati",
                              "argomenti": {"azione": "svuota",
                                            **({"persona": bersaglio.name} if bersaglio else {})}})


def _trova(ctx, nome: str):
    """Il profilo di casa con questo nome (anche storpiato: SpeakerRegistry.find), o None."""
    speakers = getattr(ctx, "speakers", None)
    if speakers is None:
        return None
    trova = getattr(speakers, "find", None)
    vero = trova(nome) if callable(trova) else None
    return speakers.get(vero or nome)


def _stanza(cons, prof):
    """(righe, giorni) del testo della stanza su disco di questa persona (di tutti con None), o
    None con la tenuta spenta (14/10, calliope/stanza/tenuta.py)."""
    t = getattr(cons, "stanza", None)
    if t is None:
        return None
    try:
        n = t.conteggi(getattr(prof, "id", None) if prof is not None else None)["righe"]
    except Exception:  # noqa: BLE001
        return None
    return int(n), int(getattr(t, "giorni", 60) or 60)


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
                      "Così testi, conversazioni, eventi e registrazioni non si "
                      "recuperano.")})


def conserva_specs() -> list[ToolSpec]:
    return [ToolSpec(
        name="dati_conservati",
        description=(
            "I dati che tengo per migliorare (testi dei turni, conversazioni archiviate e "
            "registrazioni della voce, delle persone di casa). azione: consenso_voce quando chi "
            "parla mi permette di tenere la sua voce («puoi registrare la mia voce»), o quella "
            "di un figlio (persona: il nome); revoca_voce quando non vuole più («non "
            "tenere la mia voce»); stato per «cosa tieni di me?»; svuota solo se chi amministra "
            "chiede di cancellare questi dati (persona: di chi, vuoto per tutti). Non quando "
            "chi parla vuole cancellare le sue conversazioni (conversazioni_dimentica) né per "
            "i ricordi."),
        parameters={"type": "object",
                    "properties": {"azione": {"type": "string", "enum": list(AZIONI)},
                                   "persona": {"type": "string"}},
                    "required": ["azione"]},
        func=_dati_conservati, risk="azione", levels=FAMILY, classe=_classe())]
