"""
Le domande e le prove nel servizio dello Studio (31/10, passo 8, issue #248, epic #251, decisione
0035 punto 40): i metodi di `Studio` sopra `studio_domande` e `studio_prove` (schema 10) e la
parte pura di `risposte.py`.

**Due modalità, sempre.** La verifica finta (scritta, sullo schermo: `inizia_prova`,
`rispondi_prova`, `consegna_prova`) e l'interrogazione simulata (orale, a voce: `orale_inizia`,
`orale_risposta`, `orale_basta`, dal tool `studio_interroga`) misurano la preparazione qualunque
sia il tipo della prova vera (decisione di chi amministra del 30/10).

**Le domande** sono un dato chiunque le abbia scritte (la persona, il tutore, il lettore): nel
registro solo id, conti ed esiti, sullo schermo con textContent, al modello in busta. Con le
domande valgono come domande anche le carte attive degli argomenti del piano.

**L'esito lo decide il codice** (`risposte.valuta`); «da rivedere» lo decidono dopo la consegna la
persona (fonte «persona», peso dimezzato nella padronanza) o il tutore (fonte «tutore»). Il
modello può solo proporre (`proposta` nell'orale): una misura, mai un tentativo.

**Niente corse, niente oracoli** (le revisioni delle PR #326–#330):
- ogni azione legge e scrive dentro `dati.lock`, e lo stato della prova cambia una volta sola:
  un secondo «consegna» rende la stessa correzione senza tentativi nuovi;
- le risposte attese non escono mai prima della consegna (`vista_prova` le toglie), e mentre una
  prova è aperta carte e domande di quella verifica sono nascoste alla persona;
- una prova aperta su una verifica che si chiude («fatta», «conclusa», «archiviata») si chiude
  davvero, «annullata» e senza tentativi (`_chiudi_prove`);
- la prova la fa solo la persona: il tutore la vede, decide le voci «da rivedere» e basta.
"""

from __future__ import annotations

import datetime
import json
import random

from . import carte as C
from . import dati as D
from . import padronanza as PD
from . import risposte as RS

SCRITTA, ORALE = "scritta", "orale"
MODALITA = (SCRITTA, ORALE)
TIPO_TENTATIVO = {SCRITTA: "verifica_finta", ORALE: "interrogazione"}
APERTA, CONSEGNATA, SCADUTA, ANNULLATA = "aperta", "consegnata", "scaduta", "annullata"
# Le domande di una prova: almeno tante, al più `studio_prova_domande` (scritta) o ORALE_DOMANDE
PROVA_MIN = 3
ORALE_DOMANDE = 5
# L'orale senza risposte da tanto si chiude alla prossima lettura, con le voci già valutate
ORALE_PAUSA_S = 600
# I pesi del mix per argomento con la padronanza mostrata (in ombra solo una misura)
PESI_MIX = {PD.DA_STUDIARE_P: 3, PD.QUASI_P: 2, PD.NON_MISURATA_P: 2, PD.LA_SAI_P: 1}
PROVA_APERTA = "c'è una prova aperta su questa verifica: prima finiscila"
POCHE = "servono almeno 3 domande sugli argomenti del piano: scrivile o fai le carte"
SOLO_PERSONA = "la prova la fa chi studia"
# Le domande generate (domande_genera): come le carte
STATI_DOMANDA = ("attiva", "proposta", "tolta", "ombra")
ORIGINI_DOMANDA = ("persona", "modello")


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False)


def _da(x, vuoto):
    try:
        v = json.loads(x) if x else vuoto
    except (TypeError, ValueError):
        return vuoto
    return v if isinstance(v, type(vuoto)) else vuoto


