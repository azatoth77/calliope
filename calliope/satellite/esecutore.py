"""
L'esecutore del PC sul satellite (03/10/2026, ricerca del 26/09 §5.3 punto 2).

Con Calliope sulla DGX il PC da comandare è il portatile collegato come satellite: il server
manda `pc_richiesta` sulla stessa connessione autenticata (e cifrata) dell'audio, e qui le
esegue `LocalWindowsExecutor`, lo stesso codice di Calliope in locale. I documenti scritti
sulla DGX arrivano come `file` a pezzi, con lo SHA-256, e si salvano con `LocalDelivery`
nella cartella Calliope dei Documenti del portatile.

Cosa resta qui e non esce mai:
- **i percorsi**: una ricerca manda al server nome, estensione, data e una «maniglia»
  casuale; per aprire un file il server rimanda la maniglia, che vale solo se l'ha data
  questo processo e per poco più dei 15 minuti di una ricerca. Il riferimento di un
  documento è «sat:<nome del file>», sempre dentro la cartella dei documenti;
- **i comandi delle app**: il server chiede un'app per nome e il comando si prende dal
  catalogo `pc_app` di questo PC (calliope.yaml del portatile), mai dal server.

I file della persona per un lavoro dell'agente (03/10): il server manda `file_richiesta` con
la maniglia di una ricerca; qui si controllano maniglia, estensione (`P.ESTENSIONI_INVIO`),
dimensione e schermo bloccato, poi il file parte a pezzi b"G" con lo SHA-256. Solo il nome
del file (senza cartelle) esce insieme al contenuto. I risultati tornano come documenti
nuovi (`file`), mai sopra l'originale: si salvano sempre nella cartella Calliope.

Le regole comuni (permessi, `pc_proprietari`, risultato n dell'ultima ricerca della stessa
persona) le applica il server, nella classe base di `RemotePCExecutor`. Qui, per sicurezza,
si ricontrolla lo schermo bloccato prima di mostrare o aprire qualcosa (programmi, app,
ricerca, file), l'elenco dei metodi e gli argomenti. Una richiesta arrivata quando il server
ha già smesso di aspettarla non si esegue (niente azioni in ritardo né ripetute).
"""

import datetime
import hashlib
import re
import secrets
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from ..pc.base import BLOCCATO, COMANDI_MEDIA, RICERCA_VALIDA_S, TIPI_FILE, errore
from . import protocollo as P

ESTENSIONI_FILE = P.ESTENSIONI_RICEVUTE  # documenti e risultati degli agenti
MANIGLIE_MAX = 500
MANIGLIA_S = RICERCA_VALIDA_S + 300
RIF = "sat:"                       # prefisso dei riferimenti dei documenti consegnati qui

# Metodo → capacità che serve (None: nessuna)
_CAPACITA = {"volume_leggi": "volume", "volume_imposta": "volume", "volume_muto": "volume",
             "media_info": "media", "media_comando": "media",
             "luminosita_leggi": "luminosita", "luminosita_imposta": "luminosita",
             "batteria": "batteria", "schermo": None, "blocca": "blocco",
             "programmi": "programmi", "avvia": "app", "cerca": "ricerca", "apri": None,
             "cattura": None}
# Questi mostrano o aprono contenuti: a schermo bloccato no (come la classe base)
_DA_SBLOCCATO = ("programmi", "avvia", "cerca", "apri", "cattura")
# La foto torna in base64 dentro il pc_esito: il server accetta messaggi fino a 1 MB
CATTURA_MAX_B64 = 700_000


def _livello(v) -> int:
    return max(0, min(100, int(v)))


def _data(v) -> str | None:
    """Una data ISO dal server, o None; qualunque altra cosa si scarta."""
    if not v:
        return None
    try:
        return datetime.datetime.fromisoformat(str(v)).isoformat()
    except ValueError:
        return None


