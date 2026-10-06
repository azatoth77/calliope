"""
Il file XML della fattura elettronica (FatturaPA, formato FPR12 per privati e aziende).

Versione: schema 1.2.3 delle «Specifiche tecniche del formato FatturaPA» 1.4, in vigore
dal 1° aprile 2025 (www.fatturapa.gov.it, verificato il 02/10/2026). Calliope **non
trasmette** allo SdI (principio 9): prepara il file da caricare a mano (portale «Fatture e
Corrispettivi» dell'Agenzia delle Entrate o il proprio intermediario). Niente firma né
conservazione: per FPR12 la firma non è obbligatoria.

- L'XML si costruisce con la libreria standard (xml.etree): nessuna dipendenza in più.
- La validazione contro l'XSD ufficiale usa lxml (c'è già con python-docx) e i due file
  dello schema in una cartella locale (`fatture_xsd`): Schema_VFPR12_v1.2.3.xsd e
  xmldsig-core-schema.xsd del W3C, che lo schema importa da internet. Non sono nel
  repository (lo schema non dichiara una licenza): `python -m calliope.ufficio
  --scarica-xsd` li scarica una volta e ne controlla lo SHA-256. Senza, restano i controlli
  di questo modulo (`controlla`), che coprono i vincoli di forma usati qui.
- I testi vanno in Latin-1 (i tipo String…LatinType dello schema): «€» diventa «EUR», le
  virgolette tipografiche quelle semplici; i campi «BasicLatin» (numero, codici) solo ASCII.
"""

import datetime
import hashlib
import re
import unicodedata
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

from .conti import r2, xml_num

NS = "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
VERSIONE_SCHEMA = "1.2.3"
XSD = {
    "Schema_VFPR12_v1.2.3.xsd": (
        "https://www.fatturapa.gov.it/export/documenti/fatturapa/v1.4/Schema_VFPR12_v1.2.3.xsd",
        "152944f6eef9f5d69ef6e955ee173b32142b00a8c1c5222fc97dfab5910e8a8c"),
    "xmldsig-core-schema.xsd": (
        "https://www.w3.org/TR/2002/REC-xmldsig-core-20020212/xmldsig-core-schema.xsd",
        "35cf8197da812c85e40d57891b35c94187569ed474a2dac813ce5090dafcd35c"),
}
_DSIG_URL = "http://www.w3.org/TR/2002/REC-xmldsig-core-20020212/xmldsig-core-schema.xsd"

REGIMI = ("RF01", "RF02", "RF04", "RF05", "RF06", "RF07", "RF08", "RF09", "RF10", "RF11",
          "RF12", "RF13", "RF14", "RF15", "RF16", "RF17", "RF18", "RF19", "RF20")
TIPI_DOCUMENTO = {"fattura": "TD01", "nota_di_credito": "TD04", "parcella": "TD06"}
_SERIE_CODICE = {"fatture": 0, "note_credito": 1}

_LATIN1 = {"€": "EUR", "“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "–": "-",
           "—": "-", "…": "...", "•": "-", " ": " ", " ": " ", "\t": " "}


def latino(testo, limite: int, base: bool = False) -> str:
    """Il testo nei caratteri ammessi (Latin-1, o solo ASCII se `base`), senza a capo e
    tagliato a `limite`."""
    s = str(testo or "")
    for a, b in _LATIN1.items():
        s = s.replace(a, b)
    s = re.sub(r"\s+", " ", s).strip()
    out = []
    for ch in s:
        if (ord(ch) < 128) or (not base and ord(ch) < 256 and ch.isprintable()):
            out.append(ch)
        else:
            d = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode()
            out.append(d or "?")
    return "".join(out)[:limite].strip()


def progressivo(serie: str, numero: int, anno: int) -> str:
    """5 caratteri alfanumerici, unici per trasmittente: anno, serie e numero in base 36.
    Servono sia al nome del file sia a ProgressivoInvio."""
    n = (anno % 100) * 100000 + _SERIE_CODICE.get(serie, 0) * 50000 + numero
    cifre = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = cifre[r] + s
    return s.rjust(5, "0")


