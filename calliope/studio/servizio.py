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

**Resoconto e riepilogo** (30/10, passo 4b, #244): `resoconto` (un giorno di una verifica) e
`riepilogo` (la preparazione di una verifica) sono proiezioni degli eventi `studio_eventi`, del
piano, delle pagine, degli argomenti e delle misure (`resoconto.py`): niente modello, niente
testo di un modello. Gli eventi li scrivono le azioni stesse: «inizio» (`imposta_sessione`, senza
le risposte), «fatto»/«non_fatto» (`giorno_fatto`), «saltato» (`salta_oggi`), «spostata»
(`imposta`) e «mancato» (`ricalcola`, prima di togliere un giorno passato non fatto).

**Padronanza** (30/10, passo 5, #245): `registra_tentativo` scrive un tentativo su un argomento
(dalle carte e dalla verifica finta, quando arrivano); `padronanza` la calcola dai soli tentativi
(`padronanza.py`), con le lacune e la lezione successiva. Con `studio_padronanza: ombra` (di
serie) si calcola e si misura soltanto; con «mostrata» va sulla home, nel riepilogo e nella
previsione.

**Carte** (30/10, passo 6, #246): le carte di una verifica (`carte.py`), scritte dalla persona o
dal tutore (la generazione dal lettore arriva con la seconda parte del passo), si ripassano con
Leitner a cinque scatole; ogni esito («la sapevo», «quasi», «non la sapevo», o il confronto del
codice per le risposte chiuse) è un tentativo di tipo «carta» sull'argomento. Il testo è un dato:
textContent sullo schermo, in busta al modello (`tools/studio.py`, `studio_carte`).

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

from . import carte as C
from . import dati as D
from . import piano as P
from . import padronanza as PD
from . import resoconto as R
from .mappe import Mappe

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


# Senza lettore (passo 4.5, nota della revisione della PR #314): la frase della pagina e della voce
FRASI_LETTURA = {
    "senza_modello": "La lettura delle pagine qui non è disponibile: le leggo quando c'è il "
                     "modello che vede.",
    "spenta": "La lettura delle pagine è spenta: le pagine restano da leggere.",
}
# Le due domande prima della sessione (passo 4.5, spunto approvato il 28/10): quanto conosci
# l'argomento (5 livelli) e come ti senti oggi (6 stati), come nell'app guardata il 28/10
CONOSCENZA = ("è nuovo per me", "ne so poco", "abbastanza", "lo so bene", "sono sicuro")
UMORI = ("pronto", "curioso", "tranquillo", "neutrale", "poca energia", "stressato")
SESSIONE_S = 3 * 3600
# Una carta chiesta a voce resta «in corso» solo nel turno subito dopo la domanda o la risposta
# (revisione della PR #324, nota 1), e al più tanto tempo, anche oltre la mezzanotte (nota 4)
CARTA_IN_CORSO_S = 30 * 60


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


class Studio(Mappe):
    """Lo Studio di questa installazione: un oggetto per processo. Le mappe concettuali (passo 7,
    #247) sono in `mappe.py`."""

    def __init__(self, cfg, registry=None, log=print, adesso=None):
        self.cfg = cfg
        self.registry = registry
        self.log = log
        self.modo = modo(cfg)
        m = str(getattr(cfg, "studio_padronanza", PD.OMBRA) or PD.OMBRA).strip().lower()
        self.modo_padronanza = m if m in PD.MODI else PD.OMBRA
        # L'orologio (le prove lo fingono)
        self.adesso = adesso or datetime.datetime.now
        self.dati = D.Dati(cfg.memory_db)
        # All'avvio via i provvisori di un crollo (PR #312), solo quelli più vecchi di
        # `PROVVISORI_AVVIO_S` (terza revisione della PR #312, fatto con la 4.5): un'altra
        # istanza sullo stesso disco (le prove, un riavvio veloce) può star dividendo un PDF adesso
        try:
            D.togli_provvisori(D.cartella_di(cfg), D.PROVVISORI_AVVIO_S)
        except OSError:
            pass
        # Le misure dell'ombra (e dell'attivo): solo conti, niente nomi né titoli
        self.misure = {"verifiche_create": 0, "piani": 0, "giorni_nei_piani": 0,
                       "pagine_nei_piani": 0, "giorni_oltre": 0, "avvisi": {}, "errori": 0,
                       # Le pagine arrivate (passo 4.2): da dove vengono i bordi e gli avvisi
                       "pagine": 0, "bordi": {}, "avvisi_pagine": {},
                       # La padronanza (passo 5): tentativi, misure del giorno, parole
                       "padronanza": {"tentativi": 0, "misure_giorno": 0, "parole": {}},
                       # Le carte (passo 6): quante scritte e gli esiti, da dove (mai il testo)
                       "carte": {"scritte": 0, "esiti": {}, "codice": 0, "a_voce": 0},
                       # Le mappe (passo 7, #247): quante, i controlli, i tentativi (mai il testo)
                       "mappe": {"scheletri": 0, "mie": 0, "memoria": 0, "controlli": 0,
                                 "tentativi": 0, "carte": 0,
                                 # La mappa libera e «Parliamone» (passo 7c, #328): conti,
                                 # mai testi; «svelati» deve restare 0
                                 "libere": 0, "finite": 0, "indizi": 0, "mostrati": 0,
                                 "consigli": 0, "svelati": 0}}
        # Il lettore delle pagine (passo 4.3, studio/lettura.py): lo crea `avvia_lettura`
        self.lettore = None
        # Perché non c'è il lettore (passo 4.5, nota della revisione della PR #314): None prima di
        # `avvia_lettura`, «spenta» con `studio_lettura: false`, «senza_modello» senza vLLM
        self.lettura_motivo: str | None = None
        # Le due domande prima della sessione (passo 4.5): in memoria, mai su disco, mai ai tutori
        # (decisione 0035, punto 27). {persona: {verifica, conoscenza, umore, fino}}
        self._sessioni: dict = {}
        # La carta chiesta a voce a una persona (passo 6, #246): {persona: {carta, verifica,
        # turno, fino}}. In memoria: l'esito detto dopo vale per lei, una volta sola
        self._carte_in_corso: dict = {}
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
            self.lettura_motivo = (None if self.lettore is not None else
                                   "spenta" if not getattr(self.cfg, "studio_lettura", True)
                                   else "senza_modello")
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
        frase = FRASI_LETTURA.get(self.lettura_motivo or "") if lett is None else None
        return {"verifica": v["id"], "totali": len(righe), "lette": conta.get("letta", 0),
                "illeggibili": conta.get("illeggibile", 0),
                "in_lettura": conta.get("in_lettura", 0), "da_parte": conta.get("da_parte", 0),
                "da_leggere": conta.get("da_leggere", 0), "avvisi": avvisi,
                "lettore": lett is not None,
                "in_attesa": bool(lett is not None and lett.in_attesa),
                # Senza lettore la pagina e la voce lo dicono (revisione della PR #314): mai un
                # «da leggere» muto. Solo se ci sono pagine che aspettano
                "frase": frase if frase and conta.get("da_leggere") else None}

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
        with self.dati.lock:
            db = self.dati.db
            try:
                db.execute(f"UPDATE studio_verifiche SET {sets} WHERE id = ?",
                           (*campi.values(), v["id"]))
                if "data" in campi and campi["data"] != v["data"]:
                    # La storia dello spostamento (passo 4b, #244): la data di prima e la nuova
                    self._evento(db, v, "spostata", self._oggi(), chi,
                                 da=v["data"], a=campi["data"])
                db.commit()
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
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
        non conta più: il titolo è suo). Il titolo del modello resta in `titolo_modello`: un
        proposto rinominato è una decisione della persona, che un'estrazione nuova non toglie, e il
        titolo del modello non si ripropone accanto (revisione della PR #315)."""
        from . import argomenti as A
        self._scrivibile()
        a, v = self._argomento(chi, aid)
        t = titolo_normale(titolo)
        avvisi = A.ricontrolla(t, [int(x) for x in D.da_j(a["pagine"])],
                               self.pagine(chi, v["id"]))
        self.dati.scrivi("UPDATE studio_argomenti SET titolo = ?, avvisi = ?, titolo_modello = "
                         "COALESCE(titolo_modello, ?) WHERE id = ?",
                         (t, D.j(avvisi) if avvisi else None, a["titolo"], a["id"]))
        self._ricalcola_sicuro(v["id"])

    def unisci_argomenti(self, chi, ids, titolo=None) -> int:
        """Più argomenti della stessa verifica in uno (passo 4.4): il primo resta, con le pagine
        di tutti e il titolo dato (o il suo), «tenuto»; gli altri diventano «tolti» con l'avviso
        «unito». L'id che resta."""
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
                    # Tolti con l'avviso «unito», non cancellati (seconda revisione della PR
                    # #315): restano fra i «decisi» col loro titolo e quello del modello, così
                    # una nuova estrazione non li ripropone e la conferma non li rimette nel piano
                    av = [x for x in D.da_j(a["avvisi"]) if x != A.UNITO] + [A.UNITO]
                    db.execute("UPDATE studio_argomenti SET stato = 'tolto', avvisi = ? WHERE "
                               "id = ?", (D.j(av), a["id"]))
                    # I tentativi e le carte degli uniti passano a quello che resta (passo 6,
                    # nota 2 della revisione della PR #323): la padronanza non li perde
                    for t in ("studio_tentativi", "studio_carte"):
                        db.execute(f"UPDATE {t} SET argomento = ? WHERE verifica = ? AND "
                                   "argomento = ?", (primo["id"], vid, a["id"]))
                db.commit()
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
        self._ricalcola_sicuro(vid)
        if self.modo_padronanza != PD.SPENTA:
            try:
                self._misura_padronanza(righe[0][1])
            except Exception as e:  # noqa: BLE001 — la misura non ferma l'unione
                self.misure["errori"] += 1
                self._registra(f"misura della padronanza non scritta: {type(e).__name__}")
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
        nl = A.non_lette(pagine)
        return {"esito": v.get("argomenti_esito"), "del": v.get("argomenti_del"),
                "pagine_lette": pronta,
                # Le pagine illeggibili o da parte, fuori dagli argomenti (PR #315)
                "pagine_non_lette": nl, "avvisi": ["pagine_non_lette"] if nl else [],
                "da_fare": pronta and v.get("argomenti_firma") != A.firma(pagine),
                "accesa": bool(getattr(self.cfg, "studio_argomenti", True))
                and self.lettore is not None}

    # ── l'estrazione (dal lettore, studio/lettura.py; niente `chi`: è il lavoro di sfondo) ──
    def verifiche_per_argomenti(self) -> list[dict]:
        """Le verifiche in bozza o aperte con le pagine tutte lette (o illeggibili, o da parte) e una firma
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
        """Scrive l'esito di un'estrazione: via i proposti non decisi (un proposto rinominato è
        deciso), dentro i nuovi (tranne un titolo che la persona ha già tenuto, tolto, aggiunto o
        rinominato, anche col titolo di prima), la firma e l'esito. Con «rotto» o «errore» restano
        i proposti di prima e si scrivono solo firma ed esito. Se intanto
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
                if esito in (A.ROTTO, A.ERRORE):
                    # Un'estrazione fallita non svuota niente (revisione della PR #315): restano
                    # i proposti di prima, e si scrivono solo la firma e l'esito
                    proposte = []
                else:
                    # Via i proposti che la persona non ha toccato; un proposto rinominato
                    # (titolo diverso da quello del modello) è una sua decisione e resta
                    for r in db.execute("SELECT id, titolo, titolo_modello FROM studio_argomenti "
                                        "WHERE verifica = ? AND stato = 'proposto'",
                                        (int(vid),)).fetchall():
                        if not A.rinominato(r["titolo"], r["titolo_modello"]):
                            db.execute("DELETE FROM studio_argomenti WHERE id = ?", (r["id"],))
                # I titoli decisi: quelli che restano e quelli del modello sotto una rinomina, che
                # non si ripropongono accanto al titolo della persona
                decisi = set()
                for r in db.execute("SELECT titolo, titolo_modello FROM studio_argomenti WHERE "
                                    "verifica = ?", (int(vid),)):
                    decisi |= {A.chiave(r["titolo"]), A.chiave(r["titolo_modello"])} - {""}
                ordine = db.execute("SELECT COALESCE(MAX(ordine), 0) FROM studio_argomenti WHERE "
                                    "verifica = ?", (int(vid),)).fetchone()[0]
                n = 0
                for a in proposte:
                    if A.chiave(a["titolo"]) in decisi:
                        continue
                    ordine += 1
                    n += 1
                    t = titolo_normale(a["titolo"])
                    db.execute("INSERT INTO studio_argomenti (verifica, titolo, pagine, stato, "
                               "ordine, avvisi, creato, titolo_modello) VALUES (?, ?, ?, "
                               "'proposto', ?, ?, ?, ?)",
                               (int(vid), t,
                                D.j(p for p in a["pagine"] if p in vive), ordine,
                                D.j(a["avvisi"]) if a["avvisi"] else None, D.adesso(), t))
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
        """«Non ce la faccio oggi»: oggi senza piano, le pagine passano ai giorni dopo. Per ogni
        verifica che oggi aveva un giorno del piano non fatto resta l'evento «saltato» (passo 4b,
        #244), con le pagine e i minuti che erano previsti: il ricalcolo toglie quella riga."""
        persona = str(persona or getattr(chi, "id", "") or "")
        self._chi_puo(chi, persona)
        oggi = self._oggi().isoformat()
        righe = self.dati.tutti(
            "SELECT p.*, v.persona FROM studio_piano p JOIN studio_verifiche v ON v.id = "
            "p.verifica WHERE v.persona = ? AND v.stato = 'aperta' AND p.giorno = ? AND "
            "p.fatto IS NULL", (persona, oggi))
        self.imposta_giorno(chi, self._oggi(), 0, "saltato", persona=persona)
        with self.dati.lock:
            db = self.dati.db
            try:
                for r in righe:
                    if not db.execute("SELECT 1 FROM studio_eventi WHERE verifica = ? AND "
                                      "giorno = ? AND tipo = 'saltato'",
                                      (r["verifica"], oggi)).fetchone():
                        self._evento(db, {"id": r["verifica"], "persona": r["persona"]},
                                     "saltato", oggi, chi, pagine=D.da_j(r["pagine"]),
                                     minuti=r["minuti"], fase=r["fase"])
                db.commit()
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise

    def giorno_fatto(self, chi, vid, giorno=None, fatto: bool = True):
        """Il giorno del piano fatto (o non più fatto): le sue pagine restano lette. Il giorno
        segnato (AAAA-MM-GG). Dopo mezzanotte (revisione della PR #321, nota 1): senza giorno, o
        con oggi, se chi segna ha cominciato ieri una sessione su questa verifica nelle ultime 3
        ore e oggi no, «fatto» va a ieri (la sessione delle 23:40 chiusa alle 00:10)."""
        self._scrivibile()
        v = self._verifica(chi, vid)
        g = _data(giorno or self._oggi())
        if fatto and g == self._oggi():
            # Di chiunque (#322, caso 2): il tutore fa «Inizia», il minore «Fatto»; come il ricalcolo
            ieri = self._sessione_aperta_ieri(v["id"])
            if ieri is not None:
                g = ieri
        r = self.dati.uno("SELECT * FROM studio_piano WHERE verifica = ? AND giorno = ?",
                          (v["id"], g.isoformat()))
        if r is None:
            raise NonTrovata()
        # Un giorno già fatto resta con la sua ora (la fine della sessione, per il resoconto)
        if bool(r["fatto"]) != bool(fatto):
            with self.dati.lock:
                db = self.dati.db
                try:
                    db.execute("UPDATE studio_piano SET fatto = ? WHERE id = ?",
                               (self.adesso().isoformat(timespec="seconds") if fatto else None,
                                r["id"]))
                    # L'evento con le pagine e i minuti previsti di quel giorno (passo 4b, #244):
                    # il resoconto resta anche se il piano cambia dopo
                    self._evento(db, v, "fatto" if fatto else "non_fatto", g, chi,
                                 pagine=D.da_j(r["pagine"]), minuti=r["minuti"], fase=r["fase"])
                    db.commit()
                except Exception:
                    if db.in_transaction:
                        db.rollback()
                    raise
        self._ricalcola_sicuro(v["id"])
        return g.isoformat()

    def _sessione_aperta_ieri(self, vid, chi_id=None) -> datetime.date | None:
        """Ieri, se ieri c'è un «inizio» su questa verifica (di `chi_id`, se dato) nelle ultime
        `SESSIONE_S`, nessun «inizio» oggi e il giorno di ieri del piano non è fatto: la sessione
        cominciata prima di mezzanotte è ancora quella. Altrimenti None."""
        adesso = self.adesso()
        oggi = adesso.date()
        ieri = oggi - datetime.timedelta(days=1)
        da = (adesso - datetime.timedelta(seconds=SESSIONE_S)).isoformat(timespec="seconds")
        q = ("SELECT giorno, chi FROM studio_eventi WHERE verifica = ? AND tipo = 'inizio' AND "
             "giorno >= ?")
        inizi = self.dati.tutti(q, (int(vid), ieri.isoformat()))
        if chi_id is not None:
            inizi = [e for e in inizi if e["chi"] == chi_id]
        if any(e["giorno"] == oggi.isoformat() for e in inizi):
            return None
        tutti = self.dati.tutti(q + " AND ora >= ?", (int(vid), ieri.isoformat(), da))
        if not any(e["giorno"] == ieri.isoformat() and (chi_id is None or e["chi"] == chi_id)
                   for e in tutti):
            return None
        r = self.dati.uno("SELECT fatto FROM studio_piano WHERE verifica = ? AND giorno = ?",
                          (int(vid), ieri.isoformat()))
        return ieri if r is not None and not r["fatto"] else None

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

    # ── la padronanza (30/10, passo 5, #245; decisione 0035 punto 32) ──
    def padronanza_mostrata(self) -> bool:
        """La padronanza va alla persona (home, riepilogo, previsione)? Solo «mostrata» e con lo
        Studio per gli schermi e il modello."""
        return self.modo_padronanza == PD.MOSTRATA and self.per_schermi()

    def registra_tentativo(self, chi, vid, argomento, tipo: str, esito: str,
                           fonte: str = "persona", giorno=None, carta=None) -> int:
        """Un tentativo su un argomento della verifica: `tipo` in `padronanza.TIPI`, `esito` in
        `padronanza.ESITI`, `fonte` (chi ha deciso l'esito) in `padronanza.FONTI`, mai il modello
        da solo. Solo codici e id: nessun testo. Poi la misura del giorno. L'id del tentativo.
        Dal passo 6 (#246, note 1 e 6 della revisione della PR #323): un giorno dopo oggi è
        rifiutato, e la fonte deve essere di chi registra («persona» solo la persona della
        verifica, «tutore» solo il suo tutore, «codice» tutti e due); `carta` è la carta da cui
        viene."""
        self._scrivibile()
        if self.modo_padronanza == PD.SPENTA:
            raise ValueError("la padronanza è spenta")
        v = self._verifica(chi, vid)
        if tipo not in PD.TIPI or esito not in PD.ESITI or fonte not in PD.FONTI:
            raise ValueError("tentativo sconosciuto")
        ruolo = self._chi_puo(chi, v["persona"])
        if (fonte == "persona" and ruolo != "proprietario") or (
                fonte == "tutore" and ruolo != "tutore"):
            raise ValueError("la fonte non è di chi registra")
        a = self.dati.uno("SELECT id FROM studio_argomenti WHERE id = ? AND verifica = ?",
                          (int(argomento), v["id"]))
        if a is None:
            raise NonTrovata()
        adesso = self.adesso()
        g = _data(giorno or adesso.date())
        if g > adesso.date():
            # Un tentativo datato nel futuro non conta per la padronanza di oggi (nota 1)
            raise ValueError("il giorno è dopo oggi")
        tid = self.dati.scrivi(
            "INSERT INTO studio_tentativi (verifica, persona, argomento, giorno, ora, tipo, esito, "
            "fonte, chi, carta) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (v["id"], str(v["persona"]), a["id"], g.isoformat(),
             adesso.isoformat(timespec="seconds"), tipo, esito, fonte,
             getattr(chi, "id", None), int(carta) if carta is not None else None))
        self.misure["padronanza"]["tentativi"] += 1
        try:
            self._misura_padronanza(v)
        except Exception as e:  # noqa: BLE001 — la misura non ferma il tentativo
            self.misure["errori"] += 1
            self._registra(f"misura della padronanza non scritta: {type(e).__name__}")
        return tid

    def _argomenti_numerati(self, vid) -> list[dict]:
        """Gli argomenti del piano col numero che si dice a voce (la posizione nell'elenco intero
        della verifica, come `tieni` e `togli` del tool)."""
        elenco = self.dati.tutti("SELECT * FROM studio_argomenti WHERE verifica = ? "
                                 "ORDER BY ordine, id", (int(vid),))
        return [{"id": a["id"], "numero": i, "titolo": a["titolo"],
                 "pagine": [int(x) for x in D.da_j(a["pagine"]) if str(x).isdecimal()]}
                for i, a in enumerate(elenco, 1) if a["stato"] in D.ARGOMENTI_DEL_PIANO]

    def _padronanza_di(self, vid) -> tuple[list[dict], dict]:
        tent = self.dati.tutti("SELECT argomento, giorno, tipo, esito FROM studio_tentativi "
                               "WHERE verifica = ?", (int(vid),))
        return self._argomenti_numerati(vid), PD.calcola(tent, self._oggi())

    def padronanza(self, chi, vid) -> dict:
        """La padronanza degli argomenti del piano di una verifica, dai soli tentativi: per
        argomento la cifra (o None, «non ancora misurata») con la parola, le lacune (sotto
        l'obiettivo, dal più debole, con la lezione successiva dal piano) e il livello del giorno
        (la media degli argomenti misurati, se lo sono almeno la metà). Permessi come il resto
        dello Studio; chi la mostra decide con `padronanza_mostrata`."""
        return self._padronanza(self._verifica(chi, vid))

    def _padronanza(self, v: dict) -> dict:
        args, pad = self._padronanza_di(v["id"])
        giorni = self.dati.tutti("SELECT * FROM studio_piano WHERE verifica = ? ORDER BY giorno",
                                 (v["id"],))
        for g in giorni:
            g["pagine"] = D.da_j(g["pagine"])
        vuota = {"valore": None, "parola": PD.NON_MISURATA_P, "tentativi": 0}
        return {"verifica": v["id"], "modo": self.modo_padronanza,
                "obiettivo": v["obiettivo"],
                "argomenti": [{"id": a["id"], "numero": a["numero"],
                               **{k: pad.get(a["id"], vuota)[k]
                                  for k in ("valore", "parola", "tentativi")}} for a in args],
                "lacune": PD.lacune(args, pad, int(v["obiettivo"]), giorni, self._oggi()),
                "livello": PD.livello([a["id"] for a in args], pad)}

    def _misura_padronanza(self, v: dict):
        """La misura del giorno della verifica dalla padronanza, una per giorno (si riscrive):
        con la fonte «padronanza» se mostrata (entra nella forbice), «padronanza_ombra» in ombra
        (la previsione la ignora). Nel registro solo i conti, senza nomi né titoli."""
        args, pad = self._padronanza_di(v["id"])
        lv = PD.livello([a["id"] for a in args], pad)
        parole = {}
        for a in args:
            p = pad.get(a["id"])
            k = p["parola"] if p else PD.NON_MISURATA_P
            parole[k] = parole.get(k, 0) + 1
        self.misure["padronanza"]["parole"] = parole
        self._registra(f"padronanza della verifica {v['id']}: "
                       + ", ".join(f"{k} {n}" for k, n in sorted(parole.items()))
                       + (f", livello {lv}" if lv is not None else ", livello non misurato"))
        if not self.dati.scrivibile:
            return
        oggi = self._oggi().isoformat()
        fonte = PD.FONTE_MISURA if self.modo_padronanza == PD.MOSTRATA else PD.FONTE_OMBRA
        with self.dati.lock:
            db = self.dati.db
            try:
                db.execute("DELETE FROM studio_misure WHERE verifica = ? AND giorno = ? AND "
                           "fonte IN (?, ?)", (v["id"], oggi, PD.FONTE_MISURA, PD.FONTE_OMBRA))
                # Il livello tornato a None (un argomento unito, un argomento che rientra nel
                # piano e abbassa la metà dei misurati) toglie la misura di oggi invece di
                # lasciare quella di prima (nota 4 della revisione della PR #323)
                if lv is not None:
                    db.execute("INSERT INTO studio_misure (verifica, giorno, valore, fonte) "
                               "VALUES (?, ?, ?, ?)", (v["id"], oggi, float(lv), fonte))
                db.commit()
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
        if lv is not None:
            self.misure["padronanza"]["misure_giorno"] += 1

    # ── le carte (30/10, passo 6, #246; decisione 0035 punto 33) ──
    def _carta(self, chi, cid) -> tuple[dict, dict]:
        c = self.dati.uno("SELECT * FROM studio_carte WHERE id = ?", (int(cid),))
        if c is None:
            raise NonTrovata()
        # Una carta nata dalla mappa («Fanne carte», origine «mappa») con la mappa libera aperta
        # non c'è per la persona (revisione della PR #330): dice i concetti dello scheletro
        # nascosto. Vale anche per `carta_in_corso`, che passa di qui. Il tutore la vede e la
        # corregge (seconda revisione)
        if (c["origine"] == "mappa" and getattr(chi, "id", None) == c["persona"]
                and self._libera_aperta(c["verifica"])):
            raise NonTrovata()
        return c, self._verifica(chi, c["verifica"])

    def _argomento_di(self, v: dict, argomento) -> int | None:
        """L'argomento di una carta: None, o uno della stessa verifica (non c'è → NonTrovata)."""
        if argomento is None:
            return None
        a = self.dati.uno("SELECT id FROM studio_argomenti WHERE id = ? AND verifica = ?",
                          (int(argomento), v["id"]))
        if a is None:
            raise NonTrovata()
        return a["id"]

    def aggiungi_carta(self, chi, vid, domanda, risposta, argomento=None, pagine=(),
                       origine: str = "persona", avvisi=None) -> int:
        """Una carta nuova (domanda e risposta: un dato, chiunque l'abbia scritta), nella scatola
        1 e da ripassare subito. Di serie scritta dalla persona o dal tutore; «modello» (con gli
        avvisi del controllo, che la lasciano «proposta») per la generazione dal lettore."""
        self._scrivibile()
        v = self._verifica(chi, vid)
        if v["stato"] not in ("bozza", "aperta"):
            raise VerificaChiusa()
        if origine not in C.ORIGINI:
            raise ValueError("origine sconosciuta")
        d = C.testo_normale(domanda, C.DOMANDA_MAX)
        r = C.testo_normale(risposta, C.RISPOSTA_MAX)
        aid = self._argomento_di(v, argomento)
        sue = {p["id"] for p in self._pagine_di(v["id"])}
        pag = [int(x) for x in pagine or ()]
        if any(x not in sue for x in pag):
            raise ValueError("una pagina non è di questa verifica")
        # Le carte dell'ombra non contano nel tetto (revisione della PR #325, nota 2): non sono
        # della persona e la generazione dopo le toglie
        n = self.dati.uno("SELECT COUNT(*) AS n FROM studio_carte WHERE verifica = ? AND "
                          "stato != 'ombra'", (v["id"],))["n"]
        if n >= C.CARTE_MAX:
            raise ValueError(f"al più {C.CARTE_MAX} carte per verifica")
        adesso = self.adesso().isoformat(timespec="seconds")
        cid = self.dati.scrivi(
            "INSERT INTO studio_carte (verifica, persona, argomento, domanda, risposta, chiusa, "
            "pagine, origine, stato, avvisi, scatola, scadenza, creata, creata_da) VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
            (v["id"], str(v["persona"]), aid, d, r, C.chiusa(r), D.j(dict.fromkeys(pag)),
             origine, "proposta" if avvisi else "attiva", D.j(avvisi) if avvisi else None,
             adesso, adesso, getattr(chi, "id", None)))
        self.misure["carte"]["scritte"] += 1
        self._registra(f"verifica {v['id']}: carta {cid} scritta ({origine}, "
                       f"{self._chi_registro(chi, v['persona'])})")
        return cid

    _UGUALE = object()

    def correggi_carta(self, chi, cid, domanda=None, risposta=None, argomento=_UGUALE):
        """La persona corregge una carta (anche una proposta dal modello): diventa sua, attiva,
        senza avvisi; il ripasso resta dov'era se cambia solo la domanda, ricomincia dalla
        scatola 1 se cambia la risposta."""
        self._scrivibile()
        c, v = self._carta(chi, cid)
        if c["stato"] == "ombra":
            # Una carta dell'ombra non è della persona: come `segna_carta` (revisione della PR
            # #325, nota 1), mai «attiva» da una correzione
            raise NonTrovata()
        d = C.testo_normale(domanda, C.DOMANDA_MAX) if domanda is not None else c["domanda"]
        r = C.testo_normale(risposta, C.RISPOSTA_MAX) if risposta is not None else c["risposta"]
        aid = c["argomento"] if argomento is self._UGUALE else self._argomento_di(v, argomento)
        nuova = r != c["risposta"]
        adesso = self.adesso().isoformat(timespec="seconds")
        self.dati.scrivi(
            "UPDATE studio_carte SET domanda = ?, risposta = ?, chiusa = ?, argomento = ?, "
            "origine = CASE WHEN origine = 'mappa' THEN 'mappa' ELSE 'persona' END, "
            "stato = 'attiva', avvisi = NULL, modificata = ?, "
            "scatola = CASE WHEN ? THEN 1 ELSE scatola END, "
            "scadenza = CASE WHEN ? THEN ? ELSE scadenza END WHERE id = ?",
            (d, r, C.chiusa(r), aid, adesso, int(nuova), int(nuova), adesso, c["id"]))

    def segna_carta(self, chi, cid, attiva: bool):
        """Toglie una carta dal ripasso o ce la rimette (reversibile). Su una carta proposta dal
        modello è la conferma della persona o del tutore, una per una («Tieni»), anche con un
        avviso: da lì entra nel ripasso. Una carta dell'ombra non si tocca."""
        self._scrivibile()
        c, _v = self._carta(chi, cid)
        if c["stato"] == "ombra":
            raise NonTrovata()
        adesso = self.adesso().isoformat(timespec="seconds")
        self.dati.scrivi("UPDATE studio_carte SET stato = ?, modificata = ?, scadenza = "
                         "COALESCE(scadenza, ?) WHERE id = ?",
                         ("attiva" if attiva else "tolta", adesso, adesso, c["id"]))

    def conferma_carte(self, chi, vid) -> dict:
        """«Conferma le carte»: le carte proposte dal modello senza avvisi entrano nel ripasso;
        quelle con un avviso (`genera.DA_DECIDERE`) restano proposte, e la persona le tiene una
        per una. {confermate, da_decidere}."""
        from .genera import DA_DECIDERE
        self._scrivibile()
        v = self._verifica(chi, vid)
        adesso = self.adesso().isoformat(timespec="seconds")
        n = d = 0
        with self.dati.lock:
            db = self.dati.db
            try:
                for c in db.execute("SELECT id, avvisi FROM studio_carte WHERE verifica = ? AND "
                                    "stato = 'proposta'", (v["id"],)).fetchall():
                    if set(D.da_j(c["avvisi"])) & set(DA_DECIDERE):
                        d += 1
                        continue
                    db.execute("UPDATE studio_carte SET stato = 'attiva', modificata = ?, "
                               "scadenza = ? WHERE id = ?", (adesso, adesso, c["id"]))
                    n += 1
                db.commit()
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
        self._registra(f"verifica {v['id']}: {n} carte confermate, {d} da decidere "
                       f"({self._chi_registro(chi, v['persona'])})")
        return {"confermate": n, "da_decidere": d}

    # ── la generazione (dal lettore, studio/lettura.py, studio/genera.py; niente `chi`) ──
    def _argomenti_per_carte(self, vid) -> list[dict]:
        """Gli argomenti del piano di una verifica, con le pagine (id), nell'ordine dell'elenco."""
        return [{"id": a["id"], "titolo": a["titolo"],
                 "pagine": [int(x) for x in D.da_j(a["pagine"]) if str(x).isdecimal()]}
                for a in self.dati.tutti("SELECT * FROM studio_argomenti WHERE verifica = ? "
                                         "ORDER BY ordine, id", (int(vid),))
                if a["stato"] in D.ARGOMENTI_DEL_PIANO]

    def verifiche_per_carte(self) -> list[dict]:
        """Le verifiche aperte con almeno un argomento del piano che cita una pagina letta e una
        firma (argomenti, pagine, modo) diversa da quella dell'ultima generazione, dalla più
        vicina. Vuoto con `studio_carte_genera: spenta`, la lettura spenta o i dati in sola
        lettura."""
        from . import argomenti as A
        from . import genera as G
        m = G.modo(self.cfg)
        if m == G.SPENTA or not self.dati.scrivibile:
            return []
        out = []
        for v in self.dati.tutti("SELECT * FROM studio_verifiche WHERE stato = 'aperta' AND "
                                 "data >= ? ORDER BY data, id", (self._oggi().isoformat(),)):
            args = self._argomenti_per_carte(v["id"])
            pagine = self._pagine_di(v["id"])
            lette = {int(p["id"]) for p in A.lette(pagine)}
            if not any(set(a["pagine"]) & lette for a in args):
                continue
            if G.da_generare(v.get("carte_firma"), v.get("carte_esito"), v.get("carte_del"),
                             G.firma(args, pagine, m), self.adesso()):
                out.append({**v, "_pagine": pagine, "_argomenti": args, "_modo": m})
        return out

    def proponi_carte(self, vid, firma: str, proposte: list[dict], esito: str,
                      modo_: str) -> int | None:
        """Scrive l'esito di una generazione: via le carte del modello non ancora decise (proposte
        o dell'ombra, mai corrette né confermate), dentro le nuove (tranne una domanda che c'è
        già), «proposta» con `studio_carte_genera: attiva`, «ombra» in ombra; la firma e l'esito.
        Con «rotto» o «errore» restano quelle di prima. Se intanto argomenti o pagine sono cambiati
        non scrive niente: None. Quante carte nuove."""
        from . import argomenti as A
        from . import genera as G
        with self.dati.lock:
            db = self.dati.db
            try:
                if db.in_transaction:
                    db.commit()
                db.execute("BEGIN IMMEDIATE")
                v = db.execute("SELECT * FROM studio_verifiche WHERE id = ? AND stato = 'aperta'",
                               (int(vid),)).fetchone()
                pagine = [dict(r) for r in db.execute(
                    "SELECT p.* FROM studio_pagine p JOIN studio_materiali m ON m.id = p.materiale"
                    " WHERE m.verifica = ?", (int(vid),))]
                args = [{"id": a["id"], "titolo": a["titolo"],
                         "pagine": [int(x) for x in D.da_j(a["pagine"]) if str(x).isdecimal()]}
                        for a in db.execute("SELECT * FROM studio_argomenti WHERE verifica = ? "
                                            "ORDER BY ordine, id", (int(vid),)).fetchall()
                        if a["stato"] in D.ARGOMENTI_DEL_PIANO]
                if v is None or G.firma(args, pagine, modo_) != firma:
                    db.rollback()
                    return None
                n = 0
                if esito not in (G.ROTTO, G.ERRORE):
                    db.execute("DELETE FROM studio_carte WHERE verifica = ? AND origine = "
                               "'modello' AND stato IN ('proposta', 'ombra')", (int(vid),))
                    decise = {A.chiave(r[0]) for r in db.execute(
                        "SELECT domanda FROM studio_carte WHERE verifica = ?", (int(vid),))}
                    tot = db.execute("SELECT COUNT(*) FROM studio_carte WHERE verifica = ? AND "
                                     "stato != 'ombra'", (int(vid),)).fetchone()[0]
                    adesso = self.adesso().isoformat(timespec="seconds")
                    stato = "ombra" if modo_ == G.OMBRA else "proposta"
                    for c in proposte:
                        if A.chiave(c["domanda"]) in decise or tot + n >= C.CARTE_MAX:
                            continue
                        db.execute(
                            "INSERT INTO studio_carte (verifica, persona, argomento, domanda, "
                            "risposta, chiusa, pagine, origine, stato, avvisi, scatola, scadenza, "
                            "creata) VALUES (?, ?, ?, ?, ?, ?, ?, 'modello', ?, ?, 1, NULL, ?)",
                            (int(vid), str(v["persona"]), c["argomento"], c["domanda"],
                             c["risposta"], C.chiusa(c["risposta"]), D.j(c["pagine"]), stato,
                             D.j(c["avvisi"]) if c["avvisi"] else None, adesso))
                        decise.add(A.chiave(c["domanda"]))
                        n += 1
                scritta, errori = G.firma_da_scrivere(v["carte_firma"], firma, esito)
                db.execute("UPDATE studio_verifiche SET carte_firma = ?, carte_esito = ?, "
                           "carte_del = ? WHERE id = ?",
                           (scritta, esito if esito != G.PROPOSTE or n else G.VUOTO,
                            self.adesso().isoformat(timespec="seconds"), int(vid)))
                db.commit()
                if errori >= G.ERRORI_MAX:
                    self._registra(f"verifica {vid}: carte ferme dopo {errori} errori con le stesse "
                                   "pagine e argomenti: ripartono quando cambiano")
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
        return n

    def _del_piano(self, vid) -> set:
        return {a["id"] for a in self.dati.tutti(
            "SELECT id, stato FROM studio_argomenti WHERE verifica = ?", (int(vid),))
            if a["stato"] in D.ARGOMENTI_DEL_PIANO}

    def carte(self, chi, vid) -> list[dict]:
        """Tutte le carte di una verifica, col numero (l'ordine di scrittura), il numero
        dell'argomento nell'elenco della verifica, se è da ripassare e fra quanto. Domanda e
        risposta sono un dato: lo schermo le scrive con textContent."""
        v = self._verifica(chi, vid)
        return self._carte_di(v, chi)

    def _carte_di(self, v: dict, chi=None) -> list[dict]:
        """`chi`: chi guarda; le carte della mappa si nascondono alla persona (e ai conti, senza
        `chi`), non al tutore (seconda revisione della PR #330)."""
        adesso = self.adesso()
        elenco = self.dati.tutti("SELECT id, stato FROM studio_argomenti WHERE verifica = ? "
                                 "ORDER BY ordine, id", (v["id"],))
        numeri = {a["id"]: i for i, a in enumerate(elenco, 1)}
        nel_piano = {a["id"] for a in elenco if a["stato"] in D.ARGOMENTI_DEL_PIANO}
        out = []
        # Con la mappa libera aperta (passo 7c, #328) le carte scritte da «Fanne carte» non si
        # vedono e non si ripassano: dicono i concetti dello scheletro, che resta nascosto
        libera_aperta = ((chi is None or getattr(chi, "id", None) == v["persona"])
                         and self._libera_aperta(v["id"]))
        # Le carte dell'ombra (studio_carte_genera: ombra) non vanno mai alla persona
        for i, c in enumerate(self.dati.tutti("SELECT * FROM studio_carte WHERE verifica = ? AND "
                                              "stato != 'ombra' ORDER BY id", (v["id"],)), 1):
            if libera_aperta and c["origine"] == "mappa":
                continue
            c["pagine"] = [int(x) for x in D.da_j(c["pagine"]) if str(x).isdecimal()]
            c["avvisi"] = D.da_j(c["avvisi"])
            c["numero"] = i
            c["argomento_numero"] = numeri.get(c["argomento"])
            # Le carte di un argomento fuori dal piano non si ripassano finché non torna
            c["nel_piano"] = c["argomento"] is None or c["argomento"] in nel_piano
            c["da_ripassare"] = c["nel_piano"] and C.da_ripassare(c, adesso)
            c["fra"] = (C.fra_quanto(c["scadenza"], adesso) if c["stato"] == "attiva"
                        and c["scadenza"] else None)
            out.append(c)
        return out

    def da_ripassare(self, chi, vid) -> list[dict]:
        """Le carte da ripassare adesso: prima le più scadute, poi le scatole basse."""
        v = self._verifica(chi, vid)
        return self._da_ripassare(v, chi)

    def _da_ripassare(self, v: dict, chi=None) -> list[dict]:
        out = [c for c in self._carte_di(v, chi) if c["da_ripassare"]]
        out.sort(key=lambda c: (str(c["scadenza"] or ""), c["scatola"], c["id"]))
        return out

    def _conto_carte(self, v: dict) -> dict:
        """I conti delle carte per la home e la voce: quante, quante da ripassare, la prossima."""
        tutte = [c for c in self._carte_di(v) if c["stato"] != "tolta"]
        attive = [c for c in tutte if c["stato"] == "attiva" and c["nel_piano"]]
        dopo = sorted((c for c in attive if not c["da_ripassare"] and c["scadenza"]),
                      key=lambda c: c["scadenza"])
        return {"totali": len(tutte), "da_ripassare": sum(c["da_ripassare"] for c in attive),
                "proposte": sum(c["stato"] == "proposta" for c in tutte),
                "prossima": dopo[0]["fra"] if dopo else None}

    def _vigilia(self, v: dict) -> datetime.date | None:
        d = _data(v["data"]) - datetime.timedelta(days=1)
        return d if d > self._oggi() else None

    def esito_carta(self, chi, cid, esito: str, fonte: str | None = None) -> dict:
        """L'esito di una carta: «sapevo», «quasi», «non_sapevo» (dai tasti della persona, o a
        voce da `esito_a_voce`), il ripasso di Leitner (`carte.prossima`) e il tentativo di tipo
        «carta» sull'argomento, se è nel piano e la padronanza non è spenta. `fonte` di serie è
        chi registra («persona» o «tutore»); «codice» per il confronto delle risposte chiuse."""
        self._scrivibile()
        if esito not in C.ESITI:
            raise ValueError("esito sconosciuto")
        c, v = self._carta(chi, cid)
        if c["stato"] != "attiva":
            raise ValueError("la carta non è nel ripasso")
        ruolo = self._chi_puo(chi, v["persona"])
        fonte = fonte or ("persona" if ruolo == "proprietario" else "tutore")
        adesso = self.adesso()
        scatola, scadenza = C.prossima(c["scatola"], esito, adesso, self._vigilia(v))
        self.dati.scrivi("UPDATE studio_carte SET scatola = ?, scadenza = ?, ultima = ? WHERE "
                         "id = ?", (scatola, scadenza, adesso.isoformat(timespec="seconds"),
                                    c["id"]))
        m = self.misure["carte"]
        m["esiti"][esito] = m["esiti"].get(esito, 0) + 1
        m["codice"] += fonte == "codice"
        tid = None
        if (c["argomento"] is not None and c["argomento"] in self._del_piano(v["id"])
                and self.modo_padronanza != PD.SPENTA):
            try:
                tid = self.registra_tentativo(chi, v["id"], c["argomento"], "carta",
                                              C.ESITO_TENTATIVO[esito], fonte, carta=c["id"])
            except (ValueError, NonTrovata, NonPermesso) as e:
                self._registra(f"tentativo della carta {c['id']} non scritto: {type(e).__name__}")
        self._registra(f"verifica {v['id']}: carta {c['id']} {esito} ({fonte}), scatola "
                       f"{scatola}")
        return {"carta": c["id"], "esito": esito, "fonte": fonte, "scatola": scatola,
                "scadenza": scadenza, "fra": C.fra_quanto(scadenza, adesso), "tentativo": tid,
                "restano": len(self._da_ripassare(v))}

    # ── le carte a voce (la carta in corso è di chi parla, in memoria) ──
    def _in_corso(self, persona) -> dict | None:
        ic = self._carte_in_corso.get(str(persona or ""))
        if ic is None:
            return None
        if self.adesso() > ic["fino"]:
            self._carte_in_corso.pop(str(persona or ""), None)
            return None
        return ic

    def carta_in_corso(self, chi, turno: int | None = None) -> dict | None:
        """La carta chiesta a voce a `chi` e non ancora risposta (o None): la carta e la verifica,
        se è ancora sua (o del suo minore). Con `turno`, solo nello stesso turno della domanda (o
        della risposta) o in quello subito dopo: oltre, la carta esce da «in corso» (revisione
        della PR #324, nota 1: un «no» detto due turni dopo a un'altra domanda non è un esito)."""
        ic = self._in_corso(getattr(chi, "id", None))
        if ic is None:
            return None
        if turno is not None and int(turno or 0) > int(ic["turno"] or 0) + 1:
            self._carte_in_corso.pop(str(getattr(chi, "id", "")), None)
            return None
        try:
            c, v = self._carta(chi, ic["carta"])
        except (NonTrovata, NonPermesso):
            self._carte_in_corso.pop(str(getattr(chi, "id", "")), None)
            return None
        c["pagine"] = [int(x) for x in D.da_j(c["pagine"]) if str(x).isdecimal()]
        return {**c, "verifica": v["id"], "turno": ic["turno"],
                "letta": bool(ic.get("letta"))}

    def risposta_letta(self, chi, turno: int | None = None):
        """La risposta della carta in corso è stata detta (`studio_carte` parte «risposta»): da
        qui vale solo l'autovalutazione, perché ripetere la risposta appena sentita non è
        saperla; l'esito si aspetta nel turno dopo questo."""
        ic = self._in_corso(getattr(chi, "id", None))
        if ic is not None:
            ic["letta"] = True
            if turno is not None:
                ic["turno"] = max(int(ic["turno"] or 0), int(turno or 0))

    def prossima_carta(self, chi, vid, turno: int = 0) -> dict | None:
        """La carta da chiedere a voce: quella in corso della stessa verifica, se c'è, altrimenti
        la prima da ripassare; diventa «in corso» per `chi` per il turno dopo (al più
        `CARTA_IN_CORSO_S`). Con il numero fra quelle da ripassare e quante restano. None se
        nessuna."""
        v = self._verifica(chi, vid)
        due = self._da_ripassare(v, chi)
        chiave = str(getattr(chi, "id", "") or "")
        ic = self._in_corso(chiave)
        scelta = None
        if ic is not None and ic["verifica"] == v["id"]:
            scelta = next((c for c in self._carte_di(v, chi) if c["id"] == ic["carta"]
                           and c["stato"] == "attiva"), None)
        if scelta is None and due:
            scelta = due[0]
        if scelta is None:
            self._carte_in_corso.pop(chiave, None)
            return None
        adesso = self.adesso()
        if ic is None or ic["carta"] != scelta["id"]:
            ic = {"carta": scelta["id"], "verifica": v["id"]}
        # Chiesta di nuovo: il turno è questo (nota 1), il tempo riparte (anche oltre la
        # mezzanotte, nota 4)
        ic["turno"] = int(turno or 0)
        ic["fino"] = adesso + datetime.timedelta(seconds=CARTA_IN_CORSO_S)
        self._carte_in_corso[chiave] = ic
        ids = [c["id"] for c in due]
        return {**scelta, "posizione": (ids.index(scelta["id"]) + 1) if scelta["id"] in ids
                else 1, "restano": max(len(due), 1)}

    def esito_a_voce(self, chi, frase: str, turno: int = 0) -> dict:
        """L'esito della carta in corso dalla frase detta dalla persona in questo turno, mai da
        un argomento del modello: la risposta chiusa della carta nella frase (`carte.risposta_
        giusta`, fonte «codice», solo il «giusto», solo prima che Calliope dica la risposta; una
        risposta corta solo come frase intera), altrimenti una forma chiusa dell'autovalutazione
        detta per intero (`carte.autovalutazione`, fonte di chi parla). Una volta per carta, solo
        nel turno subito dopo la domanda o la risposta. {"esito": None, "motivo"} se non c'è:
        «nessuna» (nessuna carta in corso), «stesso_turno», «tolta» (la carta è uscita dal ripasso
        intanto: esce anche da «in corso», nota 3 della PR #324), «non_detto»."""
        ic = self.carta_in_corso(chi, turno)
        if ic is None:
            return {"esito": None, "motivo": "nessuna"}
        if int(turno or 0) <= int(ic["turno"] or 0):
            return {"esito": None, "motivo": "stesso_turno", "carta": ic["id"]}
        if ic["stato"] != "attiva":
            self._carte_in_corso.pop(str(getattr(chi, "id", "") or ""), None)
            return {"esito": None, "motivo": "tolta", "carta": ic["id"]}
        esito, fonte = None, None
        if not ic["letta"] and C.risposta_giusta(ic["chiusa"], frase):
            esito, fonte = C.SAPEVO, "codice"
        else:
            esito = C.autovalutazione(frase)
        if esito is None:
            return {"esito": None, "motivo": "non_detto", "carta": ic["id"]}
        out = self.esito_carta(chi, ic["id"], esito, fonte)
        self.misure["carte"]["a_voce"] += 1
        self._carte_in_corso.pop(str(getattr(chi, "id", "") or ""), None)
        return out

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
        # Ieri con una sessione ancora aperta (PR #321, nota 1) resta nel piano: le sue pagine non
        # tornano anche su oggi (#322, caso 1), e il piano si ricalcola alla prossima lettura
        # finché la sessione non si chiude o non scadono le 3 ore
        aperto = self._sessione_aperta_ieri(v["id"])
        tieni = aperto.isoformat() if aperto else ""
        riservate = set()
        if aperto:
            r = self.dati.uno("SELECT * FROM studio_piano WHERE verifica = ? AND giorno = ? AND "
                              "fatto IS NULL", (v["id"], tieni))
            if r is not None and r["fase"] == P.STUDIO:
                riservate = {int(p) for p in D.da_j(r["pagine"])}
        piano = P.calcola(oggi, data, pagine, minuti,
                          int(getattr(self.cfg, "studio_minuti_pagina", 10) or 10),
                          fatte=fatte | riservate, giorni_fatti=giorni_fatti)
        if not self.dati.scrivibile:
            return piano
        with self.dati.lock:
            db = self.dati.db
            try:
                # I giorni passati non fatti escono dal piano: prima resta l'evento «mancato»
                # (passo 4b, #244), una volta sola per giorno, per il riepilogo. Resta solo ieri
                # con una sessione cominciata nelle ultime 3 ore (PR #321, nota 1): «Fatto» dopo
                # mezzanotte la chiude
                for r in db.execute("SELECT * FROM studio_piano WHERE verifica = ? AND fatto IS "
                                    "NULL AND giorno < ?", (v["id"], oggi.isoformat())).fetchall():
                    if r["giorno"] != tieni and not db.execute(
                            "SELECT 1 FROM studio_eventi WHERE verifica = ? AND giorno = ? AND "
                            "tipo IN ('mancato', 'saltato')", (v["id"], r["giorno"])).fetchone():
                        self._evento(db, v, "mancato", r["giorno"], None,
                                     pagine=D.da_j(r["pagine"]), minuti=r["minuti"],
                                     fase=r["fase"])
                db.execute("DELETE FROM studio_piano WHERE verifica = ? AND ((fatto IS NULL AND "
                           "giorno != ?) OR giorno >= ?)", (v["id"], tieni, data.isoformat()))
                for g in piano.giorni:
                    db.execute("INSERT INTO studio_piano (verifica, giorno, fase, pagine, "
                               "attivita, minuti, oltre) VALUES (?, ?, ?, ?, ?, ?, ?)",
                               (v["id"], g.giorno.isoformat(), g.fase, D.j(g.pagine),
                                g.attivita, g.minuti, int(g.oltre)))
                # Con ieri tenuto il piano resta «di ieri»: si rifà alla prossima lettura (#322)
                db.execute("UPDATE studio_verifiche SET piano_del = ?, piano_avvisi = ? "
                           "WHERE id = ?", (tieni or oggi.isoformat(), D.j(piano.avvisi),
                                            v["id"]))
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
        lettura, i giorni fatti dal db e gli altri dal calcolo in memoria. Se il ricalcolo
        fallisce resta il piano di prima con l'avviso `piano_non_aggiornato` (passo 4.5, nota della
        seconda revisione della PR #308: prima tornava il vecchio con gli avvisi vuoti)."""
        oggi = self._oggi()
        stato = v["stato"]
        avvisi = D.da_j(v["piano_avvisi"])
        calcolato = None
        fallito = False
        if stato in ("aperta", "fatta") and v["piano_del"] != oggi.isoformat():
            prima = self.misure["errori"]
            calcolato = self._ricalcola_sicuro(v["id"])
            fallito = self.misure["errori"] > prima
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
        if fallito and stato == "aperta":
            avvisi = [a for a in avvisi if a != P.NON_AGGIORNATO] + [P.NON_AGGIORNATO]
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
        righe_m = self.dati.tutti("SELECT giorno, valore, fonte FROM studio_misure WHERE "
                                  "verifica = ? ORDER BY giorno, id", (v["id"],))
        # Le misure della padronanza (passo 5) entrano nella forbice solo se è mostrata: quelle
        # dell'ombra mai, quelle «padronanza» scritte prima di tornare in ombra nemmeno (nota 3
        # della revisione della PR #323)
        mostrata = self.padronanza_mostrata()
        misure = [(_data(r["giorno"]), r["valore"]) for r in righe_m
                  if r["fonte"] != PD.FONTE_OMBRA and (r["fonte"] != PD.FONTE_MISURA or mostrata)]
        # «L'ultima prova» è una prova vera (la verifica finta, più avanti), mai la misura del
        # giorno della padronanza (nota 5)
        prove = [r["valore"] for r in righe_m if r["fonte"] not in (PD.FONTE_MISURA,
                                                                    PD.FONTE_OMBRA)]
        data = _data(v["data"])
        # Le pagine del piano e quelle lette nei giorni fatti (per il riepilogo, passo 4b)
        del_piano = {p_.id for p_ in self._pagine_del_piano(v["id"])}
        return {"verifica": v["id"], "stato": stato, "data": v["data"],
                "pagine": {"totali": len(del_piano), "lette": len(del_piano & fatte)},
                "giorni_mancanti": (data - oggi).days, "obiettivo": v["obiettivo"],
                "giorni": giorni, "avvisi": avvisi,
                "tappe": P.tappe(args, ordine, fatte),
                "misure": len(misure), "livello": int(round(prove[-1])) if prove else None,
                # La previsione mostrata è la forbice (revisione della PR #317, 0035 punto 9):
                # None prima di 3 misure in 2 giorni; intanto l'ultima misura vera (`livello`)
                "previsione": P.forbice(misure, data)}

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

    # ── le due domande prima della sessione (30/10, passo 4.5, #284; decisione 0035, punto 27) ──
    def imposta_sessione(self, chi, vid, conoscenza=None, umore=None) -> dict:
        """«Quanto conosci l'argomento?» (1–5) e «come ti senti oggi?» (uno di `UMORI`), a voce o
        con un tocco, prima di una sessione su una verifica. Solo in memoria, per `SESSIONE_S` e
        mai oltre la mezzanotte: mai su disco, mai nel registro, mai ai tutori; lo stato d'animo
        di un minore è un dato delicato (decisione 0035, punto 27)."""
        v = self._verifica(chi, vid)
        if conoscenza is not None:
            conoscenza = int(conoscenza)
            if not 1 <= conoscenza <= len(CONOSCENZA):
                raise ValueError("la conoscenza va da 1 a 5")
        if umore is not None:
            umore = str(umore).strip().lower()
            if umore not in UMORI:
                raise ValueError("stato d'animo sconosciuto")
        adesso = self.adesso()
        fino = min(adesso + datetime.timedelta(seconds=SESSIONE_S),
                   datetime.datetime.combine(adesso.date(), datetime.time(23, 59, 59)))
        chiave = str(getattr(chi, "id", "") or "")
        prima = self.sessione(chiave) or {}
        if prima.get("verifica") != v["id"]:
            prima = {}
        s = {"verifica": v["id"], "conoscenza": conoscenza or prima.get("conoscenza"),
             "umore": umore or prima.get("umore"), "fino": fino}
        # La sessione è di chi studia adesso (chi parla o tocca), anche sulla verifica del figlio
        self._sessioni[chiave] = s
        if not prima and self.dati.scrivibile:
            # L'ora d'inizio della sessione, per il tempo del resoconto (passo 4b, #244): solo
            # l'ora, mai le due risposte (0035 punto 27). Un errore del db non ferma la sessione
            try:
                with self.dati.lock:
                    self._evento(self.dati.db, v, "inizio", adesso.date(), chi)
                    self.dati.db.commit()
            except Exception as e:  # noqa: BLE001
                self.misure["errori"] += 1
                self._registra(f"inizio della sessione non salvato: {type(e).__name__}")
        self._registra(f"sessione sulla verifica {v['id']}")
        return dict(s)

    def sessione(self, persona) -> dict | None:
        """La sessione di oggi di una persona (le due risposte), o None se non c'è o è scaduta."""
        s = self._sessioni.get(str(persona or ""))
        if s is None:
            return None
        if self.adesso() > s["fino"]:
            self._sessioni.pop(str(persona), None)
            return None
        return dict(s)

    def dimentica_sessione(self, persona):
        self._sessioni.pop(str(persona or ""), None)
        self._carte_in_corso.pop(str(persona or ""), None)

    def nota_sessione(self, persona) -> str:
        """La nota per i dati del turno (un dato, non un ordine; principio 10): come regolare
        tono e difficoltà dalle due risposte. "" senza sessione o con lo Studio non per il
        modello."""
        if not self.per_modello():
            return ""
        s = self.sessione(persona)
        if s is None:
            return ""
        pezzi = []
        c = s.get("conoscenza")
        if c:
            pezzi.append(f"sull'argomento dice «{CONOSCENZA[c - 1]}» ({c} su 5)"
                         + (", quindi parti dalle basi, un passo alla volta" if c <= 2 else
                            ", quindi domande più difficili e meno spiegazioni" if c >= 4 else ""))
        u = s.get("umore")
        if u:
            pezzi.append(f"oggi si sente «{u}»"
                         + (", quindi frasi brevi, poco per volta, e incoraggia" if u in (
                             "poca energia", "stressato") else ""))
        return ("Studio, sessione di oggi: " + "; ".join(pezzi) + ".") if pezzi else ""

    # ── la home dello Studio (30/10, passo 4.5, #284) ──
    def _da_parte(self, vid) -> list[dict]:
        return [{"id": p["id"], "ordine": p["ordine"],
                 "numero": P.numero_leggibile(p["numero"])}
                for p in self._pagine_di(vid) if p["stato"] == "da_parte"]

    def home(self, chi) -> dict:
        """I dati della home sullo schermo personale: le verifiche aperte o in bozza di `chi` e,
        da tutore, dei suoi minori (con `di`), dalla più vicina, ognuna con data, obiettivo,
        giorni che mancano, oggi, tappe, previsione (solo dopo due misure), lettura, argomenti da
        decidere col perché e pagine da parte. Titoli e testo sono dati: la pagina li scrive solo
        con textContent."""
        from .argomenti import DA_DECIDERE
        persone = [getattr(chi, "id", None)]
        reg = self.registry
        for p in (getattr(reg, "users", {}) or {}).values() if reg is not None else ():
            if getattr(p, "id", None) not in persone and permesso(chi, p, reg) == "tutore":
                persone.append(p.id)
        out = []
        for pid in [x for x in persone if x]:
            try:
                self._chi_puo(chi, pid)
            except NonPermesso:
                continue
            nome = None if pid == getattr(chi, "id", None) else getattr(
                self._profilo(pid), "name", None)
            for v in self.dati.tutti("SELECT id FROM studio_verifiche WHERE persona = ? AND "
                                     "stato IN ('bozza', 'aperta') ORDER BY data, id", (pid,)):
                try:
                    out.append(self._home_verifica(chi, v["id"], nome, DA_DECIDERE))
                except (NonTrovata, NonPermesso):
                    continue
        out.sort(key=lambda x: (x["data"], x["id"]))
        sess = self.sessione(getattr(chi, "id", None))
        return {"verifiche": out,
                "sessione": ({"verifica": sess["verifica"], "conoscenza": sess.get("conoscenza"),
                              "umore": sess.get("umore")} if sess else None),
                "conoscenza": list(CONOSCENZA), "umori": list(UMORI),
                "prova": not self.per_schermi()}

    def _home_verifica(self, chi, vid, di, da_decidere) -> dict:
        v = self.verifica(chi, vid)
        pi = self.piano(chi, vid) if v["stato"] == "aperta" else None
        oggi = self._oggi().isoformat()
        r_oggi = next((g for g in (pi or {}).get("giorni", ()) if g["giorno"] == oggi), None)
        args = self.argomenti(chi, vid)
        decidere = [{"id": a["id"], "titolo": a["titolo"],
                     "avvisi": [x for x in a["avvisi"] if x in da_decidere]}
                    for a in args if a["stato"] == "proposto"
                    and set(a["avvisi"]) & set(da_decidere)]
        pad = (self._pad_schermo(v, args) if pi is not None and self.padronanza_mostrata()
               else None)
        return {"id": v["id"], "materia": v["materia"], "argomento": v["argomento"],
                "data": v["data"], "stato": v["stato"], "giorni_mancanti": v["giorni_mancanti"],
                "obiettivo": v["obiettivo"], "di": di,
                "oggi": ({"attivita": r_oggi["attivita"], "minuti": r_oggi["minuti"],
                          "fase": r_oggi["fase"], "fatto": bool(r_oggi["fatto"])}
                         if r_oggi else None),
                "giorni": [{"giorno": g["giorno"], "fase": g["fase"], "attivita": g["attivita"],
                            "minuti": g["minuti"], "fatto": bool(g["fatto"])}
                           for g in (pi or {}).get("giorni", ())],
                "avvisi_piano": list((pi or {}).get("avvisi") or ()),
                "tappe": [{"titolo": t.get("titolo"), "stato": t.get("stato"),
                           # La parola della padronanza, solo «mostrata» (passo 5)
                           **({"parola": pad["per"].get(t.get("argomento"))}
                              if pad else {})}
                          for t in (pi or {}).get("tappe") or ()],
                # Le lacune con la lezione successiva, solo «mostrata» (passo 5, #245)
                "lacune": pad["lacune"] if pad else None,
                "misure": (pi or {}).get("misure", 0),
                "ultima": (pi or {}).get("livello"),
                "previsione": (list((pi or {}).get("previsione"))
                               if (pi or {}).get("previsione") else None),
                "lettura": self.lettura(chi, vid),
                "argomenti": {"tenuti": sum(a["stato"] in D.ARGOMENTI_DEL_PIANO for a in args),
                              "proposti": sum(a["stato"] == "proposto" for a in args),
                              "da_decidere": decidere},
                "da_parte": self._da_parte(vid),
                # Le carte (passo 6, #246): solo i conti; il testo lo dà /api/studio/carte
                "carte": self._conto_carte(v),
                # La mappa (passo 7, #247): solo conti e stati; il testo lo dà /api/studio/mappa
                "mappa": self._conto_mappa(v),
                # Il riepilogo e le sessioni (passo 4b, #244): righe scritte dal codice dai dati
                "riepilogo": self._riepilogo_schermo(v, pi) if pi is not None else None,
                # Fuori dal piano: i tolti (non gli uniti a un altro), per rimetterli con un tocco
                "tolti": [{"id": a["id"], "titolo": a["titolo"]} for a in args
                          if a["stato"] == "tolto" and "unito" not in a["avvisi"]]}

    def _pad_schermo(self, v: dict, args: list[dict]) -> dict:
        """La padronanza per la home («mostrata»): la parola per argomento e le lacune col titolo
        (sullo schermo con textContent) e la lezione successiva."""
        p = self._padronanza(v)
        titoli = {a["id"]: a["titolo"] for a in args}
        return {"per": {a["id"]: a["parola"] for a in p["argomenti"]},
                "lacune": [{"titolo": titoli.get(x["argomento"], ""), "parola": x["parola"],
                            "lezione": (f"{R.detta(x['lezione']['giorno'])}: "
                                        f"{x['lezione']['attivita'] or ''}".strip()
                                        if x["lezione"] else "nessun giorno del piano")}
                           for x in p["lacune"]]}

    # ── resoconto e riepilogo (30/10, passo 4b, #244; decisione 0035 punto 31) ──
    def _evento(self, db, v: dict, tipo: str, giorno, chi, **dati):
        """Un evento della verifica `v`, dentro una transazione già aperta (chi chiama fa il
        commit). `dati`: solo id, numeri e date."""
        if tipo not in D.EVENTI:
            raise ValueError("evento sconosciuto")
        db.execute("INSERT INTO studio_eventi (verifica, persona, giorno, ora, tipo, chi, dati) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (v["id"], str(v["persona"]), _data(giorno).isoformat(),
                    self.adesso().isoformat(timespec="seconds"), tipo,
                    getattr(chi, "id", None) if chi is not None else None,
                    json.dumps(dati, ensure_ascii=False) if dati else None))

    def _eventi(self, vid) -> list[dict]:
        out = self.dati.tutti("SELECT * FROM studio_eventi WHERE verifica = ? ORDER BY ora, id",
                              (int(vid),))
        for e in out:
            try:
                e["dati"] = json.loads(e["dati"]) if e["dati"] else {}
            except (TypeError, ValueError):
                e["dati"] = {}
            if not isinstance(e["dati"], dict):
                e["dati"] = {}
        return out

    def _pagine_mappa(self, vid) -> dict:
        """id → `piano.Pagina` di tutte le pagine della verifica (anche tolte: la storia)."""
        return {r["id"]: P.Pagina(r["id"], r["ordine"], r["numero"], r["etichetta"],
                                  r["materiale_titolo"] or f"materiale {r['materiale_id']}")
                for r in self.dati.tutti(
                    "SELECT p.*, m.titolo AS materiale_titolo, m.id AS materiale_id FROM "
                    "studio_pagine p JOIN studio_materiali m ON m.id = p.materiale WHERE "
                    "m.verifica = ?", (int(vid),))}

    def _sessioni_di(self, v: dict, giorni_piano: list[dict]) -> list[dict]:
        oggi = self._oggi().isoformat()
        passate = [g for g in giorni_piano if g["giorno"] < oggi and not g["fatto"]]
        return R.sessioni(self._eventi(v["id"]), passate, self._oggi())

    @staticmethod
    def _numeri(ids, mappa: dict) -> list:
        """I numeri di pagina per la voce: interi solo se sono cifre, altrimenti None."""
        return [P.numero_pagina(mappa[i].numero) if i in mappa else None for i in ids]

    @staticmethod
    def _attivita(fase, ids, mappa: dict) -> str | None:
        """L'attività per lo schermo (textContent), dalle pagine di oggi del db."""
        quali = [mappa[i] for i in ids if i in mappa]
        return P.attivita(fase or P.STUDIO, quali, P.piu_materiali(quali)) if quali else None

    def _resta(self, giorni_piano: list[dict], pi: dict, dopo: str, mappa: dict) -> dict:
        """Cosa resta dopo il giorno `dopo` (AAAA-MM-GG): le pagine del piano non lette, i giorni
        del piano che vengono e il prossimo (la fase e i numeri delle sue pagine)."""
        oggi = self._oggi().isoformat()
        avanti = [g for g in giorni_piano if g["giorno"] > dopo and g["giorno"] >= oggi
                  and not g["fatto"]]
        pross = avanti[0] if avanti else None
        return {"pagine": pi["pagine"]["totali"] - pi["pagine"]["lette"], "giorni": len(avanti),
                "prossimo": ({"giorno": pross["giorno"], "fase": pross["fase"],
                              "numeri": self._numeri(pross["pagine"], mappa)}
                             if pross else None)}

    def resoconto(self, chi, vid, giorno=None) -> dict:
        """Il resoconto di un giorno di una verifica (di serie oggi), proiettato dai dati: lo
        stato (fatto, saltato, mancato, iniziato, da fare, niente), l'ora d'inizio e di fine, i
        minuti misurati (solo fra «Inizia» e «Fatto») e quelli previsti, la fase, le pagine (id e,
        per la voce, i numeri fatti di cifre), l'attività per lo schermo, cosa resta e la frase
        per la voce. Permessi come il resto dello Studio. Mai lo stato d'animo (non è su disco)."""
        v = self._verifica(chi, vid)
        g = _data(giorno or self._oggi()).isoformat()
        pi = self.piano(chi, v["id"])
        mappa = self._pagine_mappa(v["id"])
        sess = next((s for s in self._sessioni_di(v, pi["giorni"]) if s["giorno"] == g), None)
        riga = next((x for x in pi["giorni"] if x["giorno"] == g), None)
        if sess is not None and sess["stato"] != R.INIZIATO:
            r = dict(sess)
        elif riga is not None and not riga["fatto"]:
            r = {"giorno": g, "stato": R.INIZIATO if sess else R.DA_FARE,
                 "inizio": sess["inizio"] if sess else None, "fine": None, "minuti": None,
                 "previsti": riga["minuti"], "fase": riga["fase"], "pagine": list(riga["pagine"])}
        elif sess is not None:
            r = dict(sess)
        else:
            r = {"giorno": g, "stato": R.NIENTE, "inizio": None, "fine": None, "minuti": None,
                 "previsti": None, "fase": None, "pagine": []}
        r["numeri"] = self._numeri(r["pagine"], mappa)
        r["attivita"] = self._attivita(r["fase"], r["pagine"], mappa)
        # Un giorno ancora da chiudere conta fra quelli che restano («oggi compreso»)
        aperto = r["stato"] in (R.DA_FARE, R.INIZIATO)
        dopo = (_data(g) - datetime.timedelta(days=1)).isoformat() if aperto else g
        resta = self._resta(pi["giorni"], pi, dopo, mappa)
        if aperto:
            resta.update(prossimo=None, oggi_compreso=True)
        r.update(verifica=v["id"], materia=v["materia"], data=v["data"], resta=resta)
        r["frase"] = R.frase_resoconto(r, self._oggi(), self._nome_per(chi, v))
        return r

    def riepilogo(self, chi, vid) -> dict:
        """Il riepilogo della preparazione di una verifica, proiettato dai dati: giorni fatti,
        saltati e mancati, il tempo misurato, le pagine lette su quelle del piano, gli argomenti
        finiti (le tappe), quanto manca, la previsione già esistente (forbice o ultima prova), gli
        spostamenti della data, le sessioni giorno per giorno; con le righe per lo schermo e la
        frase per la voce."""
        v = self._verifica(chi, vid)
        return self._riepilogo(v, self.piano(chi, v["id"]), self._nome_per(chi, v))

    def _nome_per(self, chi, v: dict) -> str | None:
        """Il nome della persona della verifica quando chi chiede non è lei (il tutore, PR #321):
        le frasi vanno alla terza persona. None per la persona stessa, "" senza nome (#322)."""
        if getattr(chi, "id", None) == v["persona"]:
            return None
        # Senza nome una forma impersonale (#322, caso 3): "" e non «il ragazzo», che ha il
        # genere fisso e dava «Storia di il ragazzo»
        return str(getattr(self._profilo(v["persona"]), "name", "") or "").strip()

    def _riepilogo(self, v: dict, pi: dict, nome: str | None = None) -> dict:
        sess = self._sessioni_di(v, pi["giorni"])
        fatti = [s for s in sess if s["stato"] == R.FATTO]
        misurati = [s for s in fatti if s.get("minuti")]
        spost = [{"da": e["dati"].get("da"), "a": e["dati"].get("a")}
                 for e in self._eventi(v["id"]) if e["tipo"] == "spostata"
                 and e["dati"].get("da")]
        r = {"verifica": v["id"], "materia": v["materia"], "data": v["data"],
             "stato": pi["stato"], "giorni_mancanti": pi["giorni_mancanti"],
             "giorni": {"fatti": len(fatti),
                        "saltati": sum(s["stato"] == R.SALTATO for s in sess),
                        "mancati": sum(s["stato"] == R.MANCATO for s in sess)},
             "tempo": {"minuti": sum(s["minuti"] for s in misurati), "sessioni": len(misurati),
                       "senza": len(fatti) - len(misurati)},
             "pagine": dict(pi["pagine"]),
             "argomenti": {"finiti": sum(t["stato"] == "fatta" for t in pi["tappe"]),
                           "totali": len(pi["tappe"])},
             "previsione": list(pi["previsione"]) if pi.get("previsione") else None,
             "ultima": pi.get("livello"), "spostata": spost, "sessioni": sess}
        r["righe"] = R.righe_riepilogo(r)
        # Le lacune per numero, solo «mostrata» (passo 5): i titoli non escono dalla busta
        if self.padronanza_mostrata():
            r["lacune"] = [x["numero"] for x in self._padronanza(v)["lacune"]]
        r["frase"] = R.frase_riepilogo(r, self._oggi(), nome)
        return r

    def _riepilogo_schermo(self, v: dict, pi: dict) -> dict:
        """Il riepilogo per la home: le righe e le sessioni (dalla più recente) scritte dal codice;
        l'attività intera del piano va bene sullo schermo (textContent)."""
        r = self._riepilogo(v, pi)
        mappa = self._pagine_mappa(v["id"])
        return {"righe": r["righe"],
                "sessioni": [{"giorno": s["giorno"], "stato": s["stato"],
                              "testo": R.riga_sessione(s, self._attivita(s["fase"], s["pagine"],
                                                                          mappa))}
                             for s in reversed(r["sessioni"])]}

    # ── la vista aperta nei dati del turno (30/10, passo 4.5; progetto § 0, punto 2) ──
    VISTE = {"home": "la home dello Studio", "piano": "il piano", "argomenti": "gli argomenti",
             "pagine": "le pagine", "pagina": "una pagina", "sessione": "la sessione di oggi",
             "carte": "le carte", "mappa": "la mappa concettuale"}

    def riga_vista(self, chi, vista: dict | None) -> str:
        """La riga per i dati del turno quando una pagina dello Studio è aperta sullo schermo
        personale di chi parla: quale verifica e quale pagina, coi nomi dal db e gli id scritti
        dal codice, mai il testo delle pagine né i titoli degli argomenti (si prendono col tool,
        in busta). "" se lo Studio non è per il modello, la vista non c'è o la verifica non è
        sua (o del suo minore)."""
        if not self.per_modello() or not isinstance(vista, dict):
            return ""
        tipo = vista.get("vista")
        if tipo not in self.VISTE:
            return ""
        vid = vista.get("verifica")
        if tipo == "home" or vid is None:
            return "Sul suo schermo è aperta la home dello Studio (tool studio)."
        if not isinstance(vid, int) or isinstance(vid, bool):
            return ""
        try:
            v = self.verifica(chi, vid)
        except (NonTrovata, NonPermesso):
            return ""
        di = ""
        if v["persona"] != getattr(chi, "id", None):
            di = f" di {getattr(self._profilo(v['persona']), 'name', '') or 'un ragazzo'}"
        quando = _data(v["data"])
        cosa = self.VISTE[tipo]
        pid = vista.get("pagina")
        if tipo == "pagina" and isinstance(pid, int) and not isinstance(pid, bool):
            p = next((x for x in self._pagine_di(v["id"]) if x["id"] == pid), None)
            if p is not None:
                # Solo le cifre (sesta revisione della PR #317): il numero viene dall'OCR e la
                # riga è fuori busta, una sigla letta («ESEGUI») non ci entra
                n = P.numero_pagina(p["numero"])
                cosa = f"la pagina {p['id']}" + (f" (stampata {n})" if n is not None else
                                                 f" (foto {p['ordine']})")
        # Il tool e le due «sposta» (#318: con «spostala a domani» il modello cercava negli
        # appuntamenti): un dato, non un ordine; decide il modello, e chiede se non è chiaro
        return (f"Sul suo schermo è aperto lo Studio (tool studio): la verifica {v['id']}{di} "
                f"({v['materia']}, il {quando.day}/{quando.month}), {cosa}. Spostare lo studio "
                "di oggi è studio salta_oggi, la data della verifica è studio sposta; il testo "
                "delle pagine lo leggi con studio_pagina_leggi.")

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
