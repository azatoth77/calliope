"""
Adattatore Home Assistant per la casa a voce (base.py: HomeBackend).

Tutto passa da **una sola connessione WebSocket** (`/api/websocket`) tenuta aperta:
nessuna nuova connessione TLS a ogni comando, che su un Raspberry Pi piccolo costerebbe più del
comando stesso. Verificato sul sorgente di Home Assistant (home-assistant/core, ramo dev,
1/10/2026):

- autenticazione: `auth_required` → `{"type": "auth", "access_token": …}` → `auth_ok` /
  `auth_invalid`;
- entità esposte ad Assist: `homeassistant/expose_entity/list` (solo amministratori),
  `{"exposed_entities": {entity_id: {"conversation": true, …}}}`. REST `/api/states` da
  solo non sa cosa è esposto;
- nomi, alias e stanze: `config/entity_registry/get_entries`, `config/device_registry/list`,
  `config/area_registry/list`, `config/floor_registry/list`;
- stati: `subscribe_entities` con `entity_ids` = le sole esposte (stato compresso: «s»,
  «a», aggiunte «+» e tolte «-»). Le letture di casa_stato non costano una richiesta;
- comandi: prima `conversation/agent/homeassistant/debug` (riconosce la frase **senza
  eseguirla** e dice intent e bersagli), poi le regole di Calliope, poi
  `conversation/process` con `agent_id` = `conversation.home_assistant` (l'agente
  integrato, senza LLM: la documentazione dice ancora `home_assistant`, il codice usa
  l'id dell'entità) e `language: "it"`. Risposta: `response_type` action_done /
  query_answer / error, `data.success`/`failed`, `data.code`, `speech.plain.speech`.

L'agente integrato **non chiede conferme né PIN**: per una serratura esposta «sblocca la
porta» chiama `lock.unlock` (`OnOffIntentHandler`, componente intent). L'unica protezione
di HA è l'esposizione (serrature e allarme non sono esposti di predefinito, le porte del
garage sì: sono `cover`). Per questo le regole di Calliope bloccano i domini delicati
prima dell'esecuzione, grazie alla verifica a secco.

TLS: Home Assistant in casa risponde in HTTPS con il certificato del nome DuckDNS, quindi
sull'IP il nome non combacia. Tre modi, scelti in configurazione:
- `casa_tls_nome`: il nome atteso del certificato (SNI e verifica del nome), con la catena
  verificata dai certificati di sistema. Ci si collega all'IP, il nome non si risolve mai;
- `casa_tls_impronta`: l'impronta SHA-256 del certificato fissata (va bene anche per un
  certificato fatto in casa; cambia a ogni rinnovo);
- `casa_tls_verifica: false`: nessuna verifica, solo come scelta esplicita, con un avviso
  all'avvio.

Il token non compare mai in log, errori o diagnosi.
"""

import hashlib
import itertools
import json
import os
import re
import socket
import ssl
import tempfile
import threading
import time
from urllib.parse import urlparse

from .errori import riformula_errore

from .base import (Autorizza, CasaNonRisponde, Diagnosi, Entita, Esito, HomeBackend,
                   Interpretazione, nome_pulito)

AGENTE_INTEGRATO = "conversation.home_assistant"

# Intent dell'agente integrato (home-assistant/intents, frasi in sentences/it): cosa
# cambiano e cosa leggono. Il resto (ora, timer, liste, meteo, messaggi) non è della casa:
# Calliope ha i suoi tool, e i timer di HA vogliono un satellite.
INTENTI_COMANDO = {
    "HassTurnOn", "HassTurnOff", "HassToggle", "HassLightSet", "HassSetPosition",
    "HassClimateSetTemperature", "HassFanSetSpeed", "HassMediaPause", "HassMediaUnpause",
    "HassMediaNext", "HassMediaPrevious", "HassSetVolume", "HassSetVolumeRelative",
    "HassMediaPlayerMute", "HassMediaPlayerUnmute", "HassVacuumStart",
    "HassVacuumReturnToBase", "HassLawnMowerStartMowing", "HassLawnMowerDock",
}
INTENTI_LETTURA = {"HassGetState", "HassClimateGetTemperature"}

