"""
I tool della modalità sviluppo (08/10/2026, calliope/sviluppo.py,
docs/ricerche/2026-10-08-modalita-sviluppo.md).

- sviluppo(azione, quale, cambia): lo stato dell'iter di chi amministra. stato; avanti (al
  collaudo → revisione, alla revisione → attivazione con la frase di sfida per un'estensione,
  chiusura per un programma; all'analisi conferma la specifica); analisi (si torna all'analisi
  da qualunque fase, con la modifica detta: il lavoro in corso si ferma, la specifica nuova si
  propone); sospendi, riprendi, chiudi («esci» vale come chiudi); promuovi (un programma diventa un'estensione).
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
import time

from .spec import ToolContext, ToolSpec, note_rule
from ..testi import FAMILY, NIENTE

AZIONI = ["stato", "avanti", "analisi", "rifai", "ferma", "sospendi", "riprendi", "chiudi",
          "promuovi"]
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

def controlla_nuovo(ctx, tool: str, args: dict, riapri: dict | None = None) -> dict | None:
    """Uno sviluppo nuovo (un'estensione, un programma, un lavoro dell'agente) mentre uno è
    aperto: non parte, Calliope lo dice e propone di sospendere quello aperto (decisione di
    Dario dell'08/10). None se la richiesta è dello sviluppo aperto, o non ce n'è uno.

    `riapri` (10/10): gli argomenti di sviluppo_apri per la richiesta nuova. La domanda dice
    allora i due titoli («Vuoi che sospenda «somma…» e apra «moltiplica…»?») e il «sì»
    (sviluppo_passo sospendi, entro due turni) sospende quello aperto e apre il nuovo, senza
    farlo ripetere (`_PROSSIMI`, regola `sviluppo_cambio`)."""
    from ..sviluppo import ALLA, chi, estraneo
    sv = estraneo(tool, args, ctx)
    if sv is None:
        return None
    note_rule(ctx, "sviluppo_altro_bloccato")
    alla = ALLA.get(sv.fase, sv.fase)
    nuovo = _titolo_nuovo(riapri) if riapri else ""
    svs = _svs(ctx)
    if nuovo and svs is not None and not svs.lavoro_attivo(sv):
        sc = getattr(ctx, "speaker_ctx", None)
        _PROSSIMI[_chiave(chi(ctx))] = {
            "argomenti": dict(riapri), "titolo": nuovo, "da": sv.id,
            "turno": int(getattr(ctx, "turno", 0) or 0), "quando": time.time(),
            # la richiesta è stata detta con la voce riconosciuta (o con la sfida superata):
            # il «sì» breve che la conferma non deve ripeterla (tools/agenti._permesso)
            "voce": getattr(sc, "identified_by", "voce") in ("voce", None)
            or bool(getattr(sc, "sfida_superata", False))}
        domanda = f"Vuoi che sospenda «{sv.titolo}» e apra «{nuovo}»?"
        altro = ("un altro programma" if _tipo(riapri.get("tipo")) == "programma"
                 else "un'altra estensione")
        frase = (f"Adesso stiamo sviluppando «{sv.titolo}» e siamo {alla}: «{nuovo}» è "
                 f"{altro}, e ne seguo uno per volta; il primo lo riprendiamo quando vuoi. "
                 f"{domanda}")
        cosa = f"sospendere lo sviluppo di «{sv.titolo}» e aprire quello di «{nuovo}»"
    else:
        domanda = "Vuoi che sospenda questo sviluppo?"
        frase = (f"Adesso stiamo sviluppando «{sv.titolo}» e siamo {alla}: "
                 "un'altra cosa per l'agente la comincio dopo. Vuoi che sospenda questo "
                 "sviluppo? Lo riprendiamo quando vuoi.")
        cosa = f"sospendere lo sviluppo di «{sv.titolo}»"
    return {"ok": False, "fatto": f"{NIENTE}: c'è uno sviluppo aperto, il lavoro NON è partito",
            "conferma": frase, "risposta_finale": frase,
            "in_sospeso": {"domanda": domanda, "cosa": cosa,
                           "tool": "sviluppo_passo", "argomenti": {"azione": "sospendi"}}}


# La richiesta nuova in attesa del «sì» a «sospendo quello aperto e apro questo?» (10/10), per
# persona; solo in memoria, vale due turni (e al più tre minuti)
_PROSSIMI: dict = {}
PROSSIMO_TURNI = 2
PROSSIMO_S = 180


def _chiave(persona) -> str:
    return str(persona or "")


def _titolo_nuovo(riapri: dict) -> str:
    from ..agenti.servizio import senza_estensione, titolo_da
    compito = str((riapri or {}).get("compito") or "").strip()
    if compito:
        t = titolo_da(compito)
        return senza_estensione(t) if _tipo((riapri or {}).get("tipo")) == "programma" else t
    return str((riapri or {}).get("nome") or (riapri or {}).get("modifica") or "").strip()


def _apri_prossimo(ctx, sv) -> dict | None:
    """Dopo «sospendi»: apre lo sviluppo nuovo chiesto al turno della domanda, se c'è (stessa
    persona, entro PROSSIMO_TURNI turni e PROSSIMO_S secondi)."""
    from ..sviluppo import chi
    p = _PROSSIMI.pop(_chiave(chi(ctx)), None)
    if p is None or p.get("da") != sv.id:
        return None
    dt = int(getattr(ctx, "turno", 0) or 0) - int(p.get("turno") or 0)
    if not 0 <= dt <= PROSSIMO_TURNI or time.time() - float(p.get("quando") or 0) > PROSSIMO_S:
        return None
    note_rule(ctx, "sviluppo_cambio")
    prima = getattr(ctx, "voce_della_richiesta", False)
    try:
        ctx.voce_della_richiesta = bool(p.get("voce"))
        out = dict(_sviluppo_apri(ctx, **p["argomenti"]))
    finally:
        ctx.voce_della_richiesta = prima
    testa = f"Ho sospeso lo sviluppo di «{sv.titolo}»: lo riprendiamo quando vuoi."
    out["fatto"] = f"sviluppo di «{sv.titolo}» sospeso; " + str(out.get("fatto") or "")
    detto = str(out.get("risposta_finale") or "").strip()
    if detto:
        out["risposta_finale"] = f"{testa} {detto}"
        if out.get("conferma"):
            out["conferma"] = out["risposta_finale"]
    return out


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
    scaduta = _proposta_scaduta(ctx, prop)
    if scaduta is not None:
        return scaduta
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


def _proposta_scaduta(ctx, prop: str):
    """Il «sì» alla specifica dello sviluppo aperto quando l'offerta del tool è scaduta (08/10,
    misura con gemma4 del giro 4: dopo tre turni d'altro «l'analisi è corretta» → sviluppo_apri
    con la proposta di prima → «chiedimelo di nuovo»). È la proposta dello sviluppo in analisi,
    già letta alla persona: vale come «avanti» (`_avanti`, con la frase che basta per chi
    amministra; se no la specifica si ripropone). None se non è questo caso."""
    if not re.fullmatch(r"L\d+", prop or ""):
        return None
    from ..sviluppo import chi
    from . import agenti as ta
    svs = _svs(ctx)
    sv = svs.corrente(chi(ctx)) if svs is not None else None
    if (sv is None or sv.fase != "analisi" or sv.proposto != prop or not sv.specifica
            or ta._offerta_di(ctx, getattr(ctx, "lavori", None), prop)):
        return None
    prof = _prof(ctx)
    if prof is None or not _admin(ctx):
        return None
    note_rule(ctx, "sviluppo_proposta_scaduta")
    return _avanti(ctx, svs, sv, prof)


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
              "pausa": "sospendi", "riapri": "riprendi", "stop": "ferma", "blocca": "ferma",
              "interrompi": "ferma", "fermalo": "ferma", "rifallo": "rifai",
              "rifare": "rifai", "riprova": "rifai", "ricomincia": "rifai"}.get(azione, azione)
    persona = chi(ctx)
    if azione == "riprendi":
        return _riprendi(ctx, svs, persona, quale)
    sv = svs.corrente(persona)
    if azione == "stato":
        return _stato(ctx, svs, sv, persona)
    if azione == "ferma" and sv is None:
        # «Sospendi» e poi «no, fermalo» (DGX, 08/10 19:07): lo sviluppo è già sospeso, il
        # lavoro dell'agente va ancora
        al_lavoro = [s for s in svs.trova(persona, quale)
                     if svs.lavoro_attivo(s) or _in_tappa(svs, s) is not None]
        if al_lavoro:
            return _ferma(ctx, svs, al_lavoro[0], prof)
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
        _schermo(ctx, sv)
        if not svs.lavoro_attivo(sv):
            # «Sì» a «sospendo questo e apro l'altro?» (10/10, controlla_nuovo)
            cambio = _apri_prossimo(ctx, sv)
            if cambio is not None:
                return cambio
        frase = (f"D'accordo: sospendo lo sviluppo di «{sv.titolo}», eravamo {_alla(sv)}. "
                 "Quando vuoi, dimmi «riprendiamo lo sviluppo».")
        if svs.lavoro_attivo(sv):
            # Con l'agente al lavoro una pausa lascia finire il lavoro: lo si dice, e il «sì»
            # alla domanda lo ferma (DGX, 08/10 19:06: «Fermo lo sviluppo» → sospeso, e «Ti ho
            # detto di stopparlo, non deve più continuare»)
            domanda = "Vuoi che fermi anche il lavoro dell'agente?"
            return _final(f"{frase} L'agente intanto finisce il suo lavoro e te lo dico quando "
                          f"è pronto. {domanda}",
                          fatto="sviluppo sospeso; il lavoro dell'agente CONTINUA",
                          in_sospeso={"domanda": domanda,
                                      "cosa": f"fermare il lavoro dell'agente su «{sv.titolo}»",
                                      "tool": "sviluppo_passo", "argomenti": {"azione": "ferma"}})
        return _final(frase, fatto="sviluppo sospeso")
    if azione == "ferma":
        return _ferma(ctx, svs, sv, prof)
    if azione == "rifai":
        return _rifai(ctx, svs, sv, prof)
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
        domanda = "Vuoi che fermi anche il lavoro dell'agente?"
        return _final(f"L'agente sta ancora lavorando a «{sv.titolo}»: invece di chiudere, "
                      "sospendo lo sviluppo. Quando il lavoro è pronto lo riapro al collaudo. "
                      + domanda,
                      fatto="sviluppo SOSPESO, non chiuso: c'è un lavoro dell'agente in corso",
                      in_sospeso={"domanda": domanda,
                                  "cosa": f"fermare il lavoro dell'agente su «{sv.titolo}»",
                                  "tool": "sviluppo_passo", "argomenti": {"azione": "ferma"}})
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


def _rifaccio(sv) -> str:
    """La domanda dopo un lavoro fermato o non andato (nessun lavoro in corso)."""
    if sv.nota in ("annullato", "fermato"):
        return ("Il lavoro dell'agente l'hai fermato tu: lo rifaccio così com'è, o vuoi cambiare "
                "qualcosa?")
    return "Il lavoro dell'agente non è andato: lo rifaccio così com'è, o vuoi cambiare qualcosa?"


def _rifaccio_sospeso(sv) -> dict:
    """L'azione in sospeso di quella domanda (08/10 sera, DGX delle 20:05: «Sì, rifallo» →
    `analisi` senza modifica → «cosa vuoi cambiare?», poi la specifica riletta e un altro «va
    bene così»; l'azione in sospeso diceva «azione = analisi, cambia vuota per rifarlo così», che
    l'analisi non sapeva fare). Il «sì» va a `rifai`, che riparte subito con la stessa
    specifica; una modifica detta va all'analisi."""
    return {"domanda": "Lo rifaccio così com'è?",
            "cosa": f"rifare il lavoro di «{sv.titolo}» con la stessa specifica",
            "tool": "sviluppo_passo",
            "argomenti": "azione = rifai (sì, rifallo così com'è: riparte subito con la stessa "
                         "specifica); se dice cosa cambiare, azione = analisi e cambia = la "
                         "modifica come detta"}


