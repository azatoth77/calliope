"""
La scheda interattiva di un'estensione (05/10/2026, decisioni di Dario del 04–05/10): un gioco
(o un'altra scheda che si usa toccando) che gira **nel browser** degli schermi, in un riquadro
isolato. Rapporto: docs/ricerche/2026-10-05-giochi.md.

Il riquadro è un `<iframe sandbox="allow-scripts">` (senza `allow-same-origin`): la pagina che
carica, `/gioco/<gettone>` (calliope/schermi/giochi.py), ha un'origine opaca, la CSP la chiude
(`sandbox allow-scripts`, `default-src 'none'`, `connect-src 'none'`, solo i suoi script con
l'impronta SHA-256, immagini e suoni solo `data:`), e il documento lo compone Calliope da qui:
uno scheletro fisso, il **runtime** del riquadro (`RUNTIME_JS`: l'oggetto `calliope`, che toglie
fetch, WebSocket, WebRTC e simili prima del codice del gioco), lo stile e gli script del gioco,
le risorse come `data:`. Il codice del gioco non vede la pagina, la sessione, le altre schede né
i dati di Calliope: parla solo con `postMessage` verso la pagina, che controlla ogni messaggio
e lo passa al server (`POST /api/gioco`), che lo ricontrolla.

Il manifesto ha una sezione `scheda`:

    "scheda": {"tipo": "gioco",
               "file": ["logica.js", "gioco.js"],   in quest'ordine nel documento
               "stile": "gioco.css",                 facoltativo
               "risorse": ["carte/asso.svg"],         facoltative: disegni SVG
               "giocatori": {"min": 1, "max": 2},
               "condivisa": false,   partita tra schermi diversi (i messaggi passano da Calliope)
               "chat": false,        testo libero tra giocatori (solo con condivisa)
               "salva": true,        record e partite nello spazio dati dell'estensione
               "voce": false,        far dire una frase a Calliope (poche al minuto)
               "azioni": []}         metodi della porta stretta (con gli scope di «permessi»)

**Gioco puro** (`e_gioco_puro`): nessun permesso in «permessi» e nessuna azione della porta:
solo il riquadro, i suoi dati, la voce e la partita condivisa. Lo può approvare un familiare
adulto con la voce riconosciuta (servizio._approva), si usa anche dagli ospiti e sugli schermi
di stanza. Tutto il resto resta a chi amministra con la frase di sfida.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re

TIPI = ("gioco",)
_FILE_JS = re.compile(r"^[a-z][a-z0-9_]{0,30}\.js$")
_FILE_CSS = re.compile(r"^[a-z][a-z0-9_]{0,30}\.css$")
_RISORSA = re.compile(r"^[a-z0-9_\-]{1,30}(/[a-z0-9_\-]{1,30})?\.[a-z0-9]{2,4}$")
# Le risorse sono disegni SVG: l'agente scrive solo file di testo (i suoni il gioco li fa con
# Web Audio, le immagini con SVG o canvas). Nel riquadro diventano `data:`, mai script
TIPI_RISORSA = {".svg": "image/svg+xml"}
MAX_FILE_JS = 4
MAX_JS_BYTE = 300_000            # tutti gli script insieme
MAX_CSS_BYTE = 60_000
MAX_RISORSE = 24
MAX_RISORSA_BYTE = 300_000
MAX_RISORSE_BYTE = 2_000_000
MAX_GIOCATORI = 8

# I metodi della porta stretta che un riquadro può chiedere (con gli scope del manifesto),
# come per il codice Python dell'estensione (porta.py). Mai la rete in POST dal riquadro
AZIONI = ("casa_stato", "casa_comando", "lista_leggi", "lista_aggiungi", "lista_togli",
          "agenda_elenca", "timer_imposta", "rete_leggi")


class SchedaNonValida(ValueError):
    pass


def _bool(v) -> bool:
    return v is True or (isinstance(v, str) and v.strip().lower() in ("true", "sì", "si", "1"))


def normalizza(s, permessi: dict | None = None) -> dict | None:
    """La sezione «scheda» validata (o None se manca). `permessi`: quelli normalizzati del
    manifesto, per controllare che le azioni chieste siano sbloccate dagli scope."""
    if s in (None, False, {}):
        return None
    if not isinstance(s, dict):
        raise SchedaNonValida("«scheda» deve essere un oggetto")
    noti = {"tipo", "file", "stile", "risorse", "giocatori", "condivisa", "chat", "salva",
            "voce", "azioni"}
    altri = [k for k in s if k not in noti]
    if altri:
        raise SchedaNonValida(f"«scheda»: sconosciuto {', '.join(map(str, altri))} (solo "
                              f"{', '.join(sorted(noti))})")
    tipo = str(s.get("tipo") or "gioco").strip().lower()
    if tipo not in TIPI:
        raise SchedaNonValida(f"«scheda.tipo»: uno tra {', '.join(TIPI)}")
    file = s.get("file") or []
    if isinstance(file, str):
        file = [file]
    if not isinstance(file, list) or not file or len(file) > MAX_FILE_JS:
        raise SchedaNonValida(f"«scheda.file»: da 1 a {MAX_FILE_JS} file .js (per esempio "
                              "[\"logica.js\", \"gioco.js\"])")
    for f in file:
        if not isinstance(f, str) or not _FILE_JS.match(f) or f.endswith(".test.js"):
            raise SchedaNonValida(f"«scheda.file»: nome non valido «{f}» (minuscole, cifre e _, "
                                  "estensione .js; i test non vanno nel riquadro)")
    stile = s.get("stile") or ""
    if stile and (not isinstance(stile, str) or not _FILE_CSS.match(stile)):
        raise SchedaNonValida("«scheda.stile»: un file .css (minuscole, cifre e _)")
    risorse = s.get("risorse") or []
    if not isinstance(risorse, list) or len(risorse) > MAX_RISORSE:
        raise SchedaNonValida(f"«scheda.risorse»: al più {MAX_RISORSE} file")
    for r in risorse:
        if not isinstance(r, str) or not _RISORSA.match(r) or \
                "." + r.rsplit(".", 1)[-1] not in TIPI_RISORSA:
            raise SchedaNonValida(f"«scheda.risorse»: «{r}» non va (solo "
                                  f"{', '.join(sorted(TIPI_RISORSA))}, minuscole)")
    g = s.get("giocatori") or {}
    if isinstance(g, int):
        g = {"min": 1, "max": g}
    try:
        gmin, gmax = int(g.get("min", 1)), int(g.get("max", 1))
    except (TypeError, ValueError, AttributeError):
        raise SchedaNonValida("«scheda.giocatori»: {\"min\": 1, \"max\": 2}") from None
    if not (1 <= gmin <= gmax <= MAX_GIOCATORI):
        raise SchedaNonValida(f"«scheda.giocatori»: 1 ≤ min ≤ max ≤ {MAX_GIOCATORI}")
    condivisa = _bool(s.get("condivisa"))
    chat = _bool(s.get("chat"))
    if chat and not condivisa:
        raise SchedaNonValida("«scheda.chat» solo con «condivisa»: la chat è tra giocatori di "
                              "schermi diversi")
    azioni = s.get("azioni") or []
    if not isinstance(azioni, list) or any(a not in AZIONI for a in azioni):
        raise SchedaNonValida(f"«scheda.azioni»: solo {', '.join(AZIONI)}")
    azioni = sorted(set(azioni))
    if azioni and permessi is not None:
        manca = [a for a in azioni if not sbloccata(a, permessi)]
        if manca:
            raise SchedaNonValida(f"«scheda.azioni»: {', '.join(manca)} senza lo scope in "
                                  "«permessi» (vedi il contratto delle capacità)")
    return {"tipo": tipo, "file": list(file), "stile": stile, "risorse": sorted(set(risorse)),
            "giocatori": {"min": gmin, "max": gmax}, "condivisa": condivisa, "chat": chat,
            "salva": _bool(s.get("salva")) if "salva" in s else True,
            "voce": _bool(s.get("voce")), "azioni": azioni}


def sbloccata(azione: str, permessi: dict) -> bool:
    """L'azione della porta ha lo scope che serve nei permessi (normalizzati)?"""
    le, sc, r = permessi.get("legge") or {}, permessi.get("scrive") or {}, permessi.get("rete") or {}
    return {"casa_stato": bool(le.get("casa")), "casa_comando": bool(sc.get("casa")),
            "lista_leggi": bool(le.get("liste")), "lista_aggiungi": bool(sc.get("liste")),
            "lista_togli": bool(sc.get("liste")), "agenda_elenca": bool(le.get("agenda")),
            "timer_imposta": bool(sc.get("agenda")),
            "rete_leggi": bool(r.get("pubblica") or r.get("host"))}.get(azione, False)


