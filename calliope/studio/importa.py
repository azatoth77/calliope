"""
L'importazione dei materiali scaricati nello Studio (31/10, issue #298, epic #251, decisione 0035):
un file o un archivio ZIP mandato dallo schermo personale per una verifica diventa materiali e
pagine, con un lavoro di sfondo e l'avanzamento visibile. Analisi nel commento della #298.

**Cosa entra.** Il tipo si decide dai byte (`allegati.riconosci`, `immagini.tipo_dai_byte`), mai
dall'estensione; l'estensione serve solo a scoprire i tipi falsi («compiti.pdf» che è un
programma). Per tipo:
- PDF → come la 4.2: pagine JPEG (`pagine._dividi`) e la copia rifatta senza metadati, per il
  testo senza OCR del lettore;
- JPEG, PNG, WebP → come una foto della galleria (`pagine.prepara_foto`, bordi del server);
- Word, PowerPoint, Excel, OpenDocument, testo, Markdown, CSV, HTML → il testo (i lettori di
  `allegati.py`, coi controlli dello zip: bomba, DOCTYPE), in **pagine di testo già lette**
  (`metodo` «file_testo», nessuna immagine, nessun modello): ~`PAGINA_CARATTERI` caratteri per
  pagina, una diapositiva o un foglio per pagina;
- ZIP → un livello: ogni voce come sopra; uno zip dentro lo zip non si apre.
Il resto diventa una riga «non letto: …» e non ferma gli altri.

**Sicurezza.** Le voci dello zip non si estraggono mai per nome: si leggono in memoria una alla
volta, **contando** i byte decompressi (non quelli dichiarati), con i tetti `Tetti`; sul disco
vanno solo le pagine col nome del server. Percorsi assoluti, lettere di unità, «..», caratteri di
controllo, nomi lunghissimi, link simbolici, voci cifrate: saltate. Tutto il lavoro su un file
gira in un **sottoprocesso** a priorità bassa (`python -m calliope.studio.importa --lavora`), che
dà un segno di vita a ogni voce e a ogni pagina di un PDF: oltre `passo_s` senza segni il
processo si ferma, la voce diventa «troppo pesante» e si riparte dalla successiva; oltre
`tempo_max_s` per tutto l'importazione si ferma («fermata», si riprende a mano).

**Il lavoro di sfondo** (`Importi`): un thread per tutte le importazioni, una alla volta, dalla
più vecchia. Ricontrolla a ogni voce il permesso di chi l'ha mandata e lo stato della verifica
(`Studio.verifica_per_pagine`). Lo stato sta in `studio_importazioni` (schema 13): dopo un
riavvio le importazioni «in_corso» tornano «in_coda» e ripartono dalla prossima voce. Il file
arrivato si toglie a lavoro finito.

**I nomi dei file sono dati**: sullo schermo con textContent (ripuliti con
`allegati.nome_pulito`), mai al modello né nelle frasi pronte; il titolo dei materiali importati
non c'è, e il piano li dice «materiale N».
"""

from __future__ import annotations

import io
import json
import os
import queue
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

STATI = ("in_coda", "in_corso", "fermata", "finita", "errore")
VIVE = ("in_coda", "in_corso")
# Il metodo delle pagine di testo nate dall'importazione (già lette, senza immagine)
FILE_TESTO = "file_testo"
# I caratteri di una pagina di testo (una pagina stampata ne ha 2000–3000)
PAGINA_CARATTERI = 2500
# Le righe tenute per un'importazione (i file dell'archivio con l'esito)
RIGHE_MAX = 500
# Le estensioni del testo che si importa (il resto del testo, json compreso, no: il Takeout
# arriva con la seconda parte della #298)
TESTO_EST = frozenset({"txt", "md", "markdown", "csv", "html", "htm"})
# Le categorie (di `allegati.riconosci`) che diventano pagine
ACCETTATE = frozenset({"immagine", "pdf", "word", "powerpoint", "excel", "opendocument", "testo"})
# Il tipo che un'estensione promette: se i byte dicono altro è un tipo falso
ATTESO = {"pdf": "pdf", "jpg": "immagine", "jpeg": "immagine", "png": "immagine",
          "webp": "immagine", "docx": "word", "pptx": "powerpoint", "xlsx": "excel",
          "odt": "opendocument", "odp": "opendocument", "ods": "opendocument", "zip": "zip",
          **{e: "testo" for e in TESTO_EST}}
NOMI_TIPO = {"pdf": "un PDF", "immagine": "un'immagine", "word": "un documento Word",
             "powerpoint": "una presentazione", "excel": "un foglio Excel",
             "opendocument": "un documento OpenDocument", "testo": "un testo",
             "zip": "un archivio ZIP"}
# Perché una categoria non entra (scritto dal codice: va sullo schermo)
NON_ENTRA = {"eseguibile": "è un programma: non lo apro",
             "script": "è uno script: non lo apro",
             "office_vecchio": "formato Office vecchio: salvalo come docx, pptx o xlsx",
             "audio": "l'audio non lo importo", "video": "i video non li importo",
             "compresso": "archivio che non apro (solo ZIP)",
             "zip": "archivio dentro l'archivio: non lo apro",
             "binario": "formato che non importo"}
# Le parole degli avvisi delle pagine di testo
MACRO, NASCOSTO, TAGLIATO = "macro", "testo_nascosto", "tagliato"
# Il tempo per l'avvio del sottoprocesso (Python e gli import), a parte dal passo
AVVIO_S = 30.0


@dataclass
class Tetti:
    """I tetti di un'importazione (dalla configurazione): voci, byte contati, tempi, pagine."""
    file_max: int = 500
    voce_max_b: int = 30_000_000
    totale_max_b: int = 300_000_000
    rapporto: int = 150
    passo_s: float = 30.0
    tempo_max_s: float = 1800.0
    lato: int = 1600
    soglia: float = 150.0
    pdf_max_pagine: int = 40
    pagine_libere: int = 80

    @classmethod
    def da_cfg(cls, cfg, pagine_libere: int) -> "Tetti":
        def g(nome, di_serie):
            v = getattr(cfg, nome, di_serie)
            return di_serie if v is None else v
        return cls(file_max=int(g("studio_importa_file_max", 500)),
                   voce_max_b=int(float(g("studio_importa_voce_max_mb", 30.0)) * 1_000_000),
                   totale_max_b=int(float(g("studio_importa_totale_max_mb", 300.0)) * 1_000_000),
                   passo_s=float(g("studio_importa_passo_s", 30.0)),
                   tempo_max_s=float(g("studio_importa_tempo_max_s", 1800.0)),
                   lato=int(g("studio_pagina_lato", 1600) or 1600),
                   soglia=float(g("studio_nitidezza_min", 150.0) or 0.0),
                   pdf_max_pagine=int(g("studio_pdf_max_pagine", 40) or 40),
                   pagine_libere=max(0, int(pagine_libere)))


