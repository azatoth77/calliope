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

**La mappa libera** (30/10 notte, passo 7c, #328, decisione 0035 punti 37–39): la persona la fa da
zero (`inizia_libera`), con lo scheletro nascosto da vista, PDF, tool e carte finché è aperta; «Un
indizio» (`indizio_libera`) e «Mostra» (`mostra_concetto`); «Ho finito» (`finisci_libera`) col
confronto del codice (`mappa.confronta`), gli indicatori del metodo per giro (`giri`) e i tentativi
sui concetti chiave, una volta per giro; «Parliamone» legge `consigli_mappa` (in busta, senza i
concetti nascosti) e `misura_consigli` conta i concetti svelati.
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
# La mappa libera dopo «Ho finito» (passo 7c, #328): come a memoria
LIBERA_CHIUSA = "la tua mappa è già finita: per rifarla da zero, «Rifai»"
UNA_ALLA_VOLTA = "prima finisci l'altra mappa senza guardare («Controlla» o «Ho finito»)"
# Le carte scritte da «Fanne carte» cominciano così (`carte_dagli_errori`): mentre la mappa libera
# è aperta non si vedono e non si ripassano (dicono i concetti dello scheletro)
CARTE_DALLA_MAPPA = "Mappa di "
# I giri della mappa libera tenuti (gli indicatori per la «volta scorsa» e per la #248)
GIRI_MAX = 20


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
        # Dallo schema 9 (passo 7c, #328): i giri della mappa libera e i concetti del riferimento
        # con la pagina detta o il testo mostrato
        m["giri"] = [g for g in _da_j(m.get("giri"), []) if isinstance(g, dict)]
        m["visti"] = {str(k): v for k, v in _da_j(m.get("visti"), {}).items()
                      if v in (M.INDIZIO, M.VISTO)}
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
            if m["tipo"] == M.LIBERA and m["stato"] == "controllata" and not chiusa_ok:
                raise ValueError(LIBERA_CHIUSA)
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
            if k in ("nodi", "collegamenti", "tentati", "aiuto", "controllo", "giri", "visti"):
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
                if m["tipo"] == M.LIBERA and len(nodi) >= M.nodi_max(self.cfg) + M.SUOI_MAX:
                    raise ValueError(f"al più {M.nodi_max(self.cfg) + M.SUOI_MAX} concetti")
                if m["tipo"] in (M.STUDENTE, M.MEMORIA) and sum(
                        n.get("da") is None for n in nodi) >= M.SUOI_MAX:
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
            mm = self._mappe_di(v["id"])
            prima = mm.get(tipo)
            if tipo == M.STUDENTE and prima is not None:
                return prima["id"]
            # Una mappa senza guardare per volta (passo 7c, #328): con la libera aperta lo
            # scheletro è nascosto, a memoria lo mostrerebbe
            if self._aperta(mm.get(M.LIBERA)):
                raise ValueError(UNA_ALLA_VOLTA)
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
            altra = self._mappe_di(v["id"]).get(M.MEMORIA if m["tipo"] == M.LIBERA else M.LIBERA)
            if m["tipo"] in (M.MEMORIA, M.LIBERA) and self._aperta(altra):
                raise ValueError(UNA_ALLA_VOLTA)
            if m["tipo"] == M.LIBERA:
                # La mappa libera ricomincia da zero (dalla radice), giro nuovo: i giri di prima
                # restano negli indicatori, gli indizi e i concetti mostrati ripartono
                a = dict(m["aiuto"] or {})
                a["giro"] = int(a.get("giro", 0) or 0) + 1
                self._salva_mappa(m, nodi=self._nodi_libera(v), collegamenti=[], aiuto=a,
                                  tentati=[], controllo=None, controllata=None, stato="aperta",
                                  visti={})
                giro = a["giro"]
                self._registra(f"verifica {v['id']}: mappa {m['id']} (libera) rifatta, giro "
                               f"{giro}")
                return int(m["id"])
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
            if m["tipo"] in (M.SCHELETRO, M.LIBERA):
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
            if m["tipo"] in (M.SCHELETRO, M.LIBERA) or not m["controllo"]:
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

    # ── la mappa libera (passo 7c, 30/10, #328) ──
    @staticmethod
    def _aperta(m) -> bool:
        return m is not None and m["stato"] == "aperta"

    def _conta(self, k: str, n: int = 1):
        mm = self._misure_mappe()
        mm[k] = int(mm.get(k, 0) or 0) + int(n)

    def _riferimento(self, vid) -> tuple[list[dict], list[dict], str | None]:
        """Il riferimento della mappa libera (`mappa.voci_riferimento`): lo scheletro confermato,
        o le voci senza avvisi di quello proposto («rispetto alla mappa proposta, non ancora
        controllata»); mai quello dell'ombra."""
        return M.voci_riferimento(self._mappe_di(vid).get(M.SCHELETRO))

    @staticmethod
    def _nodi_libera(v) -> list[dict]:
        """La partenza della mappa libera: la radice con l'argomento della verifica scritto dalla
        persona, se c'è; altrimenti vuota. Mai un concetto dello scheletro (sarebbe una risposta
        data)."""
        try:
            t = M.testo_normale(v.get("argomento"), M.NODO_MAX)
        except ValueError:
            return []
        return [{"id": 1, "testo": t, "pagine": [], "argomento": None, "autore": "persona",
                 "stato": "tenuto", "avvisi": [], "x": 0.5, "y": 0.5, "da": None,
                 "casella": False, "radice": True}]

    def inizia_libera(self, chi, vid) -> int:
        """«Fai la tua mappa da zero»: la mappa libera della persona (una per verifica: se c'è,
        quella), anche senza scheletro. Solo la persona; non con una mappa a memoria aperta."""
        from .servizio import NonTrovata, VerificaChiusa
        if M.modo_libera(self.cfg) == "spenta":
            raise ValueError("la mappa libera qui non è accesa")
        with self.dati.lock:
            self._scrivibile()
            v = self._verifica(chi, vid)
            if v["stato"] not in ("bozza", "aperta"):
                raise VerificaChiusa()
            if self._chi_puo(chi, v["persona"]) != "proprietario":
                raise NonTrovata()
            mm = self._mappe_di(v["id"])
            if mm.get(M.LIBERA) is not None:
                return mm[M.LIBERA]["id"]
            if self._aperta(mm.get(M.MEMORIA)):
                raise ValueError(UNA_ALLA_VOLTA)
            mid = self.dati.scrivi(
                "INSERT INTO studio_mappe (verifica, persona, tipo, stato, origine, aiuto, nodi, "
                "collegamenti, creata, creata_da) VALUES (?, ?, 'libera', 'aperta', 'persona', ?, "
                "?, '[]', ?, ?)", (v["id"], str(v["persona"]), _j({"giro": 0}),
                                   _j(self._nodi_libera(v)),
                                   self.adesso().isoformat(timespec="seconds"),
                                   getattr(chi, "id", None)))
            self._conta("libere")
        self._registra(f"verifica {v['id']}: mappa {mid} (libera) cominciata")
        return mid

    def _libera(self, chi, mid, cambia=True, chiusa_ok=False) -> tuple[dict, dict]:
        from .servizio import NonTrovata
        m, v = self._mappa(chi, mid, cambia=cambia, chiusa_ok=chiusa_ok)
        if m["tipo"] != M.LIBERA:
            raise NonTrovata()
        return m, v

    def indizio_libera(self, chi, mid) -> dict:
        """«Un indizio» (la mappa libera aperta): la pagina del prossimo concetto chiave del
        riferimento che manca e non ha ancora avuto l'indizio; lo segna «indizio» (a «Ho finito»,
        se c'è, vale «indizio» e non «giusto»). {concetto (id del riferimento), pagine (id)} o
        {concetto: None, mancano}."""
        with self.dati.lock:
            m, v = self._libera(chi, mid)
            rn, rc, _t = self._riferimento(v["id"])
            if not rn:
                raise ValueError("non c'è ancora uno scheletro con cui confrontarla")
            r = M.confronta(rn, rc, m)
            per_id = {int(n["id"]): n for n in rn}
            visti = dict(m["visti"])
            for sid in r["mancanti"]:
                if str(sid) not in visti:
                    visti[str(sid)] = M.INDIZIO
                    self._salva_mappa(m, visti=visti)
                    self._conta("indizi")
                    out = {"concetto": sid, "pagine": list(per_id[sid].get("pagine") or ())}
                    break
            else:
                out = {"concetto": None, "mancano": len(r["mancanti"])}
        self._registra(f"verifica {v['id']}: mappa {m['id']} (libera), un indizio: "
                       + (f"concetto {out['concetto']}" if out["concetto"] else "nessuno"))
        return out

    def mostra_concetto(self, chi, mid, concetto) -> None:
        """«Mostra» (un tocco per concetto): il testo di un concetto chiave del riferimento che
        manca (o col nome diverso), da qui «visto»: nel giro non conta più come tentativo. Mentre
        la mappa è aperta solo dopo il suo indizio; dopo «Ho finito» per i mancanti del confronto.
        Solo la persona."""
        from .servizio import NonTrovata
        with self.dati.lock:
            m, v = self._libera(chi, mid, chiusa_ok=True)
            sid = int(concetto)
            visti = dict(m["visti"])
            if m["stato"] == "aperta":
                ok = visti.get(str(sid)) in (M.INDIZIO, M.VISTO)
            else:
                c = m["controllo"] or {}
                ok = (sid in [int(x) for x in c.get("chiave") or ()]
                      and (c.get("esiti") or {}).get(str(sid)) in (M.MANCANTE, M.DIVERSO))
            if not ok:
                raise NonTrovata()
            if visti.get(str(sid)) != M.VISTO:
                visti[str(sid)] = M.VISTO
                self._salva_mappa(m, visti=visti)
                self._conta("mostrati")
        self._registra(f"verifica {v['id']}: mappa {m['id']} (libera), mostrato il concetto {sid}")

    def finisci_libera(self, chi, mid) -> dict:
        """«Ho finito»: il confronto del codice col riferimento (`mappa.confronta`), gli indicatori
        del metodo (`mappa.indicatori`) scritti nel giro, e i tentativi «mappa» (fonte «codice»)
        sui concetti chiave, **una volta per giro** (la mappa si chiude: un secondo «Ho finito» non
        passa), solo col riferimento confermato e sugli argomenti del piano. Tutto dentro il lock.
        Il controllo salvato, coi tentativi scritti."""
        from .servizio import NonPermesso, NonTrovata
        with self.dati.lock:
            m, v = self._libera(chi, mid)
            rn, rc, rtipo = self._riferimento(v["id"])
            r = M.confronta(rn, rc, m) if rn else None
            ind = M.indicatori(m["nodi"], m["collegamenti"], r)
            adesso = self.adesso().isoformat(timespec="seconds")
            tentati = list(m["tentati"])
            scritti = 0
            if r is not None and rtipo == "confermato" and self.modo_padronanza != PD.SPENTA:
                nel_piano = self._del_piano(v["id"])
                per_id = {int(n["id"]): n for n in rn}
                for sid in r["chiave"]:
                    e = M.tentativo_libera(r["esiti"].get(sid), m["visti"].get(str(sid)))
                    arg = per_id[sid].get("argomento")
                    if e is None or sid in tentati or arg not in nel_piano:
                        continue
                    try:
                        self.registra_tentativo(chi, v["id"], arg, "mappa", e, "codice")
                        tentati.append(sid)
                        scritti += 1
                    except (ValueError, NonTrovata, NonPermesso) as ex:
                        self._registra(f"tentativo della mappa {m['id']} non scritto: "
                                       f"{type(ex).__name__}")
            controllo = {"tipo": M.LIBERA, "riferimento": rtipo, "indicatori": ind,
                         "quando": adesso, "tentativi": scritti, "conti": None}
            if r is not None:
                controllo.update(
                    chiave=r["chiave"], esiti={str(k): x for k, x in r["esiti"].items()},
                    nodo={str(k): x for k, x in r["nodo"].items()}, mancanti=r["mancanti"],
                    coll_mancanti=r["coll_mancanti"], verso_diverso=r["verso_diverso"],
                    fuori_quadro=r["fuori_quadro"], conti=r["conti"],
                    pagine={str(int(n["id"])): list(n.get("pagine") or ()) for n in rn})
            giro = int((m["aiuto"] or {}).get("giro", 0) or 0)
            giri = [g for g in m["giri"] if g.get("giro") != giro] + [{
                "giro": giro, "quando": adesso, "riferimento": rtipo, "indicatori": ind,
                "conti": controllo["conti"], "tentativi": scritti,
                "indizi": sum(x == M.INDIZIO for x in m["visti"].values()),
                "visti": sum(x == M.VISTO for x in m["visti"].values())}]
            self._salva_mappa(m, controllo=controllo, controllata=adesso, tentati=tentati,
                              stato="controllata", modificata=adesso, giri=giri[-GIRI_MAX:])
            self._conta("finite")
            self._conta("tentativi", scritti)
        k = controllo["conti"] or {}
        self._registra(f"verifica {v['id']}: mappa {m['id']} (libera) finita, giro {giro}: "
                       + (f"concetti chiave {k.get('presente', 0)} presenti, {k.get('diverso', 0)}"
                          f" diversi, {k.get('mancante', 0)} mancanti su {k.get('chiave', 0)} "
                          f"(riferimento {rtipo}); " if k else "senza riferimento; ")
                       + f"parti {ind['parti']}, isolati {ind['isolati']}, verbi vuoti "
                       f"{ind['verbi_vuoti']}, lunghi {ind['lunghi']}, profondità "
                       f"{ind['profondita']}, trasversali {ind['trasversali']}; {scritti} "
                       "tentativi")
        return controllo

    def _nascosti_libera(self, lib: dict, rn: list[dict]) -> dict:
        """{id: testo} dei concetti del riferimento che la persona non ha (né col nome diverso)
        e non ha scelto di vedere: non vanno al modello e non vanno detti."""
        c = lib.get("controllo") or {}
        trovati = {int(k) for k in (c.get("nodo") or {})}
        visti = {int(k) for k, x in (lib.get("visti") or {}).items() if x == M.VISTO}
        return {int(n["id"]): n["testo"] for n in rn
                if int(n["id"]) not in trovati and int(n["id"]) not in visti}

    def _libera_finita(self, chi, vid) -> tuple[dict, dict]:
        v = self._verifica(chi, vid)
        lib = self._mappe_di(v["id"]).get(M.LIBERA)
        if lib is None or lib["stato"] != "controllata" or not lib["controllo"]:
            raise ValueError("la mappa libera non è finita")
        return lib, v

    def consigli_mappa(self, chi, vid) -> dict:
        """I dati di «Parliamone» per il tool `studio_mappa_consigli` (in busta: è un dato):
        la mappa della persona coi codici T1…, il riferimento coi codici R1… **senza il testo dei
        concetti nascosti** (`_nascosti_libera`: al loro posto «concetto nascosto» e le pagine),
        il confronto del codice e gli indicatori, col giro di prima. ValueError se la mappa libera
        non è finita."""
        from . import piano as P
        lib, v = self._libera_finita(chi, vid)
        c = lib["controllo"]
        rn, rc, rtipo = self._riferimento(v["id"])
        nascosti = self._nascosti_libera(lib, rn)
        nomi = {}
        for p in self._pagine_di(v["id"]):
            n = P.numero_leggibile(p["numero"])
            nomi[int(p["id"])] = f"p. {n}" if n else f"foto {p['ordine']}"
        tcod = {int(n["id"]): f"T{i}" for i, n in enumerate(lib["nodi"], 1)}
        rcod = {int(n["id"]): f"R{i}" for i, n in enumerate(rn, 1)}
        nodo = {int(k): int(x) for k, x in (c.get("nodo") or {}).items()}
        chiave_ = {int(x) for x in c.get("chiave") or ()}
        esiti = c.get("esiti") or {}
        tua = {"concetti": [{"codice": tcod[int(n["id"])], "testo": str(n.get("testo") or ""),
                             **({"radice": True} if n.get("radice") else {})}
                            for n in lib["nodi"]],
               "collegamenti": [{"da": tcod.get(int(x["da"])), "verbo": str(x.get("verbo") or ""),
                                 "a": tcod.get(int(x["a"]))} for x in lib["collegamenti"]]}
        rif = None
        if rn:
            rif = {"stato": "confermato" if rtipo == "confermato"
                   else "proposto, non ancora controllato",
                   "concetti": [{"codice": rcod[int(n["id"])],
                                 "testo": ("(concetto nascosto: non dirlo e non farlo indovinare)"
                                           if int(n["id"]) in nascosti else n["testo"]),
                                 "chiave": int(n["id"]) in chiave_,
                                 "esito": esiti.get(str(int(n["id"]))),
                                 "nella_tua_mappa": tcod.get(nodo.get(int(n["id"]))),
                                 "pagine": [nomi[int(p)] for p in n.get("pagine") or ()
                                            if int(p) in nomi]} for n in rn],
                   "collegamenti": [{"da": rcod.get(int(x["da"])), "verbo": x["verbo"],
                                     "a": rcod.get(int(x["a"]))} for x in rc]}
        ind = c.get("indicatori") or {}
        prima = lib["giri"][-2]["indicatori"] if len(lib["giri"]) >= 2 else None
        coppia = {int(x["id"]): [tcod.get(int(x["da"])), tcod.get(int(x["a"]))]
                  for x in lib["collegamenti"]}
        return {"verifica": v["id"], "mappa": lib["id"], "tua": tua, "riferimento": rif,
                "confronto": ({"conti": c.get("conti"),
                               "collegamenti_mancanti": [
                                   {"fra": [tcod.get(int(x["da"])), tcod.get(int(x["a"]))],
                                    "pagine": [nomi[int(p)] for p in x.get("pagine") or ()
                                               if int(p) in nomi]}
                                   for x in c.get("coll_mancanti") or ()],
                               "verso_diverso": [coppia[int(x)] for x in c.get("verso_diverso")
                                                 or () if int(x) in coppia],
                               "fuori_dal_quadro": [coppia[int(x)] for x in c.get("fuori_quadro")
                                                    or () if int(x) in coppia]}
                              if c.get("conti") else None),
                "indicatori": ind, "giro_di_prima": prima,
                "rispetto_a_prima": M.rispetto_a_prima(prima, ind) if prima else None,
                "nascosti": len(nascosti), "frase": self._frase_confronto(c, nomi, chi, v)}

    def _frase_confronto(self, c: dict, nomi: dict, chi, v) -> str:
        """La frase del codice sul confronto (per la voce in ombra e per la pagina): solo conti e
        pagine, mai il testo dei concetti."""
        nome = self._nome_per(chi, v)
        di = "Nella tua mappa" if nome is None else (f"Nella mappa di {nome}" if nome
                                                       else "Nella sua mappa")
        k = c.get("conti")
        ind = c.get("indicatori") or {}
        pezzi = []
        if k:
            t = (f"{di} ci sono {k['presente'] + k['diverso']} concetti chiave su {k['chiave']}"
                 if k["chiave"] != 1 else f"{di} il concetto chiave "
                 + ("c'è" if k["presente"] + k["diverso"] else "manca"))
            if k["diverso"]:
                t += f", {k['diverso']} col nome da rivedere"
            pag = []
            for sid in c.get("mancanti") or ():
                pag += [nomi[int(p)] for p in (c.get("pagine") or {}).get(str(sid), ())
                        if int(p) in nomi]
            pag = list(dict.fromkeys(pag))
            if k["mancante"] and pag:
                t += f"; quelli che mancano li trovi a {', '.join(pag[:3])}"
            if c.get("riferimento") == "proposto":
                t += ", rispetto alla mappa proposta, non ancora controllata"
            pezzi.append(t + ".")
        else:
            pezzi.append(f"{di}: lo scheletro per il confronto non c'è ancora.")
        if ind.get("parti", 0) > 1:
            pezzi.append(f"È in {ind['parti']} parti staccate: prova a collegarle.")
        elif ind.get("verbi_vuoti"):
            pezzi.append("Qualche collegamento ha un verbo vuoto: prova a dire come sono legati.")
        elif ind.get("lunghi"):
            pezzi.append("Qualche concetto è lungo come una frase: prova ad accorciarlo.")
        elif ind.get("concetti", 0) >= 5 and not ind.get("trasversali"):
            pezzi.append("Manca un collegamento fra due rami diversi: ce n'è uno?")
        return " ".join(pezzi)

    def misura_consigli(self, chi, vid, testo: str, modo: str) -> dict:
        """La misura di «Parliamone» a risposta finita (o della passata in ombra, mai detta): la
        lunghezza e i concetti nascosti che la risposta dice (`mappa.svelati`, devono essere 0).
        Nel registro solo id e conti, mai il testo. {lunghezza, svelati: [id]}."""
        lib, v = self._libera_finita(chi, vid)
        rn, _rc, _t = self._riferimento(v["id"])
        sv = M.svelati(self._nascosti_libera(lib, rn), testo or "",
                       [str(n.get("testo") or "") for n in lib["nodi"]])
        self._conta("consigli")
        self._conta("svelati", len(sv))
        self._registra(f"verifica {v['id']}: mappa {lib['id']}, «Parliamone» ({modo}): "
                       f"{len(testo or '')} caratteri, {len(sv)} concetti svelati"
                       + (" (" + ", ".join(f"concetto {i}" for i in sv) + ")" if sv else ""))
        return {"lunghezza": len(testo or ""), "svelati": sv}

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
        from . import genera as G
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
            if not G.da_generare(v.get("mappa_firma"), v.get("mappa_esito"), v.get("mappa_del"),
                                 MG.firma(args, pagine, m), self.adesso()):
                continue
            with self.dati.lock:
                si, _r = self._scheletro_toccabile(self.dati.db, v["id"])
            if si:
                out.append({**v, "_pagine": pagine, "_argomenti": args, "_modo": m})
        return out

    def proponi_mappa(self, vid, firma: str, nodi: list[dict], coll: list[dict], esito: str,
                      modo_: str, isole: int = 1) -> int | None:
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
                        # Le isole rimaste dopo la seconda passata (passo 7c, #328): la pagina
                        # lo dice
                        db.execute(
                            "INSERT INTO studio_mappe (verifica, persona, tipo, stato, origine, "
                            "aiuto, nodi, collegamenti, creata) VALUES (?, ?, 'scheletro', ?, "
                            "'modello', ?, ?, ?, ?)",
                            (int(vid), str(v["persona"]),
                             "ombra" if modo_ == MG.OMBRA else "proposta",
                             _j({"isole": int(isole)}) if int(isole or 1) > 1 else None,
                             _j(nodi), _j(coll), adesso))
                        n = len(nodi)
                from . import genera as G
                scritta, errori = G.firma_da_scrivere(v["mappa_firma"], firma, esito)
                db.execute("UPDATE studio_verifiche SET mappa_firma = ?, mappa_esito = ?, "
                           "mappa_del = ? WHERE id = ?",
                           (scritta, esito if esito != MG.PROPOSTO or n else MG.VUOTO,
                            self.adesso().isoformat(timespec="seconds"), int(vid)))
                db.commit()
                if errori >= G.ERRORI_MAX:
                    self._registra(f"verifica {vid}: mappa ferma dopo {errori} errori con le stesse "
                                   "pagine e argomenti: riparte quando cambiano")
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
        lib = mm.get(M.LIBERA)

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
                "mia": conto(mia), "memoria": conto(mem),
                # La mappa libera (passo 7c, #328): conti e indicatori, mai testi
                "libera": ({"concetti": len(lib["nodi"]), "collegamenti": len(lib["collegamenti"]),
                            "aperta": lib["stato"] == "aperta", "controllata": lib["controllata"],
                            "giri": len(lib["giri"]),
                            "chiave": (((lib["controllo"] or {}).get("conti") or {})
                                       .get("chiave")),
                            "trovati": ((lambda k: (k.get("presente", 0) + k.get("diverso", 0))
                                         if k else None)(
                                (lib["controllo"] or {}).get("conti")))}
                           if lib else None)}

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
        lib = mm.get(M.LIBERA)
        a_memoria = bool(ruolo == "proprietario" and self._aperta(mem))
        # La mappa libera aperta (passo 7c, #328): lo scheletro, la mia mappa e a memoria (che
        # hanno i concetti dello scheletro) arrivano senza testi, come con a memoria aperta
        a_libera = bool(ruolo == "proprietario" and self._aperta(lib))
        nascondi = a_memoria or a_libera

        def per_schermo(m, senza_testi=False):
            if m is None:
                return None
            if senza_testi:
                return {"id": m["id"], "tipo": m["tipo"], "stato": m["stato"],
                        "origine": m["origine"], "nascosta": True, "parole": [], "nodi": [],
                        "collegamenti": [], "conti": None, "controllata": m["controllata"],
                        "modificata": m["modificata"], "aiuto": None}
            ctrl = (m["controllo"] or {}) if m["tipo"] != M.LIBERA else {}
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
        sch = mm.get(M.SCHELETRO)
        vs = per_schermo(sch, nascondi)
        if vs is not None and not vs.get("nascosta"):
            # Le parti staccate dello scheletro (passo 7c, #328): la pagina lo dice
            vs["parti"] = len(M.componenti(sch["nodi"], sch["collegamenti"])) if sch["nodi"] else 0
        return {"verifica": {"id": v["id"], "materia": v["materia"], "data": v["data"],
                             "stato": v["stato"], "di": nome},
                "scheletro": vs,
                "mia": per_schermo(mm.get(M.STUDENTE), nascondi),
                "memoria": per_schermo(mem, a_libera),
                "libera": self._libera_per_schermo(lib, per_schermo, pagine, a_memoria),
                "a_memoria": a_memoria, "a_libera": a_libera,
                "libera_accesa": M.modo_libera(self.cfg) != "spenta",
                "consigli": M.modo_consigli(self.cfg) != "spenta",
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
                        "mia": ruolo == "proprietario" and v["stato"] in ("bozza", "aperta"),
                        "libera": ruolo == "proprietario" and v["stato"] in ("bozza", "aperta")
                        and M.modo_libera(self.cfg) != "spenta"},
                "massimi": {"concetti": M.nodi_max(self.cfg), "suoi": M.SUOI_MAX,
                            "collegamenti": 2 * (M.nodi_max(self.cfg) + M.SUOI_MAX),
                            "testo": M.NODO_MAX, "verbo": M.VERBO_MAX},
                "prova": not self.per_schermi()}

    def _libera_per_schermo(self, lib, per_schermo, pagine: dict, senza_testi: bool):
        """La mappa libera per lo schermo: i concetti e i collegamenti della persona (suoi), e
        dopo «Ho finito» il confronto: i concetti chiave del riferimento con l'esito e le pagine,
        il **testo solo dei concetti mostrati** («Mostra») e di quelli presenti; i collegamenti
        mancanti (con le pagine), verso diverso e fuori dal quadro; gli indicatori e il confronto
        con la volta scorsa. Mentre è aperta gli indizi chiesti (pagine, e il testo se mostrato).
        Con `senza_testi` (una mappa a memoria aperta) senza testi."""
        if lib is None:
            return None
        out = per_schermo(lib, senza_testi)
        out["giro"] = int((lib["aiuto"] or {}).get("giro", 0) or 0)
        out["giri"] = len(lib["giri"])
        if senza_testi:
            return out
        rn, _rc, rtipo = self._riferimento(lib["verifica"])
        per_id = {int(n["id"]): n for n in rn}
        nomi = lambda ids: [pagine[int(i)] for i in ids or () if int(i) in pagine]  # noqa: E731
        visti = lib["visti"]

        def testo_se(sid, sempre=False):
            n = per_id.get(int(sid))
            if n is None:
                return None
            return n["testo"] if sempre or visti.get(str(sid)) == M.VISTO else None
        out["riferimento"] = rtipo
        out["indizi"] = ([{"n": int(k), "pagine": nomi((per_id.get(int(k)) or {}).get("pagine")),
                           "testo": testo_se(k), "visto": x == M.VISTO}
                          for k, x in visti.items() if int(k) in per_id]
                         if lib["stato"] == "aperta" else [])
        c = lib["controllo"] or {}
        if lib["stato"] != "controllata" or not c:
            out["confronto"] = None
            return out
        esiti = c.get("esiti") or {}
        nodo = {int(k): int(x) for k, x in (c.get("nodo") or {}).items()}
        pag_c = c.get("pagine") or {}
        conf = None
        if c.get("conti"):
            conf = {"riferimento": c.get("riferimento"), "conti": c["conti"],
                    "tentativi": int(c.get("tentativi") or 0),
                    "chiave": [{"n": int(sid), "esito": esiti.get(str(sid)),
                                "pagine": nomi(pag_c.get(str(sid))),
                                "nodo": nodo.get(int(sid)),
                                "visto": visti.get(str(sid)) == M.VISTO,
                                "testo": testo_se(sid, esiti.get(str(sid)) == M.PRESENTE)}
                               for sid in c.get("chiave") or ()],
                    "coll_mancanti": [{"da": x.get("da"), "a": x.get("a"),
                                       "pagine": nomi(x.get("pagine"))}
                                      for x in c.get("coll_mancanti") or ()]}
            # I concetti della persona trovati: chiave presente o col nome da rivedere
            per_suo = {nodo[int(s)]: esiti.get(str(s)) for s in c.get("chiave") or ()
                       if int(s) in nodo}
            for n in out["nodi"]:
                e = per_suo.get(int(n["id"]))
                n["esito"] = ("chiave" if e == M.PRESENTE else "da_rivedere" if e == M.DIVERSO
                              else None)
            verso, fuori = set(c.get("verso_diverso") or ()), set(c.get("fuori_quadro") or ())
            for x in out["collegamenti"]:
                x["esito"] = ("verso_diverso" if x["id"] in verso else "in_piu" if x["id"] in fuori
                              else None)
        out["confronto"] = conf
        ind = c.get("indicatori") or {}
        prima = lib["giri"][-2]["indicatori"] if len(lib["giri"]) >= 2 else None
        out["indicatori"] = ind
        out["prima"] = prima
        out["rispetto"] = M.rispetto_a_prima(prima, ind) if prima else None
        return out

    def pdf_mappa(self, chi, vid, tipo: str = M.STUDENTE) -> bytes:
        """Il PDF della mia mappa o della mappa libera (passo 7c, #328; mai dello scheletro: «lo
        scheletro non si scarica»), un formato solo (decisione 5 del 27/10): A4 orizzontale con
        nome, data e «controllata il …», l'elenco in seconda pagina (`mappa_pdf.py`). La persona e
        il tutore. La mia mappa ha i concetti dello scheletro: non esce mentre una mappa senza
        guardare (a memoria o libera) è aperta; la mappa libera ha solo i concetti della persona."""
        from . import mappa_pdf
        from .servizio import NonTrovata
        if tipo not in (M.STUDENTE, M.LIBERA):
            raise NonTrovata()
        v = self._verifica(chi, vid)
        mm = self._mappe_di(v["id"])
        mia = mm.get(tipo)
        if mia is None or not mia["nodi"]:
            raise NonTrovata()
        mem = mm.get(M.MEMORIA)
        if (tipo == M.STUDENTE and getattr(chi, "id", None) == v["persona"]
                and (self._aperta(mem) or self._aperta(mm.get(M.LIBERA)))):
            # Le risposte della mappa a memoria aperta (o lo scheletro, con la libera aperta)
            # non escono nemmeno dal PDF
            raise ValueError("prima finisci la mappa senza guardare: «Controlla» o «Ho finito»")
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
