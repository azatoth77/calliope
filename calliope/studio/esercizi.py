"""
Gli esercizi guidati dello Studio (31/10, issue #278, epic #251, decisione 0035: i compiti
guidati, mai la soluzione intera; l'esito lo decide solo il codice). Un mixin di `Studio`
(`servizio.py`), come le prove e le mappe.

**Un esercizio** è un problema portato dalla persona dentro una sua verifica: una foto («Foto di
un problema», dallo stesso `POST /api/studio/pagina` con `esercizio: true`) o il testo scritto
(`POST /api/studio/esercizio`). Il testo è un **dato non fidato**: la foto la legge il lettore
delle pagine (`lettura.Lettore.leggi_esercizio`, stessa guardia e stesso harness OCR), poi lo
stesso thread chiede la guida a passi (`esercizi_genera.py`, controllata dal codice).

**Gli stati**: «da_leggere» → «in_lettura» → «letto» (la foto letta o il testo scritto) →
«pronto» (la guida c'è) o «senza_guida» (meno di 2 passi buoni) o «illeggibile»; la persona lo
comincia («in_corso»), lo lascia («pausa») e lo finisce («finito»).

**I passi.** Uno alla volta, nell'ordine. La risposta della persona (a voce dalla sua frase, mai
da un argomento del modello; sullo schermo dal campo) la valuta `risposte.valuta`:
- «giusto»: il passo dopo; dopo l'ultimo l'esercizio è finito (il risultato l'ha trovato lei);
- «indizio» (il numero giusto senza l'unità): resta sul passo e lo dice;
- «sbagliato»: resta sul passo; dopo `INDIZIO_DOPO` errori il codice propone l'indizio, dopo
  `SALTA_DOPO` anche di saltare. **La risposta attesa non si dice mai**;
- «da rivedere» (un passo aperto, o una risposta che il codice non sa controllare): avanti, col
  segno «da rivedere» per chi lo guarda dopo.
Niente tentativi della padronanza né stelle: una misura nuova, da guardare prima di contarla.

**Chi**: risponde solo la persona dell'esercizio; il tutore lo vede (testo, passi, esiti, avvisi;
le risposte attese solo a esercizio finito) e lo può togliere. **Una prova aperta** sulla verifica
ferma la guida dei suoi esercizi (`GuidaFerma`). **L'interruttore** `studio_esercizi`: «spenta»,
«ombra» (di serie: solo chi amministra, per provarlo) o «attiva».
"""

from __future__ import annotations

import datetime
import json

from . import dati as D
from . import esercizi_genera as EG
from . import risposte as RS

# Al più tanti esercizi non finiti per verifica
ESERCIZI_MAX = 30
# Dopo tanti errori sullo stesso passo il codice propone l'indizio, poi di saltare
INDIZIO_DOPO = 2
SALTA_DOPO = 3
# Il tetto dei tentativi su un passo (revisione della PR #367): oltre, il codice non valuta più
# risposte su quel passo, restano l'indizio e «salta» (niente indovinare a tentativi)
ERRORI_MAX = 6
# Un esercizio vivo («in_corso», «pausa» o «pronto», non finito né tolto) vale per la guardia
# della voce fino a tanto tempo dall'ultima modifica (revisione della PR #367: dopo «basta» la
# guardia si spegneva, e il turno dopo «quanto faceva?» aveva la soluzione)
VIVO_S = 24 * 3600
VIVI = ("in_corso", "pausa", "pronto")
STATI = ("da_leggere", "in_lettura", "letto", "pronto", "senza_guida", "illeggibile",
         "in_corso", "pausa", "finito")
APERTI = ("da_leggere", "in_lettura", "letto", "pronto", "in_corso", "pausa")
# Le frasi del codice
FRASE_FERMA = "C'è una prova aperta su questa verifica: gli esercizi guidati tornano dopo la consegna."
FRASE_SVELATO = ("Questo lo scopri tu, un passo alla volta: dimmi la tua risposta al passo che "
                 "stiamo facendo.")


