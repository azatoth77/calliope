import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Prova a secco dell'inoltro del satellite per il telefono di casa (calliope/satellite/
inoltro.py, 03/10/2026; docs/ricerche/2026-10-03-webapp-telefono.md §8).

Tutto su 127.0.0.1, in una cartella temporanea:
- indirizzi: «0.0.0.0:8770», «:8770», «8770», «[::]:8770»; reti ammesse: private, WireGuard
  (10.x, 172.16–31.x), link-local e loopback sì, internet no (anche 172.32.x e 100.64.x, il
  CGNAT, se non aggiunto), IPv4 visto come IPv6, reti scritte male;
- connessione da un indirizzo pubblico (simulato: `Inoltro.nuova` con un indirizzo finto)
  chiusa subito, senza toccare il server; rete aggiunta in satellite_inoltro_reti accettata;
- copia nei due versi: 2 MB di eco tali e quali, chiusura a metà (FIN) passata all'altro lato;
- limiti: oltre `satellite_inoltro_max` la connessione si chiude, poi si libera il posto;
  inattività; server che non risponde (porta chiusa) o destinazione ancora sconosciuta: la
  connessione del telefono si chiude subito; `ferma` chiude porta e connessioni;
- con la CA di casa (openssl): server degli schermi vero in HTTPS, certificato con l'IP e un
  nome; attraverso l'inoltro il TLS è **da capo a capo** (catena e nome verificati con la CA,
  l'impronta vista è quella del server), la pagina /telefono risponde, l'Host di un nome è
  accettato solo se in schermi_nomi, il WebSocket del telefono si abbina con l'Origin
  dell'inoltro (IP e nome) e rifiuta l'Origin della porta del server;
- satellite vero (microfono e casse finti): l'inoltro si accende e si spegne con lui, la
  porta della pagina arriva dal benvenuto, e dopo un certificato rifatto sul server il ponte
  della pagina riceve l'impronta nuova alla riconnessione, senza riaprire la pagina;
- Edge (o Chromium) senza finestra, se c'è: la pagina /telefono aperta con un nome attraverso
  l'inoltro e il WebSocket di abbinamento dal browser vero. Il browser non ha la CA di casa
  (installarla in Windows chiede una conferma a schermo): ignora gli errori del certificato,
  che la parte qui sopra verifica con la CA.
"""

import json
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="calliope-inoltro-"))
ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


def aspetta(cond, max_s=5.0, passo=0.02):
    fine = time.monotonic() + max_s
    while time.monotonic() < fine:
        v = cond()
        if v:
            return v
        time.sleep(passo)
    return cond()


def porta_libera() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def chiusa(s: socket.socket, max_s=3.0) -> bool:
    """La connessione è stata chiusa dall'altra parte (b"" o reset) entro max_s."""
    s.settimeout(max_s)
    try:
        return s.recv(1) == b""
    except (ConnectionResetError, ConnectionAbortedError):
        return True
    except (TimeoutError, socket.timeout):
        return False


