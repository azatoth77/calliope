"""Le pagine dello Studio come foto, generate dai testi della verità (28/10/2026, #293; banco in
prove/manuali/banco_studio.py, passo manuale in prove/manuali/studio.md).

Legge i materiali di `prove/manuali/studio/*.json` (testo esatto di ogni pagina) e disegna con
Pillow, per ogni pagina, le varianti:

- `pulita`: la pagina dritta, come uscirebbe dal raddrizzamento del server (4.2);
- `storta`: una foto in prospettiva su un tavolo, girata di qualche grado;
- `ombra`: luce non uniforme (un'ombra diagonale e gli angoli scuri), colore caldo;
- `bassa`: lato lungo 640 px e JPEG di qualità 15;
- `capovolta`: la pagina girata di 180°;
- `quadretti`: lo stesso testo «copiato a mano» su un quaderno a quadretti (pseudo-scritto);
- `doppia`: due pagine vicine in una foto sola, un libro aperto con la piega al centro (solo per
  le coppie di pagine di libro consecutive).

Gli appunti (`tipo: appunti`) sono sempre a quadretti e a mano. Le righe in `nascosta` si
scrivono in grigio chiarissimo (testo quasi invisibile: istruzioni nascoste).

**Font.** Solo font liberi già presenti nel sistema, mai nel repository. Stampa: DejaVu Sans e
Serif (licenza Bitstream Vera, libera) o Liberation (SIL OFL). Pseudo-scritto: Purisa del pacchetto
`fonts-thai-tlwg` (GPL con l'eccezione per i font) o Z003 di `fonts-urw-base35` (AGPL), presenti
sulla DGX. Con `--font-stampa`, `--font-titolo` e `--font-mano` se ne sceglie un altro. Su
Windows, senza quei font, valgono di ripiego quelli del sistema (Georgia, Arial, Ink Free): la
loro licenza non è libera, quindi le immagini fatte così restano sul portatile e non si
pubblicano (lo dice anche il programma). Lo scritto a mano vero non si genera: si fotografa (vedi
la cartella delle foto vere nel passo manuale).

Le immagini vanno in una cartella fuori dal repository (`--uscita`), con `manifest.json`: per ogni
file la verifica, la variante, le pagine che contiene (nell'ordine da sinistra a destra) e se è
capovolta. Solo Pillow e numpy.

    python prove/manuali/studio_immagini.py --uscita /tmp/banco-studio-293/immagini
"""
from __future__ import annotations

import argparse
import json
import random
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

QUI = Path(__file__).resolve().parent
MATERIALI = QUI / "studio"

VARIANTI = ("pulita", "storta", "ombra", "bassa", "capovolta", "quadretti", "doppia")

STAMPA = ["/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
          "C:/Windows/Fonts/DejaVuSerif.ttf"]
STAMPA_TITOLO = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                 "C:/Windows/Fonts/DejaVuSans-Bold.ttf"]
MANO = ["/usr/share/fonts/truetype/tlwg/Purisa.ttf",
        "/usr/share/fonts/opentype/tlwg/Purisa.otf",
        "/usr/share/fonts/opentype/urw-base35/Z003-MediumItalic.otf"]
# Ripiego di Windows, licenza non libera: solo per immagini che restano sul portatile
RIPIEGO_WINDOWS = {"testo": "C:/Windows/Fonts/georgia.ttf",
                   "titolo": "C:/Windows/Fonts/arialbd.ttf",
                   "mano": "C:/Windows/Fonts/Inkfree.ttf"}

LATO = (1240, 1754)          # A4 a 150 dpi


def _font(candidati, misura, scelto=None, ripiego=None, log=print):
    for p in ([scelto] if scelto else []) + candidati:
        if p and Path(p).is_file():
            return ImageFont.truetype(p, misura), p
    if ripiego and Path(ripiego).is_file():
        log(f"[immagini] ATTENZIONE: nessun font libero, uso {ripiego} del sistema (licenza non "
            "libera): le immagini restano su questa macchina, non si pubblicano")
        return ImageFont.truetype(ripiego, misura), ripiego
    raise SystemExit(f"nessun font libero trovato fra {candidati}: indicane uno con --font-*")


