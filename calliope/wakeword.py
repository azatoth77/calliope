"""
Wake word di Calliope.

- Acustica: il rilevatore «Calliope» (formato openWakeWord, solo numpy + onnxruntime),
  ex wakeword/detector.py. I modelli generici (melspectrogram.onnx, embedding_model.onnx)
  stanno nella stessa cartella del classificatore configurato in Config.wake_model.
- Testuale: find_wake_word cerca il nome nella trascrizione (ripiego, conferma del
  risveglio, estrazione della richiesta), is_short_exit riconosce le uscite storpiate.

Estratto da calliope.py e wakeword/detector.py il 26/09/2026 (roadmap 2). Gli script di
addestramento in wakeword/ importano ancora `detector`, che ora rimanda qui.
"""
from __future__ import annotations

import difflib
import os
import re
import unicodedata
from collections import deque

import numpy as np

from .config import Config

# ─────────────────────────── RILEVATORE ACUSTICO ───────────────────────────
# Rilevatore della wake word «Calliope» — solo numpy + onnxruntime.
#
# Stessa catena di openWakeWord (formato compatibile), senza dipendere dal pacchetto:
#
#     audio 16 kHz → melspectrogram.onnx → embedding_model.onnx → calliope.onnx → punteggio 0–1
#
# - `melspectrogram.onnx` ed `embedding_model.onnx` sono i due modelli generici e congelati
#   di openWakeWord v0.5.1 (licenza Apache 2.0, scaricati da scarica_modelli.py).
# - `calliope.onnx` è il classificatore addestrato qui (train.py): riceve le ultime 16
#   embedding (1,28 s di audio) e restituisce la probabilità che sia appena stato detto
#   il nome.
#
# Il rilevatore lavora a blocchi di 1280 campioni (80 ms). Nessuna dipendenza nativa oltre
# a onnxruntime, che ha wheel anche per Windows su ARM.
#
# Nel package i modelli non stanno in una cartella scritta nel codice: melspectrogram.onnx
# ed embedding_model.onnx si cercano accanto al classificatore indicato in
# Config.wake_model (oggi wakeword/modelli/). onnxruntime si importa solo quando serve,
# così se manca Calliope ripiega sulla wake word testuale invece di non partire.

CHUNK = 1280          # campioni per blocco (80 ms a 16 kHz)
MEL_WINDOW = 76       # frame mel per ogni embedding (~0,775 s)
MEL_STEP = 8          # 8 frame mel = 80 ms tra due embedding
N_EMB = 16            # embedding in ingresso al classificatore (1,28 s)
MEL_CONTEXT = 480     # campioni di contesto per calcolare i frame mel in streaming


def _session(path: str, threads: int = 1):
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = threads
    opts.inter_op_num_threads = 1
    return ort.InferenceSession(path, sess_options=opts, providers=["CPUExecutionProvider"])


class FeatureExtractor:
    """Mel + embedding di openWakeWord, per clip intere (addestramento/valutazione)."""

    def __init__(self, models_dir: str, threads: int = 1):
        """`models_dir`: la cartella con melspectrogram.onnx ed embedding_model.onnx."""
        self.mel = _session(os.path.join(models_dir, "melspectrogram.onnx"), threads)
        self.emb = _session(os.path.join(models_dir, "embedding_model.onnx"), threads)

    @staticmethod
    def to_int16_scale(audio: np.ndarray) -> np.ndarray:
        """I modelli si aspettano campioni in scala int16 (±32768) in float32."""
        a = np.asarray(audio)
        if a.dtype == np.int16:
            return a.astype(np.float32)
        return (a.astype(np.float32) * 32767.0)

    def melspec(self, audio: np.ndarray) -> np.ndarray:
        """(N campioni) → (frame, 32). Un frame ogni 10 ms."""
        x = self.to_int16_scale(audio)[None, :]
        m = self.mel.run(None, {"input": x})[0][0, 0]
        return m / 10.0 + 2.0          # stessa trasformazione di openWakeWord

    def embed_mel(self, mel: np.ndarray, batch: int = 512) -> np.ndarray:
        """(frame, 32) → (T, 96): un'embedding ogni 8 frame mel, finestra di 76."""
        starts = range(0, mel.shape[0] - MEL_WINDOW + 1, MEL_STEP)
        wins = np.stack([mel[s:s + MEL_WINDOW] for s in starts]) if len(starts) else \
            np.zeros((0, MEL_WINDOW, 32), np.float32)
        out = []
        for i in range(0, len(wins), batch):
            w = wins[i:i + batch, :, :, None].astype(np.float32)
            out.append(self.emb.run(None, {"input_1": w})[0][:, 0, 0, :])
        return np.concatenate(out) if out else np.zeros((0, 96), np.float32)

    def embeddings(self, audio: np.ndarray) -> np.ndarray:
        return self.embed_mel(self.melspec(audio))


