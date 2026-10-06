import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco: uno schermo per satellite, anche dopo i riavvii (05/10/2026).

Sulla DGX ogni ricollegamento di un satellite dopo un riavvio di Calliope (aggiornamento)
faceva nascere un abbinamento di schermo nuovo («studio di dario 2», mai collegato), appena
il token conservato dal satellite non valeva più (pagina abbinata a mano con un codice,
schermo revocato, telefono riabbinato). Qui il server dei satelliti è quello vero
(`ServerSatelliti`, WebSocket in chiaro su 127.0.0.1), l'hub degli schermi è quello vero sullo
stesso file, e il satellite è un client finto del protocollo che conserva il token dello
schermo come `satellite.json`. Ogni «riavvio» chiude server, archivi e hub e li riapre sullo
stesso memoria.db:
- primo collegamento: uno schermo nuovo, legato al satellite; tre riavvii dopo: lo stesso,
  nessun token nuovo, nessun abbinamento in più;
- credenziali perse (token dello schermo vuoto o revocato): lo stesso schermo con un token
  nuovo, il vecchio non vale più;
- schermo di prima del 05/10 (senza legame) ripresentato dal satellite: si lega a lui, niente
  doppione; il token dello schermo di un altro satellite non si prende;
- schermo revocato: al collegamento dopo il satellite ne riceve uno (uno solo);
- revoca del satellite da terminale: toglie anche il suo schermo, non quelli degli altri;
- abbinamenti senza collegamento da più di `schermi_inattivi_giorni`: segnalati negli elenchi
  da terminale, all'avvio e in «calliope stato», mai tolti;
