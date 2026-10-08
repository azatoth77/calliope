"""
Scrivere invece di parlare (03/10/2026): moduli sullo schermo e testo scritto.

A voce Whisper storpia le partite IVA, i codici fiscali, gli IBAN, le email e i nomi difficili,
e il modello li ricopia male. Quando un tool chiede dati di cui conosce il tipo (i campi
mancanti di modello_compila, un cliente nuovo di anagrafica_salva, la domanda di un lavoro
dell'agente), lo **schermo personale** di chi parla mostra una scheda `modulo`: un campo per
dato, del tipo giusto, con i controlli mentre si scrive (pagina/schermo.js) e di nuovo qui.

- I valori inviati vanno **dritti al programma** (`Modulo.riprendi`, chiamata dal ciclo
  principale): né Whisper né il modello li vedono, nemmeno dopo (nella storia entra solo «ho
  scritto i dati per …» con i nomi dei campi). Nel registro dei turni e nei log solo i nomi
  dei campi, mai i valori.
- Chi arriva prima vince: una risposta a voce richiama lo stesso tool, che chiude il modulo
  (`chiudi_per_tool`: la scheda diventa «hai risposto a voce»); un modulo inviato chiude la
  domanda a voce (l'azione in sospeso si toglie).
- Il modulo è legato alla persona che l'ha chiesto (UserProfile.id) e va solo ai suoi schermi
  personali (visibilità `personale`: mai nella zona grigia, mai a uno schermo di stanza);
  lo può inviare solo una pagina con la sessione di uno schermo di quella persona.

La casella «scrivi invece di parlare» (server.py, /api/scrivi) mette il testo nella stessa
coda (`Schermi.ingresso`): il ciclo principale lo tratta come una frase trascritta, con
`identified_by = "schermo"` (speaker_id.py) e `canale: scritto` nel registro dei turni.

Questo modulo non importa Starlette: lo usano anche i tool e le prove senza server.
"""

import datetime
import queue
import re
import secrets
import threading
import time
from dataclasses import dataclass, field

from .schede import PERSONALE, nuova
from ..testi import iban_ok

# ─────────────────────────── tipi e controlli ───────────────────────────

TIPI = ("testo", "testo_lungo", "numero", "importo", "data", "booleano", "scelta", "elenco",
        "righe", "codice_fiscale", "partita_iva", "iban", "cap", "provincia", "email",
        "codice_destinatario")
# Tipi i cui valori non si scrivono mai nei log né nel registro (nemmeno oscurati a metà)
SENSIBILI = frozenset({"codice_fiscale", "partita_iva", "iban", "email"})
MAX_CAMPI = 24
MAX_RIGHE = 30
MAX_TESTO = 200
MAX_TESTO_LUNGO = 2000
MAX_VOCI = 40


def _cifre_cf(s) -> str:
    return re.sub(r"[\s.\-/]", "", str(s or "")).upper()


# Lunghezze degli IBAN dei paesi più vicini (gli altri: solo il controllo mod 97)
_IBAN_LUNGHEZZA = {"IT": 27, "SM": 27, "VA": 22, "DE": 22, "FR": 27, "ES": 24, "AT": 20,
                   "CH": 21, "BE": 16, "NL": 18, "PT": 25, "GB": 22, "IE": 22, "LU": 20,
                   "SI": 19, "HR": 21, "MT": 31, "GR": 27, "PL": 28}


