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
giorno.
"""

import datetime
import json
import threading
from pathlib import Path


class TurnLog:
    PREFIX = "turni-"

    def __init__(self, folder: str | None, keep_days: int = 30, modello: dict | None = None):
        self.folder = Path(folder) if folder else None
        # Campi del modello della voce in ogni turno ({"profilo", "modello"}, 06/10): le regole
        # che scattano si contano per profilo (config.RETI, categoria «modello»)
        self.modello = {k: v for k, v in (modello or {}).items() if v}
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
        rec = dict(record)
        for k, v in self.modello.items():
            rec.setdefault(k, v)
        if rec.get("livello") == "ospite":
            for key in ("testo", "risposta"):
                # Quante parole c'erano (07/10): «testo: null» di un ospite si confondeva con
                # una frase vuota arrivata al modello, «risposta: null» con il silenzio
                if isinstance(rec.get(key), str):
                    rec.setdefault(f"{key}_parole", len(rec[key].split()))
            for key in ("testo", "richiesta", "risposta"):
                if rec.get(key) is not None:
                    rec[key] = None
            if rec.get("stt_corretta"):          # prima e dopo: le parole dell'ospite
                rec["stt_corretta"] = {}
            if rec.get("stt_capito"):            # B2: come sopra, resta solo l'esito
                rec["stt_capito"] = {k: v for k, v in rec["stt_capito"].items()
                                     if k not in ("prima", "dopo")}
            rec["tool"] = [{k: v for k, v in ev.items() if k != "argomenti"}
                           for ev in rec.get("tool") or []]
        day = (rec.get("inizio") or datetime.datetime.now().isoformat())[:10]
        line = json.dumps(rec, ensure_ascii=False, default=str)
        with self._lock, open(self.folder / f"{self.PREFIX}{day}.jsonl", "a",
                              encoding="utf-8") as f:
            f.write(line + "\n")


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
