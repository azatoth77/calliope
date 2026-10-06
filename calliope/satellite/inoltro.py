"""
L'inoltro del satellite verso la pagina degli schermi e la web app del telefono (03/10/2026,
docs/ricerche/2026-10-03-webapp-telefono.md §8). Solo libreria standard.

Calliope sta sulla DGX in ufficio, raggiungibile solo in VPN; il portatile di casa (il
satellite) è in VPN; il telefono entra nella rete di casa con WireGuard (add-on di Home
Assistant sul Raspberry). Il telefono non vede la DGX: vede il portatile. Con
`satellite_inoltro: "0.0.0.0:8770"` il satellite ascolta su quella porta e copia i byte, così
come sono, verso host e porta della pagina degli schermi della DGX (host di `satellite_server`,
porta che il server dice nel «benvenuto»).

  - **TCP grezzo, niente TLS qui**: il TLS resta da capo a capo tra il telefono e la DGX, che
    presenta il suo certificato firmato dalla CA di casa (`calliope schermi --certificato
    --host <IP del portatile>`). Il portatile non vede né il token né le pagine;
  - **solo dalla rete di casa o di WireGuard**: si accettano solo indirizzi sorgente nelle
    reti di `satellite_inoltro_reti` (predefinite dal 03/10: 192.168.x, WireGuard di HA
    172.27.66.0/24, PiVPN 10.6.0.0/24, loopback; non più tutte le reti private).
    Se un giorno qualcuno inoltrasse la porta dal router verso il portatile, le connessioni da
    internet si chiudono subito (con l'add-on WireGuard di HA il telefono arriva con un
    indirizzo della LAN o di WireGuard, privato in tutti e due i casi);
  - al più `satellite_inoltro_max` connessioni insieme, chiuse dopo
    `satellite_inoltro_inattivita_s` senza un byte (SSE e WebSocket del telefono hanno un ping
    ogni 15–20 s: restano vive);
  - DGX che non risponde (VPN giù, Calliope spenta): la connessione del telefono si chiude
    subito, dopo al più `COLLEGAMENTO_S`;
  - un thread per accettare e **uno per connessione**, che copia nei due versi con i socket
    non bloccanti e `selectors` (un solo thread per socket: niente letture e scritture
    concorrenti), con la chiusura a metà (FIN) passata dall'altra parte;
  - una riga di log per connessione (chi, quanto, quanti byte), mai i dati.
"""

import ipaddress
import selectors
import socket
import threading
import time

# Dal 03/10 (analisi di sicurezza, rete, difetto 4) non più tutte le reti private: le reti
# Wi-Fi di bar, alberghi, treni e uffici sono quasi sempre 10.x o 172.16–31.x, e con la VPN
# accesa il portatile faceva da ponte da lì verso la DGX. Restano le reti dei router di casa
# (192.168.x), quella dell'add-on WireGuard di Home Assistant (172.27.66.0/24), quella di
# PiVPN (10.6.0.0/24) e il loopback. Un'altra rete di casa o di VPN va scritta in
# satellite_inoltro_reti.
RETI_PREDEFINITE = ["192.168.0.0/16", "172.27.66.0/24", "10.6.0.0/24", "127.0.0.0/8",
                    "::1/128"]
COLLEGAMENTO_S = 4.0          # attesa massima della DGX per una connessione nuova
MAX_BUFFER = 1 << 18          # byte in attesa oltre i quali non si legge dall'altro lato
LOG_RIFIUTO_S = 60.0          # un rifiuto per indirizzo al minuto nel log


def reti(elenco) -> list:
    """Le reti ammesse come oggetti di ipaddress; ValueError con la voce sbagliata."""
    out = []
    for r in elenco or ():
        try:
            out.append(ipaddress.ip_network(str(r).strip(), strict=False))
        except ValueError as e:
            raise ValueError(f"rete non valida in satellite_inoltro_reti: «{r}»") from e
    return out


def ammesso(ip: str, ammesse) -> bool:
    """L'indirizzo sorgente sta in una delle reti ammesse? Gli IPv4 visti come IPv6
    (::ffff:192.168.1.5, socket a doppio stack) valgono come IPv4."""
    try:
        a = ipaddress.ip_address(str(ip).split("%", 1)[0])
    except ValueError:
        return False
    if a.version == 6 and a.ipv4_mapped is not None:
        a = a.ipv4_mapped
    return any(a.version == r.version and a in r for r in ammesse)


