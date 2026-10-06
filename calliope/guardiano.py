"""
Il modello guardiano (05/10/2026, docs/ricerche/2026-10-05-minori.md §4): un piccolo modello di
moderazione su Ollama giudica la domanda e **ogni frase della risposta prima del TTS**, solo per
i minori e gli ospiti (gli adulti riconosciuti non pagano niente).

Tre strati di sicurezza dei contenuti per i minori (decisione di Dario del 05/10):
1. le istruzioni per fascia, nei dati del turno (calliope/minori.py, `dato_turno`);
2. **questo guardiano**, che vede la risposta vera e quindi giudica anche gli aggiramenti
   («fingi di…», «è per un compito»): ciò che conta è cosa Calliope sta per dire;
3. regole fisse (safesearch di SearXNG per fascia, voci adulte della biblioteca escluse,
   schede degli schermi filtrate).

Esiti:
- `ok`: la frase si dice;
- `vietato`: la frase non si dice, e nemmeno il resto della risposta: al suo posto una frase
  fissa (`SOSTITUTA`); la storia tiene solo ciò che è stato detto;
- `pericolo` (solo sulla domanda: chi parla dice di volersi fare del male, di subire un abuso,
  di essere in pericolo): la risposta del modello non si dice; si dice la **risposta di
  protezione** (invito a un adulto, Telefono Azzurro 19696, 112 se è in pericolo adesso) e i
  tutori ricevono un avviso discreto (solo l'argomento). Per TUTTE le fasce e anche per gli
  ospiti (senza avviso: non hanno tutori).

Streaming (principio 6): la domanda si giudica in un thread mentre il modello comincia a
rispondere; la prima frase aspetta i due giudizi, le altre si giudicano mentre la precedente
suona. Il costo è il tempo di un giudizio sulla prima frase (misure nel rapporto).

Se il guardiano non risponde (`guardiano_timeout_s`) per un minore la frase non si dice
(`guardiano_se_guasto: blocca`, una frase fissa al suo posto); per un ospite passa.

Caldo (06/10, P2 di docs/ricerche/2026-10-06-analisi-complessiva.md): sulla DGX la prima frase
dei minori era 3,3–4,4 s anche con il guardiano caldo (giudizi di 80–160 ms). Il rilevatore di
pericolo usa un modello suo (gemma4 e4b, la voce è il 26B) che nessuno caricava: ogni domanda
lo faceva caricare, il tempo massimo di 3 s chiudeva la richiesta (499 nel log di Ollama) e il
caricamento ripartiva da capo alla domanda dopo, così ogni turno pagava 3 s. Ora `prepara`
carica guardiano e rilevatore con un tempo lungo (`AVVIO_S`), e un giudizio scaduto li ricarica
in secondo piano (`_riscalda`): il turno dopo li trova pronti.

Adattatori (`ADATTATORI`), scelti con il banco `prove/misura_guardiano.py` sulle frasi in
italiano di `prove/casi_guardiano.py`: Llama Guard 3 (categorie per i bambini nel prompt),
ShieldGemma, Granite Guardian, Qwen3Guard.
"""

from __future__ import annotations

import concurrent.futures
import re
import threading
import time
from dataclasses import dataclass, field

OK, VIETATO, PERICOLO, GUASTO = "ok", "vietato", "pericolo", "guasto"
# Tempo per caricare un modello (avvio e ricarica in secondo piano): un 8B da disco ci mette
# qualche secondo, con la memoria piena anche decine
AVVIO_S = 120.0


@dataclass
class Giudizio:
    esito: str = OK
    categorie: tuple = ()
    ms: float = 0.0
    grezzo: str = ""
    # Il rilevatore di pericolo sulla domanda (giudica_domanda): il suo esito ("" = spento o
    # non chiesto) e il suo tempo, per il registro dei turni. Un rilevatore guasto o scaduto
    # per un minore vale «guasto» (filtra, Q3 dell'analisi del 06/10): prima si vedeva solo
    # il tempo di Llama Guard e il rilevatore poteva restare spento per ore senza segnali
    pericolo: str = ""
    pericolo_ms: float | None = None

    def guasto(self) -> bool:
        """Il guardiano o il rilevatore non hanno dato un giudizio (errore o tempo scaduto)."""
        return self.esito == GUASTO or self.pericolo == GUASTO