class EsecutoreSatellite:
    def __init__(self, pc=None, consegna=None, nome: str = "portatile", log=print):
        self.pc = pc                      # PCExecutor locale, o None (solo documenti)
        self.consegna = consegna          # LocalDelivery, o None
        self.nome = nome
        self.log = log
        self._maniglie: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()
        self._file: dict[int, dict] = {}  # consegne in arrivo, per id
        # Un thread solo: le chiamate native sono già in fila in LocalWindowsExecutor, e
        # la ricezione della connessione non si ferma mai ad aspettarle
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="esecutore")
        self.eseguite = 0                 # misure e prove
        self.scadute = 0
        self.file_ricevuti = 0
        self.file_mandati = 0
        self.rovina_invio = False         # solo le prove: un byte cambiato dopo lo SHA-256

    def descrizione(self) -> dict:
        """Ciò che il satellite annuncia nel «ciao»."""
        caps = self.pc.capacita() if self.pc is not None else []
        return {"nome": self.nome, "sistema": sys.platform, "capacita": caps,
                "app": self.pc.app_disponibili() if self.pc is not None and "app" in caps
                else [], "file": self.consegna is not None,
                # Sa mandare all'agente una copia di un file trovato con la ricerca
                "invio": self.pc is not None and "ricerca" in caps}

    def chiudi(self):
        self._pool.shutdown(wait=False, cancel_futures=True)
        close = getattr(self.pc, "close", None)
        if close is not None:
            close()

    # ── maniglie: i percorsi restano qui ──
    def _maniglia(self, percorso: str) -> str:
        m = secrets.token_urlsafe(12)
        ora = time.monotonic()
        with self._lock:
            for k in [k for k, (t, _) in self._maniglie.items() if ora - t > MANIGLIA_S]:
                del self._maniglie[k]
            while len(self._maniglie) >= MANIGLIE_MAX:
                del self._maniglie[next(iter(self._maniglie))]
            self._maniglie[m] = (ora, percorso)
        return m

    def _percorso(self, maniglia) -> str | None:
        with self._lock:
            v = self._maniglie.get(str(maniglia or ""))
        if v is None or time.monotonic() - v[0] > MANIGLIA_S:
            return None
        return v[1]

    # ── richieste ──
    def richiesta(self, m: dict, rispondi):
        """Una `pc_richiesta`: si esegue nel thread dell'esecutore, la risposta è un
        `pc_esito` con lo stesso id."""
        arrivo = time.monotonic()
        try:
            scadenza = max(0.1, min(60.0, float(m.get("scadenza_s") or 5.0)))
        except (TypeError, ValueError):
            scadenza = 5.0
        self._pool.submit(self._lavora, m, arrivo, scadenza, rispondi)

    def _lavora(self, m: dict, arrivo: float, scadenza: float, rispondi):
        ident, metodo = m.get("id"), str(m.get("metodo") or "")
        if time.monotonic() - arrivo > scadenza:
            # Il server ha già risposto «non ha risposto in tempo»: farla adesso sarebbe
            # un'azione che nessuno aspetta più
            self.scadute += 1
            rispondi(tipo="pc_esito", id=ident, errore="richiesta scaduta")
            return
        t0 = time.perf_counter()
        try:
            esito = self._esegui(metodo, m.get("argomenti") or {})
        except TimeoutError:
            esito = errore(f"il {self.nome} non ha risposto in tempo")
        except Exception as e:  # noqa: BLE001 — un guasto diventa un esito, mai un crash
            esito = errore(str(e) or type(e).__name__)
        self.eseguite += 1
        ms = (time.perf_counter() - t0) * 1000
        self.log(f"[ESECUTORE] {metodo}: " + ("ok" if esito.get("ok") else
                                              f"no ({esito.get('errore')})") + f", {ms:.0f} ms")
        rispondi(tipo="pc_esito", id=ident, esito=esito)

    def _esegui(self, metodo: str, a: dict) -> dict:
        if metodo not in P.METODI_PC:
            return errore(f"metodo «{metodo[:40]}» sconosciuto")
        pc = self.pc
        if metodo == "apri" and pc is not None:
            pass                           # anche i documenti consegnati (niente capacità)
        elif pc is None or (_CAPACITA[metodo] and _CAPACITA[metodo] not in pc.capacita()):
            return errore(f"sul {self.nome} questo non si può fare")
        if metodo in _DA_SBLOCCATO and pc.bloccato():
            return errore(BLOCCATO, bloccato=True)
        if metodo == "volume_leggi":
            return pc.volume_leggi()
        if metodo == "volume_imposta":
            return pc.volume_imposta(_livello(a.get("livello")))
        if metodo == "volume_muto":
            return pc.volume_muto(bool(a.get("attivo")))
        if metodo == "media_info":
            return pc.media_info()
        if metodo == "media_comando":
            comando = str(a.get("comando") or "")
            if comando not in COMANDI_MEDIA:
                return errore(f"comando «{comando[:20]}» sconosciuto")
            return pc.media_comando(comando)
        if metodo == "luminosita_leggi":
            return pc.luminosita_leggi()
        if metodo == "luminosita_imposta":
            return pc.luminosita_imposta(_livello(a.get("livello")))
        if metodo == "batteria":
            return pc.batteria()
        if metodo == "schermo":
            return pc.schermo()
        if metodo == "blocca":
            return pc.blocca()
        if metodo == "programmi":
            return {"ok": True, "programmi": list(pc._programmi())}
        if metodo == "cattura":
            return self._cattura(str(a.get("cosa") or ""))
        if metodo == "avvia":
            # Il server dice il nome; il comando è quello del catalogo di questo PC
            nome = str(a.get("app") or "").strip().lower()
            comando = pc._app.get(nome)
            if comando is None:
                return errore(f"«{nome[:40]}» non è tra le app di questo PC")
            pc._avvia(comando)
            return {"ok": True, "app": nome}
        if metodo == "cerca":
            tipo = str(a.get("tipo") or "qualsiasi")
            try:
                massimo = max(1, min(20, int(a.get("massimo") or pc.max_risultati)))
            except (TypeError, ValueError):
                massimo = pc.max_risultati
            trovati = pc._cerca(str(a.get("testo") or "")[:200],
                                tipo if tipo in TIPI_FILE else "qualsiasi",
                                _data(a.get("dal")), _data(a.get("al")), massimo)
            return {"ok": True, "risultati": [
                {"nome": r["nome"], "estensione": r.get("estensione", ""),
                 "modificato": r.get("modificato"), "maniglia": self._maniglia(r["percorso"])}
                for r in trovati[:massimo]]}
        # apri
        percorso = self._percorso(a.get("maniglia"))
        if percorso is None:
            return errore("il file non è più disponibile: serve una ricerca nuova",
                          serve_ricerca=True)
        pc._apri(percorso)
        return {"ok": True}

    def _cattura(self, cosa: str) -> dict:
        """Una schermata o una foto dalla webcam (05/10, pc_guarda): solo su richiesta del
        server, con l'avviso sul PC (LocalWindowsExecutor._cattura), ridotta qui in JPEG
        (lato 1280) e in base64 sotto CATTURA_MAX_B64. Niente file."""
        import base64
        r = self.pc.cattura(cosa)
        if not r.get("ok"):
            return r
        from ..immagini import ImmagineNonValida, prepara
        try:
            for lato, q in ((1280, 85), (1280, 70), (1024, 65), (800, 60)):
                jpeg, w, h = prepara(r["dati"], lato, max_byte=60_000_000, qualita=q)
                b64 = base64.b64encode(jpeg).decode()
                if len(b64) <= CATTURA_MAX_B64:
                    break
            else:
                return errore("immagine troppo grande da mandare")
        except ImmagineNonValida as e:
            return errore(str(e))
        self.log(f"[ESECUTORE] {'foto dalla webcam' if cosa == 'webcam' else 'schermata'} "
                 f"mandata ({w}×{h}, {len(jpeg) // 1024} KB)")
        return {"ok": True, "jpeg_b64": b64, "larghezza": w, "altezza": h}

    # ── file per l'agente (satellite → server) ──
    def file_richiesta(self, m: dict, rispondi, rispondi_bin):
        """Una `file_richiesta`: nel thread dell'esecutore, risposta `file_dati` e pezzi."""
        arrivo = time.monotonic()
        try:
            scadenza = max(0.5, min(600.0, float(m.get("scadenza_s") or 30.0)))
        except (TypeError, ValueError):
            scadenza = 30.0
        self._pool.submit(self._manda_file, m, arrivo, scadenza, rispondi, rispondi_bin)

    def _manda_file(self, m: dict, arrivo: float, scadenza: float, rispondi, rispondi_bin):
        ident = m.get("id")

        def no(msg, **extra):
            self.log(f"[ESECUTORE] file per l'agente: no ({msg})")
            rispondi(tipo="file_dati", id=ident, ok=False, errore=msg, **extra)

        if time.monotonic() - arrivo > scadenza:
            self.scadute += 1
            return no("richiesta scaduta")
        pc = self.pc
        if pc is None or "ricerca" not in pc.capacita():
            return no(f"il {self.nome} non manda file")
        percorso = self._percorso(m.get("maniglia"))
        if percorso is None:
            return no("il file non è più disponibile: serve una ricerca nuova", serve_ricerca=True)
        ammesse = {str(e).lower() for e in (m.get("estensioni") or [])} & set(P.ESTENSIONI_INVIO)
        try:
            max_byte = max(0, min(int(m.get("max_byte") or 0), P.FILE_MAX))
        except (TypeError, ValueError):
            max_byte = 0
        ext = percorso.rsplit(".", 1)[-1].lower() if "." in percorso else ""
        try:
            r = pc.copia_file({"percorso": percorso, "estensione": ext}, max_byte, ammesse)
        except Exception as e:  # noqa: BLE001 — un guasto diventa un esito
            return no(f"il file non si legge ({type(e).__name__})")
        if not r.get("ok"):
            return no(r.get("errore") or "non si può", **{k: True for k in
                                                        ("troppo_grande", "bloccato")
                                                        if r.get(k)})
        dati = r["dati"]
        sha = hashlib.sha256(dati).hexdigest()
        if self.rovina_invio and dati:
            dati = bytes([dati[0] ^ 1]) + dati[1:]
        # L'invio (in VPN anche qualche secondo) in un thread a parte: le richieste pc_* dietro
        # a questa non devono scadere aspettando la fine del trasferimento
        threading.Thread(target=self._invia_pezzi, args=(ident, r, dati, sha, rispondi,
                                                         rispondi_bin),
                         daemon=True, name="esecutore-invio").start()

    def _invia_pezzi(self, ident, r: dict, dati: bytes, sha: str, rispondi, rispondi_bin):
        rispondi(tipo="file_dati", id=ident, ok=True, nome=r["nome"], estensione=r["estensione"],
                 byte=len(dati), sha256=sha)
        for i in range(0, len(dati), P.PEZZO_FILE):
            if not rispondi_bin(P.binario(P.FILE_SU, ident, dati[i:i + P.PEZZO_FILE])):
                return
        self.file_mandati += 1
        self.log(f"[ESECUTORE] copia di un file mandata all'agente ({len(dati) / 1024:.0f} KB)")

    # ── documenti ──
    def file_inizio(self, m: dict, rispondi):
        """L'intestazione di una consegna; i pezzi arrivano dopo, sulla stessa connessione."""
        ident = m.get("id")
        try:
            byte = int(m.get("byte"))
        except (TypeError, ValueError):
            byte = -1
        sha = str(m.get("sha256") or "").lower()
        est = str(m.get("estensione") or "").lower()
        motivo = None
        if self.consegna is None:
            motivo = "questo satellite non riceve documenti"
        elif est not in ESTENSIONI_FILE:
            motivo = f"tipo di file «{est[:10]}» non ammesso"
        elif not 0 <= byte <= P.FILE_MAX:
            motivo = "file troppo grande"
        elif not re.fullmatch(r"[0-9a-f]{64}", sha):
            motivo = "checksum mancante"
        if motivo:
            rispondi(tipo="file_esito", id=ident, ok=False, errore=motivo)
            return
        voce = {"id": ident, "nome": str(m.get("nome") or "Documento"), "estensione": est,
                "byte": byte, "sha256": sha, "sostituisci": m.get("sostituisci"),
                "mtime": m.get("mtime"), "buf": bytearray(), "h": hashlib.sha256(),
                "rispondi": rispondi}
        if byte == 0:
            self._pool.submit(self._salva, voce)
            return
        with self._lock:
            self._file[ident] = voce

    def file_pezzo(self, ident: int, dati: bytes):
        with self._lock:
            voce = self._file.get(ident)
        if voce is None:
            return
        if len(voce["buf"]) + len(dati) > voce["byte"]:
            with self._lock:
                self._file.pop(ident, None)
            voce["rispondi"](tipo="file_esito", id=ident, ok=False,
                             errore="il file è arrivato più lungo del previsto")
            return
        voce["buf"] += dati
        voce["h"].update(dati)
        if len(voce["buf"]) == voce["byte"]:
            with self._lock:
                self._file.pop(ident, None)
            self._pool.submit(self._salva, voce)

    def azzera_consegne(self):
        """Connessione caduta: le consegne a metà non arriveranno più (il server ripiega)."""
        with self._lock:
            self._file.clear()

    def _rif(self, rif) -> str | None:
        """«sat:<nome>» → percorso nella cartella dei documenti; None se non è dei nostri."""
        r = str(rif or "")
        if not r.startswith(RIF):
            return None
        nome = r[len(RIF):]
        if not nome or any(c in nome for c in '/\\:') or nome in (".", "..") \
                or nome.startswith(".."):
            return None
        return str(self.consegna.folder / nome)

    def _salva(self, voce: dict):
        rispondi, ident = voce["rispondi"], voce["id"]
        try:
            if voce["h"].hexdigest() != voce["sha256"]:
                rispondi(tipo="file_esito", id=ident, ok=False,
                         errore="il file è arrivato rovinato (checksum diverso)")
                return
            from ..documenti.formato import safe_filename
            mtime = voce["mtime"]
            d = self.consegna.deliver(safe_filename(voce["nome"]), voce["estensione"],
                                      bytes(voce["buf"]), replace=self._rif(voce["sostituisci"]),
                                      mtime=float(mtime) if isinstance(mtime, (int, float))
                                      else None)
            self.file_ricevuti += 1
            self.log(f"[ESECUTORE] documento ricevuto: {d['nome_file']} "
                     f"({voce['byte'] / 1024:.0f} KB)")
            rispondi(tipo="file_esito", id=ident, ok=True, rif=RIF + d["nome_file"],
                     nome_file=d["nome_file"], mtime=d.get("mtime"), motivo=d.get("motivo"),
                     maniglia=self._maniglia(d["rif"]))
        except Exception as e:  # noqa: BLE001 — disco pieno, cartella non scrivibile…
            rispondi(tipo="file_esito", id=ident, ok=False,
                     errore=f"non sono riuscita a salvarlo ({type(e).__name__})")


