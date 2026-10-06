"""
File ZIM finti per le prove (01/10/2026): piccoli, costruiti al momento con `struct`, così
le prove del lettore (calliope/zim.py), dell'indice (calliope/biblioteca_indice.py) e delle
installazioni non dipendono dai 12 GB della biblioteca vera.

    dati = crea_zim(voci=[("Monte_Bianco", "Monte Bianco", "<html>…")],
                    redirect=[("Bianco", "Bianco", "Monte_Bianco")],
                    compressioni=("zstd", "xz", "nessuna"), esteso=(1,))

Formato 6.3 come quelli di Kiwix: namespace C (voci), M (metadati), W (mainPage), X
(elenco per titolo `X/listing/titleOrdered/v1` in un cluster non compresso), lista dei
percorsi ordinata, cluster compressi con xz o zstd, a offset normali o estesi (64 bit),
MD5 finale.
"""

import hashlib
import lzma
import struct
import uuid as _uuid

MAGIC = 72173914
REDIRECT = 0xFFFF
_COMP = {"nessuna": 1, "xz": 4, "zstd": 5}


def _compress(kind: str, data: bytes) -> bytes:
    if kind == "xz":
        return lzma.compress(data, format=lzma.FORMAT_XZ)
    if kind == "zstd":
        try:
            from compression import zstd
            return zstd.compress(data)
        except ImportError:                      # Python < 3.14: pacchetto zstandard
            import zstandard
            return zstandard.ZstdCompressor().compress(data)
    return data


def _cluster(blobs: list[bytes], kind: str, extended: bool) -> bytes:
    osz = 8 if extended else 4
    fmt = "<Q" if extended else "<I"
    offsets, pos = [], osz * (len(blobs) + 1)
    for b in blobs:
        offsets.append(pos)
        pos += len(b)
    offsets.append(pos)
    data = b"".join(struct.pack(fmt, o) for o in offsets) + b"".join(blobs)
    info = _COMP[kind] | (0x10 if extended else 0)
    return bytes([info]) + _compress(kind, data)


def crea_zim(voci, redirect=(), metadati=None, risorse=(), per_cluster=2,
             compressioni=("zstd", "xz"), esteso=(), uuid: bytes | None = None,
             principale: str | None = None) -> bytes:
    """Un file ZIM 6.3 in memoria.
    voci: (percorso, titolo, html) nel namespace C, text/html;
    redirect: (percorso, titolo, percorso di destinazione);
    risorse: (percorso, tipo MIME, contenuto) nel namespace C, non «front»;
    compressioni: a turno per i cluster dei contenuti; esteso: quali cluster hanno gli
    offset a 64 bit (indici dei cluster dei contenuti)."""
    metadati = {"Title": "Prova", "Language": "ita", "Date": "2026-10-01",
                **(metadati or {})}
    mimes = ["text/html", "text/plain", "text/css", "application/octet-stream+zimlisting"]
    entries = []
    for path, title, page in voci:
        entries.append({"ns": "C", "path": path, "title": title, "mime": "text/html",
                        "data": page.encode("utf-8") if isinstance(page, str) else page})
    for path, mime, data in risorse:
        if mime not in mimes:
            mimes.append(mime)
        entries.append({"ns": "C", "path": path, "title": "", "mime": mime,
                        "data": data if isinstance(data, bytes) else data.encode("utf-8")})
    for k, v in metadati.items():
        entries.append({"ns": "M", "path": k, "title": "", "mime": "text/plain",
                        "data": v.encode("utf-8")})
    for path, title, target in redirect:
        entries.append({"ns": "C", "path": path, "title": title, "target": ("C", target)})
    principale = principale or (voci[0][0] if voci else None)
    if principale:
        entries.append({"ns": "W", "path": "mainPage", "title": "", "target": ("C", principale)})
    listing = {"ns": "X", "path": "listing/titleOrdered/v1", "title": "",
               "mime": "application/octet-stream+zimlisting", "data": b""}
    entries.append(listing)
    entries.sort(key=lambda e: e["ns"].encode() + e["path"].encode("utf-8"))
    index = {(e["ns"], e["path"]): i for i, e in enumerate(entries)}
    # Elenco per titolo: le voci «front» (articoli e loro redirect) per namespace+titolo
    front = [i for i, e in enumerate(entries) if e["ns"] == "C"
             and ("target" in e or e.get("mime") == "text/html")]
    front.sort(key=lambda i: b"C" + (entries[i]["title"] or entries[i]["path"]).encode("utf-8"))
    listing["data"] = struct.pack(f"<{len(front)}I", *front)
    # Cluster: i contenuti a gruppi, poi l'elenco da solo e non compresso
    contents = [e for e in entries if "data" in e and e is not listing]
    clusters: list[bytes] = []
    for c, k in enumerate(range(0, len(contents), per_cluster)):
        group = contents[k:k + per_cluster]
        for b, e in enumerate(group):
            e["cluster"], e["blob"] = c, b
        clusters.append(_cluster([e["data"] for e in group], compressioni[c % len(compressioni)],
                                 c in esteso))
    listing["cluster"], listing["blob"] = len(clusters), 0
    clusters.append(_cluster([listing["data"]], "nessuna", False))
    # Dirent
    dirents = []
    for e in entries:
        tail = e["path"].encode("utf-8") + b"\0" + e["title"].encode("utf-8") + b"\0"
        if "target" in e:
            dirents.append(struct.pack("<HBcII", REDIRECT, 0, e["ns"].encode(), 0,
                                       index[e["target"]]) + tail)
        else:
            dirents.append(struct.pack("<HBcIII", mimes.index(e["mime"]), 0, e["ns"].encode(),
                                       0, e["cluster"], e["blob"]) + tail)
    mime_list = b"".join(m.encode() + b"\0" for m in mimes) + b"\0"
    mime_pos = 80
    path_ptr_pos = mime_pos + len(mime_list)
    cluster_ptr_pos = path_ptr_pos + 8 * len(entries)
    pos = cluster_ptr_pos + 8 * len(clusters)
    dirent_pos = []
    for d in dirents:
        dirent_pos.append(pos)
        pos += len(d)
    cluster_pos = []
    for c in clusters:
        cluster_pos.append(pos)
        pos += len(c)
    checksum_pos = pos
    main = index.get(("W", "mainPage"), 0xFFFFFFFF)
    header = struct.pack("<IHH16sIIQQQQIIQ", MAGIC, 6, 3, uuid or _uuid.uuid4().bytes,
                         len(entries), len(clusters), path_ptr_pos, 0xFFFFFFFFFFFFFFFF,
                         cluster_ptr_pos, mime_pos, main, 0xFFFFFFFF, checksum_pos)
    body = (header + mime_list + b"".join(struct.pack("<Q", p) for p in dirent_pos)
            + b"".join(struct.pack("<Q", p) for p in cluster_pos) + b"".join(dirents)
            + b"".join(clusters))
    assert len(body) == checksum_pos
    return body + hashlib.md5(body).digest()


