"""
Il servizio dei lavori in secondo piano (02/10/2026): collegamento, coda, proposta e
conferma, esecuzione, annullo, risultati, annuncio.

Ricalca quello che già funziona per i documenti e le installazioni:
- **la voce non aspetta mai**: i tool (`delega`, `stato`, `annulla`) leggono e scrivono solo
  lo stato in memoria; il collegamento (tunnel, Ollama remoto) lo fa il thread dei lavori o
  un thread di verifica. Nessun lock condiviso con la voce resta preso durante una rete;
- **un lavoro alla volta** (la GPU dell'agente è una), gli altri in coda;
- **proposta e conferma** per i lavori costosi (`agenti_conferma`): la proposta finisce con
  «Procedo?» e diventa un'azione in sospeso; la conferma vale solo nella risposta dopo,
  della stessa persona (come le installazioni);
- **a lavoro finito**: i file nella cartella dei risultati (`agenti_risultati`, predefinita
  Documenti\\Calliope\\Lavori), la scheda sugli schermi personali di chi l'ha chiesto, e un
  annuncio breve (`done` + `on_done`, che in main.py sveglia l'ascolto come un timer). Il
  codice non si legge mai ad alta voce;
- **domande a metà lavoro** (03/10): se all'agente manca un dato (consegna con esito
  mancano_dati, o un modello di documento con campi obbligatori vuoti) il lavoro resta
  `in_attesa` con il suo contesto (la conversazione dell'agente, la sandbox, i campi già
  compilati), la domanda si annuncia come i lavori finiti e diventa un'azione in sospeso
  (`RISPOSTA_MSG`); la risposta arriva con `rispondi` (tool lavoro_rispondi) e il lavoro torna
  in coda da dove era. Il tempo d'attesa non conta nel tetto dei minuti; al più
  `agenti_domande_max` domande per lavoro; dopo `agenti_attesa_risposta_min` senza risposta
  il lavoro si chiude da solo e lo si dice;
- **i file della persona** (03/10, file_utente.py): la copia si prende in secondo piano al
  «sì» (`_prendi_file`), entra nella sandbox o nella richiesta, e il risultato torna come
  file nuovo con `consegna` (RemoteDelivery verso il satellite), mai sopra l'originale;
- **i testi in Markdown** (07/10, documenti/markdown.py): ricerche, relazioni e riassunti si
  consegnano come `risultato.md`; la scheda è quella del documento con il lettore Markdown e
  «Scarica» (MD, PDF, Word); il riassunto detto resta breve e senza Markdown;
- **il risultato al portatile** (07/10, `_consegna_risultato`): con il satellite che riceve i
  file (ruolo «pc»), anche il risultato di un lavoro (il testo o il documento) va nella
  cartella Calliope dei Documenti del portatile, con «Lo apro?»; senza, resta nella cartella
  del lavoro sul server, e l'annuncio lo dice.
"""

import datetime
import json
import os
import queue
import re
import sys
import threading
import time
from pathlib import Path

from .arbitro import Arbitro, _interrompi
from .avanzamento import Avanzamento
from .esecuzione import Esecuzioni
from .ciclo import Agente, Annullato, Lavoro, Limite, errore_ollama_frase, per_la_voce
from .file_utente import (ESTENSIONI as ESTENSIONI_FILE_UTENTE, FileNonLeggibile, nome_risultato,
                          nome_sicuro, testo_del_file)
from .impostazioni import Impostazioni, pausa_server, ssh_eseguibile, stessa_gpu, stesso_ollama
from .remoto import ErroreOllama, crea_cliente
from .sandbox import ErroreSandbox
from ..conferme import proposta_valida, secondi_validi
from ..sicurezza import asks_secret
from .tunnel import Tunnel
from . import ripresa

# Dove sta la configurazione di OpenSSH, per i messaggi (DGX Linux dal 02/10)
_SSH_CONFIG = r".ssh\config" if sys.platform == "win32" else "~/.ssh/config"

# Codici del collegamento → (motivo breve, prossimo passo per la voce e per il terminale)
MOTIVI = {
    "vpn": ("la DGX non risponde (VPN spenta?)",
            "Accendi la VPN dell'ufficio: riprovo da sola alla prossima richiesta."),
    "timeout": ("la DGX non risponde (VPN spenta?)",
                "Accendi la VPN dell'ufficio: riprovo da sola alla prossima richiesta."),
    "nome": ("non trovo l'indirizzo della DGX (VPN spenta o alias mancante?)",
             "Accendi la VPN; se è già accesa, controlla che l'alias sia in " + _SSH_CONFIG + "."),
    "chiave": ("la DGX rifiuta la chiave SSH (non caricata in ssh-agent?)",
               "Carica la chiave con ssh-add e controlla che sia autorizzata sulla DGX: io non "
               "uso password."),
    "host_sconosciuto": ("l'impronta della DGX non è tra gli host noti, o è cambiata",
                         "Collegati una volta a mano con ssh e l'alias da un terminale, e "
                         "controlla l'impronta."),
    "porta_locale": ("la porta locale del tunnel è occupata",
                     "Chiudi il programma che la usa, o cambia porta_locale nel file della DGX."),
    "rifiutato": ("la DGX rifiuta il collegamento SSH",
                  "Controlla che sulla DGX il servizio SSH sia acceso."),
    "config_ssh": ("la configurazione di SSH ha un errore",
                   "Controlla " + _SSH_CONFIG + " da un terminale con ssh e l'alias."),
    "ssh_errore": ("il tunnel SSH non si apre",
                   "Prova da terminale: python -m calliope.agenti --prova."),
    "ssh_mancante": ("manca il client SSH",
                     "Installa il Client OpenSSH: Impostazioni, App, Funzionalità facoltative."
                     if sys.platform == "win32" else
                     "Installa il client OpenSSH: sudo apt install openssh-client."),
    "caduto": ("il tunnel verso la DGX è caduto: lo sto riaprendo",
               "Se non torna, controlla la VPN."),
    "ollama_giu": ("l'Ollama dell'agente non risponde",
                   "Sulla macchina dell'agente avvia Ollama (sulla DGX: sudo systemctl start "
                   "ollama) e controlla la porta."),
    "ollama_errore": ("l'Ollama dell'agente ha dato un errore",
                      "Prova da terminale: python -m calliope.agenti --prova."),
    # motore «openai» (vLLM sulla DGX): script nella home, vedi prove/LEGGIMI.md
    "motore_giu": ("il server del modello dell'agente non risponde",
                   "Sulla macchina dell'agente avvia il motore (sulla DGX: "
                   "~/calliope-motore/avvia.sh) e controlla la porta."),
    "motore_errore": ("il server del modello dell'agente ha dato un errore",
                      "Prova da terminale: python -m calliope.agenti --prova."),
}

_VERBI = re.compile(r"^\s*(?:(?:per favore|puoi|potresti|mi|ti chiedo di|vorrei che)\s+)*"
                    r"(?:scrivi(?:mi)?|crea(?:mi)?|fa(?:mmi|i)|prepara(?:mi)?|"
                    r"genera(?:mi)?|correggi(?:mi)?|sistema(?:mi)?|programma(?:mi)?|"
                    r"compila(?:mi)?|cerca(?:mi)?|ricerca|elabora(?:mi)?|realizza(?:mi)?|"
                    r"redigi(?:mi)?|metti(?:mi)? insieme|organizza(?:mi)?|riassumi(?:mi)?|"
                    r"traduci(?:mi)?|aggiungi(?:mi)?|modifica(?:mi)?|leggi(?:mi)?|"
                    r"controlla(?:mi)?|completa(?:mi)?)\s+", re.I)
_ARTICOLI = re.compile(r"^(?:(?:uno|una|un|il|lo|la|i|gli|le)\s+|(?:un'|l')\s*)", re.I)


def titolo_da(compito: str, parole: int = 7) -> str:
    """«Scrivi uno script che rinomina le foto per data» → «script che rinomina le foto
    per data»: il nome del lavoro detto a voce e usato per la cartella."""
    t = re.sub(r"\s+", " ", str(compito or "")).strip().rstrip(".!?")
    t = _VERBI.sub("", t, count=1)
    t = _ARTICOLI.sub("", t, count=1)
    # Anche a «(»: «carattere_controllo(cf15)» nel titolo finiva letto a voce (04/10)
    words = re.split(r"[,;:(]", t)[0].split()[:parole]
    # Niente coda monca («…rinomina le foto di»)
    while len(words) > 2 and words[-1].lower() in _CODA:
        words.pop()
    return " ".join(words) or "lavoro"


# Un lavoro di codice non è un'estensione di Calliope (06/10, caso vero della DGX: sviluppo_apri
# rifiutato, il modello ha usato lavoro_affida con «Crea un'estensione che…», e l'annuncio
# diceva «ho creato un'estensione», poi «puoi richiamarla chiedendomi l'estensione
# sommaparametri», che non esiste). Correzione della forma di una scelta già fatta (tipo
# codice): nel titolo e nel riassunto detti a voce la parola diventa «programma»
_ART = {"un": "un", "l": "il", "quest": "questo", "quell": "quel", "dell": "del", "all": "al",
        "nell": "nel", "sull": "sul", "dall": "dal", "una": "un", "la": "il", "questa": "questo",
        "quella": "quel", "le": "i", "delle": "dei", "alle": "ai", "nelle": "nei", "sulle": "sui",
        "dalle": "dai", "queste": "questi", "quelle": "quei"}
_PAROLE_ESTENSIONE = re.compile(
    r"\b(?:(un|l|quest|quell|dell|all|nell|sull|dall)['’]\s*|(una|la|questa|quella|le|delle|"
    r"alle|nelle|sulle|dalle|queste|quelle)\s+)?(estension[ei])\b", re.I)


def cosa_ha_fatto(lav, r: dict) -> str:
    """Un lavoro di codice o un'estensione fermato da un tetto senza il codice vero (06/10):
    «ha cercato i dati senza arrivare a scrivere il codice» se ci sono solo pagine d'esempio e
    script d'esplorazione; vuoto se il codice c'è (allora parlano i test)."""
    if getattr(lav, "tipo", "") not in ("codice", "estensione") or getattr(lav, "gioco", False):
        return ""
    files = [str(f) for f in (r.get("file") or [])]
    nomi = [f.rsplit("/", 1)[-1] for f in files]
    esplora = any(f.startswith("esempi/") for f in files) or any(
        n.startswith("esplora") for n in nomi) or bool(getattr(lav, "esempi", 0))
    if lav.tipo == "estensione":
        manca = "estensione.py" not in files
    else:
        codice = [n for f, n in zip(files, nomi) if n.endswith((".py", ".cs"))
                  and not f.startswith(("esempi/", ".calliope/"))
                  and not n.startswith(("esplora", "test"))]
        manca = not codice
    if not manca:
        # Il codice c'è ma nessun test (06/10, prova vera: estensione.py riscritto 4 volte)
        if not r.get("test") and not any(n.startswith("test") for n in nomi):
            return "ha scritto il codice senza arrivare a provarlo"
        return ""

    return ("ha cercato i dati senza arrivare a scrivere il codice" if esplora
            else "non è arrivato a scrivere il codice")


def senza_estensione(testo: str) -> str:

    """«Ho creato un'estensione in Python che…» → «Ho creato un programma in Python che…»."""
    def sost(m):
        art = m[1] or m[2]
        nome = "programmi" if m[3].lower().endswith("i") else "programma"
        out = (_ART[art.lower()] + " " + nome) if art else nome
        primo = m[0][:1]
        return out[:1].upper() + out[1:] if primo.isupper() else out
    return _PAROLE_ESTENSIONE.sub(sost, str(testo or ""))


_ESTENSIONI_DETTE = re.compile(r"\b([\w-]+)\.(?:py|ps1|html?|js|css|csv|tsv|txt|json|xlsx?|"
                               r"docx?|pdf|md|sh|bat|cmd|ini|ya?ml|log|xml|sql)\b", re.I)


