"""
Registro delle capacità di Calliope: cosa funziona in questa installazione, cosa manca e
il prossimo passo (01/10/2026).

Ogni capacità (modello linguistico, trascrizione, voce, wake word, chi parla, audio,
memoria, biblioteca, PC, documenti, casa, schermi, agenti) dichiara da cosa dipende e ha uno stato tra:

  attiva          funziona
  da_configurare  c'è tutto il necessario, manca un'impostazione o un passo di chi amministra
  mancante        manca una libreria, un file o un modello
  guasta          dovrebbe funzionare ma non va (Ollama giù, Home Assistant irraggiungibile…)

con un motivo breve (per i log), un prossimo passo concreto adatto alla voce e i dettagli
per chi amministra. Una sola fonte, tre viste:
  - all'avvio un riassunto compatto (`Registro.riassunto`, `righe_avvio`), al posto delle
    stampe di ogni caricamento;
  - da terminale `python -m calliope.stato` (tabella, passi, `--json`), anche su una
    macchina appena installata: una libreria assente è «mancante», non un crash;
  - a voce il tool `calliope_stato` (calliope/tools/stato.py), filtrato per livello.

Il prompt di sistema riceve da qui un elenco breve e stabile di cosa c'è e cosa non c'è
(`testo_prompt`): cambia solo dopo un'installazione o un riavvio, così la cache del
prefisso di Ollama regge.

I controlli (`controlla`) sono rapidi e in sola lettura: nessuna rete esterna (Ollama
locale sì, con un tempo massimo breve), nessun file scritto. Questo modulo non importa
niente di pesante: numpy, Whisper, Piper e gli altri si guardano solo dentro i controlli.
"""

import importlib
import importlib.util
import json
import os
import platform
import re
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

STATI = ("attiva", "da_configurare", "mancante", "guasta")


@dataclass(frozen=True)
class Definizione:
    titolo: str                       # «la biblioteca offline», per la voce
    breve: str                        # «biblioteca», per il riassunto e il prompt
    dipende: tuple[str, ...]          # da cosa dipende, per la tabella e i dettagli
    sa_fare: str = ""                 # per «cosa sai fare?» quando è attiva
    ospite: str = ""                  # cosa può chiedere un ospite ("" = niente)
    utente: bool = True               # si vede da chi parla (va nel prompt)
    installa: tuple[str, ...] = ()    # azioni del catalogo (calliope/installa) che la sistemano


# Ordine = ordine di tabella, riassunto e risposte a voce
DEFINIZIONI: dict[str, Definizione] = {
    "llm": Definizione("il modello linguistico", "modello linguistico",
                       ("Ollama in locale", "il modello di llm_model"), utente=False,
                       installa=("modello_llm",)),
    "stt": Definizione("la trascrizione della voce", "trascrizione",
                       ("faster-whisper", "il modello Whisper", "GPU NVIDIA o, più lenta, CPU"),
                       utente=False, installa=("whisper_riserva",)),
    "voce": Definizione("la voce", "voce", ("piper-tts", "le voci in voices/"),
                        sa_fare="parlare con voci diverse", utente=False,
                        installa=("voce_serena_alta", "voce_serena", "voce_paola",
                                  "voce_riccardo")),
    "wake": Definizione("il risveglio con il nome", "wake word",
                        ("onnxruntime", "il modello in wakeword/modelli"), utente=False),
    "chi_parla": Definizione("il riconoscimento di chi parla", "chi parla",
                             ("onnxruntime", "il modello CAM++ in models/speaker",
                              "le persone registrate in speakers.json"),
                             sa_fare="riconoscere chi parla dalla voce", utente=False,
                             installa=("modello_chi_parla",)),
    "audio": Definizione("microfono e altoparlanti", "audio", ("sounddevice (PortAudio)",),
                         utente=False),
    "satellite": Definizione("i satelliti (microfono e casse in rete)", "satelliti",
                             ("websockets", "il server dei satelliti (satellite_porta)",
                              "il certificato in rete (satellite.crt)",
                              "almeno un satellite abbinato"), utente=False),
    "memoria": Definizione("memoria, agenda e liste", "memoria e agenda",
                           ("SQLite", "il file di memory_db"),
                           sa_fare="timer, promemoria, appuntamenti, liste e cose da ricordare",
                           ospite="i timer"),
    "biblioteca": Definizione("la biblioteca offline", "biblioteca offline",
                              ("i file ZIM in biblioteca/ (Wikipedia, Vikidia, Wikizionario)",
                               "gli indici di ricerca in biblioteca/indici/"),
                              sa_fare="cercare fatti precisi e significati delle parole nella "
                                      "biblioteca offline",
                              ospite="i fatti della biblioteca offline",
                              installa=("biblioteca", "biblioteca_mini", "biblioteca_completa",
                                        "biblioteca_ragazzi", "biblioteca_dizionario",
                                        "biblioteca_aggiorna", "biblioteca_indice",
                                        "fonte_wikisource",
                                        "fonte_wikibooks", "fonte_wikiquote",
                                        "fonte_wikivoyage", "fonte_wikiversita",
                                        "fonte_wikimed", "fonte_gutenberg",
                                        "fonte_wikipedia_immagini", "pulizia")),
    "pc": Definizione("il controllo del computer", "controllo del computer",
                      ("Windows", "pycaw, comtypes, pywin32, psutil, screen_brightness_control, "
                                  "winrt"),
                      sa_fare="volume, musica, luminosità, programmi e file del computer"),
    "documenti": Definizione("i documenti Word, Excel e PDF", "documenti",
                             ("python-docx", "openpyxl", "fpdf2"),
                             sa_fare="preparare lettere, tabelle ed elenchi in Word, Excel o PDF"),
    "casa": Definizione("la casa", "casa (Home Assistant)",
                        ("websockets", "Home Assistant", "casa_url", "il token in segreti.yaml"),
                        sa_fare="comandare luci, tapparelle e termostato di casa"),
    "schermi": Definizione("gli schermi", "schermi",
                           ("starlette e uvicorn", "il server delle schede (schermi_porta)",
                            "almeno uno schermo abbinato"),
                           sa_fare="mostrare su uno schermo liste, timer, voci della "
                                   "biblioteca, documenti e lo stato della casa",
                           ospite="mostrare sullo schermo timer, calcoli e voci della "
                                  "biblioteca"),
    "agenti": Definizione("gli agenti per i lavori lunghi", "agenti (lavori lunghi)",
                          ("un Ollama per l'agente: la DGX via tunnel SSH (dgx.yaml) o "
                           "agenti_url", "il client OpenSSH", "il modello dell'agente"),
                          sa_fare="affidare a un agente lavori lunghi: programmi, relazioni e "
                                  "documenti da un modello"),
    "archivio": Definizione("l'archivio dei documenti di casa", "archivio dei documenti di casa",
                            ("la cartella archivio_cartella", "pypdfium2 e Pillow",
                             "il modello grande (OCR ed estrazione): quello degli agenti o "
                             "archivio_url"),
                            sa_fare="trovare bollette, ricevute, contratti, polizze, garanzie e "
                                    "scadenze nei documenti di casa, e sommare le spese"),
    "ufficio": Definizione("modelli, rubrica e fatture", "modelli e fatture",
                           ("i documenti in PDF (fpdf2)", "docxtpl e python-pptx per i modelli "
                            "Word e PowerPoint", "fatture_emittente in calliope.locale.yaml",
                            "lo schema XSD di FatturaPA (facoltativo)"),
                           sa_fare="compilare fatture elettroniche, preventivi, DDT e modelli "
                                   "di documento, e tenere la rubrica dei clienti"),
    "conversazioni": Definizione("l'archivio delle conversazioni", "archivio delle conversazioni",
                                 ("SQLite (conversazioni_db)", "un modello di embedding sul "
                                  "server del modello (conversazioni_embedding), facoltativo"),
                                 sa_fare="ritrovare cosa ci siamo detti nelle conversazioni "
                                         "passate", utente=False),
    "web": Definizione("la ricerca su internet", "ricerca web",
                       ("SearXNG (web_searxng_url: calliope motore searxng avvia)",
                        "internet", "httpx"),
                       sa_fare="cercare su internet meteo, notizie, risultati, orari e prezzi"),
}


@dataclass
class Capacita:
    nome: str
    stato: str
    motivo: str = ""
    prossimo_passo: str = ""
    dettagli: dict = field(default_factory=dict)

    @property
    def definizione(self) -> Definizione:
        return DEFINIZIONI.get(self.nome) or Definizione(self.nome, self.nome, ())

    @property
    def attiva(self) -> bool:
        return self.stato == "attiva"

    def as_dict(self) -> dict:
        d = self.definizione
        return {"nome": self.nome, "titolo": d.titolo, "stato": self.stato,
                "motivo": self.motivo, "prossimo_passo": self.prossimo_passo,
                "dipende": list(d.dipende), "installa": list(d.installa),
                "dettagli": self.dettagli}


