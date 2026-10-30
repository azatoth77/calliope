"""
Il servizio dello Studio (29/10, passo 4.1, issue #280, decisione 0035): l'API interna sopra i
dati (`dati.py`) e il piano (`piano.py`), con i permessi e l'interruttore. Niente tool, niente
pagina, niente modello: il tool `studio`, la home e la vista aperta sono del passo 4.5, che
userà questa API.

**Permessi** (risposta 5 di chi amministra del 28/10): lo Studio è di tutte le persone di casa;
ognuno vede e cambia il suo. Il tutore vede e cambia quello del suo minore; nessuno vede quello
degli altri adulti (chi amministra compreso); gli ospiti e i conoscenti mai, né per sé né per
altri. Un'azione senza permesso solleva `NonPermesso`, una verifica che non c'è `NonTrovata`:
le frasi le scrive chi le dice (0018), sempre con lo stesso rifiuto, così non si sa se la
verifica di un altro c'è.

**Interruttore** `studio_modo`: «spento» → `prepara` non crea niente (la tenuta, «dimentica»
e `--svuota` lavorano lo stesso sui dati di prima, da `conserva.py`); «ombra» → i dati si
scrivono e il piano si calcola, ma `per_modello()` e `per_schermi()` sono falsi: niente al
modello né agli schermi, solo le misure nel registro (senza nomi né titoli); «attivo» → per il
passo 4.5.

**Lettura** (30/10, passo 4.3, #282): `avvia_lettura` crea il lettore (`lettura.py`), che legge
in ombra e in attivo; `lettura()` dà l'avanzamento di una verifica e `testo_per_modello()` il testo
letto in busta, solo in attivo.

**Argomenti** (30/10, passo 4.4, #283): li chiede il thread del lettore quando le pagine di una
verifica sono tutte lette (`argomenti.py`, `verifiche_per_argomenti`, `proponi_argomenti`) e
arrivano «proposti»; la persona li tiene, li toglie, li rinomina, li unisce o ne aggiunge
(`segna_argomento`, `rinomina_argomento`, `unisci_argomenti`, `aggiungi_argomento`) e conferma
l'elenco (`conferma_argomenti`). Il piano usa solo i tenuti e gli aggiunti.

**Ricalcolo.** Il piano si ricalcola quando cambia qualcosa (argomenti confermati, data
spostata, minuti, giorno fatto o saltato, giorni senza scuola) e, alla prima lettura di un
giorno nuovo, perché «oggi» si è spostato. Con i dati di una versione più nuova (connessione
in `query_only`, `persistenza.prepara_schema`) le letture vanno lo stesso: il piano di oggi si
calcola in memoria e non si salva (revisione della PR #308).

**Chi passa chi (per il passo 4.5).** Ogni metodo decide su `chi`, il profilo di chi parla o
del proprietario dello schermo personale. Chi chiama passa `None` per un ospite **e per la zona
grigia** (voce incerta, frase breve senza impronta, compagnia senza il nome), come `_chi` di
`tools/conversazioni.py`: lo Studio di una persona non si apre su un'identità incerta. Il
profilo di un minore incerto (`minori.profilo`, `minore_incerto`) vale il minore, mai l'adulto.
"""

from __future__ import annotations

import datetime
import json
import re

from . import dati as D
from . import piano as P

SPENTO, OMBRA, ATTIVO = "spento", "ombra", "attivo"
MODI = (SPENTO, OMBRA, ATTIVO)

# La materia: un elenco fisso più «altro» (decisione 0035, punto 7: niente indice del
# programma nel passo 4). Un'altra materia si scrive com'è, corta
MATERIE = ("Matematica", "Italiano", "Storia", "Geografia", "Scienze", "Inglese", "Francese",
           "Spagnolo", "Tedesco", "Tecnologia", "Arte", "Musica", "Fisica", "Chimica", "Latino",
           "Filosofia", "Diritto", "Economia", "Informatica")
MATERIA_MAX = 40
FASCIA_DI_SERIE = "15:00-20:00"
TITOLO_MAX = 60


class NonPermesso(PermissionError):
    """Chi chiede non può vedere né cambiare lo Studio di quella persona."""


class NonTrovata(LookupError):
    """La verifica (o il materiale, la pagina, l'argomento, il giorno) non c'è, oppure è di un
    altro: sempre con lo stesso messaggio, così un id non dice se esiste (revisione della PR
    #308, nota 1)."""

    def __init__(self, *_):
        super().__init__(NON_TROVATA)


NON_TROVATA = "non c'è"


class VerificaChiusa(ValueError):
    """La verifica è fatta o archiviata: non prende pagine nuove (passo 4.2)."""

    def __init__(self, *_):
        super().__init__("la verifica è chiusa")


class TroppePagine(ValueError):
    """Le pagine di una verifica sono già al tetto `studio_pagine_max` (passo 4.2)."""

    def __init__(self, massimo: int = 0):
        super().__init__(f"al più {massimo} pagine per verifica")
        self.massimo = massimo


def modo(cfg) -> str:
    m = str(getattr(cfg, "studio_modo", SPENTO) or SPENTO).strip().lower()
    return m if m in MODI else SPENTO


def prepara(cfg, registry=None, log=print):
    """Il servizio dello Studio, o None con `studio_modo: spento` o senza il file della
    memoria."""
    if modo(cfg) == SPENTO or not getattr(cfg, "memory_db", None):
        return None
    return Studio(cfg, registry=registry, log=log)


# ─────────────────────────── permessi ───────────────────────────

def _categoria(prof) -> str:
    from ..conserva import categoria
    return categoria(prof)


def _e_tutore(chi, minore, registry=None) -> bool:
    """`chi` è un tutore di `minore`. Come `minori.tutori`: valgono i tutori scritti che sono
    ancora in casa (`conserva.tutori_validi`); se non ce n'è più nessuno, chi amministra
    (revisione della PR #308, nota 2). Senza il registro, i tutori scritti (`minori.e_tutore`)."""
    from ..conserva import tutori_validi
    validi = tutori_validi(minore, registry)
    if validi:
        return getattr(chi, "id", None) in validi
    return bool(getattr(chi, "admin", False))


def permesso(chi, proprietario, registry=None) -> str | None:
    """«proprietario», «tutore» o None. Gli ospiti e i conoscenti mai, da nessuna parte."""
    if chi is None or proprietario is None:
        return None
    if _categoria(chi) in ("ospite", "conoscente") or \
            _categoria(proprietario) in ("ospite", "conoscente"):
        return None
    if getattr(chi, "id", None) and getattr(chi, "id", None) == getattr(proprietario, "id", None):
        return "proprietario"
    if _categoria(proprietario) == "minore" and _e_tutore(chi, proprietario, registry):
        return "tutore"
    return None


def materia_normale(testo) -> str:
    t = " ".join(str(testo or "").split())[:MATERIA_MAX]
    if not t:
        raise ValueError("manca la materia")
    for m in MATERIE:
        if t.lower() == m.lower():
            return m
    return t[:1].upper() + t[1:]


