"""
I tool nativi di Calliope: identità, voce, ora.

Vedi docs/architettura-tool.md. Ogni tool è una funzione Python che riceve il
ToolContext e restituisce un dict serializzabile; gli errori tornano come
{"ok": False, "errore": ...}, mai come eccezioni verso il modello.
"""

import ast
import dataclasses
import datetime
import json
import math
import operator
import re
import time
from pathlib import Path
from types import SimpleNamespace

from ..config import VOICE_MAP, nome_tono
from ..liste import say_list, split_items
from ..memory import HOUSE, unsaid_value
from ..sicurezza import instruction_fact
from ..tempi import (parse_day_range, parse_duration, parse_shift, parse_when, say_duration,
                     say_when, sposta)

from .registry import ToolRegistry
from ..conferme import (admin_confermato, chiedi_conferma, e_admin, proposta_valida,
                        secondi_validi, serve_conferma)
from .. import minori
from .spec import ToolSpec, ToolContext, note_rule
from ..agenda import is_cancel_all
from .. import tempi
from ..schermi import schede
from ..testi import ADMIN, ALL, FAMILY, MESI, NIENTE


def _hub(ctx):
    """Il registro degli schermi (calliope/schermi/), o None: senza, le schede non si
    costruiscono nemmeno. Una scheda va nel risultato come «scheda» (o «schede»): Brain la
    toglie prima del modello e la manda agli schermi appena il tool finisce."""
    return getattr(ctx, "schermi", None)


def _con_scheda(out: dict, ctx, build) -> dict:
    """Aggiunge la scheda al risultato, se ci sono gli schermi. Un errore nella scheda non
    cambia mai il risultato del tool."""
    if _hub(ctx) is None or not isinstance(out, dict) or out.get("ok") is False:
        return out
    try:
        card = build()
        if card:
            out["scheda"] = card
    except Exception as e:  # noqa: BLE001
        print(f"   [SCHERMI] scheda non costruita: {type(e).__name__}: {e}", flush=True)
    return out


def _clean_name(raw: str) -> str:
    """Normalizza un nome detto a voce: togli punteggiatura finale, iniziali maiuscole."""
    return (raw or "").strip().rstrip(".,!?;:").strip().title()


# ─────────────────────────────── IDENTITÀ ───────────────────────────────

def _chi_parla(ctx: ToolContext) -> dict:
    """Chi sta parlando adesso: nome e se la voce è riconosciuta.

    Il livello di permesso non si restituisce: al modello non serve (i tool sono già
    filtrati nel codice) e, pur con la descrizione che lo diceva riservato, lo ripeteva
    («hai un livello di permesso amministratore», test del 24/09).
    """
    name = ctx.speaker_ctx.current_speaker
    out = {"nome": name, "riconosciuto": name is not None}
    # Età e compleanno di chi parla (07/10): i suoi dati, dal profilo
    prof = _profilo_di(ctx, name) if name else None
    if prof is not None:
        out.update(_dati_nascita(prof))
    return out


def _elenca_utenti(ctx: ToolContext) -> dict:
    """Le persone della casa registrate (speakers.json), non la rubrica dell'ufficio.

    06/10 sera (DGX): il campo «voce» era la voce di Calliope scelta per quella persona, e
    con «voce: null» il modello diceva che un ragazzo registrato «non ha ancora una sua voce
    associata», mentre l'impronta c'era. Ora `impronta_voce` (sì/no) dice se Calliope lo
    riconosce dalla voce; età e compleanno solo a chi può saperli (_vede_nascita)."""
    chi = _profilo_di(ctx, getattr(ctx.speaker_ctx, "current_speaker", None))
    utenti = []
    for nome in ctx.speakers.known_speakers():
        prof = ctx.speakers.get(nome)
        u = {"nome": nome,
             "impronta_voce": "sì" if getattr(prof, "voiceprint", None) is not None else "no",
             "amministra": bool(getattr(prof, "admin", False))}
        if minori.e_minore(prof):
            u["minorenne"] = True
        if getattr(prof, "gender", None):
            u["genere"] = prof.gender
        if getattr(prof, "preferred_voice", None):
            u["voce_di_calliope"] = Path(str(prof.preferred_voice)).stem
        if _vede_nascita(chi, prof):
            u.update(_dati_nascita(prof))
        utenti.append(u)
    return {"utenti": utenti, "numero": len(utenti)}


# ── Età e compleanni dai profili (07/10) ──
# 06/10 sera, DGX: un ragazzo registrato con la data di nascita chiede «Quanti anni ho?» → il
# modello chiama data_calcola(cosa="eta", data=<oggi>) e dice «oggi è il tuo compleanno»; poi
# il genitore chiede il compleanno e il modello cerca nelle conversazioni e conta i giorni a
# mente (309 invece di 339). La data di nascita è nel profilo (speakers.json v2, `nascita`):
# la usa il programma. Chi può saperla: la persona stessa, chi amministra, i suoi tutori; gli
# ospiti no (non hanno un profilo).
_IO = {"io", "me", "mio", "mia", "chi parla", "chi sta parlando", "se stesso", "se stessa",
       "sé stesso", "sé stessa", "me stesso", "me stessa", "il mio", "la mia"}


def _profilo_di(ctx, nome):
    speakers = getattr(ctx, "speakers", None)
    if not nome or speakers is None:
        return None
    try:
        return speakers.get(nome)
    except Exception:  # noqa: BLE001
        return None


def _nascita_di(prof) -> "datetime.date | None":
    n = getattr(prof, "nascita", None)
    return minori.leggi_data(n) if n else None


def _dati_nascita(prof, oggi: "datetime.date | None" = None) -> dict:
    """Data di nascita, anni compiuti, prossimo compleanno e giorni che mancano; {} senza."""
    d = _nascita_di(prof)
    if d is None:
        return {}
    oggi = oggi or datetime.date.today()
    prossimo = tempi.prossima(tempi.stesso_giorno(d, oggi.year), oggi)
    return {"nascita": tempi.say_date(d), "anni": tempi.anni_compiuti(d, oggi),
            "prossimo_compleanno": tempi.say_date(prossimo),
            "giorni_al_compleanno": (prossimo - oggi).days}


def _vede_nascita(chi, altro) -> bool:
    """`chi` (il profilo di chi parla, None = ospite) può sapere età e compleanno di `altro`?
    Sé stesso sì; chi amministra e i tutori (minori.e_tutore) sì; gli altri no."""
    if chi is None or altro is None:
        return False
    if chi is altro or getattr(chi, "id", None) == getattr(altro, "id", object()):
        return True
    return bool(getattr(chi, "admin", False)) or minori.e_tutore(chi, altro)


def _persona_registrata(ctx, persona: str):
    """(profilo, nome, è chi parla) per `persona` («io» o un nome), o un dict d'errore."""
    sc = getattr(ctx, "speaker_ctx", None)
    io = getattr(sc, "current_speaker", None)
    p = (persona or "").strip().strip(".,!?").casefold()
    if p in _IO or (io and p == str(io).casefold()):
        if not io:
            return {"ok": False, "errore": "non so chi sta parlando (voce non riconosciuta): "
                                           "chiedi la data di nascita e passala in data"}
        prof = _profilo_di(ctx, io)
        return (prof, io, True) if prof is not None else {
            "ok": False, "errore": "chi parla non ha un profilo: chiedi la data di nascita"}
    speakers = getattr(ctx, "speakers", None)
    nome = None
    if speakers is not None:
        trova = getattr(speakers, "find", None)
        if callable(trova):
            nome = trova(persona)
        else:
            nome = next((n for n in speakers.known_speakers()
                         if n.casefold() == p), None)
    if not nome:
        return {"ok": False, "errore": f"«{persona}» non è una persona registrata in casa: "
                                       f"chiedi la data di nascita e passala in data"}
    return (speakers.get(nome), nome, nome == io)


def _rinomina_interlocutore(ctx: ToolContext, nome: str) -> dict:
    """Rinomina la persona che sta parlando, solo dopo il suo consenso (02/10).

    Il 02/10 alle 21:55 Whisper sulla DGX ha trascritto «Calliope, chiamami Davio, ma vorrei
    sapere chi sono» (si chiedeva chi è) e il modello ha chiamato subito
    rinomina_interlocutore(nome="Davio"): il profilo di chi amministra è diventato «Davio».
    Un nome cambiato resta (speakers.json, ogni saluto, ogni annuncio), quindi come per i
    documenti e le installazioni la prima chiamata **propone** soltanto: chiude con «Vuoi che
    ti chiami Davio d'ora in poi?» e un'azione in sospeso (Brain.set_pending). Il nome
    cambia solo se lo stesso tool, con lo stesso nome e per la stessa persona, arriva nella
    risposta **successiva** (ToolContext.turno): lo richiama il modello se la persona
    acconsente. Nessuna regola sì→rinomina: decide il modello, il codice impedisce solo di
    farlo nello stesso turno della proposta."""
    old = ctx.speaker_ctx.current_speaker
    if not old:
        return {"ok": False, "errore": "non so chi sta parlando"}
    new = _clean_name(nome)
    if not new:
        return {"ok": False, "errore": "nome vuoto"}
    if new == old:
        return {"ok": True, "nome": new, "conferma": f"Ti chiamo già {new}."}
    # Il nome di un'altra persona registrata: rename() sovrascriverebbe il suo profilo
    if any(n != old and n.lower() == new.lower() for n in ctx.speakers.known_speakers()):
        return {"ok": False, "errore": f"«{new}» è il nome di un'altra persona registrata: "
                                       f"non lo cambio"}
    prof = ctx.speakers.get(old)
    chi = getattr(prof, "id", None) or old
    turno = int(getattr(ctx, "turno", 0) or 0)
    offerte = getattr(ctx, "_rinomine", None)
    if offerte is None:
        offerte = {}
        ctx._rinomine = offerte
    off = offerte.get(chi)
    valida = bool(off and off["nome"].lower() == new.lower() and _proposta_ok(ctx, off, turno))
    prima = (getattr(ctx, "risposta_precedente", None) or {}).get("testo", "")
    if not valida and turno >= 1 and domanda_rinomina(prima, new):
        # La domanda l'ha già fatta il modello a parole, senza il tool (04/10, 26B: «Vuoi
        # davvero che ti chiami Davide?» e al «sì» la chiamata trovava solo una proposta
        # nuova). È la stessa proposta, detta nella risposta precedente: vale come quella
        # del tool. Decide ancora il modello se la risposta è un consenso; per chi
        # amministra resta la conferma della voce (serve_conferma)
        off = {"nome": new, "turno": turno - 1, "quando": time.monotonic()}
        note_rule(ctx, "rinomina_domanda_detta")
    if off and off["nome"].lower() == new.lower() and _proposta_ok(ctx, off, turno):
        # Il nome di chi amministra (il caso «Davio» del 02/10) lo conferma la sua voce: un
        # «sì» breve solo in una conversazione sicura, altrimenti la frase di sfida (04/10)
        if getattr(prof, "admin", False):
            sfida = serve_conferma(ctx, "rinomina_interlocutore", {"nome": new},
                                   f"chiamarti {new}")
            if sfida is not None:
                return sfida
        offerte.pop(chi, None)
        if not ctx.speakers.rename(old, new):
            return {"ok": False, "errore": f"utente «{old}» non trovato"}
        ctx.speaker_ctx.current_speaker = new
        if getattr(ctx.speaker_ctx, "voce_sicura", None) == old:
            ctx.speaker_ctx.voce_sicura = new
        return {"ok": True, "nome": new, "fatto": "rinominato",
                "conferma": f"Va bene, d'ora in poi ti chiamo {new}."}
    offerte[chi] = {"nome": new, "turno": turno, "quando": time.monotonic()}
    note_rule(ctx, "rinomina_conferma")
    domanda = f"Vuoi che ti chiami {new} d'ora in poi?"
    return {"ok": True, "fatto": "proposto, il nome NON è ancora cambiato",
            "conferma": domanda, "risposta_finale": domanda,
            "in_sospeso": {"domanda": domanda, "cosa": f"il nome {new} al posto di {old}",
                           "tool": "rinomina_interlocutore", "argomenti": {"nome": new}}}


def domanda_rinomina(testo: str, nome: str) -> bool:
    """La risposta `testo` di Calliope chiede (con una domanda, «?») se chiamare chi parla
    `nome`: «Vuoi che ti chiami Davide?», «Vuoi davvero che d'ora in poi ti chiami Davide?».
    Solo una frase interrogativa con una forma di «chiamare» e il nome intero; «Come ti
    chiami?», «Davide è un bel nome. Altro?» o un altro nome no (prova_testo)."""
    nome = (nome or "").strip()
    if not nome:
        return False
    for frase in re.findall(r"[^.!?]*\?", testo or ""):
        if re.search(r"\bchiam\w*", frase, re.I) and re.search(
                r"(?<![\w'’])" + re.escape(nome) + r"(?!\w)", frase, re.I):
            return True
    return False


def _proposta_ok(ctx, off: dict, turno: int) -> bool:
    """La proposta (rinomina, registrazione di nuovo) vale ancora: nei turni dopo, per
    `azione_in_sospeso_turni` turni ed entro `azione_in_sospeso_s` (04/10, conferme.py)."""
    return (proposta_valida(ctx.cfg, off.get("turno", 0), turno)
            and time.monotonic() - off.get("quando", time.monotonic()) <= secondi_validi(ctx.cfg))


_CHIEDI_NASCITA = ("Quando è nato o nata {nome}? Mi serve la data di nascita per sapere come "
                   "parlarci e cosa può fare; se è maggiorenne, dimmi solo che è maggiorenne.")
_NASCITA_MSG = ("Messaggio di sistema, non della persona: per registrare {nome} hai chiesto la "
                "data di nascita. Se nella frase c'è una data, o se dice che è maggiorenne, "
                "richiama subito registra_utente con nome={nome_json} e nascita (la data come "
                "detta) oppure maggiorenne=true, e tutori se li nomina. Se parla d'altro, "
                "rispondi normalmente.")


