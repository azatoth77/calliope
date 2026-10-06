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
    "dati_persona": ("valori fissi della persona, della casa o dell'azienda che il programma "
                     "usa e che non si inventano (tariffe, stipendi, rendite); le preferenze "
                     "di forma non sono dati della persona"),
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
    stati: dict = field(default_factory=dict)   # punto → detto | dal_contesto | …

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
            # Le ricerche (internet, documenti di casa, conversazioni, rubrica: dati non fidati
            # o riservati, dalla loro ToolSpec) trovano dati, non fanno il lavoro chiesto
            spec = strumenti.get(nome) if hasattr(strumenti, "get") else None
            if getattr(spec, "non_fidato", False) or getattr(spec, "riservato", False):
                continue
            desc = re.sub(r"\s+", " ", str(fn.get("description") or "")).strip()
            # L'inizio della descrizione, a una fine di frase entro 220 caratteri
            corto = desc[:220]
            fine = max(corto.rfind(". "), corto.rfind("; "))
            out.append((nome, corto[:fine + 1] if len(desc) > 220 and fine > 60 else corto))
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


SISTEMA = """Sei l'analista delle richieste di lavoro di Calliope, un'assistente vocale di casa. Prima che un agente programmatore cominci, controlli se la richiesta basta per lavorare. Non scrivi codice e non rispondi alla persona: compili il JSON, campo per campo, nell'ordine.

Lavoro: {tipo_detto}

1. impossibile: se serve qualcosa che qui non si può fare (vedi «Cosa si può fare qui»), il perché in una frase breve da dire alla persona; altrimenti vuoto.
2. punti: per ogni punto della lista di controllo uno stato:
   - detto: la richiesta lo dice;
   - dal_contesto: non lo dice la richiesta ma lo dice la conversazione recente (una città, un file mandato, dei numeri, dei nomi, l'estensione usata poco prima);
   - scelta_ragionevole: lo sceglie l'agente senza tradire quello che la persona vuole;
   - manca: lo sa solo la persona e cambia il risultato.
   Sono scelta_ragionevole: il linguaggio (Python se non detto); come si passano i dati e come si mostra il risultato (tabella, elenco, frase, totali); cosa dire se un dato non si trova; l'unità di arrivo ovvia di una conversione; il tipo di calcolo e i valori quando la persona chiede di inventarli; la logica di un calcolo o di un controllo noto; permessi che non servono. {nota_tipo}
   Sono manca: un valore fisso della persona, della sua casa o azienda che il lavoro usa (la tariffa della sua azienda, lo stipendio di Luca, la rendita della casa: MAI inventarli né usare valori tipici); quale cosa precisa tra tante (quale file suo, quale linea di quale azienda, quale negozio, quale testata); lo scopo di una richiesta molto generica («un programma per la contabilità»); una richiesta che si legge in modi molto diversi («le città di una regione»: tutti i comuni? i capoluoghi? sopra quanti abitanti? cosa dire di ognuna?). Una fonte di internet è scelta_ragionevole se è una fonte pubblica nota che sai nominare e che ha quel dato (una voce o una tabella di Wikipedia, i cambi della BCE, il meteo di Open-Meteo); altrimenti manca.
3. dal_contesto: i dati presi dalla conversazione recente che servono al lavoro e che la richiesta non dice (es. «120 000 euro, 20 anni, 3,1 %»); vuoto se nessuno.
4. domande: una domanda breve a voce per ogni punto «manca», la più importante prima (al più 3); vuoto se non manca niente. Per ognuna, senza_risposta: «sbaglia» se senza la risposta l'agente farebbe una cosa diversa da quella voluta o inventerebbe un dato, «sceglie» se un buon programmatore sceglierebbe da solo (quali caratteri in una password, come mostrare un totale, che calcolo d'esempio fare).
5. specifica: la richiesta completa in una frase sola (input, output, fonte), al più 40 parole, con i dati della conversazione.
6. nome: {nome_regola}
7. fonte_url: per un'estensione che prende dati da internet, l'indirizzo pubblico esatto, solo se lo conosci con certezza; altrimenti vuoto. Fonti note: Wikipedia in italiano https://it.wikipedia.org/wiki/<Titolo_della_voce>; cambi di riferimento dell'euro della BCE https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml; meteo di Open-Meteo https://api.open-meteo.com/v1/forecast.
8. gia_fatto: il nome esatto di una funzione che Calliope ha già (elenco sotto) che fa questo lavoro per intero, così come chiesto; altrimenti vuoto. Prima di indicarla controlla: chiedendola a voce, la persona dice solo i suoi dati (es. «quanti giorni mancano al 25 dicembre?») e ha il risultato? Se dovrebbe dire anche la formula o il procedimento (chilometri in miglia: «moltiplica per 0,621»), o se servono numeri casuali, NON è già fatto. Non conta nemmeno una funzione generica che potrebbe arrivarci (cercare su internet, nei documenti o nelle conversazioni, mostrare sullo schermo, creare documenti). come_chiederlo: una frase d'esempio per chiederla a voce.

Cosa si può fare qui:
{capacita}

Funzioni che Calliope ha già (nome: cosa fa):
{funzioni}

Tutto in italiano, frasi da dire a voce: niente markdown, elenchi o indirizzi nelle domande e nel motivo."""