def pagina(titolo: str, *paragrafi: str, infobox: dict | None = None) -> str:
    """Una voce in stile Wikipedia: titolo, infobox facoltativa, paragrafi."""
    box = ""
    if infobox:
        rows = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in infobox.items())
        box = f'<table class="infobox">{rows}</table>'
    ps = "".join(f"<p>{p}<sup class=\"reference\">[1]</sup></p>" for p in paragrafi)
    return (f"<!DOCTYPE html><html><head><title>{titolo}</title><style>p{{}}</style></head>"
            f"<body><h1>{titolo}</h1>{box}{ps}<script>var x=1;</script></body></html>")


# Una piccola «Wikipedia» per le prove della biblioteca e delle installazioni
VOCI = [
    ("Monte_Bianco", "Monte Bianco", pagina(
        "Monte Bianco",
        "Il Monte Bianco è la montagna più alta delle Alpi e d'Italia, con un'altezza di "
        "4805 metri sul livello del mare.",
        "Si trova al confine tra Italia e Francia, nel massiccio del Monte Bianco.",
        infobox={"Altezza": "4805 m s.l.m.", "Catena": "Alpi"})),
    ("Fiume_Po", "Po", pagina(
        "Po", "Il Po è il fiume più lungo d'Italia: la sua lunghezza è di 652 chilometri.",
        "Nasce dal Monviso e sfocia nel mare Adriatico con un ampio delta.",
        infobox={"Lunghezza": "652 km"})),
    ("Vulcano", "Vulcano", pagina(
        "Vulcano", "Un vulcano è un'apertura della crosta terrestre da cui esce il magma, "
        "che in superficie diventa lava.",
        "I vulcani attivi in Italia sono l'Etna, lo Stromboli e il Vesuvio.")),
    ("Etna", "Etna", pagina(
        "Etna", "L'Etna è il vulcano attivo più alto d'Europa, in Sicilia, alto circa 3357 "
        "metri.")),
    ("Penicillina", "Penicillina", pagina(
        "Penicillina", "La penicillina è un antibiotico scoperto da Alexander Fleming nel "
        "1928 osservando una muffa.")),
    ("Città_di_Castello", "Città di Castello", pagina(
        "Città di Castello", "Città di Castello è un comune italiano della provincia di "
        "Perugia in Umbria, sul fiume Tevere.")),
]
REDIRECT_VOCI = [("Bianco", "Monte Bianco (montagna)", "Monte_Bianco"),
                 ("Po_(fiume)", "Po (fiume)", "Fiume_Po"),
                 # parole che stanno solo nel titolo del redirect (alias nell'indice)
                 ("Sovrano_dei_ghiacci", "Sovrano dei ghiacci", "Monte_Bianco")]


def mini_wikipedia(**kw) -> bytes:
    return crea_zim(VOCI, REDIRECT_VOCI, risorse=[("style.css", "text/css", "p{}")], **kw)
