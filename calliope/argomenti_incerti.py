"""
Parole incerte negli argomenti dei tool (08/10/2026, fasi F0 e F1 di
docs/ricerche/2026-10-08-parole-incerte.md).

Il problema: Whisper sbaglia i nomi poco noti («Patello Giugnasco» per «Pradello Dugnasco»,
«Mantua», «metricità»), il modello li passa così al tool, e il tool non trova niente. La
probabilità per parola di Whisper è un buon segnale **sui nomi**, non sulle frasi; il segnale più
forte è il vocabolario dei nomi che Calliope conosce già, confrontato **solo con l'argomento**.

- **Argomenti che nominano qualcosa**: `ToolSpec.nomi` ({argomento: tipo}) dice quali argomenti
  di un tool sono un nome (città, entità della casa, estensione, contatto, file…); un argomento
  oggetto (`argomenti` del collaudo) vale per ogni suo valore di testo, con il tipo dal nome del
  campo (`tipo_da_campo`).
- **F0, solo misura** (`Misura`): quando il modello chiama un tool con un argomento marcato,
  le probabilità per parola della frase si chiedono **in parallelo** al tool (whisper.cpp:
  `verbose_json`, +0,15 s di GPU misurati, solo in questi turni, rimandando l'audio della frase;
  faster-whisper: `word_timestamps`), si allinea il valore alle parole della trascrizione
  (`allinea`) e si cerca il nome noto più vicino (`Vocabolario.vicino`, somiglianza ≥ 0,7 sul
  solo argomento). Nel registro dei turni `stt_argomento`; la correzione spontanea (stesso tool,
  valore quasi uguale entro tre turni) è la regola di misura `correzione_argomento`.
- **F1, dopo un esito vuoto** (`suggerimento`): se il tool non ha trovato niente e c'è un nome
  noto vicino, o la parola è incerta, il risultato per il modello dice «forse intendeva «X»:
  chiedi se è così» o «chiedi di ripeterlo o di scriverlo». È contesto (principio 10): il valore
  non si cambia e il tool non si rilancia da sé; il «sì» richiama il tool con il nome suggerito
  attraverso l'azione in sospeso di sempre. Regola `argomento_forse`.

Privacy: per ospiti e zona grigia nel registro solo numeri (niente valore né nome noto), e F1
mai; per un tool riservato mai il valore. Solo libreria standard.
"""
from __future__ import annotations

import difflib
import json
import re
import threading
import time
import unicodedata
from collections import deque
from concurrent.futures import ThreadPoolExecutor

# ─────────────────────────────── soglie ───────────────────────────────
# Il nome noto più vicino vale da «forse intendeva» da qui in su (documento, §2: sul solo
# argomento, 44 proposte giuste su 66 e nessuna sbagliata; a 0,6 una sbagliata)
SOGLIA_NOTO = 0.7
# Una parola del valore sotto questa probabilità è incerta (whisper.cpp, §2: a 0,5 segnala 49
# nomi sbagliati su 69 e 7 giusti su 39). Dopo un esito vuoto il turno è già perso: si usa la
# soglia larga
SOGLIA_P = 0.5
# Correzione spontanea: stesso tool entro tre turni con un valore quasi uguale (§3)
CORREZIONE_TURNI = 3
CORREZIONE_SIMILE = 0.75

# Tipi degli argomenti che nominano qualcosa. «luogo» e «valore» (un dato di un collaudo o di
# un'estensione) condividono i nomi riusciti
TIPI = ("luogo", "casa", "estensione", "contatto", "persona", "file", "valore")
_STESSO_GRUPPO = {"luogo": ("luogo", "valore"), "valore": ("luogo", "valore")}

# Il tipo dal nome del campo di un'estensione o del collaudo («citta» → luogo)
_CAMPI = (
    (re.compile(r"citt|comun|local|luog|paes|posto|zona|region|provinc|nazion|stato_|"
                r"city|town|place|location|indirizz|via\b|frazion", re.I), "luogo"),
    (re.compile(r"file|document|cartell|percors", re.I), "file"),
    (re.compile(r"contatt|client|fornitor|cognom|persona|chi\b", re.I), "contatto"),
)


def tipo_da_campo(campo: str, predefinito: str = "valore") -> str:
    for rx, tipo in _CAMPI:
        if rx.search(str(campo or "")):
            return tipo
    return predefinito


