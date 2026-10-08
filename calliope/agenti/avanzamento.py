"""
L'avanzamento dei lavori sugli schermi, in diretta (03/10/2026).

La scheda `lavoro:<id>` compare appena il lavoro è affidato (in coda) e si aggiorna al suo
posto mentre l'agente lavora, sugli schermi personali di chi l'ha chiesto (visibilità
personale, come la scheda finale: hub.py decide i destinatari, mai nella zona grigia):

- lo stato (in coda, in corso, in pausa per la voce, in attesa della tua risposta, finito,
  non riuscito, annullato) e il passo attuale in parole semplici, con gli ultimi passi;
- i file scritti finora (i nomi; per il codice un'anteprima breve dell'ultimo);
- l'ultimo esito dei test;
- passate, token e minuti rispetto ai tetti del lavoro: sono gli unici numeri onesti, una
  percentuale di «quanto manca» non esiste. Dal 08/10 i tetti sono **per giro e cumulativi**:
  al giro 2 di uno sviluppo (dopo una tappa) 48 passate, 60 minuti e due volte i token, e il
  tempo continua a contare (prima restava «di 30 min» con la barra piena);
- il **flusso** dell'agente (08/10): il ragionamento, il testo, il codice negli argomenti di
  scrivi_file (vLLM), le chiamate agli strumenti con il loro esito in breve e un separatore a
  ogni passata, come una chat in sola lettura che **si accumula**. Ogni invio porta solo i
  pezzi nuovi, numerati (`n`, con la sezione `s`); la cronologia dello schermo (rimandata a
  una pagina che si ricollega) ne tiene invece l'ultima finestra (`FINESTRA` caratteri,
  `_storia` in hub.py), così la pagina riprende senza buchi né doppioni. Il registro completo
  si scrive nella cartella del lavoro (`.registro-agente.md`, nascosto: file_di_codice e le
  consegne non lo vedono) e si scarica dalla scheda (`registro`, «Scarica» di scarica.py);
- se il lavoro è di uno sviluppo (calliope/sviluppo.py, `sviluppo(lav)`): fase, correzione e
  i numeri dello sviluppo intero (somma dei lavori e delle correzioni).

**Costo**: chi lavora (il thread dei lavori, lo stream dell'agente, la voce che annulla) fa
solo `_evento`: un lock breve, qualche assegnazione e un `notify`. La scheda la costruisce e
la manda un thread suo («lavori-schermo»), al più una ogni `INTERVALLO_S` per lavoro: i
pezzi dello stream si accorpano (un pezzo numerato per sezione e per invio), e il registro su
disco lo scrive questo thread. Senza schermi (`Lavoro.on_scheda` assente) il lavoro non ha
osservatore e qui non arriva niente; il thread parte solo al primo lavoro seguito.

**Spostamento**: gli aggiornamenti automatici hanno `sposta: false` (restano al loro posto
nella cronologia e non passano in primo piano); la prima scheda e i cambi di stato che
contano (in attesa, finito, non riuscito, annullato, chiuso) la portano in cima. Le schede
finali le costruisce `Lavori.scheda` (il codice intero, l'anteprima del documento) e partono
da `finale`, nello stesso ordine degli aggiornamenti: dopo la finale nessun aggiornamento
vecchio può sovrascriverla (lock d'invio).

Con l'arbitro (agente sullo stesso Ollama della voce) la scheda dice «in pausa: sto
rispondendo a voce» finché l'agente aspetta: il thread lo guarda a ogni intervallo, solo
mentre un lavoro seguito è in corso.
"""

import json
import secrets
import threading
import time
from collections import deque
from pathlib import Path

# Al più due aggiornamenti al secondo per lavoro (i cambi di stato non aspettano)
INTERVALLO_S = 0.5
# Quanti passi recenti mostrare
PASSI_RECENTI = 6
ANTEPRIMA_RIGHE = 24
ANTEPRIMA_CARATTERI = 1400
FILE_MAX = 12
# Il flusso (08/10): la finestra che la cronologia degli schermi tiene per chi si ricollega,
# uguale al tetto della pagina (schermo.js, FLUSSO_PAGINA); il registro su disco ha il suo
FINESTRA = 40_000
REGISTRO_MAX = 16_000_000          # byte del registro completo di un lavoro
REGISTRO_ATTESA = 2_000_000        # caratteri tenuti in memoria finché manca la cartella
REGISTRO_NOME = ".registro-agente.md"
ESITO_MAX = 240                    # caratteri dell'esito breve di uno strumento
# Le sezioni del flusso
TIPI_FLUSSO = ("pensiero", "testo", "codice", "strumento", "esito", "passata")

