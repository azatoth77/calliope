"""
Immagini in ingresso (05/10/2026, docs/ricerche/2026-10-05-immagini.md): foto dal telefono,
file caricati dalla pagina degli schermi, foto dalla webcam e schermate del PC prese
dall'esecutore su richiesta.

- `prepara`: controlla i byte (il tipo vero dalla firma, mai dall'estensione o dal
  Content-Type; niente SVG né formati con script), la dimensione e i pixel (bomba di
  decompressione), gira la foto secondo l'EXIF, la riduce (lato lungo `immagini_lato_max`) e
  la riscrive in JPEG: i metadati (posizione GPS, modello del telefono) non passano.
- `Immagine`: una foto della conversazione, solo **in memoria**: la foto mai su disco, mai nel
  registro dei turni (dove resta solo il numero, la fonte e la dimensione). Si salva solo con
  «archiviala» (tool immagine_archivia → cartella dell'archivio). Dal 29/10 (decisione 0034)
  la sua **miniatura di 144 px** resta col turno nell'archivio delle conversazioni per 60 giorni,
  anche per webcam e schermate (*storico, fino al 28/10: «mai su disco» valeva anche per la
  miniatura*).
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
         "screenshot": "lo schermo del computer", "file": "da un file",
         # riletta dal cassetto dei file della persona (08/10, calliope/cassetto.py)
         "cassetto": "dal cassetto"}
# Frasi del ciclo principale (main.py)
FOTO_IN_ATTESA = "Ho la foto. Cosa vuoi sapere?"
FOTO_NON_VISTA = ("La persona ti ha mandato una foto, ma il modello di adesso non vede le "
                  "immagini: dillo in breve, e rispondi al resto se puoi.")
# #96 (16/10): la foto (o il file) mandata senza domanda non c'è più quando la persona torna a
# parlare (conversazione finita, attesa scaduta): un dato del turno, perché il modello non
# inventi una causa («la foto non mi è stata inviata come file», DGX 15/10). Non è una regola
# sul testo: vale per il turno dopo la perdita, qualunque cosa la persona dica
FOTO_PERSA = ("Una foto o un file che la persona ti aveva mandato prima senza domanda non sono "
              "più disponibili (la conversazione era finita o l'attesa scaduta). Se ne parla, "
              "dille di rimandarli; non inventare altre cause.")
# Per quanto, dopo la perdita, il dato vale per il turno della persona: `immagini_persa_s`
# nella configurazione, questo è il predefinito di InAttesa
FOTO_PERSA_S = 600.0
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


def miniatura(jpeg: bytes, lato: int = 360, qualita: int = 70) -> str:
    """La miniatura come data URL (per la scheda sullo schermo): JPEG piccolo. Più piccola
    (`lato`, `qualita`) per la copia nella Conversazione (29/10, #272)."""
    from PIL import Image
    im = Image.open(io.BytesIO(jpeg))
    im.thumbnail((lato, lato))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=qualita)
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

    def __init__(self, durata_s: float = 120.0, massimo: int = 4,
                 persa_s: float = FOTO_PERSA_S):
        self.durata_s = float(durata_s)
        self.persa_s = float(persa_s)
        self.massimo = massimo
        self._lock = threading.Lock()
        self._voci: list[Immagine] = []
        # #96: persona → quando le sue foto in attesa sono andate perse (scadute o tolte)
        self._perse: dict = {}

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
            valide = []
            for i in self._voci:
                if ora - i.arrivata <= self.durata_s:
                    valide.append(i)
                elif i.persona:              # scaduta: persa per il dato del turno (#96)
                    print("   [IMMAGINI] foto in attesa tolta: attesa scaduta (motivo "
                          "scadenza)", flush=True)
                    self._perse[i.persona] = max(self._perse.get(i.persona, 0.0),
                                                 i.arrivata + self.durata_s)
            mie = [i for i in valide if i.persona == persona]
            self._voci = [i for i in valide if i.persona != persona]
        return mie

    def svuota(self):
        with self._lock:
            self._voci.clear()

    def togli(self, persona: str | None, segna: bool = True) -> int:
        """Le foto della persona non valgono più (la sua conversazione è finita, 05/10). Con
        `segna` la perdita vale per il dato del turno `FOTO_PERSA` (#96)."""
        with self._lock:
            prima = len(self._voci)
            self._voci = [i for i in self._voci if i.persona != persona]
            tolte = prima - len(self._voci)
            if tolte and persona and segna:
                self._perse[persona] = time.time()
            return tolte

    def dimentica(self, persona: str | None) -> int:
        """«Dimentica», «ricominciamo» (#96, revisione della PR #113): le foto in attesa della
        persona vanno via con la conversazione, ma non sono «perse»: l'ha chiesto lei, il turno
        dopo non riceve `FOTO_PERSA` (e una perdita segnata prima si dimentica anche lei)."""
        tolte = self.togli(persona, segna=False)
        with self._lock:
            self._perse.pop(persona, None)
        return tolte

    def fine_conversazione(self, persona: str | None, motivo: str = "fine") -> int:
        """Da `Schermi.su_fine_conversazione` (#96, 16/10). Una foto in attesa vale nella
        conversazione in cui è arrivata (05/10): la fine vera («esci», scaduta) la toglie. Se
        invece un'altra voce ha preso la conversazione (`conversazione.SOSTITUITA`: un ospite,
        un'altra persona, anche la propria frase breve sotto soglia) la foto resta fino a
        `durata_s`: la prende solo la stessa persona (`prendi`), mai l'ospite."""
        if motivo == "sostituita":
            if self.di(persona):
                print(f"   [IMMAGINI] foto in attesa tenuta: un'altra voce in mezzo "
                      f"(motivo {motivo})", flush=True)
            return 0
        tolte = self.togli(persona)
        if tolte:
            print(f"   [IMMAGINI] {tolte} foto in attesa tolta: conversazione finita "
                  f"(motivo {motivo})", flush=True)
        return tolte

    def di(self, persona: str | None) -> int:
        """Quante foto (e file) della persona aspettano la domanda (scadute comprese)."""
        with self._lock:
            return sum(1 for i in self._voci if i.persona == persona)

    def persa(self, persona: str | None, entro_s: float | None = None) -> bool:
        """La persona aveva foto in attesa andate perse da meno di `entro_s` (predefinito
        `persa_s`, cioè `immagini_persa_s`) (#96): vero una volta sola, per il dato del turno
        `FOTO_PERSA`."""
        entro_s = self.persa_s if entro_s is None else entro_s
        if not persona:
            return False
        with self._lock:
            quando = self._perse.pop(persona, None)
        return quando is not None and time.time() - quando <= entro_s
