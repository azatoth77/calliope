"""
Esecutore remoto (03/10/2026): il PC di un satellite, comandato dal server.

Con Calliope sulla DGX il PC da comandare è il portatile collegato come satellite
(calliope/satellite/): `RemotePCExecutor` implementa `PCExecutor` inoltrando ogni chiamata
all'esecutore del satellite (calliope/satellite/esecutore.py) sulla sua connessione, con un
tempo massimo breve (`pc_remoto_timeout_s`, 2 s): la voce non aspetta oltre, e un guasto
diventa una frase chiara («il portatile non risponde»), mai un'attesa lunga.

Le regole comuni restano qui, nella classe base, sul server: permessi e proprietari (nei
tool), catalogo delle app, «risultato n dell'ultima ricerca» della stessa persona per 15
minuti, schermo bloccato. Cambia solo cosa viaggia:
- **file**: la ricerca torna con una «maniglia» casuale al posto del percorso; la classe
  base la tiene come `percorso` e per aprire la rimanda al satellite, che la conosce solo lui.
  Il percorso vero non lascia mai il portatile;
- **app**: il catalogo qui è fatto di soli nomi (quelli di `pc_app`); il comando lo prende il
  satellite dal suo catalogo. Il server non manda mai un comando da eseguire.

Quale satellite: quello attivo, cioè quello da cui si sta parlando (oggi uno solo).

I tool pc_* ci sono sempre, anche senza satellite collegato (`capacita_possibili`): un tool che
compare e scompare cambierebbe il prefisso del prompt a ogni riconnessione (cache di Ollama
persa). Senza esecutore rispondono con un errore chiaro, come casa_integrazione.
"""

import threading
import time

from .base import CAPACITA, PCExecutor


class PCNonCollegato(ConnectionError):
    """Nessun satellite con l'esecutore del PC è collegato (o è caduto a metà)."""


def per_pc(server):
    """Il collegamento del satellite con l'esecutore del PC (ServerSatelliti.per_pc: anche
    quando l'attivo è il telefono), o None. Le prove passano server finti con il solo
    attivo_pronto."""
    if server is None:
        return None
    f = getattr(server, "per_pc", None)
    return f() if f is not None else server.attivo_pronto()


