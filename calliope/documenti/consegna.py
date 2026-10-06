"""
Consegna del file: dove finisce un documento appena generato.

Con Calliope sul portatile il file si scrive lì, nella cartella dei documenti
(`LocalDelivery`). Con Calliope sulla DGX (03/10) `RemoteDelivery` lo manda al satellite
(calliope/satellite/esecutore.py), che lo salva nella cartella Calliope dei Documenti del
portatile e risponde con lo stesso dict: la generazione (scrittore.py, render.py) non cambia.
Per questo `deliver` prende solo dati semplici (nome, estensione, byte) e restituisce un
riferimento opaco (`rif`): per il file locale il percorso, per quello del satellite
«sat:<nome del file>». `apri`, se c'è, è ciò che si dà a `PCExecutor.offri_file` perché
«aprilo» lo apra (il percorso in locale, una maniglia del satellite in remoto); `dove` dice
dove è finito, se diverso da `where()`.

Regole:
- mai sovrascrivere un file che non è nostro: un nome già preso diventa «Nome (2)»;
- rigenerando dopo una modifica si riscrive lo stesso file, ma se nel frattempo è stato
  cambiato a mano (data di modifica diversa da quella registrata) o è aperto in Word
  (bloccato) la nuova versione va in un file nuovo: le modifiche fatte a mano non si
  perdono, e l'utente lo sente dire.
"""

import os
import sys
import tempfile
from pathlib import Path


def documents_folder() -> Path:
    """La cartella Documenti dell'utente, chiesta a Windows (known folder
    FOLDERID_Documents): segue lo spostamento su OneDrive o su un altro disco. Su Linux
    quella di xdg-user-dirs (`xdg_documents`); altrimenti, o se la chiamata non va,
    ~/Documents."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

            # FOLDERID_Documents = {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
            fid = GUID(0xFDD39AD0, 0x238F, 0x46AF,
                       (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            out = ctypes.c_wchar_p()
            shell32, ole32 = ctypes.windll.shell32, ctypes.windll.ole32
            if shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(out)) == 0:
                try:
                    return Path(out.value)
                finally:
                    ole32.CoTaskMemFree(out)
        except Exception:  # noqa: BLE001 — si ripiega sulla cartella di casa
            pass
        return Path.home() / "Documents"
    return xdg_documents() or Path.home() / "Documents"


def xdg_documents(config_home: Path | None = None) -> Path | None:
    """Linux (DGX OS, 02/10): la cartella dei documenti di xdg-user-dirs, letta da
    ~/.config/user-dirs.dirs come fa `xdg-user-dir DOCUMENTS` (senza lanciarlo): con il
    desktop in italiano è «~/Documenti», non «~/Documents». La variabile
    XDG_DOCUMENTS_DIR vince. None se non è impostata o punta alla home stessa (xdg-user-dirs
    usa la home per dire «cartella disattivata»)."""
    home = Path.home()
    raw = os.environ.get("XDG_DOCUMENTS_DIR")
    if not raw:
        base = config_home or Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
        try:
            text = (base / "user-dirs.dirs").read_text(encoding="utf-8")
        except OSError:
            return None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("XDG_DOCUMENTS_DIR="):
                raw = line.split("=", 1)[1].strip().strip('"')
        if not raw:
            return None
    raw = raw.replace("${HOME}", str(home)).replace("$HOME", str(home))
    path = Path(raw).expanduser()
    if not path.is_absolute() or path == home:
        return None
    return path


def default_folder() -> Path:
    return documents_folder() / "Calliope"


def unique_path(folder: Path, stem: str, ext: str) -> Path:
    """«Nome.ext», altrimenti «Nome (2).ext», «Nome (3).ext»…: mai sovrascrivere."""
    path = folder / f"{stem}.{ext}"
    n = 2
    while path.exists():
        path = folder / f"{stem} ({n}).{ext}"
        n += 1
    return path


def _write_atomic(path: Path, data: bytes):
    """Scrive in un file temporaneo accanto e poi lo sostituisce: un file a metà non resta
    mai. Se il file di destinazione è aperto in Word, os.replace solleva PermissionError."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".calliope-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class LocalDelivery:
    """Scrive i documenti in una cartella di questo PC."""

    def __init__(self, folder: str | Path | None = None):
        self.default = folder in (None, "")
        self.folder = Path(folder) if folder else default_folder()

    def where(self) -> str:
        """Dove, detto a voce (mai il percorso: si legge male e non serve)."""
        if self.default:
            return "nella cartella Calliope dei Documenti"
        return f"nella cartella {self.folder.name or self.folder}"

    def deliver(self, stem: str, ext: str, data: bytes, replace: str | None = None,
                mtime: float | None = None) -> dict:
        """Salva i byte. `replace` è il `rif` della versione precedente (modifica), con la
        sua data di modifica registrata. {"ok", "rif", "nome_file", "mtime", "motivo"}."""
        self.folder.mkdir(parents=True, exist_ok=True)
        reason = None
        target = None
        if replace:
            old = Path(replace)
            if not old.exists():
                target = old if old.parent == self.folder else None   # cancellato: si rifà
            elif mtime is not None and abs(old.stat().st_mtime - mtime) > 1.0:
                reason = "modificato"                 # cambiato a mano dopo la creazione
            else:
                target = old
        if target is not None:
            try:
                _write_atomic(target, data)
            except PermissionError:
                reason, target = "aperto", None       # aperto in Word o in Excel
        if target is None:
            base = Path(replace).stem if replace else stem
            if replace and base.endswith(")") and " (" in base:
                base = base.rsplit(" (", 1)[0]
            target = unique_path(self.folder, base, ext)
            _write_atomic(target, data)
        return {"ok": True, "rif": str(target), "nome_file": target.name,
                "mtime": target.stat().st_mtime, "motivo": reason}


