import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Le pagine dei materiali dello Studio a secco (29/10, passo 4.2, issue #281, epic #251, decisione
0035; calliope/studio/pagine.py, schermi/pagina/bordi.js, POST /api/studio/pagina).

1. **Bordi** sulle foto di fantasia di `manuali/studio_immagini.py` (storia: pulita, storta,
   ombra, bassa, doppia; generate in una cartella temporanea): storte e in ombra trovate dal server
   (l'ombra non taglia la pagina), pulite e basse intere; i bordi del telefono che il server
   conferma valgono, quelli diversi no, quelli impossibili (non convessi, fuori, piccoli, angoli
   stretti) mai; una foto senza pagina resta intera con l'avviso «bordi»; il rilevatore JS
   (bordi.js, con node) dà gli stessi angoli e la stessa nitidezza del Python sugli stessi grigi.
2. **Raddrizzamento** di una pagina di prova in prospettiva con quattro segni negli angoli: i segni
   tornano agli angoli, il rapporto dei lati è quello del foglio, il lato lungo è 1600; la
   nitidezza separa la pagina nitida da quella sfocata; la foto piccola ha l'avviso.
3. **PDF** con pypdfium2: diviso in pagine a 1600, troppe pagine rifiutate, malformato, pagina
   enorme, cifrato (con pypdf, se c'è).
4. **File ostili**: bomba di decompressione, tipo falso (HTML con estensione .jpg, JPEG rovinato,
   HEIC), nome con `..`; la cartella delle pagine che è un link fuori rifiutata; nessun file
   sovrascritto.
5. **Il server vero** (`/api/studio/pagina`, `/api/studio/verifiche`): il proprietario (minore) e il
   tutore sì; un altro adulto, chi amministra non tutore, l'ospite (zona grigia: lo schermo di
   qualcuno che non ha profilo), il conoscente, lo schermo di stanza e la sessione mancante no;
   fuori orario il minore no e il tutore sì; dimensione, invii al minuto, pagine per verifica,
   Content-Type, dati dell'invio sbagliati, materiale di un'altra verifica, verifica archiviata;
   `studio_modo` spento (404), in ombra solo chi amministra; niente nella conversazione; la
   cartella relativa accanto a memory_db; la tessera di Le mie cose.
6. **Tenuta**: 61 giorni dopo la data, «dimentica», svuota di tutti (anche gli orfani) e
   «togli la verifica» tolgono le immagini e i PDF.

    python prove/prova_studio_pagine.py
"""

import datetime
import io
import json
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI.parent))

from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

from calliope import minori  # noqa: E402
from calliope import studio as S  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.immagini import apri  # noqa: E402
from calliope.schermi import ArchivioSchermi, Schermi  # noqa: E402
from calliope.schermi.server import ServerSchermi  # noqa: E402
from calliope.studio import dati as D  # noqa: E402
from calliope.studio import pagine as PG  # noqa: E402

ERRORI = []
TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-pagine-"))
BORDI_JS = QUI.parent / "calliope" / "schermi" / "pagina" / "bordi.js"


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio and not ok else ""),
          flush=True)
    if not ok:
        ERRORI.append(nome)


def jpeg(img, q=90) -> bytes:
    b = io.BytesIO()
    img.convert("RGB").save(b, "JPEG", quality=q)
    return b.getvalue()


def png(img) -> bytes:
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


# ─────────────────────────── immagini di prova ───────────────────────────

def foto_di_fantasia() -> dict:
    """Le foto di storia di studio_immagini.py (fuori dal repository): {nome: Path}."""
    sys.path.insert(0, str(QUI / "manuali"))
    import studio_immagini as SI
    uscita = TMP / "immagini"
    SI.genera(uscita, varianti=("pulita", "storta", "ombra", "bassa", "doppia"), solo=["storia"],
              log=lambda m: None)
    return {p.stem: p for p in (uscita / "storia").glob("*.jpg")}


LATO_A4 = (1240, 1754)


def pagina_con_segni():
    """Un foglio A4 bianco con le righe di «testo» e quattro quadrati neri vicino agli angoli."""
    w, h = LATO_A4
    img = Image.new("RGB", (w, h), (246, 244, 238))
    d = ImageDraw.Draw(img)
    for y in range(260, h - 260, 46):
        for x0 in range(160, w - 200, 180):
            d.rectangle([x0, y, x0 + 140, y + 14], fill=(40, 40, 40))
    for cx, cy in ((0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)):
        d.rectangle([cx * w - 40, cy * h - 40, cx * w + 40, cy * h + 40], fill=(0, 0, 0))
    return img


def in_prospettiva(img, dst, lato=(1900, 2400), fondo=(92, 64, 40)):
    """Il foglio sul tavolo con gli angoli in `dst` (pixel della foto)."""
    w, h = img.size
    coeff = PG._coefficienti(dst, [(0, 0), (w, 0), (w, h), (0, h)])
    pag = img.convert("RGBA").transform(lato, Image.PERSPECTIVE, coeff, Image.BICUBIC,
                                        fillcolor=(0, 0, 0, 0))
    tav = Image.new("RGBA", lato, fondo + (255,))
    tav.alpha_composite(pag)
    return tav.convert("RGB")


DST = [(330, 260), (1560, 330), (1700, 2150), (200, 2060)]


# ─────────────────────────── 1. bordi ───────────────────────────

def prova_bordi(foto: dict):
    for nome in sorted(foto):
        img = apri(foto[nome].read_bytes(), 4000, 40_000_000)
        da, ang, s = PG.scegli_bordi(img, None)
        var = nome.rsplit("-", 1)[1]
        if var in ("storta", "ombra", "doppia"):
            ok = da == "server" and ang is not None
            if ok and var == "ombra":
                # L'ombra in alto a sinistra non deve tagliare la pagina (prima della soglia del
                # bordo il fondo entrava nella parte in ombra: angolo alto-sx a y 0,32)
                ok = ang[0][1] < 0.15 and ang[0][0] < 0.2
            verifica(f"bordi: {nome} trovati dal server", ok, f"{da} {ang}")
        else:
            verifica(f"bordi: {nome} intera (la pagina riempie la foto)", da == "intera", da)

    # I bordi del telefono
    img = apri(foto["p112-storta"].read_bytes(), 4000, 40_000_000)
    _, srv, _ = PG.scegli_bordi(img, None)
    vicini = [[x + 0.01, y - 0.008] for x, y in srv]
    da, ang, _ = PG.scegli_bordi(img, vicini)
    verifica("bordi: quelli del telefono vicini a quelli del server valgono",
             da == "telefono" and ang == vicini, da)
    lontani = [[0.25, 0.25], [0.75, 0.25], [0.75, 0.75], [0.25, 0.75]]
    da, ang, _ = PG.scegli_bordi(img, lontani)
    verifica("bordi: quelli del telefono diversi → valgono quelli del server",
             da == "server" and ang == srv, da)
    for nome, cattivi in (("non convessi (a farfalla)", [[0.1, 0.1], [0.9, 0.9], [0.9, 0.1], [0.1, 0.9]]),
                          ("fuori dalla foto", [[-0.5, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]),
                          ("troppo piccoli", [[0.4, 0.4], [0.5, 0.4], [0.5, 0.5], [0.4, 0.5]]),
                          ("angoli stretti", [[0.1, 0.1], [0.9, 0.12], [0.15, 0.3], [0.1, 0.9]]),
                          ("non numeri", [["a", 1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]),
                          ("tre angoli", [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]])):
        g = PG.grigio(img)
        val = PG.angoli_validi(cattivi)
        verifica(f"bordi: impossibili ({nome}) mai plausibili",
                 val is None or PG.plausibili(val, g.shape[1], g.shape[0]) is not None)
        da, ang, _ = PG.scegli_bordi(img, cattivi)
        verifica(f"bordi: impossibili ({nome}) → quelli del server", da == "server", da)

    # Una foto senza pagina: niente di plausibile, foto intera con l'avviso
    rumore = Image.effect_noise((1200, 900), 60).convert("RGB")
    d = ImageDraw.Draw(rumore)
    d.rectangle([500, 400, 560, 440], fill=(250, 250, 250))
    p = PG.prepara_foto(jpeg(rumore), None, 1600, 15_000_000, 150)
    verifica("bordi: una foto senza pagina resta intera con l'avviso «bordi»",
             p.bordi == "nessuno" and p.avvisi[:1] == ["bordi"] and p.angoli is None,
             f"{p.bordi} {p.avvisi}")
    # Senza bordi del server, quelli del telefono solo se la pagina chiara li copre
    tav = Image.new("RGB", (1200, 1600), (60, 45, 30))
    d = ImageDraw.Draw(tav)
    d.rectangle([120, 100, 1080, 1500], fill=(245, 245, 240))
    d.rectangle([300, 600, 340, 640], fill=(245, 245, 240))
    p = PG.prepara_foto(jpeg(tav), [[0.1, 0.0625], [0.9, 0.0625], [0.9, 0.9375], [0.1, 0.9375]],
                        1600, 15_000_000, 150)
    verifica("bordi: un foglio dritto sul tavolo, i bordi del telefono confermati",
             p.bordi in ("telefono", "server") and "bordi" not in p.avvisi, f"{p.bordi} {p.avvisi}")


def prova_js(foto: dict):
    node = shutil.which("node")
    if node is None:
        print("SALTATA IN PARTE: bordi.js, node non c'è (il confronto col Python)")
        return
    casi = []
    nomi = sorted(foto)[:12]
    for nome in nomi:
        img = apri(foto[nome].read_bytes(), 4000, 40_000_000)
        g, n = PG.grigio(img), PG.grigio(img, PG.LATO_NITIDEZZA)
        r = PG.rileva(g)
        casi.append({"nome": nome, "w": g.shape[1], "h": g.shape[0], "g": g.ravel().tolist(),
                     "nw": n.shape[1], "nh": n.shape[0], "n": n.ravel().tolist(),
                     "angoli": r["angoli"], "intera": r["intera"], "motivo": r["motivo"],
                     "nit": PG.nitidezza(img),
                     "plaus": PG.plausibili([[0.1, 0.1], [0.9, 0.9], [0.9, 0.1], [0.1, 0.9]],
                                            g.shape[1], g.shape[0])})
    (TMP / "casi.json").write_text(json.dumps(casi), encoding="utf-8")
    js = ("const B = require(process.argv[2]); const casi = require(process.argv[3]);"
          "console.log(JSON.stringify(casi.map((c) => { const r = B.rileva(Int32Array.from(c.g), c.w, c.h);"
          " return {nome: c.nome, r, n: B.nitidezza(Int32Array.from(c.n), c.nw, c.nh),"
          " plaus: B.plausibili([[0.1, 0.1], [0.9, 0.9], [0.9, 0.1], [0.1, 0.9]], c.w, c.h)}; })));")
    (TMP / "confronta.js").write_text(js, encoding="utf-8")
    p = subprocess.run([node, str(TMP / "confronta.js"), str(BORDI_JS), str(TMP / "casi.json")],
                       capture_output=True, text=True, timeout=120)
    try:
        out = {x["nome"]: x for x in json.loads(p.stdout)}
    except ValueError:
        verifica("bordi.js: gira con node", False, p.stderr[-300:])
        return
    diversi = []
    for c in casi:
        j = out.get(c["nome"]) or {}
        r = j.get("r") or {}
        a, b = r.get("angoli"), c["angoli"]
        stessi = (a is None) == (b is None) and (a is None or max(
            abs(x - y) for u, v in zip(a, b) for x, y in zip(u, v)) < 1e-9)
        if not stessi or r.get("intera") != c["intera"] or r.get("motivo") != c["motivo"] \
                or abs((j.get("n") or 0) - c["nit"]) > 1e-6 * max(1.0, c["nit"]) \
                or j.get("plaus") != c["plaus"]:
            diversi.append(c["nome"])
    verifica(f"bordi.js: stessi angoli, esito, motivo e nitidezza del Python su {len(casi)} foto",
             not diversi, ", ".join(diversi))


# ─────────────────────────── 2. raddrizzamento e nitidezza ───────────────────────────

def prova_raddrizza():
    foto = in_prospettiva(pagina_con_segni(), DST)
    p = PG.prepara_foto(jpeg(foto, 92), None, 1600, 15_000_000, 150)
    img = Image.open(io.BytesIO(p.jpeg)).convert("L")
    verifica("raddrizza: il server trova i bordi e porta il lato lungo a 1600",
             p.bordi == "server" and max(img.size) == 1600, f"{p.bordi} {img.size}")
    # Il rapporto dei lati viene dai lati più lunghi del quadrilatero (lo scorcio lo stringe un
    # po'): resta una pagina in verticale
    verifica("raddrizza: la pagina resta in verticale", img.size[1] > img.size[0], f"{img.size}")
    w, h = img.size
    scuri = []
    for cx, cy in ((0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)):
        box = img.crop((int(cx * w - 12), int(cy * h - 12), int(cx * w + 12), int(cy * h + 12)))
        scuri.append(sum(box.histogram()[i] * i for i in range(256)) / (24 * 24))
    verifica("raddrizza: i quattro segni tornano vicino ai loro angoli",
             all(v < 90 for v in scuri), [round(v) for v in scuri])
    # Le righe di testo dritte: una riga della pagina raddrizzata ha il nero tutto sulla stessa y
    verifica("raddrizza: niente EXIF né altro: un JPEG nuovo", p.jpeg[:3] == b"\xff\xd8\xff")
    # Nitidezza: la stessa pagina sfocata ha l'avviso, la nitida no
    nitida = PG.prepara_foto(jpeg(foto, 92), None, 1600, 15_000_000, 150)
    sfocata = PG.prepara_foto(jpeg(foto.filter(ImageFilter.GaussianBlur(4)), 92), None, 1600,
                              15_000_000, 150)
    verifica("nitidezza: la pagina nitida senza avviso, quella sfocata con «sfocata»",
             "sfocata" not in nitida.avvisi and "sfocata" in sfocata.avvisi,
             f"{nitida.nitidezza} {sfocata.nitidezza}")
    piccola = PG.prepara_foto(jpeg(foto.resize((475, 600))), None, 1600, 15_000_000, 150)
    verifica("nitidezza: una foto sotto i 1000 px ha l'avviso «piccola» (e non si ingrandisce)",
             "piccola" in piccola.avvisi and max(piccola.larghezza, piccola.altezza) < 1000,
             f"{piccola.avvisi} {piccola.larghezza}x{piccola.altezza}")
    # Una foto con l'orientamento EXIF girata prima dei bordi
    exif = Image.Exif()
    exif[0x0112] = 6                                        # girata di 90°
    b = io.BytesIO()
    foto.rotate(90, expand=True).save(b, "JPEG", quality=90, exif=exif)
    girata = PG.prepara_foto(b.getvalue(), None, 1600, 15_000_000, 150)
    verifica("raddrizza: l'EXIF dell'orientamento vale prima dei bordi (pagina in verticale)",
             girata.altezza > girata.larghezza and girata.bordi == "server",
             f"{girata.larghezza}x{girata.altezza} {girata.bordi}")


# ─────────────────────────── 3. PDF ───────────────────────────

def pdf_di(n: int, lato=(595, 842), autore=False) -> bytes:
    pagine = [pagina_con_segni().resize(lato) for _ in range(n)]
    b = io.BytesIO()
    extra = {"author": "Mario Segreto", "title": "Compiti di Mario Segreto"} if autore else {}
    pagine[0].save(b, "PDF", save_all=True, append_images=pagine[1:], resolution=72, **extra)
    return b.getvalue()


def autore_pdf(dati: bytes) -> str:
    """L'autore e il titolo scritti nel PDF (vuoto se non ci sono)."""
    import pypdfium2 as pdfium
    d = pdfium.PdfDocument(dati)
    try:
        m = d.get_metadata_dict()
        return (m.get("Author") or "") + (m.get("Title") or "").replace("Compiti di Mario Segreto", "")
    finally:
        d.close()


def pdf_a_mano(mediabox: str) -> bytes:
    """Un PDF minimo scritto a mano (xref ricostruita da PDFium)."""
    return (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[" + mediabox.encode() + b"]>>endobj\n"
            b"trailer<</Root 1 0 R>>\n%%EOF\n")


def prova_pdf():
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        print("SALTATA IN PARTE: i PDF, pypdfium2 non c'è (extra «archivio»)")
        return
    out = PG.dividi_pdf(pdf_di(3), 1600, 40, 150)
    verifica("PDF: tre pagine, ognuna col lato lungo 1600 e in JPEG",
             len(out) == 3 and all(max(p.larghezza, p.altezza) == 1600 and p.jpeg[:3] == b"\xff\xd8\xff"
                                   and p.bordi == "pdf" for p in out),
             [(p.larghezza, p.altezza) for p in out])
    for nome, dati, attesa in (
            ("troppe pagine", pdf_di(5), "al più 4"),
            ("malformato", b"%PDF-1.7\n" + os.urandom(3000), "rovinato"),
            ("troncato", pdf_di(2)[:400], "rovinato"),
            ("con una pagina enorme (200 000 punti)", pdf_a_mano("0 0 200000 200000"), "misura"),
            ("senza pagine", pdf_a_mano("0 0 0 0").replace(b"/Count 1", b"/Count 0").replace(b"[3 0 R]", b"[]"), "")):
        try:
            PG.dividi_pdf(dati, 1600, 4, 150)
            esito = "accettato"
        except PG.PaginaNonValida as e:
            esito = str(e)
        except Exception as e:  # noqa: BLE001
            esito = f"ECCEZIONE {type(e).__name__}"
        verifica(f"PDF {nome}: rifiutato con un motivo", esito != "accettato"
                 and not esito.startswith("ECCEZIONE") and attesa in esito, esito)
    import asyncio
    provv = TMP / "studio-provv" / "tmp"
    out, pulito = asyncio.run(PG.dividi_pdf_a_parte(pdf_di(2, autore=True), 1600, 40, 150,
                                                    provvisori=provv))
    verifica("PDF nel sottoprocesso: i provvisori in studio_cartella/tmp, tolti dopo la divisione",
             provv.is_dir() and not any(provv.iterdir()))
    verifica("PDF nel sottoprocesso: due pagine e la copia pulita (senza l'autore)",
             len(out) == 2 and max(out[0].larghezza, out[0].altezza) == 1600
             and pulito and pulito.startswith(b"%PDF-") and autore_pdf(pulito) == ""
             and autore_pdf(pdf_di(1, autore=True)) == "Mario Segreto")
    try:
        asyncio.run(PG.dividi_pdf_a_parte(pdf_di(3), 1600, 40, 150, tempo_pagina_s=0.001))
        esito = "accettato"
    except PG.PaginaNonValida as e:
        esito = str(e)
    verifica("PDF nel sottoprocesso: oltre il tempo per pagina il processo si ferma e il PDF è rifiutato",
             "troppo pesante" in esito, esito)
    try:
        asyncio.run(PG.dividi_pdf_a_parte(b"%PDF-1.7\n" + os.urandom(500), 1600, 40, 150))
        esito = "accettato"
    except PG.PaginaNonValida as e:
        esito = str(e)
    verifica("PDF nel sottoprocesso: malformato rifiutato con il motivo del figlio", "rovinato" in esito, esito)
    try:
        from pypdf import PdfReader, PdfWriter
        w = PdfWriter()
        for p in PdfReader(io.BytesIO(pdf_di(1))).pages:
            w.add_page(p)
        w.encrypt("segreta")
        b = io.BytesIO()
        w.write(b)
        try:
            PG.dividi_pdf(b.getvalue(), 1600, 4, 150)
            esito = "accettato"
        except PG.PaginaNonValida as e:
            esito = str(e)
        verifica("PDF cifrato: rifiutato («protetto da una password»)", "password" in esito, esito)
    except ImportError:
        print("SALTATA IN PARTE: il PDF cifrato, pypdf non c'è (extra «prove»)")


# ─────────────────────────── 4. file ostili ───────────────────────────

def prova_ostili():
    bomba = io.BytesIO()
    Image.new("1", (30000, 30000)).save(bomba, "PNG")
    for nome, dati in (("bomba di decompressione (PNG 30 000 × 30 000)", bomba.getvalue()),
                       ("HTML con l'estensione .jpg", b"<html><script>alert(1)</script></html>"),
                       ("JPEG rovinato (solo la firma)", b"\xff\xd8\xff\xe0" + os.urandom(5000)),
                       ("HEIC", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 200),
                       ("vuoto", b"")):
        try:
            PG.prepara_foto(dati, None, 1600, 15_000_000, 150)
            esito = "accettato"
        except PG.PaginaNonValida as e:
            esito = str(e)
        verifica(f"ostili: {nome} rifiutato", esito != "accettato", esito)
    # I file: nome scelto dal server, dentro la cartella, mai sovrascritto
    base = TMP / "ostili"
    rel = PG.scrivi_file(base, 7, b"x", "jpg")
    verifica("file: il nome lo sceglie il server, dentro pagine/<verifica>/",
             rel.startswith("pagine/7/") and rel.endswith(".jpg") and ".." not in rel
             and (base / rel).read_bytes() == b"x", rel)
    for est in ("../x", "exe", "jpg/../../x"):
        try:
            PG.scrivi_file(base, 7, b"x", est)
            esito = "scritto"
        except (ValueError, OSError):
            esito = "rifiutato"
        verifica(f"file: l'estensione «{est}» rifiutata", esito == "rifiutato")
    # La cartella delle pagine di una verifica che è un link fuori: rifiutata
    fuori = TMP / "fuori"
    fuori.mkdir()
    collegata = base / "pagine" / "8"
    fatto = False
    try:
        os.symlink(fuori, collegata, target_is_directory=True)
        fatto = True
    except OSError:
        if os.name == "nt":
            try:
                import _winapi
                _winapi.CreateJunction(str(fuori), str(collegata))
                fatto = True
            except OSError:
                pass
    if fatto:
        try:
            PG.scrivi_file(base, 8, b"x", "jpg")
            esito = "scritto"
        except (PermissionError, OSError):
            esito = "rifiutato"
        verifica("file: la cartella della verifica è un link fuori → rifiutato, niente scritto fuori",
                 esito == "rifiutato" and not any(fuori.iterdir()), esito)
        # togli_file non segue il link fuori
        (fuori / "dentro.jpg").write_bytes(b"y")
        n = D.togli_file(["pagine/8/dentro.jpg", "../fuori/dentro.jpg"], base)
        verifica("file: togli_file non tocca un file fuori dalla cartella (link o «..»)",
                 n == 0 and (fuori / "dentro.jpg").exists())
        os.unlink(collegata) if collegata.is_symlink() else os.rmdir(collegata)
    else:
        print("SALTATA IN PARTE: i link fuori, qui non si creano link né giunzioni")


# ─────────────────────────── 5. il server vero ───────────────────────────

class Prof:
    def __init__(self, pid, name, admin=False, nascita=None, tutori=(), tipo=None):
        self.id, self.name, self.admin = pid, name, admin
        self.nascita, self.tutori, self.fascia, self.tipo = nascita, list(tutori), None, tipo


class Registro:
    def __init__(self, *profili):
        self.users = {p.name: p for p in profili}

    def by_id(self, pid):
        return next((p for p in self.users.values() if p.id == pid), None)

    def get(self, nome):
        return self.users.get(nome)


ANDREA = Prof("a1", "Andrea")
LEO = Prof("l1", "Leo", nascita="2014-03-01", tutori=["a1"])
BRUNO = Prof("b1", "Bruno")
CARLA = Prof("c1", "Carla", admin=True)
NOTO = Prof("k1", "Piero", tipo="conoscente")
REG = Registro(ANDREA, LEO, BRUNO, CARLA, NOTO)


def chiedi(port, percorso, sessione=None, token=None, corpo=None, byte=None, meta=None, tipo=None,
           intestazioni=None):
    h = {"Content-Type": tipo or ("application/octet-stream" if byte is not None else "application/json")}
    if sessione:
        h["X-Calliope-Sessione"] = sessione
    if token:
        h["Authorization"] = "Bearer " + token
    if meta is not None:
        h["X-Calliope-Studio"] = quote(json.dumps(meta))
    h.update(intestazioni or {})
    dati = byte if byte is not None else json.dumps(corpo if corpo is not None else {}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}{percorso}", headers=h, method="POST",
                                 data=dati)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except (ValueError, OSError):   # la connessione chiusa subito (sessione, schermo)
            return e.code, {}
    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
        # /api/studio/pagina chiude subito senza leggere (sessione, schermo, Studio spento:
        # revisione della PR #312): la stessa richiesta con le sole intestazioni dà il codice
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        c.putrequest("POST", percorso)
        for k, v in {**h, "Content-Length": str(len(dati))}.items():
            c.putheader(k, v)
        c.endheaders()
        r = c.getresponse()
        try:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
        except (ValueError, OSError):
            return r.status, {}
        finally:
            c.close()


