"""
Il server web delle schede: Starlette + uvicorn **senza extra**, in un thread dentro il
processo di Calliope (docs/ricerche/2026-10-01-mappe-e-schermi.md, §9.1).

Niente `uvicorn[standard]`: httptools e uvloop non hanno wheel `win_arm64`. Starlette 1.7.0
e uvicorn 0.54.0 sono `py3-none-any`, come le loro dipendenze (anyio, h11, click, colorama):
nessun codice nativo nuovo (principio 4).

Indirizzi:
  GET  /                         la pagina (kiosk), con i suoi /schermo.css e /schermo.js
  POST /api/abbinamento          pagina senza token: {codice, richiesta, scade}
  POST /api/abbinamento/stato    «Authorization: Bearer <richiesta>» → attesa | abbinato | scaduto
  POST /api/accedi               «Authorization: Bearer <token>» → {sessione, nome, stanza…}
  GET  /eventi?sessione=…        SSE: benvenuto (con la cronologia e lo stato della voce),
                                 scheda, voce, revocato, ping
  GET  /api/salute               il server c'è (per python -m calliope.stato)
  POST /api/scrivi               «X-Calliope-Sessione: <sessione>», {testo}: una frase scritta
                                 (03/10, moduli.py), come se fosse detta dal proprietario
  POST /api/modulo               «X-Calliope-Sessione», {modulo, valori}: i dati di un modulo,
                                 controllati qui e passati al tool che li aveva chiesti
                                 Tutti e due solo durante una conversazione cominciata a
                                 voce (05/10, conversazione.py): altrimenti 403 con
                                 «codice»: «senza_conversazione»; l'evento SSE «scrittura»
                                 accende e spegne i comandi della pagina
  POST /api/immagine             «X-Calliope-Sessione», {immagine: data URL, testo}: una foto
                                 (05/10, calliope/immagini.py) dal telefono o dallo schermo,
                                 solo da uno schermo personale; ridotta e riscritta qui
  POST /api/allegato             «X-Calliope-Sessione», byte nudi (octet-stream), nome e
                                 domanda in «X-Calliope-Nome»/«X-Calliope-Testo» (URI): un file
                                 di qualsiasi tipo (05/10, calliope/allegati.py), stesse regole
  GET  /api/cruscotto            «X-Calliope-Sessione»: il cruscotto di chi amministra (06/10,
                                 cruscotto.py), solo da uno schermo personale il cui
                                 proprietario amministra; ?aggiorna=1 ricalcola. Sola lettura
  POST /api/scarica              «X-Calliope-Sessione», {chiave, formato}: l'indirizzo per
                                 scaricare il documento di una scheda (07/10, scarica.py), solo
                                 da uno schermo personale a cui la scheda è arrivata
  GET  /scarica/<gettone>        il file (MD, PDF, Word, Excel), convertito qui al primo
                                 accesso; il gettone vale pochi minuti e poche richieste
  GET  /satellite                il comando per un PC nuovo come satellite (satellite/web.py)
  /telefono/…                    la web app del telefono (telefono.py): pagina, modelli e il
                                 WebSocket del protocollo dei satelliti

SSE e non WebSocket: una sola direzione (lo schermo mostra e basta), riconnessione
automatica del browser, passa ovunque; misurato 0,4 ms di mediana in locale. Il WebSocket
c'è solo per il telefono (03/10), che manda l'audio del microfono: uvicorn lo serve con
websockets (già dipendenza dei satelliti) in modalità sans-I/O. La sessione dell'SSE è un numero a caso
legato allo schermo finché il server vive: EventSource non manda intestazioni, e il token
in un URL finirebbe nei log. Niente cookie: due schede dello stesso browser possono essere
due schermi diversi.

Mai token o codici nei log: il log degli accessi di uvicorn è spento, gli errori non
contengono le intestazioni. Si accettano solo richieste con un indirizzo IP, «localhost» o
il nome di questo PC nell'intestazione Host: una pagina web qualunque non può arrivare qui
con il DNS rebinding.
"""

import asyncio
import ipaddress
import json
import logging
import re
import secrets
import socket
import threading
import time
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from starlette.routing import Route

from ..satellite import web as satellite_web
from . import telefono
from .hub import Schermi

PAGINA = Path(__file__).resolve().parent / "pagina"
PING_S = 15.0

