"""
La stanza sul server (13/10, conversazione di stanza, **passo 1: in ombra, sola trascrizione
veloce**; progetto docs/ricerche/2026-10-13-conversazione-di-stanza.md § 3.1–3.3, § 3.5 ter,
§ 3.10, § 3.11, § 6; decisione 0029).

`Stanza` riceve dai satelliti (protocollo 3: `stanza_inizio`, b"R", `stanza_fine`) i segmenti
di parlato della stanza, li trascrive in **una corsia veloce a bassa precedenza** (stanza/coda.py:
turno > recupero > stanza > lenta), attribuisce chi parla con CAM++ e scrive le righe nel
registro della stanza del satellite (stanza/registro.py, in memoria). **Niente arriva al
modello** in questo passo: si misura (stanza/misure.py, `calliope stato --turni`).

- **Audio solo in RAM**, il tempo di trascriverlo: poi si butta (decisione 0029 punto 1).
- **Legame con i turni**: un segmento che il satellite ha segnato con l'ascolto dei comandi
  (`ascolto`) non si trascrive (niente doppio Whisper): la riga la scrive il ciclo con il testo
  del turno (`turno_testo`), «rivolta: sì».
- **Niente segmenti nuovi mentre qualcuno parla a Calliope** (audio b"A" negli ultimi
  `COMANDO_S`) né mentre una frase di un turno aspetta Whisper: la prima frase non cambia (è la
  misura più importante). Si trascrivono solo quelli del **recupero**.
- **All'interpellazione si recupera prima** (§ 3.11): quando un satellite comincia a mandare una
  frase dei comandi, i suoi segmenti detti prima passano davanti agli altri della stanza (dopo
  la frase del turno). Il ciclo, a frase trascritta, chiede la **copertura** (`copertura`):
  quante righe dette prima della domanda sono già pronte, e quanto ci mette il resto.
- **Presenza** per persona (§ 3.5 ter): la voce riconosciuta sopra soglia su un satellite apre o
  allunga la presenza lì; sentita su un altro satellite, quella di prima si chiude (evento
  `presenza` con inizio e fine) e si conta il cambio di stanza; dopo `stanza_presenza_s` senza
  sentirla si chiude da sola.
- **Pausa e ospiti** (§ 3.10, tool `stanza_pausa`): la stanza di quel satellite si ferma per un
  tempo (ospiti: `stanza_ospiti_ore`, 4 h) o finché non si riprende; il satellite lo sa subito
  (messaggio `stanza`), gli schermi della stanza lo mostrano.
- **«Dimentica»** svuota il registro della stanza del satellite e butta i segmenti in coda.
- **Durante la voce** (14/10, passo 5, `stanza_durante_voce`): i segmenti detti mentre Calliope
  parla arrivano segnati con le frasi che suonavano (`durante_voce`); le frasi (testo e durata)
  sono quelle mandate al satellite (`Collegamento.frasi_voce`) e l'ora in cui hanno cominciato a
  suonare (`suonate`). Alla trascrizione il filtro dell'eco (stanza/eco.py, regola `eco_stanza`)
  toglie le parole che sono la sua voce; la riga tutta eco è scartata («eco»). Cancello per
  satellite: con l'eco misurata sul saluto oltre `barge_in_echo_max` (casse senza cancellazione)
  quel satellite resta half-duplex anche per la stanza.
"""

import collections
import datetime
import threading
import time

import numpy as np

from . import coda as coda_mod
from . import eco as eco_mod
from .registro import (ANALISI, DETTO_CALLIOPE, PAUSA, PRESENZA, PRESENZA_INIZIO, RIGA,
                       RIGA_SCARTATA, RIPRESA, SCAMBIO_APERTO, SCAMBIO_CHIUSO, SEGMENTO,
                       RegistroStanza)

SPENTA, OMBRA = "spenta", "ombra"
COMANDO_S = 0.6               # audio dei comandi così recente: qualcuno sta parlando a Calliope
COPERTURA_FINESTRA_S = 120.0  # le righe dette entro questo tempo prima della domanda
SEGMENTO_MAX_BYTE = 2 * 16000 * 70     # oltre ~70 s un segmento è rotto: si taglia
RECENTI_MAX = 400


def modo(cfg) -> str:
    m = str(getattr(cfg, "stanza", SPENTA) or SPENTA).strip().lower()
    return m if m in (SPENTA, OMBRA) else SPENTA


def _ora_breve(epoch: float) -> str:
    return datetime.datetime.fromtimestamp(epoch).strftime("%H:%M")


class Segmento:
    __slots__ = ("sat", "nome", "canale", "id", "pezzi", "byte", "inizio", "fine", "chiuso",
                 "voce_s", "durata_s", "ascolto", "stato", "fatto", "recupero", "riga",
                 "scambio", "inizio_epoch", "fine_epoch", "esito", "durante", "dette",
                 "detto_nuove", "chiusura")

    def __init__(self, sat, nome, canale, ident, inizio):
        self.sat, self.nome, self.canale, self.id = sat, nome, canale, ident
        self.pezzi, self.byte = [], 0
        self.inizio, self.fine, self.chiuso = inizio, None, None     # monotonic di qui
        self.voce_s = self.durata_s = 0.0
        self.ascolto = None
        self.stato = "in_arrivo"               # in_arrivo | in_coda | in_corso | fatto
        self.fatto = None
        self.recupero = False
        self.riga = None
        self.scambio = None
        self.inizio_epoch = self.fine_epoch = None
        self.esito = None                      # «riga», o il motivo dello scarto
        self.durante = None                    # passo 5: id delle frasi che suonavano
        self.dette = None                      # le frasi di Calliope di quell'intervallo
        self.detto_nuove = 0                   # le loro parole non ancora contate (misure)
        self.chiusura = None                   # silenzio, pausa_breve (taglio morbido), lunga


