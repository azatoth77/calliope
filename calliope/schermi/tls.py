"""
La pagina degli schermi in HTTPS (02/10/2026). Solo libreria standard.

Sulla DGX il server degli schermi ascolta su 0.0.0.0:8770: in http il token della pagina
viaggiava in chiaro sulla rete dell'ufficio, e la futura web app per il telefono (microfono
nel browser) vuole comunque un contesto sicuro. Regole (`modo`):

  - su 127.0.0.1 (o localhost, ::1) resta **http**: il browser dello stesso computer è già
    un contesto sicuro e il token non esce dalla macchina;
  - in rete con il certificato → **https**. Il certificato è quello dei satelliti
    (`satellite.crt` / `satellite.key`, fatti da `calliope satellite --certificato`) o uno
    dedicato (`schermi_tls_cert`, `schermi_tls_chiave`);
  - in rete senza certificato il server **non parte** (capacità «da configurare» con il
    passo), come i satelliti: niente http silenzioso. Solo con `schermi_senza_tls: true`
    parte in http, con un avviso a ogni avvio.

Il certificato è autofirmato, senza CA: un browser qualunque (tablet, TV) mostra l'avviso la
prima volta («La connessione non è privata» → Avanzate → Continua) e poi ricorda
l'eccezione. Il satellite invece non chiede niente al browser: apre la pagina attraverso il
suo ponte TLS (schermi/ponte.py), che verifica l'impronta SHA-256 del certificato ricevuta
sulla connessione già verificata all'abbinamento, e il browser vede http://127.0.0.1 (un
contesto sicuro). L'alternativa provata, `--ignore-certificate-errors-spki-list` con lo
SPKI del certificato e un profilo dedicato, Edge 154 la ignora («Errore di privacy»).
"""

import base64
import hashlib
import os
import ssl
from pathlib import Path

from .. import testi


def _tlv(der: bytes, i: int) -> tuple[int, int, int]:
    """(tag, inizio del contenuto, fine) dell'elemento DER che comincia in `i`."""
    tag, n = der[i], der[i + 1]
    i += 2
    if n & 0x80:
        k = n & 0x7F
        n = int.from_bytes(der[i:i + k], "big")
        i += k
    return tag, i, i + n


def spki_der(cert_der: bytes) -> bytes:
    """La SubjectPublicKeyInfo (DER) di un certificato X.509 (DER), senza librerie:
    Certificate → tbsCertificate → [version], serial, signature, issuer, validity, subject,
    **subjectPublicKeyInfo**."""
    _, s, _ = _tlv(cert_der, 0)                 # Certificate
    _, s, _ = _tlv(cert_der, s)                 # tbsCertificate
    tag, _, e = _tlv(cert_der, s)
    i = e if tag == 0xA0 else s                 # [0] version, facoltativa
    for _ in range(5):                          # serial, signature, issuer, validity, subject
        _, _, i = _tlv(cert_der, i)
    tag, _, e = _tlv(cert_der, i)
    if tag != 0x30:
        raise ValueError("certificato non riconosciuto (SPKI)")
    return cert_der[i:e]


def spki_sha256_b64(cert_der: bytes) -> str:
    """Lo SHA-256 in base64 della chiave pubblica (lo «SPKI pin» dei browser): resta per
    l'impronta della chiave, che non cambia se il certificato si rifà con la stessa chiave."""
    return base64.b64encode(hashlib.sha256(spki_der(cert_der)).digest()).decode("ascii")


def _percorso(cfg, nome: str) -> Path:
    p = Path(str(nome))
    if p.is_absolute():
        return p
    return Path(getattr(cfg, "config_dir", None) or os.getcwd()) / p


def file_tls(cfg) -> tuple[Path, Path]:
    """Certificato e chiave da usare: quelli dedicati, se scritti; poi quelli firmati dalla
    CA di casa per i telefoni (schermi.crt, fatti da `certificato_telefono`), se ci sono;
    altrimenti quelli dei satelliti."""
    cert = getattr(cfg, "schermi_tls_cert", "")
    chiave = getattr(cfg, "schermi_tls_chiave", "")
    if cert and chiave:
        return _percorso(cfg, cert), _percorso(cfg, chiave)
    dedicati = _percorso(cfg, FOGLIA[0]), _percorso(cfg, FOGLIA[1])
    if dedicati[0].is_file() and dedicati[1].is_file():
        return dedicati
    cert = getattr(cfg, "satellite_tls_cert", "")
    chiave = getattr(cfg, "satellite_tls_chiave", "")
    return _percorso(cfg, cert or "satellite.crt"), _percorso(cfg, chiave or "satellite.key")


