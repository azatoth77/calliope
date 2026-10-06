import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco di «rispondi dove ti ho chiesto» (04/10, calliope/rispondi.py).

Prova vera del 04/10: una domanda scritta nella casella del telefono ha avuto la risposta dalle
casse del portatile (lo studio era il satellite attivo), e «mostramelo sullo schermo» detto dal
telefono è andato allo schermo dello studio. Qui, con il server dei satelliti vero (senza
rete: connessioni finte con lo stesso contratto di `Collegamento`), l'hub degli schermi vero e
il server delle pagine vero per la casella:

- frase scritta dal telefono con lo studio attivo -> il telefono attivo in prestito, la voce
  (UscitaRemota) va al telefono, la risposta scritta sulla scheda del telefono e non sullo
  studio; follow-up a voce sul telefono (il prestito non scade durante il turno), poi l'attivo
  torna lo studio; `prendi` del telefono durante il prestito lo rende suo; `lascia` riporta
  allo studio; il telefono che cade riporta allo studio;
- da uno schermo senza audio in un'altra stanza -> solo scritto (voce muta, niente finestra di
  follow-up); nella stessa stanza del satellite attivo -> detta anche; senza satelliti la
  stanza di `schermi_stanza`;
- `schermo_mostra` dal telefono (scritto o detto) -> per primo lo schermo del telefono, anche
  se è in un'altra stanza; le schede personali solo se lo schermo è di chi parla;
- annuncio di un timer messo dal telefono -> detto dal telefono e la scheda «scaduto» sul suo
  schermo; col telefono scollegato dal satellite attivo; documenti e lavori per persona;
- la casella (/api/scrivi) mette in coda l'id dello schermo.
"""

import shutil
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx

from calliope.config import Config
from calliope.rispondi import Instradamento
from calliope.satellite.server import ServerSatelliti, UscitaRemota
from calliope.schermi import ArchivioSchermi, Schermi, schede
from calliope.schermi.server import ServerSchermi
from calliope.tools.schermi import _schermo_mostra

TMP = Path(tempfile.mkdtemp(prefix="calliope-rispondi-"))
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


def aspetta(cond, max_s=3.0):
    fine = time.monotonic() + max_s
    while time.monotonic() < fine:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


class Coll:
    """Una connessione di satellite finta: quello che ServerSatelliti usa di `Collegamento`."""

    def __init__(self, sid_sat, nome, stanza, schermo_id):
        self.satellite = {"id": sid_sat, "nome": nome, "stanza": stanza}
        self.schermo_id = schermo_id
        self.pronto = True
        self.chiuso = threading.Event()
        self.mandati = []

    @property
    def stanza(self):
        return self.satellite.get("stanza") or ""

    def invia(self, **campi):
        self.mandati.append(campi)
        return True

    def invia_bin(self, dati):
        return True

    def frasi(self):
        return [m["testo"] for m in self.mandati if m.get("tipo") == "frase"]

    def attivo(self):
        return [m["attivo"] for m in self.mandati if m.get("tipo") == "attivo"]


class Voce:
    """Speaker finto: le frasi vanno all'uscita remota vera, se non è muto."""

    def __init__(self, uscita):
        self.uscita = uscita
        self.muto = False
        self.dette = []

    def say(self, testo):
        if not self.muto:
            self.dette.append(testo)
            self.uscita.invia(1, testo, b"\0\0" * 100, 22050)

    def wait(self):
        return True


