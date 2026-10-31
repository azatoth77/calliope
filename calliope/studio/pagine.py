"""
Le pagine dei materiali dello Studio (29/10, passo 4.2, issue #281, epic #251, decisione 0035):
il controllo del server sulle foto e sui PDF che arrivano da `POST /api/studio/pagina`.

- **I bordi.** Il telefono trova i quattro angoli della pagina con un rilevatore scritto a mano
  (`schermi/pagina/bordi.js`, senza OpenCV.js) e li manda con la foto, in frazioni della foto.
  Qui lo stesso rilevatore, portato in numpy (`rileva`), li **ricontrolla**: vale l'esito del
  server. Su un fotogramma ridotto (`LATO_RILEVA`, 320 px) in grigi: due sfocature 3×3, la
  soglia di Otsu, il fondo scuro collegato al bordo della foto (il tavolo), il pezzo chiaro più
  grande che resta (la pagina, con il testo dentro), i quattro punti estremi (x+y e x−y). La
  forma è plausibile (`plausibili`) se è convessa, prende fra il 15 % e il 99,5 % della foto, ha
  gli angoli fra 40° e 140° e i lati opposti non troppo diversi; e se la pagina chiara copre
  almeno l'85 % del quadrilatero (`copertura`). Se i bordi del telefono sono plausibili e vicini
  a quelli del server (al più il 4 % della diagonale) valgono quelli; se il server ne trova di
  diversi valgono i suoi; se non ne trova, quelli del telefono solo se la pagina chiara li copre;
  altrimenti la foto intera, con l'avviso «bordi». Una pagina che riempie la foto (una scansione,
  la pagina già ritagliata) resta intera senza avviso.
- **Il raddrizzamento.** Con Pillow (`Image.PERSPECTIVE`, i coefficienti risolti con numpy) e
  il lato lungo portato a `studio_pagina_lato` (1600, l'harness della lettura: una foto per
  pagina a 1600 px). *Il progetto diceva `Image.QUAD`, che è bilineare: per una pagina vista di
  sbieco da una fotocamera la trasformazione giusta è la prospettiva, sempre e solo Pillow.*
- **La nitidezza.** La varianza del laplaciano sulla pagina raddrizzata in grigi, a lato 1000
  px; sotto `studio_nitidezza_min` l'avviso «sfocata». Una pagina col lato lungo sotto i 1000 px
  ha l'avviso «piccola» (il banco del 28/10: numeri e formule a 640 px si leggono male).
- **I PDF** si dividono in pagine con pypdfium2 (già nell'extra `archivio`, con le wheel per
  `win_arm64` e `manylinux aarch64`): al più `studio_pdf_max_pagine` pagine, ognuna disegnata
  col lato lungo `studio_pagina_lato`, in un sottoprocesso con un tetto di tempo per pagina
  (`dividi_pdf_a_parte`, revisione della PR #312). Accanto alle pagine resta una copia del PDF
  rifatta con le sole pagine, senza i metadati del file arrivato, per la lettura del testo senza
  OCR (passo 4.3). Il testo **non** si legge qui.
- **I file** stanno in `studio_cartella/pagine/<id della verifica>/`, col nome scelto dal
  server (`scrivi_file`): nessun nome della persona arriva al disco; il percorso si controlla
  quando si scrive (niente `..`, niente link fuori dalla cartella), e il file si crea solo se non
  c'è già.

I byte delle immagini passano dai controlli di `immagini.apri` (tipo vero dai byte, dimensione,
pixel, bomba di decompressione, EXIF); niente librerie native nuove (principio 4).
"""

from __future__ import annotations

import io
import math
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from ..immagini import ImmagineNonValida, apri