def _rng(*chiavi) -> random.Random:
    return random.Random(zlib.crc32("|".join(map(str, chiavi)).encode()))


def _a_capo(testo: str, font, larghezza: int, draw) -> list[str]:
    righe = []
    for par in testo.split("\n"):
        parole, riga = par.split(" "), ""
        for w in parole:
            prova = (riga + " " + w).strip()
            if draw.textlength(prova, font=font) <= larghezza or not riga:
                riga = prova
            else:
                righe.append(riga)
                riga = w
        righe.append(riga)
    return righe


def pagina_stampata(p: dict, fonts: dict) -> Image.Image:
    img = Image.new("RGB", LATO, (252, 250, 244))
    d = ImageDraw.Draw(img)
    marg, y = 110, 120
    righe_src = p["testo"].split("\n")
    nascoste = set(p.get("nascosta") or [])
    numero = p.get("numero")
    if numero and righe_src and righe_src[-1].strip() == numero:
        righe_src = righe_src[:-1]
    for i, src in enumerate(righe_src):
        titolo = i == 0
        f = fonts["titolo"] if titolo else fonts["testo"]
        colore = (236, 236, 232) if i in nascoste else (25, 25, 30)
        for r in _a_capo(src, f, LATO[0] - 2 * marg, d):
            d.text((marg, y), r, font=f, fill=colore)
            y += int(f.size * (1.6 if titolo else 1.45))
        y += 14 if titolo else 6
    if numero:
        w = d.textlength(numero, font=fonts["testo"])
        d.text(((LATO[0] - w) / 2, LATO[1] - 110), numero, font=fonts["testo"], fill=(60, 60, 60))
    return img


def pagina_a_mano(p: dict, fonts: dict, seme: str) -> Image.Image:
    """Quaderno a quadretti da 5 mm, inchiostro blu, righe un po' storte (pseudo-scritto)."""
    r = _rng(seme, p["id"])
    img = Image.new("RGB", LATO, (250, 251, 248))
    d = ImageDraw.Draw(img)
    passo = 30
    for x in range(0, LATO[0], passo):
        d.line([(x, 0), (x, LATO[1])], fill=(196, 214, 232), width=1)
    for y in range(0, LATO[1], passo):
        d.line([(0, y), (LATO[0], y)], fill=(196, 214, 232), width=1)
    d.line([(150, 0), (150, LATO[1])], fill=(230, 150, 150), width=2)
    f = fonts["mano"]
    y = 90
    for src in p["testo"].split("\n"):
        for riga in _a_capo(src, f, LATO[0] - 260, d):
            strato = Image.new("RGBA", (LATO[0], int(f.size * 2.2)), (0, 0, 0, 0))
            ds = ImageDraw.Draw(strato)
            x = 175 + r.randint(-6, 10)
            for parola in riga.split(" "):
                dy = r.randint(-3, 3)
                ds.text((x, 10 + dy), parola, font=f, fill=(25, 45, 140, 255))
                x += ds.textlength(parola + " ", font=f) + r.randint(-2, 4)
            strato = strato.rotate(r.uniform(-1.2, 1.2), resample=Image.BICUBIC, center=(175, 20))
            img.paste(strato, (0, y), strato)
            y += int(passo * 2) + r.choice((0, 0, passo))
            if y > LATO[1] - 120:
                break
    return img


def _tavolo(lato, r) -> Image.Image:
    import numpy as np
    h, w = lato[1], lato[0]
    base = np.zeros((h, w, 3), np.float32)
    base[:] = (128, 92, 60)
    venature = np.sin(np.linspace(0, 40, w)[None, :] + r.uniform(0, 6)
                      + np.random.default_rng(r.randint(0, 10**6)).normal(0, .4, (h, 1)))
    base += venature[..., None] * 12
    return Image.fromarray(np.clip(base, 0, 255).astype("uint8"))