def crea_esecutore(cfg, log=print) -> EsecutoreSatellite | None:
    """L'esecutore di questo satellite: solo su Windows e con `satellite_esecutore`. Il
    controllo del PC c'è con `pc_enabled` e le librerie (altrimenti solo i documenti)."""
    if sys.platform != "win32" or not getattr(cfg, "satellite_esecutore", True):
        return None
    from ..documenti.consegna import LocalDelivery
    pc = None
    if getattr(cfg, "pc_enabled", False):
        try:
            from ..pc.windows import LocalWindowsExecutor
            pc = LocalWindowsExecutor(cfg.pc_nome, cfg.pc_app, cfg.pc_risultati,
                                      webcam=getattr(cfg, "satellite_webcam", "")
                                      or getattr(cfg, "pc_webcam", ""))
        except Exception as e:  # noqa: BLE001 — il PC è un di più: il satellite parte
            log(f"[ESECUTORE] Controllo del PC non disponibile: {type(e).__name__}: {e}")
            pc = None
    consegna = LocalDelivery(getattr(cfg, "documenti_cartella", None))
    ese = EsecutoreSatellite(pc, consegna, cfg.pc_nome, log=log)
    caps = ese.descrizione()["capacita"]
    log("[ESECUTORE] Per il server: " + (", ".join(caps) if caps else "niente controllo del PC")
        + "; documenti in " + consegna.where().removeprefix("nella "))
    return ese