LATO_RILEVA = 320
LATO_NITIDEZZA = 1000
# Sotto questo lato lungo la pagina ha l'avviso «piccola» (harness del 28/10)
LATO_PICCOLA = 1000
# Bordi del telefono «uguali» a quelli del server: distanza massima di un angolo, in frazione
# della diagonale del fotogramma ridotto
ACCORDO = 0.04
COPERTURA_MIN = 0.85
AREA_MIN, AREA_MAX = 0.15, 0.995
ANGOLO_MIN, ANGOLO_MAX = 40.0, 140.0
LATI_MIN = 0.4
# La pagina che riempie la foto: oltre questa parte del bordo chiaro non si cerca un tavolo
BORDO_CHIARO = 0.6
# Un bordo forte (Sobel sul fotogramma sfocato) ferma il fondo. Misurato il 29/10 sulle 159 foto
# di studio_immagini.py: il foglio sul tavolo dà più di 150 anche in ombra, le venature meno di
# 30; fra 40 e 80 l'esito è uguale su tutte
MURO = 60
# Lato massimo con cui si apre una foto prima del raddrizzamento (le foto del telefono arrivano
# già sotto i 3000 px; una più grande si decodifica ridotta)
LATO_APERTURA = 4000
QUALITA = 88
# Le dimensioni di una pagina di PDF in punti: al più 200 pollici (il limite di PDF)
PDF_PUNTI_MAX = 14400


class PaginaNonValida(ValueError):
    """La pagina non si usa: il messaggio dice perché, in italiano (va alla pagina)."""


@dataclass
class Pronta:
    """Una pagina pronta da salvare: il JPEG raddrizzato e ciò che ne ha detto il controllo."""
    jpeg: bytes = field(repr=False)
    larghezza: int
    altezza: int
    bordi: str                        # telefono, server, intera, nessuno (con l'avviso «bordi»)
    angoli: list | None = None        # i quattro angoli usati, in frazioni della foto
    avvisi: list = field(default_factory=list)
    nitidezza: float = 0.0


# ─────────────────────────── il rilevatore (lo stesso di bordi.js) ───────────────────────────

def grigio(img, lato: int = LATO_RILEVA):
    """La foto ridotta (lato lungo `lato`) in grigi interi 0–255, come bordi.js `grigio`."""
    import numpy as np
    from PIL import Image
    w, h = img.size
    k = min(1.0, lato / max(w, h))
    if k < 1.0:
        img = img.resize((max(1, round(w * k)), max(1, round(h * k))), Image.BILINEAR)
    a = np.asarray(img.convert("RGB"), dtype=np.int32)
    return (a[..., 0] * 299 + a[..., 1] * 587 + a[..., 2] * 114) // 1000


def sfoca(g):
    """Sfocatura 3×3 a media intera, col bordo ripetuto (bordi.js `sfoca`)."""
    import numpy as np
    p = np.pad(g, 1, mode="edge")
    h, w = g.shape
    s = sum(p[dy:dy + h, dx:dx + w] for dy in range(3) for dx in range(3))
    return s // 9


def otsu(g) -> int:
    """La soglia di Otsu: i valori ≤ soglia sono la classe scura (bordi.js `otsu`)."""
    import numpy as np
    ist = np.bincount(g.ravel(), minlength=256)[:256].astype(np.float64)
    tot = ist.sum()
    somma = float(np.dot(np.arange(256), ist))
    sb = wb = 0.0
    meglio, soglia = -1.0, 0
    for t in range(256):
        wb += ist[t]
        if wb == 0:
            continue
        wf = tot - wb
        if wf == 0:
            break
        sb += t * ist[t]
        mb, mf = sb / wb, (somma - sb) / wf
        tra = wb * wf * (mb - mf) ** 2
        if tra > meglio:
            meglio, soglia = tra, t
    return soglia


def _componente(m: list, w: int, h: int, semi, vista: bytearray) -> list:
    """I pixel veri di `m` (la maschera piatta, in una lista) raggiunti dai `semi` (4-vicini),
    come lista di indici piatti. `vista` si condivide fra più chiamate: un pixel già preso non
    si riprende."""
    coda = []
    for i in semi:
        if m[i] and not vista[i]:
            vista[i] = 1
            coda.append(i)
    k = 0
    ultima = (h - 1) * w
    while k < len(coda):
        i = coda[k]
        k += 1
        x = i % w
        if x > 0 and m[i - 1] and not vista[i - 1]:
            vista[i - 1] = 1
            coda.append(i - 1)
        if x < w - 1 and m[i + 1] and not vista[i + 1]:
            vista[i + 1] = 1
            coda.append(i + 1)
        if i >= w and m[i - w] and not vista[i - w]:
            vista[i - w] = 1
            coda.append(i - w)
        if i < ultima and m[i + w] and not vista[i + w]:
            vista[i + w] = 1
            coda.append(i + w)
    return coda


