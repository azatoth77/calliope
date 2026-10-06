import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco di «scrivere invece di parlare» (03/10, calliope/schermi/moduli.py).

- controlli dei campi con i casi limite: codice fiscale (anche omocodico e di una ditta),
  partita IVA, IBAN (mod 97, lunghezza del paese), CAP, provincia, email, codice
  destinatario, importi all'italiana, date, righe;
- moduli dai tre casi, con il server vero (uvicorn su 127.0.0.1) e un lettore SSE come
  pagina: campi mancanti di modello_compila, contatto nuovo di anagrafica_salva (codice che non
  torna), domanda di un lavoro dell'agente; la voce che offre lo schermo solo se una pagina
  personale è collegata; mai sullo schermo di stanza né nella zona grigia;
- i valori arrivano al tool **senza il modello** (l'estrattore finto non viene chiamato), e
  Calliope li conferma; la risposta a voce chiude il modulo (scheda «hai risposto a voce»);
- il canale pagina → server: sessione nell'intestazione, JSON, dimensione, invii al minuto,
  un'altra persona, uno schermo di stanza, la sessione mancante, il testo scritto in coda;
- permessi: lo scritto vale come il proprietario dello schermo ma al più familiare; per
  installazioni, fatture, schermo personale e codice all'agente si chiede la voce (azione in
  sospeso); la stanza conta come ospite;
- nel registro dei turni e nei log nessun valore sensibile (codici, IBAN, email).