def nessun_permesso(permessi: dict) -> bool:
    p = permessi or {}
    le, sc, r = p.get("legge") or {}, p.get("scrive") or {}, p.get("rete") or {}
    return (not any(le.values()) and not any(sc.values()) and not r.get("pubblica")
            and not r.get("host") and not r.get("post") and not p.get("invia"))


def e_gioco_puro(m: dict) -> bool:
    """Solo il riquadro: niente dati di casa, niente rete, niente tool (decisione 2)."""
    s = (m or {}).get("scheda")
    if not s:
        return False
    return not s.get("azioni") and nessun_permesso((m or {}).get("permessi") or {})


def in_parole(m: dict) -> list[str]:
    """Le capacità della scheda dette a chi approva."""
    s = (m or {}).get("scheda")
    if not s:
        return []
    g = s["giocatori"]
    chi = (f"da {g['min']} a {g['max']} giocatori" if g["min"] != g["max"]
           else ("un giocatore" if g["max"] == 1 else f"{g['max']} giocatori"))
    out = [f"è un gioco sullo schermo per {chi}"]
    if s["condivisa"]:
        out.append("si gioca anche tra schermi di stanze diverse")
    if s["chat"]:
        out.append("i giocatori si scrivono (con un bambino o un ospite passa dal guardiano)")
    if s["salva"]:
        out.append("tiene record e partite")
    if s["voce"]:
        out.append("mi fa dire qualche frase")
    if s["azioni"]:
        out.append("dal gioco chiede: " + ", ".join(a.replace("_", " ") for a in s["azioni"]))
    return out


