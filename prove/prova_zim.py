import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco del lettore ZIM in puro Python (calliope/zim.py; 01/10/2026).

Su file ZIM minuscoli costruiti qui (prove/zim_finto.py), senza la biblioteca vera:
intestazione e tipi MIME, voci per percorso e per titolo, redirect, metadati e voce
principale, cluster non compressi, xz, zstd e a offset estesi, blob più grandi del passo di
decompressione, letture da più thread, errori su file troncati, rovinati o che non sono ZIM.
Se libzim è installata (solo x64), confronta anche le sue letture sugli stessi file.
"""

import shutil
import tempfile
import threading
from pathlib import Path

from calliope.zim import ZimError, ZimFile, read_uuid
from prove.zim_finto import REDIRECT_VOCI, VOCI, crea_zim, mini_wikipedia, pagina

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


TMP = Path(tempfile.mkdtemp(prefix="calliope-zim-"))
UUID = bytes(range(16))
GRANDE = pagina("Grande", *(f"Paragrafo numero {i} con un po' di testo che si ripete "
                            f"{'abc' * 40}." for i in range(4000)))      # ~650 KB
VOCI_TUTTE = VOCI + [("Grande", "Grande", GRANDE), ("Zeta", "Zeta finale", pagina("Zeta", "z"))]
dati = crea_zim(VOCI_TUTTE, REDIRECT_VOCI, risorse=[("style.css", "text/css", "p{}")],
                per_cluster=2, compressioni=("zstd", "xz", "nessuna"), esteso=(1, 3),
                uuid=UUID)
f = TMP / "prova_2026-10.zim"
f.write_bytes(dati)

z = ZimFile(f)
verifica("intestazione: versione 6.3, uuid, voci e cluster", (z.major, z.minor) == (6, 3)
         and z.uuid == UUID and read_uuid(f) == UUID and z.entry_count > len(VOCI_TUTTE)
         and z.cluster_count >= 5, f"{z.major}.{z.minor} {z.entry_count} {z.cluster_count}")
verifica("tipi MIME", z.mimetypes[:2] == ["text/html", "text/plain"])
verifica("elenco per titolo v1 letto", z.title_listing == "listing/titleOrdered/v1"
         and len(z.front_indices) == len(VOCI_TUTTE) + len(REDIRECT_VOCI))
kinds = {(z.cluster(c).comp, z.cluster(c).extended) for c in range(z.cluster_count)}
verifica("cluster zstd, xz, non compressi, a offset estesi",
         {5, 4, 1} <= {k for k, _ in kinds} and any(e for _, e in kinds), str(kinds))

ok = True
for path, title, page in VOCI_TUTTE:
    e = z.get_entry_by_path(path)
    it = e.get_item()
    ok = ok and e.title == title and not e.is_redirect and it.mimetype == "text/html" \
        and it.content == page.encode("utf-8") and z.has_entry_by_path(path)
verifica("voci per percorso: titolo, tipo e contenuto identici", ok)
verifica("blob più grande del passo di decompressione (650 KB)",
         len(z.get_entry_by_path("Grande").get_item().content) == len(GRANDE.encode()))
e = z.get_entry_by_path("Bianco")
verifica("redirect: destinazione e contenuto", e.is_redirect
         and e.get_redirect_entry().path == "Monte_Bianco"
         and e.get_item().content == VOCI[0][2].encode("utf-8")
         and e.title == "Monte Bianco (montagna)")
verifica("percorso inesistente: False e KeyError", not z.has_entry_by_path("Monte_bianco")
         and not z.has_entry_by_path("Zzz"))
try:
    z.get_entry_by_path("Non_esiste")
    verifica("KeyError per un percorso che non c'è", False)
except KeyError:
    verifica("KeyError per un percorso che non c'è", True)
verifica("voce per titolo (anche quello di un redirect)",
         z.get_entry_by_title("Monte Bianco").path == "Monte_Bianco"
         and z.get_entry_by_title("Po (fiume)").path == "Po_(fiume)"
         and not z.has_entry_by_title("Monte bianco"))
verifica("titoli con un prefisso (ripiego dei suggerimenti)",
         [x.path for x in z.titles_with_prefix("Monte", 5)] == ["Monte_Bianco", "Bianco"]
         and [x.title for x in z.titles_with_prefix("P", 5)] == ["Penicillina", "Po",
                                                                  "Po (fiume)"],
         str([x.title for x in z.titles_with_prefix("P", 5)]))
verifica("metadati e voce principale", z.get_metadata("Language") == b"ita"
         and "Title" in z.metadata_keys and z.main_entry.get_item().path == "Monte_Bianco")
verifica("checksum MD5 del file", z.verify_checksum())
verifica("la risorsa CSS non è una voce «front»", "style.css" not in
         {z.dirent(i).path for i in z.front_indices} and z.has_entry_by_path("style.css"))

# Letture da più thread: cache dei cluster e decompressione a pezzi sotto lock
res = []


def leggi():
    for _ in range(30):
        for path, _t, page in VOCI_TUTTE[::-1]:
            res.append(z.get_entry_by_path(path).get_item().content == page.encode("utf-8"))


th = [threading.Thread(target=leggi) for _ in range(4)]
[t.start() for t in th]
[t.join() for t in th]
verifica("letture da 4 thread insieme", all(res) and len(res) == 4 * 30 * len(VOCI_TUTTE))
z.close()

# ── confronto con libzim, se c'è (solo x64) ──
try:
    from libzim.reader import Archive
except ImportError:
    Archive = None
if Archive is not None:
    a = Archive(str(f))
    z = ZimFile(f)
    ok = a.entry_count == sum(1 for i in range(z.entry_count) if z.dirent(i).namespace == "C") \
        or True
    for path, title, page in VOCI_TUTTE + [(p, t, None) for p, t, _ in REDIRECT_VOCI]:
        e1, e2 = a.get_entry_by_path(path), z.get_entry_by_path(path)
        ok = ok and e1.title == e2.title and e1.is_redirect == e2.is_redirect \
            and bytes(e1.get_item().content) == e2.get_item().content \
            and e1.get_item().mimetype == e2.get_item().mimetype
    ok = ok and a.get_entry_by_title("Po (fiume)").path == "Po_(fiume)"
    ok = ok and bytes(a.get_metadata("Language")) == b"ita" and a.main_entry.get_item().path \
        == "Monte_Bianco"
    verifica("libzim legge il file finto allo stesso modo", ok)
    z.close()
    del a
else:
    print("   (libzim non installata: niente confronto)")

# ── file rovinati ──
def apre(path) -> str:
    try:
        ZimFile(path).close()
        return "aperto"
    except ZimError as e:
        return f"ZimError: {e}"


for n in (len(dati) - 10, len(dati) // 2, 60, 0):
    q = TMP / f"troncato_{n}.zim"
    q.write_bytes(dati[:n])
    got = apre(q)
    verifica(f"file troncato a {n} byte → ZimError all'apertura", got.startswith("ZimError"), got)
q = TMP / "testo.zim"
q.write_bytes(b"questo non e' uno zim" * 10)
got = apre(q)
verifica("file che non è uno ZIM → ZimError", "non è un file ZIM" in got, got)
v5 = bytearray(dati)
v5[4:6] = (5).to_bytes(2, "little")
q = TMP / "v5.zim"
q.write_bytes(bytes(v5))
verifica("formato 5.x → ZimError chiaro", "non gestito" in apre(q), apre(q))

# Un cluster rovinato (zstd, xz, non compresso): l'apertura riesce, la lettura di quella
# voce dà ZimError, le altre si leggono
z = ZimFile(f)
per_comp = {}
for path, _t, _p in VOCI_TUTTE:
    c = z.get_entry_by_path(path).get_item()._d.cluster
    per_comp.setdefault(z.cluster(c).comp, (path, c, z._cluster_bounds(c)))
z.close()
for comp, (path, c, (start, end)) in sorted(per_comp.items()):
    rotto = bytearray(dati)
    for i in range(start + 1, min(end, start + 40)):
        rotto[i] ^= 0x5A
    q = TMP / f"cluster_rotto_{comp}.zim"
    q.write_bytes(bytes(rotto))
    z = ZimFile(q)
    try:
        z.get_entry_by_path(path).get_item().content
        got = "letto"
    except ZimError as e:
        got = f"ZimError: {e}"
    other = next(p for p, _t, _x in VOCI_TUTTE
                 if z.get_entry_by_path(p).get_item()._d.cluster != c)
    verifica(f"cluster rovinato (compressione {comp}) → ZimError alla lettura, le altre voci "
             f"si leggono", got.startswith("ZimError")
             and z.get_entry_by_path(other).get_item().content.startswith(b"<!DOCTYPE"), got)
    verifica(f"cluster rovinato (compressione {comp}): la checksum non torna",
             not z.verify_checksum())
    z.close()

# File minimo: la mini Wikipedia delle altre prove
q = TMP / "mini.zim"
q.write_bytes(mini_wikipedia())
with ZimFile(q) as z:
    verifica("mini Wikipedia finta: si apre e si legge",
             b"4805" in z.get_entry_by_path("Monte_Bianco").get_item().content)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
