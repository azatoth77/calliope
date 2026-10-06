"""
Calliope che mostra cose su uno schermo (fase 1 di docs/ricerche/2026-10-01-mappe-e-schermi.md).

Un piccolo server web in LAN (Starlette + uvicorn, in un thread) serve una pagina da tenere
aperta in kiosk su un PC, un tablet o una TV. Gli schermi si abbinano con un codice di 6
cifre detto a Calliope; poi ricevono le **schede** (liste, timer, voci della biblioteca,
anteprime dei documenti, stato della casa, calcoli) create dal codice dei tool nel momento
in cui il tool finisce. La voce non aspetta mai lo schermo.

  archivio.py   schermi abbinati e codici in attesa (SQLite, solo libreria standard)
  hub.py        chi riceve cosa: stanza, livello, visibilità; consegna senza bloccare
  schede.py     le schede, costruite dal codice
  server.py     Starlette + uvicorn (unica parte con dipendenze), SSE verso la pagina
  pagina/       la pagina kiosk: HTML, CSS e JS locali, niente CDN né font esterni
  __main__.py   python -m calliope.schermi: elenco, abbinamento, revoca, kiosk

Punti d'aggancio per le fasi dopo: `Mittente.stanza` (la stanza del satellite che ha
sentito la frase), la scheda `mappa` (fase 2: basta un tipo nuovo in schede.py e nella
pagina; i file PMTiles andranno serviti con le Range da server.py), gli schermi personali
dei PC con l'esecutore (fase 4: un abbinamento come gli altri, con `proprietario`).
"""

import socket

from .. import capacita
from . import tls
from .archivio import ArchivioSchermi, cifre, norm_stanza
from .hub import Mittente, Schermi, destinatari, mittente_da

__all__ = ["ArchivioSchermi", "Mittente", "Schermi", "cifre", "destinatari", "load_schermi",
           "mittente_da", "norm_stanza", "url_schermi"]


def ip_lan() -> str | None:
    """L'indirizzo di questo PC nella rete di casa. Il socket UDP «collegato» non manda
    pacchetti: serve solo a farsi dire dal sistema quale interfaccia userebbe."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        return None if ip.startswith("127.") or ip == "0.0.0.0" else ip
    except OSError:
        return None
    finally:
        s.close()


def url_schermi(cfg, port: int | None = None, https: bool | None = None) -> str:
    """L'indirizzo da aprire sugli schermi: https in rete con il certificato (tls.py)."""
    host = str(getattr(cfg, "schermi_indirizzo", "127.0.0.1") or "127.0.0.1")
    port = port or int(getattr(cfg, "schermi_porta", 8770))
    if https is None:
        try:
            https = tls.modo(cfg)[0] == "https"
        except ValueError:
            https = False
    if host in ("0.0.0.0", "::", ""):
        host = ip_lan() or "127.0.0.1"
    if ":" in host:
        host = f"[{host}]"
    return f"{'https' if https else 'http'}://{host}:{port}"


def solo_locale(cfg) -> bool:
    return tls.solo_locale(cfg)


def load_schermi(cfg, db_path: str, log=print) -> Schermi | None:
    """Il registro degli schermi con il server già acceso, oppure None (spento, librerie
    mancanti, porta occupata): Calliope parte uguale, e lo dice il registro delle capacità."""
    if not getattr(cfg, "schermi_enabled", False):
        capacita.REGISTRO.da_dict(capacita.check_schermi(cfg))
        return None
    if not (capacita.presente("starlette") and capacita.presente("uvicorn")):
        capacita.REGISTRO.da_dict(capacita.check_schermi(cfg))
        return None
    try:
        from .server import ServerSchermi
    except Exception as e:  # noqa: BLE001 — una libreria che non si carica su questa macchina
        capacita.segnala("schermi", "mancante", f"starlette o uvicorn non si caricano "
                         f"({type(e).__name__})", "Vanno reinstallate nell'ambiente di "
                         "Calliope: " + capacita.comando_libreria("starlette uvicorn",
                                                                  "schermi") + ".")
        return None
    host = str(getattr(cfg, "schermi_indirizzo", "127.0.0.1") or "127.0.0.1")
    port = int(getattr(cfg, "schermi_porta", 8770))
    # In rete: HTTPS con il certificato, o niente (02/10: il token della pagina viaggiava
    # in chiaro sulla rete dell'ufficio). Su 127.0.0.1 resta http
    try:
        modo, certificato = tls.modo(cfg)
    except ValueError as e:
        capacita.segnala("schermi", "guasta", str(e), "Rifai il certificato: python -m "
                         "calliope.satellite --certificato --forza (poi i satelliti vanno "
                         "abbinati di nuovo), e riavviami.", {"indirizzo": host, "porta": port})
        return None
    if modo == "rifiuta":
        capacita.segnala("schermi", "da_configurare", "in rete senza certificato: la pagina "
                         "non parte in chiaro", tls.PASSO_CERTIFICATO,
                         {"indirizzo": host, "porta": port})
        return None
    if modo == "http" and not tls.solo_locale(cfg):
        log(f"   [SCHERMI] ATTENZIONE: la pagina è in rete senza HTTPS (schermi_senza_tls): "
            f"il token degli schermi passa in chiaro. Per l'HTTPS: python -m "
            f"calliope.satellite --certificato")
    archivio = ArchivioSchermi(db_path, getattr(cfg, "schermi_codice_min", 10.0))
    hub = Schermi(cfg, archivio, log=log)
    hub.tls = certificato
    try:
        srv = ServerSchermi(hub, host, port, tls=certificato).avvia()
    except OSError as e:
        archivio.close()
        capacita.segnala("schermi", "guasta", f"la porta {port} non si apre ({e.strerror or e})",
                         "Un altro programma usa la porta: in calliope.locale.yaml cambia "
                         "schermi_porta e riavviami.", {"indirizzo": host, "porta": port})
        return None
    except Exception as e:  # noqa: BLE001
        archivio.close()
        capacita.segnala("schermi", "guasta", f"il server non parte ({type(e).__name__})",
                         "Guarda il terminale di Calliope: python -m calliope.stato.",
                         {"errore": str(e)})
        return None
    hub.server = srv
    hub.url = url_schermi(cfg, srv.port, https=certificato is not None)
    capacita.REGISTRO.da_dict(capacita.check_schermi(cfg, hub))
    capacita.REGISTRO.dinamica("schermi", lambda: capacita.check_schermi(cfg, hub))
    # Abbinamenti che non si collegano da giorni (05/10): si dicono, non si tolgono
    from .archivio import avviso_inattivi
    giorni = float(getattr(cfg, "schermi_inattivi_giorni", 7.0) or 0)
    riga = avviso_inattivi(archivio.inattivi(giorni), "schermi", giorni,
                           "calliope schermi --revoca")
    if riga:
        log(f"   [SCHERMI] {riga}")
    return hub
