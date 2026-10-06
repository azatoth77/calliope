"""
Esecutore locale per Windows: le capacità di PCExecutor sul PC dove gira Calliope.

Letture e azioni con API dedicate, niente tasti simulati (docs/ricerche/2026-09-26-
controllo-pc.md, sezione 2.2):
- volume: Core Audio (pycaw su comtypes), endpoint tenuto aperto;
- musica: GlobalSystemMediaTransportControls di WinRT (winrt-Windows.Media.Control);
- luminosità: WMI dei portatili / DDC-CI (screen_brightness_control);
- batteria e programmi: psutil, EnumWindows (pywin32);
- blocco: LockWorkStation; schermo bloccato: nome del desktop di input;
- ricerca: indice di Windows Search via ADODB (SQL su SYSTEMINDEX);
- app e file: os.startfile, solo su voci del catalogo o risultati di una ricerca.

Tutte le chiamate native passano da un solo thread di lavoro, con COM inizializzato una
volta: gli oggetti COM e WinRT restano aperti lì (volume con l'endpoint in cache:
~0,02 ms contro ~57 ms riaprendolo a ogni lettura) e non importa da quale thread
Calliope chiami. Ogni libreria è facoltativa: se manca, manca solo quella capacità.
"""

import asyncio
import ctypes
import datetime
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes

from .base import PCExecutor, errore, modo_apertura

TIMEOUT_S = 5.0
# La preparazione costa ~0,2 s da sola, ma all'avvio compete con il caricamento degli
# altri modelli: meglio aspettare qualche secondo che perdere tutto il controllo del PC
SETUP_TIMEOUT_S = 30.0

# Parole che nei nomi dei file non aiutano («il file della bolletta» → «bolletta»)
_STOP = {"il", "lo", "la", "i", "gli", "le", "un", "una", "uno", "di", "del", "della",
         "dello", "dei", "degli", "delle", "da", "dal", "dalla", "in", "nel", "nella",
         "con", "per", "su", "sul", "sulla", "a", "al", "alla", "e", "ed", "o", "che",
         "file", "documento", "documenti", "cartella", "mio", "mia", "miei", "mie"}
_KIND = {"documento": "System.Kind = 'document'", "pdf": "System.FileExtension = '.pdf'",
         "foto": "System.Kind = 'picture'", "musica": "System.Kind = 'music'",
         "video": "System.Kind = 'video'"}
# Nomi leggibili di alcune app multimediali (AUMID → nome detto)
_MEDIA_APPS = {"msedge": "Edge", "chrome": "Chrome", "firefox": "Firefox",
               "spotify": "Spotify", "zunemusic": "Lettore multimediale",
               "zunevideo": "Film e TV", "vlc": "VLC", "windowsmediaplayer": "Windows Media Player"}


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def _to_local_iso(value) -> str | None:
    """Data di Windows Search (UTC) → «2026-09-12T10:30» locale."""
    if not isinstance(value, datetime.datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone().replace(tzinfo=None).isoformat(timespec="minutes")


def _url_to_path(url: str) -> str:
    """«file:C:/Users/x/Documenti%20vari/a.pdf» → percorso vero sul disco."""
    if not url.lower().startswith("file:"):
        return ""
    return os.path.normpath(urllib.parse.unquote(url[5:].lstrip("/")))


# File che nessuno chiede a voce: il 27/09 una ricerca dava «claude.json» e «desktop.ini»
_SYSTEM_EXT = frozenset({"ini", "db", "dat", "tmp", "lnk", "log", "sys", "dll", "json",
                         "lock", "etl", "cache"})


def _is_system(path: str, name: str, ext: str) -> bool:
    """Cartelle nascoste («.claude», «.vscode»), AppData, file temporanei di Office
    («~$…») e di configurazione non si mostrano."""
    if ext in _SYSTEM_EXT or name.startswith(("~$", ".")):
        return True
    parts = path.replace("\\", "/").lower().split("/")
    return any(p.startswith(".") or p == "appdata" for p in parts[:-1])


def _wts_session_flag() -> int | None:
    """SessionFlags della sessione di questo processo: 0 bloccata, 1 sbloccata, -1 non
    si sa. WTSINFOEXW = DWORD Level + unione allineata a 8 byte (SessionId a 8,
    SessionState a 12, SessionFlags a 16). A 12 c'è lo stato della connessione
    (0 = attiva), che il 26/09 era stato scambiato per il flag."""
    wts = ctypes.WinDLL("wtsapi32")
    sid = wintypes.DWORD()
    if not ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(sid)):
        return None
    buf, size = ctypes.c_void_p(), wintypes.DWORD()
    if not wts.WTSQuerySessionInformationW(None, sid, 25, ctypes.byref(buf),  # WTSSessionInfoEx
                                           ctypes.byref(size)):
        return None
    try:
        if size.value < 20 or int.from_bytes(ctypes.string_at(buf, 4), "little") != 1:
            return None                                   # Level 1 atteso
        return int.from_bytes(ctypes.string_at(buf.value + 16, 4), "little", signed=True)
    finally:
        wts.WTSFreeMemory(buf)


