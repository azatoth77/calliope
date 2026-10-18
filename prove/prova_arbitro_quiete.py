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
da poco non è liberato dalla tenuta massima. Poi la tenuta massima: oltre `tenuta_max_s`
dall'ultimo «occupata» la voce torna libera da sé, con la riga nel log e il conto nella riga
del minuto dell'arbitro in ombra (`tenute_voce`). Nomi di fantasia, niente rete né audio: ~2 s.
"""
import os
import queue
import sys
import tempfile
import threading
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
finally:
    ombra.chiudi()
    q.segnali, q._voce = [], False
    q.voce_occupata = am.Quiete.voce_occupata.__get__(q)
    q.voce_libera = am.Quiete.voce_libera.__get__(q)
    q.tenuta_max_s = am.Quiete.TENUTA_MAX_S


# ─────────────────────────── 2. la tenuta massima ───────────────────────────
print("— la tenuta massima della voce")


class Orologio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


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

print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
sys.exit(1 if errori else 0)
