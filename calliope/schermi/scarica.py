"""
«Scarica» nella scheda del documento (07/10/2026): il file in MD, PDF o Word (o Excel per un
foglio), convertito al clic, dal server degli schermi.

Chi può scaricare:
- solo uno schermo **personale** a cui la scheda è arrivata davvero (`registra`, chiamata da
  hub.py quando la manda: mai una scheda costruita da chi chiede);
- e solo se il suo proprietario è la persona per cui era la scheda, o amministra;
- mai dalla zona grigia: la scheda personale ci arriva solo con l'identità decisa dalla voce
  (`Mittente.certo`, hub.destinatari) o perché scritta da quello schermo; una scheda mostrata
  nella zona grigia (lavoro_risultato del proprio lavoro) arriva senza «Scarica».

Come: la pagina chiede un gettone (`POST /api/scarica`, sessione nell'intestazione, come lo
scritto) e apre `GET /scarica/<gettone>`: un indirizzo a caso valido `schermi_scarica_s`
secondi (180) e per poche richieste, legato allo schermo. Senza intestazioni perché il
browser lo salva da sé (sul telefono negli scaricamenti), e senza sessione nell'URL. Il file si
fa al primo GET (in un thread) e resta nel gettone per le richieste dopo.

I tipi sono solo quelli fatti da qui (md, pdf, docx, xlsx) e, dal 28/10 (passo 2d, #259), il
file **originale** di un documento dell'archivio di casa, solo dei tipi che l'archivio legge
(PDF, immagini, docx, txt: `ORIGINALI`), letto al clic con i permessi rifatti adesso
(`file_fn`, costruita da schermi/raccolte.py): niente eseguibili. Il Markdown va
come text/markdown con nosniff; ogni risposta ha una CSP «sandbox», così un file aperto nel
browser invece che salvato non esegue niente.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict
from urllib.parse import quote

FORMATI = {
    "md": ("md", "text/markdown; charset=utf-8"),
    "pdf": ("pdf", "application/pdf"),
    "word": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "excel": ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    # L'audio di un avviso di pericolo (14/10, minori.Avvisi.scheda_di): dal cassetto del tutore
    "audio": ("wav", "audio/wav"),
    # Il file originale dell'archivio di casa (28/10, #259): estensione e tipo da `ORIGINALI`
    "originale": ("", "application/octet-stream"),
}
# I file dell'archivio di casa che si scaricano così come sono (le estensioni che l'archivio
# legge, archivio/testo.ESTENSIONI), con il tipo giusto per Safari su iPhone
ORIGINALI = {
    "pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "webp": "image/webp", "tif": "image/tiff", "tiff": "image/tiff", "bmp": "image/bmp",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain; charset=utf-8",
}
MAX_VOCI = 400           # schede scaricabili ricordate **per schermo** (le più recenti; dal 28/10,
                         # #259, anche una per riga dell'archivio di casa nella pagina Documenti;
                         # per schermo dalla revisione della PR #268: con un tetto unico la pagina
                         # riletta su uno schermo toglieva le voci degli altri, e «Scarica» dava 404)
MAX_GETTONI = 64
USI = 3                  # richieste per gettone (un download che riprova, l'anteprima di iOS)
AL_MINUTO = 20           # gettoni al minuto per schermo

INTESTAZIONI = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store", "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'none'; sandbox"}


class Rifiuto(Exception):
    def __init__(self, stato: int, frase: str):
        super().__init__(frase)
        self.stato = stato
        self.frase = frase


def audio_avviso(sorgente: dict, persona, avvisi=None) -> bytes:
    """L'audio di un avviso (14/10; dal 14/10 sera, rifiniture, la scheda porta solo l'id del
    file del cassetto, `avviso_audio`, e sopravvive a un riavvio nella cronologia): letto al
    clic per `persona`, il proprietario dello schermo personale che ha chiesto il gettone, con i
    permessi rifatti adesso (minori.Avvisi.audio_per: destinatario dell'avviso, ancora tutore,
    file attivo nel suo cassetto). Rifiuto 404 se non c'è più."""
    if avvisi is None:
        from .. import minori
        avvisi = minori.avvisi()
    fid = sorgente.get("avviso_audio")
    dati = avvisi.audio_per(persona, fid) if avvisi is not None and persona and fid else None
    if not dati:
        raise Rifiuto(404, "l'audio non c'è più: è scaduto o è stato tolto")
    return bytes(dati)