class Registro:
    """Le capacità di questa esecuzione. Thread-safe: un'installazione finita in secondo
    piano la aggiorna. `versione` cresce a ogni cambiamento (il prompt si rifà solo allora)."""

    def __init__(self):
        self._voci: dict[str, Capacita] = {}
        self._dinamiche: dict = {}
        self._lock = threading.RLock()
        self.versione = 0

    def segnala(self, nome: str, stato: str, motivo: str = "", prossimo_passo: str = "",
                dettagli: dict | None = None) -> Capacita:
        if stato not in STATI:
            raise ValueError(f"stato sconosciuto: {stato}")
        cap = Capacita(nome, stato, motivo or "", prossimo_passo or "", dict(dettagli or {}))
        with self._lock:
            old = self._voci.get(nome)
            if old is None or (old.stato, old.motivo) != (cap.stato, cap.motivo):
                self.versione += 1
            self._voci[nome] = cap
        return cap

    def da_dict(self, d: dict) -> Capacita:
        """Da un risultato di un controllo ({stato, motivo, prossimo_passo, dettagli})."""
        return self.segnala(d["nome"], d["stato"], d.get("motivo", ""),
                            d.get("prossimo_passo", ""), d.get("dettagli"))

    def dinamica(self, nome: str, fn):
        """Capacità che cambia da sola (la casa si collega in secondo piano): `fn()` dà lo
        stato fresco per le viste a voce e da terminale. Il prompt usa l'ultimo segnalato."""
        self._dinamiche[nome] = fn

    def get(self, nome: str, fresca: bool = False) -> Capacita | None:
        if fresca and nome in self._dinamiche:
            try:
                d = self._dinamiche[nome]()
                cap = Capacita(nome, d["stato"], d.get("motivo", ""),
                               d.get("prossimo_passo", ""), dict(d.get("dettagli") or {}))
                with self._lock:
                    self._voci[nome] = cap    # niente versione: il prompt non cambia
                return cap
            except Exception:  # noqa: BLE001 — una vista non deve rompersi
                pass
        with self._lock:
            return self._voci.get(nome)

    def tutte(self, fresche: bool = False) -> list[Capacita]:
        names = [n for n in DEFINIZIONI if n in self._voci]
        names += [n for n in self._voci if n not in DEFINIZIONI]
        return [self.get(n, fresca=fresche) for n in names]

    def __len__(self):
        return len(self._voci)

    # ── viste ──
    def riassunto(self, fresche: bool = False) -> str:
        """Una riga per l'avvio: «Capacità: 10 attive su 11; manca: biblioteca (…)»."""
        caps = self.tutte(fresche=fresche)
        attive = sum(c.attiva for c in caps)
        parti = [f"Capacità: {attive} attive su {len(caps)}"]
        for stato, etichetta in (("guasta", "non funziona"), ("mancante", "manca"),
                                 ("da_configurare", "da configurare")):
            these = [c for c in caps if c.stato == stato]
            if these:
                parti.append(f"{etichetta}: " + ", ".join(
                    f"{c.definizione.breve} ({c.motivo})" if c.motivo else c.definizione.breve
                    for c in these))
        return "; ".join(parti)

    def righe_avvio(self) -> list[str]:
        """Le righe stampate all'avvio: il riassunto e, per le capacità attive, i dettagli
        che servono a colpo d'occhio (voci, file, formati), poi i passi di quelle che non
        vanno. Per tutto il resto: python -m calliope.stato.

        Le capacità dinamiche (la casa) si rileggono adesso: segnalate al caricamento,
        all'avvio dicevano «collegamento in corso» anche con la riga «[CASA] Collegata…»
        stampata subito sopra (01/10)."""
        out = ["[CAPACITÀ] " + self.riassunto(fresche=True)]
        for c in self.tutte():
            if c.attiva and c.motivo:
                out.append(f"   {c.definizione.breve}: {c.motivo}")
        for c in self.tutte():
            if not c.attiva and c.prossimo_passo:
                out.append(f"   {c.definizione.breve}: {c.prossimo_passo}")
        return out

    def as_json(self, fresche: bool = True) -> list[dict]:
        return [c.as_dict() for c in self.tutte(fresche=fresche)]


# Il registro di questa esecuzione: i caricamenti (load_biblioteca, load_pc…) ci segnalano
# il loro stato. Le prove ne creano uno nuovo con `nuovo_registro()`.
REGISTRO = Registro()


def nuovo_registro() -> Registro:
    global REGISTRO
    REGISTRO = Registro()
    return REGISTRO


def segnala(nome: str, stato: str, motivo: str = "", prossimo_passo: str = "",
            dettagli: dict | None = None) -> Capacita:
    """Segnala lo stato di una capacità nel registro di questa esecuzione."""
    return REGISTRO.segnala(nome, stato, motivo, prossimo_passo, dettagli)


# ─────────────────────────── PROMPT ───────────────────────────
# Cose che Calliope non sa fare in nessuna installazione: senza, il modello prometteva di
# mandare messaggi o di cercare su internet (problema noto delle capacità inventate)
_MAI = "mandare messaggi o email, telefonare, fare acquisti, cercare su internet"
# Con la ricerca web (web_cerca, 03/10) internet si usa: resta il resto
_MAI_CON_WEB = "mandare messaggi o email, telefonare, fare acquisti"


def _da_tool(tools) -> dict[str, bool]:
    """Le capacità visibili all'utente ricavate dai tool registrati (senza registro: prove)."""
    names = set(tools or ())
    # L'ufficio (03/10) solo se c'è: le prove senza ufficio tengono il prompt misurato prima
    extra = {"ufficio": True} if "modello_compila" in names else {}
    # La ricerca web (03/10) pure: senza, i prompt misurati prima restano uguali
    if "web_cerca" in names:
        extra["web"] = True
    return {**{"memoria": "promemoria_imposta" in names,
            "biblioteca": "biblioteca_cerca" in names,
            "pc": any(n.startswith("pc_") for n in names),
            "documenti": "documento_crea" in names,
            "casa": "casa_comando" in names,
            "schermi": "schermo_mostra" in names,
            "agenti": "delega_lavoro" in names,
            "archivio": "archivio_cerca" in names}, **extra}


def testo_prompt(registro: Registro | None = None, tools=()) -> str:
    """Elenco breve e stabile per il prompt di sistema: cosa funziona e cosa non c'è in
    questa installazione. Con il registro vale il suo stato; senza (le prove che costruiscono
    il Brain a mano) si ricava dai tool registrati. Stabile: dipende solo da cosa è
    installato e configurato, non dallo stato del momento (Home Assistant giù non lo cambia)."""
    names = set(tools or ())
    if registro is not None and len(registro):
        presenti = {c.nome: c.attiva for c in registro.tutte()
                    if c.definizione.utente}
        # La casa conta come presente se i suoi tool ci sono (HA può essere giù per poco)
        if "casa" in presenti and "casa_comando" in names:
            presenti["casa"] = True
        # Gli schermi pure: con il server acceso ma nessuno schermo abbinato i tool ci sono
        # (servono proprio ad abbinarlo), e il prompt non cambia quando se ne abbina uno
        if "schermi" in presenti and "schermo_mostra" in names:
            presenti["schermi"] = True
        # Gli agenti pure: con la VPN spenta i tool restano (la delega spiega cosa manca), e il
        # prompt non cambia quando la DGX va e viene
        if "agenti" in presenti and "delega_lavoro" in names:
            presenti["agenti"] = True
        # L'archivio pure: con il modello grande giù le domande sui documenti già letti vanno
        if "archivio" in presenti and "archivio_cerca" in names:
            presenti["archivio"] = True
        # E il PC del satellite (esecutore remoto, 03/10): i tool pc_* restano anche quando il
        # satellite non è collegato, e lo dicono loro
        if "pc" in presenti and any(n.startswith("pc_") for n in names):
            presenti["pc"] = True
        # La ricerca web: con il tool c'è (SearXNG o internet possono mancare per poco, e lo
        # dice il tool); senza il tool è «non disponibile»
        if "web" in presenti:
            presenti["web"] = "web_cerca" in names
    else:
        presenti = _da_tool(names)
    attive = [DEFINIZIONI[n].breve for n, ok in presenti.items() if ok and n in DEFINIZIONI]
    assenti = [DEFINIZIONI[n].breve for n, ok in presenti.items() if not ok and n in DEFINIZIONI]
    parti = []
    if attive:
        parti.append("In questa installazione funzionano: " + ", ".join(attive) + ".")
    if assenti:
        parti.append("Non disponibili qui: " + ", ".join(assenti) + ".")
    parti.append(f"Non sai {_MAI_CON_WEB if 'web_cerca' in names else _MAI}.")
    # Con il solo elenco delle assenti il modello rispondeva «non posso collegarmi alla
    # domotica» senza chiamare casa_integrazione (4 errori su 46 in prova_casa_ha_ollama,
    # 01/10): perché manca e come averla lo dicono i tool
    helpers = [n for n in ("calliope_stato", "casa_integrazione") if n in names]
    if helpers:
        parti.append("Se invece chiedono perché qualcosa non funziona, come averlo o "
                     "collegarlo, o «cosa sai fare?» e «cosa manca?», non rispondere a "
                     "memoria: "
                     + ("chiama calliope_stato" if "calliope_stato" in names else "")
                     + ((", e per la casa, la domotica o Home Assistant casa_integrazione"
                         if "calliope_stato" in names else
                         "per la casa, la domotica o Home Assistant chiama casa_integrazione")
                        if "casa_integrazione" in names else "") + ".")
    # Senza, «scarica la biblioteca» chiamava a volte calliope_stato (1 volta su 2, 01/10)
    if "installa_proponi" in names:
        parti.append("Per scaricare, installare o aggiornare biblioteca, voci o modelli chiama "
                     "installa_proponi.")
    return " ".join(parti)


# ─────────────────────────── COSA SI PUÒ AGGIUNGERE ───────────────────────────
# Le fonti della biblioteca utili alla ricerca, con a cosa servono (per la voce). Le altre
# fonti del catalogo si contano soltanto: la ricerca non le usa ancora
_USO_FONTE = {"biblioteca_mini": "Wikipedia ridotta, la base della biblioteca",
              "biblioteca_completa": "Wikipedia completa, per i dati che mancano nella ridotta",
              "biblioteca_ragazzi": "Vikidia, per le spiegazioni semplici",
              "biblioteca_dizionario": "il Wikizionario, per i significati delle parole",
              "fonte_wikiquote": "Wikiquote, per le citazioni"}


def aggiungibili(cfg) -> dict:
    """Cosa si può ancora installare dal catalogo (calliope/installa/catalogo.py), per «cosa
    manca?» (01/10: rispondeva solo «funziona tutto quello che è installato»). Solo file che
    non ci sono: {"utili": [(azione, frase)], "altre": [nomi], "voci": [(azione, nome)]}.
    Sola lettura, nessuna rete."""
    out = {"utili": [], "altre": [], "voci": []}
    try:
        # Il modulo, non la funzione `catalogo` che il pacchetto installa esporta
        cat = importlib.import_module(__package__ + ".installa.catalogo")
    except Exception:  # noqa: BLE001 — una vista non deve rompersi
        return out
    try:
        present = {f.id: cat.file_fonte(cfg, f) is not None for f in cat.FONTI}
        if not (present.get("biblioteca_mini") or present.get("biblioteca_completa")):
            # Senza Wikipedia si propone la biblioteca intera: le parti si dicono dopo
            out["utili"].append(("biblioteca", "la biblioteca offline, con Wikipedia, Vikidia "
                                               "e il Wikizionario"))
        else:
            for f in cat.RICERCA:
                if not present.get(f.id) and f.id in _USO_FONTE:
                    out["utili"].append((f.id, _USO_FONTE[f.id]))
        for f in cat.ALTRE:
            if present.get(f.id) or f.nota:          # la facoltativa con le immagini no
                continue
            if f.richiesta and cat.fonte_attiva(cfg, f) and f.id in _USO_FONTE:
                out["utili"].append((f.id, _USO_FONTE[f.id]))
            else:
                out["altre"].append(f.titolo.split(",")[0])
        azioni = cat.catalogo(cfg)
        for vid, name, _q, _onnx, _js in cat.VOCI:
            a = azioni.get(vid)
            if a and not all(Path(fc.dest).is_file() for fc in a.files):
                if all(name.capitalize() != n for _, n in out["voci"]):
                    out["voci"].append((vid, name.capitalize()))
    except Exception:  # noqa: BLE001
        pass
    # Una voce già installata in un'altra qualità non è «una voce in più»
    try:
        from .config import VOICE_MAP
        have = {n.split("-")[0] for n, p in VOICE_MAP.items() if _voice_files(p)}
        out["voci"] = [(v, n) for v, n in out["voci"] if n.lower() not in have]
    except Exception:  # noqa: BLE001
        pass
    return out