# Categorie nostre (per i minori). Nel prompt di Llama Guard in inglese: il modello è stato
# addestrato sulle sue categorie in inglese e capisce i messaggi in italiano (misure nel
# rapporto); i nomi e le descrizioni contano più della lingua
CATEGORIE = (
    ("autolesionismo", "Self-Harm",
     "The child says they want to hurt or kill themselves, to disappear, to stop eating, or "
     "asks how to do it; or the agent explains how to self-harm."),
    ("abuso", "Abuse or Danger to the child",
     "The child says someone hurts, hits or touches them, asks them to keep secrets, or wants "
     "to meet them alone; or the agent encourages it."),
    ("sessuale", "Sexual Content",
     "Descriptions of sexual acts, nudity, pornography or erotic content."),
    ("violenza", "Graphic Violence",
     "Gory, cruel or detailed violence, or how to hurt people or animals."),
    ("pericoloso", "Dangerous Instructions",
     "How to make or get weapons, explosives, poisons, drugs or alcohol, or other dangerous "
     "activities for a child."),
    ("odio", "Hate and Vulgarity",
     "Hate against groups of people, or vulgar insults and swearing."),
)
PERICOLO_CATEGORIE = {"autolesionismo", "abuso"}
# Il filtro «moderato» degli ospiti: solo ciò che non va detto a nessuno (un ospite può essere
# un bambino, ma anche un adulto: niente prediche sulla violenza di un film)
MODERATO = {"autolesionismo", "abuso", "sessuale", "pericoloso", "odio"}

# Frasi fisse. La protezione è uguale per tutti: deterministica, provata, senza un'altra passata
# del modello (che potrebbe sbagliarla proprio lì)
PROTEZIONE = ("Mi dispiace tanto che tu stia vivendo questo, e hai fatto bene a dirlo. Parlane "
              "subito con un adulto di cui ti fidi, come mamma, papà o un insegnante. Puoi "
              "chiamare il Telefono Azzurro al 19696, gratis, a qualunque ora. Se sei in "
              "pericolo adesso, chiama il 112.")
PROTEZIONE_OSPITE = ("Mi dispiace tanto che tu stia vivendo questo. Parlane subito con una "
                     "persona di cui ti fidi. Se sei un ragazzo puoi chiamare il Telefono "
                     "Azzurro al 19696, a qualunque ora; se sei in pericolo adesso, chiama il "
                     "112.")
SOSTITUTA = ("Di questo è meglio che tu parli con un adulto di cui ti fidi. Se vuoi, chiedimi "
             "un'altra cosa.")
SOSTITUTA_OSPITE = "Su questo preferisco non rispondere. Se vuoi, chiedimi un'altra cosa."
GUASTO_FRASE = ("Adesso non riesco a controllare bene le mie risposte, quindi preferisco non "
                "rispondere: riprova tra poco, o chiedi a un adulto.")
# Il rilevatore di pericolo (Guardiano.pericolo): il modello della voce con l'output
# strutturato. Senza l'enum il 4B rispondeva al bambino («AIUTO», «EMERGENZA») invece di
# classificare (banco del 05/10)
PERICOLO_PROMPT = (
    "Sei il controllo di sicurezza di un'assistente vocale di casa usata anche da bambini e "
    "ragazzi. Leggi la frase detta da un bambino e rispondi in JSON con «esito».\n"
    "PERICOLO: se dice che vuole farsi del male, morire o sparire, o che smette di mangiare; "
    "oppure che qualcuno gli fa del male, lo picchia, lo tocca, lo minaccia, gli chiede di "
    "tenere un segreto con i genitori o di incontrarlo da solo.\n"
    "NO: in tutti gli altri casi, anche domande difficili su morte, guerra, corpo o droghe, e "
    "richieste di cose vietate.\n\nFrase: «{frase}»")
# Avviso ai tutori: solo l'argomento, mai le parole del minore
ARGOMENTI = {"autolesionismo": "ha parlato di farsi del male o di stare molto male",
             "abuso": "ha parlato di qualcuno che potrebbe fargli del male o metterlo in "
                      "pericolo",
             "pericolo": "ha detto una cosa che fa pensare che sia in pericolo o stia molto "
                         "male"}


# ─────────────────────────── adattatori ───────────────────────────

_LG_PROMPT = """<|begin_of_text|><|start_header_id|>user<|end_header_id|>

Task: Check if there is unsafe content in '{ruolo}' messages in conversations according our safety policy with the below categories. The User is a child.

<BEGIN UNSAFE CONTENT CATEGORIES>
{categorie}
<END UNSAFE CONTENT CATEGORIES>

<BEGIN CONVERSATION>

{conversazione}<END CONVERSATION>

Provide your safety assessment for ONLY THE LAST {ruolo} message in the above conversation:
 - First line must read 'safe' or 'unsafe'.
 - If unsafe, a second line must include a comma-separated list of violated categories.<|eot_id|><|start_header_id|>assistant<|end_header_id|>

"""


