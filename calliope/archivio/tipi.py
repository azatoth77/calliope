"""
I tipi di documento dell'archivio di casa e le loro schede (03/10/2026).

Per ogni tipo: i campi della scheda, con un «genere» che decide lo schema JSON per il modello
(output strutturati), il controllo contro il testo («mai inventare») e come il campo entra nel
grafo. Il modello produce **solo la scheda**; nodi e archi li fa il codice da qui
(`nel_grafo`), con la deduplicazione del grafo: niente relazioni inventate dal modello.

Generi dei campi:
  testo       stringa breve, non controllata (descrizioni: «lavatrice Candor LV800»)
  data        AAAA-MM-GG, tenuta solo se la data compare nel testo (anche «12 marzo 2025»)
  mese        come data, ma basta il mese nel testo («agosto 2025»): periodi delle bollette
  importo     euro, tenuto solo se il numero compare nel testo
  numero      quantità (consumi, mesi, giorni), tenuta solo se compare nel testo
  codice      numero di documento, POD, targa, matricola: tenuto solo se compare nel testo
  si_no       vero, falso o null (rinnovo tacito)
  ente        {nome, partita_iva, codice_fiscale}: il nome deve comparire nel testo
  persona     {nome, codice_fiscale}: il nome deve comparire nel testo
  persone     elenco di persone
  scadenze    elenco {data, cosa}
  beni        elenco {nome, identificativo}
  voci        elenco {descrizione, importo}
  indirizzi   elenco di stringhe, tenute se le loro parole compaiono nel testo
  [..]        uno tra i valori dati (enum)

Sensibili (sanità e identità): `referto` e `identita`. Li vedono solo la persona interessata e
chi amministra (servizio.py). La scelta è nel codice, non nel modello.

Cambiare questo file (campi, controlli, grafo) vuol dire alzare `VERSIONE`: l'archivio
rielabora da solo le schede vecchie (il testo e l'OCR restano, si rifà solo l'estrazione).
"""

import calendar
import datetime
import re

from . import normalizza as nz

VERSIONE = "1"

SCADENZE_COSA = ["pagamento", "fine_validita", "fine_contratto", "disdetta", "fine_garanzia",
                 "rinnovo", "revisione", "altro"]

COMUNI = {
    "oggetto": ("testo", "di cosa si tratta, in poche parole («bolletta luce agosto», «lavatrice "
                         "Candor LV800», «emocromo»)"),
    "data_documento": ("data", "data di emissione o del documento"),
    "numero": ("codice", "numero del documento, della fattura, della polizza o del contratto"),
    "emittente": ("ente", "chi emette il documento: l'azienda o l'ente il cui nome è di solito "
                          "in alto (fornitore, negozio, compagnia, struttura sanitaria, comune)"),
    "intestatari": ("persone", "le persone a cui è intestato o di cui parla (intestatario, "
                               "cliente, contraente, titolare, paziente): nome e cognome"),
    "importo_totale": ("importo", "il totale da pagare o pagato, in euro"),
    "scadenze": ("scadenze", "le date da ricordare scritte nel documento, con cosa scade"),
    "beni": ("beni", "oggetti o servizi di cui parla (auto con targa, elettrodomestico con "
                     "matricola, fornitura con POD o PDR)"),
    "indirizzi": ("indirizzi", "indirizzi di fornitura o dell'immobile"),
}

CATEGORIE_BOLLETTA = ["luce", "gas", "acqua", "telefono", "internet", "rifiuti", "condominio",
                      "riscaldamento", "altro"]


class Tipo:
    def __init__(self, nome: str, detto: str, articolo: str, campi: dict, sensibile=False,
                 descrizione: str = ""):
        self.nome = nome
        self.detto = detto                  # «bolletta», «carta d'identità»
        self.articolo = articolo            # «la», «il», «l'»
        self.campi = {**COMUNI, **campi}
        self.sensibile = sensibile
        self.descrizione = descrizione


