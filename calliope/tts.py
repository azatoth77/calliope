"""
Voce: divisione in frasi, pulizia del testo per il TTS e Speaker (Piper, due thread:
sintesi e riproduzione, interruzione, cambio voce, segnale acustico).
Estratto da calliope.py il 26/09/2026 (roadmap 2: divisione in package).
"""
import queue
import re
import threading
import time

import numpy as np
import sounddevice as sd

from .config import Config
from .pronuncia import Pronuncia, supporta_fonemi
from .testi import SENTENCE_END


# ─────────────────────────────── FRASI ───────────────────────────────
_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")


def split_sentences(chunks, min_chars: int = 25):
    """Raggruppa i token in frasi da mandare al TTS appena sono complete."""
    buf = ""
    for c in chunks:
        buf += c
        while True:
            cut = next((m.end() for m in SENTENCE_END.finditer(buf)
                        if m.end() >= min_chars), None)
            if cut is None:
                break
            sentence, buf = buf[:cut].strip(), buf[cut:]
            if sentence:
                yield sentence
    if buf.strip():
        yield buf.strip()


_CITATION = re.compile(r"[,;]?\s*\b(secondo|stando a|come (dice|riporta|scrive)|come si legge (su|in))"
                       r"\s+(la\s+|l')?(wikipedia|enciclopedia)\b[,;]?", re.I)


def strip_false_citation(sentence: str) -> str:
    """Toglie «secondo Wikipedia» da una frase detta senza aver consultato la biblioteca
    (il 26/09 lo diceva anche rispondendo a memoria). La frase resta, senza la fonte."""
    out = _CITATION.sub("", sentence)
    if out == sentence:
        return sentence
    out = re.sub(r"\s+([.,;:!?])", r"\1", out).strip(" ,;")
    return out[:1].upper() + out[1:] if out else ""


def clean_for_speech(text: str) -> str:
    text = _EMOJI.sub("", text)
    text = re.sub(r"[*#`_>\[\]|]", "", text)
    # Maiuscole dentro una parola ("museI"): il TTS le leggerebbe come lettere staccate
    text = re.sub(r"(?<=[a-zà-ù])[A-ZÀ-Ù]+", lambda m: m.group().lower(), text)
    return re.sub(r"\s+", " ", text).strip()