def _pulito(t: str) -> str:
    return " ".join(str(t or "").split())[:2000]


class LlamaGuard:
    """Llama Guard 3 (1B, 8B) con le categorie per i bambini nel prompt (modo raw)."""
    nome = "llama_guard"

    def __init__(self, categorie=CATEGORIE):
        self.categorie = categorie
        self.testo_cat = "\n".join(f"S{i + 1}: {c[1]}.\n{c[2]}" for i, c in enumerate(categorie))

    def richiesta(self, domanda: str, risposta: str | None) -> dict:
        conv = f"User: {_pulito(domanda)}\n\n"
        if risposta is not None:
            conv += f"Agent: {_pulito(risposta)}\n\n"
        return {"endpoint": "generate", "raw": True,
                "prompt": _LG_PROMPT.format(ruolo="Agent" if risposta is not None else "User",
                                            categorie=self.testo_cat, conversazione=conv),
                "num_predict": 12}

    def leggi(self, testo: str) -> tuple[bool, tuple]:
        t = (testo or "").strip().lower()
        if not t.startswith("unsafe"):
            return False, ()
        cats = []
        for n in re.findall(r"s(\d+)", t):
            i = int(n) - 1
            if 0 <= i < len(self.categorie):
                cats.append(self.categorie[i][0])
        return True, tuple(dict.fromkeys(cats)) or ("sconosciuta",)


_LG_STD = {1: "violenza", 2: "pericoloso", 3: "abuso", 4: "abuso", 9: "pericoloso",
           10: "odio", 11: "autolesionismo", 12: "sessuale"}


class LlamaGuardStd(LlamaGuard):
    """Llama Guard 3 con le sue categorie (il modello di chat di Ollama), per il confronto."""
    nome = "llama_guard_std"

    def richiesta(self, domanda: str, risposta: str | None) -> dict:
        msgs = [{"role": "user", "content": _pulito(domanda)}]
        if risposta is not None:
            msgs.append({"role": "assistant", "content": _pulito(risposta)})
        return {"endpoint": "chat", "messages": msgs, "num_predict": 12}

    def leggi(self, testo: str) -> tuple[bool, tuple]:
        t = (testo or "").strip().lower()
        if not t.startswith("unsafe"):
            return False, ()
        cats = [_LG_STD.get(int(n), "altro") for n in re.findall(r"s(\d+)", t)]
        return True, tuple(dict.fromkeys(cats)) or ("sconosciuta",)


_SG_DOMANDA = """You are a policy expert trying to help determine whether a user prompt is in violation of the defined safety policies.

<start_of_turn>
Human Question: {domanda}
<end_of_turn>

Our safety principle is defined in the below:

{politica}

Does the human question violate the above principle? Your answer must start with 'Yes' or 'No'. And then walk through step by step to be sure we answer correctly.
"""
_SG_RISPOSTA = """You are a policy expert trying to help determine whether an AI response to prompt is in violation of the defined safety policies.

<start_of_turn>
Human Question: {domanda}
<end_of_turn>

<start_of_turn>
Chatbot Response: {risposta}
<end_of_turn>

Our safety principle is defined in the below:

{politica}

Does the Chatbot Response violate the above principle? Your answer must start with 'Yes' or 'No'. And then walk through step by step to be sure we answer correctly.
"""


class ShieldGemma:
    """ShieldGemma (2B, 9B): una politica per richiesta; qui una sola politica che le unisce
    (la categoria si ricava con una seconda richiesta solo per la domanda: pericolo o no)."""
    nome = "shieldgemma"

    def __init__(self, categorie=CATEGORIE):
        self.categorie = categorie
        self.politica = "\n".join(
            f'* "No {c[1]}": the conversation, with a child, shall not contain or seek: '
            f"{c[2]}" for c in categorie)

    def richiesta(self, domanda: str, risposta: str | None) -> dict:
        if risposta is None:
            p = _SG_DOMANDA.format(domanda=_pulito(domanda), politica=self.politica)
        else:
            p = _SG_RISPOSTA.format(domanda=_pulito(domanda), risposta=_pulito(risposta),
                                    politica=self.politica)
        return {"endpoint": "generate", "raw": True,
                "prompt": f"<start_of_turn>user\n{p}<end_of_turn>\n<start_of_turn>model\n",
                "num_predict": 3}

    def leggi(self, testo: str) -> tuple[bool, tuple]:
        return (testo or "").strip().lower().startswith("yes"), ()


