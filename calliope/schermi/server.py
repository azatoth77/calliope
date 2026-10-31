"""
Il server web delle schede: Starlette + uvicorn **senza extra**, in un thread dentro il
processo di Calliope (docs/ricerche/2026-10-01-mappe-e-schermi.md, §9.1).

Niente `uvicorn[standard]`: httptools e uvloop non hanno wheel `win_arm64`. Starlette 1.7.0
e uvicorn 0.54.0 sono `py3-none-any`, come le loro dipendenze (anyio, h11, click, colorama):
nessun codice nativo nuovo (principio 4).

Indirizzi:
  GET  /                         la pagina (kiosk), con i suoi /schermo.css e /schermo.js (e
                                 /sezioni.js, le sezioni degli schermi personali: 27/10)
  POST /api/abbinamento          pagina senza token: {codice, richiesta, scade}
  POST /api/abbinamento/stato    «Authorization: Bearer <richiesta>» → attesa | abbinato | scaduto
  POST /api/accedi               «Authorization: Bearer <token>» → {sessione, nome, stanza…}
  GET  /eventi?sessione=…        SSE: benvenuto (con la cronologia e lo stato della voce),
                                 scheda, voce, revocato, ping; dall'08/10 sugli schermi
                                 personali la cronologia della persona (anche dopo un
                                 riavvio), «chat» (turni della conversazione) e «pulisci»
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
  POST /api/motore               «X-Calliope-Sessione», {azione: controlla|aggiorna, gettone?}:
                                 le azioni del cruscotto sulla ricerca web (09/10,
                                 cruscotto.py, web/motore.py): senza gettone lo dà (primo
                                 tocco), con il gettone fa partire l'azione (secondo tocco).
                                 Stesse regole di /api/cruscotto
  POST /api/scarica              «X-Calliope-Sessione», {chiave, formato}: l'indirizzo per
                                 scaricare il documento di una scheda (07/10, scarica.py), solo
                                 da uno schermo personale a cui la scheda è arrivata
  GET  /scarica/<gettone>        il file (MD, PDF, Word, Excel), convertito qui al primo
                                 accesso; il gettone vale pochi minuti e poche richieste
  POST /api/cassetto             «X-Calliope-Sessione», {azione: tieni|elimina|ancora, id: [..]}:
                                 i pulsanti della scheda del cassetto dei file (08/10,
                                 calliope/cassetto.py), solo da uno schermo personale e solo
                                 sui file del suo proprietario, o di un figlio sotto i 14
                                 anni per un tutore verificato dalla voce
  POST /api/conoscenti           «X-Calliope-Sessione», {azione: si|no, proposta, nome?,
                                 cognome?, nota?}: i tasti della proposta di un conoscente
                                 (14/10, decisione 0030, calliope/stanza/conoscenti.py), solo
                                 da uno schermo personale il cui proprietario amministra
  POST /api/schede               «X-Calliope-Sessione», {azione: pulisci}: «Pulisci le mie
                                 schede» (08/10, cronologia.py), solo da uno schermo personale
                                 e solo per le schede del suo proprietario
  POST /api/raccolte             «X-Calliope-Sessione», {} → {tessere} di «Le mie cose» (conto,
                                 stato, ultimo cambiamento), {raccolta} → {schede, nota?} della
                                 sua pagina (28/10, raccolte.py): letti dai servizi per il
                                 proprietario, solo da uno schermo personale, 30 al minuto
  POST /api/raccolte/cerca       «X-Calliope-Sessione», {raccolta, testo} → {schede, nota}: la
                                 ricerca in una pagina di «Le mie cose» (28/10, raccolte.cerca:
                                 i Documenti; l'Ufficio solo a chi amministra), in sola lettura, coi permessi della pagina; solo
                                 da uno schermo personale, 20 al minuto
  POST /api/conversazione        «X-Calliope-Sessione», {giorno?: oggi|ieri, schede?: bool,
                                 testo?} → {turni, nota}, {turno, indice} → {scheda},
                                 {foto} → {stato, scade?, src?} (la foto tenuta, 0034): i
                                 filtri, la ricerca e il dettaglio di una scheda piccola della
                                 Conversazione (28/10, #242, hub.chat_filtrata), solo da uno
                                 schermo personale e solo i turni del suo proprietario; 60 letture
                                 e 20 ricerche al minuto; il testo cercato non va nel registro
  POST /api/tocco                «X-Calliope-Sessione», {tocco, …}: un tocco che cambia qualcosa
                                 (28/10, tocchi.py: la spunta della lista, «+1 minuto» e «Ferma»
                                 sul timer), solo da uno schermo
                                 personale, anche senza una conversazione a voce; controllato
                                 qui, poi al ciclo della voce che lo fa passare da
                                 ToolRegistry.call col livello del proprietario e lo mette nella
                                 conversazione → {ok, in_coda}; un rifiuto arriva poi con
                                 l'evento SSE «tocco». 30 al minuto
  POST /api/studio/verifiche     «X-Calliope-Sessione», {} → {verifiche, prova}: le verifiche in
                                 bozza o aperte a cui mandare pagine (le proprie e, da tutore,
                                 quelle dei suoi minori; 29/10, passo 4.2 dello Studio, #281)
  POST /api/studio/home          «X-Calliope-Sessione», {} → la home dello Studio (30/10, #284):
                                 verifiche, piano, tappe, lettura, argomenti da decidere, pagine da
                                 parte, la sessione di oggi; sola lettura (le azioni sono tocchi)
  POST /api/vista                «X-Calliope-Sessione», {vista, verifica?, pagina?} → {ok}: la vista
                                 dello Studio aperta su questo schermo (in memoria, dati del turno)
  POST /api/studio/argomenti     «X-Calliope-Sessione», {verifica, azione?, argomento?, argomenti?,
                                 titolo?} → gli argomenti proposti di una verifica e la loro
                                 conferma: tieni, togli, rinomina, aggiungi, unisci, conferma,
                                 rifai (30/10, passo 4.4 dello Studio, #283); come le pagine,
                                 fuori dalla conversazione, in ombra solo chi amministra
  POST /api/studio/carte         «X-Calliope-Sessione», {verifica, azione?, carta?, domanda?,
                                 risposta?, argomento?, esito?} → le carte di una verifica e il
                                 loro ripasso: scrivi, correggi, togli, rimetti, esito, conferma
                                 (le proposte dal modello senza avvisi; 30/10,
                                 passo 6 dello Studio, #246); fuori dalla conversazione come gli
                                 argomenti, in ombra solo chi amministra
  POST /api/studio/prova         «X-Calliope-Sessione», {verifica, azione?, prova?, voce?,
                                 risposta?, esito?, domanda?…} → le prove della verifica (31/10,
                                 #248): la verifica finta scritta (inizia, rispondi, consegna,
                                 rivedi), le domande (domanda, togli_domanda, rimetti_domanda,
                                 conferma_domande), il tipo della prova vera e «conclusa». Le
                                 risposte attese solo dopo la consegna
  POST /api/studio/mappa         «X-Calliope-Sessione», {verifica, azione?, mappa?, nodo?,
                                 collegamento?, testo?, da?, a?, verbo?, x?, y?, argomento?,
                                 pagine?, tipo?, aiuto?} → le mappe concettuali di una verifica
                                 (30/10, passo 7 dello Studio, #247): lo scheletro, la mia mappa,
                                 a memoria, il controllo del codice; «pdf» → application/pdf della
                                 mia mappa. Fuori dalla conversazione come le carte, in ombra solo
                                 chi amministra
  POST /api/studio/ascolta       «X-Calliope-Sessione», {verifica, azione?, parte?, firma?, suona?}
                                 → il ripasso da ascoltare (31/10, #249, studio/ascolta.py): senza
                                 azione le parti; «audio» il WAV di una parte (202 mentre si
                                 prepara); «suona» il battito mentre suona; 409 con una prova
                                 aperta
  POST /api/studio/tutore        «X-Calliope-Sessione», {verifica, azione?, argomento?, parola?,
                                 prova?, voce?, esito?, indicazione?, testo?, ambito?, giorni?}
                                 → la vista del tutore di una verifica del suo minore (31/10,
                                 passo 10, #250 e #285, studio/tutore.py): padronanza (alla cieca
                                 in ombra), giudizi, «da guardare tu», prove, ripasso, mappe e
                                 carte, indicazioni; giudica, rivedi, indica, cambia, togli. Solo un
                                 tutore del minore, solo da uno schermo personale; gli altri «non
                                 c'è»
  POST /api/studio/pagina        «X-Calliope-Sessione», byte nudi (octet-stream), i dati in
                                 «X-Calliope-Studio» (URI): una foto di una pagina con i suoi
                                 angoli, o un PDF intero (29/10, #281, studio/pagine.py), nello
                                 Studio e mai nella conversazione; solo da uno schermo personale,
                                 dentro gli orari, anche senza conversazione a voce; con
                                 `studio_modo: spento` niente (404), in ombra solo chi amministra;
                                 `Content-Length` obbligatorio (411); senza sessione la risposta
                                 subito e la connessione chiusa, senza leggere il corpo (PR #312)
  GET  /satellite              il comando per un PC nuovo come satellite (satellite/web.py)
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
from .hub import Schermi, pubblica, registra_pagina, registra_scaricabili

PAGINA = Path(__file__).resolve().parent / "pagina"
PING_S = 15.0
# Eliminare dal cassetto si fa a voce (28/10 sera, seguito della #301)
CASSETTO_VOCE = "Per eliminarlo dimmelo a voce, con una frase intera."

_SICUREZZA = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    # Tutto da qui, niente da fuori: la pagina funziona senza internet
    # frame-src 'self' (05/10): solo i riquadri dei giochi (/gioco/…); anche un riquadro che
    # prova a navigare verso un altro sito lo ferma questa regola, prima della richiesta
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self'; "
                                "img-src 'self' data:; connect-src 'self'; frame-src 'self'; "
                                # Il ripasso da ascoltare (31/10, #249): l'audio dal blob preso
                                # con la sessione, come sul telefono
                                "media-src 'self' blob:; "
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


# Il resto del corpo piccolo prima di chiudere (30/10, #274). urllib (e non solo) manda le
# intestazioni e il corpo in due pezzi; un rifiuto che non legge il corpo (401, 403, 429, 413) o
# /api/accedi, che non lo legge mai, rispondeva e chiudeva la connessione con il corpo ancora in
# arrivo. Con dati non letti la chiusura diventa un RST (Windows e Linux), e il client che non ha
# ancora letto la risposta la perde: «ConnectionResetError» invece del 401 o del 429. Sotto carico
# capitava a qualche richiesta ogni cento (prova_raccolte 14 giri verdi su 24); con il ciclo a
# selettori a quasi tutte. Prima dell'ultima parte della risposta si legge il resto, solo per un
# corpo JSON dichiarato e piccolo e al più per CORPO_RESTO_S: gli invii grossi o lenti (le foto
# dello Studio, application/octet-stream) restano alle regole dei loro endpoint.
CORPO_RESTO_MAX = 64 * 1024
CORPO_RESTO_S = 2.0


class _LeggiIlResto:
    """Middleware ASGI: prima di chiudere la risposta legge il resto di un corpo JSON piccolo
    che l'app non ha letto, così la connessione si chiude con un FIN e non con un RST."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        intest = dict(scope.get("headers") or [])
        tipo = intest.get(b"content-type", b"").split(b";")[0].strip().lower()
        try:
            dichiarato = int(intest.get(b"content-length", b"-1"))
        except ValueError:
            dichiarato = -1
        # Con «Expect: 100-continue» il corpo arriva solo dopo il «100 Continue»: su un rifiuto il
        # client non lo manda, e leggerlo vorrebbe dire aspettare CORPO_RESTO_S per niente
        # (revisione della PR #331)
        if (tipo != b"application/json" or not 0 < dichiarato <= CORPO_RESTO_MAX
                or b"expect" in intest):
            return await self.app(scope, receive, send)
        finito = False

        async def ricevi():
            nonlocal finito
            m = await receive()
            if m.get("type") != "http.request" or not m.get("more_body", False):
                finito = True
            return m

        async def resto():
            letti = 0
            while not finito and letti <= CORPO_RESTO_MAX:
                letti += len((await ricevi()).get("body", b""))

        async def manda(m):
            if (m.get("type") == "http.response.body" and not m.get("more_body", False)
                    and not finito):
                try:
                    await asyncio.wait_for(resto(), CORPO_RESTO_S)
                except (asyncio.TimeoutError, OSError):
                    pass
            await send(m)

        await self.app(scope, ricevi, manda)


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


