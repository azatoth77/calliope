"""
Il guardiano a posteriori della stanza (14/10, conversazione di stanza, **passo 6**: progetto
docs/ricerche/2026-10-13-conversazione-di-stanza.md § 3.9 e § 6 riga 6; decisione 0029 punto
4). Interruttore `stanza_guardia: spenta | ombra | attiva`, di serie spenta.

Il guardiano in diretta resta com'è sulle frasi **rivolte a Calliope** (domanda di un minore o
di un ospite, due cancelli); sulle chiacchiere della stanza nessun giudizio in diretta (passo 0,
`pericolo_non_rivolta`). Qui si guarda **dopo**: quando la trascrizione si è assestata (le righe
finite da `stanza_guardia_attesa_s`; dal passo 3 sarà quella corretta dalla corsia lenta), a
blocchi, con le righe intorno, e solo dove **un minore parla o è presente**.

- **Quali righe**: quelle di un minore (voce sopra soglia o zona grigia) e quelle dette mentre un
  minore era presente vicino a quel satellite (le presenze del § 3.5 ter, più
  `stanza_presenza_s`). Mai le righe di Calliope, della TV o le frasi rivolte a Calliope (quelle
  le ha già giudicate il guardiano in diretta): stanno nel blocco solo come contesto.
- **Il giudizio**: il rilevatore di pericolo di oggi (gemma4 e4b su Ollama, `guardiano.py`: lo
  stesso client e le stesse opzioni, così non si ricarica niente) con un prompt che dice che è
  una conversazione di famiglia, con scherzi, giochi, TV e videogiochi (i falsi da evitare), e
  un output strutturato: livello (niente, dubbio, acuto), categoria (autolesionismo, abuso,
  pericolo), contesto (serio, scherzo, gioco, tv, non chiaro) e le righe del segnale.
- **Filtri dopo il giudizio** (§ 3.9): uno scherzo, un gioco o la TV non sono un segnale; un
  acuto vale solo con l'attribuzione sicura (una riga del minore con la voce sopra soglia, o
  qualcuno che parla di fargli del male mentre lui è presente); con la zona grigia, una parola
  incerta (`p_min` sotto `stanza_guardia_p`, quando Whisper la dà) o le righe del segnale fuori
  dal blocco resta un dubbio.
- **Cosa succede**: in **ombra** niente, solo le misure (`stanza-*.jsonl`, tipo `guardia`: mai
  parole, mai nomi; il minore per id) e cosa sarebbe successo. In **attiva** un acuto dà **solo
  un avviso al tutore sullo schermo personale** (decisione 0029 punto 4), senza le parole e mai
  a voce, con il rimando a `stanza_cerca` per leggerle; al più `stanza_guardia_avvisi_giorno`
  al giorno per minore, la stessa categoria non ripetuta entro 24 ore. Due dubbi della stessa
  categoria in giorni diversi entro 7 giorni danno **un** avviso non urgente.
- **Carico**: un thread a bassa precedenza; un blocco si giudica solo quando la voce è ferma da
  `stanza_guardia_quiete_s` (nessuna risposta del modello in corso, nessuna frase che aspetta
  Whisper, nessuno che parla a Calliope), al più `stanza_guardia_giudizi_ora` giudizi all'ora;
  il resto aspetta in coda (al più `CODA_MAX_S`, poi si butta e si conta).
- **Pausa e «dimentica»**: in pausa («abbiamo ospiti») su quel satellite non si raccoglie e non
  si giudica; i blocchi di prima aspettano la ripresa. Le righe dimenticate non si giudicano: un
  blocco con righe che non ci sono più si butta prima e dopo il giudizio (anche a metà).

La lettura di chi amministra (`calliope stato --guardia`): i segnali con giorno, ora, stanza,
minore, livello e categoria, mai le parole; `--falso ID` e `--vero ID` li segnano, e la sezione
di `calliope stato --turni` conta gli acuti falsi per settimana (obiettivo per accendere: meno
di uno).
"""

from __future__ import annotations

import collections
import datetime
import threading
import time
from dataclasses import dataclass, field

SPENTA, OMBRA, ATTIVA = "spenta", "ombra", "attiva"
NIENTE, DUBBIO, ACUTO = "niente", "dubbio", "acuto"
LIVELLI = (NIENTE, DUBBIO, ACUTO)
CATEGORIE = ("autolesionismo", "abuso", "pericolo", "nessuna")
CONTESTI = ("serio", "scherzo", "gioco", "tv", "non_chiaro")
NON_SEGNALI = ("scherzo", "gioco", "tv")

BLOCCO_RIGHE = 10              # righe da giudicare in un blocco
CONTESTO_PRIMA = 6             # righe di contesto prima del blocco
CONTESTO_DOPO = 3              # e dopo
BLOCCO_PAUSA_S = 300.0         # un silenzio così lungo spezza il blocco (come lo scambio)
RIGA_MAX_CAR = 240             # una riga più lunga si accorcia nel prompt
TESTO_MAX_CAR = 3600           # il blocco intero: la finestra del rilevatore è di 2048 token
CODA_MAX_S = 24 * 3600.0       # un blocco che aspetta più di così si butta (contato)
CODA_MAX = 500
TENTATIVI = 3                  # un giudizio guasto si riprova al più tante volte
PASSO_S = 2.0                  # il giro del thread
DUBBI_GIORNI = 7
RIPETUTO_S = 24 * 3600.0


