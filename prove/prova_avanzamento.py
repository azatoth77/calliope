import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco dell'avanzamento dei lavori sugli schermi (calliope/agenti/avanzamento.py,
03/10/2026), con l'Ollama finto (prove/ollama_finto.py) e, per il motore «openai», la sua API
compatibile:

- lavoro di codice: la scheda `lavoro:<id>` compare subito «in coda», poi si aggiorna al suo
  posto (`sposta: false`) con il passo, i passi recenti, i file scritti (nomi, righe e
  un'anteprima breve), l'esito dei test in parole («2 test su 3 passano»), il testo in arrivo,
  passate/token/minuti con i tetti; la scheda finale (codice intero) la sostituisce e va in
  cima; dopo la finale niente più aggiornamenti;
- ritmo: al più un aggiornamento ogni 0,5 s per lavoro anche con lo stream veloce, i pezzi
  accorpati; il costo per chi lavora (`Lavoro.nota`) in microsecondi;
- documento: «scrive la bozza» con il testo in arrivo, «impagina il documento» senza il JSON,
  scheda finale «documento» con la stessa chiave;
- domanda a metà lavoro: scheda «aspetta la tua risposta» in cima, ripresa al suo posto;
- annullo in coda (dal thread della voce, scheda costruita altrove) e in corso;
- arbitro (stesso Ollama della voce): «in pausa: sto rispondendo a voce» e ritorno;
- motore «openai»: il codice negli argomenti di scrivi_file arriva a pezzi sulla scheda;
- con gli schermi veri (Schermi, senza server): solo lo schermo personale di chi l'ha
  chiesto, una scheda sola nella cronologia, mai nella zona grigia; l'aggiornamento non
  diventa «l'ultima cosa mostrata» al posto di un calcolo;
- senza schermi, o con le schede automatiche spente, niente osservatore e niente thread.
"""

import json
import tempfile
import threading
import time
from pathlib import Path

from calliope.agenti import Lavori, carica
from calliope.agenti.avanzamento import _decodifica_argomenti
from calliope.agenti.ciclo import frase_test
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from calliope.schermi import schede
from calliope.schermi.archivio import ArchivioSchermi
from calliope.schermi.hub import Mittente, Schermi
from prove.ollama_finto import FakeOllama

TMP = Path(tempfile.mkdtemp(prefix="calliope-avanzamento-"))
MODELLO = "qwen3.6:35b"
errori = 0
# «La voce non aspetta» (03/10): le chiamate della voce costano meno di un millisecondo, e
# ciò che non devono aspettare (un pezzo dello stream, il tunnel, il portatile lento, la
# copia di un file) dura dai 0,2 s in su. Con 50 ms la prova falliva sotto carico (più
# prove insieme: «la delega risponde subito  50.5 ms», dove c'è anche l'avvio di un thread)
SUBITO_S = 0.15
LOG: list[str] = []


def sezione(nome):
    print(f"\n── {nome} ──", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    if not ok:
        errori += 1
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def aspetta(cond, s=10.0):
    fine_t = time.monotonic() + s
    while time.monotonic() < fine_t:
        if cond():
            return True
        time.sleep(0.01)
    return bool(cond())


def call(name, args=None):
    return {"name": name, "arguments": args or {}}


def cfg_base(url, **kw) -> Config:
    cfg = Config()
    cfg.agenti_url = url
    cfg.agenti_modello = MODELLO
    cfg.agenti_risultati = str(TMP / "risultati")
    cfg.agenti_sandbox = str(TMP / "sandbox")
    # Il codice dell'agente gira solo con il motore scelto a mano (03/10): qui il processo
    cfg.agenti_sandbox_motore = "processo"
    # Qui solo le schede del lavoro: l'esecuzione dimostrativa del programma finito (04/10,
    # scheda «esecuzione:…») la prova prova_esecuzione.py
    cfg.agenti_dimostrazione = False
    cfg.agenti_modelli = str(TMP / "modelli")
    cfg.llm_native_url = "http://127.0.0.1:9"
    cfg.agenti_esecuzione_s = 15.0
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def servizio(cfg) -> Lavori:
    return Lavori(cfg, carica(cfg), log=LOG.append, formati=FORMATI)


def fine(svc, s=60.0):
    # 60 s (06/10): con due runner insieme il primo lavoro (7 passate in streaming e due giri
    # di test nella sandbox) superava i 20 s di prima; finito il lavoro si torna subito
    import queue
    try:
        return svc.done.get(timeout=s)
    except queue.Empty:
        return None


class Registro:
    """Le schede mandate, con l'istante."""

    def __init__(self):
        self.schede: list[tuple[float, dict]] = []
        self.lock = threading.Lock()

    def __call__(self, card):
        with self.lock:
            self.schede.append((time.monotonic(), json.loads(json.dumps(card, default=str))))

    def tutte(self):
        with self.lock:
            return list(self.schede)


def controlla_ritmo(nome, reg, intervallo=0.5):
    """Tra due aggiornamenti automatici dello stesso lavoro almeno l'intervallo (meno un
    margine per l'orologio)."""
    agg = [(t, c) for t, c in reg.tutte() if c.get("sposta") is False]
    gaps = [b[0] - a[0] for a, b in zip(agg, agg[1:])]
    verifica(f"{nome}: al più 2 aggiornamenti al secondo", all(g >= intervallo - 0.03 for g in gaps),
             f"{len(agg)} aggiornamenti, intervallo minimo "
             f"{min(gaps) if gaps else 0:.3f} s")


def controlla_identita(nome, reg, ident):
    tutte = reg.tutte()
    verifica(f"{nome}: tutte le schede con la chiave lavoro:{ident}",
             tutte and all(c.get("chiave") == f"lavoro:{ident}" for _, c in tutte),
             str({c.get("chiave") for _, c in tutte}))
    verifica(f"{nome}: tutte personali", all(c.get("visibilita") == "personale" for _, c in tutte))


fake = FakeOllama(modelli=(MODELLO, "gemma4:e4b-it-qat")).avvia()

# ═══════════════════════════ 1. lavoro di codice ═══════════════════════════
sezione("lavoro di codice")
SBAGLIATA = "def somma(a, b):\n    return a - b\n"
GIUSTA = "def somma(a, b):\n    return a + b\n"
TEST = ("from somma import somma\n\n\ndef test_uno():\n    assert somma(2, 3) == 5\n\n\n"
        "def test_due():\n    assert somma(0, 0) == 0\n\n\ndef test_tre():\n"
        "    assert somma(1, 1) == 2\n")
fake.ritardo_pezzo, fake.pezzi = 0.02, 50
fake.copione = [
    {"thinking": "Guardo la cartella e poi scrivo la funzione.", "content":
     "Comincio dalla funzione somma e dai suoi test, poi li faccio girare. " * 3,
     "tool_calls": [call("elenca_file")]},
    {"tool_calls": [call("scrivi_file", {"percorso": "somma.py", "contenuto": SBAGLIATA})]},
    {"tool_calls": [call("scrivi_file", {"percorso": "test_somma.py", "contenuto": TEST})]},
    {"tool_calls": [call("esegui_test")]},
    {"content": "Un test passa per caso: correggo il segno. " * 4,
     "tool_calls": [call("scrivi_file", {"percorso": "somma.py", "contenuto": GIUSTA})]},
    {"tool_calls": [call("esegui_test")]},
    {"tool_calls": [call("consegna", {"riassunto": "Ho scritto la funzione che somma due "
                                                   "numeri, con tre test.", "esito": "fatto"})]},
]
svc = servizio(cfg_base(fake.url))
reg = Registro()
lav = svc.nuovo("codice", "Scrivi una funzione che somma due numeri, con i test",
                "dario-id", "Dario", "amministra")
lav.on_scheda = reg
t0 = time.monotonic()
svc.avvia(lav)
dt_avvia = time.monotonic() - t0
item = fine(svc)
verifica("avvia non aspetta la scheda", dt_avvia < SUBITO_S, f"{dt_avvia * 1000:.1f} ms")
verifica("lavoro finito", item is not None and item["stato"] == "fatto", str(item)[:200])
tutte = reg.tutte()
verifica("la prima scheda arriva subito, «in coda» o già «in corso», e va in cima",
         tutte and tutte[0][0] - t0 < 0.3 and tutte[0][1]["stato"] in ("in_coda", "in_corso")
         and tutte[0][1].get("sposta") is not False,
         f"{(tutte[0][0] - t0) * 1000:.0f} ms, {tutte and tutte[0][1]['stato']}")
controlla_identita("codice", reg, lav.id)
controlla_ritmo("codice", reg)
agg = [c for _, c in tutte[1:-1]]
verifica("gli aggiornamenti in corso non spostano la scheda",
         agg and all(c.get("sposta") is False for c in agg), f"{len(agg)} aggiornamenti")
finale = tutte[-1][1]
verifica("la scheda finale sostituisce quella in corso e va in cima",
         finale["stato"] == "fatto" and finale.get("sposta") is not False
         and any("return a + b" in f["testo"] for f in finale.get("file", [])), str(finale)[:200])
av_f = finale.get("avanzamento") or {}
verifica("la finale ha passate, token e passi recenti",
         av_f.get("passate") == lav.passi and av_f.get("max_passate") == svc.agente.max_passi
         and av_f.get("passi"), json.dumps(av_f, ensure_ascii=False)[:300])
passi = [p["testo"] for _, c in tutte for p in (c.get("avanzamento") or {}).get("passi", [])]
verifica("passi in parole semplici: scrive, prova il codice con l'esito dei test",
         "scrive somma.py" in passi and "prova il codice: 1 test su 3 passano" in passi
         and "prova il codice: tutti i 3 test passano" in passi, str(sorted(set(passi))))
con_file = [c["avanzamento"] for _, c in tutte if (c.get("avanzamento") or {}).get("file")]
verifica("i file scritti finora: nomi e righe, l'anteprima del codice",
         con_file and any(f["nome"] == "test_somma.py" and f["righe"] == 13
                          for a in con_file for f in a["file"])
         and any(a.get("anteprima") and "def somma" in a["anteprima"]["testo"] for a in con_file),
         json.dumps(con_file[-1] if con_file else {}, ensure_ascii=False)[:300])
verifica("niente codice intero negli aggiornamenti (solo l'anteprima)",
         all(not c.get("file") for c in agg))
test_visti = [c.get("test") for c in agg if c.get("test")]
verifica("l'esito dei test sulla scheda in corso", any(
    t["eseguiti"] == 3 and t["falliti"] == 2 for t in test_visti), str(test_visti[:2]))
flussi = [c["avanzamento"]["flusso"] for c in agg if c["avanzamento"].get("flusso")]
verifica("il testo che l'agente sta scrivendo, accorpato e tagliato",
         any(f["tipo"] == "testo" and ("Comincio dalla funzione" in f["testo"]
                                       or "correggo il segno" in f["testo"]) for f in flussi)
         and all(len(f["testo"]) <= 800 for f in flussi), str(flussi[:1])[:200])
verifica("tetti onesti: passate e minuti con il loro massimo, nessuna percentuale",
         all({"passate", "max_passate", "token", "max_token", "trascorso_s", "max_s"}
             <= set(c["avanzamento"]) and "percentuale" not in c["avanzamento"] for c in agg)
         and any(c["avanzamento"].get("dal") for c in agg if c["stato"] == "in_corso"))
n = len(reg.tutte())
time.sleep(0.8)
verifica("dopo la finale nessun aggiornamento", len(reg.tutte()) == n)
verifica("frase_test", frase_test({"eseguiti": 3, "falliti": 1, "errori": 0}) ==
         "prova il codice: 2 test su 3 passano"
         and frase_test({"eseguiti": 1}) == "prova il codice: il test passa"
         and frase_test({}) == "prova il codice: nessun test trovato")
verifica("la voce dice il passo nuovo («l'agente prova il codice: …»)",
         frase_test({"eseguiti": 2, "falliti": 0}).startswith("prova il codice"))

# Costo per chi lavora: un pezzo dello stream = un lock e qualche assegnazione
lv = svc.nuovo("codice", "prova del costo", "dario-id", "Dario")
lv.on_scheda = Registro()
svc.avanzamento.segui(lv)
N = 20000
t0 = time.perf_counter()
for i in range(N):
    lv.nota("flusso", tipo="testo", testo="parola ")
us = (time.perf_counter() - t0) / N * 1e6
t0 = time.perf_counter()
for i in range(2000):
    lv.passo = f"passo {i % 7}"
us_passo = (time.perf_counter() - t0) / 2000 * 1e6
verifica("costo di un pezzo dello stream per chi lavora: pochi microsecondi", us < 50,
         f"{us:.1f} µs a pezzo, {us_passo:.1f} µs a cambio di passo")
time.sleep(0.6)
verifica("20 000 pezzi in un attimo: al più 1–2 schede", len(lv.on_scheda.tutte()) <= 3,
         f"{len(lv.on_scheda.tutte())} schede")
lv.annulla.set()
lv.stato = "annullato"
svc.avanzamento.finale(lv)

# ═══════════════════════════ 2. documento ═══════════════════════════
sezione("documento")
DOC = {"titolo": "Relazione sul giardino", "blocchi": [
    {"tipo": "titolo", "testo": "Relazione sul giardino"},
    {"tipo": "paragrafo", "testo": "Il giardino ha bisogno di acqua due volte a settimana."}]}
fake.ritardo_pezzo, fake.pezzi = 0.03, 30
fake.copione = [{"content": "Relazione sul giardino. Il giardino ha bisogno di acqua due volte "
                            "a settimana, le rose vanno potate a marzo. " * 3},
                {"content": json.dumps(DOC, ensure_ascii=False)}]
reg = Registro()
lav = svc.nuovo("documento", "Prepara una relazione sul giardino", "bianca-id", "Bianca",
                formato="word")
lav.on_scheda = reg
svc.avvia(lav)
item = fine(svc)
tutte = reg.tutte()
verifica("documento finito", item and item["stato"] == "fatto")
controlla_identita("documento", reg, lav.id)
controlla_ritmo("documento", reg)
passi = [p["testo"] for _, c in tutte for p in (c.get("avanzamento") or {}).get("passi", [])]
verifica("passi: scrive la bozza, impagina il documento",
         "scrive la bozza" in passi and "impagina il documento" in passi, str(set(passi)))
flussi = [c["avanzamento"].get("flusso") for _, c in tutte
          if c["tipo"] == "lavoro" and (c.get("avanzamento") or {}).get("flusso")]
verifica("la bozza in arrivo sulla scheda, il JSON no",
         any("rose vanno potate" in f["testo"] for f in flussi)
         and not any("\"blocchi\"" in f["testo"] for f in flussi), str(flussi[-1:])[:200])
verifica("finale: scheda «documento» con la stessa chiave, in cima",
         tutte[-1][1]["tipo"] == "documento" and tutte[-1][1].get("sposta") is not False
         and tutte[-1][1]["chiave"] == f"lavoro:{lav.id}")

# ═══════════════════════════ 3. domanda a metà lavoro ═══════════════════════════
sezione("domanda a metà lavoro")
fake.ritardo_pezzo, fake.pezzi = 0.0, 4
fake.copione = [
    {"tool_calls": [call("scrivi_file", {"percorso": "saluta.py",
                                         "contenuto": "print('ciao')\n"})]},
    {"tool_calls": [call("consegna", {"riassunto": "Manca il nome.", "esito": "mancano_dati",
                                      "domanda": "Come si chiama la persona da salutare?"})]},
    {"content": "Saluto Marta: cambio il programma e lo provo. " * 4,
     "tool_calls": [call("scrivi_file", {"percorso": "saluta.py",
                                         "contenuto": "print('ciao Marta')\n"})]},
    {"tool_calls": [call("consegna", {"riassunto": "Fatto.", "esito": "fatto"})]},
]
reg = Registro()
lav = svc.nuovo("codice", "Scrivi un programma che saluta qualcuno", "dario-id", "Dario")
lav.on_scheda = reg
svc.avvia(lav)
item = fine(svc)
att = reg.tutte()[-1][1] if reg.tutte() else {}
verifica("in attesa: scheda con la domanda, in cima",
         item and item["stato"] == "in_attesa" and att.get("stato") == "in_attesa"
         and "Come si chiama" in (att.get("domanda") or "") and att.get("sposta") is not False,
         str(att)[:200])
n0 = len(reg.tutte())
fake.ritardo_pezzo, fake.pezzi = 0.05, 30
svc.rispondi(lav, "Marta")
item = fine(svc)
dopo = [c for _, c in reg.tutte()[n0:]]
verifica("ripresa: aggiornamenti al loro posto, poi la finale in cima",
         item and item["stato"] == "fatto" and len(dopo) >= 2 and dopo[-1]["stato"] == "fatto"
         and dopo[-1].get("sposta") is not False
         and all(c.get("sposta") is False for c in dopo[:-1]),
         str([(c["stato"], c.get("sposta")) for c in dopo]))
controlla_identita("domanda", reg, lav.id)

# ═══════════════════════════ 4. annullo ═══════════════════════════
sezione("annullo")
fake.ritardo_pezzo, fake.pezzi = 0.1, 40
fake.copione = [{"content": "x" * 400}]
reg1, reg2 = Registro(), Registro()
l1 = svc.nuovo("altro", "Scrivi un testo lungo", "dario-id", "Dario")
l1.on_scheda = reg1
l2 = svc.nuovo("altro", "Scrivi un altro testo", "dario-id", "Dario")
l2.on_scheda = reg2
svc.avvia(l1)
svc.avvia(l2)
aspetta(lambda: l1.stato == "in_corso" and reg2.tutte(), 5)
verifica("il secondo lavoro compare «in coda»", reg2.tutte() and reg2.tutte()[0][1]["stato"] == "in_coda")
t0 = time.perf_counter()
r = svc.annulla("dario-id", quale="tutti")
dt = time.perf_counter() - t0
verifica("annullo dalla voce senza aspettare la scheda", r["ok"] and dt < SUBITO_S, f"{dt * 1000:.1f} ms")
verifica("in coda annullato: scheda «annullato» in cima (costruita dal thread degli schermi)",
         aspetta(lambda: reg2.tutte()[-1][1]["stato"] == "annullato", 3)
         and reg2.tutte()[-1][1].get("sposta") is not False)
verifica("in corso annullato: scheda «annullato» in cima",
         aspetta(lambda: reg1.tutte() and reg1.tutte()[-1][1]["stato"] == "annullato", 5)
         and reg1.tutte()[-1][1].get("sposta") is not False,
         str([c["stato"] for _, c in reg1.tutte()]))
svc.close()

# ═══════════════════════════ 5. arbitro ═══════════════════════════
sezione("arbitro: in pausa per la voce")
cfg_s = cfg_base(fake.url, agenti_ripresa_s=0.3)
cfg_s.llm_native_url = fake.url
cfg_s.llm_model = MODELLO
svc_s = servizio(cfg_s)
fake.ritardo_pezzo, fake.pezzi = 0.1, 30
fake.copione = [{"content": "y" * 300}, {"content": "z" * 30 + "\nRIASSUNTO: Fatto."}]
reg = Registro()
lav = svc_s.nuovo("altro", "Scrivi un testo lungo", "dario-id", "Dario")
lav.on_scheda = reg
svc_s.avvia(lav)
aspetta(lambda: lav.stato == "in_corso", 5)
time.sleep(0.6)
svc_s.arbitro.voce_occupata()
verifica("«in pausa: sto rispondendo a voce» entro un secondo", aspetta(
    lambda: any(c["avanzamento"].get("pausa") for _, c in reg.tutte()
                if c["tipo"] == "lavoro" and c["stato"] == "in_corso"), 1.2))
fake.ritardo_pezzo, fake.pezzi = 0.0, 4
time.sleep(0.6)
svc_s.arbitro.voce_libera()
item = fine(svc_s)
in_corso = [c for _, c in reg.tutte() if c["stato"] == "in_corso"]
verifica("finita la voce la pausa sparisce e il lavoro finisce",
         item and item["stato"] == "fatto" and in_corso
         and in_corso[-1]["avanzamento"]["pausa"] is False,
         str([c["avanzamento"]["pausa"] for c in in_corso]))
svc_s.close()

# ═══════════════════════════ 6. motore «openai»: il codice a pezzi ═══════════════════════════
sezione("motore «openai» (vLLM): il codice negli argomenti a pezzi")
verifica("argomenti a metà decodificati",
         _decodifica_argomenti('{"percorso": "a.py", "contenuto": "def f():\\n    ret')
         == "def f():\n    ret"
         and _decodifica_argomenti('{"percorso": "a.py"') == "")
cfg_o = cfg_base(fake.url + "/v1")
svc_o = servizio(cfg_o)
LUNGO = "".join(f"def f{i}(x):\n    return x + {i}\n\n\n" for i in range(40))
fake.ritardo_pezzo, fake.pezzi, fake.pezzi_argomenti = 0.02, 30, 60
fake.copione = [
    {"tool_calls": [call("scrivi_file", {"percorso": "molte.py", "contenuto": LUNGO})]},
    {"tool_calls": [call("consegna", {"riassunto": "Fatto.", "esito": "fatto"})]},
]
reg = Registro()
lav = svc_o.nuovo("codice", "Scrivi tante funzioni", "dario-id", "Dario")
lav.on_scheda = reg
svc_o.avvia(lav)
item = fine(svc_o)
flussi = [c["avanzamento"].get("flusso") for _, c in reg.tutte()
          if c["tipo"] == "lavoro" and (c.get("avanzamento") or {}).get("flusso")]
codice = [f for f in flussi if f["tipo"] == "codice"]
verifica("il codice che l'agente sta scrivendo compare mentre arriva",
         item and item["stato"] == "fatto" and codice and "def f" in codice[0]["testo"],
         f"{len(codice)} aggiornamenti col codice, {fake.richieste[-1].get('stream')}")
svc_o.close()
fake.pezzi_argomenti = 2

# ═══════════════════════════ 7. schermi veri: visibilità ═══════════════════════════
sezione("schermi veri (Schermi, senza server): visibilità e cronologia")
cfg_h = Config()
arch = ArchivioSchermi(str(TMP / "schermi.db"))
hub = Schermi(cfg_h, arch, log=LOG.append)
mio, _ = arch.crea_con_token("studio", "dario-id", "Dario")
sogg, _ = arch.crea_con_token("soggiorno")
dario = Mittente("dario-id", "Dario", "amministra", True)
dario_grigio = Mittente("dario-id", "Dario", "familiare", False)
svc = servizio(cfg_base(fake.url))
fake.ritardo_pezzo, fake.pezzi = 0.02, 20
fake.copione = [
    {"content": "Scrivo il programma. " * 10,
     "tool_calls": [call("scrivi_file", {"percorso": "a.py", "contenuto": "print(1)\n"})]},
    {"content": "Ora lo provo. " * 10, "tool_calls": [call("esegui_python", {"percorso": "a.py"})]},
    {"tool_calls": [call("consegna", {"riassunto": "Fatto.", "esito": "fatto"})]},
]
esiti = []
# Un calcolo detto prima: resta «l'ultima cosa mostrata» anche con il lavoro che si aggiorna
hub.invia(schede.calcolo("2+2", "4"), dario)
lav = svc.nuovo("codice", "Scrivi un programma che stampa 1", "dario-id", "Dario")
lav.on_scheda = lambda card: esiti.append(hub.invia(card, dario))
svc.avvia(lav)
fine(svc)
storia_mio = hub.storia(mio["id"])
storia_sogg = hub.storia(sogg["id"])
verifica("solo lo schermo personale di chi l'ha chiesto",
         esiti and all(e["destinatari"] == [mio["nome"]] for e in esiti)
         and not any(c["tipo"] == "lavoro" for c in storia_sogg), str(esiti[:1]))
verifica(f"una scheda sola del lavoro nella cronologia ({len(esiti)} invii)",
         sum(1 for c in storia_mio if c.get("chiave") == f"lavoro:{lav.id}") == 1
         and storia_mio[-1].get("chiave") == f"lavoro:{lav.id}"
         and storia_mio[-1]["stato"] == "fatto", str([c.get("chiave") for c in storia_mio]))
ult = hub.ultima(dario)
verifica("«l'ultima cosa mostrata» è la scheda finale del lavoro (un cambio di stato)",
         ult and ult.get("chiave") == f"lavoro:{lav.id}")
hub.invia(schede.calcolo("3+3", "6"), dario)
hub.invia(schede.lavoro_avanzamento("x", "codice", "in_corso", {}, ident=lav.id), dario)
verifica("un aggiornamento automatico non prende il posto del calcolo detto dopo",
         hub.ultima(dario).get("tipo") == "calcolo")
esiti.clear()
fake.ritardo_pezzo, fake.pezzi = 0.0, 4
fake.copione = [{"tool_calls": [call("consegna", {"riassunto": "Fatto.", "esito": "fatto"})]}]
lav = svc.nuovo("codice", "Un altro programma", "dario-id", "Dario")
lav.on_scheda = lambda card: esiti.append(hub.invia(card, dario_grigio))
svc.avvia(lav)
fine(svc)
verifica("zona grigia: nessuno schermo, mai", esiti and all(
    not e["destinatari"] and e["motivo"] == "zona_grigia" for e in esiti), str(esiti[:1]))

# ═══════════════════════════ 8. senza schermi ═══════════════════════════
sezione("senza schermi")
svc2 = servizio(cfg_base(fake.url))
fake.copione = [{"tool_calls": [call("consegna", {"riassunto": "Fatto.", "esito": "fatto"})]}]
lav = svc2.nuovo("codice", "Un programma", "dario-id", "Dario")
svc2.avvia(lav)
item = fine(svc2)
verifica("senza on_scheda: niente osservatore, nessun thread degli schermi",
         item and item["stato"] == "fatto" and lav.osservatore is None
         and svc2.avanzamento._thread is None)
reg = Registro()
fake.copione = [{"tool_calls": [call("consegna", {"riassunto": "Fatto.", "esito": "fatto"})]}]
lav = svc2.nuovo("codice", "Un programma", "dario-id", "Dario")
lav.on_scheda = reg
lav.segui_schermi = False          # schermi_automatiche spente
svc2.avvia(lav)
fine(svc2)
verifica("schede automatiche spente: solo la scheda finale, come prima",
         lav.osservatore is None and len(reg.tutte()) == 1
         and reg.tutte()[0][1]["stato"] == "fatto")
svc2.close()
svc.close()
fake.ferma() if hasattr(fake, "ferma") else None

print("\nTutto a posto." if not errori else f"\n{errori} errori.")
sys.exit(1 if errori else 0)
