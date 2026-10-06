import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della web app del telefono (calliope/schermi/telefono.py, 03/10/2026), senza
browser: server degli schermi e dei satelliti veri su 127.0.0.1, client WebSocket finti.

- file della pagina: CSP (solo 'self' più 'wasm-unsafe-eval', niente 'unsafe-inline'),
  manifest della PWA con le icone, service worker, tipi; file sconosciuti e percorsi strani
  rifiutati;
- onnxruntime-web compresso con gzip, ETag e 304; modelli solo con il token di un satellite
  abbinato; CA di casa scaricabile solo se c'è; /telefono/api/stato;
- WebSocket: niente senza Origin, con un Origin diverso o con un Host sconosciuto;
  abbinamento a codice come un satellite (richiesta di schermo personale da confermare),
  sessione con lo stesso protocollo (ciao, benvenuto, pronto, ascolta, audio, frase_finita,
  schermo), token revocato → 4401;
- più satelliti: il portatile resta attivo quando arriva il telefono, «prendi» passa il posto
  al telefono (il portatile smette di ascoltare), «lascia» lo restituisce, il telefono che si
  chiude lo restituisce; il controllo del PC resta al portatile anche con il telefono attivo;
- certificato per i telefoni: CA di casa e certificato firmato da lei (openssl, se c'è),
  verificato davvero con una connessione HTTPS al server degli schermi;
- catalogo: l'azione «telefono» (onnxruntime-web e modelli generici, con dimensioni e SHA-256).
"""

import gzip
import json
import shutil
import socket
import ssl
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="calliope-telefono-"))
ERRORI = []
SENZA_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


def aspetta(cond, max_s=5.0, passo=0.05):
    t0 = time.monotonic()
    while time.monotonic() - t0 < max_s:
        v = cond()
        if v:
            return v
        time.sleep(passo)
    return None


def porta_libera() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def get(url, headers=None, ctx=None):
    """(stato, intestazioni, corpo) senza proxy di sistema e senza sollevare sugli errori."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        if ctx is not None:
            r = urllib.request.urlopen(req, context=ctx, timeout=10)
        else:
            r = SENZA_PROXY.open(req, timeout=10)
        with r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def prepara_file(cfg):
    """onnxruntime-web e modelli finti (pochi byte): la prova non dipende dai file veri."""
    web = TMP / "web"
    web.mkdir()
    (web / "ort.wasm.min.mjs").write_text("export const finto = 1;\n", encoding="utf-8")
    (web / "ort-wasm-simd-threaded.mjs").write_text("export default 1;\n", encoding="utf-8")
    (web / "ort-wasm-simd-threaded.wasm").write_bytes(b"\0asm" + bytes(300000))
    ww = TMP / "ww"
    ww.mkdir()
    for n in ("calliope", "melspectrogram", "embedding_model"):
        (ww / f"{n}.onnx").write_bytes(n.encode() * 100)
    cfg.telefono_web = str(web)
    cfg.wake_model = str(ww / "calliope.onnx")
    vad = TMP / "vad.onnx"
    vad.write_bytes(b"vad" * 100)
    cfg.vad_modello = str(vad)


def avvia(cfg):
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.server import AscoltoRemoto, ServerSatelliti
    from calliope.schermi import ArchivioSchermi, Schermi
    from calliope.schermi import tls as _tls
    from calliope.schermi.server import ServerSchermi
    srv = ServerSatelliti(cfg, ArchivioSatelliti(cfg.memory_db), log=lambda m: None).avvia()
    srv.avviato.set()
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    t = _tls.carica(cfg) if getattr(cfg, "_https", False) else None
    hub.tls = t
    web = ServerSchermi(hub, "127.0.0.1", porta_libera(), attesa_porta_s=5, tls=t).avvia()
    hub.server = web
    hub.satelliti = srv
    srv.schermi = hub
    hub.stanza_corrente = srv.stanza
    return srv, hub, web, AscoltoRemoto(srv, cfg, log=lambda m: None)


def main() -> int:
    from calliope.config import Config
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "memoria.db")
    cfg.satellite_porta = 0
    cfg.audio_modo = "satellite"
    prepara_file(cfg)
    srv, hub, web, ascolto = avvia(cfg)
    base = f"http://127.0.0.1:{web.port}"
    try:
        pagina(base, cfg, srv)
        websocket(base, web.port, srv, hub, ascolto)
    finally:
        web.ferma()
        srv.ferma()
    certificato(cfg)
    catalogo()
    shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


