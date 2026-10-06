"""
Immagini in ingresso (05/10/2026, docs/ricerche/2026-10-05-immagini.md): foto dal telefono,
file caricati dalla pagina degli schermi, foto dalla webcam e schermate del PC prese
dall'esecutore su richiesta.

- `prepara`: controlla i byte (il tipo vero dalla firma, mai dall'estensione o dal
  Content-Type; niente SVG né formati con script), la dimensione e i pixel (bomba di
  decompressione), gira la foto secondo l'EXIF, la riduce (lato lungo `immagini_lato_max`) e
  la riscrive in JPEG: i metadati (posizione GPS, modello del telefono) non passano.
- `Immagine`: una foto della conversazione, solo **in memoria**: mai su disco, mai nel
  registro dei turni (dove resta solo il numero, la fonte e la dimensione). Si salva solo con
  «archiviala» (tool immagine_archivia → cartella dell'archivio).
- `Album`: le foto della conversazione, numerate (1, 2, 3…: «la prima», «l'ultima foto»);
  vive dentro Brain e si azzera con la conversazione (Brain.end_conversation).
- `InAttesa`: una foto mandata senza domanda aspetta la frase dopo della stessa persona
  (`immagini_attesa_s`).
"""

from __future__ import annotations

import base64
import io
import threading
import time
from dataclasses import dataclass, field

# Firme dei formati ammessi (i primi byte). HEIC no: Pillow non lo legge senza un plugin
# nativo; dal telefono la pagina lo converte in JPEG prima di mandarlo (canvas)
FIRME = (
    (b"\xff\xd8\xff", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"BM", "bmp"),
)
FONTI = {"telefono": "dal telefono", "schermo": "dallo schermo", "webcam": "dalla webcam",
         "screenshot": "lo schermo del computer", "file": "da un file"}
# Frasi del ciclo principale (main.py)
FOTO_IN_ATTESA = "Ho la foto. Cosa vuoi sapere?"
FOTO_NON_VISTA = ("La persona ti ha mandato una foto, ma il modello di adesso non vede le "
                  "immagini: dillo in breve, e rispondi al resto se puoi.")
# Pixel al massimo prima di decodificare (una PNG di pochi kB può dichiarare 50 000 × 50 000)
MAX_PIXEL = 40_000_000


class ImmagineNonValida(ValueError):
    """L'immagine non si usa: il messaggio dice perché, in italiano (va alla pagina)."""


def tipo_dai_byte(dati: bytes) -> str | None:
    """Il formato vero dai primi byte, o None. WebP: «RIFF....WEBP»."""
    if dati[:4] == b"RIFF" and dati[8:12] == b"WEBP":
        return "webp"
    for firma, nome in FIRME:
        if dati.startswith(firma):
            return nome
    return None


def prepara(dati: bytes, lato_max: int = 1280, max_byte: int = 12_000_000,
            qualita: int = 85) -> tuple[bytes, int, int]:
    """(jpeg, larghezza, altezza) pronti per il modello. Solleva ImmagineNonValida."""
    if not dati:
        raise ImmagineNonValida("immagine vuota")
    if len(dati) > max_byte:
        raise ImmagineNonValida(f"immagine troppo grande (al massimo {max_byte // 1_000_000} MB)")
    tipo = tipo_dai_byte(dati)
    if tipo is None:
        head = dati[:200].lstrip().lower()
        if head.startswith(b"<") or b"<svg" in head:
            raise ImmagineNonValida("le immagini SVG non le accetto")
        if dati[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
            raise ImmagineNonValida("formato HEIC: mandala come JPEG")
        raise ImmagineNonValida("non è un'immagine JPEG, PNG, WebP, GIF o BMP")
    try:
        from PIL import Image, ImageOps
    except ImportError:
        raise ImmagineNonValida("manca Pillow per leggere le immagini") from None
    import warnings
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            im = Image.open(io.BytesIO(dati))
            if im.format is None or im.format.lower() not in (tipo, "jpeg" if tipo == "jpeg"
                                                              else tipo, "mpo"):
                raise ImmagineNonValida("il contenuto non corrisponde al formato")
            w, h = im.size
            if w < 8 or h < 8:
                raise ImmagineNonValida("immagine troppo piccola")
            if w * h > MAX_PIXEL:
                raise ImmagineNonValida("immagine con troppi pixel")
            if getattr(im, "n_frames", 1) > 1:
                im.seek(0)                      # GIF animata: il primo fotogramma
            im.draft("RGB", (lato_max, lato_max))   # JPEG grandi: decodifica già ridotta
            im = ImageOps.exif_transpose(im)
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                fondo = Image.new("RGB", im.size, (255, 255, 255))
                fondo.paste(im, mask=im.getchannel("A"))
                im = fondo
            else:
                im = im.convert("RGB")
            if max(im.size) > lato_max:
                k = lato_max / max(im.size)
                im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))),
                               Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=qualita, optimize=True)   # senza EXIF
    except ImmagineNonValida:
        raise
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise ImmagineNonValida("immagine con troppi pixel") from None
    except Exception as e:  # noqa: BLE001 - un file rovinato non deve far cadere nulla
        raise ImmagineNonValida(f"immagine rovinata ({type(e).__name__})") from None
    return buf.getvalue(), im.width, im.height


