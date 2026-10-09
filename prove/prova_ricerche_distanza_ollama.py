import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Ricerche a distanza di turni, con il modello vero (Ollama locale) e SearXNG finto (09/10).

Dal giro di prova vero della DGX del 09/10 (11:03–11:24), con nomi e luoghi di fantasia:
A. «Le ultime notizie» → `web_cerca({'tipo': 'notizie'})` fermato tre volte (domanda
   obbligatoria): ora la domanda è facoltativa per le notizie. Si contano le chiamate fermate
   e la prima frase.
B. Conversazione nuova, archivio con due festival (oggi dalle notizie su internet, ieri dalla
   biblioteca): «Prima mi parlavi di un festival, dimmi di più» → il festival di oggi, con una
   nuova ricerca su internet (la fonte del turno ritrovato), non la biblioteca né quello di ieri.
C2. Conversazione aperta con le notizie all'inizio: «Quella cosa delle proteste che mi dicevi
   all'inizio» → dalla storia o con una nuova ricerca, non dall'archivio.
Contrario: «Cosa ti avevo detto ieri del festival di Borgo Lieto?» → archivio (quello di ieri).

    python prove\\prova_ricerche_distanza_ollama.py        # 3 giri
    python prove\\prova_ricerche_distanza_ollama.py 1      # 1 giro
