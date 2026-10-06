"""
Un PC nuovo diventa satellite con un comando (03/10/2026): la pagina con il comando, lo
script d'installazione, il manifesto e il pacchetto.

Dove:
  - sulla **porta dei satelliti** (8771, lo stesso certificato che i satelliti fissano con
    l'impronta), richieste HTTP normali accanto al WebSocket (`process_request` di
    websockets): GET /installa (la pagina), /installa/installa.ps1, /installa/manifesto.json,
    /installa/pacchetto.zip. Servono anche agli aggiornamenti dei satelliti installati;
  - sul **server degli schermi**, GET /satellite: la stessa pagina (l'indirizzo che si
    ricorda), con il comando che punta alla porta dei satelliti.

La fiducia: il PC nuovo non conosce ancora il certificato del server (autofirmato, o firmato
dalla CA di casa che il PC non ha). Il comando da incollare in PowerShell contiene la
**chiave** del certificato dei satelliti (`sha256//…`, lo SHA-256 della chiave pubblica, il
«pin» di curl), da confrontare a occhio con quella stampata sul server da
`calliope satellite --elenco`. Ogni download passa da `curl.exe -k --pinnedpubkey <chiave>`
(curl di Windows 10 1803+ e 11, Schannel): niente CA, ma se la chiave non è quella curl
chiude prima di mandare o ricevere un byte (codice 90). Il manifesto arriva su quel canale e
porta lo SHA-256 del pacchetto e l'impronta del certificato per il satellite; uv si scarica
da GitHub con la verifica TLS normale e il suo SHA-256 fissato nel codice. Niente `iex` di un
testo scaricato: lo script si scrive in un file e si esegue con -File.
"""

import base64
import hashlib
import html
import ipaddress
import json
import ssl
from pathlib import Path

QUI = Path(__file__).resolve().parent
SCRIPT_PS1 = QUI / "installazione" / "installa.ps1"
PORTA_PREDEFINITA = 8771


def chiave(cfg) -> str:
    """«sha256//<base64>»: il pin della chiave pubblica del certificato dei satelliti (quello
    di curl --pinnedpubkey), oppure "" se il certificato non c'è."""
    from ..schermi.tls import spki_der
    from .server import percorso
    cert = percorso(cfg, cfg.satellite_tls_cert)
    try:
        der = ssl.PEM_cert_to_DER_cert(cert.read_text(encoding="ascii"))
        return "sha256//" + base64.b64encode(hashlib.sha256(spki_der(der)).digest()).decode()
    except (OSError, ValueError, IndexError):
        return ""


def _host_url(host: str) -> str:
    try:
        if isinstance(ipaddress.ip_address(host), ipaddress.IPv6Address):
            return f"[{host}]"
    except ValueError:
        pass
    return host


def host_da_intestazione(valore: str) -> str:
    """L'host di un'intestazione Host («192.168.1.5:8770», «[::1]:8770») senza la porta."""
    h = (valore or "").strip()
    if h.startswith("["):
        return h[1:h.find("]")] if "]" in h else ""
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


def base_url(host: str, porta: int) -> str:
    return f"https://{_host_url(host)}:{int(porta)}"


def comando_powershell(host: str, porta: int, pin: str) -> str:
    """Il comando da incollare in PowerShell (Windows PowerShell 5.1 di un PC appena
    installato va bene): scarica lo script con la chiave fissata e lo esegue da file."""
    u = base_url(host, porta)
    return (f"$k='{pin}'; $u='{u}'; $f=\"$env:TEMP\\calliope-satellite.ps1\"; "
            f"curl.exe -fsSk --pinnedpubkey $k -o $f \"$u/installa/installa.ps1\"; "
            f"if ($LASTEXITCODE -eq 0) {{ powershell -NoProfile -ExecutionPolicy Bypass "
            f"-File $f -Server $u -Chiave $k }} else {{ Write-Host \"Download non riuscito "
            f"(codice $LASTEXITCODE; 90 = chiave diversa: NON proseguire)\" }}")


def comando_bash(host: str, porta: int, pin: str) -> str:
    """Il posto per Linux: stessa forma; il satellite Linux completo è un altro lavoro."""
    u = base_url(host, porta)
    return (f"k='{pin}'; curl -fsSk --pinnedpubkey \"$k\" -o /tmp/calliope-satellite.sh "
            f"'{u}/installa/installa.sh' && sh /tmp/calliope-satellite.sh '{u}' \"$k\"")


