"""
Socket TLS da usare con più thread insieme (03/10/2026). Solo libreria standard.

La libreria `websockets` con l'API sincrona (server dei satelliti, client del satellite,
client di Home Assistant) legge il socket da un thread suo (`recv_events`) e ci scrive da
altri (`send`, la risposta ai ping, il saluto di chiusura). Con TLS sono `SSL_read` e
`SSL_write` sullo stesso oggetto SSL in due thread, che OpenSSL non ammette: ogni tanto un
messaggio scritto mentre l'altro thread è fermo in lettura non parte mai. Misurato qui
(Windows, Python 3.14, websockets 17.1): 9 aperture su 300 restavano senza risposta fino al
tempo massimo («timed out while waiting for handshake response»), 0 su 300 senza TLS; con
questa classe 0 su 300. In prova_satellite era la parte del TLS che falliva sotto carico.

`sicuro(ctx)` fa creare al contesto questa sottoclasse di `ssl.SSLSocket` (attributo
`sslsocket_class`, previsto dalla libreria standard): dopo l'handshake il socket sotto è
non bloccante e ogni operazione TLS avviene con un lucchetto; l'attesa dei dati (select) è
**fuori** dal lucchetto, così una lettura ferma non blocca una scrittura e viceversa. Il
tempo massimo impostato con `settimeout` vale come prima (TimeoutError).
"""

import select
import socket
import ssl
import threading
import time

_CREA = threading.Lock()


class _Stato:
    __slots__ = ("io", "tx", "timeout")

    def __init__(self, timeout):
        self.io = threading.Lock()          # una sola operazione TLS alla volta
        self.tx = threading.Lock()          # un sendall alla volta (i suoi pezzi in ordine)
        self.timeout = timeout              # quello chiesto da chi usa il socket


class SocketTLS(ssl.SSLSocket):
    """SSLSocket con letture e scritture da thread diversi (vedi il modulo)."""

    def _stato(self) -> "_Stato | None":
        return self.__dict__.get("_st_tls")

    def do_handshake(self, block=False):
        super().do_handshake(block)
        with _CREA:
            if self._stato() is None:
                self.__dict__["_st_tls"] = _Stato(super().gettimeout())
                super().settimeout(0.0)

    # ── tempo massimo: quello di chi usa il socket; il socket vero resta non bloccante ──
    def settimeout(self, value):
        st = self._stato()
        if st is None:
            return super().settimeout(value)
        if value is not None:
            value = float(value)
            if value < 0:
                raise ValueError("Timeout value out of range")
        st.timeout = value

    def gettimeout(self):
        st = self._stato()
        return super().gettimeout() if st is None else st.timeout

    def setblocking(self, flag):
        self.settimeout(None if flag else 0.0)

    # ── operazioni ──
    def _fai(self, op, *args):
        st = self._stato()
        if st is None:
            return op(*args)
        fine = None if st.timeout is None else time.monotonic() + st.timeout
        while True:
            with st.io:
                try:
                    return op(*args)
                except (ssl.SSLWantReadError, BlockingIOError, InterruptedError) as e:
                    attesa, errore = "r", e
                except ssl.SSLWantWriteError as e:
                    attesa, errore = "w", e
            if st.timeout == 0.0:
                raise errore                    # non bloccante chiesto da chi lo usa
            resto = None if fine is None else fine - time.monotonic()
            if resto is not None and resto <= 0:
                raise TimeoutError("The operation timed out")
            # Fuori dal lucchetto: l'altro thread può leggere o scrivere intanto. Al più 0,2 s
            # per volta: un socket chiuso da un altro thread (shutdown) non resta in attesa
            try:
                select.select([self] if attesa == "r" else [], [self] if attesa == "w" else [],
                              [], 0.2 if resto is None else min(resto, 0.2))
            except ValueError as e:             # chiuso da un altro thread (fileno -1)
                raise OSError("socket chiuso") from e

    # recv e recv_into di SSLSocket passano da read (send invece va diretto all'oggetto SSL).
    # Dopo shutdown (websockets lo chiama per chiudere) l'oggetto SSL non c'è più: come in
    # SSLSocket si legge il socket nudo, e una lettura già in attesa finisce con b"" (fine)
    def read(self, len=1024, buffer=None):  # noqa: A002 — firma di SSLSocket.read
        try:
            return self._fai(super().read, len, buffer)
        except ValueError:
            if self._stato() is not None and self._sslobj is None:
                return 0 if buffer is not None else b""
            raise

    def recv(self, buflen=1024, flags=0):
        if self._stato() is not None and self._sslobj is None:
            return self._fai(socket.socket.recv, self, buflen, flags)
        return super().recv(buflen, flags)

    def recv_into(self, buffer, nbytes=None, flags=0):
        if self._stato() is not None and self._sslobj is None:
            return self._fai(socket.socket.recv_into, self, buffer, nbytes or 0, flags)
        return super().recv_into(buffer, nbytes, flags)

    def send(self, data, flags=0):
        return self._fai(super().send, data, flags)

    def write(self, data):
        return self._fai(super().write, data)

    def sendall(self, data, flags=0):
        st = self._stato()
        if st is None:
            return super().sendall(data, flags)
        with st.tx, memoryview(data) as view, view.cast("B") as byte_view:
            fatti, tutti = 0, len(byte_view)
            while fatti < tutti:
                fatti += self.send(byte_view[fatti:], flags)


def sicuro(ctx: ssl.SSLContext) -> ssl.SSLContext:
    """Il contesto crea socket `SocketTLS` (anche quelli accettati da un socket in ascolto)."""
    ctx.sslsocket_class = SocketTLS
    return ctx