def _ferma(ctx, svs, sv, prof) -> dict:
    """«Ferma lo sviluppo», «stoppalo», «bloccalo» con l'agente al lavoro (08/10 sera, DGX delle
    19:06: «Fermo lo sviluppo» → sospendi, «l'agente intanto finisce il suo lavoro», e Dario «Ti
    ho detto di stopparlo, di fermarlo, non deve più continuare»): il lavoro dell'agente si
    ferma, lo sviluppo resta (aperto o sospeso com'era) senza lavoro, pronto per «rifallo» o
    per tornare all'analisi. Senza un lavoro in corso è una pausa: lo sviluppo si sospende.
    Quale azione sia («ferma» o «sospendi») lo sceglie il modello (principio 10)."""
    svc = getattr(ctx, "lavori", None)
    lav = svs._lavoro(sv.lavoro)
    al_lavoro = lav is not None and getattr(lav, "stato", "") in ("in_coda", "in_corso",
                                                                    "in_attesa")
    if not al_lavoro or svc is None:
        if sv.stato == "aperta":
            svs.sospendi(sv, "fermato senza lavoro in corso")
        note_rule(ctx, "sviluppo_sospeso")
        _schermo(ctx, sv)
        return _final(f"L'agente non sta lavorando a «{sv.titolo}»: ho sospeso lo sviluppo, "
                      f"eravamo {_alla(sv)}. Quando vuoi, dimmi «riprendiamo lo sviluppo».",
                      fatto="nessun lavoro da fermare: sviluppo sospeso")
    res = svc.annulla(prof.id, tutti_di_tutti=True, quale=sv.lavoro)
    if not res.get("ok"):
        return _final(str(res.get("frase") or "Non sono riuscita a fermare il lavoro."),
                      ok=False, fatto=NIENTE)
    with svs._lock:
        sv.lavoro, sv.nota = None, "annullato"
    svs.tocca(sv)
    note_rule(ctx, "sviluppo_fermato")
    _schermo(ctx, sv)
    dove = ("Lo sviluppo resta sospeso" if sv.stato == "sospesa"
            else f"Lo sviluppo resta aperto, {_alla(sv)}")
    return _final(f"Ho fermato il lavoro dell'agente su «{sv.titolo}»: non continua. {dove}: "
                  "quando vuoi lo rifaccio così com'è, o cambiamo qualcosa.",
                  fatto="lavoro dell'agente FERMATO", lavoro=getattr(lav, "id", None))