class WakeWordDetector:
    """
    Rilevatore in streaming. `process(chunk)` accetta blocchi di qualunque lunghezza
    (float32 in [-1, 1] o int16) e restituisce il punteggio più alto calcolato sui
    blocchi da 80 ms completati (None se non ne è finito nessuno).
    """

    def __init__(self, model_path: str, threads: int = 1, extra=()):
        # I due modelli generici stanno nella stessa cartella del classificatore
        self.fx = FeatureExtractor(os.path.dirname(os.path.abspath(model_path)), threads)
        self.clf = _session(model_path, threads)
        self._in = self.clf.get_inputs()[0].name
        # Altri classificatori sulle stesse feature (05/10, Config.wake_models: «Computer» e
        # «Calliope» insieme): il punteggio è il più alto. Costano poco (il grosso è
        # l'embedding, calcolato una volta)
        self._altri = []
        for p in extra or ():
            c = _session(p, threads)
            self._altri.append((c, c.get_inputs()[0].name))
        self.modelli = [os.path.basename(str(model_path))] + [
            os.path.basename(str(p)) for p in extra or ()]
        self.reset()

    def reset(self):
        # Buffer iniziali pieni di "silenzio" come fa openWakeWord: il primo punteggio
        # utile arriva subito, senza aspettare 2 secondi di riscaldamento.
        self._raw = np.zeros(0, np.float32)            # campioni non ancora elaborati
        self._tail = np.zeros(MEL_CONTEXT, np.float32)  # contesto per il mel
        self._mel = deque([np.ones(32, np.float32)] * MEL_WINDOW, maxlen=MEL_WINDOW)
        self._emb = deque(maxlen=N_EMB)
        zero_emb = self.fx.embed_mel(np.ones((MEL_WINDOW, 32), np.float32))[0]
        for _ in range(N_EMB):
            self._emb.append(zero_emb)
        # Riscaldamento con ~2 s di quasi-silenzio: senza, il passaggio dai buffer
        # iniziali all'audio vero poteva far scattare il classificatore (visto in prova)
        noise = np.random.default_rng(0).standard_normal(CHUNK * 25).astype(np.float32) * 3e-4
        for i in range(25):
            self._step(noise[i * CHUNK:(i + 1) * CHUNK])

    def _step(self, block: np.ndarray) -> float:
        x = np.concatenate([self._tail, block])
        self._tail = x[-MEL_CONTEXT:]
        for f in self.fx.melspec(x):                 # 8 frame nuovi
            self._mel.append(f)
        e = self.fx.embed_mel(np.stack(self._mel))[-1]
        self._emb.append(e)
        feats = np.stack(self._emb)[None].astype(np.float32)
        s = float(self.clf.run(None, {self._in: feats})[0].reshape(-1)[0])
        for clf, nome in self._altri:
            s = max(s, float(clf.run(None, {nome: feats})[0].reshape(-1)[0]))
        return s

    def process(self, chunk: np.ndarray) -> float | None:
        c = np.asarray(chunk)
        c = c.astype(np.float32) / 32767.0 if c.dtype == np.int16 else c.astype(np.float32)
        self._raw = np.concatenate([self._raw, c])
        best = None
        while len(self._raw) >= CHUNK:
            block, self._raw = self._raw[:CHUNK], self._raw[CHUNK:]
            s = self._step(block)
            best = s if best is None else max(best, s)
        return best


# ─────────────────────────── PARTE TESTUALE ───────────────────────────
# Regole sul testo: solo forme chiuse riconosciute per intero (criterio del 01/10,
# docs/ricerche/2026-10-01-regole-deterministiche.md). Una parola dentro una frase non
# basta mai: «chiudi le tapparelle» e «spegni la luce» sono comandi per il modello.

_NAME_MARK = "nome"      # il nome di Calliope, ovunque nella frase, diventa questa parola