class Copertura:
    """La copertura all'interpellazione di un turno (§ 3.11): le righe della stanza dette prima
    della domanda, già pronte alla domanda, e quando lo sono diventate tutte."""

    def __init__(self, stanza: "Stanza", segmenti: list, tetto_s: float):
        self._stanza, self._seg, self.tetto_s = stanza, segmenti, tetto_s
        self.t0 = time.monotonic()
        self.dette = len(segmenti)
        self.pronte = sum(1 for s in segmenti if s.stato == "fatto")
        # Passo 2 (14/10): quante sono finite nel blocco della stanza dei dati del turno, quante
        # non avevano niente da dire (scartate), quanto si è aspettato il recupero
        self.nel_contesto: int | None = None
        self.scartate: int | None = None
        self.attesa_ms: int | None = None

    def mancano(self) -> int:
        return sum(1 for s in self._seg if s.stato != "fatto")

    def aspetta(self, fino: float) -> int:
        """Prima del blocco della stanza (passo 2): aspetta che le righe dette prima della
        domanda siano trascritte, al più fino all'istante `fino` (monotonic). I ms aspettati."""
        t0 = time.monotonic()
        with self._stanza._cond:
            while any(s.stato != "fatto" for s in self._seg):
                resto = fino - time.monotonic()
                if resto <= 0:
                    break
                self._stanza._cond.wait(min(resto, 0.1))
        self.attesa_ms = int((time.monotonic() - t0) * 1000)
        return self.attesa_ms

    def nel_blocco(self, segmenti: set):
        """Le righe dette prima della domanda che il blocco contiene (per id del segmento)."""
        self.nel_contesto = sum(1 for s in self._seg if s.id in segmenti)
        self.scartate = sum(1 for s in self._seg if s.stato == "fatto"
                            and s.esito not in (None, "riga"))

    def a_dict(self) -> dict:
        """Al momento di scrivere il turno: `recupero_ms` 0 se erano tutte pronte, il tempo per
        finirle se sono finite, None se no (`in_coda`: quante mancano ancora)."""
        mancano = [s for s in self._seg if s.stato != "fatto"]
        if not self.dette or self.pronte == self.dette:
            rec = 0
        elif not mancano:
            rec = int(max(0.0, max(s.fatto for s in self._seg if s.fatto) - self.t0) * 1000)
        else:
            rec = None
        out = {"dette": self.dette, "pronte": self.pronte, "recupero_ms": rec,
               "oltre": (rec is None or rec > self.tetto_s * 1000) if self.dette else False}
        if mancano:
            out["in_coda"] = len(mancano)
        if self.nel_contesto is not None:
            out["nel_contesto"] = self.nel_contesto
            out["scartate"] = self.scartate or 0
            out["attesa_ms"] = self.attesa_ms or 0
        return out