# Attributi tenuti per le frasi di stato
_ATTRIBUTI = ("current_position", "brightness", "current_temperature", "temperature",
              "hvac_action", "unit_of_measurement", "device_class", "friendly_name",
              # le entità meteo (09/10, casa/meteo.py)
              "humidity", "apparent_temperature", "wind_speed", "pressure", "cloud_coverage",
              "temperature_unit", "wind_speed_unit", "supported_features")


class _ErroreHA(Exception):
    """Errore restituito da Home Assistant a una richiesta (codice e messaggio)."""

    def __init__(self, code: str, message: str = ""):
        self.code, self.message = code, message
        super().__init__(f"{code}: {message}")


class _Diagnosticato(Exception):
    """Collegamento fallito con una diagnosi precisa."""

    def __init__(self, codice: str, testo: str, **dettagli):
        self.codice, self.dettagli = codice, {"errore": testo, **dettagli}
        super().__init__(testo)


class _Segreto:
    """Il token: si legge solo con .valore; repr e str non lo mostrano mai (né in un
    traceback né stampando gli attributi dell'adattatore)."""
    __slots__ = ("_v",)

    def __init__(self, v: str):
        self._v = v

    @property
    def valore(self) -> str:
        return self._v

    def __repr__(self):
        return "<token nascosto>"

    __str__ = __repr__


class _Attesa:
    __slots__ = ("event", "result", "error")

    def __init__(self):
        self.event = threading.Event()
        self.result = None
        self.error = None


def fingerprint(der: bytes) -> str:
    """Impronta SHA-256 come la mostrano i browser: «AB:CD:…»."""
    h = hashlib.sha256(der).hexdigest().upper()
    return ":".join(h[i:i + 2] for i in range(0, len(h), 2))


def _norm_fp(fp: str) -> str:
    return "".join(c for c in (fp or "").upper() if c in "0123456789ABCDEF")


def cert_names(der: bytes) -> list[str]:
    """I nomi del certificato (SAN DNS, o il CN), letti senza verificarlo: servono solo a
    dire «il certificato è per …duckdns.org» nella diagnosi. Usa un decodificatore interno
    di CPython; se non c'è, nessun nome."""
    try:
        pem = ssl.DER_cert_to_PEM_cert(der)
        with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
            f.write(pem)
            path = f.name
        try:
            info = ssl._ssl._test_decode_cert(path)       # noqa: SLF001
        finally:
            os.unlink(path)
    except Exception:  # noqa: BLE001
        return []
    names = [v for k, v in info.get("subjectAltName", ()) if k == "DNS"]
    if not names:
        names = [v for rdn in info.get("subject", ()) for k, v in rdn if k == "commonName"]
    return names


