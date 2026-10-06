"""
I giochi sugli schermi (05/10/2026, decisioni di Dario del 04–05/10): le estensioni con una
scheda interattiva (calliope/estensioni/scheda.py) girano nel browser, in un riquadro isolato;
qui il lato di Calliope. Rapporto: docs/ricerche/2026-10-05-giochi.md.

- **Partita**: nasce dal tool del gioco (`est_<nome>`, a voce o scritto) su uno schermo; ha un
  gettone a caso che è l'indirizzo del suo documento (`GET /gioco/<gettone>`: lo compone
  scheda.documento dai file della versione approvata, impronta ricontrollata) e uno o più
  **posti** (uno per schermo), ognuno con il suo giocatore (chi ha aperto la partita da lì).
- **Messaggi dal riquadro** (`POST /api/gioco`, dalla pagina, che li ha già controllati): qui
  si ricontrolla tutto (schermo della sessione nella partita, tipo, dimensione, frequenza):
  `pronto` (il posto e i dati d'avvio), `battito` (tempo di gioco dei minori), `salva` e
  `leggi` (lo spazio dati dell'estensione), `manda` (a chi gioca da altri schermi, passando
  da qui), `chat` (testo libero tra giocatori: con un minore o un ospite nella partita passa
  dal guardiano), `di` (una frase detta da Calliope: poche al minuto, controllate come gli
  annunci, per i minori dal guardiano), `azione` (un metodo della porta stretta, con le regole
  delle estensioni), `fine`, `errore` e `guasto` (il cane da guardia della pagina).
- **Verso il riquadro**: l'evento SSE «gioco» allo schermo (messaggi degli altri, chat,
  giocatori, risposte che arrivano dopo, fine del tempo di gioco).

Nessun dato di casa passa di qui se il gioco non l'ha chiesto con la porta stretta; e una
partita che l'ha letto non manda più messaggi agli altri schermi (`gioco_dati_personali`).
"""

from __future__ import annotations

import json
import queue
import re
import secrets
import threading
import time
from collections import deque

from . import schede
from .hub import Mittente, destinatari
from ..testi import NIENTE, RANK

_CHIAVE = re.compile(r"^[A-Za-z0-9_\-. ]{1,40}$")
# Con un minore o un ospite nella partita i messaggi del gioco non portano testo libero: solo
# valori brevi senza spazi (mosse, coordinate, colori); il testo va con la chat, dal guardiano
_VALORE_BREVE = re.compile(r"^[\w\-.:#+/]{0,24}$")
MAX_STORIA = 200
MAX_SALVA = 16_000
MAX_DATI = 1_000_000
MAX_FRASE = 160
MAX_CHAT = 200
NOTE_GUASTO = {"non risponde": "Il gioco non rispondeva più: l'ho chiuso.",
               "navigazione": "Il gioco ha provato a cambiare pagina: l'ho chiuso.",
               "troppi messaggi": "Il gioco mandava troppi messaggi: l'ho chiuso.",
               "messaggi non validi": "Il gioco mandava messaggi non validi: l'ho chiuso.",
               "non parte": "Il gioco non è partito: l'ho chiuso."}
TIPI_PAGINA = ("pronto", "battito", "salva", "leggi", "manda", "chat", "di", "azione", "fine",
               "errore", "guasto")


def _final(testo: str, **extra) -> dict:
    return {"ok": True, **extra, "conferma": testo, "risposta_finale": testo}


def _rifiuto(ctx, testo: str, regola: str) -> dict:
    from ..tools.spec import note_rule
    note_rule(ctx, regola)
    return _final(testo, ok=False, fatto=NIENTE)


class Posto:
    def __init__(self, sid: int, mitt: Mittente, minore: bool):
        self.sid = sid
        self.persona = mitt.persona
        self.nome = mitt.nome
        self.livello = mitt.livello if mitt.persona else "ospite"
        self.minore = minore
        self.giocatore: int | None = None
        self.ultimo_battito = 0.0
        self.fermato = False
        self.messaggi: deque = deque(maxlen=200)     # istanti, per la frequenza
        self.chat: deque = deque(maxlen=50)


