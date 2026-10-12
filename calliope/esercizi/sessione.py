"""
Il servizio degli esercizi (08/10/2026): una sessione per persona, a voce e sulla scheda
insieme, con la regola dei compiti guidati nel codice.

Flusso (docs/ricerche/2026-10-08-esercizi.md, § 3):
- **inizia** (tool `esercizi`, a voce): materia, argomento e classe (dall'età se non detta);
  la prima domanda detta e la scheda sugli schermi personali di chi studia;
- **rispondi** (a voce: il modello passa la risposta come l'ha sentita; sulla scheda: il campo o
  i pulsanti, `POST /api/esercizio`, senza passare dal modello): la correzione la fa il codice
  (`controlla`), mai il modello; giusta → la prossima; sbagliata → un indizio diverso;
  dopo `minori_compiti_tentativi` (5) la spiegazione, con l'avviso ai tutori una volta per
  sessione;
- **aiuto** (un indizio, non conta come errore), **salta** (niente soluzione), **ripeti**,
  **segnala** («secondo me è sbagliato»: ricontrollo, segnalazione e avviso ai tutori),
  **fine** (il conto della sessione), **riepilogo** (per i tutori: frase e scheda col
  dettaglio e un campione da controllare), **argomenti**.

Il livello si adatta: tre giuste di fila al primo colpo → più difficile; una spiegata o due
con più errori → più facile. Le frasi sono pronte (`risposta_finale`): nessuna seconda passata
del modello, e la domanda finisce con «?» così la sessione resta come azione in sospeso per la
frase dopo (Brain.set_pending con il messaggio `ESERCIZI_MSG`).

Il tempo di studio non conta nel tempo di gioco (decisione del 07/10): la scheda non è un
gioco e non manda battiti; i secondi stanno nel registro dei tentativi.
"""

from __future__ import annotations

import collections
import json
import queue
import random
import re
import secrets
import threading
import time

from . import (MATERIE, Classe, adatto, argomenti, argomento_da_testo, calcolata,
               classe_da_eta, classe_da_testo, controlla, elenco_materie, genera, livello_per,
               materia_da_testo, nome_argomento, solo_materia)
from .modello import Esercizio, Esito
from .registro import Registro

SCADENZA_S = 30 * 60              # una sessione ferma da più di così è finita
PRONTI = 3                        # esercizi d'italiano controllati in anticipo per livello

# L'esercizio in corso come azione in sospeso (come i compiti, tools/minori.COMPITI_MSG): il
# testo arriva subito prima della frase del ragazzo, dove il modello lo legge di sicuro
ESERCIZI_MSG = ("Esercizi in corso, messaggio di sistema: hai appena chiesto «{domanda}». Se in "
                "questa frase dà una risposta, chiama subito esercizi con azione=rispondi e "
                "risposta con le sue parole esatte (mai il numero che ti aspetti), senza dire tu "
                "se è giusta. Se chiede un indizio: azione=aiuto; se vuole saltare: salta; se "
                "dice che l'esercizio è sbagliato: segnala; se vuole ripetere la domanda: ripeti; "
                "una pausa: pausa; smettere: fine. Se vuole gli esercizi in un altro modo (più "
                "giocosi, a punti, a tappe, più corti o più lunghi): azione=preferenze. Anche "
                "una parola o un numero da soli («Sei.», «Tre quarti.», «Verbo.») sono una "
                "risposta. Le domande le fa solo il programma: non inventarne tu, nemmeno per "
                "gioco. Se parla d'altro, rispondi normalmente.")
# La spinta di Brain quando, con l'esercizio in sospeso, il modello risponde senza il tool
# (rete `spinta_esercizi`): la risposta trattenuta non si dice
ESERCIZI_NUDGE = ("Esercizi in corso: non hai chiamato esercizi. Se la frase del ragazzo è una "
                  "risposta all'esercizio, chiama adesso esercizi con azione=rispondi e la "
                  "risposta con le sue parole esatte: la corregge il programma, non tu. Per un "
                  "indizio azione=aiuto, per saltare salta, se dice che è sbagliato segnala, per "
                  "una pausa pausa, per smettere fine; per cambiare il modo (più giocosi, a punti, "
                  "a tappe, più corti) preferenze. Non inventare domande d'esercizio e non "
                  "promettere di segnarti qualcosa: lo fa il programma. Solo se parla d'altro "
                  "rispondi normalmente, senza dire se l'esercizio è giusto.")
# Fine di un blocco (12/10): la proposta detta dal codice e il messaggio per la risposta
PAUSA_DOMANDA = "Facciamo una pausa o cambiamo?"
PAUSA_MSG = ("Esercizi, messaggio di sistema: hai chiesto se fare una pausa o cambiare. Se vuole "
             "la pausa: esercizi azione=pausa; se vuole finire: fine; se vuole cambiare "
             "argomento o materia: azione=inizia con quello che dice (senza argomento se non lo "
             "dice); se vuole andare avanti con questi: azione=continua. Non fare tu domande "
             "d'esercizio.")
# Dopo la spinta il modello non chiama ancora il tool e promette di segnarsi una preferenza
# («Ricevuto. Segno tutto», DGX del 12/10): non si dice, al suo posto questa
PROMESSA_FRASE = ("Non l'ho ancora salvato. Dimmi come vuoi gli esercizi: più giocosi, a punti, a "
                  "tappe, oppure blocchi più corti?")

# Una domanda d'esercizio fatta dal modello (12/10: «quanto fa 125 più 87?», «45 più 38?»):
# «quanto fa/viene/vale», «risolvi», «calcola», o due numeri con un'operazione, in una frase
# che finisce con «?»
_DOMANDA = re.compile(r"\bquant[oie]\s+(?:fa|fanno|viene|vengono|vale|valgono|resta|restano|"
                      r"ne\s+restano|sono\s+in\s+tutto)\b|\brisolvi\b|\bcalcola\b"
                      r"|\d+\s*(?:più|meno|per|diviso|x|×|\+|−|-|:)\s*\d+", re.I)
_OPERAZIONE = re.compile(r"([a-zàèéìòù]+)\s+(?:più|meno|per|diviso)\s+([a-zàèéìòù]+)", re.I)
# Una promessa di segnarsi qualcosa, senza tool («Segno tutto», «me lo segno», «terrò conto»)
_PROMESSA = re.compile(r"(?<!non )\b(?:segno|me lo segno|me li segno|annoto|me lo annoto|"
                       r"terrò (?:conto|a mente)|me lo ricorderò|lo ricorderò|ne terrò conto|"
                       r"lo terrò presente)\b", re.I)


