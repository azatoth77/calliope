"""
La «voce ferma» dell'arbitro della memoria dopo una frase accettata (18/10/2026, issue #157).

    python prove/prova_arbitro_quiete.py

Caso vero: sulla DGX la «voce ferma» unica (`arbitro_memoria.QUIETE`) restava occupata dalla
prima frase dal telefono fino al riavvio (849 minuti), perché il VAD dice «libera» solo per una
frase buttata e nessuno la liberava a fine turno. Qui, con il collegamento vero di main.py
(`Avvio._arbitro_memoria`, corsie insieme) e un `Ciclo` vero con il microfono di un satellite
finto (`AscoltoRemoto` vero, server finto): una frase accettata, il turno risponde, all'inizio
del giro dopo la voce è libera. Contrari: una frase buttata la libera come prima; una corsia
che parla ancora tiene la voce occupata anche quando l'altra finisce il turno; chi parla
da poco non è liberato dalla tenuta massima; un turno lungo vero (l'ultimo pezzo al tetto,
Whisper, un tool lento, una risposta lunga) non la fa scattare, perché la risposta la fa
ripartire (`Ciclo._prepara_risposta`) e un segnale occupato vale un segno; un secondo avvio
nello stesso processo (un conto per thread nuovo, non quello del primo con un thread morto).
Poi la tenuta massima: oltre `tenuta_max_s` senza un segno la voce torna libera da sé, con la
riga nel log, il conto nella riga del minuto dell'arbitro in ombra (`tenute_voce`) e nella
storia di `calliope stato --memoria --storia`. Nomi di fantasia, niente rete né audio: ~2 s.
"""
import os
import queue
import sys
import tempfile
import threading
import time
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")     # le emoji del Ciclo su una console non UTF-8

import numpy as np  # noqa: E402

from calliope import arbitro_memoria as am  # noqa: E402
from calliope import arbitro_ombra as AO  # noqa: E402
from calliope.main import Avvio  # noqa: E402
from calliope.satellite import protocollo as P  # noqa: E402
from calliope.satellite.server import AscoltoRemoto  # noqa: E402

import prova_eventi_ciclo as pe  # noqa: E402  (Ciclo vero con Brain a copione)

errori = 0


def verifica(nome, ok, info=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({info})" if info and not ok else ""),
          flush=True)


class Orologio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# ─────────────────────────── il satellite finto ───────────────────────────
class Collegamento:
    """Un satellite collegato: a ogni «ascolta» manda una frase (o una frase buttata)."""
    canale, satellite, riprese, eco = "wifi", {"nome": "telefono di prova"}, {}, None

    def __init__(self, server):
        self.server = server
        self.scarta = False

    def ritardo(self):
        return 0.0

    def invia(self, **d):
        if d.get("tipo") != "ascolta":
            return True
        lid = d["id"]
        pcm = P.a_pcm(np.zeros(1600, dtype=np.float32))
        ev = self.server.eventi
        ev.put((self, "audio", {"id": lid, "pcm": pcm}))
        if self.scarta:                          # una frase buttata, poi quella buona
            self.scarta = False
            ev.put((self, "scartata", {"id": lid}))
            ev.put((self, "audio", {"id": lid, "pcm": pcm}))
        ev.put((self, "frase_finita", {"id": lid, "fa_s": 1.0, "woke": True}))
        return True


class Server:
    insieme = False

    def __init__(self):
        self.eventi = queue.Queue()
        self.coll = Collegamento(self)

    def attendi_pronto(self, sat_id=None):
        return self.coll

    def attivo_pronto(self, sat_id=None):
        return self.coll


# ─────────────────────────── 1. il collegamento di main.py ───────────────────────────
print("— una frase da un satellite: il turno finisce, la voce è libera")
tmp = tempfile.mkdtemp(prefix="arbitro-quiete-")
b, c, voce, stt, turni, annunci, registri = pe.prepara(
    tmp, [[("text", "Sono le dieci.")], [("text", "Fuori piove.")],
          [("text", "Il Po è lungo 652 chilometri.")]], modo="spento")
