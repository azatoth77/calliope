import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della robustezza (03/10/2026, analisi di robustezza dell'harness).

Ogni sezione riproduce un guasto trovato dall'analisi e controlla che non blocchi più
Calliope: niente audio, niente Ollama, file temporanei.

    python prove/prova_robustezza.py            # tutte le sezioni
    python prove/prova_robustezza.py tts        # solo una (tts, …)
"""

import queue
import tempfile
import threading
import time
import types

import sounddevice as sd

from calliope import capacita, tts

ERRORI = 0


def check(cond, msg):
    global ERRORI
    print(("ok  " if cond else "ERR ") + msg, flush=True)
    if not cond:
        ERRORI += 1


def aspetta(condizione, max_s=5.0) -> bool:
    """Aspetta una condizione invece di un tempo fisso (come prova_casa_ha)."""
    fine = time.monotonic() + max_s
    while time.monotonic() < fine:
        if condizione():
            return True
        time.sleep(0.02)
    return bool(condizione())


def in_thread(fn, max_s):
    """Chiama fn in un thread: (finita entro max_s, risultato, secondi)."""
    out = {}
    t0 = time.monotonic()
    t = threading.Thread(target=lambda: out.setdefault("r", fn()), daemon=True)
    t.start()
    t.join(max_s)
    return not t.is_alive(), out.get("r"), time.monotonic() - t0


# ─────────────────────────── 1. voce (tts.py) ───────────────────────────
class Voce:
    """Piper finta: 0,2 s di audio a frase; solleva sulle frasi che contengono «ROTTA»."""
    config = types.SimpleNamespace(sample_rate=22050)

    def synthesize(self, text):
        if "ROTTA" in text:
            raise RuntimeError("espeak: errore finto")
        yield types.SimpleNamespace(audio_int16_bytes=b"\0\0" * 4410)


class Flusso:
    """Un flusso di PortAudio finto. `guasti` dice cosa fanno le write: «ok», «errore»
    (le cuffie spariscono), «blocca» (PortAudio fermo in una chiamata)."""
    aperture = 0
    modo = "ok"
    sblocca = threading.Event()

    def __init__(self, samplerate, channels, dtype, device):
        if Flusso.modo == "non_apre":
            raise sd.PortAudioError("Device unavailable")
        Flusso.aperture += 1
        self.samplerate, self.latency, self.device = samplerate, 0.0, device
        self.scritti = 0

    def start(self):
        pass

    def write(self, data):
        if Flusso.modo == "errore":
            raise sd.PortAudioError("Unanticipated host error")
        if Flusso.modo == "blocca":
            Flusso.sblocca.wait(30)
        self.scritti += len(data)

    def stop(self):
        pass

    def close(self):
        Flusso.sblocca.set()


def speaker_finto(remota=None, keepalive=False):
    cfg = types.SimpleNamespace(tts_keepalive=keepalive, name="Calliope", output_device=None,
                                tts_lead_s=0.0, tts_tail_s=0.0)
    s = tts.Speaker.__new__(tts.Speaker)
    s.cfg, s.remota, s.turno, s.voice = cfg, remota, 0, Voce()
    s._current_voice_path, s._voices, s._voices_lock, s._fillers = "finta", {}, threading.Lock(), {}
    s.text_q, s.audio_q = queue.Queue(), queue.Queue()
    s.done, s._interrupted = threading.Event(), threading.Event()
    s.played, s._now_text, s._name_until, s._rate, s.on_parla = [], "", 0.0, 22050, None
    s.out = None if remota else tts.UscitaLocale(cfg, 22050, apri_flusso=Flusso,
                                                 on_stato=s._stato_uscita)
    s._avvia_thread()
    return s


def prova_tts():
    print("\n── 1. voce: Piper che solleva, cuffie che spariscono, PortAudio fermo ──")
    capacita.nuovo_registro()
    # a) Piper solleva su una frase: la frase si salta, il turno finisce, la dopo si dice
    Flusso.modo = "ok"
    s = speaker_finto()
    s.say("Questa frase è ROTTA.")
    s.say("Questa invece va.")
    fin, ok, dt = in_thread(s.wait, 5)
    check(fin and ok, f"Piper che solleva: wait() torna ({dt:.2f} s) invece di restare ferma")
    check(s.played == ["Questa invece va."] and s.frasi_saltate == 1,
          f"la frase rotta è saltata, l'altra detta: {s.played}")

    # b) le cuffie spariscono a metà frase: l'audio si scarta, poi l'uscita si riapre
    s = speaker_finto()
    s.out._attesa = 0.05                       # riprova subito (in esercizio 1, 2, 4… s)
    Flusso.modo = "errore"
    s.start_turn()
    s.say("Le cuffie si spengono adesso.")
    fin, ok, dt = in_thread(s.wait, 5)
    check(fin, f"cuffie sparite (PortAudioError in write): wait() torna ({dt:.2f} s)")
    check(s.out.guasta and not s.played, "uscita segnata guasta, la frase non risulta detta")
    cap = capacita.REGISTRO.get("audio")
    check(cap is not None and cap.stato == "guasta", f"capacità «audio» guasta: "
          f"{cap.motivo if cap else None}")
    Flusso.modo = "ok"                          # le cuffie tornano
    aperte = Flusso.aperture
    s.start_turn()
    time.sleep(0.1)
    s.say("Eccomi di nuovo.")
    fin, ok, dt = in_thread(s.wait, 5)
    check(fin and s.played == ["Eccomi di nuovo."] and Flusso.aperture > aperte,
          f"uscita riaperta da sola, la frase dopo si sente: {s.played}")
    cap = capacita.REGISTRO.get("audio")
    check(cap is not None and cap.stato == "attiva", "capacità «audio» di nuovo attiva")

    # c) mantieni() con le cuffie sparite nel silenzio tra i turni: il thread non muore
    s = speaker_finto(keepalive=True)
    s.out._attesa = 0.05
    Flusso.modo = "errore"
    check(aspetta(lambda: s.out.guasta, 2), "keepalive con le cuffie sparite: uscita guasta")
    Flusso.modo = "ok"
    check(aspetta(lambda: not s.out.guasta, 3), "keepalive: l'uscita si riapre da sola")
    s.say("Ci sono ancora.")
    fin, ok, dt = in_thread(s.wait, 5)
    check(fin and s.played == ["Ci sono ancora."], f"dopo il keepalive guasto parla: {s.played}")

    # d) PortAudio fermo in una write: wait() ha un tempo massimo e i thread si rifanno
    s = speaker_finto()
    Flusso.sblocca.clear()
    Flusso.modo = "blocca"
    s.say("Questa resta incastrata.")
    fin, ok, dt = in_thread(lambda: s.wait(stallo_s=0.8), 5)
    check(fin and ok is False and s.blocchi == 1,
          f"PortAudio fermo: wait() torna dopo {dt:.2f} s (tempo massimo) e lo dice")
    Flusso.modo = "ok"
    Flusso.sblocca.set()
    s.start_turn()
    s.say("Dopo il blocco parlo.")
    fin, ok, dt = in_thread(s.wait, 5)
    check(fin and ok and s.played == ["Dopo il blocco parlo."],
          f"thread rifatti: la frase dopo si sente ({s.played})")

    # e) satellite: invia che solleva, fine_turno che solleva → la fine del turno arriva
    class Remota:
        _in_coda_s = 0.0

        def __init__(self):
            self.inviate = []

        def invia(self, turno, testo, audio, rate):
            if "ROTTA" in testo or "persa" in testo:
                raise ConnectionError("satellite caduto")
            self.inviate.append(testo)

        def fine_turno(self):
            if any("ultima" in t for t in self.inviate):
                raise TimeoutError("nessuna risposta")
            return list(self.inviate)

        def ferma(self, turno):
            pass
    r = Remota()
    s = speaker_finto(remota=r)
    s.say("Frase persa per strada.")
    s.say("Questa arriva.")
    fin, ok, dt = in_thread(s.wait, 5)
    check(fin and ok and s.played == ["Questa arriva."],
          f"satellite: invia che solleva non ferma la voce ({s.played})")
    s.say("E questa è l'ultima.")
    fin, ok, dt = in_thread(s.wait, 5)
    check(fin and ok, "satellite: fine_turno che solleva non ferma wait()")

    # f) il riproduttore del satellite: cuffie sparite, il turno finisce lo stesso
    from calliope.satellite.client import Riproduttore
    finiti = []
    Flusso.modo = "ok"
    cfg = types.SimpleNamespace(tts_keepalive=False, name="Calliope", output_device=None,
                                tts_lead_s=0.0, tts_tail_s=0.0)
    rp = Riproduttore(cfg, apri_flusso=Flusso, turno_finito=lambda i, d: finiti.append((i, d)))
    rp.out._attesa = 0.05
    Flusso.modo = "errore"
    rp.frase(1, 1, "Sul satellite.", 22050, 8820)
    rp.pezzo(1, b"\0\0" * 4410)
    rp.fine_turno(7)
    check(aspetta(lambda: finiti, 3) and finiti[0] == (7, []),
          f"satellite con le cuffie sparite: il turno finisce lo stesso ({finiti})")
    Flusso.modo = "ok"
    time.sleep(0.1)
    rp.frase(2, 2, "Di nuovo.", 22050, 8820)
    rp.pezzo(2, b"\0\0" * 4410)
    rp.fine_turno(8)
    check(aspetta(lambda: len(finiti) == 2, 3) and finiti[1] == (8, ["Di nuovo."]),
          f"satellite: dopo la riapertura la frase si sente ({finiti[1:]})")


# ─────────────────────────── 2. agenda e memoria.db ───────────────────────────
def prova_agenda():
    import datetime
    import sqlite3
    from calliope.agenda import Agenda
    from calliope.liste import Liste
    from calliope.memory import Memory
    from calliope.ufficio.numerazione import Numeratore
    print("\n── 2. agenda e memoria.db: «database is locked», numerazione fuori dalla transazione ──")
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "memoria.db")
    a = Agenda(path)
    mem, liste = Memory(path), Liste(path)
    modo = sqlite3.connect(path).execute("PRAGMA journal_mode").fetchone()[0]
    check(modo == "wal", f"memoria.db in WAL (journal_mode = {modo})")
    agenda_t = [t for t in threading.enumerate() if getattr(t, "_target", None) == a._run]

    # a) un errore del database nel giro: il thread non muore, riprova e annuncia
    vero = a.db

    class Guasto:
        """La connessione dell'agenda: il primo DELETE dà «database is locked»."""
        rotto = True

        def execute(self, sql, *args):
            if sql.startswith("DELETE") and Guasto.rotto:
                Guasto.rotto = False
                raise sqlite3.OperationalError("database is locked")
            return vero.execute(sql, *args)

        def __getattr__(self, k):
            return getattr(vero, k)
    a.db = Guasto()
    a.add("timer", "pasta", time.time() + 0.2)
    check(aspetta(lambda: a.due.qsize() == 1, 6), f"«database is locked» nel giro: il timer "
          f"suona lo stesso al nuovo tentativo (errori {a.errori}, voci {a.due.qsize()})")
    check(all(t.is_alive() for t in agenda_t) and a.errori == 1, "il thread dell'agenda è vivo")
    a.db = vero
    a.due.get_nowait()

    # b) un altro scrittore tiene il blocco 6 s (come la fattura di prima): si aspetta
    w = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    w.execute("BEGIN IMMEDIATE")
    threading.Timer(6.0, lambda: w.execute("ROLLBACK")).start()
    fin, _, dt = in_thread(lambda: a.add("timer", "uova", time.time() + 0.3), 15)
    check(fin, f"blocco tenuto 6 s da un altro: l'aggiunta aspetta ({dt:.1f} s), non fallisce")
    check(aspetta(lambda: a.due.qsize() == 1, 5) and all(t.is_alive() for t in agenda_t),
          "e il timer suona")
    w.close()

    # c) numerazione: i file si preparano senza tenere il blocco del database
    num = Numeratore(path)
    dentro, libera = threading.Event(), threading.Event()

    def prepara_lenta(n, testo):
        dentro.set()
        libera.wait(10)
        return {"file": []}
    oggi = datetime.date(2026, 10, 3)
    th = threading.Thread(target=lambda: num.emetti("fatture", oggi, prepara_lenta))
    th.start()
    dentro.wait(5)
    t0 = time.monotonic()
    a.add("promemoria", "chiamare", time.time() + 3600, owner="d")
    mem.remember("d", "il numero preferito è 47")
    liste.add("spesa", ["latte"], "d")
    dt = time.monotonic() - t0
    check(dt < 1.0, f"fattura in preparazione: agenda, memoria e liste scrivono subito "
          f"({dt * 1000:.0f} ms)")
    libera.set()
    th.join(10)
    check(num.elenco("fatture", 2026)[0]["stato"] == "emesso", "e la fattura è emessa")

    # d) preparazione fallita: ultimo numero → torna libero; con un successivo già preso →
    # annullato con la nota (due «processi»: due Numeratori, due lock)
    try:
        num.emetti("fatture", oggi, lambda n, t: (_ for _ in ()).throw(OSError("disco pieno")))
    except OSError:
        pass
    check(num.prossimo("fatture", 2026) == 2, "preparazione fallita sull'ultimo numero: libero "
          "(il prossimo è ancora il 2)")
    altro = Numeratore(path)
    dentro.clear()
    libera.clear()
    errore = {}

    def prepara_che_fallisce(n, testo):
        dentro.set()
        libera.wait(10)
        raise OSError("OneDrive non risponde")

    def primo():
        try:
            num.emetti("fatture", oggi, prepara_che_fallisce)
        except OSError as e:
            errore["e"] = e
    th = threading.Thread(target=primo)
    th.start()
    dentro.wait(5)
    n2 = altro.emetti("fatture", oggi, lambda n, t: {"file": []})[0]
    libera.set()
    th.join(10)
    el = {d["numero"]: d for d in num.elenco("fatture", 2026)}
    check(n2 == 3 and el[2]["stato"] == "annullato" and "OneDrive" in (el[2]["nota"] or "")
          and num.buchi("fatture", 2026) == [] and "e" in errore,
          f"fallita mentre un altro ha preso il successivo: il 2 resta annullato con la nota, "
          f"nessun buco ({el[2]['stato']}: {el[2]['nota']})")
    # e) prenotazione rimasta da un processo morto: alla prossima emissione si libera
    db = sqlite3.connect(path)
    db.execute("INSERT INTO numeri (serie, anno, numero, data, rif, dati, stato, creato) "
               "VALUES ('ddt', 2026, 1, '2026-10-01', '[]', '{}', 'in_preparazione', ?)",
               (time.time() - 3600,))
    db.commit()
    db.close()
    n = num.emetti("ddt", oggi, lambda n, t: {"file": []})[0]
    check(n == 1, f"prenotazione di un processo morto: liberata, il numero 1 si riusa ({n})")


# ─────────────────────────── 3. speakers.json ───────────────────────────
def prova_speakers():
    import json
    from pathlib import Path

    import numpy as np

    from calliope import persistenza, speaker_id
    from calliope.config import Config
    print("\n── 3. speakers.json: scrittura atomica, copia .bak, file illeggibile ──")
    capacita.nuovo_registro()
    tmp = Path(tempfile.mkdtemp())

    class Embedder:                      # niente modello CAM++: solo il nome del modello
        def __init__(self, path, threads=2):
            self.model_name = "finto"
    vero_emb, speaker_id.SpeakerEmbedder = speaker_id.SpeakerEmbedder, Embedder
    vero_path = speaker_id.SpeakerRegistry.PATH
    speaker_id.SpeakerRegistry.PATH = tmp / "speakers.json"
    cfg = Config()
    try:
        p = tmp / "speakers.json"
        bak = tmp / "speakers.json.bak"
        reg = speaker_id.SpeakerRegistry(cfg)
        vp = np.ones(4, dtype=np.float32) / 2
        reg.set_voiceprint("Dario", [vp], admin=True)
        reg.set_voiceprint("Laura", [vp])
        check(p.exists() and bak.exists() and len(json.loads(bak.read_text("utf-8"))) == 1,
              "salvataggio atomico: c'è la copia .bak della versione di prima")

        # a) un salvataggio interrotto a metà (os.replace che non arriva): il file resta intero
        prima = p.read_bytes()
        vero_replace = persistenza.os.replace
        chiamate = []

        def replace_rotto(a, b):
            chiamate.append(b)
            if str(b) == str(p):
                raise OSError("corrente saltata")
            return vero_replace(a, b)
        persistenza.os.replace = replace_rotto
        try:
            reg.set_voiceprint("Gino", [vp])
        except OSError:
            pass
        finally:
            persistenza.os.replace = vero_replace
        check(p.read_bytes() == prima and not list(tmp.glob("*.tmp")),
              "scrittura interrotta: speakers.json resta quello di prima, niente temporanei")
        reg.users.pop("Gino", None)
        reg.save()

        # b) file troncato (la scrittura di prima del 03/10 interrotta): vale la copia .bak
        txt = p.read_text("utf-8")
        p.write_text(txt[: len(txt) // 2], encoding="utf-8")
        reg = speaker_id.SpeakerRegistry(cfg)
        dario = reg.get("Dario")
        check(sorted(reg.known_speakers()) == ["Dario", "Laura"] and dario and dario.admin
              and not reg.illeggibile, f"speakers.json troncato: profili dalla copia .bak "
              f"({reg.known_speakers()}), Dario amministra ancora")
        check(json.loads(p.read_text("utf-8")) and list(tmp.glob("speakers.json.rovinato-*")),
              "il file è rifatto dalla copia, quello rovinato messo da parte")

        # c) file e copia rovinati: niente primo avvio, tutti ospiti, il file non si tocca
        p.write_text('[{"name": "Dar', encoding="utf-8")
        bak.write_text("{", encoding="utf-8")
        reg = speaker_id.SpeakerRegistry(cfg)
        first_boot = not reg.known_speakers() and not reg.illeggibile
        check(not first_boot and reg.illeggibile, f"file e copia illeggibili: NON è un primo "
              f"avvio (nessuno diventa amministratore): {reg.illeggibile}")
        reg.set_voiceprint("Intruso", [vp], admin=True)
        check(p.read_text("utf-8") == '[{"name": "Dar' and bak.read_text("utf-8") == "{",
              "e nessun salvataggio sovrascrive il file rovinato")
        cap = capacita.REGISTRO.get("chi_parla")
        check(cap is not None and cap.stato == "guasta" and "ospiti" in cap.prossimo_passo,
              f"capacità «chi_parla» guasta con il passo: {cap.prossimo_passo[:60] if cap else ''}…")
        d = capacita.check_chi_parla(types.SimpleNamespace(
            speaker_id_enabled=True, speaker_model=__file__), str(p))
        check(d["stato"] == "guasta", "anche python -m calliope.stato lo dice (check_chi_parla)")
        # d) la copia buona basta anche al controllo da terminale
        bak.write_text(json.dumps([{"name": "Dario", "admin": True, "voiceprint": [0.5] * 4,
                                    "model": Path(__file__).stem}]), encoding="utf-8")
        d = capacita.check_chi_parla(types.SimpleNamespace(
            speaker_id_enabled=True, speaker_model=__file__), str(p))
        check(d["stato"] == "attiva" and d["dettagli"]["amministra"] == ["Dario"],
              f"file rovinato ma copia buona: check_chi_parla legge la copia ({d['motivo']})")
    finally:
        speaker_id.SpeakerEmbedder = vero_emb
        speaker_id.SpeakerRegistry.PATH = vero_path

# ─────────────────────────── 4. ciclo principale e Whisper ───────────────────────────
class _Fine(KeyboardInterrupt):
    """Fine dello scenario: il Listener finto la solleva quando le frasi sono finite."""


def _main_finto(tmp, trascrizioni, brain_errori=(), turnlog_rotto=False, documenti=(),
                lavori=(), prima_di_ascoltare=None, risposte=None, agende=None,
                scadenza_s=180.0):
    """Fa girare calliope.main.main() con tutto finto (niente audio, modelli, Ollama):
    `trascrizioni` è l'elenco di cosa «sente» Whisper (un'eccezione = Whisper solleva).
    `documenti` e `lavori`: annunci già pronti all'avvio (le code `done`);
    `prima_di_ascoltare(n)`: chiamata a ogni ascolto, «sveglia» = l'agenda sveglia l'ascolto;
    `risposte`: elenco in cui Brain finto scrive (frase, azione in sospeso consumata);
    `agende`: elenco in cui finisce l'Agenda vera creata da main.
    Restituisce (frasi dette, eccezione con cui main è uscita, righe del registro)."""
    import queue as _queue
    import numpy as np

    from calliope import main as M
    from calliope.config import Config
    from calliope.turnlog import TurnLog, read_turns

    cfg = Config()
    cfg.wake_word_enabled = False
    cfg.speaker_id_enabled = False
    cfg.barge_in_enabled = False
    cfg.installa_enabled = False
    cfg.casa_enabled = False
    cfg.audio_modo = "locale"
    # Niente guardiano: con lo speaker id spento chi parla è un ospite, e per gli ospiti il
    # guardiano interrogava l'Ollama vero (~6 s a scenario, 75 s in tutto; con Ollama spento
    # la prova percorreva un'altra strada). Una prova a secco non lo tocca (06/10)
    cfg.guardiano_enabled = False
    cfg.memory_db = str(tmp / "memoria.db")
    cfg.turn_log_dir = str(tmp / "registro")
    cfg.debug_audio_dir = None
    detto = []
    frasi = list(trascrizioni)

    class Listener:
        started_at, wake_score = 0.0, 0.0
        on_speech_start = on_speech_end = None

        def __init__(self, cfg):
            pass

        n = 0

        def listen(self, wake, awake_until, seed=None, wakeup=None):
            Listener.n += 1
            cosa = prima_di_ascoltare(Listener.n) if prima_di_ascoltare else None
            if cosa == "sveglia":
                return None
            if cosa == "attendi":            # nessuno parla: solo la sveglia dell'agenda
                if wakeup is not None and wakeup.wait(5):
                    return None
                raise _Fine()
            if not frasi:
                raise _Fine()
            self.started_at = time.monotonic()
            return np.zeros(16000, dtype=np.float32)

        def measure_echo(self, stop):
            stop.wait(2)
            return 1.0

    class STT:
        ATTESA, on_ripiego = "Un attimo.", None

        def transcribe(self, audio):
            f = frasi.pop(0)
            if isinstance(f, Exception):
                raise f
            return f

    class Speaker:
        interrupted, played, _current_voice_path, on_parla = False, [], "", None

        def __init__(self, cfg, uscita=None):
            pass

        def say(self, t):
            detto.append(t)
        say_cached = say

        def wait(self, *a):
            return True

        def start_turn(self):
            pass

        def prepare(self, *a):
            pass
        preload = chime = change_voice = prepare

    class Registry:
        illeggibile = None
        users = {}

        def __init__(self, cfg):
            pass

        def known_speakers(self):
            return ["Dario"]

        def get(self, n):
            return types.SimpleNamespace(preferred_voice=None, admin=True, id="d", name=n)

    class Brain:
        last_tools, last_private, on_tool_start = [], False, None

        def __init__(self, cfg, tools, ctx):
            self.n = 0
            self.pending = None

        def warmup(self):
            pass

        def stream_reply(self, text, level, context=None):
            self.n += 1
            preso, self.pending = (self.pending or {}).get("cosa"), None   # un turno
            if risposte is not None:
                risposte.append((text, preso))
            # «chiedimi …» → una risposta con una domanda (cortesia: «ok» dopo una domanda)
            self.domanda = text.startswith("chiedimi")
            yield "Vuoi altro?" if self.domanda else f"Risposta a «{text}»."

        domanda = False

        def ultima_domanda(self):
            return self.domanda

        def record_courtesy(self, text, frase):
            self.domanda = False

        def record_announcement(self, msg, pending=None, fonte=None):
            if pending and msg.rstrip().endswith("?"):
                self.pending = dict(pending, scade=time.monotonic() + scadenza_s)

        def strip_tool_mentions(self, s):
            return s

        def mentions_tool(self, s):
            return False

        def redact(self, s):
            return s

        def rules_fired(self):
            if self.n in brain_errori:
                raise KeyError("stato rotto")      # fuori dalla rete di stream_reply
            return []

        def has_pending(self):
            return bool(self.pending) and time.monotonic() <= self.pending["scade"]

        def end_conversation(self, motivo="fine"):
            pass

        def riprendi_conversazione(self):      # 05/10: conversazione di prima del riavvio
            return False

    class TurnLogRotto(TurnLog):
        def _write(self, record):
            raise OSError(28, "No space left on device")

    def servizio(voci, **extra):
        if not voci:
            return None
        q = _queue.Queue()
        for v in voci:
            q.put(v)
        return types.SimpleNamespace(done=q, **extra)
    arbitro = types.SimpleNamespace(voce_libera=lambda: None, voce_occupata=lambda: None,
                                    proteggi_uscita=lambda: None)
    doc = servizio(documenti, formati=())
    lav = servizio(lavori, arbitro=arbitro, close=lambda: None, modelli=(),
                   agente=types.SimpleNamespace())
    from calliope.agenda import Agenda as _Agenda

    class Agenda(_Agenda):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            if agende is not None:
                agende.append(self)
    vecchi = {}
    finti = dict(Agenda=Agenda, load_ufficio=lambda *a, **k: None, Listener=Listener, make_transcriber=lambda cfg: STT(), Speaker=Speaker,
                 SpeakerRegistry=Registry, Brain=Brain, load_config=lambda: cfg,
                 single_instance_lock=lambda: None, check_audio_devices=lambda cfg: None,
                 load_wake_detector=lambda cfg: None, load_pc=lambda cfg, sat=None: None,
                 load_casa=lambda cfg: (None, None), load_biblioteca=lambda cfg: None,
                 load_documenti=lambda *a, **k: doc, load_schermi=lambda *a, **k: None,
                 load_agenti=lambda *a, **k: lav, load_archivio=lambda *a, **k: None,
                 build_registry=lambda **k: types.SimpleNamespace(announcements=lambda: [],
                                                                  get=lambda n: None),
                 TurnLog=TurnLogRotto if turnlog_rotto else TurnLog)
    for k, v in finti.items():
        vecchi[k] = getattr(M, k)
        setattr(M, k, v)
    cwd = os.getcwd()
    os.chdir(tmp)
    uscita = None
    try:
        M.main()
    except BaseException as e:  # noqa: BLE001 — _Fine, SystemExit
        uscita = e
    finally:
        os.chdir(cwd)
        for k, v in vecchi.items():
            setattr(M, k, v)
    righe = read_turns(cfg.turn_log_dir) if os.path.isdir(cfg.turn_log_dir) else []
    return detto, uscita, righe


def prova_ciclo():
    from pathlib import Path

    import numpy as np
    print("\n── 4. ciclo principale: errori imprevisti, registro su disco pieno, Whisper ──")
    capacita.nuovo_registro()
    # a) Whisper e Brain che sollevano a metà: scuse, il giro dopo risponde
    tmp = Path(tempfile.mkdtemp())
    detto, uscita, righe = _main_finto(tmp, ["che ore sono", ValueError("trascrizione rotta"),
                                             "e domani?", "terza"], brain_errori=(2,))
    check(isinstance(uscita, _Fine), f"errori imprevisti nel giro: main non esce "
          f"({type(uscita).__name__})")
    scuse = detto.count("Scusa, ho avuto un problema.")
    check(scuse == 2 and "Risposta a «che ore sono»." in detto
          and "Risposta a «terza»." in detto,
          f"due giri rotti (Whisper, stato di Brain): due scuse, e le altre risposte ci sono "
          f"({scuse} scuse)")
    errori = [r.get("errore") for r in righe if r.get("errore")]
    check(len(errori) == 2 and "ValueError" in errori[0],
          f"nel registro dei turni l'errore del giro: {errori}")
    # b) disco pieno: il registro dei turni non scrive, Calliope continua
    tmp = Path(tempfile.mkdtemp())
    detto, uscita, righe = _main_finto(tmp, ["uno", "due", "tre"], turnlog_rotto=True)
    check(isinstance(uscita, _Fine) and "Risposta a «tre»." in detto
          and "Scusa, ho avuto un problema." not in detto,
          "registro dei turni su disco pieno: Calliope continua a rispondere, senza scuse")
    # c) un guasto che si ripete: dopo ERRORI_MAX in poco tempo esce con un errore (systemd)
    from calliope import main as M
    tmp = Path(tempfile.mkdtemp())
    detto, uscita, righe = _main_finto(tmp, [RuntimeError("sempre")] * 10)
    check(isinstance(uscita, SystemExit) and uscita.code and "errori imprevisti" in str(
        uscita.code) and detto.count("Scusa, ho avuto un problema.") == M.ERRORI_MAX,
          f"guasto che si ripete: dopo {M.ERRORI_MAX} errori esce con un errore "
          f"({str(getattr(uscita, 'code', ''))[:60]})")

    # d) Whisper sulla GPU che solleva durante l'uso (VRAM finita): ricarica su CPU e rifà
    import sys as _sys
    from calliope import stt
    from calliope.config import Config
    carichi = []

    class Segmento:
        text = " ciao "

    class WhisperModel:
        def __init__(self, modello, device, compute_type):
            carichi.append(device)
            self.device, self.n = device, 0

        def transcribe(self, audio, **kw):
            self.n += 1
            if self.device == "cuda" and self.n > 2:      # dopo il riscaldamento
                raise RuntimeError("CUDA failed with error out of memory")
            return [Segmento()], None
    vero = _sys.modules.get("faster_whisper")
    _sys.modules["faster_whisper"] = types.SimpleNamespace(WhisperModel=WhisperModel)
    try:
        cfg = Config()
        cfg.whisper_device = "cuda"
        t = stt.Transcriber(cfg)
        avvisi = []
        t.on_ripiego = lambda: avvisi.append(1)
        audio = np.zeros(16000, dtype=np.float32)
        testo = t.transcribe(audio)
        check(testo == "ciao" and t.device == "cpu" and carichi == ["cuda", "cpu"]
              and avvisi == [1], f"errore CUDA in trascrizione: ricaricato su CPU, frase "
              f"trascritta lo stesso, frase d'attesa una volta ({carichi}, «{testo}»)")
        t.transcribe(audio)
        check(avvisi == [1] and carichi == ["cuda", "cpu"], "la frase dopo va su CPU, senza "
              "altre attese")
        cap = capacita.REGISTRO.get("stt")
        check(cap is not None and "CPU" in cap.motivo, f"capacità stt: {cap.motivo if cap else ''}")

        # e) server di trascrizione giù durante l'uso: frase d'attesa mentre carica la CPU
        class HttpGiu:
            def __init__(self):
                self.ok = True

            def post(self, *a, **k):
                if not self.ok:
                    raise ConnectionError("server giù")
                return types.SimpleNamespace(raise_for_status=lambda: None,
                                             json=lambda: {"text": "dal server"})
        http = HttpGiu()
        cfg.stt_url = "http://127.0.0.1:9/v1"
        s = stt.ServerTranscriber(cfg, http=http)
        avvisi.clear()
        s.on_ripiego = lambda: avvisi.append(1)
        check(s.transcribe(audio) == "dal server" and not avvisi, "server su: nessuna attesa")
        http.ok = False
        s._giu_da = -1e9
        testo = s.transcribe(audio)
        testo2 = s.transcribe(audio)
        check(testo == "ciao" and testo2 == "ciao" and avvisi == [1],
              f"server giù durante l'uso: frase d'attesa una volta, poi CPU ({avvisi})")
    finally:
        if vero is not None:
            _sys.modules["faster_whisper"] = vero
        else:
            _sys.modules.pop("faster_whisper", None)

# ─────────────────────────── 5. modello non pronto all'avvio ───────────────────────────
def prova_llm():
    import http.server
    import json

    from calliope import main as M
    from calliope.config import Config
    print("\n── 5. avvio con il modello non pronto: si aspetta invece di uscire ──")
    capacita.nuovo_registro()
    modelli = {"models": [{"name": "gemma4:e4b-it-qat", "size": 1}]}

    class Ollama(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            corpo = json.dumps(modelli).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def do_POST(self):
            # /api/chat con keep_alive "-1" (senza unità): come Ollama 0.35, 400 (03/10)
            corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            ok = corpo.get("keep_alive") != "-1"
            risposta = json.dumps({"message": {"role": "assistant", "content": "c"},
                                   "done": True} if ok else
                                  {"error": 'time: missing unit in duration "-1"'}).encode()
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(risposta)))
            self.end_headers()
            self.wfile.write(risposta)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Ollama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    cfg = Config()
    cfg.llm_backend, cfg.llm_model = "ollama", "gemma4:e4b-it-qat"
    cfg.llm_native_url = f"http://127.0.0.1:{srv.server_address[1]}"
    cfg.llm_attesa_avvio_s = 600

    class Brain:
        def __init__(self, guasti):
            self.guasti, self.tentativi = guasti, 0

        def warmup(self):
            self.tentativi += 1
            if self.tentativi <= self.guasti:
                raise ConnectionError("il modello si sta caricando")
    pause, detto = [], []
    b = Brain(3)
    r = M.aspetta_llm(cfg, b, dire=detto.append, dormi=pause.append)
    check(r is None and b.tentativi == 4 and pause == [2.0, 4.0, 8.0],
          f"modello pronto al quarto tentativo: Calliope aspetta (pause {pause}) e parte")
    check(len(detto) == 1, f"a voce una volta sola: {detto}")
    check(capacita.REGISTRO.get("llm").stato == "attiva", "capacità «llm» attiva alla fine")
    # il tempo massimo: si arrende (e allora systemd la riavvia)
    cfg.llm_attesa_avvio_s = 0
    r = M.aspetta_llm(cfg, Brain(99), dormi=pause.append)
    check(r and "ConnectionError" in r, f"con llm_attesa_avvio_s 0 si arrende subito: {r}")
    # un modello che manca non si aspetta: il server risponde, ma non lo ha
    cfg.llm_attesa_avvio_s = 600
    modelli["models"] = []
    pause.clear()
    r = M.aspetta_llm(cfg, Brain(99), dormi=pause.append)
    check(r and not pause and capacita.REGISTRO.get("llm").stato == "mancante",
          f"modello mancante: niente attesa, la capacità dice cosa scaricare "
          f"({capacita.REGISTRO.get('llm').prossimo_passo[:50]}…)")
    # 400 dal server: errore di configurazione, detto subito e senza attese (03/10:
    # llm_keep_alive "-1" scritto come testo, 11 minuti di «riprovo»)
    from calliope.brain import OllamaBackend
    modelli["models"] = [{"name": "gemma4:e4b-it-qat"}]
    pause.clear()

    class Vero:
        def __init__(self, keep):
            cfg.llm_keep_alive = keep
            self.backend = OllamaBackend(cfg)

        def warmup(self):
            self.backend.warmup()
    cfg.llm_keep_alive = "-1"
    vero = Vero("-1")
    # il backend lo manda già come numero: -1, che Ollama accetta
    r = M.aspetta_llm(cfg, vero, dormi=pause.append)
    check(r is None and not pause, f"keep_alive «-1» come testo: mandato come -1, parte ({r})")
    vero.backend._body = lambda *a, **k: {"model": cfg.llm_model, "keep_alive": "-1",
                                          "messages": []}
    r = M.aspetta_llm(cfg, vero, dormi=pause.append)
    check(r and r.startswith("il server rifiuta") and "missing unit" in r and not pause,
          f"400 all'avvio: errore di configurazione subito, nessuna attesa ({r[:90]}…)")
    cfg.llm_keep_alive = "30m"
    srv.shutdown()

# ─────────────────────────── 6. gestore di Linux: ripristino dei dati ───────────────────────────
def prova_gestore():
    import importlib.util
    import sqlite3
    from pathlib import Path
    print("\n── 6. gestore: servizio fermo prima del ripristino, -wal/-journal, archivio.db ──")
    radice = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("gestore_r", radice / "setup/linux/gestore.py")
    gestore = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gestore)
    tmp = Path(tempfile.mkdtemp())
    dati, app = tmp / "dati", tmp / "app"
    dati.mkdir()
    log = tmp / "systemctl.log"
    finto = tmp / "systemctl_finto.py"
    # il systemctl finto scrive cosa gli si chiede e, a «stop», se memoria.db c'è ancora
    finto.write_text(
        "import sys, pathlib\n"
        f"d = pathlib.Path({str(dati)!r})\n"
        f"with open({str(log)!r}, 'a') as f:\n"
        "    a = [x for x in sys.argv[1:] if x != '--user']\n"
        "    f.write(' '.join(a) + (' (dati ancora vecchi)' if (d / 'memoria.db.dopo-prova')"
        ".exists() is False else '') + chr(10))\n", encoding="utf-8")
    g = gestore.Gestore(app, dati=dati, bin_dir=tmp / "bin", unit_dir=tmp / "unit",
                        systemctl=[sys.executable, str(finto), "--user"], out=lambda *a: None)

    def valore(p):
        c = sqlite3.connect(p)
        try:
            return c.execute("SELECT v FROM t").fetchone()[0]
        finally:
            c.close()

    # dati di allora: memoria.db e archivio.db in WAL con l'ultimo valore ancora nel -wal
    for nome, v in (("memoria.db", "allora"), ("archivio.db", "archivio allora")):
        c = sqlite3.connect(dati / nome)
        c.execute("PRAGMA journal_mode = WAL")
        c.execute("PRAGMA wal_autocheckpoint = 0")
        c.execute("CREATE TABLE t (v TEXT)")
        c.execute("INSERT INTO t VALUES (?)", (v,))
        c.commit()
        if nome == "memoria.db":
            tenuta = c                      # aperta: i dati stanno ancora nel -wal
        else:
            c.close()
    check((dati / "memoria.db-wal").exists(), "memoria.db con i dati ancora nel -wal")
    copia = g.istantanea("v1")
    tenuta.close()
    check(copia is not None and valore(copia / "memoria.db") == "allora"
          and valore(copia / "archivio.db") == "archivio allora",
          "istantanea: memoria.db (con il -wal) e archivio.db copiati con l'API di backup")
    # la versione nuova scrive, e lascia un journal caldo accanto (crash a metà transazione)
    for nome in ("memoria.db", "archivio.db"):
        c = sqlite3.connect(dati / nome)
        c.execute("UPDATE t SET v = 'nuova'")
        c.commit()
        c.close()
    (dati / "memoria.db-journal").write_bytes(b"journal caldo della versione nuova")
    (dati / "memoria.db-wal").write_bytes(b"wal della versione nuova")
    g.ripristina(copia, "prova")
    righe = log.read_text().splitlines() if log.exists() else []
    check(righe and righe[0].startswith("stop calliope") and "dati ancora vecchi" in righe[0],
          f"il servizio si ferma prima di toccare i dati ({righe[:1]})")
    check(not (dati / "memoria.db-journal").exists() and not (dati / "memoria.db-wal").exists()
          and (dati / "memoria.db.dopo-prova-journal").exists()
          and (dati / "memoria.db.dopo-prova-wal").exists(),
          "journal e wal della versione nuova spostati insieme al suo database")
    check(valore(dati / "memoria.db") == "allora" and valore(dati / "archivio.db")
          == "archivio allora" and valore(dati / "memoria.db.dopo-prova") == "nuova",
          "dati di allora rimessi (anche archivio.db), quelli nuovi accanto")
    check(not list(dati.glob("*.tmp")), "nessun temporaneo rimasto")

# ─────────────────────────── 7. versioni dello schema ───────────────────────────
def prova_schema():
    import datetime
    import sqlite3
    from pathlib import Path

    from calliope import persistenza
    from calliope.agenda import Agenda
    from calliope.archivio.grafo import Grafo
    from calliope.liste import Liste
    from calliope.memory import Memory
    from calliope.ufficio.numerazione import Numeratore
    print("\n── 7. versioni dello schema: migrazioni numerate, dati più nuovi in sola lettura ──")
    capacita.nuovo_registro()
    tmp = Path(tempfile.mkdtemp())
    path = str(tmp / "memoria.db")
    a = Agenda(path)
    a.add("timer", "pasta", time.time() + 3600)
    Memory(path).remember("d", "il colore preferito è il verde")
    Liste(path)
    Numeratore(path)
    db = sqlite3.connect(path)
    ver = dict(db.execute("SELECT modulo, versione FROM meta_schema").fetchall())
    check(ver.get("agenda") == 1 and ver.get("memoria") == 1 and ver.get("liste") == 1
          and ver.get("numeri") == 1, f"ogni modulo ha la sua versione in meta_schema: {ver}")
    # migrazioni numerate: dalla versione registrata in avanti, una volta sola
    fatte = []
    m = [lambda d: fatte.append(1),
         lambda d: (fatte.append(2), persistenza.aggiungi_colonna(d, "agenda", "colore", "TEXT"))]
    db.execute("INSERT INTO meta_schema VALUES ('prova', 1)")
    db.commit()
    persistenza.migra(db, "prova", m)
    persistenza.migra(db, "prova", m)
    check(fatte == [2] and persistenza.versione_schema(db, "prova") == 2,
          f"migrazioni numerate: solo quella che manca, una volta ({fatte})")
    # una versione più nuova (dopo «calliope torna» senza i dati): sola lettura, e lo dice
    db.execute("UPDATE meta_schema SET versione = 7 WHERE modulo IN ('agenda', 'numeri')")
    db.commit()
    db.close()
    a2 = Agenda(path)
    check(not a2.scrivibile and [it["label"] for it in a2.items()] == ["pasta"],
          "agenda con uno schema più nuovo: si legge ma è in sola lettura")
    try:
        a2.add("timer", "uova", time.time() + 60)
        scritto = True
    except sqlite3.Error:
        scritto = False
    check(not scritto, "e non scrive (nessuna riga di una versione vecchia nel file nuovo)")
    cap = capacita.REGISTRO.get("memoria")
    check(cap is not None and cap.stato == "guasta" and "calliope aggiorna" in cap.prossimo_passo,
          f"capacità guasta con il passo: {cap.motivo if cap else ''}")
    n = Numeratore(path)
    try:
        n.emetti("fatture", datetime.date(2026, 10, 3), lambda k, t: {"file": []})
        emesso = True
    except sqlite3.Error:
        emesso = False
    check(not n.scrivibile and not emesso, "numerazione con uno schema più nuovo: niente numeri")
    # archivio: meta.schema letta, mai riscritta al ribasso
    gp = str(tmp / "archivio.db")
    g = Grafo(gp)
    g.close()
    c = sqlite3.connect(gp)
    c.execute("UPDATE meta SET valore = '9' WHERE chiave = 'schema'")
    c.commit()
    c.close()
    g = Grafo(gp)
    c = sqlite3.connect(gp)
    v = c.execute("SELECT valore FROM meta WHERE chiave = 'schema'").fetchone()[0]
    c.close()
    check(not g.scrivibile and v == "9", f"archivio più nuovo: sola lettura, versione non "
          f"riscritta al ribasso ({v})")
    g.close()

# ─────────────────────────── 8. varie: config, registro, satellite ───────────────────────────
def prova_varie():
    import datetime
    from pathlib import Path

    from calliope.config import Config, load_config
    from calliope.turnlog import TurnLog
    print("\n── 8. varie: limiti della configurazione, pulizia del registro, invio al satellite ──")
    tmp = Path(tempfile.mkdtemp())
    # a) valori fuori dall'intervallo: segnalati, resta il predefinito
    f = tmp / "c.yaml"
    f.write_text("llm:\n  llm_num_ctx: -5\n  llm_temperature: 7\n  max_tool_turns: 3\n",
                 encoding="utf-8")
    vecchio = os.environ.get("CALLIOPE_CONFIG_LOCALE")
    os.environ["CALLIOPE_CONFIG_LOCALE"] = str(tmp / "nessuno.yaml")
    try:
        cfg = load_config(str(f))
    finally:
        if vecchio is None:
            os.environ.pop("CALLIOPE_CONFIG_LOCALE", None)
        else:
            os.environ["CALLIOPE_CONFIG_LOCALE"] = vecchio
    check(cfg.llm_num_ctx == Config().llm_num_ctx and cfg.llm_temperature == 0.3 and cfg.max_tool_turns == 3,
          f"num_ctx -5 e temperatura 7 rifiutati (restano {cfg.llm_num_ctx} e "
          f"{cfg.llm_temperature}), il valore buono accanto passa")

    # b) registro dei turni: la pulizia anche durante l'esecuzione, al cambio di giorno
    cartella = tmp / "registro"
    log = TurnLog(str(cartella), keep_days=30)
    vecchio_file = cartella / "turni-2020-01-01.jsonl"
    vecchio_file.write_text("{}\n", encoding="utf-8")
    log._pulito_il = datetime.date.today() - datetime.timedelta(days=1)   # ieri
    log.write({"inizio": datetime.datetime.now().isoformat(), "testo": "ciao"})
    check(not vecchio_file.exists(), "registro dei turni: i file oltre keep_days si cancellano "
          "anche a Calliope accesa (una volta al giorno)")

    # c) invio verso un satellite che non legge più: tempo massimo, connessione chiusa
    from calliope.satellite.server import Collegamento

    class Sock:
        def __init__(self):
            self.chiuso = threading.Event()

        def shutdown(self, how):
            self.chiuso.set()

        def close(self):
            self.chiuso.set()

    class WsBloccato:
        def __init__(self):
            self.socket = Sock()

        def send(self, dati):
            # il buffer TCP del satellite è pieno: la send non torna finché il socket vive
            if not self.socket.chiuso.wait(30):
                return
            raise OSError("socket chiuso")
    coll = Collegamento(WsBloccato(), {"id": 1, "nome": "portatile"}, "h")
    coll.INVIO_MAX_S = 0.6
    fin, ok, dt = in_thread(lambda: coll.invia_bin(b"x" * 1000), 10)
    check(fin and ok is False and coll.chiuso.is_set() and dt < 3,
          f"satellite che non legge: l'invio si arrende dopo {dt:.1f} s (prima ~20 s, o per "
          f"sempre) e la connessione si chiude")
    check(coll.invia(tipo="frase") is False, "e gli invii dopo falliscono subito")

# ─────────────────────────── 9. combinazioni incrociate ───────────────────────────
def prova_incroci():
    from pathlib import Path
    print("\n── 9. combinazioni della notte incrociate: annunci con domanda, timer, azione in "
          "sospeso ──")
    capacita.nuovo_registro()
    # Documento pronto («La apro?») e domanda dell'agente nello stesso giro, poi un timer che
    # scade mentre la domanda del documento aspetta la risposta
    tmp = Path(tempfile.mkdtemp())
    risposte, agende = [], []
    doc = {"messaggio": "È pronta la lettera per il condominio. La apro?",
           "in_sospeso": {"cosa": "aprire la lettera", "domanda": "La apro?"}}
    lav = {"messaggio": "Il lavoro della pagina web ha una domanda: di che colore la vuoi?",
           "in_sospeso": {"cosa": "rispondere al lavoro", "domanda": "di che colore?"}}

    def prima_di_ascoltare(n):
        if n == 1:                         # il timer scade mentre la domanda aspetta
            agende[0].add("timer", "pasta", time.time() - 1)
            aspetta(lambda: not agende[0].due.empty(), 5)
            return "sveglia"
    detto, uscita, righe = _main_finto(tmp, ["sì", "rosso"], documenti=[doc], lavori=[lav],
                                       prima_di_ascoltare=prima_di_ascoltare,
                                       risposte=risposte, agende=agende)
    check(isinstance(uscita, _Fine), f"lo scenario arriva in fondo ({type(uscita).__name__})")
    i = {k: next((n for n, t in enumerate(detto) if k in t), -1)
         for k in ("La apro?", "timer pasta", "«sì»", "di che colore", "«rosso»")}
    check(-1 not in i.values() and i["La apro?"] < i["timer pasta"] < i["«sì»"]
          < i["di che colore"] < i["«rosso»"],
          f"ordine: documento, timer, «sì», poi la domanda dell'agente, «rosso» ({i})")
    check(risposte == [("sì", "aprire la lettera"), ("rosso", "rispondere al lavoro")],
          f"il «sì» va al documento anche con il timer in mezzo, «rosso» all'agente: "
          f"{risposte}")
    # Un annuncio rinviato non resta in coda per sempre se nessuno risponde: alla scadenza
    # della domanda di prima l'ascolto si sveglia da solo (main.rinvia) e lo dice
    tmp = Path(tempfile.mkdtemp())
    t0 = time.monotonic()
    detto, uscita, righe = _main_finto(
        tmp, [], documenti=[doc], lavori=[lav], scadenza_s=0.6,
        prima_di_ascoltare=lambda n: "attendi" if n == 1 else None)
    check(any("di che colore" in t for t in detto) and time.monotonic() - t0 < 5,
          f"nessuno risponde al «La apro?»: la domanda dell'agente arriva alla scadenza "
          f"({time.monotonic() - t0:.1f} s), senza che nessuno parli")


def prova_cortesia():
    from pathlib import Path
    print("\n── 10. cortesia (05/10): «grazie» e «perfetto» hanno una risposta, «basta» no ──")
    capacita.nuovo_registro()
    tmp = Path(tempfile.mkdtemp())
    risposte = []
    detto, uscita, righe = _main_finto(
        tmp, ["Grazie.", "Perfetto.", "Ok, grazie", "Basta.", "Calliope, stop.",
              "Grazie mille.", "chiedimi qualcosa", "Ok.", "Va bene così, grazie.",
              "Grazie, e domani che tempo fa?", "Lascia stare, grazie."], risposte=risposte)
    check(isinstance(uscita, _Fine), f"lo scenario arriva in fondo ({type(uscita).__name__})")
    attese = ["Prego!", "Bene!", "Figurati.", "Di niente.", "Vuoi altro?",
              "Risposta a «Ok.».", "A disposizione.", "Risposta a «Grazie, e domani che "
              "tempo fa?»."]
    detto = [t for t in detto if not t.startswith("Ciao, sono")]      # il saluto d'avvio
    check(detto == attese, f"frasi dette, a rotazione, senza il modello: {detto}")
    check([t for t, _ in risposte] == ["chiedimi qualcosa", "Ok.",
                                       "Grazie, e domani che tempo fa?"],
          f"al modello solo la domanda, «Ok.» dopo una domanda e la frase con una richiesta: "
          f"{[t for t, _ in risposte]}")
    esiti = [r.get("esito") for r in righe if r.get("esito")]
    check(esiti.count("cortesia") == 5 and esiti.count("stop") == 3,
          f"nel registro 5 «cortesia» e 3 «stop» (basta, stop, lascia stare): {esiti}")
    check(all("cortesia" in (r.get("regole") or []) for r in righe
              if r.get("esito") == "cortesia"), "regola «cortesia» nel registro dei turni")
    # Con un'azione in sospeso («La apro?») «Grazie.» resta al modello (può essere un sì)
    tmp = Path(tempfile.mkdtemp())
    risposte = []
    doc = {"messaggio": "È pronta la lettera. La apro?",
           "in_sospeso": {"cosa": "aprire la lettera", "domanda": "La apro?"}}
    detto, uscita, righe = _main_finto(tmp, ["Grazie."], documenti=[doc], risposte=risposte)
    check(risposte == [("Grazie.", "aprire la lettera")] and "Prego!" not in detto,
          f"«Grazie.» dopo «La apro?» va al modello con l'azione in sospeso: {risposte}")


SEZIONI = {"tts": prova_tts, "agenda": prova_agenda, "speakers": prova_speakers,
           "ciclo": prova_ciclo, "llm": prova_llm, "gestore": prova_gestore,
           "schema": prova_schema,
           "varie": prova_varie, "incroci": prova_incroci, "cortesia": prova_cortesia}

if __name__ == "__main__":
    scelte = sys.argv[1:] or list(SEZIONI)
    for nome in scelte:
        SEZIONI[nome]()
    print(f"\n{'Tutto ok' if not ERRORI else f'{ERRORI} errori'}")
    sys.exit(1 if ERRORI else 0)