def ambiente(con_satelliti=True, **cfgkw):
    cfg = Config()
    cfg.memory_db = str(TMP / f"m{time.monotonic_ns()}.db")
    for k, v in cfgkw.items():
        setattr(cfg, k, v)
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db))
    arch = hub.archivio
    studio, _ = arch.crea_con_token("studio", "dario-id", "Dario")
    tel, _ = arch.crea_con_token("telefono", "dario-id", "Dario")
    cucina, _ = arch.crea_con_token("cucina")
    salotto, _ = arch.crea_con_token("studio")          # schermo di stanza, nello studio
    hub._rinfresca()
    s = SimpleNamespace(cfg=cfg, hub=hub, studio=studio, tel=tel, cucina=cucina,
                        salotto=salotto, srv=None)
    if con_satelliti:
        srv = ServerSatelliti(cfg, archivio=None, log=lambda *_: None)
        s.c_studio = Coll(1, "studio", "studio", studio["id"])
        s.c_tel = Coll(2, "telefono di dario", "telefono", tel["id"])
        srv.collegati = [s.c_studio, s.c_tel]
        srv.attivo = s.c_studio
        hub.stanza_corrente = srv.stanza
        hub.satelliti = srv
        s.srv = srv
        s.voce = Voce(UscitaRemota(srv))
    else:
        s.voce = Voce(SimpleNamespace(invia=lambda *a: None))
    s.instr = Instradamento(s.srv, hub, s.voce, cfg)
    return s


def scheda_di(hub, sid, tipo="risposta"):
    return [c for c in hub.storia(sid) if c.get("tipo") == tipo]


class Persona:
    def __init__(self, ident, nome):
        self.id, self.name = ident, nome


def contesto(hub, nome="Dario", livello="familiare", testo="Sono le 8 e 21."):
    speakers = {"Dario": Persona("dario-id", "Dario")}
    sc = SimpleNamespace(current_speaker=nome, current_level=livello, from_session=False)
    return SimpleNamespace(schermi=hub, speaker_ctx=sc,
                           speakers=SimpleNamespace(get=lambda n: speakers.get(n)),
                           risposta_precedente={"testo": testo, "tool": []})


# ─────────────────────────── scritto dal telefono ───────────────────────────