# ── certificato per i telefoni (03/10) ──
# Un telefono non accetta un certificato autofirmato «per sempre»: Chrome su Android non
# registra il service worker su una pagina con errori di certificato, Safari su iOS non
# ricorda l'eccezione nella web app aggiunta alla Home. Serve una piccola **CA di casa**
# (10 anni, CA:TRUE), da installare una volta sul telefono, e un certificato del server
# firmato da lei: al più 825 giorni (limite di iOS per i certificati TLS), con gli indirizzi
# da cui il telefono raggiunge il server nel SubjectAltName ed extendedKeyUsage serverAuth.
# La chiave della CA resta accanto alla configurazione (fuori da git): serve solo a
# rinnovare il certificato del server senza reinstallare la CA sui telefoni.
CA = ("calliope-ca.crt", "calliope-ca.key")
FOGLIA = ("schermi.crt", "schermi.key")
FOGLIA_GIORNI = 825


def file_ca(cfg) -> Path | None:
    """Il certificato della CA di casa (pubblico: si scarica dal telefono), se c'è."""
    p = _percorso(cfg, CA[0])
    return p if p.is_file() else None


def _nomi_san(hosts) -> list[str]:
    """Le voci del SubjectAltName: IP:… per gli indirizzi, DNS:… per i nomi."""
    import ipaddress
    out = []
    for h in hosts:
        h = str(h or "").strip().strip("[]")
        if not h:
            continue
        try:
            out.append(f"IP:{ipaddress.ip_address(h)}")
        except ValueError:
            if all(c.isalnum() or c in "-." for c in h):
                out.append(f"DNS:{h.lower()}")
    return list(dict.fromkeys(out))


def certificato_telefono(cfg, hosts=(), forza: bool = False, out=print) -> int:
    """CA di casa (se manca) e certificato del server degli schermi firmato da lei, con
    openssl come i satelliti (niente `cryptography`). `hosts`: indirizzi e nomi da cui i
    telefoni raggiungono il server, oltre all'IP di questo computer, al suo nome, a
    localhost e 127.0.0.1."""
    import socket
    import subprocess
    import sys
    import tempfile
    from ..satellite.__main__ import _openssl
    exe = _openssl()
    if exe is None:
        out("Manca openssl: " + ("sudo apt install openssl." if sys.platform != "win32" else
                                 "installa Git per Windows (lo contiene) o OpenSSL."))
        return 1
    ca_crt, ca_key = _percorso(cfg, CA[0]), _percorso(cfg, CA[1])
    crt, key = _percorso(cfg, FOGLIA[0]), _percorso(cfg, FOGLIA[1])
    if crt.is_file() and key.is_file() and ca_crt.is_file() and not forza:
        out(f"Il certificato per i telefoni c'è già ({crt.name}, firmato da {ca_crt.name}).")
        out(f"Impronta SHA-256 della CA (da confrontare sul telefono):\n  {_impronta(ca_crt)}")
        out("Per rifare il certificato del server (per esempio con un indirizzo nuovo): "
            "--certificato --forza --host <IP>. La CA resta la stessa.")
        return 0

    def esegui(args) -> bool:
        r = subprocess.run([exe, *args], capture_output=True, text=True)
        if r.returncode != 0:
            out(f"openssl non è riuscito: {(r.stderr or r.stdout).strip()[-300:]}")
        return r.returncode == 0

    nuova_ca = not (ca_crt.is_file() and ca_key.is_file())
    if nuova_ca and not esegui(
            ["req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
             "-nodes", "-days", "3650", "-sha256", "-subj", "/CN=Calliope CA di casa",
             "-addext", "basicConstraints=critical,CA:TRUE",
             "-addext", "keyUsage=critical,keyCertSign,cRLSign",
             "-keyout", str(ca_key), "-out", str(ca_crt)]):
        return 1
    from . import ip_lan
    try:
        nome_pc = socket.gethostname()
    except OSError:
        nome_pc = ""
    san = _nomi_san([*hosts, ip_lan() or "", nome_pc, "localhost", "127.0.0.1"])
    with tempfile.TemporaryDirectory() as tmp:
        csr, ext = Path(tmp) / "s.csr", Path(tmp) / "ext.cnf"
        ext.write_text("basicConstraints=critical,CA:FALSE\n"
                       "keyUsage=critical,digitalSignature\n"
                       "extendedKeyUsage=serverAuth\n"
                       "subjectKeyIdentifier=hash\n"
                       "authorityKeyIdentifier=keyid\n"
                       f"subjectAltName={','.join(san)}\n", encoding="ascii")
        import secrets
        if not esegui(["req", "-new", "-newkey", "ec", "-pkeyopt",
                       "ec_paramgen_curve:prime256v1", "-nodes", "-subj", "/CN=calliope",
                       "-keyout", str(key), "-out", str(csr)]):
            return 1
        if not esegui(["x509", "-req", "-in", str(csr), "-CA", str(ca_crt), "-CAkey",
                       str(ca_key), "-set_serial", "0x" + secrets.token_hex(12),
                       "-days", str(FOGLIA_GIORNI), "-sha256", "-extfile", str(ext),
                       "-out", str(crt)]):
            return 1
    if sys.platform != "win32":
        for p in (ca_key, key):
            p.chmod(0o600)
    out(("Creata la CA di casa " + ca_crt.name + " e " if nuova_ca else "Rifatto ")
        + f"il certificato degli schermi {crt.name} (vale {FOGLIA_GIORNI} giorni) in "
        f"{crt.parent}.")
    out("Indirizzi nel certificato: " + ", ".join(s.split(":", 1)[1] for s in san))
    # I nomi scelti a mano (calliope.lan) passano il controllo dell'Host della pagina solo se
    # sono anche in schermi_nomi (difesa dal DNS rebinding); gli IP passano sempre
    nomi = [v.split(":", 1)[1] for v in _nomi_san(hosts) if v.startswith("DNS:")]
    mancano = [n for n in nomi if n not in {str(x).lower() for x in
                                            (getattr(cfg, "schermi_nomi", None) or ())}]
    if mancano:
        out("Per aprire la pagina con " + ", ".join(mancano) + " aggiungi in "
            "calliope.locale.yaml, sezione schermi: schermi_nomi: [" + ", ".join(mancano)
            + "] (gli indirizzi IP non ne hanno bisogno).")
    out(f"Impronta SHA-256 della CA (sul telefono, nei dettagli del profilo o del "
        f"certificato):\n  {_impronta(ca_crt)}")
    out("Riavvia Calliope: la pagina degli schermi e del telefono usa questo certificato. "
        "Sul telefono apri https://<indirizzo>:<porta>/telefono e scarica la CA dal link "
        "«certificato» (passi in prove/LEGGIMI.md). I satelliti non cambiano: ricevono "
        "l'impronta nuova sulla loro connessione.")
    return 0