def _nuovo_profilo(ctx: ToolContext, n: str, nascita: str, tutori: str, maggiorenne) -> dict:
    """«Aggiungi un familiare» (05/10, decisione di Dario): solo chi amministra, riconosciuto
    dalla voce **e** con la frase di sfida (prova di presenza: la TV o una registrazione non
    aggiungono nessuno). Dati: nome, data di nascita (la fascia d'età si ricalcola da sola,
    calliope/minori.py), tutori (chi amministra quel profilo; di partenza chi lo registra).
    Poi parla la persona nuova, con l'adulto presente."""
    sc = ctx.speaker_ctx
    d = minori.leggi_data(nascita) if str(nascita or "").strip() else None
    adulto = _yes(maggiorenne) and d is None
    if d is None and not adulto:
        note_rule(ctx, "registra_chiede_nascita")
        domanda = _CHIEDI_NASCITA.format(nome=n)
        return {"ok": False, "fatto": "NON è partita la registrazione: manca la data di nascita",
                "conferma": domanda, "risposta_finale": domanda,
                "in_sospeso": {"tool": "registra_utente", "argomenti": {"nome": n},
                               "domanda": domanda,
                               "messaggio": _NASCITA_MSG.format(nome=n, nome_json=json.dumps(n))}}
    chi = _person(ctx)
    ids = []
    for t in re.split(r",|\s+e\s+", str(tutori or "")):
        t = t.strip()
        if not t:
            continue
        trovato = ctx.speakers.find(t) if hasattr(ctx.speakers, "find") else None
        if trovato is None:
            return {"ok": False, "fatto": "NON è partita la registrazione",
                    "errore": f"«{t}» non è tra le persone registrate",
                    "cosa_fare": "chiedi chi sono i tutori tra le persone registrate"}
        ids.append(ctx.speakers.get(trovato).id)
    if not ids and chi is not None:
        ids = [chi.id]
    eta_ = minori.eta(d) if d else None
    minore = minori.fascia_per_eta(eta_) is not None
    args = {"nome": n, **({"nascita": d.isoformat()} if d else {"maggiorenne": True}),
            **({"tutori": str(tutori)} if str(tutori or "").strip() else {})}
    # Voce + frase di sfida: anche se la voce è sicura (decisione del 05/10)
    if not getattr(sc, "sfida_superata", False):
        if getattr(ctx.cfg, "conferma_sfida", True):
            return chiedi_conferma(ctx, "registra_utente", args,
                                   f"registrare {n}" + (" come minorenne" if minore else ""))
        if not admin_confermato(ctx):
            sfida = serve_conferma(ctx, "registra_utente", args, f"registrare {n}")
            if sfida is not None:
                return sfida
            frase = "Una persona nuova la può aggiungere solo chi amministra, con la sua voce."
            return {"ok": False, "fatto": "NON è partita la registrazione", "errore": frase,
                    "risposta_finale": frase}
    meta = {"nascita": d.isoformat(), "tutori": ids} if minore else (
        {"nascita": d.isoformat()} if d else {})
    sc.start_enroll(n, meta=meta)
    note_rule(ctx, "registra_minore" if minore else "registra_nuovo")
    out = {"ok": True, "nome": n, "frasi_necessarie": sc.enroll_needed}
    if minore:
        out.update(minorenne=True, fascia=minori.fascia_per_eta(eta_), eta=eta_,
                   cosa_fare=f"Di' che adesso deve parlare {n}, con un adulto accanto.")
    return out


def _registra_utente(ctx: ToolContext, nome: str, nascita: str = "", tutori: str = "",
                     maggiorenne=None) -> dict:
    """Avvia l'arruolamento vocale di una persona nuova.

    Un nome già registrato (anche scritto diverso, o con il cognome: `SpeakerRegistry.find`)
    non si registra «di nuovo»: l'impronta nuova sostituirebbe quella della persona, e con
    lei il suo livello (analisi di sicurezza del 03/10, S1: un familiare faceva registrare
    «Dario» con la voce di un amico, che da lì amministrava). Rifare l'impronta di un
    profilo che c'è già può solo chi amministra, riconosciuto dalla voce in questa frase:
    la propria subito (le frasi nuove devono somigliare a quella vecchia), quella di un
    altro familiare con un «sì» nel turno dopo; mai quella di un altro che amministra, e
    l'amministrazione non passa mai con una registrazione (`SpeakerContext.enroll_sample`).
    """
    n = _clean_name(nome)
    if not n:
        return {"ok": False, "errore": "nome vuoto"}
    sc = ctx.speaker_ctx
    if getattr(sc, "is_enrolling", False):
        return {"ok": False, "errore": f"c'è già una registrazione in corso, di "
                                       f"{sc.enrolling_name}"}
    existing = ctx.speakers.find(n) if hasattr(ctx.speakers, "find") else None
    if existing is None:
        return _nuovo_profilo(ctx, n, nascita, tutori, maggiorenne)
    prof = ctx.speakers.get(existing)
    chi = sc.current_speaker
    admin_voce = admin_confermato(ctx)
    if not admin_voce:
        sfida = serve_conferma(ctx, "registra_utente", {"nome": n}, f"rifare la voce di {existing}")
        if sfida is not None:
            return sfida
        note_rule(ctx, "registra_esistente_rifiutato")
        frase = (f"{existing} è già registrato: rifare la voce di una persona registrata "
                 f"può solo chi amministra, e deve chiederlo lui.")
        return {"ok": False, "fatto": "NON è stata avviata nessuna registrazione",
                "errore": frase, "risposta_finale": frase}
    if existing == chi:
        sc.start_enroll(existing, reenroll=True)
        return {"ok": True, "nome": existing, "rifai": True,
                "frasi_necessarie": sc.enroll_needed}
    if prof is not None and prof.admin:
        note_rule(ctx, "registra_esistente_rifiutato")
        frase = (f"La voce di {existing} può rifarla solo {existing}, chiedendomelo con la "
                 f"sua voce.")
        return {"ok": False, "fatto": "NON è stata avviata nessuna registrazione",
                "errore": frase, "risposta_finale": frase}
    turno = int(getattr(ctx, "turno", 0) or 0)
    offerte = getattr(ctx, "_riregistra", None)
    if offerte is None:
        offerte = {}
        ctx._riregistra = offerte
    chi_id = getattr(ctx.speakers.get(chi), "id", None) or chi
    off = offerte.get(chi_id)
    if off and off["nome"] == existing and _proposta_ok(ctx, off, turno):
        offerte.pop(chi_id, None)
        sc.start_enroll(existing, reenroll=True)
        return {"ok": True, "nome": existing, "rifai": True,
                "frasi_necessarie": sc.enroll_needed}
    offerte[chi_id] = {"nome": existing, "turno": turno, "quando": time.monotonic()}
    note_rule(ctx, "registra_esistente_conferma")
    domanda = (f"{existing} è già registrato. Vuoi rifare la registrazione della sua voce? "
               f"Dovrà parlare {existing}.")
    return {"ok": True, "fatto": "proposto, la registrazione NON è ancora partita",
            "conferma": domanda, "risposta_finale": domanda,
            "in_sospeso": {"domanda": domanda, "cosa": f"rifare la voce di {existing}",
                           "tool": "registra_utente", "argomenti": {"nome": existing}}}


# ─────────────────────────────── VOCE ───────────────────────────────

def _elenca_voci(ctx: ToolContext) -> dict:
    """Le voci TTS disponibili, una per modello: gli alias («serena-hd») restano
    validi per cambia_voce ma non si elencano, altrimenti Calliope li legge a voce."""
    seen, voci = set(), []
    for name, path in VOICE_MAP.items():
        if path not in seen:
            seen.add(path)
            voci.append(name.capitalize())
    # «Scarica la voce di Leonardo dal catalogo» (e2e del 06/10, giro 5, una familiare): il
    # 26B chiamava elenca_voci e diceva «Ho trovato la voce di Leonardo nel catalogo. Procedo
    # con l'installazione.» senza installare (e non poteva). Come cambia_voce: con «scarica» /
    # «installa» detto e nessun «usa/metti/cambia» l'elenco non è la richiesta; a chi non
    # amministra la frase pronta sul permesso, a chi amministra il tool giusto
    testo = getattr(ctx, "user_text", "") or ""
    if _SCARICA.search(testo) and not _USA.search(testo):
        note_rule(ctx, "voce_scarica_elenco")
        livello = getattr(getattr(ctx, "speaker_ctx", None), "current_level", "ospite")
        if livello != "amministra":
            return {"ok": False, "fatto": NIENTE, "voci": voci, "risposta_finale":
                    "Scaricare voci nuove lo può fare solo chi amministra: chiediglielo."}
        return {"voci": voci, "fatto": "solo l'elenco delle voci: NON ho scaricato niente",
                "cosa_fare": "per scaricare una voce del catalogo chiama installa_proponi"}
    return {"voci": voci}


# Tono delle risposte (04/10, calliope/personalita.py): la frase di conferma è detta già nel
# tono nuovo (risposta_finale: niente seconda passata del modello)
_TONO_DETTO = {
    "normale": "Va bene, torno a parlarti come sempre.",
    "formale": "Certamente: d'ora in avanti le risponderò in modo formale.",
    "amichevole": "Fatto! Da adesso si chiacchiera da amici.",
    "ironico": "Ironia accesa. Cercherò di non esagerare, promesso.",
    "essenziale": "Va bene. Risposte essenziali.",
    "computer_di_bordo": "Modalità computer di bordo attiva.",
}
_TONO_CASA = ("normale", "casa", "della casa", "predefinito", "solito", "di sempre")


def _cambia_tono(ctx: ToolContext, tono: str, per_tutti: bool) -> dict:
    """Il tono di chi parla (nel suo profilo) o, con per_tutti, quello della casa."""
    from ..config import TONI
    from ..personalita import salva_tono_casa
    raw = str(tono or "").strip().lower().replace("_", " ")
    nome = nome_tono(raw)
    if nome is None:
        return {"ok": False, "errore": f"tono «{tono}» sconosciuto",
                "toni_disponibili": [TONI[t]["detto"] for t in TONI]}
    sc = ctx.speaker_ctx
    chi = getattr(sc, "current_speaker", None)
    if per_tutti:
        # Il tono della casa vale per tutti: solo chi amministra (il registro lascia
        # cambia_voce ai familiari; questo controllo è in più, nel codice)
        if getattr(sc, "current_level", "ospite") != "amministra":
            return {"ok": False, "errore": "NON è stata eseguita: il tono di tutta la casa lo "
                    "cambia solo chi amministra", "risposta_finale":
                    "Il tono per tutta la casa lo può cambiare solo chi amministra. Se vuoi, "
                    "lo cambio solo per te."}
        salva_tono_casa(ctx.cfg, nome, chi)
        detto = TONI[nome]["detto"]
        frase = (f"Fatto: da adesso rispondo a tutti con il tono {detto}." if nome != "normale"
                 else "Fatto: da adesso rispondo a tutti come sempre.")
        return {"ok": True, "tono": nome, "per_tutti": True, "risposta_finale": frase}
    prof = ctx.speakers.get(chi) if chi else None
    if prof is None:
        return {"ok": False, "errore": "NON è stata eseguita: non so chi sei, quindi non posso "
                "ricordare il tuo tono", "risposta_finale":
                "Non riconosco la tua voce, quindi non posso ricordare come preferisci che ti "
                "parli."}
    casa = nome_tono(ctx.cfg.tono)
    # «Torna al tono di sempre» / «quello della casa»: si toglie la scelta personale
    prof.preferred_tone = None if (nome == casa or raw in _TONO_CASA) else nome
    ctx.speakers.save()
    usato = prof.preferred_tone or casa
    return {"ok": True, "tono": usato, "risposta_finale": _TONO_DETTO.get(
        usato, f"Va bene, da adesso ti parlo con il tono {TONI[usato]['detto']}.")}


def _cambia_modalita(ctx: ToolContext, modalita: str) -> dict:
    """La modalità (05/10, calliope/modalita.py): wake word, suoni e tono insieme, subito.
    Vale per tutta la casa: solo chi amministra, riconosciuto dalla voce in questa frase (una
    frase breve o incerta: la frase di sfida; scritto: «me lo chiedi a voce?»)."""
    from ..config import nome_modalita
    from ..modalita import Modalita, frase
    from .spec import serve_la_voce
    args = {"modalita": modalita}
    sc = ctx.speaker_ctx
    mod = getattr(ctx, "modalita", None) or Modalita(ctx.cfg)
    if (nome_modalita(modalita) == "normale" and mod.attuale != "normale"
            and getattr(sc, "identified_by", None) == "schermo" and e_admin(ctx)):
        # Tornare alla modalità normale scritto dallo schermo personale di chi amministra
        # (06/10): ripristina il predefinito, è reversibile e serve proprio quando la voce
        # non va (sulla DGX in startrek «Computer» non svegliava, e lo scritto era rifiutato:
        # «serve la voce»). Solo questo: attivare startrek scritto chiede ancora la voce
        note_rule(ctx, "modalita_normale_scritta")
        esito = mod.cambia("normale", getattr(sc, "current_speaker", None))
        return {**{k: v for k, v in esito.items() if k != "stato"},
                **(esito.get("stato") or {}), "risposta_finale": frase(esito)}
    scritto = serve_la_voce(ctx, "cambia_voce", args, "cambiare la modalità")
    if scritto is not None:
        return scritto
    if not e_admin(ctx):
        note_rule(ctx, "modalita_permesso")
        f = ("La modalità la può cambiare solo chi amministra. Se vuoi, cambio solo il tono "
             "con cui parlo a te.")
        return {"ok": False, "errore": "NON è stata eseguita: solo chi amministra",
                "risposta_finale": f}
    if not admin_confermato(ctx):
        return chiedi_conferma(ctx, "cambia_voce", args, "cambiare la modalità")
    esito = mod.cambia(modalita, getattr(sc, "current_speaker", None))
    return {**{k: v for k, v in esito.items() if k != "stato"}, **(esito.get("stato") or {}),
            "risposta_finale": frase(esito)}


def _cambia_voce(ctx: ToolContext, voce: str = "", tono: str = "",
                 per_tutti: bool = False, modalita: str = "") -> dict:
    """Cambia la voce con cui Calliope parla, il tono delle risposte o la modalità."""
    if str(modalita or "").strip():
        return _cambia_modalita(ctx, str(modalita).strip())
    voce = str(voce or "").strip()
    if tono or (voce and not _voice_path(voce) and nome_tono(voce)):
        # «Parla in modo più formale» con il tono messo in `voce`: è il tono (conversione
        # della scelta del modello, regola tono_da_voce)
        if not tono:
            note_rule(ctx, "tono_da_voce")
        # per_tutti arriva a volte come testo («true», «false»): bool("false") sarebbe vero
        tutti = (per_tutti if isinstance(per_tutti, bool)
                 else str(per_tutti).strip().lower() in ("true", "1", "sì", "si", "yes"))
        esito = _cambia_tono(ctx, tono or voce, tutti)
        if tono and voce and _voice_path(voce) and esito.get("ok"):
            # Voce e tono insieme («voce di Paola e tono formale»): anche la voce
            v = _cambia_voce_tts(ctx, voce)
            esito = {**esito, "voce": v.get("voce"), "voce_ok": v.get("ok")}
        return esito
    if not voce:
        return {"ok": False, "errore": "manca la voce o il tono"}
    return _cambia_voce_tts(ctx, voce)


def _voice_path(voce: str) -> str | None:
    key = (voce or "").strip().lower()
    path = VOICE_MAP.get(key)
    if not path and key:                           # match parziale: "serena-hd" → "serena"
        for k, p in VOICE_MAP.items():
            if k.startswith(key) or key.startswith(k):
                return p
    return path


