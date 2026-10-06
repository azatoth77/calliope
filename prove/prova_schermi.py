import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco degli schermi (calliope/schermi/, fase 1 del rapporto
docs/ricerche/2026-10-01-mappe-e-schermi.md).

- archivio: stanze dette a voce, codici, richiesta che diventa token, solo hash sul disco,
  5 codici sbagliati, scadenza, revoca;
- visibilità: pubblica, casa, personale per ospite, familiare, chi amministra, zona grigia e
  stanza; una scheda personale mai sullo schermo del soggiorno;
- server vero (uvicorn in un thread su una porta libera di 127.0.0.1) con un client httpx:
  pagina e file locali (niente indirizzi esterni), intestazioni di sicurezza, Host non
  ammessi, abbinamento, accesso, SSE (benvenuto, schede, latenza su 30 invii, cronologia
  alla riconnessione), revoca a voce e da terminale, arresto con una connessione aperta;
- schede dei tool con contesti finti: liste, timer, promemoria, biblioteca, documento (anche
  in secondo piano), casa, calcolo, e Brain che le toglie dal risultato del modello e le
  manda senza aspettare;
- tool schermo_mostra e schermo_gestisci, permessi;
- niente token né codici nei log (stdout, stderr, logger di uvicorn, registro dei turni);
- capacità «schermi» e `python -m calliope.schermi` in un sottoprocesso.