class Rifiuto(ValueError):
    """L'archivio intero non si apre: il messaggio dice perché (va sullo schermo)."""


# ─────────────────────────── nomi e voci ───────────────────────────

def nome_strano(nome: str) -> str | None:
    """Il motivo per saltare una voce dello zip dal suo nome, o None: percorso assoluto o con la
    lettera di un'unità, «..», caratteri di controllo, troppo lungo o troppo profondo. Il nome
    non arriva mai al disco (le pagine le nomina il server): questi sono segni di un archivio
    fatto apposta, e la voce non si apre."""
    n = str(nome or "")
    if not n or len(n) > 400:
        return "nome strano"
    if re.search(r"[\x00-\x1f\x7f]", n):
        return "nome strano"
    p = n.replace("\\", "/")
    if p.startswith("/") or re.match(r"[A-Za-z]:", p):
        return "percorso strano"
    parti = p.split("/")
    if ".." in parti or len(parti) > 20:
        return "percorso strano"
    return None


def _e_link(info: zipfile.ZipInfo) -> bool:
    """La voce è un link simbolico (i bit Unix negli attributi esterni)."""
    modo = (info.external_attr >> 16) & 0xFFFF
    return bool(modo) and stat.S_ISLNK(modo)


@dataclass
class Voce:
    indice: int
    nome: str                       # il percorso ripulito, un dato (per lo schermo)
    motivo: str | None = None       # perché non si apre (già dall'elenco)
    zinfo: zipfile.ZipInfo | None = None


def mostrabile(nome: str) -> str:
    """Il nome di una voce come dato da mostrare: le parti del percorso ripulite
    (`allegati.nome_pulito`), al più 120 caratteri."""
    from ..allegati import nome_pulito
    parti = [nome_pulito(x) for x in str(nome or "").replace("\\", "/").split("/")
             if x not in ("", ".", "..")]
    s = "/".join(parti) or "file"
    return s if len(s) <= 120 else "…" + s[-119:]


def elenca(path, nome: str, tetti: Tetti) -> tuple[str, list[Voce]]:
    """(«zip» o «file», le voci). Un file che non è uno ZIP generico (un docx è un documento,
    non un archivio) è una voce sola. Solleva Rifiuto per l'archivio che non si apre."""
    from ..allegati import riconosci
    with open(path, "rb") as f:
        testa = f.read(65536)
    if not testa.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        return "file", [Voce(0, mostrabile(nome))]
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, ValueError, OSError, EOFError, NotImplementedError):
        return "file", [Voce(0, mostrabile(nome))]
    with zf:
        nomi = set(zf.namelist())
        # Un documento Office o OpenDocument è uno zip, ma è un file: lo dice riconosci
        if any(n in nomi for n in ("word/document.xml", "xl/workbook.xml",
                                   "ppt/presentation.xml", "mimetype")):
            with open(path, "rb") as f:
                if riconosci(f.read(min(os.path.getsize(path), tetti.voce_max_b)), nome) != "zip":
                    return "file", [Voce(0, mostrabile(nome))]
        infos = zf.infolist()
        if len(infos) > tetti.file_max:
            raise Rifiuto(f"l'archivio ha {len(infos)} file: al più {tetti.file_max}")
        voci = []
        for info in sorted((i for i in infos if not i.is_dir()), key=lambda i: i.filename):
            motivo = nome_strano(info.filename)
            if motivo is None and _e_link(info):
                motivo = "collegamento: non lo seguo"
            if motivo is None and info.flag_bits & 0x1:
                motivo = "cifrato"
            if motivo is None and info.file_size > tetti.voce_max_b:
                motivo = f"troppo grande (al più {tetti.voce_max_b // 1_000_000} MB)"
            if motivo is None and info.file_size > 1_000_000 and \
                    info.file_size > tetti.rapporto * max(1, info.compress_size):
                motivo = "compresso in modo sospetto"
            voci.append(Voce(len(voci), mostrabile(info.filename), motivo, info))
        return "zip", voci


def leggi_voce(zf: zipfile.ZipFile, info: zipfile.ZipInfo, massimo: int) -> bytes:
    """I byte di una voce, contati mentre si decomprimono: oltre `massimo` ValueError. Le
    dimensioni dichiarate nell'archivio possono mentire."""
    buf = io.BytesIO()
    with zf.open(info) as f:
        while True:
            pezzo = f.read(1 << 16)
            if not pezzo:
                break
            buf.write(pezzo)
            if buf.tell() > massimo:
                raise ValueError("troppo grande")
    return buf.getvalue()


# ─────────────────────────── che cos'è ───────────────────────────

def classifica(dati: bytes, nome: str) -> tuple[str, str | None]:
    """(categoria, motivo per non importarlo o None). Dai byte, con l'estensione solo contro i
    tipi falsi."""
    from ..allegati import estensione, riconosci
    from ..immagini import tipo_dai_byte
    if not dati:
        return "vuoto", "file vuoto"
    cat = riconosci(dati, nome)
    ext = estensione(nome)
    atteso = ATTESO.get(ext)
    if cat in ("eseguibile", "script"):
        return cat, NON_ENTRA[cat]
    if atteso and atteso != cat:
        # Un tipo falso: «compiti.pdf» che è altro
        return cat, f"il contenuto non è {NOMI_TIPO.get(atteso, 'quello che dice il nome')}"
    if cat in NON_ENTRA and cat != "binario":
        return cat, NON_ENTRA[cat]
    if cat == "immagine" and tipo_dai_byte(dati) not in ("jpeg", "png", "webp"):
        return cat, "formato d'immagine che non importo (solo JPEG, PNG, WebP)"
    if cat == "binario":
        heic = dati[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc")
        return cat, "foto HEIC: mandala come JPEG" if heic else NON_ENTRA["binario"]
    if cat == "testo" and ext not in TESTO_EST and ext:
        return cat, NON_ENTRA["binario"]
    if cat not in ACCETTATE:
        return cat, NON_ENTRA.get(cat, NON_ENTRA["binario"])
    return cat, None


# ─────────────────────────── il testo ───────────────────────────

def html_in_testo(testo: str) -> str:
    """Il testo di una pagina HTML, senza tag, script, stili e commenti (html.parser della
    libreria standard: niente rete, niente entità esterne)."""
    from html.parser import HTMLParser

    class _P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.out, self.salta = [], 0

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "template", "noscript"):
                self.salta += 1
            elif tag in ("p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
                         "section", "article"):
                self.out.append("\n")

        def handle_endtag(self, tag):
            if tag in ("script", "style", "template", "noscript") and self.salta:
                self.salta -= 1

        def handle_data(self, data):
            if not self.salta:
                self.out.append(data)
    p = _P()
    try:
        p.feed(testo)
        p.close()
    except Exception:  # noqa: BLE001 — un HTML rotto dà il testo letto fin lì
        pass
    righe = [" ".join(r.split()) for r in "".join(p.out).splitlines()]
    return "\n".join(r for r in righe if r)


