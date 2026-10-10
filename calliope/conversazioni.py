"""
L'archivio delle conversazioni (05/10/2026, fase 2 del progetto «Contesto di Calliope»,
docs/ricerche/2026-10-05-contesto-compressione.md).

Ogni turno finito di una conversazione si salva qui, in `conversazioni.db` (accanto a
memoria.db ma separato: i ricordi si tengono per sempre, le conversazioni
`conversazioni_giorni` giorni). Così la compressione della storia e la fine di una
conversazione non perdono niente, e `conversazione_cerca` ritrova «cosa ti avevo detto
stamattina sul preventivo?».

- **Tabelle**: `conversazioni` (chi, dove, quando, riassunto di chiusura), `turni` (domanda,
  risposta, azioni con l'esito e la frase detta; mai gli argomenti dei tool), `turni_fts`
  (FTS5) e il vettore di ogni turno (float32 in un BLOB, del modello scritto accanto),
  `correnti` (la conversazione in corso, salvata a ogni turno: un riavvio non la perde).
- **Ricerca ibrida**: FTS5 (bm25) + vettori chiesti al server del modello (Ollama
  `/api/embed`, o `/v1/embeddings` di un server OpenAI), coseno in numpy (l'archivio è
  piccolo: niente indice vettoriale), fusione dei due elenchi con RRF (k = 60). Senza modello
  di embedding (non scaricato, server giù) resta FTS5, e il registro delle capacità lo dice.
- **Visibilità**: ognuno ritrova solo le proprie conversazioni (id del profilo). Quelle degli
  ospiti si archiviano ma il modello non le recupera mai, né per loro né per altri: le vede
  chi amministra, da terminale (`python -m calliope.conversazioni --elenco/--mostra`) e a voce
  solo se riconosciuto dalla voce (tool con `ospiti=true`).
- **Cancellazione**: per persona («dimentica le nostre conversazioni»), e dopo
  `conversazioni_giorni` giorni (all'avvio e una volta al giorno). Dal 10/10 «dimentica» è vera
  (§ 2.4 del progetto del registro degli eventi): `secure_delete`, l'indice FTS5 ricompattato,
  il checkpoint del WAL, anche la conversazione in corso salvata (`correnti`) e il registro
  degli eventi della persona (tabella `eventi`, calliope/eventi/registro.py).
- **Scheda «Conversazione»** (08/10): ogni turno porta in `meta` il satellite o lo schermo e il
  canale (colonna della versione 2); dal ciclo si archivia a turno finito, e `su_turni` lo
  manda in diretta agli schermi personali della persona (mai per gli ospiti); `chat` e
  `chat_markdown` per la scheda e «Scarica»; `su_dimentica` la svuota.
- I lavori lenti (inserimenti, vettori, pulizia) li fa un thread suo, in ordine: la voce non
  aspetta mai il disco né il server degli embedding. La ricerca è sincrona (la chiama il tool).
- **Mai un modello in più durante una conversazione** (06/10, prova e2e sulla DGX: Ollama ne
  tiene 3, Calliope ne usa 4, e il primo embedding scacciava il guardiano o la voce). I vettori
  dei turni si calcolano solo con Calliope inattiva da `conversazioni_vettori_inattivita_s`
  (10 minuti), a lotti, con `keep_alive: 0` (il modello si scarica subito), oppure se il
  modello è già caricato; la domanda di una ricerca si trasforma in vettore solo se il modello
  è caricato o Ollama ha un posto libero (calliope/ollama_carico.py). Altrimenti, e finché i
  vettori mancano, la ricerca va per parole (FTS5).

Solo libreria standard e numpy (già una dipendenza di base): va anche su Windows ARM.
"""
from __future__ import annotations

import datetime
import json
import os
import queue
import re
import sqlite3
import threading
import time
from pathlib import Path

from .persistenza import apri_db, prepara_schema

MODULO = "conversazioni"
RRF_K = 60
# Parole che non servono alla ricerca per parole (FTS5): articoli, preposizioni, verbi di
# cornice della domanda («cosa ti avevo detto…»)
_VUOTE = frozenset(
    "il lo la i gli le un uno una di a da in con su per tra fra del dello della dei degli "
    "delle al allo alla ai agli alle dal dalla dai dalle nel nello nella nei negli nelle sul "
    "sulla sui sulle e ed o che chi cosa come quando dove quale quali è sono era ho hai ha "
    "abbiamo avevo avevi aveva detto detta dette detti dire dici dicevo parlato parlare "
    "ricordi ricordo ricordami ti mi ci si ne non più anche me te noi voi lui lei mio mia "
    "tuo tua suo sua nostro nostra quello quella questo questa stamattina oggi ieri prima "
    "volta conversazione conversazioni calliope cercami cerca trova sai quanto quanta quanti "
    "quante fa fare faccio dovevo dovevamo volevo volevamo serviva servivano vengono costava "
    "costavano era erano stato stata giorni questi queste quel quella quei mi ti si".split())
_PAROLA = re.compile(r"[a-zàèéìòù0-9]+", re.I)
_ISTRUZIONE_QWEN = ("Instruct: Trova i turni di conversazione passati che rispondono alla "
                    "domanda\nQuery: ")


# Somiglianza minima per modello (05/10, prove/misura_conversazioni.py --embedding): sotto, il
# turno più vicino è di un altro argomento. Sul banco il turno giusto sta a 0,33–0,8 (mediana
# 0,57), il miglior turno sbagliato a 0,36 di mediana, le domande senza risposta fino a 0,43:
# la soglia toglie solo il rumore, decide il modello con i risultati davanti. Altri: 0,35
SOGLIA_VETTORI = {"qwen3-embedding": 0.35, "bge-m3": 0.38}


