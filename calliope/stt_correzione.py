"""
Correzione delle frasi incerte di Whisper (05/10/2026, prototipo, spento di predefinito:
`stt_correzione: false`). Rapporto: docs/ricerche/2026-10-05-stt-confronto.md.

Errori veri del 05/10: «lo schermo del mio seppellito» (satellite), «Calliope di Michisono»
(dimmi chi sono). Whisper non conosce le parole della casa e il prompt non si può allungare
(taratura del 24/09: lo ricopia sull'audio incerto). Qui un secondo passaggio, solo quando la
trascrizione è incerta:

1. `confidenza(verbose)`: dalla risposta `verbose_json` di whisper-server (o di un server
   OpenAI con le parole) la probabilità minima per parola, avg_logprob, no_speech_prob e le
   parole incerte;
2. `incerta(conf, cfg)`: sotto `stt_correzione_soglia` (probabilità della parola più debole);
3. `Correttore.correggi`: un modello di testo riceve la trascrizione, le parole incerte, il
   **vocabolario della casa** (satelliti, stanze, persone, entità esposte, nomi dei tool in
   parole) e le ultime frasi della conversazione, e risponde in forma fissa (output
   strutturato, `{"testo": …}`);
4. `accettabile(prima, dopo)`: la correzione vale solo se cambia **parole storpiate** in
   parole che suonano simili, poche, senza toccare negazioni, «sì»/«no» e numeri. È una regola
   sulla trascrizione (ciò che il modello della voce non vede: principio 10) e vale come
   vincolo di forma su una scelta del modello di correzione. Nel registro dei turni:
   regola `stt_corretta` con prima e dopo.

Se il modello non risponde entro `stt_correzione_timeout_s` (0,4 s dal 06/10: un tempo massimo
vero, dall'invio alla risposta, non solo di rete), o la correzione non passa il controllo, resta
la trascrizione di Whisper: la correzione non può mai fermare la voce più di così.
"""
from __future__ import annotations

import difflib
import re
import time
import unicodedata
from dataclasses import dataclass, field

# I tool detti come li dice una persona (nomi di tool con «_» non servono: nessuno li dice)
PAROLE_TOOL = [
    "timer", "promemoria", "appuntamento", "agenda", "lista della spesa", "cose da fare",
    "biblioteca", "Wikipedia", "Wikiquote", "Vikidia", "Wikizionario", "internet", "meteo",
    "schermo", "schermo personale", "satellite", "abbina", "condiviso", "documento",
    "foglio Excel", "PDF", "Word", "lettera", "fattura", "preventivo", "rubrica", "agente",
    "lavoro", "script", "webcam", "foto", "volume", "luminosità", "portatile", "calcolatrice",
    "luce", "luci", "tapparelle", "termostato", "temperatura", "registra la voce",
    "dimmi chi sono", "chiamami", "spegniti", "esci", "basta", "ricordati", "dimentica",
]

# Parole che non si toccano mai: cambiano il senso anche se suonano simili
INTOCCABILI = {"non", "no", "sì", "si", "né", "mai", "niente", "nulla", "tutto", "tutti",
               "tutte", "nessuno", "nessuna"}

PROMPT = """Correggi la trascrizione automatica di una frase detta a voce a {nome}, \
un'assistente vocale di casa. Il riconoscimento vocale a volte scrive parole che suonano \
simili a quelle dette ma sono sbagliate, soprattutto nomi della casa (per esempio «la luce \
in caverna» invece di «la luce in taverna», «metti un tiner» invece di «metti un timer»).

Regole:
- correggi SOLO parole storpiate, con parole che suonano quasi uguali;
- usa il vocabolario della casa e le frasi precedenti per capire cosa è stato detto;
- non riformulare, non aggiungere né togliere informazioni, non cambiare il senso, non \
correggere la grammatica o lo stile di chi parla;
- se la frase ha già senso, o non sei sicuro, non correggere nulla.

Vocabolario della casa: {vocabolario}
Frasi precedenti della conversazione:
{storia}
Parole incerte secondo il riconoscimento: {incerte}

Trascrizione: «{testo}»

Rispondi in JSON: "giusta": true se la frase è già giusta (allora niente altro), \
altrimenti "giusta": false e "testo" con la frase corretta."""