Tutto in una cartella temporanea: non legge calliope.locale.yaml, non tocca memoria.db.
"""

import asyncio
import contextlib
import io
import json
import re
import logging
import socket
import sqlite3
import statistics
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import httpx

from calliope import capacita
from calliope.brain import Brain
from calliope.config import Config
from calliope.schermi import ArchivioSchermi, Mittente, Schermi, cifre, destinatari, norm_stanza
from calliope.schermi import schede, server as srvmod
from calliope.schermi.server import ServerSchermi
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

RADICE = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="calliope-schermi-"))
errori = 0

# Tutto quello che il processo scrive: alla fine si cerca dentro token e codici
_cattura = io.StringIO()
_log = logging.getLogger("uvicorn")
_log.addHandler(logging.StreamHandler(_cattura))
_log.setLevel(logging.DEBUG)
logging.getLogger("uvicorn.error").addHandler(logging.StreamHandler(_cattura))
SEGRETI: list[str] = []


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


class Prof:
    def __init__(self, pid, name, admin=False):
        self.id, self.name, self.admin = pid, name, admin


class Speakers:
    def __init__(self):
        self.p = {"Dario": Prof("dario-id", "Dario", True), "Bianca": Prof("bianca-id", "Bianca")}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    def __init__(self, name, level, from_session=False):
        self.current_speaker, self.current_level, self.from_session = name, level, from_session
        self.identified_by = "voce" if name else None


def cfg_prova(**kw) -> Config:
    c = Config()
    c.memory_db = str(TMP / "memoria.db")
    c.casa_url = None
    c.config_dir = str(TMP)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


# ─────────────────────────── archivio ───────────────────────────

def prova_archivio():
    for detto, atteso in (("al soggiorno", "soggiorno"), ("della Cucina.", "cucina"),
                          ("lo studio", "studio"), ("nell'ingresso", "ingresso"),
                          ("lo schermo della camera di Bianca", "camera di bianca"),
                          ("Ilaria", "ilaria"), ("in", ""), ("", ""), (None, "")):
        verifica(f"stanza «{detto}» → «{atteso}»", norm_stanza(detto) == atteso,
                 repr(norm_stanza(detto)))
    for detto, atteso in (("123 456", "123456"), ("123.456", "123456"), ("1-2-3-4-5-6", "123456"),
                          ("codice 042", "042")):
        verifica(f"cifre «{detto}»", cifre(detto) == atteso, cifre(detto))

    db = str(TMP / "archivio.db")
    a = ArchivioSchermi(db)
    r = a.nuova_richiesta()
    SEGRETI.extend([r["richiesta"]])
    verifica("codice di 6 cifre", len(r["codice"]) == 6 and r["codice"].isdigit())
    verifica("richiesta lunga (token futuro)", len(r["richiesta"]) >= 40)
    verifica("in attesa", a.stato_richiesta(r["richiesta"])["stato"] == "attesa")
    verifica("richiesta sconosciuta: scaduta", a.stato_richiesta("x" * 43)["stato"] == "scaduto")
    verifica("formato del codice", a.abbina("12345", "soggiorno")["esito"] == "formato")
    verifica("stanza mancante", a.abbina(r["codice"], "")["esito"] == "stanza")
    res = a.abbina(" ".join([r["codice"][:3], r["codice"][3:]]), "al soggiorno")
    verifica("abbinato con il codice detto «123 456»", res["esito"] == "abbinato"
             and res["schermo"]["stanza"] == "soggiorno", str(res.get("esito")))
    st = a.stato_richiesta(r["richiesta"])
    verifica("la richiesta è diventata il token", st["stato"] == "abbinato"
             and a.per_token(r["richiesta"])["nome"] == "soggiorno")
    verifica("token sbagliato: nessuno schermo", a.per_token("y" * 43) is None
             and a.per_token("") is None)
    verifica("codice usato non vale più", a.abbina(r["codice"], "cucina")["esito"] == "sbagliato")
    # Secondo schermo nella stessa stanza: nome distinto
    r2 = a.nuova_richiesta()
    SEGRETI.append(r2["richiesta"])
    res2 = a.abbina(r2["codice"], "soggiorno")
    verifica("secondo schermo in soggiorno: «soggiorno 2»", res2["schermo"]["nome"] == "soggiorno 2")
    # Solo hash sul disco
    a.db.commit()
    raw = Path(db).read_bytes()
    verifica("sul disco niente token in chiaro", r["richiesta"].encode() not in raw
             and r2["richiesta"].encode() not in raw)
    # 5 codici sbagliati: tutti i codici in attesa si annullano
    attesa = a.nuova_richiesta()
    SEGRETI.append(attesa["richiesta"])
    sbagliati = [c for c in ("000001", "000002", "000003", "000004", "000005")
                 if c != attesa["codice"]]
    esiti = [a.abbina(c, "cucina")["esito"] for c in sbagliati[:4]]
    verifica("4 codici sbagliati: «sbagliato»", esiti == ["sbagliato"] * 4, str(esiti))
    last = a.abbina(sbagliati[4] if len(sbagliati) > 4 else "000006", "cucina")["esito"]
    verifica("il quinto annulla tutti i codici", last == "troppi"
             and a.stato_richiesta(attesa["richiesta"])["stato"] == "scaduto", last)
    # Scadenza
    sc = a.nuova_richiesta()
    SEGRETI.append(sc["richiesta"])
    a.db.execute("UPDATE schermi_attesa SET scade = ?", (time.time() - 1,))
    a.db.commit()
    verifica("codice scaduto non abbina", a.abbina(sc["codice"], "cucina")["esito"] == "sbagliato"
             and a.stato_richiesta(sc["richiesta"])["stato"] == "scaduto")
    # Al massimo 20 codici in attesa
    for _ in range(30):
        SEGRETI.append(a.nuova_richiesta()["richiesta"])
    verifica("al massimo 20 codici in attesa", a.in_attesa() == 20, str(a.in_attesa()))
    # Revoca
    verifica("trova per stanza", len(a.trova("il soggiorno")) == 1
             and a.trova("il soggiorno")[0]["nome"] == "soggiorno")
    via = a.revoca("soggiorno 2")
    verifica("revoca per nome", [s["nome"] for s in via] == ["soggiorno 2"]
             and a.per_token(r2["richiesta"]) is None)
    verifica("revoca di uno schermo che non c'è", a.revoca("garage") == [])
    s, tok = a.crea_con_token("studio", "dario-id", "Dario")
    SEGRETI.append(tok)
    verifica("kiosk: schermo personale con token", s["nome"] == "studio di dario"
             and a.per_token(tok)["proprietario"] == "dario-id")
    a.close()


# ─────────────────────────── visibilità ───────────────────────────

def prova_visibilita():
    soggiorno = {"id": 1, "nome": "soggiorno", "stanza": "soggiorno", "proprietario": None}
    cucina = {"id": 2, "nome": "cucina", "stanza": "cucina", "proprietario": None}
    studio_d = {"id": 3, "nome": "studio di dario", "stanza": "studio",
                "proprietario": "dario-id"}
    tutti = [soggiorno, cucina, studio_d]
    ospite = Mittente()
    bianca = Mittente("bianca-id", "Bianca", "familiare", True)
    dario = Mittente("dario-id", "Dario", "amministra", True)
    dario_grigio = Mittente("dario-id", "Dario", "familiare", False)

    def ids(vis, m, stanza=None, schermi=tutti):
        d, why = destinatari(vis, m, schermi, stanza)
        return [s["id"] for s in d], why

    casi = [
        ("pubblica, ospite, tutte le stanze", ids("pubblica", ospite), ([1, 2, 3], "")),
        ("pubblica, ospite, soggiorno", ids("pubblica", ospite, "soggiorno"), ([1], "")),
        ("casa, ospite: no", ids("casa", ospite), ([], "ospite")),
        ("casa, familiare, soggiorno", ids("casa", bianca, "al soggiorno"), ([1], "")),
        ("personale, Dario: solo il suo schermo", ids("personale", dario), ([3], "")),
        ("personale, Dario in soggiorno: lo stesso solo il suo", ids("personale", dario, "soggiorno"),
         ([3], "")),
        ("personale, Bianca senza schermo suo", ids("personale", bianca), ([], "personale")),
        ("personale, ospite", ids("personale", ospite), ([], "ospite")),
        ("personale, zona grigia", ids("personale", dario_grigio), ([], "zona_grigia")),
        ("casa nella zona grigia sì", ids("casa", dario_grigio, "cucina"), ([2], "")),
        ("stanza senza schermi", ids("pubblica", bianca, "garage"), ([], "stanza")),
        ("nessuno schermo", ids("pubblica", bianca, None, []), ([], "nessuno_schermo")),
        ("visibilità sconosciuta: niente", ids("segreta", dario), ([], "visibilita")),
    ]
    for nome, got, atteso in casi:
        verifica(f"visibilità: {nome}", got == atteso, "" if got == atteso
                 else f"{got} invece di {atteso}")
    # Mai una scheda personale sullo schermo del soggiorno, per nessuno
    mai = all(1 not in ids("personale", m, st)[0] for m in (ospite, bianca, dario, dario_grigio)
              for st in (None, "soggiorno"))
    verifica("personale mai sullo schermo del soggiorno", mai)


# ─────────────────────────── server ───────────────────────────

class LettoreSSE:
    """Un client SSE in un thread: raccoglie (istante, evento, dati)."""

    def __init__(self, base, sessione):
        self.eventi = []
        self.status = None
        self.chiuso = threading.Event()
        self._stop = False
        self.t = threading.Thread(target=self._run, args=(base, sessione), daemon=True)
        self.t.start()

    def _run(self, base, sessione):
        ev = None
        try:
            with httpx.stream("GET", f"{base}/eventi?sessione={sessione}", timeout=30) as r:
                self.status = r.status_code
                if r.status_code != 200:
                    return
                for line in r.iter_lines():
                    if self._stop:
                        break
                    if line.startswith("event: "):
                        ev = line[7:]
                    elif line.startswith("data: "):
                        self.eventi.append((time.perf_counter(), ev, json.loads(line[6:])))
                        if ev == "revocato":
                            break
        except Exception as e:  # noqa: BLE001
            self.eventi.append((time.perf_counter(), "errore", str(e)))
        finally:
            self.chiuso.set()

    def attendi(self, tipo, n=1, max_s=3.0):
        t0 = time.monotonic()
        while time.monotonic() - t0 < max_s:
            if sum(e[1] == tipo for e in self.eventi) >= n:
                return True
            time.sleep(0.005)
        return False

    def di(self, tipo):
        return [e for e in self.eventi if e[1] == tipo]


def nuovo_schermo(c, hub, stanza, owner=None, owner_name=None):
    r = c.post("/api/abbinamento").json()
    SEGRETI.extend([r["richiesta"], r["codice"]])
    res = hub.abbina(r["codice"], stanza, owner, owner_name)
    assert res["ok"], res
    a = c.post("/api/accedi", headers={"Authorization": f"Bearer {r['richiesta']}"}).json()
    return r["richiesta"], a


def prova_server():
    srvmod.PING_S = 0.3              # la revoca da terminale si vede al ping
    cfg = cfg_prova(schermi_porta=0)
    hub = Schermi(cfg, ArchivioSchermi(str(TMP / "server.db")))
    srv = ServerSchermi(hub, "127.0.0.1", 0).avvia()
    base = f"http://127.0.0.1:{srv.port}"
    c = httpx.Client(base_url=base, timeout=5)
    # Pagina e file: tutto locale
    p = c.get("/")
    verifica("pagina servita", p.status_code == 200 and "schermo.js" in p.text)
    verifica("intestazioni di sicurezza", "default-src 'self'" in p.headers.get(
        "content-security-policy", "") and p.headers.get("x-content-type-options") == "nosniff")
    verifica("niente intestazione server", "server" not in p.headers)
    for f in ("index.html", "schermo.css", "schermo.js"):
        text = (srvmod.PAGINA / f).read_text(encoding="utf-8")
        ext = [w for w in ("http://", "https://", "//cdn", "fonts.googleapis", "@import")
               if w in text]
        verifica(f"{f}: niente indirizzi esterni", not ext, str(ext))
    js = (srvmod.PAGINA / "schermo.js").read_text(encoding="utf-8")
    verifica("schermo.js non usa innerHTML", "innerHTML" not in js and "insertAdjacentHTML" not in js)
    verifica("CSS e JS serviti con il tipo giusto",
             c.get("/schermo.css").headers["content-type"].startswith("text/css")
             and "javascript" in c.get("/schermo.js").headers["content-type"])
    verifica("Host non ammesso (DNS rebinding): 400",
             c.get("/", headers={"Host": "attacco.example.com"}).status_code == 400)
    verifica("Host localhost ammesso", c.get("/api/salute", headers={"Host": "localhost:1"})
             .status_code == 200)
    verifica("accesso con token sbagliato: 401", c.post(
        "/api/accedi", headers={"Authorization": "Bearer " + "z" * 43}).status_code == 401)
    verifica("eventi senza sessione: 401", c.get("/eventi?sessione=nulla").status_code == 401)

    # Abbinamento dalla pagina
    r = c.post("/api/abbinamento").json()
    SEGRETI.extend([r["richiesta"], r["codice"]])
    stato = lambda: c.post("/api/abbinamento/stato",   # noqa: E731
                           headers={"Authorization": f"Bearer {r['richiesta']}"}).json()
    verifica("pagina nuova: in attesa", stato()["stato"] == "attesa")
    verifica("abbinamento senza richiesta: 401",
             c.post("/api/abbinamento/stato").status_code == 401)
    hub.abbina(r["codice"], "soggiorno")
    st = stato()
    verifica("pagina abbinata, con la stanza", st == {"stato": "abbinato", "nome": "soggiorno",
                                                      "stanza": "soggiorno"}, str(st))
    a = c.post("/api/accedi", headers={"Authorization": f"Bearer {r['richiesta']}"}).json()
    verifica("accesso: sessione diversa dal token", a.get("sessione") and a["sessione"]
             != r["richiesta"] and a["stanza"] == "soggiorno" and a["personale"] is False)

    # SSE
    sogg = LettoreSSE(base, a["sessione"])
    verifica("SSE: benvenuto", sogg.attendi("benvenuto"), str(sogg.eventi[:1]))
    tok_d, a_d = nuovo_schermo(c, hub, "studio", "dario-id", "Dario")
    studio = LettoreSSE(base, a_d["sessione"])
    studio.attendi("benvenuto")
    dario = Mittente("dario-id", "Dario", "amministra", True)
    ospite = Mittente()
    lat = []
    n_studio0 = len(studio.di("scheda"))
    for i in range(30):
        n0 = len(sogg.di("scheda"))
        t0 = time.perf_counter()
        res = hub.invia(schede.calcolo(f"{i}*2", str(i * 2)), ospite)
        invio_ms = (time.perf_counter() - t0) * 1000
        sogg.attendi("scheda", n0 + 1)
        e = sogg.di("scheda")[-1]
        lat.append((e[0] - t0) * 1000)
        if i == 0:
            verifica("invio non bloccante (< 5 ms)", invio_ms < 5, f"{invio_ms:.2f} ms")
            verifica("pubblica: su soggiorno e studio", sorted(res["schermi"]) ==
                     ["soggiorno", "studio di dario"], str(res))
    med, mx = statistics.median(lat), max(lat)
    print(f"   latenza scheda → pagina su 30 invii: mediana {med:.2f} ms, massimo {mx:.2f} ms")
    verifica("latenza SSE in locale (mediana < 20 ms)", med < 20, f"{med:.2f} ms")
    # Personale: solo allo studio di Dario. Prima le 30 pubbliche anche allo studio: il ciclo
    # aspetta solo il soggiorno, e sotto carico l'ultima arrivava allo studio dopo il conteggio
    # (06/10, due runner insieme: «personale: arrivata allo studio di Dario» falliva)
    studio.attendi("scheda", n_studio0 + 30)
    n_s, n_d = len(sogg.di("scheda")), len(studio.di("scheda"))
    doc = schede.testo("Lettera alla palestra", "Gentile palestra…", schede.PERSONALE)
    res = hub.invia(doc, dario)
    studio.attendi("scheda", n_d + 1)
    time.sleep(0.1)
    verifica("personale: arrivata allo studio di Dario", len(studio.di("scheda")) == n_d + 1
             and studio.di("scheda")[-1][2]["titolo"] == "Lettera alla palestra")
    verifica("personale: NON arrivata al soggiorno", len(sogg.di("scheda")) == n_s
             and res["schermi"] == ["studio di dario"], str(res))
    res = hub.invia(schede.testo("Agenda", "dentista", schede.PERSONALE),
                    Mittente("bianca-id", "Bianca", "familiare", True))
    verifica("personale di Bianca senza schermo suo: nessuno", res["schermi"] == []
             and res["motivo"] == "personale")
    # Stanza: schermi_stanza = cucina → il soggiorno non riceve
    cfg.schermi_stanza = "cucina"
    res = hub.invia(schede.calcolo("1+1", "2"), ospite)
    verifica("stanza del microfono senza schermi: nessuno", res["motivo"] == "stanza")
    cfg.schermi_stanza = ""
    # Automatiche spente: solo le richieste esplicite
    cfg.schermi_automatiche = False
    res = hub.invia(schede.calcolo("1+2", "3"), ospite)
    res2 = hub.invia(schede.calcolo("1+3", "4"), ospite, forza=True)
    verifica("automatiche spente: la scheda del tool non parte, «mostramelo» sì",
             res["motivo"] == "automatiche_spente" and res2["schermi"], str(res2))
    cfg.schermi_automatiche = True
    verifica("ultima scheda ricordata per la persona", hub.ultima(dario)["titolo"]
             == "Lettera alla palestra" and hub.ultima(ospite)["espressione"] == "1+3")

    # Cronologia alla riconnessione
    a2 = c.post("/api/accedi", headers={"Authorization": f"Bearer {r['richiesta']}"}).json()
    sogg2 = LettoreSSE(base, a2["sessione"])
    sogg2.attendi("benvenuto")
    cron = sogg2.di("benvenuto")[0][2]["cronologia"]
    verifica("riconnessione: cronologia (al massimo schermi_cronologia)",
             0 < len(cron) <= cfg.schermi_cronologia, str(len(cron)))
    verifica("cronologia del soggiorno senza schede personali",
             all(x["visibilita"] != "personale" for x in cron))

    # Uno schermo lento non ferma niente: la coda piena scarta
    conn, _ = hub.collega({"id": 999, "nome": "lento"}, asyncio.new_event_loop())
    t0 = time.perf_counter()
    for _ in range(100):
        conn.consegna(("scheda", "{}"))
    verifica("schermo lento: 100 consegne in < 20 ms", (time.perf_counter() - t0) * 1000 < 20)
    hub.scollega(conn)
    # Ciclo chiuso: consegna che non solleva
    loop = asyncio.new_event_loop()
    loop.close()
    conn2, _ = hub.collega({"id": 998, "nome": "chiuso"}, loop)
    verifica("ciclo chiuso: consegna fallita senza eccezioni", conn2.consegna(("scheda", "{}"))
             is False)
    hub.scollega(conn2)

    # Revoca a voce: la pagina riceve «revocato» e il token non vale più
    via = hub.revoca("studio")
    verifica("revoca: evento alla pagina", studio.attendi("revocato") and via)
    verifica("revoca: accesso rifiutato", c.post(
        "/api/accedi", headers={"Authorization": f"Bearer {tok_d}"}).status_code == 401)
    # Revoca da terminale (un altro ArchivioSchermi sullo stesso file): arriva al ping
    altro = ArchivioSchermi(str(TMP / "server.db"))
    altro.revoca("soggiorno")
    altro.close()
    hub._rinfresca()
    verifica("revoca da terminale: «revocato» al ping", sogg2.attendi("revocato", max_s=3))
    # Arresto con una connessione aperta
    tok3, a3 = nuovo_schermo(c, hub, "cucina")
    aperto = LettoreSSE(base, a3["sessione"])
    aperto.attendi("benvenuto")
    t0 = time.perf_counter()
    srv.ferma()
    dt = time.perf_counter() - t0
    verifica("arresto con una pagina collegata (< 3 s)", not srv.thread.is_alive() and dt < 3,
             f"{dt:.2f} s")
    c.close()
    return med, mx


def prova_voce():
    """Stato della voce sugli schermi (02/10): addormentata, in ascolto con il tempo che
    resta, sta pensando, sta parlando. Solo agli schermi del microfono che ascolta (il
    satellite dello studio), uno stato al riaggancio, la finestra di follow-up che scade."""
    cfg = cfg_prova(schermi_porta=0)
    hub = Schermi(cfg, ArchivioSchermi(str(TMP / "stato-voce.db")))
    srv = ServerSchermi(hub, "127.0.0.1", 0).avvia()
    base = f"http://127.0.0.1:{srv.port}"
    c = httpx.Client(base_url=base, timeout=5)
    stanza = {"v": "studio"}
    hub.stanza_corrente = lambda: stanza["v"]          # audio da un satellite nello studio
    _, a_s = nuovo_schermo(c, hub, "studio")
    _, a_c = nuovo_schermo(c, hub, "cucina")
    studio, cucina = LettoreSSE(base, a_s["sessione"]), LettoreSSE(base, a_c["sessione"])
    studio.attendi("benvenuto")
    cucina.attendi("benvenuto")
    b = studio.di("benvenuto")[0][2]
    verifica("voce: al collegamento lo stato attuale (addormentata)",
             b.get("voce") == {"stato": "dorme", "fino": None}, str(b.get("voce")))
    verifica("voce: lo schermo di un'altra stanza non lo mostra",
             cucina.di("benvenuto")[0][2].get("voce") is None)

    # Un turno: finestra di follow-up, frase, pensa, parla, di nuovo in ascolto
    t = []
    fino = time.time() + 30
    for stato, f in (("ascolta", fino), ("ascolta", None), ("pensa", None), ("parla", None),
                     ("parla", None), ("ascolta", fino)):
        t0 = time.perf_counter()
        hub.voce(stato, f)
        t.append((time.perf_counter() - t0) * 1000)
    studio.attendi("voce", 5)
    seq = [(e[2]["stato"], e[2]["fino"]) for e in studio.di("voce")]
    verifica("voce: sequenza di un turno (lo stato ripetuto non si rimanda)",
             seq == [("ascolta", round(fino, 3)), ("ascolta", None), ("pensa", None),
                     ("parla", None), ("ascolta", round(fino, 3))], str(seq))
    verifica("voce: nessun dato di chi parla (solo stato e scadenza)",
             all(set(e[2]) == {"stato", "fino"} for e in studio.di("voce")))
    verifica("voce: niente alla cucina", not cucina.di("voce"))
    # Mediana sotto i 2 ms; il massimo solo sotto i 50 (bloccare vorrebbe dire aspettare una
    # pagina, secondi): con più prove insieme sul portatile la prima chiamata, che avvia il
    # thread delle scadenze, arrivava a 18 ms (03/10)
    verifica("voce: Schermi.voce non blocca (mediana < 2 ms, massimo < 50)",
             statistics.median(t) < 2 and max(t) < 50,
             f"mediana {statistics.median(t):.2f} ms, massimo {max(t):.2f} ms: "
             + ", ".join(f"{x:.1f}" for x in t))

    # La finestra di follow-up scade: torna «dorme» da sola
    hub.voce("ascolta", time.time() + 0.4)
    torna = studio.attendi("voce", 7, max_s=3) and studio.di("voce")[-1][2]["stato"] == "dorme"
    verifica("voce: follow-up scaduto → addormentata", torna,
             str([e[2] for e in studio.di("voce")[-2:]]))

    # Interruzione (barge-in): parla, poi subito in ascolto senza conto alla rovescia
    hub.voce("parla")
    hub.voce("ascolta")
    studio.attendi("voce", 9)
    verifica("voce: interruzione → in ascolto",
             [e[2]["stato"] for e in studio.di("voce")[-2:]] == ["parla", "ascolta"])

    # Riaggancio: la pagina nuova riceve lo stato di adesso, non quello vecchio
    hub.voce("pensa")
    di_nuovo = LettoreSSE(base, a_s["sessione"])
    di_nuovo.attendi("benvenuto")
    verifica("voce: al riaggancio lo stato di adesso",
             di_nuovo.di("benvenuto")[0][2].get("voce") == {"stato": "pensa", "fino": None})

    # Il satellite cambia stanza: lo stato va alla cucina
    stanza["v"] = "cucina"
    hub.voce("parla")
    verifica("voce: segue la stanza del satellite attivo",
             cucina.attendi("voce") and cucina.di("voce")[-1][2]["stato"] == "parla")
    # Audio locale, schermi_stanza vuota: le pagine aperte su questo computer (127.0.0.1)
    hub.stanza_corrente = None
    n = hub.voce("ascolta")
    verifica("voce: audio locale → le pagine di questo computer", n == 3, f"{n} pagine")
    stato_html = (srvmod.PAGINA / "index.html").read_text(encoding="utf-8")
    js = (srvmod.PAGINA / "schermo.js").read_text(encoding="utf-8")
    verifica("pagina: fascia dello stato con ruolo status e forma",
             'id="voce"' in stato_html and 'role="status"' in stato_html
             and 'class="forma"' in stato_html and '"voce"' in js)
    srv.ferma()
    c.close()


def prova_voce_stanze():
    """Stato della voce per stanza (06/10, P9): con i satelliti insieme ogni corsia manda il
    suo stato agli schermi della sua stanza. Lo studio che pensa e la cucina che dorme non si
    sovrascrivono: ogni stanza ha il suo stato, la sua finestra di follow-up e il suo
    riaggancio."""
    cfg = cfg_prova(schermi_porta=0)
    hub = Schermi(cfg, ArchivioSchermi(str(TMP / "stato-voce-stanze.db")))
    srv = ServerSchermi(hub, "127.0.0.1", 0).avvia()
    base = f"http://127.0.0.1:{srv.port}"
    c = httpx.Client(base_url=base, timeout=5)
    hub.stanza_corrente = lambda: "studio"            # il satellite «attivo» fuori dalle corsie
    _, a_s = nuovo_schermo(c, hub, "studio")
    _, a_c = nuovo_schermo(c, hub, "cucina")
    studio, cucina = LettoreSSE(base, a_s["sessione"]), LettoreSSE(base, a_c["sessione"])
    studio.attendi("benvenuto")
    cucina.attendi("benvenuto")
    hub.voce("pensa", stanza="studio")
    hub.voce("ascolta", time.time() + 0.5, stanza="cucina")
    hub.voce("pensa", stanza="studio")                # stesso stato della sua stanza: niente
    hub.voce("parla", stanza="studio")
    hub.voce("parla", stanza="cucina")                # stesso stato, altra stanza: si manda
    hub.voce("ascolta", time.time() + 0.5, stanza="cucina")
    studio.attendi("voce", 2)
    cucina.attendi("voce", 4, max_s=3)                # ascolta, parla, ascolta, dorme
    seq_s = [e[2]["stato"] for e in studio.di("voce")]
    seq_c = [e[2]["stato"] for e in cucina.di("voce")]
    verifica("voce per stanza: lo studio riceve solo i suoi stati", seq_s == ["pensa", "parla"],
             str(seq_s))
    verifica("voce per stanza: la cucina i suoi, e la sua finestra scade da sola",
             seq_c == ["ascolta", "parla", "ascolta", "dorme"], str(seq_c))
    time.sleep(0.2)
    verifica("voce per stanza: la scadenza della cucina non tocca lo studio",
             [e[2]["stato"] for e in studio.di("voce")] == ["pensa", "parla"])
    r_s, r_c = LettoreSSE(base, a_s["sessione"]), LettoreSSE(base, a_c["sessione"])
    r_s.attendi("benvenuto")
    r_c.attendi("benvenuto")
    verifica("voce per stanza: al riaggancio ognuno lo stato della sua stanza",
             r_s.di("benvenuto")[0][2].get("voce", {}).get("stato") == "parla"
             and r_c.di("benvenuto")[0][2].get("voce", {}).get("stato") == "dorme",
             f"{r_s.di('benvenuto')[0][2].get('voce')} {r_c.di('benvenuto')[0][2].get('voce')}")
    # Senza stanza vale come prima il microfono che ascolta (qui lo studio)
    n = hub.voce("dorme")
    verifica("voce senza stanza: il microfono che ascolta (un satellite solo, audio locale)",
             n == 2 and studio.attendi("voce", 3) and not cucina.attendi("voce", 5, max_s=0.3),
             f"{n} pagine")
    srv.ferma()
    c.close()


def prova_voce_stessa_stanza():
    """Due satelliti nella stessa stanza (06/10, Q9 della seconda analisi): l'hub vero, due
    corsie vere (`Ciclo`, con i loro callback del VAD e della voce) e una pagina dello studio.
    Prima vinceva chi scriveva per ultimo: la corsia che scartava una frase riportava «dorme»
    mentre l'altra parlava. Ora la stanza mostra l'unione (parla > pensa > ascolta > dorme), e
    il satellite che se ne va toglie il suo stato."""
    import types
    from calliope import corsie
    from calliope.ciclo import Ciclo, Servizi

    cfg = cfg_prova(schermi_porta=0)
    hub = Schermi(cfg, ArchivioSchermi(str(TMP / "stato-voce-stessa.db")))
    srv = ServerSchermi(hub, "127.0.0.1", 0).avvia()
    base = f"http://127.0.0.1:{srv.port}"
    c = httpx.Client(base_url=base, timeout=5)
    _, a_s = nuovo_schermo(c, hub, "studio")
    studio = LettoreSSE(base, a_s["sessione"])
    studio.attendi("benvenuto")

    class Satelliti:
        def __init__(self):
            self.c = {1: types.SimpleNamespace(stanza="Studio"),
                      2: types.SimpleNamespace(stanza="studio")}

        def per_id(self, sid):
            return self.c.get(sid)

    servizi = Servizi(cfg, schermi=hub, satelliti=Satelliti())

    def corsia(sid):
        lst = types.SimpleNamespace(on_speech_start=None, on_speech_end=None)
        sp = types.SimpleNamespace(on_parla=None)
        ciclo = Ciclo(servizi, corsie.Corsia(f"sat:{sid}", sid), lst, sp, None, None, None,
                      None, None, threading.Event())
        return ciclo, lst, sp
    (a, la, sa), (b, lb, sb) = corsia(1), corsia(2)

    def stati(n):
        studio.attendi("voce", n, max_s=2)
        return [e[2]["stato"] for e in studio.di("voce")]
    a.voce("pensa")                     # il primo satellite pensa
    lb.on_speech_start()                # nel secondo qualcuno comincia a parlare: ascolta
    b.attesa_voce[:] = ["dorme", None]
    lb.on_speech_end()                  # …ed era una frase buttata: il secondo dorme
    verifica("stessa stanza: una frase buttata dall'altro satellite non fa «dormire» lo studio",
             stati(1) == ["pensa"] and not studio.attendi("voce", 2, max_s=0.3),
             str(stati(1)))
    sa.on_parla()                       # il primo parla
    sb.on_parla()                       # e anche il secondo: lo studio parla comunque
    a.voce("dorme")                     # il primo ha finito: il secondo parla ancora
    verifica("stessa stanza: parla finché uno dei due parla", stati(2) == ["pensa", "parla"]
             and not studio.attendi("voce", 3, max_s=0.3), str(stati(2)))
    b.voce("ascolta", time.time() + 0.4)   # il secondo apre la sua finestra di follow-up
    verifica("stessa stanza: poi in ascolto, e la finestra scade da sola",
             stati(4) == ["pensa", "parla", "ascolta", "dorme"], str(stati(4)))
    b.voce("pensa")
    stati(5)
    verifica("hub: la stanza ha le due sorgenti", set(hub._voce_src.get("studio", {}))
             == {"sat:1", "sat:2"}, str(hub._voce_src))
    n = hub.voce_via("sat:2")           # il secondo satellite se ne va mentre pensava
    verifica("satellite che se ne va: la stanza mostra gli altri (qui dorme)",
             n == 1 and stati(6)[-1] == "dorme", str(stati(6)))
    a.voce("pensa")
    stati(7)
    hub.voce_via("sat:1")
    verifica("l'ultimo satellite se ne va: la stanza esce dallo stato, la pagina dorme",
             "studio" not in hub._voce and "studio" not in hub._voce_src
             and stati(8)[-1] == "dorme", f"{hub._voce} {stati(8)}")
    di_nuovo = LettoreSSE(base, a_s["sessione"])
    di_nuovo.attendi("benvenuto")
    verifica("riaggancio dopo che i satelliti sono andati: niente stato vecchio («pensa»)",
             (di_nuovo.di("benvenuto")[0][2].get("voce") or {}).get("stato") in (None, "dorme"),
             str(di_nuovo.di("benvenuto")[0][2].get("voce")))
    # Un satellite che cambia stanza lascia quella di prima
    hub.voce("pensa", stanza="studio", sorgente="sat:3")
    hub.voce("parla", stanza="cucina", sorgente="sat:3")
    verifica("satellite spostato: lo stato lascia la stanza di prima",
             "sat:3" not in (hub._voce_src.get("studio") or {})
             and stati(10)[-1] == "dorme", str(stati(10)))
    srv.ferma()
    c.close()


def prova_porta_occupata():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]
    hub = Schermi(cfg_prova(), ArchivioSchermi(str(TMP / "porta.db")))
    t0 = time.monotonic()
    try:
        ServerSchermi(hub, "127.0.0.1", port, attesa_porta_s=0.6).avvia()
        ok = False
    except OSError:
        ok = True
    verifica("porta occupata: OSError chiaro dopo i tentativi", ok
             and 0.5 <= time.monotonic() - t0 < 3, f"{time.monotonic() - t0:.2f} s")
    # load_schermi: capacità guasta, Calliope parte uguale
    from calliope import porte
    from calliope.schermi import load_schermi
    capacita.nuovo_registro()
    cfg = cfg_prova(schermi_porta=port)
    vero = porte.ATTESA_S
    porte.ATTESA_S = 0.3
    try:
        hub2 = load_schermi(cfg, str(TMP / "porta2.db"), log=lambda m: None)
    finally:
        porte.ATTESA_S = vero
    cap = capacita.REGISTRO.get("schermi")
    verifica("load_schermi con porta occupata: None e «guasta»", hub2 is None and cap.stato == "guasta"
             and str(port) in cap.motivo, f"{cap.stato}: {cap.motivo}")
    # Il processo di prima che sta ancora chiudendo (DGX, 02/10 22:59: «Address already in
    # use» dopo calliope aggiorna): la porta si libera dopo un attimo e il server parte
    threading.Timer(0.8, s.close).start()
    righe = []
    hub3 = Schermi(cfg_prova(), ArchivioSchermi(str(TMP / "porta3.db")), log=righe.append)
    t0 = time.monotonic()
    try:
        srv = ServerSchermi(hub3, "127.0.0.1", port, attesa_porta_s=5).avvia()
        partito = srv.port == port
        srv.ferma()
    except OSError as e:
        partito = False
        righe.append(str(e))
    verifica("porta liberata dopo 0,8 s: il server riprova e parte sulla stessa porta",
             partito and 0.7 <= time.monotonic() - t0 < 4
             and any("ancora occupata" in r for r in righe), f"{righe}")
    # Subito dopo l'arresto (pagina collegata: connessione chiusa dal server, TIME_WAIT su
    # Linux) la stessa porta si riapre senza attese
    hub4 = Schermi(cfg_prova(), ArchivioSchermi(str(TMP / "porta4.db")))
    srv = ServerSchermi(hub4, "127.0.0.1", 0).avvia()
    p4 = srv.port
    with socket.create_connection(("127.0.0.1", p4)) as c:
        c.sendall(b"GET /api/salute HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        c.recv(100)
        srv.ferma()
    t0 = time.monotonic()
    srv = ServerSchermi(Schermi(cfg_prova(), ArchivioSchermi(str(TMP / "porta5.db"))),
                        "127.0.0.1", p4, attesa_porta_s=5).avvia()
    verifica("riavvio sulla stessa porta subito dopo l'arresto", srv.port == p4,
             f"{time.monotonic() - t0:.2f} s")
    srv.ferma()


# ─────────────────────────── schede dei tool ───────────────────────────

class BibliotecaFinta:
    citazioni = False

    def cerca(self, domanda, semplice=False):
        from calliope.biblioteca import Passaggio
        return [Passaggio("Giuseppe Garibaldi (Nizza, 4 luglio 1807 – Caprera, 2 giugno 1882) è "
                          "stato un generale, patriota e condottiero italiano.",
                          "Giuseppe Garibaldi", "Wikipedia", 9.0, "finto.zim", "Garibaldi"),
                Passaggio("La spedizione dei Mille…", "Spedizione dei Mille", "Wikipedia", 5.0)]

    def richieste(self, d):
        return set()

    def opzioni(self, d):
        return []

    def testo_voce(self, p, max_caratteri=2500):
        return "Primo paragrafo lungo.\n\nSecondo paragrafo."


class CasaFinta:
    def __init__(self):
        from calliope.casa.base import Entita
        self.e = [Entita("light.cucina", "Luce cucina", "light", area="Cucina", stato="on",
                         attributi={"brightness": 102}),
                  Entita("light.sala", "Luce sala", "light", area="Sala", stato="off"),
                  Entita("sensor.t", "Temperatura sala", "sensor", classe="temperature",
                         area="Sala", stato="20.5", unita="°C")]

    def entita(self):
        return self.e

    def aree(self):
        return {}


def contesto(hub, chi="Dario", livello="amministra", frase="", **kw):
    from calliope.agenda import Agenda
    from calliope.liste import Liste
    db = str(TMP / "tool.db")
    if not hasattr(contesto, "agenda"):
        contesto.agenda = Agenda(db)
        contesto.liste = Liste(db)
    return ToolContext(cfg=hub.cfg if hub else cfg_prova(), speakers=Speakers(),
                       speaker_ctx=SpeakerCtx(chi, livello), speaker=None,
                       agenda=contesto.agenda, liste=contesto.liste, schermi=hub,
                       user_text=frase, **kw)


def prova_schede_tool():
    cfg = cfg_prova()
    hub = Schermi(cfg, ArchivioSchermi(str(TMP / "tool-hub.db")))
    reg = build_registry(biblioteca=True, schermi=True, casa=True)

    def call(nome, args, ctx, livello="amministra"):
        return json.loads(reg.call(nome, args, ctx, livello))

    ctx = contesto(hub)
    out = call("lista_aggiungi", {"cose": "latte e pane"}, ctx)
    s = out.get("scheda") or {}
    verifica("lista_aggiungi: scheda lista «casa»", s.get("tipo") == "lista"
             and s.get("visibilita") == "casa" and s.get("titolo") == "Lista della spesa")
    verifica("lista: voci nuove in evidenza", [v["testo"] for v in s.get("voci", []) if v["nuova"]]
             == ["latte", "pane"], str(s.get("voci")))
    out = call("lista_togli", {"cose": "pane"}, ctx)
    verifica("lista_togli: scheda senza il pane", [v["testo"] for v in out["scheda"]["voci"]]
             == ["latte"] and out["scheda"]["tolti"] == ["pane"])
    out = call("timer_imposta", {"durata": "5 minuti", "nome": "pasta"}, ctx)
    s = out.get("scheda") or {}
    verifica("timer: scheda pubblica con la fine", s.get("tipo") == "timer"
             and s.get("visibilita") == "pubblica"
             and abs(s["timer"][-1]["fine"] - (time.time() + 300)) < 5, str(s.get("timer")))
    out = call("promemoria_imposta", {"testo": "chiamare il dentista", "quando": "domani alle 9"},
               ctx)
    s = out.get("scheda") or {}
    verifica("promemoria: scheda personale con la voce", s.get("visibilita") == "personale"
             and any("dentista" in v["testo"] for v in s.get("voci", [])))
    out = call("agenda_elenca", {}, ctx)
    verifica("agenda_elenca: timer + agenda", [x["tipo"] for x in out.get("schede", [])]
             == ["timer", "promemoria"] if "schede" in out else
             [x["tipo"] for x in out.get("scheda", [])] == ["timer", "promemoria"], str(out.keys()))
    out = call("agenda_annulla", {"cosa": "il timer della pasta"}, ctx)
    sc = out.get("scheda")
    sc = sc if isinstance(sc, list) else [sc]
    verifica("annullare il timer aggiorna la sua scheda («annullato alle …»)",
             sc[0]["tipo"] == "timer" and sc[0]["stato"] == "annullato"
             and sc[0]["timer"][0]["nota"].startswith("annullato alle "), str(sc))
    out = call("calcola", {"espressione": "17*6"}, ctx, "ospite")
    verifica("calcola: scheda pubblica", out.get("scheda", {}).get("risultato") == "102"
             and out["scheda"]["espressione"] == "17×6")
    ctx.biblioteca = BibliotecaFinta()
    out = call("biblioteca_cerca", {"domanda": "chi era Garibaldi?"}, ctx, "ospite")
    s = out.get("scheda") or {}
    verifica("biblioteca: scheda con voce, fonte, passaggio e testo lungo",
             s.get("titolo") == "Giuseppe Garibaldi" and s.get("fonte") == "Wikipedia"
             and "1807" in s.get("passaggio", "") and "Secondo paragrafo" in s.get("testo", "")
             and s.get("altre") == ["Spedizione dei Mille"] and s["visibilita"] == "pubblica")
    # «Approfondisci»: la ricerca fatta dal codice manda la scheda e non la mette nel contesto
    from calliope.tools.builtin import biblioteca_contesto
    hub._ultime.clear()
    testo = biblioteca_contesto(ctx, "chi era Garibaldi?")
    verifica("approfondisci: la scheda va allo schermo, non nel contesto del modello",
             '"scheda"' not in testo and "Secondo paragrafo" not in testo
             and (hub.ultima(hub.mittente(ctx)) or {}).get("tipo") == "biblioteca")
    ctx.casa = CasaFinta()
    out = call("casa_stato", {"cosa": "cosa c'è acceso"}, ctx, "familiare")
    s = out.get("scheda") or {}
    verifica("casa_stato: scheda «casa» con lo stato detto", s.get("tipo") == "casa"
             and s.get("visibilita") == "casa"
             and any(r["nome"] == "Luce cucina" and "40 per cento" in r["stato"]
                     for r in s.get("righe", [])), str(s.get("righe")))
    # Senza schermi niente schede (e nessun costo)
    ctx0 = contesto(None)
    out = call("lista_leggi", {}, ctx0)
    verifica("senza schermi nessuna scheda", "scheda" not in out)
    # Errore del tool: niente scheda
    out = call("timer_imposta", {"durata": "boh"}, ctx)
    verifica("errore del tool: niente scheda", "scheda" not in out)


def prova_identita():
    """Schede con identità (02/10): la stessa cosa cambiata aggiorna la sua scheda e la porta
    in cima, senza doppioni; le cose nuove sono schede nuove; gli aggiornamenti automatici
    (sposta: false) non la spostano; la cronologia rimandata al riaggancio non duplica."""
    from calliope.agenda import Agenda
    from calliope.documenti.servizio import _scheda as scheda_doc
    cfg = cfg_prova()
    hub = Schermi(cfg, ArchivioSchermi(str(TMP / "identita.db")))
    r = hub.archivio.nuova_richiesta()
    hub.archivio.abbina(r["codice"], "studio", proprietario="dario-id", proprietario_nome="Dario")
    sid = hub.abbinati()[0]["id"]
    io = Mittente(persona="dario-id", nome="Dario", livello="amministra", certo=True)
    reg = build_registry(biblioteca=True, schermi=True, casa=True)
    ctx = contesto(hub)
    ctx.agenda = Agenda(str(TMP / "identita-agenda.db"))

    def call(nome, args):
        out = json.loads(reg.call(nome, args, ctx, "amministra"))
        for c in [x for c in (out.get("scheda"), out.get("schede")) if c
                  for x in (c if isinstance(c, list) else [c])]:
            hub.invia(c, io)
        return out

    def chiavi():
        return [c.get("chiave") or c["tipo"] for c in hub.storia(sid)]

    a = call("timer_imposta", {"durata": "5 minuti", "nome": "pasta"})["scheda"]
    call("calcola", {"espressione": "2+2"})
    verifica("timer: identità timer:<id dell'agenda>-<creazione>", re.fullmatch(
        r"timer:\d+-\d+", a.get("chiave", "")), a.get("chiave"))
    call("agenda_annulla", {"cosa": "il timer della pasta"})
    st = hub.storia(sid)
    verifica("timer creato → annullato: una scheda sola, aggiornata e in cima",
             chiavi() == ["calcolo", a["chiave"]] and st[-1]["stato"] == "annullato", str(chiavi()))
    b = call("timer_imposta", {"durata": "10 minuti", "nome": "uova"})["scheda"]
    c = call("timer_imposta", {"durata": "3 minuti", "nome": "tè"})["scheda"]
    verifica("due timer diversi: due schede (anche se SQLite riusa l'id del timer annullato)",
             b["chiave"] != c["chiave"] and a["chiave"] not in (b["chiave"], c["chiave"])
             and chiavi()[-2:] == [b["chiave"], c["chiave"]], str(chiavi()))
    n = len(hub.storia(sid))
    call("calcola", {"espressione": "3*3"})
    call("calcola", {"espressione": "3*3"})
    verifica("calcolo ripetuto: due schede (niente identità)",
             len(hub.storia(sid)) == min(n + 2, 6) and chiavi()[-2:] == ["calcolo", "calcolo"],
             str(chiavi()))
    # Documento creato → modificato: una scheda sola, con l'anteprima nuova, in cima
    doc = {"titolo": "Disdetta", "blocchi": [{"tipo": "paragrafo", "testo": "prima"}]}
    d1 = scheda_doc(doc, "word", "Disdetta.docx", ident=7)
    hub.invia(d1, io)
    hub.invia(schede.calcolo("1+1", "2"), io)
    doc2 = {"titolo": "Disdetta", "blocchi": [{"tipo": "paragrafo", "testo": "dopo"}]}
    hub.invia(scheda_doc(doc2, "word", "Disdetta.docx", "testo cambiato", ident=7), io)
    docs = [x for x in hub.storia(sid) if x.get("chiave") == "documento:7"]
    verifica("documento creato → modificato: una scheda sola, in cima, con l'anteprima nuova",
             len(docs) == 1 and hub.storia(sid)[-1]["chiave"] == "documento:7"
             and docs[0]["blocchi"][0]["testo"] == "dopo", str(chiavi()))
    # Aggiornamento automatico (sposta: false): resta al suo posto
    prima = chiavi()
    pos = prima.index(b["chiave"])
    agg = schede.aggiornamento(dict(b, timer=[dict(b["timer"][0], etichetta="per uova sode")]))
    hub.invia(agg, io)
    verifica("aggiornamento automatico (sposta: false): stessa posizione, nessun doppione",
             chiavi() == prima and pos < len(prima) - 1
             and hub.storia(sid)[pos]["timer"][0]["etichetta"] == "per uova sode", str(chiavi()))
    # Lista: la stessa lista cambiata è la stessa scheda
    call("lista_aggiungi", {"cose": "latte"})
    call("lista_aggiungi", {"cose": "pane"})
    verifica("lista cambiata: una scheda sola (lista:spesa)",
             chiavi().count("lista:spesa") == 1 and chiavi()[-1] == "lista:spesa", str(chiavi()))
    # Timer cambiato («fallo diventare di 20 minuti», 03/10): la stessa scheda, aggiornata con
    # la fine nuova e portata in cima, niente doppioni
    fine_prima = b["timer"][0]["fine"]
    call("timer_imposta", {"durata": "20 minuti", "nome": "uova", "cambia": "imposta"})
    uova = [x for x in hub.storia(sid) if x.get("chiave") == b["chiave"]]
    verifica("timer cambiato: una scheda sola (stessa chiave), in cima, con la fine nuova",
             len(uova) == 1 and chiavi()[-1] == b["chiave"]
             and uova[0]["timer"][0]["fine"] - fine_prima > 500, str(chiavi()))
    # Scadenza: la manda l'agenda, la scheda dello stesso timer diventa «scaduto alle …»
    arrivate = []
    ag = Agenda(str(TMP / "identita-scadenza.db"),
                on_scaduta=lambda it: arrivate.append(schede.timer(it, "scaduto", time.time())))
    tid = ag.add("timer", "per la moka", time.time() + 0.3)
    t0 = time.monotonic()
    while not arrivate and time.monotonic() - t0 < 5:
        time.sleep(0.05)
    verifica("timer scaduto: l'agenda manda la stessa scheda «scaduto alle …»",
             arrivate and arrivate[0]["chiave"].startswith(f"timer:{tid}-")
             and arrivate[0]["timer"][0]["nota"].startswith("scaduto alle "),
             str(arrivate[:1]))
    # Riaggancio: la cronologia rimandata non ha doppioni di identità
    conn, storia = hub.collega(hub.abbinati()[0], asyncio.new_event_loop())
    ks = [x.get("chiave") for x in storia if x.get("chiave")]
    verifica("riaggancio: cronologia senza doppioni", len(ks) == len(set(ks)), str(ks))
    hub.scollega(conn)


def prova_https():
    """La pagina in HTTPS (02/10): http su 127.0.0.1, https in rete con il certificato dei
    satelliti, in rete senza certificato il server non parte (niente http silenzioso), e
    con schermi_senza_tls parte in http con un avviso. «In rete» qui è 127.0.0.2: è ancora
    il loopback (niente firewall) ma non è 127.0.0.1."""
    import ssl as _ssl
    from calliope.satellite.__main__ import _openssl, certificato
    from calliope.satellite.server import ServerSatelliti
    from calliope.schermi import load_schermi, tls, url_schermi
    vuota = TMP / "https-senza"
    vuota.mkdir(exist_ok=True)
    # In rete senza certificato: non parte, «da configurare» con il passo
    capacita.nuovo_registro()
    righe = []
    cfg = cfg_prova(config_dir=str(vuota), schermi_indirizzo="127.0.0.2", schermi_porta=0)
    hub = load_schermi(cfg, str(vuota / "m.db"), log=righe.append)
    cap = capacita.REGISTRO.get("schermi")
    verifica("in rete senza certificato: il server non parte, «da configurare» con il passo",
             hub is None and cap.stato == "da_configurare" and "--certificato" in cap.prossimo_passo
             and "schermi_senza_tls" in cap.prossimo_passo, f"{cap.stato}: {cap.motivo}")
    r = capacita.check_schermi(cfg)
    verifica("da terminale lo stesso", r["stato"] == "da_configurare"
             and "certificato" in r["motivo"], r["motivo"])
    # Scelta esplicita: in chiaro, con l'avviso
    cfg.schermi_senza_tls = True
    hub = load_schermi(cfg, str(vuota / "m.db"), log=righe.append)
    verifica("schermi_senza_tls: parte in http con un avviso",
             hub is not None and hub.url.startswith("http://") and hub.tls is None
             and any("senza HTTPS" in r for r in righe), hub.url if hub else "")
    if hub is not None:
        hub.server.ferma()
        hub.archivio.close()
    if _openssl() is None:
        print("SALTATA IN PARTE: openssl non c'è: salto la parte con il certificato")
        return
    cert_dir = TMP / "https"
    cert_dir.mkdir(exist_ok=True)
    cfg = cfg_prova(config_dir=str(cert_dir), schermi_indirizzo="127.0.0.2", schermi_porta=0)
    verifica("certificato dei satelliti creato", certificato(cfg, out=lambda m: None) == 0)
    verifica("su 127.0.0.1 resta http anche con il certificato",
             tls.modo(cfg_prova(config_dir=str(cert_dir)))[0] == "http"
             and url_schermi(cfg_prova(config_dir=str(cert_dir))).startswith("http://"))
    modo, t = tls.modo(cfg)
    der = _ssl.PEM_cert_to_DER_cert(Path(t["cert"]).read_text(encoding="ascii"))
    verifica("in rete con il certificato: https, con l'impronta e lo SPKI",
             modo == "https" and len(t["spki"]) == 44 and t["spki"].endswith("=")
             and t["spki"] == tls.spki_sha256_b64(der), t["spki"])
    capacita.nuovo_registro()
    hub = load_schermi(cfg, str(cert_dir / "m.db"), log=lambda m: None)
    verifica("load_schermi in rete con il certificato: https", hub is not None
             and hub.url.startswith("https://") and hub.tls and hub.tls["spki"] == t["spki"],
             hub.url if hub else "")
    port = hub.server.port
    with httpx.Client(verify=False, timeout=5) as c:
        r = c.get(f"https://127.0.0.2:{port}/")
        verifica("pagina servita in HTTPS", r.status_code == 200 and "schermo.js" in r.text)
        r = c.post(f"https://127.0.0.2:{port}/api/abbinamento")
        verifica("abbinamento in HTTPS", r.status_code == 200 and len(r.json()["codice"]) == 6)
    srv_der = _ssl.PEM_cert_to_DER_cert(_ssl.get_server_certificate(("127.0.0.2", port)))
    verifica("il certificato del server è quello dei satelliti", srv_der == der)
    try:
        httpx.get(f"http://127.0.0.2:{port}/api/salute", timeout=3)
        ok = False
    except httpx.HTTPError:
        ok = True
    verifica("http sulla porta HTTPS: niente risposta in chiaro", ok)
    t2 = ServerSatelliti._tls_schermi(hub)
    verifica("al satellite: https e impronta (sulla connessione già verificata)",
             t2 == {"https": True, "impronta": t["impronta"]}, str(t2))
    # Il ponte TLS del satellite: il browser parla http con 127.0.0.1, in rete solo TLS
    # verificato con l'impronta; con un'impronta sbagliata non passa niente
    from calliope.schermi.ponte import PonteTLS
    righe = []
    ponte = PonteTLS("127.0.0.2", port, t["impronta"], log=righe.append)
    r = httpx.post(f"{ponte.url}/api/abbinamento", timeout=5)
    verifica("ponte TLS: http su 127.0.0.1 verso la pagina in HTTPS",
             r.status_code == 200 and len(r.json()["codice"]) == 6)
    ponte.ferma()
    falso = PonteTLS("127.0.0.2", port, "AB" * 32, log=righe.append)
    try:
        httpx.post(f"{falso.url}/api/abbinamento", timeout=5)
        passato = True
    except httpx.HTTPError:
        passato = False
    verifica("ponte TLS: impronta diversa, connessione chiusa prima di mandare niente",
             not passato and falso.rifiutate == 1 and any("diverso" in x for x in righe))
    falso.ferma()
    hub.server.ferma()
    hub.archivio.close()
    prova_ponte_flussi(t)


def prova_ponte_flussi(t: dict):
    """Il ponte con i due versi insieme (03/10): fino al 02/10 due thread usavano lo stesso
    SSLSocket (uno in recv, l'altro in sendall), e ogni tanto la richiesta del browser non
    arrivava mai al server (pagina bianca, prova_schermi_pagina 1 volta su 3 sotto carico).
    Qui un server TLS che manda 2 MB mentre ne riceve 1, su 12 connessioni in parallelo, e
    40 scambi brevi con il server che parla per primo: tutto deve arrivare intero."""
    import hashlib
    import ssl as _ssl
    from calliope.schermi.ponte import PonteTLS
    from calliope.tls_sicuro import sicuro
    # Il server finto legge e scrive da due thread: anche lui con SocketTLS, se no il difetto
    # sarebbe il suo (BlockingIOError dal recv a metà di un sendall)
    ctx = sicuro(_ssl.SSLContext(_ssl.PROTOCOL_TLS_SERVER))
    ctx.load_cert_chain(t["cert"], t["chiave"])
    lsock = socket.create_server(("127.0.0.1", 0))
    porta = lsock.getsockname()[1]
    GIU, SU = 2_000_000, 1_000_000
    dati_giu = os.urandom(GIU)

    def leggi(s, n):
        buf = bytearray()
        while len(buf) < n:
            b = s.recv(min(65536, n - len(buf)))
            if not b:
                break
            buf += b
        return bytes(buf)

    def servi(c):
        try:
            s = ctx.wrap_socket(c, server_side=True)
            s.settimeout(20)
            if s.recv(1) == b"P":               # il server parla per primo, poi l'eco
                s.sendall(b"ciao\n")
                s.sendall(s.recv(100))
            else:                               # 2 MB giù mentre ne arriva 1 su
                ricevuti = []
                th = threading.Thread(target=lambda: ricevuti.append(leggi(s, SU)))
                th.start()
                s.sendall(dati_giu)
                th.join(20)
                s.sendall(hashlib.sha256(ricevuti[0] if ricevuti else b"").digest())
            s.close()
        except OSError:
            pass

    def accetta():
        while True:
            try:
                c, _ = lsock.accept()
            except OSError:
                return
            threading.Thread(target=servi, args=(c,), daemon=True).start()

    threading.Thread(target=accetta, daemon=True).start()
    ponte = PonteTLS("127.0.0.1", porta, t["impronta"], log=lambda m: None)
    esiti = []

    def flusso():
        su = os.urandom(SU)
        try:
            with socket.create_connection(("127.0.0.1", ponte.porta_locale), timeout=20) as c:
                c.sendall(b"F")
                th = threading.Thread(target=c.sendall, args=(su,))
                th.start()
                giu = leggi(c, GIU + 32)
                th.join(20)
            esiti.append(giu[:GIU] == dati_giu and giu[GIU:] == hashlib.sha256(su).digest())
        except OSError:
            esiti.append(False)

    def breve(i):
        eco = f"eco {i}".encode()
        try:
            with socket.create_connection(("127.0.0.1", ponte.porta_locale), timeout=20) as c:
                c.sendall(b"P")
                primo = leggi(c, 5)
                c.sendall(eco)
                esiti.append(primo == b"ciao\n" and leggi(c, len(eco)) == eco)
        except OSError:
            esiti.append(False)

    t0 = time.monotonic()
    fili = [threading.Thread(target=flusso) for _ in range(12)]
    fili += [threading.Thread(target=breve, args=(i,)) for i in range(40)]
    for f in fili:
        f.start()
    for f in fili:
        f.join(40)
    verifica("ponte TLS: 12 flussi da 2 MB giù e 1 MB su insieme e 40 scambi brevi, tutto "
             "intero", len(esiti) == 52 and all(esiti),
             f"{sum(esiti)}/52 in {time.monotonic() - t0:.1f} s")
    ponte.ferma()
    lsock.close()


def prova_documento():
    """Anteprima del documento: nel risultato (e quindi da Brain) o, in secondo piano, a file
    pronto con chi l'aveva chiesto."""
    from calliope.documenti import validate
    from calliope.documenti.consegna import LocalDelivery
    from calliope.documenti.servizio import Documenti

    class FakeWriter:
        def __init__(self, delay=0.0):
            self.delay = delay
            self.last_stats = {}

        def write(self, formato, richiesta, detto="", persona=None, titolo=""):
            time.sleep(self.delay)
            if formato == "excel":
                return validate("excel", {"titolo": "Spese di settembre", "fogli": [
                    {"nome": "Spese", "colonne": ["Voce", "Importo (€)"],
                     "righe": [["Affitto", "800"], ["Luce", "90"], ["Gas", "60"]],
                     "totale": True}]})
            return validate(formato, {"titolo": "Disdetta palestra", "blocchi": [
                {"tipo": "paragrafo", "testo": "Roma, 2 ottobre 2026", "allinea": "destra"},
                {"tipo": "paragrafo", "testo": "Spett.le Palestra,"},
                {"tipo": "paragrafo", "testo": "con la presente comunico la disdetta."},
                {"tipo": "paragrafo", "testo": "Cordiali saluti, Dario"}]})

    class pd:   # noqa: N801 — come il modulo delle prove dei documenti
        pass
    pd.FakeWriter = FakeWriter
    cfg = cfg_prova(documenti_attesa_s=2.0)
    hub = Schermi(cfg, ArchivioSchermi(str(TMP / "doc-hub.db")))
    arrivate = []
    hub.invia = lambda card, m, forza=False: arrivate.append((card, m)) or {"schermi": []}
    svc = Documenti(cfg, str(TMP / "doc.db"), writer=pd.FakeWriter(),
                    delivery=LocalDelivery(TMP / "doc"))
    reg = build_registry(documenti=svc.formati, schermi=True)
    ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx("Dario", "amministra"),
                      speaker=None, documenti=svc, schermi=hub,
                      user_text="fammi una tabella Excel delle spese")
    out = json.loads(reg.call("documento_crea", {"formato": "excel", "richiesta": "spese"}, ctx,
                              "amministra"))
    s = out.get("scheda") or {}
    verifica("documento: anteprima personale nel risultato", s.get("tipo") == "documento"
             and s.get("visibilita") == "personale" and s.get("file", "").endswith(".xlsx"))
    verifica("documento: identità documento:<id dell'archivio>",
             s.get("chiave") == f"documento:{out.get('documento')}", s.get("chiave"))
    tab = (s.get("blocchi") or [{}])[0]
    verifica("documento: tabella con il totale calcolato dal programma",
             tab.get("totale") and "950" in " ".join(tab["totale"]), str(tab.get("totale")))
    # Secondo piano: il tool risponde «te lo preparo», la scheda arriva a file pronto
    svc2 = Documenti(cfg_prova(documenti_attesa_s=0.05), str(TMP / "doc2.db"),
                     writer=pd.FakeWriter(delay=0.4), delivery=LocalDelivery(TMP / "doc2"))
    ctx.documenti = svc2
    ctx.cfg = svc2.cfg
    out = json.loads(reg.call("documento_crea", {"formato": "word", "richiesta": "lettera"}, ctx,
                              "amministra"))
    verifica("secondo piano: nessuna scheda nel risultato", out.get("in_preparazione")
             and "scheda" not in out)
    t0 = time.monotonic()
    while not arrivate and time.monotonic() - t0 < 3:
        time.sleep(0.02)
    verifica("secondo piano: anteprima mandata a file pronto, con chi l'ha chiesta",
             arrivate and arrivate[0][0]["tipo"] == "documento"
             and arrivate[0][1].persona == "dario-id" and arrivate[0][1].certo)
    svc.close()
    svc2.close()


