"""
I tool della modalità sviluppo (08/10/2026, calliope/sviluppo.py,
docs/ricerche/2026-10-08-modalita-sviluppo.md).

- sviluppo(azione, quale, cambia): lo stato dell'iter di chi amministra. stato; avanti (al
  collaudo → revisione, alla revisione → attivazione con la frase di sfida per un'estensione,
  chiusura per un programma; all'analisi conferma la specifica); analisi (si torna all'analisi
  da qualunque fase, con la modifica detta: la specifica nuova si propone, e dal 12/10 il lavoro
  in corso si ferma solo al «sì»; indietro la scarta); sospendi, riprendi, chiudi («esci» vale
  come chiudi); promuovi (un programma diventa un'estensione).
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

from .. import frasi as frasi_pronte
from .spec import ToolContext, ToolSpec, note_rule
from ..testi import FAMILY, NIENTE

AZIONI = ["stato", "avanti", "analisi", "rifai", "ferma", "sospendi", "riprendi", "chiudi",
          "promuovi", "completa", "indietro"]
# Le parole che il modello usa al posto di un'azione (in `azione`, o nel nome del tool:
# `azione_dal_nome`)
SINONIMI_AZIONE = {
    "continua": "avanti", "prosegui": "avanti", "procedi": "avanti", "cambia": "analisi",
    "modifica": "analisi", "esci": "chiudi", "basta": "chiudi", "pausa": "sospendi",
    "riapri": "riprendi", "stop": "ferma", "blocca": "ferma", "interrompi": "ferma",
    "fermalo": "ferma", "rifallo": "rifai", "rifare": "rifai", "riprova": "rifai",
    "ricomincia": "rifai", "elenco": "stato", "elenca": "stato", "lista": "stato",
    "stoppa": "ferma", "ripristina": "indietro"}
TIPI_APRI = ["estensione", "programma"]


def azione_dal_nome(name) -> str | None:
    """L'azione di sviluppo_passo nel nome di un tool che non esiste (10/10, DGX delle 15:57:
    il 26B chiamava `sviluppo_ferma` due volte, «Non ci sono riuscita», e `sviluppo_chiudi`
    diventava `sviluppo_chiedi` per la distanza di una lettera). `sviluppo_<azione>`, con
    un'azione di AZIONI o un suo sinonimo chiaro (`SINONIMI_AZIONE`), vale sviluppo_passo con
    quell'azione: correzione della forma di una scelta già fatta dal modello (principio 10,
    regola `tool_nome_azione`). Il chiamante controlla prima che il nome non sia un tool vero.
    None per ogni altro nome (`sviluppo_prova`, `sviluppo_xyz`)."""
    m = re.fullmatch(r"sviluppo_([a-z]+)", str(name or "").strip().lower())
    if not m:
        return None
    a = SINONIMI_AZIONE.get(m.group(1), m.group(1))
    return a if a in AZIONI else None


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
    from ..sviluppo import estraneo
    sv = estraneo(tool, args, ctx)
    if sv is None:
        return None
    note_rule(ctx, "sviluppo_altro_bloccato")
    return _domanda_cambio(ctx, sv, riapri)


def _domanda_cambio(ctx, sv, riapri: dict | None) -> dict:
    """Il risultato «c'è già uno sviluppo aperto»: con `riapri` la domanda con i due titoli
    («Vuoi che sospenda «…» e apra «…»?», e il «sì» sospende e apre), senza la domanda di
    sospendere e basta. Da controlla_nuovo e dall'analisi con un altro compito (10/10)."""
    from ..sviluppo import ALLA, chi
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
        c = str(riapri.get("compito") or "")
        altro = ("un altro programma" if _tipo(riapri.get("tipo")) == "programma"
                 else "un altro gioco" if gioco_sugli_schermi(c) or re.search(
                     r"\b(?:altr|nuov|second)[oa]\s+gioc(?:o|hi)\b", c, re.I)
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


def sospendi_per_ricominciare(ctx) -> str:
    """«Ricominciamo» con uno sviluppo aperto (12/10, lavoro 3; caso vero del 10/10 alle
    10:39: «ricominciamo» e poi la richiesta di un altro programma, diventata una modifica di
    quello aperto, e la persona: «quando ti ho detto ricominciamo intendevo ripartire da
    capo»): la conversazione nuova sospende lo sviluppo aperto di chi parla (l'agente, se
    lavora, finisce; si riprende quando si vuole). Effetto di una regola che c'è già
    (`nuova_conversazione`), reversibile. La frase da aggiungere, o ""."""
    from ..sviluppo import chi
    svs = _svs(ctx)
    persona = chi(ctx)
    sv = svs.corrente(persona) if svs is not None and persona is not None else None
    if sv is None:
        return ""
    svs.sospendi(sv, "conversazione nuova")
    note_rule(ctx, "sviluppo_sospeso_ricominciando")
    return f"Lo sviluppo di «{sv.titolo}» l'ho sospeso: lo riprendiamo quando vuoi."


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

# Il compito È un gioco (la cosa da fare, in testa): «un gioco», «un piccolo gioco di paura»,
# «crea un minigioco…»; non «un programma che conta i punti del gioco di carte»
_GIOCO = re.compile(r"^\W*(?:(?:crea\w*|fa\w*|scriv\w*|svilupp\w*|progett\w*|realizz\w*)\s+)?"
                    r"(?:(?:un|uno|una|il|lo|dei|degli|del)\s+)?(?:(?:piccol\w*|semplic\w*|"
                    r"nuov\w*|bel|bell\w*|breve)\s+)?(gioc(o|hi|hino|hini)|minigioc\w*|"
                    r"videogioc\w*|giochett\w*)(?![a-zà-ù])", re.I)
# Ciò che fa di un gioco un programma: una finestra sul desktop, il terminale, un linguaggio
_GIOCO_PROGRAMMA = re.compile(
    r"(?<![a-zà-ù])(finestr\w*|desktop|windows|eseguibile|\.?exe|terminale|console|"
    r"riga di comando|testuale|solo testo|python|c#|c sharp|per il pc|sul pc|"
    r"del pc)(?![a-zà-ù])", re.I)


def gioco_sugli_schermi(compito: str, frase: str = "") -> bool:
    """Il compito è un gioco, e né il compito né la frase dicono che è un programma per il
    desktop o il terminale (vedi _sviluppo_apri, 10/10)."""
    return bool(_GIOCO.search(str(compito or ""))) and not _GIOCO_PROGRAMMA.search(
        f"{compito or ''} {frase or ''}")


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
                   tappe=None, **_altro) -> dict:
    """Uno sviluppo nuovo (08/10, versione 2): un'estensione (tools/estensioni._estensione_crea)
    o un programma (tools/agenti._delega_lavoro di tipo codice), con la stessa analisi, la
    stessa proposta e gli stessi permessi di prima. `proposta` = l'id del lavoro proposto: il
    «sì» alla specifica."""
    from . import agenti as ta
    from . import estensioni as te
    t = _tipo(tipo)
    if str(tipo or "").strip().lower() == "gioco":
        gioco = True
    prop = str(proposta or "").strip()
    gia_gioco = gioco in (True, "true", "sì", "si", 1)
    if (t in ("programma", "estensione", "") and not gia_gioco and not prop
            and not str(modifica or "").strip()
            and gioco_sugli_schermi(compito, getattr(ctx, "user_text", ""))):
        # Un gioco chiesto come programma (10/10, DGX delle 15:56: «Vorrei sviluppare un
        # gioco all'interno di Calliope» → tipo programma → «non si possono creare giochi
        # interattivi o programmi con finestre»): i giochi di Calliope sono estensioni con
        # una scheda sugli schermi. Correzione della forma della scelta del modello
        # (principio 10, regola `sviluppo_gioco_schermi`); un programma con una finestra per
        # il desktop, o un gioco da terminale in Python, resta un programma.
        # Anche con tipo «estensione» senza il flag (10/10, DGX delle 17:32, dopo la
        # correzione: «Crea un gioco di Halloween per schermi dove i giocatori devono
        # scegliere tra diverse porte…» → l'analisi delle estensioni, e alla seconda passata
        # «impossibile: la richiesta non specifica la sezione scheda»): un gioco è
        # un'estensione con la scheda, e l'analisi delle estensioni non fa per lui
        note_rule(ctx, "sviluppo_gioco_schermi")
        gioco = True
    if gioco in (True, "true", "sì", "si", 1) or str(modifica or "").strip():
        t = "estensione"
    if prop and tappe in (False, "false", "no", 0, "0"):
        _tappe_rifiutate(ctx, prop)
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


def _tappe_rifiutate(ctx, prop: str):
    """«No, tutto insieme» alla proposta a tappe (11/10): il lavoro proposto `prop` perde il
    vincolo della prima tappa e parte con tutti i requisiti (regola `sviluppo_tappe_rifiutate`).
    Solo per lo sviluppo aperto di chi parla, in analisi, con quella proposta."""
    from ..sviluppo import chi
    svs = _svs(ctx)
    sv = svs.corrente(chi(ctx)) if svs is not None else None
    if sv is None or sv.fase != "analisi" or sv.proposto != prop or             sv.tappe_stato != "proposte":
        return
    svc = getattr(ctx, "lavori", None)
    prof = _prof(ctx)
    off = (svc.offerta(getattr(prof, "id", None), int(getattr(ctx, "turno", 0) or 0))
           if svc is not None and hasattr(svc, "offerta") else None)
    lav = off["lavoro"] if off is not None and getattr(off["lavoro"], "id", "") == prop else None
    svs.tappe_rifiutate(sv, lav)
    note_rule(ctx, "sviluppo_tappe_rifiutate")


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
    grezza = str(azione or "stato").strip().lower()
    azione = SINONIMI_AZIONE.get(grezza, grezza)
    persona = chi(ctx)
    if azione == "chiudi" and not str(quale or "").strip() and _chiudi_tutti_detto(ctx):
        # «Chiudi tutti gli sviluppi» detto per intero (12/10, lavoro 3; il 10/10 cinque volte
        # su cinque uno per volta): la forma della scelta già fatta dal modello (chiudi), con
        # una domanda sola per tutti (principio 10, regola `sviluppo_chiudi_tutti_forma`)
        note_rule(ctx, "sviluppo_chiudi_tutti_forma")
        quale = "tutti"
    if azione == "riprendi":
        return _riprendi(ctx, svs, persona, quale)
    if azione == "chiudi" and (_tutti(quale) or (not str(quale or "").strip()
                                                and _tutti_chiesti(ctx, persona) is not None)):
        return _chiudi_tutti(ctx, svs, persona, prof)
    sv = svs.corrente(persona)
    if azione == "stato":
        return _stato(ctx, svs, sv, persona)
    if azione == "indietro":
        return _indietro(ctx, svs, sv, prof)
    if azione == "ferma" and sv is None:
        # «Sospendi» e poi «no, fermalo» (DGX, 08/10 19:07): lo sviluppo è già sospeso, il
        # lavoro dell'agente va ancora
        al_lavoro = [s for s in svs.trova(persona, quale) if _al_lavoro(svs, s)]
        if al_lavoro:
            return _ferma(ctx, svs, al_lavoro[0], prof)
    if sv is None:
        sospesi = svs.trova(persona, quale)
        if sospesi and azione == "chiudi":
            # Chiudere uno sviluppo sospeso (10/10, DGX delle 07:14 e 07:21: «Chiudi proprio lo
            # sviluppo» e «Sospendilo e chiudilo definitivamente» → «è sospeso: vuoi
            # riprenderlo?», e non si chiudeva mai): la stessa conferma di quello aperto
            return _chiudi(ctx, svs, sospesi[0])
        if sospesi:
            s = sospesi[0]
            frase = f"Lo sviluppo di «{s.titolo}» è sospeso: vuoi riprenderlo?"
            return _final(frase, ok=False, fatto=NIENTE,
                          in_sospeso={"domanda": frase, "cosa": f"riprendere «{s.titolo}»",
                                      "tool": "sviluppo_passo",
                                      "argomenti": {"azione": "riprendi", "quale": s.id}})
        return _no(ctx, "Non c'è nessuno sviluppo aperto.")
    svs.tocca(sv)
    if (grezza in ("continua", "prosegui") and sv.fase == "revisione"
            and svs.da_completare(sv)[0]):
        # Alla revisione con qualcosa che manca la domanda è «attivarla così com'è, o faccio
        # continuare l'agente con quello che manca?» (11/10): «continua» è la seconda
        # (correzione della forma della scelta del modello, principio 10). «Avanti» resta
        # l'attivazione, con la sua frase di conferma
        note_rule(ctx, "sviluppo_continua_completa")
        azione = "completa"
    if azione == "completa":
        return _completa(ctx, svs, sv, prof)
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


def _in_attesa(svs, sv) -> object:
    """Il lavoro dello sviluppo fermo a una domanda per la persona (non una tappa), o None."""
    lav = svs._lavoro(sv.lavoro)
    if lav is not None and getattr(lav, "stato", "") == "in_attesa" and \
            _in_tappa(svs, sv) is None:
        return lav
    return None


def _chiudi(ctx, svs, sv) -> dict:
    """«Chiudi» (08/10, versione 2; DGX, 11:30: «Ok, chiuso a long», storpiato, chiudeva lo
    sviluppo con l'agente al lavoro, senza domande). Con un lavoro in corso diventa «sospendi»;
    altrimenti chiede conferma, e chiude solo al «sì» a quella domanda (il turno dopo, con
    l'azione in sospeso di sviluppo_passo): una frase breve o storpiata non chiude mai da sola.

    10/10 (DGX delle 07:17–07:18): la domanda va in fondo alla frase. Prima finiva con «Se vuoi
    solo una pausa, dimmi «sospendi»…», `Brain.set_pending` non la registrava (vuole la domanda
    alla fine), la conferma non poteva scattare e ogni «sì, chiudi» rifaceva la domanda (7 volte).
    Vale anche per uno sviluppo sospeso (`_sviluppo`)."""
    if sv.stato == "sospesa" and _al_lavoro(svs, sv):
        # Già sospeso, con l'agente ancora al lavoro: prima si ferma il lavoro
        domanda = "Vuoi che fermi il lavoro dell'agente?"
        return _final(f"Lo sviluppo di «{sv.titolo}» è sospeso, ma l'agente ci sta ancora "
                      "lavorando: prima di chiuderlo va fermato il lavoro. " + domanda,
                      ok=False, fatto="NIENTE chiuso: c'è un lavoro dell'agente in corso",
                      in_sospeso={"domanda": domanda,
                                  "cosa": f"fermare il lavoro dell'agente su «{sv.titolo}»",
                                  "tool": "sviluppo_passo", "argomenti": {"azione": "ferma"}})
    if _al_lavoro(svs, sv):
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
    domanda = "Lo chiudo?"
    frase = (f"Chiudere lo sviluppo di «{sv.titolo}» vuol dire finirlo qui; se vuoi solo una "
             f"pausa, dimmi «sospendi» e lo riprendiamo quando vuoi.{extra} {domanda}")
    return _final(frase, ok=False, fatto="NIENTE chiuso: aspetta la conferma",
                  in_sospeso={"domanda": domanda, "cosa": f"chiudere lo sviluppo di «{sv.titolo}»",
                              "tool": "sviluppo_passo", "argomenti": {"azione": "chiudi"}})


