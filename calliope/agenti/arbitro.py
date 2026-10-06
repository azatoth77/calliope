"""
L'arbitro: la voce prima di tutto (02/10/2026).

Ollama e llama-server non hanno priorità tra le richieste: un lavoro dell'agente sullo
stesso Ollama della voce la farebbe aspettare fino alla fine della generazione (32 s
misurati nella ricerca del 02/10, §4.5). L'arbitro sta fuori da Ollama, tra la voce e
l'agente:

- la voce segnala quando qualcuno comincia a parlarle (`voce_occupata`: inizio del parlato
  rivolto a Calliope, dal VAD, e inizio di ogni risposta) e quando ha finito
  (`voce_libera`); **non aspetta mai niente**: le due chiamate mettono un flag e, se serve,
  chiudono lo stream dell'agente in un thread a parte;
- l'agente, tra un passo e l'altro, chiama `attendi()` (ferma finché la voce è occupata e
  per `ripresa_s` dopo), e durante lo stream `deve_cedere()`: se la voce si è svegliata lo
  stream si chiude (la generazione si ferma davvero) e il passo si rifà dopo.

Con l'agente su un'altra macchina (la DGX via tunnel) non c'è contesa per la GPU:
`condiviso=False` e l'arbitro non ferma niente, ma la voce chiama gli stessi metodi (non
costano nulla). Il prefill di un prompt nuovo non si interrompe: per questo i passi
dell'agente mandano pochi token nuovi alla volta (risultati dei tool tagliati).

**Stessa GPU, server diverso** (04/10): sulla DGX la voce è su Ollama e l'agente su vLLM, sulla
stessa GPU; con 3–4 generazioni di vLLM in corso la prima frase della voce passava da 0,72 s a
~2 s di mediana (p90 4 s). Quando condividere lo decide `impostazioni.stessa_gpu`
(`agenti_arbitro`: auto, sempre, mai). Con vLLM chiudere lo stream annulla la richiesta
(`with_cancellation` di vLLM 0.29: la disconnessione del client fa `abort`); si perde il
passo in corso, e con `--enable-prefix-caching` rifarlo non rilegge il prompt.

**Pausa del server invece della chiusura** (04/10, `PausaServer`): con la modalità sviluppo di
vLLM (`VLLM_SERVER_DEV_MODE=1`: `setup/linux/motore/vllm.sh agente`, `PAUSA=1`) quando si parla
l'arbitro chiede `POST /pause?mode=keep` (le generazioni si congelano con la loro cache, le
richieste nuove aspettano) e, finita la ripresa, `POST /resume`: niente passo perso. Sulla DGX
la pausa risponde in ~22 ms e la ripresa in ~2 ms; le chiamate le fa un thread suo, la voce
non aspetta mai. Casi:
- endpoint assente (404: vLLM senza modalità sviluppo, llama.cpp): si chiudono gli stream come
  prima, e la pausa si riprova dopo `RICONTROLLO_S`;
- pausa che non risponde entro `timeout_s` o dà errore: in quel turno si chiudono gli stream
  (ripiego) e la ripresa si manda comunque (la pausa potrebbe essere arrivata);
- ripresa garantita: a fine ripresa (`ripresa_s` dopo `voce_libera`), dopo `tenuta_max_s` se
  la voce non dice mai «libera», all'avvio (un vLLM lasciato in pausa da un Calliope morto a
  metà), a `chiudi()` e su SIGTERM (`proteggi_uscita`: `calliope ferma`); una ripresa fallita
  si riprova ogni mezzo secondo (un server giù non è in pausa: basta che non risponda);
- lo scrittore dell'ufficio che la voce sta aspettando (`ClienteCedevole(dalla_voce=True)`) non
  si può congelare in quel turno: `vieta_pausa` riprende subito il server e per il resto del
  turno gli altri stream di quel server si chiudono come prima; dal turno dopo si congela
  anche lui;
- la pausa copre solo gli stream di quel server (`registra_stream(stop, url)`): un archivio
  su un altro server si chiude come prima.
La pausa ferma TUTTE le richieste di quel vLLM: si usa solo per il server dell'agente, mai per
quello della voce (`servizio.Lavori` lo controlla).

Gli stream registrati possono essere più d'uno (agente, archivio, scrittore dell'ufficio sullo
stesso server): `registra_stream` restituisce una chiave e `voce_occupata` li chiude tutti
(quelli che la pausa non copre). `ClienteCedevole` avvolge un client dell'agente per chi non
ha un ciclo suo (archivio, ufficio): aspetta la voce, cede quando lei si sveglia (congelato
dalla pausa, o con lo stream chiuso e la richiesta rifatta).
"""