def converti(sorgente: dict, formato: str, font=None, persona=None, avvisi=None) -> bytes:
    """I byte del file: dal Markdown (a_blocchi per PDF e Word) o dal documento a blocchi.
    `persona`: chi scarica (il proprietario dello schermo), per l'audio di un avviso."""
    from ..documenti import markdown as md
    from ..documenti.render import available_formats, render
    if formato not in FORMATI:
        raise Rifiuto(400, "formato non ammesso")
    if formato == "originale" or "file_fn" in sorgente:
        # Il file dell'archivio di casa (28/10, #259): la funzione rifà i permessi e lo legge
        if formato != "originale" or not callable(sorgente.get("file_fn")):
            raise Rifiuto(400, "formato non disponibile per questo documento")
        letto = sorgente["file_fn"]()
        if letto is None:
            raise Rifiuto(404, "il file non c'è più, o non è più tuo da vedere")
        return bytes(letto[0] if isinstance(letto, tuple) else letto)
    if formato == "audio" or "avviso_audio" in sorgente:
        # L'audio di un avviso (14/10): solo da una scheda che ce l'ha, letto al clic dal cassetto
        if formato != "audio" or not sorgente.get("avviso_audio"):
            raise Rifiuto(400, "formato non disponibile per questo documento")
        return audio_avviso(sorgente, persona, avvisi)
    if callable(sorgente.get("markdown_fn")):
        # La trascrizione della conversazione (08/10, hub.registra_chat): fatta adesso
        # dall'archivio, così il file ha anche i turni arrivati dopo la scheda
        sorgente = {"markdown": str(sorgente["markdown_fn"]() or ""),
                    "titolo": sorgente.get("titolo")}
    if "markdown_file" in sorgente:
        # Il registro di un lavoro (08/10, agenti/avanzamento.py): un file del server, letto
        # al clic (il percorso viene solo dalla scheda costruita qui, mai dalla pagina)
        from pathlib import Path
        try:
            testo = Path(str(sorgente["markdown_file"])).read_text(encoding="utf-8",
                                                                  errors="replace")
        except OSError:
            raise Rifiuto(404, "il registro non c'è più") from None
        sorgente = {"markdown": testo, "titolo": sorgente.get("titolo")}
    if "markdown" in sorgente:
        testo = str(sorgente.get("markdown") or "")
        if formato == "md":
            return md.normalizza(testo).encode("utf-8")
        if formato == "excel":
            raise Rifiuto(400, "un testo non diventa un foglio Excel")
        doc = md.a_blocchi(testo, str(sorgente.get("titolo") or ""))
    else:
        doc = sorgente.get("documento") or {}
        foglio = sorgente.get("formato") == "excel"
        if formato == "md":
            return md.da_blocchi(doc).encode("utf-8")
        if foglio != (formato == "excel"):
            raise Rifiuto(400, "formato non disponibile per questo documento")
    if formato not in available_formats()[0]:
        raise Rifiuto(503, "manca la libreria per questo formato")
    return render(formato, doc, font)


def estensione(formato: str, sorgente: dict | None = None) -> str:
    """L'estensione del file: quella del formato o, per l'originale, quella del file vero (solo
    fra `ORIGINALI`; altrimenti «bin»)."""
    if formato == "originale":
        e = str((sorgente or {}).get("estensione") or "").lower().lstrip(".")
        return e if e in ORIGINALI else "bin"
    return FORMATI[formato][0]


def tipo_mime(formato: str, sorgente: dict | None = None) -> str:
    if formato == "originale":
        return ORIGINALI.get(estensione(formato, sorgente), "application/octet-stream")
    return FORMATI[formato][1]


def nome_file(titolo: str, formato: str, sorgente: dict | None = None) -> str:
    """Il nome del file salvato: il titolo senza i caratteri vietati, in forma NFC (28/10, #259:
    le lettere accentate composte, come le scrive iOS, non «a» più l'accento a parte)."""
    import unicodedata
    from ..documenti.formato import safe_filename
    nome = unicodedata.normalize("NFC", safe_filename(titolo))
    return f"{nome}.{estensione(formato, sorgente)}"