def a_pagine(testo: str, n: int = PAGINA_CARATTERI) -> list[str]:
    """Il testo in pagine di ~n caratteri, tagliate a fine riga (o a uno spazio)."""
    testo = str(testo or "").replace("\x00", "").strip()
    out, i = [], 0
    while i < len(testo):
        j = min(len(testo), i + n)
        if j < len(testo):
            k = testo.rfind("\n", i + n // 2, j)
            if k < 0:
                k = testo.rfind(" ", i + n // 2, j)
            j = k + 1 if k > 0 else j
        pezzo = testo[i:j].strip()
        if pezzo:
            out.append(pezzo)
        i = j
    return out


def _nascosto(dati: bytes, cat: str) -> bool:
    """Testo nascosto: in Word le parti con `w:vanish`, in PowerPoint le diapositive nascoste.
    Si dice (avviso), il testo resta un dato come il resto."""
    try:
        with zipfile.ZipFile(io.BytesIO(dati)) as zf:
            nomi = zf.namelist()
            if cat == "word" and "word/document.xml" in nomi:
                with zf.open("word/document.xml") as f:
                    return b"<w:vanish" in f.read(20_000_000)
            if cat == "powerpoint":
                for n in nomi:
                    if re.fullmatch(r"ppt/slides/slide\d+\.xml", n):
                        with zf.open(n) as f:
                            if re.search(rb"<p:sld\b[^>]*\bshow=\"(0|false)\"", f.read(65536)):
                                return True
    except Exception:  # noqa: BLE001
        return False
    return False


def testi(dati: bytes, nome: str, cat: str, voce_max_b: int) -> tuple[list[str], list[str]]:
    """(pagine di testo, avvisi) di un documento o di un testo. Solleva ValueError col motivo
    per un file che non si legge."""
    from types import SimpleNamespace

    from .. import allegati as A
    cfg = SimpleNamespace(allegati_max_mb=max(1.0, voce_max_b / 1_000_000),
                          allegati_pdf_pagine=0, allegati_pdf_pagine_immagini=0,
                          immagini_lato_max=1280, allegati_audio_max_s=0)
    try:
        att = A.prepara(dati, nome, cfg)
    except A.AllegatoNonValido as e:
        raise ValueError(str(e)) from None
    avvisi = []
    for n in att.note:
        if n.startswith("non lo apro"):
            raise ValueError(n)
        if n.startswith(("file rovinato", "manca la libreria")):
            raise ValueError(n)
        if n.startswith("contiene macro"):
            avvisi.append(MACRO)
    if cat in ("word", "powerpoint") and _nascosto(dati, cat):
        avvisi.append(NASCOSTO)
    if cat == "testo" and A.estensione(nome) in ("html", "htm"):
        parti = [("tutto", html_in_testo(att.testo))]
    else:
        parti = att.parti
    pagine: list[str] = []
    if cat in ("powerpoint", "excel"):
        # Una diapositiva o un foglio per pagina (tagliati se lunghi)
        for _nome, t in parti:
            pagine += a_pagine(t)
    else:
        pagine = a_pagine("\n".join(t for _n, t in parti))
    if len(att.testo) >= A.MAX_TESTO:
        avvisi.append(TAGLIATO)
    if not pagine:
        raise ValueError("non c'è testo")
    return pagine, avvisi


# ─────────────────────────── il sottoprocesso ───────────────────────────

def _scrivi_meta(cartella: Path, i: int, meta: dict):
    d = cartella / f"v{i}"
    d.mkdir(exist_ok=True)
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def elabora(dati: bytes, nome: str, tetti: Tetti, cartella: Path, i: int, avanti) -> dict:
    """Una voce: la sua cartella `v<i>` con le pagine (p0.jpg…, pulito.pdf) o i testi, e il
    `meta` («ok» con tipo e pagine, o «non_letto» col motivo)."""
    from . import pagine as PG
    cat, motivo = classifica(dati, nome)
    if motivo:
        return {"esito": "non_letto", "tipo": cat, "motivo": motivo}
    d = cartella / f"v{i}"
    d.mkdir(exist_ok=True)
    try:
        if cat == "immagine":
            p = PG.prepara_foto(dati, None, tetti.lato, tetti.voce_max_b, tetti.soglia)
            pronte, pulito = [p], None
        elif cat == "pdf":
            massimo = min(tetti.pdf_max_pagine, tetti.pagine_libere)
            if massimo < 1:
                return {"esito": "non_letto", "tipo": cat, "motivo": "la verifica è piena"}
            pronte, pulito = PG._dividi(dati, tetti.lato, massimo, tetti.soglia,
                                        avanti=lambda _i, _n: avanti())
        else:
            tt, avvisi = testi(dati, nome, cat, tetti.voce_max_b)
            if len(tt) > tetti.pagine_libere:
                return {"esito": "non_letto", "tipo": cat,
                        "motivo": f"sono {len(tt)} pagine: la verifica non ne ha tante libere"}
            for k, t in enumerate(tt):
                (d / f"t{k}.txt").write_text(t, encoding="utf-8")
            return {"esito": "ok", "tipo": cat, "testi": len(tt), "avvisi": avvisi}
    except PG.PaginaNonValida as e:
        return {"esito": "non_letto", "tipo": cat, "motivo": str(e)[:200]}
    except ValueError as e:
        return {"esito": "non_letto", "tipo": cat, "motivo": str(e)[:200] or "non si legge"}
    pagine = []
    for k, p in enumerate(pronte):
        (d / f"p{k}.jpg").write_bytes(p.jpeg)
        pagine.append({"larghezza": p.larghezza, "altezza": p.altezza, "bordi": p.bordi,
                       "angoli": p.angoli, "avvisi": list(p.avvisi), "nitidezza": p.nitidezza})
    if pulito:
        (d / "pulito.pdf").write_bytes(pulito)
    return {"esito": "ok", "tipo": cat, "pagine": pagine, "pulito": bool(pulito)}


def lavora(cartella: Path) -> int:
    """Il corpo del sottoprocesso: legge `lavoro.json` (ingresso, nome, inizio, tetti), dice
    «voci N» e per ogni voce da `inizio` scrive `v<i>/meta.json` e dice «voce i». Un segno di
    vita («passo») a ogni pagina di un PDF. «rifiuto <motivo>» per l'archivio che non si apre."""
    lavoro = json.loads((cartella / "lavoro.json").read_text(encoding="utf-8"))
    tetti = Tetti(**lavoro["tetti"])
    path, nome, inizio = Path(lavoro["ingresso"]), str(lavoro["nome"]), int(lavoro["inizio"])

    def di(riga):
        print(riga, flush=True)
    try:
        tipo, voci = elenca(path, nome, tetti)
    except Rifiuto as e:
        di("rifiuto " + " ".join(str(e).split()))
        return 2
    di(f"voci {len(voci)} {tipo}")
    letti = 0
    zf = zipfile.ZipFile(path) if tipo == "zip" else None
    try:
        for v in voci[inizio:]:
            # Il nome (un dato, in JSON su una riga) per la riga «troppo pesante» se si ferma qui
            di(f"inizio {v.indice} " + json.dumps(v.nome, ensure_ascii=True))
            if v.motivo:
                _scrivi_meta(cartella, v.indice, {"esito": "non_letto", "motivo": v.motivo,
                                                  "nome": v.nome})
                di(f"voce {v.indice}")
                continue
            if zf is not None:
                if letti >= tetti.totale_max_b:
                    meta = {"esito": "non_letto", "motivo": "oltre il tetto dell'archivio"}
                else:
                    try:
                        dati = leggi_voce(zf, v.zinfo, min(tetti.voce_max_b,
                                                           tetti.totale_max_b - letti))
                        letti += len(dati)
                        meta = None
                    except ValueError:
                        meta = {"esito": "non_letto", "motivo": "troppo grande"}
                    except (zipfile.BadZipFile, OSError, EOFError, NotImplementedError,
                            RuntimeError, zlib_errore()) as e:
                        meta = {"esito": "non_letto",
                                "motivo": f"voce rovinata ({type(e).__name__})"}
            else:
                with open(path, "rb") as f:
                    dati = f.read(tetti.voce_max_b + 1)
                meta = ({"esito": "non_letto", "motivo": "troppo grande"}
                        if len(dati) > tetti.voce_max_b else None)
            if meta is None:
                meta = elabora(dati, v.nome.rsplit("/", 1)[-1], tetti, cartella, v.indice,
                               lambda: di("passo"))
                del dati
                if meta.get("esito") == "ok":
                    tetti.pagine_libere -= len(meta.get("pagine") or ()) + int(meta.get("testi")
                                                                               or 0)
            meta["nome"] = v.nome
            _scrivi_meta(cartella, v.indice, meta)
            di(f"voce {v.indice}")
    finally:
        if zf is not None:
            zf.close()
    di("fine")
    return 0


def zlib_errore():
    import zlib
    return zlib.error


def _figlio(argv) -> int:
    # Priorità bassa: la voce e il lettore vengono prima (su Windows la dà chi lancia)
    if hasattr(os, "nice"):
        try:
            os.nice(10)
        except OSError:
            pass
    # Gli import prima di «pronto»: il loro tempo è dell'avvio (AVVIO_S), non della prima voce
    for modulo in ("numpy", "PIL.Image", "pypdfium2", "docx", "pptx", "openpyxl",
                   "calliope.allegati", "calliope.studio.pagine"):
        try:
            __import__(modulo)
        except ImportError:
            pass
    print("pronto", flush=True)
    try:
        return lavora(Path(argv[0]))
    except Exception as e:  # noqa: BLE001
        print(f"errore {type(e).__name__}", flush=True)
        return 2


# ─────────────────────────── il lavoro di sfondo ───────────────────────────

def _lettore_righe(stream, coda: queue.Queue):
    try:
        for riga in iter(stream.readline, b""):
            coda.put(riga.decode("utf-8", "replace").strip())
    except (OSError, ValueError):
        pass
    coda.put(None)


class Importi:
    """Il lavoro di sfondo delle importazioni di uno Studio: un thread, una alla volta."""

    def __init__(self, studio, log=print, avvia: bool = True):
        self.studio = studio
        self.log = log
        self._sveglia = threading.Event()
        self._chiuso = False
        self._ferma: set[int] = set()
        self._lock = threading.Lock()
        self.corrente: int | None = None
        self._proc: subprocess.Popen | None = None
        self.misure = {"importazioni": 0, "voci": 0, "pagine": 0, "testi": 0, "non_letti": 0,
                       "pesanti": 0, "riavvii": 0}
        self._thread = None
        self.riprendi()
        if avvia:
            self._thread = threading.Thread(target=self._giro, name="studio-importa",
                                            daemon=True)
            self._thread.start()

    def _registra(self, testo: str):
        try:
            self.log(f"   [STUDIO] importazione: {testo}")
        except Exception:  # noqa: BLE001
            pass

    # ── stato su disco ──
    def riprendi(self) -> int:
        """Dopo un riavvio le importazioni «in_corso» tornano «in_coda»."""
        if not self.studio.dati.scrivibile:
            return 0
        return self.studio.dati.scrivi(
            "UPDATE studio_importazioni SET stato = 'in_coda' WHERE stato = 'in_corso'")

    def sveglia(self):
        self._sveglia.set()

    def ferma(self, iid: int):
        """«Ferma»: l'importazione in corso si ferma alla prima occasione; una in coda subito."""
        with self._lock:
            proc = None
            if self.corrente == int(iid):
                self._ferma.add(int(iid))
                proc = self._proc
            # Una in coda si ferma qui (nella stessa presa del lock: il thread non la prende
            # mentre la si ferma)
            self.studio.dati.scrivi("UPDATE studio_importazioni SET stato = 'fermata', motivo = "
                                    "'fermata da te', aggiornata = ? WHERE id = ? AND stato = "
                                    "'in_coda'", (_adesso(), int(iid)))
        if proc is not None:
            _uccidi(proc)

    def rimetti(self, iid: int) -> bool:
        """«Riprendi»: una fermata torna in coda dalla voce dove era."""
        with self._lock:
            self._ferma.discard(int(iid))
            n = self.studio.dati.scrivi("UPDATE studio_importazioni SET stato = 'in_coda', motivo "
                                        "= NULL, aggiornata = ? WHERE id = ? AND stato = "
                                        "'fermata'", (_adesso(), int(iid)))
        self.sveglia()
        return bool(n)

    def close(self):
        self._chiuso = True
        self._sveglia.set()
        with self._lock:
            proc = self._proc
        if proc is not None:
            _uccidi(proc)
        if self._thread is not None:
            self._thread.join(timeout=10)

    # ── il giro ──
    def _giro(self):
        while not self._chiuso:
            try:
                fatte = self.passata()
            except Exception as e:  # noqa: BLE001 — il thread non muore
                self._registra(f"errore ({type(e).__name__})")
                fatte = 0
            if not fatte:
                self._sveglia.wait(60.0)
                self._sveglia.clear()

    def passata(self) -> int:
        """Le importazioni in coda, una alla volta dalla più vecchia; quante fatte."""
        n = 0
        viste: set[int] = set()
        if not self.studio.dati.scrivibile:
            return 0
        while not self._chiuso:
            r = self.studio.dati.uno("SELECT * FROM studio_importazioni WHERE stato = 'in_coda'"
                                     " ORDER BY id LIMIT 1")
            # Una tornata in coda nella stessa passata (lo Studio in sola lettura) aspetta la
            # prossima sveglia
            if r is None or r["id"] in viste:
                return n
            viste.add(r["id"])
            self.esegui(r)
            n += 1
        return n

    def _aggiorna(self, iid: int, **campi):
        campi["aggiornata"] = _adesso()
        for k in ("conti", "righe"):
            if k in campi and not isinstance(campi[k], str):
                campi[k] = json.dumps(campi[k], ensure_ascii=False)
        sql = ", ".join(f"{k} = ?" for k in campi)
        self.studio.dati.scrivi(f"UPDATE studio_importazioni SET {sql} WHERE id = ?",
                                (*campi.values(), int(iid)))

    def _chiudi(self, riga: dict, stato: str, motivo: str | None = None):
        """La fine di un'importazione: «finita» o «errore» tolgono il file arrivato; «fermata»
        lo tiene per riprendere."""
        campi = {"stato": stato, "motivo": motivo}
        if stato in ("finita", "errore"):
            campi["fine"] = _adesso()
            if riga.get("file"):
                from . import dati as D
                D.togli_file([riga["file"]], D.cartella_di(self.studio.cfg))
                campi["file"] = None
        self._aggiorna(riga["id"], **campi)
        self._registra(f"{riga['id']} {stato}" + (f" ({motivo})" if motivo else ""))
        if stato == "finita":
            self.misure["importazioni"] += 1
            if self.studio.lettore is not None:
                self.studio.lettore.sveglia()

    def esegui(self, riga: dict):
        """Un'importazione: il sottoprocesso dalla prossima voce, le voci scritte nel db man
        mano, i tetti di tempo; riparte dopo una voce troppo pesante."""
        from . import dati as D
        from .servizio import NonPermesso, NonTrovata, VerificaChiusa
        iid = int(riga["id"])
        with self._lock:
            # Presa solo se è ancora in coda (un «Ferma» o un «Togli» arrivati intanto vincono)
            if self.studio.dati.scrivi("UPDATE studio_importazioni SET stato = 'in_corso', "
                                       "aggiornata = ? WHERE id = ? AND stato = 'in_coda'",
                                       (_adesso(), iid)) != 1:
                return
            self.corrente = iid
        try:
            chi = self.studio._profilo(riga["chi"]) if riga.get("chi") else None
            try:
                v = self.studio.verifica_per_pagine(chi, riga["verifica"])
            except (NonTrovata, NonPermesso):
                return self._chiudi(riga, "errore", "la verifica non c'è più")
            except VerificaChiusa:
                return self._chiudi(riga, "errore", "la verifica è chiusa")
            except PermissionError:
                return self._aggiorna(iid, stato="in_coda")
            cartella = D.cartella_di(self.studio.cfg)
            ingresso = (Path(cartella) / str(riga["file"] or "")).resolve() if cartella else None
            if ingresso is None or not riga.get("file") or \
                    (Path(cartella).resolve() / D.CARTELLA_PAGINE) not in ingresso.parents or \
                    not ingresso.is_file():
                return self._chiudi(riga, "errore", "il file arrivato non c'è più")
            t0 = time.monotonic()
            prossima = int(riga["prossima"] or 0)
            while True:
                esito, prossima = self._sottoprocesso(riga, chi, v, ingresso, prossima, t0)
                if esito == "fine":
                    return self._chiudi(self._riga(iid) or riga, "finita")
                if esito == "rifiuto":
                    return self._chiudi(self._riga(iid) or riga, "errore",
                                        self._riga(iid).get("motivo"))
                if esito == "fermata":
                    return self._aggiorna(iid, stato="fermata", prossima=prossima,
                                          motivo="fermata da te")
                if esito == "tempo":
                    return self._aggiorna(iid, stato="fermata", prossima=prossima,
                                          motivo="ci metteva troppo: riprendi per continuare")
                if esito == "chiusura":
                    return self._aggiorna(iid, stato="in_coda", prossima=prossima)
                if esito in ("permesso", "errore"):
                    r = self._riga(iid) or riga
                    return self._chiudi(r, "errore", r.get("motivo"))
                # «pesante»: la voce che bloccava è scritta, si riparte dalla successiva, con le
                # pagine libere di adesso e ricontrollando la verifica
                self.misure["riavvii"] += 1
                try:
                    v = self.studio.verifica_per_pagine(chi, riga["verifica"])
                except (NonTrovata, NonPermesso, VerificaChiusa, PermissionError):
                    return self._chiudi(self._riga(iid) or riga, "errore",
                                        "la verifica non prende più materiali")
        finally:
            with self._lock:
                self.corrente = None
                self._ferma.discard(iid)

    def _riga(self, iid: int) -> dict | None:
        return self.studio.dati.uno("SELECT * FROM studio_importazioni WHERE id = ?", (iid,))

    def _sottoprocesso(self, riga, chi, v, ingresso: Path, prossima: int, t0: float):
        """Un giro del sottoprocesso da `prossima`: (esito, prossima voce). Esiti: fine,
        rifiuto, fermata, tempo, chiusura, pesante, permesso, errore."""
        from . import dati as D
        iid = int(riga["id"])
        cartella = D.cartella_di(self.studio.cfg)
        prov = D.cartella_provvisori(cartella)
        prov.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="imp-", dir=str(prov)))
        massimo = int(getattr(self.studio.cfg, "studio_pagine_max", 80) or 80)
        tetti = Tetti.da_cfg(self.studio.cfg, massimo - int(v["n_pagine"]))
        proc = None
        try:
            (tmp / "lavoro.json").write_text(json.dumps(
                {"ingresso": str(ingresso), "nome": riga.get("nome") or "file",
                 "inizio": prossima, "tetti": asdict(tetti)}), encoding="utf-8")
            radice = Path(__file__).resolve().parent.parent.parent
            flags = 0x00004000 if sys.platform == "win32" else 0   # BELOW_NORMAL_PRIORITY_CLASS
            proc = subprocess.Popen(
                [sys.executable, "-m", "calliope.studio.importa", "--lavora", str(tmp)],
                cwd=str(radice), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, creationflags=flags)
            with self._lock:
                self._proc = proc
            coda: queue.Queue = queue.Queue()
            threading.Thread(target=_lettore_righe, args=(proc.stdout, coda), daemon=True,
                             name="studio-importa-righe").start()
            pronto, voce, nome_voce = False, None, None
            ultimo = time.monotonic()
            while True:
                if self._chiuso:
                    return "chiusura", prossima
                if iid in self._ferma:
                    return "fermata", prossima
                if time.monotonic() - t0 > tetti.tempo_max_s:
                    return "tempo", prossima
                # Fra un segno di vita e l'altro al più `passo_s` (l'avvio ha il suo tempo)
                attesa = tetti.passo_s if pronto else AVVIO_S
                try:
                    t = coda.get(timeout=min(0.5, attesa))
                except queue.Empty:
                    if time.monotonic() - ultimo <= attesa:
                        continue
                    t = None
                else:
                    ultimo = time.monotonic()
                if t is None:
                    if self._chiuso:
                        return "chiusura", prossima
                    if iid in self._ferma:
                        return "fermata", prossima
                    if voce is None:
                        # Prima di una voce: il sottoprocesso non è partito o non legge l'elenco
                        self._aggiorna(iid, motivo="non riesco ad aprire il file")
                        return "errore", prossima
                    # La voce che lo teneva occupato (o che l'ha fatto cadere) è troppo pesante
                    self.misure["pesanti"] += 1
                    self._non_letto(iid, voce, nome_voce, "troppo pesante da leggere")
                    return "pesante", voce + 1
                if t == "pronto":
                    pronto = True
                elif t.startswith("rifiuto "):
                    self._aggiorna(iid, motivo=t[len("rifiuto "):][:200])
                    return "rifiuto", prossima
                elif t.startswith("voci "):
                    pezzi = t.split()
                    self._aggiorna(iid, voci=int(pezzi[1]), tipo=pezzi[2] if len(pezzi) > 2
                                   else None)
                elif t.startswith("inizio "):
                    pezzi = t.split(" ", 2)
                    voce = int(pezzi[1])
                    try:
                        nome_voce = str(json.loads(pezzi[2]))[:120] if len(pezzi) > 2 else None
                    except ValueError:
                        nome_voce = None
                elif t.startswith("voce "):
                    i = int(t.split()[1])
                    esito = self._scrivi_voce(riga, chi, tmp, i)
                    shutil.rmtree(tmp / f"v{i}", ignore_errors=True)
                    prossima, voce = i + 1, None
                    self._aggiorna(iid, prossima=prossima)
                    if esito is not None:
                        return esito, prossima
                elif t == "fine":
                    return "fine", prossima
                elif t.startswith("errore"):
                    if voce is not None:
                        self._non_letto(iid, voce, nome_voce, "non si legge")
                        return "pesante", voce + 1
                    self._aggiorna(iid, motivo="non riesco ad aprire il file")
                    return "errore", prossima
        finally:
            with self._lock:
                self._proc = None
            if proc is not None:
                _uccidi(proc)
            shutil.rmtree(tmp, ignore_errors=True)

    def _non_letto(self, iid: int, i: int, nome, motivo: str):
        r = self._riga(iid)
        if r is None:
            return
        righe = D_da_j(r["righe"])
        conti = _conti(r["conti"])
        conti["non_letti"] = conti.get("non_letti", 0) + 1
        conti["file"] = conti.get("file", 0) + 1
        if not nome:
            nome = next((x.get("nome") for x in righe if x.get("i") == i), None) or \
                f"file {i + 1}"
        if len(righe) < RIGHE_MAX:
            righe.append({"i": i, "nome": nome, "esito": "non_letto", "motivo": motivo})
        self.misure["non_letti"] += 1
        self._aggiorna(iid, righe=righe, conti=conti)

    def _scrivi_voce(self, riga, chi, tmp: Path, i: int) -> str | None:
        """Le pagine di una voce nel db (o la riga «non letto»). Un esito che ferma
        l'importazione («permesso»), o None."""
        from . import pagine as PG
        from .servizio import NonPermesso, NonTrovata, TroppePagine, VerificaChiusa
        iid = int(riga["id"])
        d = tmp / f"v{i}"
        try:
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {"esito": "non_letto", "motivo": "non si legge"}
        nome = str(meta.get("nome") or f"file {i + 1}")[:120]
        self.misure["voci"] += 1
        if meta.get("esito") != "ok":
            self._non_letto(iid, i, nome, str(meta.get("motivo") or "non si legge")[:200])
            return None
        try:
            if meta.get("testi"):
                tt = [(d / f"t{k}.txt").read_text(encoding="utf-8")
                      for k in range(int(meta["testi"]))]
                out = self.studio.aggiungi_testi(chi, riga["verifica"], tt,
                                                 avvisi=list(meta.get("avvisi") or ()),
                                                 importazione=iid)
                self.misure["testi"] += len(tt)
            else:
                pronte = [PG.Pronta((d / f"p{k}.jpg").read_bytes(), int(m["larghezza"]),
                                    int(m["altezza"]), str(m.get("bordi") or "file"),
                                    m.get("angoli"), list(m.get("avvisi") or ()),
                                    float(m.get("nitidezza") or 0.0))
                          for k, m in enumerate(meta.get("pagine") or ())]
                pulito = (d / "pulito.pdf").read_bytes() if meta.get("pulito") else None
                out = self.studio.aggiungi_pronte(chi, riga["verifica"], pronte, "file", None,
                                                  None, pulito, importazione=iid)
                self.misure["pagine"] += len(pronte)
        except TroppePagine:
            self._non_letto(iid, i, nome, "la verifica è piena")
            return None
        except (NonTrovata, NonPermesso):
            self._aggiorna(iid, motivo="la verifica non c'è più")
            return "permesso"
        except VerificaChiusa:
            self._aggiorna(iid, motivo="la verifica è chiusa")
            return "permesso"
        except (OSError, PermissionError, ValueError) as e:
            self._non_letto(iid, i, nome, f"non salvato ({type(e).__name__})")
            return None
        r = self._riga(iid)
        righe, conti = D_da_j(r["righe"]), _conti(r["conti"])
        n = len(out.get("pagine") or ())
        conti["file"] = conti.get("file", 0) + 1
        conti["letti"] = conti.get("letti", 0) + 1
        conti["pagine"] = conti.get("pagine", 0) + n
        if len(righe) < RIGHE_MAX:
            righe.append({"i": i, "nome": nome, "esito": "ok", "tipo": meta.get("tipo"),
                          "pagine": n, "materiale": out.get("materiale"),
                          "avvisi": sorted({a for p in out.get("pagine") or ()
                                            for a in p.get("avvisi") or ()})})
        self._aggiorna(iid, righe=righe, conti=conti)
        return None