TIPI: dict[str, Tipo] = {t.nome: t for t in (
    Tipo("bolletta", "bolletta", "la", {
        "categoria": (CATEGORIE_BOLLETTA, "di cosa è la bolletta"),
        "periodo_dal": ("mese", "inizio del periodo fatturato"),
        "periodo_al": ("mese", "fine del periodo fatturato"),
        "consumo": ("numero", "consumo fatturato"),
        "unita": ("testo", "unità del consumo (kWh, Smc, mc, GB)"),
        "codice_cliente": ("codice", "codice cliente"),
        "codice_fornitura": ("codice", "POD, PDR o codice della fornitura o della linea"),
    }, descrizione="bollette di luce, gas, acqua, telefono, internet, rifiuti, condominio"),
    Tipo("ricevuta", "ricevuta", "la", {
        "categoria": (["spesa", "elettrodomestici", "arredamento", "tecnologia", "salute",
                       "auto", "casa", "scuola", "abbigliamento", "altro"], "che spesa è"),
        "voci": ("voci", "le righe con descrizione e importo"),
        "metodo_pagamento": ("testo", "come è stato pagato"),
    }, descrizione="fatture, scontrini e ricevute di acquisti e servizi"),
    Tipo("contratto", "contratto", "il", {
        "categoria": (["affitto", "internet", "telefono", "luce", "gas", "acqua", "lavoro",
                       "finanziamento", "altro"], "che contratto è"),
        "data_inizio": ("data", "inizio o attivazione"),
        "data_fine": ("data", "fine del contratto, se scritta"),
        "durata_mesi": ("numero", "durata in mesi, se scritta"),
        "rinnovo_tacito": ("si_no", "si rinnova da solo?"),
        "preavviso_disdetta_giorni": ("numero", "giorni di preavviso per la disdetta"),
        "canone": ("importo", "canone o rata, in euro"),
        "periodicita": (["mensile", "bimestrale", "trimestrale", "semestrale", "annuale",
                         "una_tantum"], "ogni quanto si paga il canone"),
    }, descrizione="contratti di affitto, utenze, abbonamenti, finanziamenti"),
    Tipo("assicurazione", "polizza", "la", {
        "ramo": (["auto", "moto", "casa", "vita", "salute", "infortuni", "viaggio", "altro"],
                 "che polizza è"),
        "data_inizio": ("data", "decorrenza"),
        "data_fine": ("data", "scadenza della polizza"),
        "premio": ("importo", "premio in euro"),
    }, descrizione="polizze assicurative"),
    Tipo("garanzia", "garanzia", "la", {
        "prodotto": ("testo", "il prodotto coperto"),
        "marca": ("testo", "marca"),
        "modello": ("testo", "modello"),
        "numero_serie": ("codice", "numero di serie o matricola"),
        "data_acquisto": ("data", "data di acquisto"),
        "durata_mesi": ("numero", "durata della garanzia in mesi"),
        "data_fine": ("data", "fine della garanzia, se scritta"),
    }, descrizione="certificati di garanzia"),
    Tipo("referto", "referto", "il", {
        "esame": ("testo", "l'esame o la visita"),
        "data_esame": ("data", "data dell'esame"),
        "medico": ("persona", "il medico che firma"),
    }, sensibile=True, descrizione="referti, analisi, visite, certificati medici"),
    Tipo("identita", "documento d'identità", "il", {
        "tipo_documento": (["carta_identita", "passaporto", "patente", "tessera_sanitaria",
                            "permesso_soggiorno", "altro"], "quale documento"),
        "data_nascita": ("data", "data di nascita del titolare"),
        "data_rilascio": ("data", "data di rilascio"),
        "data_fine": ("data", "data di scadenza"),
    }, sensibile=True, descrizione="carte d'identità, passaporti, patenti, tessere sanitarie"),
    Tipo("manuale", "manuale", "il", {
        "prodotto": ("testo", "il prodotto"),
        "marca": ("testo", "marca"),
        "modello": ("testo", "modello"),
    }, descrizione="manuali e istruzioni"),
    Tipo("altro", "documento", "il", {}, descrizione="tutto il resto"),
)}

