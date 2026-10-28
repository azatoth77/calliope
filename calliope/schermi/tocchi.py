"""
I tocchi che cambiano qualcosa dallo schermo personale (28/10, passo 2a di
docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md, decisione 10 del progetto e decisione 1
del 28/10 nell'issue #241; issue #256; timer e vincolo nel passo 2b, #257 e #262).

Un tocco vale come una frase della persona: passa da `ToolRegistry.call` come la voce (permessi,
livello, minori; con `identified_by="schermo"` i tool che vogliono la voce restano rifiutati) ed
entra nella conversazione come un turno. Si fa **sempre** dallo schermo personale, anche fuori
da una conversazione cominciata a voce (decisione di chi amministra del 28/10).

L'elenco è chiuso (`TOCCHI`): la pagina non sceglie il tool né gli argomenti liberi, manda solo
il tipo di tocco e i dati che servono, che qui si controllano contro lo stato vero. I tocchi:

- `spunta_lista`: la spunta della lista («ho preso il latte») → `lista_togli`;
- `timer_piu`: «+1 minuto» sulla scheda del timer → `timer_imposta` con `cambia` «aggiungi»;
- `timer_ferma`: «Ferma» sulla scheda del timer → `agenda_annulla`.

**Il vincolo** (#262, nota 9 della revisione della PR #261). Il tocco gira senza la politica del
turno (non c'è una frase da cui possa venire un dato non fidato, e gli argomenti li scrive il
codice): la politica ferma solo i tool vietati. Perciò un tocco può chiamare solo un tool
(`ammesso`) dell'elenco in positivo `TOCCABILI` (#266), ognuno con la riga che dice perché è
sicuro, reversibile e senza danno se toccato per sbaglio, e mai uno di `ESCLUSI` (`dimentica`,
le catture, la rubrica, la richiesta al tutore, la risposta all'agente e ciò che vuole la voce).
Le tabelle della politica da sole ne ammettevano 46 su 80. Come difesa in più restano le
condizioni di prima (`_condizioni`):

1. con una classe nella tabella di Calliope (`politica.CLASSI`): mai un tool registrato a
   runtime o senza classe, che vale «pericoloso»;
2. di classe «azione» (per definizione della politica: cambia lo stato di Calliope in modo
   reversibile e della persona) o «sicuro»;
3. senza una fonte non fidata, per tutte e due le classi (#266: il risultato del tocco va nella
   storia del modello senza busta);
4. con un effetto (`valore.effetto`) al più E2: E3 è «esce di casa, esegue codice o non si
   disfa», E4 fiducia e sicurezza fisica;
5. fuori da `politica.IRREVERSIBILI`;
6. con lo `ToolSpec` del registro, aperto ai familiari (un tool solo per chi amministra vuole la
   sua voce).

Si controlla tre volte: all'import di questo modulo (`controlla`: un tocco nuovo su un tool non
ammesso, un toccabile che è anche escluso o che non passa le condizioni ferma l'avvio e le
prove), in `prepara` (con gli argomenti veri) e nel ciclo prima di
`ToolRegistry.call` (`non_ammesso`, con lo `ToolSpec` del registro, e il tool dev'essere quello
dichiarato per quel tocco).

«Ferma» (`agenda_annulla`) è «azione» ed E2, quindi ammesso. Criterio scritto (#257): fermare un
timer di casa si disfa con una frase («rimetti il timer di 3 minuti»), come annullarlo a voce, e
dal tocco si ferma sempre un timer solo, quello toccato (`tocco_bersaglio`), mai «tutti».

**Il contesto del turno di prima** (#262). Il ciclo azzera per il tocco e rimette dopo i segni di
chi parlava (`speaker_ctx`, compreso il satellite da cui parlava) e del contesto dei tool la
politica, la frase, la proposta in sospeso (`tool_in_sospeso`), il «sì» già dato
(`politica_accettata`) e il gioco che aspetta un comando (`gioco_turno`). La stanza nel contesto
dei tool è il servizio della conversazione di stanza, non un dato del turno, e nessun tool
ammesso la legge.
"""

