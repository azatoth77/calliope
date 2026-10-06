"""
Porte in ascolto dei server di Calliope (schermi 8770, satelliti 8771), 02/10/2026.

Il 02/10 alle 22:59, sulla DGX, `calliope aggiorna` ha riavviato Calliope e il server degli
schermi non è partito: «la porta 8770 non si apre (Address already in use)», capacità
«schermi» guasta fino al riavvio dopo. Il processo vecchio era appena uscito: su Linux le
sue connessioni restano in TIME_WAIT (le pagine e i satelliti collegati) e, senza
SO_REUSEADDR, il bind della stessa porta fallisce per un minuto; durante un riavvio veloce di
systemd il processo vecchio può anche essere ancora lì per qualche istante.

Due rimedi insieme:
  - SO_REUSEADDR fuori da Windows: permette il bind con connessioni in TIME_WAIT, ma NON con
    un altro processo in ascolto sulla stessa porta (quello resta un errore vero);
  - su Windows SO_EXCLUSIVEADDRUSE, come prima: lì SO_REUSEADDR vorrebbe dire «lascia
    prendere la porta anche a un altro processo in ascolto», cioè due Calliope sulla stessa
    porta senza errore;
  - qualche tentativo di bind per `attesa_s` secondi prima di arrendersi: copre il processo
    vecchio che sta ancora chiudendo. Solo «indirizzo in uso» si riprova; gli altri errori
    (indirizzo che non esiste su questa macchina, permessi) escono subito.
"""

import errno
import os
import socket
import time

ATTESA_S = 10.0          # quanto si riprova una porta occupata all'avvio
PASSO_S = 0.5


def _in_uso(e: OSError) -> bool:
    return e.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", 10048), 10048) \
        or getattr(e, "winerror", None) in (10048, 10013)


def socket_in_ascolto(host: str, port: int, backlog: int = 64, attesa_s: float = ATTESA_S,
                      log=None) -> socket.socket:
    """Un socket TCP già in ascolto su (host, port). Solleva OSError se la porta resta
    occupata per `attesa_s` secondi (o subito, per gli altri errori)."""
    fam = socket.AF_INET6 if ":" in str(host) else socket.AF_INET
    fine = time.monotonic() + max(0.0, attesa_s)
    detto = False
    while True:
        sock = socket.socket(fam, socket.SOCK_STREAM)
        try:
            if os.name == "nt":
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            sock.listen(backlog)
            return sock
        except OSError as e:
            sock.close()
            if not _in_uso(e) or time.monotonic() >= fine:
                raise
            if log is not None and not detto:
                log(f"   [RETE] la porta {port} è ancora occupata (il processo di prima sta "
                    f"chiudendo?): riprovo per {attesa_s:.0f} s")
                detto = True
            time.sleep(PASSO_S)