def prova_brain():
    """Brain toglie la scheda dal risultato per il modello e la manda subito."""
    cfg = cfg_prova()
    hub = Schermi(cfg, ArchivioSchermi(str(TMP / "brain-hub.db")))
    inviate = []
    vero = hub.invia

    def spia(card, m, forza=False):
        inviate.append((time.perf_counter(), card))
        return vero(card, m, forza)
    hub.invia = spia
    b = Brain.__new__(Brain)
    b.cfg, b.history, b.last_tools = cfg, [], []
    b.tools = build_registry(schermi=True)
    b.tool_ctx = contesto(hub, "Bianca", "familiare")

    class Finto:
        def __init__(self):
            self.giri = 0
            self.messaggi = None
            self.prompt = ""

        def stream(self, messages, tools):
            self.giri += 1
            self.prompt = messages[0]["content"]
            if self.giri == 1:
                yield "calls", [{"id": "call_0", "name": "lista_aggiungi",
                                 "arguments": {"cose": "uova"}}]
            else:
                self.messaggi = messages
                self.t_seconda = time.perf_counter()
                yield "text", "Ho aggiunto le uova."
    b.backend = Finto()
    detto = "".join(b.stream_reply("aggiungi le uova alla lista della spesa", "familiare"))
    tool_msg = next(m for m in b.history if m["role"] == "tool")
    verifica("Brain: la scheda non arriva al modello", "scheda" not in tool_msg["content"]
             and "voci" not in json.loads(tool_msg["content"]))
    verifica("Brain: scheda mandata prima della seconda passata", inviate
             and inviate[0][0] < b.backend.t_seconda and inviate[0][1]["tipo"] == "lista")
    verifica("Brain: registro dei turni con il riassunto della scheda",
             b.last_tools[0].get("schede") == [{"tipo": "lista", "visibilita": "casa",
                                                "schermi": 0, "motivo": "nessuno_schermo"}],
             str(b.last_tools[0].get("schede")))
    verifica("Brain: prompt con schermo_mostra", "schermo_mostra" in b.backend.prompt
             and "schermo_gestisci" in b.backend.prompt)
    verifica("prompt senza schermi non li nomina", "schermo_mostra" not in Config().prompt_for(False))
    verifica("Brain: risposta detta", detto == "Ho aggiunto le uova.", detto)
    # La risposta di prima per «fammelo leggere»
    b.backend = Finto()
    list(b.stream_reply("altro", "familiare"))
    verifica("risposta precedente nel contesto", b.tool_ctx.risposta_precedente.get("testo")
             == "Ho aggiunto le uova.", str(b.tool_ctx.risposta_precedente))

    # Il codice di abbinamento mai nei log: stdout, registro dei turni
    hub2 = Schermi(cfg, ArchivioSchermi(str(TMP / "brain-hub2.db")))
    r = hub2.archivio.nuova_richiesta()
    SEGRETI.extend([r["richiesta"], r["codice"]])
    codice = r["codice"]
    b2 = Brain.__new__(Brain)
    b2.cfg, b2.history, b2.last_tools = cfg, [], []
    b2.tools = build_registry(schermi=True)
    frase = f"abbina lo schermo {codice[:3]} {codice[3:]} al soggiorno"
    b2.tool_ctx = contesto(hub2, "Dario", "amministra", frase)

    class Finto2:
        def stream(self, messages, tools):
            yield "calls", [{"id": "call_0", "name": "schermo_gestisci",
                             "arguments": {"azione": "abbina", "codice": codice,
                                           "stanza": "soggiorno"}}]
    b2.backend = Finto2()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        detto = "".join(b2.stream_reply(frase, "amministra"))
    stampato = out.getvalue()
    verifica("abbinamento a voce: frase pronta", detto == "Fatto: lo schermo del soggiorno è "
             "abbinato.", detto)
    verifica("codice non stampato", codice not in stampato, stampato[:200])
    verifica("codice mascherato negli argomenti del registro",
             b2.last_tools[0]["argomenti"]["codice"] == "******")
    rec = {"testo": frase, "richiesta": frase}
    rec = {k: b2.redact(v) for k, v in rec.items()}
    verifica("codice tolto dal testo per il registro dei turni (anche «123 456»)",
             codice[:3] not in rec["testo"] and "******" in rec["testo"], rec["testo"])
    # Registro dei turni vero, in una cartella temporanea
    from calliope.turnlog import TurnLog
    tl = TurnLog(str(TMP / "registro"), 30)
    tl.write({**rec, "tool": b2.last_tools})
    scritto = "".join(p.read_text(encoding="utf-8") for p in (TMP / "registro").glob("*"))
    verifica("registro dei turni senza il codice", codice not in scritto
             and codice[:3] + " " + codice[3:] not in scritto)