def modo(cfg) -> str:
    m = str(getattr(cfg, "stanza_guardia", SPENTA) or SPENTA).strip().lower()
    return m if m in (SPENTA, OMBRA, ATTIVA) else SPENTA


PROMPT = (
    "Sei il controllo di sicurezza di un'assistente vocale di casa. Qui sotto c'è un pezzo di "
    "conversazione trascritta in una stanza di casa, tra le persone della famiglia: non era "
    "rivolta all'assistente. È presente un minore: {minori}. La trascrizione automatica può "
    "sbagliare qualche parola.\n"
    "Le righe con il numero tra parentesi quadre sono da giudicare; quelle con il trattino sono "
    "il contesto intorno.\n"
    "In famiglia si scherza, si litiga per finta, si gioca ai videogiochi e ai giochi da "
    "tavolo, si guarda la TV, si canta, si fanno i compiti e si esagera («ti ammazzo se perdi», "
    "«muoio di noia», «che palle, mi sparo», «mi uccide questa verifica»): tutto questo è "
    "NIENTE.\n"
    "ACUTO: una riga dice in modo esplicito e serio che il minore vuole farsi del male, morire, "
    "sparire o smettere di mangiare; oppure che qualcuno gli fa del male, lo picchia, lo tocca, "
    "lo minaccia, gli chiede di tenere un segreto con i genitori o di incontrarlo da solo; "
    "oppure che è in pericolo adesso.\n"
    "DUBBIO: una cosa che potrebbe essere un segnale così, ma è ambigua o manca il contesto.\n"
    "NIENTE: tutto il resto, anche argomenti difficili detti con calma (notizie, storia, un "
    "film, un libro, un compito).\n"
    "Rispondi in JSON con «livello» (NIENTE, DUBBIO o ACUTO), «categoria» (autolesionismo, "
    "abuso, pericolo o nessuna), «contesto» (serio, scherzo, gioco, tv o non_chiaro) e «righe» "
    "(i numeri delle righe del segnale; vuoto con NIENTE).\n\n{righe}")

SCHEMA = {"type": "object", "properties": {
    "livello": {"type": "string", "enum": ["NIENTE", "DUBBIO", "ACUTO"]},
    "categoria": {"type": "string", "enum": list(CATEGORIE)},
    "contesto": {"type": "string", "enum": list(CONTESTI)},
    "righe": {"type": "array", "items": {"type": "integer"}}},
    "required": ["livello", "categoria", "contesto", "righe"]}

# Gli argomenti dell'avviso (mai le parole): quando parla il minore e quando se ne parla con lui
# presente
ARGOMENTI_PARLA = {"autolesionismo": "ha parlato di farsi del male o di stare molto male",
                   "abuso": "ha parlato di qualcuno che potrebbe fargli del male o metterlo in "
                            "pericolo",
                   "pericolo": "ha detto una cosa che fa pensare che sia in pericolo o stia "
                               "molto male"}
ARGOMENTI_PRESENTE = {"autolesionismo": "si è parlato di farsi del male",
                      "abuso": "si è parlato di qualcuno che potrebbe fargli del male o "
                               "metterlo in pericolo",
                      "pericolo": "si è detta una cosa che fa pensare che sia in pericolo"}


# ─────────────────────────── il blocco ───────────────────────────

@dataclass
class Blocco:
    sat: object
    nome_sat: str
    stanza_nome: str
    righe: list                      # tutte le righe del blocco, in ordine (dict del registro)
    giudicate: list                  # le righe da giudicare (sottoinsieme di `righe`), in ordine
    presenti: dict                   # minore (id) → nome: presenti per la voce in quel tempo
    creato: float = field(default_factory=time.monotonic)
    tentativi: int = 0

    @property
    def seqs(self) -> set:
        return {r["seq"] for r in self.giudicate}

    def minori(self) -> dict:
        """I minori del blocco: quelli che parlano (con la voce o in zona grigia) e i
        presenti."""
        out = dict(self.presenti)
        for r in self.giudicate:
            if r.get("minore") and r.get("persona_id"):
                out.setdefault(r["persona_id"], r.get("nome") or r["persona_id"])
        return out

    def parlato_s(self) -> float:
        return round(sum(max(0.0, float(r.get("fine") or 0) - float(r.get("inizio") or 0))
                         for r in self.giudicate), 1)


def _persona(r: dict) -> str | None:
    chi = str(r.get("chi") or "")
    return chi[len("persona:"):] if chi.startswith("persona:") else None


def etichetta(r: dict) -> str:
    """Come nel blocco caldo (stanza/contesto.py), più «(minore)»."""
    if r.get("chi") == "calliope":
        return "Calliope"
    nome, sic = r.get("nome"), r.get("sicurezza")
    if nome and sic == "voce":
        base = str(nome)
    elif nome and sic == "grigia":
        base = f"{nome}?"
    else:
        base = "voce non riconosciuta"
    if r.get("minore") and nome and sic in ("voce", "grigia"):
        base += " (minore)"
    if r.get("rivolta") == "si":
        base += " → Calliope"
    return base


def _corta(testo: str) -> str:
    t = " ".join(str(testo or "").split())
    return t if len(t) <= RIGA_MAX_CAR else t[:RIGA_MAX_CAR - 1] + "…"


