"""
Eseguire il programma scritto dall'agente e mostrarlo in diretta (04/10/2026).

Caso vero dell'utente: «scrivi un software in C# che fa un calcolo matematico, inventa gli
input casuali e mostrami input e output sullo schermo». L'agente scriveva e provava il codice
nel container usa-e-getta, ma chi l'aveva chiesto non vedeva mai il programma girare.

- **Dove gira**: nella stessa sandbox del lavoro (sandbox.py, motore «docker» sulla DGX: niente
  rete, disco in sola lettura salvo la cartella, utente non root, tetti a tempo, memoria e
  processi), in una cartella **nuova** per ogni esecuzione con la copia dei file del lavoro:
  ciò che il programma scrive non tocca i risultati. Tempo massimo `agenti_dimostrazione_s`.
- **Quando**: a lavoro di codice finito, se chi l'ha chiesto ha uno schermo personale
  (`agenti_dimostrazione`), e su richiesta («fammelo vedere», «eseguilo di nuovo», «eseguilo
  con 3 e 5»: tool programma_esegui). «Fermalo»: lavoro_annulla ferma prima l'esecuzione.
- **Input**: i dati detti o scritti nella casella dello schermo arrivano come argomenti della
  riga di comando **e** come righe dello stdin (uno per riga), poi lo stdin si chiude: il
  programma prende quello che si aspetta, e niente input interattivo oltre a questo.
- **Schermo**: la scheda `esecuzione:<lavoro>-<n>` (personale, come il lavoro) con stdout e
  stderr mentre arrivano, accorpati al più ogni `INTERVALLO_S`, il tempo che scorre (la pagina
  conta da sola da `dal`), il codice d'uscita e il troncamento oltre `agenti_dimostrazione_uscita_kb`
  (restano l'inizio e la coda). L'uscita intera, con lo stesso troncamento, finisce anche in
  un file nella cartella dei risultati del lavoro.
- **Voce**: un riassunto breve fatto dal programma, mai dal modello: com'è finito e le ultime
  una o due righe dell'uscita (`frase`). Mai tutto l'output.

Costo per chi chiama: `avvia` crea la cartella e fa partire un thread («lavori-esecuzione»):
pochi millisecondi. Tutto il resto (Docker, lettura dell'uscita, schede) sta nei thread suoi.
"""

import re
import shutil
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from .linguaggi import LINGUAGGI, per_estensione

INTERVALLO_S = 0.3
# Sulla scheda: la coda dell'uscita (righe e caratteri), il resto è nel file
SCHEDA_RIGHE = 200
SCHEDA_CARATTERI = 12_000
TESTA_CARATTERI = 8_000          # l'inizio che resta quando l'uscita supera il tetto
MARCA_COMPILAZIONE = "— compilazione non riuscita —"
_NOMI_PROGRAMMA = ("main", "programma", "program", "app", "calcolo", "principale")


def _secondi(s: float) -> str:
    if s < 10:
        v = f"{s:.1f}".replace(".", ",")
        return "un secondo" if v == "1,0" else f"{v} secondi"
    s = round(s)
    if s < 120:
        return f"{s} secondi"
    return f"{s // 60} minuti"


@dataclass
class Esecuzione:
    id: str                          # «L3-1»
    lavoro: object                   # Lavoro
    programma: str                   # percorso relativo del file eseguito
    linguaggio: str
    dati: list
    persona: str | None = None
    persona_nome: str | None = None
    on_scheda: object = None
    annuncia: bool = False           # a fine esecuzione un annuncio (lavori.done)
    stato: str = "in_corso"          # in_corso | fatto | errore | scaduto | fermato
    codice_uscita: int | None = None
    errore: str = ""
    inizio: float = field(default_factory=time.time)
    fine: float | None = None
    max_s: float = 60.0
    testa: list = field(default_factory=list)      # [[tipo, testo]] fino a TESTA_CARATTERI
    coda: deque = field(default_factory=deque)     # [[tipo, testo]] la parte più recente
    caratteri: int = 0               # caratteri arrivati in tutto
    omessi: int = 0                  # caratteri buttati tra la testa e la coda
    file_uscita: str = ""
    sandbox: object = None
    finita: threading.Event = field(default_factory=threading.Event)   # il programma è finito
    # Tutto fatto: scheda finale mandata, cartella cancellata, annuncio deciso
    chiusa: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    cv: threading.Condition = None
    sporco: bool = False
    inviate: int = 0
    sullo_schermo: bool = False      # almeno uno schermo personale la riceve

    def __post_init__(self):
        self.cv = threading.Condition(self.lock)

    @property
    def detto(self) -> str:
        lg = LINGUAGGI.get(self.linguaggio)
        return lg.detto if lg else self.linguaggio

    def righe(self) -> list[tuple[str, str]]:
        """L'uscita tenuta (testa e coda), a pezzi per tipo, con il lock preso da chi chiama."""
        return [tuple(x) for x in self.testa] + [tuple(x) for x in self.coda]

    def testo(self, tipo: str | None = None) -> str:
        with self.lock:
            return "".join(t for k, t in self.righe() if tipo is None or k == tipo)