def numero_detto(v) -> float | None:
    """«1.234,56», «1234,56», «1234.56», «1 234», «€ 50», 50 → numero. La virgola è sempre
    il separatore dei decimali (all'italiana). None se non è un numero."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = re.sub(r"[\s€]|euro", "", str(v or "").strip().lower())
    if not t:
        return None
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", t):        # 1.234,56
        t = t.replace(".", "").replace(",", ".")
    else:                                                     # 12,5 · 12.5
        t = t.replace(",", ".")
    if not re.fullmatch(r"-?\d+(\.\d+)?", t):
        return None
    return float(t)


def _intero(x: float):
    return int(x) if float(x).is_integer() else round(x, 6)


def controlla_campo(c: dict, v) -> tuple[object, str]:
    """(valore normalizzato, errore). Errore "" = va bene. Lo stesso controllo è in
    pagina/schermo.js (mentre si scrive): qui vale quello del server."""
    from ..ufficio.rubrica import PROVINCE, codice_fiscale_ok, partita_iva_ok
    tipo = c.get("tipo", "testo")
    obbl = bool(c.get("obbligatorio", True))
    vuoto = v is None or (isinstance(v, str) and not v.strip()) or v == []
    if tipo == "booleano":
        if isinstance(v, bool):
            return v, ""
        t = str(v or "").strip().lower()
        if t in ("true", "sì", "si", "1"):
            return True, ""
        if t in ("false", "no", "0", ""):
            return (False, "") if t or not obbl else (None, "Scegli sì o no")
        return None, "Scegli sì o no"
    if vuoto:
        return None, ("Manca" if obbl else "")
    if tipo in ("testo", "testo_lungo"):
        t = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(v)).strip()
        if tipo == "testo":
            t = re.sub(r"\s+", " ", t)
        n = MAX_TESTO if tipo == "testo" else MAX_TESTO_LUNGO
        return (t, "") if len(t) <= n else (None, f"Al massimo {n} caratteri")
    if tipo == "scelta":
        t = str(v).strip()
        return (t, "") if t in [str(o) for o in c.get("opzioni") or ()] else (None, "Scegli "
                                                                              "una voce")
    if tipo in ("numero", "importo"):
        x = numero_detto(v)
        if x is None:
            return None, "Scrivi un numero" if tipo == "numero" else "Scrivi un importo, " \
                                                                     "per esempio 1.234,50"
        if tipo == "importo":
            if x < 0:
                return None, "L'importo non può essere negativo"
            if round(x, 2) != round(x, 6):
                return None, "Al massimo due decimali"
            return _intero(round(x, 2)), ""
        return _intero(x), ""
    if tipo == "data":
        t = str(v).strip()
        d = None
        try:
            d = datetime.date.fromisoformat(t[:10]) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t) \
                else None
        except ValueError:
            d = None
        m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", t)
        if d is None and m:
            try:
                d = datetime.date(int(m[3]), int(m[2]), int(m[1]))
            except ValueError:
                d = None
        return (d.isoformat(), "") if d else (None, "Data non valida")
    if tipo == "elenco":
        voci = v if isinstance(v, list) else str(v).splitlines()
        voci = [re.sub(r"\s+", " ", str(x)).strip() for x in voci]
        voci = [x[:MAX_TESTO] for x in voci if x][:MAX_VOCI]
        return (voci, "") if voci else (None, "Manca" if obbl else "")
    if tipo == "righe":
        if not isinstance(v, list):
            return None, "Righe non valide"
        prezzi = c.get("prezzi", True)
        out = []
        for i, r in enumerate(v[:MAX_RIGHE], 1):
            if not isinstance(r, dict):
                return None, f"Riga {i} non valida"
            desc = re.sub(r"\s+", " ", str(r.get("descrizione") or "")).strip()[:MAX_TESTO]
            q, p = r.get("quantita"), r.get("prezzo")
            if not desc and q in (None, "") and p in (None, ""):
                continue                                   # riga lasciata vuota
            if not desc:
                return None, f"Riga {i}: manca la descrizione"
            qn = numero_detto(q) if q not in (None, "") else None
            if q not in (None, "") and (qn is None or qn <= 0):
                return None, f"Riga {i}: quantità non valida"
            riga = {"descrizione": desc, "quantita": _intero(qn) if qn is not None else None}
            if prezzi:
                pn = numero_detto(p)
                if pn is None or pn < 0:
                    return None, f"Riga {i}: manca il prezzo"
                riga.update(prezzo=_intero(round(pn, 2)), aliquota=None)
            else:
                if qn is None:
                    return None, f"Riga {i}: manca la quantità"
                riga["unita"] = re.sub(r"\s+", " ", str(r.get("unita") or "")).strip()[:20] or None
            out.append(riga)
        return (out, "") if out else (None, "Manca almeno una riga" if obbl else "")
    if tipo == "codice_fiscale":
        t = _cifre_cf(v)
        if re.fullmatch(r"\d{11}", t):
            return (t, "") if partita_iva_ok(t) else (None, "La cifra di controllo non torna")
        if not re.fullmatch(r"[A-Z]{6}[0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{2}[A-Z]"
                            r"[0-9LMNPQRSTUV]{3}[A-Z]", t):
            return None, "Servono 16 caratteri (o le 11 cifre di una ditta)"
        return (t, "") if codice_fiscale_ok(t) else (None, "Il carattere di controllo non "
                                                           "torna")
    if tipo == "partita_iva":
        t = _cifre_cf(v)
        if t.startswith("IT") and len(t) == 13:
            t = t[2:]
        if not re.fullmatch(r"\d{11}", t):
            return None, "Servono 11 cifre"
        return (t, "") if partita_iva_ok(t) else (None, "La cifra di controllo non torna")
    if tipo == "iban":
        t = _cifre_cf(v)
        if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", t):
            return None, "Un IBAN comincia con il paese (IT) e due cifre"
        n = _IBAN_LUNGHEZZA.get(t[:2])
        if n and len(t) != n:
            return None, f"Un IBAN {t[:2]} ha {n} caratteri (qui {len(t)})"
        return (t, "") if iban_ok(t) else (None, "Il codice di controllo non torna")
    if tipo == "cap":
        t = re.sub(r"\s", "", str(v))
        return (t, "") if re.fullmatch(r"\d{5}", t) else (None, "Il CAP ha 5 cifre")
    if tipo == "provincia":
        t = str(v).strip()
        t = PROVINCE.get(t.lower(), t).upper().strip(" ()")
        return (t, "") if re.fullmatch(r"[A-Z]{2}", t) else (None, "La sigla ha 2 lettere")
    if tipo == "email":
        t = str(v).strip().lower()
        ok = (len(t) <= 254 and re.fullmatch(r"[^@\s]+@[^@\s.]+(\.[^@\s.]+)*\.[a-z]{2,}", t))
        return (t, "") if ok else (None, "Indirizzo email non valido")
    if tipo == "codice_destinatario":
        t = _cifre_cf(v)
        return (t, "") if re.fullmatch(r"[A-Z0-9]{7}", t) else (None, "Il codice "
                                                                      "destinatario ha 7 "
                                                                      "caratteri")
    return None, "Tipo di campo sconosciuto"


def campo(nome: str, etichetta: str, tipo: str = "testo", obbligatorio: bool = True,
          valore=None, **extra) -> dict:
    """Un campo del modulo (dati, mai codice: la pagina lo disegna con textContent)."""
    if tipo not in TIPI:
        raise ValueError(f"tipo di campo sconosciuto: {tipo}")
    c = {"nome": str(nome), "etichetta": str(etichetta)[:80], "tipo": tipo,
         "obbligatorio": bool(obbligatorio)}
    if valore not in (None, "", []):
        c["valore"] = valore
    for k in ("opzioni", "suggerimenti", "errore", "aiuto", "prezzi"):
        if extra.get(k) not in (None, "", []):
            c[k] = extra[k]
    if "opzioni" in c:
        c["opzioni"] = [str(o)[:80] for o in c["opzioni"]][:30]
    if "suggerimenti" in c:
        c["suggerimenti"] = [str(o)[:80] for o in c["suggerimenti"]][:60]
    return c


# ─────────────────────────── testo nei log ───────────────────────────

_OSCURA = [
    re.compile(r"\b[A-Z]{2}\s?\d{2}(?:\s?[A-Z0-9]){11,30}\b", re.I),               # IBAN
    re.compile(r"\b(?:[A-Z]\s?){6}(?:[0-9LMNPQRSTUV]\s?){2}[A-Z]\s?(?:[0-9LMNPQRSTUV]\s?){2}"
               r"[A-Z]\s?(?:[0-9LMNPQRSTUV]\s?){3}[A-Z]\b", re.I),                  # CF
    re.compile(r"[^\s@]+@[^\s@]+\.[a-z]{2,}", re.I),                                 # email
    re.compile(r"(?<![\d])(?:\d[\s.\-]?){10,}\d(?![\d])"),                           # P. IVA…
]


def oscura(testo):
    """Il testo senza codici fiscali, partite IVA, IBAN ed email (anche detti «0 1 2 …»):
    per il registro dei turni e il terminale di ciò che arriva scritto."""
    if not isinstance(testo, str):
        return testo
    for r in _OSCURA:
        testo = r.sub("******", testo)
    return testo


def oscura_tutto(x):
    """`oscura` su tutte le stringhe di una struttura (argomenti dei tool nel registro)."""
    if isinstance(x, str):
        return oscura(x)
    if isinstance(x, list):
        return [oscura_tutto(v) for v in x]
    if isinstance(x, dict):
        return {k: oscura_tutto(v) for k, v in x.items()}
    return x


# ─────────────────────────── moduli aperti ───────────────────────────

@dataclass
class Modulo:
    id: str
    chiave: str                     # «modello:fattura», «rubrica», «lavoro:L3»
    tool: str                       # il tool che l'ha chiesto (la voce lo richiama)
    persona: str                    # UserProfile.id di chi l'ha chiesto
    nome: str | None
    livello: str                    # il livello con cui l'ha chiesto (a voce)
    titolo: str
    domanda: str
    campi: list
    riprendi: object                # riprendi(valori, turno) -> risultato del tool
    mittente: object                # hub.Mittente per le schede
    creato: float = field(default_factory=time.time)
    scade: float = 0.0
    stato: str = "aperto"           # aperto | inviato | chiuso
    schermi: list = field(default_factory=list)


class Moduli:
    """I moduli aperti, per persona e chiave. Un modulo nuovo con la stessa chiave della
    stessa persona sostituisce il vecchio (la domanda è cambiata)."""

    def __init__(self, hub):
        self.hub = hub
        self._lock = threading.Lock()
        self._aperti: dict[str, Modulo] = {}

    def _durata(self) -> float:
        return max(60.0, float(getattr(self.hub.cfg, "schermi_moduli_s", 900.0)))

    def scheda(self, m: Modulo, nota: str = "") -> dict:
        resto = max(30.0, m.scade - time.time()) if m.stato == "aperto" else 120.0
        return nuova("modulo", m.titolo, PERSONALE, durata_s=resto,
                     chiave=f"modulo:{m.persona}:{m.chiave}", modulo=m.id, domanda=m.domanda,
                     campi=m.campi if m.stato == "aperto" else [], stato=m.stato, nota=nota)

    def apri(self, spec: dict, riprendi, mittente, tool: str, livello: str) -> dict:
        """Apre il modulo sugli schermi personali di chi l'ha chiesto. {"mostrato": True se
        almeno una pagina collegata l'ha ricevuto, "id", "motivo"}. Senza persona certa
        (ospite, zona grigia) non si apre: `destinatari` lo rifiuta."""
        persona = getattr(mittente, "persona", None)
        campi = [c for c in (spec.get("campi") or []) if isinstance(c, dict)][:MAX_CAMPI]
        if not persona or not campi or not getattr(self.hub.cfg, "schermi_scritto", True):
            return {"mostrato": False, "id": None, "motivo": "nessun_modulo"}
        m = Modulo(id=secrets.token_urlsafe(12), chiave=str(spec.get("chiave") or tool),
                   tool=tool, persona=persona, nome=getattr(mittente, "nome", None),
                   livello=livello, titolo=str(spec.get("titolo") or "Dati")[:120],
                   domanda=str(spec.get("domanda") or "")[:300], campi=campi,
                   riprendi=riprendi, mittente=mittente)
        m.scade = m.creato + self._durata()
        with self._lock:
            for k, vecchio in list(self._aperti.items()):
                if vecchio.persona == persona and vecchio.chiave == m.chiave:
                    del self._aperti[k]
            self._aperti[m.id] = m
        r = self.hub.invia(self.scheda(m), mittente, forza=True)
        m.schermi = list(r.get("schermi") or [])
        if not r.get("destinatari"):
            # Nessuno schermo personale suo (o zona grigia): il modulo non esiste per nessuno
            with self._lock:
                self._aperti.pop(m.id, None)
            return {"mostrato": False, "id": None, "motivo": r.get("motivo") or ""}
        # Uno schermo personale spento: il modulo resta nella sua cronologia e si può inviare
        # quando la pagina si ricollega
        return {"mostrato": bool(m.schermi), "id": m.id, "motivo": r.get("motivo") or ""}

    def aperto(self, mid: str) -> Modulo | None:
        with self._lock:
            m = self._aperti.get(str(mid or ""))
            if m is not None and (m.stato != "aperto" or time.time() > m.scade):
                self._aperti.pop(m.id, None)
                return None
            return m

    def aperti(self, persona: str | None = None) -> list[Modulo]:
        with self._lock:
            return [m for m in self._aperti.values() if m.stato == "aperto"
                    and time.time() <= m.scade and (persona is None or m.persona == persona)]

    def chiudi(self, m: Modulo, nota: str, stato: str = "chiuso"):
        with self._lock:
            self._aperti.pop(m.id, None)
        m.stato = stato
        try:
            self.hub.invia(self.scheda(m, nota), m.mittente, forza=True)
        except Exception:  # noqa: BLE001 — lo schermo non deve fermare la voce
            pass

    def chiudi_per_tool(self, persona: str | None, tool: str, nota: str,
                        chiave: str | None = None) -> int:
        """La persona ha risposto in un altro modo (a voce): i suoi moduli di quel tool si
        chiudono, e le pagine lo mostrano."""
        if not persona:
            return 0
        via = [m for m in self.aperti(persona) if m.tool == tool
               and (chiave is None or m.chiave == chiave)]
        for m in via:
            self.chiudi(m, nota)
        return len(via)

    def valida(self, mid: str, persona: str | None, valori) -> tuple[Modulo | None, dict, dict]:
        """(modulo, valori puliti, errori {campo: frase}). Modulo None = non c'è più, non è di
        questa persona o è scaduto (errori["_"] dice quale)."""
        m = self.aperto(mid)
        if m is None:
            return None, {}, {"_": "Questo modulo non è più aperto."}
        if not persona or persona != m.persona:
            return None, {}, {"_": "Questo modulo è di un'altra persona."}
        if not isinstance(valori, dict):
            return m, {}, {"_": "Dati non validi."}
        puliti, errori = {}, {}
        for c in m.campi:
            v, err = controlla_campo(c, valori.get(c["nome"]))
            if err:
                errori[c["nome"]] = err
            elif v is not None:
                puliti[c["nome"]] = v
        return m, puliti, errori


# ─────────────────────────── ingresso (pagina → ciclo) ───────────────────────────

class Ingresso:
    """Ciò che arriva dalle pagine per il ciclo principale: testo scritto e moduli inviati.
    `metti` non blocca (coda piena = False); `sveglia` è il due_event di main.py, che
    interrompe l'attesa di una frase quando nessuno sta parlando."""

    MAX = 16

    def __init__(self):
        self.coda: queue.Queue = queue.Queue(maxsize=self.MAX)
        self.sveglia = None

    def metti(self, item: dict) -> bool:
        try:
            self.coda.put_nowait(item)
        except queue.Full:
            return False
        if self.sveglia is not None:
            try:
                self.sveglia()
            except Exception:  # noqa: BLE001
                pass
        return True

    def prendi(self) -> dict | None:
        try:
            return self.coda.get_nowait()
        except queue.Empty:
            return None

    def vuoto(self) -> bool:
        return self.coda.empty()