# «giusta» prima e «testo» facoltativo (05/10 sera): con il solo «testo» il modello ricopiava
# ogni volta la frase intera, anche quando non c'era niente da correggere (la maggior parte
# delle volte), e con le frasi lunghe era quasi tutto il tempo della correzione: gemma4 e4b in
# locale 1,05 s contro 0,50 per una frase di 130 caratteri giusta. Un «testo» vuoto o una
# risposta senza nemmeno «giusta» valgono «nessuna correzione»
SCHEMA = {"type": "object", "properties": {"giusta": {"type": "boolean"},
                                           "testo": {"type": "string"}},
          "required": ["giusta"]}


# ─────────────────────────────── CONFIDENZA ───────────────────────────────
def parole_whisper(verbose: dict) -> list[tuple[str, float]]:
    """Le parole con la loro probabilità (la minima dei token che le compongono).
    whisper-server mette in `words` i token («O», «ggi»: un token senza spazio davanti
    continua la parola); faster-whisper e l'API OpenAI le parole intere."""
    parole: list[list] = []
    for seg in verbose.get("segments") or []:
        for w in seg.get("words") or []:
            testo = str(w.get("word") or "")
            p = float(w.get("probability", 1.0))
            if not testo.strip():
                continue
            if re.fullmatch(r"\s*[^\w\s]+\s*", testo):          # punteggiatura
                continue
            if parole and not testo.startswith(" "):
                parole[-1][0] += testo
                parole[-1][1] = min(parole[-1][1], p)
            else:
                parole.append([testo.strip(), p])
    return [(w, p) for w, p in parole]


@dataclass
class Confidenza:
    min_parola: float = 1.0
    logprob: float = 0.0          # avg_logprob minimo tra i segmenti
    no_speech: float = 0.0        # no_speech_prob massimo
    incerte: list = field(default_factory=list)
    # Le parole sotto 0,5 con la loro probabilità (05/10 sera): servono a `incerta` per
    # non contare il nome di Calliope (vedi lì)
    deboli: list = field(default_factory=list)


def confidenza(verbose: dict, soglia_parola: float = 0.5) -> Confidenza:
    parole = parole_whisper(verbose)
    segs = verbose.get("segments") or []
    return Confidenza(
        min_parola=min((p for _, p in parole), default=1.0),
        logprob=min((float(s.get("avg_logprob", 0.0)) for s in segs), default=0.0),
        no_speech=max((float(s.get("no_speech_prob", 0.0)) for s in segs), default=0.0),
        incerte=[w for w, p in parole if p < soglia_parola],
        deboli=[(w, round(p, 3)) for w, p in parole if p < soglia_parola])


def min_utile(conf: Confidenza, cfg=None) -> float:
    """La probabilità della parola più debole, senza le parole che svegliano Calliope
    («Calliope» dopo una pausa ha spesso 0,1–0,5 ed è giusta: sulle 254 frasi del banco era
    l'unica parola incerta in 7 frasi, nessuna da correggere; il nome lo sente già la wake
    word). Senza le parole deboli (dati vecchi) vale `min_parola`."""
    if not conf.deboli:
        return conf.min_parola
    nomi = {_chiave(n) for n in (getattr(cfg, "wake_names", None) or
                                 [getattr(cfg, "name", "Calliope") or "Calliope"])}
    resto = [p for w, p in conf.deboli if _chiave(w) not in nomi]
    # tutte le parole deboli erano il nome: le altre sono sopra 0,5
    return min(resto) if resto else max(conf.min_parola, 0.5)