# «Scarica la voce di Ugo», «installa la voce di Paola»: chiede un download, non un cambio
# (e2e del 06/10: detto da una familiare, il modello sceglieva cambia_voce e la voce
# cambiava). Vincolo sul verbo detto contro l'azione scelta (principio 10, come
# politica_azione_incoerente): si chiede invece di cambiare, regola `voce_scarica_non_cambia`.
# Contrari: «usa la voce di Ugo», «cambia voce, metti quella scaricata ieri»
_SCARICA = re.compile(r"(?<![a-zà-ù])(scaric|install)[a-zà-ù]*", re.I)
_USA = re.compile(r"(?<![a-zà-ù])(usa|usare|usi|cambia|cambiare|metti|mettere|passa|passare|"
                  r"torna|tornare|parlami|parla)(?![a-zà-ù])", re.I)


def _cambia_voce_tts(ctx: ToolContext, voce: str) -> dict:
    """Cambia la voce con cui Calliope parla (solo tra quelle installate)."""
    key = (voce or "").strip().lower()
    nome_voce = key
    path = VOICE_MAP.get(key)
    if not path:                                  # match parziale: "serena-hd" → "serena"
        for k, p in VOICE_MAP.items():
            if k.startswith(key) or key.startswith(k):
                path, nome_voce = p, k
                break
    if not path:
        return {"ok": False, "errore": f"voce «{voce}» sconosciuta",
                "voci_disponibili": list(VOICE_MAP)}
    detto = nome_voce.split("-")[0].capitalize()
    livello = getattr(getattr(ctx, "speaker_ctx", None), "current_level", "ospite")
    installata = Path(path).is_file() and Path(path + ".json").is_file()
    testo = getattr(ctx, "user_text", "") or ""
    if _SCARICA.search(testo) and not _USA.search(testo):
        note_rule(ctx, "voce_scarica_non_cambia")
        pre = ("" if livello == "amministra"
               else "Scaricare voci nuove lo può fare solo chi amministra. ")
        if not installata:
            frase = pre + (f"La voce di {detto} qui non è installata." if pre else
                           f"La voce di {detto} non è installata: per scaricarla usa "
                           f"«scarica la voce di…» con una voce del catalogo.")
            return {"ok": False, "fatto": NIENTE, "risposta_finale": frase}
        frase = pre + f"La voce di {detto} però c'è già: vuoi che la usi?"
        return {"ok": False, "fatto": f"{NIENTE}, chiedo conferma", "risposta_finale": frase,
                "conferma": frase,
                "in_sospeso": {"domanda": frase, "cosa": f"usare la voce di {detto}",
                               "tool": "cambia_voce", "argomenti": {"voce": voce}}}
    if not installata:
        # Mai fingere un cambio: la voce non c'è sul disco
        frase = (f"La voce di {detto} non è installata, quindi non posso usarla."
                 + (" Per scaricarla chiedi a chi amministra." if livello != "amministra"
                    else ""))
        return {"ok": False, "fatto": NIENTE, "errore": "voce non installata",
                "risposta_finale": frase}
    if not ctx.speaker.change_voice(path):
        return {"ok": False, "errore": "cambio voce fallito"}
    if ctx.speaker_ctx.current_speaker:
        prof = ctx.speakers.get(ctx.speaker_ctx.current_speaker)
        if prof:
            prof.preferred_voice = path
            ctx.speakers.save()
    # Frase pronta (06/10, e2e: il modello diceva «Ho tornato alla voce di Serena»)
    return {"ok": True, "voce": path,
            "risposta_finale": f"Va bene, da adesso parlo con la voce di {detto}."}


# ─────────────────────────────── ORA E DATA ───────────────────────────────

def _ora_attuale(ctx: ToolContext) -> dict:
    """L'ora locale adesso."""
    now = datetime.datetime.now()
    # da_dire (03/10): se dopo il tool il modello non dice niente, Brain dice questa
    # (conferma_al_posto_del_vuoto) invece di lasciare la risposta senza l'ora
    return {"ora": now.strftime("%H:%M"), "fuso": "locale",
            "da_dire": f"Sono le {now.hour}:{now.minute:02d}."}


def _data_oggi(ctx: ToolContext) -> dict:
    """La data di oggi."""
    now = datetime.datetime.now()
    giorni = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
    return {"data": now.strftime("%d/%m/%Y"), "giorno": giorni[now.weekday()],
            "da_dire": f"Oggi è {giorni[now.weekday()]} {now.day} {MESI[now.month - 1]} "
                       f"{now.year}."}


# ─────────────────────────────── CALCOLI ───────────────────────────────
# I modelli piccoli sbagliano i conti a mente (17×6 sbagliato da tutti il 21/09; il
# 26/09 «300 miliardi per 2748» → «divisi… 108,84»). Il modello scrive l'espressione,
# Python la calcola. Niente eval: si visita l'albero sintattico e si ammettono solo
# numeri, operatori e poche funzioni.

_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
           ast.Mod: operator.mod, ast.Pow: operator.pow}
_UNOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
# Trigonometria in gradi: è quella dei compiti di scuola
_FUNCS = {"sqrt": math.sqrt, "radice": math.sqrt, "abs": abs, "round": round,
          "sin": lambda x: math.sin(math.radians(x)), "cos": lambda x: math.cos(math.radians(x)),
          "tan": lambda x: math.tan(math.radians(x)), "log": math.log10, "log10": math.log10,
          "ln": math.log, "exp": math.exp, "fattoriale": math.factorial,
          "factorial": math.factorial}
_CONSTS = {"pi": math.pi, "e": math.e}


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNOPS:
        return _UNOPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > 1000 or abs(left) > 1e100):
            raise ValueError("potenza troppo grande")
        return _BINOPS[type(node.op)](left, right)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in _FUNCS and len(node.args) in (1, 2) and not node.keywords):
        args = [_eval_node(a) for a in node.args]
        if node.func.id in ("fattoriale", "factorial") and args[0] > 1000:
            raise ValueError("fattoriale troppo grande")
        return _FUNCS[node.func.id](*args)
    raise ValueError("espressione non ammessa")


def _format_it(x) -> str:
    """Numero scritto all'italiana, per la voce: punto per le migliaia, virgola decimale."""
    if isinstance(x, float) and x.is_integer() and abs(x) < 1e15:
        x = int(x)
    if isinstance(x, int):
        return f"{x:,}".replace(",", ".")
    if abs(x) >= 1e15 or (x != 0 and abs(x) < 1e-6):
        return f"{x:.6g}".replace(".", ",")
    s = f"{x:,.6f}".rstrip("0").rstrip(".")
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def _to_say(x) -> str:
    """Il risultato come va detto a voce: i numeri grandi in milioni/miliardi e pochi
    decimali. Il 26/09 «824.400.000.000.000» veniva letto «ottocentoventiquattro
    quadrati…»; meglio «circa 824,4 mila miliardi»."""
    ax = abs(x)
    for scale, name in ((1e15, "milioni di miliardi"), (1e12, "mila miliardi"),
                        (1e9, "miliardi"), (1e6, "milioni")):
        if ax >= scale:
            v = x / scale
            r = round(v, 2) if abs(v) < 100 else round(v, 1)
            return ("" if abs(r - v) < 1e-9 else "circa ") + f"{_format_it(r)} {name}"
    if isinstance(x, float) and not x.is_integer():
        r = round(x, 2) if ax >= 1 else float(f"{x:.3g}")
        # Tolleranza: sin(30) vale 0,49999999999999994 e non va detto «circa 0,5»
        return ("circa " if abs(r - x) > 1e-9 * max(1.0, ax) else "") + _format_it(r)
    return _format_it(x)


# Una data scritta come numeri dentro un conto: 1977-07-04, 04/07/1977
_DATA_IN_CONTO = re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b")


def _calcola(ctx: ToolContext, espressione: str) -> dict:
    """Calcola un'espressione aritmetica in modo esatto."""
    # Un minore nei compiti (05/10): il risultato non si dà, si controlla il suo
    from .minori import calcola_in_compiti
    compito = calcola_in_compiti(ctx, espressione or "")
    if compito is not None:
        return compito
    expr = (espressione or "").strip()
    # Scritture comuni del modello o del parlato: × ÷ ^ , decimale
    expr = expr.replace("×", "*").replace("÷", "/").replace("^", "**").replace(":", "/")
    expr = re.sub(r"(?<=\d),(?=\d)", ".", expr)
    if not expr or len(expr) > 200:
        return {"ok": False, "errore": "espressione vuota o troppo lunga"}
    if _DATA_IN_CONTO.search(expr):
        # «2026-07-04-1977-07-04» (05/10, DGX): una data non si sottrae come un numero
        return {"ok": False, "errore": "questa è una data, non un conto: per età, giorni e "
                                       "date usa data_calcola con le date come dette"}
    try:
        value = _eval_node(ast.parse(expr, mode="eval"))
    except ZeroDivisionError:
        return {"ok": False, "errore": "divisione per zero"}
    except (ValueError, SyntaxError, TypeError, OverflowError) as e:
        return {"ok": False, "errore": f"non riesco a calcolare «{espressione}»: {e}"}
    if isinstance(value, float) and not math.isfinite(value):
        return {"ok": False, "errore": "risultato non finito"}
    out = {"ok": True, "espressione": expr, "risultato": _format_it(value),
           "da_dire": _to_say(value)}
    return _con_scheda(out, ctx, lambda: schede.calcolo(expr, out["risultato"]))


# ─────────────────────────────── CONTI CON LE DATE ───────────────────────────────
# 05/10 sera, DGX (26B): «sono nato il 4 luglio del 1977» → calcola('2026-07-04-1977-07-04')
# (errore: zeri iniziali), poi calcola('2026-1977') = 49 e «hai 49 anni», ma il 05/10/2026
# gli anni compiuti erano 48. Età, giorni a una data e giorno della settimana li fa il
# programma; il modello passa le date come dette (tempi.parse_date), come per timer e
# promemoria. Un tool a parte e non funzioni dentro calcola: misura in
# prove/prova_date_ricordi_ollama.py (gemma4 e4b, vedi CLAUDE.md).
_COSE_DATE = ("eta", "giorni_mancanti", "giorni_passati", "giorno_settimana", "differenza")


def _data_calcola(ctx: ToolContext, cosa: str, data: str = "", data2: str = "",
                  persona: str = "") -> dict:
    """Conti con le date: anni compiuti, giorni che mancano o che sono passati, giorno della
    settimana, differenza tra due date. Risultato con `da_dire`. Con `persona` («io» o il
    nome di una persona registrata) età e compleanno vengono dalla data di nascita del
    profilo (07/10)."""
    oggi = datetime.date.today()
    cosa = (cosa or "").strip().lower().replace("à", "a")
    if cosa not in _COSE_DATE:
        return {"ok": False, "errore": f"cosa sconosciuta: {cosa!r} (una di {', '.join(_COSE_DATE)})"}
    if (persona or "").strip():
        r = _data_persona(ctx, cosa, persona, oggi, bool((data or "").strip()))
        if r is not None:
            return r
        # Nel profilo non c'è la nascita, ma il modello ha passato la data (dai ricordi o dalla
        # conversazione, 07/10): si conta con quella
        note_rule(ctx, "eta_data_dal_modello")
        out = _data_calcola(ctx, cosa, data, data2)
        chi = _persona_registrata(ctx, persona)
        se_stesso = isinstance(chi, tuple) and chi[2]
        if out.get("ok") and cosa == "eta" and se_stesso and not (data2 or "").strip():
            n = out["anni"]
            out["da_dire"] = (f"Oggi compi {n} anni: buon compleanno!"
                              if out.get("prossimo_compleanno") == out.get("oggi") else
                              f"Hai {n} anni; ne compi {n + 1} il {out['prossimo_compleanno']}.")
        return out
    if not (data or "").strip():
        return {"ok": False, "errore": "manca la data. Per l'età o il compleanno di chi parla "
                                       "o di una persona di casa passa persona («io» o il "
                                       "nome); altrimenti la data come detta"}
    p = tempi.parse_date(data, oggi)
    if p is None:
        return {"ok": False, "errore": f"non capisco la data «{data}»: passala come detta, "
                                       f"per esempio «4 luglio 1977» o «25 dicembre»"}
    d, con_anno = p
    q = tempi.parse_date(data2, oggi) if (data2 or "").strip() else (oggi, True)
    if q is None:
        return {"ok": False, "errore": f"non capisco la data «{data2}»"}
    d2, _ = q
    detta = tempi.say_date(d, oggi, anno=con_anno)
    out: dict = {"ok": True, "oggi": tempi.say_date(oggi)}
    if cosa == "eta":
        if not con_anno:
            return {"ok": False, "errore": "per gli anni serve l'anno della data: chiedilo"}
        if d == oggi and not (data2 or "").strip():
            # 06/10 sera: «Quanti anni ho?» → data = oggi, «compie 0 anni proprio oggi», e il
            # modello diceva «oggi è il tuo compleanno». La data di oggi non è una nascita
            note_rule(ctx, "data_eta_oggi")
            return {"ok": False, "fatto": NIENTE,
                    "errore": "la data passata è quella di oggi, non una data di nascita",
                    "cosa_fare": "per l'età di chi parla o di una persona di casa richiama "
                                 "data_calcola con persona («io» o il nome); altrimenti "
                                 "chiedi la data di nascita"}
        if d > d2:
            return {"ok": False, "errore": f"il {detta} viene dopo il {tempi.say_date(d2)}"}
        n = tempi.anni_compiuti(d, d2)
        compleanno = tempi.prossima(tempi.stesso_giorno(d, d2.year), d2)
        out.update(anni=n, prossimo_compleanno=tempi.say_date(compleanno))
        # Una frase intera con il soggetto («chi è nato…»): con «49 anni compiuti» da solo
        # gemma4 e4b diceva «Ti sono 49 anni compiuti»
        quando = "oggi" if d2 == oggi else f"il {tempi.say_date(d2)}"
        out["da_dire"] = (
            f"Chi è nato il {detta} compie {n} anni proprio {quando}." if compleanno == d2
            else f"Chi è nato il {detta} {quando} "
            f"{'ha' if d2 == oggi else 'aveva' if d2 < oggi else 'avrà'} {n} anni"
            + (f"; ne compie {n + 1} il {tempi.say_date(compleanno)}." if d2 == oggi else "."))
        return out
    if cosa == "giorno_settimana":
        g = tempi.GIORNI_SETTIMANA[d.weekday()]
        verbo = "era" if d < oggi else ("è" if d == oggi else "sarà")
        out.update(giorno=g, da_dire=f"Il {detta} {verbo} {'un' if g != 'domenica' else 'una'} {g}.")
        return out
    if cosa == "giorni_mancanti":
        if not con_anno:
            d = tempi.prossima(d, oggi)
        n = (d - d2).days
        out.update(giorni=n, data=tempi.say_date(d))
        out["da_dire"] = ("È oggi." if n == 0 else "È domani." if n == 1 else
                          f"Mancano {n} giorni al {tempi.say_date(d, oggi, anno=False)}." if n > 0
                          else f"Il {tempi.say_date(d)} è già passato da {-n} giorni.")
        return out
    if cosa == "giorni_passati":
        if not con_anno and d > oggi:
            d = tempi.stesso_giorno(d, oggi.year - 1)
        n = (d2 - d).days
        out.update(giorni=n, data=tempi.say_date(d))
        out["da_dire"] = ("È oggi." if n == 0 else
                          f"Dal {tempi.say_date(d, oggi, anno=False)} sono passati {n} giorni." if n > 0
                          else f"Il {tempi.say_date(d)} deve ancora venire: mancano {-n} giorni.")
        return out
    # differenza tra due date
    a, b = sorted((d, d2))
    n = (b - a).days
    out.update(giorni=n, anni=tempi.anni_compiuti(a, b))
    out["da_dire"] = (f"Tra il {tempi.say_date(a)} e il {tempi.say_date(b)} ci sono {n} giorni"
                      + (f", cioè {out['anni']} anni compiuti" if out["anni"] else "") + ".")
    return out


