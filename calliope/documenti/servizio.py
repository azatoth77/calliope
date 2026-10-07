"""
Il servizio dei documenti: archivio dei JSON, lavori in secondo piano, frasi da dire.

- Archivio (`Archive`): il JSON di ogni documento sta in SQLite (lo stesso file della
  memoria, tabella `documenti`), non nella cartella Documenti: serve a modificarlo dopo,
  anche dopo un riavvio. Ogni modifica conserva la versione precedente del JSON
  (`documenti_versioni`); il file invece si riscrive con lo stesso nome (vedi consegna.py).
- Lavori (`Job`): uno alla volta, in un thread. Ollama serve una richiesta alla volta,
  quindi due generazioni insieme non sarebbero più veloci, e una modifica detta subito
  dopo la creazione deve aspettarla (legge l'ultimo documento quando parte, non quando
  viene chiesta). Il tool aspetta `documenti_attesa_s`: se il file è pronto lo dice
  subito, altrimenti il lavoro passa in secondo piano e, finito, finisce in `done` e
  chiama `on_done` (in main.py sveglia l'ascolto, come l'agenda con timer e promemoria).
- Il documento appena fatto si offre al PC come «ultima ricerca» della persona: «aprilo»
  diventa pc_apri_file(1), senza tool nuovi e senza percorsi dal modello.
"""

import json
import queue
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .consegna import LocalDelivery
from .formato import (ESTENSIONI, DocumentoNonValido, describe_change, is_letter,
                      safe_filename, summary, validate)
from .render import available_formats, render
from ..persistenza import apri_db, prepara_schema
from ..testi import NIENTE

_FIELDS = ("id", "owner", "owner_name", "formato", "titolo", "rif", "nome_file", "contenuto",
           "versione", "mtime", "richiesta", "creato", "modificato")


