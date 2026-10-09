"""
Tool nativi di Calliope: specifica e contesto.

Un tool nativo è una funzione Python che vive nel processo di Calliope e ha accesso
al suo stato interno (voiceprint, voce, sessione). Vedi docs/architettura-tool.md.
"""

from dataclasses import dataclass, field
from typing import Any, Callable
from ..testi import RANK


@dataclass
class ToolContext:
    """Ciò che i tool nativi possono leggere o usare del processo."""
    cfg: Any            # Config
    speakers: Any       # SpeakerRegistry
    speaker_ctx: Any    # SpeakerContext
    speaker: Any        # Speaker (per cambiare voce)
    memory: Any = None  # Memory (memory.py): fatti per persona
    agenda: Any = None  # Agenda (agenda.py): timer, promemoria, appuntamenti
    liste: Any = None   # Liste (liste.py): spesa, cose da fare… della casa
    biblioteca: Any = None  # Biblioteca (biblioteca.py): Wikipedia offline
    pc: Any = None      # {nome: PCExecutor} (calliope/pc/): i PC comandati a voce
    documenti: Any = None  # Documenti (calliope/documenti/): Word, Excel e PDF a voce
    casa: Any = None    # HomeBackend (calliope/casa/): la casa via Home Assistant, o None
    capacita: Any = None   # Registro (calliope/capacita.py): cosa funziona e cosa manca
    installazioni: Any = None  # Installazioni (calliope/installa/): download dal catalogo
    schermi: Any = None  # Schermi (calliope/schermi/): le schede sugli schermi abbinati, o None
    lavori: Any = None   # Lavori (calliope/agenti/): i lavori delegati a un agente, o None
    archivio: Any = None  # Archivio (calliope/archivio/): i documenti di casa, o None
    ufficio: Any = None  # Ufficio (calliope/ufficio/): modelli, rubrica, fatture, o None
    web: Any = None      # Web (calliope/web/): la ricerca su internet con SearXNG, o None
    estensioni: Any = None  # Estensioni (calliope/estensioni/): funzioni aggiunte, o None
    # ArchivioConversazioni (calliope/conversazioni.py): le conversazioni passate, o None
    conversazioni: Any = None
    # Modalita (calliope/modalita.py, 05/10): la modalità cambiata a voce, o None
    modalita: Any = None
    # La conversazione prima della domanda, [(ruolo, testo)] (la imposta Brain): i dati di un
    # lavoro delegato
    storia: list = field(default_factory=list)
    # La risposta precedente (la imposta Brain a ogni risposta): {"testo", "tool"}, per
    # «fammelo leggere» sullo schermo
    risposta_precedente: dict = field(default_factory=dict)
    # Numero della risposta in corso (lo imposta Brain): un'installazione proposta in una
    # risposta si può avviare solo nella successiva
    turno: int = 0
    # L'id nell'archivio della conversazione in corso (lo imposta Brain, 08/10), o None: il modo
    # cronologico di conversazione_cerca la salta (è già nella storia)
    conv_archivio: Any = None
    # Il tool dell'azione in sospeso di questo turno (lo imposta Brain): solo per lui un «sì»
    # breve di chi amministra vale come conferma (calliope/conferme.py, 04/10)
    tool_in_sospeso: str | None = None
    # La frase detta da chi parla in questo turno (la imposta Brain): ai tool serve quando
    # il modello riformula il parametro e perde un dettaglio («spiegamelo in modo semplice»)
    user_text: str = ""
    # Regole deterministiche scattate in questo turno (correzioni degli argomenti, «tutti»,
    # riscritture della casa…): Brain le azzera a ogni risposta e le passa al registro dei
    # turni. Vedi note_rule.
    regole: list = field(default_factory=list)
    # Le foto della conversazione (05/10, calliope/immagini.py: Album di Brain, che lo imposta
    # a ogni risposta) e i numeri di quelle da far vedere al modello in questo turno: un tool
    # che cattura (pc_guarda) o rimanda una foto (immagine_guarda) ne aggiunge il numero
    immagini: Any = None
    immagini_viste: list = field(default_factory=list)
    # I file allegati della conversazione (05/10, calliope/allegati.py: Allegati di Brain)
    allegati: Any = None
    # Il cassetto dei file per persona (08/10, calliope/cassetto.py: Cassetto), o None
    cassetto: Any = None
    # Quello che la politica dei tool sa del turno (calliope/politica.Turno: la frase, le fonti
    # non fidate nella conversazione, la proposta in sospeso). Lo imposta Brain prima di ogni
    # tool; senza (chiamate del codice) la politica ferma solo i tool vietati
    politica: Any = None
    # La chiamata in corso è già stata confermata dalla persona (politica.accettata, 06/10): un
    # tool con il suo «Procedo?» non lo chiede di nuovo. Lo imposta la politica, solo per la
    # durata della chiamata
    politica_accettata: bool = False
    # I tool di Calliope (ToolRegistry, lo imposta Brain): l'analisi di una richiesta di lavoro
    # (calliope/agenti/richiesta.py, 06/10) ci cerca una funzione che la fa già
    strumenti: Any = None
    # Frase d'attesa per un tool che a volte è lento (06/10: l'analisi della richiesta): la
    # imposta Brain durante la chiamata, se in questa risposta non si è ancora detto niente;
    # il tool la chiama solo quando serve davvero. None = niente frase
    attesa: Any = None
    # La scheda del risultato di un lavoro mandata in questa risposta (07/10, lavoro_risultato):
    # (turno, frase, scheda, mittente). Uno schermo_mostra «risposta» nella stessa risposta
    # rimanda questa invece di coprirla con la risposta detta
    scheda_risultato: Any = None
    # Il lavoro dell'agente appena detto (07/10, Brain.LAVORO_MSG): {"lavoro", "titolo",
    # "avvisato", "parole"} in questa risposta, o None. documento_crea lo ricorda una volta al
    # modello
    lavoro_turno: Any = None
    # L'ultimo errore l'ha scritto il registro (09/10, tools/dialogo.py: argomenti contro lo
    # schema o eccezione del tool), non il tool: niente dati, quindi niente busta dei dati non
    # fidati. Brain lo azzera prima di ogni chiamata e lo legge dopo
    errore_registro: bool = False



