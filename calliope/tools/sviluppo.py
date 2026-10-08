"""
I tool della modalità sviluppo (08/10/2026, calliope/sviluppo.py,
docs/ricerche/2026-10-08-modalita-sviluppo.md).

- sviluppo(azione, quale, cambia): lo stato dell'iter di chi amministra. stato; avanti (al
  collaudo → revisione, alla revisione → attivazione con la frase di sfida per un'estensione,
  chiusura per un programma; all'analisi conferma la specifica); analisi (si torna all'analisi
  da qualunque fase, con la modifica detta: il lavoro in corso si ferma, la specifica nuova si
  propone); sospendi, riprendi, esci; promuovi (un programma diventa un'estensione).
- sviluppo_prova(dati): il collaudo, la versione candidata provata PRIMA dell'approvazione
  (calliope/estensioni/servizio.Estensioni.prova_candidata) o il programma eseguito di nuovo
  (lavori_esegui). Il risultato è un dato non fidato (fonte «estensione», come gli est_).

E gli agganci per estensione_crea e delega_lavoro (tools/estensioni.py, tools/agenti.py): una
richiesta nuova di chi amministra apre lo sviluppo (`apri_se_serve`); mentre uno è aperto, uno
sviluppo diverso non parte (`controlla_nuovo`, regola `sviluppo_altro_bloccato`); proposta e
avvio di un lavoro cambiano la fase (`su_proposta`, `su_avvio`).
"""

from __future__ import annotations

import json
import re

from .spec import ToolContext, ToolSpec, note_rule
from ..testi import FAMILY, NIENTE

AZIONI = ["stato", "avanti", "analisi", "sospendi", "riprendi", "esci", "promuovi"]


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
                           "tool": "sviluppo", "argomenti": {"azione": "sospendi"}}}


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
    svs = getattr(svc, "sviluppi", None)
    if svs is not None:
        try:
            svs.proposto(lav)
        except Exception as e:  # noqa: BLE001 — la proposta parte comunque
            getattr(svc, "log", print)(f"[SVILUPPO] proposta: {type(e).__name__}: {e}")


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
              "cambia": "analisi", "modifica": "analisi", "chiudi": "esci", "basta": "esci",
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
                                      "tool": "sviluppo",
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
    if azione == "esci":
        svs.chiudi(sv, "uscita")
        note_rule(ctx, "sviluppo_chiuso")
        extra = ""
        if sv.tipo == "estensione" and sv.estensione and sv.fase in ("collaudo", "revisione",
                                                                      "attivazione"):
            extra = " La versione nuova resta da approvare: puoi approvarla più tardi."
        elif svs.lavoro_attivo(sv):
            extra = " Il lavoro dell'agente va avanti: te lo dico quando è finito."
        _schermo(ctx, sv)
        return _final(f"D'accordo: chiudo lo sviluppo di «{sv.titolo}» e torniamo alla "
                      f"conversazione normale.{extra}", fatto="sviluppo chiuso")
    if azione == "analisi":
        return _analisi(ctx, svs, sv, prof, str(cambia or "").strip())
    if azione == "promuovi":
        return _promuovi(ctx, svs, sv, prof)
    if azione == "avanti":
        return _avanti(ctx, svs, sv, prof)
    return {"ok": False, "fatto": NIENTE, "errore": f"azione sconosciuta: {azione}",
            "cosa_fare": "azione: " + ", ".join(AZIONI)}


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
                               "tool": "sviluppo", "argomenti": {"azione": "avanti"}}
    elif sv.fase == "analisi" and sv.specifica:
        frase += " Vuoi che affidi all'agente la specifica di prima?"
        extra["in_sospeso"] = {"domanda": "Vuoi che la affidi all'agente?",
                               "cosa": "affidare la specifica all'agente",
                               "tool": "sviluppo", "argomenti": {"azione": "avanti"}}
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
                                  "tool": "sviluppo",
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
        if svs.lavoro_attivo(sv):
            return _stato(ctx, svs, sv, sv.persona)
        frase = ("Il lavoro dell'agente non è andato: vuoi cambiare qualcosa, o lo rifaccio "
                 "così?")
        return _final(frase, ok=False, fatto=NIENTE,
                      in_sospeso={"domanda": frase, "cosa": "rifare il lavoro",
                                  "tool": "sviluppo",
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
                                  "cosa": f"attivare «{sv.titolo}»", "tool": "sviluppo",
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
                                  "tool": "sviluppo", "argomenti": {"azione": "promuovi"}})
    frase += " Va bene così?"
    return _final(frase, fatto="revisione detta",
                  in_sospeso={"domanda": "Va bene così?", "cosa": "chiudere lo sviluppo",
                              "tool": "sviluppo", "argomenti": {"azione": "avanti"}})


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


# ─────────────────────────── sviluppo_prova ───────────────────────────

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
    svs.collaudo(sv, detti, ok, esito)
    note_rule(ctx, "sviluppo_prova")
    _schermo(ctx, sv)
    return out


def sviluppo_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="sviluppo",
            description=("La modalità sviluppo di un'estensione o di un programma (analisi, "
                         "sviluppo e test, collaudo, revisione, attivazione): stato (a che punto "
                         "è); avanti (la fase dopo: «va bene, andiamo avanti», «attivala»); "
                         "analisi (si torna all'analisi per cambiare cosa deve fare: cambia = "
                         "la modifica come detta); sospendi; riprendi («riprendiamo lo sviluppo "
                         "del meteo»: quale = le parole del titolo); esci; promuovi (un programma "
                         "diventa un'estensione). Cosa fare in ogni fase è nei dati del turno."),
            parameters={"type": "object", "properties": {
                "azione": {"type": "string", "enum": AZIONI},
                "quale": {"type": "string"}, "cambia": {"type": "string"}},
                "required": ["azione"]},
            func=_sviluppo, risk="azione", levels=FAMILY),
        ToolSpec(
            name="sviluppo_prova",
            description=("Il collaudo nella modalità sviluppo: prova la versione nuova "
                         "dell'estensione (non ancora attiva) o il programma, con i dati detti "
                         "(«prova con Bergamo», «provalo con 3 e 5»). dati: i dati come detti."),
            parameters={"type": "object", "properties": {"dati": {"type": "string"}},
                        "required": []},
            func=_sviluppo_prova, risk="azione", levels=FAMILY, non_fidato=True,
            fonte="estensione", announce=("Un attimo.",)),
    ]
