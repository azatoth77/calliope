import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""La voce che offre lo schermo, con il modello vero (Ollama, gemma4 della configurazione).

    python prove/prova_scritto_ollama.py [GIRI]

Brain vero, estrazione dei campi vera, ufficio e rubrica in una cartella temporanea, un hub
degli schermi senza server con una pagina personale «collegata» (o nessuna). Conversazioni:
- contatto nuovo con una partita IVA che non torna → «… o lo scrivi sullo schermo?» e il
  modulo aperto; senza pagina la frase di sempre;
- preventivo senza dati → la domanda con lo schermo; poi i dati detti a voce → il modello
  richiama il tool e il modulo si chiude («hai risposto a voce»);
- distrattore: «che ore sono?» non apre moduli.
Misura quante volte la voce offre lo schermo quando c'è, e la prima frase.
"""

import asyncio
import tempfile
import time
from pathlib import Path

from calliope.brain import Brain
from calliope.config import Config
from calliope.documenti import Documenti
from calliope.documenti.consegna import LocalDelivery
from calliope.schermi import ArchivioSchermi, Schermi
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from calliope.ufficio import Ufficio
from calliope.ufficio.servizio import scrittore_locale

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 else 1
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


class Prof:
    def __init__(self, pid, name):
        self.id, self.name = pid, name


class Speakers:
    p = {"Dario": Prof("dario-id", "Dario")}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    current_speaker, current_level, profile_level = "Dario", "amministra", "amministra"
    from_session, identified_by = False, "voce"


ROSSI = {"tipo": "cliente", "denominazione": "Rossi e Figli Srl", "partita_iva": "12345678903",
         "indirizzo": "Via Verdi", "civico": "5", "cap": "00184", "comune": "Roma",
         "provincia": "RM"}
EMITTENTE = {"denominazione": "Esempio Srl", "partita_iva": "01234567897", "regime_fiscale":
             "RF01", "indirizzo": "Via Roma", "civico": "3", "cap": "20121", "comune": "Milano",
             "provincia": "MI", "iban": "IT60X0542811101000000123456"}

# (sessione, pagina collegata?, frase, tool atteso, controllo(risposta, hub)). Una sessione
# che finisce con «?» è solo una misura (non conta come errore): gemma4 a volte chiede i
# dati da sé invece di chiamare il tool, e allora il modulo non c'è
PRIMO: dict = {}          # il modulo aperto dal primo turno della rubrica


def primo_aperto(r, h):
    m = h.moduli.aperti("dario-id")
    PRIMO["id"] = m[0].id if m else None
    return "sullo schermo" in r and len(m) == 1


CASI = [
    ("rubrica", True, "Aggiungi in rubrica il cliente Verdi Srl, partita IVA 12345678904, "
     "via Po 3, 10121 Torino.", "anagrafica_salva", primo_aperto),
    # La risposta a voce richiama il tool: il modulo di prima si chiude (ne può aprire un
    # altro, per i dati che mancano ancora)
    ("rubrica", True, "La partita IVA giusta è 01234567897.", "anagrafica_salva",
     lambda r, h: PRIMO.get("id") and h.moduli.aperto(PRIMO["id"]) is None),
    ("rubrica_spento", False, "Aggiungi in rubrica il cliente Verdi Srl, partita IVA "
     "12345678904, via Po 3, 10121 Torino.", "anagrafica_salva",
     lambda r, h: "schermo" not in r),
    ("preventivo?", True, "Fammi un preventivo per Rossi e Figli per il sito vetrina.",
     "modello_compila", lambda r, h: "sullo schermo" in r and r.rstrip().endswith("?")),
    ("preventivo?", True, "Grafica 500 euro e sviluppo 1000 euro.", "modello_compila",
     lambda r, h: "sullo schermo" in r or "1.830" in r),
    ("ora", True, "Che ore sono?", "ora_attuale", lambda r, h: not h.moduli.aperti("dario-id")),
]

cfg = Config()
cfg.fatture_emittente = dict(EMITTENTE)
righe = []
misure = {"richieste": 0, "modulo": 0, "offerto": 0}
for giro in range(1, GIRI + 1):
    tmp = Path(tempfile.mkdtemp(prefix="calliope-scritto-ollama-"))
    db = str(tmp / "memoria.db")
    docs = Documenti(cfg, db, delivery=LocalDelivery(tmp / "Documenti"))
    u = Ufficio(cfg, db, docs, scrittore=scrittore_locale(docs.writer))
    u.rubrica.aggiungi(ROSSI, "casa", "dario-id")
    if giro == 1:
        docs.writer._native.warmup()
    brains = {}
    for sessione, collegata, frase, atteso, controllo in CASI:
        if sessione not in brains:
            cfg.memory_db = str(tmp / f"{sessione.rstrip('?')}.db")
            hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db))
            r = hub.archivio.nuova_richiesta()
            s = hub.archivio.abbina(r["codice"], "studio", "dario-id", "Dario")["schermo"]
            if collegata:
                hub.collega(s, asyncio.new_event_loop())   # una pagina aperta (finta)
            reg = build_registry(documenti=docs.formati, schermi=True, agenti=True,
                                 ufficio=u.nomi_modelli())
            ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(),
                              speaker=None, documenti=docs, ufficio=u, schermi=hub)
            brains[sessione] = (Brain(cfg, reg, ctx), hub)
        b, hub = brains[sessione]
        t0 = time.perf_counter()
        primo, parti = None, []
        for pezzo in b.stream_reply(frase, "amministra"):
            if primo is None and pezzo.strip():
                primo = time.perf_counter() - t0
            parti.append(pezzo)
        risposta = "".join(parti).strip()
        tools = [t["nome"] for t in b.last_tools]
        ok = (atteso in tools) and bool(controllo(risposta, hub))
        if collegata and atteso in ("anagrafica_salva", "modello_compila"):
            aperto = any(m.schermi for m in hub.moduli.aperti("dario-id"))
            misure["richieste"] += 1
            misure["modulo"] += aperto
            misure["offerto"] += aperto and "sullo schermo" in risposta
        nome = f"[{giro}] «{frase[:55]}» → {', '.join(tools) or '—'}"
        if sessione.endswith("?"):
            print(f"{'ok ' if ok else 'mis'} {nome}  (misura)  {primo or 0:.2f}s  "
                  f"{risposta[:160]!r}")
        else:
            verifica(nome, ok, f"{primo or 0:.2f}s  {risposta[:160]!r}")
            righe.append((ok, primo or 0))
    docs.close()

prime = sorted(r[1] for r in righe)
print(f"\nprima frase: mediana {prime[len(prime) // 2]:.2f}s, massimo {prime[-1]:.2f}s; "
      f"riuscite {sum(r[0] for r in righe)}/{len(righe)}; con la pagina collegata "
      f"{misure['richieste']} richieste di dati: modulo sullo schermo {misure['modulo']}, la "
      f"voce lo offre {misure['offerto']}/{misure['modulo']}")
sys.exit(1 if errori else 0)
