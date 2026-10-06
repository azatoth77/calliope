"""
Foto dalla webcam e schermate su richiesta (05/10/2026, docs/ricerche/2026-10-05-immagini.md).

Solo quando la persona lo chiede (tool pc_guarda), mai di continuo; sul PC compare un avviso
mentre si cattura (`Avviso`). Nessuna libreria nuova:
- **schermata**: Pillow (`ImageGrab.grab`, GDI di Windows), già nelle dipendenze;
- **webcam**: PyAV (DirectShow, `format="dshow"`), che c'è già con faster-whisper (il suo
  wheel per Windows contiene FFmpeg con dshow). OpenCV no: ~90 MB nativi in più. Si leggono
  alcuni fotogrammi prima di tenerne uno: i primi sono scuri finché l'esposizione automatica
  non si assesta (misura del 05/10: webcam integrata 1920×1080, ~1,6 s in tutto).

I byte non toccano mai il disco: tornano all'esecutore, che li riduce e li manda al server.
"""

import io
import re
import threading
import time

# Fotogrammi letti prima di tenerne uno (esposizione automatica)
FOTOGRAMMI = 8
AVVISO_PRIMA_S = 0.35
AVVISO_DOPO_S = 2.5


def nomi_webcam() -> list[str]:
    """I nomi delle webcam (DirectShow) come li mostra Windows. Solleva ImportError senza
    PyAV."""
    import av
    import av.logging
    vecchio = av.logging.get_level()
    av.logging.set_level(av.logging.INFO)
    try:
        with av.logging.Capture(True) as righe:
            try:
                av.open("video=dummy", format="dshow", options={"list_devices": "true"})
            except Exception:  # noqa: BLE001 — l'elenco arriva come log, poi «esce»
                pass
    finally:
        av.logging.set_level(vecchio)
    testo = "".join(r[2] for r in righe if len(r) > 2)
    return re.findall(r'"([^"\n]+)" \(video\)', testo)


def foto_webcam(nome: str, timeout_s: float = 6.0) -> bytes:
    """Una foto (JPEG) dalla webcam `nome`. Solleva RuntimeError con il motivo in italiano."""
    import av
    t0 = time.monotonic()
    try:
        c = av.open(f"video={nome}", format="dshow", options={"rtbufsize": "50M"},
                    timeout=timeout_s)
    except OSError as e:
        if "already in use" in str(e) or "Could not run graph" in str(e):
            raise RuntimeError("la webcam è usata da un altro programma") from None
        raise RuntimeError("la webcam non si apre") from None
    try:
        frame = None
        for i, frame in enumerate(c.decode(video=0)):
            if i + 1 >= FOTOGRAMMI or time.monotonic() - t0 > timeout_s:
                break
        if frame is None:
            raise RuntimeError("la webcam non ha mandato immagini")
        buf = io.BytesIO()
        frame.to_image().save(buf, "JPEG", quality=90)
        return buf.getvalue()
    finally:
        c.close()


def schermata() -> bytes:
    """Una schermata dello schermo principale (JPEG di qualità alta). Solo il principale:
    con tre monitor affiancati (6400×1600) ridotti a 1280 pixel il testo non si leggerebbe."""
    from PIL import ImageGrab
    im = ImageGrab.grab()
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=92)
    return buf.getvalue()


class Avviso:
    """Un riquadro sempre in primo piano in alto a destra («Calliope sta guardando lo
    schermo») finché si cattura e per qualche secondo dopo, escluso dalle schermate
    (SetWindowDisplayAffinity, WDA_EXCLUDEFROMCAPTURE da Windows 10 2004). Con tkinter, nella
    libreria standard; senza (o senza desktop) non c'è, e la cattura va avanti: l'avviso a
    voce lo dà comunque Calliope."""

    def __init__(self, testo: str):
        self.testo = testo
        self._pronto = threading.Event()
        self._chiudi = threading.Event()
        self.mostrato = False
        threading.Thread(target=self._gira, daemon=True, name="avviso-cattura").start()
        self._pronto.wait(1.0)

    def _gira(self):
        try:
            import tkinter as tk
            root = tk.Tk()
        except Exception:  # noqa: BLE001 — niente tkinter o niente desktop
            self._pronto.set()
            return
        try:
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            try:
                root.attributes("-alpha", 0.92)
            except tk.TclError:
                pass
            lab = tk.Label(root, text="●  " + self.testo, bg="#b3261e", fg="white",
                           font=("Segoe UI", 14, "bold"), padx=18, pady=10)
            lab.pack()
            root.update_idletasks()
            w = root.winfo_reqwidth()
            root.geometry(f"+{max(0, root.winfo_screenwidth() - w - 24)}+24")
            root.update()
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11)
            except Exception:  # noqa: BLE001 — Windows vecchio: l'avviso finisce nella foto
                pass
            self.mostrato = True
            self._pronto.set()
            while not self._chiudi.is_set():
                root.update()
                time.sleep(0.05)
            root.destroy()
        except Exception:  # noqa: BLE001
            self._pronto.set()

    def chiudi(self, dopo_s: float = AVVISO_DOPO_S):
        threading.Timer(max(0.0, dopo_s), self._chiudi.set).start()