def _data_persona(ctx: ToolContext, cosa: str, persona: str, oggi: datetime.date,
                  con_data: bool = False) -> dict | None:
    """Età e compleanno di una persona registrata, dalla data di nascita del profilo. None se
    nel profilo non c'è la nascita e il modello ha passato la data (`con_data`): si conta con
    quella (_data_calcola)."""
    r = _persona_registrata(ctx, persona)
    if isinstance(r, dict):
        return None if con_data else r
    prof, nome, se_stesso = r
    chi = _profilo_di(ctx, getattr(getattr(ctx, "speaker_ctx", None), "current_speaker", None))
    if not se_stesso and not _vede_nascita(chi, prof):
        note_rule(ctx, "nascita_riservata")
        return {"ok": False, "fatto": NIENTE,
                "errore": f"età e compleanno di {nome} li dico solo a {nome}, ai suoi tutori "
                          f"e a chi amministra",
                "risposta_finale": f"L'età e il compleanno di {nome} li dico solo a chi è "
                                   f"della sua famiglia e se ne occupa."}
    dati = _dati_nascita(prof, oggi)
    dal_ricordo = None
    if not dati:
        if con_data:
            return None
        # 07/10 pomeriggio, DGX: «ricordati che il mio compleanno è il 4 luglio del 1977» era
        # nei ricordi, ma il modello richiamava data_calcola(persona=io) senza data, falliva
        # due volte e diceva «Ho appena recuperato il dato…». Con la data nel risultato
        # dell'errore gemma4 e4b non richiamava mai (0 su 8, misura del 07/10): per chi parla,
        # un solo suo ricordo con una data completa e la parola della nascita vale come data
        # di nascita (regola eta_dal_ricordo), e la risposta propone di salvarla nel profilo
        dal_ricordo = _nascita_dal_ricordo(ctx, prof) if se_stesso else None
        if dal_ricordo is None:
            return {"ok": False, "fatto": NIENTE,
                    "errore": f"nel profilo di {nome} non c'è la data di nascita",
                    "cosa_fare": f"se la data di nascita di {nome} la conosci (da questa "
                                 f"conversazione o dai ricordi), richiama subito data_calcola "
                                 f"con la stessa persona e data = quella data, come detta; "
                                 f"altrimenti chiedila"}
        note_rule(ctx, "eta_dal_ricordo")
        dati = _dati_nascita(SimpleNamespace(nascita=dal_ricordo[1].isoformat()), oggi)
    if cosa not in ("eta", "giorni_mancanti"):
        return {"ok": False, "errore": "con persona: cosa è eta o giorni_mancanti (al "
                                       "compleanno); per il resto passa la data"}
    n, g = dati["anni"], dati["giorni_al_compleanno"]
    quando = ("oggi" if g == 0 else "domani" if g == 1
              else f"il {dati['prossimo_compleanno']}, tra {g} giorni")
    if se_stesso:
        frase = (f"Oggi compi {n} anni: buon compleanno!" if g == 0 else
                 f"Hai {n} anni; ne compi {n + 1} {quando}.")
    else:
        frase = (f"Oggi {nome} compie {n} anni." if g == 0 else
                 f"{nome} ha {n} anni; ne compie {n + 1} {quando}.")
    out = {"ok": True, "oggi": tempi.say_date(oggi), "persona": nome, **dati, "da_dire": frase}
    if dal_ricordo is not None:
        fatto, d = dal_ricordo
        out["fonte"] = f"il ricordo «{fatto}»"
        proposta = _proponi_nascita(ctx, prof, fatto, d)
        if proposta:
            frase = f"{frase} {_NASCITA_DOMANDA_RICORDO}"
            out.update(da_dire=frase, conferma=frase, risposta_finale=frase,
                       in_sospeso=proposta)
    return out


# Un ricordo di chi parla sulla sua nascita: una data completa e una di queste parole
_NASCITA_RICORDO = re.compile(r"(?<![a-zà-ù])(?:compleann\w*|nat[oa]|nascita)(?![a-zà-ù])",
                              re.I)
_NASCITA_DOMANDA_RICORDO = "L'ho preso dai tuoi ricordi: lo salvo come tua data di nascita?"


def _nascita_dal_ricordo(ctx, prof):
    """(fatto, data) se tra i ricordi di `prof` ce n'è uno solo con una data completa e la
    parola della nascita, e la data non lo renderebbe minorenne; altrimenti None."""
    mem = getattr(ctx, "memory", None)
    if mem is None or prof is None or minori.e_minore(prof):
        return None
    try:
        fatti = mem.facts(prof.id)
    except Exception:  # noqa: BLE001
        return None
    trovati = [(f, minori.leggi_data(f)) for f in fatti if _NASCITA_RICORDO.search(f)]
    trovati = [(f, d) for f, d in trovati if d is not None]
    if len({d for _, d in trovati}) != 1:
        return None
    f, d = trovati[0]
    return None if minori.fascia_per_eta(minori.eta(d)) is not None else (f, d)


def _proponi_nascita(ctx, prof, fatto: str, d) -> dict | None:
    """L'offerta di salvare `d` nel profilo (ricorda con `nascita`, al «sì»): l'azione in
    sospeso, o None se la data non si può proporre."""
    nascita = tempi.say_date(d)
    d2, regola = _nascita_profilo(ctx, prof, nascita)
    if d2 is None:
        if regola:
            note_rule(ctx, regola)
        return None
    offerte = getattr(ctx, "_nascite", None)
    if offerte is None:
        offerte = {}
        ctx._nascite = offerte
    offerte[prof.id] = {"data": d2.isoformat(), "turno": int(getattr(ctx, "turno", 0) or 0),
                        "quando": time.monotonic()}
    note_rule(ctx, "nascita_proposta")
    return {"domanda": _NASCITA_DOMANDA, "tool": "ricorda",
            "cosa": "la data di nascita nel tuo profilo",
            "argomenti": {"fatto": fatto, "nascita": nascita}}


# ─────────────────────────────── TIMER E PROMEMORIA ───────────────────────────────
# Durate e orari arrivano come detti a voce e si convertono in tempi.py: il modello
# trasformava «tra mezz'ora» in 60 minuti (banco dei tool del 26/09).

# ── Cambiare un timer, un promemoria o un appuntamento già messo (03/10) ──
# «Mettimi un timer di un secondo», poi «adesso impostalo di un minuto»: Calliope ne avviava
# un secondo. I tre tool che creano hanno `cambia`: il modello decide se si cambia una voce
# già messa (e come); quale voce lo decide il codice (la più simile al nome, se lo dice,
# altrimenti l'ultima messa dalla persona: Agenda.find), mai una regola sul testo.
_CAMBIA = ("imposta", "aggiungi", "togli")
# «Adesso impostalo di cinque minuti» dopo un timer di un minuto: con «la durata nuova» il
# modello sceglieva «aggiungi» 2 volte su 2 (prova del 03/10); serve dire che la durata
# detta sostituisce quella di prima
_CAMBIA_DESC = ("Solo per cambiare il timer già messo invece di avviarne un altro. «imposta»: "
                "la durata detta sostituisce quella di prima («impostalo di cinque minuti», "
                "«fallo diventare di mezz'ora», «mettilo a un minuto»). «aggiungi» o «togli» "
                "solo se chi parla dice di aggiungere o togliere («aggiungi cinque minuti», "
                "«altri 5 minuti», «toglici due minuti»). Per «un altro timer» non va passato.")
_SPOSTA_DESC = ("Solo per spostare quello già messo invece di crearne un altro: «imposta» per "
                "il nuovo quando («spostalo alle 9»), «aggiungi» o «togli» per rimandarlo o "
                "anticiparlo («rimandalo di mezz'ora»).")
_CLOCK = re.compile(r"\b(alle|all'|domani|dopodomani|stasera|stamattina|lunedì|martedì|"
                    r"mercoledì|giovedì|venerdì|sabato|domenica)\b", re.I)
_DAY = re.compile(r"\b(tra|fra|oggi|domani|dopodomani|stasera|stamattina|lunedì|martedì|"
                  r"mercoledì|giovedì|venerdì|sabato|domenica)\b", re.I)


def _modo(cambia) -> str:
    """Il modo di cambiare scelto dal modello; vuoto = voce nuova. «sì», true valgono
    «imposta»; un altro valore fuori elenco («crea», «nuovo timer», «boh») è "?": prima
    valeva «imposta» e cambiava una voce già messa invece di crearne una (analisi del
    03/10), ora il tool risponde con un errore (_modo_sbagliato)."""
    c = str(cambia or "").strip().lower()
    if c in _CAMBIA:
        return c
    if c in ("", "no", "nuovo", "nuova", "false", "none", "null", "nessuno", "niente"):
        return ""
    return "imposta" if c in ("sì", "si", "true", "1", "yes", "cambia") else "?"


def _modo_sbagliato(cambia) -> dict:
    return {"ok": False, "errore": f"cambia={cambia!r} non è un valore valido: non ho fatto "
            "niente", "cosa_fare": "per una voce nuova richiama senza cambia; per cambiare "
            "quella già messa usa cambia=imposta, aggiungi o togli"}


# Una durata vaga («un po'», «qualche minuto», «un attimo»): parse_duration la prendeva per
# 1 minuto e il timer partiva così (analisi del 03/10). Si chiede quanto
_VAGA = re.compile(r"\b(un\s+po['’]?|un\s+pochino|qualche|un\s+attimo|un\s+momento|pochi|poco)\b",
                   re.I)


def _durata_vaga(durata) -> bool:
    d = str(durata or "")
    return bool(_VAGA.search(d)) and not re.search(r"\d", d)


def _spostamento(ctx, testo: str, modo: str) -> tuple[str, int | None]:
    """(modo, secondi) per «aggiungi»/«togli»; con «imposta» e una durata detta come
    spostamento («5 minuti in più») il modo segue la frase (correzione della forma)."""
    shift = parse_shift(str(testo))
    if shift is not None and modo == "imposta":
        note_rule(ctx, "durata_relativa")
        return ("aggiungi" if shift > 0 else "togli"), abs(shift)
    if modo in ("aggiungi", "togli"):
        secs = abs(shift) if shift is not None else parse_duration(str(testo))
        return modo, secs
    return modo, None


def _rif(kind: str, label: str, tool: str, item_id: int | None = None) -> dict:
    """L'ultima voce messa, per «impostalo…», «spostalo…» nei turni dopo (Brain.AGENDA_MSG).
    `item_id`: la voce nell'agenda (07/10): suonata o annullata, il riferimento non vale più."""
    return {"cosa": f"{kind} «{label}»", "tool": tool, "id": item_id}


def _timer_auto_label(label: str) -> bool:
    """Il nome l'ha dato Calliope dalla durata («di 1 minuto»): si rifà con quella nuova."""
    return bool(re.fullmatch(r"di [\w ]+", label or "")) and bool(parse_duration(label))


def _timer_cambia(ctx, durata: str, nome: str, modo: str, prof) -> dict | None:
    """Cambia un timer già messo. None = nessun timer da cambiare (il chiamante ne avvia uno
    nuovo e lo dice)."""
    owner = prof.id if prof else None
    item, _ = ctx.agenda.find("timer", nome, owner)
    if item is None:
        return None
    now = time.time()
    modo, secs = _spostamento(ctx, durata, modo)
    if modo == "imposta":
        when = parse_when(str(durata)) if _CLOCK.search(str(durata)) else None
        secs = round(when.timestamp() - now) if when else parse_duration(str(durata))
        if not secs or secs <= 0:
            return {"ok": False, "errore": f"non capisco la durata «{durata}»: chiedi di ripeterla"}
        due = now + secs
    else:
        if not secs:
            return {"ok": False, "errore": f"non capisco quanto tempo "
                    f"{'aggiungere' if modo == 'aggiungi' else 'togliere'}: «{durata}»"}
        due = item["due"] + (secs if modo == "aggiungi" else -secs)
    left = due - now
    if left < 1:
        return {"ok": False, "errore": "così il timer sarebbe già scaduto: non l'ho cambiato",
                "cosa_fare": "chiedi quanto deve durare"}
    if left > 7 * 86400:
        return {"ok": False, "errore": "durata troppo lunga per un timer: usa un promemoria"}
    # Quanto manca detto a voce: «14 minuti e 59 secondi» dopo «aggiungi cinque minuti» a un
    # timer di 10 avviato un secondo fa si dice «15 minuti» (i secondi solo sotto i 2 minuti)
    heard = round(left) if left < 120 else round(left / 60) * 60
    label = item["label"]
    if _timer_auto_label(label):
        label = f"di {say_duration(heard)}"
    new = ctx.agenda.reschedule(item["id"], due, label=label)
    named = not _timer_auto_label(label)
    what = f"il timer {label}" if named else "il timer"
    if modo == "imposta":
        conferma = f"Fatto, ho cambiato {what}: ora scade tra {say_duration(heard)}."
    else:
        verb = "aggiunto" if modo == "aggiungi" else "tolto"
        conferma = (f"Fatto, ho {verb} {say_duration(secs)} a{what[1:]}: ora scade tra "
                    f"{say_duration(heard)}.")
    out = {"ok": True, "timer": label, "cambiato": True, "mancano": say_duration(heard),
           "conferma": conferma,
           "riferimento_agenda": _rif("il timer", label, "timer_imposta", item["id"])}
    # Stessa scheda (stessa identità, timer:<id>-<creazione>), aggiornata e portata in cima
    return _con_scheda(out, ctx, lambda: schede.timer(new))