# «Chiudi tutti gli sviluppi» (10/10, terzo giro della DGX, 10:43: «Calliope ferma il lavoro e
# chiudi tutti gli sviluppi.» → solo ferma, e la seconda parte persa; 10:43:26 «Ti ho chiesto
# di fermare il lavoro e di chiudere tutti gli sviluppi» → chiudi del solo sviluppo aperto).
# `quale = "tutti"`: lo sviluppo aperto e i sospesi di chi parla, con una sola domanda («Chiudo
# «…» e «…»?»); al «sì» si chiudono tutti, e il lavoro dell'agente su uno di loro si ferma (la
# domanda lo dice). Una richiesta doppia («ferma e chiudi tutti») è una sola chiamata. Lo
# sceglie il modello (principio 10): nessuna regola sul testo
_TUTTI_DETTI = frozenset({"tutti", "tutte", "tutto", "*", "entrambi", "entrambe",
                          "tutti e due", "tutte e due", "tutti e tre", "tutti gli sviluppi",
                          "ogni sviluppo", "all"})
_TUTTI_CHIESTI: dict = {}           # persona → {"ids", "turno"}: la domanda di _chiudi_tutti


def _tutti(quale) -> bool:
    return str(quale or "").strip().lower().rstrip(".") in _TUTTI_DETTI


def _tutti_chiesti(ctx, persona) -> dict | None:
    """La domanda «Chiudo «…» e «…»?» ancora valida per chi parla, o None."""
    from ..sviluppo import CHIUSURA_TURNI
    p = _TUTTI_CHIESTI.get(_chiave(persona))
    if p is None:
        return None
    dt = int(getattr(ctx, "turno", 0) or 0) - int(p.get("turno") or 0)
    return p if 1 <= dt <= CHIUSURA_TURNI else None


def _al_lavoro(svs, sv) -> bool:
    """L'agente lavora per lo sviluppo, o il suo lavoro aspetta (una tappa, una domanda):
    chiudere o uscire lo lascia sospeso, non perso (12/10, lavoro 3: anche una domanda)."""
    lav = svs._lavoro(sv.lavoro)
    return svs.lavoro_attivo(sv) or (lav is not None
                                     and getattr(lav, "stato", "") == "in_attesa")


# Le parole intere di «chiudi tutti gli sviluppi» (12/10, lavoro 3), tolti il nome, i riempitivi
# e la cortesia: mai una parola dentro una frase più lunga («chiudi tutte le finestre»,
# «chiudi tutti i programmi del PC» restano al modello)
_CHIUDI_TUTTI = re.compile(
    r"(?:chiudi|chiudili|chiudile|chiuderli|chiudiamo|chiudiamoli|chiudete)"
    r"(?: (?:pure|proprio|adesso|ora|subito))?"
    r"(?: (?:tutti|tutte|entrambi|entrambe)(?: (?:e due|e tre|quanti|insieme))?"
    r"(?: (?:gli|i) sviluppi(?: (?:aperti|sospesi|aperti e sospesi))?)?"
    r"| (?:gli|i) sviluppi(?: (?:aperti|sospesi|aperti e sospesi))?(?: tutti)?)")
_CHIUDI_TESTA = frozenset({"si", "ok", "allora", "e", "dai", "adesso", "ora", "ecco", "no",
                           "basta", "va", "bene"})
_CHIUDI_CODA = frozenset({"pure", "grazie", "subito", "adesso", "ora", "per", "favore"})


def chiudi_tutti_detto(testo: str, name="Calliope") -> bool:
    """La frase intera è «chiudi tutti gli sviluppi» (o «chiudili tutti», «chiudi gli
    sviluppi»…)? Forma chiusa breve (principio 10): il resto lo decide il modello."""
    from ..wakeword import _NAME_MARK, _plain_words
    parole = [w for w in _plain_words(str(testo or ""), name) if w != _NAME_MARK]
    while parole and parole[-1] in _CHIUDI_CODA:
        parole.pop()
    while len(parole) > 2 and parole[0] in _CHIUDI_TESTA:
        parole.pop(0)
    if not 2 <= len(parole) <= 8:
        return False
    return bool(_CHIUDI_TUTTI.fullmatch(" ".join(parole)))


def _chiudi_tutti_detto(ctx) -> bool:
    nomi = getattr(getattr(ctx, "cfg", None), "wake_names", None) or "Calliope"
    return chiudi_tutti_detto(str(getattr(ctx, "user_text", "") or ""), nomi)


def _chiudi_tutti(ctx, svs, persona, prof) -> dict:
    from ..sviluppo import _e
    lista = []
    sv = svs.corrente(persona)
    if sv is not None:
        lista.append(sv)
    lista += [s for s in svs.trova(persona, "") if s not in lista]
    if not lista:
        return _no(ctx, "Non c'è nessuno sviluppo aperto né sospeso.")
    if len(lista) == 1:
        return _chiudi(ctx, svs, lista[0])
    ids = sorted(s.id for s in lista)
    p = _tutti_chiesti(ctx, persona)
    if (p is not None and p.get("ids") == ids
            and getattr(ctx, "tool_in_sospeso", None) == "sviluppo_passo"):
        _TUTTI_CHIESTI.pop(_chiave(persona), None)
        svc = getattr(ctx, "lavori", None)
        fermati = []
        for s in lista:
            if _al_lavoro(svs, s) and svc is not None and s.lavoro:
                res = svc.annulla(prof.id, tutti_di_tutti=True, quale=s.lavoro)
                if res.get("ok"):
                    fermati.append(f"«{s.titolo}»")
            svs.chiudi(s, "uscita")
            _schermo(ctx, s)
        note_rule(ctx, "sviluppo_chiusi_tutti")
        titoli = _e([f"«{s.titolo}»" for s in lista])
        fermo = (f"; ho fermato il lavoro dell'agente su {_e(fermati)}" if fermati else "")
        return _final(f"D'accordo: ho chiuso gli sviluppi di {titoli}{fermo}. Torniamo alla "
                      "conversazione normale.",
                      fatto=f"{len(lista)} sviluppi chiusi"
                            + (f", {len(fermati)} lavori dell'agente fermati" if fermati
                               else ""))
    _TUTTI_CHIESTI[_chiave(persona)] = {"ids": ids, "turno": int(getattr(ctx, "turno", 0) or 0)}
    note_rule(ctx, "sviluppo_chiudi_conferma")
    lavorano = [f"«{s.titolo}»" for s in lista if _al_lavoro(svs, s)]
    titoli = _e([f"«{s.titolo}»" for s in lista])
    domanda = f"Chiudo {titoli}?"
    perche = (f"; su {_e(lavorano)} l'agente sta lavorando, e il lavoro si ferma" if lavorano
              else "")
    frase = (f"Chiuderli vuol dire finirli qui{perche}; se vuoi solo una pausa, dimmi "
             f"«sospendi». {domanda}")
    return _final(frase, ok=False, fatto="NIENTE chiuso: aspetta la conferma",
                  in_sospeso={"domanda": domanda, "cosa": f"chiudere gli sviluppi di {titoli}",
                              "tool": "sviluppo_passo",
                              "argomenti": {"azione": "chiudi", "quale": "tutti"}})


def _rifaccio(sv) -> str:
    """La domanda dopo un lavoro fermato, non andato o messo da parte (nessun lavoro in corso):
    una sola, che dice dove siamo e cosa farà (12/10, lavoro 3: prima «lo rifaccio così com'è,
    o vuoi cambiare qualcosa?», e il «sì» ripartiva da zero)."""
    from ..sviluppo import MESSO_DA_PARTE
    giro = sv.giro or {}
    da_li = bool(giro.get("cartella"))
    rifaccio = ("lo rifaccio ripartendo da quello che aveva già scritto?" if da_li
                else "lo rifaccio così com'è?")
    if sv.nota in ("annullato", "fermato"):
        return f"Il lavoro dell'agente l'hai fermato tu: {rifaccio}"
    if sv.nota == MESSO_DA_PARTE or giro.get("perche") in ("tappa", "attesa") and da_li:
        cosa = "a una tappa" if giro.get("perche") == "tappa" else "a una domanda per te"
        return f"Il lavoro dell'agente era fermo {cosa} e l'ho messo da parte: riparto da lì?"
    if "riavvio" in str(sv.nota or ""):
        return f"Il lavoro dell'agente si è interrotto per un riavvio di Calliope: {rifaccio}"
    return f"Il lavoro dell'agente non è andato: {rifaccio}"