cfg = b.cfg
cfg.arbitro_memoria = AO.OMBRA
cfg.turn_log_dir = tmp
c.s.barge_in = False                  # il nome durante la risposta qui non serve
q = am.QUIETE
q.segnali, q._voce = [], False
avvio = types.SimpleNamespace(
    s=types.SimpleNamespace(stt=types.SimpleNamespace(), stanza=None, guardia_stanza=None,
                            lavori=None),
    cfg=cfg, varco=types.SimpleNamespace(attivi=0), insieme=True,
    listener=types.SimpleNamespace(on_speech_start=None, on_speech_end=None), conv_arch=None)
Avvio._arbitro_memoria(avvio)
ombra = avvio.s.arbitro_ombra
try:
    srv = Server()
    lst = AscoltoRemoto(srv, cfg, log=lambda m: None, sat_id="tel")
    lst.on_speech_start, lst.on_speech_end = (avvio.listener.on_speech_start,
                                              avvio.listener.on_speech_end)
    c.listener = lst
    verifica("main.py: la tenuta massima dalla configurazione (frase più lunga + 60 s)",
             q.tenuta_max_s == max(am.Quiete.TENUTA_MAX_S, cfg.max_utterance_s + 60.0),
             str(q.tenuta_max_s))

    pe.giro(c, stt, "Calliope, che ore sono?")
    verifica("la frase del satellite ha risposto", "Sono le dieci." in " ".join(voce.detto),
             str(voce.detto))
    verifica("durante il turno la voce del satellite resta occupata (on_end non arriva)",
             q.occupata() == "voce", q.occupata())
    c._inizio_giro()
    verifica("all'inizio del giro dopo la voce è libera (#157: prima restava «voce»)",
             q.occupata() == "", q.occupata())

    # Contrario: una frase buttata la libera il VAD, come prima, e la buona la occupa di nuovo
    srv.coll.scarta = True
    pe.giro(c, stt, "Calliope, che tempo fa?")
    verifica("contrario: frase buttata e poi quella buona → occupata fino a fine turno",
             q.occupata() == "voce", q.occupata())
    c._inizio_giro()
    verifica("… e libera dopo", q.occupata() == "", q.occupata())

    # Contrario: un'altra corsia (il microfono locale, un altro thread) parla ancora
    parla = threading.Event()
    finito = threading.Event()

    def altra_corsia():
        avvio.listener.on_speech_start()      # qualcuno comincia a parlare qui
        parla.set()
        finito.wait(5)
        avvio.listener.on_speech_end()        # e la sua frase si butta

    th = threading.Thread(target=altra_corsia, daemon=True)
    th.start()
    parla.wait(5)
    pe.giro(c, stt, "Calliope, quanto è lungo il Po?")
    c._inizio_giro()
    verifica("contrario: il satellite finisce il turno ma l'altra corsia parla ancora → "
             "occupata", q.occupata() == "voce", q.occupata())
    finito.set()
    th.join(5)
    verifica("… finché anche lei smette", q.occupata() == "", q.occupata())

    # Contrario (revisione della PR #163): un turno più lungo della tenuta. L'ultimo pezzo al
    # tetto e Whisper fanno passare 150 s fra l'inizio del parlato e la risposta, poi la coda
    # delle frasi dette dopo il modello altri 170 s: 320 s dall'inizio del parlato
    orl_c = Orologio()
    q._ora = orl_c
    log_c = []
    q.log = log_c.append
    tenute_prima = q.tenute
    stt_vero = stt.transcribe

    def trascrivi_lento(audio):
        orl_c.t += 150.0
        return stt_vero(audio)
    stt.transcribe = trascrivi_lento
    try:
        pe.giro(c, stt, "Calliope, raccontami una storia lunga.")
        orl_c.t += 170.0
        verifica("contrario: turno di 320 s dall'inizio del parlato (risposta a 150 s, poi "
                 "170 s di voce) → nessuna tenuta, voce occupata",
                 q.occupata() == "voce" and q.tenute == tenute_prima and not log_c,
                 f"{q.occupata()} {q.tenute - tenute_prima} {log_c}")
        c._inizio_giro()
        verifica("… e libera a fine turno", q.occupata() == "", q.occupata())
    finally:
        stt.transcribe = stt_vero
        q._ora = time.monotonic
        q.log = lambda m: print(m, flush=True)

    # Il secondo avvio nello stesso processo: un thread del primo avvio ha occupato la voce
    # ed è morto; il secondo avvio ha un conto per thread suo e la voce torna libera
    th = threading.Thread(target=avvio.listener.on_speech_start, daemon=True)
    th.start()
    th.join(5)
    avvio2 = types.SimpleNamespace(
        s=types.SimpleNamespace(stt=types.SimpleNamespace(), stanza=None, guardia_stanza=None,
                                lavori=None),
        cfg=cfg, varco=types.SimpleNamespace(attivi=0), insieme=True,
        listener=types.SimpleNamespace(on_speech_start=None, on_speech_end=None),
        conv_arch=None)
    ombra.chiudi()
    Avvio._arbitro_memoria(avvio2)
    ombra = avvio2.s.arbitro_ombra
    avvio2.listener.on_speech_start()
    q.voce_libera()
    verifica("secondo avvio: la voce torna libera (il thread morto del primo non la tiene)",
             q.occupata() == "", q.occupata())
    avvio2.listener.on_speech_start()
    verifica("secondo avvio: e si occupa di nuovo", q.occupata() == "voce", q.occupata())
    q.voce_libera()
