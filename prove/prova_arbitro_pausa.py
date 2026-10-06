import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della pausa di vLLM per l'arbitro (04/10/2026).

Con la modalità sviluppo di vLLM (`VLLM_SERVER_DEV_MODE=1`) l'arbitro mette il server
dell'agente in pausa (`POST /pause?mode=keep`) quando si parla con Calliope e lo riprende dopo
(`POST /resume`), invece di chiudere gli stream. Qui, con il vLLM finto di
`prove/ollama_finto.py` (`dev = True`: in pausa gli stream non mandano pezzi):
- `PausaServer`: sonda, pausa, ripresa; senza modalità sviluppo (404) e con il server giù;
- `pausa_server`: solo motore OpenAI, senza tunnel, mai il server della voce, spegnibile;
- una generazione congelata e ripresa: nessuno stream chiuso, nessun pezzo durante la voce,
  la ripresa dopo `ripresa_s`, il testo intero con una richiesta sola; la voce non aspetta
  nemmeno con una pausa lenta; `deve_cedere` falso; «in pausa» per gli schermi;
- senza `/pause`: si chiudono gli stream come prima e la richiesta si rifà;
- pausa che non risponde e pausa con errore: ripiego (stream chiuso) e ripresa mandata
  comunque;
- lo scrittore dell'ufficio che la voce aspetta: il server riparte subito, l'altro stream si
  chiude come prima, lo scrittore finisce durante il turno; dal turno dopo si congela;
- più turni di fila, tenuta massima senza «libera», vLLM rimasto in pausa all'avvio,
  `chiudi()`, annullo durante la pausa;
- un lavoro vero (`Lavori`) con il finto in modalità sviluppo: passo congelato e non rifatto,
  `close()` lo riprende.
