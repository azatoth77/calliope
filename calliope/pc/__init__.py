"""
Controllo dei PC di casa a voce (docs/ricerche/2026-09-26-controllo-pc.md).

Due esecutori dietro la stessa interfaccia `PCExecutor` (base.py):
- in processo (windows.py): il PC su cui gira Calliope, se è Windows;
- remoto (remoto.py, 03/10): con audio_modo: satellite (Calliope sulla DGX) il PC del
  satellite, comandato sulla connessione del satellite (calliope/satellite/esecutore.py).
I tool pc_* sono in calliope/tools/pc.py.
"""

from .base import CAPACITA, COMANDI_MEDIA, TIPI_FILE, PCExecutor

__all__ = ["CAPACITA", "COMANDI_MEDIA", "TIPI_FILE", "PCExecutor", "load_pc"]


def load_pc(cfg, satelliti=None) -> dict[str, PCExecutor] | None:
    """Gli esecutori dei PC, per nome («portatile»), o None se il controllo è spento o
    non si può fare. Come la biblioteca: se manca, i tool pc_* semplicemente non ci sono,
    e all'avvio si dice perché.

    Con `satelliti` (il server dei satelliti, audio_modo: satellite) il PC è quello del
    satellite: un esecutore remoto, sempre presente con pc_enabled (i tool non cambiano
    quando il satellite va e viene); senza satellite collegato i tool lo dicono."""
    from .. import capacita
    if satelliti is not None:
        if not getattr(cfg, "pc_enabled", False):
            capacita.REGISTRO.da_dict(capacita.check_pc(cfg))
            return None
        from .remoto import RemotePCExecutor
        executor = RemotePCExecutor(satelliti, cfg.pc_nome, list(cfg.pc_app or {}),
                                    cfg.pc_risultati, cfg.pc_remoto_timeout_s)
        capacita.REGISTRO.da_dict(capacita.check_pc(cfg, satelliti))
        capacita.REGISTRO.dinamica("pc", lambda: capacita.check_pc(cfg, satelliti))
        return {cfg.pc_nome: executor}
    check = capacita.controlla_una(cfg, "pc")
    if not getattr(cfg, "pc_enabled", False) or check["stato"] == "mancante":
        capacita.REGISTRO.da_dict(check)
        return None
    from .windows import LocalWindowsExecutor, available
    reason = available()
    if reason:
        capacita.segnala("pc", "mancante", reason, check["prossimo_passo"])
        return None
    pip = ("pip install pycaw comtypes pywin32 psutil screen_brightness_control "
           "winrt-Windows.Media.Control")
    try:
        executor = LocalWindowsExecutor(cfg.pc_nome, cfg.pc_app, cfg.pc_risultati,
                                        webcam=getattr(cfg, "pc_webcam", ""))
    except Exception as e:  # noqa: BLE001 — il PC è un di più: Calliope parte comunque
        capacita.segnala("pc", "guasta", f"{type(e).__name__}: {e}",
                         "Guarda il terminale di Calliope all'avvio; se manca una libreria: "
                         f"{pip}.")
        return None
    caps = executor.capacita()
    det = {"nome": cfg.pc_nome, "capacita": list(caps),
           "app": executor.app_disponibili() if "app" in caps else [],
           "mancanti": dict(executor.mancanti), "app_tolte": list(executor.app_scartate)}
    if not caps:
        executor.close()
        capacita.segnala("pc", "mancante", "nessuna capacità disponibile",
                         f"Vanno installate le librerie: {pip}.", det)
        return None
    notes = [f"{', '.join(caps)}"]
    if executor.mancanti:
        notes.append("manca: " + ", ".join(executor.mancanti))
    if executor.app_scartate:
        notes.append("app non installate tolte: " + ", ".join(executor.app_scartate))
    capacita.segnala("pc", "attiva", "; ".join(notes),
                     f"Per il resto: {pip}." if executor.mancanti else "", det)
    return {cfg.pc_nome: executor}
