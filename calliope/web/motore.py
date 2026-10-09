"""
SearXNG tenuto aggiornato (09/10/2026, decisione di Dario): i motori a cui SearXNG si appoggia
(DuckDuckGo, Brave, Bing, Google News…) cambiano spesso le loro pagine, e un'immagine di
SearXNG vecchia di qualche settimana smette di trovare. Qui il controllo e l'aggiornamento del
container `calliope-searxng` (setup/linux/motore/searxng.sh).

Controllo (sempre, in tutti e due i modi): poche ricerche di prova fisse (`web_searxng_prove`,
una generale, una di notizie, una a tema; nessun dato di nessuno) contro il SearXNG locale, in
POST come le ricerche vere; per ciascuna risultati, motori che hanno dato risultati, motori che
non hanno risposto (con il motivo di SearXNG: CAPTCHA, timeout, accesso negato…), errori e
tempo. Il giudizio (`giudica`):
- «giù»: nessuna prova ha avuto risposta (la capacità è «guasta», come per una ricerca vera);
- «degradata»: una prova con meno di `web_searxng_min_risultati` risultati, oppure risultati o
  motori sotto `web_searxng_soglia` dell'ultimo controllo buono;
- «buona» altrimenti (diventa il nuovo «ultimo buono»).
Il controllo automatico parte una volta ogni `web_searxng_controllo_ore`, solo con Calliope
ferma da `web_searxng_inattivita_min` (nessun turno su nessuna corsia) e nessun lavoro
dell'agente in coda o in corso; il manuale (cruscotto, terminale) subito.

Aggiornamento (`web_searxng_aggiorna`: «automatico» dopo il controllo, «manuale» solo a
richiesta):
1. il tag da provare, dal registro delle immagini (Docker Hub): solo tag di data
   «AAAA.M.G-hash» con il digest dell'indice multi-architettura (arm64 e amd64), mai
   `latest`; in automatico il più recente pubblicato da almeno `web_searxng_giorni` giorni, o
   il più recente in assoluto se la ricerca è degradata; un tag già scartato non si riprova
   da solo (a mano sì);
2. le prove sull'immagine in uso, adesso (stessa rete, stessi motori);
3. la nuova scaricata e avviata **accanto** a quella in uso (`searxng.sh candidata`, porta di
   prova): le stesse prove; poi la copia di prova si toglie. Se va peggio la vecchia resta e
   non si è fermato niente;
4. se va almeno come la vecchia (`almeno_come`): `searxng.sh usa` rifà il container vero con
   la nuova (pochi secondi senza ricerca), le prove di nuovo; se non risponde o va peggio,
   `usa` con la vecchia: si torna indietro. Le immagini scaricate da qui e non più usate si
   tolgono (mai quelle di altri progetti);
5. ogni decisione nella storia (`web_searxng_stato`, ultime STORIA_MAX) e nel log; l'esito di
   un aggiornamento automatico (e il passaggio a «degradata») sugli schermi personali di chi
   amministra.
Mai durante l'uso né con lavori in corso (l'automatico ricontrolla prima del cambio); mai due
operazioni insieme, nemmeno tra Calliope e il terminale (un file di blocco).

Su Windows, o dove il container non c'è (SearXNG su un'altra macchina, niente docker), il
controllo resta se SearXNG è raggiungibile e l'aggiornamento si spegne con il suo perché.

Da terminale, sulla DGX (gestore.py lo lancia nella cartella dei dati):
    calliope motore searxng controlla | aggiorna | novita | storia
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

REPO = "searxng/searxng"
FORMA_TAG = re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})-([0-9a-f]{6,40})$")
FORMA_IMMAGINE = re.compile(r"^searxng/searxng:(\d{4}\.\d{1,2}\.\d{1,2}-[0-9a-f]{6,40})"
                            r"@(sha256:[0-9a-f]{64})$")
FORMA_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
CATEGORIE = ("general", "news", "science", "it", "images", "videos", "music", "map", "files",
             "social media")
PROVE = ("general:meteo Roma domani", "news:notizie Italia oggi", "news:Serie A risultati")
ARCHITETTURE = {"arm64", "amd64"}
STORIA_MAX = 40
TOLLERANZA_MOTORI = 1          # un motore in meno tra due giri è rumore, non un peggioramento
TOLLERANZA_RISULTATI = 0.8     # e così un quinto di risultati in meno
GIRO_S = 300.0                 # ogni quanto il thread guarda se è ora del controllo
BLOCCO_VECCHIO_S = 3 * 3600.0  # un blocco più vecchio è di un processo caduto

_RADICE = Path(__file__).resolve().parents[2]
SCRIPT = _RADICE / "setup" / "linux" / "motore" / "searxng.sh"

MODI = ("automatico", "manuale")


# ─────────────────────────── prove ───────────────────────────

def prove_da(cfg) -> list[tuple[str, str]]:
    """(categoria, domanda) dalle righe «categoria:domanda» di web_searxng_prove; le righe
    sbagliate si saltano (una categoria che SearXNG non ha darebbe zero risultati sempre)."""
    out = []
    for riga in (getattr(cfg, "web_searxng_prove", None) or PROVE):
        cat, sep, q = str(riga).partition(":")
        cat, q = cat.strip().lower(), re.sub(r"\s+", " ", q).strip()
        if sep and cat in CATEGORIE and 2 <= len(q) <= 100:
            out.append((cat, q))
    return out or [tuple(p.split(":", 1)) for p in PROVE]


def misura(url: str, prove, http, timeout_s: float = 10.0, lingua: str = "it-IT",
           immagine: str = "") -> dict:
    """Le ricerche di prova contro un SearXNG (`url`, senza la barra finale). Mai eccezioni:
    una prova che non va ha `errore`."""
    righe = []
    for cat, q in prove:
        r = {"categoria": cat, "domanda": q, "ok": False, "risultati": 0, "motori": [],
             "giu": [], "ms": 0}
        t0 = time.perf_counter()
        try:
            resp = http.post(url.rstrip("/") + "/search",
                             data={"q": q, "format": "json", "language": lingua,
                                   "categories": cat, "safesearch": "1"},
                             timeout=timeout_s, headers={"Accept": "application/json"})
            if resp.status_code != 200:
                r["errore"] = f"HTTP {resp.status_code}"
            else:
                js = resp.json()
                motori, n = set(), 0
                for x in js.get("results") or []:
                    if not isinstance(x, dict):
                        continue
                    if not str(x.get("url") or "").startswith(("http://", "https://")):
                        continue
                    n += 1
                    for e in (x.get("engines") or [x.get("engine")]):
                        if e:
                            motori.add(str(e)[:40])
                giu = []
                for g in js.get("unresponsive_engines") or []:
                    if isinstance(g, (list, tuple)) and g:
                        giu.append([str(g[0])[:40], str(g[1] if len(g) > 1 else "")[:60]])
                r.update(ok=True, risultati=n, motori=sorted(motori), giu=giu)
        except Exception as e:  # noqa: BLE001 — una prova che non va è un dato
            r["errore"] = type(e).__name__
        r["ms"] = round((time.perf_counter() - t0) * 1000)
        righe.append(r)
    return riassumi(righe, immagine)


def riassumi(righe: list[dict], immagine: str = "") -> dict:
    motori = sorted({m for r in righe for m in r.get("motori") or ()})
    giu: dict[str, str] = {}
    for r in righe:
        for nome, perche in r.get("giu") or ():
            giu.setdefault(nome, perche)
    ms = sorted(r["ms"] for r in righe if r.get("ok"))
    return {"quando": time.time(), "immagine": immagine, "prove": righe,
            "risposte": sum(bool(r.get("ok")) for r in righe),
            "risultati": sum(int(r.get("risultati") or 0) for r in righe),
            "motori": motori, "giu": [[k, v] for k, v in sorted(giu.items())],
            "ms_max": ms[-1] if ms else None}


def _buone(esito: dict, minimo: int) -> int:
    return sum(1 for r in esito.get("prove") or ()
               if r.get("ok") and int(r.get("risultati") or 0) >= minimo)


def giudica(esito: dict, buono: dict | None, minimo: int = 3, soglia: float = 0.6
            ) -> tuple[str, str]:
    """(«buona» | «degradata» | «giù», motivo per chi amministra)."""
    prove = esito.get("prove") or []
    if not prove or not esito.get("risposte"):
        errori = sorted({str(r.get("errore") or "") for r in prove} - {""})
        return "giù", "SearXNG non risponde" + (f" ({', '.join(errori)})" if errori else "")
    for r in prove:
        if not r.get("ok"):
            return "degradata", f"la prova «{r['domanda']}» non ha avuto risposta " \
                                f"({r.get('errore') or 'errore'})"
        if int(r.get("risultati") or 0) < minimo:
            giu = ", ".join(f"{g[0]} ({g[1]})" if g[1] else g[0] for g in r.get("giu") or ())
            return "degradata", (f"la prova «{r['domanda']}» ha dato {r['risultati']} "
                                 f"risultati" + (f"; non rispondono {giu}" if giu else ""))
    if buono and buono.get("prove"):
        nb, n = len(buono.get("motori") or ()), len(esito.get("motori") or ())
        if nb and n < soglia * nb:
            return "degradata", f"rispondono {n} motori contro {nb} dell'ultimo controllo buono"
        rb, r = int(buono.get("risultati") or 0), int(esito.get("risultati") or 0)
        if rb and r < soglia * rb:
            return "degradata", f"{r} risultati in tutto contro {rb} dell'ultimo controllo buono"
    return "buona", ""


def almeno_come(nuovo: dict, vecchio: dict, minimo: int = 3) -> tuple[bool, str]:
    """La nuova immagine va almeno come la vecchia? (con un po' di tolleranza: tra due giri
    di ricerche lo stesso SearXNG non dà mai gli stessi numeri)."""
    if not nuovo.get("risposte"):
        return False, "la nuova non risponde"
    bn, bv = _buone(nuovo, minimo), _buone(vecchio, minimo)
    if bn < bv:
        return False, f"prove riuscite {bn} contro {bv}"
    mn, mv = len(nuovo.get("motori") or ()), len(vecchio.get("motori") or ())
    if mn < mv - TOLLERANZA_MOTORI:
        return False, f"motori che rispondono {mn} contro {mv}"
    rn, rv = int(nuovo.get("risultati") or 0), int(vecchio.get("risultati") or 0)
    if rn < TOLLERANZA_RISULTATI * rv:
        return False, f"risultati {rn} contro {rv}"
    return True, f"prove riuscite {bn} (prima {bv}), motori {mn} (prima {mv}), " \
                 f"risultati {rn} (prima {rv})"


# ─────────────────────────── registro delle immagini ───────────────────────────

def _istante(testo) -> float | None:
    try:
        return datetime.datetime.fromisoformat(str(testo).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def tag_di(immagine: str) -> str:
    m = FORMA_IMMAGINE.match(str(immagine or ""))
    return m.group(1) if m else ""


def data_tag(tag: str) -> tuple:
    m = FORMA_TAG.match(str(tag or ""))
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (0, 0, 0)


def tag_recenti(http, url: str, timeout_s: float = 15.0) -> list[dict]:
    """I tag pubblicati, dal più recente: solo «AAAA.M.G-hash», attivi, con il digest
    dell'indice e le architetture che servono. Solleva se il registro non risponde."""
    r = http.get(url, timeout=timeout_s, headers={"Accept": "application/json"})
    if r.status_code != 200:
        raise RuntimeError(f"il registro delle immagini ha risposto {r.status_code}")
    out = []
    for x in r.json().get("results") or []:
        if not isinstance(x, dict):
            continue
        nome = str(x.get("name") or "")
        dig = str(x.get("digest") or "")
        if not FORMA_TAG.match(nome) or not FORMA_DIGEST.match(dig):
            continue                                  # «latest» e simili: mai
        if x.get("tag_status") not in (None, "active"):
            continue
        archi = {str(i.get("architecture")) for i in x.get("images") or ()
                 if isinstance(i, dict)}
        if x.get("images") is not None and not ARCHITETTURE <= archi:
            continue
        quando = _istante(x.get("tag_last_pushed") or x.get("last_updated"))
        if quando is None:
            d = data_tag(nome)
            quando = datetime.datetime(*d, tzinfo=datetime.timezone.utc).timestamp()
        out.append({"tag": nome, "digest": dig, "immagine": f"{REPO}:{nome}@{dig}",
                    "pubblicata": quando})
    out.sort(key=lambda t: (data_tag(t["tag"]), t["pubblicata"]), reverse=True)
    return out