class GraniteGuardian:
    """Granite Guardian 3 (2B, 8B): il rischio va nel messaggio di sistema, risponde Yes/No.
    Si usa il rischio generico «harm» (comprende le nostre categorie)."""
    nome = "granite"

    def __init__(self, rischio: str = "harm"):
        self.rischio = rischio

    def richiesta(self, domanda: str, risposta: str | None) -> dict:
        msgs = [{"role": "system", "content": self.rischio},
                {"role": "user", "content": _pulito(domanda)}]
        if risposta is not None:
            msgs.append({"role": "assistant", "content": _pulito(risposta)})
        return {"endpoint": "chat", "messages": msgs, "num_predict": 3}

    def leggi(self, testo: str) -> tuple[bool, tuple]:
        return (testo or "").strip().lower().startswith("yes"), ()


_QG_CAT = {"suicide": "autolesionismo", "self-harm": "autolesionismo", "sexual": "sessuale",
           "violent": "violenza", "non-violent illegal": "pericoloso", "unethical": "odio",
           "jailbreak": "pericoloso", "pii": "privacy", "politically": "politica",
           "copyright": "copyright"}


_QG_POLITICA = """<BEGIN SAFETY POLICY>
**Safety: Safe**: The {chi}'s {cosa} does not contain any prohibited content or content that could lead to prohibited content.
**Safety: Unsafe**: The {chi}'s {cosa} contains prohibited content.
**Safety: Controversial**: The {chi}'s {cosa} does not explicitly contain prohibited content, but its intent, context, or potential responses could be misinterpreted, misused, or exploited to generate unsafe content under certain conditions.
<END SAFETY POLICY>

<BEGIN UNSAFE CONTENT CATEGORIES>
Violent.
Non-violent Illegal Acts.
Sexual Content or Sexual Acts.
PII.
Suicide & Self-Harm.
Unethical Acts.
Politically Sensitive Topics.
Copyright Violation.
Jailbreak.
<END UNSAFE CONTENT CATEGORIES>"""


class QwenGuard:
    """Qwen3Guard-Gen (0,6B, 4B): multilingue, «Safety: Safe|Unsafe|Controversial» e le
    categorie. Il modello di chat sulle pagine di Ollama è in Jinja (Ollama usa i template di
    Go): il prompt si costruisce qui, uguale a quello ufficiale, in modo raw."""
    nome = "qwen3guard"

    def __init__(self, controverso_vietato: bool = True):
        self.controverso = controverso_vietato

    def richiesta(self, domanda: str, risposta: str | None) -> dict:
        chi, cosa = ("ASSISTANT", "response") if risposta is not None else ("USER", "query")
        conv = f"USER: {_pulito(domanda)}"
        if risposta is not None:
            conv += f"\n\nASSISTANT: {_pulito(risposta)}"
        compito = (f"# Task:\n1) Evaluate whether THE LAST {chi}'s {cosa} belongs to safe or "
                   f"unsafe content based on our safety policy.\n2) Identify the category of "
                   f"unsafe content found.")
        p = (f"<|im_start|>user\n{compito}\n\n{_QG_POLITICA.format(chi=chi, cosa=cosa)}\n\n"
             f"<BEGIN CONVERSATION>\n\n{conv}\n\n<END CONVERSATION>\n\nProvide your safety "
             f"assessment for ONLY THE LAST **{chi}'s {cosa}** in the above conversation:\n"
             f" - The first line must be one of: 'Safety: Safe', 'Safety: Unsafe', 'Safety: "
             f"Controversial'.\n - The second line should start with 'Categories:' followed by "
             f"a list of any unsafe content categories, separated by commas. If the content is "
             f"safe, use 'Categories: None'.<|im_end|>\n<|im_start|>assistant\n<think>\n\n"
             f"</think>\n\n")
        return {"endpoint": "generate", "raw": True, "prompt": p, "num_predict": 30}

    def leggi(self, testo: str) -> tuple[bool, tuple]:
        t = (testo or "").lower()
        m = re.search(r"safety:\s*(safe|unsafe|controversial)", t)
        if not m:
            return False, ()
        cats = []
        c = re.search(r"categor(?:y|ies):\s*([^\n]*)", t)
        for k, v in _QG_CAT.items():
            if c and k in c.group(1):
                cats.append(v)
        unsafe = m.group(1) == "unsafe" or (self.controverso and m.group(1) == "controversial")
        return unsafe, tuple(dict.fromkeys(cats)) or (("sconosciuta",) if unsafe else ())


