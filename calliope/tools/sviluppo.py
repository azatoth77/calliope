"""
I tool della modalità sviluppo (08/10/2026, calliope/sviluppo.py,
docs/ricerche/2026-10-08-modalita-sviluppo.md).

- sviluppo(azione, quale, cambia): lo stato dell'iter di chi amministra. stato; avanti (al
  collaudo → revisione, alla revisione → attivazione con la frase di sfida per un'estensione,
  chiusura per un programma; all'analisi conferma la specifica); analisi (si torna all'analisi
  da qualunque fase, con la modifica detta: il lavoro in corso si ferma, la specifica nuova si
  propone); sospendi, riprendi, esci; promuovi (un programma diventa un'estensione).
- sviluppo_collauda(dati): il collaudo, la versione candidata provata PRIMA dell'approvazione
  (calliope/estensioni/servizio.Estensioni.prova_candidata) o il programma eseguito di nuovo
  (programma_esegui). Il risultato è un dato non fidato (fonte «estensione», come gli est_).

Versione 2 (08/10, docs/ricerche/2026-10-08-modalita-sviluppo.md § 9), con i nomi nuovi (nome
singolare + verbo, prefisso per famiglia; il codice passa sempre dallo sviluppo):
- sviluppo_apri(tipo=estensione|programma, compito, …): apre uno sviluppo (prima estensione_crea
  e delega_lavoro di codice); con `proposta` conferma la specifica proposta;
- sviluppo_passo (era `sviluppo`): «chiudi» chiede conferma e, con l'agente al lavoro, sospende;
  «avanti» a una tappa fa un giro nuovo;
- sviluppo_collauda (era `sviluppo_prova`): un collaudo che non va diventa un caso per l'agente
  e la proposta «Lo faccio correggere?»;
- sviluppo_chiedi(domanda): la domanda a chi l'ha scritto, in sola lettura, con il contesto
  dello sviluppo conservato; la risposta è un dato non fidato;
- sviluppo_correggi(problema): la correzione come passo a sé (la specifica resta), dai file,
  dai collaudi falliti e dalla risposta di sviluppo_chiedi; poi di nuovo collaudo.

E gli agganci per sviluppo_apri e lavoro_affida (tools/estensioni.py, tools/agenti.py): una
richiesta nuova di chi amministra apre lo sviluppo (`apri_se_serve`); mentre uno è aperto, uno
sviluppo diverso non parte (`controlla_nuovo`, regola `sviluppo_altro_bloccato`); proposta e
avvio di un lavoro cambiano la fase (`su_proposta`, `su_avvio`).
"""

from __future__ import annotations

import json
import re

from .spec import ToolContext, ToolSpec, note_rule
from ..testi import FAMILY, NIENTE

AZIONI = ["stato", "avanti", "analisi", "sospendi", "riprendi", "chiudi", "promuovi"]
TIPI_APRI = ["estensione", "programma"]


def _final(text: str, **extra) -> dict:
    return {"ok": True, **extra, "conferma": text, "risposta_finale": text}


def _no(ctx, frase: str, regola: str = "") -> dict:
    if regola:
        note_rule(ctx, regola)
    return _final(frase, ok=False, fatto=NIENTE)


def _svs(ctx):
    from ..sviluppo import servizio
    return servizio(ctx)


def _prof(ctx):
    from . import agenti as ta
    return ta._person(ctx)


def _admin(ctx) -> bool:
    from . import agenti as ta
    from ..conferme import e_admin
    return ta._level(ctx) == "amministra" or e_admin(ctx)


def _schermo(ctx, sv):
    """La scheda dello sviluppo sugli schermi personali di chi parla (se ci sono)."""
    hub = getattr(ctx, "schermi", None)
    svs = _svs(ctx)
    if hub is None or svs is None or sv is None:
        return
    try:
        hub.invia(svs.scheda(sv), hub.mittente(ctx))
    except Exception:  # noqa: BLE001 — lo schermo non ferma la voce
        pass


# ─────────────────────────── agganci per i tool dei lavori ───────────────────────────

def controlla_nuovo(ctx, tool: str, args: dict) -> dict | None:
    """Uno sviluppo nuovo (un'estensione, un programma, un lavoro dell'agente) mentre uno è
    aperto: non parte, Calliope lo dice e propone di sospendere quello aperto (decisione di
    Dario dell'08/10). None se la richiesta è dello sviluppo aperto, o non ce n'è uno."""
    from ..sviluppo import ALLA, estraneo
    sv = estraneo(tool, args, ctx)
    if sv is None:
        return None
    note_rule(ctx, "sviluppo_altro_bloccato")
    frase = (f"Adesso stiamo sviluppando «{sv.titolo}» e siamo {ALLA.get(sv.fase, sv.fase)}: "
             "un'altra cosa per l'agente la comincio dopo. Vuoi che sospenda questo sviluppo? "
             "Lo riprendiamo quando vuoi.")
    return {"ok": False, "fatto": f"{NIENTE}: c'è uno sviluppo aperto, il lavoro NON è partito",
            "conferma": frase, "risposta_finale": frase,
            "in_sospeso": {"domanda": "Vuoi che sospenda questo sviluppo?",
                           "cosa": f"sospendere lo sviluppo di «{sv.titolo}»",
                           "tool": "sviluppo_passo", "argomenti": {"azione": "sospendi"}}}


def apri_se_serve(ctx, tipo: str, compito: str, titolo: str = "", gioco: bool = False,
                  estensione: str | None = None):
    """Una richiesta nuova di chi amministra, con la voce, apre lo sviluppo (già controllati
    permessi e voce dal tool). Restituisce lo sviluppo aperto (nuovo o quello di prima)."""
    from . import agenti as ta
    from ..sviluppo import chi
    svs = _svs(ctx)
    if svs is None or ta._level(ctx) != "amministra":
        return None
    prof = _prof(ctx)
    if prof is None:
        return None
    sv = svs.corrente(chi(ctx))
    if sv is not None:
        svs.tocca(sv)
        return sv
    note_rule(ctx, "sviluppo_aperto")
    sv = svs.apri(prof.id, getattr(prof, "name", ""),
                  "programma" if tipo == "codice" else "estensione", compito,
                  titolo=titolo, gioco=gioco, estensione=estensione)
    return sv


