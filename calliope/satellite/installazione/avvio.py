#!/usr/bin/env python3
"""
Avvio e aggiornamenti di un satellite installato con un comando dalla pagina /satellite
(03/10/2026). Solo libreria standard: gira con il Python di base installato da uv, non con il
venv di una versione, e non dipende dalla versione del satellite che sta avviando.

    avvio.py                      avvia il satellite (avvia.cmd, avvio automatico all'accesso)
    avvio.py prepara --pacchetto ZIP --sha256 HEX [--attiva] [--prova]
                                  prepara una versione dal pacchetto del server: estrazione in
                                  versioni/<versione>/, venv con uv dalle versioni bloccate,
                                  verifica a secco. --attiva: la mette in uso (installazione);
                                  --prova: la propone all'avvio come versione in prova

Come è fatta un'installazione (tutto nella cartella dell'utente, niente amministratore):

    %LOCALAPPDATA%\\Calliope\\satellite\\
        uv\\uv.exe                 uv (binario ufficiale, versione e SHA-256 fissati)
        python\\                   il Python di uv (UV_PYTHON_INSTALL_DIR)
        cache\\                    la cache di uv (wheel già scaricati: venv nuovi offline)
        versioni\\<versione>\\      il codice del satellite di una versione, con il suo .venv
        attuale, precedente       la versione in uso e quella di prima
        prova.json                una versione nuova in prova (da confermare)
        rifiutate.json            versioni tornate indietro (non si riprovano per 6 ore)
        dati\\                     calliope.yaml, calliope.locale.yaml, satellite.json (token)
        avvio.py, avvia.cmd       questo file e il suo lanciatore
        avvio.log                 cambi di versione e ritorni indietro

Aggiornamento (lo stesso schema di `calliope aggiorna` sulla DGX): il server annuncia la sua
versione nel benvenuto; il satellite, se è indietro, scarica il pacchetto (verificato con lo
SHA-256 ricevuto sulla connessione autenticata), lo prepara qui accanto con `prepara --prova`
ed esce con il codice 75 quando nessuno sta parlando. Questo avvio passa alla versione nuova
e aspetta che si ricolleghi al server (il satellite scrive `confermata-<versione>`) entro
`PROVA_S`: se non succede, o se esce prima, torna da solo alla versione di prima.
Il satellite avviato dal repository (python -m calliope.satellite) non passa da qui e non si
aggiorna da solo.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

RIAVVIA = 75                 # il satellite ha preparato una versione nuova: riavviami
PROVA_S = 180.0              # entro quanto la versione nuova deve ricollegarsi al server
RIFIUTO_S = 6 * 3600.0       # una versione tornata indietro non si riprova prima
VERSIONI_TENUTE = 3
ATTESE_CADUTA = (2, 5, 15, 30, 60)


def _ora() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _scrivi(path: Path, testo: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(testo, encoding="utf-8")
    os.replace(tmp, path)


def _leggi_json(path: Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blocco in iter(lambda: f.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


class Errore(Exception):
    """Un errore da dire così com'è, senza traccia."""