# ─────────────────────────────── USCITA AUDIO ───────────────────────────────
class UscitaLocale:
    """Le casse (o le cuffie) di questo computer, con le attenzioni scoperte sulle cuffie
    Bluetooth: silenzio all'apertura (`tts_lead_s`), silenzio prima di chiudere
    (`tts_tail_s`, cambio di frequenza), silenzio continuo tra i turni (`keepalive`).

    Estratta da Speaker il 02/10/2026 per il satellite (calliope/satellite/), che riproduce
    le frasi arrivate dal server con le stesse attenzioni. `apri_flusso` è la classe del
    flusso (sd.RawOutputStream; le prove ne passano una finta). La usa un thread solo.

    Non solleva mai (03/10, analisi di robustezza): se le cuffie spariscono a metà frase
    PortAudio dà un errore, e prima il thread della riproduzione moriva con lui, lasciando
    Calliope viva ma muta per sempre. Ora l'uscita si segna guasta, l'audio si scarta (lo
    dice il log) e la si riapre da sola con attese crescenti (1, 2, 4… fino a 30 s): prima
    il dispositivo scelto, poi quello predefinito del sistema. `on_stato(guasta, motivo)`
    avvisa del cambio (il registro delle capacità, «audio»)."""

    RIPROVA_MAX_S = 30.0

    def __init__(self, cfg: Config, sample_rate: int, apri_flusso=None, device="cfg",
                 on_stato=None):
        self.cfg = cfg
        self.device = cfg.output_device if device == "cfg" else device
        self._apri = apri_flusso or sd.RawOutputStream
        self.stream = None
        self.on_stato = on_stato
        self.guasta = False
        self.motivo = ""
        self._rate = int(sample_rate)
        self._riprova_alle = 0.0
        self._attesa = 1.0
        self.scartati_s = 0.0               # audio non riprodotto per l'uscita guasta
        self.apri(sample_rate)

    @property
    def rate(self) -> int:
        if self.stream is None:
            return self._rate
        try:
            return int(self.stream.samplerate)
        except Exception:  # noqa: BLE001
            return self._rate

    @property
    def latency(self) -> float:
        if self.stream is None:
            return 0.0
        try:
            return float(self.stream.latency)
        except Exception:  # noqa: BLE001
            return 0.0

    def _chiudi_flusso(self, coda: bool):
        st, self.stream = self.stream, None
        if st is None:
            return
        try:
            if coda:
                # Le cuffie Bluetooth tengono un loro buffer oltre a quello di PortAudio:
                # senza questo silenzio perdono la coda della frase. stop() aspetta che il
                # buffer sia riprodotto; close() da solo lo scarterebbe
                st.write(b"\0\0" * int(self.rate_di(st) * self.cfg.tts_tail_s))
            st.stop()
        except Exception:  # noqa: BLE001 — un flusso guasto si chiude come si può
            pass
        try:
            st.close()
        except Exception:  # noqa: BLE001
            pass

    def rate_di(self, st) -> int:
        try:
            return int(st.samplerate)
        except Exception:  # noqa: BLE001
            return self._rate

    def _apri_su(self, device, sample_rate: int):
        st = self._apri(samplerate=sample_rate, channels=1, dtype="int16", device=device)
        try:
            st.start()
            st.write(b"\0\0" * int(sample_rate * self.cfg.tts_lead_s))
        except Exception:
            try:
                st.close()
            except Exception:  # noqa: BLE001
                pass
            raise
        return st

    def apri(self, sample_rate: int) -> bool:
        """(Ri)apre l'uscita alla frequenza data. False se non si apre (resta guasta e si
        riprova più tardi da sola)."""
        self._rate = int(sample_rate)
        self._chiudi_flusso(coda=not self.guasta)
        errore = None
        # Il dispositivo scelto, poi quello predefinito: le cuffie spente non tornano subito,
        # le casse del portatile sì
        for dev in dict.fromkeys([self.device, None]):
            try:
                self.stream = self._apri_su(dev, self._rate)
                break
            except Exception as e:  # noqa: BLE001
                errore = e
        if self.stream is None:
            self._guasto(errore)
            return False
        if self.guasta:
            self.guasta = False
            self._attesa = 1.0
            perso = f" (audio non riprodotto: {self.scartati_s:.1f} s)" if self.scartati_s else ""
            print(f"   [AUDIO] Uscita audio di nuovo disponibile{perso}", flush=True)
            self.scartati_s = 0.0
            self._avvisa()
        return True

    def _guasto(self, errore):
        motivo = f"{type(errore).__name__}: {errore}" if errore is not None else "errore"
        primo = not self.guasta
        self.guasta, self.motivo = True, motivo
        self._chiudi_flusso(coda=False)
        self._riprova_alle = time.monotonic() + self._attesa
        if primo:
            import sys
            if not sys.is_finalizing():
                print(f"   [AUDIO] Uscita audio guasta ({motivo}): scarto l'audio e riprovo "
                      f"ad aprirla da sola", flush=True)
            self._avvisa()
        self._attesa = min(self._attesa * 2, self.RIPROVA_MAX_S)

    def _avvisa(self):
        cb = self.on_stato
        if cb is not None:
            try:
                cb(self.guasta, self.motivo)
            except Exception:  # noqa: BLE001
                pass

    def _ripristina(self) -> bool:
        """Con l'uscita guasta: riprova ad aprirla se è il momento. True se è aperta."""
        if not self.guasta:
            return True
        if time.monotonic() < self._riprova_alle:
            return False
        return self.apri(self._rate)

    def scrivi(self, audio: bytes) -> bool:
        """Scrive un pezzo di audio. False se l'uscita è guasta: il pezzo si scarta."""
        if self.guasta and not self._ripristina():
            self.scartati_s += len(audio) / 2 / max(1, self._rate)
            return False
        try:
            self.stream.write(audio)
            return True
        except Exception as e:  # noqa: BLE001 — cuffie sparite, PortAudio chiuso…
            self.scartati_s += len(audio) / 2 / max(1, self._rate)
            self._guasto(e)
            return False

    def mantieni(self) -> bool:
        """Silenzio di 20 ms (keepalive). Con l'uscita guasta prova a riaprirla e aspetta
        20 ms. Restituisce sempre True (prima False con PortAudio chiuso, e il thread della
        riproduzione finiva: anche quando le cuffie sparivano)."""
        if self.guasta and not self._ripristina():
            time.sleep(0.02)
            return True
        try:
            self.stream.write(b"\0\0" * int(self.rate * 0.02))
        except Exception as e:  # noqa: BLE001
            self._guasto(e)
            time.sleep(0.02)
        return True

    def chiudi(self):
        self._chiudi_flusso(coda=False)


