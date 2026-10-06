"""
I lavori dell'agente che sopravvivono a un riavvio di Calliope (06/10/2026).

Caso vero della DGX: alle 16:56 Dario fa partire «gioco memory da giocare sullo schermo» (tipo
codice, qwen3.6 su vLLM); l'agente scrive gioco.js, logica.js e logica.test.js nella sandbox.
Alle 17:07 un `calliope aggiorna` riavvia il servizio: il lavoro muore, dopo il riavvio
Calliope non dice niente e lavori_stato risponde «Non ho lavori in corso.». Dario pensa che si
sia piantata. Prima di qui coda e stato dei lavori stavano solo in memoria (lavoro.json si
scriveva nella cartella dei risultati, a lavoro fermo o finito).

Cosa fa:
- **lo stato su disco**: a ogni cambio (in coda, in corso, in attesa di risposta, finito) il
  servizio scrive `in_corso.json` nella cartella delle sandbox (`agenti_sandbox`, sulla DGX
  ~/calliope/lavori/), atomico (persistenza.scrivi_json): chi, titolo, compito, tipo, stato,
  cartella dei risultati, cartella della sandbox, domande fatte. Lo legge anche il gestore
  di Linux (setup/linux/gestore.py) prima di fermare il servizio;
- **all'avvio**: i lavori che risultano in coda o in corso diventano «interrotti»; un lavoro
  che aspettava una risposta torna ad aspettarla, con la conversazione dell'agente, se questa
  era salvabile (JSON), altrimenti è interrotto anche lui;
- **l'annuncio**: alla persona che li aveva chiesti, al primo silenzio e verso la sua corsia e
  il suo satellite come gli altri annunci dei lavori: «il lavoro «…» si è interrotto per un
  riavvio di Calliope. Lo rifaccio?», con l'azione in sospeso delega_lavoro(proposta=id).
  Solo se il lavoro era vivo da meno di `agenti_interrotti_annuncio_h` ore e una volta sola
  (`annunciato` resta nel file: un secondo riavvio non lo ripete). Più vecchi: solo
  nell'elenco di lavori_stato, per un giorno;
- **al «sì»** un lavoro nuovo (id nuovo) con lo stesso compito, la stessa persona e la stessa
  cartella dei risultati. Un lavoro di codice o un'estensione **riparte dalla sua sandbox**,
  con i file già scritti: l'agente li vede nell'elenco dei file e un vincolo gli dice che il
  lavoro era stato interrotto. È semplice (la sandbox è una cartella; i file sono dell'agente
  stesso, nello stesso isolamento) e fa risparmiare i minuti già spesi; la conversazione
  dell'agente invece riparte da capo (a metà lavoro non è salvata, ed è lo stato meno sicuro
  da riprendere). Un lavoro su un **file della persona** non si rifà da solo: la copia del
  file e la consegna al satellite non sopravvivono al riavvio, quindi l'annuncio dice di
  chiederlo di nuovo, senza domanda.

Solo libreria standard. Il formato del file è letto anche dal gestore (setup/linux/
gestore.py, `lavori_vivi`): cambiarlo insieme.
"""

import datetime
import json
import time
from pathlib import Path

from ..persistenza import FileRovinato, leggi_json, scrivi_json

FILE = "in_corso.json"
VERSIONE = 1
VIVI = ("in_coda", "in_corso", "in_attesa")
TENUTI_S = 86400.0                # un interrotto resta nell'elenco (e nel file) un giorno
_FILE_INIZIALI_MAX = 2_000_000    # oltre, il lavoro non si riprende dalla sandbox


def percorso(cartella_sandbox) -> Path:
    return Path(cartella_sandbox) / FILE


def _json(x):
    """Una copia JSON di `x`, o None se non si salva (la conversazione dell'agente in attesa)."""
    try:
        return json.loads(json.dumps(x, ensure_ascii=False))
    except (TypeError, ValueError):
        return None


