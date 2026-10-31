"""
I metodi di `Studio` per la libreria (31/10, issue #297, epic #251, decisione 0035 punto 46).

- `proposte_libreria`: i contenuti scelti dal codice per una verifica (`indice.scegli`), coi mazzi
  già aggiunti segnati; la padronanza conta solo se «mostrata»;
- `scheda_libreria` e `soluzione_libreria`: una scheda da leggere sullo schermo, le soluzioni di
  «prova tu» una per volta, solo a richiesta (mai nella risposta della scheda);
- `aggiungi_mazzo`: le carte di un mazzo fra quelle della verifica, legate all'argomento, origine
  «libreria», attive e da ripassare subito; una domanda che c'è già non si riscrive;
- `_libreria_home`: la sezione «Dalla libreria» della home, o in ombra solo i conti nel registro.

Con una prova aperta sulla verifica la libreria non c'è per nessuno (come il ripasso da
ascoltare): schede e carte possono avere le risposte delle domande. I contenuti sono dati fidati
(scritti e rivisti da noi): i titoli possono andare alla voce, i titoli degli argomenti della
persona no (sono dati delle pagine).

Interruttore `studio_libreria`: «attiva» (di serie con lo Studio), «ombra» (si calcola e si
contano le proposte nel registro, senza nomi né titoli), «spenta».
"""

from __future__ import annotations

from . import formato as F
from . import indice as I

SPENTA, OMBRA, ATTIVA = "spenta", "ombra", "attiva"
MODI = (SPENTA, OMBRA, ATTIVA)
# Le schede che si possono aprire: tutte quelle della libreria (anche i prerequisiti fuori dalle
# proposte), perché sono materiale fidato e pubblico; con una prova aperta nessuna
CON_PROVA = "c'è una prova aperta su questa verifica: la libreria torna dopo la consegna"


def modo(cfg) -> str:
    m = str(getattr(cfg, "studio_libreria", ATTIVA) or ATTIVA).strip().lower()
    return m if m in MODI else ATTIVA


