import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Delega, stato e annullo dei lavori a voce con il modello vero della voce (Ollama locale,
gemma4:e4b-it-qat) e un agente FINTO (prove/ollama_finto.py, lento: i lavori restano in
corso per le domande «a che punto è?» e «fermalo»).

Frasi come dette a voce, una sessione = un Brain:
- da delegare: script e programmi (anche da correggere), una pagina web, una relazione lunga
  in Word, una ricerca a più passi; con proposta e «sì» / «no» per i lavori costosi;
- da NON delegare (la ricerca del 02/10 delegava «come si scrive un ciclo for?» 2 volte su
  2): domande brevi di programmazione, spiegazioni, l'ora, una lettera in PDF e una tabella
  Excel (documento_crea), il volume del computer;
- permessi: un familiare non affida codice, un ospite non vede i tool;
- stato e annullo.
Tool come in Calliope: PC finto, documenti (servizio finto), schermi e agenti.

    python prove\\prova_agenti_ollama.py        # 2 giri
    python prove\\prova_agenti_ollama.py 1      # 1 giro
"""

import re
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ora_giusta import ora_o_tool  # noqa: E402  (03/10: l'ora giusta senza tool vale)
from calliope.agenti import Lavori, carica
from calliope.brain import Brain
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from prove.ollama_finto import FakeOllama
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
    def __init__(self, name, level, how="voce"):
        self.current_speaker, self.current_level, self.from_session = name, level, False
        self.identified_by = how


class DocJob:
    pass


class FakeDocs:
    """Documenti finti: documento_crea riesce subito (qui conta solo quale tool sceglie)."""
    formati = FORMATI

    def __init__(self):
        self.chiesti = []

    def crea(self, owner, owner_name, formato, richiesta, detto="", titolo=""):
        self.chiesti.append((formato, richiesta))
        return DocJob()

    def wait(self, job, t):
        return {"ok": True, "frase": "Ho preparato il documento, nella cartella Calliope dei "
                                     "Documenti."}


def delegato(svc, tipo=None):
    return [lv for lv in svc.lavori if tipo is None or lv.tipo == tipo]


DELEGA = "delega_lavoro"
NIENTE = ("niente_delega",)       # nessun delega_lavoro (qualunque altra cosa va bene)

# (sessione, chi, livello, come, frase, atteso, controllo(risposta, svc, docs))
#   atteso: nome del tool, NIENTE, oppure una tupla di tool ammessi
CASI = [
    # Codice: proposta, «sì», stato, annullo
    ("cod", "Dario", "amministra", "voce",
     "Scrivimi uno script Python che rinomina le foto di una cartella mettendo la data nel "
     "nome, con i test.", DELEGA,
     lambda r, s, d: r.rstrip().endswith("?") and not s.attivi()),
    ("cod", "Dario", "amministra", "breve", "Sì, vai.", DELEGA,
     lambda r, s, d: any(lv.tipo == "codice" for lv in s.attivi())),
    ("cod", "Dario", "amministra", "voce", "A che punto è il programma?", "lavori_stato",
     lambda r, s, d: "Sto lavorando" in r or "in coda" in r),
    ("cod", "Dario", "amministra", "voce", "Fermalo, non mi serve più.", "lavori_annulla",
     lambda r, s, d: "Ho fermato" in r and not any(lv.tipo == "codice" for lv in s.attivi())),
    # Documento lungo: parte subito (non costoso), non è documento_crea
    ("rel", "Dario", "amministra", "voce",
     "Preparami una relazione di cinque pagine sul risparmio energetico in casa, in Word, con "
     "introduzione, consigli per stanza e conclusioni.", DELEGA,
     lambda r, s, d: any(lv.tipo == "documento" for lv in s.lavori) and not d.chiesti),
    # Ricerca: proposta e «no»
    ("ric", "Dario", "amministra", "voce",
     "Fai una ricerca approfondita sulla storia dei Medici a Firenze e scrivimi una relazione "
     "completa.", DELEGA, lambda r, s, d: r.rstrip().endswith("?")),
    ("ric", "Dario", "amministra", "breve", "No, lascia stare.", NIENTE,
     lambda r, s, d: not any(lv.tipo == "ricerca" for lv in s.lavori)),
    # Altri lavori di codice
    ("cod2", "Dario", "amministra", "voce",
     "Correggi lo script di backup: non copia i file nascosti. Aggiungi anche i test.", DELEGA,
     lambda r, s, d: True),
    ("web", "Dario", "amministra", "voce",
     "Scrivimi una pagina web per la lista della spesa, con il pulsante per aggiungere le "
     "voci.", DELEGA, lambda r, s, d: True),
    # Da NON delegare
    ("for", "Dario", "amministra", "voce", "Come si scrive un ciclo for in Python, in breve?",
     NIENTE, lambda r, s, d: len(r) > 10),
    ("ric2", "Dario", "amministra", "voce", "Cos'è una funzione ricorsiva? Dimmelo in due parole.",
     NIENTE, lambda r, s, d: len(r) > 10),
    ("api", "Dario", "amministra", "voce", "Cosa vuol dire API in informatica?", NIENTE,
     lambda r, s, d: len(r) > 10),
    ("ora", "Dario", "amministra", "voce", "Che ore sono?", "ora_attuale",
     lambda r, s, d: re.search(r"\d", r)),
    ("let", "Dario", "amministra", "voce", "Scrivimi una lettera di disdetta della palestra in "
     "PDF.", "documento_crea", lambda r, s, d: True),
    # «compiti» come il parametro di delega_lavoro: senza la frase sui documenti brevi nel
    # prompt andava all'agente 3 volte su 4 (02/10)
    ("elenco", "Dario", "amministra", "voce", "Fai un PDF con l'elenco dei compiti di Matteo per "
     "domani: matematica pagina 40, leggere un capitolo del libro, ripassare storia.",
     "documento_crea", lambda r, s, d: True),
    ("xls", "Dario", "amministra", "voce", "Fammi una tabella Excel con le spese di settembre: "
     "affitto 800, luce 90, gas 60, con il totale.", "documento_crea", lambda r, s, d: True),
    ("vol", "Dario", "amministra", "voce", "Alza il volume del computer.", "pc_volume",
     lambda r, s, d: True),
    # Permessi
    ("fam", "Bianca", "familiare", "voce", "Scrivimi uno script che fa il backup dei miei "
     "documenti ogni sera.", (DELEGA, None),
     lambda r, s, d: not any(lv.persona == "bianca-id" and lv.tipo == "codice" for lv in s.lavori)),
    ("osp", None, "ospite", "voce", "Scrivimi un programma che calcola le tasse.",
     (DELEGA, None), lambda r, s, d: not any(lv.persona is None for lv in s.lavori)),
    # Stato senza lavori di chi chiede
    ("st", "Bianca", "familiare", "voce", "A che punto sono i miei lavori?", "lavori_stato",
     lambda r, s, d: True),
]

righe = []
for giro in range(1, GIRI + 1):
    tmp = Path(tempfile.mkdtemp(prefix="calliope_agenti_ollama_"))
    agente = FakeOllama(modelli=("qwen3.6:35b",), caricati=("qwen3.6:35b",)).avvia()
    agente.ritardo_pezzo, agente.pezzi = 0.5, 40         # ~20 s a passata: resta in corso
    agente.predefinita = {"content": "Sto lavorando. " * 20}
    cfg = Config()
    cfg.agenti_url = agente.url
    cfg.agenti_modello = "qwen3.6:35b"
    cfg.agenti_risultati = str(tmp / "risultati")
    cfg.agenti_sandbox = str(tmp / "sandbox")
    cfg.agenti_modelli = str(tmp / "modelli")
    svc = Lavori(cfg, carica(cfg), log=lambda m: None, formati=FORMATI)
    svc.verifica()
    pcs = {"portatile": FakePC(volume=40, luminosita=80)}
    docs = FakeDocs()
    # Come in Calliope: PC, documenti, schermi e agenti
    reg = build_registry(pc=pcs, documenti=FORMATI, schermi=True, agenti=True)
    brains = {}
    for sessione, chi, livello, come, frase, atteso, controllo in CASI:
        key = (sessione, chi)
        if key not in brains:
            ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(chi, livello),
                              speaker=None, pc=pcs, documenti=docs, lavori=svc)
            brains[key] = Brain(cfg, reg, ctx)
        b = brains[key]
        b.tool_ctx.speaker_ctx = SpeakerCtx(chi, livello, come)
        t0 = time.perf_counter()
        primo, parti = None, []
        for pezzo in b.stream_reply(frase, livello):
            if primo is None and pezzo.strip():
                primo = time.perf_counter() - t0
            parti.append(pezzo)
        totale = time.perf_counter() - t0
        risposta = "".join(parti).strip()
        if sessione == "cod" and frase.startswith("Fermalo"):
            time.sleep(1.0)                              # il lavoro si ferma da sé
        tools = [t["nome"] for t in b.last_tools]
        if atteso == NIENTE:
            ok_tool = DELEGA not in tools
        elif isinstance(atteso, tuple):
            ok_tool = any(t in atteso for t in tools) or (None in atteso and not tools)
        else:
            ok_tool = ((atteso in tools and (atteso == DELEGA or DELEGA not in tools))
                       or ora_o_tool(atteso, tools, risposta))
        try:
            ok_stato = bool(controllo(risposta, svc, docs))
        except Exception as e:  # noqa: BLE001
            ok_stato, risposta = False, f"{risposta} [controllo: {e}]"
        argomenti = "; ".join(f"{t['nome']}({', '.join(f'{k}={v!r}' for k, v in t['argomenti'].items())})"
                              for t in b.last_tools) or "—"
        verifica(f"[{giro}] {chi or 'ospite'}: «{frase}» → {argomenti}", ok_tool and ok_stato,
                 f"{primo or 0:.2f}/{totale:.2f}s  {risposta[:150]!r}")
        righe.append((giro, frase, ok_tool and ok_stato, primo or 0, totale))
    svc.close()
    agente.ferma()

prime = sorted(r[3] for r in righe)
print(f"\nprima frase mediana {prime[len(prime) // 2]:.2f}s, massimo {prime[-1]:.2f}s; "
      f"riuscite {sum(r[2] for r in righe)}/{len(righe)}")
print(f"{errori} errori" if errori else "Tutto a posto.")
sys.exit(1 if errori else 0)