ELENCO = list(TIPI)


# ─────────────────────────── schema JSON per il modello ───────────────────────────

def _nullable(t: dict) -> dict:
    return {"anyOf": [t, {"type": "null"}]}


_DATA = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props),
            "additionalProperties": False}


def _schema_campo(genere) -> dict:
    if isinstance(genere, list):
        return _nullable({"type": "string", "enum": genere})
    s = {"testo": _nullable({"type": "string", "maxLength": 160}),
         "data": _nullable(_DATA), "mese": _nullable(_DATA),
         "importo": _nullable({"type": "number"}), "numero": _nullable({"type": "number"}),
         "codice": _nullable({"type": "string", "maxLength": 60}),
         "si_no": _nullable({"type": "boolean"})}.get(genere)
    if s is not None:
        return s
    # «nome_e_cognome», non «nome»: con «nome» qwen3.6 scriveva solo il nome di battesimo
    # («Mario» per «Mario Bianchi», 8 documenti su 10 nella misura del 03/10)
    persona = _obj({"nome_e_cognome": {"type": "string", "maxLength": 120},
                    "codice_fiscale": _nullable({"type": "string", "maxLength": 20})})
    # Ente e persona singoli: sempre un oggetto, con il nome che può essere null. Con
    # «oggetto oppure null» qwen3.6 sceglieva null quasi sempre (10 emittenti su 10 persi
    # nella misura del 03/10, anche con il nome in cima al documento)
    if genere == "ente":
        return _obj({"nome": _nullable({"type": "string", "maxLength": 160}),
                     "partita_iva": _nullable({"type": "string", "maxLength": 20}),
                     "codice_fiscale": _nullable({"type": "string", "maxLength": 20})})
    if genere == "persona":
        return _obj({"nome_e_cognome": _nullable({"type": "string", "maxLength": 120}),
                     "codice_fiscale": _nullable({"type": "string", "maxLength": 20})})
    if genere == "persone":
        return {"type": "array", "items": persona, "maxItems": 6}
    if genere == "scadenze":
        return {"type": "array", "maxItems": 8, "items": _obj(
            {"data": _DATA, "cosa": {"type": "string", "enum": SCADENZE_COSA}})}
    if genere == "beni":
        return {"type": "array", "maxItems": 8, "items": _obj(
            {"nome": {"type": "string", "maxLength": 120},
             "identificativo": _nullable({"type": "string", "maxLength": 40})})}
    if genere == "voci":
        return {"type": "array", "maxItems": 30, "items": _obj(
            {"descrizione": {"type": "string", "maxLength": 120}, "importo": {"type": "number"}})}
    if genere == "indirizzi":
        return {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 160}}
    raise ValueError(genere)


def schema(tipo: str) -> dict:
    """Lo schema JSON (strict) della scheda di un tipo: tutti i campi obbligatori, null se il
    dato non c'è."""
    t = TIPI[tipo]
    return _obj({k: _schema_campo(g) for k, (g, _) in t.campi.items()})


def schema_tipo() -> dict:
    return _obj({"tipo": {"type": "string", "enum": ELENCO}})


def guida_campi(tipo: str) -> str:
    """I campi con la loro spiegazione, per il prompt dell'estrazione."""
    t = TIPI[tipo]
    return "\n".join(f"- {k}: {d}" for k, (_, d) in t.campi.items())


# ─────────────────────────── controllo contro il testo ───────────────────────────

class _Testo:
    def __init__(self, testo: str):
        self.testo = testo or ""
        self.numeri = nz.numeri(self.testo)
        self.giorni, self.mesi = nz.date(self.testo)


