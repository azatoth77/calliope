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

**Ricalcolo.** Il piano si ricalcola quando cambia qualcosa (argomenti confermati, data
spostata, minuti, giorno fatto o saltato, giorni senza scuola) e, alla prima lettura di un
giorno nuovo, perché «oggi» si è spostato.
"""

from __future__ import annotations

import datetime

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
TITOLO_MAX = 60


class NonPermesso(PermissionError):
    """Chi chiede non può vedere né cambiare lo Studio di quella persona."""


class NonTrovata(LookupError):
    """La verifica (o il materiale, la pagina, l'argomento) non c'è."""


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


def permesso(chi, proprietario) -> str | None:
    """«proprietario», «tutore» o None. Gli ospiti e i conoscenti mai, da nessuna parte."""
    if chi is None or proprietario is None:
        return None
    if _categoria(chi) in ("ospite", "conoscente") or \
            _categoria(proprietario) in ("ospite", "conoscente"):
        return None
    if getattr(chi, "id", None) and getattr(chi, "id", None) == getattr(proprietario, "id", None):
        return "proprietario"
    from .. import minori
    if _categoria(proprietario) == "minore" and minori.e_tutore(chi, proprietario):
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
    contro i titoli che sono ordini (decisione 0035, punto 6) arriva con il passo 4.4."""
    t = " ".join(str(testo or "").split())[:TITOLO_MAX]
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
        # Le misure dell'ombra (e dell'attivo): solo conti, niente nomi né titoli
        self.misure = {"verifiche_create": 0, "piani": 0, "giorni_nei_piani": 0,
                       "pagine_nei_piani": 0, "giorni_oltre": 0, "avvisi": {}}

    def close(self):
        self.dati.close()

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
        p = permesso(chi, prop)
        if p is None:
            raise NonPermesso("non è tuo")
        return p

    def _verifica(self, chi, vid) -> dict:
        v = self.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (int(vid),))
        if v is None:
            raise NonTrovata("verifica")
        try:
            self._chi_puo(chi, v["persona"])
        except NonPermesso:
            # Lo stesso rifiuto di una verifica che non c'è: non si sa se quella di un altro c'è
            raise NonTrovata("verifica") from None
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
        n = D.togli_file(file, getattr(self.cfg, "studio_cartella", None))
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
            raise NonTrovata("materiale")
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
            raise NonTrovata("pagina")
        _m, v = self._materiale(chi, p["materiale"])
        self.dati.scrivi("UPDATE studio_pagine SET stato = ? WHERE id = ?", (stato, p["id"]))
        self.ricalcola(v["id"])

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
            self.ricalcola(v["id"])
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
            raise NonTrovata("argomento")
        v = self._verifica(chi, a["verifica"])
        self.dati.scrivi("UPDATE studio_argomenti SET stato = ? WHERE id = ?",
                         ("tenuto" if tenuto else "tolto", a["id"]))
        self.ricalcola(v["id"])

    def conferma_argomenti(self, chi, vid) -> dict:
        """La conferma a mano: gli argomenti ancora proposti diventano tenuti, la verifica
        passa da bozza ad aperta e il piano si calcola."""
        self._scrivibile()
        v = self._verifica(chi, vid)
        with self.dati.lock:
            self.dati.db.execute("UPDATE studio_argomenti SET stato = 'tenuto' WHERE "
                                 "verifica = ? AND stato = 'proposto'", (v["id"],))
            if v["stato"] == "bozza":
                self.dati.db.execute("UPDATE studio_verifiche SET stato = 'aperta' WHERE id = ?",
                                     (v["id"],))
            self.dati.db.commit()
        self.ricalcola_persona(v["persona"])
        return self.piano(chi, v["id"])

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
            raise NonTrovata("giorno")
        self.dati.scrivi("UPDATE studio_piano SET fatto = ? WHERE id = ?",
                         (D.adesso() if fatto else None, r["id"]))
        self.ricalcola(v["id"])

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
        fascia = P.fascia_valida(getattr(cfg, "studio_fascia", "")) or P.fascia_valida(
            "15:00-20:00")
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
            self.ricalcola(v["id"])

    def ricalcola(self, vid) -> P.Piano | None:
        """Ricalcola il piano di una verifica aperta, tenendo i giorni fatti. Con più verifiche
        aperte della stessa persona negli stessi giorni i minuti si dividono in parti uguali."""
        v = self.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (int(vid),))
        if v is None or v["stato"] not in ("aperta", "fatta"):
            return None
        oggi = self._oggi()
        data = _data(v["data"])
        # Passata: la verifica è fatta, il piano resta com'era (la storia)
        if data < oggi:
            if v["stato"] != "fatta":
                self.dati.scrivi("UPDATE studio_verifiche SET stato = 'fatta' WHERE id = ?",
                                 (v["id"],))
            return None
        liberi = self._minuti_base(v["persona"])
        altre = [(_data(x["data"])) for x in self.dati.tutti(
            "SELECT data FROM studio_verifiche WHERE persona = ? AND stato = 'aperta' AND "
            "id != ? AND data > ?", (v["persona"], v["id"], oggi.isoformat()))]
        minuti_v = int(v["minuti_giorno"] if v["minuti_giorno"] is not None
                       else getattr(self.cfg, "studio_minuti_giorno", 45))
        minuti = {}
        for i in range((data - oggi).days):
            g = oggi + datetime.timedelta(days=i)
            k = 1 + sum(1 for d in altre if g < d)
            minuti[g] = min(minuti_v, liberi(g)) // k
        # Le pagine degli argomenti tenuti, una volta sola, senza quelle tolte
        argomenti = [a for a in self.dati.tutti(
            "SELECT * FROM studio_argomenti WHERE verifica = ?", (v["id"],))
            if a["stato"] in D.ARGOMENTI_DEL_PIANO]
        ids = {int(p) for a in argomenti for p in D.da_j(a["pagine"])}
        righe = self.dati.tutti(
            "SELECT p.*, m.titolo AS materiale_titolo FROM studio_pagine p JOIN studio_materiali"
            " m ON m.id = p.materiale WHERE m.verifica = ? AND p.stato != 'tolta'", (v["id"],))
        pagine = [P.Pagina(r["id"], r["ordine"], r["numero"],
                           r["etichetta"] or r["materiale_titolo"]) for r in righe
                  if r["id"] in ids]
        fatti = self.dati.tutti("SELECT * FROM studio_piano WHERE verifica = ? AND "
                                "fatto IS NOT NULL", (v["id"],))
        fatte = {int(p) for r in fatti if r["fase"] == P.STUDIO for p in D.da_j(r["pagine"])}
        giorni_fatti = {_data(r["giorno"]) for r in fatti}
        piano = P.calcola(oggi, data, pagine, minuti,
                          int(getattr(self.cfg, "studio_minuti_pagina", 10) or 10),
                          fatte=fatte, giorni_fatti=giorni_fatti)
        with self.dati.lock:
            db = self.dati.db
            db.execute("DELETE FROM studio_piano WHERE verifica = ? AND fatto IS NULL",
                       (v["id"],))
            for g in piano.giorni:
                db.execute("INSERT INTO studio_piano (verifica, giorno, fase, pagine, attivita, "
                           "minuti, oltre) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (v["id"], g.giorno.isoformat(), g.fase, D.j(g.pagine), g.attivita,
                            g.minuti, int(g.oltre)))
            db.execute("UPDATE studio_verifiche SET piano_del = ?, piano_avvisi = ? WHERE id = ?",
                       (oggi.isoformat(), D.j(piano.avvisi), v["id"]))
            db.commit()
        self._misura_piano(v["id"], piano)
        return piano

    def piano(self, chi, vid) -> dict:
        """Il piano di una verifica: i giorni (fatti compresi), gli avvisi, i giorni che
        mancano, l'obiettivo, le tappe e la previsione (solo dopo due misure vere)."""
        v = self._verifica(chi, vid)
        oggi = self._oggi()
        if v["stato"] in ("aperta", "fatta") and v["piano_del"] != oggi.isoformat():
            self.ricalcola(v["id"])
            v = self._verifica(chi, vid)
        avvisi = D.da_j(v["piano_avvisi"]) if v["stato"] == "aperta" else []
        giorni = self.dati.tutti("SELECT * FROM studio_piano WHERE verifica = ? "
                                 "ORDER BY giorno", (v["id"],))
        for g in giorni:
            g["pagine"] = D.da_j(g["pagine"])
            g["oltre"] = bool(g["oltre"])
        fatte = {p_ for g in giorni if g["fatto"] and g["fase"] == P.STUDIO
                 for p_ in g["pagine"]}
        pag = self.pagine(chi, v["id"])
        ordine = {p_["id"]: p_["ordine"] for p_ in pag if p_["stato"] != "tolta"}
        args = [a for a in self.argomenti(chi, v["id"]) if a["stato"] in D.ARGOMENTI_DEL_PIANO]
        misure = [(_data(r["giorno"]), r["valore"]) for r in self.dati.tutti(
            "SELECT giorno, valore FROM studio_misure WHERE verifica = ? ORDER BY giorno, id",
            (v["id"],))]
        data = _data(v["data"])
        return {"verifica": v["id"], "stato": v["stato"], "data": v["data"],
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
            if v["piano_del"] != oggi.isoformat():
                self.ricalcola(v["id"])
            r = self.dati.uno("SELECT * FROM studio_piano WHERE verifica = ? AND giorno = ?",
                              (v["id"], oggi.isoformat()))
            if r is not None:
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
        return {"modo": self.modo, **{k: (dict(v) if isinstance(v, dict) else v)
                                      for k, v in self.misure.items()}}