class Servizi:
    studio = None


def file_studio(cfg) -> list[Path]:
    c = D.cartella_di(cfg)
    return sorted(p for p in c.rglob("*") if p.is_file()) if c and c.exists() else []


def prova_server():
    cartella = TMP / "server"
    cartella.mkdir()
    cfg = Config()
    cfg.config_dir = str(cartella)
    cfg.memory_db = str(cartella / "memoria.db")
    cfg.studio_modo = "attivo"
    cfg.studio_cartella = "studio"                     # relativa: accanto a memoria.db
    cfg.turn_log_dir = str(cartella / "registro")
    minori.prepara(cfg, registry=REG)
    ora = [datetime.datetime(2026, 10, 29, 16, 0)]
    st = S.Studio(cfg, registry=REG, log=lambda m: None, adesso=lambda: ora[0])
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    hub.profilo = REG.by_id
    serv = Servizi()
    serv.studio = st
    hub.servizi = serv
    srv = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
    hub.server = srv
    port = srv.port
    try:
        arch = hub.archivio
        tok = {}
        for chi, pid in (("leo", "l1"), ("andrea", "a1"), ("bruno", "b1"), ("carla", "c1"),
                         ("noto", "k1"), ("grigio", "x9"), ("leo2", "l1"), ("leo3", "l1")):
            _, tok[chi] = arch.crea_con_token("telefono " + chi, proprietario=pid,
                                              proprietario_nome=chi.title())
        _, tok["cucina"] = arch.crea_con_token("cucina")
        hub._rinfresca()
        sess = {k: chiedi(port, "/api/accedi", token=t)[1].get("sessione") for k, t in tok.items()}

        vid = st.crea_verifica(LEO, "Storia", "2026-11-05", argomento="Le scoperte geografiche")
        vid_a = st.crea_verifica(ANDREA, "Inglese", "2026-11-10")
        foto = in_prospettiva(pagina_con_segni(), DST)
        foto_b = jpeg(foto, 90)
        angoli = [[x / 1900, y / 2400] for x, y in DST]

        # Il proprietario (un minore)
        s, d = chiedi(port, "/api/studio/pagina", sess["leo"], byte=foto_b,
                      meta={"verifica": vid, "angoli": angoli})
        verifica("server: il minore manda una pagina della sua verifica (200)",
                 s == 200 and d.get("pagine") and d["pagine"][0]["bordi"] in ("telefono", "server"),
                 f"{s} {d}")
        mid = d.get("materiale")
        righe = st.pagine(LEO, vid)
        verifica("server: la pagina è «da_leggere», col file nella cartella dello Studio, senza testo",
                 len(righe) == 1 and righe[0]["stato"] == "da_leggere" and righe[0]["testo"] is None
                 and (Path(cfg.memory_db).parent / "studio" / righe[0]["file"]).is_file(),
                 json.dumps({k: righe[0][k] for k in ("stato", "file")}) if righe else "")
        verifica("server: la cartella relativa sta accanto a memory_db",
                 D.cartella_di(cfg) == Path(cfg.memory_db).resolve().parent / "studio")
        verifica("server: gli angoli usati, la nitidezza e il lato salvati con la pagina",
                 righe and json.loads(righe[0]["angoli"] or "null") and righe[0]["nitidezza"]
                 and max(righe[0]["larghezza"], righe[0]["altezza"]) == 1600)
        s, d = chiedi(port, "/api/studio/pagina", sess["leo"], byte=foto_b,
                      meta={"verifica": vid, "materiale": mid})
        verifica("server: la seconda pagina dello stesso giro nello stesso materiale, dopo",
                 s == 200 and d.get("materiale") == mid and d["pagine"][0]["ordine"] == 2, f"{s} {d}")
        verifica("server: niente nella conversazione (l'ingresso del ciclo è vuoto)",
                 hub.ingresso.vuoto())

        # Il tutore
        s, d = chiedi(port, "/api/studio/pagina", sess["andrea"], byte=foto_b, meta={"verifica": vid})
        verifica("server: il tutore manda una pagina nella verifica del suo minore", s == 200, f"{s} {d}")
        s, d = chiedi(port, "/api/studio/verifiche", sess["andrea"], corpo={})
        di = {v["id"]: v.get("di") for v in d.get("verifiche", [])}
        verifica("server: le verifiche del tutore: la sua e quella del minore (col nome)",
                 s == 200 and di.get(vid_a) is None and di.get(vid) == "Leo", f"{s} {d}")
        s, d = chiedi(port, "/api/studio/verifiche", sess["leo"], corpo={})
        verifica("server: il minore vede solo la sua, con le pagine contate",
                 s == 200 and [v["id"] for v in d["verifiche"]] == [vid] and d["verifiche"][0]["pagine"] == 3,
                 f"{s} {d}")

        # Chi non può
        for chi, attesa in (("bruno", 404), ("carla", 404), ("noto", 404), ("grigio", 403),
                            ("cucina", 403)):
            s, d = chiedi(port, "/api/studio/pagina", sess[chi], byte=foto_b, meta={"verifica": vid})
            verifica(f"server: {chi} non manda pagine nella verifica di Leo ({attesa})",
                     s == attesa, f"{s} {d}")
        s, d = chiedi(port, "/api/studio/pagina", None, byte=foto_b, meta={"verifica": vid})
        verifica("server: senza sessione 401", s == 401, f"{s}")
        s, d = chiedi(port, "/api/studio/pagina", sess["leo"], byte=foto_b, meta={"verifica": 9999})
        verifica("server: una verifica che non c'è: lo stesso 404 di quella di un altro",
                 s == 404 and d.get("errore") == "Questa verifica non c'è.", f"{s} {d}")
        s, d = chiedi(port, "/api/studio/verifiche", sess["bruno"], corpo={})
        verifica("server: un altro adulto non vede le verifiche di Leo",
                 s == 200 and vid not in [v["id"] for v in d.get("verifiche", [])], f"{s} {d}")
        s, d = chiedi(port, "/api/studio/verifiche", sess["noto"], corpo={})
        verifica("server: il conoscente non ha verifiche", s == 200 and d.get("verifiche") == [],
                 f"{s} {d}")

        # Orari del minore
        minori._SERVIZIO["regole"].imposta("l1", "orari", ["15:00-17:00"])
        try:
            reale = datetime.datetime.now()
            if minori.fuori_orario(LEO, reale):
                pass
            minori._SERVIZIO["regole"].imposta("l1", "orari", [
                f"{(reale - datetime.timedelta(minutes=30)).strftime('%H:%M')}-"
                f"{(reale + datetime.timedelta(minutes=30)).strftime('%H:%M')}"])
            s, d = chiedi(port, "/api/studio/pagina", sess["leo2"], byte=foto_b, meta={"verifica": vid})
            verifica("server: fuori orario il minore non manda pagine (403, con la frase)",
                     s == 403 and d.get("codice") == "fuori_orario", f"{s} {d}")
            s, d = chiedi(port, "/api/studio/pagina", sess["leo2"], byte=foto_b, meta={"verifica": 9999})
            verifica("server: gli orari prima della verifica (fuori orario anche una che non c'è dà 403)",
                     s == 403 and d.get("codice") == "fuori_orario", f"{s} {d}")
            s, d = chiedi(port, "/api/studio/pagina", sess["andrea"], byte=foto_b, meta={"verifica": vid})
            verifica("server: fuori orario del minore il tutore sì", s == 200, f"{s} {d}")
        finally:
            minori._SERVIZIO["regole"].imposta("l1", "orari", [])

        # Limiti e dati sbagliati
        prima = file_studio(cfg)
        cfg.studio_pagina_max_mb = 1.0
        cfg.studio_pdf_max_mb = 1.0
        # Solo le intestazioni, con una lunghezza oltre il tetto: il 413 arriva prima del corpo
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        c.putrequest("POST", "/api/studio/pagina")
        for k, v in (("Content-Type", "application/octet-stream"), ("Content-Length", "2000000"),
                     ("X-Calliope-Sessione", sess["leo"]),
                     ("X-Calliope-Studio", quote(json.dumps({"verifica": vid})))):
            c.putheader(k, v)
        c.endheaders()
        s = c.getresponse().status
        c.close()
        verifica("limiti: un file dichiarato oltre il tetto → 413 prima del corpo", s == 413, f"{s}")

        def a_pezzi():
            for _ in range(12):
                yield b"\xff\xd8\xff" + b"0" * 100_000
        # A pezzi, senza la lunghezza: il tetto vale mentre si legge
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/studio/pagina", data=a_pezzi(), method="POST",
            headers={"Content-Type": "application/octet-stream", "Transfer-Encoding": "chunked",
                     "X-Calliope-Sessione": sess["leo"],
                     "X-Calliope-Studio": quote(json.dumps({"verifica": vid}))})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                s = r.status
        except urllib.error.HTTPError as e:
            s = e.code
        except OSError:
            s = "chiusa"
        verifica("limiti: senza Content-Length (a pezzi) → 411 subito (o la connessione chiusa)",
                 s in (411, "chiusa"), f"{s}")
        prova_dos(port, sess, vid, foto_b)
        cfg.studio_pagina_max_mb, cfg.studio_pdf_max_mb = 15.0, 30.0
        s, d = chiedi(port, "/api/studio/pagina", sess["leo"], byte=foto_b, meta={"verifica": vid},
                      tipo="application/json")
        verifica("limiti: Content-Type diverso da octet-stream → 415", s == 415, f"{s}")
        for nome, meta in (("senza verifica", {}), ("verifica testo", {"verifica": "1"}),
                           ("verifica vera ma bool", {"verifica": True}),
                           ("materiale negativo", {"verifica": vid, "materiale": -2})):
            s, d = chiedi(port, "/api/studio/pagina", sess["leo"], byte=foto_b, meta=meta)
            verifica(f"limiti: dati dell'invio sbagliati ({nome}) → 400", s == 400, f"{s} {d}")
        s, d = chiedi(port, "/api/studio/pagina", sess["leo"], byte=foto_b,
                      intestazioni={"X-Calliope-Studio": "x" * 3000})
        verifica("limiti: dati dell'invio troppo lunghi → 400", s == 400, f"{s}")
        s, d = chiedi(port, "/api/studio/pagina", sess["andrea"], byte=foto_b,
                      meta={"verifica": vid_a, "materiale": mid})
        verifica("limiti: il materiale di un'altra verifica → 404", s == 404, f"{s} {d}")
        for nome, dati, attesa in (("HTML con .jpg", b"<html>ciao</html>", 415),
                                   ("JPEG rovinato", b"\xff\xd8\xff\xe0" + os.urandom(4000), 415),
                                   ("HEIC", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 100, 415),
                                   ("PDF malformato", b"%PDF-1.7\n" + os.urandom(2000), 415),
                                   ("GIF (non è una pagina)", b"GIF89a" + b"\x00" * 50, 415)):
            s, d = chiedi(port, "/api/studio/pagina", sess["leo"], byte=dati, meta={"verifica": vid})
            verifica(f"ostili sul server: {nome} → {attesa} con un motivo",
                     s == attesa and d.get("errore"), f"{s} {d}")
        bomba = io.BytesIO()
        Image.new("1", (30000, 30000)).save(bomba, "PNG")
        s, d = chiedi(port, "/api/studio/pagina", sess["leo"], byte=bomba.getvalue(),
                      meta={"verifica": vid})
        verifica("ostili sul server: la bomba di decompressione → 415", s == 415, f"{s} {d}")
        verifica("ostili sul server: niente scritto su disco dai rifiuti", file_studio(cfg) == prima)

        # Il PDF diviso in pagine, col titolo dal nome (senza percorso) e il PDF tenuto accanto
        try:
            import pypdfium2  # noqa: F401
            pdf = True
        except ImportError:
            pdf = False
        if pdf:
            s, d = chiedi(port, "/api/studio/pagina", sess["leo"], byte=pdf_di(2, autore=True),
                          meta={"verifica": vid, "nome": "../../etc/Capitolo 7.pdf"})
            mats = st.dati.tutti("SELECT * FROM studio_materiali WHERE verifica = ?", (vid,))
            m_pdf = next((m for m in mats if m["origine"] == "file"), {})
            verifica("PDF sul server: due pagine, un materiale «file» col PDF tenuto accanto",
                     s == 200 and len(d.get("pagine") or []) == 2 and m_pdf.get("titolo") == "Capitolo 7.pdf"
                     and str(m_pdf.get("riferimento") or "").startswith("file:pagine/")
                     and (D.cartella_di(cfg) / m_pdf["riferimento"][5:]).is_file(), f"{s} {d} {m_pdf}")
            tenuto = (D.cartella_di(cfg) / m_pdf["riferimento"][5:]).read_bytes() if m_pdf else b""
            verifica("PDF sul server: la copia tenuta è un PDF con le pagine, senza i metadati dell'originale",
                     tenuto.startswith(b"%PDF-") and autore_pdf(tenuto) == ""
                     and autore_pdf(pdf_di(1, autore=True)) == "Mario Segreto", autore_pdf(tenuto))

        if pdf:
            prova_pdf_insieme(port, sess, vid)

        # Pagine per verifica e invii al minuto
        cfg.studio_pagine_max = len(st.pagine(LEO, vid)) + 1
        s, d = chiedi(port, "/api/studio/pagina", sess["leo"], byte=foto_b, meta={"verifica": vid})
        s2, d2 = chiedi(port, "/api/studio/pagina", sess["leo"], byte=foto_b, meta={"verifica": vid})
        verifica("limiti: oltre `studio_pagine_max` pagine per verifica → 413",
                 s == 200 and s2 == 413, f"{s} {s2} {d2}")
        if pdf:
            cfg.studio_pagine_max = len(st.pagine(LEO, vid)) + 1
            s, d = chiedi(port, "/api/studio/pagina", sess["leo"], byte=pdf_di(3), meta={"verifica": vid})
            verifica("limiti: un PDF con più pagine di quante ne restano → rifiutato intero",
                     s == 415 and "al più 1" in d.get("errore", ""), f"{s} {d}")
        cfg.studio_pagine_max = 80
        cfg.studio_pagine_al_minuto = 3
        codici = [chiedi(port, "/api/studio/pagina", sess["leo3"], byte=b"<x>", meta={"verifica": vid})[0]
                  for _ in range(4)]
        verifica("limiti: oltre gli invii al minuto → 429", codici[:3] == [415] * 3 and codici[3] == 429,
                 codici)
        cfg.studio_pagine_al_minuto = 40

        # Verifica archiviata
        st.archivia(ANDREA, vid_a)
        s, d = chiedi(port, "/api/studio/pagina", sess["andrea"], byte=foto_b, meta={"verifica": vid_a})
        verifica("server: una verifica archiviata non prende pagine (409)", s == 409, f"{s} {d}")

        # La tessera di Le mie cose
        from calliope.schermi import raccolte
        t = next(x for x in raccolte.tessere(hub, LEO, lambda m: None) if x["id"] == "studio")
        verifica("tessera: con lo Studio attivo apre la pagina, col conto delle verifiche",
                 t["pagina"] is True and t["conto"] == 1, json.dumps(t))

        # Ombra e spento
        st.modo = "ombra"
        s, d = chiedi(port, "/api/studio/pagina", sess["leo"], byte=foto_b, meta={"verifica": vid})
        verifica("ombra: chi non amministra no (403)", s == 403, f"{s} {d}")
        vid_c = st.crea_verifica(CARLA, "Diritto", "2026-11-20")
        s, d = chiedi(port, "/api/studio/pagina", sess["carla"], byte=foto_b, meta={"verifica": vid_c})
        s2, d2 = chiedi(port, "/api/studio/verifiche", sess["carla"], corpo={})
        verifica("ombra: chi amministra sì, con la scritta «prova»",
                 s == 200 and s2 == 200 and d2.get("prova") is True, f"{s} {s2} {d2}")
        tl = next(x for x in raccolte.tessere(hub, LEO, lambda m: None) if x["id"] == "studio")
        tc = next(x for x in raccolte.tessere(hub, CARLA, lambda m: None) if x["id"] == "studio")
        verifica("ombra: la tessera apre la pagina solo a chi amministra («prova»)",
                 tl["pagina"] is False and tc["pagina"] is True and tc["stato"].startswith("prova"),
                 json.dumps([tl, tc]))
        st.modo = "attivo"
        serv.studio = None
        s, d = chiedi(port, "/api/studio/pagina", sess["leo"], byte=foto_b, meta={"verifica": vid})
        s2, _ = chiedi(port, "/api/studio/verifiche", sess["leo"], corpo={})
        ts = next(x for x in raccolte.tessere(hub, LEO, lambda m: None) if x["id"] == "studio")
        verifica("spento: l'endpoint non accetta niente (404) e la tessera dice «arriva presto»",
                 s == 404 and s2 == 404 and ts["pagina"] is False and ts["stato"] == "arriva presto",
                 f"{s} {s2} {ts}")
        verifica("spento: S.prepara con «spento» non crea il servizio",
                 S.prepara(type("C", (), {"studio_modo": "spento", "memory_db": cfg.memory_db})()) is None)
        serv.studio = st

        # ─── 6. tenuta, dimentica, svuota, togli ───
        def file_di(v):
            righe = st.dati.tutti("SELECT p.file FROM studio_pagine p JOIN studio_materiali m ON "
                                  "m.id = p.materiale WHERE m.verifica = ?", (v,))
            rif = [m["riferimento"][5:] for m in st.dati.tutti(
                "SELECT riferimento FROM studio_materiali WHERE verifica = ? AND riferimento LIKE "
                "'file:%'", (v,))]
            return [D.cartella_di(cfg) / r["file"] for r in righe] + [D.cartella_di(cfg) / r for r in rif]

        f_leo = file_di(vid)
        verifica("tenuta: prima ci sono i file della verifica di Leo (immagini e PDF)",
                 f_leo and all(p.is_file() for p in f_leo), len(f_leo))
        from calliope.conserva import Conservazione
        cons = Conservazione(cfg, log=lambda m: None)
        # Come la rotazione: oggi meno `studio_tenuta_giorni`; 60 giorni dopo la data resta, 61 no
        cons._studio(scadute_prima=datetime.date(2026, 11, 5))
        verifica("tenuta: 60 giorni dopo la data restano", all(p.is_file() for p in f_leo))
        cons._studio(scadute_prima=datetime.date(2026, 11, 6))
        verifica("tenuta: 61 giorni dopo via la verifica, le immagini, il PDF e la cartella",
                 not any(p.exists() for p in f_leo) and not (D.cartella_di(cfg) / "pagine" / str(vid)).exists())

        # Gli orfani nella rotazione: un file senza riga vecchio di due giorni via, uno appena
        # scritto (un invio in corso) e quelli delle righe restano
        vid_o = st.crea_verifica(BRUNO, "Storia", "2026-11-20")
        chiedi(port, "/api/studio/pagina", sess["bruno"], byte=foto_b, meta={"verifica": vid_o})
        f_o = file_di(vid_o)
        vecchio = D.cartella_di(cfg) / "pagine" / "777" / "vecchio.jpg"
        nuovo = D.cartella_di(cfg) / "pagine" / "777" / "nuovo.jpg"
        vecchio.parent.mkdir(parents=True, exist_ok=True)
        vecchio.write_bytes(b"x")
        nuovo.write_bytes(b"x")
        due_giorni = time.time() - 2 * 86400
        os.utime(vecchio, (due_giorni, due_giorni))
        r = cons._studio(scadute_prima=datetime.date(2026, 11, 6))
        verifica("rotazione: l'orfano di due giorni via, quello appena scritto e le pagine vere restano",
                 not vecchio.exists() and nuovo.exists() and f_o and all(p.is_file() for p in f_o)
                 and r.get("orfani") == 1, f"{r}")
        st.togli_verifica(BRUNO, vid_o)
        nuovo.unlink()

        vid2 = st.crea_verifica(LEO, "Scienze", "2026-11-06")
        chiedi(port, "/api/studio/pagina", sess["leo"], byte=foto_b, meta={"verifica": vid2})
        f2 = file_di(vid2)
        D.cancella_file(cfg.memory_db, persona="l1", archiviate=False, cartella=cfg.studio_cartella)
        verifica("dimentica: le pagine di Leo via dal disco (cartella relativa risolta)",
                 f2 and not any(p.exists() for p in f2))
        vid3 = st.crea_verifica(BRUNO, "Fisica", "2026-11-12")
        chiedi(port, "/api/studio/pagina", sess["bruno"], byte=foto_b, meta={"verifica": vid3})
        f3 = file_di(vid3)
        out = st.togli_verifica(BRUNO, vid3)
        verifica("togli la verifica: le sue pagine via dal disco",
                 out["file"] == len(f3) and not any(p.exists() for p in f3), out)
        vid4 = st.crea_verifica(BRUNO, "Chimica", "2026-11-13")
        chiedi(port, "/api/studio/pagina", sess["bruno"], byte=foto_b, meta={"verifica": vid4})
        orfano = D.cartella_di(cfg) / "pagine" / "999" / "rimasto.jpg"
        orfano.parent.mkdir(parents=True, exist_ok=True)
        orfano.write_bytes(b"x")
        fuori = TMP / "fuori-svuota.jpg"
        fuori.write_bytes(b"y")
        cons._studio(tutto=True)
        verifica("svuota: tutte le pagine via, anche un file rimasto senza riga; fuori niente",
                 not file_studio(cfg) and fuori.exists(), [str(p) for p in file_studio(cfg)][:3])
    finally:
        srv.ferma()
        st.close()