class DallaLibreria:
    """La libreria nello Studio (mixin di `servizio.Studio`)."""

    _libreria_caricata: I.Libreria | None = None

    def libreria_modo(self) -> str:
        return modo(self.cfg)

    def libreria(self) -> I.Libreria:
        """La libreria, caricata una volta per processo (i file sono nel repository)."""
        if self._libreria_caricata is None:
            self._libreria_caricata = I.Libreria.carica(log=self.log)
        return self._libreria_caricata

    def _misure_libreria(self) -> dict:
        return self.misure.setdefault("libreria", {"proposte": 0, "ombra": 0, "schede": 0,
                                                    "soluzioni": 0, "mazzi": 0, "carte": 0,
                                                    "senza": 0, "attivita": 0})

    def prova_aperta_di(self, chi) -> bool:
        """`chi` (un profilo o l'id della persona) ha una prova aperta su una sua verifica,
        qualsiasi: le attività della libreria aspettano la consegna, come le carte (revisione
        della PR #366, nota 1: anche su un'altra verifica)."""
        pid = chi if isinstance(chi, str) else str(getattr(chi, "id", "") or "")
        try:
            return self.dati.uno(
                "SELECT p.id FROM studio_prove p JOIN studio_verifiche v ON v.id = p.verifica "
                "WHERE v.persona = ? AND p.stato = 'aperta' AND v.stato IN ('bozza', 'aperta')",
                (pid,)) is not None
        except Exception:  # noqa: BLE001 — una tabella che manca (schema di prima): niente prove
            return False

    def nota_attivita(self, cid: str):
        """Un'attività della libreria aperta: solo il conto e l'id (della libreria, non della
        persona) nel registro."""
        self._misure_libreria()["attivita"] += 1
        self._registra(f"libreria: attività {cid} aperta")

    def _libreria_chiusa(self, v: dict) -> bool:
        """Con una prova aperta la libreria non c'è, per nessuno."""
        try:
            return self._prova_aperta(v["id"]) is not None
        except Exception:  # noqa: BLE001 — una tabella che manca (schema di prima): niente prove
            return False

    def _chiavi_carte(self, vid) -> set:
        from ..argomenti import chiave
        return {chiave(r["domanda"]) for r in self.dati.tutti(
            "SELECT domanda FROM studio_carte WHERE verifica = ? AND stato != 'ombra'",
            (int(vid),))}

    def _proposte(self, v: dict) -> list[dict]:
        """Le proposte per la verifica `v` (già col permesso controllato), coi mazzi annotati."""
        lib = self.libreria()
        args = self._argomenti_numerati(v["id"])
        if not args and v.get("argomento"):
            # Senza argomenti confermati: l'argomento generale della verifica
            args = [{"id": None, "numero": None, "titolo": v["argomento"]}]
        pad = None
        if self.padronanza_mostrata():
            pad = {a["id"]: a["valore"] for a in self._padronanza(v)["argomenti"]}
        out = I.scegli(lib, args, v["materia"], pad, int(v["obiettivo"] or 75))
        for p in out:
            if p["tipo"] == F.MINIAPP:
                p["tipo_app"] = lib.contenuti[p["contenuto"]]["tipo_app"]
        if any(p["tipo"] == F.MAZZO for p in out):
            from ..argomenti import chiave
            ci_sono = self._chiavi_carte(v["id"])
            for p in out:
                if p["tipo"] == F.MAZZO:
                    dom = [chiave(c["domanda"]) for c in lib.contenuti[p["contenuto"]]["carte"]]
                    p["carte"] = len(dom)
                    p["aggiunte"] = sum(d in ci_sono for d in dom)
                    p["aggiunto"] = p["aggiunte"] == len(dom)
        return out

    def proposte_libreria(self, chi, vid) -> dict:
        """I contenuti della libreria per una verifica, scelti dal codice: {verifica, modo,
        proposte, materie, chiusa}. Permessi come il resto dello Studio (`NonTrovata`)."""
        v = self._verifica(chi, vid)
        m = self.libreria_modo()
        chiusa = self._libreria_chiusa(v)
        prop = [] if m == SPENTA or chiusa else self._proposte(v)
        self._misure_libreria()["proposte"] += 1
        return {"verifica": v["id"], "materia": v["materia"], "modo": m,
                "proposte": prop if m == ATTIVA else [], "materie": self.libreria().materie(),
                "chiusa": CON_PROVA if chiusa else None}

    def _libreria_home(self, chi, v: dict) -> list[dict] | None:
        """La sezione «Dalla libreria» della home: le proposte in attivo; in ombra solo i conti
        nel registro (una riga per verifica e giorno, se cambiano), None."""
        m = self.libreria_modo()
        if m == SPENTA or self._libreria_chiusa(v):
            return None
        try:
            prop = self._proposte(v)
        except Exception as ex:  # noqa: BLE001 — la libreria non ferma la home
            self.log(f"   [STUDIO] libreria della verifica {v['id']}: {type(ex).__name__}")
            return None
        if m == OMBRA:
            conti = {}
            for p in prop:
                conti[p["tipo"]] = conti.get(p["tipo"], 0) + 1
            firma = (v["id"], self._oggi().isoformat(), tuple(sorted(conti.items())))
            visti = self.__dict__.setdefault("_libreria_ombra", set())
            if firma not in visti:
                visti.add(firma)
                self._misure_libreria()["ombra"] += 1
                if not prop:
                    self._misure_libreria()["senza"] += 1
                self._registra(f"libreria della verifica {v['id']} (ombra): {len(prop)} proposte"
                               + "".join(f", {t} {n}" for t, n in sorted(conti.items())))
            return None
        return prop

    def _scheda_di(self, chi, vid, sid) -> tuple[dict, dict]:
        from ..servizio import NonTrovata
        v = self._verifica(chi, vid)
        if self.libreria_modo() != ATTIVA or self._libreria_chiusa(v):
            raise NonTrovata()
        s = self.libreria().get(sid)
        if s is None or s["tipo"] != F.SCHEDA:
            raise NonTrovata()
        return v, s

    def scheda_libreria(self, chi, vid, sid) -> dict:
        """Una scheda della libreria da leggere: i metadati, le parti, i prerequisiti col titolo,
        i mazzi della scheda; di «prova tu» solo le domande (le soluzioni con
        `soluzione_libreria`)."""
        _v, s = self._scheda_di(chi, vid, sid)
        lib = self.libreria()
        sc = s["scheda"]
        self._misure_libreria()["schede"] += 1
        return {"id": s["id"], "titolo": s["titolo"], "materia": s["materia"],
                "classe": dict(s["classe"]), "argomento": s["argomento"], "durata": s["durata"],
                "introduzione": sc["introduzione"],
                "sezioni": [dict(x) for x in sc["sezioni"]],
                "ricorda": list(sc["ricorda"]),
                "esempi": [x["testo"] for x in sc.get("esempi", [])],
                "errori": list(sc.get("errori", [])),
                "prova_tu": [{"n": i, "domanda": x["domanda"]}
                             for i, x in enumerate(sc.get("prova_tu", []), 1)],
                "prerequisiti": [{"id": p, "titolo": lib.contenuti[p]["titolo"]}
                                 for p in s["prerequisiti"] if p in lib.contenuti],
                "mazzi": [{"id": x["id"], "titolo": x["titolo"], "carte": len(x["carte"])}
                          for x in lib.di_scheda(s["id"]) if x["tipo"] == F.MAZZO],
                # Le mini-app della scheda (parte 2): si aprono col tocco «studio_attivita»
                "attivita": [{"id": x["id"], "titolo": x["titolo"], "tipo_app": x["tipo_app"],
                              "durata": x["durata"]}
                             for x in lib.di_scheda(s["id"])
                             if x["tipo"] == F.MINIAPP and x["id"] in lib.app]}

    def soluzione_libreria(self, chi, vid, sid, n) -> dict:
        """La soluzione della domanda `n` (da 1) di «prova tu» di una scheda."""
        from ..servizio import NonTrovata
        _v, s = self._scheda_di(chi, vid, sid)
        pt = s["scheda"].get("prova_tu", [])
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= len(pt):
            raise NonTrovata()
        self._misure_libreria()["soluzioni"] += 1
        return {"scheda": s["id"], "n": n, "risposta": pt[n - 1]["risposta"]}

    def aggiungi_mazzo(self, chi, vid, mid, argomento=None) -> dict:
        """Le carte di un mazzo della libreria fra quelle della verifica: origine «libreria»,
        attive e da ripassare subito, legate all'argomento (`argomento`, della verifica; senza,
        quello della proposta, se c'è). Una domanda che c'è già si salta; il tetto delle carte
        vale. {aggiunte, gia, fuori}."""
        from .. import carte as C
        from ..argomenti import chiave
        from ..servizio import NonTrovata, VerificaChiusa
        self._scrivibile()
        v = self._verifica(chi, vid)
        if self.libreria_modo() != ATTIVA:
            raise NonTrovata()
        if v["stato"] not in ("bozza", "aperta"):
            raise VerificaChiusa()
        if self._libreria_chiusa(v):
            raise ValueError(CON_PROVA)
        mz = self.libreria().get(mid)
        if mz is None or mz["tipo"] != F.MAZZO:
            raise NonTrovata()
        if argomento is None:
            p = next((x for x in self._proposte(v) if x["contenuto"] == mz["id"]), None)
            aid = p["argomento"] if p else None
        else:
            aid = self._argomento_di(v, argomento)
        adesso = self.adesso().isoformat(timespec="seconds")
        n = gia = fuori = 0
        with self.dati.lock:
            db = self.dati.db
            try:
                if db.in_transaction:
                    db.commit()
                db.execute("BEGIN IMMEDIATE")
                # Dentro la transazione: la verifica è ancora aperta e le domande sono quelle di
                # adesso (un doppio tocco non scrive due volte)
                ok = db.execute("SELECT stato FROM studio_verifiche WHERE id = ?",
                                (v["id"],)).fetchone()
                if ok is None or ok[0] not in ("bozza", "aperta"):
                    db.rollback()
                    raise VerificaChiusa()
                ci_sono = {chiave(r[0]) for r in db.execute(
                    "SELECT domanda FROM studio_carte WHERE verifica = ? AND stato != 'ombra'",
                    (v["id"],))}
                tot = db.execute("SELECT COUNT(*) FROM studio_carte WHERE verifica = ? AND "
                                 "stato != 'ombra'", (v["id"],)).fetchone()[0]
                for c in mz["carte"]:
                    k = chiave(c["domanda"])
                    if k in ci_sono:
                        gia += 1
                        continue
                    if tot + n >= C.CARTE_MAX:
                        fuori += 1
                        continue
                    d = C.testo_normale(c["domanda"], C.DOMANDA_MAX)
                    r = C.testo_normale(c["risposta"], C.RISPOSTA_MAX)
                    db.execute(
                        "INSERT INTO studio_carte (verifica, persona, argomento, domanda, "
                        "risposta, chiusa, pagine, origine, stato, avvisi, scatola, scadenza, "
                        "creata, creata_da) VALUES (?, ?, ?, ?, ?, ?, '[]', 'libreria', 'attiva', "
                        "NULL, 1, ?, ?, ?)",
                        (v["id"], str(v["persona"]), aid, d, r, C.chiusa(r), adesso, adesso,
                         getattr(chi, "id", None)))
                    ci_sono.add(k)
                    n += 1
                db.commit()
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
        mis = self._misure_libreria()
        mis["mazzi"] += 1
        mis["carte"] += n
        self.misure["carte"]["scritte"] += n
        self._registra(f"verifica {v['id']}: {n} carte dalla libreria, {gia} c'erano già"
                       + (f", {fuori} oltre il tetto" if fuori else "")
                       + f" ({self._chi_registro(chi, v['persona'])})")
        return {"aggiunte": n, "gia": gia, "fuori": fuori}