def _rifaccio_sospeso(sv) -> dict:
    """L'azione in sospeso di quella domanda (08/10 sera, DGX delle 20:05: «Sì, rifallo» →
    `analisi` senza modifica → «cosa vuoi cambiare?», poi la specifica riletta e un altro «va
    bene così»). Il «sì» va a `rifai`, che riparte subito con la stessa specifica, dai file del
    giro se ci sono; una modifica detta va all'analisi."""
    return {"domanda": "Lo rifaccio?",
            "cosa": f"rifare il lavoro di «{sv.titolo}» con la stessa specifica",
            "tool": "sviluppo_passo",
            "argomenti": "azione = rifai (sì, rifallo, riparti: riparte subito con la stessa "
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
    # I file del giro restano per «rifallo» (12/10, A5)
    svs.segna_fermato(sv, lav)
    with svs._lock:
        sv.lavoro, sv.nota = None, "annullato"
    svs.tocca(sv)
    note_rule(ctx, "sviluppo_fermato")
    _schermo(ctx, sv)
    dove = ("Lo sviluppo resta sospeso" if sv.stato == "sospesa"
            else f"Lo sviluppo resta aperto, {_alla(sv)}")
    return _final(f"Ho fermato il lavoro dell'agente su «{sv.titolo}»: non continua. {dove}: "
                  "quando vuoi lo rifaccio ripartendo da quello che aveva già scritto, o "
                  "cambiamo qualcosa.",
                  fatto="lavoro dell'agente FERMATO", lavoro=getattr(lav, "id", None))


def _rifai(ctx, svs, sv, prof, problema: str = "") -> dict:
    """«Sì, rifallo» dopo un lavoro fermato o non andato: un lavoro nuovo uguale all'ultimo
    dello sviluppo (stessa specifica, stessi vincoli e file di partenza), avviato subito: la
    specifica la persona l'aveva già accettata. Senza l'ultimo lavoro in memoria (un riavvio),
    il lavoro nuovo dalla specifica dello sviluppo.

    Con `problema` (11/10, sviluppo_correggi su uno sviluppo fermo senza una versione): lo
    stesso lavoro con il problema detto e il motivo dell'arresto nei vincoli.

    Dal 12/10 (lavoro 3, A5) sempre dai file del giro fermo (`parti_da`: li legge il thread dei
    lavori quando il lavoro nuovo comincia, perché un lavoro appena fermato li sta ancora
    copiando), non solo con `problema`: «rifallo» e «correggi» partono dallo stesso punto. A
    una tappa «rifallo» è un altro giro dello stesso lavoro."""
    from . import agenti as ta
    svc = getattr(ctx, "lavori", None)
    if svc is None:
        return _no(ctx, "Qui non ci sono agenti.")
    tappa = _in_tappa(svs, sv)
    if tappa is not None and not problema and hasattr(svc, "continua"):
        frase = svc.continua(tappa)
        if frase:
            note_rule(ctx, "sviluppo_tappa_continua")
            svs.tocca(sv)
            return _final(frase, fatto="un altro giro avviato: NON è ancora finito",
                          lavoro=tappa.id)
    if svs.lavoro_attivo(sv) or tappa is not None or _in_attesa(svs, sv) is not None:
        return _stato(ctx, svs, sv, sv.persona)
    if sv.fase == "analisi":
        return _avanti(ctx, svs, sv, prof)
    if sv.fase != "sviluppo":
        return _no(ctx, f"Non c'è un lavoro da rifare: siamo {_alla(sv)}. Se qualcosa non va, "
                        "lo faccio correggere.")
    problema = str(problema or "").strip()
    note_rule(ctx, "sviluppo_correggi_rifai" if problema else "sviluppo_rifai")
    nota = ""
    if problema:
        arresto = svs.motivo_arresto(sv)
        nota = (" Il lavoro di prima si è fermato senza consegnare"
                + (f" ({arresto.rstrip('.')})" if arresto else "")
                + ". Da correggere, detto dalla persona: «" + problema[:400] + "».")
    ultimo = None
    for voce in reversed(sv.lavori or []):
        lv = svs._lavoro(voce.get("id"))
        if lv is not None and svs._stesso_tipo(sv, lv):
            ultimo = lv
            break
    giro = sv.giro or {}
    # Da dove ripartire: il lavoro fermo in memoria, o la cartella del giro (dopo un riavvio);
    # solo se ha una cartella (un lavoro mai cominciato non ha scritto niente)
    parti_da = (ultimo if ultimo is not None and getattr(ultimo, "stato", "") != "fatto"
                else giro.get("cartella") or None)
    if parti_da is not None and not _cartella_di(parti_da):
        parti_da = None
    if ultimo is None:
        out = _nuovo_lavoro(ctx, svs, sv, prof, sv.specifica or sv.richiesta,
                            (f"Da correggere, detto dalla persona: «{problema[:400]}»."
                             if problema else ""), avvia=True, parti_da=parti_da)
        _schermo(ctx, sv)
        return _frase_rifatto(out, sv, problema, parti_da)
    lav = svc.nuovo(ultimo.tipo, ultimo.compito, prof.id, prof.name, "amministra",
                    getattr(ultimo, "formato", "") or "", getattr(ultimo, "modello", "") or "",
                    ((getattr(ultimo, "vincoli", "") or "") + nota).strip(),
                    list(getattr(ultimo, "dati", None) or []))
    for k in ("titolo", "estensione", "gioco", "specifica", "correzione"):
        if getattr(ultimo, k, None) is not None:
            setattr(lav, k, getattr(ultimo, k))
    if getattr(lav, "tipo", "") == "estensione" and svs.e_gioco(sv):
        lav.gioco = True                    # A7: il tipo dallo sviluppo, non dal flag
    lav.file_iniziali = dict(getattr(ultimo, "file_iniziali", None) or {})
    if getattr(lav, "tipo", "") == "codice" and not getattr(lav, "input", None):
        # Il file della persona resta (12/10, A6)
        _file_della_persona(ctx, svs, sv, lav)
    _metti_giro(lav, parti_da)
    out = ta._avvia(ctx, svc, lav)
    _schermo(ctx, sv)
    return _frase_rifatto(out, sv, problema, parti_da)


def _cartella_di(parti_da) -> str:
    """La cartella dei risultati di un lavoro (o la cartella stessa), "" se non ce l'ha."""
    if isinstance(parti_da, str):
        return parti_da
    r = getattr(parti_da, "risultato", None) or {}
    return str(r.get("cartella") or getattr(parti_da, "cartella", "") or "")


def _metti_giro(lav, parti_da):
    """I file del giro fermo nel lavoro nuovo (12/10, A4 e A5): quelli che ci sono già adesso,
    e `parti_da` perché il thread dei lavori li rilegga quando il lavoro comincia
    (agenti/servizio._file_del_giro): un lavoro appena fermato li sta ancora copiando, e il
    lavoro di prima di una modifica intanto va avanti."""
    if parti_da is None:
        return
    from ..sviluppo import VINCOLO_GIRO, file_del_giro
    giro = file_del_giro(parti_da)
    if giro:
        lav.file_iniziali = {**(getattr(lav, "file_iniziali", None) or {}), **giro}
        if VINCOLO_GIRO not in (getattr(lav, "vincoli", "") or ""):
            lav.vincoli = ((getattr(lav, "vincoli", "") or "").rstrip() + " "
                           + VINCOLO_GIRO).strip()
    lav.parti_da = parti_da


def _frase_rifatto(out, sv, problema: str, parti_da) -> dict:
    if not isinstance(out, dict) or out.get("ok") is False:
        return out
    if problema:
        frase = (f"D'accordo: non c'era ancora una versione da correggere, quindi rifaccio il "
                 f"lavoro di «{sv.titolo}» con la correzione, ripartendo da quello che aveva "
                 "già scritto. Ci lavora in secondo piano: te lo dico quando è pronto.")
    elif parti_da is not None:
        frase = (f"D'accordo: rifaccio il lavoro di «{sv.titolo}» ripartendo da quello che "
                 "aveva già scritto. Ci lavora in secondo piano: te lo dico quando è pronto.")
    else:
        frase = (f"D'accordo: rifaccio il lavoro di «{sv.titolo}» con la stessa specifica. "
                 "Ci lavora in secondo piano: te lo dico quando è pronto.")
    out["conferma"] = out["risposta_finale"] = frase
    return out


def _sospeso_gioco(sv) -> dict:
    """La domanda «Lo apro in prova?» al collaudo di un gioco: il «sì» è sviluppo_collauda."""
    from ..sviluppo import DOMANDA_GIOCO
    return {"domanda": DOMANDA_GIOCO, "tool": "sviluppo_collauda",
            "cosa": f"aprire «{sv.titolo}» in prova sullo schermo", "argomenti": {}}


def _alla(sv) -> str:
    from ..sviluppo import ALLA
    return ALLA.get(sv.fase, sv.fase)


def _stato(ctx, svs, sv, persona) -> dict:
    if sv is None:
        sospesi = svs.sospesi(persona)
        if not sospesi:
            return _final("Non c'è nessuno sviluppo aperto.", fatto="niente")
        # Tutti nel conto, i più recenti per nome (10/10: «Ho 4 sviluppi sospesi» con il
        # quinto, il più recente, mancante)
        from ..sviluppo import elenco
        voci = elenco(sospesi, lambda s: f"«{s.titolo}» ({_alla(s)})")
        return _final(("Ho uno sviluppo sospeso: " if len(sospesi) == 1 else
                       f"Ho {len(sospesi)} sviluppi sospesi: ") + voci
                      + ". Dimmi quale riprendere.", fatto="nessuno sviluppo aperto")
    frase = frasi_pronte.scegli("sviluppo.stato", titolo=sv.titolo, dove=svs.dove(sv))
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
    elif sv.fase == "sviluppo" and lav is not None and lav.stato == "in_attesa" and \
            getattr(lav, "domanda", ""):
        frase += f" L'agente aspetta una tua risposta: {lav.domanda}"
    elif sv.fase == "sviluppo" and sv.nota:
        frase += " " + _rifaccio(sv)
        _schermo(ctx, sv)
        return _final(frase, fatto="stato dello sviluppo: nessun lavoro in corso",
                      sviluppo=sv.id, in_sospeso=_rifaccio_sospeso(sv))
    elif sv.fase == "collaudo" and svs.e_gioco(sv):
        # Un gioco si prova guardandolo (11/10)
        from ..sviluppo import DOMANDA_GIOCO
        frase += f" È un gioco: lo apro sullo schermo, in prova, senza attivarlo. {DOMANDA_GIOCO}"
        _schermo(ctx, sv)
        return _final(frase, fatto="stato dello sviluppo", sviluppo=sv.id,
                      in_sospeso=_sospeso_gioco(sv))
    elif sv.fase == "collaudo":
        n = len(sv.collaudi)
        frase += (f" Hai fatto {'una prova' if n == 1 else f'{n} prove'}." if n else
                  " Puoi provarla prima di approvarla." if sv.tipo == "estensione"
                  else " Puoi provarlo con dati tuoi.")
    _schermo(ctx, sv)
    return _final(frase, fatto="stato dello sviluppo", sviluppo=sv.id)


def _riprendi(ctx, svs, persona, quale: str) -> dict:
    """«Riprendiamo lo sviluppo»: uno sospeso (quello detto, o il più recente), un programma
    consegnato da riaprire (12/10, M7), o quello già aperto. Dal 12/10 (lavoro 3) una frase
    sola che dice dove siamo e, se c'è un lavoro fermo, una domanda sola su cosa farà («…: lo
    rifaccio ripartendo da quello che aveva già scritto?»); il «sì» fa partire il lavoro senza
    rileggere la specifica (prima 4–5 turni: «è già aperto», «l'hai fermato tu: lo rifaccio
    così com'è, o vuoi cambiare qualcosa?», «cosa vuoi cambiare?», «va bene così?»)."""
    trovati = svs.trova(persona, quale)
    riaperto = False
    if str(quale or "").strip():
        # Un programma consegnato con quel nome vince su uno sospeso che non lo è
        chiusi = svs.riapribili(persona, quale)
        if chiusi and (not trovati or _punti(svs, chiusi[0], quale) > _punti(svs, trovati[0],
                                                                            quale)):
            trovati, riaperto = chiusi, True
    # Quello aperto, senza la sospensione pigra di `corrente` (riprenderne un altro lo sospende
    # comunque, e la frase lo deve dire)
    with svs._lock:
        aperto = next((s for s in svs.sviluppi if s.persona == persona
                       and s.stato == "aperta"), None)
    if not trovati or (aperto is not None and str(quale or "").strip() and not riaperto
                       and _punti(svs, aperto, quale) > _punti(svs, trovati[0], quale)):
        if aperto is not None:
            # Già aperto (09/10, DGX delle 20:41: «Riprendiamo lo sviluppo di…» → «è già
            # aperto», e un turno in più per sentire cosa fare): vale come ripresa
            note_rule(ctx, "sviluppo_ripreso_aperto")
            svs.tocca(aperto)
            return _ripresa(ctx, svs, aperto, "")
        return _no(ctx, "Non ho sviluppi sospesi da riprendere.")
    sv = trovati[0]
    if riaperto:
        prima = svs.riapri(sv)
        note_rule(ctx, "sviluppo_riaperto")
        testa = (f"Ho sospeso «{prima.titolo}». " if prima is not None else "")
        frase = (f"{testa}Riapro «{sv.titolo}», con la sua richiesta: siamo al collaudo. Puoi "
                 "provarlo con dati tuoi, o dirmi cosa cambiare.")
        _schermo(ctx, sv)
        return _final(frase, fatto="programma riaperto", sviluppo=sv.id)
    prima = svs.riprendi(sv)
    note_rule(ctx, "sviluppo_ripreso")
    return _ripresa(ctx, svs, sv, f"Ho sospeso «{prima.titolo}». " if prima is not None else "")


def _punti(svs, sv, quale: str) -> float:
    """Quanto il titolo di `sv` somiglia a `quale` (come Sviluppi.trova)."""
    import difflib
    q = str(quale or "").strip().lower()
    if not q:
        return 0.0
    def parole(t):
        return {w for w in re.findall(r"[a-zà-ù0-9]{3,}", t.lower())
                if w not in ("sviluppo", "estensione", "programma", "della", "dello")}
    tp = parole(f"{sv.titolo} {sv.estensione or ''}")
    comuni = sum(1 for w in parole(q) if any(w[:5] == x[:5] for x in tp))
    return comuni + difflib.SequenceMatcher(None, q, sv.titolo.lower()).ratio()


def _ripresa(ctx, svs, sv, testa: str) -> dict:
    """La frase della ripresa: dove siamo, in breve, e al più una domanda (12/10)."""
    frase = f"{testa}Riprendiamo «{sv.titolo}», eravamo {_alla(sv)}."
    extra = {}
    lav = svs._lavoro(sv.lavoro)
    tappa = _in_tappa(svs, sv)
    if sv.fase == "collaudo" and svs.e_gioco(sv):
        from ..sviluppo import DOMANDA_GIOCO
        frase += f" È un gioco: lo apro sullo schermo, in prova, senza attivarlo. {DOMANDA_GIOCO}"
        extra["in_sospeso"] = _sospeso_gioco(sv)
    elif sv.fase == "collaudo":
        frase += (" Puoi provarla prima di approvarla: dimmi «prova con…» e i dati."
                  if sv.tipo == "estensione" else " Puoi provarlo con dati tuoi.")
    elif sv.fase == "revisione":
        frase += " Vuoi andare avanti?"
        extra["in_sospeso"] = {"domanda": "Vuoi andare avanti?", "cosa": "andare avanti",
                               "tool": "sviluppo_passo", "argomenti": {"azione": "avanti"}}
    elif sv.fase == "sviluppo" and tappa is not None:
        # Fermo a una tappa (12/10, A5): il lavoro c'è ancora e aspetta la persona
        # Dopo giri finiti allo stesso punto (18/10, #174) non un altro giro uguale
        from ..agenti.servizio import giri_uguali
        uguali = bool(giri_uguali(tappa))
        domanda = ("Faccio consegnare all'agente quello che funziona già, o vuoi cambiare la "
                   "richiesta?" if uguali else "Continuo con un altro giro?")
        frase += f" Il lavoro dell'agente è fermo a una tappa e aspetta te. {domanda}"
        extra["in_sospeso"] = {"domanda": domanda, "cosa": (
                                   "consegnare quello che funziona" if uguali
                                   else "un altro giro di lavoro"),
                               "tool": "sviluppo_passo", "argomenti": {"azione": "avanti"}}
    elif sv.fase == "sviluppo" and svs.lavoro_attivo(sv):
        frase += " L'agente ci sta lavorando: te lo dico quando è pronto."
    elif sv.fase == "sviluppo" and lav is not None and lav.stato == "in_attesa":
        frase += f" L'agente aspetta una tua risposta: {getattr(lav, 'domanda', '')}"
    elif sv.fase == "sviluppo" and (sv.nota or sv.giro):
        # DGX, 08/10 20:04: ripreso dopo il lavoro fermato, «siamo allo sviluppo» e basta
        frase += " " + _rifaccio(sv)
        extra["in_sospeso"] = _rifaccio_sospeso(sv)
    elif sv.fase == "analisi" and sv.ritorno:
        frase += (" C'è una modifica che aspetta il tuo sì: affido all'agente la richiesta "
                  "cambiata, o lascio com'era?")
        extra["in_sospeso"] = {"domanda": "Affido la richiesta cambiata, o lascio com'era?",
                               "cosa": "affidare la richiesta cambiata",
                               "tool": "sviluppo_passo",
                               "argomenti": "azione = avanti per affidarla; azione = indietro "
                                            "per lasciare com'era"}
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
    from ..sviluppo import NOMI_COLLAUDO, argomenti_detti, tipo_collaudo
    casi = "; ".join(f"«{c.get('dati') or 'senza dati'}»"
                     + (f" (argomenti passati: {argomenti_detti(c)})" if c.get("argomenti")
                        else "")
                     + " → " + ("aperto in prova sullo schermo" if c.get("anteprima")
                                else NOMI_COLLAUDO[tipo_collaudo(c)]) + ": "
                     + f"{c.get('esito') or 'errore'}"
                     + (f" (la persona: {c['giudizio']})" if c.get("giudizio") else "")
                     for c in sv.collaudi[-5:])
    diagnosi = svs.diagnosi(sv)        # solo della versione provata (12/10 sera)
    rete = svs.testo_traccia(sv)
    return (f" Collaudi della versione che la persona ha provato (dati → esito): {casi}."
            + (f" Diagnosi di chi l'ha scritto, alla domanda «{diagnosi['domanda']}»: "
               f"{diagnosi.get('dettagli') or diagnosi.get('voce')}" if diagnosi else "")
            + (f" {rete}" if rete else "")
            + " Controlla che la versione nuova non abbia gli stessi problemi: aggiungi un test "
              "con ogni caso che non andava.")


def _nuovo_lavoro(ctx, svs, sv, prof, compito: str, nota: str = "", avvia: bool = False,
                  cambiamento: list | None = None, da_correggere: str = "",
                  parti_da=None) -> dict:
    """Il lavoro dello sviluppo con la specifica di adesso, proposto con «Ho capito così: …
    Va bene così?» (la persona conferma la specifica: è la fine dell'analisi). `avvia`: la
    persona l'ha già sentita e accettata («avanti», «completa»), il lavoro parte. `nota`: per
    l'agente, nei vincoli (quello che manca, per «completa»). `cambiamento` (12/10, la specifica
    viva): i cambi dei requisiti appena fatti; la proposta dice solo quelli."""
    from . import agenti as ta
    svc = getattr(ctx, "lavori", None)
    turno = int(getattr(ctx, "turno", 0) or 0)
    lav = _lavoro_dello_sviluppo(ctx, svs, sv, prof, compito,
                                 _unisci(nota, _collaudi_per_agente(svs, sv)))
    if isinstance(lav, dict):
        return lav
    _con_esempi(svs, sv, lav)
    # La tappa decisa con la persona, ciò che qui non si può fare e ciò che c'era già (11/10)
    svs._metti_vincoli(sv, lav)
    if cambiamento is not None:
        lav.cambiamento = list(cambiamento)
    if da_correggere:
        lav.da_correggere = da_correggere
    _metti_giro(lav, parti_da)
    if avvia:
        return ta._avvia(ctx, svc, lav)
    return ta._proponi(ctx, svc, lav, turno)


def _unisci(*parti) -> str:
    return " ".join(str(p).strip() for p in parti if p and str(p).strip())


def _file_della_persona(ctx, svs, sv, lav):
    """Il file della persona di un programma (12/10, A6: «rinomina le foto di questo file», poi
    «ordina per data», e il lavoro nuovo non aveva più il file): la copia del lavoro di prima
    (in memoria o su disco), oppure, se la proposta di prima non è ancora partita, lo stesso
    file da prendere."""
    inp = svs.file_persona(sv)
    if inp is not None:
        lav.input = inp
        pronto = getattr(lav, "input_pronto", None)
        if pronto is not None:
            pronto.set()
        return
    svc = getattr(ctx, "lavori", None)
    prof = _prof(ctx)
    off = (svc.offerta(getattr(prof, "id", None), int(getattr(ctx, "turno", 0) or 0))
           if svc is not None and hasattr(svc, "offerta") else None)
    prima = off["lavoro"] if off is not None and sv.proposto and \
        getattr(off["lavoro"], "id", None) == sv.proposto else None
    if prima is not None and getattr(prima, "file_utente", None) is not None:
        lav.file_utente = prima.file_utente
        lav.file_candidati = list(getattr(prima, "file_candidati", None) or [])


def _lavoro_dello_sviluppo(ctx, svs, sv, prof, compito: str, vincoli: str = ""):
    """Il costruttore unico dei lavori di uno sviluppo (12/10, A6; prima tre, e ognuno copiava
    cose diverse): modifica, correzione, «completa». Per un'estensione la versione provata, se
    c'è, con lo stesso nome; un gioco ha il contratto e lo scheletro del gioco anche se il
    modello non l'ha detto (A7: il tipo viene dallo sviluppo e dal manifesto, `e_gioco`). Per
    un programma la sua cartella, se c'è («riparti dal programma di prima» solo allora), e il
    file della persona. In ogni lavoro: i vincoli della persona e la fonte del primo lavoro, lo
    storico delle modifiche (a parte dalla specifica)."""
    svc = getattr(ctx, "lavori", None)
    if svc is None:
        return _no(ctx, "Qui non ci sono agenti.")
    storia = list(getattr(ctx, "storia", None) or [])
    ing = sv.ingressi if isinstance(sv.ingressi, dict) else {}
    storico = svs.storico_per_agente(sv)
    if sv.tipo == "estensione":
        est = getattr(ctx, "estensioni", None)
        if est is None:
            return _no(ctx, "Qui le estensioni non ci sono.")
        from ..estensioni.servizio import runtime_testo
        from .estensioni import VINCOLO_GIOCO, funzioni_di_calliope, titolo_vincolo
        gioco = svs.e_gioco(sv)
        file = {"calliope_estensione.py": runtime_testo()}
        testa = ""
        if sv.estensione:
            testa = (f"È lo sviluppo dell'estensione «{sv.estensione}»: i suoi file (la versione "
                     "che la persona ha provato) sono già nella cartella; tieni lo stesso nome "
                     "nel manifesto. " + titolo_vincolo(est, sv.estensione))
            file.update(est.file_per_modifica(sv.estensione, candidata=True))
        v = _unisci(testa, ing.get("vincoli"), storico, vincoli, funzioni_di_calliope(),
                    VINCOLO_GIOCO if gioco else "")
        lav = svc.nuovo("estensione", compito, prof.id, prof.name, "amministra", "", "", v,
                        storia)
        lav.estensione = sv.estensione or None
        lav.gioco = gioco
        lav.file_iniziali = file
    else:
        from ..sviluppo import file_di_codice
        file = file_di_codice(sv.cartella) if sv.cartella else {}
        v = _unisci("Riparti dal programma di prima: i suoi file sono già nella cartella."
                    if file else "", ing.get("vincoli"), storico, vincoli)
        lav = svc.nuovo("codice", compito, prof.id, prof.name, "amministra", "", "", v, storia)
        lav.file_iniziali = file
        _file_della_persona(ctx, svs, sv, lav)
    lav.titolo = sv.titolo
    lav.specifica = compito
    return lav


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
    """Si torna all'analisi da qualunque fase, con la modifica detta. Dal 12/10 (la specifica
    viva) la modifica è un'operazione sui requisiti (`_modifica`): il lavoro si ferma e la
    proposta nuova dice solo cosa è cambiato; se la frase non dice cosa cambiare, o dice una
    cosa che c'è già, niente si ferma."""
    svc = getattr(ctx, "lavori", None)
    if svc is None:
        return _no(ctx, "Qui non ci sono agenti.")
    if cambia and sv.tipo in ("programma", "estensione"):
        from ..sviluppo import altro_compito_in_cambia
        if altro_compito_in_cambia(cambia, sv, svs.e_gioco(sv)):
            # Un altro compito non è una modifica dell'analisi (10/10, terzo giro della DGX:
            # con «…converte i gradi Celsius in Fahrenheit» all'analisi, «…converte i
            # chilometri in miglia» → analisi con cambia = il compito nuovo → «Ho capito così:
            # …Celsius… Con questa modifica: …chilometri…», due volte). La stessa domanda di
            # sviluppo_apri con un compito diverso: niente si ferma né cambia prima del «sì»
            note_rule(ctx, "sviluppo_altro_bloccato")
            note_rule(ctx, "sviluppo_analisi_altro")
            return _domanda_cambio(ctx, sv, {"tipo": sv.tipo, "compito": cambia})
    note_rule(ctx, "sviluppo_analisi")
    from ..sviluppo import senza_contenuto
    if cambia and senza_contenuto(cambia, sv) and not _cosa_appena_chiesta(ctx, consuma=True):
        # Una modifica che non dice cosa cambiare (12/10 sera, 08:38: «Vorrei modificare
        # Halloween le porte magiche.» → cambia = «modifica le regole o il funzionamento come
        # desideri», preso per un difetto: «Lo faccio correggere?»). La domanda, una volta: la
        # risposta che segue passa al modello dell'agente anche se è breve
        note_rule(ctx, "sviluppo_modifica_riempitivo")
        note_rule(ctx, "sviluppo_modifica_vaga")
        svs.tocca(sv)
        _schermo(ctx, sv)
        return _chiedi_cosa(ctx, sv, "Cosa vuoi cambiare, di preciso?", "analisi")
    if not cambia:
        # «Torniamo all'analisi» senza dire cosa (12/10, A4): niente si ferma né cambia fase
        # finché la modifica non c'è e non è confermata; il lavoro in corso continua, la
        # versione provata resta (prima il lavoro si fermava subito e indietro non si tornava)
        note_rule(ctx, "sviluppo_analisi_senza_modifica")
        svs.tocca(sv)
        frase = "D'accordo: cosa vuoi cambiare?"
        if svs.lavoro_attivo(sv):
            frase = ("D'accordo: cosa vuoi cambiare? Intanto l'agente continua: lo fermo solo "
                     "quando la modifica è decisa.")
        _schermo(ctx, sv)
        return _final(frase, fatto="niente cambiato: manca la modifica",
                      in_sospeso={"domanda": "Cosa vuoi cambiare?",
                                  "cosa": "la modifica allo sviluppo",
                                  "tool": "sviluppo_passo",
                                  "argomenti": "azione = analisi, cambia = la modifica come "
                                               "detta dalla persona"})
    prima = svs.istantanea(sv)
    m = _modifica(ctx, svs, sv, cambia, "analisi")
    if m["esito"] == "risposta":
        return m["out"]
    if m["esito"] == "cambi":
        return _proponi_modifica(ctx, svs, sv, prof, cambia, m["cambi"], prima)
    if m["esito"] in ("difetto", "gia"):
        return _gia_nella_richiesta(ctx, svs, sv, cambia, m["esito"])
    # Senza i requisiti (sviluppo_requisiti: false, o niente agente): la specifica con la
    # modifica in coda, come prima del 12/10; il lavoro in corso si ferma comunque solo al «sì»
    base = (sv.specifica or sv.richiesta or "").strip().rstrip(".")
    return _proponi_modifica(ctx, svs, sv, prof, cambia, None, prima,
                             compito=_con_modifica(base, cambia),
                             nota=f"Cambiamento chiesto dalla persona: «{cambia}».")


def _con_fermato(ctx, sv, out, fermato: str):
    if isinstance(out, dict) and fermato:
        for k in ("conferma", "risposta_finale"):
            if isinstance(out.get(k), str):
                out[k] = fermato + out[k]
    _schermo(ctx, sv)
    return out


# «Cosa non va?» chiesto da sviluppo_correggi (12/10): persona → turno. La risposta richiama
# sviluppo_correggi con l'azione in sospeso, e allora non si richiede
_COSA_CHIESTA: dict = {}


def _modifica(ctx, svs, sv, testo: str, da: str, gia_chiesto: bool = False) -> dict:
    """La frase della persona diventa un'operazione sui requisiti (12/10, la specifica viva,
    A3): la stessa per «cambia» (sviluppo_passo analisi) e per «correggi»
    (sviluppo_correggi). Il modello dell'agente dice se chiede un comportamento diverso
    (cambia: i requisiti si aggiornano), un difetto del codice o niente di preciso (vago: si
    chiede). Restituisce {esito}: «cambi» (con i cambi applicati), «difetto», «gia» (c'era
    già), «risposta» (con `out`, da dare: la domanda, o il guasto per «cambia»), «senza» (i
    requisiti non si usano: come prima)."""
    if not getattr(ctx.cfg, "sviluppo_requisiti", True):
        return {"esito": "senza"}
    r = svs.aggiorna_requisiti(sv, testo, str(getattr(ctx, "user_text", "") or ""),
                               attesa=getattr(ctx, "attesa", None))
    esito = r.get("esito")
    if esito in ("senza agente", "nessun requisito", "senza specifica"):
        # Niente requisiti da cui partire (l'agente non c'è, o non ne ha estratti): come prima
        return {"esito": "senza"}
    tool = "sviluppo_correggi" if da == "correggi" else "sviluppo_passo"
    if esito != "modello":
        if da == "correggi":
            return {"esito": "difetto"}       # la correzione parte comunque, come prima
        note_rule(ctx, "sviluppo_modifica_guasto")
        domanda = "Riprovo?"
        frase = ("Adesso non riesco a mettere la modifica nella richiesta"
                 + (": ci mette troppo" if esito == "tempo" else "") + ". " + domanda)
        return {"esito": "risposta", "out": _final(
            frase, ok=False, fatto=f"{NIENTE}: la richiesta NON è cambiata",
            guasto="un guasto di adesso, non una cosa che non sai fare",
            in_sospeso={"domanda": domanda, "cosa": "rifare la modifica", "tool": tool,
                        "argomenti": {"azione": "analisi", "cambia": testo}})}
    if r.get("cambi"):
        note_rule(ctx, "sviluppo_modifica_requisiti")
        return {"esito": "cambi", "cambi": r["cambi"]}
    if r.get("tipo") == "vago":
        if da == "correggi" and not _va_chiesto(ctx, svs, sv, gia_chiesto):
            return {"esito": "difetto"}
        note_rule(ctx, "sviluppo_modifica_vaga")
        domanda = r.get("domanda") or ("Cosa non va, di preciso?" if da == "correggi"
                                       else "Cosa vuoi cambiare, di preciso?")
        return {"esito": "risposta", "out": _chiedi_cosa(ctx, sv, domanda, da)}
    return {"esito": "difetto" if r.get("tipo") == "difetto" else "gia"}


def _cosa_appena_chiesta(ctx, consuma: bool = False) -> bool:
    """«Cosa non va?» è stato chiesto a chi parla da poco (la risposta arriva adesso);
    `consuma`: la domanda vale una volta."""
    from ..sviluppo import chi
    chiave = str(chi(ctx))
    turno = int(getattr(ctx, "turno", 0) or 0)
    si = 0 <= turno - int(_COSA_CHIESTA.get(chiave, -99)) <= 2
    if consuma:
        _COSA_CHIESTA.pop(chiave, None)
    return si


def _va_chiesto(ctx, svs, sv, gia_chiesto: bool = False) -> bool:
    """«Correggilo» senza dire cosa: si chiede solo se l'agente non ha niente da cui partire
    (nessun collaudo fallito o giudicato sbagliato, nessuna diagnosi da correggere) e non si è
    appena chiesto."""
    if gia_chiesto or _cosa_appena_chiesta(ctx) or sv.fase not in ("collaudo", "revisione",
                                                                    "attivazione"):
        # Un lavoro fermo prima della consegna ha il motivo dell'arresto da cui ripartire
        return False
    if any((not c.get("ok") and not c.get("anteprima")) or c.get("giudizio")
           for c in sv.collaudi[-5:]):
        return False
    return not any(q.get("correzione") for q in svs.chiesti_ora(sv)[-3:])


def _chiedi_cosa(ctx, sv, domanda: str, da: str) -> dict:
    from ..sviluppo import chi
    # La risposta che arriva adesso non si richiede (anche per «cambia», 12/10 sera)
    _COSA_CHIESTA[str(chi(ctx))] = int(getattr(ctx, "turno", 0) or 0)
    if da == "correggi":
        # 12/10, caso vero (11/10 19:25): «non ci siamo, ci sono cose che non funzionano,
        # correggile» → all'agente il problema «il gioco non funziona correttamente»
        _COSA_CHIESTA[str(chi(ctx))] = int(getattr(ctx, "turno", 0) or 0)
        note_rule(ctx, "sviluppo_correggi_chiede")
        _schermo(ctx, sv)
        return _final(domanda, ok=False, fatto=f"{NIENTE}: chiesto cosa non va, l'agente NON è "
                                               "ripartito",
                      in_sospeso={"domanda": domanda, "cosa": "cosa correggere",
                                  "tool": "sviluppo_correggi",
                                  "argomenti": "problema = cosa non va, come detto dalla "
                                               "persona"})
    return _final(domanda, ok=False, fatto=f"{NIENTE}: chiesto cosa cambiare",
                  in_sospeso={"domanda": domanda, "cosa": "la modifica allo sviluppo",
                              "tool": "sviluppo_passo",
                              "argomenti": "azione = analisi, cambia = la modifica come detta "
                                           "dalla persona"})


def _proponi_modifica(ctx, svs, sv, prof, detto: str, cambi: list | None,
                      prima: dict | None = None, compito: str = "", nota: str = "") -> dict:
    """I requisiti sono cambiati (12/10): si torna all'analisi e il lavoro nuovo (dai file della
    versione provata, se c'è) si propone dicendo solo cosa è cambiato («Ho cambiato due cose: …
    Va bene così, o la cambiamo?»).

    Dal 12/10 (lavoro 3, A4) il lavoro in corso NON si ferma qui: si ferma al «sì» alla
    proposta (`Sviluppi.avviato`), e il lavoro nuovo riparte dai file che aveva scritto. Fino ad
    allora «lascia com'era» (`sviluppo_passo indietro`) torna dov'eravamo: al collaudo della
    versione provata, o al lavoro che intanto è andato avanti (`Sviluppi.ritorno`)."""
    lav_prima = svs._lavoro(sv.lavoro)
    vivo = lav_prima is not None and getattr(lav_prima, "stato", "") in (
        "in_coda", "in_corso", "in_attesa")
    if prima is None or not svs.tieni_ritorno(sv, prima):
        # Niente a cui tornare (all'analisi, senza lavoro): come prima
        vivo = False
    parti_da = lav_prima if vivo else None
    if vivo:
        note_rule(ctx, "sviluppo_modifica_lavoro_continua")
    svs.passa(sv, "analisi", "modifica: " + str(detto or "")[:120])
    sv.lavoro, sv.nota = None, ""
    svs.tocca(sv)
    out = _nuovo_lavoro(ctx, svs, sv, prof, compito or sv.specifica or sv.richiesta, nota,
                        cambiamento=cambi, parti_da=parti_da)
    rit = sv.ritorno or {}
    testa = ""
    if vivo:
        testa = "Il lavoro di prima intanto continua: lo fermo solo al tuo sì. "
    elif rit.get("fase") in ("collaudo", "revisione", "attivazione") and rit.get("versione"):
        testa = (f"La versione {rit['versione']} resta: se lasci com'era, torniamo a "
                 "provarla. ")
    elif rit.get("fase") in ("collaudo", "revisione"):
        testa = "Quello che c'è resta: se lasci com'era, torniamo a provarlo. "
    return _con_fermato(ctx, sv, out, testa)


def _indietro(ctx, svs, sv, prof) -> dict:
    """«Lascia com'era», «no, torna com'era» alla modifica proposta (12/10, A4): lo sviluppo
    torna dov'era prima della modifica (fase, versione provata, requisiti, il lavoro che intanto
    è continuato) e la proposta si scarta. Regola `sviluppo_modifica_lasciata`."""
    if sv is None:
        return _no(ctx, "Non c'è nessuno sviluppo aperto.")
    if not sv.ritorno:
        return _no(ctx, "Non c'è una modifica da togliere: la richiesta è quella di prima.")
    proposto = sv.proposto
    svc = getattr(ctx, "lavori", None)
    r = svs.ripristina(sv)
    if proposto and svc is not None and hasattr(svc, "ritira"):
        try:
            svc.ritira(prof.id, proposto)
        except Exception:  # noqa: BLE001 — la proposta scade comunque
            pass
    note_rule(ctx, "sviluppo_modifica_lasciata")
    _schermo(ctx, sv)
    frase = f"D'accordo, lascio «{sv.titolo}» com'era"
    extra = {}
    tappa = _in_tappa(svs, sv)
    if svs.lavoro_attivo(sv):
        frase += ": l'agente continua il lavoro di prima."
    elif tappa is not None:
        domanda = "Continuo con un altro giro?"
        frase += f": il lavoro di prima è fermo a una tappa. {domanda}"
        extra["in_sospeso"] = {"domanda": domanda, "cosa": "un altro giro di lavoro",
                               "tool": "sviluppo_passo", "argomenti": {"azione": "avanti"}}
    elif sv.fase == "collaudo":
        v = f", versione {sv.versione}" if sv.versione and sv.tipo == "estensione" else ""
        frase += f": siamo di nuovo al collaudo{v}."
        if svs.e_gioco(sv):
            from ..sviluppo import DOMANDA_GIOCO
            frase += f" {DOMANDA_GIOCO}"
            extra["in_sospeso"] = _sospeso_gioco(sv)
    elif sv.fase == "sviluppo" and (sv.nota or sv.giro):
        frase += ". " + _rifaccio(sv)
        extra["in_sospeso"] = _rifaccio_sospeso(sv)
    else:
        frase += f": siamo {_alla(sv)}."
    return _final(frase, fatto="modifica lasciata: lo sviluppo è com'era",
                  tornato=(r or {}).get("fase"), **extra)


def _gia_nella_richiesta(ctx, svs, sv, detto: str, esito: str) -> dict:
    """La modifica detta c'era già nei requisiti: niente si ferma. Con del codice consegnato e
    un difetto («non lo fa»), la domanda «Lo faccio correggere?» (il «sì» va a
    sviluppo_correggi); con una proposta aperta, la sua domanda di nuovo."""
    note_rule(ctx, "sviluppo_modifica_gia")
    if esito == "difetto" and (sv.versione or sv.cartella or sv.estensione):
        domanda = "Lo faccio correggere?"
        cosa = "il gioco" if svs.e_gioco(sv) else sv.cosa()
        # 12/10 sera: prima «Questo la richiesta lo dice già: …» (sgrammaticato)
        return _final(f"La richiesta lo dice già: se {cosa} non lo fa, va corretto il codice. "
                      f"{domanda}", ok=False, fatto=f"{NIENTE}: la richiesta non cambia",
                      in_sospeso={"domanda": domanda, "tool": "sviluppo_correggi",
                                  "cosa": f"far correggere «{sv.titolo}»",
                                  "argomenti": {"problema": detto}})
    if sv.proposto and sv.fase == "analisi":
        domanda = svs.domanda_proposta(sv)
        return _final(f"Questo nella richiesta c'è già: non cambio niente. {domanda}", ok=False,
                      fatto=f"{NIENTE}: la richiesta non cambia",
                      in_sospeso={"domanda": domanda, "tool": "sviluppo_apri",
                                  "cosa": f"affidare all'agente «{sv.titolo}»",
                                  "argomenti": {"proposta": sv.proposto}})
    return _final("Questo nella richiesta c'è già: non cambio niente.", ok=False,
                  fatto=f"{NIENTE}: la richiesta non cambia")


def _con_modifica(base: str, cambia: str) -> str:
    """La specifica con la modifica detta, SOLO senza i requisiti (`sviluppo_requisiti:
    false`): dal 12/10 la modifica cambia i requisiti e la specifica si rigenera (la coda «Con
    questa modifica» lasciava le contraddizioni). Se la modifica è la specifica di adesso detta
    di nuovo, o ci sta dentro, la specifica resta com'è."""
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
                return _nuovo_lavoro(ctx, svs, sv, prof, sv.specifica, avvia=True,
                                     parti_da=svs.lavoro_di_prima(sv))
        if sv.specifica:
            return _nuovo_lavoro(ctx, svs, sv, prof, sv.specifica,
                                 parti_da=svs.lavoro_di_prima(sv))
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
        if svs.lavoro_attivo(sv) or _in_attesa(svs, sv) is not None:
            return _stato(ctx, svs, sv, sv.persona)
        if sv.nota or sv.giro:
            # «Avanti», «sì, procedi» con il lavoro fermo (12/10, lavoro 3): vuol dire rifarlo,
            # senza un'altra domanda (prima «lo rifaccio così com'è, o…?» di nuovo)
            note_rule(ctx, "sviluppo_avanti_rifai")
            return _rifai(ctx, svs, sv, prof)
        return _final(_rifaccio(sv), ok=False, fatto=NIENTE, in_sospeso=_rifaccio_sospeso(sv))
    if sv.fase == "collaudo":
        return _revisione(ctx, svs, sv)
    if sv.fase in ("revisione", "attivazione"):
        if sv.tipo == "programma":
            svs.chiudi(sv, "consegnato")
            note_rule(ctx, "sviluppo_chiuso")
            _schermo(ctx, sv)
            return _final(f"Fatto: lo sviluppo di «{sv.titolo}» è chiuso. Il programma resta "
                          "nella cartella Lavori: per usarlo di nuovo, chiedimi di eseguirlo; "
                          "per cambiarlo, di riaprirlo.",
                          fatto="sviluppo chiuso: si può riaprire con la sua richiesta")
        est = getattr(ctx, "estensioni", None)
        if est is None:
            return _no(ctx, "Qui le estensioni non ci sono.")
        if not sv.estensione:
            return _no(ctx, "Non c'è ancora una versione da attivare: prima la facciamo e la "
                            "proviamo.")
        svs.passa(sv, "attivazione", "avanti")
        out = est.gestisci(ctx, "approva", sv.estensione)
        fatto = str((out or {}).get("fatto") or "") if isinstance(out, dict) else ""
        if isinstance(out, dict) and out.get("ok") is False and not out.get("in_sospeso")                 and "frase di conferma" not in fatto and "serve la voce" not in fatto:
            # Non si può approvare (test, testi): si resta alla revisione
            svs.passa(sv, "revisione", "approvazione non riuscita")
        return out
    return _no(ctx, "Non c'è niente da far andare avanti.")


def _verifica_per_la_voce(ctx, svs, sv):
    """Il confronto con la richiesta per la versione di adesso: quello fatto alla consegna o,
    se manca, uno nuovo nel turno della voce (con la frase d'attesa, entro
    sviluppo_verifica_voce_s)."""
    if svs.verifica_valida(sv) or not getattr(ctx.cfg, "sviluppo_requisiti", True):
        return
    svs.verifica_consegna(sv, attesa=getattr(ctx, "attesa", None), dalla_voce=True,
                          tempo_s=float(getattr(ctx.cfg, "sviluppo_verifica_voce_s", 20.0)
                                        or 20.0))


def _completa(ctx, svs, sv, prof) -> dict:
    """«Continua a farli» (11/10, revisione onesta): l'agente fa quello che manca rispetto
    alla specifica approvata (i requisiti della tappa di adesso mancanti o fatti in parte; se
    non ce ne sono, la tappa dopo). È una modifica dello stesso sviluppo: la specifica non
    cambia, i file di partenza sono quelli della versione consegnata, il lavoro parte subito
    (la persona ha appena detto di sì a «faccio continuare l'agente?»)."""
    from ..requisiti import elenco_voce, pulito
    if svs.lavoro_attivo(sv) or _in_tappa(svs, sv) is not None:
        return _stato(ctx, svs, sv, sv.persona)
    if sv.fase not in ("collaudo", "revisione", "attivazione"):
        return _no(ctx, "Prima finiamo questo giro: quando l'agente consegna, ti dico cosa "
                        "manca rispetto alla richiesta.")
    _verifica_per_la_voce(ctx, svs, sv)
    voci, tappa_dopo = svs.da_completare(sv)
    if not voci:
        if svs.verifica_valida(sv):
            return _final("Rispetto alla richiesta non manca niente: se vuoi cambiare qualcosa, "
                          "dimmi cosa.", ok=False, fatto=NIENTE)
        return _no(ctx, "Non sono riuscita a confrontarla con la richiesta, quindi non so dirti "
                        "cosa manca: dimmi tu cosa far fare all'agente.")
    note_rule(ctx, "sviluppo_completa")
    fase_prima, tappa_prima = sv.fase, sv.tappa
    if tappa_dopo:
        sv.tappa = max(1, sv.tappa) + 1
        note_rule(ctx, "sviluppo_tappa_dopo")
    elenco = "; ".join(v["testo"] + (f" (ora: {pulito(v['nota'], 120)})" if v.get("nota")
                                      else "") for v in voci)
    cambia = (f"Tappa {sv.tappa} dello stesso sviluppo, aggiungi: {elenco}" if tappa_dopo else
              f"Completa quello che manca rispetto alla specifica approvata: {elenco}")
    base = (sv.specifica or sv.richiesta or "").strip().rstrip(".")
    svs.passa(sv, "sviluppo", "completa: " + ", ".join(v["testo"] for v in voci)[:120])
    out = _nuovo_lavoro(ctx, svs, sv, prof, base, cambia, avvia=True)
    testi = elenco_voce([v["testo"] for v in voci])
    testa = (f"D'accordo, passiamo alla tappa {sv.tappa}: {testi}. " if tappa_dopo else
             f"D'accordo: l'agente continua con quello che manca, {testi}. ")
    if isinstance(out, dict) and out.get("ok") is not False:
        for k in ("conferma", "risposta_finale"):
            if isinstance(out.get(k), str):
                out[k] = testa + out[k]
    elif isinstance(out, dict):
        # Non è partito (agenti o estensioni che mancano): si torna dov'eravamo
        sv.tappa = tappa_prima
        svs.passa(sv, fase_prima, "completa non partito")
    _schermo(ctx, sv)
    return out


def _revisione(ctx, svs, sv) -> dict:
    """Dal collaudo alla revisione: permessi, rete, analisi del codice, test, collaudi e
    differenze, detti in breve e per intero sulla scheda."""
    from ..sviluppo import conto_collaudi, misura_programma
    # Le anteprime di un gioco (11/10) non sono prove «riuscite»: l'ha visto la persona
    anteprime = [c for c in sv.collaudi if c.get("anteprima")]
    # Le prove di questa versione (12/10): quelle delle versioni di prima non dicono niente di lei
    collaudi = [c for c in sv.collaudi if not c.get("anteprima")
                and (sv.versione is None or c.get("versione") in (None, sv.versione))]
    # Le risposte buone separate da ciò che è girato senza trovare niente (12/10, caso vero:
    # «Prove: 16, 15 riuscite» con sette «non trovato»); il collaudo saltato si dice (caso vero
    # dell'11/10 16:26: niente prove e «tutto sembra in ordine» detto dal modello)
    detto_coll = conto_collaudi(collaudi) or "Il collaudo l'hai saltato: nessuna prova fatta."
    if not collaudi and not anteprime:
        note_rule(ctx, "sviluppo_revisione_senza_collaudo")
    if anteprime:
        detto_coll = (("L'hai visto in prova sullo schermo." if len(anteprime) == 1 else
                       f"L'hai visto in prova sullo schermo {len(anteprime)} volte.")
                      + (f" {detto_coll}" if collaudi else ""))
    elif svs.e_gioco(sv):
        detto_coll = "Il collaudo l'hai saltato: non l'hai visto in prova sullo schermo."
    # La revisione onesta (11/10, caso vero del gioco di Halloween: «tutto sembra in ordine: i
    # test passano tutti» con voce, musica e porte variabili mancanti): requisito per requisito,
    # la specifica approvata confrontata con i file consegnati (calliope/requisiti.py); se il
    # confronto non c'è lo si dice. Poi la domanda: attivarla così com'è o completarla
    _verifica_per_la_voce(ctx, svs, sv)
    confronto = svs.frase_confronto(sv) if (sv.requisiti or sv.verifica) else ""
    manca, tappa_dopo = svs.da_completare(sv)
    if confronto:
        note_rule(ctx, "sviluppo_revisione_requisiti")
    if manca:
        note_rule(ctx, "sviluppo_revisione_manca")
    if sv.tipo == "estensione":
        est = getattr(ctx, "estensioni", None)
        rev = est.revisione(sv.estensione) if est is not None and sv.estensione else None
        if rev is None:
            return _no(ctx, "Non c'è una versione da rivedere: forse è già stata approvata.")
        sv.revisione = rev["testo"] + f"\n- {detto_coll}"
        fumo = ""
        if svs.e_gioco(sv):
            # La prova di fumo è un test di avvio, non delle regole (11/10)
            from ..requisiti import frase_fumo
            fumo = frase_fumo(_test_della_versione(est, sv, rev))
            if fumo:
                sv.revisione += f"\n- {fumo}"
        svs.passa(sv, "revisione", "avanti dal collaudo")
        note_rule(ctx, "sviluppo_revisione")
        _schermo(ctx, sv)
        detto = " ".join(x for x in (rev["frase"], fumo, detto_coll, confronto) if x)
        if not rev["approvabile"]:
            return _final(f"{detto} Così non si può approvare: dimmi cosa correggere.",
                          fatto="revisione detta")
        if manca:
            # Manca qualcosa (11/10): attivarla così com'è, o far continuare l'agente
            domanda = ("Vuoi attivarla così com'è, o passo alla tappa dopo?" if tappa_dopo else
                       "Vuoi attivarla così com'è, o faccio continuare l'agente con quello che "
                       "manca?")
            return _final(f"{detto} {domanda}", fatto="revisione detta: NON è ancora attiva",
                          _fidati=[str(sv.titolo or "")],
                          in_sospeso=_sospeso_completa(
                              domanda, f"attivare «{sv.titolo}» così com'è o completarla",
                              "attivarla così com'è", tappa_dopo))
        # La domanda in fondo (09/10, caso vero della DGX delle 21:00: con «Vuoi attivarla? Ti
        # chiederò la frase di conferma.» la risposta non finiva con «?», l'azione in sospeso
        # non restava e «Sì, attivarla.» arrivava alla politica senza la proposta). Il titolo
        # viene dallo stato dello sviluppo: un nome fidato per la risposta (`_fidati`)
        frase = f"{detto} Ti chiederò la frase di conferma: vuoi attivarla?"
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
             f"righe.{t} {detto_coll}" + (f" {confronto}" if confronto else "")
             + " Il codice è sullo schermo, se ce l'hai.")
    sv.revisione = (f"- File di codice: {misura['file']}\n- Righe: {misura['righe']}\n"
                    f"- {t.strip() or 'Test: nessuno'}\n- {detto_coll}")
    svs.passa(sv, "revisione", "avanti dal collaudo")
    note_rule(ctx, "sviluppo_revisione")
    soglia = int(getattr(ctx.cfg, "sviluppo_programma_righe", 150) or 150)
    grande = misura["righe"] >= soglia or misura["file"] >= 3 or len(collaudi) >= 3
    _schermo(ctx, sv)
    if grande and not sv.proposta_estensione and not manca:
        sv.proposta_estensione = True
        svs.tocca(sv)
        note_rule(ctx, "sviluppo_proposta_estensione")
        domanda = ("È un programma bello grosso: vuoi che diventi un'estensione? Un programma si "
                   "esegue adesso e basta; un'estensione resta, la richiami a voce quando vuoi, "
                   "ha i permessi approvati da te e le sue versioni.")
        return _final(f"{frase} {domanda}", fatto="revisione detta",
                      in_sospeso={"domanda": domanda, "cosa": "farne un'estensione",
                                  "tool": "sviluppo_passo", "argomenti": {"azione": "promuovi"}})
    if manca:
        # Manca qualcosa (11/10): chiuderlo così com'è, o far continuare l'agente
        domanda = ("Lo chiudo così com'è, o passo alla tappa dopo?" if tappa_dopo else
                   "Lo chiudo così com'è, o faccio continuare l'agente con quello che manca?")
        return _final(f"{frase} {domanda}", fatto="revisione detta",
                      in_sospeso=_sospeso_completa(
                          domanda, f"chiudere «{sv.titolo}» così com'è o completarlo",
                          "chiuderlo così com'è", tappa_dopo))
    frase += " Va bene così?"
    return _final(frase, fatto="revisione detta",
                  in_sospeso={"domanda": "Va bene così?", "cosa": "chiudere lo sviluppo",
                              "tool": "sviluppo_passo", "argomenti": {"azione": "avanti"}})