# ─────────────────────────── per i tool ───────────────────────────

def _hub(ctx):
    hub = getattr(ctx, "schermi", None)
    return hub if hub is not None and getattr(hub, "moduli", None) is not None else None


_PRONOME_DICI = re.compile(r"(?<!\w)([Mm]e) (l[aeio]) (ri)?dici\?$")


def domanda_schermo(frase: str) -> str:
    """La domanda detta quando il modulo è sullo schermo: «Me li dici?» → «Me li dici, o li
    scrivi sullo schermo?». La frase finisce sempre con «?» (resta l'azione in sospeso)."""
    f = frase.rstrip()
    if not f.endswith("?"):
        return f + " Puoi dirmelo o scriverlo sullo schermo."
    # «Me li/lo/la/le (ri)dici?» in fondo, anche minuscolo dopo i due punti («…: me la
    # ridici?»): il pronome resta quello della domanda (04/10: «Me le dici?» e «Me la
    # dici?» dei modelli di documento con un dato solo cadevano sulla frase generica).
    m = _PRONOME_DICI.search(f)
    if m:
        me, pron, ri = m.group(1), m.group(2), m.group(3) or ""
        return f[:m.start()] + f"{me} {pron} {ri}dici, o {pron} scrivi sullo schermo?"
    return f[:-1] + ", o puoi scriverlo sullo schermo?"