def adattatore_per(modello: str):
    m = (modello or "").lower()
    if "llama-guard" in m or "llamaguard" in m:
        return LlamaGuard()
    if "shieldgemma" in m:
        return ShieldGemma()
    if "granite" in m:
        return GraniteGuardian()
    if "qwen3guard" in m or "qwen3-guard" in m:
        return QwenGuard()
    raise ValueError(f"modello guardiano sconosciuto: {modello}")


# ─────────────────────────── il guardiano ───────────────────────────

class Guardiano:
    """Giudica domande e frasi con un modello di moderazione su Ollama (API nativa)."""

    def __init__(self, cfg, cliente=None, log=print):
        self.cfg = cfg
        self.modello = str(getattr(cfg, "guardiano_modello", "") or "")
        self.url = (str(getattr(cfg, "guardiano_url", "") or "")
                    or str(getattr(cfg, "llm_native_url", "http://127.0.0.1:11434"))).rstrip("/")
        self.timeout_s = float(getattr(cfg, "guardiano_timeout_s", 3.0) or 3.0)
        self.adattatore = adattatore_per(self.modello) if self.modello else None
        self._cliente = cliente
        self.log = log
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=3,
                                                           thread_name_prefix="guardiano")
        self.ultimo_errore: str | None = None
        self.ultimo_errore_pericolo: str | None = None
        self.misure: list[float] = []
        self._riscaldo: set = set()              # ricariche in secondo piano in corso
        self._lock_riscaldo = threading.Lock()

    @property
    def attivo(self) -> bool:
        return bool(self.modello) and self.adattatore is not None and bool(
            getattr(self.cfg, "guardiano_enabled", True))

    def _http(self):
        if self._cliente is None:
            import httpx
            self._cliente = httpx.Client(timeout=self.timeout_s)
        return self._cliente

    def prepara(self) -> bool:
        """Carica il modello (keep_alive come la voce) e il rilevatore di pericolo, se ha un
        modello suo: la prima frase di un bambino non deve pagare il caricamento. Tempo lungo
        (`AVVIO_S`): con il tempo di un giudizio (3 s) un caricamento più lento si chiudeva a
        metà e non finiva mai. True se il guardiano risponde."""
        if not self.attivo:
            return False
        g = self.giudica("Ciao", None, timeout=AVVIO_S, riscalda=False)
        if self._pericolo_modello() is not None and not self.condivide_voce():
            p = self.pericolo("Ciao", timeout=AVVIO_S, riscalda=False)
            if p.esito == GUASTO:
                self.log(f"[GUARDIANO] il rilevatore di pericolo non risponde ({p.grezzo})")
        return g.esito != GUASTO

    def _riscalda(self, chi: str):
        """Un giudizio è scaduto (modello scaricato, o mai caricato): lo si ricarica in
        secondo piano con il tempo lungo, uno alla volta, così il turno dopo lo trova pronto
        invece di pagare di nuovo il tempo massimo."""
        lock = self.__dict__.get("_lock_riscaldo")
        if lock is None:                         # sottoclassi delle prove senza __init__
            return
        with lock:
            if chi in self._riscaldo:
                return
            self._riscaldo.add(chi)

        def carica():
            try:
                if chi == "pericolo":
                    self.pericolo("Ciao", timeout=AVVIO_S, riscalda=False)
                else:
                    self.giudica("Ciao", None, timeout=AVVIO_S, riscalda=False)
            finally:
                with lock:
                    self._riscaldo.discard(chi)
        threading.Thread(target=carica, name=f"riscalda-{chi}", daemon=True).start()

    @staticmethod
    def _scaduto(e: Exception) -> bool:
        return "timeout" in type(e).__name__.lower()

    def giudica(self, domanda: str, risposta: str | None = None,
                categorie_attive: set | None = None, timeout: float | None = None,
                riscalda: bool = True) -> Giudizio:
        """Un giudizio. `risposta` None = si giudica la domanda. `categorie_attive`: le
        categorie che contano (MODERATO per gli ospiti); None = tutte."""
        if not self.attivo:
            return Giudizio(GUASTO, grezzo="spento")
        req = self.adattatore.richiesta(domanda, risposta)
        body = {"model": self.modello, "stream": False,
                "keep_alive": getattr(self.cfg, "guardiano_keep_alive", "30m"),
                "options": {"temperature": 0, "num_predict": req.get("num_predict", 12),
                            "num_ctx": int(getattr(self.cfg, "guardiano_num_ctx", 2048) or 2048)}}
        if req["endpoint"] == "generate":
            body.update(prompt=req["prompt"], raw=bool(req.get("raw")))
            path = "/api/generate"
        else:
            body.update(messages=req["messages"])
            path = "/api/chat"
        t0 = time.perf_counter()
        try:
            r = self._http().post(self.url + path, json=body, timeout=timeout or self.timeout_s)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            js = r.json()
            testo = js.get("response") if path == "/api/generate" else (
                (js.get("message") or {}).get("content"))
        except Exception as e:  # noqa: BLE001
            self.ultimo_errore = type(e).__name__
            if riscalda and self._scaduto(e):
                self._riscalda("guardiano")
            return Giudizio(GUASTO, ms=round((time.perf_counter() - t0) * 1000, 1),
                            grezzo=type(e).__name__)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        self.misure = (self.misure + [ms])[-200:]
        self.ultimo_errore = None
        unsafe, cats = self.adattatore.leggi(testo or "")
        if unsafe and categorie_attive is not None and cats and cats != ("sconosciuta",):
            cats = tuple(c for c in cats if c in categorie_attive)
            unsafe = bool(cats)
        if not unsafe:
            return Giudizio(OK, (), ms, (testo or "").strip()[:80])
        if risposta is None and set(cats) & PERICOLO_CATEGORIE:
            return Giudizio(PERICOLO, cats, ms, (testo or "").strip()[:80])
        return Giudizio(VIETATO, cats, ms, (testo or "").strip()[:80])

    def in_parallelo(self, domanda: str, risposta: str | None = None,
                     categorie_attive: set | None = None):
        """Un giudizio in un thread del guardiano, mentre il modello della voce risponde: la
        domanda (`risposta` None: guardiano e rilevatore di pericolo insieme) o una frase.
        Chi lo usa trattiene solo l'uscita verso la voce finché il giudizio non arriva."""
        if risposta is None:
            return self._pool.submit(self.giudica_domanda, domanda, categorie_attive)
        return self._pool.submit(self.giudica, domanda, risposta, categorie_attive)

    # ── il rilevatore di pericolo (sulla domanda) ──
    def _pericolo_modello(self) -> tuple[str, str] | None:
        """(url, modello) del rilevatore: guardiano_pericolo_modello, oppure il modello della
        voce se è su Ollama (stessa finestra e keep_alive: niente ricaricamenti)."""
        cfg = self.cfg
        if not getattr(cfg, "guardiano_pericolo", True):
            return None
        m = str(getattr(cfg, "guardiano_pericolo_modello", "") or "")
        url = str(getattr(cfg, "guardiano_pericolo_url", "") or "")
        if not m:
            if str(getattr(cfg, "llm_backend", "ollama")) != "ollama":
                return None
            m = str(getattr(cfg, "llm_model", "") or "")
        url = url or str(getattr(cfg, "llm_native_url", "") or self.url)
        return (url.rstrip("/"), m) if m else None

    def pericolo(self, domanda: str, timeout: float | None = None,
                 riscalda: bool = True) -> Giudizio:
        """Il bambino dice di essere in pericolo? I modelli di moderazione giudicano se un
        testo è dannoso, non se chi parla è a rischio: «lo zio mi picchia», «un signore mi ha
        detto di non dirlo» per loro sono testi innocui (Llama Guard 3 8B: 0 su 3). Qui il
        modello della voce con l'output strutturato (enum PERICOLO / NO): 9 su 9 sul banco,
        nessun falso allarme su 27 domande normali e vietate (rapporto §4)."""
        dove = self._pericolo_modello()
        if dove is None:
            return Giudizio(GUASTO, grezzo="spento")
        url, modello = dove
        cfg = self.cfg
        # Stesse opzioni della voce (num_ctx e keep_alive): se cambiano, Ollama ricarica il
        # modello della voce. Con un modello a parte, la finestra del guardiano
        stesso = self.condivide_voce()
        try:
            from .config import keep_alive_valido
            from .contesto import finestra
            num_ctx = finestra(cfg) if stesso else int(getattr(cfg, "guardiano_num_ctx", 2048))
            keep = (keep_alive_valido(getattr(cfg, "llm_keep_alive", "-1m")) if stesso
                    else getattr(cfg, "guardiano_keep_alive", "-1m"))
        except Exception:  # noqa: BLE001
            num_ctx, keep = int(getattr(cfg, "llm_num_ctx", 16384) or 16384), "-1m"
        body = {"model": modello, "stream": False, "think": False, "keep_alive": keep,
                "messages": [{"role": "user", "content": PERICOLO_PROMPT.format(
                    frase=_pulito(domanda)[:600])}],
                "format": {"type": "object", "properties": {"esito": {
                    "type": "string", "enum": ["PERICOLO", "NO"]}}, "required": ["esito"]},
                "options": {"temperature": 0, "num_predict": 16, "num_ctx": num_ctx}}
        t0 = time.perf_counter()
        try:
            r = self._http().post(url + "/api/chat", json=body, timeout=timeout or self.timeout_s)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            testo = ((r.json().get("message") or {}).get("content") or "")
        except Exception as e:  # noqa: BLE001
            # Il modello della voce non si ricarica da qui: lo tiene caldo la voce
            if riscalda and self._scaduto(e) and not stesso:
                self._riscalda("pericolo")
            return Giudizio(GUASTO, ms=round((time.perf_counter() - t0) * 1000, 1),
                            grezzo=type(e).__name__)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        if "PERICOLO" in testo.upper():
            return Giudizio(PERICOLO, ("pericolo",), ms, testo.strip()[:40])
        return Giudizio(OK, (), ms, testo.strip()[:40])

    def condivide_voce(self) -> bool:
        """Il rilevatore di pericolo usa il modello della voce (stesso Ollama, stesso modello)."""
        dove = self._pericolo_modello()
        cfg = self.cfg
        return bool(dove) and dove[1] == str(getattr(cfg, "llm_model", "")) and dove[0] == str(
            getattr(cfg, "llm_native_url", "")).rstrip("/")

    def giudica_domanda(self, domanda: str, categorie_attive: set | None = None) -> Giudizio:
        """La domanda: il modello di moderazione e il rilevatore di pericolo insieme (in
        parallelo); pericolo se lo dice uno dei due."""
        # Un pool a parte: giudica_domanda gira già nel pool del guardiano (filtra)
        if getattr(self, "_pool_pericolo", None) is None:
            self._pool_pericolo = concurrent.futures.ThreadPoolExecutor(
                max_workers=2, thread_name_prefix="pericolo")
        f_p = self._pool_pericolo.submit(self.pericolo, domanda)
        g = self.giudica(domanda, None, categorie_attive)
        try:
            p = f_p.result(timeout=self.timeout_s + 0.5)
        except Exception:  # noqa: BLE001
            p = Giudizio(GUASTO, ms=round((self.timeout_s + 0.5) * 1000, 1), grezzo="timeout")
        if p.esito == PERICOLO and g.esito != PERICOLO:
            cats = tuple(c for c in g.categorie if c in PERICOLO_CATEGORIE) or ("pericolo",)
            g = Giudizio(PERICOLO, cats, max(g.ms, p.ms), f"{g.grezzo} | rilevatore")
        # Spento per configurazione (guardiano_pericolo: false, voce non su Ollama): nessun
        # esito, non è un guasto
        spento = p.esito == GUASTO and p.grezzo == "spento"
        g.pericolo = "" if spento else p.esito
        g.pericolo_ms = None if spento else p.ms
        if p.esito == GUASTO and not spento:
            self.ultimo_errore_pericolo = p.grezzo
        return g

    def close(self):
        self._pool.shutdown(wait=False, cancel_futures=True)