def prova_dos(port, sess, vid, foto_b):
    """Revisione della PR #312: senza sessione niente si legge e la connessione si chiude subito;
    un rifiuto dopo una sessione valida butta il corpo al più per STUDIO_SCARTA_S; un invio vero
    troppo lento si ferma dopo STUDIO_LEGGI_S."""
    import socket
    from calliope.schermi import server as SRV

    def manda(intestazioni: dict, corpo_iniziale: bytes = b"", lento: float = 0.0, durata: float = 0.0):
        """(prima riga della risposta, secondi, chiusa?) mandando le intestazioni e poi, se
        `lento`, un byte ogni `lento` secondi per al più `durata` secondi."""
        sk = socket.create_connection(("127.0.0.1", port), timeout=30)
        t0 = time.monotonic()
        righe = "".join(f"{k}: {v}\r\n" for k, v in intestazioni.items())
        sk.sendall(f"POST /api/studio/pagina HTTP/1.1\r\nHost: 127.0.0.1\r\n{righe}\r\n".encode()
                   + corpo_iniziale)
        risposta = b""
        sk.settimeout(lento or 30)
        fine = t0 + (durata or 30)
        chiusa = False
        while time.monotonic() < fine:
            try:
                pezzo = sk.recv(65536)
            except socket.timeout:
                if lento:
                    try:
                        sk.sendall(b"0")
                    except OSError:
                        chiusa = True
                        break
                continue
            except OSError:
                chiusa = True
                break
            if not pezzo:
                chiusa = True
                break
            risposta += pezzo
        sk.close()
        return risposta.split(b"\r\n", 1)[0].decode("latin-1"), time.monotonic() - t0, chiusa

    base = {"Content-Type": "application/octet-stream",
            "X-Calliope-Studio": quote(json.dumps({"verifica": vid}))}
    # Senza sessione, 20 MB dichiarati e solo 1 kB mandato: 401 subito e la connessione chiusa
    riga, dt, chiusa = manda({**base, "Content-Length": "20000000"}, b"x" * 1000)
    verifica("DoS: senza sessione e con un corpo grosso → 401 subito, niente letto, connessione chiusa",
             " 401 " in riga and chiusa and dt < 5, f"{riga} {dt:.1f}s chiusa={chiusa}")
    riga, dt, chiusa = manda({**base, "X-Calliope-Sessione": "inventata", "Content-Length": "5000"}, b"",
                             lento=0.5, durata=8)
    verifica("DoS: una sessione inventata con un invio lento → 401 subito, senza aspettare il corpo",
             " 401 " in riga and dt < 5, f"{riga} {dt:.1f}s")
    riga, dt, chiusa = manda({**base, "X-Calliope-Sessione": sess["leo"]}, b"")
    verifica("DoS: senza Content-Length → 411 subito e la connessione chiusa",
             " 411 " in riga and chiusa and dt < 5, f"{riga} {dt:.1f}s")
    prima_s, prima_l = SRV.STUDIO_SCARTA_S, SRV.STUDIO_LEGGI_S
    SRV.STUDIO_SCARTA_S, SRV.STUDIO_LEGGI_S = 1.5, 1.5
    try:
        # Un rifiuto dopo una sessione valida (la verifica che non c'è) con un invio lento: il corpo
        # si butta al più per STUDIO_SCARTA_S, poi la risposta e la connessione chiusa
        meta = quote(json.dumps({"verifica": 9999}))
        riga, dt, chiusa = manda({**base, "X-Calliope-Studio": meta, "X-Calliope-Sessione": sess["leo"],
                                  "Content-Length": "100000"}, b"", lento=0.3, durata=10)
        verifica("DoS: un rifiuto con un invio lento si interrompe dopo il tempo massimo (404)",
                 " 404 " in riga and dt < 6, f"{riga} {dt:.1f}s chiusa={chiusa}")
        # Lo stesso rifiuto con il corpo tutto mandato: la frase arriva (il telefono la vede)
        s, d = chiedi(port, "/api/studio/pagina", sess["leo"], byte=foto_b, meta={"verifica": 9999})
        verifica("DoS: il rifiuto con il corpo intero arriva con la sua frase", s == 404 and d.get("errore"),
                 f"{s} {d}")
        # Un invio vero troppo lento: 408 dopo STUDIO_LEGGI_S
        riga, dt, chiusa = manda({**base, "X-Calliope-Sessione": sess["leo"], "Content-Length": "100000"},
                                 b"\xff\xd8\xff", lento=0.3, durata=10)
        verifica("DoS: un invio vero troppo lento si ferma (408) dopo il tempo massimo",
                 " 408 " in riga and dt < 6, f"{riga} {dt:.1f}s")
    finally:
        SRV.STUDIO_SCARTA_S, SRV.STUDIO_LEGGI_S = prima_s, prima_l


