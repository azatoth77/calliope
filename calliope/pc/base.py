"""
Interfaccia delle capacità di un PC (docs/ricerche/2026-09-26-controllo-pc.md, sezione 5).

`PCExecutor` è ciò che Calliope sa chiedere a un PC: leggere volume, musica, luminosità,
batteria, programmi aperti e blocco; cambiare volume e luminosità; comandare la musica;
aprire un'app del catalogo; bloccare lo schermo; cercare un file e aprirne uno dei
risultati. Oggi c'è una sola implementazione, `LocalWindowsExecutor` (windows.py), che
agisce sul portatile stesso («esecutore in processo»). Domani la stessa interfaccia
passerà per un WebSocket verso un'app sul PC: per questo i metodi prendono e
restituiscono solo dati semplici (str, int, bool, dict, list), serializzabili in JSON.

Regole che valgono per ogni esecutore e stanno qui, non nelle implementazioni:
- le app si aprono solo dal catalogo (nome parlato → comando scritto nella
  configurazione), mai con un comando scelto dal modello;
- i file si aprono solo come «risultato n dell'ultima ricerca» fatta dalla stessa persona
  (il richiedente), e solo per qualche minuto: nessun percorso passa mai dal modello;
- a schermo bloccato si rifiuta tutto ciò che mostra o apre contenuti (app, file,
  ricerca, programmi aperti). Volume, musica e blocco restano ammessi.

I permessi per persona (proprietario, livello) li decide Calliope nei tool
(calliope/tools/pc.py): l'esecutore riceve solo chi chiede, per tenere separate le
ricerche di persone diverse.
"""

import difflib
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path

# Capacità che un esecutore può dichiarare. Se una manca (libreria non installata,
# monitor esterno senza DDC/CI, PC fisso senza batteria…) il tool corrispondente non c'è.
CAPACITA = ("volume", "media", "luminosita", "batteria", "programmi", "blocco",
            "ricerca", "app", "schermata", "webcam")
# Cosa può guardare pc_guarda (05/10) → la capacità che serve
CATTURE = {"schermo": "schermata", "webcam": "webcam"}
TIPI_FILE = ("qualsiasi", "documento", "pdf", "foto", "musica", "video")
COMANDI_MEDIA = ("riproduci", "pausa", "avanti", "indietro")
# Per quanto vale «apri il secondo»: dopo, i risultati si dimenticano e serve una ricerca
# nuova (si evita di aprire un file trovato ore prima, magari da un'altra conversazione)
RICERCA_VALIDA_S = 15 * 60

BLOCCATO = "lo schermo del PC è bloccato"

# «Apri» (pc_apri_file, documenti consegnati, risultati degli agenti) apre con il programma
# predefinito solo i tipi che mostrano un contenuto: documenti, fogli, presentazioni, PDF,
# testo, immagini, audio e video. Gli script e le pagine (.py, .ps1, .js, .htm…) si aprono
# come testo nel Blocco note: con il programma predefinito Windows li **esegue** (.py è
# associato a py.exe). Eseguibili, installatori e collegamenti non si aprono mai. Analisi di
# sicurezza del 03/10 (rete, difetto 1): un .py consegnato al satellite e poi «aperto»
# girava fuori dalla sandbox.
ESTENSIONI_APRI = frozenset((
    "pdf", "doc", "docx", "odt", "rtf", "txt", "md", "csv", "tsv", "log", "xls", "xlsx",
    "ods", "ppt", "pptx", "odp", "epub", "jpg", "jpeg", "png", "gif", "bmp", "webp", "tif",
    "tiff", "heic", "mp3", "wav", "flac", "m4a", "ogg", "aac", "wma", "mp4", "mkv", "avi",
    "mov", "webm", "wmv", "m4v"))
ESTENSIONI_COME_TESTO = frozenset((
    "py", "pyw", "ps1", "psm1", "psd1", "bat", "cmd", "vbs", "vbe", "js", "jse", "mjs", "wsf",
    "wsh", "hta", "htm", "html", "xhtml", "svg", "xml", "xsl", "json", "ini", "cfg", "conf",
    "toml", "yaml", "yml", "reg", "sql", "sh", "css", "ipynb"))