def disposizione(nome: str) -> str:
    """Content-Disposition per il salvataggio: un nome ASCII di riserva e quello vero in
    UTF-8 (RFC 6266). Il nome di riserva toglie gli accenti invece di metterci «_» (28/10, #259:
    «Città» → «Citta»), per chi non legge `filename*`."""
    import unicodedata
    piatto = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii") or "file"
    ascii_ = "".join(c if 32 <= ord(c) < 127 and c not in '"\\;' else "_" for c in piatto)
    return f"attachment; filename=\"{ascii_}\"; filename*=UTF-8''{quote(nome, safe='')}"


class Scaricamenti:
    """Le schede scaricabili per schermo e i gettoni. Thread-safe; non blocca mai la voce
    (la conversione la fa il server, in un thread suo)."""

    def __init__(self, cfg):
        self.cfg = cfg
        self._lock = threading.Lock()
        self._voci: dict[int, OrderedDict] = {}      # sid → (chiave → voce), MAX_VOCI ciascuno
        self._gettoni: OrderedDict = OrderedDict()   # gettone → dati
        self._richieste: dict[int, list[float]] = {}
        # Gli avvisi dei tutori (minori.Avvisi) per l'audio di un avviso; None = quelli del
        # servizio (minori.avvisi()). Le prove ne passano uno loro
        self.avvisi = None

    @property
    def durata_s(self) -> float:
        return float(getattr(self.cfg, "schermi_scarica_s", 180.0) or 180.0)

    def registra(self, sid: int, scheda: dict, persona: str | None):
        """La scheda con `_scarica` è arrivata allo schermo `sid`, per `persona`."""
        sorgente = scheda.get("_scarica")
        chiave = scheda.get("chiave") or scheda.get("id")
        if not isinstance(sorgente, dict) or not chiave or not persona:
            return
        with self._lock:
            per = self._voci.setdefault(sid, OrderedDict())
            per.pop(chiave, None)
            per[chiave] = {"sorgente": sorgente, "persona": persona,
                           "formati": tuple(scheda.get("scarica") or ()),
                           "solo_persona": bool(sorgente.get("solo_persona")),
                           "titolo": str(sorgente.get("titolo") or scheda.get("titolo") or "Documento")}
            while len(per) > MAX_VOCI:
                per.popitem(last=False)

    def dimentica(self, sids) -> int:
        """Gli schermi revocati (seconda revisione della PR #268, #260): via le loro voci di
        «Scarica» (fino a MAX_VOCI ciascuno, con le sorgenti intere), i gettoni e il conto delle
        richieste. Quante voci tolte."""
        via = {s for s in sids}
        tolte = 0
        with self._lock:
            for sid in via:
                tolte += len(self._voci.pop(sid, None) or ())
                self._richieste.pop(sid, None)
            for g in [g for g, d in self._gettoni.items() if d.get("sid") in via]:
                self._gettoni.pop(g, None)
        return tolte

    def tieni_solo(self, validi) -> int:
        """Tiene le voci dei soli schermi `validi` (gli abbinati): chiamata da `Schermi.abbinati`
        quando rilegge l'elenco, così anche uno schermo revocato da terminale (un altro
        processo) perde le sue voci. Quante voci tolte."""
        validi = set(validi)
        with self._lock:
            fuori = [sid for sid in set(self._voci) | set(self._richieste) if sid not in validi]
            fuori += [d.get("sid") for d in self._gettoni.values() if d.get("sid") not in validi]
        return self.dimentica(fuori) if fuori else 0

    def voce(self, sid: int, chiave: str) -> dict | None:
        with self._lock:
            per = self._voci.get(sid)
            return per.get(chiave) if per is not None else None

    def gettone(self, schermo: dict, chiave: str, formato: str, amministra: bool = False) -> dict:
        """{"url", "nome", "scade"} per lo schermo che chiede; Rifiuto altrimenti."""
        sid = schermo.get("id")
        proprietario = schermo.get("proprietario")
        if not proprietario:
            raise Rifiuto(403, "si scarica solo da uno schermo personale")
        formato = str(formato or "").lower()
        if formato not in FORMATI:
            raise Rifiuto(400, "formato non ammesso")
        v = self.voce(sid, str(chiave or ""))
        if v is None:
            raise Rifiuto(404, "questo documento non è più scaricabile da qui: chiedimelo di "
                               "nuovo")
        if v["persona"] != proprietario and (not amministra or v.get("solo_persona")):
            # L'audio di un avviso (14/10) solo al suo tutore: chi amministra non passa
            raise Rifiuto(403, "il documento è di un'altra persona")
        if v["formati"] and formato not in v["formati"]:
            raise Rifiuto(400, "formato non disponibile per questo documento")
        if (formato == "originale") != callable(v["sorgente"].get("file_fn")):
            raise Rifiuto(400, "formato non disponibile per questo documento")
        sorgente = v["sorgente"]
        if formato == "originale" and callable(sorgente.get("estensione_fn")):
            # Il nome che la pagina scrive in «Scaricato: …» deve essere quello del file salvato
            # (seconda revisione della PR #268, #260): con più copie di un documento il file
            # vero può avere un'altra estensione da quella registrata. `estensione_fn` guarda il
            # file che `file_fn` leggerà, senza leggerlo; None = non c'è più, o non è più suo
            try:
                ext = sorgente["estensione_fn"]()
            except Exception:  # noqa: BLE001 — un archivio guasto: come un file sparito
                ext = None
            if not ext:
                raise Rifiuto(404, "il file non c'è più, o non è più tuo da vedere")
            sorgente = {**sorgente, "estensione": ext}
        ora = time.monotonic()
        with self._lock:
            fatti = [t for t in self._richieste.get(sid, []) if ora - t < 60.0]
            if len(fatti) >= AL_MINUTO:
                self._richieste[sid] = fatti
                raise Rifiuto(429, "troppi scaricamenti: aspetta un momento")
            self._richieste[sid] = fatti + [ora]
            g = secrets.token_urlsafe(24)
            self._gettoni[g] = {"sid": sid, "sorgente": sorgente, "formato": formato,
                                "persona": proprietario,
                                "nome": nome_file(v["titolo"], formato, sorgente),
                                "tipo": tipo_mime(formato, sorgente), "usi": 0,
                                "scade": ora + self.durata_s, "dati": None,
                                "lock": threading.Lock()}
            while len(self._gettoni) > MAX_GETTONI:
                self._gettoni.popitem(last=False)
            nome = self._gettoni[g]["nome"]
        return {"url": f"/scarica/{g}", "nome": nome, "scade_s": round(self.durata_s)}

    def prendi(self, gettone: str, valido=None) -> tuple[str, str, bytes]:
        """(nome del file, tipo, byte) per il GET; Rifiuto se il gettone non vale (scaduto,
        usato troppe volte, schermo revocato: `valido(sid)`). Converte qui: chiamare da un
        thread, mai dal ciclo del server."""
        with self._lock:
            g = self._gettoni.get(str(gettone or ""))
            if g is None or time.monotonic() > g["scade"] or g["usi"] >= USI:
                self._gettoni.pop(str(gettone or ""), None)
                raise Rifiuto(404, "indirizzo scaduto: tocca di nuovo «Scarica»")
            g["usi"] += 1
        if valido is not None and not valido(g["sid"]):
            raise Rifiuto(404, "schermo non più abbinato")
        if g["formato"] == "originale":
            return self._originale(g)
        with g["lock"]:
            if g["dati"] is None:
                g["dati"] = converti(g["sorgente"], g["formato"],
                                     getattr(self.cfg, "documenti_font", None),
                                     persona=g.get("persona"), avvisi=self.avvisi)
        return g["nome"], g["tipo"], g["dati"]

    @staticmethod
    def _originale(g: dict) -> tuple[str, str, bytes]:
        """Il file dell'archivio di casa (revisione della PR #268): riletto dal disco a ogni uso
        (il gettone non tiene in memoria fino a `archivio_max_mb` per 180 s), e nome e tipo
        dall'estensione del file letto davvero (`file_fn` → (byte, estensione)), non da quella
        del documento: con più copie il primo file buono può essere un altro."""
        letto = g["sorgente"]["file_fn"]()
        if letto is None:
            raise Rifiuto(404, "il file non c'è più, o non è più tuo da vedere")
        dati, ext = letto if isinstance(letto, tuple) else (letto, g["sorgente"].get("estensione"))
        sorgente = {**g["sorgente"], "estensione": ext}
        if estensione("originale", sorgente) == "bin":
            raise Rifiuto(404, "questo file non si scarica da qui")
        nome = nome_file(str(g["sorgente"].get("titolo") or "Documento"), "originale", sorgente)
        return nome, tipo_mime("originale", sorgente), bytes(dati)
