import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Gli schermi a voce con il modello vero (Ollama) e il server delle schede vero.

1. Frasi come dette a voce, con il server acceso su una porta libera di 127.0.0.1 e una
   pagina finta collegata in SSE: abbinamento («abbina lo schermo 481 207 al soggiorno»,
   anche personale), «quali schermi ci sono?», le schede automatiche dei tool (lista, timer,
   calcolo, biblioteca finta), «mostramelo sullo schermo», «metti la lista sullo schermo»,
   «fammi vedere i miei promemoria», «togli tutto dallo schermo», «scollega lo schermo»; un
   familiare che prova ad abbinare; distrattori con la parola «schermo» che sono del PC
   («abbassa la luminosità dello schermo», «blocca lo schermo») e «che ore sono?».
2. Latenza: le stesse frasi con gli schermi spenti (nessun tool degli schermi, nessun server)
   e accesi (tool, server e una pagina collegata): la prima frase non deve peggiorare.

    python prove\\prova_schermi_ollama.py        # 2 giri
    python prove\\prova_schermi_ollama.py 1      # 1 giro
"""

import json
import re
import statistics
import tempfile
import threading
import time
from pathlib import Path

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ora_giusta import ora_o_tool  # noqa: E402  (03/10: l'ora giusta senza tool vale)
from calliope.agenda import Agenda
from calliope.brain import Brain
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from calliope.liste import Liste
from calliope.schermi import ArchivioSchermi, Schermi
from calliope.schermi.server import ServerSchermi
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from prove.pc_finto import FakePC

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


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
    def __init__(self, name, level):
        self.current_speaker, self.current_level, self.from_session = name, level, False
        self.identified_by = "voce" if name else None


class BibliotecaFinta:
    citazioni = False

    def cerca(self, domanda, semplice=False):
        from calliope.biblioteca import Passaggio
        return [Passaggio("Giuseppe Garibaldi (Nizza, 4 luglio 1807 – Caprera, 2 giugno 1882) è "
                          "stato un generale, patriota e condottiero italiano, detto «l'Eroe dei "
                          "due mondi».", "Giuseppe Garibaldi", "Wikipedia", 9.0)]

    def richieste(self, d):
        return set()

    def opzioni(self, d):
        return []

    def testo_voce(self, p, max_caratteri=2500):
        return p.testo


class Pagina:
    """Una pagina collegata in SSE: conta le schede che arrivano."""

    def __init__(self, base, token):
        a = httpx.post(f"{base}/api/accedi", headers={"Authorization": f"Bearer {token}"}).json()
        self.schede = []
        self.t = threading.Thread(target=self._run, args=(base, a["sessione"]), daemon=True)
        self.t.start()

    def _run(self, base, sess):
        ev = None
        try:
            with httpx.stream("GET", f"{base}/eventi?sessione={sess}", timeout=None) as r:
                for line in r.iter_lines():
                    if line.startswith("event: "):
                        ev = line[7:]
                    elif line.startswith("data: ") and ev == "scheda":
                        self.schede.append(json.loads(line[6:]))
                    elif ev == "revocato":
                        return
        except Exception:  # noqa: BLE001 — server fermato a fine prova
            pass


def pagina_nuova(base):
    r = httpx.post(f"{base}/api/abbinamento").json()
    return r["codice"], r["richiesta"]


def spaziato(codice, modo):
    return {"gruppi": f"{codice[:3]} {codice[3:]}", "cifre": " ".join(codice),
            "unito": codice}[modo]


def esegui(b, frase, livello):
    t0 = time.perf_counter()
    primo, parti = None, []
    for pezzo in b.stream_reply(frase, livello):
        if primo is None and pezzo.strip():
            primo = time.perf_counter() - t0
        parti.append(pezzo)
    return "".join(parti).strip(), primo or 0.0, time.perf_counter() - t0


# ─────────────────────────── 1. frasi ───────────────────────────
righe = []
for giro in range(1, GIRI + 1):
    tmp = Path(tempfile.mkdtemp(prefix="calliope_schermi_ollama_"))
    cfg = Config()
    cfg.memory_db = str(tmp / "memoria.db")
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db))
    srv = ServerSchermi(hub, "127.0.0.1", 0).avvia()
    base = f"http://127.0.0.1:{srv.port}"
    hub.url = base
    agenda, liste = Agenda(cfg.memory_db), Liste(cfg.memory_db)
    pc = FakePC(volume=40, luminosita=80)
    # Con i tool degli agenti, come in Calliope con dgx.yaml (02/10)
    reg = build_registry(pc={"portatile": pc}, documenti=FORMATI, biblioteca=True, schermi=True,
                         agenti=True)
    pagine = {}
    stato = {"codici": {}}
    # Un satellite collegato nell'ingresso, con il suo schermo: «questo satellite è il mio
    # schermo personale» (03/10)
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.server import Collegamento, ServerSatelliti
    sats = ServerSatelliti(cfg, ArchivioSatelliti(cfg.memory_db), log=lambda m: None)
    sats.schermi, hub.satelliti = hub, sats
    sat_ingresso, _ = sats.archivio.crea_con_token("ingresso")
    sats.attivo = Collegamento(None, sat_ingresso, "h")
    sats.attivo.schermo_id = hub.archivio.crea_con_token("ingresso")[0]["id"]

    def proprietario_satellite():
        return sats.archivio.trova(sat_ingresso["id"])[0]["proprietario"]

    def nuovo_codice(nome):
        codice, richiesta = pagina_nuova(base)
        stato["codici"][nome] = (codice, richiesta)
        return codice

    # (sessione, chi, livello, frase (funzione), tool atteso, controllo(risposta, last_tools))
    def abbinato(stanza):
        return lambda r, t: any(s["stanza"] == stanza for s in hub.abbinati())

    def scheda_arrivata(tipo):
        def ok(r, t):
            time.sleep(0.15)
            return any(c["tipo"] == tipo for p in pagine.values() for c in p.schede[-3:])
        return ok

    CASI = [
        ("a", "Dario", "amministra",
         lambda: f"Abbina lo schermo {spaziato(nuovo_codice('soggiorno'), 'gruppi')} al soggiorno.",
         "schermo_gestisci", abbinato("soggiorno")),
        ("a", "Dario", "amministra",
         lambda: f"Abbina lo schermo {spaziato(nuovo_codice('studio'), 'cifre')} come mio "
                 f"schermo personale nello studio.",
         "schermo_gestisci",
         # Dal 03/10 (analisi di sicurezza) l'abbinamento personale chiede prima conferma
         lambda r, t: r.rstrip().endswith("?") and not any(
             s["stanza"] == "studio" for s in hub.abbinati())),
        ("a", "Dario", "amministra", lambda: "Sì, abbinalo pure.", "schermo_gestisci",
         lambda r, t: any(s["stanza"] == "studio" and s["proprietario"] == "dario-id"
                          for s in hub.abbinati())),
        ("b", "Dario", "amministra", lambda: "Quali schermi ci sono?", "schermo_gestisci",
         lambda r, t: "soggiorno" in r and "studio" in r),
        ("c", "Bianca", "familiare", lambda: "Aggiungi il latte alla lista della spesa.",
         "lista_aggiungi", scheda_arrivata("lista")),
        ("c", "Bianca", "familiare", lambda: "Mettimi la lista della spesa sullo schermo.",
         "schermo_mostra", lambda r, t: r.startswith("Ecco")),
        ("d", "Dario", "amministra", lambda: "Metti un timer di 5 minuti.", "timer_imposta",
         scheda_arrivata("timer")),
        ("d", "Dario", "amministra", lambda: "Mostramelo sullo schermo.", "schermo_mostra",
         lambda r, t: r.startswith("Ecco")),
        ("e", "Dario", "amministra", lambda: "Quanto fa 17 per 6?", "calcola",
         scheda_arrivata("calcolo")),
        ("e", "Dario", "amministra", lambda: "Fammelo vedere sullo schermo.", "schermo_mostra",
         lambda r, t: r.startswith("Ecco")),
        ("f", None, "ospite", lambda: "Chi era Garibaldi?", "biblioteca_cerca",
         scheda_arrivata("biblioteca")),
        ("g", "Dario", "amministra", lambda: "Ricordami domani alle 9 di chiamare il dentista.",
         "promemoria_imposta", lambda r, t: True),
        ("g", "Dario", "amministra", lambda: "Fammi vedere i miei promemoria sullo schermo.",
         "schermo_mostra",
         lambda r, t: r == "Ecco, è sullo schermo dello studio di dario."),
        ("g2", "Dario", "amministra", lambda: "Mettimi sullo schermo i miei appuntamenti.",
         "schermo_mostra",
         lambda r, t: r == "Ecco, è sullo schermo dello studio di dario."),
        ("h", "Dario", "amministra", lambda: "Togli tutto dallo schermo.", "schermo_mostra",
         lambda r, t: any(x["nome"] == "schermo_mostra" and x["argomenti"].get("cosa") == "niente"
                          for x in t)),
        ("i", "Bianca", "familiare",
         lambda: f"Abbina lo schermo {spaziato(nuovo_codice('cucina'), 'gruppi')} alla cucina.",
         ("schermo_gestisci", None),
         lambda r, t: not any(s["stanza"] == "cucina" for s in hub.abbinati())),
        # Distrattori: «schermo» del PC
        ("l", "Dario", "amministra", lambda: "Abbassa la luminosità dello schermo.",
         "pc_luminosita", lambda r, t: not any(x["nome"].startswith("schermo_") for x in t)),
        ("l", "Dario", "amministra", lambda: "Blocca lo schermo.", "pc_blocca",
         lambda r, t: not any(x["nome"].startswith("schermo_") for x in t)),
        ("m", "Bianca", "familiare", lambda: "Che ore sono?", "ora_attuale",
         lambda r, t: not any(x["nome"].startswith("schermo_") for x in t)),
        ("n", "Dario", "amministra", lambda: "Scollega lo schermo dello studio.",
         "schermo_gestisci",
         lambda r, t: not any(s["stanza"] == "studio" for s in hub.abbinati())),
        # «Questo schermo è mio» dal satellite (03/10): domanda, poi il sì; il no; i permessi
        ("p", "Dario", "amministra", lambda: "Questo satellite è il mio schermo personale.",
         "schermo_gestisci",
         lambda r, t: r.endswith("?") and proprietario_satellite() is None),
        ("p", "Dario", "amministra", lambda: "Sì.", "schermo_gestisci",
         lambda r, t: proprietario_satellite() == "dario-id"),
        ("q", "Dario", "amministra", lambda: "Rendi di nuovo condiviso questo schermo.",
         "schermo_gestisci",
         lambda r, t: r.endswith("?") and proprietario_satellite() == "dario-id"),
        ("q", "Dario", "amministra", lambda: "No, lascia stare.", ("schermo_gestisci", None),
         lambda r, t: proprietario_satellite() == "dario-id"),
        ("q2", "Dario", "amministra", lambda: "Rendi condiviso lo schermo di questo satellite.",
         "schermo_gestisci", lambda r, t: r.endswith("?")),
        ("q2", "Dario", "amministra", lambda: "Sì, grazie.", "schermo_gestisci",
         lambda r, t: proprietario_satellite() is None),
        ("r", "Bianca", "familiare", lambda: "Questo satellite è il mio schermo personale.",
         ("schermo_gestisci", None), lambda r, t: proprietario_satellite() is None),
        ("s", None, "ospite", lambda: "Questo schermo è mio: rendilo personale.",
         ("schermo_gestisci", None), lambda r, t: proprietario_satellite() is None),
    ]
    brains = {}
    for sessione, chi, livello, frase_fn, atteso, controllo in CASI:
        frase = frase_fn()
        key = (sessione, chi)
        if key not in brains:
            ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(chi, livello),
                              speaker=None, agenda=agenda, liste=liste, pc={"portatile": pc},
                              biblioteca=BibliotecaFinta(), schermi=hub)
            brains[key] = Brain(cfg, reg, ctx)
        b = brains[key]
        risposta, primo, totale = esegui(b, frase, livello)
        # Le pagine si collegano appena abbinate (come farebbe il browser)
        for nome, (codice, richiesta) in list(stato["codici"].items()):
            if nome not in pagine and hub.archivio.per_token(richiesta):
                pagine[nome] = Pagina(base, richiesta)
                time.sleep(0.1)
        tools = [t["nome"] for t in b.last_tools]
        if isinstance(atteso, tuple):
            ok_tool = any(t in atteso for t in tools) or (None in atteso and not tools)
        else:
            ok_tool = atteso in tools or ora_o_tool(atteso, tools, risposta)
        try:
            ok_stato = bool(controllo(risposta, b.last_tools))
        except Exception as e:  # noqa: BLE001
            ok_stato, risposta = False, f"{risposta} [controllo: {e}]"
        argomenti = "; ".join(f"{t['nome']}({', '.join(f'{k}={v!r}' for k, v in t['argomenti'].items())})"
                              for t in b.last_tools) or "—"
        # La frase con il codice non si stampa intera: il codice è un segreto
        detta = re.sub(r"\d(?: ?\d){5}", "******", b.redact(frase))
        verifica(f"[{giro}] {chi or 'ospite'}: «{detta}» → {argomenti}", ok_tool and ok_stato,
                 f"{primo:.2f}/{totale:.2f}s  {risposta[:140]!r}")
        righe.append((giro, frase, ok_tool and ok_stato, primo, totale))
    srv.ferma()

prime = sorted(r[3] for r in righe)
print(f"\nfrasi: riuscite {sum(r[2] for r in righe)}/{len(righe)}, prima frase mediana "
      f"{statistics.median(prime):.2f}s, massimo {prime[-1]:.2f}s")

# ─────────────────────────── 2. latenza: schermi spenti e accesi ───────────────────────────
FRASI = ["Aggiungi il pane alla lista della spesa.", "Metti un timer di 3 minuti.",
         "Quanto fa 23 per 7?", "Chi era Garibaldi?", "Che ore sono?"]


def blocco(acceso: bool, ripetizioni: int) -> list[float]:
    tmp = Path(tempfile.mkdtemp(prefix="calliope_schermi_lat_"))
    cfg = Config()
    cfg.memory_db = str(tmp / "memoria.db")
    agenda, liste = Agenda(cfg.memory_db), Liste(cfg.memory_db)
    pc = FakePC(volume=40, luminosita=80)
    hub = srv = None
    if acceso:
        hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db))
        srv = ServerSchermi(hub, "127.0.0.1", 0).avvia()
        base = f"http://127.0.0.1:{srv.port}"
        codice, richiesta = pagina_nuova(base)
        hub.abbina(codice, "soggiorno")
        pagina = Pagina(base, richiesta)
        time.sleep(0.2)
    reg = build_registry(pc={"portatile": pc}, documenti=FORMATI, biblioteca=True,
                         schermi=acceso, agenti=True)
    tempi = []
    # Un giro a vuoto: la cache del prefisso di Ollama si scalda con questo prompt
    for i in range(ripetizioni + 1):
        for frase in FRASI:
            ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx("Bianca",
                              "familiare"), speaker=None, agenda=agenda, liste=liste,
                              pc={"portatile": pc}, biblioteca=BibliotecaFinta(), schermi=hub)
            b = Brain(cfg, reg, ctx)
            _, primo, _ = esegui(b, frase, "familiare")
            if i:
                tempi.append(primo)
    if acceso:
        arrivate = len(pagina.schede)
        verifica(f"schermi accesi: schede arrivate alla pagina ({arrivate})", arrivate >= 3 * ripetizioni)
        srv.ferma()
    return tempi


rip = 2 * GIRI
spenti = blocco(False, rip)
accesi = blocco(True, rip)
ms, ma = statistics.median(spenti), statistics.median(accesi)
print(f"\nprima frase, {len(spenti)} risposte per parte: schermi spenti mediana {ms:.2f}s "
      f"(massimo {max(spenti):.2f}), accesi mediana {ma:.2f}s (massimo {max(accesi):.2f})")
verifica("la prima frase non peggiora con il server acceso (mediana entro +0,10 s)",
         ma <= ms + 0.10, f"{ms:.2f} → {ma:.2f}s")
print(f"{errori} errori" if errori else "Tutto a posto.")
sys.exit(1 if errori else 0)