"""

import tempfile
import threading
import time
from pathlib import Path

from calliope.agenti import Lavori, carica
from calliope.agenti.arbitro import Arbitro, ClienteCedevole, PausaServer
from calliope.agenti.impostazioni import Impostazioni, pausa_server
from calliope.agenti.remoto import Interrotto
from calliope.agenti.remoto_openai import ClienteOpenAI
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from prove.ollama_finto import FakeOllama

TMP = Path(tempfile.mkdtemp(prefix="calliope-arbitro-pausa-"))
MODELLO = "qwen3.6-35b"
SUBITO_S = 0.15
errori = 0
LOG: list[str] = []
T0 = time.perf_counter()


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def aspetta(cond, s=5.0):
    t = time.monotonic() + s
    while time.monotonic() < t:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


def body(testo="ciao"):
    return {"model": MODELLO, "messages": [{"role": "user", "content": testo}],
            "options": {"num_predict": 50}}


class Corsa:
    """Una richiesta in un thread: esito, testo, tempo."""

    def __init__(self, cliente, testo="ciao"):
        self.cliente, self.testo = cliente, testo
        self.esito, self.content, self.fine = None, "", None
        self.th = threading.Thread(target=self._gira, daemon=True)
        self.th.start()

    def _gira(self):
        try:
            self.content = self.cliente.chat(body(self.testo))["content"]
            self.esito = "ok"
        except Interrotto:
            self.esito = "interrotto"
        except Exception as e:  # noqa: BLE001
            self.esito = f"errore {type(e).__name__}"
        self.fine = time.monotonic()


fake = FakeOllama(modelli=(MODELLO,)).avvia()
fake.dev = True
URL = fake.url + "/v1"
TESTO = "abcdefghij" * 6
fake.predefinita = {"content": TESTO}
fake.pezzi, fake.ritardo_pezzo = 30, 0.04      # ~1,2 s di generazione

# ═══════════════════════════ 1. PausaServer ═══════════════════════════
sezione("PausaServer: sonda, pausa, ripresa")
ps = PausaServer(URL, log=LOG.append)
verifica("URL: radice senza /v1", ps.url == fake.url.lower())
verifica("sonda: modalità sviluppo, non in pausa", ps.sonda() is False and ps.disponibile is True)
verifica("pausa", ps.pausa() and not fake._libero.is_set() and ps.da_riprendere)
verifica("sonda: in pausa", ps.sonda() is True)
verifica("ripresa", ps.riprendi() and fake._libero.is_set() and not ps.da_riprendere)
ps.chiudi()

fake2 = FakeOllama(modelli=(MODELLO,)).avvia()        # vLLM senza modalità sviluppo
ps2 = PausaServer(fake2.url + "/v1", log=LOG.append)
verifica("senza modalità sviluppo: 404, non disponibile, niente da riprendere",
         ps2.sonda() is None and not ps2.pausa() and ps2.disponibile is False
         and not ps2.da_riprendere)
verifica("…e lo dice una volta nel log", sum("senza /pause" in r for r in LOG) == 1)
verifica("ripresa senza modalità sviluppo: niente da fare", ps2.riprendi())
ps2.chiudi()
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
porta_chiusa = s.getsockname()[1]
s.close()
ps3 = PausaServer(f"http://127.0.0.1:{porta_chiusa}/v1", timeout_s=0.5, log=LOG.append)
# (su Windows una porta chiusa su 127.0.0.1 non rifiuta subito: ConnectTimeout, non partita)
verifica("server giù: la pausa fallisce e non c'è niente da riprendere",
         not ps3.pausa() and not ps3.da_riprendere)
ps3.chiudi()

# ═══════════════════════════ 2. quando si usa ═══════════════════════════
sezione("pausa_server: quando si usa")


def cfgv(**kw):
    cfg = Config()
    cfg.llm_native_url = "http://127.0.0.1:11434"
    cfg.llm_base_url = "http://127.0.0.1:11434/v1"
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def imp(url, modo="diretto"):
    return Impostazioni(modo, url, MODELLO, motore="openai" if url.endswith("/v1") else "ollama")


verifica("DGX: vLLM dell'agente accanto all'Ollama della voce",
         isinstance(pausa_server(cfgv(), imp("http://127.0.0.1:8000/v1")), PausaServer))
verifica("mai con l'Ollama (API nativa)", pausa_server(cfgv(), imp("http://127.0.0.1:11434")) is None)
verifica("mai con il tunnel", pausa_server(cfgv(), imp("http://127.0.0.1:11436/v1", "tunnel")) is None)
verifica("mai il server della voce (voce su vLLM, stesso server)",
         pausa_server(cfgv(llm_base_url="http://localhost:8000/v1"),
                      imp("http://127.0.0.1:8000/v1")) is None)
verifica("voce su un altro vLLM (8001): sì",
         pausa_server(cfgv(llm_base_url="http://127.0.0.1:8001/v1"),
                      imp("http://127.0.0.1:8000/v1")) is not None)
verifica("agenti_pausa_vllm: false", pausa_server(cfgv(agenti_pausa_vllm=False),
                                                  imp("http://127.0.0.1:8000/v1")) is None)
verifica("nessun agente", pausa_server(cfgv(), None) is None)


def arbitro(url=URL, ripresa_s=0.3, **kw):
    timeout = kw.pop("timeout_s", 1.0)
    a = Arbitro(True, ripresa_s, pausa=PausaServer(url, timeout_s=timeout, log=LOG.append),
                log=LOG.append, **kw)
    aspetta(lambda: a.pausa.disponibile is not None, 2)
    return a


# ═══════════════════════════ 3. generazione congelata ═══════════════════════════
sezione("generazione congelata e ripresa (niente passo perso)")
arb = arbitro()
cli = ClienteOpenAI(URL)
ced = ClienteCedevole(cli, arb)
fake.richieste.clear()
fake.chiamate_pausa.clear()
interrotte = fake.interrotte
c = Corsa(ced)
aspetta(lambda: len(fake.pezzi_tempi) > 0 and len(cli._risposte) == 1, 3)
time.sleep(0.3)
fake.ritardo_pausa = 0.3                      # una pausa lenta: la voce non deve aspettarla
t = time.perf_counter()
arb.voce_occupata()
dt = time.perf_counter() - t
verifica("la voce non aspetta la pausa", dt < SUBITO_S, f"{dt * 1000:.2f} ms")
verifica("pausa chiesta", aspetta(lambda: fake.chiamate_pausa == ["pausa"], 2))
fake.ritardo_pausa = 0.0
aspetta(lambda: arb._in_pausa, 2)
t_pausa = time.monotonic()
verifica("deve_cedere falso: lo stream resta aperto, congelato", not arb.deve_cedere(URL))
verifica("«in pausa» per gli schermi", arb.in_pausa())
time.sleep(0.6)                                # la voce risponde
arb.voce_libera()
t_libera = time.monotonic()
verifica("ripresa dopo ripresa_s", aspetta(lambda: fake.chiamate_pausa == ["pausa", "ripresa"]
                                           and not arb._in_pausa, 2))
t_ripresa = time.monotonic()
c.th.join(5)
durante = [x for x in fake.pezzi_tempi if t_pausa + 0.05 < x < t_libera + 0.25]
verifica("nessun pezzo mentre la voce parlava", not durante, f"{len(durante)} pezzi")
verifica("ripresa non prima di ripresa_s", t_ripresa - t_libera >= 0.28,
         f"{t_ripresa - t_libera:.2f}s")
verifica("testo intero, una richiesta sola, nessuno stream chiuso",
         c.esito == "ok" and c.content == TESTO and len(fake.richieste) == 1
         and fake.interrotte == interrotte and arb.cessioni == 0 and ced.cessioni == 0,
         f"{c.esito} richieste={len(fake.richieste)} cessioni={arb.cessioni}")
verifica("contatori: una pausa, una ripresa", arb.pause == 1 and arb.riprese == 1)

sezione("richiesta nuova durante la voce: aspetta, poi parte")
fake.chiamate_pausa.clear()
arb.voce_occupata()
aspetta(lambda: arb._in_pausa, 2)
c = Corsa(ced, "nuova")
time.sleep(0.4)
verifica("non parte mentre si parla", len(fake.richieste) == 1)
arb.voce_libera()
c.th.join(5)
verifica("parte dopo la ripresa e finisce", c.esito == "ok" and len(fake.richieste) == 2)

sezione("più turni di fila")
fake.chiamate_pausa.clear()
fake.richieste.clear()
c = Corsa(ced)
aspetta(lambda: len(cli._risposte) == 1, 3)
for _ in range(5):
    arb.voce_occupata()
    time.sleep(0.12)
    arb.voce_libera()
    time.sleep(0.1)                           # meno della ripresa: resta in pausa
aspetta(lambda: not arb._in_pausa and fake._libero.is_set(), 3)
c.th.join(5)
verifica("una pausa sola per turni ravvicinati, poi ripreso",
         fake.chiamate_pausa == ["pausa", "ripresa"], str(fake.chiamate_pausa))
verifica("…testo intero senza richieste rifatte", c.esito == "ok" and c.content == TESTO
         and len(fake.richieste) == 1)
fake.chiamate_pausa.clear()
for _ in range(3):
    arb.voce_occupata()
    aspetta(lambda: arb._in_pausa, 2)
    arb.voce_libera()
    aspetta(lambda: not arb._in_pausa, 2)
verifica("turni distanziati: pausa e ripresa a ogni turno",
         fake.chiamate_pausa == ["pausa", "ripresa"] * 3, str(fake.chiamate_pausa))

sezione("annullo durante la pausa")
c = Corsa(cli)                                 # client nudo: lo chiude il lavoro
aspetta(lambda: len(cli._risposte) == 1, 3)
arb.voce_occupata()
aspetta(lambda: arb._in_pausa, 2)
t = time.monotonic()
cli.interrompi()
c.th.join(3)
verifica("lo stream congelato si chiude subito", c.esito == "interrotto"
         and c.fine - t < 1.0, f"{c.esito} {(c.fine or 0) - t:.2f}s")
arb.voce_libera()
aspetta(lambda: not arb._in_pausa, 2)

sezione("tenuta massima senza «libera»")
arb_t = arbitro(tenuta_max_s=0.5)
fake.chiamate_pausa.clear()
arb_t.voce_occupata()
verifica("ripreso dopo tenuta_max_s anche se la voce non dice «libera»",
         aspetta(lambda: fake.chiamate_pausa == ["pausa", "ripresa"] and fake._libero.is_set(),
                 2.5), str(fake.chiamate_pausa))
arb_t.chiudi()

# ═══════════════════════════ 4. senza /pause e ripieghi ═══════════════════════════
sezione("senza modalità sviluppo: si chiudono gli stream come prima")
fake2.predefinita = {"content": TESTO}
fake2.pezzi, fake2.ritardo_pezzo = 30, 0.04
arb2 = arbitro(fake2.url + "/v1")
verifica("la sonda all'avvio la scopre assente", arb2.pausa.disponibile is False)
cli2 = ClienteOpenAI(fake2.url + "/v1")
ced2 = ClienteCedevole(cli2, arb2)
fake2.richieste.clear()
c = Corsa(ced2)
aspetta(lambda: len(cli2._risposte) == 1, 3)
arb2.voce_occupata()
verifica("stream chiuso subito", aspetta(lambda: fake2.interrotte >= 1, 2))
verifica("deve_cedere vero", arb2.deve_cedere(fake2.url))
arb2.voce_libera()
c.th.join(6)
verifica("rifatta dopo la voce, testo intero", c.esito == "ok" and c.content == TESTO
         and len(fake2.richieste) == 2 and ced2.cessioni == 1)
arb2.chiudi()

for nome, imposta in (("pausa che non risponde", {"ritardo_pausa": 0.8}),
                      ("pausa con errore 500", {"stato_pausa": 500})):
    sezione(f"{nome}: ripiego e ripresa comunque")
    arb3 = arbitro(timeout_s=0.3)
    ced3 = ClienteCedevole(ClienteOpenAI(URL), arb3)
    fake.richieste.clear()
    fake.chiamate_pausa.clear()
    interrotte = fake.interrotte
    c = Corsa(ced3)
    aspetta(lambda: len(fake.pezzi_tempi) > 0 and len(fake.richieste) == 1, 3)
    for k, v in imposta.items():
        setattr(fake, k, v)
    arb3.voce_occupata()
    verifica("stream chiuso (ripiego per il turno)", aspetta(lambda: fake.interrotte > interrotte, 3)
             and arb3.ripieghi == 1)
    verifica("ripresa mandata comunque", aspetta(lambda: "ripresa" in fake.chiamate_pausa
                                                 and fake._libero.is_set(), 3),
             str(fake.chiamate_pausa))
    verifica("deve_cedere vero nel turno del ripiego", arb3.deve_cedere(URL))
    fake.ritardo_pausa, fake.stato_pausa = 0.0, 200
    arb3.voce_libera()
    c.th.join(6)
    verifica("richiesta rifatta dopo la voce, testo intero", c.esito == "ok"
             and c.content == TESTO and len(fake.richieste) == 2)
    fake.chiamate_pausa.clear()
    arb3.voce_occupata()
    verifica("al turno dopo si riprova la pausa", aspetta(lambda: fake.chiamate_pausa[:1] == ["pausa"], 2))
    arb3.voce_libera()
    aspetta(lambda: not arb3._in_pausa, 2)
    arb3.chiudi()

# ═══════════════════════════ 5. scrittore dell'ufficio ═══════════════════════════
sezione("scrittore dell'ufficio che la voce aspetta")
arb = arbitro(ripresa_s=0.3)
cli = ClienteOpenAI(URL)
agente = ClienteCedevole(cli, arb)                 # un lavoro dell'agente
fake.richieste.clear()
fake.chiamate_pausa.clear()
interrotte = fake.interrotte
ca = Corsa(agente, "agente")
aspetta(lambda: len(fake.richieste) == 1 and len(cli._risposte) == 1, 3)
arb.voce_occupata()                                # la domanda
aspetta(lambda: arb._in_pausa, 2)
verifica("l'agente è congelato", fake.interrotte == interrotte)
t = time.monotonic()
scr = Corsa(ClienteCedevole(cli, arb, dalla_voce=True), "scrittore")
verifica("il server riparte subito per lo scrittore",
         aspetta(lambda: fake.chiamate_pausa == ["pausa", "ripresa"], 1.0)
         and time.monotonic() - t < 0.5, f"{time.monotonic() - t:.2f}s")
verifica("l'altro stream di quel server si chiude come prima",
         aspetta(lambda: fake.interrotte > interrotte, 2))
scr.th.join(5)
verifica("lo scrittore finisce durante il turno della voce",
         scr.esito == "ok" and scr.content == TESTO and arb._attiva)
arb.voce_occupata()                                # inizio della risposta, stesso turno
time.sleep(0.2)
verifica("nello stesso turno niente pausa di nuovo", fake.chiamate_pausa == ["pausa", "ripresa"])
arb.voce_libera()
ca.th.join(6)
verifica("il lavoro dell'agente si rifà dopo la voce", ca.esito == "ok" and ca.content == TESTO
         and agente.cessioni == 1)

sezione("scrittore partito in un turno, voce al turno dopo: si congela")
fake.chiamate_pausa.clear()
fake.richieste.clear()
interrotte = fake.interrotte
arb.voce_occupata()                                # turno N (lo scrittore nasce qui)
aspetta(lambda: arb._in_pausa, 2)
scr = Corsa(ClienteCedevole(cli, arb, dalla_voce=True), "scrittore")
aspetta(lambda: len(cli._risposte) == 1 and not arb._in_pausa, 2)
arb.voce_libera(0.0)
time.sleep(0.15)
arb.voce_occupata()                                # turno N+1
verifica("pausa al turno dopo", aspetta(lambda: arb._in_pausa, 2), str(fake.chiamate_pausa))
time.sleep(0.4)
verifica("lo scrittore è congelato, non chiuso", fake.interrotte == interrotte
         and scr.esito is None)
arb.voce_libera()
scr.th.join(6)
verifica("…e finisce dopo la ripresa con una richiesta sola", scr.esito == "ok"
         and scr.content == TESTO and len(fake.richieste) == 1)
arb.chiudi()

# ═══════════════════════════ 6. ripresa garantita ═══════════════════════════
sezione("ripresa garantita: avvio e chiusura")
fake._libero.clear()                               # vLLM rimasto in pausa (Calliope morta)
LOG.clear()
arb = arbitro()
verifica("all'avvio un vLLM rimasto in pausa riparte", aspetta(lambda: fake._libero.is_set(), 2)
         and any("rimasto in pausa" in r for r in LOG))
arb.voce_occupata()
aspetta(lambda: arb._in_pausa, 2)
t = time.monotonic()
arb.chiudi()
verifica("chiudi() durante la voce: ripreso subito", fake._libero.is_set()
         and time.monotonic() - t < 1.0, f"{time.monotonic() - t:.2f}s")
arb.voce_occupata()
time.sleep(0.2)
verifica("dopo chiudi() niente più pause", fake._libero.is_set())

# ═══════════════════════════ 7. un lavoro vero ═══════════════════════════
sezione("lavoro dell'agente (Lavori) con la pausa")
cfg = Config()
cfg.agenti_url = URL
cfg.agenti_modello = MODELLO
cfg.agenti_risultati = str(TMP / "risultati")
cfg.agenti_sandbox = str(TMP / "sandbox")
cfg.agenti_sandbox_motore = "processo"
cfg.agenti_dimostrazione = False
cfg.agenti_modelli = str(TMP / "modelli")
cfg.llm_native_url = "http://127.0.0.1:11434"
cfg.agenti_ripresa_s = 0.2
svc = Lavori(cfg, carica(cfg), log=LOG.append, formati=FORMATI)
verifica("Lavori: arbitro con la pausa del server", svc.arbitro.pausa is not None
         and svc.arbitro.pausa.url == fake.url.lower())
aspetta(lambda: svc.arbitro.pausa.disponibile is True, 2)
fake.predefinita = {"content": "Fatto."}
fake.ritardo_pezzo, fake.pezzi = 0.1, 25
fake.copione = [{"content": "y" * 250}, {"content": "z" * 30 + "\nRIASSUNTO: Fatto il lavoro."}]
fake.richieste.clear()
fake.chiamate_pausa.clear()
interrotte = fake.interrotte
lav = svc.nuovo("altro", "Scrivi un testo lungo", "dario-id", "Dario")
svc.avvia(lav)
aspetta(lambda: len(fake.richieste) >= 1 and lav.stato == "in_corso", 5)
time.sleep(0.5)
svc.arbitro.voce_occupata()
aspetta(lambda: svc.arbitro._in_pausa, 2)
time.sleep(0.5)
svc.arbitro.voce_libera()
verifica("il lavoro finisce", aspetta(lambda: lav.stato == "fatto", 15), lav.stato)
verifica("passo congelato, non rifatto: nessuno stream chiuso, nessun cedimento",
         fake.interrotte == interrotte and lav.cedimenti == 0 and len(fake.richieste) == 1,
         f"interrotte={fake.interrotte - interrotte} cedimenti={lav.cedimenti} "
         f"richieste={len(fake.richieste)}")
svc.arbitro.voce_occupata()
aspetta(lambda: svc.arbitro._in_pausa, 2)
svc.close()
verifica("close() riprende il server", fake._libero.is_set())

fake.ferma()
fake2.ferma()
print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
sys.exit(1 if errori else 0)