def nome_file(trasmittente: str, prog: str) -> str:
    """IT<codice fiscale o partita IVA del trasmittente>_<progressivo>.xml"""
    return f"IT{trasmittente}_{prog}.xml"


def _sub(parent, tag: str, text=None):
    e = ET.SubElement(parent, tag)
    if text is not None:
        e.text = str(text)
    return e


def _anagrafica(parent, s: dict):
    a = _sub(parent, "Anagrafica")
    if s.get("denominazione"):
        _sub(a, "Denominazione", latino(s["denominazione"], 80))
    else:
        _sub(a, "Nome", latino(s.get("nome"), 60))
        _sub(a, "Cognome", latino(s.get("cognome"), 60))


def _sede(parent, s: dict):
    sede = _sub(parent, "Sede")
    _sub(sede, "Indirizzo", latino(s.get("indirizzo"), 60))
    if s.get("civico"):
        _sub(sede, "NumeroCivico", latino(s["civico"], 8, base=True))
    nazione = (s.get("nazione") or "IT").upper()
    _sub(sede, "CAP", s.get("cap") if nazione == "IT" else (s.get("cap") or "00000"))
    _sub(sede, "Comune", latino(s.get("comune"), 60))
    if s.get("provincia") and nazione == "IT":
        _sub(sede, "Provincia", s["provincia"].upper())
    _sub(sede, "Nazione", nazione)


