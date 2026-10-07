"""
Il telefono come satellite: una web app (PWA) servita dal server degli schermi (03/10/2026,
docs/ricerche/2026-10-03-webapp-telefono.md).

La pagina /telefono fa nel browser quello che il satellite fa sul portatile: microfono, Silero
VAD e la wake word «Calliope» (gli stessi modelli ONNX, con onnxruntime-web in WebAssembly,
caricati da qui: niente CDN), riproduzione della voce di Piper a pezzi con Web Audio,
interruzione locale («Calliope, basta»). Parla lo **stesso protocollo** del satellite
(calliope/satellite/protocollo.py) su un WebSocket di questo server: `PonteWs` è una
facciata sincrona del WebSocket di Starlette con l'API di `websockets.sync`, così
`ServerSatelliti._gestisci` (abbinamento a codice, token, sessione, prendi/lascia) è lo stesso
codice. Il telefono è un satellite come gli altri: si abbina da terminale
(`calliope satellite --abbina <codice> --stanza telefono --personale Dario`), il token sta solo
nel browser (sul server lo SHA-256), e le schede arrivano con l'SSE degli schermi, con il
token di schermo che il satellite riceve sulla sua connessione.

Indirizzi (sullo stesso host e porta della pagina degli schermi):
  GET /telefono/                 la pagina (CSP con 'wasm-unsafe-eval', nient'altro da fuori)
  GET /telefono/<file>           script, foglio di stile, AudioWorklet, service worker,
                                 manifest, icone
  GET /telefono/ort/<file>       onnxruntime-web (cartella telefono_web), gzip se accettato
  GET /telefono/modelli/<nome>   VAD e wake word: solo con il token di un satellite abbinato
  GET /telefono/calliope-ca.crt  la CA di casa da installare sul telefono (tls.py)
  GET /telefono/api/stato        cosa c'è e cosa manca (nessun segreto)
  POST /telefono/api/diagnostica «Prova il microfono»: due registrazioni brevi dal telefono
                                 (token del satellite, solo telefoni personali), salvate come
                                 WAV con scadenza e riassunte (telefono_diagnostica.py)
  WS  /telefono/ws/abbina        abbinamento, come /abbina dei satelliti
  WS  /telefono/ws/sessione      il protocollo del satellite, come /satellite

Il WebSocket dei satelliti (porta 8771) rifiuta i browser (Origin presente, 02/10): il
telefono entra solo da qui, con l'Origin della pagina stessa.
"""

import asyncio
import gzip
import hashlib
import json
import queue
import threading
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import (FileResponse, JSONResponse, PlainTextResponse,
                                 RedirectResponse, Response)
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket

PAGINA = Path(__file__).resolve().parent / "pagina" / "telefono"

# onnxruntime-web 1.30.0 (npm, 30/09/2026): solo WebAssembly, un thread, nessun worker
ORT_VERSIONE = "1.30.0"
ORT_FILE = ("ort.wasm.min.mjs", "ort-wasm-simd-threaded.mjs", "ort-wasm-simd-threaded.wasm")

# File della pagina: nome → tipo
FILE_PAGINA = {
    "telefono.js": "text/javascript; charset=utf-8",
    "voce.js": "text/javascript; charset=utf-8",
    "microfono.js": "text/javascript; charset=utf-8",
    "schermo-acceso.js": "text/javascript; charset=utf-8",
    "sw.js": "text/javascript; charset=utf-8",
    "telefono.css": "text/css; charset=utf-8",
    "manifest.webmanifest": "application/manifest+json",
    "icona.svg": "image/svg+xml",
    "icona-180.png": "image/png",
    "icona-192.png": "image/png",
    "icona-512.png": "image/png",
}
TIPI = {".mjs": "text/javascript; charset=utf-8", ".wasm": "application/wasm",
        ".onnx": "application/octet-stream"}

DIAG_PER_10_MIN = 6          # prove del microfono ogni 10 minuti, per telefono

_BASE = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
         "X-Frame-Options": "DENY"}


def csp(host: str) -> str:
    """CSP della pagina del telefono: tutto da qui. 'wasm-unsafe-eval' è l'unica eccezione
    (compilare il WebAssembly di onnxruntime-web: niente eval di JavaScript). Il WebSocket è
    scritto anche per esteso: Safari prima della 15.4 non lo comprendeva in 'self'."""
    ws = f" wss://{host} ws://{host}" if host else ""
    return ("default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; "
            "style-src 'self'; img-src 'self' data:; media-src 'self' blob:; "
            f"connect-src 'self'{ws}; manifest-src 'self'; frame-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'none'")