def sobel(g):
    """|gx| + |gy| di Sobel, col bordo ripetuto (bordi.js `sobel`)."""
    import numpy as np
    p = np.pad(g, 1, mode="edge")
    h, w = g.shape

    def a(dy, dx):
        return p[dy:dy + h, dx:dx + w]
    gx = (a(0, 2) + 2 * a(1, 2) + a(2, 2)) - (a(0, 0) + 2 * a(1, 0) + a(2, 0))
    gy = (a(2, 0) + 2 * a(2, 1) + a(2, 2)) - (a(0, 0) + 2 * a(0, 1) + a(0, 2))
    return np.abs(gx) + np.abs(gy)


def _pagina(g):
    """(maschera della pagina chiara più grande, intera?): il fondo scuro collegato al bordo
    della foto si toglie, poi il pezzo più grande di ciò che resta. Il fondo si allarga solo
    fra i pixel scuri **senza un bordo forte** (Sobel oltre `MURO`): così non entra nella parte
    della pagina in ombra, scura come il tavolo ma separata da lui dal bordo del foglio."""
    import numpy as np
    h, w = g.shape
    t = otsu(g)
    scuro = g <= t
    bordo = [i for i in range(w)] + [(h - 1) * w + i for i in range(w)] + \
        [y * w for y in range(1, h - 1)] + [y * w + w - 1 for y in range(1, h - 1)]
    piatto = scuro.ravel()
    chiari = sum(1 for i in bordo if not piatto[i])
    if chiari > BORDO_CHIARO * len(bordo):
        return None, True
    passa = (scuro & (sobel(g) <= MURO)).ravel().tolist()
    fondo = np.zeros(h * w, dtype=bool)
    fondo[_componente(passa, w, h, bordo, bytearray(h * w))] = True
    resto = ~fondo.reshape(h, w)
    # Il pezzo più grande: i semi in ordine di riga, un pezzo alla volta (a parità il primo)
    vista = bytearray(h * w)
    meglio: list = []
    totale = int(resto.sum())
    r = resto.ravel().tolist()
    for i in np.flatnonzero(resto.ravel()).tolist():
        if vista[i]:
            continue
        pezzo = _componente(r, w, h, [i], vista)
        if len(pezzo) > len(meglio):
            meglio = pezzo
        if len(meglio) * 2 > totale:
            break
    out = np.zeros(h * w, dtype=bool)
    out[meglio] = True
    return out.reshape(h, w), False


def _estremi(maschera):
    """I quattro angoli (alto-sx, alto-dx, basso-dx, basso-sx) dai punti estremi di x+y e x−y,
    in pixel del fotogramma ridotto; il primo in ordine di riga a parità (bordi.js)."""
    import numpy as np
    ys, xs = np.nonzero(maschera)
    s, d = xs + ys, xs - ys
    out = []
    for i in (int(np.argmin(s)), int(np.argmax(d)), int(np.argmax(s)), int(np.argmin(d))):
        out.append((float(xs[i]) + 0.5, float(ys[i]) + 0.5))
    return out


def _px(angoli, w, h):
    return [(float(x) * w, float(y) * h) for x, y in angoli]


def _area(p) -> float:
    return abs(sum(p[i][0] * p[(i + 1) % 4][1] - p[(i + 1) % 4][0] * p[i][1]
                   for i in range(4))) / 2


def angoli_validi(angoli) -> list | None:
    """Gli angoli arrivati dalla pagina come [[x, y]×4] di numeri finiti, o None."""
    if not isinstance(angoli, list) or len(angoli) != 4:
        return None
    out = []
    for a in angoli:
        if not isinstance(a, list) or len(a) != 2:
            return None
        for v in a:
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                return None
        out.append([float(a[0]), float(a[1])])
    return out