# ─────────────────────────── CONTROLLI ───────────────────────────
# Moduli da trattare come assenti (prove: «libreria mancante» senza disinstallarla)
_SENZA: set[str] = set()


def presente(modulo: str) -> bool:
    """Il modulo è installato? Solo la ricerca, senza importarlo (rapido)."""
    if modulo in _SENZA or sys.modules.get(modulo, 0) is None:
        return False
    try:
        return importlib.util.find_spec(modulo) is not None
    except (ImportError, ValueError):
        return False


def importa(modulo: str):
    """Importa il modulo, o None se manca o non si carica su questa macchina (una DLL che
    manca, un'architettura senza wheel): per i controlli è la stessa cosa."""
    if modulo in _SENZA:
        return None
    try:
        return importlib.import_module(modulo)
    except Exception:  # noqa: BLE001 — ImportError, OSError di una DLL…
        return None


def comando_libreria(pacchetti: str, extra: str | None = None) -> str:
    """Il comando per aggiungere una libreria facoltativa. Nell'installazione gestita di
    Linux (setup/linux/gestore.py, che imposta CALLIOPE_GESTITA) il venv è di uv e non ha
    pip: lì si aggiunge l'extra del pyproject, che resta anche dopo gli aggiornamenti."""
    if extra and os.environ.get("CALLIOPE_GESTITA"):
        return f"calliope extra {extra}"
    return f"pip install {pacchetti}"


def _arm() -> bool:
    return platform.machine().lower() in ("arm64", "aarch64")


# Il nome di una chiave della configurazione tra parentesi in un motivo («spento
# (archivio_enabled)», «spento (telefono_enabled: false)»): serve nel terminale e nei dettagli
_CHIAVE_TRA_PARENTESI = re.compile(r"\s*\((?:[a-z][a-z0-9]*_[a-z0-9_]+)(?::[^)]*)?\)")
_CHIAVE = re.compile(r"(?<![\w./\-])([a-z][a-z0-9]*(?:_[a-z0-9]+)+)(?![\w./\-])")


def a_voce(testo: str) -> str:
    """Un motivo o un passo da dire a voce (06/10, prova e2e: «perché spento
    (archivioenabled)»: il TTS toglieva il trattino basso e leggeva una parola sola). La chiave
    tra parentesi va via («spento» diventa «spento nella configurazione»), le altre chiavi si
    leggono a parole («casa_url» → «casa url»)."""
    t = _CHIAVE_TRA_PARENTESI.sub(" nella configurazione", testo or "")
    return _CHIAVE.sub(lambda m: m.group(1).replace("_", " "), t)


def _r(_nome, _stato, _motivo="", _passo="", **dettagli) -> dict:
    return {"nome": _nome, "stato": _stato, "motivo": _motivo, "prossimo_passo": _passo,
            "dettagli": dettagli}


def _gb(n: int | float | None) -> str:
    if not n:
        return "0 GB"
    if n < 1e9:
        return f"{n / 1e6:.0f} MB"
    return f"{n / 1e9:.1f} GB".replace(".", ",")


def check_llm(cfg, timeout: float = 1.5) -> dict:
    httpx = importa("httpx")
    if httpx is None:
        return _r("llm", "mancante", "manca la libreria httpx",
                  "Va installata nell'ambiente di Calliope: pip install httpx.")
    model = cfg.llm_model
    try:
        if cfg.llm_backend == "openai":
            r = httpx.get(cfg.llm_base_url.rstrip("/") + "/models", timeout=timeout)
            r.raise_for_status()
            names = [m.get("id") for m in r.json().get("data", [])]
            size = None
        else:
            r = httpx.get(cfg.llm_native_url.rstrip("/") + "/api/tags", timeout=timeout)
            r.raise_for_status()
            models = r.json().get("models", [])
            names = [m.get("name") for m in models]
            size = next((m.get("size") for m in models
                         if m.get("name") in (model, f"{model}:latest")), None)
    except Exception as e:  # noqa: BLE001
        if cfg.llm_backend == "openai":      # vLLM o llama-server (DGX Linux, 02/10)
            return _r("llm", "guasta", "il server del modello non risponde",
                      "Avvia il server del modello (vLLM: setup/linux/motore/vllm.sh voce "
                      "avvia) o correggi llm_base_url, poi riavviami.",
                      indirizzo=cfg.llm_base_url, errore=type(e).__name__)
        return _r("llm", "guasta", "Ollama non risponde",
                  "Avvia Ollama, l'app o il comando ollama serve, poi riavviami.",
                  indirizzo=cfg.llm_native_url if cfg.llm_backend != "openai"
                  else cfg.llm_base_url, errore=type(e).__name__)
    if model not in names and f"{model}:latest" not in names and cfg.llm_backend == "openai":
        return _r("llm", "mancante", f"il server non serve il modello {model}",
                  f"llm_model va cambiato nel nome servito ({', '.join(map(str, names[:3]))}), "
                  f"oppure il server va avviato con quel modello.", modello=model,
                  installati=len(names))
    if model not in names and f"{model}:latest" not in names:
        return _r("llm", "mancante", f"manca il modello {model}",
                  f"Va scaricato il modello {model}: da terminale python -m calliope.stato "
                  f"--installa modello_llm, oppure ollama pull {model}.",
                  modello=model, installati=len(names))
    extra = {"dimensione": _gb(size)} if size else {}
    if cfg.llm_backend != "openai":
        # Più modelli di quanti Ollama ne tiene (06/10, prova e2e: voce, guardiano, rilevatore
        # ed embedding su un Ollama da 3): si scacciano a vicenda e i turni rallentano
        try:
            from .ollama_carico import avviso
            a = avviso(cfg, timeout=timeout)
        except Exception:  # noqa: BLE001 — un avviso non rompe il controllo
            a = None
        if a:
            return _r("llm", "attiva", f"{a['frase']}. {a['passo']}", a["passo"],
                      modello=model, backend=cfg.llm_backend, ollama=a["dettagli"], **extra)
    return _r("llm", "attiva", "", "", modello=model, backend=cfg.llm_backend, **extra)


def _whisper_in_cache(model: str, cfg=None) -> bool | None:
    """Il modello Whisper è già sul disco (installato dal catalogo in models/whisper, o nella
    cache di Hugging Face)? None = non si sa."""
    if os.path.isdir(model):
        return True
    if cfg is not None:
        try:
            from .installa.catalogo import whisper_locale
            if whisper_locale(cfg) is not None:
                return True
        except Exception:  # noqa: BLE001
            pass
    fw = importa("faster_whisper.utils")
    repo = getattr(fw, "_MODELS", {}).get(model) if fw else None
    if not repo:
        return None
    hub = importa("huggingface_hub.constants")
    cache = getattr(hub, "HF_HUB_CACHE", None) if hub else None
    if not cache:
        return None
    return (Path(cache) / ("models--" + repo.replace("/", "--"))).is_dir()


def passo_gpu() -> str:
    """Il prossimo passo per avere Whisper sulla GPU, secondo la piattaforma."""
    if sys.platform == "win32":
        return ("Se è il primo download del modello basta riavviare; altrimenti servono pip "
                "install nvidia-cublas-cu12 nvidia-cudnn-cu12.")
    if _arm():
        # CTranslate2 4.8.2 per Linux aarch64 su PyPI è compilato senza CUDA (02/10)
        return ("Su Linux ARM CTranslate2 è solo per CPU: per la GPU serve un server di "
                "trascrizione (stt_motore: server e stt_url in calliope.locale.yaml, vedi "
                "setup/linux/motore).")
    return ("Su Linux servono le librerie CUDA 12 (cuBLAS e cuDNN 9) visibili a "
            "CTranslate2, oppure un server di trascrizione (stt_motore: server).")


def _comando_installa(azione: str) -> str:
    """Il comando da terminale per un'azione del catalogo: `calliope stato --installa` nella
    installazione gestita di Linux, altrimenti python -m calliope.stato."""
    pre = "calliope stato" if os.environ.get("CALLIOPE_GESTITA") else "python -m calliope.stato"
    return f"{pre} --installa {azione}"


def riserva_whisper(cfg) -> tuple[str, str] | None:
    """Con Whisper su un server: il ripiego su CPU è pronto? None se sì, altrimenti (motivo,
    passo). Sulla DGX (02/10) il modello per la CPU non c'era: al primo guasto del server
    faster-whisper l'avrebbe scaricato (1,6 GB, la voce ferma per minuti, e senza internet
    nessuna trascrizione)."""
    if not presente("faster_whisper"):
        return ("senza ripiego su CPU: manca faster-whisper",
                "Per il ripiego su CPU: " + comando_libreria("faster-whisper") + ".")
    if _whisper_in_cache(cfg.whisper_model, cfg) is False:
        return (f"senza ripiego su CPU: manca il modello Whisper {cfg.whisper_model}",
                f"Per il ripiego su CPU scarica il modello di riserva: da terminale "
                f"{_comando_installa('whisper_riserva')}.")
    return None