class EserciziSpenti(LookupError):
    """Gli esercizi guidati non ci sono per chi chiede (spenti, o in ombra e non amministra)."""


class GuidaFerma(ValueError):
    """Una prova aperta sulla verifica: niente guida finché non si consegna."""

    def __init__(self, frase: str = FRASE_FERMA):
        super().__init__(frase)
        self.frase = frase


def _ora(adesso) -> str:
    return adesso.isoformat(timespec="seconds")


class Esercizi:
    """I metodi degli esercizi guidati (mixin di `Studio`)."""

    # ── permessi e stato ──
    def esercizi_modo(self) -> str:
        return EG.modo(self.cfg)

    def esercizi_per(self, chi) -> bool:
        """Gli esercizi guidati ci sono per `chi`: «attiva», o «ombra» e chi amministra."""
        m = self.esercizi_modo()
        return m == EG.ATTIVA or (m == EG.OMBRA and bool(getattr(chi, "admin", False)))

    def _es_acceso(self, chi):
        if not self.esercizi_per(chi):
            raise EserciziSpenti()

    def _riga_es(self, eid) -> dict | None:
        r = self.dati.uno("SELECT * FROM studio_esercizi WHERE id = ?", (int(eid),))
        if r is None:
            return None
        r["avvisi"] = D.da_j(r.get("avvisi"))
        r["esiti"] = D.da_j(r.get("esiti"))
        try:
            p = json.loads(r.get("passi") or "[]")
        except ValueError:
            p = []
        r["passi"] = [x for x in p if isinstance(x, dict)] if isinstance(p, list) else []
        return r

    def _esercizio(self, chi, eid) -> tuple[dict, dict, str]:
        """(esercizio, verifica, ruolo): l'esercizio di `chi` o del suo minore; NonTrovata per
        uno di un altro (lo stesso rifiuto di uno che non c'è)."""
        from .servizio import NonTrovata
        e = self._riga_es(eid)
        if e is None:
            raise NonTrovata()
        v = self._verifica(chi, e["verifica"])
        return e, v, self._chi_puo(chi, v["persona"])

    def prova_della_persona(self, persona) -> bool:
        """La persona ha una prova aperta su una sua verifica, qualsiasi (revisione della PR #367,
        la regola delle mini-app: anche su un'altra verifica la guida aspetta la consegna). Le
        prove scadute per il tempo si chiudono qui (`_prova_aperta`)."""
        try:
            vv = [r["verifica"] for r in self.dati.tutti(
                "SELECT DISTINCT p.verifica FROM studio_prove p JOIN studio_verifiche v ON "
                "v.id = p.verifica WHERE v.persona = ? AND p.stato = 'aperta'", (str(persona),))]
        except Exception:  # noqa: BLE001 — una tabella che manca (schema di prima): niente prove
            return False
        return any(self._prova_aperta(vid) for vid in vv)

    def _guida_ferma(self, v: dict):
        """Una prova aperta della persona, su qualsiasi sua verifica, ferma la guida (anche per
        il tutore)."""
        if self.prova_della_persona(v["persona"]):
            raise GuidaFerma()

    # ── arrivare ──
    def aggiungi_esercizio(self, chi, vid, testo=None, jpeg: bytes | None = None,
                           avvisi=()) -> dict:
        """Un esercizio nuovo nella verifica: il testo scritto (stato «letto») o la foto già
        controllata dal server (`pagine.prepara_foto`, stato «da_leggere»). La persona o il suo
        tutore, verifica in bozza o aperta, al più `ESERCIZI_MAX` non finiti."""
        from . import pagine as PG
        self._es_acceso(chi)
        self._scrivibile()
        if jpeg is None:
            testo = EG.testo_pulito(testo)
            if len(testo) < 5:
                raise ValueError("scrivi il testo del problema")
        cartella = D.cartella_di(self.cfg)
        scritto = None
        with self.dati.lock:
            v = self.verifica_per_pagine(chi, vid)
            # Con una prova aperta niente esercizi nuovi (la guida aspetta la consegna)
            self._guida_ferma(v)
            n = self.dati.db.execute(
                "SELECT COUNT(*) FROM studio_esercizi WHERE verifica = ? AND stato IN (" +
                ",".join("?" * len(APERTI)) + ")", (v["id"], *APERTI)).fetchone()[0]
            if n >= ESERCIZI_MAX:
                raise ValueError(f"al più {ESERCIZI_MAX} esercizi aperti per verifica")
            if jpeg is not None:
                scritto = PG.scrivi_file(cartella, v["id"], jpeg, "jpg")
            try:
                eid = self.dati.db.execute(
                    "INSERT INTO studio_esercizi (verifica, persona, origine, file, testo, stato, "
                    "avvisi, creato, creato_da) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (v["id"], v["persona"], "foto" if jpeg is not None else "scritto", scritto,
                     None if jpeg is not None else testo,
                     "da_leggere" if jpeg is not None else "letto", D.j(avvisi), D.adesso(),
                     str(getattr(chi, "id", "")))).lastrowid
                self.dati.db.commit()
            except Exception:
                if self.dati.db.in_transaction:
                    self.dati.db.rollback()
                if scritto:
                    D.togli_file([scritto], cartella)
                raise
        self.misure["esercizi"] = self.misure.get("esercizi", 0) + 1
        self._registra(f"verifica {v['id']}: esercizio {eid} arrivato "
                       f"({'foto' if jpeg is not None else 'scritto'}, "
                       f"{self._chi_registro(chi, v['persona'])})")
        if self.lettore is not None:
            self.lettore.sveglia()
        return {"esercizio": eid, "verifica": v["id"]}

    # ── per il lettore ──
    def esercizi_da_leggere(self) -> list[dict]:
        """Le foto degli esercizi da leggere (le più vecchie prima), se gli esercizi non sono
        spenti e la verifica è ancora viva."""
        if self.esercizi_modo() == EG.SPENTA or not self.dati.scrivibile:
            return []
        return self.dati.tutti(
            "SELECT e.* FROM studio_esercizi e JOIN studio_verifiche v ON v.id = e.verifica "
            "WHERE e.stato = 'da_leggere' AND v.stato IN ('bozza', 'aperta') ORDER BY e.id "
            "LIMIT 5")

    def esercizi_per_guida(self) -> list[dict]:
        """Gli esercizi letti che aspettano la guida, con materia e classe della verifica."""
        if self.esercizi_modo() == EG.SPENTA or not self.dati.scrivibile:
            return []
        return self.dati.tutti(
            "SELECT e.*, v.materia AS materia, v.livello AS livello FROM studio_esercizi e "
            "JOIN studio_verifiche v ON v.id = e.verifica WHERE e.stato = 'letto' AND "
            "v.stato IN ('bozza', 'aperta') ORDER BY e.id LIMIT 5")

    def prendi_esercizio(self, eid) -> bool:
        return self.dati.scrivi("UPDATE studio_esercizi SET stato = 'in_lettura' WHERE id = ? "
                                "AND stato = 'da_leggere'", (int(eid),)) == 1

    def rilascia_esercizio(self, eid):
        self.dati.scrivi("UPDATE studio_esercizi SET stato = 'da_leggere' WHERE id = ? AND "
                         "stato = 'in_lettura'", (int(eid),))

    def riprendi_esercizi(self) -> int:
        """Dopo un riavvio gli esercizi rimasti «in_lettura» tornano da leggere."""
        if not self.dati.scrivibile:
            return 0
        return self.dati.scrivi("UPDATE studio_esercizi SET stato = 'da_leggere' WHERE "
                                "stato = 'in_lettura'")

    def esercizio_letto(self, eid, testo: str | None, avvisi=()) -> bool:
        """Il testo letto dalla foto («letto»), o None: «illeggibile». False se la riga è
        cambiata nel frattempo (tolta)."""
        t = EG.testo_pulito(testo) if testo else ""
        stato = "letto" if len(t) >= 5 else "illeggibile"
        e = self._riga_es(eid)
        if e is None:
            return False
        av = list(dict.fromkeys(list(e["avvisi"]) + list(avvisi or ())))
        n = self.dati.scrivi(
            "UPDATE studio_esercizi SET stato = ?, testo = ?, avvisi = ?, modificato = ? WHERE "
            "id = ? AND stato = 'in_lettura'", (stato, t or None, D.j(av), D.adesso(), int(eid)))
        if n == 1:
            self._registra(f"esercizio {eid}: {'letto' if stato == 'letto' else 'illeggibile'}"
                           f" ({len(t)} caratteri)")
        return n == 1

    def scrivi_guida(self, eid, firma: str, passi: list[dict], risultato: str | None,
                     avvisi=(), esito: str = EG.PRONTA) -> bool:
        """La guida del lettore: «pronto» con da `PASSI_MIN` passi, altrimenti «senza_guida».
        Solo se l'esercizio è ancora «letto» con lo stesso testo (la firma). Nel registro solo
        conti."""
        e = self._riga_es(eid)
        if e is None or e["stato"] != "letto" or EG.firma(e["testo"] or "", "guida") != firma:
            return False
        stato = "pronto" if esito == EG.PRONTA and len(passi) >= EG.PASSI_MIN else "senza_guida"
        av = list(dict.fromkeys(list(e["avvisi"]) + list(avvisi or ())))
        n = self.dati.scrivi(
            "UPDATE studio_esercizi SET stato = ?, passi = ?, risultato = ?, avvisi = ?, "
            "firma = ?, passo = 0, esiti = '[]', errori = 0, modificato = ? WHERE id = ? AND "
            "stato = 'letto'",
            (stato, json.dumps(passi if stato == "pronto" else [], ensure_ascii=False),
             risultato if stato == "pronto" else None, D.j(av), firma, D.adesso(), int(eid)))
        if n == 1:
            m = self.misure.setdefault("guide", {"pronte": 0, "senza": 0, "passi": 0})
            m["pronte" if stato == "pronto" else "senza"] += 1
            m["passi"] += len(passi) if stato == "pronto" else 0
            self._registra(f"esercizio {eid}: guida {'pronta' if stato == 'pronto' else 'non fatta'}"
                           f" ({len(passi)} passi" + (f"; avvisi {', '.join(av)}" if av else "")
                           + ")")
        return n == 1

    # ── la vista ──
    def _vista_es(self, e: dict, ruolo: str, ferma: bool) -> dict:
        """Un esercizio per lo schermo: il testo e la domanda del passo in corso (dati: la pagina
        li scrive con textContent). Le risposte attese mai alla persona; al tutore solo a
        esercizio finito. Gli indizi solo quelli già chiesti."""
        passi = e["passi"]
        k = int(e["passo"] or 0)
        finito = e["stato"] == "finito"
        voci = []
        for i, p in enumerate(passi):
            x = {"n": i + 1, "tipo": p.get("tipo"),
                 "esito": next((s["esito"] for s in e["esiti"] if s.get("passo") == i), None)}
            if i <= k or finito or ruolo == "tutore":
                x["domanda"] = p.get("testo")
                if p.get("tipo") == "scelta":
                    x["opzioni"] = list(p.get("opzioni") or [])
            if i < k or finito:
                x["fatto"] = True
            if ruolo == "tutore" and finito:
                x["attesa"] = p.get("attesa")
            voci.append(x)
        corrente = None
        if e["stato"] in ("pronto", "in_corso", "pausa") and k < len(passi):
            p = passi[k]
            corrente = {"n": k + 1, "di": len(passi), "tipo": p.get("tipo"),
                        "domanda": p.get("testo"), "opzioni": list(p.get("opzioni") or []),
                        "errori": int(e["errori"] or 0),
                        "indizio": p.get("indizio") if int(e["indizi"] or 0) > k
                        and p.get("indizio") else None,
                        "ha_indizio": bool(p.get("indizio")),
                        "puo_saltare": int(e["errori"] or 0) >= SALTA_DOPO}
        return {"id": e["id"], "verifica": e["verifica"], "origine": e["origine"],
                "stato": e["stato"], "testo": e["testo"], "avvisi": list(e["avvisi"]),
                "creato": e["creato"], "voci": voci, "corrente": corrente,
                "giusti": sum(s.get("esito") == RS.GIUSTO for s in e["esiti"]),
                "da_rivedere": sum(s.get("esito") == RS.DA_RIVEDERE for s in e["esiti"]),
                "saltati": sum(s.get("esito") == "saltato" for s in e["esiti"]),
                "ruolo": ruolo, "ferma": ferma,
                "puo_rispondere": ruolo == "proprietario" and not ferma and corrente is not None}

    def esercizi(self, chi, vid) -> dict:
        """Gli esercizi di una verifica per lo schermo, i più recenti prima."""
        self._es_acceso(chi)
        v = self._verifica(chi, vid)
        ruolo = self._chi_puo(chi, v["persona"])
        ferma = self.prova_della_persona(v["persona"])
        out = [self._vista_es(self._riga_es(r["id"]), ruolo, ferma) for r in self.dati.tutti(
            "SELECT id FROM studio_esercizi WHERE verifica = ? ORDER BY id DESC", (v["id"],))]
        return {"verifica": v["id"], "esercizi": out, "ferma": ferma, "ruolo": ruolo,
                "chiusa": v["stato"] not in ("bozza", "aperta"),
                "massimi": {"testo": EG.TESTO_MAX}}

    def esercizio(self, chi, eid) -> dict:
        self._es_acceso(chi)
        e, v, ruolo = self._esercizio(chi, eid)
        return self._vista_es(e, ruolo, self.prova_della_persona(v["persona"]))

    def conto_esercizi(self, chi, v: dict) -> dict | None:
        """I conti degli esercizi di una verifica per la home (None se spenti per `chi`)."""
        if not self.esercizi_per(chi):
            return None
        r = self.dati.tutti("SELECT stato FROM studio_esercizi WHERE verifica = ?", (v["id"],))
        return {"totali": len(r), "in_corso": sum(x["stato"] in ("in_corso", "pausa") for x in r),
                "pronti": sum(x["stato"] == "pronto" for x in r),
                "da_leggere": sum(x["stato"] in ("da_leggere", "in_lettura", "letto") for x in r),
                "finiti": sum(x["stato"] == "finito" for x in r)}

    # ── la guida ──
    def _da_fare(self, chi, eid=None, vid=None) -> tuple[dict, dict]:
        """L'esercizio su cui lavorare: quello detto, o quello in corso più recente della
        persona (poi uno in pausa, poi uno pronto), nella verifica detta se c'è. Solo la persona
        dell'esercizio; NonTrovata se non ce n'è."""
        from .servizio import NonPermesso, NonTrovata
        self._es_acceso(chi)
        if eid is not None:
            e, v, ruolo = self._esercizio(chi, eid)
            if ruolo != "proprietario":
                raise NonPermesso("lo fa chi studia")
        else:
            q = ("SELECT e.id FROM studio_esercizi e JOIN studio_verifiche v ON v.id = e.verifica"
                 " WHERE e.persona = ? AND e.stato IN ('in_corso', 'pausa', 'pronto') AND "
                 "v.stato IN ('bozza', 'aperta')")
            arg = [str(getattr(chi, "id", ""))]
            if vid is not None:
                q += " AND e.verifica = ?"
                arg.append(int(vid))
            q += (" ORDER BY CASE e.stato WHEN 'in_corso' THEN 0 WHEN 'pausa' THEN 1 ELSE 2 END,"
                  " COALESCE(e.modificato, e.creato) DESC LIMIT 1")
            r = self.dati.uno(q, tuple(arg))
            if r is None:
                raise NonTrovata()
            e, v, _ruolo = self._esercizio(chi, r["id"])
        if e["stato"] not in ("pronto", "in_corso", "pausa"):
            raise ValueError(e["stato"])
        self._guida_ferma(v)
        return e, v

    def _aggiorna(self, e: dict, **campi):
        campi["modificato"] = D.adesso()
        for k in ("esiti",):
            if k in campi:
                campi[k] = json.dumps(campi[k], ensure_ascii=False)
        sets = ", ".join(f"{k} = ?" for k in campi)
        self.dati.scrivi(f"UPDATE studio_esercizi SET {sets} WHERE id = ?",
                         (*campi.values(), int(e["id"])))

    def passo_esercizio(self, chi, eid=None, vid=None) -> dict:
        """Il passo in corso (comincia l'esercizio, o lo riprende): {esercizio, n, di, domanda,
        tipo, opzioni}. Le risposte attese mai."""
        self._scrivibile()
        with self.dati.lock:
            e, v = self._da_fare(chi, eid, vid)
            if e["stato"] != "in_corso":
                self._aggiorna(e, stato="in_corso")
        k = int(e["passo"] or 0)
        p = e["passi"][k]
        return {"esercizio": e["id"], "verifica": v["id"], "n": k + 1, "di": len(e["passi"]),
                "tipo": p.get("tipo"), "domanda": p.get("testo"),
                "opzioni": list(p.get("opzioni") or []), "nuovo": e["stato"] == "pronto"}

    def rispondi_esercizio(self, chi, risposta, eid=None, vid=None, fonte: str = "voce") -> dict:
        """La risposta della persona al passo in corso, valutata dal codice
        (`risposte.valuta`). {esito, frase, n, di, finito, domanda?, offri_indizio,
        offri_salta}: la frase la scrive il codice, mai con la risposta attesa."""
        self._scrivibile()
        r = RS.riga(risposta, RS.RISPOSTA_MAX)
        with self.dati.lock:
            e, v = self._da_fare(chi, eid, vid)
            k = int(e["passo"] or 0)
            p = e["passi"][k]
            if int(e["errori"] or 0) >= ERRORI_MAX:
                # Il tetto dei tentativi: non si valuta più, restano l'indizio e «salta»
                return {"esercizio": e["id"], "esito": "fermo", "n": k + 1,
                        "di": len(e["passi"]), "finito": False, "errori": int(e["errori"]),
                        "offri_indizio": bool(p.get("indizio")), "offri_salta": True,
                        "frase": "Su questo passo hai provato tante volte: chiedi un indizio o "
                                 "salta il passo."}
            esito, _fonte = RS.valuta(p, r)
            esiti = list(e["esiti"])
            errori = int(e["errori"] or 0)
            avanti = esito in (RS.GIUSTO, RS.DA_RIVEDERE)
            if esito == RS.SBAGLIATO:
                errori += 1
            if avanti:
                esiti = [s for s in esiti if s.get("passo") != k] + [
                    {"passo": k, "esito": esito, "errori": errori, "fonte": fonte,
                     "ora": _ora(self.adesso())}]
                k += 1
                errori = 0
            finito = avanti and k >= len(e["passi"])
            self._aggiorna(e, passo=k, errori=errori, esiti=esiti,
                           stato="finito" if finito else "in_corso",
                           **({"finito": D.adesso()} if finito else {}))
        m = self.misure.setdefault("risposte_esercizi", {})
        m[esito] = m.get(esito, 0) + 1
        out = {"esercizio": e["id"], "esito": esito, "n": min(k, len(e["passi"])),
               "di": len(e["passi"]), "finito": finito, "errori": errori,
               "offri_indizio": esito == RS.SBAGLIATO and errori >= INDIZIO_DOPO
               and bool(p.get("indizio")),
               "offri_salta": esito == RS.SBAGLIATO and errori >= SALTA_DOPO}
        if finito:
            g = sum(s.get("esito") == RS.GIUSTO for s in esiti)
            out["frase"] = (("Giusto! " if esito == RS.GIUSTO else "")
                            + "Hai fatto tutti i passi: la soluzione l'hai trovata tu."
                            + (f" {len(esiti) - g} da rivedere con chi ti segue."
                               if len(esiti) - g else ""))
            self._registra(f"esercizio {e['id']}: finito ({g} giusti su {len(esiti)})")
            return out
        if avanti:
            q = e["passi"][k]
            out.update({"domanda": q.get("testo"), "tipo": q.get("tipo"),
                        "opzioni": list(q.get("opzioni") or []), "n": k + 1})
            out["frase"] = ("Giusto!" if esito == RS.GIUSTO else
                            "Questo non lo controllo io: lo guardate dopo.") + \
                f" Passo {k + 1} di {len(e['passi'])}."
            return out
        if esito == RS.INDIZIO:
            out["frase"] = "Il numero va bene: con quale unità di misura?"
        elif esito == RS.VUOTA:
            out["frase"] = "Non ho sentito una risposta: riprova."
        else:
            out["frase"] = "Non ancora." + (
                " Vuoi un indizio?" if out["offri_indizio"] else " Riprova.") + (
                " Se vuoi, possiamo anche saltare questo passo." if out["offri_salta"] else "")
        out["n"] = k + 1
        return out

    def indizio_esercizio(self, chi, eid=None, vid=None) -> dict:
        """L'indizio del passo in corso (scritto dal lettore, controllato dal codice: non
        contiene la risposta). {indizio | None}."""
        self._scrivibile()
        with self.dati.lock:
            e, _v = self._da_fare(chi, eid, vid)
            k = int(e["passo"] or 0)
            ind = e["passi"][k].get("indizio")
            if ind:
                self._aggiorna(e, indizi=max(int(e["indizi"] or 0), k + 1), stato="in_corso")
        return {"esercizio": e["id"], "n": k + 1, "indizio": ind}

    def salta_passo(self, chi, eid=None, vid=None) -> dict:
        """Il passo in corso saltato (il segno «saltato», senza la risposta)."""
        self._scrivibile()
        with self.dati.lock:
            e, _v = self._da_fare(chi, eid, vid)
            k = int(e["passo"] or 0)
            esiti = [s for s in e["esiti"] if s.get("passo") != k] + [
                {"passo": k, "esito": "saltato", "errori": int(e["errori"] or 0),
                 "ora": _ora(self.adesso())}]
            finito = k + 1 >= len(e["passi"])
            self._aggiorna(e, passo=k + 1, errori=0, esiti=esiti,
                           stato="finito" if finito else "in_corso",
                           **({"finito": D.adesso()} if finito else {}))
        out = {"esercizio": e["id"], "finito": finito, "di": len(e["passi"])}
        if not finito:
            q = e["passi"][k + 1]
            out.update({"n": k + 2, "domanda": q.get("testo"), "tipo": q.get("tipo"),
                        "opzioni": list(q.get("opzioni") or [])})
        return out

    def pausa_esercizio(self, chi) -> bool:
        """«Basta»: l'esercizio in corso della persona va in pausa (la guardia si ferma)."""
        n = self.dati.scrivi("UPDATE studio_esercizi SET stato = 'pausa', modificato = ? WHERE "
                             "persona = ? AND stato = 'in_corso'",
                             (D.adesso(), str(getattr(chi, "id", ""))))
        return n > 0

    def togli_esercizio(self, chi, eid) -> dict:
        """Toglie un esercizio (la persona o il tutore), con la sua foto."""
        self._es_acceso(chi)
        self._scrivibile()
        e, v, _ruolo = self._esercizio(chi, eid)
        with self.dati.lock:
            self.dati.scrivi("DELETE FROM studio_esercizi WHERE id = ?", (int(e["id"]),))
        if e.get("file"):
            D.togli_file([e["file"]], D.cartella_di(self.cfg))
        self._registra(f"verifica {v['id']}: esercizio {e['id']} tolto")
        return {"tolto": e["id"]}

    # ── la guardia della voce ──
    def _vietati(self, dove: str, arg=()) -> dict | None:
        try:
            righe = self.dati.tutti(
                "SELECT id, COALESCE(modificato, creato) AS quando FROM studio_esercizi WHERE "
                "stato IN ('in_corso', 'pausa', 'pronto') AND " + dove, arg)
        except Exception:  # noqa: BLE001 — una tabella che manca (db di prima): niente guardia
            return None
        adesso = datetime.datetime.now()
        voci = []
        for r in righe:
            try:
                t = datetime.datetime.fromisoformat(str(r["quando"]))
                if (adesso - t).total_seconds() > VIVO_S:
                    continue
            except (TypeError, ValueError):
                pass
            e = self._riga_es(r["id"])
            if e is not None:
                voci.append(EG.vietati(e))
        return EG.unisci(voci)

    def vietati_di(self, persona) -> dict | None:
        """Cosa la voce non dice a `persona`: i suoi esercizi vivi («in_corso», «pausa»,
        «pronto», modificati da meno di `VIVO_S`), uniti (`esercizi_genera.unisci`); None se non
        ce ne sono."""
        return self._vietati("persona = ?", (str(persona),))

    def vietati_tutti(self) -> dict | None:
        """Gli esercizi vivi di tutti: per chi parla con la voce incerta (revisione della PR
        #367, la strada prudente: senza sapere chi è, nessuna soluzione di nessuno)."""
        return self._vietati("1 = 1")


