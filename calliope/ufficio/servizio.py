"""
Il servizio dell'ufficio: modelli da compilare a voce, rubrica, numerazione, fatture.

Il flusso di `compila` (tool modello_compila):
1. il modello della voce passa il nome del modello e i dati **come detti**;
2. una richiesta a parte allo stesso LLM, con lo schema JSON dei campi (output strutturati),
   li estrae: quello che non è stato detto resta null, mai inventato (come
   calliope/agenti/modelli.py); la bozza della persona tiene i dati già raccolti, così la
   risposta a «mi servono il cliente e il prezzo» completa la stessa fattura;
3. il codice risolve i nomi della rubrica, controlla i campi obbligatori (quelli mancanti
   diventano **una domanda**, con l'azione in sospeso per il turno dopo) e fa i conti
   (conti.py: numeri e totali sempre del programma);
4. un documento numerato (fattura, nota di credito, preventivo, DDT, modelli con `serie`) si
   **propone** («Fattura numero 12 del 2026 a Rossi Srl… La preparo?») e si emette solo
   con il «sì» nella risposta dopo, della stessa persona (come le installazioni): il numero
   consumato non torna indietro;
5. i testi lunghi dentro un modello (tipo testo_lungo: la descrizione di un preventivo) li
   scrive lo scrittore (sulla DGX se c'è l'agente, altrimenti lo stesso modello della voce),
   in secondo piano: il lavoro passa dal servizio dei documenti, che lo annuncia a file
   pronto come una lettera lunga.
"""

import datetime
import json
import re
import threading
import time
from pathlib import Path

from ..conferme import proposta_valida, secondi_validi
from ..documenti.consegna import LocalDelivery
from ..documenti.formato import ESTENSIONI, safe_filename, validate
from ..documenti.render import render
from . import conti, fatturapa, stampe
from .modelli import (Modello, carica, compila_docx, compila_json, compila_pptx, librerie,
                      risolvi)
from .numerazione import NumerazioneError, Numeratore
from .rubrica import (NOMI_CAMPI, Rubrica, controlla, descrivi, mancanti_per_fattura,
                      nome_di, spaziata)
from ..testi import MESI, NIENTE, RANK, iban_ok

_CARTELLE = {"fattura": "Fatture", "nota_di_credito": "Fatture", "preventivo": "Preventivi",
             "ddt": "DDT"}
# Come si chiama il documento a voce, con il genere (la apro / lo apro)
_NOMI = {"fattura": ("la fattura", True), "nota_di_credito": ("la nota di credito", True),
         "preventivo": ("il preventivo", False), "ddt": ("il DDT", False)}


def parse_data(testo, oggi: datetime.date | None = None) -> datetime.date | None:
    """«oggi», «ieri», «15 ottobre», «15/10/2026», «2026-10-15» → data. None se non si capisce.
    Conversione della forma (principio 10): la data la sceglie chi parla."""
    oggi = oggi or datetime.date.today()
    t = str(testo or "").strip().lower()
    if not t or t in ("oggi", "data di oggi"):
        return oggi
    if t == "ieri":
        return oggi - datetime.timedelta(days=1)
    if t == "domani":
        return oggi + datetime.timedelta(days=1)
    try:
        return datetime.date.fromisoformat(t[:10])
    except ValueError:
        pass
    m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2,4}))?", t)
    if m:
        d, mo, y = int(m[1]), int(m[2]), m[3]
    else:
        m = re.search(r"(\d{1,2})\s+(?:di\s+)?(" + "|".join(MESI) + r")(?:\s+(\d{4}))?", t)
        if not m:
            return None
        d, mo, y = int(m[1]), MESI.index(m[2]) + 1, m[3]
    y = int(y) + (2000 if y and len(y) == 2 else 0) if y else oggi.year
    try:
        return datetime.date(y, mo, d)
    except ValueError:
        return None


def data_detta(d: datetime.date) -> str:
    return f"{d.day} {MESI[d.month - 1]} {d.year}"


def elenco_detto(cose: list[str]) -> str:
    return cose[0] if len(cose) == 1 else ", ".join(cose[:-1]) + " e " + cose[-1]