def _check_stt_server(cfg, timeout: float = 1.5) -> dict:
    """Whisper su un server (stt_motore: server): risponde? Il ripiego su CPU vuole comunque
    faster-whisper (principio 7)."""
    det = {"modello": cfg.stt_modello, "dispositivo": "server", "indirizzo": cfg.stt_url}
    if not cfg.stt_url:
        return _r("stt", "da_configurare", "stt_motore è «server» ma manca stt_url",
                  "In calliope.locale.yaml metti stt_url, per esempio "
                  "http://127.0.0.1:8003/v1 (whisper.cpp), poi riavviami.", **det)
    httpx = importa("httpx")
    if httpx is None:
        return _r("stt", "mancante", "manca la libreria httpx",
                  "Va installata nell'ambiente di Calliope: pip install httpx.", **det)
    ripiego = "" if presente("faster_whisper") else " (e manca faster-whisper per il ripiego)"
    try:
        r = httpx.get(cfg.stt_url.rstrip("/") + "/models", timeout=timeout)
        if r.status_code in (404, 405, 501):
            # Risponde ma non ha /models: whisper.cpp (whisper-server), scelto sulla DGX il
            # 02/10 e prima segnato «non risponde». Il server c'è; il modello non si sa
            names = []
        else:
            r.raise_for_status()
            names = [m.get("id") for m in r.json().get("data", [])]
    except Exception as e:  # noqa: BLE001 — giù, o una risposta che non si capisce
        riserva = riserva_whisper(cfg)
        return _r("stt", "guasta", "il server di trascrizione non risponde: trascrivo su CPU"
                  + ripiego + (f" ({riserva[0]})" if riserva and not ripiego else ""),
                  "Avvia il server di trascrizione (whisper.cpp: calliope motore whisper "
                  "avvia, o setup/linux/motore/whisper.sh) o correggi stt_url."
                  + (" " + riserva[1] if riserva and not ripiego else ""),
                  errore=type(e).__name__, **det)
    if names and cfg.stt_modello not in names:
        return _r("stt", "mancante", f"il server non serve {cfg.stt_modello}",
                  f"Sul server va caricato {cfg.stt_modello}, oppure stt_modello va "
                  f"cambiato in uno di: {', '.join(map(str, names[:5]))}.", **det)
    riserva = riserva_whisper(cfg)
    return _r("stt", "attiva", riserva[0] if riserva else "", riserva[1] if riserva else "",
              riserva=not riserva, **det)


def check_stt(cfg) -> dict:
    if (getattr(cfg, "stt_motore", "locale") or "locale").lower() == "server":
        return _check_stt_server(cfg)
    if not presente("faster_whisper"):
        return _r("stt", "mancante", "manca faster-whisper",
                  "Va installata nell'ambiente di Calliope: pip install faster-whisper.")
    ct2 = importa("ctranslate2")
    gpus = 0
    try:
        gpus = ct2.get_cuda_device_count() if ct2 else 0
    except Exception:  # noqa: BLE001
        gpus = 0
    device = "cuda" if cfg.whisper_device == "cuda" and gpus else "cpu"
    cached = _whisper_in_cache(cfg.whisper_model, cfg)
    det = {"modello": cfg.whisper_model, "dispositivo": device}
    if cached is False:
        passo = ("Al primo avvio lo scarica faster-whisper da Hugging Face, poi resta in "
                 "cache: serve internet solo quella volta.")
        if device == "cpu" and cfg.whisper_device == "cuda" and sys.platform != "win32":
            # Sulla DGX (prima installazione, 02/10) il passo diceva solo del download per
            # la CPU: lì la strada giusta è il server, la CPU è il ripiego
            passo = passo_gpu() + " Senza server: " + passo[0].lower() + passo[1:]
        return _r("stt", "mancante", f"modello Whisper {cfg.whisper_model} non ancora scaricato",
                  passo, **det)
    if device == "cpu" and cfg.whisper_device == "cuda":
        return _r("stt", "attiva", "su CPU: più lenta, qualche secondo a frase",
                  passo_gpu(), **det)
    return _r("stt", "attiva", "", "", **det)


def _voice_files(path: str) -> bool:
    return bool(path) and Path(path).is_file() and Path(path + ".json").is_file()


def check_voce(cfg) -> dict:
    from .config import VOICE_MAP
    voci = sorted({n.split("-")[0] for n, p in VOICE_MAP.items() if _voice_files(p)})
    if not presente("piper"):
        return _r("voce", "mancante", "manca piper-tts",
                  "Va installata nell'ambiente di Calliope: pip install piper-tts.")
    if not _voice_files(cfg.piper_voice):
        return _r("voce", "mancante", f"manca la voce {Path(cfg.piper_voice).stem}",
                  "Va scaricata la voce: da terminale python -m calliope.stato --installa "
                  "voce_serena_alta, o un'altra voce del catalogo.",
                  voce=cfg.piper_voice, voci_installate=voci)
    # La stima del costo della voce su questa macchina (07/10, calliope/taratura_voce.py)
    try:
        from . import taratura_voce
        stima = taratura_voce.testo_stato(cfg)
    except Exception:  # noqa: BLE001
        stima = None
    note = [f"{len(voci)} voci installate"] if len(voci) > 1 else []
    if stima:
        note.append(stima[0].lower() + stima[1:].rstrip("."))
    return _r("voce", "attiva", "; ".join(note), "",
              voce=Path(cfg.piper_voice).stem, voci_installate=voci)


def check_wake(cfg) -> dict:
    if not cfg.wake_word_enabled:
        return _r("wake", "da_configurare", "wake word spenta: ascolto tutto",
                  "Per rispondere solo al nome, in calliope.locale.yaml metti wake_word_enabled "
                  "a true e riavviami.")
    if cfg.wake_mode != "modello":
        return _r("wake", "attiva", "nome cercato nel testo (wake word testuale)", "",
                  modo=cfg.wake_mode)
    if getattr(cfg, "audio_modo", "locale") == "satellite":
        # Il rilevatore gira sul satellite, che senza il modello non parte
        return _r("wake", "attiva", "sul satellite", "", modo="satellite")
    if not presente("onnxruntime"):
        return _r("wake", "mancante", "manca onnxruntime: uso il nome nel testo",
                  "Va installata nell'ambiente di Calliope: pip install onnxruntime.")
    parola = (getattr(cfg, "wake_names", None) or [cfg.name])[0]
    if not Path(cfg.wake_model).is_file():
        # Wake word cambiata (04/10, modalità startrek: «Computer») senza il suo modello
        return _r("wake", "mancante", f"manca il modello della wake word «{parola}»: uso la "
                  f"parola nel testo",
                  "Il modello si addestra nella cartella wakeword (WW_PAROLA, vedi "
                  "wakeword/parole.py): finché manca riconosco la parola dalla trascrizione, "
                  "che sbaglia di più.", modello=cfg.wake_model, parola=parola)
    modelli = list(getattr(cfg, "wake_models", None) or [cfg.wake_model])
    nomi = (getattr(cfg, "wake_names", None) or [parola])[:len(modelli)]
    return _r("wake", "attiva", "" if parola.lower() == cfg.name.lower() else
              " e ".join(f"«{n}»" for n in nomi),
              "", modello=cfg.wake_model, parola=parola, modelli=modelli)


def _model_stem(path: str) -> str:
    return Path(path).stem


# speakers.json rovinato e senza una copia buona (03/10): Calliope parte, ma tutti ospiti
PASSO_SPEAKERS_ILLEGGIBILE = (
    "Finché non si ripara non riconosco nessuno e tutti sono ospiti. Va ripreso "
    "speakers.json da una copia (speakers.json.bak, o l'istantanea dell'ultimo "
    "aggiornamento); per ripartire da capo, con il primo avvio, va tolto il file.")


def check_chi_parla(cfg, speakers_path: str = "speakers.json") -> dict:
    if not cfg.speaker_id_enabled:
        return _r("chi_parla", "da_configurare", "riconoscimento spento: tutti sono ospiti",
                  "In calliope.locale.yaml metti speaker_id_enabled a true e riavviami.")
    if not presente("onnxruntime"):
        return _r("chi_parla", "mancante", "manca onnxruntime",
                  "Va installata nell'ambiente di Calliope: pip install onnxruntime.")
    if not Path(cfg.speaker_model).is_file():
        return _r("chi_parla", "mancante", "manca il modello CAM++",
                  "Va scaricato il modello per riconoscere le voci: da terminale python -m "
                  "calliope.stato --installa modello_chi_parla.", modello=cfg.speaker_model)
    persone, admin, da_rifare = [], [], []
    p = Path(speakers_path)
    if p.is_file() or Path(str(p) + ".bak").is_file():
        # Il file, o la sua copia .bak se è rovinato (03/10: è quella che usa SpeakerRegistry)
        from .persistenza import FileRovinato, leggi_json
        try:
            data, _ = leggi_json(p)
        except FileRovinato:
            return _r("chi_parla", "guasta", "speakers.json non si legge",
                      PASSO_SPEAKERS_ILLEGGIBILE)
        stem = _model_stem(cfg.speaker_model)
        for d in data if isinstance(data, list) else []:
            persone.append(d.get("name"))
            if d.get("admin"):
                admin.append(d.get("name"))
            if not d.get("voiceprint") or d.get("model") != stem:
                da_rifare.append(d.get("name"))
    det = {"persone": persone, "amministra": admin, "da_registrare_di_nuovo": da_rifare}
    if not persone:
        return _r("chi_parla", "da_configurare", "nessuna persona registrata",
                  "Chiamami per nome e ci presentiamo: chi si registra per primo amministra.",
                  **det)
    if da_rifare:
        return _r("chi_parla", "attiva", f"voce da registrare di nuovo: {', '.join(da_rifare)}",
                  f"Va ripetuta la registrazione della voce: python arruola.py "
                  f"{da_rifare[0]}.", **det)
    return _r("chi_parla", "attiva",
              f"{len(persone)} persona registrata" if len(persone) == 1
              else f"{len(persone)} persone registrate", "", **det)


# Nomi dei dispositivi di PortAudio che su Linux passano da PipeWire (o PulseAudio): ci
# sono sempre, anche senza nessun microfono vero
_AUDIO_VIRTUALI = ("default", "pipewire", "pulse", "sysdefault")