def nomi_estensione(schema: dict) -> dict:
    """`ToolSpec.nomi` del tool di un'estensione: gli input di testo liberi (senza enum), con il
    tipo dal nome del campo."""
    out = {}
    for k, v in ((schema or {}).get("properties") or {}).items():
        if isinstance(v, dict) and v.get("type") == "string" and not v.get("enum"):
            out[k] = tipo_da_campo(k)
    return out


# ─────────────────────────────── forme ───────────────────────────────
def lettere(s) -> str:
    """Solo le lettere, minuscole, senza accenti e con le doppie ridotte: «Pratofiorito
    Maggiore» e «Prato Fiorito Magiore» hanno la stessa forma (come nella misura del 08/10)."""
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    s = "".join(c for c in s if c.isalpha() and not unicodedata.combining(c))
    return re.sub(r"(.)\1+", r"\1", s)


def somiglianza(a, b) -> float:
    la, lb = lettere(a), lettere(b)
    if not la or not lb:
        return 0.0
    return difflib.SequenceMatcher(None, la, lb).ratio()


def chiave(s) -> str:
    """Lettere e cifre, minuscole, senza accenti né spazi: per dire se due valori sono lo stesso
    nome («Luca» e «Lucca» no, anche se hanno la stessa forma di `lettere`)."""
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return "".join(c for c in s if c.isalnum() and not unicodedata.combining(c))


def uguali(a, b) -> bool:
    return bool(chiave(a)) and chiave(a) == chiave(b)


def correzione(prima, dopo) -> bool:
    """Il secondo valore corregge il primo? Diversi, ma quasi uguali: tutto il valore, o una
    parola di almeno 4 lettere con una parola dell'altro (≥ 0,75; «Pradello Duniasco» →
    «Pradello Dugnasco», «Luca» → «Lucca»)."""
    if uguali(prima, dopo) or not chiave(prima) or not chiave(dopo):
        return False
    if re.findall(r"\d+", str(prima)) != re.findall(r"\d+", str(dopo)):
        return False                      # «Via Roma 3» → «Via Roma 5» è un'altra cosa

    def sim(x, y):                        # con le doppie: «Luca» → «Lucca» cambia
        return difflib.SequenceMatcher(None, chiave(x), chiave(y)).ratio()
    if sim(prima, dopo) >= CORREZIONE_SIMILE:
        return True
    a = [w for w in _gettoni(prima) if len(chiave(w)) >= 4]
    b = [w for w in _gettoni(dopo) if len(chiave(w)) >= 4]
    return any(not uguali(x, y) and sim(x, y) >= CORREZIONE_SIMILE for x in a for y in b)


def nella_frase(valore, testo) -> bool:
    """Il valore viene dalle parole della frase (anche corretto dal modello: «Pratofiorino» →
    «Pratofiorito»)? Solo questi valori entrano nel vocabolario: mai un nome preso da un
    risultato o scelto dal modello."""
    return allinea(valore, [(w, 1.0) for w in _gettoni(testo)]) is not None


def _gettoni(s) -> list[str]:
    return [w for w in re.findall(r"[\w'’]+", str(s or "")) if any(c.isalnum() for c in w)]


def argomenti_marcati(spec, args) -> list[tuple[str, str, str]]:
    """(campo, valore, tipo) degli argomenti che nominano qualcosa, con un valore di testo.
    Un argomento oggetto vale per ogni suo valore di testo («argomenti.citta»)."""
    nomi = getattr(spec, "nomi", None) or {}
    if not nomi or not isinstance(args, dict):
        return []
    out = []
    for campo, tipo in nomi.items():
        v = args.get(campo)
        if isinstance(v, str) and v.strip() and re.search(r"[^\W\d_]", v):
            out.append((campo, v.strip(), tipo))
        elif isinstance(v, dict):
            for k, x in v.items():
                if isinstance(x, str) and x.strip() and re.search(r"[^\W\d_]", x):
                    out.append((f"{campo}.{k}", x.strip(), tipo_da_campo(k, tipo)))
    return out[:4]


def sostituisci(args: dict, campo: str, nuovo: str) -> dict:
    """Gli argomenti con il valore di `campo` («argomenti.citta» per un oggetto) cambiato."""
    out = json.loads(json.dumps(args or {}, ensure_ascii=False, default=str))
    testa, _, coda = campo.partition(".")
    if coda and isinstance(out.get(testa), dict):
        out[testa][coda] = nuovo
    else:
        out[testa] = nuovo
    return out