import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable

from ..liste import say_list, split_items

_MAX_TESTO = 80
# Le forme che per lista_togli svuotano la lista (liste.Liste.remove)
_TUTTO = re.compile(r"\s*(tutto|tutta|tutte|tutti|tutto quanto)\s*", re.I)
# L'identità della scheda del timer (schede.chiave_timer): timer:<id>-<creato in ms>
_CHIAVE_TIMER = re.compile(r"timer:(\d{1,12})-(\d{1,16})")


def _testo(v, massimo=_MAX_TESTO) -> str | None:
    if not isinstance(v, str):
        return None
    t = re.sub(r"\s+", " ", v).strip()
    return t if 0 < len(t) <= massimo else None


@dataclass(frozen=True)
class Tocco:
    """Un tocco dell'elenco chiuso: il tool che chiama (dichiarato, per il vincolo) e la
    funzione che dai dati della pagina e dallo stato vero fa gli argomenti."""
    tool: str
    prepara: Callable
    # Il tocco agisce su un oggetto scelto dal codice (il timer toccato: ToolContext.tocco_bersaglio).
    # Senza, il tool sceglierebbe dal testo, e agenda_annulla potrebbe annullare «tutti»
    # (revisione della PR #265): il ciclo lo rifiuta (`senza_bersaglio`)
    bersaglio: bool = False


# ─────────────────────────── il vincolo (#262, #266) ───────────────────────────

@dataclass(frozen=True)
class Toccabile:
    """Un tool che un tocco può chiamare: perché è sicuro, reversibile e senza danno se toccato
    per sbaglio, e se il tocco deve dire su che cosa agisce (`Tocco.bersaglio`)."""
    perche: str
    bersaglio: bool = False


# L'elenco in positivo (#266, revisione della PR #265): le tabelle della politica da sole
# ammettevano 46 tool su 80, `dimentica`, `pc_guarda` e `anagrafica_salva` compresi. Un tool
# entra qui solo con la sua riga; un tocco su un tool che non c'è ferma l'import (l'avvio e le
# prove). Le condizioni della politica (`_condizioni`) restano, come difesa in più
TOCCABILI: Mapping[str, Toccabile] = MappingProxyType({
    "lista_togli": Toccabile(
        "la spunta di una voce che c'è adesso nella lista (controllata in `prepara`, una cosa sola, "
        "mai «tutto»): si rimette con «aggiungi il latte», resta in casa, e per sbaglio costa una "
        "voce da riscrivere"),
    "timer_imposta": Toccabile(
        "«+1 minuto» sul timer toccato, che c'è ancora: allunga un timer di casa di un minuto, si "
        "ferma con «Ferma» o a voce, e per sbaglio costa un minuto in più", bersaglio=True),
    "agenda_annulla": Toccabile(
        "«Ferma» sul timer toccato e solo su lui (il bersaglio, mai «tutti» né un promemoria): si "
        "rimette a voce, la scheda lo mostra subito fermato, e per sbaglio costa un timer da "
        "rimettere (criterio scritto del 28/10, #257)", bersaglio=True),
})