def prova_scritto_dal_telefono():
    e = ambiente()
    item = {"tipo": "scritto", "testo": "che ore sono?", "persona": "dario-id",
            "schermo": e.tel["nome"], "stanza": "telefono", "schermo_id": e.tel["id"]}
    come = e.instr.inizio_scritto(item, 0.0)
    verifica("scritto dal telefono, lo studio attivo: risponde il telefono",
             come == "satellite" and e.srv.attivo is e.c_tel, come)
    verifica("lo studio sa di non essere più attivo, il telefono sì",
             e.c_studio.attivo()[-1:] == [False] and e.c_tel.attivo()[-1:] == [True])
    e.voce.say("Sono le 8 e 21.")
    verifica("la voce va al telefono, non alle casse dello studio",
             e.c_tel.frasi() == ["Sono le 8 e 21."] and e.c_studio.frasi() == [])
    e.instr.risposta_scritta(item, "che ore sono?", "Sono le 8 e 21.")
    r = scheda_di(e.hub, e.tel["id"])
    verifica("la risposta è scritta sulla scheda del telefono, con la domanda",
             len(r) == 1 and r[0]["testo"] == "Sono le 8 e 21."
             and r[0]["domanda"] == "che ore sono?" and r[0]["visibilita"] == "personale", str(r))
    verifica("e non sullo schermo dello studio", scheda_di(e.hub, e.studio["id"]) == [])
    e.instr.risposta_scritta(item, "che ore sono?", "Sono le 8 e 21. Buona giornata.")
    r = scheda_di(e.hub, e.tel["id"])
    verifica("la stessa risposta allungata sostituisce la scheda",
             len(r) == 1 and r[0]["testo"].endswith("Buona giornata."))
    # Fine del turno: la finestra di follow-up tiene il telefono attivo
    awake = time.monotonic() + 0.4
    verifica("dopo il turno la finestra resta quella del turno",
             e.instr.dopo_turno(awake) == awake)
    verifica("finestra di follow-up: il telefono resta attivo", e.srv.attivo is e.c_tel)
    # Follow-up a voce sul telefono: durante il turno il prestito non scade
    time.sleep(0.1)
    e.instr.inizio_voce()
    verifica("follow-up a voce: l'origine è il telefono",
             (e.instr.origine() or {}).get("schermo") == e.tel["id"])
    time.sleep(0.5)
    verifica("durante il turno a voce il telefono resta attivo (finestra passata)",
             e.srv.attivo is e.c_tel)
    e.voce.say("Prego.")
    verifica("anche il follow-up si sente dal telefono", e.c_tel.frasi()[-1] == "Prego.")
    e.instr.dopo_turno(time.monotonic() + 0.2)
    verifica("finita la finestra, l'attivo torna lo studio",
             aspetta(lambda: e.srv.attivo is e.c_studio) and e.c_studio.attivo()[-1] is True
             and e.c_tel.attivo()[-1] is False)
    verifica("l'ascolto sul telefono finisce (evento «cambio»)",
             any(c is e.c_tel and t == "cambio" for c, t, _ in list(e.srv.eventi.queue)))
    verifica("nessun prestito rimasto", e.srv.prestito is None)
    e.voce.say("Un annuncio.")
    verifica("dopo, la voce torna alle casse dello studio", e.c_studio.frasi() == ["Un annuncio."])

    # Il telefono attivo per sua scelta (microfono acceso): niente da restituire
    e.srv.prendi(e.c_tel)
    e.instr.inizio_scritto(item, 0.0)
    e.instr.dopo_turno(time.monotonic() - 1)
    verifica("telefono già attivo per sua scelta: resta attivo dopo lo scritto",
             e.srv.attivo is e.c_tel and e.srv.prestito is None)
    e.srv.prendi(e.c_studio)

    # «Parla» durante il prestito: diventa suo
    e.instr.inizio_scritto(item, 0.0)
    e.srv.prendi(e.c_tel)
    e.instr.dopo_turno(time.monotonic() - 1)
    verifica("«Parla» toccato durante il prestito: il telefono resta attivo",
             e.srv.attivo is e.c_tel and e.srv.prestito is None)
    e.srv.prendi(e.c_studio)

    # La pagina del telefono lascia (microfono spento, finestra finita): torna lo studio
    e.instr.inizio_scritto(item, 0.0)
    e.instr.dopo_turno(time.monotonic() + 30)
    verifica("«lascia» del telefono durante il prestito: torna lo studio",
             e.srv.lascia(e.c_tel) and e.srv.attivo is e.c_studio and e.srv.prestito is None)

    # Il telefono cade durante il prestito
    e.instr.inizio_scritto(item, 0.0)
    e.c_tel.chiuso.set()
    e.srv._togli(e.c_tel)
    verifica("il telefono scollegato durante il prestito: torna lo studio",
             e.srv.attivo is e.c_studio and e.srv.prestito is None)
    e.hub.archivio.close()


# ─────────────────────────── schermi senza audio ───────────────────────────

def prova_senza_audio():
    e = ambiente()
    prima = time.monotonic() - 5
    item = {"tipo": "scritto", "testo": "che ore sono?", "persona": None,
            "schermo": "cucina", "stanza": "cucina", "schermo_id": e.cucina["id"]}
    come = e.instr.inizio_scritto(item, prima)
    verifica("schermo di cucina senza audio, studio attivo: solo scritto",
             come == "muta" and e.voce.muto and e.srv.attivo is e.c_studio, come)
    e.voce.say("Sono le 8 e 21.")
    verifica("niente detto ad alta voce nello studio", e.c_studio.frasi() == [])
    e.instr.risposta_scritta(item, "che ore sono?", "Sono le 8 e 21.")
    r = scheda_di(e.hub, e.cucina["id"])
    verifica("la risposta è scritta sullo schermo della cucina (pubblica: è di stanza)",
             len(r) == 1 and r[0]["visibilita"] == "pubblica")
    verifica("e solo lì", scheda_di(e.hub, e.salotto["id"]) == []
             and scheda_di(e.hub, e.studio["id"]) == [])
    fine = e.instr.dopo_turno(time.monotonic() + 8)
    verifica("dopo: voce di nuovo accesa e nessuna finestra di follow-up aperta nello studio",
             not e.voce.muto and fine == prima)

    item2 = dict(item, schermo="studio", stanza="studio", schermo_id=e.salotto["id"])
    come = e.instr.inizio_scritto(item2, prima)
    verifica("schermo senza audio nella stanza del satellite attivo: detta anche",
             come == "stanza" and not e.voce.muto, come)
    e.voce.say("Ecco.")
    verifica("…dal satellite di quella stanza", e.c_studio.frasi() == ["Ecco."])
    e.instr.dopo_turno(time.monotonic() + 8)
    e.hub.archivio.close()

    # Senza satelliti: conta schermi_stanza
    e = ambiente(con_satelliti=False, schermi_stanza="studio")
    item = {"tipo": "scritto", "schermo_id": e.cucina["id"], "stanza": "cucina"}
    verifica("senza satelliti, schermo di un'altra stanza: solo scritto",
             e.instr.inizio_scritto(item, 0.0) == "muta" and e.voce.muto)
    e.instr.dopo_turno(0.0)
    item = {"tipo": "scritto", "schermo_id": e.salotto["id"], "stanza": "studio"}
    verifica("senza satelliti, schermo della stanza di Calliope: detta",
             e.instr.inizio_scritto(item, 0.0) == "stanza" and not e.voce.muto)
    e.hub.archivio.close()