class Partita:
    def __init__(self, nome: str, versione: int, manifesto: dict, avviata_da: Mittente):
        self.id = "P" + secrets.token_hex(4)
        self.gettone = secrets.token_urlsafe(24)
        self.nome, self.versione, self.manifesto = nome, versione, manifesto
        self.titolo = manifesto.get("titolo", nome)
        self.scheda = manifesto.get("scheda") or {}
        self.avviata_da = avviata_da
        self.creata = self.ultimo = time.time()
        self.posti: dict[int, Posto] = {}
        self.storia: deque = deque(maxlen=MAX_STORIA)
        self.contaminazione: set[str] = set()
        self.frasi: deque = deque(maxlen=50)
        self.carte: dict[int, dict] = {}            # la scheda mandata a ogni schermo
        self.n = 0

    @property
    def condivisa(self) -> bool:
        return bool(self.scheda.get("condivisa"))

    @property
    def massimo(self) -> int:
        return int((self.scheda.get("giocatori") or {}).get("max", 1))

    def protetta(self) -> bool:
        """Nella partita c'è un minore o un ospite (testo libero dal guardiano)."""
        return any(p.minore or not p.persona for p in self.posti.values())


class Giochi:
    def __init__(self, cfg, hub, estensioni=None, log=print):
        self.cfg = cfg
        self.hub = hub
        self.estensioni = estensioni
        self.log = log
        self._lock = threading.RLock()
        self.partite: dict[str, Partita] = {}
        self._per_gettone: dict[str, str] = {}
        self._documenti: dict[tuple, tuple] = {}
        # Le frasi che i giochi fanno dire a Calliope: le dice il ciclo principale (main.py)
        # quando nessuno parla, come gli annunci
        self.frasi: queue.Queue = queue.Queue()
        self.on_frase = None
        self.guardiano = None              # main.py: calliope.guardiano.Guardiano (o None)
        self.guasti: deque = deque(maxlen=100)

    # ── configurazione ──
    def _c(self, k: str, d):
        try:
            return type(d)(getattr(self.cfg, k, d))
        except (TypeError, ValueError):
            return d

    # ── dal tool del gioco ──
    def avvia(self, ctx, nome: str, versione: int, m: dict, argomenti: dict) -> dict:
        """Apre una partita (o si unisce a quella aperta da un altro schermo) e manda la
        scheda del gioco a uno schermo. Il risultato per la voce."""
        from .. import minori
        from ..estensioni.scheda import e_gioco_puro
        if not getattr(self.cfg, "giochi_enabled", True):
            return _rifiuto(ctx, "I giochi sugli schermi sono spenti.", "gioco_spento")
        self.pulisci()
        titolo = m.get("titolo", nome)
        prof = minori.profilo(ctx)
        minore = minori.e_minore(prof)
        if minore:
            resta = minori.gioco_restante_s(prof)
            if resta is not None and resta <= 0:
                out = _rifiuto(ctx, "Per oggi il tempo dei giochi è finito.", "gioco_tempo_finito")
                rq = minori.richieste()
                if rq is not None:
                    try:
                        _, nuova = rq.crea(prof, "tempo_gioco", "tempo_gioco",
                                           registry=getattr(ctx, "speakers", None))
                        t = minori._tutore_nome(prof, getattr(ctx, "speakers", None))
                        frase = ("Per oggi il tempo dei giochi è finito. " + (
                            f"Ho chiesto a {t} se puoi giocare ancora un po'." if nuova else
                            f"L'ho già chiesto a {t}: aspettiamo la risposta."))
                        out.update(conferma=frase, risposta_finale=frase)
                    except Exception:  # noqa: BLE001
                        pass
                return out
        mitt = self.hub.mittente(ctx)
        puro = e_gioco_puro(m)
        perm = m.get("permessi") or {}
        vis = (schede.PUBBLICA if puro else schede.PERSONALE
               if (perm.get("legge") or {}).get("agenda") else schede.CASA)
        stanza = mitt.stanza or self.hub.stanza_predefinita or None
        dest, motivo = destinatari(vis, mitt, self.hub.abbinati(), stanza)
        if not dest:
            frasi = {"nessuno_schermo": "Per giocare serve uno schermo abbinato: non ne ho.",
                     "ospite": f"«{titolo}» lo mostro solo a chi vive in casa.",
                     "personale": f"«{titolo}» va sul tuo schermo personale, e non ne hai uno.",
                     "zona_grigia": "Non ti ho riconosciuto bene: ripetimelo con una frase più "
                                    "lunga.",
                     "stanza": "Qui non c'è uno schermo per giocare."}
            return _rifiuto(ctx, frasi.get(motivo, "Non trovo uno schermo per giocare."),
                            "gioco_senza_schermo")
        # Uno schermo solo: quello da cui arriva la richiesta, altrimenti il personale di chi
        # parla, altrimenti il primo della stanza
        s = next((x for x in dest if x.get("id") == mitt.schermo), None) or next(
            (x for x in dest if mitt.persona and x.get("proprietario") == mitt.persona), dest[0])
        sid = s["id"]
        unisciti = str((argomenti or {}).get("partita") or "").strip().lower() != "nuova"
        with self._lock:
            p = None
            if m.get("scheda", {}).get("condivisa") and unisciti:
                aperte = [x for x in self.partite.values() if x.nome == nome
                          and x.versione == versione and sid not in x.posti
                          and len(x.posti) < x.massimo and time.time() - x.ultimo < 1800]
                p = max(aperte, key=lambda x: x.ultimo) if aperte else None
            nuova = p is None
            if nuova:
                p = Partita(nome, versione, m, mitt)
                self.partite[p.id] = p
                self._per_gettone[p.gettone] = p.id
            p.posti[sid] = Posto(sid, mitt, minore)
            p.ultimo = time.time()
        card = schede.nuova("gioco", titolo, vis, durata_s=None, chiave=f"gioco:{p.id}",
                            partita=p.id, doc=f"/gioco/{p.gettone}", condivisa=p.condivisa,
                            giocatori=p.massimo, watchdog_s=self._c("giochi_watchdog_s", 6.0))
        self.hub.ricorda(card, mitt)
        p.carte[sid] = card
        collegato = self.hub.invia_a(sid, card)
        self._registra(p, "avvio" if nuova else "unito", schermo=s.get("nome"),
                       persona=mitt.nome)
        dove = s.get("nome") or "schermo"
        if not nuova:
            altri = [self._nome_schermo(x) for x in p.posti if x != sid]
            frase = (f"Sei nella partita di «{titolo}»" + (f" con {', '.join(altri)}"
                                                           if altri else "") + ".")
        elif p.condivisa:
            frase = (f"Ecco «{titolo}» sullo schermo {self._di(dove)}. Per giocare da un'altra "
                     f"stanza, chiedimelo da lì.")
        else:
            frase = f"Ecco «{titolo}» sullo schermo {self._di(dove)}."
        if not collegato:
            frase += " Lo schermo sembra spento: lo vedrai appena si riaccende."
        from ..tools.spec import note_rule
        note_rule(ctx, "gioco_avviato")
        return _final(frase, partita=p.id)

    def _nome_schermo(self, sid) -> str:
        s = self.hub.schermo(sid) or {}
        return f"lo schermo {self._di(s.get('nome') or 'senza nome')}"

    @staticmethod
    def _di(nome: str) -> str:
        n = str(nome or "").strip()
        return n if n.lower().startswith(("del", "dello", "della", "di ")) else f"«{n}»"

    # ── il documento del riquadro ──
    def documento(self, gettone: str) -> tuple[str, str] | None:
        """(HTML, CSP) del riquadro della partita, dai file della versione approvata (impronta
        ricontrollata). None: gettone sconosciuto, partita finita o file cambiati."""
        from ..estensioni.scheda import documento
        with self._lock:
            pid = self._per_gettone.get(str(gettone or ""))
            p = self.partite.get(pid) if pid else None
        est = self.estensioni
        if p is None or est is None:
            return None
        voce = est.archivio.voce(p.nome) or {}
        if voce.get("stato") != "attiva" or voce.get("attiva") != p.versione \
                or not est.archivio.verifica(p.nome):
            return None
        chiave = (p.nome, p.versione)
        d = self._documenti.get(chiave)
        if d is None:
            d = documento(p.scheda, est.file_versione(p.nome, p.versione))
            self._documenti = {chiave: d}             # una versione per volta in memoria
        return d

    # ── dalla pagina ──
    def da_pagina(self, schermo: dict, dati: dict) -> dict:
        """Un messaggio di un riquadro, arrivato dalla pagina dello schermo. Il risultato va
        alla pagina (e al riquadro, se aveva un id); `_stato` è il codice HTTP."""
        if not isinstance(dati, dict):
            return {"errore": "dati non validi", "_stato": 400}
        tipo = str(dati.get("tipo") or "")
        if tipo not in TIPI_PAGINA:
            return {"errore": "tipo sconosciuto", "_stato": 400}
        sid = schermo.get("id")
        with self._lock:
            p = self.partite.get(str(dati.get("partita") or ""))
            posto = p.posti.get(sid) if p is not None else None
        if p is None or posto is None:
            return {"errore": "partita sconosciuta per questo schermo", "_stato": 404}
        # Frequenza (il battito e il cane da guardia non contano)
        ora = time.time()
        if tipo not in ("battito", "guasto"):
            n = self._c("giochi_messaggi_secondo", 10)
            recenti = [t for t in posto.messaggi if ora - t < 1.0]
            if len(recenti) >= n:
                self._registra(p, "troppi_messaggi", regola="gioco_troppi_messaggi")
                return {"errore": "troppi messaggi", "_stato": 429}
            posto.messaggi.append(ora)
        try:
            grezzo = len(json.dumps(dati, ensure_ascii=False))
        except (TypeError, ValueError):
            return {"errore": "dati non validi", "_stato": 400}
        if grezzo > self._c("giochi_messaggio_max", 4096) + 512:
            self._registra(p, "messaggio_grande", regola="gioco_messaggio_grande")
            return {"errore": "messaggio troppo grande", "_stato": 413}
        p.ultimo = ora
        f = getattr(self, "_t_" + tipo)
        try:
            return f(p, posto, dati)
        except Exception as e:  # noqa: BLE001 — un messaggio non ferma il server
            self.log(f"[GIOCHI] {p.titolo}: {tipo} non riuscito: {type(e).__name__}: {e}")
            return {"errore": "non riuscito", "_stato": 500}

    def _avvio(self, p: Partita, posto: Posto) -> dict:
        return {"partita": p.id, "giocatore": posto.giocatore,
                "giocatori": len(p.posti), "massimo": p.massimo, "condivisa": p.condivisa,
                "storia": list(p.storia)[-100:], "lingua": "it"}

    def _t_pronto(self, p: Partita, posto: Posto, dati) -> dict:
        from .. import minori
        with self._lock:
            if posto.giocatore is None:
                usati = {x.giocatore for x in p.posti.values() if x.giocatore is not None}
                posto.giocatore = next(i for i in range(1, p.massimo + 2) if i not in usati)
        if posto.minore:
            prof = self._profilo(posto.persona)
            resta = minori.gioco_restante_s(prof) if prof is not None else None
            if resta is not None and resta <= 0:
                posto.fermato = True
                return {"ok": False, "fine_tempo": True,
                        "nota": "Per oggi il tempo dei giochi è finito."}
        posto.fermato = False
        self._agli_altri(p, posto, "giocatori", {"giocatori": len(p.posti),
                                                 "pronto": posto.giocatore})
        return {"ok": True, "avvio": self._avvio(p, posto)}

    def _t_battito(self, p: Partita, posto: Posto, dati) -> dict:
        """Il tempo di gioco (05/10, decisione 5): la pagina manda un battito ogni ~15 s mentre
        il riquadro si vede. Conta per il giocatore del posto, se è un minore."""
        from .. import minori
        ora = time.time()
        try:
            secondi = float(dati.get("secondi") or 0)
        except (TypeError, ValueError):
            secondi = 0.0
        # Mai più del tempo vero passato dal battito di prima (una pagina non gonfia né
        # sgonfia il conto), al più 30 s
        passato = ora - posto.ultimo_battito if posto.ultimo_battito else secondi
        secondi = max(0.0, min(secondi, passato + 1.0, 30.0))
        posto.ultimo_battito = ora
        if not posto.minore or posto.fermato:
            return {"ok": True, "fine_tempo": posto.fermato}
        prof = self._profilo(posto.persona)
        tg = minori.tempo_gioco()
        if prof is None or tg is None:
            return {"ok": True}
        tg.aggiungi(prof.id, secondi)
        resta = minori.gioco_restante_s(prof)
        if resta is not None and resta <= 0:
            posto.fermato = True
            self._registra(p, "fine_tempo", regola="gioco_tempo_finito", persona=prof.name)
            nota = "Per oggi il tempo dei giochi è finito."
            self.hub.evento_a(posto.sid, "gioco", {"partita": p.id, "tipo": "fine_tempo",
                                                   "dati": {"nota": nota}})
            return {"ok": True, "fine_tempo": True, "nota": nota}
        return {"ok": True, "resta_s": round(resta) if resta is not None else None}

    def _file_dati(self, p: Partita, chiave: str):
        est = self.estensioni
        cart = est.archivio.cartella_dati(p.nome)
        return cart, cart / f"gioco_{chiave}.json"

    def _t_salva(self, p: Partita, posto: Posto, dati) -> dict:
        if not p.scheda.get("salva"):
            return {"errore": "questo gioco non salva dati", "_stato": 403}
        chiave = str(dati.get("chiave") or "")
        if not _CHIAVE.match(chiave) or ".." in chiave:
            return {"errore": "chiave non valida (lettere, cifre, - _ . e spazi)", "_stato": 400}
        try:
            testo = json.dumps(dati.get("valore"), ensure_ascii=False)
        except (TypeError, ValueError):
            return {"errore": "valore non valido", "_stato": 400}
        if len(testo.encode("utf-8")) > MAX_SALVA:
            return {"errore": "valore troppo grande", "_stato": 413}
        cart, f = self._file_dati(p, chiave)
        cart.mkdir(parents=True, exist_ok=True)
        altri = sum(x.stat().st_size for x in cart.iterdir() if x.is_file() and x != f)
        if altri + len(testo.encode("utf-8")) > MAX_DATI:
            return {"errore": "spazio dei dati esaurito", "_stato": 413}
        from ..persistenza import scrivi_atomico
        if p.contaminazione:
            # Dati personali letti dalla partita: chi li rilegge è contaminato (come porta.py)
            self.estensioni.archivio.contamina(p.nome, p.contaminazione)
        scrivi_atomico(f, testo)
        return {"ok": True}

    def _t_leggi(self, p: Partita, posto: Posto, dati) -> dict:
        if not p.scheda.get("salva"):
            return {"errore": "questo gioco non salva dati", "_stato": 403}
        chiave = str(dati.get("chiave") or "")
        if not _CHIAVE.match(chiave) or ".." in chiave:
            return {"errore": "chiave non valida", "_stato": 400}
        _, f = self._file_dati(p, chiave)
        if not f.is_file():
            return {"ok": True, "valore": None}
        p.contaminazione |= set(self.estensioni.archivio.contaminazione(p.nome))
        try:
            return {"ok": True, "valore": json.loads(f.read_text(encoding="utf-8"))}
        except ValueError:
            return {"ok": True, "valore": None}

    def _t_manda(self, p: Partita, posto: Posto, dati) -> dict:
        if not p.condivisa:
            return {"errore": "partita non condivisa", "_stato": 403}
        valore = dati.get("dati")
        if p.contaminazione:
            # La partita ha letto dati personali (porta stretta): agli altri schermi niente
            self._registra(p, "bloccato", regola="gioco_dati_personali")
            return {"errore": "la partita ha letto dati personali: niente messaggi agli altri "
                              "schermi", "_stato": 403}
        if p.protetta() and not _solo_valori_brevi(valore):
            self._registra(p, "bloccato", regola="gioco_testo_libero")
            return {"errore": "con un bambino o un ospite nella partita i messaggi del gioco "
                              "portano solo valori brevi: il testo va con la chat",
                    "_stato": 422}
        with self._lock:
            p.n += 1
            msg = {"n": p.n, "da": posto.giocatore, "dati": valore}
            p.storia.append(msg)
        self._agli_altri(p, posto, "messaggio", msg)
        return {"ok": True, "n": p.n}

    def _t_chat(self, p: Partita, posto: Posto, dati) -> dict:
        if not (p.condivisa and p.scheda.get("chat")):
            return {"errore": "questo gioco non ha la chat", "_stato": 403}
        testo = _pulisci(dati.get("testo"), MAX_CHAT)
        if not testo:
            return {"errore": "messaggio vuoto", "_stato": 400}
        ora = time.time()
        if len([t for t in posto.chat if ora - t < 60]) >= self._c("giochi_chat_minuto", 6):
            return {"errore": "troppi messaggi: aspetta un momento", "_stato": 429}
        posto.chat.append(ora)
        if p.protetta():
            esito = self._guardiano(testo, domanda=True, minore=any(
                x.minore for x in p.posti.values()))
            if esito != "ok":
                regola = "gioco_chat_pericolo" if esito == "pericolo" else "gioco_chat_fermata"
                self._registra(p, "chat_fermata", regola=regola)
                if esito == "pericolo" and posto.minore:
                    self._avviso_pericolo(posto)
                return {"errore": "messaggio non mandato", "_stato": 422}
        self._agli_altri(p, posto, "chat", {"da": posto.giocatore, "testo": testo})
        return {"ok": True}

    def _t_di(self, p: Partita, posto: Posto, dati) -> dict:
        """Una frase del gioco detta da Calliope («Hai vinto!»): poche al minuto, nessun
        simbolo, controllata come gli annunci (riferire.controlla_testo: numeri a pagamento,
        segreti, soldi, indicazioni sulla casa); per un minore o un ospite dal guardiano. Non
        entra nella storia della conversazione."""
        if not p.scheda.get("voce"):
            return {"errore": "questo gioco non parla", "_stato": 403}
        testo = _pulisci(dati.get("testo"), MAX_FRASE)
        if not testo or not re.search(r"[A-Za-zÀ-ÿ]{2}", testo):
            return {"errore": "frase vuota", "_stato": 400}
        ora = time.time()
        with self._lock:
            if len([t for t in p.frasi if ora - t < 60]) >= self._c("giochi_frasi_minuto", 3):
                self._registra(p, "frase_fermata", regola="gioco_frasi_troppe")
                return {"errore": "troppe frasi: al più qualcuna al minuto", "_stato": 429}
            p.frasi.append(ora)
        from .. import riferire
        detto, regole = riferire.controlla_testo(testo, "estensione")
        if regole:
            # Un numero a pagamento, un ordine, un segreto: la frase non si dice affatto (una
            # frase fissa al posto di «Hai vinto!» non servirebbe a nessuno)
            self._registra(p, "frase_fermata", regola=",".join(regole))
            return {"errore": "frase non detta", "_stato": 422}
        if posto.minore or not posto.persona:
            esito = self._guardiano(detto, domanda=False, minore=posto.minore)
            if esito != "ok":
                self._registra(p, "frase_fermata", regola="gioco_frase_guardiano")
                return {"errore": "frase non detta", "_stato": 422}
        self.frasi.put({"messaggio": detto, "partita": p.id, "titolo": p.titolo,
                        "persona": posto.persona, "minore": posto.minore,
                        "schermo": posto.sid})
        if self.on_frase is not None:
            try:
                self.on_frase()
            except Exception:  # noqa: BLE001
                pass
        return {"ok": True}

    def _t_azione(self, p: Partita, posto: Posto, dati) -> dict:
        """Un metodo della porta stretta chiesto dal riquadro (con gli scope del manifesto):
        sicura → subito; vietata → errore; pericolosa → si chiede a voce, e la risposta arriva
        al riquadro dopo (evento «gioco»)."""
        nome = str(dati.get("nome") or "")
        args = dati.get("argomenti") if isinstance(dati.get("argomenti"), dict) else {}
        if nome not in (p.scheda.get("azioni") or []):
            self._registra(p, "azione_rifiutata", regola="gioco_azione_non_dichiarata",
                           azione=nome[:40])
            return {"errore": f"«{nome[:40]}» non è tra le azioni del gioco", "_stato": 403}
        est = self.estensioni
        if est is None:
            return {"errore": "estensioni spente", "_stato": 503}
        rif = dati.get("id")
        es = AzioneGioco(self, p, posto, nome, args, rif)
        return es.avvia()

    def _t_fine(self, p: Partita, posto: Posto, dati) -> dict:
        self._registra(p, "fine", giocatore=posto.giocatore)
        return {"ok": True}

    def _t_errore(self, p: Partita, posto: Posto, dati) -> dict:
        self.log(f"[GIOCHI] {p.titolo}: errore nel riquadro: "
                 f"{_pulisci(dati.get('testo'), 160)}")
        return {"ok": True}

    def _t_guasto(self, p: Partita, posto: Posto, dati) -> dict:
        """Il cane da guardia della pagina ha chiuso il riquadro (non risponde, troppi
        messaggi, ha provato a cambiare pagina): si segnala e resta scritto."""
        motivo = _pulisci(dati.get("motivo"), 80) or "guasto"
        self.guasti.append({"quando": time.time(), "gioco": p.nome, "motivo": motivo})
        # La scheda di quello schermo resta chiusa (anche dopo che la pagina si ricarica: un
        # riquadro bloccato non riparte da solo dalla cronologia)
        card = p.carte.get(posto.sid)
        if card is not None:
            nota = NOTE_GUASTO.get(motivo, "Il gioco si è chiuso.")
            p.carte[posto.sid] = chiusa = {**card, "stato": "chiuso", "nota": nota,
                                           "sposta": False}
            self.hub.invia_a(posto.sid, chiusa)
        posto.fermato = True
        self._registra(p, "guasto", regola="gioco_chiuso_dal_controllo", motivo=motivo)
        self.log(f"[GIOCHI] «{p.titolo}» chiuso sullo schermo "
                 f"{self._nome_schermo(posto.sid)}: {motivo}")
        return {"ok": True}

    # ── utilità ──
    def _profilo(self, pid):
        from ..minori import _per_id
        return _per_id(getattr(getattr(self.estensioni, "tool_ctx", None), "speakers", None)
                       or getattr(self, "speakers", None), pid)

    def _agli_altri(self, p: Partita, da: Posto, tipo: str, dati: dict):
        for sid, posto in list(p.posti.items()):
            if sid != da.sid and not posto.fermato:
                self.hub.evento_a(sid, "gioco", {"partita": p.id, "tipo": tipo, "dati": dati})

    def manda_a(self, p: Partita, posto: Posto, tipo: str, dati: dict):
        self.hub.evento_a(posto.sid, "gioco", {"partita": p.id, "tipo": tipo, "dati": dati})

    def _guardiano(self, testo: str, domanda: bool, minore: bool) -> str:
        """ok | vietato | pericolo | guasto. Senza guardiano: per un minore si blocca (come
        guardiano_se_guasto), per un ospite passa."""
        g = self.guardiano
        se_guasto = "ok" if not minore or str(getattr(self.cfg, "guardiano_se_guasto",
                                                      "blocca")) != "blocca" else "guasto"
        if g is None:
            return se_guasto
        try:
            from .. import guardiano as gd
            att = None if minore else set(getattr(gd, "MODERATO", ()) or ()) or None
            r = (g.giudica_domanda(testo, att) if domanda else
                 g.giudica("(frase di un gioco)", testo, att))
        except Exception:  # noqa: BLE001
            return se_guasto
        if r.esito == "ok":
            return "ok"
        if r.esito == "guasto":
            return se_guasto
        return r.esito

    def _avviso_pericolo(self, posto: Posto):
        from .. import minori
        prof = self._profilo(posto.persona)
        av = minori.avvisi()
        if prof is None or av is None:
            return
        try:
            av.manda(prof, "sicurezza", f"{prof.name} ha scritto nella chat di un gioco una cosa "
                                        f"che mi preoccupa. Parlagli appena puoi, con calma.",
                     urgente=True)
        except Exception:  # noqa: BLE001
            pass

    def _registra(self, p: Partita, evento: str, **extra):
        est = self.estensioni
        if est is not None:
            est.archivio.registra({"gioco": p.nome, "versione": p.versione, "partita": p.id,
                                   "evento": evento, **extra})
        regola = extra.get("regola")
        if regola:
            est_nota = getattr(est, "nota_regola", None)
            if est_nota is not None:
                for r in str(regola).split(","):
                    est_nota(r)

    def pulisci(self):
        """Le partite senza segni da più di `giochi_partita_ore`: il loro indirizzo non vale
        più."""
        ore = self._c("giochi_partita_ore", 6.0)
        limite = time.time() - ore * 3600
        with self._lock:
            for pid in [k for k, v in self.partite.items() if v.ultimo < limite]:
                p = self.partite.pop(pid)
                self._per_gettone.pop(p.gettone, None)

    def stato(self) -> dict:
        with self._lock:
            return {"partite": len(self.partite), "guasti_recenti": len(
                [g for g in self.guasti if time.time() - g["quando"] < 3600])}