# ─────────────────────────── analisi del codice JavaScript ───────────────────────────
# Come analisi.py per il Python: non è un confine (il confine è il riquadro: origine opaca,
# CSP, runtime), ma dice a chi approva le parti a rischio, e un gioco puro con un riscontro
# non si approva da un familiare (solo chi amministra, con la sfida)
_RISCHI_JS = (
    (r"\bfetch\s*\(|XMLHttpRequest|\bWebSocket\b|\bEventSource\b|sendBeacon|WebTransport",
     "rete", "chiede la rete (il riquadro non ce l'ha)"),
    (r"RTCPeerConnection|RTCDataChannel|webkitRTC", "webrtc", "WebRTC: un canale verso fuori"),
    (r"\b(Shared)?Worker\s*\(|importScripts|serviceWorker", "worker", "processi in parallelo"),
    (r"\beval\s*\(|\bnew\s+Function\b|\bFunction\s*\(|setTimeout\s*\(\s*['\"`]|"
     r"setInterval\s*\(\s*['\"`]|\bimport\s*\(", "codice_dinamico", "codice costruito a runtime"),
    (r"document\.cookie|localStorage|sessionStorage|indexedDB|\bcaches\b", "archivio_browser",
     "archivi del browser (il riquadro non ne ha)"),
    (r"\b(window\.)?(top|parent|opener)\s*\.|\bframes\s*\[|window\.open\s*\(", "fuori_riquadro",
     "prova a toccare la pagina fuori dal riquadro"),
    (r"\blocation\s*(\.\s*(href|assign|replace)\b|=)|\bhistory\s*\.\s*(push|replace)State",
     "navigazione", "cambia pagina (il riquadro si chiuderebbe)"),
    (r"postMessage\s*\(", "messaggi_diretti", "messaggi diretti alla pagina invece di calliope.*"),
    (r"createElement\s*\(\s*['\"`](iframe|script|link|object|embed|form|a|meta|base)['\"`]",
     "elementi_attivi", "crea elementi che caricano o navigano"),
    (r"\b(srcdoc|outerHTML)\b|insertAdjacentHTML|document\.write", "html_dinamico",
     "scrive HTML grezzo"),
    (r"\\x[0-9a-fA-F]{2}(\\x[0-9a-fA-F]{2}){15,}|[A-Za-z0-9+/]{200,}={0,2}|"
     r"String\.fromCharCode\s*\((\s*\d+\s*,){15,}", "offuscato", "testo codificato lungo"),
    (r"\bon[a-z]+\s*=\s*['\"]", "gestori_in_linea", "gestori in linea (onclick=…: la CSP li "
                                                   "blocca)"),
)