# La domanda della revisione quando manca qualcosa (11/10): due strade, le sceglie il modello
ARGOMENTI_COMPLETA = ("azione = completa se vuole che l'agente faccia quello che manca "
                      "(«continua», «falli», «completalo», «sì, continua»); azione = avanti se "
                      "va bene così com'è («attivala così», «va bene così»)")


# La domanda con due strade (12/10 sera, caso vero delle 12:20: a «Vuoi attivarla così com'è, o
# faccio continuare l'agente con quello che manca?» la persona ha detto «No, farlo continuare con
# quello che manca.»: nessun tool, e la voce ha promesso «Ti avviso quando è pronto»). Il
# messaggio di sempre diceva «se acconsente chiama…, se rifiuta non farlo», e il blocco dello
# stato la trattava come un sì/no senza gli argomenti: il «no» davanti alla seconda strada
# sembrava un rifiuto. Un messaggio suo: le due strade, e il «no» che va alla prima
SCELTA_COMPLETA_MSG = (
    "Azione in sospeso: poco fa hai chiesto «{domanda}». È una scelta tra due strade, non un sì "
    "o un no. Se chi parla vuole che l'agente continui con quello che manca{tappa} («continua», "
    "«fallo continuare», «completalo», anche con un «no» davanti: «No, fallo continuare con "
    "quello che manca» rifiuta la prima strada e sceglie la seconda), chiama subito "
    "sviluppo_passo con azione = completa. Se vuole {prima} («va bene così», «attivala così»), "
    "sviluppo_passo con azione = avanti. La frase la dice il tool: non promettere niente senza "
    "chiamarlo. Se chiede altro, rispondi a quello.")