def dice_nome(cfg, testo: str) -> bool:
    """La frase contiene una parola che sveglia (il nome, o la wake word: «il computer è…»
    in modalità startrek)? Allora mentre la dice il barge-in la ignora."""
    low = (testo or "").lower()
    return any(n.lower() in low for n in getattr(cfg, "wake_names", None) or [cfg.name])


def segnale(rate: int) -> bytes:
    """Due note brevi prima di un annuncio (timer, promemoria): chi è nella stanza capisce
    che non è una risposta ma un avviso. PCM int16 mono alla frequenza data."""
    notes = []
    for freq in (880, 660):
        t = np.arange(int(rate * 0.18)) / rate
        env = np.minimum(1, np.minimum(t / 0.01, (t[-1] - t) / 0.05))
        notes.append(0.25 * np.sin(2 * np.pi * freq * t) * env)
        notes.append(np.zeros(int(rate * 0.05)))
    return (np.concatenate(notes) * 32767).astype(np.int16).tobytes()


# ─────────────────────────────── VOCE (TTS) ───────────────────────────────
_END_TURN = object()


class _Filler:
    """Frase d'attesa da sintetizzare al momento (non era pronta per questa voce)."""

    def __init__(self, text: str):
        self.text = text


class _VoiceChange:
    """Segnale di cambio voce: viaggia nelle code insieme alle frasi, così la voce
    cambia esattamente tra una frase e l'altra e il flusso audio viene riaperto
    solo dal thread che lo usa."""

    def __init__(self, voice):
        self.voice = voice


# Piper e espeak-ng da più thread (06/10, più satelliti insieme): espeak-ng ha uno stato
# globale, quindi i fonemi uno alla volta in tutto il processo; la voce vera (onnxruntime) può
# girare in parallelo. Con piper-tts < 1.3 (fonemi e voce insieme) la sintesi intera
_SINTESI = threading.Lock()


def _fonemi_protetti(voice):
    """`voice.phonemize` sotto il lucchetto comune (una volta per voce)."""
    f = getattr(voice, "phonemize", None)
    if f is None or getattr(f, "_protetta", False):
        return

    def phonemize(*a, **k):
        with _SINTESI:
            return f(*a, **k)
    phonemize._protetta = True
    try:
        voice.phonemize = phonemize
    except (AttributeError, TypeError):
        pass


