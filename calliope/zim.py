"""
Lettore di file ZIM (Kiwix) in puro Python: solo libreria standard (01/10/2026).

Prende il posto di libzim, che non ha wheel per Windows su ARM (ricerca e misure in
docs/ricerche/2026-10-01-biblioteca-senza-libzim.md). Usa `struct`, `mmap`, `lzma` e
`compression.zstd` (Python 3.14, PEP 784; con Python più vecchi il pacchetto `zstandard`).
Sui 4 file della biblioteca dà le stesse voci e lo stesso HTML di libzim (600 voci su 600),
si apre in <1 ms (libzim ~100 ms) e legge una voce in 3–4 ms.

Copre quello che serve a calliope/biblioteca.py e a calliope/biblioteca_indice.py:
  - voce per percorso (ricerca binaria sulla lista dei percorsi) e per titolo (ricerca
    binaria su X/listing/titleOrdered/v1), redirect, metadati, voce principale;
  - contenuto dei blob, con cluster non compressi, xz, zstd e a offset estesi (64 bit);
  - `titles_with_prefix`, il ripiego di libzim per i suggerimenti senza Xapian;
  - scorrimento di tutti i dirent per costruire l'indice.
Niente Xapian: ricerca full-text e suggerimenti stanno nell'indice SQLite FTS5
(calliope/biblioteca_indice.py).

Formato: https://wiki.openzim.org/wiki/ZIM_file_format. Si leggono solo i file 6.x (namespace
nuovi: C contenuti, M metadati, W voci note, X indici), gli unici che Kiwix pubblica.

L'API ricalca quella di libzim usata dalla biblioteca (`has_entry_by_path`,
`get_entry_by_path`, `entry.is_redirect`, `get_redirect_entry`, `get_item().content`,
`mimetype`, `title`, `get_entry_by_title`, `get_metadata`): così il resto del codice non
cambia. Un file rovinato o troncato solleva `ZimError` (all'apertura se l'intestazione non
torna, alla lettura se è rovinato un cluster).
"""

from __future__ import annotations

import lzma
import mmap
import os
import struct
import threading
from array import array
from collections import OrderedDict

MAGIC = 72173914
HEADER_SIZE = 80
REDIRECT = 0xFFFF
LINKTARGET = 0xFFFE
DELETED = 0xFFFD
NO_PTR = 0xFFFFFFFFFFFFFFFF
TITLE_LISTING = "listing/titleOrdered/v1"

# Compressione dei cluster: 4 bit bassi del byte d'informazione
COMP_NONE = (0, 1)
COMP_XZ = 4
COMP_ZSTD = 5
EXTENDED = 0x10          # offset dei blob a 64 bit


class ZimError(Exception):
    """File che non è uno ZIM, troncato o rovinato."""


def _zstd_decompressor():
    """Decompressore zstd con `decompress(data, max_length)`, `eof` e `needs_input`, come
    quelli di lzma. Python 3.14 lo ha nella libreria standard (anche su ARM64)."""
    try:
        from compression import zstd
        return zstd.ZstdDecompressor()
    except ImportError:
        pass
    try:
        import zstandard
    except ImportError as e:
        raise ZimError("per i cluster zstd serve Python 3.14 o il pacchetto zstandard") from e

    class _Adapter:
        """`zstandard` decomprime tutto in una volta: niente lettura a pezzi."""
        needs_input = False

        def __init__(self):
            self._d = zstandard.ZstdDecompressor().decompressobj()
            self.eof = False

        def decompress(self, data, max_length=-1):
            out = self._d.decompress(data)
            self.eof = True
            return out
    return _Adapter()


class Dirent:
    """Una voce della directory: contenuto (cluster, blob), redirect o voce speciale."""
    __slots__ = ("index", "mime", "namespace", "path", "title", "cluster", "blob", "redirect")

    def __init__(self, index, mime, namespace, path, title, cluster, blob, redirect):
        self.index, self.mime, self.namespace = index, mime, namespace
        self.path, self.title = path, title
        self.cluster, self.blob, self.redirect = cluster, blob, redirect

    @property
    def is_redirect(self) -> bool:
        return self.mime == REDIRECT

    @property
    def is_content(self) -> bool:
        return self.mime < DELETED

    @property
    def shown_title(self) -> str:
        """Il titolo; se è vuoto vale il percorso (regola del formato)."""
        return self.title or self.path