_SICUREZZA = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    # Tutto da qui, niente da fuori: la pagina funziona senza internet
    # frame-src 'self' (05/10): solo i riquadri dei giochi (/gioco/…); anche un riquadro che
    # prova a navigare verso un altro sito lo ferma questa regola, prima della richiesta
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self'; "
                                "img-src 'self' data:; connect-src 'self'; frame-src 'self'; "
                                "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"),
}


def _host_ok(host: str, nomi: set[str]) -> bool:
    h = (host or "").strip().lower()
    if h.startswith("["):                                   # [::1]:8770
        h = h[1:h.find("]")] if "]" in h else h
    elif h.count(":") == 1:
        h = h.rsplit(":", 1)[0]
    if not h:
        return False
    if h in nomi:
        return True
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


class _SoloHostNoti:
    """Middleware ASGI: risponde 400 se Host non è un IP, «localhost» o il nome del PC."""

    def __init__(self, app, nomi: set[str]):
        self.app = app
        self.nomi = nomi

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            host = next((v.decode("latin-1") for k, v in scope.get("headers", [])
                         if k == b"host"), "")
            if not _host_ok(host, self.nomi):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                    return
                resp = PlainTextResponse("Host non ammesso", status_code=400)
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _nomi_ammessi(extra=()) -> set[str]:
    nomi = {"localhost"}
    try:
        h = socket.gethostname().lower()
        nomi |= {h, f"{h}.local", f"{h}.lan", f"{h}.home"}
    except OSError:
        pass
    return nomi | {str(n).lower() for n in extra or ()}


def _bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    return auth[7:].strip() if auth.lower().startswith("bearer ") else ""


def _json(data, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status, headers={"Cache-Control": "no-store",
                                                           **_SICUREZZA})