NOTA_TIPO = {
    "estensione": ("Un'estensione si usa a voce tante volte: i dati di ogni uso (quale regione, "
                   "quale città, quale importo) li dice chi la usa in quel momento: l'input "
                   "non manca mai."),
    "codice": ("Un programma si può rieseguire a voce con dei valori: i valori che cambiano "
               "a ogni esecuzione (i chilometri di un viaggio, l'IBAN da controllare, il numero "
               "da convertire) non mancano; un file della persona da leggere invece va indicato."),
}
STATI = ("detto", "dal_contesto", "scelta_ragionevole", "manca")
# Punti che non mancano mai: li sceglie l'agente (il linguaggio, cosa dire se un dato non c'è)
# o li dice chi usa l'estensione a ogni uso (l'input). Nello schema non hanno «manca»
SENZA_MANCA = {"estensione": ("input", "non_trovato"), "codice": ("linguaggio",)}


def schema(tipo: str, senza_domande: bool = False) -> dict:
    stringa = {"type": "string"}

    def stati(p):
        no = senza_domande or p in SENZA_MANCA.get(tipo, ())
        return {"type": "string", "enum": [s for s in STATI if not (no and s == "manca")]}
    return {"type": "object", "additionalProperties": False,
            "required": ["impossibile", "punti", "dal_contesto", "domande", "specifica", "nome",
                         "fonte_url", "gia_fatto", "come_chiederlo"],
            "properties": {
                "impossibile": stringa,
                "punti": {"type": "object", "additionalProperties": False,
                          "required": list(PUNTI[tipo]),
                          "properties": {p: stati(p) for p in PUNTI[tipo]}},
                "dal_contesto": {"type": "array", "items": stringa, "maxItems": 6},
                "domande": {"type": "array", "maxItems": 3, "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["domanda", "senza_risposta"],
                    "properties": {"domanda": stringa, "senza_risposta": {
                        "type": "string", "enum": ["sbaglia", "sceglie"]}}}},
                "specifica": stringa, "nome": stringa, "fonte_url": stringa,
                "gia_fatto": stringa, "come_chiederlo": stringa}}


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
        tipo_detto=("un'estensione nuova di Calliope (una funzione permanente, usata a voce). "
                    if tipo == "estensione" else "un programma da scrivere ed eseguire una "
                    "volta. ") + "Lista di controllo: " + "; ".join(
                        f"{p} = {PUNTI_DETTI[p]}" for p in PUNTI[tipo]) + ".",
        nota_tipo=NOTA_TIPO.get(tipo, ""),
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
        utente += ("\nLe domande le hai già fatte e la persona ha risposto: niente più «manca», "
                   "usa le risposte (dal_contesto) e scrivi la specifica completa.")
    return [{"role": "system", "content": sistema}, {"role": "user", "content": utente}]


# ─────────────────────────── risposta ───────────────────────────

def _pulisci(t, max_car: int = 300) -> str:
    t = re.sub(r"[*_#`>|]+", " ", str(t or ""))
    t = re.sub(r"https?://\S+", "", t)
    return re.sub(r"\s+", " ", t).strip()[:max_car]