def costruisci(fattura: dict, totali: dict) -> bytes:
    """L'XML FPR12 di una fattura (o nota di credito). `fattura`:
      tipo (TD01, TD04…), numero (testo), data (date), progressivo (5 caratteri),
      emittente {denominazione | nome+cognome, partita_iva, codice_fiscale, regime_fiscale,
                 indirizzo, civico, cap, comune, provincia, nazione, iban, email, telefono},
      trasmittente (codice fiscale o partita IVA di chi trasmette: l'emittente),
      cliente {stessi campi, codice_destinatario, pec},
      causale (testo), collegata {"numero", "data"} per la nota di credito,
      pagamento {"modalita": "MP05", "scadenza": date, "iban"} o None
    `totali`: il risultato di conti.calcola."""
    em, cl = fattura["emittente"], fattura["cliente"]
    ET.register_namespace("p", NS)
    ET.register_namespace("ds", NS_DS)
    ET.register_namespace("xsi", NS_XSI)
    root = ET.Element(f"{{{NS}}}FatturaElettronica", {"versione": "FPR12"})
    root.set(f"{{{NS_XSI}}}schemaLocation",
             f"{NS} http://www.fatturapa.gov.it/export/fatturazione/sdi/fatturapa/v1.2/"
             f"Schema_del_file_xml_FatturaPA_versione_1.2.xsd")
    head = _sub(root, "FatturaElettronicaHeader")
    dt = _sub(head, "DatiTrasmissione")
    idt = _sub(dt, "IdTrasmittente")
    _sub(idt, "IdPaese", "IT")
    _sub(idt, "IdCodice", fattura["trasmittente"])
    _sub(dt, "ProgressivoInvio", fattura["progressivo"])
    _sub(dt, "FormatoTrasmissione", "FPR12")
    estero = (cl.get("nazione") or "IT").upper() != "IT"
    codice = cl.get("codice_destinatario") or ("XXXXXXX" if estero else "0000000")
    _sub(dt, "CodiceDestinatario", codice.upper())
    if cl.get("pec") and codice == "0000000":
        _sub(dt, "PECDestinatario", cl["pec"])
    # Cedente/prestatore
    ced = _sub(head, "CedentePrestatore")
    da = _sub(ced, "DatiAnagrafici")
    idf = _sub(da, "IdFiscaleIVA")
    _sub(idf, "IdPaese", (em.get("nazione") or "IT").upper())
    _sub(idf, "IdCodice", em["partita_iva"])
    if em.get("codice_fiscale"):
        _sub(da, "CodiceFiscale", em["codice_fiscale"].upper())
    _anagrafica(da, em)
    _sub(da, "RegimeFiscale", em.get("regime_fiscale") or "RF01")
    _sede(ced, em)
    # Cessionario/committente
    ces = _sub(head, "CessionarioCommittente")
    da = _sub(ces, "DatiAnagrafici")
    if cl.get("partita_iva"):
        idf = _sub(da, "IdFiscaleIVA")
        _sub(idf, "IdPaese", (cl.get("nazione") or "IT").upper())
        _sub(idf, "IdCodice", cl["partita_iva"])
    if cl.get("codice_fiscale"):
        _sub(da, "CodiceFiscale", cl["codice_fiscale"].upper())
    _anagrafica(da, cl)
    _sede(ces, cl)
    # Corpo
    body = _sub(root, "FatturaElettronicaBody")
    dg = _sub(body, "DatiGenerali")
    dgd = _sub(dg, "DatiGeneraliDocumento")
    _sub(dgd, "TipoDocumento", fattura.get("tipo") or "TD01")
    _sub(dgd, "Divisa", "EUR")
    _sub(dgd, "Data", fattura["data"].isoformat())
    _sub(dgd, "Numero", latino(fattura["numero"], 20, base=True))
    rit = totali.get("ritenuta")
    if rit:
        r = _sub(dgd, "DatiRitenuta")
        _sub(r, "TipoRitenuta", rit["tipo"])
        _sub(r, "ImportoRitenuta", xml_num(rit["importo"], 2, 2))
        _sub(r, "AliquotaRitenuta", xml_num(rit["aliquota"], 2, 2))
        _sub(r, "CausalePagamento", rit["causale"])
    if totali.get("bollo"):
        b = _sub(dgd, "DatiBollo")
        _sub(b, "BolloVirtuale", "SI")
        _sub(b, "ImportoBollo", xml_num(totali["bollo"], 2, 2))
    cassa = totali.get("cassa")
    if cassa:
        c = _sub(dgd, "DatiCassaPrevidenziale")
        _sub(c, "TipoCassa", cassa["tipo"])
        _sub(c, "AlCassa", xml_num(cassa["aliquota"], 2, 2))
        _sub(c, "ImportoContributoCassa", xml_num(cassa["importo"], 2, 2))
        _sub(c, "ImponibileCassa", xml_num(cassa["imponibile"], 2, 2))
        _sub(c, "AliquotaIVA", xml_num(cassa["aliquota_iva"], 2, 2))
        if cassa.get("ritenuta"):
            _sub(c, "Ritenuta", "SI")
        if cassa.get("natura"):
            _sub(c, "Natura", cassa["natura"])
    _sub(dgd, "ImportoTotaleDocumento", xml_num(totali["totale"], 2, 2))
    causale = latino(fattura.get("causale"), 1000)
    while causale:                       # Causale è lunga al massimo 200: si ripete
        _sub(dgd, "Causale", causale[:200])
        causale = causale[200:]
    coll = fattura.get("collegata")
    if coll:
        fc = _sub(dg, "DatiFattureCollegate")
        _sub(fc, "IdDocumento", latino(coll["numero"], 20, base=True))
        if coll.get("data"):
            _sub(fc, "Data", coll["data"].isoformat())
    dbs = _sub(body, "DatiBeniServizi")
    for i, riga in enumerate(totali["righe"], 1):
        ln = _sub(dbs, "DettaglioLinee")
        _sub(ln, "NumeroLinea", i)
        _sub(ln, "Descrizione", latino(riga["descrizione"], 1000))
        _sub(ln, "Quantita", xml_num(riga["quantita"]))
        if riga.get("unita"):
            _sub(ln, "UnitaMisura", latino(riga["unita"], 10, base=True))
        _sub(ln, "PrezzoUnitario", xml_num(riga["prezzo"]))
        _sub(ln, "PrezzoTotale", xml_num(riga["totale"]))
        _sub(ln, "AliquotaIVA", xml_num(riga["aliquota"], 2, 2))
        if riga.get("ritenuta") and rit:
            _sub(ln, "Ritenuta", "SI")
        if riga.get("natura"):
            _sub(ln, "Natura", riga["natura"])
    for e in totali["riepilogo"]:
        rp = _sub(dbs, "DatiRiepilogo")
        _sub(rp, "AliquotaIVA", xml_num(e["aliquota"], 2, 2))
        if e["natura"]:
            _sub(rp, "Natura", e["natura"])
        _sub(rp, "ImponibileImporto", xml_num(e["imponibile"], 2, 2))
        _sub(rp, "Imposta", xml_num(e["imposta"], 2, 2))
        if not e["natura"]:
            _sub(rp, "EsigibilitaIVA", "I")
        if e.get("riferimento"):
            _sub(rp, "RiferimentoNormativo", latino(e["riferimento"], 100))
    pag = fattura.get("pagamento")
    if pag:
        dp = _sub(body, "DatiPagamento")
        _sub(dp, "CondizioniPagamento", "TP02")
        det = _sub(dp, "DettaglioPagamento")
        _sub(det, "ModalitaPagamento", pag.get("modalita") or "MP05")
        if pag.get("scadenza"):
            _sub(det, "DataScadenzaPagamento", pag["scadenza"].isoformat())
        _sub(det, "ImportoPagamento", xml_num(totali["da_pagare"], 2, 2))
        if pag.get("iban"):
            _sub(det, "IBAN", re.sub(r"\s+", "", pag["iban"]).upper())
    ET.indent(root, "  ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")


