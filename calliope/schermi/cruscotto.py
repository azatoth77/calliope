"""
Il cruscotto di chi amministra (06/10/2026, fase 1 del pannello di amministrazione: solo
lettura). Una scheda sugli schermi personali di chi amministra (mai su quelli di stanza, mai
ad altri; anche sul telefono, nel carosello) con:

- versione in uso, capacità con motivo e prossimo passo (come `calliope stato`);
- latenza per giorno (mediana, p90, base, cause, avviso: come `calliope stato --turni`), i
  giudizi mancati del guardiano e l'attesa delle schede trattenute (`schede_attesa_ms`);
- satelliti e schermi abbinati: stanza, di chi, collegato o no, ultimo collegamento, gli
  inattivi da `schermi_inattivi_giorni` (doppioni da togliere a mano);
- regole scattate negli ultimi giorni (per regola e per profilo o modello), errori del ciclo
  (solo il tipo dell'eccezione: mai testi);
- richieste in attesa: avvisi ai tutori non ancora detti, estensioni da approvare, lavori che
  aspettano una risposta.

Nessuna azione: revoche e approvazioni restano a voce o da terminale, qui solo il comando da
dire o da lanciare, come testo. Nessun dato personale di altri: niente testi delle
conversazioni, ricordi, documenti, titoli dei lavori; solo conteggi e stati (le regole del
registro dei turni restano: degli ospiti il registro non ha testi). Nessun tool nuovo,
niente nel prompt: il prefisso del modello non cambia.

I dati si calcolano fuori dal thread della voce (il server li chiede con `asyncio.to_thread`)
e restano in una cache per `CACHE_S`; i file del registro dei turni si rileggono solo se sono
cambiati (dimensione e data), quindi di solito solo quello di oggi. Solo libreria standard.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path

from .. import latenza

CACHE_S = 25.0            # la pagina aggiorna ogni ~30 s: una richiesta, un calcolo
FORZA_MIN_S = 5.0         # «Aggiorna» non ricalcola più spesso di così
GIORNI = 7                # latenza, regole ed errori: gli ultimi giorni del registro
ERRORI_MAX = 10           # gli errori recenti mostrati

_RADICE = Path(__file__).resolve().parents[2]


# ─────────────────────────── versione ───────────────────────────

def versione_in_uso(radice: Path | None = None) -> dict:
    """La versione del codice che gira: VERSIONE.json del gestore di Linux (una cartella per
    versione), altrimenti il repository (portatile). Mai percorsi."""
    radice = Path(radice or _RADICE)
    f = radice / "VERSIONE.json"
    if f.is_file():
        try:
            info = json.loads(f.read_text(encoding="utf-8"))
            return {"origine": "installata",
                    "descrizione": str(info.get("descrizione") or info.get("id") or "")[:60],
                    "commit": str(info.get("commit") or "")[:12],
                    "installata": str(info.get("installata") or "")[:25]}
        except (OSError, ValueError, AttributeError):
            pass
    out = {"origine": "repository", "descrizione": "", "commit": "", "installata": ""}
    try:
        r = subprocess.run(["git", "-C", str(radice), "log", "-1", "--format=%h|%cI"],
                           capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and "|" in r.stdout:
            h, quando = r.stdout.strip().split("|", 1)
            out.update(commit=h[:12], installata=quando[:25])
        r = subprocess.run(["git", "-C", str(radice), "describe", "--always", "--dirty",
                            "--tags"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            out["descrizione"] = r.stdout.strip()[:60]
    except (OSError, subprocess.SubprocessError):
        pass
    return out


# ─────────────────────────── registro dei turni ───────────────────────────

# Un nome di classe d'eccezione («ConnectionError», «httpx.ReadTimeout», «StopIteration»),
# in testa e seguito da «:» o da niente. Una parola qualunque in testa («Dario: …») no
_TIPO = re.compile(r"^((?:[a-z_][a-z0-9_]*\.){0,3}[A-Z][A-Za-z0-9]*(?:Error|Exception|Timeout|"
                   r"Exit|Interrupt|Warning|Failure|Iteration))(?::|$)")


def tipo_errore(testo) -> str:
    """Solo il tipo dell'eccezione, mai il messaggio (può contenere pezzi di ciò che è stato
    detto); se non c'è un tipo riconoscibile, «errore»."""
    m = _TIPO.match(str(testo or "").strip())
    return m.group(1) if m else "errore"