# ─────────────────────────────── allineamento ───────────────────────────────
def allinea(valore: str, parole: list[tuple[str, float]], nomi_sveglia=()) -> dict | None:
    """Le parole della trascrizione da cui viene il valore: la finestra di parole consecutive
    (lunga quanto il valore, una in più o in meno) più simile lettera per lettera, se la
    somiglianza è almeno 0,5 (con tolleranza: il modello può aver già corretto «Patello» in
    «Pradello»). Le parole che svegliano non contano. None se non c'è (valore detto in un turno
    di prima, preso da un risultato, scritto dal modello)."""
    sveglia = {lettere(n) for n in nomi_sveglia or ()}
    ps = [(w, float(p)) for w, p in parole or () if lettere(w) and lettere(w) not in sveglia]
    n = len(_gettoni(valore))
    if not ps or not n:
        return None
    meglio = None
    for lung in sorted({max(1, n - 1), n, n + 1}):
        for i in range(0, len(ps) - lung + 1):
            fin = ps[i:i + lung]
            s = somiglianza(valore, " ".join(w for w, _ in fin))
            if meglio is None or s > meglio[0] + 1e-9:
                meglio = (s, fin)
    if meglio is None or meglio[0] < 0.5:
        return None
    s, fin = meglio
    probs = [p for _, p in fin]
    return {"p_min": round(min(probs), 3), "p_media": round(sum(probs) / len(probs), 3),
            "parole": len(fin), "uguale": s >= 0.999, "somiglianza_frase": round(s, 3)}


# ─────────────────────────────── esito del tool ───────────────────────────────
_NON_TROVATO = re.compile(
    r"non\s+(?:l['’]\s*ho\s+|ho\s+|è\s+stat[oa]\s+|sono\s+stat[ie]\s+)?trovat|"
    r"non\s+(?:esist|c['’]è|ci\s+sono|risult|(?:lo\s+|la\s+|l['’]\s*)?riconosc)|"
    r"nessun[oa]?\s+(?:risultat|città|luog|corrispond|"
    r"element|dato|dati|file|voce|contatt|dispositiv|estension|localit|comune)|"
    r"\bsconosciut|\binesistent|not\s+found|no\s+results?|no\s+match|unknown\s+(?:city|place|"
    r"location)|could\s+not\s+find|couldn['’]t\s+find|\b404\b", re.I)
# Le decisioni della politica e dei permessi non sono un esito del tool
_MOTIVI_FERMO = re.compile(r"permess|politic|conferm|sfida|minor|guardian|bloccat", re.I)
# «L'azione NON è stata eseguita» (testi.NIENTE): la politica o lo schema l'hanno fermata (caso
# vero della DGX, 09/10 alle 20:48: sviluppo_collauda fermato da valore_non_ancorata contava
# come «errore» del tool)
_NIENTE = "NIENTE: l'azione NON è stata eseguita"
# Un risultato riuscito che dice a parole di non aver trovato (09/10 sera, caso vero della DGX
# alle 20:47: «Non ho trovato la città 'Pradello Lugnasco'» nel da_dire di un collaudo) conta come
# vuoto solo se il «non trovato» riguarda un nome: seguito o preceduto da una cosa che si cerca
# per nome («la città», «località non trovata»), da «nulla», «niente», o con dentro il valore
# passato al tool; e solo se accanto non ci sono dati. «Non ho trovato pioggia, è sereno» non è
# vuoto. Meglio ancora il campo «trovato»: false, che il contratto delle estensioni chiede dal
# 09/10 sera (CAPACITA.md, estensioni/prompt.py)
_COSE = (r"(?:citt[aà]|comun[ei]|localit[aà]|luogh?[oi]|paes[ei]|post[oi]|indirizz[oi]|"
         r"nom[ei]|contatt[oi]|client[ei]|fornitor[ei]|person[ae]|file|document[oi]|"
         r"cartell[ae]|voc[ei]|dispositiv[oi]|entit[aà]|stanz[ae]|estension[ei]|element[oi]|"
         r"corrispondenz[ae]|risultat[oi]|dat[oi]|niente|nulla|city|place|location|town|name|"
         r"results?|match)\b")
