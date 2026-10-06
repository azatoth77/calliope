"""
Un Home Assistant finto per le prove della casa (prova_casa_ha.py, prova_casa_ha_ollama.py).

È un vero server WebSocket (websockets, in un thread) che parla il protocollo di HA:
autenticazione, entità esposte, registri, subscribe_entities con gli stati compressi,
conversation/agent/list, conversation/agent/homeassistant/debug e conversation/process.
Le frasi le riconosce **hassil con le frasi italiane vere di Home Assistant**
(pacchetto home-assistant-intents), come l'agente integrato: una frase che il vero HA non
capirebbe, qui non passa. Solo per le prove:

    pip install hassil home-assistant-intents

Le azioni cambiano gli stati in memoria e mandano gli eventi ai client iscritti; ogni
servizio eseguito finisce in `servizi`, così le prove vedono cosa è stato fatto davvero.
Il token finto non è un segreto: serve a controllare che Calliope non lo stampi mai.
"""

import json
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

VERSIONE = "2026.9.3"
TOKEN = "tok-finto-0123456789abcdef-NON-STAMPARE"
NOME_CERT = "casa-finta.duckdns.org"

AREE = {
    "cucina": {"name": "Cucina", "aliases": [], "floor_id": "terra"},
    "sala": {"name": "Sala", "aliases": ["soggiorno", "salotto"], "floor_id": "terra"},
    "ingresso": {"name": "Ingresso", "aliases": [], "floor_id": "terra"},
    "garage": {"name": "Garage", "aliases": [], "floor_id": "terra"},
    "giardino": {"name": "Giardino", "aliases": [], "floor_id": None},
    "camera": {"name": "Camera", "aliases": ["camera da letto"], "floor_id": "sopra"},
    "cameretta": {"name": "Cameretta", "aliases": [], "floor_id": "sopra"},
    "bagno": {"name": "Bagno", "aliases": [], "floor_id": "sopra"},
    "studio": {"name": "Studio", "aliases": [], "floor_id": "sopra"},
}
PIANI = {"terra": {"name": "Piano terra", "aliases": ["piano di sotto"], "level": 0},
         "sopra": {"name": "Primo piano", "aliases": ["piano di sopra"], "level": 1}}


def _e(eid, nome, area, stato, classe=None, esposta=True, alias=(), attr=None, device=None):
    return {"id": eid, "nome": nome, "area": area, "stato": stato, "classe": classe,
            "esposta": esposta, "alias": list(alias), "attr": dict(attr or {}),
            "device": device}


def entita_casa() -> list[dict]:
    """Una casa realistica: luci per stanza, tapparelle, termostato, sensori, una
    serratura, l'allarme, prese, porta del garage, cancello, e due entità NON esposte."""
    return [
        _e("light.cucina", "Luce cucina", "cucina", "off"),
        _e("light.sottopensile", "Sottopensile", "cucina", "off"),
        _e("light.lampadario_sala", "Lampadario sala", "sala", "on", attr={"brightness": 255}),
        _e("light.piantana", "Piantana", "sala", "off", alias=["lampada da terra"]),
        _e("light.camera", "Luce camera", None, "off", device="dev_camera"),
        _e("light.comodino", "Lampada comodino", "camera", "off"),
        _e("light.cameretta", "Luce cameretta", "cameretta", "off"),
        _e("light.bagno", "Luce bagno", "bagno", "on", attr={"brightness": 128}),
        _e("light.studio", "Luce studio", "studio", "off"),
        _e("light.giardino", "Luci giardino", "giardino", "off"),
        _e("cover.sala", "Tapparella sala", "sala", "open", "shutter",
           attr={"current_position": 100}),
        _e("cover.cucina", "Tapparella cucina", "cucina", "open", "shutter",
           attr={"current_position": 100}),
        _e("cover.camera", "Tapparella camera", "camera", "closed", "shutter",
           attr={"current_position": 0}),
        _e("cover.garage", "Porta del garage", "garage", "closed", "garage",
           attr={"current_position": 0}),
        _e("cover.cancello", "Cancello", "giardino", "closed", "gate"),
        _e("climate.termostato", "Termostato", "sala", "heat",
           attr={"current_temperature": 20.5, "temperature": 21, "hvac_action": "heating"}),
        _e("sensor.temperatura_camera", "Temperatura camera", "camera", "19.8", "temperature",
           attr={"unit_of_measurement": "°C"}),
        _e("sensor.temperatura_esterna", "Temperatura esterna", "giardino", "14.2",
           "temperature", attr={"unit_of_measurement": "°C"}),
        _e("sensor.umidita_bagno", "Umidità bagno", "bagno", "63", "humidity",
           attr={"unit_of_measurement": "%"}),
        _e("binary_sensor.finestra_cucina", "Finestra cucina", "cucina", "on", "window"),
        _e("binary_sensor.porta_ingresso", "Porta ingresso", "ingresso", "off", "door"),
        _e("switch.presa_tv", "Presa TV", "sala", "on"),
        _e("switch.presa_lavatrice", "Presa lavatrice", "bagno", "off"),
        _e("lock.ingresso", "Serratura ingresso", "ingresso", "locked"),
        _e("alarm_control_panel.casa", "Allarme", "ingresso", "disarmed"),
        _e("scene.cinema", "Cinema", "sala", "unknown"),
        # Non esposte: Calliope non deve né vederle né comandarle
        _e("light.laboratorio", "Luce laboratorio", "garage", "off", esposta=False),
        _e("switch.server", "Server", "studio", "on", esposta=False),
    ]


