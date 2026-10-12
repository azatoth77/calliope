"""
Il registro degli esercizi (08/10/2026), nel file della memoria (`memoria.db`), schema
versionato (`persistenza.prepara_schema`, modulo «esercizi»):

- `esercizi_tentativi`: ogni risposta, aiuto, salto o soluzione, con la domanda, la risposta
  attesa e quella data (normalizzata, al più 60 caratteri), l'esito, i suggerimenti usati, i
  secondi e il canale (voce o scheda). È il dettaglio che vedono i tutori (decisione del 07/10:
  anche per gli adolescenti, che lo sanno);
- `esercizi_segnalazioni`: «secondo me è sbagliato» del ragazzo, con il ricontrollo;
- `esercizi_banco`: gli esercizi d'italiano già controllati (Wikizionario e secondo modello),
  per firma: buoni (si riusano) o scartati (non si propongono più);
- `esercizi_preferenze` (12/10): come vuole gli esercizi ogni persona (blocchi più corti, modo
  giocoso, punti, tappe), così valgono anche in una conversazione nuova. Scadono come i
  tentativi (`conserva.TABELLE_MEMORIA`, 60 giorni dall'ultimo cambio) e si svuotano con la
  persona;
- `esercizi_punto` (12/10 sera): «a che punto siete» per persona e materia (argomento, entro,
  con o senza cambio, detti dal codice dopo che il modello ha interpretato la risposta) e la
  classe (materia «_classe», con l'anno scolastico), con la data: dopo
  `esercizi_punto_giorni` (14) Calliope lo richiede. Stessa scadenza e stesso svuotamento delle
  preferenze.

Nel registro dei turni e negli avvisi vanno solo materia e argomento, mai le risposte.
"""

from __future__ import annotations

import datetime
import json
import random
import threading

from .modello import Esercizio


# Gli esiti che chiudono un esercizio (le domande aperte delle interrogazioni, 12/10 sera:
# parziale, non_giusta e da_guardare, cioè il modello non era sicuro del giudizio)
FINALI = ("giusta", "spiegato", "saltato", "scartato", "parziale", "non_giusta", "da_guardare")