def titolo_detto(titolo: str) -> str:
    """Il titolo del lavoro da dire a voce (04/10): «modulo codice_fiscale.py con la funzione
    carattere_controllo» → «modulo codice fiscale con la funzione carattere controllo»;
    passa da per_la_voce, e se lì non resta niente si tengono solo le parole."""
    t = re.sub(r"\([^)]*\)?", " ", str(titolo or ""))
    t = _ESTENSIONI_DETTE.sub(r"\1", t)
    t = re.sub(r"(?<=\w)_(?=\w)", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    detto = per_la_voce(t).rstrip(".").strip()
    if not detto:
        detto = re.sub(r"\s+", " ", re.sub(r"[^\w\s'’-]|_", " ", t)).strip()
    return detto or "il lavoro"


_CODA = frozenset("di a da in con su per tra fra e o il lo la i gli le un uno una del dello "
                  "della dei degli delle al allo alla ai agli alle dal dalla nel nella sul "
                  "sulla che".split())


# Il testo dell'agente nella cartella del lavoro (07/10, documenti/markdown.py)
NOME_RISULTATO = "risultato.md"


def frase_tappa(lav, titolo: str) -> str:
    """Il rapporto di una tappa (08/10, versione 2 della modalità sviluppo), senza il nome di
    chi l'ha chiesto: cosa è fatto, cosa blocca, i segnali di giro a vuoto, la scelta."""
    r = lav.risultato or {}
    perche = {"passate": "ha finito le passate del giro", "tempo": "è finito il tempo del giro",
              "token": "ha finito i token del giro: ho compresso il suo diario"}.get(
        r.get("tipo_limite"), "è arrivato al limite del giro")
    parti = [f"«{titolo}» si è fermato a una tappa: {perche}."]
    fatto = per_la_voce(str(r.get("riassunto") or ""), 220).rstrip(".")
    if fatto:
        parti.append(f"Finora {fatto[:1].lower() + fatto[1:]}.")
    t = r.get("test") or {}
    if isinstance(t, dict) and t.get("eseguiti"):
        n = int(t.get("eseguiti") or 0)
        ko = int(t.get("falliti") or 0) + int(t.get("errori") or 0)
        parti.append(f"I test passano, {n} su {n}." if r.get("test_passano") or not ko
                     else f"Dei test ne passano {max(0, n - ko)} su {max(n, ko)}.")
    manca = [per_la_voce(str(x), 120).rstrip(".") for x in (r.get("manca") or [])[:2]]
    manca = [m for m in manca if m]
    if manca:
        parti.append("Manca: " + "; ".join(manca) + ".")
    seg = (r.get("segnali") or {}).get("frasi") or []
    if seg:
        parti.append("Attenzione, sembra girare a vuoto: " + ", ".join(seg) + ".")
    parti.append("Continuo con un altro giro, vuoi cambiare qualcosa prima, o lo fermo?")
    return " ".join(parti)


def titolo_file(titolo: str) -> str:
    """Il titolo del lavoro come titolo di un file e di un documento: maiuscola in testa."""
    t = re.sub(r"\s+", " ", str(titolo or "")).strip() or "Risultato"
    return t[:1].upper() + t[1:]


def _nome_cartella(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", s).strip(" .")
    return s[:60] or "lavoro"


# La domanda dell'agente come azione in sospeso (Brain.set_pending con «messaggio»): la
# risposta di chi parla non è un «sì», quindi il testo generico di PENDING_MSG («se chi parla
# acconsente…») non va bene. Decide il modello se ciò che dice è la risposta
RISPOSTA_MSG = ("Domanda in sospeso: hai appena chiesto, per il lavoro «{titolo}» affidato "
                "all'agente, «{domanda}». Se chi parla risponde alla domanda (anche solo con il "
                "dato: un nome, una cifra, una data), chiama subito lavoro_rispondi con "
                "lavoro=\"{id}\" e risposta = quello che ha detto, con i dati come detti. Se "
                "parla d'altro, fai quello che chiede.")


class ErroreInput(Exception):
    """Il file della persona non è arrivato o non si legge: il lavoro non parte."""


def _durata(s: float) -> str:
    m = int(s // 60)
    if m < 60:
        return "un minuto" if m <= 1 else f"{m} minuti"
    h = round(m / 60)
    return "un'ora" if h == 1 else f"{h} ore"


def cartella_risultati(cfg) -> Path:
    folder = getattr(cfg, "agenti_risultati", None)
    if folder:
        return Path(folder)
    from ..documenti.consegna import default_folder
    return default_folder() / "Lavori"


def cartella_sandbox(cfg) -> Path:
    p = Path(getattr(cfg, "agenti_sandbox", None) or "lavori")
    if not p.is_absolute():
        base = getattr(cfg, "config_dir", None)
        p = Path(base) / p if base else p.resolve()
    return p


def cartella_modelli(cfg) -> Path:
    folder = getattr(cfg, "agenti_modelli", None)
    if folder:
        return Path(folder)
    from ..documenti.consegna import default_folder
    return default_folder() / "Modelli"


class Lavori:
    def __init__(self, cfg, imp: Impostazioni, on_done=None, biblioteca=None,
                 formati=("word", "excel", "pdf"), log=print, cliente=None, modelli=None,
                 consegna=None):
        self.cfg = cfg
        # Dove tornano i risultati dei lavori fatti sui file della persona: RemoteDelivery
        # (il satellite) o None (restano nella cartella del lavoro, su questo computer)
        self.consegna = consegna
        # Gli esecutori del PC (main.py): il risultato consegnato si offre a «aprilo» (07/10)
        self.pcs: dict = {}
        self.imp = imp
        self.on_done = on_done
        self.log = log
        self.formati = tuple(formati or ())
        self.done: queue.Queue = queue.Queue()
        self.female = getattr(cfg, "gender", "f") == "f"
        self.tunnel = (Tunnel(imp.ssh_alias, imp.porta_locale, imp.porta_remota, imp.timeout_s,
                              ssh=ssh_eseguibile(), log=log) if imp.tunnel else None)
        self.cliente = cliente or crea_cliente(imp)
        self.stesso = stesso_ollama(cfg, imp)
        # Stessa GPU della voce (stesso Ollama, o vLLM sulla stessa macchina: 04/10)
        self.stessa_gpu = stessa_gpu(cfg, imp)
        condiviso = self.stessa_gpu and getattr(cfg, "agenti_precedenza_voce", True)
        self.arbitro = Arbitro(condiviso, float(getattr(cfg, "agenti_ripresa_s", 3.0)),
                               pausa=pausa_server(cfg, imp, log) if condiviso else None,
                               log=log)
        if modelli is None:
            from .modelli import carica_modelli
            modelli = carica_modelli(cartella_modelli(cfg))
        self.modelli = modelli
        self.agente = Agente(cfg, imp, self.cliente, self.arbitro, log=log,
                             biblioteca=biblioteca, modelli=self.modelli,
                             stesso_ollama=self.stesso)
        # La scheda del lavoro in diretta sugli schermi (03/10): solo per i lavori con
        # on_scheda, costruita e mandata da un thread suo, mai da chi lavora
        self.avanzamento = Avanzamento(
            lambda lav=None: (self.agente.max_passi, self.agente.tetto_token(lav),
                              self.agente.tempo_max_s),
            self.arbitro, finale=self.scheda, log=log,
            # Il lavoro di uno sviluppo (08/10): fase, correzione e i numeri dello sviluppo
            sviluppo=lambda lav: (self.sviluppi.riepilogo_lavoro(lav)
                                  if self.sviluppi is not None else None))
        self.diagnosi = {"codice": "non_provato", "stato": "attiva",
                         "motivo": "collegamento non ancora provato", "passo": "",
                         "quando": 0.0}
        self._lock = threading.Lock()        # solo stato in memoria: mai preso durante la rete
        self._verifica_lock = threading.Lock()
        self._coda: queue.Queue = queue.Queue()
        self.lavori: list[Lavoro] = []
        self.corrente: Lavoro | None = None
        self._sandbox = None
        # Il motore della sandbox (docker o processo): lo sceglie il thread dei lavori, che può
        # aspettare Docker; il registro delle capacità legge solo questo
        self.isolamento = None
        # I linguaggi dei programmi (04/10, linguaggi.py): {nome: Isolamento}, Python compreso
        self.isolamenti: dict = {}
        # Il programma di un lavoro eseguito e mostrato in diretta (04/10, esecuzione.py)
        self.esecuzioni = Esecuzioni(self, log=log)
        self._offerte: dict[str, dict] = {}
        self.estensioni = None      # Estensioni (calliope/estensioni/): le versioni da approvare
        # La modalità sviluppo (08/10, calliope/sviluppo.py): la crea load_agenti; None = niente
        self.sviluppi = None
        # L'analisi della richiesta prima della proposta (06/10, richiesta.Analizzatore): la
        # crea load_agenti con agenti_analisi; None = si propone come prima (le prove a secco)
        self.analizzatore = None
        self._n = 0
        self._chiuso = False
        self._worker = threading.Thread(target=self._esegui_coda, daemon=True, name="lavori")
        # I lavori che sopravvivono a un riavvio (06/10, ripresa.py): lo stato su disco, e
        # all'avvio quelli rimasti in coda o in corso diventano «interrotti»
        self._stato_file = ripresa.percorso(cartella_sandbox(cfg))
        self._stato_lock = threading.Lock()
        self._ripristina()
        self._worker.start()

    # ─────────────────────────── collegamento ───────────────────────────
    def _diag(self, codice: str, stato: str, motivo: str = "", passo: str = "", **extra):
        self.diagnosi = {"codice": codice, "stato": stato, "motivo": motivo, "passo": passo,
                         "quando": time.monotonic(), **extra}
        return self.diagnosi

    def verifica(self) -> dict:
        """Apre il tunnel se serve, chiede versione e modelli. Blocca (fino al tempo massimo
        del collegamento): mai dal thread della voce."""
        with self._verifica_lock:
            imp = self.imp
            if self.tunnel is not None:
                code = self.tunnel.assicura(imp.timeout_s)
                if code != "ok":
                    motivo, passo = MOTIVI.get(code, MOTIVI["ssh_errore"])
                    return self._diag(code, "guasta", motivo, passo)
            try:
                ver = self.cliente.versione(timeout=imp.timeout_s)
                nomi = self.cliente.modelli(timeout=imp.timeout_s)
            except ErroreOllama as e:
                motivo, passo = MOTIVI.get(e.codice, MOTIVI["ollama_errore"])
                return self._diag(e.codice, "guasta", motivo, passo)
            mancanti = [m for m in dict.fromkeys([imp.modello, imp.modello_scrittore])
                        if not self.cliente.ha(nomi, m)]
            if mancanti:
                m = mancanti[0]
                dove = imp.su_nome
                passo = (f"Scaricalo {dove} con ollama pull {m}." if imp.motore == "ollama"
                         else f"Il motore {dove} serve altri modelli ({', '.join(nomi) or 'nessuno'}): "
                              f"avvialo con {m} o correggi agente_modello.")
                return self._diag("modello_mancante", "mancante", f"{dove} manca {m}",
                                  passo, versione=ver, modelli=len(nomi))
            caricato = self.cliente.ha(self.cliente.caricati(timeout=imp.timeout_s),
                                       imp.modello)
            return self._diag("ok", "attiva", "", "", versione=ver, modelli=len(nomi),
                              caricato=caricato)

    def verifica_in_secondo_piano(self):
        if self._verifica_lock.locked():
            return
        threading.Thread(target=self.verifica, daemon=True, name="lavori-verifica").start()

    def descrizione(self) -> str:
        """Dove gira l'agente, per il riassunto dell'avvio (mai host o utente)."""
        motore = " (API compatibile OpenAI)" if self.imp.motore == "openai" else ""
        if self.tunnel is not None:
            return (f"{self.imp.modello} {self.imp.su_nome}{motore} via tunnel SSH "
                    f"«{self.imp.ssh_alias}» (porta locale {self.imp.porta_locale})")
        if self.stesso:
            return f"{self.imp.modello} sullo stesso Ollama della voce (la voce ha la precedenza)"
        return f"{self.imp.modello} su {self.imp.url}"

    # ─────────────────────────── lavori ───────────────────────────
    def nuovo(self, tipo, compito, persona=None, persona_nome=None, livello="familiare",
              formato="", modello="", vincoli="", dati=None) -> Lavoro:
        with self._lock:
            self._n += 1
            n = self._n
        lav = Lavoro(f"L{n}", tipo, str(compito or "").strip(), persona, persona_nome, livello,
                     str(formato or ""), str(modello or ""), str(vincoli or ""),
                     list(dati or []))
        lav.titolo = (self.modelli[lav.modello].titolo.lower() if lav.modello in self.modelli
                      else titolo_da(lav.compito))
        if lav.tipo == "codice":
            lav.titolo = senza_estensione(lav.titolo)
            lav.non_estensione = senza_estensione(lav.compito) != lav.compito
        return lav

    def attivi(self, persona=None, attesa: bool = False) -> list[Lavoro]:
        """I lavori in coda o in corso (con `attesa` anche quelli che aspettano una risposta:
        non occupano l'agente)."""
        stati = ("in_coda", "in_corso") + (("in_attesa",) if attesa else ())
        with self._lock:
            return [lv for lv in self.lavori if lv.stato in stati
                    and (persona is None or lv.persona == persona)]

    # ─────────────────────────── domande a metà lavoro ───────────────────────────
    def in_attesa(self, persona=None) -> list[Lavoro]:
        with self._lock:
            return [lv for lv in self.lavori if lv.stato == "in_attesa"
                    and (persona is None or lv.persona == persona)]

    def trova_in_attesa(self, persona, quale: str = "", admin: bool = False):
        """(lavoro, "", False) il lavoro in attesa a cui risponde `persona`; (None, frase,
        altrui) se non c'è o non è suo (`altrui`: c'è, ma è di un altro). `quale`: l'id («L3») o parole del titolo («la relazione»); vuoto va bene
        se ce n'è uno solo."""
        import difflib
        tutti = self.in_attesa()
        if not tutti:
            return None, "Non ho lavori che aspettano una risposta.", False
        q = str(quale or "").strip()
        scelto = None
        if re.fullmatch(r"[Ll]\d+", q):
            scelto = next((lv for lv in tutti if lv.id.lower() == q.lower()), None)
        elif q:
            ql = re.sub(r"\b(il|lo|la|l'|lavoro|della|del|di|per)\b", " ", q.lower()).split()
            def punti(lv):
                t = f"{lv.titolo} {lv.compito}".lower()
                parole = sum(1 for w in ql if len(w) > 2 and w[:-1] in t)
                return parole + difflib.SequenceMatcher(None, " ".join(ql), lv.titolo.lower()
                                                        ).ratio()
            migliori = sorted(tutti, key=punti, reverse=True)
            if punti(migliori[0]) >= 1.0:
                scelto = migliori[0]
        if scelto is None:
            mine = [lv for lv in tutti if admin or lv.persona == persona]
            if len(mine) == 1:
                scelto = mine[0]
            elif not mine:
                return None, ("Le domande dei lavori che aspettano sono per chi li ha chiesti: "
                              "può rispondere solo lui o chi amministra."), True
            else:
                nomi = [f"«{lv.titolo}»" for lv in mine]
                return None, ("Ho più lavori che aspettano una risposta: "
                              + ", ".join(nomi[:-1]) + " e " + nomi[-1] + ". A quale rispondi?"
                              ), False
        if not admin and scelto.persona != persona:
            return None, (f"La domanda di «{scelto.titolo}» è per chi l'ha chiesto: può "
                          f"rispondere solo lui o chi amministra."), True
        return scelto, "", False

    def offerta_risposta(self, lav: Lavoro) -> dict:
        """L'azione in sospeso della domanda di `lav` (Brain.set_pending)."""
        return {"domanda": lav.domanda, "tool": "lavoro_rispondi",
                "cosa": f"la domanda del lavoro «{lav.titolo}»",
                "argomenti": {"lavoro": lav.id},
                "messaggio": RISPOSTA_MSG.format(titolo=lav.titolo, domanda=lav.domanda,
                                                 id=lav.id)}

    @staticmethod
    def in_tappa(lav) -> bool:
        """Il lavoro aspetta alla fine di un giro (08/10, tappe della modalità sviluppo)."""
        return (getattr(lav, "stato", "") == "in_attesa"
                and (getattr(lav, "risultato", None) or {}).get("esito") == "tappa")

    def continua(self, lav: Lavoro, nota: str = "") -> str | None:
        """Un giro nuovo per un lavoro fermo a una tappa (08/10, versione 2 della modalità
        sviluppo): di nuovo tutte le passate, il tempo e i token, con il contesto di prima e la
        nota della persona («cambia e continua»). None se il lavoro non è fermo a una tappa."""
        nota = re.sub(r"\s+", " ", str(nota or "")).strip()[:1000]
        with self._lock:
            if not self.in_tappa(lav):
                return None
            ora = time.time()
            lav.attesa_s += ora - (lav.attesa_dal or ora)
            lav.attesa_dal = None
            lav.giro = int(getattr(lav, "giro", 1) or 1) + 1
            lav.passi0, lav.token0 = lav.passi, lav.token
            lav.attesa0, lav.giro_inizio = lav.attesa_s, ora
            lav.avvisato = False
            if isinstance(lav.segnali, dict):
                lav.segnali["senza_novita"] = 0
            lav.nota_giro = nota
            lav.risposta = nota or "continua"
            lav.stato, lav.passo = "in_coda", f"riprende: giro {lav.giro}"
            occupato = self.corrente is not None
        self.log(f"[AGENTI] {lav.id}: giro {lav.giro}" + (f", con la nota «{nota[:80]}»"
                                                          if nota else ""))
        self._coda.put(lav)
        self._salva_stato()
        return (f"Continuo «{titolo_detto(lav.titolo)}»: un altro giro di "
                f"{_durata(self.agente.tempo_max_s)}"
                + (" con la tua indicazione" if nota else "")
                + (", appena finisce il lavoro in corso" if occupato else "")
                + ". Ti avviso quando è pronto.")

    def rispondi(self, lav: Lavoro, risposta: str) -> str | None:
        """La risposta alla domanda di `lav`: il lavoro torna in coda e riprende da dove era.
        Non aspetta nulla (la voce chiama da qui). None se il lavoro non aspetta più."""
        risposta = re.sub(r"\s+", " ", str(risposta or "")).strip()[:2000]
        if self.in_tappa(lav):
            # La risposta al rapporto di una tappa: un giro nuovo, con la frase come nota
            # se dice più di «continua»
            nuda = re.fullmatch(r"(?i)\W*(sì|si|ok|va bene|continua|vai|avanti|prosegui)\W*",
                                risposta or "")
            return self.continua(lav, "" if nuda else risposta)
        with self._lock:
            if lav.stato != "in_attesa" or not risposta:
                return None
            lav.domande[-1][1] = risposta
            lav.risposta = risposta
            lav.attesa_s += time.time() - (lav.attesa_dal or time.time())
            lav.attesa_dal = None
            lav.stato, lav.passo = "in_coda", "riprende dopo la risposta"
            occupato = self.corrente is not None
        self._coda.put(lav)
        self._salva_stato()
        return (f"Grazie, lo dico all'agente: riprendo «{lav.titolo}»"
                + (" appena finisce il lavoro in corso" if occupato else " in secondo piano")
                + ". Ti avviso quando è pronto.")

    def _scadenze(self):
        """I lavori in attesa da più di agenti_attesa_risposta_min si chiudono da soli."""
        limite = float(getattr(self.cfg, "agenti_attesa_risposta_min", 120.0)) * 60
        ora = time.time()
        with self._lock:
            scaduti = [lv for lv in self.lavori if lv.stato == "in_attesa"
                       and ora - (lv.attesa_dal or ora) > limite]
            for lv in scaduti:
                lv.stato, lv.fine, lv.passo = "scaduto", ora, "chiuso senza risposta"
        for lv in scaduti:
            self.log(f"[AGENTI] {lv.id}: nessuna risposta in {_durata(limite)}: lo chiudo")
            self._chiudi_attesa(lv, {"esito": "scaduto", "attesa": limite})
            self._annuncia(lv)
        if scaduti:
            self._salva_stato()

    def _chiudi_attesa(self, lav: Lavoro, ris: dict):
        """Un lavoro in attesa che finisce senza riprendere (scaduto o annullato): i file fatti
        fin lì restano nella cartella del lavoro."""
        dest = Path(lav.cartella) if lav.cartella else self._cartella_lavoro(lav)
        ris = {**ris, "domanda": lav.domanda, "cartella": str(dest)}
        sb = lav.sandbox
        if sb is not None:
            try:
                ris["file"] = sb.copia_in(dest)
            except OSError:
                pass
        lav.risultato = ris
        lav.contesto, lav.sandbox, lav.input = {}, None, None
        self._metadati(lav, dest)

    def _filtra_segreti(self, lav: Lavoro, ris: dict):
        """L'agente non chiede mai segreti (password, PIN, codici, token, il wifi): una
        domanda o un riassunto che li chiede non si dice e il lavoro si chiude. Con un file
        della persona che glielo ordinava nei commenti, gemma4 chiedeva la password del wifi
        6 volte su 6 (analisi di sicurezza del 03/10, agenti, difetto 2)."""
        dom = str(ris.get("domanda") or "")
        ria = str(ris.get("riassunto") or "")
        if not (asks_secret(dom) or asks_secret(ria)):
            return
        self.log(f"[AGENTI] {lav.id}: l'agente ha chiesto un dato riservato: non lo riferisco")
        ris.update(esito="impossibile", domanda="", riassunto="",
                   motivo="l'agente mi ha chiesto un dato riservato, come una password: non "
                          "lo chiedo, e il lavoro si ferma qui")

    def _puo_chiedere(self, lav: Lavoro, ris: dict) -> bool:
        self._filtra_segreti(lav, ris)
        return (ris.get("esito") == "mancano_dati" and bool(str(ris.get("domanda") or "").strip())
                and len(lav.domande) < int(getattr(self.cfg, "agenti_domande_max", 3))
                and not lav.annulla.is_set())

    def _sospendi(self, lav: Lavoro, ris: dict, dest: Path):
        dom = re.sub(r"\s+", " ", str(ris.get("domanda") or "")).strip()[:300]
        if not dom.endswith("?"):
            dom = dom.rstrip(".!:;,") + "?"
        with self._lock:
            lav.domande.append([dom, None])
            lav.stato, lav.passo = "in_attesa", "aspetta una risposta"
            lav.attesa_dal = time.time()
        lav.risultato = {"esito": "domanda", "domanda": dom, "cartella": str(dest)}
        self.log(f"[AGENTI] {lav.id}: domanda a {lav.persona_nome or 'chi l’ha chiesto'}")
        self._metadati(lav, dest)
        self._annuncia(lav)

    # ─────────────────────────── i file della persona ───────────────────────────
    def max_byte_file(self) -> int:
        return int(float(getattr(self.cfg, "agenti_file_max_mb", 10.0)) * 1048576)

    def _prendi_file(self, lav: Lavoro):
        """La copia del file della persona, in secondo piano subito dopo il «sì»: dal PC
        locale o dal satellite (a pezzi, con lo SHA-256). Mai dal thread della voce."""
        fu = lav.file_utente or {}
        try:
            r = fu["ex"].copia_file(fu["item"], self.max_byte_file(), ESTENSIONI_FILE_UTENTE)
        except TimeoutError as e:
            r = {"ok": False, "errore": str(e) or "il PC non ha risposto in tempo"}
        except ConnectionError as e:
            r = {"ok": False, "errore": str(e) or "il PC si è scollegato"}
        except Exception as e:  # noqa: BLE001 — diventa l'errore del lavoro
            r = {"ok": False, "errore": f"c'è stato un problema ({type(e).__name__})"}
        if r.get("ok"):
            lav.input = {"nome": str(r["nome"]), "estensione": str(r["estensione"]),
                         "dati": bytes(r["dati"]), "percorso": nome_sicuro(r["nome"])}
            self.log(f"[AGENTI] {lav.id}: copia del file arrivata "
                     f"({len(r['dati']) / 1024:.0f} KB)")
        else:
            lav.input_errore = str(r.get("errore") or "non è arrivato")
            self.log(f"[AGENTI] {lav.id}: il file non è arrivato ({lav.input_errore})")
        lav.input_pronto.set()

    def _prepara_input(self, lav: Lavoro):
        """Nel thread dei lavori: aspetta la copia (già partita al «sì») e ne estrae il testo
        per i lavori che non sono codice."""
        fu = lav.file_utente or {}
        attesa = 30.0 + self.max_byte_file() / 1048576
        fine = time.monotonic() + attesa
        lav.passo = "prende il file"
        while not lav.input_pronto.wait(0.2):
            if lav.annulla.is_set():
                raise Annullato()
            if time.monotonic() > fine:
                raise ErroreInput(f"non ho ricevuto {fu.get('detto', 'il file')} in tempo")
        if lav.input is None:
            raise ErroreInput(f"non ho potuto prendere {fu.get('detto', 'il file')}: "
                              f"{lav.input_errore}")
        if lav.tipo != "codice" and not lav.input_testo:
            try:
                lav.input_testo = testo_del_file(
                    lav.input["nome"], lav.input["dati"],
                    int(getattr(self.cfg, "agenti_file_caratteri", 40000)))
            except FileNonLeggibile as e:
                raise ErroreInput(f"non riesco a leggere {fu.get('detto', 'il file')}: {e}") \
                    from None

    def _consegna_utente(self, lav: Lavoro, ris: dict, dest: Path):
        """Il risultato di un lavoro su un file della persona: un file nuovo («backup
        (corretto).py»), mai l'originale; con il satellite va nella cartella Calliope dei
        Documenti del portatile (RemoteDelivery), altrimenti resta nella cartella del lavoro."""
        inp = lav.input
        uscite: list[Path] = []
        files = list(ris.get("file") or [])
        orig = Path(inp["percorso"])
        if lav.tipo == "codice":
            p = dest / orig.name
            if p.is_file() and p.read_bytes() != inp["dati"]:
                nuovo = dest / nome_risultato(orig.name, "codice")
                os.replace(p, nuovo)
                files = [nuovo.name if f == orig.name else f for f in files]
                uscite.append(nuovo)
            for f in files:
                n = Path(f).name
                if "/" in f or n == orig.name or n in (lav.file_iniziali or {}) or \
                        n.startswith("test") or n.endswith("_test.py") or \
                        (uscite and n == uscite[0].name):
                    continue
                uscite.append(dest / f)
        else:
            for f in files:
                p = dest / f
                if p.stem.lower() == orig.stem.lower():
                    nuovo = dest / nome_risultato(f"{p.stem}{p.suffix}", lav.tipo)
                    os.replace(p, nuovo)
                    files = [nuovo.name if x == f else x for x in files]
                    p = nuovo
                uscite.append(p)
        ris["file"] = files
        ris["consegnati"], ris["dove"] = [], "nella cartella Lavori dei Documenti"
        if not uscite:
            return
        if self.consegna is None:
            ris["consegnati"] = [p.name for p in uscite]
            return
        from ..documenti.formato import safe_filename
        from ..satellite.protocollo import ESTENSIONI_RICEVUTE
        dove = set()
        for p in uscite:
            ext = p.suffix.lower().lstrip(".")
            stem = p.stem
            if ext not in ESTENSIONI_RICEVUTE:      # .js, .bat…: arriva come testo
                stem, ext = p.name, "txt"
            try:
                d = self.consegna.deliver(safe_filename(stem), ext, p.read_bytes())
            except Exception as e:  # noqa: BLE001 — il file resta comunque qui
                self.log(f"[AGENTI] {lav.id}: consegna non riuscita: {type(e).__name__}: {e}")
                continue
            ris["consegnati"].append(d["nome_file"])
            dove.add(d.get("dove") or self.consegna.where())
        if dove:
            ris["dove"] = sorted(dove)[0]

    def collegamento_guasto(self, recente_s: float = 30.0) -> dict | None:
        """La diagnosi, se dice che l'agente non è raggiungibile da poco: allora la delega si
        rifiuta subito (e si riprova in secondo piano). Più vecchia, si lascia provare al
        lavoro: la VPN può essere stata accesa nel frattempo."""
        d = self.diagnosi
        if d.get("stato") in ("guasta", "mancante") and time.monotonic() - d["quando"] < recente_s:
            return d
        return None

    def serve_conferma(self, lav: Lavoro) -> bool:
        # Un file della persona lascia il PC: la conferma c'è sempre (03/10)
        if lav.file_utente is not None or getattr(lav, "file_candidati", None):
            return True
        mode = str(getattr(self.cfg, "agenti_conferma", "costosi") or "costosi").lower()
        if mode == "sempre":
            return True
        if mode == "mai":
            return False
        # Le ricerche partono senza «Procedo?» (decisione di Dario, 08/10): le chiede la persona
        # in modo esplicito e costano poco; il codice e le estensioni lo chiedono ancora
        if lav.tipo in ("codice", "estensione"):
            return True
        if self.attivi():
            return True
        return self.diagnosi.get("caricato") is False

    def proposta(self, lav: Lavoro) -> str:
        cand = getattr(lav, "file_candidati", None) or []
        if len(cand) > 1:
            nomi = [c["detto"] for c in cand]
            return (f"Ho trovato {len(cand)} file: " + ", ".join(nomi[:-1]) + " e " + nomi[-1]
                    + ". Quale mando all'agente? Lavora su una copia: l'originale non lo tocco.")
        if lav.file_utente is not None:
            stima = {"codice": "Ci vorranno alcuni minuti", "ricerca": "Ci vorrà qualche minuto",
                     "documento": "Ci vorranno un paio di minuti",
                     "estensione": "Ci vorranno alcuni minuti",
                     "altro": "Ci vorrà qualche minuto"}[lav.tipo]
            return (f"Mando una copia {lav.file_utente['detto_di']} all'agente "
                    f"{self.imp.su_nome}: lavora sulla copia, e il risultato torna come file "
                    f"nuovo; l'originale non lo tocco. {stima}. Procedo?")
        return self._proposta(lav)

    def _proposta(self, lav: Lavoro) -> str:
        cosa = {"codice": "È un lavoro di programmazione", "ricerca": "È una ricerca a più passi",
                "documento": "È un documento lungo", "altro": "È un lavoro lungo",
                "estensione": ("È la modifica di una funzione di Calliope" if getattr(
                    lav, "estensione", None) else "È una funzione nuova di Calliope")}[lav.tipo]
        if lav.modello and lav.modello in self.modelli:
            cosa = f"È {self.modelli[lav.modello].titolo.lower()} da compilare"
        stima = {"codice": "Ci vorranno alcuni minuti", "ricerca": "Ci vorrà qualche minuto",
                 "documento": "Ci vorranno un paio di minuti",
                 "estensione": "Ci vorranno alcuni minuti, poi te la faccio approvare",
                 "altro": "Ci vorrà qualche minuto"}[lav.tipo]
        att = self.attivi()
        coda = f"; prima devo finire «{att[0].titolo}»" if att else ""
        carico = ("; prima devo caricare il modello, ci vuole un minuto in più"
                  if self.diagnosi.get("caricato") is False else "")
        # La specifica raffinata dall'analisi della richiesta (06/10): la persona sente cosa
        # si farà davvero prima del «sì»
        spec = str(getattr(lav, "specifica", "") or "").strip().rstrip(".")
        prima = f"Ho capito così: {spec[:1].lower() + spec[1:]}. " if spec else ""
        return (f"{prima}{cosa}: lo affido all'agente {self.imp.su_nome}{coda}{carico}. {stima} "
                f"e ti avviso quando ha finito. Procedo?")


    def proponi(self, lav: Lavoro, turno: int) -> str:
        frase = self.proposta(lav)
        with self._lock:
            self._offerte[lav.persona or "?"] = {
                "lavoro": lav, "turno": turno,
                "scade": time.monotonic() + secondi_validi(self.cfg)}
        return frase

    def offerta(self, persona, turno: int) -> dict | None:
        """L'offerta ancora valida per questa persona (senza consumarla): nei turni dopo la
        proposta, per `azione_in_sospeso_turni` turni ed entro `azione_in_sospeso_s` (04/10:
        prima solo nella risposta subito dopo, e un turno in mezzo la consumava)."""
        with self._lock:
            off = self._offerte.get(persona or "?")
            if off is not None and time.monotonic() > off["scade"]:
                self._offerte.pop(persona or "?", None)
                return None
        if off is None:
            # Un lavoro interrotto da un riavvio, già annunciato con «Lo rifaccio?» (ripresa.py):
            # vale senza turno (l'annuncio non è una risposta); il «sì» lo controlla l'azione
            # in sospeso del Brain (persona, turni, satellite)
            primo = self._interrotti_da_rifare(persona)
            return {"lavoro": primo[0], "turno": None, "ripresa": True} if primo else None
        if not proposta_valida(self.cfg, off["turno"], turno):
            return None
        return off

    def conferma(self, persona, offerta: str, turno: int) -> Lavoro | None:
        """Il lavoro proposto a questa persona, se `offerta` è il suo id e la proposta vale
        ancora; la consuma solo allora (un «sì» rifiutato per la voce non la perde)."""
        off = self.offerta(persona, turno)
        if off is None or off["lavoro"].id != str(offerta or "").strip():
            return None
        if off.get("ripresa"):
            return self._rifai_interrotti(persona)
        with self._lock:
            self._offerte.pop(persona or "?", None)
        return off["lavoro"]

    def avvia(self, lav: Lavoro) -> str:
        att = self.attivi()
        with self._lock:
            self.lavori.append(lav)
            # I lavori in attesa di una risposta non escono dall'elenco
            vecchi = [lv for lv in self.lavori[:-30] if lv.stato != "in_attesa"]
            self.lavori = [lv for lv in self.lavori if lv not in vecchi]
        if lav.on_scheda is not None and getattr(lav, "segui_schermi", True):
            self.avanzamento.segui(lav)       # la scheda compare subito, «in coda»
        if lav.file_utente is not None and not lav.input_pronto.is_set():
            # La copia del file parte subito, al «sì»: non aspetta il suo turno nella coda
            threading.Thread(target=self._prendi_file, args=(lav,), daemon=True,
                             name="lavori-file").start()
        self._coda.put(lav)
        for altro in getattr(lav, "insieme", None) or ():      # ripresi con lui (ripresa.py)
            with self._lock:
                self.lavori.append(altro)
            self._coda.put(altro)
        self._salva_stato()
        if att:
            return (f"D'accordo: lo metto in coda dopo «{att[0].titolo}». Ti avviso quando è "
                    f"pronto.")
        return ("Ci lavoro in secondo piano: ti avviso quando è pronto. Intanto puoi chiedermi "
                "altro.")

    def stato(self, persona=None, tutti: bool = False) -> str:
        with self._lock:
            mine = [lv for lv in self.lavori if tutti or lv.persona == persona]
        corso = [lv for lv in mine if lv.stato == "in_corso"]
        coda = [lv for lv in mine if lv.stato == "in_coda"]
        attesa = [lv for lv in mine if lv.stato == "in_attesa"]
        # Interrotti da un riavvio (06/10, ripresa.py): mai «Non ho lavori in corso.» e basta
        interrotti = self._frase_interrotti([lv for lv in mine if lv.stato == "interrotto"],
                                            persona)
        if attesa:
            # Prima la domanda: è l'unica cosa che aspetta chi parla
            lv = attesa[-1]
            chi = f" di {lv.persona_nome}" if tutti and lv.persona != persona and \
                lv.persona_nome else ""
            frase = (f"«{lv.titolo}»{chi} è fermo a una tappa: aspetta che tu dica se "
                     f"continuare con un altro giro." if self.in_tappa(lv)
                     else f"«{lv.titolo}»{chi} aspetta una risposta: {lv.domanda}")
            altri = len(corso) + len(coda)
            if altri:
                frase = (f"{'Ho un altro lavoro' if altri == 1 else f'Ho {altri} lavori'} "
                         f"in corso. " + frase)
            # La domanda dell'agente resta l'ultima cosa detta: gli interrotti prima
            return (f"{interrotti.split(':')[0].rstrip('.')}. " if interrotti else "") + frase
        if corso:
            lv = corso[0]
            minuti = max(0, int((time.time() - (lv.inizio or time.time())) / 60))
            da = ("da meno di un minuto" if minuti < 1 else "da un minuto" if minuti == 1
                  else f"da {minuti} minuti")
            chi = f" per {lv.persona_nome}" if tutti and lv.persona != persona and \
                lv.persona_nome else ""
            frase = (f"Sto lavorando a «{lv.titolo}»{chi} {da}: l'agente {lv.passo}, "
                     f"al passo {lv.passi + 1}.")
            if coda:
                frase += (f" Poi c'è «{coda[0].titolo}» in coda." if len(coda) == 1
                          else f" Poi ce ne sono {len(coda)} in coda.")
            return frase + (f" {interrotti}" if interrotti else "")
        if coda:
            return (f"«{coda[0].titolo}» è in coda: comincio appena posso."
                    + (f" {interrotti}" if interrotti else ""))
        if interrotti:
            return f"Non ho lavori in corso. {interrotti}"
        finiti = [lv for lv in mine if lv.stato not in ("in_coda", "in_corso")]
        if finiti:
            lv = finiti[-1]
            come = {"fatto": "è finito", "mancano_dati": "aspetta dei dati da te",
                    "errore": "non è riuscito", "annullato": "è stato annullato",
                    "scaduto": "l'ho chiuso perché aspettava una risposta da troppo",
                    "ripreso": "si era interrotto per un riavvio, e l'ho rifatto"}.get(
                lv.stato, lv.stato)
            return f"Non ho lavori in corso. L'ultimo, «{lv.titolo}», {come}."
        return "Non ho lavori in corso."

    def annulla(self, persona=None, tutti_di_tutti: bool = False, quale: str = "ultimo") -> dict:
        """Ferma il lavoro in corso (o in coda) di `persona`; chi amministra può fermare
        anche quelli degli altri. Non aspetta: il lavoro si ferma da sé entro un attimo."""
        with self._lock:
            mine = [lv for lv in self.lavori if lv.stato in ("in_coda", "in_corso", "in_attesa")
                    and (tutti_di_tutti or lv.persona == persona)]
        if not mine:
            others = self.attivi(attesa=True)
            if others and not tutti_di_tutti:
                return {"ok": False, "frase": "Non hai lavori in corso: quelli che vedo sono di "
                                              "altri, e li può fermare solo chi li ha chiesti o "
                                              "chi amministra."}
            return {"ok": False, "frase": "Non ho lavori in corso da fermare."}
        if re.fullmatch(r"L\d+", str(quale or "")):
            # Un lavoro preciso (08/10, modalità sviluppo: si torna all'analisi e il lavoro di
            # quello sviluppo si ferma, non un altro)
            targets = [lv for lv in mine if lv.id == quale]
            if not targets:
                return {"ok": False, "frase": "Quel lavoro non è più in corso."}
        else:
            targets = mine if quale == "tutti" else [next((lv for lv in mine
                                                           if lv.stato == "in_corso"), mine[-1])]
        for lv in targets:
            lv.annulla.set()
            with self._lock:
                era = lv.stato
                if lv.stato in ("in_coda", "in_attesa"):
                    lv.stato, lv.passo, lv.fine = "annullato", "annullato", time.time()
            if era == "in_attesa":
                # La copia dei file fatti fin lì tocca il disco: non nel thread della voce
                def chiudi(lv=lv):
                    self._chiudi_attesa(lv, {"esito": "annullato"})
                    self._scheda_finale(lv)
                threading.Thread(target=chiudi, daemon=True, name="lavori-annullo").start()
            elif era == "in_coda":
                # La scheda «annullato» la costruisce il thread degli schermi
                self._scheda_finale(lv, sincrona=False)
        if any(lv is self.corrente for lv in targets):
            # Solo lo stream del thread dei lavori: lo stesso client può servire l'ufficio
            _interrompi(self.cliente, self._worker.ident)
            sb = self._sandbox
            if sb is not None:
                sb.termina()
        self._salva_stato()
        nomi = [f"«{lv.titolo}»" for lv in targets]
        cosa = nomi[0] if len(nomi) == 1 else ", ".join(nomi[:-1]) + " e " + nomi[-1]
        return {"ok": True, "frase": f"Ho fermato {cosa}. Quello che era già fatto resta nella "
                                     f"cartella Lavori dei Documenti."
                if len(targets) == 1 else f"Ho fermato {cosa}."}

    # ─────────────────────────── esecuzione ───────────────────────────
    def scegli_isolamento(self):
        """Chiede a Docker se l'immagine della sandbox c'è (fino a 5 s): mai dalla voce."""
        from .sandbox import scegli_isolamento
        try:
            self.isolamento = scegli_isolamento(
                getattr(self.cfg, "agenti_sandbox_motore", "auto"),
                getattr(self.cfg, "agenti_sandbox_immagine", None))
        except Exception as e:  # noqa: BLE001
            self.log(f"[AGENTI] scelta della sandbox: {type(e).__name__}: {e}")
        try:
            from .linguaggi import scegli
            self.isolamenti = scegli(self.cfg, self.isolamento)
        except Exception as e:  # noqa: BLE001
            self.log(f"[AGENTI] linguaggi della sandbox: {type(e).__name__}: {e}")
        return self.isolamento

    def _esegui_coda(self):
        self.scegli_isolamento()
        try:
            self._annuncia_ripresi()
        except Exception as e:  # noqa: BLE001 — un annuncio rotto non ferma la coda
            self.log(f"[AGENTI] annuncio dei lavori interrotti: {type(e).__name__}: {e}")
        while not self._chiuso:
            try:
                self._scadenze()
            except Exception as e:  # noqa: BLE001 — una scadenza rotta non ferma la coda
                self.log(f"[AGENTI] controllo delle attese: {type(e).__name__}: {e}")
            try:
                lav = self._coda.get(timeout=0.5)
            except queue.Empty:
                continue
            if lav is None:
                break
            if lav.annulla.is_set() or lav.stato == "annullato":
                lav.stato, lav.fine = "annullato", time.time()
                continue
            self.corrente = lav
            try:
                self._esegui(lav)
            except Exception as e:  # noqa: BLE001 — un lavoro rotto non ferma la coda
                self.log(f"[AGENTI] errore inatteso in {lav.id}: {type(e).__name__}: {e}")
                lav.stato = "errore"
                lav.risultato = {"esito": "errore", "motivo": "c'è stato un problema"}
                self._annuncia(lav)
            finally:
                self.corrente = None
                self._sandbox = None
                self._salva_stato()

    def _esegui(self, lav: Lavoro):
        ripresa = lav.risposta is not None
        lav.stato, lav.passo = "in_corso", "si collega all'agente"
        if not ripresa:
            lav.inizio = time.time()
        d = self.verifica()
        if d["codice"] != "ok":
            lav.stato, lav.fine = "errore", time.time()
            ris = {"esito": "errore", "motivo": d["motivo"], "passo": d["passo"],
                   "codice": d["codice"]}
            if ripresa:          # i file fatti prima della domanda restano nella cartella
                self._chiudi_attesa(lav, ris)
            else:
                lav.risultato = ris
            self._annuncia(lav)
            return
        # Alla ripresa dopo una domanda la cartella è la stessa
        dest = Path(lav.cartella) if lav.cartella else self._cartella_lavoro(lav)
        lav.cartella = str(dest)
        self._salva_stato()
        ris: dict = {}
        try:
            if lav.file_utente is not None:
                self._prepara_input(lav)
            if lav.tipo in ("codice", "estensione"):
                sb = lav.sandbox
                if sb is None:
                    from .sandbox import Sandbox
                    # Un lavoro ripreso dopo un riavvio (ripresa.py): la sua sandbox di prima
                    riuso = getattr(lav, "sandbox_da", None)
                    root = (Path(riuso) if riuso else cartella_sandbox(self.cfg)
                            / f"{lav.id}-{time.strftime('%Y%m%d-%H%M%S')}")
                    iso = self.scegli_isolamento()   # di nuovo: l'immagine può essere arrivata ora
                    sb = Sandbox(root, float(getattr(self.cfg, "agenti_esecuzione_s", 30.0)),
                                 int(getattr(self.cfg, "agenti_memoria_mb", 1024)),
                                 max_totale=5_000_000 + (len(lav.input["dati"])
                                                         if lav.input else 0),
                                 isolamento=iso,
                                 cpu=float(getattr(self.cfg, "agenti_sandbox_cpu", 2.0)),
                                 linguaggi=self.isolamenti)
                    self.log(f"[AGENTI] {lav.id}: sandbox {sb.isolamento.descrizione}")
                    lav.sandbox = sb
                    self._salva_stato()
                    for nome, testo in (lav.file_iniziali or {}).items():
                        if not (riuso and (sb.root / nome).is_file()):
                            sb.scrivi(nome, testo)
                    if lav.input:
                        sb.metti(lav.input["percorso"], lav.input["dati"])
                self._sandbox = sb
                if lav.tipo == "estensione":
                    from ..estensioni import contratto
                    from ..estensioni.prompt import sistema_estensione
                    est = getattr(self, "estensioni", None)
                    presi = est.archivio.nomi() if est is not None else ()
                    atteso = getattr(lav, "estensione", None)
                    # Il contratto delle capacità (05/10): nel prompt e nella cartella, in sola
                    # lettura, con il runtime; il primo passo è il piano
                    gioco = bool(getattr(lav, "gioco", False))
                    if contratto.FILE not in sb.sola_lettura:
                        try:
                            sb.scrivi(contratto.FILE, contratto.testo(
                                self.cfg, "gioco" if gioco else "estensione"))
                        except Exception as e:  # noqa: BLE001 — resta il prompt
                            self.log(f"[AGENTI] {lav.id}: {contratto.FILE} non scritto: {e}")
                        sb.sola_lettura |= {contratto.FILE, "calliope_estensione.py"}
                    ris = self.agente.codice(
                        lav, sb, sistema=sistema_estensione(self.cfg, gioco=gioco),
                        controlla=self._controlla_estensione(lav, presi, atteso),
                        esempi=True, piano=True)
                else:
                    ris = self.agente.codice(lav, sb)
                lav.risposta = None
                if ris.get("esito") == "tappa":
                    self._tappa(lav, ris, dest, sb)
                    return
                if self._puo_chiedere(lav, ris):
                    self._sospendi(lav, ris, dest)
                    return
                ris["file"] = sb.copia_in(dest)
                if lav.tipo == "estensione" and ris.get("esito") == "fatto":
                    # La versione da approvare (calliope/estensioni/): annuncio con la domanda
                    est = getattr(self, "estensioni", None)
                    c = (est.candidata_da_lavoro(lav, sb, ris) if est is not None
                         else {"errore": "le estensioni non sono attive"})
                    if "errore" in c:
                        ris.update(esito="errore", motivo=c["errore"])
                    else:
                        ris["estensione"] = c
            elif lav.tipo == "documento" and lav.modello:
                ris = self.agente.da_modello(lav)
            elif lav.tipo == "documento":
                ris = self.agente.documento(lav, self.formati or ("word",))
            elif lav.tipo == "ricerca":
                ris = self.agente.ricerca(lav)
            else:
                ris = self.agente.altro(lav)
            lav.risposta = None
            if self._puo_chiedere(lav, ris):
                self._sospendi(lav, ris, dest)
                return
            if ris.get("documento") is not None:
                ris.update(self._scrivi_documento(lav, ris, dest))
            elif ris.get("testo"):
                ris.update(self._scrivi_testo(lav, ris, dest))
            lav.stato = {"fatto": "fatto", "mancano_dati": "mancano_dati"}.get(
                ris.get("esito"), "errore")
            if lav.stato == "errore" and not ris.get("motivo"):
                ris["motivo"] = (per_la_voce(ris.get("riassunto")) or
                                 "l'agente non è riuscito a farlo")
            if lav.stato == "fatto" and lav.input:
                self._consegna_utente(lav, ris, dest)
            elif lav.stato == "fatto" and lav.tipo not in ("codice", "estensione"):
                self._consegna_risultato(lav, ris, dest)
        except ErroreInput as e:
            lav.stato = "errore"
            ris = {"esito": "errore", "motivo": str(e)}
        except Annullato:
            lav.stato = "annullato"
            ris = {"esito": "annullato"}
            if self._sandbox is not None:
                ris["file"] = self._sandbox.copia_in(dest)
        except Limite as e:
            lav.stato = "errore"
            ris = {"esito": "limite", "motivo": f"ho dovuto fermarlo: {e}",
                   **{k: v for k, v in e.parziale.items() if v}}
            if self._sandbox is not None:
                ris.update(self._parziale(lav, self._sandbox, dest))
        except ErroreSandbox as e:
            lav.stato = "errore"
            self.log(f"[AGENTI] {lav.id}: {e}")
            ris = {"esito": "errore", "motivo": "la sandbox per eseguire il codice non è pronta",
                   "passo": (self.isolamento.passo if self.isolamento else ""),
                   "errore": str(e)}
        except ErroreOllama as e:
            lav.stato = "errore"
            self.log(f"[AGENTI] {lav.id}: Ollama dell'agente: {e.codice}: {str(e)[:200]}")
            code, frase = errore_ollama_frase(e, self.imp)
            ris = {"esito": "errore", "motivo": frase, "codice": code}
            self.verifica_in_secondo_piano()
        except Exception as e:  # noqa: BLE001
            from ..documenti.formato import DocumentoNonValido
            lav.stato = "errore"
            why = ("il documento uscito non era valido" if isinstance(e, DocumentoNonValido)
                   else "c'è stato un problema")
            self.log(f"[AGENTI] {lav.id}: {type(e).__name__}: {e}")
            ris = {"esito": "errore", "motivo": why, "errore": f"{type(e).__name__}: {e}"}
        lav.fine = time.time()
        ris["cartella"] = str(dest)
        lav.risultato = ris
        # Il contesto di un lavoro di uno sviluppo resta finché lo sviluppo è aperto o sospeso
        # (08/10, versione 2: sviluppo_chiedi e sviluppo_correggi ripartono da lì)
        self._conserva(lav)
        # Finito: il contesto per una ripresa non serve più (i file restano su disco)
        lav.contesto, lav.sandbox = {}, None
        self._metadati(lav, dest)
        if lav.stato != "annullato":
            # Il programma finito si esegue sullo schermo prima dell'annuncio (04/10)
            es = self.esecuzioni.dimostra(lav)
            self._annuncia(lav)
            if es is not None:
                self.esecuzioni.in_cima(es)       # la scheda del lavoro è appena andata in cima
        else:
            self._scheda_finale(lav)

    def _conserva(self, lav: Lavoro):
        svs = getattr(self, "sviluppi", None)
        if svs is None:
            return
        try:
            svs.conserva(lav)
        except Exception as e:  # noqa: BLE001 — il lavoro finisce comunque
            self.log(f"[AGENTI] {lav.id}: contesto dello sviluppo non conservato: {e}")

    def _controlla_estensione(self, lav, presi, atteso):
        """Il controllo della consegna di un lavoro «estensione»: quello di sempre
        (`controlla_consegna`: manifesto, nome, test) e, se passa, il ricollaudo alla consegna
        (08/10 notte, calliope/sonde.py): in un lavoro di uno sviluppo con dei collaudi che non
        andavano, la versione nuova si prova con quei casi prima di dire «è pronto», una volta
        per lavoro."""
        from ..estensioni.prompt import controlla_consegna

        def controlla(sandbox):
            errore = controlla_consegna(sandbox, nomi_presi=presi, nome_atteso=atteso)
            if errore:
                return errore
            svs = self.sviluppi
            if svs is None or getattr(lav, "ricollaudo_fatto", False):
                return None
            try:
                sv = svs.di_lavoro(lav.id, lav.persona, chiusi=True)
                if sv is None or not sv.collaudi:
                    return None
                from ..sonde import ricollaudo
                return ricollaudo(self.cfg, getattr(self, "estensioni", None), svs, sv, lav,
                                  sandbox, log=self.log,
                                  resta_tempo=lambda: self.agente._resta_tempo(lav))
            except Exception as e:  # noqa: BLE001 — il ricollaudo non ferma la consegna
                self.log(f"[AGENTI] {lav.id}: ricollaudo non riuscito: {type(e).__name__}: {e}")
                return None
        return controlla

    def _tappa(self, lav: Lavoro, ris: dict, dest: Path, sb):
        """Un tetto del giro in un lavoro di uno sviluppo (08/10): il lavoro aspetta con il
        contesto e la sandbox, i file fatti fin qui nella cartella, e il rapporto si annuncia
        (calliope/sviluppo.py lo dice e chiede se continuare)."""
        ris = {**ris, "cartella": str(dest)}
        try:
            ris["file"] = sb.copia_in(dest)
        except OSError:
            pass
        with self._lock:
            lav.stato, lav.passo = "in_attesa", "aspetta: fine del giro"
            lav.attesa_dal = time.time()
        lav.risultato = ris
        self._metadati(lav, dest)
        self._conserva(lav)
        self._annuncia(lav)

    def _parziale(self, lav: Lavoro, sb, dest: Path) -> dict:
        """Un lavoro di codice fermato da un tetto (06/10): i file nella cartella e l'esito dei
        test rifatti dal programma, perché l'annuncio dica cosa funziona già."""
        out = {"file": sb.copia_in(dest)}
        try:
            if self.agente._ha_test(sb):
                lav.passo = "controlla i test"
                r = sb.test()
                out.update(test=r.get("esito"), test_passano=r.get("passano"),
                           test_uscita=str(r.get("uscita") or "")[-3000:])
        except Exception as e:  # noqa: BLE001 — i file restano comunque
            self.log(f"[AGENTI] {lav.id}: test dopo il tetto non eseguiti: {e}")
        return out

    def _cartella_lavoro(self, lav: Lavoro) -> Path:
        base = cartella_risultati(self.cfg)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H%M")
        dest = base / _nome_cartella(f"{stamp} {lav.titolo}")
        n = 2
        while dest.exists():
            dest = base / _nome_cartella(f"{stamp} {lav.titolo} ({n})")
            n += 1
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def _scrivi_documento(self, lav, ris, dest: Path) -> dict:
        from ..documenti.consegna import LocalDelivery
        from ..documenti.formato import ESTENSIONI, safe_filename, summary
        from ..documenti.render import render
        doc, formato = ris["documento"], ris["formato"]
        data = render(formato, doc, getattr(self.cfg, "documenti_font", None))
        d = LocalDelivery(dest).deliver(safe_filename(doc["titolo"]), ESTENSIONI[formato], data)
        return {"file": [d["nome_file"]], "rif": d["rif"],
                "contenuto": summary(formato, doc, False)}

    def _scrivi_testo(self, lav, ris, dest: Path) -> dict:
        """Il testo dell'agente come `risultato.md` (07/10: prima la ricerca diventava un Word
        di soli paragrafi, e gli altri lavori un .txt). Il titolo in cima se manca; PDF e Word
        si fanno a richiesta («Scarica», «fammene un PDF»)."""
        from ..documenti import markdown as md
        testo, tolto = md.senza_recinto(str(ris.get("testo") or ""))
        if tolto:
            self.log(f"[AGENTI] {lav.id}: il testo era tutto in un recinto ```markdown: tolto")
        testo = md.con_titolo(testo, titolo_file(lav.titolo))
        path = dest / NOME_RISULTATO
        path.write_text(testo, encoding="utf-8")
        return {"file": [path.name], "testo": testo, "markdown": True,
                "contenuto": md.descrivi(testo)}

    def _consegna_risultato(self, lav: Lavoro, ris: dict, dest: Path):
        """Il risultato di un lavoro (il testo o il documento) anche nella cartella Calliope dei
        Documenti del portatile (07/10), come i documenti di Calliope: con il satellite che
        riceve i file, RemoteDelivery e «Lo apro?»; senza, resta nella cartella del lavoro sul
        server e la frase lo dice. Con Calliope sul PC stesso (`consegna` None) il file è già
        nei suoi Documenti: si offre ad «aprilo». Dal thread dei lavori (aspetta la rete)."""
        files = [f for f in (ris.get("file") or []) if "/" not in str(f)]
        if not files:
            return
        p = dest / files[0]
        if not p.is_file():
            return
        ext = p.suffix.lower().lstrip(".")
        if self.consegna is None:
            if self._offri(lav, str(p), ext):
                ris["apribile"] = True
            return
        from ..documenti.formato import safe_filename
        from ..pc.remoto import per_pc
        nome_pc = getattr(self.consegna, "nome", "portatile")
        c = per_pc(getattr(self.consegna, "server", None))
        if c is None or not (getattr(c, "esecutore", None) or {}).get("file"):
            ris["dove"] = (f"sul server, nella cartella Lavori, perché il {nome_pc} non è "
                           f"collegato")
            return
        try:
            d = self.consegna.deliver(safe_filename(titolo_file(lav.titolo)), ext, p.read_bytes())
        except Exception as e:  # noqa: BLE001 — il file resta comunque nella cartella del lavoro
            self.log(f"[AGENTI] {lav.id}: consegna al {nome_pc} non riuscita: "
                     f"{type(e).__name__}: {e}")
            ris["dove"] = f"sul server, nella cartella Lavori: il {nome_pc} non l'ha ricevuto"
            return
        if not d.get("remoto"):
            # RemoteDelivery l'ha lasciato nella cartella di riserva sul server: qui c'è già
            # la cartella del lavoro, la copia non serve
            try:
                Path(str(d.get("rif") or "")).unlink()
            except OSError:
                pass
            perche = str(d.get("dove") or "").split("perché ", 1)[-1] or "non ha risposto"
            ris["dove"] = f"sul server, nella cartella Lavori, perché {perche}"
            return
        ris["consegnati_pc"] = [d["nome_file"]]
        ris["dove"] = self.consegna.where()
        self.log(f"[AGENTI] {lav.id}: risultato consegnato al {nome_pc} ({d['nome_file']})")
        if d.get("apri") and self._offri(lav, d["apri"], ext):
            ris["apribile"] = True

    def _offri(self, lav: Lavoro, percorso: str, ext: str) -> bool:
        """Il file appena consegnato diventa l'«ultima ricerca» di chi ha chiesto il lavoro:
        «aprilo» → pc_apri_file(1), come i documenti (documenti/servizio.Documenti._offer)."""
        if not self.pcs or lav.persona is None:
            return False
        ex = next(iter(self.pcs.values()))
        offri = getattr(ex, "offri_file", None)
        if offri is None:
            return False
        try:
            offri(lav.persona, {"nome": titolo_file(lav.titolo), "estensione": ext,
                                "percorso": percorso,
                                "modificato": time.strftime("%Y-%m-%dT%H:%M")})
            return True
        except Exception:  # noqa: BLE001 — aprire è un di più
            return False

    def _metadati(self, lav: Lavoro, dest: Path):
        r = lav.risultato
        meta = {"id": lav.id, "tipo": lav.tipo, "titolo": lav.titolo, "compito": lav.compito,
                "chi": lav.persona_nome, "persona": lav.persona, "stato": lav.stato,
                "esito": r.get("esito"),
                "riassunto": r.get("riassunto"), "domanda": r.get("domanda"),
                "domande": [list(x) for x in lav.domande] or None,
                "attesa_s": round(lav.attesa_s, 1) or None,
                "file_utente": (lav.input or {}).get("nome") or None,
                "consegnati": r.get("consegnati"),
                "test": r.get("test"), "file": r.get("file"), "motivo": r.get("motivo"),
                "modello": self.imp.modello, "passi": lav.passi, "token": lav.token,
                "token_letti": lav.prompt_token, "cedimenti": lav.cedimenti,
                # 05/10: il ragionamento a parte, e il contesto (finestra, picco dei token
                # letti in una passata, risultati messi nei file .calliope, diari)
                "token_ragionamento": lav.ragionamento,
                "contesto": dict(lav.uso_contesto) or None,
                "secondi": round((lav.fine or time.time()) - (lav.inizio or time.time())
                                 - lav.attesa_s, 1),
                "inizio": datetime.datetime.fromtimestamp(lav.inizio or time.time())
                .isoformat(timespec="seconds"),
                # Quando è finito (07/10): lavoro_stato lo dice anche dopo un riavvio
                "fine": (datetime.datetime.fromtimestamp(lav.fine).isoformat(timespec="seconds")
                         if lav.fine else None),
                # Il testo intero di una ricerca (07/10): per lavoro_risultato dopo un riavvio
                # (agenti/risultato.py), senza rileggere il file Word
                "testo": (str(r.get("testo"))[:100_000] if r.get("testo") else None)}
        try:
            from ..persistenza import scrivi_json      # atomico (03/10)
            scrivi_json(dest / "lavoro.json", meta, indent=1)
        except OSError:
            pass

    # ─────────────────────────── annuncio e scheda ───────────────────────────
    def frase_finale(self, lav: Lavoro) -> str:
        r = lav.risultato
        titolo = titolo_detto(lav.titolo)     # niente nomi di file né parentesi a voce
        riuscita = "riuscita" if self.female else "riuscito"
        dove = "nella cartella Lavori dei Documenti"
        if self.in_tappa(lav):
            return frase_tappa(lav, titolo)
        if lav.stato == "in_attesa":
            dom = lav.domanda
            if dom.lower().startswith("per "):     # «Per compilare «…» mi servono: …»
                return dom[:1].lower() + dom[1:]
            return f"per «{titolo}» ho una domanda: {dom[:1].lower() + dom[1:]}"
        if lav.stato == "scaduto":
            return (f"ho chiuso «{titolo}»: aspettavo da {_durata(r.get('attesa') or 0)} "
                    f"la risposta alla mia domanda. Quello che avevo già fatto è {dove}; se "
                    f"vuoi, chiedimelo di nuovo con i dati.")
        if lav.stato == "mancano_dati":
            return (f"per «{titolo}» mi mancano dei dati. "
                    + (r.get("domanda") or "Me li dici, così lo rifaccio?"))
        if lav.stato == "errore":
            if r.get("esito") == "limite":
                t = r.get("test") or {}
                n = t.get("eseguiti") or 0
                ko = (t.get("falliti") or 0) + (t.get("errori") or 0)
                test = ""
                if t and r.get("test_passano"):
                    test = f" I test che ha scritto passano, {n} su {n}."
                elif t:
                    test = f" Dei test che ha scritto ne passano {max(0, n - ko)} su {max(n, ko)}."
                limite = r.get('motivo', '').split(': ', 1)[-1]
                # Cosa ha fatto, in parole (06/10, L1 della DGX: «ha fatto tutte le 24 passate»
                # non diceva che non c'era nemmeno una riga dell'estensione)
                fatto = cosa_ha_fatto(lav, r)
                if fatto:
                    limite = f"{fatto}, e {limite}"
                return (f"ho fermato «{titolo}»: {limite}. "
                        f"Quello che ho fatto è {dove}.{test}")
            passo = f" {r['passo']}" if r.get("passo") else ""
            motivo = str(r.get("motivo") or "").rstrip(". ")
            if r.get("esito") == "impossibile":
                # Il riassunto dell'agente è una frase sua («Qui posso eseguire solo Python e
                # C#…»): dopo un punto, non dopo i due punti (04/10)
                return f"non sono {riuscita} a fare «{titolo}». {motivo}.{passo}"
            return f"non sono {riuscita} a fare «{titolo}»: {motivo}.{passo}"
        if r.get("esito") == "impossibile":
            return f"non sono {riuscita} a fare «{titolo}». {per_la_voce(r.get('riassunto'))}"
        if lav.tipo == "estensione" and r.get("estensione"):
            return r["estensione"]["frase"]
        if lav.tipo in ("codice", "estensione"):
            sintesi = per_la_voce(r.get("riassunto"))
            if lav.tipo == "codice":
                sintesi = senza_estensione(sintesi)
            t = r.get("test") or {}
            n = t.get("eseguiti") or 0
            ko = (t.get("falliti") or 0) + (t.get("errori") or 0)
            if not t:
                test = "Non ci sono test."
            elif r.get("test_passano"):
                test = f"I test passano, {n} su {n}." if n != 1 else "Il test passa."
            else:
                test = (f"Attenzione: {ko} test su {max(n, ko)} "
                        + ("non passa." if ko == 1 else "non passano."))
            files = len(r.get("file") or [])
            sintesi = sintesi[:1].lower() + sintesi[1:] if sintesi else ""
            if lav.input:
                return (f"ho finito «{titolo}»" + (f": {sintesi.rstrip('.')}." if sintesi
                                                        else ".")
                        + f" {test} {self._frase_consegna(r)}")
            demo = ""
            if r.get("dimostrazione"):
                demo = " " + r["dimostrazione"]
            elif r.get("dimostrazione_in_corso"):
                demo = " Lo sto eseguendo: guardalo sullo schermo."
            # Come rieseguirlo (06/10: «come la richiamo?» faceva inventare un comando a voce)
            ancora = " Per usarlo di nuovo dimmi «eseguilo», anche con dei valori."
            if getattr(lav, "non_estensione", False):
                ancora = (" Non è un'estensione di Calliope: è un programma a sé, e per usarlo "
                          "di nuovo dimmi «eseguilo», anche con dei valori.")
            if r.get("dimostrazione_esito") not in (None, "fatto"):
                # La dimostrazione si è fermata (06/10: «funziona correttamente» del riassunto
                # e subito dopo «si è fermato con un errore»): niente riassunto dell'agente, che
                # direbbe il contrario di quello che si è visto
                senza = ("con i valori d'esempio" if r.get("dimostrazione_con_dati")
                         else "senza dati")
                demo = demo.strip()
                return (f"ho finito «{titolo}». {test} {'Il file è' if files == 1 else 'I file sono'}"
                        f" {dove}. Eseguito {senza}, però: {demo[:1].lower() + demo[1:]}"
                        + (" Non è un'estensione di Calliope: è un programma a sé."
                           if getattr(lav, "non_estensione", False) else "")
                        + (" Forse vuole dei valori: dimmi «eseguilo con» e i valori." if not
                           r.get("dimostrazione_con_dati") else ""))
            return (f"ho finito «{titolo}»" + (f": {sintesi.rstrip('.')}." if sintesi
                                                    else ".")
                    + f" {test} {'Il file è' if files == 1 else 'I file sono'} {dove}.{demo}"
                    + ancora)
        cosa = r.get("contenuto")
        sintesi = per_la_voce(r.get("riassunto")) if lav.tipo in ("ricerca", "altro") else ""
        # «Ho finito», non «è pronto»: il titolo può essere femminile («relazione…»)
        coda = self._frase_consegna(r) if lav.input else f"Il file è {r.get('dove') or dove}."
        if not lav.input and r.get("apribile"):
            coda += " Lo apro?"
        return (f"ho finito «{titolo}»" + (f": {cosa}" if cosa else "")
                + (f". {sintesi.rstrip('.')}" if sintesi else "") + f". {coda}")

    @staticmethod
    def _frase_consegna(r: dict) -> str:
        """Dove sono i file nuovi di un lavoro su un file della persona (senza estensione:
        si legge male)."""
        nomi = [f"«{Path(n).stem}»" for n in (r.get("consegnati") or [])]
        if not nomi:
            return "Non ho cambiato niente: l'originale è com'era."
        elenco = nomi[0] if len(nomi) == 1 else ", ".join(nomi[:-1]) + " e " + nomi[-1]
        verbo = "è" if len(nomi) == 1 else "sono"
        chi = "Il file nuovo" if len(nomi) == 1 else "I file nuovi"
        return (f"{chi}, {elenco}, {verbo} {r.get('dove') or 'nella cartella Lavori dei Documenti'}"
                f"; l'originale non l'ho toccato.")

    def scheda(self, lav: Lavoro) -> dict | None:
        try:
            from ..schermi import schede
        except Exception:  # noqa: BLE001
            return None
        r = lav.risultato
        if r.get("estensione"):
            # La scheda di revisione: cosa fa, permessi, test, analisi del codice
            return schede.testo(f"Estensione da approvare: {r['estensione']['nome']}",
                                r["estensione"]["scheda_testo"], "personale")
        if r.get("documento") is not None and r.get("file"):
            try:
                return schede.documento(r["documento"], r.get("formato", "word"), r["file"][0],
                                        ident=f"lavoro-{lav.id}")
            except Exception:  # noqa: BLE001
                return None
        if r.get("markdown") and r.get("testo") and lav.stato == "fatto":
            # Il testo in Markdown (07/10): la scheda del documento con il lettore e «Scarica»,
            # con la chiave del lavoro (sostituisce quella in diretta)
            return schede.documento_markdown(
                titolo_file(lav.titolo), r["testo"], ident=lav.id,
                riassunto=per_la_voce(r.get("riassunto"), 400),
                nome_file=(r.get("file") or [NOME_RISULTATO])[0],
                cartella=Path(r.get("cartella") or "").name, stato=lav.stato)
        files = []
        dest = Path(r.get("cartella") or "")
        for name in (r.get("file") or [])[:8]:
            p = dest / name
            if p.suffix.lower() in (".py", ".txt", ".md", ".json", ".csv", ".html", ".css",
                                    ".js", ".ps1", ".sql", ".toml", ".yaml", ".yml", ".ini"):
                try:
                    files.append({"nome": name, "testo": p.read_text(encoding="utf-8",
                                                                      errors="replace")})
                except OSError:
                    pass
        return schede.lavoro(lav.titolo, lav.tipo, lav.stato, per_la_voce(r.get("riassunto"), 400)
                             or r.get("motivo") or "", files, r.get("test"),
                             Path(r.get("cartella") or "").name, r.get("domanda") or "",
                             ident=lav.id)

    def _scheda_finale(self, lav: Lavoro, sincrona: bool = True) -> bool:
        """La scheda finale di un lavoro seguito in diretta: sostituisce quella in corso e
        va in cima. False se il lavoro non era seguito."""
        if lav.osservatore is None:
            return False
        return self.avanzamento.finale(lav, sincrona=sincrona)

    def _annuncia(self, lav: Lavoro):
        text = self.frase_finale(lav)
        on_card = lav.on_scheda
        if self._scheda_finale(lav):
            pass
        elif on_card is not None and lav.stato in ("fatto", "errore", "mancano_dati",
                                                   "in_attesa", "scaduto"):
            card = self.scheda(lav)
            if card:
                try:
                    on_card(card)
                except Exception as e:  # noqa: BLE001 — lo schermo non ferma l'annuncio
                    self.log(f"[AGENTI] scheda non inviata: {e}")
        who = f"{lav.persona_nome}, " if lav.persona_nome else ""
        msg = who + text if who else text[0].upper() + text[1:]
        item = {"id": lav.id, "tipo": lav.tipo, "titolo": lav.titolo, "stato": lav.stato,
                "esito": lav.risultato.get("esito"), "messaggio": msg,
                "chi": lav.persona, "chi_nome": lav.persona_nome, "passi": lav.passi,
                "token": lav.token, "secondi": round((lav.fine or time.time())
                                                     - (lav.inizio or time.time()), 1),
                "cartella": lav.risultato.get("cartella"), "test": lav.risultato.get("test")}
        if self.in_tappa(lav):
            # Una tappa (08/10): «continuo?»; la modalità sviluppo la riscrive con la fase
            item["in_sospeso"] = {"domanda": "Continuo?", "tool": "lavoro_rispondi",
                                  "cosa": f"un altro giro di lavoro per «{lav.titolo}»",
                                  "argomenti": {"lavoro": lav.id, "risposta": "continua"}}
            item["tappa"] = True
        elif lav.stato == "in_attesa":
            # La domanda diventa un'azione in sospeso: la risposta nel turno dopo è per lei
            item["in_sospeso"] = self.offerta_risposta(lav)
            item["domanda"] = lav.domanda
            # Anche un modulo sullo schermo personale di chi l'ha chiesto, per scrivere la
            # risposta invece di dettarla (03/10, calliope/schermi/moduli.py: lo apre main)
            from ..schermi.moduli import campo
            item["modulo"] = {"chiave": f"lavoro:{lav.id}", "titolo": f"Domanda: {lav.titolo}",
                              "domanda": lav.domanda,
                              "campi": [campo("risposta", "La tua risposta", "testo_lungo")]}
        if lav.risultato.get("consegnati"):
            item["consegnati"] = lav.risultato["consegnati"]
        if lav.risultato.get("apribile") and not lav.input and lav.stato == "fatto":
            # «Lo apro?» (07/10): il risultato è l'«ultima ricerca» di chi l'ha chiesto
            from ..documenti.servizio import in_sospeso
            item["in_sospeso"] = in_sospeso("Lo apro?", f"il risultato «{titolo_detto(lav.titolo)}»")
        if (lav.risultato.get("estensione") or {}).get("in_sospeso"):
            # «Vuoi approvarla?» → estensione_gestisci approva (con la frase di sfida)
            item["in_sospeso"] = lav.risultato["estensione"]["in_sospeso"]
        if self.sviluppi is not None:
            # Un lavoro della modalità sviluppo (08/10): la fase cambia e l'annuncio dice dove
            # siamo (un'estensione si prova prima di approvarla: niente «Vuoi approvarla?»)
            try:
                item = self.sviluppi.lavoro_finito(lav, item) or item
            except Exception as e:  # noqa: BLE001 — l'annuncio parte comunque
                self.log(f"[AGENTI] sviluppo di {lav.id}: {type(e).__name__}: {e}")
        self.done.put(item)
        if self.on_done:
            self.on_done()

    # ─────────────────────────── riavvii (06/10, ripresa.py) ───────────────────────────
    def _salva_stato(self):
        """Lo stato dei lavori su disco (in_corso.json), a ogni cambio. Non durante la
        chiusura: i lavori fermati da close() restano «in corso» nel file, e al prossimo avvio
        diventano interrotti."""
        if self._chiuso or not hasattr(self, "_stato_lock"):
            return
        with self._lock:
            lavori = list(self.lavori)
        try:
            with self._stato_lock:
                ripresa.scrivi(self._stato_file, lavori)
        except OSError as e:
            self.log(f"[AGENTI] stato dei lavori non salvato: {e}")

    def _ripristina(self):
        """All'avvio: i lavori rimasti in coda o in corso diventano interrotti, quelli in
        attesa di una risposta tornano ad aspettarla (se la conversazione dell'agente c'è)."""
        righe = ripresa.leggi(self._stato_file, salta_pid=os.getpid())
        if not righe:
            return
        ora = time.time()
        for r in righe:
            m = re.fullmatch(r"L(\d+)", str(r["id"]))
            if m:
                self._n = max(self._n, int(m[1]))     # niente id doppi con quelli di prima
            if r["stato"] not in ripresa.VIVI + ("interrotto",):
                continue
            lav = ripresa.ricostruisci(r, Lavoro)
            if lav.stato == "interrotto" and ora - lav.vivo >= ripresa.TENUTI_S:
                continue
            self.lavori.append(lav)
            if r["stato"] in ripresa.VIVI:
                cosa = ("aspetta ancora la risposta" if lav.stato == "in_attesa"
                        else f"interrotto (era {r['stato'].replace('_', ' ')})")
                self.log(f"[AGENTI] {lav.id} «{lav.titolo}» di "
                         f"{lav.persona_nome or 'qualcuno'}: {cosa} dopo il riavvio")
                if lav.stato == "interrotto" and lav.cartella and Path(lav.cartella).is_dir():
                    self._metadati(lav, Path(lav.cartella))
        self._salva_stato()

    def _entro_annuncio(self, lav, ora: float | None = None) -> bool:
        limite = float(getattr(self.cfg, "agenti_interrotti_annuncio_h", 3.0) or 0) * 3600
        return ((ora or time.time()) - (getattr(lav, "vivo", None) or 0)) < limite

    def _interrotti_da_rifare(self, persona) -> list:
        """Gli interrotti di `persona` già annunciati con «Lo rifaccio?», ancora da decidere
        e recenti (`agenti_interrotti_annuncio_h`); il primo è quello dell'offerta."""
        with self._lock:
            out = [lv for lv in getattr(self, "lavori", ()) if lv.stato == "interrotto"
                   and lv.persona == persona
                   and persona is not None and getattr(lv, "annunciato", False)
                   and ripresa.riprendibile(lv) and self._entro_annuncio(lv)]
        return sorted(out, key=lambda lv: lv.creato)

    def offerta_ripresa(self, persona) -> dict | None:
        """L'azione in sospeso per rifare gli interrotti di `persona` (lavoro_stato)."""
        primo = self._interrotti_da_rifare(persona)
        return ripresa.offerta(primo[0]) if primo else None

    def _frase_interrotti(self, interrotti: list, persona) -> str:
        if not interrotti:
            return ""
        nomi = [f"«{lv.titolo}»" for lv in interrotti]
        if len(nomi) == 1:
            frase = f"{nomi[0][:1].upper()}{nomi[0][1:]} si è interrotto per un riavvio di Calliope"
        else:
            frase = (", ".join(nomi[:-1]) + " e " + nomi[-1]
                     + " si sono interrotti per un riavvio di Calliope")
        da_rifare = self._interrotti_da_rifare(persona)
        if da_rifare:
            return frase + (": lo rifaccio?" if len(da_rifare) == 1 else ": li rifaccio?")
        return frase + "."

    def _rifai_interrotti(self, persona):
        """Il «sì» all'annuncio: un lavoro nuovo per ogni interrotto di `persona` (stesso
        compito, stessa cartella, la sandbox di prima per il codice). Restituisce il primo, che
        il tool avvia; gli altri partono con lui (`insieme`)."""
        vecchi = self._interrotti_da_rifare(persona)
        nuovi = []
        for lv in vecchi:
            n = self.nuovo(lv.tipo, lv.compito, lv.persona, lv.persona_nome, lv.livello,
                           lv.formato, lv.modello, lv.vincoli, list(lv.dati))
            nuovi.append(ripresa.nota_ripresa(lv, n))
            with self._lock:
                lv.stato, lv.passo = "ripreso", f"rifatto come {n.id}"
            self.log(f"[AGENTI] {lv.id} interrotto: lo rifaccio come {n.id}")
        if not nuovi:
            return None
        nuovi[0].insieme = nuovi[1:]
        return nuovi[0]

    def _annuncia_ripresi(self):
        """Dal thread dei lavori, all'avvio: gli interrotti recenti alla persona che li aveva
        chiesti (un annuncio per persona, con «Lo rifaccio?»), e le domande di prima del
        riavvio di nuovo (l'azione in sospeso del Brain non c'è più). Una volta sola."""
        ora = time.time()
        with self._lock:
            interrotti = [lv for lv in self.lavori if lv.stato == "interrotto"
                          and not getattr(lv, "annunciato", False)]
            attese = [lv for lv in self.lavori if lv.stato == "in_attesa"
                      and getattr(lv, "ripristinato", False)]
        per_persona: dict = {}
        for lv in interrotti:
            lv.annunciato = True
            if not self._entro_annuncio(lv, ora):
                continue                     # più vecchi: solo nell'elenco di lavoro_stato
            if ripresa.riprendibile(lv) and lv.persona is not None:
                per_persona.setdefault(lv.persona, []).append(lv)
            else:
                self._metti_annuncio(lv, ripresa.frase(lv, titolo_detto(lv.titolo)))
        for gruppo in per_persona.values():
            primo = gruppo[0]
            off = ripresa.offerta(primo)
            if len(gruppo) == 1:
                testo = ripresa.frase(primo, titolo_detto(primo.titolo))
            else:
                nomi = [f"«{titolo_detto(lv.titolo)}»" for lv in gruppo]
                testo = (f"i lavori {', '.join(nomi[:-1])} e {nomi[-1]} si sono interrotti per "
                         f"un riavvio di Calliope. Li rifaccio?")
                off = {**off, "domanda": "Li rifaccio?",
                       "cosa": f"rifare i {len(gruppo)} lavori interrotti"}
            self._metti_annuncio(primo, testo, off)
        for lv in attese:
            lv.ripristinato = False
            if self._entro_annuncio(lv, ora):
                self._annuncia(lv)
        if interrotti:
            self._salva_stato()

    def _metti_annuncio(self, lav, testo: str, in_sospeso: dict | None = None):
        who = f"{lav.persona_nome}, " if lav.persona_nome else ""
        msg = who + testo if who else testo[0].upper() + testo[1:]
        item = {"id": lav.id, "tipo": lav.tipo, "titolo": lav.titolo, "stato": lav.stato,
                "esito": "interrotto", "messaggio": msg, "chi": lav.persona,
                "chi_nome": lav.persona_nome, "passi": 0, "token": 0, "secondi": 0,
                "cartella": lav.cartella, "test": None}
        if in_sospeso:
            item["in_sospeso"] = in_sospeso
        self.log(f"[AGENTI] {lav.id}: annuncio dell'interruzione a "
                 f"{lav.persona_nome or 'chi l’ha chiesto'}")
        self.done.put(item)
        if self.on_done:
            self.on_done()

    # ─────────────────────────── chiusura ───────────────────────────
    def close(self):
        self._chiuso = True
        # Prima di tutto: vLLM non resta in pausa (blocca ogni richiesta, anche di altri)
        self.arbitro.chiudi()
        self.avanzamento.chiudi()
        for lv in self.attivi():
            lv.annulla.set()
        self.cliente.interrompi()
        if self._sandbox is not None:
            self._sandbox.termina()
        self.esecuzioni.ferma(admin=True)
        self._coda.put(None)
        if self.tunnel is not None:
            self.tunnel.chiudi()
        self.cliente.close()