# ─────────────────────────── l'API dello Studio (mixin) ───────────────────────────

_CREA = threading.Lock()
# Le fasi della scheda, nell'ordine (issue #298): ricevuto, estratto, letto, argomenti, preparato
FASI = ("ricevuto", "estratto", "letto", "argomenti", "preparato")
# Le righe mandate alla pagina per un'importazione (le altre si contano)
RIGHE_SCHERMO = 200


class Importazioni:
    """L'importazione dei materiali nello Studio (mixin di `Studio`): l'arrivo del file, le
    pagine di testo, la vista con le fasi e i tasti «Ferma», «Riprendi», «Togli»."""

    @property
    def importi(self) -> Importi:
        """Il lavoro di sfondo, creato al primo uso (uno solo anche da più thread)."""
        with _CREA:
            if self._importi is None:
                self._importi = Importi(self, log=self.log)
        return self._importi

    def importa_acceso(self) -> bool:
        return bool(getattr(self.cfg, "studio_importa", True))

    def avvia_importi(self):
        """All'avvio: riprende le importazioni rimaste in coda o in corso, se ce ne sono."""
        if self._importi is None and self.dati.scrivibile and self.importa_acceso() and \
                self.dati.uno("SELECT 1 FROM studio_importazioni WHERE stato IN ('in_coda', "
                              "'in_corso') LIMIT 1"):
            return self.importi
        return self._importi

    def importazione_viva(self, vid) -> bool:
        return self.dati.uno("SELECT 1 FROM studio_importazioni WHERE verifica = ? AND stato IN "
                             "('in_coda', 'in_corso') LIMIT 1", (int(vid),)) is not None

    def importazioni_vive(self, persona) -> int:
        r = self.dati.uno("SELECT COUNT(*) AS n FROM studio_importazioni WHERE persona = ? AND "
                          "stato IN ('in_coda', 'in_corso', 'fermata')", (str(persona),))
        return int(r["n"]) if r else 0

    def registra_importazione(self, chi, vid, file_rel: str, nome: str) -> int:
        """Il file arrivato (già scritto da chi chiama con `pagine.apri_nuovo`) diventa
        un'importazione «in_coda». Ricontrolla la verifica e il tetto delle importazioni vive
        della persona (`studio_importa_coda`); se non entra il file si toglie. L'id."""
        from . import dati as D
        from .servizio import TroppePagine
        try:
            self._scrivibile()
            with self.dati.lock:
                v = self.verifica_per_pagine(chi, vid)
                coda = int(getattr(self.cfg, "studio_importa_coda", 10) or 10)
                if self.importazioni_vive(v["persona"]) >= coda:
                    raise TroppeImportazioni(coda)
                massimo = int(getattr(self.cfg, "studio_pagine_max", 80) or 80)
                if v["n_pagine"] >= massimo:
                    raise TroppePagine(massimo)
                iid = self.dati.scrivi(
                    "INSERT INTO studio_importazioni (verifica, persona, chi, file, nome, stato, "
                    "creata, aggiornata) VALUES (?, ?, ?, ?, ?, 'in_coda', ?, ?)",
                    (v["id"], str(v["persona"]), getattr(chi, "id", None), file_rel,
                     mostrabile(nome)[:120], D.adesso(), D.adesso()))
        except Exception:
            D.togli_file([file_rel], D.cartella_di(self.cfg))
            raise
        self._registra(f"verifica {v['id']}: importazione {iid} in coda "
                       f"({self._chi_registro(chi, v['persona'])})")
        self.importi.sveglia()
        return iid

    def aggiungi_testi(self, chi, vid, testi_: list, avvisi=None,
                       importazione: int | None = None) -> dict:
        """Le pagine di testo di un file importato (#298): un materiale «file» senza titolo (il
        nome del file è un dato: il piano dice «materiale N»), una pagina per testo nello stato
        «letta» col `metodo` «file_testo», senza immagine e senza modello. Il testo è un dato
        non fidato come quello dell'OCR. Il tetto `studio_pagine_max`."""
        from . import dati as D
        from .servizio import TroppePagine
        self._scrivibile()
        massimo = int(getattr(self.cfg, "studio_pagine_max", 80) or 80)
        av = D.j(sorted(set(avvisi or ()))) if avvisi else None
        with self.dati.lock:
            v = self.verifica_per_pagine(chi, vid)
            if v["n_pagine"] + len(testi_) > massimo:
                raise TroppePagine(massimo)
            db = self.dati.db
            try:
                if db.in_transaction:
                    db.commit()
                db.execute("BEGIN IMMEDIATE")
                mid = db.execute(
                    "INSERT INTO studio_materiali (verifica, origine, titolo, riferimento, creato, "
                    "importazione) VALUES (?, 'file', NULL, NULL, ?, ?)",
                    (v["id"], D.adesso(), int(importazione) if importazione is not None
                     else None)).lastrowid
                r = db.execute("SELECT COALESCE(MAX(p.ordine), 0) FROM studio_pagine p JOIN "
                               "studio_materiali m ON m.id = p.materiale WHERE m.verifica = ?",
                               (v["id"],)).fetchone()
                ordine = int(r[0])
                out = []
                for t in testi_:
                    ordine += 1
                    pid = db.execute(
                        "INSERT INTO studio_pagine (materiale, ordine, stato, testo, metodo, "
                        "creata, avvisi) VALUES (?, ?, 'letta', ?, ?, ?, ?)",
                        (mid, ordine, str(t), FILE_TESTO, D.adesso(), av)).lastrowid
                    out.append({"id": pid, "ordine": ordine, "avvisi": list(avvisi or ())})
                db.commit()
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
        self._registra(f"verifica {v['id']}: {len(out)} pagine di testo importate "
                       f"({self._chi_registro(chi, v['persona'])})")
        self._ricalcola_sicuro(v["id"])
        return {"verifica": v["id"], "materiale": mid, "pagine": out}

    def _importazione(self, chi, vid, iid) -> tuple[dict, dict]:
        from .servizio import NonTrovata
        v = self._verifica(chi, vid)
        r = self.dati.uno("SELECT * FROM studio_importazioni WHERE id = ? AND verifica = ?",
                          (int(iid), v["id"]))
        if r is None:
            raise NonTrovata()
        return r, v

    def azione_importazione(self, chi, vid, iid, azione: str) -> bool:
        """«ferma», «riprendi» o «togli» (la riga e il file arrivato; le pagine già fatte
        restano, come materiali della verifica). Vero se è cambiato qualcosa."""
        from . import dati as D
        self._scrivibile()
        r, _v = self._importazione(chi, vid, iid)
        if azione == "ferma":
            if r["stato"] not in VIVE:
                return False
            self.importi.ferma(r["id"])
            return True
        if azione == "riprendi":
            return self.importi.rimetti(r["id"])
        if azione == "togli":
            if self._importi is not None:
                self._importi.ferma(r["id"])
            self.dati.scrivi("DELETE FROM studio_importazioni WHERE id = ?", (r["id"],))
            if r.get("file"):
                D.togli_file([r["file"]], D.cartella_di(self.cfg))
            return True
        raise ValueError("azione sconosciuta")

    def importazioni(self, chi, vid) -> dict:
        """Le importazioni di una verifica con le fasi e i conti, per la scheda dello Studio.
        Nomi e motivi sono dati da mostrare con textContent; le fasi le scrive il codice."""
        v = self._verifica(chi, vid)
        out = []
        for r in self.dati.tutti("SELECT * FROM studio_importazioni WHERE verifica = ? "
                                 "ORDER BY id DESC LIMIT 20", (v["id"],)):
            conti = _conti(r["conti"])
            righe = D_da_j(r["righe"])
            pag = self.dati.tutti(
                "SELECT p.stato FROM studio_pagine p JOIN studio_materiali m ON m.id = "
                "p.materiale WHERE m.importazione = ? AND p.stato != 'tolta'", (r["id"],))
            letti = sum(1 for p in pag if p["stato"] in ("letta", "illeggibile", "da_parte"))
            fasi = {"ricevuto": "fatta"}
            estratto = r["stato"] == "finita"
            fasi["estratto"] = "fatta" if estratto else (
                "in_corso" if r["stato"] == "in_corso" else "ferma" if r["stato"] in
                ("fermata", "errore") else "in_attesa")
            letto = estratto and letti == len(pag)
            fasi["letto"] = "fatta" if letto else ("in_corso" if pag else "in_attesa")
            fine = r["fine"] or ""
            arg = letto and bool(v.get("argomenti_del")) and str(v["argomenti_del"]) >= fine
            fasi["argomenti"] = "fatta" if arg else (
                "spenta" if not getattr(self.cfg, "studio_argomenti", True) else "in_attesa")
            prep = arg and any(str(v.get(k) or "") >= fine and v.get(k)
                               for k in ("carte_del", "domande_del", "mappa_del"))
            fasi["preparato"] = "fatta" if prep else "in_attesa"
            n_arg = self.dati.uno("SELECT COUNT(*) AS n FROM studio_argomenti WHERE verifica = ? "
                                  "AND stato != 'tolto'", (v["id"],))["n"] if arg else None
            out.append({
                "id": r["id"], "nome": r["nome"], "tipo": r["tipo"], "stato": r["stato"],
                "motivo": r["motivo"], "voci": r["voci"], "prossima": r["prossima"],
                "creata": r["creata"], "fine": r["fine"],
                "conti": {"file": int(conti.get("file", 0)), "letti": int(conti.get("letti", 0)),
                          "non_letti": int(conti.get("non_letti", 0)),
                          "pagine": len(pag), "pagine_lette": letti, "argomenti": n_arg},
                "fasi": [{"fase": f, "stato": fasi[f]} for f in FASI],
                "righe": righe[:RIGHE_SCHERMO], "righe_altre": max(0, len(righe) - RIGHE_SCHERMO),
                "puo": {"ferma": r["stato"] in VIVE, "riprendi": r["stato"] == "fermata",
                        "togli": True}})
        return {"verifica": v["id"], "importazioni": out,
                "viva": any(x["stato"] in VIVE for x in out),
                "acceso": self.importa_acceso()}


class TroppeImportazioni(ValueError):
    """La persona ha già tante importazioni vive (`studio_importa_coda`)."""

    def __init__(self, massimo: int = 0):
        super().__init__(f"al più {massimo} importazioni insieme")
        self.massimo = massimo


def D_da_j(testo) -> list:
    from .dati import da_j
    return [x for x in da_j(testo) if isinstance(x, dict)]


def _conti(testo) -> dict:
    try:
        v = json.loads(testo or "{}")
    except (TypeError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


def _adesso() -> str:
    from .dati import adesso
    return adesso()


def _uccidi(proc: subprocess.Popen):
    try:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--lavora":
        sys.exit(_figlio(sys.argv[2:]))
    sys.exit(2)
