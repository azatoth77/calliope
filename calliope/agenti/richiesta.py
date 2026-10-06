"""
L'analisi della richiesta prima di partire (06/10/2026, richiesta di Dario dopo il lavoro L1
della DGX: «creami un'estensione che mi fa una ricerca sulle città di una regione prendendole
da Wikipedia» → 5 pagine scaricate, 6 script d'esplorazione, 24 passate finite e nessuna
estensione, perché la richiesta non era una specifica: quali città? «principali» secondo cosa?
da quale tabella?). Niente spinte a metà lavoro: la domanda si fa **prima**, al momento della
proposta.

`estensione_crea` e `delega_lavoro` di tipo codice chiamano `Analizzatore.analizza` prima di
creare il lavoro. Il modello è quello dell'agente (qwen3.6 su vLLM sulla DGX), con l'output
strutturato (schema JSON, decodifica guidata), senza ragionamento, con un tempo massimo
(`agenti_analisi_s`, 10 s compresa la verifica della fonte); oltre, o con un errore, si procede
come prima (esito «nessuna»). Il contesto è la conversazione recente (ToolContext.storia).

Lista di controllo chiusa per tipo (`PUNTI`): estensione = input, output, fonte dei dati, caso
«non trovato», permessi; codice = input, output, dati della persona, linguaggio. Cinque esiti
(banco `prove/banco_richieste.py`, etichette decise da Dario il 06/10):
- **chiara**: si procede come oggi;
- **raffinabile**: la conversazione completa la richiesta; la proposta dice la specifica in una
  frase prima di «Procedo?» e il compito all'agente è quello raffinato;
- **vaga**: mancano dati che sa solo la persona; al più 2 domande a voce (azione in sospeso come
  le altre), tutte sul modulo dello schermo personale se c'è;
- **gia_fatto** («c'è già»): una funzione di Calliope lo fa già (dal registro dei tool, mai da un
  elenco scritto a mano): lo dice e come chiederlo, senza costruire un doppione;
- **impossibile** («impossibile qui»): serve qualcosa che la sandbox o la porta delle estensioni
  non hanno (rete di casa, file del PC…): lo dice subito, senza domande.

Per un'estensione che legge internet l'analizzatore indica la fonte (`fonte_url`), e una
lettura rapida con la rete pubblica di Calliope (`web.rete.RetePubblica`, gli stessi controlli
delle estensioni) verifica che esista: se non risponde la richiesta diventa vaga («da quale
sito prendo i dati?»).

Una sola analisi per richiesta: dopo le domande, la risposta (il modello della voce richiama il
tool) si analizza di nuovo senza l'esito vaga; dopo «c'è già» o «impossibile qui», il «sì,
comunque» procede come oggi (`recente`).
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field

ESITI = ("chiara", "raffinabile", "vaga", "gia_fatto", "impossibile")
PUNTI = {
    "estensione": ("input", "output", "fonte", "non_trovato", "permessi"),
    "codice": ("input", "output", "dati_persona", "linguaggio"),
}
PUNTI_DETTI = {
    "input": "cosa entra (i dati che dà chi la usa)",
    "output": "cosa esce (cosa dice o mostra, quanto)",
    "fonte": "da dove vengono i dati (quale sito, pagina o tabella)",
    "non_trovato": "cosa fare se il dato non c'è",
    "permessi": "cosa le serve oltre a internet pubblico (casa, liste, invii)",
    "dati_persona": "valori della persona, della casa o dell'azienda che non si inventano",
    "linguaggio": "il linguaggio, se conta (altrimenti Python)",
}
# Tool che non sono «funzioni» da proporre al posto di un lavoro: i lavori stessi, le
# installazioni, la gestione delle persone e di Calliope
NON_FUNZIONI = frozenset({
    "delega_lavoro", "estensione_crea", "estensioni_gestisci", "lavori_stato",
    "lavori_annulla", "lavori_rispondi", "lavori_esegui", "installa_proponi", "installa_avvia",
    "installa_gestisci", "registra_utente", "rinomina_interlocutore", "elenca_utenti",
    "elenca_voci", "chi_parla", "minore_gestisci", "richiesta_tutore", "dimentica",
    "conversazioni_dimentica", "calliope_stato", "schermo_gestisci", "cambia_voce",
})
ATTESA = "Un attimo, guardo bene cosa mi chiedi."
ATTESA_DOPO_S = 1.2           # la frase d'attesa solo se l'analisi va oltre
VERIFICA_MAX_S = 4.0          # la lettura della fonte, dentro il tempo dell'analisi
MAX_DOMANDE_VOCE = 2


@dataclass
class Esito:
    esito: str = "nessuna"    # uno di ESITI, o «nessuna» (ripiego: si procede come oggi)
    specifica: str = ""
    domande: list = field(default_factory=list)
    mancano: list = field(default_factory=list)
    nome: str = ""
    fonte_url: str = ""
    fonte_ok: bool | None = None
    tool: str = ""
    come_chiederlo: str = ""
    motivo: str = ""
    secondi: float = 0.0
    errore: str = ""

    def per_registro(self) -> dict:
        d = {"esito": self.esito, "s": round(self.secondi, 2)}
        for k in ("mancano", "domande", "specifica", "tool", "fonte_ok", "errore"):
            v = getattr(self, k)
            if v not in (None, "", []):
                d[k] = v
        return d


# ─────────────────────────── testo per il modello ───────────────────────────

def funzioni(strumenti) -> list[tuple[str, str]]:
    """Le funzioni che Calliope ha già, dal registro dei tool (estensioni comprese: est_*):
    (nome, prima frase della descrizione). Senza registro, i nomi della politica."""
    out = []
    if strumenti is not None and hasattr(strumenti, "all_schemas"):
        for s in strumenti.all_schemas():
            fn = s.get("function") or {}
            nome = fn.get("name") or ""
            if not nome or nome in NON_FUNZIONI:
                continue
            desc = re.sub(r"\s+", " ", str(fn.get("description") or "")).strip()
            prima = re.split(r"(?<=[.;:])\s", desc, maxsplit=1)[0]
            out.append((nome, prima[:160]))
        return out
    from .. import politica
    return [(n, "") for n, c in sorted(politica.CLASSI.items())
            if n not in NON_FUNZIONI and c.classe in (politica.SICURO, politica.AZIONE)]


def capacita(cfg, tipo: str, linguaggi=("python",)) -> str:
    """Cosa si può fare qui, dal codice (contratto delle estensioni, linguaggi della sandbox)."""
    if tipo == "estensione":
        from ..estensioni import contratto as c
        righe = ["Un'estensione è un piccolo programma Python che resta e si usa a voce; gira "
                 "in un contenitore isolato.", "Da sola: " + "; ".join(
                     f"{v}" for v in c.DA_SOLA.values()) + ".",
                 "Chiedendo a Calliope: " + "; ".join(
                     cosa for _, _, cosa in c.PORTA.values()) + "."]
        righe.append("Impossibile: " + "; ".join(cosa for cosa, _ in c.IMPOSSIBILI.values())
                     + ".")
        return "\n".join(righe)
    from .linguaggi import LINGUAGGI
    nomi = [n for n in linguaggi if n in LINGUAGGI] or ["python"]
    return ("Un lavoro di codice: l'agente scrive ed esegue il programma in una sandbox isolata, "
            f"linguaggi {', '.join(nomi)}; il programma si esegue una volta e si può rieseguire "
            "a voce con dei valori.\nLa sandbox: niente rete (né internet né la rete di casa), "
            "niente pip, niente file del PC della persona (solo un file che la persona manda "
            "all'agente), niente programmi con finestre, niente orari fissi.\nImpossibile qui: "
            "collegarsi a dispositivi di casa (inverter, router, NAS, stampanti), leggere o "
            "salvare i file e le cartelle del PC (backup, rinomina di cartelle), mandare email o "
            "messaggi, restare acceso in secondo piano.")


SISTEMA = """Sei l'analista delle richieste di lavoro di Calliope, un'assistente vocale di casa. Prima che un agente programmatore cominci, decidi se la richiesta è una specifica sufficiente. Non scrivi codice e non rispondi alla persona: compili il JSON.