def modo_apertura(nome: str) -> str | None:
    """Come si apre un file: "normale" (programma predefinito), "testo" (Blocco note) o
    None (non si apre: eseguibili, installatori, collegamenti, tipi sconosciuti)."""
    ext = Path(str(nome or "")).suffix.lower().lstrip(".")
    if ext in ESTENSIONI_APRI:
        return "normale"
    if ext in ESTENSIONI_COME_TESTO:
        return "testo"
    return None


def errore(msg: str, **extra) -> dict:
    return {"ok": False, "errore": msg, **extra}


def mb(n: int) -> str:
    """Byte detti a voce: «12 MB», «800 KB»."""
    if n < 1024:
        return f"{n} byte"
    return f"{n / 1048576:.0f} MB" if n >= 1048576 else f"{n // 1024} KB"


class FileTroppoGrande(ValueError):
    def __init__(self, byte: int, massimo: int):
        super().__init__(f"il file è troppo grande ({mb(byte)}, il massimo è {mb(massimo)})")
        self.byte, self.massimo = byte, massimo


class PCExecutor(ABC):
    """Le capacità di un PC. Ogni metodo pubblico restituisce un dict con `ok`."""

    def __init__(self, nome: str, app: dict[str, str] | None = None,
                 max_risultati: int = 5):
        self.nome = nome
        # Catalogo: nome parlato («blocco note») → comando. Le chiavi in minuscolo.
        self._app = {k.strip().lower(): v for k, v in (app or {}).items()}
        self.max_risultati = max_risultati
        # Ultima ricerca per richiedente: (istante, risultati con percorso)
        self._ricerche: dict[str, tuple[float, list[dict]]] = {}
        self._mutex = threading.Lock()

    # ─────────────────────────── da implementare ───────────────────────────

    @abstractmethod
    def capacita(self) -> list[str]:
        """Le capacità disponibili su questo PC, sottoinsieme di CAPACITA."""

    @abstractmethod
    def volume_leggi(self) -> dict:
        """{"ok", "livello": 0–100, "muto": bool}"""

    @abstractmethod
    def volume_imposta(self, livello: int) -> dict:
        """Volume assoluto 0–100 (toglie anche il muto). {"ok", "livello", "muto"}"""

    @abstractmethod
    def volume_muto(self, attivo: bool) -> dict:
        """{"ok", "livello", "muto"}"""

    @abstractmethod
    def media_info(self) -> dict:
        """{"ok", "sessione": bool, "in_riproduzione": bool, "titolo", "artista", "app"}"""

    @abstractmethod
    def media_comando(self, comando: str) -> dict:
        """comando ∈ COMANDI_MEDIA. {"ok", "app"} o errore se non c'è nulla da comandare."""

    @abstractmethod
    def luminosita_leggi(self) -> dict:
        """{"ok", "livello": 0–100}"""

    @abstractmethod
    def luminosita_imposta(self, livello: int) -> dict:
        """{"ok", "livello"}"""

    @abstractmethod
    def batteria(self) -> dict:
        """{"ok", "percento", "in_carica"} oppure {"ok", "batteria": False} (PC fisso)."""

    @abstractmethod
    def schermo(self) -> dict:
        """{"ok", "bloccato": bool, "inattivo_s": float}"""

    @abstractmethod
    def blocca(self) -> dict:
        """Blocca la sessione (come Win+L). {"ok"}"""

    @abstractmethod
    def _programmi(self) -> list[str]:
        """Nomi leggibili dei programmi con una finestra visibile."""

    @abstractmethod
    def _avvia(self, comando: str) -> None:
        """Avvia il comando di una voce del catalogo (solo quelli)."""

    @abstractmethod
    def _cerca(self, testo: str, tipo: str, dal: str | None, al: str | None,
               massimo: int) -> list[dict]:
        """Risultati [{"nome", "estensione", "percorso", "modificato"}], i più recenti prima."""

    @abstractmethod
    def _apri(self, percorso: str) -> None:
        """Apre un file con il programma predefinito."""

    # ─────────────────────────── comuni ───────────────────────────

    def bloccato(self) -> bool:
        try:
            return bool(self.schermo().get("bloccato"))
        except Exception:
            return True                      # nel dubbio, come bloccato: si mostra meno

    def descrizione(self) -> dict:
        """Ciò che l'esecutore dichiara di sé (all'abbinamento, domani via rete)."""
        return {"nome": self.nome, "capacita": self.capacita(), "app": self.app_disponibili()}

    def app_disponibili(self) -> list[str]:
        return list(self._app)

    def programmi_aperti(self) -> dict:
        if self.bloccato():
            return errore(BLOCCATO, bloccato=True)
        return {"ok": True, "programmi": self._programmi()}

    def apri_app(self, app: str) -> dict:
        if self.bloccato():
            return errore(BLOCCATO, bloccato=True)
        key = (app or "").strip().lower()
        if key not in self._app:
            close = difflib.get_close_matches(key, list(self._app), n=1, cutoff=0.8)
            if not close:
                return errore(f"«{app}» non è tra le app che posso aprire",
                              app_disponibili=self.app_disponibili())
            key = close[0]
        self._avvia(self._app[key])
        return {"ok": True, "app": key}

    def cerca_file(self, richiedente: str, testo: str = "", tipo: str = "qualsiasi",
                   dal: str | None = None, al: str | None = None) -> dict:
        """Cerca nell'indice e ricorda i risultati per `richiedente`. I percorsi restano
        qui: fuori escono nome, estensione e data."""
        if self.bloccato():
            return errore(BLOCCATO, bloccato=True)
        if tipo not in TIPI_FILE:
            tipo = "qualsiasi"
        found = self._cerca(testo or "", tipo, dal, al, self.max_risultati)
        # Dal più recente (07/10): Windows Search lo fa già (ORDER BY System.DateModified,
        # anche sul satellite, che usa lo stesso esecutore); qui vale per ogni esecutore. Non
        # c'è un punteggio di pertinenza: il nome o il contenuto filtrano, la data ordina, e il
        # numero 1 della domanda «Quale apro?» è sempre il più recente (tools/pc.py)
        found = sorted(found, key=lambda r: str(r.get("modificato") or ""), reverse=True)
        with self._mutex:
            self._ricerche[richiedente] = (time.time(), found)
        return {"ok": True, "risultati": [
            {"n": i, "nome": r["nome"], "estensione": r.get("estensione", ""),
             "modificato": r.get("modificato")} for i, r in enumerate(found, 1)]}

    def offri_file(self, richiedente: str, item: dict) -> None:
        """Un file che Calliope ha appena scritto per `richiedente` (un documento, vedi
        calliope/documenti/) diventa la sua «ultima ricerca» con un solo risultato: così
        «aprilo» è pc_apri_file(1). `item` = {"nome", "estensione", "percorso",
        "modificato"}; è segnato come proprio: lo ha chiesto lui."""
        with self._mutex:
            self._ricerche[richiedente] = (time.time(), [{**item, "proprio": True}])

    def ultimo_proprio(self, richiedente: str) -> bool:
        """L'ultima «ricerca» di `richiedente` è un documento suo, ancora valido? Allora può
        aprirlo anche chi non è proprietario del PC: l'ha appena fatto scrivere lui."""
        with self._mutex:
            last = self._ricerche.get(richiedente)
        return bool(last and time.time() - last[0] <= RICERCA_VALIDA_S and last[1]
                    and all(r.get("proprio") for r in last[1]))

    def risultato(self, richiedente: str, risultato: int) -> dict:
        """Il risultato n (da 1; -1 = l'ultimo) dell'ultima ricerca di `richiedente`:
        {"ok", "item"} (con il percorso, che resta qui) o l'errore da dire."""
        with self._mutex:
            last = self._ricerche.get(richiedente)
        if last is None or time.time() - last[0] > RICERCA_VALIDA_S:
            return errore("non c'è una tua ricerca recente di file", serve_ricerca=True)
        found = last[1]
        if not found:
            return errore("l'ultima ricerca non aveva trovato niente", serve_ricerca=True)
        if int(risultato) == -1:                   # «l'ultimo»
            risultato = len(found)
        if len(found) == 1 and int(risultato) != 1:
            # Un solo file: qualunque numero vuol dire quello (07/10, DGX: dopo «salvato come
            # “Nome (2)”» il modello chiedeva il 2, e con una foto di mezzo la domanda di
            # conferma per un file che non c'era si ripeteva 10 volte). Correzione della forma
            # di una scelta già fatta dal modello (principio 10): regola `pc_numero_unico`
            return {"ok": True, "item": dict(found[0]), "numero_corretto": True}
        if not 1 <= int(risultato) <= len(found):
            # I numeri che ci sono, con i nomi (07/10, DGX: dopo «salvato come “Nome (2)”» il
            # modello chiamava pc_apri_file(2) e l'errore «ha 1 risultati, non 2» non gli
            # diceva quale numero usare)
            ci_sono = ("c'è solo il numero 1" if len(found) == 1
                       else f"ci sono i numeri da 1 a {len(found)}")
            elenco = "; ".join(f"{i} = «{r.get('nome')}»" for i, r in enumerate(found, 1))
            return errore(f"il numero {risultato} non c'è: {ci_sono} ({elenco}; il numero 1 è "
                          f"il più recente)", risultati=len(found))
        return {"ok": True, "item": dict(found[int(risultato) - 1])}

    def apri_file(self, richiedente: str, risultato: int) -> dict:
        """Apre il risultato n (da 1; -1 = l'ultimo) dell'ultima ricerca di `richiedente`."""
        if self.bloccato():
            return errore(BLOCCATO, bloccato=True)
        r = self.risultato(richiedente, risultato)
        if not r.get("ok"):
            return r
        item = r["item"]
        ext = str(item.get("estensione") or "").lower().lstrip(".")
        modo = modo_apertura(f"x.{ext}" if ext else str(item.get("percorso") or ""))
        if modo is None:
            return errore(f"i file .{ext or '?'} non li apro: sono programmi, installatori o "
                          f"collegamenti, e si avviano solo a mano", tipo_vietato=True)
        self._apri(item["percorso"])
        return {"ok": True, "nome": item["nome"], **({"come_testo": True} if modo == "testo"
                                                     else {}),
                **({"numero_corretto": True} if r.get("numero_corretto") else {})}

    def copia_file(self, item: dict, max_byte: int, estensioni) -> dict:
        """Una copia del file `item` (un risultato di `risultato`) per l'agente (03/10,
        calliope/agenti/file_utente.py): {"ok", "nome" (il nome vero del file, senza
        cartelle), "estensione", "dati"} o l'errore. Solo le `estensioni` ammesse, al più
        `max_byte`, mai a schermo bloccato. Chi può chiederla lo decidono i tool."""
        ext = str(item.get("estensione") or "").lower().lstrip(".")
        if ext not in set(estensioni or ()):
            return errore(f"i file .{ext or '?'} non si mandano all'agente")
        if self.bloccato():
            return errore(BLOCCATO, bloccato=True)
        try:
            nome, dati = self._leggi(item["percorso"], int(max_byte))
        except FileTroppoGrande as e:
            return errore(str(e), troppo_grande=True)
        except OSError as e:
            return errore(f"il file non si legge ({type(e).__name__})")
        if Path(nome).suffix.lower().lstrip(".") != ext:
            return errore("il file non è più quello trovato")
        return {"ok": True, "nome": nome, "estensione": ext, "dati": dati}

    def cattura(self, cosa: str) -> dict:
        """Una schermata («schermo») o una foto dalla webcam («webcam»), su richiesta (05/10,
        tool pc_guarda): {"ok", "dati": byte dell'immagine} o l'errore. Mai a schermo bloccato
        (né la schermata di blocco, né la webcam di un PC lasciato solo)."""
        cap = CATTURE.get(str(cosa or ""))
        if cap is None:
            return errore(f"non so guardare «{str(cosa)[:20]}»")
        if cap not in self.capacita():
            return errore("qui non posso " + ("fare schermate" if cap == "schermata"
                                              else "usare la webcam"))
        if self.bloccato():
            return errore(BLOCCATO, bloccato=True)
        return self._cattura(cosa)

    def _cattura(self, cosa: str) -> dict:
        """{"ok", "dati"}: le implementazioni con schermate o webcam la ridefiniscono."""
        return errore("qui non posso guardare")

    def _leggi(self, percorso: str, max_byte: int) -> tuple[str, bytes]:
        """(nome del file, byte) di un file di questo PC. Le implementazioni remote la
        ridefiniscono (il percorso è una maniglia del satellite)."""
        p = Path(percorso)
        size = p.stat().st_size
        if size > max_byte:
            raise FileTroppoGrande(size, max_byte)
        dati = p.read_bytes()
        if len(dati) > max_byte:
            raise FileTroppoGrande(len(dati), max_byte)
        return p.name, dati