def formatta(b: Blocco) -> str:
    """Le righe per il prompt: numerate quelle da giudicare, col trattino il contesto. Entro
    TESTO_MAX_CAR: si toglie prima il contesto più lontano, poi si accorciano le righe."""
    giud = {id(r): i + 1 for i, r in enumerate(b.giudicate)}
    righe = list(b.righe)

    def testo(rr):
        out = []
        for r in rr:
            n = giud.get(id(r))
            pre = f"[{n}]" if n else "-"
            out.append(f"{pre} {etichetta(r)}: {_corta(r.get('testo'))}")
        return "\n".join(out)

    t = testo(righe)
    while len(t) > TESTO_MAX_CAR:
        # Il contesto più lontano dal blocco esce per primo (prima quello prima, poi dopo)
        fuori = [i for i, r in enumerate(righe) if id(r) not in giud]
        if not fuori:
            break
        primo = next(i for i, r in enumerate(righe) if id(r) in giud)
        prima = [i for i in fuori if i < primo]
        righe.pop(prima[0] if prima else fuori[-1])
        t = testo(righe)
    return t[:TESTO_MAX_CAR]


def prompt(b: Blocco) -> str:
    nomi = ", ".join(sorted(set(b.minori().values()))) or "un ragazzo"
    return PROMPT.format(minori=nomi, righe=formatta(b))


def leggi_esito(js) -> dict | None:
    """L'output del modello in forma pulita, o None se non si legge."""
    if not isinstance(js, dict):
        return None
    liv = str(js.get("livello") or "").strip().lower()
    cat = str(js.get("categoria") or "").strip().lower()
    ctx = str(js.get("contesto") or "").strip().lower()
    if liv not in LIVELLI:
        return None
    righe = []
    for x in js.get("righe") or []:
        try:
            righe.append(int(x))
        except (TypeError, ValueError):
            continue
    return {"livello": liv, "categoria": cat if cat in CATEGORIE else "nessuna",
            "contesto": ctx if ctx in CONTESTI else "non_chiaro", "righe": righe}


class GiudiceModello:
    """Il rilevatore di pericolo di `guardiano.py` con il prompt della stanza: stesso modello,
    stesso Ollama, stesse opzioni (num_ctx e keep_alive: niente ricaricamenti)."""

    def __init__(self, guardiano, timeout_s: float = 30.0):
        self.guardiano, self.timeout_s = guardiano, float(timeout_s)
        self.ultimo_ms: float | None = None

    def __call__(self, b: Blocco) -> dict | None:
        js, ms = self.guardiano.chiedi_json(prompt(b), SCHEMA, num_predict=80,
                                            timeout=self.timeout_s)
        self.ultimo_ms = ms
        return leggi_esito(js)


# ─────────────────────────── la guardia ───────────────────────────

