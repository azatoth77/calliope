"""
La porta verso internet per il codice che non è di Calliope (05/10/2026): le estensioni (porta
stretta, calliope/estensioni/porta.py) e l'agente che scrive un parser (scarica_esempio,
calliope/agenti/ciclo.py). Regola di Dario del 05/10: **internet pubblico si legge
liberamente**, i dati personali escono solo lungo i flussi approvati (lo decide il guardrail,
calliope/guardrail.py); qui si garantisce che la richiesta vada davvero su internet pubblico,
con dei tetti, e che resti scritta.

- Tutte le regole di `pagina.scarica` (solo http e https sulle porte 80 e 443, nessun nome
  locale, ogni indirizzo del nome pubblico, connessione all'indirizzo già controllato, ogni
  reindirizzamento ricontrollato, tempo e dimensione massimi, gzip con un tetto). Porte 80 e
  443 soltanto: le altre porte pubbliche servono di rado a un sito di dati e sono quelle dei
  servizi esposti per errore (un Ollama su 0.0.0.0, un pannello d'amministrazione).
- In più gli indirizzi di **questa macchina** visti da fuori (se la DGX ha un IP pubblico, il
  suo Ollama su 0.0.0.0 sarebbe «pubblico») e `web_reti_vietate`.
- Un tetto al minuto per tutto il processo (`estensioni_rete_max_minuto`): un'estensione o un
  agente impazzito non diventa un generatore di traffico dall'IP dell'ufficio.
- Il **registro delle uscite** (`uscite.jsonl` nella cartella delle estensioni): una riga per
  richiesta, fatta o bloccata, con chi (estensione e versione, o lavoro dell'agente), persona,
  host, metodo, byte, esito e motivo. Mai il percorso né la query (potrebbero contenere dati):
  solo l'host. `riepilogo()` per il registro delle capacità.
"""

from __future__ import annotations

import collections
import json
import socket
import threading
import time
from pathlib import Path

from . import pagina

TIPI_DATI = ("text/html", "application/xhtml+xml", "text/plain", "application/json",
             "text/csv", "application/xml", "text/xml", "application/rss+xml",
             "application/atom+xml")


def indirizzi_propri() -> list[str]:
    """Gli indirizzi con cui questa macchina esce (senza mandare pacchetti: un connect UDP
    sceglie solo l'interfaccia). Se uno è pubblico, va vietato come gli altri."""
    out = []
    for fam, dest in ((socket.AF_INET, ("192.0.2.1", 53)), (socket.AF_INET6, ("2001:db8::1", 53))):
        try:
            with socket.socket(fam, socket.SOCK_DGRAM) as s:
                s.connect(dest)
                out.append(s.getsockname()[0])
        except OSError:
            continue
    return out