# ─────────────────────────── schermo_mostra ───────────────────────────

def prova_mostra():
    e = ambiente()
    item = {"tipo": "scritto", "schermo_id": e.tel["id"], "stanza": "telefono"}
    e.instr.inizio_scritto(item, 0.0)
    ctx = contesto(e.hub)
    m = e.hub.mittente(ctx)
    verifica("scritto dal telefono: il mittente viene dallo schermo del telefono",
             m.schermo == e.tel["id"] and m.stanza == "telefono", str(m))
    res = _schermo_mostra(ctx, "risposta")
    ult = e.hub.storia(e.tel["id"])
    verifica("«mostramelo sullo schermo» dal telefono -> schermo del telefono",
             any(c.get("tipo") == "testo" for c in ult)
             and not any(c.get("tipo") == "testo" for c in e.hub.storia(e.studio["id"])),
             res.get("risposta_finale"))
    e.instr.dopo_turno(time.monotonic() - 1)

    # A voce, con il telefono attivo per sua scelta (stanza del telefono «studio» nel caso
    # del 04/10: deve venire prima comunque)
    e.c_tel.satellite["stanza"] = "studio"
    e.srv.prendi(e.c_tel)
    e.instr.inizio_voce()
    m = e.hub.mittente(ctx)
    from calliope.schermi.hub import destinatari
    dest, _ = destinatari("casa", m, e.hub.abbinati(), m.stanza)
    verifica("detto dal telefono: lo schermo del telefono per primo, poi quelli della stanza",
             [s["id"] for s in dest][:1] == [e.tel["id"]] and e.studio["id"] in
             [s["id"] for s in dest], str([s["nome"] for s in dest]))
    dest, _ = destinatari("personale", m, e.hub.abbinati(), m.stanza)
    verifica("una scheda personale: prima il telefono, poi gli altri schermi di Dario",
             [s["id"] for s in dest] == [e.tel["id"], e.studio["id"]],
             str([s["nome"] for s in dest]))
    ospite = e.hub.mittente(contesto(e.hub, nome=None, livello="ospite"))
    dest, motivo = destinatari("personale", ospite, e.hub.abbinati(), "studio")
    verifica("ospite dal telefono: le schede personali restano negate", not dest
             and motivo == "ospite")
    dest, motivo = destinatari("casa", ospite, e.hub.abbinati(), "studio")
    verifica("ospite dal telefono: le schede della casa restano negate", not dest
             and motivo == "ospite")
    e.instr.dopo_turno(time.monotonic() - 1)
    # Uno schermo personale di un altro non riceve le schede personali di chi parla
    e.srv.prendi(e.c_studio)
    altro, _ = e.hub.archivio.crea_con_token("camera", "laura-id", "Laura")
    e.hub._rinfresca()
    m = e.hub.mittente(ctx)
    m.schermo = altro["id"]
    dest, _ = destinatari("personale", m, e.hub.abbinati(), "studio")
    verifica("origine sullo schermo personale di un'altra persona: niente scheda personale lì",
             altro["id"] not in [s["id"] for s in dest])
    e.hub.archivio.close()