# ─────────────────────────── controlli ───────────────────────────

def controlla(fattura: dict, totali: dict) -> list[str]:
    """I vincoli che lo schema e lo SdI controllano e che dipendono dai dati (frasi brevi).
    Lo schema si controlla poi con l'XSD, se c'è."""
    from .rubrica import codice_fiscale_ok, partita_iva_ok
    err = []
    em, cl = fattura["emittente"], fattura["cliente"]
    if not partita_iva_ok(em.get("partita_iva") or ""):
        err.append("la partita IVA dell'emittente non è valida")
    if (em.get("regime_fiscale") or "RF01") not in REGIMI:
        err.append(f"regime fiscale {em.get('regime_fiscale')} sconosciuto")
    for chi, s in (("dell'emittente", em), ("del cliente", cl)):
        if not (s.get("denominazione") or (s.get("nome") and s.get("cognome"))):
            err.append(f"manca il nome {chi}")
        nazione = (s.get("nazione") or "IT").upper()
        if not s.get("indirizzo") or not s.get("comune"):
            err.append(f"manca l'indirizzo {chi}")
        if nazione == "IT" and not re.fullmatch(r"\d{5}", s.get("cap") or ""):
            err.append(f"manca il CAP {chi}")
        if nazione == "IT" and not re.fullmatch(r"[A-Z]{2}", (s.get("provincia") or "").upper()):
            err.append(f"manca la provincia {chi}")
    if not (cl.get("partita_iva") or cl.get("codice_fiscale")):
        err.append("il cliente non ha né partita IVA né codice fiscale")
    elif cl.get("partita_iva") and (cl.get("nazione") or "IT") == "IT" and \
            not partita_iva_ok(cl["partita_iva"]):
        err.append("la partita IVA del cliente non è valida")
    elif cl.get("codice_fiscale") and not codice_fiscale_ok(cl["codice_fiscale"]):
        err.append("il codice fiscale del cliente non è valido")
    if not re.fullmatch(r"[A-Z0-9]{7}", (cl.get("codice_destinatario") or "0000000").upper()):
        err.append("il codice destinatario del cliente deve avere 7 caratteri")
    if not re.search(r"\d", str(fattura.get("numero") or "")):
        err.append("il numero della fattura deve contenere una cifra")
    if fattura["data"] > datetime.date.today():
        err.append("la data della fattura è nel futuro")
    # Coerenza dei conti (controlli 00422 e 00423 dello SdI), a prova di modifiche future
    for r in totali["righe"]:
        if abs(r2(r["quantita"] * r["prezzo"]) - r["totale"]) > Decimal("0.01"):
            err.append(f"prezzo totale sbagliato nella riga «{r['descrizione'][:30]}»")
        if r["aliquota"] == 0 and not r.get("natura"):
            err.append("una riga senza IVA non ha la natura")
    for e in totali["riepilogo"]:
        if abs(r2(e["imponibile"] * e["aliquota"] / 100) - e["imposta"]) > Decimal("0.01"):
            err.append(f"imposta sbagliata al {e['aliquota']} per cento")
    if totali.get("ritenuta") and not any(r.get("ritenuta") for r in totali["righe"]) and \
            not (totali.get("cassa") or {}).get("ritenuta"):
        err.append("c'è la ritenuta ma nessuna riga è soggetta")
    if fattura.get("tipo") == "TD04" and not fattura.get("collegata"):
        err.append("una nota di credito deve dire quale fattura corregge")
    return err