def analizza_js(sorgenti: dict[str, str]) -> dict:
    """{"sintassi": [], "rischi": [{file, riga, cosa, perche}]} per i file .js della scheda.
    La sintassi la controlla Node nel container (sandbox.test): qui solo i riscontri."""
    rischi = []
    for nome, testo in sorted(sorgenti.items()):
        if not nome.endswith(".js") or nome.endswith(".test.js"):
            continue
        for i, riga in enumerate(str(testo).splitlines(), 1):
            pulita = riga.strip()
            if pulita.startswith("//"):
                continue
            for rx, cosa, perche in _RISCHI_JS:
                if re.search(rx, riga):
                    rischi.append({"file": nome, "riga": i, "cosa": cosa, "perche": perche})
            if len(rischi) >= 40:
                break
    return {"sintassi": [], "rischi": rischi}


# ─────────────────────────── il documento del riquadro ───────────────────────────

# Il runtime del riquadro: gira prima del codice del gioco, nello stesso documento. Toglie le
# vie verso fuori che la CSP non copre tutte (WebRTC, worker), cattura la pagina madre e dà
# al gioco l'oggetto `calliope`. Risponde ai controlli («ping») della pagina: un gioco bloccato
# in un ciclo infinito non risponde, e la pagina lo chiude (cane da guardia)
RUNTIME_JS = r"""(function () {
  "use strict";
  var P = window.parent;
  var invia = function (m) { try { P.postMessage(m, "*"); } catch (e) { /* niente */ } };
  var RISORSE = __RISORSE__;
  var VIA = ["fetch", "XMLHttpRequest", "WebSocket", "EventSource", "WebTransport",
    "RTCPeerConnection", "webkitRTCPeerConnection", "RTCDataChannel", "RTCSessionDescription",
    "RTCIceCandidate", "Worker", "SharedWorker", "BroadcastChannel", "open", "Notification",
    "MessageChannel", "Request", "PresentationRequest"];
  VIA.forEach(function (k) {
    try { Object.defineProperty(window, k, { value: undefined, writable: false, configurable: false }); }
    catch (e) { try { window[k] = undefined; } catch (e2) { /* niente */ } }
  });
  ["sendBeacon", "serviceWorker", "share", "credentials", "geolocation", "mediaDevices",
   "clipboard", "bluetooth", "usb", "serial", "hid", "locks"].forEach(function (k) {
    try { Object.defineProperty(Navigator.prototype, k, { get: function () { return undefined; }, configurable: false }); }
    catch (e) { /* niente */ }
  });
  var n = 0, attese = {}, avvio = null, errori = 0;
  var ascolti = { avvio: [], messaggio: [], chat: [], giocatori: [], pausa: [], fine_tempo: [] };
  function manda(tipo, dati) {
    var m = { calliope: 1, tipo: tipo, id: ++n };
    for (var k in (dati || {})) m[k] = dati[k];
    invia(m);
    return m.id;
  }
  function chiedi(tipo, dati) {
    return new Promise(function (ok, ko) {
      var id = manda(tipo, dati);
      attese[id] = { ok: ok, ko: ko };
      setTimeout(function () { if (attese[id]) { delete attese[id]; ko(new Error("nessuna risposta")); } }, 130000);
    });
  }
  window.addEventListener("message", function (ev) {
    if (ev.source !== P) return;
    var m = ev.data;
    if (!m || m.calliope !== 1 || typeof m.tipo !== "string") return;
    if (m.tipo === "ping") { invia({ calliope: 1, tipo: "pong", n: m.n }); return; }
    if (m.tipo === "risposta") {
      var a = attese[m.rif];
      if (a) { delete attese[m.rif]; if (m.ok) a.ok(m.valore); else a.ko(new Error(m.errore || "rifiutato")); }
      return;
    }
    if (m.tipo === "avvio") avvio = m.dati || {};
    (ascolti[m.tipo] || []).forEach(function (f) { try { f(m.dati); } catch (e) { console.error(e); } });
  });
  window.addEventListener("error", function (ev) {
    if (errori++ < 3) invia({ calliope: 1, tipo: "errore", id: ++n, testo: String(ev.message || "errore").slice(0, 200) });
  });
  function quando(tipo) { return function (f) { if (typeof f === "function") ascolti[tipo].push(f); }; }
  var api = {
    quandoPronto: function (f) { if (typeof f !== "function") return; ascolti.avvio.push(f); if (avvio) f(avvio); },
    quandoMessaggio: quando("messaggio"),
    quandoChat: quando("chat"),
    quandoGiocatori: quando("giocatori"),
    quandoPausa: quando("pausa"),
    quandoFineTempo: quando("fine_tempo"),
    salva: function (chiave, valore) { return chiedi("salva", { chiave: String(chiave), valore: valore }); },
    leggi: function (chiave) { return chiedi("leggi", { chiave: String(chiave) }); },
    manda: function (dati) { manda("manda", { dati: dati }); },
    chat: function (testo) { return chiedi("chat", { testo: String(testo) }); },
    di: function (testo) { return chiedi("di", { testo: String(testo) }); },
    azione: function (nome, argomenti) { return chiedi("azione", { nome: String(nome), argomenti: argomenti || {} }); },
    fine: function (esito) { manda("fine", { esito: esito === undefined ? null : esito }); },
    risorsa: function (nome) { return RISORSE[nome] || null; }
  };
  Object.freeze(api);
  Object.defineProperty(window, "calliope", { value: api, writable: false, configurable: false });
  manda("pronto", {});
})();
"""