_COSA_DOPO = re.compile(r"^\W*(?:(?:il|lo|la|l['’]|i|gli|le|un|una|uno|un['’]|alcun[oa]?|"
                        r"nessun[oa]?|del|dello|della|dell['’]|dei|degli|delle|the|any|a)"
                        r"(?:\s+|(?<=['’])))*" + _COSE, re.I)
_COSA_PRIMA = re.compile(_COSE + r"[^.;:!?]{0,12}$", re.I)
_ATTACCO = re.compile(r"^(?:[\s'\"«»‘’:,]|\b(?:il|lo|la|l|per|di|a|in|con|su)\b)*", re.I)
_CHIUSI = re.compile(r"(?:nessun|not\s+found|no\s+results?|no\s+match|unknown|could|couldn|"
                     r"sconosciut|inesistent|404)", re.I)
# I campi di un risultato che sono solo parole per chi parla: il resto sono dati
_CAMPI_MESSAGGIO = frozenset({"da_dire", "messaggio", "message", "errore", "error", "avviso",
                              "nota", "consiglio", "suggerimento", "suggerimenti", "trovato",
                              "trovata", "ok"})


def dice_non_trovato(testo: str, valori=()) -> bool:
    """Il testo dice di non aver trovato un nome? (vedi sopra)"""
    t = str(testo or "")
    valori = [v for v in valori or () if len(chiave(v)) >= 3]
    for m in _NON_TROVATO.finditer(t):
        if _CHIUSI.match(m.group(0)):
            return True
        dopo = re.sub(r"^\w*", "", t[m.end():m.end() + 80])       # il resto della parola
        prima = t[:m.start()]
        if _COSA_DOPO.match(dopo):
            return True
        # Prima della frase, e il valore, solo con «trovato» e «riconosce» («Località non
        # trovata»; «Milano: non ci sono allerte» non dice che Milano non c'è)
        if not re.search(r"trovat|riconosc", m.group(0), re.I):
            continue
        if _COSA_PRIMA.search(prima):
            return True
        # Il valore subito dopo («non ho trovato 'Pradello Lugnasco'») o subito prima
        # («Pradello Lugnasco non è stato trovato»): mai più in là («non ho trovato pioggia a
        # Milano» non dice che Milano non c'è)
        dopo = _ATTACCO.sub("", dopo)
        if any(chiave(dopo[:len(v) + 12]).startswith(chiave(v))
               or chiave(prima[-(len(v) + 12):]).endswith(chiave(v)) for v in valori):
            return True
    return False


def _valori(argomenti) -> list[str]:
    out = []
    for v in (argomenti.values() if isinstance(argomenti, dict) else ()):
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
        elif isinstance(v, dict):
            out += [x.strip() for x in v.values() if isinstance(x, str) and x.strip()]
    return out


def _ha_dati(ris: dict, valori) -> bool:
    """Il risultato ha dati oltre alle parole per chi parla (e oltre ai valori passati, che
    un'estensione può ripetere)?"""
    for k, v in ris.items():
        if k in _CAMPI_MESSAGGIO or _vuoto(v) or isinstance(v, bool):
            continue
        if isinstance(v, str) and any(uguali(v, x) or chiave(x) in chiave(v) for x in valori
                                      if len(chiave(x)) >= 3):
            continue
        return True
    return False


def _testi(x, prof: int = 0):
    if prof > 5:
        return
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _testi(v, prof + 1)
    elif isinstance(x, list):
        for v in x[:50]:
            yield from _testi(v, prof + 1)


def _vuoto(x) -> bool:
    return x is None or (isinstance(x, (list, dict, str)) and not x)