def _foreground_exe() -> str:
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        import psutil
        return psutil.Process(pid.value).name()
    except Exception:  # noqa: BLE001
        return ""


def _input_desktop() -> str:
    """Nome del desktop che riceve l'input, in minuscolo; "" se non si apre."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    handle = user32.OpenInputDesktop(0, False, 0x0001)          # DESKTOP_READOBJECTS
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(256)
        need = wintypes.DWORD()
        if user32.GetUserObjectInformationW(wintypes.HANDLE(handle), 2, buf,  # UOI_NAME
                                            ctypes.sizeof(buf), ctypes.byref(need)):
            return buf.value.lower()
        return ""
    finally:
        user32.CloseDesktop(wintypes.HANDLE(handle))


def _say_name(filename: str) -> str:
    """«Bolletta_luce-agosto.pdf» → «Bolletta luce agosto»: come va detto a voce."""
    stem = os.path.splitext(filename)[0]
    return re.sub(r"\s+", " ", re.sub(r"[_\-.]+", " ", stem)).strip() or filename


def _stem(word: str) -> str:
    """Radice per il confronto sui nomi: «bollette» e «bolletta» → «bollett»."""
    return word[:-1] if len(word) > 4 and word[-1] in "aeio" else word


class LocalWindowsExecutor(PCExecutor):
    """Le capacità del PC su cui gira Calliope."""

    def __init__(self, nome: str = "portatile", app: dict[str, str] | None = None,
                 max_risultati: int = 5, webcam: str = ""):
        super().__init__(nome, {}, max_risultati)
        self.webcam = ""                        # nome DirectShow della webcam (pc_guarda)
        self._webcam_voluta = str(webcam or "")
        self._caps: list[str] = []
        self.mancanti: dict[str, str] = {}      # capacità → perché manca (per l'avvio)
        self.app_scartate: list[str] = []       # voci del catalogo non installate
        self._vol = self._dev_id = self._enum = None
        self._loop = self._media_mgr = None
        self._search = None
        self._desc_cache: dict[str, str] = {}
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="calliope-pc",
                                        initializer=self._init_thread)
        self._call(self._setup, dict(app or {}), timeout=SETUP_TIMEOUT_S)

    # ─────────────────────────── thread e preparazione ───────────────────────────

    @staticmethod
    def _init_thread():
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except ImportError:
            try:
                import comtypes
                comtypes.CoInitialize()
            except ImportError:
                pass

    def _call(self, fn, *args, timeout: float = TIMEOUT_S):
        return self._pool.submit(fn, *args).result(timeout=timeout)

    def close(self):
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _setup(self, app: dict[str, str]):
        def attempt(cap, fn):
            try:
                fn()
                self._caps.append(cap)
            except ImportError as e:
                self.mancanti[cap] = f"manca {e.name or e}"
            except Exception as e:  # noqa: BLE001 — ogni capacità è facoltativa
                self.mancanti[cap] = f"{type(e).__name__}: {e}"[:120]

        attempt("volume", self._setup_volume)
        attempt("media", self._setup_media)
        attempt("luminosita", self._setup_brightness)
        attempt("batteria", self._setup_battery)
        attempt("programmi", self._setup_programs)
        attempt("blocco", lambda: ctypes.windll.user32.LockWorkStation)  # solo la presenza
        attempt("ricerca", self._setup_search)
        attempt("schermata", self._setup_screenshot)
        attempt("webcam", self._setup_webcam)
        for name, command in app.items():
            if self._app_ok(str(command)):
                self._app[name.strip().lower()] = str(command)
            else:
                self.app_scartate.append(name)
        if self._app:
            self._caps.append("app")
        else:
            self.mancanti["app"] = "nessuna app del catalogo è installata"

    def capacita(self) -> list[str]:
        return list(self._caps)

    # ─────────────────────────── foto su richiesta (05/10) ───────────────────────────

    def _setup_screenshot(self):
        from PIL import ImageGrab  # noqa: F401 — solo la presenza (Pillow)

    def _setup_webcam(self):
        from .cattura import nomi_webcam
        nomi = nomi_webcam()
        if not nomi:
            raise RuntimeError("nessuna webcam")
        voluta = self._webcam_voluta.strip().lower()
        scelta = next((n for n in nomi if n.lower() == voluta), None) if voluta else nomi[0]
        if scelta is None:
            raise RuntimeError(f"webcam «{self._webcam_voluta}» non trovata (ci sono: "
                               f"{', '.join(nomi)})")
        self.webcam = scelta

    def _cattura(self, cosa: str) -> dict:
        """Fuori dal thread COM: la webcam costa ~1,5 s e non deve fermare volume e musica.
        L'avviso sul PC compare prima e resta qualche secondo dopo."""
        from .cattura import AVVISO_PRIMA_S, Avviso, foto_webcam, schermata
        avviso = Avviso("Calliope sta usando la webcam" if cosa == "webcam"
                        else "Calliope sta guardando lo schermo")
        try:
            time.sleep(AVVISO_PRIMA_S if avviso.mostrato else 0)
            dati = foto_webcam(self.webcam) if cosa == "webcam" else schermata()
        except RuntimeError as e:
            return errore(str(e))
        except Exception as e:  # noqa: BLE001
            return errore(f"cattura non riuscita ({type(e).__name__})")
        finally:
            avviso.chiudi()
        return {"ok": True, "dati": dati}

    # ─────────────────────────── volume ───────────────────────────

    def _setup_volume(self):
        from pycaw.pycaw import AudioUtilities
        self._enum = AudioUtilities.GetDeviceEnumerator()
        self._endpoint().GetMasterVolumeLevelScalar()

    def _endpoint(self):
        """Controllo del volume dell'uscita predefinita, riaperto solo se cambia (cuffie
        Bluetooth collegate o staccate): l'id costa poco, l'attivazione ~50 ms."""
        import comtypes
        from pycaw.pycaw import IAudioEndpointVolume
        dev = self._enum.GetDefaultAudioEndpoint(0, 1)       # eRender, eMultimedia
        dev_id = dev.GetId()
        if dev_id != self._dev_id or self._vol is None:
            iface = dev.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None)
            self._vol = iface.QueryInterface(IAudioEndpointVolume)
            self._dev_id = dev_id
        return self._vol

    def _volume_state(self) -> dict:
        vol = self._endpoint()
        return {"ok": True, "livello": round(vol.GetMasterVolumeLevelScalar() * 100),
                "muto": bool(vol.GetMute())}

    def volume_leggi(self) -> dict:
        return self._call(self._volume_state)

    def volume_imposta(self, livello: int) -> dict:
        def do():
            vol = self._endpoint()
            vol.SetMasterVolumeLevelScalar(max(0, min(100, int(livello))) / 100, None)
            vol.SetMute(0, None)
            return self._volume_state()
        return self._call(do)

    def volume_muto(self, attivo: bool) -> dict:
        def do():
            self._endpoint().SetMute(1 if attivo else 0, None)
            return self._volume_state()
        return self._call(do)

    # ─────────────────────────── musica ───────────────────────────

    def _setup_media(self):
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as Manager)
        self._loop = asyncio.new_event_loop()
        self._media_mgr = self._loop.run_until_complete(self._await(Manager.request_async()))

    @staticmethod
    async def _await(op):
        return await op

    def _media_app(self, session) -> str:
        aumid = session.source_app_user_model_id or ""
        key = aumid.split("!")[-1].lower().removesuffix(".exe").split(".")[-1]
        return _MEDIA_APPS.get(key, key.capitalize() or "un programma")

    def media_info(self) -> dict:
        def do():
            session = self._media_mgr.get_current_session()
            if session is None:
                return {"ok": True, "sessione": False, "in_riproduzione": False}
            status = int(session.get_playback_info().playback_status)   # 4 = in riproduzione
            out = {"ok": True, "sessione": True, "in_riproduzione": status == 4,
                   "app": self._media_app(session), "titolo": None, "artista": None}
            try:
                props = self._loop.run_until_complete(
                    self._await(session.try_get_media_properties_async()))
                out["titolo"] = props.title or None
                out["artista"] = props.artist or None
            except Exception:  # noqa: BLE001 — il titolo è un di più
                pass
            return out
        return self._call(do)

    def media_comando(self, comando: str) -> dict:
        def do():
            session = self._media_mgr.get_current_session()
            if session is None:
                return errore("non c'è niente da comandare: nessun programma sta "
                              "suonando o è in pausa")
            method = {"riproduci": session.try_play_async, "pausa": session.try_pause_async,
                      "avanti": session.try_skip_next_async,
                      "indietro": session.try_skip_previous_async}.get(comando)
            if method is None:
                return errore(f"comando «{comando}» sconosciuto")
            done = self._loop.run_until_complete(self._await(method()))
            if not done:
                return errore(f"{self._media_app(session)} non accetta il comando «{comando}»")
            return {"ok": True, "app": self._media_app(session)}
        return self._call(do)

    # ─────────────────────────── luminosità, batteria ───────────────────────────

    def _setup_brightness(self):
        import screen_brightness_control as sbc
        if not sbc.get_brightness(display=0):
            raise RuntimeError("nessuno schermo con luminosità regolabile")

    def luminosita_leggi(self) -> dict:
        def do():
            import screen_brightness_control as sbc
            return {"ok": True, "livello": int(sbc.get_brightness(display=0)[0])}
        return self._call(do)

    def luminosita_imposta(self, livello: int) -> dict:
        def do():
            import screen_brightness_control as sbc
            sbc.set_brightness(max(0, min(100, int(livello))), display=0)
            return {"ok": True, "livello": int(sbc.get_brightness(display=0)[0])}
        return self._call(do)

    def _setup_battery(self):
        import psutil
        if psutil.sensors_battery() is None:
            raise RuntimeError("nessuna batteria")

    def batteria(self) -> dict:
        import psutil
        b = psutil.sensors_battery()
        if b is None:
            return {"ok": True, "batteria": False}
        return {"ok": True, "batteria": True, "percento": round(b.percent),
                "in_carica": bool(b.power_plugged)}

    # ─────────────────────────── schermo e blocco ───────────────────────────

    def schermo(self) -> dict:
        """Bloccato secondo il flag di sessione di WTS (WTSINFOEXW.SessionFlags, a
        scostamento 16: 0 = bloccato, 1 = sbloccato). Provato a mano il 27/09: con Win+L
        passa da 1 a 0 subito. Il nome del desktop di input NON basta: la schermata di
        blocco di Windows 11 (LockApp) gira sul desktop «Default», che diventa
        «Winlogon» solo per un attimo; così Calliope apriva il blocco note a schermo
        bloccato. Se il flag è sconosciuto (-1) valgono LockApp in primo piano e il
        desktop; se nessun segnale si legge, bloccato."""
        flag = _wts_session_flag()
        if flag in (0, 1):
            locked = flag == 0
        else:
            locked = _foreground_exe().lower() == "lockapp.exe" or _input_desktop() != "default"
        info = _LASTINPUTINFO(ctypes.sizeof(_LASTINPUTINFO), 0)
        idle = None
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            idle = round(((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF)
                         / 1000, 1)
        return {"ok": True, "bloccato": locked, "inattivo_s": idle}

    def blocca(self) -> dict:
        if not ctypes.windll.user32.LockWorkStation():
            return errore("Windows non ha bloccato la sessione")
        return {"ok": True}

    # ─────────────────────────── programmi aperti ───────────────────────────

    def _setup_programs(self):
        import psutil  # noqa: F401
        import win32gui  # noqa: F401
        import win32process  # noqa: F401

    def _description(self, exe: str) -> str:
        """Nome leggibile del programma («Microsoft Edge»), dalla descrizione del file."""
        if exe in self._desc_cache:
            return self._desc_cache[exe]
        name = os.path.splitext(os.path.basename(exe))[0].capitalize()
        try:
            import win32api
            lang, page = win32api.GetFileVersionInfo(exe, r"\VarFileInfo\Translation")[0]
            desc = win32api.GetFileVersionInfo(
                exe, rf"\StringFileInfo\{lang:04x}{page:04x}\FileDescription")
            if desc and desc.strip():
                name = desc.strip()
        except Exception:  # noqa: BLE001
            pass
        self._desc_cache[exe] = name
        return name

    def _programmi(self) -> list[str]:
        def do():
            import psutil
            import win32gui
            import win32process
            dwm = ctypes.WinDLL("dwmapi")
            names: list[str] = []

            def visit(hwnd, _):
                if not (win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd)):
                    return True
                if win32gui.GetWindow(hwnd, 4):                     # GW_OWNER: finestre di dialogo
                    return True
                if win32gui.GetWindowLong(hwnd, -20) & 0x80:        # WS_EX_TOOLWINDOW
                    return True
                cloaked = wintypes.DWORD()                          # app UWP sospese, altri desktop
                dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), 4)
                if cloaked.value:
                    return True
                if win32gui.GetClassName(hwnd) in ("Progman", "Shell_TrayWnd", "WorkerW"):
                    return True
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    exe = psutil.Process(pid).exe()
                except (psutil.Error, OSError):
                    return True
                if os.path.basename(exe).lower() == "applicationframehost.exe":
                    name = win32gui.GetWindowText(hwnd)             # app UWP: il titolo è il nome
                else:
                    name = self._description(exe)
                if name not in names:
                    names.append(name)
                return True

            win32gui.EnumWindows(visit, None)
            return names
        return self._call(do)

    # ─────────────────────────── app ───────────────────────────

    @staticmethod
    def _browser_exe() -> str | None:
        """Programma del browser predefinito (associazione https dell'utente)."""
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\Shell"
                                r"\Associations\UrlAssociations\https\UserChoice") as k:
                prog_id = winreg.QueryValueEx(k, "ProgId")[0]
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id + r"\shell\open\command") as k:
                command = winreg.QueryValueEx(k, "")[0]
        except OSError:
            return None
        m = re.match(r'\s*"([^"]+)"|\s*(\S+)', command)
        exe = m and (m.group(1) or m.group(2))
        return exe if exe and os.path.exists(exe) else None

    @staticmethod
    def _app_path(exe: str) -> bool:
        """L'eseguibile è registrato in App Paths (così lo trova ShellExecute: Word, Excel)."""
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion"
                                          r"\App Paths" + "\\" + exe):
                    return True
            except OSError:
                pass
        return False

    def _app_ok(self, command: str) -> bool:
        """La voce del catalogo si può aprire su questo PC?"""
        c = command.strip()
        if c == "browser":
            return self._browser_exe() is not None
        if re.fullmatch(r"[a-z][a-z0-9.+-]+:", c, re.I):          # protocollo: ms-settings:
            import winreg
            try:
                winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, c[:-1]).Close()
                return True
            except OSError:
                return False
        if os.path.isabs(c):
            return os.path.exists(c)
        return bool(shutil.which(c)) or self._app_path(c)

    def _avvia(self, comando: str) -> None:
        target = self._browser_exe() if comando == "browser" else comando
        if not target:
            raise RuntimeError("browser predefinito non trovato")
        self._call(os.startfile, target)

    # ─────────────────────────── ricerca e apertura di file ───────────────────────────

    def _setup_search(self):
        import win32com.client
        conn = win32com.client.Dispatch("ADODB.Connection")
        conn.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
        self._search = conn

    def _query(self, where: list[str], top: int) -> list[dict]:
        import win32com.client
        rs = win32com.client.Dispatch("ADODB.Recordset")
        # System.ItemUrl («file:C:/…»), non ItemPathDisplay: quello è il percorso come lo
        # mostra Esplora file (cartelle tradotte) e non esiste sul disco; il 27/09 nessun
        # risultato si apriva («il file non c'è più»), 8 su 8
        # Se ne chiedono di più perché i file di sistema si scartano dopo
        rs.Open("SELECT TOP {} System.ItemUrl, System.FileName, System.FileExtension, "
                "System.DateModified FROM SYSTEMINDEX WHERE {} "
                "ORDER BY System.DateModified DESC".format(int(top) * 4, " AND ".join(where)),
                self._search)
        out = []
        try:
            while not rs.EOF and len(out) < top:
                field = rs.Fields.Item
                name = str(field("System.FileName").Value or "")
                ext = str(field("System.FileExtension").Value or "").lstrip(".").lower()
                path = _url_to_path(str(field("System.ItemUrl").Value or ""))
                if path and not _is_system(path, name, ext):
                    out.append({"nome": _say_name(name), "estensione": ext, "percorso": path,
                                "modificato": _to_local_iso(field("System.DateModified").Value)})
                rs.MoveNext()
        finally:
            rs.Close()
        return out

    def _cerca(self, testo, tipo, dal, al, massimo) -> list[dict]:
        home = os.path.expanduser("~").replace("\\", "/").replace("'", "''")
        base = [f"SCOPE='file:{home}'", "System.ItemType <> 'Directory'"]
        if tipo in _KIND:
            base.append(_KIND[tipo])
        for value, op in ((dal, ">="), (al, "<")):
            if value:
                when = datetime.datetime.fromisoformat(value).astimezone(datetime.timezone.utc)
                base.append(f"System.DateModified {op} '{when:%Y-%m-%d %H:%M:%S}'")
        # Solo lettere e cifre: niente apici, niente SQL dal modello
        words = [_stem(w) for w in re.findall(r"\w+", (testo or "").lower())
                 if w not in _STOP and len(w) > 1][:5]

        def do():
            found = self._query(base + [f"System.FileName LIKE '%{w}%'" for w in words],
                                massimo)
            if not found and words:
                # Nessun nome corrisponde: si cerca nel contenuto (più lento sui nomi,
                # veloce sul testo, 5–10 ms misurati)
                terms = " AND ".join(f'"{w}*"' for w in words)
                found = self._query(base + [f"CONTAINS('{terms}')"], massimo)
            return found
        return self._call(do)

    def _apri(self, percorso: str) -> None:
        """Apre un file senza mai eseguirlo (base.modo_apertura): i documenti con il
        programma predefinito, script e pagine come testo nel Blocco note, il resto no.
        Il controllo è qui anche per il satellite, che non si fida del server."""
        if not os.path.exists(percorso):
            raise FileNotFoundError("il file non c'è più")
        modo = modo_apertura(percorso)
        if modo == "normale":
            self._call(os.startfile, percorso)
        elif modo == "testo":
            blocco = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32",
                                  "notepad.exe")
            self._call(lambda: subprocess.Popen([blocco, percorso], close_fds=True))
        else:
            raise PermissionError("questo tipo di file non lo apro: si avvia solo a mano")


def available() -> str | None:
    """None se l'esecutore Windows può partire, altrimenti il motivo."""
    if sys.platform != "win32":
        return "non è Windows"
    return None