class Entry:
    """Come libzim.reader.Entry, per quello che usa la biblioteca."""

    def __init__(self, zim: "ZimFile", d: Dirent):
        self._zim, self._d = zim, d

    @property
    def index(self) -> int:
        return self._d.index

    @property
    def path(self) -> str:
        return self._d.path

    @property
    def title(self) -> str:
        return self._d.shown_title

    @property
    def is_redirect(self) -> bool:
        return self._d.is_redirect

    def get_redirect_entry(self) -> "Entry":
        if not self._d.is_redirect:
            raise ZimError(f"{self._d.path} non è un redirect")
        return Entry(self._zim, self._zim.dirent(self._d.redirect))

    def get_item(self) -> "Item":
        d, hops = self._d, 0
        while d.is_redirect:
            if hops >= 10:
                raise ZimError(f"troppi redirect da {self._d.path}")
            d, hops = self._zim.dirent(d.redirect), hops + 1
        if not d.is_content:
            raise ZimError(f"{d.path} non ha contenuto")
        return Item(self._zim, d)


class Item:
    def __init__(self, zim: "ZimFile", d: Dirent):
        self._zim, self._d = zim, d

    @property
    def path(self) -> str:
        return self._d.path

    @property
    def title(self) -> str:
        return self._d.shown_title

    @property
    def mimetype(self) -> str:
        return self._zim.mimetypes[self._d.mime]

    @property
    def content(self) -> bytes:
        return self._zim.blob(self._d.cluster, self._d.blob)

    @property
    def size(self) -> int:
        return len(self.content)