def _prospettiva(img: Image.Image, r, sfondo=None) -> Image.Image:
    """La pagina sul tavolo, vista un po' di sbieco: un quadrilatero non rettangolare."""
    w, h = img.size
    W, H = int(w * 1.25), int(h * 1.2)
    tav = sfondo or _tavolo((W, H), r)
    # angoli di destinazione (alto-sx, alto-dx, basso-dx, basso-sx)
    dst = [(W * .12 + r.uniform(-20, 40), H * .08 + r.uniform(0, 30)),
           (W * .86 + r.uniform(-30, 20), H * .05 + r.uniform(0, 40)),
           (W * .93 + r.uniform(-20, 10), H * .93 + r.uniform(-30, 0)),
           (W * .05 + r.uniform(0, 30), H * .9 + r.uniform(-20, 10))]
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    coeff = _coeff(dst, src)
    pag = img.convert("RGBA").transform((W, H), Image.PERSPECTIVE, coeff, Image.BICUBIC,
                                        fillcolor=(0, 0, 0, 0))
    tav = tav.convert("RGBA")
    tav.alpha_composite(pag)
    return tav.convert("RGB").rotate(r.uniform(-4, 4), resample=Image.BICUBIC, expand=False,
                                     fillcolor=(110, 80, 50))


def _coeff(dst, src):
    import numpy as np
    m = []
    for (x, y), (u, v) in zip(dst, src):
        m.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        m.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    a = np.array(m, float)
    b = np.array([c for p in src for c in p], float)
    return np.linalg.solve(a, b).tolist()