def offri(ctx, res: dict, tool: str, riprendi, livello: str | None = None) -> dict:
    """Il risultato di un tool con `modulo` (la specifica dei campi): lo toglie (non è per il
    modello), apre il modulo sugli schermi personali di chi parla e, se una pagina l'ha
    ricevuto, cambia la frase («… o li scrivi sullo schermo?»). Senza schermi il risultato
    resta quello di sempre."""
    spec = res.pop("modulo", None) if isinstance(res, dict) else None
    hub = _hub(ctx)
    if not spec or hub is None or riprendi is None:
        return res
    lvl = livello or getattr(getattr(ctx, "speaker_ctx", None), "current_level", "ospite")
    try:
        r = hub.moduli.apri(spec, riprendi, hub.mittente(ctx), tool, lvl)
    except Exception as e:  # noqa: BLE001 — lo schermo non deve fermare il tool
        print(f"   [SCHERMI] modulo non aperto: {type(e).__name__}", flush=True)
        return res
    # Si offre lo schermo solo se chi parla può scriverci adesso (conversazione a voce, 05/10)
    if r.get("mostrato") and _scrive(hub, r):
        from ..tools.spec import note_rule
        note_rule(ctx, "modulo_sullo_schermo")
        for k in ("frase", "conferma", "risposta_finale"):
            if isinstance(res.get(k), str) and res[k]:
                res[k] = spec.get("frase_schermo") or domanda_schermo(res[k])
    return res