def _rifai(ctx, svs, sv, prof) -> dict:
    """«Sì, rifallo» dopo un lavoro fermato o non andato: un lavoro nuovo uguale all'ultimo
    dello sviluppo (stessa specifica, stessi vincoli e file di partenza), avviato subito: la
    specifica la persona l'aveva già accettata. Senza l'ultimo lavoro in memoria (un riavvio),
    il lavoro nuovo dalla specifica dello sviluppo."""
    from . import agenti as ta
    svc = getattr(ctx, "lavori", None)
    if svc is None:
        return _no(ctx, "Qui non ci sono agenti.")
    if svs.lavoro_attivo(sv) or _in_tappa(svs, sv) is not None:
        return _stato(ctx, svs, sv, sv.persona)
    if sv.fase == "analisi":
        return _avanti(ctx, svs, sv, prof)
    if sv.fase != "sviluppo":
        return _no(ctx, f"Non c'è un lavoro da rifare: siamo {_alla(sv)}. Se qualcosa non va, "
                        "lo faccio correggere.")
    note_rule(ctx, "sviluppo_rifai")
    ultimo = None
    for voce in reversed(sv.lavori or []):
        lv = svs._lavoro(voce.get("id"))
        if lv is not None and svs._stesso_tipo(sv, lv):
            ultimo = lv
            break
    if ultimo is None:
        out = _nuovo_lavoro(ctx, svs, sv, prof, sv.specifica or sv.richiesta, avvia=True)
        _schermo(ctx, sv)
        return out
    lav = svc.nuovo(ultimo.tipo, ultimo.compito, prof.id, prof.name, "amministra",
                    getattr(ultimo, "formato", "") or "", getattr(ultimo, "modello", "") or "",
                    getattr(ultimo, "vincoli", "") or "",
                    list(getattr(ultimo, "dati", None) or []))
    for k in ("titolo", "estensione", "gioco", "specifica", "correzione"):
        if getattr(ultimo, k, None) is not None:
            setattr(lav, k, getattr(ultimo, k))
    lav.file_iniziali = dict(getattr(ultimo, "file_iniziali", None) or {})
    out = ta._avvia(ctx, svc, lav)
    if isinstance(out, dict):
        frase = (f"D'accordo: rifaccio il lavoro di «{sv.titolo}» con la stessa specifica. Ci "
                 "lavora in secondo piano: te lo dico quando è pronto.")
        out["conferma"] = out["risposta_finale"] = frase
    _schermo(ctx, sv)
    return out


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
        frase += " " + _rifaccio(sv)
        _schermo(ctx, sv)
        return _final(frase, fatto="stato dello sviluppo: nessun lavoro in corso",
                      sviluppo=sv.id, in_sospeso=_rifaccio_sospeso(sv))
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
    elif sv.fase == "sviluppo" and sv.nota and not svs.lavoro_attivo(sv):
        # DGX, 08/10 20:04: ripreso dopo il lavoro fermato, «siamo allo sviluppo» e basta
        frase += " " + _rifaccio(sv)
        extra["in_sospeso"] = _rifaccio_sospeso(sv)
    elif sv.fase == "analisi" and sv.specifica:
        frase += " Vuoi che affidi all'agente la specifica di prima?"
        extra["in_sospeso"] = {"domanda": "Vuoi che la affidi all'agente?",
                               "cosa": "affidare la specifica all'agente",
                               "tool": "sviluppo_passo", "argomenti": {"azione": "avanti"}}
    _schermo(ctx, sv)
    return _final(frase, fatto="sviluppo ripreso", sviluppo=sv.id, **extra)