def note_rule(ctx, name: str):
    """Segna che una regola sul testo ha deciso o corretto qualcosa in questo turno."""
    rules = getattr(ctx, "regole", None)
    if isinstance(rules, list):
        rules.append(name)


# Scritto da uno schermo personale (03/10): ciò che vuole la voce riconosciuta di chi amministra
# non passa con il solo scritto. La domanda finisce con «?»: diventa un'azione in sospeso, e
# la risposta a voce richiama il tool, che rifà i suoi controlli sulla voce di quella frase
SCRITTO_VOCE = ("Me l'hai scritto, ma per {cosa} mi serve la tua voce: me lo chiedi a voce, "
                "con una frase intera?")


def scritto(ctx) -> bool:
    """La richiesta di questo turno è arrivata scritta da uno schermo personale."""
    return getattr(getattr(ctx, "speaker_ctx", None), "identified_by", None) == "schermo"


def serve_la_voce(ctx, tool: str, argomenti: dict | None, cosa: str,
                  livello: str = "amministra") -> dict | None:
    """Il risultato da dare se la richiesta è scritta ma vuole la voce di chi ha `livello`
    (installazioni, fatture, schermo personale, codice all'agente): conferma a voce con
    l'azione in sospeso. None se non è scritta, o se chi scrive non avrebbe quel livello
    nemmeno a voce (allora vale il rifiuto di sempre)."""
    sc = getattr(ctx, "speaker_ctx", None)
    if getattr(sc, "identified_by", None) != "schermo":
        return None
    if RANK.get(getattr(sc, "profile_level", "ospite") or "ospite", 0) < RANK.get(livello, 2):
        return None
    note_rule(ctx, "scritto_serve_voce")
    frase = SCRITTO_VOCE.format(cosa=cosa)
    return {"ok": False, "fatto": "NIENTE: l'azione NON è stata eseguita: serve la voce",
            "conferma": frase, "risposta_finale": frase,
            "in_sospeso": {"domanda": "Me lo chiedi a voce?", "cosa": cosa, "tool": tool,
                           "argomenti": dict(argomenti or {})}}


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict                       # JSON schema, campi vincolati
    func: Callable                         # funzione Python nativa
    risk: str = "lettura"                  # "lettura" | "azione" | "sensibile"
    levels: frozenset[str] = frozenset({"ospite"})
    requires_internet: bool = False        # principio 5 della visione
    # Frasi brevi che Calliope dice appena il modello chiama il tool, per coprire l'attesa
    # della seconda passata («Vediamo…»). Solo per i tool lenti (biblioteca): su ora o
    # calcoli sarebbe tempo perso. Le dice il codice, non il modello, e non entrano
    # nella storia. Vuoto = nessun annuncio.
    announce: tuple[str, ...] = ()
    # Argomenti da non scrivere mai nei log e nel registro dei turni (il codice di
    # abbinamento di uno schermo): Brain li maschera
    segreti: tuple[str, ...] = ()
    # Tool che leggono dati personali (l'archivio dei documenti di casa): argomenti, risultato e
    # risposta non vanno né nel registro dei turni né nel terminale, solo il nome del tool
    riservato: bool = False
    # Tool che portano testo scritto fuori da Calliope (web_cerca: i siti internet), dove
    # possono esserci istruzioni per i modelli. Dopo un loro risultato Brain non esegue azioni
    # nella stessa risposta (politica.DOPO_DATO) e a risposta finita li toglie dalla storia
    non_fidato: bool = False
    # Politica unica dei tool (05/10, calliope/politica.py): la classe del tool («sicuro»,
    # «azione», «pericoloso», «vietato») per quelli registrati a runtime (le estensioni); i tool
    # di Calliope la hanno nella tabella politica.CLASSI. Senza nessuna delle due vale
    # «pericoloso». `fonte`: il risultato è un dato non fidato di questa fonte
    # (provenienza.FONTI: «web», «estensione», «archivio», «agente»…); `chiave`: gli argomenti
    # importanti per la provenienza degli argomenti
    classe: str | None = None
    fonte: str | None = None
    chiave: tuple[str, ...] = ()
    # La forma degli argomenti scelti dal modello, ricondotta a quella del tool prima dei
    # permessi e della politica (08/10: estensione_gestisci «attiva» → «approva»): (ctx,
    # argomenti) → argomenti. Solo conversioni di forma (principio 10), con una regola nel
    # registro dei turni; None = niente
    prepara: Callable | None = None
    # Gli argomenti che nominano qualcosa (08/10, calliope/argomenti_incerti.py): {argomento:
    # tipo} con tipo «luogo», «casa», «estensione», «contatto», «persona», «file» o «valore».
    # Su questi si misura quanto Whisper era sicuro delle parole e si cerca il nome noto più
    # vicino; dopo un esito vuoto il modello riceve «forse intendeva…». Un argomento oggetto
    # vale per ogni suo valore di testo, con il tipo dal nome del campo. Vuoto = nessuno
    nomi: dict = field(default_factory=dict)

    def schema(self) -> dict:
        """Schema del tool nel formato OpenAI (Ollama lo accetta sia su /api/chat sia su /v1)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
