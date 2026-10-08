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

I tipi sono solo quelli fatti da qui (md, pdf, docx, xlsx): niente eseguibili. Il Markdown va
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
}
MAX_VOCI = 64            # schede scaricabili ricordate (le più recenti)
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


def converti(sorgente: dict, formato: str, font=None) -> bytes:
    """I byte del file: dal Markdown (a_blocchi per PDF e Word) o dal documento a blocchi."""
    from ..documenti import markdown as md
    from ..documenti.render import available_formats, render
    if formato not in FORMATI:
        raise Rifiuto(400, "formato non ammesso")
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


def nome_file(titolo: str, formato: str) -> str:
    from ..documenti.formato import safe_filename
    return f"{safe_filename(titolo)}.{FORMATI[formato][0]}"


def disposizione(nome: str) -> str:
    """Content-Disposition per il salvataggio: un nome ASCII di riserva e quello vero in
    UTF-8 (RFC 6266)."""
    ascii_ = "".join(c if 32 <= ord(c) < 127 and c not in '"\\;' else "_" for c in nome)
    return f"attachment; filename=\"{ascii_}\"; filename*=UTF-8''{quote(nome, safe='')}"


class Scaricamenti:
    """Le schede scaricabili per schermo e i gettoni. Thread-safe; non blocca mai la voce
    (la conversione la fa il server, in un thread suo)."""

    def __init__(self, cfg):
        self.cfg = cfg
        self._lock = threading.Lock()
        self._voci: OrderedDict = OrderedDict()      # (sid, chiave) → voce
        self._gettoni: OrderedDict = OrderedDict()   # gettone → dati
        self._richieste: dict[int, list[float]] = {}

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
            self._voci.pop((sid, chiave), None)
            self._voci[(sid, chiave)] = {"sorgente": sorgente, "persona": persona,
                                         "formati": tuple(scheda.get("scarica") or ()),
                                         "titolo": str(sorgente.get("titolo") or
                                                       scheda.get("titolo") or "Documento")}
            while len(self._voci) > MAX_VOCI:
                self._voci.popitem(last=False)

    def voce(self, sid: int, chiave: str) -> dict | None:
        with self._lock:
            return self._voci.get((sid, chiave))

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
        if v["persona"] != proprietario and not amministra:
            raise Rifiuto(403, "il documento è di un'altra persona")
        if v["formati"] and formato not in v["formati"]:
            raise Rifiuto(400, "formato non disponibile per questo documento")
        ora = time.monotonic()
        with self._lock:
            fatti = [t for t in self._richieste.get(sid, []) if ora - t < 60.0]
            if len(fatti) >= AL_MINUTO:
                self._richieste[sid] = fatti
                raise Rifiuto(429, "troppi scaricamenti: aspetta un momento")
            self._richieste[sid] = fatti + [ora]
            g = secrets.token_urlsafe(24)
            self._gettoni[g] = {"sid": sid, "sorgente": v["sorgente"], "formato": formato,
                                "nome": nome_file(v["titolo"], formato), "usi": 0,
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
        with g["lock"]:
            if g["dati"] is None:
                g["dati"] = converti(g["sorgente"], g["formato"],
                                     getattr(self.cfg, "documenti_font", None))
        return g["nome"], FORMATI[g["formato"]][1], g["dati"]
