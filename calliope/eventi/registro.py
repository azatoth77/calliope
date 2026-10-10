"""
Il registro degli eventi: uno per persona, uno anonimo per satellite (10/10/2026, § 2.3–2.6 del
progetto docs/ricerche/2026-10-10-registro-eventi.md).

- **Un registro per chiave** della conversazione di oggi (`corsie.RegistroConversazioni`):
  `persona:<id>` (una per persona, da qualunque satellite) o `ospite:<corsia>` (anonimo, uno per
  satellite). Nessun registro globale, nessuna API che legga gli eventi di più registri insieme:
  `Registri` dà un registro per volta.
- **In sola aggiunta**: `Registro.aggiungi` è l'unico modo di scrivere; `seq` lo assegna il
  registro sotto il suo lock (un solo scrittore per registro, § 2.6 a). Le conversazioni sono
  segmenti fra `conversazione_aperta` e `conversazione_chiusa`. In memoria restano il segmento
  aperto e l'ultimo chiuso (la coda).
- **Disco** (`Disco`): tabella `eventi` in `conversazioni.db`, partizionata per registro, scritta
  a lotti a fine turno nel thread dell'archivio (la voce non aspetta il disco). Un errore di
  scrittura si conta e si dice nel log; la conversazione continua.
- **Riavvio** (`Registri.riprendi`): i segmenti aperti e non scaduti si rigiocano dal disco; una
  riga rovinata chiude il rigioco di quel registro all'ultimo evento buono (`eventi_troncati`);
  una proposta aperta diventa `proposta_chiusa(persa_riavvio)`.
- **«Dimentica»** (`Disco.dimentica`, `Registri.dimentica`): `DELETE … WHERE registro = ?` con
  `secure_delete` e il checkpoint del WAL, e il registro in memoria svuotato (§ 2.6 f).
- **Porte** (§ 2.5): ciò che attraversa i registri passa da una funzione `porta_*` con un nome,
  che scrive un evento nuovo nel registro di destinazione (mai una copia di eventi).

Solo libreria standard e sqlite3.
"""
from __future__ import annotations

import threading
import time
import uuid

from .tipi import TIPI, Evento, EventoNonValido, controlla, da_riga, riga

# ─────────────────────────── disco ───────────────────────────
MODULO = "eventi"