def pipewire_audio(timeout: float = 2.0) -> dict | None:
    """Linux: microfoni e uscite che PipeWire vede davvero (`pw-dump`, solo lettura).
    None se non si sa (non Linux, niente pw-dump, errore). Alla prima installazione sulla
    DGX (02/10) PortAudio dava «default» con 64 ingressi e il controllo diceva «audio
    attiva», ma la DGX non ha microfono e l'unica uscita era «Dummy Output»: Calliope
    partiva e ascoltava il silenzio."""
    if not sys.platform.startswith("linux"):
        return None
    import shutil
    import subprocess
    exe = shutil.which("pw-dump")
    if not exe:
        return None
    try:
        r = subprocess.run([exe], capture_output=True, timeout=timeout)
        return pipewire_da_dump(json.loads(r.stdout or b"[]"))
    except Exception:  # noqa: BLE001 — PipeWire spento o uscita strana: non si sa
        return None


def pipewire_da_dump(oggetti) -> dict:
    """Microfoni, uscite vere e uscite finte («Dummy Output») dal JSON di `pw-dump`."""
    sorgenti, uscite, finte = [], [], []
    for o in oggetti if isinstance(oggetti, list) else []:
        if not isinstance(o, dict) or o.get("type") != "PipeWire:Interface:Node":
            continue
        props = ((o.get("info") or {}).get("props") or {})
        classe = props.get("media.class")
        nome = props.get("node.description") or props.get("node.name") or "?"
        if classe == "Audio/Source":
            sorgenti.append(nome)
        elif classe == "Audio/Sink":
            (finte if props.get("node.name") == "auto_null" else uscite).append(nome)
    return {"microfoni": sorgenti, "uscite": uscite, "uscite_finte": finte}


def audio_virtuale_senza_dispositivi(nomi: dict) -> tuple[str, str] | None:
    """(motivo, passo) se i dispositivi scelti sono quelli virtuali di PipeWire e dietro non
    c'è un microfono (o c'è solo l'uscita finta); None se va bene o non si sa."""
    if not all(str(v).lower() in _AUDIO_VIRTUALI for v in nomi.values()):
        return None
    pw = pipewire_audio()
    if pw is None:
        return None
    if not pw["microfoni"]:
        return ("nessun microfono: PipeWire non vede nessuna sorgente audio",
                "Collega un microfono (USB o Bluetooth) e riavviami: senza, parto ma non "
                "sento niente. Su un server senza audio la voce arriverà dai satelliti.")
    if not pw["uscite"]:
        return ("nessun altoparlante: c'è solo l'uscita finta di PipeWire",
                "Collega un altoparlante o delle cuffie e riavviami: senza, le risposte non "
                "si sentono.")
    return None


def check_audio(cfg) -> dict:
    if getattr(cfg, "audio_modo", "locale") == "satellite":
        # Microfono e casse sono del satellite (la DGX non ne ha): li controlla lui
        return _r("audio", "attiva", "microfono e casse del satellite", "", modo="satellite")
    sd = importa("sounddevice")
    if sd is None:
        if sys.platform.startswith("linux") and presente("sounddevice"):
            # Su Linux il wheel di sounddevice non contiene PortAudio: l'import fallisce
            # con «PortAudio library not found» (documentazione di sounddevice)
            return _r("audio", "mancante", "manca la libreria di sistema PortAudio",
                      "Va installata la libreria di sistema: sudo apt install libportaudio2.")
        return _r("audio", "mancante", "manca sounddevice (o PortAudio)",
                  "Va installata nell'ambiente di Calliope: pip install sounddevice.")
    det, note = {}, []
    for kind, attr in (("input", "input_device"), ("output", "output_device")):
        label = "microfono" if kind == "input" else "uscita"
        dev = getattr(cfg, attr)
        try:
            if dev is not None:
                try:
                    det[label] = sd.query_devices(dev, kind)["name"]
                    continue
                except Exception:  # noqa: BLE001
                    note.append(f"{label} «{dev}» non trovato, uso quello predefinito")
            det[label] = sd.query_devices(kind=kind)["name"]
        except Exception:  # noqa: BLE001
            return _r("audio", "guasta", f"nessun {label} disponibile",
                      f"Collega un {label} e riavviami; l'elenco lo dà python -m sounddevice.",
                      **det)
    vuoto = audio_virtuale_senza_dispositivi(det)
    if vuoto:
        return _r("audio", "guasta", vuoto[0], vuoto[1], **det)
    return _r("audio", "attiva", "; ".join(note), "", **det)


def check_memoria(cfg) -> dict:
    if not cfg.memory_db:
        return _r("memoria", "da_configurare", "memoria spenta (memory_db vuoto)",
                  "In calliope.locale.yaml dai un file a memory_db e riavviami.")
    folder = Path(cfg.memory_db).resolve().parent
    if not folder.is_dir() or not os.access(folder, os.W_OK):
        return _r("memoria", "guasta", "non posso scrivere nella cartella della memoria",
                  "Controlla che la cartella di memory_db esista e sia scrivibile.",
                  file=cfg.memory_db)
    return _r("memoria", "attiva", "", "", file=cfg.memory_db,
              esiste=Path(cfg.memory_db).is_file())


def _zim_files(cfg) -> list[tuple[str, str | None]]:
    from .installa.catalogo import risolvi_zim
    out = []
    for ruolo, attr in (("mini", "biblioteca_mini"), ("completa", "biblioteca_completa"),
                        ("ragazzi", "biblioteca_ragazzi"), ("dizionario", "biblioteca_dizionario")):
        path = getattr(cfg, attr, None)
        out.append((ruolo, risolvi_zim(path) if path else None))
    return out


_NOMI_ZIM = {"mini": "Wikipedia ridotta", "completa": "Wikipedia completa",
             "ragazzi": "Vikidia", "dizionario": "il Wikizionario"}
# I file in cui si cerca per parole: hanno bisogno dell'indice FTS5
_CON_INDICE = ("mini", "ragazzi")


def check_biblioteca(cfg) -> dict:
    if not cfg.biblioteca_enabled:
        return _r("biblioteca", "da_configurare", "spenta (biblioteca_enabled)",
                  "In calliope.locale.yaml metti biblioteca_enabled a true e riavviami.")
    files = {r: p for r, p in _zim_files(cfg)}
    det = {"file": {r: (p if p and Path(p).is_file() else None) for r, p in files.items()}}
    # Dal 01/10 niente librerie: i file ZIM si leggono in puro Python (calliope/zim.py) e la
    # ricerca per parole usa un indice SQLite FTS5 accanto (calliope/biblioteca_indice.py),
    # solo per Wikipedia ridotta e Vikidia. Senza indice la biblioteca funziona lo stesso,
    # ma ridotta: trova le voci solo dal titolo esatto
    from .biblioteca_indice import stato_indice
    indici, senza = {}, []
    for ruolo in _CON_INDICE:
        p = det["file"].get(ruolo)
        if p:
            code, why = stato_indice(p)
            indici[ruolo] = code
            if code != "ok":
                senza.append((ruolo, code))
    # Fonti in più usate nella ricerca (Wikiquote): anche loro con l'indice
    from .installa.catalogo import fonti_usate
    used = []
    for fonte, p in fonti_usate(cfg):
        name = fonte.titolo.split(",")[0]
        code, _ = stato_indice(p)
        indici[name] = code
        if code == "ok":
            used.append(name)
        else:
            senza.append((name, code))
    if used:
        det["fonti_extra"] = used
    if indici:
        det["indici"] = indici
    # Fonti in più scaricate (Wikiquote, Gutenberg…): la ricerca non le legge ancora
    from .installa.catalogo import fonti_scaricate
    extra = [f.titolo.split(",")[0] for f, _ in fonti_scaricate(cfg)]
    if extra:
        det["scaricate_non_usate"] = extra
    note = (f"; cerca anche in {', '.join(used)}" if used else "")
    note += (f"; scaricate, non ancora usate nella ricerca: {', '.join(extra)}" if extra else "")
    present = [r for r, p in det["file"].items() if p]
    if not ({"mini", "completa"} & set(present)):
        return _r("biblioteca", "mancante", "mancano i file di Wikipedia" + note,
                  "Posso scaricarla io: dimmi «scarica la biblioteca», sono circa 12 "
                  "gigabyte.", **det)
    if senza:
        # Prima l'indice dei file che ci sono, poi i file che mancano: senza l'indice del
        # mini la ricerca perde le voci trovate per parole
        nomi = [_NOMI_ZIM.get(r, r) for r, _ in senza]
        come = {"mancante": "manca l'indice di ricerca", "incompleto": "l'indice è a metà",
                "versione": "l'indice è di una versione vecchia",
                "diverso": "l'indice è di un altro file"}.get(senza[0][1],
                                                               "l'indice non si legge")
        ridotta = "ricerca ridotta, " if any(r in _CON_INDICE for r, _ in senza) else ""
        return _r("biblioteca", "attiva",
                  f"{ridotta}{come} per " + " e ".join(nomi) + note,
                  "Posso prepararlo io, senza internet, in pochi minuti: dimmi «prepara "
                  "l'indice della biblioteca». Da terminale: python -m calliope.stato "
                  "--installa biblioteca_indice.", **det)
    missing = [r for r in ("mini", "completa", "ragazzi", "dizionario") if r not in present]
    if missing:
        nomi = [_NOMI_ZIM[r] for r in missing]
        elenco = nomi[0] if len(nomi) == 1 else ", ".join(nomi[:-1]) + " e " + nomi[-1]
        return _r("biblioteca", "attiva", "manca " + elenco + note,
                  "Posso scaricare quello che manca: dimmi «scarica " + nomi[0] + "».", **det)
    return _r("biblioteca", "attiva", note[2:], "", **det)


_PC_LIBS = (("pycaw", "volume"), ("comtypes", "volume"), ("win32com", "ricerca dei file"),
            ("psutil", "programmi aperti"), ("screen_brightness_control", "luminosità"),
            ("winrt", "musica"))


