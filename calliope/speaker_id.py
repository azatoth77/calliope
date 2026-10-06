"""
Speaker ID — riconoscimento di chi parla con impronte vocali (voiceprint).

Dal 24/09/2026 l'impronta è un embedding neurale, CAM++ di 3D-Speaker in ONNX: fbank in
numpy + onnxruntime, niente torch (docs/ricerche/2026-09-24-riconoscimento-parlante.md).
L'MFCC di prima accettava come Dario il 33 % delle frasi di italiani sconosciuti; CAM++
ha un EER del 2 % e rifiuta Dario nel 4 % dei casi con 5 frasi di arruolamento.

Serve per preferenze, memoria e livelli di permesso; non autorizza da solo azioni
sensibili (una voce registrata o clonata passerebbe).
Include la stima del genere dalla frequenza fondamentale (pitch).
"""

import json
import os
import re
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


# ──────────────────────────── STIMA GENERE ────────────────────────────

def estimate_gender(audio: np.ndarray, sample_rate: int = 16000) -> str | None:
    """Stima il genere da un segmento audio basandosi sulla frequenza fondamentale.

    Restituisce 'm', 'f' o None (incerto).
    Maschile: 85–180 Hz, Femminile: 165–255 Hz.
    """
    if len(audio) < sample_rate * 0.3:  # meno di 0.3 s → troppo breve
        return None
    try:
        import torch
        import torchaudio
        waveform = torch.from_numpy(audio).unsqueeze(0)
        # Calcola il pitch con torchaudio (metodo autocorrelazione)
        pitch, _, _ = torchaudio.functional.detect_pitch_frequency(
            waveform, sample_rate, frame_length=512, hop_length=256)
        pitch = pitch.numpy()
        valid = pitch[pitch > 0]  # scarta frame senza pitch rilevato
        if len(valid) < 5:
            return None
        mean_pitch = float(valid.mean())
        # Soglie conservative con zona grigia
        if mean_pitch >= 170:
            return "f"
        elif mean_pitch <= 150:
            return "m"
        return None  # zona grigia 150–170 Hz → chiedere all'utente
    except Exception:
        return None


# ──────────────────────────── IMPRONTA VOCALE ────────────────────────────