def _solo_valori_brevi(v, profondita: int = 0) -> bool:
    if profondita > 6:
        return False
    if isinstance(v, str):
        return bool(_VALORE_BREVE.match(v))
    if isinstance(v, (int, float, bool)) or v is None:
        return True
    if isinstance(v, list):
        return len(v) <= 100 and all(_solo_valori_brevi(x, profondita + 1) for x in v)
    if isinstance(v, dict):
        return len(v) <= 50 and all(_VALORE_BREVE.match(str(k)) and
                                    _solo_valori_brevi(x, profondita + 1) for k, x in v.items())
    return False


def _pulisci(testo, massimo: int) -> str:
    t = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f​-‏‪-‮]", " ",
                                   str(testo or ""))).strip()
    return t[:massimo]


class AzioneGioco:
    """Una richiesta del riquadro alla porta stretta (estensioni/porta.py), con la stessa
    interfaccia di un'esecuzione (estensioni/esecuzione.py) per la porta e per il «sì» della
    persona (estensioni_gestisci consenti/nega). La contaminazione è della partita: un gioco
    che ha letto l'agenda non manda più messaggi agli altri schermi."""

    def __init__(self, giochi: Giochi, p: Partita, posto: Posto, azione: str, params: dict,
                 rif):
        from ..guardrail import StatoEsecuzione
        est = giochi.estensioni
        with est._lock:
            est._n += 1
            self.id = f"G{est._n}"
        self.giochi, self.partita, self.posto = giochi, p, posto
        self.azione, self.params, self.rif = azione, dict(params or {}), rif
        self.nome, self.versione, self.manifesto = p.nome, p.versione, p.manifesto
        self.persona, self.persona_nome = posto.persona, posto.nome
        self.livello = min(posto.livello, "familiare", key=lambda x: RANK.get(x, 0))
        self.storia = StatoEsecuzione()
        if p.contaminazione:
            self.storia.contamina(*p.contaminazione)
        self.decisioni: list = []
        self.mittente = Mittente(persona=posto.persona, nome=posto.nome, livello=self.livello,
                                 certo=bool(posto.persona), schermo=posto.sid)
        self.stato = "in_corso"
        self.richiesta = None
        self.risultato = None
        self.errore = ""
        self.tempo_s = 0.0
        self.da_annunciare = False
        self._cambio = threading.Condition()
        self._decisione = None

    def avvia(self) -> dict:
        est = self.giochi.estensioni
        porta = est.porta
        esito = porta.gestisci(self, self.azione, self.params)
        if not esito.get("conferma"):
            self._fine(esito)
            return self._per_pagina(esito)
        # Pericolosa: si chiede a voce (come un'estensione sospesa), la risposta arriva dopo
        with self._cambio:
            self.richiesta = {"azione": self.azione, "argomenti": self.params, **esito}
            self.stato = "in_attesa"
        with est._lock:
            est.esecuzioni[self.id] = self
        q = est._domanda(est.tool_ctx, self)
        est.done.put({"id": self.id, "estensione": self.nome, "chi": self.persona,
                      "chi_nome": self.persona_nome, "stato": "in_attesa",
                      "messaggio": q["risposta_finale"], "in_sospeso": q["in_sospeso"]})
        if est.on_done:
            est.on_done()
        threading.Thread(target=self._aspetta, args=(esito,), daemon=True,
                         name=f"gioco-azione-{self.id}").start()
        return {"ok": True, "in_attesa": True, "domanda": esito.get("domanda")}

    def _aspetta(self, esito: dict):
        est = self.giochi.estensioni
        fine = time.monotonic() + float(getattr(est, "conferma_s", 120.0))
        with self._cambio:
            while self._decisione is None and self.stato == "in_attesa":
                resto = fine - time.monotonic()
                if resto <= 0:
                    break
                self._cambio.wait(resto)
            dec = self._decisione
        out = est.porta.dopo_conferma(self, self.azione, self.params, esito, dec)
        self._fine(out)
        r = self._per_pagina(out)
        self.giochi.manda_a(self.partita, self.posto, "risposta",
                            {"rif": self.rif, **{k: v for k, v in r.items() if k != "_stato"}})

    def _fine(self, out: dict):
        self.partita.contaminazione |= set(self.storia.contaminazione)
        with self._cambio:
            if "errore" in out:
                self.stato, self.errore = "errore", str(out["errore"])[:300]
            else:
                self.stato = "finita"
                self.risultato = {"da_dire": ""}
            self._cambio.notify_all()

    @staticmethod
    def _per_pagina(out: dict) -> dict:
        if "errore" in out:
            return {"ok": False, "errore": str(out["errore"])[:300]}
        ris = out.get("risultato")
        return {"ok": True, "valore": ris}

    # ── come Esecuzione, per estensioni_gestisci consenti/nega ──
    def attendi(self, timeout: float) -> str:
        fine = time.monotonic() + timeout
        with self._cambio:
            while self.stato == "in_corso":
                resto = fine - time.monotonic()
                if resto <= 0:
                    break
                self._cambio.wait(resto)
            return self.stato

    def decidi(self, si: bool, chi=None, sempre: bool = False) -> bool:
        with self._cambio:
            if self.stato != "in_attesa" or self.richiesta is None:
                return False
            self._decisione = {"si": bool(si), "chi": chi, "sempre": bool(sempre)}
            self.stato = "in_corso"
            self.richiesta = None
            self._cambio.notify_all()
            return True

    def annulla(self):
        with self._cambio:
            if self.stato in ("in_corso", "in_attesa"):
                self.stato = "negata"
                self.errore = "annullata"
                self._cambio.notify_all()