DISPOSITIVI = [{"id": "dev_camera", "area_id": "camera", "name": "Plafoniera camera",
                "name_by_user": None}]

_INTENTS = None


def _intents():
    global _INTENTS
    if _INTENTS is None:
        from hassil import Intents
        from home_assistant_intents import get_intents
        _INTENTS = (Intents.from_dict(get_intents("it")), get_intents("it")["responses"])
    return _INTENTS


def errore_ha(chiave: str, **valori) -> str:
    """Il testo vero di una risposta d'errore italiana di HA (home-assistant-intents), con i
    valori al posto dei segnaposto («{{ area }}», «{{ state | lower }}»)."""
    template = _intents()[1]["errors"][chiave]
    return re.sub(r"\{\{\s*(\w+)(?:\s*\|\s*\w+)?\s*\}\}",
                  lambda m: str(valori.get(m.group(1), "")), template)


def disponibile() -> str | None:
    """None se l'HA finto può girare, altrimenti cosa manca."""
    try:
        import hassil  # noqa: F401
        import home_assistant_intents  # noqa: F401
        import websockets  # noqa: F401
    except ImportError as e:
        return f"{e.name} (pip install hassil home-assistant-intents websockets)"
    return None


# ─────────────────────────── certificati per le prove TLS ───────────────────────────

def openssl() -> str | None:
    for c in (shutil.which("openssl"), r"C:\Program Files\Git\usr\bin\openssl.exe",
              r"C:\Program Files\Git\mingw64\bin\openssl.exe"):
        if c and Path(c).exists():
            return c
    return None


def crea_certificato(cartella: Path, nome: str = NOME_CERT) -> tuple[Path, Path] | None:
    """Certificato autofirmato per `nome` (come quello DuckDNS di casa), oppure None se
    openssl non c'è (le prove TLS saltano)."""
    exe = openssl()
    if exe is None:
        return None
    cert, key = cartella / "cert.pem", cartella / "key.pem"
    r = subprocess.run([exe, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                        "-subj", f"/CN={nome}", "-keyout", str(key), "-out", str(cert),
                        "-addext", f"subjectAltName=DNS:{nome}",
                        "-addext", "basicConstraints=critical,CA:TRUE",
                        "-addext", "keyUsage=critical,keyCertSign,digitalSignature,keyEncipherment",
                        "-addext", "extendedKeyUsage=serverAuth"],
                       capture_output=True, text=True)
    return (cert, key) if r.returncode == 0 else None


# ─────────────────────────── server ───────────────────────────