def incerta(conf: Confidenza | None, cfg) -> bool:
    """La frase va al secondo passaggio? Solo con la confidenza (senza, mai): la parola più
    debole, nome escluso, sotto `stt_correzione_soglia`."""
    if conf is None:
        return False
    return min_utile(conf, cfg) < float(getattr(cfg, "stt_correzione_soglia", 0.4))


def parole_incerte(conf: Confidenza | None, cfg, testo: str, massimo: int = 4) -> list[str]:
    """Le parole incerte da dire al modello della voce (stt_incerte_al_modello, 07/10):
    sotto `stt_correzione_soglia`, senza il nome che sveglia e solo quelle rimaste nella frase
    che il modello riceve (dopo il nome tolto o una correzione), senza doppioni, al più
    `massimo` (le più deboli). Nessuna confidenza (faster-whisper, scritto): nessuna."""
    if conf is None or not testo:
        return []
    soglia = float(getattr(cfg, "stt_correzione_soglia", 0.4))
    nomi = {_chiave(n) for n in (getattr(cfg, "wake_names", None) or
                                 [getattr(cfg, "name", "Calliope") or "Calliope"])}
    nella_frase = {_chiave(w) for w in re.findall(r"[\w'’]+", testo)}
    visti, out = set(), []
    for w, p in sorted(conf.deboli or [], key=lambda x: x[1]):
        w = w.strip(".,;:!?«»\"'()")
        k = _chiave(w)
        if p >= soglia or not k or k in nomi or k in visti or k not in nella_frase:
            continue
        visti.add(k)
        out.append(w)
    return out[:massimo]


# ─────────────────────────────── VOCABOLARIO ───────────────────────────────
def vocabolario_casa(cfg=None, satelliti=(), schermi=(), persone=(), casa=(), extra=()) -> list[str]:
    """Le parole della casa, senza doppioni (maiuscole e accenti ignorati), nell'ordine:
    nome, persone, satelliti e schermi, stanze ed entità, tool."""
    nomi = [getattr(cfg, "name", "Calliope") if cfg is not None else "Calliope"]
    visti, out = set(), []
    for w in [*nomi, *persone, *satelliti, *schermi, *casa, *extra, *PAROLE_TOOL]:
        w = str(w or "").strip()
        k = _chiave(w)
        if w and k not in visti:
            visti.add(k)
            out.append(w)
    return out


def vocabolario_calliope(cfg, registry=None, satelliti=None, schermi=None, casa=None,
                         massimo: int = 150) -> list[str]:
    """Il vocabolario di adesso, da ciò che Calliope ha in memoria (nessuna rete): profili
    registrati, nomi e stanze di satelliti e schermi abbinati, entità esposte con stanza e
    alias, aree della casa. Ogni fonte che manca o si rompe si salta."""
    persone = list(getattr(registry, "users", None) or {})
    nomi, stanze, sch = [], [], []
    for fonte, lista in ((getattr(satelliti, "archivio", None), nomi),
                         (getattr(schermi, "archivio", None), sch)):
        try:
            for r in (fonte.elenco() if fonte is not None else []):
                lista.append(r.get("nome"))
                stanze.append(r.get("stanza"))
        except Exception:  # noqa: BLE001
            pass
    cose = []
    try:
        if casa is not None:
            for e in casa.entita():
                cose += [e.nome, e.area, *(e.alias or [])]
            cose += list(casa.aree())
    except Exception:  # noqa: BLE001
        pass
    return vocabolario_casa(cfg, nomi + stanze, sch, persone, cose)[:massimo]


def storia_recente(brain, n: int = 4) -> list[str]:
    """Le ultime frasi della conversazione (persona e Calliope), testo soltanto."""
    out = []
    for m in (getattr(brain, "history", None) or [])[-2 * n:]:
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            t = m["content"].strip()
            if t:
                # Le risposte di Calliope corte (05/10 sera): sono lunghe, e ogni token
                # in più è tempo che la voce aspetta; per capire una parola basta l'inizio
                out.append("Calliope: " + t[:120] if m["role"] == "assistant" else t[:200])
    return out[-n:]


