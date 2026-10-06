import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Misura dell'arbitro con l'agente su vLLM sulla stessa GPU della voce (04/10/2026).

Da lanciare **sulla DGX**, nella cartella dei dati (~/calliope: calliope.yaml e
calliope.locale.yaml danno l'Ollama della voce e agenti_url), con l'interprete di Calliope:

    cd ~/calliope && CALLIOPE_LLM_PROFILO=gemma4-26b-ollama CALLIOPE_LLM_KEEP_ALIVE=-1m \\
        <venv>/bin/python <sorgente>/prove/misura_arbitro_vllm.py [giri] [--carichi 3]
        [--fasi base,senza,chiusura,pausa] [--token 1500]

Tre fasi con le stesse domande (prompt e tool veri, come prova_regressione: prefisso vero):
1. **base**: niente carico su vLLM;
2. **senza arbitro**: `--carichi` generazioni lunghe su vLLM in ciclo (relazioni da ~1500
   token, come lavori, scrittore e archivio), sempre accese;
3. **chiusura** (con arbitro): le stesse, attraverso `ClienteCedevole`; per ogni domanda la
   voce fa come main.py: `voce_occupata` all'inizio del parlato, 1 s di parlato + Whisper, la
   risposta, `voce_libera` (ripresa dopo `agenti_ripresa_s`); l'arbitro chiude gli stream;
4. **pausa** (04/10): come la 3, ma l'arbitro mette vLLM in pausa (`/pause?mode=keep`, serve
   la modalità sviluppo: `vllm.sh agente`, `PAUSA=1`) invece di chiudere: le generazioni
   lunghe devono arrivare in fondo anche con una domanda ogni ~7 s.
Per ogni domanda la prima frase come in main.py (la prima frase intera per il TTS); tra una
domanda e l'altra una pausa di `PAUSA_S` (la persona ascolta e pensa). Alla fine mediana,
p90 e massimo per fase, pezzi generati da vLLM al secondo (anche quelli delle generazioni poi
chiuse), token al secondo delle generazioni arrivate in fondo, generazioni finite, stream
chiusi dall'arbitro, tempi di pausa e ripresa.

Il servizio calliope vivo usa lo stesso Ollama: stesso modello, num_ctx e keep_alive del
profilo (niente ricaricamenti). Non tocca né vLLM né Ollama oltre alle richieste.
"""

import statistics
import threading
import time

from calliope.agenti.arbitro import Arbitro, ClienteCedevole, PausaServer
from calliope.contesto import finestra
from calliope.agenti.impostazioni import carica, stessa_gpu
from calliope.agenti.remoto import Interrotto
from calliope.agenti.remoto_openai import ClienteOpenAI
from calliope.brain import Brain
from calliope.config import load_config
from calliope.documenti.formato import FORMATI
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from calliope.tts import split_sentences

argv = sys.argv[1:]
GIRI = int(argv[0]) if argv and argv[0].isdigit() else 1
CARICHI = int(argv[argv.index("--carichi") + 1]) if "--carichi" in argv else 3
TOKEN = int(argv[argv.index("--token") + 1]) if "--token" in argv else 1500   # per generazione
FASI = (argv[argv.index("--fasi") + 1].split(",") if "--fasi" in argv
        else ["base", "senza", "chiusura", "pausa"])
PARLATO_S = 1.0          # dall'inizio del parlato alla trascrizione pronta
PAUSA_S = 4.0            # tra la fine di una risposta e la domanda dopo
DOMANDE = ["Che ore sono?", "Quanto fa 17 per 23?", "Come stai oggi?",
           "Raccontami una barzelletta breve.", "Che giorno è oggi?",
           "Quanto fa la radice quadrata di 144?", "Dammi un consiglio per dormire meglio.",
           "Come si dice grazie in inglese?", "Che ore saranno tra tre ore?",
           "Dimmi una curiosità sulla luna."]
TEMI = ["la manutenzione di un impianto fotovoltaico", "la storia dei treni in Italia",
        "come organizzare una cantina", "il risparmio energetico in un condominio",
        "la coltivazione dei pomodori sul balcone"]


class SpeakerCtx:
    current_speaker, current_level, profile_level = "Dario", "amministra", "amministra"
    identified_by, from_session, conferma_breve, sfida, sfida_superata = "voce", False, False, None, False
    livello = "amministra"


class Prof:
    id, name, admin = "dario-id", "Dario", True


class Speakers:
    def get(self, n):
        return Prof() if n == "Dario" else None

    def known_speakers(self):
        return ["Dario"]


class Carico:
    """Una generazione lunga dopo l'altra su vLLM, finché `fermo` non è acceso."""

    def __init__(self, cliente, modello, n, fermo):
        self.cliente, self.modello, self.n, self.fermo = cliente, modello, n, fermo
        self.token, self.richieste, self.errori, self.pezzi = 0, 0, 0, 0
        self.th = threading.Thread(target=self.gira, daemon=True, name=f"carico-{n}")

    def gira(self):
        k = self.n
        while not self.fermo.is_set():
            tema = TEMI[k % len(TEMI)]
            k += 1
            body = {"model": self.modello, "think": False,
                    "options": {"temperature": 0.7, "num_predict": TOKEN},
                    "messages": [{"role": "user", "content":
                                  f"Scrivi una relazione lunga e dettagliata, in italiano, su "
                                  f"{tema}, con almeno otto sezioni. Variante {k}."}]}
            try:
                out = self.cliente.chat(body, controlla=self._controlla, su_pezzo=self._pezzo)
                self.token += int(out.get("eval") or 0)
                self.richieste += 1
            except Interrotto:
                pass
            except Exception:  # noqa: BLE001
                self.errori += 1
                time.sleep(1)

    def _pezzo(self, _t):
        self.pezzi += 1

    def _controlla(self):
        if self.fermo.is_set():
            raise Interrotto()


