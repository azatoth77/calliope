"""
Il ciclo della voce di una corsia (06/10/2026, P8 dell'analisi complessiva,
docs/ricerche/2026-10-06-analisi-complessiva.md § 4.3).

Fino al 06/10 il ciclo era `giro`, una chiusura di ~1 100 righe dentro `main.main()`, e
`corsie.clona` la ricopiava per ogni satellite rifacendo le celle delle sue variabili libere:
una variabile di `main` dimenticata nell'elenco restava condivisa tra le corsie senza nessun
errore (così era nato il difetto dello stato della voce sugli schermi, P9). Qui:

- `Servizi`: ciò che le corsie condividono (configurazione, registro delle voci, Whisper,
  agenda, schermi, agenti, guardiano, registro dei turni…), con i pochi valori che cambiano a
  voce (wake word, suoni, barge-in, biblioteca appena scaricata) come attributi espliciti;
- `Ciclo`: una corsia (l'audio di questo computer, o un satellite) con i suoi oggetti
  (ascolto, voce in uscita, chi parla, Brain, ToolContext) e il suo stato (turno in corso,
  finestra di ascolto, interruzione, annunci rinviati, errori recenti).

`main.main()` prepara i servizi e il ciclo della corsia locale; `main.esegui_corsie` crea un
`Ciclo` per ogni satellite che si collega.
"""
import dataclasses
import datetime
import re
import threading
import time
import wave
from pathlib import Path

import numpy as np

from . import contesto, corsie, minori
from . import guardiano as guardia
from . import provenienza, riferire
from . import allegati as allegati_mod
from .agenda import announcement
from .compressione import FRASE_DURA
from .config import Config, DEEPEN_WORDS, SEARCH_PROMISE
from .immagini import FOTO_IN_ATTESA, FOTO_NON_VISTA, Immagine
from .schermi import schede as schede_foto
from .schermi.moduli import annuncio_lavoro, completa as completa_modulo, oscura, oscura_tutto
from .speaker_id import estimate_gender
from .suoni import FINE, INIZIO
from .tools.builtin import biblioteca_contesto
from .tts import split_sentences, clean_for_speech, strip_false_citation
from .wakeword import (SPEGNI_SATELLITE_MSG, closing_kind, exit_action, exit_request,
                       find_wake_word, is_stop, nuova_conversazione, said_name)

# Errori imprevisti nel ciclo (03/10): oltre ERRORI_MAX in ERRORI_FINESTRA_S Calliope esce con
# un errore (sotto systemd riparte da capo) invece di girare a vuoto chiedendo scusa
ERRORI_MAX = 5
ERRORI_FINESTRA_S = 120.0