def _collaudi_per_agente(svs, sv) -> str:
    """I collaudi della versione provata per il lavoro che riparte dall'analisi (08/10 sera,
    giro 5: la persona ha dato la diagnosi durante il collaudo, «i nomi devi codificarli», e il
    lavoro L2 è ripartito con la sola specifica, senza i collaudi né la traccia di rete; la
    versione nuova aveva la stessa doppia codifica). Come per sviluppo_correggi: dati, argomenti
    passati, esito, il giudizio della persona, la diagnosi di chi l'ha scritto e la traccia.
    "" senza collaudi."""
    if not sv.collaudi:
        return ""
    from ..sviluppo import argomenti_detti
    casi = "; ".join(f"«{c.get('dati') or 'senza dati'}»"
                     + (f" (argomenti passati: {argomenti_detti(c)})" if c.get("argomenti")
                        else "")
                     + f" → {'riuscito' if c.get('ok') else 'NON riuscito'}: "
                     + f"{c.get('esito') or 'errore'}"
                     + (f" (la persona: {c['giudizio']})" if c.get("giudizio") else "")
                     for c in sv.collaudi[-5:])
    diagnosi = next((q for q in reversed(sv.chiesti) if q.get("dettagli") or q.get("voce")),
                    None)
    rete = svs.testo_traccia(sv)
    return (f" Collaudi della versione che la persona ha provato (dati → esito): {casi}."
            + (f" Diagnosi di chi l'ha scritto, alla domanda «{diagnosi['domanda']}»: "
               f"{diagnosi.get('dettagli') or diagnosi.get('voce')}" if diagnosi else "")
            + (f" {rete}" if rete else "")
            + " Controlla che la versione nuova non abbia gli stessi problemi: aggiungi un test "
              "con ogni caso che non andava.")


def _nuovo_lavoro(ctx, svs, sv, prof, compito: str, cambia: str = "",
                  avvia: bool = False) -> dict:
    """Il lavoro dello sviluppo con la specifica nuova, proposto con «Ho capito così: …
    Procedo?» (la persona conferma la specifica: è la fine dell'analisi). `avvia`: la persona
    l'ha già sentita e accettata («avanti»), il lavoro parte."""
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
            return _estensione_crea(ctx, compito=compito, nome=sv.titolo, gioco=sv.gioco,
                                    accanto=True)
        from ..estensioni.servizio import runtime_testo
        from .estensioni import funzioni_di_calliope
        from .estensioni import titolo_vincolo
        vincoli = (f"È lo sviluppo dell'estensione «{sv.estensione}»: i suoi file (la versione che "
                   "la persona ha provato) sono già nella cartella; tieni lo stesso nome nel "
                   "manifesto. " + titolo_vincolo(est, sv.estensione)
                   + (f" Cambiamento chiesto dalla persona: «{cambia}»." if cambia
                      else "") + _collaudi_per_agente(svs, sv) + " "
                   + funzioni_di_calliope())
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
                   + (f" Cambiamento chiesto dalla persona: «{cambia}»." if cambia else "")
                   + _collaudi_per_agente(svs, sv))
        lav = svc.nuovo("codice", compito, prof.id, prof.name, "amministra", "", "", vincoli,
                        storia)
        lav.titolo = sv.titolo
        lav.file_iniziali = file_di_codice(sv.cartella) if sv.cartella else {}
    lav.specifica = compito
    _con_esempi(svs, sv, lav)
    if avvia:
        return ta._avvia(ctx, svc, lav)
    return ta._proponi(ctx, svc, lav, turno)


def _con_esempi(svs, sv, lav) -> int:
    """Le risposte vere dei collaudi nella cartella dell'agente (`esempi_veri/`, 08/10 notte) e
    nei vincoli come usarle nei test. Il numero di file messi (0 senza)."""
    from ..sviluppo import ESEMPI_VINCOLO, ESEMPI_VERI
    try:
        esempi = svs.esempi(sv)
    except Exception as e:  # noqa: BLE001 — gli esempi aiutano, non fermano il lavoro
        getattr(svs, "log", print)(f"[SVILUPPO] esempi veri non preparati: "
                                   f"{type(e).__name__}: {e}")
        return 0
    if not esempi:
        return 0
    # Quelli della versione di prima (tra i file della candidata) li sostituiscono i nuovi
    lav.file_iniziali = {k: v for k, v in (lav.file_iniziali or {}).items()
                         if not k.startswith(ESEMPI_VERI + "/")}
    lav.file_iniziali.update(esempi)
    lav.vincoli = ((lav.vincoli or "").rstrip() + " " + ESEMPI_VINCOLO).strip()
    return len(esempi) - 1


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
    compito = _con_modifica(base, cambia)
    out = _nuovo_lavoro(ctx, svs, sv, prof, compito, cambia)
    if isinstance(out, dict) and fermato:
        for k in ("conferma", "risposta_finale"):
            if isinstance(out.get(k), str):
                out[k] = fermato + out[k]
    _schermo(ctx, sv)
    return out