Lavoro: {tipo_detto}.
Lista di controllo: {punti}.

Esiti:
- chiara: si capisce cosa entra, cosa esce e da dove vengono i dati. I dettagli secondari li sceglie l'agente e NON sono mancanze: il linguaggio (Python se non detto), il formato dell'uscita, cosa dire se un dato non si trova, i valori d'esempio quando la persona chiede di inventarli, il comportamento ovvio di un calcolo noto. Una fonte pubblica nota e stabile va bene anche se la persona non la nomina (Wikipedia per una tabella o una voce precisa, i cambi di riferimento della BCE, un servizio meteo pubblico come Open-Meteo).
- raffinabile: manca qualcosa, ma la conversazione recente lo dice (una città, un file mandato, dei numeri, dei nomi, l'estensione usata poco prima). In specifica la richiesta completa con quei dati.
- vaga: manca qualcosa che sa solo la persona e che la conversazione non dice: un suo dato o della sua casa o azienda (tariffe, stipendi, rendite, importi: MAI inventarli né usare valori tipici), quale cosa precisa (quale linea e fermata, quale file, quale negozio o sito, quale testata), cosa deve fare di preciso una richiesta molto generica, oppure la richiesta ha letture molto diverse («le città» di una regione: tutti i comuni? i capoluoghi? sopra quanti abitanti? «principali» secondo cosa? da quale pagina o tabella? cosa dire di ognuna?). In domande da 1 a 3 domande brevi a voce, una per punto, la più importante prima.
- gia_fatto: una delle funzioni che Calliope ha già (elenco sotto) fa la stessa cosa per intero: in tool il suo nome esatto, in come_chiederlo una frase d'esempio con cui chiederla a voce.
- impossibile: serve qualcosa che qui non si può fare (elenco sotto): in motivo il perché in una frase breve da dire alla persona.

Cosa si può fare qui:
{capacita}

Funzioni che Calliope ha già (nome: cosa fa):
{funzioni}

Campi:
- mancano: i punti della lista di controllo che mancano davvero (vuoto per chiara).
- specifica: per chiara e raffinabile una frase sola con input, output e fonte, al più 40 parole; vuota per gli altri esiti.
- nome: {nome_regola}
- fonte_url: per un'estensione che prende dati da internet, l'indirizzo pubblico esatto della pagina o dell'API, se lo sai (es. https://it.wikipedia.org/wiki/Regioni_d%27Italia); altrimenti vuoto.
- tool, come_chiederlo: solo per gia_fatto. motivo: solo per impossibile.
Tutto in italiano, frasi da dire a voce: niente markdown, elenchi o indirizzi nelle domande e nel motivo."""


def schema(tipo: str, senza_domande: bool = False) -> dict:
    esiti = [e for e in ESITI if not (senza_domande and e == "vaga")]
    stringa = {"type": "string"}
    return {"type": "object", "additionalProperties": False,
            "required": ["mancano", "esito", "specifica", "domande", "nome", "fonte_url",
                         "tool", "come_chiederlo", "motivo"],
            "properties": {
                "mancano": {"type": "array", "items": {"type": "string",
                                                       "enum": list(PUNTI[tipo])}},
                "esito": {"type": "string", "enum": esiti},
                "specifica": stringa,
                "domande": {"type": "array", "items": stringa, "maxItems": 3},
                "nome": stringa, "fonte_url": stringa, "tool": stringa,
                "come_chiederlo": stringa, "motivo": stringa}}


def _conversazione(storia, max_voci: int = 8, max_car: int = 400) -> str:
    righe = []
    for voce in list(storia or [])[-max_voci:]:
        try:
            ruolo, testo = voce[0], voce[1]
        except (TypeError, IndexError, KeyError):
            continue
        chi = "Persona" if ruolo == "user" else "Calliope"
        t = re.sub(r"\s+", " ", str(testo or "")).strip()
        if t:
            righe.append(f"{chi}: {t[:max_car]}")
    return "\n".join(righe) or "(nessuna)"


def messaggi(cfg, tipo: str, compito: str, storia=(), detto: str = "", strumenti=None,
             linguaggi=("python",), nota: str = "", senza_domande: bool = False) -> list[dict]:
    fz = funzioni(strumenti)
    sistema = SISTEMA.format(
        tipo_detto=("un'estensione nuova di Calliope (una funzione permanente)"
                    if tipo == "estensione" else "un programma da scrivere ed eseguire una volta"),
        punti=", ".join(f"{p} = {PUNTI_DETTI[p]}" for p in PUNTI[tipo]),
        capacita=capacita(cfg, tipo, linguaggi),
        funzioni="\n".join(f"- {n}: {d}" if d else f"- {n}" for n, d in fz) or "(nessuna)",
        nome_regola=("un nome breve in italiano, 2-4 parole minuscole (es. «città della "
                     "regione»)." if tipo == "estensione" else "vuoto."))
    utente = (f"Conversazione recente:\n{_conversazione(storia)}\n\n"
              f"Richiesta di lavoro: «{str(compito).strip()}»")
    d = str(detto or "").strip()
    if d and d not in compito:
        utente += f"\nFrase detta dalla persona: «{d}»"
    if nota:
        utente += "\n" + nota
    if senza_domande:
        utente += ("\nLe domande le hai già fatte e la persona ha risposto: l'esito vaga non c'è "
                   "più, usa quello che sai (raffinabile con la specifica completa).")
    return [{"role": "system", "content": sistema}, {"role": "user", "content": utente}]


# ─────────────────────────── risposta ───────────────────────────

def _pulisci(t, max_car: int = 300) -> str:
    t = re.sub(r"[*_#`>|]+", " ", str(t or ""))
    t = re.sub(r"https?://\S+", "", t)
    return re.sub(r"\s+", " ", t).strip()[:max_car]


def interpreta(testo: str, tipo: str, senza_domande: bool = False) -> Esito:
    """Il JSON del modello → Esito (ripiego «nessuna» se non si legge)."""
    try:
        d = json.loads(testo)
    except (TypeError, ValueError):
        m = re.search(r"\{.*\}", str(testo or ""), re.S)
        try:
            d = json.loads(m.group(0)) if m else None
        except ValueError:
            d = None
    if not isinstance(d, dict):
        return Esito(errore="risposta non JSON")
    esito = str(d.get("esito") or "").strip().lower()
    if esito not in ESITI:
        return Esito(errore=f"esito sconosciuto: {esito[:30]}")
    domande = [_pulisci(x, 200) for x in (d.get("domande") or []) if _pulisci(x, 200)][:3]
    domande = [q if q.endswith("?") else q.rstrip(".") + "?" for q in domande]
    e = Esito(esito=esito, specifica=_pulisci(d.get("specifica"), 400), domande=domande,
              mancano=[p for p in (d.get("mancano") or []) if p in PUNTI[tipo]],
              nome=_pulisci(d.get("nome"), 60).lower().strip(" .«»\"'"),
              fonte_url=str(d.get("fonte_url") or "").strip()[:300],
              tool=str(d.get("tool") or "").strip(),
              come_chiederlo=_pulisci(d.get("come_chiederlo"), 160),
              motivo=_pulisci(d.get("motivo"), 300))
    if e.esito == "vaga" and senza_domande:
        e.esito = "raffinabile" if e.specifica else "chiara"
    if e.esito == "vaga" and not e.domande:
        # Vaga senza domande da fare: niente da chiedere, si procede
        e.esito = "raffinabile" if e.specifica else "chiara"
    if e.esito == "raffinabile" and not e.specifica:
        e.esito = "chiara"
    if e.esito == "impossibile" and not e.motivo:
        e.esito = "chiara"
    return e


# ─────────────────────────── l'analizzatore ───────────────────────────

class Analizzatore:
    """Una richiesta di lavoro → Esito, con il client dell'agente di `lavori` (Lavori). La voce
    aspetta al più `agenti_analisi_s`: il tool lo chiama dal turno della voce."""

    def __init__(self, cfg, lavori, log=print):
        self.cfg = cfg
        self.lavori = lavori
        self.log = log
        self.tempo_s = float(getattr(cfg, "agenti_analisi_s", 10.0) or 10.0)
        self._lock = threading.Lock()
        self._recenti: dict = {}        # persona → {"turno", "tipo", "esito", "compito", …}
        self.rete = None                 # RetePubblica (le estensioni la passano), o creata qui

    # ── memoria di una richiesta (una sola analisi) ──
    def ricorda(self, persona, tipo: str, turno: int, compito: str, esito: Esito):
        with self._lock:
            self._recenti[persona or "?"] = {"turno": int(turno), "tipo": tipo,
                                             "esito": esito.esito, "compito": compito,
                                             "domande": list(esito.domande),
                                             "tool": esito.tool, "quando": time.monotonic()}

    def recente(self, persona, tipo: str, turno: int) -> dict | None:
        """L'analisi della richiesta precedente della stessa persona e dello stesso tipo, se è
        ancora la stessa conversazione (proposta_valida, come le azioni in sospeso); la consuma."""
        from ..conferme import proposta_valida, secondi_validi
        with self._lock:
            r = self._recenti.pop(persona or "?", None)
        if r is None or r["tipo"] != tipo:
            return None
        if time.monotonic() - r["quando"] > secondi_validi(self.cfg):
            return None
        if not proposta_valida(self.cfg, r["turno"], int(turno)):
            return None
        return r

    def dimentica(self, persona):
        with self._lock:
            self._recenti.pop(persona or "?", None)

    # ── analisi ──
    def _cliente(self):
        lav = self.lavori
        cliente = lav.cliente
        arb = getattr(lav, "arbitro", None)
        if arb is not None and getattr(arb, "condiviso", False):
            # Stessa GPU della voce: la richiesta nasce dal turno della voce (come lo scrittore
            # dell'ufficio), niente pausa del server in questo turno
            from .arbitro import ClienteCedevole
            cliente = ClienteCedevole(cliente, arb, dalla_voce=True)
        return cliente

    def analizza(self, tipo: str, compito: str, storia=(), detto: str = "", strumenti=None,
                 nota: str = "", senza_domande: bool = False, attesa=None) -> Esito:
        """L'esito per la richiesta, entro `tempo_s`; `attesa(frase)` se va oltre
        ATTESA_DOPO_S. Mai un'eccezione: un guasto è l'esito «nessuna»."""
        t0 = time.monotonic()
        fine = t0 + self.tempo_s
        imp = self.lavori.imp
        linguaggi = tuple(getattr(self.lavori, "isolamenti", {}) or ()) or ("python",)
        try:
            msgs = messaggi(self.cfg, tipo, compito, storia, detto, strumenti, linguaggi, nota,
                            senza_domande)
        except Exception as e:  # noqa: BLE001 — l'analisi è un di più
            return Esito(errore=f"prompt: {type(e).__name__}: {e}", secondi=0.0)
        body = {"model": imp.modello, "messages": msgs, "think": False,
                "format": schema(tipo, senza_domande),
                "options": {"temperature": 0.0, "num_predict": 700,
                            "num_ctx": _num_ctx(self.lavori)},
                "keep_alive": getattr(self.cfg, "llm_keep_alive", None) or "30m"}

        out: dict = {}
        tid: list = []
        cliente = self._cliente()

        def gira():
            tid.append(threading.get_ident())
            try:
                out["r"] = cliente.chat(body)
            except Exception as e:  # noqa: BLE001
                out["errore"] = f"{type(e).__name__}: {str(e)[:200]}"
        th = threading.Thread(target=gira, daemon=True, name="analisi-richiesta")
        th.start()
        th.join(ATTESA_DOPO_S)
        if th.is_alive() and attesa is not None:
            try:
                attesa(ATTESA)
            except Exception:  # noqa: BLE001 — la frase non deve fermare l'analisi
                pass
        th.join(max(0.0, fine - time.monotonic()))
        if th.is_alive():
            if tid:
                from .arbitro import _interrompi
                _interrompi(self.lavori.cliente, tid[0])
            return Esito(errore="tempo scaduto", secondi=time.monotonic() - t0)
        if "errore" in out:
            return Esito(errore=out["errore"], secondi=time.monotonic() - t0)
        e = interpreta((out.get("r") or {}).get("content", ""), tipo, senza_domande)
        if tipo == "estensione" and e.esito in ("chiara", "raffinabile") and \
                e.fonte_url.startswith(("http://", "https://")):
            resto = fine - time.monotonic()
            e.fonte_ok = self.verifica_fonte(e.fonte_url, min(VERIFICA_MAX_S, resto)) \
                if resto > 0.5 else None
            if e.fonte_ok is False and not senza_domande:
                # La fonte che l'analizzatore conosceva non risponde: chi la usa sa da dove
                # prendere i dati (06/10, Dario: E11 del banco, CAP → comune)
                e.esito = "vaga"
                e.mancano = sorted(set(e.mancano) | {"fonte"})
                e.domande = ["Non ho trovato una fonte pubblica che risponda: da quale sito "
                             "prendo i dati?"]

        e.secondi = time.monotonic() - t0
        return e

    def verifica_fonte(self, url: str, timeout_s: float) -> bool | None:
        """La fonte esiste? Una lettura con la rete pubblica (solo internet pubblico, tetto al
        minuto, registro delle uscite). None se non si può dire (indirizzo con dati personali,
        tetto raggiunto)."""
        from ..web import pagina
        from ..web.privacy import Ripulitore, privati_da_config
        from ..web.rete import TIPI_DATI
        from urllib.parse import unquote
        _, tolti = Ripulitore([], privati_da_config(self.cfg)).pulisci(
            re.sub(r"[/?&=#:+_.-]+", " ", unquote(url)))
        if set(tolti) - {"numero"}:
            return None
        rete = self.rete or getattr(getattr(self.lavori, "agente", None), "rete", None)
        if rete is None:
            from ..estensioni import cartella
            from ..web.rete import RetePubblica
            rete = self.rete = RetePubblica(self.cfg, cartella(self.cfg) / "uscite.jsonl",
                                            log=self.log)
        try:
            rete.richiesta(url, {"origine": "analisi"}, max_byte=1_500_000,
                           timeout_s=max(0.5, timeout_s), tipi=TIPI_DATI)
            return True
        except pagina.PaginaVietata as e:
            return None if "troppe richieste" in str(e) else False
        except pagina.PaginaNonLetta as e:
            return True if "troppo grande" in str(e) else False
        except Exception:  # noqa: BLE001
            return None


def _num_ctx(lavori) -> int:
    ag = getattr(lavori, "agente", None)
    try:
        return int(ag.num_ctx()) if ag is not None and hasattr(ag, "num_ctx") else 32768
    except Exception:  # noqa: BLE001
        return 32768


# ─────────────────────────── frasi ───────────────────────────

def frase_domande(domande: list[str], schermo: bool = False) -> str:
    """Le domande a voce: al più MAX_DOMANDE_VOCE (le altre solo sullo schermo)."""
    qs = [q.strip() for q in domande if q.strip()][:MAX_DOMANDE_VOCE]
    if not qs:
        return ""
    if len(qs) == 1:
        testo = "Prima di cominciare mi serve sapere una cosa. " + qs[0]
    else:
        testo = "Prima di cominciare mi servono due cose. " + " ".join(qs)
    if schermo and len(domande) > len(qs):
        testo += " Le altre domande le trovi sullo schermo."
    return testo


def frase_impossibile(motivo: str) -> str:
    m = motivo.strip().rstrip(".")
    return f"Questo qui non posso farlo: {m[:1].lower() + m[1:]}." if m else \
        "Questo qui non posso farlo."