class Ufficio:
    def __init__(self, cfg, db_path: str, documenti, estrai=None, scrittore=None,
                 cartella_modelli=None, oggi=None):
        self.cfg = cfg
        self.documenti = documenti
        self.rubrica = Rubrica(db_path)
        self.numeri = Numeratore(db_path, getattr(cfg, "ufficio_serie", None) or {})
        self.cartella_modelli = cartella_modelli
        self.catalogo, self.errori_modelli = carica(cartella_modelli)
        self.librerie = librerie()
        # estrai(messages, schema) -> testo JSON: lo stesso LLM della voce (Writer._ask)
        self._estrai = estrai or (lambda msgs, schema: documenti.writer._ask(msgs, schema))
        # scrittore(sistema, utente) -> testo: i testi lunghi (DGX se c'è, se no la voce)
        self.scrittore = scrittore
        self.female = getattr(cfg, "gender", "f") == "f"
        self.oggi = oggi or datetime.date.today      # le prove la fissano
        self.bozze: dict[str, dict] = {}
        self.offerte: dict[str, dict] = {}
        self._n = 0
        self._lock = threading.Lock()
        self.stats: list[dict] = []

    # ─────────────────────────── utilità ───────────────────────────
    def nomi_modelli(self) -> list[str]:
        """I modelli che si possono compilare qui (Word e PowerPoint solo con le librerie)."""
        return [n for n, m in self.catalogo.items()
                if m.tipo not in ("docx", "pptx") or self.librerie.get(m.tipo)]

    def ricarica(self):
        self.catalogo, self.errori_modelli = carica(self.cartella_modelli)

    def _id(self) -> str:
        with self._lock:
            self._n += 1
            return f"U{self._n}"

    def _bozza_s(self) -> float:
        return float(getattr(self.cfg, "ufficio_bozza_s", 900))

    def emittente(self) -> tuple[dict, list[str]]:
        """I dati di chi emette (calliope.locale.yaml, sezione ufficio, fatture_emittente) e
        cosa manca per una fattura."""
        raw = dict(getattr(self.cfg, "fatture_emittente", None) or {})
        dati, err = controlla(raw)
        for k in ("regime_fiscale", "iban", "aliquota_iva", "ritenuta", "tipo_ritenuta",
                  "causale_ritenuta", "cassa_tipo", "cassa_aliquota", "cassa_ritenuta",
                  "giorni_pagamento", "bollo_addebito", "natura"):
            if raw.get(k) not in (None, ""):
                dati[k] = str(raw[k]).strip()
        problemi = list(err.values())
        if dati.get("iban"):
            dati["iban"] = re.sub(r"\s+", "", dati["iban"]).upper()
            if not iban_ok(dati["iban"]):
                problemi.append("l'IBAN non torna")
        if not dati.get("partita_iva"):
            problemi.append("manca la partita IVA")
        problemi += [f"manca {NOMI_CAMPI[k]}" for k in mancanti_per_fattura(dati)
                     if k != "partita_iva"]
        return dati, problemi

    def _offri(self, owner: str, path: str, titolo: str, ext: str) -> bool:
        try:
            return self.documenti._offer(owner, {"rif": path}, titolo, ext)
        except Exception:  # noqa: BLE001 — aprire è un di più
            return False

    def _cartella(self, m: Modello) -> LocalDelivery:
        base = Path(self.documenti.delivery.folder)
        sub = _CARTELLE.get(m.tipo)
        return LocalDelivery(base / sub) if sub else LocalDelivery(base)

    def _dove(self, m: Modello) -> str:
        sub = _CARTELLE.get(m.tipo)
        d = self.documenti.delivery
        base = d.where() if hasattr(d, "where") else "nella cartella dei documenti"
        return (f"nella cartella {sub} dentro la cartella Calliope dei Documenti"
                if sub and getattr(d, "default", False) else
                (f"nella cartella {sub}" if sub else base))

    # ─────────────────────────── estrazione dei dati ───────────────────────────
    def estrai(self, m: Modello, testo: str, gia: dict, chiesti=()) -> dict:
        """I campi detti, con lo schema del modello. null = non detto. `chiesti`: i campi
        chiesti nella domanda di prima («mi servono: il cliente e le voci»): la frase detta
        risponde a quella (04/10, 26B: «A Rossi e Figli, sviluppo del sito, 800 euro.» dopo
        la domanda dava le voci ma non il cliente)."""
        noti = {k: (v.get("nome_completo") if isinstance(v, dict) else v)
                for k, v in (gia or {}).items() if v not in (None, "", [])}
        domanda = [m.campi[k].detto() for k in chiesti or () if k in m.campi]
        sistema = (
            f"Estrai i dati per compilare «{m.titolo}» da quello che è stato detto a voce. "
            "Rispondi solo con JSON compatto secondo lo schema. "
            f"Campi: {m.descrivi_campi()}. "
            "Usa SOLO quello che è stato detto (qui o nei dati già raccolti): quello che non "
            "è stato detto va a null, non inventare nomi, prezzi, quantità, aliquote, date o "
            "indirizzi. Restituisci tutti i campi: quelli già raccolti, aggiornati con quelli "
            "nuovi o corretti. Numeri come numeri (500, 12.5), senza «€» né «euro»; non "
            "calcolare totali, IVA, sconti o ritenute. Nomi di persone e ditte come detti. "
            f"Oggi è {data_detta(self.oggi())}.")
        utente = ((f"Dati già raccolti: {json.dumps(noti, ensure_ascii=False)}\n" if noti else
                   "")
                  + (f"Alla persona era stato chiesto: {elenco_detto(domanda)}. La frase detta "
                     f"risponde a questa domanda (il cliente si dice spesso con «a» o «per»: "
                     f"«a Rossi», «per Bianchi»).\n" if domanda else "")
                  + f"Detto a voce: {testo.strip()}")
        t0 = time.perf_counter()
        raw = self._estrai([{"role": "system", "content": sistema},
                            {"role": "user", "content": utente}], m.schema())
        self.stats.append({"estrazione_s": round(time.perf_counter() - t0, 2)})
        try:
            dati = json.loads(raw or "{}")
        except ValueError:
            dati = {}
        return {k: v for k, v in (dati if isinstance(dati, dict) else {}).items()
                if k in m.campi}

    # ─────────────────────────── compilazione ───────────────────────────
    def compila(self, owner: str, owner_name: str | None, livello: str, modello: str,
                testo: str, turno: int, proposta: str = "", on_scheda=None) -> dict:
        """Il risultato per il tool: {"frase", "in_sospeso"?, "job"?…}."""
        proposta = str(proposta or "").strip()
        if proposta:
            return self._conferma(owner, owner_name, livello, proposta, turno, on_scheda)
        bozza = self.bozze.get(owner)
        if bozza and time.time() - bozza["quando"] > self._bozza_s():
            bozza = None
        m = risolvi(self.catalogo, modello) if modello else None
        if m is None and bozza and (not modello or modello.lower() in ("", "stesso", "questo")):
            m = self.catalogo.get(bozza["modello"])
        if m is None:
            nomi = elenco_detto(self.nomi_modelli())
            return self._finale(f"Non ho un modello che si chiama «{modello}». Ho: {nomi}.",
                                ok=False, fatto=NIENTE)
        if m.tipo in ("docx", "pptx") and not self.librerie.get(m.tipo):
            lib = "docxtpl" if m.tipo == "docx" else "python-pptx"
            return self._finale(f"Per il modello «{m.nome}» manca la libreria {lib}: chiedi a "
                                f"chi amministra di installarla.", ok=False, fatto=NIENTE)
        if m.fiscale and RANK.get(livello, 0) < RANK.get(
                getattr(self.cfg, "ufficio_livello_fiscale", "amministra"), 2):
            return self._finale("Le fatture le può preparare solo chi amministra.", ok=False,
                                fatto=NIENTE)
        if m.tipo in ("fattura", "nota_di_credito", "preventivo", "ddt"):
            problemi = self.emittente()[1]
            if problemi:
                return self._finale(
                    "Per " + self._nome(m)[0] + " mi servono i dati di chi la emette: "
                    + elenco_detto(problemi[:4]) + ". Vanno in calliope.locale.yaml, sezione "
                    "ufficio, alla voce fatture_emittente.", ok=False, fatto=NIENTE)
        gia = dict(bozza["dati"]) if bozza and bozza["modello"] == m.nome else {}
        stessa = bool(bozza and bozza["modello"] == m.nome)
        nuovi = self.estrai(m, testo, gia, bozza.get("chiesti", ()) if stessa else ())
        dati = dict(gia)
        for k, v in nuovi.items():
            if v not in (None, "", []):
                dati[k] = v
        return self._avanti(owner, owner_name, m, dati, turno, on_scheda)

    def completa_modulo(self, owner: str, owner_name: str | None, livello: str, valori: dict,
                        turno: int, on_scheda=None) -> dict:
        """I dati scritti nel modulo sullo schermo (03/10, calliope/schermi/moduli.py): già
        controllati dal server, entrano nella bozza **senza estrazione** (né Whisper né il
        modello li vedono) e il resto è come a voce: rubrica, campi mancanti, proposta.
        `livello`: quello con cui la persona ha chiesto il documento a voce."""
        bozza = self.bozze.get(owner)
        if not bozza or time.time() - bozza["quando"] > self._bozza_s():
            return self._finale("Il documento che stavamo preparando non c'è più: dimmi di "
                                "nuovo cosa preparo.", ok=False, fatto=NIENTE)
        m = self.catalogo.get(bozza["modello"])
        if m is None:
            return self._finale("Quel modello non c'è più.", ok=False, fatto=NIENTE)
        if m.fiscale and RANK.get(livello, 0) < RANK.get(
                getattr(self.cfg, "ufficio_livello_fiscale", "amministra"), 2):
            return self._finale("Le fatture le può preparare solo chi amministra.", ok=False,
                                fatto=NIENTE)
        dati = dict(bozza["dati"])
        for k, v in (valori or {}).items():
            if k in m.campi and v not in (None, "", []):
                dati[k] = v
        res = self._avanti(owner, owner_name, m, dati, turno, on_scheda)
        if res.get("frase"):
            res["frase"] = "Grazie, ho i dati. " + res["frase"]
        return res

    def _avanti(self, owner, owner_name, m: Modello, dati: dict, turno: int,
                on_scheda) -> dict:
        """Dai dati raccolti (detti o scritti) al documento: rubrica, campi mancanti, conti,
        proposta o lavoro."""
        self.bozze[owner] = {"modello": m.nome, "dati": dati, "quando": time.time()}
        # Nomi della rubrica
        for n, c in m.campi.items():
            if c.tipo != "anagrafica" or dati.get(n) in (None, "") or isinstance(dati[n], dict):
                continue
            trovato, altri = self.rubrica.trova(str(dati[n]), owner)
            if trovato is None:
                detto = dati.pop(n)
                if altri:
                    nomi = [a["nome_completo"] for a in altri]
                    return self._domanda(m, f"In rubrica ho {elenco_detto(nomi)}: quale "
                                            f"intendi?", campi=[n], owner=owner, scelte=nomi)
                return self._domanda(
                    m, f"Non trovo «{detto}» nella rubrica. Dimmi un altro nome, oppure "
                       f"aggiungilo prima alla rubrica con i suoi dati.", completa=False)
            dati[n] = trovato
        mancano = m.mancanti(dati)
        self.bozze[owner]["chiesti"] = list(mancano)
        if mancano:
            cose = elenco_detto([m.campi[k].detto() for k in mancano])
            return self._domanda(m, f"Per {self._nome(m)[0]} mi servono: {cose}. Me li dici?",
                                 campi=mancano, owner=owner)
        if m.tipo in ("fattura", "nota_di_credito", "preventivo", "ddt"):
            return self._prepara_pronto(owner, owner_name, m, dati, turno, on_scheda)
        if m.serie:
            return self._proponi(owner, turno, m, dati, None,
                                 f"{m.titolo[0].upper()}{m.titolo[1:]} numero "
                                 f"{self.numeri.prossimo(m.serie, self.oggi().year)} del "
                                 f"{self.oggi().year}")
        return self._lavoro(owner, owner_name, m, dati, None, on_scheda)

    def _nome(self, m: Modello) -> tuple[str, bool]:
        if m.tipo in _NOMI:
            return _NOMI[m.tipo]
        return f"il modello «{m.titolo}»", False

    def _finale(self, frase: str, **extra) -> dict:
        return {"ok": extra.pop("ok", True), "frase": frase, **extra}

    def _domanda(self, m: Modello, frase: str, completa: bool = True, campi=None,
                 owner: str | None = None, scelte=None) -> dict:
        """Una domanda per completare il modello: il turno dopo il modello della voce
        richiama modello_compila con lo stesso modello e i dati nuovi. Con `campi` anche il
        modulo per lo schermo (03/10, `modulo`: lo toglie e lo apre il tool)."""
        out = self._finale(frase, ok=False, fatto="il documento NON è ancora pronto: mancano "
                                                  "dei dati")
        if completa:
            out["in_sospeso"] = {"domanda": frase, "cosa": f"completare {self._nome(m)[0]}",
                                 "tool": "modello_compila",
                                 "argomenti": {"modello": m.nome}}
        spec = self._modulo(m, campi or (), owner, scelte, frase)
        if spec:
            out["modulo"] = spec
        return out

    def _modulo(self, m: Modello, campi, owner, scelte, domanda: str) -> dict | None:
        """La specifica del modulo per i campi che mancano (calliope/schermi/moduli.py): un
        campo per dato, del tipo del modello. Le tabelle libere restano a voce."""
        from ..schermi.moduli import campo
        out = []
        for n in campi:
            c = m.campi.get(n)
            if c is None:
                continue
            etichetta = re.sub(r"^(il|lo|la|l'|i|gli|le)\s*", "", c.detto(), flags=re.I)
            etichetta = etichetta[:1].upper() + etichetta[1:]
            obbl = c.obbligatorio and c.predefinito is None
            if c.tipo == "anagrafica":
                if scelte:
                    out.append(campo(n, etichetta, "scelta", obbl, opzioni=list(scelte)))
                else:
                    nomi = [x["nome_completo"] for x in self.rubrica.visibili(owner)][:60] \
                        if owner else []
                    out.append(campo(n, etichetta + " (nome in rubrica)", "testo", obbl,
                                     suggerimenti=nomi))
            elif c.tipo == "righe":
                out.append(campo(n, etichetta, "righe", obbl, prezzi=c.prezzi))
            elif c.tipo in ("testo", "testo_lungo", "numero", "importo", "data", "booleano",
                            "elenco"):
                out.append(campo(n, etichetta, c.tipo, obbl))
        if not out:
            return None
        nome = self._nome(m)[0]
        return {"chiave": f"modello:{m.nome}", "titolo": f"Dati per {nome}",
                "domanda": domanda, "campi": out}

    # ── fattura, nota di credito, preventivo, DDT ──
    def _prepara_pronto(self, owner, owner_name, m: Modello, dati: dict, turno: int,
                        on_scheda) -> dict:
        em, problemi = self.emittente()
        if problemi:
            return self._finale(
                "Per " + self._nome(m)[0] + " mi servono i dati di chi la emette: "
                + elenco_detto(problemi[:4]) + ". Vanno in calliope.locale.yaml, sezione "
                "ufficio, alla voce fatture_emittente.", ok=False, fatto=NIENTE)
        cliente = dati["cliente"]
        if m.fiscale:
            buchi = mancanti_per_fattura(cliente)
            if buchi:
                cose = elenco_detto([NOMI_CAMPI[k] for k in buchi])
                return self._finale(
                    f"Per fatturare a {nome_di(cliente)} mi mancano in rubrica {cose}: "
                    f"aggiungili alla sua scheda e poi riprova.", ok=False, fatto=NIENTE)
        data = parse_data(dati.get("data"), self.oggi())
        if data is None:
            detta = dati.pop("data", None)
            return self._domanda(m, f"Non ho capito la data «{detta}»: me la ridici?",
                                 campi=["data"], owner=owner)
        if m.fiscale and data > self.oggi():
            return self._domanda(m, "Una fattura non può avere una data futura: che data metto?",
                                 campi=["data"], owner=owner)
        doc = {"emittente": em, "cliente": cliente, "data": data}
        if m.tipo == "ddt":
            righe = []
            for i, r in enumerate(dati["righe"], 1):
                try:
                    q = conti.dec(r.get("quantita"), f"riga {i}") if r.get("quantita") not in (
                        None, "") else None
                except conti.DatiNonValidi:
                    q = None
                if q is None or not str(r.get("descrizione") or "").strip():
                    return self._domanda(m, f"Del bene {i} mi servono descrizione e quantità.")
                righe.append({"descrizione": str(r["descrizione"]).strip(), "quantita": q,
                              "unita": str(r.get("unita") or "").strip()})
            doc.update({k: dati.get(k) for k in ("causale_trasporto", "colli", "peso", "aspetto",
                                                  "trasporto_a_cura", "vettore",
                                                  "luogo_destinazione")})
            doc["trasporto_a_cura"] = doc.get("trasporto_a_cura") or "mittente"
            doc["righe"] = righe
            frase = (f"DDT numero {self.numeri.prossimo('ddt', data.year)} del {data.year} a "
                     f"{nome_di(cliente)}, con {len(righe)} "
                     f"{'voce' if len(righe) == 1 else 'voci'}")
            return self._proponi(owner, turno, m, dati, doc, frase)
        regime = em.get("regime_fiscale") or "RF01"
        forfettario = regime == "RF19"
        aliq = "0" if forfettario else em.get("aliquota_iva", "22")
        natura = "N2.2" if forfettario else em.get("natura", "")
        rit_emittente = em.get("ritenuta") and not forfettario and m.tipo != "preventivo"
        con_rit = dati.get("ritenuta")
        if con_rit is None:
            con_rit = bool(rit_emittente and cliente.get("partita_iva"))
        try:
            righe = conti.prepara_righe(dati["righe"], aliq, natura,
                                        iva_inclusa=bool(dati.get("iva_inclusa")),
                                        ritenuta_predefinita=bool(con_rit))
            ritenuta = ({"tipo": em.get("tipo_ritenuta") or "RT01",
                         "aliquota": em.get("ritenuta") or "20",
                         "causale": em.get("causale_ritenuta") or "A"} if con_rit else None)
            cassa = ({"tipo": em["cassa_tipo"], "aliquota": em.get("cassa_aliquota") or "4",
                      "aliquota_iva": aliq if not forfettario else "0",
                      "natura": natura if forfettario else "",
                      "ritenuta": str(em.get("cassa_ritenuta", "")).lower() in ("si", "sì",
                                                                                "true", "1")}
                     if em.get("cassa_tipo") else None)
            totali = conti.calcola(
                righe, ritenuta, cassa, bollo="auto",
                bollo_addebito=str(em.get("bollo_addebito", "si")).lower() in ("si", "sì",
                                                                               "true", "1"))
        except conti.DatiNonValidi as e:
            return self._domanda(m, "Qualcosa non torna: " + elenco_detto(e.errori[:3])
                                 + ". Me lo ridici?")
        doc.update({"righe_dette": dati["righe"], "totali": totali,
                    "causale": dati.get("causale") or dati.get("note") or ""})
        if m.tipo == "preventivo":
            doc.update({"oggetto": dati["oggetto"], "descrizione_detta":
                        dati.get("descrizione") or "", "validita_giorni":
                        dati.get("validita_giorni") or 30, "note": dati.get("note") or ""})
        if m.fiscale:
            doc["tipo"] = "TD04" if m.tipo == "nota_di_credito" else "TD01"
            if m.tipo == "nota_di_credito":
                doc["collegata"] = {"numero": str(dati["fattura_collegata"]),
                                    "data": parse_data(dati.get("data_fattura_collegata"),
                                                       self.oggi())
                                    if dati.get("data_fattura_collegata") else None}
            giorni = dati.get("scadenza_giorni") or em.get("giorni_pagamento") or 30
            try:
                giorni = int(float(giorni))
            except (TypeError, ValueError):
                giorni = 30
            doc["pagamento"] = ({"modalita": "MP05", "iban": em["iban"],
                                 "scadenza": data + datetime.timedelta(days=giorni)}
                                if em.get("iban") else None)
        n = self.numeri.prossimo(m.serie, data.year)
        nome, fem = self._nome(m)
        frase = (f"{nome[0].upper()}{nome[1:]} numero {n} del {data.year} a "
                 f"{nome_di(cliente)}, {len(totali['righe'])} "
                 f"{'voce' if len(totali['righe']) == 1 else 'voci'}: "
                 f"{conti.riassunto_detto(totali)}")
        return self._proponi(owner, turno, m, dati, doc, frase)

    def _proponi(self, owner, turno, m: Modello, dati, doc, frase: str) -> dict:
        fem = self._nome(m)[1]
        domanda = "La preparo?" if fem else "Lo preparo?"
        oid = self._id()
        self.offerte[owner] = {"id": oid, "turno": turno, "azione": "emetti",
                               "modello": m.nome, "dati": dati, "doc": doc,
                               "quando": time.time()}
        return self._finale(f"{frase}. {domanda}", fatto="proposta: il documento NON è ancora "
                            "stato preparato", proposta=oid,
                            in_sospeso={"domanda": domanda, "cosa": f"preparare "
                                        f"{self._nome(m)[0]}", "tool": "modello_compila",
                                        "argomenti": {"modello": m.nome, "dati": "sì",
                                                      "proposta": oid}})

    def _offerta(self, owner, proposta, turno, azioni, consuma: bool = True) -> dict | None:
        """La proposta ancora valida: nei turni dopo, per `azione_in_sospeso_turni` turni ed
        entro `azione_in_sospeso_s` (04/10, calliope/conferme.py; prima solo nel turno subito
        dopo). `consuma`: la toglie (dopo i controlli dei permessi, non prima)."""
        off = self.offerte.get(owner)
        limite = secondi_validi(self.cfg)
        if not off or off["id"] != proposta or off["azione"] not in azioni:
            return None
        if not proposta_valida(self.cfg, off["turno"], turno) or                 time.time() - off["quando"] > limite:
            return None
        if consuma:
            self.offerte.pop(owner, None)
        return off

    def _conferma(self, owner, owner_name, livello, proposta, turno, on_scheda) -> dict:
        off = self._offerta(owner, proposta, turno, ("emetti",), consuma=False)
        if off is None:
            return self._finale("Prima devo dirti cosa preparo e avere il tuo sì: dimmelo di "
                                "nuovo.", ok=False, fatto=NIENTE, regola="ufficio_senza_offerta")
        m = self.catalogo.get(off["modello"])
        if m is None:
            return self._finale("Quel modello non c'è più.", ok=False, fatto=NIENTE)
        if m.fiscale and RANK.get(livello, 0) < RANK.get(
                getattr(self.cfg, "ufficio_livello_fiscale", "amministra"), 2):
            return self._finale("Le fatture le può preparare solo chi amministra.", ok=False,
                                fatto=NIENTE)
        self.offerte.pop(owner, None)
        self.bozze.pop(owner, None)
        return self._lavoro(owner, owner_name, m, off["dati"], off["doc"], on_scheda)

    # ── il lavoro: testi lunghi, numero, file ──
    def _lavoro(self, owner, owner_name, m: Modello, dati, doc, on_scheda) -> dict:
        from ..documenti.servizio import Job
        job = Job("modello", owner, owner_name)
        job.on_scheda = on_scheda
        self.documenti._submit(job, lambda j: self._produci(j, m, dati, doc))
        res = self.documenti.wait(job, float(getattr(self.cfg, "documenti_attesa_s", 4.0)))
        if res is not None:
            return res
        nome, fem = self._nome(m)
        frase = (f"{'Te la preparo' if fem else 'Te lo preparo'}: ci vuole un po', ti avviso "
                 f"quando è {'pronta' if fem else 'pronto'}.")
        return self._finale(frase, in_preparazione=True,
                            fatto="il documento è in preparazione, NON è ancora pronto")

    def testo_lungo(self, m: Modello, campo: str, detto: str, dati: dict) -> str:
        """Il testo lungo di un campo, dallo scrittore; senza scrittore (o se non riesce)
        resta quello detto. Solo i fatti detti: niente prezzi né date inventati."""
        if not self.scrittore or not str(detto or "").strip():
            return str(detto or "")
        c = m.campi[campo]
        sistema = ("Scrivi in italiano corretto e professionale il testo richiesto per un "
                   "documento: da 1 a 3 paragrafi separati da una riga vuota, niente markdown, "
                   "niente titoli, niente saluti. Usa solo i fatti detti: non aggiungere "
                   "prezzi, quantità, date, nomi o promesse che non sono stati detti.")
        contesto = {k: (v.get("nome_completo") if isinstance(v, dict) else v)
                    for k, v in dati.items() if k != campo and not isinstance(v, list)}
        utente = (f"Documento: {m.titolo}. Testo da scrivere: {c.detto()}.\n"
                  f"Altri dati: {json.dumps(contesto, ensure_ascii=False)}\n"
                  f"Quello che è stato detto: {str(detto).strip()}")
        try:
            t0 = time.perf_counter()
            testo = str(self.scrittore(sistema, utente) or "").strip()
            self.stats.append({"scrittore_s": round(time.perf_counter() - t0, 2)})
        except Exception as e:  # noqa: BLE001 — si ripiega su quello detto
            print(f"   [UFFICIO] scrittore non riuscito: {type(e).__name__}: {e}", flush=True)
            return str(detto)
        testo = re.sub(r"[*#`_]{1,3}", "", testo)
        return testo[:2800] or str(detto)

    def _produci(self, job, m: Modello, dati: dict, doc: dict | None) -> dict:
        t0 = time.perf_counter()
        dati = dict(dati)
        for n, c in m.campi.items():
            if c.tipo == "testo_lungo" and dati.get(n):
                dati[n] = self.testo_lungo(m, n, dati[n], dati)
        if doc is not None and m.tipo == "preventivo":
            doc = dict(doc, descrizione=dati.get("descrizione") or "")
        out = self._scrivi(job.owner, job.owner_name, m, dati, doc)
        self.stats.append({"modello": m.nome, "totale_s": round(time.perf_counter() - t0, 2)})
        return out

    def _scrivi(self, owner, owner_name, m: Modello, dati: dict, doc: dict | None) -> dict:
        nome, fem = self._nome(m)
        consegna = self._cartella(m)
        fonts = getattr(self.cfg, "documenti_font", None)
        data = (doc or {}).get("data") or self.oggi()
        info: dict = {}

        def prepara(numero: int | None, testo_numero: str | None) -> dict:
            files = []
            if m.tipo in ("fattura", "nota_di_credito"):
                f = dict(doc, numero=testo_numero,
                         progressivo=fatturapa.progressivo(m.serie, numero, data.year),
                         trasmittente=(doc["emittente"].get("codice_fiscale")
                                       or doc["emittente"]["partita_iva"]))
                errori = fatturapa.controlla(f, doc["totali"])
                xml = fatturapa.costruisci(f, doc["totali"])
                xsd = fatturapa.valida_xsd(xml, fatturapa.cartella_xsd(self.cfg))
                if errori or xsd:
                    raise conti.DatiNonValidi(errori or xsd)
                info["xsd"] = xsd is not None
                titolo = "Nota di credito" if m.tipo == "nota_di_credito" else "Fattura"
                blocchi = validate("pdf", stampe.fattura(f, doc["totali"], titolo))
                pdf = render("pdf", blocchi, fonts)
                d1 = consegna.deliver(safe_filename(blocchi["titolo"]), "pdf", pdf)
                files.append(d1["rif"])
                xml_path = Path(consegna.folder) / fatturapa.nome_file(f["trasmittente"],
                                                                       f["progressivo"])
                if xml_path.exists():
                    raise conti.DatiNonValidi([f"il file {xml_path.name} esiste già"])
                xml_path.write_bytes(xml)
                files.append(str(xml_path))
                info.update(blocchi=blocchi, pdf=d1, xml=xml_path.name, totali=doc["totali"])
            elif m.tipo in ("preventivo", "ddt"):
                p = dict(doc, numero=testo_numero)
                blocchi = validate("pdf", stampe.preventivo(p, doc["totali"])
                                   if m.tipo == "preventivo" else stampe.ddt(p))
                d1 = consegna.deliver(safe_filename(blocchi["titolo"]), "pdf",
                                      render("pdf", blocchi, fonts))
                files.append(d1["rif"])
                info.update(blocchi=blocchi, pdf=d1, totali=doc.get("totali"))
            else:
                ctx = self.contesto(m, dati, testo_numero, numero, data)
                if m.tipo == "json":
                    blocchi = validate(m.uscita, compila_json(m, ctx))
                    d1 = consegna.deliver(safe_filename(blocchi["titolo"]), ESTENSIONI[m.uscita],
                                          render(m.uscita, blocchi, fonts))
                    info.update(blocchi=blocchi)
                else:
                    raw = (compila_docx if m.tipo == "docx" else compila_pptx)(m.file, ctx)
                    stem = safe_filename(f"{m.titolo} {testo_numero or ''} "
                                         f"{_nome_cliente(ctx)}".strip())
                    d1 = consegna.deliver(stem, m.tipo, raw)
                files.append(d1["rif"])
                info.update(pdf=d1)
            return {"file": files}

        try:
            if m.serie:
                numero, _ = self.numeri.emetti(m.serie, data, prepara, owner, owner_name,
                                               m.nome, (doc or {}).get("oggetto") or m.titolo,
                                               conti.serializza({k: v for k, v in dati.items()}))
                info["numero"] = numero
            else:
                prepara(None, None)
        except (conti.DatiNonValidi, NumerazioneError) as e:
            errs = getattr(e, "errori", None) or [str(e)]
            print(f"   [UFFICIO] {m.nome} non emesso: {'; '.join(errs)}", flush=True)
            riuscita = "riuscita" if self.female else "riuscito"
            frase = f"Non sono {riuscita} a preparare {nome}: {errs[0]}."
            return {"ok": False, "fatto": NIENTE, "errore": "; ".join(errs), "frase": frase,
                    "annuncio": frase}
        d1 = info["pdf"]
        ext = Path(d1["nome_file"]).suffix.lstrip(".")
        if info.get("blocchi") and m.tipo == "json":
            self.documenti.archive.add(owner, owner_name, m.uscita, info["blocchi"]["titolo"],
                                       d1["rif"], d1["nome_file"], info["blocchi"],
                                       d1.get("mtime"), f"modello {m.nome}")
        apribile = self._offri(owner, d1["rif"], Path(d1["nome_file"]).stem, ext)
        chiedi = (" La apro?" if fem else " Lo apro?") if apribile else ""
        cliente = (doc or {}).get("cliente") or next(
            (v for v in dati.values() if isinstance(v, dict) and "nome_completo" in v), None)
        chi = f" per {nome_di(cliente)}" if cliente else ""
        num = (f" numero {info['numero']} del {data.year}" if info.get("numero") else "")
        tot = info.get("totali")
        soldi = ""
        if tot:
            soldi = f": totale {conti.euro_detto(tot['totale'])}"
            if tot.get("ritenuta"):
                soldi += f", da pagare {conti.euro_detto(tot['da_pagare'])}"
        dove = self._dove(m)
        if m.fiscale:
            extra = (" Il PDF è la copia di cortesia; il file XML va caricato a mano sul "
                     "portale Fatture e Corrispettivi o dal tuo intermediario: io non lo "
                     "invio.")
        else:
            extra = ""
        pronto = "pronta" if fem else "pronto"
        corpo = f"{nome}{num}{chi}{soldi}, {dove}.{extra}{chiedi}"
        scheda = None
        if info.get("blocchi"):
            from ..documenti.servizio import _scheda
            scheda = _scheda(info["blocchi"], "pdf" if m.tipo != "json" else m.uscita,
                             d1["nome_file"])
        out = {"ok": True, "modello": m.nome, "nome_file": d1["nome_file"],
               "numero": info.get("numero"), "frase": f"Ho preparato {corpo}",
               "annuncio": f"È {pronto} {corpo}", "scheda": scheda,
               "cosa_fare": "Non leggere il documento."
               + (" Se chiede di aprirlo chiama pc_apri_file con risultato 1." if apribile
                  else "")}
        if info.get("xml"):
            out["xml"] = info["xml"]
            out["xsd_verificato"] = info.get("xsd", False)
        if apribile:
            from ..documenti.servizio import in_sospeso
            out["in_sospeso"] = in_sospeso(chiedi.strip(), nome)
        return out

    def contesto(self, m: Modello, dati: dict, testo_numero, numero, data) -> dict:
        """Il contesto dei modelli Word e PowerPoint: i campi (con i contatti interi e le
        righe con gli importi già scritti all'italiana) più numero, data, emittente e totali."""
        em, _ = self.emittente()
        ctx = {"numero": testo_numero or "", "numero_progressivo": numero or "",
               "anno": data.year, "data": data_detta(data), "oggi": data_detta(self.oggi()),
               "emittente": _contatto_ctx(em) if em else {}}
        for n, c in m.campi.items():
            v = dati.get(n)
            if v in (None, "") and c.predefinito is not None:
                v = c.predefinito
            if c.tipo == "anagrafica":
                ctx[n] = _contatto_ctx(v) if isinstance(v, dict) else {"nome": v or ""}
            elif c.tipo == "righe" and v:
                try:
                    righe = conti.prepara_righe(v, em.get("aliquota_iva", "22") if em else "22",
                                                "N2.2" if (em or {}).get("regime_fiscale") ==
                                                "RF19" else "")
                    tot = conti.calcola(righe)
                except conti.DatiNonValidi:
                    ctx[n] = v
                    continue
                ctx[n] = [{"descrizione": r["descrizione"],
                           "quantita": stampe._qta(r["quantita"]),
                           "prezzo": conti.euro(r["prezzo"]), "importo": conti.euro(r["totale"]),
                           "iva": stampe._iva(r)} for r in tot["righe"]]
                ctx["totali"] = {"imponibile": conti.euro(tot["imponibile"]),
                                 "iva": conti.euro(tot["imposta"]),
                                 "totale": conti.euro(tot["totale"])}
            elif c.tipo in ("numero", "importo") and isinstance(v, (int, float)):
                ctx[n] = conti.euro(conti.dec(v), c.tipo == "importo") if c.tipo == "importo" \
                    else stampe._qta(conti.dec(v))
            elif c.tipo == "booleano":
                ctx[n] = "sì" if v else "no"
            else:
                ctx[n] = "" if v is None else v
        return ctx

    # ─────────────────────────── rubrica ───────────────────────────
    def rubrica_cerca(self, owner: str, testo: str) -> dict:
        res = self.rubrica.cerca(testo, owner)
        if not res:
            return self._finale(f"In rubrica non trovo «{testo}».", ok=False)
        migliori = [c for s, c in res if s >= res[0][0] - 0.1][:3]
        if len(migliori) == 1:
            c = migliori[0]
            buchi = mancanti_per_fattura(c)
            nota = (f" Per fatturare mancano {elenco_detto([NOMI_CAMPI[k] for k in buchi])}."
                    if buchi else "")
            return self._finale(f"In rubrica c'è {descrivi(c)}.{nota}", contatto=c["id"])
        return self._finale("In rubrica ho " + elenco_detto(
            [descrivi(c, completo=False) for c in migliori]) + ".")

    def _schema_rubrica(self) -> dict:
        s = {"anyOf": [{"type": "string"}, {"type": "null"}]}
        props = {k: s for k in ("tipo", "denominazione", "nome", "cognome", "partita_iva",
                                "codice_fiscale", "indirizzo", "civico", "cap", "comune",
                                "provincia", "nazione", "email", "pec", "codice_destinatario",
                                "telefono", "note")}
        props["solo_per_me"] = {"anyOf": [{"type": "boolean"}, {"type": "null"}]}
        return {"type": "object", "properties": props, "required": list(props)}

    def _estrai_contatto(self, testo: str, attuale: dict | None) -> dict:
        sistema = (
            "Estrai i dati di un contatto (cliente, fornitore o altro) da quello che è stato "
            "detto a voce. Rispondi solo con JSON compatto secondo lo schema. tipo: cliente, "
            "fornitore o contatto. denominazione: il nome di una ditta o società (con Srl, "
            "Spa…); nome e cognome: per una persona. indirizzo: la via senza il numero; "
            "civico: il numero; provincia: la sigla (MI, RM…). Codici e numeri come detti, "
            "cifre comprese. solo_per_me: true solo se dice che è solo suo. Quello che non è "
            "stato detto va a null: non inventare niente."
            + (" Ti do il contatto attuale: restituisci SOLO i campi da cambiare, gli altri a "
               "null." if attuale else ""))
        utente = ((f"Contatto attuale: {json.dumps(attuale, ensure_ascii=False)}\n"
                   if attuale else "") + f"Detto a voce: {testo.strip()}")
        raw = self._estrai([{"role": "system", "content": sistema},
                            {"role": "user", "content": utente}], self._schema_rubrica())
        try:
            d = json.loads(raw or "{}")
        except ValueError:
            d = {}
        return {k: v for k, v in (d if isinstance(d, dict) else {}).items()
                if v not in (None, "", [])}

    def rubrica_salva(self, owner: str, livello: str, azione: str, nome: str, testo: str,
                      turno: int, proposta: str = "") -> dict:
        proposta = str(proposta or "").strip()
        if proposta:
            off = self._offerta(owner, proposta, turno, ("aggiungi", "modifica", "elimina"))
            if off is None:
                return self._finale("Prima devo dirti cosa cambio in rubrica e avere il tuo "
                                    "sì: dimmelo di nuovo.", ok=False, fatto=NIENTE,
                                    regola="ufficio_senza_offerta")
            try:
                if off["azione"] == "aggiungi":
                    self.rubrica.aggiungi(off["dati"], off["ambito"], owner)
                    frase = f"Fatto, ho aggiunto {nome_di(off['dati'])} alla rubrica."
                elif off["azione"] == "modifica":
                    c = self.rubrica.modifica(off["contatto"], off["dati"], owner)
                    frase = f"Fatto, ho aggiornato {c['nome_completo']} in rubrica."
                else:
                    self.rubrica.elimina(off["contatto"], owner)
                    frase = f"Fatto, ho tolto {off['nome']} dalla rubrica."
            except ValueError as e:
                return self._finale(f"Non ci sono riuscita: {e}.", ok=False, fatto=NIENTE)
            return self._finale(frase)
        azione = str(azione or "aggiungi").strip().lower()
        if azione not in ("aggiungi", "modifica", "elimina"):
            azione = "aggiungi"
        if azione in ("modifica", "elimina"):
            c, altri = self.rubrica.trova(nome or testo, owner)
            if c is None:
                if altri:
                    return self._finale("In rubrica ho " + elenco_detto(
                        [a["nome_completo"] for a in altri]) + ": quale intendi?", ok=False,
                        fatto=NIENTE)
                return self._finale(f"In rubrica non trovo «{nome}».", ok=False, fatto=NIENTE)
            if c["ambito"] not in ("casa", owner):
                return self._finale("Quel contatto non è tuo.", ok=False, fatto=NIENTE)
            if azione == "elimina":
                oid = self._id()
                self.offerte[owner] = {"id": oid, "turno": turno, "azione": "elimina",
                                       "contatto": c["id"], "nome": c["nome_completo"],
                                       "quando": time.time()}
                return self._proposta_rubrica(oid, f"Tolgo {c['nome_completo']} dalla rubrica?")
            nuovi = self._estrai_contatto(testo, {k: v for k, v in c.items()
                                                  if k not in ("id", "ambito", "nome_completo")})
            nuovi.pop("solo_per_me", None)
            dati, err = controlla(nuovi)
            if err:
                return self._finale(_errori_detti(err), ok=False, fatto=NIENTE)
            dati = {k: v for k, v in dati.items() if v != c.get(k)}
            if not dati:
                return self._finale(f"Non ho capito cosa cambiare per {c['nome_completo']}: "
                                    f"me lo ridici?", ok=False, fatto=NIENTE)
            oid = self._id()
            self.offerte[owner] = {"id": oid, "turno": turno, "azione": "modifica",
                                   "contatto": c["id"], "dati": dati, "quando": time.time()}
            cambi = elenco_detto([f"{NOMI_CAMPI.get(k, k)} "
                                  f"{spaziata(v) if k in ('partita_iva', 'codice_fiscale', 'codice_destinatario') else v}"
                                  for k, v in dati.items()])
            return self._proposta_rubrica(oid, f"Per {c['nome_completo']} cambio {cambi}. "
                                               f"Va bene?")
        nuovi = self._estrai_contatto(f"{nome}. {testo}" if nome and nome not in testo
                                      else testo, None)
        personale = bool(nuovi.pop("solo_per_me", False))
        dati, err = controlla(nuovi)
        ambito = owner if personale else "casa"
        if err:
            # Un codice che non torna: anche il modulo sullo schermo, con i dati già capiti e
            # l'errore sul campo (03/10)
            return self._finale(_errori_detti(err), ok=False, fatto=NIENTE,
                                modulo=self.modulo_contatto(dati, err, ambito, nuovi))
        if not (dati.get("denominazione") or dati.get("nome") or dati.get("cognome")):
            return self._finale("Come si chiama il contatto da aggiungere?", ok=False,
                                fatto=NIENTE, modulo=self.modulo_contatto(dati, {}, ambito))
        dati.setdefault("tipo", "cliente")
        dup = self.rubrica.duplicato(dati, owner)
        if dup:
            return self._finale(f"In rubrica c'è già {descrivi(dup, completo=False)}: se vuoi "
                                f"cambiarlo dimmi cosa aggiornare.", ok=False, fatto=NIENTE)
        oid = self._id()
        self.offerte[owner] = {"id": oid, "turno": turno, "azione": "aggiungi", "dati": dati,
                               "ambito": ambito, "quando": time.time()}
        solo = " solo per te" if personale else ""
        out = self._proposta_rubrica(oid, f"Aggiungo{solo} alla rubrica {descrivi(dati)}? ")
        buchi = mancanti_per_fattura(dati) if dati.get("tipo") == "cliente" else []
        if buchi:
            # Per fatturare mancano dati: sullo schermo si possono scrivere (il «sì» a voce lo
            # aggiunge com'è)
            spec = self.modulo_contatto(dati, {}, ambito)
            spec["frase_schermo"] = (f"Per fatturare a {nome_di(dati)} "
                                     f"{'manca' if len(buchi) == 1 else 'mancano'} "
                                     f"{elenco_detto([NOMI_CAMPI[k] for k in buchi])}: puoi "
                                     f"scriverli sullo schermo. Intanto lo aggiungo così?")
            out["modulo"] = spec
        return out

    def modulo_contatto(self, dati: dict, errori: dict, ambito: str,
                        detti: dict | None = None) -> dict:
        """Il modulo di un contatto nuovo per lo schermo (calliope/schermi/moduli.py): i campi
        già capiti precompilati, quelli sbagliati con l'errore. Un valore sbagliato resta come
        detto (`detti`), così si corregge la cifra invece di riscrivere tutto."""
        from ..schermi.moduli import campo
        detti = detti or {}

        def v(k):
            return detti.get(k) if k in errori else dati.get(k)

        persona = bool(dati.get("nome") or dati.get("cognome")) and not dati.get("denominazione")
        campi = [campo("tipo", "Tipo", "scelta", True, dati.get("tipo") or "cliente",
                       opzioni=["cliente", "fornitore", "contatto"])]
        if persona:
            campi += [campo("nome", "Nome", "testo", True, v("nome")),
                      campo("cognome", "Cognome", "testo", True, v("cognome"))]
        else:
            campi.append(campo("denominazione", "Ragione sociale (o nome e cognome)", "testo",
                               True, v("denominazione")))
        for k, etichetta, tipo in (("partita_iva", "Partita IVA", "partita_iva"),
                                   ("codice_fiscale", "Codice fiscale", "codice_fiscale"),
                                   ("indirizzo", "Indirizzo (via)", "testo"),
                                   ("civico", "Numero civico", "testo"),
                                   ("cap", "CAP", "cap"), ("comune", "Comune", "testo"),
                                   ("provincia", "Provincia (sigla)", "provincia"),
                                   ("email", "Email", "email"), ("pec", "PEC", "email"),
                                   ("codice_destinatario", "Codice destinatario SdI",
                                    "codice_destinatario")):
            campi.append(campo(k, etichetta, tipo, False, v(k),
                               errore=errori.get(k, "")[:1].upper() + errori.get(k, "")[1:]
                               if errori.get(k) else ""))
        return {"chiave": "rubrica", "titolo": "Contatto nuovo per la rubrica",
                "domanda": "Controlla i dati e invia: lo aggiungo alla rubrica.",
                "campi": campi, "ambito": ambito}

    def rubrica_da_modulo(self, owner: str, valori: dict, ambito: str) -> dict:
        """Un contatto nuovo scritto nel modulo sullo schermo: i valori, già controllati dal
        server, vanno in rubrica senza passare dal modello. Inviare il modulo vale come il
        «sì»: chi l'ha inviato è chi aveva chiesto di aggiungerlo a voce."""
        dati, err = controlla(dict(valori or {}))
        if err:
            return self._finale(_errori_detti(err), ok=False, fatto=NIENTE,
                                modulo=self.modulo_contatto(dati, err, ambito, valori))
        if not (dati.get("denominazione") or (dati.get("nome") and dati.get("cognome"))):
            return self._finale("Manca il nome del contatto.", ok=False, fatto=NIENTE,
                                modulo=self.modulo_contatto(dati, {}, ambito))
        dup = self.rubrica.duplicato(dati, owner)
        if dup:
            return self._finale(f"In rubrica c'è già {descrivi(dup, completo=False)}: se vuoi "
                                f"cambiarlo dimmi cosa aggiornare.", ok=False, fatto=NIENTE)
        off = self.offerte.get(owner)
        if off and off.get("azione") == "aggiungi":
            self.offerte.pop(owner, None)          # la proposta a voce non serve più
        self.rubrica.aggiungi(dati, ambito if ambito in ("casa", owner) else "casa", owner)
        buchi = mancanti_per_fattura(dati) if dati.get("tipo", "cliente") == "cliente" else []
        nota = (f" Per fatturare {'manca' if len(buchi) == 1 else 'mancano'} ancora "
                f"{elenco_detto([NOMI_CAMPI[k] for k in buchi])}." if buchi else "")
        return self._finale(f"Grazie, ho aggiunto {nome_di(dati)} alla rubrica.{nota}")

    def _proposta_rubrica(self, oid: str, frase: str) -> dict:
        frase = frase.strip()
        return self._finale(frase, fatto="proposta: la rubrica NON è ancora cambiata",
                            proposta=oid,
                            in_sospeso={"domanda": frase.rsplit(". ", 1)[-1],
                                        "cosa": "cambiare la rubrica",
                                        "tool": "anagrafica_salva",
                                        "argomenti": {"proposta": oid}})

    def dimentica(self, owner: str):
        """Calliope si addormenta: bozze e proposte della persona non valgono più."""
        self.bozze.pop(owner, None)
        self.offerte.pop(owner, None)