def _con_modifica(base: str, cambia: str) -> str:
    """La specifica con la modifica detta (08/10, DGX delle 17:01: «Ho capito così: aggiungi
    la possibilità di scegliere quanti giorni… Con questa modifica: aggiungere la possibilità
    di scegliere quanti giorni…»): se la modifica è la specifica di adesso detta di nuovo, o
    ci sta dentro, la specifica resta com'è."""
    import difflib
    from ..estensioni.servizio import _norm_testo
    base, cambia = str(base or "").strip(), str(cambia or "").strip().rstrip(".")
    if not base:
        return cambia
    a, b = _norm_testo(base), _norm_testo(cambia)
    if not b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= 0.8:
        return base
    return f"{base}. Con questa modifica: {cambia}"


def _avanti(ctx, svs, sv, prof) -> dict:
    from . import agenti as ta
    svc = getattr(ctx, "lavori", None)
    if sv.fase == "analisi":
        if sv.proposto and ta._offerta_di(ctx, svc, sv.proposto):
            return ta._delega_lavoro(ctx, proposta=sv.proposto)
        if sv.specifica and sv.proposto:
            # «Avanti» in analisi accetta la specifica già proposta e letta (08/10, DGX delle
            # 17:02: «l'analisi è corretta e voglio implementarla così» → la stessa domanda di
            # nuovo, perché tre turni dopo l'offerta era scaduta). Con la frase che basta per
            # chi amministra, il lavoro parte con la specifica letta; se no, si ripropone
            from ..conferme import admin_confermato
            if admin_confermato(ctx):
                note_rule(ctx, "sviluppo_avanti_accetta")
                return _nuovo_lavoro(ctx, svs, sv, prof, sv.specifica, avvia=True)
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
        return _final(_rifaccio(sv), ok=False, fatto=NIENTE, in_sospeso=_rifaccio_sospeso(sv))
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
        # La domanda in fondo (09/10, caso vero della DGX delle 21:00: con «Vuoi attivarla? Ti
        # chiederò la frase di conferma.» la risposta non finiva con «?», l'azione in sospeso
        # non restava e «Sì, attivarla.» arrivava alla politica senza la proposta). Il titolo
        # viene dallo stato dello sviluppo: un nome fidato per la risposta (`_fidati`)
        frase = (f"{rev['frase']} {detto_coll} Ti chiederò la frase di conferma: vuoi "
                 "attivarla?")
        return _final(frase, fatto="revisione detta: NON è ancora attiva",
                      _fidati=[str(sv.titolo or "")],
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
    schema = ((m or {}).get("input") or {}).get("properties") or {}
    props = list(schema)
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
    out = _numeri_detti(schema, s, primo)
    if out:
        return out
    return {primo: s}


# «Guanzate, 5 giorni», «Lucca per i prossimi 3 giorni»: un numero seguito dal NOME di un
# input numerico dell'estensione (08/10, DGX: «Guanzate, 5 giorni» finiva tutto in `citta`, e
# per tre collaudi «non trovato»). Conversione di forma della chiamata del modello (principio
# 10, regola `collaudo_input_dal_testo`): solo con il nome esatto dell'input dopo il numero, e
# solo se resta qualcosa per il primo input. Contrari in prova_sviluppo: «Via Roma 5», «Bari,
# 5» (senza il nome dell'input), «3 e 5» per un programma, un input senza numeri
_CONNETTIVI = re.compile(r"(?:[,;]|\b(?:per|nei|negli|ai|i|gli|le|prossim[ie]|successiv[ie]|"
                         r"seguent[ie]|di|a|con))+\s*$", re.I)


def _numeri_detti(schema: dict, s: str, primo: str) -> dict:
    out = {}
    resto = s
    for k, v in schema.items():
        if k == primo or (v or {}).get("type") not in ("integer", "number"):
            continue
        forme = {k.lower(), k.lower().rstrip("aeio")}
        rx = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s+(" + "|".join(
            re.escape(f) for f in sorted(forme, key=len, reverse=True)) + r")[a-zà-ù]*(?![\w])",
            re.I)
        trovati = list(rx.finditer(resto))
        if len(trovati) != 1:
            continue
        m = trovati[0]
        n = m.group(1).replace(",", ".")
        out[k] = int(n) if v.get("type") == "integer" and "." not in n else float(n)
        resto = (resto[:m.start()] + resto[m.end():]).strip()
    if not out:
        return {}
    resto = _CONNETTIVI.sub("", resto).strip(" ,;")
    while True:
        r2 = _CONNETTIVI.sub("", resto).strip(" ,;")
        if r2 == resto:
            break
        resto = r2
    if not resto:
        return {}
    return {primo: resto, **out}


def input_della_prova(m: dict) -> list[str]:
    """Gli input della versione in prova detti per il modello: «citta (testo): nome della
    città…», «giorni (numero intero): quanti giorni…»."""
    tipi = {"string": "testo", "integer": "numero intero", "number": "numero",
            "boolean": "sì o no"}
    out = []
    schema = ((m or {}).get("input") or {})
    req = set(schema.get("required") or [])
    for k, v in (schema.get("properties") or {}).items():
        d = re.sub(r"\s+", " ", str((v or {}).get("description") or "")).strip()[:90]
        out.append(f"{k} ({tipi.get((v or {}).get('type'), (v or {}).get('type') or 'testo')}"
                   + (", obbligatorio" if k in req else "") + ")" + (f": {d}" if d else ""))
    return out


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