def interpreta(testo: str, tipo: str, senza_domande: bool = False,
               conversazione: bool = True) -> Esito:
    """Il JSON del modello → Esito (ripiego «nessuna» se non si legge). L'esito lo decide il
    codice dagli stati dei punti: impossibile, poi c'è già, poi un punto che manca (vaga), poi
    un punto dalla conversazione (raffinabile), altrimenti chiara."""
    try:
        d = json.loads(testo)
    except (TypeError, ValueError):
        m = re.search(r"\{.*\}", str(testo or ""), re.S)
        try:
            d = json.loads(m.group(0)) if m else None
        except ValueError:
            d = None
    if not isinstance(d, dict) or not isinstance(d.get("punti"), dict):
        return Esito(errore="risposta non JSON")
    stati = {}
    for p in PUNTI[tipo]:
        v = d["punti"].get(p)
        s = str((v or {}).get("stato") if isinstance(v, dict) else v or "").strip().lower()
        stati[p] = s if s in STATI else "scelta_ragionevole"
        if stati[p] == "manca" and p in SENZA_MANCA.get(tipo, ()):
            stati[p] = "scelta_ragionevole"
    if senza_domande:
        stati = {p: ("dal_contesto" if s == "manca" else s) for p, s in stati.items()}
    # Solo le domande senza le quali l'agente sbaglierebbe (06/10: «vuoi anche i simboli nella
    # password?» non si chiede); una domanda scritta come testo semplice vale
    grezze = []
    for x in d.get("domande") or []:
        if isinstance(x, dict):
            if str(x.get("senza_risposta") or "sbaglia").strip().lower() == "sceglie":
                continue
            x = x.get("domanda")
        grezze.append(x)
    domande = [_pulisci(x, 200) for x in grezze if _pulisci(x, 200)][:3]
    domande = [q if q.endswith("?") else q.rstrip(".") + "?" for q in domande]
    e = Esito(specifica=_pulisci(d.get("specifica"), 400), domande=domande,
              mancano=[p for p, s in stati.items() if s == "manca"],
              nome=_pulisci(d.get("nome"), 60).lower().strip(" .«»\"'"),
              fonte_url=str(d.get("fonte_url") or "").strip()[:300],
              tool=str(d.get("gia_fatto") or "").strip(),
              come_chiederlo=_pulisci(d.get("come_chiederlo"), 160),
              motivo=_pulisci(d.get("impossibile"), 300), stati=stati)
    if e.motivo:
        e.esito = "impossibile"
    elif e.tool:
        e.esito = "gia_fatto"
    elif e.mancano and e.domande:
        e.esito = "vaga"
    elif conversazione and e.specifica and (any(
            s == "dal_contesto" for s in stati.values()) or any(
            str(x).strip() for x in (d.get("dal_contesto") or []))):
        # Raffinabile solo con una conversazione da cui prendere qualcosa
        e.esito = "raffinabile"
    else:
        # Un punto che manca senza domande da fare: niente da chiedere, si procede
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
        self.ultima_fonte = ""           # la voce di Wikipedia trovata dalla ricerca

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
                "options": {"temperature": 0.0, "num_predict": 600,
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
        e = interpreta((out.get("r") or {}).get("content", ""), tipo, senza_domande,
                       conversazione=bool(storia) or senza_domande)
        if tipo == "estensione" and e.esito in ("chiara", "raffinabile") and \
                e.fonte_url.startswith(("http://", "https://")):
            resto = fine - time.monotonic()
            self.ultima_fonte = ""
            e.fonte_ok = self.verifica_fonte(e.fonte_url, min(VERIFICA_MAX_S, resto)) \
                if resto > 0.5 else None
            if e.fonte_ok and self.ultima_fonte:
                e.fonte_url = self.ultima_fonte     # la voce giusta trovata con la ricerca
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
        fine = time.monotonic() + timeout_s
        try:
            rete.richiesta(url, {"origine": "analisi"}, max_byte=1_500_000,
                           timeout_s=max(0.5, timeout_s), tipi=TIPI_DATI)
            return True
        except pagina.PaginaVietata as e:
            return None if "troppe richieste" in str(e) else False
        except pagina.PaginaNonLetta as e:
            if "troppo grande" in str(e) or re.search(r"risposto (400|405|422)\b", str(e)):
                return True          # il sito c'è (un'API senza parametri risponde 400)
            if "certificato" in str(e):
                return None          # non si può dire (catena del certificato incompleta)
            alt = self._voce_wikipedia(rete, url, fine - time.monotonic())
            if alt:
                self.ultima_fonte = alt
                return True
            return False
        except Exception:  # noqa: BLE001
            return None

    def _voce_wikipedia(self, rete, url: str, resto: float) -> str:
        """Una voce di Wikipedia indovinata male («Lista_dei_comuni_d'Italia»): la ricerca di
        Wikipedia (opensearch) con il titolo, una richiesta sola. L'indirizzo trovato, o ""."""
        from urllib.parse import quote, unquote, urlsplit
        u = urlsplit(url)
        if not u.netloc.endswith("wikipedia.org") or not u.path.startswith("/wiki/") \
                or resto < 0.5:
            return ""
        titolo = unquote(u.path[len("/wiki/"):]).replace("_", " ").strip()
        if not titolo:
            return ""
        api = (f"https://{u.netloc}/w/api.php?action=opensearch&limit=1&namespace=0"
               f"&format=json&search={quote(titolo)}")
        try:
            r = rete.richiesta(api, {"origine": "analisi"}, max_byte=50_000,
                               timeout_s=max(0.5, resto), tipi=("application/json",))
            dati = json.loads(r.get("testo_grezzo") or "[]")
            return str(dati[3][0]) if len(dati) > 3 and dati[3] else ""
        except Exception:  # noqa: BLE001 — la verifica è un di più
            return ""


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
