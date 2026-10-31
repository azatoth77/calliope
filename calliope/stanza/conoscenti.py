"""
I conoscenti (14/10, decisione 0030; progetto docs/ricerche/2026-10-13-conversazione-di-stanza.md
§ 3.10 e passo 7): le voci sconosciute di adulti che tornano diventano «conoscenti» col nome
dedotto dalla conversazione, **solo dopo il sì di chi amministra** sullo schermo personale.

Interruttore `stanza_conoscenti` (di serie spento): spento, niente di questo modulo parte.

**Gruppi (in memoria, per installazione)**. Un segmento della stanza con una voce che nessun
profilo riconosce (né la famiglia né un conoscente) e almeno `speaker_min_voice_s` di voce entra
nel gruppo più somigliante (impronta CAM++ sopra `speaker_id_threshold`), o ne apre uno nuovo. I
gruppi non vanno mai su disco: si perdono al riavvio e dopo `GRUPPO_TENUTA_S` senza sentirli.

**Il nome dedotto** (regola `conoscente_nome`, principio 10: riconosce forme chiuse e brevi; il
suo solo effetto è una *proposta* a chi amministra, che decide; casi contrari nelle prove):

- *vocativo o saluto seguito dalla risposta di quella voce*: «Ciao Marco!», «Marco, tu che
  dici?», «… vero, Marco?» detti da una voce, e la prima riga dopo, di un'altra voce, entro
  `VOCATIVO_S`, è del gruppo X → un indizio (peso 1) per «X si chiama Marco»; se risponde la
  persona di casa che si chiama così, il vocativo era suo e non conta;
- *presentazione* detta dal gruppo X: «sono Marco», «mi chiamo Marco», «piacere, sono Marco»
  → un indizio (peso 2);
- *terza persona*: un nome detto in un altro modo («ho visto Marco ieri») non è un indizio per
  nessuno; detto dal gruppo X è un contrario per «X si chiama Marco» (peso −1: di sé non si
  parla in terza persona);
- *indizi concordi*: si propone quando un nome ha almeno `conoscenti_soglia` punti da almeno
  due righe diverse, il secondo nome sotto la metà, e il gruppo ha abbastanza voce
  (`conoscenti_min_voce_s`, tre segmenti) per un'impronta buona. Indizi discordi: niente.

**Omonimie** (aggiunta di chi amministra del 14/10): l'identità di un conoscente è la sua
impronta, il nome un'etichetta. Un nome uguale a quello di un familiare o di un conoscente già
salvato **non si esclude**: la proposta lo dice («un altro Marco, non Marco Rossi?») e un sì
crea sempre un profilo nuovo, mai una fusione. Cognome e nota libera («collega di Carlo»)
distinguono gli omonimi nelle righe della stanza, nella ricerca e in «dimentica Marco».

**Minori**: con uno stimatore dell'età della voce (`eta`, oggi non c'è) un gruppo che sembra di
un bambino non si propone mai; senza, la proposta lo dice («non so dire l'età dalla voce»).

**Proposta**: una scheda «conoscente» sugli schermi **personali** di chi amministra (mai a voce,
mai sugli schermi di stanza), con un pezzo breve di trascrizione e Sì / No / un nome diverso,
più cognome e nota. Senza il sì niente va su disco. Un No non ripropone la stessa voce finché
Calliope gira (dopo un riavvio niente se ne ricorda: per non salvare l'impronta di chi ha detto
no).

**Il conoscente** (`conoscenti.json` accanto alla configurazione, scritto in modo atomico, senza
copia `.bak`): id, nome, cognome, nota, impronta, quando è stato salvato e l'ultima volta che si
è sentito. Livello **ospite** sempre: non è nel registro delle voci della famiglia
(speakers.json), quindi nessun percorso di riconoscimento dei comandi lo vede; lo nominano le
righe della stanza e, dal 14/10 sera, i dati del turno quando parla a Calliope (un'etichetta,
`SpeakerContext.conoscente`: chi parla resta None, ciclo._conoscente_turno). Le sue righe vanno su disco con la tenuta della stanza (60 giorni) e si
cercano come quelle della famiglia (chi c'era). **Conservazione** (14/10 sera, decisione di
Dario): come un adulto della famiglia, non come un ospite: nel registro dei turni il suo id,
il nome e le parole, la sua conversazione (una per conoscente, `persona:<id>`) nell'archivio su
disco per `turn_log_days`, gli eventi; la voce solo con il consenso, che oggi non può dare
(calliope/conserva.py). I permessi restano da ospite. Si cancella dopo
`conoscenti_scadenza_giorni` senza sentirlo, con «dimentica Marco» (tool `conoscenti`, solo
chi amministra) e con `calliope conserva --svuota`; con lui le sue righe su disco, e (con i
`su_tolto` della conservazione) i suoi turni, eventi e conversazioni.

**Promozione** (aggiunta del 14/10): solo chi amministra, a voce riconosciuta e con il sì alla
domanda (tool `conoscente_livello`, pericoloso con la sfida), un conoscente diventa familiare:
stesso id, impronta e nome; il profilo entra in speakers.json con i permessi e le regole dei
familiari; se è un minore servono la data di nascita e i tutori. Al contrario un familiare (non
chi amministra, non un minore) torna conoscente. Turni, eventi e conversazioni seguono l'id:
promosso restano suoi da familiare, tornato conoscente restano (la voce registrata no: un
conoscente non ha il consenso, e la rotazione la toglie).

Misure senza parole né nomi (stanza/misure.py, tipo «conoscenti»).
"""

from __future__ import annotations

import datetime
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

from .. import impronte_satellite as _imp_sat

GIORNO_S = 86400.0
GRUPPI_MAX = 60
GRUPPO_EMB_MAX = 30
GRUPPO_TENUTA_S = 24 * 3600.0
GRUPPO_MIN_SEGMENTI = 3
VOCATIVO_S = 15.0
RIFIUTATI_MAX = 200
ESTRATTO_RIGA = 140
SENTITO_SALVA_S = 3600.0
SINCRONIZZA_S = 2.0
FORMATO = 1