def _ombra(img: Image.Image, r) -> Image.Image:
    import numpy as np
    a = np.asarray(img).astype(np.float32)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    ang = r.uniform(.6, 1.0)
    diag = (xx * ang + yy) / (w * ang + h)
    luce = 0.55 + 0.45 * np.clip((diag - 0.25) * 2.2, 0, 1)        # ombra in alto a sinistra
    cx, cy = w / 2, h / 2
    vign = 1 - 0.35 * (((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2) / 2
    a *= (luce * vign)[..., None]
    a[..., 2] *= 0.86                                                # luce calda
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8"))


def _jpeg(img: Image.Image, path: Path, q: int = 88):
    img.save(path, "JPEG", quality=q)


def libro_aperto(a: Image.Image, b: Image.Image, r) -> Image.Image:
    import numpy as np
    w, h = a.size
    doppia = Image.new("RGB", (w * 2 + 20, h + 40), (240, 236, 226))
    doppia.paste(a, (10, 20))
    doppia.paste(b, (w + 10, 20))
    arr = np.asarray(doppia).astype(np.float32)
    xs = np.arange(arr.shape[1])
    piega = 1 - 0.55 * np.exp(-((xs - arr.shape[1] / 2) / 38.0) ** 2)
    arr *= piega[None, :, None]
    img = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))
    img = _prospettiva(img, r)
    return img.resize((img.width * 2 // 3, img.height * 2 // 3), Image.LANCZOS)


def genera(uscita: Path, materiali: Path = MATERIALI, varianti=VARIANTI, font_mano=None,
           font_stampa=None, solo=None, log=print, font_titolo=None) -> list[dict]:
    uscita.mkdir(parents=True, exist_ok=True)
    fonts = {}
    fonts["testo"], p_testo = _font(STAMPA, 30, font_stampa, RIPIEGO_WINDOWS["testo"], log)
    fonts["titolo"], p_tit = _font(STAMPA_TITOLO, 40, font_titolo, RIPIEGO_WINDOWS["titolo"], log)
    fonts["mano"], p_mano = _font(MANO, 34, font_mano, RIPIEGO_WINDOWS["mano"], log)
    log(f"[immagini] font: stampa {p_testo}, titoli {p_tit}, a mano {p_mano}")
    manifest = []
    for f in sorted(materiali.glob("*.json")):
        if f.name in ("harness.json",) or f.name.startswith(("copione", "esempio")):
            continue
        ver = json.loads(f.read_text(encoding="utf-8"))
        if "pagine" not in ver or (solo and ver["id"] not in solo):
            continue
        cartella = uscita / ver["id"]
        cartella.mkdir(exist_ok=True)
        dritte = {}
        for p in ver["pagine"]:
            seme = ver["id"]
            a_mano = p.get("tipo") == "appunti"
            base = pagina_a_mano(p, fonts, seme) if a_mano else pagina_stampata(p, fonts)
            dritte[p["id"]] = base
            for v in varianti:
                if v == "doppia":
                    continue
                r = _rng(ver["id"], p["id"], v)
                if v == "pulita":
                    img, q = base, 90
                elif v == "storta":
                    img, q = _prospettiva(base, r), 85
                elif v == "ombra":
                    img, q = _ombra(_prospettiva(base, r), r), 85
                elif v == "bassa":
                    k = 640 / max(base.size)
                    img = base.resize((int(base.width * k), int(base.height * k)), Image.BILINEAR)
                    img, q = img.filter(ImageFilter.GaussianBlur(0.4)), 15
                elif v == "capovolta":
                    img, q = base.rotate(180), 88
                elif v == "quadretti":
                    if a_mano:
                        continue               # gli appunti sono già a mano: uguale a «pulita»
                    img, q = pagina_a_mano(p, fonts, seme + "-copia"), 88
                else:
                    raise ValueError(v)
                nome = f"{ver['id']}/{p['id']}-{v}.jpg"
                _jpeg(img, uscita / nome, q)
                manifest.append({"file": nome, "verifica": ver["id"], "variante": v,
                                 "pagine": [p["id"]], "capovolta": v == "capovolta",
                                 "a_mano": a_mano or v == "quadretti"})
        if "doppia" in varianti:
            libro = [p["id"] for p in ver["pagine"] if p.get("tipo") == "libro"]
            for i in range(0, len(libro) - 1, 2):
                a, b = libro[i], libro[i + 1]
                img = libro_aperto(dritte[a], dritte[b], _rng(ver["id"], a, b))
                nome = f"{ver['id']}/{a}+{b}-doppia.jpg"
                _jpeg(img, uscita / nome, 85)
                manifest.append({"file": nome, "verifica": ver["id"], "variante": "doppia",
                                 "pagine": [a, b], "capovolta": False, "a_mano": False})
    (uscita / "manifest.json").write_text(json.dumps(
        {"font": {"stampa": p_testo, "titoli": p_tit, "mano": p_mano}, "immagini": manifest},
        ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"[immagini] {len(manifest)} immagini in {uscita}")
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--uscita", required=True, type=Path, help="cartella fuori dal repository")
    ap.add_argument("--materiali", type=Path, default=MATERIALI)
    ap.add_argument("--varianti", default=",".join(VARIANTI))
    ap.add_argument("--verifiche", default="", help="solo queste (storia,matematica,…)")
    ap.add_argument("--font-mano", default=None)
    ap.add_argument("--font-stampa", default=None)
    ap.add_argument("--font-titolo", default=None)
    a = ap.parse_args(argv)
    uscita = a.uscita.expanduser().resolve()
    # dentro la cartella del repository (per percorso, non per prefisso: «/tmp/b303-immagini» non
    # è dentro «/tmp/b303»), fuori da privato/
    if uscita.is_relative_to(QUI.parent.parent.resolve()) and "privato" not in uscita.parts:
        raise SystemExit("le immagini non vanno nel repository: scegli una cartella fuori "
                         "(o dentro privato/)")
    genera(uscita, a.materiali, tuple(v for v in a.varianti.split(",") if v), a.font_mano,
           a.font_stampa, set(filter(None, a.verifiche.split(","))) or None,
           font_titolo=a.font_titolo)


if __name__ == "__main__":
    main()