class Eco:
    """Server TCP finto: rimanda quello che riceve; a fine dati del client chiude lui."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(64)
        self.porta = self.sock.getsockname()[1]
        self.connessioni = 0
        self.fin_visti = 0
        threading.Thread(target=self._accetta, daemon=True).start()

    def _accetta(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            self.connessioni += 1
            threading.Thread(target=self._eco, args=(c,), daemon=True).start()

    def _eco(self, c):
        try:
            while True:
                d = c.recv(65536)
                if not d:
                    self.fin_visti += 1
                    break
                c.sendall(d)
        except OSError:
            pass
        finally:
            c.close()

    def chiudi(self):
        self.sock.close()


# ───────────────────────────── funzioni pure ─────────────────────────────
def parte_filtro():
    from calliope.config import Config
    from calliope.satellite.inoltro import RETI_PREDEFINITE, ammesso, indirizzo, reti
    verifica("indirizzi: host:porta, :porta, porta, [IPv6]:porta, solo host",
             indirizzo("0.0.0.0:8770") == ("0.0.0.0", 8770)
             and indirizzo("192.168.1.30:8443") == ("192.168.1.30", 8443)
             and indirizzo(":8770") == ("0.0.0.0", 8770) and indirizzo("8770") == ("0.0.0.0", 8770)
             and indirizzo("[::]:8770") == ("::", 8770)
             and indirizzo("192.168.1.30") == ("192.168.1.30", 8770))
    sbagliati = 0
    for t in ("", "casa:porta", "1.2.3.4:99999", "[::1"):
        try:
            indirizzo(t)
        except ValueError:
            sbagliati += 1
    verifica("indirizzi scritti male: errore chiaro", sbagliati == 4)
    verifica("reti predefinite uguali a quelle di Config",
             Config().satellite_inoltro_reti == RETI_PREDEFINITE)
    r = reti(RETI_PREDEFINITE)
    # Dal 03/10 (analisi di sicurezza) non più tutte le reti private: i Wi-Fi di bar,
    # alberghi e uffici (10.x, 172.16–31.x) restano fuori
    si = ["192.168.1.23", "10.6.0.2", "172.27.66.2", "127.0.0.1", "::1",
          "::ffff:192.168.1.5"]
    no = ["8.8.8.8", "93.184.216.34", "172.32.0.1", "100.64.0.1", "2001:4860::8888",
          "::ffff:8.8.8.8", "", "non-un-ip", "10.8.0.2", "10.0.0.5", "172.16.0.5",
          "172.31.255.1", "169.254.3.4", "fe80::1%12", "fd00::5"]
    verifica("ammessi: LAN di casa, WireGuard di HA e PiVPN, loopback, IPv4 in IPv6",
             all(ammesso(ip, r) for ip in si), str([ip for ip in si if not ammesso(ip, r)]))
    verifica("rifiutati: internet, reti private di bar e uffici, link-local, ULA, strani",
             not any(ammesso(ip, r) for ip in no), str([ip for ip in no if ammesso(ip, r)]))
    verifica("una rete aggiunta (CGNAT di Tailscale) si ammette",
             ammesso("100.64.0.1", reti([*RETI_PREDEFINITE, "100.64.0.0/10"])))
    try:
        reti(["192.168.1.0/24", "casa"])
        verifica("rete scritta male: errore con la voce sbagliata", False)
    except ValueError as e:
        verifica("rete scritta male: errore con la voce sbagliata", "casa" in str(e))


# ───────────────────────────── inoltro TCP ─────────────────────────────
def parte_tcp():
    from calliope.satellite.inoltro import Inoltro
    eco = Eco()
    righe = []
    ino = Inoltro("127.0.0.1:0", lambda: ("127.0.0.1", eco.porta), max_connessioni=3,
                  log=righe.append)
    try:
        # Indirizzo pubblico (simulato): chiusa subito, il server non vede niente
        a, b = socket.socketpair()
        prima = eco.connessioni
        ok = ino.nuova(b, ("8.8.8.8", 40000))
        verifica("da un indirizzo pubblico: rifiutata e chiusa subito, il server non la vede",
                 not ok and chiusa(a, 1) and eco.connessioni == prima
                 and ino.rifiutate_rete == 1 and any("8.8.8.8" in x for x in righe))
        a.close()
        a, b = socket.socketpair()
        ino.nuova(b, ("8.8.8.8", 40001))
        verifica("rifiuti dello stesso indirizzo: una riga di log al minuto",
                 sum("8.8.8.8" in x for x in righe) == 1)
        a.close()
        a, b = socket.socketpair()
        ok = ino.nuova(b, ("192.168.1.23", 40002))
        a.sendall(b"ciao")
        a.settimeout(3)
        verifica("da un indirizzo di casa (simulato): passa", ok and a.recv(10) == b"ciao")
        a.close()

        # 2 MB di eco tali e quali, con la chiusura a metà
        c = socket.create_connection(("127.0.0.1", ino.porta), timeout=5)
        dati = os.urandom(2 * 1024 * 1024)
        ricevuti = bytearray()

        def leggi():
            while True:
                d = c.recv(65536)
                if not d:
                    return
                ricevuti.extend(d)
        t = threading.Thread(target=leggi, daemon=True)
        t.start()
        t0 = time.monotonic()
        c.sendall(dati)
        c.shutdown(socket.SHUT_WR)                  # FIN: il server deve vederlo e chiudere
        t.join(10)
        dt = time.monotonic() - t0
        verifica("2 MB nei due versi tali e quali, FIN passato al server e ritorno",
                 bytes(ricevuti) == dati and eco.fin_visti >= 1,
                 f"{len(ricevuti)} byte, {dt * 1000:.0f} ms, {4 / dt:.0f} MB/s in tutto")
        c.close()
        verifica("una riga per connessione, senza dati: chi, quanto, byte",
                 aspetta(lambda: any(x.startswith("[INOLTRO] 127.0.0.1: chiusa") and "MB" not in x
                                     and "kB verso il server" in x for x in righe), 3),
                 next((x for x in reversed(righe) if "127.0.0.1" in x), ""))

        # Limite di connessioni
        aperte = [socket.create_connection(("127.0.0.1", ino.porta), timeout=5) for _ in range(3)]
        for s in aperte:
            s.sendall(b"x")
            s.recv(1)
        verifica("limite: 3 aperte", aspetta(lambda: ino.attive == 3, 3), str(ino.attive))
        quarta = socket.create_connection(("127.0.0.1", ino.porta), timeout=5)
        verifica("limite: la quarta si chiude subito", chiusa(quarta, 3)
                 and ino.rifiutate_limite == 1)
        quarta.close()
        aperte.pop().close()
        aspetta(lambda: ino.attive == 2, 3)
        nuova = socket.create_connection(("127.0.0.1", ino.porta), timeout=5)
        nuova.sendall(b"y")
        nuova.settimeout(3)
        verifica("limite: chiusa una, il posto si libera", nuova.recv(1) == b"y")
        aperte.append(nuova)

        # ferma: porta e connessioni chiuse
        ino.ferma()
        verifica("ferma: le connessioni aperte si chiudono", all(chiusa(s, 3) for s in aperte))
        for s in aperte:
            s.close()
        try:
            socket.create_connection(("127.0.0.1", ino.porta), timeout=2).close()
            spenta = False
        except OSError:
            spenta = True
        verifica("ferma: la porta non accetta più", spenta)
    finally:
        ino.ferma()

    # Inattività
    ino = Inoltro("127.0.0.1:0", lambda: ("127.0.0.1", eco.porta), inattivita_s=0.5,
                  log=lambda m: None)
    try:
        s = socket.create_connection(("127.0.0.1", ino.porta), timeout=5)
        s.sendall(b"z")
        s.recv(1)
        t0 = time.monotonic()
        verifica("inattività: chiusa dopo il tempo senza byte",
                 chiusa(s, 4) and ino.chiuse_inattive == 1, f"{time.monotonic() - t0:.1f} s")
        s.close()
    finally:
        ino.ferma()

    # Server che non risponde e destinazione sconosciuta
    morta = porta_libera()
    righe = []
    ino = Inoltro("127.0.0.1:0", lambda: ("127.0.0.1", morta), log=righe.append)
    try:
        s = socket.create_connection(("127.0.0.1", ino.porta), timeout=5)
        t0 = time.monotonic()
        verifica("server che non risponde: la connessione del telefono si chiude subito",
                 chiusa(s, 6) and ino.fallite == 1, f"{time.monotonic() - t0:.1f} s, "
                 + next((x for x in righe if "non risponde" in x), "nessuna riga"))
        s.close()
    finally:
        ino.ferma()
    ino = Inoltro("127.0.0.1:0", lambda: None, log=lambda m: None)
    try:
        s = socket.create_connection(("127.0.0.1", ino.porta), timeout=5)
        t0 = time.monotonic()
        verifica("destinazione ancora sconosciuta: chiusa subito",
                 chiusa(s, 2) and time.monotonic() - t0 < 1)
        s.close()
    finally:
        ino.ferma()
    eco.chiudi()


# ───────────────────── schermi veri in HTTPS con la CA di casa ─────────────────────
def config(d: Path, **campi):
    from calliope.config import Config
    c = Config()
    c.config_dir = str(d)
    c.memory_db = str(d / "memoria.db")
    c.satellite_porta = 0
    c.audio_modo = "satellite"
    c.schermi_indirizzo = "0.0.0.0"
    c.telefono_web = str(d / "web")
    for k, v in campi.items():
        setattr(c, k, v)
    return c


def avvia_server(cfg, tls):
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.server import ServerSatelliti
    from calliope.schermi import ArchivioSchermi, Schermi
    from calliope.schermi.server import ServerSchermi
    srv = ServerSatelliti(cfg, ArchivioSatelliti(cfg.memory_db), log=lambda m: None).avvia()
    srv.avviato.set()
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    hub.tls = tls
    # Solo su 127.0.0.1 (la prova non apre porte in rete), con la configurazione «in rete»
    web = ServerSchermi(hub, "127.0.0.1", porta_libera(), attesa_porta_s=5, tls=tls).avvia()
    hub.server = web
    hub.satelliti = srv
    srv.schermi = hub
    hub.stanza_corrente = srv.stanza
    cfg.schermi_porta = web.port
    return srv, hub, web


def richiesta(porta, host, ctx, percorso="/telefono/api/stato"):
    """(stato HTTP, impronta del certificato visto) con Host e SNI = host, verso 127.0.0.1."""
    import hashlib
    raw = socket.create_connection(("127.0.0.1", porta), timeout=5)
    s = ctx.wrap_socket(raw, server_hostname=host.split(":")[0])
    imp = hashlib.sha256(s.getpeercert(binary_form=True)).hexdigest().upper()
    s.sendall(f"GET {percorso} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
    risposta = b""
    while True:
        d = s.recv(65536)
        if not d:
            break
        risposta += d
    s.close()
    return int(risposta.split(b" ", 2)[1]), ":".join(imp[i:i + 2] for i in range(0, 64, 2))


def ws_abbina(porta, host, origine, ctx) -> str:
    """Tipo della prima risposta del WebSocket di abbinamento del telefono (o l'errore)."""
    from calliope.satellite import protocollo as P
    from calliope.tls_sicuro import sicuro
    from websockets.sync.client import connect
    try:
        raw = socket.create_connection(("127.0.0.1", porta), timeout=5)
        with connect(f"wss://{host}/telefono/ws/abbina", sock=raw, ssl=sicuro(ctx),
                     server_hostname=host.split(":")[0], open_timeout=5,
                     additional_headers={"Origin": origine}) as ws:
            ws.send(P.testo(tipo="abbina", versione=2, nome="telefono"))
            return P.leggi(ws.recv(timeout=5)).get("tipo") or "?"
    except Exception as e:  # noqa: BLE001
        return f"rifiutato ({type(e).__name__})"


def parte_https():
    from calliope.satellite.__main__ import _openssl
    from calliope.satellite.inoltro import Inoltro
    from calliope.schermi import tls as T
    from calliope.schermi.__main__ import main as schermi_main
    if _openssl() is None:
        print("SALTATA IN PARTE: openssl non c'è: salto la parte con la CA di casa")
        return None
    d = TMP / "dgx"
    d.mkdir()
    (d / "web").mkdir()
    cfg = config(d, schermi_nomi=["calliope.lan"])
    # --host ripetuto e con la virgola, come sulla DGX: IP in VPN, IP del portatile, un nome
    out = []
    os.environ["CALLIOPE_CONFIG"] = str(d / "calliope.yaml")
    os.environ["CALLIOPE_CONFIG_LOCALE"] = str(d / "calliope.locale.yaml")
    (d / "calliope.yaml").write_text("", encoding="utf-8")
    rc = schermi_main(["--certificato", "--host", "10.9.8.7,192.168.1.30", "--host",
                       "calliope.lan", "--host", "casa.lan"], out=out.append)
    crt = d / "schermi.crt"
    if rc != 0 or not crt.is_file():
        # La configurazione del terminale non punta a d: certificato diretto
        out = []
        rc = T.certificato_telefono(cfg, ["10.9.8.7", "192.168.1.30", "calliope.lan",
                                          "casa.lan"], out=out.append)
    testo = "\n".join(out)
    verifica("--certificato con più --host e con la virgola: tutti nel certificato",
             rc == 0 and all(x in testo for x in ("10.9.8.7", "192.168.1.30", "calliope.lan",
                                                  "127.0.0.1")), testo.splitlines()[1] if
             len(testo.splitlines()) > 1 else testo)
    verifica("--certificato: ricorda schermi_nomi per i nomi scelti a mano",
             "schermi_nomi" in testo and "casa.lan" in testo)
    tls = T.carica(cfg)
    srv, hub, web = avvia_server(cfg, tls)
    ca = ssl.create_default_context(cafile=str(d / "calliope-ca.crt"))
    righe = []
    ino = Inoltro("127.0.0.1:0", lambda: ("127.0.0.1", web.port), log=righe.append)
    try:
        st, imp = richiesta(ino.porta, f"127.0.0.1:{ino.porta}", ca)
        verifica("attraverso l'inoltro: HTTPS verificato con la CA di casa, /telefono risponde",
                 st == 200, f"HTTP {st}")
        verifica("TLS da capo a capo: il certificato visto è quello del server degli schermi",
                 imp == tls["impronta"])
        st, _ = richiesta(ino.porta, f"calliope.lan:{ino.porta}", ca)
        verifica("con un nome in schermi_nomi (e nel certificato): accettato", st == 200,
                 f"HTTP {st}")
        st, _ = richiesta(ino.porta, f"casa.lan:{ino.porta}", ca)
        verifica("con un nome nel certificato ma non in schermi_nomi: «Host non ammesso»",
                 st == 400, f"HTTP {st}")
        senza = ssl.create_default_context()
        try:
            richiesta(ino.porta, f"127.0.0.1:{ino.porta}", senza)
            fidato = True
        except ssl.SSLError:
            fidato = False
        verifica("senza la CA il telefono non si fida (l'inoltro non cambia il certificato)",
                 not fidato)
        dove = f"127.0.0.1:{ino.porta}"
        verifica("WebSocket del telefono attraverso l'inoltro, Origin dell'inoltro: abbinamento",
                 ws_abbina(ino.porta, dove, f"https://{dove}", ca) == "codice")
        dove = f"calliope.lan:{ino.porta}"
        verifica("WebSocket con un nome: Origin e Host coincidono, abbinamento",
                 ws_abbina(ino.porta, dove, f"https://{dove}", ca) == "codice")
        verifica("WebSocket con l'Origin della porta del server (un altro sito): rifiutato",
                 ws_abbina(ino.porta, dove, f"https://calliope.lan:{web.port}", ca)
                 .startswith("rifiutato"))
        browser_vero(ino.porta, righe)
    finally:
        ino.ferma()
        web.ferma()
        srv.ferma()
    return d


# ───────────────────────────── satellite vero ─────────────────────────────
class Rilevatore:
    def reset(self):
        pass

    def process(self, frame):
        return None


def parte_satellite(d_cert: Path | None):
    import prova_satellite as PS
    from calliope.satellite.client import Satellite
    from calliope.schermi import tls as T
    d = TMP / "sat"
    d.mkdir()
    (d / "web").mkdir()
    if d_cert is not None:
        for n in ("calliope-ca.crt", "calliope-ca.key", "schermi.crt", "schermi.key"):
            shutil.copy(d_cert / n, d / n)
    cfg = config(d)
    tls = T.carica(cfg) if d_cert is not None else None
    srv, hub, web = avvia_server(cfg, tls)
    _, token = srv.archivio.crea_con_token("studio")
    righe, pagine = [], []
    cfg_s = PS.cfg_prova(d, satellite_server=f"ws://127.0.0.1:{srv.port}",
                         satellite_credenziali=str(d / "sat.json"),
                         satellite_schermo="finestra" if tls else "no",
                         satellite_inoltro="127.0.0.1:0", schermi_porta=1)
    Path(cfg_s.satellite_credenziali).write_text(json.dumps({"token": token}), encoding="utf-8")
    sat = Satellite(cfg_s, sorgente=lambda **kw: PS.MicFinto(PS.Scena(), **kw),
                    apri_uscita=PS.Casse().flusso, log=righe.append, rilevatore=Rilevatore(),
                    esecutore=False, apri_schermo=pagine.append)
    t = threading.Thread(target=sat.esegui, daemon=True)
    t.start()
    try:
        verifica("satellite: l'inoltro si accende con lui",
                 aspetta(lambda: sat.inoltro is not None, 5)
                 and any("[INOLTRO] Acceso" in x for x in righe))
        verifica("satellite: la porta della pagina arriva dal benvenuto (non schermi_porta "
                 "di qui)", aspetta(lambda: sat.collegato.is_set(), 10)
                 and sat._destinazione_inoltro() == ("127.0.0.1", web.port),
                 str(sat._destinazione_inoltro()))
        porta = sat.inoltro.porta
        if tls is not None:
            ca = ssl.create_default_context(cafile=str(d / "calliope-ca.crt"))
            st, imp = richiesta(porta, f"127.0.0.1:{porta}", ca)
            verifica("satellite: la pagina del telefono raggiunta attraverso il suo inoltro",
                     st == 200 and imp == tls["impronta"], f"HTTP {st}")
            verifica("satellite: la pagina degli schermi aperta una volta, ponte con l'impronta",
                     aspetta(lambda: len(pagine) == 1 and sat._ponte is not None, 5)
                     and sat._ponte.impronta == tls["impronta"].replace(":", ""))
            # Certificato rifatto sul server (--forza) e Calliope riavviata: qui basta che il
            # server mandi l'impronta nuova e che il satellite si ricolleghi
            T.certificato_telefono(cfg, ["10.9.8.7"], forza=True, out=lambda m: None)
            nuovo = T.carica(cfg)
            hub.tls = nuovo
            prima = sat.connessioni
            srv.collegati[0].ws.close()
            verifica("certificato rifatto: alla riconnessione il ponte usa l'impronta nuova",
                     aspetta(lambda: sat.connessioni > prima and sat._ponte.impronta
                             == nuovo["impronta"].replace(":", ""), 10)
                     and nuovo["impronta"] != tls["impronta"],
                     next((x for x in righe if "certificato della pagina" in x), "nessuna riga"))
            verifica("certificato rifatto: la pagina non si riapre (si ricollega da sola)",
                     len(pagine) == 1, str(len(pagine)))
        sat.ferma()
        t.join(10)
        try:
            socket.create_connection(("127.0.0.1", porta), timeout=2).close()
            spenta = False
        except OSError:
            spenta = True
        verifica("satellite spento: l'inoltro si spegne con lui", spenta and sat.inoltro is None)
    finally:
        sat.ferma()
        web.ferma()
        srv.ferma()


# ───────────────────────────── browser vero ─────────────────────────────
def browser() -> str | None:
    for c in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if Path(c).is_file():
            return c
    for e in ("msedge", "chromium", "chromium-browser", "google-chrome"):
        if shutil.which(e):
            return shutil.which(e)
    return None


def browser_vero(porta: int, righe: list):
    exe = browser()
    if exe is None:
        print("SALTATA IN PARTE: né Edge né Chromium: salto la pagina nel browser")
        return
    from websockets.sync.client import connect
    # Porta di DevTools scelta dal browser e chiusura dell'albero intero (cdp.py, 06/10)
    from cdp import Browser
    br = Browser(exe, TMP / "profilo", ("--no-proxy-server",
                                        "--host-resolver-rules=MAP calliope.lan 127.0.0.1",
                                        "--ignore-certificate-errors"))
    ws = None
    try:
        try:
            url_dbg = br.ws_pagina()
        except RuntimeError:
            verifica("browser: DevTools risponde", False)
            return
        ws = connect(url_dbg, max_size=2 ** 24).__enter__()     # chiusa nel finally
        n = [0]

        def chiama(metodo, params=None):
            n[0] += 1
            ws.send(json.dumps({"id": n[0], "method": metodo, "params": params or {}}))
            while True:
                m = json.loads(ws.recv(timeout=30))
                if m.get("id") == n[0]:
                    return m

        def valuta(expr):
            r = chiama("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                            "awaitPromise": True}).get("result", {})
            return r.get("result", {}).get("value")
        chiama("Page.enable")
        url = f"https://calliope.lan:{porta}/telefono/"
        chiama("Page.navigate", {"url": url})
        titolo = aspetta(lambda: valuta("document.readyState === 'complete' && "
                                        "location.protocol === 'https:' && document.title"), 15)
        verifica("browser: /telefono aperta con un nome attraverso l'inoltro", bool(titolo),
                 str(titolo))
        tipo = valuta("""new Promise(ok => {
            const ws = new WebSocket(`wss://${location.host}/telefono/ws/abbina`);
            ws.onopen = () => ws.send(JSON.stringify({tipo: "abbina", versione: 2, nome: "edge"}));
            ws.onmessage = e => { ok(JSON.parse(e.data).tipo); ws.close(); };
            ws.onerror = () => ok("errore");
            setTimeout(() => ok("tempo scaduto"), 8000);
        })""")
        verifica("browser: WebSocket del telefono dal browser vero (Origin dell'inoltro)",
                 tipo == "codice", str(tipo))
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass
        br.chiudi()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        parte_filtro()
        parte_tcp()
        d = parte_https()
        parte_satellite(d)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