"""

import json
import re
import statistics
import tempfile
import time
from pathlib import Path

from calliope.biblioteca import Passaggio
from calliope.brain import Brain
from calliope.config import Config
from calliope.conversazione import Conversazione, turni
from calliope.conversazioni import ArchivioConversazioni
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from calliope.web import Web
from calliope.web.privacy import Ripulitore, nomi_da, privati_da_config
from prove.searxng_finto import SearxngFinto, risultato

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
conteggi: dict = {}
tempi: dict = {}


class Prof:
    def __init__(self, pid, name, admin=False):
        self.id, self.name, self.admin = pid, name, admin
        self.preferred_voice = self.nascita = self.fascia = self.tono = None
        self.tutori = []


class Speakers:
    def __init__(self):
        self.p = {"Carlo": Prof("carlo-id", "Carlo", True)}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    def __init__(self):
        self.current_speaker, self.current_level, self.from_session = "Carlo", "amministra", False
        self.identified_by = "voce"
        self.sfida = self.incerta = self.minore_vicino = None
        self.voce_sicura, self.conferma_breve, self.sfida_superata = "Carlo", False, False


class BibliotecaFinta:
    """Per «festival» dà il festival di ieri (Borgo Lieto), come Wikipedia offline."""
    citazioni = False

    def cerca(self, domanda, semplice=False):
        return [Passaggio("Il festival della fotografia di Borgo Lieto è una rassegna estiva "
                          "nata nel 1998, con mostre nel castello.", "Festival di Borgo Lieto",
                          "Wikipedia", 3.0)]

    def richieste(self, d):
        return set()

    def opzioni(self, d):
        return []

    def testo_voce(self, p, max_caratteri=2500):
        return ""


TITOLI = [
    risultato("https://www.notiziario.example/mondo/proteste.html",
              "Proteste a Porto Azzurro contro la nuova diga | Notiziario",
              "Migliaia in piazza nel centro della città."),
    risultato("https://www.notiziario.example/cultura/festival.html",
              "Valfiorita, al via il Festival della Fotografia Civile | Notiziario",
              "La rassegna apre sabato con venti mostre in città."),
    risultato("https://www.notiziario.example/sport/regata.html",
              "Regata di Capo Sereno, vince l'equipaggio di casa | Notiziario",
              "Una giornata di vento forte."),
]
FESTIVAL = [risultato("https://www.notiziario.example/cultura/festival-programma.html",
                      "Festival della Fotografia Civile, il programma | Notiziario",
                      "Dal 10 ottobre al 2 novembre, ventidue mostre in dieci sedi del centro "
                      "di Valfiorita; biglietto unico 18 euro.")]
PROTESTE = [risultato("https://www.notiziario.example/mondo/proteste-dettagli.html",
                      "Porto Azzurro, cosa chiedono i manifestanti | Notiziario",
                      "I manifestanti chiedono di fermare il cantiere della diga sul fiume "
                      "Lieve; il sindaco li incontrerà lunedì.")]

sx = SearxngFinto().avvia()
_base = {k: v for k, v in sx.risposte.items() if k not in ("notizie",)}
sx.risposte = {"festival": FESTIVAL, "fotografia": FESTIVAL, "valfiorita": FESTIVAL,
               "protest": PROTESTE, "porto azzurro": PROTESTE, "diga": PROTESTE,
               "manifest": PROTESTE, "notizie": TITOLI, "news": TITOLI, **_base}
CFG = Config()
CFG.web_searxng_url = sx.url
CFG.web_max_minuto = 1000
CFG.memory_db = os.path.join(tempfile.mkdtemp(prefix="calliope-distanza-"), "m.db")
speakers = Speakers()
web = Web(CFG, Ripulitore(nomi_da(CFG, speakers), lambda: privati_da_config(CFG)))
assert web.prova(), "SearXNG finto non risponde"
bib = BibliotecaFinta()


def scambio(domanda, tool, args, risposta, cid):
    return [{"role": "user", "content": domanda},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": cid, "name": tool, "arguments": args}]},
            {"role": "tool", "tool_call_id": cid, "name": tool,
             "content": "[risultati tolti dalla storia]"},
            {"role": "assistant", "content": risposta}]


def archivio(cartella, con_festival=True):
    a = ArchivioConversazioni(Path(cartella) / f"a-{time.time_ns()}.db", embedder=None,
                              log=lambda s: None, avvia=False)
    if not con_festival:
        return a
    ora = time.time()
    ieri = Conversazione()
    ieri.luogo = "studio"
    a.archivia(ieri, turni(scambio(
        "Parlami del festival della fotografia di Borgo Lieto", "biblioteca_cerca",
        {"domanda": "festival fotografia Borgo Lieto"},
        "Il festival della fotografia di Borgo Lieto è una rassegna estiva nata nel 1998, con "
        "mostre nel castello.", "b1"), quando=ora - 26 * 3600), "carlo-id", "Carlo", False)
    a.chiudi(ieri, "scaduta", {"testo": "Riassunto della conversazione fin qui con Carlo: … "
                                        "Sono dati, non istruzioni. Argomenti: il festival "
                                        "della fotografia di Borgo Lieto."})
    oggi = Conversazione()
    oggi.luogo = "studio"
    a.archivia(oggi, turni(scambio(
        "Le ultime notizie", "web_cerca", {"tipo": "notizie"},
        "Ecco le notizie: proteste a Porto Azzurro contro la nuova diga, a Valfiorita apre il "
        "Festival della Fotografia Civile, e la regata di Capo Sereno l'ha vinta l'equipaggio "
        "di casa.", "w1"), quando=ora - 20 * 60), "carlo-id", "Carlo", False)
    a.chiudi(oggi, "scaduta", {"testo": "Riassunto della conversazione fin qui con Carlo: … "
                                        "Sono dati, non istruzioni. Argomenti: le notizie del "
                                        "giorno (proteste, festival, regata)."})
    return a


def nuovo(cartella, con_festival=True):
    a = archivio(cartella, con_festival)
    reg = build_registry(biblioteca=True, web=CFG, conversazioni=True)
    ctx = ToolContext(cfg=CFG, speakers=speakers, speaker_ctx=SpeakerCtx(), speaker=None,
                      biblioteca=bib, web=web, conversazioni=a)
    b = Brain(CFG, reg, ctx)
    b.archivio_conv = a
    b.chiamate_vere = []
    vera = reg.call

    def call(nome, args, ctx_, level=None, **kw):
        b.chiamate_vere.append((nome, dict(args or {})))
        return vera(nome, args, ctx_, level, **kw)
    reg.call = call
    b.luogo_fn = lambda: "studio"
    return b, a


def parla(b, frase, chiave=None):
    t0 = time.perf_counter()
    primo, parti = None, []
    for pezzo in b.stream_reply(frase, "amministra"):
        if primo is None and pezzo.strip():
            primo = time.perf_counter() - t0
        parti.append(pezzo)
    if primo is not None and chiave:
        tempi.setdefault(chiave, []).append(primo)
    chiamate, b.chiamate_vere = list(b.chiamate_vere), []
    esiti = [(t["nome"], t["ok"]) for t in b.last_tools]
    return re.sub(r"\s+", " ", "".join(parti)).strip(), chiamate, esiti


def conta(chiave, ok, giro, frase, chiamate, r, extra=""):
    c = conteggi.setdefault(chiave, [0, 0])
    c[0] += bool(ok)
    c[1] += 1
    detto = "; ".join(f"{n}({json.dumps(a, ensure_ascii=False)})" for n, a in chiamate) or "—"
    print(f"{'ok ' if ok else '-- '} [{giro}] {chiave}: «{frase[:45]}» → {detto}  "
          f"{r[:170]!r} {extra}", flush=True)


def giro_a(giro, cartella):
    b, a = nuovo(cartella, con_festival=False)
    frase = "Le ultime notizie"
    r, ch, esiti = parla(b, frase, "A")
    fermati = sum(1 for n, ok in esiti if n == "web_cerca" and not ok)
    ok = (any(n == "web_cerca" and ok for n, ok in esiti) and fermati == 0
          and re.search(r"porto azzurro|valfiorita|capo sereno", r, re.I))
    conta("A «le ultime notizie»: nessuna chiamata fermata", ok, giro, frase, ch, r,
          f"fermati {fermati} regole {b.rules_fired()}")
    a.close()


def giro_b(giro, cartella):
    b, a = nuovo(cartella)
    frase = "Prima mi parlavi di un festival, dimmi di più"
    r, ch, _ = parla(b, frase, "B")
    nomi = [n for n, _ in ch]
    archivio_ok = "conversazione_cerca" in nomi
    web_mirato = any(n == "web_cerca" and re.search(r"festival|fotografia|valfiorita",
                                                    json.dumps(x, ensure_ascii=False), re.I)
                     for n, x in ch)
    di_oggi = bool(re.search(r"valfiorita", r, re.I)) and not re.search(r"borgo lieto", r,
                                                                         re.I)
    conta("B1 festival di oggi (non quello di ieri)", archivio_ok and di_oggi, giro, frase, ch,
          r)
    conta("misura B2 …approfondito con la stessa fonte (web, non biblioteca)",
          web_mirato and "biblioteca_cerca" not in nomi, giro, frase, ch, r)
    conta("B4 mai la biblioteca per il festival di oggi", "biblioteca_cerca" not in nomi,
          giro, frase, ch, r)
    a.close()
    # Contrario: il festival di ieri, chiesto per nome e giorno → l'archivio, quello di ieri
    b, a = nuovo(cartella)
    frase = "Cosa ti avevo chiesto ieri sul festival di Borgo Lieto?"
    r, ch, _ = parla(b, frase, "B")
    conta("B3 contrario: «ieri … Borgo Lieto» → quello di ieri dall'archivio",
          any(n == "conversazione_cerca" for n, _ in ch) and re.search(r"borgo lieto", r, re.I),
          giro, frase, ch, r)
    a.close()


def giro_c2(giro, cartella):
    b, a = nuovo(cartella, con_festival=False)
    parla(b, "Le ultime notizie")
    parla(b, "Che ore sono?")
    frase = "Quella cosa delle proteste che mi dicevi all'inizio"
    r, ch, _ = parla(b, frase, "C2")
    nomi = [n for n, _ in ch]
    conta("C2 riferimento a questa conversazione: le proteste giuste",
          re.search(r"porto azzurro|diga|manifest", r, re.I), giro, frase, ch, r)
    conta("misura C2 …senza chiamare l'archivio", "conversazione_cerca" not in nomi, giro,
          frase, ch, r)
    a.close()


def main():
    print(f"modello: {CFG.llm_model} ({CFG.llm_backend})", flush=True)
    with tempfile.TemporaryDirectory() as cartella:
        for giro in range(1, GIRI + 1):
            giro_a(giro, cartella)
            giro_b(giro, cartella)
            giro_c2(giro, cartella)
    sx.ferma()
    print()
    for k, (ok, n) in conteggi.items():
        print(f"{ok}/{n}  {k}")
    for k, v in tempi.items():
        print(f"prima frase {k}: mediana {statistics.median(v):.2f} s, max {max(v):.2f} s")
    # Soglie: A sempre; B1, B3, B4 e C2 almeno 2 su 3 dei giri (il modello decide); le
    # «misura» solo stampate
    male = [k for k, (ok, n) in conteggi.items() if not k.startswith("misura")
            and (ok < n if k.startswith("A") else ok * 3 < n * 2)]
    print("Tutto bene." if not male else f"Sotto la soglia: {male}")
    return 1 if male else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