def _collauda_estensione(ctx, svs, sv, est, passati: dict, detti: str):
    """Un collaudo della versione candidata con questi argomenti: (risultato per il modello,
    fallito, rifiutato prima di partire). Un collaudo partito resta nello sviluppo con la sua
    traccia di rete (08/10: per l'agente, mai alla voce)."""
    from ..estensioni.servizio import CHIAVE_TRACCIA
    out = est.prova_candidata(ctx, sv.estensione, passati)
    traccia = out.pop(CHIAVE_TRACCIA, None) if isinstance(out, dict) else None
    ris = (out or {}).get("risultati") if isinstance(out, dict) else None
    if isinstance(out, dict) and ris is None and not out.get("errore"):
        return out, False, True
    esito = (ris.get("da_dire") if isinstance(ris, dict) and ris.get("da_dire")
             else json.dumps(ris, ensure_ascii=False) if ris is not None
             else str((out or {}).get("errore") or (out or {}).get("conferma") or ""))
    fallito = _fallito(out, ris)
    svs.collaudo(sv, detti, not fallito, esito, rete=traccia, argomenti=passati)
    return out, fallito, False


# Più valori da provare detti insieme (08/10 sera, DGX delle 20:10, con nomi di fantasia: «prova
# con Borgoverde Maggiore e Pratofiorito» → UNA chiamata con argomenti = {"citta": "Borgoverde
# Maggiore"} e dati = «Borgoverde Maggiore e Pratofiorito», e la voce: «per Pratofiorito non ho
# ancora ricevuto i dati»). Il
# separatore: virgola, punto e virgola, «e», «ed», «e poi», «poi», «oppure»; davanti a un valore
# si tolgono «con», «a», «anche», «poi»
_SEP_VALORI = re.compile(r"\s*(?:[,;]|\s(?:e\s+poi|poi|ed|e|oppure)\s)\s*", re.I)
_DAVANTI = re.compile(r"^(?:(?:e|ed|poi|anche|invece|pure)\s+)*(?:(?:con|a|ad|per)\s+(?=\D))?",
                      re.I)


def valori_elenco(dati) -> list[str]:
    """I valori di un elenco detto («A e B», «A, B e C», «con A e poi con B»); [] se non è un
    elenco: meno di due valori, più di quattro, un valore che comincia con un numero
    («Pratofiorito, 3 giorni», «3 e 5») o lungo più di sei parole."""
    s = re.sub(r"\s+", " ", str(dati or "")).strip().strip(".")
    s = _DAVANTI.sub("", s)
    voci = [_DAVANTI.sub("", v.strip()).strip(" .") for v in _SEP_VALORI.split(" " + s + " ")]
    voci = [v for v in voci if v]
    if not 2 <= len(voci) <= 4:
        return []
    if any(v[0].isdigit() or not re.search(r"[^\W\d_]{2,}", v) or len(v.split()) > 6
           for v in voci):
        return []
    return voci


def piu_valori(m: dict, argomenti, dati, passati: dict) -> list[tuple[str, dict]] | None:
    """Un collaudo per valore, quando il modello ha già separato i valori: `dati` è un elenco
    («A e B») e `argomenti` ha per il primo input UNO solo di quei valori. Correzione della forma
    di una scelta del modello (principio 10, regola `collaudo_piu_valori`): solo così, perché
    «A e B» da solo può essere un nome solo (un comune «Bosco e Prato»): se il modello passa
    l'elenco intero, o solo `dati`, resta un collaudo con quello che ha scelto. Gli altri input
    (i giorni) valgono per tutti, salvo un valore che li dice da sé («B per 3 giorni»).
    [(valore detto, argomenti), …] o None."""
    if not isinstance(argomenti, dict) or not isinstance(dati, str) or not passati:
        return None
    schema = ((m or {}).get("input") or {})
    props = list(schema.get("properties") or {})
    req = list(schema.get("required") or [])
    if not props:
        return None
    primo = req[0] if req else props[0]
    val = passati.get(primo)
    if not isinstance(val, str) or not val.strip():
        return None
    voci = valori_elenco(dati)
    if not voci:
        return None
    from ..estensioni.servizio import _norm_testo
    n_val = _norm_testo(val)
    if n_val == _norm_testo(dati):
        return None
    lette = [(v, _argomenti(m, v)) for v in voci]
    uguali = [i for i, (v, a) in enumerate(lette)
              if n_val in (_norm_testo(v), _norm_testo(str(a.get(primo) or "")))]
    if len(uguali) != 1:
        return None
    out = []
    for i, (v, a) in enumerate(lette):
        if i == uguali[0]:
            out.append((v, dict(passati)))
        else:
            out.append((v, {**passati, **{k: x for k, x in a.items() if x not in ("", None)}}))
    return out