def chiudi_se_vuoto(ctx, motivo: str):
    """L'analisi dice «impossibile qui» o «c'è già»: lo sviluppo appena aperto per questa
    richiesta, senza lavori, si chiude (altrimenti bloccherebbe gli altri per mezz'ora)."""
    from ..sviluppo import chi
    svs = _svs(ctx)
    sv = svs.corrente(chi(ctx)) if svs is not None else None
    if sv is None or sv.fase != "analisi" or sv.lavoro or sv.proposto or sv.versione:
        return
    if any("da" in x or x.get("stato") for x in sv.storia):
        return                               # aveva già fatto strada: resta
    svs.chiudi(sv, motivo)
    note_rule(ctx, "sviluppo_chiuso")


def su_proposta(svc, lav):
    """La proposta di un lavoro: lo sviluppo in analisi che la riceve, o None."""
    svs = getattr(svc, "sviluppi", None)
    if svs is not None:
        try:
            return svs.proposto(lav)
        except Exception as e:  # noqa: BLE001 — la proposta parte comunque
            getattr(svc, "log", print)(f"[SVILUPPO] proposta: {type(e).__name__}: {e}")
    return None


# ─────────────────────────── sviluppo_apri ───────────────────────────

def _tipo(tipo) -> str:
    t = str(tipo or "").strip().lower()
    if t in ("programma", "codice", "script", "programmi"):
        return "programma"
    if t in ("estensione", "estensioni", "funzione", "gioco"):
        return "estensione"
    return ""


def _sviluppo_apri(ctx: ToolContext, tipo: str = "", compito: str = "", nome: str = "",
                   modifica: str = "", proposta: str = "", gioco=False, gia_fatto_da: str = "",
                   come_chiederlo: str = "", vincoli: str = "", file: str = "", allegato=None,
                   **_altro) -> dict:
    """Uno sviluppo nuovo (08/10, versione 2): un'estensione (tools/estensioni._estensione_crea)
    o un programma (tools/agenti._delega_lavoro di tipo codice), con la stessa analisi, la
    stessa proposta e gli stessi permessi di prima. `proposta` = l'id del lavoro proposto: il
    «sì» alla specifica."""
    from . import agenti as ta
    from . import estensioni as te
    t = _tipo(tipo)
    if gioco in (True, "true", "sì", "si", 1) or str(modifica or "").strip():
        t = "estensione"
    prop = str(proposta or "").strip()
    if not t and prop:
        svc = getattr(ctx, "lavori", None)
        prof = ta._person(ctx)
        off = (svc.offerta(getattr(prof, "id", None), int(getattr(ctx, "turno", 0) or 0))
               if svc is not None and hasattr(svc, "offerta") else None)
        if off is not None and getattr(off["lavoro"], "tipo", "") == "codice":
            t = "programma"
    if t == "programma":
        return ta._delega_lavoro(ctx, tipo="codice", compito=compito, vincoli=vincoli,
                                 proposta=proposta, file=file, allegato=allegato)
    return te._estensione_crea(ctx, compito=compito, nome=nome, proposta=proposta,
                               gia_fatto_da=gia_fatto_da, come_chiederlo=come_chiederlo,
                               gioco=gioco, modifica=modifica)


def su_avvio(ctx, svc, lav):
    svs = getattr(svc, "sviluppi", None)
    if svs is None:
        return
    try:
        sv = svs.avviato(lav)
    except Exception as e:  # noqa: BLE001 — il lavoro parte comunque
        getattr(svc, "log", print)(f"[SVILUPPO] avvio: {type(e).__name__}: {e}")
        return
    if sv is not None and ctx is not None:
        note_rule(ctx, "sviluppo_fase")


# ─────────────────────────── sviluppo ───────────────────────────

def _sviluppo(ctx: ToolContext, azione: str = "stato", quale: str = "", cambia: str = "",
              **_altro) -> dict:
    from ..sviluppo import chi
    svs = _svs(ctx)
    if svs is None:
        return _no(ctx, "Qui la modalità sviluppo non c'è: servono gli agenti.")
    prof = _prof(ctx)
    if prof is None or not _admin(ctx):
        return _no(ctx, "La modalità sviluppo è di chi amministra.", "sviluppo_permesso")
    azione = str(azione or "stato").strip().lower()
    azione = {"continua": "avanti", "prosegui": "avanti", "procedi": "avanti",
              "cambia": "analisi", "modifica": "analisi", "esci": "chiudi", "basta": "chiudi",
              "pausa": "sospendi", "riapri": "riprendi"}.get(azione, azione)
    persona = chi(ctx)
    if azione == "riprendi":
        return _riprendi(ctx, svs, persona, quale)
    sv = svs.corrente(persona)
    if azione == "stato":
        return _stato(ctx, svs, sv, persona)
    if sv is None:
        sospesi = svs.trova(persona, quale)
        if sospesi:
            s = sospesi[0]
            frase = f"Lo sviluppo di «{s.titolo}» è sospeso: vuoi riprenderlo?"
            return _final(frase, ok=False, fatto=NIENTE,
                          in_sospeso={"domanda": frase, "cosa": f"riprendere «{s.titolo}»",
                                      "tool": "sviluppo_passo",
                                      "argomenti": {"azione": "riprendi", "quale": s.id}})
        return _no(ctx, "Non c'è nessuno sviluppo aperto.")
    svs.tocca(sv)
    if azione == "sospendi":
        svs.sospendi(sv)
        note_rule(ctx, "sviluppo_sospeso")
        extra = (" L'agente intanto finisce il suo lavoro: te lo dico quando è pronto."
                 if svs.lavoro_attivo(sv) else "")
        _schermo(ctx, sv)
        return _final(f"D'accordo: sospendo lo sviluppo di «{sv.titolo}», eravamo "
                      f"{_alla(sv)}. Quando vuoi, dimmi «riprendiamo lo sviluppo».{extra}",
                      fatto="sviluppo sospeso")
    if azione == "chiudi":
        return _chiudi(ctx, svs, sv)
    if azione == "analisi":
        return _analisi(ctx, svs, sv, prof, str(cambia or "").strip())
    if azione == "promuovi":
        return _promuovi(ctx, svs, sv, prof)
    if azione == "avanti":
        return _avanti(ctx, svs, sv, prof)
    return {"ok": False, "fatto": NIENTE, "errore": f"azione sconosciuta: {azione}",
            "cosa_fare": "azione: " + ", ".join(AZIONI)}


def _in_tappa(svs, sv) -> object:
    """Il lavoro dello sviluppo fermo a una tappa (fine del giro), o None."""
    lav = svs._lavoro(sv.lavoro)
    if lav is not None and getattr(lav, "stato", "") == "in_attesa" and (
            getattr(lav, "risultato", None) or {}).get("esito") == "tappa":
        return lav
    return None