finally:
    ombra.chiudi()
    q.segnali, q._voce = [], False
    q.voce_occupata = am.Quiete.voce_occupata.__get__(q)
    q.voce_libera = am.Quiete.voce_libera.__get__(q)
    q.tenuta_max_s = am.Quiete.TENUTA_MAX_S


# ─────────────────────────── 2. la tenuta massima ───────────────────────────
print("— la tenuta massima della voce")


orl = Orologio()
log = []
qt = am.Quiete(orologio=orl, tenuta_max_s=180.0, log=log.append)
qt.voce_occupata()
orl.t += 179
verifica("contrario: a 179 s dall'inizio del parlato la voce è ancora occupata",
         qt.occupata() == "voce" and not log and qt.tenute == 0)
qt.voce_occupata()                         # un segno nuovo (la frase dopo, unita al tetto)
orl.t += 100
verifica("contrario: un «occupata» nuovo fa ripartire la tenuta (279 s in tutto)",
         qt.occupata() == "voce" and qt.tenute == 0)
orl.t += 81
verifica("oltre la tenuta massima senza un segno: la voce torna libera",
         qt.occupata() == "" and qt.tenute == 1 and qt.ultimo_motivo == "tenuta")
verifica("… con la riga nel log", len(log) == 1 and "tenuta massima" in log[0], str(log))
verifica("… e quiete(5) solo 5 s dopo (la voce è stata occupata fino ad ora)",
         not qt(5) and (orl.__setattr__("t", orl.t + 6) or qt(5)))
verifica("una tenuta sola: il campionamento dopo non la riconta",
         qt.campiona() == "" and qt.tenute == 1 and len(log) == 1)
# Contrario: ultimo pezzo al tetto (120 s), Whisper (5 s), un tool lento e la risposta del
# modello (varco aperto 120 s), poi 150 s di frasi ancora da dire: 395 s in tutto
orl3 = Orologio()
log3 = []
varco = {"attivi": 0, "whisper": False}
q3 = am.Quiete(orologio=orl3, tenuta_max_s=180.0, log=log3.append)
q3.segnali = [("risposta", lambda: varco["attivi"] > 0), ("whisper", lambda: varco["whisper"])]