def _data_ok(v, tx: _Testo, solo_mese: bool = False) -> str | None:
    iso = nz.data_iso(v)
    if iso is None:
        return None
    if iso in tx.giorni:
        return iso
    if solo_mese and iso[:7] in tx.mesi:
        return iso
    return None


def pulisci(tipo: str, grezza: dict, testo: str) -> tuple[dict, list[dict]]:
    """La scheda del modello controllata contro il testo: (scheda, scartati). Un valore che
    non si ritrova nel testo diventa null (o esce dall'elenco) e va negli scartati, con il
    campo e il motivo: mai un dato inventato nel grafo."""
    t = TIPI[tipo]
    tx = _Testo(testo)
    out: dict = {}
    scartati: list[dict] = []
    regole: list[str] = []
    grezza = grezza if isinstance(grezza, dict) else {}

    def scarta(campo, valore, motivo="non è nel testo"):
        scartati.append({"campo": campo, "valore": valore, "motivo": motivo})

    def ente(v, campo):
        if not isinstance(v, dict) or not str(v.get("nome") or "").strip():
            return None
        nome = str(v["nome"]).strip()
        if not nz.nome_nel_testo(nome, testo):
            scarta(campo, nome)
            return None
        e = {"nome": nome}
        for k in ("partita_iva", "codice_fiscale"):
            if v.get(k):
                if not nz.codice_nel_testo(v[k], testo):
                    scarta(f"{campo}.{k}", v[k])
                elif k == "codice_fiscale" and not re.fullmatch(r"\d{11}", nz.compatto(v[k])):
                    # Il codice fiscale di un'azienda è di 11 cifre: uno di persona è quasi
                    # sempre quello dell'intestatario messo al posto sbagliato (misura del 03/10)
                    scarta(f"{campo}.{k}", v[k], "è il codice fiscale di una persona")
                else:
                    e[k] = nz.compatto(v[k])
        return e

    def persona(v, campo):
        if not isinstance(v, dict):
            return None
        nome = str(v.get("nome_e_cognome") or v.get("nome") or "").strip()
        if not nome:
            return None
        if len(nome.split()) == 1:
            nome = _con_cognome(nome, testo, regole)
        if not nz.nome_nel_testo(nome, testo):
            scarta(campo, nome)
            return None
        p = {"nome": nome}
        if v.get("codice_fiscale"):
            if nz.codice_nel_testo(v["codice_fiscale"], testo):
                p["codice_fiscale"] = nz.compatto(v["codice_fiscale"])
            else:
                scarta(f"{campo}.codice_fiscale", v["codice_fiscale"])
        return p

    for campo, (genere, _) in t.campi.items():
        v = grezza.get(campo)
        if isinstance(genere, list):
            out[campo] = v if v in genere else None
        elif genere == "testo":
            out[campo] = str(v).strip()[:160] if isinstance(v, str) and v.strip() else None
        elif genere in ("data", "mese"):
            ok = _data_ok(v, tx, genere == "mese") if v else None
            if v and ok is None:
                scarta(campo, v)
            out[campo] = ok
        elif genere in ("importo", "numero"):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                if nz.importo_nel_testo(v, testo, tx.numeri):
                    out[campo] = round(float(v), 2)
                else:
                    scarta(campo, v)
                    out[campo] = None
            else:
                out[campo] = None
        elif genere == "codice":
            if isinstance(v, str) and v.strip():
                if nz.codice_nel_testo(v, testo):
                    out[campo] = v.strip()
                else:
                    scarta(campo, v)
                    out[campo] = None
            else:
                out[campo] = None
        elif genere == "si_no":
            out[campo] = v if isinstance(v, bool) else None
        elif genere == "ente":
            out[campo] = ente(v, campo)
        elif genere == "persona":
            out[campo] = persona(v, campo)
        elif genere == "persone":
            ps = [persona(x, campo) for x in (v if isinstance(v, list) else [])]
            seen, out[campo] = set(), []
            for p in ps:
                if p and nz.nome_persona(p["nome"]) not in seen:
                    seen.add(nz.nome_persona(p["nome"]))
                    out[campo].append(p)
        elif genere == "scadenze":
            lst = []
            for x in v if isinstance(v, list) else []:
                if not isinstance(x, dict):
                    continue
                d = _data_ok(x.get("data"), tx)
                if d is None:
                    scarta(campo, x.get("data"))
                    continue
                cosa = x.get("cosa") if x.get("cosa") in SCADENZE_COSA else "altro"
                if not any(s["data"] == d and s["cosa"] == cosa for s in lst):
                    lst.append({"data": d, "cosa": cosa})
            out[campo] = lst
        elif genere == "beni":
            lst = []
            for x in v if isinstance(v, list) else []:
                if not isinstance(x, dict) or not str(x.get("nome") or "").strip():
                    continue
                b = {"nome": str(x["nome"]).strip()[:120]}
                ident = x.get("identificativo")
                if ident:
                    if nz.codice_nel_testo(ident, testo):
                        b["identificativo"] = str(ident).strip()
                    else:
                        scarta(f"{campo}.identificativo", ident)
                lst.append(b)
            out[campo] = lst
        elif genere == "voci":
            lst = []
            for x in v if isinstance(v, list) else []:
                if not isinstance(x, dict):
                    continue
                imp = x.get("importo")
                if not (isinstance(imp, (int, float)) and nz.importo_nel_testo(imp, testo,
                                                                                tx.numeri)):
                    scarta(campo, x)
                    continue
                lst.append({"descrizione": str(x.get("descrizione") or "")[:120],
                            "importo": round(float(imp), 2)})
            out[campo] = lst
        elif genere == "indirizzi":
            lst = []
            for x in v if isinstance(v, list) else []:
                if isinstance(x, str) and x.strip():
                    # Il CAP e le sigle possono mancare nel testo: contano via e numero
                    parole = nz.nome_luogo(x).split()
                    if parole and nz.nome_nel_testo(" ".join(parole[:4]), testo):
                        lst.append(x.strip()[:160])
                    else:
                        scarta(campo, x)
            out[campo] = lst
    calcola(tipo, out)
    if regole:
        out["_regole"] = sorted(set(regole))
    return out, scartati