import queue
import threading
import time

RICONTROLLO_S = 600.0          # dopo un 404 la pausa si riprova tra 10 minuti
ATTESA_RIPRESA_S = 3.0         # vieta_pausa: quanto aspetta che il server riparta
INCERTA_S = 15.0               # dopo una pausa senza risposta: controlli con /is_paused


def radice(url: str | None) -> str:
    """http://127.0.0.1:8000/v1/ → http://127.0.0.1:8000 (localhost → 127.0.0.1)."""
    u = (url or "").strip().rstrip("/")
    if u.endswith("/v1"):
        u = u[:-3]
    return u.replace("://localhost", "://127.0.0.1").lower()


class PausaServer:
    """`POST /pause?mode=keep` e `POST /resume` di vLLM in modalità sviluppo. Ogni chiamata ha
    un tempo massimo breve; nessuna solleva. `disponibile`: None (non ancora provato), True,
    False (404: niente modalità sviluppo; si riprova dopo RICONTROLLO_S)."""

    def __init__(self, url: str, timeout_s: float = 1.0, log=print):
        import httpx
        self.url = radice(url)
        self.log = log
        self._disponibile: bool | None = None
        self._dal_404 = 0.0
        self.da_riprendere = False          # una pausa chiesta (forse arrivata) da riprendere
        # Dopo una pausa senza risposta, fin quando ricontrollare: la richiesta potrebbe
        # arrivare al server DOPO la nostra ripresa e lasciarlo in pausa
        self.incerta_fino = 0.0
        self.tempi_pausa: list[float] = []   # secondi, per le misure
        self.tempi_ripresa: list[float] = []
        self._http = httpx.Client(base_url=self.url, timeout=httpx.Timeout(
            timeout_s, connect=min(0.5, timeout_s)))

    @property
    def disponibile(self) -> bool | None:
        if self._disponibile is False and time.monotonic() - self._dal_404 > RICONTROLLO_S:
            self._disponibile = None
        return self._disponibile

    def _assente(self):
        if self._disponibile is not False:
            self.log("   [AGENTI] vLLM senza /pause (modalità sviluppo spenta): l'arbitro "
                     "chiude gli stream quando si parla.")
        self._disponibile = False
        self._dal_404 = time.monotonic()

    def sonda(self) -> bool | None:
        """GET /is_paused: True/False (e la pausa è disponibile), None se non si sa."""
        import httpx
        try:
            r = self._http.get("/is_paused")
        except httpx.HTTPError:
            return None
        if r.status_code == 404:
            self._assente()
            return None
        if r.status_code >= 400:
            return None
        self._disponibile = True
        try:
            return bool(r.json().get("is_paused"))
        except ValueError:
            return None

    def pausa(self) -> bool:
        import httpx
        t = time.perf_counter()
        self.da_riprendere = True            # anche se non risponde: potrebbe essere arrivata
        try:
            r = self._http.post("/pause", params={"mode": "keep"})
        except (httpx.ConnectError, httpx.ConnectTimeout):
            self.da_riprendere = False       # server giù: la richiesta non è partita
            return False
        except httpx.HTTPError:
            self.incerta_fino = time.monotonic() + INCERTA_S
            return False
        if r.status_code == 404:
            self.da_riprendere = False
            self._assente()
            return False
        if r.status_code >= 400:
            return False
        self._disponibile = True
        self.tempi_pausa.append(time.perf_counter() - t)
        return True

    def riprendi(self) -> bool:
        """True se il server non è più in pausa (ripreso, giù o senza modalità sviluppo)."""
        import httpx
        t = time.perf_counter()
        try:
            r = self._http.post("/resume")
        except httpx.ConnectError:
            self.da_riprendere = False       # giù: un server riavviato non è in pausa
            return True
        except httpx.HTTPError:
            return False
        if r.status_code == 404:
            self.da_riprendere = False
            return True
        if r.status_code >= 400:
            return False
        self.da_riprendere = False
        self.tempi_ripresa.append(time.perf_counter() - t)
        return True

    def chiudi(self):
        try:
            self._http.close()
        except Exception:  # noqa: BLE001
            pass