class Guardia:
    def __init__(self, cfg, stanza, giudice, registry=None, avvisi=None, misure=None,
                 occupato=(), log=print, avvia: bool = True):
        self.cfg, self.stanza, self.giudice = cfg, stanza, giudice
        self.registry = registry if registry is not None else getattr(stanza, "registry", None)
        self._avvisi = avvisi
        self.misure = misure if misure is not None else getattr(stanza, "misure", None)
        self.occupato = list(occupato)
        self.log = log
        self._lock = threading.Lock()
        self._coda: collections.deque = collections.deque()
        self._visti: dict = {}                 # sat → set dei seq già raccolti
        self._fatti: collections.deque = collections.deque()   # monotonic dei giudizi
        self._voce = False
        self._libera_da = 0.0
        self._n_id = 0
        self._ultimo_id = ""
        # Per gli avvisi (attiva) e per ciò che sarebbe successo (ombra): epoch degli avvisi
        # per minore, (minore, categoria) → epoch dell'ultimo avviso, i dubbi per minore e
        # categoria (giorno), e l'ultimo avviso dei dubbi
        self._avvisi_dati: dict = {}
        self._categoria: dict = {}
        self._dubbi: dict = {}
        self._dubbi_avviso: dict = {}
        self.giudizi = 0
        self._riprendi_misure()
        self._fermo = threading.Event()
        self._thread = None
        if avvia:
            self._thread = threading.Thread(target=self._lavora, name="stanza-guardia",
                                            daemon=True)
            self._thread.start()

    # ── configurazione ──
    @property
    def modo(self) -> str:
        return modo(self.cfg)

    def _cfg(self, nome, predefinito):
        v = getattr(self.cfg, nome, predefinito)
        return predefinito if v is None else v

    # ── la voce (oltre alle funzioni `occupato`) ──
    def voce_occupata(self):
        self._voce = True

    def voce_libera(self):
        if self._voce:
            self._libera_da = time.monotonic()
        self._voce = False

    def libera(self) -> bool:
        """La DGX è libera per un giudizio: nessuna funzione `occupato` dice sì, e da
        `stanza_guardia_quiete_s` (nessuna risposta, nessuna frase in Whisper, nessuno che parla
        a Calliope)."""
        ora = time.monotonic()
        occ = self._voce
        for f in self.occupato:
            try:
                occ = occ or bool(f())
            except Exception:  # noqa: BLE001 — nel dubbio è occupata
                occ = True
        if occ:
            self._libera_da = ora
            return False
        return ora - self._libera_da >= float(self._cfg("stanza_guardia_quiete_s", 5.0))

    def _sotto_tetto(self) -> bool:
        tetto = int(self._cfg("stanza_guardia_giudizi_ora", 30))
        ora = time.monotonic()
        while self._fatti and ora - self._fatti[0] > 3600.0:
            self._fatti.popleft()
        return tetto <= 0 or len(self._fatti) < tetto

    # ── il thread ──
    def _lavora(self):
        prossima_raccolta = 0.0
        while not self._fermo.wait(PASSO_S):
            if self.modo == SPENTA:
                continue
            try:
                if time.monotonic() >= prossima_raccolta:
                    prossima_raccolta = time.monotonic() + float(
                        self._cfg("stanza_guardia_ogni_s", 60.0))
                    self.raccogli()
                while (not self._fermo.is_set() and self.libera() and self._sotto_tetto()
                       and self.giudica_uno()):
                    pass
            except Exception as e:  # noqa: BLE001 — la guardia non ferma niente
                self.log(f"   [GUARDIA] giro non riuscito: {type(e).__name__}")

    def giro(self, ora: float | None = None) -> int:
        """Un giro intero (prove): raccoglie e giudica finché la voce è libera e il tetto lo
        permette. Quanti giudizi."""
        if self.modo == SPENTA:
            return 0
        self.raccogli(ora)
        n = 0
        while self.libera() and self._sotto_tetto() and self.giudica_uno():
            n += 1
        return n

    def chiudi(self):
        self._fermo.set()

    # ── la raccolta ──
    def _registri(self) -> list:
        st = self.stanza
        return list(getattr(st, "_registri", {}).items())

    def _minori_profili(self) -> dict:
        from .. import minori
        reg = self.registry
        out = {}
        for u in list(getattr(reg, "users", {}).values()) if reg is not None else []:
            try:
                if minori.e_minore(u):
                    out[getattr(u, "id", None) or u.name] = u
            except Exception:  # noqa: BLE001
                continue
        return out

    def _presenze_minori(self, sat, minori_: dict) -> list:
        """(id, nome, da, a) delle presenze dei minori vicino a `sat`, allungate di
        `stanza_presenza_s` (la presenza si chiude dopo tanto senza sentirli)."""
        dopo = float(self._cfg("stanza_presenza_s", 600.0))
        out = []
        fn = getattr(self.stanza, "presenze", None)
        if fn is None:
            return out
        for pid, prof in minori_.items():
            try:
                intervalli = fn(pid)
            except Exception:  # noqa: BLE001
                continue
            for s, a, b in intervalli:
                if str(s) == str(sat):
                    out.append((pid, prof.name, float(a), float(b) + dopo))
        return out

    def raccogli(self, ora: float | None = None) -> int:
        """Le righe nuove e assestate di ogni satellite (non in pausa) diventano blocchi in
        coda, se un minore parla o è presente. Quanti blocchi nuovi."""
        if self.modo == SPENTA or not getattr(self.cfg, "minori_enabled", True):
            return 0
        ora = time.time() if ora is None else float(ora)
        attesa = float(self._cfg("stanza_guardia_attesa_s", 120.0))
        ogni = float(self._cfg("stanza_guardia_blocco_max_s", 900.0))
        minori_ = self._minori_profili()
        nuovi = 0
        for sat, reg in self._registri():
            pausa = getattr(self.stanza, "stato_pausa", lambda s: None)(sat)
            if pausa is not None:
                continue                      # ospiti: niente raccolta né giudizi
            righe = reg.righe()
            visti = self._visti.setdefault(sat, set())
            # Le righe uscite (dimenticate, sostituite, oltre la tenuta) non tornano: via
            visti.intersection_update({r["seq"] for r in righe})
            nuove = [r for r in righe if r["seq"] not in visti]
            if not nuove:
                continue
            assestate = [r for r in nuove if float(r.get("fine") or r["t"]) <= ora - attesa]
            if not assestate:
                continue
            ultima = max(float(r.get("fine") or r["t"]) for r in righe)
            quieta = ultima <= ora - attesa
            vecchia = min(float(r.get("fine") or r["t"]) for r in assestate) <= ora - ogni
            if not (quieta or vecchia or len(assestate) >= BLOCCO_RIGHE * 2):
                continue                      # lo scambio continua: si aspetta che si chiuda
            for r in assestate:
                visti.add(r["seq"])
            nuovi += self._blocchi(sat, righe, assestate, minori_)
        return nuovi

    def _da_giudicare(self, r: dict, presenze: list) -> tuple[bool, dict]:
        """La riga si giudica? E i minori presenti in quel momento."""
        if r.get("chi") in ("calliope", "tv") or r.get("rivolta") == "si":
            return False, {}
        if not str(r.get("testo") or "").strip():
            return False, {}
        t = float(r.get("inizio") or r.get("t") or 0)
        presenti = {pid: nome for pid, nome, a, b in presenze if a - 60.0 <= t <= b}
        parla = bool(r.get("minore")) and r.get("sicurezza") in ("voce", "grigia")
        return parla or bool(presenti), presenti

    def _blocchi(self, sat, righe: list, assestate: list, minori_: dict) -> int:
        presenze = self._presenze_minori(sat, minori_)
        scelte = []
        for r in assestate:
            si, presenti = self._da_giudicare(r, presenze)
            if si:
                scelte.append(dict(r, persona_id=_persona(r), presenti_riga=presenti))
        if not scelte:
            return 0
        # Gruppi: un silenzio oltre BLOCCO_PAUSA_S o BLOCCO_RIGHE righe chiudono un blocco
        gruppi, cur = [], []
        for r in scelte:
            if cur and (len(cur) >= BLOCCO_RIGHE or float(r.get("inizio") or r["t"]) - float(
                    cur[-1].get("fine") or cur[-1]["t"]) > BLOCCO_PAUSA_S):
                gruppi.append(cur)
                cur = []
            cur.append(r)
        if cur:
            gruppi.append(cur)
        info = (getattr(self.stanza, "_info", {}) or {}).get(sat) or {}
        nome_sat = str(info.get("nome") or sat)
        stanza_nome = str(info.get("stanza") or info.get("nome") or sat)
        per_seq = {r["seq"]: i for i, r in enumerate(righe)}
        n = 0
        for g in gruppi:
            i0, i1 = per_seq.get(g[0]["seq"], 0), per_seq.get(g[-1]["seq"], len(righe) - 1)
            scelte_seq = {r["seq"]: r for r in g}
            tutte = []
            for r in righe[max(0, i0 - CONTESTO_PRIMA):i1 + 1 + CONTESTO_DOPO]:
                if r.get("chi") == "tv":
                    continue
                tutte.append(scelte_seq.get(r["seq"], r))
            presenti = {}
            for r in g:
                presenti.update(r.get("presenti_riga") or {})
            b = Blocco(sat, nome_sat, stanza_nome, tutte, [scelte_seq[r["seq"]] for r in g],
                       presenti)
            with self._lock:
                self._coda.append(b)
                while len(self._coda) > CODA_MAX:
                    via = self._coda.popleft()
                    self._misura(esito="scaduto", sat=via.nome_sat, righe=len(via.giudicate))
            n += 1
        return n

    def in_coda(self) -> int:
        with self._lock:
            return len(self._coda)

    # ── il giudizio ──
    def _vivi(self, b: Blocco) -> bool:
        reg = dict(self._registri()).get(b.sat)
        if reg is None:
            return False
        try:
            return b.seqs <= reg.seq_vivi()
        except Exception:  # noqa: BLE001
            return False

    def giudica_uno(self) -> bool:
        """Il primo blocco giudicabile della coda (non di un satellite in pausa). False se non
        ce n'è nessuno."""
        if self.modo == SPENTA:
            return False
        b = None
        with self._lock:
            ora = time.monotonic()
            while self._coda and ora - self._coda[0].creato > CODA_MAX_S:
                via = self._coda.popleft()
                self._misura(esito="scaduto", sat=via.nome_sat, righe=len(via.giudicate))
            for x in list(self._coda):
                if getattr(self.stanza, "stato_pausa", lambda s: None)(x.sat) is None:
                    b = x
                    self._coda.remove(x)
                    break
        if b is None:
            return False
        if not self._vivi(b):
            self._misura(esito="dimenticato", sat=b.nome_sat, righe=len(b.giudicate))
            return True
        self._fatti.append(time.monotonic())
        self.giudizi += 1
        t0 = time.perf_counter()
        try:
            res = self.giudice(b)
        except Exception:  # noqa: BLE001 — un giudice guasto vale «guasto»
            res = None
        ms = round((time.perf_counter() - t0) * 1000, 1)
        if not self._vivi(b):
            # «Dimentica» durante il giudizio: il giudizio si butta
            self._misura(esito="dimenticato", sat=b.nome_sat, righe=len(b.giudicate), ms=ms)
            return True
        if res is None:
            b.tentativi += 1
            self._misura(esito="guasto", sat=b.nome_sat, righe=len(b.giudicate), ms=ms,
                         tentativo=b.tentativi)
            if b.tentativi < TENTATIVI:
                with self._lock:
                    self._coda.append(b)
            return True
        self._esito(b, res, ms)
        return True

    def decidi(self, b: Blocco, res: dict) -> dict:
        """Il livello dopo i filtri (§ 3.9), il minore e il modo («parla», «presente»)."""
        liv, cat, ctx = res["livello"], res["categoria"], res["contesto"]
        segnate = [b.giudicate[i - 1] for i in res.get("righe") or []
                   if 1 <= i <= len(b.giudicate)]
        motivo, modo_, minori_ = None, None, {}
        soglia_p = float(self._cfg("stanza_guardia_p", 0.5))
        if liv != NIENTE and ctx in NON_SEGNALI:
            liv, motivo = NIENTE, ctx
        if liv != NIENTE:
            parla = {r["persona_id"]: r.get("nome") for r in segnate
                     if r.get("minore") and r.get("persona_id") and r.get("sicurezza") == "voce"}
            grigia = {r["persona_id"]: r.get("nome") for r in segnate
                      if r.get("minore") and r.get("persona_id") and r.get("sicurezza") == "grigia"}
            # I minori presenti (per la voce) quando sono state dette le righe del segnale
            presenti = {}
            for r in segnate:
                presenti.update(r.get("presenti_riga") or {})
            if parla:
                minori_, modo_ = parla, "parla"
            elif grigia:
                minori_, modo_ = grigia, "parla"
            elif presenti:
                minori_, modo_ = presenti, "presente"
            else:
                minori_, modo_ = b.minori(), "presente"
            if liv == ACUTO:
                incerte = any(r.get("p_min") is not None and float(r["p_min"]) < soglia_p
                              for r in segnate)
                if not segnate:
                    liv, motivo = DUBBIO, "righe"
                elif incerte:
                    liv, motivo = DUBBIO, "parole_incerte"
                elif cat == "nessuna":
                    liv, motivo = DUBBIO, "categoria"
                elif not parla and grigia:
                    liv, motivo = DUBBIO, "voce_incerta"
                elif not parla and cat == "autolesionismo":
                    liv, motivo = DUBBIO, "non_del_minore"
                elif not parla and not presenti:
                    liv, motivo = DUBBIO, "chi"
            if cat == "nessuna":
                cat = "pericolo"
        return {"livello": liv, "categoria": cat if liv != NIENTE else None, "contesto": ctx,
                "motivo": motivo, "minori": minori_, "modo": modo_,
                "righe_segnate": len(segnate),
                "ora": (datetime.datetime.fromtimestamp(float(
                    (segnate or b.giudicate)[0].get("inizio") or b.giudicate[0]["t"]))
                    .strftime("%H:%M"))}

    def _esito(self, b: Blocco, res: dict, ms: float):
        d = self.decidi(b, res)
        # L'id prima dell'avviso (14/10): è il riferimento dell'avviso, così `calliope stato
        # --guardia --falso ID` ferma anche l'avviso non ancora visto
        ident = self._nuovo_id()
        avviso = None
        if d["livello"] == ACUTO:
            avviso = self._avviso_acuto(b, d, ident)
        elif d["livello"] == DUBBIO:
            avviso = self._dubbio(b, d, ident)
        self._misura(esito="giudicato", id=ident, sat=b.nome_sat, minori=sorted(d["minori"]),
                     modo_minore=d["modo"], righe=len(b.giudicate),
                     contesto_righe=len(b.righe) - len(b.giudicate), parlato_s=b.parlato_s(),
                     ms=ms, modello=res["livello"], livello=d["livello"],
                     categoria=d["categoria"], contesto=d["contesto"], motivo=d["motivo"],
                     segnate=d["righe_segnate"], avviso=avviso, ora=d["ora"],
                     attesa_s=round(time.monotonic() - b.creato, 1), modo=self.modo)
        if d["livello"] != NIENTE:
            # Mai le parole né i nomi nel log: livello, categoria, stanza
            self.log(f"   [GUARDIA] {b.stanza_nome}: {d['livello']} ({d['categoria']}"
                     + (f", {d['motivo']}" if d["motivo"] else "") + ")"
                     + (f" → avviso {avviso}" if avviso else ""))

    def _nuovo_id(self) -> str:
        base = datetime.datetime.now().strftime("%m%d-%H%M%S")
        with self._lock:
            if base == self._ultimo_id[:11]:
                self._n_id += 1
                ident = f"{base}-{self._n_id}"
            else:
                self._n_id = 0
                ident = base
            self._ultimo_id = ident
        return ident

    # ── gli avvisi ──
    def _avvisi_servizio(self):
        if self._avvisi is not None:
            return self._avvisi
        from .. import minori
        return minori.avvisi()

    def _prof(self, pid):
        for u in list(getattr(self.registry, "users", {}).values()) if self.registry else []:
            if getattr(u, "id", None) == pid:
                return u
        return None

    def _avviso_acuto(self, b: Blocco, d: dict, ident: str = "") -> str | None:
        """Un acuto: per ogni minore, l'avviso (attiva) o ciò che sarebbe successo (ombra):
        «mandato», «ombra», «tetto» (già `stanza_guardia_avvisi_giorno` oggi), «ripetuto»
        (stessa categoria entro 24 ore). Il più significativo dei minori."""
        ora = time.time()
        oggi = datetime.date.today()
        tetto = int(self._cfg("stanza_guardia_avvisi_giorno", 1))
        esiti = []
        for pid, nome in d["minori"].items():
            gia = [t for t in self._avvisi_dati.get(pid, [])
                   if datetime.date.fromtimestamp(t) == oggi]
            ultimo = self._categoria.get((pid, d["categoria"]))
            if ultimo is not None and ora - ultimo < RIPETUTO_S:
                esiti.append("ripetuto")
                continue
            if tetto > 0 and len(gia) >= tetto:
                esiti.append("tetto")
                continue
            self._avvisi_dati.setdefault(pid, []).append(ora)
            self._categoria[(pid, d["categoria"])] = ora
            if self.modo != ATTIVA:
                esiti.append("ombra")
                continue
            arg = (ARGOMENTI_PARLA if d["modo"] == "parla" else ARGOMENTI_PRESENTE).get(
                d["categoria"], ARGOMENTI_PARLA["pericolo"])
            testo = testo_avviso(nome or pid, b.stanza_nome, d["ora"], arg, d["modo"])
            esiti.append("mandato" if self._manda(pid, testo, urgente=True, b=b, ident=ident)
                         else "non_mandato")
        for e in ("mandato", "non_mandato", "ombra", "tetto", "ripetuto"):
            if e in esiti:
                return e
        return None

    def _dubbio(self, b: Blocco, d: dict, ident: str = "") -> str | None:
        """Un dubbio: niente avviso, un conto per minore e categoria. Due dubbi della stessa
        categoria in giorni diversi entro DUBBI_GIORNI → un avviso non urgente (una volta ogni
        DUBBI_GIORNI)."""
        ora = time.time()
        oggi = datetime.date.today()
        esito = None
        for pid, nome in d["minori"].items():
            k = (pid, d["categoria"])
            giorni = [g for g in self._dubbi.get(k, []) if (oggi - g).days < DUBBI_GIORNI]
            altro_giorno = any(g != oggi for g in giorni)
            giorni.append(oggi)
            self._dubbi[k] = giorni[-20:]
            ultimo = self._dubbi_avviso.get(k)
            if not altro_giorno or (ultimo is not None and ora - ultimo < DUBBI_GIORNI * 86400):
                continue
            self._dubbi_avviso[k] = ora
            if self.modo != ATTIVA:
                esito = esito or "ombra"
                continue
            arg = (ARGOMENTI_PARLA if d["modo"] == "parla" else ARGOMENTI_PRESENTE).get(
                d["categoria"], ARGOMENTI_PARLA["pericolo"])
            testo = testo_dubbi(nome or pid, arg, d["modo"])
            esito = ("mandato" if self._manda(pid, testo, urgente=False, b=b, ident=ident)
                     else "non_mandato")
        return esito

    def _manda(self, pid, testo: str, urgente: bool, b: Blocco | None = None,
               ident: str = "") -> bool:
        from ..minori import origine_stanza
        av = self._avvisi_servizio()
        prof = self._prof(pid)
        if av is None or prof is None:
            return False
        try:
            return (av.solo_schermo(prof, "sicurezza_stanza", testo, urgente=urgente,
                                    registry=self.registry,
                                    origine=origine_stanza(b.stanza_nome if b else ""),
                                    rif=f"guardia:{ident}" if ident else None) or 0) > 0
        except Exception as e:  # noqa: BLE001
            self.log(f"   [GUARDIA] avviso non mandato: {type(e).__name__}")
            return False

    # ── misure ──
    def _misura(self, **campi):
        if self.misure is not None:
            try:
                self.misure.scrivi("guardia", **campi)
            except Exception:  # noqa: BLE001
                pass

    def _riprendi_misure(self):
        """Dopo un riavvio: gli avvisi di oggi, l'ultima categoria per minore e i dubbi degli
        ultimi giorni dal file delle misure (il tetto e i dubbi non ripartono da zero)."""
        cartella = getattr(self.misure, "cartella", None)
        if cartella is None:
            return
        from .misure import leggi
        try:
            righe = leggi(str(cartella), DUBBI_GIORNI + 1)
        except Exception:  # noqa: BLE001
            return
        for r in righe:
            if r.get("tipo") != "guardia" or r.get("esito") != "giudicato":
                continue
            try:
                t = datetime.datetime.fromisoformat(str(r.get("t"))).timestamp()
            except ValueError:
                continue
            for pid in r.get("minori") or []:
                if r.get("livello") == ACUTO and r.get("avviso") in ("mandato", "ombra"):
                    self._avvisi_dati.setdefault(pid, []).append(t)
                    self._categoria[(pid, r.get("categoria"))] = t
                elif r.get("livello") == DUBBIO:
                    self._dubbi.setdefault((pid, r.get("categoria")), []).append(
                        datetime.date.fromtimestamp(t))
                    if r.get("avviso") in ("mandato", "ombra"):
                        self._dubbi_avviso[(pid, r.get("categoria"))] = t


