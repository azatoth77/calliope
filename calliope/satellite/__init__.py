"""
Satelliti: microfono e casse in rete, Calliope altrove (02/10/2026, rapporto
docs/ricerche/2026-10-02-satellite.md).

Calliope gira sulla DGX (in ufficio, in VPN; domani a casa, in LAN) e il portatile diventa
un satellite: microfono, casse e schermo. Un WebSocket che apre il satellite, PCM 16 kHz,
JSON per i comandi; wake word, VAD e riproduzione sul satellite, tutto il resto sul server.

  protocollo.py   messaggi e audio (lo importano entrambi i lati)
  archivio.py     satelliti abbinati e codici in attesa (come gli schermi, stesso file)
  server.py       dentro Calliope: ServerSatelliti, AscoltoRemoto (il Listener remoto),
                  UscitaRemota (dove Speaker manda le frasi)
  client.py       il satellite: Satellite, Riproduttore
  inoltro.py      sul satellite, facoltativo (satellite_inoltro): inoltro TCP grezzo verso la
                  pagina degli schermi del server, per il telefono nella rete di casa o in
                  WireGuard quando il server è altrove (TLS da capo a capo)
  esecutore.py    sul satellite Windows: l'esecutore del PC (richieste pc_* del server con
                  LocalWindowsExecutor, documenti ricevuti nella cartella Calliope dei Documenti)
  __main__.py     python -m calliope.satellite: avvia il satellite; sul server abbina,
                  revoca, elenca, crea il certificato
  web.py          un PC nuovo con un comando (03/10): pagina /satellite (schermi) e
                  /installa (porta dei satelliti), script, manifesto, pacchetto
  pacchetto.py    il pacchetto del satellite dalla versione in uso (zip deterministico,
                  requisiti da uv.lock), annunciato nel benvenuto
  aggiorna.py     sul satellite installato: scarica e prepara la versione del server
  installazione/  avvio.py (avvio con aggiornamenti e ritorno indietro, solo stdlib) e
                  installa.ps1 (lo script del comando della pagina)

L'esecutore remoto del PC (03/10, protocollo 2; docs/ricerche/2026-09-26-controllo-pc.md §5)
usa la stessa connessione autenticata e la stessa direzione (il PC si collega al server):
lato server è calliope/pc/remoto.py (RemotePCExecutor) e RemoteDelivery
(calliope/documenti/consegna.py).
"""

from .. import capacita

__all__ = ["RilevatoreRemoto", "load_satelliti"]


class RilevatoreRemoto:
    """Al posto del rilevatore della wake word nel ciclo principale: la wake word gira sul
    satellite. Basta che non sia None (main.py decide il barge-in e il secondo stadio)."""

    def reset(self):
        pass

    def process(self, frame):           # pragma: no cover — non si chiama mai qui
        return None


def load_satelliti(cfg, db_path: str, log=print):
    """Il server dei satelliti già acceso, oppure (None, motivo) — senza satelliti Calliope
    con audio_modo: satellite non sente niente, e main si ferma con il motivo."""
    if not capacita.presente("websockets"):
        capacita.REGISTRO.da_dict(capacita.check_satellite(cfg))
        return None, ("manca la libreria websockets: "
                      + capacita.comando_libreria("websockets", "casa"))
    from .archivio import ArchivioSatelliti
    from .server import ServerSatelliti
    archivio = ArchivioSatelliti(db_path, cfg.satellite_codice_min)
    srv = ServerSatelliti(cfg, archivio, log=log)
    try:
        srv.avvia()
    except (OSError, ValueError) as e:
        archivio.close()
        motivo = (f"la porta {cfg.satellite_porta} non si apre ({e.strerror or e})"
                  if isinstance(e, OSError) else str(e))
        passo = ("Un altro programma usa la porta: cambia satellite_porta in "
                 "calliope.locale.yaml." if isinstance(e, OSError) else
                 "Sul server: python -m calliope.satellite --certificato, poi riavviami "
                 "(oppure satellite_senza_tls: true, solo come ultima scelta).")
        capacita.segnala("satellite", "guasta", motivo, passo)
        return None, f"{motivo}. {passo}"
    if srv.ssl is None and not srv.host.startswith("127.") and srv.host not in ("localhost",
                                                                                "::1"):
        log("[SATELLITE] ATTENZIONE: ascolto in rete senza TLS (satellite_senza_tls): audio "
            "e token viaggiano in chiaro. Crea il certificato con python -m calliope.satellite "
            "--certificato.")
    capacita.REGISTRO.da_dict(capacita.check_satellite(cfg, srv))
    capacita.REGISTRO.dinamica("satellite", lambda: capacita.check_satellite(cfg, srv))
    # Satelliti che non si collegano da giorni (05/10): si dicono, non si tolgono
    from ..schermi.archivio import avviso_inattivi
    giorni = float(getattr(cfg, "schermi_inattivi_giorni", 7.0) or 0)
    riga = avviso_inattivi(archivio.inattivi(giorni), "satelliti", giorni,
                           "calliope satellite --revoca")
    if riga:
        log(f"   [SATELLITE] {riga}")
    return srv, ""