def kaldi_fbank(audio: np.ndarray, num_mel: int = 80, sr: int = 16000) -> np.ndarray:
    """Fbank «alla Kaldi» (dither 0, finestra povey, preenfasi 0,97, snip edges) in numpy.

    Verificata contro torchaudio.compliance.kaldi.fbank (prove/prova_speaker.py fbank).
    """
    flen, fshift, nfft = int(0.025 * sr), int(0.010 * sr), 512
    n = 1 + (len(audio) - flen) // fshift
    idx = np.arange(flen)[None, :] + fshift * np.arange(n)[:, None]
    fr = audio[idx].astype(np.float64)
    fr -= fr.mean(axis=1, keepdims=True)
    fr = np.concatenate([fr[:, :1] - 0.97 * fr[:, :1], fr[:, 1:] - 0.97 * fr[:, :-1]], axis=1)
    win = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(flen) / (flen - 1))) ** 0.85
    spec = np.abs(np.fft.rfft(fr * win, nfft)) ** 2
    mel = lambda f: 1127.0 * np.log(1 + f / 700.0)
    centers = np.linspace(mel(20.0), mel(sr / 2), num_mel + 2)
    fft_mel = mel(np.arange(nfft // 2 + 1) * sr / nfft)
    fb = np.zeros((num_mel, nfft // 2 + 1))
    for m in range(num_mel):
        l, c, r = centers[m], centers[m + 1], centers[m + 2]
        fb[m] = np.maximum(0, np.minimum((fft_mel - l) / (c - l), (r - fft_mel) / (r - c)))
    return np.log(np.maximum(spec @ fb.T, np.finfo(np.float32).eps)).astype(np.float32)


def normalize(v: np.ndarray) -> np.ndarray:
    return (v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-10)).astype(np.float32)


class SpeakerEmbedder:
    """Embedding del parlante con onnxruntime (CAM++ di 3D-Speaker di default)."""

    def __init__(self, model_path: str, threads: int = 2):
        import onnxruntime as ort
        self.model_name = Path(model_path).stem
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        self.session = ort.InferenceSession(model_path, so, providers=["CPUExecutionProvider"])
        meta = self.session.get_modelmeta().custom_metadata_map
        # Alcuni modelli vogliono i campioni in scala int16
        self.scale = 32768.0 if meta.get("normalize_samples", "1") == "0" else 1.0
        self.input = self.session.get_inputs()[0].name
        self._lock = threading.Lock()

    def embed(self, audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
        """Embedding normalizzato di una frase (float32 16 kHz mono)."""
        if len(audio) < sample_rate // 2:                 # sotto 0,5 s: riempie di zeri
            audio = np.pad(audio, (0, sample_rate // 2 - len(audio)))
        f = kaldi_fbank(audio * self.scale, sr=sample_rate)
        f -= f.mean(axis=0, keepdims=True)                # media per frase (CMN)
        with self._lock:
            out = self.session.run(None, {self.input: f[None]})[0][0]
        return normalize(out)


# ──────────────────────────── PROFILO UTENTE ────────────────────────────

# Versione dei profili in speakers.json (05/10): 2 = nascita, tutori, fascia (minori)
PROFILO_VERSIONE = 2

@dataclass
class UserProfile:
    name: str
    gender: str | None = None                # "m" o "f" (dedotto dalla voce)
    voiceprint: np.ndarray | None = None     # media normalizzata degli embedding
    # Impronta dell'arruolamento: gli aggiornamenti non possono allontanarsene troppo,
    # così il profilo non scivola piano piano verso la voce di un altro
    initial_voiceprint: np.ndarray | None = None
    model: str | None = None                 # modello che ha calcolato l'impronta
    preferred_voice: str | None = None        # voce TTS preferita
    # Tono delle risposte per questa persona (04/10, config.TONI): None = quello della casa
    preferred_tone: str | None = None
    # Chi amministra (Primo/Prima, il primo utente). È un attributo del profilo e non
    # del nome: così resta anche dopo «chiamami Dario».
    admin: bool = False
    # Minori (05/10, calliope/minori.py): data di nascita (AAAA-MM-GG; la fascia d'età si
    # ricalcola da sola), tutori (id dei profili che lo amministrano) e, senza data, la fascia
    # scritta a mano: il vecchio «giovane» (booleano fino al 04/10) diventa «ragazzi» finché chi
    # amministra non dice la data (`python arruola.py <nome> --nascita AAAA-MM-GG`)
    nascita: str | None = None
    tutori: list[str] = field(default_factory=list)
    fascia: str | None = None
    # Quando è stata fatta l'impronta (AAAA-MM-GG) e la media mobile dei punteggi con cui la
    # voce viene riconosciuta: per i minori il promemoria di rifarla (la voce cambia in fretta)
    impronta_data: str | None = None
    riconoscimento: float | None = None
    samples: list[np.ndarray] = field(default_factory=list)  # embedding dell'arruolamento
    # Identificativo stabile: la memoria (memory.py) è legata a questo, non al nome,
    # così una rinomina non perde i ricordi
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def needs_enroll(self) -> bool:
        return self.voiceprint is None

    @property
    def young(self) -> bool:
        """Minorenne con Vikidia per prima (biblioteca: spiegazioni semplici). Fino al 04/10 era
        il booleano «giovane»; ora viene dalla fascia e dal preset (calliope/minori.py)."""
        from . import minori
        p = minori.preset(self)
        return p is not None and p.get("fonti") == "vikidia"

    def to_dict(self) -> dict:
        vec = lambda v: v.tolist() if v is not None else None
        return {
            "id": self.id,
            "name": self.name,
            "gender": self.gender,
            "voiceprint": vec(self.voiceprint),
            "initial_voiceprint": vec(self.initial_voiceprint),
            "model": self.model,
            "preferred_voice": self.preferred_voice,
            "tono": self.preferred_tone,
            "admin": self.admin,
            # Versione del profilo (05/10): 2 = con nascita, tutori e fascia. Un profilo di
            # una versione più nuova rende il file di sola lettura (SpeakerRegistry._load)
            "versione": PROFILO_VERSIONE,
            "nascita": self.nascita,
            "tutori": list(self.tutori),
            "fascia": self.fascia,
            "impronta_data": self.impronta_data,
            "riconoscimento": (round(self.riconoscimento, 3)
                               if isinstance(self.riconoscimento, float) else None),
            # Il vecchio campo, per una versione di Calliope di prima (calliope torna): un
            # minore con Vikidia resta almeno «giovane»
            "giovane": bool(self.fascia or self.nascita) and self.young,
        }

    @classmethod
    def from_dict(cls, d: dict, model: str) -> "UserProfile":
        vec = lambda k: np.array(d[k], dtype=np.float32) if d.get(k) else None
        prof = cls(name=d["name"], gender=d.get("gender"), model=d.get("model"),
                   voiceprint=vec("voiceprint"), initial_voiceprint=vec("initial_voiceprint"),
                   preferred_voice=d.get("preferred_voice"),
                   preferred_tone=d.get("tono") if isinstance(d.get("tono"), str) else None,
                   admin=bool(d.get("admin", False)),
                   nascita=d.get("nascita") if isinstance(d.get("nascita"), str) else None,
                   tutori=[str(t) for t in (d.get("tutori") or []) if t],
                   fascia=d.get("fascia") if isinstance(d.get("fascia"), str) else None,
                   impronta_data=d.get("impronta_data") if isinstance(d.get("impronta_data"),
                                                                      str) else None,
                   riconoscimento=(float(d["riconoscimento"]) if isinstance(
                       d.get("riconoscimento"), (int, float)) else None))
        # Migrazione del 05/10: «giovane» senza data di nascita = fascia «ragazzi»
        if d.get("giovane") and not prof.nascita and not prof.fascia:
            prof.fascia = "ragazzi"
        if d.get("id"):
            prof.id = d["id"]
        if prof.model != model:
            # Impronta di un altro modello (es. il vecchio MFCC): non confrontabile.
            # Nome, admin, genere e voce restano; la voce va riarruolata.
            prof.voiceprint = prof.initial_voiceprint = None
            prof.model = model
        return prof


# ──────────────────────────── REGISTRO UTENTI ────────────────────────────

class SpeakerRegistry:
    """Carica/salva i profili utente da/per un file JSON."""

    PATH = Path("speakers.json")
    SALVA_OGNI_S = 60.0          # impronte aggiornate da adapt: al più un salvataggio al minuto

    def __init__(self, cfg=None):
        if cfg is None:
            from .config import Config
            cfg = Config()
        self.cfg = cfg
        self.embedder = SpeakerEmbedder(cfg.speaker_model, cfg.speaker_threads)
        self.users: dict[str, UserProfile] = {}   # nome → profilo
        self._lock = threading.Lock()
        # speakers.json c'è ma non si legge, e nemmeno la sua copia (03/10): il motivo. Allora
        # niente primo avvio né salvataggi: tutti ospiti finché qualcuno non lo ripara
        self.illeggibile: str | None = None
        self._salvato = 0.0                       # monotonic dell'ultimo salvataggio
        self._da_salvare = False                  # impronte aggiornate non ancora scritte
        self._load()
        import atexit
        atexit.register(self.flush)

    def _profili(self, data) -> dict[str, "UserProfile"]:
        if not isinstance(data, list):
            raise ValueError("non è un elenco di profili")
        return {d["name"]: UserProfile.from_dict(d, self.embedder.model_name) for d in data}

    def _load(self):
        """Carica i profili. Un file rovinato (corrente saltata a metà scrittura, disco
        pieno) prima valeva come «nessun profilo»: al riavvio era il primo avvio, e chi
        parlava per primo diventava amministratore (analisi di robustezza, 03/10). Ora si
        prova la copia `speakers.json.bak`; se non va nemmeno quella Calliope parte con i
        profili vuoti **in sola lettura**: tutti ospiti, nessuno promosso, il file non si
        tocca, e il registro delle capacità lo dice («chi_parla» guasta, con il passo)."""
        p, bak = Path(self.PATH), Path(str(self.PATH) + ".bak")
        dati, errore = None, None
        for f, quale in ((p, "file"), (bak, "bak")):
            if not f.exists():
                continue
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                dati = (self._profili(raw), quale, raw)
                break
            except Exception as e:  # noqa: BLE001
                errore = errore or e
        if dati is None:
            self.users = {}
            if errore is not None:
                self.illeggibile = (f"{p.name} non si legge ({type(errore).__name__}: "
                                    f"{errore}) e non c'è una copia buona")
                print(f"[SPEAKER] {self.illeggibile}: parto con tutti ospiti e non lo "
                      f"sovrascrivo", flush=True)
                try:
                    from . import capacita
                    capacita.segnala("chi_parla", "guasta", f"{p.name} non si legge",
                                     capacita.PASSO_SPEAKERS_ILLEGGIBILE)
                except Exception:  # noqa: BLE001
                    pass
            return
        self.users, quale, data = dati
        nuovi = [d.get("name") for d in data if isinstance(d.get("versione"), int)
                 and d["versione"] > PROFILO_VERSIONE]
        if nuovi:
            # Profili scritti da una versione più nuova di Calliope (calliope torna senza i
            # dati): si leggono, ma il file non si riscrive (perderebbe i campi nuovi)
            self.illeggibile = (f"{p.name} ha profili di una versione più nuova di Calliope "
                                f"({', '.join(map(str, nuovi))}): lo uso in sola lettura")
            print(f"[SPEAKER] {self.illeggibile}", flush=True)
            return
        if quale == "bak":
            # Il file rovinato si mette da parte (serve a capire cosa è successo) e si rifà
            # dalla copia
            da_parte = p.with_name(f"{p.name}.rovinato-{time.strftime('%Y%m%d-%H%M%S')}")
            try:
                if p.exists():
                    os.replace(p, da_parte)
            except OSError:
                pass
            print(f"[SPEAKER] {p.name} non si leggeva ({errore}): uso la copia {bak.name}"
                  f" ({len(self.users)} profili); il file rovinato è in {da_parte.name}",
                  flush=True)
            self.save()
        elif any(not d.get("id") for d in data):
            self.save()                      # profili di prima: si fissa l'id

    def save(self):
        """Scrittura atomica (temporaneo, fsync, os.replace) con la copia della versione
        di prima in `.bak`: un'interruzione a metà lascia sempre un file intero. Con il file
        illeggibile non si scrive niente (lo si sovrascriverebbe)."""
        from .persistenza import scrivi_json
        if self.illeggibile:
            print(f"   [SPEAKER] Profili non salvati: {self.illeggibile}", flush=True)
            return
        with self._lock:
            data = [u.to_dict() for u in self.users.values()]
            scrivi_json(self.PATH, data, copia=True)
            self._salvato = time.monotonic()
            self._da_salvare = False

    def flush(self):
        """Scrive le impronte aggiornate e non ancora salvate (all'uscita)."""
        if self._da_salvare:
            try:
                self.save()
            except Exception as e:  # noqa: BLE001
                print(f"   [SPEAKER] Impronte non salvate all'uscita: {e}", flush=True)

    def get(self, name: str) -> UserProfile | None:
        return self.users.get(name)

    def by_id(self, pid: str | None) -> UserProfile | None:
        """Il profilo con questo id (UserProfile.id): gli schermi personali sono legati
        all'id, non al nome (03/10, testo scritto sullo schermo)."""
        if not pid:
            return None
        return next((u for u in self.users.values() if getattr(u, "id", None) == pid), None)

    def rename(self, old_name: str, new_name: str) -> UserProfile | None:
        """Rinomina un utente. Restituisce il profilo rinominato o None."""
        prof = self.users.pop(old_name, None)
        if prof is None:
            return None
        prof.name = new_name
        self.users[new_name] = prof
        self.save()
        print(f"   [SPEAKER] Rinominato «{old_name}» → «{new_name}»")
        return prof

    def known_speakers(self) -> list[str]:
        return list(self.users.keys())

    def find(self, name: str) -> str | None:
        """Il profilo registrato che corrisponde a `name`, o None.

        Vale anche con maiuscole, accenti e spazi diversi («dario», «Dàrio») e con il
        nome solo o con il cognome («Dario Rossi» per «Dario»): registrare di nuovo un nome
        già presente sostituirebbe l'impronta di quella persona (analisi di sicurezza del
        03/10, S1: un familiare faceva registrare «Dario» con la voce di un altro e
        prendeva il suo profilo, amministrazione compresa)."""
        key = name_key(name)
        if not key:
            return None
        first = key.split()[0]
        for n in self.users:
            k = name_key(n)
            if k == key:
                return n
        for n in self.users:
            k = name_key(n)
            if k and (len(k.split()) == 1 or len(key.split()) == 1) and k.split()[0] == first:
                return n
        return None

    def embed(self, audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
        return self.embedder.embed(audio, sample_rate)

    def best_match(self, audio: np.ndarray | None = None, sample_rate: int = 16000,
                   emb: np.ndarray | None = None) -> tuple[str | None, float]:
        """Il profilo più somigliante e il suo punteggio, senza soglia.
        Si può passare l'embedding già calcolato (es. in parallelo a Whisper)."""
        if emb is None:
            emb = self.embed(audio, sample_rate)
        best_name, best_sim = None, 0.0
        for name, prof in self.users.items():
            if prof.voiceprint is not None:
                sim = float(np.dot(emb, prof.voiceprint))
                if sim > best_sim:
                    best_name, best_sim = name, sim
        return best_name, best_sim

    def identify(self, audio: np.ndarray, sample_rate: int = 16000,
                 threshold: float | None = None) -> tuple[str | None, float]:
        """Riconosce chi parla: (nome, similarità) oppure (None, similarità migliore)."""
        threshold = self.cfg.speaker_id_threshold if threshold is None else threshold
        best_name, best_sim = self.best_match(audio, sample_rate)
        if best_sim >= threshold:
            return best_name, best_sim
        return None, best_sim

    def set_voiceprint(self, name: str, embeddings: list[np.ndarray],
                       gender: str | None = None, admin: bool | None = None) -> UserProfile:
        """Crea o sostituisce l'impronta di `name` con la media di più frasi."""
        vp = normalize(np.mean(np.stack(embeddings), axis=0))
        prof = self.users.get(name) or UserProfile(name=name)
        prof.voiceprint, prof.initial_voiceprint = vp, vp.copy()
        import datetime as _dt
        prof.impronta_data = _dt.date.today().isoformat()
        prof.riconoscimento = None
        prof.model, prof.samples = self.embedder.model_name, list(embeddings)
        if gender is not None:
            prof.gender = gender
        if admin is not None:
            prof.admin = admin
        self.users[name] = prof
        self.save()
        return prof

    def adapt(self, name: str, emb: np.ndarray, sim: float) -> bool:
        """Aggiorna l'impronta con una frase riconosciuta con sicurezza.

        Il microfono e la voce cambiano da un giorno all'altro: arruolato il 21/09,
        Dario il 24/09 veniva rifiutato nel 18 % dei casi con il profilo fermo e nel
        3,6 % con l'aggiornamento. Solo sopra `speaker_adapt_threshold`, con media
        mobile, e senza allontanarsi dall'impronta dell'arruolamento.
        """
        cfg = self.cfg
        prof = self.users.get(name)
        if prof is None or prof.voiceprint is None or sim < cfg.speaker_adapt_threshold:
            return False
        new = normalize((1 - cfg.speaker_adapt_alpha) * prof.voiceprint
                        + cfg.speaker_adapt_alpha * emb)
        if (prof.initial_voiceprint is not None
                and float(np.dot(new, prof.initial_voiceprint)) < cfg.speaker_adapt_max_drift):
            return False
        prof.voiceprint = new
        # Al più un salvataggio al minuto (03/10): prima si riscriveva il file a ogni frase
        # sicura; il resto lo scrive flush() all'uscita
        self._da_salvare = True
        if time.monotonic() - self._salvato >= self.SALVA_OGNI_S:
            self.save()
        return True


def name_key(name: str) -> str:
    """Un nome confrontabile: minuscole, senza accenti né punteggiatura, spazi singoli."""
    t = unicodedata.normalize("NFKD", name or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", t).split())


# ──────────────────────────── INTEGRAZIONE CON CALLIOPE ────────────────────────────

class SpeakerContext:
    """Tiene traccia dello speaker corrente e gestisce l'arruolamento."""

    # Frasi-guida per l'arruolamento: aperte, così chi parla dice qualche secondo di
    # voce senza doversi inventare cosa dire (il 26/09 un ragazzo registrato senza
    # guida diceva solo «Calliope» e le frasi venivano scartate perché troppo brevi)
    ENROLL_PROMPTS = [
        "Raccontami cosa hai fatto oggi.",
        "Dimmi qual è il tuo piatto preferito e perché ti piace.",
        "Descrivimi la stanza in cui ti trovi adesso.",
        "Raccontami un film, un libro o una canzone che ti è piaciuto.",
        "Dimmi cosa ti piacerebbe fare questo fine settimana.",
        "Raccontami un bel ricordo di una vacanza.",
    ]

    def __init__(self, registry: SpeakerRegistry):
        self.registry = registry
        self.current_speaker: str | None = None
        # True se l'identità del turno è stata confermata solo dalla conversazione
        # (punteggio nella zona grigia): allora il livello si ferma a "familiare"
        self.from_session: bool = False
        # Come è stata decisa l'identità di questo turno (main.py): "voce" (impronta sopra
        # soglia), "breve" (frase troppo corta: vale chi parlava), "conversazione" (zona
        # grigia), "schermo" (testo scritto su uno schermo personale, o frase breve subito
        # dopo: 03/10) o None. Le installazioni vogliono "voce" nella richiesta (tools/stato.py)
        self.identified_by: str | None = None
        self._enrolling: str | None = None     # nome in fase di arruolamento
        self._enroll_admin: bool = False       # il profilo in arruolamento amministra?
        self._enroll_embs: list[np.ndarray] = []
        self._enroll_gender: str | None = None
        # Ri-registrazione di un profilo che ha già un'impronta: le frasi nuove devono
        # somigliare a quella vecchia (chi rifà la propria voce, non un'altra persona)
        self._enroll_ref: np.ndarray | None = None
        self._reenroll: bool = False
        # Scadenza: senza una frase valida entro `speaker_enroll_timeout_s` la
        # registrazione si chiude (prima restava aperta per sempre, e la prima voce che
        # passava, anche la TV, diventava una frase di arruolamento: S10 del 03/10)
        self._enroll_deadline: float = 0.0
        # Conferme (04/10, calliope/conferme.py). `voce_sicura`: chi è stato riconosciuto
        # dalla voce (sopra soglia) in questa conversazione; `conferma_breve`: questa frase è
        # breve, di quella persona che amministra, con l'impronta compatibile
        # (≥ speaker_conferma_breve_soglia), quindi può confermare un'azione proposta;
        # `sfida`: la frase di conferma da ripetere in corso; `sfida_superata`: superata in
        # questa frase (Brain esegue l'azione)
        self.voce_sicura: str | None = None
        self.punteggio: float | None = None
        self.conferma_breve: bool = False
        self.sfida = None
        self.sfida_superata: bool = False

    def aggiorna_conversazione(self, name: str | None, how: str | None, in_session: bool,
                               score: float | None):
        """Dopo il riconoscimento di una frase (main.py): chi è sicuro nella conversazione e
        se questa frase breve può confermare un'azione proposta a chi amministra."""
        if not in_session:
            self.voce_sicura = None          # conversazione nuova (dopo il nome)
        if how == "voce":
            self.voce_sicura = name
        elif how in ("breve", "conversazione", "schermo") and name and name == self.voce_sicura:
            pass
        else:
            self.voce_sicura = None          # un ospite, un'altra persona: si riparte
        prof = self.registry.get(name) if name else None
        soglia = float(getattr(self.registry.cfg, "speaker_conferma_breve_soglia", 0.40))
        self.punteggio = score
        self.conferma_breve = bool(how == "breve" and name and name == self.voce_sicura
                                   and prof is not None and prof.admin and score is not None
                                   and score >= soglia)
        self.sfida_superata = False

    @property
    def is_enrolling(self) -> bool:
        return self._enrolling is not None

    @property
    def enroll_needed(self) -> int:
        return self.registry.cfg.speaker_enroll_phrases

    @property
    def enrolling_name(self) -> str | None:
        return self._enrolling

    @property
    def enroll_remaining(self) -> int:
        return self.enroll_needed - len(self._enroll_embs)

    @property
    def enroll_timeout_s(self) -> float:
        return float(getattr(self.registry.cfg, "speaker_enroll_timeout_s", 120.0))

    @property
    def enroll_expired(self) -> bool:
        """La registrazione in corso è scaduta (nessuna frase valida da troppo)."""
        return self._enrolling is not None and time.monotonic() > self._enroll_deadline

    @property
    def enroll_prompt(self) -> str:
        """La prossima frase-guida da proporre a chi si sta registrando."""
        return self.ENROLL_PROMPTS[len(self._enroll_embs) % len(self.ENROLL_PROMPTS)]

    def start_enroll(self, name: str, admin: bool = False, reenroll: bool = False,
                     meta: dict | None = None):
        """Avvia la modalità arruolamento per 'name' (admin=True per Primo/Prima).

        `reenroll`: si rifà l'impronta di un profilo che c'è già. Il permesso lo decide
        il tool (`registra_utente`); qui le frasi nuove devono somigliare all'impronta
        vecchia, se c'è, e il profilo tiene il suo `admin` com'era."""
        prof = self.registry.get(name)
        self._enrolling = name
        self._enroll_admin = admin
        self._enroll_embs = []
        self._enroll_gender = None
        self._enroll_ref = (prof.voiceprint.copy() if reenroll and prof is not None
                            and prof.voiceprint is not None else None)
        self._reenroll = bool(reenroll and prof is not None)
        # Dati del profilo nuovo da scrivere a registrazione finita (minori: nascita, tutori)
        self._enroll_meta = dict(meta or {})
        self._enroll_deadline = time.monotonic() + self.enroll_timeout_s
        print(f"   [SPEAKER] Arruolamento «{name}»: di' {self.enroll_needed} frasi, "
              f"una alla volta.")

    def enroll_sample(self, audio: np.ndarray, sample_rate: int = 16000,
                      detect_gender: bool = False, voiced_s: float | None = None) -> str:
        """Processa una frase di arruolamento.

        Restituisce "fatto" (profilo salvato), "ancora" (serve un'altra frase),
        "breve" (frase troppo corta, non contata: sotto ~1,5 s l'impronta è poco
        affidabile) o "altra_voce:<nome>" (la voce è già di un altro profilo, per
        esempio il genitore che parla al posto del figlio: non contata).
        """
        if self._enrolling is None:
            return "ancora"
        if self.enroll_expired:
            print(f"   [SPEAKER] Registrazione di «{self._enrolling}» scaduta.")
            self.stop_enroll()
            return "scaduto"
        cfg = self.registry.cfg
        if voiced_s is None:
            voiced_s = len(audio) / sample_rate
        if voiced_s < cfg.speaker_enroll_min_s:
            print(f"   [SPEAKER] Frase troppo breve ({voiced_s:.1f} s), non contata.")
            return "breve"
        emb = self.registry.embed(audio, sample_rate)
        for name, prof in self.registry.users.items():
            if (name != self._enrolling and prof.voiceprint is not None
                    and float(np.dot(emb, prof.voiceprint)) >= cfg.speaker_id_threshold):
                print(f"   [SPEAKER] Questa voce è di «{name}», non di «{self._enrolling}»: "
                      f"frase non contata.")
                return f"altra_voce:{name}"
        if self._enroll_ref is not None:
            sim = float(np.dot(emb, self._enroll_ref))
            if sim < cfg.speaker_id_threshold - cfg.speaker_id_session_margin:
                print(f"   [SPEAKER] La voce non somiglia all'impronta di «{self._enrolling}»"
                      f" ({sim:.2f}): frase non contata.")
                return "non_somiglia"
        self._enroll_embs.append(emb)
        self._enroll_deadline = time.monotonic() + self.enroll_timeout_s
        if detect_gender and self._enroll_gender is None:
            self._enroll_gender = estimate_gender(audio, sample_rate)
        if len(self._enroll_embs) >= self.enroll_needed:
            name = self._enrolling
            existing = self.registry.get(name)
            # L'amministrazione non passa mai con una registrazione: un profilo nuovo non
            # amministra (salvo il primo utente della casa), uno rifatto resta com'era
            if self._enroll_admin:
                admin = True
            elif existing is not None and self._reenroll:
                admin = existing.admin
            else:
                admin = False
            prof = self.registry.set_voiceprint(
                name, self._enroll_embs, gender=self._enroll_gender, admin=admin)
            meta = getattr(self, "_enroll_meta", None) or {}
            if meta:
                for k in ("nascita", "tutori", "fascia"):
                    if k in meta:
                        setattr(prof, k, meta[k])
                if meta.get("nascita"):
                    prof.fascia = None
                self.registry.save()
            print(f"   [SPEAKER] Arruolamento «{name}» completato.")
            self.stop_enroll()
            return "fatto"
        print(f"   [SPEAKER] Ancora {self.enroll_needed - len(self._enroll_embs)} "
              f"frasi per «{self._enrolling}».")
        return "ancora"

    def stop_enroll(self):
        self._enrolling = None
        self._enroll_embs = []
        self._enroll_ref = None
        self._reenroll = False
        self._enroll_meta = {}

    @property
    def current_level(self) -> str:
        """Livello di permesso dello speaker corrente (principio 9 della visione).

        ospite → voce non riconosciuta; familiare → voce riconosciuta;
        amministra → Primo/Prima, il primo utente della casa, anche dopo un cambio di
        nome, ma solo se la voce è stata riconosciuta sopra soglia in questo turno.
        Scritto da uno schermo personale (identified_by "schermo", 03/10): al più familiare;
        per ciò che vuole chi amministra serve la voce (tools/spec.serve_la_voce).
        """
        level = self.profile_level
        if level == "amministra" and self.identified_by == "schermo":
            return "familiare"
        return level

    @property
    def profile_level(self) -> str:
        """Il livello che chi parla avrebbe a voce (senza il tetto dello scritto)."""
        if self.current_speaker is None:
            return "ospite"
        prof = self.registry.get(self.current_speaker)
        if prof and prof.admin and not self.from_session:
            return "amministra"
        return "familiare"