def testo_avviso(nome: str, stanza: str, ora: str, argomento: str, modo_: str) -> str:
    """L'avviso al tutore di un acuto: dove e quando, l'argomento, mai le parole; come leggerle
    (stanza_cerca, solo per i tutori)."""
    if modo_ == "parla":
        cosa = f"{nome} {argomento}"
    else:
        cosa = f"con {nome} presente {argomento}"
    return (f"Da verificare, sentito nella conversazione in {stanza} verso le {ora}: {cosa}. "
            f"Non era rivolto a me e non ho detto niente a nessuno. Se vuoi leggere cosa si è "
            f"detto, chiedimi «cosa ha detto {nome} in {stanza} verso le {ora}?».")


def testo_dubbi(nome: str, argomento: str, modo_: str) -> str:
    cosa = f"{nome} {argomento}" if modo_ == "parla" else f"con {nome} presente {argomento}"
    return (f"Da tenere d'occhio, segnale debole: nelle conversazioni di casa di due giorni "
            f"diversi questa settimana {cosa}, in modo poco chiaro. Non ho detto niente a "
            f"nessuno. Quando puoi, chiedigli con calma come sta.")


# ─────────────────────────── riassunto per calliope stato ───────────────────────────

def _p(valori, q):
    from .misure import _p as p
    return p(valori, q)


