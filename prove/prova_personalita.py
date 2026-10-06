import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della personalità (04/10, docs/ricerche/2026-10-04-personalita-wake-word.md):
tono di voce della casa e per persona, wake word cambiata (testuale, posizione, Whisper,
barge-in), modalità startrek e suoni di inizio e fine ascolto. Ogni regola sul testo ha i suoi
casi contrari (principio 10).
"""

import base64
import io
import queue
import tempfile
import threading
import time
import types
import wave
from pathlib import Path

import numpy as np

from calliope import config as C
from calliope.config import Config, TONI, frase_tono, nome_tono
from calliope.stt import hotwords_whisper, prompt_whisper
from calliope.suoni import (FINE, INIZIO, MAX_FILE_S, SuoniAscolto, da_benvenuto, leggi_wav,
                            sintetico)
from calliope.tts import dice_nome
from calliope.wakeword import exit_intent, exit_request, find_wake_word, is_stop, said_name

errori = 0


def verifica(nome, ottenuto, atteso):
    global errori
    ok = ottenuto == atteso
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome} → {ottenuto!r}" + ("" if ok else f"  (atteso {atteso!r})"))


TMP = Path(tempfile.mkdtemp(prefix="calliope-personalita-"))

# ── configurazione: parole che svegliano ──
c = Config()
verifica("wake_names predefinito", c.wake_names, ["Calliope"])
verifica("exit_names predefinito", c.exit_names, ["Calliope"])
c.wake_word = "Computer"
verifica("wake_names con Computer", c.wake_names, ["Computer", "Calliope"])
c.wake_anche_nome = False
verifica("wake_names senza il nome", c.wake_names, ["Computer"])
c.wake_anche_nome, c.wake_posizione = True, "inizio"
verifica("exit_names con una parola comune", c.exit_names, ["Calliope"])
verifica("wake_start_only", c.wake_start_only, True)
c.wake_word = "calliope"                       # uguale al nome: niente doppione
verifica("wake_names con la stessa parola", c.wake_names, ["calliope"])

# ── modalità startrek: preset, file locale che vince, nome sconosciuto ──
(TMP / "calliope.yaml").write_text("identita:\n  modalita: startrek\n", encoding="utf-8")
loc = TMP / "calliope.locale.yaml"
loc.write_text("identita:\n  tono: ironico\n", encoding="utf-8")
os.environ["CALLIOPE_CONFIG_LOCALE"] = str(loc)
cfg = C.load_config(str(TMP / "calliope.yaml"))
verifica("startrek: wake word", cfg.wake_names, ["Computer", "Calliope"])
verifica("startrek: posizione", cfg.wake_posizione, "inizio")
verifica("startrek: suoni", cfg.suoni_ascolto, True)
verifica("startrek: modello", cfg.wake_model, "wakeword/modelli/computer.onnx")
verifica("startrek: il locale vince sulla modalità (tono)", cfg.tono, "ironico")
verifica("startrek: il nome resta", cfg.name, "Calliope")
loc.write_text("identita:\n  modalita: stratrek\n", encoding="utf-8")
cfg2 = C.load_config(str(TMP / "calliope.yaml"))
verifica("modalità sconosciuta: niente cambia", (cfg2.wake_names, cfg2.tono),
         (["Calliope"], "normale"))
loc.write_text("", encoding="utf-8")

# ── toni: nomi detti e casi contrari ──
for detto, atteso in [("Formale", "formale"), ("formali", "formale"), ("più ironica", "ironico"),
                      ("amichevoli", "amichevole"), ("computer di bordo", "computer_di_bordo"),
                      ("Star Trek", "computer_di_bordo"), ("più breve", "essenziale"),
                      ("normale", "normale"), ("quello di sempre", None),
                      # contrari: voci, parole a caso
                      ("pizza", None), ("Paola", None), ("serena", None), ("", None),
                      ("formaggio", None), ("ironia della sorte", None)]:
    verifica(f"tono «{detto}»", nome_tono(detto), atteso)

# ── prompt: «normale» è il testo di sempre; ogni tono tiene le regole della voce ──
p = Config().prompt_for(False)
verifica("prompt normale: caldo e naturale", "in modo caldo e naturale, da una a tre frasi, senza "
         "markdown" in p, True)
verifica("prompt normale: tu", "Dai del tu a chi ti parla; non ne conosci il genere" in p, True)
for t in TONI:
    cc = Config()
    cc.tono = t
    pt = cc.prompt_for(False)
    verifica(f"prompt {t}: regole della voce", ("senza markdown, elenchi, emoji o URL" in pt
                                               and "numeri in cifre" in pt), True)
cc = Config()
cc.tono = "formale"
verifica("prompt formale: lei", "Dai del lei" in cc.prompt_for(False), True)
cc.tono = "essenziale"
verifica("prompt essenziale: una frase", "con una frase breve, senza markdown" in cc.prompt_for(False), True)
cc.tono = "inventato"
verifica("tono sconosciuto: prompt normale", cc.prompt_for(False) == p, True)
verifica("frase del tono per persona", (frase_tono("formale").endswith("(dai del lei)"),
                                        frase_tono("ironico").startswith("preferisce il tono ironico")),
         (True, True))
verifica("niente formule di conferma nei toni", any(w in (v["stile"]).lower() for v in TONI.values()
                                                    for w in ("eseguito", "fatto", "confermato")), False)

# ── wake word testuale con la posizione (wake_posizione: inizio) ──
N = ["Computer", "Calliope"]
for testo, atteso in [
        ("Computer, che ore sono?", "che ore sono"),
        ("Computer.", ""),
        ("Ehi computer accendi la luce", "accendi la luce"),
        ("Ok computer, spegni la luce.", "spegni la luce"),
        ("Sì, computer, spegni la luce.", "spegni la luce"),
        ("Che ore sono, computer?", "Che ore sono"),           # in fondo, dopo la virgola
        ("Calliope, che ore sono?", "che ore sono"),           # il nome vale ancora
        ("Il computer è lento, computer spegnilo", "spegnilo"),
        # contrari: la parola c'è ma non chiama nessuno
        ("Il computer è lento.", None),
        ("Ho comprato un computer nuovo", None),
        ("Accendi il computer", None),
        ("Computo metrico della casa", None),                   # «computo» 0,80 < 0,85
        ("Oggi piove.", None)]:
    verifica(f"inizio «{testo}»", find_wake_word(testo, N, 0.85, start_only=True), atteso)
info = {}
find_wake_word("Il computer è lento.", N, 0.5, info, start_only=True)
verifica("fuori posizione segnalato", info.get("fuori_posizione"), True)
info = {}
find_wake_word("Computer, il computer è lento.", N, 0.5, info, start_only=True)
verifica("fuori posizione non segnalato se c'è il richiamo", "fuori_posizione" in info, False)
# «ovunque» (Calliope di sempre): niente cambia
verifica("ovunque: nome in mezzo", find_wake_word("Accendi la luce, Calliope, in sala.", "Calliope",
                                                  0.78), "in sala")
verifica("ovunque con Computer in mezzo", find_wake_word("Il computer è lento", N, 0.78), "è lento")
verifica("più parole: vale la prima", find_wake_word("Calliope, chiedi al computer", N, 0.85),
         "chiedi al computer")

# ── uscite, stop, nome detto con più parole ──
verifica("uscita «Computer, esci»", exit_request("Computer, esci", N, ["Calliope"]), "dormi")
verifica("uscita «Computer, spegniti»", exit_request("Computer, spegniti", N, ["Calliope"]), "spegni")
verifica("uscita «spegni Calliope»", exit_request("spegni Calliope", N, ["Calliope"]), "spegni")
verifica("contrario: «spegni computer» è il PC", exit_intent("spegni computer", N, ["Calliope"]), None)
verifica("contrario: «Computer, spegni il computer»",
         exit_request("Computer, spegni il computer", N, ["Calliope"]), None)
verifica("senza spegni_nomi «spegni Calliope» come prima", exit_intent("spegni Calliope"), "spegni")
verifica("stop «Computer, grazie»", is_stop("Computer, grazie", N), True)
verifica("contrario stop «Computer, ferma la musica»", is_stop("Computer, ferma la musica", N), False)
verifica("nome detto con la wake word", said_name("Mi chiamo Dario, computer", N), "Dario")

# ── Whisper e barge-in ──
d = Config()
verifica("prompt di Whisper di sempre", prompt_whisper(d), "Conversazione con Calliope.")
verifica("hotwords di sempre", hotwords_whisper(d), "Calliope")
d.wake_word = "Computer"
verifica("prompt di Whisper con Computer", prompt_whisper(d), "Conversazione con Computer.")
verifica("hotwords con Computer", hotwords_whisper(d), "Calliope Computer")
verifica("barge-in: dice il nome", dice_nome(d, "Sono Calliope."), True)
verifica("barge-in: dice la wake word", dice_nome(d, "Il computer è acceso."), True)
verifica("barge-in: contrario", dice_nome(d, "Sono le 15:30."), False)

# ── suoni ──
for tipo in (INIZIO, FINE):
    x = sintetico(tipo, 16000, 0.35)
    dur = len(x) / 16000
    spettro = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / 16000)
    basso = spettro[f < 1000].sum() / spettro.sum()
    verifica(f"suono {tipo}: corto", dur <= 0.25, True)
    verifica(f"suono {tipo}: non forte", float(np.max(np.abs(x))) <= 0.36, True)
    verifica(f"suono {tipo}: lontano dalla voce (<1 kHz)", basso < 0.01, True)


def scrivi_wav(path, rate, canali, larghezza, secondi):
    t = np.arange(int(rate * secondi)) / rate
    y = 0.5 * np.sin(2 * np.pi * 440 * t)
    if larghezza == 1:
        s = ((y + 1) * 127.5).astype(np.uint8).reshape(-1, 1)
    elif larghezza == 2:
        s = (y * 32767).astype("<i2").view(np.uint8).reshape(-1, 2)
    else:
        s = (y * (2 ** 23 - 1)).astype("<i4").view(np.uint8).reshape(-1, 4)[:, :3]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(canali)
        w.setsampwidth(larghezza)
        w.setframerate(rate)
        w.writeframes(np.ascontiguousarray(np.concatenate([s] * canali, axis=1)).tobytes())


for rate, canali, larghezza in [(44100, 2, 2), (22050, 1, 1), (48000, 1, 3)]:
    pth = TMP / f"s{rate}{canali}{larghezza}.wav"
    scrivi_wav(pth, rate, canali, larghezza, 0.3)
    y = leggi_wav(pth, 16000)
    verifica(f"wav {rate} Hz, {canali} canali, {larghezza * 8} bit", (abs(len(y) - 4800) <= 2,
                                                                     0.4 < float(np.max(y)) < 0.6), (True, True))
pth = TMP / "lungo.wav"
scrivi_wav(pth, 16000, 1, 2, 4.0)
verifica("wav lungo tagliato", len(leggi_wav(pth, 16000)), int(16000 * MAX_FILE_S))
(TMP / "rotto.wav").write_bytes(b"non sono un wav")
try:
    leggi_wav(TMP / "rotto.wav", 16000)
    verifica("wav rotto", "letto", "ValueError")
except ValueError:
    verifica("wav rotto", "ValueError", "ValueError")
s = Config()
s.suoni_ascolto, s.suono_inizio_ascolto, s.config_dir = True, "rotto.wav", str(TMP)
s.suono_fine_ascolto = "lungo.wav"
righe = []
sa = SuoniAscolto(s, log=righe.append)
verifica("file rotto: sintetico e una riga nel log", (len(sa.pcm(INIZIO, 16000)) ==
                                                       len(sintetico(INIZIO, 16000)) * 2, len(righe)), (True, 1))
verifica("file dell'utente usato", len(sa.pcm(FINE, 16000)), int(16000 * MAX_FILE_S) * 2)
solo_fine = Config()
solo_fine.suoni_ascolto, solo_fine.suono_inizio_ascolto = True, "nessuno"
sf = SuoniAscolto(solo_fine)
verifica("«nessuno»: niente bip d'inizio, quello di fine sì", (sf.pcm(INIZIO, 16000),
                                                              len(sf.pcm(FINE, 16000)) > 0), (b"", True))
spenti = Config()
verifica("suoni spenti: niente", (SuoniAscolto(spenti).pcm(INIZIO, 16000),
                                  SuoniAscolto(spenti).per_satellite()), (b"", None))
b = sa.per_satellite(22050)
r = da_benvenuto(b)
verifica("benvenuto: andata e ritorno", (r[INIZIO][1], r[INIZIO][0] == sa.pcm(INIZIO, 22050)), (22050, True))
for nome, rotto in [("niente", None), ("non dict", "x"), ("frequenza assurda", {"rate": 5, "inizio": "AAAA"}),
                    ("base64 rotto", {"rate": 16000, "inizio": "%%%"}),
                    ("byte dispari", {"rate": 16000, "inizio": base64.b64encode(b"abc").decode()})]:
    verifica(f"benvenuto rotto ({nome})", da_benvenuto(rotto), {})

# ── Listener: on_wake solo allo scatto a Calliope addormentata ──
from calliope.audio import Listener  # noqa: E402


class MicFinto:
    def __init__(self, samplerate, channels, dtype, blocksize, device, callback):
        self.cb, self.n, self._stop = callback, blocksize, threading.Event()
        self.coda = queue.Queue()

    def start(self):
        def gira():
            while not self._stop.is_set():
                try:
                    f = MIC.get_nowait()
                except queue.Empty:
                    f = np.zeros(self.n, np.float32)
                self.cb(f.reshape(-1, 1), self.n, None, None)
                time.sleep(0.002)
        threading.Thread(target=gira, daemon=True).start()

    def abort(self):
        self._stop.set()

    close = abort


class VadFinto:
    def prob(self, frame):
        return 1.0 if np.max(np.abs(frame)) > 0.05 else 0.0

    def reset_states(self):
        pass


class WakeFinta:
    def __init__(self):
        self.n = 0

    def reset(self):
        self.n = 0

    def process(self, frame):
        self.n += 1
        return 0.95 if np.max(np.abs(frame)) > 0.05 else 0.0


MIC: queue.Queue = queue.Queue()
lc = Config()
lc.wake_consecutive, lc.silence_ms, lc.min_speech_ms = 2, 200, 100
L = Listener(lc, sorgente=MicFinto)
L.model = VadFinto()
scatti = []
L.on_wake = lambda: scatti.append(time.monotonic())


def frase():
    for _ in range(20):                  # 0,64 s di «voce»
        MIC.put(np.full(512, 0.3, np.float32))


frase()
a = L.listen(WakeFinta(), awake_until=0.0)
verifica("on_wake: addormentata, uno scatto", (a is not None, len(scatti)), (True, 1))
scatti.clear()
frase()
a = L.listen(WakeFinta(), awake_until=float("inf"))
verifica("contrario on_wake: già sveglia, nessun suono", (a is not None, len(scatti)), (True, 0))
L.stream.abort()

# ── Speaker.suono_ascolto: in locale sì, con il satellite no ──
from calliope.tts import Speaker  # noqa: E402
sp = object.__new__(Speaker)
sp.muto, sp.remota, sp.out, sp._rate, sp.audio_q = False, None, None, 22050, queue.Queue()
sp.suono_ascolto(sa, INIZIO)
verifica("Speaker: suono in coda", sp.audio_q.qsize(), 1)
sp.remota = object()
sp.suono_ascolto(sa, FINE)
verifica("contrario Speaker: con il satellite niente", sp.audio_q.qsize(), 1)

# ── tono a voce: cambia_voce con tono, per persona e per la casa ──
from calliope.speaker_id import UserProfile  # noqa: E402
from calliope.tools.builtin import _cambia_voce  # noqa: E402


class Registro:
    def __init__(self):
        self.p = {"Dario": UserProfile("Dario", admin=True), "Bianca": UserProfile("Bianca")}
        self.salvati = 0

    def get(self, n):
        return self.p.get(n)

    def save(self):
        self.salvati += 1


class VoceFinta:
    def __init__(self):
        self.voci = []

    def change_voice(self, p):
        self.voci.append(p)
        return True


def contesto(chi, livello):
    tc = Config()
    tc.config_dir = str(TMP)
    return types.SimpleNamespace(cfg=tc, speakers=REG, speaker=VoceFinta(), regole=[],
                                 speaker_ctx=types.SimpleNamespace(current_speaker=chi,
                                                                   current_level=livello))


REG = Registro()
ctx = contesto("Bianca", "familiare")
r = _cambia_voce(ctx, tono="formale")
verifica("tono di Bianca", (r["ok"], REG.p["Bianca"].preferred_tone, "risposta_finale" in r),
         (True, "formale", True))
r = _cambia_voce(ctx, voce="ironica")
verifica("tono messo in voce (regola tono_da_voce)", (REG.p["Bianca"].preferred_tone, ctx.regole),
         ("ironico", ["tono_da_voce"]))
r = _cambia_voce(ctx, voce="paola")
verifica("contrario: «paola» è una voce", (r["ok"], ctx.speaker.voci[-1].endswith("paola-medium.onnx"),
                                          REG.p["Bianca"].preferred_tone), (True, True, "ironico"))
r = _cambia_voce(ctx, tono="normale")
verifica("torna normale: tolta la scelta", REG.p["Bianca"].preferred_tone, None)
r = _cambia_voce(ctx, tono="pizza")
verifica("tono sconosciuto", r["ok"], False)
r = _cambia_voce(ctx, tono="formale", per_tutti=True)
verifica("per_tutti da un familiare: rifiutato", (r["ok"], ctx.cfg.tono, (TMP / "personalita.json").exists()),
         (False, "normale", False))
ctxa = contesto("Dario", "amministra")
r = _cambia_voce(ctxa, tono="essenziale", per_tutti=True)
verifica("per_tutti da chi amministra", (r["ok"], ctxa.cfg.tono, (TMP / "personalita.json").exists()),
         (True, "essenziale", True))
ospite = contesto(None, "ospite")
verifica("ospite: niente tono personale", _cambia_voce(ospite, tono="formale")["ok"], False)
r = _cambia_voce(ctx, voce="", tono="")
verifica("né voce né tono", r["ok"], False)

# personalita.json: vince se è più recente dei file di configurazione
from calliope.personalita import carica_tono_casa  # noqa: E402
t = Config()
t.config_dir = str(TMP)
os.utime(TMP / "calliope.yaml", (time.time() - 100, time.time() - 100))
os.utime(loc, (time.time() - 100, time.time() - 100))
verifica("tono della casa detto a voce, più recente", (carica_tono_casa(t, log=lambda *a: None), t.tono),
         ("essenziale", "essenziale"))
t2 = Config()
t2.config_dir = str(TMP)
os.utime(loc, None)
time.sleep(0.01)
os.utime(loc, (time.time() + 5, time.time() + 5))
verifica("contrario: file di configurazione più recente", (carica_tono_casa(t2, log=lambda *a: None),
                                                           t2.tono), (None, "normale"))

# profilo: il tono va e torna da speakers.json
pr = UserProfile("Gino", preferred_tone="ironico")
verifica("profilo: tono salvato", UserProfile.from_dict(pr.to_dict(), pr.model).preferred_tone, "ironico")
verifica("profilo vecchio senza tono", UserProfile.from_dict({"name": "X"}, None).preferred_tone, None)

# ── Brain: il tono della persona prima della domanda, mai nel prompt di sistema ──
from calliope.brain import Brain  # noqa: E402
from calliope.tools.registry import ToolRegistry  # noqa: E402
bc = Config()
REG.p["Bianca"].preferred_tone = "formale"
tctx = types.SimpleNamespace(speakers=REG, speaker_ctx=types.SimpleNamespace(
    current_speaker="Bianca", identified_by="voce"))
br = Brain(bc, ToolRegistry(), tctx)
br.last_rules = []
msgs = br._turn_context()
verifica("Brain: tono di Bianca nei dati del turno, un messaggio solo",
         (len(msgs), "riconosciuta dalla voce; preferisce il tono formale nelle parole" in msgs[0]["content"],
          "(dai del lei)." in msgs[0]["content"]), (1, True, True))
verifica("Brain: regola tono_persona", br.last_rules, ["tono_persona"])
sistema = br._system_messages()[0]["content"]
tctx.speaker_ctx.current_speaker = "Dario"
verifica("Brain: stesso prompt di sistema per chi ha un altro tono",
         br._system_messages()[0]["content"] == sistema, True)
verifica("contrario Brain: Dario senza tono suo", "preferisce il tono" in br._turn_context()[0]["content"],
         False)
bc.tono = "formale"
tctx.speaker_ctx.current_speaker = "Bianca"
verifica("contrario Brain: tono uguale a quello della casa",
         "preferisce il tono" in br._turn_context()[0]["content"], False)
tctx.speaker_ctx.current_speaker = None
verifica("contrario Brain: ospite", "preferisce il tono" in br._turn_context()[0]["content"], False)

# «calliope_cambia_voce(…)» scritto come testo (04/10): la guardia lo prende
from calliope.brain import TextCallGuard  # noqa: E402
schemi = [{"function": {"name": "cambia_voce", "parameters": {"properties": {
    "voce": {}, "tono": {}, "per_tutti": {}}}}}]
g = TextCallGuard(schemi)
detto = g.feed('calliope_cambia_voce(tono="computer_di_bordo", per_tutti=true)') + g.flush()
verifica("guardia: calliope_cambia_voce", (detto, (g.call or {}).get("name")), ("", "cambia_voce"))
g = TextCallGuard(schemi)
detto = g.feed("Calliope è il mio nome.") + g.flush()
verifica("contrario guardia: «Calliope è il mio nome.»", (detto, g.call), ("Calliope è il mio nome.", None))
r = _cambia_voce(ctx, tono="formale", per_tutti="false")
verifica("per_tutti come testo «false»: solo per la persona", (r["ok"], REG.p["Bianca"].preferred_tone),
         (True, "formale"))

# ── telefono: senza il modello della parola nuova resta quello del nome ──
from calliope.schermi.telefono import file_modelli  # noqa: E402
(TMP / "modelli").mkdir()
(TMP / "modelli" / "calliope.onnx").write_bytes(b"x")
tf = Config()
tf.wake_model = str(TMP / "modelli" / "computer.onnx")
verifica("telefono: ripiego su calliope.onnx", Path(file_modelli(tf)["calliope"]).name, "calliope.onnx")
(TMP / "modelli" / "computer.onnx").write_bytes(b"x")
verifica("telefono: c'è computer.onnx", Path(file_modelli(tf)["calliope"]).name, "computer.onnx")

# ── satellite: il modello del server se c'è, altrimenti il proprio ──
from calliope.satellite import client as SC  # noqa: E402
log, chiesti = [], []
fs = SC.Satellite.__new__(SC.Satellite)
fs.cfg = types.SimpleNamespace(wake_model=str(TMP / "modelli" / "calliope.onnx"))
fs._wake_file, fs._wake_su_misura, fs.log, fs.wake = "calliope.onnx", False, log.append, "vecchio"
fs._wake_in_uso, fs._cartella_wake = ["calliope.onnx"], str(TMP / "modelli")
fs._crea_rilevatore = lambda p, altri: ("nuovo", os.path.basename(p))
fs._wake_voluti, fs._wake_annunciati, fs._wake_in_arrivo = None, {}, None
fs._wake_chiesti, fs._manda = set(), lambda **k: chiesti.append(k) or True
SC.Satellite._cambia_wake(fs, "manca.onnx")
verifica("satellite: modello assente, resta il suo", (fs.wake, fs._wake_file, len(log), chiesti),
         ("vecchio", "calliope.onnx", 1, []))
SC.Satellite._cambia_wake(fs, "computer.onnx")
verifica("satellite: passa al modello del server", (fs.wake, fs._wake_file), (("nuovo", "computer.onnx"),
                                                                            "computer.onnx"))
SC.Satellite._cambia_wake(fs, "../../segreto.onnx")
verifica("contrario satellite: niente percorsi dal server", fs._wake_file, "computer.onnx")

print(f"\n{'Tutto ok' if not errori else f'{errori} errori'}")
sys.exit(1 if errori else 0)