class Arbitro:
    def __init__(self, condiviso: bool, ripresa_s: float = 3.0, tenuta_max_s: float = 45.0,
                 pausa: PausaServer | None = None, log=print):
        self.condiviso = bool(condiviso)
        self.ripresa_s = float(ripresa_s)
        # Se la voce non dice mai «libera» (una frase scartata, un errore) l'agente riparte
        # comunque dopo questo tempo
        self.tenuta_max_s = float(tenuta_max_s)
        self.log = log
        self._cv = threading.Condition()
        self._attiva = False
        self._dal = 0.0
        self._fino = 0.0
        self._streams: dict[int, tuple] = {}   # chiave → (funzione che chiude, url o None)
        self._n = 0
        # Quante volte la voce si è svegliata (da libera a occupata): chi è partito durante un
        # turno della voce (`ClienteCedevole(dalla_voce=True)`) cede solo al turno dopo
        self.turni = 0
        self.cessioni = 0                   # stream chiusi per dare la precedenza alla voce
        self.attese_s = 0.0                 # tempo passato dall'agente ad aspettare
        # Pausa del server (vLLM in modalità sviluppo)
        self.pausa = pausa if self.condiviso else None
        self._voluta = False                # il server dovrebbe essere in pausa
        self._in_pausa = False              # il server è (o potrebbe essere) in pausa
        self._ripiego_turno = -1            # in questo turno si chiudono gli stream
        self._vieti: dict[int, int] = {}    # chiave → turno: richieste che la voce aspetta
        self._chiuso = False
        self.pause = 0
        self.riprese = 0
        self.ripieghi = 0
        # Le chiusure degli stream le fa un thread già pronto (03/10): `Thread.start()`
        # aspetta che il thread nuovo parta davvero, e con la macchina carica (più prove
        # insieme, il browser, Whisper) l'attesa arrivava a 15–50 ms nel thread della voce.
        # Mettere una funzione in coda non aspetta nessuno
        self._da_chiudere: queue.SimpleQueue = queue.SimpleQueue()
        if self.condiviso:
            threading.Thread(target=self._chiudi_stream, daemon=True,
                             name="arbitro-cedi").start()
        if self.pausa is not None:
            threading.Thread(target=self._gestisci_pausa, daemon=True,
                             name="arbitro-pausa").start()

    # ── pausa del server ──
    def _stesso_server(self, url) -> bool:
        return url is None or radice(url) == self.pausa.url

    def _copre(self, url) -> bool:
        """Lo stream di `url` è congelato dalla pausa del server (invece che chiuso)?"""
        return (self.pausa is not None and self.pausa.disponibile is not False
                and self._ripiego_turno != self.turni and self._stesso_server(url))

    def _pausa_usabile(self) -> bool:
        return (self.pausa is not None and not self._chiuso
                and self.pausa.disponibile is not False
                and self._ripiego_turno != self.turni
                and self.turni not in self._vieti.values())

    def _gestisci_pausa(self):
        """Il thread della pausa: porta il server allo stato voluto (pausa mentre la voce è
        occupata e per la ripresa dopo, altrimenti ripreso)."""
        p = self.pausa
        # All'avvio: un vLLM lasciato in pausa (Calliope morta a metà di un turno) riparte
        if p.sonda():
            self.log("   [AGENTI] vLLM era rimasto in pausa: lo riprendo.")
            with self._cv:
                self._in_pausa = True
        while True:
            attesa = 0.0
            with self._cv:
                if self._voluta and not self._occupata():
                    self._voluta = False     # finita la ripresa (o la tenuta massima)
                voluta, in_p = self._voluta, self._in_pausa
                if voluta == in_p:
                    if self._chiuso and not in_p:
                        return
                    now = time.monotonic()
                    if voluta:
                        fine = (self._dal + self.tenuta_max_s if self._attiva else self._fino)
                        attesa = min(1.0, max(0.01, fine - now + 0.005))
                    elif p.incerta_fino > now:
                        attesa = -1          # pausa senza risposta di poco fa: si controlla
                    else:
                        attesa = 1.0
                    if attesa > 0:
                        self._cv.wait(attesa)
                        continue
            if attesa < 0:
                # Una pausa arrivata dopo la nostra ripresa lascerebbe vLLM fermo: si guarda
                if p.sonda():
                    with self._cv:
                        self._in_pausa = True
                else:
                    with self._cv:
                        self._cv.wait(0.3)
                continue
            if voluta:
                ok = p.pausa()
                stops = []
                with self._cv:
                    if ok:
                        self._in_pausa = True
                        self.pause += 1
                    else:
                        # Ripiego per questo turno: si chiudono gli stream come prima; se la
                        # pausa potrebbe essere arrivata, la ripresa si manda comunque
                        self._ripiego_turno = self.turni
                        self._voluta = False
                        self._in_pausa = p.da_riprendere
                        self.ripieghi += 1
                        if self._attiva:
                            stops = [s for s, u in self._streams.values()
                                     if self._stesso_server(u)]
                    self._cv.notify_all()
                for stop in stops:
                    self.cessioni += 1
                    self._da_chiudere.put(stop)
            else:
                ok = p.riprendi()
                with self._cv:
                    if ok:
                        self._in_pausa = False
                        self.riprese += 1
                        self._cv.notify_all()
                    else:
                        self._cv.wait(0.5)    # si riprova tra poco

    def vieta_pausa(self) -> int:
        """Una richiesta che la voce sta aspettando (lo scrittore dell'ufficio) sta per partire:
        in questo turno niente pausa del server. Se è già in pausa si riprende subito, e gli
        altri stream di quel server si chiudono come prima. Aspetta (al più
        ATTESA_RIPRESA_S) che il server sia ripreso. Restituisce la chiave per
        `togli_vieto`."""
        stops = []
        with self._cv:
            self._n += 1
            k = self._n
            self._vieti[k] = self.turni
            if self.pausa is None:
                return k
            if self._voluta or self._in_pausa:
                self._voluta = False
                if self._attiva:
                    self._ripiego_turno = self.turni
                    stops = [s for s, u in self._streams.values() if self._stesso_server(u)]
                self._cv.notify_all()
        for stop in stops:
            self.cessioni += 1
            self._da_chiudere.put(stop)
        fine = time.monotonic() + ATTESA_RIPRESA_S
        with self._cv:
            while self._in_pausa and time.monotonic() < fine:
                self._cv.wait(0.05)
        return k

    def togli_vieto(self, chiave: int):
        with self._cv:
            self._vieti.pop(chiave, None)

    def chiudi(self, timeout_s: float = 1.5):
        """Alla chiusura di Calliope: il server non resta in pausa. Aspetta la ripresa al più
        `timeout_s`, poi la manda da sé."""
        if self.pausa is None:
            return
        with self._cv:
            self._chiuso = True
            self._voluta = False
            self._cv.notify_all()
            fine = time.monotonic() + timeout_s
            while self._in_pausa and time.monotonic() < fine:
                self._cv.wait(0.05)
            ancora = self._in_pausa or self.pausa.da_riprendere
        if ancora:
            self.pausa.riprendi()

    def proteggi_uscita(self):
        """Su SIGTERM (`calliope ferma`, systemd) riprende il server prima di uscire: Python
        di suo uscirebbe senza atexit. Poi il gestore di prima (o l'uscita normale del
        segnale). Solo dal thread principale."""
        if self.pausa is None:
            return
        import os
        import signal
        if threading.current_thread() is not threading.main_thread():
            return
        try:
            prima = signal.getsignal(signal.SIGTERM)
        except (ValueError, AttributeError):
            return
        if prima is signal.SIG_IGN:
            return

        def gestore(signum, frame):
            try:
                self.chiudi(timeout_s=0.5)
            finally:
                if callable(prima):
                    prima(signum, frame)
                else:
                    signal.signal(signal.SIGTERM, signal.SIG_DFL)
                    os.kill(os.getpid(), signal.SIGTERM)
        try:
            signal.signal(signal.SIGTERM, gestore)
        except (ValueError, OSError):
            pass

    # ── lato voce: non blocca mai ──
    def voce_occupata(self):
        if not self.condiviso:
            return
        with self._cv:
            if not self._attiva:
                self._dal = time.monotonic()
                self.turni += 1
            self._attiva = True
            usa = self._pausa_usabile()
            if usa:
                self._voluta = True
            stops = [s for s, u in self._streams.values() if not (usa and self._copre(u))]
            self._cv.notify_all()
        for stop in stops:
            self.cessioni += 1
            self._da_chiudere.put(stop)

    def _chiudi_stream(self):
        while True:
            stop = self._da_chiudere.get()
            try:
                stop()
            except Exception:  # noqa: BLE001 — uno stream già chiuso: va bene così
                pass

    def voce_libera(self, ripresa_s: float | None = None):
        if not self.condiviso:
            return
        with self._cv:
            if not self._attiva:
                return                       # già libera: niente pausa in più
            self._attiva = False
            self._fino = time.monotonic() + (self.ripresa_s if ripresa_s is None else ripresa_s)
            self._cv.notify_all()

    # ── lato agente ──
    def _occupata(self) -> bool:
        now = time.monotonic()
        if self._attiva and now - self._dal > self.tenuta_max_s:
            self._attiva = False             # nessuno ha detto «libera»: si riparte
        return self._attiva or now < self._fino

    def in_pausa(self) -> bool:
        """L'agente sta aspettando la voce (o la ripresa dopo): per la scheda «in pausa»
        sugli schermi (avanzamento.py). Non blocca."""
        if not self.condiviso:
            return False
        with self._cv:
            return self._occupata()

    def deve_cedere(self, url: str | None = None) -> bool:
        """Lo stream di `url` (None: quello del server dell'agente) deve chiudersi? No se la
        pausa del server lo congela."""
        if not self.condiviso:
            return False
        with self._cv:
            if not self._attiva:
                return False
            return not (self._voluta and self._copre(url))

    def attendi(self, annulla: threading.Event | None = None) -> float:
        """Aspetta che la voce sia libera (solo se condiviso). Restituisce i secondi
        aspettati."""
        if not self.condiviso:
            return 0.0
        t0 = time.monotonic()
        with self._cv:
            while self._occupata():
                if annulla is not None and annulla.is_set():
                    break
                self._cv.wait(0.1)
        waited = time.monotonic() - t0
        self.attese_s += waited
        return waited

    def registra_stream(self, stop, url: str | None = None) -> int:
        """`stop()` chiude uno stream (da un altro thread); `url` è il server dello stream
        (None: quello dell'agente). Restituisce la chiave per `togli_stream`."""
        with self._cv:
            self._n += 1
            self._streams[self._n] = (stop, url)
            return self._n

    def togli_stream(self, chiave: int | None = None):
        """Toglie lo stream `chiave`; senza chiave tutti."""
        with self._cv:
            if chiave is None:
                self._streams.clear()
            else:
                self._streams.pop(chiave, None)