def riassunto_file(turni: list[dict]) -> dict:
    """Ciò che serve al cruscotto da un file del registro (un giorno): latenza per giorno,
    regole per nome e per profilo o modello, errori (tipo e ora)."""
    regole: Counter = Counter()
    per_profilo: dict[str, Counter] = {}
    turni_profilo: Counter = Counter()
    errori = []
    for t in turni:
        chi = str(t.get("profilo") or t.get("modello") or "—")[:40]
        turni_profilo[chi] += 1
        for r in t.get("regole") or ():
            if isinstance(r, str):
                regole[r] += 1
                per_profilo.setdefault(chi, Counter())[r] += 1
        if t.get("errore"):
            errori.append({"quando": str(t.get("inizio") or "")[:19],
                           "tipo": tipo_errore(t["errore"]),
                           "esito": str(t.get("esito") or "")[:30] or None})
    return {"giorni": latenza.per_giorno(turni), "regole": dict(regole),
            "per_profilo": {k: dict(v) for k, v in per_profilo.items()},
            "turni_profilo": dict(turni_profilo), "errori": errori}


class LettoreTurni:
    """I file del registro con una cache per file (dimensione e data di modifica): un file di
    un giorno passato non si rilegge più, quello di oggi solo quando cresce."""

    def __init__(self):
        self._cache: dict[str, tuple[tuple, dict]] = {}
        self._lock = threading.Lock()

    def riassunti(self, cartella, giorni: int = GIORNI) -> list[dict]:
        if not cartella or not Path(cartella).is_dir():
            return []
        files = sorted(Path(cartella).glob("turni-*.jsonl"))[-giorni:]
        out = []
        with self._lock:
            visti = set()
            for f in files:
                try:
                    st = f.stat()
                except OSError:
                    continue
                firma = (st.st_size, st.st_mtime_ns)
                k = str(f)
                visti.add(k)
                c = self._cache.get(k)
                if c is None or c[0] != firma:
                    turni = latenza.leggi_file(f)
                    c = (firma, riassunto_file(turni))
                    self._cache[k] = c
                out.append(c[1])
            for k in [k for k in self._cache if k not in visti]:
                del self._cache[k]
        return out


def unisci(riassunti: list[dict]) -> dict:
    giorni: dict = {}
    regole: Counter = Counter()
    per_profilo: dict[str, Counter] = {}
    turni_profilo: Counter = Counter()
    errori = []
    for r in riassunti:
        giorni.update(r["giorni"])
        regole.update(r["regole"])
        turni_profilo.update(r["turni_profilo"])
        for k, v in r["per_profilo"].items():
            per_profilo.setdefault(k, Counter()).update(v)
        errori.extend(r["errori"])
    errori.sort(key=lambda e: e["quando"])
    return {"giorni": dict(sorted(giorni.items())), "regole": regole,
            "per_profilo": per_profilo, "turni_profilo": turni_profilo, "errori": errori}


# ─────────────────────────── abbinamenti ───────────────────────────

def _tabella_ro(db_path, tabella: str) -> list[dict]:
    """Le righe di una tabella degli abbinamenti, in sola lettura (senza il server dei
    satelliti: nessuna tabella creata). Mai il token."""
    if not db_path or not Path(db_path).is_file():
        return []
    try:
        uri = Path(db_path).resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=1) as db:
            cur = db.execute(f"SELECT * FROM {tabella} ORDER BY id")
            nomi = [d[0] for d in cur.description]
            return [{k: v for k, v in zip(nomi, row) if "token" not in k and "ripresa" not in k}
                    for row in cur.fetchall()]
    except sqlite3.Error:
        return []


def _riga_abbinamento(s: dict, collegati: set, limite: float, attivo=None) -> dict:
    visto = s.get("visto")
    return {"nome": s.get("nome"), "stanza": s.get("stanza"),
            "personale_di": s.get("proprietario_nome") or None,
            "ruolo": s.get("ruolo") or None,
            "collegato": s.get("id") in collegati,
            **({"attivo": True} if attivo is not None and s.get("id") == attivo else {}),
            "visto": visto, "creato": s.get("creato"),
            "inattivo": bool(limite) and (visto or s.get("creato") or 0) < limite
                        and s.get("id") not in collegati}


# ─────────────────────────── il cruscotto ───────────────────────────

