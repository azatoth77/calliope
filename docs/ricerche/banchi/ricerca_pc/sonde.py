"""Sonde di SOLA LETTURA per la ricerca sul controllo dei PC (docs/ricerche/2026-09-26-controllo-pc.md).

Nessun clic, nessuna digitazione, nessuna modifica di impostazioni: si leggono solo
finestre, processi, albero UI Automation, volume, luminosità e indice di Windows Search,
misurando i tempi. Lo schermo catturato resta in memoria e non si salva.

Uso (venv separato):  docs\\ricerche\\banchi\\ricerca_pc\\.venv\\Scripts\\python docs\\ricerche\\banchi\\ricerca_pc\\sonde.py
"""

import json
import os
import shutil
import statistics
import sys
import time


def timed(fn, n=5):
    """Esegue fn n volte e restituisce (ultimo risultato, mediana ms, primo ms)."""
    times, result = [], None
    for _ in range(n):
        t = time.perf_counter()
        result = fn()
        times.append((time.perf_counter() - t) * 1000)
    return result, round(statistics.median(times), 1), round(times[0], 1)


out = {}

# 1. Finestre di primo livello visibili con titolo (win32gui)
import win32gui
import win32process


def list_windows():
    wins = []

    def cb(h, _):
        if win32gui.IsWindowVisible(h) and win32gui.GetWindowText(h):
            wins.append((h, win32gui.GetClassName(h), win32gui.GetWindowText(h)))
        return True

    win32gui.EnumWindows(cb, None)
    return wins


wins, med, first = timed(list_windows)
out["finestre"] = {"n": len(wins), "ms_mediana": med, "ms_primo": first,
                   "classi": sorted({c for _, c, _ in wins})[:25]}
fg = win32gui.GetForegroundWindow()
out["primo_piano_classe"] = win32gui.GetClassName(fg)

# 2. Processi (psutil)
import psutil

procs, med, first = timed(lambda: [p.info for p in psutil.process_iter(["pid", "name"])])
out["processi"] = {"n": len(procs), "ms_mediana": med, "ms_primo": first}

# Programma associato a ogni finestra (per «chiudi/mostra Word»)
def windows_with_exe():
    res = []
    for h, c, t in wins:
        _, pid = win32process.GetWindowThreadProcessId(h)
        try:
            res.append(psutil.Process(pid).name())
        except psutil.Error:
            res.append("?")
    return res

exes, med, _ = timed(windows_with_exe, 3)
out["finestre_con_programma"] = {"ms_mediana": med, "programmi": sorted(set(exes))}

# 3. Volume (pycaw / Core Audio via comtypes): sola lettura
from pycaw.pycaw import AudioUtilities

def read_volume():
    dev = AudioUtilities.GetSpeakers()
    vol = dev.EndpointVolume
    return round(vol.GetMasterVolumeLevelScalar() * 100), bool(vol.GetMute())

try:
    (lvl, mute), med, first = timed(read_volume)
    out["volume"] = {"livello": lvl, "muto": mute, "ms_mediana": med, "ms_primo": first}
except Exception as e:  # noqa: BLE001
    out["volume"] = {"errore": repr(e)}

try:
    sess, med, first = timed(lambda: [s.Process.name() for s in AudioUtilities.GetAllSessions() if s.Process], 3)
    out["sessioni_audio"] = {"programmi": sorted(set(sess)), "ms_mediana": med}
except Exception as e:  # noqa: BLE001
    out["sessioni_audio"] = {"errore": repr(e)}

# 4. Luminosità (screen_brightness_control): sola lettura
try:
    import screen_brightness_control as sbc
    b, med, first = timed(lambda: sbc.get_brightness(), 3)
    out["luminosita"] = {"valori": b, "ms_mediana": med, "ms_primo": first}
except Exception as e:  # noqa: BLE001
    out["luminosita"] = {"errore": repr(e)}

# 5. Windows Search (indice di sistema) via OLE DB: query di sola lettura
import win32com.client


def search(where, top=10):
    conn = win32com.client.Dispatch("ADODB.Connection")
    conn.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
    rs = win32com.client.Dispatch("ADODB.Recordset")
    rs.Open(f"SELECT TOP {top} System.ItemPathDisplay FROM SYSTEMINDEX WHERE {where}", conn)
    n = 0
    while not rs.EOF:
        n += 1
        rs.MoveNext()
    rs.Close()
    conn.Close()
    return n


