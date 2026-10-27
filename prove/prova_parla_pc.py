"""Prova a secco di «Parla» sul PC personale (27/10/2026, passo 1b di
docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md, issue #239; area
docs/aree/schermi-telefono.md).

Sul PC la voce la fa il satellite Python, non la pagina: «Parla» sulla pagina dello schermo
personale chiede al server di far ascoltare senza il nome il satellite legato a quello schermo.

1. **Il server dei satelliti** (`ServerSatelliti.tocca`): il satellite legato prende il posto (come
   il telefono che tocca «Parla»: l'altro riceve «attivo: false») e riceve «tocco» con i secondi;
   un satellite non collegato no; uno chiuso no.
2. **Gli schermi** (`Schermi.parla_possibile`, `parla`): solo uno schermo personale legato a un
   satellite, col server dei satelliti; i secondi da `schermi_parla_s`.
3. **L'API** (server degli schermi vero su 127.0.0.1): `/api/accedi` dice `parla` solo sullo
   schermo personale legato; `/api/parla` lo fa (il satellite riceve «tocco»), 403 dallo schermo
   di stanza e da uno personale senza satellite, 409 col satellite scollegato, 401 senza
   sessione, 429 oltre 20 al minuto.
4. **Il satellite** (`Satellite._comando`): «tocco» allunga la finestra senza il nome del Listener
   (`sveglio_fino`, tra 1 e 30 s) e suona l'inizio; il Listener usa la più lontana tra
   `awake_until` e `sveglio_fino` in tutti e tre i punti in cui decide se la frase è per Calliope,
   e una frase cominciata nella finestra vale come il nome (`woke`, punteggio 1: il server non la
   scarta, come il tocco del telefono; revisione della PR #255). Mentre Calliope parla il tocco
   ferma la voce e la veglia finisce con «interruzione» (motivo «tocco») invece di
   «veglia_finita»; senza tocco resta «veglia_finita».

    python prove/prova_parla_pc.py
"""

import json
import re
import shutil
import sys
import tempfile
import threading
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from calliope.config import Config
from calliope.satellite.archivio import ArchivioSatelliti
from calliope.satellite.server import ServerSatelliti
from calliope.schermi import ArchivioSchermi, Schermi
from calliope.schermi.server import ServerSchermi

RADICE = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="calliope-parla-pc-"))
ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


class CollFinto:
    """Un satellite collegato: si guardano solo i messaggi che riceve."""

    def __init__(self, sid, nome):
        self.satellite = {"id": sid, "nome": nome, "stanza": nome}
        self.chiuso = threading.Event()
        self.ricevuti = []
        self.eventi = None

    def invia(self, **campi):
        self.ricevuti.append(campi)
        return True

    def chiudi(self, *a):
        self.chiuso.set()

    def tipi(self):
        return [m.get("tipo") for m in self.ricevuti]


def cfg_prova():
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "memoria.db")
    cfg.satellite_porta = 0
    cfg.audio_modo = "satellite"
    cfg.schermi_parla_s = 6.0
    return cfg


def satelliti():
    cfg = cfg_prova()
    srv = ServerSatelliti(cfg, ArchivioSatelliti(cfg.memory_db), log=lambda m: None)
    cucina, pc = CollFinto(1, "cucina"), CollFinto(5, "studio")
    srv.collegati.extend([cucina, pc])
    srv._attivo = cucina
    verifica("satelliti: «tocco» al satellite legato, che prende il posto",
             srv.tocca(5, 6.0) is True and srv._attivo is pc
             and {"tipo": "tocco", "secondi": 6.0} in pc.ricevuti, json.dumps(pc.ricevuti))
    verifica("satelliti: l'altro lascia il posto (attivo: false)",
             any(m.get("tipo") == "attivo" and m.get("attivo") is False for m in cucina.ricevuti),
             json.dumps(cucina.ricevuti))
    verifica("satelliti: un satellite non collegato no", srv.tocca(9) is False)
    pc.chiuso.set()
    verifica("satelliti: uno chiuso no", srv.tocca(5) is False)
    return cfg


