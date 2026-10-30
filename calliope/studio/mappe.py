"""
Le mappe concettuali nel servizio dello Studio (30/10, passo 7, issue #247, decisione 0035 punto
35): i metodi di `Studio` sopra la tabella `studio_mappe` (schema 8) e la parte pura di `mappa.py`.

**Chi.** Lo scheletro lo vedono e lo cambiano la persona e il tutore del suo minore; la mappa dello
studente e le ricostruzioni a memoria le vedono tutti e due (il tutore scarica il PDF) ma le cambia
solo la persona: il PDF dice di chi è (scelta prudente del passo 7, da confermare). Un altro adulto,
l'ospite e chi non è riconosciuto mai, con lo stesso «non c'è» di una verifica che non c'è. Uno
scheletro in stato «ombra» (dalla generazione in ombra) non va mai alla persona.

**Il testo è un dato**: nel registro solo id, conti ed esiti; la vista per lo schermo (`vista_mappe`)
non contiene mai il testo atteso delle caselle, e mentre una mappa a memoria è aperta manda a chi la
fa lo scheletro e la mia mappa senza i testi. Al modello arriva solo come carta («Fanne carte»), in
busta.

**Lo scheletro confermato con le copie è in sola lettura** (revisione della PR #326): cambiarlo
cambierebbe le risposte attese di una mappa già fatta. «Riapri lo scheletro» (la persona o il
tutore) lo riporta a «proposto» e toglie la mia mappa e quella a memoria (i tentativi restano), che
si rifanno dopo la nuova conferma.

**Una cosa per volta**: ogni azione legge e scrive dentro `dati.lock` (un RLock), così due
«Controlla» o due «Parti da qui» insieme non scrivono due volte.

**Tentativi.** «Controlla» scrive un tentativo di tipo «mappa» (fonte «codice») per ogni casella
riempita, una volta per casella per giro (`tentati`); «Rifai» apre un giro nuovo.
"""

from __future__ import annotations

import json

from . import dati as D
from . import mappa as M
from . import padronanza as PD

_UGUALE = object()
SOLA_LETTURA = ("lo scheletro è confermato e ci sono le mappe fatte da lì: per cambiarlo, «Riapri "
                "lo scheletro»")
# La mappa a memoria dopo il primo «Controlla» (seconda revisione della PR #326): non si cambia
# più, si riparte con «Rifai» (altrimenti, con lo scheletro di nuovo visibile, si copiava e si
# ricontrollava)
MEMORIA_CHIUSA = "la mappa a memoria è già controllata: per rifarla, «Rifai»"


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False)


def _da_j(t, vuoto):
    try:
        v = json.loads(t) if t else vuoto
    except (TypeError, ValueError):
        return vuoto
    return v if isinstance(v, type(vuoto)) else vuoto