def cartella_xsd(cfg) -> Path:
    p = Path(getattr(cfg, "fatture_xsd", None) or "fatturapa")
    if not p.is_absolute():
        base = getattr(cfg, "config_dir", None)
        p = (Path(base) / p) if base else p.resolve()
    return p


def xsd_presente(cartella: Path) -> bool:
    return all((Path(cartella) / n).is_file() for n in XSD)


_SCHEMI: dict[str, object] = {}


def _schema(cartella: Path):
    key = str(Path(cartella).resolve())
    if key not in _SCHEMI:
        from lxml import etree
        cartella = Path(cartella)
        testo = (cartella / "Schema_VFPR12_v1.2.3.xsd").read_bytes()
        locale = (cartella / "xmldsig-core-schema.xsd").resolve().as_uri()
        # Lo schema importa xmldsig da w3.org: si legge la copia locale (niente rete)
        testo = testo.replace(_DSIG_URL.encode(), locale.encode())
        parser = etree.XMLParser(no_network=True, resolve_entities=True)
        doc = etree.fromstring(testo, parser, base_url=(cartella / "x.xsd").resolve().as_uri())
        _SCHEMI[key] = etree.XMLSchema(doc)
    return _SCHEMI[key]


def valida_xsd(xml: bytes, cartella: Path) -> list[str] | None:
    """Gli errori dello schema ufficiale ([] = valido), o None se lo schema non c'è o lxml
    manca (allora valgono solo i controlli di `controlla`)."""
    if not xsd_presente(cartella):
        return None
    try:
        from lxml import etree
    except ImportError:
        return None
    schema = _schema(cartella)
    doc = etree.fromstring(xml, etree.XMLParser(no_network=True, resolve_entities=False))
    if schema.validate(doc):
        return []
    return [f"riga {e.line}: {e.message}" for e in schema.error_log][:10]


def scarica_xsd(cartella: Path, log=print) -> bool:
    """Scarica i due file dello schema (una volta, durante l'installazione o lo sviluppo) e
    ne verifica lo SHA-256. Non serve a Calliope per funzionare."""
    import httpx
    cartella = Path(cartella)
    cartella.mkdir(parents=True, exist_ok=True)
    ok = True
    for nome, (url, sha) in XSD.items():
        dest = cartella / nome
        if dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest() == sha:
            log(f"{nome}: già presente e verificato")
            continue
        r = httpx.get(url, follow_redirects=True, timeout=30)
        r.raise_for_status()
        got = hashlib.sha256(r.content).hexdigest()
        if got != sha:
            log(f"{nome}: SHA-256 diverso da quello atteso ({got[:12]}…): non salvato. Lo "
                f"schema può essere cambiato: controlla la versione su www.fatturapa.gov.it")
            ok = False
            continue
        dest.write_bytes(r.content)
        log(f"{nome}: scaricato e verificato")
    return ok