def _sposta(ctx, kind: str, query: str, quando: str, modo: str, prof, tool: str) -> dict:
    """Sposta un promemoria o un appuntamento già messo (con l'avviso dell'appuntamento)."""
    the = "l'" if kind[0] in "aeiou" else "il "
    item, gone = ctx.agenda.find(kind, query, prof.id)
    if item is None:
        detto = "era già passato" if gone else "non c'è"
        return {"ok": False, "errore": f"{the}{kind} da cambiare {detto}: non ho cambiato niente",
                "cosa_fare": f"se chi parla vuole un {kind} nuovo, chiama {tool} senza cambia"}
    # parse_when non conosce il passato: «ieri alle 7» diventerebbe «oggi alle 19»
    if re.search(r"\b(ieri|scors[oa])\b", str(quando), re.I):
        return {"ok": False, "errore": f"«{quando}» è già passato: non l'ho spostato",
                "cosa_fare": "chiedi il giorno giusto"}
    now = datetime.datetime.now()
    modo, secs = _spostamento(ctx, quando, modo)
    if modo == "imposta":
        # «Spostalo alle 9» senza giorno: lo stesso giorno della voce (domani resta domani)
        base = now
        day = datetime.datetime.fromtimestamp(item["due"]).date()
        if day > now.date() and not _DAY.search(str(quando)):
            base = datetime.datetime.combine(day, datetime.time())
        when = parse_when(str(quando), base)
        if when is None:
            return {"ok": False, "errore": f"non capisco quando: «{quando}»",
                    "cosa_fare": "chiedi il giorno e l'ora"}
    else:
        if not secs:
            return {"ok": False, "errore": f"non capisco di quanto spostarlo: «{quando}»"}
        # Sull'epoch: «spostalo di un'ora» è un'ora vera anche al cambio dell'ora legale
        when = datetime.datetime.fromtimestamp(item["due"] + (secs if modo == "aggiungi"
                                                              else -secs))
    if when <= now:
        return {"ok": False, "errore": f"{say_when(when)} è già passato: non l'ho spostato",
                "cosa_fare": "chiedi il giorno giusto"}
    lead = int(getattr(ctx.cfg, "appuntamento_anticipo_min", 60) or 0)
    ctx.agenda.reschedule(item["id"], when.timestamp(), lead_s=lead * 60)
    label = item["label"]
    if kind == "appuntamento":
        avviso = ""
        if lead > 0 and sposta(when, -lead * 60) > now:
            ahead = "un'ora" if lead == 60 else say_duration(lead * 60)
            avviso = f" Te lo ricordo {ahead} prima."
        conferma = f"Spostato: {label}, {say_when(when)}.{avviso}"
    else:
        conferma = f"Va bene, ho spostato il promemoria: {say_when(when)} ti ricordo di {label}."
    return _con_scheda({"ok": True, kind: label, "quando": say_when(when), "cambiato": True,
                        "conferma": conferma,
                        "riferimento_agenda": _rif(f"{the}{kind}", label, tool, item["id"])},
                       ctx, lambda: _scheda_agenda(ctx, prof))


def _timer_imposta(ctx: ToolContext, durata: str, nome: str = "", cambia: str = "") -> dict:
    """Avvia un timer (della casa: lo possono usare anche gli ospiti)."""
    if ctx.agenda is None:
        return {"ok": False, "errore": "agenda non disponibile"}
    prof = _person(ctx)
    modo = _modo(cambia)
    if modo == "?":
        return _modo_sbagliato(cambia)
    if _durata_vaga(durata):
        domanda = "Quanto deve durare il timer?"
        return {"ok": False, "fatto": "niente", "errore": f"«{durata}» non è una durata",
                "conferma": domanda, "risposta_finale": domanda}
    rearmed = False
    if modo:
        changed = _timer_cambia(ctx, durata, nome, modo, prof)
        if changed is not None:
            return changed
        # Nessun timer da cambiare (quello di un secondo è già suonato): se ne avvia uno
        # nuovo e la conferma lo dice; «aggiungi 5 minuti» vale un timer di 5 minuti
        rearmed = True
        modo, shift = _spostamento(ctx, durata, modo)
        if modo == "togli":
            return {"ok": False, "errore": "non c'è nessun timer da accorciare",
                    "cosa_fare": "chiedi se vuole un timer nuovo e di quanto"}
        if shift:
            durata = say_duration(shift)
    secs = parse_duration(str(durata))
    if not secs:
        return {"ok": False, "errore": f"non capisco la durata «{durata}»: chiedi di ripeterla"}
    if secs > 7 * 86400:
        return {"ok": False, "errore": "durata troppo lunga per un timer: usa un promemoria"}
    label = (nome or "").strip().rstrip(".")
    # «timer per la pasta», non «timer la pasta» (il modello passa «pasta» o «la pasta»)
    if label and not re.match(r"(di|del|dell|della|dei|degli|delle|per)\b", label, re.I):
        label = f"per {label}"
    label = label or f"di {say_duration(secs)}"
    due = time.time() + secs
    tid = ctx.agenda.add("timer", label, due,
                         owner=prof.id if prof else None, owner_name=prof.name if prof else None)
    # «conferma» già pronta: senza, il modello a volte ripeteva la richiesta invece di
    # confermarla (prova del 26/09)
    conferma = (f"Va bene, timer {label} avviato: {say_duration(secs)}." if nome
                else f"Va bene, timer {label} avviato.")
    if rearmed:
        conferma = f"Non c'era più un timer da cambiare, quindi ne ho avviato uno {label}."
    out = {"ok": True, "timer": label, "durata": say_duration(secs),
           "scade": say_when(sposta(datetime.datetime.now(), secs)),
           "conferma": conferma,
           "riferimento_agenda": _rif("il timer", label, "timer_imposta", tid)}
    # La scheda di questo timer (identità timer:<id>-<creazione>): un altro timer è un'altra
    return _con_scheda(out, ctx, lambda: schede.timer(ctx.agenda.get(tid)
                                                      or {"id": tid, "label": label, "due": due}))


def _scheda_agenda(ctx, prof):
    """Promemoria e appuntamenti di chi parla: scheda personale."""
    return schede.promemoria(ctx.agenda, prof.id, prof.name) if prof else None


def _promemoria_imposta(ctx: ToolContext, testo: str, quando: str, cambia: str = "") -> dict:
    """Promemoria personale per chi parla, a un'ora detta a voce (o spostato: `cambia`)."""
    prof = _person(ctx)
    if prof is None or ctx.agenda is None:
        return {"ok": False, "errore": "non so chi sei, quindi non posso fissarti un promemoria"}
    if _modo(cambia) == "?":
        return _modo_sbagliato(cambia)
    if _modo(cambia):
        return _sposta(ctx, "promemoria", testo, quando, _modo(cambia), prof,
                       "promemoria_imposta")
    # parse_when non conosce il passato: «ieri alle 9» diventava «oggi alle 9» (analisi del
    # 03/10; per gli appuntamenti e gli spostamenti il controllo c'era già)
    if re.search(r"\b(ieri|scors[oa])\b", str(quando), re.I):
        return {"ok": False, "errore": f"«{quando}» è già passato: non l'ho segnato",
                "cosa_fare": "chiedi il giorno giusto"}
    when = parse_when(str(quando))
    if when is None:
        return {"ok": False, "errore": f"non capisco quando: «{quando}». Chiedi l'ora o fra quanto"}
    if when <= datetime.datetime.now():
        return {"ok": False, "errore": f"{say_when(when)} è già passato: non l'ho segnato",
                "cosa_fare": "chiedi il giorno giusto"}
    what = re.sub(r"^(di|che)\s+", "", (testo or "").strip().rstrip("."), flags=re.I)
    pid = ctx.agenda.add("promemoria", what, when.timestamp(), owner=prof.id,
                         owner_name=prof.name)
    return _con_scheda({"ok": True, "promemoria": what, "quando": say_when(when),
                        "conferma": f"Va bene, {say_when(when)} ti ricordo di {what}.",
                        "riferimento_agenda": _rif("il promemoria", what, "promemoria_imposta",
                                                   pid)},
                       ctx, lambda: _scheda_agenda(ctx, prof))


def _agenda_elenca(ctx: ToolContext) -> dict:
    """Timer attivi e promemoria di chi parla."""
    if ctx.agenda is None:
        return {"ok": False, "errore": "agenda non disponibile"}
    prof = _person(ctx)
    now = time.time()
    out = []
    for it in ctx.agenda.items(prof.id if prof else None):
        if it["kind"] == "timer":
            out.append({"timer": it["label"], "mancano": say_duration(max(0, it["due"] - now))})
        elif it["kind"] == "appuntamento":
            # Solo i prossimi due giorni: per gli altri c'è appuntamenti_elenca
            if it["due"] - now <= 2 * 86400:
                out.append({"appuntamento": it["label"],
                            "quando": say_when(datetime.datetime.fromtimestamp(it["due"]))})
        else:
            out.append({"promemoria": it["label"],
                        "quando": say_when(datetime.datetime.fromtimestamp(it["due"]))})
    res = {"voci": out, "numero": len(out)}

    def cards():
        lst = []
        if any("timer" in v for v in out):
            lst.extend(schede.timer_attivi(ctx.agenda))
        if prof and any("timer" not in v for v in out):
            lst.append(_scheda_agenda(ctx, prof))
        return lst or None
    return _con_scheda(res, ctx, cards)


def _voce_detta(it: dict) -> str:
    """Una voce dell'agenda detta a voce: «il timer per la pasta», «il promemoria di
    chiamare la mamma», «l'appuntamento dal dentista»."""
    label = (it.get("label") or "").strip()
    if it["kind"] == "timer":
        return f"il timer {label}".strip()
    if it["kind"] == "promemoria":
        return f"il promemoria di {label}" if label else "il promemoria"
    return f"l'appuntamento «{label}»" if label else "l'appuntamento"


def _annulla_quale(ctx: ToolContext, cosa: str, prof) -> dict:
    """Niente di annullato (03/10): la richiesta non nomina una voce che c'è. Si dice cosa
    c'è e si chiede quale, invece di annullare la più simile («annulla il dentista» con un
    solo timer delle uova annullava il timer). Con una voce sola la domanda è un'azione in
    sospeso: al «sì» il modello richiama agenda_annulla con quella."""
    items = ctx.agenda.items(prof.id if prof else None)
    q = cosa.lower()
    kinds = {k for k in ("timer", "promemoria", "appuntament") if k in q}
    pool = [it for it in items if any(it["kind"].startswith(k) for k in kinds)] or items
    if not items:
        text = "Non ho annullato niente: non c'è nessun timer, promemoria o appuntamento."
        return {"ok": False, "errore": "non c'è niente da annullare", "conferma": text,
                "risposta_finale": text}
    detto = f"«{cosa.strip()}»" if 0 < len(cosa.strip()) <= 40 else "quello che mi hai detto"
    if len(pool) == 1:
        voce = _voce_detta(pool[0])
        domanda = f"Annullo {voce}?"
        text = f"Non trovo {detto}: c'è solo {voce}. {domanda}"
        return {"ok": False, "fatto": "niente", "errore": f"non trovo {detto}",
                "conferma": text, "risposta_finale": text,
                "in_sospeso": {"tool": "agenda_annulla", "argomenti": {"cosa": pool[0]["label"]},
                               "cosa": f"annullare {voce}", "domanda": domanda}}
    voci = [_voce_detta(it) for it in pool[:4]]
    elenco = ", ".join(voci[:-1]) + " e " + voci[-1]
    text = f"Non ho annullato niente: non trovo {detto}. Ci sono {elenco}: quale annullo?"
    return {"ok": False, "fatto": "niente", "errore": f"non trovo {detto}", "conferma": text,
            "risposta_finale": text}


def _agenda_annulla(ctx: ToolContext, cosa: str) -> dict:
    """Annulla un timer o un promemoria («il timer della pasta», «tutti i timer»)."""
    if ctx.agenda is None:
        return {"ok": False, "errore": "agenda non disponibile"}
    prof = _person(ctx)
    gone = ctx.agenda.cancel(cosa or "", prof.id if prof else None)
    if is_cancel_all(cosa or ""):
        note_rule(ctx, "agenda_tutto")
    if not gone:
        return _annulla_quale(ctx, cosa or "", prof)
    res = {"ok": True, "annullati": [f"{g['kind']} {g['label']}" for g in gone],
           "conferma": "Ho annullato " + " e ".join(_voce_detta(g) for g in gone) + "."}

    def cards():
        # La scheda di ogni timer annullato si aggiorna («annullato alle 23:05») e passa in
        # cima: è la stessa scheda (stessa identità), non una nuova
        lst = [schede.timer(g, "annullato") for g in gone if g["kind"] == "timer"]
        if prof and any(g["kind"] != "timer" for g in gone):
            lst.append(_scheda_agenda(ctx, prof))
        return lst or None
    return _con_scheda(res, ctx, cards)


# ─────────────────────────────── BIBLIOTECA ───────────────────────────────
# Wikipedia italiana offline (calliope/biblioteca.py). Il risultato è compatto (2–3
# passaggi brevi) per non allungare il prompt, con l'istruzione di rispondere in breve
# e non di leggere i passaggi.