def _scrive(hub, r) -> bool:
    m = hub.moduli.aperto(r.get("id"))
    f = getattr(hub, "scrittura_persona", None)
    return m is not None and (f is None or f(m.persona))


def chiudi_per_voce(ctx, tool: str, chiave: str | None = None) -> int:
    """Il tool è stato richiamato (la risposta è arrivata a voce, o scritta nella casella): i
    moduli di chi parla per quel tool si chiudono."""
    hub = _hub(ctx)
    if hub is None:
        return 0
    sc = getattr(ctx, "speaker_ctx", None)
    name = getattr(sc, "current_speaker", None)
    speakers = getattr(ctx, "speakers", None)
    prof = speakers.get(name) if name and speakers else None
    nota = ("Hai risposto scrivendo a Calliope." if getattr(sc, "identified_by", None)
            == "schermo" else "Hai risposto a voce.")
    return hub.moduli.chiudi_per_tool(getattr(prof, "id", None), tool, nota, chiave)


# ─────────────────────────── per il ciclo principale ───────────────────────────

def completa(hub, item: dict, brain, turno: int) -> dict:
    """Un modulo inviato dalla pagina (già validato dal server): i valori vanno al tool che
    l'aveva chiesto, senza modello. Restituisce {"frase", "rec"} per main.py: la frase da
    dire e i campi del registro dei turni (solo i nomi dei campi)."""
    m: Modulo | None = item.get("_modulo")
    valori = item.get("valori") or {}
    rec = {"canale": "modulo", "modulo": getattr(m, "chiave", None),
           "campi": sorted(valori), "livello": getattr(m, "livello", None)}
    if m is None or m.stato != "aperto":
        return {"frase": "", "rec": dict(rec, esito="modulo_chiuso")}
    hub.moduli.chiudi(m, "Inviato: ti rispondo.", stato="inviato")
    try:
        res = m.riprendi(valori, turno) or {}
    except Exception as e:  # noqa: BLE001 — un errore del tool non ferma la voce
        print(f"   [SCHERMI] modulo «{m.chiave}»: {type(e).__name__}", flush=True)
        res = {"ok": False, "frase": "Non sono riuscita a usare i dati che hai scritto: "
                                     "riprova a voce."}
    frase = str(res.get("risposta_finale") or res.get("frase") or res.get("conferma")
                or "").strip()
    # Le schede del risultato (il documento pronto…) vanno agli schermi di chi l'ha chiesto
    for card in [c for c in (res.get("scheda"), res.get("schede")) if c]:
        for c in (card if isinstance(card, list) else [card]):
            try:
                hub.invia(c, m.mittente)
            except Exception:  # noqa: BLE001
                pass
    # Un'altra domanda di dati (un codice che non torna, il cliente da scegliere): un altro
    # modulo con lo stesso modo di riprendere
    if isinstance(res.get("modulo"), dict):
        r = hub.moduli.apri(res["modulo"], m.riprendi, m.mittente, m.tool, m.livello)
        if r.get("mostrato") and frase:
            frase = res["modulo"].get("frase_schermo") or domanda_schermo(frase)
    # Nella storia del modello: che i dati sono arrivati scritti (mai i valori), e la frase
    if brain is not None:
        nomi = ", ".join(c["etichetta"].lower() for c in m.campi if c["nome"] in valori)
        brain.pending = None          # la domanda a voce ha avuto risposta
        brain.history.append({"role": "user", "content": f"(Ho scritto sullo schermo i dati "
                                                        f"per «{m.titolo}»: {nomi}.)"})
        if frase:
            brain.record_announcement(frase, res.get("in_sospeso"), fonte=None)
    return {"frase": frase, "rec": dict(rec, esito="modulo",
                                        ok=res.get("ok", True) is not False)}