class Registro:
    def __init__(self, path: str):
        from ..persistenza import apri_db, prepara_schema
        self._lock = threading.Lock()
        self.db = apri_db(path)

        def v1(db):
            db.execute("CREATE TABLE IF NOT EXISTS esercizi_tentativi (id INTEGER PRIMARY KEY, "
                       "persona TEXT NOT NULL, giorno TEXT NOT NULL, quando TEXT NOT NULL, "
                       "sessione TEXT, materia TEXT NOT NULL, argomento TEXT NOT NULL, "
                       "classe TEXT, livello INTEGER, esercizio TEXT NOT NULL, domanda TEXT, "
                       "attesa TEXT, data TEXT, esito TEXT NOT NULL, suggerimenti INTEGER "
                       "NOT NULL DEFAULT 0, secondi REAL, canale TEXT)")
            db.execute("CREATE INDEX IF NOT EXISTS esercizi_tentativi_pg ON "
                       "esercizi_tentativi(persona, giorno)")
            db.execute("CREATE TABLE IF NOT EXISTS esercizi_segnalazioni (id INTEGER PRIMARY "
                       "KEY, persona TEXT NOT NULL, quando TEXT NOT NULL, esercizio TEXT NOT "
                       "NULL, materia TEXT, argomento TEXT, domanda TEXT, attesa TEXT, data "
                       "TEXT, nota TEXT, ricontrollo TEXT, esito TEXT, visto TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS esercizi_banco (firma TEXT PRIMARY KEY, "
                       "materia TEXT NOT NULL, argomento TEXT NOT NULL, livello INTEGER, "
                       "dati TEXT NOT NULL, verifica TEXT, stato TEXT NOT NULL, creato TEXT "
                       "NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS esercizi_banco_al ON "
                       "esercizi_banco(argomento, livello, stato)")
        def v2(db):
            db.execute("CREATE TABLE IF NOT EXISTS esercizi_preferenze (persona TEXT PRIMARY "
                       "KEY, dati TEXT NOT NULL, aggiornato TEXT NOT NULL)")
        def v3(db):
            db.execute("CREATE TABLE IF NOT EXISTS esercizi_punto (persona TEXT NOT NULL, "
                       "materia TEXT NOT NULL, dati TEXT NOT NULL, aggiornato TEXT NOT NULL, "
                       "PRIMARY KEY (persona, materia))")
        self.scrivibile = prepara_schema(self.db, "esercizi", [v1, v2, v3])

    # ── preferenze per persona (12/10) ──
    def preferenze(self, persona: str) -> dict:
        with self._lock:
            r = self.db.execute("SELECT dati FROM esercizi_preferenze WHERE persona = ?",
                                (persona,)).fetchone()
        try:
            return dict(json.loads(r[0])) if r else {}
        except (TypeError, ValueError):
            return {}

    def salva_preferenze(self, persona: str, dati: dict):
        with self._lock:
            self.db.execute(
                "INSERT INTO esercizi_preferenze (persona, dati, aggiornato) VALUES (?, ?, ?) "
                "ON CONFLICT(persona) DO UPDATE SET dati = excluded.dati, "
                "aggiornato = excluded.aggiornato",
                (persona, json.dumps(dati, ensure_ascii=False),
                 datetime.date.today().isoformat()))
            self.db.commit()

    # ── a che punto siete (12/10 sera) ──
    def punto(self, persona: str, materia: str) -> dict | None:
        """{"dati": {...}, "aggiornato": date} o None."""
        with self._lock:
            r = self.db.execute("SELECT dati, aggiornato FROM esercizi_punto WHERE persona = ? "
                                "AND materia = ?", (persona, materia)).fetchone()
        if not r:
            return None
        try:
            return {"dati": dict(json.loads(r[0])),
                    "aggiornato": datetime.date.fromisoformat(r[1][:10])}
        except (TypeError, ValueError):
            return None

    def salva_punto(self, persona: str, materia: str, dati: dict,
                    giorno: datetime.date | None = None):
        with self._lock:
            self.db.execute(
                "INSERT INTO esercizi_punto (persona, materia, dati, aggiornato) VALUES "
                "(?, ?, ?, ?) ON CONFLICT(persona, materia) DO UPDATE SET dati = excluded.dati, "
                "aggiornato = excluded.aggiornato",
                (persona, materia, json.dumps(dati, ensure_ascii=False),
                 (giorno or datetime.date.today()).isoformat()))
            self.db.commit()

    # ── tentativi ──
    def tentativo(self, persona: str, sessione: str, es: Esercizio, classe: str, esito: str,
                  data: str = "", suggerimenti: int = 0, secondi: float | None = None,
                  canale: str = "voce"):
        adesso = datetime.datetime.now()
        with self._lock:
            self.db.execute(
                "INSERT INTO esercizi_tentativi (persona, giorno, quando, sessione, materia, "
                "argomento, classe, livello, esercizio, domanda, attesa, data, esito, "
                "suggerimenti, secondi, canale) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "?, ?, ?)",
                (persona, adesso.date().isoformat(), adesso.isoformat(timespec="seconds"),
                 sessione, es.materia, es.argomento, classe, es.livello, es.firma,
                 es.testo[:300], str(es.risposta_detta)[:80], str(data or "")[:60], esito,
                 int(suggerimenti), None if secondi is None else round(float(secondi), 1),
                 canale))
            self.db.commit()

    def tentativi(self, persona: str, dal: datetime.date | None = None,
                  al: datetime.date | None = None) -> list[dict]:
        dal = (dal or datetime.date.today()).isoformat()
        al = (al or datetime.date.today()).isoformat()
        with self._lock:
            rows = self.db.execute(
                "SELECT quando, materia, argomento, classe, livello, esercizio, domanda, attesa, "
                "data, esito, suggerimenti, secondi, canale FROM esercizi_tentativi WHERE "
                "persona = ? AND giorno BETWEEN ? AND ? ORDER BY id", (persona, dal, al)
            ).fetchall()
        k = ("quando", "materia", "argomento", "classe", "livello", "esercizio", "domanda",
             "attesa", "data", "esito", "suggerimenti", "secondi", "canale")
        return [dict(zip(k, r)) for r in rows]

    def fatti_di_recente(self, persona: str, giorni: int = 14) -> set[str]:
        """Le firme degli esercizi risolti di recente: non si ripropongono subito."""
        dal = (datetime.date.today() - datetime.timedelta(days=giorni)).isoformat()
        with self._lock:
            rows = self.db.execute("SELECT DISTINCT esercizio FROM esercizi_tentativi WHERE "
                                   "persona = ? AND giorno >= ? AND esito = 'giusta'",
                                   (persona, dal)).fetchall()
        return {r[0] for r in rows}

    # ── segnalazioni ──
    def segnala(self, persona: str, es: Esercizio, data: str, nota: str, ricontrollo: dict,
                esito: str) -> int:
        with self._lock:
            cur = self.db.execute(
                "INSERT INTO esercizi_segnalazioni (persona, quando, esercizio, materia, "
                "argomento, domanda, attesa, data, nota, ricontrollo, esito) VALUES (?, ?, ?, "
                "?, ?, ?, ?, ?, ?, ?, ?)",
                (persona, datetime.datetime.now().isoformat(timespec="seconds"), es.firma,
                 es.materia, es.argomento, es.testo[:300], str(es.risposta_detta)[:80],
                 str(data or "")[:60], str(nota or "")[:200],
                 json.dumps(ricontrollo, ensure_ascii=False, default=str), esito))
            self.db.commit()
            return int(cur.lastrowid)

    def segnalazioni(self, persona: str | None = None, solo_nuove: bool = False) -> list[dict]:
        q = ("SELECT id, persona, quando, materia, argomento, domanda, attesa, data, nota, "
             "esito FROM esercizi_segnalazioni WHERE 1=1")
        args: list = []
        if persona:
            q += " AND persona = ?"
            args.append(persona)
        if solo_nuove:
            q += " AND visto IS NULL"
        with self._lock:
            rows = self.db.execute(q + " ORDER BY id", args).fetchall()
        k = ("id", "persona", "quando", "materia", "argomento", "domanda", "attesa", "data",
             "nota", "esito")
        return [dict(zip(k, r)) for r in rows]

    # ── banco degli esercizi controllati ──
    def banco_leggi(self, firma: str) -> tuple[str, dict] | None:
        with self._lock:
            r = self.db.execute("SELECT stato, verifica FROM esercizi_banco WHERE firma = ?",
                                (firma,)).fetchone()
        if not r:
            return None
        try:
            return r[0], json.loads(r[1] or "{}")
        except ValueError:
            return r[0], {}

    def banco_scrivi(self, es: Esercizio, stato: str, verifica: dict):
        with self._lock:
            self.db.execute(
                "INSERT INTO esercizi_banco (firma, materia, argomento, livello, dati, verifica, "
                "stato, creato) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(firma) DO UPDATE SET "
                "stato = excluded.stato, verifica = excluded.verifica",
                (es.firma, es.materia, es.argomento, es.livello,
                 json.dumps(es.a_dict(), ensure_ascii=False, default=str),
                 json.dumps(verifica, ensure_ascii=False, default=str), stato,
                 datetime.datetime.now().isoformat(timespec="seconds")))
            self.db.commit()

    def banco_buoni(self, argomento: str, livello: int, escludi: set[str],
                    n: int = 20) -> list[Esercizio]:
        with self._lock:
            rows = self.db.execute("SELECT firma, dati FROM esercizi_banco WHERE argomento = ? "
                                   "AND livello = ? AND stato = 'buono' ORDER BY random() "
                                   "LIMIT ?", (argomento, livello, n + len(escludi))).fetchall()
        out = []
        for firma, dati in rows:
            if firma in escludi:
                continue
            try:
                out.append(Esercizio.da_dict(json.loads(dati)))
            except (TypeError, ValueError):
                continue
        return out[:n]

    def banco_conta(self) -> dict:
        with self._lock:
            rows = self.db.execute("SELECT stato, COUNT(*) FROM esercizi_banco GROUP BY stato"
                                   ).fetchall()
        return {r[0]: r[1] for r in rows}

    # ── riepilogo per i tutori ──
    def riepilogo(self, persona: str, nome: str, dal: datetime.date | None = None,
                  al: datetime.date | None = None, campione: int = 3,
                  rng: random.Random | None = None) -> dict:
        """{"frase": per la voce, "righe": dettaglio per la scheda, "campione": esercizi da
        guardare, "segnalazioni": […], "secondi": tempo di studio}."""
        t = self.tentativi(persona, dal, al)
        oggi = (dal or datetime.date.today()) == (al or datetime.date.today()) == datetime.date.today()
        quando = "Oggi" if oggi else "In questi giorni"
        risposte = [x for x in t if x["esito"] in ("giusta", "sbagliata")]
        esercizi: dict[str, dict] = {}
        for x in t:
            e = esercizi.setdefault(x["esercizio"], {"materia": x["materia"],
                                                     "argomento": x["argomento"],
                                                     "esito": None, "errori": 0, **x})
            if x["esito"] == "sbagliata":
                e["errori"] += 1
            if x["esito"] in FINALI:
                e["esito"] = x["esito"]
        per_arg: dict[tuple, list] = {}
        for e in esercizi.values():
            if e["esito"] is None and not e["errori"]:
                continue
            per_arg.setdefault((e["materia"], e["argomento"]), []).append(e)
        secondi = sum(float(x["secondi"] or 0) for x in t)
        seg = [s for s in self.segnalazioni(persona)
               if (dal or datetime.date.today()).isoformat() <= s["quando"][:10]
               <= (al or datetime.date.today()).isoformat()]
        if not per_arg:
            return {"frase": f"{quando} {nome} non ha fatto esercizi con me.", "righe": [],
                    "campione": [], "segnalazioni": seg, "secondi": 0}
        parti = []
        from . import nome_argomento
        for (mat, arg), lst in per_arg.items():
            giuste = sum(1 for e in lst if e["esito"] == "giusta")
            primo = sum(1 for e in lst if e["esito"] == "giusta" and not e["errori"])
            spiegati = sum(1 for e in lst if e["esito"] == "spiegato")
            guardare = sum(1 for e in lst if e["esito"] == "da_guardare")
            s = f"{nome_argomento(arg)}: {giuste} giusti su {len(lst)}"
            if primo and primo != giuste:
                s += f" ({primo} al primo colpo)"
            if spiegati:
                s += f", {spiegati} spiegat{'o' if spiegati == 1 else 'i'} dopo i tentativi"
            if guardare:
                s += f", {guardare} da guardare tu"
            parti.append(s)
        n = sum(len(v) for v in per_arg.values())
        minuti = round(secondi / 60)
        frase = (f"{quando} {nome} ha fatto {n} esercizi" + (f" in circa {minuti} minuti"
                                                             if minuti >= 2 else "")
                 + ": " + "; ".join(parti) + ".")
        if seg:
            frase += (f" Ha segnalato {len(seg)} esercizi" if len(seg) > 1 else
                      " Ha segnalato un esercizio") + " come sbagliati: li trovi sullo schermo."
        da_guardare = [e for e in esercizi.values() if e["esito"] == "da_guardare"]
        if da_guardare:
            frase += (" Una risposta aperta è da guardare tu" if len(da_guardare) == 1 else
                      f" {len(da_guardare)} risposte aperte sono da guardare tu") + (
                ": non ero sicura del giudizio, le trovi sullo schermo.")
        rng = rng or random.Random()
        visti = [e for e in esercizi.values() if e["esito"] != "da_guardare"]
        cam = da_guardare + rng.sample(visti, min(max(0, campione - len(da_guardare)),
                                                  len(visti)))
        righe = [{"quando": x["quando"][11:16], "argomento": nome_argomento(x["argomento"]),
                  "domanda": x["domanda"], "attesa": x["attesa"], "data": x["data"],
                  "esito": x["esito"], "canale": x["canale"]} for x in t]
        return {"frase": frase, "righe": righe,
                "campione": [{"domanda": c["domanda"], "attesa": c["attesa"],
                              **({"data": c["data"], "da_guardare": True}
                                 if c["esito"] == "da_guardare" else {})} for c in cam],
                "segnalazioni": seg, "secondi": secondi, "risposte": len(risposte)}

    def close(self):
        try:
            self.db.close()
        except Exception:  # noqa: BLE001
            pass