def piu_recente(a: dict, attuale_tag: str, tags: list[dict]) -> bool:
    """`a` (un tag del registro) è più recente dell'immagine in uso? Per data del tag; a
    pari data per data di pubblicazione, se quella in uso è nel registro."""
    da, dv = data_tag(a["tag"]), data_tag(attuale_tag)
    if da != dv:
        return da > dv
    if a["tag"] == attuale_tag:
        return False
    v = next((t for t in tags if t["tag"] == attuale_tag), None)
    return v is not None and a["pubblicata"] > v["pubblicata"]


# ─────────────────────────── script e ambiente ───────────────────────────

class Script:
    """searxng.sh con bash, con la porta di Calliope. (codice, uscita) e mai eccezioni."""

    def __init__(self, percorso: Path = SCRIPT, porta: int = 8004):
        self.percorso = Path(percorso)
        self.porta = int(porta)

    def __call__(self, *args, timeout: float = 900.0) -> tuple[int, str]:
        env = {k: v for k, v in os.environ.items() if k != "IMMAGINE"}
        env["PORTA"] = str(self.porta)
        try:
            r = subprocess.run(["bash", str(self.percorso), *map(str, args)],
                               capture_output=True, text=True, timeout=timeout, env=env,
                               stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return 124, "tempo scaduto"
        except OSError as e:
            return 127, type(e).__name__
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()[-2000:]


def ambiente(cfg) -> tuple[bool, bool, str]:
    """(si può controllare, si può aggiornare, perché no)."""
    url = str(getattr(cfg, "web_searxng_url", "") or "")
    if not getattr(cfg, "web_enabled", True) or not url:
        return False, False, "SearXNG non configurato"
    if not getattr(cfg, "online", True):
        return False, False, "senza rete (online: false)"
    host = (urlsplit(url).hostname or "").lower()
    if host not in ("127.0.0.1", "::1", "localhost"):
        return True, False, "SearXNG gira su un'altra macchina: si aggiorna da lì"
    if not sys.platform.startswith("linux"):
        return True, False, "l'aggiornamento c'è solo sulla macchina del container (Linux)"
    if not SCRIPT.is_file():
        return True, False, "manca setup/linux/motore/searxng.sh"
    if shutil.which("docker") is None or shutil.which("bash") is None:
        return True, False, "manca docker"
    return True, True, ""


def _porta(url: str) -> int:
    try:
        return urlsplit(url).port or 8004
    except ValueError:
        return 8004


def _vivo(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "posix":
        return True                       # su Windows conta l'età del blocco
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ─────────────────────────── il servizio ───────────────────────────

class Occupato(Exception):
    pass


class MotoreRicerca:
    """Controllo e aggiornamento di SearXNG. Thread-safe; una operazione alla volta.

    `inattivita()` → secondi dall'ultimo turno (None: non si sa, vale «ferma»);
    `lavori()` → quanti lavori dell'agente in coda o in corso; `avvisa(titolo, testo)` → un
    avviso a chi amministra. `http` (httpx.Client o un finto), `script` (Script o un finto) e
    `orologio` si sostituiscono nelle prove."""

    def __init__(self, cfg, *, http=None, script=None, log=print, inattivita=None,
                 lavori=None, avvisa=None, web=None, orologio=time.time,
                 controllabile: bool | None = None, aggiornabile: bool | None = None):
        self.cfg = cfg
        self.url = str(getattr(cfg, "web_searxng_url", "") or "").rstrip("/")
        modo = str(getattr(cfg, "web_searxng_aggiorna", "automatico") or "").strip().lower()
        self.modo = modo if modo in MODI else "manuale"
        c, a, perche = ambiente(cfg)
        self.controllabile = c if controllabile is None else controllabile
        self.aggiornabile = (a if aggiornabile is None else aggiornabile) and self.controllabile
        self.perche = "" if self.aggiornabile else (perche or "aggiornamento spento")
        self.script = script or Script(SCRIPT, _porta(self.url))
        self._http = http
        self.log = log
        self.inattivita = inattivita
        self.lavori = lavori
        self.avvisa = avvisa
        self.web = web
        self.orologio = orologio
        self.file = Path(str(getattr(cfg, "web_searxng_stato", "") or "motore/searxng.json"))
        self.minimo = int(getattr(cfg, "web_searxng_min_risultati", 3) or 1)
        self.soglia = float(getattr(cfg, "web_searxng_soglia", 0.6) or 0.0)
        self._lock = threading.Lock()          # una operazione alla volta (questo processo)
        self._lock_file = threading.Lock()     # lettura e scrittura dello stato
        self._avvio = threading.Lock()         # due pulsanti insieme: ne parte uno
        self._cache: tuple = (None, {})
        self.in_corso: dict | None = None
        self._ferma = threading.Event()
        self._thread: threading.Thread | None = None

    # ── rete ──
    def http(self):
        if self._http is None:
            import httpx
            self._http = httpx.Client(timeout=15.0, trust_env=False)
        return self._http

    # ── stato su disco ──
    def leggi(self) -> dict:
        from ..persistenza import FileRovinato, leggi_json
        with self._lock_file:
            try:
                firma = self.file.stat().st_mtime_ns
            except OSError:
                firma = None
            if firma is not None and firma == self._cache[0]:
                return self._cache[1]
            try:
                dati, _ = leggi_json(self.file)
            except FileRovinato:
                dati = None
            dati = dati if isinstance(dati, dict) else {}
            self._cache = (firma, dati)
            return dati

    def _aggiorna_stato(self, **campi) -> dict:
        from ..persistenza import scrivi_json
        dati = dict(self.leggi())
        evento = campi.pop("evento", None)
        dati.update(campi)
        if evento:
            storia = list(dati.get("storia") or [])
            storia.append({"quando": self.orologio(), **evento})
            dati["storia"] = storia[-STORIA_MAX:]
        with self._lock_file:
            scrivi_json(self.file, dati, copia=True)
            self._cache = (None, {})
        return dati

    def _registra(self, evento: str, frase: str, chi: str, **altro):
        self.log(f"[WEB] SearXNG: {frase}")
        self._aggiorna_stato(evento={"evento": evento, "frase": frase, "chi": chi, **altro})

    # ── blocco tra processi (Calliope e il terminale) ──
    def _blocco(self) -> Path:
        return self.file.with_name(self.file.name + ".blocco")

    def _prendi_blocco(self):
        p = self._blocco()
        p.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                try:
                    pid = int(p.read_text().strip() or 0)
                    eta = time.time() - p.stat().st_mtime
                except (OSError, ValueError):
                    pid, eta = 0, BLOCCO_VECCHIO_S + 1
                if (pid and _vivo(pid) and pid != os.getpid()) and eta < BLOCCO_VECCHIO_S:
                    raise Occupato("un altro controllo di SearXNG è in corso") from None
                try:
                    p.unlink()
                except OSError:
                    pass
                continue
            with os.fdopen(fd, "w") as f:
                f.write(str(os.getpid()))
            return
        raise Occupato("un altro controllo di SearXNG è in corso")

    def _lascia_blocco(self):
        try:
            self._blocco().unlink()
        except OSError:
            pass

    def _operazione(self, azione: str, chi: str):
        """Il contesto di una operazione: un solo controllo o aggiornamento alla volta."""
        motore = self

        class _Op:
            def __enter__(self_op):
                if not motore._lock.acquire(blocking=False):
                    raise Occupato("c'è già un controllo o un aggiornamento in corso")
                try:
                    motore._prendi_blocco()
                except Exception:
                    motore._lock.release()
                    raise
                motore.in_corso = {"azione": azione, "chi": chi, "dal": motore.orologio(),
                                   "fase": "comincio"}
                return self_op

            def __exit__(self_op, *exc):
                motore.in_corso = None
                motore._lascia_blocco()
                motore._lock.release()
                return False
        return _Op()

    def _fase(self, testo: str):
        if self.in_corso is not None:
            self.in_corso["fase"] = testo

    # ── viste ──
    def giudizio(self) -> dict:
        """{"stato": buona | degradata | giù | mai, "motivo", "quando"} dell'ultimo controllo."""
        g = self.leggi().get("giudizio")
        return g if isinstance(g, dict) else {"stato": "mai", "motivo": "", "quando": None}

    def vista(self) -> dict:
        """Per il cruscotto di chi amministra: niente percorsi, niente domande di persone (le
        prove sono frasi fisse della configurazione)."""
        st = self.leggi()
        ultimo = st.get("ultimo") if isinstance(st.get("ultimo"), dict) else None
        storia = [e for e in st.get("storia") or [] if isinstance(e, dict)][-6:][::-1]
        return {"modo": self.modo, "aggiornabile": self.aggiornabile, "perche": self.perche,
                "controllabile": self.controllabile,
                "immagine": tag_di(st.get("immagine") or "") or None,
                "giudizio": self.giudizio(), "ultimo": ultimo,
                "novita": st.get("novita") if isinstance(st.get("novita"), dict) else None,
                "esito": st.get("esito") if isinstance(st.get("esito"), dict) else None,
                "in_corso": dict(self.in_corso) if self.in_corso else None,
                "storia": storia, "giorni": float(getattr(self.cfg, "web_searxng_giorni", 3.0)),
                "comando": "calliope motore searxng controlla | aggiorna"}

    # ── condizioni ──
    def inattiva_s(self) -> float | None:
        if self.inattivita is None:
            return None
        try:
            return float(self.inattivita())
        except Exception:  # noqa: BLE001
            return 0.0                         # non si sa: meglio non disturbare

    def lavori_in_corso(self) -> int:
        if self.lavori is None:
            return 0
        try:
            return int(self.lavori())
        except Exception:  # noqa: BLE001
            return 1

    def libera(self) -> tuple[bool, str]:
        """Calliope è ferma e senza lavori? (per l'automatico)"""
        n = self.lavori_in_corso()
        if n:
            return False, f"{n} lavori dell'agente in corso"
        s = self.inattiva_s()
        minimo = float(getattr(self.cfg, "web_searxng_inattivita_min", 30.0)) * 60
        if s is not None and s < minimo:
            return False, "Calliope è in uso"
        return True, ""

    # ── controllo ──
    def _immagine_in_uso(self) -> str:
        if not self.aggiornabile:
            return ""
        rc, out = self.script("immagine", timeout=30)
        riga = out.strip().splitlines()[-1].strip() if out.strip() else ""
        return riga if rc == 0 and FORMA_IMMAGINE.match(riga) else ""

    def _misura(self, url: str, immagine: str = "") -> dict:
        return misura(url, prove_da(self.cfg), self.http(),
                      timeout_s=max(5.0, float(getattr(self.cfg, "web_timeout_s", 6.0)) + 4),
                      lingua=str(getattr(self.cfg, "web_lingua", "it-IT") or "it-IT"),
                      immagine=immagine)

    def controlla(self, chi: str = "automatico") -> dict:
        """Le prove adesso, il giudizio e lo stato salvato. {"stato", "motivo", "esito"}."""
        if not self.controllabile:
            return {"stato": "spento", "motivo": self.perche, "esito": None}
        with self._operazione("controlla", chi):
            return self._controlla(chi)

    def _controlla(self, chi: str) -> dict:
        self._fase("ricerche di prova")
        immagine = self._immagine_in_uso()
        esito = self._misura(self.url, immagine)
        st = self.leggi()
        buono = st.get("buono") if isinstance(st.get("buono"), dict) else None
        # L'ultimo buono vale per la stessa immagine: dopo un cambio fatto a mano
        # (calliope motore searxng avvia) si riparte dal primo controllo
        if buono and immagine and buono.get("immagine") and buono["immagine"] != immagine:
            buono = None
        stato, motivo = giudica(esito, buono, self.minimo, self.soglia)
        prima = self.giudizio().get("stato")
        campi = {"ultimo": esito, "giudizio": {"stato": stato, "motivo": motivo,
                                                "quando": esito["quando"]}}
        if immagine:
            campi["immagine"] = immagine
        if stato == "buona":
            campi["buono"] = esito
        frase = (f"controllo: {_dici(stato)}" + (f", {motivo}" if motivo else "")
                 + f" ({esito['risultati']} risultati, {len(esito['motori'])} motori)")
        self._aggiorna_stato(**campi, evento={"evento": "controllo", "esito": stato,
                                              "frase": frase, "chi": chi})
        self.log(f"[WEB] SearXNG: {frase}")
        if self.web is not None and stato == "giù":
            self.web.diagnosi = {"codice": "searxng_giu", "quando": time.time()}
        if stato == "degradata" and prima != "degradata" and chi == "automatico":
            self._avvisa("La ricerca su internet va peggio",
                         f"Il controllo di SearXNG dice: {motivo}. "
                         + ("Provo un'immagine più recente quando sono ferma."
                            if self.modo == "automatico" and self.aggiornabile else
                            "Dal cruscotto puoi provare «Aggiorna»."))
        return {"stato": stato, "motivo": motivo, "esito": esito}

    # ── aggiornamento ──
    def novita(self) -> list[dict]:
        """I tag del registro (rete: solo il registro delle immagini). Salvati nello stato."""
        url = str(getattr(self.cfg, "web_searxng_registro", "") or "")
        tags = tag_recenti(self.http(), url)
        if tags:
            t = tags[0]
            self._aggiorna_stato(novita={"tag": t["tag"], "pubblicata": t["pubblicata"],
                                         "quando": self.orologio()})
        return tags

    def scegli(self, tags: list[dict], attuale: str, manuale: bool, degradata: bool
               ) -> dict | None:
        """Il tag da provare, o None."""
        giorni = float(getattr(self.cfg, "web_searxng_giorni", 3.0) or 0.0)
        scartate = self.leggi().get("scartate") or {}
        ora = self.orologio()
        atag = tag_di(attuale)
        for t in tags:
            if not piu_recente(t, atag, tags):
                return None                    # in ordine: da qui in giù sono più vecchi
            if manuale:
                return t
            if t["tag"] in scartate:
                continue
            if degradata or ora - t["pubblicata"] >= giorni * 86400:
                return t
        return None

    def aggiorna(self, chi: str = "automatico", manuale: bool = False) -> dict:
        """{"esito": aggiornata | tenuta | indietro | ultima | niente | rinviato | errore |
        spento, "frase"}."""
        if not self.aggiornabile:
            return {"esito": "spento", "frase": f"Non si aggiorna da qui: {self.perche}."}
        with self._operazione("aggiorna", chi):
            return self._aggiorna(chi, manuale)

    def _fine(self, esito: str, frase: str, chi: str, manuale: bool, **altro) -> dict:
        r = {"esito": esito, "frase": frase, "quando": self.orologio(), "chi": chi, **altro}
        if esito not in ("niente",):
            self._aggiorna_stato(esito=r, evento={"evento": "aggiornamento", "esito": esito,
                                                  "frase": frase, "chi": chi})
            self.log(f"[WEB] SearXNG: {frase}")
        if not manuale and esito in ("aggiornata", "tenuta", "indietro", "errore"):
            self._avvisa("SearXNG", frase)
        return r

    def _aggiorna(self, chi: str, manuale: bool) -> dict:
        if self.lavori_in_corso():
            return self._fine("rinviato", "Non aggiorno SearXNG adesso: ci sono lavori "
                              "dell'agente in corso.", chi, manuale)
        self._fase("cerco l'immagine più recente")
        try:
            tags = self.novita()
        except Exception as e:  # noqa: BLE001
            return self._fine("errore", f"Il registro delle immagini non risponde "
                              f"({type(e).__name__}): SearXNG resta com'è.", chi, manuale)
        vecchia = self._immagine_in_uso()
        if not vecchia:
            return self._fine("errore", "Non so quale immagine di SearXNG è in uso: resta "
                              "com'è (calliope motore searxng stato).", chi, manuale)
        degradata = self.giudizio().get("stato") in ("degradata", "giù")
        scelta = self.scegli(tags, vecchia, manuale, degradata)
        if scelta is None:
            if manuale or degradata:
                return self._fine("ultima", f"SearXNG è già all'immagine più recente che posso "
                                  f"usare ({tag_di(vecchia)}).", chi, manuale)
            return self._fine("niente", "", chi, manuale)
        nuova = scelta["immagine"]
        # Le prove sulla vecchia adesso: stessa rete e stessi motori della nuova
        self._fase(f"provo quella in uso ({tag_di(vecchia)})")
        prima = self._misura(self.url, vecchia)
        self._fase(f"scarico e provo {scelta['tag']} accanto")
        rc, out = self.script("candidata", nuova)
        if rc != 0:
            self.script("togli-candidata", timeout=60)
            return self._fine("errore", f"Non sono riuscita a scaricare o avviare "
                              f"{scelta['tag']}: SearXNG resta {tag_di(vecchia)}.", chi, manuale,
                              tag=scelta["tag"], dettaglio=out[-300:])
        url_prova = out.strip().splitlines()[-1].strip() if out.strip() else ""
        if not re.match(r"^http://127\.0\.0\.1:\d+$", url_prova):
            url_prova = f"http://127.0.0.1:{_porta(self.url) + 2000}"
        try:
            candidata = self._misura(url_prova, nuova)
        finally:
            self.script("togli-candidata", timeout=60)
        ok, perche = almeno_come(candidata, prima, self.minimo)
        if not ok:
            self._scarta(scelta["tag"])
            return self._fine("tenuta", f"Ho provato SearXNG {scelta['tag']} ma va peggio "
                              f"({perche}): resta {tag_di(vecchia)}.", chi, manuale,
                              tag=scelta["tag"], prima=_breve(prima), prova=_breve(candidata))
        # Il cambio: pochi secondi senza ricerca. L'automatico ricontrolla prima che nessuno
        # abbia cominciato a parlare intanto
        if not manuale:
            libera, motivo = self.libera()
            if not libera:
                return self._fine("rinviato", f"SearXNG {scelta['tag']} va bene, ma "
                                  f"{motivo}: lo cambio la prossima volta.", chi, manuale)
        self._fase(f"passo a {scelta['tag']}")
        rc, out = self.script("usa", nuova, timeout=300)
        dopo = self._misura(self.url, nuova) if rc == 0 else None
        ok, perche = almeno_come(dopo, prima, self.minimo) if dopo else (False, "non risponde")
        if not ok:
            self._fase("torno indietro")
            rc2, out2 = self.script("usa", vecchia, timeout=300)
            self._scarta(scelta["tag"])
            frase = (f"SearXNG {scelta['tag']} dopo il cambio va peggio ({perche}): sono "
                     f"tornata a {tag_di(vecchia)}." if rc2 == 0 else
                     f"SearXNG {scelta['tag']} non va ({perche}) e il ritorno a "
                     f"{tag_di(vecchia)} non è riuscito: calliope motore searxng avvia.")
            return self._fine("indietro" if rc2 == 0 else "errore", frase, chi, manuale,
                              tag=scelta["tag"], dettaglio=(out2 if rc2 else out)[-300:])
        stato, motivo = giudica(dopo, None, self.minimo, self.soglia)
        self._aggiorna_stato(immagine=nuova, buono=dopo, ultimo=dopo,
                             giudizio={"stato": stato, "motivo": motivo,
                                       "quando": dopo["quando"]})
        # Le immagini scaricate da qui e non più usate: tenute quella in uso e la precedente
        self.script("pulisci-immagini", vecchia, timeout=300)
        return self._fine("aggiornata", f"Ho aggiornato SearXNG da {tag_di(vecchia)} a "
                          f"{scelta['tag']}: {perche}.", chi, manuale, tag=scelta["tag"],
                          prima=_breve(prima), dopo=_breve(dopo))

    def _scarta(self, tag: str):
        sc = dict(self.leggi().get("scartate") or {})
        sc[tag] = self.orologio()
        # Solo le ultime: un tag di mesi fa non torna comunque
        self._aggiorna_stato(scartate=dict(sorted(sc.items(), key=lambda x: x[1])[-20:]))

    def _avvisa(self, titolo: str, testo: str):
        if self.avvisa is None:
            return
        try:
            self.avvisa(titolo, testo)
        except Exception as e:  # noqa: BLE001
            self.log(f"[WEB] avviso a chi amministra non mandato: {type(e).__name__}")

    # ── a richiesta (cruscotto) ──
    def avvia_azione(self, azione: str, chi: str) -> tuple[bool, str]:
        """«controlla» o «aggiorna» in un thread: (partita, frase). Il cruscotto mostra
        fase ed esito leggendo `vista()`."""
        if azione not in ("controlla", "aggiorna"):
            return False, "azione sconosciuta"
        if azione == "controlla" and not self.controllabile:
            return False, f"Il controllo non c'è qui: {self.perche}."
        if azione == "aggiorna" and not self.aggiornabile:
            return False, f"L'aggiornamento non c'è qui: {self.perche}."
        if azione == "aggiorna" and self.lavori_in_corso():
            return False, "Ci sono lavori dell'agente in corso: aggiorno quando finiscono."
        with self._avvio:
            if self.in_corso is not None or self._lock.locked():
                return False, "C'è già un controllo o un aggiornamento in corso."
            self.in_corso = {"azione": azione, "chi": chi, "dal": self.orologio(),
                             "fase": "comincio"}

        def corri():
            try:
                if azione == "controlla":
                    self.controlla(chi)
                else:
                    self.aggiorna(chi, manuale=True)
            except Occupato as e:
                if not self._lock.locked():
                    self.in_corso = None
                self._aggiorna_stato(esito={"esito": "occupato", "frase": f"{e}: riprova tra "
                                            "poco.", "quando": self.orologio(), "chi": chi})
            except Exception as e:  # noqa: BLE001
                if not self._lock.locked():
                    self.in_corso = None
                self.log(f"[WEB] SearXNG: {azione} non riuscito: {type(e).__name__}: {e}")
                try:
                    self._registra("errore", f"{azione} non riuscito ({type(e).__name__})",
                                   chi)
                except Exception:  # noqa: BLE001
                    pass
        threading.Thread(target=corri, name=f"searxng-{azione}", daemon=True).start()
        return True, "Controllo partito." if azione == "controlla" else "Aggiornamento partito."

    # ── automatico ──
    def passo(self) -> str:
        """Un giro del controllo quotidiano: cosa ha fatto (per il log e le prove)."""
        if not self.controllabile:
            return "spento"
        ore = float(getattr(self.cfg, "web_searxng_controllo_ore", 24.0) or 24.0)
        ultimo = (self.leggi().get("ultimo") or {}).get("quando") or 0
        if self.orologio() - float(ultimo) < ore * 3600:
            return "presto"
        libera, _ = self.libera()
        if not libera:
            return "occupata"
        try:
            r = self.controlla("automatico")
        except Occupato:
            return "occupata"
        if self.modo != "automatico" or not self.aggiornabile:
            return "controllato"
        libera, _ = self.libera()
        if not libera:
            return "controllato"
        try:
            a = self.aggiorna("automatico", manuale=False)
        except Occupato:
            return "controllato"
        return f"{r['stato']}:{a['esito']}"

    def avvia(self) -> "MotoreRicerca":
        if self._thread is not None or not self.controllabile:
            return self

        def giro():
            while not self._ferma.wait(GIRO_S):
                try:
                    self.passo()
                except Exception as e:  # noqa: BLE001 — mai fermare il controllo
                    self.log(f"[WEB] controllo di SearXNG non riuscito: {type(e).__name__}: {e}")
        self._thread = threading.Thread(target=giro, name="searxng-controllo", daemon=True)
        self._thread.start()
        return self

    def ferma(self):
        self._ferma.set()


def _dici(stato: str) -> str:
    return {"buona": "va bene", "degradata": "degradata", "giù": "SearXNG non risponde"}.get(
        stato, stato)


def _breve(esito: dict | None) -> dict | None:
    if not esito:
        return None
    return {"risposte": esito.get("risposte"), "risultati": esito.get("risultati"),
            "motori": len(esito.get("motori") or ())}


# ─────────────────────────── da terminale ───────────────────────────

def _lavori_da_file() -> int:
    """I lavori in coda o in corso secondo Calliope (lavori/in_corso.json nella cartella dei
    dati, come il gestore), se il processo che li ha scritti è vivo."""
    f = Path("lavori") / "in_corso.json"
    try:
        dati = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    pid = dati.get("pid") if isinstance(dati, dict) else None
    if isinstance(pid, int) and not _vivo(pid):
        return 0
    return sum(1 for r in (dati.get("lavori") or []) if isinstance(r, dict)
               and r.get("stato") in ("in_coda", "in_corso"))


def main(argv=None) -> int:
    import argparse
    from ..config import load_config
    p = argparse.ArgumentParser(prog="calliope motore searxng",
                                description="Controllo e aggiornamento di SearXNG")
    p.add_argument("azione", choices=("controlla", "aggiorna", "novita", "storia"))
    a = p.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    cfg = load_config()
    m = MotoreRicerca(cfg, lavori=_lavori_da_file)
    if not m.controllabile:
        print(f"Niente da fare qui: {m.perche}.")
        return 1
    try:
        if a.azione == "controlla":
            r = m.controlla("terminale")
            e = r["esito"]
            print(f"{_dici(r['stato'])}" + (f": {r['motivo']}" if r["motivo"] else ""))
            for x in e["prove"]:
                giu = ", ".join(f"{g[0]} ({g[1]})" for g in x["giu"]) or "nessuno"
                print(f"  {x['categoria']:8} «{x['domanda']}»: {x['risultati']} risultati in "
                      f"{x['ms']} ms, motori {', '.join(x['motori']) or '—'}; non rispondono "
                      f"{giu}" + (f"; errore {x['errore']}" if x.get("errore") else ""))
            return 0 if r["stato"] == "buona" else 3
        if a.azione == "aggiorna":
            r = m.aggiorna("terminale", manuale=True)
            print(r["frase"] or r["esito"])
            return 0 if r["esito"] in ("aggiornata", "ultima") else 1
        if a.azione == "novita":
            tags = m.novita()
            attuale = tag_di(m._immagine_in_uso())
            print(f"In uso: {attuale or 'non so (qui non c è docker?)'}")
            for t in tags[:8]:
                giorni = (time.time() - t["pubblicata"]) / 86400
                print(f"  {t['tag']:24} pubblicata {giorni:.1f} giorni fa"
                      + ("  ← in uso" if t["tag"] == attuale else ""))
            return 0
        for e in m.leggi().get("storia") or []:
            quando = datetime.datetime.fromtimestamp(e.get("quando") or 0)
            print(f"{quando:%d/%m %H:%M}  {e.get('evento', ''):14} {e.get('chi', ''):11} "
                  f"{e.get('frase', '')}")
        return 0
    except Occupato as e:
        print(f"{e}: riprova tra poco.")
        return 75


if __name__ == "__main__":
    sys.exit(main())