def _v1(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS eventi (
            registro TEXT NOT NULL, seq INTEGER NOT NULL, conv TEXT NOT NULL, corsia TEXT,
            t REAL NOT NULL, tipo TEXT NOT NULL, turno INTEGER NOT NULL DEFAULT 0,
            vis TEXT NOT NULL, persona TEXT, ospite INTEGER NOT NULL DEFAULT 0,
            dati TEXT NOT NULL, v INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (registro, seq));
        CREATE INDEX IF NOT EXISTS eventi_t ON eventi(t);
        CREATE TABLE IF NOT EXISTS eventi_dimenticati (
            registro TEXT NOT NULL, quando REAL NOT NULL);
    """)


# Un modulo suo in meta_schema, nello stesso file dell'archivio: una versione di Calliope di prima
# (ritorno indietro di `calliope aggiorna`) non lo conosce e non se ne accorge
MIGRAZIONI = [_v1]


class Disco:
    """Gli eventi su disco, a lotti. `in_coda(f)`: chi esegue i lavori (il thread dell'archivio
    delle conversazioni); None = subito (prove)."""

    def __init__(self, db, lock=None, in_coda=None, log=print, scrivibile: bool = True):
        self.db = db
        self.lock = lock or threading.Lock()
        self.in_coda = in_coda
        self.log = log
        self.scrivibile = scrivibile
        self._da_scrivere: list[Evento] = []
        self._lock_lista = threading.Lock()
        self.errori = 0                  # lotti non scritti (disco pieno, sola lettura…)
        self.persi = 0                   # eventi non scritti
        self.scritti = 0
        self.byte = 0                    # byte dei dati scritti (dalla partenza)
        if scrivibile:
            from ..persistenza import prepara_schema
            try:
                with self.lock:
                    self.scrivibile = prepara_schema(db, MODULO, MIGRAZIONI, "conversazioni")
            except Exception as e:  # noqa: BLE001 — disco in sola lettura: eventi in memoria
                self.scrivibile = False
                log(f"[EVENTI] tabella degli eventi non scrivibile ({type(e).__name__}): "
                    f"gli eventi restano in memoria")

    @classmethod
    def da_archivio(cls, arch, log=print) -> "Disco":
        """Nello stesso file e nello stesso thread dell'archivio delle conversazioni (§ 2.3)."""
        return cls(arch.db, arch.lock, arch._in_coda, log=log,
                   scrivibile=bool(getattr(arch, "scrivibile", True)))

    @classmethod
    def file(cls, path, log=print) -> "Disco":
        """Un file suo, senza thread (prove, `calliope stato`)."""
        from ..persistenza import apri_db
        return cls(apri_db(str(path)), log=log)

    # ── scrittura a lotti ──
    def accoda(self, ev: Evento):
        """In memoria: l'evento andrà su disco con il prossimo lotto (microsecondi)."""
        with self._lock_lista:
            self._da_scrivere.append(ev)

    def scrivi(self):
        """Il lotto degli eventi accodati, nel thread dell'archivio (o subito senza thread).
        Non solleva mai: un errore si conta e si dice nel log."""
        with self._lock_lista:
            lotto, self._da_scrivere = self._da_scrivere, []
        if not lotto:
            return
        if not self.scrivibile:
            self.persi += len(lotto)
            return

        def f():
            try:
                righe = [riga(ev) for ev in lotto]
                with self.lock:
                    self.db.executemany(
                        "INSERT OR IGNORE INTO eventi (registro, seq, conv, corsia, t, tipo, "
                        "turno, vis, persona, ospite, dati, v) VALUES "
                        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", righe)
                    self.db.commit()
                self.scritti += len(righe)
                self.byte += sum(len(r[10]) for r in righe)
            except Exception as e:  # noqa: BLE001 — il disco non ferma la conversazione
                self.errori += 1
                self.persi += len(lotto)
                try:
                    self.db.rollback()
                except Exception:  # noqa: BLE001
                    pass
                if self.errori == 1 or self.errori % 100 == 0:
                    self.log(f"[EVENTI] lotto non scritto ({type(e).__name__}: {e}); eventi "
                             f"persi finora: {self.persi}")
        if self.in_coda is None:
            f()
        else:
            self.in_coda(f)

    def _lavoro(self, f):
        if self.in_coda is None:
            f()
        else:
            self.in_coda(f)

    # ── lettura (riavvio, stato): per registro, mai «tutto» ──
    def chiavi(self) -> list[str]:
        with self.lock:
            return [r[0] for r in self.db.execute("SELECT DISTINCT registro FROM eventi")]

    def leggi(self, chiave: str, da_seq: int = 0) -> list[tuple]:
        with self.lock:
            return self.db.execute(
                "SELECT registro, seq, conv, corsia, t, tipo, turno, vis, dati, v FROM eventi "
                "WHERE registro = ? AND seq >= ? ORDER BY seq", (chiave, int(da_seq))).fetchall()

    def ultimo_seq(self, chiave: str) -> int:
        with self.lock:
            r = self.db.execute("SELECT MAX(seq) FROM eventi WHERE registro = ?",
                                (chiave,)).fetchone()
        return int(r[0] or 0) if r else 0

    def inizio_ultimo_segmento(self, chiave: str) -> int:
        """Il seq dell'ultima `conversazione_aperta` del registro (0 se non c'è)."""
        with self.lock:
            r = self.db.execute("SELECT MAX(seq) FROM eventi WHERE registro = ? AND tipo = "
                                "'conversazione_aperta'", (chiave,)).fetchone()
        return int(r[0] or 0) if r else 0

    # ── cancellazioni: «dimentica», rotazione, chiusura degli ospiti (§ 2.3, § 10) ──
    def dimentica(self, chiave: str, quando: float | None = None) -> int:
        """Tutte le righe del registro, con `secure_delete` e il checkpoint del WAL; la
        richiesta resta in `eventi_dimenticati` (solo la chiave e l'ora) per il controllo di
        `calliope stato`. Sincrono: chi lo chiama ha già il lock dell'archivio o no."""
        quando = time.time() if quando is None else quando
        with self._lock_lista:
            self._da_scrivere = [e for e in self._da_scrivere if e.registro != chiave]
        with self.lock:
            n = cancella_sicuro(self.db, "DELETE FROM eventi WHERE registro = ?", (chiave,))
            self.db.execute("INSERT INTO eventi_dimenticati (registro, quando) VALUES (?, ?)",
                            (chiave, quando))
            self.db.commit()
            checkpoint(self.db)
        return n

    def chiudi_ospite(self, chiave: str, conv: str):
        """Una conversazione anonima chiusa: i suoi eventi si cancellano (§ 2.4; l'archivio tiene
        ciò che teneva già)."""
        def f():
            try:
                with self.lock:
                    cancella_sicuro(self.db, "DELETE FROM eventi WHERE registro = ? AND conv = ?",
                                    (chiave, conv))
                    self.db.commit()
            except Exception as e:  # noqa: BLE001
                self.log(f"[EVENTI] eventi dell'ospite non cancellati: {type(e).__name__}")
        self._lavoro(f)

    def ruota(self, giorni: float, ora: float | None = None) -> None:
        """Dopo `giorni` gli eventi delle conversazioni chiuse si cancellano (l'archivio ne tiene
        la forma dei turni, § 2.3); quelli di un segmento mai chiuso dopo il doppio."""
        if giorni <= 0:
            return
        ora = time.time() if ora is None else ora
        limite = ora - giorni * 86400

        def f():
            try:
                with self.lock:
                    cancella_sicuro(self.db, (
                        "DELETE FROM eventi WHERE t < ? AND ((registro, conv) IN (SELECT "
                        "registro, conv FROM eventi WHERE tipo = 'conversazione_chiusa') OR "
                        "t < ?)"), (limite, ora - 2 * giorni * 86400))
                    # Un ospite che non è tornato: la sua conversazione è finita da un pezzo
                    cancella_sicuro(self.db, "DELETE FROM eventi WHERE ospite = 1 AND t < ?",
                                    (ora - 86400,))
                    self.db.execute("DELETE FROM eventi_dimenticati WHERE quando < ?",
                                    (ora - 30 * 86400,))
                    self.db.commit()
            except Exception as e:  # noqa: BLE001
                self.log(f"[EVENTI] rotazione non riuscita: {type(e).__name__}: {e}")
        self._lavoro(f)


def cancella_sicuro(db, sql: str, parametri=()) -> int:
    """Un DELETE con `secure_delete` (le pagine liberate si azzerano); poi l'impostazione
    di prima della connessione."""
    prima = db.execute("PRAGMA secure_delete").fetchone()
    db.execute("PRAGMA secure_delete = ON")
    try:
        return db.execute(sql, parametri).rowcount
    finally:
        if prima is not None and not prima[0]:
            db.execute("PRAGMA secure_delete = OFF")


def checkpoint(db):
    """Il WAL ricopiato nel file e troncato: le versioni vecchie delle pagine non restano."""
    try:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
    except Exception:  # noqa: BLE001 — senza WAL (journal di rollback) non serve
        pass


# ─────────────────────────── il registro di una conversazione ───────────────────────────
class Registro:
    """Gli eventi di una chiave (`persona:<id>` o `ospite:<corsia>`), in sola aggiunta."""

    def __init__(self, chiave: str, disco: Disco | None = None, seq: int = 0):
        self.chiave = chiave
        self.disco = disco
        self._lock = threading.RLock()
        self._eventi: list[Evento] = []
        self._seq = int(seq)
        self.conv: str | None = None         # il segmento aperto
        self.chiuso: str | None = None       # l'ultimo segmento chiuso (la coda)
        self.troncati = 0                    # righe rovinate trovate nel rigioco
        # Lo spazio dell'ombra (calliope/eventi/ombra.py), solo in memoria: la Conversazione di
        # Brain che corrisponde al segmento aperto, i messaggi già visti, le differenze già dette
        self.stato: dict = {}

    @property
    def ospite(self) -> bool:
        return self.chiave.startswith("ospite:")

    def lotto(self):
        """Il lock del registro: un turno intero si scrive tutto insieme (§ 2.6 a)."""
        return self._lock

    @property
    def seq(self) -> int:
        return self._seq

    def aggiungi(self, _tipo: str, turno: int = 0, *, corsia: str | None = None,
                 vis: str | None = None, t: float | None = None, **dati) -> Evento:
        """L'unico modo di scrivere: un evento in coda, con il `seq` dopo l'ultimo."""
        tipo = _tipo
        v = controlla(tipo, vis, dati)
        with self._lock:
            if tipo == "conversazione_aperta":
                if self.conv is not None:
                    raise EventoNonValido("un segmento è già aperto: prima chiudilo")
                conv = uuid.uuid4().hex[:12]
            elif self.conv is None:
                raise EventoNonValido(f"{tipo}: nessuna conversazione aperta nel registro")
            else:
                conv = self.conv
            self._seq += 1
            ev = Evento(self.chiave, self._seq, conv, corsia,
                        time.time() if t is None else float(t), tipo, int(turno or 0), v,
                        dict(dati))
            if tipo == "conversazione_aperta":
                # In memoria il segmento nuovo e l'ultimo chiuso (la coda): gli altri sono su
                # disco e nell'archivio
                tieni = {self.chiuso} if self.chiuso else set()
                self._eventi = [e for e in self._eventi if e.conv in tieni]
                self.conv = conv
            self._eventi.append(ev)
            if tipo == "conversazione_chiusa":
                self.chiuso, self.conv = conv, None
            if self.disco is not None:
                self.disco.accoda(ev)
            return ev

    def apri(self, come: str, turno: int = 0, corsia: str | None = None, **dati) -> Evento:
        return self.aggiungi("conversazione_aperta", turno, corsia=corsia,
                             chiave=self.chiave, come=come, **dati)

    def chiudi(self, motivo: str, turno: int = 0, corsia: str | None = None) -> Evento | None:
        with self._lock:
            if self.conv is None:
                return None
            conv = self.conv
            ev = self.aggiungi("conversazione_chiusa", turno, corsia=corsia, motivo=motivo)
            if self.ospite and self.disco is not None:
                # Gli eventi con testo di un ospite non restano oltre la sua conversazione: prima
                # il lotto in attesa (anche gli ultimi eventi), poi la cancellazione
                self.disco.scrivi()
                self.disco.chiudi_ospite(self.chiave, conv)
            return ev

    def eventi(self, conv: str | None = None) -> tuple[Evento, ...]:
        """Gli eventi di un segmento (quello aperto se `conv` è None), nell'ordine di `seq`."""
        with self._lock:
            c = self.conv if conv is None else conv
            if c is None:
                return ()
            return tuple(e for e in self._eventi if e.conv == c)

    def svuota(self):
        """«Dimentica» in memoria: niente eventi, nessun segmento aperto. `seq` continua."""
        with self._lock:
            self._eventi, self.conv, self.chiuso = [], None, None
            self.stato.clear()

    # ── rigioco ──
    def _rigioca(self, eventi: list[Evento]):
        with self._lock:
            self._eventi = list(eventi)
            self.conv = self.chiuso = None
            for e in eventi:
                if e.tipo == "conversazione_aperta":
                    self.conv = e.conv
                elif e.tipo == "conversazione_chiusa":
                    self.chiuso, self.conv = e.conv, None


# ─────────────────────────── tutti i registri, uno per volta ───────────────────────────
class Registri:
    """I registri del processo. Dà **un** registro per volta: nessuna lettura di più registri
    insieme (§ 2.1, § 11.2)."""

    def __init__(self, disco: Disco | None = None, log=print):
        self.disco = disco
        self.log = log
        self._regs: dict[str, Registro] = {}
        self._lock = threading.Lock()
        self.troncati = 0

    def della_corsia(self, chiave: str) -> Registro:
        """Il registro della conversazione del turno (la chiave che la corsia ha scelto con
        `corsie.RegistroConversazioni.scegli`)."""
        return self._di(chiave)

    def _di(self, chiave: str, crea: bool = True) -> Registro | None:
        if not (chiave.startswith("persona:") or chiave.startswith("ospite:")
                or chiave == "casa"):
            raise EventoNonValido(f"chiave di registro non valida: {chiave!r}")
        with self._lock:
            r = self._regs.get(chiave)
            if r is None and crea:
                seq = 0
                if self.disco is not None:
                    try:
                        seq = self.disco.ultimo_seq(chiave)
                    except Exception:  # noqa: BLE001 — il disco non ferma la conversazione
                        seq = 0
                r = self._regs[chiave] = Registro(chiave, self.disco, seq)
            return r

    def esiste(self, chiave: str) -> bool:
        with self._lock:
            return chiave in self._regs

    def chiavi(self) -> list[str]:
        with self._lock:
            return list(self._regs)

    def scrivi(self):
        if self.disco is not None:
            self.disco.scrivi()

    def dimentica(self, chiave: str):
        """In memoria: il registro si svuota (il disco lo cancella `Disco.dimentica`)."""
        r = self._di(chiave, crea=False)
        if r is not None:
            r.svuota()

    def riprendi(self, scadenza_s: float = 0.0, ora: float | None = None) -> dict:
        """All'avvio: i segmenti aperti e non scaduti si rigiocano dal disco. Restituisce
        {"ripresi", "chiusi", "troncati", "proposte_perse"}."""
        out = {"ripresi": 0, "chiusi": 0, "troncati": 0, "proposte_perse": 0}
        if self.disco is None:
            return out
        ora = time.time() if ora is None else ora
        try:
            chiavi = self.disco.chiavi()
        except Exception as e:  # noqa: BLE001
            self.log(f"[EVENTI] registri non riletti: {type(e).__name__}: {e}")
            return out
        for chiave in chiavi:
            try:
                self._riprendi_uno(chiave, scadenza_s, ora, out)
            except Exception as e:  # noqa: BLE001 — un registro rovinato non ferma l'avvio
                out["troncati"] += 1
                self.log(f"[EVENTI] registro {chiave.split(':')[0]} non ripreso: "
                         f"{type(e).__name__}")
        self.troncati += out["troncati"]
        if out["ripresi"] or out["troncati"]:
            self.log(f"[EVENTI] Riprese {out['ripresi']} conversazioni dal registro degli "
                     f"eventi" + (f"; {out['troncati']} righe rovinate (eventi_troncati)"
                                  if out["troncati"] else ""))
        self.disco.scrivi()
        return out

    def _riprendi_uno(self, chiave: str, scadenza_s: float, ora: float, out: dict):
        disco = self.disco
        inizio = disco.inizio_ultimo_segmento(chiave)
        righe = disco.leggi(chiave, inizio) if inizio else []
        eventi: list[Evento] = []
        atteso = inizio
        troncato = False
        for r in righe:
            try:
                ev = da_riga(r)
            except (ValueError, TypeError, KeyError):
                troncato = True
                break
            if ev.seq != atteso:              # un buco: si ferma all'ultimo evento buono
                troncato = True
                break
            eventi.append(ev)
            atteso += 1
        reg = self._di(chiave)
        if troncato:
            reg.troncati += 1
            out["troncati"] += 1
        if not eventi or eventi[0].tipo != "conversazione_aperta":
            return
        segmento = [e for e in eventi if e.conv == eventi[0].conv]
        reg._rigioca(segmento)
        if reg.conv is None:
            return                            # l'ultimo segmento è già chiuso
        if scadenza_s > 0 and ora - segmento[-1].t > scadenza_s:
            reg.chiudi("scaduta_riavvio", segmento[-1].turno)
            out["chiusi"] += 1
            return
        # Una proposta aperta si perde al riavvio (decisione di Dario, § 2.3)
        aperte: dict[str, Evento] = {}
        for e in segmento:
            if e.tipo == "proposta_aperta":
                aperte[str(e.dati.get("id"))] = e
            elif e.tipo == "proposta_chiusa":
                aperte.pop(str(e.dati.get("id")), None)
        for pid, e in aperte.items():
            reg.aggiungi("proposta_chiusa", e.turno, id=pid, come="persa_riavvio",
                         eseguita=False)
            out["proposte_perse"] += 1
        reg.stato["ripreso"] = True
        out["ripresi"] += 1


# ─────────────────────────── porte fra registri (§ 2.5) ───────────────────────────
_porte = threading.local()

PORTE = ("annuncio", "avviso_tutore", "coda", "riassegna", "proposta_altrui")


def porte_usate(azzera: bool = True) -> list[str]:
    """I nomi delle porte usate da questo thread dall'ultima volta (per il registro dei turni)."""
    lst = getattr(_porte, "usate", None) or []
    if azzera:
        _porte.usate = []
    return list(lst)


def _usa(nome: str):
    if not isinstance(getattr(_porte, "usate", None), list):
        _porte.usate = []
    _porte.usate.append(nome)


def porta_annuncio(registri: Registri, chiave: str) -> Registro:
    """Un annuncio (lavoro, documento, installazione, agenda) per la persona che l'ha chiesto:
    il registro **suo** (mai di chi ha parlato per ultimo, buco 5)."""
    if not (chiave.startswith("persona:") or chiave.startswith("ospite:") or chiave == "casa"):
        raise EventoNonValido("annuncio: serve la chiave di una conversazione")
    _usa("annuncio")
    return registri._di(chiave)


def porta_avviso_tutore(registri: Registri, chiave_tutore: str) -> Registro:
    """L'avviso del guardiano detto al tutore: nel registro **del tutore**, solo il testo detto
    (mai le frasi del minore)."""
    if not chiave_tutore.startswith("persona:"):
        raise EventoNonValido("avviso al tutore: serve la chiave di una persona")
    _usa("avviso_tutore")
    return registri._di(chiave_tutore)


def porta_coda(registri: Registri, chiave_chiusa: str, chiave_nuova: str) -> Registro:
    """La coda di una conversazione chiusa va solo nella nuova della **stessa** chiave, mai in
    quella di un ospite (buco 6)."""
    if chiave_chiusa != chiave_nuova or chiave_nuova.startswith("ospite:"):
        raise EventoNonValido("la coda va solo alla stessa persona")
    _usa("coda")
    return registri._di(chiave_nuova)


def porta_riassegna(registri: Registri, da: str, seq: int, a: str, motivo: str,
                    corsia: str | None = None) -> tuple[Evento, Evento]:
    """Un turno finito nel registro sbagliato (§ 2.6 c): mai riscrittura. `turno_riassegnato`
    nell'origine (che da lì non lo proietta più) e un `detto_persona` nuovo nella destinazione,
    con il testo copiato una volta e `riassegnato_da`. Solo esplicita (a voce o da chi
    amministra), mai automatica."""
    if da == a:
        raise EventoNonValido("riassegnazione nello stesso registro")
    origine = registri._di(da, crea=False)
    if origine is None:
        raise EventoNonValido("registro d'origine sconosciuto")
    with origine.lotto():
        ev = next((e for e in origine.eventi() if e.seq == seq), None)
        if ev is None or ev.tipo != "detto_persona":
            raise EventoNonValido("si riassegna solo un detto_persona del segmento aperto")
        e1 = origine.aggiungi("turno_riassegnato", ev.turno, corsia=corsia, da_registro=da,
                              seq=seq, a_registro=a, motivo=motivo)
    dest = registri._di(a)
    _usa("riassegna")
    with dest.lotto():
        if dest.conv is None:
            dest.apri("riassegnato", ev.turno, corsia)
        dati = {k: v for k, v in ev.dati.items() if k in TIPI["detto_persona"].campi}
        dati["riassegnato_da"] = f"{da}#{seq}"
        e2 = dest.aggiungi("detto_persona", ev.turno, corsia=corsia, vis=ev.vis, **dati)
    return e1, e2


def porta_proposta_altrui(registri: Registri, chiave: str, satellite: str | None,
                          ora: float | None = None) -> dict | None:
    """«C'è una proposta di Ginevra in sospeso»: dal registro di quella persona solo
    {chi_nome, domanda, cosa}, solo per lo stesso satellite e solo entro i tempi della proposta."""
    reg = registri._di(chiave, crea=False)
    if reg is None:
        return None
    ora = time.time() if ora is None else ora
    aperta = None
    for e in reg.eventi():
        if e.tipo == "proposta_aperta":
            aperta = e
        elif e.tipo == "proposta_chiusa" and aperta is not None \
                and e.dati.get("id") == aperta.dati.get("id"):
            aperta = None
    if aperta is None or aperta.dati.get("satellite") != satellite:
        return None
    scade = aperta.dati.get("scade")
    if isinstance(scade, (int, float)) and ora > scade:
        return None
    _usa("proposta_altrui")
    return {"chi_nome": aperta.dati.get("chi"), "domanda": aperta.dati.get("domanda"),
            "cosa": aperta.dati.get("cosa")}


# ─────────────────────────── le guardie in `calliope stato` (§ 10) ───────────────────────────
def stato_disco(path, giorni: int = 7, avviso_mb: float = 50.0) -> dict | None:
    """In sola lettura, da `conversazioni.db`: la crescita del registro (MB per giorno, totale,
    `eventi_mb_giorno`) e il controllo di «dimentica» (`dimentica_residui`: righe rimaste di un
    registro dimenticato scritte prima della richiesta, nella tabella `eventi`, nell'archivio
    delle conversazioni e nella conversazione salvata; più i turni orfani dell'archivio). Mai
    testo: solo conteggi. None se il file o la tabella non ci sono."""
    import json as _json
    import sqlite3
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return None
    try:
        db = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True, timeout=5.0)
    except sqlite3.Error:
        return None
    try:
        tabelle = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "eventi" not in tabelle:
            return None
        per_giorno = [{"giorno": r[0], "mb": round((r[1] or 0) / 1e6, 3), "eventi": r[2]}
                      for r in db.execute(
                          "SELECT date(t, 'unixepoch', 'localtime') AS g, SUM(length(dati) + "
                          "length(registro) + length(conv) + 40), COUNT(*) FROM eventi "
                          "GROUP BY g ORDER BY g DESC LIMIT ?", (int(giorni),))]
        tot = db.execute("SELECT COUNT(*), SUM(length(dati) + length(registro) + length(conv) "
                         "+ 40), COUNT(DISTINCT registro) FROM eventi").fetchone()
        richieste = db.execute("SELECT registro, MAX(quando) FROM eventi_dimenticati GROUP BY "
                               "registro").fetchall()
        residui = 0
        for registro, quando in richieste:
            residui += db.execute("SELECT COUNT(*) FROM eventi WHERE registro = ? AND t <= ?",
                                  (registro, quando)).fetchone()[0]
            persona = registro.split(":", 1)[1] if registro.startswith("persona:") else None
            if persona and "conversazioni" in tabelle:
                residui += db.execute(
                    "SELECT COUNT(*) FROM conversazioni WHERE persona = ? AND ospite = 0 AND "
                    "inizio <= ?", (persona, quando)).fetchone()[0]
            if "correnti" in tabelle:
                for (stato,) in db.execute("SELECT stato FROM correnti WHERE chiave = ?",
                                           (registro,)):
                    try:
                        st = _json.loads(stato)
                        if st.get("history") and float(st.get("inizio") or 0) <= quando:
                            residui += 1
                    except (ValueError, TypeError, AttributeError):
                        residui += 1
        orfani = 0
        if {"turni", "conversazioni"} <= tabelle and richieste:
            orfani = db.execute("SELECT COUNT(*) FROM turni WHERE conv NOT IN (SELECT id FROM "
                                "conversazioni)").fetchone()[0]
        oggi = per_giorno[0]["mb"] if per_giorno else 0.0
        mb = (tot[1] or 0) / 1e6
        return {"per_giorno": per_giorno, "eventi": tot[0] or 0, "mb": round(mb, 3),
                "registri": tot[2] or 0,
                "dimentica": {"richieste": len(richieste), "residui": residui + orfani},
                "avviso": bool(avviso_mb and (oggi > avviso_mb or mb > 10 * avviso_mb))}
    except sqlite3.Error:
        return None
    finally:
        db.close()


def testo_stato(d: dict | None, avviso_mb: float = 50.0) -> str | None:
    """Le righe per `calliope stato`."""
    if not d:
        return None
    g = d["per_giorno"][0] if d["per_giorno"] else None
    righe = [f"Registro degli eventi: {d['eventi']} eventi in {d['registri']} registri, "
             f"{d['mb']:.2f} MB" + (f"; {g['giorno']} {g['mb']:.2f} MB" if g else "")]
    dm = d["dimentica"]
    righe.append(f"Dimentica: {dm['richieste']} richieste, residui {dm['residui']}")
    if d.get("avviso"):
        righe.append(f"ATTENZIONE: il registro degli eventi cresce oltre {avviso_mb:.0f} MB al "
                     f"giorno (o {10 * avviso_mb:.0f} MB in tutto): guarda la rotazione "
                     f"(eventi_giorni)")
    if dm["residui"]:
        righe.append("ATTENZIONE: dopo «dimentica» restano righe di una persona dimenticata "
                     "(dimentica_residui deve essere 0)")
    return "\n".join(righe)