class ZimFile:
    """Un file ZIM aperto in sola lettura con mmap. Thread-safe: la cache dei cluster e la
    decompressione a pezzi sono sotto un lock (le letture sono di pochi millisecondi)."""

    def __init__(self, path: str | os.PathLike, cluster_cache: int = 8,
                 dirent_cache: int = 20_000):
        self.path = os.fspath(path)
        self._f = open(self.path, "rb")
        try:
            self.size = os.fstat(self._f.fileno()).st_size
            if self.size < HEADER_SIZE:
                raise ZimError("file troppo corto per essere uno ZIM")
            self._mm = mmap.mmap(self._f.fileno(), 0, access=mmap.ACCESS_READ)
        except BaseException:
            self._f.close()
            raise
        self._views: list[memoryview] = []
        self._lock = threading.RLock()
        self._cluster_cache: OrderedDict[int, _Cluster] = OrderedDict()
        self._cache_size = 0                 # durante l'apertura niente cache
        self._dirent_cache: dict[int, Dirent] = {}
        self._dirent_max = 0
        self._title_idx: array | memoryview = array("I")
        try:
            self._read_header()
        except BaseException:
            self.close()
            raise
        self._cache_size = max(0, cluster_cache)
        self._dirent_max = dirent_cache

    # ── intestazione ──
    def _read_header(self):
        mm = self._mm
        magic, self.major, self.minor = struct.unpack_from("<IHH", mm, 0)
        if magic != MAGIC:
            raise ZimError("non è un file ZIM")
        if self.major != 6:
            raise ZimError(f"formato ZIM {self.major}.{self.minor} non gestito (serve il 6.x)")
        self.uuid = bytes(mm[8:24])
        self.entry_count, self.cluster_count = struct.unpack_from("<II", mm, 24)
        (self.path_ptr_pos, self.title_ptr_pos, self.cluster_ptr_pos,
         self.mime_list_pos) = struct.unpack_from("<QQQQ", mm, 32)
        self.main_page, self.layout_page = struct.unpack_from("<II", mm, 64)
        self.checksum_pos = struct.unpack_from("<Q", mm, 72)[0]
        # Un file troncato (download interrotto, disco pieno) si riconosce qui: le liste
        # dei puntatori e la checksum finale devono stare dentro il file
        if (self.checksum_pos + 16 > self.size
                or self.path_ptr_pos + 8 * self.entry_count > self.checksum_pos
                or self.cluster_ptr_pos + 8 * self.cluster_count > self.checksum_pos
                or self.mime_list_pos >= self.checksum_pos):
            raise ZimError("file ZIM troncato o rovinato")
        # Tipi MIME: stringhe terminate da zero, chiuse da una stringa vuota
        self.mimetypes: list[str] = []
        pos = self.mime_list_pos
        while True:
            end = mm.find(b"\0", pos, self.checksum_pos)
            if end < 0:
                raise ZimError("elenco dei tipi MIME rovinato")
            if end == pos:
                break
            self.mimetypes.append(mm[pos:end].decode("utf-8", "replace"))
            pos = end + 1
        self._cluster_ptr = array("Q")
        self._cluster_ptr.frombytes(mm[self.cluster_ptr_pos:
                                       self.cluster_ptr_pos + 8 * self.cluster_count])
        if array("Q", [1]).tobytes() != struct.pack("<Q", 1):
            self._cluster_ptr.byteswap()                  # macchina big-endian
        # Elenco per titolo: dalla 6.1 sta in X/listing/titleOrdered/v1 (solo le voci
        # «front»: articoli e loro redirect); nei file vecchi nell'intestazione
        self.title_listing = None
        i = self._find_path_index("X", TITLE_LISTING)
        if i is not None:
            d = self._read_dirent(i)
            if d.is_content:
                view = self.blob_view(d.cluster, d.blob)
                if len(view) % 4 == 0 and struct.pack("<I", 1) == array("I", [1]).tobytes():
                    self._title_idx = view.cast("B").cast("I")   # niente copia
                    self._views.append(self._title_idx)
                else:
                    self._title_idx = array("I", bytes(view))
                    if struct.pack("<I", 1) != array("I", [1]).tobytes():
                        self._title_idx.byteswap()
                self.title_listing = TITLE_LISTING
        elif self.title_ptr_pos != NO_PTR and self.title_ptr_pos + 4 * self.entry_count \
                <= self.checksum_pos:
            self._title_idx = array("I")
            self._title_idx.frombytes(mm[self.title_ptr_pos:
                                         self.title_ptr_pos + 4 * self.entry_count])
            self.title_listing = "header"

    def close(self):
        with self._lock:
            self._cluster_cache.clear()
            for v in self._views:
                v.release()
            self._views.clear()
            self._title_idx = array("I")
            try:
                self._mm.close()
            except (BufferError, ValueError):
                pass
            self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ── dirent ──
    def _path_ptr(self, i: int) -> int:
        if not 0 <= i < self.entry_count:
            raise ZimError(f"voce {i} fuori dal file")
        off = struct.unpack_from("<Q", self._mm, self.path_ptr_pos + 8 * i)[0]
        if off + 8 > self.checksum_pos:
            raise ZimError("puntatore a una voce fuori dal file")
        return off

    def _read_dirent(self, i: int) -> Dirent:
        mm = self._mm
        off = self._path_ptr(i)
        mime, _plen, ns = struct.unpack_from("<HBc", mm, off)
        ns = ns.decode("latin-1")
        if mime == REDIRECT:
            redirect = struct.unpack_from("<I", mm, off + 8)[0]
            cluster = blob = None
            pos = off + 12
        elif mime in (LINKTARGET, DELETED):
            cluster = blob = redirect = None
            pos = off + 8
        else:
            cluster, blob = struct.unpack_from("<II", mm, off + 8)
            redirect = None
            pos = off + 16
        end = mm.find(b"\0", pos, self.checksum_pos)
        end2 = mm.find(b"\0", end + 1, self.checksum_pos) if end >= 0 else -1
        if end2 < 0:
            raise ZimError("voce della directory rovinata")
        path = mm[pos:end].decode("utf-8", "replace")
        title = mm[end + 1:end2].decode("utf-8", "replace")
        return Dirent(i, mime, ns, path, title, cluster, blob, redirect)

    def dirent(self, i: int) -> Dirent:
        d = self._dirent_cache.get(i)
        if d is None:
            d = self._read_dirent(i)
            if len(self._dirent_cache) >= self._dirent_max:
                self._dirent_cache.clear()
            if self._dirent_max:
                self._dirent_cache[i] = d
        return d

    def _key_at(self, i: int) -> bytes:
        """Chiave d'ordinamento della lista dei percorsi: namespace + percorso, in byte."""
        mm = self._mm
        off = self._path_ptr(i)
        mime = struct.unpack_from("<H", mm, off)[0]
        pos = off + (12 if mime == REDIRECT else 8 if mime in (LINKTARGET, DELETED) else 16)
        end = mm.find(b"\0", pos, self.checksum_pos)
        if end < 0:
            raise ZimError("voce della directory rovinata")
        return mm[off + 3:off + 4] + mm[pos:end]

    def _lower_bound(self, key: bytes) -> int:
        lo, hi = 0, self.entry_count
        while lo < hi:
            mid = (lo + hi) // 2
            if self._key_at(mid) < key:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def _find_path_index(self, ns: str, path: str) -> int | None:
        key = ns.encode("latin-1") + path.encode("utf-8")
        i = self._lower_bound(key)
        if i < self.entry_count and self._key_at(i) == key:
            return i
        return None

    # ── API in stile libzim ──
    def has_entry_by_path(self, path: str) -> bool:
        return self._find_path_index("C", path) is not None

    def get_entry_by_path(self, path: str) -> Entry:
        i = self._find_path_index("C", path)
        if i is None:
            raise KeyError(path)
        return Entry(self, self.dirent(i))

    def _title_key(self, j: int) -> bytes:
        d = self.dirent(self._title_idx[j])
        return d.namespace.encode("latin-1") + d.shown_title.encode("utf-8")

    def _title_lower_bound(self, key: bytes) -> int:
        lo, hi = 0, len(self._title_idx)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._title_key(mid) < key:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def has_entry_by_title(self, title: str) -> bool:
        try:
            self.get_entry_by_title(title)
            return True
        except KeyError:
            return False

    def get_entry_by_title(self, title: str) -> Entry:
        key = b"C" + title.encode("utf-8")
        j = self._title_lower_bound(key)
        if j < len(self._title_idx) and self._title_key(j) == key:
            return Entry(self, self.dirent(self._title_idx[j]))
        raise KeyError(title)

    def titles_with_prefix(self, prefix: str, n: int = 10) -> list[Entry]:
        """Voci il cui titolo comincia con `prefix`, sensibile alle maiuscole come l'ordine
        dei byte: il ripiego di libzim per i suggerimenti quando manca l'indice."""
        key = b"C" + prefix.encode("utf-8")
        j = self._title_lower_bound(key)
        out = []
        while j < len(self._title_idx) and len(out) < n:
            if not self._title_key(j).startswith(key):
                break
            out.append(Entry(self, self.dirent(self._title_idx[j])))
            j += 1
        return out

    @property
    def front_indices(self):
        """Indici dei dirent «front» (articoli e loro redirect), in ordine di titolo."""
        return self._title_idx

    def get_metadata(self, name: str) -> bytes:
        i = self._find_path_index("M", name)
        if i is None:
            raise KeyError(name)
        d = self.dirent(i)
        if not d.is_content:
            raise KeyError(name)
        return self.blob(d.cluster, d.blob)

    @property
    def metadata_keys(self) -> list[str]:
        i = self._lower_bound(b"M")
        out = []
        while i < self.entry_count:
            d = self.dirent(i)
            if d.namespace != "M":
                break
            out.append(d.path)
            i += 1
        return out

    @property
    def main_entry(self) -> Entry:
        i = self._find_path_index("W", "mainPage")
        d = self.dirent(i if i is not None else self.main_page)
        return Entry(self, d)

    def iter_dirents(self, start: int = 0, stop: int | None = None):
        """Tutti i dirent in ordine di percorso, senza riempire la cache (indice)."""
        stop = self.entry_count if stop is None else min(stop, self.entry_count)
        for i in range(start, stop):
            yield self._read_dirent(i)

    # ── cluster e blob ──
    def _cluster_bounds(self, c: int) -> tuple[int, int]:
        if not 0 <= c < self.cluster_count:
            raise ZimError(f"cluster {c} fuori dal file")
        start = self._cluster_ptr[c]
        end = self._cluster_ptr[c + 1] if c + 1 < self.cluster_count else self.checksum_pos
        if not start < end <= self.checksum_pos:
            raise ZimError(f"cluster {c} rovinato")
        return start, end

    def cluster(self, c: int) -> "_Cluster":
        with self._lock:
            cl = self._cluster_cache.get(c)
            if cl is not None:
                self._cluster_cache.move_to_end(c)
                return cl
            cl = _Cluster(self._mm, *self._cluster_bounds(c), lock=self._lock)
            if cl.compressed and self._cache_size:   # i non compressi si leggono dal mmap
                self._cluster_cache[c] = cl
                while len(self._cluster_cache) > self._cache_size:
                    self._cluster_cache.popitem(last=False)
            return cl

    def blob(self, c: int, b: int) -> bytes:
        return self.cluster(c).blob(b)

    def blob_view(self, c: int, b: int) -> memoryview:
        """Blob senza copia, per i cluster non compressi (indici, elenchi)."""
        return self.cluster(c).blob_view(b)

    def verify_checksum(self) -> bool:
        """MD5 di tutto il file fino a checksumPos. Lento: legge tutto il file."""
        import hashlib
        h = hashlib.md5()
        pos = 0
        while pos < self.checksum_pos:
            chunk = self._mm[pos:min(pos + (8 << 20), self.checksum_pos)]
            h.update(chunk)
            pos += len(chunk)
        return h.digest() == self._mm[self.checksum_pos:self.checksum_pos + 16]


