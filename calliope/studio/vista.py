"""
La vista aperta dello Studio nei dati del turno (30/10/2026, passo 4.5, issue #284; progetto
docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md § 0, punto 2: «Calliope sa cosa c'è sullo
schermo»).

La pagina dello schermo personale manda la sua vista dello Studio a ogni cambio
(`POST /api/vista`, al più una al secondo): {vista, verifica?, pagina?}. Il server tiene l'ultima
per schermo, in memoria, con l'ora (`Viste`), con la chiave `(id, creato)` dello schermo. Il
«al più una al secondo» è della pagina; il server ne accetta al più 60 al minuto per schermo. Nei dati del turno entra una riga corta **solo se**
chi parla è riconosciuto (o parla dal suo dispositivo personale), un suo schermo personale è
collegato e ha una vista dello Studio di meno di `VISTA_S` secondi: «Sul suo schermo è aperta la
verifica 12 (Storia, il 5/11): il piano.». La scrive il codice dagli id e dal db
(`Studio.riga_vista`), mai dal testo delle pagine né dai titoli degli argomenti; è un dato, non un
ordine (principio 10). Sta nei dati del turno, che cambiano a ogni turno: il prefisso resta
stabile (#95). Nel registro dei turni solo la regola `studio_vista`, mai la vista.
"""
from __future__ import annotations

import threading
import time

VISTA_S = 600.0
TIPI = ("home", "piano", "argomenti", "pagine", "pagina", "sessione")


def valida(dati) -> dict | None:
    """La vista mandata dalla pagina, controllata: {vista, verifica?, pagina?} o None (anche
    `{"vista": None}` per «lo Studio non è più aperto»)."""
    if not isinstance(dati, dict):
        return None
    tipo = dati.get("vista")
    if tipo is None:
        return {"vista": None}
    if tipo not in TIPI:
        return None
    out = {"vista": tipo}
    for k in ("verifica", "pagina"):
        v = dati.get(k)
        if v is None:
            continue
        if not isinstance(v, int) or isinstance(v, bool) or not 0 < v < 10 ** 9:
            return None
        out[k] = v
    return out


def chiave(schermo: dict) -> tuple:
    """La chiave di uno schermo per la vista: (id, creato), come le sessioni (revisione della PR
    #317): uno schermo revocato e un altro con lo stesso numero non si passano la vista."""
    return (schermo.get("id"), schermo.get("creato"))


class Viste:
    """L'ultima vista dello Studio per schermo, in memoria (mai su disco)."""

    def __init__(self, orologio=time.monotonic):
        self._d: dict = {}
        self._lock = threading.Lock()
        self.orologio = orologio

    def metti(self, schermo_id, vista: dict | None):
        with self._lock:
            if not vista or vista.get("vista") is None:
                self._d.pop(schermo_id, None)
            else:
                self._d[schermo_id] = (dict(vista), self.orologio())

    def di(self, schermo_id, entro_s: float = VISTA_S) -> tuple[dict, float] | None:
        with self._lock:
            x = self._d.get(schermo_id)
        if x is None or self.orologio() - x[1] > entro_s:
            return None
        return x

    def togli(self, schermo_id):
        with self._lock:
            self._d.pop(schermo_id, None)


def riga(ctx, studio) -> str:
    """La riga della vista aperta per i dati del turno, o "": vedi il docstring del modulo."""
    if studio is None or not studio.per_modello():
        return ""
    hub = getattr(ctx, "schermi", None)
    viste = getattr(hub, "viste_studio", None)
    if viste is None or not hasattr(hub, "abbinati"):
        return ""
    from ..tools.studio import chi_di
    try:
        chi = chi_di(ctx)
        if chi is None:
            return ""
        m = hub.mittente(ctx)
        if getattr(m, "persona", None) != getattr(chi, "id", None):
            return ""
        from .. import dispositivo
        if not getattr(m, "certo", False) and not dispositivo.proprio(ctx, m):
            return ""
        migliore = None
        for s in hub.abbinati():
            if s.get("proprietario") != chi.id or not hub.collegato(s["id"]):
                continue
            x = viste.di(chiave(s))
            if x is not None and (migliore is None or x[1] > migliore[1]):
                migliore = x
        return studio.riga_vista(chi, migliore[0]) if migliore else ""
    except Exception:  # noqa: BLE001 — nel dubbio la riga non c'è
        return ""