def _names(name) -> list[str]:
    """Le parole che svegliano: un nome solo («Calliope») o un elenco (Config.wake_names,
    04/10: «Computer» e «Calliope»)."""
    if isinstance(name, str):
        return [name] if name.strip() else []
    return [n for n in (name or ()) if isinstance(n, str) and n.strip()]


def _plain_words(text: str, name="Calliope") -> list[str]:
    """Parole minuscole, senza accenti né punteggiatura; il nome (anche storpiato o
    attaccato alla parola dopo, «Calliopeesci») diventa `_NAME_MARK`. `name` può essere
    un elenco di parole (wake word diversa dal nome, 04/10): vale ognuna."""
    # Accenti tolti: «Eschì» (01/10) contro «esci» stava a 0,67, sotto soglia
    plain = unicodedata.normalize("NFD", (text or "").lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    lows = [n.lower() for n in _names(name) if " " not in n.strip()]
    out = []
    for w in re.findall(r"\w+", plain):
        for low in lows:
            if w.startswith(low) and len(w) >= len(low) + 2:
                out += [_NAME_MARK, w[len(low):]]
                break
            if (len(w) >= len(low) - 2
                    and difflib.SequenceMatcher(None, w, low).ratio() >= 0.78):
                out.append(_NAME_MARK)
                break
        else:
            out.append(w)
    return out


# Uscita. Dal 01/10 «esci» addormenta (torna ad aspettare il nome) e solo «spegniti»
# chiude il programma: un falso diventa reversibile. Prima EXIT_WORDS cercava «chiudi»
# ovunque, e «Calliope, speni taverna» (01/10) o «chiudi le tapparelle» spegnevano
# Calliope; is_short_exit prendeva per «esci» anche «spegnilo», «senti», «ci riesci?»,
# «alza audio», «Chiore sono» (21/09, era «che ore sono»).
_EXIT_LEAD = {"allora", "ok", "okay", "va", "bene", "ora", "adesso", "dai", "grazie", "mille",
              "per", "favore", "ciao", "ecco", "beh", "quindi", "e", "si", "senti", "ascolta",
              "ehi", "pure", "tante", "ok", "sì",
              # «Certo, spegniti.» (01/10): Whisper sente spesso «Calliope» come «Certo»
              "certo"}
_EXIT_TRAIL = {"pure", "grazie", "mille", "per", "favore", "ciao", "adesso", "ora", "allora",
               "subito", "dai", "tante", "a", "presto", "domani", "dopo"}
_SLEEP = re.compile(
    # «ischi»: storpiatura vera di «esci» (01/10), a 0,67 di somiglianza, sotto soglia
    r"esci|ischi|uscire|arrivederci|addio|addio pesci|buonanotte|buona notte"
    r"|(?:puoi |potresti )?(?:andare|uscire|andare a dormire|tornare a dormire)"
    r"|(?:vai|torna|tornare|andare) a (?:dormire|riposare|nanna)")
# «speniti», «spenniti»: storpiature di «spegniti» (e2e del 06/10, voce di Piper di Andrea:
# «Calliope spenniti.» 2 volte su 6 giri sulla DGX; con faster-whisper 4 su 8 sintesi). Solo
# la frase intera, come «spegniti»; non sono parole italiane
_SHUTDOWN = re.compile(
    rf"(?:puoi |potresti )?(?:spegniti|spenn?iti|spegnerti|chiuditi|chiuderti"
    rf"|(?:spegni|chiudi|spegnere|chiudere) {_NAME_MARK}"
    rf"|(?:spegni|chiudi|termina|spegnere|chiudere|terminare) (?:il |l )?programma"
    rf"(?: di {_NAME_MARK})?"
    rf"|esci dal programma|(?:spegniti|spegnerti) del tutto)")
# Storpiature di «esci» detto da solo (24/09–01/10): «è sci», «Eshi», «Eschì», «pesci».
# Parole vere vicine che non sono un'uscita
_NOT_ESCI = {"esco", "esce", "esca", "escono", "riesci", "pesce", "sci", "pesca", "pesche",
             "disco", "fischi", "fresco", "tesci", "bisci", "lisci"}


def exit_intent(text: str, name="Calliope", spegni_nomi=None) -> str | None:
    """La frase intera è un'uscita? "dormi" (esci, arrivederci, addio, vai a dormire),
    "spegni" (spegniti, spegni Calliope, chiudi il programma), oppure None.

    Riconosce solo la frase intera, a parte il nome (in qualunque posizione) e i
    riempitivi in testa e in fondo («allora», «ok», «grazie», «pure»…). «Spegni la luce»,
    «chiudi Excel», «quando esci dal lavoro ricordami…» vanno al modello.

    `spegni_nomi` (04/10, Config.exit_names): i nomi che valgono in «spegni <nome>». Con una
    wake word comune («Computer») «spegni computer» è il PC, non Calliope: lì vale solo il
    nome dell'assistente. None = gli stessi di `name`.
    """
    words = _plain_words(text, name)
    core = _exit_core(words)
    if _SHUTDOWN.fullmatch(" ".join(core)):
        if spegni_nomi is None or _NAME_MARK not in core:
            return "spegni"
        if _SHUTDOWN.fullmatch(" ".join(_exit_core(_plain_words(text, spegni_nomi)))):
            return "spegni"
        return None
    if _is_sleep(core, words):
        return "dormi"
    # Addormentarsi è reversibile: basta anche la prima frase, se il resto è un'altra
    # («Calliope esci un attimo, facciamo una prova dopo», 26/09). Spegnersi no.
    clauses = [_plain_words(c, name) for c in re.split(r"[,.;:!?]", text or "")]
    clauses = [c for c in clauses if any(w != _NAME_MARK for w in c)]
    if len(clauses) > 1 and _is_sleep(_exit_core(clauses[0]), clauses[0]):
        return "dormi"
    return None


def _exit_core(words: list[str]) -> list[str]:
    """Le parole senza riempitivi in testa e in fondo; il nome resta solo dopo
    «spegni»/«chiudi» («spegni Calliope»)."""
    core = list(words)
    while core and (core[0] in _EXIT_LEAD or core[0] == _NAME_MARK):
        core.pop(0)
    while core:
        if core[-2:] in (["un", "attimo"], ["per", "ora"], ["per", "adesso"], ["un", "po"]):
            del core[-2:]
        elif core[-1] in _EXIT_TRAIL or (core[-1] == _NAME_MARK and (
                len(core) < 2 or core[-2] not in ("spegni", "chiudi", "spegnere", "chiudere",
                                                  "di"))):
            core.pop()
        else:
            break
    return core


def _is_sleep(core: list[str], words: list[str]) -> bool:
    if _SLEEP.fullmatch(" ".join(w for w in core if w != _NAME_MARK)):
        return True
    # Storpiature di «esci»: una o due parole (il nome escluso, riempitivi compresi: «È
    # sci» sono «e» + «sci»), o una sola dopo i riempitivi («Cambio per pesci», 21/09, con
    # il nome sentito in «Cambio»), che unite somigliano a «esci»
    rest = [w for w in words if w != _NAME_MARK]
    plain_core = [w for w in core if w != _NAME_MARK]
    for cand in (rest if 1 <= len(rest) <= 2 else None,
                 plain_core if len(plain_core) == 1 else None):
        if not cand:
            continue
        w = "".join(cand)
        if w not in _NOT_ESCI and len(w) <= 6 and \
                difflib.SequenceMatcher(None, w, "esci").ratio() >= 0.75:
            return True
    return False


def uscita_intera(text: str, name="Calliope") -> str | None:
    """Come exit_intent, ma solo sulla frase **intera** (senza il ripiego sulla prima clausola
    di «dormi»): "dormi", "spegni" o None. Per la corsia veloce delle risposte a una proposta
    (calliope/risposte.py, 10/10): «Esci un attimo, facciamo una prova dopo» non è una forma
    chiusa."""
    words = _plain_words(text, name)
    core = _exit_core(words)
    if not core:
        return None
    if _SHUTDOWN.fullmatch(" ".join(core)):
        return "spegni"
    return "dormi" if _is_sleep(core, words) else None


def exit_request(text: str, name="Calliope", spegni_nomi=None) -> str | None:
    """exit_intent sulla frase intera o, se c'è il nome, sulla richiesta che lo
    accompagna: «Puoi mischiare con il resto. Grazie. Puoi uscire Calliope.» (26/09)."""
    found = exit_intent(text, name, spegni_nomi)
    if found is None:
        request = find_wake_word(text, name, 0.5)
        if request:
            found = exit_intent(request, name, spegni_nomi)
    return found


# «Spegniti» detto da un satellite (02/10): il processo è un servizio sulla DGX, che a voce
# non si riaccende (systemd non riavvia un'uscita normale). Calliope si addormenta e dice
# come spegnerla davvero.
SPEGNI_SATELLITE_MSG = ("Vado a dormire. Il server resta acceso: per spegnerlo usa "
                        "calliope ferma.")


def exit_action(how: str | None, satellite: bool = False) -> str | None:
    """L'uscita da eseguire per una richiesta di exit_request: "dormi", "spegni", None, oppure
    "spegni_satellite" quando l'audio arriva da un satellite (audio_modo: satellite) e la
    frase chiede di spegnersi: allora ci si addormenta come con «esci», e il server resta
    acceso. Con l'audio locale nulla cambia."""
    if how == "spegni" and satellite:
        return "spegni_satellite"
    return how


# Conversazione nuova (05/10, calliope/compressione.py): «ricominciamo», «nuova
# conversazione», «ricominciamo da capo». Solo la frase intera, a parte il nome e i riempitivi
# (principio 10: forma chiusa e breve, effetto reversibile: la conversazione di prima resta
# nell'archivio e si ritrova con conversazione_cerca). «Ricominciamo il timer», «nuova
# conversazione con Bianca?», «ricomincia la lista da capo» vanno al modello.
_NUOVA = re.compile(
    r"(?:possiamo |puoi |vorrei |voglio )?(?:"
    r"(?:ricominciamo|ricominciare|ricomincia|riparti|ripartiamo|ripartire)"
    r"(?: da capo| daccapo| da zero| dall inizio| tutto)?"
    r"|(?:(?:apri|cominciamo|iniziamo|facciamo|inizia|comincia|apriamo|una|un altra) )?"
    r"(?:una |un )?nuova conversazione"
    r"|(?:azzera|cancella|pulisci) (?:la )?conversazione"
    r"|cambiamo (?:discorso|argomento) del tutto"
    r"|(?:facciamo |si )?tabula rasa)")


def nuova_conversazione(text: str, name="Calliope") -> bool:
    """La frase intera chiede una conversazione nuova?"""
    core = _exit_core(_plain_words(text, name))
    return bool(core) and bool(_NUOVA.fullmatch(" ".join(w for w in core if w != _NAME_MARK)))


def is_short_exit(text: str, name="Calliope") -> bool:
    """Compatibilità: True se la frase è un'uscita qualunque (vedi exit_request)."""
    return exit_request(text, name) is not None


# Stop: «basta», «grazie», «va bene così» quando non c'è niente da fermare, o dopo
# un'interruzione. Tutte le parole della frase devono stare nel lessico di chiusura (il
# nome escluso): con la sola prima parola «Ok, aprilo», «Ferma la musica», «Grazie, e
# domani che tempo fa?» finivano nel nulla (rapporto del 01/10).
_CLOSING = {"ok", "okay", "va", "bene", "grazie", "mille", "tante", "basta", "cosi", "stop",
            "niente", "nulla", "lascia", "stare", "perfetto", "zitta", "zitto", "silenzio",
            "fermati", "ferma", "taci", "smettila", "a", "posto", "apposto", "per", "favore",
            "d", "accordo", "fa", "lo", "stesso", "fine", "benissimo", "ottimo", "dai",
            # cortesia (05/10): «ti ringrazio», «gentilissima», «ok, capito». Non «sei» né
            # «molto»: da sole sono risposte («Sei.» a «di quanti minuti?»)
            "ti", "ringrazio", "gentile", "gentilissima", "capito"}

# Le due forme della chiusura (05/10, segnalazione di Dario: «ok, grazie» e «perfetto»
# restavano senza risposta). Un ordine di silenzio basta che compaia una sua parola
# («ok, basta», «grazie, lascia stare»): resta muta. Senza, una parola di ringraziamento
# fa «grazie» («perfetto, grazie»); altrimenti è una conferma («ok», «va bene così»).
_SILENCE = {"basta", "stop", "niente", "nulla", "lascia", "stare", "zitta", "zitto",
            "silenzio", "fermati", "ferma", "taci", "smettila", "fine", "stesso"}
_THANKS = {"grazie", "ringrazio", "gentile", "gentilissima"}


def is_stop(text: str, name="Calliope") -> bool:
    """La frase intera è una chiusura («Grazie mille», «Calliope, stop», «Va bene così»)?"""
    words = [w for w in _plain_words(text, name) if w != _NAME_MARK]
    return bool(words) and all(w in _CLOSING for w in words)


def closing_kind(text: str, name="Calliope") -> str | None:
    """Che chiusura è la frase intera: "silenzio" («basta», «stop», «lascia stare»),
    "grazie" («grazie mille», «ok, grazie») o "conferma" («perfetto», «va bene così»);
    None se non è una chiusura (vedi is_stop)."""
    words = [w for w in _plain_words(text, name) if w != _NAME_MARK]
    if not words or not all(w in _CLOSING for w in words):
        return None
    if any(w in _SILENCE for w in words):
        return "silenzio"
    return "grazie" if any(w in _THANKS for w in words) else "conferma"


# Cortesia dopo il nome: «Apri il documento, Calliope, grazie.» → vale la frase prima
_COURTESY = {"grazie", "mille", "tante", "per", "favore", "dai", "ti", "prego", "pure",
             "gentilmente", "cortesemente", "su"}

# Il nome detto dopo «Vuoi dirmi il tuo nome?» (primo utente): «Mi chiamo Dario» diventava
# «Mi Chiamo Dario» (rapporto del 01/10). Si tolgono solo le formule di presentazione e la
# cortesia; il resto è il nome, come detto.
_NAME_INTRO = re.compile(r"^\W*(?:(?:ok|okay|allora|sì|si|certo|va bene|ciao)\W+)*"
                         r"(?:mi chiamo|il mio nome è|il mio nome e'|chiamami|sono|io sono)\s+",
                         re.I)


def said_name(text: str, name="Calliope") -> str:
    """Il nome da una risposta come «Mi chiamo Dario, grazie» → «Dario»."""
    t = text or ""
    for n in _names(name):
        t = re.sub(rf"\b{re.escape(n)}\b", "", t, flags=re.I)
    t = _NAME_INTRO.sub("", t.strip(" ,.!?;:"))
    t = re.sub(r"(?:[\s,.!?;:]+(?:grazie|per favore|ciao))+[\s,.!?;:]*$", "", t, flags=re.I)
    return t.strip(" ,.!?;:").title()


def load_wake_detector(cfg: Config):
    """Il rilevatore della wake word acustica, oppure None (modalità testo).

    Ripiego automatico sulla wake word testuale se il modello o onnxruntime mancano:
    Calliope funziona comunque, solo con Whisper sempre acceso.
    """
    from . import capacita
    check = capacita.controlla_una(cfg, "wake")
    if not cfg.wake_word_enabled or cfg.wake_mode != "modello":
        capacita.REGISTRO.da_dict(check)
        return None
    try:
        modelli = list(getattr(cfg, "wake_models", None) or [cfg.wake_model])
        detector = WakeWordDetector(modelli[0], extra=modelli[1:])
        if check["stato"] == "attiva":
            capacita.REGISTRO.da_dict(check)
        else:
            capacita.segnala("wake", "attiva", "", "", {
                "modello": cfg.wake_model, "soglia": cfg.wake_threshold,
                "blocchi": cfg.wake_consecutive})
        return detector
    except Exception as e:
        # Ripiego sulla wake word testuale: Calliope funziona, con Whisper sempre acceso
        if check["stato"] == "attiva":
            check = {**check, "stato": "guasta", "motivo": f"modello non caricato ({e}): uso "
                     f"il nome nel testo", "prossimo_passo": "Controlla il file in "
                     f"{cfg.wake_model}, oppure riaddestralo nella cartella wakeword."}
        capacita.REGISTRO.da_dict(check)
        return None


# Parole che possono precedere la wake word in testa alla frase («Ehi Computer», «Ok
# computer, …», «Allora, Computer…») con wake_posizione: inizio
_WAKE_LEAD = {"ehi", "ehy", "hey", "ei", "ok", "okay", "allora", "senti", "scusa", "ciao",
              "dai", "e", "si", "sì", "ora", "adesso", "buongiorno", "buonasera"}


def find_wake_word(text: str, name, threshold: float,
                   info: dict | None = None, start_only: bool = False) -> str | None:
    """
    Cerca il nome nella frase, tollerando piccoli errori di trascrizione
    ("Caliope", "Calliop"...). Restituisce ciò che segue il nome
    ("" se c'era solo il nome), oppure None se il nome non c'è.
    Funziona anche con nomi di più parole ("Hey Calliope") e con più parole che svegliano
    (`name` elenco, Config.wake_names, 04/10): vale quella che compare prima.
    `info`, se c'è, riceve {"cortesia": True} quando dopo il nome c'era solo cortesia e
    vale la frase prima (per il registro dei turni).

    `start_only` (wake_posizione: inizio, per una parola comune come «computer»): il nome
    vale solo in testa alla frase (dopo «ehi», «ok», «allora»…) o subito dopo una virgola o
    un punto, come quando si chiama qualcuno. «Il computer è lento» non sveglia; «Computer,
    che ore sono?» e «Sì, computer, spegni la luce» sì. Se il nome c'era ma nel posto
    sbagliato `info` riceve {"fuori_posizione": True}: il risveglio acustico si scarta.
    """
    best, fuori = None, False
    for n in _names(name):
        sub: dict = {}
        hit = _find_one(text, n, threshold, sub, start_only)
        if hit is None:
            fuori = fuori or bool(sub.get("fuori_posizione"))
        elif best is None or hit[0] < best[0]:
            best = (hit[0], hit[1], sub)
    if info is not None:
        if best is not None:
            info.update({k: v for k, v in best[2].items() if k != "fuori_posizione"})
        elif fuori:
            info["fuori_posizione"] = True
    return best[1] if best is not None else None


def _vocative(words: list[str], clean: list[str], i: int) -> bool:
    """La parola in posizione `i` è detta come un richiamo: in testa (solo saluti e
    riempitivi prima) o subito dopo una virgola, un punto o un punto esclamativo."""
    if all(c in _WAKE_LEAD or not c for c in clean[:i]):
        return True
    return i > 0 and words[i - 1].rstrip()[-1:] in (",", ".", "!", "?", ";", ":")


def _find_one(text: str, name: str, threshold: float, info: dict | None,
              start_only: bool) -> tuple[int, str] | None:
    """(posizione, richiesta) per un nome solo, oppure None (vedi find_wake_word)."""
    words = (text or "").split()
    clean = [re.sub(r"[^\wàèéìòù]", "", w.lower()) for w in words]
    target = name.lower().split()
    n = len(target)
    target_text = " ".join(target)
    # Nome attaccato alla parola dopo: il 26/09 «Calliope, esci» → «Calliopeici»
    if n == 1:
        for i, w in enumerate(clean):
            if w.startswith(target_text) and len(w) >= len(target_text) + 2:
                if start_only and not _vocative(words, clean, i):
                    if info is not None:
                        info["fuori_posizione"] = True
                    continue
                rest = w[len(target_text):]
                return i, " ".join([rest] + words[i + 1:]).strip(" ,.!?;:")
    for i in range(len(words) - n + 1):
        candidate = " ".join(clean[i:i + n])
        # Parole molto più corte del nome («callo», «calle») non sono il nome storpiato
        if len(candidate) < len(target_text) - 2:
            continue
        if candidate.strip() and difflib.SequenceMatcher(
                None, candidate, " ".join(target)).ratio() >= threshold:
            if start_only and not _vocative(words, clean, i):
                # «il computer è lento»: la parola c'è ma non chiama nessuno
                if info is not None:
                    info["fuori_posizione"] = True
                continue
            after = " ".join(words[i + n:]).strip(" ,.!?;:")
            before_all = " ".join(words[:i]).strip(" ,.!?;:")
            # Nome in mezzo e solo cortesia dopo: «Apri il documento, Calliope, grazie.»
            # (rapporto del 01/10: arrivava solo «grazie», preso per uno stop). Vale la frase
            # prima del nome; «Calliope, grazie» da solo resta «grazie».
            if after and before_all and all(
                    w in _COURTESY for w in _plain_words(after, name)):
                after = ""
                if info is not None:
                    info["cortesia"] = True
            if after:
                return i, after
            # Nome in fondo: «Puoi uscire, Calliope» (26/09: veniva preso per un saluto).
            # Vale la frase che precede il nome, l'ultima se ce n'è più d'una.
            before = re.split(r"(?<=[.!?])\s+", " ".join(words[:i]).strip())[-1]
            return i, before.strip(" ,.!?;:")
    return None