def _sospeso_completa(domanda: str, cosa: str, prima: str, tappa_dopo: bool) -> dict:
    return {"domanda": domanda, "cosa": cosa, "tool": "sviluppo_passo",
            "argomenti": ARGOMENTI_COMPLETA,
            "messaggio": SCELTA_COMPLETA_MSG.format(
                domanda=domanda, prima=prima,
                tappa=" (o passi alla tappa dopo)" if tappa_dopo else "")}


def _test_della_versione(est, sv, rev) -> dict | None:
    """I test della versione in revisione (archivio delle estensioni), o None."""
    try:
        ver = est.archivio.versione(sv.estensione, rev.get("versione") or sv.versione) or {}
        return ver.get("test") or None
    except Exception:  # noqa: BLE001
        return None


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


def tipo_collaudo(out, ris, passati=None) -> str:
    """Il tipo di un collaudo (12/10, calliope/sviluppo.TIPI_COLLAUDO): «errore» se si è
    fermata (nessun risultato), poi dal risultato come per gli altri tool
    (argomenti_incerti.esito): «vuoto» per un «non trovato», «errore_dichiarato» per un campo
    d'errore che l'estensione restituisce, «risposta» per il resto."""
    if not isinstance(out, dict) or ris is None:
        return "errore"
    from ..argomenti_incerti import esito
    try:
        e = esito(out, passati)
    except Exception:  # noqa: BLE001 — nel dubbio, dal solo campo d'errore
        e = "errore" if _fallito(out, ris) else "pieno"
    if e == "vuoto":
        return "vuoto"
    if e == "errore" or _fallito(out, ris):
        return "errore_dichiarato"
    if isinstance(ris, dict) and _solo_non_trovato(ris, passati):
        return "vuoto"
    return "risposta"