def miniatura(jpeg: bytes, lato: int = 360) -> str:
    """La miniatura come data URL (per la scheda sullo schermo): JPEG piccolo."""
    from PIL import Image
    im = Image.open(io.BytesIO(jpeg))
    im.thumbnail((lato, lato))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=70)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def da_data_url(testo: str) -> bytes:
    """I byte di «data:image/…;base64,…» (o base64 nudo). Solleva ImmagineNonValida."""
    if not isinstance(testo, str) or not testo:
        raise ImmagineNonValida("manca l'immagine")
    if testo.startswith("data:"):
        testa, _, testo = testo.partition(",")
        if ";base64" not in testa:
            raise ImmagineNonValida("immagine non in base64")
    try:
        return base64.b64decode(testo, validate=True)
    except (ValueError, TypeError):
        raise ImmagineNonValida("base64 non valido") from None


@dataclass
class Immagine:
    jpeg: bytes = field(repr=False)  # mai in un log, nemmeno per sbaglio
    larghezza: int
    altezza: int
    fonte: str = "telefono"          # telefono, schermo, webcam, screenshot, file
    persona: str | None = None       # id del profilo di chi l'ha mandata o chiesta
    arrivata: float = field(default_factory=time.time)
    n: int = 0                       # numero nella conversazione (Album.aggiungi)
    descrizione: str = ""            # breve, fatta dal modello (Brain.descrivi_immagini)

    def b64(self) -> str:
        return base64.b64encode(self.jpeg).decode()

    def etichetta(self) -> str:
        """«Foto 2 (dal telefono)»: il nome con cui il modello e la persona la indicano."""
        return f"Foto {self.n} ({FONTI.get(self.fonte, self.fonte)})"

    def per_registro(self) -> dict:
        """Ciò che va nel registro dei turni: niente byte, niente descrizione."""
        return {"n": self.n, "fonte": self.fonte, "lato": max(self.larghezza, self.altezza),
                "kb": round(len(self.jpeg) / 1024)}


class Album:
    """Le foto di una conversazione, numerate da 1. Al più `massimo`: oltre si toglie la più
    vecchia (il suo numero non si riusa)."""

    def __init__(self, massimo: int = 8):
        self.massimo = max(1, int(massimo))
        self.foto: list[Immagine] = []
        self._prossimo = 1

    def aggiungi(self, img: Immagine) -> Immagine:
        img.n = self._prossimo
        self._prossimo += 1
        self.foto.append(img)
        del self.foto[:-self.massimo]
        return img

    def prendi(self, n: int | None) -> Immagine | None:
        """La foto numero `n`; con n ≤ 0 o None l'ultima (-1 la penultima…)."""
        if not self.foto:
            return None
        if n is None or n == 0:
            return self.foto[-1]
        if n < 0:
            return self.foto[n] if -n <= len(self.foto) else None
        return next((f for f in self.foto if f.n == n), None)

    def numeri(self) -> list[int]:
        return [f.n for f in self.foto]

    def svuota(self):
        self.foto.clear()
        self._prossimo = 1

    def __len__(self):
        return len(self.foto)


def modello_vede(cfg) -> bool:
    """Il modello della voce vede le immagini? `immagini_modello` «si»/«no», oppure «auto»:
    con Ollama la capacità «vision» di /api/show (3 s al più; Ollama giù = sì, si ricontrolla
    alla prima foto con Brain.vede_immagini), con l'API OpenAI sì (vLLM: Gemma 4 e qwen3.6)."""
    mode = str(getattr(cfg, "immagini_modello", "auto") or "auto").lower()
    if mode in ("si", "sì", "true", "yes"):
        return True
    if mode in ("no", "false"):
        return False
    if getattr(cfg, "llm_backend", "ollama") != "ollama":
        return True
    try:
        import httpx
        r = httpx.post(cfg.llm_native_url.rstrip("/") + "/api/show",
                       json={"model": cfg.llm_model}, timeout=3.0)
        return "vision" in (r.json().get("capabilities") or [])
    except Exception:  # noqa: BLE001
        return True


def opzioni_tool(cfg, pcs=None, archivio=None) -> dict | None:
    """Gli argomenti di build_registry(immagini=…): None con le foto spente o un modello che
    non le vede. `pc_guarda` c'è se un PC sa fare schermate o foto con la webcam (con
    l'esecutore remoto sempre: il prefisso del prompt non cambia con il satellite)."""
    if not getattr(cfg, "immagini_enabled", True) or not modello_vede(cfg):
        return None
    pc = any({"schermata", "webcam"} & set(getattr(ex, "capacita_possibili", ex.capacita)())
             for ex in (pcs or {}).values())
    return {"storia": str(getattr(cfg, "immagini_storia", "messaggio")), "pc": pc,
            "archivio": archivio is not None}


class InAttesa:
    """Foto arrivate senza domanda: aspettano la prossima frase della stessa persona."""

    def __init__(self, durata_s: float = 120.0, massimo: int = 4):
        self.durata_s = float(durata_s)
        self.massimo = massimo
        self._lock = threading.Lock()
        self._voci: list[Immagine] = []

    def metti(self, img: Immagine):
        with self._lock:
            self._voci.append(img)
            del self._voci[:-self.massimo]

    def prendi(self, persona: str | None) -> list[Immagine]:
        """Le foto della persona ancora valide (e le toglie). Un ospite (None) niente."""
        if persona is None:
            return []
        ora = time.time()
        with self._lock:
            valide = [i for i in self._voci if ora - i.arrivata <= self.durata_s]
            mie = [i for i in valide if i.persona == persona]
            self._voci = [i for i in valide if i.persona != persona]
        return mie

    def svuota(self):
        with self._lock:
            self._voci.clear()

    def togli(self, persona: str | None) -> int:
        """Le foto della persona non valgono più (la sua conversazione è finita, 05/10)."""
        with self._lock:
            prima = len(self._voci)
            self._voci = [i for i in self._voci if i.persona != persona]
            return prima - len(self._voci)