class FakeHA:
    def __init__(self, token: str = TOKEN, entita: list[dict] | None = None, admin: bool = True,
                 agente: bool = True, ritardo_s: float = 0.0, ssl_files=None,
                 frasi_proprie: dict | None = None):
        self.token, self.admin, self.agente = token, admin, agente
        self.ritardo_s = ritardo_s
        self.entita = {e["id"]: e for e in (entita if entita is not None else entita_casa())}
        self.frasi_proprie = frasi_proprie or {"buonanotte casa": "trigger"}
        # Frase → (codice, chiave dell'errore di HA, valori): conversation/process risponde
        # con quell'errore vero di HA (01/10: «nell'area Taverna il dominio light non è
        # stato esposto», che la verifica a secco non aveva previsto)
        self.errori_forzati: dict[str, tuple[str, str, dict]] = {}
        self.ssl_files = ssl_files
        self.servizi: list[tuple] = []          # (servizio, entity_id, valore)
        self.richieste: list[str] = []          # tipi dei messaggi ricevuti
        self.testi: list[tuple[str, str]] = []  # (tipo, testo) di debug e process
        self._conns: list[dict] = []
        self._lock = threading.Lock()
        self.server = None
        self.port = None

    # ── avvio ──
    def avvia(self, port: int = 0) -> "FakeHA":
        """`port` fissa la porta: per riaccendere HA dove era (prova del ricollegamento)."""
        from websockets.sync.server import serve
        ctx = None
        if self.ssl_files:
            import ssl
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(str(self.ssl_files[0]), str(self.ssl_files[1]))
            # Il server di websockets legge da un thread suo e scrive da altri: come per i
            # satelliti serve il socket TLS di calliope/tls_sicuro.py (03/10)
            from calliope.tls_sicuro import sicuro
            sicuro(ctx)
        _intents()                              # carica le frasi prima del primo client
        self.server = serve(self._handler, "127.0.0.1", port, ssl=ctx, compression=None,
                            max_size=None)
        self.port = self.server.socket.getsockname()[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    @property
    def url(self) -> str:
        return f"{'https' if self.ssl_files else 'http'}://127.0.0.1:{self.port}"

    def ferma(self):
        if self.server is not None:
            self.server.shutdown()
            for c in list(self._conns):
                try:
                    c["ws"].close()
                except Exception:  # noqa: BLE001
                    pass

    # ── protocollo ──
    def _send(self, conn, obj):
        with conn["lock"]:
            conn["ws"].send(json.dumps(obj))

    def _handler(self, ws):
        conn = {"ws": ws, "subs": {}, "lock": threading.Lock()}
        ws.send(json.dumps({"type": "auth_required", "ha_version": VERSIONE}))
        try:
            msg = json.loads(ws.recv(timeout=10))
        except Exception:  # noqa: BLE001
            return
        if msg.get("type") != "auth" or msg.get("access_token") != self.token:
            ws.send(json.dumps({"type": "auth_invalid",
                                "message": "Invalid access token or password"}))
            ws.close()
            return
        ws.send(json.dumps({"type": "auth_ok", "ha_version": VERSIONE}))
        with self._lock:
            self._conns.append(conn)
        try:
            for raw in ws:
                m = json.loads(raw)
                self.richieste.append(m.get("type"))
                # Il ritardo vale per il riconoscimento delle frasi: è la parte lenta su un Pi
                if self.ritardo_s and m.get("type") in ("conversation/agent/homeassistant/debug",
                                                        "conversation/process"):
                    time.sleep(self.ritardo_s)
                self._comando(conn, m)
        except Exception:  # noqa: BLE001
            pass
        finally:
            with self._lock:
                if conn in self._conns:
                    self._conns.remove(conn)

    def _ok(self, conn, mid, result):
        self._send(conn, {"id": mid, "type": "result", "success": True, "result": result})

    def _err(self, conn, mid, code, message=""):
        self._send(conn, {"id": mid, "type": "result", "success": False,
                          "error": {"code": code, "message": message}})

    def _comando(self, conn, m):
        mid, t = m.get("id"), m.get("type")
        if t == "get_config":
            return self._ok(conn, mid, {"version": VERSIONE, "language": "it"})
        if t == "homeassistant/expose_entity/list":
            if not self.admin:
                return self._err(conn, mid, "unauthorized", "Unauthorized")
            exposed = {e["id"]: {"conversation": True} for e in self.entita.values()
                       if e["esposta"]}
            exposed["switch.server"] = {"cloud.alexa": True}       # esposta ad altri, non ad Assist
            return self._ok(conn, mid, {"exposed_entities": exposed})
        if t == "config/entity_registry/get_entries":
            out = {}
            for eid in m.get("entity_ids", []):
                e = self.entita.get(eid)
                out[eid] = None if e is None else {
                    "entity_id": eid, "name": None, "original_name": e["nome"],
                    "aliases": e["alias"], "area_id": e["area"], "device_id": e["device"],
                    "device_class": None, "original_device_class": e["classe"]}
            return self._ok(conn, mid, out)
        if t == "config/device_registry/list":
            return self._ok(conn, mid, DISPOSITIVI)
        if t == "config/area_registry/list":
            return self._ok(conn, mid, [{"area_id": k, **v} for k, v in AREE.items()])
        if t == "config/floor_registry/list":
            return self._ok(conn, mid, [{"floor_id": k, **v} for k, v in PIANI.items()])
        if t == "subscribe_entities":
            ids = set(m.get("entity_ids") or self.entita)
            conn["subs"][mid] = ids
            self._ok(conn, mid, None)
            return self._send(conn, {"id": mid, "type": "event", "event": {"a": {
                eid: self._compresso(self.entita[eid]) for eid in ids if eid in self.entita}}})
        if t == "unsubscribe_events":
            conn["subs"].pop(m.get("subscription"), None)
            return self._ok(conn, mid, None)
        if t == "conversation/agent/list":
            agents = ([{"id": "conversation.home_assistant", "name": "Home Assistant",
                        "supported_languages": ["it", "en"]}] if self.agente else [])
            return self._ok(conn, mid, {"agents": agents})
        if t == "conversation/agent/homeassistant/debug":
            if not self.admin:
                return self._err(conn, mid, "unauthorized", "Unauthorized")
            results = []
            for s in m.get("sentences", []):
                self.testi.append(("debug", s))
                results.append(self._debug(s))
            return self._ok(conn, mid, {"results": results})
        if t == "conversation/process":
            self.testi.append(("process", m.get("text", "")))
            return self._ok(conn, mid, self._process(m.get("text", "")))
        return self._err(conn, mid, "unknown_command", f"Unknown command: {t}")

    @staticmethod
    def _compresso(e):
        attrs = {"friendly_name": e["nome"], **e["attr"]}
        if e["classe"]:
            attrs["device_class"] = e["classe"]
        return {"s": e["stato"], "a": attrs, "lc": time.time()}

    def _cambia(self, e, stato=None, **attr):
        if stato is not None:
            e["stato"] = stato
        e["attr"].update(attr)
        diff = {"+": {"s": e["stato"], "a": dict(attr)}}
        with self._lock:
            conns = list(self._conns)
        for c in conns:
            for sid, ids in list(c["subs"].items()):
                if e["id"] in ids:
                    try:
                        self._send(c, {"id": sid, "type": "event",
                                       "event": {"c": {e["id"]: diff}}})
                    except Exception:  # noqa: BLE001
                        pass

    def imposta(self, eid, stato=None, **attr):
        """Cambia uno stato dall'esterno (come un interruttore premuto a mano)."""
        self._cambia(self.entita[eid], stato, **attr)

    # ── riconoscimento (hassil, frasi vere di HA) ──
    def _slot_lists(self, solo_esposte=True):
        from hassil import TextSlotList
        names = []
        for e in self.entita.values():
            if solo_esposte and not e["esposta"]:
                continue
            for n in [e["nome"], *e["alias"]]:
                names.append((n, n, {"domain": e["id"].split(".")[0]}))
        areas = [(n, k) for k, v in AREE.items() for n in [v["name"], *v["aliases"]]]
        floors = [(n, k) for k, v in PIANI.items() for n in [v["name"], *v["aliases"]]]
        return {"name": TextSlotList.from_tuples(names),
                "area": TextSlotList.from_tuples(areas),
                "floor": TextSlotList.from_tuples(floors)}

    def _riconosci(self, text):
        from hassil import recognize_best
        intents, _ = _intents()
        text = text.strip().rstrip(".!")
        r = recognize_best(text, intents, slot_lists=self._slot_lists(True), language="it")
        if r is not None:
            return r, True
        r = recognize_best(text, intents, slot_lists=self._slot_lists(False), language="it")
        return r, False

    def _bersagli(self, r, solo_esposte=True):
        ents = [e for e in self.entita.values() if e["esposta"] or not solo_esposte]
        s = {k: v.value for k, v in r.entities.items()}
        if not {"name", "area", "floor", "domain", "device_class"} & set(s) \
                and r.intent.name != "HassClimateGetTemperature":
            return []                           # ora, data, timer: nessun dispositivo
        if "name" in s:
            n = str(s["name"]).lower()
            ents = [e for e in ents if n in [x.lower() for x in [e["nome"], *e["alias"]]]]
        if "area" in s:
            ents = [e for e in ents if self._area(e) == s["area"]]
        if "floor" in s:
            ents = [e for e in ents if (AREE.get(self._area(e)) or {}).get("floor_id")
                    == s["floor"]]
        if "domain" in s:
            doms = s["domain"] if isinstance(s["domain"], list) else [s["domain"]]
            ents = [e for e in ents if e["id"].split(".")[0] in doms]
        if "device_class" in s:
            dcs = s["device_class"] if isinstance(s["device_class"], list) else [s["device_class"]]
            ents = [e for e in ents if e["classe"] in dcs]
        if r.intent.name == "HassClimateGetTemperature" and "name" not in s:
            ents = [e for e in ents if e["id"].startswith("climate.")]
        return ents

    def _area(self, e):
        if e["area"]:
            return e["area"]
        return next((d["area_id"] for d in DISPOSITIVI if d["id"] == e["device"]), None)

    def _debug(self, text):
        if text.strip().lower().rstrip(".!") in self.frasi_proprie:
            return {"match": True, "source": "trigger", "sentence_template": text}
        r, esposte = self._riconosci(text)
        if r is None:
            return None
        targets = self._bersagli(r, solo_esposte=esposte)
        return {"intent": {"name": r.intent.name},
                "slots": {k: (v.text or v.value) for k, v in r.entities.items()},
                "details": {k: {"name": k, "value": v.value, "text": v.text}
                            for k, v in r.entities.items()},
                "targets": {e["id"]: {"matched": True} for e in targets},
                "match": True, "sentence_template": "", "unmatched_slots": {},
                "source": "builtin"}

    # ── esecuzione ──
    def _risposta(self, kind, speech, data):
        return {"response": {"response_type": kind, "language": "it", "data": data,
                             "speech": {"plain": {"speech": speech, "extra_data": None}}},
                "conversation_id": "finto", "continue_conversation": False}

    def _errore(self, code, speech):
        return self._risposta("error", speech, {"code": code})

    def _process(self, text):
        forced = self.errori_forzati.get(text.strip().lower().rstrip(".!"))
        if forced:
            code, key, values = forced
            return self._errore(code, errore_ha(key, **values))
        if text.strip().lower().rstrip(".!") in self.frasi_proprie:
            return self._risposta("action_done", "Fatto", {"targets": [], "success": [],
                                                         "failed": []})
        r, esposte = self._riconosci(text)
        if r is None:
            return self._errore("no_intent_match", "Mi dispiace, non ho capito")
        slots = {k: (v.text or str(v.value)) for k, v in r.entities.items()}
        if not esposte:
            return self._errore("no_valid_targets",
                                errore_ha("no_entity_exposed", entity=slots.get("name", "")))
        ents = self._bersagli(r)
        name = r.intent.name
        if not ents and name not in ("HassGetState",):
            return self._errore("no_valid_targets", "Mi dispiace, nessun dispositivo "
                                "corrisponde alla tua richiesta")
        _, responses = _intents()
        template = ((responses.get("intents") or {}).get(name) or {}).get(r.response or "default", "")
        done = []
        if name in ("HassTurnOn", "HassTurnOff"):
            on = name == "HassTurnOn"
            for e in ents:
                d = e["id"].split(".")[0]
                if e["stato"] == "unavailable":
                    continue                    # irraggiungibile: il servizio non la cambia
                if d == "cover":
                    self._cambia(e, "open" if on else "closed",
                                 current_position=100 if on else 0)
                    self.servizi.append(("cover.open_cover" if on else "cover.close_cover", e["id"], None))
                elif d == "lock":
                    self._cambia(e, "locked" if on else "unlocked")
                    self.servizi.append(("lock.lock" if on else "lock.unlock", e["id"], None))
                elif d in ("scene", "script"):
                    self.servizi.append((f"{d}.turn_on", e["id"], None))
                else:
                    self._cambia(e, "on" if on else "off")
                    self.servizi.append((f"{d}.turn_{'on' if on else 'off'}", e["id"], None))
                done.append(e)
        elif name == "HassLightSet":
            b = r.entities.get("brightness")
            for e in ents:
                if b is not None:
                    self._cambia(e, "on", brightness=round(float(b.value) * 255 / 100))
                    self.servizi.append(("light.turn_on", e["id"], b.value))
                done.append(e)
        elif name == "HassSetPosition":
            p = int(float(r.entities["position"].value))
            for e in ents:
                self._cambia(e, "open" if p > 0 else "closed", current_position=p)
                self.servizi.append(("cover.set_cover_position", e["id"], p))
                done.append(e)
        elif name == "HassClimateSetTemperature":
            t = float(r.entities["temperature"].value)
            for e in ents:
                self._cambia(e, None, temperature=t)
                self.servizi.append(("climate.set_temperature", e["id"], t))
                done.append(e)
        elif name == "HassClimateGetTemperature":
            e = ents[0]
            t = e["attr"].get("current_temperature", e["stato"])
            return self._risposta("query_answer", f"{t:g} gradi" if isinstance(t, float)
                                  else f"{t} gradi", {"success": [], "failed": []})
        elif name == "HassGetState":
            want = r.entities.get("state")
            matched = [e for e in ents if want is None or e["stato"] == want.value]
            names = sorted(e["nome"] for e in matched)
            kind = r.response or "one"
            if kind == "one":
                speech = f"{slots.get('name', '').capitalize()} è {ents[0]['stato']}" if ents else "Nessuno"
            elif kind in ("one_yesno", "any", "all"):
                speech = ("Sì" + (", " + " e ".join(names) if kind == "any" else "")) if matched else "No"
            elif kind == "which":
                speech = " e ".join(names) if names else "Nessuno"
            else:
                speech = str(len(matched))
            return self._risposta("query_answer", speech,
                                  {"success": [{"name": e["nome"], "type": "entity", "id": e["id"]}
                                               for e in matched], "failed": []})
        else:
            return self._errore("failed_to_handle", "Si è verificato un errore inatteso "
                                "durante l'elaborazione")
        speech = template
        for k, v in slots.items():
            speech = speech.replace("{{ slots." + k + " }}", v).replace("{{slots." + k + "}}", v)
        if "{" in speech:
            speech = "Fatto"
        return self._risposta("action_done", speech, {
            "targets": [], "failed": [],
            "success": [{"name": e["nome"], "type": "entity", "id": e["id"]} for e in done]})


def porta_chiusa() -> int:
    """Una porta TCP dove non ascolta nessuno (HA spento)."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Muto:
    """Accetta la connessione TCP e non risponde mai (HA bloccato o rete che perde i
    pacchetti): il collegamento deve scadere entro il tempo massimo."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.held = []
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                c, _ = self.sock.accept()
                self.held.append(c)
            except OSError:
                return

    def ferma(self):
        self.sock.close()
        for c in self.held:
            c.close()


def cartella_temporanea() -> Path:
    return Path(tempfile.mkdtemp(prefix="calliope_ha_"))