class Speaker:
    """Due thread: uno sintetizza la frase successiva mentre l'altro riproduce.

    Si può interrompere (barge-in, `interrupt()`): la riproduzione va a blocchi da
    100 ms e si ferma al blocco successivo; `played` dice quali frasi sono state
    pronunciate per intero, così la storia dell'LLM contiene solo ciò che si è sentito.
    """

    PLAY_BLOCK_S = 0.1          # granularità dell'interruzione
    muto = False                # vedi __init__ (anche per gli Speaker costruiti senza)

    def __init__(self, cfg: Config, uscita=None, base: "Speaker | None" = None):
        """`uscita` None: le casse di questo computer (UscitaLocale). Altrimenti un'uscita
        remota (calliope/satellite/server.py, UscitaRemota): le frasi sintetizzate qui
        partono verso il satellite, che le riproduce e dice quali ha detto per intero.

        `base` (06/10, `gemello`): un'altra voce in uscita con le stesse voci di Piper già
        caricate e le stesse frasi pronte, per la corsia di un altro satellite."""
        self.cfg = cfg
        self.remota = uscita
        self.turno = 0                       # cresce a ogni start_turn (uscita remota)
        self._prima_voce: dict[int, float] = {}   # turno → quando si è sentita (locale)
        # Muta per un turno (04/10, calliope/rispondi.py): una frase scritta da uno schermo
        # senza audio in un'altra stanza ha la risposta solo scritta, mai detta qui
        self.muto = False
        if base is not None:
            self.voice = base._voices.get(cfg.piper_voice) or base.voice
            self.pronuncia = base.pronuncia
            self._current_voice_path = cfg.piper_voice
            self._voices = base._voices
            self._voices_lock = base._voices_lock
            self._fillers = base._fillers
            if getattr(base, "_filler_phrases", None):
                self._filler_phrases = base._filler_phrases
        else:
            from piper import PiperVoice
            self.voice = PiperVoice.load(cfg.piper_voice)   # usata solo dal thread di sintesi
            # Inglesismi detti all'inglese («file» → «fàil»), solo nel testo per Piper
            self.pronuncia = Pronuncia(getattr(cfg, "tts_pronuncia_extra", None),
                                       attiva=getattr(cfg, "tts_pronuncia", True))
            self._current_voice_path = cfg.piper_voice
            self._voices = {cfg.piper_voice: self.voice}    # voci già caricate, per percorso
            self._voices_lock = threading.Lock()
            self._fillers: dict[tuple[str, str], bytes] = {}   # (voce, frase) → audio pronto
        self.text_q: queue.Queue = queue.Queue()
        self.audio_q: queue.Queue = queue.Queue()
        self.done = threading.Event()
        self._interrupted = threading.Event()
        self.played: list[str] = []          # frasi pronunciate per intero in questo turno
        self._now_text = ""                  # frase in riproduzione
        self._name_until = 0.0               # fino a quando la sua voce può contenere il nome
        self._rate = self.voice.config.sample_rate    # frequenza della voce in uscita
        self.out = None
        # Chiamata (senza argomenti, dal thread della riproduzione) quando una frase comincia:
        # lo stato «parla» sugli schermi (main.py). Non deve bloccare
        self.on_parla = None
        if uscita is None:
            # Dopo l'avvio la usa solo il thread di riproduzione
            self.out = UscitaLocale(cfg, self._rate, on_stato=self._stato_uscita)
        self._avvia_thread()

    # ── robustezza (03/10) ──
    # Prima un errore di Piper su una frase, o le cuffie sparite a metà, uccidevano il thread:
    # `wait()` restava ferma per sempre e Calliope viva ma muta (systemd non la riavvia).
    # Ora un errore salta la frase (nel log), la fine del turno arriva sempre, e `wait()` ha
    # un tempo massimo: senza progressi per WAIT_STALLO_S i thread si rifanno da capo
    # (generazione nuova, code nuove) e si prosegue.
    WAIT_STALLO_S = 20.0
    _gen = 0
    _progresso = 0.0
    _attesa_extra = 0.0
    frasi_saltate = 0
    blocchi = 0                     # volte che wait() è scaduta

    def _avvia_thread(self):
        """Thread di sintesi e riproduzione per la generazione corrente, con le loro code:
        un thread vecchio rimasto bloccato (PortAudio, Piper) non tocca più quelle nuove."""
        gen, tq, aq = self._gen, self.text_q, self.audio_q
        self._progresso = time.monotonic()
        threading.Thread(target=self._synth_worker, args=(gen, tq, aq), daemon=True,
                         name=f"tts-sintesi-{gen}").start()
        target = self._play_worker if self.remota is None else self._send_worker
        threading.Thread(target=target, args=(gen, aq), daemon=True,
                         name=f"tts-uscita-{gen}").start()

    def _stato_uscita(self, guasta: bool, motivo: str):
        try:
            from . import capacita
            if guasta:
                capacita.segnala("audio", "guasta", f"uscita audio guasta ({motivo})",
                                 "Controlla le cuffie o le casse: riprovo ad aprire l'uscita "
                                 "da sola.")
            else:
                capacita.segnala("audio", "attiva", "uscita audio di nuovo disponibile")
        except Exception:  # noqa: BLE001
            pass

    def _salta(self, text, e: Exception):
        self.frasi_saltate += 1
        print(f"\n   [TTS] Frase saltata ({type(e).__name__}: {e}): {str(text)[:80]!r}",
              flush=True)

    @property
    def stream(self):
        """Il flusso di PortAudio dell'uscita locale (None con un'uscita remota)."""
        return self.out.stream if self.out is not None else None

    def _synth(self, text: str) -> bytes:
        return self._pcm(self.voice, text)

    def _pcm(self, voice, text: str) -> bytes:
        """PCM int16 di una frase. La pronuncia degli inglesismi (calliope/pronuncia.py)
        cambia solo il testo dato a Piper: `played`, la storia e gli schermi restano uguali.
        Più satelliti insieme (06/10): i fonemi uno alla volta in tutto il processo (espeak-ng,
        che Piper usa per i fonemi, ha uno stato globale), la voce (onnxruntime) in parallelo."""
        pron = getattr(self, "pronuncia", None)
        if hasattr(voice, "synthesize_stream_raw"):               # piper-tts < 1.3
            with _SINTESI:
                if pron is not None:
                    text = pron.applica(text, fonemi=False)
                return b"".join(voice.synthesize_stream_raw(text))
        _fonemi_protetti(voice)
        if pron is not None:
            text = pron.applica(text, fonemi=supporta_fonemi(voice))
        return b"".join(ch.audio_int16_bytes for ch in voice.synthesize(text))

    def gemello(self, uscita) -> "Speaker":
        """Un'altra voce in uscita (la corsia di un altro satellite, calliope/corsie.py) con le
        voci di Piper e le frasi pronte di questa: niente da ricaricare."""
        g = Speaker(self.cfg, uscita=uscita, base=self)
        g.on_parla = self.on_parla
        return g

    def _synth_worker(self, gen=None, text_q=None, audio_q=None):
        text_q = self.text_q if text_q is None else text_q
        audio_q = self.audio_q if audio_q is None else audio_q
        gen = self._gen if gen is None else gen
        while gen == self._gen:
            item = text_q.get()
            self._progresso = time.monotonic()
            try:
                if isinstance(item, _VoiceChange):
                    self.voice = item.voice
                    audio_q.put(item)
                elif item is _END_TURN:
                    audio_q.put(item)
                elif isinstance(item, _Filler):
                    if not self._interrupted.is_set():
                        audio_q.put(("", self._synth(item.text)))   # "": non va in played
                elif not self._interrupted.is_set():      # interrotta: non si sintetizza più
                    audio_q.put((item, self._synth(item)))
            except Exception as e:  # noqa: BLE001 — Piper/espeak su un testo strano
                self._salta(item.text if isinstance(item, _Filler) else item, e)

    def _play_worker(self, gen=None, audio_q=None):
        audio_q = self.audio_q if audio_q is None else audio_q
        gen = self._gen if gen is None else gen
        keepalive = self.cfg.tts_keepalive
        while gen == self._gen:
            try:
                item = audio_q.get(timeout=0.02 if keepalive else 1.0)
            except queue.Empty:
                # Niente da dire: silenzio a blocchi di 20 ms, così le cuffie Bluetooth
                # non vanno in risparmio e non tagliano l'attacco del turno dopo. Con
                # l'uscita guasta mantieni() prova a riaprirla (UscitaLocale)
                if keepalive or getattr(self.out, "guasta", False):
                    try:
                        self.out.mantieni()
                    except Exception:  # noqa: BLE001
                        time.sleep(0.02)
                continue
            self._progresso = time.monotonic()
            if item is _END_TURN:
                try:
                    time.sleep(self.out.latency)
                except Exception:  # noqa: BLE001
                    pass
                if gen == self._gen:
                    self.done.set()
                continue
            try:
                if isinstance(item, _VoiceChange):
                    # La nuova voce può avere un'altra frequenza di campionamento (la
                    # riapertura scrive prima il silenzio di coda per le cuffie Bluetooth)
                    self._rate = item.voice.config.sample_rate
                    if self._rate != self.out.rate:
                        self.out.apri(self._rate)
                else:
                    self._play(*item, gen=gen)
            except Exception as e:  # noqa: BLE001 — la riproduzione non deve mai morire
                self._now_text = ""
                self._salta(item[0] if isinstance(item, tuple) else item, e)

    def _send_worker(self, gen=None, audio_q=None):
        """Uscita remota (satellite): ogni frase parte appena sintetizzata, con il suo testo
        e la sua frequenza; la fine del turno aspetta che il satellite l'abbia riprodotta e
        riceve le frasi dette per intero (servono a `played` dopo un'interruzione)."""
        audio_q = self.audio_q if audio_q is None else audio_q
        gen = self._gen if gen is None else gen
        while gen == self._gen:
            item = audio_q.get()
            self._progresso = time.monotonic()
            if item is _END_TURN:
                try:
                    # fine_turno aspetta al più l'audio mandato + 10 s (UscitaRemota)
                    self._attesa_extra = float(getattr(self.remota, "_in_coda_s", 0.0) or 0.0)
                    dette = self.remota.fine_turno()
                    if dette:
                        self.played.extend(dette)
                except Exception as e:  # noqa: BLE001
                    print(f"\n   [TTS] Fine turno del satellite non riuscita: "
                          f"{type(e).__name__}: {e}", flush=True)
                self._attesa_extra = 0.0
                if gen == self._gen:
                    self.done.set()
                continue
            try:
                if isinstance(item, _VoiceChange):
                    self._rate = item.voice.config.sample_rate
                elif not self._interrupted.is_set():
                    text, audio = item
                    self._parla()
                    self.remota.invia(self.turno, text, audio, self._rate)
            except Exception as e:  # noqa: BLE001
                self._salta(item[0] if isinstance(item, tuple) else item, e)

    def prima_voce(self) -> float | None:
        """Il monotonic in cui la prima frase di questo turno ha cominciato a sentirsi (casse
        locali: primo blocco scritto più il ritardo dell'uscita; satellite: quando lui ha
        cominciato a suonarla). None se non si sa (satellite vecchio, niente detto)."""
        if self.remota is not None:
            f = getattr(self.remota, "prima_voce", None)
            return f(self.turno) if f is not None else None
        return self.__dict__.get("_prima_voce", {}).get(self.turno)

    def _play(self, text: str, audio: bytes, gen=None):
        """Riproduce una frase a blocchi, fermandosi se arriva un'interruzione. Con l'uscita
        guasta la frase si scarta (lo dice il log) e non va in `played`."""
        if self._interrupted.is_set():
            return
        mentions_name = dice_nome(self.cfg, text)
        self._now_text = text
        self._parla()
        out = self.out
        step = int(out.rate * self.PLAY_BLOCK_S) * 2       # byte (int16)
        intera = True
        for i in range(0, len(audio), step):
            if self._interrupted.is_set() or (gen is not None and gen != self._gen):
                intera = False          # interrotta, o thread superato (wait scaduta)
                break
            if out.scrivi(audio[i:i + step]) is False:
                intera = False
                print(f"\n   [TTS] Frase non detta (uscita audio guasta): {text[:80]!r}",
                      flush=True)
                break
            self._progresso = time.monotonic()
            pv = self.__dict__.setdefault("_prima_voce", {})
            if i == 0 and self.turno not in pv:
                if len(pv) > 50:
                    pv.pop(min(pv), None)
                pv[self.turno] = self._progresso + float(getattr(out, "latency", 0.0) or 0.0)
        if intera and text:
            self.played.append(text)
        self._now_text = ""
        if mentions_name:
            # Il buffer (Bluetooth compreso) e il rilevatore arrivano dopo: margine
            self._name_until = time.monotonic() + self.out.latency + 0.8

    def _parla(self):
        cb = self.on_parla
        if cb is not None:
            try:
                cb()
            except Exception:  # noqa: BLE001 — uno schermo non deve mai fermare la voce
                pass

    def prepare(self, phrases):
        """Sintetizza in secondo piano le frasi d'attesa dei tool (ToolSpec.announce) con
        la voce attuale, così `say_cached` le fa partire subito, senza aspettare Piper."""
        self._filler_phrases = list(dict.fromkeys(phrases))
        path = self._current_voice_path

        def work():
            voice = self._load(path)
            for text in self._filler_phrases:
                key = (path, text)
                if key not in self._fillers:
                    self._fillers[key] = self._pcm(voice, text)
        threading.Thread(target=work, daemon=True).start()

    def say_cached(self, text: str):
        """Dice una frase d'attesa: subito se è già pronta per la voce attuale, altrimenti
        la sintetizza (~0,2 s) e intanto prepara le altre per questa voce. Non finisce in
        `played` (quindi nemmeno nella storia dopo un'interruzione)."""
        if self.muto:
            return
        audio = self._fillers.get((self._current_voice_path, text))
        if audio is not None:
            self.audio_q.put(("", audio))
        else:
            self.text_q.put(_Filler(text))
            if getattr(self, "_filler_phrases", None):
                self.prepare(self._filler_phrases)

    def chime(self):
        """Due note brevi prima di un annuncio (timer, promemoria): chi è nella stanza
        capisce che non è una risposta ma un avviso."""
        if self.muto:
            return
        rate = self.out.rate if self.out is not None else self._rate
        self.audio_q.put(("", segnale(rate)))

    def suono_ascolto(self, suoni, tipo: str):
        """Il segnale d'inizio o di fine ascolto (calliope/suoni.py) dalle casse locali.
        Con un satellite lo suona lui, appena sente la wake word: qui niente."""
        if self.muto or self.remota is not None or suoni is None:
            return
        pcm = suoni.pcm(tipo, self.out.rate if self.out is not None else self._rate)
        if pcm:
            self.audio_q.put(("", pcm))

    def suono(self, suoni, tipo: str):
        """Il segnale d'inizio o di fine ascolto deciso dal server (06/10, il nome da solo:
        calliope/ciclo.py): dalle casse locali o, con un satellite, mandato come una frase
        senza testo (come `chime`), così lo suona anche un satellite vecchio."""
        if self.muto or suoni is None:
            return
        pcm = suoni.pcm(tipo, self.out.rate if self.out is not None else self._rate)
        if pcm:
            self.audio_q.put(("", pcm))

    def sintetizza(self, text: str) -> tuple[bytes, int]:
        """Una frase sintetizzata subito con la voce attuale, fuori dalle code: (PCM int16,
        frequenza). Serve al saluto che il satellite dice quando si collega. Da chiamare
        prima di usare le code (all'avvio): la voce non va usata da due thread insieme."""
        voice = self._load(self._current_voice_path)
        return self._pcm(voice, text), voice.config.sample_rate

    def saying_name(self) -> bool:
        """True se la voce di Calliope in uscita può contenere il suo nome: la wake word
        va ignorata, altrimenti in cassa si interromperebbe da sola («sono Calliope»).
        Con il satellite lo sa lui, che riproduce (calliope/satellite/client.py)."""
        if self.remota is not None:
            return False
        return dice_nome(self.cfg, self._now_text) or time.monotonic() < self._name_until

    def start_turn(self):
        """Inizio di una risposta: azzera le frasi pronunciate e l'interruzione."""
        self.played = []
        self.turno += 1          # il satellite scarta solo le frasi del turno interrotto
        self._interrupted.clear()

    def interrupt(self):
        """Barge-in: smette di parlare al prossimo blocco e scarta le frasi in coda. Con il
        satellite si è già fermato lui (la wake word gira lì): qui si avvisa e basta."""
        self._interrupted.set()
        if self.remota is not None:
            self.remota.ferma(self.turno)

    @property
    def interrupted(self) -> bool:
        return self._interrupted.is_set()

    def say(self, text: str):
        if self.muto:
            return
        self.text_q.put(text)

    def wait(self, stallo_s: float | None = None) -> bool:
        """Blocca finché tutto ciò che è in coda è stato pronunciato. Mai per sempre: se per
        `stallo_s` (WAIT_STALLO_S) i thread non fanno nessun progresso (un blocco di audio
        scritto, una frase sintetizzata), la voce è bloccata (PortAudio o Piper fermi in una
        chiamata): si scartano le code, si rifanno i thread e si prosegue. False in quel caso.
        Con il satellite si aspetta anche l'audio già mandato, che lui sta riproducendo."""
        stallo = self.WAIT_STALLO_S if stallo_s is None else stallo_s
        self.text_q.put(_END_TURN)
        self._progresso = time.monotonic()
        while not self.done.wait(0.25):
            fermo = time.monotonic() - self._progresso
            if fermo > stallo + self._attesa_extra:
                self._riavvia(fermo)
                return False
        self.done.clear()
        return True

    def _riavvia(self, fermo: float):
        """La voce non ha finito il turno: thread nuovi con code nuove. Un thread vecchio,
        se mai si sblocca, vede la generazione cambiata ed esce senza toccare niente."""
        self.blocchi += 1
        print(f"\n   [TTS] La voce è ferma da {fermo:.0f} s: scarto il turno e riavvio la "
              f"sintesi e l'uscita", flush=True)
        self._gen += 1
        self.text_q, self.audio_q = queue.Queue(), queue.Queue()
        self.done.clear()
        self._now_text = ""
        if self.out is not None and isinstance(self.out, UscitaLocale):
            vecchia = self.out
            vecchia.on_stato = None          # i suoi guasti non contano più
            # Il flusso vecchio si chiude in un thread a parte: può essere proprio lui a
            # bloccare (e chiuderlo sblocca la write ferma)
            threading.Thread(target=vecchia.chiudi, daemon=True).start()
            try:
                self.out = UscitaLocale(self.cfg, self._rate, apri_flusso=vecchia._apri,
                                        device=vecchia.device, on_stato=self._stato_uscita)
            except Exception as e:  # noqa: BLE001 — resta la vecchia, guasta: riprova da sola
                print(f"   [TTS] Uscita non riaperta: {type(e).__name__}: {e}", flush=True)
        self._avvia_thread()

    def change_voice(self, voice_path: str) -> bool:
        """Cambia la voce a runtime. Restituisce True se OK.

        Il modello si carica qui, così un errore torna subito al chiamante; il cambio
        vero avviene in coda, dopo le frasi già inviate con la voce precedente.
        """
        try:
            new_voice = self._load(voice_path)
        except Exception as e:
            print(f"   [TTS] Errore cambio voce: {e}")
            return False
        self._current_voice_path = voice_path
        self.text_q.put(_VoiceChange(new_voice))
        print(f"   [TTS] Voce cambiata: {voice_path}")
        return True

    def _load(self, voice_path: str):
        """Carica una voce Piper una volta sola: dopo resta in memoria.

        Caricarla costa ~1,5 s: nel test del 24/09 ogni cambio di voce ritardava di
        altrettanto la risposta (prima frase a 2,05–2,37 s invece di ~0,6).
        """
        from piper import PiperVoice
        with self._voices_lock:
            voice = self._voices.get(voice_path)
        if voice is None:
            voice = PiperVoice.load(voice_path)
            with self._voices_lock:
                voice = self._voices.setdefault(voice_path, voice)
        return voice

    def preload(self, voice_paths):
        """Carica in secondo piano le voci che serviranno (es. le preferite degli utenti)."""
        def work():
            for path in dict.fromkeys(p for p in voice_paths if p):
                try:
                    self._load(path)
                except Exception as e:
                    print(f"   [TTS] Voce non caricata ({path}): {e}", flush=True)
        threading.Thread(target=work, daemon=True).start()