PESO_VOCATIVO, PESO_PRESENTAZIONE, PESO_TERZA = 1, 2, -1

# ── la regola sul testo `conoscente_nome` ──
_MAIUSC = "A-ZÀÈÉÌÒÙ"
_MINUSC = "a-zàèéìòù"
_NOME = rf"([{_MAIUSC}][{_MINUSC}]{{2,}}(?:-[{_MAIUSC}][{_MINUSC}]+)?)"
_SALUTI = (r"ciao|salve|buongiorno|buonasera|buonanotte|ehi|ehil[aà]|bentornat[oa]|"
           r"ben\s?arrivat[oa]|benvenut[oa]|grazie|arrivederci|piacere|addio")
RE_SALUTO = re.compile(rf"(?i:\b(?:{_SALUTI}))\s*[,!]?\s+{_NOME}\b")
RE_VOC_INIZIO = re.compile(rf"^[\s\"«]*{_NOME}\s*[,!?]")
RE_VOC_FINE = re.compile(rf",\s*{_NOME}\s*[.!?…]*[\s\"»]*$")
RE_VOC_DENTRO = re.compile(rf",\s*{_NOME}\s*,")
RE_PRESENTA = re.compile(
    rf"(?:(?:^|[,.!?;:]\s*|(?i:\b(?:ciao|salve|piacere|allora)\W+))(?i:(?:io\s+)?sono)"
    rf"|(?i:\bmi\s+chiamo))\s+{_NOME}(?!\s+e\s)")
RE_PAROLA = re.compile(_NOME)

# Parole con la maiuscola che non sono nomi di persona (inizio di frase, saluti, titoli)
STOP = frozenset("""
ciao salve buongiorno buonasera buonanotte grazie prego piacere scusa scusami senti sentite
guarda guardate allora dai ecco bene benissimo va vabbe vabbè okay ok certo forse anche pero
però quindi comunque infatti insomma aspetta aspettate vieni venite andiamo dimmi dimmelo
dica sono sei siamo siete era erano sara sarà che chi come cosa dove quando quanto quale
perche perché il lo la le gli un una uno questo questa quello quella questi quelle io tu
lui lei noi voi loro mio mia tuo tua suo sua nostro nostra adesso ora oggi domani ieri
stasera stamattina dopo prima sempre mai mamma papa papà babbo nonno nonna zio zia amore
tesoro caro cara signora signore signor signorina dottore dottoressa professore professoressa
calliope buon benvenuto benvenuta bentornato bentornata bravo brava bravi brave basta
eh ah oh uh mah boh beh ehi wow ehm hmm mhm sì si no non niente tutto tutti tutte nessuno
lunedi lunedì martedi martedì mercoledi mercoledì giovedi giovedì venerdi venerdì sabato
domenica gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre
dicembre natale pasqua italia roma milano napoli torino firenze venezia bologna genova
cioe cioè tipo praticamente davvero veramente esatto appunto magari speriamo andate andiamo
facciamo fate fai fammi prendi metti dammi dateci ditemi ascolta ascoltate attento attenta
""".split())