class _Cluster:
    """Un cluster. Si decomprime a pezzi da 256 KB, solo fino al blob che serve: un cluster
    di Wikipedia è ~2 MB decompresso e decomprimerlo tutto costa ~4 ms."""

    STEP = 256 * 1024

    def __init__(self, mm, start: int, end: int, lock=None):
        self._lock = lock or threading.RLock()
        info = mm[start]
        self.comp = info & 0x0F
        self.extended = bool(info & EXTENDED)
        self.osz = 8 if self.extended else 4
        self._fmt1 = "<Q" if self.extended else "<I"
        self.compressed = self.comp not in COMP_NONE
        self._mm, self._start, self._end = mm, start + 1, end
        if self.compressed:
            if self.comp == COMP_XZ:
                self._dec = lzma.LZMADecompressor()
            elif self.comp == COMP_ZSTD:
                self._dec = _zstd_decompressor()
            else:
                raise ZimError(f"compressione {self.comp} non gestita")
            self._raw = mm[start + 1:end]
            self._fed = False
            self._buf = bytearray()
            self._need(self.osz)
            first = struct.unpack_from(self._fmt1, self._buf, 0)[0]
        else:
            if self._start + self.osz > end:
                raise ZimError("cluster troncato")
            first = struct.unpack_from(self._fmt1, mm, self._start)[0]
        if first < self.osz or first % self.osz:
            raise ZimError("cluster rovinato")
        self.n = first // self.osz - 1          # numero di blob
        fmt = "<%d%s" % (self.n + 1, "Q" if self.extended else "I")
        if self.compressed:
            self._need(first)
            self.offsets = struct.unpack_from(fmt, self._buf, 0)
        else:
            if self._start + first > end:
                raise ZimError("cluster troncato")
            self.offsets = struct.unpack_from(fmt, mm, self._start)
            if self._start + self.offsets[-1] > end:
                raise ZimError("cluster troncato")

    def _need(self, size: int):
        """Decomprime finché il buffer non ha almeno `size` byte."""
        try:
            while len(self._buf) < size:
                want = max(size - len(self._buf), self.STEP)
                if not self._fed:
                    chunk = self._dec.decompress(self._raw, max_length=want)
                    self._fed, self._raw = True, None
                elif self._dec.eof:
                    break
                else:
                    chunk = self._dec.decompress(b"", max_length=want)
                self._buf += chunk
                if not chunk and (self._dec.eof or self._dec.needs_input):
                    break
        except ZimError:
            raise
        except Exception as e:  # noqa: BLE001 — LZMAError, ZstdError: dati rovinati
            raise ZimError(f"cluster rovinato: {e}") from e
        if len(self._buf) < size:
            raise ZimError("cluster troncato")

    def _check(self, b: int):
        if not 0 <= b < self.n:
            raise ZimError(f"blob {b} fuori dal cluster")

    def blob(self, b: int) -> bytes:
        self._check(b)
        a, z = self.offsets[b], self.offsets[b + 1]
        if self.compressed:
            with self._lock:
                self._need(z)
                return bytes(self._buf[a:z])
        return self._mm[self._start + a:self._start + z]

    def blob_view(self, b: int) -> memoryview:
        self._check(b)
        a, z = self.offsets[b], self.offsets[b + 1]
        if self.compressed:
            with self._lock:
                self._need(z)
                return memoryview(bytes(self._buf[a:z]))
        return memoryview(self._mm)[self._start + a:self._start + z]

    def blobs(self):
        """Tutti i blob, in ordine (per l'indice: un cluster si legge una volta sola)."""
        for b in range(self.n):
            yield self.blob(b)


def read_uuid(path: str | os.PathLike) -> bytes:
    """L'uuid di un file ZIM dalla sola intestazione (per controllare l'indice, <1 ms)."""
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) < 24 or struct.unpack_from("<I", head, 0)[0] != MAGIC:
        raise ZimError("non è un file ZIM")
    return head[8:24]