def _chiudi(ctx, svs, sv) -> dict:
    """«Chiudi» (08/10, versione 2; DGX, 11:30: «Ok, chiuso a long», storpiato, chiudeva lo
    sviluppo con l'agente al lavoro, senza domande). Con un lavoro in corso diventa «sospendi»;
    altrimenti chiede conferma, e chiude solo al «sì» a quella domanda (il turno dopo, con
    l'azione in sospeso di sviluppo_passo): una frase breve o storpiata non chiude mai da sola."""
    if svs.lavoro_attivo(sv) or _in_tappa(svs, sv) is not None:
        svs.sospendi(sv, "chiesto di chiudere con l'agente al lavoro")
        note_rule(ctx, "sviluppo_chiudi_sospende")
        _schermo(ctx, sv)
        return _final(f"L'agente sta ancora lavorando a «{sv.titolo}»: invece di chiudere, "
                      "sospendo lo sviluppo. Quando il lavoro è pronto lo riapro al collaudo.",
                      fatto="sviluppo SOSPESO, non chiuso: c'è un lavoro dell'agente in corso")
    from ..sviluppo import CHIUSURA_TURNI
    turno = int(getattr(ctx, "turno", 0) or 0)
    chiesta = sv.chiusura_chiesta
    if (chiesta is not None and 1 <= turno - int(chiesta) <= CHIUSURA_TURNI
            and getattr(ctx, "tool_in_sospeso", None) == "sviluppo_passo"):
        svs.chiudi(sv, "uscita")
        note_rule(ctx, "sviluppo_chiuso")
        extra = ""
        if sv.tipo == "estensione" and sv.estensione and sv.fase in ("collaudo", "revisione",
                                                                      "attivazione"):
            extra = " La versione nuova resta da approvare: puoi approvarla più tardi."
        _schermo(ctx, sv)
        return _final(f"D'accordo: chiudo lo sviluppo di «{sv.titolo}» e torniamo alla "
                      f"conversazione normale.{extra}", fatto="sviluppo chiuso")
    sv.chiusura_chiesta = turno
    svs.tocca(sv)
    note_rule(ctx, "sviluppo_chiudi_conferma")
    extra = ""
    if sv.tipo == "estensione" and sv.estensione and sv.fase in ("collaudo", "revisione",
                                                                  "attivazione"):
        extra = " La versione nuova non è ancora approvata."
    domanda = f"Chiudo lo sviluppo di «{sv.titolo}»?"
    frase = (f"{domanda}{extra} Se vuoi solo una pausa, dimmi «sospendi» e lo riprendiamo "
             "quando vuoi.")
    return _final(frase, ok=False, fatto="NIENTE chiuso: aspetta la conferma",
                  in_sospeso={"domanda": domanda, "cosa": f"chiudere lo sviluppo di «{sv.titolo}»",
                              "tool": "sviluppo_passo", "argomenti": {"azione": "chiudi"}})


def _alla(sv) -> str:
    from ..sviluppo import ALLA
    return ALLA.get(sv.fase, sv.fase)


def _stato(ctx, svs, sv, persona) -> dict:
    if sv is None:
        sospesi = svs.sospesi(persona)
        if not sospesi:
            return _final("Non c'è nessuno sviluppo aperto.", fatto="niente")
        voci = [f"«{s.titolo}» ({_alla(s)})" for s in sospesi[:4]]
        from ..sviluppo import _e
        return _final(("Ho uno sviluppo sospeso: " if len(voci) == 1 else
                       f"Ho {len(voci)} sviluppi sospesi: ") + _e(voci)
                      + ". Dimmi quale riprendere.", fatto="nessuno sviluppo aperto")
    frase = f"Stiamo sviluppando «{sv.titolo}»: {svs.dove(sv)}."
    lav = svs._lavoro(sv.lavoro)
    if sv.fase == "sviluppo" and _in_tappa(svs, sv) is not None:
        frase += " Il lavoro dell'agente è fermo a una tappa: continuo con un altro giro?"
        _schermo(ctx, sv)
        return _final(frase, fatto="stato dello sviluppo", sviluppo=sv.id,
                      in_sospeso={"domanda": "Continuo con un altro giro?",
                                  "cosa": "un altro giro di lavoro", "tool": "sviluppo_passo",
                                  "argomenti": {"azione": "avanti"}})
    if sv.fase == "sviluppo" and lav is not None and lav.stato in ("in_coda", "in_corso"):
        frase += f" L'agente {getattr(lav, 'passo', 'lavora')}, al passo {lav.passi + 1}."
    elif sv.fase == "sviluppo" and sv.nota:
        frase += " Il lavoro dell'agente non è andato: vuoi cambiare qualcosa o lo rifaccio?"
    elif sv.fase == "collaudo":
        n = len(sv.collaudi)
        frase += (f" Hai fatto {'una prova' if n == 1 else f'{n} prove'}." if n else
                  " Puoi provarla prima di approvarla." if sv.tipo == "estensione"
                  else " Puoi provarlo con dati tuoi.")
    _schermo(ctx, sv)
    return _final(frase, fatto="stato dello sviluppo", sviluppo=sv.id)


def _riprendi(ctx, svs, persona, quale: str) -> dict:
    trovati = svs.trova(persona, quale)
    if not trovati:
        aperto = svs.corrente(persona)
        if aperto is not None:
            return _final(f"Lo sviluppo di «{aperto.titolo}» è già aperto: "
                          f"{svs.dove(aperto)}.", fatto="già aperto")
        return _no(ctx, "Non ho sviluppi sospesi da riprendere.")
    sv = trovati[0]
    prima = svs.riprendi(sv)
    note_rule(ctx, "sviluppo_ripreso")
    frase = (f"Ho sospeso «{prima.titolo}». " if prima is not None else "")
    frase += f"Riprendiamo «{sv.titolo}»: {svs.dove(sv)}."
    extra = {}
    if sv.fase == "collaudo":
        frase += (" Puoi provarla prima di approvarla: dimmi «prova con…» e i dati."
                  if sv.tipo == "estensione" else " Puoi provarlo con dati tuoi.")
    elif sv.fase == "revisione":
        frase += " Vuoi andare avanti?"
        extra["in_sospeso"] = {"domanda": "Vuoi andare avanti?", "cosa": "andare avanti",
                               "tool": "sviluppo_passo", "argomenti": {"azione": "avanti"}}
    elif sv.fase == "analisi" and sv.specifica:
        frase += " Vuoi che affidi all'agente la specifica di prima?"
        extra["in_sospeso"] = {"domanda": "Vuoi che la affidi all'agente?",
                               "cosa": "affidare la specifica all'agente",
                               "tool": "sviluppo_passo", "argomenti": {"azione": "avanti"}}
    _schermo(ctx, sv)
    return _final(frase, fatto="sviluppo ripreso", sviluppo=sv.id, **extra)