class HomeAssistantBackend(HomeBackend):
    nome_sistema = "Home Assistant"

    def __init__(self, url: str, token: str, agente: str = AGENTE_INTEGRATO,
                 lingua: str = "it", timeout_s: float = 4.0, connessione_s: float = 3.0,
                 tls_nome: str | None = None, tls_impronta: str | None = None,
                 tls_verifica: bool = True, tls_ca: str | None = None,
                 aggiorna_s: float = 300.0, log=print):
        u = urlparse(url.strip())
        if u.scheme not in ("http", "https") or not u.hostname:
            raise ValueError("casa_url deve essere come https://192.168.1.10:8123")
        self.url = f"{u.scheme}://{u.hostname}:{u.port or (443 if u.scheme == 'https' else 80)}"
        self.host, self.port = u.hostname, u.port or (443 if u.scheme == "https" else 80)
        self.tls = u.scheme == "https"
        self._token = _Segreto(token)
        self.agente = agente or AGENTE_INTEGRATO
        self.lingua = lingua or "it"
        self.timeout_s = float(timeout_s)
        self.connessione_s = float(connessione_s)
        self.tls_nome = (tls_nome or "").strip() or None
        self.tls_impronta = _norm_fp(tls_impronta or "") or None
        self.tls_verifica = bool(tls_verifica)
        self.tls_ca = tls_ca or None
        self.aggiorna_s = float(aggiorna_s)
        self._log = log or (lambda *_a, **_k: None)

        self.versione: str | None = None
        self.agente_ok = False
        self._ws = None
        self._ids = itertools.count(1)
        self._send_lock = threading.Lock()
        self._attese: dict[int, _Attesa] = {}
        self._subs: set[int] = set()
        self._esposte: list[str] = []
        self._meta: dict[str, dict] = {}
        self._aree: dict[str, list[str]] = {}
        self._stati: dict[str, dict] = {}
        self._caricato = 0.0
        self._aggiornando = threading.Lock()
        self._ready = threading.Event()
        self._tentato = threading.Event()   # un tentativo di collegamento è finito
        # Tentativi di collegamento iniziati e finiti: una richiesta aspetta un tentativo
        # iniziato *dopo* di lei (vedi _assicura)
        self._iniziati = 0
        self._finiti = 0
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._diag = Diagnosi("in_corso", {})
        self._ultimo_detto = None
        self.ultimi_tempi: dict = {}
        self._thread = threading.Thread(target=self._run, name="casa-ha", daemon=True)

    def __repr__(self):                   # mai il token, nemmeno in un traceback
        return f"<HomeAssistantBackend {self.url}>"

    # ─────────────────────────── ciclo di collegamento ───────────────────────────

    def avvia(self):
        """Si collega in secondo piano: l'avvio di Calliope non aspetta Home Assistant."""
        self._thread.start()

    def close(self):
        self._stop.set()
        self._wake.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass

    def _run(self):
        pause = 0.0
        while not self._stop.is_set():
            if pause:
                self._wake.wait(pause)      # una richiesta sveglia subito un nuovo tentativo
                self._wake.clear()
                if self._stop.is_set():
                    break
            self._iniziati += 1
            try:
                ws = self._collega()
            except _Diagnosticato as e:
                self._fallito(e.codice, e.dettagli)
                pause = min(60.0, max(5.0, pause * 2))
                self._finiti = self._iniziati
                self._tentato.set()
                continue
            except Exception as e:  # noqa: BLE001
                self._fallito("non_raggiunge", {"errore": _testo(e)})
                pause = min(60.0, max(5.0, pause * 2))
                self._finiti = self._iniziati
                self._tentato.set()
                continue
            pause = 0.0
            self._finiti = self._iniziati
            self._tentato.set()
            self._leggi(ws)
            if not self._stop.is_set():
                self._fallito("non_raggiunge", {"errore": "connessione chiusa da Home Assistant"})
                pause = 2.0

    def _fallito(self, codice: str, dettagli: dict):
        self._ready.clear()
        self._diag = Diagnosi(codice, dettagli)
        said = (codice, dettagli.get("errore"))
        if said != self._ultimo_detto:      # niente righe ripetute a ogni tentativo
            self._ultimo_detto = said
            self._log(f"[CASA] Home Assistant non collegata ({codice}: {dettagli.get('errore')})."
                      f" Riprovo in secondo piano e alla prima richiesta.")

    # ── TLS e socket ──

    def _socket_tls(self) -> socket.socket:
        """Socket TLS già verificato secondo la configurazione."""
        raw = socket.create_connection((self.host, self.port), timeout=self.connessione_s)
        try:
            if self.tls_impronta or not self.tls_verifica:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            else:
                ctx = ssl.create_default_context(cafile=self.tls_ca)
            # websockets legge e scrive da thread diversi: socket TLS adatto (tls_sicuro.py)
            from ..tls_sicuro import sicuro
            sock = sicuro(ctx).wrap_socket(raw, server_hostname=self.tls_nome or self.host)
        except ssl.SSLCertVerificationError as e:
            raw.close()
            names = self._nomi_certificato()
            # 62 = nome diverso, 64 = IP diverso (ci si collega all'IP, il certificato è
            # per il nome DuckDNS: è il caso tipico della casa)
            if getattr(e, "verify_code", None) in (62, 64) or "mismatch" in str(e).lower():
                raise _Diagnosticato("tls_nome", "il nome del certificato non combacia",
                                     nomi=names) from None
            raise _Diagnosticato("tls_certificato", f"certificato non verificabile "
                                 f"({getattr(e, 'verify_message', '') or e})", nomi=names) from None
        except ssl.SSLError as e:
            raw.close()
            raise _Diagnosticato("non_raggiunge", f"errore TLS: {e}") from None
        except BaseException:
            raw.close()
            raise
        if self.tls_impronta:
            found = fingerprint(sock.getpeercert(binary_form=True) or b"")
            if _norm_fp(found) != self.tls_impronta:
                sock.close()
                raise _Diagnosticato("tls_impronta", "l'impronta del certificato è diversa",
                                     trovata=found)
        return sock

    def _nomi_certificato(self) -> list[str]:
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
            with socket.create_connection((self.host, self.port), self.connessione_s) as raw:
                with ctx.wrap_socket(raw, server_hostname=self.tls_nome or self.host) as s:
                    return cert_names(s.getpeercert(binary_form=True) or b"")
        except Exception:  # noqa: BLE001
            return []

    def _apri(self):
        from websockets.sync.client import connect
        try:
            sock = self._socket_tls() if self.tls else socket.create_connection(
                (self.host, self.port), timeout=self.connessione_s)
        except _Diagnosticato:
            raise
        except (TimeoutError, socket.timeout):
            raise _Diagnosticato("non_raggiunge", f"nessuna risposta entro "
                                 f"{self.connessione_s:g} s") from None
        except ConnectionRefusedError:
            raise _Diagnosticato("non_raggiunge", "connessione rifiutata (porta chiusa o "
                                 "servizio spento)") from None
        except OSError as e:
            raise _Diagnosticato("non_raggiunge", _testo(e)) from None
        # Il socket è già TLS e verificato: websockets parla sopra senza rifare TLS
        # (schema ws://). Niente proxy di sistema: è una connessione di casa.
        try:
            return connect(f"ws://{self.host}:{self.port}/api/websocket", sock=sock,
                           proxy=None, open_timeout=self.connessione_s,
                           max_size=32 * 1024 * 1024, compression=None,
                           ping_interval=20, ping_timeout=20, close_timeout=2,
                           user_agent_header="Calliope")
        except Exception as e:  # noqa: BLE001
            sock.close()
            text = _testo(e)
            if "200" in text or "404" in text or "invalid" in text.lower():
                raise _Diagnosticato("non_raggiunge", f"risponde ma non come Home Assistant "
                                     f"({text})") from None
            raise _Diagnosticato("non_raggiunge", text) from None

    # ── autenticazione e caricamento ──

    def _collega(self):
        ws = self._apri()
        try:
            ws.socket.settimeout(None)
            hello = json.loads(ws.recv(timeout=self.connessione_s))
            if hello.get("type") != "auth_required":
                raise _Diagnosticato("non_raggiunge", "risposta inattesa: non sembra Home "
                                     "Assistant")
            ws.send(json.dumps({"type": "auth", "access_token": self._token.valore}))
            reply = json.loads(ws.recv(timeout=self.connessione_s))
            if reply.get("type") == "auth_invalid":
                # Il messaggio di HA («Invalid access token or password») non contiene il token
                raise _Diagnosticato("token_rifiutato", "token rifiutato da Home Assistant")
            if reply.get("type") != "auth_ok":
                raise _Diagnosticato("non_raggiunge", f"autenticazione: risposta "
                                     f"{reply.get('type')!r}")
            self.versione = reply.get("ha_version") or hello.get("ha_version")

            def call(payload):
                return self._diretta(ws, payload)

            try:
                agents = call({"type": "conversation/agent/list", "language": self.lingua})
            except _ErroreHA:
                agents = {}                  # HA troppo vecchio: niente comandi, letture sì
            ids = {a.get("id") for a in (agents or {}).get("agents", [])}
            self.agente_ok = self.agente in ids or (self.agente == AGENTE_INTEGRATO
                                                    and "homeassistant" in ids)
            self._carica(call)
            self._subs.clear()
            self._stati = {}
            if self._esposte:
                sid = next(self._ids)
                self._subs.add(sid)
                self._diretta(ws, {"type": "subscribe_entities", "entity_ids": self._esposte},
                              sid=sid)
                first = json.loads(ws.recv(timeout=self.timeout_s))
                if first.get("type") == "event":
                    self._applica(first.get("event") or {})
        except _Diagnosticato:
            ws.close()
            raise
        except _ErroreHA as e:
            ws.close()
            if e.code == "unauthorized":
                raise _Diagnosticato("non_admin", "il token non è di un amministratore: "
                                     "l'elenco delle entità esposte non si può leggere") from None
            raise _Diagnosticato("non_raggiunge", f"errore di Home Assistant: {e}") from None
        except TimeoutError:
            ws.close()
            raise _Diagnosticato("non_raggiunge", f"Home Assistant non ha risposto entro "
                                 f"{self.connessione_s:g} s") from None
        except Exception:
            ws.close()
            raise
        self._ws = ws
        n = len(self._esposte)
        if not self.agente_ok:
            self._diag = Diagnosi("agente_assente", {"versione": self.versione,
                                                     "agente": self.agente})
        elif n == 0:
            self._diag = Diagnosi("nessuna_entita", {"versione": self.versione})
        else:
            self._diag = Diagnosi("ok", {"versione": self.versione, "entita": n,
                                         "aree": len({m.get("area") for m in self._meta.values()
                                                      if m.get("area")})})
        self._ready.set()
        said = ("ok", self.versione, n)
        if said != self._ultimo_detto:
            self._ultimo_detto = said
            self._log(f"[CASA] Collegata a Home Assistant {self.versione}: {n} entità esposte"
                      + (f" ({_conteggio(self._esposte)})" if n else
                         " (nessuna: vanno esposte ad Assist)")
                      + ("" if self.agente_ok else f"; agente {self.agente} assente"))
        return ws

    def _diretta(self, ws, payload: dict, sid: int | None = None):
        """Richiesta durante il collegamento, prima che parta il lettore."""
        mid = sid or next(self._ids)
        ws.send(json.dumps({"id": mid, **payload}))
        deadline = time.monotonic() + self.timeout_s
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError
            msg = json.loads(ws.recv(timeout=left))
            if msg.get("type") == "event" and msg.get("id") in self._subs:
                self._applica(msg.get("event") or {})
                continue
            if msg.get("id") != mid or msg.get("type") != "result":
                continue
            if not msg.get("success"):
                err = msg.get("error") or {}
                raise _ErroreHA(err.get("code", "unknown"), err.get("message", ""))
            return msg.get("result")

    def _carica(self, call):
        """Esposte, nomi, alias, stanze e piani."""
        exposed = (call({"type": "homeassistant/expose_entity/list"}) or {}).get(
            "exposed_entities", {})
        ids = sorted(eid for eid, a in exposed.items() if (a or {}).get("conversation"))
        entries = call({"type": "config/entity_registry/get_entries",
                        "entity_ids": ids}) if ids else {}
        devices = {d.get("id"): d for d in (call({"type": "config/device_registry/list"}) or [])}
        areas = {a.get("area_id"): a for a in (call({"type": "config/area_registry/list"}) or [])}
        try:
            floors = {f.get("floor_id"): f for f in
                      (call({"type": "config/floor_registry/list"}) or [])}
        except _ErroreHA:
            floors = {}
        meta = {}
        for eid in ids:
            ent = (entries or {}).get(eid) or {}
            area_id = ent.get("area_id") or (devices.get(ent.get("device_id")) or {}).get("area_id")
            area = areas.get(area_id) or {}
            floor = floors.get(area.get("floor_id")) or {}
            meta[eid] = {"nome": ent.get("name") or ent.get("original_name"),
                         "alias": [a for a in (ent.get("aliases") or []) if a],
                         "classe": ent.get("device_class") or ent.get("original_device_class"),
                         "area": area.get("name"), "piano": floor.get("name")}
        self._aree = {a.get("name"): [x for x in (a.get("aliases") or []) if x]
                      for a in areas.values() if a.get("name")}
        self._aree.update({f.get("name"): [x for x in (f.get("aliases") or []) if x]
                           for f in floors.values() if f.get("name")})
        self._meta, self._esposte = meta, ids
        self._caricato = time.monotonic()

    # ── lettore ──

    def _leggi(self, ws):
        try:
            for raw in ws:
                try:
                    msg = json.loads(raw)
                except (TypeError, json.JSONDecodeError):
                    continue
                kind = msg.get("type")
                if kind == "result":
                    a = self._attese.pop(msg.get("id"), None)
                    if a is not None:
                        if msg.get("success"):
                            a.result = msg.get("result")
                        else:
                            err = msg.get("error") or {}
                            a.error = _ErroreHA(err.get("code", "unknown"), err.get("message", ""))
                        a.event.set()
                elif kind == "event" and msg.get("id") in self._subs:
                    self._applica(msg.get("event") or {})
        except Exception:  # noqa: BLE001 — connessione chiusa o rotta: si ricollega
            pass
        finally:
            self._ready.clear()
            self._ws = None
            for a in list(self._attese.values()):
                a.error = CasaNonRisponde("connessione con Home Assistant chiusa")
                a.event.set()
            self._attese.clear()

    def _applica(self, ev: dict):
        """Stati compressi di subscribe_entities: «a» aggiunte, «c» cambi, «r» tolte."""
        for eid, st in (ev.get("a") or {}).items():
            self._stati[eid] = {"s": st.get("s"), "a": dict(st.get("a") or {})}
        for eid, diff in (ev.get("c") or {}).items():
            cur = self._stati.setdefault(eid, {"s": None, "a": {}})
            plus = diff.get("+") or {}
            if "s" in plus:
                cur["s"] = plus["s"]
            if "a" in plus:
                cur["a"].update(plus["a"])
            for k in (diff.get("-") or {}).get("a", []):
                cur["a"].pop(k, None)
        for eid in ev.get("r") or []:
            self._stati.pop(eid, None)

    # ─────────────────────────── richieste ───────────────────────────

    def _assicura(self):
        if self._ready.is_set():
            return
        self._tentato.clear()
        # Vale solo un tentativo iniziato dopo questa richiesta: uno già in corso era partito
        # quando HA forse era ancora spento, e se fallisce non dice niente di adesso (01/10:
        # con HA appena riacceso la prima richiesta poteva cadere sul tentativo vecchio, una
        # delle cause dell'instabilità di prova_casa_ha)
        need = self._iniziati + 1
        if not self._thread.is_alive() and not self._stop.is_set():
            self.avvia()
        self._wake.set()
        # Si aspetta la fine del tentativo, non tutto il tempo massimo: con HA spento la
        # connessione è rifiutata subito e la risposta arriva subito. Chi parla non aspetta
        # mai più di casa_connessione_s: se HA è lento il tentativo continua in secondo piano.
        deadline = time.monotonic() + self.connessione_s + 0.5
        while time.monotonic() < deadline and not self._ready.is_set():
            self._tentato.wait(min(0.2, max(0.0, deadline - time.monotonic())))
            self._tentato.clear()
            if self._finiti >= need and not self._ready.is_set():
                break
        if not self._ready.is_set():
            raise CasaNonRisponde(self._diag.dettagli.get("errore") or "Home Assistant non risponde")

    def _richiesta(self, payload: dict, timeout: float | None = None):
        self._assicura()
        ws = self._ws
        if ws is None:
            raise CasaNonRisponde("connessione con Home Assistant chiusa")
        a = _Attesa()
        with self._send_lock:
            mid = next(self._ids)
            self._attese[mid] = a
            try:
                ws.send(json.dumps({"id": mid, **payload}))
            except Exception as e:  # noqa: BLE001
                self._attese.pop(mid, None)
                raise CasaNonRisponde(f"invio fallito: {_testo(e)}") from None
        if not a.event.wait(timeout or self.timeout_s):
            self._attese.pop(mid, None)
            raise CasaNonRisponde(f"Home Assistant non ha risposto entro "
                                  f"{timeout or self.timeout_s:g} s")
        if a.error is not None:
            raise a.error
        return a.result

    def _forse_aggiorna(self):
        """Esposizione e nomi si rileggono ogni `aggiorna_s`, in secondo piano: chi espone
        una luce nuova non deve riavviare Calliope."""
        if time.monotonic() - self._caricato < self.aggiorna_s or self._aggiornando.locked():
            return

        def job():
            with self._aggiornando:
                try:
                    old = set(self._esposte)
                    self._carica(lambda p: self._richiesta(p))
                    if set(self._esposte) != old:
                        self._risottoscrivi()
                except Exception:  # noqa: BLE001 — si riprova al prossimo giro
                    self._caricato = time.monotonic()

        threading.Thread(target=job, name="casa-aggiorna", daemon=True).start()

    def _risottoscrivi(self):
        ws, old = self._ws, set(self._subs)
        if ws is None:
            return
        a = _Attesa()
        with self._send_lock:
            sid = next(self._ids)
            self._subs.add(sid)
            self._attese[sid] = a
            ws.send(json.dumps({"id": sid, "type": "subscribe_entities",
                                "entity_ids": self._esposte}))
        a.event.wait(self.timeout_s)
        for s in old:
            try:
                self._richiesta({"type": "unsubscribe_events", "subscription": s})
            except Exception:  # noqa: BLE001
                pass
            self._subs.discard(s)
        keep = set(self._esposte)
        for eid in list(self._stati):
            if eid not in keep:
                self._stati.pop(eid, None)

    # ─────────────────────────── interfaccia di capacità ───────────────────────────

    def aree(self) -> dict[str, list[str]]:
        return dict(self._aree)

    def entita(self) -> list[Entita]:
        self._assicura()
        self._forse_aggiorna()
        out = []
        for eid in self._esposte:
            m = self._meta.get(eid, {})
            st = self._stati.get(eid) or {}
            attrs = st.get("a") or {}
            out.append(Entita(
                id=eid, nome=nome_pulito(attrs.get("friendly_name") or m.get("nome")
                                         or eid.split(".", 1)[1]),
                dominio=eid.split(".", 1)[0],
                classe=attrs.get("device_class") or m.get("classe"),
                area=m.get("area"), piano=m.get("piano"),
                alias=[nome_pulito(a) for a in (m.get("alias") or []) if isinstance(a, str)],
                stato=st.get("s"), unita=attrs.get("unit_of_measurement"),
                attributi={k: attrs[k] for k in _ATTRIBUTI if k in attrs}))
        return out

    def meteo_esposte(self) -> list[str]:
        # Nessun _assicura: l'elenco dell'ultimo caricamento (resta anche con HA spento). Con HA
        # collegata l'esposizione si rilegge in secondo piano ogni aggiorna_s (non blocca)
        if self._ready.is_set():
            self._forse_aggiorna()
        return [eid for eid in list(self._esposte) if eid.startswith("weather.")]

    def previsioni(self, entity_id: str, tipo: str = "daily") -> list[dict]:
        """`weather.get_forecasts` (HA 2023.12 e seguenti), servizio di sola lettura con la
        risposta: `call_service` con `return_response`. Solo un'entità meteo esposta e solo
        questo servizio: nessun altro servizio di HA si chiama fuori dai comandi verificati a
        secco."""
        if not str(entity_id).startswith("weather.") or entity_id not in self._esposte:
            raise ValueError("entità meteo non esposta")
        if tipo not in ("daily", "hourly", "twice_daily"):
            raise ValueError("tipo di previsione sconosciuto")
        r = self._richiesta({"type": "call_service", "domain": "weather",
                             "service": "get_forecasts", "service_data": {"type": tipo},
                             "target": {"entity_id": entity_id}, "return_response": True})
        resp = (r or {}).get("response") or {}
        voci = (resp.get(entity_id) or {}).get("forecast") or []
        return [v for v in voci if isinstance(v, dict)]

    def _interpreta(self, res: dict | None) -> Interpretazione:
        if not res:
            return Interpretazione(capito=False)
        if res.get("source") == "trigger":
            return Interpretazione(capito=True, azione="altro", intento="trigger",
                                   origine="propria")
        name = (res.get("intent") or {}).get("name", "")
        if not res.get("match"):
            missing = [str(v) for v in (res.get("unmatched_slots") or {}).values() if v]
            return Interpretazione(capito=False, intento=name, non_trovati=missing)
        azione = ("comando" if name in INTENTI_COMANDO else
                  "lettura" if name in INTENTI_LETTURA else "altro")
        return Interpretazione(capito=True, azione=azione, intento=name,
                               bersagli=list((res.get("targets") or {}).keys()),
                               origine="propria" if res.get("source") == "custom"
                               else "predefinita")

    def comando(self, testo: str, autorizza: Autorizza) -> Esito:
        t0 = time.perf_counter()
        self._assicura()
        self._forse_aggiorna()
        if not self.agente_ok:
            return Esito(False, "errore", codice="agente_assente")
        try:
            dbg = self._richiesta({"type": "conversation/agent/homeassistant/debug",
                                   "sentences": [testo], "language": self.lingua})
        except _ErroreHA as e:
            # Senza la verifica a secco non si sa cosa farebbe: non si esegue
            return Esito(False, "errore", codice="verifica_assente",
                         frase=f"verifica non disponibile ({e.code})")
        res = ((dbg or {}).get("results") or [None])[0]
        interp = self._interpreta(res)
        t1 = time.perf_counter()
        self.ultimi_tempi = {"verifica_s": round(t1 - t0, 3)}
        if not interp.capito:
            return Esito(False, "errore", codice="non_capito", interpretazione=interp,
                         tempi=dict(self.ultimi_tempi))
        motivo = autorizza(interp)
        if motivo:
            return Esito(False, "rifiuto", codice=motivo, interpretazione=interp,
                         bersagli=interp.bersagli, tempi=dict(self.ultimi_tempi))
        try:
            r = self._richiesta({"type": "conversation/process", "text": testo,
                                 "language": self.lingua, "agent_id": self.agente})
        except _ErroreHA as e:
            return Esito(False, "errore", codice="fallito", frase=e.message,
                         interpretazione=interp)
        except CasaNonRisponde:
            # Il comando è partito: HA può eseguirlo anche dopo il tempo massimo
            return Esito(False, "errore", codice="lento", interpretazione=interp,
                         bersagli=interp.bersagli)
        t2 = time.perf_counter()
        self.ultimi_tempi["esecuzione_s"] = round(t2 - t1, 3)
        esito = self._esito(r or {}, interp)
        esito.tempi = dict(self.ultimi_tempi)
        return esito

    @staticmethod
    def _esito(r: dict, interp: Interpretazione) -> Esito:
        resp = r.get("response") or {}
        kind = resp.get("response_type")
        speech = (((resp.get("speech") or {}).get("plain") or {}).get("speech") or "").strip()
        data = resp.get("data") or {}
        speech = _ritocca(speech)
        if kind == "action_done":
            ok_ids = [s.get("id") for s in data.get("success", []) if s.get("type") == "entity"]
            failed = [s.get("name") or s.get("id") for s in data.get("failed", [])]
            ok = bool(data.get("success")) or not failed
            return Esito(ok, "fatto" if ok else "errore", speech or "Fatto.",
                         codice="" if ok else "fallito", bersagli=ok_ids or interp.bersagli,
                         falliti=failed, interpretazione=interp)
        if kind == "query_answer":
            return Esito(True, "risposta", speech, bersagli=interp.bersagli,
                         interpretazione=interp)
        # Errori: le frasi tecniche di HA («nell'area Taverna il dominio light non è stato
        # esposto», 01/10) in italiano normale (casa/errori.py)
        code = data.get("code") or "unknown"
        speech, _ = riformula_errore(speech, code)
        return Esito(False, "errore", speech, codice=code, interpretazione=interp)

    def attendi_primo_tentativo(self, max_s: float) -> bool:
        end = time.monotonic() + max(0.0, max_s)
        while self._finiti < 1 and not self._ready.is_set():
            left = end - time.monotonic()
            if left <= 0:
                return False
            self._tentato.wait(min(0.05, left))
        return True

    def diagnosi(self, riprova: bool = False) -> Diagnosi:
        if riprova and not self._ready.is_set():
            try:
                self._assicura()
            except CasaNonRisponde:
                pass
        if self._ready.is_set() and self._diag.codice == "ok":
            self._diag.dettagli["entita"] = len(self._esposte)
        return Diagnosi(self._diag.codice, dict(self._diag.dettagli))


def _ritocca(speech: str) -> str:
    """Due difetti delle risposte italiane di HA, che riusano la parola detta: «Ho aperto
    tutte le tapparella» e «Ho spento le luci in piano di sopra»."""
    s = re.sub(r"\btutte le (\w+?)a\b", r"tutte le \1e", speech or "")
    s = re.sub(r"\bin (primo|secondo|terzo|piano)\b", r"al \1", s)
    if s and s[-1] not in ".!?":
        s += "."
    return s


def _conteggio(ids: list[str]) -> str:
    counts: dict[str, int] = {}
    for eid in ids:
        d = eid.split(".", 1)[0]
        counts[d] = counts.get(d, 0) + 1
    return ", ".join(f"{d} {n}" for d, n in sorted(counts.items(), key=lambda x: -x[1]))


def _testo(e: BaseException) -> str:
    return f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
