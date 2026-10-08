"""
Calliope — ciclo principale.

Pipeline: microfono → Silero VAD → wake word acustica → faster-whisper → Ollama
(streaming, tool) → Piper → altoparlanti. Dopo una risposta resta in ascolto per qualche
secondo, così si può continuare la conversazione senza richiamarla. Mentre parla ascolta
solo la wake word (barge-in), e la voce di chi è registrato se il microfono non sente
l'eco. Il ciclo è rimasto com'era in calliope.py fino al 26/09/2026 (roadmap 2: divisione
in package); la configurazione arriva da calliope.yaml tramite load_config().

Con `audio_modo: satellite` (02/10/2026) microfono, VAD, wake word e casse sono di un
satellite in rete (calliope/satellite/): `AscoltoRemoto` e `UscitaRemota` hanno lo stesso
contratto di Listener e dell'uscita di Speaker, e il ciclo resta lo stesso.

Qui si preparano i servizi; il ciclo della voce è in calliope/ciclo.py (`Ciclo`, dal 06/10:
P8 dell'analisi complessiva). Con i satelliti tutti insieme (calliope/corsie.py) ogni
satellite ha la sua **corsia**, cioè un suo `Ciclo` con i suoi oggetti (ascolto, voce, chi
parla, Brain) e il suo stato (finestra di ascolto, turno), in un thread per satellite. Le
conversazioni sono per persona (`corsie.RegistroConversazioni`), anche con l'audio di questo
computer (una corsia sola, il thread principale).
"""
import atexit
import dataclasses
import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import sounddevice as sd

from . import attrito, capacita, contesto, corsie, latenza, minori
from . import guardiano as guardia
from .agenda import Agenda
from .agenti import load_agenti
from .archivio import load_archivio
from .audio import Listener
from .biblioteca import load_biblioteca
from .brain import Brain, RichiestaRifiutata
# Il ciclo della voce (06/10, P8): ERRORI_*, domanda_guardia e save_debug_audio restano
# importabili da qui (prove, documenti)
from .ciclo import (ERRORI_FINESTRA_S, ERRORI_MAX, Ciclo, Servizi,  # noqa: F401
                    domanda_guardia, save_debug_audio)
from .casa import load_casa
from .config import Config, VOICE_MAP, load_config
from .documenti import load_documenti
from .ufficio import load_ufficio
from .installa import Installazioni
from .immagini import InAttesa, opzioni_tool as opzioni_foto
from .liste import Liste
from .memory import Memory
from .pc import load_pc
from .schermi import load_schermi
from .sicurezza import proteggi_dati
from .speaker_id import SpeakerRegistry, SpeakerContext
from .stt import make_transcriber
from .tools.builtin import biblioteca_spec, build_registry
from .tools.spec import ToolContext
from .tts import Speaker
from .turnlog import TurnLog
from .web import load_web
from .modalita import Modalita
from .personalita import carica_tono_casa
from .suoni import INIZIO, SuoniAscolto
from .cortesia import Cortesia
from .wakeword import load_wake_detector

def check_audio_devices(cfg: Config):
    """Se il microfono o l'uscita scelti non ci sono (es. cuffie Bluetooth spente),
    usa quelli predefiniti del sistema (Windows; su Linux quelli di PipeWire o ALSA)
    invece di fermarsi con un errore. Cosa si usa va nel
    registro delle capacità (riassunto dell'avvio)."""
    names, notes = {}, []
    for kind, attr in (("input", "input_device"), ("output", "output_device")):
        label = "microfono" if kind == "input" else "uscita"
        dev = getattr(cfg, attr)
        try:
            if dev is not None:
                names[label] = sd.query_devices(dev, kind)["name"]
                continue
        except Exception:
            notes.append(f"{label} «{dev}» non trovato (spento o scollegato?), uso quello "
                         f"predefinito")
            setattr(cfg, attr, None)
        try:
            names[label] = sd.query_devices(kind=kind)["name"]
        except Exception:                 # nessun predefinito: lo dirà l'apertura del flusso
            notes.append(f"nessun {label} predefinito")
    vuoto = capacita.audio_virtuale_senza_dispositivi(names)
    if vuoto:                         # Linux senza microfono (la DGX in ufficio): si parte lo
        print(f"[AUDIO] {vuoto[0]}. {vuoto[1]}", flush=True)       # stesso, ma lo si dice
        capacita.segnala("audio", "guasta", vuoto[0], vuoto[1], names)
        return
    capacita.segnala("audio", "attiva", "; ".join(
        [f"{k} {v}" for k, v in names.items()] + notes), "", names)


# ─────────────────────────── COMANDI VOCALI ───────────────────────────
# I comandi regex sono diventati tool nativi: arruolamento → registra_utente,
# rename → rinomina_interlocutore, voce → cambia_voce / elenca_voci.
# Vedi tools/builtin.py e docs/architettura-tool.md.


# ─────────────────────────────── MAIN ───────────────────────────────
def single_instance_lock():
    """Impedisce di avviare due Calliope insieme.

    Il 26/09 un'istanza rimasta accesa in attesa e una nuova parlavano insieme sullo
    stesso altoparlante e chiedevano risposte allo stesso Ollama. Una porta locale
    occupata fa da lucchetto: il sistema la libera da solo se il processo muore.
    """
    import os
    import socket
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # CALLIOPE_PORTA_ISTANZA solo per le prove (prove/prova_satellite.py), che avviano una
    # Calliope vera accanto a quella che può essere accesa sul portatile
    port = int(os.environ.get("CALLIOPE_PORTA_ISTANZA") or 47913)
    try:
        lock.bind(("127.0.0.1", port))
    except OSError:
        sys.exit("Calliope è già in esecuzione: chiudi l'altra istanza prima di avviarne una nuova.")
    return lock


# NOTIFY_SOCKET tolto dall'ambiente all'avvio (06/10, `trattieni_notify_socket`): resta qui
_NOTIFY_SOCKET: str | None = None


def trattieni_notify_socket() -> str | None:
    """Toglie NOTIFY_SOCKET dall'ambiente e lo tiene per `notifica_systemd` (06/10). I
    processi figli lo ereditavano: `systemctl show` (systemd 255, chiamato da ollama_carico
    per OLLAMA_MAX_LOADED_MODELS) manda da sé «EXIT_STATUS=0» su quel socket, e il journal
    della DGX segnava «Got notification message from PID …, but reception only permitted for
    main PID» (all'avvio, alla compressione, a conversazione_cerca: 10 volte dal 05/10). Con
    NotifyAccess=main systemd lo scartava già; ora non arriva più, da nessun figlio (systemctl,
    ssh del tunnel, docker della sandbox)."""
    global _NOTIFY_SOCKET
    import os
    v = os.environ.pop("NOTIFY_SOCKET", None)
    if v:
        _NOTIFY_SOCKET = v
    return _NOTIFY_SOCKET