def _json(data, status: int = 200, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(data, status_code=status, headers={"Cache-Control": "no-store",
                                                           **_SICUREZZA, **(headers or {})})


# La frase del 429 di ogni limite (revisione della PR #269: le letture dicevano «troppi tocchi»)
TROPPI_TOCCHI = "troppi tocchi: aspetta un momento"
TROPPE_LETTURE = "Troppe richieste in poco tempo: riprovo fra qualche secondo."
TROPPE_RICERCHE = "Troppe ricerche in poco tempo: riprova fra qualche secondo."
LETTURE_AL_MINUTO = 60          # /api/raccolte per schermo (era 30 fino alla revisione della PR #269)
TROPPE_PAGINE = "Troppe pagine in poco tempo: aspetta un momento."
# /api/studio/pagina (revisione della PR #312): il corpo di un rifiuto si butta al più per tanti
# secondi; un invio vero si legge al più per tanti (15 MB in 2 minuti: ~1 Mbit/s)
STUDIO_SCARTA_S = 12.0
STUDIO_LEGGI_S = 120.0
# PDF divisi insieme al più (ognuno è un sottoprocesso; seconda revisione della PR #312)
STUDIO_PDF_INSIEME = 1


def crea_app(hub: Schermi) -> Starlette:
    """L'app Starlette per questo hub. Le sessioni SSE vivono qui (in memoria)."""
    sessioni: dict[str, tuple] = {}

    def _schermo_sessione(sess):
        """(numero, schermo) della sessione, o (numero, None). La sessione vale solo per lo schermo
        con cui è nata: il numero si riusa dopo una revoca, anche da terminale (#266, seconda
        revisione della PR #270), e una pagina vecchia non diventa lo schermo nuovo. Se l'elenco
        in memoria non torna, lo si rilegge una volta; una sessione di uno schermo che non c'è
        più si toglie."""
        with lock:
            v = sessioni.get(sess) if sess else None
        if not v:
            return None, None
        sid, creato = v
        for rileggi in (False, True):
            if rileggi:
                hub._rinfresca()
            s = next((s for s in hub.abbinati() if s["id"] == sid), None)
            if s is not None and s.get("creato") == creato:
                return sid, s
        with lock:
            sessioni.pop(sess, None)
        return sid, None
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
            sessioni[sess] = (s["id"], s.get("creato"))   # l'identità, non solo il numero (#266)
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
                      # Si scrive? (05/10; dal 28/10, #301, dallo schermo personale sempre)
                      "scrittura": hub.stato_scrittura(s),
                      # L'accento e le sezioni nascoste a un minore (27/10, aspetto.py)
                      "aspetto": hub.aspetto_di(s), "nascoste": hub.nascoste_di(s),
                      # «Parla» e le sezioni sul PC personale (27/10, passo 1b)
                      "parla": hub.parla_possibile(s),
                      "sezioni": bool(getattr(hub.cfg, "schermi_sezioni", True))})

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
        sid, schermo = _schermo_sessione(sess)
        if schermo is None:
            # 401: EventSource si ferma e la pagina rifà l'accesso (o torna ad abbinarsi)
            return PlainTextResponse("sessione non valida", status_code=401,
                                     headers={"Cache-Control": "no-store", **_SICUREZZA})
        client = request.client.host if request.client else ""
        personale = bool(schermo.get("proprietario"))
        # Uno schermo personale ritrova la cronologia del suo proprietario (08/10, anche dopo un
        # riavvio o appena abbinato), rivista contro lo stato vero: fuori dal ciclo del server
        ripresa = []
        if personale:
            try:
                ripresa = await asyncio.to_thread(hub.ripresa, schermo)
            except Exception as e:  # noqa: BLE001 — senza ripresa resta quella in memoria
                hub.log(f"[SCHERMI] ripresa della cronologia non riuscita: {type(e).__name__}")
        conn, storia = hub.collega(schermo, asyncio.get_running_loop(),
                                   locale=client in ("127.0.0.1", "::1"), ripresa=ripresa)
        # Accettata da `collega` con l'identità di adesso (#338, revisione della PR #341): se lo
        # schermo è passato a un'altra persona mentre si preparava la ripresa, niente della persona
        # di prima (conversazione, «Scarica» della chat, contesto) e la pagina rifà l'accesso
        accettata = bool(getattr(conn, "accettata", True))
        # La scheda «Conversazione» (08/10): dopo collega, così un turno archiviato nel frattempo
        # arriva comunque (la pagina scarta i doppioni per id)
        chat = await asyncio.to_thread(hub.chat_per, schermo) if personale and accettata else None
        if chat is not None and hub.registra_chat(schermo["id"], schermo.get("proprietario"),
                                                  schermo=schermo) is False:
            chat = None                 # cambiato proprio adesso: la conversazione non va
        contesto = hub.contesto_per(schermo) if accettata else None

        def da_rifare() -> str | None:
            """Subito prima del benvenuto: «revocato», «proprietario» o None (va bene)."""
            if not hub.valido(schermo["id"], schermo.get("creato")):
                return "revocato"
            if not accettata or not hub.valido(schermo["id"], schermo.get("creato"),
                                               schermo.get("proprietario")):
                return "proprietario"
            return None

        async def flusso():
            try:
                subito = da_rifare()
                if subito is not None:
                    # Niente benvenuto con la riga di prima: la pagina rifà l'accesso (o l'abbinamento)
                    yield "retry: 3000\n\n"
                    yield f"event: {subito}\ndata: {{}}\n\n"
                    if subito == "revocato":
                        with lock:
                            for k in [k for k, v in sessioni.items()
                                      if v == (schermo["id"], schermo.get("creato"))]:
                                sessioni.pop(k, None)
                    return
                benvenuto = {"nome": schermo["nome"], "stanza": schermo["stanza"],
                             "personale": personale,
                             "ora_server": time.time(), "cronologia": storia,
                             # Quante schede tiene la pagina (schermi_cronologia, 08/10)
                             "cronologia_max": hub._n_storia(),
                             # La conversazione della persona (solo schermi personali)
                             "chat": chat,
                             # Stato della voce (o None: questa pagina non lo mostra)
                             "voce": hub.voce_per(conn),
                             # La stanza ascolta? (13/10, conversazione di stanza)
                             "stanza": hub.stanza_per(conn),
                             # Si può scrivere adesso? (dal 28/10, #301: moduli a parte)
                             "scrittura": hub.stato_scrittura_per(conn),
                             # Uso del contesto dell'ultima risposta (schermi personali)
                             "contesto": contesto,
                             # La parola che sveglia («Dormo · di' «Computer»», 04/10)
                             "parola": (getattr(hub.cfg, "wake_names", None)
                                        or ["Calliope"])[0]}
                yield "retry: 3000\n\n"
                yield f"event: benvenuto\ndata: {json.dumps(benvenuto, ensure_ascii=False, default=str)}\n\n"
                while True:
                    try:
                        tipo, dati = await asyncio.wait_for(conn.coda.get(), PING_S)
                    except asyncio.TimeoutError:
                        if not hub.valido(schermo["id"], schermo.get("creato")):  # revocato o riusato
                            tipo, dati = "revocato", "{}"
                        elif not hub.valido(schermo["id"], schermo.get("creato"),
                                            schermo.get("proprietario")):
                            # Passato a un'altra persona (#338): la pagina rifà l'accesso
                            tipo, dati = "proprietario", "{}"
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
                            # Solo le sessioni di questo abbinamento: un numero riusato ha le sue (#338)
                            for k in [k for k, v in sessioni.items()
                                      if v == (schermo["id"], schermo.get("creato"))]:
                                sessioni.pop(k, None)
                        return
                    if tipo == "proprietario":
                        # Lo stesso schermo di un'altra persona (#338): il flusso finisce e la pagina
                        # svuota e rifà l'accesso col token, che vale ancora (la sessione nuova
                        # nasce con il proprietario di adesso)
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
        punto da cui passa ogni ingresso dalla pagina (testo, moduli, foto, file): sessione,
        HTTPS, limite al minuto e, dal 05/10, la conversazione a voce; dal 28/10 (#301) dallo
        schermo personale la casella, le foto e i file valgono sempre, i moduli no
        (`Schermi.scritto_consentito`)."""
        if not getattr(hub.cfg, "schermi_scritto", True):
            return None, _json({"errore": "scrittura spenta"}, 403)
        client = request.client.host if request.client else ""
        if request.url.scheme != "https" and client not in ("127.0.0.1", "::1"):
            return None, _json({"errore": "solo in HTTPS"}, 403)
        sess = request.headers.get("x-calliope-sessione", "")
        sid, schermo = _schermo_sessione(sess)
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
        # La conversazione a voce (05/10): dal 28/10 (#301) solo per i moduli e gli schermi di
        # stanza; dallo schermo personale si scrive sempre, al più come familiare (il tocco
        # lo stesso). Dopo il limite al minuto, così i rifiuti nel registro restano pochi
        ok, motivo = hub.scritto_consentito(schermo, canale)
        if not ok:
            hub.rifiuta_scritto(schermo, motivo, canale)
            return None, _json({"errore": hub.testo_senza_conversazione(canale),
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
                                 "schermo_id": schermo.get("id"), "schermo_creato": schermo.get("creato"), "schermo_proprietario": schermo.get("proprietario"),
                                 # Dalla modalità scrittura del telefono la risposta è solo
                                 # scritta (28/10, dopo la revisione della PR #304)
                                 "solo_scritto": personale and dati.get("solo_scritto") is True,
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
                                   "schermo_id": schermo.get("id"), "schermo_creato": schermo.get("creato"), "schermo_proprietario": schermo.get("proprietario"), "arrivato": time.time()}):
            return _json({"errore": "Calliope è occupata: riprova tra poco"}, 503)
        return _json({"ok": True})

    async def immagine(request: Request):
        """Una foto dallo schermo personale (05/10): byte controllati e riscritti in JPEG qui
        (immagini.prepara, in un thread: Pillow costa decine di ms), poi all'ingresso come
        il testo scritto. Mai su disco."""
        if not getattr(hub.cfg, "immagini_enabled", True):
            return _json({"errore": "foto spente"}, 403)
        # Le foto come la casella: dallo schermo personale sempre (28/10, #301)
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
                                   "solo_scritto": dati.get("solo_scritto") is True,
                                   "schermo_id": schermo.get("id"), "schermo_creato": schermo.get("creato"), "schermo_proprietario": schermo.get("proprietario"), "arrivato": time.time()}):
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
                "solo_scritto": request.headers.get("x-calliope-solo-scritto") == "1",
                "schermo_id": schermo.get("id"), "schermo_creato": schermo.get("creato"), "schermo_proprietario": schermo.get("proprietario"), "arrivato": time.time()}
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
        sid, schermo = _schermo_sessione(sess)
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

    # ── le azioni del cruscotto sulla ricerca web (09/10, cruscotto.py) ──
    async def motore(request: Request):
        """«Controlla» e «Aggiorna» di SearXNG: le prime azioni del cruscotto. Come
        /api/cruscotto (sessione in un'intestazione, HTTPS fuori da questo computer, schermo
        personale di chi amministra ricontrollato adesso), più il corpo JSON e i due tocchi
        con il gettone. L'azione gira in un thread del motore: la pagina ne vede la fase e
        l'esito nel cruscotto."""
        cr = getattr(hub, "cruscotto", None)
        if cr is None or getattr(cr, "motore", None) is None:
            return _json({"errore": "qui la ricerca web non c'è"}, 404)
        client = request.client.host if request.client else ""
        if request.url.scheme != "https" and client not in ("127.0.0.1", "::1"):
            return _json({"errore": "solo in HTTPS"}, 403)
        sess = request.headers.get("x-calliope-sessione", "")
        sid, schermo = _schermo_sessione(sess)
        if schermo is None:
            return _json({"errore": "sessione non valida"}, 401)
        if not cr.amministra(schermo):
            return _json({"errore": "solo sugli schermi personali di chi amministra"}, 403)
        dati, errore = await corpo_json(request, 1024)
        if errore is not None:
            return errore
        if not isinstance(dati, dict):
            return _json({"errore": "dati non validi"}, 400)
        azione = str(dati.get("azione") or "")
        gettone = dati.get("gettone")
        if not gettone:
            try:
                return _json(cr.gettone(schermo, azione))
            except ValueError as e:
                return _json({"errore": str(e)}, 429 if "troppe" in str(e) else 400)
        ok, frase = await asyncio.to_thread(cr.esegui, schermo, azione, str(gettone), hub.log)
        return _json({"ok": ok, "frase": frase}, 200 if ok else 409)

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
        sid, schermo = _schermo_sessione(sess)
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

    # ── il cassetto dei file (08/10, calliope/cassetto.py) ──
    pulsanti: dict[int, list[float]] = {}

    async def cassetto(request: Request):
        """I pulsanti della scheda del cassetto (Tieni, Elimina, Tieni ancora; Elimina tutti,
        Tieni tutti): sessione in un'intestazione e corpo JSON (come lo scritto: nessuna pagina
        di un altro sito li manda), solo in HTTPS fuori da questo computer, solo da uno schermo
        personale e solo sui file del suo proprietario. Non serve una conversazione a voce: la
        scheda è già sullo schermo del proprietario; e non c'è voce, quindi nemmeno la zona
        grigia. Dopo, la scheda aggiornata a tutti i suoi schermi personali."""
        cas = getattr(hub, "cassetto", None)
        if cas is None:
            return _json({"errore": "cassetto spento"}, 404)
        client = request.client.host if request.client else ""
        if request.url.scheme != "https" and client not in ("127.0.0.1", "::1"):
            return _json({"errore": "solo in HTTPS"}, 403)
        sess = request.headers.get("x-calliope-sessione", "")
        sid, schermo = _schermo_sessione(sess)
        if schermo is None:
            return _json({"errore": "sessione non valida"}, 401)
        persona = schermo.get("proprietario")
        if not persona:
            return _json({"errore": "solo dagli schermi personali"}, 403)
        ora = time.monotonic()
        with lock:
            fatti = [t for t in pulsanti.get(schermo["id"], []) if ora - t < 60.0]
            if len(fatti) >= 30:
                pulsanti[schermo["id"]] = fatti
                return _json({"errore": "troppi tocchi: aspetta un momento"}, 429)
            pulsanti[schermo["id"]] = fatti + [ora]
        dati, errore = await corpo_json(request, 4096)
        if errore is not None:
            return errore
        if not isinstance(dati, dict):
            return _json({"errore": "dati non validi"}, 400)
        ids = dati.get("id")
        ids = ids if isinstance(ids, list) else [ids]
        ids = [i for i in ids if isinstance(i, int) and not isinstance(i, bool)]

        def fai():
            from .. import minori
            reg = cas.registry
            prof = reg.by_id(persona) if reg is not None else None
            # Di chi sono i file: del proprietario dello schermo, oppure (08/10, decisione di
            # Dario) di un figlio di cui è tutore, solo in una conversazione verificata dalla
            # voce (Schermi.scrittura_consentita: riconosciuto dalla voce sopra soglia, non zona
            # grigia né frase breve né scritto) e con la regola d'età della visibilità
            # (conversazioni_visibili_ai_tutori: ogni minore, dal 14/10)
            padroni = {cas.proprietario(i) for i in ids} - {None}
            if len(padroni) > 1:
                return {"ok": False, "errore": "file di persone diverse", "_stato": 409}
            padrone = next(iter(padroni), persona)
            tutore = padrone != persona
            if tutore:
                figlio = reg.by_id(padrone) if reg is not None else None
                if (figlio is None or prof is None or not minori.e_minore(figlio)
                        or not minori.e_tutore(prof, figlio)
                        or not minori.conversazioni_visibili_ai_tutori(figlio)):
                    return {"ok": False, "errore": "Questi file non sono tuoi.", "_stato": 403}
                ok, _ = hub.scrittura_consentita(schermo)
                if not ok:
                    return {"ok": False, "_stato": 403, "codice": "senza_conversazione",
                            "errore": "Per i file di un ragazzo parlami prima a voce: "
                                      "di' «Calliope» e poi tocca di nuovo."}
            # Eliminare dal cassetto si fa a voce (28/10 sera, seguito della #301): dalla scheda
            # restano «Tieni» e «Tieni ancora»; un «elimina» arrivato lo stesso si ferma qui, coi
            # suoi sinonimi («cancella», «butta»: la mappa del tool, 29/10, #307). Dietro c'è la
            # stessa difesa in Cassetto.da_pagina
            from ..cassetto import azione_canonica
            if azione_canonica(dati.get("azione")) == "elimina":
                return {"ok": False, "_stato": 403, "codice": "serve_voce",
                        "errore": CASSETTO_VOCE}
            # «Tieni» di un tutore va nella SUA cartella dell'archivio (il ragazzo i documenti
            # di casa non li vede): come cassetto_gestisci a voce
            out = cas.da_pagina(padrone, str(dati.get("azione") or ""), ids,
                                minore=bool(not tutore and prof is not None
                                            and minori.e_minore(prof)),
                                nome_persona=getattr(prof, "name", None) if tutore else None)
            if out.get("ok"):
                # La scheda di prima, con i file che restano (o la frase se non ne resta), sugli
                # schermi personali di chi ha toccato
                aperti = None if tutore else cas.schede_aperte.get(persona)
                if aperti is not None:
                    resto = [r for r in (cas.prendi(persona, i) for i in sorted(aperti))
                             if r is not None]
                elif tutore:
                    resto = cas.elenco(padrone)
                else:
                    resto = cas.elenco(persona, cas.avviso_giorni * 86400.0)
                titolo = (f"I file di {getattr(reg.by_id(padrone), 'name', '')}".strip()
                          if tutore else "")
                cas.manda_scheda(hub, persona, cas.scheda(
                    padrone, resto, titolo=titolo,
                    tieni=tutore or not (prof is not None and minori.e_minore(prof)),
                    nota="" if resto else out.get("frase", "")))
            return out
        try:
            out = await asyncio.to_thread(fai)
        except Exception as e:  # noqa: BLE001
            hub.log(f"[CASSETTO] pulsante non riuscito: {type(e).__name__}: {e}")
            return _json({"errore": "non ci sono riuscita"}, 500)
        return _json(out, int(out.pop("_stato", 200 if out.get("ok") else 409)))

    # ── i conoscenti (14/10, decisione 0030, calliope/stanza/conoscenti.py) ──
    async def conoscenti_api(request: Request):
        """I tasti della proposta (Sì, con il nome proposto o uno diverso, cognome e nota; No):
        sessione in un'intestazione e corpo JSON, solo in HTTPS fuori da questo computer, solo
        da uno schermo personale il cui proprietario amministra (letto adesso). La proposta è
        arrivata solo lì; un sì crea un profilo da ospite, mai un familiare (per quello serve la
        voce: conoscente_livello)."""
        con = getattr(hub, "conoscenti", None)
        if con is None:
            return _json({"errore": "conoscenti spenti"}, 404)
        client = request.client.host if request.client else ""
        if request.url.scheme != "https" and client not in ("127.0.0.1", "::1"):
            return _json({"errore": "solo in HTTPS"}, 403)
        sess = request.headers.get("x-calliope-sessione", "")
        sid, schermo = _schermo_sessione(sess)
        if schermo is None:
            return _json({"errore": "sessione non valida"}, 401)
        persona = str(schermo.get("proprietario") or "")
        if not persona or persona not in con.admin_ids():
            return _json({"errore": "solo dallo schermo personale di chi amministra"}, 403)
        ora = time.monotonic()
        with lock:
            fatti = [t for t in pulsanti.get(-10_000 - schermo["id"], []) if ora - t < 60.0]
            if len(fatti) >= 20:
                pulsanti[-10_000 - schermo["id"]] = fatti
                return _json({"errore": "troppi tocchi: aspetta un momento"}, 429)
            pulsanti[-10_000 - schermo["id"]] = fatti + [ora]
        dati, errore = await corpo_json(request, 2048)
        if errore is not None:
            return errore
        if not isinstance(dati, dict):
            return _json({"errore": "dati non validi"}, 400)
        campi = {k: str(dati.get(k) or "")[:120] for k in ("proposta", "azione", "nome",
                                                            "cognome", "nota")}
        try:
            out = await asyncio.to_thread(con.risposta, campi["proposta"], campi["azione"],
                                          persona, campi["nome"], campi["cognome"],
                                          campi["nota"])
        except Exception as e:  # noqa: BLE001
            hub.log(f"[CONOSCENTI] tasto non riuscito: {type(e).__name__}")
            return _json({"errore": "non ci sono riuscita"}, 500)
        return _json(out, int(out.pop("_stato", 200 if out.get("ok") else 409)))

    # ── «Pulisci le mie schede» (08/10, cronologia.py) ──
    async def schede_api(request: Request):
        """Il tasto della pagina: la cronologia delle schede del proprietario dello schermo, su
        disco e sui suoi schermi personali. Sessione in un'intestazione e corpo JSON (come lo
        scritto), solo in HTTPS fuori da questo computer, solo da uno schermo personale e solo
        per le sue schede. Non serve una conversazione a voce: le schede sono già sue."""
        client = request.client.host if request.client else ""
        if request.url.scheme != "https" and client not in ("127.0.0.1", "::1"):
            return _json({"errore": "solo in HTTPS"}, 403)
        sess = request.headers.get("x-calliope-sessione", "")
        sid, schermo = _schermo_sessione(sess)
        if schermo is None:
            return _json({"errore": "sessione non valida"}, 401)
        persona = schermo.get("proprietario")
        if not persona:
            return _json({"errore": "si pulisce solo da uno schermo personale"}, 403)
        ora = time.monotonic()
        with lock:
            fatti = [t for t in pulsanti.get(-schermo["id"], []) if ora - t < 60.0]
            if len(fatti) >= 10:
                pulsanti[-schermo["id"]] = fatti
                return _json({"errore": "troppi tocchi: aspetta un momento"}, 429)
            pulsanti[-schermo["id"]] = fatti + [ora]
        dati, errore = await corpo_json(request, 1024)
        if errore is not None:
            return errore
        if not isinstance(dati, dict) or dati.get("azione") != "pulisci":
            return _json({"errore": "azione sconosciuta"}, 400)
        n = await asyncio.to_thread(hub.pulisci_schede, persona)
        return _json({"ok": True, "tolte": n,
                      "frase": "Schede tolte." if n else "Non c'erano schede da togliere."})

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
        sid, schermo = _schermo_sessione(sess)
        if schermo is None:
            return _json({"errore": "sessione non valida"}, 401)
        massimo = int(getattr(hub.cfg, "giochi_messaggio_max", 4096) or 4096) + 1024
        dati, errore = await corpo_json(request, massimo)
        if errore is not None:
            return errore
        out = await asyncio.to_thread(g.da_pagina, schermo, dati)
        stato = int(out.pop("_stato", 200)) if isinstance(out, dict) else 500
        return _json(out, stato)

    # ── l'aspetto (27/10, aspetto.py) ──
    scelte_aspetto: dict[int, list[float]] = {}

    async def aspetto_api(request: Request):
        """L'accento scelto in Io › Aspetto: sessione in un'intestazione, JSON {accento}, solo
        in HTTPS fuori da questo computer, solo da uno schermo personale."""
        client = request.client.host if request.client else ""
        if request.url.scheme != "https" and client not in ("127.0.0.1", "::1"):
            return _json({"errore": "solo in HTTPS"}, 403)
        sess = request.headers.get("x-calliope-sessione", "")
        sid, schermo = _schermo_sessione(sess)
        if schermo is None:
            return _json({"errore": "sessione non valida"}, 401)
        ora = time.monotonic()
        with lock:
            fatti = [t for t in scelte_aspetto.get(schermo["id"], []) if ora - t < 60.0]
            if len(fatti) >= 10:
                scelte_aspetto[schermo["id"]] = fatti
                return _json({"errore": "troppi tocchi: aspetta un momento"}, 429)
            scelte_aspetto[schermo["id"]] = fatti + [ora]
        dati, errore = await corpo_json(request, 512)
        if errore is not None:
            return errore
        scelta = str((dati or {}).get("accento") or "") if isinstance(dati, dict) else ""
        out = await asyncio.to_thread(hub.scegli_accento, schermo, scelta)
        stato = int(out.pop("_stato", 200))
        return _json(out, stato)

    # ── «Parla» sul PC personale (27/10, passo 1b) ──
    tocchi_parla: dict[int, list[float]] = {}

    async def parla_api(request: Request):
        """«Parla» sulla pagina dello schermo personale di un PC satellite: il suo satellite
        ascolta senza il nome. Sessione in un'intestazione, solo in HTTPS fuori da questo
        computer (la pagina del satellite passa dal ponte su 127.0.0.1), al più 20 al minuto."""
        client = request.client.host if request.client else ""
        if request.url.scheme != "https" and client not in ("127.0.0.1", "::1"):
            return _json({"errore": "solo in HTTPS"}, 403)
        sess = request.headers.get("x-calliope-sessione", "")
        sid, schermo = _schermo_sessione(sess)
        if schermo is None:
            return _json({"errore": "sessione non valida"}, 401)
        ora = time.monotonic()
        with lock:
            fatti = [t for t in tocchi_parla.get(schermo["id"], []) if ora - t < 60.0]
            if len(fatti) >= 20:
                tocchi_parla[schermo["id"]] = fatti
                return _json({"errore": "troppi tocchi: aspetta un momento"}, 429)
            tocchi_parla[schermo["id"]] = fatti + [ora]
        out = await asyncio.to_thread(hub.parla, schermo)
        stato = int(out.pop("_stato", 200))
        return _json(out, stato)

    # ── le raccolte di «Le mie cose» e i tocchi (28/10, raccolte.py e tocchi.py) ──
    letture_racc: dict[int, list[float]] = {}
    tocchi_fatti: dict[int, list[float]] = {}

    def schermo_personale(request: Request, conti: dict, n: int, frase: str = TROPPI_TOCCHI):
        """(schermo, None) per uno schermo personale con la sessione valida, in HTTPS fuori da
        questo computer, sotto il limite di `n` richieste al minuto; altrimenti (None, risposta).
        Non serve una conversazione a voce (decisione del 28/10). Oltre il limite 429 con `frase`,
        `Retry-After` e `riprova_s` (i secondi finché si libera un posto: la pagina riprova da sola)."""
        client = request.client.host if request.client else ""
        if request.url.scheme != "https" and client not in ("127.0.0.1", "::1"):
            return None, _json({"errore": "solo in HTTPS"}, 403)
        sess = request.headers.get("x-calliope-sessione", "")
        sid, schermo = _schermo_sessione(sess)
        if schermo is None:
            return None, _json({"errore": "sessione non valida"}, 401)
        if not schermo.get("proprietario"):
            return None, _json({"errore": "solo da uno schermo personale"}, 403)
        ora = time.monotonic()
        with lock:
            fatti = [t for t in conti.get(schermo["id"], []) if ora - t < 60.0]
            if len(fatti) >= n:
                conti[schermo["id"]] = fatti
                attesa = max(1, int(60.0 - (ora - fatti[0])) + 1)
                return None, _json({"errore": frase, "riprova_s": attesa}, 429, {"Retry-After": str(attesa)})
            conti[schermo["id"]] = fatti + [ora]
        return schermo, None

    def profilo_di(schermo: dict):
        if hub.profilo is None:
            return None
        try:
            return hub.profilo(schermo.get("proprietario"))
        except Exception:  # noqa: BLE001 — un profilo illeggibile: niente raccolte
            return None

    async def raccolte_api(request: Request):
        """Le tessere di «Le mie cose» ({} → {tessere}) o le schede di una raccolta
        ({raccolta} → {schede, nota?}), lette dai servizi per il proprietario dello schermo."""
        from . import raccolte
        # 60 letture al minuto (revisione della PR #269: con 30 chi sfoglia le raccolte, più le
        # riletture delle tessere, arrivava al limite e la pagina restava vuota)
        schermo, errore = schermo_personale(request, letture_racc, LETTURE_AL_MINUTO, TROPPE_LETTURE)
        if errore is not None:
            return errore
        dati, errore = await corpo_json(request, 512)
        if errore is not None:
            return errore
        if not isinstance(dati, dict):
            return _json({"errore": "dati non validi"}, 400)
        prof = profilo_di(schermo)
        if prof is None:
            return _json({"errore": "non so di chi è questo schermo"}, 403)
        quale = dati.get("raccolta")
        if quale is None:
            out = await asyncio.to_thread(raccolte.tessere, hub, prof, hub.log)
            return _json({"tessere": out})
        out = await asyncio.to_thread(raccolte.pagina, hub, prof, str(quale)[:40], schermo, hub.log)
        return schede_della_pagina(out, schermo)

    def schede_della_pagina(out: dict, schermo: dict):
        """La risposta di una pagina o di una ricerca: le chiavi private di «Scarica» (un
        documento, il registro di un lavoro, i file dell'archivio: 28/10, #258 e #259) restano
        sul server, registrate per questo schermo come per la cronologia ripresa."""
        stato = int(out.pop("_stato", 200))
        if isinstance(out.get("schede"), list):
            # Dall'ultima alla prima (registra_pagina): le prime della pagina perdono «Scarica» per
            # ultime oltre il tetto delle voci per schermo
            registra_pagina(hub.scaricamenti, schermo["id"], out["schede"], schermo["proprietario"], hub.log)
            out["schede"] = [pubblica(c) for c in out["schede"]]
        return _json(out, stato)

    ricerche_racc: dict[int, list[float]] = {}

    async def cerca_api(request: Request):
        """La ricerca in una pagina di «Le mie cose» (28/10, passo 2d, #259: i Documenti), in
        sola lettura: {raccolta, testo} → {schede, nota}. Solo da uno schermo personale, 20 al
        minuto, con i permessi della pagina (raccolte.cerca). Il testo cercato non va nel
        registro: i documenti di casa sono dati personali (come i tool `riservati`)."""
        from . import raccolte
        schermo, errore = schermo_personale(request, ricerche_racc, 20, TROPPE_RICERCHE)
        if errore is not None:
            return errore
        dati, errore = await corpo_json(request, 1024)
        if errore is not None:
            return errore
        if not isinstance(dati, dict) or not isinstance(dati.get("testo"), str) \
                or not isinstance(dati.get("raccolta"), str):
            return _json({"errore": "dati non validi"}, 400)
        prof = profilo_di(schermo)
        if prof is None:
            return _json({"errore": "non so di chi è questo schermo"}, 403)
        out = await asyncio.to_thread(raccolte.cerca, hub, prof, dati["raccolta"][:40],
                                      dati["testo"], hub.log)
        return schede_della_pagina(out, schermo)

    letture_conv: dict[int, list[float]] = {}
    ricerche_conv: dict[int, list[float]] = {}

    async def conversazione_api(request: Request):
        """I filtri e la ricerca della Conversazione (28/10, #242): {giorno?, schede?, testo?} →
        {turni, nota}. Solo da uno schermo personale (come la scheda «Conversazione» del
        benvenuto) e solo i turni del suo proprietario; non serve una conversazione a voce (è una
        lettura, come la cronologia). Una ricerca conta anche fra le ricerche (20 al minuto). Il
        testo cercato non va nel registro: sono le parole della persona."""
        dati, errore = await corpo_json(request, 1024)
        if errore is not None:
            return errore
        if not isinstance(dati, dict):
            return _json({"errore": "dati non validi"}, 400)
        if "foto" in dati:
            # La foto di una miniatura (28/10, decisione 0034): lo stato e, finché è tenuta, la
            # foto intera, solo dai propri schermi personali
            fid = dati.get("foto")
            if not isinstance(fid, int) or isinstance(fid, bool) or fid < 0:
                return _json({"errore": "dati non validi"}, 400)
            schermo, errore = schermo_personale(request, letture_conv, LETTURE_AL_MINUTO, TROPPE_LETTURE)
            if errore is not None:
                return errore
            out = await asyncio.to_thread(hub.chat_foto, schermo, fid)
            stato = int(out.pop("_stato", 200))
            return _json(out, stato)
        if "turno" in dati or "indice" in dati:
            # Il dettaglio di una scheda piccola leggera (revisione della PR #271)
            t, i = dati.get("turno"), dati.get("indice")
            if not (isinstance(t, int) and isinstance(i, int)) or isinstance(t, bool) \
                    or isinstance(i, bool) or t < 0 or not 0 <= i < 8:
                return _json({"errore": "dati non validi"}, 400)
            schermo, errore = schermo_personale(request, letture_conv, LETTURE_AL_MINUTO, TROPPE_LETTURE)
            if errore is not None:
                return errore
            out = await asyncio.to_thread(hub.chat_scheda, schermo, t, i)
            stato = int(out.pop("_stato", 200))
            return _json(out, stato)
        giorno, schede, testo = dati.get("giorno"), dati.get("schede", False), dati.get("testo", "")
        if giorno not in (None, "", "oggi", "ieri") or not isinstance(schede, bool) \
                or not isinstance(testo, str):
            return _json({"errore": "dati non validi"}, 400)
        testo = testo.strip()
        if testo:
            schermo, errore = schermo_personale(request, ricerche_conv, 20, TROPPE_RICERCHE)
        else:
            schermo, errore = schermo_personale(request, letture_conv, LETTURE_AL_MINUTO, TROPPE_LETTURE)
        if errore is not None:
            return errore
        out = await asyncio.to_thread(hub.chat_filtrata, schermo, giorno or None, schede, testo)
        stato = int(out.pop("_stato", 200))
        return _json(out, stato)

    async def tocco_api(request: Request):
        """Un tocco che cambia qualcosa (la spunta, i tasti del timer): controllato qui contro lo
        stato vero (tocchi.prepara), poi al ciclo della voce, che lo fa passare da
        ToolRegistry.call col livello del proprietario e lo mette nella conversazione."""
        from . import tocchi
        schermo, errore = schermo_personale(request, tocchi_fatti, 30)
        if errore is not None:
            return errore
        dati, errore = await corpo_json(request, 1024)
        if errore is not None:
            return errore
        if getattr(hub, "tool_ctx", None) is None:
            return _json({"errore": "Calliope non è pronta: riprova tra poco."}, 503)
        out = await asyncio.to_thread(tocchi.prepara, dati, hub.tool_ctx, profilo_di(schermo))
        if "errore" in out:
            return _json({"errore": out["errore"]}, int(out.get("_stato", 400)))
        if not hub.ingresso.metti({"tipo": "tocco", "tool": out["tool"],
                                   "argomenti": out["argomenti"],
                                   "descrizione": out["descrizione"],
                                   "tocco": str(dati.get("tocco")),
                                   # Ciò che la pagina ha toccato, per ritrovare il tasto con
                                   # l'esito (evento «tocco»): solo testi brevi
                                   "pagina": {k: str(dati.get(k))[:120]
                                              for k in ("lista", "voce", "chiave")
                                              if isinstance(dati.get(k), str)},
                                   # Lo Studio (#284): solo gli id che la pagina ha toccato
                                   **({"studio": {k: dati.get(k) for k in (
                                       "verifica", "argomento", "pagina")
                                       if isinstance(dati.get(k), int)}}
                                      if str(dati.get("tocco")).startswith("studio_") else {}),
                                   # Il timer toccato (#257): lo sceglie il codice, mai il modello
                                   "bersaglio": out.get("bersaglio"),
                                   "persona": schermo.get("proprietario"),
                                   "schermo": schermo.get("nome"),
                                   "stanza": schermo.get("stanza"),
                                   "schermo_id": schermo.get("id"), "schermo_creato": schermo.get("creato"), "schermo_proprietario": schermo.get("proprietario"), "arrivato": time.time()}):
            return _json({"errore": "Calliope è occupata: riprova tra poco"}, 503)
        return _json({"ok": True, "in_coda": True})

    # ── lo Studio: le pagine dei materiali (29/10, passo 4.2, #281, calliope/studio/pagine.py) ──
    invii_studio: dict[int, list[float]] = {}
    # I PDF che si stanno dividendo adesso (tutto nel ciclo di uvicorn: un contatore basta)
    pdf_in_corso = [0]
    letture_studio: dict[int, list[float]] = {}

    def studio_di(schermo: dict):
        """(servizio dello Studio, profilo del proprietario, None) oppure (None, None, risposta).
        Con `studio_modo: spento` niente; in ombra solo chi amministra (la pagina «prova» del
        banco); gli ospiti e i conoscenti mai (Studio.permesso, più sotto)."""
        st = getattr(hub, "studio", None) or getattr(getattr(hub, "servizi", None), "studio", None)
        if st is None:
            return None, None, _json({"errore": "Lo Studio è spento."}, 404)
        prof = profilo_di(schermo)
        if prof is None:
            return None, None, _json({"errore": "non so di chi è questo schermo"}, 403)
        if not st.per_schermi() and not (st.modo == "ombra" and getattr(prof, "admin", False)):
            return None, None, _json({"errore": "Lo Studio non è ancora acceso."}, 403)
        return st, prof, None

    async def studio_verifiche(request: Request):
        """{} → {verifiche, prova}: le verifiche in bozza o aperte a cui il proprietario dello
        schermo può mandare pagine (le sue e, da tutore, quelle dei suoi minori). Sola lettura."""
        schermo, errore = schermo_personale(request, letture_studio, LETTURE_AL_MINUTO,
                                            TROPPE_LETTURE)
        if errore is not None:
            return errore
        dati, errore = await corpo_json(request, 256)
        if errore is not None:
            return errore
        st, prof, errore = studio_di(schermo)
        if errore is not None:
            return errore
        from ..studio import NonPermesso
        try:
            out = await asyncio.to_thread(st.verifiche_per_pagine, prof)
        except NonPermesso:
            out = []
        return _json({"verifiche": out, "prova": not st.per_schermi(),
                      "max_pagine": int(getattr(hub.cfg, "studio_pagine_max", 80) or 80),
                      "pdf_max_pagine": int(getattr(hub.cfg, "studio_pdf_max_pagine", 40) or 40)})

    viste_fatte: dict[int, list[float]] = {}

    async def vista_api(request: Request):
        """{vista, verifica?, pagina?} → {ok}: la vista dello Studio aperta su questo schermo
        personale (30/10, passo 4.5, studio/vista.py), al più una al secondo; {vista: null} quando
        lo Studio si chiude. Solo in memoria, per la riga dei dati del turno."""
        from ..studio import vista as V
        schermo, errore = schermo_personale(request, viste_fatte, 60)
        if errore is not None:
            return errore
        dati, errore = await corpo_json(request, 256)
        if errore is not None:
            return errore
        v = V.valida(dati)
        if v is None:
            return _json({"errore": "vista non valida"}, 400)
        viste = getattr(hub, "viste_studio", None)
        if viste is not None:
            from ..studio.vista import chiave
            viste.metti(chiave(schermo), v)
        return _json({"ok": True})

    async def studio_home(request: Request):
        """{} → la home dello Studio (30/10, passo 4.5, #284): le verifiche del proprietario e,
        da tutore, dei suoi minori, con piano, tappe, lettura, argomenti da decidere e pagine da
        parte (`Studio.home`). Sola lettura, anche fuori orario: le azioni sono tocchi
        (/api/tocco) e passano dal ciclo, dove valgono gli orari."""
        schermo, errore = schermo_personale(request, letture_studio, LETTURE_AL_MINUTO,
                                            TROPPE_LETTURE)
        if errore is not None:
            return errore
        dati, errore = await corpo_json(request, 256)
        if errore is not None:
            return errore
        st, prof, errore = studio_di(schermo)
        if errore is not None:
            return errore
        from ..studio import NonPermesso
        try:
            out = await asyncio.to_thread(st.home, prof)
        except NonPermesso:
            out = {"verifiche": [], "sessione": None, "prova": not st.per_schermi()}
        except PermissionError:
            return _json({"errore": "Lo Studio adesso è in sola lettura."}, 503)
        # I tocchi solo con lo Studio per il modello (in ombra la home è la prova di chi
        # amministra: si guarda, non si tocca)
        out["tocchi"] = bool(st.per_modello())
        return _json(out)

    # Le azioni della conferma degli argomenti (30/10, passo 4.4, #283): sui dati della persona,
    # reversibili (un argomento tolto si tiene di nuovo, rinominato si rinomina) e fuori dalla
    # conversazione come le pagine del 4.2
    AZIONI_ARGOMENTI = ("tieni", "togli", "rinomina", "aggiungi", "unisci", "conferma", "rifai")

    def vista_argomenti(st, prof, vid) -> dict:
        """Gli argomenti di una verifica per la vista minima: titolo (un dato: la pagina lo
        scrive solo con textContent), stato, avvisi e le pagine citate col numero stampato o
        l'ordine; lo stato della verifica e dell'estrazione."""
        from ..studio import piano as P
        v = st.verifica(prof, vid)
        pagine = {p["id"]: p for p in st.pagine(prof, vid)}

        def nome(pid):
            p = pagine.get(pid)
            if p is None:
                return None
            n = P.numero_leggibile(p["numero"])
            return f"p. {n}" if n else f"foto {p['ordine']}"
        lettura = st.lettura(prof, vid)
        return {"verifica": {"id": v["id"], "materia": v["materia"], "data": v["data"],
                             "stato": v["stato"]},
                "argomenti": [{"id": a["id"], "titolo": a["titolo"], "stato": a["stato"],
                               "avvisi": [x for x in a["avvisi"] if isinstance(x, str)],
                               "pagine": [x for x in (nome(p) for p in a["pagine"]) if x]}
                              for a in st.argomenti(prof, vid)],
                "estrazione": st.estrazione(prof, vid),
                "lettura": {k: lettura[k] for k in ("totali", "lette", "illeggibili")},
                "prova": not st.per_schermi()}

    async def studio_argomenti(request: Request):
        """{verifica, azione?, argomento?, argomenti?, titolo?} → la vista degli argomenti. Senza
        azione sola lettura; con un'azione la fa (`Studio.segna_argomento`, `rinomina_argomento`,
        `aggiungi_argomento`, `unisci_argomenti`, `conferma_argomenti`, `rifai_argomenti`) coi
        permessi dello Studio (sua o, da tutore, del suo minore) e, per un minore, dentro gli
        orari. Lo Studio acceso come per le pagine (in ombra solo chi amministra, «prova»)."""
        schermo, errore = schermo_personale(request, letture_studio, LETTURE_AL_MINUTO,
                                            TROPPE_LETTURE)
        if errore is not None:
            return errore
        dati, errore = await corpo_json(request, 2048)
        if errore is not None:
            return errore
        st, prof, errore = studio_di(schermo)
        if errore is not None:
            return errore
        vid, azione = dati.get("verifica"), dati.get("azione")
        if not isinstance(vid, int) or isinstance(vid, bool) or vid < 1 or (
                azione is not None and azione not in AZIONI_ARGOMENTI):
            return _json({"errore": "richiesta non valida"}, 400)
        aid = dati.get("argomento")
        if azione in ("tieni", "togli", "rinomina") and (
                not isinstance(aid, int) or isinstance(aid, bool)):
            return _json({"errore": "manca l'argomento"}, 400)
        titolo = dati.get("titolo")
        if titolo is not None and (not isinstance(titolo, str) or len(titolo) > 200):
            return _json({"errore": "titolo non valido"}, 400)
        ids = dati.get("argomenti")
        if azione == "unisci" and (not isinstance(ids, list) or not 2 <= len(ids) <= 12 or any(
                not isinstance(x, int) or isinstance(x, bool) for x in ids)):
            return _json({"errore": "servono da due a dodici argomenti"}, 400)
        from .. import minori
        from ..studio import NonPermesso, NonTrovata
        if azione is not None:
            orario = minori.fuori_orario(prof)
            if orario:
                return _json({"errore": minori.frase_fuori_orario(prof, orario),
                              "codice": "fuori_orario"}, 403)

        def fai():
            extra = {}
            if azione in ("tieni", "togli", "rinomina", "unisci"):
                # Gli argomenti toccati devono essere di questa verifica
                suoi = {a["id"] for a in st.argomenti(prof, vid)}
                if not ({aid} if azione != "unisci" else set(ids)) <= suoi:
                    raise NonTrovata()
            if azione in ("tieni", "togli"):
                st.segna_argomento(prof, aid, azione == "tieni")
            elif azione == "rinomina":
                st.rinomina_argomento(prof, aid, titolo)
            elif azione == "aggiungi":
                st.aggiungi_argomento(prof, vid, titolo, [], proposto=False)
            elif azione == "unisci":
                st.unisci_argomenti(prof, ids, titolo)
            elif azione == "conferma":
                extra["da_decidere"] = st.conferma_argomenti(prof, vid).get("da_decidere", 0)
            elif azione == "rifai":
                st.rifai_argomenti(prof, vid)
            return {**vista_argomenti(st, prof, vid), **extra}
        try:
            out = await asyncio.to_thread(fai)
        except (NonTrovata, NonPermesso):
            return _json({"errore": "Questa verifica non c'è."}, 404)
        except PermissionError:
            return _json({"errore": "Lo Studio adesso è in sola lettura."}, 503)
        except ValueError:
            return _json({"errore": "Non va: controlla il titolo."}, 400)
        if azione is not None:
            hub.log(f"[STUDIO] argomenti della verifica {vid}: {azione}")
        return _json(out)

    # Le carte (30/10, passo 6, #246): sui dati della persona, reversibili (una carta tolta si
    # rimette, corretta si corregge), fuori dalla conversazione come gli argomenti: il testo delle
    # carte è un dato e non entra nella storia, e venti risposte non sono venti tocchi
    # «conferma» (seconda parte del passo 6): le carte proposte dal modello senza avvisi entrano
    # nel ripasso; «rimetti» su una proposta è il «Tieni» della persona, una per una
    AZIONI_CARTE = ("scrivi", "correggi", "togli", "rimetti", "esito", "conferma")

    def vista_carte(st, prof, vid) -> dict:
        """Le carte di una verifica per la vista: domanda e risposta (un dato: la pagina le
        scrive solo con textContent), stato, argomento, pagine, ripasso; quelle da ripassare
        adesso in ordine, ognuna con le tre scadenze dei tasti scritte dal codice; gli argomenti
        per la scelta."""
        from ..studio import carte as C
        from ..studio import piano as P
        v = st.verifica(prof, vid)
        pagine = {p["id"]: p for p in st.pagine(prof, vid)}

        def nome(pid):
            p = pagine.get(pid)
            if p is None:
                return None
            n = P.numero_leggibile(p["numero"])
            return f"p. {n}" if n else f"foto {p['ordine']}"
        args = st.argomenti(prof, vid)
        titoli = {a["id"]: a["titolo"] for a in args}
        adesso = st.adesso()
        vigilia = st._vigilia(v)
        carte = st.carte(prof, vid)
        due = [c["id"] for c in sorted((c for c in carte if c["da_ripassare"]),
                                        key=lambda c: (str(c["scadenza"] or ""), c["scatola"],
                                                       c["id"]))]

        def tasti(c):
            return {e: C.fra_quanto(C.prossima(c["scatola"], e, adesso, vigilia)[1], adesso)
                    for e in C.ESITI}
        return {"verifica": {"id": v["id"], "materia": v["materia"], "data": v["data"],
                             "stato": v["stato"]},
                "carte": [{"id": c["id"], "numero": c["numero"], "domanda": c["domanda"],
                           "risposta": c["risposta"], "stato": c["stato"],
                           "origine": c["origine"],
                           "avvisi": [x for x in c["avvisi"] if isinstance(x, str)],
                           "argomento": c["argomento"],
                           "argomento_numero": c["argomento_numero"],
                           "argomento_titolo": titoli.get(c["argomento"]),
                           "pagine": [x for x in (nome(p) for p in c["pagine"]) if x],
                           "scatola": c["scatola"], "fra": c["fra"],
                           "da_ripassare": c["da_ripassare"], "nel_piano": c["nel_piano"],
                           **({"tasti": tasti(c)} if c["da_ripassare"] else {})}
                          for c in carte],
                "da_ripassare": due,
                "argomenti": [{"id": a["id"], "numero": i, "titolo": a["titolo"]}
                              for i, a in enumerate(args, 1)
                              if a["stato"] in ("tenuto", "aggiunto")],
                "massimi": {"domanda": C.DOMANDA_MAX, "risposta": C.RISPOSTA_MAX},
                "prova": not st.per_schermi()}

    async def studio_carte(request: Request):
        """{verifica, azione?, carta?, domanda?, risposta?, argomento?, esito?} → la vista delle
        carte. Senza azione sola lettura (anche fuori orario); con un'azione la fa
        (`Studio.aggiungi_carta`, `correggi_carta`, `segna_carta`, `esito_carta`) coi permessi
        dello Studio e, per un minore, dentro gli orari. L'esito dei tasti è della persona (o del
        tutore): mai del modello."""
        schermo, errore = schermo_personale(request, letture_studio, LETTURE_AL_MINUTO,
                                            TROPPE_LETTURE)
        if errore is not None:
            return errore
        dati, errore = await corpo_json(request, 4096)
        if errore is not None:
            return errore
        st, prof, errore = studio_di(schermo)
        if errore is not None:
            return errore
        from ..studio import carte as C
        vid, azione = dati.get("verifica"), dati.get("azione")
        if not isinstance(vid, int) or isinstance(vid, bool) or vid < 1 or (
                azione is not None and azione not in AZIONI_CARTE):
            return _json({"errore": "richiesta non valida"}, 400)
        cid = dati.get("carta")
        if azione in ("correggi", "togli", "rimetti", "esito") and (
                not isinstance(cid, int) or isinstance(cid, bool)):
            return _json({"errore": "manca la carta"}, 400)
        testi = {}
        for k, mx in (("domanda", C.DOMANDA_MAX), ("risposta", C.RISPOSTA_MAX)):
            x = dati.get(k)
            if x is not None and (not isinstance(x, str) or len(x) > mx * 2):
                return _json({"errore": "testo non valido"}, 400)
            testi[k] = x
        if azione == "scrivi" and not (testi["domanda"] and testi["risposta"]):
            return _json({"errore": "servono la domanda e la risposta"}, 400)
        arg = dati.get("argomento")
        if arg is not None and (not isinstance(arg, int) or isinstance(arg, bool)):
            return _json({"errore": "argomento non valido"}, 400)
        esito = dati.get("esito")
        if azione == "esito" and esito not in C.ESITI:
            return _json({"errore": "esito non valido"}, 400)
        from .. import minori
        from ..studio import NonPermesso, NonTrovata, VerificaChiusa
        if azione is not None:
            orario = minori.fuori_orario(prof)
            if orario:
                return _json({"errore": minori.frase_fuori_orario(prof, orario),
                              "codice": "fuori_orario"}, 403)

        def fai():
            extra = {}
            if azione in ("correggi", "togli", "rimetti", "esito"):
                # La carta toccata deve essere di questa verifica
                if cid not in {c["id"] for c in st.carte(prof, vid)}:
                    raise NonTrovata()
            if azione == "scrivi":
                extra["scritta"] = st.aggiungi_carta(prof, vid, testi["domanda"],
                                                     testi["risposta"], argomento=arg)
            elif azione == "correggi":
                st.correggi_carta(prof, cid, testi["domanda"], testi["risposta"],
                                  **({"argomento": arg} if "argomento" in dati else {}))
            elif azione in ("togli", "rimetti"):
                st.segna_carta(prof, cid, azione == "rimetti")
            elif azione == "esito":
                r = st.esito_carta(prof, cid, esito)
                extra["ultimo"] = {"carta": cid, "esito": esito, "fra": r["fra"]}
            elif azione == "conferma":
                extra["confermate"] = st.conferma_carte(prof, vid)
            return {**vista_carte(st, prof, vid), **extra}
        try:
            out = await asyncio.to_thread(fai)
        except (NonTrovata, NonPermesso):
            return _json({"errore": "Questa verifica non c'è."}, 404)
        except VerificaChiusa:
            return _json({"errore": "La verifica è chiusa: niente carte nuove."}, 409)
        except PermissionError:
            return _json({"errore": "Lo Studio adesso è in sola lettura."}, 503)
        except ValueError:
            return _json({"errore": "Non va: controlla la domanda e la risposta."}, 400)
        if azione is not None:
            # Nel registro solo l'azione e gli id, mai il testo delle carte
            hub.log(f"[STUDIO] carte della verifica {vid}: {azione}"
                    + (f" {cid}" if isinstance(cid, int) else ""))
        return _json(out)

    # La vista del tutore (31/10, passo 10, #250 e #285, studio/tutore.py): solo un tutore del
    # minore; gli altri, la persona stessa compresa, lo stesso «non c'è» di una verifica che non
    # esiste. Le indicazioni sono testo di un adulto di casa: la pagina le scrive con textContent,
    # il registro non le vede mai
    AZIONI_TUTORE = ("giudica", "rivedi", "indica", "cambia", "togli")

    async def studio_tutore(request: Request):
        """{verifica, azione?, …} → la vista del tutore (`Studio.vista_tutore`). Senza azione sola
        lettura; con un'azione: «giudica» (argomento, parola), «rivedi» (prova, voce, esito),
        «indica» (testo, ambito: verifica | materia | tutto, giorni?), «cambia» (indicazione,
        testo?, giorni?), «togli» (indicazione)."""
        schermo, errore = schermo_personale(request, letture_studio, LETTURE_AL_MINUTO,
                                            TROPPE_LETTURE)
        if errore is not None:
            return errore
        dati, errore = await corpo_json(request, 2048)
        if errore is not None:
            return errore
        st, prof, errore = studio_di(schermo)
        if errore is not None:
            return errore
        from ..studio import tutore as TU

        def intero(k):
            x = dati.get(k)
            return x if isinstance(x, int) and not isinstance(x, bool) and 0 < x < 10 ** 9 \
                else None
        vid, azione = intero("verifica"), dati.get("azione")
        if vid is None or (azione is not None and azione not in AZIONI_TUTORE):
            return _json({"errore": "richiesta non valida"}, 400)
        testo = dati.get("testo")
        if testo is not None and (not isinstance(testo, str) or len(testo) > TU.INDICAZIONE_MAX * 2):
            return _json({"errore": "testo non valido"}, 400)
        giorni = dati.get("giorni")
        if giorni is not None and (not isinstance(giorni, int) or isinstance(giorni, bool)):
            return _json({"errore": "durata non valida"}, 400)
        ambito = dati.get("ambito", "verifica")
        if azione == "indica" and (ambito not in ("verifica", "materia", "tutto") or not testo):
            return _json({"errore": "richiesta non valida"}, 400)
        if azione == "giudica" and (intero("argomento") is None
                                    or not isinstance(dati.get("parola"), str)):
            return _json({"errore": "richiesta non valida"}, 400)
        if azione == "rivedi" and (intero("prova") is None or intero("voce") is None
                                   or not isinstance(dati.get("esito"), str)):
            return _json({"errore": "richiesta non valida"}, 400)
        if azione in ("cambia", "togli") and intero("indicazione") is None:
            return _json({"errore": "manca l'indicazione"}, 400)
        from ..studio import NonPermesso, NonTrovata, VerificaChiusa

        def fai():
            if azione == "giudica":
                return st.giudica(prof, vid, intero("argomento"), dati["parola"])
            if azione == "rivedi":
                return st.rivedi_da_tutore(prof, vid, intero("prova"), intero("voce"),
                                           dati["esito"])
            if azione in ("indica", "cambia", "togli"):
                # La verifica dice di chi è: l'indicazione è per lo stesso minore
                v = st._verifica_tutore(prof, vid)
                if azione == "indica":
                    st.scrivi_indicazione(prof, v["persona"], testo,
                                          verifica=v["id"] if ambito == "verifica" else None,
                                          materia=v["materia"] if ambito == "materia" else None,
                                          giorni=giorni, canale="schermo")
                else:
                    iid = intero("indicazione")
                    r = st.dati.uno("SELECT persona FROM studio_indicazioni WHERE id = ?", (iid,))
                    if r is None or r["persona"] != v["persona"]:
                        raise NonTrovata()
                    if azione == "cambia":
                        st.cambia_indicazione(prof, iid, testo, giorni)
                    else:
                        st.togli_indicazione(prof, iid)
            return st.vista_tutore(prof, vid)
        try:
            out = await asyncio.to_thread(fai)
        except (NonTrovata, NonPermesso):
            return _json({"errore": "Questa verifica non c'è."}, 404)
        except VerificaChiusa:
            return _json({"errore": "La verifica è chiusa."}, 409)
        except PermissionError:
            return _json({"errore": "Lo Studio adesso è in sola lettura."}, 503)
        except ValueError as e:
            # Le frasi dei rifiuti le scrive il codice (mai il testo arrivato)
            return _json({"errore": "Non va: " + str(e) + "."}, 400)
        if azione is not None:
            # Nel registro solo l'azione e gli id, mai il testo delle indicazioni
            hub.log(f"[STUDIO] vista del tutore, verifica {vid}: {azione}")
        out["prova"] = not st.per_schermi()
        return _json(out)

    # Le prove e le domande (31/10, passo 8, #248): la verifica finta scritta, le domande scritte
    # a mano o proposte dal lettore, il tipo della prova vera. Fuori dalla conversazione come le
    # carte (il testo è un dato: la pagina lo scrive con textContent); l'esito lo decide il codice,
    # «da rivedere» la persona o il tutore, mai il modello. Le risposte attese arrivano alla pagina
    # solo dopo la consegna (Studio._vista)
    AZIONI_PROVA = ("inizia", "rispondi", "consegna", "rivedi", "domanda", "togli_domanda",
                    "rimetti_domanda", "conferma_domande", "tipo", "conclusa")

    def vista_prove(st, prof, vid) -> dict:
        from ..studio import risposte as RS
        args = st.argomenti(prof, vid)
        d = st.domande(prof, vid)
        return {**st.prove(prof, vid),
                "domande": [{"id": x["id"], "numero": x["numero"], "tipo": x["tipo"],
                             "testo": x["testo"], "opzioni": x["opzioni"],
                             # Al tutore con la prova del minore aperta niente risposte
                             # (revisione della PR #348, nota 2)
                             "attesa": (RS.attesa_detta(x) if x.get("attesa") is not None
                                        else None), "chiave": x["chiave"],
                             "stato": x["stato"], "origine": x["origine"], "avvisi": x["avvisi"],
                             "argomento_numero": x["argomento_numero"]}
                            for x in d["domande"]],
                "domande_nascoste": d["nascoste"],
                "risposte_nascoste": bool(d.get("risposte_nascoste")),
                "argomenti": [{"id": a["id"], "numero": i, "titolo": a["titolo"]}
                              for i, a in enumerate(args, 1)
                              if a["stato"] in ("tenuto", "aggiunto")],
                "tipi": list(RS.TIPI),
                "massimi": {"testo": RS.TESTO_MAX, "opzione": RS.OPZIONE_MAX,
                            "attesa": RS.ATTESA_MAX, "risposta": RS.RISPOSTA_MAX},
                "prova": not st.per_schermi()}

    async def studio_prova(request: Request):
        """{verifica, azione?, prova?, voce?, risposta?, esito?, domanda?, tipo?, testo?,
        attesa?, opzioni?, chiave?, argomento?, prova_vera?, finestra?} → la vista delle prove.
        Senza azione sola lettura (anche fuori orario); con un'azione la fa coi permessi dello
        Studio e, per un minore, dentro gli orari. Le prove le fa solo la persona."""
        schermo, errore = schermo_personale(request, letture_studio, LETTURE_AL_MINUTO,
                                            TROPPE_LETTURE)
        if errore is not None:
            return errore
        dati, errore = await corpo_json(request, 8192)
        if errore is not None:
            return errore
        st, prof, errore = studio_di(schermo)
        if errore is not None:
            return errore
        from ..studio import risposte as RS
        vid, azione = dati.get("verifica"), dati.get("azione")
        if not _intero(vid) or vid < 1 or (azione is not None and azione not in AZIONI_PROVA):
            return _json({"errore": "richiesta non valida"}, 400)
        pid, voce, did = dati.get("prova"), dati.get("voce"), dati.get("domanda")
        if azione in ("rispondi", "consegna", "rivedi") and not _intero(pid):
            return _json({"errore": "manca la prova"}, 400)
        if azione in ("rispondi", "rivedi") and not _intero(voce):
            return _json({"errore": "manca la domanda"}, 400)
        if azione in ("togli_domanda", "rimetti_domanda") and not _intero(did):
            return _json({"errore": "manca la domanda"}, 400)
        risposta = dati.get("risposta")
        if risposta is not None and (not isinstance(risposta, str)
                                     or len(risposta) > RS.RISPOSTA_MAX * 2):
            return _json({"errore": "risposta non valida"}, 400)
        if azione == "rivedi" and dati.get("esito") not in RS.REVISIONI:
            return _json({"errore": "esito non valido"}, 400)
        campi = {}
        if azione == "domanda":
            for k, mx in (("testo", RS.TESTO_MAX), ("attesa", RS.ATTESA_MAX)):
                x = dati.get(k)
                if not isinstance(x, str) or len(x) > mx * 2:
                    return _json({"errore": "testo non valido"}, 400)
                campi[k] = x
            for k in ("opzioni", "chiave"):
                x = dati.get(k) or []
                if not isinstance(x, list) or len(x) > 5 or not all(
                        isinstance(o, str) and len(o) <= 2 * RS.OPZIONE_MAX for o in x):
                    return _json({"errore": "testo non valido"}, 400)
                campi[k] = x
            if dati.get("tipo") not in RS.TIPI:
                return _json({"errore": "tipo non valido"}, 400)
            arg = dati.get("argomento")
            if arg is not None and not _intero(arg):
                return _json({"errore": "argomento non valido"}, 400)
        if azione == "tipo" and (dati.get("prova_vera") not in ("scritta", "interrogazione")
                                 or not isinstance(dati.get("finestra", False), bool)):
            return _json({"errore": "tipo non valido"}, 400)
        from .. import minori
        from ..studio import NonPermesso, NonTrovata, VerificaChiusa
        if azione is not None:
            orario = minori.fuori_orario(prof)
            if orario:
                return _json({"errore": minori.frase_fuori_orario(prof, orario),
                              "codice": "fuori_orario"}, 403)

        def fai():
            extra = {}
            if azione in ("rispondi", "consegna", "rivedi"):
                # La prova toccata deve essere di questa verifica
                if st.vista_prova(prof, pid)["verifica"] != vid:
                    raise NonTrovata()
            if azione == "inizia":
                extra["iniziata"] = st.inizia_prova(prof, vid)["id"]
            elif azione == "rispondi":
                st.rispondi_prova(prof, pid, voce, risposta or "")
            elif azione == "consegna":
                extra["consegnata"] = st.consegna_prova(prof, pid)["id"]
            elif azione == "rivedi":
                st.rivedi_voce(prof, pid, voce, dati["esito"])
            elif azione == "domanda":
                extra["scritta"] = st.aggiungi_domanda(
                    prof, vid, dati["tipo"], campi["testo"], campi["attesa"], campi["opzioni"],
                    campi["chiave"], argomento=dati.get("argomento"))
            elif azione in ("togli_domanda", "rimetti_domanda"):
                if did not in {x["id"] for x in st.domande(prof, vid)["domande"]}:
                    raise NonTrovata()
                st.segna_domanda(prof, did, azione == "rimetti_domanda")
            elif azione == "conferma_domande":
                extra["confermate"] = st.conferma_domande(prof, vid)
            elif azione == "tipo":
                st.imposta(prof, vid, prova=dati["prova_vera"],
                           finestra=bool(dati.get("finestra", False)))
            elif azione == "conclusa":
                st.conclusa(prof, vid)
            return {**vista_prove(st, prof, vid), **extra}
        try:
            out = await asyncio.to_thread(fai)
        except (NonTrovata, NonPermesso):
            return _json({"errore": "Questa verifica non c'è."}, 404)
        except VerificaChiusa:
            return _json({"errore": "La verifica è chiusa."}, 409)
        except PermissionError:
            return _json({"errore": "Lo Studio adesso è in sola lettura."}, 503)
        except ValueError as e:
            from ..studio import prove as PV
            noti = {PV.POCHE: "Servono almeno 3 domande sugli argomenti del piano: scrivile o "
                              "fai le carte.",
                    PV.PROVA_APERTA: "C'è già una prova aperta su questa verifica.",
                    PV.SOLO_PERSONA: "La prova la fa chi studia, dal suo schermo.",
                    "la prova è chiusa": "La prova è chiusa: le risposte non cambiano più."}
            return _json({"errore": noti.get(str(e), "Non va: controlla la domanda e la "
                                                     "risposta.")}, 400)
        if azione is not None:
            # Nel registro solo l'azione e gli id, mai il testo
            hub.log(f"[STUDIO] prove della verifica {vid}: {azione}"
                    + (f" {pid}" if _intero(pid) else "") + (f" {did}" if _intero(did) else ""))
        return _json(out)

    # Le mappe concettuali (30/10, passo 7, #247): sui dati della persona, fuori dalla
    # conversazione come le carte (il testo dei concetti è un dato e non entra nella storia); il
    # controllo è del codice, mai del modello. Lo scheletro lo cambiano la persona e il tutore, la
    # mia mappa e a memoria solo la persona (Studio._mappa)
    AZIONI_MAPPA = ("scheletro", "nodo", "togli_nodo", "collega", "togli_collegamento", "sposta",
                    "riempi", "tieni", "conferma", "inizia", "rifai", "controlla", "carte",
                    "riordina", "riapri", "pdf", "libera", "finito", "indizio", "mostra")
    # «libera», «finito», «indizio», «mostra»: la mappa libera (30/10, passo 7c, #328)
    CON_MAPPA = ("nodo", "togli_nodo", "collega", "togli_collegamento", "sposta", "riempi",
                 "tieni", "conferma", "rifai", "controlla", "carte", "riordina", "riapri",
                 "finito", "indizio", "mostra")

    def _intero(x) -> bool:
        return isinstance(x, int) and not isinstance(x, bool)

    async def studio_mappa(request: Request):
        """{verifica, azione?, …} → la vista delle mappe (`Studio.vista_mappe`). Senza azione sola
        lettura (anche fuori orario); con un'azione la fa coi permessi dello Studio e, per un
        minore, dentro gli orari; «pdf» dà il PDF della mia mappa (anche fuori orario: si legge)."""
        from ..studio import mappa as M
        schermo, errore = schermo_personale(request, letture_studio, LETTURE_AL_MINUTO,
                                            TROPPE_LETTURE)
        if errore is not None:
            return errore
        dati, errore = await corpo_json(request, 4096)
        if errore is not None:
            return errore
        st, prof, errore = studio_di(schermo)
        if errore is not None:
            return errore
        vid, azione = dati.get("verifica"), dati.get("azione")
        if not _intero(vid) or vid < 1 or (azione is not None and azione not in AZIONI_MAPPA):
            return _json({"errore": "richiesta non valida"}, 400)
        mid = dati.get("mappa")
        if azione in CON_MAPPA and not _intero(mid):
            return _json({"errore": "manca la mappa"}, 400)
        for k in ("nodo", "collegamento", "da", "a", "argomento", "concetto"):
            if dati.get(k) is not None and not _intero(dati.get(k)):
                return _json({"errore": "richiesta non valida"}, 400)
        if azione in ("togli_nodo", "sposta", "riempi") and not _intero(dati.get("nodo")):
            return _json({"errore": "manca il concetto"}, 400)
        if azione == "togli_collegamento" and not _intero(dati.get("collegamento")):
            return _json({"errore": "manca il collegamento"}, 400)
        for k, mx in (("testo", M.NODO_MAX), ("verbo", M.VERBO_MAX)):
            x = dati.get(k)
            if x is not None and (not isinstance(x, str) or len(x) > mx * 4):
                return _json({"errore": "testo non valido"}, 400)
        pagine = dati.get("pagine")
        if pagine is not None and (not isinstance(pagine, list) or len(pagine) > 20
                                   or not all(_intero(x) for x in pagine)):
            return _json({"errore": "pagine non valide"}, 400)
        xy = [dati.get("x"), dati.get("y")]
        if azione == "sposta" and not all(isinstance(z, (int, float)) and not isinstance(z, bool)
                                          for z in xy):
            return _json({"errore": "posizione non valida"}, 400)
        tipo, aiuto = dati.get("tipo"), dati.get("aiuto")
        if azione == "inizia" and tipo not in (M.STUDENTE, M.MEMORIA):
            return _json({"errore": "tipo non valido"}, 400)
        if azione == "pdf" and tipo not in (None, M.STUDENTE, M.LIBERA):
            return _json({"errore": "tipo non valido"}, 400)
        if azione == "mostra" and not _intero(dati.get("concetto")):
            return _json({"errore": "manca il concetto"}, 400)
        if aiuto is not None and aiuto not in M.AIUTI:
            return _json({"errore": "aiuto non valido"}, 400)
        from .. import minori
        from ..studio import NonPermesso, NonTrovata, VerificaChiusa
        if azione not in (None, "pdf"):
            orario = minori.fuori_orario(prof)
            if orario:
                return _json({"errore": minori.frase_fuori_orario(prof, orario),
                              "codice": "fuori_orario"}, 403)

        def fai():
            extra = {}
            if azione in CON_MAPPA:
                # La mappa toccata deve essere di questa verifica
                vm = st.vista_mappe(prof, vid)
                suoi = {m["id"] for m in (vm.get(k) for k in ("scheletro", "mia", "memoria",
                                                               "libera")) if m}
                if mid not in suoi:
                    raise NonTrovata()
            if azione == "pdf":
                return st.pdf_mappa(prof, vid, tipo or M.STUDENTE)
            if azione == "scheletro":
                extra["mappa"] = st.scrivi_scheletro(prof, vid)
            elif azione == "nodo":
                kw = {}
                if "argomento" in dati:
                    kw["argomento"] = dati.get("argomento")
                if pagine is not None:
                    kw["pagine"] = pagine
                extra["nodo"] = st.nodo_mappa(prof, mid, dati.get("testo"), dati.get("nodo"), **kw)
            elif azione == "togli_nodo":
                st.togli_nodo(prof, mid, dati["nodo"])
            elif azione == "collega":
                if dati.get("collegamento") is None and not (_intero(dati.get("da"))
                                                             and _intero(dati.get("a"))):
                    raise ValueError("mancano i concetti")
                extra["collegamento"] = st.collega(prof, mid, dati.get("da"), dati.get("a"),
                                                   dati.get("verbo"), dati.get("collegamento"))
            elif azione == "togli_collegamento":
                st.togli_collegamento(prof, mid, dati["collegamento"])
            elif azione == "sposta":
                st.sposta_nodo(prof, mid, dati["nodo"], xy[0], xy[1])
            elif azione == "riempi":
                st.riempi(prof, mid, dati["nodo"], dati.get("testo") or "")
            elif azione == "tieni":
                st.tieni_mappa(prof, mid, dati.get("nodo"), dati.get("collegamento"))
            elif azione == "conferma":
                extra["confermato"] = st.conferma_scheletro(prof, mid)
            elif azione == "inizia":
                extra["mappa"] = st.inizia_mappa(prof, vid, tipo, aiuto)
            elif azione == "rifai":
                extra["mappa"] = st.rifai_mappa(prof, mid, aiuto)
            elif azione == "controlla":
                extra["controllo"] = st.controlla_mappa(prof, mid)["conti"]
            elif azione == "carte":
                extra["carte"] = st.carte_dagli_errori(prof, mid)
            elif azione == "riordina":
                st.riordina_mappa(prof, mid)
            elif azione == "riapri":
                extra["riaperto"] = st.riapri_scheletro(prof, mid)
            elif azione == "libera":
                extra["mappa"] = st.inizia_libera(prof, vid)
            elif azione == "finito":
                c = st.finisci_libera(prof, mid)
                extra["finito"] = {"conti": c.get("conti"), "tentativi": c.get("tentativi")}
            elif azione == "indizio":
                extra["indizio"] = st.indizio_libera(prof, mid)
            elif azione == "mostra":
                st.mostra_concetto(prof, mid, dati["concetto"])
            return {**st.vista_mappe(prof, vid), **extra}
        try:
            out = await asyncio.to_thread(fai)
        except (NonTrovata, NonPermesso):
            return _json({"errore": "Questa verifica non c'è."}, 404)
        except VerificaChiusa:
            return _json({"errore": "La verifica è chiusa: la mappa si guarda e si scarica."},
                         409)
        except PermissionError:
            return _json({"errore": "Lo Studio adesso è in sola lettura."}, 503)
        except ValueError as e:
            # Le frasi dei ValueError sono del codice (mai il testo della mappa)
            return _json({"errore": f"Non va: {e}."}, 400)
        if azione is not None:
            # Nel registro solo l'azione e gli id, mai il testo dei concetti
            hub.log(f"[STUDIO] mappa della verifica {vid}: {azione}"
                    + (f" {mid}" if _intero(mid) else ""))
        if azione == "pdf":
            from starlette.responses import Response
            return Response(out, media_type="application/pdf",
                            headers={"Cache-Control": "no-store",
                                     "X-Content-Type-Options": "nosniff",
                                     "Content-Security-Policy": "sandbox",
                                     "Content-Disposition":
                                         f'attachment; filename="mappa-{vid}.pdf"'})
        return _json(out)

    # Il ripasso da ascoltare (31/10, passo 9, #249, studio/ascolta.py): le parti, l'audio di una
    # parte (WAV, preso dalla pagina con la sessione nell'intestazione e suonato da un URL blob:
    # niente gettoni nell'indirizzo) e il battito mentre suona. Con una prova aperta niente (409)
    letture_ascolta: dict[int, list[float]] = {}
    # La pausa della stanza del satellite del PC mentre il ripasso suona: 2 minuti (l'analisi
    # della #249), rinnovata dal battito di 30 s quando ne restano meno di 75 s; dopo una pagina
    # chiusa senza «non suona più» scade da sola
    ASCOLTA_PAUSA_STANZA_MIN = 2.0
    ASCOLTA_RINNOVA_S = 75.0
    # Gli schermi che suonano il ripasso per satellite (revisione della PR #345): {sat: {schermo:
    # ultimo battito}}. La stanza si riprende solo quando nessuno suona più
    suonano: dict = {}
    suonano_lock = threading.Lock()

    def stanza_del_ripasso(schermo: dict, suona: bool) -> bool:
        """Half-duplex sul PC personale legato a un satellite: mentre il ripasso suona la stanza
        di quel satellite va in pausa con motivo «ripasso» (rinnovata dal battito); quando smette
        su tutti i suoi schermi si riprende, solo se la pausa è ancora la sua. La pausa scelta da
        una persona non si tocca mai. True se c'è una pausa del ripasso."""
        stanza = getattr(getattr(hub, "servizi", None), "stanza", None)
        sat = schermo.get("satellite")
        if stanza is None or not sat:
            return False
        ora = time.time()
        with suonano_lock:
            chi = suonano.setdefault(sat, {})
            if suona:
                chi[schermo.get("id")] = ora
            else:
                chi.pop(schermo.get("id"), None)
            for k in [k for k, t in chi.items() if ora - t > 3 * 30.0]:
                chi.pop(k, None)                 # una pagina chiusa senza dirlo
            altri = bool(chi)
        try:
            p = stanza.stato_pausa(sat)
            nostra = p is not None and p.get("motivo") == "ripasso"
            if suona:
                fino = (p or {}).get("fino")
                if p is None or (nostra and fino and fino - ora < ASCOLTA_RINNOVA_S):
                    stanza.pausa(sat, "ripasso", minuti=ASCOLTA_PAUSA_STANZA_MIN)
                    return True
                return nostra
            if nostra and not altri:
                stanza.riprendi(sat)
        except Exception as e:  # noqa: BLE001 — la stanza non ferma il ripasso
            hub.log(f"[STUDIO] pausa della stanza per il ripasso: {type(e).__name__}")
        return False

    async def studio_ascolta(request: Request):
        """{verifica, azione?, parte?, firma?, suona?} → senza azione le parti del ripasso
        (`Studio.ascolto_parti`, anche fuori orario: è una lettura); `audio` il WAV di una parte
        (200, audio/wav) o 202 {pronto: false, fatto} mentre si prepara (per un minore dentro gli
        orari); `suona` il battito mentre suona ({prova}). Permessi dello Studio: la persona e il
        tutore del minore; ospiti mai. Il titolo delle parti è un dato: la pagina usa textContent."""
        schermo, errore = schermo_personale(request, letture_ascolta, 2 * LETTURE_AL_MINUTO,
                                            TROPPE_LETTURE)
        if errore is not None:
            return errore
        dati, errore = await corpo_json(request, 1024)
        if errore is not None:
            return errore
        st, prof, errore = studio_di(schermo)
        if errore is not None:
            return errore
        from ..studio import ascolta as A
        if A.modo(hub.cfg) != "attiva":
            return _json({"errore": "Il ripasso da ascoltare qui non è acceso."}, 404)
        vid, azione = dati.get("verifica"), dati.get("azione")
        if not _intero(vid) or vid < 1 or azione not in (None, "audio", "suona"):
            return _json({"errore": "richiesta non valida"}, 400)
        parte, firma = dati.get("parte"), dati.get("firma")
        if azione == "audio" and (not _intero(parte) or not 1 <= parte <= 500 or (
                firma is not None and (not isinstance(firma, str) or len(firma) > 32))):
            return _json({"errore": "richiesta non valida"}, 400)
        from .. import minori
        from ..studio import NonPermesso, NonTrovata
        if azione == "audio":
            orario = minori.fuori_orario(prof)
            if orario:
                return _json({"errore": minori.frase_fuori_orario(prof, orario),
                              "codice": "fuori_orario"}, 403)

        def fai():
            if azione == "suona":
                suona = bool(dati.get("suona"))
                try:
                    prova = st.prova_in_corso(prof, vid) is not None
                except (NonTrovata, NonPermesso):
                    raise
                pausa = stanza_del_ripasso(schermo, suona and not prova)
                return {"prova": prova, "stanza_in_pausa": pausa}
            if azione == "audio":
                return st.ascolto_audio(prof, vid, parte, firma)
            return st.ascolto_parti(prof, vid)
        try:
            out = await asyncio.to_thread(fai)
        except (NonTrovata, NonPermesso):
            return _json({"errore": "Questa verifica non c'è."}, 404)
        except A.ProvaAperta:
            return _json({"errore": "C'è una prova in corso: il ripasso torna dopo la consegna.",
                          "prova": True}, 409)
        except ValueError:
            return _json({"errore": "Questa parte non c'è più: ricarico il ripasso.",
                          "cambiato": True}, 409)
        if azione != "audio":
            return _json(out)
        if out.get("cambiato"):
            return _json({"errore": "Il ripasso è cambiato: ricarico le parti.", "cambiato": True,
                          "firma": out.get("firma")}, 409)
        if out.get("senza_voce"):
            return _json({"errore": "Qui l'audio del ripasso non si può preparare: chiedimelo a "
                                    "voce."}, 503)
        if "file" not in out:
            return _json({"pronto": False, "fatto": out.get("fatto") or 0.0}, 202)
        hub.log(f"[STUDIO] ripasso della verifica {vid}: parte {parte} allo schermo")
        return FileResponse(out["file"], media_type="audio/wav",
                            headers={"Cache-Control": "no-store",
                                     "X-Content-Type-Options": "nosniff",
                                     "Content-Security-Policy": "sandbox",
                                     "Content-Disposition":
                                         f'inline; filename="ripasso-{vid}-parte-{parte}.wav"'})

    def meta_studio(request: Request):
        """I dati dell'invio da «X-Calliope-Studio» (JSON codificato come URI, al più 2 KB):
        {verifica, materiale?, angoli?, nome?}, o None se non sono validi."""
        from urllib.parse import unquote
        grezzo = request.headers.get("x-calliope-studio", "")
        if not grezzo or len(grezzo) > 2048:
            return None
        try:
            m = json.loads(unquote(grezzo))
        except ValueError:
            return None
        if not isinstance(m, dict):
            return None
        vid, mid = m.get("verifica"), m.get("materiale")
        if not isinstance(vid, int) or isinstance(vid, bool) or vid < 1:
            return None
        if mid is not None and (not isinstance(mid, int) or isinstance(mid, bool) or mid < 1):
            return None
        nome = m.get("nome")
        if nome is not None and not isinstance(nome, str):
            return None
        # Il nome del file è solo un titolo: niente percorsi, niente caratteri di controllo
        nome = re.sub(r"[\x00-\x1f\x7f]", " ", (nome or "").replace("\\", "/").split("/")[-1])
        nome = " ".join(nome.split())[:60] or None
        return {"verifica": vid, "materiale": mid, "angoli": m.get("angoli"), "nome": nome,
                # Un PDF dichiarato (passo 4.5): il 429 si dà prima di leggere il corpo
                "pdf": m.get("pdf") is True or bool(nome and nome.lower().endswith(".pdf"))}

    async def studio_pagina(request: Request):
        """Vedi `_studio_pagina`. Revisione della PR #312: senza una sessione valida, senza
        `Content-Length` o con una lunghezza oltre il tetto la risposta arriva subito e la
        connessione si chiude, senza leggere niente. Solo dopo una sessione valida e lo Studio
        acceso un rifiuto (verifica, orari, pagine) legge e butta il corpo dichiarato, al più per
        `STUDIO_SCARTA_S` secondi: il telefono che manda una foto di qualche MB riceve la frase
        del rifiuto e non una connessione chiusa a metà, e un invio lento non tiene niente."""
        request.state.studio_letto = False
        request.state.studio_scarta = False
        risposta = await _studio_pagina(request)
        if request.state.studio_scarta and not request.state.studio_letto:
            async def scarta():
                async for _pezzo in request.stream():
                    pass
            try:
                await asyncio.wait_for(scarta(), STUDIO_SCARTA_S)
            except Exception:  # noqa: BLE001 — lento o andato via: si chiude e basta
                risposta.headers["Connection"] = "close"
        return risposta

    async def _studio_pagina(request: Request):
        """Una pagina (foto JPEG o PNG, con i quattro angoli del telefono) o un PDF intero dallo
        schermo personale, nei byte nudi (application/octet-stream, come /api/allegato); i dati
        dell'invio in «X-Calliope-Studio». Fuori dalla conversazione e dall'album: la pagina va
        nello Studio, nello stato «da leggere». Nell'ordine: sessione dello schermo personale
        (in HTTPS) e invii al minuto; lo Studio acceso; la verifica (sua o del suo minore, in
        bozza o aperta: Studio._verifica e _chi_puo); gli orari del minore che manda; la
        dimensione; il tipo vero dai byte; poi il controllo della pagina in un thread."""
        n = max(1, int(getattr(hub.cfg, "studio_pagine_al_minuto", 40) or 40))
        schermo, errore = schermo_personale(request, invii_studio, n, TROPPE_PAGINE)
        if errore is not None:
            errore.headers["Connection"] = "close"
            return errore
        mb_foto = float(getattr(hub.cfg, "studio_pagina_max_mb", 15.0) or 15.0)
        mb_pdf = float(getattr(hub.cfg, "studio_pdf_max_mb", 30.0) or 30.0)
        max_b = int(max(mb_foto, mb_pdf) * 1_000_000)
        # La lunghezza dichiarata è obbligatoria (niente invii a pezzi) e sotto il tetto
        try:
            dichiarati = int(request.headers.get("content-length", ""))
        except ValueError:
            dichiarati = -1
        if dichiarati < 0:
            return _json({"errore": "serve la lunghezza del file"}, 411, {"Connection": "close"})
        if dichiarati > max_b:
            return _json({"errore": "file troppo grande"}, 413, {"Connection": "close"})
        st, prof, errore = studio_di(schermo)
        if errore is not None:
            errore.headers["Connection"] = "close"
            return errore
        # Da qui un rifiuto legge e butta il corpo dichiarato, con un tempo massimo
        request.state.studio_scarta = True
        tipo = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if tipo != "application/octet-stream":
            return _json({"errore": "serve application/octet-stream"}, 415)
        meta = meta_studio(request)
        if meta is None:
            return _json({"errore": "dati dell'invio non validi"}, 400)
        from .. import minori
        from ..studio import NonPermesso, NonTrovata, TroppePagine, VerificaChiusa
        # Gli orari dei tutori prima della verifica (revisione della PR #312): fuori orario un
        # minore non manda pagine, come per i tocchi
        orario = minori.fuori_orario(prof)
        if orario:
            return _json({"errore": minori.frase_fuori_orario(prof, orario),
                          "codice": "fuori_orario"}, 403)
        try:
            v = await asyncio.to_thread(st.verifica_per_pagine, prof, meta["verifica"])
        except (NonTrovata, NonPermesso):
            return _json({"errore": "Questa verifica non c'è."}, 404)
        except VerificaChiusa:
            return _json({"errore": "Questa verifica è chiusa: non prende pagine nuove."}, 409)
        except PermissionError:
            return _json({"errore": "Lo Studio adesso è in sola lettura."}, 503)
        massimo = int(getattr(hub.cfg, "studio_pagine_max", 80) or 80)
        if v["n_pagine"] >= massimo:
            return _json({"errore": f"Questa verifica ha già {massimo} pagine."}, 413)
        # Un PDF dichiarato (il nome di un PDF, o `pdf: true`) mentre un altro si divide: il 429
        # prima di leggere il corpo (terza revisione della PR #312, fatto con la 4.5), e il corpo
        # dichiarato si butta come per gli altri rifiuti
        if meta["pdf"] and pdf_in_corso[0] >= STUDIO_PDF_INSIEME:
            return _json({"errore": "Sto già dividendo un PDF: riprova fra poco.",
                          "riprova_s": 5}, 429, {"Retry-After": "5"})
        troppo = _json({"errore": "file troppo grande"}, 413, {"Connection": "close"})
        corpo = bytearray()
        request.state.studio_letto = True

        async def leggi():
            async for pezzo in request.stream():
                corpo.extend(pezzo)
                if len(corpo) > dichiarati:
                    return False
            return True
        try:
            if not await asyncio.wait_for(leggi(), STUDIO_LEGGI_S):
                return troppo
        except asyncio.TimeoutError:
            return _json({"errore": "invio troppo lento: riprova"}, 408, {"Connection": "close"})
        dati = bytes(corpo)
        del corpo
        from ..immagini import tipo_dai_byte
        from ..studio import pagine as PG
        lato = int(getattr(hub.cfg, "studio_pagina_lato", 1600) or 1600)
        soglia = float(getattr(hub.cfg, "studio_nitidezza_min", 150.0) or 0.0)
        try:
            if PG.e_pdf(dati):
                if len(dati) > int(mb_pdf * 1_000_000):
                    return _json({"errore": f"PDF troppo grande (al massimo {mb_pdf:g} MB)"}, 413)
                max_pag = min(int(getattr(hub.cfg, "studio_pdf_max_pagine", 40) or 40),
                              massimo - v["n_pagine"])
                # In un sottoprocesso con un tetto di tempo per pagina (revisione della PR
                # #312); si tiene la copia rifatta senza i metadati, non il file arrivato
                # Al più STUDIO_PDF_INSIEME divisioni insieme (seconda revisione della PR #312:
                # dieci PDF insieme erano 20 processi e più di un GB); oltre, 429
                if pdf_in_corso[0] >= STUDIO_PDF_INSIEME:
                    return _json({"errore": "Sto già dividendo un PDF: riprova fra poco.",
                                  "riprova_s": 5}, 429, {"Retry-After": "5"})
                pdf_in_corso[0] += 1
                try:
                    from ..studio.dati import cartella_di, cartella_provvisori
                    pronte, originale = await PG.dividi_pdf_a_parte(
                        dati, lato, max_pag, soglia,
                        provvisori=cartella_provvisori(cartella_di(hub.cfg)))
                finally:
                    pdf_in_corso[0] -= 1
                origine = "file"
            elif tipo_dai_byte(dati) in ("jpeg", "png", "webp"):
                if len(dati) > int(mb_foto * 1_000_000):
                    return _json({"errore": f"foto troppo grande (al massimo {mb_foto:g} MB)"},
                                 413)
                pronte = [await asyncio.to_thread(PG.prepara_foto, dati, meta["angoli"], lato,
                                                  int(mb_foto * 1_000_000), soglia)]
                origine, originale = "foto", None
            else:
                heic = dati[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc")
                return _json({"errore": "formato HEIC: mandala come JPEG" if heic else
                              "Mandami una foto JPEG o PNG, oppure un PDF."}, 415)
        except PG.PaginaNonValida as e:
            return _json({"errore": str(e)}, 415)
        del dati
        try:
            out = await asyncio.to_thread(
                st.aggiungi_pronte, prof, v["id"], pronte, origine,
                meta["nome"] if origine == "file" else None, meta["materiale"], originale)
        except (NonTrovata, NonPermesso):
            return _json({"errore": "Questa verifica non c'è."}, 404)
        except VerificaChiusa:
            return _json({"errore": "Questa verifica è chiusa: non prende pagine nuove."}, 409)
        except TroppePagine as e:
            return _json({"errore": f"Questa verifica arriverebbe oltre {e.massimo} pagine."},
                         413)
        except PermissionError:
            return _json({"errore": "Non riesco a salvare la pagina."}, 503)
        except OSError as e:
            hub.log(f"[STUDIO] pagina non salvata: {type(e).__name__}")
            return _json({"errore": "Non riesco a salvare la pagina."}, 503)
        return _json({"ok": True, **out})

    app = Starlette(routes=[
        Route("/", file("index.html", "text/html; charset=utf-8")),
        Route("/schermo.css", file("schermo.css", "text/css; charset=utf-8")),
        Route("/schermo.js", file("schermo.js", "text/javascript; charset=utf-8")),
        # Le sezioni degli schermi personali (27/10), del telefono e del PC
        Route("/sezioni.js", file("sezioni.js", "text/javascript; charset=utf-8")),
        Route("/pc.js", file("pc.js", "text/javascript; charset=utf-8")),
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
        Route("/api/motore", motore, methods=["POST"]),
        Route("/api/scarica", scarica_gettone, methods=["POST"]),
        Route("/scarica/{gettone}", scarica_file),
        Route("/api/cassetto", cassetto, methods=["POST"]),
        Route("/api/conoscenti", conoscenti_api, methods=["POST"]),
        Route("/api/schede", schede_api, methods=["POST"]),
        Route("/gioco/{gettone}", gioco_documento),
        Route("/api/gioco", gioco_api, methods=["POST"]),
        Route("/api/aspetto", aspetto_api, methods=["POST"]),
        Route("/api/parla", parla_api, methods=["POST"]),
        Route("/api/raccolte", raccolte_api, methods=["POST"]),
        Route("/api/raccolte/cerca", cerca_api, methods=["POST"]),
        Route("/api/conversazione", conversazione_api, methods=["POST"]),
        Route("/api/tocco", tocco_api, methods=["POST"]),
        Route("/api/studio/verifiche", studio_verifiche, methods=["POST"]),
        Route("/api/studio/home", studio_home, methods=["POST"]),
        Route("/api/vista", vista_api, methods=["POST"]),
        Route("/api/studio/argomenti", studio_argomenti, methods=["POST"]),
        Route("/api/studio/carte", studio_carte, methods=["POST"]),
        Route("/api/studio/prova", studio_prova, methods=["POST"]),
        Route("/api/studio/mappa", studio_mappa, methods=["POST"]),
        Route("/api/studio/ascolta", studio_ascolta, methods=["POST"]),
        Route("/api/studio/tutore", studio_tutore, methods=["POST"]),
        Route("/api/studio/pagina", studio_pagina, methods=["POST"]),
        # Il rilevatore dei bordi e la pagina dello Studio (29/10, #281), del telefono e del PC
        Route("/bordi.js", file("bordi.js", "text/javascript; charset=utf-8")),
        Route("/studio.js", file("studio.js", "text/javascript; charset=utf-8")),
        *telefono.rotte(hub),
        # /satellite: il comando per far diventare satellite un PC nuovo (03/10)
        *satellite_web.rotte(hub),
    ])
    app.state.sessioni = sessioni
    return _LeggiIlResto(_SoloHostNoti(app, _nomi_ammessi(getattr(hub.cfg, "schermi_nomi", ()))))


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