def voce(lav, ora: float) -> dict:
    """La riga di `lav` nel file. `vivo`: l'ultima volta che lo si è visto vivo."""
    sb = getattr(lav, "sandbox", None)
    root = str(sb.root) if sb is not None and getattr(sb, "root", None) else \
        getattr(lav, "sandbox_da", None)
    iniziali = dict(getattr(lav, "file_iniziali", None) or {})
    if sum(len(str(v)) for v in iniziali.values()) > _FILE_INIZIALI_MAX:
        iniziali = None
    d = {"id": lav.id, "tipo": lav.tipo, "titolo": lav.titolo, "compito": lav.compito,
         "persona": lav.persona, "persona_nome": lav.persona_nome, "livello": lav.livello,
         "formato": lav.formato, "modello": lav.modello, "vincoli": lav.vincoli,
         "dati": [[str(r), str(t)[:2000]] for r, t in list(lav.dati or [])[-8:]],
         "stato": lav.stato, "creato": lav.creato, "inizio": lav.inizio,
         "cartella": lav.cartella, "sandbox": root,
         "domande": [list(x) for x in lav.domande], "attesa_dal": lav.attesa_dal,
         "attesa_s": lav.attesa_s,
         "file_persona": bool(lav.file_utente is not None or lav.input or
                              getattr(lav, "file_candidati", None)),
         "estensione": getattr(lav, "estensione", None),
         "gioco": bool(getattr(lav, "gioco", False)),
         "doppione_chiesto": bool(getattr(lav, "doppione_chiesto", False)),
         "file_iniziali": iniziali,
         "annunciato": bool(getattr(lav, "annunciato", False)),
         "vivo": ora if lav.stato in VIVI else (getattr(lav, "vivo", None) or ora)}
    if lav.stato == "in_attesa":
        d["contesto"] = _json(lav.contesto or {})
    return d


def scrivi(path, lavori: list, ora: float | None = None, pid: int | None = None):
    """I lavori vivi e gli interrotti di meno di un giorno, atomico."""
    import os
    ora = time.time() if ora is None else ora
    righe = [voce(lv, ora) for lv in lavori
             if lv.stato in VIVI or (lv.stato == "interrotto"
                                     and ora - (getattr(lv, "vivo", None) or ora) < TENUTI_S)]
    scrivi_json(path, {"versione": VERSIONE, "pid": os.getpid() if pid is None else pid,
                       "aggiornato": datetime.datetime.fromtimestamp(ora).isoformat(
                           timespec="seconds"),
                       "lavori": righe}, indent=1)


def leggi(path, salta_pid: int | None = None) -> list[dict]:
    """Le righe del file (vuoto se non c'è o non si legge: un file rovinato non ferma l'avvio).
    `salta_pid`: il file scritto da questo stesso processo non è un riavvio (un servizio dei
    lavori chiuso e ricreato, come nelle prove) e non si legge."""
    try:
        dati, _ = leggi_json(path)
    except FileRovinato:
        return []
    if not isinstance(dati, dict) or not isinstance(dati.get("lavori"), list):
        return []
    if salta_pid is not None and dati.get("pid") == salta_pid:
        return []
    return [r for r in dati["lavori"] if isinstance(r, dict) and r.get("id") and r.get("stato")]


def riprendibile(lav) -> bool:
    """Si può rifare al «sì»: non un lavoro su un file della persona (la copia e la consegna
    non sopravvivono al riavvio)."""
    return not getattr(lav, "file_persona", False) and getattr(lav, "iniziali_ok", True)