- il satellite vero (`Satellite._apri_schermo`) riapre la pagina solo se il token cambia.
"""

import json
import tempfile
import threading
import time
from pathlib import Path

errori = 0


def ok(msg, cond, extra=""):
    global errori
    print(("ok  " if cond else "ERR ") + msg + (f"  ({extra})" if extra else ""), flush=True)
    if not cond:
        errori += 1


def cfg_prova(tmp: Path):
    from calliope.config import Config
    cfg = Config()
    cfg.config_dir = str(tmp)
    cfg.memory_db = str(tmp / "memoria.db")
    cfg.satellite_porta = 0
    cfg.satellite_indirizzo = "127.0.0.1"
    cfg.satellite_esecutore = False
    cfg.schermi_inattivi_giorni = 7.0
    return cfg


class Calliope:
    """Il lato server di un avvio: archivio dei satelliti, server, hub degli schermi."""

    def __init__(self, cfg):
        from calliope.satellite.archivio import ArchivioSatelliti
        from calliope.satellite.server import ServerSatelliti
        from calliope.schermi.archivio import ArchivioSchermi
        from calliope.schermi.hub import Schermi
        self.log = []
        self.arch = ArchivioSatelliti(cfg.memory_db)
        self.srv = ServerSatelliti(cfg, self.arch, log=self.log.append)
        self.hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
        self.srv.schermi = self.hub
        self.srv.avvia()
        self.srv.avviato.set()
        self.url = f"ws://127.0.0.1:{self.srv.port}"

    def ferma(self):
        self.srv.ferma()
        self.hub.archivio.close()
        self.arch.close()


class SatelliteFinto:
    """Il protocollo del satellite per quel che serve qui: «ciao» con il token, «pronto»,
    «schermo» con il token conservato; il token nuovo si salva come in satellite.json."""

    def __init__(self, token: str):
        self.token = token
        self.cred = {}                     # come satellite.json: schermo_token

    def collega(self, url: str) -> dict:
        """Una sessione: la risposta «schermo» del server (o {} se non arriva)."""
        from websockets.sync.client import connect
        from calliope.satellite import protocollo as P
        with connect(url + P.PERCORSO_AUDIO, open_timeout=5, close_timeout=1,
                     user_agent_header=None) as ws:
            ws.send(P.testo(tipo="ciao", versione=P.VERSIONE, token=self.token, primo=False,
                            nome="prova", esecutore=None))
            m = P.leggi(ws.recv(timeout=5))
            if m.get("tipo") != "benvenuto":
                return {}
            ws.send(P.testo(tipo="pronto", eco=None))
            if not m.get("schermi"):
                return {}
            ws.send(P.testo(tipo="schermo", token=self.cred.get("schermo_token") or ""))
            fine = time.monotonic() + 5
            while time.monotonic() < fine:
                msg = ws.recv(timeout=max(0.1, fine - time.monotonic()))
                if isinstance(msg, bytes):
                    continue
                r = P.leggi(msg)
                if r.get("tipo") == "schermo":
                    if r.get("token"):
                        self.cred["schermo_token"] = r["token"]
                    return r
        return {}


def avvio(cfg, sat: SatelliteFinto) -> tuple[dict, list[dict], list[str]]:
    """Un avvio di Calliope con un collegamento del satellite: risposta, schermi, log."""
    c = Calliope(cfg)
    try:
        r = sat.collega(c.url)
        return r, c.hub.archivio.elenco(), list(c.log)
    finally:
        c.ferma()


def parte_riavvii(tmp: Path):
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.schermi.archivio import ArchivioSchermi
    cfg = cfg_prova(tmp)
    a = ArchivioSatelliti(cfg.memory_db)
    studio, tok_studio = a.crea_con_token("studio", "dario-id", "Dario", ruolo="pc")
    telefono, tok_tel = a.crea_con_token("telefono", "dario-id", "Dario")
    a.close()
    sat = SatelliteFinto(tok_studio)

    r, schermi, log = avvio(cfg, sat)
    ok("primo collegamento: uno schermo nuovo con il token", bool(r.get("token"))
       and len(schermi) == 1, str(schermi))
    sid = schermi[0]["id"] if schermi else None
    ok("lo schermo è legato al satellite e ne eredita il proprietario",
       schermi and schermi[0]["satellite"] == studio["id"]
       and schermi[0]["proprietario"] == "dario-id", str(schermi))
    primo = sat.cred.get("schermo_token")

    for i in range(3):
        r, schermi, log = avvio(cfg, sat)
        ok(f"riavvio {i + 1}: stesso schermo, nessun token nuovo, nessun abbinamento in più",
           r.get("porta") and not r.get("token") and [s["id"] for s in schermi] == [sid],
           f"{r} {[s['nome'] for s in schermi]}")

    # Credenziali del satellite perse (satellite.json rifatto, pagina del telefono ripulita)
    sat.cred.clear()
    r, schermi, log = avvio(cfg, sat)
    ok("credenziali perse: lo stesso schermo con un token nuovo",
       bool(r.get("token")) and r["token"] != primo and [s["id"] for s in schermi] == [sid],
       f"{[s['nome'] for s in schermi]}")
    ok("credenziali perse: il log dice che l'ha ritrovato",
       any("ritrovato" in x for x in log), " / ".join(log))
    arc = ArchivioSchermi(cfg.memory_db)
    ok("credenziali perse: il token vecchio non vale più, il nuovo sì",
       arc.per_token(primo) is None and arc.per_token(r["token"])["id"] == sid)
    arc.close()

    # Token revocato a mano conservato dal satellite: niente doppione, lo stesso schermo
    sat.cred["schermo_token"] = primo
    r, schermi, log = avvio(cfg, sat)
    ok("token vecchio ripresentato: stesso schermo, token nuovo",
       bool(r.get("token")) and [s["id"] for s in schermi] == [sid])

    # Lo schermo di prima del 05/10, senza legame, con il token nel telefono
    arc = ArchivioSchermi(cfg.memory_db)
    vecchio, tok_vecchio = arc.crea_con_token("telefono", "dario-id", "Dario")
    arc.close()
    tel = SatelliteFinto(tok_tel)
    tel.cred["schermo_token"] = tok_vecchio
    r, schermi, log = avvio(cfg, tel)
    s_tel = [s for s in schermi if s["id"] == vecchio["id"]]
    ok("schermo di prima ripresentato: si lega al suo satellite, niente doppione",
       not r.get("token") and len(schermi) == 2 and s_tel
       and s_tel[0]["satellite"] == telefono["id"], str(schermi))
    ok("schermo di prima: il log lo dice", any("legato al satellite" in x for x in log))

    # Il token dello schermo di un altro satellite non si prende
    furbo = SatelliteFinto(tok_tel)
    furbo.cred["schermo_token"] = sat.cred["schermo_token"]
    r, schermi, log = avvio(cfg, furbo)
    ok("token dello schermo di un altro satellite: si usa il proprio",
       bool(r.get("token")) and r["token"] != sat.cred["schermo_token"]
       and len(schermi) == 2, str([s["nome"] for s in schermi]))
    arc = ArchivioSchermi(cfg.memory_db)
    ok("…e lo schermo dello studio resta del suo satellite",
       arc.per_token(sat.cred["schermo_token"])["satellite"] == studio["id"])
    arc.close()

    # Lo schermo revocato: al collegamento dopo il satellite ne riceve uno, uno solo
    c = Calliope(cfg)
    via = c.hub.revoca(sid)
    c.ferma()
    ok("revoca dello schermo dello studio", [s["id"] for s in via] == [sid])
    r, schermi, log = avvio(cfg, sat)
    nuovi = [s for s in schermi if s["satellite"] == studio["id"]]
    ok("dopo la revoca: uno schermo nuovo per lo studio (uno solo)",
       bool(r.get("token")) and len(nuovi) == 1 and nuovi[0]["id"] != sid, str(schermi))
    r, schermi2, log = avvio(cfg, sat)
    ok("…e al riavvio dopo resta quello", not r.get("token") and schermi2 == schermi
       or [s["id"] for s in schermi2] == [s["id"] for s in schermi])
    return cfg, studio, telefono


def parte_revoca_e_inattivi(cfg, studio, telefono):
    from calliope import stato as stato_mod
    from calliope.satellite.__main__ import gestione
    from calliope.schermi import __main__ as schermi_main
    from calliope.schermi.archivio import ArchivioSchermi
    import sqlite3

    # Inattivi: lo schermo del telefono visto 10 giorni fa, uno mai collegato e vecchio
    arc = ArchivioSchermi(cfg.memory_db)
    orfano, _ = arc.crea_con_token("studio", "dario-id", "Dario")
    arc.close()
    db = sqlite3.connect(cfg.memory_db)
    dieci = time.time() - 10 * 86400
    db.execute("UPDATE schermi SET visto = ? WHERE satellite = ?", (dieci, telefono["id"]))
    db.execute("UPDATE schermi SET creato = ?, visto = NULL WHERE id = ?", (dieci, orfano["id"]))
    db.execute("UPDATE satelliti SET visto = ? WHERE id = ?", (dieci, telefono["id"]))
    db.commit()
    db.close()
    arc = ArchivioSchermi(cfg.memory_db)
    vecchi = {s["nome"] for s in arc.inattivi(7)}
    ok("inattivi: visto 10 giorni fa e mai collegato da 10 giorni",
       len(vecchi) == 2 and orfano["nome"] in vecchi, str(vecchi))
    ok("inattivi: con 0 giorni nessun avviso", arc.inattivi(0) == [])
    ok("inattivi: si segnalano e basta (nessuno tolto)", len(arc.elenco()) == 3)
    arc.close()

    out = []
    vero = stato_mod._config
    stato_mod._config = lambda quiet=True: cfg
    try:
        schermi_main.main([], out=out.append)
    finally:
        stato_mod._config = vero
    testo = "\n".join(out)
    ok("elenco degli schermi: ultimo collegamento, satellite e «inattivo»",
       "ULTIMO COLLEGAMENTO" in testo and "<- inattivo" in testo and "mai collegato" in testo
       and "calliope schermi --revoca" in testo, testo[:300])
    out = []
    gestione(["--elenco"], out=out.append, cfg=cfg)
    testo = "\n".join(out)
    ok("elenco dei satelliti: il telefono inattivo segnalato",
       "<- inattivo" in testo and "calliope satellite --revoca" in testo, testo[:300])

    # Avvio: la riga per chi amministra; «calliope stato»: la nota
    from calliope import capacita
    from calliope.schermi.archivio import avviso_inattivi
    c = Calliope(cfg)
    try:
        riga = avviso_inattivi(c.hub.archivio.inattivi(7), "schermi", 7,
                               "calliope schermi --revoca")
        ok("avviso all'avvio: nomi e comando", "senza collegamento da più di 7 giorni" in riga
           and orfano["nome"] in riga, riga)
        c.hub.server_attivo = True
        c.hub.url = "http://127.0.0.1:8770"
        r = capacita.check_schermi(cfg, c.hub)
        ok("calliope stato: la nota sugli schermi inattivi",
           "senza collegamento da più di 7 giorni" in r["motivo"], r["motivo"])
    finally:
        c.ferma()

    # Revoca del satellite: anche il suo schermo, non quello dello studio
    out = []
    rc = gestione(["--revoca", telefono["nome"]], out=out.append, cfg=cfg)
    arc = ArchivioSchermi(cfg.memory_db)
    resto = arc.elenco()
    arc.close()
    ok("revoca del telefono: tolto anche il suo schermo",
       rc == 0 and not any(s["satellite"] == telefono["id"] for s in resto)
       and any("anche il suo schermo" in x for x in out), " / ".join(out))
    ok("revoca del telefono: lo schermo dello studio resta",
       any(s["satellite"] == studio["id"] for s in resto), str(resto))


def parte_client(tmp: Path):
    """Il satellite vero riapre la pagina solo quando il token dello schermo cambia."""
    from calliope.satellite.client import Satellite
    cfg = cfg_prova(tmp)
    cfg.satellite_server = "ws://127.0.0.1:1"
    s = Satellite.__new__(Satellite)
    s.cfg = cfg
    s.cred = {}
    s.cred_path = tmp / "satellite-client.json"
    s.log = lambda m: None
    s._ponte = None
    s._schermo_aperto = False
    pagine = []
    s.apri_schermo = pagine.append
    s._apri_schermo({"porta": 8770, "token": "a" * 43, "https": False})
    ok("client: prima pagina aperta con il token", len(pagine) == 1 and "#t=" + "a" * 43
       in pagine[0])
    s._apri_schermo({"porta": 8770, "token": None, "https": False})
    ok("client: ricollegamento senza token nuovo, la pagina resta", len(pagine) == 1)
    s._apri_schermo({"porta": 8770, "token": "a" * 43, "https": False})
    ok("client: stesso token, la pagina resta", len(pagine) == 1)
    s._apri_schermo({"porta": 8770, "token": "b" * 43, "https": False})
    ok("client: token nuovo, la pagina si riapre con lui", len(pagine) == 2
       and "b" * 43 in pagine[1])
    salvato = json.loads(s.cred_path.read_text(encoding="utf-8"))
    ok("client: il token nuovo è salvato", salvato.get("schermo_token") == "b" * 43)


# Codice d'uscita di una prova saltata per intero (06/10): il runner la conta a parte,
# non come superata (prove/__main__.py)
SALTATA = 77


def main():
    from calliope import capacita
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if not capacita.presente("websockets"):
        print("websockets non c'è: salto la prova")
        return SALTATA
    with tempfile.TemporaryDirectory(prefix="calliope-schermi-sat-",
                                     ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        cfg, studio, telefono = parte_riavvii(tmp)
        parte_revoca_e_inattivi(cfg, studio, telefono)
        parte_client(tmp)
    print(f"\n{'Tutto ok' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