def _con_cognome(nome: str, testo: str, regole: list) -> str:
    """Il modello ha scritto solo il nome di battesimo («GIULIA») e il documento ha il
    cognome a parte («Cognome: BIANCHI  Nome: GIULIA», carte d'identità e moduli): si uniscono.
    Correzione della forma di una scelta del modello (principio 10), con il suo nome nelle
    regole della scheda. Solo con le etichette esplicite, mai indovinando."""
    t = nz.senza_accenti(testo)
    m_c = re.search(r"\bcognome\s*[:\-]?\s*([A-Za-z']+)", t, re.I)
    m_n = re.search(r"(?<![a-z])nome\s*[:\-]?\s*([A-Za-z']+)", t, re.I)
    if m_c and m_n and nz.piatto(m_n.group(1)) == nz.piatto(nome):
        regole.append("nome_cognome_uniti")
        return f"{nome} {m_c.group(1)}"
    return nome


def _piu_mesi(iso: str, mesi: int) -> str:
    d = datetime.date.fromisoformat(iso)
    m = d.month - 1 + int(mesi)
    y, m = d.year + m // 12, m % 12 + 1
    return datetime.date(y, m, min(d.day, calendar.monthrange(y, m)[1])).isoformat()


def calcola(tipo: str, s: dict):
    """Le date che il programma ricava (mai il modello): fine della garanzia o del contratto
    da inizio e durata, la disdetta dal preavviso; poi le scadenze dei campi propri del tipo.
    Le ricavate sono in `_calcolati`."""
    calc = []
    if tipo == "garanzia" and not s.get("data_fine") and s.get("data_acquisto") and \
            s.get("durata_mesi"):
        s["data_fine"] = _piu_mesi(s["data_acquisto"], s["durata_mesi"])
        calc.append("data_fine")
    if tipo == "contratto" and not s.get("data_fine") and s.get("data_inizio") and \
            s.get("durata_mesi"):
        s["data_fine"] = _piu_mesi(s["data_inizio"], s["durata_mesi"])
        calc.append("data_fine")
    extra = {"garanzia": ("data_fine", "fine_garanzia"),
             "assicurazione": ("data_fine", "fine_validita"),
             "identita": ("data_fine", "fine_validita"),
             "contratto": ("data_fine", "fine_contratto")}.get(tipo)
    sc = s.setdefault("scadenze", [])
    if extra and s.get(extra[0]):
        d = s[extra[0]]
        # la stessa data già messa dal modello con un'altra parola resta una sola
        if not any(x["data"] == d for x in sc):
            sc.append({"data": d, "cosa": extra[1],
                       **({"calcolata": True} if extra[0] in calc else {})})
    if tipo == "contratto" and s.get("data_fine") and s.get("preavviso_disdetta_giorni") and \
            s.get("rinnovo_tacito"):
        d = (datetime.date.fromisoformat(s["data_fine"])
             - datetime.timedelta(days=int(s["preavviso_disdetta_giorni"]))).isoformat()
        if not any(x["data"] == d and x["cosa"] == "disdetta" for x in sc):
            sc.append({"data": d, "cosa": "disdetta", "calcolata": True})
            calc.append("disdetta")
    sc.sort(key=lambda x: x["data"])
    if calc:
        s["_calcolati"] = calc


