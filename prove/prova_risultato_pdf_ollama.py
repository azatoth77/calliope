import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""«Fammene un PDF» subito dopo il risultato di un lavoro dell'agente, con il modello vero della
voce (Ollama locale, gemma4:e4b-it-qat) e il modello dell'agente FINTO (prove/ollama_finto.py).

Caso vero della DGX del 07/10 pomeriggio (registro dei turni, qui con nomi di fantasia): una
ricerca finita e annunciata («ho finito «Esegui una ricerca approfondita sui vantaggi»: …
Il file è nella cartella Calliope dei Documenti del portatile. Lo apro?»), «Per il risultato.»
→ risultato_lavoro e il riassunto detto; poi «Fammene un PDF» trascritto «Ho metto un pdf.»
→ pc_cerca_file(tipo=pdf), l'elenco dei PDF del PC, invece di risultato_lavoro(modo=pdf).

Per ogni frase un Brain nuovo con quella storia (annuncio e riassunto come dati dell'agente,
la proposta «Lo apro?» in sospeso), e la frase:
  1. «Ho metto un pdf.» (storpiata come nel caso vero) → risultato_lavoro modo pdf;
  2. «Fammene un PDF.» → risultato_lavoro modo pdf;
  3. «Famme un pdf.» (un'altra storpiatura, non negli esempi del contesto) → modo pdf;
  4. «Me lo fai in Word?» → risultato_lavoro modo word;
  contrari (un file del PC nominato: pc_cerca_file, mai risultato_lavoro):
  5. «Cercami il PDF della bolletta della luce.»;
  6. «Aprimi il PDF del contratto d'affitto.».
Caso vero del 07/10, 16:11 (telefono, 26B): l'annuncio e poi altri turni (lista, promemoria),
senza il riassunto; «E il risultato di ricerca sulle pompe di calore?» → lavori_stato (l'elenco
dei lavori finiti) invece di risultato_lavoro:
  7. quella frase, 8. «Cosa ha trovato la ricerca sulle pompe di calore?» → risultato_lavoro;
  9. contrario: «Quali lavori hai finito oggi?» → lavori_stato.
Le 7–9 sono solo misura: il 4B qui non chiama nessun tool (risponde dalla storia), nemmeno
per la 9; contano nel riepilogo, non negli errori.

    python prove\\prova_risultato_pdf_ollama.py        # 3 giri
    python prove\\prova_risultato_pdf_ollama.py 1      # 1 giro
"""

import tempfile
import time
from pathlib import Path

from calliope.agenti import Lavori, carica
from calliope.brain import Brain
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from calliope.documenti.servizio import in_sospeso
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from prove.ollama_finto import FakeOllama
from prove.pc_finto import FakePC

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
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


COMPITO = ("Fai una ricerca sui vantaggi e gli svantaggi delle pompe di calore per una casa.")
TITOLO = "Esegui una ricerca approfondita sui vantaggi e gli svantaggi delle pompe di calore"
DETTO = "Esegui una ricerca approfondita sui vantaggi"
RIASSUNTO = ("La convenienza dipende dalla zona climatica, dal tipo di impianto esistente e "
             "dalla disponibilità di incentivi statali.")
TESTO = ("# Pompe di calore\n\n## Vantaggi\n\nAlta efficienza, meno emissioni, costi di "
         "gestione bassi.\n\n## Svantaggi\n\nCosto iniziale alto, serve una casa ben isolata.\n")
ANNUNCIO = (f"Marta, ho finito «{DETTO}»: 11 sezioni, 3 elenchi e 3 tabelle. {RIASSUNTO} Il "
            "file è nella cartella Calliope dei Documenti del portatile. Lo apro?")
RISPOSTA = (f"«{DETTO}»: Le pompe di calore offrono un'alta efficienza energetica e riducono le "
            "emissioni, con un risparmio sui costi di gestione. Tuttavia hanno un costo "
            "iniziale elevato e richiedono un edificio ben isolato. Il testo intero è sul tuo "
            "schermo.")

# (frase, tool atteso, modo atteso o None = qualunque, storia: "dopo" il riassunto detto o
# "lontano": l'annuncio e poi altri turni, senza il riassunto)
FRASI = [
    ("Ho metto un pdf.", "risultato_lavoro", "pdf", "dopo"),
    ("Fammene un PDF.", "risultato_lavoro", "pdf", "dopo"),
    ("Famme un pdf.", "risultato_lavoro", "pdf", "dopo"),
    ("Me lo fai in Word?", "risultato_lavoro", "word", "dopo"),
    ("Cercami il PDF della bolletta della luce.", "pc_cerca_file", None, "dopo"),
    ("Aprimi il PDF del contratto d'affitto.", "pc_cerca_file", None, "dopo"),
    # Caso vero del 07/10, 16:11 (telefono): il risultato di un lavoro nominato, chiesto un
    # po' dopo l'annuncio → lavori_stato (l'elenco), poi «Di quello della pompa di calore, sì»
    ("E il risultato di ricerca sulle pompe di calore?", "risultato_lavoro", None, "lontano"),
    ("Cosa ha trovato la ricerca sulle pompe di calore?", "risultato_lavoro", None, "lontano"),
    # contrario: l'elenco dei lavori
    ("Quali lavori hai finito oggi?", "lavori_stato", None, "lontano"),
]
ALTRI = [("Che ore sono?", "Sono le 16:10."),
         ("Ricordami tra 5 minuti di controllare il forno.",
          "Va bene, oggi alle 16 e 15 ti ricordo di controllare il forno."),
         ("Mostrami la lista della spesa.", "La lista della spesa è vuota."),
         ("Aggiungi il pane alla lista.", "Ho aggiunto il pane alla lista della spesa."),
         ("Grazie.", "Prego.")]

righe = []


def sessione(cfg, svc, pcs, storia="dopo"):
    """Un Brain nuovo con la storia del caso vero."""
    reg = build_registry(pc=pcs, documenti=FORMATI, schermi=True, agenti=True)
    ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx("Marta", "amministra"),
                      speaker=None, pc=pcs, documenti=None, lavori=svc)
    b = Brain(cfg, reg, ctx)
    b.history = [{"role": "user", "content": COMPITO},
                 {"role": "assistant", "content": "Ci lavoro in secondo piano: ti avviso "
                                                  "quando è pronto. Intanto puoi chiedermi altro."},
                 {"role": "user", "content": "Quanto fa 17 per 23?"},
                 {"role": "assistant", "content": "391."}]
    b.conv_owner = "marta-id"
    b.last_turn_at = time.monotonic()
    b.record_announcement(ANNUNCIO, in_sospeso("Lo apro?", f"il risultato «{DETTO}»"),
                          fonte="agente")
    if storia == "lontano":
        for dom, risp in ALTRI:
            b.history += [{"role": "user", "content": dom},
                          {"role": "assistant", "content": risp}]
        b.pending = None
        return b
    b.history += [{"role": "user", "content": "Per il risultato."},
                  {"role": "assistant", "content": RISPOSTA, "_fonte": "agente"}]
    return b


for giro in range(1, GIRI + 1):
    tmp = Path(tempfile.mkdtemp(prefix="calliope_risultato_pdf_"))
    agente = FakeOllama(modelli=("qwen3.6:35b",), caricati=("qwen3.6:35b",)).avvia()
    agente.predefinita = {"content": RISPOSTA}
    cfg = Config()
    cfg.agenti_url = agente.url
    cfg.agenti_modello = "qwen3.6:35b"
    cfg.agenti_risultati = str(tmp / "risultati")
    cfg.agenti_sandbox = str(tmp / "sandbox")
    cfg.agenti_modelli = str(tmp / "modelli")
    svc = Lavori(cfg, carica(cfg), log=lambda m: None, formati=FORMATI)
    svc.verifica()
    lav = svc.nuovo("ricerca", TITOLO, "marta-id", "Marta", "amministra")
    dest = tmp / "risultati" / "ricerca"
    dest.mkdir(parents=True)
    (dest / "risultato.md").write_text(TESTO, encoding="utf-8")
    lav.stato, lav.inizio, lav.fine = "fatto", time.time() - 120, time.time() - 50
    lav.cartella = str(dest)
    lav.risultato = {"esito": "fatto", "testo": TESTO, "riassunto": RIASSUNTO,
                     "file": ["risultato.md"], "cartella": str(dest)}
    svc.lavori.append(lav)
    pcs = {"portatile": FakePC(volume=40, luminosita=80)}
    for i, (frase, atteso, modo, storia) in enumerate(FRASI, 1):
        b = sessione(cfg, svc, pcs, storia)
        t0 = time.perf_counter()
        primo, parti = None, []
        for pezzo in b.stream_reply(frase, "amministra"):
            if primo is None and pezzo.strip():
                primo = time.perf_counter() - t0
            parti.append(pezzo)
        risposta = "".join(parti).strip()
        chiamate = [(t["nome"], t["argomenti"]) for t in b.last_tools]
        nomi = [n for n, _ in chiamate]
        if atteso == "risultato_lavoro":
            ok = any(n == atteso and (modo is None or str(a.get("modo", "")).lower() == modo)
                     for n, a in chiamate)
            ok = ok and "pc_cerca_file" not in nomi and "lavori_stato" not in nomi
        else:
            ok = atteso in nomi and "risultato_lavoro" not in nomi
        argomenti = "; ".join(f"{n}({', '.join(f'{k}={v!r}' for k, v in a.items())})"
                              for n, a in chiamate) or "—"
        dettaglio = f"{primo or 0:.2f}s  {risposta[:160]!r}  regole={b.last_rules}"
        if storia == "lontano":
            # Solo misura: col 4B nessun tool, nemmeno lavori_stato per «Quali lavori hai
            # finito oggi?» (risponde dalla storia, 0/3 prima e dopo il 07/10); il 26B della
            # DGX chiamava lavori_stato. Non conta negli errori
            print(f"{'ok ' if ok else '-- '} [{giro}.{i}] (misura) «{frase}» → {argomenti}  "
                  f"{dettaglio}", flush=True)
        else:
            verifica(f"[{giro}.{i}] «{frase}» → {argomenti}", ok, dettaglio)
        righe.append((giro, i, ok, primo or 0))
    svc.close()
    agente.ferma()

prime = sorted(r[3] for r in righe)
for i, (frase, _, _, _) in enumerate(FRASI, 1):
    rr = [r for r in righe if r[1] == i]
    print(f"«{frase}»: {sum(r[2] for r in rr)}/{len(rr)}")
print(f"\nprima frase mediana {prime[len(prime) // 2]:.2f}s, massimo {prime[-1]:.2f}s; "
      f"riuscite {sum(r[2] for r in righe)}/{len(righe)}")
print(f"{errori} errori" if errori else "Tutto a posto.")
sys.exit(1 if errori else 0)
