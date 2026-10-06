import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a voce dell'ufficio con il modello vero (Ollama, gemma4 della configurazione).

    python prove/prova_ufficio_ollama.py [GIRI]

Brain vero, estrazione dei campi vera (stessa richiesta a Ollama di Calliope), rubrica,
numerazione e file in una cartella temporanea. Conversazioni: fattura detta tutta e «sì»;
fattura senza dati → domanda → dati → proposta → «no»; preventivo di un familiare; DDT;
rubrica (aggiungi con «sì», cerca); familiare che chiede una fattura (rifiutata); distrattori
(lettera semplice a documento_crea, ora). Conta i tool giusti, i numeri e i totali nei file,
e la prima frase.
"""

import datetime
import re
import tempfile
import time
from pathlib import Path

from calliope.brain import Brain
from calliope.config import Config
from calliope.documenti import Documenti
from calliope.documenti.consegna import LocalDelivery
from calliope.documenti.render import plain_text
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from calliope.ufficio import Ufficio
from calliope.ufficio.servizio import scrittore_locale

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ora_giusta import ora_o_tool  # noqa: E402  (04/10: l'ora giusta senza tool vale)

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
    p = {"Dario": Prof("dario-id", "Dario"), "Bianca": Prof("bianca-id", "Bianca")}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    def __init__(self, name, level):
        self.current_speaker, self.current_level = name, level
        self.from_session, self.identified_by = False, "voce"


EMITTENTE = {"denominazione": "Esempio Srl", "partita_iva": "01234567897", "regime_fiscale":
             "RF01", "indirizzo": "Via Roma", "civico": "3", "cap": "20121", "comune": "Milano",
             "provincia": "MI", "iban": "IT60X0542811101000000123456", "ritenuta": "20"}
ROSSI = {"tipo": "cliente", "denominazione": "Rossi e Figli Srl", "partita_iva": "12345678903",
         "indirizzo": "Via Verdi", "civico": "5", "cap": "00184", "comune": "Roma",
         "provincia": "RM"}


def pdf_di(cartella: Path) -> str:
    files = sorted(cartella.glob("*.pdf"), key=lambda p: p.stat().st_mtime)
    return plain_text("pdf", files[-1].read_bytes()) if files else ""


def numeri(u, serie):
    return [d["numero"] for d in u.numeri.elenco(serie, datetime.date.today().year)]


# (sessione, chi, livello, frase, tool atteso o None, controllo(risposta, ufficio, cartella))
CASI = [
    ("fattura", "Dario", "amministra",
     "Fammi una fattura a Rossi e Figli per due giornate di consulenza a 500 euro l'una.",
     "modello_compila", lambda r, u, c: "1.220" in r and r.rstrip().endswith("?")
     and not numeri(u, "fatture")),
    ("fattura", "Dario", "amministra", "Sì, preparala.", "modello_compila",
     lambda r, u, c: numeri(u, "fatture") == [1] and "1.220,00 €" in pdf_di(c / "Fatture")
     and any((c / "Fatture").glob("IT01234567897_*.xml"))),
    # Senza dati gemma4 chiede da sé cliente e voci (0/4 chiamate nella sonda del 03/10): va
    # bene uguale, purché non dichiari niente; la risposta dopo chiama il tool
    ("domanda", "Dario", "amministra", "Prepara una fattura.", None,
     lambda r, u, c: re.search(r"client|voc|import|prezz", r, re.I)
     and len(numeri(u, "fatture")) <= 1),
    ("domanda", "Dario", "amministra", "A Rossi e Figli, sviluppo del sito, 800 euro.",
     "modello_compila", lambda r, u, c: "976" in r and len(numeri(u, "fatture")) <= 1),
    ("domanda", "Dario", "amministra", "No, lascia stare.", None,
     lambda r, u, c: len(numeri(u, "fatture")) <= 1),
    ("preventivo", "Bianca", "familiare",
     "Fammi un preventivo per Rossi e Figli per un sito vetrina: grafica 500 euro e "
     "sviluppo 1000 euro.", "modello_compila",
     lambda r, u, c: "1.830" in r and not numeri(u, "preventivi")),
    ("preventivo", "Bianca", "familiare", "Sì.", "modello_compila",
     lambda r, u, c: numeri(u, "preventivi") == [1] and "1.830,00 €" in pdf_di(c / "Preventivi")),
    ("ddt", "Dario", "amministra",
     "Fai un documento di trasporto per Rossi e Figli: 2 monitor da 27 pollici, corriere BRT.",
     "modello_compila", lambda r, u, c: r.rstrip().endswith("?") and not numeri(u, "ddt")),
    ("ddt", "Dario", "amministra", "Va bene, procedi.", "modello_compila",
     lambda r, u, c: numeri(u, "ddt") == [1] and "BRT" in pdf_di(c / "DDT")),
    ("rubrica", "Dario", "amministra",
     "Aggiungi in rubrica il cliente Bianchi Snc, partita IVA 01234567897, corso Cavour 10, "
     "27100 Pavia, provincia di Pavia.", "anagrafica_salva",
     lambda r, u, c: "Bianchi" in r and r.rstrip().endswith("?")
     and u.rubrica.trova("Bianchi", "dario-id")[0] is None),
    ("rubrica", "Dario", "amministra", "Sì.", "anagrafica_salva",
     lambda r, u, c: (u.rubrica.trova("Bianchi", "dario-id")[0] or {}).get("cap") == "27100"),
    ("cerca", "Dario", "amministra", "Che partita IVA ha Rossi e Figli in rubrica?",
     "anagrafica_cerca", lambda r, u, c: "1 2 3 4 5" in r or "12345678903" in r.replace(" ", "")),
    ("familiare", "Bianca", "familiare", "Fammi una fattura a Rossi e Figli per 300 euro di "
     "assistenza.", None, lambda r, u, c: all(d["chi"] != "Bianca" for d in
                                               u.numeri.elenco("fatture"))),
    ("distrattori", "Dario", "amministra", "Preparami una lettera di disdetta della palestra.",
     "documento_crea", lambda r, u, c: True),
    ("distrattori", "Dario", "amministra", "Che ore sono?", "ora_attuale", lambda r, u, c: True),
]


def aspetta(svc, brain, limite=90.0):
    t0 = time.perf_counter()
    while svc.busy() and time.perf_counter() - t0 < limite:
        time.sleep(0.05)
    out = []
    while not svc.done.empty():
        msg = svc.done.get_nowait()["messaggio"]
        brain.record_announcement(msg)
        out.append(msg)
    return out


cfg = Config()
cfg.fatture_emittente = dict(EMITTENTE)
cfg.documenti_attesa_s = 8.0
righe = []
for giro in range(1, GIRI + 1):
    tmp = Path(tempfile.mkdtemp(prefix="calliope-ufficio-ollama-"))
    db = str(tmp / "memoria.db")
    docs = Documenti(cfg, db, delivery=LocalDelivery(tmp / "Documenti"))
    u = Ufficio(cfg, db, docs, scrittore=scrittore_locale(docs.writer))
    u.rubrica.aggiungi(ROSSI, "casa", "dario-id")
    reg = build_registry(documenti=docs.formati, schermi=True, agenti=True,
                         ufficio=u.nomi_modelli())
    if giro == 1:
        docs.writer._native.warmup()
    brains = {}
    for sessione, chi, livello, frase, atteso, controllo in CASI:
        key = (sessione, chi)
        if key not in brains:
            ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(chi, livello),
                              speaker=None, documenti=docs, ufficio=u)
            brains[key] = Brain(cfg, reg, ctx)
        b = brains[key]
        t0 = time.perf_counter()
        primo, parti = None, []
        for pezzo in b.stream_reply(frase, livello):
            if primo is None and pezzo.strip():
                primo = time.perf_counter() - t0
            parti.append(pezzo)
        annunci = aspetta(docs, b)
        risposta = " ".join(["".join(parti).strip()] + annunci).strip()
        tools = [t["nome"] for t in b.last_tools]
        ok_tool = ((atteso in tools) or ora_o_tool(atteso, tools, "".join(parti))) if atteso \
            else True
        try:
            ok = ok_tool and bool(controllo(risposta, u, tmp / "Documenti"))
        except Exception as e:  # noqa: BLE001
            ok, risposta = False, f"{risposta} [controllo: {type(e).__name__}: {e}]"
        argomenti = "; ".join(f"{t['nome']}({', '.join(f'{k}={v!r}' for k, v in t['argomenti'].items())})"
                              for t in b.last_tools) or "—"
        verifica(f"[{giro}] {chi}: «{frase[:60]}» → {argomenti[:160]}", ok,
                 f"{primo or 0:.2f}s  {risposta[:170]!r}")
        righe.append((ok, primo or 0))
    docs.close()

prime = sorted(r[1] for r in righe)
estr = sorted(s["estrazione_s"] for s in u.stats if "estrazione_s" in s)
print(f"\nprima frase: mediana {prime[len(prime) // 2]:.2f}s, massimo {prime[-1]:.2f}s; "
      f"riuscite {sum(r[0] for r in righe)}/{len(righe)}"
      + (f"; estrazione dei campi mediana {estr[len(estr) // 2]:.2f}s" if estr else ""))
sys.exit(1 if errori else 0)
