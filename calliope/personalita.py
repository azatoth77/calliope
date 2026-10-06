"""
Tono di voce della casa e delle persone (04/10, docs/ricerche/2026-10-04-personalita-wake-word.md).

- Il tono **della casa** sta nel prompt di sistema (Config.tono, config.TONI): cambia di rado,
  quindi la cache del prefisso di Ollama si rifà una volta sola. Si sceglie in calliope.yaml
  (o con `modalita: startrek`) oppure a voce da chi amministra («d'ora in poi parla a tutti
  in modo formale»): quello detto a voce si salva in `personalita.json` accanto a
  calliope.yaml e vince sul file, finché non si cambia di nuovo.
- La **modalità** (05/10, «passa alla modalità Star Trek»): wake word, suoni e tono insieme,
  scelta a voce da chi amministra e salvata nello stesso file (calliope/modalita.py).
- Il tono **di una persona** si salva nel suo profilo (speakers.json, come la voce
  preferita) e arriva al modello nei messaggi subito prima della domanda (Brain._tone_message),
  mai nel prompt: così quando parla un'altra persona il prefisso resta in cache.
"""
from __future__ import annotations

import datetime
import os

from .config import TONI, nome_tono

FILE = "personalita.json"


def percorso(cfg) -> str:
    return os.path.join(getattr(cfg, "config_dir", None) or os.getcwd(), FILE)


def _leggi(cfg, log=print) -> dict | None:
    from .persistenza import FileRovinato, leggi_json
    try:
        dati, _ = leggi_json(percorso(cfg))
    except FileRovinato as e:
        log(f"[TONO] {FILE} non si legge ({e}): uso il tono e la modalità di calliope.yaml")
        return None
    return dati if isinstance(dati, dict) else None


def _piu_recente(cfg) -> bool:
    """personalita.json è più recente dei file di configurazione? Vince il più recente: se
    dopo il cambio a voce qualcuno ha scritto nei file (un tono, una modalità), vale il file."""
    try:
        detto = os.path.getmtime(percorso(cfg))
        base = getattr(cfg, "config_dir", None) or os.getcwd()
        scritti = [os.path.getmtime(p) for p in (os.path.join(base, "calliope.yaml"),
                                                 os.path.join(base, "calliope.locale.yaml"))
                   if os.path.exists(p)]
    except OSError:
        return False
    return not scritti or max(scritti) <= detto


def carica_tono_casa(cfg, log=print) -> str | None:
    """La modalità (05/10) e il tono della casa scelti a voce (personalita.json), applicati a
    `cfg` prima che si preparino wake word, Whisper e voce. Restituisce il tono, o None se non
    c'è (vale quello del file di configurazione) o se il file non si legge."""
    dati = _leggi(cfg, log)
    if not dati or not _piu_recente(cfg):
        return None
    if "modalita" in dati:
        from .config import cambia_modalita
        prima = cfg.modalita
        try:
            n = cambia_modalita(cfg, dati.get("modalita"))
            if (prima or None) != cfg.modalita:
                log(f"[MODALITÀ] Scelta a voce: {n} ({FILE})")
        except ValueError as e:
            log(f"[MODALITÀ] {FILE}: {e}")
    tono = nome_tono(dati.get("tono"))
    if tono is None:
        return None
    if tono != nome_tono(cfg.tono):
        log(f"[TONO] Tono della casa scelto a voce: {TONI[tono]['detto']} ({FILE})")
    cfg.tono = tono
    return tono


def _salva(cfg, campi: dict):
    from .persistenza import scrivi_json
    dati = {}
    try:
        dati = _leggi(cfg, log=lambda *_: None) or {}
    except Exception:  # noqa: BLE001
        dati = {}
    if not _piu_recente(cfg):
        dati = {}                     # quello vecchio non valeva più: si riparte dal file
    dati.update(campi)
    dati["quando"] = datetime.datetime.now().isoformat(timespec="seconds")
    scrivi_json(percorso(cfg), dati)


def salva_tono_casa(cfg, tono: str, chi: str | None = None):
    """Cambia il tono della casa adesso (il prossimo prompt di sistema) e lo salva."""
    cfg.tono = tono
    _salva(cfg, {"tono": tono, "da": chi})


def salva_modalita(cfg, modalita: str, tono_fuori: str | None, chi: str | None = None):
    """Salva la modalità scelta a voce (già applicata a `cfg`), con il tono della casa che
    vale adesso e quello da rimettere tornando alla normale (`tono_fuori`)."""
    _salva(cfg, {"modalita": modalita, "tono": nome_tono(cfg.tono) or "normale",
                 "tono_fuori_modalita": tono_fuori, "da": chi})


def tono_fuori_modalita(cfg) -> str | None:
    """Il tono della casa da rimettere tornando alla modalità normale (personalita.json)."""
    dati = _leggi(cfg, log=lambda *_: None) or {}
    return nome_tono(dati.get("tono_fuori_modalita")) if _piu_recente(cfg) else None