class Mappe:
    """Mescolata in `Studio` (servizio.py): usa `dati`, `_verifica`, `_chi_puo`, `_scrivibile`,
    `_pagine_di`, `_registra`, `registra_tentativo`, `padronanza_mostrata`, `_padronanza`."""

    # ── leggere ──
    def _riga_mappa(self, mid) -> dict | None:
        m = self.dati.uno("SELECT * FROM studio_mappe WHERE id = ?", (int(mid),))
        if m is None:
            return None
        m["nodi"] = [n for n in _da_j(m["nodi"], []) if isinstance(n, dict)]
        m["collegamenti"] = [c for c in _da_j(m["collegamenti"], []) if isinstance(c, dict)]
        m["controllo"] = _da_j(m["controllo"], {}) or None
        m["aiuto"] = _da_j(m["aiuto"], {})
        m["tentati"] = [int(x) for x in _da_j(m["tentati"], []) if str(x).lstrip("-").isdecimal()]
        return m

    def _copie(self, vid) -> list[int]:
        return [r["id"] for r in self.dati.tutti(
            "SELECT id FROM studio_mappe WHERE verifica = ? AND tipo IN ('studente', 'memoria')",
            (int(vid),))]

    def _mappa(self, chi, mid, cambia: bool = False, riapri: bool = False,
               chiusa_ok: bool = False) -> tuple[dict, dict]:
        """(mappa, verifica) se `chi` la può vedere (o, con `cambia`, cambiare); altrimenti
        NonTrovata, come una verifica che non c'è. Uno scheletro confermato con le copie non si
        cambia (ValueError, `SOLA_LETTURA`), tranne che per riaprirlo (`riapri`); una mappa a
        memoria controllata nemmeno (`MEMORIA_CHIUSA`), tranne che per «Rifai», «Fanne carte» e un
        altro «Controlla», che non cambia niente (`chiusa_ok`)."""
        from .servizio import NonTrovata, VerificaChiusa
        m = self._riga_mappa(mid)
        if m is None or m["stato"] == "ombra":
            raise NonTrovata()
        v = self._verifica(chi, m["verifica"])
        if cambia:
            self._scrivibile()
            if v["stato"] not in ("bozza", "aperta"):
                raise VerificaChiusa()
            if m["tipo"] != M.SCHELETRO and self._chi_puo(chi, v["persona"]) != "proprietario":
                raise NonTrovata()
            if (m["tipo"] == M.SCHELETRO and m["stato"] == "confermata" and not riapri
                    and self._copie(v["id"])):
                raise ValueError(SOLA_LETTURA)
            if m["tipo"] == M.MEMORIA and m["stato"] == "controllata" and not chiusa_ok:
                raise ValueError(MEMORIA_CHIUSA)
        return m, v

    def _mappe_di(self, vid) -> dict:
        """{tipo: la mappa più recente di quel tipo} di una verifica, senza quelle dell'ombra."""
        out = {}
        for r in self.dati.tutti("SELECT id, tipo FROM studio_mappe WHERE verifica = ? AND "
                                 "stato != 'ombra' ORDER BY id", (int(vid),)):
            out[r["tipo"]] = r["id"]
        return {t: self._riga_mappa(i) for t, i in out.items()}

    def _scheletro_confermato(self, vid) -> dict | None:
        s = self._mappe_di(vid).get(M.SCHELETRO)
        return s if s is not None and s["stato"] == "confermata" else None

    def _salva_mappa(self, m: dict, **campi):
        """Scrive i campi di una mappa. Lo scrivono solo le azioni della persona (o del tutore):
        uno scheletro cambiato così è «toccato», e la generazione non lo rifà più (`aiuto`)."""
        campi.setdefault("modificata", self.adesso().isoformat(timespec="seconds"))
        if m.get("tipo") == M.SCHELETRO and "aiuto" not in campi:
            campi["aiuto"] = {**(m.get("aiuto") or {}), "toccato": True}
        sets, arg = [], []
        for k, val in campi.items():
            if k in ("nodi", "collegamenti", "tentati", "aiuto", "controllo"):
                val = _j(val) if val is not None else None
            sets.append(f"{k} = ?")
            arg.append(val)
        self.dati.scrivi(f"UPDATE studio_mappe SET {', '.join(sets)} WHERE id = ?",
                         (*arg, int(m["id"])))

    def _misure_mappe(self) -> dict:
        return self.misure.setdefault("mappe", {"scheletri": 0, "mie": 0, "memoria": 0,
                                                "controlli": 0, "tentativi": 0, "carte": 0})

    # ── lo scheletro scritto a mano ──
    def scrivi_scheletro(self, chi, vid) -> int:
        """Uno scheletro vuoto da scrivere a mano (la persona o il tutore), «proposto» finché non
        lo conferma; se ce n'è già uno (non dell'ombra), quello."""
        from .servizio import VerificaChiusa
        self._scrivibile()
        v = self._verifica(chi, vid)
        if v["stato"] not in ("bozza", "aperta"):
            raise VerificaChiusa()
        c = self._mappe_di(v["id"]).get(M.SCHELETRO)
        if c is not None:
            return c["id"]
        adesso = self.adesso().isoformat(timespec="seconds")
        mid = self.dati.scrivi(
            "INSERT INTO studio_mappe (verifica, persona, tipo, stato, origine, creata, creata_da) "
            "VALUES (?, ?, 'scheletro', 'proposta', 'persona', ?, ?)",
            (v["id"], str(v["persona"]), adesso, getattr(chi, "id", None)))
        self._misure_mappe()["scheletri"] += 1
        self._registra(f"verifica {v['id']}: scheletro {mid} da scrivere "
                       f"({self._chi_registro(chi, v['persona'])})")
        return mid

    def _autore(self, chi, v) -> str:
        return "persona" if getattr(chi, "id", None) == v["persona"] else "tutore"

    def _pagine_ok(self, v, pagine) -> list[int]:
        sue = {int(p["id"]) for p in self._pagine_di(v["id"])}
        pag = [int(x) for x in pagine or ()]
        if any(x not in sue for x in pag):
            raise ValueError("una pagina non è di questa verifica")
        return list(dict.fromkeys(pag))

    def nodo_mappa(self, chi, mid, testo, nodo=None, argomento=_UGUALE, pagine=None) -> int:
        """Un concetto nuovo (senza `nodo`) o il testo cambiato di uno che c'è. Nello scheletro un
        concetto scritto da una persona è subito «tenuto»; nella mappa dello studente la persona
        aggiunge i suoi e cambia solo quelli suoi (le caselle si riempiono con `riempi`)."""
        from .servizio import NonTrovata
        t = M.testo_normale(testo, M.NODO_MAX)
        with self.dati.lock:
            m, v = self._mappa(chi, mid, cambia=True)
            nodi = m["nodi"]
            if nodo is None:
                if m["tipo"] == M.SCHELETRO and len(nodi) >= M.nodi_max(self.cfg):
                    raise ValueError(f"al più {M.nodi_max(self.cfg)} concetti")
                if m["tipo"] != M.SCHELETRO and sum(n.get("da") is None
                                                   for n in nodi) >= M.SUOI_MAX:
                    raise ValueError(f"al più {M.SUOI_MAX} concetti tuoi in più")
                aid = (self._argomento_di(v, argomento) if argomento is not _UGUALE else None)
                x, y = M.libero(nodi)
                nid = max([int(n["id"]) for n in nodi] + [0]) + 1
                nodi.append({"id": nid, "testo": t, "pagine": self._pagine_ok(v, pagine),
                             "argomento": aid, "autore": self._autore(chi, v), "stato": "tenuto",
                             "avvisi": [], "x": x, "y": y, "da": None, "casella": False})
            else:
                n = next((n for n in nodi if int(n["id"]) == int(nodo)), None)
                if n is None or (m["tipo"] != M.SCHELETRO and (n.get("da") is not None
                                                               or n.get("casella"))):
                    raise NonTrovata()
                n["testo"] = t
                if m["tipo"] == M.SCHELETRO:
                    # Cambiato da una persona: suo, tenuto, senza gli avvisi del modello
                    n.update(autore=self._autore(chi, v), stato="tenuto", avvisi=[])
                if argomento is not _UGUALE:
                    n["argomento"] = self._argomento_di(v, argomento)
                if pagine is not None:
                    n["pagine"] = self._pagine_ok(v, pagine)
                nid = int(n["id"])
            self._salva_mappa(m, nodi=nodi)
        return nid

    def togli_nodo(self, chi, mid, nodo):
        """Toglie un concetto e i suoi collegamenti. Nella mappa dello studente solo quelli suoi:
        i concetti dello scheletro restano (le caselle si svuotano con `riempi`)."""
        from .servizio import NonTrovata
        with self.dati.lock:
            m, _v = self._mappa(chi, mid, cambia=True)
            n = next((n for n in m["nodi"] if int(n["id"]) == int(nodo)), None)
            if n is None or (m["tipo"] != M.SCHELETRO and n.get("da") is not None):
                raise NonTrovata()
            nodi = [x for x in m["nodi"] if x is not n]
            coll = [c for c in m["collegamenti"] if int(nodo) not in (int(c["da"]), int(c["a"]))]
            self._salva_mappa(m, nodi=nodi, collegamenti=coll)

    def collega(self, chi, mid, da, a, verbo, collegamento=None) -> int:
        """Un collegamento nuovo da `da` ad `a` col verbo (senza `collegamento`), o il verbo
        cambiato di uno che c'è. Niente collegamenti di un concetto con sé stesso né doppi."""
        from .servizio import NonTrovata
        vb = M.testo_normale(verbo, M.VERBO_MAX)
        with self.dati.lock:
            m, v = self._mappa(chi, mid, cambia=True)
            coll = m["collegamenti"]
            ids = {int(n["id"]) for n in m["nodi"]}
            if collegamento is not None:
                c = next((c for c in coll if int(c["id"]) == int(collegamento)), None)
                if c is None:
                    raise NonTrovata()
                c["verbo"] = vb
                if m["tipo"] == M.SCHELETRO:
                    c.update(autore=self._autore(chi, v), stato="tenuto", avvisi=[])
                cid = int(c["id"])
            else:
                if int(da) not in ids or int(a) not in ids:
                    raise NonTrovata()
                if int(da) == int(a):
                    raise ValueError("un concetto non si collega con sé stesso")
                if any({int(c["da"]), int(c["a"])} == {int(da), int(a)} for c in coll):
                    raise ValueError("questi due concetti sono già collegati")
                tetto = 2 * M.nodi_max(self.cfg) + (0 if m["tipo"] == M.SCHELETRO
                                                     else 2 * M.SUOI_MAX)
                if len(coll) >= tetto:
                    raise ValueError("troppi collegamenti")
                cid = max([int(c["id"]) for c in coll] + [0]) + 1
                coll.append({"id": cid, "da": int(da), "a": int(a), "verbo": vb, "pagine": [],
                             "autore": self._autore(chi, v), "stato": "tenuto", "avvisi": [],
                             "origine": None})
            self._salva_mappa(m, collegamenti=coll)
        return cid

    def togli_collegamento(self, chi, mid, collegamento):
        from .servizio import NonTrovata
        with self.dati.lock:
            m, _v = self._mappa(chi, mid, cambia=True)
            coll = [c for c in m["collegamenti"] if int(c["id"]) != int(collegamento)]
            if len(coll) == len(m["collegamenti"]):
                raise NonTrovata()
            self._salva_mappa(m, collegamenti=coll)

    def sposta_nodo(self, chi, mid, nodo, x, y):
        """Sposta un concetto (frazioni della mappa, 0,05–0,95): solo il disegno, il significato
        non cambia. Dal trascinamento o dalle frecce del pannello (niente solo trascinando)."""
        from .servizio import NonTrovata
        x, y = float(x), float(y)
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError("fuori dalla mappa")
        with self.dati.lock:
            m, _v = self._mappa(chi, mid, cambia=True)
            n = next((n for n in m["nodi"] if int(n["id"]) == int(nodo)), None)
            if n is None:
                raise NonTrovata()
            n["x"], n["y"] = round(min(0.95, max(0.05, x)), 3), round(min(0.95, max(0.05, y)), 3)
            self._salva_mappa(m, nodi=m["nodi"])

    def riempi(self, chi, mid, nodo, testo):
        """La parola della persona in una casella vuota ("" la svuota)."""
        from .servizio import NonTrovata
        t = M.testo_normale(testo, M.NODO_MAX, vuoto=True)
        with self.dati.lock:
            m, _v = self._mappa(chi, mid, cambia=True)
            n = next((n for n in m["nodi"] if int(n["id"]) == int(nodo)), None)
            if n is None or not n.get("casella"):
                raise NonTrovata()
            n["testo"] = t
            self._salva_mappa(m, nodi=m["nodi"])

    def tieni_mappa(self, chi, mid, nodo=None, collegamento=None):
        """Nello scheletro, un concetto o un collegamento proposto con un avviso: la persona (o il
        tutore) lo tiene, uno per uno (come «Tieni» delle carte)."""
        from .servizio import NonTrovata
        with self.dati.lock:
            m, _v = self._mappa(chi, mid, cambia=True)
            if m["tipo"] != M.SCHELETRO:
                raise NonTrovata()
            voci = m["nodi"] if nodo is not None else m["collegamenti"]
            k = nodo if nodo is not None else collegamento
            x = next((x for x in voci if int(x["id"]) == int(k)), None) if k is not None else None
            if x is None:
                raise NonTrovata()
            x["stato"] = "tenuto"
            self._salva_mappa(m, nodi=m["nodi"], collegamenti=m["collegamenti"])

    def conferma_scheletro(self, chi, mid) -> dict:
        """«Conferma lo scheletro»: i concetti e i collegamenti proposti senza avvisi diventano
        tenuti, quelli con un avviso restano proposti (la persona li tiene uno per uno); servono
        almeno `mappa.MIN_CONFERMA` concetti tenuti. {tenuti, da_decidere}."""
        from .servizio import NonTrovata
        with self.dati.lock:
            m, v = self._mappa(chi, mid, cambia=True)
            if m["tipo"] != M.SCHELETRO:
                raise NonTrovata()
            d = 0
            for x in m["nodi"] + m["collegamenti"]:
                if x.get("stato") == "proposto":
                    if x.get("avvisi"):
                        d += 1
                    else:
                        x["stato"] = "tenuto"
            nodi, _coll = M.tenuti(m)
            if len(nodi) < M.MIN_CONFERMA:
                raise ValueError(f"servono almeno {M.MIN_CONFERMA} concetti")
            self._salva_mappa(m, nodi=m["nodi"], collegamenti=m["collegamenti"],
                              stato="confermata")
        self._registra(f"verifica {v['id']}: scheletro {m['id']} confermato, {len(nodi)} "
                       f"concetti, {d} da decidere ({self._chi_registro(chi, v['persona'])})")
        return {"tenuti": len(nodi), "da_decidere": d}

    def riordina_mappa(self, chi, mid):
        """«Riordina»: la disposizione calcolata dal codice (`mappa.disposizione`: al centro il
        concetto con più collegamenti, gli altri attorno), al posto di quella a mano."""
        with self.dati.lock:
            m, _v = self._mappa(chi, mid, cambia=True)
            pos = M.disposizione(m["nodi"], m["collegamenti"])
            for n in m["nodi"]:
                n["x"], n["y"] = pos.get(int(n["id"]), (n.get("x"), n.get("y")))
            self._salva_mappa(m, nodi=m["nodi"])

    def riapri_scheletro(self, chi, mid) -> dict:
        """«Riapri lo scheletro» (la persona o il tutore): di nuovo «proposto», da confermare; la
        mia mappa e quella a memoria fatte da lì vanno via (i tentativi già scritti restano) e si
        rifanno dopo la nuova conferma. {copie_tolte}."""
        from .servizio import NonTrovata
        with self.dati.lock:
            m, v = self._mappa(chi, mid, cambia=True, riapri=True)
            if m["tipo"] != M.SCHELETRO or m["stato"] != "confermata":
                raise NonTrovata()
            db = self.dati.db
            try:
                n = db.execute("DELETE FROM studio_mappe WHERE verifica = ? AND tipo IN "
                               "('studente', 'memoria')", (v["id"],)).rowcount or 0
                db.execute("UPDATE studio_mappe SET stato = 'proposta', modificata = ? WHERE id = ?",
                           (self.adesso().isoformat(timespec="seconds"), m["id"]))
                db.commit()
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
        self._registra(f"verifica {v['id']}: scheletro {m['id']} riaperto, {n} mappe tolte "
                       f"({self._chi_registro(chi, v['persona'])})")
        return {"copie_tolte": n}

    # ── la mia mappa e a memoria ──
    def _deboli(self, v) -> tuple[list, str]:
        """(gli argomenti dal più debole, l'aiuto di serie): dalla padronanza solo se mostrata
        (in ombra non si usa: sarebbe mostrarla di nascosto); altrimenti niente e «medio»."""
        if not self.padronanza_mostrata():
            return [], M.AIUTO_DI_SERIE
        p = self._padronanza(v)
        misurati = sorted((a for a in p["argomenti"] if a["valore"] is not None),
                          key=lambda a: a["valore"])
        lv = p.get("livello")
        aiuto = ("tanto" if lv is None or lv < 45 else "medio" if lv < 75 else "poco")
        return [a["id"] for a in misurati], aiuto

    def _prossimo_giro(self, s: dict) -> int:
        """Il giro della copia nuova: un contatore sullo scheletro (`aiuto.giro`), che cresce a
        ogni copia e resta dopo «Riapri lo scheletro», così le caselle non si ripetono (seconda
        revisione della PR #326). Dentro il lock di chi chiama."""
        a = dict(s.get("aiuto") or {})
        giro = int(a.get("giro", -1)) + 1
        a["giro"] = giro
        self.dati.scrivi("UPDATE studio_mappe SET aiuto = ? WHERE id = ?", (_j(a), int(s["id"])))
        s["aiuto"] = a
        return giro

    def _nuova_copia(self, v, s, tipo, aiuto, giro) -> tuple[list, list, dict]:
        deboli, di_serie = self._deboli(v)
        aiuto = aiuto if aiuto in M.AIUTI else di_serie
        nodi_s, coll_s = M.tenuti(s)
        caselle = M.scegli_caselle(nodi_s, M.AIUTI[aiuto], deboli, giro, coll_s)
        nodi, coll = M.copia(s, caselle, con_pagine=tipo == M.STUDENTE)
        attese = [n["testo"] for n in nodi_s if int(n["id"]) in caselle]
        altre = [a["titolo"] for a in self._argomenti_per_carte(v["id"])] + \
                [n["testo"] for n in nodi_s if int(n["id"]) not in caselle]
        return nodi, coll, {"livello": aiuto, "giro": int(giro),
                            "parole": M.parole_da_mettere(attese, altre)}

    def inizia_mappa(self, chi, vid, tipo: str, aiuto: str | None = None) -> int:
        """«Parti da qui: fai la tua» (la mia mappa, con il libro) o «Rifai la mappa a memoria»:
        una copia dello scheletro confermato con le caselle vuote. La mia mappa è una sola (se c'è,
        quella); a memoria se ne apre una nuova al posto di quella di prima (i tentativi restano).
        Solo la persona. Tutto dentro il lock: due «Parti da qui» insieme danno una mappa sola."""
        from .servizio import NonTrovata, VerificaChiusa
        if tipo not in (M.STUDENTE, M.MEMORIA):
            raise ValueError("tipo sconosciuto")
        with self.dati.lock:
            self._scrivibile()
            v = self._verifica(chi, vid)
            if v["stato"] not in ("bozza", "aperta"):
                raise VerificaChiusa()
            if self._chi_puo(chi, v["persona"]) != "proprietario":
                raise NonTrovata()
            s = self._scheletro_confermato(v["id"])
            if s is None:
                raise ValueError("lo scheletro non è confermato")
            prima = self._mappe_di(v["id"]).get(tipo)
            if tipo == M.STUDENTE and prima is not None:
                return prima["id"]
            giro = self._prossimo_giro(s)
            nodi, coll, aiuto_d = self._nuova_copia(v, s, tipo, aiuto, giro)
            adesso = self.adesso().isoformat(timespec="seconds")
            db = self.dati.db
            try:
                if tipo == M.MEMORIA:
                    db.execute("DELETE FROM studio_mappe WHERE verifica = ? AND tipo = 'memoria'",
                               (v["id"],))
                c = db.execute(
                    "INSERT INTO studio_mappe (verifica, persona, tipo, stato, origine, aiuto, nodi,"
                    " collegamenti, creata, creata_da) VALUES (?, ?, ?, 'aperta', 'persona', ?, ?, "
                    "?, ?, ?)", (v["id"], str(v["persona"]), tipo, _j(aiuto_d), _j(nodi),
                                 _j(coll), adesso, getattr(chi, "id", None)))
                db.commit()
                mid = c.lastrowid
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
        self._misure_mappe()["mie" if tipo == M.STUDENTE else "memoria"] += 1
        self._registra(f"verifica {v['id']}: mappa {mid} ({tipo}, aiuto {aiuto_d['livello']}, "
                       f"{sum(bool(n['casella']) for n in nodi)} caselle)")
        return mid

    def rifai_mappa(self, chi, mid, aiuto: str | None = None) -> int:
        """«Rifai»: a memoria un giro nuovo (altre caselle); la mia mappa ricomincia dallo
        scheletro (i concetti suoi vanno via: la pagina lo chiede prima). Dentro il lock."""
        from .servizio import NonTrovata
        with self.dati.lock:
            m, v = self._mappa(chi, mid, cambia=True, chiusa_ok=True)
            if m["tipo"] == M.SCHELETRO:
                raise NonTrovata()
            s = self._scheletro_confermato(v["id"])
            if s is None:
                raise ValueError("lo scheletro non è confermato")
            giro = self._prossimo_giro(s)
            nodi, coll, aiuto_d = self._nuova_copia(v, s, m["tipo"],
                                                    aiuto or m["aiuto"].get("livello"), giro)
            self._salva_mappa(m, nodi=nodi, collegamenti=coll, aiuto=aiuto_d, tentati=[],
                              controllo=None, controllata=None, stato="aperta")
        self._registra(f"verifica {v['id']}: mappa {m['id']} ({m['tipo']}) rifatta, giro {giro}")
        return int(m["id"])

    def controlla_mappa(self, chi, mid) -> dict:
        """«Controlla»: il confronto deterministico con lo scheletro confermato (`mappa.controlla`),
        salvato con l'ora; un tentativo «mappa» (fonte «codice») per ogni casella riempita, una
        volta per casella in questo giro. Tutto dentro il lock (revisione della PR #326: due
        «Controlla» insieme scrivevano i tentativi due volte). Il risultato coi conti e i
        tentativi scritti."""
        from .servizio import NonPermesso, NonTrovata
        with self.dati.lock:
            m, v = self._mappa(chi, mid, cambia=True, chiusa_ok=True)
            if m["tipo"] == M.SCHELETRO:
                raise NonTrovata()
            s = self._scheletro_confermato(v["id"])
            if s is None:
                raise ValueError("lo scheletro non è confermato")
            r = M.controlla(s, m)
            adesso = self.adesso().isoformat(timespec="seconds")
            tentati = list(m["tentati"])
            nel_piano = self._del_piano(v["id"])
            scritti = 0
            if self.modo_padronanza != PD.SPENTA:
                for n in m["nodi"]:
                    nid = int(n["id"])
                    if (m["tipo"] == M.MEMORIA and r["caselle"].get(nid) == M.VUOTA
                            and nid not in tentati):
                        # Solo a memoria (terza revisione della PR #326): con il libro una casella
                        # riempita dopo il primo «Controlla» dà ancora «indizio»
                        # Lasciata vuota al controllo: in questo giro non conta più (seconda
                        # revisione della PR #326: riempita dopo, con lo scheletro visibile, non
                        # deve dare un «giusto»)
                        tentati.append(nid)
                        continue
                    e = M.esito_tentativo(r["caselle"].get(nid), m["tipo"])
                    if e is None or nid in tentati or n.get("argomento") not in nel_piano:
                        continue
                    try:
                        self.registra_tentativo(chi, v["id"], n["argomento"], "mappa", e, "codice")
                        tentati.append(nid)
                        scritti += 1
                    except (ValueError, NonTrovata, NonPermesso) as ex:
                        self._registra(f"tentativo della mappa {m['id']} non scritto: "
                                       f"{type(ex).__name__}")
            controllo = {"caselle": {str(k): x for k, x in r["caselle"].items()},
                         "mancanti": r["mancanti"], "in_piu": r["in_piu"],
                         "verbo_diverso": r["verbo_diverso"],
                         "verso_diverso": r["verso_diverso"], "conti": r["conti"],
                         "quando": adesso}
            self._salva_mappa(m, controllo=controllo, controllata=adesso, tentati=tentati,
                              stato="controllata", modificata=adesso)
            mm = self._misure_mappe()
            mm["controlli"] += 1
            mm["tentativi"] += scritti
        k = r["conti"]
        self._registra(f"verifica {v['id']}: mappa {m['id']} ({m['tipo']}) controllata: "
                       f"{k['giusta']} giuste, {k['sbagliata']} sbagliate, {k['vuota']} vuote, "
                       f"{k['mancanti']} collegamenti mancanti, {k['in_piu']} in più, "
                       f"{k['verso_diverso']} col verso diverso; {scritti} tentativi")
        return {**controllo, "tentativi": scritti}

    def carte_dagli_errori(self, chi, mid) -> int:
        """«Fanne carte»: per ogni casella sbagliata o vuota dell'ultimo controllo una carta della
        persona, con una domanda che si dice a voce («Mappa di storia: che cosa arriva in
        «America»?», «Mappa di storia: «Colombo» arriva in che cosa?») e il concetto come risposta,
        con l'argomento e le pagine del concetto; non due volte la stessa domanda. Dentro il lock.
        Il testo dei concetti entra così nelle carte, che `studio_carte` dà al modello in busta.
        Quante scritte."""
        from .servizio import NonTrovata
        with self.dati.lock:
            m, v = self._mappa(chi, mid, cambia=True, chiusa_ok=True)
            if m["tipo"] == M.SCHELETRO or not m["controllo"]:
                raise NonTrovata()
            s = self._scheletro_confermato(v["id"])
            if s is None:
                raise ValueError("lo scheletro non è confermato")
            s_nodi, s_coll = M.tenuti(s)
            per_id = {int(n["id"]): n for n in s_nodi}
            esiste = {M.chiave(c["domanda"]) for c in self._carte_di(v)}
            sue = {int(x["id"]) for x in self._pagine_di(v["id"])}
            materia = str(v["materia"]).lower()
            n_scritte = 0
            for k, e in (m["controllo"].get("caselle") or {}).items():
                if e not in (M.SBAGLIATA, M.VUOTA):
                    continue
                n = next((x for x in m["nodi"] if int(x["id"]) == int(k)), None)
                atteso = per_id.get(int((n or {}).get("da") or -1))
                if atteso is None:
                    continue
                c = next((c for c in s_coll if int(atteso["id"]) in (int(c["da"]), int(c["a"]))),
                         None)
                if c is None:
                    continue
                sorgente = int(c["da"]) == int(atteso["id"])
                altro = per_id[int(c["a"]) if sorgente else int(c["da"])]
                # Il concetto da ricordare è da dove parte la freccia: «che cosa <verbo> «altro»?»;
                # è dove arriva: «altro» <verbo> che cosa?»
                dom = M.testo_normale(f"Mappa di {materia}: che cosa {c['verbo']} «{altro['testo']}»?"
                                      if sorgente else
                                      f"Mappa di {materia}: «{altro['testo']}» {c['verbo']} che cosa?",
                                      240)
                if M.chiave(dom) in esiste:
                    continue
                try:
                    self.aggiungi_carta(chi, v["id"], dom, atteso["testo"],
                                        argomento=atteso.get("argomento"),
                                        pagine=[p for p in atteso.get("pagine") or () if p in sue])
                except (ValueError, NonTrovata):
                    continue
                esiste.add(M.chiave(dom))
                n_scritte += 1
            self._misure_mappe()["carte"] += n_scritte
        return n_scritte

    # ── la generazione dello scheletro (dal lettore, studio/lettura.py, mappa_genera.py) ──
    def _scheletro_toccabile(self, db, vid) -> tuple[bool, list[int]]:
        """(si può generare?, gli id degli scheletri del modello da rifare). Mai sopra uno scheletro
        della persona: scritto a mano, confermato, o con una voce cambiata da una persona."""
        rifare = []
        for r in db.execute("SELECT id, stato, origine, nodi, collegamenti, aiuto FROM "
                            "studio_mappe WHERE verifica = ? AND tipo = 'scheletro'",
                            (int(vid),)).fetchall():
            voci = _da_j(r["nodi"], []) + _da_j(r["collegamenti"], [])
            mano = r["origine"] != "modello" or r["stato"] == "confermata" or bool(
                _da_j(r["aiuto"], {}).get("toccato")) or any(
                isinstance(x, dict) and x.get("autore") not in (None, "modello") for x in voci)
            if mano:
                return False, []
            rifare.append(r["id"])
        return True, rifare

    def verifiche_per_mappa(self) -> list[dict]:
        """Le verifiche aperte con almeno un argomento del piano che cita una pagina letta, senza
        uno scheletro della persona e con una firma (argomenti, pagine, modo) diversa da quella
        dell'ultima generazione, dalla più vicina. Vuoto con `studio_mappa_genera: spenta` o i dati
        in sola lettura."""
        from . import argomenti as A
        from . import mappa_genera as MG
        m = MG.modo(self.cfg)
        if m == MG.SPENTA or not self.dati.scrivibile:
            return []
        out = []
        for v in self.dati.tutti("SELECT * FROM studio_verifiche WHERE stato = 'aperta' AND "
                                 "data >= ? ORDER BY data, id", (self._oggi().isoformat(),)):
            args = self._argomenti_per_carte(v["id"])
            pagine = self._pagine_di(v["id"])
            lette = {int(p["id"]) for p in A.lette(pagine)}
            if not any(set(a["pagine"]) & lette for a in args):
                continue
            if v.get("mappa_firma") == MG.firma(args, pagine, m):
                continue
            with self.dati.lock:
                si, _r = self._scheletro_toccabile(self.dati.db, v["id"])
            if si:
                out.append({**v, "_pagine": pagine, "_argomenti": args, "_modo": m})
        return out

    def proponi_mappa(self, vid, firma: str, nodi: list[dict], coll: list[dict], esito: str,
                      modo_: str) -> int | None:
        """Scrive l'esito di una generazione: via gli scheletri del modello mai toccati (proposti o
        dell'ombra), dentro il nuovo («proposta» con `studio_mappa_genera: attiva`, «ombra» in
        ombra), la firma e l'esito. Con «rotto» o «errore» resta quello di prima. Se intanto
        argomenti o pagine sono cambiati, o la persona ha scritto il suo scheletro, non scrive
        niente: None. Quanti concetti."""
        from . import mappa_genera as MG
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
                si, rifare = self._scheletro_toccabile(db, vid)
                if v is None or not si or MG.firma(args, pagine, modo_) != firma:
                    db.rollback()
                    return None
                n = 0
                if esito not in (MG.ROTTO, MG.ERRORE):
                    for mid in rifare:
                        db.execute("DELETE FROM studio_mappe WHERE id = ?", (mid,))
                    if nodi:
                        adesso = self.adesso().isoformat(timespec="seconds")
                        db.execute(
                            "INSERT INTO studio_mappe (verifica, persona, tipo, stato, origine, "
                            "nodi, collegamenti, creata) VALUES (?, ?, 'scheletro', ?, 'modello', "
                            "?, ?, ?)", (int(vid), str(v["persona"]),
                                         "ombra" if modo_ == MG.OMBRA else "proposta",
                                         _j(nodi), _j(coll), adesso))
                        n = len(nodi)
                db.execute("UPDATE studio_verifiche SET mappa_firma = ?, mappa_esito = ?, "
                           "mappa_del = ? WHERE id = ?",
                           (firma, esito if esito != MG.PROPOSTO or n else MG.VUOTO, D.adesso(),
                            int(vid)))
                db.commit()
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
        return n

    # ── per la home, la voce e lo schermo ──
    def _conto_mappa(self, v: dict) -> dict:
        """Solo conti e stati (per la home e per la voce): mai il testo."""
        mm = self._mappe_di(v["id"])
        s, mia, mem = mm.get(M.SCHELETRO), mm.get(M.STUDENTE), mm.get(M.MEMORIA)

        def conto(m):
            if m is None:
                return None
            k = (m["controllo"] or {}).get("conti") or {}
            return {"concetti": len(m["nodi"]), "collegamenti": len(m["collegamenti"]),
                    "caselle_vuote": sum(bool(n.get("casella")) and not str(n.get("testo") or "")
                                         .strip() for n in m["nodi"]),
                    "controllata": m["controllata"],
                    "aperta": m["stato"] == "aperta",
                    "ultimo": ({x: int(k.get(x) or 0) for x in ("giusta", "sbagliata", "vuota",
                                                                "mancanti", "in_piu",
                                                                "verso_diverso")}
                               if k else None)}
        return {"scheletro": ({"stato": s["stato"], "origine": s["origine"],
                               "concetti": len(M.tenuti(s)[0]),
                               "da_decidere": sum(x.get("stato") == "proposto"
                                                  for x in s["nodi"] + s["collegamenti"])}
                              if s else None),
                "mia": conto(mia), "memoria": conto(mem)}

    def vista_mappe(self, chi, vid) -> dict:
        """Le mappe di una verifica per lo schermo (`/api/studio/mappa`): lo scheletro (non
        dell'ombra), la mia mappa e l'ultima a memoria, coi testi (un dato: la pagina li scrive
        solo con textContent), le pagine col numero stampato o «foto n», gli esiti dell'ultimo
        controllo; **mai il testo atteso delle caselle**. Mentre la mappa a memoria di chi chiede
        è aperta (non ancora controllata), lo scheletro e la mia mappa arrivano **senza i testi**
        dei concetti e senza le parole (`nascosta`), e la pagina ne nasconde le schede: le risposte
        non arrivano alla pagina prima di «Controlla» (revisione della PR #326)."""
        from . import piano as P
        v = self._verifica(chi, vid)
        ruolo = self._chi_puo(chi, v["persona"])
        pagine = {}
        for p in self._pagine_di(v["id"]):
            n = P.numero_leggibile(p["numero"])
            pagine[int(p["id"])] = f"p. {n}" if n else f"foto {p['ordine']}"

        mm = self._mappe_di(v["id"])
        mem = mm.get(M.MEMORIA)
        a_memoria = bool(ruolo == "proprietario" and mem is not None and mem["stato"] == "aperta")

        def per_schermo(m, senza_testi=False):
            if m is None:
                return None
            if senza_testi:
                return {"id": m["id"], "tipo": m["tipo"], "stato": m["stato"],
                        "origine": m["origine"], "nascosta": True, "parole": [], "nodi": [],
                        "collegamenti": [], "conti": None, "controllata": m["controllata"],
                        "modificata": m["modificata"], "aiuto": None}
            ctrl = m["controllo"] or {}
            esiti = ctrl.get("caselle") or {}
            verbo = set(ctrl.get("verbo_diverso") or ())
            verso = set(ctrl.get("verso_diverso") or ())
            in_piu = {int(x["collegamento"]): x for x in ctrl.get("in_piu") or ()}
            mancanti = {}
            for x in ctrl.get("mancanti") or ():
                mancanti.setdefault(x.get("nodo"), []).extend(x.get("pagine") or ())
            nomi = lambda ids: [pagine[int(i)] for i in ids or () if int(i) in pagine]  # noqa: E731
            return {"id": m["id"], "tipo": m["tipo"], "stato": m["stato"],
                    "origine": m["origine"], "aiuto": (m["aiuto"] or {}).get("livello"),
                    "parole": list((m["aiuto"] or {}).get("parole") or ()),
                    "controllata": m["controllata"], "modificata": m["modificata"],
                    "conti": ctrl.get("conti"),
                    "nodi": [{"id": int(n["id"]), "testo": str(n.get("testo") or ""),
                              "pagine": nomi(n.get("pagine")), "argomento": n.get("argomento"),
                              "autore": n.get("autore"), "stato": n.get("stato", "tenuto"),
                              "avvisi": [x for x in n.get("avvisi") or () if isinstance(x, str)],
                              "x": n.get("x"), "y": n.get("y"), "casella": bool(n.get("casella")),
                              "suo": n.get("da") is None,
                              "esito": esiti.get(str(n["id"])),
                              "manca": nomi(dict.fromkeys(mancanti.get(int(n["id"]), ()))) if
                              int(n["id"]) in mancanti else None}
                             for n in m["nodi"]],
                    "collegamenti": [{"id": int(c["id"]), "da": int(c["da"]), "a": int(c["a"]),
                                      "verbo": str(c.get("verbo") or ""),
                                      "pagine": nomi(c.get("pagine")), "autore": c.get("autore"),
                                      "stato": c.get("stato", "tenuto"),
                                      "avvisi": [x for x in c.get("avvisi") or ()
                                                 if isinstance(x, str)],
                                      "esito": ("verso_diverso" if int(c["id"]) in verso else
                                                "verbo_diverso" if int(c["id"]) in verbo else
                                                "in_piu" if int(c["id"]) in in_piu else None),
                                      "guarda": (nomi(in_piu[int(c["id"])]["pagine"])
                                                 if int(c["id"]) in in_piu else None)}
                                     for c in m["collegamenti"]]}
        _d, aiuto = self._deboli(v)
        nome = getattr(self._profilo(v["persona"]), "name", None) if ruolo == "tutore" else None
        return {"verifica": {"id": v["id"], "materia": v["materia"], "data": v["data"],
                             "stato": v["stato"], "di": nome},
                "scheletro": per_schermo(mm.get(M.SCHELETRO), a_memoria),
                "mia": per_schermo(mm.get(M.STUDENTE), a_memoria),
                "memoria": per_schermo(mem),
                "a_memoria": a_memoria,
                "argomenti": [{"id": a["id"], "numero": i, "titolo": a["titolo"]}
                              for i, a in enumerate(self.argomenti(chi, vid), 1)
                              if a["stato"] in D.ARGOMENTI_DEL_PIANO],
                "pagine": [{"id": k, "nome": x} for k, x in pagine.items()],
                "aiuto": aiuto, "aiuti": dict(M.AIUTI),
                "puo": {"scheletro": v["stato"] in ("bozza", "aperta") and not (
                            (mm.get(M.SCHELETRO) or {}).get("stato") == "confermata"
                            and (mm.get(M.STUDENTE) or mem)),
                        "riapri": v["stato"] in ("bozza", "aperta")
                        and (mm.get(M.SCHELETRO) or {}).get("stato") == "confermata",
                        "mia": ruolo == "proprietario" and v["stato"] in ("bozza", "aperta")},
                "massimi": {"concetti": M.nodi_max(self.cfg), "suoi": M.SUOI_MAX,
                            "collegamenti": 2 * (M.nodi_max(self.cfg) + M.SUOI_MAX),
                            "testo": M.NODO_MAX, "verbo": M.VERBO_MAX},
                "prova": not self.per_schermi()}

    def pdf_mappa(self, chi, vid) -> bytes:
        """Il PDF della mia mappa (mai dello scheletro: «lo scheletro non si scarica»), un formato
        solo (decisione 5 del 27/10): A4 orizzontale con nome, data e «controllata il …», l'elenco
        in seconda pagina (`mappa_pdf.py`). La persona e il tutore."""
        from . import mappa_pdf
        from .servizio import NonTrovata
        v = self._verifica(chi, vid)
        mm = self._mappe_di(v["id"])
        mia = mm.get(M.STUDENTE)
        if mia is None or not mia["nodi"]:
            raise NonTrovata()
        mem = mm.get(M.MEMORIA)
        if (getattr(chi, "id", None) == v["persona"] and mem is not None
                and mem["stato"] == "aperta"):
            # Le risposte della mappa a memoria aperta non escono nemmeno dal PDF
            raise ValueError("prima finisci la mappa a memoria: «Controlla»")
        from . import piano as P
        prof = chi if getattr(chi, "id", None) == v["persona"] else self._profilo(v["persona"])
        nome = str(getattr(prof, "name", "") or "")
        pagine = {}
        for p in self._pagine_di(v["id"]):
            n = P.numero_leggibile(p["numero"])
            pagine[int(p["id"])] = f"p. {n}" if n else f"foto {p['ordine']}"
        self._registra(f"verifica {v['id']}: PDF della mappa {mia['id']} "
                       f"({self._chi_registro(chi, v['persona'])})")
        return mappa_pdf.render(mia, nome=nome, materia=str(v["materia"]),
                                data_verifica=str(v["data"]), pagine=pagine,
                                font=getattr(self.cfg, "documenti_font", None))
