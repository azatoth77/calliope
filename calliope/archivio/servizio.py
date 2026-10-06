"""
Il servizio dell'archivio dei documenti di casa (03/10/2026): la cartella osservata, la coda
dei file da leggere, l'elaborazione in secondo piano e le interrogazioni con i permessi.

Ingresso. Un thread guarda `archivio_cartella` ogni `archivio_intervallo_min` minuti: un file
nuovo o cambiato (dimensione, data di modifica, poi SHA-256) va in coda; un file uguale a un
altro già letto (stesso SHA-256) è lo stesso documento; un file sparito toglie il documento e
quello che affermava nel grafo (non se sparisce tutta la cartella: un disco staccato non
svuota l'archivio). Ogni documento si rielabora da solo quando cambia la versione
dell'estrattore (`tipi.VERSIONE`, solo l'estrazione) o della lettura (`testo.VERSIONE`,
anche l'OCR). La voce non aspetta mai: il thread dell'archivio è l'unico che scrive.

Permessi (decisi qui, nel codice; docs/ricerche/2026-10-03-documenti-grafo.md, §5):
- gli ospiti non vedono niente;
- un documento **sensibile** (referti, documenti d'identità: `tipi.Tipo.sensibile`) lo vedono
  solo la persona interessata (intestatario collegato al suo profilo, o la sua cartella) e chi
  amministra, e mai nella zona grigia della conversazione;
- un documento nella cartella di una persona (la prima sottocartella ha il nome di un profilo:
  «Documenti casa/Giulia/…») è **personale**: lo vedono lei e chi amministra;
- tutto il resto è **della casa**: lo vedono i familiari.
Il collegamento tra una persona dei documenti e un profilo di Calliope è esplicito:
`archivio_intestatari` ({profilo: "nome e cognome, codice fiscale, …"}) oppure il nome
completo del profilo uguale a quello sul documento. Un nome di battesimo da solo non basta
(«Maria» madre e figlia).
"""

import datetime
import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import normalizza as nz
from . import testo as lettura
from . import tipi
from .grafo import Grafo

_IO = {"io", "me", "mio", "mia", "miei", "mie", "mi", "per me", "di me", "mie cose"}
_VUOTE = {"il", "lo", "la", "i", "gli", "le", "un", "una", "uno", "di", "del", "della", "dei",
          "delle", "degli", "dello", "da", "in", "con", "su", "per", "a", "al", "alla", "e", "o",
          "mio", "mia", "miei", "mie", "nostro", "nostra", "nostri", "nostre", "suo", "sua",
          "che", "quanto", "quanti", "quale", "quali", "ho", "abbiamo", "ha", "documento",
          "documenti", "dove", "cosa", "c", "l", "d", "un'", "trova", "cerca", "dimmi"}


@dataclass
class Chi:
    """Chi fa la domanda: livello e profilo (dalla voce o dal lavoro dell'agente)."""
    livello: str = "ospite"           # ospite | familiare | amministra
    profilo: str | None = None        # UserProfile.id
    nome: str | None = None           # UserProfile.name
    zona_grigia: bool = False         # identità confermata solo dalla conversazione

    @classmethod
    def da_ctx(cls, ctx) -> "Chi":
        sc = getattr(ctx, "speaker_ctx", None)
        name = getattr(sc, "current_speaker", None)
        prof = ctx.speakers.get(name) if name and getattr(ctx, "speakers", None) else None
        return cls(getattr(sc, "current_level", "ospite") or "ospite",
                   getattr(prof, "id", None), getattr(prof, "name", None),
                   bool(getattr(sc, "from_session", False))
                   or getattr(sc, "identified_by", None) == "conversazione")


