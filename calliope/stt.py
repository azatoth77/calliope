"""
Trascrizione con faster-whisper (GPU, con ripiego su CPU).
Estratto da calliope.py il 26/09/2026 (roadmap 2: divisione in package).

Dal 02/10/2026 anche con un server di trascrizione (`stt_motore: server`,
`ServerTranscriber`): sulla DGX Spark (Linux aarch64) CTranslate2 di PyPI è solo per CPU, e
Whisper sulla GPU lo serve un altro processo (vLLM, whisper.cpp). Stessa interfaccia
`transcribe(audio) -> str` (principio 2); se il server non risponde, faster-whisper su CPU
(principio 7).
"""
import io
import os
import threading
import time
import wave
import re
import sys
from pathlib import Path

import numpy as np

from .config import Config, HALLUCINATIONS


# ─────────────────────────────── TRASCRIZIONE ───────────────────────────────
def _add_cuda_dlls():
    """Su Windows rende visibili le DLL di cuBLAS/cuDNN installate via pip."""
    if sys.platform != "win32":
        return
    try:
        import nvidia
    except ImportError:
        return
    for base in map(Path, nvidia.__path__):
        for sub in ("cublas", "cudnn"):
            d = base / sub / "bin"
            if d.is_dir():
                os.add_dll_directory(str(d))
                os.environ["PATH"] = str(d) + os.pathsep + os.environ["PATH"]


def modello_whisper(cfg: Config) -> str:
    """Il modello da dare a faster-whisper: la cartella installata dal catalogo
    (models/whisper/<modello>, verificata con il checksum) se c'è, altrimenti il nome, che
    faster-whisper cerca nella cache di Hugging Face o scarica."""
    from .installa.catalogo import whisper_locale
    d = whisper_locale(cfg)
    return str(d) if d is not None else cfg.whisper_model


def prompt_whisper(cfg) -> str:
    """Il prompt iniziale di Whisper: corto, con la parola che sveglia (taratura del 24/09:
    un prompt più lungo viene ricopiato sull'audio incerto)."""
    nomi = getattr(cfg, "wake_names", None) or [cfg.name]
    return f"Conversazione con {nomi[0]}."


def hotwords_whisper(cfg) -> str | None:
    """Le hotwords di faster-whisper: quelle di whisper_hotwords più le parole che svegliano
    (04/10). Con la configurazione di sempre resta «Calliope»."""
    parole = (cfg.whisper_hotwords or "").split()
    for n in getattr(cfg, "wake_names", None) or []:
        if n.lower() not in {p.lower() for p in parole}:
            parole.append(n)
    return " ".join(parole) or None


# Il prompt di Whisper si ricalcola a ogni frase (05/10): con la modalità cambiata a voce la
# parola che sveglia cambia senza riavvio. Un valore assegnato (le prove) resta fisso
_PROMPT = property(
    lambda self: getattr(self, "_prompt_fisso", None) or prompt_whisper(self.cfg),
    lambda self, v: setattr(self, "_prompt_fisso", v))


