"""
Il servizio delle installazioni: piano e prerequisiti, offerta in sospeso, lavoro in
secondo piano con avanzamento, annullo, annuncio e attivazione.

Regole (nel codice, non nel modello):
- si installa solo un'azione del catalogo (catalogo.py);
- `proponi` controlla i prerequisiti (libreria che funziona su questa macchina, spazio sul
  disco, file già presenti) e restituisce una proposta che finisce con una domanda; ricorda
  l'offerta per quella persona e quel turno;
- `avvia` parte solo se c'è un'offerta della stessa persona per la stessa azione, fatta nel
  turno precedente: mai nello stesso turno (il modello non può proporre e avviare da solo)
  e mai dopo un turno in mezzo. Se la persona dice sì lo decide il modello, con l'azione in
  sospeso davanti (brain.PENDING_MSG); che una proposta ci sia stata lo decide il codice;
- dopo la verifica di un file di Wikipedia ridotta o di Vikidia si costruisce il suo indice
  di ricerca (passo «indice», in un processo a parte con `python -m
  calliope.biblioteca_indice`); l'azione `biblioteca_indice` fa solo quel passo;
- un lavoro alla volta, in un thread; finito, va in `done` e chiama `on_done` (in main.py
  sveglia l'ascolto come un timer); `completa` lo attiva sul thread principale (la
  biblioteca si riapre e il tool compare) e restituisce la frase da annunciare.
La stessa `piano` + `esegui` serve al terminale (python -m calliope.stato --installa).
"""

import datetime
import os
import queue
import re
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import capacita as _cap
from ..conferme import proposta_valida
from .catalogo import (KIWIX_MAIN, KIWIX_MIRROR, MARCATORE, RICERCA, Azione, FileCat, Fonte,
                       candidati_indice, cartella_biblioteca, catalogo, file_fonte,
                       fonte_attiva, indici_superflui, serve_indice, versione_zim,
                       versioni_vecchie)
from .scarica import (Annullato, ErroreInstallazione, part_path, richiesta, scarica_file,
                      sha256_file)
from ..testi import MESI

# Sopra questa dimensione un file presente con la dimensione giusta si dà per integro senza
# rifare il checksum: 9 GB costerebbero ~20 s in un turno a voce
_HASH_MAX = 200_000_000
# Dimensione supposta di un modello di Ollama non ancora scaricato, per lo spazio sul disco
_LLM_STIMA = 10_000_000_000
# Indice di ricerca (calliope/biblioteca_indice.py), misurato il 01/10: indice ≈ 0,54–0,67 ×
# lo ZIM; durante la costruzione serve circa il doppio (VACUUM riscrive il file). Tempo:
# ~70 s per GB di ZIM con 12 processi, ~1,5 minuti per GB con 4 (mini: 3,6 minuti)
_INDICE_RAPPORTO = 0.65
_INDICE_S_PER_GB = {1: 300.0, 2: 160.0, 4: 90.0, 6: 75.0, 12: 70.0}


def _indice_secondi(byte: int, procs: int) -> float:
    k = max(p for p in _INDICE_S_PER_GB if p <= max(1, procs))
    return byte / 1e9 * _INDICE_S_PER_GB[k]


def parla_byte(n: int | float | None) -> str:
    """Una dimensione detta per esteso: «169 megabyte», «2,4 gigabyte»."""
    if not n:
        return "pochi byte"
    if n < 1e6:
        return "meno di un megabyte"
    if n < 1e9:
        return f"{round(n / 1e6)} megabyte"
    s = f"{n / 1e9:.1f}".replace(".", ",").replace(",0", "")
    return f"{s} gigabyte"


def parla_minuti(m: float) -> str:
    if m < 1.5:
        return "meno di due minuti"
    if m < 60:
        return f"circa {round(m)} minuti"
    h = m / 60
    return "circa un'ora" if h < 1.5 else f"circa {round(h)} ore"


def parla_versione(ver: str) -> str:
    try:
        y, mth = ver.split("-")
        return f"{MESI[int(mth) - 1]} {y}"
    except (ValueError, IndexError):
        return ver


@dataclass
class Piano:
    azione: Azione
    codice: str = "ok"         # ok | gia_fatto | libreria | spazio | rete | ollama_giu | ...
    frase: str = ""            # la proposta (finisce con «?») o perché non si fa
    files: list[FileCat] = field(default_factory=list)
    fonti: list[Fonte] = field(default_factory=list)    # fonti dei file da scaricare
    gia: list[str] = field(default_factory=list)        # titoli già presenti
    byte: int = 0              # da scaricare (al netto dei .part già scritti)
    libero: int | None = None
    minuti: float = 0.0
    eliminare: list[Path] = field(default_factory=list)  # pulizia
    indici: list[Path] = field(default_factory=list)     # file ZIM già presenti da indicizzare
    byte_indice: int = 0       # spazio per gli indici (picco durante la costruzione)
    minuti_indice: float = 0.0

    @property
    def ok(self) -> bool:
        return self.codice == "ok"


