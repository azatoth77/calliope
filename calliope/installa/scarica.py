"""
Scaricamento di un file del catalogo: solo verso le origini ammesse, con ripresa,
checksum e spostamento atomico.

- Origine: https verso un host dell'azione, anche dopo ogni reindirizzamento (seguiti a
  mano, al massimo 5). http solo verso 127.0.0.1 (il server finto delle prove).
- Ripresa: si scrive in <file>.part; se c'è già, si chiede il resto con l'intestazione
  HTTP Range. Un server che risponde 200 invece di 206 fa ripartire da capo.
- Fine: dimensione uguale al catalogo, SHA-256 uguale al catalogo, poi os.replace sul nome
  vero (atomico sullo stesso disco). Un checksum sbagliato cancella il .part: il file è da
  riscaricare, non da riprendere.
- Annullo: un threading.Event controllato a ogni blocco; il .part resta per la ripresa.
"""

import hashlib
import os
import threading
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from .catalogo import FileCat

LOCALI = ("127.0.0.1",)
BLOCCO = 1 << 20


class ErroreInstallazione(Exception):
    """Errore con un codice stabile e una frase per la voce."""

    def __init__(self, codice: str, frase: str):
        super().__init__(frase)
        self.codice, self.frase = codice, frase


class Annullato(ErroreInstallazione):
    def __init__(self):
        super().__init__("annullato", "Download annullato.")


def controlla_url(url: str, hosts) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    ok_scheme = parts.scheme == "https" or (parts.scheme == "http" and host in LOCALI)
    if not ok_scheme or host not in tuple(hosts or ()):
        raise ErroreInstallazione("origine_non_ammessa",
                                  f"L'origine {host or url} non è nel catalogo: non scarico.")
    return url


def richiesta(http, method: str, url: str, hosts, headers=None, stream: bool = False):
    """Una richiesta che segue i reindirizzamenti solo verso host ammessi."""
    for _ in range(6):
        controlla_url(url, hosts)
        req = http.build_request(method, url, headers=headers or {})
        r = http.send(req, stream=stream, follow_redirects=False)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
            nxt = urljoin(url, r.headers["location"])
            r.close()
            url = nxt
            continue
        return r
    raise ErroreInstallazione("troppi_rimandi", "L'origine rimanda troppe volte: non scarico.")


def sha256_file(path, cancel: threading.Event | None = None, progress=None) -> str:
    h = hashlib.sha256()
    done = 0
    with open(path, "rb") as f:
        while chunk := f.read(4 * BLOCCO):
            if cancel is not None and cancel.is_set():
                raise Annullato()
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done)
    return h.hexdigest()


def part_path(dest) -> Path:
    d = Path(dest)
    return d.with_name(d.name + ".part")


def scarica_file(http, f: FileCat, hosts, cancel: threading.Event | None = None,
                 progress=None, verifica=None) -> str:
    """Scarica `f` in f.dest. `progress(byte_scritti_del_file)`; `verifica(byte)` durante il
    checksum. Restituisce lo SHA-256. Solleva ErroreInstallazione (o Annullato)."""
    dest = Path(f.dest)
    part = part_path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    offset = part.stat().st_size if part.exists() else 0
    if f.size is not None and offset > f.size:
        part.unlink()
        offset = 0
    try:
        _scarica(http, f, hosts, part, offset, cancel, progress)
    except ErroreInstallazione as e:
        if e.codice == "dimensione":
            part.unlink(missing_ok=True)      # dati sbagliati: non si riprendono
        raise
    sha = sha256_file(part, cancel, verifica)
    if f.sha256 and sha.lower() != f.sha256.lower():
        part.unlink(missing_ok=True)
        raise ErroreInstallazione("checksum", "Il file scaricato non corrisponde al checksum "
                                  "del catalogo: l'ho cancellato.")
    os.replace(part, dest)
    return sha


def _scarica(http, f: FileCat, hosts, part: Path, offset: int, cancel, progress):
    if f.size is None or offset < f.size:
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        r = richiesta(http, "GET", f.url, hosts, headers=headers, stream=True)
        try:
            if r.status_code == 416 and offset:
                # Range oltre la fine: il .part è già intero (o il server non lo sa); si
                # verifica sotto
                pass
            elif r.status_code == 206 and offset:
                start = (r.headers.get("content-range") or "").split(" ")[-1].split("-")[0]
                if start.strip() != str(offset):
                    raise ErroreInstallazione("ripresa", "Il server ha risposto con un pezzo "
                                              "sbagliato: riprova più tardi.")
                offset = _scrivi(r, part, "ab", offset, f, cancel, progress)
            elif r.status_code == 200:
                offset = _scrivi(r, part, "wb", 0, f, cancel, progress)
            else:
                raise ErroreInstallazione("http", f"Il server ha risposto con l'errore "
                                          f"{r.status_code}.")
        finally:
            r.close()
    if f.size is not None and part.stat().st_size != f.size:
        raise ErroreInstallazione("dimensione", "Il file scaricato non ha la dimensione "
                                  "attesa: riprova più tardi.")


def _scrivi(r, part: Path, mode: str, offset: int, f: FileCat, cancel, progress) -> int:
    with open(part, mode) as out:
        # Senza dimensione del blocco: i dati si scrivono appena arrivano, così una
        # connessione che cade a metà lascia nel .part tutto quello già ricevuto
        for chunk in r.iter_bytes():
            if cancel is not None and cancel.is_set():
                raise Annullato()
            offset += len(chunk)
            if f.size is not None and offset > f.size:
                raise ErroreInstallazione("dimensione", "Il server manda più dati del "
                                          "previsto: interrompo.")
            out.write(chunk)
            if progress:
                progress(offset)
    return offset
