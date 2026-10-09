import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Le ricerche della conversazione con la loro fonte, con il modello vero (09/10/2026 sera,
docs/aree/biblioteca.md). Manuale, non nel runner: serve l'Ollama di questo PC (il modello di
calliope.yaml). Mai l'Ollama della DGX. SearXNG e biblioteca finti.

- **notizia di prima**: notizie (tromba marina nel Trapanese), ora, un conto, la Torre di Pisa
  nella biblioteca, poi «Torniamo alla notizia del trapanese di prima. Dimmi di più.» → conta se
  chiama web_cerca con «tromba», «trapan» o «marsala» nella domanda (caso vero della DGX delle
  21:06: biblioteca_cerca);
- **birra**: «Quali sono le tecniche per fare la birra in casa?» → conta se chiama web_cerca
  (caso vero delle 18:47: tre biblioteca_cerca fuori tema).

    python prove\\misura_ricerche_fonte.py [GIRI] [RADICE]
"""
import os
import re
import sys
import tempfile
import time

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 else 3
# Un'altra radice del codice (il main, per il confronto «prima»)
RADICE = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))
sys.path.insert(0, RADICE)
os.chdir(RADICE)

from calliope.biblioteca import Passaggio  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402
from calliope.web import Web  # noqa: E402
from calliope.web.privacy import Ripulitore  # noqa: E402
from prove.searxng_finto import SearxngFinto, risultato  # noqa: E402


class Prof:
    def __init__(self):
        self.id, self.name, self.admin, self.preferred_voice = "d", "Dario", True, None


class Speakers:
    def get(self, n):
        return Prof() if n == "Dario" else None

    def known_speakers(self):
        return ["Dario"]


class SpeakerCtx:
    def __init__(self):
        self.current_speaker, self.current_level, self.from_session = "Dario", "familiare", False
        self.identified_by = "voce"


class Bib:
    citazioni = False
    domande = []

    def cerca(self, domanda, semplice=False):
        self.domande.append(domanda)
        if "pisa" in domanda.lower():
            return [Passaggio("La torre di Pisa è il campanile della cattedrale di Santa Maria "
                              "Assunta, famosa per la sua pendenza.", "Torre di Pisa",
                              "Wikipedia", 3.0)]
        return [Passaggio("Il birraio è un film del 1915 con Charlie Chaplin.", "Il birraio",
                          "Wikipedia", 2.0)]

    def richieste(self, d):
        return set()

    def opzioni(self, d):
        return []

    def testo_voce(self, p, max_caratteri=2500):
        return ""


NOTIZIE = [risultato("https://www.ansa.it/sicilia/tromba.html",
                     "Doppia tromba marina nel Trapanese, nove feriti a Marsala | ANSA",
                     "Danni al porto e a una scuola; sei bambini tra i feriti."),
           risultato("https://www.ansa.it/sport/serie-a.html", "Serie A, l'Inter vince | ANSA",
                     "Due a zero a San Siro.")]
TROMBA = [risultato("https://www.ansa.it/sicilia/tromba-dettagli.html",
                    "Tromba marina a Marsala, la scuola evacuata | ANSA",
                    "La protezione civile: 120 sfollati, il sindaco chiede lo stato di "
                    "calamità.")]
BIRRA = [risultato("https://www.birramia.it/guida-all-grain.html",
                   "Birra in casa: la guida all grain | BirraMia",
                   "Ammostamento a 66 gradi per un'ora, bollitura di 60 minuti, "
                   "fermentazione a 18–20 gradi.")]
sx = SearxngFinto().avvia()
base = {k: v for k, v in sx.risposte.items() if k != "notizie"}
sx.risposte = {"tromba": TROMBA, "trapan": TROMBA, "marsala": TROMBA, "birra": BIRRA,
               "notizie": NOTIZIE, "news": NOTIZIE, **base}
cfg = Config()
cfg.web_searxng_url = sx.url
cfg.web_max_minuto = 1000
cfg.memory_db = os.path.join(tempfile.mkdtemp(prefix="mis-ric-"), "m.db")
web = Web(cfg, Ripulitore())
assert web.prova()
reg = build_registry(biblioteca=True, web=cfg)
bib = Bib()


def nuovo():
    ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(), speaker=None,
                      biblioteca=bib, web=web)
    return Brain(cfg, reg, ctx)


def turno(b, frase):
    t0 = time.perf_counter()
    primo, parti = None, []
    for p in b.stream_reply(frase, "familiare"):
        if primo is None and p.strip():
            primo = time.perf_counter() - t0
        parti.append(p)
    return re.sub(r"\s+", " ", "".join(parti)).strip(), primo or 0.0


ok_d = ok_b = 0
tempi = []
for g in range(GIRI):
    b = nuovo()
    for f in ("Dimmi le ultime notizie", "Che ore sono?", "Quanto fa 12 per 7?",
              "Dimmi qualcosa sulla torre di Pisa"):
        turno(b, f)
    n = len(sx.domande())
    nb = len(bib.domande)
    r, t = turno(b, "Torniamo alla notizia del trapanese di prima. Dimmi di più.")
    tools = [x["nome"] for x in b.last_tools]
    qs = [q.lower() for q in sx.domande()[n:]]
    ok = "web_cerca" in tools and any(re.search(r"tromba|trapan|marsala", q) for q in qs)
    ok_d += ok
    tempi.append(t)
    print(f"D {g}: {'ok' if ok else 'NO'} {tools} web={qs} bib={bib.domande[nb:]} "
          f"regole={b.rules_fired()} ({t:.2f} s) → {r[:140]!r}", flush=True)
    b = nuovo()
    n = len(sx.domande())
    nb = len(bib.domande)
    r, t = turno(b, "Quali sono le tecniche per fare la birra in casa?")
    tools = [x["nome"] for x in b.last_tools]
    ok = "web_cerca" in tools
    ok_b += ok
    print(f"B {g}: {'ok' if ok else 'NO'} {tools} web={sx.domande()[n:]} "
          f"bib={bib.domande[nb:]} ({t:.2f} s) → {r[:140]!r}", flush=True)
sx.ferma()
print(f"\nRISULTATO {RADICE}: notizia di prima {ok_d}/{GIRI}, birra su internet {ok_b}/{GIRI}; "
      f"prima frase mediana D {sorted(tempi)[len(tempi) // 2]:.2f} s")