def esito(res, argomenti=None) -> str:
    """Com'è andato il tool, per la misura e per F1:
    - «fermato»: non è partito (politica, permessi, conferma o domanda in sospeso; «NIENTE:
      l'azione NON è stata eseguita»);
    - «vuoto»: è partito e non ha trovato niente (campo d'errore o testo «non trovato», «nessun
      risultato» riferito a un nome e senza dati accanto, `dice_non_trovato`; risultati vuoti;
      «trovato»: false);
    - «errore»: è partito e si è rotto per altro (rete, codice);
    - «pieno»: ha trovato qualcosa.
    Il testo dei risultati di un'estensione è un dato non fidato: qui decide solo se aggiungere
    un suggerimento, mai un'azione. `argomenti`: quelli passati al tool (un «non trovato» con
    dentro il valore riguarda quel nome; il valore ripetuto nel risultato non è un dato)."""
    valori = _valori(argomenti)
    if not isinstance(res, dict):
        return "errore"
    if "in_sospeso" in res or _MOTIVI_FERMO.search(str(res.get("motivo") or "")):
        return "fermato"
    if res.get("trovato") is False or res.get("trovata") is False:
        return "vuoto"
    ris = res.get("risultati", res.get("risultato"))
    if ("risultati" in res or "risultato" in res) and _vuoto(ris):
        return "vuoto"
    if isinstance(ris, dict):
        if ris.get("trovato") is False or ris.get("trovata") is False:
            return "vuoto"
        for k in ("risultati", "risultato", "elenco", "voci", "items", "results"):
            if k in ris and _vuoto(ris[k]):
                return "vuoto"
        if ris and all(_vuoto(v) for v in ris.values()):
            return "vuoto"                # {"previsioni": []}
        err = " ".join(str(ris.get(k) or "") for k in ("errore", "error", "messaggio",
                                                         "message", "da_dire"))
        # Le parole contano solo senza dati accanto: «Non ho trovato pioggia» con temperatura e
        # cielo è un risultato pieno
        if not _ha_dati(ris, valori) and dice_non_trovato(err, valori):
            return "vuoto"
        if ris.get("errore") or ris.get("error") or ris.get("ok") is False:
            return "errore"
    for k in ("trovati", "n", "quanti"):
        if res.get(k) == 0:
            return "vuoto"
    fallito = "errore" in res or res.get("ok") is False
    testo = " ".join(str(res.get(k) or "") for k in ("errore", "conferma", "risposta_finale",
                                                      "fatto"))
    if fallito:
        if _NON_TROVATO.search(testo) or res.get("nomi_vicini") is not None:
            return "vuoto"
        return "fermato" if str(res.get("fatto") or "").startswith(_NIENTE) else "errore"
    # Riuscito, ma il risultato dice a parole che non c'è («Località non trovata»)
    if isinstance(ris, (list, str)) or (isinstance(ris, dict) and not _ha_dati(ris, valori)):
        corto = " ".join(_testi(ris))[:600]
        if corto and len(corto) < 300 and dice_non_trovato(corto, valori):
            return "vuoto"
    return "pieno"