def chiedi(port, percorso, sessione=None, token=None):
    h = {"Content-Type": "application/json"}
    if sessione:
        h["X-Calliope-Sessione"] = sessione
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(f"http://127.0.0.1:{port}{percorso}", headers=h, method="POST", data=b"{}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def server():
    cfg = cfg_prova()
    srv = ServerSatelliti(cfg, ArchivioSatelliti(cfg.memory_db), log=lambda m: None)
    pc = CollFinto(5, "studio")
    srv.collegati.append(pc)
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    hub.satelliti = srv
    web = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
    hub.server = web
    try:
        arch = hub.archivio
        s_pc, t_pc = arch.crea_con_token("studio", proprietario="dario", proprietario_nome="Dario")
        arch.lega_satellite(s_pc["id"], 5)
        _, t_tel = arch.crea_con_token("telefono", proprietario="dario", proprietario_nome="Dario")
        _, t_cucina = arch.crea_con_token("cucina")
        hub._rinfresca()
        port = web.port
        st, a = chiedi(port, "/api/accedi", token=t_pc)
        st2, b = chiedi(port, "/api/accedi", token=t_tel)
        st3, c = chiedi(port, "/api/accedi", token=t_cucina)
        verifica("accedi: «parla» solo sullo schermo personale legato a un satellite",
                 a.get("parla") is True and b.get("parla") is False and c.get("parla") is False,
                 json.dumps([a.get("parla"), b.get("parla"), c.get("parla")]))
        st, r = chiedi(port, "/api/parla", sessione=a["sessione"])
        verifica("parla: il satellite del PC riceve «tocco» coi secondi della configurazione",
                 st == 200 and r.get("ok") and r.get("secondi") == 6.0
                 and {"tipo": "tocco", "secondi": 6.0} in pc.ricevuti, f"{st} {r} {pc.tipi()}")
        st, r = chiedi(port, "/api/parla", sessione=c["sessione"])
        verifica("parla: dallo schermo di stanza no (403)", st == 403, f"{st} {r}")
        st, r = chiedi(port, "/api/parla", sessione=b["sessione"])
        verifica("parla: da uno schermo personale senza satellite no (403)", st == 403, f"{st} {r}")
        st, r = chiedi(port, "/api/parla", sessione="inventata")
        verifica("parla: senza sessione no (401)", st == 401, str(st))
        pc.chiuso.set()
        st, r = chiedi(port, "/api/parla", sessione=a["sessione"])
        verifica("parla: col satellite scollegato lo dice (409)", st == 409 and "collegato" in r.get("errore", ""),
                 f"{st} {r}")
        codici = [chiedi(port, "/api/parla", sessione=a["sessione"])[0] for _ in range(20)]
        verifica("parla: al più 20 tocchi al minuto (poi 429)", 429 in codici, str(codici))
    finally:
        web.ferma()


def satellite():
    from calliope.satellite.client import Satellite as Client
    finto = types.SimpleNamespace(listener=types.SimpleNamespace(sveglio_fino=0.0), suonati=[], traccia=[])
    finto._suona = lambda tipo: finto.suonati.append(tipo)
    prima = time.monotonic()
    Client._comando(finto, {"tipo": "tocco", "secondi": 6})
    resto = finto.listener.sveglio_fino - prima
    verifica("satellite: «tocco» allunga la finestra senza il nome e suona l'inizio",
             5.5 <= resto <= 6.5 and finto.suonati == ["inizio"], f"{resto:.2f} {finto.suonati}")
    Client._comando(finto, {"tipo": "tocco", "secondi": 999})
    verifica("satellite: al più 30 s", finto.listener.sveglio_fino - time.monotonic() <= 30.0)
    # Mentre Calliope parla: la voce si ferma, la veglia finisce con «interruzione»
    fermate = []
    finto2 = types.SimpleNamespace(listener=types.SimpleNamespace(sveglio_fino=0.0), traccia=[],
                                   player=types.SimpleNamespace(ferma=lambda *a: fermate.append(1), saying_name=None),
                                   _stop_veglia=threading.Event(), _veglia_id=41, _suona=lambda t: None)
    Client._comando(finto2, {"tipo": "tocco", "secondi": 6})
    verifica("satellite: il tocco mentre Calliope parla ferma la voce e la veglia",
             fermate == [1] and finto2._stop_veglia.is_set() and finto2._toccata == 41)
    mandati = []
    finto2.listener.watch_for_name = lambda *a, **k: None
    finto2.wake = object()
    finto2._manda = lambda **k: mandati.append(k)
    Client._veglia(finto2, {"id": 41})
    verifica("satellite: la veglia finisce con «interruzione» (motivo «tocco»)",
             mandati == [{"tipo": "interruzione", "id": 41, "motivo": "tocco"}], json.dumps(mandati))
    mandati.clear()
    Client._veglia(finto2, {"id": 42})
    verifica("satellite: senza tocco resta «veglia_finita»", mandati == [{"tipo": "veglia_finita", "id": 42}],
             json.dumps(mandati))
    src = (RADICE / "calliope" / "audio.py").read_text(encoding="utf-8")
    verifica("Listener: la frase cominciata nella finestra di «Parla» vale come il nome",
             re.search(r"self\.started_at <= self\.sveglio_fino\):\s*\n\s*self\.woke, self\.wake_score = True, 1\.0", src)
             is not None)
    usi = len(re.findall(r"max\(awake_until, self\.sveglio_fino\)", src))
    # l'unico confronto con awake_until da solo è quello della finestra di «Parla» stessa
    vecchi = len(re.findall(r"started_at (?:<=|>) awake_until\b(?!\s*\n\s*and self\.started_at <= self\.sveglio_fino)", src))
    verifica("Listener: la finestra più lontana nei tre punti in cui decide, nessun confronto vecchio",
             usi == 3 and vecchi == 0 and "self.sveglio_fino = 0.0" in src, f"{usi} {vecchi}")


def main() -> int:
    try:
        satelliti()
        server()
        satellite()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