class Stanza:
    def __init__(self, cfg, stt, registry=None, misure=None, log=print):
        self.cfg, self.stt, self.registry, self.log = cfg, stt, registry, log
        self.misure = misure
        self.server = None                     # ServerSatelliti (per lo stato ai satelliti)
        self.schermi = None                    # hub degli schermi (il segno «ascolto la stanza»)
        self._cond = threading.Condition()
        self._registri: dict = {}              # sat → RegistroStanza
        self._info: dict = {}                  # sat → {nome, stanza, canale}
        self._in_arrivo: dict = {}             # (sat, id) → Segmento
        self._coda: list[Segmento] = []
        self._recenti: dict = {}               # sat → deque dei segmenti chiusi (copertura)
        self._legati: dict = {}                # (sat, ascolto) → Segmento legato a un turno
        self._comando: dict = {}               # sat → monotonic dell'ultimo audio b"A"
        self._recupero: dict = {}              # sat → monotonic: i segmenti chiusi prima
        self._pause: dict = {}                 # sat → {motivo, fino (epoch o None)}
        self._scambio: dict = {}               # sat → (numero, monotonic dell'ultimo segmento)
        self._presenti: dict = {}              # persona → {sat, nome, inizio, ultimo}
        self._intervalli = collections.deque(maxlen=2000)   # (persona, sat, inizio, fine)
        self._n_scambi = 0
        self._detto_contate: dict = {}         # sat → id delle frasi già contate (misure eco)
        self._fermo = threading.Event()
        self._thread = threading.Thread(target=self._lavora, name="stanza-veloce", daemon=True)
        self._thread.start()
        self.trascritti = 0

    # ── configurazione ──
    def accesa_per(self, satellite: dict) -> bool:
        """La stanza è accesa per questo satellite nel file di configurazione: `stanza: ombra`
        e il suo nome in `stanza_satelliti` (vuoto = tutti)."""
        if modo(self.cfg) == SPENTA:
            return False
        nomi = [str(n).strip().lower() for n in (getattr(self.cfg, "stanza_satelliti", None)
                                                  or []) if str(n).strip()]
        return not nomi or str(satellite.get("nome") or "").strip().lower() in nomi

    def stato_per(self, satellite: dict) -> dict:
        """Lo stato da mandare al satellite (benvenuto e messaggio `stanza`)."""
        if not self.accesa_per(satellite):
            return {"attiva": False, "motivo": "spenta"}
        p = self._pausa_viva(satellite.get("id"))
        seg = float(getattr(self.cfg, "stanza_segmento_max_s", 20.0) or 20.0)
        if p is not None:
            return {"attiva": False, "motivo": p["motivo"], "fino": p["fino"],
                    "segmento_max_s": seg}
        c = self.cfg
        return {"attiva": True, "motivo": None, "fino": None, "segmento_max_s": seg,
                "taglio_zona_s": float(getattr(c, "stanza_taglio_zona_s", 4.0)),
                "pausa_breve_ms": int(getattr(c, "stanza_pausa_breve_ms", 160) or 160),
                "tetto_duro_s": float(getattr(c, "stanza_tetto_duro_s", 5.0)),
                "durante_voce": self.durante_qui(satellite.get("id"))}

    # ── durante la voce (passo 5) ──
    def _cancello(self, sat) -> bool:
        """Il cancello per satellite (§ 5.3 c): l'eco misurata sul saluto oltre
        `barge_in_echo_max` (casse senza cancellazione) chiude l'ascolto durante la voce. Un'eco
        non misurata (niente saluto, telefono) lo lascia aperto: il filtro resta."""
        coll = None
        if self.server is not None:
            try:
                coll = self.server.per_id(sat)
            except Exception:  # noqa: BLE001
                coll = None
        e = getattr(coll, "eco", None) if coll is not None else None
        try:
            return e is not None and float(e) > float(getattr(self.cfg, "barge_in_echo_max",
                                                              0.05))
        except (TypeError, ValueError):
            return False

    def durante_qui(self, sat) -> bool:
        """La stanza di questo satellite ascolta anche mentre Calliope parla."""
        return bool(getattr(self.cfg, "stanza_durante_voce", False)) and not self._cancello(sat)

    def pronto(self, coll):
        """Il satellite ha detto il saluto (l'eco è misurata): lo stato di nuovo, col
        cancello dell'ascolto durante la voce."""
        sat = coll.satellite.get("id")
        if not getattr(self.cfg, "stanza_durante_voce", False) or sat not in self._info:
            return
        if self._cancello(sat):
            self.log(f"   [STANZA] {coll.satellite.get('nome')}: eco sul saluto oltre "
                     f"{self.cfg.barge_in_echo_max:.2f}, la stanza non ascolta mentre parlo")
        self._annuncia(sat)

    def _dette(self, coll, s: "Segmento") -> list:
        """Le frasi di Calliope dell'intervallo del segmento: quelle che il satellite ha
        segnato e quelle che, per l'ora in cui hanno cominciato a suonare, ci cadono dentro
        (con la tolleranza e la coda dell'eco). Con il conto delle parole nuove per le misure."""
        frasi = dict(getattr(coll, "frasi_voce", None) or {})
        suonate = dict(getattr(coll, "suonate", None) or {})
        ids = {i for i in (s.durante or ()) if i in frasi}
        tol = eco_mod.TOLLERANZA_S
        for fid, (_testo, dur) in frasi.items():
            t0 = suonate.get(fid)
            if t0 is None or s.fine is None:
                continue
            if t0 - tol <= s.fine and t0 + dur + eco_mod.CODA_S + tol >= s.inizio:
                ids.add(fid)
        ora_m, ora_e = time.monotonic(), time.time()
        out = []
        contate = self._detto_contate.setdefault(s.sat, set())
        for fid in sorted(ids):
            testo, dur = frasi[fid]
            t0 = suonate.get(fid)
            out.append(eco_mod.Detta(testo, None if t0 is None else ora_e - (ora_m - t0), dur))
            if fid not in contate:
                contate.add(fid)
                s.detto_nuove += len(eco_mod.parole(testo))
        if len(contate) > 600:
            for k in sorted(contate)[:300]:
                contate.discard(k)
        return out

    def _pausa_viva(self, sat):
        p = self._pause.get(sat)
        if p is not None and p.get("fino") is not None and p["fino"] <= time.time():
            return None
        return p

    def registro(self, sat) -> RegistroStanza:
        with self._cond:
            r = self._registri.get(sat)
            if r is None:
                nome = (self._info.get(sat) or {}).get("nome") or str(sat)
                r = self._registri[sat] = RegistroStanza(f"stanza:{sat}", nome)
            return r

    # ── dal server dei satelliti (thread della connessione) ──
    def collegato(self, coll):
        sat = coll.satellite.get("id")
        with self._cond:
            self._info[sat] = {"nome": coll.satellite.get("nome") or str(sat),
                               "stanza": coll.stanza, "canale": coll.canale}
        self._segno(sat)

    def scollegato(self, coll):
        sat = coll.satellite.get("id")
        with self._cond:
            via = [k for k in self._in_arrivo if k[0] == sat]
            segs = [self._in_arrivo.pop(k) for k in via]
        for s in segs:
            self._misura("buttato", sat=s.nome, canale=s.canale, motivo="scollegato",
                         voce_s=round(s.voce_s, 2))
        altro = None
        if self.server is not None:
            try:
                altro = self.server.per_id(sat)
            except Exception:  # noqa: BLE001
                altro = None
        # Una riconnessione dello stesso satellite: il segno resta (è già quello nuovo)
        self._segno(sat, via=altro is None or altro is coll)

    def voce_comando(self, coll):
        """Un pezzo di audio dei comandi (b"A"): qualcuno sta parlando a Calliope da questo
        satellite. Alla prima volta di una frase, i segmenti detti prima vanno in recupero."""
        sat = coll.satellite.get("id")
        ora = time.monotonic()
        with self._cond:
            prima = self._comando.get(sat, 0.0)
            self._comando[sat] = ora
            if ora - prima > 1.0:
                self._recupero[sat] = ora
                for s in self._coda:
                    if s.sat == sat and s.fine is not None and s.fine <= ora:
                        s.recupero = True
                self._cond.notify_all()

    def inizio(self, coll, m: dict):
        sat = coll.satellite.get("id")
        if not self.accesa_per(coll.satellite) or self._pausa_viva(sat) is not None:
            return
        try:
            ident = int(m.get("id"))
            fa = min(60.0, max(0.0, float(m.get("fa_s") or 0.0)))
        except (TypeError, ValueError):
            return
        ora = time.monotonic()
        s = Segmento(sat, coll.satellite.get("nome") or str(sat), coll.canale, ident,
                     ora - fa - coll.ritardo())
        s.inizio_epoch = time.time() - (ora - s.inizio)
        with self._cond:
            self._info.setdefault(sat, {"nome": s.nome, "stanza": coll.stanza,
                                        "canale": coll.canale})
            self._in_arrivo[(sat, ident)] = s

    def pezzo(self, coll, ident: int, pcm: bytes):
        sat = coll.satellite.get("id")
        with self._cond:
            s = self._in_arrivo.get((sat, ident))
            if s is None:
                return
            if s.byte + len(pcm) > SEGMENTO_MAX_BYTE:
                return
            s.pezzi.append(pcm)
            s.byte += len(pcm)

    def fine(self, coll, m: dict):
        sat = coll.satellite.get("id")
        try:
            ident = int(m.get("id"))
        except (TypeError, ValueError):
            return
        with self._cond:
            s = self._in_arrivo.pop((sat, ident), None)
        if s is None:
            return
        chiusura = str(m.get("chiusura") or "")
        dv = m.get("durante_voce")
        if isinstance(dv, list) and dv:
            s.durante = sorted({int(x) for x in dv[:50]
                                if isinstance(x, int) and not isinstance(x, bool)})
        try:
            s.voce_s = min(120.0, max(0.0, float(m.get("parlato_ms") or 0) / 1000))
            s.durata_s = min(120.0, max(0.0, float(m.get("durata_s") or 0)))
        except (TypeError, ValueError):
            s.voce_s = s.durata_s = 0.0
        ora = time.monotonic()
        s.chiuso = ora
        s.chiusura = chiusura
        # La fine del parlato: prima del silenzio che l'ha chiuso (o della micro-pausa)
        coda_s = (float(self.cfg.silence_ms) / 1000 if chiusura == "silenzio" else
                  float(getattr(self.cfg, "stanza_pausa_breve_ms", 160) or 0) / 1000
                  if chiusura == "pausa_breve" else 0.0)
        s.fine = ora - coda_s - coll.ritardo()
        s.fine_epoch = time.time() - (ora - s.fine)
        if chiusura not in ("silenzio", "pausa_breve", "lunga"):
            self._misura("buttato", sat=s.nome, canale=s.canale,
                         motivo=chiusura or "?", voce_s=round(s.voce_s, 2))
            return
        if s.durante is not None and not self.durante_qui(sat):
            # Detto durante la voce, ma qui la stanza non ascolta mentre Calliope parla (spento
            # nel file o cancello dell'eco): come prima del passo 5, il segmento si butta
            self._misura("buttato", sat=s.nome, canale=s.canale,
                         motivo="eco_cancello" if self._cancello(sat) else "voce",
                         voce_s=round(s.voce_s, 2))
            return
        if self.durante_qui(sat):
            try:
                s.dette = self._dette(coll, s) or None
            except Exception:  # noqa: BLE001 — senza frasi il segmento resta com'è
                s.dette = None
        asc = m.get("ascolto")
        if isinstance(asc, int) and not isinstance(asc, bool):
            s.ascolto = asc
        self._apri_scambio(s)
        reg = self.registro(sat)
        with self._cond:
            rec = self._recenti.setdefault(sat, collections.deque(maxlen=RECENTI_MAX))
            rec.append(s)
            if s.ascolto is not None:
                # Legato a un turno: il testo lo dà il ciclo (niente doppio Whisper)
                s.stato, s.fatto, s.pezzi = "fatto", ora, []
                self._legati[(sat, s.ascolto)] = s
                while len(self._legati) > 200:
                    self._legati.pop(next(iter(self._legati)))
            else:
                if sat in self._recupero and s.fine <= self._recupero[sat]:
                    s.recupero = True
                s.stato = "in_coda"
                self._coda.append(s)
                self._taglia_coda()
                self._cond.notify_all()
        reg.aggiungi(SEGMENTO, scambio=s.scambio, segmento=s.id, inizio=round(s.inizio_epoch, 3),
                     fine=round(s.fine_epoch, 3), voce_s=round(s.voce_s, 2), durante_voce=s.durante,
                     turno=s.ascolto, wake=s.ascolto is not None)
        if s.ascolto is not None:
            self._misura("segmento", sat=s.nome, canale=s.canale, voce_s=round(s.voce_s, 2),
                         durata_s=round(s.durata_s, 2), byte=s.byte, esito="legato",
                         chiusura=s.chiusura)

    def _taglia_coda(self):
        """Con il lock: oltre `stanza_coda_max_s` di audio in coda si buttano i più vecchi (non
        quelli del recupero)."""
        tetto = float(getattr(self.cfg, "stanza_coda_max_s", 600.0) or 600.0)
        while sum(x.durata_s for x in self._coda) > tetto:
            vecchi = [x for x in self._coda if not x.recupero]
            if not vecchi:
                break
            x = vecchi[0]
            self._coda.remove(x)
            x.stato, x.fatto, x.pezzi, x.esito = "fatto", time.monotonic(), [], "coda_piena"
            self._misura("buttato", sat=x.nome, canale=x.canale, motivo="coda_piena",
                         voce_s=round(x.voce_s, 2))

    def _apri_scambio(self, s: Segmento):
        """Lo scambio del segmento: quello aperto, o uno nuovo dopo `stanza_scambio_pausa_s` di
        silenzio (e quello di prima si chiude)."""
        pausa = float(getattr(self.cfg, "stanza_scambio_pausa_s", 300.0) or 300.0)
        reg = self.registro(s.sat)
        with self._cond:
            n, ultimo = self._scambio.get(s.sat, (None, 0.0))
            prima = None
            if n is None or s.inizio - ultimo > pausa:
                prima = n
                self._n_scambi += 1
                n = self._n_scambi
                nuovo = True
            else:
                nuovo = False
            self._scambio[s.sat] = (n, s.chiuso)
        if prima is not None:
            reg.aggiungi(SCAMBIO_CHIUSO, scambio=prima, motivo="silenzio")
        if nuovo:
            reg.aggiungi(SCAMBIO_APERTO, scambio=n, satellite=s.nome)
        s.scambio = n

    # ── dal ciclo ──
    def copertura(self, sat, inizio_turno: float) -> Copertura | None:
        """Al momento in cui la frase del turno è trascritta: le righe della stanza di `sat`
        dette (chiuse dal VAD) prima dell'inizio della frase, negli ultimi
        COPERTURA_FINESTRA_S. None se la stanza non è accesa lì."""
        with self._cond:
            if sat not in self._info:
                return None
            segs = [s for s in self._recenti.get(sat, ())
                    if s.ascolto is None and s.fine is not None
                    and inizio_turno - COPERTURA_FINESTRA_S <= s.fine < inizio_turno - 0.05]
            for s in segs:
                if s.stato != "fatto":
                    s.recupero = True
            self._recupero[sat] = max(self._recupero.get(sat, 0.0), inizio_turno)
            self._cond.notify_all()
        return Copertura(self, segs,
                         float(getattr(self.cfg, "stanza_recupero_max_s", 1.5) or 1.5))

    def turno_testo(self, sat, ascolto, testo: str, chi: dict | None = None,
                    inizio: float | None = None, fine: float | None = None):
        """La frase di un turno (rivolta a Calliope) entra nella stanza di quel satellite, con
        il testo del turno: lega il segmento della stanza che la copre, se c'è. `chi`:
        {persona, nome, sicurezza («voce», «grigia», «nessuna»), minore}. Il `seq` della riga
        (per `segna_rivolta`), o None."""
        if sat not in self._info or self._pausa_viva(sat) is not None:
            return None                        # in pausa (ospiti): nemmeno le frasi dei turni
        with self._cond:
            s = self._legati.pop((sat, ascolto), None) if ascolto is not None else None
        chi = chi or {}
        t_ini = s.inizio_epoch if s is not None else inizio
        t_fin = s.fine_epoch if s is not None else fine
        e = self.registro(sat).aggiungi(
            RIGA, segmento=s.id if s is not None else None, versione=1,
            inizio=round(t_ini or time.time(), 3), fine=round(t_fin or time.time(), 3),
            testo=str(testo or ""), chi=chi.get("chi") or "ignoto", nome=chi.get("nome"),
            sicurezza=chi.get("sicurezza") or "nessuna", p_min=None, rivolta="si",
            minore=bool(chi.get("minore")))
        if chi.get("sicurezza") == "voce" and chi.get("persona"):
            self._sentita(chi["persona"], chi.get("nome"), sat, time.time())
        return e.seq

    def segna_rivolta(self, sat, seq, esito: str, giudizio=None):
        """Passo 2 (14/10): la frase di un turno ignorata o non rivolta resta nella stanza, con
        «rivolta: no» (un evento `analisi` che rimanda alla riga: in sola aggiunta). `giudizio`:
        il giudizio «rivolta» in compagnia (True, False, None), per la rilettura."""
        if seq is None or sat not in self._info:
            return
        reg = self.registro(sat)
        if not any(e.seq == seq for e in reg.eventi(RIGA)):
            return                             # dimenticata o uscita per la tenuta
        reg.aggiungi(ANALISI, analisi="rivolta", riga=seq, esito=esito, giudizio=giudizio)

    def detto(self, sat, testo: str, inizio: float | None = None, fine: float | None = None):
        """Passo 2 (14/10): ciò che Calliope ha detto ad alta voce vicino al satellite (la
        risposta di un turno), perché la stanza sappia anche le sue righe. Non in pausa."""
        testo = " ".join(str(testo or "").split())
        if not testo or sat not in self._info or self._pausa_viva(sat) is not None:
            return
        ora = time.time()
        self.registro(sat).aggiungi(DETTO_CALLIOPE, testo=testo[:2000],
                                    inizio=round(inizio or ora, 3), fine=round(fine or ora, 3))

    def accesa_qui(self, sat) -> bool:
        """La stanza ascolta adesso su questo satellite: accesa nel file e non in pausa."""
        info = self._info.get(sat)
        return (info is not None and self.accesa_per({"id": sat, "nome": info.get("nome")})
                and self._pausa_viva(sat) is None)

    def dimentica(self, sat) -> int:
        """«Dimentica»: il registro della stanza del satellite si svuota e i suoi segmenti in
        coda si buttano. Restituisce quanti eventi c'erano."""
        with self._cond:
            via = [s for s in self._coda if s.sat == sat]
            for s in via:
                self._coda.remove(s)
                s.stato, s.fatto, s.pezzi, s.esito = "fatto", time.monotonic(), [], "dimentica"
            for k in [k for k in self._legati if k[0] == sat]:
                self._legati.pop(k)
            self._scambio.pop(sat, None)
        n = self.registro(sat).svuota()
        nome = (self._info.get(sat) or {}).get("nome") or str(sat)
        self._misura("dimentica", sat=nome, eventi=n)
        self.log(f"   [STANZA] {nome}: registro della stanza svuotato ({n} eventi)")
        return n

    # ── pausa e ospiti (tool stanza_pausa) ──
    def pausa(self, sat, motivo: str = "pausa", minuti: float | None = None) -> dict:
        fino = time.time() + float(minuti) * 60 if minuti else None
        with self._cond:
            self._pause[sat] = {"motivo": motivo, "fino": fino}
            via = [k for k in self._in_arrivo if k[0] == sat]
            for k in via:
                self._in_arrivo.pop(k)
        reg = self.registro(sat)
        n, _ = self._scambio.get(sat, (None, 0.0))
        if n is not None:
            reg.aggiungi(SCAMBIO_CHIUSO, scambio=n, motivo=motivo)
            self._scambio.pop(sat, None)
        reg.aggiungi(PAUSA, motivo=motivo, fino=fino)
        nome = (self._info.get(sat) or {}).get("nome") or str(sat)
        self._misura("pausa", sat=nome, motivo=motivo,
                     ore=round(float(minuti) / 60, 2) if minuti else None)
        self.log(f"   [STANZA] {nome}: ascolto della stanza in pausa ({motivo}"
                 + (f", fino alle {_ora_breve(fino)})" if fino else ")"))
        self._annuncia(sat)
        return {"fino": fino, "motivo": motivo}

    def riprendi(self, sat) -> bool:
        with self._cond:
            p = self._pause.pop(sat, None)
        if p is None:
            return False
        self.registro(sat).aggiungi(RIPRESA, motivo=p.get("motivo"))
        nome = (self._info.get(sat) or {}).get("nome") or str(sat)
        self.log(f"   [STANZA] {nome}: ascolto della stanza ripreso")
        self._annuncia(sat)
        return True

    def stato_pausa(self, sat) -> dict | None:
        return self._pausa_viva(sat)

    def _annuncia(self, sat):
        """Lo stato nuovo al satellite (messaggio `stanza`) e agli schermi della sua stanza."""
        srv = self.server
        if srv is not None:
            try:
                coll = srv.per_id(sat)
            except Exception:  # noqa: BLE001
                coll = None
            if coll is not None and getattr(coll, "stanza_capace", False):
                coll.invia(tipo="stanza", **self.stato_per(coll.satellite))
        self._segno(sat)

    def _segno(self, sat, via: bool = False):
        """Il segno sugli schermi della stanza del satellite: «Ascolto la stanza», «Stanza in
        pausa: ospiti, fino alle 22:15», o niente."""
        hub, info = self.schermi, self._info.get(sat)
        if hub is None or info is None or not hasattr(hub, "stanza_segno"):
            return
        testo = None
        if not via and self.accesa_per({"id": sat, "nome": info.get("nome")}):
            p = self._pausa_viva(sat)
            if p is None:
                testo = "Ascolto la stanza"
            else:
                testo = ("Stanza in pausa: ospiti" if p["motivo"] == "ospiti"
                         else "Ascolto della stanza in pausa")
                if p.get("fino"):
                    testo += f", fino alle {_ora_breve(p['fino'])}"
        try:
            hub.stanza_segno(info.get("stanza") or "", f"sat:{sat}", testo)
        except Exception:  # noqa: BLE001 — il segno non ferma la stanza
            pass

    # ── presenza (§ 3.5 ter) ──
    def _sentita(self, persona, nome, sat, t: float):
        presenza_s = float(getattr(self.cfg, "stanza_presenza_s", 600.0) or 600.0)
        chiudi, apri, cambio = None, False, None
        with self._cond:
            p = self._presenti.get(persona)
            if p is not None and p["sat"] == sat and t - p["ultimo"] <= presenza_s:
                p["ultimo"] = t
            else:
                if p is not None:
                    chiudi = p
                    # Nell'elenco degli intervalli dentro il lock (14/10): fuori, una ricerca
                    # in quell'istante non vedeva la presenza né aperta né chiusa
                    self._intervalli.append((persona, p["sat"], p["inizio"], p["ultimo"]))
                    if p["sat"] != sat:
                        cambio = (p["sat"], t - p["ultimo"])
                self._presenti[persona] = {"sat": sat, "nome": nome, "inizio": t, "ultimo": t}
                apri = True
        if chiudi is not None:
            self._chiudi_presenza(persona, chiudi)
        if apri:
            self.registro(sat).aggiungi(PRESENZA_INIZIO, persona=persona, nome=nome)
        if cambio is not None:
            da = (self._info.get(cambio[0]) or {}).get("nome") or str(cambio[0])
            a = (self._info.get(sat) or {}).get("nome") or str(sat)
            self._misura("cambio_stanza", persona=persona, da=da, a=a, dopo_s=round(cambio[1], 1))

    def _chiudi_presenza(self, persona, p: dict):
        self.registro(p["sat"]).aggiungi(PRESENZA, persona=persona, nome=p.get("nome"),
                                         inizio=round(p["inizio"], 3), fine=round(p["ultimo"], 3))
        nome = (self._info.get(p["sat"]) or {}).get("nome") or str(p["sat"])
        self._misura("presenza", persona=persona, sat=nome,
                     durata_s=round(p["ultimo"] - p["inizio"], 1))

    def presenti(self, sat) -> list[dict]:
        """Chi è presente adesso vicino al satellite (voce sopra soglia negli ultimi
        `stanza_presenza_s`)."""
        presenza_s = float(getattr(self.cfg, "stanza_presenza_s", 600.0) or 600.0)
        ora = time.time()
        with self._cond:
            return [{"persona": k, "nome": v.get("nome"), "dal": v["inizio"]}
                    for k, v in self._presenti.items()
                    if v["sat"] == sat and ora - v["ultimo"] <= presenza_s]

    def presenze(self, persona) -> list[tuple]:
        """Gli intervalli (satellite, inizio, fine) in cui la persona era presente, compreso
        quello aperto: per «quello che dicevamo di là» (passo 2 e 4)."""
        with self._cond:
            out = [(s, a, b) for p, s, a, b in self._intervalli if p == persona]
            v = self._presenti.get(persona)
            if v is not None:
                out.append((v["sat"], v["inizio"], v["ultimo"]))
        return out

    def _scadenze(self):
        presenza_s = float(getattr(self.cfg, "stanza_presenza_s", 600.0) or 600.0)
        ora = time.time()
        with self._cond:
            vecchie = [(k, v) for k, v in self._presenti.items()
                       if ora - v["ultimo"] > presenza_s]
            for k, v in vecchie:
                self._presenti.pop(k)
                self._intervalli.append((k, v["sat"], v["inizio"], v["ultimo"]))
            pause = [k for k, p in self._pause.items()
                     if p.get("fino") is not None and p["fino"] <= ora]
        for k, v in vecchie:
            self._chiudi_presenza(k, v)
        for sat in pause:
            self.riprendi(sat)
        for r in list(self._registri.values()):
            r.pota()

    # ── la corsia veloce ──
    def _scegli(self) -> Segmento | None:
        """Con il lock: il prossimo segmento, o None se ora non se ne comincia nessuno."""
        if not self._coda:
            return None
        rec = [s for s in self._coda if s.recupero]
        if rec:
            return min(rec, key=lambda s: s.fine)
        ora = time.monotonic()
        if any(ora - t < COMANDO_S for t in self._comando.values()):
            return None                       # qualcuno parla a Calliope: la stanza aspetta
        aspetta = getattr(self.stt, "aspetta_turno", None)
        if callable(aspetta) and aspetta():
            return None
        return self._coda[0]

    def _lavora(self):
        prossimo_tick = 0.0
        while not self._fermo.is_set():
            with self._cond:
                s = self._scegli()
                if s is None:
                    self._cond.wait(0.2)
                else:
                    self._coda.remove(s)
                    s.stato = "in_corso"
            if time.monotonic() >= prossimo_tick:
                prossimo_tick = time.monotonic() + 5.0
                try:
                    self._scadenze()
                except Exception as e:  # noqa: BLE001
                    self.log(f"   [STANZA] scadenze: {type(e).__name__}: {e}")
            if s is not None:
                try:
                    self._trascrivi(s)
                except Exception as e:  # noqa: BLE001 — un segmento non ferma la stanza
                    self.log(f"   [STANZA] segmento non trascritto: {type(e).__name__}: {e}")
                    self._fatto(s, None, "errore", 0.0, 0.0)

    def _trascrivi(self, s: Segmento):
        prio = coda_mod.RECUPERO if s.recupero else coda_mod.STANZA
        audio = np.frombuffer(b"".join(s.pezzi), dtype="<i2").astype(np.float32) / 32768.0
        s.pezzi = []                          # l'audio non resta (decisione 0029 punto 1)
        t0 = time.monotonic()
        attesa = t0 - (s.chiuso or t0)
        try:
            testo = self.stt.transcribe(audio, priorita=prio, prompt="")
        except TypeError:                     # un trascrittore senza precedenza (prove)
            testo = self.stt.transcribe(audio)
        stt_s = time.monotonic() - t0
        scartata = getattr(self.stt, "ultima_scartata", None)
        testo = (testo or "").strip()
        eco = self._eco_misure(s, None)
        if not testo:
            self._fatto(s, None, "allucinazione" if scartata else "vuota", attesa, stt_s, eco)
            return
        tolte = 0
        if s.dette:
            # Il filtro dell'eco (passo 5, regola eco_stanza): le parole che sono la sua voce
            e = eco_mod.filtra(testo, s.dette, s.inizio_epoch, s.fine_epoch,
                               nomi=getattr(self.cfg, "wake_names", None) or ())
            eco = self._eco_misure(s, e)
            if e.tutta_eco:
                self._fatto(s, None, "eco", attesa, stt_s, eco)
                return
            testo, tolte = e.testo, e.tolte
        chi = self._chi(audio, s.voce_s)
        s.esito = "riga"
        self.registro(s.sat).aggiungi(
            RIGA, segmento=s.id, scambio=s.scambio, versione=1,
            inizio=round(s.inizio_epoch or time.time(), 3),
            fine=round(s.fine_epoch or time.time(), 3), testo=testo, chi=chi["chi"],
            nome=chi.get("nome"), sicurezza=chi["sicurezza"], p_min=None, rivolta="ignoto",
            minore=chi.get("minore", False),
            **({"durante_voce": True, "eco_tolte": tolte} if s.durante or s.dette else {}))
        if chi["sicurezza"] == "voce":
            self._sentita(chi["persona"], chi.get("nome"), s.sat, s.fine_epoch or time.time())
        self._fatto(s, testo, None, attesa, stt_s, eco)

    @staticmethod
    def _eco_misure(s: Segmento, e) -> dict:
        """I numeri del filtro dell'eco per le misure (mai parole): solo per i segmenti detti
        durante la voce o vicini a una sua frase."""
        if not (s.durante or s.dette):
            return {}
        out = {"durante": True, "frasi": len(s.dette or ()), "detto_nuove": s.detto_nuove}
        if e is not None:
            out.update(parole=e.parole, eco_tolte=e.tolte, residua=e.residua,
                       regole=list(e.regole))
        return out

    def _fatto(self, s: Segmento, testo, motivo, attesa: float, stt_s: float,
               eco: dict | None = None):
        ora = time.monotonic()
        if testo is None and motivo is not None:
            s.esito = motivo
            self.registro(s.sat).aggiungi(RIGA_SCARTATA, segmento=s.id, motivo=motivo)
        with self._cond:
            s.stato, s.fatto = "fatto", ora
            self._cond.notify_all()
        self.trascritti += 1
        self._misura("segmento", sat=s.nome, canale=s.canale, voce_s=round(s.voce_s, 2),
                     durata_s=round(s.durata_s, 2), byte=s.byte,
                     esito="riga" if testo else "scartata", motivo=motivo,
                     attesa_s=round(attesa, 3), stt_s=round(stt_s, 3),
                     ritardo_s=round(ora - (s.chiuso or ora), 3), recupero=s.recupero,
                     chiusura=s.chiusura,
                     **(eco or {}))

    def _chi(self, audio, voce_s: float) -> dict:
        """Chi parla nel segmento (CAM++), con le regole di sempre: sopra soglia e con il
        margine dal secondo profilo «voce»; poco sotto «grigia»; altrimenti «nessuna». Mai
        verso l'alto: non cambia permessi né impronte."""
        reg, cfg = self.registry, self.cfg
        nessuno = {"chi": "ignoto", "nome": None, "sicurezza": "nessuna"}
        if reg is None or voce_s < float(getattr(cfg, "speaker_min_voice_s", 1.0) or 1.0):
            return nessuno
        try:
            emb = reg.embed(audio, cfg.sample_rate)
            classifica = list(reg.classifica(emb))
        except Exception:  # noqa: BLE001 — senza impronta, «ignoto»
            return nessuno
        if not classifica or classifica[0][1] <= 0:
            return nessuno
        nome, sim = classifica[0]
        sim2 = classifica[1][1] if len(classifica) > 1 else None
        thr = float(cfg.speaker_id_threshold)
        netta = sim2 is None or sim - sim2 >= float(getattr(cfg, "speaker_id_margine", 0.0))
        prof = reg.get(nome)
        pid = getattr(prof, "id", None) or nome
        try:
            from ..minori import e_minore
            minore = bool(prof is not None and e_minore(prof))
        except Exception:  # noqa: BLE001
            minore = False
        if sim >= thr and netta:
            return {"chi": f"persona:{pid}", "persona": pid, "nome": nome, "sicurezza": "voce",
                    "minore": minore}
        if sim >= thr - float(getattr(cfg, "speaker_id_session_margin", 0.08)):
            return {"chi": f"persona:{pid}", "persona": pid, "nome": nome,
                    "sicurezza": "grigia", "minore": minore}
        return nessuno

    def _misura(self, tipo: str, **campi):
        if self.misure is not None:
            try:
                self.misure.scrivi(tipo, **campi)
            except Exception:  # noqa: BLE001
                pass

    # ── stato (cruscotto, prove) ──
    def in_coda(self) -> int:
        with self._cond:
            return len(self._coda)

    def stato(self) -> dict:
        with self._cond:
            sats = dict(self._info)
        out = {}
        for sat, info in sats.items():
            r = self._registri.get(sat)
            out[info.get("nome") or str(sat)] = {
                "stanza": info.get("stanza"), "canale": info.get("canale"),
                "pausa": self._pausa_viva(sat), "eventi": len(r) if r is not None else 0,
                "righe": len(r.righe()) if r is not None else 0,
                "presenti": [p["nome"] for p in self.presenti(sat)]}
        return out

    def chiudi(self):
        self._fermo.set()
        with self._cond:
            self._cond.notify_all()