def _interrompi(cliente, tid: int):
    """Chiude lo stream del thread `tid` (i client di remoto.py e remoto_openai.py); un client
    senza il parametro (le prove) li chiude tutti."""
    try:
        cliente.interrompi(tid)
    except TypeError:
        cliente.interrompi()


class ClienteCedevole:
    """Un client dell'agente che dà la precedenza alla voce, per chi non ha un ciclo suo
    (OCR ed estrazione dell'archivio, testi lunghi dell'ufficio). Stessa interfaccia del
    client avvolto; `chat` aspetta la voce e, quando lei si sveglia, resta congelato dalla
    pausa del server oppure chiude lo stream e rifà la richiesta da capo appena è di nuovo
    libera (si perde solo la generazione in corso).

    `dalla_voce=True`: la richiesta nasce da un turno della voce (lo scrittore dell'ufficio,
    che la voce aspetta per qualche secondo): non aspetta il turno in corso, non si congela
    in quel turno (`Arbitro.vieta_pausa`) e cede solo se ne comincia un altro. Con
    `arbitro.condiviso` falso è un passaggio diretto."""

    def __init__(self, cliente, arbitro: Arbitro, dalla_voce: bool = False):
        self._cliente = cliente
        self._arbitro = arbitro
        self.dalla_voce = dalla_voce
        self.cessioni = 0

    def __getattr__(self, nome):
        return getattr(self._cliente, nome)

    def chat(self, body: dict, su_pezzo=None, controlla=None, **kw) -> dict:
        from .remoto import Interrotto
        arb = self._arbitro
        if not arb.condiviso:
            return self._cliente.chat(body, su_pezzo=su_pezzo, controlla=controlla, **kw)
        url = getattr(self._cliente, "url", None)
        turno = arb.turni if self.dalla_voce else None
        vieto = arb.vieta_pausa() if self.dalla_voce else None
        tid = threading.get_ident()
        try:
            while True:
                if turno is None:
                    arb.attendi()
                    turno = arb.turni
                ceduto = []

                def stop():
                    ceduto.append(1)
                    _interrompi(self._cliente, tid)

                def cedi(turno=turno):
                    if controlla is not None:
                        controlla()
                    if arb.turni != turno and arb.deve_cedere(url):
                        ceduto.append(1)
                        raise Interrotto()
                chiave = arb.registra_stream(stop, url)
                try:
                    # Svegliata tra attendi() e la registrazione: si aspetta di nuovo
                    if arb.turni != turno and arb.deve_cedere(url):
                        raise Interrotto()
                    return self._cliente.chat(body, su_pezzo=su_pezzo, controlla=cedi, **kw)
                except Interrotto:
                    if not ceduto and arb.turni == turno:
                        raise                # chiuso da qualcun altro (annullo, chiusura)
                    self.cessioni += 1
                    turno = None             # si rifà dopo la voce
                finally:
                    arb.togli_stream(chiave)
        finally:
            if vieto is not None:
                arb.togli_vieto(vieto)
