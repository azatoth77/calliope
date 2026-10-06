"""Raccolta a SOLA LETTURA dell'albero UI Automation di una finestra (prova del selettore UI).

Nessun clic, nessuna digitazione: si legge l'albero con una sola richiesta di cache
(IUIAutomation.BuildUpdatedCache con TreeScope_Subtree), così il costo misurato è quello
che avrebbe un selettore vero. La lettura si fa due volte: le app Chromium (Edge, VS Code,
Teams) espongono l'albero completo solo dopo che un client UIA l'ha chiesto una volta.

Uso:
    python raccogli_uia.py --hwnd 12345 --nome esplora_download
    python raccogli_uia.py --classe Shell_TrayWnd --nome barra
    python raccogli_uia.py --elenco            # finestre visibili (handle, classe, programma)

Scrive dati/alberi/<nome>.json. I nomi degli elementi possono contenere dati personali
(nomi di file, titoli): la cartella dati/ è fuori da git.
"""

import argparse
import ctypes
import json
import time
from pathlib import Path

import psutil
import uiautomation as auto
import uiautomation.uiautomation as uia_core
import win32gui
import win32process

QUI = Path(__file__).resolve().parent
ALBERI = QUI / "dati" / "alberi"

# Proprietà lette in cache (id UIA_*PropertyId)
PROP = {
    "nome": 30005, "tipo": 30003, "automation_id": 30011, "classe": 30012,
    "abilitato": 30010, "fuori_schermo": 30022, "rett": 30001, "focusable": 30009,
    "aiuto": 30013, "framework": 30024, "tipo_locale": 30004,
    "p_invoke": 30031, "p_toggle": 30041, "p_selitem": 30036, "p_value": 30043,
    "p_expand": 30028, "p_range": 30033, "p_legacy": 30090,
    "toggle_stato": 30086, "valore": 30045, "valore_solo_lettura": 30046,
    "espanso_stato": 30070, "selezionato": 30079, "range_valore": 30047,
    "azione_legacy": 30100,
}
PATTERN = {"p_invoke": "Invoke", "p_toggle": "Toggle", "p_selitem": "SelectionItem",
           "p_value": "Value", "p_expand": "ExpandCollapse", "p_range": "RangeValue"}


def finestre():
    res = []

    def cb(h, _):
        if win32gui.IsWindowVisible(h):
            _, pid = win32process.GetWindowThreadProcessId(h)
            try:
                exe = psutil.Process(pid).name()
            except psutil.Error:
                exe = "?"
            res.append({"hwnd": h, "classe": win32gui.GetClassName(h), "programma": exe,
                        "titolo": win32gui.GetWindowText(h)})
        return True

    win32gui.EnumWindows(cb, None)
    return res


def _val(el, pid):
    try:
        return el.GetCachedPropertyValue(pid)
    except Exception:  # noqa: BLE001
        return None


def leggi_albero(hwnd):
    """Una richiesta di cache per tutto il sottoalbero (vista di controllo)."""
    client = uia_core._AutomationClient.instance()
    ia = client.IUIAutomation
    cr = ia.CreateCacheRequest()
    for pid in PROP.values():
        cr.AddProperty(pid)
    cr.TreeScope = 7  # Element | Children | Descendants
    root = ia.ElementFromHandle(hwnd)
    t = time.perf_counter()
    cached = root.BuildUpdatedCache(cr)
    ms_cache = (time.perf_counter() - t) * 1000

    elementi = []

    def visita(el, percorso, prof):
        d = {k: _val(el, pid) for k, pid in PROP.items()}
        tipo = auto.ControlTypeNames.get(d["tipo"], str(d["tipo"]))
        r = d["rett"]
        rett = [int(x) for x in r] if r is not None and len(r) == 4 else None
        valore = d["valore"]
        if isinstance(valore, str) and len(valore) > 80:
            valore = valore[:80] + "…"  # il contenuto dei documenti non serve
        pattern = [PATTERN[k] for k in PATTERN if d[k]]
        e = {
            "id": len(elementi), "nome": (d["nome"] or "").strip(), "tipo": tipo,
            "tipo_locale": d["tipo_locale"], "automation_id": d["automation_id"] or "",
            "classe": d["classe"] or "", "framework": d["framework"] or "",
            "abilitato": bool(d["abilitato"]), "visibile": not bool(d["fuori_schermo"]),
            "focusable": bool(d["focusable"]), "pattern": pattern,
            "legacy_azione": d["azione_legacy"] if d["p_legacy"] else None,
            "toggle": d["toggle_stato"] if d["p_toggle"] else None,
            "valore": valore if d["p_value"] else None,
            "espanso": d["espanso_stato"] if d["p_expand"] else None,
            "selezionato": bool(d["selezionato"]) if d["p_selitem"] else None,
            "range": d["range_valore"] if d["p_range"] else None,
            "aiuto": (d["aiuto"] or "")[:120], "rett": rett, "prof": prof,
            "percorso": percorso,
        }
        elementi.append(e)
        etichetta = f"{tipo[:-7] if tipo.endswith('Control') else tipo}:{e['nome'][:40]}"
        try:
            figli = el.GetCachedChildren()
        except Exception:  # noqa: BLE001
            figli = None
        if figli:  # un puntatore COM nullo vale False
            for i in range(figli.Length):
                visita(figli.GetElement(i), percorso + [etichetta], prof + 1)

    t2 = time.perf_counter()
    visita(cached, [], 0)
    ms_visita = (time.perf_counter() - t2) * 1000
    return elementi, ms_cache, ms_visita


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hwnd", type=int)
    ap.add_argument("--classe")
    ap.add_argument("--nome")
    ap.add_argument("--nota", default="")
    ap.add_argument("--elenco", action="store_true")
    a = ap.parse_args()
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    if a.elenco:
        for f in finestre():
            if f["titolo"]:
                print(f["hwnd"], f["classe"], f["programma"], repr(f["titolo"][:60]))
        return
    hwnd = a.hwnd or win32gui.FindWindow(a.classe, None)
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    letture = []
    for _ in range(3):  # la prima «sveglia» le app Chromium
        el, ms_c, ms_v = leggi_albero(hwnd)
        letture.append({"elementi": len(el), "ms_cache": round(ms_c, 1),
                        "ms_visita": round(ms_v, 1)})
    out = {"schermata": a.nome, "nota": a.nota, "hwnd": hwnd,
           "classe": win32gui.GetClassName(hwnd), "programma": psutil.Process(pid).name(),
           "titolo": win32gui.GetWindowText(hwnd), "letture": letture, "elementi": el}
    ALBERI.mkdir(parents=True, exist_ok=True)
    (ALBERI / f"{a.nome}.json").write_text(json.dumps(out, ensure_ascii=False, indent=0),
                                          encoding="utf-8")
    azionabili = [e for e in el if e["pattern"] and e["abilitato"] and e["visibile"]]
    print(json.dumps({"schermata": a.nome, "letture": letture,
                      "azionabili_visibili": len(azionabili),
                      "con_nome": sum(1 for e in azionabili if e["nome"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