def crea_app(hub: Schermi) -> Starlette:
    """L'app Starlette per questo hub. Le sessioni SSE vivono qui (in memoria)."""
    sessioni: dict[str, int] = {}
    lock = threading.Lock()

    def file(nome: str, tipo: str):
        async def handler(request: Request):
            return FileResponse(PAGINA / nome, media_type=tipo,
                                headers={"Cache-Control": "no-cache", **_SICUREZZA})
        return handler

    async def nuovo_abbinamento(request: Request):
        r = hub.archivio.nuova_richiesta()
        return _json({"codice": r["codice"], "richiesta": r["richiesta"], "scade": r["scade"],
                      "ora_server": time.time()})

    async def stato_abbinamento(request: Request):
        richiesta = _bearer(request)
        if not richiesta:
            return _json({"stato": "scaduto"}, 401)
        st = hub.archivio.stato_richiesta(richiesta)
        out = {"stato": st["stato"]}
        if st["stato"] == "abbinato":
            s = st["schermo"]
            out.update(nome=s["nome"], stanza=s["stanza"])
        return _json(out)

    async def accedi(request: Request):
        if in_arresto():
            return _json({"errore": "in arresto"}, 503)
        s = hub.archivio.per_token(_bearer(request))
        if s is None:
            return _json({"errore": "schermo non abbinato"}, 401)
        sess = secrets.token_urlsafe(18)
        with lock:
            # Una sessione vecchia dello stesso schermo resta valida finché la sua pagina
            # è aperta; le sessioni orfane si tolgono oltre un tetto
            if len(sessioni) > 200:
                sessioni.clear()
            sessioni[sess] = s["id"]
        hub.archivio.segna_visto(s["id"])
        personale = bool(s.get("proprietario"))
        # La casella «scrivi invece di parlare» (03/10): sugli schermi personali, e su quelli
        # di stanza solo se la configurazione lo vuole (lì chi scrive è un ospite)
        scrive = bool(getattr(hub.cfg, "schermi_scritto", True)) and (
            personale or bool(getattr(hub.cfg, "schermi_scritto_stanza", False)))
        cr = getattr(hub, "cruscotto", None)
        return _json({"sessione": sess, "nome": s["nome"], "stanza": s["stanza"],
                      "personale": personale, "scrivi": scrive, "ora_server": time.time(),
                      # Il cruscotto di chi amministra (06/10): solo per decidere se la pagina
                      # mostra il pulsante; /api/cruscotto lo ricontrolla a ogni richiesta
                      "amministra": bool(cr is not None and cr.amministra(s)),
                      # Si scrive solo durante una conversazione a voce (05/10)
                      "scrittura": hub.stato_scrittura(s)})

    def in_arresto():
        # Durante l'arresto (ServerSchermi.ferma) niente flussi nuovi: una pagina che si
        # ricollega subito, sulla stessa connessione keep-alive, aprirebbe un flusso che
        # nessuno chiude più e uvicorn lo cancellerebbe a forza (traccia di CancelledError)
        return getattr(hub, "server", None) is not None and not hub.server_attivo

    async def eventi(request: Request):
        if in_arresto():
            return PlainTextResponse("in arresto", status_code=503,
                                     headers={"Cache-Control": "no-store", **_SICUREZZA})
        sess = request.query_params.get("sessione", "")
        with lock:
            sid = sessioni.get(sess)
        schermo = next((s for s in hub.abbinati() if s["id"] == sid), None) if sid else None
        if schermo is None:
            # 401: EventSource si ferma e la pagina rifà l'accesso (o torna ad abbinarsi)
            return PlainTextResponse("sessione non valida", status_code=401,
                                     headers={"Cache-Control": "no-store", **_SICUREZZA})
        client = request.client.host if request.client else ""
        conn, storia = hub.collega(schermo, asyncio.get_running_loop(),
                                   locale=client in ("127.0.0.1", "::1"))

        async def flusso():
            try:
                benvenuto = {"nome": schermo["nome"], "stanza": schermo["stanza"],
                             "personale": bool(schermo.get("proprietario")),
                             "ora_server": time.time(), "cronologia": storia,
                             # Stato della voce (o None: questa pagina non lo mostra)
                             "voce": hub.voce_per(conn),
                             # Si può scrivere adesso? (05/10: solo in conversazione)
                             "scrittura": hub.stato_scrittura_per(conn),
                             # Uso del contesto dell'ultima risposta (schermi personali)
                             "contesto": hub.contesto_per(schermo),
                             # La parola che sveglia («Dormo · di' «Computer»», 04/10)
                             "parola": (getattr(hub.cfg, "wake_names", None)
                                        or ["Calliope"])[0]}
                yield "retry: 3000\n\n"
                yield f"event: benvenuto\ndata: {json.dumps(benvenuto, ensure_ascii=False, default=str)}\n\n"
                while True:
                    try:
                        tipo, dati = await asyncio.wait_for(conn.coda.get(), PING_S)
                    except asyncio.TimeoutError:
                        if not hub.valido(schermo["id"]):     # revocato da terminale
                            tipo, dati = "revocato", "{}"
                        else:
                            # Un evento vero e non un commento: la pagina lo vede e capisce
                            # da sola se il flusso è morto (rete caduta senza chiusura, 02/10)
                            yield f"event: ping\ndata: {int(time.time())}\n\n"
                            continue
                    if tipo == "fine":                        # arresto del server
                        return
                    yield f"event: {tipo}\ndata: {dati}\n\n"
                    if tipo == "revocato":
                        with lock:
                            for k in [k for k, v in sessioni.items() if v == schermo["id"]]:
                                sessioni.pop(k, None)
                        return
            finally:
                hub.scollega(conn)

        return StreamingResponse(flusso(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store",
                                          "X-Accel-Buffering": "no", **_SICUREZZA})

    async def salute(request: Request):
        return _json({"ok": True, "servizio": "calliope-schermi"})

    # ── dalla pagina a Calliope (03/10): testo scritto e moduli ──
    # Niente cookie: la sessione viaggia in un'intestazione che una pagina di un altro sito
    # non può mandare senza il permesso CORS (che qui non c'è), e il corpo deve essere JSON:
    # nessun modulo HTML di un altro sito può arrivare qui (CSRF). Solo in HTTPS, salvo dal
    # computer stesso; un limite di invii al minuto per schermo e di dimensione.
    invii: dict[int, list[float]] = {}

    def scrivibile(request: Request, canale: str = "scritto"):
        """(schermo, None) se la richiesta può scrivere; altrimenti (None, risposta). Il
        punto da cui passa ogni ingresso dalla pagina (testo, moduli, domani le immagini):
        sessione, HTTPS, limite al minuto e, dal 05/10, la conversazione a voce
        (`Schermi.scrittura_consentita`)."""
        if not getattr(hub.cfg, "schermi_scritto", True):
            return None, _json({"errore": "scrittura spenta"}, 403)
        client = request.client.host if request.client else ""
        if request.url.scheme != "https" and client not in ("127.0.0.1", "::1"):
            return None, _json({"errore": "solo in HTTPS"}, 403)
        sess = request.headers.get("x-calliope-sessione", "")
        with lock:
            sid = sessioni.get(sess) if sess else None
        schermo = next((s for s in hub.abbinati() if s["id"] == sid), None) if sid else None
        if schermo is None:
            return None, _json({"errore": "sessione non valida"}, 401)
        n = max(1, int(getattr(hub.cfg, "schermi_scritto_al_minuto", 12)))
        ora = time.monotonic()
        with lock:
            fatti = [t for t in invii.get(schermo["id"], []) if ora - t < 60.0]
            if len(fatti) >= n:
                invii[schermo["id"]] = fatti
                return None, _json({"errore": "troppi invii: aspetta un momento"}, 429)
            invii[schermo["id"]] = fatti + [ora]
        # Da uno schermo di stanza si scrive solo se la configurazione lo vuole (come ospite)
        if not schermo.get("proprietario") and not getattr(hub.cfg, "schermi_scritto_stanza",
                                                           False):
            return None, _json({"errore": "da questo schermo non si scrive"}, 403)
        # Solo durante una conversazione cominciata a voce (05/10): chi ha in mano lo schermo
        # non scrive a nome del proprietario se lui non sta parlando con Calliope. Dopo il
        # limite al minuto, così i rifiuti nel registro dei turni restano pochi
        ok, motivo = hub.scrittura_consentita(schermo)
        if not ok:
            hub.rifiuta_scritto(schermo, motivo, canale)
            return None, _json({"errore": hub.testo_senza_conversazione(),
                                "codice": "senza_conversazione", "motivo": motivo}, 403)
        return schermo, None

    async def corpo_json(request: Request, massimo: int):
        """(dati, None) oppure (None, risposta d'errore). Solo application/json, al massimo
        `massimo` byte anche senza Content-Length."""
        tipo = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if tipo != "application/json":
            return None, _json({"errore": "serve JSON"}, 415)
        try:
            if int(request.headers.get("content-length") or 0) > massimo:
                return None, _json({"errore": "troppo grande"}, 413)
        except ValueError:
            return None, _json({"errore": "lunghezza non valida"}, 400)
        dati = b""
        async for pezzo in request.stream():
            dati += pezzo
            if len(dati) > massimo:
                return None, _json({"errore": "troppo grande"}, 413)
        try:
            return json.loads(dati.decode("utf-8") or "{}"), None
        except (ValueError, UnicodeDecodeError):
            return None, _json({"errore": "JSON non valido"}, 400)

    async def scrivi(request: Request):
        schermo, errore = scrivibile(request, "scritto")
        if errore is not None:
            return errore
        personale = bool(schermo.get("proprietario"))
        dati, errore = await corpo_json(request, 4096)
        if errore is not None:
            return errore
        testo = dati.get("testo") if isinstance(dati, dict) else None
        if not isinstance(testo, str):
            return _json({"errore": "manca il testo"}, 400)
        testo = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", testo)).strip()
        if not testo:
            return _json({"errore": "manca il testo"}, 400)
        if len(testo) > int(getattr(hub.cfg, "schermi_scritto_max", 500)):
            return _json({"errore": "testo troppo lungo"}, 413)
        ok = hub.ingresso.metti({"tipo": "scritto", "testo": testo,
                                 "persona": schermo.get("proprietario"),
                                 "schermo": schermo.get("nome"), "stanza": schermo.get("stanza"),
                                 # La risposta torna qui (calliope/rispondi.py, 04/10)
                                 "schermo_id": schermo.get("id"),
                                 "arrivato": time.time()})
        if not ok:
            return _json({"errore": "Calliope è occupata: riprova tra poco"}, 503)
        return _json({"ok": True, "come": "persona" if personale else "ospite"})

    async def modulo(request: Request):
        schermo, errore = scrivibile(request, "modulo")
        if errore is not None:
            return errore
        dati, errore = await corpo_json(request, 32768)
        if errore is not None:
            return errore
        if not isinstance(dati, dict):
            return _json({"errore": "dati non validi"}, 400)
        # Il modulo è di chi l'ha chiesto: solo uno schermo personale suo lo invia
        m, valori, errori = hub.moduli.valida(str(dati.get("modulo") or ""),
                                              schermo.get("proprietario"), dati.get("valori"))
        if m is None:
            return _json({"errore": errori.get("_", "modulo chiuso")}, 409)
        if errori:
            return _json({"errori": errori}, 422)
        if not hub.ingresso.metti({"tipo": "modulo", "_modulo": m, "valori": valori,
                                   "schermo": schermo.get("nome"),
                                   "stanza": schermo.get("stanza"),
                                   "schermo_id": schermo.get("id"), "arrivato": time.time()}):
            return _json({"errore": "Calliope è occupata: riprova tra poco"}, 503)
        return _json({"ok": True})

    async def immagine(request: Request):
        """Una foto dallo schermo personale (05/10): byte controllati e riscritti in JPEG qui
        (immagini.prepara, in un thread: Pillow costa decine di ms), poi all'ingresso come
        il testo scritto. Mai su disco."""
        if not getattr(hub.cfg, "immagini_enabled", True):
            return _json({"errore": "foto spente"}, 403)
        # Anche le foto solo durante una conversazione a voce (05/10, conversazione.py)
        schermo, errore = scrivibile(request, "immagine")
        if errore is not None:
            return errore
        if not schermo.get("proprietario"):
            return _json({"errore": "le foto si mandano solo da uno schermo personale"}, 403)
        max_mb = float(getattr(hub.cfg, "immagini_max_mb", 12.0))
        dati, errore = await corpo_json(request, int(max_mb * 1_400_000) + 8192)
        if errore is not None:
            return errore
        if not isinstance(dati, dict):
            return _json({"errore": "dati non validi"}, 400)
        testo = dati.get("testo") or ""
        if not isinstance(testo, str):
            return _json({"errore": "testo non valido"}, 400)
        testo = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", testo)).strip()
        if len(testo) > int(getattr(hub.cfg, "schermi_scritto_max", 500)):
            return _json({"errore": "testo troppo lungo"}, 413)
        from ..immagini import Immagine, ImmagineNonValida, da_data_url, prepara
        try:
            grezzi = da_data_url(dati.get("immagine"))
            jpeg, w, h = await asyncio.to_thread(
                prepara, grezzi, int(getattr(hub.cfg, "immagini_lato_max", 1280)),
                int(max_mb * 1_000_000))
        except ImmagineNonValida as e:
            return _json({"errore": str(e)}, 415)
        fonte = "telefono" if dati.get("fonte") == "telefono" else "schermo"
        img = Immagine(jpeg, w, h, fonte=fonte, persona=schermo.get("proprietario"))
        if not hub.ingresso.metti({"tipo": "immagine", "immagine": img, "testo": testo,
                                   "persona": schermo.get("proprietario"),
                                   "schermo": schermo.get("nome"),
                                   "stanza": schermo.get("stanza"),
                                   "schermo_id": schermo.get("id"), "arrivato": time.time()}):
            return _json({"errore": "Calliope è occupata: riprova tra poco"}, 503)
        return _json({"ok": True, "larghezza": w, "altezza": h})

    async def allegato(request: Request):
        """Un file di qualsiasi tipo dallo schermo personale (05/10, calliope/allegati.py): i
        byte nudi nel corpo (application/octet-stream: nessun modulo HTML di un altro sito lo
        manda, e la sessione è in un'intestazione), nome e domanda in intestazioni codificate.
        Tipo vero dai byte e lettura in un thread; un'immagine segue la strada delle foto.
        Mai su disco. Stesse regole della scrittura e delle foto (scrivibile)."""
        if not getattr(hub.cfg, "allegati_enabled", True):
            return _json({"errore": "allegati spenti"}, 403)
        schermo, errore = scrivibile(request, "allegato")
        if errore is not None:
            return errore
        if not schermo.get("proprietario"):
            return _json({"errore": "i file si mandano solo da uno schermo personale"}, 403)
        tipo = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if tipo != "application/octet-stream":
            return _json({"errore": "serve application/octet-stream"}, 415)
        max_b = int(float(getattr(hub.cfg, "allegati_max_mb", 25.0)) * 1_000_000)
        troppo = _json({"errore": f"file troppo grande (al massimo {max_b // 1_000_000} MB)"},
                       413)
        try:
            if int(request.headers.get("content-length") or 0) > max_b:
                return troppo
        except ValueError:
            return _json({"errore": "lunghezza non valida"}, 400)
        corpo = bytearray()
        async for pezzo in request.stream():
            corpo += pezzo
            if len(corpo) > max_b:
                return troppo
        from urllib.parse import unquote
        nome = unquote(request.headers.get("x-calliope-nome", ""))[:300]
        testo = unquote(request.headers.get("x-calliope-testo", ""))
        testo = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", testo)).strip()
        if len(testo) > int(getattr(hub.cfg, "schermi_scritto_max", 500)):
            return _json({"errore": "testo troppo lungo"}, 413)
        fonte = "telefono" if request.headers.get("x-calliope-fonte") == "telefono" else "schermo"
        dati = bytes(corpo)
        del corpo
        from ..allegati import AllegatoNonValido, prepara as prepara_file
        from ..immagini import (Immagine, ImmagineNonValida, prepara as prepara_foto,
                                tipo_dai_byte)
        voce = {"testo": testo, "persona": schermo.get("proprietario"),
                "schermo": schermo.get("nome"), "stanza": schermo.get("stanza"),
                "schermo_id": schermo.get("id"), "arrivato": time.time()}
        if tipo_dai_byte(dati):
            # Un'immagine (dai byte): come una foto, ridotta e riscritta in JPEG
            if not getattr(hub.cfg, "immagini_enabled", True):
                return _json({"errore": "foto spente"}, 403)
            try:
                jpeg, w, h = await asyncio.to_thread(
                    prepara_foto, dati, int(getattr(hub.cfg, "immagini_lato_max", 1280)),
                    max_b)
            except ImmagineNonValida as e:
                return _json({"errore": str(e)}, 415)
            voce.update(tipo="immagine", immagine=Immagine(
                jpeg, w, h, fonte=fonte, persona=schermo.get("proprietario")))
            risposta = {"ok": True, "tipo": "immagine", "larghezza": w, "altezza": h}
        else:
            try:
                att = await asyncio.to_thread(prepara_file, dati, nome, hub.cfg,
                                              schermo.get("proprietario"), fonte)
            except AllegatoNonValido as e:
                return _json({"errore": str(e)}, 415)
            voce.update(tipo="allegato", allegato=att)
            risposta = {"ok": True, "tipo": att.categoria, "descrizione": att.tipo(),
                        "note": list(att.note)}
        if not hub.ingresso.metti(voce):
            return _json({"errore": "Calliope è occupata: riprova tra poco"}, 503)
        return _json(risposta)

    # ── cruscotto di chi amministra (06/10, cruscotto.py) ──
    async def cruscotto(request: Request):
        """Sola lettura. Sessione in un'intestazione (come lo scritto: nessuna pagina di un altro
        sito la manda), solo in HTTPS fuori da questo computer, solo uno schermo personale il
        cui proprietario amministra, ricontrollato qui a ogni richiesta. Il calcolo in un
        thread, con la cache del cruscotto: la voce non lo aspetta mai."""
        cr = getattr(hub, "cruscotto", None)
        if cr is None:
            return _json({"errore": "cruscotto spento"}, 404)
        client = request.client.host if request.client else ""
        if request.url.scheme != "https" and client not in ("127.0.0.1", "::1"):
            return _json({"errore": "solo in HTTPS"}, 403)
        sess = request.headers.get("x-calliope-sessione", "")
        with lock:
            sid = sessioni.get(sess) if sess else None
        schermo = next((s for s in hub.abbinati() if s["id"] == sid), None) if sid else None
        if schermo is None:
            return _json({"errore": "sessione non valida"}, 401)
        if not cr.amministra(schermo):
            return _json({"errore": "solo sugli schermi personali di chi amministra"}, 403)
        forza = request.query_params.get("aggiorna") == "1"
        try:
            dati = await asyncio.to_thread(cr.dati, forza)
        except Exception as e:  # noqa: BLE001
            return _json({"errore": f"cruscotto non calcolato ({type(e).__name__})"}, 500)
        return _json(dati)

    # ── «Scarica» nella scheda del documento (07/10, scarica.py) ──
    async def scarica_gettone(request: Request):
        """L'indirizzo per scaricare il documento di una scheda: sessione in un'intestazione
        (come lo scritto), JSON, solo in HTTPS fuori da questo computer. Non serve una
        conversazione a voce: il documento è già sullo schermo del proprietario."""
        from .scarica import Rifiuto
        client = request.client.host if request.client else ""
        if request.url.scheme != "https" and client not in ("127.0.0.1", "::1"):
            return _json({"errore": "solo in HTTPS"}, 403)
        sess = request.headers.get("x-calliope-sessione", "")
        with lock:
            sid = sessioni.get(sess) if sess else None
        schermo = next((s for s in hub.abbinati() if s["id"] == sid), None) if sid else None
        if schermo is None:
            return _json({"errore": "sessione non valida"}, 401)
        dati, errore = await corpo_json(request, 2048)
        if errore is not None:
            return errore
        if not isinstance(dati, dict):
            return _json({"errore": "dati non validi"}, 400)
        cr = getattr(hub, "cruscotto", None)
        try:
            amministra = bool(cr is not None and cr.amministra(schermo))
        except Exception:  # noqa: BLE001
            amministra = False
        try:
            out = hub.scaricamenti.gettone(schermo, str(dati.get("chiave") or ""),
                                           str(dati.get("formato") or ""), amministra)
        except Rifiuto as e:
            return _json({"errore": e.frase}, e.stato)
        return _json(out)

    async def scarica_file(request: Request):
        from starlette.responses import Response
        from .scarica import INTESTAZIONI, Rifiuto, disposizione
        client = request.client.host if request.client else ""
        if request.url.scheme != "https" and client not in ("127.0.0.1", "::1"):
            return PlainTextResponse("solo in HTTPS", status_code=403, headers=INTESTAZIONI)
        try:
            nome, tipo, dati = await asyncio.to_thread(
                hub.scaricamenti.prendi, request.path_params.get("gettone", ""), hub.valido)
        except Rifiuto as e:
            return PlainTextResponse(e.frase, status_code=e.stato, headers=INTESTAZIONI)
        except Exception as e:  # noqa: BLE001 — la conversione non riuscita è una risposta
            hub.log(f"[SCHERMI] scaricamento non riuscito: {type(e).__name__}: {e}")
            return PlainTextResponse("conversione non riuscita", status_code=500,
                                     headers=INTESTAZIONI)
        return Response(dati, media_type=tipo,
                        headers={**INTESTAZIONI, "Content-Disposition": disposizione(nome)})

    # ── giochi (05/10, giochi.py) ──
    async def gioco_documento(request: Request):
        """Il documento del riquadro di una partita: origine opaca (CSP sandbox), niente rete,
        solo i suoi script. Gettone a caso, valido finché la partita vive."""
        g = getattr(hub, "giochi", None)
        doc = g.documento(request.path_params.get("gettone", "")) if g is not None else None
        if doc is None:
            return PlainTextResponse("gioco non trovato", status_code=404,
                                     headers={"Cache-Control": "no-store",
                                              "Content-Security-Policy": "default-src 'none'",
                                              "X-Content-Type-Options": "nosniff"})
        from starlette.responses import HTMLResponse
        from ..estensioni.scheda import INTESTAZIONI
        html, csp = doc
        return HTMLResponse(html, headers={**INTESTAZIONI, "Content-Security-Policy": csp})

    async def gioco_api(request: Request):
        """Un messaggio di un riquadro, dalla pagina dello schermo: sessione in un'intestazione,
        JSON, solo in HTTPS fuori da questo computer. Non serve una conversazione a voce: si
        gioca toccando. Tutto il resto lo controlla giochi.Giochi.da_pagina."""
        g = getattr(hub, "giochi", None)
        if g is None or not getattr(hub.cfg, "giochi_enabled", True):
            return _json({"errore": "giochi spenti"}, 403)
        client = request.client.host if request.client else ""
        if request.url.scheme != "https" and client not in ("127.0.0.1", "::1"):
            return _json({"errore": "solo in HTTPS"}, 403)
        sess = request.headers.get("x-calliope-sessione", "")
        with lock:
            sid = sessioni.get(sess) if sess else None
        schermo = next((s for s in hub.abbinati() if s["id"] == sid), None) if sid else None
        if schermo is None:
            return _json({"errore": "sessione non valida"}, 401)
        massimo = int(getattr(hub.cfg, "giochi_messaggio_max", 4096) or 4096) + 1024
        dati, errore = await corpo_json(request, massimo)
        if errore is not None:
            return errore
        out = await asyncio.to_thread(g.da_pagina, schermo, dati)
        stato = int(out.pop("_stato", 200)) if isinstance(out, dict) else 500
        return _json(out, stato)

    app = Starlette(routes=[
        Route("/", file("index.html", "text/html; charset=utf-8")),
        Route("/schermo.css", file("schermo.css", "text/css; charset=utf-8")),
        Route("/schermo.js", file("schermo.js", "text/javascript; charset=utf-8")),
        Route("/api/abbinamento", nuovo_abbinamento, methods=["POST"]),
        Route("/api/abbinamento/stato", stato_abbinamento, methods=["POST"]),
        Route("/api/accedi", accedi, methods=["POST"]),
        Route("/eventi", eventi),
        Route("/api/salute", salute),
        Route("/api/scrivi", scrivi, methods=["POST"]),
        Route("/api/modulo", modulo, methods=["POST"]),
        Route("/api/immagine", immagine, methods=["POST"]),
        Route("/api/allegato", allegato, methods=["POST"]),
        Route("/api/cruscotto", cruscotto),
        Route("/api/scarica", scarica_gettone, methods=["POST"]),
        Route("/scarica/{gettone}", scarica_file),
        Route("/gioco/{gettone}", gioco_documento),
        Route("/api/gioco", gioco_api, methods=["POST"]),
        *telefono.rotte(hub),
        # /satellite: il comando per far diventare satellite un PC nuovo (03/10)
        *satellite_web.rotte(hub),
    ])
    app.state.sessioni = sessioni
    return _SoloHostNoti(app, _nomi_ammessi(getattr(hub.cfg, "schermi_nomi", ())))


