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
(`ammesso`):

1. con una classe nella tabella di Calliope (`politica.CLASSI`): mai un tool registrato a
   runtime o senza classe, che vale «pericoloso»;
2. di classe «azione» (per definizione della politica: cambia lo stato di Calliope in modo
   reversibile e della persona) o «sicuro» senza una fonte non fidata (il risultato del tocco va
   nella storia del modello senza busta);
3. con un effetto (`valore.effetto`) al più E2: E3 è «esce di casa, esegue codice o non si
   disfa», E4 fiducia e sicurezza fisica;
4. fuori da `politica.IRREVERSIBILI`.

Si controlla tre volte: all'import di questo modulo (`controlla`: un tocco nuovo su un tool non
ammesso ferma l'avvio e le prove), in `prepara` (con gli argomenti veri) e nel ciclo prima di
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
from dataclasses import dataclass
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


# ─────────────────────────── il vincolo (#262) ───────────────────────────

def ammesso(tool: str, argomenti: dict | None = None, spec=None) -> str | None:
    """None se un tocco può chiamare `tool` con questi argomenti; altrimenti il motivo."""
    from .. import politica, valore
    if tool not in politica.CLASSI:
        return f"«{tool}» non ha una classe nella tabella della politica"
    cl = politica.classe_di(tool, spec)
    if cl.classe == politica.SICURO:
        if politica.fonte_di(tool, spec):
            return f"«{tool}» legge dati non fidati"
    elif cl.classe != politica.AZIONE:
        return f"«{tool}» è di classe «{cl.classe}», non reversibile"
    if valore.effetto(tool, dict(argomenti or {}), spec) > valore.E2:
        return f"«{tool}» ha un effetto che non si disfa (oltre E2)"
    if tool in politica.IRREVERSIBILI:
        return f"«{tool}» è tra le azioni irreversibili"
    return None


def controlla(elenco=None) -> list[str]:
    """I tocchi dell'elenco (di serie `TOCCHI`) il cui tool non è ammesso: [«tocco: motivo»]."""
    errori = []
    for nome, t in (TOCCHI if elenco is None else elenco).items():
        motivo = ammesso(t.tool)
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
    # toglierebbe altro (o niente). Si chiede di dirlo a voce, dove il modello sceglie
    if split_items(voce) != [voce.strip(" .!?")] or _TUTTO.fullmatch(voce):
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


TOCCHI = {"spunta_lista": Tocco("lista_togli", _spunta_lista),
          "timer_piu": Tocco("timer_imposta", _timer_piu, bersaglio=True),
          "timer_ferma": Tocco("agenda_annulla", _timer_ferma, bersaglio=True)}

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