def _piu_collaudi(ctx, svs, sv, est, valori: list[tuple[str, dict]]) -> dict:
    """I collaudi di più valori detti insieme, uno dopo l'altro: ognuno resta nello sviluppo
    come un collaudo a sé (con la sua traccia), il modello riceve i risultati in fila."""
    note_rule(ctx, "collaudo_piu_valori")
    fatti, falliti = [], []
    primo_out = None
    for detto, args in valori:
        out, fallito, prima = _collauda_estensione(ctx, svs, sv, est, args, detto)
        if prima:
            if not fatti:
                return out                   # il primo non è partito: nessuno parte
            fatti.append({"provato": detto, "partito": False,
                          "nota": str((out or {}).get("conferma") or (out or {}).get("fatto")
                                      or "non partito")})
            continue
        primo_out = primo_out or out
        voce = {"provato": detto, "argomenti_passati": args, "riuscito": not fallito}
        if isinstance(out, dict) and out.get("risultati") is not None:
            voce["risultati"] = out["risultati"]
        else:
            voce["errore"] = "si è fermata con un errore: i dettagli sono sulla scheda"
        if fallito:
            falliti.append(detto)
            note_rule(ctx, "sviluppo_collaudo_fallito")
        fatti.append(voce)
    note_rule(ctx, "sviluppo_collauda")
    _schermo(ctx, sv)
    n = est.archivio.candidata(sv.estensione)
    res = {"ok": True, "estensione": (primo_out or {}).get("estensione") or sv.titolo,
           "collaudi": fatti,
           "collaudo": (f"{len(fatti)} prove della versione {n}, NON ancora approvata né attiva, "
                        "una per valore detto: di' in breve il risultato di OGNUNA")}
    if isinstance(primo_out, dict) and primo_out.get("avviso"):
        res["avviso"] = primo_out["avviso"]
    if falliti:
        cosa = ", ".join(f"«{x}»" for x in falliti)
        res["cosa_fare"] = (f"per {cosa} di' che la prova si è fermata con un errore (i dettagli "
                            "sono sulla scheda) e chiedi «Lo faccio correggere?»")
        res["in_sospeso"] = {"domanda": "Lo faccio correggere?", "tool": "sviluppo_correggi",
                             "cosa": f"far correggere «{sv.titolo}» all'agente",
                             "argomenti": {"problema": f"il collaudo con {cosa} si ferma con "
                                                       "un errore"}}
    return res