def riassunto(righe: list[dict]) -> dict:
    """Dalle misure (tipo `guardia` e `guardia_lettura`): per giorno blocchi, ore di
    chiacchiera con un minore, livelli, categorie, contesti, motivi, avvisi; in tutto segnali
    per ora per livello e gli acuti letti falsi per settimana."""
    giorni: dict = {}
    segnali: dict = {}
    letture: dict = {}
    ms: list = []
    for r in righe:
        if r.get("tipo") == "guardia_lettura":
            letture[str(r.get("segnale"))] = str(r.get("esito") or "")
            continue
        if r.get("tipo") != "guardia":
            continue
        g = giorni.setdefault(str(r.get("t", ""))[:10], {
            "blocchi": 0, "parlato_s": 0.0, "livelli": {}, "modello": {}, "categorie": {},
            "contesti": {}, "motivi": {}, "avvisi": {}, "guasti": 0, "dimenticati": 0,
            "scaduti": 0, "righe": 0})
        e = r.get("esito")
        if e == "guasto":
            g["guasti"] += 1
            continue
        if e == "dimenticato":
            g["dimenticati"] += 1
            continue
        if e == "scaduto":
            g["scaduti"] += 1
            continue
        if e != "giudicato":
            continue
        g["blocchi"] += 1
        g["righe"] += int(r.get("righe") or 0)
        g["parlato_s"] += float(r.get("parlato_s") or 0)
        for chiave, valore in (("livelli", r.get("livello")), ("modello", r.get("modello")),
                               ("contesti", r.get("contesto"))):
            v = str(valore or "?")
            g[chiave][v] = g[chiave].get(v, 0) + 1
        if r.get("livello") in (DUBBIO, ACUTO):
            c = str(r.get("categoria") or "?")
            g["categorie"][c] = g["categorie"].get(c, 0) + 1
            if r.get("id"):
                segnali[str(r["id"])] = r
        if r.get("motivo"):
            m = str(r["motivo"])
            g["motivi"][m] = g["motivi"].get(m, 0) + 1
        if r.get("avviso"):
            a = str(r["avviso"])
            g["avvisi"][a] = g["avvisi"].get(a, 0) + 1
        if r.get("ms") is not None:
            ms.append(float(r["ms"]))
    ore = sum(g["parlato_s"] for g in giorni.values()) / 3600
    per_livello = {liv: sum(g["livelli"].get(liv, 0) for g in giorni.values())
                   for liv in (DUBBIO, ACUTO)}
    acuti = [s for s in segnali.values() if s.get("livello") == ACUTO]
    falsi = sum(1 for s in acuti if letture.get(str(s.get("id"))) == "falso")
    letti = sum(1 for s in acuti if str(s.get("id")) in letture)
    settimane = max(1.0, len(giorni) / 7.0) if giorni else None
    for g in giorni.values():
        g["ore"] = round(g.pop("parlato_s") / 3600, 3)
    return {"giorni": giorni, "ore": round(ore, 3),
            "per_ora": {k: (round(v / ore, 2) if ore > 0 else None)
                        for k, v in per_livello.items()},
            "segnali": per_livello, "acuti": len(acuti), "acuti_letti": letti,
            "acuti_falsi": falsi,
            "falsi_settimana": round(falsi / settimane, 2) if settimane else None,
            "ms_p50": _p(ms, 0.5), "ms_p90": _p(ms, 0.9),
            "elenco": sorted(segnali.values(), key=lambda s: str(s.get("t"))),
            "letture": letture}