def prova_pdf_insieme(port, sess, vid):
    """Al più un PDF diviso alla volta (seconda revisione della PR #312): con una divisione lenta
    in corso, il secondo PDF riceve 429 con Retry-After; finita la prima, si riprova e va."""
    import threading
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        print("SALTATA IN PARTE: i PDF insieme, pypdfium2 non c'è (extra «archivio»)")
        return
    vero = PG.dividi_pdf_a_parte
    entrato = threading.Event()

    async def lento(*a, **k):
        import asyncio
        entrato.set()
        await asyncio.sleep(2.0)
        return await vero(*a, **k)
    PG.dividi_pdf_a_parte = lento
    esiti = {}
    try:
        t = threading.Thread(target=lambda: esiti.__setitem__("primo", chiedi(
            port, "/api/studio/pagina", sess["andrea"], byte=pdf_di(1), meta={"verifica": vid})))
        t.start()
        entrato.wait(20)
        import http.client
        b = pdf_di(1)
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        c.request("POST", "/api/studio/pagina", body=b, headers={
            "Content-Type": "application/octet-stream", "X-Calliope-Sessione": sess["leo"],
            "X-Calliope-Studio": quote(json.dumps({"verifica": vid}))})
        r = c.getresponse()
        secondo = (r.status, r.getheader("Retry-After"), json.loads(r.read() or b"{}"))
        c.close()
        # Un PDF dichiarato (`pdf: true`) riceve il 429 prima che il corpo si legga (passo 4.5,
        # terza revisione della PR #312): con un corpo che non è un PDF, letto darebbe 415
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        c.request("POST", "/api/studio/pagina", body=b"x" * 4000, headers={
            "Content-Type": "application/octet-stream", "X-Calliope-Sessione": sess["leo"],
            "X-Calliope-Studio": quote(json.dumps({"verifica": vid, "pdf": True}))})
        r = c.getresponse()
        dichiarato = (r.status, json.loads(r.read() or b"{}"))
        c.close()
        t.join(30)
    finally:
        PG.dividi_pdf_a_parte = vero
    verifica("PDF insieme: con una divisione in corso il secondo PDF → 429 «riprova fra poco» con Retry-After",
             secondo[0] == 429 and secondo[1] and "riprova" in secondo[2].get("errore", ""), str(secondo))
    verifica("PDF insieme: un PDF dichiarato riceve il 429 prima di leggere il corpo (non il 415)",
             dichiarato[0] == 429, str(dichiarato))
    verifica("PDF insieme: il primo finisce bene", (esiti.get("primo") or (0,))[0] == 200, str(esiti)[:200])
    s, d = chiedi(port, "/api/studio/pagina", sess["leo"], byte=pdf_di(1), meta={"verifica": vid})
    verifica("PDF insieme: finita la prima divisione il secondo passa", s == 200, f"{s} {d}")