class Cruscotto:
    """I dati del cruscotto, calcolati a richiesta con una cache. `servizi` è l'oggetto dei
    servizi di main.py (registry, satelliti, lavori: letti al momento, possono arrivare
    dopo); nelle prove basta un oggetto con quegli attributi."""

    def __init__(self, cfg, hub, servizi=None, registro_capacita=None):
        self.cfg = cfg
        self.hub = hub
        self.servizi = servizi
        self._capacita = registro_capacita
        self._lettore = LettoreTurni()
        self._lock = threading.Lock()
        self._dati: dict | None = None
        self._quando = 0.0
        self.calcoli = 0
        self.ultimo_ms = 0.0

    # ── chi può vederlo ──
    def _registry(self):
        return getattr(self.servizi, "registry", None)

    def amministra(self, schermo: dict | None) -> bool:
        """Lo schermo è personale e il suo proprietario amministra Calliope (letto adesso:
        un amministratore tolto non vede più niente alla richiesta dopo)."""
        if not schermo or not schermo.get("proprietario"):
            return False
        reg = self._registry()
        if reg is None or getattr(reg, "illeggibile", False):
            return False
        try:
            prof = reg.by_id(schermo["proprietario"])
        except Exception:  # noqa: BLE001
            return False
        return bool(prof is not None and getattr(prof, "admin", False))

    # ── dati ──
    def dati(self, forza: bool = False) -> dict:
        """I dati (dalla cache se recenti). Da chiamare fuori dal thread della voce."""
        with self._lock:
            eta = time.monotonic() - self._quando
            if self._dati is not None and (eta < CACHE_S and not (forza and eta >= FORZA_MIN_S)):
                return self._dati
            t0 = time.perf_counter()
            self._dati = self._calcola()
            self.ultimo_ms = round((time.perf_counter() - t0) * 1000, 1)
            self._dati["calcolo_ms"] = self.ultimo_ms
            self._quando = time.monotonic()
            self.calcoli += 1
            return self._dati

    def _parte(self, fn, *a):
        """Una sezione che non va non rompe le altre: lo dice al suo posto."""
        try:
            return fn(*a)
        except Exception as e:  # noqa: BLE001
            return {"errore": f"non letto ({type(e).__name__})"}

    def _calcola(self) -> dict:
        turni = self._parte(lambda: unisci(self._lettore.riassunti(
            getattr(self.cfg, "turn_log_dir", None), GIORNI)))
        return {"ora": time.time(),
                "versione": self._parte(versione_in_uso),
                "capacita": self._parte(self._capacita_attuali),
                "latenza": self._parte(self._latenza, turni),
                "abbinamenti": self._parte(self._abbinamenti),
                "regole": self._parte(self._regole, turni),
                "errori": self._parte(self._errori, turni),
                "attesa": self._parte(self._attesa)}

    def _capacita_attuali(self) -> dict:
        from .. import capacita
        reg = self._capacita or capacita.REGISTRO
        caps = reg.tutte(fresche=True)
        voci = [{"nome": c.nome, "breve": c.definizione.breve, "stato": c.stato,
                 "motivo": c.motivo, "prossimo_passo": c.prossimo_passo} for c in caps]
        return {"attive": sum(c.attiva for c in caps), "totale": len(caps), "voci": voci,
                "comando": "calliope stato --dettagli"}

    def _latenza(self, turni: dict) -> dict:
        if "errore" in turni:
            return turni
        soglia = float(getattr(self.cfg, "latenza_avviso_s", 1.2) or 0)
        giorni = []
        for data, d in turni["giorni"].items():
            g = d["guardiano"]
            giorni.append({
                "data": data, "risposte": d["risposte"],
                "prima_frase": d["prima_frase"], "fine_parlato": d["fine_parlato"],
                "prima_voce": d.get("prima_voce"),
                "stt": d["stt"], "base": d["base"],
                "guardiano": {"n": g["n"], "prima_frase": g["prima_frase"],
                              "guasti": g.get("guasti", 0)},
                "correzione": d["correzione"], "tool": d["tool"], "lettura": d["lettura"],
                "contesto": d["contesto"], "coda": d["coda"],
                "schede_attesa": d.get("schede_attesa"),
                "avviso": latenza.avviso(d, soglia) if soglia > 0 else None,
                "avviso_guasti": latenza.avviso_guasti(d)})
        return {"soglia_s": soglia, "giorni": giorni[::-1],
                "comando": "calliope stato --turni"}

    def _regole(self, turni: dict) -> dict:
        if "errore" in turni:
            return turni
        return {"giorni": GIORNI,
                "totali": [{"regola": r, "n": n} for r, n in turni["regole"].most_common()],
                "per_profilo": [{"profilo": k, "turni": turni["turni_profilo"].get(k, 0),
                                 "regole": [{"regola": r, "n": n} for r, n in v.most_common()]}
                                for k, v in sorted(turni["per_profilo"].items())]}

    def _errori(self, turni: dict) -> dict:
        if "errore" in turni:
            return turni
        e = turni["errori"]
        return {"giorni": GIORNI, "n": len(e),
                "per_tipo": [{"tipo": t, "n": n}
                             for t, n in Counter(x["tipo"] for x in e).most_common()],
                "recenti": e[-ERRORI_MAX:][::-1], "comando": "calliope log"}

    def _abbinamenti(self) -> dict:
        giorni = float(getattr(self.cfg, "schermi_inattivi_giorni", 7.0) or 0)
        limite = time.time() - giorni * 86400 if giorni > 0 else 0
        hub = self.hub
        coll = {s["id"] for s in hub.collegati()}
        schermi = [_riga_abbinamento(s, coll, limite) for s in hub.abbinati()]
        srv = getattr(self.servizi, "satelliti", None) or getattr(hub, "satelliti", None)
        if srv is not None and getattr(srv, "archivio", None) is not None:
            righe = srv.archivio.elenco()
            collegati = {c.satellite.get("id") for c in list(getattr(srv, "collegati", ()))
                         if not c.chiuso.is_set()}
            att = getattr(srv, "_attivo", None)
            attivo = att.satellite.get("id") if att is not None else None
            server = True
        else:
            righe = _tabella_ro(getattr(self.cfg, "memory_db", None) or "memoria.db",
                                "satelliti")
            collegati, attivo, server = set(), None, False
        satelliti = [_riga_abbinamento(s, collegati, limite, attivo) for s in righe]
        return {"inattivi_giorni": giorni, "schermi": schermi, "satelliti": satelliti,
                "server_satelliti": server,
                "comandi": {"schermi": "calliope schermi --revoca <stanza>",
                            "satelliti": "calliope satellite --revoca <nome>"}}

    def _attesa(self) -> dict:
        out = {}
        # Avvisi ai tutori non ancora detti (minori.Avvisi): solo quanti
        db = getattr(self.cfg, "memory_db", None) or "memoria.db"
        tutori = {"n": 0, "urgenti": 0}
        if Path(db).is_file():
            try:
                uri = Path(db).resolve().as_uri() + "?mode=ro"
                with sqlite3.connect(uri, uri=True, timeout=1) as c:
                    row = c.execute("SELECT COUNT(*), COALESCE(SUM(urgente), 0) FROM "
                                    "avvisi_tutori WHERE detto IS NULL").fetchone()
                tutori = {"n": int(row[0]), "urgenti": int(row[1])}
            except sqlite3.Error:
                pass                       # tabella assente: nessun minore registrato
        out["tutori"] = {**tutori, "nota": "si dicono al tutore alla sua prossima frase "
                                           "riconosciuta"}
        # Estensioni da approvare (indice.json delle estensioni, in sola lettura)
        da_approvare = []
        try:
            from ..persistenza import leggi_json
            cart = Path(getattr(self.cfg, "estensioni_cartella", None) or "estensioni")
            if not cart.is_absolute() and getattr(self.cfg, "config_dir", None):
                cart = Path(self.cfg.config_dir) / cart
            indice, _ = leggi_json(cart / "indice.json")
            for nome, v in sorted((indice or {}).items()):
                if not isinstance(v, dict):
                    continue
                for n, ver in (v.get("versioni") or {}).items():
                    if isinstance(ver, dict) and ver.get("stato") == "da_approvare":
                        da_approvare.append({"nome": str(nome)[:40], "versione": int(n),
                                             "test_passano": bool(ver.get("test_passano"))})
        except Exception:  # noqa: BLE001 — senza estensioni: nessuna
            pass
        out["estensioni"] = {"da_approvare": da_approvare,
                             "comando": "a voce: «approva l'estensione <nome>» (con la frase "
                                        "di sfida)"}
        # Lavori che aspettano una risposta (Lavori.in_attesa): quanti, non i titoli
        lav = getattr(self.servizi, "lavori", None)
        if lav is not None:
            try:
                attesa = lav.in_attesa()
                out["lavori"] = {"in_attesa": len(attesa),
                                 "attivi": len(lav.attivi()),
                                 "comando": "a voce: «lavori in sospeso» o «per il lavoro …: "
                                            "<risposta>»"}
            except Exception as e:  # noqa: BLE001
                out["lavori"] = {"errore": f"non letto ({type(e).__name__})"}
        else:
            out["lavori"] = None
        return out