# Stati che chiudono (o sospendono) il lavoro: la loro scheda la costruisce Lavori.scheda
FINALI = frozenset(("fatto", "errore", "mancano_dati", "scaduto", "annullato", "in_attesa"))
# Passi interni che sulla scheda non dicono niente di nuovo
_PASSI_MUTI = frozenset(("in coda",))


def _anteprima(testo: str) -> str:
    righe = str(testo or "").splitlines()
    t = "\n".join(righe[:ANTEPRIMA_RIGHE])
    if len(t) > ANTEPRIMA_CARATTERI:
        t = t[:ANTEPRIMA_CARATTERI].rsplit("\n", 1)[0]
    if len(righe) > ANTEPRIMA_RIGHE or len(t) < len("\n".join(righe)):
        t += "\n…"
    return t


_ESCAPE = {"n": "\n", "t": "    ", '"': '"', "\\": "\\", "/": "/", "r": "", "b": "", "f": ""}


class _Argomenti:
    """Gli argomenti JSON di una chiamata che arrivano a pezzi (vLLM): il testo dopo
    «"contenuto": "», sciolto man mano. Incrementale (08/10): ogni pezzo costa quanto è
    lungo, anche per un file di 50 000 caratteri; un escape a metà aspetta il pezzo dopo,
    così il testo restituito cresce solo in fondo (mai riscritto)."""

    def __init__(self):
        self.raw = ""
        self.k = -1                 # dove si legge il contenuto (−1: non ancora trovato)
        self.fine = False
        self.percorso = ""

    def aggiungi(self, pezzo: str) -> str:
        """Il testo nuovo del contenuto (vuoto se non ce n'è)."""
        self.raw += str(pezzo or "")
        if self.fine:
            return ""
        if not self.percorso:
            i = self.raw.find('"percorso"')
            if i >= 0:
                a = self.raw.find('"', self.raw.find(":", i) + 1)
                b = self.raw.find('"', a + 1) if a >= 0 else -1
                if a >= 0 and b > a:
                    self.percorso = self.raw[a + 1:b][:160]
        if self.k < 0:
            i = self.raw.find('"contenuto"')
            if i < 0:
                return ""
            c = self.raw.find(":", i)
            j = self.raw.find('"', c + 1) if c >= 0 else -1
            if j < 0:
                return ""
            self.k = j + 1
        t, k, out = self.raw, self.k, []
        while k < len(t):
            ch = t[k]
            if ch == "\\":
                if k + 1 >= len(t):
                    break                       # l'escape finisce nel pezzo dopo
                n = t[k + 1]
                if n == "u":
                    if k + 6 > len(t):
                        break
                    try:
                        out.append(chr(int(t[k + 2:k + 6], 16)))
                    except ValueError:
                        pass
                    k += 6
                    continue
                out.append(_ESCAPE.get(n, ""))
                k += 2
                continue
            if ch == '"':                       # fine della stringa
                self.fine = True
                k += 1
                break
            out.append(ch)
            k += 1
        self.k = k
        return "".join(out)


def _decodifica_argomenti(arg: str) -> str:
    """Gli argomenti JSON di scrivi_file a metà (vLLM li manda a pezzi): il testo dopo
    «"contenuto": "», con gli escape più comuni sciolti. Vuoto se non c'è ancora."""
    return _Argomenti().aggiungi(arg)