class Installazione:
    def __init__(self, radice: Path, out=print):
        self.radice = Path(radice)
        self.versioni = self.radice / "versioni"
        self.dati = self.radice / "dati"
        self.out = out

    # ── puntatori ──
    def _leggi(self, nome: str) -> str | None:
        try:
            return (self.radice / nome).read_text(encoding="utf-8").strip() or None
        except OSError:
            return None

    def attuale(self) -> str | None:
        return self._leggi("attuale")

    def precedente(self) -> str | None:
        return self._leggi("precedente")

    def attiva(self, vid: str):
        vecchia = self.attuale()
        if vecchia and vecchia != vid:
            _scrivi(self.radice / "precedente", vecchia + "\n")
        _scrivi(self.radice / "attuale", vid + "\n")

    def completa(self, vid: str | None) -> bool:
        if not vid:
            return False
        d = self.versioni / vid
        return ((d / "VERSIONE.json").is_file() and not (d / ".incompleta").exists()
                and self.python_di(vid).is_file())

    def python_di(self, vid: str) -> Path:
        sub = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
        return self.versioni / vid / ".venv" / sub[0] / sub[1]

    def log(self, msg: str):
        self.out(f"[AVVIO] {msg}")
        try:
            with open(self.radice / "avvio.log", "a", encoding="utf-8") as f:
                f.write(f"{_ora()}  {msg}\n")
        except OSError:
            pass

    # ── uv ──
    def uv(self) -> str:
        exe = self.radice / "uv" / ("uv.exe" if os.name == "nt" else "uv")
        return str(exe) if exe.is_file() else (shutil.which("uv") or "uv")

    def ambiente_uv(self) -> dict:
        env = dict(os.environ, UV_PYTHON_INSTALL_DIR=str(self.radice / "python"),
                   UV_CACHE_DIR=str(self.radice / "cache"), UV_NO_CONFIG="1",
                   UV_NO_PROGRESS="1")
        for k in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "UV_INDEX_URL",
                  "UV_EXTRA_INDEX_URL", "PIP_INDEX_URL"):
            env.pop(k, None)
        return env

    # ── preparazione di una versione ──
    def prepara(self, pacchetto: Path, sha256: str, attiva=False, prova=False,
                uv=None, verifica=None) -> str:
        """Estrae il pacchetto in versioni/<versione>/ e gli crea il venv con uv. Non cambia
        la versione in uso (salvo `attiva`). Restituisce la versione."""
        pacchetto = Path(pacchetto)
        if sha256_file(pacchetto).lower() != sha256.strip().lower():
            raise Errore("il pacchetto non corrisponde allo SHA-256 atteso: non lo uso")
        with zipfile.ZipFile(pacchetto) as z:
            try:
                info = json.loads(z.read("VERSIONE.json"))
            except (KeyError, ValueError):
                raise Errore("il pacchetto non ha VERSIONE.json") from None
            vid = str(info.get("versione") or "")
            if not vid or not all(c in "0123456789abcdef" for c in vid):
                raise Errore("versione del pacchetto non valida")
            dest = self.versioni / vid
            if self.completa(vid):
                self.log(f"versione {vid} già pronta")
            else:
                if dest.exists():
                    shutil.rmtree(dest)
                dest.mkdir(parents=True)
                (dest / ".incompleta").write_text(_ora(), encoding="utf-8")
                try:
                    for nome in z.namelist():
                        p = Path(nome)
                        if p.is_absolute() or ".." in p.parts or ":" in nome or "\\" in nome:
                            raise Errore(f"nome non ammesso nel pacchetto: {nome}")
                    z.extractall(dest)
                    self._ambiente(dest, info, uv)
                    (verifica or self._verifica)(vid)
                    (dest / ".incompleta").unlink()
                except BaseException:
                    shutil.rmtree(dest, ignore_errors=True)
                    raise
        if attiva:
            self.attiva(vid)
        if prova:
            da = self.attuale()
            if da != vid:
                _scrivi(self.radice / "prova.json", json.dumps(
                    {"versione": vid, "da": da, "sha256": sha256.lower(), "preparata": _ora()},
                    indent=2) + "\n")
        return vid

    def _uv(self, uv, args: list[str], timeout=1800, offline_prima=False):
        cmd = list(uv or [self.uv()])
        tentativi = ([cmd + args[:2] + ["--offline"] + args[2:]] if offline_prima else []) \
            + [cmd + args]
        for i, c in enumerate(tentativi):
            r = subprocess.run(c, env=self.ambiente_uv(), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout)
            if r.returncode == 0:
                return
            if i == len(tentativi) - 1:
                righe = (r.stderr or r.stdout or "").strip().splitlines()
                raise Errore(f"uv {' '.join(args[:2])} non è riuscito"
                             + (f": {righe[-1]}" if righe else ""))

    def _ambiente(self, dest: Path, info: dict, uv=None):
        python = str(info.get("python") or "3.14")
        self.log(f"preparo la versione {dest.name} (Python {python})…")
        self._uv(uv, ["python", "install", python, "--no-bin", "--no-registry"])
        self._uv(uv, ["venv", "--managed-python", "--python", python, str(dest / ".venv")])
        py = str(self.python_di(dest.name))
        req = dest / str(info.get("requisiti") or "requisiti.txt")
        nodeps = dest / str(info.get("senza_dipendenze") or "requisiti-senza-dipendenze.txt")
        # Prima dalla cache (un aggiornamento con le stesse librerie non tocca la rete)
        self._uv(uv, ["pip", "install", "--python", py, "--require-hashes",
                      "--only-binary", ":all:", "-r", str(req)], offline_prima=True)
        if nodeps.is_file():
            self._uv(uv, ["pip", "install", "--python", py, "--require-hashes",
                          "--only-binary", ":all:", "--no-deps", "-r", str(nodeps)],
                     offline_prima=True)

    def _verifica(self, vid: str):
        """Prova a secco: il codice del satellite si importa con il venv nuovo."""
        r = subprocess.run([str(self.python_di(vid)), "-c",
                            "import calliope.satellite.client, calliope.satellite.esecutore"],
                           cwd=self.versioni / vid, env=self.ambiente(vid), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=300)
        if r.returncode != 0:
            righe = (r.stderr or "").strip().splitlines()
            raise Errore("la versione nuova non si importa: " + (righe[-1] if righe else "?"))

    # ── esecuzione ──
    def ambiente(self, vid: str) -> dict:
        env = dict(os.environ, PYTHONUTF8="1",
                   CALLIOPE_SATELLITE_INSTALLAZIONE=str(self.radice),
                   CALLIOPE_SATELLITE_VERSIONE=vid,
                   CALLIOPE_CONFIG=str(self.dati / "calliope.yaml"))
        for k in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME"):
            env.pop(k, None)
        return env

    def comando(self, vid: str) -> list[str]:
        return [str(self.python_di(vid)), "-u", "-m", "calliope.satellite"]

    def prova(self) -> dict:
        return _leggi_json(self.radice / "prova.json")

    def _rifiuta(self, vid: str):
        f = self.radice / "rifiutate.json"
        d = _leggi_json(f)
        d[vid] = time.time()
        _scrivi(f, json.dumps(d, indent=2) + "\n")

    def _conferma(self, vid: str):
        (self.radice / "prova.json").unlink(missing_ok=True)
        (self.radice / f"confermata-{vid}").unlink(missing_ok=True)
        self.log(f"versione {vid} confermata: si è ricollegata al server")
        # L'avvio stesso si aggiorna solo da una versione confermata (come il gestore della
        # DGX), e vale dal prossimo avvio
        nuovo = self.versioni / vid / "calliope" / "satellite" / "installazione" / "avvio.py"
        mio = self.radice / "avvio.py"
        try:
            if nuovo.is_file() and (not mio.is_file()
                                    or nuovo.read_bytes() != mio.read_bytes()):
                tmp = mio.with_name("avvio.py.tmp")
                shutil.copy2(nuovo, tmp)
                os.replace(tmp, mio)
                self.log("avvio aggiornato (vale dal prossimo avvio)")
        except OSError as e:
            self.log(f"avvio non aggiornato ({e})")
        self.pulisci()

    def _torna(self, vid: str, motivo: str):
        p = self.prova()
        da = p.get("da")
        self._rifiuta(vid)
        (self.radice / "prova.json").unlink(missing_ok=True)
        if da and self.completa(da):
            _scrivi(self.radice / "attuale", da + "\n")
            self.log(f"la versione {vid} {motivo}: torno a {da} (non la riprovo per "
                     f"{RIFIUTO_S / 3600:.0f} ore)")
        else:
            self.log(f"la versione {vid} {motivo}, e non c'è una versione di prima da usare")

    def pulisci(self):
        tieni = {self.attuale(), self.precedente()}
        if not self.versioni.is_dir():
            return
        tutte = sorted((p for p in self.versioni.iterdir() if p.is_dir()),
                       key=lambda p: p.stat().st_mtime)
        for p in reversed(tutte):
            if len(tieni - {None}) >= VERSIONI_TENUTE:
                break
            if self.completa(p.name):
                tieni.add(p.name)
        for p in tutte:
            if p.name not in tieni:
                shutil.rmtree(p, ignore_errors=True)

    def _scegli(self) -> tuple[str | None, bool]:
        """(versione da avviare, in prova?). Una versione in prova preparata dal satellite
        diventa quella in uso qui."""
        cur = self.attuale()
        p = self.prova()
        nuova = p.get("versione")
        if nuova and nuova != cur:
            if self.completa(nuova):
                self.attiva(nuova)
                p["inizio"] = _ora()
                _scrivi(self.radice / "prova.json", json.dumps(p, indent=2) + "\n")
                self.log(f"passo alla versione {nuova} (da {cur}): in prova per "
                         f"{self.prova_s:.0f} s")
                return nuova, True
            (self.radice / "prova.json").unlink(missing_ok=True)
        return cur, bool(nuova and nuova == cur)

    def esegui(self, prova_s: float = PROVA_S, comando=None, attese=ATTESE_CADUTA) -> int:
        """Il ciclo dell'avvio: finché il satellite non esce da sé (0) o con Ctrl+C."""
        self.prova_s = prova_s
        comando = comando or self.comando
        cadute = 0
        while True:
            vid, in_prova = self._scegli()
            if not vid or not self.completa(vid):
                self.log("nessuna versione del satellite pronta: rifai l'installazione dalla "
                         "pagina /satellite del server")
                return 1
            try:
                rc, tornata = self._lancia(vid, in_prova, comando)
            except KeyboardInterrupt:
                return 0
            if tornata:
                cadute = 0
                continue
            if rc == RIAVVIA:
                cadute = 0
                continue
            if rc == 0:
                return 0
            attesa = attese[min(cadute, len(attese) - 1)]
            cadute += 1
            self.log(f"il satellite è uscito con il codice {rc}: lo riavvio tra {attesa} s")
            try:
                time.sleep(attesa)
            except KeyboardInterrupt:
                return 0

    def _lancia(self, vid: str, in_prova: bool, comando) -> tuple[int, bool]:
        proc = subprocess.Popen(comando(vid), cwd=self.versioni / vid, env=self.ambiente(vid))
        inizio = time.monotonic()
        conferma = self.radice / f"confermata-{vid}"
        try:
            while True:
                rc = proc.poll()
                if in_prova:
                    if conferma.exists():
                        self._conferma(vid)
                        in_prova = False
                    elif rc not in (None, 0):
                        self._torna(vid, f"è uscita con il codice {rc} prima di ricollegarsi")
                        return rc, True
                    elif rc is None and time.monotonic() - inizio > self.prova_s:
                        self._ferma(proc)
                        self._torna(vid, f"non si è ricollegata al server entro "
                                         f"{self.prova_s:.0f} s")
                        return -1, True
                if rc is not None:
                    return rc, False
                time.sleep(0.2)
        except KeyboardInterrupt:
            # Ctrl+C arriva anche al satellite (stessa console): lo si aspetta un poco
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._ferma(proc)
            raise

    @staticmethod
    def _ferma(proc):
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