def _eseguibile(path: Path) -> bool:
    """Il file Python fa qualcosa quando lo si esegue (non solo def, class, import e
    costanti)? Analisi della forma del codice con ast, senza eseguirlo."""
    import ast
    try:
        albero = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError, ValueError):
        return False
    quieti = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom,
              ast.Assign, ast.AnnAssign, ast.Pass)
    for nodo in albero.body:
        if isinstance(nodo, quieti):
            continue
        if isinstance(nodo, ast.Expr) and isinstance(nodo.value, ast.Constant):
            continue                         # docstring
        return True
    return False


def _aggiungi(pezzi, tipo: str, t: str):
    if pezzi and pezzi[-1][0] == tipo:
        pezzi[-1][1] += t
    else:
        pezzi.append([tipo, t])


class Esecuzioni:
    def __init__(self, lavori, log=print, intervallo: float = INTERVALLO_S):
        self.lavori = lavori
        self.cfg = lavori.cfg
        self.log = log
        self.intervallo = float(intervallo)
        self._lock = threading.Lock()
        self.tutte: list[Esecuzione] = []
        self._n: dict[str, int] = {}

    # ─────────────────────────── quale programma ───────────────────────────
    def max_s(self) -> float:
        return float(getattr(self.cfg, "agenti_dimostrazione_s", 60.0))

    def max_caratteri(self) -> int:
        return int(float(getattr(self.cfg, "agenti_dimostrazione_uscita_kb", 64)) * 1024)

    @staticmethod
    def programma_di(lav) -> tuple[str | None, str]:
        """(percorso relativo, "") del programma di un lavoro di codice finito, o (None,
        motivo). Prima quello indicato dall'agente con consegna(programma=…), poi l'unico file
        di codice che non è un test, poi i nomi soliti (main.py, Program.cs…) o il file con
        `if __name__ == "__main__"`."""
        r = getattr(lav, "risultato", None) or {}
        dest = Path(r.get("cartella") or "")
        files = [f for f in (r.get("file") or []) if per_estensione(f)]
        if not files or not dest.is_dir():
            return None, "non trovo i file del programma"
        scelto = str(r.get("programma") or "").strip().replace("\\", "/")
        if scelto and scelto in files:
            return scelto, ""

        def test(f):
            n = Path(f).name.lower()
            return n.startswith("test") or n.endswith(("_test.py", "tests.cs", "test.cs"))
        # Un file Python è un programma se fa qualcosa quando lo si esegue: `__main__` o
        # istruzioni di primo livello che non sono definizioni né import (un modulo di sole
        # funzioni, eseguito, non stamperebbe niente)
        cand = [f for f in files if not test(f) and (not f.lower().endswith(".py")
                                                     or _eseguibile(dest / f))]
        if not cand:
            return None, ("ci sono solo funzioni e test, non un programma da eseguire"
                          if any(not test(f) for f in files)
                          else "ci sono solo i test, non un programma da eseguire")
        if len(cand) == 1:
            return cand[0], ""
        cs = [f for f in cand if f.lower().endswith(".cs")]
        if cs and len({str(Path(f).parent) for f in cs}) == 1 and len(cs) == len(cand):
            return cs[0], ""           # il C# si compila per cartella: un file qualunque
        for nome in _NOMI_PROGRAMMA:
            for f in cand:
                if Path(f).stem.lower() == nome:
                    return f, ""
        principali = []
        for f in cand:
            try:
                t = (dest / f).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "__main__" in t or re.search(r"\bstatic\s+(?:async\s+)?\w+\s+Main\s*\(", t):
                principali.append(f)
        if len(principali) == 1:
            return principali[0], ""
        return None, "non so quale dei file è il programma da eseguire"

    def ultimo_lavoro(self, persona=None, admin: bool = False, quale: str = ""):
        """Il lavoro di codice finito più recente di `persona` (chi amministra: anche degli
        altri), o quello con l'id detto («L3»)."""
        with self.lavori._lock:
            tutti = list(self.lavori.lavori)
        q = str(quale or "").strip()
        cand = [lv for lv in tutti if lv.tipo == "codice" and (lv.risultato or {}).get("file")
                and lv.stato in ("fatto", "errore", "annullato")]
        if re.fullmatch(r"[Ll]\d+", q):
            cand = [lv for lv in cand if lv.id.lower() == q.lower()]
        mine = [lv for lv in cand if lv.persona == persona]
        if mine:
            return mine[-1]
        return cand[-1] if admin and cand else None

    # ─────────────────────────── avvio ───────────────────────────
    def in_corso(self, persona=None) -> list[Esecuzione]:
        with self._lock:
            return [e for e in self.tutte if e.stato == "in_corso"
                    and (persona is None or e.persona == persona)]

    def avvia(self, lav, dati=(), on_scheda=None, persona=None, persona_nome=None,
              annuncia: bool = False):
        """(Esecuzione, "") partita in secondo piano, o (None, frase) se non si può. Non
        aspetta: la cartella si prepara qui (copie di pochi file), Docker nel thread suo."""
        from .sandbox import ErroreSandbox, Sandbox
        from .servizio import cartella_sandbox
        prog, perche = self.programma_di(lav)
        if prog is None:
            return None, f"Non posso eseguire «{lav.titolo}»: {perche}."
        lg = per_estensione(prog)
        isolamenti = getattr(self.lavori, "isolamenti", None) or {}
        iso = isolamenti.get(lg.nome) if lg.nome != "python" else (
            isolamenti.get("python") or self.lavori.isolamento)
        if iso is None or not iso.pronto:
            passo = f" {iso.passo}" if iso is not None and iso.passo else ""
            return None, (f"Non posso eseguire il programma: qui il {lg.detto} non si può "
                          f"eseguire in modo isolato.{passo}")
        if any(e.lavoro is lav for e in self.in_corso()):
            return None, f"«{lav.titolo}» è già in esecuzione: guardalo sullo schermo."
        dati = [re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(d)).strip()
                for d in (dati or [])][:20]
        dati = [d[:500] for d in dati if d]
        with self._lock:
            n = self._n.get(lav.id, 0) + 1
            self._n[lav.id] = n
        es = Esecuzione(f"{lav.id}-{n}", lav, prog, lg.nome, dati,
                        persona if persona is not None else lav.persona,
                        persona_nome if persona_nome is not None else lav.persona_nome,
                        on_scheda if on_scheda is not None else lav.on_scheda, annuncia,
                        max_s=self.max_s())
        r = lav.risultato
        root = cartella_sandbox(self.cfg) / f"{lav.id}-esecuzione-{n}-{time.strftime('%H%M%S')}"
        try:
            sb = Sandbox(root, es.max_s, int(getattr(self.cfg, "agenti_memoria_mb", 1024)),
                         max_uscita=self.max_caratteri(),
                         isolamento=isolamenti.get("python") or self.lavori.isolamento,
                         cpu=float(getattr(self.cfg, "agenti_sandbox_cpu", 2.0)),
                         linguaggi=isolamenti)
            dest = Path(r["cartella"])
            for f in r.get("file") or []:
                p = dest / f
                if p.is_file():
                    sb.metti(f, p.read_bytes())
        except (ErroreSandbox, OSError) as e:
            shutil.rmtree(root, ignore_errors=True)
            self.log(f"[AGENTI] {es.id}: esecuzione non preparata: {e}")
            return None, "Non sono riuscita a preparare l'esecuzione del programma."
        es.sandbox = sb
        with self._lock:
            self.tutte.append(es)
            if len(self.tutte) > 40:          # le vecchie finite escono dall'elenco
                vecchie = [e for e in self.tutte[:-20] if e.stato != "in_corso"]
                self.tutte = [e for e in self.tutte if e not in vecchie]
        threading.Thread(target=self._corri, args=(es,), daemon=True,
                         name=f"lavori-esecuzione-{es.id}").start()
        return es, ""

    # ─────────────────────────── il thread dell'esecuzione ───────────────────────────
    def _flusso(self, es: Esecuzione, tipo: str, t: str):
        tetto = self.max_caratteri()
        with es.lock:
            es.caratteri += len(t)
            spazio = TESTA_CARATTERI - sum(len(x[1]) for x in es.testa)
            if spazio > 0 and not es.coda:
                _aggiungi(es.testa, tipo, t[:spazio])
                t = t[spazio:]
            if t:
                _aggiungi(es.coda, tipo, t)
                tot = sum(len(x[1]) for x in es.coda)
                limite = max(1024, tetto - TESTA_CARATTERI)
                while tot > limite and es.coda:
                    via = tot - limite
                    if len(es.coda[0][1]) <= via:
                        tot -= len(es.coda[0][1])
                        es.omessi += len(es.coda[0][1])
                        es.coda.popleft()
                    else:
                        es.coda[0][1] = es.coda[0][1][via:]
                        es.omessi += via
                        tot -= via
            es.sporco = True
            es.cv.notify()

    def _schermo(self, es: Esecuzione):
        """Il thread delle schede: una ogni `intervallo` al più, finché l'esecuzione corre."""
        ultimo = float("-inf")
        while True:
            with es.lock:
                # Senza uscita nuova niente schede: il tempo che scorre lo conta la pagina
                while not es.sporco and not es.finita.is_set():
                    es.cv.wait(1.0)
                if es.finita.is_set():
                    return
                resto = ultimo + self.intervallo - time.monotonic()
            if resto > 0:
                es.finita.wait(resto)
                if es.finita.is_set():
                    return
            with es.lock:
                es.sporco = False
            self._manda(es, sposta=False)
            ultimo = time.monotonic()

    def _manda(self, es: Esecuzione, sposta: bool):
        if es.on_scheda is None:
            return
        try:
            r = es.on_scheda(self.scheda(es, sposta))
            es.inviate += 1
            # hub.invia dice a chi è arrivata: senza uno schermo personale la voce non dice
            # «è sullo schermo»
            if isinstance(r, dict):
                es.sullo_schermo = es.sullo_schermo or bool(r.get("destinatari"))
            else:
                es.sullo_schermo = True
        except Exception as e:  # noqa: BLE001 — lo schermo non ferma il programma
            self.log(f"[AGENTI] {es.id}: scheda non inviata: {type(e).__name__}: {e}")

    def _corri(self, es: Esecuzione):
        from .sandbox import ErroreSandbox
        lav = es.lavoro
        self.log(f"[AGENTI] {es.id}: eseguo {es.programma} ({es.detto})"
                 + (f" con {len(es.dati)} dati" if es.dati else ""))
        self._manda(es, sposta=True)                  # la scheda compare subito, in cima
        schermo = None
        if es.on_scheda is not None:
            schermo = threading.Thread(target=self._schermo, args=(es,), daemon=True,
                                       name=f"lavori-esecuzione-schermo-{es.id}")
            schermo.start()
        stdin = "".join(d + "\n" for d in es.dati)
        try:
            res = es.sandbox.esegui(es.programma, es.dati, stdin=stdin,
                                    flusso=lambda tipo, t: self._flusso(es, tipo, t))
        except ErroreSandbox as e:
            res = {"codice_uscita": None, "errore": str(e), "scaduto": False}
        except Exception as e:  # noqa: BLE001
            res = {"codice_uscita": None, "errore": f"{type(e).__name__}", "scaduto": False}
        with es.lock:
            es.fine = time.time()
            es.codice_uscita = res.get("codice_uscita")
            if es.stato == "fermato":
                pass
            elif res.get("scaduto"):
                es.stato = "scaduto"
            elif es.codice_uscita == 0 and not res.get("errore"):
                es.stato = "fatto"
            else:
                es.stato = "errore"
                es.errore = str(res.get("errore") or "")
        self._salva(es)
        es.finita.set()
        with es.lock:
            es.cv.notify_all()
        if schermo is not None:
            schermo.join(timeout=2)
        self._manda(es, sposta=False)                 # la finale, al suo posto
        try:
            shutil.rmtree(es.sandbox.root, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass
        self.log(f"[AGENTI] {es.id}: {es.stato}, codice {es.codice_uscita}, "
                 f"{es.fine - es.inizio:.2f} s, {es.caratteri} caratteri")
        # Chi aspetta (attendi) e il thread decidono qui, con il lock, chi dice com'è finita
        with es.lock:
            es.chiusa.set()
            annuncia = es.annuncia
        if annuncia:
            msg = self.frase(es)
            who = f"{es.persona_nome}, " if es.persona_nome else ""
            msg = who + msg[:1].lower() + msg[1:] if who else msg
            item = {"id": es.id, "tipo": "esecuzione", "titolo": lav.titolo, "stato": es.stato,
                    "esito": "esecuzione", "messaggio": msg, "chi": es.persona,
                    "chi_nome": es.persona_nome, "codice_uscita": es.codice_uscita,
                    "secondi": round(es.fine - es.inizio, 2), "linguaggio": es.linguaggio}
            self.lavori.done.put(item)
            if self.lavori.on_done:
                self.lavori.on_done()

    def _salva(self, es: Esecuzione):
        """L'uscita (con lo stesso troncamento) nella cartella dei risultati del lavoro."""
        dest = Path((es.lavoro.risultato or {}).get("cartella") or "")
        if not dest.is_dir():
            return
        with es.lock:
            pezzi = [x for x in es.testa]
            coda = list(es.coda)
            omessi = es.omessi
        testo = "".join(t for _, t in pezzi)
        if omessi:
            testo += f"\n[… {omessi} caratteri omessi …]\n"
        testo += "".join(t for _, t in coda)
        intest = (f"# {es.programma} ({es.detto}), {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(es.inizio))}"
                  + (f", dati: {' '.join(es.dati)}" if es.dati else "")
                  + f"\n# esito: {es.stato}, codice d'uscita {es.codice_uscita}\n")
        p = dest / f"esecuzione-{es.id.split('-')[-1]}.txt"
        try:
            p.write_text(intest + testo, encoding="utf-8")
            es.file_uscita = p.name
        except OSError:
            pass

    # ─────────────────────────── fermare e aspettare ───────────────────────────
    def ferma(self, persona=None, admin: bool = False) -> list[Esecuzione]:
        """Ferma le esecuzioni in corso di `persona` (chi amministra: tutte). Non aspetta."""
        via = [e for e in self.in_corso() if admin or e.persona == persona]
        for e in via:
            with e.lock:
                if e.stato == "in_corso":
                    e.stato = "fermato"
            try:
                e.sandbox.termina()
            except Exception:  # noqa: BLE001
                pass
        return via

    def attendi(self, es: Esecuzione, timeout: float) -> bool:
        """Aspetta la fine fino a `timeout`. True: finita, e niente annuncio dopo (la frase la
        dice chi aspettava). False: ancora in corso, e alla fine ci sarà l'annuncio."""
        es.chiusa.wait(max(0.0, timeout))
        with es.lock:
            if es.chiusa.is_set():
                es.annuncia = False
                return True
            es.annuncia = True
            return False

    def dimostra(self, lav) -> Esecuzione | None:
        """A lavoro di codice finito (thread dei lavori, prima dell'annuncio): se chi l'ha
        chiesto ha gli schermi, il programma si esegue e si mostra. Aspetta al più
        `agenti_dimostrazione_attesa_s`: se finisce prima, l'annuncio del lavoro dice com'è
        andata (`risultato["dimostrazione"]`), altrimenti lo dirà un annuncio a parte. Mai sui
        lavori fatti su un file della persona (il suo script di backup non si «mostra»)."""
        if (not getattr(self.cfg, "agenti_dimostrazione", True) or lav.tipo != "codice"
                or lav.stato != "fatto" or lav.on_scheda is None or lav.input
                or not getattr(lav, "segui_schermi", True)):
            return None
        # Con gli argomenti d'esempio dell'agente, se ne ha dati (06/10)
        es, perche = self.avvia(lav, (lav.risultato or {}).get("argomenti_esempio") or ())
        if es is None:
            self.log(f"[AGENTI] {lav.id}: niente esecuzione dimostrativa: {perche}")
            return None
        finita = self.attendi(es, float(getattr(self.cfg, "agenti_dimostrazione_attesa_s",
                                                8.0)))
        if finita:
            lav.risultato["dimostrazione"] = self.frase(es)
            # Com'è andata, per l'annuncio: non deve dire «funziona» se si è fermata (06/10)
            lav.risultato["dimostrazione_esito"] = es.stato
            lav.risultato["dimostrazione_con_dati"] = bool(es.dati)
        else:
            lav.risultato["dimostrazione_in_corso"] = True
        return es

    def in_cima(self, es: Esecuzione):
        """Riporta in primo piano la scheda (dopo la scheda finale del lavoro, che va in cima)."""
        self._manda(es, sposta=True)

    # ─────────────────────────── voce e schermo ───────────────────────────
    @staticmethod
    def _ultime(testo: str, n: int = 2, max_car: int = 90) -> list[str]:
        righe = [re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", r)).strip()
                 for r in testo.splitlines()]
        righe = [r for r in righe if r and r != MARCA_COMPILAZIONE]
        out = []
        for r in righe[-n:]:
            if len(r) > max_car:
                r = r[:max_car].rsplit(" ", 1)[0] + "…"
            out.append(r)
        return out

    def frase(self, es: Esecuzione) -> str:
        """Il riassunto per la voce, dal programma: com'è finito e le ultime righe."""
        durata = _secondi((es.fine or time.time()) - es.inizio)
        schermo = " Il resto è sullo schermo." if es.sullo_schermo else ""
        if es.stato == "fermato":
            return "Ho fermato il programma."
        if es.stato == "scaduto":
            return (f"Ho fermato il programma dopo {_secondi(es.max_s)}: era ancora in "
                    f"esecuzione.{schermo}")
        if es.stato == "errore":
            err = self._ultime(es.testo("err") or es.testo(), 1)
            if MARCA_COMPILAZIONE in es.testo("err"):
                return ("Il programma non si compila" + (f": «{err[0]}»." if err else ".")
                        + schermo)
            if es.codice_uscita is None:
                return f"Non sono riuscita a eseguire il programma: {es.errore}."
            if es.codice_uscita == 137:
                return "Il programma è stato fermato: ha usato troppa memoria." + schermo
            return (f"Il programma si è fermato con un errore (codice {es.codice_uscita})"
                    + (f": «{err[0]}»." if err else ".") + schermo)
        righe = self._ultime(es.testo("out"))
        if not righe:
            return f"Il programma ha finito in {durata} senza scrivere niente."
        detto = "«" + "», «".join(righe) + "»"
        return (f"Il programma ha finito in {durata}. "
                + ("L'ultima riga dice" if len(righe) == 1 else "Le ultime righe dicono")
                + f": {detto}." + schermo)

    def scheda(self, es: Esecuzione, sposta: bool = True) -> dict:
        from ..schermi import schede
        with es.lock:
            pezzi = es.righe()
            omessi = es.omessi
            stato, codice = es.stato, es.codice_uscita
            fine = es.fine
        # Sulla scheda la coda: al più SCHEDA_RIGHE righe e SCHEDA_CARATTERI caratteri
        scelti, car, righe = [], 0, 0
        for i in range(len(pezzi) - 1, -1, -1):
            tipo, t = pezzi[i]
            linee = t.count("\n")
            if car + len(t) > SCHEDA_CARATTERI or righe + linee > SCHEDA_RIGHE:
                resto_car = SCHEDA_CARATTERI - car
                taglio = t[-resto_car:] if resto_car > 0 else ""
                taglio = "\n".join(taglio.split("\n")[-max(1, SCHEDA_RIGHE - righe):])
                if taglio:
                    scelti.append((tipo, taglio))
                omessi += len(t) - len(taglio) + sum(len(x[1]) for x in pezzi[:i])
                break
            scelti.append((tipo, t))
            car += len(t)
            righe += linee
        scelti.reverse()
        ora = time.time()
        return schede.esecuzione(
            es.lavoro.titolo, es.programma, es.detto, stato, es.dati,
            [{"tipo": k, "testo": t} for k, t in scelti], omessi, codice,
            inizio=es.inizio, trascorso_s=round((fine or ora) - es.inizio, 2), max_s=es.max_s,
            ident=es.id, sposta=sposta, file=es.file_uscita, ora_server=ora)