def _biblioteca_cerca(ctx: ToolContext, domanda: str) -> dict:
    """Cerca un fatto nella biblioteca offline."""
    if ctx.biblioteca is None:
        return {"ok": False, "errore": "biblioteca non disponibile"}
    # Spiegazione semplice: chi parla è un ragazzo (profilo «giovane») o lo ha chiesto
    prof = _person(ctx)
    asked = re.search(r"\b(in modo semplice|in parole semplici|come a un bambino|"
                      r"come (?:a|per) un ragazzo|semplicemente|facile facile)\b",
                      f"{getattr(ctx, 'user_text', '')} {domanda}", re.I)
    simple = bool(asked) or bool(prof and getattr(prof, "young", False))
    t0 = time.perf_counter()
    found = ctx.biblioteca.cerca(domanda or "", semplice=simple)
    # Un minore (05/10): niente voci per adulti, nemmeno sulla scheda dello schermo
    found = minori.filtra_per_minore(ctx, list(found), lambda p: (p.titolo, p.testo))
    # Nome ambiguo per Wikipedia stessa (la voce principale è una disambiguazione:
    # iperbole, Venere, Mercurio): si risponde sul significato più probabile e si
    # offrono gli altri, invece di sceglierne uno a caso
    # (Non per le citazioni: «una citazione di Dante» non chiede quale Dante)
    asked = getattr(ctx.biblioteca, "richieste", lambda q: set())(domanda or "")
    options = [] if simple or asked else ctx.biblioteca.opzioni(domanda or "")
    options = minori.filtra_per_minore(ctx, list(options), lambda p: (p.titolo, p.testo))
    ms = round((time.perf_counter() - t0) * 1000)
    if options:
        lead = [p for p in found if p.fonte == "Wikizionario"][:1]
        return {"ok": True, "trovato": True, "ambiguo": True, "ms": ms,
                "significati": ([{"nome": f"definizione del dizionario", "testo": p.testo}
                                 for p in lead]
                                + [{"nome": p.titolo, "testo": p.testo} for p in options]),
                "cosa_fare": "La parola ha più significati. Se la conversazione chiarisce "
                             "già quale, rispondi solo su quello. Altrimenti rispondi in 1–2 "
                             "frasi sul significato più comune e poi chiedi in breve se "
                             "intendeva invece un altro, nominandone al massimo due. Non "
                             "leggere l'elenco."}
    if not found:
        # Formulato perché il modello non smetta di usare i tool nei turni dopo
        return {"ok": True, "trovato": False, "ms": ms,
                "cosa_fare": "Nella biblioteca non c'è: rispondi con quello che sai, in "
                             "breve, senza citare Wikipedia, e se non sei sicura dillo."}
    out = {"ok": True, "trovato": True, "ms": ms,
            "passaggi": [{"voce": p.titolo, "fonte": p.fonte, "testo": p.testo} for p in found],
            # «Se non contengono la risposta…»: il 26/09, con passaggi fuori tema su un
            # superlativo, il modello inventava «il lago più grande d'Italia è il lago
            # di Vico, in Calabria» invece di dire Garda, che sapeva
            "cosa_fare": "Se un passaggio risponde proprio alla domanda, rispondi in 1–3 "
                         "frasi con quel dato e cita la fonte in breve («secondo "
                         "Wikipedia…», «secondo il Wikizionario…»), senza leggere i "
                         "passaggi. Se i passaggi parlano d'altro, ignorali: rispondi con "
                         "quello che sai, se ne sei sicura, senza citare fonti."}
    if simple:
        out["stile"] = ("Spiega in modo semplice e chiaro, con parole adatte a un ragazzo "
                        "delle medie, magari con un esempio; niente termini difficili.")
    # Sullo schermo la voce trovata, con un testo più lungo da leggere (la voce dice 1–3 frasi)
    bib = ctx.biblioteca
    return _con_scheda(out, ctx, lambda: schede.biblioteca(
        domanda, found, getattr(bib, "testo_voce", lambda p: "")(found[0])))


def biblioteca_contesto(ctx: ToolContext, domanda: str) -> str:
    """Ricerca fatta dal codice («approfondisci», o una ricerca promessa e non fatta):
    il risultato diventa un messaggio di contesto per il turno, non una chiamata di tool
    che il modello potrebbe decidere di non fare."""
    res = _biblioteca_cerca(ctx, domanda)
    # La scheda va allo schermo, non nel contesto del modello (lì sarebbe testo in più)
    card = res.pop("scheda", None)
    hub = _hub(ctx)
    if card and hub is not None:
        try:
            hub.invia(card, hub.mittente(ctx))
        except Exception as e:  # noqa: BLE001
            print(f"   [SCHERMI] scheda non inviata: {e}", flush=True)
    return (f"Hai appena cercato nella biblioteca la domanda «{domanda}». Risultato: "
            f"{json.dumps(res, ensure_ascii=False)} Rispondi usando questi passaggi, in modo "
            f"più preciso e approfondito di prima (2–4 frasi), citando la fonte in breve. Se "
            f"non contengono la risposta dillo, senza inventare.")


_BIBLIOTECA_SPEC = ToolSpec(
    name="biblioteca_cerca",
    description=("Cerca nella biblioteca offline (Wikipedia italiana) un fatto preciso: "
                 "date, numeri, misure, persone, luoghi, opere, definizioni. Il parametro "
                 "è la domanda, con i nomi propri. Usalo invece di rispondere a memoria "
                 "sui fatti; non serve per conti, ora, opinioni o chiacchiere."),
    parameters={"type": "object",
                "properties": {"domanda": {"type": "string"}},
                "required": ["domanda"]},
    func=_biblioteca_cerca, risk="lettura", levels=ALL,
    # Coprono la seconda passata dell'LLM sui passaggi (~0,3–0,5 s): la ricerca in sé
    # costa ~30 ms. Brevi, e diverse, per non ripetere sempre la stessa.
    announce=("Vediamo.", "Controllo nella biblioteca.", "Un attimo, cerco.",
              "Vediamo cosa dice l'enciclopedia."))


def biblioteca_spec(citazioni: bool = False) -> ToolSpec:
    """Lo spec di biblioteca_cerca; con Wikiquote aperta (Biblioteca.citazioni, 01/10) la
    descrizione nomina anche citazioni e proverbi. Senza Wikiquote resta quella di prima:
    il prefisso del prompt non cambia."""
    if not citazioni:
        return _BIBLIOTECA_SPEC
    return dataclasses.replace(
        _BIBLIOTECA_SPEC,
        description=("Cerca nella biblioteca offline (Wikipedia italiana e Wikiquote) un fatto "
                     "preciso: date, numeri, misure, persone, luoghi, opere, definizioni; "
                     "anche citazioni, aforismi e proverbi («una citazione di…», «chi ha "
                     "detto…?»). Il parametro è la domanda, con i nomi propri. Usalo invece "
                     "di rispondere a memoria sui fatti; non serve per conti, ora, opinioni o "
                     "chiacchiere."))


# ─────────────────────────────── MEMORIA ───────────────────────────────

def _person(ctx: ToolContext):
    """Il profilo di chi parla, o None (ospite: niente memoria)."""
    name = ctx.speaker_ctx.current_speaker
    return ctx.speakers.get(name) if name and ctx.speakers else None


def _yes(value) -> bool:
    """Booleano detto dal modello: True, "true", "sì"…"""
    return value is True or str(value).strip().lower() in ("true", "1", "sì", "si", "yes")


_NO_MEMORY = {"ok": False, "fatto": "NIENTE: la memoria non è disponibile, NON è stato "
                                    "ricordato né tolto niente",
              "errore": "la memoria non è disponibile adesso",
              "risposta_finale": "Adesso la mia memoria non è disponibile, quindi non posso "
                                 "ricordarlo né dimenticarlo."}


# ── La propria data di nascita nel profilo (07/10 pomeriggio, caso vero della DGX) ──
# «Ricordati che il mio compleanno è il 4 luglio del 1977» diventava solo un ricordo; poi
# «quanti anni ho?» → data_calcola(persona=io) falliva (niente nascita nel profilo). Il modello
# decide che il fatto è la data di nascita di chi parla (argomento `nascita` di ricorda); il
# codice propone «Lo salvo anche come tua data di nascita?» e la salva nel profilo solo al
# «sì», nella risposta dopo (come rinomina_interlocutore; chi amministra con la sua voce o la
# frase di sfida). Solo per sé: mai per un minore (la cambia un tutore, minore_gestisci) né
# con una data che renderebbe minorenne un profilo adulto, e solo con l'anno detto.
_NASCITA_DOMANDA = "Lo salvo anche come tua data di nascita?"


def _nascita_profilo(ctx: ToolContext, prof, nascita: str):
    """(data, None) se la data di nascita di chi parla si può proporre per il profilo, oppure
    (None, regola) se no (None, None: niente da fare)."""
    d = minori.leggi_data(nascita)
    if d is None:
        return None, "nascita_non_capita"
    if getattr(prof, "nascita", None) == d.isoformat():
        return None, None
    if minori.e_minore(prof) or minori.fascia_per_eta(minori.eta(d)) is not None:
        return None, "nascita_minore_tutore"
    # Detta dalla persona: in questa conversazione o in un suo ricordo (eta_dal_ricordo)
    detti = [getattr(ctx, "user_text", "") or ""] + [
        t for r, t in (getattr(ctx, "storia", None) or ()) if r == "user"]
    try:
        detti += list(ctx.memory.facts(prof.id)) if ctx.memory is not None else []
    except Exception:  # noqa: BLE001
        pass
    if not any(str(d.year) in t for t in detti):
        return None, "nascita_non_detta"
    return d, None


def _salva_nascita(ctx: ToolContext, prof, fatto: str, nascita: str) -> dict | None:
    """Il «sì» alla proposta: la data nel profilo. None se non c'è una proposta valida."""
    turno = int(getattr(ctx, "turno", 0) or 0)
    offerte = getattr(ctx, "_nascite", None) or {}
    d, _ = _nascita_profilo(ctx, prof, nascita)
    off = offerte.get(prof.id)
    if d is None or not off or off["data"] != d.isoformat() or not _proposta_ok(ctx, off, turno):
        return None
    if getattr(prof, "admin", False):
        sfida = serve_conferma(ctx, "ricorda", {"fatto": fatto, "nascita": nascita},
                               "salvare la tua data di nascita")
        if sfida is not None:
            return sfida
    offerte.pop(prof.id, None)
    prof.nascita = d.isoformat()
    try:
        ctx.speakers.save()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "fatto": NIENTE, "errore": f"profilo non salvato: {e}"}
    note_rule(ctx, "nascita_nel_profilo")
    frase = (f"Fatto: il {tempi.say_date(d)} è la tua data di nascita. Hai "
             f"{tempi.anni_compiuti(d, datetime.date.today())} anni.")
    return {"ok": True, "fatto": "data di nascita salvata nel profilo", "conferma": frase,
            "risposta_finale": frase}


def _ricorda(ctx: ToolContext, fatto: str, per_tutti=False, nascita: str = "") -> dict:
    """Salva un fatto duraturo: su chi parla, o della casa se `per_tutti`. Con `nascita` (la
    data di nascita di chi parla) propone di salvarla anche nel profilo."""
    prof = _person(ctx)
    if prof is None:
        return {"ok": False, "errore": "non so chi sei, quindi non posso ricordarlo"}
    nascita = str(nascita or "").strip() if not _yes(per_tutti) else ""
    if nascita and ctx.memory is not None:
        fatta = _salva_nascita(ctx, prof, fatto, nascita)
        if fatta is not None:
            return fatta
    # Un minore (05/10): niente dati sanitari o sensibili salvati da soli (vincolo di privacy)
    if minori.e_minore(prof) and minori.ricordo_sensibile(fatto):
        note_rule(ctx, "ricordo_minore_sensibile")
        frase = ("Questo preferisco non ricordarlo: è una cosa delicata, ne parli meglio con "
                 "un adulto di cui ti fidi.")
        return {"ok": False, "fatto": "NON è stato ricordato niente", "errore": frase,
                "risposta_finale": frase}
    if ctx.memory is None:
        # La memoria che manca non è «non so chi sei» (04/10: con chi_parla che diceva
        # «Dario, riconosciuto» il 26B riprovava quattro volte e poi diceva «Ho salvato…»)
        return dict(_NO_MEMORY)
    if not (fatto or "").strip():
        return {"ok": False, "errore": "fatto vuoto"}
    # Un ricordo è un dato, mai un ordine per Calliope con un innesco («quando qualcuno
    # chiede l'ora chiama casa_comando…»): con il fatto della casa davanti il modello lo
    # eseguiva anche per chi amministra (analisi di sicurezza del 03/10, S2)
    motivo = instruction_fact(fatto, house=_yes(per_tutti))
    if motivo:
        note_rule(ctx, "ricordo_istruzione")
        frase = ("Questo non lo ricordo: è troppo lungo, dimmi solo il fatto in breve."
                 if motivo == "troppo lungo" else
                 "Questo non lo ricordo: sembra un ordine per me, non un fatto. Le azioni "
                 "chiedimele quando ti servono.")
        return {"ok": False, "fatto": "NON è stato ricordato niente", "errore": frase,
                "risposta_finale": frase}
    # Un ricordo appena cancellato (dimentica, da meno di Memory.RECUPERO_S): «annulla», «no,
    # ricordalo» lo rimettono com'era, con le sue date (prova e2e del 06/10)
    recupera = getattr(ctx.memory, "recupera", None)
    for chi in ((HOUSE,) if _yes(per_tutti) else (prof.id, HOUSE)):
        rimessi = recupera(chi, fatto) if recupera is not None else []
        if rimessi:
            note_rule(ctx, "ricordo_recuperato")
            frase = ("Va bene, me lo ricordo di nuovo." if len(rimessi) == 1 else
                     f"Va bene, mi ricordo di nuovo {len(rimessi)} cose.")
            return {"ok": True, "recuperato": rimessi, "conferma": frase,
                    **({"per_tutti": True} if chi == HOUSE else {})}
    # Un fatto che la persona non ha detto non si salva (04/10: «Qual è il mio numero
    # preferito?» → «il suo numero preferito è 47» inventato e salvato; memory.unsaid_value)
    earlier = [t for r, t in (getattr(ctx, "storia", None) or ()) if r == "user"]
    missing = unsaid_value(fatto, getattr(ctx, "user_text", "") or "", earlier, (prof.name,))
    if missing:
        note_rule(ctx, "ricordo_non_detto")
        domanda = (getattr(ctx, "user_text", "") or "").rstrip().endswith("?")
        frase = ("Questo non me l'hai mai detto, quindi non lo so. Se vuoi, dimmelo e me lo "
                 "ricordo." if domanda else
                 "Non ho capito bene cosa ricordare: me lo ridici?")
        return {"ok": False, "fatto": "NON è stato ricordato niente",
                "errore": f"«{missing}» non l'ha detto la persona: non inventare i fatti",
                "risposta_finale": frase}
    if _yes(per_tutti):
        out = ctx.memory.remember(HOUSE, fatto)
        out["per_tutti"] = True
        out["conferma"] = "Va bene, lo ricorderò per tutta la famiglia."
        return out
    out = ctx.memory.remember(prof.id, fatto)
    d = minori.leggi_data(nascita) if (nascita and out.get("ok")) else None
    proposta = _proponi_nascita(ctx, prof, fatto, d) if d is not None else None
    if nascita and out.get("ok") and d is None:
        note_rule(ctx, "nascita_non_capita")
    if proposta:
        proposta["argomenti"]["nascita"] = nascita       # come detta (il «sì» la ripete)
        frase = f"Me lo ricordo. {_NASCITA_DOMANDA}"
        out.update(conferma=frase, risposta_finale=frase, in_sospeso=proposta,
                   fatto="ricordato; la data di nascita NON è ancora nel profilo")
    return out