def plausibili(angoli, w: int, h: int) -> str | None:
    """None se il quadrilatero (frazioni della foto `w`×`h`) può essere una pagina; altrimenti
    il motivo (bordi.js `plausibili`)."""
    if angoli is None or len(angoli) != 4:
        return "mancano"
    if any(not (-0.02 <= v <= 1.02) for a in angoli for v in a):
        return "fuori"
    p = _px(angoli, w, h)
    segni = []
    for i in range(4):
        a, b, c = p[i], p[(i + 1) % 4], p[(i + 2) % 4]
        segni.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
    if not (all(s > 0 for s in segni) or all(s < 0 for s in segni)):
        return "non_convesso"
    area = _area(p) / (w * h)
    if area < AREA_MIN:
        return "piccolo"
    if area > AREA_MAX:
        return "tutta"
    for i in range(4):
        a, b, c = p[i - 1], p[i], p[(i + 1) % 4]
        v1, v2 = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
        n = math.hypot(*v1) * math.hypot(*v2)
        if n == 0:
            return "angolo"
        ang = math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / n))))
        if not ANGOLO_MIN <= ang <= ANGOLO_MAX:
            return "angolo"
    lati = [math.dist(p[i], p[(i + 1) % 4]) for i in range(4)]
    for i in (0, 1):
        a, b = lati[i], lati[i + 2]
        if min(a, b) < LATI_MIN * max(a, b):
            return "lati"
    return None


def copertura(maschera, angoli) -> float:
    """La parte del quadrilatero (frazioni) coperta dalla pagina chiara della maschera."""
    import numpy as np
    if maschera is None:
        return 0.0
    h, w = maschera.shape
    p = _px(angoli, w, h)
    yy, xx = np.mgrid[0:h, 0:w]
    xx, yy = xx + 0.5, yy + 0.5
    dentro = np.ones((h, w), dtype=bool)
    orario = sum(p[i][0] * p[(i + 1) % 4][1] - p[(i + 1) % 4][0] * p[i][1] for i in range(4)) > 0
    for i in range(4):
        a, b = p[i], p[(i + 1) % 4]
        c = (b[0] - a[0]) * (yy - a[1]) - (b[1] - a[1]) * (xx - a[0])
        dentro &= (c >= 0) if orario else (c <= 0)
    n = int(dentro.sum())
    return float((dentro & maschera).sum()) / n if n else 0.0


def _vicino_al_bordo(angoli) -> bool:
    """Il quadrilatero è quasi la foto intera (ogni angolo entro il 3 % del suo)."""
    ang = ((0, 0), (1, 0), (1, 1), (0, 1))
    return all(abs(a[0] - b[0]) <= 0.03 and abs(a[1] - b[1]) <= 0.03 for a, b in zip(angoli, ang))


def rileva(g) -> dict:
    """Il rilevatore sul fotogramma in grigi (`grigio`): {angoli (frazioni) o None, intera,
    motivo, maschera}. `intera`: la pagina riempie la foto."""
    h, w = g.shape
    b = sfoca(sfoca(g))
    maschera, intera = _pagina(b)
    if intera:
        return {"angoli": None, "intera": True, "motivo": None, "maschera": None}
    if maschera is None or maschera.sum() < AREA_MIN * w * h:
        return {"angoli": None, "intera": False, "motivo": "piccolo", "maschera": maschera}
    angoli = [[x / w, y / h] for x, y in _estremi(maschera)]
    if _vicino_al_bordo(angoli):
        return {"angoli": None, "intera": True, "motivo": None, "maschera": maschera}
    motivo = plausibili(angoli, w, h)
    if motivo is None and copertura(maschera, angoli) < COPERTURA_MIN:
        motivo = "copertura"
    return {"angoli": angoli if motivo is None else None, "intera": False, "motivo": motivo,
            "maschera": maschera}