def importo_principale(tipo: str, s: dict) -> float | None:
    """La cifra del documento per le somme: il totale, altrimenti premio o canone."""
    for k in ("importo_totale", "premio", "canone"):
        if s.get(k) is not None:
            return s[k]
    return None


def categoria(tipo: str, s: dict) -> str | None:
    """Di cosa si tratta, per il nodo categoria e le somme («luce», «auto», «salute»)."""
    if tipo in ("bolletta", "ricevuta", "contratto") and s.get("categoria") not in (None, "altro"):
        return s["categoria"]
    if tipo == "assicurazione" and s.get("ramo") not in (None, "altro"):
        return s["ramo"]
    if tipo == "referto":
        return "salute"
    if tipo == "identita":
        return "identità"
    return None


# ─────────────────────────── come si dice ───────────────────────────

_DI_CATEGORIA = {"luce": "della luce", "gas": "del gas", "acqua": "dell'acqua",
                 "telefono": "del telefono", "internet": "di internet",
                 "rifiuti": "dei rifiuti", "condominio": "del condominio",
                 "riscaldamento": "del riscaldamento", "affitto": "d'affitto",
                 "lavoro": "di lavoro", "finanziamento": "di finanziamento"}
_DOC_IDENTITA = {"carta_identita": ("la", "carta d'identità"), "passaporto": ("il", "passaporto"),
                 "patente": ("la", "patente"), "tessera_sanitaria": ("la", "tessera sanitaria"),
                 "permesso_soggiorno": ("il", "permesso di soggiorno")}


def nome_detto(nome: str) -> str:
    """«LUMEN ENERGIA S.p.A.» → «Lumen Energia»: senza forma societaria, maiuscole normali."""
    n = re.sub(r"[\s,]*\b(?:s\.?\s?p\.?\s?a\.?|s\.?\s?r\.?\s?l\.?|s\.?\s?n\.?\s?c\.?|"
               r"s\.?\s?a\.?\s?s\.?)(?=\W|$)\.?", "", str(nome or ""), flags=re.I).strip(" ,.-")
    if n.isupper() or n.islower():
        n = " ".join(w if len(w) <= 2 and w.isupper() and not w.isalpha() else w.capitalize()
                     for w in n.split())
    return n or str(nome or "")