def _solo_non_trovato(ris: dict, passati) -> bool:
    """Il risultato è solo una frase che comincia dicendo di non aver trovato (S1 dell'08/10:
    «Non ho trovato il meteo per Borgoverde Alto. Verifica i nomi.», per argomenti_incerti
    «pieno» perché il nome non segue subito «trovato»), senza nessun dato accanto. Decide solo
    il conteggio e le parole della frase (che sono comunque quelle dell'estensione); contrario:
    «Non ho trovato pioggia: sereno, 21 gradi» con i dati."""
    from .. import argomenti_incerti as ai
    testo = str(ris.get("da_dire") or ris.get("messaggio") or "").strip()
    if not testo or ai._ha_dati(ris, ai._valori(passati)):
        return False
    m = ai._NON_TROVATO.search(testo)
    return bool(m) and m.start() <= 3


def _collauda_estensione(ctx, svs, sv, est, passati: dict, detti: str):
    """Un collaudo della versione candidata con questi argomenti: (risultato per il modello,
    fallito, rifiutato prima di partire, tipo). Un collaudo partito resta nello sviluppo con la
    sua traccia di rete (08/10: per l'agente, mai alla voce)."""
    from ..estensioni.servizio import CHIAVE_TRACCIA
    out = est.prova_candidata(ctx, sv.estensione, passati)
    traccia = out.pop(CHIAVE_TRACCIA, None) if isinstance(out, dict) else None
    ris = (out or {}).get("risultati") if isinstance(out, dict) else None
    if isinstance(out, dict) and ris is None and not out.get("errore"):
        return out, False, True, ""
    esito = (ris.get("da_dire") if isinstance(ris, dict) and ris.get("da_dire")
             else json.dumps(ris, ensure_ascii=False) if ris is not None
             else str((out or {}).get("errore") or (out or {}).get("conferma") or ""))
    fallito = _fallito(out, ris)
    tipo = tipo_collaudo(out, ris, passati)
    svs.collaudo(sv, detti, not fallito, esito, rete=traccia, argomenti=passati, tipo=tipo)
    return out, fallito, False, tipo


def _detto_estensione(out) -> str:
    """Le parole dell'estensione da dire tra virgolette: il suo da_dire o il suo errore; per un
    collaudo fermato, l'errore dell'esecuzione (senza «l'estensione «X» non è riuscita:»)."""
    from ..sviluppo import testo_detto
    if not isinstance(out, dict):
        return ""
    ris = out.get("risultati")
    if isinstance(ris, dict):
        for k in ("da_dire", "errore", "error", "messaggio", "message"):
            if isinstance(ris.get(k), str) and ris[k].strip():
                return testo_detto(ris[k])
        return ""
    if isinstance(ris, str):
        return testo_detto(ris)
    err = str(out.get("errore") or "")
    err = re.sub(r"^l'estensione «[^»]*» non è riuscita:\s*", "", err)
    return testo_detto(err, 120, 1)