def distanza(a, b, w: int, h: int) -> float:
    """La distanza massima fra gli angoli corrispondenti, in frazione della diagonale."""
    d = math.hypot(w, h)
    return max(math.dist((p[0] * w, p[1] * h), (q[0] * w, q[1] * h)) for p, q in zip(a, b)) / d


def scegli_bordi(img, angoli_tel) -> tuple[str, list | None, dict]:
    """(da dove, angoli da usare o None, esito del server). «telefono» se il server li
    conferma (o, senza bordi suoi, la pagina chiara li copre); «server» se i suoi sono diversi;
    «intera» se la pagina riempie la foto; «nessuno» se niente è plausibile."""
    g = grigio(img)
    h, w = g.shape
    s = rileva(g)
    tel = angoli_validi(angoli_tel)
    tel_ok = tel is not None and plausibili(tel, w, h) is None
    if s["angoli"] is not None:
        if tel_ok and distanza(tel, s["angoli"], w, h) <= ACCORDO:
            return "telefono", tel, s
        return "server", s["angoli"], s
    if s["intera"]:
        return "intera", None, s
    if tel_ok and copertura(s["maschera"], tel) >= COPERTURA_MIN:
        return "telefono", tel, s
    return "nessuno", None, s


# ─────────────────────────── raddrizzare, nitidezza ───────────────────────────

def _coefficienti(uscita, ingresso):
    """I coefficienti di Image.PERSPECTIVE che portano i punti `uscita` sui punti `ingresso`."""
    import numpy as np
    m, b = [], []
    for (x, y), (u, v) in zip(uscita, ingresso):
        m.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        m.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b += [u, v]
    return np.linalg.solve(np.array(m, float), np.array(b, float)).tolist()


def raddrizza(img, angoli, lato: int):
    """La pagina dentro gli `angoli` (frazioni, alto-sx, alto-dx, basso-dx, basso-sx) raddrizzata
    con il lato lungo al più `lato`; senza angoli la foto intera ridotta."""
    from PIL import Image
    w, h = img.size
    if angoli is None:
        k = min(1.0, lato / max(w, h))
        if k < 1.0:
            img = img.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
        return img
    p = _px(angoli, w, h)
    larg = max(math.dist(p[0], p[1]), math.dist(p[3], p[2]))
    alt = max(math.dist(p[0], p[3]), math.dist(p[1], p[2]))
    k = min(1.0, lato / max(larg, alt))
    W, H = max(8, round(larg * k)), max(8, round(alt * k))
    coeff = _coefficienti([(0, 0), (W, 0), (W, H), (0, H)], p)
    return img.transform((W, H), Image.PERSPECTIVE, coeff, Image.BICUBIC,
                         fillcolor=(255, 255, 255))


def nitidezza(img) -> float:
    """La varianza del laplaciano (4 vicini) in grigi a lato `LATO_NITIDEZZA`, dopo aver
    portato il contrasto fra l'1° e il 99° percentile a 0–255 (una pagina in ombra non sembra
    sfocata solo perché è scura). bordi.js fa lo stesso sull'anteprima."""
    import numpy as np
    gi = grigio(img, LATO_NITIDEZZA)
    if gi.shape[0] < 3 or gi.shape[1] < 3:
        return 0.0
    # I percentili dall'istogramma (gli stessi in bordi.js): il primo valore oltre l'1 % e il
    # primo che arriva al 99 %
    cum = np.cumsum(np.bincount(gi.ravel(), minlength=256)[:256])
    n = int(cum[-1])
    basso = int(np.searchsorted(cum, 0.01 * n, side="right"))
    alto = int(np.searchsorted(cum, 0.99 * n, side="left"))
    g = gi.astype(np.float64)
    if alto - basso < 1:
        return 0.0
    g = np.clip((g - basso) * (255.0 / (alto - basso)), 0, 255)
    lap = (4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:])
    return float(lap.var())


def _jpeg(img) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=QUALITA, optimize=True)   # senza EXIF
    return buf.getvalue()


def _avvisi(img, nit: float, soglia: float) -> list:
    out = []
    if nit < soglia:
        out.append("sfocata")
    if max(img.size) < LATO_PICCOLA:
        out.append("piccola")
    return out