def cartella_ort(cfg) -> Path:
    return Path(str(getattr(cfg, "telefono_web", "") or "models/web"))


def file_modelli(cfg) -> dict[str, Path | None]:
    """I quattro modelli della pagina: Silero VAD (quello del pacchetto silero-vad, o
    vad_modello) e la catena della wake word accanto a wake_model."""
    from ..vad import modello_onnx
    wake = Path(str(getattr(cfg, "wake_model", "") or "wakeword/modelli/calliope.onnx"))
    if not wake.is_file() and (wake.parent / "calliope.onnx").is_file():
        # Wake word cambiata senza il suo modello (modalità startrek senza computer.onnx,
        # 04/10): il telefono resta sul nome, che il server accetta (wake_anche_nome)
        wake = wake.parent / "calliope.onnx"
    out = {"vad": modello_onnx(getattr(cfg, "vad_modello", None) or None),
           "melspectrogram": wake.parent / "melspectrogram.onnx",
           "embedding_model": wake.parent / "embedding_model.onnx",
           "calliope": wake}
    # Il classificatore del nome accanto a quello della parola della modalità (05/10,
    # Config.wake_models: «Computer» e «Calliope» insieme)
    altri = [Path(m) for m in (getattr(cfg, "wake_models", None) or [])[1:]]
    if altri and altri[0].name != wake.name:
        out["nome"] = altri[0]
    return {k: (p if p is not None and Path(p).is_file() else None) for k, p in out.items()}


def stato(cfg, hub=None) -> dict:
    """Cosa serve alla web app e cosa manca: per la pagina (/telefono/api/stato), per
    python -m calliope.schermi e per il registro delle capacità. Nessun segreto."""
    ort = {n: (cartella_ort(cfg) / n).is_file() for n in ORT_FILE}
    fm = file_modelli(cfg)
    modelli = {k: p is not None for k, p in fm.items()}
    # Una «versione» per modello (data e dimensione): la pagina la mette nell'URL, così la
    # sua cache si rinnova quando il file cambia
    versioni = {k: _etag(p).strip('"')[:12] for k, p in fm.items() if p is not None}
    satelliti = getattr(hub, "satelliti", None) if hub is not None else None
    manca = []
    if not getattr(cfg, "telefono_enabled", True):
        manca.append("spento (telefono_enabled: false)")
    if getattr(cfg, "audio_modo", "locale") != "satellite":
        manca.append("Calliope usa l'audio di questo computer (audio_modo: locale): il "
                     "telefono serve con Calliope sul server (audio_modo: satellite)")
    elif hub is not None and satelliti is None:
        manca.append("il server dei satelliti non è acceso")
    if not all(ort.values()):
        manca.append("manca onnxruntime-web: python -m calliope.stato --installa telefono")
    if not (modelli["melspectrogram"] and modelli["embedding_model"]):
        manca.append("mancano i modelli generici della wake word: python -m calliope.stato "
                     "--installa telefono")
    if not modelli["calliope"]:
        manca.append("manca il modello della wake word «Calliope» (wakeword/modelli/"
                     "calliope.onnx): copialo dal portatile")
    if not modelli["vad"]:
        manca.append("manca Silero VAD (pacchetto silero-vad o vad_modello)")
    from .tls import file_ca
    return {"pronto": not manca, "manca": manca, "ort": ort, "ort_versione": ORT_VERSIONE,
            "modelli": modelli, "versioni": versioni, "ca": file_ca(cfg) is not None,
            "nome": getattr(cfg, "name", "Calliope")}


# ───────────────────────────── file compressi ─────────────────────────────
class _Gzip:
    """Il gzip dei file grandi (il WebAssembly di onnxruntime: 14 MB → 3,7 MB), fatto una
    volta e tenuto in memoria finché il file non cambia."""

    def __init__(self):
        self._cache: dict[str, tuple[float, int, bytes]] = {}
        self._lock = threading.Lock()

    def dati(self, path: Path) -> bytes:
        st = path.stat()
        k = str(path)
        with self._lock:
            c = self._cache.get(k)
            if c is not None and c[0] == st.st_mtime and c[1] == st.st_size:
                return c[2]
        z = gzip.compress(path.read_bytes(), compresslevel=6, mtime=0)
        with self._lock:
            self._cache[k] = (st.st_mtime, st.st_size, z)
        return z


def _etag(path: Path) -> str:
    st = path.stat()
    return '"' + hashlib.sha1(f"{path.name}:{st.st_mtime_ns}:{st.st_size}".encode()
                              ).hexdigest()[:20] + '"'


