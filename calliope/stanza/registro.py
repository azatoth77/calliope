"""
Il registro della stanza (13/10, conversazione di stanza, passo 1: progetto § 3.3, decisione
0029; terzo tipo di registro accanto a quelli della 0027).

Uno **per satellite**, chiave `stanza:<id>`: del canale, come l'anonimo `ospite:<corsia>`, non
di una persona. In sola aggiunta, `seq` senza buchi, un solo scrittore (il thread della stanza);
le revisioni (la corsia lenta, passo 3) saranno eventi nuovi che rimandano a quelli di prima,
mai riscritture: la proiezione `righe` prende l'ultima versione di ogni segmento.

Tipi (schema del § 3.3; quelli dei passi dopo sono già nominati):

    scambio_aperto / scambio_chiuso   scambio, motivo (silenzio, pausa, riavvio, dimentica)
    segmento        scambio, inizio/fine (epoch), voce_s, durante_voce, turno (id dell'ascolto
                    dei comandi se è legato a un turno), wake
    riga            segmento, versione (1 veloce, 2 lenta), inizio/fine, testo, chi
                    («persona:<id>», «calliope», «ignoto»…), nome, sicurezza («voce», «grigia»,
                    «nessuna»), p_min, rivolta («si» per un turno, «no», «ignoto»), minore
    riga_scartata   segmento, motivo (eco, allucinazione, vuota, tv, doppione, errore)
    presenza_inizio persona, nome (la voce sopra soglia la prima volta qui)
    presenza        persona, nome, inizio, fine: un intervallo chiuso (§ 3.5 ter: da una stanza
                    all'altra, chi era presente dove e quando)
    pausa / ripresa motivo («pausa», «ospiti»), fino
    detto_calliope, riassunto_stanza, analisi   (passi 2–6)

**Dove**: in memoria, al più `TENUTA_S` (24 h, decisione 0029 punto 8: «memoria» di serie) e al
più `MAX_EVENTI`; si perde al riavvio. Su disco (`stanza_tenuta: {giorni: N}` nel file locale
di chi amministra) nel passo dopo: `Evento.a_dict` è già la riga della tabella `eventi`.
"""

import itertools
import threading
import time
from dataclasses import dataclass, field

TENUTA_S = 24 * 3600.0
MAX_EVENTI = 20000

SCAMBIO_APERTO, SCAMBIO_CHIUSO = "scambio_aperto", "scambio_chiuso"
SEGMENTO, RIGA, RIGA_SCARTATA = "segmento", "riga", "riga_scartata"
PRESENZA_INIZIO, PRESENZA = "presenza_inizio", "presenza"
PAUSA, RIPRESA = "pausa", "ripresa"
TIPI = (SCAMBIO_APERTO, SCAMBIO_CHIUSO, SEGMENTO, RIGA, RIGA_SCARTATA, PRESENZA_INIZIO,
        PRESENZA, PAUSA, RIPRESA, "detto_calliope", "riassunto_stanza", "analisi")


@dataclass
class Evento:
    seq: int
    t: float                                  # epoch
    tipo: str
    dati: dict = field(default_factory=dict)

    def a_dict(self, chiave: str) -> dict:
        """La riga per il disco (tabella `eventi`, passo successivo): chiave del registro, seq,
        istante, tipo e i dati."""
        return {"registro": chiave, "seq": self.seq, "t": round(self.t, 3), "tipo": self.tipo,
                "dati": dict(self.dati)}


class RegistroStanza:
    def __init__(self, chiave: str, nome: str = "", tenuta_s: float = TENUTA_S,
                 max_eventi: int = MAX_EVENTI):
        self.chiave, self.nome = chiave, nome
        self.tenuta_s, self.max_eventi = float(tenuta_s), int(max_eventi)
        self._eventi: list[Evento] = []
        self._seq = itertools.count(1)
        self._lock = threading.Lock()
        self.tolti = 0                        # eventi usciti per la tenuta o il tetto

    def aggiungi(self, tipo: str, t: float | None = None, **dati) -> Evento:
        if tipo not in TIPI:
            raise ValueError(f"tipo di evento della stanza sconosciuto: {tipo!r}")
        with self._lock:
            e = Evento(next(self._seq), time.time() if t is None else float(t), tipo, dati)
            self._eventi.append(e)
            self._pota()
            return e

    def _pota(self):
        limite = time.time() - self.tenuta_s
        n, tot = 0, len(self._eventi)
        while n < tot and (self._eventi[n].t < limite or tot - n > self.max_eventi):
            n += 1
        if n:
            del self._eventi[:n]
            self.tolti += n

    def pota(self):
        with self._lock:
            self._pota()

    def eventi(self, tipo: str | None = None) -> list[Evento]:
        with self._lock:
            return [e for e in self._eventi if tipo is None or e.tipo == tipo]

    def __len__(self):
        with self._lock:
            return len(self._eventi)

    def righe(self, dal: float | None = None) -> list[dict]:
        """La proiezione: le righe vive (l'ultima versione di ogni segmento, o le righe senza
        segmento come quelle di un turno senza stanza), in ordine di inizio, senza le
        scartate."""
        with self._lock:
            ev = list(self._eventi)
        scartati = {e.dati.get("segmento") for e in ev if e.tipo == RIGA_SCARTATA}
        ultime: dict = {}
        sciolte = []
        for e in ev:
            if e.tipo != RIGA:
                continue
            d = dict(e.dati, seq=e.seq, t=e.t)
            seg = d.get("segmento")
            if seg is None:
                sciolte.append(d)
            elif seg not in scartati:
                if seg not in ultime or int(d.get("versione") or 1) >= int(
                        ultime[seg].get("versione") or 1):
                    ultime[seg] = d
        out = sorted(list(ultime.values()) + sciolte,
                     key=lambda d: (float(d.get("inizio") or d["t"]), d["seq"]))
        if dal is not None:
            out = [d for d in out if float(d.get("fine") or d["t"]) >= dal]
        return out

    def svuota(self) -> int:
        """«Dimentica» (decisione 0029, § 4 punto 5): via tutto, righe, segmenti e presenze.
        La numerazione continua (chi legge sa che è stato svuotato)."""
        with self._lock:
            n = len(self._eventi)
            self._eventi.clear()
            return n

    def conteggi(self) -> dict:
        with self._lock:
            ev = list(self._eventi)
        out: dict = {}
        for e in ev:
            out[e.tipo] = out.get(e.tipo, 0) + 1
        return out