def prepara_foto(dati: bytes, angoli_tel, lato: int = 1600, max_byte: int = 15_000_000,
                 soglia_nitidezza: float = 60.0) -> Pronta:
    """Una foto di una pagina: controllata (`immagini.apri`), i bordi ricontrollati, raddrizzata
    al lato `lato`, la nitidezza misurata. Solleva PaginaNonValida."""
    try:
        img = apri(dati, LATO_APERTURA, max_byte)
    except ImmagineNonValida as e:
        raise PaginaNonValida(str(e)) from None
    da, angoli, _s = scegli_bordi(img, angoli_tel)
    pagina = raddrizza(img, angoli, lato)
    nit = nitidezza(pagina)
    avvisi = _avvisi(pagina, nit, soglia_nitidezza)
    if da == "nessuno":
        avvisi.insert(0, "bordi")
    return Pronta(_jpeg(pagina), pagina.width, pagina.height, da,
                  [[round(x, 4), round(y, 4)] for x, y in angoli] if angoli else None,
                  avvisi, round(nit, 1))


# ─────────────────────────── PDF ───────────────────────────

def e_pdf(dati: bytes) -> bool:
    return dati[:5] == b"%PDF-"


def dividi_pdf(dati: bytes, lato: int = 1600, max_pagine: int = 40,
               soglia_nitidezza: float = 60.0) -> list[Pronta]:
    """Le pagine di un PDF disegnate col lato lungo `lato`, al più `max_pagine` (oltre: rifiuto,
    non un taglio silenzioso). Solleva PaginaNonValida. Nel processo che chiama: il server usa
    `dividi_pdf_a_parte`, in un sottoprocesso con un tetto di tempo per pagina."""
    return _dividi(dati, lato, max_pagine, soglia_nitidezza)[0]


def _apri_pdf(dati: bytes):
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise PaginaNonValida("qui non so aprire i PDF (manca pypdfium2)") from None
    try:
        return pdfium, pdfium.PdfDocument(dati)
    except pdfium.PdfiumError as e:
        if "password" in str(e).lower():
            raise PaginaNonValida("il PDF è protetto da una password") from None
        raise PaginaNonValida("il PDF è rovinato") from None
    except Exception:  # noqa: BLE001 - un file ostile non deve far cadere nulla
        raise PaginaNonValida("il PDF è rovinato") from None


def _dividi(dati: bytes, lato: int, max_pagine: int, soglia_nitidezza: float,
            avanti=None) -> tuple[list[Pronta], bytes | None]:
    """(pagine, PDF pulito). Il PDF pulito ha le sole pagine, rifatte in un documento nuovo
    (`import_pages`): senza il dizionario Info né i metadati XMP del file arrivato (autore,
    programma, date), ma col testo delle pagine per la lettura del passo 4.3. `avanti(i, n)` dopo
    l'apertura (i = -1) e dopo ogni pagina: il sottoprocesso lo dice al server."""
    pdfium, pdf = _apri_pdf(dati)
    try:
        n = len(pdf)
        if n < 1:
            raise PaginaNonValida("il PDF non ha pagine")
        if n > max_pagine:
            raise PaginaNonValida(f"il PDF ha {n} pagine: al più {max_pagine}")
        if avanti:
            avanti(-1, n)
        out = []
        for i in range(n):
            pagina = pdf[i]
            try:
                w, h = pagina.get_size()
                if not (0 < w <= PDF_PUNTI_MAX and 0 < h <= PDF_PUNTI_MAX):
                    raise PaginaNonValida(f"la pagina {i + 1} del PDF ha una misura strana")
                k = lato / max(w, h)
                img = pagina.render(scale=k).to_pil().convert("RGB")
            except PaginaNonValida:
                raise
            except Exception:  # noqa: BLE001
                raise PaginaNonValida(f"la pagina {i + 1} del PDF è rovinata") from None
            finally:
                pagina.close()
            nit = nitidezza(img)
            out.append(Pronta(_jpeg(img), img.width, img.height, "pdf", None,
                              _avvisi(img, nit, soglia_nitidezza), round(nit, 1)))
            if avanti:
                avanti(i, n)
        pulito = None
        try:
            nuovo = pdfium.PdfDocument.new()
            try:
                nuovo.import_pages(pdf)
                buf = io.BytesIO()
                nuovo.save(buf)
                pulito = buf.getvalue()
            finally:
                nuovo.close()
        except Exception:  # noqa: BLE001 — senza la copia pulita non si tiene niente
            pulito = None
        return out, pulito
    finally:
        pdf.close()