@dataclass
class Lavoro:
    azione: Azione
    piano: Piano
    chi: str | None
    chi_nome: str | None
    inizio: float = field(default_factory=time.time)
    cancel: threading.Event = field(default_factory=threading.Event)
    fase: str = "scarico"      # scarico | verifico | indice | fatto
    fatto: int = 0
    totale: int = 0
    thread: threading.Thread | None = None


class Installazioni:
    def __init__(self, cfg, http=None, on_done=None, origini: dict | None = None,
                 log=print):
        self.cfg = cfg
        self.origini = {"kiwix_mirror": KIWIX_MIRROR, "kiwix_main": KIWIX_MAIN,
                        **(origini or {})}
        self.catalogo = catalogo(cfg, origini)
        self._http = http
        self.on_done = on_done
        self.done: queue.Queue = queue.Queue()
        self._offerte: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.lavoro: Lavoro | None = None
        self.ultimo: dict | None = None
        self._log = log
        # capacità → funzione (sul thread principale) che la riattiva senza riavvio
        self.attivatori: dict = {}

    # ── rete ──
    @property
    def http(self):
        if self._http is None:
            import httpx
            self._http = httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))
        return self._http

    @property
    def velocita(self) -> float:
        return max(0.1, float(getattr(self.cfg, "installa_velocita_mb_s", 10.0))) * 1e6

    @property
    def margine(self) -> int:
        return int(float(getattr(self.cfg, "installa_margine_gb", 2.0)) * 1e9)

    @property
    def offerta_s(self) -> float:
        return float(getattr(self.cfg, "azione_in_sospeso_s", 180.0))

    def occupato(self) -> bool:
        return self.lavoro is not None and self.lavoro.thread is not None \
            and self.lavoro.thread.is_alive()

    # ── piano e prerequisiti ──
    def piano(self, azione_id: str) -> Piano:
        a = self.catalogo.get(azione_id)
        if a is None:
            return Piano(Azione(azione_id, azione_id, "?", "?"), "sconosciuta",
                         "Questa non è nel mio catalogo: posso installare solo biblioteca, "
                         "voci e modelli.")
        p = Piano(a)
        for lib in a.librerie:
            if _cap.importa(lib) is None:
                p.codice = "libreria"
                p.frase = self._frase_libreria(a, lib)
                return p
        try:
            if a.tipo == "file":
                self._piano_file(p)
            elif a.tipo == "kiwix":
                self._piano_kiwix(p)
            elif a.tipo == "aggiorna_zim":
                self._piano_aggiorna(p)
            elif a.tipo == "ollama":
                self._piano_ollama(p)
            elif a.tipo == "pulizia":
                self._piano_pulizia(p)
            elif a.tipo == "indice":
                self._piano_indice(p)
        except ErroreInstallazione as e:
            p.codice, p.frase = e.codice, e.frase
        return p

    def _frase_libreria(self, a: Azione, lib: str) -> str:
        what = {"voce": "Qui la voce non funzionerebbe",
                "chi_parla": "Qui il riconoscimento delle voci non funzionerebbe",
                "stt": "Qui la trascrizione su CPU non funzionerebbe"}.get(
            a.capacita, "Qui non funzionerebbe ancora")
        pkg = {"piper": "piper-tts", "onnxruntime": "onnxruntime",
               "faster_whisper": "faster-whisper"}.get(lib, lib)
        return (f"{what}: manca la libreria {pkg}. Non scarico niente; la libreria va "
                f"installata con pip install {pkg}.")

    def _presente(self, f: FileCat) -> bool:
        p = Path(f.dest)
        if not p.is_file() or (f.size is not None and p.stat().st_size != f.size):
            return False
        if f.sha256 and p.stat().st_size <= _HASH_MAX:
            return sha256_file(p).lower() == f.sha256.lower()
        return True

    def _spazio(self, p: Piano, folder: Path, need: int | None = None):
        """Calcola byte, spazio libero e minuti; codice «spazio» se non basta."""
        need = p.byte + p.byte_indice if need is None else need
        probe = Path(folder).resolve()
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        p.libero = shutil.disk_usage(probe).free
        p.minuti = p.byte / self.velocita / 60 + p.minuti_indice
        if p.libero < need + self.margine:
            p.codice = "spazio"
            p.frase = (f"Servirebbero {parla_byte(need)}, più un margine di "
                       f"{parla_byte(self.margine)}, ma sul disco ne restano "
                       f"{parla_byte(p.libero)}: prima va liberato spazio. Non scarico "
                       f"niente.")

    def _proposta(self, p: Piano, cosa: str, nota: str = ""):
        a = p.azione
        dopo = (" Dopo preparo l'indice per la ricerca, senza internet." if p.byte_indice
                else "")
        p.frase = (f"Scarico {cosa} {a.origine}: {parla_byte(p.byte)}, sul disco ci sono "
                   f"{parla_byte(p.libero)} liberi, ci vorranno {parla_minuti(p.minuti)} e "
                   f"serve internet solo per lo scaricamento.{dopo} {nota}".rstrip()
                   + " Procedo?")

    # ── indice di ricerca (calliope/biblioteca_indice.py) ──
    @property
    def processi_indice(self) -> int:
        return max(1, int(getattr(self.cfg, "biblioteca_indice_processi", 4) or 1))

    def _stima_indice(self, p: Piano, sizes: list[int]):
        """Spazio e tempo per gli indici dei file (già presenti o da scaricare)."""
        p.byte_indice = int(sum(sizes) * _INDICE_RAPPORTO * 2)
        p.minuti_indice = sum(_indice_secondi(s, self.processi_indice) for s in sizes) / 60

    def _proposta_indice(self, p: Piano, prima: str = ""):
        nomi = list(dict.fromkeys(_titolo_zim(q) for q in p.indici))
        cosa = nomi[0] if len(nomi) == 1 else ", ".join(nomi[:-1]) + " e " + nomi[-1]
        p.frase = (f"{prima}Preparo l'indice di ricerca per {cosa}, su questo computer e "
                   f"senza internet: ci vorranno {parla_minuti(p.minuti)} e servono "
                   f"{parla_byte(p.byte_indice)} sul disco, che ne ha {parla_byte(p.libero)} "
                   f"liberi. Intanto la biblioteca resta in uso. Procedo?")

    def _piano_indice(self, p: Piano, prima: str = ""):
        p.indici = candidati_indice(self.cfg, p.azione.fonti)
        if not p.indici:
            p.codice = "gia_fatto"
            p.frase = ("L'indice di ricerca della biblioteca è già pronto: non c'è niente da "
                       "fare." if file_fonte(self.cfg, RICERCA[0]) or file_fonte(
                           self.cfg, RICERCA[2]) else
                       "Non c'è niente da indicizzare: la biblioteca non è ancora scaricata. "
                       "Dimmi «scarica la biblioteca».")
            return
        self._stima_indice(p, [q.stat().st_size for q in p.indici])
        self._spazio(p, cartella_biblioteca(self.cfg))
        if p.ok:
            self._proposta_indice(p, prima)

    def _piano_file(self, p: Piano):
        a = p.azione
        todo = [f for f in a.files if not self._presente(f)]
        if not todo:
            p.codice = "gia_fatto"
            p.frase = (f"{a.titolo[0].upper()}{a.titolo[1:]} c'è già ed è integra: non c'è "
                       f"niente da fare." if a.capacita == "voce" else
                       f"{a.titolo[0].upper()}{a.titolo[1:]} c'è già ed è integro: non c'è "
                       f"niente da fare.")
            return
        p.files = todo
        p.byte = sum(max(0, (f.size or 0) - _part_size(f)) for f in todo)
        self._spazio(p, Path(todo[0].dest).parent)
        if p.ok:
            nota = "Dopo servirà un riavvio." if a.attivazione == "riavvio" else ""
            self._proposta(p, a.titolo, nota)

    # Kiwix: indice della cartella, .sha256 ufficiale, dimensione sul mirror
    def _ultima(self, fonte: Fonte, cache: dict) -> str | None:
        hosts = self.catalogo["biblioteca"].hosts
        if fonte.cartella not in cache:
            try:
                r = richiesta(self.http, "GET", f"{self.origini['kiwix_main']}/{fonte.cartella}/",
                              hosts)
            except ErroreInstallazione:
                raise
            except Exception as e:  # noqa: BLE001 — rete
                raise ErroreInstallazione("rete", "Non riesco a raggiungere il sito di Kiwix: "
                                          "controlla la connessione e riprova.") from e
            if r.status_code != 200:
                raise ErroreInstallazione("rete", f"Il sito di Kiwix ha risposto con l'errore "
                                          f"{r.status_code}: riprova più tardi.")
            cache[fonte.cartella] = r.text
        vers = re.findall(r'href="' + re.escape(fonte.prefisso) + r'_(\d{4}-\d{2})\.zim"',
                          cache[fonte.cartella])
        return max(vers) if vers else None

    def _file_kiwix(self, fonte: Fonte, ver: str) -> FileCat:
        hosts = self.catalogo["biblioteca"].hosts
        name = f"{fonte.prefisso}_{ver}.zim"
        try:
            r = richiesta(self.http, "GET",
                          f"{self.origini['kiwix_main']}/{fonte.cartella}/{name}.sha256", hosts)
            sha = re.match(r"\s*([0-9a-fA-F]{64})\b", r.text or "") if r.status_code == 200 \
                else None
            url = f"{self.origini['kiwix_mirror']}/{fonte.cartella}/{name}"
            h = richiesta(self.http, "HEAD", url, hosts)
            size = int(h.headers.get("content-length") or 0) if h.status_code == 200 else 0
        except ErroreInstallazione:
            raise
        except Exception as e:  # noqa: BLE001
            raise ErroreInstallazione("rete", "Non riesco a raggiungere il sito di Kiwix: "
                                      "controlla la connessione e riprova.") from e
        if not sha:
            raise ErroreInstallazione("checksum_assente", f"Sul sito di Kiwix non trovo il "
                                      f"checksum di {fonte.titolo}: senza non scarico.")
        if not size:
            raise ErroreInstallazione("dimensione", f"Il mirror non mi dice quanto pesa "
                                      f"{fonte.titolo}: riprova più tardi.")
        dest = cartella_biblioteca(self.cfg) / name
        return FileCat(url, str(dest), size, sha.group(1).lower())

    def _piano_kiwix(self, p: Piano):
        a = p.azione
        todo = []
        for fonte in a.fonti:
            have = file_fonte(self.cfg, fonte)
            if have is not None:
                v = versione_zim(str(have))
                p.gia.append(fonte.titolo + (f" (versione di {parla_versione(v[1])})" if v
                                             else ""))
            else:
                todo.append(fonte)
        if not todo:
            what = a.titolo if len(a.fonti) > 1 else p.gia[0]
            if candidati_indice(self.cfg, a.fonti):
                # I file ci sono ma l'indice no (costruzione interrotta, versione vecchia):
                # «scarica la biblioteca» porta comunque al passo che manca
                self._piano_indice(p, prima=f"{_cap1(what)} c'è già, ma senza l'indice la "
                                            f"ricerca è ridotta. ")
                return
            p.codice = "gia_fatto"
            p.frase = (f"{_cap1(what)}: c'è già. Per una versione più nuova chiedimi di "
                       f"aggiornare la biblioteca.")
            return
        cache: dict = {}
        for fonte in todo:
            ver = self._ultima(fonte, cache)
            if ver is None:
                raise ErroreInstallazione("non_trovata", f"Sul sito di Kiwix non trovo "
                                          f"{fonte.titolo}.")
            p.files.append(self._file_kiwix(fonte, ver))
            p.fonti.append(fonte)
        p.byte = sum(max(0, f.size - _part_size(f)) for f in p.files)
        self._stima_indice(p, [f.size for f in p.files if serve_indice(f.dest)])
        self._spazio(p, cartella_biblioteca(self.cfg))
        if p.ok:
            cosa = (" e ".join(f.titolo for f in p.fonti) if len(p.fonti) <= 2
                    else ", ".join(f.titolo.split(",")[0] for f in p.fonti[:-1]) + " e "
                    + p.fonti[-1].titolo.split(",")[0])
            notes = [f.nota for f in p.fonti if f.nota]
            extra = [f for f in p.fonti if not f.attr]
            if any(not f.richiesta for f in extra):
                notes.append("Le fonti in più per ora le conservo soltanto: le userò nelle "
                             "ricerche quando sarà pronta l'integrazione.")
            elif any(not fonte_attiva(self.cfg, f) for f in extra):
                notes.append("Per usarla nelle ricerche va accesa in biblioteca_fonti_extra, "
                             "in calliope.locale.yaml.")
            self._proposta(p, cosa, " ".join(notes))

    def _piano_aggiorna(self, p: Piano):
        cache: dict = {}
        installed = [(f, file_fonte(self.cfg, f)) for f in p.azione.fonti]
        installed = [(f, h) for f, h in installed if h is not None]
        if not installed:
            p.codice = "gia_fatto"
            p.frase = "Non c'è niente da aggiornare: la biblioteca non è ancora scaricata."
            return
        for fonte, have in installed:
            cur = versione_zim(str(have))
            ver = self._ultima(fonte, cache)
            if ver and cur and ver > cur[1]:
                # Già scaricata e verificata, in attesa del suo indice: niente download
                ready = cartella_biblioteca(self.cfg) / f"{fonte.prefisso}_{ver}.zim"
                if ready.is_file() and Path(str(ready) + MARCATORE).is_file():
                    if fonte.indice:
                        p.indici.append(ready)
                    continue
                p.files.append(self._file_kiwix(fonte, ver))
                p.fonti.append(fonte)
        if not p.files and p.indici:
            self._piano_indice(p, prima="Le versioni nuove sono già scaricate, ma entrano in "
                                        "uso solo con il loro indice. ")
            return
        if not p.files:
            p.codice = "gia_fatto"
            p.frase = "La biblioteca è già all'ultima versione: non c'è niente da aggiornare."
            return
        p.byte = sum(max(0, f.size - _part_size(f)) for f in p.files)
        self._stima_indice(p, [f.size for f in p.files if serve_indice(f.dest)]
                           + [q.stat().st_size for q in p.indici])
        self._spazio(p, cartella_biblioteca(self.cfg))
        if p.ok:
            nomi = [f"{fo.titolo.split(',')[0]} di {parla_versione(versione_zim(fi.dest)[1])}"
                    for fo, fi in zip(p.fonti, p.files)]
            self._proposta(p, "le versioni nuove: " + ", ".join(nomi),
                           "Le versioni nuove entrano in uso quando sono pronte; i file "
                           "vecchi restano finché non mi chiedi di pulirli.")

    def _ollama_modelli(self) -> list[dict]:
        url = self.cfg.llm_native_url.rstrip("/") + "/api/tags"
        try:
            r = self.http.get(url, timeout=3.0)
            r.raise_for_status()
            return r.json().get("models", [])
        except Exception as e:  # noqa: BLE001
            raise ErroreInstallazione("ollama_giu", "Ollama non risponde: va avviato prima "
                                      "di scaricare il modello.") from e

    def _piano_ollama(self, p: Piano):
        model = self.cfg.llm_model
        models = self._ollama_modelli()
        have = next((m for m in models if m.get("name") in (model, f"{model}:latest")), None)
        folder = Path(os.environ.get("OLLAMA_MODELS") or Path.home() / ".ollama" / "models")
        p.byte = int(have.get("size") or 0) if have else _LLM_STIMA
        self._spazio(p, folder, need=0 if have else _LLM_STIMA)
        if not p.ok:
            return
        if have:
            p.frase = (f"Il modello {model} c'è già e pesa {parla_byte(have.get('size'))}: "
                       f"se vuoi controllo se ce n'è una versione più nuova e nel caso la "
                       f"scarico dal registro di Ollama. Serve internet. Procedo?")
        else:
            p.frase = (f"Scarico il modello {model} dal registro di Ollama: non so quanto pesa "
                       f"prima di cominciare, di solito qualche gigabyte; sul disco ci sono "
                       f"{parla_byte(p.libero)} liberi. Serve internet. Procedo?")

    def _piano_pulizia(self, p: Piano):
        # File ZIM superati e indici che non servono più (dei file superati o cancellati,
        # costruzioni interrotte)
        old = versioni_vecchie(self.cfg)
        old += [q for q in indici_superflui(self.cfg) if q not in old]
        if self.occupato() and self.lavoro.fase == "indice":
            old = [q for q in old if not q.name.endswith(".tmp")]
        if not old:
            p.codice = "gia_fatto"
            p.frase = "Non ci sono file vecchi della biblioteca da cancellare."
            return
        p.eliminare = old
        freed = sum(q.stat().st_size for q in old if q.exists())
        p.frase = (f"Posso cancellare {len(old)} file vecchi della biblioteca, già sostituiti da "
                   f"versioni nuove e verificate: si liberano {parla_byte(freed)}. Li "
                   f"cancello?" if len(old) > 1 else
                   f"Posso cancellare un file vecchio della biblioteca, già sostituito da una "
                   f"versione nuova e verificata: si liberano {parla_byte(freed)}. Lo cancello?")

    # ── offerta e avvio ──
    def proponi(self, azione_id: str, persona: str, turno: int) -> dict:
        if self.occupato():
            job = self.lavoro
            if job.azione.id == azione_id:
                return {"ok": False, "codice": "in_corso",
                        "frase": f"Sto già scaricando {job.azione.titolo}. " + self.stato()["frase"]}
            return {"ok": False, "codice": "occupato",
                    "frase": f"Sto già scaricando {job.azione.titolo}: una cosa alla volta. "
                             f"Aspetta che finisca, oppure chiedimi di annullarlo."}
        p = self.piano(azione_id)
        if not p.ok:
            self._offerte.pop(persona, None)
            return {"ok": False, "codice": p.codice, "frase": p.frase}
        self._offerte[persona] = {"azione": azione_id, "turno": turno, "piano": p,
                                  "scade": time.monotonic() + self.offerta_s}
        return {"ok": True, "codice": "proposta", "frase": p.frase, "piano": p}

    def offerta(self, persona: str) -> dict | None:
        return self._offerte.get(persona)

    def avvia(self, azione_id: str, persona: str, turno: int,
              chi_nome: str | None = None) -> dict:
        # Valida nei turni dopo la proposta della stessa persona, non solo in quello subito
        # dopo (04/10, calliope/conferme.py); si consuma solo quando si avvia
        off = self._offerte.get(persona)
        if off is not None and time.monotonic() > off["scade"]:
            self._offerte.pop(persona, None)
            off = None
        if (off is None or off["azione"] != azione_id
                or not proposta_valida(self.cfg, off["turno"], turno)):
            return {"ok": False, "codice": "senza_offerta",
                    "frase": "Prima devo dirti cosa scarico, quanto pesa e quanto ci vuole, e "
                             "avere il tuo sì: chiedimelo di nuovo."}
        self._offerte.pop(persona, None)
        if self.occupato():
            return {"ok": False, "codice": "occupato",
                    "frase": f"Sto già scaricando {self.lavoro.azione.titolo}: una cosa alla "
                             f"volta."}
        p = off["piano"]
        # Lo spazio può essere cambiato dalla proposta
        if p.azione.tipo in ("file", "kiwix", "aggiorna_zim", "indice"):
            folder = Path(p.files[0].dest).parent if p.files else cartella_biblioteca(self.cfg)
            self._spazio(p, folder)
            if not p.ok:
                return {"ok": False, "codice": p.codice, "frase": p.frase}
        if p.azione.tipo == "pulizia":
            res = self.esegui(p)
            self._registra_fine(p.azione, res, persona, chi_nome, time.time())
            return {"ok": res["esito"] == "ok", "codice": res["esito"], "frase": res["frase"],
                    "sincrono": True}
        job = Lavoro(p.azione, p, persona, chi_nome, totale=p.byte,
                     fase="scarico" if p.files or p.azione.tipo in ("ollama", "file")
                     else "indice")
        job.thread = threading.Thread(target=self._run, args=(job,), daemon=True,
                                      name="installa")
        self.lavoro = job
        job.thread.start()
        when = "" if p.azione.tipo == "ollama" else f": ci vorranno {parla_minuti(p.minuti)}"
        what = (f"a scaricare {p.azione.titolo}" if p.files or p.azione.tipo == "ollama"
                or p.azione.tipo == "file" else "a preparare l'indice di ricerca della "
                                                  "biblioteca")
        return {"ok": True, "codice": "avviato",
                "frase": f"Ho cominciato {what}{when}. Ti avviso quando ha finito; puoi "
                         f"chiedermi a che punto è, o di annullarlo."}

    # ── esecuzione (thread o terminale) ──
    def esegui(self, p: Piano, cancel: threading.Event | None = None, avanz=None) -> dict:
        """Esegue il piano e restituisce {esito, frase, byte, attiva}. Non solleva."""
        a = p.azione
        cancel = cancel or threading.Event()
        try:
            if a.tipo in ("file", "kiwix", "aggiorna_zim"):
                done_before = 0
                for f in p.files:
                    base = done_before

                    def prog(n, base=base):
                        if avanz:
                            avanz("scarico", base + n)

                    def ver(n):
                        if avanz:
                            avanz("verifico", n)
                    sha = scarica_file(self.http, f, a.hosts, cancel, prog, ver)
                    if a.tipo != "file":
                        Path(f.dest + MARCATORE).write_text(
                            f"{sha}  {Path(f.dest).name}\n{datetime.datetime.now().isoformat()}"
                            f"\n", encoding="utf-8")
                    done_before += f.size or 0
                # Passo «indice», dopo la verifica: un file nuovo di Wikipedia ridotta o
                # Vikidia entra in uso (risolvi_zim) solo con il suo indice completo
                todo = [Path(f.dest) for f in p.files if serve_indice(f.dest)]
                self._indici(todo + [q for q in p.indici if q not in todo], cancel, avanz)
                return {"esito": "ok", "frase": "", "byte": p.byte,
                        "attiva": self._attivazione(p)}
            if a.tipo == "indice":
                self._indici(p.indici, cancel, avanz)
                return {"esito": "ok", "frase": "", "byte": 0, "attiva": "subito"}
            if a.tipo == "ollama":
                self._pull(cancel, avanz)
                return {"esito": "ok", "frase": "", "byte": 0, "attiva": "subito"}
            if a.tipo == "pulizia":
                freed, busy = 0, []
                from ..biblioteca_indice import percorso_indice
                for q in p.eliminare:
                    try:
                        size = q.stat().st_size
                        q.unlink()
                        freed += size
                        if q.suffix == ".zim":
                            for side in (MARCATORE, ".sha256"):
                                Path(str(q) + side).unlink(missing_ok=True)
                            idx = percorso_indice(q)      # l'indice va via con il suo file
                            if idx.exists() and idx not in p.eliminare:
                                freed += idx.stat().st_size
                                idx.unlink()
                    except PermissionError:
                        busy.append(q.name)
                    except FileNotFoundError:
                        pass
                if busy:
                    return {"esito": "errore", "frase": "Alcuni file sono ancora in uso: "
                            "riavviami e poi chiedimi di nuovo la pulizia.", "byte": freed}
                return {"esito": "ok", "frase": f"Fatto: ho cancellato i file vecchi della "
                        f"biblioteca e liberato {parla_byte(freed)}.", "byte": freed,
                        "attiva": "nessuna"}
        except Annullato:
            return {"esito": "annullato", "frase": "Download annullato.", "byte": 0}
        except ErroreInstallazione as e:
            return {"esito": "errore", "frase": e.frase, "codice": e.codice, "byte": 0}
        except Exception as e:  # noqa: BLE001 — rete, disco
            return {"esito": "errore", "frase": "Si è interrotto per un problema di rete o del "
                    "disco: se me lo richiedi riparto da dove ero arrivata.",
                    "codice": type(e).__name__, "byte": 0}
        return {"esito": "errore", "frase": "Azione sconosciuta.", "byte": 0}

    def _attivazione(self, p: Piano) -> str:
        a = p.azione
        if a.tipo in ("kiwix", "aggiorna_zim"):
            return ("subito" if any(f.attr or fonte_attiva(self.cfg, f) for f in p.fonti)
                    or p.indici else "nessuna")
        return a.attivazione

    def _indici(self, files: list[Path], cancel: threading.Event, avanz=None):
        """Costruisce gli indici in un processo a parte (`python -m
        calliope.biblioteca_indice`): la RAM della costruzione (~2 GB sul mini) non resta a
        Calliope, la priorità è bassa e un annullo lo ferma pulito. Solleva Annullato o
        ErroreInstallazione."""
        from ..biblioteca_indice import pronto
        for q in files:
            if pronto(q):
                continue

            def prog(n, tot, q=q):
                if avanz:
                    avanz("indice", n, tot)
            self._indice_processo(Path(q), cancel, prog)
            if not pronto(q):
                raise ErroreInstallazione("indice", f"L'indice di {_titolo_zim(q)} non è "
                                          f"venuto bene: chiedimi di nuovo di prepararlo.")

    def _indice_processo(self, zim: Path, cancel: threading.Event, prog):
        import subprocess
        import sys
        root = Path(__file__).resolve().parents[2]
        env = dict(os.environ, PYTHONUTF8="1",
                   PYTHONPATH=os.pathsep.join([str(root)] + ([os.environ["PYTHONPATH"]]
                                                             if os.environ.get("PYTHONPATH")
                                                             else [])))
        flags = 0
        if os.name == "nt":       # priorità bassa (la ereditano i processi figli), niente finestra
            flags = subprocess.BELOW_NORMAL_PRIORITY_CLASS | subprocess.CREATE_NO_WINDOW
        cmd = [sys.executable, "-m", "calliope.biblioteca_indice", str(zim.resolve()),
               "--avanzamento", "--stdin", "--processi", str(self.processi_indice)]
        extra = {} if os.name == "nt" else {"preexec_fn": _nice}   # Linux: nice 10
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                errors="replace", env=env, creationflags=flags, **extra)
        lines: queue.Queue = queue.Queue()

        def pump():
            for line in proc.stdout:
                lines.put(line)
            lines.put(None)
        threading.Thread(target=pump, daemon=True, name="indice-out").start()
        tail: list[str] = []
        try:
            while True:
                try:
                    line = lines.get(timeout=0.2)
                except queue.Empty:
                    if cancel.is_set():
                        raise Annullato()
                    continue
                if line is None:
                    break
                line = line.strip()
                if line.startswith("AVANZAMENTO "):
                    try:
                        n, tot = (int(x) for x in line.split()[1:3])
                        prog(n, tot)
                    except ValueError:
                        pass
                elif line:
                    tail = (tail + [line])[-5:]
                if cancel.is_set():
                    raise Annullato()
            rc = proc.wait()
        except Annullato:
            # Il processo si ferma da solo quando gli si chiude lo stdin, e cancella il
            # file a metà; se non risponde (VACUUM in corso) si chiude a forza
            try:
                proc.stdin.close()
                proc.wait(timeout=60)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()
            raise
        finally:
            if proc.poll() is None:
                proc.kill()
        if rc != 0:
            self._log(f"[INSTALLA] indice di {zim.name} non riuscito: {' | '.join(tail)}")
            raise ErroreInstallazione("indice", f"Ho i file, ma non sono riuscita a preparare "
                                      f"l'indice di ricerca di {_titolo_zim(zim)}. Chiedimi di "
                                      f"preparare l'indice della biblioteca per riprovare.")

    def _pull(self, cancel, avanz):
        import json
        url = self.cfg.llm_native_url.rstrip("/") + "/api/pull"
        totals: dict = {}
        with self.http.stream("POST", url, json={"model": self.cfg.llm_model, "stream": True},
                              timeout=None) as r:
            if r.status_code >= 400:
                r.read()
                raise ErroreInstallazione("ollama", f"Ollama ha risposto con l'errore "
                                          f"{r.status_code}.")
            for line in r.iter_lines():
                if cancel.is_set():
                    raise Annullato()
                if not line.strip():
                    continue
                obj = json.loads(line)
                if obj.get("error"):
                    raise ErroreInstallazione("ollama", f"Ollama non è riuscito a scaricare il "
                                              f"modello: {obj['error']}.")
                if obj.get("digest") and obj.get("total"):
                    totals[obj["digest"]] = (obj.get("completed") or 0, obj["total"])
                    if avanz:
                        avanz("scarico", sum(c for c, _ in totals.values()),
                              sum(t for _, t in totals.values()))
                if obj.get("status") == "success":
                    return
        raise ErroreInstallazione("ollama", "Ollama ha chiuso lo scaricamento senza finire.")

    def _run(self, job: Lavoro):
        def avanz(fase, n, totale=None):
            job.fase, job.fatto = fase, n
            if totale:
                job.totale = totale
        res = self.esegui(job.piano, job.cancel, avanz)
        job.fase = "fatto"
        self._registra_fine(job.azione, res, job.chi, job.chi_nome, job.inizio)

    def _registra_fine(self, a: Azione, res: dict, chi, chi_nome, inizio: float):
        item = {"azione": a.id, "titolo": a.titolo, "capacita": a.capacita,
                "esito": res["esito"], "frase": res.get("frase", ""),
                "codice": res.get("codice"), "byte": res.get("byte", 0),
                "attiva": res.get("attiva"), "chi": chi, "chi_nome": chi_nome,
                "inizio": datetime.datetime.fromtimestamp(inizio).isoformat(timespec="seconds"),
                "fine": datetime.datetime.now().isoformat(timespec="seconds"),
                # L'annullo e la pulizia li ha già detti il tool: solo nel registro
                "annuncia": res["esito"] != "annullato" and a.tipo != "pulizia"}
        self.ultimo = item
        self.done.put(item)
        if self.on_done and item["annuncia"]:
            self.on_done()

    def completa(self, item: dict) -> str:
        """Sul thread principale: attiva quello che si può attivare senza riavvio, aggiorna
        il registro delle capacità e restituisce la frase da annunciare."""
        titolo = item["titolo"]
        if item["esito"] != "ok":
            return f"Non sono riuscita a installare {titolo}. {item.get('frase') or ''}".strip()
        how = item.get("attiva")
        cap = item.get("capacita")
        activated = False
        if how == "subito" and cap in self.attivatori:
            try:
                activated = bool(self.attivatori[cap]())
            except Exception as e:  # noqa: BLE001
                self._log(f"[INSTALLA] attivazione di {cap} non riuscita: {e}")
        elif cap and cap in _cap.CONTROLLI and cap != "biblioteca":
            _cap.REGISTRO.da_dict(_cap.controlla_una(self.cfg, cap))
            activated = how == "subito"
        if how == "nessuna":
            return (f"Ho finito di scaricare {titolo} e ho verificato il checksum: per ora la "
                    f"conservo, la userò nelle ricerche quando sarà pronta l'integrazione.")
        verb = "preparare" if item.get("azione") == "biblioteca_indice" else "installare"
        if how == "riavvio" or (how == "subito" and not activated and cap in self.attivatori):
            return f"Ho finito di {verb} {titolo}: si userà dopo un riavvio, riavviami quando vuoi."
        extra = {"biblioteca": " Ora puoi chiedermi fatti e significati delle parole.",
                 "voce": " Puoi chiedermi di parlare con questa voce."}.get(cap, "")
        return f"Ho finito di {verb} {titolo}: si può già usare.{extra}"

    # ── stato e annullo ──
    def stato(self) -> dict:
        job = self.lavoro
        if job is not None and self.occupato():
            if job.fase == "verifico":
                frase = f"Ho scaricato {job.azione.titolo} e sto verificando il checksum."
            elif job.fase == "indice":
                pct = (f": sono al {min(99, int(job.fatto * 100 / job.totale))} per cento"
                       if job.totale and job.fatto else "")
                frase = (f"Sto preparando l'indice di ricerca della biblioteca{pct}. Intanto "
                         f"la biblioteca si usa come prima.")
            elif job.totale:
                pct = min(99, int(job.fatto * 100 / job.totale))
                elapsed = max(1.0, time.time() - job.inizio)
                rest = (job.totale - job.fatto) / max(job.fatto / elapsed, 1.0) / 60
                frase = (f"Sto scaricando {job.azione.titolo}: sono al {pct} per cento, "
                         f"{parla_byte(job.fatto)} su {parla_byte(job.totale)}; manca "
                         f"{parla_minuti(rest)}.")
            else:
                frase = f"Sto scaricando {job.azione.titolo}."
            return {"in_corso": True, "azione": job.azione.id, "fatto": job.fatto,
                    "totale": job.totale, "fase": job.fase, "frase": frase}
        last = self.ultimo
        if last:
            esito = {"ok": "è finito bene", "annullato": "è stato annullato",
                     "errore": "non è riuscito"}.get(last["esito"], last["esito"])
            return {"in_corso": False, "frase": f"Non sto scaricando niente. L'ultimo, "
                    f"{last['titolo']}, {esito}."}
        return {"in_corso": False, "frase": "Non sto scaricando niente."}

    def annulla(self) -> dict:
        job = self.lavoro
        if job is None or not self.occupato():
            return {"ok": False, "frase": "Non sto scaricando niente."}
        indexing = job.fase == "indice"
        job.cancel.set()
        job.thread.join(timeout=5)
        if indexing:
            return {"ok": True, "frase": "Ho fermato la preparazione dell'indice: i file "
                    "scaricati restano, e la biblioteca si usa come prima. Quando vuoi "
                    "chiedimi di preparare l'indice della biblioteca."}
        resume = (" Quello che ho già scaricato resta: se me lo richiedi riparto da lì."
                  if job.azione.tipo != "ollama" else "")
        return {"ok": True, "frase": f"Ho annullato lo scaricamento di {job.azione.titolo}."
                + resume}

    def close(self):
        if self.occupato():
            self.lavoro.cancel.set()


def _cap1(s: str) -> str:
    return s[:1].upper() + s[1:]


def _titolo_zim(path) -> str:
    """«Wikipedia ridotta», «Vikidia»: il nome della fonte di un file ZIM, per la voce."""
    from .catalogo import FONTI
    fv = versione_zim(str(path))
    for f in FONTI:
        if fv and fv[0] == f.prefisso:
            return f.titolo.split(",")[0]
    return Path(path).name


def _part_size(f: FileCat) -> int:
    p = part_path(f.dest)
    try:
        return p.stat().st_size if p.exists() else 0
    except OSError:
        return 0


def _nice():   # pragma: no cover — nel figlio, solo fuori da Windows
    """Priorità bassa per la costruzione dell'indice (come BELOW_NORMAL su Windows)."""
    try:
        os.nice(10)
    except OSError:
        pass