class _Lucchetto:
    """Un solo avvio per installazione (l'avvio automatico e un doppio clic insieme)."""

    def __init__(self, path: Path):
        self.path = path
        self.f = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.path, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.f.close()
            self.f = None
        return self.f is not None

    def __exit__(self, *exc):
        if self.f is not None:
            self.f.close()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    radice = Path(os.environ.get("CALLIOPE_SATELLITE_RADICE") or Path(__file__).resolve().parent)
    inst = Installazione(radice)
    if argv and argv[0] == "prepara":
        p = argparse.ArgumentParser(prog="avvio.py prepara")
        p.add_argument("--pacchetto", required=True)
        p.add_argument("--sha256", required=True)
        p.add_argument("--attiva", action="store_true")
        p.add_argument("--prova", action="store_true")
        a = p.parse_args(argv[1:])
        try:
            vid = inst.prepara(Path(a.pacchetto), a.sha256, attiva=a.attiva, prova=a.prova)
        except (Errore, OSError, subprocess.TimeoutExpired, zipfile.BadZipFile) as e:
            print(f"Errore: {e}", file=sys.stderr)
            return 1
        print(vid)
        return 0
    prova_s = float(os.environ.get("CALLIOPE_SATELLITE_PROVA_S") or PROVA_S)
    with _Lucchetto(radice / "avvio.lock") as mio:
        if not mio:
            print("[AVVIO] Il satellite è già acceso (un altro avvio.py tiene il lucchetto).")
            return 0
        return inst.esegui(prova_s=prova_s)


if __name__ == "__main__":
    sys.exit(main())