# ───────────────────────────── file ─────────────────────────────
def pagina(base, cfg, srv):
    from calliope.schermi import telefono
    s, h, corpo = get(base + "/telefono")
    verifica("/telefono porta a /telefono/", s == 200 and b"Abbina questo telefono" in corpo)
    s, h, corpo = get(base + "/telefono/")
    csp = h.get("content-security-policy", "")
    verifica("pagina: CSP solo 'self' più 'wasm-unsafe-eval'",
             s == 200 and "script-src 'self' 'wasm-unsafe-eval'" in csp
             and "unsafe-inline" not in csp and "unsafe-eval'" not in csp.replace(
                 "wasm-unsafe-eval'", "") and "http" not in csp.replace("ws://", "").replace(
                 "wss://", ""), csp)
    verifica("pagina: microfono permesso solo a sé stessa",
             h.get("permissions-policy", "").startswith("microphone=(self)"))
    html = corpo.decode("utf-8")
    verifica("pagina: niente script in linea né risorse esterne",
             "<script>" not in html and "http://" not in html and "https://" not in html)
    verifica("pagina: manifest, icona per iOS, schermo.js incorporato",
             'rel="manifest"' in html and "apple-touch-icon" in html
             and 'data-incorporata="1"' in html)
    s, h, corpo = get(base + "/telefono/manifest.webmanifest")
    m = json.loads(corpo)
    tipi = {i["sizes"] for i in m["icons"]}
    verifica("manifest: standalone, start_url e scope /telefono/, icone 192 e 512",
             s == 200 and h.get("content-type", "").startswith("application/manifest+json")
             and m["display"] == "standalone" and m["start_url"] == m["scope"] == "/telefono/"
             and {"192x192", "512x512"} <= tipi
             and any("maskable" in i.get("purpose", "") for i in m["icons"]))
    for i in m["icons"]:
        s, h, corpo = get(base + i["src"])
        png = corpo[:8] == b"\x89PNG\r\n\x1a\n"
        verifica(f"icona {i['src'].rsplit('/', 1)[-1]} ({i['sizes']}) servita",
                 s == 200 and (png or i["type"] == "image/svg+xml"))
    s, h, corpo = get(base + "/telefono/sw.js")
    verifica("service worker: senza cache HTTP, niente notifiche push",
             s == 200 and h.get("cache-control") == "no-cache" and b"\"push\"" not in corpo
             and b"pushManager" not in corpo
             and b"showNotification" not in corpo)
    for nome in ("telefono.js", "voce.js", "microfono.js", "schermo-acceso.js", "telefono.css",
                 "icona-180.png"):
        s, h, _ = get(base + "/telefono/" + nome)
        verifica(f"{nome} servito", s == 200)
    for nome in ("index.html.bak", "..%2Fserver.py", "telefono.py", "nonce.js"):
        s, _, _ = get(base + "/telefono/" + nome)
        verifica(f"/telefono/{nome} → non trovato", s == 404, str(s))
    # onnxruntime-web: gzip, ETag, 304
    url = base + "/telefono/ort/ort-wasm-simd-threaded.wasm?v=1"
    s, h, corpo = get(url, {"Accept-Encoding": "gzip"})
    vero = (Path(cfg.telefono_web) / "ort-wasm-simd-threaded.wasm").read_bytes()
    verifica("ort: WebAssembly compresso con gzip, tipo application/wasm",
             s == 200 and h.get("content-encoding") == "gzip"
             and h.get("content-type") == "application/wasm" and gzip.decompress(corpo) == vero,
             f"{len(corpo)} byte su {len(vero)}")
    s2, _, corpo2 = get(url, {"If-None-Match": h.get("etag", "")})
    verifica("ort: ETag → 304", s2 == 304 and not corpo2)
    s, h, corpo = get(base + "/telefono/ort/ort.wasm.min.mjs")
    verifica("ort: il modulo è JavaScript", s == 200 and "javascript" in h.get("content-type", ""))
    s, _, _ = get(base + "/telefono/ort/altro.wasm")
    verifica("ort: solo i file noti", s == 404)
    # modelli: solo con il token di un satellite
    s, _, _ = get(base + "/telefono/modelli/calliope.onnx")
    verifica("modelli: senza token 401", s == 401)
    s, _, _ = get(base + "/telefono/modelli/calliope.onnx", {"Authorization": "Bearer sbagliato"})
    verifica("modelli: con un token sbagliato 401", s == 401)
    sat, token = srv.archivio.crea_con_token("telefono")
    s, h, corpo = get(base + "/telefono/modelli/calliope.onnx",
                      {"Authorization": "Bearer " + token})
    verifica("modelli: con il token del satellite 200, non in cache condivisa",
             s == 200 and corpo == Path(cfg.wake_model).read_bytes()
             and h.get("cache-control", "").startswith("private"))
    s, _, _ = get(base + "/telefono/modelli/segreti.yaml", {"Authorization": "Bearer " + token})
    verifica("modelli: solo i quattro noti", s == 404)
    srv.archivio.revoca(sat["id"])
    s, _, _ = get(base + "/telefono/modelli/vad.onnx", {"Authorization": "Bearer " + token})
    verifica("modelli: token revocato 401", s == 401)
    s, _, _ = get(base + "/telefono/calliope-ca.crt")
    verifica("CA di casa: 404 finché non c'è", s == 404)
    s, _, corpo = get(base + "/telefono/api/stato")
    d = json.loads(corpo)
    verifica("api/stato: pronto, con le versioni dei modelli e nessun percorso",
             d["pronto"] and set(d["versioni"]) == {"vad", "melspectrogram", "embedding_model",
                                                    "calliope"}
             and str(TMP) not in corpo.decode("utf-8"), str(d.get("manca")))
    c2 = type(cfg)()
    c2.telefono_web = str(TMP / "manca")
    c2.wake_model = str(TMP / "manca" / "calliope.onnx")
    st = telefono.stato(c2)
    verifica("stato: senza file dice cosa manca e il comando",
             not st["pronto"] and any("--installa telefono" in m for m in st["manca"])
             and any("calliope.onnx" in m for m in st["manca"]))


