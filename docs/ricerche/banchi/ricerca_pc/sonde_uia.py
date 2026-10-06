"""Sonde di SOLA LETTURA, seconda parte: dimensione e tempi dell'albero UI Automation delle
finestre aperte (per stimare quanto costa dare a un LLM la «vista» di una finestra) e stato
della sessione multimediale di Windows (WinRT). Si contano gli elementi, non si stampano
i nomi (possono contenere dati personali). Nessuna azione.
"""

import asyncio
import json
import time

import uiautomation as auto
import win32gui
import win32process
import psutil

out = {"uia_per_finestra": []}


def windows():
    res = []

    def cb(h, _):
        if win32gui.IsWindowVisible(h) and win32gui.GetWindowText(h):
            _, pid = win32process.GetWindowThreadProcessId(h)
            try:
                exe = psutil.Process(pid).name()
            except psutil.Error:
                exe = "?"
            res.append((h, win32gui.GetClassName(h), exe))
        return True

    win32gui.EnumWindows(cb, None)
    return res


for h, cls, exe in windows():
    if cls in ("Progman",):
        continue
    t = time.perf_counter()
    n, named, interactive = 0, 0, 0
    try:
        ctrl = auto.ControlFromHandle(h)
        for c, d in auto.WalkControl(ctrl, includeTop=True, maxDepth=25):
            n += 1
            if c.Name:
                named += 1
            if c.ControlTypeName in ("ButtonControl", "EditControl", "HyperlinkControl",
                                     "MenuItemControl", "ListItemControl", "TabItemControl",
                                     "CheckBoxControl", "ComboBoxControl", "TreeItemControl"):
                interactive += 1
            if n >= 5000:
                break
        ms = round((time.perf_counter() - t) * 1000)
        out["uia_per_finestra"].append({"programma": exe, "classe": cls, "elementi": n,
                                        "con_nome": named, "interattivi": interactive, "ms": ms})
    except Exception as e:  # noqa: BLE001
        out["uia_per_finestra"].append({"programma": exe, "classe": cls, "errore": repr(e)[:120]})


# Sessione multimediale (Global System Media Transport Controls): sola lettura
async def media():
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as M,
    )
    t = time.perf_counter()
    mgr = await M.request_async()
    s = mgr.get_current_session()
    if s is None:
        return {"sessione": None, "ms": round((time.perf_counter() - t) * 1000)}
    info = s.get_playback_info()
    return {"app": s.source_app_user_model_id, "stato": int(info.playback_status),
            "puo_pausa": info.controls.is_pause_enabled,
            "ms": round((time.perf_counter() - t) * 1000)}

try:
    out["media"] = asyncio.run(media())
except Exception as e:  # noqa: BLE001
    out["media"] = {"errore": repr(e)[:200]}

print(json.dumps(out, ensure_ascii=False, indent=1))