def testo(r: dict, modo_: str = SPENTA) -> str:
    out = [f"Guardiano a posteriori della stanza (passo 6, stanza_guardia: {modo_})"]
    if not r.get("giorni"):
        out.append("  nessuna misura (spento, o nessuna chiacchiera con un minore)")
        return "\n".join(out)
    for giorno in sorted(r["giorni"]):
        g = r["giorni"][giorno]
        out.append(f"  {giorno}: {g['blocchi']} blocchi ({g['righe']} righe, {g['ore']:.2f} h "
                   f"di chiacchiera con un minore); livelli {g['livelli']} (dal modello "
                   f"{g['modello']}); contesti {g['contesti']}"
                   + (f"; categorie {g['categorie']}" if g["categorie"] else "")
                   + (f"; filtri {g['motivi']}" if g["motivi"] else "")
                   + (f"; avvisi {g['avvisi']}" if g["avvisi"] else "")
                   + (f"; guasti {g['guasti']}" if g["guasti"] else "")
                   + (f"; dimenticati {g['dimenticati']}" if g["dimenticati"] else "")
                   + (f"; scaduti in coda {g['scaduti']}" if g["scaduti"] else ""))
    po = r["per_ora"]
    out.append(f"  Segnali per ora di chiacchiera con un minore: dubbi {po.get(DUBBIO)}, "
               f"acuti {po.get(ACUTO)} (su {r['ore']:.2f} h); giudizio p50 {r['ms_p50']} ms, "
               f"p90 {r['ms_p90']} ms")
    avviso = ""
    if r["acuti"] and r["acuti_letti"] < r["acuti"]:
        avviso = (f" ⚠ {r['acuti'] - r['acuti_letti']} acuti da leggere "
                  "(calliope stato --guardia)")
    elif (r.get("falsi_settimana") or 0) >= 1:
        avviso = " ⚠ oltre un acuto falso a settimana: non accendere"
    out.append(f"  Acuti: {r['acuti']}, letti {r['acuti_letti']}, falsi {r['acuti_falsi']} "
               f"({r['falsi_settimana']} a settimana; obiettivo per accendere < 1)" + avviso)
    return "\n".join(out)