def _breve(testo, n: int = ESITO_MAX) -> str:
    t = " ".join(str(testo or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def chiamata_breve(nome: str, args) -> str:
    """La chiamata a uno strumento detta in breve: il nome e gli argomenti che dicono cosa
    (percorso, domanda, indirizzo), mai il contenuto di un file."""
    a = args if isinstance(args, dict) else {}
    cosa = ""
    for k in ("percorso", "cartella", "domanda", "url", "query", "esito", "capacita_necessarie"):
        if a.get(k):
            cosa = a[k] if isinstance(a[k], str) else json.dumps(a[k], ensure_ascii=False)
            break
    if nome == "esegui_python" and a.get("argomenti"):
        cosa = f"{cosa} {' '.join(map(str, a['argomenti']))}".strip()
    return _breve(f"{nome} · {cosa}" if cosa else nome, 160)


def esito_breve(nome: str, r) -> str:
    """L'esito di uno strumento in una riga: «scritto, 42 righe», «3 test su 4 passano»,
    l'errore, l'inizio dell'uscita."""
    from .ciclo import frase_test
    if not isinstance(r, dict):
        if isinstance(r, list):
            return f"{len(r)} risultati"
        return _breve(r)
    if r.get("errore"):
        return _breve(f"errore: {r['errore']}")
    if nome == "scrivi_file":
        return "scritto" + (f" ({r['righe']} righe)" if r.get("righe") else "")
    if nome == "esegui_test" or "esito_test" in r:
        return frase_test(r.get("esito") or r.get("esito_test")).replace("prova il codice: ", "")
    if nome == "elenca_file" and isinstance(r.get("file"), list):
        return f"{len(r['file'])} file"
    if nome == "leggi_file":
        t = r.get("testo") or r.get("contenuto") or ""
        return f"letto ({str(t).count(chr(10)) + 1} righe)" if t else "letto"
    if "uscita" in r:
        u = str(r.get("uscita") or "").strip()
        cod = r.get("codice")
        return _breve((f"uscita {cod}: " if cod not in (None, 0) else "") + (u or "nessuna uscita"))
    if r.get("ok") is True:
        return _breve(r.get("nota") or "fatto")
    if r.get("ok") is False:
        return _breve(r.get("nota") or "non riuscito")
    return _breve(json.dumps(r, ensure_ascii=False, default=str))


class _Segue:
    """Quello che la scheda di un lavoro mostra oltre ai campi del lavoro."""

    def __init__(self, lav):
        self.lav = lav
        self.passi: deque = deque(maxlen=PASSI_RECENTI)
        self.file: dict[str, int] = {}        # nome → righe, nell'ordine dell'ultima scrittura
        self.anteprima: dict | None = None
        self.test: dict | None = None
        self.sporco = True
        self.finale_pendente = False           # una finale da costruire nel thread
        self.chiuso = False                    # finale mandata: niente più aggiornamenti
        self.ultimo = float("-inf")            # monotonic dell'ultimo invio
        self.inviate = 0
        self.pausa = False                     # ultima pausa mandata
        # ── il flusso a sequenza (08/10) ──
        self.uid = secrets.token_hex(4)        # cambia se l'id del lavoro si ripete (riavvio)
        self.n = 0                             # ultimo pezzo numerato
        self.sez = 0                           # sezione corrente
        self.sez_tipo = ""
        self.sez_file = ""
        self.nuovi: list = []                  # [sezione, tipo, file, [testi]] da numerare
        self.finestra: deque = deque()         # gli ultimi pezzi mandati (per la cronologia)
        self.fin_car = 0
        self.taglio = False                    # la finestra ha perso l'inizio
        self.arg: _Argomenti | None = None     # la chiamata in arrivo (argomenti a pezzi)
        self.reg_coda: list = []               # pezzi da scrivere nel registro
        self.reg_car = 0
        self.reg_path: Path | None = None
        self.reg_byte = 0
        self.reg_s = 0                         # sezione dell'ultimo pezzo scritto
        self.reg_recinto = False               # un blocco di codice aperto nel registro
        self.reg_pieno = False


class Avanzamento:
    def __init__(self, tetti, arbitro=None, finale=None, log=print,
                 intervallo: float = INTERVALLO_S, sviluppo=None):
        """`tetti()` → (passate, token, secondi) massimi per giro; `finale(lav)` → la scheda
        finale (Lavori.scheda) o None; `sviluppo(lav)` → il riepilogo dello sviluppo del
        lavoro (calliope/sviluppo.py, `Sviluppi.riepilogo_lavoro`) o None."""
        self.tetti = tetti
        self.arbitro = arbitro
        self.costruisci_finale = finale
        self.sviluppo = sviluppo
        self.log = log
        self.intervallo = float(intervallo)
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._invio = threading.Lock()         # una scheda alla volta, nell'ordine giusto
        self._segue: dict[str, _Segue] = {}
        self._thread = None
        self._chiuso = False
        self.inviate = 0

    # ─────────────────────────── da chi lavora: mai bloccante ───────────────────────────
    def segui(self, lav):
        """Comincia a seguire `lav` (alla delega, con gli schermi): la prima scheda parte
        subito e porta il lavoro in cima."""
        if getattr(lav, "on_scheda", None) is None:
            return
        with self._lock:
            if lav.id not in self._segue:
                self._segue[lav.id] = _Segue(lav)
                if lav.passo and lav.passo not in _PASSI_MUTI:
                    self._segue[lav.id].passi.append((time.time(), lav.passo))
            if self._thread is None and not self._chiuso:
                self._thread = threading.Thread(target=self._ciclo, daemon=True,
                                                name="lavori-schermo")
                self._thread.start()
            self._cv.notify()
        lav.osservatore = self._evento

    @staticmethod
    def _aggiungi(sg: _Segue, tipo: str, testo: str, file: str = "", nuova: bool = False):
        """Un pezzo di flusso (con il lock): nella sezione corrente se è dello stesso tipo
        (e dello stesso file), altrimenti in una sezione nuova."""
        if not testo:
            return
        if nuova or tipo != sg.sez_tipo or file != sg.sez_file:
            sg.sez += 1
            sg.sez_tipo, sg.sez_file = tipo, file
        if sg.nuovi and sg.nuovi[-1][0] == sg.sez:
            sg.nuovi[-1][3].append(testo)
        else:
            sg.nuovi.append([sg.sez, tipo, file, [testo]])

    def _evento(self, lav, evento: str, dati: dict):
        with self._lock:
            sg = self._segue.get(lav.id)
            if sg is None:
                return
            if evento == "passo":
                p = lav.passo
                if p and p not in _PASSI_MUTI and (not sg.passi or sg.passi[-1][1] != p):
                    sg.passi.append((time.time(), p))
            elif evento == "stato":
                if lav.stato in ("in_coda", "in_corso") and sg.chiuso:
                    sg.chiuso = False          # ripresa dopo una risposta
            elif evento == "passata":
                sg.arg = None
                giro = int(getattr(lav, "giro", 1) or 1)
                self._aggiungi(sg, "passata", (f"giro {giro} · " if giro > 1 else "")
                               + f"passata {lav.passi + 1}", nuova=True)
                return                          # niente da mostrare finché non arriva testo
            elif evento == "flusso":
                tipo, t = dati.get("tipo") or "testo", str(dati.get("testo") or "")
                if tipo == "chiamata":
                    if sg.arg is None:
                        sg.arg = _Argomenti()
                    nuovo = sg.arg.aggiungi(t)
                    if not nuovo:
                        return
                    self._aggiungi(sg, "codice", nuovo, sg.arg.percorso)
                else:
                    if tipo not in TIPI_FLUSSO:
                        tipo = "testo"
                    self._aggiungi(sg, tipo, t)
            elif evento == "strumento":
                sg.arg = None
                self._aggiungi(sg, "strumento", chiamata_breve(str(dati.get("nome") or "?"),
                                                              dati.get("argomenti")), nuova=True)
                return                          # l'esito arriva subito dopo
            elif evento == "esito":
                self._aggiungi(sg, "esito", esito_breve(str(dati.get("nome") or ""),
                                                        dati.get("esito")), nuova=True)
            elif evento == "file":
                nome, testo = str(dati.get("nome") or "file"), str(dati.get("testo") or "")
                sg.file.pop(nome, None)
                sg.file[nome] = testo.count("\n") + (0 if testo.endswith("\n") else 1)
                while len(sg.file) > FILE_MAX:
                    sg.file.pop(next(iter(sg.file)))
                if lav.tipo == "codice":
                    sg.anteprima = {"nome": nome, "testo": _anteprima(testo)}
                sg.arg = None
            elif evento == "test":
                e = dati.get("esito")
                if isinstance(e, dict):
                    sg.test = {k: int(e.get(k) or 0)
                               for k in ("eseguiti", "falliti", "errori", "saltati")}
            sg.sporco = True
            self._cv.notify()

    def finale(self, lav, sincrona: bool = True) -> bool:
        """La scheda finale (o della domanda) di `lav`, con `sposta`: dal thread dei lavori
        la costruisce e la manda subito, prima dell'annuncio; dagli altri thread (la voce che
        annulla) la passa al thread degli schermi (`sincrona=False`)."""
        with self._lock:
            sg = self._segue.get(lav.id)
            if sg is None:
                return False
            if not sincrona:
                sg.finale_pendente = True
                self._cv.notify()
                return True
        self._manda_finale(sg)
        return True

    def chiudi(self):
        with self._lock:
            self._chiuso = True
            self._cv.notify_all()

    # ─────────────────────────── il thread degli schermi ───────────────────────────
    def _in_pausa(self) -> bool:
        arb = self.arbitro
        if arb is None or not getattr(arb, "condiviso", False):
            return False
        try:
            return bool(arb.in_pausa())
        except Exception:  # noqa: BLE001
            return False

    def _ciclo(self):
        while True:
            pronti, finali, seguiti = [], [], []
            with self._lock:
                if self._chiuso:
                    return
                ora = time.monotonic()
                attesa = None
                # Con l'arbitro si guarda la pausa a ogni intervallo, finché un lavoro corre
                if getattr(self.arbitro, "condiviso", False):
                    seguiti = [sg for sg in self._segue.values()
                               if not sg.chiuso and sg.lav.stato == "in_corso"]
                    if seguiti:
                        attesa = self.intervallo
                for sg in list(self._segue.values()):
                    if sg.finale_pendente:
                        sg.finale_pendente = False
                        finali.append(sg)
                    elif sg.chiuso or not sg.sporco:
                        continue
                    elif sg.lav.stato in FINALI:
                        sg.sporco = False       # la scheda la manda `finale`
                    elif ora - sg.ultimo >= self.intervallo:
                        pronti.append(sg)
                    else:
                        resto = sg.ultimo + self.intervallo - ora
                        attesa = resto if attesa is None else min(attesa, resto)
                if not pronti and not finali and not seguiti:
                    self._cv.wait(attesa)
                    continue
            pausa = self._in_pausa() if seguiti else False
            for sg in finali:
                self._manda_finale(sg)
            for sg in seguiti:
                if sg not in pronti and sg.pausa != pausa and \
                        time.monotonic() - sg.ultimo >= self.intervallo:
                    pronti.append(sg)
            for sg in pronti:
                self._manda(sg, pausa)
            if not pronti and not finali:
                with self._lock:
                    if not self._chiuso:
                        self._cv.wait(attesa)

    # ─────────────────────────── il flusso numerato ───────────────────────────
    @staticmethod
    def _numera(sg: _Segue) -> list[dict]:
        """I pezzi in arrivo dall'ultimo invio, numerati (con il lock): vanno nella scheda,
        nella finestra della cronologia e nella coda del registro."""
        out = []
        for s, tipo, file, testi in sg.nuovi:
            sg.n += 1
            p = {"n": sg.n, "s": s, "t": tipo, "x": "".join(testi)}
            if file:
                p["f"] = file
            out.append(p)
            sg.finestra.append(p)
            sg.fin_car += len(p["x"])
            if sg.reg_car < REGISTRO_ATTESA:
                sg.reg_coda.append(p)
                sg.reg_car += len(p["x"])
        sg.nuovi = []
        while sg.fin_car > FINESTRA and len(sg.finestra) > 1:
            sg.fin_car -= len(sg.finestra.popleft()["x"])
            sg.taglio = True
        if sg.fin_car > FINESTRA and sg.finestra:
            # Un pezzo solo più lungo della finestra (un file enorme in un colpo): la coda
            p = sg.finestra[0]
            sg.finestra[0] = dict(p, x=p["x"][-FINESTRA:])
            sg.fin_car = len(sg.finestra[0]["x"])
            sg.taglio = True
        return out

    def _flussi(self, sg: _Segue, pezzi: list[dict]) -> tuple[dict, dict]:
        """(flusso dell'invio, flusso per la cronologia) della scheda (con il lock)."""
        base = {"id": sg.uid, "fino": sg.n}
        vivo = dict(base, pezzi=pezzi)
        storia = dict(base, pezzi=list(sg.finestra), finestra=True,
                      taglio=bool(sg.taglio))
        return vivo, storia

    def _registro(self, sg: _Segue):
        """Scrive nel registro su disco i pezzi in coda (fuori dal lock, dal thread degli
        schermi). Il registro è in Markdown: separatori di passata, ragionamento e testo
        come paragrafi, codice in blocchi, chiamate ed esiti in una riga."""
        lav = sg.lav
        with self._lock:
            if sg.reg_path is None:
                cartella = getattr(lav, "cartella", None)
                if not cartella:
                    return
                sg.reg_path = Path(cartella) / REGISTRO_NOME
            coda, sg.reg_coda, sg.reg_car = sg.reg_coda, [], 0
        if not coda or sg.reg_pieno:
            return
        parti = []
        if sg.reg_byte == 0:
            parti.append(f"# Registro del lavoro {lav.id}: {getattr(lav, 'titolo', '')}\n\n"
                         f"Il flusso dell'agente come è arrivato sugli schermi: ragionamento, "
                         f"testo, codice, strumenti ed esiti.\n")
        for p in coda:
            nuova = p["s"] != sg.reg_s
            if nuova and sg.reg_recinto:
                parti.append("\n`````\n")
                sg.reg_recinto = False
            t, x = p["t"], p["x"]
            if t == "passata":
                parti.append(f"\n---\n\n## {x}\n")
            elif t == "strumento":
                parti.append(f"\n→ {x}\n")
            elif t == "esito":
                parti.append(f"← {x}\n")
            elif t == "codice":
                if nuova:
                    parti.append(f"\n*Codice{': ' + p['f'] if p.get('f') else ''}*\n\n`````\n")
                    sg.reg_recinto = True
                parti.append(x)
            else:
                if nuova:
                    parti.append("\n*Ragionamento*\n\n" if t == "pensiero" else "\n*Testo*\n\n")
                parti.append(x)
            sg.reg_s = p["s"]
        dati = "".join(parti).encode("utf-8")
        if sg.reg_byte + len(dati) > REGISTRO_MAX:
            dati = "\n\n*(registro troppo lungo: il resto non è stato scritto)*\n".encode()
            sg.reg_pieno = True
        try:
            sg.reg_path.parent.mkdir(parents=True, exist_ok=True)
            with open(sg.reg_path, "ab") as f:
                f.write(dati)
            sg.reg_byte += len(dati)
        except OSError as e:
            sg.reg_pieno = True
            self.log(f"[AGENTI] {lav.id}: registro non scritto: {e}")

    def _scaricabile(self, sg: _Segue, card: dict) -> dict:
        """La scheda con «Scarica il registro», se il registro c'è (hub.py lo registra solo
        per gli schermi personali di chi l'ha chiesto, come «Scarica» dei documenti)."""
        if sg.reg_path is None or sg.reg_byte <= 0:
            return card
        lav = sg.lav
        return {**card, "registro": {"chiave": f"registro:{lav.id}", "formati": ["md"]},
                "_registro": {"markdown_file": str(sg.reg_path),
                              "titolo": f"Registro di {getattr(lav, 'titolo', lav.id)}"}}

    # ─────────────────────────── la scheda ───────────────────────────
    def _riepilogo_sviluppo(self, lav):
        if self.sviluppo is None:
            return None
        try:
            return self.sviluppo(lav)
        except Exception as e:  # noqa: BLE001 — la scheda va anche senza
            self.log(f"[AGENTI] riepilogo dello sviluppo non letto: {type(e).__name__}: {e}")
            return None

    def _istantanea(self, sg: _Segue, pausa: bool) -> dict:
        """I dati dell'avanzamento (con il lock)."""
        lav = sg.lav
        try:
            passate, token, secondi = self.tetti(lav)     # il tetto dei token è per tipo
        except TypeError:
            passate, token, secondi = self.tetti()
        # Per giro (08/10): un lavoro di uno sviluppo continuato dopo una tappa ha di nuovo
        # tutte le passate, il tempo e i token (ciclo._tetti): i tetti mostrati sono cumulativi,
        # come i conti (passate, token e minuti del lavoro intero)
        giro = max(1, int(getattr(lav, "giro", 1) or 1))
        ora = time.time()
        corre = lav.stato == "in_corso"
        trascorso = 0.0
        if lav.inizio:
            fine = lav.fine or (lav.attesa_dal if lav.stato == "in_attesa" else None) or ora
            trascorso = max(0.0, fine - lav.inizio - lav.attesa_s)
        av = {"passo": lav.passo if lav.passo not in _PASSI_MUTI else "",
              "pausa": bool(pausa and corre),
              "passi": [{"ora": round(t, 1), "testo": p} for t, p in sg.passi],
              "file": [{"nome": n, "righe": r} for n, r in reversed(list(sg.file.items()))],
              "anteprima": dict(sg.anteprima) if sg.anteprima else None,
              "test": dict(sg.test) if sg.test else None,
              "giro": giro,
              "passate": lav.passi, "max_passate": int(passate) * giro,
              "token": lav.token, "max_token": int(token) * giro,
              "ragionamento": int(getattr(lav, "ragionamento", 0) or 0),
              "trascorso_s": round(trascorso, 1), "max_s": round(float(secondi)) * giro,
              # da quando contare (epoch) se il lavoro corre: la pagina conta da sola
              "dal": round(ora - trascorso, 1) if corre else None,
              "ora_server": round(ora, 3)}
        return av

    def _manda(self, sg: _Segue, pausa: bool):
        from ..schermi import schede
        lav = sg.lav
        svil = self._riepilogo_sviluppo(lav)
        with self._invio:
            with self._lock:
                if sg.chiuso or lav.stato in FINALI:
                    sg.sporco = False
                    return
                sg.sporco = False
                av = self._istantanea(sg, pausa)
                vivo, storia = self._flussi(sg, self._numera(sg))
                prima = sg.inviate == 0
                sg.pausa = av["pausa"]
            self._registro(sg)
            av["flusso"] = vivo
            if svil:
                av["sviluppo"] = svil
            card = schede.lavoro_avanzamento(lav.titolo, lav.tipo, lav.stato, av, ident=lav.id,
                                             sposta=prima)
            card["_storia"] = {"avanzamento": {**card["avanzamento"], "flusso": storia}}
            self._consegna(lav, self._scaricabile(sg, card))
            with self._lock:
                sg.ultimo = time.monotonic()
                sg.inviate += 1

    def _manda_finale(self, sg: _Segue):
        lav = sg.lav
        svil = self._riepilogo_sviluppo(lav)
        with self._invio:
            with self._lock:
                av = self._istantanea(sg, False)
                # Gli ultimi pezzi arrivati vanno con la finale: il flusso resta intero nella
                # pagina, e nel registro
                vivo, storia = self._flussi(sg, self._numera(sg))
                sg.chiuso = True
                sg.sporco = False
                if lav.stato != "in_attesa":
                    self._segue.pop(lav.id, None)
            self._registro(sg)
            av["flusso"] = vivo
            if svil:
                av["sviluppo"] = svil
            card = None
            if self.costruisci_finale is not None:
                try:
                    card = self.costruisci_finale(lav)
                except Exception as e:  # noqa: BLE001 — lo schermo non ferma l'annuncio
                    self.log(f"[AGENTI] scheda finale non costruita: {type(e).__name__}: {e}")
            if card is None:
                from ..schermi import schede
                card = schede.lavoro_avanzamento(lav.titolo, lav.tipo, lav.stato, av,
                                                 ident=lav.id, sposta=True)
                av = card["avanzamento"]
            else:
                # La stessa identità della scheda in corso: la sostituisce (anche quella del
                # documento), e porta il lavoro in cima
                card = {**card, "chiave": f"lavoro:{lav.id}", "avanzamento": av}
                card.pop("sposta", None)
            card["_storia"] = {"avanzamento": {**av, "flusso": storia}}
            self._consegna(lav, self._scaricabile(sg, card))
            with self._lock:
                sg.ultimo = time.monotonic()
                sg.inviate += 1

    def _consegna(self, lav, card: dict):
        fn = getattr(lav, "on_scheda", None)
        if fn is None:
            return
        try:
            fn(card)
            self.inviate += 1
        except Exception as e:  # noqa: BLE001
            self.log(f"[AGENTI] scheda non inviata: {e}")