def avanti(secondi):
    for _ in range(int(secondi)):          # il thread dell'ombra campiona ogni secondo
        orl3.t += 1
        q3.campiona()


q3.voce_occupata()                         # l'ultimo pezzo al tetto comincia
avanti(120)
varco["whisper"] = True
avanti(5)
varco["whisper"] = False
q3.voce_occupata()                         # _prepara_risposta
varco["attivi"] = 1
avanti(120)                                # tool lento e modello
varco["attivi"] = 0
avanti(150)                                # la coda delle frasi
verifica("contrario: turno lungo vero (tetto, Whisper, tool lento, risposta lunga) → "
         "nessuna tenuta", q3.occupata() == "voce" and q3.tenute == 0 and not log3,
         f"{q3.occupata()} {q3.tenute} {log3}")
avanti(31)
verifica("… la tenuta scatta solo 180 s dopo l'ultimo segno (la fine del modello)",
         q3.tenute == 1 and q3.occupata() == "", f"{q3.tenute}")
verifica("la tenuta di serie è più lunga della frase più lunga di serie (120 s)",
         am.Quiete().tenuta_max_s == am.Quiete.TENUTA_MAX_S > 120)


class Misure:
    def __init__(self):
        self.righe = []

    def scrivi(self, tipo, **campi):
        self.righe.append((tipo, campi))


mis = Misure()
orl2 = Orologio()
q2 = am.Quiete(orologio=orl2, tenuta_max_s=10.0, log=lambda m: None)
om = AO.Ombra(types.SimpleNamespace(), q2, inventario=lambda: {}, libera=lambda: None,
              caricati=lambda: [], misure=mis, orologio=orl2, avvia=False)
om.conto = lambda forza=False: types.SimpleNamespace(occupanti=[], tipo="cpu", libera_gb=1.0,
                                                     spazio_gb=1.0, margine_gb=0.0)
om.minuto()
verifica("riga del minuto senza tenute: niente «tenute_voce»",
         "tenute_voce" not in mis.righe[-1][1], str(mis.righe[-1]))
q2.voce_occupata()
orl2.t += 11
q2.campiona()
om.minuto()
verifica("riga del minuto con una tenuta: «tenute_voce»: 1",
         mis.righe[-1][1].get("tenute_voce") == 1, str(mis.righe[-1]))
om.minuto()
verifica("il minuto dopo non la riconta", "tenute_voce" not in mis.righe[-1][1])

# La storia di `calliope stato --memoria --storia`: una riga per giorno, solo se c'è
righe = [{"t": "2026-10-17T10:00:00", "tipo": "minuto", "libera_gb": 20.0, "margine_gb": 8.0},
         {"t": "2026-10-18T10:00:00", "tipo": "minuto", "libera_gb": 20.0, "margine_gb": 8.0,
          "tenute_voce": 2},
         {"t": "2026-10-18T10:01:00", "tipo": "minuto", "libera_gb": 20.0, "margine_gb": 8.0,
          "tenute_voce": 1}]
st = AO.storia(righe)
verifica("storia: tenute_voce sommate per giorno (0 il 17, 3 il 18)",
         st["2026-10-17"]["tenute_voce"] == 0 and st["2026-10-18"]["tenute_voce"] == 3, str(st))
testo = AO.testo_storia(st)
riga_t = [x for x in testo.splitlines() if "tenuta massima" in x]
verifica("testo della storia: una riga sola, del 18, con l'avviso",
         len(riga_t) == 1 and ": 3" in riga_t[0] and "AVVISO" in riga_t[0]
         and testo.index("2026-10-18") < testo.index(riga_t[0]), testo)

print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
sys.exit(1 if errori else 0)