# ─────────────────────────── tool di voce ───────────────────────────

def prova_tool_voce():
    cfg = cfg_prova()
    hub = Schermi(cfg, ArchivioSchermi(str(TMP / "voce.db")))
    hub.url = "http://127.0.0.1:8770"
    reg = build_registry(schermi=True)

    def call(nome, args, chi="Dario", livello="amministra", frase="", gray=False, turno=0,
             come="voce"):
        ctx = contesto(hub, chi, livello, frase)
        ctx.speaker_ctx.from_session = gray
        ctx.turno = turno
        if come is not None:
            ctx.speaker_ctx.identified_by = come
        return json.loads(reg.call(nome, args, ctx, livello)), ctx

    r, _ = call("schermo_mostra", {"cosa": "lista"})
    verifica("nessuno schermo, chi amministra: l'indirizzo e il codice",
             "http://127.0.0.1:8770" in r["risposta_finale"] and r["ok"] is False)
    r, _ = call("schermo_mostra", {"cosa": "lista"}, "Bianca", "familiare")
    verifica("nessuno schermo, familiare: chiedi a chi amministra",
             "chiedi a chi amministra" in r["risposta_finale"])
    r, _ = call("schermo_gestisci", {"azione": "elenca"})
    verifica("elenco vuoto", "Non c'è nessuno schermo" in r["risposta_finale"])
    # Abbinare a voce
    a = hub.archivio.nuova_richiesta()
    SEGRETI.extend([a["richiesta"], a["codice"]])
    r, _ = call("schermo_gestisci", {"azione": "abbina", "codice": a["codice"]})
    verifica("abbina senza stanza: chiede la stanza", r.get("cosa_fare", "").startswith(
        "chiedi in che stanza"), str(r))
    r, ctx = call("schermo_gestisci", {"azione": "abbina", "codice": "12", "stanza": "in soggiorno"},
                  frase=f"abbina lo schermo {a['codice'][:3]} {a['codice'][3:]} al soggiorno")
    verifica("codice storpiato dal modello: preso dalla frase (regola registrata)",
             r["risposta_finale"] == "Fatto: lo schermo del soggiorno è abbinato."
             and "codice_dalla_frase" in ctx.regole, r["risposta_finale"])
    r, _ = call("schermo_gestisci", {"azione": "abbina", "codice": "999999", "stanza": "cucina"})
    verifica("codice sbagliato: frase senza ripetere il codice", "non corrisponde" in
             r["risposta_finale"] and "999999" not in r["risposta_finale"])
    r, _ = call("schermo_gestisci", {"azione": "abbina", "codice": "1", "stanza": "cucina"})
    verifica("senza 6 cifre: le chiede", "6 cifre" in r["risposta_finale"])
    r, _ = call("schermo_gestisci", {"azione": "abbina", "codice": "123456", "stanza": "cucina"},
                "Bianca", "familiare")
    verifica("familiare non può abbinare (NON eseguita)", r.get("ok") is False
             and "NON" in r.get("fatto", ""))
    b = hub.archivio.nuova_richiesta()
    SEGRETI.extend([b["richiesta"], b["codice"]])
    # Abbinare subito come personale vuole la voce e il «sì» nel turno dopo (03/10, analisi
    # di sicurezza S3), come «questo schermo è mio»
    r, _ = call("schermo_gestisci", {"azione": "abbina", "codice": b["codice"], "stanza": "studio",
                                     "personale": True}, come="breve", turno=10)
    verifica("abbinamento personale senza la voce nella frase: rifiutato",
             r.get("ok") is False and "dalla voce" in r["risposta_finale"], r["risposta_finale"])
    r, _ = call("schermo_gestisci", {"azione": "abbina", "codice": b["codice"], "stanza": "studio",
                                     "personale": True}, turno=11)
    verifica("abbinamento personale: prima la domanda", r["risposta_finale"].endswith("?")
             and not hub.archivio.elenco() or all(s["stanza"] != "studio"
                                                  for s in hub.archivio.elenco()),
             r["risposta_finale"])
    r, _ = call("schermo_gestisci", {"azione": "abbina", "personale": True}, turno=12)
    verifica("schermo personale di chi parla", "personale di Dario" in r["risposta_finale"]
             and r["risposta_finale"].startswith("Fatto: lo schermo dello studio"),
             r["risposta_finale"])
    r, _ = call("schermo_gestisci", {"azione": "abbina", "codice": "111111", "stanza": "studio",
                                     "persona": "Gino"})
    verifica("persona sconosciuta", "Non conosco Gino" in r["risposta_finale"])
    # «come mio schermo personale»: il modello manda persona="me" (02/10) → chi parla; ma un
    # nome vero resta quel nome (caso contrario qui sopra, «Gino»)
    b2 = hub.archivio.nuova_richiesta()
    SEGRETI.extend([b2["richiesta"], b2["codice"]])
    r, ctx = call("schermo_gestisci", {"azione": "abbina", "codice": b2["codice"],
                                       "stanza": "camera", "personale": True, "persona": "me"},
                  turno=20)
    r, _ = call("schermo_gestisci", {"azione": "abbina", "personale": True}, turno=21)
    verifica("persona «me» = chi parla", "personale di Dario" in r["risposta_finale"]
             and "persona_io" in ctx.regole, r["risposta_finale"])
    hub.revoca("camera")
    r, _ = call("schermo_gestisci", {"azione": "elenca"})
    verifica("elenco con due schermi", r["risposta_finale"].startswith("Ci sono 2 schermi:")
             and "personale di Dario" not in r["risposta_finale"] and "studio di dario" in
             r["risposta_finale"], r["risposta_finale"])

    # Mostrare (nessuna pagina collegata: «sembra spento»)
    r, _ = call("schermo_mostra", {"cosa": "lista"}, "Bianca", "familiare")
    verifica("lista con gli schermi spenti: lo dice", r["risposta_finale"].startswith(
        "Gli schermi sembrano spenti"), r["risposta_finale"])
    # Collego una connessione finta al soggiorno e allo studio
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    sogg = next(s for s in hub.abbinati() if s["stanza"] == "soggiorno")
    stud = next(s for s in hub.abbinati() if s["stanza"] == "studio")
    c1, _ = hub.collega(sogg, loop)
    c2, _ = hub.collega(stud, loop)
    r, _ = call("schermo_mostra", {"cosa": "lista"}, "Bianca", "familiare")
    verifica("«metti la lista sullo schermo»: soggiorno e studio",
             r["risposta_finale"] == "Ecco, è sugli schermi del soggiorno e dello studio di dario.",
             r["risposta_finale"])
    r, _ = call("schermo_mostra", {"cosa": "promemoria"}, "Bianca", "familiare")
    verifica("agenda di Bianca senza schermo suo: rifiuto chiaro",
             r["risposta_finale"].startswith("È una cosa tua"), r["risposta_finale"])
    r, _ = call("schermo_mostra", {"cosa": "promemoria"}, "Dario", "amministra")
    verifica("agenda di Dario: solo sul suo schermo",
             r["risposta_finale"] == "Ecco, è sullo schermo dello studio di dario.",
             r["risposta_finale"])
    r, _ = call("schermo_mostra", {"cosa": "promemoria"}, "Dario", "familiare", gray=True)
    verifica("zona grigia: niente personale", "Non ho riconosciuto bene" in r["risposta_finale"])
    r, _ = call("schermo_mostra", {"cosa": "lista"}, None, "ospite")
    verifica("ospite: la lista no", r["risposta_finale"].startswith("Questo lo mostro solo"))
    r, _ = call("schermo_mostra", {"cosa": "timer"}, None, "ospite")
    verifica("ospite: i timer sì", r["risposta_finale"].startswith("Ecco"), r["risposta_finale"])
    r, ctx = call("schermo_mostra", {"cosa": "risposta"}, "Bianca", "familiare")
    verifica("«fammelo leggere» senza risposta prima", r["risposta_finale"].startswith(
        "Non ho ancora niente"))
    ctx = contesto(hub, "Bianca", "familiare")
    ctx.risposta_precedente = {"testo": "Domani alle 9 hai il dentista.",
                               "tool": ["appuntamenti_elenca"]}
    r = json.loads(reg.call("schermo_mostra", {"cosa": "risposta"}, ctx, "familiare"))
    verifica("risposta con tool personali: personale (Bianca non ha schermo suo)",
             r["risposta_finale"].startswith("È una cosa tua"), r["risposta_finale"])
    ctx.risposta_precedente = {"testo": "Garibaldi nacque a Nizza nel 1807.",
                               "tool": ["biblioteca_cerca"]}
    r = json.loads(reg.call("schermo_mostra", {"cosa": "risposta"}, ctx, "familiare"))
    verifica("risposta della biblioteca: sugli schermi", r["risposta_finale"].startswith("Ecco"))
    r, _ = call("schermo_mostra", {"cosa": "ultima"}, "Bianca", "familiare")
    verifica("«mostramelo»: l'ultima scheda della persona", r["risposta_finale"].startswith("Ecco"))
    r, _ = call("schermo_mostra", {"cosa": "niente"}, "Bianca", "familiare")
    verifica("«togli dallo schermo»", r["risposta_finale"].startswith("Fatto, ho tolto"))
    r, _ = call("schermo_mostra", {"cosa": "documento"}, "Dario", "amministra")
    verifica("documento senza documenti", r["ok"] is False and "documento" in r["risposta_finale"])
    r, _ = call("schermo_gestisci", {"azione": "scollega", "stanza": "dello studio"})
    verifica("scollega a voce", r["risposta_finale"].startswith("Fatto, ho scollegato lo schermo "
                                                                 "dello studio"), r["risposta_finale"])
    r, _ = call("schermo_gestisci", {"azione": "scollega", "stanza": "garage"})
    verifica("scollega uno schermo che non c'è", r["risposta_finale"].startswith("Non trovo"))
    hub.scollega(c1)
    hub.scollega(c2)
    loop.call_soon_threadsafe(loop.stop)
    # Il codice è un segreto del tool
    verifica("schermo_gestisci: codice tra i segreti", reg.get("schermo_gestisci").segreti
             == ("codice",))
    verifica("livelli: schermo_mostra a tutti, schermo_gestisci solo a chi amministra",
             reg.get("schermo_mostra").levels == frozenset({"ospite", "familiare", "amministra"})
             and reg.get("schermo_gestisci").levels == frozenset({"amministra"}))