def quantile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else 0.0


def prima_frase(b, domanda):
    b.history = []
    t0 = time.perf_counter()
    primo = None
    for frase in split_sentences(b.stream_reply(domanda, "amministra")):
        frase = b.strip_tool_mentions(frase)
        if frase and primo is None:
            primo = time.perf_counter() - t0
    return primo, time.perf_counter() - t0


def fase(nome, b, cfg, imp, arbitro=None, carichi=0):
    fermo = threading.Event()
    cl = []
    for i in range(carichi):
        cli = ClienteOpenAI(imp.url)
        if arbitro is not None:
            cli = ClienteCedevole(cli, arbitro)
        cl.append(Carico(cli, imp.modello, i, fermo))
    for c in cl:
        c.th.start()
    if carichi:
        time.sleep(8)                  # le generazioni a regime
    t_inizio = time.monotonic()
    tok0 = sum(c.token for c in cl)
    pz0 = sum(c.pezzi for c in cl)
    fin0 = sum(c.richieste for c in cl)
    prime, totali = [], []
    for giro in range(GIRI):
        for d in DOMANDE:
            if arbitro is not None:
                arbitro.voce_occupata()
            time.sleep(PARLATO_S)
            if arbitro is not None:
                arbitro.voce_occupata()            # inizio della risposta (main.py)
            p, t = prima_frase(b, d)
            if arbitro is not None:
                arbitro.voce_libera()
            prime.append(p or t)
            totali.append(t)
            print(f"  [{nome}] {d!r}: prima frase {p or 0:.2f}s, risposta {t:.2f}s", flush=True)
            time.sleep(PAUSA_S)
    durata = time.monotonic() - t_inizio
    fermo.set()
    for c in cl:
        try:
            c.cliente.interrompi()
        except Exception:  # noqa: BLE001
            pass
        c.th.join(10)
    tok = sum(c.token for c in cl) - tok0
    pz = sum(c.pezzi for c in cl) - pz0
    fin = sum(c.richieste for c in cl) - fin0
    ced = sum(getattr(c.cliente, "cessioni", 0) for c in cl)
    err = sum(c.errori for c in cl)
    extra = ""
    if arbitro is not None and arbitro.pausa is not None:
        ps = arbitro.pausa
        tp = sorted(ps.tempi_pausa) or [0.0]
        tr = sorted(ps.tempi_ripresa) or [0.0]
        extra = (f"; pause {arbitro.pause}, riprese {arbitro.riprese}, ripieghi "
                 f"{arbitro.ripieghi}; pausa {statistics.median(tp) * 1000:.0f} ms (max "
                 f"{tp[-1] * 1000:.0f}), ripresa {statistics.median(tr) * 1000:.0f} ms (max "
                 f"{tr[-1] * 1000:.0f})")
        arbitro.chiudi()
    print(f"{nome}: prima frase mediana {statistics.median(prime):.2f}s, p90 "
          f"{quantile(prime, 0.9):.2f}s, massimo {max(prime):.2f}s (n={len(prime)}); vLLM "
          f"{pz / durata:.0f} pezzi/s, {tok / durata:.0f} token/s finiti, {fin} generazioni "
          f"finite in {durata:.0f}s, stream ceduti {ced}, errori {err}{extra}", flush=True)
    return {"fase": nome, "mediana": statistics.median(prime), "p90": quantile(prime, 0.9),
            "massimo": max(prime), "token_s": tok / durata, "pezzi_s": pz / durata,
            "finite": fin, "cessioni": ced}


cfg = load_config()
imp = carica(cfg)
if imp is None or imp.motore != "openai":
    sys.exit("serve agenti_url verso vLLM (…/v1) in calliope.locale.yaml")
print(f"voce {cfg.llm_model} su {cfg.llm_native_url} (num_ctx {finestra(cfg)}, keep_alive "
      f"{cfg.llm_keep_alive}); agente {imp.modello} su {imp.url}; stessa GPU: "
      f"{stessa_gpu(cfg, imp)}; {CARICHI} carichi, {GIRI} giri × {len(DOMANDE)} domande",
      flush=True)
reg = build_registry(biblioteca=True, citazioni=True, documenti=FORMATI, casa=True,
                     schermi=True, agenti=True)
ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(), speaker=None)
b = Brain(cfg, reg, ctx)
t = time.perf_counter()
b.warmup()
print(f"riscaldamento {time.perf_counter() - t:.2f}s", flush=True)
esiti = []
rip = float(cfg.agenti_ripresa_s)
if "base" in FASI:
    esiti.append(fase("base", b, cfg, imp))
if "senza" in FASI:
    esiti.append(fase("senza arbitro", b, cfg, imp, carichi=CARICHI))
if "chiusura" in FASI:
    esiti.append(fase("chiusura", b, cfg, imp, Arbitro(True, rip), CARICHI))
if "pausa" in FASI:
    arb = Arbitro(True, rip, pausa=PausaServer(imp.url))
    time.sleep(1)
    if arb.pausa.disponibile is not True:
        print("pausa: vLLM senza /pause (modalità sviluppo spenta): fase saltata", flush=True)
    else:
        esiti.append(fase("pausa", b, cfg, imp, arb, CARICHI))
print("\nfase            mediana   p90   massimo  pezzi/s finiti/s finite")
for e in esiti:
    print(f"{e['fase']:<15} {e['mediana']:6.2f}s {e['p90']:5.2f}s {e['massimo']:6.2f}s "
          f"{e.get('pezzi_s', 0):8.0f} {e['token_s']:8.0f} {e.get('finite', 0):6d}")