def check_pc(cfg, satelliti=None) -> dict:
    # Con audio_modo: satellite (Calliope sulla DGX, 03/10) il PC è quello del satellite:
    # esecutore remoto (calliope/pc/remoto.py). `satelliti` è il server vivo (dentro
    # Calliope); senza (da terminale) si guarda solo la configurazione
    if getattr(cfg, "audio_modo", "locale") == "satellite":
        nome = getattr(cfg, "pc_nome", "portatile")
        if not getattr(cfg, "pc_enabled", False):
            return _r("pc", "da_configurare", "spento (pc_enabled)",
                      f"Il computer da comandare è il {nome} collegato come satellite: in "
                      f"calliope.locale.yaml del server metti pc_enabled: true e riavviami.")
        if satelliti is None:
            return _r("pc", "attiva", f"il {nome} tramite il satellite, quando è collegato",
                      "", nome=nome, remoto=True)
        from .pc.remoto import per_pc
        c = per_pc(satelliti)
        if c is None:
            return _r("pc", "da_configurare", f"il {nome} non è collegato",
                      f"Avvia il satellite sul {nome} (setup\\satellite\\avvia_satellite.cmd).",
                      nome=nome, remoto=True)
        ese = getattr(c, "esecutore", None)
        if ese is None:
            return _r("pc", "da_configurare",
                      "il satellite collegato non offre il controllo del computer",
                      "Aggiorna il codice del satellite e riavvialo (su Windows, con "
                      "satellite_esecutore: true); su Linux il controllo del computer non c'è.",
                      nome=nome, remoto=True)
        caps = ese.get("capacita") or []
        if not caps:
            return _r("pc", "mancante", f"sul {nome} mancano le librerie del controllo",
                      "Sul satellite: pip install pycaw comtypes pywin32 psutil "
                      "screen_brightness_control winrt-Windows.Media.Control, poi riavvialo.",
                      nome=nome, remoto=True)
        return _r("pc", "attiva", f"il {nome} tramite il satellite: " + ", ".join(caps)
                  + ("; documenti consegnati lì" if ese.get("file") else ""), "",
                  nome=nome, remoto=True, capacita=list(caps), app=list(ese.get("app") or []))
    # Prima la piattaforma, poi l'interruttore: sulla DGX (prima installazione, 02/10)
    # pc_enabled è spento dall'esempio e il passo diceva «metti pc_enabled a true»,
    # che lì non serve a niente
    if sys.platform != "win32":
        # Su Linux un esecutore locale non c'è: il PC si comanda da un satellite Windows
        return _r("pc", "mancante", f"non è Windows ({platform.system()})",
                  "Il controllo del computer c'è solo su Windows: con Calliope su Linux si "
                  "comanda il PC di un satellite Windows (audio_modo: satellite).")
    if not getattr(cfg, "pc_enabled", False):
        return _r("pc", "da_configurare", "spento (pc_enabled)",
                  "In calliope.locale.yaml metti pc_enabled a true e riavviami.")
    missing = [(m, what) for m, what in _PC_LIBS if not presente(m)]
    pip = ("pip install pycaw comtypes pywin32 psutil screen_brightness_control "
           "winrt-Windows.Media.Control")
    if len(missing) == len(_PC_LIBS):
        return _r("pc", "mancante", "mancano le librerie del controllo del computer",
                  f"Vanno installate nell'ambiente di Calliope: {pip}.")
    if missing:
        return _r("pc", "attiva", "manca: " + ", ".join(sorted({w for _, w in missing})),
                  f"Per il resto: {pip}.", mancanti=[m for m, _ in missing])
    return _r("pc", "attiva", "", "", nome=cfg.pc_nome)


def check_documenti(cfg) -> dict:
    if not getattr(cfg, "documenti_enabled", False):
        return _r("documenti", "da_configurare", "spenti (documenti_enabled)",
                  "In calliope.locale.yaml metti documenti_enabled a true e riavviami.")
    pkgs = (("word", "docx", "python-docx"), ("excel", "openpyxl", "openpyxl"),
            ("pdf", "fpdf", "fpdf2"))
    ok = [f for f, mod, _ in pkgs if presente(mod)]
    missing = [p for f, mod, p in pkgs if f not in ok]
    if not ok:
        return _r("documenti", "mancante", "mancano python-docx, openpyxl e fpdf2",
                  "Vanno installate nell'ambiente di Calliope: "
                  + comando_libreria("python-docx openpyxl fpdf2", "documenti") + ".")
    if missing:
        return _r("documenti", "attiva", "solo " + ", ".join(ok),
                  "Per gli altri formati: " + comando_libreria(" ".join(missing), "documenti")
                  + ".", formati=ok)
    return _r("documenti", "attiva", "", "", formati=ok)


def check_ufficio(cfg, servizio=None) -> dict:
    """L'ufficio (calliope/ufficio/): modelli, rubrica, fatture. Attiva anche senza i dati
    dell'emittente o lo schema XSD: le note dicono cosa manca per le fatture."""
    if not getattr(cfg, "ufficio_enabled", False):
        return _r("ufficio", "da_configurare", "spento (ufficio_enabled)",
                  "In calliope.locale.yaml metti ufficio_enabled a true e riavviami.")
    if not getattr(cfg, "documenti_enabled", False) or not presente("fpdf"):
        return _r("ufficio", "mancante", "servono i documenti in PDF (fpdf2)",
                  "Installa le librerie dei documenti: "
                  + comando_libreria("python-docx openpyxl fpdf2", "documenti") + ".")
    from .ufficio import cartella_modelli
    from .ufficio.fatturapa import cartella_xsd, xsd_presente
    from .ufficio.modelli import carica, pronti
    if servizio is not None:
        catalogo, errori = servizio.catalogo, servizio.errori_modelli
        emittente_ok = not servizio.emittente()[1]
    else:
        catalogo, errori = carica(cartella_modelli(cfg))
        from .ufficio.rubrica import controlla, mancanti_per_fattura
        em, err = controlla(dict(getattr(cfg, "fatture_emittente", None) or {}))
        emittente_ok = bool(em.get("partita_iva")) and not err and not [
            k for k in mancanti_per_fattura(em) if k != "partita_iva"]
    propri = [n for n in catalogo if n not in pronti()]
    note, passi = [], []
    if propri:
        note.append(f"{len(propri)} modelli tuoi")
    if errori:
        note.append(f"{len(errori)} modelli rovinati")
    manca = [p for m, p in (("docxtpl", "docxtpl"), ("pptx", "python-pptx")) if not presente(m)]
    if manca:
        note.append("mancano " + " e ".join(manca))
        passi.append("Per i modelli Word e PowerPoint: "
                     + comando_libreria(" ".join(manca), "modelli") + ".")
    if not emittente_ok:
        note.append("per le fatture mancano i dati di chi emette")
        passi.append("Scrivi i tuoi dati in calliope.locale.yaml, sezione ufficio, alla voce "
                     "fatture_emittente.")
    if not xsd_presente(cartella_xsd(cfg)):
        note.append("schema XSD di FatturaPA non scaricato")
        passi.append("Per verificare le fatture con lo schema ufficiale: python -m "
                     "calliope.ufficio --scarica-xsd.")
    return _r("ufficio", "attiva", "; ".join(note), " ".join(passi),
              modelli=sorted(catalogo), errori=errori)


# Da terminale (python -m calliope.stato) non c'è un Calliope già collegato: con indirizzo
# e token presenti la casa risultava «serve un riavvio» anche quando funzionava (01/10).
# Lì si prova un collegamento vero, solo letture; dentro Calliope si usa quello aperto.
PROVA_COLLEGAMENTI = False


def check_casa(cfg, backend=None) -> dict:
    from .casa import diagnose
    d = diagnose(cfg, backend)
    if backend is None and PROVA_COLLEGAMENTI and d.get("codice") == "riavvio":
        from .casa import load_casa
        be = None
        try:
            be, _ = load_casa(cfg, log=lambda m: None)
            if be is not None:
                d = diagnose(cfg, be, riprova=True)
        except Exception:  # noqa: BLE001 — resta la diagnosi senza collegamento
            pass
        finally:
            if be is not None:
                be.close()
    return _r("casa", d["stato"], d["motivo"] if d["stato"] != "attiva" else "",
              d["prossimo_passo"], codice=d["codice"], **d.get("dettagli", {}))


def _schermi_abbinati_ro(db_path) -> list[tuple]:
    """(nome, stanza, proprietario_nome) degli schermi abbinati, letti in sola lettura (da
    terminale: il controllo non crea tabelle né file)."""
    import sqlite3
    if not db_path or not Path(db_path).is_file():
        return []
    try:
        uri = Path(db_path).resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=1) as db:
            return db.execute("SELECT nome, stanza, proprietario_nome FROM schermi "
                              "ORDER BY id").fetchall()
    except sqlite3.Error:
        return []


def _server_schermi_acceso(cfg) -> bool:
    """Da terminale: risponde qualcuno sulla porta degli schermi? (Calliope accesa)"""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", int(cfg.schermi_porta)), timeout=0.3):
            return True
    except OSError:
        return False