class RemoteDelivery:
    """Manda i documenti al satellite collegato (l'esecutore del suo PC). Se nessun satellite
    li riceve, o la consegna non riesce, il file resta su questo computer (`locale`) e la
    frase lo dice: il documento non si perde mai."""

    RIF = "sat:"

    def __init__(self, server, locale: "LocalDelivery | None" = None, nome: str = "portatile",
                 timeout_s: float = 10.0, velocita_mb_s: float = 1.0):
        self.server = server
        self.locale = locale or LocalDelivery()
        self.nome = nome
        # Tempo massimo: una base più il tempo di trasferimento a `velocita_mb_s` (prudente:
        # in VPN qualche MB/s, in LAN molti di più). Il documento si consegna in secondo
        # piano (Documenti._pool): la voce non lo aspetta oltre documenti_attesa_s
        self.timeout_s = float(timeout_s)
        self.velocita_mb_s = float(velocita_mb_s)
        self.ultima: dict = {}              # l'ultima consegna (prove e registro)

    @property
    def folder(self) -> Path:
        """La cartella di riserva, su questo computer."""
        return self.locale.folder

    def where(self) -> str:
        return f"nella cartella Calliope dei Documenti del {self.nome}"

    def _sul_server(self, stem, ext, data, replace, mtime, perche: str) -> dict:
        if replace and str(replace).startswith(self.RIF):
            replace, mtime = None, None     # la versione di prima sta sul satellite
        d = self.locale.deliver(stem, ext, data, replace=replace, mtime=mtime)
        d["dove"] = f"sul server, perché {perche}"
        d["remoto"] = False
        self.ultima = {"remoto": False, "motivo": perche}
        return d

    def deliver(self, stem: str, ext: str, data: bytes, replace: str | None = None,
                mtime: float | None = None) -> dict:
        from ..pc.remoto import per_pc
        c = per_pc(self.server)
        if c is None or not (getattr(c, "esecutore", None) or {}).get("file"):
            perche = (f"il {self.nome} non è collegato" if c is None else
                      f"il satellite collegato non riceve documenti")
            return self._sul_server(stem, ext, data, replace, mtime, perche)
        sostituisci = replace if replace and str(replace).startswith(self.RIF) else None
        attesa = self.timeout_s + len(data) / (self.velocita_mb_s * 1024 * 1024)
        try:
            r = c.consegna_file(stem, ext, data, sostituisci=sostituisci,
                                mtime=mtime if sostituisci else None, timeout=attesa)
        except TimeoutError:
            return self._sul_server(stem, ext, data, replace, mtime,
                                    f"il {self.nome} non ha risposto in tempo")
        except ConnectionError:
            return self._sul_server(stem, ext, data, replace, mtime,
                                    f"il {self.nome} si è scollegato durante l'invio")
        if not r.get("ok"):
            return self._sul_server(stem, ext, data, replace, mtime,
                                    f"il {self.nome} non l'ha salvato ({r.get('errore')})")
        self.ultima = {"remoto": True, "byte": len(data)}
        return {"ok": True, "rif": str(r.get("rif") or ""), "nome_file": str(r.get("nome_file")),
                "mtime": r.get("mtime"), "motivo": r.get("motivo"),
                "apri": r.get("maniglia"), "remoto": True}