def soglia_vettori(modello: str) -> float:
    m = (modello or "").lower()
    for nome, v in SOGLIA_VETTORI.items():
        if m.startswith(nome):
            return v
    return 0.35 if m else 0.0


def percorso_db(cfg) -> Path:
    p = getattr(cfg, "conversazioni_db", None) or "conversazioni.db"
    p = Path(os.path.expanduser(str(p)))
    if not p.is_absolute():
        p = Path(getattr(cfg, "config_dir", None) or ".") / p
    return p


def _v1(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS conversazioni (
            id INTEGER PRIMARY KEY, persona TEXT, nome TEXT, ospite INTEGER NOT NULL DEFAULT 0,
            luogo TEXT, inizio REAL NOT NULL, fine REAL, motivo TEXT, riassunto TEXT,
            riassunto_dati TEXT, ricordi_proposti TEXT);
        CREATE INDEX IF NOT EXISTS conv_persona ON conversazioni(persona, fine);
        CREATE TABLE IF NOT EXISTS turni (
            id INTEGER PRIMARY KEY, conv INTEGER NOT NULL, quando REAL NOT NULL,
            domanda TEXT, risposta TEXT, azioni TEXT, riservato INTEGER NOT NULL DEFAULT 0,
            vettore BLOB, modello TEXT);
        CREATE INDEX IF NOT EXISTS turni_conv ON turni(conv);
        CREATE VIRTUAL TABLE IF NOT EXISTS turni_fts USING fts5(testo, tokenize='unicode61');
        CREATE TABLE IF NOT EXISTS correnti (
            chiave TEXT PRIMARY KEY, stato TEXT NOT NULL, aggiornata REAL NOT NULL);
    """)


def _v2(db):
    """08/10: `meta` dei turni (JSON: il satellite o lo schermo del turno, «voce» o «scritto»)
    per la scheda «Conversazione» degli schermi personali. NULL nei turni di prima."""
    from .persistenza import aggiungi_colonna
    aggiungi_colonna(db, "turni", "meta", "TEXT")


MIGRAZIONI = [_v1, _v2]


# ─────────────────────────── embedding ───────────────────────────
class Embedder:
    """I vettori dei testi dal server del modello. Ollama: `/api/embed` con `num_gpu: 0`
    (sulla CPU: sul portatile la VRAM serve alla voce e a Whisper, e un modello in più la
    farebbe scaricare); un server OpenAI: `/v1/embeddings`. Vettori normalizzati (float32)."""

    def __init__(self, url: str, modello: str, cpu: bool = True, timeout_s: float = 20.0):
        import httpx
        self.url = url.rstrip("/")
        self.openai = self.url.endswith("/v1")
        self.modello = modello
        self.cpu = cpu
        self.http = httpx.Client(timeout=httpx.Timeout(timeout_s, connect=3.0))
        self.qwen = "qwen3-embedding" in modello.lower()

    def vettori(self, testi: list[str], domanda: bool = False, keep_alive="30m"):
        import numpy as np
        if domanda and self.qwen:
            testi = [_ISTRUZIONE_QWEN + t for t in testi]
        if self.openai:
            r = self.http.post(self.url + "/embeddings",
                               json={"model": self.modello, "input": testi})
            r.raise_for_status()
            dati = sorted(r.json().get("data") or [], key=lambda d: d.get("index", 0))
            vv = [d["embedding"] for d in dati]
        else:
            body = {"model": self.modello, "input": testi, "keep_alive": keep_alive}
            if self.cpu:
                body["options"] = {"num_gpu": 0}
            r = self.http.post(self.url + "/api/embed", json=body)
            if r.status_code == 404:
                raise ModelloMancante(self.modello)
            r.raise_for_status()
            vv = r.json().get("embeddings") or []
        if len(vv) != len(testi):
            raise RuntimeError("il server non ha dato un vettore per testo")
        m = np.asarray(vv, dtype=np.float32)
        n = np.linalg.norm(m, axis=1, keepdims=True)
        n[n == 0] = 1.0
        return m / n

    def close(self):
        try:
            self.http.close()
        except Exception:  # noqa: BLE001
            pass


class ModelloMancante(RuntimeError):
    pass


# ─────────────────────────── l'archivio ───────────────────────────
class ArchivioConversazioni:
    def __init__(self, path, giorni: int = 30, embedder: Embedder | None = None, log=print,
                 avvia: bool = True, inattivita_s: float = 600.0, cfg=None):
        self.path = str(path)
        # Calliope inattiva (nessun turno archiviato né ricerca) da `inattivita_s`: solo allora
        # i vettori caricano il modello di embedding (06/10)
        self.inattivita_s = float(inattivita_s)
        self.ultima_attivita = time.monotonic()
        self.cfg = cfg
        self.vettori_rimandati = 0          # volte in cui i vettori hanno aspettato
        self.ricerche_per_parole = 0        # ricerche senza vettori: Ollama pieno
        self._ultimo_giro = 0.0
        self.giorni = int(giorni)
        self.embedder = embedder
        # Somiglianza minima (coseno) perché un turno entri nella ricerca per significato:
        # sotto, anche il turno più vicino non c'entra (tarata sul banco: SOGLIA_VETTORI)
        self.soglia_vettori = soglia_vettori(getattr(embedder, "modello", "") or "")
        self.log = log
        self.db = apri_db(self.path)
        # Le pagine liberate si azzerano (10/10, «dimentica» vera: anche la conversazione in
        # corso riscritta a ogni turno non lascia le versioni vecchie nel file)
        try:
            self.db.execute("PRAGMA secure_delete = ON")
        except sqlite3.Error:
            pass
        self.lock = threading.Lock()
        self.scrivibile = prepara_schema(self.db, MODULO, MIGRAZIONI, "conversazioni")
        # Stato dei vettori per il registro delle capacità: None (non ancora provato), True,
        # o il motivo per cui mancano
        self.stato_vettori: bool | str | None = None if embedder else "nessun modello"
        self.coda: queue.Queue = queue.Queue()
        self._fermo = threading.Event()
        self._thread = None
        self._ultima_pulizia = 0.0
        # Chi vuole sapere dei turni appena archiviati di una persona (08/10: la scheda
        # «Conversazione» degli schermi personali, hub.Schermi.chat_nuovi): funzioni
        # (persona, [voci di `voce_chat`]), dal thread dell'archivio, mai per gli ospiti. E di
        # una persona che ha cancellato le sue conversazioni (funzioni(persona))
        self.su_turni: list = []
        self.su_dimentica: list = []
        # Lavori in più della pulizia di ogni giorno (10/10: la rotazione del registro degli
        # eventi), dal thread dell'archivio
        self.su_pulizia: list = []
        # Il registro degli eventi su disco (calliope/eventi/registro.Disco), se c'è: «dimentica»
        # cancella anche lì
        self.eventi = None
        if avvia:
            self.avvia()

    # ── thread ──
    def avvia(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._ciclo, name="conversazioni",
                                            daemon=True)
            self._thread.start()

    def _ciclo(self):
        self._pulizia()
        while not self._fermo.is_set():
            try:
                lavoro = self.coda.get(timeout=1.0)
            except queue.Empty:
                if time.time() - self._ultima_pulizia > 86400:
                    self._pulizia()
                # Inattiva: i vettori rimasti indietro, ogni mezzo minuto
                if (self.embedder is not None and self.inattiva()
                        and time.monotonic() - self._ultimo_giro > 30):
                    self._ultimo_giro = time.monotonic()
                    try:
                        self._vettori_mancanti()
                    except Exception as e:  # noqa: BLE001
                        self.log(f"[CONVERSAZIONI] Vettori: {type(e).__name__}: {e}")
                continue
            if lavoro is None:
                break
            try:
                lavoro()
            except Exception as e:  # noqa: BLE001 — l'archivio non deve fermare la voce
                self.log(f"[CONVERSAZIONI] Errore: {type(e).__name__}: {e}")
            finally:
                self.coda.task_done()
            if self.coda.empty():
                self._vettori_mancanti()

    def attendi(self, timeout: float = 10.0) -> bool:
        """Aspetta che la coda sia vuota (prove, chiusura)."""
        fine = time.monotonic() + timeout
        while time.monotonic() < fine:
            if self.coda.unfinished_tasks == 0:
                return True
            time.sleep(0.02)
        return False

    def close(self):
        self.attendi(5.0)
        self._fermo.set()
        self.coda.put(None)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self.embedder is not None:
            self.embedder.close()
        with self.lock:
            try:
                self.db.close()
            except sqlite3.Error:
                pass

    # ── attività ──
    def segna_attivita(self):
        self.ultima_attivita = time.monotonic()

    def inattiva(self) -> bool:
        return time.monotonic() - self.ultima_attivita >= self.inattivita_s

    def _ollama(self):
        """(url, modello) se gli embedding sono su un Ollama (con il suo limite di modelli
        residenti); None per un server OpenAI o un embedder senza server (prove)."""
        emb = self.embedder
        url = getattr(emb, "url", None)
        if emb is None or not url or getattr(emb, "openai", False):
            return None
        return url, emb.modello

    def _in_coda(self, f):
        if self._thread is None:
            f()                        # senza thread (prove): subito
        else:
            self.coda.put(f)

    # ── scrittura (dal thread della voce, eseguita dal worker) ──
    def archivia(self, conv, turni: list[dict], persona, nome, ospite: bool):
        """Aggiunge i turni finiti di `conv` (calliope.conversazione.turni); apre la riga della
        conversazione la prima volta e ne scrive l'id in `conv.id_archivio`."""
        if not turni or not self.scrivibile:
            return
        self.segna_attivita()

        def f():
            nuovi = []
            with self.lock:
                if conv.id_archivio is None:
                    cur = self.db.execute(
                        "INSERT INTO conversazioni (persona, nome, ospite, luogo, inizio) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (persona, nome, int(bool(ospite)), conv.luogo, conv.inizio))
                    conv.id_archivio = cur.lastrowid
                from .conversazione import testo_turno
                for t in turni:
                    meta = t.get("meta") if isinstance(t.get("meta"), dict) else None
                    cur = self.db.execute(
                        "INSERT INTO turni (conv, quando, domanda, risposta, azioni, riservato, "
                        "meta) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (conv.id_archivio, t["quando"], t["domanda"], t["risposta"],
                         json.dumps(t["azioni"], ensure_ascii=False), int(t["riservato"]),
                         json.dumps(meta, ensure_ascii=False) if meta else None))
                    self.db.execute("INSERT INTO turni_fts (rowid, testo) VALUES (?, ?)",
                                    (cur.lastrowid, testo_turno(t)))
                    nuovi.append(voce_chat(cur.lastrowid, t["quando"], t["domanda"],
                                           t["risposta"], meta, conv.luogo, t["azioni"]))
                self.db.commit()
            # In diretta agli schermi personali della persona (mai gli ospiti), dopo il commit
            if persona and not ospite and self.su_turni:
                for g in list(self.su_turni):
                    try:
                        g(str(persona), [v for v in nuovi if v is not None])
                    except Exception as e:  # noqa: BLE001 — lo schermo non ferma l'archivio
                        self.log(f"[CONVERSAZIONI] schermi non avvisati: {type(e).__name__}")
        self._in_coda(f)

    # ── la scheda «Conversazione» (08/10) ──
    def chat(self, persona: str | None, n: int = 80) -> list[dict]:
        """Gli ultimi `n` turni di `persona` (mai degli ospiti), dal più vecchio, entro la
        tenuta dell'archivio: per la scheda «Conversazione» di un suo schermo personale."""
        if not persona or n <= 0:
            return []
        dal = time.time() - self.giorni * 86400 if self.giorni > 0 else 0.0
        with self.lock:
            righe = self.db.execute(
                "SELECT t.id, t.quando, t.domanda, t.risposta, t.meta, c.luogo, t.azioni "
                "FROM turni t JOIN conversazioni c ON c.id = t.conv WHERE c.persona = ? AND "
                "c.ospite = 0 AND t.quando >= ? ORDER BY t.id DESC LIMIT ?",
                (str(persona), dal, int(n))).fetchall()
        out = []
        for r in reversed(righe):
            try:
                meta = json.loads(r[4]) if r[4] else None
                azioni = json.loads(r[6] or "[]")
            except ValueError:
                meta, azioni = None, []
            v = voce_chat(r[0], r[1], r[2], r[3], meta, r[5], azioni)
            if v is not None:
                out.append(v)
        return out

    def chat_markdown(self, persona: str | None, n: int = 2000) -> str:
        """La trascrizione in Markdown («Scarica» della scheda), giorno per giorno."""
        return chat_markdown(self.chat(persona, n))

    def chiudi(self, conv, motivo: str, riassunto: dict | None = None):
        """La conversazione è finita: fine, motivo e (se c'è) il riassunto di chiusura."""
        if not self.scrivibile:
            return

        def f():
            if conv.id_archivio is None:
                return
            r = riassunto or {}
            with self.lock:
                self.db.execute(
                    "UPDATE conversazioni SET fine = ?, motivo = ?, riassunto = ?, "
                    "riassunto_dati = ?, ricordi_proposti = ? WHERE id = ?",
                    (time.time(), motivo, r.get("testo"),
                     json.dumps(r.get("dati"), ensure_ascii=False) if r.get("dati") else None,
                     json.dumps((r.get("dati") or {}).get("ricordi_proposti") or [],
                                ensure_ascii=False), conv.id_archivio))
                self.db.commit()
        self._in_coda(f)

    def salva_corrente(self, conv):
        """La conversazione in corso su disco (a ogni turno), nel thread dell'archivio."""
        if not self.scrivibile:
            return
        stato = json.dumps(conv.esporta(), ensure_ascii=False)

        def f():
            with self.lock:
                self.db.execute(
                    "INSERT INTO correnti (chiave, stato, aggiornata) VALUES (?, ?, ?) "
                    "ON CONFLICT(chiave) DO UPDATE SET stato = excluded.stato, "
                    "aggiornata = excluded.aggiornata", (conv.chiave, stato, time.time()))
                self.db.commit()
        self._in_coda(f)

    def chiavi_correnti(self) -> list[str]:
        """Le chiavi delle conversazioni in corso salvate (una per persona e per satellite
        dal 06/10): al riavvio si riprendono tutte quelle non scadute."""
        with self.lock:
            return [r[0] for r in self.db.execute("SELECT chiave FROM correnti")]

    def leggi_corrente(self, chiave: str = "casa") -> dict | None:
        with self.lock:
            row = self.db.execute("SELECT stato FROM correnti WHERE chiave = ?",
                                  (chiave,)).fetchone()
        try:
            return json.loads(row[0]) if row else None
        except ValueError:
            return None

    # ── vettori ──
    def _vettori_mancanti(self, lotto: int = 16):
        """Calcola i vettori dei turni che non li hanno (nel worker, a coda vuota). Su Ollama
        solo se il modello è già caricato o se Calliope è inattiva (allora a lotti più grandi),
        sempre con keep_alive 0: un modello in più non scaccia mai la voce o il guardiano."""
        emb = self.embedder
        if emb is None or not self.scrivibile:
            return
        from .conversazione import testo_turno
        o = self._ollama()
        extra = {}
        if o is not None:
            extra = {"keep_alive": 0}
            if self.inattiva():
                lotto = max(lotto, 64)
        while self.coda.empty() and not self._fermo.is_set():
            if o is not None and not self.inattiva():
                from . import ollama_carico as OC
                if not OC.residente(*o):
                    self.vettori_rimandati += 1
                    return
            with self.lock:
                righe = self.db.execute(
                    "SELECT id, domanda, risposta, azioni FROM turni WHERE vettore IS NULL "
                    "OR modello IS NOT ? ORDER BY id DESC LIMIT ?",
                    (emb.modello, lotto)).fetchall()
            if not righe:
                return
            testi = [testo_turno({"domanda": d, "risposta": r,
                                  "azioni": json.loads(a or "[]")})[:2000]
                     for _, d, r, a in righe]
            try:
                vv = emb.vettori(testi, **extra)
            except Exception as e:  # noqa: BLE001 — si riprova al prossimo turno
                motivo = ("modello non scaricato" if isinstance(e, ModelloMancante)
                          else f"server non raggiungibile ({type(e).__name__})")
                if self.stato_vettori != motivo:
                    self.log(f"[CONVERSAZIONI] Vettori non calcolati: {motivo}; resta la "
                             f"ricerca per parole")
                self.stato_vettori = motivo
                return
            self.stato_vettori = True
            with self.lock:
                for (i, *_), v in zip(righe, vv):
                    self.db.execute("UPDATE turni SET vettore = ?, modello = ? WHERE id = ?",
                                    (v.astype("float32").tobytes(), emb.modello, i))
                self.db.commit()

    # ── ricerca ──
    def cerca(self, domanda: str, persona: str | None, *, ospiti: bool = False,
              dal: float | None = None, al: float | None = None, k: int = 4,
              escludi_conv=None, solo: str | None = None) -> dict:
        """I turni passati più vicini alla domanda. `persona`: l'id del profilo (solo le sue
        conversazioni, mai degli ospiti); `ospiti=True` (solo chi amministra): le
        conversazioni degli ospiti. Restituisce {"risultati": […], "modo": "ibrida" |
        "parole"}."""
        dove, args = ["c.ospite = ?"], [1 if ospiti else 0]
        if not ospiti:
            if not persona:
                return {"risultati": [], "modo": "nessuno"}
            dove.append("c.persona = ?")
            args.append(str(persona))
        if dal is not None:
            dove.append("t.quando >= ?")
            args.append(dal)
        if al is not None:
            dove.append("t.quando < ?")
            args.append(al)
        if escludi_conv is not None:
            dove.append("t.conv IS NOT ?")
            args.append(escludi_conv)
        filtro = " AND ".join(dove)
        # Per parole
        parole = [w.lower() for w in _PAROLA.findall(domanda or "")
                  if w.lower() not in _VUOTE and len(w) > 1]
        rank_fts: list[int] = []
        if parole and solo != "vettori":
            q = " OR ".join(f'"{w[:-1] if len(w) > 4 else w}"*' for w in parole[:12])
            with self.lock:
                try:
                    rank_fts = [r[0] for r in self.db.execute(
                        f"SELECT t.id FROM turni_fts f JOIN turni t ON t.id = f.rowid "
                        f"JOIN conversazioni c ON c.id = t.conv WHERE turni_fts MATCH ? "
                        f"AND {filtro} ORDER BY bm25(turni_fts) LIMIT 30", [q, *args])]
                except sqlite3.OperationalError:
                    rank_fts = []
        # Per significato
        rank_vet: list[int] = []
        modo = "parole"
        self.segna_attivita()
        o = self._ollama()
        vettori_ok = True
        if o is not None and solo != "parole" and domanda.strip():
            # Durante una conversazione mai un modello in più su un Ollama pieno (06/10)
            from . import ollama_carico as OC
            vettori_ok = OC.puo_caricare(o[0], o[1], self.cfg)
            if not vettori_ok:
                self.ricerche_per_parole += 1
        if (self.embedder is not None and domanda.strip() and solo != "parole"
                and vettori_ok):
            try:
                import numpy as np
                qv = self.embedder.vettori([domanda], domanda=True,
                                           **({"keep_alive": "2m"} if o else {}))[0]
                with self.lock:
                    righe = self.db.execute(
                        f"SELECT t.id, t.vettore FROM turni t JOIN conversazioni c "
                        f"ON c.id = t.conv WHERE t.vettore IS NOT NULL AND t.modello = ? "
                        f"AND {filtro}", [self.embedder.modello, *args]).fetchall()
                if righe:
                    m = np.frombuffer(b"".join(r[1] for r in righe), dtype=np.float32)
                    m = m.reshape(len(righe), -1)
                    sim = m @ qv
                    ordine = np.argsort(-sim)[:30]
                    rank_vet = [righe[i][0] for i in ordine if sim[i] >= self.soglia_vettori]
                modo = "ibrida"
                self.stato_vettori = True
            except Exception as e:  # noqa: BLE001 — resta la ricerca per parole
                self.stato_vettori = ("modello non scaricato" if isinstance(e, ModelloMancante)
                                      else f"server non raggiungibile ({type(e).__name__})")
        # Fusione (RRF)
        punti: dict[int, float] = {}
        for elenco in (rank_fts, rank_vet):
            for pos, i in enumerate(elenco):
                punti[i] = punti.get(i, 0.0) + 1.0 / (RRF_K + pos + 1)
        scelti = sorted(punti, key=lambda i: -punti[i])[:k]
        out = []
        if scelti:
            with self.lock:
                righe = {r[0]: r for r in self.db.execute(
                    f"SELECT t.id, t.quando, t.domanda, t.risposta, t.azioni, c.riassunto, "
                    f"c.nome, t.conv FROM turni t JOIN conversazioni c ON c.id = t.conv "
                    f"WHERE t.id IN ({','.join('?' * len(scelti))})", scelti)}
            for i in scelti:
                r = righe.get(i)
                if r is None:
                    continue
                out.append({"id": i, "quando": r[1], "domanda": r[2] or "",
                            "risposta": r[3] or "", "azioni": json.loads(r[4] or "[]"),
                            "nome": r[6], "conv": r[7], "punti": round(punti[i], 4),
                            "parole": i in rank_fts, "significato": i in rank_vet})
        return {"risultati": out, "modo": modo}

    def recenti(self, persona: str | None, *, salta: int = 0, n: int = 3,
                dal: float | None = None, al: float | None = None,
                escludi_conv=None) -> dict:
        """Le conversazioni di `persona` dalla più recente (08/10, il modo cronologico di
        conversazione_cerca: «di cosa parlavamo prima?», «più indietro ancora»), saltando le
        prime `salta`: {"conversazioni": [{"id", "inizio", "fine", "luogo", "riassunto",
        "domande"}], "altre": quante ne restano dopo queste}. Ordine per l'ultimo turno; solo
        quelle con almeno un turno, mai degli ospiti. Senza riassunto (non ancora chiusa, o
        riassunto non fatto) le prime domande della persona."""
        if not persona:
            return {"conversazioni": [], "altre": 0}
        dove, args = ["c.persona = ?", "c.ospite = 0"], [str(persona)]
        if escludi_conv is not None:
            dove.append("c.id IS NOT ?")
            args.append(escludi_conv)
        avere = []
        if dal is not None:
            avere.append("MAX(t.quando) >= ?")
        if al is not None:
            avere.append("MIN(t.quando) < ?")
        args_avere = [x for x in (dal, al) if x is not None]
        sql = (f"SELECT c.id, MIN(t.quando), MAX(t.quando), c.luogo, c.riassunto "
               f"FROM conversazioni c JOIN turni t ON t.conv = c.id WHERE {' AND '.join(dove)} "
               f"GROUP BY c.id" + (f" HAVING {' AND '.join(avere)}" if avere else "")
               + " ORDER BY MAX(t.quando) DESC")
        with self.lock:
            righe = self.db.execute(sql, [*args, *args_avere]).fetchall()
            scelte = righe[max(0, int(salta)):max(0, int(salta)) + max(0, int(n))]
            out = []
            for cid, inizio, fine, luogo, riassunto in scelte:
                domande = [r[0] for r in self.db.execute(
                    "SELECT domanda FROM turni WHERE conv = ? AND COALESCE(domanda, '') != '' "
                    "ORDER BY id LIMIT 4", (cid,))]
                out.append({"id": cid, "inizio": inizio, "fine": fine, "luogo": luogo,
                            "riassunto": _riassunto_nudo(riassunto), "domande": domande})
        return {"conversazioni": out,
                "altre": max(0, len(righe) - max(0, int(salta)) - len(out))}

    def ultima(self, persona: str | None, luogo, entro_ore: float, ovunque: bool = False):
        """Il riassunto dell'ultima conversazione chiusa di `persona` nello stesso luogo (con
        `ovunque` in qualunque luogo: la conversazione segue la persona da un satellite
        all'altro, 06/10), se è finita entro `entro_ore` ore: (testo, fine) o None. Mai per
        gli ospiti."""
        if not persona or entro_ore <= 0:
            return None
        dove = "" if ovunque else "AND luogo IS ? "
        with self.lock:
            row = self.db.execute(
                "SELECT riassunto, fine FROM conversazioni WHERE persona = ? AND ospite = 0 "
                "AND fine IS NOT NULL AND riassunto IS NOT NULL " + dove
                + "ORDER BY fine DESC LIMIT 1",
                (str(persona),) if ovunque else (str(persona), luogo)).fetchone()
        if not row or time.time() - row[1] > entro_ore * 3600:
            return None
        return row[0], row[1]

    # ── cancellazione ──
    def dimentica(self, persona: str) -> int:
        """Cancella tutte le conversazioni di una persona. Restituisce quante.

        Dal 10/10 per davvero (§ 2.4 e § 10 del progetto del registro degli eventi): prima si
        aspettano i lavori in coda (un turno ancora da archiviare tornerebbe dopo la
        cancellazione), poi `secure_delete` (le pagine liberate si azzerano), l'indice FTS5
        ricompattato (le parole dei turni tolti non restano nei suoi segmenti), la conversazione
        in corso salvata (`correnti`), il registro degli eventi della persona, e il checkpoint del
        WAL (le versioni vecchie delle pagine non restano nel file accanto)."""
        from .eventi.registro import checkpoint
        self.attendi(3.0)
        with self.lock:
            ids = [r[0] for r in self.db.execute(
                "SELECT id FROM conversazioni WHERE persona = ? AND ospite = 0",
                (str(persona),))]
            prima = self.db.execute("PRAGMA secure_delete").fetchone()
            self.db.execute("PRAGMA secure_delete = ON")
            try:
                self._togli(ids)
                # I turni orfani: archiviati dopo una cancellazione di prima del 10/10 (la
                # conversazione in corso restava, e i suoi turni finivano su una riga tolta)
                orfani = [r[0] for r in self.db.execute(
                    "SELECT id FROM turni WHERE conv NOT IN (SELECT id FROM conversazioni)")]
                for t in orfani:
                    self.db.execute("DELETE FROM turni_fts WHERE rowid = ?", (t,))
                    self.db.execute("DELETE FROM turni WHERE id = ?", (t,))
                ids += [None] * bool(orfani)
                # La conversazione in corso salvata per il riavvio
                self.db.execute("DELETE FROM correnti WHERE chiave = ?",
                                (f"persona:{persona}",))
                if ids:
                    try:
                        self.db.execute("INSERT INTO turni_fts(turni_fts) VALUES('optimize')")
                    except sqlite3.Error:
                        pass
            finally:
                if prima is not None and not prima[0]:
                    self.db.execute("PRAGMA secure_delete = OFF")
            self.db.commit()
            ev = self.eventi
        if ev is not None:
            try:
                ev.dimentica(f"persona:{persona}")
            except Exception as e:  # noqa: BLE001
                self.log(f"[CONVERSAZIONI] registro degli eventi non cancellato: "
                         f"{type(e).__name__}")
        else:
            with self.lock:
                checkpoint(self.db)
        # Anche dalla scheda «Conversazione» dei suoi schermi personali (08/10)
        for g in list(self.su_dimentica):
            try:
                g(str(persona))
            except Exception as e:  # noqa: BLE001
                self.log(f"[CONVERSAZIONI] schermi non avvisati: {type(e).__name__}")
        return len([i for i in ids if i is not None])

    def pulisci_wal(self):
        """Dopo i lavori in coda, il WAL ricopiato nel file e troncato (10/10: dopo «dimentica»
        la conversazione in corso, salvata ancora una volta durante il turno, non resta nelle
        versioni vecchie delle pagine)."""
        from .eventi.registro import checkpoint

        def f():
            with self.lock:
                checkpoint(self.db)
        self._in_coda(f)

    def _togli(self, ids: list[int]):
        for cid in ids:
            turni = [r[0] for r in self.db.execute("SELECT id FROM turni WHERE conv = ?",
                                                   (cid,))]
            for t in turni:
                self.db.execute("DELETE FROM turni_fts WHERE rowid = ?", (t,))
            self.db.execute("DELETE FROM turni WHERE conv = ?", (cid,))
            self.db.execute("DELETE FROM conversazioni WHERE id = ?", (cid,))

    def _pulizia(self):
        self._ultima_pulizia = time.time()
        for f in list(self.su_pulizia):
            try:
                f()
            except Exception as e:  # noqa: BLE001
                self.log(f"[CONVERSAZIONI] pulizia: {type(e).__name__}: {e}")
        if not self.scrivibile or self.giorni <= 0:
            return
        limite = time.time() - self.giorni * 86400
        with self.lock:
            ids = [r[0] for r in self.db.execute(
                "SELECT id FROM conversazioni WHERE COALESCE(fine, inizio) < ?", (limite,))]
            if ids:
                self._togli(ids)
            self.db.execute("DELETE FROM correnti WHERE aggiornata < ?", (limite,))
            self.db.commit()
        if ids:
            self.log(f"[CONVERSAZIONI] Tolte {len(ids)} conversazioni più vecchie di "
                     f"{self.giorni} giorni")

    # ── terminale ──
    def elenco(self, ospiti: bool | None = None, limite: int = 50) -> list[dict]:
        dove = "" if ospiti is None else f"WHERE c.ospite = {1 if ospiti else 0}"
        with self.lock:
            righe = self.db.execute(
                f"SELECT c.id, c.nome, c.ospite, c.luogo, c.inizio, c.fine, c.motivo, "
                f"(SELECT COUNT(*) FROM turni t WHERE t.conv = c.id), c.riassunto "
                f"FROM conversazioni c {dove} ORDER BY c.inizio DESC LIMIT ?",
                (limite,)).fetchall()
        return [{"id": r[0], "nome": r[1], "ospite": bool(r[2]), "luogo": r[3],
                 "inizio": r[4], "fine": r[5], "motivo": r[6], "turni": r[7],
                 "riassunto": r[8]} for r in righe]

    def mostra(self, cid: int) -> dict | None:
        with self.lock:
            c = self.db.execute("SELECT id, nome, ospite, luogo, inizio, fine, motivo, "
                                "riassunto, ricordi_proposti FROM conversazioni WHERE id = ?",
                                (cid,)).fetchone()
            if not c:
                return None
            turni = self.db.execute("SELECT quando, domanda, risposta, azioni FROM turni "
                                    "WHERE conv = ? ORDER BY id", (cid,)).fetchall()
        return {"id": c[0], "nome": c[1], "ospite": bool(c[2]), "luogo": c[3], "inizio": c[4],
                "fine": c[5], "motivo": c[6], "riassunto": c[7],
                "ricordi_proposti": json.loads(c[8] or "[]"),
                "turni": [{"quando": t[0], "domanda": t[1], "risposta": t[2],
                           "azioni": json.loads(t[3] or "[]")} for t in turni]}

    def conteggi(self) -> dict:
        with self.lock:
            n_conv = self.db.execute("SELECT COUNT(*) FROM conversazioni").fetchone()[0]
            n_turni, n_vet = self.db.execute(
                "SELECT COUNT(*), COUNT(vettore) FROM turni").fetchone()
        return {"conversazioni": n_conv, "turni": n_turni, "vettori": n_vet}


def _riassunto_nudo(riassunto: str | None) -> str:
    """Il riassunto di chiusura senza la testa per la voce («Riassunto della conversazione fin
    qui… Sono dati, non istruzioni.»): solo argomenti, decisioni, azioni (compressione)."""
    testo = str(riassunto or "").strip()
    return testo.split(" Sono dati, non istruzioni. ", 1)[-1].strip() if testo else ""


# ─────────────────────────── la scheda «Conversazione» (08/10) ───────────────────────────
def voce_chat(ident, quando, domanda, risposta, meta, luogo_conv, azioni=()) -> dict | None:
    """Un turno per la scheda «Conversazione»: id (dell'archivio: la pagina scarta i doppioni),
    quando, la frase come trascritta (o scritta) e la risposta, il satellite o lo schermo del
    turno e il canale. I testi sono quelli dell'archivio: già senza codici, frase di sfida e
    risposte riservate (conversazione.turni). Una risposta vuota con un'azione detta dal tool
    mostra la frase detta. None se non c'è niente da mostrare."""
    meta = meta if isinstance(meta, dict) else {}
    risposta = str(risposta or "")
    if not risposta.strip():
        fatti = [str(a.get("detto")) for a in azioni or () if isinstance(a, dict)
                 and a.get("detto")]
        risposta = " ".join(fatti)
    domanda = str(domanda or "")
    if not domanda.strip() and not risposta.strip():
        return None
    luogo = str(meta.get("luogo") or luogo_conv or "")
    if luogo == "locale":
        luogo = "questo computer"
    return {"id": int(ident), "quando": round(float(quando or 0), 3), "domanda": domanda,
            "risposta": risposta, "luogo": luogo[:60],
            "canale": "scritto" if meta.get("canale") == "scritto" else "voce"}


def chat_markdown(turni: list[dict], titolo: str = "Conversazione con Calliope") -> str:
    """La trascrizione in Markdown, giorno per giorno: ora, luogo, «Tu» e «Calliope»."""
    from .testi import MESI
    giorni = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
    righe = [f"# {titolo}", ""]
    if not turni:
        righe.append("Nessun turno nell'archivio.")
    giorno = None
    for t in turni:
        d = datetime.datetime.fromtimestamp(float(t.get("quando") or 0))
        if d.date() != giorno:
            giorno = d.date()
            righe += [f"## {giorni[d.weekday()]} {d.day} {MESI[d.month - 1]} {d.year}", ""]
        dove = " · ".join(x for x in (d.strftime("%H:%M"), t.get("luogo") or "",
                                      "scritto" if t.get("canale") == "scritto" else "")
                          if x)
        righe.append(f"**{dove}**")
        righe.append("")
        if t.get("domanda"):
            righe += [f"**Tu:** {t['domanda']}", ""]
        if t.get("risposta"):
            righe += [f"**Calliope:** {t['risposta']}", ""]
    return "\n".join(righe).rstrip() + "\n"


# ─────────────────────────── avvio ───────────────────────────
def url_embedding(cfg) -> str:
    """Il server degli embedding: `conversazioni_embedding_url`, altrimenti l'Ollama della
    voce (con la voce su vLLM, l'Ollama locale)."""
    url = (getattr(cfg, "conversazioni_embedding_url", None) or "").strip()
    if url:
        return url.rstrip("/")
    if getattr(cfg, "llm_backend", "ollama") == "ollama":
        return (getattr(cfg, "llm_native_url", None) or "http://127.0.0.1:11434").rstrip("/")
    return "http://127.0.0.1:11434"


def load_conversazioni(cfg, log=print, avvia: bool = True) -> ArchivioConversazioni | None:
    """L'archivio, o None (spento o il file non si apre): Calliope parte uguale."""
    from . import capacita
    if not getattr(cfg, "conversazioni_enabled", True):
        capacita.segnala("conversazioni", "da_configurare", "archivio delle conversazioni spento",
                         "Accendilo con conversazioni_enabled: true in calliope.locale.yaml.")
        return None
    modello = (getattr(cfg, "conversazioni_embedding", None) or "").strip()
    emb = None
    if modello:
        try:
            emb = Embedder(url_embedding(cfg), modello,
                           cpu=bool(getattr(cfg, "conversazioni_embedding_cpu", True)))
        except Exception as e:  # noqa: BLE001
            log(f"[CONVERSAZIONI] Embedding non disponibili ({type(e).__name__}: {e})")
    try:
        arch = ArchivioConversazioni(percorso_db(cfg), int(getattr(cfg, "conversazioni_giorni",
                                                                   30)),
                                     emb, log=log, avvia=avvia,
                                     inattivita_s=float(getattr(
                                         cfg, "conversazioni_vettori_inattivita_s", 600.0)),
                                     cfg=cfg)
    except Exception as e:  # noqa: BLE001
        capacita.segnala("conversazioni", "guasta",
                         f"il database non si apre ({type(e).__name__})",
                         "Controlla conversazioni_db in calliope.locale.yaml.",
                         {"errore": str(e)})
        return None
    capacita.REGISTRO.dinamica("conversazioni", lambda: stato_capacita(cfg, arch))
    capacita.REGISTRO.da_dict(stato_capacita(cfg, arch))
    return arch


def stato_capacita(cfg, arch) -> dict:
    """La voce del registro delle capacità: attiva con la ricerca ibrida o solo per parole
    (calliope/capacita.check_conversazioni)."""
    from .capacita import check_conversazioni
    return check_conversazioni(cfg, arch)


def _ora(t) -> str:
    if not t:
        return "-"
    return datetime.datetime.fromtimestamp(t).strftime("%d/%m %H:%M")


def main(argv=None):
    import argparse
    from .config import load_config
    p = argparse.ArgumentParser(
        prog="python -m calliope.conversazioni",
        description="L'archivio delle conversazioni (solo per chi amministra la macchina).")
    p.add_argument("--elenco", action="store_true", help="le conversazioni, le più recenti prima")
    p.add_argument("--ospiti", action="store_true", help="solo quelle degli ospiti")
    p.add_argument("--mostra", type=int, metavar="ID", help="una conversazione per intero")
    p.add_argument("--cerca", metavar="TESTO", help="cerca tra quelle degli ospiti (--ospiti) "
                   "o di una persona (--persona ID)")
    p.add_argument("--persona", metavar="ID", help="id del profilo (speakers.json)")
    p.add_argument("--dimentica", metavar="ID", help="cancella le conversazioni di un profilo")
    a = p.parse_args(argv)
    cfg = load_config()
    arch = load_conversazioni(cfg, log=lambda s: None, avvia=False)
    if arch is None:
        print("Archivio delle conversazioni non disponibile.")
        return 1
    try:
        if a.mostra is not None:
            c = arch.mostra(a.mostra)
            if c is None:
                print("Nessuna conversazione con questo id.")
                return 1
            chi = "ospite" if c["ospite"] else (c["nome"] or "?")
            print(f"Conversazione {c['id']} · {chi} · {c['luogo'] or '-'} · "
                  f"{_ora(c['inizio'])} → {_ora(c['fine'])} ({c['motivo'] or 'aperta'})")
            if c["riassunto"]:
                print(f"Riassunto: {c['riassunto']}")
            if c["ricordi_proposti"]:
                print("Ricordi proposti (non salvati): " + "; ".join(c["ricordi_proposti"]))
            for t in c["turni"]:
                print(f"\n[{_ora(t['quando'])}] Tu: {t['domanda']}")
                for az in t["azioni"]:
                    print(f"   [{az.get('tool')}] {'ok' if az.get('ok') else 'non riuscito'}")
                print(f"Calliope: {t['risposta']}")
            return 0
        if a.dimentica:
            print(f"Cancellate {arch.dimentica(a.dimentica)} conversazioni.")
            return 0
        if a.cerca:
            r = arch.cerca(a.cerca, a.persona, ospiti=a.ospiti or not a.persona)
            print(f"Ricerca {r['modo']}:")
            for x in r["risultati"]:
                print(f"- [{_ora(x['quando'])}] {x['domanda']} → {x['risposta'][:120]}")
            return 0
        for c in arch.elenco(True if a.ospiti else None):
            chi = "ospite" if c["ospite"] else (c["nome"] or "?")
            print(f"{c['id']:5d}  {_ora(c['inizio'])} → {_ora(c['fine'])}  {chi:12s} "
                  f"{c['turni']:3d} turni  {(c['riassunto'] or '')[:70]}")
        print(arch.conteggi())
        return 0
    finally:
        arch.close()


if __name__ == "__main__":
    raise SystemExit(main())