# Gli esclusi in modo esplicito (#266): ammessi dalle sole tabelle della politica, o vicini a
# un tocco che verrà, ma con un danno se toccati per sbaglio, o che vogliono la voce. Un tool non
# può essere in tutti e due gli elenchi (controllato all'import)
ESCLUSI: dict[str, str] = {
    "dimentica": "cancella un ricordo: non si rimette uguale, e un tocco per sbaglio lo perde",
    "conversazioni_dimentica": "cancella conversazioni dall'archivio: non si disfa",
    "pc_guarda": "cattura dello schermo o foto con la webcam: guarda nella stanza o nel PC",
    "immagine_guarda": "guarda una foto (anche una cattura): il risultato entra nella storia",
    "anagrafica_salva": "scrive nella rubrica dell'ufficio dati di altre persone",
    "anagrafica_cerca": "legge la rubrica dell'ufficio: dati di altre persone nella storia",
    "richiesta_tutore": "manda una richiesta al tutore: un messaggio a un'altra persona",
    "lavoro_rispondi": "risponde all'agente al lavoro: la risposta cambia ciò che costruisce",
    "lavoro_annulla": "ferma un lavoro dell'agente: non si riprende da dove era",
    "cambia_voce": "cambia la modalità di Calliope per tutti: vuole la voce",
    "citta_casa_salva": "cambia la città della casa per tutti",
    "registra_utente": "aggiunge una persona: vuole la voce di chi amministra",
    "minore_gestisci": "cambia i permessi di un minore: vuole la voce del tutore",
    "conoscenti": "salva o toglie le voci di fuori casa: vuole la voce di chi amministra",
    "conoscente_livello": "cambia il livello di un conoscente: vuole la voce di chi amministra",
    "installa_proponi": "propone un'installazione: vuole la voce di chi amministra",
    "installa_avvia": "installa dal catalogo: esce di casa e vuole la voce",
    "installa_gestisci": "annulla o cambia un'installazione: vuole la voce",
    "modello_compila": "compila un documento dell'ufficio: vuole la voce",
    "sviluppo_apri": "apre la modalità sviluppo: vuole la voce di chi amministra",
}


def _condizioni(tool: str, argomenti: dict | None = None, spec=None) -> str | None:
    """Le condizioni della politica (#262), dopo l'elenco: None se passano; altrimenti il
    motivo. La fonte non fidata vale per ogni classe (#266): il risultato del tocco va nella
    storia del modello senza busta, anche quello di un'«azione»."""
    from .. import politica, valore
    if tool not in politica.CLASSI:
        return f"«{tool}» non ha una classe nella tabella della politica"
    cl = politica.classe_di(tool, spec)
    if cl.classe not in (politica.SICURO, politica.AZIONE):
        return f"«{tool}» è di classe «{cl.classe}», non reversibile"
    if politica.fonte_di(tool, spec):
        return f"«{tool}» legge dati non fidati"
    if valore.effetto(tool, dict(argomenti or {}), spec) > valore.E2:
        return f"«{tool}» ha un effetto che non si disfa (oltre E2)"
    if tool in politica.IRREVERSIBILI:
        return f"«{tool}» è tra le azioni irreversibili"
    # Con lo ToolSpec del registro (il ciclo): un tool che i familiari non possono usare vuole
    # la voce di chi amministra; per i minori e gli altri livelli decide ToolRegistry.call
    livelli = getattr(spec, "levels", None)
    if livelli is not None and "familiare" not in livelli:
        return f"«{tool}» non è per i familiari: vuole la voce di chi amministra"
    return None


def ammesso(tool: str, argomenti: dict | None = None, spec=None) -> str | None:
    """None se un tocco può chiamare `tool` con questi argomenti; altrimenti il motivo:
    escluso, fuori dall'elenco `TOCCABILI`, o una condizione della politica che non passa."""
    if tool in ESCLUSI:
        return f"«{tool}» è escluso dai tocchi: {ESCLUSI[tool]}"
    if tool not in TOCCABILI:
        return f"«{tool}» non è nell'elenco dei tool toccabili"
    return _condizioni(tool, argomenti, spec)


def controlla(elenco=None, toccabili=None) -> list[str]:
    """Gli errori dell'elenco dei tocchi (di serie `TOCCHI`) e di `TOCCABILI`: un tocco su un
    tool non ammesso, un tool che vuole il bersaglio in un tocco che non ce l'ha, un toccabile
    escluso o che non passa le condizioni. [«nome: motivo»]."""
    errori = []
    tocc = TOCCABILI if toccabili is None else toccabili
    for nome in sorted(set(tocc) & set(ESCLUSI)):
        errori.append(f"{nome}: è sia toccabile sia escluso")
    for nome in tocc:
        motivo = _condizioni(nome)
        if motivo:
            errori.append(f"{nome}: {motivo}")
    for nome, t in (TOCCHI if elenco is None else elenco).items():
        motivo = (f"«{t.tool}» è escluso dai tocchi: {ESCLUSI[t.tool]}" if t.tool in ESCLUSI
                  else f"«{t.tool}» non è nell'elenco dei tool toccabili" if t.tool not in tocc
                  else _condizioni(t.tool))
        if not motivo and tocc[t.tool].bersaglio and not t.bersaglio:
            motivo = f"«{t.tool}» si tocca solo con un bersaglio"
        if motivo:
            errori.append(f"{nome}: {motivo}")
    return errori