# ─────────────────────────────── vocabolario ───────────────────────────────
class Vocabolario:
    """I nomi che Calliope conosce già, per tipo: estensioni (nome e titolo), entità esposte
    della casa (nome, alias, stanze), persone registrate, e i valori dei tool con un esito
    pieno (collaudi, estensioni, ricerche) detti da chi vive in casa. Questi ultimi stanno in
    memoria e si ricaricano all'avvio dal registro dei turni (`stt_argomento` con esito pieno):
    nessun file nuovo."""

    def __init__(self, massimo: int = 400):
        self._riusciti: deque = deque(maxlen=massimo)
        self._lock = threading.Lock()
        self._caricato: set = set()

    def ricorda(self, tipo: str, valore: str):
        v = str(valore or "").strip()
        if not v or len(v) > 80 or not lettere(v):
            return
        with self._lock:
            for i, (t, x) in enumerate(self._riusciti):
                if t == tipo and uguali(x, v):
                    del self._riusciti[i]
                    break
            self._riusciti.append((tipo, v))

    def carica_dal_registro(self, cartella, giorni: int = 14, attendi: bool = True):
        """I valori con esito pieno degli ultimi `giorni` file del registro (una volta per
        cartella). Mai dei turni di ospiti (nel registro non hanno il valore). Con
        `attendi=False` in un thread a parte: la prima chiamata di un tool non aspetta la
        lettura del registro."""
        if not cartella:
            return
        chiave = str(cartella)
        with self._lock:
            if chiave in self._caricato:
                return
            self._caricato.add(chiave)
        if not attendi:
            threading.Thread(target=self._carica, args=(cartella, giorni), daemon=True,
                             name="vocabolario-registro").start()
            return
        self._carica(cartella, giorni)

    def _carica(self, cartella, giorni: int):
        try:
            from .latenza import leggi
            turni = leggi(cartella, giorni)
        except Exception:  # noqa: BLE001 — senza registro, solo i nomi di questa sessione
            return
        for t in turni:
            for m in t.get("stt_argomento") or ():
                if isinstance(m, dict) and m.get("esito") == "pieno" and m.get("valore"):
                    self.ricorda(m.get("tipo") or "valore", m["valore"])

    def riusciti(self, tipo: str) -> list[str]:
        gruppo = _STESSO_GRUPPO.get(tipo, (tipo,))
        with self._lock:
            return [v for t, v in reversed(self._riusciti) if t in gruppo]

    def nomi(self, tipo: str, ctx=None) -> list[str]:
        """I nomi noti per questo tipo di argomento. Ogni fonte che manca o si rompe si salta."""
        out = list(self.riusciti(tipo))
        if ctx is None:
            return out
        try:
            if tipo == "estensione":
                est = getattr(ctx, "estensioni", None)
                arch = getattr(est, "archivio", None)
                for n in (arch.nomi() if arch is not None else []):
                    m = arch.manifesto(n) or {}
                    if m.get("titolo"):
                        out.append(str(m["titolo"]))
                    out.append(n.replace("_", " "))
            elif tipo == "casa":
                casa = getattr(ctx, "casa", None)
                if casa is not None:
                    for e in casa.entita():
                        out += [e.nome, e.area, *(e.alias or [])]
                    out += list(casa.aree() or [])
            elif tipo in ("persona", "contatto"):
                out += list(getattr(getattr(ctx, "speakers", None), "users", None) or {})
        except Exception:  # noqa: BLE001
            pass
        visti, puliti = set(), []
        for n in out:
            k = chiave(n)
            if n and k and k not in visti:
                visti.add(k)
                puliti.append(str(n))
        return puliti

    def vicino(self, valore: str, tipo: str, ctx=None) -> tuple[str | None, float]:
        """Il nome noto più simile al valore e la somiglianza (lettere, doppie ridotte). Per un
        argomento «casa» (una frase: «accendi la lampara del sottalco») si confrontano i pezzi
        di una, due e tre parole della frase."""
        nomi = self.nomi(tipo, ctx)
        if not nomi or not lettere(valore):
            return None, 0.0
        pezzi = [valore]
        if tipo == "casa":
            g = _gettoni(valore)
            pezzi = [" ".join(g[i:i + n]) for n in (1, 2, 3) for i in range(len(g) - n + 1)
                     if len(lettere(" ".join(g[i:i + n]))) >= 5] or [valore]
        meglio, s_meglio = None, 0.0
        for p in pezzi:
            for n in nomi:
                s = somiglianza(p, n)
                if s > s_meglio:
                    meglio, s_meglio = n, s
        return meglio, round(s_meglio, 3)


VOCABOLARIO = Vocabolario()

# Le richieste delle probabilità per parola, in secondo piano (una alla volta: whisper.cpp le
# mette comunque in fila)
_POOL: ThreadPoolExecutor | None = None
_POOL_LOCK = threading.Lock()


def _pool() -> ThreadPoolExecutor:
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt-argomenti")
        return _POOL


# ─────────────────────────────── l'ascolto del turno ───────────────────────────────
class Ascolto:
    """L'audio della frase di questo turno e il trascrittore, per chiedere le probabilità per
    parola solo se serve (un tool con un argomento marcato). Se la frase le aveva già
    (`verbose_json` acceso per la correzione), si usano quelle."""

    def __init__(self, audio=None, stt=None, conf=None, nomi_sveglia=()):
        self.audio = audio
        self.stt = stt
        self.nomi_sveglia = tuple(nomi_sveglia or ())
        gia = getattr(conf, "parole", None) if conf is not None else None
        self._parole = list(gia) if gia else None
        self._futuro = None
        self._t0 = None
        self.ms: float | None = None

    @property
    def possibile(self) -> bool:
        return self._parole is not None or (
            self.audio is not None and len(self.audio) > 0
            and callable(getattr(self.stt, "parole", None)))

    def avvia(self):
        """Chiede le parole in secondo piano (una volta per turno)."""
        if self._parole is not None or self._futuro is not None or not self.possibile:
            return
        self._t0 = time.perf_counter()

        def chiedi():
            try:
                return self.stt.parole(self.audio)
            finally:
                self.ms = round((time.perf_counter() - self._t0) * 1000, 1)
        self._futuro = _pool().submit(chiedi)

    def parole(self, attesa_s: float = 0.0) -> list | None:
        """Le parole con la probabilità, se sono arrivate entro `attesa_s`; None altrimenti."""
        if self._parole is not None:
            return self._parole
        if self._futuro is None:
            return None
        try:
            self._parole = list(self._futuro.result(timeout=max(0.0, attesa_s)) or [])
        except Exception:  # noqa: BLE001 — tempo scaduto o server giù: niente misura
            if self._futuro.done():
                self._parole = []
            return None
        return self._parole

    @property
    def pronte(self) -> bool:
        return self._parole is not None or (self._futuro is not None and self._futuro.done())