def _della(cosa: str) -> str:
    """«della lavatrice», «del televisore», «dell'asciugatrice»: il genere dalla prima parola
    (in «-a», «-ice», «-ione», «-ie»: femminile). Sbaglia sui casi rari, ma resta comprensibile."""
    if cosa[:1].lower() in "aeiouàèéìòù":
        return "dell'" + cosa
    prima = cosa.split()[0].lower()
    femminile = prima.endswith(("a", "ice", "ione", "ie"))     # lavatrice, televisione
    return ("della " if femminile else "del ") + cosa


def _di(nome: str) -> str:
    """«di Aurora Assicurazioni»: davanti ai nomi propri niente elisione («d'Aurora» suona
    male); sì davanti ai nomi comuni («d'affitto» lo fa _DI_CATEGORIA)."""
    return "di " + nome


def descrivi(tipo: str, s: dict, file: str = "") -> str:
    """Come si chiama il documento a voce: «la bolletta della luce di Lumen Energia del 10
    settembre 2026». La fa il codice dai campi controllati, non il modello."""
    em = nome_detto(s["emittente"]["nome"]) if s.get("emittente") else ""
    chi = s["intestatari"][0]["nome"] if s.get("intestatari") else ""
    chi = " ".join(w.capitalize() for w in chi.split()) if chi.isupper() else chi
    quando = s.get("data_documento")
    if tipo == "bolletta":
        base = f"la bolletta {_DI_CATEGORIA.get(s.get('categoria'), '')}".strip()
        if em:
            base += f" {_di(em)}"
    elif tipo == "ricevuta":
        base = "la ricevuta" + (f" {_di(em)}" if em else "")
        if s.get("oggetto"):
            base += f" ({s['oggetto']})"
    elif tipo == "contratto":
        base = f"il contratto {_DI_CATEGORIA.get(s.get('categoria'), '')}".strip()
        if em:
            base += f" con {em}"
        quando = None
    elif tipo == "assicurazione":
        ramo = s.get("ramo")
        base = "la polizza" + (f" {ramo}" if ramo and ramo != "altro" else "")
        if em:
            base += f" {_di(em)}"
        quando = None
    elif tipo == "garanzia":
        cosa = s.get("prodotto") or s.get("oggetto") or ""
        base = "la garanzia" + (f" {_della(cosa)}" if cosa else "")
        quando = None
    elif tipo == "referto":
        base = "il referto" + (f" {_di(s['esame'])}" if s.get("esame") else "")
        if chi:
            base += f" {_di(chi)}"
        quando = s.get("data_esame") or quando
    elif tipo == "identita":
        art, nome = _DOC_IDENTITA.get(s.get("tipo_documento"), ("il", "documento d'identità"))
        base = f"{art} {nome}" + (f" {_di(chi)}" if chi else "")
        quando = None
    elif tipo == "manuale":
        cosa = s.get("prodotto") or s.get("oggetto") or ""
        base = "il manuale" + (f" {_di(cosa)}" if cosa else "")
        quando = None
    else:
        base = f"il documento «{s.get('oggetto') or file}»" if (s.get("oggetto") or file) \
            else "il documento"
    if quando:
        base += f" del {nz.data_detta(quando)}"
    return " ".join(base.split())


# ─────────────────────────── nel grafo ───────────────────────────

_PAGANTE = {"bolletta", "ricevuta", "contratto", "assicurazione"}