async def _file(request: Request, path: Path, tipo: str, gz: _Gzip, cache: str):
    """Un file statico, compresso se il browser lo accetta e se conviene (> 64 kB)."""
    etag = _etag(path)
    h = {"Cache-Control": cache, "ETag": etag, "Vary": "Accept-Encoding", **_BASE}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=h)
    if "gzip" in request.headers.get("accept-encoding", "") and path.stat().st_size > 65536:
        dati = await asyncio.to_thread(gz.dati, path)
        return Response(dati, media_type=tipo, headers={**h, "Content-Encoding": "gzip"})
    return FileResponse(path, media_type=tipo, headers=h)


# ───────────────────────────── ponte WebSocket ─────────────────────────────
_FINE = object()


class PonteWs:
    """L'API sincrona di `websockets.sync` (recv, send, close, ping, request.path,
    protocol.close_rcvd, latency) sopra un WebSocket di Starlette: il codice dei satelliti
    gira in un suo thread come per una connessione del satellite vero. Le uscite passano al
    ciclo asyncio con call_soon_threadsafe e non aspettano mai."""

    telefono = True        # il canale nel registro dei turni (07/10, pause: calliope/pause.py)

    def __init__(self, loop: asyncio.AbstractEventLoop, path: str):
        self.loop = loop
        self.request = SimpleNamespace(path=path, headers={})
        self.protocol = SimpleNamespace(close_rcvd=True)
        self.latency = 0.0
        self.entrata: queue.Queue = queue.Queue()
        self.uscita: asyncio.Queue = asyncio.Queue()
        self.chiuso = False
        self.codice_chiusura = None

    @staticmethod
    def _chiusa(codice=1006, motivo=""):
        from websockets.exceptions import ConnectionClosed
        from websockets.frames import Close
        return ConnectionClosed(Close(codice, motivo), None)

    def recv(self, timeout: float | None = None):
        try:
            item = self.entrata.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError("niente dal telefono") from None
        if item is _FINE:
            self.entrata.put(_FINE)                # anche le chiamate dopo lo sanno
            raise self._chiusa(self.codice_chiusura or 1006)
        return item

    def send(self, dati):
        if self.chiuso:
            raise self._chiusa(self.codice_chiusura or 1006)
        try:
            self.loop.call_soon_threadsafe(self.uscita.put_nowait, dati)
        except RuntimeError:                       # ciclo chiuso: server fermato
            self.chiuso = True
            raise self._chiusa() from None

    def close(self, code: int = 1000, reason: str = ""):
        if self.chiuso:
            return
        self.chiuso = True
        try:
            self.loop.call_soon_threadsafe(self.uscita.put_nowait, (_FINE, code, reason))
        except RuntimeError:
            pass

    def ping(self):
        """Il keepalive lo fa uvicorn (ping ogni 20 s)."""


def _origine_ok(ws: WebSocket) -> bool:
    """Solo la pagina stessa: Origin con lo stesso host e porta dell'intestazione Host."""
    origin = ws.headers.get("origin", "")
    host = ws.headers.get("host", "")
    if not origin or not host:
        return False
    u = urlsplit(origin)
    return u.scheme in ("https", "http") and u.netloc.lower() == host.lower()


async def _ponte(websocket: WebSocket, hub, percorso_satellite: str):
    srv = getattr(hub, "satelliti", None)
    if not _origine_ok(websocket):
        await websocket.close(1008)
        return
    await websocket.accept()
    if srv is None or not getattr(hub.cfg, "telefono_enabled", True):
        motivo = ("la voce dal telefono è spenta (telefono_enabled)"
                  if not getattr(hub.cfg, "telefono_enabled", True) else
                  "Calliope non usa i satelliti (audio_modo: locale): la voce dal telefono "
                  "serve con Calliope sul server")
        await websocket.send_text(json.dumps({"tipo": "errore", "motivo": motivo},
                                             ensure_ascii=False))
        await websocket.close(4503)
        return
    loop = asyncio.get_running_loop()
    ponte = PonteWs(loop, percorso_satellite)

    def lavora():
        try:
            srv._gestisci(ponte)
        finally:
            ponte.close(1000, "")

    threading.Thread(target=lavora, name="telefono", daemon=True).start()

    async def manda():
        while True:
            item = await ponte.uscita.get()
            if isinstance(item, tuple) and item and item[0] is _FINE:
                try:
                    await websocket.close(item[1], item[2] or None)
                except Exception:  # noqa: BLE001 — già chiusa dall'altra parte
                    pass
                return
            if isinstance(item, str):
                await websocket.send_text(item)
            else:
                await websocket.send_bytes(bytes(item))

    mittente = asyncio.create_task(manda())
    try:
        while True:
            ricevi = asyncio.ensure_future(websocket.receive())
            fatti, _ = await asyncio.wait({ricevi, mittente},
                                          return_when=asyncio.FIRST_COMPLETED)
            if mittente in fatti:
                ricevi.cancel()
                break
            m = ricevi.result()
            if m["type"] == "websocket.disconnect":
                codice = int(m.get("code") or 1006)
                ponte.codice_chiusura = codice
                # Senza saluto di chiusura (rete caduta, telefono bloccato): come il satellite
                ponte.protocol.close_rcvd = None if codice in (1005, 1006) else True
                break
            dati = m.get("text")
            ponte.entrata.put(dati if dati is not None else (m.get("bytes") or b""))
    except Exception:  # noqa: BLE001 — connessione caduta a metà: la vede il thread
        pass
    finally:
        ponte.chiuso = True
        ponte.entrata.put(_FINE)
        if not mittente.done():
            mittente.cancel()