def problema(cfg) -> str:
    """Perché un PC nuovo non può ancora installarsi da qui ("" = si può)."""
    if not getattr(cfg, "satellite_installazione", True):
        return "l'installazione dei satelliti è spenta (satellite_installazione: false)."
    if str(getattr(cfg, "audio_modo", "locale")) != "satellite":
        return ("Calliope qui non usa i satelliti (audio_modo: satellite in "
                "calliope.locale.yaml).")
    from .server import solo_locale
    if solo_locale(str(cfg.satellite_indirizzo or "127.0.0.1")):
        return ("il server dei satelliti ascolta solo su questo computer: "
                "satellite_indirizzo: 0.0.0.0 in calliope.locale.yaml, poi riavvia Calliope.")
    if not chiave(cfg):
        return ("manca il certificato dei satelliti: calliope satellite --certificato, poi "
                "riavvia Calliope.")
    return ""


_STILE = """
body{font-family:system-ui,Segoe UI,sans-serif;max-width:52rem;margin:0 auto;padding:16px;
background:#f7f5f0;color:#1d1b16;line-height:1.5}
h1{font-size:1.5rem}h2{font-size:1.1rem;margin-top:1.6rem}
pre{background:#fff;border:1px solid #d6d0c4;border-radius:6px;padding:12px;white-space:pre-wrap;
word-break:break-all;font-size:.9rem}
code{font-size:.95rem}.chiave{font-weight:600}.nota{color:#5b564b;font-size:.92rem}
.problema{background:#fde8e4;border:1px solid #e5a99d;border-radius:6px;padding:12px}
@media (prefers-color-scheme:dark){body{background:#1b1a17;color:#ece8de}
pre{background:#262420;border-color:#46423a}.nota{color:#b5afa2}
.problema{background:#4a2620;border-color:#7d4034}}
"""


def pagina(host: str, porta: int, pin: str, motivo: str = "") -> str:
    """La pagina /satellite: il comando per un PC Windows nuovo, la chiave da controllare e
    cosa succede dopo. Niente script (CSP degli schermi), niente risorse esterne."""
    e = html.escape
    if motivo or not pin:
        corpo = (f'<p class="problema">Per ora un PC nuovo non può diventare satellite: '
                 f'{e(motivo or "manca il certificato dei satelliti.")}</p>')
    else:
        corpo = f"""
<h2>1. Controlla la chiave</h2>
<p>Sul server lancia <code>calliope satellite --elenco</code> (sul portatile di sviluppo
<code>python -m calliope.satellite --elenco</code>): la riga «Chiave per i PC nuovi» deve essere
<b>identica</b> a questa. Se è diversa, fermati: qualcuno si mette in mezzo.</p>
<pre class="chiave">{e(pin)}</pre>
<h2>2. Incolla in PowerShell (Windows)</h2>
<p>Sul PC nuovo, una finestra di PowerShell normale (non da amministratore). Il comando
contiene la stessa chiave: curl scarica solo se il server la ha.</p>
<pre>{e(comando_powershell(host, porta, pin))}</pre>
<p class="nota">Cosa fa: scarica uv (il gestore di Python di Astral, versione e SHA-256 fissati) e
con lui Python; scarica da qui il codice del satellite e le sue librerie con le versioni
bloccate; prepara la configurazione con l'indirizzo di questo server e l'impronta del suo
certificato; chiede se avviare il satellite all'accesso; lo avvia. Tutto in
<code>%LOCALAPPDATA%\\Calliope\\satellite</code>, senza diritti di amministratore. Il satellite
mostra un codice di 6 cifre: sul server <code>calliope satellite --abbina &lt;codice&gt;
--stanza &lt;stanza&gt; --pc</code> (con <code>--pc</code> il satellite comanda anche questo PC: volume, file, documenti; senza è solo voce). Da lì si aggiorna da solo quando si aggiorna il server.</p>
<h2>Linux</h2>
<p class="nota">Il satellite Linux con un comando non c'è ancora. La forma sarà questa:</p>
<pre>{e(comando_bash(host, porta, pin))}</pre>"""
    return f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nuovo satellite</title><link rel="stylesheet" href="/satellite.css"></head>