def frase_collaudo(cosa: str, tipo: str, detto: str, n=None) -> str:
    """La frase di un collaudo, con l'esito vero (12/10): le parole dell'estensione, mai una causa
    inventata. `cosa`: «con «Bergamo»» o «senza dati»."""
    ver = f"la versione {n}" if n else "la versione in prova"
    if tipo == "errore":
        return (f"La prova {cosa} si è fermata con un errore"
                + (f": {detto}." if detto else ".") + " I dettagli sono sulla scheda.")
    if not detto:
        return ""
    if tipo == "vuoto":
        return (f"La prova {cosa} è girata senza trovare niente: {ver} risponde «{detto}». Se "
                "non è la risposta giusta, dimmelo e la faccio correggere.")
    if tipo == "errore_dichiarato":
        return (f"La prova {cosa} è girata e {ver} risponde con un suo errore: «{detto}». Se "
                "con questo dato non è giusto, dimmelo e la faccio correggere.")
    return f"La prova {cosa}: {ver} risponde «{detto}»."


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
    fatti, fermati, frasi = [], [], []
    primo_out = None
    tutte = True                             # ogni prova ha una frase con l'esito vero
    for detto, args in valori:
        out, fallito, prima, tipo = _collauda_estensione(ctx, svs, sv, est, args, detto)
        if prima:
            if not fatti:
                return out                   # il primo non è partito: nessuno parte
            nota = str((out or {}).get("conferma") or (out or {}).get("fatto") or "non partito")
            fatti.append({"provato": detto, "partito": False, "nota": nota})
            tutte = False
            continue
        primo_out = primo_out or out
        voce = {"provato": detto, "argomenti_passati": args, "riuscito": not fallito,
                "esito": tipo}
        if isinstance(out, dict) and out.get("risultati") is not None:
            voce["risultati"] = out["risultati"]
        else:
            voce["errore"] = "si è fermata con un errore: i dettagli sono sulla scheda"
        if tipo == "errore":
            fermati.append(detto)
            note_rule(ctx, "sviluppo_collaudo_fallito")
        elif fallito:
            note_rule(ctx, "sviluppo_collaudo_errore_dichiarato")
        if tipo == "vuoto":
            note_rule(ctx, "sviluppo_collaudo_vuoto")
        parole = _detto_estensione(out)
        if tipo == "errore":
            frasi.append(f"Con «{detto}» si è fermata con un errore"
                         + (f": {parole}." if parole else "."))
        elif parole:
            frasi.append(f"Con «{detto}» risponde «{parole}».")
        else:
            tutte = False
        fatti.append(voce)
    note_rule(ctx, "sviluppo_collauda")
    _schermo(ctx, sv)
    n = est.archivio.candidata(sv.estensione)
    res = {"ok": True, "estensione": (primo_out or {}).get("estensione") or sv.titolo,
           "collaudi": fatti,
           "collaudo": (f"{len(fatti)} prove della versione {n}, NON ancora approvata né attiva, "
                        "una per valore detto: di' in breve il risultato di OGNUNA, con le "
                        "parole dei risultati, mai una causa che non dicono")}
    if isinstance(primo_out, dict) and primo_out.get("avviso"):
        res["avviso"] = primo_out["avviso"]
    domanda = ""
    if fermati:
        cosa = ", ".join(f"«{x}»" for x in fermati)
        domanda = "Lo faccio correggere?"
        res["cosa_fare"] = (f"per {cosa} di' che la prova si è fermata con un errore (i dettagli "
                            "sono sulla scheda) e chiedi «Lo faccio correggere?»")
        res["in_sospeso"] = {"domanda": domanda, "tool": "sviluppo_correggi",
                             "cosa": f"far correggere «{sv.titolo}» all'agente",
                             "argomenti": {"problema": f"il collaudo con {cosa} si ferma con "
                                                       "un errore"}}
    if tutte and frasi:
        # L'esito vero di ogni prova detto dal codice (12/10): le parole dell'estensione, non
        # un riassunto del modello della voce («errore di rete» per un «non trovato»)
        note_rule(ctx, "sviluppo_collaudo_detto")
        frase = (f"Versione {n} in prova. " if n else "") + " ".join(frasi) + (
            f" {domanda}" if domanda else "")
        res["conferma"] = res["risposta_finale"] = frase.strip()
    return res


ANTEPRIMA = "in prova sullo schermo"


