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
  percentuale di «quanto manca» non esiste;
- il testo che l'agente sta scrivendo (risposta, ragionamento, o il codice negli argomenti
  di scrivi_file con vLLM), tagliato alla coda.

**Costo**: chi lavora (il thread dei lavori, lo stream dell'agente, la voce che annulla) fa
solo `_evento`: un lock breve, qualche assegnazione e un `notify`. La scheda la costruisce e
la manda un thread suo («lavori-schermo»), al più una ogni `INTERVALLO_S` per lavoro: i
pezzi dello stream si accorpano. Senza schermi (`Lavoro.on_scheda` assente) il lavoro non ha
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

import threading
import time
from collections import deque

# Al più due aggiornamenti al secondo per lavoro (i cambi di stato non aspettano)
INTERVALLO_S = 0.5
# Quanti passi recenti mostrare, e quanto testo in arrivo
PASSI_RECENTI = 6
FLUSSO_MAX = 600
ANTEPRIMA_RIGHE = 24
ANTEPRIMA_CARATTERI = 1400
FILE_MAX = 12

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


def _decodifica_argomenti(arg: str) -> str:
    """Gli argomenti JSON di scrivi_file a metà (vLLM li manda a pezzi): il testo dopo
    «"contenuto": "», con gli escape più comuni sciolti. Vuoto se non c'è ancora."""
    i = arg.find('"contenuto"')
    if i < 0:
        return ""
    j = arg.find('"', arg.find(":", i) + 1)
    if j < 0:
        return ""
    t = arg[j + 1:]
    out, k = [], 0
    while k < len(t):
        ch = t[k]
        if ch == "\\" and k + 1 < len(t):
            n = t[k + 1]
            out.append({"n": "\n", "t": "    ", '"': '"', "\\": "\\", "/": "/"}.get(n, ""))
            k += 2
            continue
        if ch == '"':                       # fine della stringa
            break
        out.append(ch)
        k += 1
    return "".join(out)


class _Segue:
    """Quello che la scheda di un lavoro mostra oltre ai campi del lavoro."""

    def __init__(self, lav):
        self.lav = lav
        self.passi: deque = deque(maxlen=PASSI_RECENTI)
        self.file: dict[str, int] = {}        # nome → righe, nell'ordine dell'ultima scrittura
        self.anteprima: dict | None = None
        self.flusso = ""
        self.flusso_tipo = ""
        self.chiamata = ""                     # argomenti a pezzi della chiamata in corso
        self.test: dict | None = None
        self.sporco = True
        self.finale_pendente = False           # una finale da costruire nel thread
        self.chiuso = False                    # finale mandata: niente più aggiornamenti
        self.ultimo = float("-inf")            # monotonic dell'ultimo invio
        self.inviate = 0
        self.pausa = False                     # ultima pausa mandata


class Avanzamento:
    def __init__(self, tetti, arbitro=None, finale=None, log=print,
                 intervallo: float = INTERVALLO_S):
        """`tetti()` → (passate, token, secondi) massimi; `finale(lav)` → la scheda finale
        (Lavori.scheda) o None."""
        self.tetti = tetti
        self.arbitro = arbitro
        self.costruisci_finale = finale
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
                sg.flusso, sg.flusso_tipo, sg.chiamata = "", "", ""
                return                          # niente da mostrare finché non arriva testo
            elif evento == "flusso":
                tipo, t = dati.get("tipo") or "testo", str(dati.get("testo") or "")
                if tipo == "chiamata":
                    sg.chiamata = (sg.chiamata + t)[-20000:]
                    codice = _decodifica_argomenti(sg.chiamata)
                    if not codice:
                        return
                    sg.flusso, sg.flusso_tipo = codice[-FLUSSO_MAX:], "codice"
                else:
                    if sg.flusso_tipo != tipo:
                        sg.flusso = ""
                    sg.flusso = (sg.flusso + t)[-FLUSSO_MAX:]
                    sg.flusso_tipo = tipo
            elif evento == "file":
                nome, testo = str(dati.get("nome") or "file"), str(dati.get("testo") or "")
                sg.file.pop(nome, None)
                sg.file[nome] = testo.count("\n") + (0 if testo.endswith("\n") else 1)
                while len(sg.file) > FILE_MAX:
                    sg.file.pop(next(iter(sg.file)))
                if lav.tipo == "codice":
                    sg.anteprima = {"nome": nome, "testo": _anteprima(testo)}
                sg.flusso, sg.flusso_tipo, sg.chiamata = "", "", ""
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

    def _istantanea(self, sg: _Segue, pausa: bool) -> dict:
        """I dati dell'avanzamento (con il lock)."""
        lav = sg.lav
        try:
            passate, token, secondi = self.tetti(lav)     # il tetto dei token è per tipo
        except TypeError:
            passate, token, secondi = self.tetti()
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
              "flusso": ({"tipo": sg.flusso_tipo, "testo": sg.flusso}
                         if sg.flusso.strip() and corre else None),
              "test": dict(sg.test) if sg.test else None,
              "passate": lav.passi, "max_passate": int(passate),
              "token": lav.token, "max_token": int(token),
              "trascorso_s": round(trascorso, 1), "max_s": round(float(secondi)),
              # da quando contare (epoch) se il lavoro corre: la pagina conta da sola
              "dal": round(ora - trascorso, 1) if corre else None,
              "ora_server": round(ora, 3)}
        return av

    def _manda(self, sg: _Segue, pausa: bool):
        from ..schermi import schede
        lav = sg.lav
        with self._invio:
            with self._lock:
                if sg.chiuso or lav.stato in FINALI:
                    sg.sporco = False
                    return
                sg.sporco = False
                av = self._istantanea(sg, pausa)
                prima = sg.inviate == 0
                sg.pausa = av["pausa"]
            card = schede.lavoro_avanzamento(lav.titolo, lav.tipo, lav.stato, av, ident=lav.id,
                                             sposta=prima)
            self._consegna(lav, card)
            with self._lock:
                sg.ultimo = time.monotonic()
                sg.inviate += 1

    def _manda_finale(self, sg: _Segue):
        lav = sg.lav
        with self._invio:
            with self._lock:
                av = self._istantanea(sg, False)
                av["flusso"] = None
                sg.chiuso = True
                sg.sporco = False
                if lav.stato != "in_attesa":
                    self._segue.pop(lav.id, None)
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
            else:
                # La stessa identità della scheda in corso: la sostituisce (anche quella del
                # documento), e porta il lavoro in cima
                card = {**card, "chiave": f"lavoro:{lav.id}", "avanzamento": av}
                card.pop("sposta", None)
            self._consegna(lav, card)
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