queries = {
    "nome_contiene_fattura": "System.FileName LIKE '%fattura%'",
    "pdf_ultimi_30_giorni": "System.FileExtension = '.pdf' AND System.DateModified > '2026-08-27'",
    "testo_contiene_calliope": "CONTAINS('\"calliope\"')",
}
out["windows_search"] = {}
for k, q in queries.items():
    try:
        n, med, first = timed(lambda q=q: search(q), 3)
        out["windows_search"][k] = {"risultati_max10": n, "ms_mediana": med, "ms_primo": first}
    except Exception as e:  # noqa: BLE001
        out["windows_search"][k] = {"errore": repr(e)[:200]}

out["everything_es_exe"] = shutil.which("es.exe") or shutil.which("es")
out["everything_in_esecuzione"] = any((p.get("name") or "").lower().startswith("everything") for p in procs)

# 6. UI Automation: albero della finestra in primo piano o di Esplora risorse / Blocco note
import uiautomation as auto

target = None
for h, c, t in wins:
    if c in ("CabinetWClass", "Notepad"):
        target = (h, c)
        break
if target is None:
    target = (fg, win32gui.GetClassName(fg))


def uia_tree(hwnd, max_depth=12):
    ctrl = auto.ControlFromHandle(hwnd)
    counts, n = {}, 0
    for c, depth in auto.WalkControl(ctrl, includeTop=True, maxDepth=max_depth):
        n += 1
        counts[c.ControlTypeName] = counts.get(c.ControlTypeName, 0) + 1
    return n, counts


try:
    (n, counts), med, first = timed(lambda: uia_tree(target[0]), 3)
    out["uia_albero"] = {"classe_finestra": target[1], "elementi": n, "ms_mediana": med,
                         "ms_primo": first,
                         "tipi": dict(sorted(counts.items(), key=lambda kv: -kv[1])[:12])}
except Exception as e:  # noqa: BLE001
    out["uia_albero"] = {"errore": repr(e)[:200]}

# Barra delle applicazioni: pulsanti dei programmi (utile per «quali programmi sono aperti»)
try:
    def taskbar():
        tb = auto.ControlFromHandle(win32gui.FindWindow("Shell_TrayWnd", None))
        return sum(1 for c, d in auto.WalkControl(tb, maxDepth=8) if c.ControlTypeName == "ButtonControl")
    nb, med, first = timed(taskbar, 3)
    out["uia_taskbar"] = {"pulsanti": nb, "ms_mediana": med, "ms_primo": first}
except Exception as e:  # noqa: BLE001
    out["uia_taskbar"] = {"errore": repr(e)[:200]}

# pywinauto con backend UIA sulla stessa finestra (confronto)
try:
    from pywinauto import Desktop

    def pwa():
        w = Desktop(backend="uia").window(handle=target[0])
        return len(w.descendants())
    n2, med, first = timed(pwa, 3)
    out["pywinauto_uia"] = {"discendenti": n2, "ms_mediana": med, "ms_primo": first}
except Exception as e:  # noqa: BLE001
    out["pywinauto_uia"] = {"errore": repr(e)[:200]}

# 7. Stato della sessione: inattività e blocco (sola lettura)
import ctypes
from ctypes import wintypes


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


li = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li))
out["inattivo_s"] = round((ctypes.windll.kernel32.GetTickCount() - li.dwTime) / 1000, 1)
out["logonui_in_esecuzione"] = any((p.get("name") or "").lower() == "logonui.exe" for p in procs)

# 8. Cattura dello schermo in memoria (non salvata), per stimare il costo di un agente UI
try:
    from PIL import ImageGrab
    img, med, first = timed(lambda: ImageGrab.grab(all_screens=False), 3)
    out["screenshot"] = {"dimensioni": img.size, "ms_mediana": med, "ms_primo": first}
    del img
except Exception as e:  # noqa: BLE001
    out["screenshot"] = {"errore": repr(e)[:200]}

# 9. Batteria e alimentazione
bat = psutil.sensors_battery()
out["batteria"] = None if bat is None else {"percento": bat.percent, "in_carica": bat.power_plugged}

out["python"] = sys.version.split()[0]
print(json.dumps(out, ensure_ascii=False, indent=1))