# Sfondo chiaro: i giochi scritti dall'agente danno quasi sempre per scontato il bianco (il primo
# memory della DGX aveva il titolo grigio scuro). Si scorre se il gioco non ci sta
_STILE_BASE = ("html,body{margin:0;padding:0;height:100%;background:#fafafa;color:#222;"
               "font-family:system-ui,sans-serif;overflow:auto}"
               "#gioco{width:100%;min-height:100%;box-sizing:border-box;padding:2vmin}")


def _hash(testo: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(testo.encode("utf-8")).digest()).decode() + "'"


def _js_sicuro(js: str) -> str:
    """Il codice dentro <script>: «</script» non chiude il tag (in JS «<\\/script» è uguale)."""
    return re.sub(r"</(script)", r"<\\/\1", js, flags=re.I)


def documento(scheda: dict, file: dict[str, bytes]) -> tuple[str, str]:
    """(HTML del riquadro, CSP) dai file della versione approvata. `file`: {percorso: byte}."""
    risorse = {}
    for r in scheda.get("risorse") or []:
        dati = file.get(r)
        if dati is None:
            continue
        tipo = TIPI_RISORSA["." + r.rsplit(".", 1)[-1]]
        risorse[r] = f"data:{tipo};base64," + base64.b64encode(dati).decode("ascii")
    runtime = RUNTIME_JS.replace("__RISORSE__", json.dumps(risorse).replace("</", "<\\/"))
    script = [runtime] + [_js_sicuro(file.get(f, b"").decode("utf-8", "replace"))
                          for f in scheda["file"]]
    css = _STILE_BASE + "\n" + (file.get(scheda["stile"], b"").decode("utf-8", "replace")
                                if scheda.get("stile") else "")
    css = css.replace("</", "<\\/")
    html = ("<!doctype html><html lang=\"it\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<meta http-equiv=\"x-dns-prefetch-control\" content=\"off\">"
            "<meta name=\"referrer\" content=\"no-referrer\">"
            f"<title>Gioco</title><style>{css}</style></head><body><div id=\"gioco\"></div>"
            + "".join(f"<script>{s}</script>" for s in script) + "</body></html>")
    csp = ("sandbox allow-scripts; default-src 'none'; "
           "script-src " + " ".join(_hash(s) for s in script) + "; "
           "style-src 'unsafe-inline'; img-src data: blob:; media-src data: blob:; "
           "font-src data:; connect-src 'none'; frame-src 'none'; child-src 'none'; "
           "worker-src 'none'; object-src 'none'; manifest-src 'none'; form-action 'none'; "
           "base-uri 'none'; frame-ancestors 'self'")
    return html, csp


INTESTAZIONI = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-DNS-Prefetch-Control": "off",
    "Cache-Control": "no-store",
    "Cross-Origin-Opener-Policy": "same-origin",
    # Nessuna capacità del browser: né microfono né webcam né posizione, niente suono da solo
    "Permissions-Policy": ("camera=(), microphone=(), geolocation=(), autoplay=(), "
                           "fullscreen=(), payment=(), usb=(), serial=(), bluetooth=(), hid=(), "
                           "display-capture=(), screen-wake-lock=(), clipboard-read=(), "
                           "clipboard-write=(), publickey-credentials-get=(), "
                           "browsing-topics=(), idle-detection=()"),
}