Tutto in una cartella temporanea: non legge calliope.locale.yaml, non tocca memoria.db.
"""

import io
import json
import tempfile
import threading
import time
from pathlib import Path

import httpx

from calliope.brain import Brain
from calliope.config import Config
from calliope.documenti import Documenti
from calliope.documenti.consegna import LocalDelivery
from calliope.schermi import ArchivioSchermi, Schermi
from calliope.schermi import moduli as M
from calliope.schermi.server import ServerSchermi
from calliope.speaker_id import SpeakerContext
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext, serve_la_voce
from calliope.turnlog import TurnLog
from calliope.ufficio.servizio import Ufficio

TMP = Path(tempfile.mkdtemp(prefix="calliope-scritto-"))
errori = 0
# Valori sensibili usati nella prova: alla fine non devono comparire in log e registro
SENSIBILI = ["RSSMRA80A01H501U", "12345678903", "01234567897", "IT60X0542811101000000123456",
             "mario@rossi.it", "BNCLRD85T10F205Z"]


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


def cf_con_controllo(base15: str) -> str:
    """Il carattere di controllo di un codice fiscale (per costruire casi validi)."""
    from calliope.ufficio.rubrica import _CF_DISPARI
    s = sum(_CF_DISPARI[ch] if i % 2 == 0 else (int(ch) if ch.isdigit() else ord(ch) - 65)
            for i, ch in enumerate(base15))
    return base15 + chr(65 + s % 26)


# ─────────────────────────── controlli ───────────────────────────

def prova_controlli():
    c = lambda tipo, v, obbl=True, **k: M.controlla_campo(  # noqa: E731
        {"tipo": tipo, "obbligatorio": obbl, **k}, v)
    casi = [
        ("codice_fiscale", "RSSMRA80A01H501U", "RSSMRA80A01H501U", ""),
        ("codice_fiscale", "rssmra 80a01 h501u", "RSSMRA80A01H501U", ""),
        ("codice_fiscale", "RSSMRA80A01H501V", None, "Il carattere di controllo non torna"),
        ("codice_fiscale", "RSSMRA80A01H501", None, "Servono 16 caratteri (o le 11 cifre di una ditta)"),
        ("codice_fiscale", "01234567897", "01234567897", ""),          # ditta
        ("codice_fiscale", "01234567890", None, "La cifra di controllo non torna"),
        ("partita_iva", "01234567897", "01234567897", ""),
        ("partita_iva", "IT 012 345 678 97", "01234567897", ""),
        ("partita_iva", "12345678903", "12345678903", ""),
        ("partita_iva", "12345678904", None, "La cifra di controllo non torna"),
        ("partita_iva", "00000000000", None, "La cifra di controllo non torna"),
        ("partita_iva", "1234567890", None, "Servono 11 cifre"),
        ("iban", "IT60 X054 2811 1010 0000 0123 456", "IT60X0542811101000000123456", ""),
        ("iban", "it60x0542811101000000123456", "IT60X0542811101000000123456", ""),
        ("iban", "IT61X0542811101000000123456", None, "Il codice di controllo non torna"),
        ("iban", "IT60X054281110100000012345", None, "Un IBAN IT ha 27 caratteri (qui 26)"),
        ("iban", "GB82WEST12345698765432", "GB82WEST12345698765432", ""),
        ("iban", "12345", None, "Un IBAN comincia con il paese (IT) e due cifre"),
        ("cap", "20121", "20121", ""), ("cap", "2012", None, "Il CAP ha 5 cifre"),
        ("provincia", "mi", "MI", ""), ("provincia", "Milano", "MI", ""),
        ("provincia", "Mil", None, "La sigla ha 2 lettere"),
        ("email", "Mario@Rossi.it", "mario@rossi.it", ""),
        ("email", "mario@rossi", None, "Indirizzo email non valido"),
        ("codice_destinatario", "kr78r9e", "KR78R9E", ""),
        ("codice_destinatario", "ABC", None, "Il codice destinatario ha 7 caratteri"),
        ("importo", "1.234,56", 1234.56, ""), ("importo", "1234,5", 1234.5, ""),
        ("importo", "€ 50", 50, ""), ("importo", "12,345", None, "Al massimo due decimali"),
        ("importo", "-3", None, "L'importo non può essere negativo"),
        ("importo", "dieci", None, "Scrivi un importo, per esempio 1.234,50"),
        ("data", "2026-10-03", "2026-10-03", ""), ("data", "3/10/2026", "2026-10-03", ""),
        ("data", "31/02/2026", None, "Data non valida"),
        ("testo", "", None, "Manca"), ("testo", "x" * 201, None, "Al massimo 200 caratteri"),
        ("booleano", "sì", True, ""), ("booleano", False, False, ""),
    ]
    for tipo, v, atteso, err in casi:
        got = c(tipo, v)
        verifica(f"{tipo} «{v if len(str(v)) < 30 else str(v)[:27] + '…'}»",
                 got == (atteso, err), str(got))
    # Omocodia: 2 cifre sostituite da lettere (L=0, M=1…), con il controllo rifatto
    omo = cf_con_controllo("RSSMRA80A01H5LM")
    verifica("codice fiscale omocodico valido", c("codice_fiscale", omo) == (omo, ""), omo)
    verifica("facoltativo vuoto: niente errore", c("email", "", obbl=False) == (None, ""))
    verifica("scelta fuori elenco", c("scelta", "Verdi", opzioni=["Rossi"])[1] == "Scegli una voce")
    righe, e = c("righe", [{"descrizione": "Consulenza", "quantita": "2", "prezzo": "500"},
                           {"descrizione": "", "quantita": "", "prezzo": ""}])
    verifica("righe: valori in numeri, riga vuota saltata", e == "" and righe == [
        {"descrizione": "Consulenza", "quantita": 2, "prezzo": 500, "aliquota": None}], str(righe))
    verifica("righe: prezzo mancante", c("righe", [{"descrizione": "x", "quantita": "1"}])[1]
             == "Riga 1: manca il prezzo")
    verifica("righe senza prezzi (DDT): quantità obbligatoria",
             c("righe", [{"descrizione": "x"}], prezzi=False)[1] == "Riga 1: manca la quantità")
    # Oscuramento per log e registro
    t = ("cf RSSMRA80A01H501U, piva 1 2 3 4 5 6 7 8 9 0 3, iban IT60 X054 2811 1010 0000 0123 "
         "456, mail mario@rossi.it, alle 10:30 del 3 ottobre, 500 euro")
    o = M.oscura(t)
    verifica("oscura: codici, IBAN ed email via", not any(s in o.replace(" ", "")
                                                          for s in SENSIBILI) and
             "mario@" not in o, o)
    verifica("oscura: ore, date e importi restano", "10:30" in o and "3 ottobre" in o
             and "500 euro" in o, o)
    # Domanda con lo schermo: il pronome della domanda resta (04/10: «Me le dici?» e
    # «Me la dici?» dei modelli con un dato solo cadevano sulla frase generica)
    for frase, attesa in (
            ("Mi servono le firme. Me le dici?", "Me le dici, o le scrivi sullo schermo?"),
            ("Mi serve la data. Me la dici?", "Me la dici, o la scrivi sullo schermo?"),
            ("Mi servono: a e b. Me li dici?", "Me li dici, o li scrivi sullo schermo?"),
            ("Non ho capito la data «x»: me la ridici?",
             "me la ridici, o la scrivi sullo schermo?"),
            ("Me lo ridici?", "Me lo ridici, o lo scrivi sullo schermo?"),
            ("Va bene?", "Va bene, o puoi scriverlo sullo schermo?"),
            ("Insomme li dici?", "Insomme li dici, o puoi scriverlo sullo schermo?")):
        verifica(f"domanda_schermo: {frase}", M.domanda_schermo(frase).endswith(attesa),
                 M.domanda_schermo(frase))


# ─────────────────────────── ambiente ───────────────────────────

class Prof:
    def __init__(self, pid, name, admin=False):
        self.id, self.name, self.admin = pid, name, admin
        self.preferred_voice = None


class Speakers:
    def __init__(self):
        self.users = {"Dario": Prof("dario-id", "Dario", True), "Bianca": Prof("bianca-id", "Bianca")}

    def get(self, n):
        return self.users.get(n)

    def by_id(self, pid):
        return next((u for u in self.users.values() if u.id == pid), None)

    def known_speakers(self):
        return list(self.users)


class Estrattore:
    def __init__(self):
        self.code, self.chiamate = [], 0

    def __call__(self, messages, schema):
        self.chiamate += 1
        return json.dumps(self.code.pop(0) if self.code else {})


EMITTENTE = {"denominazione": "Esempio Srl", "partita_iva": "01234567897",
             "codice_fiscale": "01234567897", "regime_fiscale": "RF01", "indirizzo": "Via Roma",
             "civico": "3", "cap": "20121", "comune": "Milano", "provincia": "MI",
             "iban": "IT60 X054 2811 1010 0000 0123 456", "giorni_pagamento": "30"}
ROSSI = {"tipo": "cliente", "denominazione": "Rossi & Figli S.r.l.",
         "partita_iva": "12345678903", "indirizzo": "Via Verdi", "civico": "5", "cap": "00184",
         "comune": "Roma", "provincia": "RM"}


def cfg_prova(**kw) -> Config:
    c = Config()
    c.memory_db = str(TMP / "memoria.db")
    c.casa_url = None
    c.config_dir = str(TMP)
    c.documenti_attesa_s = 5.0
    c.fatture_emittente = dict(EMITTENTE)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


class LettoreSSE:
    """La pagina di uno schermo, ridotta: riceve le schede."""

    def __init__(self, base, sessione):
        self.eventi = []
        threading.Thread(target=self._run, args=(base, sessione), daemon=True).start()

    def _run(self, base, sessione):
        ev = None
        try:
            with httpx.stream("GET", f"{base}/eventi?sessione={sessione}", timeout=60) as r:
                for line in r.iter_lines():
                    if line.startswith("event: "):
                        ev = line[7:]
                    elif line.startswith("data: "):
                        self.eventi.append((ev, json.loads(line[6:])))
        except Exception:  # noqa: BLE001
            pass

    def moduli(self):
        return [d for e, d in self.eventi if e == "scheda" and d.get("tipo") == "modulo"]

    def attendi(self, cond, max_s=3.0):
        t0 = time.monotonic()
        while time.monotonic() - t0 < max_s:
            if cond():
                return True
            time.sleep(0.01)
        return False


def nuovo_schermo(c, hub, stanza, owner=None, owner_name=None):
    r = c.post("/api/abbinamento").json()
    res = hub.abbina(r["codice"], stanza, owner, owner_name)
    assert res["ok"], res
    a = c.post("/api/accedi", headers={"Authorization": f"Bearer {r['richiesta']}"}).json()
    return a


class Ambiente:
    def __init__(self, nome, **cfgkw):
        self.cfg = cfg_prova(**cfgkw)
        self.cfg.memory_db = str(TMP / f"{nome}.db")
        self.hub = Schermi(self.cfg, ArchivioSchermi(self.cfg.memory_db))
        self.srv = ServerSchermi(self.hub, "127.0.0.1", 0).avvia()
        self.base = f"http://127.0.0.1:{self.srv.port}"
        self.c = httpx.Client(base_url=self.base, timeout=5)
        self.speakers = Speakers()
        docs = Documenti(self.cfg, self.cfg.memory_db, writer=object(),
                         delivery=LocalDelivery(TMP / nome), formats=("word", "excel", "pdf"))
        self.est = Estrattore()
        import datetime
        self.u = Ufficio(self.cfg, self.cfg.memory_db, docs, estrai=self.est,
                         scrittore=lambda s, u: "testo", oggi=lambda: datetime.date(2026, 10, 2))
        self.u.rubrica.aggiungi(ROSSI, "casa", "dario-id")
        self.reg = build_registry(documenti=("word", "excel", "pdf"),
                                  ufficio=self.u.nomi_modelli(), schermi=True, installa=True)
        self.sc = SpeakerContext(self.speakers)
        self.ctx = ToolContext(cfg=self.cfg, speakers=self.speakers, speaker_ctx=self.sc,
                               speaker=None, documenti=docs, ufficio=self.u, schermi=self.hub)
        self.brain = Brain(self.cfg, self.reg, self.ctx)

    def parla(self, chi, how="voce", from_session=False, stanza=None):
        self.sc.current_speaker = chi
        self.sc.identified_by = how if chi else None
        self.sc.from_session = from_session
        # Come main.py: una frase detta apre (o chiude) la conversazione per lo scritto (05/10)
        if how != "schermo":
            prof = self.speakers.get(chi) if chi else None
            self.hub.conversazioni.voce(getattr(prof, "id", None), how if chi else None,
                                        stanza=stanza)

    def chiama(self, nome, args, turno=1, frase=""):
        self.ctx.turno, self.ctx.user_text = turno, frase
        self.ctx.regole.clear()
        out = json.loads(self.reg.call(nome, args, self.ctx, self.sc.current_level))
        out["_regole"] = list(self.ctx.regole)
        return out

    def invia(self, sess, path, dati, **kw):
        h = {"X-Calliope-Sessione": sess, **kw.pop("headers", {})}
        return self.c.post(path, headers=h, json=dati, **kw)

    def chiudi(self):
        self.srv.ferma()
        self.hub.archivio.close()


# ─────────────────────────── moduli dai tool ───────────────────────────

def prova_modello():
    a = Ambiente("modello")
    try:
        studio = nuovo_schermo(a.c, a.hub, "studio", "dario-id", "Dario")
        sogg = nuovo_schermo(a.c, a.hub, "soggiorno")
        pag = LettoreSSE(a.base, studio["sessione"])
        pag_sogg = LettoreSSE(a.base, sogg["sessione"])
        a_bianca = nuovo_schermo(a.c, a.hub, "camera", "bianca-id", "Bianca")
        time.sleep(0.3)
        # Dario chiede una fattura a voce senza dati: domanda + modulo sullo schermo
        a.parla("Dario")
        a.est.code.append({"cliente": None, "righe": None})
        r = a.chiama("modello_compila", {"modello": "fattura", "dati": "fammi una fattura"})
        verifica("domanda con lo schermo: «o li scrivi sullo schermo?»",
                 r["risposta_finale"].endswith("Me li dici, o li scrivi sullo schermo?")
                 and "modulo_sullo_schermo" in r["_regole"], r["risposta_finale"])
        verifica("la specifica del modulo non va al modello", "modulo" not in r)
        verifica("azione in sospeso resta (risposta a voce possibile)",
                 r.get("in_sospeso", {}).get("tool") == "modello_compila")
        pag.attendi(lambda: pag.moduli())
        m = pag.moduli()[-1] if pag.moduli() else {}
        tipi = {x["nome"]: x["tipo"] for x in m.get("campi", [])}
        verifica("modulo sullo schermo personale: cliente (con la rubrica) e righe",
                 tipi == {"cliente": "testo", "righe": "righe"}
                 and "Rossi & Figli S.r.l." in m["campi"][0].get("suggerimenti", [])
                 and m.get("visibilita") == "personale", str(m.get("campi")))
        verifica("mai sullo schermo del soggiorno", not pag_sogg.moduli())
        # Canale: errori
        corpo = {"modulo": m["id_modulo"] if "id_modulo" in m else m.get("modulo"),
                 "valori": {"cliente": "Rossi & Figli S.r.l.",
                            "righe": [{"descrizione": "Consulenza", "quantita": "2",
                                       "prezzo": "500,00"}]}}
        verifica("senza sessione: 401", a.c.post("/api/modulo", json=corpo).status_code == 401)
        verifica("sessione sbagliata: 401",
                 a.invia("x" * 24, "/api/modulo", corpo).status_code == 401)
        verifica("schermo del soggiorno: rifiutato",
                 a.invia(sogg["sessione"], "/api/modulo", corpo).status_code == 403)
        rv = a.invia(a_bianca["sessione"], "/api/modulo", corpo)
        verifica("schermo personale di un'altra persona: rifiutato (Bianca non sta parlando)",
                 rv.status_code == 403 and rv.json().get("codice") == "senza_conversazione",
                 rv.text)
        r415 = a.c.post("/api/modulo", headers={"X-Calliope-Sessione": studio["sessione"],
                                                "Content-Type": "text/plain"},
                        content=json.dumps(corpo))
        verifica("niente JSON (un form HTML di un altro sito): 415", r415.status_code == 415)
        grande = dict(corpo, valori=dict(corpo["valori"], cliente="x" * 40000))
        verifica("corpo troppo grande: 413",
                 a.invia(studio["sessione"], "/api/modulo", grande).status_code == 413)
        sbagliato = {"modulo": corpo["modulo"], "valori": {"cliente": "Rossi",
                                                           "righe": [{"descrizione": "x"}]}}
        r422 = a.invia(studio["sessione"], "/api/modulo", sbagliato)
        verifica("riga senza prezzo: 422 con l'errore sul campo", r422.status_code == 422
                 and r422.json()["errori"] == {"righe": "Riga 1: manca il prezzo"}, r422.text)
        verifica("niente in coda dopo gli errori", a.hub.ingresso.vuoto())
        # Invio giusto: in coda, poi il ciclo principale lo passa al tool
        chiamate = a.est.chiamate
        ok = a.invia(studio["sessione"], "/api/modulo", corpo)
        verifica("invio giusto: 200", ok.status_code == 200, ok.text)
        item = a.hub.ingresso.prendi()
        verifica("in coda per il ciclo principale", item and item["tipo"] == "modulo")
        a.brain.turn_number = 4
        out = M.completa(a.hub, item, a.brain, a.brain.turn_number)
        verifica("valori al tool senza il modello (nessuna estrazione)",
                 a.est.chiamate == chiamate)
        verifica("Calliope conferma e propone la fattura",
                 out["frase"].startswith("Grazie, ho i dati. La fattura numero 1 del 2026 a "
                                         "Rossi & Figli") and out["frase"].endswith(
                     "La preparo?"), out["frase"])
        verifica("registro: solo i nomi dei campi", out["rec"]["campi"] == ["cliente", "righe"]
                 and "Consulenza" not in json.dumps(out["rec"]), str(out["rec"]))
        hist = json.dumps(a.brain.history, ensure_ascii=False)
        verifica("storia del modello: «ho scritto i dati», senza i valori",
                 "Ho scritto sullo schermo i dati" in hist and "Consulenza" not in hist
                 and "500" not in hist.split("La fattura")[0], hist[:200])
        verifica("la proposta diventa l'azione in sospeso", a.brain.has_pending())
        pag.attendi(lambda: any(x.get("stato") == "inviato" for x in pag.moduli()))
        verifica("la scheda del modulo diventa «inviato»",
                 any(x.get("stato") == "inviato" and not x.get("campi") for x in pag.moduli()))
        verifica("modulo inviato non si rimanda", a.invia(studio["sessione"], "/api/modulo",
                                                          corpo).status_code == 409)
        oid = a.u.offerte["dario-id"]["id"]
        r = a.chiama("modello_compila", {"modello": "fattura", "dati": "sì", "proposta": oid},
                     turno=5)
        verifica("«sì» a voce nel turno dopo: fattura emessa", r.get("ok") and r.get("numero")
                 == 1, r.get("risposta_finale"))

        # Risposta a voce prima del modulo: il modulo si chiude
        a.est.code.append({"cliente": None, "righe": None})
        a.chiama("modello_compila", {"modello": "preventivo", "dati": "un preventivo"}, turno=7)
        verifica("preventivo: modulo aperto", len(a.hub.moduli.aperti("dario-id")) == 1)
        a.est.code.append({"cliente": "Rossi e figli", "oggetto": "Sito", "righe": [
            {"descrizione": "Sito", "quantita": None, "prezzo": 900, "aliquota": None}]})
        r = a.chiama("modello_compila", {"modello": "preventivo", "dati": "a Rossi, sito, 900"},
                     turno=8)
        verifica("risposta a voce: il modulo si chiude", not a.hub.moduli.aperti("dario-id")
                 and r["risposta_finale"].endswith("Lo preparo?"), r["risposta_finale"])
        pag.attendi(lambda: any(x.get("nota") == "Hai risposto a voce." for x in pag.moduli()))
        verifica("la pagina mostra «hai risposto a voce»",
                 any(x.get("nota") == "Hai risposto a voce." for x in pag.moduli()))

        # Zona grigia: niente modulo; ospite: niente
        a.parla("Dario", how="conversazione", from_session=True)
        a.est.code.append({"cliente": None, "righe": None})
        r = a.chiama("modello_compila", {"modello": "preventivo", "dati": "x"}, turno=9)
        verifica("zona grigia: nessun modulo, frase di sempre",
                 "schermo" not in r["risposta_finale"] and not a.hub.moduli.aperti("dario-id"),
                 r["risposta_finale"])
        # Senza pagina collegata: la voce non nomina lo schermo
        b = Ambiente("senza_pagina")
        try:
            nuovo_schermo(b.c, b.hub, "studio", "dario-id", "Dario")
            b.parla("Dario")
            b.est.code.append({"cliente": None, "righe": None})
            r = b.chiama("modello_compila", {"modello": "fattura", "dati": "fattura"})
            verifica("schermo personale spento: la voce non offre lo schermo",
                     r["risposta_finale"].endswith("Me li dici?"), r["risposta_finale"])
        finally:
            b.chiudi()
    finally:
        a.chiudi()


def prova_rubrica():
    a = Ambiente("rubrica")
    try:
        studio = nuovo_schermo(a.c, a.hub, "studio", "dario-id", "Dario")
        pag = LettoreSSE(a.base, studio["sessione"])
        time.sleep(0.3)
        a.parla("Dario")
        # Partita IVA storpiata da Whisper: errore detto, modulo con il valore da correggere
        a.est.code.append({"tipo": "cliente", "denominazione": "Bianchi Srl",
                           "partita_iva": "12345678904", "cap": "20100", "comune": "Milano"})
        r = a.chiama("anagrafica_salva", {"azione": "aggiungi", "nome": "Bianchi Srl",
                                          "dati": "partita iva 12345678904"})
        verifica("codice che non torna: «o lo scrivi sullo schermo?»",
                 "non torna" in r["risposta_finale"] and r["risposta_finale"].endswith(
                     "o lo scrivi sullo schermo?"), r["risposta_finale"])
        pag.attendi(lambda: pag.moduli())
        m = pag.moduli()[-1]
        piva = next(x for x in m["campi"] if x["nome"] == "partita_iva")
        verifica("modulo del contatto: la partita IVA detta, con l'errore",
                 piva.get("valore") == "12345678904" and "non torna" in piva.get("errore", ""),
                 str(piva))
        valori = {"tipo": "cliente", "denominazione": "Bianchi Srl", "partita_iva": "1234567890 4",
                  "codice_fiscale": "RSSMRA80A01H501V", "cap": "20100", "comune": "Milano",
                  "provincia": "Milano", "email": "mario@rossi.it"}
        r422 = a.invia(studio["sessione"], "/api/modulo", {"modulo": m["modulo"],
                                                           "valori": valori})
        err = r422.json().get("errori", {})
        verifica("server: partita IVA e codice fiscale sbagliati, 422",
                 r422.status_code == 422 and set(err) == {"partita_iva", "codice_fiscale"},
                 r422.text)
        valori.update(partita_iva="01234567897", codice_fiscale="RSSMRA80A01H501U")
        r = a.invia(studio["sessione"], "/api/modulo", {"modulo": m["modulo"], "valori": valori})
        verifica("valori corretti: 200", r.status_code == 200, r.text)
        out = M.completa(a.hub, a.hub.ingresso.prendi(), a.brain, 3)
        c = a.u.rubrica.trova("Bianchi", "dario-id")[0]
        verifica("contatto in rubrica con i valori esatti scritti", c and c["partita_iva"]
                 == "01234567897" and c["codice_fiscale"] == "RSSMRA80A01H501U"
                 and c["provincia"] == "MI" and c["email"] == "mario@rossi.it", str(c))
        verifica("conferma a voce senza i codici", out["frase"].startswith(
            "Grazie, ho aggiunto Bianchi Srl alla rubrica") and "123" not in out["frase"],
            out["frase"])
        # Registro dei turni: niente valori
        log = TurnLog(str(TMP / "registro"), 30)
        log.write({"inizio": "2026-10-03T10:00:00", **out["rec"], "risposta": M.oscura(out["frase"])})
        testo = "".join(p.read_text(encoding="utf-8") for p in (TMP / "registro").glob("*"))
        verifica("registro dei turni: nessun valore sensibile",
                 not any(s in testo for s in SENSIBILI) and "partita_iva" in testo, testo[:200])
    finally:
        a.chiudi()


class Lav:
    def __init__(self):
        self.id, self.titolo, self.domanda = "L3", "la relazione", "Chi è il cliente?"


class LavoriFinti:
    def __init__(self):
        self.lav = Lav()
        self.risposte = []

    def in_attesa(self, persona=None):
        return [self.lav]

    def rispondi(self, lav, risposta):
        self.risposte.append((lav.id, risposta))
        return f"Grazie, lo dico all'agente: riprendo «{lav.titolo}» in secondo piano."


def prova_lavoro():
    a = Ambiente("lavoro")
    try:
        studio = nuovo_schermo(a.c, a.hub, "studio", "dario-id", "Dario")
        pag = LettoreSSE(a.base, studio["sessione"])
        time.sleep(0.3)
        lavori = LavoriFinti()
        item = {"id": "L3", "messaggio": "Dario, per «la relazione» ho una domanda: chi è il "
                                         "cliente?", "chi": "dario-id", "chi_nome": "Dario",
                "in_sospeso": {"tool": "lavori_rispondi", "domanda": "Chi è il cliente?",
                               "argomenti": {"lavoro": "L3"}, "messaggio": "Domanda in sospeso"},
                "modulo": {"chiave": "lavoro:L3", "titolo": "Domanda: la relazione",
                           "domanda": "Chi è il cliente?",
                           "campi": [M.campo("risposta", "La tua risposta", "testo_lungo")]}}
        # L'annuncio arriva a conversazione chiusa (05/10): il modulo c'è, ma per scriverci
        # bisogna prima chiamarla
        msg = M.annuncio_lavoro(a.hub, dict(item), lavori, a.brain)
        verifica("domanda dell'agente senza conversazione: «chiamarmi e scrivere»", msg.endswith(
            "oppure chiamarmi e scrivere la risposta sullo schermo."), msg)
        pag.attendi(lambda: pag.moduli())
        m = pag.moduli()[-1]
        r0 = a.invia(studio["sessione"], "/api/modulo", {"modulo": m["modulo"], "valori": {
            "risposta": "Rossi & Figli, via Verdi 5"}})
        verifica("modulo inviato senza conversazione: 403, niente in coda",
                 r0.status_code == 403 and r0.json().get("codice") == "senza_conversazione"
                 and a.hub.ingresso.vuoto(), r0.text)
        a.parla("Dario")                       # «Calliope» detto da Dario
        msg = M.annuncio_lavoro(a.hub, item, lavori, a.brain)
        verifica("domanda dell'agente in conversazione: offre lo schermo", msg.endswith(
            "Puoi rispondermi a voce o scrivere la risposta sullo schermo."), msg)
        verifica("la domanda resta un'azione in sospeso", a.brain.has_pending())
        pag.attendi(lambda: len(pag.moduli()) >= 2)
        m = pag.moduli()[-1]
        r = a.invia(studio["sessione"], "/api/modulo", {"modulo": m["modulo"], "valori": {
            "risposta": "Rossi & Figli, via Verdi 5"}})
        verifica("risposta scritta: 200", r.status_code == 200, r.text)
        out = M.completa(a.hub, a.hub.ingresso.prendi(), a.brain, 2)
        verifica("la risposta esatta arriva al lavoro", lavori.risposte == [
            ("L3", "Rossi & Figli, via Verdi 5")], str(lavori.risposte))
        verifica("conferma a voce e domanda chiusa", out["frase"].startswith("Grazie, lo dico")
                 and not a.brain.has_pending(), out["frase"])
    finally:
        a.chiudi()


# ─────────────────────────── testo scritto ───────────────────────────

def prova_casella():
    a = Ambiente("casella", schermi_scritto_al_minuto=5)
    try:
        studio = nuovo_schermo(a.c, a.hub, "studio", "dario-id", "Dario")
        sogg = nuovo_schermo(a.c, a.hub, "soggiorno")
        verifica("accesso: la casella c'è sullo schermo personale",
                 studio.get("scrivi") is True and sogg.get("scrivi") is False)
        # Senza conversazione a voce (05/10): rifiutato, niente al ciclo, regola nel registro
        registro = []
        a.hub.registro_turni = registro.append
        verifica("accesso senza conversazione: scrittura spenta, con la frase",
                 studio.get("scrittura", {}).get("attiva") is False
                 and "Calliope" in studio["scrittura"].get("testo", ""), str(studio))
        r = a.invia(studio["sessione"], "/api/scrivi", {"testo": "che ore sono?"})
        verifica("scritto senza conversazione: 403 senza_conversazione, niente in coda",
                 r.status_code == 403 and r.json().get("codice") == "senza_conversazione"
                 and a.hub.ingresso.vuoto(), r.text)
        verifica("registro dei turni: regola scritto_senza_conversazione, senza il testo",
                 registro and registro[-1]["regole"] == ["scritto_senza_conversazione"]
                 and "ore" not in json.dumps(registro), str(registro))
        a.parla("Dario")
        r = a.invia(studio["sessione"], "/api/scrivi", {"testo": "  il codice\x07 è\nRSS  "})
        item = a.hub.ingresso.prendi()
        verifica("testo scritto in coda, con la persona dello schermo",
                 r.status_code == 200 and item["tipo"] == "scritto"
                 and item["persona"] == "dario-id" and item["testo"] == "il codice è RSS",
                 str(item))
        verifica("schermo di stanza (predefinito): 403",
                 a.invia(sogg["sessione"], "/api/scrivi", {"testo": "ciao"}).status_code == 403)
        verifica("testo troppo lungo: 413", a.invia(studio["sessione"], "/api/scrivi", {
            "testo": "x" * 600}).status_code == 413)
        verifica("testo vuoto: 400", a.invia(studio["sessione"], "/api/scrivi",
                                             {"testo": "   "}).status_code == 400)
        codici = [a.invia(studio["sessione"], "/api/scrivi", {"testo": f"ciao {i}"}).status_code
                  for i in range(4)]
        verifica("limite di invii al minuto: 429", codici[-1] == 429 and 200 in codici, str(codici))
        while a.hub.ingresso.prendi():
            pass
        sveglie = []
        a.hub.ingresso.sveglia = lambda: sveglie.append(1)
        a.hub.ingresso.metti({"tipo": "scritto", "testo": "x"})
        verifica("la coda sveglia il ciclo principale", sveglie == [1])
    finally:
        a.chiudi()
    b = Ambiente("casella_stanza", schermi_scritto_stanza=True)
    try:
        sogg = nuovo_schermo(b.c, b.hub, "soggiorno")
        b.parla(None, stanza="cucina")         # una conversazione, ma in un'altra stanza
        r = b.invia(sogg["sessione"], "/api/scrivi", {"testo": "che ore sono?"})
        verifica("schermo di stanza, conversazione in un'altra stanza: 403",
                 r.status_code == 403 and r.json().get("motivo") == "altra_stanza", r.text)
        b.parla(None, stanza="soggiorno")      # un ospite parla nel soggiorno
        r = b.invia(sogg["sessione"], "/api/scrivi", {"testo": "che ore sono?"})
        item = b.hub.ingresso.prendi()
        verifica("schermo di stanza ammesso: vale come ospite", r.status_code == 200
                 and r.json()["come"] == "ospite" and item["persona"] is None, r.text)
    finally:
        b.chiudi()
    c = Ambiente("casella_spenta", schermi_scritto=False)
    try:
        studio = nuovo_schermo(c.c, c.hub, "studio", "dario-id", "Dario")
        verifica("scrittura spenta: niente casella, 403", studio.get("scrivi") is False
                 and c.invia(studio["sessione"], "/api/scrivi", {"testo": "x"}).status_code
                 == 403)
    finally:
        c.chiudi()
    # In rete senza HTTPS: rifiutato (si prova se il PC ha un indirizzo in rete)
    from calliope.schermi import ip_lan
    ip = ip_lan()
    if ip:
        d = Ambiente("casella_rete", schermi_senza_tls=True)
        try:
            d.srv.ferma()
            d.srv = ServerSchermi(d.hub, "0.0.0.0", 0).avvia()
            cl = httpx.Client(base_url=f"http://{ip}:{d.srv.port}", timeout=5)
            studio = nuovo_schermo(cl, d.hub, "studio", "dario-id", "Dario")
            d.parla("Dario")
            r = cl.post("/api/scrivi", headers={"X-Calliope-Sessione": studio["sessione"]},
                        json={"testo": "x"})
            verifica("in rete senza HTTPS: 403", r.status_code == 403
                     and "HTTPS" in r.json().get("errore", ""), r.text)
        finally:
            d.chiudi()
    else:
        print("SALTATA IN PARTE: nessun indirizzo in rete: il caso «senza HTTPS» si salta")


# ─────────────────────────── permessi ───────────────────────────

def prova_permessi():
    a = Ambiente("permessi")
    try:
        sc = a.sc
        a.ctx.installazioni = object()     # solo per arrivare al controllo dei permessi
        a.parla("Dario", how="schermo")
        verifica("scritto da chi amministra: al più familiare",
                 sc.current_level == "familiare" and sc.profile_level == "amministra")
        r = a.chiama("installa_avvia", {"azione": "vikidia"})
        verifica("installazione scritta: chiede la voce (azione in sospeso)",
                 r.get("ok") is False and "mi serve la tua voce" in r["risposta_finale"]
                 and r["in_sospeso"]["tool"] == "installa_avvia"
                 and "scritto_serve_voce" in r["_regole"], r.get("risposta_finale"))
        r = a.chiama("installa_proponi", {"azione": "vikidia"})
        verifica("proposta d'installazione scritta: chiede la voce",
                 r["risposta_finale"].endswith("con una frase intera?")
                 and r["in_sospeso"]["argomenti"] == {"azione": "vikidia"}, r["risposta_finale"])
        r = a.chiama("schermo_gestisci", {"azione": "personale", "stanza": "studio"})
        verifica("schermo personale scritto: chiede la voce",
                 "mi serve la tua voce" in r.get("risposta_finale", ""), r.get("risposta_finale"))
        n0 = a.est.chiamate
        r = a.chiama("modello_compila", {"modello": "fattura", "dati": "fattura a Rossi"})
        verifica("fattura scritta: chiede la voce, niente estrazione",
                 "preparare una fattura" in r["risposta_finale"] and a.est.chiamate == n0,
                 r["risposta_finale"])
        a.est.code.append({"cliente": "Rossi e figli", "oggetto": "Sito", "righe": [
            {"descrizione": "Sito", "quantita": None, "prezzo": 900, "aliquota": None}]})
        r = a.chiama("modello_compila", {"modello": "preventivo", "dati": "preventivo a Rossi"})
        verifica("preventivo scritto (livello familiare): passa",
                 r["risposta_finale"].endswith("Lo preparo?"), r["risposta_finale"])
        a.parla("Bianca", how="schermo")
        r = a.chiama("installa_avvia", {"azione": "vikidia"})
        verifica("familiare che scrive: il rifiuto di sempre, nessuna conferma a voce",
                 "in_sospeso" not in r and "solo chi amministra" in r["risposta_finale"],
                 r["risposta_finale"])
        a.parla(None)
        r = a.chiama("modello_compila", {"modello": "preventivo", "dati": "x"})
        verifica("schermo di stanza (ospite): rifiutato", r.get("ok") is False
                 and "in_sospeso" not in r)
        a.parla("Dario", how="voce")
        verifica("a voce, chi amministra: amministra", sc.current_level == "amministra"
                 and serve_la_voce(a.ctx, "x", {}, "y") is None)
        r = a.chiama("installa_avvia", {"azione": "vikidia"})
        verifica("a voce: niente richiesta di voce", "mi serve la tua voce" not in
                 r.get("risposta_finale", ""), r.get("risposta_finale"))
    finally:
        a.chiudi()


def prova_log(cattura: str):
    trovati = [s for s in SENSIBILI if s in cattura]
    # I valori sbagliati scritti (12345678904, …V) sono stati mandati dalla prova stessa; quelli
    # giusti non devono mai comparire in quello che il processo ha stampato
    verifica("log: nessun codice fiscale, partita IVA, IBAN o email in chiaro", not trovati,
             str(trovati))


if __name__ == "__main__":
    reale = sys.stdout
    buf = io.StringIO()

    class Doppio(io.TextIOBase):
        def write(self, s):
            buf.write(s)
            return reale.write(s)

        def flush(self):
            reale.flush()
    prova_controlli()
    sys.stdout = Doppio()
    try:
        prova_modello()
        prova_rubrica()
        prova_lavoro()
        prova_casella()
        prova_permessi()
    finally:
        sys.stdout = reale
    # Le righe «ok»/«ERR» della prova contengono i valori di proposito: si guarda il resto
    prova_log("\n".join(r for r in buf.getvalue().splitlines()
                        if not r.startswith(("ok ", "ERR"))))
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
    sys.exit(1 if errori else 0)