class Archive:
    def __init__(self, path: str):
        self._lock = threading.Lock()
        self.db = apri_db(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS documenti (
                               id INTEGER PRIMARY KEY,
                               owner TEXT NOT NULL,          -- UserProfile.id
                               owner_name TEXT,
                               formato TEXT NOT NULL,        -- word | excel | pdf
                               titolo TEXT NOT NULL,
                               rif TEXT,                     -- dove è stato consegnato (percorso)
                               nome_file TEXT,
                               contenuto TEXT NOT NULL,      -- il JSON validato
                               versione INTEGER NOT NULL DEFAULT 1,
                               mtime REAL,                   -- data del file dopo l'ultima scrittura
                               richiesta TEXT,
                               creato REAL NOT NULL,
                               modificato REAL NOT NULL)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS documenti_versioni (
                               documento INTEGER NOT NULL,
                               versione INTEGER NOT NULL,
                               contenuto TEXT NOT NULL,
                               rif TEXT,
                               creato REAL NOT NULL,
                               PRIMARY KEY (documento, versione))""")
        self.db.commit()
        # Versione dello schema (03/10, persistenza.prepara_schema): la 1 è quello qui sopra;
        # le prossime si aggiungono in fondo all'elenco, solo colonne con NULL o un
        # predefinito. Dati di una versione più nuova: sola lettura
        self.scrivibile = prepara_schema(self.db, "documenti", [lambda db: None])

    def add(self, owner, owner_name, formato, titolo, rif, nome_file, contenuto: dict,
            mtime, richiesta) -> int:
        now = time.time()
        with self._lock:
            cur = self.db.execute(
                "INSERT INTO documenti (owner, owner_name, formato, titolo, rif, nome_file, "
                "contenuto, mtime, richiesta, creato, modificato) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (owner, owner_name, formato, titolo, rif, nome_file,
                 json.dumps(contenuto, ensure_ascii=False), mtime, richiesta, now, now))
            self.db.commit()
        return cur.lastrowid

    def _one(self, where: str, args) -> dict | None:
        with self._lock:
            row = self.db.execute(f"SELECT {', '.join(_FIELDS)} FROM documenti WHERE {where}",
                                  args).fetchone()
        if not row:
            return None
        out = dict(zip(_FIELDS, row))
        out["contenuto"] = json.loads(out["contenuto"])
        return out

    def last(self, owner) -> dict | None:
        """L'ultimo documento creato o modificato da `owner`."""
        return self._one("owner = ? ORDER BY modificato DESC, id DESC LIMIT 1", (owner,))

    def get(self, doc_id: int) -> dict | None:
        return self._one("id = ?", (doc_id,))

    def update(self, doc_id: int, contenuto: dict, rif, nome_file, mtime):
        """Nuova versione: quella di prima resta in documenti_versioni."""
        with self._lock:
            old = self.db.execute("SELECT versione, contenuto, rif, modificato FROM documenti "
                                  "WHERE id = ?", (doc_id,)).fetchone()
            self.db.execute("INSERT OR REPLACE INTO documenti_versioni (documento, "
                            "versione, contenuto, rif, creato) VALUES (?,?,?,?,?)",
                            (doc_id, old[0], old[1], old[2], old[3]))
            self.db.execute("UPDATE documenti SET contenuto = ?, titolo = ?, rif = ?, "
                            "nome_file = ?, mtime = ?, versione = ?, modificato = ? WHERE id = ?",
                            (json.dumps(contenuto, ensure_ascii=False), contenuto["titolo"], rif,
                             nome_file, mtime, old[0] + 1, time.time(), doc_id))
            self.db.commit()

    def versions(self, doc_id: int) -> list[dict]:
        with self._lock:
            rows = self.db.execute("SELECT versione, contenuto FROM documenti_versioni "
                                   "WHERE documento = ? ORDER BY versione", (doc_id,)).fetchall()
        return [{"versione": v, "contenuto": json.loads(c)} for v, c in rows]


class Job:
    """Un lavoro (creazione o modifica): il tool lo aspetta un po', poi lo lascia andare."""

    def __init__(self, kind: str, owner: str, owner_name: str | None):
        self.kind, self.owner, self.owner_name = kind, owner, owner_name
        self.event = threading.Event()
        self.lock = threading.Lock()
        self.result: dict | None = None
        self.background = False


def in_sospeso(domanda: str, cosa: str) -> dict:
    """L'azione proposta con «Lo apro?»: il documento appena scritto è il risultato 1
    dell'«ultima ricerca» della persona (vedi Documenti._offer)."""
    return {"domanda": domanda, "cosa": cosa, "tool": "pc_apri_file",
            "argomenti": {"risultato": 1}}


# Come si chiama il documento a voce, e il genere per «la apro» / «lo apro»
_NOUNS = {"word": ("il documento", False), "excel": ("il foglio Excel", False),
          "pdf": ("il PDF", False)}


def noun(formato: str, lettera: bool) -> tuple[str, bool]:
    if lettera:
        return ("la lettera" if formato == "word" else "la lettera in PDF"), True
    return _NOUNS[formato]


def _scheda(doc: dict, formato: str, nome_file: str, modifica: str = "",
            ident=None) -> dict | None:
    """L'anteprima del documento per gli schermi (calliope/schermi/schede.py): personale,
    con l'identità del documento (una modifica aggiorna la stessa scheda)."""
    try:
        from ..schermi.schede import documento
        return documento(doc, formato, Path(nome_file).name, modifica, ident=ident)
    except Exception:  # noqa: BLE001 — l'anteprima non deve mai fermare il documento
        return None


class Documenti:
    def __init__(self, cfg, db_path: str, writer=None, delivery=None, formats=None,
                 on_done=None, pcs=None):
        self.cfg = cfg
        self.formati = tuple(formats) if formats is not None else available_formats()[0]
        self.archive = Archive(db_path)
        if writer is None:
            from .scrittore import Writer
            writer = Writer(cfg)
        self.writer = writer
        self.delivery = delivery or LocalDelivery(getattr(cfg, "documenti_cartella", None))
        self.fonts = getattr(cfg, "documenti_font", None)
        self.female = getattr(cfg, "gender", "f") == "f"
        self.done: queue.Queue = queue.Queue()    # annunci dei lavori finiti in secondo piano
        self.on_done = on_done
        self.pcs = pcs or {}
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="documenti")
        self._pending = 0
        self._pending_lock = threading.Lock()
        self.stats: list[dict] = []             # tempi di ogni lavoro (per le prove)

    # ── lavori ──
    def busy(self) -> bool:
        with self._pending_lock:
            return self._pending > 0

    def _submit(self, job: Job, fn, *args) -> Job:
        with self._pending_lock:
            self._pending += 1
        self._pool.submit(self._run, job, fn, *args)
        return job

    def _run(self, job: Job, fn, *args):
        try:
            result = fn(job, *args)
        except DocumentoNonValido as e:
            print(f"   [DOCUMENTI] JSON non valido anche al secondo tentativo: {e}", flush=True)
            result = self._failure("il modello non ha scritto un documento valido",
                                   "il testo che mi è uscito non era valido")
        except Exception as e:  # noqa: BLE001 — un errore diventa una frase, mai un crash
            print(f"   [DOCUMENTI] Errore: {type(e).__name__}: {e}", flush=True)
            result = self._failure(f"{type(e).__name__}: {e}", "c'è stato un problema")
        finally:
            with self._pending_lock:
                self._pending -= 1
        with job.lock:
            job.result = result
            job.event.set()
            background = job.background
        # Finito in secondo piano: l'anteprima va agli schermi adesso (calliope/schermi/).
        # Finito entro l'attesa, la scheda è nel risultato del tool e la manda Brain.
        on_card = getattr(job, "on_scheda", None)
        if background and on_card and result.get("scheda"):
            try:
                on_card(result["scheda"])
            except Exception as e:  # noqa: BLE001 — lo schermo non ferma l'annuncio
                print(f"   [DOCUMENTI] scheda non inviata: {e}", flush=True)
        if background:
            text = result.get("annuncio") or result.get("frase") or ""
            if text:
                who = f"{job.owner_name}, " if job.owner_name else ""
                self.done.put({"owner": job.owner, "owner_name": job.owner_name,
                               "messaggio": who + text[0].lower() + text[1:]
                               if who else text, "ok": result.get("ok"),
                               # «È pronta la lettera… La apro?»: l'azione proposta va
                               # ricordata anche per l'annuncio (Brain.record_announcement)
                               "in_sospeso": result.get("in_sospeso")})
                if self.on_done:
                    self.on_done()

    def wait(self, job: Job, timeout: float) -> dict | None:
        """Il risultato se arriva entro `timeout`, altrimenti None e il lavoro verrà
        annunciato a fine lavoro."""
        if job.event.wait(max(0.0, timeout)):
            return job.result
        with job.lock:
            if job.event.is_set():
                return job.result
            job.background = True
        return None

    def _failure(self, errore: str, detto: str) -> dict:
        riuscita = "riuscita" if self.female else "riuscito"
        return {"ok": False, "fatto": NIENTE, "errore": errore,
                "frase": f"Non sono {riuscita} a preparare il documento: {detto}. Riprova "
                         f"dicendolo in un altro modo.",
                "annuncio": f"Non sono {riuscita} a preparare il documento: {detto}."}

    # ── creare ──
    def crea(self, owner: str, owner_name: str | None, formato: str, richiesta: str,
             detto: str = "", titolo: str = "") -> Job:
        return self._submit(Job("crea", owner, owner_name), self._create, formato, richiesta,
                            detto, titolo)

    def _create(self, job: Job, formato, richiesta, detto, titolo) -> dict:
        t0 = time.perf_counter()
        doc = self.writer.write(formato, richiesta, detto, job.owner_name, titolo)
        gen_s = time.perf_counter() - t0
        data = render(formato, doc, self.fonts)
        ext = ESTENSIONI[formato]
        d = self.delivery.deliver(safe_filename(doc["titolo"]), ext, data)
        doc_id = self.archive.add(job.owner, job.owner_name, formato, doc["titolo"], d["rif"],
                                  d["nome_file"], doc, d.get("mtime"), richiesta or detto)
        can_open = self._offer(job.owner, d, doc["titolo"], ext)
        letter = is_letter(richiesta, detto, doc["titolo"]) and formato != "excel"
        name, fem = noun(formato, letter)
        what = summary(formato, doc, letter)
        where = d.get("dove") or self.delivery.where()
        ask = (" La apro?" if fem else " Lo apro?") if can_open else ""
        total_s = time.perf_counter() - t0
        self.stats.append({"lavoro": "crea", "formato": formato, "generazione_s": round(gen_s, 2),
                           "totale_s": round(total_s, 2), **getattr(self.writer, "last_stats", {})})
        pronto = "pronta" if fem else "pronto"
        return {"ok": True, "documento": doc_id, "formato": formato, "titolo": doc["titolo"],
                "nome_file": d["nome_file"], "contenuto": what, "secondi": round(total_s, 1),
                # Anteprima per gli schermi personali (Brain la toglie prima del modello)
                "scheda": _scheda(doc, formato, d["nome_file"], ident=doc_id),
                "frase": f"Ho preparato {name} «{doc['titolo']}»: {what}, {where}.{ask}",
                "annuncio": f"È {pronto} {name} «{doc['titolo']}»: {what}, {where}.{ask}",
                "cosa_fare": ("Non leggere il documento. Se chiede di aprirlo chiama "
                              "pc_apri_file con risultato 1; per cambiarlo documento_modifica."
                              if can_open else "Non leggere il documento. Per cambiarlo "
                                               "documento_modifica."),
                # La domanda «Lo apro?» diventa un'azione in sospeso per il turno dopo
                # (Brain): decide il modello se la risposta è un sì
                **({"in_sospeso": in_sospeso(ask.strip(), f"{name} «{doc['titolo']}»")}
                   if can_open else {})}

    def scrivi_fisso(self, owner: str, formato: str, doc: dict) -> dict:
        """Un documento con il testo già pronto nel codice (la guida per collegare la casa):
        niente LLM, stessa validazione, stesso file e stessa consegna. Non entra
        nell'archivio delle modifiche. {"ok", "nome_file", "dove", "apribile"}."""
        doc = validate(formato, doc)
        data = render(formato, doc, self.fonts)
        ext = ESTENSIONI[formato]
        d = self.delivery.deliver(safe_filename(doc["titolo"]), ext, data)
        return {"ok": True, "nome_file": d["nome_file"],
                "dove": d.get("dove") or self.delivery.where(),
                "apribile": self._offer(owner, d, doc["titolo"], ext)}

    def _offer(self, owner: str, delivered: dict, title: str, ext: str) -> bool:
        """Il file appena scritto diventa l'«ultima ricerca» della persona sul PC:
        «aprilo» → pc_apri_file(1). Con la consegna locale vale il percorso; con quella al
        satellite la maniglia che ha dato lui (`apri`). Un documento rimasto sul server
        (satellite assente) non si offre: lì non c'è nessuno schermo dove aprirlo."""
        percorso = delivered.get("apri") or (delivered.get("rif")
                                              if isinstance(self.delivery, LocalDelivery)
                                              else None)
        if not percorso or not self.pcs:
            return False
        ex = next(iter(self.pcs.values()))
        offer = getattr(ex, "offri_file", None)
        if offer is None:
            return False
        # Il nome vero del file (07/10): dopo una modifica salvata come «Titolo (2)» perché
        # l'originale era aperto, «Apro Titolo (2).» dice quale versione si apre
        nome = Path(str(delivered.get("nome_file") or "")).stem or title
        try:
            offer(owner, {"nome": nome, "estensione": ext, "percorso": percorso,
                          "modificato": time.strftime("%Y-%m-%dT%H:%M")})
            return True
        except Exception:  # noqa: BLE001 — aprire è un di più
            return False

    # ── modificare ──
    def modifica(self, owner: str, owner_name: str | None, modifica: str, detto: str = "") -> Job:
        return self._submit(Job("modifica", owner, owner_name), self._edit, modifica, detto)

    def _edit(self, job: Job, modifica, detto) -> dict:
        last = self.archive.last(job.owner)
        if last is None:
            return {"ok": False, "fatto": NIENTE,
                    "errore": "questa persona non ha ancora creato documenti",
                    "frase": "Non trovo un tuo documento da cambiare: prima dimmi cosa "
                             "preparare.",
                    "annuncio": "non ho trovato un tuo documento da cambiare."}
        formato, old = last["formato"], last["contenuto"]
        t0 = time.perf_counter()
        new = self.writer.edit(formato, old, modifica or detto, detto)
        gen_s = time.perf_counter() - t0
        change = describe_change(formato, old, new)
        title = new["titolo"]
        if not change:
            return {"ok": False, "fatto": "NIENTE: il documento NON è cambiato",
                    "errore": "la modifica non ha cambiato niente",
                    "frase": f"Non ho capito cosa cambiare in «{old['titolo']}»: puoi dirlo in "
                             f"un altro modo?",
                    "annuncio": f"non ho capito cosa cambiare in «{old['titolo']}»."}
        ext = ESTENSIONI[formato]
        data = render(formato, new, self.fonts)
        d = self.delivery.deliver(safe_filename(title), ext, data, replace=last["rif"],
                                  mtime=last["mtime"])
        self.archive.update(last["id"], new, d["rif"], d["nome_file"], d.get("mtime"))
        can_open = self._offer(job.owner, d, title, ext)
        note = ""
        copia = d.get("motivo") in ("aperto", "modificato")
        if d.get("motivo") == "aperto":
            note = (f" Il file era aperto, quindi ho salvato la nuova versione come "
                    f"«{Path(d['nome_file']).stem}».")
        elif d.get("motivo") == "modificato":
            note = (f" Il file era stato cambiato a mano, quindi ho salvato la nuova versione "
                    f"come «{Path(d['nome_file']).stem}».")
        total_s = time.perf_counter() - t0
        self.stats.append({"lavoro": "modifica", "formato": formato,
                           "generazione_s": round(gen_s, 2), "totale_s": round(total_s, 2),
                           **getattr(self.writer, "last_stats", {})})
        return {"ok": True, "documento": last["id"], "formato": formato, "titolo": title,
                "nome_file": d["nome_file"], "modifica": change, "secondi": round(total_s, 1),
                "scheda": _scheda(new, formato, d["nome_file"], change, ident=last["id"]),
                "frase": f"Fatto, ho aggiornato «{title}»: {change}.{note}",
                "annuncio": f"ho aggiornato «{title}»: {change}.{note}",
                # Il numero tra parentesi del nome nuovo non è il risultato (07/10, DGX: dopo
                # «salvato come “Titolo (2)”» il modello chiamava pc_apri_file(2))
                "cosa_fare": ("Non leggere il documento. Se chiede di aprirlo chiama "
                              "pc_apri_file con risultato 1"
                              + (f": è la versione nuova, «{Path(d['nome_file']).stem}» (il "
                                 f"numero tra parentesi nel nome non è il risultato)."
                                 if copia else ".") if can_open
                              else "Non leggere il documento.")}

    def close(self):
        self._pool.shutdown(wait=False, cancel_futures=True)
