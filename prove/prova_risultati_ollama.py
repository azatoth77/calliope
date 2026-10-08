import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Il risultato di un lavoro dell'agente già finito, chiesto a voce, con il modello vero della
voce (Ollama locale, gemma4:e4b-it-qat) e il modello dell'agente FINTO (prove/ollama_finto.py:
il riassunto per la voce è a copione).

Caso vero della DGX del 07/10 (registro dei turni, qui con nomi di fantasia): una ricerca
finita e annunciata («ho finito «Esegui una ricerca approfondita…»: 20 paragrafi…»), poi
«E il risultato?» → lavoro_rispondi fallito («l'agente non ha generato un rapporto da
leggermi»); «leggili o delegali e dammi un bel riassunto» → programma_esegui («Non ho programmi
finiti da eseguire»), due volte; poi lavoro_affida di un «documento generato dalla ricerca
precedente». Manca un modo per avere il risultato: dal 07/10 c'è lavoro_risultato.

Per ogni frase un Brain nuovo, con la storia come quella vera (richiesta, «Ci lavoro…»,
annuncio dell'agente come dato non fidato), e la frase subito dopo l'annuncio:
  1. «E il risultato?» (breve, quindi familiare);
  2. «Perfetto, ti chiederei di leggerli o comunque di delegarli e di darmi un bel riassunto.»;
  3. «…voglio un bel riassunto verbale.».
Riuscita: nessun tool sbagliato (programma_esegui, lavoro_rispondi, lavoro_affida,
pc_cerca_file), nessuna chiamata scritta come testo e, per la 2 e la 3, un dettaglio che sta
solo nel testo intero (non nell'annuncio). Senza lavoro_risultato (main prima del 07/10) la prova misura lo stesso.

    python prove\\prova_risultati_ollama.py        # 5 giri
    python prove\\prova_risultati_ollama.py 2      # 2 giri
"""

import re
import tempfile
import time
from pathlib import Path

from calliope.agenti import Lavori, carica
from calliope.agenti.ciclo import Lavoro
from calliope.brain import Brain
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from prove.ollama_finto import FakeOllama
from prove.pc_finto import FakePC

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 5
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
        self.p = {"Marta": Prof("marta-id", "Marta", True)}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    def __init__(self, name, level, how="voce"):
        self.current_speaker, self.current_level, self.from_session = name, level, False
        self.identified_by = how


COMPITO = ("Fai una ricerca approfondita su internet sui pannelli fotovoltaici Solaris: se "
           "esiste un'integrazione con Home Assistant, quali sono le caratteristiche "
           "principali e se c'è hardware da aggiungere.")
RIASSUNTO = ("Ho completato la ricerca sui pannelli Solaris e la loro integrazione con Home "
             "Assistant. Solaris offre pannelli ad altissima efficienza con garanzie fino a 25 "
             "anni.")
PARAGRAFI = [
    "I pannelli Solaris sono moduli monocristallini ad alta efficienza, fino al 22 per cento.",
    "La garanzia sul prodotto e sulla resa arriva a 25 anni.",
    "Non esiste un'integrazione ufficiale di Home Assistant con il marchio Solaris.",
    "Esiste però un componente della comunità, installabile con HACS, chiamato solaris-locale.",
    "Il componente legge i dati dal gateway del sistema attraverso la rete di casa.",
    "In alternativa l'inverter espone i dati con il protocollo Modbus TCP.",
    "Per usare Modbus serve abilitarlo dal pannello dell'installatore.",
    "Non serve hardware aggiuntivo se il gateway è già collegato alla rete.",
    "Se il gateway è collegato solo in Wi-Fi, conviene un cavo di rete.",
    "I dati disponibili sono produzione istantanea, energia del giorno e stato dei moduli.",
] * 2
TESTO = "\n\n".join(PARAGRAFI)
ANNUNCIO = ("Marta, ho finito «Esegui una ricerca approfondita su internet sui pannelli»: 20 "
            "paragrafi. " + RIASSUNTO + " Il file è nella cartella Lavori dei Documenti.")
# Il riassunto per la voce del modello dell'agente (finto: a copione)
RIASSUNTO_AGENTE = ("Un'integrazione ufficiale con Home Assistant non c'è, ma c'è un componente "
                    "della comunità da installare con HACS che legge i dati dal gateway. In "
                    "alternativa l'inverter parla Modbus TCP, da abilitare dal pannello "
                    "dell'installatore. Non serve hardware in più se il gateway è già in rete: "
                    "al massimo un cavo di rete al posto del Wi-Fi.")
DETTAGLI = re.compile(r"hacs|modbus|comunit|cavo di rete", re.I)
SBAGLIATI = {"programma_esegui", "lavoro_rispondi", "lavoro_affida", "pc_cerca_file"}

# (come, livello, frase, serve il dettaglio)
FRASI = [
    ("breve", "familiare", "E il risultato?", False),
    ("voce", "amministra", "Perfetto, ti chiederei di leggerli o comunque di delegarli e di "
                           "darmi un bel riassunto.", True),
    ("voce", "amministra", "Prima hai fatto una ricerca su internet sui pannelli Solaris: mi "
                           "hai dato un documento ma non me l'hai riassunto per bene, io non lo "
                           "posso guardare adesso, voglio un bel riassunto verbale.", True),
]

righe = []


def sessione(cfg, svc, pcs):
    """Un Brain nuovo con la storia vera: richiesta, avvio, annuncio dell'agente."""
    reg = build_registry(pc=pcs, documenti=FORMATI, schermi=True, agenti=True)
    ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx("Marta", "amministra"),
                      speaker=None, pc=pcs, documenti=None, lavori=svc)
    b = Brain(cfg, reg, ctx)
    b.history = [{"role": "user", "content": COMPITO},
                 {"role": "assistant", "content": "Ci lavoro in secondo piano: ti avviso "
                                                  "quando è pronto. Intanto puoi chiedermi altro."}]
    b.conv_owner = "marta-id"
    b.last_turn_at = time.monotonic()
    b.record_announcement(ANNUNCIO, None, fonte="agente")
    return b


for giro in range(1, GIRI + 1):
    tmp = Path(tempfile.mkdtemp(prefix="calliope_risultati_ollama_"))
    agente = FakeOllama(modelli=("qwen3.6:35b",), caricati=("qwen3.6:35b",)).avvia()
    agente.predefinita = {"content": RIASSUNTO_AGENTE}
    cfg = Config()
    cfg.agenti_url = agente.url
    cfg.agenti_modello = "qwen3.6:35b"
    cfg.agenti_risultati = str(tmp / "risultati")
    cfg.agenti_sandbox = str(tmp / "sandbox")
    cfg.agenti_modelli = str(tmp / "modelli")
    svc = Lavori(cfg, carica(cfg), log=lambda m: None, formati=FORMATI)
    svc.verifica()
    # La ricerca finita, come dopo _esegui (risultato in memoria, file nella cartella)
    lav = svc.nuovo("ricerca", COMPITO, "marta-id", "Marta", "amministra")
    dest = tmp / "risultati" / "ricerca"
    dest.mkdir(parents=True)
    (dest / "ricerca.txt").write_text(TESTO, encoding="utf-8")
    lav.stato, lav.inizio, lav.fine = "fatto", time.time() - 90, time.time() - 30
    lav.cartella = str(dest)
    lav.risultato = {"esito": "fatto", "testo": TESTO, "riassunto": RIASSUNTO,
                     "file": ["ricerca.txt"], "cartella": str(dest)}
    svc.lavori.append(lav)
    pcs = {"portatile": FakePC(volume=40, luminosita=80)}
    # Ogni frase subito dopo l'annuncio (come nel caso vero), in una sessione sua
    for i, (come, livello, frase, dettaglio) in enumerate(FRASI, 1):
        b = sessione(cfg, svc, pcs)
        b.tool_ctx.speaker_ctx = SpeakerCtx("Marta", livello, come)
        t0 = time.perf_counter()
        primo, parti = None, []
        for pezzo in b.stream_reply(frase, livello):
            if primo is None and pezzo.strip():
                primo = time.perf_counter() - t0
            parti.append(pezzo)
        risposta = "".join(parti).strip()
        tools = [t["nome"] for t in b.last_tools]
        sbagliati = sorted(set(tools) & SBAGLIATI)
        come_testo = bool(re.match(r"\s*\w+\(", risposta))
        ok = (not sbagliati and bool(risposta) and not come_testo
              and (not dettaglio or bool(DETTAGLI.search(risposta))))
        argomenti = "; ".join(f"{t['nome']}({', '.join(f'{k}={v!r}' for k, v in t['argomenti'].items())})"
                              for t in b.last_tools) or "—"
        verifica(f"[{giro}.{i}] «{frase[:40]}…» → {argomenti}", ok,
                 f"{primo or 0:.2f}s  {risposta[:220]!r}")
        righe.append((giro, i, ok, primo or 0, "lavoro_risultato" in tools))
    svc.close()
    agente.ferma()

prime = sorted(r[3] for r in righe)
for i in range(1, len(FRASI) + 1):
    rr = [r for r in righe if r[1] == i]
    print(f"frase {i}: riuscite {sum(r[2] for r in rr)}/{len(rr)}, lavoro_risultato "
          f"{sum(r[4] for r in rr)}/{len(rr)}")
print(f"\nprima frase mediana {prime[len(prime) // 2]:.2f}s, massimo {prime[-1]:.2f}s; "
      f"riuscite {sum(r[2] for r in righe)}/{len(righe)}")
print(f"{errori} errori" if errori else "Tutto a posto.")
sys.exit(1 if errori else 0)