# ─────────────────────────────── la misura di una chiamata ───────────────────────────────
class Misura:
    """Un argomento marcato di una chiamata: valore, tipo, esito del tool, nome noto vicino,
    probabilità (anche arrivata dopo, `completa`)."""

    def __init__(self, tool: str, campo: str, valore: str, tipo: str, riservata: bool = False,
                 anonima: bool = False):
        self.tool, self.campo, self.valore, self.tipo = tool, campo, valore, tipo
        self.riservata = riservata          # tool riservato: mai il valore
        self.anonima = anonima              # ospite o zona grigia: solo numeri
        self.esito: str | None = None
        self.noto: str | None = None
        self.somiglianza: float = 0.0
        self.allineata: dict | None = None
        self.p_tardi = False
        self.correzione: dict | None = None
        self.forse: str | None = None       # F1: «forse» | «ripeti» | «nessuno»
        self.da_suggerimento = False        # il valore è quello suggerito al turno prima

    def completa(self, ascolto: Ascolto | None, attesa_s: float = 0.0):
        if self.allineata is not None or ascolto is None:
            return
        parole = ascolto.parole(attesa_s)
        if parole is None:
            self.p_tardi = ascolto.possibile
            return
        self.p_tardi = False
        self.allineata = allinea(self.valore, parole, ascolto.nomi_sveglia) or {}

    @property
    def p_min(self) -> float | None:
        return (self.allineata or {}).get("p_min")

    def per_registro(self, ms: float | None = None) -> dict:
        out = {"tool": self.tool, "argomento": self.campo, "tipo": self.tipo,
               "esito": self.esito}
        if not (self.riservata or self.anonima):
            out["valore"] = self.valore
            if self.noto is not None:
                out["noto"] = self.noto
        out["somiglianza"] = self.somiglianza
        if self.noto is not None and uguali(self.noto, self.valore):
            out["e_noto"] = True
        a = self.allineata
        if a:
            out.update(p_min=a["p_min"], p_media=a["p_media"], parole=a["parole"],
                       uguale_alla_frase=a["uguale"])
        elif a == {}:
            out["allineato"] = False
        elif self.p_tardi:
            out["p_tardi"] = True
        if ms is not None and (a or self.p_tardi):
            out["stt_ms"] = ms
        if self.correzione:
            out["correzione"] = self.correzione
        if self.forse:
            out["forse"] = self.forse
        if self.da_suggerimento:
            out["da_suggerimento"] = True
        return out


# ─────────────────────────────── F1: il suggerimento ───────────────────────────────
FORSE_MSG = ("Con «{detto}» non è stato trovato niente, e forse ho capito male il nome. Dillo "
             "in breve e chiudi la risposta con la domanda «Intendevi {forse}?», con il punto "
             "di domanda. Se poi dice sì, richiama {tool} con «{forse}» al posto di «{detto}». "
             "Non dire che è stato trovato e non cambiare il nome da solo.")
RIPETI_MSG = ("Con «{detto}» non è stato trovato niente, e forse ho capito male il nome. Dillo "
              "in breve e chiedi a chi parla di ripeterlo, o di scriverlo{schermo}. Non "
              "inventare un nome.")


def suggerimento(m: Misura, soglia_noto: float = SOGLIA_NOTO,
                 soglia_p: float = SOGLIA_P, scritto: bool = False) -> dict | None:
    """Dopo un esito vuoto: «forse intendeva X» con un nome noto vicino (sotto 1: uguale non è
    un suggerimento), altrimenti «ripeti o scrivi» se una parola del valore era incerta per
    Whisper. Con la frase scritta (niente Whisper) solo il nome vicino. None se niente."""
    if m.esito != "vuoto":
        return None
    if m.noto and soglia_noto <= m.somiglianza and not uguali(m.noto, m.valore):
        m.forse = "forse"
        return {"forma": "forse", "detto": m.valore, "forse": m.noto}
    p = m.p_min
    if not scritto and p is not None and p < soglia_p:
        m.forse = "ripeti"
        return {"forma": "ripeti", "detto": m.valore}
    m.forse = "nessuno"
    return None