def vietati_per_ctx(ctx) -> dict | None:
    """Cosa la voce non dice a chi parla in questo turno: i suoi esercizi vivi; con la voce
    incerta (`chi_di` None) quelli di tutti. None senza Studio o senza esercizi vivi."""
    st = getattr(ctx, "studio", None)
    if st is None or not callable(getattr(st, "vietati_di", None)):
        return None
    try:
        from ..tools.studio import chi_di
        chi = chi_di(ctx)
        return st.vietati_di(chi.id) if chi is not None else st.vietati_tutti()
    except Exception:  # noqa: BLE001 — la guardia non ferma mai il turno
        return None


# Gli argomenti dei tool che scrivono o mostrano (revisione della PR #367: «ricorda» ripeteva la
# soluzione nella sua conferma) e le frasi pronte dei risultati, con un esercizio vivo
FRASE_ARGOMENTI = ("Questo non lo scrivo e non lo segno: è la soluzione del problema che stai "
                   "facendo a passi. Trovala tu, un passo alla volta.")
_FRASI = ("conferma", "risposta_finale", "da_dire")


def guardia_argomenti(name: str, arguments, ctx) -> dict | None:
    """Il rifiuto (un risultato col testo del codice) di una chiamata i cui argomenti di testo
    dicono la soluzione di un esercizio vivo di chi parla; None se va bene. Il tool
    dell'esercizio non si controlla (le sue frasi sono del codice)."""
    if name == "studio_esercizio":
        return None
    v = vietati_per_ctx(ctx)
    if v is None or not EG.svela_valore(v, arguments or {}):
        return None
    return {"ok": False, "errore": "la soluzione di un esercizio guidato", "fatto": "NIENTE",
            "conferma": FRASE_ARGOMENTI, "risposta_finale": FRASE_ARGOMENTI}


def guardia_risultato(name: str, result, ctx):
    """Le frasi pronte di un risultato (conferma, risposta_finale, da_dire) che dicono la
    soluzione di un esercizio vivo: al loro posto la frase del codice. Il risultato com'è
    altrimenti (o senza esercizi vivi)."""
    if name == "studio_esercizio" or not isinstance(result, dict):
        return result
    frasi = [k for k in _FRASI if isinstance(result.get(k), str) and result.get(k)]
    if not frasi:
        return result
    v = vietati_per_ctx(ctx)
    if v is None:
        return result
    tolte = [k for k in frasi if EG.svela(v, result[k])]
    if not tolte:
        return result
    out = dict(result)
    for k in tolte:
        out[k] = FRASE_SVELATO
    return out
