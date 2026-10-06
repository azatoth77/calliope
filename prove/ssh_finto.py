"""
Un `ssh` FINTO per le prove del tunnel (calliope/agenti/tunnel.py). Non si collega a niente:
simula quello che fa OpenSSH con `-N -L porta_locale:127.0.0.1:porta_remota alias`.

Lo si mette nel PATH (o in CALLIOPE_SSH) con un `ssh.cmd` accanto (vedi `prepara`), e lo si
guida con variabili d'ambiente, lette a ogni avvio:

  SSH_FINTO_MODO     ok | cade:<secondi> | chiave | vpn | nome | host | porta | muto
  SSH_FINTO_DESTINO  porta su 127.0.0.1 dove inoltrare (l'Ollama finto); senza, porta_remota
  SSH_FINTO_LOG      file dove aggiungere una riga JSON con gli argomenti ricevuti

Gli errori sono le frasi vere di OpenSSH, con un utente e un indirizzo inventati: la prova
controlla che Calliope non li ripeta mai.
"""

import json
import os
import socket
import sys
import threading
import time

UTENTE, HOST = "utente-segreto", "10.9.8.7"


def _pipe(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _inoltra(lp: int, dest: int, durata: float | None):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE if hasattr(
        socket, "SO_EXCLUSIVEADDRUSE") else socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("127.0.0.1", lp))
    except OSError:
        sys.stderr.write(f"bind [127.0.0.1]:{lp}: Address already in use\r\n"
                         f"channel_setup_fwd_listener_tcpip: cannot listen to port: {lp}\r\n"
                         f"Could not request local forwarding.\r\n")
        sys.stderr.flush()
        os._exit(255)
    srv.listen(16)
    if durata is not None:
        def cadi():
            time.sleep(durata)
            sys.stderr.write(f"client_loop: send disconnect: Connection reset by {HOST} port "
                             f"22\r\n")
            sys.stderr.flush()
            os._exit(255)
        threading.Thread(target=cadi, daemon=True).start()
    while True:
        c, _ = srv.accept()
        try:
            d = socket.create_connection(("127.0.0.1", dest), timeout=5)
            d.settimeout(None)
        except OSError:
            c.close()
            continue
        threading.Thread(target=_pipe, args=(c, d), daemon=True).start()
        threading.Thread(target=_pipe, args=(d, c), daemon=True).start()


def main(argv):
    log = os.environ.get("SSH_FINTO_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(argv) + "\n")
    lp = rp = None
    if "-L" in argv:
        parts = argv[argv.index("-L") + 1].split(":")
        lp, rp = int(parts[-3]), int(parts[-1])
    modo = os.environ.get("SSH_FINTO_MODO", "ok")
    err = sys.stderr.write
    if modo == "chiave":
        err(f"{UTENTE}@{HOST}: Permission denied (publickey).\r\n")
        return 255
    if modo == "vpn":
        time.sleep(0.3)
        err(f"ssh: connect to host {HOST} port 22: Connection timed out\r\n")
        return 255
    if modo == "nome":
        err(f"ssh: Could not resolve hostname {argv[-1]}: Host sconosciuto.\r\n")
        return 255
    if modo == "host":
        err("@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\r\n"
            "@    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @\r\n"
            f"Host key for {HOST} has changed and you have requested strict checking.\r\n"
            "Host key verification failed.\r\n")
        return 255
    if modo == "porta":
        err(f"bind [127.0.0.1]:{lp}: Address already in use\r\n"
            f"channel_setup_fwd_listener_tcpip: cannot listen to port: {lp}\r\n"
            "Could not request local forwarding.\r\n")
        return 255
    if modo == "muto":
        time.sleep(3600)
        return 255
    durata = float(modo.split(":", 1)[1]) if modo.startswith("cade:") else None
    dest = int(os.environ.get("SSH_FINTO_DESTINO") or rp)
    _inoltra(lp, dest, durata)
    return 0


def prepara(cartella) -> str:
    """Scrive `ssh.cmd` (Windows) o `ssh` eseguibile (Linux: la DGX, prima installazione
    del 02/10) in `cartella`, che chiama questo script con lo stesso Python, e restituisce
    il suo percorso. Mettere la cartella in testa al PATH, o il percorso in CALLIOPE_SSH."""
    from pathlib import Path
    script = Path(__file__).resolve()
    if os.name == "nt":
        p = Path(cartella) / "ssh.cmd"
        p.write_text(f'@"{sys.executable}" -u "{script}" %*\r\n', encoding="utf-8")
    else:
        p = Path(cartella) / "ssh"
        p.write_text(f'#!/bin/sh\nexec "{sys.executable}" -u "{script}" "$@"\n',
                     encoding="utf-8")
        p.chmod(0o755)
    return str(p)


if __name__ == "__main__":
    sys.stderr.flush()
    code = main(sys.argv[1:])
    sys.stderr.flush()
    os._exit(code)