class Transcriber:
    prompt = _PROMPT
    # La confidenza dell'ultima frase (stt_correzione.Confidenza) per la correzione delle
    # frasi incerte: la dà solo il server (verbose_json); qui None, e non si corregge
    ultima_confidenza = None
    # La famiglia dell'ultima frase scartata come allucinazione (calliope/allucinazioni.py,
    # 09/10), o None: il ciclo la scrive nel registro dei turni (regola allucinazione_whisper)
    ultima_scartata = None

    def __init__(self, cfg: Config, solo_cpu: bool = False):
        from faster_whisper import WhisperModel
        self.cfg = cfg
        modello = modello_whisper(cfg)
        # Suggerisce a Whisper come si scrive il nome, così lo riconosce meglio (dal 04/10
        # la parola che sveglia: «Conversazione con Computer.» in modalità startrek)
        self._prompt_fisso = None      # None = prompt_whisper(cfg) a ogni frase
        _add_cuda_dlls()
        if solo_cpu:                         # ripiego del ServerTranscriber: niente GPU
            self.model = WhisperModel(modello, device="cpu", compute_type="int8")
            self.device, self.error = "cpu", None
            noise = np.random.default_rng(0).normal(0, 0.05, 3 * cfg.sample_rate)
            self._run(noise.astype(np.float32))
            return
        try:
            self.model = WhisperModel(modello, device=cfg.whisper_device,
                                      compute_type=cfg.whisper_compute_type)
            # Verifica + warm-up. Rumore e non silenzio: sul silenzio Whisper non decodifica
            # e la ricerca beam si inizializzava alla prima frase vera (1,17 s invece di 0,2)
            noise = np.random.default_rng(0).normal(0, 0.05, 3 * cfg.sample_rate)
            for _ in range(2):
                self._run(noise.astype(np.float32))
            self.device, self.error = cfg.whisper_device, None
        except Exception as e:
            self.model = WhisperModel(modello, device="cpu", compute_type="int8")
            self.device, self.error = "cpu", str(e)
        # Nel registro delle capacità: il riassunto dell'avvio dice modello e dispositivo
        # (la riga da controllare dopo il primo download, vedi CLAUDE.md)
        from . import capacita
        if self.device == cfg.whisper_device:
            capacita.segnala("stt", "attiva", f"Whisper {cfg.whisper_model} su {self.device}",
                             "", {"modello": cfg.whisper_model, "dispositivo": self.device})
        else:
            capacita.segnala("stt", "attiva", f"Whisper {cfg.whisper_model} su CPU, GPU non "
                             f"utilizzabile ({self.error[:120]})",
                             capacita.passo_gpu(),
                             {"modello": cfg.whisper_model, "dispositivo": "cpu",
                              "errore": self.error})

    def _run(self, audio):
        segments, _ = self.model.transcribe(audio, language=self.cfg.language,
                                            beam_size=self.cfg.whisper_beam_size,
                                            hotwords=hotwords_whisper(self.cfg),
                                            initial_prompt=self.prompt,
                                            condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments).strip()

    def parole(self, audio) -> list[tuple[str, float]]:
        """Le parole della frase con la loro probabilità (08/10, calliope/argomenti_incerti.py),
        con le stesse opzioni della trascrizione più `word_timestamps`: solo quando il modello
        chiama un tool con un argomento che nomina qualcosa, in secondo piano (portatile:
        0,315 → 0,355 s di mediana per frase)."""
        segments, _ = self.model.transcribe(audio, language=self.cfg.language,
                                            beam_size=self.cfg.whisper_beam_size,
                                            hotwords=hotwords_whisper(self.cfg),
                                            initial_prompt=self.prompt,
                                            condition_on_previous_text=False,
                                            word_timestamps=True)
        return [(w.word.strip(), round(float(w.probability), 3))
                for s in segments for w in (s.words or ()) if any(c.isalnum() for c in w.word)]

    # Chiamata (senza argomenti) prima di caricare Whisper su CPU durante l'uso: main.py ci
    # fa dire una frase d'attesa, perché la prima frase sulla CPU costa secondi (03/10)
    on_ripiego = None
    ATTESA = "Un attimo, oggi ci metto un po' di più a capire."

    def _avvisa_ripiego(self):
        cb = self.on_ripiego
        if cb is not None:
            try:
                cb()
            except Exception:  # noqa: BLE001
                pass

    def _ripiega_su_cpu(self, e: Exception) -> bool:
        """Errore durante una trascrizione sulla GPU (VRAM finita con un agente o un
        documento sullo stesso Ollama, driver CUDA): Whisper si ricarica su CPU e la frase
        si rifà lì (principio 7, prima valeva solo all'avvio e l'errore chiudeva Calliope).
        False se si è già sulla CPU: l'errore è un altro."""
        if self.device == "cpu":
            return False
        from faster_whisper import WhisperModel
        from . import capacita
        self.error = f"{type(e).__name__}: {e}"[:200]
        print(f"   [STT] Errore di Whisper su {self.device} ({self.error}): ricarico su CPU",
              flush=True)
        self._avvisa_ripiego()
        self.model = WhisperModel(modello_whisper(self.cfg), device="cpu", compute_type="int8")
        self.device = "cpu"
        capacita.segnala("stt", "attiva", f"Whisper {self.cfg.whisper_model} su CPU dopo un "
                         f"errore della GPU ({self.error[:120]})",
                         "Riavviami per tornare sulla GPU; se si ripete, " + capacita.passo_gpu(),
                         {"modello": self.cfg.whisper_model, "dispositivo": "cpu",
                          "errore": self.error})
        return True

    def transcribe(self, audio: np.ndarray) -> str:
        try:
            text = self._run(audio)
        except Exception as e:  # noqa: BLE001
            if not self._ripiega_su_cpu(e):
                raise
            text = self._run(audio)
        # Confronto senza punteggiatura finale: «Grazie a tutti.» sfuggiva (test del 24/09).
        # Dal 09/10 le frasi tipiche delle allucinazioni di Whisper, per intero
        # (calliope/allucinazioni.py: «e con il nostro corso gratuito www.…» su rumore)
        from .allucinazioni import allucinazione
        famiglia = ("sottotitoli" if text.lower().strip(" .!?…") in HALLUCINATIONS
                    else allucinazione(text, getattr(self.cfg, "wake_names", None)
                                       or [self.cfg.name]))
        self.ultima_scartata = famiglia
        if famiglia is not None or self._is_prompt_echo(text):
            return ""
        return text

    def _is_prompt_echo(self, text: str) -> bool:
        """Whisper ricopia il prompt iniziale sull'audio incerto. Il 01/10, su 0,6 s di
        voce, «Calliope Conversazione con Calliope»: con il nome davanti (hotword) il
        confronto esatto non scattava e Calliope si è svegliata. Si confronta senza il
        nome e senza punteggiatura."""
        def bare(s: str) -> str:
            words = re.findall(r"\w+", s.lower())
            nomi = {n.lower() for n in getattr(self.cfg, "wake_names", [self.cfg.name])}
            return " ".join(w for w in words if w not in nomi)
        return bool(bare(text)) and bare(text) == bare(self.prompt)