# ─────────────────────────────── DIAGNOSTICA ───────────────────────────────
def save_debug_audio(cfg: Config, audio: np.ndarray, text: str) -> str:
    """Salva la frase captata e la sua trascrizione, per tarare VAD, microfono e STT.
    Restituisce il nome del file (senza estensione), citato nel registro dei turni."""
    folder = Path(cfg.debug_audio_dir)
    folder.mkdir(parents=True, exist_ok=True)
    stem = time.strftime("%Y%m%d-%H%M%S")
    with wave.open(str(folder / f"{stem}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(cfg.sample_rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    with open(folder / "trascrizioni.tsv", "a", encoding="utf-8") as f:
        f.write(f"{stem}\t{cfg.whisper_model}\t{text}\n")
    return stem


def domanda_guardia(text: str, files, massimo: int = 3000) -> str:
    """La domanda da far giudicare al guardiano (minori e ospiti, calliope/guardiano.py): con
    file allegati in questo turno anche il loro testo estratto (05/10, allegati), tagliato per
    stare nella finestra piccola del guardiano. Il testo resta un dato: serve solo al giudizio."""
    pezzi = [a.testo for a in (files or ()) if getattr(a, "parti", None)]
    if not pezzi:
        return text
    return (text + "\n\n" + "\n\n".join(pezzi))[:max(len(text) + 500, massimo)]


# Minori in pericolo (prova e2e del 06/10): un pezzo di frase detto mentre Calliope rispondeva
# al pezzo di prima si giudica unito a lui entro questi secondi; una protezione interrotta si
# ripete al turno dopo della stessa persona entro questi secondi
UNIONE_PEZZI_S = 30.0
RIPETI_PROTEZIONE_S = 300.0


# ─────────────────────────────── SERVIZI ───────────────────────────────
@dataclasses.dataclass
class Servizi:
    """Ciò che tutte le corsie condividono. Lo prepara `main.main()`; i campi che cambiano
    mentre Calliope è accesa (la modalità cambiata a voce, la biblioteca appena scaricata, il
    primo utente registrato) si leggono da qui a ogni uso."""
    cfg: Config
    registry: object = None              # SpeakerRegistry
    embed_pool: object = None            # ThreadPoolExecutor dell'impronta (CAM++)
    satelliti: object = None             # ServerSatelliti, o None con l'audio locale
    stt: object = None                   # trascrittore (corsie.STTCondiviso con più corsie)
    correttore: object = None            # stt_correzione.Correttore, o None
    casa: object = None
    agenda: object = None
    documenti: object = None
    installazioni: object = None
    schermi: object = None
    instradamento: object = None         # rispondi.Instradamento
    lavori: object = None
    compressore: object = None
    web: object = None
    tools: object = None                 # ToolRegistry
    giochi: object = None
    guardiano: object = None
    foto_attesa: object = None           # immagini.InAttesa (foto e file senza domanda)
    cortesia: object = None
    turns: object = None                 # TurnLog
    attiva_minori: object = None         # () → True se ha registrato i tool dei minori
    # Cambiano a voce (modalità, main.applica_modalita) o da un'installazione
    wake: object = None
    suoni: object = None
    barge_in: bool = False
    barge_voice: bool = False
    biblioteca: object = None
    # Primo avvio: al prossimo «Calliope» si registra il primo utente (Primo/Prima)
    enroll_pending: bool = False
    # monotonic dell'ultimo controllo delle impronte dei minori (uno al giorno)
    controllo_impronte: list = dataclasses.field(default_factory=lambda: [0.0])


# ─────────────────────────────── TURNO ───────────────────────────────
# Una fase che chiude il giro (equivale al vecchio «return» dentro giro)
_FINE = object()


@dataclasses.dataclass(slots=True)
class Turno:
    """Le variabili di un giro, passate da una fase all'altra (slots: un nome sbagliato è un
    errore, non un attributo nuovo)."""
    guided: bool = False                 # registrazione della voce o nome del primo utente
    scritto: dict | None = None          # la frase (o foto, file, modulo) da uno schermo
    audio: object = None
    barged: bool = False                 # la frase arriva da un'interruzione
    in_session: bool = False             # dentro la finestra di ascolto
    t0: float = 0.0                      # perf_counter alla fine dell'ascolto
    t0_mono: float = 0.0
    voiced_s: float = 0.0                # secondi di voce (senza pre-roll e silenzio)
    emb_job: object = None               # impronta in calcolo (Future)
    text: str = ""
    conf_stt: object = None              # stt_correzione.Confidenza della frase, o None
    prev_how: str | None = None          # come era riconosciuto chi parlava prima
    voce_secondo: tuple = (None, None)   # il secondo profilo e il suo punteggio (07/10)
    speaker_name: str | None = None
    prof_turno: object = None            # profilo di chi parla (minori, orari)
    context: str | None = None           # contesto del turno (biblioteca, foto non viste)
    foto: list = dataclasses.field(default_factory=list)
    files: list = dataclasses.field(default_factory=list)
    level: str = "ospite"
    minore_turno: bool = False
    usa_guardia: bool = False
    esito_g: object = None               # guardiano.Esito
    esito_u: object = None               # riferire.Esito
    was_enrolling: bool = False
    watch_stop: object = None            # barge-in: fine dell'ascolto del nome
    watch: dict = dataclasses.field(default_factory=dict)
    watcher: object = None
    first: bool = True
    said: list = dataclasses.field(default_factory=list)
    protezione: str | None = None        # la frase di protezione detta in questo turno


def solo_nome_acustico(text: str, voiced_s: float, cfg) -> bool:
    """Regola `nome_da_solo_acustico` (06/10, principio 10: riguarda l'audio e le
    storpiature del nome, che il modello non vede). Con la wake word acustica scattata sicura
    e il nome assente dal testo, la frase è il nome da solo se il testo è vuoto (Whisper ha
    restituito un'allucinazione o l'eco del prompt, già tolte in stt.py) o se la voce dura
    non più di wake_solo_nome_s: in così poco tempo, dopo il nome, non c'è una domanda."""
    if not re.sub(r"[\W_]+", "", text or ""):
        return True
    return voiced_s <= float(getattr(cfg, "wake_solo_nome_s", 0.0) or 0.0)


# ─────────────────────────────── CICLO ───────────────────────────────
class Ciclo:
    """Il ciclo della voce di una corsia: `giro` ascolta una frase e risponde (o annuncia).
    Gli oggetti della corsia sono attributi espliciti; i servizi condivisi stanno in `s`."""

    def __init__(self, servizi: Servizi, corsia, listener, speaker, speaker_ctx, brain,
                 tool_ctx, annunci, ingresso, sveglia):
        self.s = servizi
        self.corsia = corsia                 # corsie.Corsia
        self.listener = listener
        self.speaker = speaker
        self.speaker_ctx = speaker_ctx
        self.brain = brain
        self.tool_ctx = tool_ctx
        self.annunci = annunci               # code degli annunci (agenda, documenti, lavori…)
        self.ingresso = ingresso             # frasi e moduli scritti dagli schermi
        self.sveglia = sveglia               # threading.Event: un annuncio o uno scritto
        # Stato della corsia
        self.rec = None                      # il turno in corso (registro dei turni)
        self.awake_until = 0.0               # fino a quando accetta domande senza il nome
        self.barge_seed = None               # audio dell'interruzione, da cui riparte l'ascolto
        self.last_question = None            # ultima domanda con risposta («approfondisci»)
        self.pending_real_name = None        # attende il nome vero del primo utente
        self.enroll_reminded: set = set()    # registrazioni a cui si è ricordato il nome
        # Annunci che chiudono con una domanda mentre un'altra aspetta: al giro dopo (rinvia)
        self.annunci_rinviati: list[tuple] = []
        self.errori_ciclo: list[float] = []  # monotonic degli errori imprevisti recenti
        # Minori in pericolo (prova e2e del 06/10): la protezione che sta suonando (niente
        # barge-in con la sola voce), quella interrotta da ripetere (chi, monotonic, frase) e
        # l'ultima frase giudicata dal guardiano (chi, testo, monotonic), da unire al pezzo
        # che la continua mentre Calliope risponde
        self.protezione_in_corso = False
        self.protezione_da_ripetere: tuple | None = None
        self.ultima_frase_guardia: tuple | None = None
        # Lo stato della voce sugli schermi mentre si aspetta una frase (dorme o ascolta)
        self.attesa_voce = ["dorme", None]
        # Il nome da solo con i suoni (06/10): frasi prese finora e il timer del suono di fine
        # ascolto se nessuno parla nella finestra (vedi `_solo_il_nome`)
        self.frasi_prese = 0
        self._fine_attesa: threading.Timer | None = None
        self._collega_voce()

    # ── stato della voce sugli schermi ──
    def stanza_voce(self) -> str | None:
        """La stanza degli schermi che mostrano lo stato della voce di questa corsia (06/10,
        P9): per un satellite la sua, "" se non è collegato (nessuno schermo); None con
        l'audio di questo computer o un satellite solo (il microfono che ascolta, come
        prima). Vale anche dai thread del VAD e della riproduzione, che non sono la corsia."""
        sid = getattr(self.corsia, "satellite_id", None)
        if sid is None or self.s.satelliti is None:
            return None
        coll = self.s.satelliti.per_id(sid)
        return (coll.stanza or "") if coll is not None else ""

    def voce(self, stato, fino=None):
        """Stato della voce sugli schermi (02/10): addormentata, in ascolto (con il tempo che
        resta della finestra di follow-up), sta pensando, sta parlando. Schermi.voce non
        blocca; lo schermo non deve mai fermare la voce."""
        schermi = self.s.schermi
        if schermi is None:
            return
        try:
            stanza = self.stanza_voce()
            if stanza != "":
                # La corsia come sorgente (Q9): con due satelliti nella stessa stanza gli
                # schermi mostrano l'unione dei loro stati, non l'ultimo scritto
                schermi.voce(stato, fino, stanza=stanza,
                             **({"sorgente": self.corsia.chiave} if stanza else {}))
        except Exception:  # noqa: BLE001
            pass

    def _collega_voce(self):
        """Il VAD (inizio e scarto di una frase) e la riproduzione cambiano lo stato della voce
        di questa corsia: callback legati a lei, non alla corsia del thread (P9: prima erano
        quelli della corsia locale, condivisi da tutti i satelliti)."""
        if self.s.schermi is None or self.listener is None:
            return
        if self.speaker is not None:
            self.speaker.on_parla = lambda: self.voce("parla")
        prima_inizio, prima_fine = self.listener.on_speech_start, self.listener.on_speech_end

        def inizio_frase():
            self.voce("ascolta")           # parla a Calliope: niente conto alla rovescia
            if prima_inizio is not None:
                prima_inizio()

        def fine_frase():
            self.voce(*self.attesa_voce)   # frase buttata: si torna come prima
            if prima_fine is not None:
                prima_fine()
        self.listener.on_speech_start, self.listener.on_speech_end = inizio_frase, fine_frase

    # ── aiuti ──

    def known_voice(self, audio) -> bool:
        """Il parlato durante una risposta è di una persona registrata?

        Mai durante la frase di protezione di un minore (o di un ospite) in pericolo (prova
        e2e del 06/10): la seconda metà della sua stessa frase («…e di non dirlo alla mamma»)
        la interrompeva, e 19696 e il consiglio di parlarne con un adulto non arrivavano. Lì
        la ferma solo il nome («Calliope, basta»); se succede, la protezione si ripete per
        intero al turno dopo (`_protezione_dopo`)."""
        cfg, registry = self.s.cfg, self.s.registry
        if getattr(self, "protezione_in_corso", False):
            print(f"\n   [BARGE-IN] parlato di {len(audio) / cfg.sample_rate:.1f} s durante la "
                  f"protezione → continuo", flush=True)
            return False
        name, sim = registry.best_match(emb=registry.embed(audio, cfg.sample_rate))
        ok = sim >= cfg.speaker_id_threshold - cfg.speaker_id_session_margin
        print(f"\n   [BARGE-IN] parlato di {len(audio) / cfg.sample_rate:.1f} s: "
              f"{name or 'sconosciuto'} {sim:.2f}" + ("" if ok else " → continuo"), flush=True)
        return ok

    def in_console(self, testo, risposta: bool = False):
        """Il testo da stampare nel terminale (sulla DGX finisce nel journal di systemd, che
        resta): niente frasi degli ospiti, né risposte con i dati dei tool riservati
        (documenti di casa, rubrica, fatture). Lo stesso criterio del registro dei turni
        (analisi di sicurezza del 03/10, S9)."""
        if self.speaker_ctx.current_level == "ospite":
            return "(una frase di un ospite)" if not risposta else "…"
        if risposta and getattr(self.brain, "last_private", False):
            return "…"
        return testo

    def rule(self, name: str):
        """Una regola sul testo ha deciso qualcosa in questo turno: resta nel registro dei
        turni (campo `regole`), così la revisione può misurare quanto scatta e quando."""
        if self.rec is not None:
            self.rec.setdefault("regole", []).append(name)

    def rinvia(self, coda, item) -> bool:
        """Annunci che chiudono con una domanda («… La apro?», «il lavoro ha una domanda:
        …?») mentre un'altra domanda aspetta ancora la risposta: si dicono al giro dopo (03/10,
        analisi di robustezza). Prima vinceva l'ultima: il «sì» andava alla domanda
        dell'agente e la proposta del documento si perdeva. True se l'annuncio va rinviato
        (e allora è messo da parte)."""
        brain = self.brain
        msg = str(item.get("messaggio") or "")
        if item.get("in_sospeso") and msg.rstrip().endswith("?") and brain.has_pending():
            print(f"\n   [ANNUNCI] Rinviato (c'è già una domanda in sospeso): {msg[:80]}",
                  flush=True)
            self.annunci_rinviati.append((coda, item))
            # Se nessuno risponde, alla scadenza della domanda di prima l'ascolto si sveglia
            # e l'annuncio rinviato si dice
            resto = (getattr(brain, "pending", None) or {}).get("scade", 0) - time.monotonic()
            t = threading.Timer(max(0.5, resto + 0.2), self.sveglia.set)
            t.daemon = True
            t.start()
            return True
        return False

    def proteggi(self, prof, categorie, rec_):
        """Un minore in pericolo (05/10, calliope/guardiano.py): avviso discreto e urgente ai
        tutori, solo l'argomento; nel registro dei turni niente frasi del minore."""
        rec_["testo"] = rec_["richiesta"] = None
        rec_["guardiano"] = {"esito": "pericolo", "categorie": list(categorie or ())}
        self.rule("guardiano_pericolo")
        av = minori.avvisi()
        if prof is None or av is None:
            return
        argomento = next((guardia.ARGOMENTI[c] for c in (categorie or ())
                          if c in guardia.ARGOMENTI), "ha detto una cosa che mi preoccupa")
        try:
            # Lo stesso episodio non si avvisa due volte (prova e2e del 06/10: la frase di
            # Sofia spezzata in due turni mandava due avvisi uguali); un argomento diverso sì
            n = av.manda(prof, "sicurezza", f"{prof.name} {argomento}. Gli ho detto di "
                                            f"parlarne con un adulto e gli ho dato il numero del "
                                            f"Telefono Azzurro. Parlagli appena puoi, con calma.",
                         urgente=True,
                         non_ripetere_s=float(getattr(self.s.cfg, "minori_avviso_ripetuto_s",
                                                      0) or 0))
            if n == -1:
                self.rule("avviso_pericolo_ripetuto")
        except Exception as e:  # noqa: BLE001
            print(f"   [MINORI] avviso non mandato: {type(e).__name__}: {e}", flush=True)

    def avvisi_ai_tutori(self, nome):
        """Gli avvisi per chi ha appena parlato, se è un tutore riconosciuto dalla voce: con il
        segnale, dopo la risposta. Una volta al giorno anche i promemoria dell'impronta."""
        cfg, registry, speaker = self.s.cfg, self.s.registry, self.speaker
        controllo_impronte = self.s.controllo_impronte
        av = minori.avvisi()
        if av is None:
            return
        if time.monotonic() - controllo_impronte[0] > 86400 or not controllo_impronte[0]:
            controllo_impronte[0] = time.monotonic()
            reg = minori.regole()
            for p in list(getattr(registry, "users", {}).values()):
                motivo = minori.impronta_da_rifare(p, cfg=cfg) if minori.e_minore(p) else None
                if not motivo or reg is None:
                    continue
                ultima = reg.leggi(p.id).get("promemoria_impronta")
                oggi = datetime.date.today()
                if ultima and (oggi - datetime.date.fromisoformat(ultima)).days < 7:
                    continue
                reg.imposta(p.id, "promemoria_impronta", oggi.isoformat())
                av.manda(p, "impronta", f"È ora di rifare la registrazione della voce di "
                                        f"{p.name}: {motivo}. Quando siete insieme, dimmi «rifai "
                                        f"la voce di {p.name}».")
        prof = registry.get(nome) if nome else None
        if prof is None or self.speaker_ctx.identified_by != "voce":
            return
        lista = av.da_dire(prof.id)
        if lista:
            self.rule("avviso_tutore")
            speaker.start_turn()
            speaker.chime()
            speaker.say(av.frase(lista))
            speaker.wait()
        self.richieste_al_tutore(prof)

    def richieste_al_tutore(self, prof):
        """Le richieste dei ragazzi in attesa (05/10, minori.Richieste): dopo la prima risposta
        al tutore riconosciuto dalla voce, una volta per conversazione, «Intanto: Bianca ti ha
        chiesto…?», e la domanda diventa un'azione in sospeso (il «sì» la approva con
        minore_gestisci). Mai se c'è già un'altra domanda in sospeso.

        Prova e2e del 06/10 (giro 5): a «Sofia mi ha chiesto qualcosa?» la richiesta si diceva
        due volte nello stesso turno (la frase di minore_gestisci(richieste) e poi «Intanto:
        …»), e dopo «Non sono sicura di aver capito… potresti spiegarmelo meglio?» arrivava
        una seconda domanda («… Va bene?») che diventava l'azione in sospeso del turno dopo
        (a «che ore sono?» il 26B rispondeva «Mi hai interrotta…»). Ora le richieste elencate
        dal tool in questa risposta contano come dette, e dopo una risposta che chiede
        qualcosa (Brain.ultima_domanda) la richiesta aspetta una risposta dopo."""
        brain, registry, speaker = self.brain, self.s.registry, self.speaker
        rq = minori.richieste()
        if rq is None or minori.e_minore(prof) or brain.has_pending():
            return
        conv = getattr(brain, "conv", None)
        dette = getattr(conv, "richieste_dette", None) if conv is not None else None
        if conv is not None and dette is None:
            dette = set()
            try:
                conv.richieste_dette = dette
            except AttributeError:
                return
        try:
            attese = [r for r in rq.in_attesa_per(prof, registry) if r["id"] not in dette]
        except Exception as e:  # noqa: BLE001
            print(f"   [MINORI] richieste non lette: {type(e).__name__}: {e}", flush=True)
            return
        if not attese:
            return
        elencate = any(t.get("nome") == "minore_gestisci" and t.get("ok")
                       and str((t.get("argomenti") or {}).get("azione") or "") == "richieste"
                       for t in getattr(brain, "last_tools", None) or ())
        if elencate:
            # Già dette dal tool in questa risposta: non si ripetono
            for x in attese:
                dette.add(x["id"])
            return
        ultima = getattr(brain, "ultima_domanda", None)
        if callable(ultima) and ultima():
            return                  # la risposta ha appena chiesto qualcosa: prima quella
        r = attese[0]
        for x in attese:
            dette.add(x["id"])
        minore = minori._per_id(registry, r["minore"])
        nome_m = getattr(minore, "name", "un ragazzo")
        frase = "Intanto: " + rq.frase(r, nome_m) + ". Va bene?"
        if len(attese) > 1:
            frase = (f"Intanto: ci sono {len(attese)} richieste dei ragazzi. La prima: "
                     + rq.frase(r, nome_m) + ". Va bene?")
        self.rule("richiesta_al_tutore")
        print(f"   [MINORI] richiesta R{r['id']} detta a {prof.name}", flush=True)
        speaker.start_turn()
        speaker.say(frase)
        speaker.wait()
        args = {"nome": nome_m, "azione": "approva_richiesta", "valore": f"R{r['id']}"}
        brain.record_announcement(frase, {
            "tool": "minore_gestisci", "argomenti": args, "domanda": "Va bene?",
            "cosa": f"approvare la richiesta di {nome_m}",
            "messaggio": (f"Azione in sospeso: alla fine della tua ultima risposta hai chiesto "
                          f"a {prof.name} se approva la richiesta R{r['id']} di {nome_m} "
                          f"({rq.frase(r, nome_m)}). Se acconsente (sì, va bene, ok) chiama "
                          f"minore_gestisci con azione=\"approva_richiesta\", nome="
                          f"\"{nome_m}\", valore=\"R{r['id']}\" (con i minuti dopo, se li dice: "
                          f"\"R{r['id']} 20\"). Se rifiuta chiama minore_gestisci con azione="
                          f"\"nega_richiesta\" e lo stesso valore. Se chiede altro, fai quello "
                          f"che chiede.")}, fonte=None)

    def errore_nel_giro(self, e: Exception):
        """Un errore imprevisto in un giro: traccia nel log, una frase di scuse, il turno nel
        registro con l'errore, e si continua. Troppi di fila (ERRORI_MAX in ERRORI_FINESTRA_S)
        vuol dire un guasto che non passa: uscita con errore, così systemd la riavvia da capo
        (su Windows si chiude e lo dice)."""
        import traceback
        ora = time.monotonic()
        errori = self.errori_ciclo
        errori[:] = [t for t in errori if ora - t < ERRORI_FINESTRA_S] + [ora]
        print(f"\n[ERRORE] Errore imprevisto nel ciclo ({type(e).__name__}: {e}): continuo",
              flush=True)
        traceback.print_exc()
        if self.rec is not None:
            self.rec["errore"] = f"{type(e).__name__}: {e}"[:300]
            self.s.turns.write(self.rec)
            self.rec = None
        try:
            self.speaker.start_turn()
            self.speaker.say("Scusa, ho avuto un problema.")
            self.speaker.wait()
        except Exception:  # noqa: BLE001 — anche la voce può essere il guasto
            pass
        if len(errori) >= ERRORI_MAX:
            raise SystemExit(f"[ERRORE] {len(errori)} errori imprevisti in "
                             f"{ERRORI_FINESTRA_S:.0f} s: esco (sotto systemd riparto da capo)")

    def esegui(self, fine: threading.Event | None = None) -> None:
        """Il ciclo: un giro dopo l'altro, protetti (errore_nel_giro), fino a «spegniti» o a
        `fine`. Un SystemExit (troppi errori) esce da qui. In una corsia di satellite «esci»
        addormenta e il ciclo continua (Q10 della seconda analisi del 06/10): chiudere il thread
        lascerebbe il satellite sordo, con la corsia ancora registrata nello smistatore. Oggi
        dai satelliti «spegniti» è già «spegni_satellite» (exit_action): è una rete per la
        prossima modifica."""
        while fine is None or not fine.is_set():
            try:
                if self.giro() == "esci":
                    if getattr(self.corsia, "satellite_id", None) is None:
                        return
                    self._dormi_invece_di_uscire()
            except Exception as e:  # noqa: BLE001
                self.errore_nel_giro(e)

    def _dormi_invece_di_uscire(self):
        """«esci» in una corsia di satellite: torna ad aspettare il nome, conversazione chiusa
        (il turno è già nel registro: non si riscrive)."""
        print(f"[CORSIE] {self.corsia.nome}: «esci» da un satellite, torno a dormire (il "
              f"server resta acceso)", flush=True)
        self.rec = None
        if self.s.schermi is not None:
            try:
                self.s.schermi.conversazioni.chiudi(self.corsia.chiave_schermi)
            except Exception:  # noqa: BLE001
                pass
        self.brain.end_conversation()
        self.awake_until, self.last_question = 0.0, None

    # ── il giro ──
    def giro(self):
        """Un giro del ciclo: ascolta una frase e risponde (o annuncia). Restituisce "esci"
        quando Calliope si spegne. Dal 03/10 (analisi di robustezza) il giro è protetto
        (`esegui`): un errore imprevisto (disco pieno nel registro, CUDA, un satellite che
        cade) non chiude più Calliope. Dal 06/10 (P8) è diviso in fasi: ognuna restituisce
        None per passare alla successiva, `_FINE` per chiudere il giro o "esci"."""
        t = Turno(guided=self._inizio_giro())
        self._riprendi_rinviati()
        if not t.guided and self._annunci_pronti():
            self._di_gli_annunci()
            return None
        for fase in (self._prendi_scritto, self._scritto_senza_domanda, self._ascolta,
                     self._trascrivi, self._chi_parla, self._conversazione_del_turno,
                     self._arruolamento, self._nome_reale, self._richiamo, self._primo_avvio,
                     self._mostra_richiesta, self._uscite, self._chiusure,
                     self._fuori_orario, self._contesto_e_allegati):
            esito = fase(t)
            if esito is not None:
                return None if esito is _FINE else esito
        self._rispondi(t)
        self._registra_risposta(t)
        self._dopo_la_risposta(t)
        return None

    # ── fase 0: tra un turno e l'altro ──
    def _inizio_giro(self) -> bool:
        """In cima al giro: il turno di prima nel registro, la conversazione di nuovo libera,
        la registrazione della voce scaduta, il tool della ricerca web se è tornata.
        Restituisce `guided`: durante una registrazione della voce (o in attesa del nome del
        primo utente) si ascolta senza bisogno del nome."""
        s, cfg, speaker_ctx = self.s, self.s.cfg, self.speaker_ctx
        if self.rec:
            s.turns.write(self.rec)
            self.rec = None
        # Il turno di prima è finito: voce di nuovo accesa, il satellite in prestito resta
        # attivo fino alla fine della finestra di follow-up (calliope/rispondi.py)
        self.awake_until = s.instradamento.dopo_turno(self.awake_until)
        self.corsia.fine_turno()          # la conversazione del turno torna libera (corsie.py)
        if s.satelliti is not None:
            # Senza un satellite collegato nessuno sente: anche gli annunci (timer, lavori
            # finiti) aspettano che se ne colleghi uno
            self.listener.attendi()
        # Durante una registrazione della voce (o in attesa del nome del primo utente)
        # si ascolta senza bisogno del nome: il 26/09 Calliope si riaddormentava dopo
        # la prima frase e chi si registrava doveva dire «Calliope» a ogni frase
        if speaker_ctx.enroll_expired:
            # Nessuna frase valida per speaker_enroll_timeout_s: la registrazione si chiude
            # (aperta per sempre, la prima voce che passava diventava una frase: 03/10)
            name_exp = speaker_ctx.enrolling_name
            speaker_ctx.stop_enroll()
            print(f"   [SPEAKER] Registrazione di «{name_exp}» scaduta.", flush=True)
            self.speaker.say("La registrazione della voce è scaduta: se vuoi, chiedimela di nuovo.")
            self.speaker.wait()
        guided = speaker_ctx.is_enrolling or self.pending_real_name is not None
        # SearXNG era giù all'avvio e ora risponde: il tool compare tra un turno e l'altro
        # (il prompt lo nomina dal turno dopo), senza riavvio
        if s.web is not None and s.web.pronta and s.tools.get("web_cerca") is None:
            from .tools.web import web_spec
            spec = web_spec(cfg)
            s.tools.register(spec)
            self.speaker.prepare(spec.announce)
            self.brain.rileggi_tool()
        # Il turno di prima è finito (o non c'era): un agente sullo stesso Ollama riparte dopo
        # agenti_ripresa_s. La voce lo ferma di nuovo appena qualcuno le parla (on_speech_start)
        if s.lavori is not None:
            s.lavori.arbitro.voce_libera()
        if guided:
            self.awake_until = max(self.awake_until, time.monotonic() + cfg.followup_s)
        awake = not cfg.wake_word_enabled or time.monotonic() < self.awake_until
        print("\n🎙  In ascolto…" if awake else f"\n💤 Di' «{cfg.wake_names[0]}» per svegliarmi…")
        return guided

    # ── annunci: timer, documenti, installazioni, lavori, estensioni, giochi ──
    def _riprendi_rinviati(self):
        """Gli annunci con una domanda rinviati (vedi `rinvia`) tornano in coda quando la
        domanda di prima ha avuto la sua risposta (o è scaduta)."""
        if self.annunci_rinviati and not self.brain.has_pending():
            for coda, it in self.annunci_rinviati:
                coda.put(it)
            self.annunci_rinviati.clear()

    def _annunci_pronti(self) -> bool:
        """Timer e promemoria scaduti, documenti pronti, lavori finiti…: si annunciano prima di
        tornare ad ascoltare."""
        a, giochi = self.annunci, self.s.giochi
        code = (a.documenti, a.installazioni, a.lavori, a.estensioni)
        return (not a.agenda.empty() or any(q is not None and not q.empty() for q in code)
                # Le frasi dei giochi (05/10): una coda sola, la dice la prima corsia libera
                or (giochi is not None and not giochi.frasi.empty()))

    def _di_gli_annunci(self):
        self.sveglia.clear()
        self._annuncia_agenda()
        self._annuncia_documenti()
        self._annuncia_installazioni()
        self._annuncia_lavori()
        self._annuncia_estensioni()
        self._annuncia_giochi()
        self.speaker.wait()
        self.awake_until = time.monotonic() + self.s.cfg.followup_s   # per rispondere senza nome
        self.rec = None

    def _annuncia_agenda(self):
        coda, speaker = self.annunci.agenda, self.speaker
        while not coda.empty():
            item = coda.get_nowait()
            msg = announcement(item)
            print(f"\n   [AGENDA] {msg}", flush=True)
            # Dal satellite da cui era stato chiesto, se è collegato (04/10)
            self.s.instradamento.annuncia_verso(("agenda", item.get("id")))
            speaker.chime()
            speaker.say(msg)

    def _annuncia_documenti(self):
        coda, speaker, brain = self.annunci.documenti, self.speaker, self.brain
        while coda is not None and not coda.empty():
            done_item = coda.get_nowait()
            if self.rinvia(coda, done_item):
                continue
            msg = done_item["messaggio"]
            print(f"\n   [DOCUMENTI] {msg}", flush=True)
            self.s.instradamento.annuncia_verso(persona=done_item.get("owner"))
            # Nella conversazione di chi l'aveva chiesto (06/10, corsie.py)
            self.corsia.annuncio_per(brain, done_item.get("owner"))
            speaker.chime()
            speaker.say(msg)
            # Nella storia: a «sì, aprilo» il modello sa quale documento; «La apro?»
            # diventa un'azione in sospeso per il turno dopo
            brain.record_announcement(msg, done_item.get("in_sospeso"), fonte=None)

    def _annuncia_installazioni(self):
        """Installazioni finite: si attivano qui (thread della corsia), poi l'annuncio; nel
        registro dei turni chi, cosa, quando ed esito."""
        coda, speaker = self.annunci.installazioni, self.speaker
        while coda is not None and not coda.empty():
            item = coda.get_nowait()
            msg = self.s.installazioni.completa(item) if item["annuncia"] else ""
            self.s.turns.write({"inizio": item["fine"], "esito": "installazione",
                                "livello": "amministra", "installazione": item,
                                "risposta": msg or None})
            if msg:
                print(f"\n   [INSTALLA] {msg}", flush=True)
                speaker.chime()
                speaker.say(msg)
                self.brain.record_announcement(msg, fonte=None)

    def _annuncia_lavori(self):
        """Lavori dell'agente finiti: segnale, frase breve (mai il codice: quello è sullo
        schermo e nei file), nella storia per «aprilo» e «cosa hai fatto?», e una riga nel
        registro dei turni."""
        s, coda, speaker, brain = self.s, self.annunci.lavori, self.speaker, self.brain
        while coda is not None and not coda.empty():
            item = coda.get_nowait()
            if self.rinvia(coda, item):
                continue
            # Una domanda dell'agente va anche sullo schermo personale, come modulo
            msg = annuncio_lavoro(s.schermi, item, s.lavori, brain)
            item.pop("modulo", None)
            if s.cfg.rete("riferire") and not (item.get("in_sospeso") or {}).get(
                    "tool") == "estensioni_gestisci":
                # Il riassunto è dell'agente (06/10, calliope/riferire.py): numeri a
                # pagamento, codici, soldi e indicazioni sulla casa non si ripetono
                msg, regole_u = riferire.controlla_testo(
                    msg, "agente", provenienza.testo_persona(
                        getattr(brain, "history", None) or []),
                    str(item.get("titolo") or ""))
                for regola in regole_u:
                    print(f"   [USCITA] annuncio: {regola}", flush=True)
            s.turns.write({"inizio": datetime.datetime.now().isoformat(timespec="seconds"),
                           "esito": "lavoro", "lavoro": {k: v for k, v in item.items()
                                                         if k != "messaggio"},
                           "risposta": msg})
            print(f"\n   [AGENTI] {msg}", flush=True)
            s.instradamento.annuncia_verso(persona=item.get("chi"))
            self.corsia.annuncio_per(brain, item.get("chi"))
            speaker.chime()
            speaker.say(msg)
            # Una domanda dell'agente («… ho una domanda: …?») diventa un'azione in
            # sospeso: la risposta nel turno dopo va a lavori_rispondi. Il riassunto è
            # dell'agente: dato non fidato (calliope/provenienza.py)
            brain.record_announcement(msg, item.get("in_sospeso"), fonte="agente")

    def _annuncia_estensioni(self):
        """Estensioni che il tool non ha aspettato: il risultato, o l'azione pericolosa che
        aspetta il «sì» (diventa un'azione in sospeso, come le domande dei lavori)."""
        s, coda, speaker, brain = self.s, self.annunci.estensioni, self.speaker, self.brain
        while coda is not None and not coda.empty():
            item = coda.get_nowait()
            if self.rinvia(coda, item):
                continue
            msg = item["messaggio"]
            if s.cfg.rete("riferire"):
                msg, regole_u = riferire.controlla_testo(
                    msg, "estensione", provenienza.testo_persona(
                        getattr(brain, "history", None) or []))
                for regola in regole_u:
                    print(f"   [USCITA] annuncio: {regola}", flush=True)
            s.turns.write({"inizio": datetime.datetime.now().isoformat(timespec="seconds"),
                           "esito": "estensione", "estensione": {k: v for k, v in item.items()
                                                                 if k != "messaggio"},
                           "risposta": msg})
            print(f"\n   [ESTENSIONI] {msg}", flush=True)
            speaker.chime()
            speaker.say(msg)
            brain.record_announcement(msg, item.get("in_sospeso"), fonte="estensione")

    def _annuncia_giochi(self):
        """Le frasi dei giochi (05/10, schermi/giochi.py: già controllate lì, poche al minuto,
        dal guardiano per i minori): si dicono e basta, fuori dalla storia della conversazione
        (non sono una risposta di Calliope né una domanda)."""
        giochi = self.s.giochi
        while giochi is not None and not giochi.frasi.empty():
            item = giochi.frasi.get_nowait()
            msg = str(item.get("messaggio") or "")
            self.s.turns.write({"inizio": datetime.datetime.now().isoformat(timespec="seconds"),
                                "esito": "gioco", "gioco": {"partita": item.get("partita"),
                                                            "titolo": item.get("titolo")},
                                "risposta": None if item.get("minore") else msg,
                                "regole": ["gioco_frase"]})
            print(f"\n   [GIOCHI] «{item.get('titolo')}»: "
                  f"{'(frase di un gioco di un minore)' if item.get('minore') else msg}",
                  flush=True)
            self.speaker.say(msg)

    # ── fase 1: scrivere invece di parlare ──
    def _prendi_scritto(self, t):
        """Scrivere invece di parlare (03/10, schermi/moduli.py). Un modulo inviato da uno
        schermo personale va dritto al tool che l'aveva chiesto (né Whisper né il modello
        vedono i valori); un testo scritto vale come una frase detta e segue il percorso di
        sempre dopo lo STT, senza wake word."""
        schermi = self.s.schermi
        if schermi is None or t.guided:
            return None
        scritto = self.ingresso.prendi()
        if scritto is None:
            return None
        self.sveglia.clear()          # la sveglia era per questo: l'ascolto non gira a vuoto
        if not self.ingresso.vuoto():
            self.sveglia.set()
        # Di nuovo qui (05/10): la conversazione può essere finita mentre il testo
        # aspettava in coda («esci» detto un attimo prima). Niente al ciclo
        ok, motivo = schermi.scrittura_consentita(schermi.schermo(scritto.get("schermo_id")))
        if not ok:
            print(f"   [SCHERMI] scritto dallo schermo «{scritto.get('schermo')}» "
                  f"scartato: nessuna conversazione ({motivo})", flush=True)
            self.rec = {"inizio": datetime.datetime.now().isoformat(timespec="milliseconds"),
                        "esito": "rifiutato", "canale": scritto.get("tipo"),
                        "schermo": scritto.get("schermo"), "motivo": motivo,
                        "regole": ["scritto_senza_conversazione"]}
            return _FINE
        # Rispondi dove ti ho chiesto: dal satellite di quello schermo, oppure solo
        # scritto se lo schermo non ha audio ed è in un'altra stanza
        come = self.s.instradamento.inizio_scritto(scritto, self.awake_until)
        if come != "satellite":
            print(f"   [SCHERMI] risposta {'solo scritta' if come == 'muta' else 'qui'}"
                  f" per lo schermo «{scritto.get('schermo')}»", flush=True)
        t.scritto = scritto
        return None

    def _scritto_senza_domanda(self, t):
        """File, foto e moduli dagli schermi: con il testo sono una frase scritta, da soli
        aspettano la domanda (o vanno dritti al tool)."""
        tipo = (t.scritto or {}).get("tipo")
        if tipo == "allegato":
            return self._allegato_dallo_schermo(t)
        if tipo == "immagine":
            return self._foto_dallo_schermo(t)
        if tipo == "modulo":
            return self._modulo_dallo_schermo(t)
        return None

    def _senza_domanda(self, t, frase: str):
        """La frase detta (e scritta sullo schermo) per un file o una foto senza domanda."""
        self.s.instradamento.risposta_scritta(t.scritto, "", frase)
        self.speaker.start_turn()
        self.speaker.say(frase)
        self.speaker.wait()
        self.rec["risposta"] = frase
        self.awake_until = time.monotonic() + self.s.cfg.followup_s
        return _FINE

    def _allegato_dallo_schermo(self, t):
        """Un file dallo schermo personale (05/10, calliope/allegati.py): come una foto. Con
        il testo è una frase scritta con il file; da solo aspetta la domanda. Il nome del file
        non si dice né si registra (è un dato di chi l'ha mandato)."""
        scritto, schermi = t.scritto, self.s.schermi
        att = scritto.pop("allegato")
        if (scritto.get("testo") or "").strip():
            scritto.update(tipo="scritto", allegati=[att])
            return None
        self.s.foto_attesa.metti(att)
        frase = allegati_mod.FILE_IN_ATTESA.format(cosa=att.detto())
        self.rec = {"inizio": datetime.datetime.now().isoformat(timespec="milliseconds"),
                    "esito": "allegato_in_attesa", "canale": "scritto",
                    "allegati": [att.per_registro()]}
        print(f"\n📎 File dallo schermo «{scritto.get('schermo')}» ({att.tipo()}, "
              f"{round(att.dimensione / 1024)} kB): aspetto la domanda", flush=True)
        if schermi is not None and scritto.get("schermo_id") is not None:
            try:
                schermi.invia_a(scritto["schermo_id"], schede_foto.allegato(att))
            except Exception as e:  # noqa: BLE001 — lo schermo non ferma la voce
                print(f"   [SCHERMI] file non mostrato: {e}", flush=True)
        return self._senza_domanda(t, frase)

    def _foto_dallo_schermo(self, t):
        """Una foto dallo schermo personale (05/10, calliope/immagini.py): con il testo è una
        frase scritta con la foto; da sola aspetta la domanda, scritta o detta."""
        scritto, schermi = t.scritto, self.s.schermi
        img = scritto.pop("immagine")
        if (scritto.get("testo") or "").strip():
            scritto.update(tipo="scritto", immagini=[img])
            return None
        self.s.foto_attesa.metti(img)
        self.rec = {"inizio": datetime.datetime.now().isoformat(timespec="milliseconds"),
                    "esito": "foto_in_attesa", "canale": "scritto",
                    "immagini": [img.per_registro()]}
        print(f"\n📷 Foto dallo schermo «{scritto.get('schermo')}» "
              f"({img.larghezza}×{img.altezza}): aspetto la domanda", flush=True)
        if schermi is not None and scritto.get("schermo_id") is not None:
            try:
                schermi.invia_a(scritto["schermo_id"], schede_foto.foto(img))
            except Exception as e:  # noqa: BLE001 — lo schermo non ferma la voce
                print(f"   [SCHERMI] foto non mostrata: {e}", flush=True)
        return self._senza_domanda(t, FOTO_IN_ATTESA)

    def _modulo_dallo_schermo(self, t):
        """Un modulo inviato: dritto al tool che l'aveva chiesto (schermi/moduli.py)."""
        scritto, brain, speaker = t.scritto, self.brain, self.speaker
        self.voce("pensa")
        # Il modulo è della conversazione della persona (06/10, corsie.py)
        self.corsia.turno(brain, None, "schermo", True, persona_id=scritto.get("persona"))
        esito = completa_modulo(self.s.schermi, scritto, brain, getattr(brain, "turn_number", 0))
        self.rec = {"inizio": datetime.datetime.now().isoformat(timespec="milliseconds"),
                    **esito["rec"]}
        print(f"\n✍  Modulo «{self.rec.get('modulo')}» dallo schermo "
              f"({', '.join(self.rec['campi'])})")
        if esito["frase"]:
            print(f"{self.s.cfg.name}: {oscura(esito['frase'])}", flush=True)
            self.s.instradamento.risposta_scritta(scritto, "", esito["frase"])
            speaker.start_turn()
            speaker.say(esito["frase"])
            speaker.wait()
            self.rec["risposta"] = oscura(esito["frase"])
        self.awake_until = time.monotonic() + self.s.cfg.followup_s
        return _FINE

    # ── fase 2: ascolto ──
    def _ascolta(self, t):
        """Lo stato della voce sugli schermi, poi una frase dal microfono (o quella scritta).
        Apre il turno nel registro."""
        s, cfg, listener = self.s, self.s.cfg, self.listener
        if t.guided or not cfg.wake_word_enabled:
            self.attesa_voce[:] = ["ascolta", None]
        elif time.monotonic() < self.awake_until:
            self.attesa_voce[:] = ["ascolta", time.time() + (self.awake_until - time.monotonic())]
        else:
            self.attesa_voce[:] = ["dorme", None]
        if t.scritto is None:
            self.voce(*self.attesa_voce)
            audio = listener.listen(None if t.guided else s.wake,
                                    self.awake_until if not t.guided else float("inf"),
                                    seed=self.barge_seed,
                                    wakeup=self.sveglia if not t.guided else None)
            if audio is None:        # svegliata dall'agenda o da una pagina: al giro dopo
                return _FINE
            self.frasi_prese += 1    # la finestra del nome da solo non suona più la fine
            s.instradamento.inizio_voce()
            t.barged, self.barge_seed = self.barge_seed is not None, None
            # Frase presa (suono di fine ascolto): con la wake word acustica listen restituisce
            # solo le frasi rivolte a Calliope; con quella testuale si aspetta il nome (sotto)
            if s.suoni is not None and s.satelliti is None and s.wake is not None \
                    and not t.guided:
                self.speaker.suono_ascolto(s.suoni, FINE)
            t.in_session = listener.started_at <= self.awake_until   # nella finestra
            started = time.time() - (time.monotonic() - listener.started_at)
        else:
            audio = np.zeros(0, dtype=np.float32)     # niente audio: il testo è già scritto
            t.barged, t.in_session = False, True
            started = t.scritto.get("arrivato") or time.time()
        t.audio = audio
        self.voce("pensa")
        t.t0 = time.perf_counter()
        t.t0_mono = time.monotonic()    # per fine_parlato_s (Listener.ended_at è monotonic)
        self.rec = {"inizio": datetime.datetime.fromtimestamp(started).isoformat(
                        timespec="milliseconds"),
                    "durata_s": round(len(audio) / cfg.sample_rate, 2), "sveglia": t.in_session,
                    "livello": self.speaker_ctx.current_level, "voce": None, "testo": None,
                    "esito": None, **({"canale": "scritto"} if t.scritto else {})}
        return None

    # ── fase 3: trascrizione ──
    def _trascrivi(self, t):
        """Whisper (intanto l'impronta si calcola nell'altro thread) e, se accesa, la
        correzione delle frasi incerte."""
        s, cfg = self.s, self.s.cfg
        # Durata della voce, senza pre-roll e silenzio finale: decide se l'impronta è
        # affidabile (sotto ~1 s no) e se una frase vale per l'arruolamento
        t.voiced_s = max(0.0, len(t.audio) / cfg.sample_rate
                         - (cfg.preroll_ms + cfg.silence_ms) / 1000)
        identify = (cfg.speaker_id_enabled and not self.speaker_ctx.is_enrolling
                    and t.scritto is None)
        t.emb_job = (s.embed_pool.submit(s.registry.embed, t.audio, cfg.sample_rate)
                     if identify else None)
        t.text = s.stt.transcribe(t.audio) if t.scritto is None else t.scritto["testo"]
        conf_stt = getattr(s.stt, "ultima_confidenza", None) if t.scritto is None else None
        t.conf_stt = conf_stt
        if conf_stt is not None and t.text:
            from . import stt_correzione
            # La parola più debole (nome escluso) e quante sotto 0,5, mai le parole: per
            # ritarare la soglia sulle conversazioni vere (05/10 sera)
            self.rec["stt_confidenza"] = {
                "min": round(stt_correzione.min_utile(conf_stt, cfg), 3),
                "deboli": len(conf_stt.deboli or conf_stt.incerte)}
        if s.correttore is not None:
            self._correggi_frase(t, conf_stt)
        return None

    def _parole_incerte(self, t) -> list[str]:
        """Le parole incerte da dire al modello della voce (stt_incerte_al_modello, 07/10),
        sulla frase che riceve (nome tolto, eventuale correzione); nel registro solo quante."""
        cfg = self.s.cfg
        if t.conf_stt is None or not (getattr(cfg, "stt_incerte_al_modello", False)
                                      or getattr(cfg, "stt_incerte_riscrivi", False)):
            return []
        from . import stt_correzione
        parole = stt_correzione.parole_incerte(t.conf_stt, cfg, t.text)
        if parole and isinstance(self.rec.get("stt_confidenza"), dict):
            self.rec["stt_confidenza"]["al_modello"] = len(parole)
        return parole

    def _correggi_frase(self, t, conf_stt):
        s, cfg, rec = self.s, self.s.cfg, self.rec
        from . import stt_correzione
        if t.text and stt_correzione.incerta(conf_stt, cfg):
            # Frase incerta: un secondo passaggio con le parole della casa e le ultime frasi.
            # La correzione vale solo se cambia parole storpiate in parole che suonano simili
            # (stt_correzione.accettabile); se il modello tarda, resta quella di Whisper
            es = s.correttore.correggi(
                t.text, conf_stt,
                stt_correzione.vocabolario_calliope(cfg, s.registry, s.satelliti, s.schermi,
                                                    s.casa),
                stt_correzione.storia_recente(self.brain))
            rec["stt_correzione_ms"] = es.ms
            if es.motivo == "tempo":         # oltre stt_correzione_timeout_s: vale Whisper
                rec["stt_correzione_scaduta"] = True
            if es.cambiata:
                print(f"   [STT] frase incerta corretta ({es.ms:.0f} ms)", flush=True)
                rec["stt_corretta"] = {"prima": es.prima, "dopo": es.testo}
                self.rule("stt_corretta")
                t.text = es.testo

    # ── fase 4: chi parla ──
    def _chi_parla(self, t):
        """Chi parla: il proprietario dello schermo da cui è scritta la frase, o la voce
        (impronta CAM++, frase breve, zona grigia, profilo più protetto)."""
        speaker_ctx = self.speaker_ctx
        t.speaker_name = None
        t.prev_how, speaker_ctx.identified_by = speaker_ctx.identified_by, None
        speaker_ctx.conferma_breve = speaker_ctx.sfida_superata = False   # valgono una frase
        speaker_ctx.incerta = speaker_ctx.minore_vicino = None            # anche queste
        if t.scritto is not None:
            self._chi_scrive(t)
        if t.emb_job is not None:
            self._riconosci_voce(t)
        self.rec.update(livello=speaker_ctx.current_level, testo=t.text,
                        stt_s=round(time.perf_counter() - t.t0, 2))
        return None

    def _chi_scrive(self, t):
        """Scritto da uno schermo personale: vale come il suo proprietario, con identified_by
        «schermo» (al più familiare: per ciò che vuole la voce di chi amministra si chiede la
        voce, tools/spec.serve_la_voce). Da uno schermo di stanza: ospite. Mai la zona grigia."""
        speaker_ctx = self.speaker_ctx
        prof = self.s.registry.by_id(t.scritto.get("persona"))
        speaker_ctx.current_speaker = prof.name if prof else None
        speaker_ctx.from_session = False
        speaker_ctx.identified_by = "schermo" if prof else None
        t.speaker_name = prof.name if prof else None
        self.rec["voce"] = {"nome": t.speaker_name, "modo": "schermo" if prof else "ospite",
                            "schermo": t.scritto.get("schermo")}
        speaker_ctx.aggiorna_conversazione(t.speaker_name, speaker_ctx.identified_by,
                                           True, None)

    def _classifica(self, emb) -> list:
        """[(nome, punteggio)] dal più somigliante; con un registro che sa solo il migliore
        (prove a secco), solo quello."""
        reg = self.s.registry
        if hasattr(reg, "classifica") and emb is not None:
            return list(reg.classifica(emb))
        best, sim = reg.best_match(emb=emb)
        return [(best, sim)] if best is not None else []

    def _confronta_voce(self, t, emb):
        """(nome, come, punteggio, migliore) per l'impronta della frase."""
        s, cfg, speaker_ctx = self.s, self.s.cfg, self.speaker_ctx
        classifica = self._classifica(emb)
        best, sim = classifica[0] if classifica and classifica[0][1] > 0 else (None, 0.0)
        secondo, sim2 = classifica[1] if len(classifica) > 1 else (None, None)
        t.voce_secondo = (secondo, sim2)
        # Voci di famiglia (07/10): sopra soglia ma a meno di `speaker_id_margine` dal secondo
        # profilo la voce non decide da sola (vale come la zona grigia)
        netta = sim2 is None or sim - sim2 >= float(getattr(cfg, "speaker_id_margine", 0.0))
        prev = speaker_ctx.current_speaker
        thr = cfg.speaker_id_threshold
        if t.voiced_s < cfg.speaker_min_voice_s and t.in_session and prev:
            # Frase troppo breve per l'impronta: vale chi parlava fino a un attimo fa,
            # ma al più come familiare (03/10, analisi di sicurezza S4): un «sì» di
            # chiunque, anche della TV, valeva come chi amministra (installazioni,
            # schermi personali, file). Se un attimo fa aveva scritto, resta «schermo»:
            # nemmeno lì un «sì» breve diventa la voce di chi amministra
            name, how = prev, ("schermo" if t.prev_how == "schermo" else "breve")
            if how == "breve":
                speaker_ctx.from_session = True
        elif sim >= thr and netta:
            name, how = best, "voce"
            speaker_ctx.from_session = False
        elif (t.in_session and best is not None and best == prev
              and sim >= thr - cfg.speaker_id_session_margin):
            # Zona grigia dentro una conversazione: conferma chi parlava al turno
            # prima, ma il livello si ferma a "familiare" (vedi current_level)
            name, how = best, "conversazione"
            speaker_ctx.from_session = True
        else:
            name, how = None, None
            speaker_ctx.from_session = False
        speaker_ctx.identified_by = how
        # Voce incerta tra un minore e un altro profilo (05/10, minori.piu_protetto): vale
        # il profilo più protetto, mai un adulto
        if not netta and sim >= thr and how != "breve":
            self.rule("voce_margine")
        protetto = minori.piu_protetto(s.registry, emb, name, how, sim, cfg)
        if protetto is not None and protetto != name:
            print(f"   [VOCE] incerta tra {name or 'ospite'} e {protetto}: vale {protetto} "
                  f"(il profilo più protetto)", flush=True)
            self.rule("minore_piu_protetto")
            # L'adulto tra cui si è incerti: chi era stato scelto, o il migliore se adulto.
            # Se serve una sua azione, la frase chiede chi parla (registry, brain._sfida)
            adulto = name or (best if best != protetto else secondo)
            if adulto and adulto != protetto and not minori.e_minore(s.registry.get(adulto)):
                speaker_ctx.incerta = (adulto, protetto)
            name, how = protetto, "conversazione"
            speaker_ctx.from_session = True
            speaker_ctx.identified_by = how
        elif how == "voce" and name:
            vicino = self._minore_vicino(name, sim, classifica)
            if vicino is not None:
                # Il verso pericoloso: chi amministra con un minore a meno di
                # `minori_margine_amministra`. Resta lui, ma al più familiare
                print(f"   [VOCE] {name}, ma {vicino} è vicino: niente permessi di chi "
                      f"amministra in questa frase", flush=True)
                self.rule("amministra_minore_vicino")
                speaker_ctx.minore_vicino = vicino
                how = "conversazione"
                speaker_ctx.from_session = True
                speaker_ctx.identified_by = how
        return name, how, sim, best

    def _minore_vicino(self, name, sim, classifica) -> str | None:
        """Il minore con un punteggio a meno di `minori_margine_amministra` da chi amministra
        riconosciuto dalla voce (None se chi parla non amministra o nessun minore è vicino)."""
        reg, cfg = self.s.registry, self.s.cfg
        prof = reg.get(name)
        if not getattr(prof, "admin", False) or not getattr(cfg, "minori_enabled", True):
            return None
        margine = float(getattr(cfg, "minori_margine_amministra", 0.0))
        for n, p in classifica:
            if n != name and sim - p < margine and minori.e_minore(reg.get(n)):
                return n
        return None

    def _riconosci_voce(self, t):
        cfg, registry, speaker_ctx = self.s.cfg, self.s.registry, self.speaker_ctx
        emb = t.emb_job.result()
        name, how, sim, best = self._confronta_voce(t, emb)
        if how == "voce" and name and minori.e_minore(registry.get(name)):
            # Media mobile del riconoscimento: il promemoria di rifare l'impronta
            p_m = registry.get(name)
            p_m.riconoscimento = (sim if p_m.riconoscimento is None
                                  else 0.9 * p_m.riconoscimento + 0.1 * sim)
            registry._da_salvare = True
        # Punteggio contro il profilo di chi vale in questa frase (per la frase breve:
        # chi parlava), per la conferma breve di chi amministra (calliope/conferme.py)
        vp = getattr(registry.get(name), "voiceprint", None) if name else None
        own = float(np.dot(emb, vp)) if vp is not None else None
        # Un altro profilo somiglia a questa frase almeno quanto chi vale: la frase breve non
        # conferma un'azione di chi amministra (07/10)
        altro = bool(own is not None and best is not None and best != name and sim >= own)
        speaker_ctx.aggiorna_conversazione(name, how, t.in_session, own, altro)
        adapted = how == "voce" and registry.adapt(name, emb, sim)
        # Punteggio sempre in console: serve a tarare soglia e impronta (docs/test-vocale.md)
        note = {"breve": " frase breve, vale la conversazione",
                "conversazione": " confermata dalla conversazione"}.get(how, "")
        if how == "breve" and own is not None:
            note += (f" ({own:.2f}: può confermare)" if speaker_ctx.conferma_breve
                     else f" ({own:.2f})")
        print(f"   [VOCE] {name or 'non riconosciuta'} {sim:.3f}"
              f" (soglia {cfg.speaker_id_threshold:.2f}, voce {t.voiced_s:.1f} s){note}"
              + (" · impronta aggiornata" if adapted else ""), flush=True)
        # Riconosciuto → familiare, non riconosciuto → ospite (principio 9).
        # Azzerare a None evita che resti lo speaker del turno precedente.
        speaker_ctx.current_speaker = name
        secondo, sim2 = getattr(t, "voce_secondo", (None, None))
        self.rec["voce"] = {"nome": name, "migliore": best, "punteggio": round(sim, 3),
                            "modo": how, "voce_s": round(t.voiced_s, 2), "aggiornata": adapted,
                            # Il secondo profilo e la distanza dal primo (07/10): per tarare
                            # `speaker_id_margine` e `minori_margine_amministra` sui turni veri
                            **({"secondo": secondo, "secondo_punteggio": round(sim2, 3),
                                "margine": round(sim - sim2, 3)} if secondo is not None else {}),
                            **({"incerta": list(speaker_ctx.incerta)}
                               if getattr(speaker_ctx, "incerta", None) else {}),
                            **({"minore_vicino": speaker_ctx.minore_vicino}
                               if getattr(speaker_ctx, "minore_vicino", None) else {}),
                            **({"conferma_breve": speaker_ctx.conferma_breve,
                                "punteggio_conversazione": round(own, 3)}
                               if how == "breve" and own is not None else {})}
        if name:
            t.speaker_name = name
            # Se l'utente ha una voce preferita, usala
            prof = registry.get(name)
            if prof and prof.preferred_voice and \
                    self.speaker._current_voice_path != prof.preferred_voice:
                self.speaker.change_voice(prof.preferred_voice)

    # ── fase 5: la conversazione del turno ──
    def _persona_id(self, nome):
        return getattr(self.s.registry.get(nome), "id", None) if nome else None

    def _conversazione_del_turno(self, t):
        """La conversazione del turno (06/10, calliope/corsie.py): quella di chi parla, da
        qualunque satellite, se la voce è riconosciuta sopra la soglia; la frase breve
        continua quella di questo satellite; gli ospiti hanno la loro, qui. Un doppione (la
        stessa frase presa da un altro satellite nella stessa stanza) si scarta."""
        s = self.s
        if self._chiedi_chi_parla(t):
            return _FINE
        # Chi amministra con un minore vicino (07/10): la voce lo ha riconosciuto (sopra il
        # margine), quindi la sua conversazione; i permessi restano da familiare
        how = ("voce" if getattr(self.speaker_ctx, "minore_vicino", None)
               else self.speaker_ctx.identified_by)
        if not self.corsia.turno(self.brain, t.speaker_name, how,
                                 t.in_session, t.text, self.rec, t.scritto,
                                 persona_id=self._persona_id(t.speaker_name),
                                 impronta=t.emb_job.result() if t.emb_job is not None
                                 else None):
            return _FINE
        # Chi ha chiesto: i suoi documenti e lavori si annunceranno da dove ha chiesto
        s.instradamento.persona(self._persona_id(t.speaker_name))
        if s.cfg.debug_audio_dir and t.scritto is None:
            self.rec["audio"] = save_debug_audio(s.cfg, t.audio, t.text)
        if not t.text and not self._risveglio_acustico(t):
            self.rec["esito"] = "vuoto"
            return _FINE
        return None

    def _chiedi_chi_parla(self, t) -> bool:
        """Voce incerta tra chi parlava (chi amministra) e un minore, mentre la conversazione di
        chi amministra su questo satellite aspetta il suo «sì» a un'azione proposta (07/10: in
        auto «Sì, procedi.» di chi amministra valeva come il minore, la sua conversazione si
        perdeva e l'azione restava lì). Vale sempre il profilo più protetto, ma invece di
        rispondere al minore in una conversazione vuota la frase chiede chi parla; l'azione
        resta in sospeso per la voce di chi amministra. Regola `voce_incerta_chiede`."""
        from .conferme import CHI_PARLA
        sc = self.speaker_ctx
        inc = getattr(sc, "incerta", None)
        conv = getattr(self.corsia, "conv", None)
        if (not inc or not t.in_session or t.scritto is not None or not t.text or conv is None
                or getattr(sc, "sfida", None) is not None):
            return False
        prof = self.s.registry.get(inc[0])
        pid = getattr(prof, "id", None)
        p = getattr(conv, "pending", None)
        if (not getattr(prof, "admin", False) or not pid or not isinstance(p, dict)
                or getattr(conv, "chiave", None) != corsie.RegistroConversazioni.chiave_persona(pid)
                or p.get("chi") != pid or time.monotonic() > float(p.get("scade", 0))):
            return False
        frase = CHI_PARLA.format(adulto=inc[0], minore=inc[1])
        print(f"   [VOCE] incerta con un'azione in sospeso: chiedo chi parla", flush=True)
        self.rule("voce_incerta_chiede")
        self.speaker.start_turn()
        self.speaker.say(frase)
        self.speaker.wait()
        self.rec.update(esito="chi_parla", risposta=frase)
        self.awake_until = time.monotonic() + self.s.cfg.followup_s
        return True

    def _risveglio_acustico(self, t) -> bool:
        """La frase è passata perché la wake word acustica è scattata a Calliope addormentata
        (non nella finestra d'ascolto, non scritta, non durante una registrazione). Una frase
        così con il testo vuoto è il nome da solo (vedi `_cerca_il_nome`), non un «vuoto»."""
        s, cfg = self.s, self.s.cfg
        return (s.wake is not None and cfg.wake_word_enabled and t.scritto is None
                and not t.guided and not t.barged
                and self.listener.started_at > self.awake_until)

    def _segna_conversazione(self, t):
        """Una frase detta e rivolta a Calliope: la conversazione per lo scritto sugli
        schermi (05/10, schermi/conversazione.py). Chi è riconosciuto dalla voce la apre o
        la rinnova; un ospite o un'altra persona la chiude."""
        s, schermi = self.s, self.s.schermi
        if schermi is None or t.scritto is not None or self.speaker_ctx.is_enrolling:
            return
        o = s.instradamento.origine() or {}
        prof = s.registry.get(t.speaker_name) if t.speaker_name else None
        schermi.conversazioni.voce(
            getattr(prof, "id", None), self.speaker_ctx.identified_by,
            stanza=o.get("stanza") or schermi.stanza_predefinita or None,
            satellite=o.get("satellite"), locale=s.satelliti is None,
            chiave=self.corsia.chiave_schermi)

    # ── fase 6: registrazione della voce e nome del primo utente ──
    def _arruolamento(self, t):
        """Una frase della registrazione della voce (o il suo annullo)."""
        s, cfg, speaker_ctx, speaker = self.s, self.s.cfg, self.speaker_ctx, self.speaker
        if not speaker_ctx.is_enrolling:
            return None
        text = t.text
        self.rec["esito"] = "arruolamento"
        enrolling_name = speaker_ctx.enrolling_name
        if re.match(r"\W*(annulla|basta|stop|lascia stare)\b", text, re.I):
            speaker_ctx.stop_enroll()
            speaker.say("Va bene, registrazione annullata.")
            speaker.wait()
            return _FINE
        # Anche qui le uscite valgono: il 26/09 «Calliope, esci» veniva preso come frase
        # di registrazione (troppo breve) e Calliope restava accesa. «Esci» annulla e
        # la addormenta, solo «spegniti» chiude il programma (01/10)
        how = exit_action(exit_request(text, cfg.wake_names, cfg.exit_names),
                          s.satelliti is not None)
        if how:
            return self._esci_dalla_registrazione(how)
        # Ogni frase della registrazione comincia con il mio nome: senza, la prima voce
        # che passava (TV, una persona nella stanza) diventava una frase di chi si
        # registra (analisi di sicurezza del 03/10). Regola sul nome, che il modello
        # non vede (principio 10)
        if find_wake_word(text, cfg.wake_names, 0.5) is None:
            self.rule("arruolamento_senza_nome")
            print(f"   [SPEAKER] frase senza il mio nome, non contata: «{text}»", flush=True)
            # Il promemoria una volta sola: con la TV accesa non si ripete a ogni frase
            if enrolling_name not in self.enroll_reminded:
                self.enroll_reminded.add(enrolling_name)
                speaker.say("Comincia la frase con il mio nome, così so che parli a me.")
                speaker.wait()
            return _FINE
        done = speaker_ctx.enroll_sample(t.audio, cfg.sample_rate, voiced_s=t.voiced_s)
        self._esito_registrazione(done, enrolling_name)
        return _FINE

    def _esci_dalla_registrazione(self, how):
        self.speaker_ctx.stop_enroll()
        self.rule("uscita_" + how)
        if how == "spegni":
            self.rec["esito"] = "uscita"
            self.s.turns.write(self.rec)
            self.speaker.say("Registrazione annullata. Mi spengo: a presto!")
            self.speaker.wait()
            return "esci"
        self.rec["esito"] = "dormi"
        if self.s.schermi is not None:
            self.s.schermi.conversazioni.chiudi(self.corsia.chiave_schermi)
        self.speaker.say("Registrazione annullata. " + (
            SPEGNI_SATELLITE_MSG if how == "spegni_satellite" else "Chiamami quando vuoi."))
        self.speaker.wait()
        self.brain.end_conversation()
        self.awake_until, self.last_question = 0.0, None
        return _FINE

    def _esito_registrazione(self, done, enrolling_name):
        speaker, speaker_ctx = self.speaker, self.speaker_ctx
        if done == "scaduto":
            speaker.say("La registrazione della voce è scaduta: se vuoi, chiedimela "
                        "di nuovo.")
            speaker.wait()
        elif done == "non_somiglia":
            speaker.say(f"Questa voce non somiglia a quella di {enrolling_name}: deve "
                        f"parlare {enrolling_name}. {speaker_ctx.enroll_prompt}")
            speaker.wait()
        elif done == "breve":
            speaker.say(f"Un po' più lunga, per favore. {speaker_ctx.enroll_prompt}")
            speaker.wait()
        elif done.startswith("altra_voce:"):
            other = done.split(":", 1)[1]
            speaker.say(f"Questa mi sembra la voce di {other}. Deve parlare "
                        f"{enrolling_name}: {speaker_ctx.enroll_prompt}")
            speaker.wait()
        elif done == "fatto":
            if self.s.attiva_minori():
                self.brain.rileggi_tool()        # mentions_tool rilegge i nomi dei tool
            speaker.say(f"Registrato {enrolling_name}. Ora ti riconosco.")
            # Se è Primo/Prima, chiedi subito se vuole dire il suo nome
            if enrolling_name in ("Primo", "Prima"):
                speaker.say("Vuoi dirmi il tuo nome?")
                speaker.wait()
                self.pending_real_name = enrolling_name
            else:
                speaker.wait()
        else:
            n = speaker_ctx.enroll_remaining
            speaker.say(f"Grazie. {'Ancora una' if n == 1 else f'Ancora {n}'}: "
                        f"{speaker_ctx.enroll_prompt}")
            speaker.wait()

    def _nome_reale(self, t):
        """Attesa del nome vero dopo l'arruolamento di Primo/Prima."""
        if not self.pending_real_name:
            return None
        speaker, text = self.speaker, t.text
        self.rec["esito"] = "nome"
        negative = re.match(r"\b(no|non|nessuno|basta)\b", text, re.I)
        if negative:
            speaker.say(f"Va bene, ti chiamerò {self.pending_real_name}.")
            self.pending_real_name = None
            speaker.wait()
            return _FINE
        # «Mi chiamo Dario» → «Dario», non «Mi Chiamo Dario» (rapporto del 01/10)
        name = said_name(text, self.s.cfg.wake_names)
        if name != text.strip().title().rstrip(".,!?;:"):
            self.rule("nome_detto")
        if len(name.split()) <= 5 and name:
            old = self.pending_real_name
            prof = self.s.registry.rename(old, name)
            if prof:
                self.speaker_ctx.current_speaker = name
                speaker.say(f"Ok, ti chiamerò {name}.")
            self.pending_real_name = None
            speaker.wait()
            return _FINE
        speaker.say("Non ho capito. Dimmi il tuo nome o 'no'.")
        speaker.wait()
        self.awake_until = time.monotonic() + self.s.cfg.followup_s
        return _FINE

    # ── fase 7: il nome (wake word) ──
    def _richiamo(self, t):
        """Wake word. Il nome si cerca anche durante la finestra di ascolto: «Calliope?» da
        solo è un richiamo e riceve il saluto, non va all'LLM (test del 24/09)."""
        if t.barged:
            return self._dopo_interruzione(t)
        if self.s.cfg.wake_word_enabled and t.scritto is None:
            return self._cerca_il_nome(t)
        return None

    def _dopo_interruzione(self, t):
        """Dopo un barge-in la frase comincia con il nome (e magari con la coda della voce di
        Calliope, se in cassa): vale ciò che segue il nome."""
        cfg = self.s.cfg
        self.rec["interruzione"] = True
        self._segna_conversazione(t)
        info = {}
        request = find_wake_word(t.text, cfg.wake_names, 0.5, info)
        t.text = request if request is not None else t.text
        if info.get("cortesia"):
            self.rule("cortesia_dopo_nome")
        # Solo una chiusura intera («basta», «ok grazie»): «Calliope, grazie, e domani
        # che tempo fa?» va al modello (01/10)
        if not t.text or is_stop(t.text, cfg.wake_names):
            print(f"Tu: {self.in_console(self.rec['testo'])}  (interruzione: resto in ascolto)")
            self.rec["esito"] = "interruzione"
            self.rule("stop_interruzione")
            self.brain.record_stop(t.text or "Basta.")
            self.awake_until = time.monotonic() + cfg.followup_s
            return _FINE
        return None

    def _cerca_il_nome(self, t):
        s, cfg, listener = self.s, self.s.cfg, self.listener
        text = t.text
        info = {}
        request = find_wake_word(text, cfg.wake_names, cfg.wake_match, info,
                                 start_only=cfg.wake_start_only)
        if s.wake is not None and listener.started_at > self.awake_until:
            # Svegliata dal modello acustico. Secondo stadio: il nome deve comparire
            # nel testo almeno a tolleranza larga, altrimenti serve un punteggio alto
            self.rec["risveglio"] = round(listener.wake_score, 2)
            if request is None:
                request = find_wake_word(text, cfg.wake_names, 0.5, info,
                                         start_only=cfg.wake_start_only)
            if request is None and info.get("fuori_posizione"):
                # Wake word comune («il computer è lento», wake_posizione: inizio): la
                # parola c'è ma non chiama nessuno, anche se il modello acustico è sicuro
                print("   (risveglio scartato: la parola non è un richiamo)")
                self.rule("wake_fuori_posizione")
                self.rec.update(esito="scartato", testo=None)
                return _FINE
            if request is None:
                if listener.wake_score < cfg.wake_confirm_score:
                    print(f"   (risveglio scartato: punteggio {listener.wake_score:.2f},"
                          f" nome non trascritto)")
                    self.rec.update(esito="scartato", testo=None)
                    return _FINE
                if solo_nome_acustico(text, t.voiced_s, cfg):
                    # Scatto sicuro su una frase vuota (allucinazione, eco del prompt) o breve
                    # quanto il nome: è il nome da solo, storpiato da Whisper. Il 06/10 sulla
                    # DGX «Computer» → «Come più tardi.» (0,76 s) andava al modello come
                    # domanda e due «Computer» trascritti vuoti non facevano niente
                    self.rule("nome_da_solo_acustico")
                    request = ""
                else:
                    request = text    # nome storpiato ma scatto sicuro: tutta la frase
        if request is None and listener.started_at > self.awake_until:
            print(f"   (ignorato: «{text}»)")
            self.rec["esito"] = "ignorato"
            # Privacy: una frase non rivolta a Calliope non si conserva, a meno che non
            # contenga qualcosa di simile al nome (possibile risveglio mancato, utile
            # per tarare la wake word). Il 24/09 finiva nel registro una conversazione
            # tra due persone.
            if find_wake_word(text, cfg.wake_names, 0.5) is None:
                self.rec["testo"] = None
            return _FINE
        self._segna_conversazione(t)                 # la frase è rivolta a Calliope
        if request == "":                            # ha detto solo "Calliope"
            return self._solo_il_nome(t)
        if listener.started_at > self.awake_until:   # svegliata ora: vale ciò che segue
            t.text = request
            if info.get("cortesia"):
                self.rule("cortesia_dopo_nome")
        # Wake word testuale: la frase è presa solo ora, con il nome trovato (o nella
        # finestra di ascolto)
        if s.suoni is not None and s.satelliti is None and s.wake is None:
            self.speaker.suono_ascolto(s.suoni, FINE)
        return None

    def _inizia_primo_utente(self, t):
        """Primo avvio: rileva il genere dalla voce e registra Primo o Prima."""
        cfg, speaker_ctx = self.s.cfg, self.speaker_ctx
        gender = estimate_gender(t.audio, cfg.sample_rate)
        title = "Prima" if gender == "f" else "Primo"
        speaker_ctx.start_enroll(title, admin=True)
        speaker_ctx.enroll_sample(t.audio, cfg.sample_rate, detect_gender=True,
                                  voiced_s=t.voiced_s)
        self.s.enroll_pending = False
        self.speaker.say(f"Ah, sei il mio {title}! Ancora "
                         f"{speaker_ctx.enroll_remaining} frasi per registrare la tua voce. "
                         f"{speaker_ctx.enroll_prompt}")

    def _solo_il_nome(self, t):
        """Il nome da solo («Calliope.», «Computer» e una pausa): il saluto breve, oppure,
        con i suoni di ascolto accesi (modalità startrek), di nuovo il suono d'inizio ascolto,
        come nella serie: nome, bip, comando. In tutti e due i casi la finestra d'ascolto si
        apre per followup_s; con i suoni, se nessuno parla, si chiude col suono di fine."""
        s, cfg = self.s, self.s.cfg
        print(f"Tu: {self.in_console(t.text) or '(il nome)'}")
        self.rec["esito"] = "saluto"
        suoni = (s.suoni if getattr(cfg, "suoni_ascolto", False)
                 and getattr(s.suoni, "attivi", True) else None)
        if s.enroll_pending:
            self._inizia_primo_utente(t)
        elif suoni is not None and hasattr(self.speaker, "suono"):
            # Il satellite ha già suonato inizio (allo scatto) e fine (frase presa): il
            # suono d'inizio di nuovo dice «ora ti ascolto» (06/10: dopo il bip di fine
            # Dario credeva che l'ascolto fosse chiuso)
            self.rule("nome_da_solo_suono")
            self.rec["risposta"] = "(suono d'inizio ascolto)"
            self.speaker.suono(suoni, INIZIO)
        elif t.speaker_name:
            self.speaker.say(f"Ciao {t.speaker_name}.")
        else:
            self.speaker.say("Sì?")
        self.speaker.wait()
        self.awake_until = time.monotonic() + cfg.followup_s
        if suoni is not None and not s.enroll_pending and hasattr(self.speaker, "suono"):
            self._fine_se_nessuno_parla(suoni, cfg.followup_s)
        return _FINE

    def _fine_se_nessuno_parla(self, suoni, dopo_s: float):
        """Il suono di fine ascolto alla chiusura della finestra, se nel frattempo non è
        stata presa nessuna frase (con una frase lo suona chi ha il microfono)."""
        if self._fine_attesa is not None:
            self._fine_attesa.cancel()
        prese = self.frasi_prese

        def chiudi():
            if self.frasi_prese == prese and time.monotonic() >= self.awake_until - 0.2:
                print("   (finestra d'ascolto chiusa: nessuno ha parlato)", flush=True)
                try:
                    self.speaker.suono(suoni, FINE)
                except Exception:  # noqa: BLE001 — un suono non ferma il ciclo
                    pass
        self._fine_attesa = threading.Timer(max(0.0, dopo_s), chiudi)
        self._fine_attesa.daemon = True
        self._fine_attesa.start()

    def _primo_avvio(self, t):
        """Se è il primo avvio e l'utente si è presentato (es. "Calliope, sono Mario"),
        avvia comunque l'arruolamento come Primo/Prima."""
        if not self.s.enroll_pending or t.scritto is not None:
            return None
        self.rec["esito"] = "arruolamento"
        self._inizia_primo_utente(t)
        self.speaker.wait()
        self.awake_until = time.monotonic() + self.s.cfg.followup_s
        return _FINE

    def _mostra_richiesta(self, t):
        self._segna_conversazione(t)     # senza wake word, o dopo il nome (una volta in più)
        cfg = self.s.cfg
        if t.scritto is not None:
            # «Calliope, che ore sono?» scritto: vale ciò che segue il nome, come a voce
            request = find_wake_word(t.text, cfg.wake_names, cfg.wake_match)
            if request:
                t.text = request
            # Codici, IBAN ed email scritti non vanno nel terminale né nel registro dei turni
            self.rec["testo"] = oscura(t.text)
            print(f"\n✍  Scritto dallo schermo «{t.scritto.get('schermo')}»: "
                  f"{self.in_console(oscura(t.text))}"
                  + (f"  ({t.speaker_name})" if t.speaker_name else "  (ospite)"))
        else:
            print(f"Tu: {self.in_console(t.text)}  [STT {time.perf_counter() - t.t0:.2f}s]"
                  + (f"  ({t.speaker_name})" if t.speaker_name else ""))
        return None

    # ── fase 8: comandi fissi (uscite, cortesia), orari dei minori ──
    def _addormentati(self, frase: str):
        """«Esci»: lo scritto si spegne subito, la conversazione si chiude."""
        if self.s.schermi is not None:
            self.s.schermi.conversazioni.chiudi(self.corsia.chiave_schermi)
        self.speaker.say(frase)
        self.speaker.wait()
        self.brain.end_conversation()
        self.awake_until, self.last_question = 0.0, None
        return _FINE

    def _uscite(self, t):
        """Uscita: un comando Python, deterministico e senza un turno LLM, ma solo sulla frase
        intera (wakeword.exit_intent). Dal 01/10 «esci», «arrivederci», «addio» la
        addormentano (torna ad aspettare il nome, la conversazione si chiude); solo
        «spegniti», «spegni Calliope», «chiudi il programma» chiudono il processo, che a voce
        non si riaccende. Prima «Calliope, speni taverna» (01/10) la spegneva. Con l'audio di
        un satellite (02/10) «spegniti» addormenta soltanto: il server sulla DGX è un servizio
        che a voce non si riaccende (exit_action, uscita_spegni_satellite)."""
        s, cfg, text = self.s, self.s.cfg, t.text
        how = exit_action(exit_request(text, cfg.wake_names, cfg.exit_names),
                          s.satelliti is not None)
        if how == "spegni_satellite":
            print(f"Tu: {self.in_console(text)}  (da un satellite: torno a dormire, il server "
                  f"resta acceso)")
            self.rec["esito"] = "dormi"
            self.rule("uscita_spegni_satellite")
            return self._addormentati(SPEGNI_SATELLITE_MSG)
        if how == "spegni":
            self.rec["esito"] = "uscita"
            self.rule("uscita_spegni")
            s.turns.write(self.rec)
            self.speaker.say("Mi spengo. A presto!")
            self.speaker.wait()
            return "esci"
        if how == "dormi":
            print(f"Tu: {self.in_console(text)}  (torno a dormire)")
            self.rec["esito"] = "dormi"
            self.rule("uscita_dormi")
            return self._addormentati("A presto!")
        # «Ricominciamo», «nuova conversazione» (05/10): la conversazione si chiude come con
        # «esci» (archiviata, riassunto in secondo piano) ma Calliope resta in ascolto. Solo
        # la frase intera (wakeword.nuova_conversazione)
        if nuova_conversazione(text, cfg.wake_names):
            print(f"Tu: {self.in_console(text)}  (conversazione nuova)")
            self.rec["esito"] = "nuova_conversazione"
            self.rule("nuova_conversazione")
            self.brain.end_conversation("nuova")
            self.speaker.say("Va bene, ricominciamo da capo.")
            self.speaker.wait()
            self.awake_until, self.last_question = time.monotonic() + cfg.followup_s, None
            return _FINE
        return None

    def _chiusure(self, t):
        """«Calliope, stop», «grazie», «va bene così» quando non sta parlando: niente LLM (che
        diceva «Prego, sono qui per aiutarti»). Solo se tutta la frase è una chiusura: «Ok,
        aprilo», «Ferma la musica» vanno al modello. E non se Calliope ha appena chiesto un
        consenso («Lo apro?»): lì «grazie» può voler dire sì, e decide il modello con l'azione
        in sospeso davanti (il 01/10 «Grazie.» dopo «Lo apro?» era zittito).

        Cortesia (05/10): «grazie», «ok, grazie», «perfetto» ricevono una frase breve già
        sintetizzata (calliope/cortesia.py), nel tono di chi parla. La conversazione resta
        (storia e riferimenti: «grazie» a metà non la chiude), ma la finestra di follow-up si
        chiude: è la fine dello scambio, e il parlato della stanza dopo un «grazie» non va
        trascritto. «Ok», «va bene» dopo una domanda di Calliope sono una risposta: vanno al
        modello."""
        s, cfg, brain, text = self.s, self.s.cfg, self.brain, t.text
        forma = closing_kind(text, cfg.wake_names) if not brain.has_pending() else None
        if forma == "conferma" and brain.ultima_domanda():
            forma = None
        if forma in ("grazie", "conferma"):
            prof = s.registry.get(t.speaker_name) if t.speaker_name else None
            frase = s.cortesia.risposta(forma, getattr(prof, "preferred_tone", None), cfg.tono)
            print(f"Tu: {self.in_console(text)}")
            print(f"{cfg.name}: {frase}")
            self.rec["esito"] = "cortesia"
            self.rec["risposta"] = frase
            self.rule("cortesia")
            self.speaker.say_cached(frase)
            self.speaker.wait()
            brain.record_courtesy(text, frase)
            self.awake_until = 0.0
            return _FINE
        if forma == "silenzio":
            print(f"Tu: {self.in_console(text)}  (niente da fermare: resto in ascolto)")
            self.rec["esito"] = "stop"
            self.rule("stop")
            self.awake_until = time.monotonic() + cfg.followup_s
            return _FINE
        return None

    def _fuori_orario(self, t):
        """Orari in cui Calliope non risponde a un minore (05/10, decisi dai tutori): si
        risponde solo a chi è in pericolo."""
        s = self.s
        t.prof_turno = s.registry.get(t.speaker_name) if t.speaker_name else None
        orario = minori.fuori_orario(t.prof_turno) if t.prof_turno is not None else None
        if not orario:
            return None
        self.rec["esito"] = "fuori_orario"
        self.rule("minore_fuori_orario")
        g = s.guardiano.giudica_domanda(t.text) if s.guardiano is not None else None
        if g is not None and g.esito == guardia.PERICOLO:
            self.proteggi(t.prof_turno, g.categorie, self.rec)
            self.speaker.say(guardia.PROTEZIONE)
        else:
            self.speaker.say(minori.frase_fuori_orario(t.prof_turno, orario))
        self.speaker.wait()
        return _FINE

    # ── fase 9: contesto, foto e file del turno ──
    def _contesto_e_allegati(self, t):
        """«Approfondisci», «cerca meglio», «sei sicura?»: la domanda precedente si cerca nella
        biblioteca dal codice (il modello da solo spesso risponde a memoria; va bene, e la
        fonte la si chiede quando serve: scelta del 26/09). Poi le foto e i file del turno."""
        s = self.s
        if (s.biblioteca and self.last_question and len(t.text.split()) <= 6
                and DEEPEN_WORDS.search(t.text)):
            t.context = biblioteca_contesto(self.tool_ctx, self.last_question)
            self.rec["approfondimento"] = self.last_question
            self.rule("approfondisci")
            print(f"   [BIBLIOTECA] approfondisco «{self.last_question}»", flush=True)
        self._foto_e_file(t)
        return None

    def _foto_e_file(self, t):
        """Foto di questo turno (05/10): quelle scritte con la frase e quelle mandate poco fa
        senza domanda dalla stessa persona. Mai per gli ospiti. Solo in memoria: nel registro
        dei turni numero, fonte e dimensione. I file allegati (05/10, calliope/allegati.py)
        come le foto."""
        s, cfg, brain, scritto = self.s, self.s.cfg, self.brain, t.scritto
        foto = list(scritto.get("immagini") or []) if scritto is not None else []
        files = list(scritto.get("allegati") or []) if scritto is not None else []
        prof_foto = s.registry.get(t.speaker_name) if t.speaker_name else None
        if self.speaker_ctx.current_level == "ospite" or prof_foto is None:
            foto, files = [], []
        else:
            for x in s.foto_attesa.prendi(prof_foto.id):
                (foto if isinstance(x, Immagine) else files).append(x)
        for att in files:
            # Audio: trascritto qui con il Whisper della voce, come contenuto del file. Mai
            # dalla pipeline della voce (wake word, regole, chi parla, conferme): è un dato
            if att.da_trascrivere:
                t_a = time.perf_counter()
                allegati_mod.trascrivi(att, s.stt, float(getattr(cfg, "allegati_audio_max_s",
                                                                 180.0)))
                print(f"   [ALLEGATI] audio trascritto in {time.perf_counter() - t_a:.2f} s",
                      flush=True)
            # Le pagine scansionate di un PDF vanno al modello come foto (se le vede)
            if att.pagine_img and brain.vede_immagini():
                foto += att.pagine_img
            att.pagine_img = []
        if files:
            self.rec["allegati"] = [a.per_registro() for a in files]
            self.rule("allegato_in_ingresso")
            print(f"   [ALLEGATI] {len(files)} file con la domanda ("
                  + ", ".join(f"{a.categoria} {round(a.dimensione / 1024)} kB" for a in files)
                  + ")", flush=True)
        if foto and not brain.vede_immagini():
            print("   [IMMAGINI] il modello della voce non vede le immagini", flush=True)
            t.context = ((t.context + "\n") if t.context else "") + FOTO_NON_VISTA
            foto = []
        if foto:
            self.rec["immagini"] = [i.per_registro() for i in foto]
            self.rule("immagine_in_ingresso")
            print(f"   [IMMAGINI] {len(foto)} foto con la domanda ("
                  + ", ".join(f"{i.larghezza}×{i.altezza}" for i in foto) + ")", flush=True)
        t.foto, t.files = foto, files

    # ── fase 10: la risposta ──
    def _prepara_risposta(self, t):
        """Prima della risposta: la voce è occupata (arbitro, compressione), il guardiano per
        minori e ospiti, la frase d'attesa dei tool lenti, la compressione dura."""
        s, cfg, brain = self.s, self.s.cfg, self.brain
        print(f"{cfg.name}: ", end="", flush=True)
        if s.lavori is not None:
            s.lavori.arbitro.voce_occupata()     # anche senza VAD (frase dopo un barge-in)
        if s.compressore is not None:
            s.compressore.voce_occupata()
        t.level = self.speaker_ctx.current_level
        # Minori e ospiti: il guardiano sulle frasi (gli adulti riconosciuti non pagano niente)
        t.minore_turno = t.prof_turno is not None and minori.e_minore(t.prof_turno)
        t.usa_guardia = s.guardiano is not None and (t.minore_turno or (
            t.level == "ospite" and cfg.guardiano_ospiti))
        t.esito_g = guardia.Esito()
        # Ciò che dice con dati non fidati di mezzo (06/10, calliope/riferire.py): ogni frase
        # si controlla prima di dirla; con la conversazione pulita non costa niente
        t.esito_u = riferire.Esito()
        self.rec.update(esito="risposta", richiesta=t.text)
        t.was_enrolling = self.speaker_ctx.is_enrolling
        self.speaker.start_turn()
        rec, t0, speaker = self.rec, t.t0, self.speaker

        def announce(phrase):
            # Tool lento: la frase d'attesa parte subito e copre la seconda passata
            rec["primo_suono_s"] = round(time.perf_counter() - t0, 2)
            print(f"[attesa {rec['primo_suono_s']:.2f}s] {phrase} ", end="", flush=True)
            speaker.say_cached(phrase)
        brain.on_tool_start = announce
        # Soglia dura del contesto (05/10, calliope/compressione.py): l'ultima risposta ha
        # riempito più del 90 % della finestra e la compressione in secondo piano non è
        # bastata: si comprime adesso, con una frase d'attesa breve
        if s.compressore is not None and s.compressore.soglia(
                getattr(brain, "uso_precedente", None)) == "dura":
            announce(FRASE_DURA)
            self.rule("contesto_dura")
            try:
                s.compressore.comprimi_ora(brain)
            except Exception as e:  # noqa: BLE001 — si risponde comunque
                print(f"   [CONTESTO] compressione non riuscita: {type(e).__name__}: {e}",
                      flush=True)
        if t.context:
            announce("Controllo nella biblioteca.")

    def _testo_per_guardia(self, t) -> str:
        """La frase da far giudicare a guardiano e rilevatore di pericolo. Un pezzo detto da un
        minore mentre Calliope rispondeva al suo pezzo di prima (barge-in, entro
        `UNIONE_PEZZI_S`) è la stessa frase spezzata: si giudica unita (prova e2e del 06/10,
        «un signore al parco mi ha detto di andare a casa sua» | «e di non dirlo alla
        mamma»: la seconda metà da sola può non sembrare un pericolo). Solo per il giudizio:
        al modello e nella storia va la frase com'è. Vincolo di sicurezza (principio 10),
        regola `guardia_pezzi_uniti`; casi contrari: un'altra persona, una frase non
        interrotta, troppo tempo dopo."""
        chi, ora = t.speaker_name, time.monotonic()
        prima = self.ultima_frase_guardia
        testo = t.text
        if (t.barged and t.minore_turno and chi and prima and prima[0] == chi
                and ora - prima[2] <= UNIONE_PEZZI_S):
            testo = f"{prima[1]} {t.text}"[-1500:]
            self.rule("guardia_pezzi_uniti")
        self.ultima_frase_guardia = (chi, testo, ora)
        return testo

    def _protezione_dopo(self, t):
        """La frase di protezione di un minore (o di un ospite) in pericolo deve arrivare per
        intero, con il 19696 e il consiglio di parlarne con un adulto (prova e2e del 06/10).
        Se il nome l'ha interrotta prima della fine si ripete per intero alla fine del turno
        dopo della stessa persona, entro `RIPETI_PROTEZIONE_S` (se quel turno non l'ha già
        detta lui). Regole `protezione_interrotta` e `protezione_ripetuta`."""
        interrotta = bool(t.watch.get("seed"))
        dette = list(getattr(self.speaker, "played", None) or [])
        chi, ora = t.speaker_name, time.monotonic()
        if t.protezione and t.protezione in dette:
            self.protezione_da_ripetere = None          # arrivata per intero
            return
        if t.protezione and interrotta:
            self.protezione_da_ripetere = (chi, ora, t.protezione)
            self.rule("protezione_interrotta")
            return
        da_ripetere = self.protezione_da_ripetere
        if da_ripetere is None:
            return
        if ora - da_ripetere[1] > RIPETI_PROTEZIONE_S:
            self.protezione_da_ripetere = None
            return
        if da_ripetere[0] != chi or interrotta:
            return                                      # aspetta un turno suo, finito
        self.protezione_da_ripetere = None
        self.rule("protezione_ripetuta")
        print("   [GUARDIANO] protezione interrotta: la ripeto per intero", flush=True)
        self.speaker.say(da_ripetere[2])
        self.speaker.wait()

    def _ascolta_il_nome(self, t):
        """Barge-in: mentre parla, un thread ascolta solo la wake word (e la voce di chi è
        registrato, se il microfono non sente l'eco)."""
        s, speaker = self.s, self.speaker
        t.watch_stop, t.watch, t.watcher = threading.Event(), {}, None
        if not s.barge_in or getattr(speaker, "muto", False):
            return
        wake, barge_voice, watch, watch_stop = s.wake, s.barge_voice, t.watch, t.watch_stop

        def watch_name():
            watch["seed"] = self.listener.watch_for_name(
                wake, watch_stop, speaker.saying_name,
                voice_ok=self.known_voice if barge_voice else None)
            if watch["seed"]:
                speaker.interrupt()
        t.watcher = threading.Thread(target=watch_name, daemon=True)
        t.watcher.start()

    def _rispondi(self, t):
        """Il modello risponde in streaming, frase per frase verso la voce (con i controlli
        di ciò che dice e, per minori e ospiti, il guardiano)."""
        s, cfg, brain, speaker = self.s, self.s.cfg, self.brain, self.speaker
        self._prepara_risposta(t)
        self._ascolta_il_nome(t)
        t.first, t.said = True, []
        try:
            if t.foto and s.schermi is not None:
                # Le miniature agli schermi personali di chi parla (dopo l'identità)
                brain.manda_schede([schede_foto.foto(i) for i in t.foto], "foto")
            if t.files and s.schermi is not None:
                brain.manda_schede([schede_foto.allegato(a) for a in t.files], "allegato")
            # I file sono dati non fidati: entrano dalla porta unica (calliope/provenienza.py)
            for att in t.files:
                brain.allega_non_fidato(att.fonte_dato, att, att.nome)
            # Al più conversazioni_parallele risposte del modello insieme (06/10, corsie.py):
            # oltre, una frase già pronta e la coda in ordine d'arrivo
            attesa_coda = self.corsia.entra_llm(lambda: (
                self.rule("coda_risposte"), print("[in coda] ", end="", flush=True),
                speaker.say_cached(corsie.FRASE_CODA)))
            if attesa_coda:
                self.rec["coda_s"] = round(attesa_coda, 2)
            # Per un minore le schede dei tool aspettano il giudizio sulla domanda (Q3
            # dell'analisi del 06/10): il guardiano non le giudica, e sullo schermo personale
            # comparivano prima che la voce rifiutasse
            trattieni = t.usa_guardia and t.minore_turno
            brain.trattieni_schede = [] if trattieni else None
            brain.schede_attesa_ms = None
            incerte = self._parole_incerte(t)
            frasi = split_sentences(brain.stream_reply(
                t.text, t.level, context=t.context, **({"immagini": t.foto} if t.foto else {}),
                **({"incerte": incerte} if incerte else {})))
            if cfg.rete("riferire"):
                frasi = riferire.filtra(brain, frasi, t.text, t.esito_u)
            if t.usa_guardia:
                # Il guardiano (05/10): domanda e ogni frase prima della voce. Con un file
                # allegato da un minore giudica anche il testo estratto (dato, 05/10)
                frasi = guardia.filtra(s.guardiano, frasi,
                                       domanda_guardia(self._testo_per_guardia(t), t.files),
                                       t.minore_turno, t.esito_g,
                                       None if t.minore_turno else guardia.MODERATO,
                                       al_giudizio=brain.rilascia_schede if trattieni else None)
            for sentence in frasi:
                if speaker.interrupted:
                    break          # chiude lo stream dell'LLM: Ollama smette di generare
                protezione = sentence in (guardia.PROTEZIONE, guardia.PROTEZIONE_OSPITE)
                sentence = self._frase_da_dire(t, sentence)
                if sentence:
                    if protezione:
                        # Da qui la voce di chi parla non la interrompe (known_voice)
                        self.protezione_in_corso, t.protezione = True, sentence
                    self._di_frase(t, sentence)
        except Exception as e:
            print(f"\n[LLM] Errore: {e}")
            self.rec["errore"] = str(e)
            speaker.say("Scusa, ho avuto un problema a rispondere.")
        finally:
            # Nessun giudizio sulla domanda (risposta interrotta o errore): le schede
            # trattenute non partono
            if getattr(brain, "trattieni_schede", None) is not None:
                brain.rilascia_schede(False)
        self.corsia.esci_llm()          # il modello ha finito: il posto a chi aspetta

    def _frase_da_dire(self, t, sentence: str) -> str:
        """Una frase del modello pronta per la voce ("" = non si dice)."""
        cfg, brain = self.s.cfg, self.brain
        sentence = brain.strip_tool_mentions(sentence)
        # Prima della pulizia: clean_for_speech toglie «_» e il nome del tool non
        # si riconosceva più («Uso bibliotecacerca» detto ad alta voce, 01/10)
        if brain.mentions_tool(sentence) and cfg.rete("nome_tool_parlato"):
            parlata = brain.speak_tool_names(sentence)
            if parlata is None:
                print(f"({sentence!r}: annuncia un tool, non la dico) ", end="", flush=True)
                self.rule("annuncio_tool_taciuto")
                return ""
            self.rule("nome_tool_parlato")
            sentence = parlata
        sentence = clean_for_speech(sentence)
        if not re.search(r"[^\W_]", sentence or ""):
            # Solo punteggiatura («…», «.»): non si dice (06/10); Brain la tratta come una
            # risposta vuota (regola risposta_solo_punteggiatura)
            return ""
        # «secondo Wikipedia» solo se in questo turno ha davvero consultato la
        # biblioteca: il 26/09 lo diceva anche rispondendo a memoria (Po, Garda)
        if (not t.context and cfg.rete("citazione_tolta")
                and not any(x["nome"] in ("biblioteca_cerca", "web_cerca")
                            for x in brain.last_tools)):
            cleaned = strip_false_citation(sentence)
            if cleaned != sentence:
                self.rule("citazione_tolta")
            sentence = cleaned
        return sentence

    def _di_frase(self, t, sentence: str):
        rec = self.rec
        if t.first:
            rec["prima_frase_s"] = round(time.perf_counter() - t.t0, 2)
            # Primo suono = frase d'attesa se c'è stata, altrimenti la prima frase
            rec.setdefault("primo_suono_s", rec["prima_frase_s"])
            # Dalla fine della voce (06/10, P4): comprende il silenzio con cui il VAD
            # chiude la frase, cioè la latenza che si sente (calliope/latenza.py)
            fine_voce = getattr(self.listener, "ended_at", 0.0) or 0.0
            if t.scritto is None and 0 < fine_voce <= t.t0_mono:
                rec["fine_parlato_s"] = round(rec["prima_frase_s"] + t.t0_mono - fine_voce, 2)
            print(f"[prima frase {rec['prima_frase_s']:.2f}s] ", end="")
            t.first = False
        print(self.in_console(oscura(sentence) if t.scritto is not None else sentence,
                              risposta=True), end=" ", flush=True)
        self.speaker.say(sentence)
        t.said.append(sentence)

    # ── fase 11: dopo la risposta ──
    def _registra_risposta(self, t):
        """La risposta nel registro dei turni: ciò che è stato detto, i tool, le regole, i
        controlli di ciò che dice e del guardiano, la compressione, il contesto; tolti i dati
        che non devono restare (riservati, codici, frase di sfida)."""
        brain, rec = self.brain, self.rec
        rec.update(risposta=" ".join(t.said), tool=brain.last_tools)
        if t.files:
            # Di nuovo dopo la risposta: il numero del file lo dà la conversazione (Brain)
            rec["allegati"] = [a.per_registro() for a in t.files]
        self._registra_controlli(t)
        # La frase come l'ha capita il modello (variante B2, stt_incerte_riscrivi): prima, dopo
        # e se è valsa per la politica e la storia (stt_correzione.accettabile)
        if getattr(brain, "last_capito", None):
            rec["stt_capito"] = dict(brain.last_capito)
        # Il modello ha finito: una compressione in secondo piano può partire (soglia
        # morbida), e si ferma se qualcuno ricomincia a parlare
        self._compressione_dopo(t)
        self._oscura_registro(t)
        for name in brain.rules_fired():
            self.rule(name)
        print()
        self._uso_del_contesto(t)
        if t.scritto is not None:
            # Anche scritta, sullo schermo da cui è arrivata la frase: chi scrive spesso non
            # può ascoltare (04/10). Prima di aspettare la voce: si legge subito
            rec["risposta_scritta"] = self.s.instradamento.risposta_scritta(
                t.scritto, t.text, " ".join(t.said))

    def _registra_controlli(self, t):
        """Ciò che i controlli dell'uscita (riferire.py) e il guardiano hanno fermato."""
        brain, rec, esito_u, esito_g = self.brain, self.rec, t.esito_u, t.esito_g
        if esito_u.fermate or esito_u.fonte_aggiunta:
            rec["uscita"] = {"fermate": [f[0] for f in esito_u.fermate],
                             "fonti": sorted({f[1] for f in esito_u.fermate if f[1]}),
                             "fonte_aggiunta": esito_u.fonte_aggiunta}
            for regola in dict.fromkeys(f[0] for f in esito_u.fermate):
                self.rule(regola)
            if esito_u.fonte_aggiunta:
                self.rule("uscita_fonte_aggiunta")
            if esito_u.fermate and not (t.usa_guardia and esito_g.fermata):
                # La storia tiene solo ciò che è stato detto: il modello non deve credere di
                # aver dato l'indicazione (né ripeterla al turno dopo)
                guardia.correggi_storia(brain, esito_u.detto)
                try:
                    brain.salva_conversazione()
                except Exception:  # noqa: BLE001
                    pass
        if not t.usa_guardia:
            return
        ms_g = [m for m, _ in esito_g.frasi]
        dom = esito_g.domanda
        rec["guardiano"] = {"frasi": len(ms_g), "ms": ms_g[:6],
                            "domanda_ms": getattr(dom, "ms", None),
                            # Esito di guardiano e rilevatore sulla domanda (Q3 dell'analisi
                            # del 06/10): un rilevatore guasto o scaduto ora si vede
                            "domanda": getattr(dom, "esito", None),
                            **({"pericolo": dom.pericolo, "pericolo_ms": dom.pericolo_ms}
                               if getattr(dom, "pericolo", "") else {}),
                            **({"guasto": True} if dom is not None and dom.guasto() else {}),
                            **({"schede_attesa_ms": brain.schede_attesa_ms}
                               if getattr(brain, "schede_attesa_ms", None) is not None
                               else {}),
                            **({"fermata": esito_g.fermata,
                                "categorie": list(esito_g.categorie)}
                               if esito_g.fermata else {})}
        if esito_g.fermata:
            guardia.correggi_storia(brain, esito_g.detto)
            print(f"\n   [GUARDIANO] risposta fermata: {esito_g.fermata} "
                  f"{list(esito_g.categorie)}", flush=True)
            if esito_g.fermata == guardia.PERICOLO:
                self.proteggi(t.prof_turno if t.minore_turno else None, esito_g.categorie, rec)
            else:
                self.rule("guardiano_" + esito_g.fermata)
                if t.minore_turno:
                    rec["testo"] = rec["richiesta"] = None
            rec["risposta"] = " ".join(esito_g.detto)

    def _compressione_dopo(self, t):
        brain, compressore = self.brain, self.s.compressore
        if getattr(brain, "last_compressione", None):
            self.rec["compressione"] = dict(brain.last_compressione)
        brain.uso_precedente = getattr(brain, "last_context", None)
        if compressore is None:
            return
        compressore.voce_libera()
        if compressore.soglia(brain.uso_precedente) is not None:
            try:
                if compressore.avvia(brain):
                    self.rec["compressione_avviata"] = True
            except Exception as e:  # noqa: BLE001
                print(f"   [CONTESTO] compressione non avviata: {type(e).__name__}: {e}",
                      flush=True)

    def _oscura_registro(self, t):
        brain, rec, scritto = self.brain, self.rec, t.scritto
        if getattr(brain, "last_private", False):
            # Documenti di casa (tool riservati): la risposta contiene i loro dati, e nel
            # registro dei turni restano solo i nomi dei tool
            rec.update(risposta=None, riservato=True)
        # Il codice di abbinamento di uno schermo non resta nel registro dei turni
        for key in ("testo", "richiesta", "risposta"):
            rec[key] = brain.redact(rec.get(key))
            if scritto is not None:
                rec[key] = oscura(rec[key])
        if scritto is not None:
            rec["tool"] = oscura_tutto(rec.get("tool"))
        # Frase di sfida (04/10, conferme.py): le parole chieste o ripetute non servono nel
        # registro dei turni, bastano le regole `sfida_voce` (chiesta) e `sfida_risposta`
        if {"sfida_voce", "sfida_risposta"} & set(brain.rules_fired()):
            if getattr(brain, "last_sfida", False):
                rec["testo"] = "(frase di conferma)"
            if isinstance(rec.get("risposta"), str):
                rec["risposta"] = re.sub(r"([Rr]ipeti:).*", r"\1 …", rec["risposta"])
        for chiave in ("stt_corretta", "stt_capito"):
            if chiave not in rec:
                continue
            # Prima e dopo della correzione seguono il testo: tolti se il testo non resta
            # (ospiti, minori fermati, frase di conferma), ripuliti come lui altrimenti
            if rec.get("testo") is None or rec.get("testo") == "(frase di conferma)":
                rec[chiave] = {k: v for k, v in rec[chiave].items()
                               if k not in ("prima", "dopo")}
            else:
                rec[chiave] = {k: (brain.redact(v) if k in ("prima", "dopo") else v)
                               for k, v in rec[chiave].items()}

    def _uso_del_contesto(self, t):
        """Uso del contesto, dai token veri del motore (05/10, calliope/contesto.py): nel
        registro dei turni, in console e come barra sullo schermo personale di chi parla."""
        brain, schermi = self.brain, self.s.schermi
        uso_ctx = getattr(brain, "last_context", None)
        # Rilettura del prompt della prima passata (06/10, P4): oltre ~1 s la cache del
        # prefisso non è servita (riavvio, altra conversazione)
        if getattr(brain, "last_lettura_s", None) is not None:
            self.rec["lettura_s"] = brain.last_lettura_s
        if not uso_ctx:
            return
        self.rec["contesto"] = dict(uso_ctx)
        print(f"   {contesto.riga(uso_ctx)}", flush=True)
        if schermi is not None:
            try:
                schermi.contesto(schermi.mittente(self.tool_ctx), uso_ctx)
            except Exception:  # noqa: BLE001 — la barra non deve fermare il turno
                pass

    def _prima_voce(self, t):
        """Quando la risposta ha cominciato a sentirsi, da `t0` come `prima_frase_s` (06/10,
        prova e2e: la voce arrivava 0,2–0,5 s dopo `prima_frase_s`, p90 1–2,8 s, per sintesi,
        rete e riproduzione sul satellite). La dice il satellite (`suona`); con le casse
        locali il primo blocco scritto più il ritardo dell'uscita. Anche la frase d'attesa:
        è la prima voce che si sente."""
        try:
            tv = self.speaker.prima_voce()
        except Exception:  # noqa: BLE001 — una misura non ferma il turno
            tv = None
        if self.rec is not None and tv is not None and t.t0_mono and tv >= t.t0_mono:
            self.rec["prima_voce_s"] = round(tv - t.t0_mono, 2)

    def _dopo_la_risposta(self, t):
        """Finita la voce: interruzione, ricerca promessa, avvisi ai tutori, registrazione
        appena chiesta, finestra di ascolto."""
        cfg, speaker, speaker_ctx = self.s.cfg, self.speaker, self.speaker_ctx
        speaker.wait()
        self._prima_voce(t)
        if t.watcher:
            t.watch_stop.set()
            t.watcher.join()
        self.protezione_in_corso = False
        if t.watch.get("seed"):
            # Interrotta: nella storia solo le frasi pronunciate per intero; si ascolta
            # subito, partendo dall'audio che contiene il nome
            self.brain.record_interruption(speaker.played)
            self.rec.update(interrotta=True,
                            risposta=None if getattr(self.brain, "last_private", False)
                            else " ".join(speaker.played))
            self.barge_seed = t.watch["seed"]
        self._protezione_dopo(t)
        self._ricerca_promessa(t)
        if not t.context:
            self.last_question = t.text
        if not t.watch.get("seed"):
            self.avvisi_ai_tutori(t.speaker_name)
        speaker.start_turn()     # azzera un'interruzione arrivata a risposta finita
        if speaker_ctx.is_enrolling and not t.was_enrolling:
            self.enroll_reminded.discard(speaker_ctx.enrolling_name)
            speaker.say(f"{speaker_ctx.enrolling_name}, adesso parla tu, e comincia ogni "
                        f"frase con il mio nome: ti chiederò {speaker_ctx.enroll_needed} "
                        f"frasi, una alla volta. {speaker_ctx.enroll_prompt}")
            speaker.wait()
        self.awake_until = time.monotonic() + cfg.followup_s

    def _ricerca_promessa(self, t):
        """Ricerca promessa e non fatta («devo fare una ricerca», 26/09): la si fa subito.
        Non su una domanda («Lo cerco nella biblioteca?»): lì decide la persona."""
        s, cfg, brain, speaker = self.s, self.s.cfg, self.brain, self.speaker
        detto = " ".join(t.said)
        promised = (s.biblioteca and cfg.rete("ricerca_promessa") and not t.watch.get("seed")
                    and not t.context
                    and not any(x["nome"] == "biblioteca_cerca" for x in brain.last_tools)
                    and SEARCH_PROMISE.search(detto)
                    and not detto.rstrip().endswith("?"))
        if not promised:
            return
        self.rule("ricerca_promessa")
        print("   [BIBLIOTECA] aveva promesso una ricerca: la faccio", flush=True)
        speaker.start_turn()
        speaker.say_cached("Controllo nella biblioteca.")
        extra = biblioteca_contesto(self.tool_ctx, t.text)
        self.corsia.entra_llm()
        try:
            # Una continuazione, non un «Cerca pure.» finto dell'utente nella storia
            for sentence in split_sentences(brain.stream_continuation(t.level, context=extra)):
                sentence = brain.strip_tool_mentions(sentence)
                sentence = brain.speak_tool_names(sentence)
                if sentence is None:
                    continue
                sentence = clean_for_speech(sentence)
                if sentence:
                    print(self.in_console(oscura(sentence) if t.scritto is not None
                                          else sentence, risposta=True), end=" ", flush=True)
                    speaker.say(sentence)
                    t.said.append(sentence)
        except Exception as e:
            print(f"\n[LLM] Errore: {e}")
        self.corsia.esci_llm()
        print()
        speaker.wait()
        self.rec.update(risposta=" ".join(t.said), ricerca_promessa=True)
        if t.scritto is not None:
            s.instradamento.risposta_scritta(t.scritto, t.text, " ".join(t.said))