def nel_grafo(g, db, doc: int, tipo: str, s: dict):
    """Nodi e archi del documento, dalla scheda controllata (gli archi hanno fonte = doc)."""
    data = s.get("data_documento")
    cat = categoria(tipo, s)
    if cat:
        c = g.entita(db, "categoria", cat)
        g.arco(db, doc, "riguarda", c, doc)
    ente = None
    if s.get("emittente"):
        e = s["emittente"]
        ente = g.entita(db, "ente", nome_detto(e["nome"]), partita_iva=e.get("partita_iva"),
                        codice_fiscale=e.get("codice_fiscale"))
        if ente:
            g.arco(db, doc, "emesso_da", ente, doc)
    persone = []
    for p in s.get("intestatari") or []:
        nome = " ".join(w.capitalize() for w in p["nome"].split()) if p["nome"].isupper() \
            else p["nome"]
        pid = g.entita(db, "persona", nome, codice_fiscale=p.get("codice_fiscale"))
        if pid:
            persone.append(pid)
            g.arco(db, doc, "intestato_a", pid, doc)
    if s.get("medico"):
        m = g.entita(db, "persona", s["medico"]["nome"],
                     codice_fiscale=s["medico"].get("codice_fiscale"))
        if m:
            g.arco(db, doc, "redatto_da", m, doc)
    # Importi: il principale (con la data del documento, per le somme) e gli altri
    importi = []
    for campo, voce in (("importo_totale", "totale"), ("premio", "premio"), ("canone", "canone")):
        v = s.get(campo)
        if v is not None and not any(abs(v - x) < 0.005 for x, _ in importi):
            importi.append((v, voce))
    for x in s.get("voci") or []:
        importi.append((x["importo"], x["descrizione"] or "voce"))
    for i, (v, voce) in enumerate(importi):
        nid = g.nodo(db, "importo", f"doc:{doc}:imp:{i}", f"{nz.euro(v)} ({voce})", data=data,
                     valore=v, attributi={"voce": voce, "valuta": "EUR"})
        g.arco(db, doc, "ha_importo", nid, doc, {"voce": voce})
        if tipo in _PAGANTE and i == 0:
            for pid in persone:
                g.arco(db, pid, "paga", nid, doc)
    for i, sc in enumerate(s.get("scadenze") or []):
        nid = g.nodo(db, "scadenza", f"doc:{doc}:scad:{i}",
                     f"{sc['cosa'].replace('_', ' ')} {nz.data_detta(sc['data'])}",
                     data=sc["data"], attributi={"cosa": sc["cosa"],
                                                 **({"calcolata": True} if sc.get("calcolata")
                                                    else {})})
        g.arco(db, doc, "scade_il", nid, doc, {"cosa": sc["cosa"]})
    luoghi = []
    for ind in s.get("indirizzi") or []:
        lid = g.entita(db, "luogo", ind)
        if lid:
            luoghi.append(lid)
            g.arco(db, doc, "riguarda", lid, doc)
    beni = list(s.get("beni") or [])
    if tipo in ("garanzia", "manuale") and (s.get("prodotto") or s.get("numero_serie")):
        nome = " ".join(x for x in (s.get("prodotto"), s.get("marca") if s.get("marca") and
                                    s["marca"].lower() not in (s.get("prodotto") or "").lower()
                                    else None) if x) or s.get("oggetto") or "prodotto"
        beni.insert(0, {"nome": nome, "identificativo": s.get("numero_serie")})
    if tipo == "bolletta" and s.get("codice_fornitura"):
        beni.insert(0, {"nome": f"fornitura {s.get('categoria') or ''}".strip(),
                        "identificativo": s["codice_fornitura"]})
    for b in beni:
        bid = g.entita(db, "bene", b["nome"], identificativo=b.get("identificativo"),
                       attributi={"identificativo": b.get("identificativo")})
        if not bid:
            continue
        rel = "copre" if tipo in ("garanzia", "assicurazione") else "riguarda"
        g.arco(db, doc, rel, bid, doc)
        if tipo == "bolletta" and ente and b.get("identificativo"):
            g.arco(db, ente, "fornisce", bid, doc)
        if luoghi and tipo in ("bolletta", "contratto"):
            g.arco(db, bid, "si_trova_in", luoghi[0], doc)