# Il tetto di tempo per aprire il PDF e per ogni pagina, nel sottoprocesso (revisione della PR
# #312: una pagina vettoriale pesantissima non deve tenere occupato il server)
PDF_TEMPO_PAGINA_S = 10.0
# L'avvio del sottoprocesso (Python e gli import di numpy, Pillow e pypdfium2), a parte: su una
# macchina carica o a freddo può volere più di una pagina (seconda revisione della PR #312)
PDF_TEMPO_AVVIO_S = 30.0


async def dividi_pdf_a_parte(dati: bytes, lato: int = 1600, max_pagine: int = 40,
                             soglia_nitidezza: float = 60.0,
                             tempo_pagina_s: float = PDF_TEMPO_PAGINA_S,
                             provvisori=None, tempo_avvio_s: float = PDF_TEMPO_AVVIO_S):
    """`_dividi` in un sottoprocesso (`python -m calliope.studio.pagine --pdf`), con al più
    `tempo_pagina_s` per aprire il PDF e per ogni pagina: oltre, il processo si ferma e il PDF è
    rifiutato. Nessun thread del server occupato: il processo si aspetta con asyncio. Le pagine
    passano da una cartella temporanea, tolta subito dopo. (pagine, PDF pulito o None).
    Solleva PaginaNonValida."""
    import asyncio
    import json
    import shutil
    import sys
    import tempfile
    # Dentro la cartella dello Studio (`provvisori`, studio_cartella/tmp), che la rotazione e
    # l'avvio puliscono: pagine di quaderni non restano nella cartella di sistema dopo un crollo
    if provvisori is not None:
        Path(provvisori).mkdir(parents=True, exist_ok=True)
    cartella = Path(tempfile.mkdtemp(prefix="pdf-", dir=str(provvisori) if provvisori else None))
    radice = Path(__file__).resolve().parent.parent.parent
    proc = None
    try:
        (cartella / "ingresso.pdf").write_bytes(dati)
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "calliope.studio.pagine", "--pdf", str(cartella),
            str(int(lato)), str(int(max_pagine)), str(float(soglia_nitidezza)), cwd=str(radice),
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
        n, fatte, pronto = None, 0, False
        while True:
            try:
                # La prima riga («pronto») dopo l'avvio di Python e gli import: un tempo suo, più
                # largo; poi `tempo_pagina_s` per aprire il PDF e per ogni pagina
                riga = await asyncio.wait_for(proc.stdout.readline(),
                                              tempo_pagina_s if pronto else tempo_avvio_s)
            except asyncio.TimeoutError:
                raise PaginaNonValida("il PDF è troppo pesante da dividere" + (
                    f" (pagina {fatte + 1})" if n else "")) from None
            t = riga.decode("utf-8", "replace").strip()
            if not t:
                raise PaginaNonValida("il PDF non si divide")
            if t.startswith("errore "):
                raise PaginaNonValida(t[len("errore "):][:200])
            if t == "pronto":
                pronto = True
            elif t.startswith("pagine "):
                n = int(t.split()[1])
            elif t.startswith("pagina "):
                fatte += 1
            elif t == "fine":
                break
        await asyncio.wait_for(proc.wait(), tempo_pagina_s)
        meta = json.loads((cartella / "pagine.json").read_text(encoding="utf-8"))
        out = [Pronta((cartella / f"p{i}.jpg").read_bytes(), m["larghezza"], m["altezza"],
                      "pdf", None, list(m["avvisi"]), float(m["nitidezza"]))
               for i, m in enumerate(meta)]
        f = cartella / "pulito.pdf"
        return out, (f.read_bytes() if f.exists() else None)
    finally:
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
                await proc.wait()
            except (ProcessLookupError, OSError):
                pass
        shutil.rmtree(cartella, ignore_errors=True)