def ricostruisci(riga: dict, Lavoro):
    """Il Lavoro della riga, nello stato giusto dopo un riavvio: «interrotto», oppure ancora
    «in_attesa» se aspettava una risposta e la conversazione dell'agente c'è."""
    lav = Lavoro(str(riga["id"]), str(riga.get("tipo") or "altro"), str(riga.get("compito") or ""),
                 riga.get("persona"), riga.get("persona_nome"),
                 str(riga.get("livello") or "familiare"), str(riga.get("formato") or ""),
                 str(riga.get("modello") or ""), str(riga.get("vincoli") or ""),
                 [tuple(x) for x in riga.get("dati") or [] if isinstance(x, list) and len(x) == 2])
    lav.titolo = str(riga.get("titolo") or "lavoro")
    lav.creato = float(riga.get("creato") or time.time())
    lav.inizio = riga.get("inizio")
    lav.cartella = riga.get("cartella")
    lav.domande = [list(x) for x in riga.get("domande") or [] if isinstance(x, list)]
    lav.attesa_dal = riga.get("attesa_dal")
    lav.attesa_s = float(riga.get("attesa_s") or 0.0)
    lav.estensione = riga.get("estensione")
    lav.gioco = bool(riga.get("gioco"))
    lav.doppione_chiesto = bool(riga.get("doppione_chiesto"))
    lav.file_iniziali = dict(riga.get("file_iniziali") or {})
    lav.iniziali_ok = riga.get("file_iniziali") is not None
    lav.file_persona = bool(riga.get("file_persona"))
    lav.annunciato = bool(riga.get("annunciato"))
    lav.vivo = float(riga.get("vivo") or time.time())
    root = riga.get("sandbox")
    lav.sandbox_da = root if root and Path(root).is_dir() else None
    stato = str(riga["stato"])
    ctx = riga.get("contesto")
    if stato == "in_attesa" and isinstance(ctx, dict) and not lav.file_persona and \
            (ctx.get("tipo") != "codice" or lav.sandbox_da):
        lav.contesto = ctx
        lav.stato, lav.passo = "in_attesa", "aspetta una risposta"
        lav.risultato = {"esito": "domanda", "domanda": lav.domanda,
                         "cartella": lav.cartella or ""}
        lav.ripristinato = True
    else:
        lav.stato, lav.passo = "interrotto", "interrotto da un riavvio"
        lav.fine = lav.vivo
        lav.risultato = {"esito": "interrotto", "cartella": lav.cartella or ""}
    return lav


def file_scritti(lav) -> int:
    """Quanti file aveva già scritto l'agente nella sandbox (per l'annuncio)."""
    root = getattr(lav, "sandbox_da", None)
    if not root:
        return 0
    try:
        return sum(1 for p in Path(root).iterdir()
                   if p.is_file() and not p.name.startswith(".")
                   and p.name not in (lav.file_iniziali or {}))
    except OSError:
        return 0


def frase(lav, titolo: str) -> str:
    """L'annuncio di un lavoro interrotto (senza il nome della persona davanti)."""
    if not riprendibile(lav):
        return (f"il lavoro «{titolo}» si è interrotto per un riavvio di Calliope. Era su un tuo "
                f"file: se vuoi, chiedimelo di nuovo.")
    n = file_scritti(lav)
    gia = ""
    if n:
        gia = (" L'agente aveva già scritto un file, e ripartirei da lì." if n == 1 else
               f" L'agente aveva già scritto {n} file, e ripartirei da quelli.")
    return f"il lavoro «{titolo}» si è interrotto per un riavvio di Calliope.{gia} Lo rifaccio?"


def offerta(lav) -> dict:
    """L'azione in sospeso dell'annuncio: il «sì» richiama delega_lavoro con l'id."""
    return {"domanda": "Lo rifaccio?", "tool": "delega_lavoro",
            "cosa": f"rifare il lavoro interrotto «{lav.titolo}»",
            "argomenti": {"proposta": lav.id}}


def nota_ripresa(lav, nuovo):
    """Il lavoro nuovo al posto dell'interrotto `lav`: stessi dati, stessa cartella dei
    risultati e (codice, estensioni) la stessa sandbox con i file già scritti."""
    for k in ("estensione", "gioco", "doppione_chiesto"):
        setattr(nuovo, k, getattr(lav, k, None))
    nuovo.titolo = lav.titolo
    nuovo.file_iniziali = dict(lav.file_iniziali or {})
    if lav.cartella and Path(lav.cartella).is_dir():
        nuovo.cartella = lav.cartella
    risposte = lav.risposte_testo()
    extra = []
    if lav.tipo in ("codice", "estensione") and getattr(lav, "sandbox_da", None):
        nuovo.sandbox_da = lav.sandbox_da
        extra.append("Questo lavoro era stato interrotto da un riavvio: nella cartella ci sono "
                     "i file scritti fin lì. Guardali, tieni quello che va e completa il lavoro.")
    if risposte:
        extra.append("Risposte già date da chi ha chiesto il lavoro:\n" + risposte)
    extra = [x for x in extra if x not in (nuovo.vincoli or "")]   # ripreso due volte
    if extra:
        nuovo.vincoli = "\n".join([x for x in [nuovo.vincoli] if x] + extra)
    nuovo.ripresa_di = lav.id
    return nuovo