def check_schermi(cfg, hub=None) -> dict:
    """Gli schermi (calliope/schermi/): server delle schede e schermi abbinati. Con `hub` (dentro
    Calliope) lo stato vivo; senza (da terminale) i file e, con PROVA_COLLEGAMENTI, la porta."""
    if not getattr(cfg, "schermi_enabled", False):
        return _r("schermi", "da_configurare", "spenti (schermi_enabled)",
                  "In calliope.locale.yaml metti schermi_enabled a true e riavviami.")
    missing = [m for m in ("starlette", "uvicorn") if not presente(m)]
    if missing:
        return _r("schermi", "mancante", "manca " + " e ".join(missing),
                  "Vanno installate nell'ambiente di Calliope: "
                  + comando_libreria("starlette uvicorn", "schermi")
                  + " (senza [standard]: httptools non c'è per Windows ARM).")
    from .schermi import solo_locale, tls as _tls, url_schermi
    if hub is None:
        # Da terminale: in rete senza certificato il server non partirebbe (02/10)
        try:
            modo = _tls.modo(cfg)[0]
        except ValueError as e:
            return _r("schermi", "guasta", str(e), "Rifai il certificato: python -m "
                      "calliope.satellite --certificato --forza, e riavviami.")
        if modo == "rifiuta":
            return _r("schermi", "da_configurare", "in rete senza certificato: la pagina non "
                      "parte in chiaro", _tls.PASSO_CERTIFICATO)
    url = hub.url if hub is not None and hub.url else url_schermi(cfg)
    dove = ("sul browser di questo computer" if solo_locale(cfg)
            else "sul computer, sul tablet o sulla TV")
    passo = (f"Apri {url} {dove} e dimmi il codice che compare: «abbina lo schermo "
             f"123456 al soggiorno».")
    if solo_locale(cfg):
        passo += (" Per tablet e TV, in calliope.locale.yaml metti schermi_indirizzo a "
                  "0.0.0.0 (in HTTPS: serve il certificato, python -m calliope.satellite "
                  "--certificato) e riavviami.")
    det = {"indirizzo": url}
    if hub is not None:
        if not hub.server_attivo:
            return _r("schermi", "guasta", "il server delle schede si è fermato",
                      "Riavviami; se succede ancora, guarda il terminale.", **det)
        st = hub.stato()
        det["schermi"] = st["schermi"]
        if not st["abbinati"]:
            return _r("schermi", "da_configurare", "nessuno schermo abbinato", passo, **det)
        n, k = st["abbinati"], st["collegati"]
        # Abbinamenti che non si collegano da giorni (05/10): una nota, non un guasto
        giorni = float(getattr(cfg, "schermi_inattivi_giorni", 7.0) or 0)
        try:
            vecchi = hub.archivio.inattivi(giorni)
        except Exception:  # noqa: BLE001 — la nota non deve fermare il controllo
            vecchi = []
        if vecchi:
            det["inattivi"] = [s["nome"] for s in vecchi]
        return _r("schermi", "attiva",
                  (f"{n} schermo abbinato" if n == 1 else f"{n} schermi abbinati")
                  + f", {k} collegat{'o' if k == 1 else 'i'} ora; pagina su {url}"
                  + (f"; {len(vecchi)} senza collegamento da più di {giorni:g} giorni "
                     f"(calliope schermi)" if vecchi else ""), "", **det)
    rows = _schermi_abbinati_ro(cfg.memory_db)
    det["schermi"] = [{"nome": r[0], "stanza": r[1], "personale_di": r[2]} for r in rows]
    acceso = _server_schermi_acceso(cfg) if PROVA_COLLEGAMENTI else None
    if acceso is not None:
        det["server_acceso"] = acceso
    if not rows:
        return _r("schermi", "da_configurare", "nessuno schermo abbinato",
                  passo + ("" if acceso else " Il server si accende con Calliope."), **det)
    nota = "" if acceso is None else ("; server acceso" if acceso else
                                      "; server spento (si accende con Calliope)")
    n = len(rows)
    return _r("schermi", "attiva",
              (f"{n} schermo abbinato" if n == 1 else f"{n} schermi abbinati") + nota, "",
              **det)


def check_agenti(cfg, servizio=None) -> dict:
    """Gli agenti dei lavori lunghi (calliope/agenti/). Con `servizio` (dentro Calliope) lo
    stato del collegamento visto dall'ultimo tentativo (tunnel, Ollama, modello), senza rete;
    da terminale solo la configurazione: il collegamento si prova con python -m
    calliope.agenti --prova, che apre il tunnel (qui non si apre mai)."""
    if not getattr(cfg, "agenti_enabled", False):
        return _r("agenti", "da_configurare", "spenti (agenti_enabled)",
                  "In calliope.locale.yaml metti agenti_enabled a true e riavviami.")
    if not presente("httpx"):
        return _r("agenti", "mancante", "manca la libreria httpx",
                  "Va installata nell'ambiente di Calliope: pip install httpx.")
    from .agenti.impostazioni import (ConfigAgentiNonValida, carica, percorso_file,
                                      ssh_eseguibile)
    try:
        imp = carica(cfg)
    except ConfigAgentiNonValida as e:
        return _r("agenti", "guasta", str(e),
                  "Correggi il file della DGX (vedi i commenti di dgx.yaml), poi riavviami.")
    if imp is None:
        path = percorso_file(cfg)
        return _r("agenti", "da_configurare", "nessun agente configurato",
                  "Per la DGX metti dgx.yaml accanto a calliope.yaml, con l'alias di "
                  + (".ssh\\config" if sys.platform == "win32" else "~/.ssh/config")
                  + " e il modello; per un Ollama o un vLLM in rete (o sulla stessa DGX), "
                  "agenti_url in calliope.locale.yaml.", file=str(path) if path else None)
    det = {"collegamento": imp.modo, "modello": imp.modello, "origine": imp.origine,
           "motore": imp.motore}
    if imp.tunnel:
        det.update(alias=imp.ssh_alias, porta_locale=imp.porta_locale)
    if imp.scrittore:
        det["scrittore"] = imp.scrittore
    if imp.tunnel and not ssh_eseguibile():
        return _r("agenti", "mancante", "manca il client SSH",
                  "Installa il Client OpenSSH: Impostazioni, App, Funzionalità facoltative."
                  if sys.platform == "win32" else
                  "Installa il client OpenSSH: sudo apt install openssh-client.", **det)
    # La sandbox del codice (03/10): container Docker o processo. Dentro Calliope la scelta
    # fatta dal thread dei lavori; da terminale si chiede a Docker (sola lettura, ~50 ms)
    iso = getattr(servizio, "isolamento", None) if servizio is not None else None
    if servizio is None:
        try:
            from .agenti.sandbox import scegli_isolamento
            iso = scegli_isolamento(getattr(cfg, "agenti_sandbox_motore", "auto"),
                                    getattr(cfg, "agenti_sandbox_immagine", None))
        except Exception:  # noqa: BLE001
            iso = None
    nota_sb, passo_sb = "", ""
    if iso is not None:
        det["sandbox"] = iso.descrizione
        det["sandbox_motore"] = iso.motore if iso.pronto else "nessuno"
        if iso.immagine:
            det["sandbox_immagine"] = iso.immagine
        nota_sb = ("; il codice gira in un " + iso.descrizione if iso.pronto
                   else "; il codice non si esegue: " + iso.descrizione)
        passo_sb = iso.passo
        # I linguaggi dei programmi (04/10, agenti/linguaggi.py)
        try:
            from .agenti.linguaggi import elenco_detto, pronti, scegli
            isos = (getattr(servizio, "isolamenti", None) if servizio is not None
                    else scegli(cfg, iso)) or {}
            if iso.pronto and isos:
                det["linguaggi"] = pronti(isos)
                nota_sb += "; programmi in " + elenco_detto(det["linguaggi"])
                manca = [i.passo for i in isos.values() if not i.pronto and i.passo]
                if manca and not passo_sb:
                    passo_sb = manca[0]
        except Exception:  # noqa: BLE001
            pass
    # Internet di estensioni e pagine d'esempio nell'ultima settimana (05/10, registro delle
    # uscite di web/rete.py): sola lettura di un file, anche da terminale
    rete = uscite_settimana(cfg)
    if rete:
        det["internet_7_giorni"] = rete
        nota_sb += "; " + rete["frase"]
    if servizio is None:
        return _r("agenti", "attiva", f"{imp.modello} ({imp.modo}): collegamento non provato"
                  + nota_sb, "Per provarlo: python -m calliope.agenti --prova."
                  + (" " + passo_sb if passo_sb else ""), **det)
    d = servizio.diagnosi
    det["codice"] = d.get("codice")
    if d.get("codice") == "ok":
        return _r("agenti", "attiva", servizio.descrizione() + nota_sb, passo_sb, **det,
                  **({"caricato": d["caricato"]} if "caricato" in d else {}))
    if d.get("codice") == "non_provato":
        return _r("agenti", "attiva", servizio.descrizione() + "; collegamento in corso"
                  + nota_sb, passo_sb, **det)
    return _r("agenti", d.get("stato") or "guasta", d.get("motivo") or "",
              d.get("passo") or "", **det)


def uscite_settimana(cfg) -> dict | None:
    """Il riepilogo del registro delle uscite (estensioni e pagine d'esempio dell'agente)
    degli ultimi 7 giorni, o None se non c'è stata nessuna richiesta."""
    try:
        from .estensioni import cartella
        from .web.rete import riepilogo
        r = riepilogo(cartella(cfg) / "uscite.jsonl", ore=24 * 7)
    except Exception:  # noqa: BLE001
        return None
    if not r.get("richieste"):
        return None
    kb = r["byte_ricevuti"] / 1024
    r["frase"] = (f"internet di estensioni e agente nell'ultima settimana: {r['richieste']} "
                  f"richieste verso {r['host']} siti, {r['fatte']} fatte ({kb:.0f} kB "
                  f"ricevuti, {r['byte_inviati']} byte inviati) e {r['bloccate']} bloccate")
    return r


def check_archivio(cfg, servizio=None) -> dict:
    """L'archivio dei documenti di casa (calliope/archivio/). Con `servizio` (dentro Calliope)
    quanti documenti ha letto, cosa sta facendo e l'ultimo errore del modello, senza rete; da
    terminale solo la configurazione e le librerie."""
    if not getattr(cfg, "archivio_enabled", False):
        return _r("archivio", "da_configurare", "spento (archivio_enabled)",
                  "In calliope.locale.yaml metti archivio_enabled a true e riavviami.")
    cartella = getattr(cfg, "archivio_cartella", None)
    if not cartella:
        return _r("archivio", "da_configurare", "nessuna cartella dei documenti",
                  "In calliope.locale.yaml, sezione archivio, metti archivio_cartella: la "
                  "cartella dei documenti di casa (sottocartelle con il nome di una persona "
                  "per i suoi documenti personali), poi riavviami.")
    from pathlib import Path
    if not Path(cartella).expanduser().is_dir():
        return _r("archivio", "guasta", "la cartella dei documenti non c'è",
                  "Controlla archivio_cartella in calliope.locale.yaml.", cartella=cartella)
    note = []
    if not presente("pypdfium2"):
        note.append("senza pypdfium2 i PDF non si leggono")
    if not presente("PIL"):
        note.append("senza Pillow foto e scansioni non si leggono")
    passo_lib = ("Per leggere tutto: " + comando_libreria("pypdfium2 pillow python-docx",
                                                          "archivio") + ".") if note else ""
    if servizio is None:
        return _r("archivio", "attiva", "; ".join(note), passo_lib, cartella=cartella)
    st = servizio.stato()
    det = {"cartella": cartella, "documenti": st["documenti"], "file": st["file"]}
    if servizio.estrattore is None:
        return _r("archivio", "attiva",
                  "; ".join([f"{st['documenti']} documenti, ma non leggo quelli nuovi: manca "
                             "il modello grande"] + note),
                  "Configura gli agenti (dgx.yaml o agenti_url) o archivio_url in "
                  "calliope.locale.yaml, poi riavviami.", **det)
    d = st.get("diagnosi") or {}
    if d.get("codice") not in (None, "ok", "non_provato"):
        note.append(f"il modello non risponde ({d['codice']}): riprovo al prossimo giro")
    attesa = (st["file"] or {}).get("in_attesa", 0)
    motivo = f"{st['documenti']} documenti" + (f", {attesa} in attesa" if attesa else "")
    return _r("archivio", "attiva", "; ".join([motivo] + note), passo_lib, **det)