class Prove:
    """Il mixin delle prove di `Studio` (`self.dati`, `self.adesso`, `self._verifica`…)."""

    # ─────────────────────────── le domande ───────────────────────────
    def _riga_domanda(self, r: dict) -> dict:
        d = dict(r)
        d["opzioni"] = _da(d.get("opzioni"), [])
        d["chiave"] = _da(d.get("chiave"), [])
        d["pagine"] = [int(x) for x in _da(d.get("pagine"), []) if str(x).isdecimal()]
        d["avvisi"] = _da(d.get("avvisi"), [])
        return d

    def aggiungi_domanda(self, chi, vid, tipo, testo, attesa, opzioni=(), chiave=(),
                         argomento=None, pagine=(), origine: str = "persona",
                         avvisi=None) -> int:
        """Una domanda nuova (un dato, chiunque l'abbia scritta), controllata nella forma
        (`risposte.prepara`). Della persona o del tutore; «modello» per la generazione."""
        self._scrivibile()
        v = self._verifica(chi, vid)
        if v["stato"] not in ("bozza", "aperta"):
            from .servizio import VerificaChiusa
            raise VerificaChiusa()
        if origine not in ORIGINI_DOMANDA:
            raise ValueError("origine sconosciuta")
        d = RS.prepara(tipo, testo, attesa, opzioni, chiave)
        aid = self._argomento_di(v, argomento)
        sue = {p["id"] for p in self._pagine_di(v["id"])}
        pag = [int(x) for x in pagine or ()]
        if any(x not in sue for x in pag):
            raise ValueError("una pagina non è di questa verifica")
        with self.dati.lock:
            n = self.dati.uno("SELECT COUNT(*) AS n FROM studio_domande WHERE verifica = ? AND "
                              "stato != 'ombra'", (v["id"],))["n"]
            if n >= RS.DOMANDE_MAX:
                raise ValueError(f"al più {RS.DOMANDE_MAX} domande per verifica")
            adesso = self.adesso().isoformat(timespec="seconds")
            did = self.dati.scrivi(
                "INSERT INTO studio_domande (verifica, persona, argomento, tipo, testo, opzioni, "
                "attesa, chiave, pagine, origine, stato, avvisi, creata, creata_da) VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (v["id"], str(v["persona"]), aid, d["tipo"], d["testo"], _j(d["opzioni"]),
                 d["attesa"], _j(d["chiave"]), _j(list(dict.fromkeys(pag))), origine,
                 "proposta" if avvisi else "attiva", _j(avvisi) if avvisi else None, adesso,
                 getattr(chi, "id", None)))
        self.misure["prove"]["domande"] += 1
        self._registra(f"verifica {v['id']}: domanda {did} scritta ({d['tipo']}, {origine}, "
                       f"{self._chi_registro(chi, v['persona'])})")
        return did

    def _domanda(self, chi, did) -> tuple[dict, dict]:
        r = self.dati.uno("SELECT * FROM studio_domande WHERE id = ?", (int(did),))
        if r is None or r["stato"] == "ombra":
            from .servizio import NonTrovata
            raise NonTrovata()
        v = self._verifica(chi, r["verifica"])
        if self._nascoste(v, chi):
            from .servizio import NonTrovata
            raise NonTrovata()
        return self._riga_domanda(r), v

    def segna_domanda(self, chi, did, attiva: bool):
        """Toglie una domanda o la rimette; su una proposta del modello è il «Tieni»."""
        self._scrivibile()
        with self.dati.lock:
            d, _v = self._domanda(chi, did)
            self.dati.scrivi("UPDATE studio_domande SET stato = ?, modificata = ? WHERE id = ?",
                             ("attiva" if attiva else "tolta",
                              self.adesso().isoformat(timespec="seconds"), d["id"]))

    def conferma_domande(self, chi, vid) -> dict:
        """«Conferma le domande proposte»: quelle senza avvisi diventano attive, le altre restano
        proposte e si tengono una per una. {confermate, da_decidere}."""
        from .domande_genera import DA_DECIDERE
        self._scrivibile()
        with self.dati.lock:
            v = self._verifica(chi, vid)
            if self._nascoste(v, chi):
                raise ValueError(PROVA_APERTA)
            n = k = 0
            adesso = self.adesso().isoformat(timespec="seconds")
            for r in self.dati.tutti("SELECT id, avvisi FROM studio_domande WHERE verifica = ? "
                                     "AND stato = 'proposta'", (v["id"],)):
                if set(_da(r["avvisi"], [])) & set(DA_DECIDERE):
                    k += 1
                    continue
                self.dati.scrivi("UPDATE studio_domande SET stato = 'attiva', modificata = ? "
                                 "WHERE id = ?", (adesso, r["id"]))
                n += 1
        self._registra(f"verifica {v['id']}: {n} domande confermate, {k} da decidere")
        return {"confermate": n, "da_decidere": k}

    def domande(self, chi, vid) -> dict:
        """Le domande di una verifica per lo schermo: {domande, nascoste}. Mentre una prova è
        aperta, per la persona sono nascoste (le risposte attese sono lì)."""
        v = self._verifica(chi, vid)
        if self._nascoste(v, chi):
            return {"domande": [], "nascoste": True}
        numeri = {a["id"]: i for i, a in enumerate(self.dati.tutti(
            "SELECT id FROM studio_argomenti WHERE verifica = ? ORDER BY ordine, id",
            (v["id"],)), 1)}
        out = []
        senza = self._risposte_nascoste(v, chi)
        for i, r in enumerate(self.dati.tutti("SELECT * FROM studio_domande WHERE verifica = ? "
                                              "AND stato != 'ombra' ORDER BY id", (v["id"],)), 1):
            d = self._riga_domanda(r)
            d["numero"] = i
            d["argomento_numero"] = numeri.get(d["argomento"])
            if senza:
                # Al tutore, con la prova del minore aperta, solo i testi (PR #348, nota 2)
                d["attesa"], d["chiave"] = None, []
            out.append(d)
        return {"domande": out, "nascoste": False, "risposte_nascoste": senza}

    # ── la generazione (dal lettore, studio/domande_genera.py; niente `chi`) ──
    def verifiche_per_domande(self) -> list[dict]:
        """Come `verifiche_per_carte`: le verifiche aperte con un argomento del piano su pagine
        lette e una firma diversa da quella dell'ultima generazione delle domande."""
        from . import argomenti as A
        from . import domande_genera as G
        m = G.modo(self.cfg)
        if m == G.SPENTA or not self.dati.scrivibile:
            return []
        out = []
        for v in self.dati.tutti("SELECT * FROM studio_verifiche WHERE stato = 'aperta' AND "
                                 "data >= ? ORDER BY data, id", (self._oggi().isoformat(),)):
            args = self._argomenti_per_carte(v["id"])
            pagine = self._pagine_di(v["id"])
            lette = {int(p["id"]) for p in A.lette(pagine)}
            if not any(set(a["pagine"]) & lette for a in args):
                continue
            if G.da_generare(v.get("domande_firma"), v.get("domande_esito"),
                             v.get("domande_del"), G.firma(args, pagine, m), self.adesso()):
                out.append({**v, "_pagine": pagine, "_argomenti": args, "_modo": m})
        return out

    def proponi_domande(self, vid, firma: str, proposte: list[dict], esito: str,
                        modo_: str) -> int | None:
        """Come `proponi_carte`: via le domande del modello non decise, dentro le nuove
        («proposta» o «ombra»), la firma e l'esito; None se intanto argomenti o pagine sono
        cambiati."""
        from . import argomenti as A
        from . import domande_genera as G
        with self.dati.lock:
            db = self.dati.db
            try:
                if db.in_transaction:
                    db.commit()
                db.execute("BEGIN IMMEDIATE")
                v = db.execute("SELECT * FROM studio_verifiche WHERE id = ? AND stato = 'aperta'",
                               (int(vid),)).fetchone()
                pagine = [dict(r) for r in db.execute(
                    "SELECT p.* FROM studio_pagine p JOIN studio_materiali m ON m.id = p.materiale"
                    " WHERE m.verifica = ?", (int(vid),))]
                args = [{"id": a["id"], "titolo": a["titolo"],
                         "pagine": [int(x) for x in D.da_j(a["pagine"]) if str(x).isdecimal()]}
                        for a in db.execute("SELECT * FROM studio_argomenti WHERE verifica = ? "
                                            "ORDER BY ordine, id", (int(vid),)).fetchall()
                        if a["stato"] in D.ARGOMENTI_DEL_PIANO]
                if v is None or G.firma(args, pagine, modo_) != firma:
                    db.rollback()
                    return None
                n = 0
                if esito not in (G.ROTTO, G.ERRORE):
                    db.execute("DELETE FROM studio_domande WHERE verifica = ? AND origine = "
                               "'modello' AND stato IN ('proposta', 'ombra')", (int(vid),))
                    decise = {A.chiave(r[0]) for r in db.execute(
                        "SELECT testo FROM studio_domande WHERE verifica = ?", (int(vid),))}
                    tot = db.execute("SELECT COUNT(*) FROM studio_domande WHERE verifica = ? AND "
                                     "stato != 'ombra'", (int(vid),)).fetchone()[0]
                    adesso = self.adesso().isoformat(timespec="seconds")
                    stato = "ombra" if modo_ == G.OMBRA else "proposta"
                    for d in proposte:
                        if A.chiave(d["testo"]) in decise or tot + n >= RS.DOMANDE_MAX:
                            continue
                        db.execute(
                            "INSERT INTO studio_domande (verifica, persona, argomento, tipo, "
                            "testo, opzioni, attesa, chiave, pagine, origine, stato, avvisi, "
                            "creata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'modello', ?, ?, ?)",
                            (int(vid), str(v["persona"]), d["argomento"], d["tipo"], d["testo"],
                             _j(d["opzioni"]), d["attesa"], _j(d["chiave"]), _j(d["pagine"]),
                             stato, _j(d["avvisi"]) if d["avvisi"] else None, adesso))
                        decise.add(A.chiave(d["testo"]))
                        n += 1
                scritta, errori = G.firma_da_scrivere(v["domande_firma"], firma, esito)
                db.execute("UPDATE studio_verifiche SET domande_firma = ?, domande_esito = ?, "
                           "domande_del = ? WHERE id = ?",
                           (scritta, esito if esito != G.PROPOSTE or n else G.VUOTO,
                            self.adesso().isoformat(timespec="seconds"), int(vid)))
                db.commit()
                if errori >= G.ERRORI_MAX:
                    self._registra(f"verifica {vid}: domande ferme dopo {errori} errori con le "
                                   "stesse pagine e argomenti: ripartono quando cambiano")
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
        return n

    # ─────────────────────────── le prove ───────────────────────────
    def _riga_prova(self, r: dict | None) -> dict | None:
        if r is None:
            return None
        p = dict(r)
        p["voci"] = _da(p.get("voci"), [])
        p["riepilogo"] = _da(p.get("riepilogo"), {})
        p["mix"] = _da(p.get("mix"), {})
        return p

    def _prova_aperta(self, vid) -> dict | None:
        """La prova aperta di una verifica ancora aperta (una per verifica), dopo aver chiuso
        quella scaduta per il tempo."""
        r = self.dati.uno("SELECT p.* FROM studio_prove p JOIN studio_verifiche v ON v.id = "
                          "p.verifica WHERE p.verifica = ? AND p.stato = 'aperta' AND v.stato IN "
                          "('bozza', 'aperta') ORDER BY p.id DESC LIMIT 1", (int(vid),))
        p = self._riga_prova(r)
        if p is not None and self._scaduta(p):
            self._chiudi_prova(p, SCADUTA)
            return None
        return p

    def _nascoste(self, v: dict, chi) -> bool:
        """Carte e domande nascoste a chi le guarda: la persona della verifica (o i conti, senza
        `chi`) mentre una sua prova è aperta."""
        if chi is not None and getattr(chi, "id", None) != v["persona"]:
            return False
        try:
            return self._prova_aperta(v["id"]) is not None
        except Exception:  # noqa: BLE001 — una tabella che manca (schema di prima): niente prove
            return False

    def _risposte_nascoste(self, v: dict, chi) -> bool:
        """Le risposte attese (domande, carte, prove chiuse) nascoste a chi guarda **non** la
        persona, il tutore compreso, mentre una prova della persona è aperta sulla verifica
        (revisione della PR #348, nota 2: come il ripasso, che si blocca per tutti). Il tutore
        vede al più i testi delle domande; la persona non vede nemmeno quelli (`_nascoste`)."""
        if chi is None or getattr(chi, "id", None) == v["persona"]:
            return False
        try:
            return self._prova_aperta(v["id"]) is not None
        except Exception:  # noqa: BLE001 — una tabella che manca (schema di prima)
            return False

    def prova_in_corso(self, chi, vid) -> dict | None:
        """La prova aperta della verifica (modalità e id), per il tool e la home."""
        v = self._verifica(chi, vid)
        p = self._prova_aperta(v["id"])
        return {"id": p["id"], "modalita": p["modalita"]} if p else None

    def _scaduta(self, p: dict) -> bool:
        adesso = self.adesso()
        if p["modalita"] == SCRITTA:
            return bool(p["scade"]) and adesso > datetime.datetime.fromisoformat(p["scade"])
        ultima = p.get("ultima") or p["inizio"]
        return (adesso - datetime.datetime.fromisoformat(ultima)).total_seconds() > ORALE_PAUSA_S

    def _pool(self, v: dict) -> list[dict]:
        """Le domande possibili: le domande attive e le carte attive degli argomenti del piano
        (una carta della mappa no, se la mappa libera è aperta)."""
        nel_piano = self._del_piano(v["id"])
        out = []
        for r in self.dati.tutti("SELECT * FROM studio_domande WHERE verifica = ? AND stato = "
                                 "'attiva' ORDER BY id", (v["id"],)):
            d = self._riga_domanda(r)
            if d["argomento"] in nel_piano:
                out.append({"fonte": "domanda", "id": d["id"], "argomento": d["argomento"],
                            "tipo": d["tipo"], "testo": d["testo"], "opzioni": d["opzioni"],
                            "attesa": d["attesa"], "chiave": d["chiave"], "pagine": d["pagine"]})
        libera = self._libera_aperta(v["id"])
        for c in self.dati.tutti("SELECT * FROM studio_carte WHERE verifica = ? AND stato = "
                                 "'attiva' ORDER BY id", (v["id"],)):
            if c["argomento"] not in nel_piano or (libera and c["origine"] == "mappa"):
                continue
            out.append({"fonte": "carta", "id": c["id"], "argomento": c["argomento"],
                        "tipo": RS.CARTA if c["chiusa"] else "aperta", "testo": c["domanda"],
                        "opzioni": [], "attesa": c["risposta"], "chiusa": c["chiusa"],
                        "chiave": [], "pagine": [int(x) for x in D.da_j(c["pagine"])
                                                 if str(x).isdecimal()]})
        return out

    def _mix(self, v: dict, pool: list[dict], n: int, seme: int) -> tuple[list[dict], dict]:
        """Le domande della prova: per argomento, uniformi o pesate dalla padronanza mostrata
        (in ombra i pesi sono solo una misura); dentro un argomento prima le usate meno."""
        rnd = random.Random(seme)
        per: dict[int, list[dict]] = {}
        for d in pool:
            per.setdefault(d["argomento"], []).append(d)
        usate: dict[tuple, int] = {}
        # Le domande viste e lasciate vuote (revisione della PR #342): la prova dopo le evita se
        # può, altrimenti le mette in fondo (consegnare vuoto non fa ritrovare le stesse domande)
        vuote: dict[tuple, int] = {}
        for r in self.dati.tutti("SELECT voci FROM studio_prove WHERE verifica = ?", (v["id"],)):
            for x in _da(r["voci"], []):
                k = (x.get("fonte"), x.get("id"))
                usate[k] = usate.get(k, 0) + 1
                if x.get("esito") == RS.VUOTA:
                    vuote[k] = vuote.get(k, 0) + 1
        for lst in per.values():
            rnd.shuffle(lst)
            lst.sort(key=lambda d: (vuote.get((d["fonte"], d["id"]), 0),
                                    usate.get((d["fonte"], d["id"]), 0)))
        pad = self._padronanza(v)
        parola = {a["id"]: a["parola"] for a in pad["argomenti"]}
        pesi = {a: PESI_MIX.get(parola.get(a, PD.NON_MISURATA_P), 2) for a in per}
        pesata = self.padronanza_mostrata()
        quota = self._quote(pesi if pesata else {a: 1 for a in per}, per, n)
        misura = self._quote(pesi, per, n)
        scelte = []
        for a in sorted(per, key=lambda a: (-quota[a], a)):
            scelte += per[a][:quota[a]]
        rnd.shuffle(scelte)
        # Quelle lasciate vuote l'altra volta, se non si sono potute evitare, vanno in fondo
        scelte.sort(key=lambda d: vuote.get((d["fonte"], d["id"]), 0))
        mix = {"modo": "padronanza" if pesata else "uniforme",
               "quote": {str(a): q for a, q in quota.items()},
               "pesate": {str(a): q for a, q in misura.items()}}
        return scelte, mix

    @staticmethod
    def _quote(pesi: dict, per: dict, n: int) -> dict:
        """Quante domande per argomento: in proporzione ai pesi, senza superare quelle che ci
        sono, il resto a chi ne ha ancora (deterministico)."""
        quota = {a: 0 for a in per}
        resto = min(n, sum(len(x) for x in per.values()))
        while resto > 0:
            vivi = [a for a in per if quota[a] < len(per[a])]
            if not vivi:
                break
            a = min(vivi, key=lambda a: ((quota[a] + 1) / pesi.get(a, 1), a))
            quota[a] += 1
            resto -= 1
        return quota

    def _voce(self, d: dict, k: int) -> dict:
        """Una voce della prova: la domanda copiata, la risposta e l'esito vuoti."""
        return {"n": k, "fonte": d["fonte"], "id": d["id"], "argomento": d["argomento"],
                "tipo": d["tipo"], "testo": d["testo"], "opzioni": list(d.get("opzioni") or ()),
                "attesa": d["attesa"], "chiave": list(d.get("chiave") or ()),
                "chiusa": d.get("chiusa"), "pagine": list(d.get("pagine") or ()),
                "risposta": None, "esito": None, "fonte_esito": None, "proposta": None,
                "tentativo": None}

    def inizia_prova(self, chi, vid, modalita: str = SCRITTA) -> dict:
        """Apre una prova sulla verifica (solo la persona; una aperta per volta: se c'è già della
        stessa modalità si riprende). La vista della prova."""
        from .servizio import VerificaChiusa
        self._scrivibile()
        if modalita not in MODALITA:
            raise ValueError("modalità sconosciuta")
        with self.dati.lock:
            v = self._verifica(chi, vid)
            if self._chi_puo(chi, v["persona"]) != "proprietario":
                raise ValueError(SOLO_PERSONA)
            if v["stato"] != "aperta":
                raise VerificaChiusa()
            aperta = self._prova_aperta(v["id"])
            if aperta is not None:
                if aperta["modalita"] != modalita:
                    raise ValueError(PROVA_APERTA)
                return self._vista(aperta, chi, v)
            n = (ORALE_DOMANDE if modalita == ORALE
                 else int(getattr(self.cfg, "studio_prova_domande", 10) or 10))
            pool = self._pool(v)
            if len(pool) < PROVA_MIN:
                raise ValueError(POCHE)
            adesso = self.adesso().replace(microsecond=0)
            seme = random.SystemRandom().randrange(1, 2 ** 31)
            scelte, mix = self._mix(v, pool, n, seme)
            voci = [self._voce(d, k) for k, d in enumerate(scelte, 1)]
            minuti = int(getattr(self.cfg, "studio_prova_minuti", 20) or 20)
            scade = (adesso + datetime.timedelta(minutes=minuti)).isoformat() \
                if modalita == SCRITTA else None
            pid = self.dati.scrivi(
                "INSERT INTO studio_prove (verifica, persona, modalita, stato, inizio, scade, "
                "ultima, corrente, seme, mix, voci, creata_da) VALUES (?, ?, ?, 'aperta', ?, ?, ?, "
                "0, ?, ?, ?, ?)",
                (v["id"], str(v["persona"]), modalita, adesso.isoformat(), scade,
                 adesso.isoformat(), seme, _j(mix), _j(voci), getattr(chi, "id", None)))
            self.misure["prove"]["iniziate"] += 1
            self._registra(f"verifica {v['id']}: prova {pid} {modalita} con {len(voci)} domande "
                           f"(mix {mix['modo']}: " + ", ".join(
                               f"arg. {a} {q}" for a, q in mix["quote"].items() if q)
                           + "; pesato dalla padronanza: " + ", ".join(
                               f"arg. {a} {q}" for a, q in mix["pesate"].items() if q) + ")")
            out = self._vista(self._riga_prova(self.dati.uno(
                "SELECT * FROM studio_prove WHERE id = ?", (pid,))), chi, v)
        # Fuori dal lock: chi aspetta la partenza di una prova (le attività della libreria aperte
        # dalla persona si chiudono, revisione della PR #366, nota 1)
        for gancio in list(getattr(self, "ganci_prova", ()) or ()):
            try:
                gancio(str(v["persona"]))
            except Exception as ex:  # noqa: BLE001 — un gancio non ferma la prova
                self.log(f"   [STUDIO] gancio della prova: {type(ex).__name__}")
        return out

    def _prova(self, chi, pid) -> tuple[dict, dict]:
        from .servizio import NonTrovata
        p = self._riga_prova(self.dati.uno("SELECT * FROM studio_prove WHERE id = ?", (int(pid),)))
        if p is None:
            raise NonTrovata()
        v = self._verifica(chi, p["verifica"])
        if p["stato"] == APERTA and v["stato"] not in ("bozza", "aperta"):
            # La verifica si è chiusa per un'altra strada: la prova si chiude adesso, senza
            # tentativi (la rete di `_chiudi_prove`)
            self._chiudi_prova(p, ANNULLATA)
            p = self._riga_prova(self.dati.uno("SELECT * FROM studio_prove WHERE id = ?",
                                               (p["id"],)))
        elif p["stato"] == APERTA and self._scaduta(p):
            self._chiudi_prova(p, SCADUTA)
            p = self._riga_prova(self.dati.uno("SELECT * FROM studio_prove WHERE id = ?",
                                               (p["id"],)))
        return p, v

    def vista_prova(self, chi, pid) -> dict:
        with self.dati.lock:
            p, v = self._prova(chi, pid)
            return self._vista(p, chi, v)

    def prove(self, chi, vid) -> dict:
        """Le prove di una verifica per lo schermo: quella aperta (se c'è) e le chiuse, dalla
        più recente, con i riepiloghi; quante domande ci sono per una prova nuova."""
        with self.dati.lock:
            v = self._verifica(chi, vid)
            aperta = self._prova_aperta(v["id"])
            chiuse = [self._riga_prova(r) for r in self.dati.tutti(
                "SELECT * FROM studio_prove WHERE verifica = ? AND stato != 'aperta' ORDER BY id "
                "DESC LIMIT 10", (v["id"],))]
            return {"verifica": v["id"], "prova_vera": v.get("prova") or "scritta",
                    "finestra": bool(v.get("finestra")),
                    "aperta": self._vista(aperta, chi, v) if aperta else None,
                    "chiuse": [self._vista(p, chi, v) for p in chiuse],
                    "domande_pronte": len(self._pool(v)), "minimo": PROVA_MIN,
                    "minuti": int(getattr(self.cfg, "studio_prova_minuti", 20) or 20),
                    "quante": int(getattr(self.cfg, "studio_prova_domande", 10) or 10)}

    def _vista(self, p: dict, chi, v: dict) -> dict:
        """La prova per lo schermo. **Aperta: mai la risposta attesa né l'esito**; chiusa: la
        correzione. Il testo è un dato (textContent)."""
        aperta = p["stato"] == APERTA
        numeri = {a["id"]: i for i, a in enumerate(self.dati.tutti(
            "SELECT id FROM studio_argomenti WHERE verifica = ? ORDER BY ordine, id",
            (v["id"],)), 1)}
        voci = []
        for x in p["voci"]:
            y = {"n": x["n"], "tipo": x["tipo"], "testo": x["testo"],
                 "opzioni": list(x.get("opzioni") or ()),
                 "argomento_numero": numeri.get(x.get("argomento")),
                 "risposta": x.get("risposta")}
            if not aperta:
                y.update(chiusa=x["tipo"] in RS.CHIUSE,
                         esito=x.get("esito"), deciso_da=x.get("fonte_esito"),
                         attesa=RS.attesa_detta(x), pagine=list(x.get("pagine") or ()))
            voci.append(y)
        ruolo = self._chi_puo(chi, v["persona"])
        if not aperta and ruolo == "tutore" and self._risposte_nascoste(v, chi):
            # Una prova chiusa vista dal tutore mentre il minore ne fa un'altra: le stesse domande
            # possono tornare, quindi niente risposte attese (PR #348, nota 2)
            for y in voci:
                y["attesa"] = None
        out = {"id": p["id"], "verifica": v["id"], "modalita": p["modalita"], "stato": p["stato"],
               "inizio": p["inizio"], "scade": p["scade"], "fine": p["fine"], "voci": voci,
               "corrente": p["corrente"], "puo_rispondere": aperta and ruolo == "proprietario"
               and p["modalita"] == SCRITTA,
               "puo_rivedere": not aperta and p["stato"] != ANNULLATA,
               # Sulle domande chiuse la persona dà al più «indizio» (revisione della PR #342)
               "tutore": ruolo == "tutore"}
        if aperta and p["scade"]:
            out["secondi"] = max(0, int((datetime.datetime.fromisoformat(p["scade"])
                                         - self.adesso()).total_seconds()))
        if not aperta:
            out["riepilogo"] = p["riepilogo"]
            out["frase"] = self._frase_prova(p, self._nome_per(chi, v))
        return out

    def rispondi_prova(self, chi, pid, n: int, risposta) -> dict:
        """Una risposta della verifica finta scritta: solo la persona, solo con la prova aperta e
        nel tempo. Si può cambiare finché non consegna. La vista (senza esiti)."""
        self._scrivibile()
        with self.dati.lock:
            p, v = self._prova(chi, pid)
            if self._chi_puo(chi, v["persona"]) != "proprietario":
                raise ValueError(SOLO_PERSONA)
            if p["stato"] != APERTA or p["modalita"] != SCRITTA:
                raise ValueError("la prova è chiusa")
            voce = next((x for x in p["voci"] if x["n"] == int(n)), None)
            if voce is None:
                raise ValueError("domanda sconosciuta")
            voce["risposta"] = RS.riga(risposta, RS.RISPOSTA_MAX) or None
            adesso = self.adesso().isoformat(timespec="seconds")
            self.dati.scrivi("UPDATE studio_prove SET voci = ?, ultima = ? WHERE id = ? AND "
                             "stato = 'aperta'", (_j(p["voci"]), adesso, p["id"]))
            p["ultima"] = adesso
            return self._vista(p, chi, v)

    def consegna_prova(self, chi, pid) -> dict:
        """«Consegna»: il codice valuta ogni risposta, scrive i tentativi (una volta: la prova
        passa a «consegnata» nella stessa operazione), il riepilogo per argomento e la misura.
        Un secondo «consegna» rende la stessa correzione senza tentativi."""
        self._scrivibile()
        with self.dati.lock:
            p, v = self._prova(chi, pid)
            if self._chi_puo(chi, v["persona"]) != "proprietario":
                raise ValueError(SOLO_PERSONA)
            if p["stato"] == APERTA:
                self._chiudi_prova(p, CONSEGNATA, chi)
                p, v = self._prova(chi, pid)
            return self._vista(p, chi, v)

    def _chiudi_prova(self, p: dict, stato: str, chi=None):
        """Chiude una prova aperta (dentro il lock): «consegnata» e «scaduta» valutano le risposte
        date e scrivono i tentativi e la misura; «annullata» (la verifica si è chiusa) niente."""
        with self.dati.lock:
            r = self.dati.uno("SELECT stato FROM studio_prove WHERE id = ?", (p["id"],))
            if r is None or r["stato"] != APERTA:
                return
            adesso = self.adesso().isoformat(timespec="seconds")
            if stato == ANNULLATA:
                self.dati.scrivi("UPDATE studio_prove SET stato = ?, fine = ? WHERE id = ? AND "
                                 "stato = 'aperta'", (ANNULLATA, adesso, p["id"]))
                self.misure["prove"]["annullate"] += 1
                self._registra(f"verifica {p['verifica']}: prova {p['id']} annullata (la "
                               "verifica si è chiusa), senza tentativi")
                return
            if p["modalita"] == SCRITTA:
                for x in p["voci"]:
                    if x.get("esito") is None:
                        x["esito"], x["fonte_esito"] = RS.valuta(x, x.get("risposta"))
            else:
                # Orale: le voci mai chieste non contano (non sono «vuote»)
                p["voci"] = [x for x in p["voci"] if x.get("esito") is not None]
            v = self.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (p["verifica"],))
            p["riepilogo"] = self._riepilogo_prova(p, v)
            # Prima lo stato (la prova non si chiude due volte), poi i tentativi
            n = self.dati.scrivi("UPDATE studio_prove SET stato = ?, fine = ?, voci = ?, "
                                 "riepilogo = ? WHERE id = ? AND stato = 'aperta'",
                                 (stato, adesso, _j(p["voci"]), _j(p["riepilogo"]), p["id"]))
            if not n:
                return
            self._tentativi_prova(p, v, chi)
            self.dati.scrivi("UPDATE studio_prove SET voci = ? WHERE id = ?",
                             (_j(p["voci"]), p["id"]))
            self._misura_prova(p, v)
            m = self.misure["prove"]
            m[stato] = m.get(stato, 0) + 1
            for x in p["voci"]:
                m["esiti"][x["esito"]] = m["esiti"].get(x["esito"], 0) + 1
            rp = p["riepilogo"]
            self._registra(f"verifica {p['verifica']}: prova {p['id']} {p['modalita']} {stato}: "
                           + ", ".join(f"{k} {rp['totali'].get(k, 0)}" for k in RS.ESITI)
                           + (f", punteggio {rp['punteggio']}" if rp.get("punteggio") is not None
                              else ""))

    def _tentativi_prova(self, p: dict, v: dict, chi=None):
        """I tentativi delle voci decise e non ancora scritte, con la fonte di chi ha deciso."""
        if self.modo_padronanza == PD.SPENTA:
            return
        tipo = TIPO_TENTATIVO[p["modalita"]]
        nel_piano = self._del_piano(v["id"])
        persona = (chi if chi is not None and getattr(chi, "id", None) == v["persona"]
                   else self._profilo(v["persona"]))
        for x in p["voci"]:
            if (x.get("esito") not in RS.DECISI or x.get("tentativo")
                    or x.get("argomento") not in nel_piano):
                continue
            fonte = x.get("fonte_esito") or "codice"
            chi_reg = chi if fonte == "tutore" else persona
            if chi_reg is None:
                continue
            try:
                x["tentativo"] = self.registra_tentativo(chi_reg, v["id"], x["argomento"], tipo,
                                                         x["esito"], fonte)
            except Exception as e:  # noqa: BLE001 — un tentativo che non va non ferma la prova
                self._registra(f"tentativo della prova {p['id']} non scritto: "
                               f"{type(e).__name__}")

    def _riepilogo_prova(self, p: dict, v: dict) -> dict:
        """I conti per argomento (col numero dell'elenco, mai il titolo), i totali, il punteggio
        (giusto 1, indizio 0,5 sulle decise) e il confronto con la prova di prima della stessa
        modalità. Il punteggio c'è solo se almeno metà delle voci date è decisa dal codice o dal
        tutore (una prova di sole aperte non fa un numero)."""
        numeri = {a["id"]: i for i, a in enumerate(self.dati.tutti(
            "SELECT id FROM studio_argomenti WHERE verifica = ? ORDER BY ordine, id",
            (v["id"],)), 1)}
        per: dict = {}
        tot = {k: 0 for k in RS.ESITI}
        for x in p["voci"]:
            e = x.get("esito") or RS.VUOTA
            tot[e] = tot.get(e, 0) + 1
            a = per.setdefault(str(numeri.get(x.get("argomento"), 0)), {k: 0 for k in RS.ESITI})
            a[e] += 1
        decise = [x for x in p["voci"] if x.get("esito") in RS.DECISI]
        affidabili = [x for x in decise if x.get("fonte_esito") in ("codice", "tutore")]
        date = [x for x in p["voci"] if x.get("esito") != RS.VUOTA]
        vuote = [x for x in p["voci"] if x.get("esito") == RS.VUOTA]
        punteggio = None
        # Revisione della PR #342: nella scritta le vuote valgono 0 (rispondere solo a quella che
        # si sa non dà 100); nell'orale le voci sono già le sole domande fatte. Il punteggio c'è
        # solo con almeno metà delle domande con una risposta e metà delle date decise dal codice
        # o dal tutore
        contate = decise + vuote
        if (decise and len(affidabili) * 2 >= max(1, len(date))
                and len(date) * 2 >= max(1, len(p["voci"]))):
            punti = sum(PD.ESITI[x["esito"]] for x in decise)
            punteggio = int(round(100 * punti / len(contate)))
        prima = self.dati.uno("SELECT riepilogo FROM studio_prove WHERE verifica = ? AND "
                              "modalita = ? AND stato IN ('consegnata', 'scaduta') AND id < ? "
                              "ORDER BY id DESC LIMIT 1", (v["id"], p["modalita"], p["id"]))
        prec = _da(prima["riepilogo"], {}).get("punteggio") if prima else None
        # Le mappe senza guardare chiuse dopo l'inizio di questa prova (una prova possibile,
        # col suo controllo: qui solo citate, mai mescolate nel punteggio)
        mappe = []
        for m in self.dati.tutti("SELECT tipo, controllo, controllata FROM studio_mappe WHERE "
                                 "verifica = ? AND tipo IN ('memoria', 'libera') AND controllata "
                                 ">= ?", (v["id"], p["inizio"])):
            k = (_da(m["controllo"], {}) or {}).get("conti") or {}
            if m["tipo"] == "memoria" and k:
                mappe.append({"tipo": "memoria", "giuste": int(k.get("giusta") or 0),
                              "su": sum(int(k.get(x) or 0) for x in ("giusta", "sbagliata",
                                                                     "vuota"))})
            elif m["tipo"] == "libera" and k.get("chiave"):
                mappe.append({"tipo": "libera", "giuste": int(k.get("trovati") or 0),
                              "su": int(k.get("chiave") or 0)})
        return {"per_argomento": per, "totali": tot, "punteggio": punteggio,
                "prima": prec, "domande": len(p["voci"]), "mappe": mappe,
                "poche_risposte": len(date) * 2 < max(1, len(p["voci"]))}

    def _misura_prova(self, p: dict, v: dict):
        """La misura vera della prova in `studio_misure` («l'ultima prova» del piano), con la
        fonte «verifica_finta» o «interrogazione»; solo col punteggio."""
        pt = p["riepilogo"].get("punteggio")
        if pt is None or not self.dati.scrivibile:
            return
        self.dati.scrivi("INSERT INTO studio_misure (verifica, giorno, valore, fonte) VALUES "
                         "(?, ?, ?, ?)", (v["id"], self._oggi().isoformat(), float(pt),
                                          TIPO_TENTATIVO[p["modalita"]]))

    def rivedi_voce(self, chi, pid, n: int, esito: str) -> dict:
        """«Era giusta / Quasi / No» su una voce da rivedere di una prova chiusa: la persona
        (fonte «persona», peso dimezzato) o il tutore (fonte «tutore»), una volta per voce."""
        self._scrivibile()
        if esito not in RS.REVISIONI:
            raise ValueError("esito sconosciuto")
        with self.dati.lock:
            p, v = self._prova(chi, pid)
            if p["stato"] not in (CONSEGNATA, SCADUTA):
                raise ValueError("la prova non è ancora consegnata")
            voce = next((x for x in p["voci"] if x["n"] == int(n)), None)
            if voce is None or voce.get("esito") != RS.DA_RIVEDERE:
                raise ValueError("questa risposta non è da rivedere")
            ruolo = self._chi_puo(chi, v["persona"])
            # Sulle domande chiuse la persona dà al più «indizio» (revisione della PR #342): una
            # risposta a cavallo o negata non diventa «giusto» con l'autovalutazione
            if ruolo == "proprietario" and voce.get("tipo") in RS.CHIUSE and esito == RS.GIUSTO:
                esito = RS.INDIZIO
            voce["esito"] = esito
            voce["fonte_esito"] = "persona" if ruolo == "proprietario" else "tutore"
            p["riepilogo"] = self._riepilogo_prova(p, v)
            n_ = self.dati.scrivi("UPDATE studio_prove SET voci = ?, riepilogo = ? WHERE id = ? "
                                  "AND stato = ?", (_j(p["voci"]), _j(p["riepilogo"]), p["id"],
                                                    p["stato"]))
            if n_:
                self._tentativi_prova(p, v, chi)
                self.dati.scrivi("UPDATE studio_prove SET voci = ? WHERE id = ?",
                                 (_j(p["voci"]), p["id"]))
                self.misure["prove"]["riviste"] += 1
                if voce.get("proposta"):
                    m = self.misure["prove"]
                    m["proposte_confrontate"] += 1
                    m["proposte_uguali"] += RS.PROPOSTE.get(voce["proposta"]) == esito
                self._registra(f"verifica {v['id']}: prova {p['id']}, voce {voce['n']} rivista "
                               f"({voce['fonte_esito']}): {esito}")
            return self._vista(p, chi, v)

    def _chiudi_prove(self, vid, motivo: str) -> int:
        """La verifica non è più aperta: le prove aperte si chiudono davvero, «annullate», senza
        tentativi (come `_chiudi_scadute` delle mappe). Quante."""
        if not self.dati.scrivibile:
            return 0
        n = 0
        with self.dati.lock:
            try:
                righe = self.dati.tutti("SELECT * FROM studio_prove WHERE verifica = ? AND "
                                        "stato = 'aperta'", (int(vid),))
            except Exception:  # noqa: BLE001 — schema di prima
                return 0
            for r in righe:
                self._chiudi_prova(self._riga_prova(r), ANNULLATA)
                n += 1
        if n:
            self._registra(f"verifica {vid}: {n} prove annullate ({motivo})")
        return n

    def _frase_prova(self, p: dict, nome: str | None = None) -> str:
        """La frase del codice sul riepilogo (per la voce e lo schermo): conti, argomenti col
        numero, mai il testo. Al tutore in terza persona col nome."""
        rp = p.get("riepilogo") or {}
        t = rp.get("totali") or {}
        if p["stato"] == ANNULLATA:
            return "La prova è stata chiusa senza esito: la verifica non è più aperta."
        chi = "Hai" if nome is None else (f"{nome} ha" if nome else "Ha")
        n = int(rp.get("domande") or 0)
        g = int(t.get(RS.GIUSTO, 0))
        pezzi = [f"{chi} risposto giusto a {g} domand{'a' if g == 1 else 'e'} su {n}"]
        if t.get(RS.INDIZIO):
            pezzi.append(f"{t[RS.INDIZIO]} a metà")
        if t.get(RS.SBAGLIATO):
            pezzi.append(f"{t[RS.SBAGLIATO]} sbagliat{'a' if t[RS.SBAGLIATO] == 1 else 'e'}")
        if t.get(RS.DA_RIVEDERE):
            pezzi.append(f"{t[RS.DA_RIVEDERE]} da rivedere")
        if t.get(RS.VUOTA):
            pezzi.append(f"{t[RS.VUOTA]} senza risposta")
        frase = ", ".join(pezzi) + "."
        if rp.get("poche_risposte"):
            frase += " Con meno di metà delle risposte la prova non conta come misura."
        deboli = sorted(((k, a) for k, a in (rp.get("per_argomento") or {}).items()
                         if k != "0" and a.get(RS.SBAGLIATO, 0) + a.get(RS.INDIZIO, 0) > 0),
                        key=lambda x: -(x[1].get(RS.SBAGLIATO, 0) * 2 + x[1].get(RS.INDIZIO, 0)))
        if deboli:
            frase += f" Da riprendere l'argomento {deboli[0][0]}."
        if rp.get("punteggio") is not None and rp.get("prima") is not None:
            d = rp["punteggio"] - rp["prima"]
            frase += (" Meglio della volta scorsa." if d > 0 else
                      " Come la volta scorsa." if d == 0 else " Meno della volta scorsa.")
        if t.get(RS.DA_RIVEDERE):
            frase += (" Le risposte da rivedere si decidono nello Studio, guardando quella "
                      "attesa." if nome is None else
                      " Le risposte da rivedere si possono decidere nello Studio.")
        return frase

    # ─────────────────────────── l'orale ───────────────────────────
    def _orale(self, chi) -> tuple[dict, dict] | None:
        """La prova orale aperta di chi parla (la sua, mai quella di un altro), dopo la
        scadenza per la pausa."""
        r = self.dati.uno("SELECT p.* FROM studio_prove p JOIN studio_verifiche v ON v.id = "
                          "p.verifica WHERE p.persona = ? AND p.modalita = 'orale' AND p.stato = "
                          "'aperta' AND v.stato IN ('bozza', 'aperta') ORDER BY p.id DESC LIMIT 1",
                          (str(getattr(chi, "id", "") or ""),))
        if r is None:
            return None
        p, v = self._prova(chi, r["id"])
        return (p, v) if p["stato"] == APERTA else None

    def _domanda_orale(self, p: dict, turno: int) -> dict | None:
        """La voce in corso dell'orale, segnata «chiesta» in questo turno."""
        if p["corrente"] >= len(p["voci"]):
            return None
        x = p["voci"][p["corrente"]]
        self._orali[str(p["persona"])] = {"prova": p["id"], "n": x["n"], "turno": int(turno)}
        # Anche su disco il turno e l'ora della domanda (revisione della PR #342): dopo un
        # riavvio la risposta si valuta, ma mai nello stesso turno di una domanda di adesso
        x["chiesta"] = {"turno": int(turno), "ora": self.adesso().isoformat(timespec="seconds")}
        self.dati.scrivi("UPDATE studio_prove SET voci = ? WHERE id = ? AND stato = 'aperta'",
                         (_j(p["voci"]), p["id"]))
        return {"n": x["n"], "di": len(p["voci"]), "tipo": x["tipo"], "testo": x["testo"],
                "opzioni": list(x.get("opzioni") or ())}

    def orale_inizia(self, chi, vid, turno: int = 0) -> dict:
        """Apre (o riprende) l'interrogazione orale: {prova, domanda}."""
        with self.dati.lock:
            vista = self.inizia_prova(chi, vid, ORALE)
            p, _v = self._prova(chi, vista["id"])
            return {"prova": p["id"], "verifica": p["verifica"],
                    "domanda": self._domanda_orale(p, turno)}

    def orale_ripeti(self, chi, turno: int = 0) -> dict | None:
        with self.dati.lock:
            o = self._orale(chi)
            if o is None:
                return None
            return {"prova": o[0]["id"], "domanda": self._domanda_orale(o[0], turno)}

    def orale_risposta(self, chi, frase: str, turno: int = 0, proposta=None) -> dict:
        """La risposta detta alla domanda in corso: l'esito dal codice (`risposte.valuta`) sulla
        frase della persona, mai sulla proposta del modello (che resta una misura). Una volta per
        domanda, mai nel turno in cui è stata chiesta. Poi la domanda dopo (nello stesso
        risultato) o, finite, la chiusura con i tentativi e il riepilogo.
        {"motivo"} senza valutazione: «nessuna», «stesso_turno»."""
        self._scrivibile()
        with self.dati.lock:
            o = self._orale(chi)
            if o is None:
                return {"motivo": "nessuna"}
            p, v = o
            if self._chi_puo(chi, v["persona"]) != "proprietario":
                return {"motivo": "nessuna"}
            chiesta = self._orali.get(str(p["persona"])) or {}
            x = p["voci"][p["corrente"]] if p["corrente"] < len(p["voci"]) else None
            if x is None:
                self._chiudi_prova(p, CONSEGNATA, chi)
                return self._fine_orale(chi, p["id"])
            if not (chiesta.get("prova") == p["id"] and chiesta.get("n") == x["n"]):
                # Niente in memoria (un riavvio): vale la domanda scritta nella prova; chiesta
                # prima dell'avvio di questo processo si valuta sempre
                su_disco = x.get("chiesta") or {}
                avvio = getattr(self, "_avvio", None)
                prima = (not su_disco.get("ora") or avvio is None
                         or datetime.datetime.fromisoformat(su_disco["ora"]) < avvio)
                chiesta = {} if prima else {"prova": p["id"], "n": x["n"],
                                            "turno": su_disco.get("turno")}
            if chiesta.get("prova") == p["id"] and chiesta.get("n") == x["n"] and \
                    int(turno or 0) <= int(chiesta.get("turno") or 0):
                return {"motivo": "stesso_turno", "domanda": {"n": x["n"], "testo": x["testo"]}}
            x["risposta"] = RS.riga(frase, RS.RISPOSTA_MAX) or None
            x["esito"], x["fonte_esito"] = RS.valuta(x, frase)
            if isinstance(proposta, str) and proposta in RS.PROPOSTE:
                x["proposta"] = proposta
                self.misure["prove"]["proposte"] += 1
            p["corrente"] += 1
            adesso = self.adesso().isoformat(timespec="seconds")
            self.dati.scrivi("UPDATE studio_prove SET voci = ?, corrente = ?, ultima = ? WHERE "
                             "id = ? AND stato = 'aperta'",
                             (_j(p["voci"]), p["corrente"], adesso, p["id"]))
            p["ultima"] = adesso
            esito = {"n": x["n"], "esito": x["esito"], "fonte": x["fonte_esito"],
                     "attesa": RS.attesa_detta(x), "tipo": x["tipo"]}
            if p["corrente"] >= len(p["voci"]):
                self._chiudi_prova(p, CONSEGNATA, chi)
                return {**self._fine_orale(chi, p["id"]), "valutata": esito}
            return {"valutata": esito, "domanda": self._domanda_orale(p, turno),
                    "prova": p["id"]}

    def orale_basta(self, chi) -> dict:
        """«Basta così»: chiude l'orale con le voci già valutate (tentativi e riepilogo)."""
        with self.dati.lock:
            o = self._orale(chi)
            if o is None:
                return {"motivo": "nessuna"}
            self._chiudi_prova(o[0], CONSEGNATA, chi)
            return self._fine_orale(chi, o[0]["id"])

    def _fine_orale(self, chi, pid) -> dict:
        self._orali.pop(str(getattr(chi, "id", "") or ""), None)
        p, v = self._prova(chi, pid)
        return {"prova": p["id"], "chiusa": True, "frase": self._frase_prova(
            p, self._nome_per(chi, v)), "riepilogo": p["riepilogo"]}

    def _conto_prove(self, v: dict) -> dict:
        """Solo conti per la home e la voce: la prova aperta, l'ultima per modalità (punteggio),
        quante domande pronte."""
        try:
            aperta = self._prova_aperta(v["id"])
            ultime = {}
            for m in MODALITA:
                r = self.dati.uno("SELECT id, riepilogo, fine FROM studio_prove WHERE verifica = "
                                  "? AND modalita = ? AND stato IN ('consegnata', 'scaduta') "
                                  "ORDER BY id DESC LIMIT 1", (v["id"], m))
                if r:
                    rp = _da(r["riepilogo"], {})
                    ultime[m] = {"punteggio": rp.get("punteggio"), "fine": r["fine"],
                                 "da_rivedere": int((rp.get("totali") or {}).get(RS.DA_RIVEDERE,
                                                                                 0))}
            pronte = len(self._pool(v))
        except Exception:  # noqa: BLE001 — schema di prima
            return {"aperta": None, "ultime": {}, "pronte": 0, "minimo": PROVA_MIN}
        return {"aperta": ({"id": aperta["id"], "modalita": aperta["modalita"]}
                           if aperta else None),
                "ultime": ultime, "pronte": pronte, "minimo": PROVA_MIN}