# ─────────────────────────── annunci ───────────────────────────

class AgendaFinta:
    def __init__(self):
        self.n = 0

    def add(self, kind, label, due, owner=None, owner_name=None, parent=None):
        self.n += 1
        return self.n


def prova_annunci():
    e = ambiente()
    agenda = AgendaFinta()
    e.instr.avvolgi_agenda(agenda)
    tid = agenda.add("timer", "pasta", 0)          # fuori da un turno: nessuna origine
    verifica("voce aggiunta fuori da un turno: nessuna origine",
             e.instr.origine_di(("agenda", tid)) is None)
    item = {"tipo": "scritto", "schermo_id": e.tel["id"], "stanza": "telefono"}
    e.instr.inizio_scritto(item, 0.0)
    e.instr.persona("dario-id")
    tid = agenda.add("timer", "pasta", 0)
    e.instr.dopo_turno(time.monotonic() - 1)
    verifica("timer messo dal telefono: dopo il turno torna attivo lo studio",
             e.srv.attivo is e.c_studio)
    # Lo scade l'agenda: la scheda va allo schermo del telefono
    m = e.instr.mittente_annuncio(("agenda", tid))
    verifica("la scheda «scaduto» del timer va allo schermo del telefono",
             m.schermo == e.tel["id"] and m.stanza == "telefono")
    cambiato = e.instr.annuncia_verso(("agenda", tid))
    e.voce.say("Il timer pasta è scaduto.")
    verifica("l'annuncio del timer si dice dal telefono",
             cambiato and e.srv.attivo is e.c_tel
             and e.c_tel.frasi()[-1:] == ["Il timer pasta è scaduto."]
             and "Il timer pasta è scaduto." not in e.c_studio.frasi())
    e.instr.dopo_turno(time.monotonic() - 1)
    verifica("dopo l'annuncio torna lo studio", e.srv.attivo is e.c_studio)
    # Documenti e lavori: per persona
    verifica("documento di Dario: annunciato da dove ha chiesto",
             e.instr.annuncia_verso(persona="dario-id") and e.srv.attivo is e.c_tel)
    e.instr.dopo_turno(time.monotonic() - 1)
    verifica("persona sconosciuta: dal satellite attivo",
             not e.instr.annuncia_verso(persona="laura-id") and e.srv.attivo is e.c_studio)
    # Telefono scollegato: dal satellite attivo, come prima
    e.c_tel.chiuso.set()
    verifica("telefono scollegato: l'annuncio resta allo studio",
             not e.instr.annuncia_verso(("agenda", tid)) and e.srv.attivo is e.c_studio)
    e.hub.archivio.close()


# ─────────────────────────── la casella ───────────────────────────

def prova_casella():
    cfg = Config()
    cfg.memory_db = str(TMP / "casella.db")
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db))
    s, token = hub.archivio.crea_con_token("telefono", "dario-id", "Dario")
    hub._rinfresca()
    srv = ServerSchermi(hub, "127.0.0.1", 0).avvia()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{srv.port}", timeout=5) as c:
            a = c.post("/api/accedi", headers={"Authorization": f"Bearer {token}"}).json()
            hub.conversazioni.voce("dario-id", "voce")    # si scrive in conversazione (05/10)
            r = c.post("/api/scrivi", json={"testo": "che ore sono?"},
                       headers={"X-Calliope-Sessione": a["sessione"]})
        it = hub.ingresso.prendi()
        verifica("la casella mette in coda l'id dello schermo (la risposta torna lì)",
                 r.status_code == 200 and it and it.get("schermo_id") == s["id"]
                 and it.get("stanza") == "telefono", str(it))
    finally:
        srv.ferma()
        hub.archivio.close()


def main() -> int:
    try:
        prova_scritto_dal_telefono()
        prova_senza_audio()
        prova_mostra()
        prova_annunci()
        prova_casella()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not errori else f"\n{errori} prove non riuscite.")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