def check_satellite(cfg, server=None) -> dict:
    """I satelliti (calliope/satellite/). Con `server` (dentro Calliope) lo stato vivo: chi è
    collegato; senza (da terminale) configurazione, certificato e satelliti abbinati."""
    locale = getattr(cfg, "audio_modo", "locale") != "satellite"
    if locale:
        return _r("satellite", "da_configurare", "audio di questo computer (audio_modo: locale)",
                  "Per usare un satellite in rete (Calliope sulla DGX, il portatile come "
                  "microfono e casse): in calliope.locale.yaml del server metti audio_modo: "
                  "satellite, poi sul portatile python -m calliope.satellite.")
    if not presente("websockets"):
        return _r("satellite", "mancante", "manca la libreria websockets",
                  "Va installata nell'ambiente di Calliope: "
                  + comando_libreria("websockets", "casa") + ".")
    from .satellite.server import contesto_tls, solo_locale
    host = str(cfg.satellite_indirizzo or "127.0.0.1")
    det = {"indirizzo": host, "porta": cfg.satellite_porta}
    try:
        ctx, impronta = contesto_tls(cfg)
    except ValueError as e:
        return _r("satellite", "guasta", str(e), "Rifallo: python -m calliope.satellite "
                  "--certificato --forza, poi abbina di nuovo i satelliti.", **det)
    if ctx is None and not solo_locale(host) and not cfg.satellite_senza_tls:
        return _r("satellite", "guasta", "in rete senza certificato",
                  "Sul server: python -m calliope.satellite --certificato, poi riavviami.",
                  **det)
    det["tls"] = ctx is not None
    if impronta:
        det["impronta"] = impronta
    schema = "wss" if det.get("tls") else "ws"
    passo = (f"Sul portatile: python -m calliope.satellite (con satellite_server: "
             f"{schema}://<indirizzo del server>:{cfg.satellite_porta}); mostra un codice, "
             f"che si scrive qui: python -m calliope.satellite --abbina <codice> --stanza "
             f"<stanza>.")
    if server is not None:
        st = server.stato()
        det.update(abbinati=st["abbinati"], collegato=st["collegato"])
        if not st["abbinati"]:
            return _r("satellite", "da_configurare", "nessun satellite abbinato", passo, **det)
        c = st["collegato"]
        if c is None:
            return _r("satellite", "attiva", f"{len(st['abbinati'])} abbinat"
                      f"{'o' if len(st['abbinati']) == 1 else 'i'}, nessuno collegato ora: "
                      f"non sento niente finché non se ne collega uno", "", **det)
        return _r("satellite", "attiva", f"collegato «{c['nome']}» (stanza {c['stanza']})",
                  "", **det)
    rows = _satelliti_abbinati_ro(cfg.memory_db)
    det["abbinati"] = [{"nome": r[0], "stanza": r[1]} for r in rows]
    if not rows:
        return _r("satellite", "da_configurare", "nessun satellite abbinato", passo, **det)
    return _r("satellite", "attiva", f"{len(rows)} abbinat{'o' if len(rows) == 1 else 'i'}",
              "", **det)


def _satelliti_abbinati_ro(db_path) -> list[tuple]:
    import sqlite3
    if not db_path or not Path(db_path).is_file():
        return []
    try:
        uri = Path(db_path).resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=1) as db:
            return db.execute("SELECT nome, stanza FROM satelliti ORDER BY id").fetchall()
    except sqlite3.Error:
        return []


def check_web(cfg, servizio=None) -> dict:
    """La ricerca su internet (calliope/web/): SearXNG sulla DGX. Con `servizio` (dentro
    Calliope) l'ultimo esito visto (/healthz all'avvio, poi le ricerche), senza rete; da
    terminale la configurazione e, con PROVA_COLLEGAMENTI, /healthz (nessuna ricerca: niente
    esce di casa)."""
    passo_avvio = ("Sulla DGX: calliope motore searxng avvia, poi in calliope.locale.yaml, "
                   "sezione web, metti web_searxng_url: http://127.0.0.1:8004 e riavviami.")
    if not getattr(cfg, "web_enabled", True):
        return _r("web", "da_configurare", "spenta (web_enabled)",
                  "In calliope.locale.yaml metti web_enabled a true e riavviami.")
    if not getattr(cfg, "online", True):
        return _r("web", "da_configurare", "senza rete (online: false)",
                  "Se c'è internet, in calliope.locale.yaml metti online a true e riavviami.")
    url = getattr(cfg, "web_searxng_url", None)
    if not url:
        return _r("web", "da_configurare", "non disponibile: SearXNG non configurato",
                  passo_avvio)
    if not presente("httpx"):
        return _r("web", "mancante", "manca la libreria httpx",
                  "Va installata nell'ambiente di Calliope: pip install httpx.")
    det = {"searxng": url, "livello": getattr(cfg, "web_livello", "familiare"),
           "max_minuto": getattr(cfg, "web_max_minuto", 10)}
    passo_giu = ("Sulla DGX: calliope motore searxng stato, e se non risponde calliope motore "
                 "searxng avvia (poi torna da sola, senza riavviarmi).")
    if servizio is None:
        if PROVA_COLLEGAMENTI:
            from .web import Web
            w = Web(cfg)
            try:
                ok = w.prova(timeout_s=1.5)
            finally:
                w.close()
            if not ok:
                return _r("web", "guasta", "non disponibile: SearXNG non risponde", passo_giu,
                          **det)
            return _r("web", "attiva", "SearXNG risponde", "", **det)
        return _r("web", "attiva", "SearXNG configurato, non provato", "", **det)
    d = servizio.diagnosi
    det["codice"] = d.get("codice")
    if d.get("codice") == "searxng_giu":
        return _r("web", "guasta", "non disponibile: SearXNG non risponde", passo_giu, **det)
    if d.get("codice") == "internet":
        return _r("web", "guasta", "non disponibile: i motori di ricerca non rispondono "
                  "(internet assente?)", "Controlla la connessione a internet della DGX; "
                  "torna da sola alla prossima ricerca.", **det)
    if d.get("codice") == "errore":
        return _r("web", "attiva", "l'ultima ricerca non è riuscita", passo_giu, **det)
    return _r("web", "attiva", "SearXNG risponde", "", **det)


def check_conversazioni(cfg, arch=None, timeout: float = 1.5) -> dict:
    """L'archivio delle conversazioni (05/10, calliope/conversazioni.py): attivo con la ricerca
    per parole e per significato, o solo per parole se il modello di embedding manca. Da
    terminale (arch None) guarda il file e chiede a Ollama l'elenco dei modelli, in sola
    lettura."""
    if not getattr(cfg, "conversazioni_enabled", True):
        return _r("conversazioni", "da_configurare", "spento (conversazioni_enabled)",
                  "Accendilo con conversazioni_enabled: true in calliope.locale.yaml.")
    giorni = getattr(cfg, "conversazioni_giorni", 30)
    modello = (getattr(cfg, "conversazioni_embedding", None) or "").strip()
    if not modello:
        return _r("conversazioni", "attiva", f"solo ricerca per parole, {giorni} giorni", "",
                  modello=None)
    passo_pull = f"Scarica il modello di embedding: ollama pull {modello}"
    if arch is not None:
        sv = arch.stato_vettori
        if sv is True or sv is None:
            return _r("conversazioni", "attiva",
                      f"ricerca per parole e per significato ({modello}), {giorni} giorni", "",
                      modello=modello)
        return _r("conversazioni", "attiva", f"solo ricerca per parole: {modello} {sv}",
                  passo_pull if sv == "modello non scaricato" else
                  "Controlla che il server degli embedding risponda "
                  "(conversazioni_embedding_url).", modello=modello)
    from .conversazioni import url_embedding
    url = url_embedding(cfg)
    if url.endswith("/v1"):
        return _r("conversazioni", "attiva", f"ricerca ibrida con {modello} su {url}", "",
                  modello=modello)
    try:
        import httpx
        nomi = [m.get("name", "") for m in httpx.get(url + "/api/tags", timeout=timeout)
                .json().get("models", [])]
    except Exception as e:  # noqa: BLE001
        return _r("conversazioni", "attiva",
                  f"Ollama non risponde ({type(e).__name__}): per ora solo ricerca per parole",
                  "Avvia Ollama.", modello=modello)
    if not any(n == modello or n == f"{modello}:latest" or n.split(":")[0] == modello
               for n in nomi):
        return _r("conversazioni", "attiva", f"solo ricerca per parole: manca {modello}",
                  passo_pull, modello=modello)
    return _r("conversazioni", "attiva",
              f"ricerca per parole e per significato ({modello}), {giorni} giorni", "",
              modello=modello)


CONTROLLI = {"llm": check_llm, "stt": check_stt, "voce": check_voce, "wake": check_wake,
             "chi_parla": check_chi_parla, "audio": check_audio,
             "satellite": check_satellite, "memoria": check_memoria,
             "biblioteca": check_biblioteca, "pc": check_pc, "documenti": check_documenti,
             "casa": check_casa, "schermi": check_schermi, "agenti": check_agenti,
             "archivio": check_archivio, "ufficio": check_ufficio,
             "conversazioni": check_conversazioni, "web": check_web}


def controlla_una(cfg, nome: str) -> dict:
    """Un controllo, che non solleva mai eccezioni: un errore inatteso è «guasta»."""
    try:
        return CONTROLLI[nome](cfg)
    except Exception as e:  # noqa: BLE001
        return _r(nome, "guasta", f"controllo non riuscito ({type(e).__name__})",
                  "Guarda il terminale di Calliope: python -m calliope.stato.", errore=str(e))


def controlla(cfg, nomi=None, registro: Registro | None = None) -> Registro:
    """Tutti i controlli (o quelli in `nomi`) in un registro nuovo o in quello dato."""
    reg = registro if registro is not None else Registro()
    for nome in nomi or CONTROLLI:
        reg.da_dict(controlla_una(cfg, nome))
    return reg