def unisci_righe(testo: str) -> str:
    """Il testo di un server senza gli a capo tra i segmenti (05/10 sera). whisper-server con
    `verbose_json` accende i tempi per token e con loro il taglio dei segmenti a 60 caratteri
    (`max_len`), **su un token**, cioè anche a metà parola: la DGX trascriveva «di fis\\nica»,
    «Gra\\nzie», «dall'ind\\neterminazione», e il testo arrivava così al modello, alla wake
    word testuale e al registro (sul banco delle 104: WER 13,4 % contro 12,1 % senza a capo).
    Un segmento che comincia una parola ha lo spazio davanti: l'a capo si toglie e basta. Un
    a capo dopo la punteggiatura e senza spazio (un altro server che va a capo tra le frasi)
    diventa uno spazio."""
    testo = re.sub(r"\n(?=\s)", "", testo)
    testo = re.sub(r"(?<=[.!?;:,])\n", " ", testo)
    return testo.replace("\n", "")


def wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    """L'audio float32 in un WAV PCM 16 bit mono, in memoria (niente file)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


class ServerTranscriber(Transcriber):
    """Whisper servito da un altro processo con l'API compatibile OpenAI:
    `POST {stt_url}/audio/transcriptions` (multipart: file WAV, model, language, prompt,
    temperature 0, response_format json) → `{"text": …}`. Vale per vLLM con
    openai/whisper-large-v3-turbo, per whisper.cpp (`whisper-server --inference-path
    /v1/audio/transcriptions`) e per speaches.

    Beam e hotwords non sono nell'API: li fissa il server (whisper.cpp: `-bs 5`); il prompt
    («Conversazione con Calliope.») passa. Se il server non risponde entro `stt_timeout_s`
    la frase si trascrive con faster-whisper su CPU, caricato la prima volta che serve (o
    all'avvio se il server è già giù): più lento, ma Calliope continua a capire (principio
    7). Il registro delle capacità lo dice."""

    RIPROVA_S = 30.0         # dopo un errore il server si riprova a questa distanza

    def __init__(self, cfg: Config, http=None):
        import httpx
        self.cfg = cfg
        self._prompt_fisso = None      # None = prompt_whisper(cfg) a ogni frase
        if not cfg.stt_url:
            raise ValueError("stt_motore è «server» ma manca stt_url")
        self.url = cfg.stt_url.rstrip("/") + "/audio/transcriptions"
        self.http = http or httpx.Client(timeout=httpx.Timeout(
            cfg.stt_timeout_s, connect=min(2.0, cfg.stt_timeout_s)))
        self.device, self.error = "server", None
        self._cpu: Transcriber | None = None
        self._cpu_lock = threading.Lock()
        self._giu_da = -1e9                  # monotonic dell'ultimo errore del server
        self.ultimo = "server"               # chi ha trascritto l'ultima frase
        try:                                 # verifica + riscaldamento, come la GPU
            noise = np.random.default_rng(0).normal(0, 0.05, cfg.sample_rate)
            self._chiedi(noise.astype(np.float32))
            self._segnala_ok()
        except Exception as e:  # noqa: BLE001
            self._errore(e)
            self._cpu_pronto()               # meglio pagare il caricamento adesso

    def _chiedi(self, audio: np.ndarray) -> str:
        # Con la correzione delle frasi incerte (05/10, stt_correzione.py) serve la
        # probabilità di ogni parola: verbose_json (whisper-server la dà per token; stessi
        # tempi del json, 0,28 s di mediana sulla DGX); anche per dire le parole incerte al
        # modello della voce (stt_incerte_al_modello, 07/10)
        verbose = bool(getattr(self.cfg, "stt_correzione", False)
                       or getattr(self.cfg, "stt_incerte_al_modello", False)
                       or getattr(self.cfg, "stt_incerte_riscrivi", False))
        files = {"file": ("frase.wav", wav_bytes(audio, self.cfg.sample_rate), "audio/wav")}
        data = {"model": self.cfg.stt_modello, "language": self.cfg.language,
                "prompt": self.prompt, "temperature": "0",
                "response_format": "verbose_json" if verbose else "json"}
        self.ultima_confidenza = None
        r = self.http.post(self.url, files=files, data=data)
        r.raise_for_status()
        try:
            v = r.json()
        except ValueError:                   # response_format ignorato: testo semplice
            return unisci_righe(r.text).strip()
        if verbose and v.get("segments") is not None:
            from .stt_correzione import confidenza
            self.ultima_confidenza = confidenza(v)
        return unisci_righe(str(v.get("text") or "")).strip()

    def parole(self, audio) -> list[tuple[str, float]]:
        """Le parole della frase con la probabilità (08/10, calliope/argomenti_incerti.py): la
        stessa frase rimandata con `verbose_json`, senza i tempi per token (la probabilità c'è
        lo stesso; misurato sulla DGX: 0,37 s di mediana contro 0,22 del json). Solo quando il
        modello chiama un tool con un argomento che nomina qualcosa, in parallelo al tool. Con il
        server giù nessuna parola (il ripiego su CPU serve alla voce, non alla misura)."""
        if self.ultimo != "server" or time.monotonic() - self._giu_da < self.RIPROVA_S:
            return []
        from .stt_correzione import parole_whisper
        files = {"file": ("frase.wav", wav_bytes(audio, self.cfg.sample_rate), "audio/wav")}
        data = {"model": self.cfg.stt_modello, "language": self.cfg.language,
                "prompt": self.prompt, "temperature": "0", "response_format": "verbose_json",
                "token_timestamps": "false"}
        r = self.http.post(self.url, files=files, data=data)
        r.raise_for_status()
        return [(w, round(p, 3)) for w, p in parole_whisper(r.json())]

    def _segnala_ok(self):
        from . import capacita
        riserva = capacita.riserva_whisper(self.cfg)
        capacita.segnala("stt", "attiva", f"Whisper sul server ({self.cfg.stt_modello})"
                         + ("" if not riserva else f"; {riserva[0]}"),
                         "" if not riserva else riserva[1],
                         {"modello": self.cfg.stt_modello, "dispositivo": "server",
                          "indirizzo": self.cfg.stt_url})

    def _errore(self, e: Exception):
        from . import capacita
        self._giu_da = time.monotonic()
        self.error = f"{type(e).__name__}: {e}"[:200]
        capacita.segnala("stt", "guasta", "il server di trascrizione non risponde: trascrivo "
                         "su CPU, più lenta",
                         "Controlla il server di trascrizione (calliope motore whisper "
                         "stato) e l'indirizzo stt_url in calliope.locale.yaml.",
                         {"modello": self.cfg.whisper_model, "dispositivo": "cpu",
                          "indirizzo": self.cfg.stt_url, "errore": type(e).__name__})

    def _cpu_pronto(self) -> Transcriber:
        with self._cpu_lock:
            if self._cpu is None:
                print(f"   [STT] server di trascrizione giù: carico Whisper "
                      f"{self.cfg.whisper_model} su CPU", flush=True)
                self._cpu = Transcriber(self.cfg, solo_cpu=True)
            return self._cpu

    def _run(self, audio):
        if time.monotonic() - self._giu_da >= self.RIPROVA_S:
            try:
                text = self._chiedi(audio)
                if self.ultimo != "server" or self.error:
                    self._segnala_ok()
                    self.error = None
                self.ultimo = "server"
                return text
            except Exception as e:  # noqa: BLE001 — rete, timeout, 5xx
                self._errore(e)
        self.ultimo = "cpu"
        self.ultima_confidenza = None
        if self._cpu is None:
            # Il server è caduto durante l'uso: caricare Whisper su CPU costa secondi, e
            # intanto Calliope lo dice (frase d'attesa, una volta sola)
            self._avvisa_ripiego()
        return self._cpu_pronto()._run(audio)

    def _ripiega_su_cpu(self, e: Exception) -> bool:
        return False          # il ripiego del server è già in _run


def make_transcriber(cfg: Config) -> Transcriber:
    """Il trascrittore scelto da `stt_motore`: «locale» (faster-whisper nel processo) o
    «server» (API compatibile OpenAI, con ripiego su CPU)."""
    motore = (getattr(cfg, "stt_motore", "locale") or "locale").lower()
    if motore == "server":
        return ServerTranscriber(cfg)
    if motore != "locale":
        raise ValueError(f"stt_motore sconosciuto: {motore!r} (locale | server)")
    return Transcriber(cfg)