def _figlio_pdf(argv) -> int:
    """Il sottoprocesso di `dividi_pdf_a_parte`: legge `ingresso.pdf`, scrive le pagine e il PDF
    pulito nella stessa cartella, e dice ogni passo con una riga su stdout."""
    import json
    cartella, lato, max_pagine, soglia = Path(argv[0]), int(argv[1]), int(argv[2]), float(argv[3])

    def avanti(i, n):
        print(f"pagine {n}" if i < 0 else f"pagina {i + 1}", flush=True)
    # Gli import prima di «pronto»: il tempo d'avvio non conta per la prima pagina
    try:
        import numpy  # noqa: F401
        import PIL.Image  # noqa: F401
        import pypdfium2  # noqa: F401
    except ImportError:
        pass
    print("pronto", flush=True)
    try:
        pronte, pulito = _dividi((cartella / "ingresso.pdf").read_bytes(), lato, max_pagine,
                                 soglia, avanti)
    except PaginaNonValida as e:
        print("errore " + " ".join(str(e).split()), flush=True)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"errore il PDF non si divide ({type(e).__name__})", flush=True)
        return 2
    meta = []
    for i, p in enumerate(pronte):
        (cartella / f"p{i}.jpg").write_bytes(p.jpeg)
        meta.append({"larghezza": p.larghezza, "altezza": p.altezza, "avvisi": p.avvisi,
                     "nitidezza": p.nitidezza})
    if pulito:
        (cartella / "pulito.pdf").write_bytes(pulito)
    (cartella / "pagine.json").write_text(json.dumps(meta), encoding="utf-8")
    print("fine", flush=True)
    return 0


# ─────────────────────────── file su disco ───────────────────────────

def scrivi_file(cartella, verifica: int, dati: bytes, estensione: str) -> str:
    """Scrive `dati` in `cartella/pagine/<verifica>/<nome a caso>.<estensione>` e restituisce il
    percorso relativo alla cartella (con «/»). Il nome lo sceglie il server; il percorso si
    controlla quando si scrive: dentro la cartella anche dopo aver seguito i link, file nuovo
    (mai sovrascritto). Solleva OSError o PermissionError."""
    rel, f = apri_nuovo(cartella, verifica, estensione)
    try:
        f.write(dati)
    finally:
        f.close()
    return rel


# Le estensioni dei file nella cartella delle pagine: le pagine (jpg), le copie dei PDF (pdf) e,
# dal 31/10 (#298), il file arrivato di un'importazione (imp), tolto a lavoro finito
ESTENSIONI = ("jpg", "pdf", "imp")


def apri_nuovo(cartella, verifica: int, estensione: str):
    """(percorso relativo, file aperto in scrittura) di un file nuovo in
    `cartella/pagine/<verifica>/`, con gli stessi controlli di `scrivi_file`: per chi scrive a
    pezzi (l'importazione, che non tiene il file arrivato in memoria). Chi lo apre lo chiude."""
    if estensione not in ESTENSIONI:
        raise ValueError("estensione")
    if cartella is None:
        raise PermissionError("manca la cartella dello Studio")
    base = Path(cartella)
    base.mkdir(parents=True, exist_ok=True)
    base = base.resolve()
    rel = f"pagine/{int(verifica)}/{secrets.token_hex(12)}.{estensione}"
    dest = base / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    reale = dest.parent.resolve()
    if base not in reale.parents or reale != (base / "pagine" / str(int(verifica))).resolve() \
            or (base / "pagine").is_symlink() or dest.parent.is_symlink():
        raise PermissionError("la cartella delle pagine esce dalla cartella dello Studio")
    return rel, open(reale / dest.name, "xb")


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 6 and sys.argv[1] == "--pdf":
        sys.exit(_figlio_pdf(sys.argv[2:]))
    sys.exit(2)