def annuncio_lavoro(hub, item: dict, lavori, brain) -> str:
    """Un lavoro dell'agente che fa una domanda (main.py, annunci): la domanda diventa anche un
    modulo sullo schermo personale di chi l'ha chiesto. Restituisce il messaggio da dire."""
    msg = item["messaggio"]
    if hub is None or getattr(hub, "moduli", None) is None or not item.get("modulo") \
            or not item.get("chi"):
        return msg
    from .hub import Mittente
    lid = item.get("id")
    mitt = Mittente(persona=item["chi"], nome=item.get("chi_nome"), livello="familiare",
                    certo=True, stanza=None)

    def riprendi(valori, turno, lid=lid):
        lav = next((lv for lv in lavori.in_attesa() if lv.id == lid), None)
        if lav is None:
            return {"ok": False, "frase": "Quel lavoro non aspetta più una risposta."}
        frase = lavori.rispondi(lav, valori.get("risposta") or "")
        return {"ok": frase is not None,
                "frase": frase or "Quel lavoro non aspetta più una risposta."}
    try:
        r = hub.moduli.apri(item["modulo"], riprendi, mitt, "lavoro_rispondi", "familiare")
    except Exception:  # noqa: BLE001
        return msg
    if r.get("mostrato"):
        # Lo scritto vale solo durante una conversazione a voce (05/10): un annuncio può
        # arrivare a conversazione chiusa, e allora prima bisogna chiamarla
        if _scrive(hub, r):
            msg = msg.rstrip() + " Puoi rispondermi a voce o scrivere la risposta sullo schermo."
        else:
            msg = msg.rstrip() + (" Puoi rispondermi a voce, oppure chiamarmi e scrivere la "
                                  "risposta sullo schermo.")
        if brain is not None and item.get("in_sospeso"):
            brain.set_pending(item["in_sospeso"])     # il messaggio non finisce più con «?»
    return msg