def _nuovo_lavoro(ctx, svs, sv, prof, compito: str, cambia: str = "") -> dict:
    """Il lavoro dello sviluppo con la specifica nuova, proposto con «Ho capito così: …
    Procedo?» (la persona conferma la specifica: è la fine dell'analisi)."""
    from . import agenti as ta
    svc = getattr(ctx, "lavori", None)
    turno = int(getattr(ctx, "turno", 0) or 0)
    storia = list(getattr(ctx, "storia", None) or [])
    if sv.tipo == "estensione":
        est = getattr(ctx, "estensioni", None)
        if est is None:
            return _no(ctx, "Qui le estensioni non ci sono.")
        if not sv.estensione:
            # Nessuna versione ancora: la richiesta rifatta passa dall'analisi come la prima
            from .estensioni import _estensione_crea
            return _estensione_crea(ctx, compito=compito, nome=sv.titolo, gioco=sv.gioco)
        from ..estensioni.servizio import runtime_testo
        from .estensioni import funzioni_di_calliope
        vincoli = (f"È lo sviluppo dell'estensione «{sv.estensione}»: i suoi file (la versione che "
                   "la persona ha provato) sono già nella cartella; tieni lo stesso nome nel "
                   "manifesto." + (f" Cambiamento chiesto dalla persona: «{cambia}»." if cambia
                                   else "") + " " + funzioni_di_calliope())
        lav = svc.nuovo("estensione", compito, prof.id, prof.name, "amministra", "", "",
                        vincoli, storia)
        lav.titolo = sv.titolo
        lav.estensione = sv.estensione
        lav.gioco = bool(sv.gioco)
        lav.file_iniziali = {"calliope_estensione.py": runtime_testo(),
                             **est.file_per_modifica(sv.estensione, candidata=True)}
    else:
        from ..sviluppo import file_di_codice
        vincoli = ("Riparti dal programma di prima: i suoi file sono già nella cartella."
                   + (f" Cambiamento chiesto dalla persona: «{cambia}»." if cambia else ""))
        lav = svc.nuovo("codice", compito, prof.id, prof.name, "amministra", "", "", vincoli,
                        storia)
        lav.titolo = sv.titolo
        lav.file_iniziali = file_di_codice(sv.cartella) if sv.cartella else {}
    lav.specifica = compito
    return ta._proponi(ctx, svc, lav, turno)


def _analisi(ctx, svs, sv, prof, cambia: str) -> dict:
    """Si torna all'analisi da qualunque fase: il lavoro in corso si ferma, la specifica con la
    modifica si propone (la persona la conferma con il «sì»)."""
    svc = getattr(ctx, "lavori", None)
    if svc is None:
        return _no(ctx, "Qui non ci sono agenti.")
    note_rule(ctx, "sviluppo_analisi")
    fermato = ""
    if svs.lavoro_attivo(sv) or (svs._lavoro(sv.lavoro) is not None
                                 and svs._lavoro(sv.lavoro).stato == "in_attesa"):
        res = svc.annulla(prof.id, tutti_di_tutti=True, quale=sv.lavoro)
        if res.get("ok"):
            fermato = "Ho fermato il lavoro dell'agente. "
    svs.passa(sv, "analisi", cambia or "torna all'analisi")
    sv.lavoro, sv.nota = None, ""
    svs.tocca(sv)
    if not cambia:
        frase = fermato + "D'accordo, torniamo all'analisi: cosa vuoi cambiare?"
        _schermo(ctx, sv)
        return _final(frase, fatto="sviluppo all'analisi: manca la modifica",
                      in_sospeso={"domanda": frase, "cosa": "la modifica allo sviluppo",
                                  "tool": "sviluppo_passo",
                                  "argomenti": "azione = analisi, cambia = la modifica come "
                                               "detta dalla persona"})
    base = (sv.specifica or sv.richiesta or "").strip().rstrip(".")
    compito = f"{base}. Con questa modifica: {cambia}" if base else cambia
    out = _nuovo_lavoro(ctx, svs, sv, prof, compito, cambia)
    if isinstance(out, dict) and fermato:
        for k in ("conferma", "risposta_finale"):
            if isinstance(out.get(k), str):
                out[k] = fermato + out[k]
    _schermo(ctx, sv)
    return out


def _avanti(ctx, svs, sv, prof) -> dict:
    from . import agenti as ta
    svc = getattr(ctx, "lavori", None)
    if sv.fase == "analisi":
        if sv.proposto and ta._offerta_di(ctx, svc, sv.proposto):
            return ta._delega_lavoro(ctx, proposta=sv.proposto)
        if sv.specifica:
            return _nuovo_lavoro(ctx, svs, sv, prof, sv.specifica)
        return _no(ctx, "Siamo ancora all'analisi: prima dimmi cosa deve fare.")
    if sv.fase == "sviluppo":
        tappa = _in_tappa(svs, sv)
        if tappa is not None:
            # Una tappa (08/10, versione 2): «continua» → un giro nuovo con il contesto
            frase = svc.continua(tappa) if hasattr(svc, "continua") else None
            if frase:
                note_rule(ctx, "sviluppo_tappa_continua")
                svs.tocca(sv)
                return _final(frase, fatto="un altro giro avviato: NON è ancora finito",
                              lavoro=tappa.id)
        if svs.lavoro_attivo(sv):
            return _stato(ctx, svs, sv, sv.persona)
        frase = ("Il lavoro dell'agente non è andato: vuoi cambiare qualcosa, o lo rifaccio "
                 "così?")
        return _final(frase, ok=False, fatto=NIENTE,
                      in_sospeso={"domanda": frase, "cosa": "rifare il lavoro",
                                  "tool": "sviluppo_passo",
                                  "argomenti": "azione = analisi, cambia = la modifica detta "
                                               "(vuota per rifarlo così)"})
    if sv.fase == "collaudo":
        return _revisione(ctx, svs, sv)
    if sv.fase in ("revisione", "attivazione"):
        if sv.tipo == "programma":
            svs.chiudi(sv, "consegnato")
            note_rule(ctx, "sviluppo_chiuso")
            _schermo(ctx, sv)
            return _final(f"Fatto: lo sviluppo di «{sv.titolo}» è chiuso. Il programma resta "
                          "nella cartella Lavori: per usarlo di nuovo, chiedimi di eseguirlo.",
                          fatto="sviluppo chiuso")
        est = getattr(ctx, "estensioni", None)
        if est is None or not sv.estensione:
            return _no(ctx, "Qui le estensioni non ci sono.")
        svs.passa(sv, "attivazione", "avanti")
        out = est.gestisci(ctx, "approva", sv.estensione)
        fatto = str((out or {}).get("fatto") or "") if isinstance(out, dict) else ""
        if isinstance(out, dict) and out.get("ok") is False and not out.get("in_sospeso")                 and "frase di conferma" not in fatto and "serve la voce" not in fatto:
            # Non si può approvare (test, testi): si resta alla revisione
            svs.passa(sv, "revisione", "approvazione non riuscita")
        return out
    return _no(ctx, "Non c'è niente da far andare avanti.")