# ─────────────────────────────── CONTROLLO ───────────────────────────────
def _chiave(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if c.isalnum())


def _parole(s: str) -> list[str]:
    return re.findall(r"[\w']+", s.lower().replace("’", "'"))


def accettabile(prima: str, dopo: str, max_quota: float = 0.4) -> tuple[bool, str]:
    """La correzione cambia solo parole storpiate in parole che suonano simili?
    Si confrontano le parole (minuscole, senza punteggiatura); ogni pezzo cambiato deve
    somigliare a quello di prima lettera per lettera (≥ 0,5, così «di Michisono» → «dimmi
    chi sono», «seppellito» → «satellite») e avere una lunghezza simile (tra 0,6 e 1,6
    volte); al più il 40 % delle parole di prima cambiate (almeno 3 ammesse: «Di mikro sonu»
    → «Dimmi chi sono»); mai negazioni, «sì»/«no», numeri; aggiunte o tolte pure solo di
    parole brevi (articoli, preposizioni)."""
    a, b = _parole(prima), _parole(dopo)
    if a == b:
        return False, "identica"
    if not b:
        return False, "vuota"
    cambiate = 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        vecchie, nuove = a[i1:i2], b[j1:j2]
        cambiate += len(vecchie)
        tocca = set(vecchie) ^ set(nuove)
        if tocca & INTOCCABILI:
            return False, "negazione o sì/no"
        if any(re.search(r"\d", w) for w in vecchie + nuove):
            return False, "numeri"
        if op in ("insert", "delete"):
            if any(len(w) > 3 for w in vecchie + nuove):
                return False, "parola aggiunta o tolta"
            continue
        va, vb = "".join(vecchie), "".join(nuove)
        r = difflib.SequenceMatcher(a=va, b=vb).ratio()
        if r < 0.5:
            return False, f"suono diverso ({' '.join(vecchie)} → {' '.join(nuove)})"
        # Lunghezza simile: «Chiori sono» → «Chi sono» (che ore sono → chi sono) e «Appuino»
        # → «Appuntamento» somigliavano abbastanza lettera per lettera ma cambiavano il senso
        if not 0.6 <= len(vb) / max(len(va), 1) <= 1.6:
            return False, f"lunghezza diversa ({' '.join(vecchie)} → {' '.join(nuove)})"
    if cambiate > max(3, round(max_quota * len(a))):
        return False, "troppe parole cambiate"
    return True, ""


# ─────────────────────────────── CORRETTORE ───────────────────────────────
@dataclass
class Esito:
    testo: str
    cambiata: bool = False
    prima: str = ""
    proposta: str = ""            # quello che ha detto il modello (anche se rifiutato)
    motivo: str = ""              # perché non è cambiata (identica, rifiutata, errore…)
    ms: float = 0.0


