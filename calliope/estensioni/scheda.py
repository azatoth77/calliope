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
               "file": ["logica.js"],                 in quest'ordine nel documento (una tela
                                                      può avere il suo tela.js)
               "stile": "tema.css",                   facoltativo: le variabili del tema
               "risorse": ["carte/asso.svg"],         facoltative: disegni SVG
               "giocatori": {"min": 1, "max": 2},
               "condivisa": false,   partita tra schermi diversi (i messaggi passano da Calliope)
               "chat": false,        testo libero tra giocatori (solo con condivisa)
               "salva": true,        record e partite nello spazio dati dell'estensione
               "voce": false,        far dire una frase a Calliope (poche al minuto)
               "azioni": [],         metodi della porta stretta (con gli scope di «permessi»)
               "macchina": {…}}      la macchina a stati di Calliope (macchina.py), obbligatoria

**La macchina a stati** (13/10, calliope/estensioni/macchina.py e motore_gioco.js): un gioco
dichiara fasi e comandi in `macchina` e scrive in logica.js solo `GIOCO` (partita nuova, mosse,
comandi attivi, vista); preparazione, turni, punti, esito, fine, disegno sul palco fisso,
pulsanti e voce sono del motore, che il documento del riquadro carica prima degli script del
gioco. Dal 14/10 (passo 4 del progetto, il palco) è l'unico formato: un gioco senza `macchina`
(con `gioco.js` libero e l'`ascolta` piatto dell'11/10) non si approva né si apre più, e si
rifà con lo sviluppo (decisione 9 di chi amministra, 12/10: niente compatibilità).

**Comandi a voce** (11/10, calliope/gioco_voce.py): i comandi delle fasi, con gli slot espansi
in un elenco piatto chiuso (`ascolta` nella scheda normalizzata, scritto da Calliope); una frase
che corrisponde per intero a una forma di un comando attivo va dritta al gioco come mossa, senza
il modello. Al riquadro arriva solo il nome del comando e, con `macchina.giocatore`, il nome di
chi è riconosciuto dalla voce: mai audio né testo libero. Li riceve il motore, da un canale
riservato del runtime (il codice del gioco non li vede).

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
            "voce", "azioni", "macchina"}
    if s.get("ascolta") not in (None, False, {}, []):
        # 14/10: i comandi a voce piatti dell'11/10 non ci sono più (giochi vecchi tolti)
        raise SchedaNonValida("«scheda.ascolta» non c'è più: i comandi a voce sono quelli delle "
                              "fasi in «scheda.macchina», li ricava Calliope")
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
                              "[\"logica.js\"])")
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
    if s.get("macchina") in (None, False, {}):
        # 14/10 (passo 4, decisione 9 del 12/10): i giochi vecchi, con gioco.js libero, non si
        # approvano più
        raise SchedaNonValida(SENZA_MACCHINA)
    from . import macchina as mc
    try:
        macchina = mc.normalizza(s.get("macchina"), {"min": gmin, "max": gmax})
        ascolta = mc.ascolta(macchina, {"min": gmin, "max": gmax})
    except mc.MacchinaNonValida as e:
        raise SchedaNonValida(str(e)) from None
    if ascolta.get("giocatore") and "rete_leggi" in azioni:
        # Il nome di chi gioca resta dentro Calliope: un gioco che legge la rete potrebbe
        # metterlo in un indirizzo
        raise SchedaNonValida("«scheda.macchina.giocatore»: il nome di chi gioca solo per un "
                              "gioco senza rete_leggi")
    return {"tipo": tipo, "file": list(file), "stile": stile, "risorse": sorted(set(risorse)),
            "giocatori": {"min": gmin, "max": gmax}, "condivisa": condivisa, "chat": chat,
            "salva": _bool(s.get("salva")) if "salva" in s else True,
            "voce": _bool(s.get("voce")), "azioni": azioni, "ascolta": ascolta,
            "macchina": macchina}


# Il messaggio per un gioco senza la macchina (all'agente, a chi approva, nei log)
SENZA_MACCHINA = ("un gioco si scrive con la macchina a stati di Calliope: «scheda.macchina» con "
                  "le fasi e i comandi, e logica.js con const GIOCO = {…} (niente gioco.js né "
                  "«ascolta»: il disegno sul palco, i pulsanti e la voce sono di Calliope)")