def senza_bersaglio(scritto: dict) -> bool:
    """Il tocco vuole un bersaglio (`Tocco.bersaglio`) e non ce l'ha: il controllo del ciclo,
    con la sua regola (`tocco_senza_bersaglio`)."""
    t = TOCCHI.get(str((scritto or {}).get("tocco") or ""))
    b = (scritto or {}).get("bersaglio")
    return bool(t and t.bersaglio) and not (isinstance(b, dict) and b.get("timer") is not None
                                            and b.get("chiave"))


def non_ammesso(scritto: dict, spec=None) -> str | None:
    """Il controllo del ciclo prima di `ToolRegistry.call`: il tocco è dell'elenco, il tool è
    quello dichiarato per lui ed è ammesso con questi argomenti e lo `ToolSpec` del registro.
    None se va bene; altrimenti il motivo."""
    t = TOCCHI.get(str((scritto or {}).get("tocco") or ""))
    if t is None:
        return "tocco sconosciuto"
    tool = str(scritto.get("tool") or "")
    if tool != t.tool:
        return f"il tocco «{scritto.get('tocco')}» chiama «{t.tool}», non «{tool}»"
    return ammesso(tool, scritto.get("argomenti") or {}, spec)


# ─────────────────────────── la spunta della lista ───────────────────────────

def _spunta_lista(dati: dict, fonti) -> dict:
    """La spunta di una voce della lista: «lista_togli» con quella voce. La voce deve esserci
    adesso nella lista (la pagina può essere rimasta indietro). La scheda taglia le voci lunghe
    a 80 caratteri con «…» (schede._taglia): allora vale l'unica voce che comincia così."""
    liste = getattr(fonti, "liste", None)
    if liste is None:
        return {"errore": "Le liste non sono disponibili.", "_stato": 503}
    lista, voce = _testo(dati.get("lista"), 60), _testo(dati.get("voce"))
    if lista is None or voce is None:
        return {"errore": "dati non validi", "_stato": 400}
    key, voci = liste.read(lista)
    if voce not in voci and voce.endswith("…"):
        simili = [v for v in voci if v.startswith(voce[:-1].rstrip())]
        voce = simili[0] if len(simili) == 1 else voce
    if voce not in voci:
        return {"errore": f"«{voce}» non c'è più nella lista.", "_stato": 409}
    # lista_togli divide le cose su virgole e «e» e svuota la lista con «tutto»: una voce così
    # toglierebbe altro (o niente). Si chiede di dirlo a voce, dove il modello sceglie. «Tutto»
    # come lo vede lista_togli: dopo split_items, senza la punteggiatura («tutto.», #266)
    pezzi = split_items(voce)
    if pezzi != [voce.strip(" .!?")] or any(_TUTTO.fullmatch(p) for p in pezzi + [voce]):
        return {"errore": "Questa voce si toglie a voce: dimmi che cosa togliere dalla lista.",
                "_stato": 422}
    return {"tool": "lista_togli", "argomenti": {"cose": voce, "lista": key},
            "descrizione": f"(Ho tolto «{voce}» {say_list(key, 'da')} toccando lo schermo.)"}


# ─────────────────────────── i tasti del timer (#257) ───────────────────────────