def prova_personale_voce():
    """«Questo satellite è il mio schermo personale» e «rendilo condiviso» a voce (03/10):
    solo chi amministra, riconosciuto dalla voce nella frase; prima la domanda (azione in
    sospeso), poi, nella risposta dopo, il cambiamento; il satellite da cui si parla o lo
    schermo nominato; lo schermo del satellite segue subito."""
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.server import Collegamento, ServerSatelliti
    cfg = cfg_prova()
    db = str(TMP / "personale.db")
    hub = Schermi(cfg, ArchivioSchermi(db), log=lambda m: None)
    hub.url = "http://127.0.0.1:8770"
    reg = build_registry(schermi=True)
    srv = ServerSatelliti(cfg_prova(memory_db=db), ArchivioSatelliti(db), log=lambda m: None)
    srv.schermi = hub
    sat, _ = srv.archivio.crea_con_token("studio")
    schermo_sat, _ = hub.archivio.crea_con_token("studio")      # la pagina del satellite
    cucina, _ = hub.archivio.crea_con_token("cucina")           # uno schermo normale
    coll = Collegamento(None, sat, "h")
    coll.schermo_id = schermo_sat["id"]

    def call(args, chi="Dario", livello="amministra", turno=1, come="voce", frase=""):
        ctx = contesto(hub, chi, livello, frase)
        ctx.speaker_ctx.identified_by = come if chi else None
        ctx.turno = turno
        return json.loads(reg.call("schermo_gestisci", args, ctx, livello)), ctx

    def proprietari():
        return (srv.archivio.trova(sat["id"])[0]["proprietario"],
                next(x for x in hub.archivio.elenco() if x["id"] == schermo_sat["id"])
                ["proprietario"])

    r, _ = call({"azione": "personale"})
    verifica("personale senza satellite collegato né stanza: chiede quale schermo",
             r["ok"] is False and "stanza" in r.get("cosa_fare", ""), str(r))
    hub.satelliti = srv
    srv.attivo = coll
    r, ctx = call({"azione": "personale"}, turno=1)
    off = r.get("in_sospeso") or {}
    verifica("«questo satellite è il mio schermo personale»: domanda, niente cambiato",
             r["risposta_finale"] == "Lo schermo dello studio riceverà anche promemoria, "
             "appuntamenti e documenti: lo rendo personale tuo?"
             and proprietari() == (None, None) and off.get("tool") == "schermo_gestisci"
             and off.get("argomenti") == {"azione": "personale", "stanza": "studio"},
             r["risposta_finale"])
    r, _ = call({"azione": "personale"}, turno=1)
    verifica("nella stessa risposta non si conferma da sola",
             "in_sospeso" in r and proprietari() == (None, None))
    r, _ = call({"azione": "personale", "stanza": "studio"}, turno=2)
    verifica("«sì» nella risposta dopo (con la voce: dal 03/10 un «sì» breve non basta): satellite e suo schermo personali, subito",
             r["risposta_finale"].startswith("Fatto: lo schermo dello studio è personale tuo")
             and proprietari() == ("dario-id", "dario-id"),
             f"{r['risposta_finale']} {proprietari()}")
    r, _ = call({"azione": "personale", "persona": "me"}, turno=3)
    verifica("già personale: lo dice, nessuna domanda", "è già personale tuo" in
             r["risposta_finale"] and "in_sospeso" not in r, r["risposta_finale"])
    # Condiviso, troppi turni dopo: la proposta non vale più
    r, _ = call({"azione": "condiviso"}, turno=4)
    verifica("«rendilo condiviso»: domanda che dice cosa perde",
             r["risposta_finale"] == "Lo schermo dello studio non riceverà più promemoria, "
             "appuntamenti e documenti tuoi: lo rendo condiviso?", r["risposta_finale"])
    # Dal 04/10 la proposta vale 3 turni (calliope/conferme.py): 4 dopo non più
    r, _ = call({"azione": "condiviso"}, turno=8)
    verifica("quattro turni dopo: di nuovo la domanda", "in_sospeso" in r
             and proprietari() == ("dario-id", "dario-id"))
    r, _ = call({"azione": "condiviso"}, turno=9)
    verifica("condiviso dopo il sì", r["risposta_finale"] == "Fatto: lo schermo dello studio "
             "è di nuovo condiviso." and proprietari() == (None, None), r["risposta_finale"])
    # Permessi
    r, _ = call({"azione": "personale"}, "Bianca", "familiare", turno=8)
    verifica("familiare: rifiutato, niente cambiato", r.get("ok") is False
             and "NON" in json.dumps(r, ensure_ascii=False) and proprietari() == (None, None),
             str(r)[:160])
    r, _ = call({"azione": "personale"}, None, "ospite", turno=9)
    verifica("ospite: rifiutato, niente cambiato", r.get("ok") is False
             and proprietari() == (None, None), str(r)[:160])
    r, ctx = call({"azione": "personale"}, turno=10, come="sessione")
    verifica("chi amministra ma non riconosciuto dalla voce in quella frase: rifiutato",
             "non ti ho riconosciuto" in r["risposta_finale"] and "in_sospeso" not in r
             and "schermo_proprietario_permesso" in ctx.regole, r["risposta_finale"])
    r, _ = call({"azione": "personale"}, turno=11, come="breve")
    verifica("richiesta con identità breve: rifiutata (e dal 03/10 anche il sì)",
             "non ti ho riconosciuto" in r["risposta_finale"])
    # Uno schermo nominato, per un'altra persona
    r, _ = call({"azione": "personale", "stanza": "in cucina", "persona": "bianca"}, turno=12)
    off = r.get("in_sospeso") or {}
    verifica("schermo nominato per un'altra persona: domanda con il suo nome",
             r["risposta_finale"] == "Lo schermo della cucina riceverà anche promemoria, "
             "appuntamenti e documenti di Bianca: lo rendo personale di Bianca?"
             and off.get("argomenti") == {"azione": "personale", "stanza": "cucina",
                                          "persona": "Bianca"}, r["risposta_finale"])
    r, _ = call(off.get("argomenti") or {}, turno=13)
    cu = next(x for x in hub.archivio.elenco() if x["id"] == cucina["id"])
    verifica("e dopo il sì è di Bianca (il satellite non cambia)",
             cu["proprietario"] == "bianca-id" and proprietari() == (None, None),
             r["risposta_finale"])
    r, _ = call({"azione": "personale", "persona": "Gino"}, turno=14)
    verifica("persona sconosciuta: niente", r["ok"] is False and "Gino" in r["risposta_finale"])
    r, _ = call({"azione": "personale", "stanza": "garage"}, turno=15)
    verifica("schermo che non c'è", r["risposta_finale"].startswith("Non trovo"))
    # Il modello sceglie «abbina» con personale=true ma senza codice: è «personale»
    r, ctx = call({"azione": "abbina", "personale": True}, turno=16,
                  frase="Questo satellite è il mio schermo personale.")
    verifica("abbina senza codice con personale: diventa la domanda di «personale»",
             "lo rendo personale tuo?" in r["risposta_finale"]
             and "schermo_personale_senza_codice" in ctx.regole, r["risposta_finale"])
    r, ctx = call({"azione": "abbina", "personale": True, "stanza": "studio"}, turno=17,
                  frase="abbina lo schermo 123 456 allo studio come mio")
    verifica("caso contrario: con le cifre nella frase resta un abbinamento",
             "schermo_personale_senza_codice" not in ctx.regole
             and "lo rendo" not in r["risposta_finale"], r["risposta_finale"])
    r, ctx = call({"azione": "personale", "codice": "123456", "stanza": "studio",
                   "persona": "chi_parla"}, turno=30,
                  frase="Abbina lo schermo 123 456 come mio schermo personale nello studio.")
    verifica("personale con le 6 cifre: è un abbinamento personale (chi_parla = chi parla)",
             "schermo_personale_con_codice" in ctx.regole and "persona_io" in ctx.regole
             and r["risposta_finale"].endswith("personale tuo?"),
             r["risposta_finale"])
    srv.archivio.close()
    hub.archivio.close()