def _dimentica(ctx: ToolContext, fatto: str) -> dict:
    """Toglie un fatto ricordato su chi parla («tutto» per cancellarli tutti), oppure,
    se tra i suoi non c'è, un fatto della casa."""
    prof = _person(ctx)
    if prof is None:
        return {"ok": False, "errore": "non so chi sei"}
    if ctx.memory is None:
        return dict(_NO_MEMORY)
    out = ctx.memory.forget(prof.id, fatto or "")
    if not out.get("ok") and (fatto or "").strip().lower() not in ("tutto", "tutti"):
        house = ctx.memory.forget(HOUSE, fatto or "")
        if house.get("ok"):
            house["per_tutti"] = True
            out = house
    if out.get("ok"):
        # Recuperabile per qualche minuto (Memory.recupera, da ricorda): lo si dice
        minuti = max(1, int(getattr(ctx.memory, "RECUPERO_S", 300) // 60))
        cosa = out.get("dimenticato")
        out["conferma"] = ((f"Ho dimenticato che {_ricordo_detto(cosa)}" if cosa else
                            "Ho dimenticato tutto quello che mi avevi detto")
                           + f". Se è stato un errore, dimmi «annulla» entro {minuti} minuti.")
        out["se_annulla"] = (f"se la persona dice «annulla» o «no, ricordalo» entro {minuti} "
                             f"minuti, chiama ricorda con fatto=«{cosa or 'tutto'}»: lo "
                             f"rimetto com'era")
    return out


def _ricordo_detto(testo: str) -> str:
    """Il ricordo dentro una frase («Ho dimenticato che il tuo numero preferito è 47»)."""
    t = str(testo or "").strip().rstrip(".")
    return (t[:1].lower() + t[1:]) if t else "quello che mi avevi detto"


# ─────────────────────────────── LISTE ───────────────────────────────
# Spesa, cose da fare, regali… della casa (liste.py). Conferme già pronte.

def _items_phrase(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " e " + items[-1]


def _lista_aggiungi(ctx: ToolContext, cose: str, lista: str = "spesa") -> dict:
    if ctx.liste is None:
        return {"ok": False, "errore": "liste non disponibili"}
    items = split_items(str(cose))
    if not items:
        return {"ok": False, "errore": "non ho capito cosa aggiungere: chiedi di ripeterlo"}
    prof = _person(ctx)
    key, added, already = ctx.liste.add(lista, items, prof.name if prof else None)
    parts = []
    if added:
        parts.append(f"Ho aggiunto {_items_phrase(added)} {say_list(key, 'a')}.")
    if already:
        parts.append(f"{_items_phrase(already).capitalize()} "
                     f"{"c'era già" if len(already) == 1 else "c'erano già"}.")
    return _con_scheda({"ok": True, "lista": key, "aggiunti": added, "gia_presenti": already,
                        "conferma": " ".join(parts)}, ctx,
                       lambda: schede.lista(key, ctx.liste.read(key)[1], aggiunti=added))


def _lista_leggi(ctx: ToolContext, lista: str = "spesa") -> dict:
    if ctx.liste is None:
        return {"ok": False, "errore": "liste non disponibili"}
    key, items = ctx.liste.read(lista)
    card = lambda: schede.lista(key, items)     # noqa: E731
    if not items:
        return _con_scheda({"ok": True, "lista": key, "voci": [], "numero": 0,
                            "conferma": f"{say_list(key).capitalize()} è vuota."}, ctx, card)
    shown = items[:8]
    more = f" e altre {len(items) - 8}" if len(items) > 8 else ""
    n = "una cosa" if len(items) == 1 else f"{len(items)} cose"
    return _con_scheda({
        "ok": True, "lista": key, "voci": items, "numero": len(items),
        "conferma": f"{say_list(key, 'in').capitalize()} c'è {n}: {_items_phrase(shown)}{more}."
        if len(items) == 1 else
        f"{say_list(key, 'in').capitalize()} ci sono {n}: {_items_phrase(shown)}{more}."},
        ctx, card)


def _lista_togli(ctx: ToolContext, cose: str, lista: str = "spesa") -> dict:
    if ctx.liste is None:
        return {"ok": False, "errore": "liste non disponibili"}
    items = split_items(str(cose)) or [str(cose)]
    key, removed, missing = ctx.liste.remove(lista, items)
    if not removed and not missing:
        return {"ok": True, "lista": key, "tolti": [],
                "conferma": f"{say_list(key).capitalize()} era già vuota."}
    if not removed:
        return {"ok": False, "lista": key, "non_trovati": missing,
                "errore": f"{say_list(key, 'in')} non c'è {_items_phrase(missing)}",
                "cosa_fare": "dillo in breve: non c'era"}
    if re.fullmatch(r"\s*tutt[oiae]( quanto)?\s*", str(cose), re.I):
        conferma = f"Fatto, ho svuotato {say_list(key)}."
    else:
        conferma = f"Ho tolto {_items_phrase(removed)} {say_list(key, 'da')}."
        if missing:
            conferma += f" {_items_phrase(missing).capitalize()} non c'era."
    return _con_scheda({"ok": True, "lista": key, "tolti": removed, "non_trovati": missing,
                        "conferma": conferma}, ctx,
                       lambda: schede.lista(key, ctx.liste.read(key)[1], tolti=removed))


# ─────────────────────────────── APPUNTAMENTI ───────────────────────────────
# Personali, nell'agenda (kind «appuntamento») con un avviso automatico prima.

def _appuntamento_aggiungi(ctx: ToolContext, cosa: str, quando: str, cambia: str = "") -> dict:
    prof = _person(ctx)
    if prof is None or ctx.agenda is None:
        return {"ok": False, "errore": "non so chi sei, quindi non posso segnarti appuntamenti"}
    if _modo(cambia) == "?":
        return _modo_sbagliato(cambia)
    if _modo(cambia):
        return _sposta(ctx, "appuntamento", cosa, quando, _modo(cambia), prof,
                       "appuntamento_aggiungi")
    when = parse_when(str(quando))
    if when is None:
        return {"ok": False, "errore": f"non capisco quando: «{quando}»",
                "cosa_fare": "chiedi il giorno e l'ora"}
    # parse_when prende il primo orario futuro e non conosce il passato: «ieri alle 9»
    # diventerebbe «oggi alle 21»
    if re.search(r"\b(ieri|scors[oa])\b", str(quando), re.I):
        return {"ok": False, "errore": f"«{quando}» è già passato: non l'ho segnato",
                "cosa_fare": "chiedi il giorno giusto"}
    now = datetime.datetime.now()
    if when <= now:
        return {"ok": False, "errore": f"{say_when(when)} è già passato: non l'ho segnato",
                "cosa_fare": "chiedi il giorno giusto"}
    what = re.sub(r"^(ho|il|lo|la|l'|un|una)\s+", "", (cosa or "").strip().rstrip("."),
                  flags=re.I) or "appuntamento"
    aid = ctx.agenda.add("appuntamento", what, when.timestamp(),
                         owner=prof.id, owner_name=prof.name)
    lead = int(getattr(ctx.cfg, "appuntamento_anticipo_min", 60) or 0)
    reminder = sposta(when, -lead * 60)              # un'ora vera prima (ora legale)
    if lead > 0 and reminder > now:
        ctx.agenda.add("avviso", what, reminder.timestamp(),
                       owner=prof.id, owner_name=prof.name, parent=aid)
        # «1 ora» la voce lo legge «uno ora»
        ahead = "un'ora" if lead == 60 else say_duration(lead * 60)
        avviso = f" Te lo ricordo {ahead} prima."
    else:
        avviso = ""
    return _con_scheda({"ok": True, "appuntamento": what, "quando": say_when(when),
                        "conferma": f"Segnato: {what}, {say_when(when)}.{avviso}",
                        "riferimento_agenda": _rif("l'appuntamento", what,
                                                   "appuntamento_aggiungi", aid)},
                       ctx, lambda: _scheda_agenda(ctx, prof))


def _appuntamenti_elenca(ctx: ToolContext, quando: str = "") -> dict:
    """Gli appuntamenti del periodo e, nella stessa frase, i promemoria del periodo e i timer
    attivi (04/10: a «Cosa ho in agenda?» il 26B chiamava solo questo tool e rispondeva «non
    hai appuntamenti» con un timer e due promemoria attivi)."""
    prof = _person(ctx)
    if prof is None or ctx.agenda is None:
        return {"ok": False, "errore": "non so chi sei, quindi non conosco i tuoi appuntamenti"}
    start, end, label = parse_day_range(str(quando or ""))
    t0, t1 = start.timestamp(), end.timestamp()
    found = ctx.agenda.appointments(prof.id, t0, t1)
    now = time.time()
    anche = []
    for it in ctx.agenda.items(prof.id):
        if it["kind"] == "timer" and t0 <= now <= t1:
            anche.append(f"{_voce_detta(it)}, che suona tra "
                         f"{say_duration(max(0, it['due'] - now))}")
        elif it["kind"] == "promemoria" and t0 <= it["due"] < t1:
            anche.append(f"{_voce_detta(it)}, "
                         f"{say_when(datetime.datetime.fromtimestamp(it['due']))}")
    poi = f" Hai anche {'; '.join(anche)}." if anche else ""
    if not found:
        res = {"ok": True, "appuntamenti": [], "quando": label,
               "conferma": f"{label.capitalize()} non hai appuntamenti.{poi}"}
        if anche:
            res["anche"] = anche
            return _con_scheda(res, ctx, lambda: _scheda_agenda(ctx, prof))
        return res
    one_day = (end - start).total_seconds() <= 86400
    voci = []
    for it in found:
        due = datetime.datetime.fromtimestamp(it["due"])
        # In un giorno solo il giorno l'ha già detto la conferma: basta l'ora
        when = (f"alle {due.hour}" + (f" e {due.minute}" if due.minute else "") if one_day
                else say_when(due))
        voci.append(f"{it['label']} {when}")
    res = {"ok": True, "appuntamenti": voci, "quando": label,
           "conferma": f"{label.capitalize()} hai: {_items_phrase(voci)}.{poi}"}
    if anche:
        res["anche"] = anche
    return _con_scheda(res, ctx, lambda: _scheda_agenda(ctx, prof))


# ─────────────────────────────── REGISTRO ───────────────────────────────


_SPECS = [
    ToolSpec(
        name="chi_parla",
        # «adesso», «solo»: il 26/09 a «Chi era Mercurio?» rispondeva «Chi ti sta
        # parlando è Dario», confondendo le domande su persone con chi_parla
        description=("Dice SOLO chi sta parlando con Calliope in questo momento: il nome e se "
                     "la voce è stata riconosciuta. Usalo per «sai chi sono?», «chi ti "
                     "parla?». Non serve per domande su personaggi, storia o mitologia."),
        parameters={"type": "object", "properties": {}, "required": []},
        func=_chi_parla, risk="lettura", levels=ALL),
    ToolSpec(
        name="elenca_voci",
        # «Non conosci i loro nomi»: senza, a metà conversazione il modello rispondeva
        # a «che voci hai?» inventando «Sofia, Marco e Giulia» (prova del 26/09)
        description=("Elenca le voci con cui Calliope può parlare. Non conosci i loro "
                     "nomi: per rispondere a qualunque domanda sulle voci chiamalo sempre, "
                     "non inventarli. A voce citane al massimo tre o quattro."),
        parameters={"type": "object", "properties": {}, "required": []},
        func=_elenca_voci, risk="lettura", levels=ALL),
    ToolSpec(
        name="ora_attuale",
        description="Restituisce l'ora locale adesso.",
        parameters={"type": "object", "properties": {}, "required": []},
        func=_ora_attuale, risk="lettura", levels=ALL),
    ToolSpec(
        name="data_oggi",
        description="Restituisce la data di oggi: giorno della settimana e data.",
        parameters={"type": "object", "properties": {}, "required": []},
        func=_data_oggi, risk="lettura", levels=ALL),
    ToolSpec(
        name="calcola",
        description=("Calcola in modo esatto un'espressione aritmetica. Usalo per OGNI conto "
                     "(moltiplicazioni, divisioni, percentuali, potenze, radici), mai a mente. "
                     "L'espressione è in cifre con + - * / ** e parentesi; funzioni sqrt, "
                     "sin, cos, tan (in gradi), log, ln, exp, abs, round, fattoriale; "
                     "costanti pi ed e. «per» è una moltiplicazione, «diviso» una "
                     "divisione. Esempi: «17 per 6» → «17*6», «300 miliardi per 2748» → "
                     "«300e9*2748», "
                     "«il 15 per cento di 80» → «80*15/100», «2 alla decima» → «2**10», "
                     "«radice di 144» → «sqrt(144)». Nella risposta usa il campo da_dire."),
        parameters={"type": "object",
                    "properties": {"espressione": {"type": "string"}},
                    "required": ["espressione"]},
        func=_calcola, risk="lettura", levels=ALL),
    ToolSpec(
        name="data_calcola",
        description=("Conti con le date, esatti: anni compiuti (età), giorni che mancano a "
                     "una data o passati da una data, giorno della settimana di una data, "
                     "distanza tra due date. Le date come dette («4 luglio 1977», «25 "
                     "dicembre», «Natale», «domani»): la data di oggi la sa il programma, "
                     "non passarla. Età e compleanno di chi parla («quanti anni ho?») o di "
                     "una persona di casa («quanti anni ha Bianca?», «quando è il compleanno "
                     "di Bianca?»): persona, senza data; la data di nascita la prende il "
                     "programma dal profilo, non chiederla prima. Per le date usa questo, "
                     "non calcola. Nella risposta usa il campo da_dire."),
        parameters={"type": "object",
                    "properties": {
                        "cosa": {"type": "string", "enum": list(_COSE_DATE)},
                        "data": {"type": "string",
                                 "description": "la data come detta, con l'anno se detto"},
                        "data2": {"type": "string",
                                  "description": "solo per una distanza tra due date o per "
                                                 "l'età a un'altra data; vuoto = oggi"},
                        "persona": {"type": "string",
                                    "description": "«io» per chi parla, o il nome di una "
                                                   "persona registrata: età (eta) e giorni "
                                                   "al compleanno (giorni_mancanti)"}},
                    "required": ["cosa"]},
        func=_data_calcola, risk="lettura", levels=ALL),
    ToolSpec(
        name="elenca_utenti",
        description=("Le persone della casa registrate (familiari, non i clienti): per "
                     "ognuna se ha l'impronta della voce (impronta_voce: se Calliope la "
                     "riconosce quando parla), se è minorenne e, a chi può saperli, età e "
                     "compleanno. Per «chi è registrato?», «Bianca è registrata?», «mi "
                     "riconosci la voce di Bianca?». La rubrica dell'ufficio (clienti, "
                     "fornitori) è un'altra cosa: anagrafica_cerca."),
        parameters={"type": "object", "properties": {}, "required": []},
        func=_elenca_utenti, risk="lettura", levels=FAMILY),
    ToolSpec(
        name="cambia_voce",
        description=("Cambia la voce con cui Calliope parla alla persona corrente (voce: un "
                     "nome breve tra quelle installate, vedi elenca_voci; «scarica la voce "
                     "di…» è installa_proponi) oppure il tono delle risposte («parlami "
                     "in modo più formale», «sii più ironica», «rispondi in modo "
                     "essenziale», «torna normale»: tono). Con per_tutti=true il tono vale "
                     "per tutta la casa. Per passare a un'altra modalità o tornare alla "
                     "normale («modalità Star Trek», «modalità normale»): modalita."),
        parameters={"type": "object",
                    "properties": {"voce": {"type": "string"},
                                   "tono": {"type": "string",
                                            "enum": ["normale", "formale", "amichevole",
                                                     "ironico", "essenziale",
                                                     "computer_di_bordo"]},
                                   "per_tutti": {"type": "boolean"},
                                   "modalita": {"type": "string",
                                                "enum": ["normale", "startrek"]}},
                    "required": []},
        func=_cambia_voce, risk="azione", levels=FAMILY),
    ToolSpec(
        name="rinomina_interlocutore",
        description=("Cambia il nome con cui Calliope chiama la persona che sta "
                     "parlando adesso. Usalo quando qualcuno dice come si chiama o "
                     "chiede di essere chiamato in un altro modo («d'ora in poi chiamami "
                     "Davide»): chiamalo subito, senza chiedere tu se ne è sicura, perché "
                     "la domanda di conferma la fa il tool. Il nome cambia solo se la "
                     "persona dice di sì: allora richiamalo con lo stesso nome."),
        parameters={"type": "object",
                    "properties": {"nome": {"type": "string"}},
                    "required": ["nome"]},
        func=_rinomina_interlocutore, risk="azione", levels=FAMILY),
    ToolSpec(
        name="registra_utente",
        description=("Avvia la registrazione della voce di una persona nuova («aggiungi un "
                     "familiare», «registra mia figlia Bianca»). nascita: la data di nascita "
                     "come detta; maggiorenne: true se è adulto e la data non serve; tutori: "
                     "chi si occupa di un minore, se li nomina."),
        parameters={"type": "object",
                    "properties": {"nome": {"type": "string"},
                                   "nascita": {"type": "string"},
                                   "maggiorenne": {"type": "boolean"},
                                   "tutori": {"type": "string"}},
                    "required": ["nome"]},
        # Dal 05/10 solo chi amministra, con la voce e la frase di sfida (_nuovo_profilo). Il
        # primo utente della casa si registra senza tool, dal ciclo principale.
        func=_registra_utente, risk="azione", levels=ADMIN),
    # Timer e promemoria. «Ricordami di…» è un promemoria; «ricordati che…» è memoria.
    ToolSpec(
        name="timer_imposta",
        description=("Avvia un timer, o cambia quello già messo (cambia). La durata va "
                     "passata con le parole dette, senza "
                     "convertirla: «mezz'ora», «10 minuti», «un'ora e un quarto». Il nome è "
                     "facoltativo, per esempio «della pasta»."),
        parameters={"type": "object",
                    "properties": {"durata": {"type": "string"},
                                   "nome": {"type": "string"},
                                   "cambia": {"type": "string", "enum": list(_CAMBIA),
                                              "description": _CAMBIA_DESC}},
                    "required": ["durata"]},
        func=_timer_imposta, risk="azione", levels=ALL),
    ToolSpec(
        name="promemoria_imposta",
        description=("Fissa un promemoria per chi parla: «ricordami di… alle/tra/domani…». "
                     "Il testo è cosa ricordare; quando va passato con le parole dette, "
                     "senza convertirlo: «tra 20 minuti», «alle 18», «domani alle 9». "
                     "Non è ricorda, che salva fatti su chi parla. Sposta anche un promemoria "
                     "già messo (cambia)."),
        parameters={"type": "object",
                    "properties": {"testo": {"type": "string"},
                                   "quando": {"type": "string"},
                                   "cambia": {"type": "string", "enum": list(_CAMBIA),
                                              "description": _SPOSTA_DESC}},
                    "required": ["testo", "quando"]},
        func=_promemoria_imposta, risk="azione", levels=FAMILY),
    ToolSpec(
        name="agenda_elenca",
        description=("Elenca timer attivi, promemoria e appuntamenti vicini di chi parla, con "
                     "quanto manca: «cosa ho in agenda?», «che timer ci sono?», «i miei "
                     "promemoria»."),
        parameters={"type": "object", "properties": {}, "required": []},
        func=_agenda_elenca, risk="lettura", levels=ALL),
    ToolSpec(
        name="agenda_annulla",
        description=("Annulla un timer, un promemoria o un appuntamento. Il parametro lo "
                     "descrive: «il timer della pasta», «il promemoria delle 18», «il "
                     "dentista», «tutti i timer»."),
        parameters={"type": "object",
                    "properties": {"cosa": {"type": "string"}},
                    "required": ["cosa"]},
        func=_agenda_annulla, risk="azione", levels=ALL),
    # Appuntamenti: personali, con un avviso automatico prima (Config.appuntamento_anticipo_min)
    ToolSpec(
        name="appuntamento_aggiungi",
        description=("Segna un appuntamento di chi parla: «martedì alle 17 ho il dentista». "
                     "Cosa è l'appuntamento («dentista»); quando va passato con le parole "
                     "dette, senza convertirlo: «martedì alle 17», «domani alle 9 e mezza». "
                     "Per «ricordami di…» usa promemoria_imposta. Sposta anche un appuntamento "
                     "già segnato (cambia)."),
        parameters={"type": "object",
                    "properties": {"cosa": {"type": "string"},
                                   "quando": {"type": "string"},
                                   "cambia": {"type": "string", "enum": list(_CAMBIA),
                                              "description": _SPOSTA_DESC}},
                    "required": ["cosa", "quando"]},
        func=_appuntamento_aggiungi, risk="azione", levels=FAMILY),
    ToolSpec(
        name="appuntamenti_elenca",
        description=("Elenca gli appuntamenti di chi parla (con i promemoria del periodo e "
                     "i timer attivi): «cosa ho domani?», «cosa ho martedì?», «questa "
                     "settimana». Il parametro è il giorno con le parole dette; vuoto = i "
                     "prossimi 7 giorni. Nella risposta usa la conferma. Per metterli sullo "
                     "schermo usa schermo_mostra."),
        parameters={"type": "object",
                    "properties": {"quando": {"type": "string"}},
                    "required": []},
        func=_appuntamenti_elenca, risk="lettura", levels=FAMILY),
    # Liste della casa, condivise dalla famiglia (niente per gli ospiti)
    ToolSpec(
        name="lista_aggiungi",
        description=("Aggiunge una o più cose a una lista della casa: «aggiungi latte e uova "
                     "alla lista della spesa». Cose separate da virgola o «e»; lista è il "
                     "nome («spesa» se non è detto, «cose da fare», «regali»…)."),
        parameters={"type": "object",
                    "properties": {"cose": {"type": "string"},
                                   "lista": {"type": "string"}},
                    "required": ["cose"]},
        func=_lista_aggiungi, risk="azione", levels=FAMILY),
    ToolSpec(
        name="lista_leggi",
        description=("Legge una lista della casa: «cosa c'è nella lista della spesa?». "
                     "Nella risposta usa la conferma."),
        parameters={"type": "object",
                    "properties": {"lista": {"type": "string"}},
                    "required": []},
        func=_lista_leggi, risk="lettura", levels=FAMILY),
    ToolSpec(
        name="lista_togli",
        description=("Toglie cose da una lista della casa: «ho preso il pane», «togli le "
                     "uova». cose=«tutto» svuota la lista («svuota la lista della spesa»)."),
        parameters={"type": "object",
                    "properties": {"cose": {"type": "string"},
                                   "lista": {"type": "string"}},
                    "required": ["cose"]},
        func=_lista_togli, risk="azione", levels=FAMILY),
    # Memoria: niente per gli ospiti (privacy), ognuno vede solo i propri fatti; quelli
    # «per tutti» sono della casa e li vede tutta la famiglia
    ToolSpec(
        name="ricorda",
        description=("Salva per sempre un fatto, da ricordare anche nelle prossime "
                     "conversazioni. Usalo quando ti chiedono di ricordare qualcosa o ti "
                     "dicono qualcosa di importante e duraturo. Il fatto è una frase breve e "
                     "completa, per esempio «il suo numero preferito è 47». per_tutti: true "
                     "se è un'informazione della casa utile a tutta la famiglia (wifi, "
                     "caldaia, dove sono le cose); false se riguarda chi parla. nascita: "
                     "solo se il fatto è la data di nascita o il compleanno con l'anno di chi "
                     "parla, la data come detta («4 luglio 1977»); mai per altre persone."),
        parameters={"type": "object",
                    "properties": {"fatto": {"type": "string"},
                                   "per_tutti": {"type": "boolean"},
                                   "nascita": {"type": "string"}},
                    "required": ["fatto"]},
        func=_ricorda, risk="azione", levels=FAMILY),
    ToolSpec(
        name="dimentica",
        description=("Cancella un fatto ricordato su chi parla, quando chiede di "
                     "dimenticarlo. Il parametro descrive il fatto; «tutto» li cancella "
                     "tutti."),
        parameters={"type": "object",
                    "properties": {"fatto": {"type": "string"}},
                    "required": ["fatto"]},
        func=_dimentica, risk="azione", levels=FAMILY),
]


def build_registry(biblioteca: bool = False, pc: dict | None = None,
                   pc_ospite: bool = False, documenti=None, casa: bool | None = None,
                   casa_ospite: bool = False, pc_nome: str | None = None,
                   installa: bool = True, citazioni: bool = False,
                   schermi: bool = False, agenti: bool = False,
                   agenti_modelli=(), ufficio=(), archivio: bool = False,
                   web=None, conversazioni: bool = False,
                   immagini: dict | None = None,
                   minori_tool: bool = False, allegati: bool = False,
                   cassetto: bool = False) -> ToolRegistry:
    """Costruisce il registro dei tool nativi di Calliope.

    `biblioteca_cerca` si registra solo se la biblioteca c'è: un tool che risponde
    sempre «non installata» avvelenerebbe la conversazione (vedi CLAUDE.md). Per lo
    stesso motivo i tool pc_* ci sono solo con i PC (`pc`: {nome: PCExecutor}, da
    calliope.pc.load_pc), e solo per le capacità che hanno; `pc_ospite` lascia volume e
    musica anche agli ospiti (Config.pc_ospite_volume_media). `documenti` sono i formati
    disponibili («word», «excel», «pdf»: Documenti.formati) e registra documento_crea e
    documento_modifica; None o vuoto = niente documenti.

    `casa`: None = niente tool della casa (casa_enabled spento, o le prove che non la
    usano); False = solo casa_integrazione (indirizzo o token mancanti: spiega cosa
    manca); True = anche casa_comando e casa_stato. `casa_ospite` li lascia agli ospiti
    per i domini di casa_ospite_domini. `pc_nome` serve alla descrizione di casa_comando.

    `calliope_stato` c'è sempre (registro delle capacità, 01/10); `installa` aggiunge i tool
    delle installazioni (installa_proponi, installa_avvia, installa_gestisci): ci sono anche
    nelle prove, così il prompt misurato è quello vero; senza il servizio rispondono «spente».

    `schermi`: schermo_mostra e schermo_gestisci (calliope/schermi/, 02/10), con il server
    delle schede acceso. Le schede automatiche dei tool non dipendono da questi due tool.

    `agenti`: lavoro_affida, lavoro_stato e lavoro_annulla (calliope/agenti/, 02/10), con un
    agente configurato (dgx.yaml o agenti_url); `agenti_modelli` sono i nomi dei modelli di
    documento (template) che l'agente sa compilare.

    `ufficio`: i nomi dei modelli che modello_compila sa compilare (calliope/ufficio/, 03/10);
    registra modello_compila, anagrafica_cerca e anagrafica_salva. Vuoto = niente ufficio.
    `archivio`: archivio_cerca, archivio_scadenze e archivio_somma (calliope/archivio/, 03/10),
    con la cartella dei documenti di casa configurata.
    `web`: web_cerca (calliope/web/, 03/10), con SearXNG configurato e raggiungibile; il valore
    è la Config (per web_livello) o True per i livelli predefiniti.
    `immagini`: i tool delle foto (calliope/tools/immagini.py, 05/10), {storia, pc,
    archivio}; None = le foto sono spente o il modello non le vede.
    `allegati`: i tool dei file allegati (calliope/tools/allegati.py, 05/10): allegato_leggi,
    allegato_archivia con l'archivio, e il parametro `allegato` di lavoro_affida.
    `cassetto` (08/10, calliope/cassetto.py): con gli allegati, il cassetto dei file per persona
    (allegato_leggi con `cassetto` e `di`, cassetto_gestisci).
    `minori_tool`: compiti_aiuto e minore_gestisci (calliope/tools/minori.py, 05/10), con
    almeno un profilo minorenne in casa (il prefisso degli altri non cambia finché non c'è).
    """
    reg = ToolRegistry()
    for spec in _SPECS:
        reg.register(spec)
    if biblioteca:
        reg.register(biblioteca_spec(citazioni))      # `citazioni`: c'è Wikiquote
    if web:
        from .web import web_spec
        reg.register(web_spec(None if web is True else web))
    if pc:
        from .pc import pc_specs
        for spec in pc_specs(pc, pc_ospite, documenti=bool(documenti), agenti=bool(agenti)):
            reg.register(spec)
    if documenti:
        from .documenti import documenti_specs
        for spec in documenti_specs(documenti, agenti=bool(agenti)):
            reg.register(spec)
    # La città di casa detta a voce (09/10, calliope/luogo.py): c'è sempre, anche senza casa
    from .casa import luogo_spec
    reg.register(luogo_spec())
    if casa is not None:
        from .casa import casa_specs
        for spec in casa_specs(bool(casa), casa_ospite,
                               pc_nome=pc_nome or (next(iter(pc)) if pc else None)):
            reg.register(spec)
    if schermi:
        from .schermi import schermi_specs
        for spec in schermi_specs():
            reg.register(spec)
    if archivio:
        from .archivio import archivio_specs
        for spec in archivio_specs():
            reg.register(spec)
    if agenti:
        from .agenti import agenti_specs
        file_pc = bool(pc) and any("ricerca" in getattr(ex, "capacita_possibili",
                                                        ex.capacita)() for ex in pc.values())
        for spec in agenti_specs(documenti or (), agenti_modelli, file_pc=file_pc,
                                 archivio=archivio, allegati=allegati):
            reg.register(spec)
        # La modalità sviluppo (08/10, calliope/sviluppo.py): l'iter di estensioni e programmi
        from .sviluppo import sviluppo_specs
        for spec in sviluppo_specs(file_pc=file_pc, allegati=bool(allegati)):
            reg.register(spec)
    if ufficio:
        from .ufficio import ufficio_specs
        for spec in ufficio_specs(ufficio):
            reg.register(spec)
    if conversazioni:
        # conversazione_cerca e conversazioni_dimentica (05/10, calliope/conversazioni.py)
        from .conversazioni import conversazioni_specs
        for spec in conversazioni_specs():
            reg.register(spec)
    if immagini is not None:
        from .immagini import immagini_specs
        for spec in immagini_specs(**immagini):
            reg.register(spec)
    if allegati:
        from .allegati import allegati_specs
        for spec in allegati_specs(archivio=archivio, cassetto=cassetto):
            reg.register(spec)
    if minori_tool:
        from .minori import minori_specs
        for spec in minori_specs():
            reg.register(spec)
    from .stato import stato_specs
    for spec in stato_specs(installa):
        reg.register(spec)
    return reg
