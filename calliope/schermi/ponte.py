"""
Il ponte TLS del satellite verso la pagina degli schermi in HTTPS (02/10/2026). Solo
libreria standard.

La pagina del server è in HTTPS con un certificato autofirmato (schermi/tls.py). Il
satellite non chiede al browser di fidarsi: ascolta su 127.0.0.1 (una porta libera) e per
ogni connessione del browser apre una connessione TLS verso il server, controlla
l'**impronta SHA-256** del certificato (la stessa verifica del WebSocket del satellite,
nessuna CA) e poi copia i byte nei due versi. Il browser apre
`http://127.0.0.1:<porta>/#t=<token>`:

  - 127.0.0.1 è un contesto sicuro per il browser (servirà al microfono della web app);
  - in rete viaggia solo TLS, verificato con l'impronta: il token non passa mai in chiaro;
  - nessuna opzione del browser da toccare. Si era provato prima
    `--ignore-certificate-errors-spki-list=<SPKI>` (con un profilo dedicato): Edge 154 lo
    ignora e mostra «Errore di privacy» (prove/prova_schermi_pagina.py, 02/10);
  - nessun parsing HTTP: SSE e keep-alive passano così come sono. Il server vede Host
    «127.0.0.1:<porta>», un IP, quindi ammesso.

Se l'impronta non corrisponde la connessione si chiude subito, prima di mandare un byte
del browser (che contiene il token), e il log lo dice una volta.
"""

import hashlib
import selectors
import socket
import ssl
import threading


def _norm(impronta: str | None) -> str:
    t = str(impronta or "")
    if "=" in t:
        t = t.split("=", 1)[1]
    return "".join(ch for ch in t.upper() if ch in "0123456789ABCDEF")


class PonteTLS:
    """127.0.0.1:<porta> → TLS verso (host, porta) del server, con l'impronta fissata."""

    def __init__(self, host: str, porta: int, impronta: str, log=print,
                 timeout_s: float = 5.0):
        self.host, self.porta = host, int(porta)
        self.impronta = _norm(impronta)
        if len(self.impronta) != 64:
            raise ValueError("impronta SHA-256 del server mancante: il ponte non parte")
        self.log = log
        self.timeout_s = timeout_s
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        # Nessuna CA né nome: si controlla l'impronta del certificato, come per il WebSocket
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(32)
        self.porta_locale = self.sock.getsockname()[1]
        self._fermo = threading.Event()
        self._detto = False
        self.rifiutate = 0
        threading.Thread(target=self._accetta, name="ponte-schermi", daemon=True).start()

    def aggiorna_impronta(self, impronta: str) -> bool:
        """Il certificato del server è stato rifatto: l'impronta nuova arriva sulla
        connessione del satellite (già verificata). True se è cambiata."""
        nuova = _norm(impronta)
        if len(nuova) != 64 or nuova == self.impronta:
            return False
        self.impronta = nuova
        self._detto = False
        return True

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.porta_locale}"

    def _accetta(self):
        while not self._fermo.is_set():
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._servi, args=(c,), daemon=True).start()

    def _servi(self, browser: socket.socket):
        try:
            raw = socket.create_connection((self.host, self.porta), timeout=self.timeout_s)
            server = self.ctx.wrap_socket(raw)
            vista = hashlib.sha256(server.getpeercert(binary_form=True)).hexdigest().upper()
            if vista != self.impronta:
                self.rifiutate += 1
                if not self._detto:
                    self._detto = True
                    self.log("[SATELLITE] La pagina degli schermi ha un certificato diverso da "
                             "quello del server abbinato: non la apro (il token non parte).")
                server.close()
                browser.close()
                return
        except OSError:
            browser.close()                     # server giù: la pagina riproverà da sola
            return
        try:
            self._inoltra(browser, server)
        finally:
            for s in (browser, server):
                try:
                    s.close()
                except OSError:
                    pass

    # Byte in attesa oltre i quali non si legge più dall'altro lato (contropressione)
    MAX_BUFFER = 1 << 18

    def _inoltra(self, browser: socket.socket, server: ssl.SSLSocket):
        """Copia i byte nei due versi da **un solo thread**, con i socket non bloccanti.

        Prima (fino al 03/10) c'erano due thread, uno per verso, che usavano lo stesso
        SSLSocket: uno fermo in recv (SSL_read) e l'altro in sendall (SSL_write). OpenSSL non
        ammette due thread sullo stesso oggetto SSL: ogni tanto la richiesta del browser
        («GET / HTTP/1.1») partiva e il server non la riceveva mai, la pagina restava bianca
        30 s e lo schermo non si collegava (1 volta su 3 o 4 in prova_schermi_pagina sotto
        carico). Qui tutte le operazioni TLS sono dello stesso thread."""
        browser.setblocking(False)
        server.setblocking(False)
        al_server, al_browser = bytearray(), bytearray()
        fine_browser = fine_server = False
        sel = selectors.DefaultSelector()
        try:
            while not self._fermo.is_set():
                # Fine: un lato ha chiuso e quello che aveva mandato è stato consegnato
                if (fine_browser and not al_server) or (fine_server and not al_browser):
                    return
                ev_b = (selectors.EVENT_READ if not fine_browser
                        and len(al_server) < self.MAX_BUFFER else 0)                     | (selectors.EVENT_WRITE if al_browser else 0)
                ev_s = (selectors.EVENT_READ if not fine_server
                        and len(al_browser) < self.MAX_BUFFER else 0)                     | (selectors.EVENT_WRITE if al_server else 0)
                for s, ev in ((browser, ev_b), (server, ev_s)):
                    if ev:
                        try:
                            sel.modify(s, ev)
                        except KeyError:
                            sel.register(s, ev)
                    else:
                        try:
                            sel.unregister(s)
                        except KeyError:
                            pass
                # Dati già decifrati dentro l'oggetto SSL: select non li vede
                attesa = 0 if (server.pending() and ev_s & selectors.EVENT_READ) else 1.0
                sel.select(attesa) if sel.get_map() else self._fermo.wait(attesa)
                # browser → server
                if not fine_browser and len(al_server) < self.MAX_BUFFER:
                    try:
                        b = browser.recv(65536)
                        if b:
                            al_server += b
                        else:
                            fine_browser = True
                    except (BlockingIOError, InterruptedError):
                        pass
                if al_server:
                    try:
                        n = server.send(al_server)
                        del al_server[:n]
                    except (ssl.SSLWantWriteError, ssl.SSLWantReadError, BlockingIOError):
                        pass
                # server → browser (tutto quello che c'è, anche ciò che è già decifrato)
                while not fine_server and len(al_browser) < self.MAX_BUFFER:
                    try:
                        b = server.recv(65536)
                    except (ssl.SSLWantReadError, ssl.SSLWantWriteError, BlockingIOError):
                        break
                    except ssl.SSLZeroReturnError:
                        b = b""
                    if b:
                        al_browser += b
                    else:
                        fine_server = True
                if al_browser:
                    try:
                        n = browser.send(al_browser)
                        del al_browser[:n]
                    except (BlockingIOError, InterruptedError):
                        pass
        except OSError:
            pass                                # un lato è caduto: si chiudono tutti e due
        finally:
            sel.close()

    def ferma(self):
        self._fermo.set()
        try:
            self.sock.close()
        except OSError:
            pass