# ─────────────────────────── capacità e terminale ───────────────────────────

def prova_capacita():
    capacita.nuovo_registro()
    c = capacita.check_schermi(cfg_prova(schermi_enabled=False))
    verifica("capacità: spenti → da configurare", c["stato"] == "da_configurare")
    capacita._SENZA.add("uvicorn")
    c = capacita.check_schermi(cfg_prova())
    verifica("capacità: senza uvicorn → mancante, con il pip giusto", c["stato"] == "mancante"
             and "pip install starlette uvicorn" in c["prossimo_passo"])
    capacita._SENZA.discard("uvicorn")
    cfg = cfg_prova(memory_db=str(TMP / "cap.db"))
    c = capacita.check_schermi(cfg)
    verifica("capacità da terminale, nessuno schermo: il passo con l'indirizzo",
             c["stato"] == "da_configurare" and "http://127.0.0.1:8770" in c["prossimo_passo"]
             and "0.0.0.0" in c["prossimo_passo"], c["prossimo_passo"])
    verifica("il controllo non crea il file della memoria", not Path(cfg.memory_db).exists())
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db))
    hub.url, hub.server_attivo = "http://127.0.0.1:8770", True
    c = capacita.check_schermi(cfg, hub)
    verifica("capacità nel processo, nessuno schermo: da configurare", c["stato"] == "da_configurare")
    a = hub.archivio.nuova_richiesta()
    SEGRETI.extend([a["richiesta"], a["codice"]])
    hub.abbina(a["codice"], "soggiorno")
    c = capacita.check_schermi(cfg, hub)
    verifica("capacità: attiva con uno schermo", c["stato"] == "attiva"
             and c["motivo"].startswith("1 schermo abbinato, 0 collegati"), c["motivo"])
    c = capacita.check_schermi(cfg)
    verifica("capacità da terminale: lo schermo letto in sola lettura", c["stato"] == "attiva")
    hub.server_attivo = False
    verifica("server fermo: guasta", capacita.check_schermi(cfg, hub)["stato"] == "guasta")
    # Prompt: la capacità conta come presente se i tool ci sono
    reg = capacita.Registro()
    reg.segnala("schermi", "da_configurare", "nessuno schermo abbinato")
    names = [s["function"]["name"] for s in build_registry(schermi=True).all_schemas()]
    testo = capacita.testo_prompt(reg, names)
    verifica("prompt: «schermi» tra quelle che funzionano (si abbinano a voce)",
             "funzionano: schermi" in testo, testo)
    testo = capacita.testo_prompt(reg, [n for n in names if not n.startswith("schermo_")])
    verifica("prompt senza i tool: non disponibili", "Non disponibili qui: schermi" in testo)
    hub.archivio.close()