def ha_macchina(m: dict | None) -> bool:
    """La scheda del manifesto (già normalizzato) è un gioco del formato di oggi (14/10)."""
    s = (m or {}).get("scheda") or {}
    return bool(s.get("macchina"))


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
    # 12/10 sera: «per da 2 a 4 giocatori» e «con 1 comandi» detti nella revisione
    chi = (f", da {g['min']} a {g['max']} giocatori" if g["min"] != g["max"]
           else (" per un giocatore" if g["max"] == 1 else f" per {g['max']} giocatori"))
    out = [f"è un gioco sullo schermo{chi}"]
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
    if s.get("macchina"):
        from .macchina import in_parole as macchina_in_parole
        out.append(macchina_in_parole(s["macchina"]))
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
  var ascolti = { avvio: [], messaggio: [], chat: [], giocatori: [], pausa: [], fine_tempo: [], comando: [],
                  partita: [], autorevole: [], specchio: [], nome: [] };
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
  // Il canale del motore della macchina a stati (14/10, motore_gioco.js): l'istantanea della
  // partita (fase, a chi tocca, punti, comandi a voce che valgono adesso, numerata) e lo stato
  // per la ripresa dopo «Riapri», le mosse a voce ({comando, n, giocatore?}), i comandi
  // rifiutati perché arrivati su un'istantanea vecchia e la diagnosi del palco. Il motore, che
  // viene subito dopo, lo prende e lo toglie: il codice del gioco non lo vede (il confine resta
  // la pagina e il server, che ricontrollano tutto)
  Object.defineProperty(window, "__calliopeMotore", { configurable: true, writable: false, value: Object.freeze({
    stato: function (istantanea, ripresa) {
      var d = { istantanea: istantanea };
      if (ripresa !== undefined && ripresa !== null) d.ripresa = ripresa;
      manda("stato", d);
    },
    rifiutato: function (x) {
      x = x || {};
      manda("rifiutato", { comando: String(x.comando || "").slice(0, 24), motivo: String(x.motivo || "").slice(0, 20),
                           n: typeof x.n === "number" ? x.n : null });
    },
    quandoComando: quando("comando"),
    // La partita condivisa con il motore (14/10): lo stato che uno specchio disegna, la partita
    // passata a questo schermo, un nome scritto su uno specchio, e la mossa di uno specchio
    quandoPartita: quando("partita"),
    quandoAutorevole: quando("autorevole"),
    quandoSpecchio: quando("specchio"),
    quandoNome: quando("nome"),
    mossa: function (x) {
      x = x || {};
      var d = {};
      if (typeof x.comando === "string") { d.comando = x.comando.slice(0, 24); d.n = typeof x.n === "number" ? x.n : null; }
      if (typeof x.rinomina === "number") { d.rinomina = x.rinomina; d.nome = String(x.nome || "").slice(0, 20); }
      manda("mossa", d);
    },
    palco: function (difetti) {
      manda("palco", { difetti: Array.isArray(difetti) ? difetti.slice(0, 3).map(function (x) { return String(x).slice(0, 300); }) : [] });
    }
  }) });
  manda("pronto", {});
})();
"""

# Sfondo chiaro: i giochi scritti dall'agente danno quasi sempre per scontato il bianco (il primo
# memory della DGX aveva il titolo grigio scuro). Dal 14/10 niente scroll: il motore disegna su
# un palco di misura fissa (1280×720 o 720×1280) scalato e centrato nella finestra
_STILE_BASE = ("html,body{margin:0;padding:0;height:100%;background:#fafafa;color:#222;"
               "font-family:system-ui,sans-serif;overflow:hidden}"
               "#gioco{position:fixed;inset:0;overflow:hidden}")


# Lo stile del motore (13/10; il palco dal 14/10): il gioco lo cambia con le variabili nel suo
# .css (il tema), senza toccare la logica. Posizione, misura e corpo di ogni scatola li mette il
# motore in linea con !important (impagina): il tema non sposta né ingrandisce niente, così la
# misura della prova di fumo vale anche con il tema
STILE_MOTORE = (
    ":root{--sfondo:#fafafa;--testo:#222;--primario:#3557c9;--accento:#f39a2e;"
    "--carattere:system-ui,sans-serif;--raggio:12px;--casella:#ffffff;--bordo:#c8cdd8}"
    "html,body{background:var(--sfondo);color:var(--testo);font-family:var(--carattere)}"
    ".palco{position:absolute;left:50%;top:50%;transform-origin:center center;overflow:hidden}"
    ".palco>*{position:absolute;box-sizing:border-box;margin:0;padding:0;overflow:hidden;"
    "line-height:1.2;display:flex;align-items:center;justify-content:center;text-align:center;"
    "overflow-wrap:anywhere;font-family:var(--carattere)}"
    ".palco .titolo,.palco .grande,.palco .riga{font-weight:bold}"
    ".palco .sottotitolo{opacity:.8}"
    ".palco .comando{font-weight:normal;border:0;border-radius:var(--raggio);"
    "background:var(--primario);color:#fff;cursor:pointer;padding:0 18px}"
    ".palco .casella{border-radius:calc(var(--raggio) / 2);background:var(--casella);"
    "border:2px solid var(--bordo);color:var(--testo);padding:4px}"
    ".palco .casella.comando{border-color:var(--primario);color:var(--testo);padding:4px}"
    ".palco .casella img{max-width:100%;max-height:100%}"
    ".palco .punti{border-radius:var(--raggio);background:rgba(0,0,0,.05)}"
    ".palco .giocatore.tocca{font-weight:bold;border-bottom:4px solid var(--accento)}"
    ".palco .giocatore.nome{border:0;background:none;color:var(--testo);cursor:pointer;"
    "padding:0 18px}"
    ".palco .scrivi-nome{box-sizing:border-box;border:3px solid var(--primario);"
    "border-radius:var(--raggio);padding:0 12px;background:#fff;color:#222}"
    ".palco .avviso-nome{background:#fff3f3;color:#a00;text-align:center;margin:0}"
    ".palco .riga{border-radius:var(--raggio);background:rgba(0,0,0,.05);padding:0 16px}"
    ".palco .riga.tocca{outline:4px solid var(--accento)}"
    ".palco .riga.primo{background:var(--accento);color:#fff}"
    ".palco .tela{display:block;text-align:start}"
    ".errore-gioco{position:fixed;left:0;right:0;bottom:0;margin:0;padding:8px 12px;"
    "background:#fff3f3;color:#a00;font-size:18px;z-index:10}")

_MOTORE: str | None = None


def motore_js() -> str:
    """Il motore della macchina a stati (motore_gioco.js accanto a questo file)."""
    global _MOTORE
    if _MOTORE is None:
        from pathlib import Path
        _MOTORE = Path(__file__).with_name("motore_gioco.js").read_text(encoding="utf-8")
    return _MOTORE


def avvio_js(macchina: dict, giocatori: dict, titolo: str = "") -> str:
    """Lo script dopo quelli del gioco: avvia il motore con la logica (GIOCO) e la macchina."""
    dati = json.dumps({"macchina": macchina, "giocatori": giocatori,
                       "titolo": str(titolo or "")[:80]}, ensure_ascii=False)
    return ('CalliopeMotore.avvia(typeof GIOCO === "undefined" ? undefined : GIOCO, '
            + _js_sicuro(dati) + ");")


def _hash(testo: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(testo.encode("utf-8")).digest()).decode() + "'"


def _js_sicuro(js: str) -> str:
    """Il codice dentro <script>: «</script» non chiude il tag (in JS «<\\/script» è uguale)."""
    return re.sub(r"</(script)", r"<\\/\1", js, flags=re.I)


def documento(scheda: dict, file: dict[str, bytes], titolo: str = "") -> tuple[str, str]:
    """(HTML del riquadro, CSP) dai file della versione approvata. `file`: {percorso: byte}.
    `titolo`: il titolo del gioco (la pagina della preparazione). Un gioco senza la macchina
    (formato di prima del 14/10) non ha documento: SchedaNonValida."""
    if not scheda.get("macchina"):
        raise SchedaNonValida(SENZA_MACCHINA)
    risorse = {}
    for r in scheda.get("risorse") or []:
        dati = file.get(r)
        if dati is None:
            continue
        tipo = TIPI_RISORSA["." + r.rsplit(".", 1)[-1]]
        risorse[r] = f"data:{tipo};base64," + base64.b64encode(dati).decode("ascii")
    runtime = RUNTIME_JS.replace("__RISORSE__", json.dumps(risorse).replace("</", "<\\/"))
    # La macchina a stati (13/10): il motore prima degli script del gioco, l'avvio dopo (GIOCO è
    # una dichiarazione di logica.js nello stesso spazio globale)
    script = ([runtime, _js_sicuro(motore_js())]
              + [_js_sicuro(file.get(f, b"").decode("utf-8", "replace")) for f in scheda["file"]]
              + [avvio_js(scheda["macchina"], scheda["giocatori"], titolo)])
    base = _STILE_BASE + STILE_MOTORE
    css = base + "\n" + (file.get(scheda["stile"], b"").decode("utf-8", "replace")
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
