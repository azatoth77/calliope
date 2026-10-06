import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Prova a secco dell'esecutore remoto del PC (calliope/pc/remoto.py,
calliope/satellite/esecutore.py, RemoteDelivery in calliope/documenti/consegna.py).

Server dei satelliti e satellite veri su 127.0.0.1 (WebSocket, protocollo 2), con un PC finto
sul satellite (prove/pc_finto.py): nessuna azione sul PC vero. Si prova:
- i tool pc_* con l'esecutore remoto: sempre presenti (stesso schema prima e dopo la
  connessione), errore chiaro senza satellite; volume, musica, app (il comando lo sceglie il
  satellite dal suo catalogo), ricerca e apertura di file, permessi (proprietari, ultima
  ricerca della stessa persona), schermo bloccato (anche ricontrollato sul satellite);
- i percorsi non lasciano il satellite (maniglie) e una maniglia inventata non apre niente;
- tempo massimo (la voce non aspetta oltre), richiesta scaduta non eseguita dopo, satellite
  che cade a metà di una chiamata e si ricollega;
- satellite vecchio (protocollo 1) accettato senza esecutore; satellite nuovo davanti a un
  server vecchio: torna da solo al protocollo 1;
- consegna dei documenti: piccolo, grande (20 MB) con checksum, checksum sbagliato, modifica
  dello stesso file, satellite che cade durante l'invio, nessun satellite (il file resta sul
  server e la frase lo dice); Documenti con «La apro?» e pc_apri_file sul satellite;
- misure: giro di una richiesta e velocità della consegna in locale.
"""

import hashlib
import json
import statistics
import tempfile
import threading
import time
from pathlib import Path

from calliope.config import Config
from calliope.documenti import Documenti
from calliope.documenti.consegna import LocalDelivery, RemoteDelivery
from calliope.documenti.formato import validate
from calliope.pc.remoto import PCNonCollegato, RemotePCExecutor
from calliope.satellite import protocollo as P
from calliope.satellite.archivio import ArchivioSatelliti
from calliope.satellite.client import Satellite
from calliope.satellite.esecutore import EsecutoreSatellite
from calliope.satellite.server import ServerSatelliti
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from pc_finto import APP, FILE, FakePC

errori = 0


def ok(msg, cond, extra=""):
    global errori
    print(("ok  " if cond else "ERR ") + msg + (f"  ({extra})" if extra else ""), flush=True)
    if not cond:
        errori += 1


def aspetta(cond, timeout=10.0, passo=0.02) -> bool:
    fine = time.monotonic() + timeout
    while time.monotonic() < fine:
        if cond():
            return True
        time.sleep(passo)
    return bool(cond())


# ───────────────────────── persone e contesto (come prova_pc) ─────────────────────────
class Prof:
    def __init__(self, pid, name, admin=False):
        self.id, self.name, self.admin = pid, name, admin


class Speakers:
    def __init__(self):
        self.p = {"Dario": Prof("dario-id", "Dario", admin=True),
                  "Bianca": Prof("bianca-id", "Bianca"), "Marco": Prof("marco-id", "Marco")}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    def __init__(self, name):
        self.current_speaker, self.from_session = name, False
        prof = Speakers().get(name)
        self.current_level = "amministra" if prof and prof.admin else "familiare"


CFG = Config()
CFG.pc_proprietari = ["Marco"]


def chiama(reg, pcs, nome, args, chi="Dario", user_text=""):
    sc = SpeakerCtx(chi)
    ctx = ToolContext(cfg=CFG, speakers=Speakers(), speaker_ctx=sc, speaker=None, pc=pcs,
                      user_text=user_text)
    return json.loads(reg.call(nome, args, ctx, sc.current_level))


def niente(r) -> bool:
    return r.get("ok") is False and "NON" in str(r.get("fatto", ""))


# ───────────────────────── PC finto del satellite ─────────────────────────
class PCLento(FakePC):
    """Il PC finto con un ritardo regolabile su ogni chiamata (rete o Windows lenti)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.ritardo = 0.0

    def _pausa(self):
        if self.ritardo:
            time.sleep(self.ritardo)

    def volume_leggi(self):
        self._pausa()
        return super().volume_leggi()

    def volume_imposta(self, livello):
        self._pausa()
        return super().volume_imposta(livello)


class Rilevatore:
    def reset(self):
        pass

    def process(self, frame):
        return None