def prova_terminale():
    db = TMP / "term.db"
    # Una copia di calliope.yaml nella cartella temporanea: accanto non ci sono segreti.yaml
    # né calliope.locale.yaml (il controllo della casa guarderebbe segreti.yaml)
    cfg_file = TMP / "calliope.yaml"
    cfg_file.write_text((RADICE / "calliope.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    env = dict(os.environ, PYTHONUTF8="1", CALLIOPE_MEMORY_DB=str(db),
               CALLIOPE_CONFIG=str(cfg_file), PYTHONPATH=str(RADICE),
               CALLIOPE_CONFIG_LOCALE=str(TMP / "nessun-locale.yaml"))

    def run(*args):
        r = subprocess.run([sys.executable, "-m", "calliope.schermi", *args], cwd=TMP,
                           env=env, capture_output=True, text=True, encoding="utf-8")
        return r.returncode, r.stdout + r.stderr

    rc, out = run()
    verifica("terminale: elenco vuoto con il passo", rc == 0 and "Nessuno schermo" in out, out[-200:])
    a = ArchivioSchermi(str(db))
    req = a.nuova_richiesta()
    SEGRETI.extend([req["richiesta"], req["codice"]])
    rc, out = run("--abbina", req["codice"], "--stanza", "cucina")
    verifica("terminale: abbina", rc == 0 and "Abbinato: cucina" in out, out[-200:])
    verifica("terminale: il codice non si ristampa", req["codice"] not in out)
    rc, out = run("--abbina", "000000", "--stanza", "cucina")
    verifica("terminale: codice sbagliato → 1", rc == 1 and "Nessuno schermo in attesa" in out)
    rc, out = run()
    verifica("terminale: elenco", rc == 0 and "cucina" in out)
    rc, out = run("--revoca", "cucina")
    verifica("terminale: revoca", rc == 0 and "Scollegato: cucina" in out
             and a.per_token(req["richiesta"]) is None)
    # calliope.stato regge la capacità nuova (JSON)
    r = subprocess.run([sys.executable, "-m", "calliope.stato", "--json"], cwd=TMP, env=env,
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    try:
        caps = {c["nome"]: c for c in json.loads(r.stdout)["capacita"]}
    except (ValueError, KeyError):
        caps = {}
    verifica("calliope.stato --json: c'è «schermi»", "schermi" in caps, r.stderr[-200:])
    a.close()


def prova_config():
    from calliope.config import SEZIONI, example_yaml
    verifica("configurazione: sezione schermi", SEZIONI.get("schermi", [])[:3] ==
             ["schermi_enabled", "schermi_indirizzo", "schermi_porta"])
    c = Config()
    verifica("predefinito: solo questo PC (127.0.0.1), porta 8770",
             c.schermi_indirizzo == "127.0.0.1" and c.schermi_porta == 8770 and c.schermi_enabled)
    verifica("file d'esempio con la sezione schermi", "\nschermi:\n" in example_yaml())


def prova_log():
    """Nessun token e nessun codice in quello che il processo ha scritto."""
    testo = _cattura.getvalue()
    trovati = [s[:6] + "…" for s in SEGRETI if len(s) >= 6 and s in testo]
    verifica("log di uvicorn senza token né codici", not trovati, str(trovati))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    # Anche lo stdout di questa prova si controlla alla fine (tranne i codici di prova
    # mostrati di proposito: nessuno)
    reale = sys.stdout

    class Doppio(io.TextIOBase):
        def write(self, s):
            _cattura.write(s)
            return reale.write(s)

        def flush(self):
            reale.flush()
    sys.stdout = Doppio()
    sys.stderr_orig = sys.stderr
    prova_archivio()
    prova_visibilita()
    med, mx = prova_server()
    prova_voce()
    prova_voce_stanze()
    prova_voce_stessa_stanza()
    prova_porta_occupata()
    prova_schede_tool()
    prova_identita()
    prova_https()
    prova_documento()
    prova_brain()
    prova_tool_voce()
    prova_personale_voce()
    prova_capacita()
    prova_terminale()
    prova_config()
    prova_log()
    sys.stdout = reale
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'} "
          f"(latenza SSE mediana {med:.2f} ms, massimo {mx:.2f} ms)")
    sys.exit(1 if errori else 0)