def titolo_normale(testo) -> str:
    """Un titolo di argomento: una riga, al più `TITOLO_MAX` caratteri. Il controllo di forma
    contro i titoli proposti dal modello che sono ordini (decisione 0035, punto 6) è
    `argomenti.forma_titolo` (passo 4.4)."""
    t = re.sub(r"[\x00-\x1f\x7f  ​-‏‪-‮⁦-⁩]", " ",
               str(testo or ""))
    t = " ".join(t.split())[:TITOLO_MAX].strip()
    if not t:
        raise ValueError("manca il titolo")
    return t


def _data(valore) -> datetime.date:
    if isinstance(valore, datetime.datetime):
        return valore.date()
    if isinstance(valore, datetime.date):
        return valore
    return datetime.date.fromisoformat(str(valore).strip()[:10])


class Studio:
    """Lo Studio di questa installazione: un oggetto per processo."""

    def __init__(self, cfg, registry=None, log=print, adesso=None):
        self.cfg = cfg
        self.registry = registry
        self.log = log
        self.modo = modo(cfg)
        # L'orologio (le prove lo fingono)
        self.adesso = adesso or datetime.datetime.now
        self.dati = D.Dati(cfg.memory_db)
        # All'avvio nessun PDF si sta dividendo: via i provvisori di un crollo (PR #312)
        try:
            D.togli_provvisori(D.cartella_di(cfg))
        except OSError:
            pass
        # Le misure dell'ombra (e dell'attivo): solo conti, niente nomi né titoli
        self.misure = {"verifiche_create": 0, "piani": 0, "giorni_nei_piani": 0,
                       "pagine_nei_piani": 0, "giorni_oltre": 0, "avvisi": {}, "errori": 0,
                       # Le pagine arrivate (passo 4.2): da dove vengono i bordi e gli avvisi
                       "pagine": 0, "bordi": {}, "avvisi_pagine": {}}
        # Il lettore delle pagine (passo 4.3, studio/lettura.py): lo crea `avvia_lettura`
        self.lettore = None
        self.fascia = P.fascia_valida(getattr(cfg, "studio_fascia", ""))
        if self.fascia is None:
            # Il caricamento della configurazione la rifiuta già (config._fascia_valida); qui
            # per una Config scritta a mano. Una riga nel registro, poi il valore di serie
            self.log(f"   [STUDIO] studio_fascia «{getattr(cfg, 'studio_fascia', '')}» non è "
                     f"valida: uso {FASCIA_DI_SERIE}")
            self.fascia = P.fascia_valida(FASCIA_DI_SERIE)

    def close(self):
        if self.lettore is not None:
            self.lettore.close()
        self.dati.close()

    # ── la lettura delle pagine (30/10, passo 4.3, #282) ──
    def avvia_lettura(self, lavori=None, avvia: bool = True):
        """Il lettore delle pagine in un thread (studio/lettura.py): legge in ombra e in attivo
        (con `studio_lettura`); il testo arriva a un modello solo in attivo e in busta
        (`testo_per_modello`)."""
        from . import lettura as L
        if self.lettore is None:
            self.lettore = L.prepara(self, lavori=lavori, log=self.log, avvia=avvia)
        return self.lettore

    def lettura(self, chi, vid) -> dict:
        """L'avanzamento della lettura di una verifica (per la 4.5): pagine lette su totali,
        illeggibili, in lettura e da leggere, gli avvisi della lettura e se il lettore aspetta
        (la DGX occupata). Le pagine tolte non contano."""
        v = self._verifica(chi, vid)
        righe = self.dati.tutti(
            "SELECT p.stato, p.avvisi FROM studio_pagine p JOIN studio_materiali m ON m.id = "
            "p.materiale WHERE m.verifica = ? AND p.stato != 'tolta'", (v["id"],))
        conta = {}
        for r in righe:
            conta[r["stato"]] = conta.get(r["stato"], 0) + 1
        avvisi = {}
        for r in righe:
            for a in D.da_j(r["avvisi"]):
                avvisi[a] = avvisi.get(a, 0) + 1
        lett = self.lettore
        return {"verifica": v["id"], "totali": len(righe), "lette": conta.get("letta", 0),
                "illeggibili": conta.get("illeggibile", 0),
                "in_lettura": conta.get("in_lettura", 0), "da_parte": conta.get("da_parte", 0),
                "da_leggere": conta.get("da_leggere", 0), "avvisi": avvisi,
                "lettore": lett is not None,
                "in_attesa": bool(lett is not None and lett.in_attesa)}

    def testo_per_modello(self, chi, vid) -> str | None:
        """Il testo letto delle pagine di una verifica per un modello: solo in attivo, sempre in
        busta (`provenienza.racchiudi`, decisione 0035 punto 6), una busta per pagina col
        riferimento P1, P2… scritto dal codice. None in ombra o senza pagine lette."""
        if not self.per_modello():
            return None
        from .. import provenienza
        out = []
        for i, p in enumerate(self.pagine(chi, vid), 1):
            if p["stato"] != "letta" or not p["testo"]:
                continue
            fonte = "allegato" if p["metodo"] == "pdf_testo" else "foto"
            num = P.numero_leggibile(p["numero"])
            titolo = f"P{i}" + (f" · pagina stampata {num}" if num else "")
            out.append(provenienza.racchiudi(fonte, p["testo"], titolo))
        return "\n\n".join(out) or None

    # ── interruttore ──
    def per_modello(self) -> bool:
        """Lo Studio può arrivare al modello (dati del turno, tool)? Solo «attivo»."""
        return self.modo == ATTIVO

    def per_schermi(self) -> bool:
        """Lo Studio può arrivare agli schermi (home, tessera, schede)? Solo «attivo»."""
        return self.modo == ATTIVO

    # ── chi ──
    def _oggi(self) -> datetime.date:
        return self.adesso().date()

    def _profilo(self, persona_id):
        reg = self.registry
        by_id = getattr(reg, "by_id", None) if reg is not None else None
        try:
            return by_id(str(persona_id)) if callable(by_id) else None
        except Exception:  # noqa: BLE001
            return None

    def _chi_puo(self, chi, persona_id) -> str:
        prop = chi if getattr(chi, "id", None) == persona_id else self._profilo(persona_id)
        p = permesso(chi, prop, self.registry)
        if p is None:
            raise NonPermesso("non è tuo")
        return p

    def _verifica(self, chi, vid) -> dict:
        v = self.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (int(vid),))
        if v is None:
            raise NonTrovata()
        try:
            self._chi_puo(chi, v["persona"])
        except NonPermesso:
            # Lo stesso rifiuto di una verifica che non c'è: non si sa se quella di un altro c'è
            raise NonTrovata() from None
        return v

    def _scrivibile(self):
        if not self.dati.scrivibile:
            raise PermissionError("dati di una versione più nuova: sola lettura")

    # ── verifiche ──
    def crea_verifica(self, chi, materia, data, livello=None, argomento=None, obiettivo=None,
                      persona=None) -> int:
        """Una verifica nuova, in bozza, per `chi` o (un tutore) per il suo minore."""
        self._scrivibile()
        persona = str(persona or getattr(chi, "id", "") or "")
        self._chi_puo(chi, persona)
        d = _data(data)
        if d < self._oggi():
            raise ValueError("la data è passata")
        ob = int(obiettivo if obiettivo is not None else getattr(self.cfg, "studio_obiettivo", 75))
        if not 1 <= ob <= 100:
            raise ValueError("l'obiettivo va da 1 a 100")
        vid = self.dati.scrivi(
            "INSERT INTO studio_verifiche (persona, materia, argomento, data, livello, obiettivo,"
            " stato, creata, creata_da) VALUES (?, ?, ?, ?, ?, ?, 'bozza', ?, ?)",
            (persona, materia_normale(materia),
             (" ".join(str(argomento).split())[:120] or None) if argomento else None,
             d.isoformat(), (" ".join(str(livello).split())[:60] or None) if livello else None,
             ob, D.adesso(), getattr(chi, "id", None)))
        self.misure["verifiche_create"] += 1
        self._registra(f"verifica {vid} creata ({self._chi_registro(chi, persona)})")
        return vid

    def verifica(self, chi, vid) -> dict:
        v = self._verifica(chi, vid)
        v["giorni_mancanti"] = (_data(v["data"]) - self._oggi()).days
        return v

    def verifiche(self, chi, persona=None, archiviate: bool = False) -> list[dict]:
        """Le verifiche di una persona (di serie di chi chiede), dalla più vicina."""
        persona = str(persona or getattr(chi, "id", "") or "")
        self._chi_puo(chi, persona)
        q = "SELECT * FROM studio_verifiche WHERE persona = ?"
        if not archiviate:
            q += " AND stato != 'archiviata'"
        out = self.dati.tutti(q + " ORDER BY data, id", (persona,))
        for v in out:
            v["giorni_mancanti"] = (_data(v["data"]) - self._oggi()).days
        return out

    def imposta(self, chi, vid, *, data=None, obiettivo=None, minuti_giorno=None,
                livello=None, materia=None, argomento=None):
        """Cambia la data («la verifica è spostata a lunedì»), l'obiettivo, i minuti al giorno
        (anche il tutore), la classe, la materia; poi il piano si ricalcola."""
        self._scrivibile()
        v = self._verifica(chi, vid)
        campi = {}
        if data is not None:
            d = _data(data)
            if d < self._oggi():
                raise ValueError("la data è passata")
            campi["data"] = d.isoformat()
            if v["stato"] == "fatta":
                campi["stato"] = "aperta"
        if obiettivo is not None:
            if not 1 <= int(obiettivo) <= 100:
                raise ValueError("l'obiettivo va da 1 a 100")
            campi["obiettivo"] = int(obiettivo)
        if minuti_giorno is not None:
            if not 0 <= int(minuti_giorno) <= 600:
                raise ValueError("i minuti al giorno vanno da 0 a 600")
            campi["minuti_giorno"] = int(minuti_giorno)
        if livello is not None:
            campi["livello"] = " ".join(str(livello).split())[:60] or None
        if materia is not None:
            campi["materia"] = materia_normale(materia)
        if argomento is not None:
            campi["argomento"] = " ".join(str(argomento).split())[:120] or None
        if not campi:
            return
        sets = ", ".join(f"{k} = ?" for k in campi)
        self.dati.scrivi(f"UPDATE studio_verifiche SET {sets} WHERE id = ?",
                         (*campi.values(), v["id"]))
        self.ricalcola_persona(v["persona"])

    def archivia(self, chi, vid):
        """«Archivia la verifica»: resta per sempre, anche dopo «dimentica» (decisione 0035,
        punto 4); va via solo con `--svuota` o togliendola."""
        self._scrivibile()
        v = self._verifica(chi, vid)
        self.dati.scrivi("UPDATE studio_verifiche SET stato = 'archiviata', archiviata = ? "
                         "WHERE id = ?", (D.adesso(), v["id"]))
        self.ricalcola_persona(v["persona"])

    def togli_verifica(self, chi, vid) -> dict:
        """Toglie la verifica e tutto ciò che è suo (pagine, testo, argomenti, piano)."""
        self._scrivibile()
        v = self._verifica(chi, vid)
        with self.dati.lock:
            db = self.dati.db
            if db.in_transaction:
                db.commit()
            prima = db.execute("PRAGMA secure_delete").fetchone()[0]
            db.execute("PRAGMA secure_delete = ON")
            try:
                db.execute("BEGIN IMMEDIATE")
                file = D._togli_verifiche(db, [v["id"]])
                db.commit()
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
            finally:
                db.execute(f"PRAGMA secure_delete = {int(prima)}")
        n = D.togli_file(file, D.cartella_di(self.cfg))
        self.ricalcola_persona(v["persona"])
        return {"verifiche": 1, "file": n}

    # ── materiali e pagine (solo i riferimenti: il caricamento è del passo 4.2) ──
    def aggiungi_materiale(self, chi, vid, origine: str, titolo=None, riferimento=None) -> int:
        self._scrivibile()
        v = self._verifica(chi, vid)
        if origine not in D.ORIGINI:
            raise ValueError("origine sconosciuta")
        return self.dati.scrivi(
            "INSERT INTO studio_materiali (verifica, origine, titolo, riferimento, creato) "
            "VALUES (?, ?, ?, ?, ?)",
            (v["id"], origine, (" ".join(str(titolo).split())[:60] or None) if titolo else None,
             str(riferimento)[:300] if riferimento else None, D.adesso()))

    def _materiale(self, chi, mid) -> tuple[dict, dict]:
        m = self.dati.uno("SELECT * FROM studio_materiali WHERE id = ?", (int(mid),))
        if m is None:
            raise NonTrovata()
        return m, self._verifica(chi, m["verifica"])

    def aggiungi_pagina(self, chi, mid, numero=None, ordine=None, etichetta=None, file=None,
                        stato: str = "buona", testo=None, metodo=None) -> int:
        """Una pagina di un materiale. `file` è relativo alla cartella dello Studio; `testo` è
        il testo letto (passo 4.3), un dato non fidato che qui si salva com'è."""
        self._scrivibile()
        m, v = self._materiale(chi, mid)
        if stato not in D.STATI_PAGINA:
            raise ValueError("stato della pagina sconosciuto")
        if ordine is None:
            r = self.dati.uno("SELECT COALESCE(MAX(p.ordine), 0) AS o FROM studio_pagine p JOIN "
                              "studio_materiali m ON m.id = p.materiale WHERE m.verifica = ?",
                              (v["id"],))
            ordine = int(r["o"]) + 1
        pid = self.dati.scrivi(
            "INSERT INTO studio_pagine (materiale, ordine, numero, etichetta, stato, file, testo,"
            " metodo, creata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (m["id"], int(ordine), (str(numero).strip()[:12] or None) if numero else None,
             (" ".join(str(etichetta).split())[:40] or None) if etichetta else None, stato,
             file, testo, metodo, D.adesso()))
        return pid

    def pagine(self, chi, vid) -> list[dict]:
        v = self._verifica(chi, vid)
        return self.dati.tutti(
            "SELECT p.*, m.titolo AS materiale_titolo FROM studio_pagine p JOIN studio_materiali"
            " m ON m.id = p.materiale WHERE m.verifica = ? ORDER BY p.ordine, p.id", (v["id"],))

    def segna_pagina(self, chi, pid, stato: str):
        """Lo stato di una pagina («tolta», «letta»…); il piano si ricalcola."""
        self._scrivibile()
        if stato not in D.STATI_PAGINA:
            raise ValueError("stato della pagina sconosciuto")
        p = self.dati.uno("SELECT * FROM studio_pagine WHERE id = ?", (int(pid),))
        if p is None:
            raise NonTrovata()
        _m, v = self._materiale(chi, p["materiale"])
        self.dati.scrivi("UPDATE studio_pagine SET stato = ? WHERE id = ?", (stato, p["id"]))
        self._ricalcola_sicuro(v["id"])

    # ── pagine dalla fotocamera e dai PDF (29/10, passo 4.2, #281: POST /api/studio/pagina) ──
    def verifica_per_pagine(self, chi, vid) -> dict:
        """La verifica a cui `chi` aggiunge pagine: la sua o quella del suo minore (tutore), in
        bozza o aperta. `NonTrovata` (anche per quella di un altro), `VerificaChiusa`; con le
        pagine che ha già (`n_pagine`), per il tetto `studio_pagine_max`."""
        self._scrivibile()
        v = self._verifica(chi, vid)
        if v["stato"] not in ("bozza", "aperta"):
            raise VerificaChiusa()
        r = self.dati.uno("SELECT COUNT(*) AS n FROM studio_pagine p JOIN studio_materiali m ON "
                          "m.id = p.materiale WHERE m.verifica = ?", (v["id"],))
        v["n_pagine"] = int(r["n"]) if r else 0
        return v

    def verifiche_per_pagine(self, chi) -> list[dict]:
        """Le verifiche in bozza o aperte a cui `chi` può mandare pagine: le sue e, se è tutore,
        quelle dei suoi minori (con `di`, il nome del minore). Per la pagina del telefono."""
        persone = [getattr(chi, "id", None)]
        reg = self.registry
        for p in (getattr(reg, "users", {}) or {}).values() if reg is not None else ():
            if getattr(p, "id", None) not in persone and permesso(chi, p, reg) == "tutore":
                persone.append(p.id)
        out = []
        for pid in persone:
            if not pid:
                continue
            try:
                self._chi_puo(chi, pid)
            except NonPermesso:
                continue
            nome = None if pid == getattr(chi, "id", None) else getattr(self._profilo(pid),
                                                                       "name", None)
            for v in self.dati.tutti(
                    "SELECT v.*, (SELECT COUNT(*) FROM studio_pagine p JOIN studio_materiali m "
                    "ON m.id = p.materiale WHERE m.verifica = v.id) AS n_pagine FROM "
                    "studio_verifiche v WHERE persona = ? AND stato IN ('bozza', 'aperta') "
                    "ORDER BY data, id", (pid,)):
                out.append({"id": v["id"], "materia": v["materia"], "argomento": v["argomento"],
                            "data": v["data"], "stato": v["stato"], "pagine": v["n_pagine"],
                            "giorni_mancanti": (_data(v["data"]) - self._oggi()).days,
                            "di": nome})
        return out

    def aggiungi_pronte(self, chi, vid, pronte: list, origine: str = "foto", titolo=None,
                        materiale=None, originale: bytes | None = None) -> dict:
        """Le pagine controllate dal server (`studio/pagine.Pronta`) nella verifica: i JPEG (e il
        PDF originale) nella cartella dello Studio, una riga per pagina nello stato «da_leggere»,
        in fondo all'ordine. `materiale`: quello di un invio già cominciato (le pagine dello
        stesso giro stanno insieme), altrimenti uno nuovo. Il tetto `studio_pagine_max` per
        verifica; i file scritti si tolgono se le righe non entrano."""
        from . import pagine as PG
        self._scrivibile()
        cartella = D.cartella_di(self.cfg)
        massimo = int(getattr(self.cfg, "studio_pagine_max", 80) or 80)
        scritti: list[str] = []
        with self.dati.lock:
            v = self.verifica_per_pagine(chi, vid)
            if v["n_pagine"] + len(pronte) > massimo:
                raise TroppePagine(massimo)
            # Un PDF ha sempre il suo materiale (passo 4.3): la sua copia sta nel `riferimento`
            # del materiale, e la pagina i del materiale è la pagina i del PDF per la lettura del
            # testo senza OCR. Nello stesso materiale di un altro PDF la copia non avrebbe riga
            if materiale is not None and originale is None:
                m = self.dati.uno("SELECT * FROM studio_materiali WHERE id = ?", (int(materiale),))
                if m is None or m["verifica"] != v["id"] or m["origine"] != origine:
                    raise NonTrovata()
                mid = m["id"]
            else:
                mid = None
            db = self.dati.db
            try:
                for p in pronte:
                    scritti.append(PG.scrivi_file(cartella, v["id"], p.jpeg, "jpg"))
                rif = None
                if originale is not None:
                    pdf = PG.scrivi_file(cartella, v["id"], originale, "pdf")
                    scritti.append(pdf)
                    rif = D.RIF_FILE + pdf
                if db.in_transaction:
                    db.commit()
                db.execute("BEGIN IMMEDIATE")
                if mid is None:
                    mid = db.execute(
                        "INSERT INTO studio_materiali (verifica, origine, titolo, riferimento, "
                        "creato) VALUES (?, ?, ?, ?, ?)",
                        (v["id"], origine, (" ".join(str(titolo).split())[:60] or None)
                         if titolo else None, rif, D.adesso())).lastrowid
                r = db.execute("SELECT COALESCE(MAX(p.ordine), 0) FROM studio_pagine p JOIN "
                               "studio_materiali m ON m.id = p.materiale WHERE m.verifica = ?",
                               (v["id"],)).fetchone()
                ordine = int(r[0])
                out = []
                for p, f in zip(pronte, scritti):
                    ordine += 1
                    pid = db.execute(
                        "INSERT INTO studio_pagine (materiale, ordine, stato, file, creata, "
                        "angoli, avvisi, nitidezza, larghezza, altezza) VALUES (?, ?, "
                        "'da_leggere', ?, ?, ?, ?, ?, ?, ?)",
                        (mid, ordine, f, D.adesso(),
                         json.dumps(p.angoli) if p.angoli else None,
                         D.j(p.avvisi) if p.avvisi else None, p.nitidezza, p.larghezza,
                         p.altezza)).lastrowid
                    out.append({"id": pid, "ordine": ordine, "bordi": p.bordi,
                                "avvisi": list(p.avvisi), "larghezza": p.larghezza,
                                "altezza": p.altezza})
                db.commit()
            except Exception:
                if db.in_transaction:
                    db.rollback()
                D.togli_file(scritti, cartella)
                raise
        self.misure["pagine"] = self.misure.get("pagine", 0) + len(out)
        for p in pronte:
            self.misure["bordi"][p.bordi] = self.misure["bordi"].get(p.bordi, 0) + 1
            for a in p.avvisi:
                self.misure["avvisi_pagine"][a] = self.misure["avvisi_pagine"].get(a, 0) + 1
        self._registra(f"verifica {v['id']}: {len(out)} pagine arrivate ({origine}, "
                       f"{self._chi_registro(chi, v['persona'])})")
        if self.lettore is not None:
            self.lettore.sveglia()
        return {"verifica": v["id"], "materiale": mid, "pagine": out}

    # ── argomenti (l'estrazione è del passo 4.4: qui il modello dei dati e la conferma) ──
    def aggiungi_argomento(self, chi, vid, titolo, pagine, proposto: bool = True,
                           avvisi=None) -> int:
        """Un argomento con le pagine che cita (id di `studio_pagine` della stessa verifica).
        `proposto` (dall'estrazione, da confermare) o aggiunto dalla persona."""
        self._scrivibile()
        v = self._verifica(chi, vid)
        sue = {p["id"] for p in self.pagine(chi, v["id"])}
        pag = [int(p) for p in pagine or ()]
        if any(p not in sue for p in pag):
            raise ValueError("una pagina non è di questa verifica")
        r = self.dati.uno("SELECT COALESCE(MAX(ordine), 0) AS o FROM studio_argomenti WHERE "
                          "verifica = ?", (v["id"],))
        aid = self.dati.scrivi(
            "INSERT INTO studio_argomenti (verifica, titolo, pagine, stato, ordine, avvisi, "
            "creato) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (v["id"], titolo_normale(titolo), D.j(dict.fromkeys(pag)),
             "proposto" if proposto else "aggiunto", int(r["o"]) + 1,
             D.j(avvisi) if avvisi else None, D.adesso()))
        if not proposto:
            self._ricalcola_sicuro(v["id"])
        return aid

    def argomenti(self, chi, vid) -> list[dict]:
        v = self._verifica(chi, vid)
        out = self.dati.tutti("SELECT * FROM studio_argomenti WHERE verifica = ? "
                              "ORDER BY ordine, id", (v["id"],))
        for a in out:
            a["pagine"] = D.da_j(a["pagine"])
            a["avvisi"] = D.da_j(a["avvisi"])
        return out

    def segna_argomento(self, chi, aid, tenuto: bool):
        """Tiene o toglie un argomento (anche dopo la conferma); il piano si ricalcola."""
        self._scrivibile()
        a = self.dati.uno("SELECT * FROM studio_argomenti WHERE id = ?", (int(aid),))
        if a is None:
            raise NonTrovata()
        v = self._verifica(chi, a["verifica"])
        self.dati.scrivi("UPDATE studio_argomenti SET stato = ? WHERE id = ?",
                         ("tenuto" if tenuto else "tolto", a["id"]))
        self._ricalcola_sicuro(v["id"])

    def conferma_argomenti(self, chi, vid) -> dict:
        """La conferma dell'elenco: gli argomenti ancora proposti diventano tenuti, la verifica
        passa da bozza ad aperta e il piano si calcola. Dal passo 4.4 (#283) un proposto con un
        avviso da decidere (`argomenti.DA_DECIDERE`: fuori dalle pagine citate, solo da pagine con
        istruzioni, titolo che è un ordine) resta proposto, fuori dal piano, finché la persona non
        lo tiene o lo toglie da solo: nel risultato `da_decidere` dice quanti sono."""
        from .argomenti import DA_DECIDERE
        self._scrivibile()
        v = self._verifica(chi, vid)
        da_decidere = 0
        with self.dati.lock:
            db = self.dati.db
            try:
                for a in db.execute("SELECT id, avvisi FROM studio_argomenti WHERE verifica = ? "
                                    "AND stato = 'proposto'", (v["id"],)).fetchall():
                    if set(D.da_j(a["avvisi"])) & set(DA_DECIDERE):
                        da_decidere += 1
                        continue
                    db.execute("UPDATE studio_argomenti SET stato = 'tenuto' WHERE id = ?",
                               (a["id"],))
                if v["stato"] == "bozza":
                    db.execute("UPDATE studio_verifiche SET stato = 'aperta' WHERE id = ?",
                               (v["id"],))
                db.commit()
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
        self.ricalcola_persona(v["persona"])
        return {**self.piano(chi, v["id"]), "da_decidere": da_decidere}

    def _argomento(self, chi, aid) -> tuple[dict, dict]:
        a = self.dati.uno("SELECT * FROM studio_argomenti WHERE id = ?", (int(aid),))
        if a is None:
            raise NonTrovata()
        return a, self._verifica(chi, a["verifica"])

    def rinomina_argomento(self, chi, aid, titolo):
        """Il titolo scritto dalla persona al posto di quello proposto (passo 4.4): lo stato
        resta, gli avvisi diventano quelli del controllo delle pagine sul titolo nuovo (la forma
        non conta più: il titolo è suo)."""
        from . import argomenti as A
        self._scrivibile()
        a, v = self._argomento(chi, aid)
        t = titolo_normale(titolo)
        avvisi = A.ricontrolla(t, [int(x) for x in D.da_j(a["pagine"])],
                               self.pagine(chi, v["id"]))
        self.dati.scrivi("UPDATE studio_argomenti SET titolo = ?, avvisi = ? WHERE id = ?",
                         (t, D.j(avvisi) if avvisi else None, a["id"]))
        self._ricalcola_sicuro(v["id"])

    def unisci_argomenti(self, chi, ids, titolo=None) -> int:
        """Più argomenti della stessa verifica in uno (passo 4.4): il primo resta, con le pagine
        di tutti e il titolo dato (o il suo), «tenuto»; gli altri si tolgono. L'id che resta."""
        from . import argomenti as A
        self._scrivibile()
        ids = list(dict.fromkeys(int(x) for x in ids or ()))
        if len(ids) < 2:
            raise ValueError("servono almeno due argomenti")
        righe = [self._argomento(chi, x) for x in ids]
        vid = righe[0][1]["id"]
        if any(v["id"] != vid for _a, v in righe):
            raise NonTrovata()
        primo = righe[0][0]
        t = titolo_normale(titolo) if titolo is not None else primo["titolo"]
        pagine = list(dict.fromkeys(int(p) for a, _v in righe for p in D.da_j(a["pagine"])))
        avvisi = A.ricontrolla(t, pagine, self.pagine(chi, vid))
        with self.dati.lock:
            db = self.dati.db
            try:
                db.execute("UPDATE studio_argomenti SET titolo = ?, pagine = ?, stato = 'tenuto', "
                           "avvisi = ? WHERE id = ?",
                           (t, D.j(pagine), D.j(avvisi) if avvisi else None, primo["id"]))
                for a, _v in righe[1:]:
                    db.execute("DELETE FROM studio_argomenti WHERE id = ?", (a["id"],))
                db.commit()
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
        self._ricalcola_sicuro(vid)
        return primo["id"]

    def rifai_argomenti(self, chi, vid):
        """«Rifai gli argomenti»: la prossima volta che la DGX è libera il lettore li chiede di
        nuovo; i proposti non decisi si sostituiscono, quelli decisi restano."""
        self._scrivibile()
        v = self._verifica(chi, vid)
        self.dati.scrivi("UPDATE studio_verifiche SET argomenti_firma = NULL, argomenti_esito = "
                         "NULL WHERE id = ?", (v["id"],))
        if self.lettore is not None:
            self.lettore.sveglia()

    def estrazione(self, chi, vid) -> dict:
        """Dove sono gli argomenti di una verifica (per la vista): l'esito dell'ultima estrazione
        e quando, se le pagine sono tutte lette e se gli argomenti vanno chiesti di nuovo."""
        from . import argomenti as A
        v = self._verifica(chi, vid)
        pagine = self.pagine(chi, v["id"])
        pronta = A.pronta(pagine)
        return {"esito": v.get("argomenti_esito"), "del": v.get("argomenti_del"),
                "pagine_lette": pronta,
                "da_fare": pronta and v.get("argomenti_firma") != A.firma(pagine),
                "accesa": bool(getattr(self.cfg, "studio_argomenti", True))
                and self.lettore is not None}

    # ── l'estrazione (dal lettore, studio/lettura.py; niente `chi`: è il lavoro di sfondo) ──
    def verifiche_per_argomenti(self) -> list[dict]:
        """Le verifiche in bozza o aperte con le pagine tutte lette (o illeggibili) e una firma
        diversa da quella dell'ultima estrazione, dalla più vicina. Vuoto con
        `studio_argomenti: false` o i dati in sola lettura."""
        from . import argomenti as A
        if not getattr(self.cfg, "studio_argomenti", True) or not self.dati.scrivibile:
            return []
        out = []
        for v in self.dati.tutti("SELECT * FROM studio_verifiche WHERE stato IN ('bozza', "
                                 "'aperta') ORDER BY data, id"):
            pagine = self._pagine_di(v["id"])
            if A.pronta(pagine) and v["argomenti_firma"] != A.firma(pagine):
                out.append({**v, "_pagine": pagine})
        return out

    def _pagine_di(self, vid) -> list[dict]:
        return self.dati.tutti(
            "SELECT p.* FROM studio_pagine p JOIN studio_materiali m ON m.id = p.materiale WHERE "
            "m.verifica = ? ORDER BY p.ordine, p.id", (int(vid),))

    def proponi_argomenti(self, vid, firma: str, proposte: list[dict], esito: str) -> int | None:
        """Scrive l'esito di un'estrazione: via i proposti non decisi, dentro i nuovi (tranne un
        titolo che la persona ha già tenuto, tolto o aggiunto), la firma e l'esito. Se intanto
        le pagine sono cambiate (o la verifica non c'è più) non scrive niente: None. Quanti
        proposti nuovi."""
        from . import argomenti as A
        with self.dati.lock:
            db = self.dati.db
            try:
                if db.in_transaction:
                    db.commit()
                db.execute("BEGIN IMMEDIATE")
                v = db.execute("SELECT * FROM studio_verifiche WHERE id = ? AND stato IN "
                               "('bozza', 'aperta')", (int(vid),)).fetchone()
                pagine = [dict(r) for r in db.execute(
                    "SELECT p.* FROM studio_pagine p JOIN studio_materiali m ON m.id = p.materiale"
                    " WHERE m.verifica = ?", (int(vid),))]
                if v is None or A.firma(pagine) != firma:
                    db.rollback()
                    return None
                vive = {int(p["id"]) for p in pagine if p["stato"] != "tolta"}
                db.execute("DELETE FROM studio_argomenti WHERE verifica = ? AND stato = "
                           "'proposto'", (int(vid),))
                decisi = {A.chiave(r["titolo"]) for r in db.execute(
                    "SELECT titolo FROM studio_argomenti WHERE verifica = ?", (int(vid),))}
                ordine = db.execute("SELECT COALESCE(MAX(ordine), 0) FROM studio_argomenti WHERE "
                                    "verifica = ?", (int(vid),)).fetchone()[0]
                n = 0
                for a in proposte:
                    if A.chiave(a["titolo"]) in decisi:
                        continue
                    ordine += 1
                    n += 1
                    db.execute("INSERT INTO studio_argomenti (verifica, titolo, pagine, stato, "
                               "ordine, avvisi, creato) VALUES (?, ?, ?, 'proposto', ?, ?, ?)",
                               (int(vid), titolo_normale(a["titolo"]),
                                D.j(p for p in a["pagine"] if p in vive), ordine,
                                D.j(a["avvisi"]) if a["avvisi"] else None, D.adesso()))
                db.execute("UPDATE studio_verifiche SET argomenti_firma = ?, argomenti_esito = ?,"
                           " argomenti_del = ? WHERE id = ?",
                           (firma, esito if esito != A.PROPOSTI or n else A.VUOTO, D.adesso(),
                            int(vid)))
                db.commit()
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
        return n

    # ── giorni ──
    def imposta_giorno(self, chi, giorno, minuti: int | None, motivo: str = "minuti",
                       persona=None):
        """Un giorno con minuti diversi per una persona: 0 = senza piano (giorno senza scuola,
        `motivo` «senza_scuola»); None toglie l'eccezione. Il piano si ricalcola."""
        self._scrivibile()
        persona = str(persona or getattr(chi, "id", "") or "")
        self._chi_puo(chi, persona)
        g = _data(giorno)
        if minuti is None:
            self.dati.scrivi("DELETE FROM studio_giorni WHERE persona = ? AND giorno = ?",
                             (persona, g.isoformat()))
        else:
            if not 0 <= int(minuti) <= 600:
                raise ValueError("i minuti vanno da 0 a 600")
            self.dati.scrivi(
                "INSERT INTO studio_giorni (persona, giorno, minuti, motivo) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(persona, giorno) DO UPDATE SET minuti = excluded.minuti, "
                "motivo = excluded.motivo", (persona, g.isoformat(), int(minuti), motivo))
        self.ricalcola_persona(persona)

    def salta_oggi(self, chi, persona=None):
        """«Non ce la faccio oggi»: oggi senza piano, le pagine passano ai giorni dopo."""
        self.imposta_giorno(chi, self._oggi(), 0, "saltato", persona=persona)

    def giorno_fatto(self, chi, vid, giorno=None, fatto: bool = True):
        """Il giorno del piano fatto (o non più fatto): le sue pagine restano lette."""
        self._scrivibile()
        v = self._verifica(chi, vid)
        g = _data(giorno or self._oggi())
        r = self.dati.uno("SELECT id FROM studio_piano WHERE verifica = ? AND giorno = ?",
                          (v["id"], g.isoformat()))
        if r is None:
            raise NonTrovata()
        self.dati.scrivi("UPDATE studio_piano SET fatto = ? WHERE id = ?",
                         (D.adesso() if fatto else None, r["id"]))
        self._ricalcola_sicuro(v["id"])

    # ── misure e previsione ──
    def aggiungi_misura(self, chi, vid, valore: float, fonte: str, argomento=None,
                        giorno=None) -> int:
        """Una misura vera della padronanza in % (dal passo 5: carte, verifica finta)."""
        self._scrivibile()
        v = self._verifica(chi, vid)
        if not 0 <= float(valore) <= 100:
            raise ValueError("la misura va da 0 a 100")
        return self.dati.scrivi(
            "INSERT INTO studio_misure (verifica, argomento, giorno, valore, fonte) "
            "VALUES (?, ?, ?, ?, ?)",
            (v["id"], argomento, _data(giorno or self._oggi()).isoformat(), float(valore),
             str(fonte)[:40]))

    # ── il piano ──
    def _minuti_base(self, persona: str):
        """La funzione giorno → minuti liberi della persona (senza dividere fra le verifiche)."""
        cfg = self.cfg
        fascia = self.fascia
        prof = self._profilo(persona)
        orari = []
        if prof is not None and _categoria(prof) == "minore":
            from .. import minori
            try:
                p = minori.preset(prof) or {}
            except Exception:  # noqa: BLE001
                p = {}
            orari = p.get("orari") or []
        senza = {P.giorno_della_settimana(x) for x in
                 getattr(cfg, "studio_giorni_senza_piano", None) or ()} - {None}
        eccezioni = {r["giorno"]: int(r["minuti"]) for r in self.dati.tutti(
            "SELECT giorno, minuti FROM studio_giorni WHERE persona = ?", (persona,))}
        adesso = self.adesso()
        oggi = adesso.date()

        def liberi(g: datetime.date) -> int:
            if g.isoformat() in eccezioni:
                return eccezioni[g.isoformat()]
            if g.weekday() in senza:
                return 0
            return P.minuti_liberi(fascia, orari, adesso.hour * 60 + adesso.minute
                                   if g == oggi else None)
        return liberi

    def ricalcola_persona(self, persona: str):
        for v in self.dati.tutti("SELECT id FROM studio_verifiche WHERE persona = ? AND "
                                 "stato IN ('aperta', 'fatta')", (str(persona),)):
            self._ricalcola_sicuro(v["id"])

    def _ricalcola_sicuro(self, vid) -> P.Piano | None:
        """`ricalcola` che non ferma mai le altre verifiche della persona né le letture: un
        errore va nel registro (col solo id) e nelle misure."""
        try:
            return self.ricalcola(vid)
        except Exception as e:  # noqa: BLE001
            self.misure["errori"] += 1
            self._registra(f"piano della verifica {vid} non ricalcolato: {type(e).__name__}")
            return None

    def _pagine_del_piano(self, vid) -> list[P.Pagina]:
        """Le pagine degli argomenti tenuti, una volta sola, senza quelle tolte."""
        argomenti = [a for a in self.dati.tutti(
            "SELECT * FROM studio_argomenti WHERE verifica = ?", (int(vid),))
            if a["stato"] in D.ARGOMENTI_DEL_PIANO]
        ids = {int(x) for a in argomenti for x in D.da_j(a["pagine"])
               if isinstance(x, int) or str(x).isdecimal()}
        righe = self.dati.tutti(
            "SELECT p.*, m.titolo AS materiale_titolo, m.id AS materiale_id FROM studio_pagine "
            "p JOIN studio_materiali m ON m.id = p.materiale WHERE m.verifica = ? AND "
            "p.stato != 'tolta'", (int(vid),))
        return [P.Pagina(r["id"], r["ordine"], r["numero"], r["etichetta"],
                         r["materiale_titolo"] or f"materiale {r['materiale_id']}")
                for r in righe if r["id"] in ids]

    def ricalcola(self, vid) -> P.Piano | None:
        """Ricalcola il piano di una verifica aperta, tenendo i giorni fatti. Con più verifiche
        aperte della stessa persona negli stessi giorni i minuti si dividono in parti uguali
        (solo con quelle che hanno pagine da leggere). Con i dati in sola lettura il piano si
        calcola e si restituisce senza salvarlo."""
        v = self.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (int(vid),))
        if v is None or v["stato"] not in ("aperta", "fatta"):
            return None
        oggi = self._oggi()
        data = _data(v["data"])
        # Passata: la verifica è fatta, il piano resta com'era (la storia)
        if data < oggi:
            if v["stato"] != "fatta" and self.dati.scrivibile:
                self.dati.scrivi("UPDATE studio_verifiche SET stato = 'fatta' WHERE id = ?",
                                 (v["id"],))
            return None
        liberi = self._minuti_base(v["persona"])
        # Una verifica aperta senza pagine da leggere non toglie minuti (revisione della PR
        # #308, nota 5)
        altre = [_data(x["data"]) for x in self.dati.tutti(
            "SELECT id, data FROM studio_verifiche WHERE persona = ? AND stato = 'aperta' AND "
            "id != ? AND data > ?", (v["persona"], v["id"], oggi.isoformat()))
            if self._pagine_del_piano(x["id"])]
        minuti_v = int(v["minuti_giorno"] if v["minuti_giorno"] is not None
                       else getattr(self.cfg, "studio_minuti_giorno", 45))
        minuti = {}
        for i in range((data - oggi).days):
            g = oggi + datetime.timedelta(days=i)
            k = 1 + sum(1 for d in altre if g < d)
            minuti[g] = min(minuti_v, liberi(g)) // k
        pagine = self._pagine_del_piano(v["id"])
        # I giorni fatti prima della data (spostata prima di un giorno fatto: quelli dopo non
        # contano più, revisione della PR #308, nota 11)
        fatti = self.dati.tutti("SELECT * FROM studio_piano WHERE verifica = ? AND "
                                "fatto IS NOT NULL AND giorno < ?", (v["id"], data.isoformat()))
        fatte = {int(p) for r in fatti if r["fase"] == P.STUDIO for p in D.da_j(r["pagine"])}
        giorni_fatti = {_data(r["giorno"]) for r in fatti}
        piano = P.calcola(oggi, data, pagine, minuti,
                          int(getattr(self.cfg, "studio_minuti_pagina", 10) or 10),
                          fatte=fatte, giorni_fatti=giorni_fatti)
        if not self.dati.scrivibile:
            return piano
        with self.dati.lock:
            db = self.dati.db
            try:
                db.execute("DELETE FROM studio_piano WHERE verifica = ? AND (fatto IS NULL OR "
                           "giorno >= ?)", (v["id"], data.isoformat()))
                for g in piano.giorni:
                    db.execute("INSERT INTO studio_piano (verifica, giorno, fase, pagine, "
                               "attivita, minuti, oltre) VALUES (?, ?, ?, ?, ?, ?, ?)",
                               (v["id"], g.giorno.isoformat(), g.fase, D.j(g.pagine),
                                g.attivita, g.minuti, int(g.oltre)))
                db.execute("UPDATE studio_verifiche SET piano_del = ?, piano_avvisi = ? "
                           "WHERE id = ?", (oggi.isoformat(), D.j(piano.avvisi), v["id"]))
                db.commit()
            except Exception:
                # Niente DELETE a metà lasciato alla prossima scrittura (nota 8)
                if db.in_transaction:
                    db.rollback()
                raise
        self._misura_piano(v["id"], piano)
        return piano

    def _piano_vivo(self, v: dict) -> tuple[list[dict], list[str], str]:
        """(giorni, avvisi, stato) del piano di oggi. Se va ricalcolato e i dati sono in sola
        lettura, i giorni fatti dal db e gli altri dal calcolo in memoria."""
        oggi = self._oggi()
        stato = v["stato"]
        avvisi = D.da_j(v["piano_avvisi"])
        calcolato = None
        if stato in ("aperta", "fatta") and v["piano_del"] != oggi.isoformat():
            calcolato = self._ricalcola_sicuro(v["id"])
            nuova = self.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (v["id"],))
            if nuova is not None:
                stato, avvisi = nuova["stato"], D.da_j(nuova["piano_avvisi"])
            if _data(v["data"]) < oggi:
                stato = "fatta"
        righe = self.dati.tutti("SELECT * FROM studio_piano WHERE verifica = ? ORDER BY giorno",
                                (v["id"],))
        if calcolato is not None and not self.dati.scrivibile:
            data = _data(v["data"]).isoformat()
            righe = [r for r in righe if r["fatto"] and r["giorno"] < data] + [
                {"id": None, "verifica": v["id"], "giorno": g.giorno.isoformat(),
                 "fase": g.fase, "pagine": D.j(g.pagine), "attivita": g.attivita,
                 "minuti": g.minuti, "oltre": int(g.oltre), "fatto": None}
                for g in calcolato.giorni]
            righe.sort(key=lambda r: r["giorno"])
            avvisi = list(calcolato.avvisi)
        for g in righe:
            g["pagine"] = D.da_j(g["pagine"])
            g["oltre"] = bool(g["oltre"])
        return righe, (avvisi if stato == "aperta" else []), stato

    def piano(self, chi, vid) -> dict:
        """Il piano di una verifica: i giorni (fatti compresi), gli avvisi, i giorni che
        mancano, l'obiettivo, le tappe e la previsione (solo dopo due misure vere)."""
        v = self._verifica(chi, vid)
        oggi = self._oggi()
        giorni, avvisi, stato = self._piano_vivo(v)
        fatte = {p_ for g in giorni if g["fatto"] and g["fase"] == P.STUDIO
                 for p_ in g["pagine"]}
        pag = self.pagine(chi, v["id"])
        ordine = {p_["id"]: p_["ordine"] for p_ in pag if p_["stato"] != "tolta"}
        args = [a for a in self.argomenti(chi, v["id"]) if a["stato"] in D.ARGOMENTI_DEL_PIANO]
        misure = [(_data(r["giorno"]), r["valore"]) for r in self.dati.tutti(
            "SELECT giorno, valore FROM studio_misure WHERE verifica = ? ORDER BY giorno, id",
            (v["id"],))]
        data = _data(v["data"])
        return {"verifica": v["id"], "stato": stato, "data": v["data"],
                "giorni_mancanti": (data - oggi).days, "obiettivo": v["obiettivo"],
                "giorni": giorni, "avvisi": avvisi,
                "tappe": P.tappe(args, ordine, fatte),
                "misure": len(misure), "livello": int(round(misure[-1][1])) if misure else None,
                "previsione": P.previsione(misure, data)}

    def oggi(self, chi, persona=None) -> list[dict]:
        """La riga «Oggi» di una persona: le attività di oggi di ogni verifica aperta."""
        persona = str(persona or getattr(chi, "id", "") or "")
        self._chi_puo(chi, persona)
        oggi = self._oggi()
        out = []
        for v in self.dati.tutti("SELECT * FROM studio_verifiche WHERE persona = ? AND "
                                 "stato = 'aperta' ORDER BY data, id", (persona,)):
            giorni, _avvisi, stato = self._piano_vivo(v)
            r = next((g for g in giorni if g["giorno"] == oggi.isoformat()), None)
            if r is not None and stato == "aperta":
                out.append({"verifica": v["id"], "materia": v["materia"], "data": v["data"],
                            "fase": r["fase"], "attivita": r["attivita"],
                            "minuti": r["minuti"], "fatto": bool(r["fatto"])})
        return out

    # ── registro e misure ──
    def _chi_registro(self, chi, persona) -> str:
        return "per sé" if getattr(chi, "id", None) == persona else "da un tutore"

    def _registra(self, riga: str):
        self.log(f"   [STUDIO] ({self.modo}) {riga}")

    def _misura_piano(self, vid, piano: P.Piano):
        m = self.misure
        m["piani"] += 1
        m["giorni_nei_piani"] += len(piano.giorni)
        m["pagine_nei_piani"] += sum(len(g.pagine) for g in piano.giorni if g.fase == P.STUDIO)
        m["giorni_oltre"] += sum(g.oltre for g in piano.giorni)
        for a in piano.avvisi:
            m["avvisi"][a] = m["avvisi"].get(a, 0) + 1
        studio = sum(g.fase == P.STUDIO for g in piano.giorni)
        self._registra(f"piano della verifica {vid}: {len(piano.giorni)} giorni ({studio} di "
                       f"studio), {piano.pagine_totali} pagine, {piano.pagine_fatte} lette, "
                       f"mancano {piano.giorni_mancanti} giorni"
                       + (f", avvisi {', '.join(piano.avvisi)}" if piano.avvisi else ""))

    def stato(self) -> dict:
        """Per `calliope stato` e le prove: il modo e le misure."""
        out = {"modo": self.modo, **{k: (dict(v) if isinstance(v, dict) else v)
                                     for k, v in self.misure.items()}}
        if self.lettore is not None:
            out["lettura"] = self.lettore.stato()
        return out
