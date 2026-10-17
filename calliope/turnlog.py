"""
Registro dei turni: una riga JSON per ogni frase captata, un file al giorno.

È la base dell'auto-miglioramento (docs/visione.md): chi parla, cosa ha capito Whisper,
cosa è stato fatto (tool, guardia) e con quali tempi. Da qui si ricavano, per esempio,
le frasi ripetute subito dopo, segnale di una trascrizione sbagliata (vedi revisione.py).
Dal 01/10 il campo `regole` elenca le regole deterministiche sul testo scattate nel turno
(uscita, stop, spinte, azione in sospeso, correzioni dei tool…): solo nomi, così si misura
quanto scattano senza conservare altro.

Privacy: degli ospiti (voce non riconosciuta) non si salva il testo, né la richiesta né
la risposta; i file più vecchi di `keep_days` si cancellano all'avvio e poi una volta al
giorno. Dal 12/10 (decisione 0028, T1, calliope/conserva.py) le parole restano solo per le
persone di casa riconosciute, per `turn_log_days` (60) giorni: delle voci incerte (zona grigia)
restano solo i numeri. Dal 16/10 (decisione 0031) anche i minori e i dubbi tra un adulto e un
minore tengono le parole (dal 12 al 16/10 no). Lo decide `Conservazione.testo_turno`, il
solo posto; il ciclo lo segna nel turno (`conserva`), e qui vale anche per le righe scritte da
altri (cassetto, schermi, installazioni). Dal 14/10 sera (decisione 0030 aggiornata) anche i
turni di un **conoscente**: livello ospite, ma nel campo `voce` il suo id, il nome
(`nome_conoscente`) e le parole, come un adulto.
"""

import datetime
import json
import threading
from pathlib import Path


class TurnLog:
    PREFIX = "turni-"

    def __init__(self, folder: str | None, keep_days: int = 60, modello: dict | None = None,
                 conserva=None):
        self.folder = Path(folder) if folder else None
        # La conservazione (12/10, calliope/conserva.Conservazione): chi tiene le parole. None
        # (prove, `calliope stato`): solo la regola degli ospiti
        self.conserva = conserva
        # Campi del modello della voce in ogni turno ({"profilo", "modello"}, 06/10): le regole
        # che scattano si contano per profilo (config.RETI, categoria «modello»). Dal 15/10 anche
        # `reti_spente` (llm_reti_spente, profilo e locale insieme), scritta anche vuota: il
        # rapporto degli scatti (calliope/reti_scatti.py) sa così se una rete era accesa
        self.modello = {k: v for k, v in (modello or {}).items()
                        if v is not None and v != ""}
        self.keep_days = keep_days
        self._lock = threading.Lock()
        self._pulito_il = None                  # il giorno dell'ultima pulizia
        if self.folder:
            self.folder.mkdir(parents=True, exist_ok=True)
            self._prune()

    def _prune(self):
        """Cancella i file più vecchi del limite di conservazione."""
        self._pulito_il = datetime.date.today()
        limit = self._pulito_il - datetime.timedelta(days=self.keep_days)
        for f in self.folder.glob(f"{self.PREFIX}*.jsonl"):
            try:
                day = datetime.date.fromisoformat(f.stem[len(self.PREFIX):])
            except ValueError:
                continue
            if day < limit:
                f.unlink(missing_ok=True)

    errori = 0                      # righe non scritte (disco pieno, permessi…)

    def _senza_parole(self, rec: dict) -> bool:
        """Le parole di questo turno non restano: ospite, segnato dal ciclo, o (righe scritte
        da altri) la conservazione dice no. Un conoscente (14/10 sera, decisione 0030
        aggiornata) è di livello ospite ma le parole restano, se lo dice la conservazione."""
        if _segnato_no(rec):
            return True
        v = rec.get("voce") if isinstance(rec.get("voce"), dict) else {}
        conoscente = bool(v.get("conoscente") and v.get("id") and not v.get("nome"))
        if rec.get("livello") == "ospite" and not conoscente:
            return True
        if self.conserva is not None and "conserva" not in rec:
            try:
                return not self.conserva.testo_turno(rec)
            except Exception:  # noqa: BLE001 — nel dubbio senza parole
                return True
        # Senza la conservazione (prove, `calliope stato`) un conoscente resta senza parole
        return conoscente and self.conserva is None

    def write(self, record: dict):
        """Aggiunge un turno. Per gli ospiti toglie i testi prima di scrivere. Non solleva
        mai (03/10, analisi di robustezza): con il disco pieno ogni turno sollevava OSError
        e il ciclo principale si chiudeva; ora la riga si salta e lo dice il log (la prima
        volta e poi ogni 100)."""
        if not self.folder:
            return
        try:
            self._write(record)
        except Exception as e:  # noqa: BLE001
            self.errori += 1
            if self.errori == 1 or self.errori % 100 == 0:
                print(f"   [REGISTRO] Turno non registrato ({type(e).__name__}: {e}); "
                      f"righe perse finora: {self.errori}", flush=True)

    def _write(self, record: dict):
        # Pulizia anche durante l'esecuzione, una volta al giorno (03/10): sulla DGX Calliope
        # gira per settimane, e i turni restavano oltre keep_days fino al riavvio
        if self._pulito_il != datetime.date.today():
            self._prune()
            # E la rotazione della conservazione (17/10, issue #32): prima girava solo
            # all'avvio e salvando la voce, così il banco della stanza a eccezione scaduta e la
            # voce di chi non parla più restavano oltre i giorni. In secondo piano, una volta
            if self.conserva is not None:
                try:
                    self.conserva.ruota_se_serve()
                except Exception:  # noqa: BLE001 — la rotazione non ferma il registro
                    pass
        rec = dict(record)
        for k, v in self.modello.items():
            rec.setdefault(k, v)
        if self._senza_parole(rec):
            # Ospiti (dal 01/10), e dal 12/10 voci incerte (dal 12 al 16/10 anche i minori):
            # restano i numeri, le regole e i nomi dei tool; per testo e risposta quante parole
            # c'erano (07/10)
            from .conserva import togli_testo
            togli_testo(rec)
        day = (rec.get("inizio") or datetime.datetime.now().isoformat())[:10]
        line = json.dumps(rec, ensure_ascii=False, default=str)
        with self._lock, open(self.folder / f"{self.PREFIX}{day}.jsonl", "a",
                              encoding="utf-8") as f:
            f.write(line + "\n")


def _segnato_no(rec: dict) -> bool:
    c = rec.get("conserva")
    return isinstance(c, dict) and c.get("testo") is False


def read_turns(folder: str, days: int | None = None) -> list[dict]:
    """Legge i turni registrati (gli ultimi `days` giorni, o tutti), in ordine."""
    files = sorted(Path(folder).glob(f"{TurnLog.PREFIX}*.jsonl"))
    if days is not None:
        files = files[-days:]
    turns = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                turns.append(json.loads(line))
    return turns