def _impronta(path: Path) -> str:
    der = ssl.PEM_cert_to_DER_cert(path.read_text(encoding="ascii"))
    h = hashlib.sha256(der).hexdigest().upper()
    return ":".join(h[i:i + 2] for i in range(0, len(h), 2))


def carica(cfg) -> dict | None:
    """{"cert", "chiave", "spki", "impronta"} se i file ci sono, None se non ci sono.
    ValueError se ci sono ma non si caricano."""
    cert, chiave = file_tls(cfg)
    if not (cert.is_file() and chiave.is_file()):
        return None
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert), str(chiave))
        der = ssl.PEM_cert_to_DER_cert(cert.read_text(encoding="ascii"))
        spki = spki_sha256_b64(der)
    except (ssl.SSLError, OSError, ValueError, IndexError) as e:
        raise ValueError(f"certificato o chiave degli schermi non validi "
                         f"({e.__class__.__name__})") from e
    h = hashlib.sha256(der).hexdigest().upper()
    return {"cert": str(cert), "chiave": str(chiave), "spki": spki,
            "impronta": ":".join(h[i:i + 2] for i in range(0, len(h), 2))}


def solo_locale(cfg) -> bool:
    return testi.solo_locale(str(getattr(cfg, "schermi_indirizzo", "127.0.0.1") or "127.0.0.1"))


def modo(cfg) -> tuple[str, dict | None]:
    """("http" | "https" | "rifiuta", file del certificato o None). ValueError se il
    certificato c'è ma è rovinato (in rete: meglio fermarsi che andare in chiaro)."""
    if solo_locale(cfg):
        return "http", None
    tls = carica(cfg)
    if tls is not None:
        return "https", tls
    if getattr(cfg, "schermi_senza_tls", False):
        return "http", None
    return "rifiuta", None


PASSO_CERTIFICATO = ("In rete la pagina degli schermi va in HTTPS: crea il certificato con "
                     "«calliope satellite --certificato» (o python -m calliope.satellite "
                     "--certificato) e riavviami. Per vederla solo da questo computer: "
                     "schermi_indirizzo: 127.0.0.1. Solo come ultima scelta, in chiaro: "
                     "schermi_senza_tls: true in calliope.locale.yaml.")