def _errori_detti(err: dict) -> str:
    testo = elenco_detto(list(err.values()))
    return testo[0].upper() + testo[1:] + ". Me lo ridici?"


def _contatto_ctx(c: dict) -> dict:
    if not isinstance(c, dict):
        return {"nome": str(c or "")}
    out = {k: v for k, v in c.items() if k not in ("id", "ambito")}
    out["nome"] = nome_di(c)
    via = " ".join(x for x in (c.get("indirizzo"), c.get("civico")) if x)
    luogo = " ".join(x for x in (c.get("cap"), c.get("comune")) if x)
    if c.get("provincia"):
        luogo += f" ({c['provincia']})"
    out["indirizzo_completo"] = ", ".join(x for x in (via, luogo.strip()) if x)
    return out


def _nome_cliente(ctx: dict) -> str:
    for v in ctx.values():
        if isinstance(v, dict) and v.get("indirizzo_completo") is not None and v is not \
                ctx.get("emittente"):
            return v.get("nome", "")
    return ""


def scrittore_locale(writer):
    """I testi lunghi con lo stesso modello della voce (Writer._ask con uno schema minimo)."""
    schema = {"type": "object", "properties": {"testo": {"type": "string"}},
              "required": ["testo"]}

    def scrivi(sistema: str, utente: str) -> str:
        raw = writer._ask([{"role": "system", "content": sistema + " Rispondi in JSON con il "
                            "campo testo."}, {"role": "user", "content": utente}], schema)
        try:
            return str(json.loads(raw).get("testo") or "")
        except (ValueError, AttributeError):
            return ""
    return scrivi


