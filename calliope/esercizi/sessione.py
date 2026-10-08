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
import secrets
import threading
import time

from . import (MATERIE, Classe, adatto, argomenti, argomento_da_testo, classe_da_eta,
               classe_da_testo, controlla, genera, livello_per, materia_da_testo,
               nome_argomento)
from .modello import Esercizio, Esito
from .registro import Registro

SCADENZA_S = 30 * 60              # una sessione ferma da più di così è finita
PRONTI = 3                        # esercizi d'italiano controllati in anticipo per livello

# L'esercizio in corso come azione in sospeso (come i compiti, tools/minori.COMPITI_MSG): il
# testo arriva subito prima della frase del ragazzo, dove il modello lo legge di sicuro
ESERCIZI_MSG = ("Esercizi in corso, messaggio di sistema: hai appena chiesto «{domanda}». Se in "
                "questa frase dà una risposta, chiama subito esercizi con azione=rispondi e "
                "risposta come l'ha detta, senza dire tu se è giusta. Se chiede un indizio: "
                "azione=aiuto; se vuole saltare: salta; se dice che l'esercizio è sbagliato: "
                "segnala; se vuole ripetere la domanda: ripeti; se vuole smettere: fine. Anche "
                "una parola o un numero da soli («Sei.», «Tre quarti.», «Verbo.») sono una "
                "risposta. Se parla d'altro, rispondi normalmente.")
# La spinta di Brain quando, con l'esercizio in sospeso, il modello risponde senza il tool
# (rete `spinta_esercizi`): la risposta trattenuta non si dice
ESERCIZI_NUDGE = ("Esercizi in corso: non hai chiamato esercizi. Se la frase del ragazzo è una "
                  "risposta all'esercizio, chiama adesso esercizi con azione=rispondi e la "
                  "risposta come l'ha detta: la corregge il programma, non tu. Per un indizio "
                  "azione=aiuto, per saltare salta, se dice che è sbagliato segnala, per smettere "
                  "fine. Solo se parla d'altro rispondi normalmente, senza dire se l'esercizio è "
                  "giusto.")
ARGOMENTO_MSG = ("Esercizi, messaggio di sistema: hai chiesto quale argomento di {materia}. Se "
                 "risponde con un argomento, chiama esercizi con azione=inizia, "
                 "materia={materia} e argomento come l'ha detto{classe}.")

BRAVO = {"f": ("Giusto!", "Esatto!", "Brava!", "Perfetto!"),
         "m": ("Giusto!", "Esatto!", "Bravo!", "Perfetto!")}