def periodo(testo: str, oggi: datetime.date | None = None
            ) -> tuple[str | None, str | None, str]:
    """Periodo detto → (dal, al escluso, come dirlo), date ISO. Anni espliciti («2025», «nel
    2025», «settembre 2025»), poi quelli di tempi.parse_past_range («quest'anno», «l'anno
    scorso», «agosto», «il mese scorso»). (None, None, "") = nessun filtro."""
    oggi = oggi or datetime.date.today()
    t = nz.senza_accenti(str(testo or "")).lower().strip()
    if not t:
        return None, None, ""
    m = re.search(r"\b(" + "|".join(nz.MESI) + r")\s+(?:del\s+)?(\d{4})\b", t)
    if m:
        mese, anno = nz.MESI.index(m.group(1)) + 1, int(m.group(2))
        dal = datetime.date(anno, mese, 1)
        al = datetime.date(anno + (mese == 12), mese % 12 + 1, 1)
        return dal.isoformat(), al.isoformat(), f"a {m.group(1)} {anno}"
    anni = [int(a) for a in re.findall(r"\b(19\d\d|20\d\d)\b", t)]
    if len(anni) == 1:
        return f"{anni[0]}-01-01", f"{anni[0] + 1}-01-01", f"nel {anni[0]}"
    if len(anni) == 2:
        a, b = sorted(anni)
        return f"{a}-01-01", f"{b + 1}-01-01", f"dal {a} al {b}"
    from ..tempi import parse_past_range
    now = datetime.datetime.combine(oggi, datetime.time(12))
    dal, al, detto = parse_past_range(t, now)
    if dal is None and al is None:
        return None, None, ""
    return (dal.date().isoformat() if dal else None,
            al.date().isoformat() if al else (oggi + datetime.timedelta(days=1)).isoformat(),
            detto)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blocco in iter(lambda: f.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


class Archivio:
    def __init__(self, cfg, grafo: Grafo, cartella, estrattore=None, ocr=None, log=print,
                 profili=None, prima_di_chiamare=None):
        self.cfg = cfg
        self.grafo = grafo
        self.cartella = Path(cartella) if cartella else None
        self.estrattore = estrattore
        self.ocr = ocr
        self.log = log
        # Funzione che restituisce i nomi dei profili registrati (le cartelle personali)
        self.profili = profili or (lambda: [])
        self.intervallo_s = float(getattr(cfg, "archivio_intervallo_min", 10.0)) * 60
        self.max_pagine = int(getattr(cfg, "archivio_max_pagine", 12))
        self.max_byte = float(getattr(cfg, "archivio_max_mb", 50.0)) * 1024 * 1024
        self._sveglia = threading.Event()
        self._chiuso = False
        self._thread = None
        self.in_lavorazione: str | None = None
        self.ultimo_giro: dict = {}
        # Ultimo errore del modello (OCR o estrazione), per il registro delle capacità
        self.diagnosi: dict = {"codice": "non_provato", "quando": 0.0}

    # ─────────────────────────── ciclo ───────────────────────────
    def avvia(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._ciclo, daemon=True, name="archivio")
            self._thread.start()

    def sveglia(self):
        self._sveglia.set()

    def close(self):
        self._chiuso = True
        self._sveglia.set()
        for x in (self.ocr, getattr(self.estrattore, "cliente", None)):
            try:
                if x is not None and hasattr(x, "close"):
                    x.close()
            except Exception:  # noqa: BLE001
                pass

    def _ciclo(self):
        while not self._chiuso:
            try:
                self.giro()
            except Exception as e:  # noqa: BLE001 — un giro rotto non ferma l'archivio
                self.log(f"[ARCHIVIO] errore nel giro: {type(e).__name__}: {e}")
            self._sveglia.wait(self.intervallo_s)
            self._sveglia.clear()

    def giro(self) -> dict:
        """Una passata: scansione della cartella, poi i file in coda, uno alla volta."""
        t0 = time.monotonic()
        coda, tolti = self.scansiona()
        fatti = errori = 0
        for p in coda:
            if self._chiuso:
                break
            esito = self.elabora_file(p)
            if esito == "ok":
                fatti += 1
            elif esito == "modello_giu":
                break                      # si riprova al giro dopo
            else:
                errori += 1
        self.ultimo_giro = {"quando": time.time(), "in_coda": len(coda), "fatti": fatti,
                            "errori": errori, "tolti": tolti,
                            "secondi": round(time.monotonic() - t0, 1)}
        if fatti or errori or tolti:
            self.log(f"[ARCHIVIO] {fatti} documenti letti, {errori} con errori, {tolti} tolti "
                     f"({self.ultimo_giro['secondi']} s)")
        return self.ultimo_giro

    # ─────────────────────────── scansione ───────────────────────────
    def _file(self):
        root = self.cartella
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root)
            if any(part.startswith((".", "~$")) for part in rel.parts):
                continue
            if p.is_file() and p.suffix.lower() in lettura.ESTENSIONI:
                yield p

    def scansiona(self) -> tuple[list[Path], int]:
        """(file da leggere, documenti tolti). Non legge i file uguali a prima."""
        if self.cartella is None or not self.cartella.is_dir():
            return [], 0
        g = self.grafo
        noti = {r["percorso"]: r for r in g.leggi("SELECT * FROM file")}
        visti, coda = set(), []
        for p in self._file():
            key = str(p.relative_to(self.cartella)).replace("\\", "/")
            visti.add(key)
            st = p.stat()
            if st.st_size > self.max_byte:
                continue
            r = noti.get(key)
            if r is not None and r["dimensione"] == st.st_size and \
                    abs((r["mtime"] or 0) - st.st_mtime) < 1 and self._aggiornato(r):
                continue
            coda.append(p)
        tolti = 0
        spariti = [k for k in noti if k not in visti]
        # Cartella vuota o disco staccato: non si svuota l'archivio
        if spariti and visti:
            with g.transazione() as db:
                for k in spariti:
                    row = db.execute("SELECT nodo FROM file WHERE percorso = ?", (k,)).fetchone()
                    db.execute("DELETE FROM file WHERE percorso = ?", (k,))
                    doc = row["nodo"] if row else None
                    if doc is not None and db.execute(
                            "SELECT COUNT(*) FROM file WHERE nodo = ?", (doc,)).fetchone()[0] == 0:
                        g.togli_documento(db, doc)
                        tolti += 1
        return coda, tolti

    def _aggiornato(self, r) -> bool:
        if r["stato"] == "ok":
            return r["versione"] == self._versione()
        # Gli errori di lettura si riprovano solo con una versione nuova o un file cambiato;
        # quelli del modello (giù, in attesa) al giro dopo
        return r["stato"] == "errore" and r["versione"] == self._versione()

    @staticmethod
    def _versione() -> str:
        return f"{tipi.VERSIONE}.{lettura.VERSIONE}"

    # ─────────────────────────── un file ───────────────────────────
    def _segna(self, key, sha, st, stato, errore=None, nodo=None):
        with self.grafo.transazione() as db:
            db.execute("INSERT INTO file (percorso, sha256, dimensione, mtime, stato, errore, "
                       "versione, nodo, aggiornato) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                       "ON CONFLICT(percorso) DO UPDATE SET sha256 = excluded.sha256, "
                       "dimensione = excluded.dimensione, mtime = excluded.mtime, "
                       "stato = excluded.stato, errore = excluded.errore, "
                       "versione = excluded.versione, nodo = excluded.nodo, "
                       "aggiornato = excluded.aggiornato",
                       (key, sha, st.st_size, st.st_mtime, stato, errore, self._versione(), nodo,
                        datetime.datetime.now().isoformat(timespec="seconds")))

    def elabora_file(self, path) -> str:
        """Legge, estrae e mette nel grafo un file. «ok», «errore» (il file) o «modello_giu»
        (riprovare dopo)."""
        p = Path(path)
        key = str(p.relative_to(self.cartella)).replace("\\", "/") if self.cartella else p.name
        self.in_lavorazione = key
        try:
            st = p.stat()
            sha = _sha256(p)
        except OSError as e:
            self.in_lavorazione = None
            self.log(f"[ARCHIVIO] {key}: non si legge ({e.strerror})")
            return "errore"
        try:
            g = self.grafo
            prima = g.leggi("SELECT n.id, s.versione, s.versione_testo, s.testo, s.metodo "
                            "FROM nodi n LEFT JOIN schede s ON s.nodo = n.id "
                            "WHERE n.tipo = 'documento' AND n.chiave = ?", (f"sha:{sha}",))
            prima = prima[0] if prima else None
            if prima is not None and prima["versione"] == tipi.VERSIONE and \
                    prima["versione_testo"] == lettura.VERSIONE:
                self._segna(key, sha, st, "ok", nodo=prima["id"])   # una copia dello stesso
                return "ok"
            if prima is not None and prima["versione_testo"] == lettura.VERSIONE and prima["testo"]:
                letto = lettura.Estratto(prima["testo"], prima["metodo"] or "salvato")
            else:
                try:
                    letto = lettura.leggi(p, self.ocr, self.max_pagine)
                except lettura.ErroreTesto as e:
                    self._segna(key, sha, st, "errore", str(e))
                    self.log(f"[ARCHIVIO] {key}: {e}")
                    return "errore"
            if not letto.testo.strip():
                self._segna(key, sha, st, "errore", "nessun testo leggibile")
                return "errore"
            if self.estrattore is None:
                self._segna(key, sha, st, "in_attesa", "estrattore spento")
                return "modello_giu"
            try:
                est = self.estrattore.elabora(letto.testo, p.name)
            except Exception as e:  # noqa: BLE001 — rete, modello giù, JSON non valido
                codice = getattr(e, "codice", None) or type(e).__name__
                self.diagnosi = {"codice": str(codice), "motivo": str(e)[:200],
                                 "quando": time.time()}
                self._segna(key, sha, st, "in_attesa", f"estrazione non riuscita ({codice})")
                self.log(f"[ARCHIVIO] {key}: estrazione non riuscita ({codice})")
                return "modello_giu"
            self.diagnosi = {"codice": "ok", "quando": time.time()}
            doc = self.registra(key, sha, letto, est)
            self._segna(key, sha, st, "ok", nodo=doc)
            return "ok"
        except Exception as e:  # noqa: BLE001
            self.log(f"[ARCHIVIO] {key}: {type(e).__name__}: {e}")
            try:
                self._segna(key, sha, st, "errore", f"{type(e).__name__}")
            except Exception:  # noqa: BLE001
                pass
            return "errore"
        finally:
            self.in_lavorazione = None

    def registra(self, key: str, sha: str, letto, est: dict) -> int:
        """Il documento nel grafo: nodo, scheda, testo, nodi e archi (una transazione)."""
        tipo, s = est["tipo"], est["scheda"]
        parti = key.split("/")
        cartella = parti[0] if len(parti) > 1 else ""
        nome = tipi.descrivi(tipo, s, Path(key).stem)
        attrs = {"tipo_doc": tipo, "categoria": tipi.categoria(tipo, s),
                 "file": parti[-1], "percorso": key, "cartella": cartella,
                 "sensibile": tipi.TIPI[tipo].sensibile, "numero": s.get("numero"),
                 "oggetto": s.get("oggetto"), "versione": tipi.VERSIONE}
        g = self.grafo
        with g.transazione() as db:
            doc = g.nodo(db, "documento", f"sha:{sha}", nome, data=s.get("data_documento"),
                         valore=tipi.importo_principale(tipo, s), attributi=attrs)
            # Rielaborazione: prima si toglie quello che affermava la versione vecchia
            db.execute("UPDATE nodi SET data = ?, valore = ? WHERE id = ?",
                       (s.get("data_documento"), tipi.importo_principale(tipo, s), doc))
            g.togli_fonte(db, doc)
            tipi.nel_grafo(g, db, doc, tipo, s)
            db.execute("INSERT OR REPLACE INTO schede (nodo, tipo, versione, scheda, testo, "
                       "metodo, versione_testo, scartati) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (doc, tipo, tipi.VERSIONE, json.dumps(s, ensure_ascii=False),
                        letto.testo, letto.metodo, lettura.VERSIONE,
                        json.dumps(est.get("scartati") or [], ensure_ascii=False)))
            db.execute("DELETE FROM testi WHERE rowid = ?", (doc,))
            db.execute("INSERT INTO testi (rowid, nome, testo) VALUES (?, ?, ?)",
                       (doc, nome + " " + parti[-1], letto.testo))
        return doc

    def riprocessa(self) -> int:
        """Segna tutti i file da rileggere al prossimo giro (l'OCR salvato si riusa se la
        versione della lettura è la stessa). Restituisce quanti."""
        with self.grafo.transazione() as db:
            n = db.execute("UPDATE file SET versione = 'vecchia'").rowcount
            db.execute("UPDATE schede SET versione = 'vecchia'")
        self.sveglia()
        return n

    # ─────────────────────────── permessi ───────────────────────────
    def persone_di(self, nome_profilo: str | None) -> set[int]:
        """I nodi persona collegati a un profilo: i nomi e i codici fiscali di
        archivio_intestatari, o il nome completo del profilo (almeno due parole)."""
        if not nome_profilo:
            return set()
        mappa = getattr(self.cfg, "archivio_intestatari", None) or {}
        voci = [x.strip() for k, v in mappa.items() if k.casefold() == nome_profilo.casefold()
                for x in str(v or "").split(",") if x.strip()]
        if len(nome_profilo.split()) >= 2:
            voci.append(nome_profilo)
        forme = set()
        for v in voci:
            cf = nz.codice_fiscale(v)
            forme.add("cf:" + cf if cf else "nome:" + nz.nome_persona(v))
        if not forme:
            return set()
        segn = ",".join("?" * len(forme))
        return {r["nodo"] for r in self.grafo.leggi(
            f"SELECT nodo FROM alias WHERE tipo = 'persona' AND forma IN ({segn})",
            tuple(forme))}

    def _persone_doc(self, ids) -> dict[int, set[int]]:
        ids = list(ids)
        out: dict[int, set[int]] = {i: set() for i in ids}
        for i in range(0, len(ids), 500):
            pezzo = ids[i:i + 500]
            for r in self.grafo.leggi(
                    f"SELECT da, a FROM archi WHERE rel = 'intestato_a' AND da IN "
                    f"({','.join('?' * len(pezzo))})", tuple(pezzo)):
                out[r["da"]].add(r["a"])
        return out

    def puo_vedere(self, doc: dict, chi: Chi, mie: set[int] | None = None) -> bool:
        if chi.livello not in ("familiare", "amministra") or chi.profilo is None:
            return False
        a = doc.get("attributi") or {}
        sens = bool(a.get("sensibile"))
        if sens and chi.zona_grigia:
            return False
        if chi.livello == "amministra":
            return True
        mie = self.persone_di(chi.nome) if mie is None else mie
        cartella = (a.get("cartella") or "").casefold()
        profili = {n.casefold() for n in self.profili()}
        mio = (bool(chi.nome) and cartella == chi.nome.casefold()) or \
            bool(doc.get("persone", set()) & mie)
        if sens or cartella in profili:
            return mio
        return True

    def visibilita_scheda(self, doc: dict) -> str:
        """«casa» o «personale» per gli schermi."""
        a = doc.get("attributi") or {}
        cartella = (a.get("cartella") or "").casefold()
        if a.get("sensibile") or cartella in {n.casefold() for n in self.profili()}:
            return "personale"
        return "casa"

    # ─────────────────────────── interrogazioni ───────────────────────────
    def documenti(self, chi: Chi, tipo: str | None = None, dal: str | None = None,
                  al: str | None = None, persone: set[int] | None = None,
                  categoria: str | None = None, ente: str | None = None) -> list[dict]:
        """I documenti visibili a `chi`, filtrati, dal più recente."""
        sql = "SELECT * FROM nodi WHERE tipo = 'documento'"
        params: list = []
        if tipo:
            sql += " AND json_extract(attributi, '$.tipo_doc') = ?"
            params.append(tipo)
        if categoria:
            sql += " AND json_extract(attributi, '$.categoria') = ?"
            params.append(categoria)
        if dal:
            sql += " AND data >= ?"
            params.append(dal)
        if al:
            sql += " AND data < ?"
            params.append(al)
        sql += " ORDER BY data DESC, id DESC"
        rows = self.grafo.leggi(sql, tuple(params))
        pers = self._persone_doc(r["id"] for r in rows)
        mie = self.persone_di(chi.nome)
        out = []
        enti = self._enti_di(ente) if ente else None
        emessi = self._emessi(enti) if enti is not None else None
        for r in rows:
            d = {"id": r["id"], "nome": r["nome"], "data": r["data"], "totale": r["valore"],
                 "attributi": json.loads(r["attributi"] or "{}"), "persone": pers[r["id"]]}
            if persone is not None and not (d["persone"] & persone):
                continue
            if emessi is not None and d["id"] not in emessi:
                continue
            if self.puo_vedere(d, chi, mie):
                out.append(d)
        return out

    def _enti_di(self, nome: str) -> set[int]:
        k = nz.nome_ente(nome)
        if not k:
            return set()
        out = set()
        for r in self.grafo.leggi("SELECT forma, nodo FROM alias WHERE tipo = 'ente' AND "
                                  "forma LIKE 'nome:%'"):
            f = r["forma"][5:]
            if k == f or f" {k} " in f" {f} " or nz.simile(f, k, 0.85):
                out.add(r["nodo"])
        return out

    def _emessi(self, enti: set[int]) -> set[int]:
        if not enti:
            return set()
        return {r["da"] for r in self.grafo.leggi(
            f"SELECT da FROM archi WHERE rel = 'emesso_da' AND a IN ({','.join('?' * len(enti))})",
            tuple(enti))}

    def persone_da(self, detto: str, chi: Chi) -> set[int] | None:
        """«io», «mia», «Giulia», «Laura Bianchi» → i nodi persona; None = nessun filtro."""
        t = nz.piatto(detto)
        if not t:
            return None
        if t in _IO or set(t.split()) <= _IO:
            return self.persone_di(chi.nome)
        for n in self.profili():
            if nz.piatto(n) == t:
                return self.persone_di(n) | self._persone_per_parole(t)
        return self._persone_per_parole(t)

    def _persone_per_parole(self, t: str) -> set[int]:
        parole = set(nz.nome_persona(t).split())
        if not parole:
            return set()
        return {r["nodo"] for r in self.grafo.leggi(
            "SELECT forma, nodo FROM alias WHERE tipo = 'persona' AND forma LIKE 'nome:%'")
                if parole <= set(r["forma"][5:].split())}

    def cerca(self, chi: Chi, cosa: str = "", tipo: str | None = None,
              persona: str = "", periodo_detto: str = "", limite: int = 5) -> dict:
        """I documenti più adatti alla richiesta (visibili a chi chiede)."""
        dal, al, detto = periodo(periodo_detto)
        persone = self.persone_da(persona, chi) if persona else None
        if persone is not None and not persone:
            return {"documenti": [], "periodo": detto, "persona_sconosciuta": True}
        docs = self.documenti(chi, tipo, dal, al, persone)
        parole = [w for w in nz.piatto(cosa).split() if w not in _VUOTE and len(w) > 1]
        if parole and docs:
            punti = self._punteggi(parole, {d["id"] for d in docs})
            for d in docs:
                d["punti"] = punti.get(d["id"], 0.0)
            docs = [d for d in docs if d["punti"] > 0]
            # a parità di punti il più recente
            docs.sort(key=lambda d: (-round(d["punti"], 1), -_giorno(d["data"])))
        return {"documenti": docs[:limite], "totale": len(docs), "periodo": detto}

    def _punteggi(self, parole: list[str], ammessi: set[int]) -> dict[int, float]:
        """Punteggio per documento: le parole nel nome (descrizione, categoria, ente) contano
        molto più che nel testo. Radice = la parola senza l'ultima lettera («bollett» per
        bolletta e bollette, «contratt»: con 5 lettere «contr» prendeva anche «Contraente»)."""
        radici = [w[:-1] if len(w) > 4 else w for w in parole]
        q = " OR ".join(f'"{r}"*' for r in radici)
        out: dict[int, float] = {}
        try:
            rows = self.grafo.leggi("SELECT rowid, nome, bm25(testi, 4.0, 1.0) AS b FROM testi "
                                    "WHERE testi MATCH ?", (q,))
        except Exception:  # noqa: BLE001 — una query FTS strana non ferma la ricerca
            rows = []
        for r in rows:
            if r["rowid"] not in ammessi:
                continue
            nome = nz.piatto(r["nome"])
            nel_nome = sum(1 for x in radici if re.search(rf"\b{re.escape(x)}", nome))
            out[r["rowid"]] = nel_nome * 3 + min(2.0, -r["b"])
        # categoria e tipo: «luce» → bollette della luce anche se la parola non è nel testo
        for d_id, attrs in ((r["id"], json.loads(r["attributi"] or "{}")) for r in self.grafo.leggi(
                f"SELECT id, attributi FROM nodi WHERE tipo = 'documento' AND id IN "
                f"({','.join('?' * len(ammessi))})", tuple(ammessi))):
            extra = sum(2 for x in radici if (attrs.get("categoria") or "").startswith(x)
                        or (attrs.get("tipo_doc") or "").startswith(x))
            if extra:
                out[d_id] = out.get(d_id, 0.0) + extra
        return out

    def scheda(self, doc_id: int) -> dict:
        rows = self.grafo.leggi("SELECT tipo, scheda FROM schede WHERE nodo = ?", (doc_id,))
        if not rows:
            return {}
        return {"tipo": rows[0]["tipo"], **json.loads(rows[0]["scheda"])}

    def scadenze(self, chi: Chi, giorni: int = 30, tipo: str | None = None,
                 oggi: datetime.date | None = None) -> list[dict]:
        """Le scadenze da oggi a `giorni` giorni, dei documenti visibili."""
        oggi = oggi or datetime.date.today()
        fino = (oggi + datetime.timedelta(days=giorni)).isoformat()
        rows = self.grafo.leggi(
            "SELECT s.data, json_extract(s.attributi, '$.cosa') AS cosa, "
            "json_extract(s.attributi, '$.calcolata') AS calcolata, r.da AS doc "
            "FROM nodi s JOIN archi r ON r.a = s.id AND r.rel = 'scade_il' "
            "WHERE s.tipo = 'scadenza' AND s.data >= ? AND s.data <= ? ORDER BY s.data",
            (oggi.isoformat(), fino))
        if not rows:
            return []
        visibili = {d["id"]: d for d in self.documenti(chi, tipo)}
        out = []
        for r in rows:
            d = visibili.get(r["doc"])
            if d is not None:
                out.append({"data": r["data"], "cosa": r["cosa"], "calcolata": bool(r["calcolata"]),
                            "documento": d})
        return out

    def somma(self, chi: Chi, categoria: str | None = None, tipo: str | None = None,
              ente: str = "", persona: str = "", periodo_detto: str = "") -> dict:
        """La somma degli importi dei documenti (bollette, ricevute, polizze; non i canoni
        dei contratti, che sono mensili), fatta dal programma."""
        dal, al, detto = periodo(periodo_detto)
        persone = self.persone_da(persona, chi) if persona else None
        tipi_somma = [tipo] if tipo else ["bolletta", "ricevuta", "assicurazione"]
        docs = []
        for t in tipi_somma:
            docs += self.documenti(chi, t, dal, al, persone, categoria or None, ente or None)
        con = [d for d in docs if d["totale"] is not None]
        per_anno: dict[str, float] = {}
        for d in con:
            if d["data"]:
                per_anno[d["data"][:4]] = round(per_anno.get(d["data"][:4], 0) + d["totale"], 2)
        date_ = sorted(d["data"] for d in con if d["data"])
        return {"totale": round(sum(d["totale"] for d in con), 2), "documenti": len(con),
                "senza_importo": len(docs) - len(con), "periodo": detto, "dal": dal, "al": al,
                "primo": date_[0] if date_ else None, "ultimo": date_[-1] if date_ else None,
                "per_anno": dict(sorted(per_anno.items())), "elenco": con}

    # ─────────────────────────── stato ───────────────────────────
    def stato(self) -> dict:
        g = self.grafo
        per_stato = {r["stato"]: r["n"] for r in g.leggi(
            "SELECT stato, COUNT(*) AS n FROM file GROUP BY stato")}
        docs = g.leggi("SELECT COUNT(*) AS n FROM nodi WHERE tipo = 'documento'")[0]["n"]
        return {"documenti": docs, "file": per_stato, "ultimo_giro": self.ultimo_giro,
                "in_lavorazione": self.in_lavorazione, "cartella": str(self.cartella or ""),
                "diagnosi": self.diagnosi}


def _giorno(iso: str | None) -> int:
    if not iso:
        return 0
    try:
        return datetime.date.fromisoformat(iso).toordinal()
    except ValueError:
        return 0