def _sviluppo_prova(ctx: ToolContext, dati: str = "", argomenti=None, **_altro) -> dict:
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
    # Gli input per nome (08/10): un oggetto `argomenti`, anche passato come testo JSON
    if isinstance(argomenti, str) and argomenti.strip().startswith("{"):
        try:
            argomenti = json.loads(argomenti)
        except ValueError:
            argomenti = None
    if not isinstance(argomenti, dict) or not argomenti:
        argomenti = None
    detti = dati if isinstance(dati, str) else json.dumps(dati, ensure_ascii=False)
    if argomenti is not None and not str(detti or "").strip():
        detti = ", ".join(f"{k}: {v}" for k, v in argomenti.items())
    passati = None
    if sv.tipo == "estensione":
        est = getattr(ctx, "estensioni", None)
        if est is None or not sv.estensione:
            return _no(ctx, "Qui le estensioni non ci sono.")
        n = est.archivio.candidata(sv.estensione)
        m = est.archivio.manifesto(sv.estensione, n) if n else None
        if m is None:
            return _no(ctx, "Non c'è una versione nuova da provare.")
        passati = _argomenti(m, argomenti if argomenti is not None else dati)
        if argomenti is None and len(passati) > 1:
            note_rule(ctx, "collaudo_input_dal_testo")
        valori = piu_valori(m, argomenti, dati, passati)
        if valori:
            return _piu_collaudi(ctx, svs, sv, est, valori)
        out, fallito, prima = _collauda_estensione(ctx, svs, sv, est, passati, detti)
        if prima:
            # Un rifiuto prima dell'esecuzione (file cambiati, contenitore spento, un gioco)
            # non è un collaudo: si dice e basta
            return out
    else:
        from . import agenti as ta
        lav_id = sv.lavoro if svs._lavoro(sv.lavoro) is not None else ""
        out = ta._lavori_esegui(ctx, lavoro=lav_id, dati=dati)
        fallito = not bool((out or {}).get("ok"))
        svs.collaudo(sv, detti, not fallito, str((out or {}).get("conferma") or ""),
                     argomenti=passati)
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
    if isinstance(out, dict) and passati is not None:
        # Gli argomenti veri dell'esecuzione (08/10): il modello vede se il problema è nel
        # passaggio («citta = "Guanzate, 5 giorni"») e non nel codice
        out = {**out, "argomenti_passati": passati}
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
    sv = svs.corrente(chi(ctx)) if svs is not None else None
    if sv is None:
        # Nessuno sviluppo aperto: «correggi lo script di backup…» è una richiesta nuova di
        # codice (misura del 08/10 con gemma4: 2 volte su 2 qui invece di sviluppo_apri). Una
        # conversione della forma della scelta del modello: lo sviluppo di un programma, con
        # la frase della persona (regola `sviluppo_correggi_nuovo`)
        note_rule(ctx, "sviluppo_correggi_nuovo")
        compito = (str(getattr(ctx, "user_text", "") or "").strip()
                   or str(problema or "").strip())
        return _sviluppo_apri(ctx, tipo="programma", compito=compito)
    prof = _prof(ctx)
    if prof is None or not _admin(ctx):
        return _no(ctx, "Le correzioni sono di chi amministra.", "sviluppo_permesso")
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
    from ..sviluppo import argomenti_detti
    casi = "; ".join(f"«{c.get('dati') or 'senza dati'}»"
                     + (f" (argomenti passati: {argomenti_detti(c)})" if c.get("argomenti")
                        else "") + f" → {c.get('esito') or 'errore'}"
                     + (f" (la persona: {c['giudizio']})" if c.get("giudizio") else "")
                     for c in falliti)
    diagnosi = next((q for q in reversed(sv.chiesti) if q.get("dettagli") or q.get("voce")),
                    None)
    # La traccia di rete dei collaudi (08/10): le richieste vere con l'esito, la causa che nel
    # giro della DGX l'agente non vedeva (nella sandbox non ha rete)
    rete = svs.testo_traccia(sv)
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
               + (f" {rete}" if rete else "")
               + " Trova la causa, correggi il codice, aggiungi un test con ogni caso che non "
                 "andava, rifai i test, poi consegna.")
    lav = _lavoro_dello_sviluppo(ctx, svc, sv, prof, sv.specifica or sv.richiesta, vincoli)
    if isinstance(lav, dict):
        return lav
    _con_esempi(svs, sv, lav)
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
        from .estensioni import funzioni_di_calliope, titolo_vincolo
        v = (f"È lo sviluppo dell'estensione «{sv.estensione}»: tieni lo stesso nome nel "
             f"manifesto. {titolo_vincolo(est, sv.estensione)} {vincoli} "
             f"{funzioni_di_calliope()}")
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
             "modifica": {"type": "string", "description": (
                 "per CAMBIARE un'estensione che c'è: solo il suo NOME (es. «modifica "
                 "l'estensione Meteo città aggiungendo i giorni» → modifica = \"Meteo città\", "
                 "compito = \"aggiungi i giorni\"); MAI cosa cambiare, che va in compito; "
                 "vuoto per una nuova")},
             "gia_fatto_da": {"type": "string"}, "come_chiederlo": {"type": "string"},
             "proposta": {"type": "string"}, "gioco": {"type": "boolean"}}
    if file_pc:
        props["file"] = {"type": "string"}
    if allegati:
        props["allegato"] = {"type": "integer"}
    return ToolSpec(
        name="sviluppo_apri",
        description=(
            "Crea un'estensione nuova di Calliope o un programma: apre lo sviluppo di qualcosa "
            "che l'agente scrive in codice («voglio un'estensione che…», «fammi uno script…»). "
            "tipo estensione: una funzione permanente di Calliope, che resta e si usa a voce "
            "(«fammi una funzione che "
            "converte le unità di misura»), o una versione nuova di un'estensione che c'è («falla "
            "funzionare per ogni città», «correggila»: modifica = il suo nome); gioco=true per un "
            "gioco sullo schermo. tipo programma: uno script o un programma da usare adesso, in "
            "Python o C# («scrivimi uno script che rinomina le foto»)"
            + (", anche su un file della persona sul PC (file = il nome detto)" if file_pc
               else "")
            + (" o allegato (allegato = il numero)" if allegati else "")
            + ". NON per domande brevi e spiegazioni di programmazione («come si scrive un "
            "ciclo for?», «cos'è una funzione ricorsiva?»): rispondi tu, a voce. compito: cosa deve fare, "
            "con i dati come detti. nome: un nome breve per un'estensione nuova. gia_fatto_da: se uno "
            "dei tuoi tool fa "
            "già la stessa cosa (sommare = calcola), il suo nome, e come_chiederlo: la frase per "
            "chiederlo a voce. Se il risultato finisce con una domanda («Va bene così, o la "
            "cambiamo?»), dopo il sì richiamalo con proposta = l'id proposto (es. «L3»)."),
        parameters={"type": "object", "properties": props, "required": ["compito"]},
        func=_sviluppo_apri, risk="azione", levels=FAMILY,
        # Il nome di un'estensione da cambiare (calliope/argomenti_incerti.py)
        nomi={"modifica": "estensione"})


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
                         "detta); rifai (dopo un lavoro fermato o non andato, «sì, rifallo», "
                         "«riprova così com'è»: riparte subito con la stessa specifica); ferma "
                         "(«ferma/stoppa/blocca lo sviluppo», «fermalo»: il lavoro dell'agente "
                         "si ferma subito); sospendi (una pausa, «mettiamo in pausa»: un lavoro "
                         "dell'agente in corso finisce); riprendi («riprendiamo lo sviluppo del meteo»: quale "
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
                         "(«prova con Bergamo», «provalo con 3 e 5»). Per un'estensione, più "
                         "valori detti insieme («prova con Bergamo e Roma») sono un collaudo "
                         "ciascuno: una chiamata per valore. dati: i dati come detti. "
                         "argomenti: per un'estensione con più input (sono nei dati del "
                         "turno), un oggetto con un valore per input («Bergamo per 3 giorni» → "
                         "{\"citta\": \"Bergamo\", \"giorni\": 3})."),
            parameters={"type": "object", "properties": {"dati": {"type": "string"},
                                                         "argomenti": {"type": "object"}},
                        "required": []},
            func=_sviluppo_prova, risk="azione", levels=FAMILY, non_fidato=True,
            fonte="estensione", announce=("Un attimo.",),
            # I dati del collaudo nominano qualcosa (calliope/argomenti_incerti.py): `argomenti`
            # per ogni valore di testo, con il tipo dal nome dell'input («citta» → luogo)
            nomi={"dati": "valore", "argomenti": "valore"}),
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
            description=("Solo con uno sviluppo aperto (nei dati del turno): fa correggere il "
                         "codice dello sviluppo da chi l'ha scritto, senza cambiare cosa deve "
                         "fare («correggilo», «fallo sistemare», «sì» a «Lo faccio "
                         "correggere?»; a una tappa, «cambia e continua»). problema: cosa non "
                         "va, come detto. Per cambiare cosa deve fare, sviluppo_passo con azione "
                         "analisi; per correggere uno script o un file fuori da uno sviluppo, "
                         "sviluppo_apri tipo programma."),
            parameters={"type": "object", "properties": {"problema": {"type": "string"}},
                        "required": []},
            func=_sviluppo_correggi, risk="azione", levels=FAMILY),
    ]