def conto_detto(fatti: int, giuste: int) -> str:
    """«1 esercizio, 1 giusto», «10 esercizi, 8 giusti», «3 esercizi, nessuno giusto»."""
    es = "1 esercizio" if fatti == 1 else f"{fatti} esercizi"
    g = "nessuno giusto" if giuste == 0 else "1 giusto" if giuste == 1 else f"{giuste} giusti"
    return f"{es}, {g}"


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
        if s.materia == "italiano":
            es = self._prossimo_italiano(s.argomento, s.livello, escludi)
        else:
            es = None
            for _ in range(30):
                cand = mod.genera(s.argomento, s.livello, self._nuovo_seme())
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
        return s.es.voce if s.es else ""

    def _riprova(self, s: Sessione) -> str:
        return ("Riprova: quanto ti viene?" if s.materia == "matematica" else
                "Riprova: che cosa rispondi?")

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
               argomento: str = "", classe: str = "", mittente=None) -> dict:
        arg = argomento_da_testo(argomento, materia_da_testo(materia)) if argomento else None
        mat = materia_da_testo(materia) or (argomenti()[arg][0] if arg else None)
        if arg is None and argomento:
            arg = argomento_da_testo(argomento)
            mat = argomenti()[arg][0] if arg else mat
        cl = classe_da_testo(classe) or classe_da_eta(eta)
        if mat is None and arg is None:
            return self._final("Di che materia? Per ora ho matematica e italiano.", ok=True,
                               in_sospeso={"tool": "esercizi", "argomenti": {"azione": "inizia"},
                                           "domanda": "?", "cosa": "gli esercizi",
                                           "messaggio": ARGOMENTO_MSG.format(
                                               materia="matematica o italiano",
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
        if fascia == "adolescenti" and not self._detto_oggi(prof.id):
            inizio += " Ti ricordo che i tuoi tutori vedono come vanno gli esercizi."
        s.esito = {"testo": "", "giusta": None}
        self.log(f"   [ESERCIZI] {prof.name}: {mat}, {arg}, {cl}, livello {livello}")
        return self._risultato(s, f"{inizio} Prima domanda: {self._domanda(s)}",
                               sessione=s.id, materia=mat, argomento=arg, classe=str(cl))

    def _detto_oggi(self, persona: str) -> bool:
        return bool(self.registro.tentativi(persona))

    def rispondi(self, prof, risposta: str, canale: str = "voce") -> dict:
        s = self.sessione(prof.id)
        if s is None or s.es is None:
            return self._final("Non abbiamo esercizi aperti: vuoi cominciare? Dimmi la materia.",
                               ok=False, fatto="NIENTE: nessun esercizio aperto")
        s.ultimo = time.monotonic()
        es = s.es
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
        bravo = self.rng.choice(BRAVO["f" if s.gender == "f" else "m"])
        frase = (e.nota if e.nota.startswith("Giusto") else bravo + (" " + e.nota if e.nota else ""))
        s.esito = {"testo": frase, "giusta": True}
        cambio = self._adatta(s)
        if s.fatti % 10 == 0:
            frase += f" Siamo a {conto_detto(s.fatti, s.giuste)}."
        if cambio > 0:
            frase += " Proviamo un po' più difficile."
        elif cambio < 0:
            frase += " Facciamone uno un po' più facile."
        if self._prossimo(s) is None:
            return self._chiudi(s, frase + " Per ora gli esercizi sono finiti.")
        return self._risultato(s, f"{frase} Prossima: {self._domanda(s)}", giusta=True)

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
            if s.aiuti < len(es.suggerimenti) and e.conta:
                frase += " Un indizio: " + es.suggerimenti[s.aiuti]
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
        if self._prossimo(s) is None:
            return self._chiudi(s, frase)
        return self._risultato(s, f"{frase} Prossima: {self._domanda(s)}",
                               soluzione_spiegata=True)

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
        if s is None or s.es is None:
            return self._final("Non abbiamo esercizi aperti.", ok=False, fatto="NIENTE")
        s.ultimo = time.monotonic()
        es = s.es
        self.registro.tentativo(s.persona, s.id, es, str(s.classe), "aiuto", "", s.aiuti + 1,
                                None, "voce")
        if s.aiuti < len(es.suggerimenti):
            frase = "Un indizio: " + es.suggerimenti[s.aiuti]
            s.aiuti += 1
        else:
            frase = "Gli indizi sono finiti: prova a rispondere, oppure dimmi «salta»."
        s.esito = {"testo": frase, "giusta": None}
        return self._risultato(s, f"{frase} {'Che cosa ti viene?' if s.materia == 'matematica' else 'Che cosa rispondi?'}")

    def salta(self, prof, canale: str = "voce") -> dict:
        s = self.sessione(prof.id)
        if s is None or s.es is None:
            return self._final("Non abbiamo esercizi aperti.", ok=False, fatto="NIENTE")
        s.ultimo = time.monotonic()
        self.registro.tentativo(s.persona, s.id, s.es, str(s.classe), "saltato", "", s.aiuti,
                                time.monotonic() - s.inizio_es, canale)
        s.fila_giuste = 0
        s.esito = {"testo": "Saltato.", "giusta": None}
        if self._prossimo(s) is None:
            return self._chiudi(s, "Va bene.")
        return self._risultato(s, f"Va bene, saltiamo questo. Prossima: {self._domanda(s)}")

    def ripeti(self, prof) -> dict:
        s = self.sessione(prof.id)
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
        if self._prossimo(s) is None:
            return self._chiudi(s, es.spiegazione)
        return self._risultato(s, f"{es.spiegazione} Prossima: {self._domanda(s)}")

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
        if es.materia == "matematica":
            from .matematica import verifica as ricalcola
            ok = ricalcola(es)
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
        frase = (f"L'ho ricontrollato{' con un altro conto' if es.materia == 'matematica' else ''}"
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
                "fatti": s.fatti, "giuste": s.giuste, "stato": "aperta" if s.aperta else "finita",
                "esito": dict(s.esito), "tentativi": s.errori, "massimo": self.massimo}
        if es is not None and s.aperta:
            pub = es.pubblico()
            dati.update(domanda=pub["testo"], tipo_risposta=pub["tipo"], scelte=pub["scelte"],
                        esercizio=pub["id"],
                        campo="numero" if s.materia == "matematica" else "testo")
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
        if s is None or s.es is None:
            return None
        return {"materia": s.materia, "argomento": nome_argomento(s.argomento),
                "domanda": s.es.testo, "errori": s.errori, "massimo": self.massimo}

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