class RemotePCExecutor(PCExecutor):
    remoto = True
    # Dopo un tempo scaduto le chiamate successive dello stesso tool falliscono subito per
    # qualche secondo: un tool fa anche 2–3 chiamate (schermo bloccato, poi l'azione) e la
    # voce non deve aspettare 2 s per ognuna
    PAUSA_DOPO_TIMEOUT_S = 5.0

    def __init__(self, server, nome: str = "portatile", app: list[str] | None = None,
                 max_risultati: int = 5, timeout_s: float = 2.0):
        # Il catalogo: solo nomi, uguali alla chiave (il comando sta sul satellite)
        super().__init__(nome, {a: a for a in (app or [])}, max_risultati)
        self.server = server
        self.timeout_s = float(timeout_s)
        self._muto_fino = 0.0
        self._lock_t = threading.Lock()

    # ── collegamento ──
    def _coll(self):
        c = per_pc(self.server)
        if c is None:
            raise PCNonCollegato(f"il {self.nome} non è collegato a Calliope")
        if getattr(c, "esecutore", None) is None:
            raise PCNonCollegato(f"il satellite collegato non offre il controllo del "
                                 f"{self.nome} (va aggiornato, oppure non è Windows)")
        return c

    def collegato(self) -> bool:
        try:
            self._coll()
            return True
        except PCNonCollegato:
            return False

    def motivo_non_collegato(self) -> str:
        try:
            self._coll()
            return ""
        except PCNonCollegato as e:
            return str(e)

    def _chiama(self, metodo: str, **argomenti) -> dict:
        c = self._coll()
        with self._lock_t:
            muto = time.monotonic() < self._muto_fino
        if muto:
            raise TimeoutError(f"il {self.nome} non risponde")
        try:
            return c.chiama_pc(metodo, argomenti, self.timeout_s)
        except TimeoutError:
            with self._lock_t:
                self._muto_fino = time.monotonic() + self.PAUSA_DOPO_TIMEOUT_S
            raise TimeoutError(f"il {self.nome} non risponde") from None
        except ConnectionError as e:
            raise PCNonCollegato(f"il {self.nome} si è scollegato") from e

    def _dati(self, metodo: str, **argomenti) -> dict:
        """Per i metodi «interni» della classe base, che non restituiscono un esito: un
        rifiuto del satellite diventa un'eccezione con il suo motivo."""
        r = self._chiama(metodo, **argomenti)
        if not r.get("ok"):
            raise RuntimeError(r.get("errore") or "non ha funzionato")
        return r

    # ── capacità ──
    def capacita(self) -> list[str]:
        try:
            return list(self._coll().esecutore["capacita"])
        except PCNonCollegato:
            return []

    def capacita_possibili(self) -> list[str]:
        """Per i tool: tutte, sempre (il prefisso del prompt non cambia con il satellite)."""
        return list(CAPACITA)

    def app_catalogo(self) -> list[str]:
        """L'enum di pc_apri_app: il catalogo di calliope.yaml, stabile."""
        return list(self._app)

    def app_disponibili(self) -> list[str]:
        """Le app del catalogo; con un satellite collegato solo quelle che ha davvero."""
        try:
            sue = set(self._coll().esecutore.get("app") or ())
        except PCNonCollegato:
            return list(self._app)
        return [a for a in self._app if a in sue]

    # ── schermo bloccato: qui un guasto non vale «bloccato» ──
    def bloccato(self) -> bool:
        """Come la classe base, ma senza satellite o con un tempo scaduto si solleva
        l'eccezione: «il portatile è bloccato» sarebbe falso, e i tool dicono il motivo vero."""
        r = self._chiama("schermo")
        if not r.get("ok"):
            return True
        return bool(r.get("bloccato"))

    # ── letture e azioni: inoltrate ──
    def volume_leggi(self) -> dict:
        return self._chiama("volume_leggi")

    def volume_imposta(self, livello: int) -> dict:
        return self._chiama("volume_imposta", livello=int(livello))

    def volume_muto(self, attivo: bool) -> dict:
        return self._chiama("volume_muto", attivo=bool(attivo))

    def media_info(self) -> dict:
        return self._chiama("media_info")

    def media_comando(self, comando: str) -> dict:
        return self._chiama("media_comando", comando=comando)

    def luminosita_leggi(self) -> dict:
        return self._chiama("luminosita_leggi")

    def luminosita_imposta(self, livello: int) -> dict:
        return self._chiama("luminosita_imposta", livello=int(livello))

    def batteria(self) -> dict:
        return self._chiama("batteria")

    def schermo(self) -> dict:
        return self._chiama("schermo")

    def blocca(self) -> dict:
        return self._chiama("blocca")

    def _programmi(self) -> list[str]:
        return list(self._dati("programmi").get("programmi") or [])

    def _avvia(self, comando: str) -> None:
        self._dati("avvia", app=comando)     # qui «comando» è il nome dell'app

    def _cerca(self, testo, tipo, dal, al, massimo) -> list[dict]:
        r = self._dati("cerca", testo=testo, tipo=tipo, dal=dal, al=al, massimo=massimo)
        return [{"nome": str(x.get("nome") or ""), "estensione": str(x.get("estensione") or ""),
                 "modificato": x.get("modificato"), "percorso": str(x.get("maniglia") or "")}
                for x in (r.get("risultati") or []) if isinstance(x, dict)]

    def _apri(self, percorso: str) -> None:
        self._dati("apri", maniglia=percorso)  # la maniglia data dal satellite

    # ── foto su richiesta (05/10): la webcam costa più dei 2 s delle altre chiamate ──
    CATTURA_TIMEOUT_S = 10.0

    def cattura(self, cosa: str) -> dict:
        """Come la classe base, ma la cattura la fa il satellite (che ricontrolla schermo
        bloccato e capacità e mostra l'avviso): l'immagine torna in base64 nel `pc_esito`,
        già ridotta là (sotto il MB dei messaggi)."""
        import base64
        c = self._coll()
        try:
            r = c.chiama_pc("cattura", {"cosa": str(cosa)}, self.CATTURA_TIMEOUT_S)
        except TimeoutError:
            raise TimeoutError(f"il {self.nome} non ha mandato l'immagine in tempo") from None
        except ConnectionError as e:
            raise PCNonCollegato(f"il {self.nome} si è scollegato") from e
        if not r.get("ok"):
            return r
        try:
            return {"ok": True, "dati": base64.b64decode(str(r.get("jpeg_b64") or ""),
                                                         validate=True)}
        except ValueError:
            return {"ok": False, "errore": "immagine arrivata rovinata"}

    # ── una copia di un file per l'agente (03/10) ──
    # Velocità prudente per il tempo massimo del trasferimento (in VPN qualche MB/s)
    VELOCITA_FILE_MB_S = 1.0

    def copia_file(self, item: dict, max_byte: int, estensioni) -> dict:
        """Come la classe base, ma il file sta sul satellite: lo manda lui, a pezzi con lo
        SHA-256 (Collegamento.ricevi_file), dopo aver ricontrollato maniglia, estensione,
        dimensione e schermo bloccato. Blocca fino al tempo massimo: solo dal thread dei
        lavori, mai dalla voce. Solleva PCNonCollegato o TimeoutError."""
        ext = str(item.get("estensione") or "").lower().lstrip(".")
        if ext not in set(estensioni or ()):
            return {"ok": False, "errore": f"i file .{ext or '?'} non si mandano all'agente"}
        c = self._coll()
        attesa = 10.0 + int(max_byte) / (self.VELOCITA_FILE_MB_S * 1048576)
        try:
            return c.ricevi_file(item["percorso"], int(max_byte), list(estensioni), attesa)
        except TimeoutError:
            raise TimeoutError(f"il {self.nome} non ha mandato il file in tempo") from None