def scrittore_agenti(lavori, ripiego=None):
    """I testi lunghi con lo scrittore degli agenti (qwen3.6 su vLLM sulla DGX, motore
    «openai»). Se la DGX non risponde si usa `ripiego` (lo scrittore locale)."""
    from ..agenti.impostazioni import opzioni_voce

    def scrivi(sistema: str, utente: str) -> str:
        try:
            d = lavori.verifica()
            if d.get("codice") != "ok":
                raise RuntimeError(d.get("motivo") or "agente non raggiungibile")
            imp = lavori.imp
            # Lo stesso modello sullo stesso Ollama della voce: num_ctx e keep_alive della voce
            # (04/10), altrimenti Ollama ricarica il modello con agenti_num_ctx
            voce = {} if getattr(imp, "tunnel", False) else opzioni_voce(
                lavori.cfg, imp.url, imp.modello_scrittore, getattr(imp, "motore", "ollama"))
            body = {"model": imp.modello_scrittore, "messages": [
                        {"role": "system", "content": sistema},
                        {"role": "user", "content": utente}],
                    "options": {"temperature": 0.4, "num_predict": 1500,
                                "num_ctx": _num_ctx_agente(lavori),
                                **voce.get("options", {})},
                    "think": False,
                    **({"keep_alive": voce["keep_alive"]} if "keep_alive" in voce else {})}
            # Stessa GPU della voce: cede il passo al turno dopo (non a quello che l'ha chiesto)
            arb = getattr(lavori, "arbitro", None)
            cliente = lavori.cliente
            if arb is not None and getattr(arb, "condiviso", False):
                from ..agenti.arbitro import ClienteCedevole
                cliente = ClienteCedevole(cliente, arb, dalla_voce=True)
            return cliente.chat(body)["content"]
        except Exception:  # noqa: BLE001
            if ripiego is None:
                raise
            return ripiego(sistema, utente)
    return scrivi


def _num_ctx_agente(lavori) -> int:
    """La finestra dell'agente (05/10: agenti_num_ctx può essere «auto»)."""
    ag = getattr(lavori, "agente", None)
    if ag is not None and hasattr(ag, "num_ctx"):
        return int(ag.num_ctx())
    v = getattr(lavori.cfg, "agenti_num_ctx", 32768)
    return v if isinstance(v, int) and not isinstance(v, bool) else 32768