def _collauda_gioco(ctx, svs, sv, est) -> dict:
    """Il collaudo di un gioco è vederlo (11/10, DGX delle 16:25–16:26: «Con cosa provo?» →
    «è un gioco, dovrei vederlo» → «Fammelo vedere e fallo girare» → «Un gioco si prova sullo
    schermo dopo l'approvazione: qui non lo eseguo», e Dario ha saltato il collaudo e approvato
    senza averlo visto). La versione candidata si apre in prova sullo schermo da cui si parla
    (Estensioni.prova_gioco → Giochi.avvia_prova, scheda con `"prova": true`): niente dati da
    passare, il giudizio è della persona. Resta nello sviluppo come un collaudo «anteprima»: se
    poi dice cosa non va, sviluppo_correggi lo prende come caso (giudizio)."""
    out = est.prova_gioco(ctx, sv.estensione)
    if not isinstance(out, dict) or out.get("ok") is False:
        return out
    frase = str(out.get("risposta_finale") or out.get("conferma") or "").strip()
    svs.collaudo(sv, ANTEPRIMA, True, frase or "aperto in prova sullo schermo",
                 anteprima=True)
    note_rule(ctx, "sviluppo_collauda")
    note_rule(ctx, "sviluppo_collaudo_gioco")
    _schermo(ctx, sv)
    domanda = "Quando l'hai provato, dimmi se va bene o cosa cambiare."
    frase = f"{frase} {domanda}".strip()
    return {**out, "conferma": frase, "risposta_finale": frase,
            "collaudo": (f"«{sv.titolo}» è aperto IN PROVA sullo schermo: NON è approvato né "
                         "attivo, e non lo è finché la persona non dice di attivarlo"),
            "cosa_fare": ("se dice che va bene o di attivarlo, sviluppo_passo con azione avanti "
                          "(la revisione); se dice cosa cambiare, sviluppo_correggi con "
                          "problema = la modifica come detta")}


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
        if est is None:
            return _no(ctx, "Qui le estensioni non ci sono.")
        if not sv.estensione:
            return _no(ctx, f"Non c'è ancora una versione da provare: siamo {_alla(sv)}.")
        n = est.archivio.candidata(sv.estensione)
        m = est.archivio.manifesto(sv.estensione, n) if n else None
        if m is None:
            return _no(ctx, "Non c'è una versione nuova da provare.")
        if m.get("scheda"):
            return _collauda_gioco(ctx, svs, sv, est)
        passati = _argomenti(m, argomenti if argomenti is not None else dati)
        if argomenti is None and len(passati) > 1:
            note_rule(ctx, "collaudo_input_dal_testo")
        valori = piu_valori(m, argomenti, dati, passati)
        if valori:
            return _piu_collaudi(ctx, svs, sv, est, valori)
        out, fallito, prima, tipo = _collauda_estensione(ctx, svs, sv, est, passati, detti)
        if prima:
            # Un rifiuto prima dell'esecuzione (file cambiati, contenitore spento, un gioco)
            # non è un collaudo: si dice e basta
            return out
    else:
        from . import agenti as ta
        lav_id = sv.lavoro if svs._lavoro(sv.lavoro) is not None else ""
        out = ta._lavori_esegui(ctx, lavoro=lav_id, dati=dati)
        fallito = not bool((out or {}).get("ok"))
        tipo = "errore" if fallito else "risposta"
        svs.collaudo(sv, detti, not fallito, str((out or {}).get("conferma") or ""),
                     argomenti=passati, tipo=tipo)
    note_rule(ctx, "sviluppo_collauda")
    _schermo(ctx, sv)
    # Il caso detto con i valori passati davvero (12/10, prova col modello: dati = «prova con
    # Bergamo» diventava «La prova con «prova con Bergamo»»), come sonde.detto
    valori = [str(v) for v in (passati or {}).values() if str(v).strip()]
    caso = ", ".join(valori)[:80] if valori else str(detti or "").strip()
    cosa = f"con «{caso}»" if caso else "senza dati"
    n = None
    if sv.tipo == "estensione":
        n = est.archivio.candidata(sv.estensione) or sv.versione
    if tipo == "errore":
        # Un collaudo che si è fermato diventa un caso per l'agente (versione 2): la frase la
        # dice il codice, dal 12/10 con la causa che dice l'esecuzione (M1: prima solo «si è
        # fermata con un errore»), e il «sì» va a sviluppo_correggi
        note_rule(ctx, "sviluppo_collaudo_fallito")
        domanda = "Lo faccio correggere?"
        if sv.tipo == "estensione":
            causa = _detto_estensione(out)
        else:
            from ..sviluppo import testo_detto
            causa = testo_detto((out or {}).get("conferma") or (out or {}).get("errore"), 140)
        frase = f"{frase_collaudo(cosa, 'errore', causa, n)} {domanda}"
        return _final(frase, ok=False, fatto="collaudo NON riuscito",
                      in_sospeso={"domanda": domanda, "tool": "sviluppo_correggi",
                                  "cosa": f"far correggere «{sv.titolo}» all'agente",
                                  "argomenti": {"problema": f"il collaudo {cosa} si ferma con "
                                                            "un errore"
                                                            + (f": {causa}" if causa else "")}})
    if isinstance(out, dict) and passati is not None:
        # Gli argomenti veri dell'esecuzione (08/10): il modello vede se il problema è nel
        # passaggio («citta = "Guanzate, 5 giorni"») e non nel codice
        out = {**out, "argomenti_passati": passati}
    if sv.tipo == "estensione" and isinstance(out, dict):
        # L'esito vero detto dal codice (12/10, caso vero dell'08/10: l'esito era «Non ho
        # trovato il meteo per…» e la voce ha detto quattro volte «errore di rete»). Un «non
        # trovato» o un errore che l'estensione restituisce apposta non è un difetto: niente
        # «Lo faccio correggere?» (M1); lo dice la persona, se è sbagliato
        if tipo == "vuoto":
            note_rule(ctx, "sviluppo_collaudo_vuoto")
        elif tipo == "errore_dichiarato":
            note_rule(ctx, "sviluppo_collaudo_errore_dichiarato")
        frase = frase_collaudo(cosa, tipo, _detto_estensione(out), n)
        if frase:
            note_rule(ctx, "sviluppo_collaudo_detto")
            out = {**out, "conferma": frase, "risposta_finale": frase, "esito": tipo}
        else:
            out = {**out, "esito": tipo,
                   "cosa_fare": "di' in breve il risultato con le parole dei risultati; mai una "
                                "causa (la rete, i nomi…) che i risultati non dicono"}
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
    if _chiudi_tutti_detto(ctx):
        # «Chiudi tutti gli sviluppi» detto per intero e preso per una domanda (10/10, DGX
        # delle 11:48: «Non c'è nessuno sviluppo aperto: di quale codice parli?», falso): è la
        # chiusura, con la sua domanda (forma chiusa, effetto: una domanda; principio 10)
        note_rule(ctx, "sviluppo_chiudi_tutti_forma")
        return _sviluppo(ctx, azione="chiudi", quale="tutti")
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
    if r is not None and _risposta_ripetuta(sv, domanda, r):
        # La stessa risposta di una domanda diversa (12/10 sera, 11:11:59 e 12:06:03: «Il
        # lavoro si è fermato perché il sistema ha rilevato che…» a «scegliere la prima porta
        # non porta a nulla» e a «perché è bloccato?»): una volta di nuovo, senza le domande
        # di prima nel contesto
        note_rule(ctx, "sviluppo_chiedi_ripetuta")
        r2, _ = chiedi_agente(svc, domanda, svs.testo_per_agente(sv, chiesti=False), tempo)
        if r2 is not None:
            r = r2
    if r is None:
        note_rule(ctx, "sviluppo_chiedi_guasto")
        getattr(svc, "log", print)(f"[SVILUPPO] {sv.id}: domanda all'agente: {esito}")
        arresto = svs.motivo_arresto(sv, voce=True)
        return _final((arresto + " " if arresto else "")
                      + "Adesso chi l'ha scritta non mi risponde"
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
    arresto = svs.motivo_arresto(sv, voce=True)
    if arresto:
        # Il motivo dell'arresto deciso da Calliope (11/10, DGX delle 15:52: «perché è rimasto
        # bloccato?» → «un errore nel codice delle porte», e il ragionamento ripetuto non
        # arrivava alla voce). «motivo» resta fuori dalla busta del dato: lo scrive il codice
        out["motivo"] = arresto
        out["cosa_fare"] = ("se chiede perché il lavoro si è fermato o è bloccato, di' PRIMA "
                            "il «motivo» (l'arresto l'hai deciso tu, non è la risposta "
                            "dell'agente), poi in breve la risposta di chi l'ha scritto; "
                            + out["cosa_fare"])
        note_rule(ctx, "sviluppo_chiedi_arresto")
    if r.get("serve_correzione"):
        out["in_sospeso"] = {"domanda": "Lo faccio correggere?", "tool": "sviluppo_correggi",
                             "cosa": f"far correggere «{sv.titolo}»",
                             "argomenti": {"problema": str(r.get("cosa_correggere") or domanda)
                                           [:300]}}
    # La risposta detta dal codice (12/10, caso vero del 09/10 20:42: l'agente aveva scritto che
    # la ricerca dei nomi simili non c'era, con correzione = true; la voce ha letto solo il
    # messaggio e chiesto «Ti va bene o lo faccio correggere?», e la persona ha detto «mi va
    # bene»). Se va corretto lo si dice PER PRIMO, con le parole dell'agente; poi la risposta
    from ..sviluppo import testo_detto
    voce = testo_detto(r.get("voce"), 260, 2)
    parti = [arresto] if arresto else []
    if r.get("serve_correzione"):
        note_rule(ctx, "sviluppo_chiedi_correzione_detta")
        manca = testo_detto(r.get("cosa_correggere"), 140, 1)
        parti.append("Chi l'ha scritta dice che va corretto" + (f": {manca}." if manca else "."))
        if voce:
            parti.append(f"La sua risposta: {voce}.")
        parti.append("Lo faccio correggere?")
    elif voce:
        parti.append(f"Chi l'ha scritta risponde: {voce}.")
    else:
        parti.append("La risposta di chi l'ha scritta è sulla scheda dello sviluppo.")
    frase = " ".join(p for p in parti if p)
    out["conferma"] = out["risposta_finale"] = frase
    return out


MAX_CHIESTI_RIPETUTA = 5

# Le correzioni di un gioco che non correggono (12/10 sera, 11:37 e 11:42: «non si vede nessun
# mostro, nessun punto, vince V senza motivo», due correzioni finite «fatto» con i test verdi e
# il gioco uguale; la seconda con lo stesso identico problema della prima). L'agente correggeva
# logica.js e i suoi test (le regole), mentre ciò che la persona vede passa da gioco.js; e non
# sapeva che la versione provata era già la correzione di prima. Dal 14/10 il disegno è della
# macchina a stati di Calliope (niente gioco.js): ciò che si vede viene da vista ed esito di
# logica.js e dalla pagina scelta nel manifesto
VINCOLO_CORREZIONE_GIOCO = (
    " È un GIOCO e il problema l'ha visto la persona sullo schermo: la causa può essere in ciò "
    "che si mostra (GIOCO.vista, l'«esito» delle mosse, la pagina e le etichette nel "
    "manifesto) o in quali comandi valgono (GIOCO.attivi), non solo nelle regole. Segui il tocco "
    "della persona fino a ciò che appare: che il pulsante chiami la mossa giusta e che il "
    "risultato (cosa c'è dietro la porta, i punti, chi vince e perché) venga mostrato. Il test "
    "che riproduce il problema va in gioco.test.js e guida il gioco vero: const g = await "
    "apriGioco({ seme: 1 }); await g.tocca(\"2 giocatori\"); await g.tocca(\"testo del "
    "pulsante\"); poi controlla con g.testo() e g.stato() proprio quello che la persona dice "
    "che non va (il mostro, i punti, il vincitore), e con g.palco() se dice che qualcosa non "
    "si vede o esce dallo schermo. I test di logica.test.js non vedono la pagina.")


# La correzione parte da un test che fallisce (12/10 sera, parte 1 del flusso a fasi; ricerca
# 2026-10-12-flusso-agente-fasi § 5.1, passo 1). Prima «trova la causa, correggi, aggiungi un
# test con ogni caso che non andava»: alle 11:37 e alle 11:42 il test non c'era e i test verdi
# non riguardavano il difetto. Il codice lo controlla alla consegna (agenti/riproduzione.py)
VINCOLO_RIPRODUCI = (
    " PRIMA di toccare il codice scrivi un test che riproduce il problema segnalato ed "
    "eseguilo con esegui_test: deve FALLIRE sul codice di adesso (se passa, non riproduce il "
    "problema: cambialo). Poi trova la causa e correggi il codice finché quel test e gli altri "
    "passano, e consegna. Alla consegna Calliope riesegue i tuoi test nuovi sulla versione di "
    "prima: se lì passano, o se il codice non è cambiato, la correzione non vale.")


def _detto_adesso(ctx, problema: str) -> str:
    """Le parole della persona in questo turno, se dicono più del problema passato dal modello
    (12/10 sera: la seconda correzione ha ricevuto lo stesso problema della prima, e «è sempre
    esattamente uguale a prima» si perdeva)."""
    from ..estensioni.servizio import _norm_testo
    detto = re.sub(r"\s+", " ", str(getattr(ctx, "user_text", "") or "")).strip()
    if len(detto) < 25 or _norm_testo(detto) in _norm_testo(problema):
        return ""
    return f" Le parole della persona adesso: «{detto[:500]}»."


def _correzione_di_prima(svs, sv) -> str:
    """La versione provata era già una correzione: lo si dice all'agente (12/10 sera)."""
    from ..sviluppo import cambiamento_chiesto
    c = cambiamento_chiesto(sv)
    if not c.startswith("correggere: "):
        return ""
    return (f" ATTENZIONE: la versione che la persona ha appena provato era GIÀ una correzione "
            f"(per: «{c.removeprefix('correggere: ')[:300]}»), e la persona dice che non va "
            "ancora: la correzione di prima NON ha funzionato, anche se i suoi test passavano. "
            "Non rifare la stessa modifica: trova perché ciò che la persona vede non è "
            "cambiato.")


def _risposta_ripetuta(sv, domanda: str, r: dict) -> bool:
    """La risposta dell'agente è (quasi) uguale a quella di una domanda diversa di prima."""
    import difflib
    from ..estensioni.servizio import _norm_testo
    voce = _norm_testo(str(r.get("voce") or ""))
    d = _norm_testo(domanda)
    if len(voce) < 20:
        return False
    for q in sv.chiesti[-MAX_CHIESTI_RIPETUTA:]:
        if _norm_testo(str(q.get("domanda") or "")) == d:
            continue
        prima = _norm_testo(str(q.get("voce") or ""))
        if prima and difflib.SequenceMatcher(None, voce, prima).ratio() >= 0.9:
            return True
    return False


# ─────────────────────────── sviluppo_correggi ───────────────────────────

def _sviluppo_correggi(ctx: ToolContext, problema: str = "", **_altro) -> dict:
    """La correzione come passo a sé (08/10, versione 2; DGX, 11:15: «fai revisionare il codice
    all'agente» tornava all'analisi e rileggeva la specifica). La specifica resta: l'agente
    riparte dai suoi file, dai collaudi che non vanno e dalla risposta di sviluppo_chiedi; poi
    di nuovo collaudo. A una tappa è «cambia e continua»: il giro nuovo con la nota.

    Dal 12/10 (la specifica viva, A3): se la persona chiede un comportamento diverso («metti 7
    porte», «i mostri danno punti»), è la stessa operazione sui requisiti di «cambia»: la
    richiesta si aggiorna, e il lavoro nuovo si propone dicendo cosa è cambiato. «Non funziona,
    correggi» senza dire cosa, e senza collaudi falliti da cui partire, chiede «Cosa non va?»
    prima di far ripartire l'agente."""
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
    # Un comportamento diverso, un difetto o niente di preciso (12/10, la specifica viva, A3):
    # lo dice il modello dell'agente, con la stessa operazione sui requisiti di «cambia». Il
    # «sì» a «Lo faccio correggere?» (un collaudo fallito, una diagnosi) è una correzione e
    # basta; la risposta a «Cosa non va?» si guarda di nuovo
    risposta = _cosa_appena_chiesta(ctx, consuma=True)
    si_alla_domanda = (getattr(ctx, "tool_in_sospeso", None) == "sviluppo_correggi"
                       and not risposta)
    from ..sviluppo import senza_contenuto
    if problema and not si_alla_domanda and not risposta and senza_contenuto(
            problema, sv, correzione=True):
        # Un problema che non descrive niente (12/10 sera, 08:46: «Calliope va modificato
        # Calliope.», il primo pezzo di una frase tagliata al nome → problema «va modificato
        # Calliope», e la correzione partiva senza una domanda). Con un collaudo fallito di
        # questa versione l'agente ha da dove partire: il problema detto non aggiunge niente
        note_rule(ctx, "sviluppo_correggi_vago")
        falliti_ora = [c for c in sv.collaudi[-5:]
                       if not c.get("ok") and not c.get("anteprima")
                       and c.get("versione") in (None, sv.versione)]
        if not falliti_ora:
            return _chiedi_cosa(ctx, sv, "Cosa non va? Dimmi cosa hai visto o cosa deve fare "
                                         "di diverso, così lo dico a chi l'ha scritto.",
                                "correggi")
        problema = ""
    if not problema and not si_alla_domanda and not risposta and _va_chiesto(ctx, svs, sv):
        return _chiedi_cosa(ctx, sv, "Cosa non va? Dimmi cosa hai visto o cosa deve fare di "
                                     "diverso, così lo dico a chi l'ha scritto.", "correggi")
    if problema and not si_alla_domanda:
        prima = svs.istantanea(sv)
        m = _modifica(ctx, svs, sv, problema, "correggi", gia_chiesto=risposta)
        if m["esito"] == "risposta":
            return m["out"]
        if m["esito"] == "cambi":
            note_rule(ctx, "sviluppo_correggi_cambia")
            return _proponi_modifica(ctx, svs, sv, prof, problema, m["cambi"], prima)
    if sv.fase == "sviluppo" and not (sv.estensione if sv.tipo == "estensione"
                                      else sv.cartella):
        # Uno sviluppo fermo prima della prima consegna (11/10, DGX delle 15:53: il lavoro del
        # gioco di Halloween fermato per il ragionamento ripetuto, «Lo faccio correggere?», «Sì»
        # → sviluppo_correggi → «Qui le estensioni non ci sono.», due volte: non c'era una
        # versione da cui partire). Il modello ha scelto «correggi» e la persona ha detto sì:
        # la forma corretta di quella scelta è rifare il lavoro con il problema detto e i file
        # già scritti (principio 10, regola `sviluppo_correggi_rifai`). Effetto: lo stesso di
        # «rifallo», che la persona aveva davanti («lo rifaccio così com'è, o vuoi cambiare
        # qualcosa?»), con in più la nota
        if not problema:
            note_rule(ctx, "sviluppo_correggi_rifai")
        return _rifai(ctx, svs, sv, prof, problema)
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
    diagnosi = svs.diagnosi(sv)        # solo della versione provata (12/10 sera)
    # La traccia di rete dei collaudi (08/10): le richieste vere con l'esito, la causa che nel
    # giro della DGX l'agente non vedeva (nella sandbox non ha rete)
    rete = svs.testo_traccia(sv)
    # Cosa deve fare è la specifica del compito, intera (12/10: prima una copia tagliata a 500
    # caratteri e «la specifica NON cambia» anche quando la persona chiedeva altro, A3)
    vincoli = (f"È una CORREZIONE dello sviluppo «{sv.titolo}»: cosa deve fare resta quello del "
               "compito. I file della versione che la "
               "persona ha provato sono già nella cartella: riparti da quelli, non riscrivere da "
               "zero."
               + (f" Collaudi che non vanno (dati → esito): {casi}." if casi else "")
               + (f" Diagnosi di chi l'ha scritto, alla domanda «{diagnosi['domanda']}»: "
                  f"{diagnosi.get('dettagli') or diagnosi.get('voce')}"
                  + (f" Da correggere: {diagnosi['cosa_correggere']}."
                     if diagnosi.get("cosa_correggere") else "") if diagnosi else "")
               + (f" Problema detto dalla persona: «{problema}»." if problema else "")
               + _detto_adesso(ctx, problema)
               + _correzione_di_prima(svs, sv)
               + (VINCOLO_CORREZIONE_GIOCO if svs.e_gioco(sv) else "")
               + (f" {rete}" if rete else "")
               + VINCOLO_RIPRODUCI)
    lav = _lavoro_dello_sviluppo(ctx, svs, sv, prof, sv.specifica or sv.richiesta, vincoli)
    if isinstance(lav, dict):
        return lav
    _con_esempi(svs, sv, lav)
    svs._metti_vincoli(sv, lav)
    lav.correzione = True
    lav.problema_correzione = problema
    with svs._lock:
        sv.correzioni += 1
    svs.passa(sv, "sviluppo", "correzione" + (f": {problema[:80]}" if problema else ""))
    note_rule(ctx, "sviluppo_correzione")
    from . import agenti as ta
    out = ta._avvia(ctx, svc, lav)
    caso = falliti[-1].get("dati") if falliti else ""
    # Un gioco si riprova guardandolo (12/10 sera: «rifacciamo la prova con «in prova sullo
    # schermo»», il dato del collaudo di un gioco detto come un dato della prova)
    if svs.e_gioco(sv) or (falliti and falliti[-1].get("anteprima")):
        caso_detto = " sullo schermo"
    else:
        caso_detto = f" con «{caso}»" if caso else ""
    frase = frasi_pronte.scegli("sviluppo.correzione", caso=caso_detto)   # catalogo (12/10)
    out["conferma"] = out["risposta_finale"] = frase
    _schermo(ctx, sv)
    return out


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
             "proposta": {"type": "string"}, "gioco": {"type": "boolean"},
             "tappe": {"type": "boolean"}}
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
            "funzionare per ogni città», «correggila»: modifica = il suo nome). Un gioco o un "
            "minigioco, anche con grafica, animazioni e punti, è un'estensione con gioco=true: "
            "si gioca sugli schermi di Calliope (tipo programma solo se chiede proprio un "
            "programma per il desktop o il terminale). "
            "tipo programma: uno script o un programma da usare adesso, in "
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
            "cambiamo?»), dopo il sì richiamalo con proposta = l'id proposto (es. «L3»); "
            "alla proposta a tappe, se vuole tutto insieme, anche tappe = false."),
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
                         "«riprova così com'è»: riparte subito con la stessa specifica, dai "
                         "file già scritti); indietro (alla modifica proposta, «lascia com'era»: "
                         "torna dov'eravamo, la modifica si scarta); ferma "
                         "(«ferma/stoppa/blocca lo sviluppo», «fermalo»: il lavoro dell'agente "
                         "si ferma subito); sospendi (una pausa, «mettiamo in pausa»: un lavoro "
                         "dell'agente in corso finisce); riprendi («riprendiamo lo sviluppo del meteo», anche "
                         "«riapri il programma delle vocali» già chiuso: quale "
                         "= le parole del titolo); chiudi (chiede conferma; «chiudi tutti gli "
                         "sviluppi»: quale = \"tutti\", e ferma anche il lavoro dell'agente); "
                         "promuovi (un "
                         "programma diventa un'estensione); completa (dopo la consegna, "
                         "l'agente fa quello che manca rispetto alla richiesta, o la tappa dopo: "
                         "«continua a farli»). L'azione va nell'argomento azione: "
                         "non ci sono tool sviluppo_ferma, sviluppo_chiudi o sviluppo_stato. "
                         "Cosa fare in ogni fase è nei dati del turno."),
            parameters={"type": "object", "properties": {
                "azione": {"type": "string", "enum": AZIONI},
                "quale": {"type": "string"}, "cambia": {"type": "string"}},
                "required": ["azione"]},
            func=_sviluppo, risk="azione", levels=FAMILY),
        ToolSpec(
            name="sviluppo_collauda",
            description=("Il collaudo nella modalità sviluppo: prova la versione nuova "
                         "dell'estensione (non ancora attiva) o il programma, con i dati detti "
                         "(«prova con Bergamo», «provalo con 3 e 5»); un gioco si apre in prova "
                         "sullo schermo, senza dati («fammelo vedere»). Per un'estensione, più "
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
                         "usa?»). Risponde senza cambiare niente. domanda: come detta. Solo "
                         "per DOMANDE sul codice: se la persona dice che qualcosa non va («non "
                         "porta a nulla», «non si vede il mostro») è sviluppo_correggi; per "
                         "chiudere, fermare o sospendere uno sviluppo («chiudi tutti gli "
                         "sviluppi») c'è sviluppo_passo con l'azione."),
            parameters={"type": "object", "properties": {"domanda": {"type": "string"}},
                        "required": ["domanda"]},
            func=_sviluppo_chiedi, risk="lettura", levels=FAMILY, non_fidato=True,
            fonte="agente", announce=("Lo chiedo a chi l'ha scritta.",)),
        ToolSpec(
            name="sviluppo_correggi",
            description=("Solo con uno sviluppo aperto (nei dati del turno): fa correggere il "
                         "codice dello sviluppo da chi l'ha scritto («correggilo», «fallo "
                         "sistemare», «sì» a «Lo faccio correggere?»; a una tappa, «cambia e "
                         "continua»). problema: cosa non va o cosa deve fare di diverso, come "
                         "detto (se chiede un comportamento diverso, la richiesta si aggiorna da "
                         "sé). Per correggere uno script o un file fuori da uno sviluppo, "
                         "sviluppo_apri tipo programma."),
            parameters={"type": "object", "properties": {"problema": {"type": "string"}},
                        "required": []},
            func=_sviluppo_correggi, risk="azione", levels=FAMILY),
    ]