<body><h1>Un PC nuovo come satellite di Calliope</h1>{corpo}</body></html>
"""


def script_ps1() -> bytes:
    """installa.ps1 con il BOM UTF-8: Windows PowerShell 5.1 legge un .ps1 senza BOM come
    ANSI e rovinerebbe le lettere accentate."""
    return b"\xef\xbb\xbf" + SCRIPT_PS1.read_bytes().lstrip(b"\xef\xbb\xbf")


SCRIPT_SH = (b"#!/bin/sh\n# Satellite Linux con un comando: non ancora disponibile "
             b"(calliope/satellite/web.py).\n"
             b"echo 'Il satellite Linux con un comando non c e ancora: vedi prove/LEGGIMI.md "
             b"di Calliope (satellite dal repository).'\nexit 1\n")


# ───────────────────────── porta dei satelliti (websockets) ─────────────────────────
def risposta(server, request):
    """`process_request` di websockets: None per le richieste WebSocket (le gestisce il
    server dei satelliti); per le altre una pagina, lo script o il pacchetto."""
    from websockets.datastructures import Headers
    from websockets.http11 import Response
    if "upgrade" in {k.lower() for k in request.headers.keys()}:
        return None
    path = request.path.split("?", 1)[0]
    cfg = server.cfg

    def r(stato: int, corpo: bytes, tipo: str, extra=()):
        frase = {200: "OK", 404: "Not Found", 503: "Service Unavailable"}.get(stato, "Error")
        h = Headers([("Content-Type", tipo), ("Content-Length", str(len(corpo))),
                     ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                     ("Connection", "close"), *extra])
        return Response(stato, frase, h, corpo)

    if not getattr(cfg, "satellite_installazione", True) or server.ssl is None:
        return r(404, b"installazione dei satelliti spenta\n", "text/plain; charset=utf-8")
    host = host_da_intestazione(request.headers.get("Host", "")) or "127.0.0.1"
    porta = int(server.port)
    if path in ("/installa", "/installa/"):
        return r(200, pagina(host, porta, chiave(cfg)).encode("utf-8"),
                 "text/html; charset=utf-8",
                 [("Content-Security-Policy", "default-src 'none'; style-src 'self'")])
    if path == "/satellite.css":
        return r(200, _STILE.encode("utf-8"), "text/css; charset=utf-8")
    if path == "/installa/installa.ps1":
        return r(200, script_ps1(), "text/plain; charset=utf-8")
    if path == "/installa/installa.sh":
        return r(200, SCRIPT_SH, "text/plain; charset=utf-8")
    dist = getattr(server, "distributore", None)
    if path == "/installa/manifesto.json":
        m = dist.manifesto(f"wss://{_host_url(host)}:{porta}", server.impronta) if dist else None
        if m is None:
            motivo = (dist.motivo if dist else "") or "pacchetto non disponibile"
            return r(503, json.dumps({"errore": motivo}, ensure_ascii=False).encode("utf-8"),
                     "application/json; charset=utf-8")
        return r(200, json.dumps(m, ensure_ascii=False, indent=2).encode("utf-8"),
                 "application/json; charset=utf-8")
    if path == "/installa/pacchetto.zip":
        p = dist.pacchetto() if dist else None
        if p is None:
            return r(503, b"pacchetto non disponibile\n", "text/plain; charset=utf-8")
        return r(200, p.dati, "application/zip",
                 [("Content-Disposition", 'attachment; filename="calliope-satellite.zip"')])
    return r(404, b"non trovato\n", "text/plain; charset=utf-8")


# ───────────────────────── server degli schermi (Starlette) ─────────────────────────
def rotte(hub) -> list:
    """GET /satellite (e il suo foglio di stile) sul server degli schermi."""
    from starlette.responses import HTMLResponse, Response
    from starlette.routing import Route

    async def pagina_satellite(request):
        cfg = hub.cfg
        host = host_da_intestazione(request.headers.get("host", "")) or "127.0.0.1"
        motivo = problema(cfg)
        return HTMLResponse(pagina(host, int(cfg.satellite_porta), "" if motivo else
                                   chiave(cfg), motivo),
                            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                                     "X-Content-Type-Options": "nosniff",
                                     "Content-Security-Policy":
                                         "default-src 'none'; style-src 'self'"})

    async def stile(request):
        return Response(_STILE, media_type="text/css; charset=utf-8",
                        headers={"Cache-Control": "no-cache"})

    return [Route("/satellite", pagina_satellite), Route("/satellite.css", stile)]