# ───────────────────────────── rotte ─────────────────────────────
def rotte(hub) -> list:
    cfg = hub.cfg
    gz = _Gzip()

    def bearer(request: Request) -> str:
        a = request.headers.get("authorization", "")
        return a[7:].strip() if a.lower().startswith("bearer ") else ""

    async def radice(request: Request):
        return RedirectResponse("/telefono/", status_code=308)

    async def pagina(request: Request):
        host = request.headers.get("host", "")
        return FileResponse(PAGINA / "index.html", media_type="text/html; charset=utf-8",
                            headers={"Cache-Control": "no-cache", **_BASE,
                                     "Content-Security-Policy": csp(host),
                                     "Permissions-Policy":
                                         "microphone=(self), screen-wake-lock=(self), camera=()"})

    async def statico(request: Request):
        nome = request.path_params["nome"]
        tipo = FILE_PAGINA.get(nome)
        p = PAGINA / nome
        if tipo is None or not p.is_file():
            return PlainTextResponse("non trovato", status_code=404, headers=_BASE)
        h = {"Cache-Control": "no-cache", **_BASE}
        if nome == "sw.js":
            h["Service-Worker-Allowed"] = "/telefono/"
        return FileResponse(p, media_type=tipo, headers=h)

    async def ort(request: Request):
        nome = request.path_params["nome"]
        p = cartella_ort(cfg) / nome
        if nome not in ORT_FILE or not p.is_file():
            return PlainTextResponse("onnxruntime-web non installato: python -m calliope.stato "
                                     "--installa telefono", status_code=404, headers=_BASE)
        return await _file(request, p, TIPI[Path(nome).suffix], gz,
                           "public, max-age=604800")

    async def modello(request: Request):
        nome = request.path_params["nome"]
        srv = getattr(hub, "satelliti", None)
        if srv is None or srv.archivio.per_token(bearer(request)) is None:
            # I modelli (la wake word è addestrata con dati non commerciali) vanno solo ai
            # telefoni abbinati
            return PlainTextResponse("solo per i satelliti abbinati", status_code=401,
                                     headers={"Cache-Control": "no-store", **_BASE})
        p = file_modelli(cfg).get(nome.removesuffix(".onnx"))
        if p is None:
            return PlainTextResponse("modello mancante", status_code=404, headers=_BASE)
        return await _file(request, p, TIPI[".onnx"], gz, "private, max-age=86400")

    async def ca(request: Request):
        from .tls import file_ca
        p = file_ca(cfg)
        if p is None:
            return PlainTextResponse("Nessuna CA di casa: sul server python -m calliope.schermi "
                                     "--certificato", status_code=404, headers=_BASE)
        return FileResponse(p, media_type="application/x-x509-ca-cert",
                            filename="calliope-ca.crt", headers={"Cache-Control": "no-cache",
                                                                 **_BASE})

    async def api_stato(request: Request):
        return JSONResponse(stato(cfg, hub), headers={"Cache-Control": "no-store", **_BASE})

    invii_diag: dict[int, list[float]] = {}
    lock_diag = threading.Lock()

    async def rifiuta(request: Request, corpo: dict, codice: int, h: dict, limite: int):
        """Una risposta d'errore dopo aver letto (e buttato) il corpo, fino a `limite` byte e
        per al più 5 s (03/10). Senza, la connessione si chiudeva con i dati del telefono
        ancora da leggere: su Windows è un RST, e il telefono vedeva un errore di rete invece
        del 401 (prova_telefono_audio nell'hook; sonda sotto carico con 64 KB: 25 errori di
        rete su 4 500 richieste, 0 su 7 200 leggendo il corpo)."""
        async def scarta():
            letti = 0
            async for pezzo in request.stream():
                letti += len(pezzo)
                if letti > limite:
                    return
        try:
            if int(request.headers.get("content-length") or 0) <= limite:
                await asyncio.wait_for(scarta(), 5.0)
        except (ValueError, asyncio.TimeoutError, OSError):
            pass
        except Exception:  # noqa: BLE001 — il client se n'è andato: si risponde comunque
            pass
        return JSONResponse(corpo, status_code=codice, headers=h)

    async def diagnostica(request: Request):
        """«Prova il microfono»: il token del satellite (come per i modelli), e solo da un
        telefono personale: le registrazioni sono la voce del suo proprietario. Al massimo
        DIAG_PER_10_MIN prove ogni 10 minuti e MAX_BYTE per prova."""
        import time

        from . import telefono_diagnostica as D
        h = {"Cache-Control": "no-store", **_BASE}
        srv = getattr(hub, "satelliti", None)
        sat = srv.archivio.per_token(bearer(request)) if srv is not None else None
        if sat is None:
            return await rifiuta(request, {"errore": "telefono non abbinato"}, 401, h, D.MAX_BYTE)
        if not sat.get("proprietario"):
            return await rifiuta(request, {"errore": "la prova del microfono è solo per i "
                                                     "telefoni personali (abbinati con "
                                                     "--personale)"}, 403, h, D.MAX_BYTE)
        ora = time.monotonic()
        with lock_diag:
            fatte = [t for t in invii_diag.get(sat["id"], []) if ora - t < 600]
            if len(fatte) >= DIAG_PER_10_MIN:
                invii_diag[sat["id"]] = fatte
                troppe = True
            else:
                invii_diag[sat["id"]] = fatte + [ora]
                troppe = False
        if troppe:
            return await rifiuta(request, {"errore": "troppe prove: aspetta qualche minuto"}, 429,
                                 h, D.MAX_BYTE)
        try:
            if int(request.headers.get("content-length") or 0) > D.MAX_BYTE:
                return JSONResponse({"errore": "troppo grande"}, status_code=413, headers=h)
        except ValueError:
            return JSONResponse({"errore": "lunghezza non valida"}, status_code=400, headers=h)
        dati = bytearray()
        async for pezzo in request.stream():
            dati += pezzo
            if len(dati) > D.MAX_BYTE:
                return JSONResponse({"errore": "troppo grande"}, status_code=413, headers=h)
        try:
            esito = await asyncio.to_thread(D.analizza, cfg, bytes(dati), str(sat.get("nome") or ""),
                                            sat.get("proprietario"))
        except D.ErroreDiagnostica as e:
            return JSONResponse({"errore": str(e)}, status_code=400, headers=h)
        log = getattr(hub, "log", None)
        if callable(log):
            log(f"   [TELEFONO] prova del microfono di «{sat.get('nome')}»: {esito['cartella']}")
        return JSONResponse(esito, headers=h)

    async def ws_abbina(websocket: WebSocket):
        from ..satellite import protocollo as P
        await _ponte(websocket, hub, P.PERCORSO_ABBINA)

    async def ws_sessione(websocket: WebSocket):
        from ..satellite import protocollo as P
        await _ponte(websocket, hub, P.PERCORSO_AUDIO)

    return [
        Route("/telefono", radice),
        Route("/telefono/", pagina),
        Route("/telefono/api/stato", api_stato),
        Route("/telefono/api/diagnostica", diagnostica, methods=["POST"]),
        Route("/telefono/calliope-ca.crt", ca),
        Route("/telefono/ort/{nome}", ort),
        Route("/telefono/modelli/{nome}", modello),
        Route("/telefono/{nome}", statico),
        WebSocketRoute("/telefono/ws/abbina", ws_abbina),
        WebSocketRoute("/telefono/ws/sessione", ws_sessione),
    ]


def ws_disponibile() -> bool:
    """uvicorn serve i WebSocket con websockets (già dipendenza dei satelliti), in modalità
    sans-I/O: niente asyncio di websockets, niente codice nativo nuovo."""
    from .. import capacita
    return capacita.presente("websockets")


__all__ = ["PonteWs", "csp", "file_modelli", "rotte", "stato", "ws_disponibile"]