def _revisione(ctx, svs, sv) -> dict:
    """Dal collaudo alla revisione: permessi, rete, analisi del codice, test, collaudi e
    differenze, detti in breve e per intero sulla scheda."""
    from ..sviluppo import misura_programma
    collaudi = sv.collaudi
    riusciti = sum(1 for c in collaudi if c.get("ok"))
    detto_coll = ("Nessuna prova fatta." if not collaudi else
                  f"Prove: {len(collaudi)}, " + ("tutte riuscite." if riusciti == len(collaudi)
                                                 else f"{riusciti} riuscite."))
    if sv.tipo == "estensione":
        est = getattr(ctx, "estensioni", None)
        rev = est.revisione(sv.estensione) if est is not None and sv.estensione else None
        if rev is None:
            return _no(ctx, "Non c'è una versione da rivedere: forse è già stata approvata.")
        sv.revisione = rev["testo"] + f"\n- {detto_coll}"
        svs.passa(sv, "revisione", "avanti dal collaudo")
        note_rule(ctx, "sviluppo_revisione")
        _schermo(ctx, sv)
        if not rev["approvabile"]:
            return _final(f"{rev['frase']} {detto_coll} Così non si può approvare: dimmi cosa "
                          "correggere.", fatto="revisione detta")
        frase = f"{rev['frase']} {detto_coll} Vuoi attivarla? Ti chiederò la frase di conferma."
        return _final(frase, fatto="revisione detta: NON è ancora attiva",
                      in_sospeso={"domanda": "Vuoi attivarla?",
                                  "cosa": f"attivare «{sv.titolo}»", "tool": "sviluppo_passo",
                                  "argomenti": {"azione": "avanti"}})
    # Un programma: file, righe, test, prove; e se è grande, la proposta di un'estensione
    misura = misura_programma(sv.cartella)
    lav = svs._lavoro(sv.lavoro)
    test = ((getattr(lav, "risultato", None) or {}).get("test") if lav is not None else None) \
        or _test_su_disco(sv.cartella)
    t = ""
    if isinstance(test, dict) and test.get("eseguiti"):
        k, f = int(test.get("eseguiti") or 0), int(test.get("falliti") or 0) + int(
            test.get("errori") or 0)
        t = f" Test: {k - f} su {k} passano." if f else f" Test: passano, {k} su {k}."
    frase = (f"Revisione di «{sv.titolo}»: {misura['file']} "
             + ("file" if misura["file"] != 1 else "file") + f" di codice, {misura['righe']} "
             f"righe.{t} {detto_coll} Il codice è sullo schermo, se ce l'hai.")
    sv.revisione = (f"- File di codice: {misura['file']}\n- Righe: {misura['righe']}\n"
                    f"- {t.strip() or 'Test: nessuno'}\n- {detto_coll}")
    svs.passa(sv, "revisione", "avanti dal collaudo")
    note_rule(ctx, "sviluppo_revisione")
    soglia = int(getattr(ctx.cfg, "sviluppo_programma_righe", 150) or 150)
    grande = misura["righe"] >= soglia or misura["file"] >= 3 or len(collaudi) >= 3
    _schermo(ctx, sv)
    if grande and not sv.proposta_estensione:
        sv.proposta_estensione = True
        svs.tocca(sv)
        note_rule(ctx, "sviluppo_proposta_estensione")
        domanda = ("È un programma bello grosso: vuoi che diventi un'estensione? Un programma si "
                   "esegue adesso e basta; un'estensione resta, la richiami a voce quando vuoi, "
                   "ha i permessi approvati da te e le sue versioni.")
        return _final(f"{frase} {domanda}", fatto="revisione detta",
                      in_sospeso={"domanda": domanda, "cosa": "farne un'estensione",
                                  "tool": "sviluppo_passo", "argomenti": {"azione": "promuovi"}})
    frase += " Va bene così?"
    return _final(frase, fatto="revisione detta",
                  in_sospeso={"domanda": "Va bene così?", "cosa": "chiudere lo sviluppo",
                              "tool": "sviluppo_passo", "argomenti": {"azione": "avanti"}})