def notifica_systemd(messaggio: str) -> bool:
    """sd_notify senza libsystemd (02/10, DGX Linux): un datagramma sul socket in
    NOTIFY_SOCKET. Con `Type=notify` nell'unità (setup/linux/calliope.service) systemd
    considera Calliope avviata solo dopo READY=1: `systemctl --user restart calliope`
    aspetta che i modelli siano caricati, e un avvio che si rompe a metà risulta fallito.
    È ciò che usa `calliope aggiorna` per decidere se tornare alla versione di prima.
    Fuori da systemd (Windows, avvio a mano) non fa niente."""
    import os
    import socket
    addr = os.environ.get("NOTIFY_SOCKET") or _NOTIFY_SOCKET
    if not addr or not hasattr(socket, "AF_UNIX"):
        return False
    if addr.startswith("@"):                    # socket astratto di Linux
        addr = "\0" + addr[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(addr)
            s.sendall(messaggio.encode("utf-8"))
        return True
    except OSError:
        return False


def aspetta_llm(cfg: Config, brain, dire=None, dormi=time.sleep) -> str | None:
    """Riscalda il modello all'avvio. Se non risponde non esce subito (03/10, analisi di
    robustezza): all'accensione della DGX Ollama o vLLM possono non essere ancora pronti
    (vLLM ci mette minuti), e uscendo systemd esauriva i 5 riavvii in 10 minuti lasciando
    Calliope spenta. Si riprova ogni 2, 4, 8… fino a 30 s per `llm_attesa_avvio_s`, con la
    capacità «llm» che dice cosa manca e, una volta, una frase a voce (`dire`); sotto
    systemd si allunga il tempo d'avvio (EXTEND_TIMEOUT_USEC) e lo stato dice che aspetta.
    Un modello che manca (il server risponde ma non lo ha) non si aspetta.
    None quando il modello risponde, altrimenti il motivo per cui arrendersi."""
    fine = time.monotonic() + max(0.0, float(getattr(cfg, "llm_attesa_avvio_s", 0) or 0))
    attesa, detto = 2.0, False
    while True:
        try:
            brain.warmup()
            capacita.REGISTRO.da_dict(capacita.controlla_una(cfg, "llm"))
            if detto:
                print("[LLM] Il modello risponde: proseguo", flush=True)
            return None
        except RichiestaRifiutata as e:
            # 400: il server c'è e rifiuta la richiesta, cioè la configurazione è sbagliata
            # (03/10: llm_keep_alive "-1" senza unità, 11 minuti di «riprovo»). Si dice subito
            capacita.REGISTRO.da_dict(capacita.controlla_una(cfg, "llm"))
            return (f"il server rifiuta la richiesta, controlla le chiavi llm_* di "
                    f"calliope.locale.yaml ({e})")[:400]
        except Exception as e:  # noqa: BLE001
            stato = capacita.controlla_una(cfg, "llm")
            capacita.REGISTRO.da_dict(stato)
            motivo = f"{type(e).__name__}: {e}"[:200]
            resta = fine - time.monotonic()
            if stato.get("stato") == "mancante" or resta <= 0:
                return motivo
            pausa = min(attesa, 30.0, resta)
            print(f"[LLM] Il modello non risponde ancora ({stato.get('motivo') or motivo}): "
                  f"riprovo tra {pausa:.0f} s (aspetto ancora {resta / 60:.0f} minuti)",
                  flush=True)
            notifica_systemd(f"EXTEND_TIMEOUT_USEC={int((pausa + 60) * 1e6)}\n"
                             f"STATUS=Aspetto il modello: {stato.get('motivo') or motivo}")
            if not detto and dire is not None:
                try:
                    dire("Il modello non risponde ancora: aspetto che sia pronto.")
                except Exception:  # noqa: BLE001
                    pass
            detto = True
            dormi(pausa)
            attesa = min(attesa * 2, 30.0)


class Avvio:
    """L'avvio di Calliope (06/10, P8): ciò che era il corpo di `main()`, diviso in passi. Gli
    attributi sono gli oggetti preparati (configurazione, audio, servizi, tool, Brain, corsie);
    ciò che le corsie condividono va in `self.s` (ciclo.Servizi)."""

    def __init__(self):
        self._lock = single_instance_lock()   # tenuto in vita finché c'è l'avvio
        cfg = self.cfg = load_config()   # calliope.yaml (o CALLIOPE_CONFIG), poi l'ambiente
        # La modalità e il tono della casa scelti a voce (personalita.json), se più recenti
        # dei file
        carica_tono_casa(cfg)
        self.modalita = Modalita(cfg)        # la modalità cambiata a voce, subito (05/10)
        self.s = Servizi(cfg)
        self.echo_level = None
        self.corsie_tutte: dict = {}

    def prepara(self):
        cfg = self.cfg
        print(f"Avvio {cfg.name}… carico i modelli")
        # Su Linux: umask 077 e permessi stretti su memoria, voci, registro e segreti (03/10)
        corretti = proteggi_dati(cfg)
        if corretti:
            print(f"[SICUREZZA] Permessi ristretti su {len(corretti)} file di dati (solo "
                  f"l'utente di Calliope li legge)")
        self._chi_parla()
        self._audio()
        self._voce()
        self._servizi_di_casa()
        self._schermi()
        self._agenti_archivio_web()
        self._tool()
        self._minori_e_guardiano()
        self._estensioni_e_giochi()
        self._brain_e_compressione()
        self._corsia_locale()
        self._modello_e_saluto()
        self._barge_in()
        self.modalita.ascoltatori.append(self.applica_modalita)
        self._ciclo_locale()
        if self.s.satelliti is not None:
            self.s.satelliti.avviato.set()   # ora i satelliti si accolgono (saluto pronto)
        # Avvio finito (modelli caricati, saluto detto): sotto systemd (Type=notify, Linux) è
        # il segnale che l'aggiornamento è riuscito; senza NOTIFY_SOCKET non fa niente
        notifica_systemd("READY=1\nSTATUS=In ascolto")

    # ── chi parla, microfono e casse ──
    def _chi_parla(self):
        cfg, s = self.cfg, self.s
        s.registry = SpeakerRegistry(cfg)
        self.speaker_ctx = SpeakerContext(s.registry)
        # L'impronta si calcola in parallelo a Whisper: 25–50 ms che non pesano sulla risposta
        s.embed_pool = ThreadPoolExecutor(max_workers=1)
        # Persone registrate e voci da registrare di nuovo (es. dopo il passaggio dall'MFCC a
        # CAM++): nel registro delle capacità, detto nel riassunto dell'avvio
        capacita.REGISTRO.da_dict(capacita.controlla_una(cfg, "chi_parla"))
        # Se nessun utente è registrato, Calliope chiede subito di registrare il primo utente
        # della casa — "Primo" (m) o "Prima" (f)
        # Un speakers.json illeggibile non è un primo avvio (03/10): chi parlasse per primo
        # diventerebbe amministratore. Tutti ospiti finché non si ripara (SpeakerRegistry._load)
        s.enroll_pending = not s.registry.known_speakers() and not s.registry.illeggibile

    def _audio(self):
        """Microfono e casse: di questo computer, oppure di un satellite in rete (la DGX non ne
        ha: calliope/satellite/, docs/ricerche/2026-10-02-satellite.md)."""
        cfg, s = self.cfg, self.s
        if cfg.audio_modo == "satellite":
            from .satellite import load_satelliti
            s.satelliti, motivo = load_satelliti(cfg, cfg.memory_db or "memoria.db")
            if s.satelliti is None:
                for line in capacita.REGISTRO.righe_avvio():
                    print(line)
                sys.exit(f"[SATELLITE] Il server dei satelliti non parte: {motivo}")
            s.satelliti.ferma_alla_chiusura()    # anche su sys.exit e Ctrl+C
            capacita.REGISTRO.da_dict(capacita.controlla_una(cfg, "audio"))
            # Tutti i satelliti insieme, una corsia ciascuno (06/10, calliope/corsie.py)
            s.satelliti.insieme = bool(getattr(cfg, "satelliti_insieme", True))
        else:
            if cfg.audio_modo != "locale":
                print(f"[CONFIG] audio_modo «{cfg.audio_modo}» sconosciuto: uso l'audio locale "
                      f"(locale | satellite)")
            check_audio_devices(cfg)
            capacita.REGISTRO.da_dict(capacita.controlla_una(cfg, "satellite"))
        # PC comandato a voce (calliope/pc/): se non è Windows o mancano le librerie è None
        # e i tool pc_* non ci sono. Va preparato prima di Speaker: il precaricamento delle
        # voci tiene occupato l'interprete per ~7 s, e la preparazione del volume (pycaw,
        # 40 ms da sola) superava il tempo massimo e spegneva il controllo del PC (27/09).
        # Con i satelliti (Calliope sulla DGX) il PC è quello del satellite: esecutore remoto
        # sulla sua connessione (calliope/pc/remoto.py)
        self.pcs = load_pc(cfg, s.satelliti)
        # Casa via Home Assistant (calliope/casa/): il collegamento parte in secondo piano e
        # non ritarda l'avvio; senza indirizzo o token resta solo casa_integrazione, che spiega
        # a voce cosa manca
        s.casa, _diagnosi = load_casa(cfg)
        if s.satelliti is None:
            self.listener = Listener(cfg)
            s.wake = load_wake_detector(cfg)
        else:
            from .satellite import RilevatoreRemoto
            from .satellite.server import AscoltoRemoto
            self.listener = AscoltoRemoto(s.satelliti, cfg)
            # La wake word acustica gira sul satellite: qui basta sapere che c'è
            s.wake = (RilevatoreRemoto() if cfg.wake_word_enabled and cfg.wake_mode == "modello"
                      else None)
            capacita.REGISTRO.da_dict(capacita.controlla_una(cfg, "wake"))
        s.stt = make_transcriber(cfg)   # locale (faster-whisper) o server, vedi stt.py
        # Più corsie insieme: una trascrizione alla volta, la confidenza per corsia
        self.insieme = s.satelliti is not None and s.satelliti.insieme
        if self.insieme:
            s.stt = corsie.STTCondiviso(s.stt)
        # Correzione delle frasi incerte (05/10, prototipo spento: stt_correzione.py)
        if getattr(cfg, "stt_correzione", False):
            from . import stt_correzione
            s.correttore = stt_correzione.Correttore(cfg)

    def testo_saluto(self, primo: bool) -> str:
        """Con una wake word diversa dal nome (modalità startrek: «Computer») il saluto la
        dice; si rifà quando la modalità cambia a voce (05/10)."""
        cfg = self.cfg
        parola = cfg.wake_names[0]
        chiamami = ("mi chiami per nome" if parola.lower() == cfg.name.lower()
                    else f"dici «{parola}»")
        if primo:
            return (f"Ciao, sono {cfg.name}. Non conosco ancora nessuno. "
                    f"Dopo che {chiamami}, ci presentiamo.")
        if self.s.registry.illeggibile:
            return (f"Ciao, sono {cfg.name}. Non riesco a leggere l'elenco delle voci: per "
                    "ora non riconosco nessuno e vi tratto da ospiti.")
        return (f"Ciao, sono {cfg.name}. Chiamami per nome quando hai bisogno."
                if parola.lower() == cfg.name.lower() else
                f"Ciao, sono {cfg.name}. Di' «{parola}» quando hai bisogno.")

    def _voce(self):
        cfg, s = self.cfg, self.s
        self.greeting = self.testo_saluto(s.enroll_pending)
        if s.satelliti is None:
            speaker = self.speaker = Speaker(cfg)
        else:
            from .satellite.server import UscitaRemota
            speaker = self.speaker = Speaker(cfg, uscita=UscitaRemota(s.satelliti))
            # Il saluto lo dice ogni satellite alla prima connessione, e intanto misura l'eco:
            # si sintetizza ora, prima che altri thread usino la voce
            s.satelliti.saluto = speaker.sintetizza(self.greeting)
        # Suoni di inizio e fine ascolto (04/10, calliope/suoni.py; modalità startrek): li suona
        # chi ha il microfono. In locale l'inizio allo scatto della wake word acustica, dentro
        # Listener.listen; con un satellite o un telefono glieli manda il benvenuto
        s.suoni = suoni = SuoniAscolto(cfg) if cfg.suoni_ascolto else None
        if suoni is not None and s.satelliti is None:
            self.listener.on_wake = lambda: speaker.suono_ascolto(suoni, INIZIO)
        if s.satelliti is not None:
            s.satelliti.suoni = suoni
        # Whisper che passa alla CPU durante l'uso (errore della GPU, server di trascrizione
        # giù): la prima frase costa secondi, e Calliope lo dice invece di tacere (03/10)
        stt = s.stt
        stt.on_ripiego = lambda: corsie.per_corsia(speaker, "speaker").say_cached(stt.ATTESA)
        # Voci caricate in secondo piano: così un cambio di voce non ritarda la risposta
        # (~1,2 s l'una): prima le preferite degli utenti, poi le altre.
        speaker.preload([s.registry.get(n).preferred_voice for n in s.registry.known_speakers()]
                        + [p for p in VOICE_MAP.values() if Path(p).exists()])
        capacita.REGISTRO.da_dict(capacita.controlla_una(cfg, "voce"))

    # ── servizi ──
    def _servizi_di_casa(self):
        """Biblioteca, memoria, agenda, liste, documenti, installazioni. Tool nativi: registro
        + contesto che dà loro accesso allo stato del processo (voiceprint, voce, sessione).
        Vedi docs/architettura-tool.md."""
        cfg, s = self.cfg, self.s
        db = cfg.memory_db or "memoria.db"
        # Biblioteca offline: se i file ZIM mancano è None e il tool non c'è (senza l'indice di
        # ricerca c'è, ridotta: lo dice il registro delle capacità)
        s.biblioteca = load_biblioteca(cfg)
        self.memory = Memory(cfg.memory_db, cfg.memory_max_facts) if cfg.memory_db else None
        capacita.REGISTRO.da_dict(capacita.controlla_una(cfg, "memoria"))
        # Timer e promemoria: quando qualcosa scade l'agenda sveglia l'ascolto
        due = self.due_event = threading.Event()
        s.agenda = Agenda(db, on_due=due.set)
        # Liste della casa (spesa, cose da fare…), nello stesso file
        self.liste = Liste(db)
        # Documenti Word, Excel e PDF (calliope/documenti/): i JSON nello stesso file; un
        # documento finito in secondo piano sveglia l'ascolto come un timer scaduto
        # Con i satelliti i file vanno al portatile collegato (RemoteDelivery)
        s.documenti = load_documenti(cfg, db, on_done=due.set, pcs=self.pcs,
                                     satelliti=s.satelliti)
        # Installazioni a voce dal catalogo (calliope/installa/): finite in secondo piano,
        # svegliano l'ascolto come un timer e si annunciano con il segnale acustico
        s.installazioni = Installazioni(cfg, on_done=due.set) if cfg.installa_enabled else None

    def _timer_scaduto(self, item):
        """Un timer che scade aggiorna la sua scheda sugli schermi («scaduto alle 23:07»): la
        manda l'agenda, dal suo thread (Schermi.invia non blocca)."""
        from .schermi import schede
        if item.get("kind") == "timer":
            # Verso lo schermo da cui era stato chiesto (calliope/rispondi.py, 04/10)
            self.s.schermi.invia(schede.timer(item, "scaduto", time.time()),
                                 self.s.instradamento.mittente_annuncio(("agenda", item.get("id"))))

    def _schermi(self):
        """Schermi (calliope/schermi/): il server delle schede parte in un thread; senza
        starlette e uvicorn, o con la porta occupata, è None e Calliope funziona uguale (lo dice
        il registro delle capacità). Le schede le mandano i tool, la voce non le aspetta."""
        cfg, s = self.cfg, self.s
        schermi = s.schermi = load_schermi(cfg, cfg.memory_db or "memoria.db")
        if schermi is not None:
            s.agenda.on_scaduta = self._timer_scaduto
            # Scrivere invece di parlare (03/10, schermi/moduli.py): testo e moduli dalle pagine
            # svegliano l'ascolto come un timer, e si trattano tra un turno e l'altro
            schermi.ingresso.sveglia = self.due_event.set
            # Il cruscotto di chi amministra (06/10, schermi/cruscotto.py): sola lettura, sugli
            # schermi personali di chi amministra; lavori e satelliti letti al momento
            from .schermi.cruscotto import Cruscotto
            schermi.cruscotto = Cruscotto(cfg, schermi, servizi=s)
        if schermi is not None and s.satelliti is not None:
            # Le schede vanno agli schermi della stanza del satellite che ascolta, e il
            # satellite può aprire la pagina con un token suo (calliope/satellite/server.py)
            schermi.stanza_corrente = s.satelliti.stanza
            s.satelliti.schermi = schermi
            # Il telefono (web app /telefono) entra come satellite dal server degli schermi; e
            # «questo schermo è mio» a voce (schermo_gestisci, 03/10): il satellite da cui si parla
            schermi.satelliti = s.satelliti
        # Rispondi dove ti ho chiesto (04/10, calliope/rispondi.py): una frase scritta dal
        # telefono ha la risposta dal telefono (e scritta sul suo schermo), le schede vanno
        # prima allo schermo da cui arriva la richiesta, gli annunci al satellite che li aveva
        # chiesti
        from .rispondi import Instradamento
        s.instradamento = Instradamento(s.satelliti, schermi, self.speaker, cfg)
        s.instradamento.avvolgi_agenda(s.agenda)

    def _agenti_archivio_web(self):
        cfg, s, listener = self.cfg, self.s, self.listener
        # Agenti per i lavori lunghi (calliope/agenti/): la DGX via tunnel SSH (dgx.yaml) o un
        # Ollama diretto (agenti_url). Il tunnel si apre in secondo piano: l'avvio non aspetta,
        # e senza VPN Calliope parte uguale. Un lavoro finito sveglia l'ascolto come un timer.
        # Con i satelliti i risultati dei lavori sui file della persona tornano al portatile
        # (RemoteDelivery, come i documenti); senza, restano nella cartella del lavoro
        consegna_lavori = None
        if s.satelliti is not None:
            from .documenti.consegna import LocalDelivery, RemoteDelivery
            consegna_lavori = RemoteDelivery(
                s.satelliti, LocalDelivery(getattr(cfg, "documenti_cartella", None)),
                getattr(cfg, "pc_nome", "portatile"))
        lavori = s.lavori = load_agenti(cfg, on_done=self.due_event.set, biblioteca=s.biblioteca,
                                        formati=s.documenti.formati if s.documenti else (),
                                        consegna=consegna_lavori)
        if lavori is not None:
            atexit.register(lavori.close)        # chiude il tunnel anche su un'uscita brusca
            # Il risultato consegnato al portatile si offre ad «aprilo» (07/10)
            lavori.pcs = self.pcs
            if self.insieme:
                # Più corsie: la voce è libera solo quando nessuna la tiene (06/10)
                lavori.arbitro.voce_occupata, lavori.arbitro.voce_libera = corsie.condivisa(
                    lavori.arbitro.voce_occupata, lavori.arbitro.voce_libera)
            # Arbitro: con l'agente sulla GPU della voce (stesso Ollama, o vLLM sulla stessa
            # macchina: impostazioni.stessa_gpu), la voce ha la precedenza
            listener.on_speech_start = lavori.arbitro.voce_occupata
            listener.on_speech_end = lavori.arbitro.voce_libera
            # vLLM in pausa mentre si parla: su SIGTERM (calliope ferma) si riprende prima di
            # uscire, altrimenti resterebbe fermo fino al prossimo avvio
            lavori.arbitro.proteggi_uscita()
        # Ufficio (calliope/ufficio/): modelli di documento, rubrica, fatture e DDT. Usa il
        # servizio dei documenti (cartella, lavori in secondo piano, «aprilo») e, per i testi
        # lunghi dentro un modello, lo scrittore degli agenti se c'è
        self.ufficio = None
        if s.documenti is not None:
            self.ufficio = load_ufficio(cfg, cfg.memory_db or "memoria.db", s.documenti, lavori)
        else:
            capacita.REGISTRO.da_dict(capacita.controlla_una(cfg, "ufficio"))
        # Archivio dei documenti di casa (calliope/archivio/): la cartella si legge in secondo
        # piano con il modello grande (lo stesso degli agenti, o archivio_url); senza cartella
        # è None
        archivio = self.archivio = load_archivio(cfg, lavori=lavori, speakers=s.registry)
        if archivio is not None:
            atexit.register(archivio.close)
            if lavori is not None:
                lavori.agente.archivio = archivio      # le ricerche delegate esplorano il grafo
        # Ricerca su internet (calliope/web/, 03/10): SearXNG sulla DGX, solo se configurato e
        # con la rete. Giù all'avvio: il tool arriva da solo quando risponde (vedi il ciclo)
        web = s.web = load_web(cfg, speakers=s.registry)
        if web is not None:
            atexit.register(web.close)
            if lavori is not None:
                lavori.agente.web = web                # le ricerche delegate leggono anche il web

    def _tool(self):
        cfg, s = self.cfg, self.s
        schermi, lavori, ufficio, web = s.schermi, s.lavori, self.ufficio, s.web
        # Archivio delle conversazioni (05/10, calliope/conversazioni.py): i turni finiti, per
        # la compressione della storia e per conversazione_cerca
        from .conversazioni import load_conversazioni
        conv_arch = self.conv_arch = load_conversazioni(cfg)
        if conv_arch is not None:
            atexit.register(conv_arch.close)
        # Il cassetto dei file per persona (08/10, calliope/cassetto.py): foto, file e audio
        # restano 7 giorni; con gli allegati dagli schermi
        cassetto = None
        if schermi is not None and getattr(cfg, "allegati_enabled", True):
            from .cassetto import load_cassetto
            cassetto = load_cassetto(cfg)
        s.cassetto = cassetto
        if cassetto is not None:
            atexit.register(cassetto.close)
            cassetto.archivio, cassetto.registry = self.archivio, s.registry
            schermi.cassetto = cassetto
        s.tools = build_registry(biblioteca=s.biblioteca is not None, pc=self.pcs,
                                 pc_ospite=cfg.pc_ospite_volume_media,
                                 documenti=s.documenti.formati if s.documenti else None,
                                 casa=(s.casa is not None) if cfg.casa_enabled else None,
                                 casa_ospite=bool(cfg.casa_ospite_domini),
                                 installa=s.installazioni is not None,
                                 citazioni=bool(s.biblioteca and s.biblioteca.citazioni),
                                 schermi=schermi is not None,
                                 agenti=lavori is not None,
                                 # Con l'ufficio i modelli si compilano con modello_compila
                                 agenti_modelli=(tuple(lavori.modelli)
                                                 if lavori and ufficio is None else ()),
                                 ufficio=tuple(ufficio.nomi_modelli()) if ufficio else (),
                                 archivio=self.archivio is not None,
                                 web=cfg if web is not None and web.pronta else None,
                                 conversazioni=conv_arch is not None,
                                 # Foto (05/10, calliope/immagini.py): pc_guarda,
                                 # immagine_archivia
                                 immagini=opzioni_foto(cfg, self.pcs, self.archivio),
                                 # File allegati dagli schermi (05/10, calliope/allegati.py)
                                 allegati=bool(getattr(cfg, "allegati_enabled", True)
                                               and schermi is not None),
                                 cassetto=cassetto is not None)
        # Foto (e file allegati) mandati senza domanda: aspettano la frase dopo della stessa
        # persona
        s.foto_attesa = InAttesa(getattr(cfg, "immagini_attesa_s", 120.0))
        if schermi is not None:
            # Una foto in attesa della domanda vale solo nella conversazione in cui è arrivata
            schermi.su_fine_conversazione.append(s.foto_attesa.togli)
        self.tool_ctx = ToolContext(cfg=cfg, speakers=s.registry,
                                    speaker_ctx=self.speaker_ctx, speaker=self.speaker,
                                    memory=self.memory, agenda=s.agenda, liste=self.liste,
                                    biblioteca=s.biblioteca, pc=self.pcs, documenti=s.documenti,
                                    casa=s.casa, capacita=capacita.REGISTRO,
                                    installazioni=s.installazioni, schermi=schermi,
                                    lavori=lavori, ufficio=ufficio, archivio=self.archivio,
                                    web=web, conversazioni=conv_arch, modalita=self.modalita,
                                    cassetto=cassetto)

    def attiva_minori(self) -> bool:
        """I tool compiti_aiuto e minore_gestisci solo con un minore in casa: True se li ha
        appena registrati."""
        tools, registry = self.s.tools, self.s.registry
        if tools.get("compiti_aiuto") is not None or not any(
                minori.e_minore(p) for p in getattr(registry, "users", {}).values()):
            return False
        from .tools.minori import minori_specs
        for spec in minori_specs():
            tools.register(spec)
        return True

    def _minori_e_guardiano(self):
        cfg, s = self.cfg, self.s
        # Minori (05/10, calliope/minori.py): regole per persona, compiti, avvisi ai tutori
        # (stesso file della memoria)
        minori.prepara(cfg, schermi=s.schermi, registry=s.registry)
        # Esercizi generati da Calliope (08/10, calliope/esercizi/): stesso file della memoria;
        # la scheda risponde da /api/esercizio (schermi/server.py)
        try:
            from .esercizi import sessione as esercizi
            srv = esercizi.prepara(cfg, schermi=s.schermi, biblioteca=s.biblioteca,
                                    registry=s.registry)
            if s.schermi is not None:
                s.schermi.esercizi = srv
        except Exception as e:  # noqa: BLE001 — senza esercizi Calliope parte lo stesso
            print(f"[ESERCIZI] non disponibili: {type(e).__name__}: {e}", flush=True)
        s.attiva_minori = self.attiva_minori
        self.attiva_minori()
        # Il guardiano (calliope/guardiano.py): domanda e frasi della risposta per minori e
        # ospiti. Si carica in secondo piano (la prima frase di un bambino non paga il
        # caricamento)
        if not (cfg.minori_enabled and cfg.guardiano_enabled and cfg.guardiano_modello):
            return
        try:
            guardiano = s.guardiano = guardia.Guardiano(cfg)
            atexit.register(guardiano.close)

            def scalda_guardiano():
                t0 = time.perf_counter()
                ok = guardiano.prepara()
                print(f"\n[GUARDIANO] {cfg.guardiano_modello} "
                      + (f"pronto ({time.perf_counter() - t0:.1f} s)" if ok else
                         f"non risponde ({guardiano.ultimo_errore}): per i minori le frasi non "
                         f"controllate non si dicono"), flush=True)
            # Caricato subito con un minore in casa, o se giudica anche gli ospiti
            # (guardiano_ospiti): prima, per i soli ospiti, il primo turno pagava il tempo
            # massimo e la risposta passava senza giudizio (Q3 dell'analisi del 06/10)
            if cfg.guardiano_ospiti or any(minori.e_minore(p) for p in
                                           getattr(s.registry, "users", {}).values()):
                threading.Thread(target=scalda_guardiano, daemon=True).start()
        except Exception as e:  # noqa: BLE001
            print(f"[GUARDIANO] non disponibile: {type(e).__name__}: {e}", flush=True)
            s.guardiano = None

    def _estensioni_e_giochi(self):
        """Estensioni (calliope/estensioni/, 04/10): funzioni permanenti scritte dall'agente,
        approvate con la frase di sfida, sempre nel container della sandbox. Il container si
        sceglie in secondo piano; i tool est_<nome> delle attive si registrano qui."""
        cfg, s = self.cfg, self.s
        from .estensioni import load_estensioni
        from .tools.estensioni import estensioni_specs
        estensioni = self.estensioni = load_estensioni(cfg, s.tools, self.tool_ctx, s.lavori)
        if estensioni is not None:
            try:
                # sviluppo_apri (08/10, versione 2) c'è già con gli agenti: non si rifà
                for spec in estensioni_specs(crea=s.lavori is not None
                                             and s.tools.get("sviluppo_apri") is None):
                    s.tools.register(spec)
                estensioni.aggiorna_tool()
                self.tool_ctx.estensioni = estensioni
                estensioni.on_done = self.due_event.set
                atexit.register(estensioni.close)
            except Exception as e:  # noqa: BLE001 — senza estensioni Calliope parte uguale
                print(f"[ESTENSIONI] non disponibili: {type(e).__name__}: {e}", flush=True)
                estensioni = self.estensioni = None
        # Giochi sugli schermi (05/10, calliope/schermi/giochi.py): le estensioni con una
        # scheda interattiva girano nel browser, in un riquadro isolato; qui le partite e i
        # messaggi
        if estensioni is not None and s.schermi is not None and cfg.giochi_enabled:
            from .schermi.giochi import Giochi
            giochi = s.giochi = Giochi(cfg, s.schermi, estensioni)
            giochi.guardiano = s.guardiano
            giochi.on_frase = self.due_event.set
            s.schermi.giochi = estensioni.giochi = giochi

    def _luogo_satellite(self):
        """La stanza del satellite per l'archivio delle conversazioni. stanza_corrente è la
        funzione del server dei satelliti (satelliti.stanza), non il suo valore: chiamarla (il
        05/10 la funzione finiva nell'archivio e ogni turno falliva con «type 'method' is not
        supported»)."""
        s = getattr(self.s.schermi, "stanza_corrente", None) or self.s.satelliti.stanza
        s = s() if callable(s) else s
        return str(s) if s else "satellite"

    def _brain_e_compressione(self):
        cfg, s = self.cfg, self.s
        brain = self.brain = Brain(cfg, s.tools, self.tool_ctx)
        # Conversazione come oggetto, archivio e compressione vicino al limite (05/10,
        # calliope/conversazione.py, calliope/compressione.py)
        brain.archivio_conv = self.conv_arch
        brain.luogo_fn = self._luogo_satellite if s.satelliti is not None else (
            lambda: "locale")
        from .compressione import Compressore, crea_riassuntori
        riassuntori = crea_riassuntori(cfg, s.lavori)
        if not riassuntori:
            return
        compressore = s.compressore = Compressore(cfg, riassuntori, self.conv_arch)
        if self.insieme:
            compressore.voce_occupata, compressore.voce_libera = corsie.condivisa(
                compressore.voce_occupata, compressore.voce_libera)
        brain.compressore = compressore
        atexit.register(compressore.close)
        print(f"[CONTESTO] Compressione oltre il {cfg.contesto_soglia_morbida:.0%} della "
              f"finestra; riassume: {' → '.join(r.nome for r in riassuntori)}", flush=True)
        listener = self.listener
        prima_inizio_c, prima_fine_c = listener.on_speech_start, listener.on_speech_end

        def inizio_parlato():
            compressore.voce_occupata()      # il riassunto con il modello della voce cede
            if prima_inizio_c is not None:
                prima_inizio_c()

        def fine_parlato():
            compressore.voce_libera()
            if prima_fine_c is not None:
                prima_fine_c()
        listener.on_speech_start, listener.on_speech_end = inizio_parlato, fine_parlato

    def _corsia_locale(self):
        """Le conversazioni, una per persona e una per ospiti di ogni satellite (06/10,
        calliope/corsie.py), e le risposte del modello insieme (conversazioni_parallele)."""
        cfg, brain = self.cfg, self.brain
        self.registro_conv = corsie.RegistroConversazioni(cfg)
        self.varco = corsie.Varco(getattr(cfg, "conversazioni_parallele", 1))
        brain.conversazioni = self.registro_conv
        self.registro_conv.riprendi(self.conv_arch)   # di prima di un riavvio, se non scadute
        # La corsia di questo thread: l'audio di questo computer, o il satellite attivo
        corsia = self.corsia = corsie.Corsia("locale", registro=self.registro_conv,
                                             varco=self.varco)
        corsia.listener, corsia.speaker = self.listener, self.speaker
        corsia.speaker_ctx, corsia.brain, corsia.tool_ctx = self.speaker_ctx, brain, self.tool_ctx
        corsie.entra(corsia)
        self.corsie_tutte[corsia.chiave] = corsia
        if self.estensioni is not None:
            # mentions_tool rilegge i nomi dei tool
            self.estensioni.on_cambio = lambda: self.brain.rileggi_tool()
        if self.s.installazioni is not None:
            self.s.installazioni.attivatori["biblioteca"] = self.activate_library

    def activate_library(self) -> bool:
        """Biblioteca appena scaricata: si apre, il tool compare e il prompt la nomina, senza
        riavvio. Gira sul thread della corsia, tra un turno e l'altro."""
        s = self.s
        nuova = load_biblioteca(self.cfg)
        if nuova is None:
            return False
        vecchia, s.biblioteca = s.biblioteca, nuova
        self.tool_ctx.biblioteca = nuova
        for c in list(self.corsie_tutte.values()):   # anche le corsie dei satelliti
            if c.tool_ctx is not None:
                c.tool_ctx.biblioteca = nuova
        if s.lavori is not None:
            s.lavori.agente.biblioteca = nuova     # le ricerche dell'agente la usano subito
        if vecchia is not None:
            vecchia.close()        # su Windows un file aperto non si cancella (pulizia)
        spec = biblioteca_spec(nuova.citazioni)
        old = s.tools.get("biblioteca_cerca")
        if old is None or old.description != spec.description:   # anche Wikiquote nuova
            s.tools.register(spec)
            if old is None:
                self.speaker.prepare(spec.announce)
            self.brain.rileggi_tool()             # mentions_tool rilegge i nomi dei tool
        return True

    # ── modello, saluto, barge-in ──
    def _modello_e_saluto(self):
        cfg, s, speaker, brain = self.cfg, self.s, self.speaker, self.brain
        from .compressione import FRASE_DURA
        # Frasi d'attesa dei tool lenti («Vediamo…»), sintetizzate subito in secondo piano
        # e le risposte di cortesia («Prego!», «Bene!») nel tono della casa e delle persone
        s.cortesia = Cortesia()
        speaker.prepare(s.tools.announcements() + [s.stt.ATTESA, FRASE_DURA, corsie.FRASE_CODA]
                        + s.cortesia.frasi([cfg.tono] + [u.preferred_tone for u in
                                                         s.registry.users.values()
                                                         if u.preferred_tone]))
        errore_llm = aspetta_llm(cfg, brain, dire=(speaker.say if s.satelliti is None else None))
        if errore_llm is not None:
            for line in capacita.REGISTRO.righe_avvio():
                print(line)
            if errore_llm.startswith("il server rifiuta"):
                sys.exit(f"[LLM] Errore di configurazione del modello: {errore_llm}")
            sys.exit(f"[LLM] Non riesco a contattare il modello ({errore_llm}). Ollama (o vLLM) "
                     f"è avviato? Hai fatto 'ollama pull {cfg.llm_model}'?")
        # Finestra di contesto dal setup (05/10, calliope/contesto.py): con «auto» la calcola
        # e, se cambia, ricarica il modello prima del saluto; dice sempre quale e perché
        try:
            contesto.prepara(cfg, brain)
        except Exception as e:  # noqa: BLE001 — resta la finestra del riscaldamento
            print(f"[CONTESTO] Finestra non calcolata ({type(e).__name__}: {e}): uso "
                  f"{contesto.finestra(cfg)}", flush=True)
        # La conversazione ripresa dopo il riavvio va subito in cache (06/10, P3: il primo
        # turno non rilegge la storia) e, se ieri o oggi la voce era lenta, lo si dice (P4)
        threading.Thread(target=latenza.scalda_ripresa, args=(brain, self.registro_conv.tutte()),
                         name="scalda-ripresa", daemon=True).start()
        avviso_latenza = latenza.avviso_recente(cfg)
        if avviso_latenza:
            print(f"[LATENZA] {avviso_latenza} Dettagli: calliope stato --turni", flush=True)
        # Troppe domande di sicurezza oggi o ieri (08/10, calliope/attrito.py, D6)
        avviso_attrito = attrito.avviso_recente(cfg)
        if avviso_attrito:
            print(f"[SICUREZZA] {avviso_attrito} Dettagli: calliope stato --turni", flush=True)
        # Una riga di riassunto al posto delle stampe di ogni caricamento; la tabella completa
        # con i passi: python -m calliope.stato. La casa si collega in secondo piano: di solito
        # ha già finito (Whisper e le voci si caricano in qualche secondo), al più si aspettano
        # 0,3 s il primo tentativo, e il riassunto rilegge il suo stato (01/10: diceva
        # «collegamento in corso» sotto la riga «[CASA] Collegata…»)
        if s.casa is not None:
            s.casa.attendi_primo_tentativo(0.3)
        for line in capacita.REGISTRO.righe_avvio():
            print(line)
        if s.satelliti is None:
            self._saluto_ed_eco()
        # Registro dei turni: ogni turno si scrive all'inizio del giro dopo, così anche i
        # rami che finiscono con `continue` vengono registrati (vedi turnlog.py)
        # Profilo e modello in ogni turno (06/10, P6): le reti per modello si misurano da lì
        s.turns = TurnLog(cfg.turn_log_dir, cfg.turn_log_days,
                          modello={"profilo": cfg.llm_profilo or None, "modello": cfg.llm_model})
        if s.schermi is not None:
            # I rifiuti dello scritto senza conversazione (thread del server, 05/10)
            s.schermi.registro_turni = s.turns.write
        if s.cassetto is not None:
            # Il cassetto (08/10): nel registro solo nome, tipo e dimensione; la pulizia dei
            # file scaduti subito e poi ogni cassetto_pulizia_s
            s.cassetto.registro = s.turns.write
            s.cassetto.avvia(float(getattr(cfg, "cassetto_pulizia_s", 3600.0)))

    def _saluto_ed_eco(self):
        """Il saluto, e intanto si misura se il microfono sente la sua voce (eco)."""
        speaker = self.speaker
        speaker.say(self.greeting)
        echo_stop = threading.Event()
        echo = {}
        echo_thread = threading.Thread(
            target=lambda: echo.setdefault("q", self.listener.measure_echo(echo_stop)),
            daemon=True)
        echo_thread.start()
        speaker.wait()
        echo_stop.set()
        echo_thread.join()
        self.echo_level = echo.get("q", 1.0)

    def _barge_in(self):
        cfg, s, echo_level = self.cfg, self.s, self.echo_level
        s.barge_in = s.wake is not None and cfg.barge_in_enabled
        if echo_level is None:
            # Satellite: l'eco la misura lui sul saluto della prima connessione, e il livello B
            # vale solo se lì non l'ha sentita (AscoltoRemoto.watch_for_name)
            s.barge_voice = s.barge_in and cfg.barge_in_voice
            if s.barge_in:
                print(f"[BARGE-IN] Attivo sul satellite: «{cfg.wake_names[0]}, basta» mentre "
                      "parlo mi interrompe" + ("; anche la voce di chi è registrato, se il "
                                               "satellite non sente la mia eco"
                                               if s.barge_voice else ""))
            return
        # Livello B leggero: solo se il microfono non sente l'eco della sua voce
        s.barge_voice = s.barge_in and cfg.barge_in_voice and echo_level <= cfg.barge_in_echo_max
        if s.barge_in:
            print(f"[BARGE-IN] Attivo: «{cfg.wake_names[0]}, basta» mentre parlo mi interrompe")
            print(f"[BARGE-IN] Eco sentita durante il saluto: {echo_level * 100:.0f} % dei "
                  f"frame → " + ("anche la voce di chi è registrato mi interrompe"
                                 if s.barge_voice
                                 else "solo il nome (il microfono sente la mia voce)"))

    def applica_modalita(self, _cfg) -> dict:
        """La modalità è cambiata a voce (05/10, calliope/modalita.py): chi tiene una copia
        della wake word, dei suoni o del saluto la rifà adesso, senza riavvio. Il resto
        (Whisper, wake word testuale, uscite, schermi, prompt) legge cfg a ogni uso."""
        cfg, s, speaker = self.cfg, self.s, self.speaker
        note = {}
        suoni = s.suoni = SuoniAscolto(cfg) if cfg.suoni_ascolto else None
        if s.satelliti is None:
            s.wake = load_wake_detector(cfg)     # rileva anche «Calliope» (Config.wake_models)
            self.listener.on_wake = ((lambda: speaker.suono_ascolto(suoni, INIZIO))
                                     if suoni is not None else None)
            s.barge_in = s.wake is not None and cfg.barge_in_enabled
            s.barge_voice = s.barge_in and cfg.barge_in_voice and (
                self.echo_level is None or self.echo_level <= cfg.barge_in_echo_max)
            if s.wake is not None:
                note["modelli"] = list(getattr(s.wake, "modelli", []))
            else:
                note["wake"] = "testuale"
            return note
        capacita.REGISTRO.da_dict(capacita.controlla_una(cfg, "wake"))
        s.satelliti.suoni = suoni
        note.update(s.satelliti.annuncia_modalita())
        # Il saluto dei satelliti nuovi con la parola nuova, in secondo piano (~0,3 s di
        # sintesi: la conferma a voce non aspetta; dal 06/10 la sintesi regge più thread)
        primo = not s.registry.known_speakers() and not s.registry.illeggibile

        def rifai_saluto(testo=self.testo_saluto(primo)):
            try:
                s.satelliti.saluto = speaker.sintetizza(testo)
            except Exception as e:  # noqa: BLE001
                print(f"[MODALITÀ] saluto non rifatto: {type(e).__name__}: {e}", flush=True)
        threading.Thread(target=rifai_saluto, daemon=True, name="saluto").start()
        return note

    # ── il ciclo ──
    def _ciclo_locale(self):
        """Il ciclo della corsia di questo thread. Annunci (timer, documenti, installazioni,
        lavori, estensioni) e frasi scritte dagli schermi: con una corsia sola le code dei
        servizi; con i satelliti insieme ogni corsia vede solo i suoi (corsie.Smistatore)."""
        s = self.s
        annunci = types.SimpleNamespace(
            agenda=s.agenda.due, documenti=getattr(s.documenti, "done", None),
            installazioni=getattr(s.installazioni, "done", None),
            lavori=getattr(s.lavori, "done", None),
            estensioni=getattr(self.estensioni, "done", None))
        ingresso = s.schermi.ingresso if s.schermi is not None else None
        # I callback del VAD prima dello stato della voce (arbitro, compressione): ogni corsia
        # ci aggiunge il suo (Ciclo._collega_voce, P9)
        self.parlato = (self.listener.on_speech_start, self.listener.on_speech_end)
        self.ciclo = Ciclo(s, self.corsia, self.listener, self.speaker, self.speaker_ctx,
                           self.brain, self.tool_ctx, annunci, ingresso, self.due_event)
        self.corsia.ciclo = self.ciclo

    def esegui(self):
        if self.insieme:
            # Un satellite che si collega per la prima volta ha la sua corsia (06/10,
            # calliope/corsie.py); questo thread aspetta e crea quelle nuove
            Corsie(self).esegui()
        else:
            self.ciclo.esegui()
        # Uscita normale dal ciclo: il server dei satelliti si ferma qui, a interprete ancora
        # vivo (02/10: da atexit websockets dava «cannot schedule new futures after interpreter
        # shutdown»). Con l'audio di un satellite «spegniti» oggi addormenta soltanto, ma un
        # break futuro non deve ritrovare il difetto.
        if self.s.satelliti is not None:
            self.s.satelliti.ferma()


class Corsie:
    """Tutti i satelliti insieme (06/10, calliope/corsie.py): ogni satellite che si collega per
    la prima volta ha la sua corsia, un thread con il suo `Ciclo` (calliope/ciclo.py) e i suoi
    oggetti: ascolto e voce legati al suo id, `SpeakerContext`, Brain e ToolContext suoi.
    Restano condivisi il registro delle voci, i servizi (agenda, memoria, liste, casa…), la
    trascrizione, le conversazioni per persona.

    Le code degli annunci e delle frasi scritte le svuota uno smistatore: ogni corsia vede
    solo ciò che è per il suo satellite (o per nessuno in particolare). Un satellite che si
    scollega lascia la sua corsia ad aspettarlo; un errore fatale di una corsia (troppi errori
    di fila) ferma Calliope come prima."""

    def __init__(self, avvio: Avvio):
        self.a = avvio
        self.satelliti = avvio.s.satelliti
        self.fine = threading.Event()
        self.uscite: list = []
        self.smist = corsie.Smistatore(self._fonti(), self._disponibile)

    def _scritto_per(self, item) -> str | None:
        """La corsia di una frase scritta: il satellite dello schermo (il telefono), o uno
        nella stessa stanza; None = una qualunque."""
        from .schermi.archivio import norm_stanza
        satelliti = self.satelliti
        coll = satelliti.per_schermo(item.get("schermo_id"))
        if coll is not None:
            return f"sat:{coll.satellite.get('id')}"
        stanza = norm_stanza(item.get("stanza") or "")
        if stanza:
            with satelliti._cond:
                stessi = [c for c in reversed(satelliti.collegati) if c.pronto
                          and not c.chiuso.is_set() and norm_stanza(c.stanza or "") == stanza]
            if stessi:
                return f"sat:{stessi[0].satellite.get('id')}"
        return None

    def _fonti(self) -> dict:
        s, instr = self.a.s, self.a.s.instradamento

        def coda(servizio, nome="done"):
            return getattr(servizio, nome, None) if servizio is not None else None
        return {
            "agenda": (s.agenda.due, lambda it: instr.corsia_di(("agenda", it.get("id")))),
            "documenti": (coda(s.documenti), lambda it: instr.corsia_di(
                persona=it.get("owner"))),
            "installazioni": (coda(s.installazioni), None),
            "lavori": (coda(s.lavori), lambda it: instr.corsia_di(persona=it.get("chi"))),
            "estensioni": (coda(self.a.estensioni), None),
            "scritti": (coda(getattr(s.schermi, "ingresso", None), "coda"), self._scritto_per)}

    def _disponibile(self, chiave) -> bool:
        c = self.smist.corsie.get(chiave)
        return c is not None and self.satelliti.per_id(c.satellite_id) is not None

    def _ponte(self):
        """Le sveglie dei servizi (un timer scaduto, una frase scritta) alle corsie giuste."""
        due_event = self.a.due_event
        while True:
            due_event.wait()
            due_event.clear()
            try:
                self.smist.sveglia()
            except Exception as e:  # noqa: BLE001
                print(f"   [CORSIE] smistamento: {type(e).__name__}: {e}", flush=True)

    def _ciclo(self, c):
        corsie.entra(c)
        try:
            c.ciclo.esegui(self.fine)
        except SystemExit as e:              # troppi errori di fila: ferma Calliope
            self.uscite.append(e)
            self.fine.set()

    def crea(self, sid, nome):
        from .satellite.server import AscoltoRemoto, UscitaRemota
        a, smist = self.a, self.smist
        cfg, brain = a.cfg, a.brain
        c = corsie.Corsia(f"sat:{sid}", satellite_id=sid, nome=nome, registro=a.registro_conv,
                          varco=a.varco)
        lst = AscoltoRemoto(self.satelliti, cfg, sat_id=sid)
        lst.on_speech_start, lst.on_speech_end = a.parlato   # lo stato della voce: Ciclo
        sp = a.speaker.gemello(UscitaRemota(self.satelliti, sat_id=sid))
        sc = SpeakerContext(a.s.registry)
        tc = dataclasses.replace(a.tool_ctx, speaker_ctx=sc, speaker=sp, storia=[],
                                 risposta_precedente={}, regole=[], immagini_viste=[], turno=0,
                                 tool_in_sospeso=None, user_text="", immagini=None,
                                 allegati=None, politica=None)
        b = Brain(cfg, a.s.tools, tc)
        for k in ("archivio_conv", "compressore", "luogo_fn", "prefix_tokens", "last_context"):
            setattr(b, k, getattr(brain, k, None))
        b.conversazioni, b.satellite = a.registro_conv, c.chiave
        c.listener, c.speaker, c.speaker_ctx, c.brain, c.tool_ctx = lst, sp, sc, b, tc
        annunci = types.SimpleNamespace(**{n: smist.vista(n, c) for n in
                                           ("agenda", "documenti", "installazioni", "lavori",
                                            "estensioni")})
        c.ciclo = Ciclo(a.s, c, lst, sp, sc, b, tc, annunci, smist.vista("scritti", c),
                        c.sveglia)
        smist.corsie[c.chiave] = c
        a.corsie_tutte[c.chiave] = c
        c.thread = threading.Thread(target=self._ciclo, args=(c,), daemon=True,
                                    name=f"corsia-{sid}")
        c.thread.start()
        print(f"[CORSIE] {nome or sid}: corsia nuova ({len(smist.corsie)} satelliti, "
              f"risposte insieme: {a.varco.limite or 'senza limite'})", flush=True)
        smist.sveglia()                      # annunci arrivati prima di lei

    def _voce_di_chi_va(self, presenti: set, ora: set):
        """Un satellite che se ne va toglie il suo stato della voce dagli schermi della sua
        stanza (Q9): restano gli stati degli altri satelliti lì, o «dorme»."""
        schermi = self.a.s.schermi
        for chiave in presenti - ora:
            if schermi is not None:
                try:
                    schermi.voce_via(chiave)
                except Exception:  # noqa: BLE001 — lo schermo non ferma mai la voce
                    pass
        presenti.clear()
        presenti.update(ora)

    def esegui(self):
        """Aspetta i satelliti e crea le corsie nuove, finché una corsia non ferma Calliope."""
        threading.Thread(target=self._ponte, daemon=True, name="corsie-sveglie").start()
        satelliti = self.satelliti
        presenti: set = set()
        while not self.fine.is_set():
            with satelliti._cond:
                pronti = [(x.satellite.get("id"), x.satellite.get("nome") or "")
                          for x in satelliti.collegati if x.pronto and not x.chiuso.is_set()]
            for sid, nome in pronti:
                if f"sat:{sid}" not in self.smist.corsie:
                    self.crea(sid, nome)
            self._voce_di_chi_va(presenti, {f"sat:{sid}" for sid, _ in pronti})
            self.fine.wait(0.3)
        if self.uscite:
            raise self.uscite[0]


def main():
    trattieni_notify_socket()          # i processi figli non devono parlare a systemd
    avvio = Avvio()
    avvio.prepara()
    avvio.esegui()
