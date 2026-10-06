"""
Ascolto: microfono sempre aperto, Silero VAD, barge-in mentre Calliope parla, misura
dell'eco. Estratto da calliope.py il 26/09/2026 (roadmap 2: divisione in package).

Dal 02/10/2026 lo stesso `Listener` gira anche sul satellite (calliope/satellite/client.py):
lì `on_audio` riceve i frame della frase appena è rivolta a Calliope, per mandarli al
server mentre si parla; prima, da addormentata, l'audio non esce da qui.
"""
import collections
import queue
import threading
import time

import numpy as np
import sounddevice as sd

from .config import Config


# ─────────────────────────────── ASCOLTO (VAD) ───────────────────────────────
class Listener:
    FRAME = 512  # campioni a 16 kHz = 32 ms (richiesto da Silero)

    def __init__(self, cfg: Config, sorgente=None):
        """`sorgente`: la classe del flusso del microfono, con gli argomenti di
        sd.InputStream (le prove ne passano una che legge un file)."""
        from .vad import carica_vad
        self.cfg = cfg
        self._sorgente = sorgente or sd.InputStream
        # Silero VAD con torch (Windows, come sempre) o con onnxruntime senza torch (Linux
        # aarch64, dove torch su PyPI è quello con CUDA: vedi vad.py)
        self.model = carica_vad(cfg.vad_motore, cfg.vad_modello)
        self.frames: queue.Queue = queue.Queue()
        self.active = False       # half-duplex: fuori da listen() si tengono solo gli ultimi frame
        self.started_at = 0.0     # istante (monotonic) in cui è iniziata l'ultima frase
        # Istante (monotonic) in cui è finita la voce dell'ultima frase, senza il silenzio con
        # cui il VAD la chiude (06/10: `fine_parlato_s` nel registro dei turni)
        self.ended_at = 0.0
        # Avvisi all'arbitro degli agenti (vedi listen): funzioni senza argomenti, o None
        self.on_speech_start = None
        self.on_speech_end = None
        # Satellite: riceve una lista di frame (float32) appena la frase è rivolta a
        # Calliope (sveglia, o wake word scattata) e poi a ogni frame nuovo; se la frase si
        # butta dopo, arriva on_speech_end. None = niente (Calliope in locale)
        self.on_audio = None
        # Suono d'inizio ascolto (04/10, calliope/suoni.py): chiamata senza argomenti quando
        # la wake word acustica scatta a Calliope addormentata. Non deve bloccare
        self.on_wake = None
        # Ultimi frame captati mentre non si ascolta: diventano il pre-roll iniziale.
        # Senza, chi parlava appena Calliope finiva perdeva l'attacco (test del 24/09:
        # voce a 100–160 ms dall'inizio invece di 240–290, «Equale rospaniac»).
        frame_ms = self.FRAME / cfg.sample_rate * 1000
        self._recent = collections.deque(maxlen=max(1, int(cfg.preroll_ms / frame_ms)))
        self._recent_lock = threading.Lock()
        # Il flusso del microfono resta sempre aperto: riaprirlo a ogni turno costava
        # 150–200 ms e tagliava l'attacco delle frasi dette subito dopo una risposta.
        self.stream = None
        self._open_stream()

    def _open_stream(self):
        """(Ri)apre il microfono. Se il dispositivo non c'è, riprova finché non torna."""
        if self.stream is not None:
            try:
                self.stream.abort()
                self.stream.close()
            except Exception:
                pass
        while True:
            try:
                self.stream = self._sorgente(
                    samplerate=self.cfg.sample_rate, channels=1, dtype="float32",
                    blocksize=self.FRAME, device=self.cfg.input_device,
                    callback=self._callback)
                self.stream.start()
                return
            except Exception as e:
                print(f"   [MIC] microfono non disponibile ({e}): riprovo tra 2 secondi", flush=True)
                time.sleep(2)

    def _callback(self, indata, n, t, status):
        frame = indata[:, 0].copy()
        with self._recent_lock:          # stesso lock di listen(): nessun frame perso
            if self.active:
                self.frames.put(frame)
            # Sempre: all'inizio di listen() gli ultimi ~300 ms fanno da pre-roll
            self._recent.append(frame)

    def watch_for_name(self, wake, stop: threading.Event, muted,
                       voice_ok=None) -> list | None:
        """Barge-in mentre Calliope parla. Niente Whisper finché non scatta.

        Livello A: la wake word; se scatta restituisce gli ultimi ~2 s di audio (il nome
        e l'inizio della richiesta), da passare a `listen(seed=…)`. Con `muted()` vero
        (Calliope sta dicendo il proprio nome) gli scatti si ignorano.
        Livello B leggero (`voice_ok` non None, solo se all'avvio non si è sentita l'eco,
        vedi `measure_echo`): anche il VAD; dopo `barge_in_voice_min_s` di parlato (e di
        nuovo al doppio) l'audio va a `voice_ok(audio)`, che dice se è la voce di una
        persona registrata. Così TV e ospiti non la interrompono.
        Restituisce None se `stop` arriva prima.
        """
        cfg = self.cfg
        frame_ms = self.FRAME / cfg.sample_rate * 1000
        ring = collections.deque(maxlen=int(cfg.barge_in_seed_s * 1000 / frame_ms))
        pre = collections.deque(maxlen=max(1, int(cfg.preroll_ms / frame_ms)))
        if wake is not None:
            wake.reset()
        streak = 0
        seg, gap, checks = [], 0, 0          # parlato in corso (livello B)
        steps = (cfg.barge_in_voice_min_s * 1000, 2 * cfg.barge_in_voice_min_s * 1000)
        if voice_ok is not None:
            self.model.reset_states()
        with self._recent_lock:
            while not self.frames.empty():
                self.frames.get_nowait()
            self.active = True
        try:
            while not stop.is_set():
                try:
                    frame = self.frames.get(timeout=0.1)
                except queue.Empty:
                    continue
                ring.append(frame)
                if voice_ok is not None:
                    prob = self.model.prob(frame)
                    if prob >= cfg.vad_threshold:
                        seg.append(frame)
                        gap = 0
                    elif seg:
                        seg.append(frame)
                        gap += 1
                        if gap * frame_ms > 300:          # pausa: il parlato è finito
                            seg, gap, checks = [], 0, 0
                    else:
                        pre.append(frame)
                    voiced_ms = (len(seg) - gap) * frame_ms
                    if checks < len(steps) and voiced_ms >= steps[checks]:
                        checks += 1
                        if voice_ok(np.concatenate(seg)):
                            print("\n   [BARGE-IN] voce di una persona registrata: mi fermo",
                                  flush=True)
                            return list(pre) + seg
                score = wake.process(frame) if wake is not None else None
                if score is None:
                    continue
                if muted():
                    streak = 0
                    continue
                streak = streak + 1 if score >= cfg.barge_in_threshold else 0
                if streak >= cfg.wake_consecutive:
                    print(f"\n   [BARGE-IN] sentito il nome ({score:.2f}): mi fermo", flush=True)
                    # Il microfono resta attivo: i frame che arrivano finché listen()
                    # riparte restano in coda (è il seguito della richiesta)
                    return list(ring)
            self.active = False
            return None
        except BaseException:
            self.active = False
            raise

    def measure_echo(self, stop: threading.Event) -> float:
        """Quota di frame in cui il VAD sente parlato, finché arriva `stop`.

        Si usa mentre Calliope dice il saluto: se il VAD scatta sulla sua voce, il
        microfono sente l'eco (altoparlante senza cancellazione) e il barge-in con la
        voce non si può usare. Il microfono interno del portatile, aperto in MME, ha la
        cancellazione dell'eco di Windows (docs/ricerche/2026-09-26-cancellazione-eco.md).
        """
        cfg = self.cfg
        self.model.reset_states()
        with self._recent_lock:
            while not self.frames.empty():
                self.frames.get_nowait()
            self.active = True
        total = speech = 0
        try:
            while not stop.is_set():
                try:
                    frame = self.frames.get(timeout=0.1)
                except queue.Empty:
                    continue
                total += 1
                if self.model.prob(frame) >= cfg.vad_threshold:
                    speech += 1
        finally:
            self.active = False
        return speech / total if total else 0.0

    def listen(self, wake=None, awake_until: float = float("inf"),
               seed: list | None = None, wakeup: threading.Event | None = None):
        """Restituisce la prossima frase captata.

        Con `wake` (rilevatore della wake word) le frasi iniziate a Calliope addormentata,
        cioè dopo `awake_until`, si restituiscono solo se il rilevatore è scattato
        durante la frase. Le altre vengono buttate qui, in memoria: non arrivano a
        Whisper, al registro né ai file. Il rilevatore riceve gli stessi frame del VAD
        e la frase comprende il nome, così «Calliope, che ore sono?» detto d'un fiato
        arriva intero. Dopo la chiamata `self.woke` e `self.wake_score` dicono se e
        quanto è scattato.

        Con `seed` (frame consegnati da `watch_for_name` dopo un barge-in) la frase è già
        cominciata: si parte da quei frame e il VAD la chiude al silenzio come sempre.

        Con `wakeup` impostato (un timer o un promemoria scaduto) restituisce None appena
        nessuno sta parlando, così Calliope può annunciarlo senza aspettare una frase.
        """
        cfg = self.cfg
        frame_ms = self.FRAME / cfg.sample_rate * 1000
        preroll = collections.deque(maxlen=max(1, int(cfg.preroll_ms / frame_ms)))
        # Arbitro degli agenti (calliope/agenti/arbitro.py): `on_speech_start` appena qualcuno
        # comincia a parlare a Calliope (sveglia, o nome sentito dal rilevatore), così un agente
        # sullo stesso Ollama si ferma mentre la frase finisce e Whisper trascrive;
        # `on_speech_end` se la frase si butta. Solo un flag: non bloccano mai.
        on_start = getattr(self, "on_speech_start", None)
        on_end = getattr(self, "on_speech_end", None)
        on_audio = getattr(self, "on_audio", None)
        on_wake = getattr(self, "on_wake", None)
        signaled, sent = False, 0

        speech, silent, talking = [], 0, False
        self.woke, self.wake_score, streak = False, 0.0, 0
        if wake is not None:
            wake.reset()            # half-duplex: mentre Calliope parlava non l'ha sentita
        self.model.reset_states()
        while not seed and not self.frames.empty():   # dopo un barge-in la coda è il seguito
            self.frames.get_nowait()
        # Il pre-roll parte dagli ultimi ~300 ms captati mentre Calliope parlava.
        # Con le cuffie non contengono la sua voce; in cassa potrebbero contenerne la
        # coda, ma finiscono solo in testa a una frase che il VAD ha già riconosciuto.
        with self._recent_lock:
            preroll.extend(self._recent)
            self._recent.clear()
            self.active = True
        if seed:
            talking, speech = True, list(seed)
            self.started_at = time.monotonic() - len(seed) * frame_ms / 1000
            self.woke, self.wake_score = True, 1.0
        try:
            while True:
                if wakeup is not None and wakeup.is_set() and not talking:
                    return None
                try:
                    frame = self.frames.get(timeout=1.0)
                except queue.Empty:
                    # In un secondo dovrebbero arrivare ~31 frame: se non arriva nulla il
                    # microfono si è fermato o è stato staccato. Si riapre e si riparte.
                    print("   [MIC] nessun audio dal microfono da 1 secondo: riapro il flusso",
                          flush=True)
                    self._open_stream()
                    if signaled and on_end is not None:
                        on_end()                 # la frase a metà si butta
                    signaled, sent = False, 0
                    talking, speech, silent = False, [], 0
                    preroll.clear()
                    self.model.reset_states()
                    continue
                if len(frame) != self.FRAME:
                    continue
                prob = self.model.prob(frame)

                if wake is not None:
                    score = wake.process(frame)          # un punteggio ogni 80 ms
                    if score is not None:
                        streak = streak + 1 if score >= cfg.wake_threshold else 0
                        if talking:
                            self.wake_score = max(self.wake_score, score)
                            if streak >= cfg.wake_consecutive:
                                if (not self.woke and on_wake is not None
                                        and self.started_at > awake_until):
                                    try:
                                        on_wake()
                                    except Exception:  # noqa: BLE001 — un suono non ferma
                                        pass
                                self.woke = True

                if not talking:
                    preroll.append(frame)
                    if prob >= cfg.vad_threshold:
                        talking, speech, silent = True, list(preroll), 0
                        self.started_at = time.monotonic() - len(preroll) * frame_ms / 1000
                        self.woke, self.wake_score = False, 0.0
                    continue

                speech.append(frame)
                if not signaled and (
                        wake is None or self.started_at <= awake_until or self.woke):
                    signaled = True
                    if on_start is not None:
                        on_start()
                if signaled and on_audio is not None:
                    on_audio(speech[sent:])          # satellite: la frase parte già ora
                    sent = len(speech)
                silent = silent + 1 if prob < cfg.vad_threshold - 0.15 else 0
                too_long = len(speech) * frame_ms >= cfg.max_utterance_s * 1000
                if silent * frame_ms >= cfg.silence_ms or too_long:
                    long_enough = (len(speech) - silent) * frame_ms >= cfg.min_speech_ms
                    for_me = wake is None or self.started_at <= awake_until or self.woke
                    if long_enough and for_me:
                        self.ended_at = time.monotonic() - silent * frame_ms / 1000
                        return np.concatenate(speech)
                    if signaled and on_end is not None:
                        on_end()
                    signaled, sent = False, 0
                    if long_enough and self.wake_score >= 0.3:
                        # Quasi-risveglio: solo il punteggio, per tarare la soglia
                        print(f"   (quasi risveglio: {self.wake_score:.2f})", flush=True)
                    # Rumore, oppure parlato non rivolto a Calliope: si butta
                    talking, speech, silent = False, [], 0
                    preroll.clear()
                    self.model.reset_states()
        finally:
            self.active = False