def indirizzo(testo: str, porta_predefinita: int = 8770) -> tuple[str, int]:
    """«192.168.1.30:8770», «0.0.0.0:8770», «:8770», «8770», «[::]:8770», «192.168.1.30»
    → (host, porta). ValueError se non si capisce."""
    t = str(testo or "").strip()
    if not t:
        raise ValueError("indirizzo vuoto")
    if t.isdigit():
        host, porta = "0.0.0.0", t
    elif t.startswith("["):
        fine = t.find("]")
        if fine < 0:
            raise ValueError(f"indirizzo non valido: «{testo}»")
        host, resto = t[1:fine], t[fine + 1:]
        porta = resto[1:] if resto.startswith(":") else str(porta_predefinita)
    elif t.count(":") == 1:
        host, porta = t.split(":")
        host = host or "0.0.0.0"
    elif t.count(":") > 1:
        host, porta = t, str(porta_predefinita)       # IPv6 senza parentesi né porta
    else:
        host, porta = t, str(porta_predefinita)
    if not porta.isdigit() or not 0 <= int(porta) <= 65535:
        raise ValueError(f"porta non valida: «{testo}»")
    return host, int(porta)


class Inoltro:
    """Ascolta su (host, porta) e copia ogni connessione ammessa verso `destinazione()`, una
    funzione che dà (host, porta) della pagina degli schermi oppure None (ancora sconosciuta:
    la connessione si chiude)."""

    def __init__(self, ascolto: str, destinazione, ammesse=None, max_connessioni: int = 32,
                 inattivita_s: float = 300.0, log=print, attesa_porta_s: float = 2.0):
        from ..porte import socket_in_ascolto
        self.host, self.porta = indirizzo(ascolto)
        self.destinazione = destinazione
        self.reti = reti(RETI_PREDEFINITE if ammesse is None else ammesse)
        self.max = max(1, int(max_connessioni))
        self.inattivita_s = float(inattivita_s)
        self.log = log
        self.sock = socket_in_ascolto(self.host, self.porta, 64, attesa_s=attesa_porta_s)
        self.porta = self.sock.getsockname()[1]           # con 0: quella scelta dal sistema
        self.sock.settimeout(0.5)
        self._fermo = threading.Event()
        self._lock = threading.Lock()
        self._connessioni: set[socket.socket] = set()     # lato telefono, una per connessione
        self._socket: set[socket.socket] = set()          # tutti, per chiuderli in ferma()
        self._ultimo_rifiuto: dict[str, float] = {}
        # Contatori (terminale e prove)
        self.accettate = 0
        self.rifiutate_rete = 0
        self.rifiutate_limite = 0
        self.fallite = 0                  # DGX irraggiungibile o destinazione sconosciuta
        self.chiuse_inattive = 0
        self._thread = threading.Thread(target=self._accetta, name="inoltro", daemon=True)
        self._thread.start()

    @property
    def attive(self) -> int:
        with self._lock:
            return len(self._connessioni)

    def _accetta(self):
        while not self._fermo.is_set():
            try:
                c, addr = self.sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return                                    # chiuso da ferma()
            self.nuova(c, addr)

    def nuova(self, c: socket.socket, addr) -> bool:
        """Una connessione appena accettata: filtro sull'indirizzo sorgente e limite, poi un
        thread suo. False se rifiutata (chiusa subito). Le prove la chiamano con un
        indirizzo finto."""
        ip = str(addr[0]) if addr else ""
        if not ammesso(ip, self.reti):
            self.rifiutate_rete += 1
            self._chiudi(c)
            self._log_rifiuto(ip, "indirizzo fuori dalle reti ammesse "
                                  "(satellite_inoltro_reti)")
            return False
        with self._lock:
            pieno = len(self._connessioni) >= self.max or self._fermo.is_set()
            if not pieno:
                self._connessioni.add(c)
                self._socket.add(c)
        if pieno:
            self.rifiutate_limite += 1
            self._chiudi(c)
            self._log_rifiuto(ip, f"già {self.max} connessioni aperte")
            return False
        self.accettate += 1
        threading.Thread(target=self._servi, args=(c, ip), name="inoltro-conn",
                         daemon=True).start()
        return True

    def _log_rifiuto(self, ip: str, motivo: str):
        ora = time.monotonic()
        if ora - self._ultimo_rifiuto.get(ip, -LOG_RIFIUTO_S) >= LOG_RIFIUTO_S:
            self._ultimo_rifiuto[ip] = ora
            if len(self._ultimo_rifiuto) > 1000:
                self._ultimo_rifiuto.clear()
            self.log(f"[INOLTRO] rifiutata da {ip}: {motivo}")

    @staticmethod
    def _chiudi(s: socket.socket):
        try:
            s.close()
        except OSError:
            pass

    def _servi(self, telefono: socket.socket, ip: str):
        t0 = time.monotonic()
        server = None
        esito, su, giu = "", 0, 0
        try:
            dest = self.destinazione()
            if not dest:
                esito = "pagina degli schermi del server ancora sconosciuta"
                self.fallite += 1
                return
            try:
                server = socket.create_connection(dest, timeout=COLLEGAMENTO_S)
            except OSError as e:
                esito = f"il server non risponde ({e.strerror or type(e).__name__})"
                self.fallite += 1
                return
            with self._lock:
                if self._fermo.is_set():
                    return
                self._socket.add(server)
            for s in (telefono, server):
                try:
                    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except OSError:
                    pass
            esito, su, giu = self._copia(telefono, server)
        finally:
            with self._lock:
                self._connessioni.discard(telefono)
                self._socket.discard(telefono)
                self._socket.discard(server)
            for s in (telefono, server):
                if s is not None:
                    self._chiudi(s)
            if not self._fermo.is_set():
                self.log(f"[INOLTRO] {ip}: {esito or 'chiusa'}, {time.monotonic() - t0:.1f} s, "
                         f"{_kb(su)} verso il server, {_kb(giu)} verso il telefono")

    def _copia(self, a: socket.socket, b: socket.socket) -> tuple[str, int, int]:
        """Copia nei due versi finché tutti e due hanno chiuso (o uno è caduto, o niente passa
        per `inattivita_s`). (esito, byte a→b, byte b→a)."""
        a.setblocking(False)
        b.setblocking(False)
        altro = {a: b, b: a}
        verso = {a: bytearray(), b: bytearray()}          # byte da scrivere su quel socket
        finito = {a: False, b: False}                     # quel socket ha chiuso in lettura
        chiuso_scrittura = {a: False, b: False}
        contati = {a: 0, b: 0}                            # byte letti da quel socket
        sel = selectors.DefaultSelector()
        registrati: dict = {}
        ultimo = time.monotonic()
        try:
            while not self._fermo.is_set():
                for s in (a, b):
                    ev = 0
                    if not finito[s] and len(verso[altro[s]]) < MAX_BUFFER:
                        ev |= selectors.EVENT_READ
                    if verso[s]:
                        ev |= selectors.EVENT_WRITE
                    if ev != registrati.get(s, 0):
                        if not ev:
                            sel.unregister(s)
                        elif s in registrati and registrati[s]:
                            sel.modify(s, ev)
                        else:
                            sel.register(s, ev)
                        registrati[s] = ev
                if not any(registrati.values()):
                    return "chiusa", contati[a], contati[b]
                pronti = sel.select(1.0)
                ora = time.monotonic()
                if not pronti:
                    if ora - ultimo > self.inattivita_s:
                        self.chiuse_inattive += 1
                        return "chiusa per inattività", contati[a], contati[b]
                    continue
                for chiave, ev in pronti:
                    s = chiave.fileobj
                    if ev & selectors.EVENT_READ:
                        try:
                            dati = s.recv(65536)
                        except (BlockingIOError, InterruptedError):
                            dati = None
                        if dati:
                            verso[altro[s]] += dati
                            contati[s] += len(dati)
                            ultimo = ora
                        elif dati is not None:
                            finito[s] = True
                    if ev & selectors.EVENT_WRITE and verso[s]:
                        try:
                            n = s.send(verso[s])
                            del verso[s][:n]
                            ultimo = ora
                        except (BlockingIOError, InterruptedError):
                            pass
                # Chiusura a metà: chi ha finito di mandare, una volta consegnato tutto, lo
                # dice all'altro lato (FIN), che può ancora rispondere
                for s in (a, b):
                    o = altro[s]
                    if finito[s] and not verso[o] and not chiuso_scrittura[o]:
                        chiuso_scrittura[o] = True
                        try:
                            o.shutdown(socket.SHUT_WR)
                        except OSError:
                            pass
                if all(finito.values()) and not verso[a] and not verso[b]:
                    return "chiusa", contati[a], contati[b]
            return "inoltro spento", contati[a], contati[b]
        except (OSError, ValueError, KeyError):           # un lato è caduto (o ferma())
            return "interrotta", contati[a], contati[b]
        finally:
            sel.close()

    def ferma(self):
        """Chiude la porta e tutte le connessioni in corso. Idempotente."""
        self._fermo.set()
        self._chiudi(self.sock)
        with self._lock:
            aperti = list(self._socket)
            self._socket.clear()
            self._connessioni.clear()
        for s in aperti:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._chiudi(s)
        self._thread.join(timeout=2)


def _kb(n: int) -> str:
    return f"{n} B" if n < 10240 else f"{n // 1024} kB"