def _gestore_eccezioni(loop, context):
    """Su Windows (ciclo Proactor) un browser che chiude di colpo la connessione (tablet
    spento, scheda chiusa) produce «ConnectionResetError» dentro asyncio: è normale, non va
    stampato con la traccia. Il resto passa al gestore predefinito."""
    exc = context.get("exception")
    if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
        return
    loop.default_exception_handler(context)


class _SenzaRumoreArresto(logging.Filter):
    """«timeout graceful shutdown exceeded» all'arresto con pagine collegate: atteso."""

    def filter(self, record):
        return "timeout graceful shutdown" not in str(record.msg)


logging.getLogger("uvicorn.error").addFilter(_SenzaRumoreArresto())


class ServerSchermi:
    """uvicorn in un thread daemon, sul socket aperto qui (così una porta occupata è un
    errore chiaro, non un `sys.exit` dentro il thread)."""

    def __init__(self, hub: Schermi, host: str, port: int, attesa_porta_s: float | None = None,
                 tls: dict | None = None):
        from ..porte import ATTESA_S
        self.attesa_porta_s = ATTESA_S if attesa_porta_s is None else attesa_porta_s
        # {"cert", "chiave", "spki", "impronta"} (schermi/tls.py): HTTPS; None = http
        self.tls = tls
        self.hub = hub
        self.host = host
        self.port = port
        self.server = None
        self.thread = None
        self.sock = None

    def avvia(self, attesa_s: float = 3.0):
        import uvicorn
        # SO_REUSEADDR fuori da Windows, SO_EXCLUSIVEADDRUSE su Windows, e qualche tentativo
        # se la porta è ancora del processo di prima (calliope/porte.py: 02/10, riavvio con
        # «calliope aggiorna» e «Address already in use»). OSError se resta occupata
        from ..porte import socket_in_ascolto
        sock = socket_in_ascolto(self.host, self.port, 64, attesa_s=self.attesa_porta_s,
                                 log=self.hub.log)
        sock.setblocking(False)
        self.sock = sock
        self.port = sock.getsockname()[1]
        # log_config=None: uvicorn non tocca la configurazione dei log del processo
        config = uvicorn.Config(crea_app(self.hub), log_config=None, log_level="warning",
                                access_log=False,
                                lifespan="off", ws=self._ws(), ws_max_size=2 ** 20,
                                http="h11", loop="asyncio",
                                timeout_graceful_shutdown=1, server_header=False,
                                proxy_headers=False,
                                **({"ssl_certfile": self.tls["cert"],
                                    "ssl_keyfile": self.tls["chiave"]} if self.tls else {}))
        self.server = uvicorn.Server(config)

        async def servi():
            asyncio.get_running_loop().set_exception_handler(_gestore_eccezioni)
            await self.server.serve(sockets=[sock])

        self.thread = threading.Thread(target=asyncio.run, args=(servi(),),
                                       name="schermi", daemon=True)
        self.thread.start()
        t0 = time.monotonic()
        while not self.server.started and time.monotonic() - t0 < attesa_s:
            if not self.thread.is_alive():
                break
            time.sleep(0.01)
        if not self.server.started:
            raise RuntimeError("il server degli schermi non è partito")
        self.hub.server_attivo = True
        return self

    def _ws(self) -> str:
        """WebSocket solo per il telefono, e solo se c'è websockets (sans-I/O: nessun codice
        nativo nuovo); altrimenti niente, come prima."""
        if getattr(self.hub.cfg, "telefono_enabled", True) and telefono.ws_disponibile():
            return "websockets-sansio"
        return "none"

    def ferma(self):
        self.hub.server_attivo = False
        self.hub.chiudi_tutte()
        if self.server is not None:
            self.server.should_exit = True
        if self.thread is not None:
            self.thread.join(timeout=3)
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