def satellite(cfg_s, ese):
    import prova_satellite as T
    sat = Satellite(cfg_s, sorgente=lambda **kw: T.MicFinto(T.Scena(), **kw),
                    apri_uscita=T.Casse().flusso, log=lambda m: None, rilevatore=Rilevatore(),
                    esecutore=ese)
    threading.Thread(target=sat.esegui, daemon=True).start()
    return sat


def cfg_satellite(tmp: Path, url: str, token: str, nome: str) -> Config:
    import prova_satellite as T
    cfg = T.cfg_prova(tmp, satellite_server=url)
    cfg.satellite_credenziali = str(tmp / f"{nome}.json")
    Path(cfg.satellite_credenziali).write_text(json.dumps({"token": token}), encoding="utf-8")
    return cfg


def principale(tmp: Path):
    import prova_satellite as T
    cfg = T.cfg_prova(tmp)
    arch = ArchivioSatelliti(cfg.memory_db)
    log = []
    srv = ServerSatelliti(cfg, arch, log=log.append).avvia()
    srv.avviato.set()
    url = f"ws://127.0.0.1:{srv.port}"
    _, token = arch.crea_con_token("studio", ruolo="pc")

    remoto = RemotePCExecutor(srv, "portatile", list(APP), 5, timeout_s=2.0)
    pcs = {"portatile": remoto}
    reg = build_registry(pc=pcs, documenti=("excel",))
    schemi_prima = json.dumps(reg.all_schemas(), sort_keys=True)
    nomi = {s["function"]["name"] for s in reg.all_schemas()}
    ok("esecutore remoto: gli 8 tool pc_* ci sono anche senza satellite",
       {"pc_stato", "pc_volume", "pc_media", "pc_luminosita", "pc_apri_app", "pc_blocca",
        "pc_cerca_file", "pc_apri_file"} <= nomi)
    r = chiama(reg, pcs, "pc_volume", {"azione": "alza"})
    ok("senza satellite: errore chiaro, NON eseguita", niente(r) and "non è collegato"
       in r.get("errore", ""), r.get("errore"))

    # ── satellite vecchio (protocollo 1): accettato, senza esecutore ──
    from websockets.sync.client import connect
    with connect(url + P.PERCORSO_AUDIO, compression=None) as ws:
        ws.send(P.testo(tipo="ciao", versione=1, token=token, primo=False))
        m = P.leggi(ws.recv(timeout=5))
        ws.send(P.testo(tipo="pronto", eco=None))
        aspetta(lambda: srv.attivo_pronto() is not None, 3)
        c = srv.attivo_pronto()
        ok("satellite vecchio (protocollo 1): benvenuto, nessun esecutore",
           m.get("tipo") == "benvenuto" and c is not None and c.esecutore is None)
        r = chiama(reg, pcs, "pc_volume", {"azione": "alza"})
        ok("satellite vecchio: il tool dice che va aggiornato", niente(r)
           and "aggiornato" in r.get("errore", ""), r.get("errore"))
        dv = RemoteDelivery(srv, LocalDelivery(tmp / "server"), "portatile")
        d = dv.deliver("Vecchio", "pdf", b"%PDF-1.4 x")
        ok("satellite vecchio: il documento resta sul server e lo si dice",
           not d.get("remoto") and (tmp / "server" / "Vecchio.pdf").is_file()
           and "non riceve documenti" in d.get("dove", ""), d.get("dove"))
    aspetta(lambda: srv.attivo is None, 3)

    # ── satellite nuovo davanti a un server vecchio: torna al protocollo 1 ──
    vere = P.VERSIONI
    P.VERSIONI = (1,)
    try:
        pc_v = PCLento()
        sat_v = satellite(cfg_satellite(tmp, url, token, "vecchio"),
                          EsecutoreSatellite(pc_v, None, "portatile", log=lambda m: None))
        collegato = aspetta(lambda: srv.attivo_pronto() is not None, 8)
        c = srv.attivo_pronto()
        ok("server vecchio: il satellite nuovo si collega con il protocollo 1, senza esecutore",
           collegato and sat_v.versione == 1 and c is not None and c.esecutore is None,
           f"versione {sat_v.versione}")
        sat_v.ferma()
    finally:
        P.VERSIONI = vere
    aspetta(lambda: srv.attivo is None, 3)

    # ── satellite nuovo con l'esecutore (PC finto) ──
    pc = PCLento(volume=40, media=None)
    cartella_sat = tmp / "portatile" / "Documenti" / "Calliope"
    log_sat = []
    ese = EsecutoreSatellite(pc, LocalDelivery(cartella_sat), "portatile", log=log_sat.append)
    cfg_s = cfg_satellite(tmp, url, token, "nuovo")
    sat = satellite(cfg_s, ese)
    ok("satellite con esecutore collegato (protocollo 2)",
       aspetta(lambda: (srv.attivo_pronto() is not None
                        and srv.attivo_pronto().esecutore is not None), 8))
    c = srv.attivo_pronto()
    ok("capacità annunciate nel «ciao»", c is not None and set(c.esecutore["capacita"])
       == set(pc.capacita()) and c.esecutore["file"] and "calcolatrice" in c.esecutore["app"],
       str(c.esecutore if c else None))
    ok("il server lo dice nel log", any("esecutore del PC" in x for x in log), log[-1:])
    ok("prefisso del prompt: gli schemi dei tool non cambiano con il satellite collegato",
       json.dumps(reg.all_schemas(), sort_keys=True) == schemi_prima)

    # ── volume, musica, stato ──
    r = chiama(reg, pcs, "pc_volume", {"azione": "alza"})
    ok("pc_volume alza: il PC del satellite va a 50", pc.volume == 50
       and "50 per cento" in r.get("conferma", ""), str(r))
    r = chiama(reg, pcs, "pc_stato", {"cosa": "volume"})
    ok("pc_stato volume", "50 per cento" in r.get("conferma", ""), r.get("conferma"))
    r = chiama(reg, pcs, "pc_media", {"comando": "pausa"})
    ok("pc_media senza niente in riproduzione: il motivo del satellite, NON eseguita",
       niente(r) and "niente da comandare" in r.get("errore", ""), str(r))
    giri = []
    for _ in range(20):
        t0 = time.perf_counter()
        remoto.volume_leggi()
        giri.append((time.perf_counter() - t0) * 1000)
    ok(f"giro di una richiesta in locale: mediana {statistics.median(giri):.1f} ms, "
       f"massimo {max(giri):.1f} ms", statistics.median(giri) < 100)

    # ── app: il comando lo sceglie il satellite ──
    r = chiama(reg, pcs, "pc_apri_app", {"app": "calcolatrice"})
    ok("pc_apri_app: il satellite avvia il comando del SUO catalogo",
       pc.azioni[-1] == ("avvia", "calc.exe") and "calcolatrice" in r.get("conferma", ""),
       str(pc.azioni[-1:]))
    del pc._app["word"]
    r = chiama(reg, pcs, "pc_apri_app", {"app": "word"})
    ok("app del catalogo del server che il satellite non ha: NON eseguita",
       niente(r) and pc.azioni[-1] != ("avvia", "winword.exe"), r.get("errore"))
    pc._app["word"] = "winword.exe"
    r = c.chiama_pc("avvia", {"app": "cmd.exe /c del"}, 2.0)
    ok("un comando dal server non si esegue mai (solo nomi del catalogo)",
       not r.get("ok") and pc.azioni[-1] != ("avvia", "cmd.exe /c del"), r.get("errore"))
    r = c.chiama_pc("os_system", {"cmd": "x"}, 2.0)
    ok("metodo fuori elenco: rifiutato dal satellite", not r.get("ok")
       and "sconosciuto" in r.get("errore", ""), r.get("errore"))

    # ── file: ricerca, maniglie, apertura, permessi ──
    r = chiama(reg, pcs, "pc_cerca_file", {"testo": "bolletta"})
    ok("pc_cerca_file sul satellite: 3 bollette", len(r.get("risultati") or []) == 3,
       r.get("conferma"))
    tenuti = remoto._ricerche.get("dario-id", (0, []))[1]
    veri = {f["percorso"] for f in FILE}
    ok("i percorsi non arrivano al server (solo maniglie)",
       tenuti and not any(x["percorso"] in veri or "finto" in x["percorso"] for x in tenuti)
       and "finto" not in json.dumps(r))
    r = chiama(reg, pcs, "pc_apri_file", {"risultato": 2})
    ok("pc_apri_file 2: il satellite apre il percorso vero del secondo",
       pc.azioni[-1][0] == "apri" and pc.azioni[-1][1] in veri and r.get("ok"), str(r))
    n = len(pc.azioni)
    pc.ultima_ricerca = None
    r = chiama(reg, pcs, "pc_cerca_file", {"testo": "bolletta"}, chi="Bianca")
    ok("Bianca (non proprietaria): ricerca rifiutata senza chiedere al satellite",
       niente(r) and pc.ultima_ricerca is None and len(pc.azioni) == n)
    r = chiama(reg, pcs, "pc_apri_file", {"risultato": 1}, chi="Marco")
    ok("Marco (proprietario) non apre la ricerca di Dario", not r.get("ok")
       and len(pc.azioni) == n, r.get("errore"))
    try:
        remoto._apri("maniglia-inventata")
        aperto = True
    except RuntimeError:
        aperto = False
    ok("una maniglia inventata non apre niente", not aperto and len(pc.azioni) == n)

    # ── schermo bloccato ──
    pc.locked = True
    r = chiama(reg, pcs, "pc_cerca_file", {"testo": "bolletta"})
    ok("schermo bloccato: niente ricerca", niente(r) and "bloccato" in r.get("motivo", ""))
    r = chiama(reg, pcs, "pc_apri_app", {"app": "calcolatrice"})
    ok("schermo bloccato: niente app", niente(r) and len(pc.azioni) == n)
    r = chiama(reg, pcs, "pc_volume", {"azione": "abbassa"})
    ok("schermo bloccato: il volume sì", r.get("ok") and pc.volume == 40, str(r))
    n = len(pc.azioni)
    r = c.chiama_pc("apri", {"maniglia": tenuti[0]["percorso"]}, 2.0)
    ok("schermo bloccato ricontrollato sul satellite (anche se il server non lo facesse)",
       not r.get("ok") and r.get("bloccato") and len(pc.azioni) == n, str(r))
    r = chiama(reg, pcs, "pc_blocca", {})
    ok("pc_blocca a schermo già bloccato", "già bloccato" in r.get("conferma", ""))
    pc.locked = False

    # ── tempo massimo, richiesta scaduta ──
    remoto.timeout_s = 0.5
    pc.ritardo = 1.0
    t0 = time.monotonic()
    r = chiama(reg, pcs, "pc_volume", {"azione": "alza"})
    dt = time.monotonic() - t0
    ok(f"satellite lento: «non ha risposto in tempo» dopo {dt:.2f} s (tempo massimo 0,5)",
       not r.get("ok") and "in tempo" in r.get("errore", "") and dt < 0.9, str(r))
    t0 = time.monotonic()
    r = chiama(reg, pcs, "pc_volume", {"azione": "alza"})
    dt2 = time.monotonic() - t0
    ok(f"subito dopo un tempo scaduto la chiamata non aspetta di nuovo ({dt2 * 1000:.0f} ms)",
       not r.get("ok") and dt2 < 0.2)
    time.sleep(0.6)                     # il satellite finisce la lettura lenta
    pc.ritardo = 1.5
    remoto._muto_fino = 0.0
    prima = pc.volume
    try:
        remoto.volume_imposta(77)       # resta in coda dietro niente: ritardo 1 s > 0,5
    except TimeoutError:
        pass
    remoto._muto_fino = 0.0
    try:
        remoto.volume_imposta(88)       # in coda dietro la prima: scade prima di partire
    except TimeoutError:
        pass
    aspetta(lambda: ese.scadute >= 1, 4)
    time.sleep(1.2)
    ok("richiesta scaduta in coda: non eseguita più tardi (niente azioni in ritardo)",
       ese.scadute >= 1 and pc.volume != 88, f"volume {prima}→{pc.volume}, "
       f"scadute {ese.scadute}")
    pc.ritardo = 0.0
    remoto._muto_fino = 0.0
    remoto.timeout_s = 2.0

    # ── satellite che cade a metà di una chiamata ──
    pc.ritardo = 1.5
    esito = {}

    def lenta():
        t = time.monotonic()
        esito["r"] = chiama(reg, pcs, "pc_volume", {"azione": "imposta", "valore": "30"})
        esito["s"] = time.monotonic() - t
    th = threading.Thread(target=lenta)
    th.start()
    time.sleep(0.3)
    sat.ws.close()
    th.join(5)
    r = esito.get("r") or {}
    ok(f"satellite caduto a metà: «si è scollegato» dopo {esito.get('s', 0):.2f} s, NON "
       f"eseguita", niente(r) and "scollegato" in r.get("errore", "") and esito["s"] < 1.0,
       str(r))
    pc.ritardo = 0.0
    ok("il satellite si ricollega da solo con l'esecutore",
       aspetta(lambda: (srv.attivo_pronto() is not None
                        and srv.attivo_pronto().esecutore is not None), 10))
    c = srv.attivo_pronto()
    r = chiama(reg, pcs, "pc_volume", {"azione": "imposta", "valore": "35"})
    ok("dopo la riconnessione funziona", r.get("ok") and pc.volume == 35, str(r))

    # ── consegna dei documenti ──
    dv = RemoteDelivery(srv, LocalDelivery(tmp / "server"), "portatile")
    d = dv.deliver("Lettera", "docx", b"PK\x03\x04 lettera finta")
    f = cartella_sat / "Lettera.docx"
    ok("documento piccolo: sul satellite, riferimento «sat:», maniglia per aprirlo",
       d.get("remoto") and d.get("rif") == "sat:Lettera.docx" and f.is_file()
       and f.read_bytes() == b"PK\x03\x04 lettera finta" and d.get("apri"), str(d))
    ok("il riferimento non contiene il percorso del portatile", str(cartella_sat) not in
       json.dumps(d))
    d2 = dv.deliver("Lettera", "docx", b"PK\x03\x04 versione 2", replace=d["rif"],
                    mtime=d["mtime"])
    ok("modifica: stesso file riscritto sul satellite, una copia sola",
       d2.get("rif") == "sat:Lettera.docx" and f.read_bytes() == b"PK\x03\x04 versione 2"
       and len(list(cartella_sat.glob("Lettera*"))) == 1, str(d2))
    grande = os.urandom(20 * 1024 * 1024)
    t0 = time.perf_counter()
    d3 = dv.deliver("Grande", "pdf", grande)
    dt = time.perf_counter() - t0
    g = cartella_sat / "Grande.pdf"
    ok(f"documento grande (20 MB) a pezzi con checksum: {dt:.2f} s, "
       f"{20 / dt:.0f} MB/s in locale", d3.get("remoto") and g.is_file()
       and hashlib.sha256(g.read_bytes()).digest() == hashlib.sha256(grande).digest(), str(d3)[:80])
    r = c.consegna_file("Rovinato", "pdf", b"%PDF dati", sha256="0" * 64, timeout=5)
    ok("checksum sbagliato: rifiutato, nessun file", not r.get("ok") and "rovinato"
       in r.get("errore", "") and not (cartella_sat / "Rovinato.pdf").exists(), str(r))
    r = c.consegna_file("Strano", "exe", b"MZ", timeout=5)
    ok("estensione non ammessa: rifiutata", not r.get("ok")
       and not (cartella_sat / "Strano.exe").exists(), r.get("errore"))
    r = c.consegna_file("../../fuori", "pdf", b"%PDF", timeout=5)
    ok("nome con «..» e barre: resta nella cartella dei documenti",
       r.get("ok") and not (tmp / "portatile" / "fuori.pdf").exists()
       and (cartella_sat / Path(r["nome_file"]).name).is_file(), str(r))
    r = c.consegna_file("Altro", "pdf", b"%PDF y", sostituisci="sat:..\\..\\x.pdf", timeout=5)
    ok("riferimento da sostituire fuori dalla cartella: ignorato (file nuovo)",
       r.get("ok") and (cartella_sat / "Altro.pdf").is_file(), str(r))

    # Documenti vero con la consegna al satellite: «La apro?» e pc_apri_file sul satellite
    class Scrittore:
        last_stats = {}

        def write(self, formato, richiesta, detto="", persona=None, titolo=""):
            return validate("excel", {"titolo": "Spese di ottobre", "fogli": [
                {"nome": "Spese", "colonne": ["Voce", "Importo"],
                 "righe": [["Affitto", "800"], ["Luce", "90"]], "totale": True}]})
    cfg_d = Config()
    svc = Documenti(cfg_d, str(tmp / "doc.db"), writer=Scrittore(), delivery=dv, pcs=pcs,
                    formats=("excel",))
    res = svc.wait(svc.crea("bianca-id", "Bianca", "excel", "le spese"), 10)
    ok("Documenti: file sul portatile, la frase lo dice e chiede «Lo apro?»",
       res and res.get("ok") and "Documenti del portatile" in res.get("frase", "")
       and res.get("frase", "").endswith("apro?")
       and (cartella_sat / "Spese di ottobre.xlsx").is_file(), (res or {}).get("frase"))
    n = len(pc.azioni)
    r = chiama(reg, pcs, "pc_apri_file", {"risultato": 1}, chi="Bianca")
    ok("«aprilo»: Bianca apre il suo documento sul satellite (anche se non è proprietaria)",
       r.get("ok") and len(pc.azioni) == n + 1 and pc.azioni[-1][1].endswith(
           "Spese di ottobre.xlsx"), str(r))

    # Satellite che cade durante l'invio: il file resta sul server
    vero_pezzo = ese.file_pezzo
    caduto = {"n": 0}

    def pezzo_e_cado(ident, dati):
        caduto["n"] += 1
        if caduto["n"] == 2:
            sat.ws.close()
        return vero_pezzo(ident, dati)
    ese.file_pezzo = pezzo_e_cado
    d4 = dv.deliver("Interrotto", "pdf", os.urandom(4 * 1024 * 1024))
    ese.file_pezzo = vero_pezzo
    ok("satellite caduto durante l'invio: file sul server, nessun file a metà sul satellite",
       not d4.get("remoto") and (tmp / "server" / "Interrotto.pdf").is_file()
       and not list(cartella_sat.glob("Interrotto*")) and "scollegato" in d4.get("dove", ""),
       d4.get("dove"))
    aspetta(lambda: srv.attivo_pronto() is not None, 10)

    # Nessun satellite: il documento resta sul server e Calliope lo dice
    sat.ferma()
    ese.chiudi()
    aspetta(lambda: srv.attivo is None, 5)
    res = svc.wait(svc.crea("bianca-id", "Bianca", "excel", "le spese"), 10)
    ok("nessun satellite: il file resta sul server, la frase lo dice, niente «Lo apro?»",
       res and res.get("ok") and "sul server" in res.get("frase", "")
       and "non è collegato" in res.get("frase", "") and "apro?" not in res.get("frase", ""),
       (res or {}).get("frase"))
    r = chiama(reg, pcs, "pc_volume", {"azione": "alza"})
    ok("satellite spento: di nuovo errore chiaro", niente(r) and "non è collegato"
       in r.get("errore", ""), r.get("errore"))
    svc.close()
    srv.ferma()
    arch.close()