class RetePubblica:
    def __init__(self, cfg=None, registro: str | Path | None = None, risolutore=None,
                 eccezioni=frozenset(), porte=(80, 443), scarica=None, contesto_tls=None,
                 log=print):
        """`risolutore`, `eccezioni`, `porte` e `contesto_tls` servono solo alle prove (un sito
        finto su 127.0.0.2 con il suo certificato)."""
        self.cfg = cfg
        self.contesto_tls = contesto_tls
        self.registro = Path(registro) if registro else None
        self.risolutore = risolutore
        self.eccezioni = frozenset(eccezioni)
        self.porte = tuple(porte)
        self._scarica = scarica or pagina.scarica
        self.log = log
        self.max_minuto = int(getattr(cfg, "estensioni_rete_max_minuto", 30) or 30)
        vietate = list(getattr(cfg, "web_reti_vietate", None) or ())
        vietate += [ip for ip in indirizzi_propri()
                    if not pagina.indirizzo_vietato(ip)]           # solo quelli pubblici
        self.vietate = pagina.reti(vietate)
        self._lock = threading.Lock()
        self._ultime: collections.deque = collections.deque()
        # I dati riservati di casa (web/riservati.py, 05/10): nessuna richiesta li porta fuori,
        # nemmeno codificati o a pezzi su più richieste della stessa esecuzione o dello stesso
        # lavoro. Lo imposta chi ha la memoria (load_estensioni); None = nessun controllo
        self.riservati = None
        self._usciti: dict = {}             # esecuzione o lavoro → valori già usciti

    # ── tetto ──
    def _posto(self) -> bool:
        ora = time.monotonic()
        with self._lock:
            while self._ultime and ora - self._ultime[0] > 60:
                self._ultime.popleft()
            if len(self._ultime) >= self.max_minuto:
                return False
            self._ultime.append(ora)
            return True

    # ── richiesta ──
    def richiesta(self, url: str, origine: dict, metodo: str = "GET", corpo: str | None = None,
                  max_byte: int = 1_000_000, timeout_s: float = 10.0, tipi=TIPI_DATI,
                  host_ammesso=None, max_rimandi: int = 3) -> dict:
        """Il risultato di `pagina.scarica`, o PaginaVietata / PaginaNonLetta. Ogni richiesta
        (riuscita o no) finisce nel registro delle uscite."""
        host = _host(url)
        inviati = len(corpo.encode("utf-8")) if corpo else 0
        # Un indirizzo con spazi o caratteri non codificati non parte (08/10): prima partiva
        # rotto e tornava «collegamento non riuscito», senza la causa per chi scrive il codice
        rotto = pagina.url_non_codificato(url)
        if rotto:
            self.registra(origine, host, metodo, "bloccata", "url_non_codificato",
                          inviati=inviati)
            raise pagina.PaginaVietata(rotto)
        trovati = self._riservati(url, corpo, origine)
        if trovati:
            self.registra(origine, host, metodo, "bloccata",
                          "dato_riservato: " + ", ".join(trovati), inviati=inviati)
            raise pagina.PaginaVietata("la richiesta contiene un dato riservato di casa")
        if not self._posto():
            self.registra(origine, host, metodo, "bloccata",
                          f"più di {self.max_minuto} richieste al minuto", inviati=inviati)
            raise pagina.PaginaVietata(f"troppe richieste a internet (al più {self.max_minuto} "
                                       "al minuto)")
        t0 = time.monotonic()
        try:
            r = self._scarica(url, max_byte=max_byte, timeout_s=timeout_s, vietate=self.vietate,
                              eccezioni=self.eccezioni, porte=self.porte,
                              risolutore=self.risolutore, tipi=tipi, metodo=metodo, corpo=corpo,
                              host_ammesso=host_ammesso, max_rimandi=max_rimandi,
                              contesto_tls=self.contesto_tls)
        except pagina.PaginaVietata as e:
            self.registra(origine, host, metodo, "bloccata", str(e), inviati=inviati)
            raise
        except pagina.PaginaNonLetta as e:
            self.registra(origine, host, metodo, "fallita", str(e), inviati=inviati,
                          ms=int((time.monotonic() - t0) * 1000))
            raise
        finale = _host(r.get("url") or url)
        self.registra(origine, host, metodo, "fatta", "", inviati=inviati,
                      ricevuti=int(r.get("byte") or len(r.get("testo_grezzo") or "")),
                      ms=int((time.monotonic() - t0) * 1000),
                      **({"host_finale": finale} if finale != host else {}))
        return r

    def _riservati(self, url: str, corpo, origine: dict) -> list[str]:
        """I tipi di dato riservato nella richiesta, anche sommando i valori delle richieste
        precedenti della stessa esecuzione o dello stesso lavoro (un segreto a pezzi)."""
        r = self.riservati
        if r is None:
            return []
        from urllib.parse import parse_qsl, unquote_plus, urlsplit
        try:
            u = urlsplit(str(url or ""))
            pezzi = {"q": "".join(v for _, v in parse_qsl(u.query, keep_blank_values=True))
                     + str(corpo or ""),
                     "p": ([x for x in unquote_plus(u.path).split("/") if x] or [""])[-1],
                     "h": (u.hostname or "").split(".")[0]}
        except ValueError:
            pezzi = {"q": str(corpo or "")}
        # Tre somme separate (valori della query e corpo, ultimo pezzo del percorso, primo
        # pezzo del nome): un pezzo fisso in mezzo («/x?a=Gira», «/x?a=sole») non le spezza
        chiave = str((origine or {}).get("esecuzione") or (origine or {}).get("lavoro") or "")
        with self._lock:
            prima = self._usciti.get(chiave, {}) if chiave else {}
            somme = {k: (prima.get(k, "") + v)[-20_000:] for k, v in pezzi.items()}
            if chiave:
                self._usciti[chiave] = somme
                while len(self._usciti) > 200:
                    self._usciti.pop(next(iter(self._usciti)))
        somma = " ".join(somme.values())
        try:
            tipi = r.trova(str(url or ""), str(corpo or ""), *somme.values(),
                           forme_personali=False)
            if r.ripulitore is not None:
                for t in (str(url or ""), str(corpo or "")):
                    _, tolti = r.ripulitore.pulisci(unquote_plus(t))
                    tipi += [x for x in tolti if x == "dato_privato" and x not in tipi]
            return tipi
        except Exception:  # noqa: BLE001 — il controllo non rompe la richiesta: blocca
            return ["controllo_non_riuscito"]

    # ── registro ──
    def registra(self, origine: dict, host: str, metodo: str, esito: str, motivo: str = "",
                 inviati: int = 0, ricevuti: int = 0, **extra):
        h = self.host_per_registro(host)
        if h != host and host:
            motivo = str(motivo or "").replace(host, h)
        riga = {"quando": time.strftime("%Y-%m-%dT%H:%M:%S"), **(origine or {}),
                "host": h, "metodo": metodo, "byte_inviati": inviati,
                "byte_ricevuti": ricevuti, "esito": esito, **extra}
        if motivo:
            riga["motivo"] = str(motivo)[:200]
        if self.registro is None:
            return
        try:
            self.registro.parent.mkdir(parents=True, exist_ok=True)
            with open(self.registro, "a", encoding="utf-8") as f:
                f.write(json.dumps(riga, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass

    def riepilogo(self, ore: float = 24) -> dict:
        return riepilogo(self.registro, ore)

    def host_per_registro(self, host: str) -> str:
        """L'host com'è, o «[tolto]» se il nome stesso porta un dato riservato
        («girasole-blu-4417.sito.org»): il registro delle uscite non deve contenerlo."""
        r = self.riservati
        if r is None or not host:
            return host
        try:
            return "[tolto: dato riservato]" if r.trova(host, forme_personali=False) else host
        except Exception:  # noqa: BLE001
            return "[tolto]"


def riepilogo(registro, ore: float = 24) -> dict:
    """{"richieste", "fatte", "bloccate", "byte_inviati", "byte_ricevuti", "host"} delle ultime
    `ore` ore, letto dalla coda del registro (al più gli ultimi 2 MB)."""
    out = {"richieste": 0, "fatte": 0, "bloccate": 0, "byte_inviati": 0, "byte_ricevuti": 0,
           "host": 0}
    p = Path(registro) if registro else None
    if p is None or not p.is_file():
        return out
    limite = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - ore * 3600))
    host = set()
    try:
        with open(p, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 2_000_000))
            righe = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return out
    for r in righe:
        try:
            d = json.loads(r)
        except ValueError:
            continue
        if not isinstance(d, dict) or str(d.get("quando") or "") < limite:
            continue
        out["richieste"] += 1
        if d.get("esito") == "fatta":
            out["fatte"] += 1
        elif d.get("esito") == "bloccata":
            out["bloccate"] += 1
        out["byte_inviati"] += int(d.get("byte_inviati") or 0)
        out["byte_ricevuti"] += int(d.get("byte_ricevuti") or 0)
        if d.get("host"):
            host.add(d["host"])
    out["host"] = len(host)
    return out


def _host(url: str) -> str:
    from urllib.parse import urlsplit
    try:
        return (urlsplit(str(url or "")).hostname or "").rstrip(".").lower()[:120]
    except ValueError:
        return ""