# ───────────────────────────── WebSocket ─────────────────────────────
def websocket(base, porta, srv, hub, ascolto):
    from websockets.exceptions import ConnectionClosed, InvalidStatus
    from websockets.sync.client import connect
    from calliope.satellite import protocollo as P
    ws_base = f"ws://127.0.0.1:{porta}"
    origine = {"Origin": f"http://127.0.0.1:{porta}"}

    def rifiutato(url, headers):
        try:
            with connect(url, additional_headers=headers, open_timeout=5) as ws:
                ws.send(P.testo(tipo="abbina", versione=2))
                ws.recv(timeout=3)
            return False
        except (InvalidStatus, ConnectionClosed, OSError):
            return True

    verifica("WebSocket: senza Origin rifiutato", rifiutato(ws_base + "/telefono/ws/abbina", {}))
    verifica("WebSocket: Origin di un altro sito rifiutato", rifiutato(
        ws_base + "/telefono/ws/abbina", {"Origin": "https://evil.example"}))
    verifica("WebSocket: Origin con un'altra porta rifiutato", rifiutato(
        ws_base + "/telefono/ws/abbina", {"Origin": f"http://127.0.0.1:{porta + 1}"}))
    verifica("WebSocket: Host sconosciuto (DNS rebinding) rifiutato", rifiutato(
        ws_base + "/telefono/ws/abbina", {"Origin": "http://evil.example", "Host": "evil.example"}))

    # Abbinamento come un satellite, con la richiesta di schermo personale
    with connect(ws_base + "/telefono/ws/abbina", additional_headers=origine) as ws:
        ws.send(P.testo(tipo="abbina", versione=2, nome="telefono", personale="Dario"))
        m = P.leggi(ws.recv(timeout=5))
        verifica("abbinamento: codice di 6 cifre", m.get("tipo") == "codice"
                 and len(str(m.get("codice"))) == 6)
        res = srv.archivio.abbina(m["codice"], "auto")
        verifica("abbinamento: chi amministra vede la richiesta personale, non applicata",
                 res["ok"] and res["personale_chiesto"] == "Dario"
                 and not res["schermo"].get("proprietario"))
        m = P.leggi(ws.recv(timeout=5))
        token = m.get("token")
        verifica("abbinamento: la richiesta diventa il token (solo l'hash sul server)",
                 m.get("tipo") == "abbinato" and token
                 and token not in Path(srv.archivio.path).read_bytes().decode("latin-1"))

    # Il portatile (satellite vero del protocollo, con l'esecutore) è già collegato e attivo
    sat_pc, token_pc = srv.archivio.crea_con_token("studio", ruolo="pc")
    pc = connect(f"ws://127.0.0.1:{srv.port}" + P.PERCORSO_AUDIO)
    pc.send(P.testo(tipo="ciao", versione=2, token=token_pc, primo=False, nome="portatile",
                    esecutore={"nome": "portatile", "capacita": ["volume"], "file": True}))
    verifica("portatile: benvenuto", P.leggi(pc.recv(timeout=5)).get("tipo") == "benvenuto")
    verifica("portatile: attivo", P.leggi(pc.recv(timeout=5)) == {"tipo": "attivo",
                                                                  "attivo": True, "altro": None})
    pc.send(P.testo(tipo="pronto", eco=0.0))
    aspetta(lambda: srv.attivo_pronto() is not None)
    risultato = {}

    def ascolta():
        risultato["audio"] = ascolto.listen(object(), 0.0)
        risultato["woke"] = ascolto.woke
    t = threading.Thread(target=ascolta, daemon=True)
    t.start()
    m = P.leggi(pc.recv(timeout=5))
    verifica("il server ascolta il portatile", m.get("tipo") == "ascolta")
    lid_pc = m.get("id")

    # Il telefono si collega: resta in attesa, il portatile continua
    tel = connect(ws_base + "/telefono/ws/sessione", additional_headers=origine)
    tel.send(P.testo(tipo="ciao", versione=2, token=token, primo=False, nome="telefono"))
    m = P.leggi(tel.recv(timeout=5))
    verifica("telefono: benvenuto con i parametri e gli schermi",
             m.get("tipo") == "benvenuto" and "wake_threshold" in m.get("parametri", {})
             and m.get("schermi") is not None)
    m = P.leggi(tel.recv(timeout=5))
    verifica("telefono: in attesa, il portatile resta attivo",
             m.get("tipo") == "attivo" and m.get("attivo") is False and m.get("altro") == "studio"
             and srv.attivo.satellite["nome"] == "studio")
    tel.send(P.testo(tipo="pronto", eco=None))
    time.sleep(0.2)
    # «prendi»: il telefono diventa attivo, il portatile smette di ascoltare
    tel.send(P.testo(tipo="prendi"))
    msgs = [P.leggi(pc.recv(timeout=5)) for _ in range(2)]
    verifica("prendi: il portatile sa che non è più attivo e smette di ascoltare",
             {"tipo": "attivo", "attivo": False, "altro": "auto"} in msgs
             and {"tipo": "sveglia", "id": lid_pc} in msgs, str(msgs))
    pc.send(P.testo(tipo="nessuna_frase", id=lid_pc))     # come farebbe Listener
    m1 = P.leggi(tel.recv(timeout=5))
    m2 = P.leggi(tel.recv(timeout=5))
    asc = m1 if m1.get("tipo") == "ascolta" else m2
    verifica("prendi: il telefono è attivo e riceve «ascolta»",
             {m1.get("tipo"), m2.get("tipo")} == {"attivo", "ascolta"} and asc.get("wake") is True)
    verifica("stanza degli schermi: quella del telefono", srv.stanza() == "auto")
    verifica("controllo del PC: resta al portatile anche con il telefono attivo",
             srv.per_pc() is not None and srv.per_pc().satellite["nome"] == "studio")
    from calliope.pc.remoto import per_pc
    verifica("per_pc anche con un server senza il metodo (prove vecchie)",
             per_pc(type("S", (), {"attivo_pronto": lambda self: "x"})()) == "x"
             and per_pc(None) is None)
    # Una frase dal telefono, come la manda la pagina
    for _ in range(10):
        tel.send(P.binario(P.AUDIO, asc["id"], b"\x10\x00" * 512))
    tel.send(P.testo(tipo="frase_finita", id=asc["id"], fa_s=0.4, woke=True, wake_score=1.0))
    t.join(5)
    verifica("la frase del telefono arriva ad AscoltoRemoto (woke vero)",
             risultato.get("audio") is not None and len(risultato["audio"]) == 5120
             and risultato.get("woke"))
    # La voce verso il telefono, a pezzi
    from calliope.satellite.server import UscitaRemota
    out = UscitaRemota(srv)
    out.invia(1, "Sono le dieci.", b"\x01\x00" * 8820, 22050)
    m = P.leggi(tel.recv(timeout=5))
    pezzi = []
    while len(pezzi) < 2:
        d = tel.recv(timeout=5)
        if isinstance(d, bytes):
            pezzi.append(P.apri_binario(d))
    verifica("voce: «frase» e poi i pezzi binari «T» verso il telefono",
             m.get("tipo") == "frase" and m.get("testo") == "Sono le dieci."
             and all(p[0] == P.VOCE and p[1] == m["id"] for p in pezzi))
    # schermo: token di schermo sulla connessione, schermo nella stanza del telefono
    tel.send(P.testo(tipo="schermo", token=""))
    m = None
    for _ in range(50):
        d = tel.recv(timeout=5)
        if isinstance(d, str) and P.leggi(d).get("tipo") == "schermo":
            m = P.leggi(d)
            break
    verifica("schermo: token per le schede, nella stanza del telefono",
             m and m.get("token") and any(s["stanza"] == "auto" for s in hub.abbinati()))
    # «lascia»: il posto torna al portatile
    tel.send(P.testo(tipo="lascia"))
    verifica("lascia: il portatile torna attivo",
             aspetta(lambda: srv.attivo is not None and srv.attivo.satellite["nome"] == "studio"))
    # di nuovo al telefono, poi il telefono si chiude: torna al portatile
    tel.send(P.testo(tipo="prendi"))
    aspetta(lambda: srv.attivo.satellite["nome"] == "auto")
    tel.close()
    verifica("telefono chiuso: il portatile torna attivo", aspetta(
        lambda: srv.attivo is not None and srv.attivo.satellite["nome"] == "studio"))
    # Una seconda pagina con lo stesso token sostituisce la prima (4409)
    a = connect(ws_base + "/telefono/ws/sessione", additional_headers=origine)
    a.send(P.testo(tipo="ciao", versione=2, token=token, primo=False))
    a.recv(timeout=5)
    b = connect(ws_base + "/telefono/ws/sessione", additional_headers=origine)
    b.send(P.testo(tipo="ciao", versione=2, token=token, primo=False))
    b.recv(timeout=5)
    codice = None
    try:
        while True:
            a.recv(timeout=5)
    except ConnectionClosed as e:
        codice = e.rcvd.code if e.rcvd else None
    verifica("stesso telefono due volte: la connessione vecchia chiude con 4409", codice == 4409,
             str(codice))
    # Revoca: 4401 (il controllo gira ogni 5 s)
    srv.CONTROLLO_REVOCA_S = 0.3
    srv.archivio.revoca("auto")
    codice = None
    try:
        while True:
            b.recv(timeout=8)
    except ConnectionClosed as e:
        codice = e.rcvd.code if e.rcvd else None
    except TimeoutError:
        codice = "nessuna chiusura"
    verifica("telefono revocato: chiusura 4401", codice == 4401, str(codice))
    c = connect(ws_base + "/telefono/ws/sessione", additional_headers=origine)
    c.send(P.testo(tipo="ciao", versione=2, token=token, primo=False))
    try:
        c.recv(timeout=5)
        codice = None
    except ConnectionClosed as e:
        codice = e.rcvd.code if e.rcvd else None
    verifica("token revocato: niente sessione (4401)", codice == 4401, str(codice))
    pc.close()
    # Senza il server dei satelliti (Calliope in locale) il telefono lo sa subito
    sat_vecchio, hub.satelliti = hub.satelliti, None
    with connect(ws_base + "/telefono/ws/sessione", additional_headers=origine) as ws:
        m = P.leggi(ws.recv(timeout=5))
        try:
            ws.recv(timeout=5)
            codice = None
        except ConnectionClosed as e:
            codice = e.rcvd.code if e.rcvd else None
    verifica("senza satelliti (audio_modo: locale): errore chiaro e chiusura 4503",
             m.get("tipo") == "errore" and "audio_modo" in m.get("motivo", "") and codice == 4503)
    hub.satelliti = sat_vecchio