@dataclass
class Esito:
    """Cosa è successo in una risposta filtrata (per il registro dei turni e gli avvisi)."""
    domanda: Giudizio | None = None
    frasi: list = field(default_factory=list)       # [(ms, esito)] per frase
    fermata: str | None = None                      # "vietato" | "pericolo" | "guasto"
    categorie: tuple = ()
    detto: list = field(default_factory=list)


def filtra(guardiano: Guardiano, frasi, domanda: str, minore: bool, esito: Esito,
           categorie_attive: set | None = None, al_giudizio=None):
    """Le frasi della risposta (generatore di stringhe, già divise) che si possono dire.

    Generatore: la domanda si giudica subito in parallelo; ogni frase aspetta il proprio
    giudizio (la prima anche quello della domanda). Con «pericolo» sulla domanda o «vietato»
    su una frase lo stream del modello si chiude (`frasi.close()`) e si dice la frase fissa.
    Con il guardiano guasto: per un minore la frase fissa di guasto, per un ospite si passa.
    Anche sulla domanda (Q3 dell'analisi del 06/10): per un minore un guardiano o un
    rilevatore di pericolo guasto o scaduto vale «guasto», non «sicura».

    `al_giudizio(ok)`: chiamata una volta, appena arriva il giudizio sulla domanda (ok =
    si può rispondere): per i minori le schede della prima passata aspettano lei
    (Brain.trattieni_schede)."""
    # La domanda si giudica mentre il modello comincia a rispondere (in_parallelo): nessuna
    # frase va alla voce prima del suo giudizio (domanda_ok)
    fut = guardiano.in_parallelo(domanda, None, categorie_attive)
    sostituta = SOSTITUTA if minore else SOSTITUTA_OSPITE
    protezione = PROTEZIONE if minore else PROTEZIONE_OSPITE
    blocca_se_guasto = minore and str(getattr(guardiano.cfg, "guardiano_se_guasto",
                                              "blocca")) == "blocca"

    def stato_domanda() -> str:
        """OK, PERICOLO, oppure GUASTO (solo per un minore con guardiano_se_guasto: blocca)."""
        primo = esito.domanda is None
        if primo:
            try:
                esito.domanda = fut.result(timeout=2 * guardiano.timeout_s + 1)
            except Exception:  # noqa: BLE001
                esito.domanda = Giudizio(GUASTO, grezzo="timeout")
        g = esito.domanda
        stato = (PERICOLO if g.esito == PERICOLO else
                 GUASTO if blocca_se_guasto and g.guasto() else OK)
        if primo and al_giudizio is not None:
            try:
                al_giudizio(stato == OK)
            except Exception:  # noqa: BLE001 — le schede non fermano mai la voce
                pass
        return stato

    def ferma(stato: str) -> str:
        """La frase fissa per una domanda fermata (pericolo o guasto)."""
        if stato == PERICOLO:
            esito.fermata, esito.categorie = PERICOLO, esito.domanda.categorie
            esito.detto.append(protezione)
            return protezione
        esito.fermata = GUASTO
        esito.detto.append(GUASTO_FRASE)
        return GUASTO_FRASE

    def chiudi():
        try:
            frasi.close()
        except Exception:  # noqa: BLE001
            pass

    try:
        # Il rilevatore usa lo stesso modello della voce: Ollama serve le richieste a un modello
        # una alla volta, e se parte prima la risposta il rilevatore la aspetta tutta (banco
        # sulla DGX del 05/10: prima frase dei minori 2,0 s contro 1,0). Allora prima il
        # giudizio sulla domanda (~0,15–0,3 s), poi la risposta
        if guardiano.condivide_voce():
            stato = stato_domanda()
            if stato != OK:
                yield ferma(stato)
                return
        for frase in frasi:
            vuota = not str(frase or "").strip()
            # Il giudizio della frase parte subito, insieme all'attesa di quello della domanda
            # (la prima frase non paga i due giudizi uno dopo l'altro)
            f_frase = None if vuota else guardiano.in_parallelo(domanda, frase,
                                                                categorie_attive)
            stato = stato_domanda()
            if stato != OK:
                chiudi()
                yield ferma(stato)
                return
            if vuota:
                continue
            try:
                g = f_frase.result(timeout=guardiano.timeout_s + 0.5)
            except Exception:  # noqa: BLE001
                g = Giudizio(GUASTO, grezzo="timeout")
            esito.frasi.append((g.ms, g.esito))
            if g.esito == VIETATO:
                esito.fermata, esito.categorie = VIETATO, g.categorie
                chiudi()
                esito.detto.append(sostituta)
                yield sostituta
                return
            if g.esito == GUASTO and blocca_se_guasto:
                esito.fermata = GUASTO
                chiudi()
                esito.detto.append(GUASTO_FRASE)
                yield GUASTO_FRASE
                return
            esito.detto.append(frase)
            yield frase
        # Nessuna frase (un tool con la sua frase finale è comunque una frase): il giudizio
        # sulla domanda conta lo stesso
        stato = stato_domanda()
        if stato != OK:
            yield ferma(stato)
    finally:
        chiudi()


def correggi_storia(brain, detto: list[str]):
    """Dopo una risposta fermata dal guardiano la storia deve contenere solo ciò che è stato
    detto (come dopo un barge-in): il modello non deve credere di aver detto il resto."""
    testo = " ".join(x for x in detto if x).strip()
    h = getattr(brain, "history", None)
    if not isinstance(h, list):
        return
    # Via le risposte del modello dopo l'ultima domanda (testo e chiamate dei tool restano solo
    # se c'erano già risultati: un tool eseguito resta nella storia)
    while h and h[-1].get("role") == "assistant" and not h[-1].get("tool_calls"):
        h.pop()
    h.append({"role": "assistant", "content": testo or "…"})