def domanda_inventata(testo: str) -> bool:
    """Il testo contiene una domanda d'esercizio (una frase con «?» che chiede un conto)?"""
    from .numeri import parola_numero
    for frase in re.split(r"(?<=[.!?…])\s+", str(testo or "")):
        if "?" not in frase:
            continue
        if _DOMANDA.search(frase):
            return True
        for m in _OPERAZIONE.finditer(frase):
            if parola_numero(m.group(1)) is not None and parola_numero(m.group(2)) is not None:
                return True
    return False


def testo_del_modello(testo: str) -> str | None:
    """Con gli esercizi aperti, cosa c'è di sbagliato nel testo detto senza il tool:
    «domanda» (una domanda d'esercizio inventata), «promessa» (segnarsi qualcosa), None."""
    if domanda_inventata(testo):
        return "domanda"
    if _PROMESSA.search(str(testo or "")):
        return "promessa"
    return None


def _norm(t: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", str(t or "").casefold()).split())


def aperta_di(tool_ctx) -> bool:
    """Chi parla ha una sessione di esercizi aperta (anche in pausa)? Per Brain (rete
    `spinta_esercizi` anche senza l'azione in sospeso)."""
    try:
        srv = servizio()
        sc = getattr(tool_ctx, "speaker_ctx", None)
        nome = getattr(sc, "current_speaker", None)
        reg = getattr(tool_ctx, "speakers", None)
        if srv is None or not nome or reg is None:
            return False
        prof = reg.get(nome)
        return prof is not None and srv.sessione(prof.id) is not None
    except Exception:  # noqa: BLE001 — la rete non deve fermare la risposta
        return False


def blocco_per(classe: Classe | None, cfg=None) -> int:
    """Esercizi di un blocco prima di «Facciamo una pausa o cambiamo?» (12/10, decisione di
    Dario): più corto per i piccoli, 5 in prima, seconda e terza elementare, 10 dopo."""
    piccoli = int(getattr(cfg, "esercizi_blocco_piccoli", 5) or 5)
    altri = int(getattr(cfg, "esercizi_blocco", 10) or 10)
    if classe is not None and classe.scuola == "elementari" and classe.anno <= 3:
        return piccoli
    return altri
ARGOMENTO_MSG = ("Esercizi, messaggio di sistema: hai chiesto quale argomento di {materia}. Se "
                 "risponde con un argomento, chiama esercizi con azione=inizia, "
                 "materia={materia} e argomento come l'ha detto{classe}.")

BRAVO = {"f": ("Giusto!", "Esatto!", "Brava!", "Perfetto!"),
         "m": ("Giusto!", "Esatto!", "Bravo!", "Perfetto!")}
# Il modo giocoso (12/10): complimenti e domande dette dal codice, mai dal modello
BRAVO_GIOCO = {"f": ("Centro!", "Fantastico!", "Che campionessa!", "Grandiosa!"),
               "m": ("Centro!", "Fantastico!", "Che campione!", "Grandioso!")}
SFIDE = ("Sfida numero {n}:", "Ecco la sfida {n}:", "Via con la sfida {n}:")


def conto_detto(fatti: int, giuste: int) -> str:
    """«1 esercizio, 1 giusto», «10 esercizi, 8 giusti», «3 esercizi, nessuno giusto»."""
    es = "1 esercizio" if fatti == 1 else f"{fatti} esercizi"
    g = "nessuno giusto" if giuste == 0 else "1 giusto" if giuste == 1 else f"{giuste} giusti"
    return f"{es}, {g}"


def _indizi(es: Esercizio) -> list[str]:
    """Gli indizi non vuoti dell'esercizio."""
    return [str(x).strip() for x in (es.suggerimenti or []) if str(x or "").strip()]


def _o(prof) -> str:
    return "a" if getattr(prof, "gender", None) == "f" else "o"


class Sessione:
    def __init__(self, persona, nome, gender, materia, argomento, classe: Classe, livello,
                 fascia, mittente=None):
        self.id = secrets.token_hex(4)
        self.persona, self.nome, self.gender = persona, nome, gender
        self.materia, self.argomento, self.classe = materia, argomento, classe
        self.livello, self.fascia = livello, fascia
        self.mittente = mittente
        self.es: Esercizio | None = None
        self.errori = 0                    # risposte sbagliate sull'esercizio in corso
        self.aiuti = 0                     # indizi dati sull'esercizio in corso
        self.inizio_es = time.monotonic()
        self.fila_giuste = 0
        self.fila_difficili = 0
        self.fatti = 0
        self.giuste = 0
        self.spiegati = 0
        self.recenti: collections.deque = collections.deque(maxlen=200)
        self.ultimo = time.monotonic()
        self.aperta = True
        self.avvisato = False              # avviso ai tutori per una spiegazione, una volta
        self.esito: dict = {}              # l'ultimo esito da mostrare sulla scheda
        self.cambio_livello = 0
        # Blocchi, pausa, modo (12/10): contati dal codice, detti dalle sue frasi
        self.blocco = 10                   # esercizi per blocco, poi «pausa o cambiamo?»
        self.nel_blocco = 0
        self.in_pausa = False
        self.giocoso = False
        self.punti_on = False
        self.tappe_on = False
        self.punti = 0
        self.tappa = 1

    def applica(self, pref: dict, cfg=None):
        """Le preferenze salvate della persona (Registro.preferenze)."""
        self.giocoso = bool(pref.get("giocoso"))
        self.punti_on = bool(pref.get("punti")) or self.giocoso
        self.tappe_on = bool(pref.get("tappe"))
        b = pref.get("blocco")
        self.blocco = (max(2, min(20, int(b))) if isinstance(b, int) and b > 0
                       else blocco_per(self.classe, cfg))

    @property
    def scaduta(self) -> bool:
        return time.monotonic() - self.ultimo > SCADENZA_S


class Servizio:
    def __init__(self, cfg, registro: Registro, schermi=None, biblioteca=None, log=print,
                 parere=None, wikizionario=None, registry=None):
        self.cfg = cfg
        self.registry = registry           # SpeakerRegistry: i profili per id (la scheda)
        self.registro = registro
        self.schermi = schermi
        self.log = log
        self._lock = threading.RLock()
        self.sessioni: dict[str, Sessione] = {}
        self._biblioteca = biblioteca
        self._parere = parere
        self._diz = wikizionario
        self._diz_cercato = wikizionario is not None
        self._pronti: dict[tuple, collections.deque] = {}
        self._coda: queue.Queue = queue.Queue()
        self._lavoratore: threading.Thread | None = None
        self.rng = random.Random()

    # ── utilità ──
    @property
    def massimo(self) -> int:
        return int(getattr(self.cfg, "minori_compiti_tentativi", 5) or 5)

    @property
    def parere(self):
        if self._parere is None:
            from .verifica import SecondoParere
            self._parere = SecondoParere(self.cfg)
        return self._parere

    @property
    def wikizionario(self):
        if not self._diz_cercato:
            self._diz_cercato = True
            from .verifica import Wikizionario
            self._diz = Wikizionario.da_config(self.cfg, self._biblioteca)
        return self._diz

    def sessione(self, persona: str) -> Sessione | None:
        with self._lock:
            s = self.sessioni.get(persona)
            if s is not None and (s.scaduta or not s.aperta):
                self.sessioni.pop(persona, None)
                return None
            return s

    # ── esercizi ──
    def _nuovo_seme(self) -> int:
        return self.rng.randrange(1, 2**31)

    def _prossimo(self, s: Sessione) -> Esercizio | None:
        escludi = set(s.recenti) | self.registro.fatti_di_recente(s.persona)
        mod = MATERIE[s.materia]
        if not calcolata(s.materia):
            es = self._prossimo_italiano(s.argomento, s.livello, escludi)
        else:
            es = None
            for _ in range(30):
                try:
                    cand = mod.genera(s.argomento, s.livello, self._nuovo_seme())
                except ValueError as e:
                    # Il ricalcolo non torna (o una sequenza ambigua): mai al ragazzo
                    self.log(f"   [ESERCIZI] scartato dal ricalcolo: {e}")
                    continue
                if cand.firma not in escludi:
                    es = cand
                    break
        if es is not None:
            s.es, s.errori, s.aiuti = es, 0, 0
            s.inizio_es = time.monotonic()
            s.recenti.append(es.firma)
        return es

    def _verifica_italiano(self, es: Esercizio) -> dict:
        """L'esito del controllo, dal banco se l'esercizio era già stato controllato."""
        gia = self.registro.banco_leggi(es.firma)
        if gia is not None and gia[0] in ("buono", "scartato"):
            return dict(gia[1], esito=gia[0])
        from .verifica import verifica_italiano
        v = verifica_italiano(es, self.wikizionario, self.parere)
        if v["esito"] in ("buono", "scartato"):
            try:
                self.registro.banco_scrivi(es, v["esito"], v)
            except Exception:  # noqa: BLE001 — il banco è una cache: senza si rifà la domanda
                pass
        return v

    def _prossimo_italiano(self, argomento: str, livello: int, escludi: set) -> Esercizio | None:
        chiave = (argomento, livello)
        with self._lock:
            coda = self._pronti.setdefault(chiave, collections.deque())
            while coda:
                es = coda.popleft()
                if es.firma not in escludi:
                    self._chiedi_riempimento(chiave)
                    return es
        for es in self.registro.banco_buoni(argomento, livello, escludi, n=1):
            self._chiedi_riempimento(chiave)
            es.verifica = dict(es.verifica, banco=True)
            return es
        senza = bool(getattr(self.cfg, "esercizi_senza_secondo_parere", False))
        for _ in range(6):
            es = genera(argomento, livello, self._nuovo_seme())
            if es.firma in escludi:
                continue
            v = self._verifica_italiano(es)
            es.verifica = v
            if v["esito"] == "buono" or (v["esito"] == "non_verificato" and senza):
                self._chiedi_riempimento(chiave)
                return es
            if v["esito"] == "non_verificato":
                # Il secondo modello non risponde: inutile insistere ora
                self.log(f"   [ESERCIZI] secondo parere non disponibile "
                         f"({v.get('errore') or v.get('modello')})")
                return None
        return None

    def _chiedi_riempimento(self, chiave):
        self._coda.put(chiave)
        if self._lavoratore is None or not self._lavoratore.is_alive():
            self._lavoratore = threading.Thread(target=self._lavora, daemon=True,
                                                name="esercizi-pronti")
            self._lavoratore.start()

    def _lavora(self):
        """In secondo piano: tiene `PRONTI` esercizi d'italiano controllati per livello."""
        n_pronti = int(getattr(self.cfg, "esercizi_pronti", PRONTI) or 0)
        while True:
            try:
                chiave = self._coda.get(timeout=60)
            except queue.Empty:
                return
            argomento, livello = chiave
            tentativi = 0
            while tentativi < 4 * max(1, n_pronti):
                with self._lock:
                    if len(self._pronti.setdefault(chiave, collections.deque())) >= n_pronti:
                        break
                tentativi += 1
                es = genera(argomento, livello, self._nuovo_seme())
                try:
                    v = self._verifica_italiano(es)
                except Exception as e:  # noqa: BLE001
                    self.log(f"   [ESERCIZI] controllo fallito: {type(e).__name__}")
                    break
                if v["esito"] == "non_verificato":
                    break
                if v["esito"] == "buono":
                    es.verifica = v
                    with self._lock:
                        self._pronti[chiave].append(es)

    def prepara(self, argomento: str, livello: int):
        """Prepara in secondo piano gli esercizi d'italiano di quel livello (all'inizio di una
        sessione: il primo arriva mentre si dice la frase d'inizio)."""
        if argomenti().get(argomento, ("",))[0] == "italiano":
            self._chiedi_riempimento((argomento, livello))

    # ── frasi ──
    def _domanda(self, s: Sessione) -> str:
        if not s.es:
            return ""
        if s.giocoso:
            v = s.es.voce
            return f"{self.rng.choice(SFIDE).format(n=s.fatti + 1)} {v[:1].lower()}{v[1:]}"
        return s.es.voce

    def _pausa_out(self, s: Sessione, frase: str, regola: str | None = None) -> dict:
        """La frase con la proposta «pausa o cambiamo?» in sospeso (PAUSA_MSG)."""
        out = self._final(frase)
        if frase.rstrip().endswith("?"):
            out["in_sospeso"] = {"tool": "esercizi", "argomenti": {"azione": "continua"},
                                 "domanda": "?", "cosa": "gli esercizi", "messaggio": PAUSA_MSG}
        if regola:
            out["regola"] = regola
        self._scheda(s)
        return out

    def _ferma(self, s: Sessione) -> dict:
        """Una risposta o un'azione mentre la sessione aspetta «pausa o cambiamo?»."""
        return self._pausa_out(s, "Siamo in pausa: continuiamo o cambiamo?",
                               "esercizi_in_pausa")

    def _dopo(self, s: Sessione, frase: str, **extra) -> dict:
        """Dopo un esercizio chiuso (giusto, spiegato, saltato): la prossima domanda o, a fine
        blocco, la proposta del codice «Facciamo una pausa o cambiamo?» (12/10)."""
        s.nel_blocco += 1
        if s.nel_blocco >= max(1, s.blocco):
            return self._fine_blocco(s, frase)
        if self._prossimo(s) is None:
            return self._chiudi(s, frase + " Per ora gli esercizi sono finiti.")
        return self._risultato(s, f"{frase} Prossima: {self._domanda(s)}", **extra)

    def _fine_blocco(self, s: Sessione, frase: str) -> dict:
        s.nel_blocco = 0
        conto = f" Siamo a {conto_detto(s.fatti, s.giuste)}."
        if s.punti_on:
            conto += f" Hai {s.punti} punt{'o' if s.punti == 1 else 'i'}."
        tappe = int(getattr(self.cfg, "esercizi_tappe", 3) or 3)
        if s.tappe_on:
            if s.tappa >= tappe:
                return self._chiudi(s, f"{frase} Hai superato anche l'ultima tappa: percorso "
                                       f"finito!" + (f" Hai {s.punti} punti." if s.punti_on
                                                     else ""))
            conto = f" Tappa {s.tappa} di {tappe} superata!" + conto
            s.tappa += 1
        s.es, s.in_pausa = None, True
        s.esito = {"testo": (frase + conto).strip(), "giusta": None}
        return self._pausa_out(s, f"{frase}{conto} {PAUSA_DOMANDA}", "esercizi_fine_blocco")

    @staticmethod
    def _chiedi(s: Sessione) -> str:
        """«quanto ti viene?» per un conto, «con l'unità di misura» per una misura, «che cosa
        rispondi?» per le parole e le scelte."""
        es = s.es
        if es is not None and es.tipo == "misura":
            return "quanto ti viene, con l'unità di misura?"
        if calcolata(s.materia) and (es is None or es.tipo != "scelta"):
            return "quanto ti viene?"
        return "che cosa rispondi?"

    def _riprova(self, s: Sessione) -> str:
        return "Riprova: " + self._chiedi(s)

    def _risultato(self, s: Sessione, frase: str, domanda: bool = True, **extra) -> dict:
        """Il risultato per il tool: frase pronta, sessione in sospeso, scheda aggiornata."""
        out = {"ok": True, "conferma": frase, "risposta_finale": frase, **extra}
        if domanda and s.aperta and s.es is not None and frase.rstrip().endswith("?"):
            out["in_sospeso"] = {"tool": "esercizi", "argomenti": {"azione": "rispondi"},
                                 "domanda": "?", "cosa": "l'esercizio",
                                 "messaggio": ESERCIZI_MSG.format(domanda=s.es.testo)}
        self._scheda(s)
        return out

    @staticmethod
    def _final(frase: str, ok: bool = True, **extra) -> dict:
        return {"ok": ok, **extra, "conferma": frase, "risposta_finale": frase}

    # ── azioni ──
    def inizia(self, prof, fascia: str | None, eta: int | None, materia: str = "",
               argomento: str = "", classe: str = "", mittente=None, modo: str = "",
               blocco: str = "") -> dict:
        # «logica» come argomento è la materia, non l'analisi logica (conversione di forma)
        if argomento and solo_materia(argomento) and not materia_da_testo(materia):
            materia, argomento = solo_materia(argomento), ""
        arg = argomento_da_testo(argomento, materia_da_testo(materia)) if argomento else None
        mat = materia_da_testo(materia) or (argomenti()[arg][0] if arg else None)
        if arg is None and argomento and not materia_da_testo(materia):
            arg = argomento_da_testo(argomento)
            mat = argomenti()[arg][0] if arg else mat
        cl = classe_da_testo(classe) or classe_da_eta(eta)
        if mat is None and arg is None:
            return self._final(f"Di che materia? Ho {elenco_materie()}.", ok=True,
                               in_sospeso={"tool": "esercizi", "argomenti": {"azione": "inizia"},
                                           "domanda": "?", "cosa": "gli esercizi",
                                           "messaggio": ARGOMENTO_MSG.format(
                                               materia=elenco_materie().replace(" e ", " o "),
                                               classe="")})
        if arg is None:
            adatti = [a for a, (m, _) in argomenti(mat).items() if cl is None or adatto(a, cl)]
            adatti = adatti or list(argomenti(mat))
            elenco = ", ".join(nome_argomento(a) for a in adatti)
            cl_txt = f", classe={cl.detta()}" if cl else ""
            frase = f"Va bene, {mat}. Su che cosa? Per esempio: {elenco}?"
            return self._final(frase, in_sospeso={
                "tool": "esercizi", "argomenti": {"azione": "inizia", "materia": mat},
                "domanda": "?", "cosa": "gli esercizi",
                "messaggio": ARGOMENTO_MSG.format(materia=mat, classe=cl_txt)})
        if cl is None:
            da, a = argomenti()[arg][1]["classi"]
            cl = Classe.da_indice((da.indice + a.indice) // 2)
        livello = livello_per(arg, cl)
        s = Sessione(prof.id, prof.name, getattr(prof, "gender", None), mat, arg, cl, livello,
                     fascia, mittente)
        try:
            pref = self.registro.preferenze(prof.id)
        except Exception:  # noqa: BLE001 — senza preferenze, i valori di sempre
            pref = {}
        if modo or blocco:
            pref, _ = self._nuove_preferenze(pref, modo, blocco, cl)
            self._salva_preferenze(prof.id, pref)
        s.applica(pref, self.cfg)
        with self._lock:
            vecchia = self.sessioni.get(prof.id)
            self.sessioni[prof.id] = s
        if vecchia is not None and vecchia.aperta and vecchia.es is not None:
            vecchia.aperta = False
        self.prepara(arg, livello)
        es = self._prossimo(s)
        if es is None:
            with self._lock:
                self.sessioni.pop(prof.id, None)
            return self._final("Adesso non riesco a controllare gli esercizi di "
                               f"{nome_argomento(arg)}: proviamo un'altra cosa, per esempio "
                               "matematica?", ok=False, fatto="NIENTE: nessun esercizio pronto")
        if not adatto(arg, cl):
            nota = f" Di solito si fanno più avanti, ma proviamo."
        else:
            nota = ""
        inizio = f"Facciamo {nome_argomento(arg)}, livello da {cl.detta()}.{nota}"
        if s.tappe_on:
            inizio += (f" È un percorso a {int(getattr(self.cfg, 'esercizi_tappe', 3) or 3)} "
                       f"tappe da {s.blocco} esercizi.")
        elif s.punti_on:
            inizio += " Giochiamo a punti: 2 al primo colpo, 1 dopo un aiuto o un errore."
        if fascia == "adolescenti" and not self._detto_oggi(prof.id):
            inizio += " Ti ricordo che i tuoi tutori vedono come vanno gli esercizi."
        s.esito = {"testo": "", "giusta": None}
        self.log(f"   [ESERCIZI] {prof.name}: {mat}, {arg}, {cl}, livello {livello}")
        return self._risultato(s, f"{inizio} Prima domanda: {self._domanda(s)}",
                               sessione=s.id, materia=mat, argomento=arg, classe=str(cl))

    def _detto_oggi(self, persona: str) -> bool:
        return bool(self.registro.tentativi(persona))

    def rispondi(self, prof, risposta: str, canale: str = "voce", detto: str = "",
                 ultima: str = "") -> dict:
        """`detto`: la frase della persona (il modello deve passare un numero che si ricava da
        lì); `ultima`: l'ultima cosa detta da Calliope (una domanda inventata dal modello non è
        quella che il codice controlla). Vuoti (la scheda, le prove) = nessun controllo."""
        s = self.sessione(prof.id)
        if s is not None and s.es is None and s.in_pausa:
            return self._ferma(s)
        if s is None or s.es is None:
            return self._final("Non abbiamo esercizi aperti: vuoi cominciare? Dimmi la materia.",
                               ok=False, fatto="NIENTE: nessun esercizio aperto")
        s.ultimo = time.monotonic()
        s.in_pausa = False
        es = s.es
        if (canale == "voce" and ultima and domanda_inventata(ultima)
                and _norm(es.voce) not in _norm(ultima)):
            # La domanda l'ha fatta il modello, non il codice (DGX del 12/10: «45 più 38?»
            # inventata, la risposta giusta 83 segnata sbagliata contro 55 più 49): non si
            # giudica, si torna alla domanda vera. Non conta come tentativo
            s.esito = {"testo": "", "giusta": None}
            return self._risultato(s, "Quella domanda non l'ho preparata io, quindi non posso "
                                      "correggerla. La domanda dell'esercizio è questa: "
                                      + self._domanda(s), regola="esercizi_domanda_non_sua")
        if canale == "voce" and detto and es.tipo in ("valore", "frazione_ridotta", "misura"):
            from .numeri import leggi_valore, valore_detto
            v = leggi_valore(risposta)
            if v is not None and not valore_detto(v, detto):
                # Il numero non si ricava da ciò che ha detto (DGX del 12/10: «Suttanto
                # salida» passato come 76): il codice non giudica, chiede
                s.esito = {"testo": "", "giusta": None}
                return self._risultato(s, "Non ho capito il numero: me lo ripeti?",
                                       regola="esercizi_numero_non_detto")
        e: Esito = controlla(es, risposta)
        if e.giusta is None:
            s.esito = {"testo": e.nota, "giusta": None}
            return self._risultato(s, e.nota + " " + self._riprova(s))
        if e.giusta:
            return self._giusta(s, prof, e, risposta, canale)
        return self._sbagliata(s, prof, e, risposta, canale)

    def _giusta(self, s: Sessione, prof, e: Esito, risposta: str, canale: str) -> dict:
        es = s.es
        secondi = time.monotonic() - s.inizio_es
        self.registro.tentativo(s.persona, s.id, es, str(s.classe), "giusta", e.letta or risposta,
                                s.aiuti, secondi, canale)
        s.fatti += 1
        s.giuste += 1
        primo = s.errori == 0 and s.aiuti == 0
        s.fila_giuste = s.fila_giuste + 1 if primo else 0
        s.fila_difficili = 0 if s.errori < 2 else s.fila_difficili + 1
        bravo = self.rng.choice((BRAVO_GIOCO if s.giocoso else BRAVO)
                                ["f" if s.gender == "f" else "m"])
        frase = (e.nota if e.nota.startswith("Giusto") else bravo + (" " + e.nota if e.nota else ""))
        if s.punti_on:
            p = 2 if primo else 1
            s.punti += p
            frase += f" Più {p} punt{'i' if p > 1 else 'o'}: sei a {s.punti}."
        s.esito = {"testo": frase, "giusta": True}
        cambio = self._adatta(s)
        if cambio > 0:
            frase += " Proviamo un po' più difficile."
        elif cambio < 0:
            frase += " Facciamone uno un po' più facile."
        return self._dopo(s, frase, giusta=True)

    def _sbagliata(self, s: Sessione, prof, e: Esito, risposta: str, canale: str) -> dict:
        es = s.es
        if e.conta:
            s.errori += 1
        self.registro.tentativo(s.persona, s.id, es, str(s.classe), "sbagliata",
                                e.letta or risposta, s.aiuti, None, canale)
        if s.errori < self.massimo:
            frase = "Non ancora." if e.conta else "Quasi."
            if e.nota:
                frase += " " + e.nota
            # Mai «Un indizio:» senza l'indizio (DGX del 12/10, 16:17: la frase finiva lì)
            sugg = _indizi(es)
            if s.aiuti < len(sugg) and e.conta:
                frase += " Un indizio: " + sugg[s.aiuti]
                s.aiuti += 1
            s.esito = {"testo": frase, "giusta": False}
            return self._risultato(s, f"{frase} {self._riprova(s)}", giusta=False,
                                   tentativi=s.errori, massimo=self.massimo)
        return self._spiega(s, prof)

    def _spiega(self, s: Sessione, prof) -> dict:
        """Dopo i tentativi: la soluzione spiegata, e i tutori lo sanno (una volta per
        sessione), come nei compiti guidati."""
        es = s.es
        secondi = time.monotonic() - s.inizio_es
        self.registro.tentativo(s.persona, s.id, es, str(s.classe), "spiegato", "", s.aiuti,
                                secondi, "voce")
        s.fatti += 1
        s.spiegati += 1
        s.fila_giuste = 0
        s.fila_difficili += 1
        frase = (f"Hai provato {self.massimo} volte e ti sei impegnat{_o(prof)}: ti spiego. "
                 f"{es.spiegazione}")
        if not s.avvisato:
            s.avvisato = True
            chi = self._avvisa(prof, s, "spiegazione")
            if chi:
                frase += f" Lo dico anche {chi}, così ripassate insieme."
        s.esito = {"testo": "La soluzione: " + es.spiegazione, "giusta": False}
        self._adatta(s)
        return self._dopo(s, frase, soluzione_spiegata=True)

    def _adatta(self, s: Sessione) -> int:
        if s.fila_giuste >= 3 and s.livello < 3:
            s.livello += 1
            s.fila_giuste = 0
            self.prepara(s.argomento, s.livello)
            return 1
        if s.fila_difficili >= 2 and s.livello > 1:
            s.livello -= 1
            s.fila_difficili = 0
            return -1
        return 0

    def aiuto(self, prof) -> dict:
        s = self.sessione(prof.id)
        if s is not None and s.es is None and s.in_pausa:
            return self._ferma(s)
        if s is None or s.es is None:
            return self._final("Non abbiamo esercizi aperti.", ok=False, fatto="NIENTE")
        s.ultimo = time.monotonic()
        es = s.es
        self.registro.tentativo(s.persona, s.id, es, str(s.classe), "aiuto", "", s.aiuti + 1,
                                None, "voce")
        sugg = _indizi(es)
        if s.aiuti < len(sugg):
            frase = "Un indizio: " + sugg[s.aiuti]
            s.aiuti += 1
        else:
            frase = "Gli indizi sono finiti: prova a rispondere, oppure dimmi «salta»."
        s.esito = {"testo": frase, "giusta": None}
        return self._risultato(s, f"{frase} {self._chiedi(s)[0].upper()}{self._chiedi(s)[1:]}")

    def salta(self, prof, canale: str = "voce") -> dict:
        s = self.sessione(prof.id)
        if s is not None and s.es is None and s.in_pausa:
            return self._ferma(s)
        if s is None or s.es is None:
            return self._final("Non abbiamo esercizi aperti.", ok=False, fatto="NIENTE")
        s.ultimo = time.monotonic()
        self.registro.tentativo(s.persona, s.id, s.es, str(s.classe), "saltato", "", s.aiuti,
                                time.monotonic() - s.inizio_es, canale)
        s.fila_giuste = 0
        s.esito = {"testo": "Saltato.", "giusta": None}
        return self._dopo(s, "Va bene, saltiamo questo.")

    def ripeti(self, prof) -> dict:
        s = self.sessione(prof.id)
        if s is not None and s.es is None and s.in_pausa:
            return self._ferma(s)
        if s is None or s.es is None:
            return self._final("Non abbiamo esercizi aperti.", ok=False, fatto="NIENTE")
        s.ultimo = time.monotonic()
        return self._risultato(s, self._domanda(s))

    def soluzione(self, prof, libero: bool) -> dict:
        """La soluzione chiesta: solo con i compiti «liberi» (adolescenti, se il tutore vuole) o
        per un adulto che prova gli esercizi; per gli altri la regola dei tentativi."""
        s = self.sessione(prof.id)
        if s is None or s.es is None:
            return self._final("Non abbiamo esercizi aperti.", ok=False, fatto="NIENTE")
        if not libero:
            rest = self.massimo - s.errori
            frase = (f"La soluzione te la spiego dopo {self.massimo} tentativi: te ne mancano "
                     f"{rest}. Vuoi un indizio?")
            return self._risultato(s, frase, regola="esercizi_soluzione_negata")
        es = s.es
        self.registro.tentativo(s.persona, s.id, es, str(s.classe), "spiegato", "", s.aiuti,
                                time.monotonic() - s.inizio_es, "voce")
        s.fatti += 1
        s.esito = {"testo": "La soluzione: " + es.spiegazione, "giusta": None}
        return self._dopo(s, es.spiegazione)

    # ── pausa, ripresa e preferenze (12/10) ──
    def pausa(self, prof) -> dict:
        """«Facciamo una pausa»: la sessione resta (fino a SCADENZA_S), l'esercizio in corso
        anche; «continuiamo» riprende da lì."""
        s = self.sessione(prof.id)
        if s is None:
            return self._final("Non stavamo facendo esercizi.", ok=False, fatto="NIENTE")
        s.ultimo = time.monotonic()
        s.in_pausa = True
        conto = f" Finora {conto_detto(s.fatti, s.giuste)}." if s.fatti else ""
        if s.punti_on and s.fatti:
            conto += f" Hai {s.punti} punt{'o' if s.punti == 1 else 'i'}."
        frase = f"Va bene, facciamo una pausa.{conto} Quando vuoi riprendere, dimmi «continuiamo»."
        s.esito = {"testo": "In pausa.", "giusta": None}
        self._scheda(s)
        return self._final(frase, regola="esercizi_pausa")

    def continua(self, prof) -> dict:
        s = self.sessione(prof.id)
        if s is None:
            return self._final("Non abbiamo esercizi da riprendere: vuoi cominciare? Dimmi la "
                               "materia.", ok=False, fatto="NIENTE: nessun esercizio aperto")
        s.ultimo = time.monotonic()
        s.in_pausa = False
        if s.es is None and self._prossimo(s) is None:
            return self._chiudi(s, "Per ora gli esercizi sono finiti.")
        s.esito = {"testo": "", "giusta": None}
        return self._risultato(s, f"Riprendiamo. {self._domanda(s)}", regola="esercizi_ripresa")

    def _nuove_preferenze(self, pref: dict, modo: str, blocco: str,
                          classe: Classe | None) -> tuple[dict, list[str]]:
        """(preferenze nuove, parti dette). `modo`: giocoso, normale, punti, tappe;
        `blocco`: un numero («3»), «più corti», «più lunghi»."""
        pref = dict(pref or {})
        parti = []
        m = _norm(modo)
        if "normal" in m or "seri" in m:
            pref.update(giocoso=False, punti=False, tappe=False)
            parti.append("come al solito, senza giochi")
        if "gioc" in m:
            pref.update(giocoso=True, punti=True)
            parti.append("più giocosi, con i punti")
        if "punt" in m and "gioc" not in m:
            pref["punti"] = True
            parti.append("a punti")
        if "tapp" in m or "percors" in m:
            pref["tappe"] = True
            parti.append("a tappe")
        b = _norm(blocco)
        attuale = pref.get("blocco") if isinstance(pref.get("blocco"), int) else blocco_per(
            classe, self.cfg)
        from .numeri import leggi_valore
        v = leggi_valore(b) if b else None
        nuovo = None
        if v is not None and v.denominator == 1 and v > 0:
            nuovo = int(v)
        elif "cort" in b or "men" in b or "poch" in b:
            nuovo = max(2, attuale // 2)
        elif "lung" in b or "di pi" in b or "tant" in b:
            nuovo = attuale + 5
        if nuovo is not None:
            nuovo = max(2, min(20, nuovo))
            pref["blocco"] = nuovo
            parti.append(f"blocchi da {nuovo} esercizi")
        return pref, parti

    def _salva_preferenze(self, persona: str, pref: dict):
        try:
            self.registro.salva_preferenze(persona, pref)
        except Exception as e:  # noqa: BLE001 — la preferenza vale comunque per la sessione
            self.log(f"   [ESERCIZI] preferenze non salvate: {type(e).__name__}")

    def preferenze(self, prof, modo: str = "", blocco: str = "") -> dict:
        """«Rendili più giocosi», «facciamolo a punti», «a tappe», «blocchi più corti»: la
        preferenza resta salvata per la persona (anche nelle conversazioni nuove) e vale subito
        nella sessione aperta. La frase la dice il codice: mai «segno tutto» senza salvare."""
        s = self.sessione(prof.id)
        try:
            prima = self.registro.preferenze(prof.id)
        except Exception:  # noqa: BLE001
            prima = {}
        pref, parti = self._nuove_preferenze(prima, modo, blocco,
                                             s.classe if s is not None else None)
        if not parti:
            return {"ok": False, "fatto": "NIENTE: nessuna preferenza cambiata",
                    "errore": "manca come li vuole",
                    "cosa_fare": "chiedi come vuole gli esercizi: più giocosi, a punti, a tappe, "
                                 "blocchi più corti o più lunghi; poi richiama con modo o blocco"}
        self._salva_preferenze(prof.id, pref)
        frase = ("Va bene: d'ora in poi " + ", ".join(parti)
                 + ". Me lo ricordo anche le prossime volte.")
        if s is None:
            return self._final(frase, regola="esercizi_preferenze")
        s.ultimo = time.monotonic()
        s.applica(pref, self.cfg)
        s.nel_blocco = min(s.nel_blocco, max(0, s.blocco - 1))
        if s.es is not None and not s.in_pausa:
            return self._risultato(s, f"{frase} Torniamo a noi: {self._domanda(s)}",
                                   regola="esercizi_preferenze")
        self._scheda(s)
        return self._final(frase + " Quando vuoi, dimmi «continuiamo».",
                           regola="esercizi_preferenze")

    def fine(self, prof) -> dict:
        s = self.sessione(prof.id)
        if s is None:
            return self._final("Non stavamo facendo esercizi.", ok=False, fatto="NIENTE")
        return self._chiudi(s, "")

    def _chiudi(self, s: Sessione, prima: str) -> dict:
        s.aperta = False
        with self._lock:
            if self.sessioni.get(s.persona) is s:
                self.sessioni.pop(s.persona, None)
        if s.fatti:
            conto = (f"Abbiamo finito: {conto_detto(s.fatti, s.giuste)}."
                     + (" Ottimo lavoro!" if s.giuste >= 0.8 * s.fatti else
                        " Bel lavoro, la prossima volta andrà ancora meglio."))
        else:
            conto = "Va bene, smettiamo qui."
        s.esito = {"testo": conto, "giusta": None}
        self._scheda(s)
        frase = (prima + " " + conto).strip()
        return self._final(frase, fatti=s.fatti, giuste=s.giuste)

    def segnala(self, prof, nota: str = "", risposta: str = "") -> dict:
        """«Secondo me è sbagliato»: il codice ricontrolla (un altro conto, o di nuovo
        Wikizionario e secondo modello), registra la segnalazione e avvisa i tutori. Se il
        ricontrollo non torna, l'esercizio si toglie dal banco."""
        s = self.sessione(prof.id)
        if s is None or s.es is None:
            return self._final("Non abbiamo esercizi aperti da controllare.", ok=False,
                               fatto="NIENTE")
        s.ultimo = time.monotonic()
        es = s.es
        if calcolata(es.materia):
            ok = bool(MATERIE[es.materia].verifica(es))
            ricontrollo = {"tipo": "ricalcolo", "torna": ok}
        else:
            from .verifica import verifica_italiano
            # Di nuovo, senza il banco: il ragazzo può aver visto giusto
            v = verifica_italiano(es, self.wikizionario, self.parere)
            ok = v["esito"] != "scartato"
            ricontrollo = v
        esito = "confermato" if ok else "scartato"
        self.registro.segnala(s.persona, es, risposta, nota, ricontrollo, esito)
        chi = self._avvisa(prof, s, "segnalazione")
        a_chi = chi or "a chi ti segue"
        if not ok:
            try:
                self.registro.banco_scrivi(es, "scartato", dict(ricontrollo, segnalato=True))
            except Exception:  # noqa: BLE001
                pass
            self.registro.tentativo(s.persona, s.id, es, str(s.classe), "scartato", "", s.aiuti,
                                    None, "voce")
            frase = (f"Hai fatto bene a dirmelo: ricontrollandolo non mi torna, quindi lo tolgo. "
                     f"Lo dico anche {a_chi}.")
            s.esito = {"testo": "Esercizio tolto: grazie della segnalazione.", "giusta": None}
            if self._prossimo(s) is None:
                return self._chiudi(s, frase)
            return self._risultato(s, f"{frase} Prossima: {self._domanda(s)}",
                                   regola="esercizi_segnalato_tolto")
        frase = (f"L'ho ricontrollato{' con un altro conto' if calcolata(es.materia) else ''}"
                 f" e mi torna, ma l'ho segnato e lo dico {a_chi}.")
        s.esito = {"testo": "Segnalato: lo guarderà un adulto.", "giusta": None}
        return self._risultato(s, f"{frase} {self._riprova(s)}",
                               regola="esercizi_segnalato_confermato")

    def _avvisa(self, prof, s: Sessione, perche: str) -> str:
        """L'avviso ai tutori (minori.Avvisi): l'argomento, mai le risposte. Restituisce «a
        Dario e ad Elena» per la frase, o "" se non ci sono tutori (un adulto che prova)."""
        from .. import minori as M
        if not M.e_minore(prof):
            return ""
        av = M.avvisi()
        reg = getattr(av, "registry", None) if av is not None else None
        nomi = [u.name for u in M.tutori(prof, reg) if getattr(u, "name", None)]
        if av is None:
            return ""
        arg = nome_argomento(s.argomento)
        testo = (f"{prof.name} ha provato {self.massimo} volte un esercizio di {arg} senza "
                 f"riuscirci: gliel'ho spiegato. Il riepilogo degli esercizi te lo dico se me lo "
                 f"chiedi." if perche == "spiegazione" else
                 f"{prof.name} ha segnalato un esercizio di {arg} come sbagliato: lo trovi nel "
                 f"riepilogo degli esercizi.")
        try:
            av.manda(prof, "esercizi", testo, non_ripetere_s=3600.0)
        except Exception as e:  # noqa: BLE001 — l'avviso non deve fermare l'esercizio
            self.log(f"   [ESERCIZI] avviso non mandato: {type(e).__name__}")
        return " e ".join(("ad " if n[:1].lower() in "aeiou" else "a ") + n for n in nomi[:2])

    def riepilogo(self, minore, giorni: int = 1, mittente=None) -> dict:
        import datetime
        al = datetime.date.today()
        dal = al - datetime.timedelta(days=max(1, int(giorni)) - 1)
        r = self.registro.riepilogo(minore.id, minore.name, dal, al,
                                    int(getattr(self.cfg, "esercizi_campione", 3) or 3))
        if mittente is not None and self.schermi is not None and (r["righe"] or r["segnalazioni"]):
            try:
                from ..schermi import schede
                card = schede.nuova("esercizi_riepilogo", f"Esercizi di {minore.name}",
                                    schede.PERSONALE, durata_s=None,
                                    chiave=f"esercizi_riepilogo:{minore.id}",
                                    frase=r["frase"], righe=r["righe"][-60:],
                                    campione=r["campione"],
                                    segnalazioni=[{"domanda": x["domanda"], "attesa": x["attesa"],
                                                   "data": x["data"], "nota": x["nota"],
                                                   "esito": x["esito"]}
                                                  for x in r["segnalazioni"][-10:]])
                self.schermi.invia(card, mittente)
                r["frase"] += " Il dettaglio è sul tuo schermo."
            except Exception as e:  # noqa: BLE001
                self.log(f"   [ESERCIZI] scheda del riepilogo non mandata: {type(e).__name__}")
        return r

    def elenco_argomenti(self, classe: Classe | None, materia: str | None) -> str:
        parti = []
        for m in MATERIE:
            if materia and m != materia:
                continue
            a = [nome_argomento(x) for x in argomenti(m) if classe is None or adatto(x, classe)]
            if a:
                parti.append(f"{m}: {', '.join(a)}")
        return "; ".join(parti)

    # ── scheda ──
    def _scheda(self, s: Sessione):
        if self.schermi is None or s.mittente is None:
            return
        try:
            from ..schermi import schede
            card = self.scheda(s)
            schede_ok = card is not None
            if schede_ok:
                self.schermi.invia(card, s.mittente)
        except Exception as e:  # noqa: BLE001 — lo schermo non deve fermare l'esercizio
            self.log(f"   [ESERCIZI] scheda non mandata: {type(e).__name__}")

    def scheda(self, s: Sessione) -> dict | None:
        from ..schermi import schede
        es = s.es
        dati = {"materia": s.materia, "argomento": nome_argomento(s.argomento),
                "classe": s.classe.detta(), "livello": s.livello, "numero": s.fatti + 1,
                "fatti": s.fatti, "giuste": s.giuste,
                "stato": ("finita" if not s.aperta else "pausa" if s.in_pausa else "aperta"),
                "esito": dict(s.esito), "tentativi": s.errori, "massimo": self.massimo}
        if s.punti_on:
            dati["punti"] = s.punti
        if s.tappe_on:
            dati["tappa"] = s.tappa
        if es is not None and s.aperta:
            pub = es.pubblico()
            dati.update(domanda=pub["testo"], tipo_risposta=pub["tipo"], scelte=pub["scelte"],
                        esercizio=pub["id"],
                        campo=("misura" if es.tipo == "misura" else
                               "numero" if calcolata(s.materia) else "testo"))
        return schede.nuova("esercizio", f"Esercizi: {nome_argomento(s.argomento)}",
                            schede.PERSONALE, durata_s=None, chiave=f"esercizi:{s.persona}",
                            **dati)

    def _profilo(self, pid):
        users = getattr(self.registry, "users", None) or {}
        return next((u for u in users.values() if getattr(u, "id", None) == pid), None)

    def da_scheda(self, schermo: dict, dati: dict) -> dict:
        """Un'azione dalla scheda dello schermo personale (`POST /api/esercizio`): il server
        ha già controllato sessione e HTTPS; qui lo schermo deve essere personale e il suo
        proprietario deve avere una sessione aperta (cominciata a voce). Fuori orario no.
        {ok, scheda, frase} o {errore, _stato}."""
        if not isinstance(dati, dict):
            return {"errore": "dati non validi", "_stato": 400}
        prof = self._profilo(schermo.get("proprietario")) if schermo.get("proprietario") else None
        if prof is None:
            return {"errore": "Gli esercizi si fanno da uno schermo personale.", "_stato": 403}
        from .. import minori as M
        orario = M.fuori_orario(prof)
        if orario:
            return {"errore": M.frase_fuori_orario(prof, orario), "_stato": 403}
        azione = str(dati.get("azione") or "")
        s = self.sessione(prof.id)
        if s is None:
            return {"errore": "Gli esercizi sono finiti: per ricominciare chiedilo a voce.",
                    "_stato": 409}
        if azione in ("continua", "fine") and s.es is None and s.in_pausa:
            out = self.continua(prof) if azione == "continua" else self.fine(prof)
            s2 = self.sessione(prof.id) or s
            return {"ok": True, "frase": out.get("risposta_finale", ""), "scheda": self.scheda(s2)}
        if s.es is None or str(dati.get("esercizio") or "") != s.es.firma:
            return {"errore": "Questo esercizio non c'è più: guarda quello nuovo.",
                    "_stato": 409, "scheda": self.scheda(s)}
        risposta = str(dati.get("risposta") or "")[:80]
        if azione == "rispondi":
            if not risposta.strip():
                return {"errore": "Scrivi la risposta.", "_stato": 422}
            out = self.rispondi(prof, risposta, canale="scheda")
        elif azione == "aiuto":
            out = self.aiuto(prof)
        elif azione == "salta":
            out = self.salta(prof, canale="scheda")
        elif azione == "segnala":
            out = self.segnala(prof, str(dati.get("nota") or "")[:200], risposta)
        elif azione == "fine":
            out = self.fine(prof)
        else:
            return {"errore": "azione sconosciuta", "_stato": 400}
        s2 = self.sessione(prof.id) or s
        return {"ok": True, "frase": out.get("risposta_finale", ""), "scheda": self.scheda(s2)}

    def stato(self, persona: str) -> dict | None:
        """Per il dato del turno (minori.dato_turno): materia, argomento e domanda in corso."""
        s = self.sessione(persona)
        if s is None or (s.es is None and not s.in_pausa):
            return None
        return {"materia": s.materia, "argomento": nome_argomento(s.argomento),
                "domanda": s.es.testo if s.es is not None else "", "errori": s.errori,
                "massimo": self.massimo, "pausa": s.in_pausa}

    def close(self):
        self.registro.close()


# ─────────────────────────── servizio del processo ───────────────────────────

_SERVIZIO: dict = {"servizio": None}


def prepara(cfg, schermi=None, biblioteca=None, registry=None, log=print) -> Servizio | None:
    """Da main.py all'avvio: il servizio sul file della memoria."""
    if not getattr(cfg, "esercizi_enabled", True):
        _SERVIZIO["servizio"] = None
        return None
    reg = Registro(getattr(cfg, "memory_db", "memoria.db"))
    _SERVIZIO["servizio"] = Servizio(cfg, reg, schermi=schermi, biblioteca=biblioteca, log=log,
                                     registry=registry)
    return _SERVIZIO["servizio"]


def servizio() -> Servizio | None:
    return _SERVIZIO.get("servizio")


def imposta(s: Servizio | None):
    _SERVIZIO["servizio"] = s


def json_sicuro(o) -> str:
    return json.dumps(o, ensure_ascii=False, default=str)