# ───────────────────────────── certificato ─────────────────────────────
def certificato(cfg):
    from calliope.satellite.__main__ import _openssl
    from calliope.schermi import tls
    if _openssl() is None:
        print("SALTATA IN PARTE: openssl non c'è: salto il certificato per i telefoni")
        return
    d = TMP / "cert"
    d.mkdir()
    c = type(cfg)()
    c.config_dir = str(d)
    c.memory_db = str(d / "m.db")
    c.satellite_porta = 0
    c.audio_modo = "satellite"
    c.telefono_web, c.wake_model, c.vad_modello = cfg.telefono_web, cfg.wake_model, cfg.vad_modello
    out = []
    verifica("--certificato: CA di casa e certificato degli schermi",
             tls.certificato_telefono(c, ["10.9.8.7", "calliope.lan"], out=out.append) == 0
             and (d / "calliope-ca.crt").is_file() and (d / "schermi.crt").is_file(),
             out[-1] if out else "")
    verifica("i file nuovi vincono su quelli dei satelliti", tls.file_tls(c)[0].name == "schermi.crt")
    ca_prima = (d / "calliope-ca.crt").read_bytes()
    out = []
    tls.certificato_telefono(c, ["10.9.8.6"], forza=True, out=out.append)
    verifica("--forza rifà il certificato, la CA resta la stessa (niente da reinstallare)",
             (d / "calliope-ca.crt").read_bytes() == ca_prima
             and any("10.9.8.6" in r for r in out))
    c.schermi_indirizzo = "0.0.0.0"
    c._https = True
    srv, hub, web, _ = avvia(c)
    try:
        ctx = ssl.create_default_context(cafile=str(d / "calliope-ca.crt"))
        s, _, _ = get(f"https://127.0.0.1:{web.port}/telefono/api/stato", ctx=ctx)
        verifica("HTTPS verificato con la CA di casa (nome e catena), come farà il telefono",
                 s == 200)
        s, h, corpo = get(f"https://127.0.0.1:{web.port}/telefono/calliope-ca.crt", ctx=ctx)
        verifica("la CA si scarica dalla pagina (come certificato da installare)",
                 s == 200 and corpo == ca_prima and "x509-ca-cert" in h.get("content-type", ""))
        senza = ssl.create_default_context()
        try:
            get(f"https://127.0.0.1:{web.port}/telefono/", ctx=senza)
            fidato = True
        except (ssl.SSLError, urllib.error.URLError):
            fidato = False
        verifica("senza la CA il certificato non è fidato", not fidato)
        verifica("il satellite riceve l'impronta del certificato nuovo per il suo ponte",
                 hub.tls and hub.tls["cert"].endswith("schermi.crt"))
    finally:
        web.ferma()
        srv.ferma()


def catalogo():
    from calliope.config import Config
    from calliope.installa.catalogo import DESCRIZIONI, catalogo as cat
    a = cat(Config()).get("telefono")
    nomi = [Path(f.dest).name for f in (a.files if a else ())]
    verifica("catalogo: «telefono» con onnxruntime-web e i modelli generici, SHA-256 e dimensioni",
             a is not None and "telefono" in DESCRIZIONI
             and set(nomi) == {"ort.wasm.min.mjs", "ort-wasm-simd-threaded.mjs",
                               "ort-wasm-simd-threaded.wasm", "melspectrogram.onnx",
                               "embedding_model.onnx"}
             and all(f.sha256 and f.size and f.url.startswith("https://") for f in a.files)
             and "cdn.jsdelivr.net" in a.hosts and "github.com" in a.hosts)


if __name__ == "__main__":
    sys.exit(main())