def capacita_e_carico(tmp: Path):
    """load_pc con i satelliti, check_pc remoto, prompt stabile."""
    from calliope import capacita
    from calliope.pc import load_pc
    cfg = Config()
    cfg.audio_modo = "satellite"
    cfg.pc_enabled = False
    ok("satellite e pc_enabled spento: nessun esecutore, passo «pc_enabled: true»",
       load_pc(cfg, satelliti=object()) is None
       and "pc_enabled: true" in capacita.check_pc(cfg)["prossimo_passo"])
    cfg.pc_enabled = True

    class SrvFinto:
        def __init__(self):
            self.c = None

        def attivo_pronto(self):
            return self.c
    s = SrvFinto()
    pcs = load_pc(cfg, satelliti=s)
    ok("load_pc con i satelliti: un RemotePCExecutor con il nome del PC",
       isinstance((pcs or {}).get(cfg.pc_nome), RemotePCExecutor))
    ok("check_pc senza satellite collegato: «da configurare» con il passo",
       capacita.check_pc(cfg, s)["stato"] == "da_configurare")
    s.c = type("C", (), {"esecutore": {"capacita": ["volume"], "app": [], "file": True}})()
    r = capacita.check_pc(cfg, s)
    ok("check_pc con l'esecutore: attiva, con le capacità", r["stato"] == "attiva"
       and "volume" in r["motivo"], r["motivo"])
    reg = capacita.Registro()
    reg.segnala("pc", "da_configurare", "non collegato")
    testo = capacita.testo_prompt(reg, ["pc_volume"])
    ok("prompt: il PC conta come presente se i tool ci sono (satellite che va e viene)",
       "controllo del computer" in testo.split("Non disponibili")[0], testo[:120])
    s.c = type("C", (), {"esecutore": None})()       # satellite vecchio
    try:
        RemotePCExecutor(s, "portatile")._chiama("volume_leggi")
        errore = None
    except PCNonCollegato as e:
        errore = str(e)
    ok("RemotePCExecutor senza esecutore: PCNonCollegato", errore and "aggiornato" in errore,
       errore)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        import websockets  # noqa: F401
    except ImportError:
        print("websockets non installato: salto")
        sys.exit(77)    # saltata: il runner la conta a parte
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        capacita_e_carico(Path(d))
        principale(Path(d))
    print("\nTutto ok" if not errori else f"\n{errori} errori")
    sys.exit(1 if errori else 0)