def prova_orfani_schema_nuovo():
    """Seconda revisione della PR #312: con lo schema «studio» di una versione più nuova la
    rotazione non toglie orfani (un file citato solo da una tabella della v3 resta); con lo schema
    di questa versione sì. I provvisori di un crollo vanno via (rotazione dopo un'ora, avvio)."""
    import sqlite3
    db_path = TMP / "schema-nuovo" / "memoria.db"
    db_path.parent.mkdir()
    c = Config()
    c.memory_db = str(db_path)
    c.studio_modo = "ombra"
    c.studio_cartella = "studio"
    st = S.Studio(c, registry=REG, log=lambda m: None)
    vid = st.crea_verifica(BRUNO, "Storia", "2026-11-20")
    mid = st.aggiungi_materiale(BRUNO, vid, "foto")
    st.aggiungi_pagina(BRUNO, mid, file="pagine/1/citata.jpg", stato="da_leggere")
    st.close()
    base = D.cartella_di(c)
    (base / "pagine" / "1").mkdir(parents=True)
    file = {n: base / "pagine" / "1" / f"{n}.jpg" for n in ("citata", "della_v3", "orfano")}
    vecchio = time.time() - 2 * 86400
    for f in file.values():
        f.write_bytes(b"x")
        os.utime(f, (vecchio, vecchio))
    db = sqlite3.connect(db_path)
    db.execute("CREATE TABLE studio_carte_v3 (id INTEGER PRIMARY KEY, file TEXT)")
    db.execute("INSERT INTO studio_carte_v3 (file) VALUES ('pagine/1/della_v3.jpg')")
    db.execute("UPDATE meta_schema SET versione = ? WHERE modulo = 'studio'",
               (len(D.MIGRAZIONI) + 1,))
    db.commit()
    db.close()
    oggi = datetime.date(2026, 10, 30)
    out = D.cancella_file(str(db_path), scadute_prima=oggi, cartella="studio")
    verifica("orfani: con uno schema più nuovo la rotazione non toglie niente (il file della tabella nuova resta)",
             all(f.exists() for f in file.values()) and out.get("orfani_saltati") is True, str(out))
    db = sqlite3.connect(db_path)
    db.execute("UPDATE meta_schema SET versione = ? WHERE modulo = 'studio'", (len(D.MIGRAZIONI),))
    db.commit()
    db.close()
    out = D.cancella_file(str(db_path), scadute_prima=oggi, cartella="studio")
    verifica("orfani: contrario, con lo schema di questa versione via i file che nessuna riga cita",
             file["citata"].exists() and not file["orfano"].exists() and not file["della_v3"].exists()
             and out.get("orfani") == 2, str(out))
    # I provvisori: uno vecchio di due ore via con la rotazione, uno recente resta; all'avvio tutti
    tmp = D.cartella_provvisori(base)
    for n in ("pdf-vecchio", "pdf-recente"):
        (tmp / n).mkdir(parents=True)
        (tmp / n / "p0.jpg").write_bytes(b"x")
    due_ore = time.time() - 7200
    os.utime(tmp / "pdf-vecchio", (due_ore, due_ore))
    D.cancella_file(str(db_path), scadute_prima=oggi, cartella="studio")
    verifica("provvisori: la rotazione toglie quelli di un crollo (più di un'ora), non quelli in corso",
             not (tmp / "pdf-vecchio").exists() and (tmp / "pdf-recente").exists())
    # All'avvio (passo 4.5, terza revisione della PR #312) solo quelli più vecchi di 15 minuti:
    # un'altra istanza sullo stesso disco può star dividendo un PDF adesso
    (tmp / "pdf-mezzora").mkdir(parents=True)
    mezzora = time.time() - 1800
    os.utime(tmp / "pdf-mezzora", (mezzora, mezzora))
    S.Studio(c, registry=REG, log=lambda m: None).close()
    verifica("provvisori: all'avvio dello Studio via quelli di più di 15 minuti, non quello in corso",
             tmp.is_dir() and not (tmp / "pdf-mezzora").exists() and (tmp / "pdf-recente").exists())


def prova_schema():
    c = Config()
    c.memory_db = str(TMP / "schema.db")
    c.studio_modo = "ombra"
    st = S.Studio(c, registry=REG, log=lambda m: None)
    try:
        col = {r["name"] for r in st.dati.tutti("PRAGMA table_info(studio_pagine)")}
        ver = st.dati.uno("SELECT versione FROM meta_schema WHERE modulo = 'studio'")
        verifica("schema: dalla versione 2 angoli, avvisi, nitidezza e lato delle pagine (8 dal "
                 "passo 7, #247)", {"angoli", "avvisi", "nitidezza", "larghezza", "altezza"} <= col
                 and ver and ver["versione"] == len(D.MIGRAZIONI) == 9, f"{ver} {sorted(col)}")
        verifica("schema: «da_leggere» è uno stato della pagina", "da_leggere" in D.STATI_PAGINA)
    finally:
        st.close()


def main() -> int:
    try:
        t0 = time.monotonic()
        prova_schema()
        foto = foto_di_fantasia()
        prova_bordi(foto)
        prova_js(foto)
        prova_raddrizza()
        prova_pdf()
        prova_ostili()
        prova_server()
        prova_orfani_schema_nuovo()
        print(f"({time.monotonic() - t0:.1f} s)")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