def _test_su_disco(cartella):
    from pathlib import Path
    try:
        dati = json.loads((Path(cartella) / "lavoro.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return dati.get("test") if isinstance(dati, dict) else None


def _promuovi(ctx, svs, sv, prof) -> dict:
    """Un programma diventa un'estensione (decisione di Dario dell'08/10: chiesto, con la
    differenza spiegata): lo sviluppo del programma si chiude, si apre quello dell'estensione
    con i file del programma (sotto programma/ nella cartella dell'agente)."""
    if sv.tipo != "programma":
        return _no(ctx, "È già un'estensione.")
    if sv.fase not in ("collaudo", "revisione"):
        return _no(ctx, "Prima finiamo il programma: poi, se vuoi, ne facciamo un'estensione.")
    note_rule(ctx, "sviluppo_promosso")
    svs.chiudi(sv, "diventa estensione")
    if sv.cartella:
        svs.da_programma[prof.id] = sv.cartella
    spec = (sv.specifica or sv.richiesta or sv.titolo).strip().rstrip(".")
    compito = (f"Un'estensione di Calliope che fa quello che fa il programma «{sv.titolo}»: "
               f"{spec}.")
    from .estensioni import _estensione_crea
    return _estensione_crea(ctx, compito=compito, nome=sv.titolo)


# ─────────────────────────── sviluppo_collauda ───────────────────────────

def _argomenti(m: dict, dati) -> dict:
    """I dati della prova come li passa il modello («Bergamo», «citta: Bergamo», un oggetto)
    → gli input dell'estensione. Una conversione di forma (principio 10)."""
    props = list(((m or {}).get("input") or {}).get("properties") or {})
    req = list(((m or {}).get("input") or {}).get("required") or [])
    if isinstance(dati, dict):
        return {k: v for k, v in dati.items() if k in props} or (
            {props[0]: next(iter(dati.values()))} if props and dati else {})
    s = str(dati or "").strip()
    if not s or not props:
        return {}
    if s.startswith("{"):
        try:
            return _argomenti(m, json.loads(s))
        except ValueError:
            pass
    coppie = dict((k.strip().lower(), v.strip()) for k, v in
                  re.findall(r"([A-Za-zà-ù_]+)\s*[:=]\s*([^,;]+)", s))
    if coppie and any(k in props for k in coppie):
        return {k: v for k, v in coppie.items() if k in props}
    primo = req[0] if req else props[0]
    return {primo: s}


def _fallito(out, ris) -> bool:
    """Il collaudo non è andato, per il codice (08/10, versione 2): l'esecuzione si è fermata
    con un errore, o il risultato dell'estensione ha un campo d'errore. Un risultato che dice
    «non trovato» a parole lo giudica la persona (e il modello)."""
    if not isinstance(out, dict):
        return True
    if out.get("errore") or (out.get("ok") is False and "risultati" not in out):
        return True
    if isinstance(ris, dict):
        if ris.get("errore") or ris.get("error") or ris.get("ok") is False:
            return True
    return False


def _sviluppo_prova(ctx: ToolContext, dati: str = "", **_altro) -> dict:
    from ..sviluppo import chi
    svs = _svs(ctx)
    if svs is None:
        return _no(ctx, "Qui la modalità sviluppo non c'è.")
    prof = _prof(ctx)
    if prof is None or not _admin(ctx):
        return _no(ctx, "Il collaudo è di chi amministra.", "sviluppo_permesso")
    sv = svs.corrente(chi(ctx))
    if sv is None:
        return _no(ctx, "Non c'è nessuno sviluppo aperto da provare.")
    if sv.fase in ("analisi", "sviluppo"):
        return _no(ctx, f"Non c'è ancora niente da provare: siamo {_alla(sv)}.")
    svs.tocca(sv)
    detti = dati if isinstance(dati, str) else json.dumps(dati, ensure_ascii=False)
    if sv.tipo == "estensione":
        est = getattr(ctx, "estensioni", None)
        if est is None or not sv.estensione:
            return _no(ctx, "Qui le estensioni non ci sono.")
        n = est.archivio.candidata(sv.estensione)
        m = est.archivio.manifesto(sv.estensione, n) if n else None
        if m is None:
            return _no(ctx, "Non c'è una versione nuova da provare.")
        out = est.prova_candidata(ctx, sv.estensione, _argomenti(m, dati))
        ok = isinstance(out, dict) and out.get("risultati") is not None
        ris = (out or {}).get("risultati") if ok else None
        esito = (ris.get("da_dire") if isinstance(ris, dict) and ris.get("da_dire")
                 else json.dumps(ris, ensure_ascii=False) if ris is not None
                 else str((out or {}).get("errore") or (out or {}).get("conferma") or ""))
    else:
        from . import agenti as ta
        lav_id = sv.lavoro if svs._lavoro(sv.lavoro) is not None else ""
        out = ta._lavori_esegui(ctx, lavoro=lav_id, dati=dati)
        ok = bool((out or {}).get("ok"))
        esito = str((out or {}).get("conferma") or "")
    if sv.tipo == "estensione":
        fallito = _fallito(out, (out or {}).get("risultati") if isinstance(out, dict) else None)
        # Un rifiuto prima dell'esecuzione (file cambiati, contenitore spento, un gioco) non è
        # un collaudo: si dice e basta
        prima = isinstance(out, dict) and out.get("risultati") is None and not out.get("errore")
        if prima:
            return out
    else:
        fallito = not ok
    svs.collaudo(sv, detti, not fallito, esito)
    note_rule(ctx, "sviluppo_collauda")
    _schermo(ctx, sv)
    if fallito:
        # Un collaudo che non va diventa un caso per l'agente (versione 2): la frase la dice il
        # codice (niente testo dell'estensione), e il «sì» va a sviluppo_correggi
        note_rule(ctx, "sviluppo_collaudo_fallito")
        cosa = f"con «{detti}»" if detti else "senza dati"
        domanda = "Lo faccio correggere?"
        frase = (f"La prova {cosa} non è andata: si è fermata con un errore. I dettagli sono "
                 f"sulla scheda dello sviluppo. {domanda}")
        return _final(frase, ok=False, fatto="collaudo NON riuscito",
                      in_sospeso={"domanda": domanda, "tool": "sviluppo_correggi",
                                  "cosa": f"far correggere «{sv.titolo}» all'agente",
                                  "argomenti": {"problema": f"il collaudo {cosa} si ferma con "
                                                            "un errore"}})
    return out


# ─────────────────────────── sviluppo_chiedi ───────────────────────────

def _sviluppo_chiedi(ctx: ToolContext, domanda: str = "", **_altro) -> dict:
    """La domanda a chi ha scritto il codice (08/10, versione 2; DGX, 11:13: «Perché?» dopo
    «Impossibile cercare la città», e la voce improvvisava). L'agente risponde in sola lettura,
    con il contesto dello sviluppo conservato; la risposta è un dato non fidato (fonte agente)."""
    from ..sviluppo import chi, chiedi_agente
    svs = _svs(ctx)
    if svs is None:
        return _no(ctx, "Qui la modalità sviluppo non c'è.")
    prof = _prof(ctx)
    if prof is None or not _admin(ctx):
        return _no(ctx, "Le domande a chi scrive il codice sono di chi amministra.",
                   "sviluppo_permesso")
    sv = svs.corrente(chi(ctx))
    if sv is None:
        return _no(ctx, "Non c'è nessuno sviluppo aperto: di quale codice parli?")
    if sv.fase == "analisi" and not (sv.estensione or sv.cartella or sv.lavoro):
        return _no(ctx, "Non c'è ancora codice da spiegare: siamo all'analisi.")
    domanda = str(domanda or "").strip() or str(getattr(ctx, "user_text", "") or "").strip()
    if not domanda:
        return {"ok": False, "fatto": NIENTE, "errore": "manca la domanda",
                "cosa_fare": "richiama con domanda = la domanda della persona come detta"}
    svc = getattr(ctx, "lavori", None)
    svs.tocca(sv)
    tempo = float(getattr(ctx.cfg, "sviluppo_chiedi_s", 60.0) or 60.0)
    r, esito = chiedi_agente(svc, domanda, svs.testo_per_agente(sv), tempo)
    if r is None:
        note_rule(ctx, "sviluppo_chiedi_guasto")
        getattr(svc, "log", print)(f"[SVILUPPO] {sv.id}: domanda all'agente: {esito}")
        return _final("Adesso chi l'ha scritta non mi risponde"
                      + (" in tempo" if esito == "tempo" else "")
                      + ". Riprova tra poco, oppure lo faccio correggere?", ok=False,
                      fatto=NIENTE, guasto="un guasto di adesso, non una cosa che non sai fare",
                      in_sospeso={"domanda": "Lo faccio correggere?", "tool": "sviluppo_correggi",
                                  "cosa": f"far correggere «{sv.titolo}»",
                                  "argomenti": {"problema": domanda}})
    svs.chiesto(sv, domanda, r)
    note_rule(ctx, "sviluppo_chiedi")
    _schermo(ctx, sv)
    out = {"ok": True, "chi_risponde": "l'agente che ha scritto il codice",
           "risposta": r.get("voce") or "", "serve_correzione": bool(r.get("serve_correzione")),
           "dettagli": "sullo schermo, nella scheda dello sviluppo",
           "cosa_fare": ("di' in breve la risposta, come risposta di chi l'ha scritta"
                         + (", e chiedi «Lo faccio correggere?»" if r.get("serve_correzione")
                            else ""))}
    if r.get("serve_correzione"):
        out["in_sospeso"] = {"domanda": "Lo faccio correggere?", "tool": "sviluppo_correggi",
                             "cosa": f"far correggere «{sv.titolo}»",
                             "argomenti": {"problema": str(r.get("cosa_correggere") or domanda)
                                           [:300]}}
    return out


# ─────────────────────────── sviluppo_correggi ───────────────────────────

def _sviluppo_correggi(ctx: ToolContext, problema: str = "", **_altro) -> dict:
    """La correzione come passo a sé (08/10, versione 2; DGX, 11:15: «fai revisionare il codice
    all'agente» tornava all'analisi e rileggeva la specifica). La specifica resta: l'agente
    riparte dai suoi file, dai collaudi che non vanno e dalla risposta di sviluppo_chiedi; poi
    di nuovo collaudo. A una tappa è «cambia e continua»: il giro nuovo con la nota."""
    from ..sviluppo import chi
    svs = _svs(ctx)
    if svs is None:
        return _no(ctx, "Qui la modalità sviluppo non c'è.")
    prof = _prof(ctx)
    if prof is None or not _admin(ctx):
        return _no(ctx, "Le correzioni sono di chi amministra.", "sviluppo_permesso")
    sv = svs.corrente(chi(ctx))
    if sv is None:
        return _no(ctx, "Non c'è nessuno sviluppo aperto da correggere.")
    svc = getattr(ctx, "lavori", None)
    problema = str(problema or "").strip()
    tappa = _in_tappa(svs, sv)
    if tappa is not None:
        frase = svc.continua(tappa, problema) if hasattr(svc, "continua") else None
        if frase:
            note_rule(ctx, "sviluppo_tappa_cambia")
            svs.tocca(sv)
            return _final(frase, fatto="un altro giro avviato con la nota: NON è ancora finito",
                          lavoro=tappa.id)
    if svs.lavoro_attivo(sv):
        return _final("L'agente ci sta già lavorando: te lo dico quando è pronto, e poi lo "
                      "proviamo.", ok=False, fatto=NIENTE)
    if sv.fase == "analisi" and not (sv.estensione or sv.cartella):
        return _no(ctx, "Non c'è ancora codice da correggere: prima finiamo l'analisi.")
    # Un collaudo riuscito per il codice ma sbagliato per la persona: è lui il caso
    if problema and sv.collaudi and sv.collaudi[-1].get("ok") and \
            not sv.collaudi[-1].get("giudizio"):
        sv.collaudi[-1]["giudizio"] = problema[:200]
    falliti = [c for c in sv.collaudi if not c.get("ok") or c.get("giudizio")][-5:]
    casi = "; ".join(f"«{c.get('dati') or 'senza dati'}» → {c.get('esito') or 'errore'}"
                     + (f" (la persona: {c['giudizio']})" if c.get("giudizio") else "")
                     for c in falliti)
    diagnosi = next((q for q in reversed(sv.chiesti) if q.get("dettagli") or q.get("voce")),
                    None)
    vincoli = (f"È una CORREZIONE dello sviluppo «{sv.titolo}»: la specifica NON cambia "
               f"(«{(sv.specifica or sv.richiesta)[:500]}»). I file della versione che la "
               "persona ha provato sono già nella cartella: riparti da quelli, non riscrivere da "
               "zero."
               + (f" Collaudi che non vanno (dati → esito): {casi}." if casi else "")
               + (f" Diagnosi di chi l'ha scritto, alla domanda «{diagnosi['domanda']}»: "
                  f"{diagnosi.get('dettagli') or diagnosi.get('voce')}"
                  + (f" Da correggere: {diagnosi['cosa_correggere']}."
                     if diagnosi.get("cosa_correggere") else "") if diagnosi else "")
               + (f" Problema detto dalla persona: «{problema}»." if problema else "")
               + " Trova la causa, correggi il codice, aggiungi un test con ogni caso che non "
                 "andava, rifai i test, poi consegna.")
    lav = _lavoro_dello_sviluppo(ctx, svc, sv, prof, sv.specifica or sv.richiesta, vincoli)
    if isinstance(lav, dict):
        return lav
    lav.correzione = True
    with svs._lock:
        sv.correzioni += 1
    svs.passa(sv, "sviluppo", "correzione" + (f": {problema[:80]}" if problema else ""))
    note_rule(ctx, "sviluppo_correzione")
    from . import agenti as ta
    out = ta._avvia(ctx, svc, lav)
    caso = falliti[-1].get("dati") if falliti else ""
    frase = ("D'accordo: lo faccio correggere a chi l'ha scritto. Ci lavora in secondo piano; "
             "quando è pronto rifacciamo la prova" + (f" con «{caso}»" if caso else "") + ".")
    out["conferma"] = out["risposta_finale"] = frase
    _schermo(ctx, sv)
    return out


def _lavoro_dello_sviluppo(ctx, svc, sv, prof, compito: str, vincoli: str):
    """Il lavoro dell'agente sui file dello sviluppo (correzione): per un'estensione la
    versione provata, con lo stesso nome; per un programma la sua cartella."""
    storia = list(getattr(ctx, "storia", None) or [])
    if sv.tipo == "estensione":
        est = getattr(ctx, "estensioni", None)
        if est is None or not sv.estensione:
            return _no(ctx, "Qui le estensioni non ci sono.")
        from ..estensioni.servizio import runtime_testo
        from .estensioni import funzioni_di_calliope
        v = (f"È lo sviluppo dell'estensione «{sv.estensione}»: tieni lo stesso nome nel "
             f"manifesto. {vincoli} {funzioni_di_calliope()}")
        lav = svc.nuovo("estensione", compito, prof.id, prof.name, "amministra", "", "", v,
                        storia)
        lav.estensione = sv.estensione
        lav.gioco = bool(sv.gioco)
        lav.file_iniziali = {"calliope_estensione.py": runtime_testo(),
                             **est.file_per_modifica(sv.estensione, candidata=True)}
    else:
        from ..sviluppo import file_di_codice
        lav = svc.nuovo("codice", compito, prof.id, prof.name, "amministra", "", "", vincoli,
                        storia)
        lav.file_iniziali = file_di_codice(sv.cartella) if sv.cartella else {}
    lav.titolo = sv.titolo
    lav.specifica = compito
    return lav


def sviluppo_apri_spec(file_pc: bool = False, allegati: bool = False) -> ToolSpec:
    """sviluppo_apri (08/10, versione 2): estensioni e programmi, con `file` e `allegato` come
    per i lavori quando ci sono il PC e gli allegati."""
    props = {"tipo": {"type": "string", "enum": TIPI_APRI},
             "compito": {"type": "string"}, "nome": {"type": "string"},
             "modifica": {"type": "string"},
             "gia_fatto_da": {"type": "string"}, "come_chiederlo": {"type": "string"},
             "proposta": {"type": "string"}, "gioco": {"type": "boolean"}}
    if file_pc:
        props["file"] = {"type": "string"}
    if allegati:
        props["allegato"] = {"type": "integer"}
    return ToolSpec(
        name="sviluppo_apri",
        description=(
            "Apre lo sviluppo di qualcosa che l'agente scrive in codice. tipo estensione: una "
            "funzione permanente di Calliope, che resta e si usa a voce («fammi una funzione che "
            "converte le unità di misura»), o una versione nuova di un'estensione che c'è («falla "
            "funzionare per ogni città», «correggila»: modifica = il suo nome); gioco=true per un "
            "gioco sullo schermo. tipo programma: uno script o un programma da usare adesso, in "
            "Python o C# («scrivimi uno script che rinomina le foto»)"
            + (", anche su un file della persona sul PC (file = il nome detto)" if file_pc
               else "")
            + (" o allegato (allegato = il numero)" if allegati else "")
            + ". NON per domande brevi di programmazione: rispondi tu. compito: cosa deve fare, "
            "con i dati come detti. nome: un nome breve per un'estensione nuova. gia_fatto_da: se uno "
            "dei tuoi tool fa "
            "già la stessa cosa (sommare = calcola), il suo nome, e come_chiederlo: la frase per "
            "chiederlo a voce. Se il risultato finisce con una domanda («Va bene così, o la "
            "cambiamo?»), dopo il sì richiamalo con proposta = l'id proposto (es. «L3»)."),
        parameters={"type": "object", "properties": props, "required": ["compito"]},
        func=_sviluppo_apri, risk="azione", levels=FAMILY)


def sviluppo_specs(file_pc: bool = False, allegati: bool = False) -> list[ToolSpec]:
    return [
        sviluppo_apri_spec(file_pc, allegati),
        ToolSpec(
            name="sviluppo_passo",
            description=("Un passo della modalità sviluppo di un'estensione o di un programma "
                         "(analisi, sviluppo e test, collaudo, revisione, attivazione): stato (a "
                         "che punto è); avanti (la fase dopo: «va bene, andiamo avanti», "
                         "«attivala»; a una tappa del lavoro, «continua»); analisi (si torna "
                         "all'analisi per cambiare cosa deve fare: cambia = la modifica come "
                         "detta); sospendi; riprendi («riprendiamo lo sviluppo del meteo»: quale "
                         "= le parole del titolo); chiudi (chiede conferma); promuovi (un "
                         "programma diventa un'estensione). Cosa fare in ogni fase è nei dati "
                         "del turno."),
            parameters={"type": "object", "properties": {
                "azione": {"type": "string", "enum": AZIONI},
                "quale": {"type": "string"}, "cambia": {"type": "string"}},
                "required": ["azione"]},
            func=_sviluppo, risk="azione", levels=FAMILY),
        ToolSpec(
            name="sviluppo_collauda",
            description=("Il collaudo nella modalità sviluppo: prova la versione nuova "
                         "dell'estensione (non ancora attiva) o il programma, con i dati detti "
                         "(«prova con Bergamo», «provalo con 3 e 5»). dati: i dati come detti."),
            parameters={"type": "object", "properties": {"dati": {"type": "string"}},
                        "required": []},
            func=_sviluppo_prova, risk="azione", levels=FAMILY, non_fidato=True,
            fonte="estensione", announce=("Un attimo.",)),
        ToolSpec(
            name="sviluppo_chiedi",
            description=("Nella modalità sviluppo, una domanda a chi ha scritto il codice: "
                         "perché un collaudo dà quel risultato, come funziona, cosa fa in un "
                         "caso («perché non trova Cerro Maggiore?», «come mai?», «che fonte "
                         "usa?»). Risponde senza cambiare niente. domanda: come detta."),
            parameters={"type": "object", "properties": {"domanda": {"type": "string"}},
                        "required": ["domanda"]},
            func=_sviluppo_chiedi, risk="lettura", levels=FAMILY, non_fidato=True,
            fonte="agente", announce=("Lo chiedo a chi l'ha scritta.",)),
        ToolSpec(
            name="sviluppo_correggi",
            description=("Nella modalità sviluppo, fa correggere il codice da chi l'ha scritto, "
                         "senza cambiare cosa deve fare («correggilo», «fallo sistemare», «sì» a "
                         "«Lo faccio correggere?»; a una tappa, «cambia e continua»). problema: "
                         "cosa non va, come detto. Per cambiare cosa deve fare, invece, "
                         "sviluppo_passo con azione analisi."),
            parameters={"type": "object", "properties": {"problema": {"type": "string"}},
                        "required": []},
            func=_sviluppo_correggi, risk="azione", levels=FAMILY),
    ]