def elenco(r: dict, nomi: dict | None = None) -> str:
    """`calliope stato --guardia`: i segnali, senza parole, per la lettura di chi amministra."""
    nomi = nomi or {}
    out = ["Segnali del guardiano a posteriori (mai le parole: per leggerle, a voce «cosa ha "
           "detto … in … verso le …?», solo i tutori)"]
    if not r.get("elenco"):
        out.append("  nessun segnale")
        return "\n".join(out)
    for s in r["elenco"]:
        lett = r["letture"].get(str(s.get("id")))
        chi = ", ".join(nomi.get(m, m) for m in s.get("minori") or []) or "?"
        out.append(f"  {s.get('id')}  {str(s.get('t', ''))[:10]} {s.get('ora') or '??:??'}  "
                   f"{s.get('sat')}  {chi} ({s.get('modo_minore') or '?'})  "
                   f"{s.get('livello')} {s.get('categoria')}  contesto {s.get('contesto')}"
                   + (f"  filtro {s.get('motivo')}" if s.get("motivo") else "")
                   + (f"  avviso {s.get('avviso')}" if s.get("avviso") else "")
                   + (f"  letto: {lett}" if lett else ""))
    out.append("Per segnarne uno: calliope stato --guardia --falso ID (oppure --vero ID)")
    return "\n".join(out)