def _timer_toccato(dati: dict, fonti) -> tuple[dict | None, dict | None]:
    """(timer, None) per la scheda toccata, o (None, errore). Il timer deve esserci ancora, essere
    un timer (della casa: gli altri tipi dell'agenda sono personali) e avere la stessa identità
    della scheda (SQLite riusa gli id: `schede.chiave_timer` ha anche l'istante di creazione)."""
    from . import schede
    agenda = getattr(fonti, "agenda", None)
    if agenda is None:
        return None, {"errore": "L'agenda non è disponibile.", "_stato": 503}
    chiave = _testo(dati.get("chiave"), 40)
    m = _CHIAVE_TIMER.fullmatch(chiave or "")
    if m is None:
        return None, {"errore": "dati non validi", "_stato": 400}
    it = agenda.get(int(m.group(1)))
    if (it is None or it.get("kind") != "timer" or schede.chiave_timer(it) != chiave
            or float(it.get("due") or 0) <= time.time()):
        return None, {"errore": "Questo timer non c'è più: è già suonato o è stato fermato.",
                      "_stato": 409}
    return it, None


def _detto(it: dict) -> str:
    label = str(it.get("label") or "").strip()
    return f"il timer {label}" if label else "il timer"


def _timer_piu(dati: dict, fonti) -> dict:
    """«+1 minuto»: `timer_imposta` con «aggiungi» sul timer toccato (il bersaglio, non il nome:
    con due timer senza nome il tool sceglierebbe l'ultimo messo)."""
    it, errore = _timer_toccato(dati, fonti)
    if errore:
        return errore
    return {"tool": "timer_imposta",
            "argomenti": {"durata": "1 minuto", "nome": str(it.get("label") or ""),
                          "cambia": "aggiungi"},
            "bersaglio": {"timer": it["id"], "chiave": dati["chiave"].strip()},
            "descrizione": f"(Ho aggiunto un minuto al{_detto(it)[2:]} toccando lo schermo.)"}


def _timer_ferma(dati: dict, fonti) -> dict:
    """«Ferma»: `agenda_annulla` sul timer toccato, solo lui."""
    it, errore = _timer_toccato(dati, fonti)
    if errore:
        return errore
    return {"tool": "agenda_annulla", "argomenti": {"cosa": _detto(it)},
            "bersaglio": {"timer": it["id"], "chiave": dati["chiave"].strip()},
            "descrizione": f"(Ho fermato {_detto(it)} toccando lo schermo.)"}


# Immutabile a runtime (#266, revisione della PR #270): un tocco nuovo si aggiunge qui nel codice,
# dove lo vede il controllo dell'import, mai dopo
TOCCHI = MappingProxyType({"spunta_lista": Tocco("lista_togli", _spunta_lista),
                           "timer_piu": Tocco("timer_imposta", _timer_piu, bersaglio=True),
                           "timer_ferma": Tocco("agenda_annulla", _timer_ferma, bersaglio=True)})

# All'avvio: un tocco su un tool non ammesso non arriva mai a girare
_ERRORI = controlla()
if _ERRORI:
    raise RuntimeError("tocchi non ammessi (schermi/tocchi.py): " + "; ".join(_ERRORI))


def prepara(dati, fonti) -> dict:
    """Dal corpo della richiesta della pagina ({tocco, …}) al tool da chiamare:
    {tool, argomenti, descrizione, bersaglio?} o {errore, _stato}."""
    if not isinstance(dati, dict):
        return {"errore": "dati non validi", "_stato": 400}
    t = TOCCHI.get(str(dati.get("tocco") or ""))
    if t is None:
        return {"errore": "tocco sconosciuto", "_stato": 400}
    out = t.prepara(dati, fonti)
    if "errore" in out:
        return out
    motivo = (f"chiama «{out.get('tool')}» invece di «{t.tool}»" if out.get("tool") != t.tool
              else ammesso(t.tool, out.get("argomenti")))
    if not motivo and t.bersaglio and not isinstance(out.get("bersaglio"), dict):
        motivo = "senza bersaglio"
    if motivo:
        return {"errore": "Questo tocco non è ammesso: chiedimelo a voce.", "_stato": 403,
                "motivo": motivo}
    return out