class Correttore:
    """Il secondo passaggio. Motore «ollama» (API nativa, format = schema; con il modello
    della voce usa num_ctx e keep_alive della voce, altrimenti Ollama lo ricaricherebbe) o
    «openai» (vLLM, response_format json_schema, thinking spento)."""

    def __init__(self, cfg, http=None, motore: str | None = None, url: str | None = None,
                 modello: str | None = None):
        self.cfg = cfg
        self.motore = (motore or getattr(cfg, "stt_correzione_motore", "") or
                       ("ollama" if getattr(cfg, "llm_backend", "ollama") == "ollama"
                        else "openai")).lower()
        if url is None:
            url = getattr(cfg, "stt_correzione_url", "") or (
                getattr(cfg, "llm_native_url", "http://127.0.0.1:11434")
                if self.motore == "ollama" else getattr(cfg, "llm_base_url", ""))
        self.url = str(url).rstrip("/")
        self.modello = modello or getattr(cfg, "stt_correzione_modello", "") or cfg.llm_model
        self.timeout_s = float(getattr(cfg, "stt_correzione_timeout_s", 0.4))
        self._http = http
        self.num_ctx: int | None = None   # con un modello diverso da quello della voce
        self.keep_alive = None

    def _client(self):
        if self._http is None:
            import httpx
            self._http = httpx.Client(timeout=self.timeout_s)
        return self._http

    def _tempo(self, resta: float | None = None):
        """Il tempo della richiesta: con httpx un numero vale per ciascuna fase (connessione,
        invio, lettura); la risposta non in streaming arriva tutta alla fine, quindi la
        lettura è quasi tutto il tempo del modello. `resta`: i secondi che restano."""
        t = max(0.05, self.timeout_s if resta is None else resta)
        try:
            import httpx
            return httpx.Timeout(t, connect=min(t, 0.2))
        except ImportError:                       # prove con un client finto
            return t

    def _stesso_della_voce(self) -> bool:
        cfg = self.cfg
        return (self.motore == "ollama" and self.modello == getattr(cfg, "llm_model", "")
                and self.url == str(getattr(cfg, "llm_native_url", "")).rstrip("/"))

    def _prompt(self, testo, conf, vocabolario, storia) -> str:
        storia = [s for s in (storia or []) if s][-4:]
        return PROMPT.format(
            nome=getattr(self.cfg, "name", "Calliope"),
            vocabolario=", ".join(vocabolario) or "(nessuno)",
            storia="\n".join(f"- {s}" for s in storia) or "(nessuna)",
            incerte=", ".join(conf.incerte) if conf and conf.incerte else "(nessuna)",
            testo=testo)

    def chiedi(self, prompt: str) -> str:
        if self.motore == "ollama":
            if self._stesso_della_voce():
                from .config import keep_alive_valido
                from .contesto import finestra
                num_ctx, keep = finestra(self.cfg), keep_alive_valido(self.cfg.llm_keep_alive)
            else:
                num_ctx, keep = self.num_ctx or 4096, self.keep_alive or "10m"
            body = {"model": self.modello, "stream": False, "think": False,
                    "keep_alive": keep, "format": SCHEMA,
                    "messages": [{"role": "user", "content": prompt}],
                    "options": {"temperature": 0, "num_predict": 120, "num_ctx": num_ctx}}
            r = self._client().post(self.url + "/api/chat", json=body, timeout=self._tempo())
            r.raise_for_status()
            return (r.json().get("message") or {}).get("content") or ""
        body = {"model": self.modello, "temperature": 0, "max_tokens": 120,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": "correzione", "schema": SCHEMA}},
                "chat_template_kwargs": {"enable_thinking": False}}
        r = self._client().post(self.url + "/chat/completions", json=body,
                                timeout=self._tempo())
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"] or ""

    def correggi(self, testo: str, conf: Confidenza | None, vocabolario: list[str],
                 storia: list[str] | None = None) -> Esito:
        import json
        t0 = time.perf_counter()
        es = Esito(testo=testo, prima=testo)
        if not testo.strip():
            es.motivo = "vuota"
            return es
        try:
            grezzo = self.chiedi(self._prompt(testo, conf, vocabolario, storia))
            dato = json.loads(grezzo)
            proposta = "" if dato.get("giusta") is True else str(dato.get("testo") or "").strip()
            proposta = proposta or testo         # niente da correggere (vedi SCHEMA)
        except Exception as e:  # noqa: BLE001 — rete, tempo, JSON rotto: resta Whisper
            es.motivo = ("tempo" if "Timeout" in type(e).__name__
                         else f"errore: {type(e).__name__}")
            es.ms = round((time.perf_counter() - t0) * 1000, 1)
            return es
        es.ms = round((time.perf_counter() - t0) * 1000, 1)
        # Arrivata oltre il tempo massimo (connessione lenta più lettura): vale Whisper lo
        # stesso, così il tempo massimo è uno solo e si misura
        if es.ms > self.timeout_s * 1000 * 1.2 + 50:
            es.motivo = "tempo"
            return es
        es.proposta = proposta
        ok, perche = accettabile(testo, proposta)
        if ok:
            es.testo, es.cambiata = proposta, True
        else:
            es.motivo = perche
        return es