def _chiave(nome: str) -> str:
    t = unicodedata.normalize("NFKD", str(nome or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", t).split())


def _parole(testo: str) -> list[str]:
    return _chiave(testo).split()


@dataclass
class Nomi:
    """I nomi di persona di una riga, per forma."""
    presentazioni: list = field(default_factory=list)
    vocativi: list = field(default_factory=list)
    terza: list = field(default_factory=list)


def nomi_in(testo: str, esclusi=()) -> Nomi:
    """La regola `conoscente_nome` su una riga: le presentazioni («sono Marco»), i vocativi e
    i saluti («Ciao Marco!», «Marco, tu che dici?», «vero, Marco?») e gli altri nomi (terza
    persona). Solo parole con la maiuscola che non sono in STOP né in `esclusi` (i nomi di
    Calliope, delle stanze)."""
    t = " ".join(str(testo or "").split())
    out = Nomi()
    if not t:
        return out
    escl = {_chiave(e) for e in esclusi or () if e} | STOP

    def buono(n: str) -> bool:
        k = _chiave(n)
        return bool(k) and len(k) >= 3 and k not in escl and not any(
            w in escl for w in k.split())
    usati: set = set()
    for m in RE_PRESENTA.finditer(t):
        n = m.group(1)
        if buono(n) and n not in out.presentazioni:
            out.presentazioni.append(n)
            usati.add(m.start(1))
    for rx in (RE_SALUTO, RE_VOC_INIZIO, RE_VOC_FINE, RE_VOC_DENTRO):
        for m in rx.finditer(t):
            n = m.group(1)
            if m.start(1) in usati or not buono(n):
                continue
            usati.add(m.start(1))
            if n not in out.vocativi and n not in out.presentazioni:
                out.vocativi.append(n)
    for m in RE_PAROLA.finditer(t):
        n = m.group(1)
        if m.start(1) in usati or not buono(n):
            continue
        # Una maiuscola a inizio di frase non è per forza un nome: solo se è un nome già
        # noto come vocativo o presentazione in questa riga (allora è già usato) o lontano
        # dall'inizio della frase
        prima = t[:m.start(1)].rstrip()
        if not prima or prima[-1] in ".!?…:;\"«":
            continue
        if n not in out.terza and n not in out.vocativi and n not in out.presentazioni:
            out.terza.append(n)
    return out


# ── stato ──
def accesa(cfg) -> bool:
    return bool(getattr(cfg, "stanza_conoscenti", False))


def percorso(cfg) -> Path:
    p = getattr(cfg, "conoscenti_file", None) or "conoscenti.json"
    p = Path(os.path.expanduser(str(p)))
    if not p.is_absolute():
        p = Path(getattr(cfg, "config_dir", None) or ".") / p
    return p


def svuota_file(cfg) -> int:
    """`calliope conserva --svuota` da un altro processo: il file dei conoscenti cancellato
    (quanti ce n'erano). Calliope, se gira, se ne accorge alla lettura dopo (`_sincronizza`)."""
    p = percorso(cfg)
    if not p.exists():
        return 0
    try:
        n = len(json.loads(p.read_text(encoding="utf-8")).get("conoscenti") or [])
    except Exception:  # noqa: BLE001 — un file rovinato si cancella lo stesso
        n = 0
    p.unlink(missing_ok=True)
    return n


def trova_in(elenco, chi: str) -> list:
    """I conoscenti di `elenco` che rispondono a `chi` (Conoscenti.trova; anche per la
    conservazione da terminale, dal file)."""
    ws = [w for w in _parole(chi) if w not in ("il", "la", "lo", "di", "del", "della")]
    if not ws:
        return []
    out = []
    for c in elenco:
        tutte = set(_parole(f"{c.nome} {c.cognome} {c.nota}"))
        if _chiave(c.nome) == ws[0] and all(w in tutte for w in ws[1:]):
            out.append(c)
    return out


def firma_file(cfg):
    """(mtime, dimensione) del file dei conoscenti, o None se non c'è: per rileggerlo solo
    quando cambia (conserva.Conservazione.conoscente)."""
    try:
        st = percorso(cfg).stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def leggi_file(cfg) -> dict:
    """I conoscenti del file in sola lettura (id → Conoscente), senza aprire i conoscenti:
    per la conservazione da terminale e con i conoscenti spenti (14/10 sera). File mancante o
    rovinato: nessuno."""
    p = percorso(cfg)
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return {str(x["id"]): Conoscente.da_dict(x) for x in d.get("conoscenti") or []
                if isinstance(x, dict) and x.get("id")}
    except Exception:  # noqa: BLE001 — rovinato: nessuno
        return {}


def conta_file(cfg) -> int | None:
    p = percorso(cfg)
    if not p.exists():
        return None if not accesa(cfg) else 0
    try:
        return len(json.loads(p.read_text(encoding="utf-8")).get("conoscenti") or [])
    except Exception:  # noqa: BLE001
        return None


@dataclass
class Conoscente:
    id: str
    nome: str
    cognome: str = ""
    nota: str = ""
    impronta: np.ndarray | None = None
    modello: str | None = None
    creato: str = ""                 # AAAA-MM-GG
    ultimo: float = 0.0              # epoch dell'ultima volta sentito
    confermato_da: str | None = None
    tipo: str = "conoscente"         # per conserva.categoria: mai un familiare
    # Impronte per satellite (15/10, calliope/impronte_satellite.py): come per la famiglia,
    # imparate solo dalle frasi sicure; seguono la persona (promozione e ritorno)
    impronte_satellite: dict = field(default_factory=dict)

    @property
    def name(self) -> str:           # come UserProfile, per chi stampa un nome
        return self.nome_pieno()

    def nome_pieno(self) -> str:
        return " ".join(x for x in (self.nome, self.cognome) if x).strip()

    def descrizione(self) -> str:
        """«Marco Rossi, collega di Carlo»: come lo si dice per distinguerlo dagli omonimi."""
        return self.nome_pieno() + (f", {self.nota}" if self.nota else "")

    def a_dict(self) -> dict:
        return {"id": self.id, "nome": self.nome, "cognome": self.cognome, "nota": self.nota,
                "impronta": (self.impronta.tolist() if self.impronta is not None else None),
                "modello": self.modello, "creato": self.creato,
                "ultimo": round(float(self.ultimo or 0), 1),
                "confermato_da": self.confermato_da,
                **({"impronte_satellite": _imp_sat.scrivi(self.impronte_satellite)}
                   if _imp_sat.scrivi(self.impronte_satellite) else {})}

    @classmethod
    def da_dict(cls, d: dict) -> "Conoscente":
        imp = d.get("impronta")
        return cls(id=str(d["id"]), nome=str(d.get("nome") or ""),
                   cognome=str(d.get("cognome") or ""), nota=str(d.get("nota") or ""),
                   impronta=(np.asarray(imp, dtype=np.float32) if imp else None),
                   modello=d.get("modello"), creato=str(d.get("creato") or ""),
                   ultimo=float(d.get("ultimo") or 0.0),
                   confermato_da=d.get("confermato_da"),
                   impronte_satellite=_imp_sat.leggi(d.get("impronte_satellite")))


@dataclass
class Indizio:
    nome: str
    forma: str                       # vocativo, presentazione, terza
    peso: int
    t: float
    sat: object
    riga: object                     # (sat, seq) della riga che lo dà: una volta sola
    estratto: list = field(default_factory=list)


@dataclass
class Gruppo:
    n: int
    centro: np.ndarray
    embs: list = field(default_factory=list)
    voce_s: float = 0.0
    segmenti: int = 0
    primo: float = 0.0
    ultimo: float = 0.0
    indizi: list = field(default_factory=list)
    stato: str = "aperto"            # aperto, proposto, rifiutato, minore, salvato
    proposta: str | None = None
    eta: dict = field(default_factory=dict)      # «bambino»/«adulto» → voti
    discordi_contati: bool = False

    def aggiungi(self, emb: np.ndarray, voce_s: float, t: float):
        self.embs.append(emb)
        del self.embs[:-GRUPPO_EMB_MAX]
        c = np.mean(np.stack(self.embs), axis=0)
        self.centro = (c / (np.linalg.norm(c) + 1e-10)).astype(np.float32)
        self.voce_s += float(voce_s or 0)
        self.segmenti += 1
        self.ultimo = t


@dataclass
class Proposta:
    id: str
    gruppo: int
    nome: str
    estratto: list
    avvisi: list
    creata: float
    mandata: bool = False
    esito: str | None = None         # salvato, rifiutato, scaduta


def _normalizza(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    return (v / (np.linalg.norm(v) + 1e-10)).astype(np.float32)


class Conoscenti:
    """I conoscenti di un'installazione: il file, i gruppi in memoria, le proposte."""

    def __init__(self, cfg, path=None, registry=None, misure=None, log=print, eta=None):
        self.cfg = cfg
        self.path = Path(path) if path is not None else percorso(cfg)
        self.registry = registry
        self.misure = misure
        self.log = log
        # Lo stimatore dell'età della voce: f(impronta) → «bambino», «adulto» o None. Oggi non
        # c'è un modello: None, e la proposta lo dice
        self.eta = eta
        self.schermi = None           # hub degli schermi (le proposte a chi amministra)
        self.esclusi: set = set()     # nomi che non sono persone (Calliope, le stanze)
        self._lock = threading.RLock()
        self._conoscenti: dict[str, Conoscente] = {}
        self._gruppi: dict[int, Gruppo] = {}
        self._n = 0
        self._rifiutati: list[np.ndarray] = []
        self._proposte: dict[str, Proposta] = {}
        self._vocativi: dict = {}     # sat → [(autore, nomi, fine, testo, nome autore)]
        self._stamp = None
        self._sincro = 0.0
        self._salvato_sentito = 0.0
        self._ultima_rotazione = 0.0
        # Chi vuole sapere di un conoscente tolto (dimenticato, scaduto, svuotato): la stanza
        # (righe in memoria e su disco). f(id) — e di un cambio di livello: f(vecchio, nuovo)
        self.su_tolto: list = []
        self.su_livello: list = []
        # Le domande aperte del tool (promozione, «dimentica»): chiave → turno
        self.domande: dict = {}
        self.carica()

    # ── soglie ──
    def _thr(self) -> float:
        return float(getattr(self.cfg, "speaker_id_threshold", 0.48))

    def _margine(self) -> float:
        return float(getattr(self.cfg, "speaker_id_margine", 0.08) or 0.0)

    @property
    def giorni(self) -> int:
        return int(getattr(self.cfg, "conoscenti_scadenza_giorni", 180) or 180)

    def _modello(self) -> str | None:
        emb = getattr(self.registry, "embedder", None)
        return getattr(emb, "model_name", None)

    # ── il file ──
    def carica(self):
        with self._lock:
            self._conoscenti = {}
            self._stamp = self._firma()
            if not self.path.exists():
                return
            try:
                d = json.loads(self.path.read_text(encoding="utf-8"))
                for x in d.get("conoscenti") or []:
                    c = Conoscente.da_dict(x)
                    self._conoscenti[c.id] = c
            except Exception as e:  # noqa: BLE001 — un file rovinato: nessuno, e lo dice
                self.log(f"   [CONOSCENTI] {self.path.name} non si legge "
                         f"({type(e).__name__}): nessun conoscente")
                self._conoscenti = {}

    def _firma(self):
        try:
            st = self.path.stat()
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _sincronizza(self, sempre: bool = False):
        """Il file cambiato da un altro processo (`calliope conserva --svuota`): si rilegge; un
        file sparito vuol dire nessun conoscente."""
        ora = time.monotonic()
        if not sempre and ora - self._sincro < SINCRONIZZA_S:
            return
        self._sincro = ora
        f = self._firma()
        if f != self._stamp:
            prima = set(self._conoscenti)
            self.carica()
            for cid in prima - set(self._conoscenti):
                self._avvisa_tolto(cid)

    def salva(self):
        from ..persistenza import scrivi_json
        with self._lock:
            dati = {"formato": FORMATO,
                    "conoscenti": [c.a_dict() for c in self._conoscenti.values()]}
            if not self._conoscenti and not self.path.exists():
                self._stamp = None
                return
            # Senza copia .bak: un conoscente dimenticato non deve restare in una copia
            scrivi_json(self.path, dati, copia=False)
            self._stamp = self._firma()

    # ── i conoscenti ──
    def elenco(self) -> list[Conoscente]:
        with self._lock:
            self._sincronizza()
            return sorted(self._conoscenti.values(), key=lambda c: (_chiave(c.nome_pieno()),
                                                                    c.creato))

    def per_id(self, cid) -> Conoscente | None:
        if not cid:
            return None
        cid = str(cid)
        if cid.startswith("conoscente:"):
            cid = cid[len("conoscente:"):]
        with self._lock:
            self._sincronizza()
            return self._conoscenti.get(cid)

    def esiste(self, cid) -> bool:
        return self.per_id(cid) is not None

    def trova(self, chi: str) -> list[Conoscente]:
        """I conoscenti che rispondono a «Marco», «Marco Rossi», «Marco collega di Carlo»: tutte
        le parole dette stanno nel nome, nel cognome o nella nota. Più di uno: omonimi."""
        return trova_in(self.elenco(), chi)

    def classifica(self, emb, chiavi=None) -> list[tuple[float, Conoscente]]:
        """[(punteggio, conoscente)] dal più somigliante; con `chiavi` (15/10, impronte per
        satellite) il massimo fra l'impronta salvata e quella del satellite."""
        if emb is None:
            return []
        with self._lock:
            self._sincronizza()
            mod = self._modello()
            cl = [((_imp_sat.punteggio(emb, c.impronta, c.impronte_satellite, chiavi)[0]
                    if chiavi else float(np.dot(emb, c.impronta))), c)
                  for c in self._conoscenti.values()
                  if c.impronta is not None and (mod is None or c.modello in (None, mod))]
        return sorted(cl, key=lambda x: -x[0])

    def riconosci(self, emb, sim_famiglia: float | None = None, t: float | None = None,
                  chiavi=None, segna: bool = True) -> Conoscente | None:
        """Il conoscente di questa impronta: sopra soglia, con il margine dal secondo e dal
        profilo della famiglia più vicino. Lo segna «sentito» (se `segna`). Con `chiavi` anche
        le impronte del satellite (`speaker_impronte_satellite: attivo`)."""
        cl = self.classifica(emb, chiavi)
        if not cl:
            return None
        sim, c = cl[0]
        thr, mar = self._thr(), self._margine()
        if sim < thr:
            return None
        if len(cl) > 1 and sim - cl[1][0] < mar:
            return None
        if sim_famiglia is not None and sim - float(sim_famiglia) < mar:
            return None
        if segna:
            self.sentito(c.id, t)
        return c

    def impara_satellite(self, cid, emb, chiavi, sim_famiglia: float | None = None,
                         voce_s: float = 0.0, chiavi_decisione=None) -> list[str]:
        """Una frase di un conoscente riconosciuto entra nelle sue impronte del satellite, solo
        se è sicura (impronte_satellite.sicura: sopra `speaker_adapt_threshold`, margine
        `speaker_impronte_margine` sul secondo conoscente e sulla famiglia, voce lunga). Il
        ciclo lo chiama fuori dalla compagnia. `chiavi_decisione`: le chiavi con cui si è
        deciso (None in ombra: l'impronta salvata soltanto)."""
        cl = self.classifica(emb, chiavi_decisione)
        if not cl or cl[0][1].id != str(cid):
            return []
        sim, c = cl[0]
        altri = [x[0] for x in cl[1:2]] + ([float(sim_famiglia)] if sim_famiglia is not None
                                           else [])
        sim2 = max(altri) if altri else None
        if not _imp_sat.sicura(self.cfg, "voce", sim, sim2, voce_s):
            return []
        with self._lock:
            cambiate = _imp_sat.impara(c.impronte_satellite, emb, chiavi, c.impronta, self.cfg)
            if cambiate:
                self.salva()
        return cambiate

    def svuota_impronte_satellite(self, cid=None) -> int:
        """Via le impronte per satellite di un conoscente (o di tutti); l'impronta salvata
        resta."""
        n = 0
        with self._lock:
            self._sincronizza(sempre=True)
            for c in self._conoscenti.values():
                if cid is not None and c.id != str(cid):
                    continue
                n += len(c.impronte_satellite)
                c.impronte_satellite = {}
            if n:
                self.salva()
        return n

    def sentito(self, cid, t: float | None = None):
        with self._lock:
            c = self._conoscenti.get(str(cid))
            if c is None:
                return
            c.ultimo = time.time() if t is None else float(t)
            if time.monotonic() - self._salvato_sentito >= SENTITO_SALVA_S:
                self._salvato_sentito = time.monotonic()
                self.salva()

    def _avvisa_tolto(self, cid):
        for f in list(self.su_tolto):
            try:
                f(cid)
            except Exception as e:  # noqa: BLE001
                self.log(f"   [CONOSCENTI] pulizia non riuscita: {type(e).__name__}")

    def dimentica(self, cid) -> bool:
        """Via impronta e profilo, e (con i `su_tolto`) le sue righe su disco."""
        with self._lock:
            self._sincronizza(sempre=True)
            c = self._conoscenti.pop(str(cid), None)
            if c is None:
                return False
            self.salva()
        self._avvisa_tolto(c.id)
        self._misura("dimenticato")
        self.log("   [CONOSCENTI] un conoscente dimenticato")
        return True

    def svuota(self) -> int:
        """Tutti (`calliope conserva --svuota`, dati_conservati svuota): profili, impronte, le
        loro righe su disco; e in memoria gruppi e proposte."""
        with self._lock:
            ids = list(self._conoscenti)
            self._conoscenti = {}
            self._gruppi.clear()
            self._proposte.clear()
            self._vocativi.clear()
            self.path.unlink(missing_ok=True)
            self._stamp = None
        for cid in ids:
            self._avvisa_tolto(cid)
        if ids:
            self._misura("svuotati", n=len(ids))
        return len(ids)

    def ruota(self, ora: float | None = None) -> int:
        """Via i conoscenti non sentiti da `conoscenti_scadenza_giorni` (all'avvio della stanza
        e una volta al giorno), con le loro righe."""
        ora = time.time() if ora is None else float(ora)
        self._ultima_rotazione = time.time()
        limite = ora - self.giorni * GIORNO_S
        with self._lock:
            self._sincronizza(sempre=True)
            vecchi = [c.id for c in self._conoscenti.values()
                      if float(c.ultimo or 0) < limite]
            for cid in vecchi:
                self._conoscenti.pop(cid, None)
            if vecchi:
                self.salva()
        for cid in vecchi:
            self._avvisa_tolto(cid)
            self._misura("scaduto")
        if vecchi:
            self.log(f"   [CONOSCENTI] {len(vecchi)} conoscenti non sentiti da {self.giorni} "
                     f"giorni: dimenticati")
        return len(vecchi)

    # ── i gruppi delle voci sconosciute ──
    def assegna(self, emb, voce_s: float, t: float | None = None) -> int | None:
        """Il gruppo della voce sconosciuta di un segmento (nuovo se non somiglia a nessuno)."""
        if emb is None:
            return None
        t = time.time() if t is None else float(t)
        emb = _normalizza(emb)
        thr = self._thr()
        with self._lock:
            self._pota_gruppi(t)
            best, sim = None, -1.0
            for g in self._gruppi.values():
                s = float(np.dot(emb, g.centro))
                if s > sim:
                    best, sim = g, s
            if best is None or sim < thr:
                self._n += 1
                best = Gruppo(self._n, emb.copy(), primo=t, ultimo=t)
                self._gruppi[best.n] = best
                if any(float(np.dot(emb, r)) >= thr for r in self._rifiutati):
                    best.stato = "rifiutato"      # la voce a cui chi amministra ha detto no
                self._misura("gruppo_nuovo")
                while len(self._gruppi) > GRUPPI_MAX:
                    vecchio = min(self._gruppi.values(), key=lambda g: g.ultimo)
                    self._togli_gruppo(vecchio.n)
            best.aggiungi(emb, voce_s, t)
            if self.eta is not None and best.stato == "aperto":
                try:
                    e = self.eta(emb)
                except Exception:  # noqa: BLE001
                    e = None
                if e in ("bambino", "adulto"):
                    best.eta[e] = best.eta.get(e, 0) + 1
                    if (best.eta.get("bambino", 0) >= 2
                            and best.eta["bambino"] > best.eta.get("adulto", 0)):
                        best.stato = "minore"
                        self._misura("minore")
            return best.n

    def _togli_gruppo(self, n):
        g = self._gruppi.pop(n, None)
        if g is not None and g.proposta:
            p = self._proposte.get(g.proposta)
            if p is not None and p.esito is None:
                p.esito = "scaduta"

    def _pota_gruppi(self, ora: float):
        for n in [n for n, g in self._gruppi.items() if ora - g.ultimo > GRUPPO_TENUTA_S]:
            self._togli_gruppo(n)

    def gruppo(self, n) -> Gruppo | None:
        with self._lock:
            return self._gruppi.get(n)

    # ── la deduzione del nome ──
    @staticmethod
    def _autore(riga: dict) -> str:
        if riga.get("gruppo") is not None:
            return f"gruppo:{riga['gruppo']}"
        return str(riga.get("chi") or "ignoto")

    def osserva(self, sat, riga: dict):
        """Una riga della stanza (anche di un turno): gli indizi per i gruppi."""
        testo = str(riga.get("testo") or "")
        autore = self._autore(riga)
        ini = float(riga.get("inizio") or riga.get("t") or time.time())
        fin = float(riga.get("fine") or ini)
        g_n = riga.get("gruppo")
        chiave = (sat, riga.get("seq"))
        nomi = nomi_in(testo, self.esclusi)
        toccati = set()
        with self._lock:
            # 1. Questa riga risponde a un vocativo detto da un'altra voce poco prima?
            pend = [v for v in self._vocativi.get(sat, []) if ini - v["fine"] <= VOCATIVO_S]
            resto = []
            for v in pend:
                if v["autore"] == autore:
                    resto.append(v)            # la stessa voce che continua: aspetta ancora
                    continue
                # La prima riga di un'altra voce è la risposta (consuma il vocativo)
                if g_n is not None and len(v["nomi"]) == 1:
                    g = self._gruppi.get(g_n)
                    if g is not None:
                        estr = [f"{v['chi']}: {_corto(v['testo'])}",
                                f"voce nuova: {_corto(testo)}"]
                        if self._indizio(g, Indizio(v["nomi"][0], "vocativo", PESO_VOCATIVO,
                                                    ini, sat, (v["riga"], chiave), estr)):
                            toccati.add(g_n)
            self._vocativi[sat] = resto
            # 2. Presentazioni e terza persona detti dal gruppo stesso
            if g_n is not None and g_n in self._gruppi:
                g = self._gruppi[g_n]
                for n in nomi.presentazioni:
                    if self._indizio(g, Indizio(n, "presentazione", PESO_PRESENTAZIONE, ini,
                                                sat, chiave, [f"voce nuova: {_corto(testo)}"])):
                        toccati.add(g_n)
                for n in nomi.terza:
                    if self._indizio(g, Indizio(n, "terza", PESO_TERZA, ini, sat, chiave, [])):
                        toccati.add(g_n)
            # 3. I vocativi di questa riga aspettano la risposta
            if nomi.vocativi:
                self._vocativi.setdefault(sat, []).append(
                    {"autore": autore, "nomi": list(nomi.vocativi), "fine": fin,
                     "testo": testo, "riga": chiave, "chi": _chi_detto(riga)})
            del self._vocativi.get(sat, [])[:-20]
        for n in toccati:
            self.valuta(n)

    def _indizio(self, g: Gruppo, i: Indizio) -> bool:
        if any(x.riga == i.riga and x.forma == i.forma and _chiave(x.nome) == _chiave(i.nome)
               for x in g.indizi):
            return False
        g.indizi.append(i)
        del g.indizi[:-50]
        return True

    def punteggi(self, g: Gruppo) -> list[tuple[str, int, int]]:
        """[(nome, punti, righe con indizi a favore)] dal più forte."""
        pt: dict = {}
        for i in g.indizi:
            k = _chiave(i.nome)
            p = pt.setdefault(k, [i.nome, 0, set()])
            p[1] += i.peso
            if i.peso > 0:
                p[2].add(i.riga)
        return sorted(((v[0], v[1], len(v[2])) for v in pt.values()), key=lambda x: -x[1])

    def valuta(self, n) -> Proposta | None:
        """Se gli indizi del gruppo bastano, la proposta a chi amministra."""
        soglia = int(getattr(self.cfg, "conoscenti_soglia", 3) or 3)
        min_voce = float(getattr(self.cfg, "conoscenti_min_voce_s", 6.0) or 0.0)
        with self._lock:
            g = self._gruppi.get(n)
            if g is None or g.stato != "aperto":
                return None
            if g.segmenti < GRUPPO_MIN_SEGMENTI or g.voce_s < min_voce:
                return None
            pt = self.punteggi(g)
            if not pt:
                return None
            nome, punti, righe = pt[0]
            if punti < soglia or righe < 2:
                return None
            secondo = pt[1][1] if len(pt) > 1 else 0
            if secondo > 0 and secondo * 2 >= punti:
                if not g.discordi_contati:
                    g.discordi_contati = True
                    self._misura("discordi")
                return None
            p = Proposta(uuid.uuid4().hex[:12], g.n, nome, self._estratto(g, nome),
                         self._avvisi(nome, g), time.time())
            self._proposte[p.id] = p
            g.stato, g.proposta = "proposto", p.id
        self._misura("proposta", omonimo_famiglia=any(a["tipo"] == "famiglia" for a in p.avvisi),
                     omonimo_conoscente=any(a["tipo"] == "conoscente" for a in p.avvisi),
                     eta=self.eta is not None)
        self.log("   [CONOSCENTI] una voce nuova da proporre a chi amministra")
        self.manda(p)
        return p

    def _estratto(self, g: Gruppo, nome: str) -> list[str]:
        k = _chiave(nome)
        buoni = [i for i in g.indizi if _chiave(i.nome) == k and i.peso > 0 and i.estratto]
        buoni.sort(key=lambda i: (-i.peso, -i.t))
        return list(buoni[0].estratto) if buoni else []

    def _avvisi(self, nome: str, g: Gruppo | None = None) -> list[dict]:
        k = _chiave(nome)
        out = []
        fam = [str(getattr(p, "name", "")) for p in list(getattr(self.registry, "users",
                                                                    {}).values())
               if _chiave(str(getattr(p, "name", ""))).split()[:1] == [k]]
        if fam:
            out.append({"tipo": "famiglia", "testo": (
                f"In famiglia c'è già {fam[0]}: questa è un'altra voce. Se la salvi è un altro "
                f"{nome}; un cognome o una nota li distinguono.")})
        con = [c for c in self._conoscenti.values() if _chiave(c.nome) == k]
        if con:
            nomi = ", ".join(c.descrizione() for c in con[:3])
            out.append({"tipo": "conoscente", "testo": (
                f"Conosco già {nomi}, ma con un'altra voce: è un altro {nome}, non "
                f"{con[0].nome_pieno()}? Se lo salvi resta un profilo a parte; un cognome o una "
                f"nota li distinguono.")})
        if self.eta is None:
            out.append({"tipo": "eta", "testo": (
                "Non so dire l'età dalla voce: i bambini non si salvano come conoscenti, se è "
                "un bambino rispondi No.")})
        return out

    # ── le proposte sugli schermi ──
    def admin_ids(self) -> list[str]:
        return [str(getattr(p, "id", "")) for p in list(getattr(self.registry, "users",
                                                                {}).values())
                if getattr(p, "admin", False) and getattr(p, "id", None)]

    def scheda(self, p: Proposta) -> dict:
        from ..schermi import schede
        if p.esito is None:
            domanda = (f"Ho sentito una voce nuova che chiamate {p.nome}: la salvo come "
                       "conoscente?")
        else:
            domanda = {"salvato": "Salvata come conoscente.",
                       "rifiutato": "Non la salvo, e non te la propongo più.",
                       "scaduta": "Questa voce non la sento più: proposta chiusa."}.get(
                p.esito, "Proposta chiusa.")
        return schede.nuova("conoscente", "Una voce nuova", schede.PERSONALE, durata_s=None,
                            chiave=f"conoscente:{p.id}", proposta=p.id, nome=p.nome,
                            domanda=domanda, estratto=list(p.estratto)[:3],
                            avvisi=[a["testo"] for a in p.avvisi], aperta=p.esito is None)

    def manda(self, p: Proposta) -> int:
        """La scheda sugli schermi personali di chi amministra (mai su quelli di stanza, mai a
        voce). Quanti con una pagina aperta; senza, si riprova (`ogni_tanto`)."""
        hub = self.schermi
        if hub is None:
            return 0
        admin = set(self.admin_ids())
        n = 0
        scheda = self.scheda(p)
        try:
            for s in hub.abbinati():
                if str(s.get("proprietario") or "") in admin:
                    try:
                        if hub.collegato(s["id"]):
                            n += bool(hub.invia_a(s["id"], scheda, creato=s.get("creato"),
                                                  proprietario=s.get("proprietario")))
                    except Exception:  # noqa: BLE001
                        continue
        except Exception:  # noqa: BLE001
            return 0
        if n and p.esito is None and not p.mandata:
            p.mandata = True
            self._misura("mandata")
        return n

    def ogni_tanto(self):
        """Dalla stanza (ogni 5 s): le proposte non ancora mandate, la scadenza una volta al
        giorno, il file cambiato da fuori."""
        with self._lock:
            self._sincronizza()
            da_mandare = [p for p in self._proposte.values() if p.esito is None and not p.mandata]
        for p in da_mandare:
            self.manda(p)
        if time.time() - self._ultima_rotazione >= GIORNO_S:
            try:
                self.ruota()
            except Exception as e:  # noqa: BLE001
                self.log(f"   [CONOSCENTI] scadenze: {type(e).__name__}: {e}")

    def proposte_aperte(self) -> list[Proposta]:
        with self._lock:
            return [p for p in self._proposte.values() if p.esito is None]

    def risposta(self, pid: str, azione: str, admin_id: str, nome: str = "", cognome: str = "",
                 nota: str = "") -> dict:
        """Il tasto della scheda (POST /api/conoscenti): «si» (con il nome proposto o uno
        diverso, cognome e nota facoltativi) o «no». Il server ha già controllato che lo
        schermo sia personale di chi amministra."""
        azione = str(azione or "").strip().lower()
        nome = " ".join(str(nome or "").split())[:40]
        cognome = " ".join(str(cognome or "").split())[:40]
        nota = " ".join(str(nota or "").split())[:80]
        with self._lock:
            p = self._proposte.get(str(pid or ""))
            if p is None or p.esito is not None:
                return {"ok": False, "errore": "Questa proposta non c'è più.", "_stato": 410}
            g = self._gruppi.get(p.gruppo)
            if g is None:
                p.esito = "scaduta"
                return {"ok": False, "errore": "Questa voce non la sento più da tempo: non "
                                               "posso salvarla.", "_stato": 410}
            if azione == "no":
                p.esito = "rifiutato"
                g.stato = "rifiutato"
                self._rifiutati.append(g.centro.copy())
                del self._rifiutati[:-RIFIUTATI_MAX]
                g.indizi.clear()
                self._misura("rifiuto")
                out = {"ok": True, "frase": "Va bene: non la salvo, e non te la ripropongo."}
            elif azione == "si":
                nome = nome or p.nome
                if not re.fullmatch(r"[^\W\d_][\w' -]*", nome):
                    return {"ok": False, "errore": "Scrivi un nome fatto di lettere.",
                            "_stato": 400}
                gemelli = [c for c in self._conoscenti.values()
                           if (_chiave(c.nome), _chiave(c.cognome), _chiave(c.nota))
                           == (_chiave(nome), _chiave(cognome), _chiave(nota))]
                if gemelli:
                    return {"ok": False, "_stato": 409, "errore": (
                        f"Ho già un conoscente che si chiama {gemelli[0].descrizione()}: "
                        "aggiungi un cognome o una nota per distinguerli.")}
                c = Conoscente(uuid.uuid4().hex, nome[:1].upper() + nome[1:], cognome, nota,
                               g.centro.copy(), self._modello(),
                               datetime.date.today().isoformat(), time.time(), str(admin_id))
                self._conoscenti[c.id] = c
                self.salva()
                p.esito = "salvato"
                g.stato = "salvato"
                self._gruppi.pop(g.n, None)       # da adesso la riconosce il profilo
                diverso = _chiave(nome) != _chiave(p.nome)
                self._misura("conferma", nome_diverso=diverso, cognome=bool(cognome),
                             nota=bool(nota),
                             omonimo=bool(any(a["tipo"] in ("famiglia", "conoscente")
                                              for a in p.avvisi)))
                out = {"ok": True, "conoscente": c.id,
                       "frase": f"Salvato: da adesso riconosco {c.descrizione()}."}
            else:
                return {"ok": False, "errore": "azione sconosciuta", "_stato": 400}
        self.manda(p)
        return out

    # ── promozione e ritorno (solo chi amministra: lo controlla il tool) ──
    def promuovi(self, cid: str, nome: str = "", nascita: str | None = None,
                 tutori=()) -> object:
        """Il conoscente diventa familiare: un profilo in speakers.json con lo **stesso id**,
        l'impronta, il nome (con il cognome se serve a distinguerlo); fuori dai conoscenti.
        Restituisce il profilo. Errore (ValueError con la frase) se il nome c'è già."""
        from ..speaker_id import UserProfile
        reg = self.registry
        if reg is None or not hasattr(reg, "users"):
            raise ValueError("Qui non ho il registro delle voci.")
        with self._lock:
            c = self._conoscenti.get(str(cid))
            if c is None:
                raise ValueError("Questo conoscente non c'è più.")
            nome = " ".join(str(nome or "").split()) or c.nome_pieno()
            trova = getattr(reg, "find", None)
            gia = trova(nome) if callable(trova) else (nome if nome in reg.users else None)
            if gia is not None or nome in reg.users:
                raise ValueError(
                    f"In famiglia c'è già {gia or nome}: per tenerli distinti dimmi un nome "
                    "diverso per lui.")
            prof = UserProfile(name=nome, voiceprint=c.impronta.copy() if c.impronta is not None
                               else None,
                               initial_voiceprint=(c.impronta.copy() if c.impronta is not None
                                                   else None),
                               model=c.modello or self._modello(), admin=False,
                               nascita=nascita or None, tutori=[str(t) for t in tutori or ()])
            prof.id = c.id
            prof.impronta_data = datetime.date.today().isoformat()
            # Le impronte per satellite seguono la persona (15/10)
            prof.impronte_satellite = dict(c.impronte_satellite or {})
            reg.users[nome] = prof
            if hasattr(reg, "save"):
                reg.save()
            self._conoscenti.pop(c.id, None)
            self.salva()
        for f in list(self.su_livello):
            try:
                f(f"conoscente:{c.id}", c.id, nome)
            except Exception as e:  # noqa: BLE001
                self.log(f"   [CONOSCENTI] righe non spostate: {type(e).__name__}")
        self._misura("promosso", minore=bool(nascita and tutori))
        return prof

    def declassa(self, prof) -> Conoscente:
        """Un familiare torna conoscente (chi amministra e i minori no: lo controlla anche il
        tool): stesso id e impronta, fuori da speakers.json."""
        reg = self.registry
        if prof is None or getattr(prof, "admin", False):
            raise ValueError("Chi amministra non si può togliere dalla famiglia così.")
        try:
            from ..minori import e_minore
            if e_minore(prof):
                raise ValueError("Un minore resta in famiglia: non lo rendo conoscente.")
        except ValueError:
            raise
        except Exception:  # noqa: BLE001
            pass
        if getattr(prof, "voiceprint", None) is None:
            raise ValueError("Di questa persona non ho l'impronta della voce.")
        with self._lock:
            parti = str(prof.name).split(" ", 1)
            c = Conoscente(str(prof.id), parti[0], parti[1] if len(parti) > 1 else "", "",
                           np.asarray(prof.voiceprint, dtype=np.float32).copy(),
                           getattr(prof, "model", None) or self._modello(),
                           datetime.date.today().isoformat(), time.time())
            c.impronte_satellite = dict(getattr(prof, "impronte_satellite", None) or {})
            reg.users.pop(prof.name, None)
            if hasattr(reg, "save"):
                reg.save()
            self._conoscenti[c.id] = c
            self.salva()
        for f in list(self.su_livello):
            try:
                f(c.id, f"conoscente:{c.id}", c.nome_pieno())
            except Exception as e:  # noqa: BLE001
                self.log(f"   [CONOSCENTI] righe non spostate: {type(e).__name__}")
        self._misura("declassato")
        return c

    # ── la stanza dimentica un satellite ──
    def dimentica_sat(self, sat):
        """«Dimentica» della stanza: gli indizi presi da lì e i vocativi in attesa."""
        with self._lock:
            self._vocativi.pop(sat, None)
            for g in self._gruppi.values():
                g.indizi = [i for i in g.indizi if i.sat != sat]

    # ── misure e stato ──
    def _misura(self, evento: str, **campi):
        if self.misure is not None:
            try:
                self.misure.scrivi("conoscenti", evento=evento, **campi)
            except Exception:  # noqa: BLE001
                pass

    def stato(self) -> dict:
        with self._lock:
            stati: dict = {}
            for g in self._gruppi.values():
                stati[g.stato] = stati.get(g.stato, 0) + 1
            return {"conoscenti": len(self._conoscenti), "gruppi": len(self._gruppi),
                    "gruppi_per_stato": stati,
                    "proposte_aperte": sum(1 for p in self._proposte.values()
                                           if p.esito is None)}


def _corto(testo: str, n: int = ESTRATTO_RIGA) -> str:
    t = " ".join(str(testo or "").split())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def _chi_detto(riga: dict) -> str:
    if riga.get("chi") == "calliope":
        return "Calliope"
    if riga.get("sicurezza") == "voce" and riga.get("nome"):
        return str(riga["nome"])
    return "un'altra voce"


def load_conoscenti(cfg, registry=None, misure=None, log=print) -> Conoscenti | None:
    """I conoscenti con `stanza_conoscenti: true` (e il registro delle voci), altrimenti
    None."""
    if not accesa(cfg) or registry is None:
        return None
    try:
        c = Conoscenti(cfg, registry=registry, misure=misure, log=log)
    except Exception as e:  # noqa: BLE001
        log(f"[CONOSCENTI] non pronti ({type(e).__name__}: {e})")
        return None
    nomi = set(getattr(cfg, "wake_names", None) or ()) | {"Calliope"}
    c.esclusi = {str(n) for n in nomi}
    # La prima scadenza la fa `ogni_tanto` dalla stanza, con le pulizie delle righe già legate
    log(f"[CONOSCENTI] Voci nuove proposte come conoscenti a chi amministra ({len(c.elenco())} "
        f"salvati, scadenza {c.giorni} giorni senza sentirli)")
    return c