# ─────────────────────────────── riassunto (calliope stato --turni) ───────────────────────────
def riassunto(turni: list[dict], soglie=(0.3, 0.4, 0.5)) -> dict:
    """Quante chiamate con un argomento marcato, quante con esito vuoto, quante con un nome
    noto vicino, le probabilità sotto le soglie, le correzioni spontanee e i suggerimenti."""
    ms = [m for t in turni for m in (t.get("stt_argomento") or ()) if isinstance(m, dict)]
    r = {"chiamate": len(ms), "turni": sum(1 for t in turni if t.get("stt_argomento")),
         "esiti": {}, "con_probabilita": 0, "sotto": {str(s): 0 for s in soglie},
         "sotto_vuoti": {str(s): 0 for s in soglie}, "noto_vicino": 0, "noto_vicino_vuoti": 0,
         "noto_uguale": 0, "correzioni": 0, "correzioni_riuscite": 0, "forse": {}, "da_suggerimento": 0, "p_tardi": 0,
         "non_allineati": 0, "per_tool": {}}
    for m in ms:
        e = m.get("esito") or "?"
        r["esiti"][e] = r["esiti"].get(e, 0) + 1
        r["per_tool"][m.get("tool") or "?"] = r["per_tool"].get(m.get("tool") or "?", 0) + 1
        p = m.get("p_min")
        if p is not None:
            r["con_probabilita"] += 1
            for s in soglie:
                if p < s:
                    r["sotto"][str(s)] += 1
                    if e == "vuoto":
                        r["sotto_vuoti"][str(s)] += 1
        r["p_tardi"] += bool(m.get("p_tardi"))
        r["non_allineati"] += m.get("allineato") is False
        s = float(m.get("somiglianza") or 0)
        if m.get("e_noto"):
            r["noto_uguale"] += 1
        elif s >= SOGLIA_NOTO:
            r["noto_vicino"] += 1
            r["noto_vicino_vuoti"] += e == "vuoto"
        r["correzioni"] += bool(m.get("correzione"))
        # Il caso del documento: il primo vuoto o in errore, il secondo pieno
        r["correzioni_riuscite"] += bool(
            m.get("correzione") and e == "pieno"
            and (m["correzione"] or {}).get("esito_prima") in ("vuoto", "errore"))
        if m.get("forse"):
            r["forse"][m["forse"]] = r["forse"].get(m["forse"], 0) + 1
        r["da_suggerimento"] += bool(m.get("da_suggerimento"))
    return r


def testo(r: dict) -> str:
    if not r.get("chiamate"):
        return "Argomenti che nominano qualcosa (stt_argomento): nessuna chiamata nel registro."
    es = ", ".join(f"{k} {v}" for k, v in sorted(r["esiti"].items()))
    righe = [f"Argomenti che nominano qualcosa (stt_argomento): {r['chiamate']} chiamate in "
             f"{r['turni']} turni ({es})."]
    if r["con_probabilita"]:
        sotto = ", ".join(f"< {k}: {v} (vuoti {r['sotto_vuoti'][k]})"
                          for k, v in r["sotto"].items())
        righe.append(f"  probabilità di Whisper su {r['con_probabilita']}: {sotto}")
    righe.append(f"  nome noto vicino (≥ {SOGLIA_NOTO}): {r['noto_vicino']} (con esito vuoto "
                 f"{r['noto_vicino_vuoti']}); uguale a un nome noto: {r['noto_uguale']}")
    altro = []
    if r["correzioni"]:
        altro.append(f"correzioni spontanee {r['correzioni']} (dopo un esito vuoto e "
                     f"riuscite: {r['correzioni_riuscite']})")
    if r["forse"]:
        altro.append("suggerimenti " + ", ".join(f"{k} {v}" for k, v in r["forse"].items()))
    if r["da_suggerimento"]:
        altro.append(f"usati {r['da_suggerimento']}")
    if r["p_tardi"] or r["non_allineati"]:
        altro.append(f"probabilità arrivate tardi {r['p_tardi']}, valori non nella frase "
                     f"{r['non_allineati']}")
    if altro:
        righe.append("  " + "; ".join(altro))
    return "\n".join(righe)
