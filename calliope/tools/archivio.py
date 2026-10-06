"""
I tool dell'archivio dei documenti di casa (calliope/archivio/, 03/10/2026): pochi, chiusi,
con gli enum, e con la frase già pronta (`risposta_finale`): il modello della voce non legge
le schede e non fa i conti.

- archivio_cerca(cosa, tipo, persona, periodo, dato): trova un documento e dice il dato
  chiesto (descrizione, importo, scadenza, numero, data, intestatario); con dato=dettagli
  restituisce i campi della scheda al modello (domande che gli enum non coprono: «quanti kWh?»);
- archivio_scadenze(entro, tipo): cosa scade da oggi alla settimana, al mese, ai tre mesi,
  all'anno;
- archivio_somma(categoria, tipo, ente, persona, periodo): quanto si è speso, sommato dal
  programma.

Permessi nel codice (archivio/servizio.py): gli ospiti non hanno i tool; i documenti
sensibili (referti, identità) solo all'interessato e a chi amministra, mai nella zona grigia;
quelli nella cartella di una persona solo a lei e a chi amministra. La scheda sugli schermi
è «casa» o «personale» secondo il documento.

Privacy del registro dei turni: i tool sono `riservati` (spec.py): argomenti, risultato e
risposta non finiscono né nel registro né nel terminale, solo il nome del tool.
"""

from ..archivio import Chi
from ..archivio import normalizza as nz
from ..archivio import tipi
from .spec import ToolContext, ToolSpec
from ..testi import FAMILY, NIENTE

_TIPI = ["qualsiasi"] + tipi.ELENCO
_DATI = ["descrizione", "importo", "scadenza", "numero", "data", "chi", "dettagli"]
_ENTRO = {"settimana": (7, "nella prossima settimana"), "mese": (31, "nel prossimo mese"),
          "tre_mesi": (92, "nei prossimi tre mesi"), "anno": (366, "nel prossimo anno")}
_CATEGORIE = ["qualsiasi", "luce", "gas", "acqua", "telefono", "internet", "rifiuti",
              "condominio", "riscaldamento", "auto", "casa", "salute", "spesa",
              "elettrodomestici", "tecnologia", "scuola"]
_PER_CATEGORIA = {"luce": "la luce", "gas": "il gas", "acqua": "l'acqua",
                  "telefono": "il telefono", "internet": "internet", "rifiuti": "i rifiuti",
                  "condominio": "il condominio", "riscaldamento": "il riscaldamento",
                  "auto": "l'auto", "casa": "la casa", "salute": "la salute",
                  "spesa": "la spesa", "elettrodomestici": "gli elettrodomestici",
                  "tecnologia": "la tecnologia", "scuola": "la scuola"}
_COSA_SCADE = {"pagamento": "da pagare", "fine_validita": "scade", "fine_contratto": "finisce",
               "disdetta": "ultimo giorno per la disdetta", "fine_garanzia": "finisce",
               "rinnovo": "si rinnova", "revisione": "revisione", "altro": "scade"}


def _final(text: str, **extra) -> dict:
    return {"ok": True, **extra, "conferma": text, "risposta_finale": text}


def _no(text: str) -> dict:
    return _final(text, ok=False, fatto=NIENTE)


def _servizio(ctx):
    return getattr(ctx, "archivio", None)


def _chi(ctx) -> Chi | None:
    chi = Chi.da_ctx(ctx)
    return chi if chi.livello in FAMILY and chi.profilo else None


def _maiuscola(t: str) -> str:
    return t[:1].upper() + t[1:]


def _scheda_schermo(svc, ctx, doc: dict, s: dict) -> dict | None:
    """L'anteprima del documento per gli schermi: i campi principali in una tabella."""
    if getattr(ctx, "schermi", None) is None:
        return None
    try:
        from ..schermi import schede
    except Exception:  # noqa: BLE001
        return None
    righe = []
    if doc.get("data"):
        righe.append(["Data", nz.data_detta(doc["data"])])
    if s.get("emittente"):
        righe.append(["Emesso da", s["emittente"]["nome"]])
    for p in s.get("intestatari") or []:
        righe.append(["Intestato a", p["nome"]])
    if s.get("numero"):
        righe.append(["Numero", s["numero"]])
    if doc.get("totale") is not None:
        righe.append(["Importo", nz.euro(doc["totale"])])
    for k, nome in (("periodo_dal", "Periodo dal"), ("periodo_al", "Periodo al"),
                    ("prodotto", "Prodotto"), ("esame", "Esame")):
        if s.get(k):
            v = s[k]
            righe.append([nome, nz.data_detta(v) if k.startswith("periodo") else str(v)])
    if s.get("consumo") is not None:
        righe.append(["Consumo", f"{s['consumo']:g} {s.get('unita') or ''}".strip()])
    for sc in s.get("scadenze") or []:
        righe.append([_maiuscola(sc["cosa"].replace("_", " ")), nz.data_detta(sc["data"])])
    card = schede.nuova("documento", _maiuscola(doc["nome"]), svc.visibilita_scheda(doc),
                        chiave=f"archivio:{doc['id']}", formato="",
                        file=(doc.get("attributi") or {}).get("file", ""),
                        blocchi=[{"tipo": "tabella", "colonne": ["", ""],
                                  "righe": righe[:30], "totale": None}])
    return card


_ARTICOLATE = {"di": {"il": "del", "lo": "dello", "la": "della", "i": "dei", "gli": "degli",
                      "le": "delle", "l'": "dell'"},
               "in": {"il": "nel", "lo": "nello", "la": "nella", "i": "nei", "gli": "negli",
                      "le": "nelle", "l'": "nell'"}}


def _prep(prep: str, nome: str) -> str:
    """«di» + «la polizza auto» → «della polizza auto»; «in» + «il referto» → «nel referto»
    (con la maiuscola se comincia la frase: «In» → «Nel»)."""
    cap = prep[:1].isupper()
    p = prep.lower()
    art, _, resto = nome.partition(" ")
    if nome.startswith("l'"):
        art, resto = "l'", nome[2:]
    out = (_ARTICOLATE[p][art] + ("" if art == "l'" else " ") + resto) if art in _ARTICOLATE[p]         else f"{p} {nome}"
    return _maiuscola(out) if cap else out


def _risposta_dato(dato: str, doc: dict, s: dict) -> str:
    nome = doc["nome"]
    if dato == "importo":
        if doc.get("totale") is None:
            return f"{_prep('In', nome)} non trovo l'importo."
        return f"{_maiuscola(nome)}: {nz.euro(doc['totale'])}."
    if dato == "scadenza":
        sc = s.get("scadenze") or []
        if not sc:
            return f"{_prep('In', nome)} non trovo scadenze."
        parti = [f"{_COSA_SCADE.get(x['cosa'], 'scade')} il {nz.data_detta(x['data'])}"
                 for x in sc[:3]]
        return f"{_maiuscola(nome)}: " + ", ".join(parti) + "."
    if dato == "numero":
        if not s.get("numero"):
            return f"{_prep('In', nome)} non trovo un numero."
        return f"Il numero {_prep('di', nome)} è {s['numero']}."
    if dato == "data":
        if not doc.get("data"):
            return f"{_prep('In', nome)} non trovo la data."
        return f"{_maiuscola(nome)} è del {nz.data_detta(doc['data'])}."
    if dato == "chi":
        parti = []
        if s.get("intestatari"):
            parti.append("è intestato a " + " e ".join(p["nome"] for p in s["intestatari"][:3]))
        if s.get("emittente"):
            parti.append("l'ha emesso " + tipi.nome_detto(s["emittente"]["nome"]))
        return (f"{_maiuscola(nome)}: " + ", ".join(parti) + ".") if parti else \
            f"{_prep('In', nome)} non trovo a chi è intestato."
    # descrizione: con il numero e a chi è intestato, se ci sono (04/10, 26B: a «Qual è il
    # numero della polizza dell'auto?» e «A chi è intestato il contratto di internet?»
    # lasciava dato=descrizione e la frase pronta non conteneva il dato chiesto)
    chi_num = []
    if s.get("numero"):
        chi_num.append(f"numero {s['numero']}")
    if s.get("intestatari"):
        chi_num.append("a nome di " + " e ".join(p["nome"] for p in s["intestatari"][:3]))
    if chi_num:
        nome = f"{nome}, {', '.join(chi_num)}"
    extra = []
    if doc.get("totale") is not None:
        extra.append(nz.euro(doc["totale"]))
    sc = [x for x in s.get("scadenze") or [] if x["cosa"] in ("pagamento", "fine_validita",
                                                                 "fine_garanzia",
                                                                 "fine_contratto")]
    if sc:
        extra.append(f"{_COSA_SCADE.get(sc[0]['cosa'], 'scade')} il "
                     f"{nz.data_detta(sc[0]['data'])}")
    return _maiuscola(nome) + (": " + ", ".join(extra) if extra else "") + "."


def _archivio_cerca(ctx: ToolContext, cosa: str = "", tipo: str = "qualsiasi",
                    persona: str = "", periodo: str = "", dato: str = "descrizione") -> dict:
    svc = _servizio(ctx)
    if svc is None:
        return _no("Qui non ho l'archivio dei documenti di casa.")
    chi = _chi(ctx)
    if chi is None:
        return _no("I documenti di casa li posso cercare solo per le persone di casa che "
                   "riconosco dalla voce.")
    tipo = tipo if tipo in tipi.TIPI else None
    dato = dato if dato in _DATI else "descrizione"
    res = svc.cerca(chi, str(cosa or ""), tipo, str(persona or ""), str(periodo or ""))
    docs = res["documenti"]
    if res.get("persona_sconosciuta"):
        return _final(f"Non trovo documenti di {persona}.", ok=False)
    if not docs:
        quando = f" {res['periodo']}" if res.get("periodo") else ""
        cosa_d = f" su «{cosa}»" if cosa else ""
        return _final(f"Non trovo documenti{cosa_d}{quando} nell'archivio.", ok=False)
    doc = docs[0]
    s = svc.scheda(doc["id"])
    card = _scheda_schermo(svc, ctx, doc, s)
    if dato == "dettagli":
        campi = {k: v for k, v in s.items() if v not in (None, [], "") and not k.startswith("_")}
        out = {"ok": True, "documento": doc["nome"], "campi": campi,
               "altri": [d["nome"] for d in docs[1:3]],
               "cosa_fare": "rispondi in una o due frasi solo con i dati di questi campi; se il "
                            "dato chiesto non c'è, dillo"}
        if card:
            out["scheda"] = card
        return out
    frase = _risposta_dato(dato, doc, s)
    if dato == "descrizione" and len(docs) > 1:
        altri = [d["nome"] for d in docs[1:3]]
        frase = (f"Ne ho trovati {res['totale']}. Il più adatto è {doc['nome']}"
                 + _risposta_dato("descrizione", doc, s)[len(doc["nome"]):]
                 + " Poi " + " e ".join(altri) + ".")
    out = _final(frase, documento=doc["nome"])
    if card:
        out["scheda"] = card
    return out


def _archivio_scadenze(ctx: ToolContext, entro: str = "mese", tipo: str = "qualsiasi") -> dict:
    svc = _servizio(ctx)
    if svc is None:
        return _no("Qui non ho l'archivio dei documenti di casa.")
    chi = _chi(ctx)
    if chi is None:
        return _no("Le scadenze dei documenti le dico solo alle persone di casa che riconosco "
                   "dalla voce.")
    giorni, detto = _ENTRO.get(entro, _ENTRO["mese"])
    lst = svc.scadenze(chi, giorni, tipo if tipo in tipi.TIPI else None)
    if not lst:
        return _final(f"{_maiuscola(detto)} non scade niente tra i documenti di casa.")
    parti = []
    for x in lst[:5]:
        d = x["documento"]
        cosa = _COSA_SCADE.get(x["cosa"], "scade")
        imp = f", {nz.euro(d['totale'])}" if x["cosa"] == "pagamento" and \
            d.get("totale") is not None else ""
        parti.append(f"il {nz.data_detta(x['data'], anno=False)} {d['nome']} ({cosa}{imp})")
    frase = f"{_maiuscola(detto)}: " + "; ".join(parti) + "."
    if len(lst) > 5:
        frase += f" E altre {len(lst) - 5}."
    return _final(frase, quante=len(lst))


def _archivio_somma(ctx: ToolContext, categoria: str = "qualsiasi", tipo: str = "qualsiasi",
                    ente: str = "", persona: str = "", periodo: str = "") -> dict:
    svc = _servizio(ctx)
    if svc is None:
        return _no("Qui non ho l'archivio dei documenti di casa.")
    chi = _chi(ctx)
    if chi is None:
        return _no("Le spese dei documenti le dico solo alle persone di casa che riconosco "
                   "dalla voce.")
    cat = categoria if categoria in _CATEGORIE and categoria != "qualsiasi" else None
    r = svc.somma(chi, cat, tipo if tipo in tipi.TIPI else None, str(ente or ""),
                  str(persona or ""), str(periodo or ""))
    per = _PER_CATEGORIA.get(cat, cat) if cat else ""
    quando = f" {r['periodo']}" if r["periodo"] else ""
    con = f" con {ente}" if ente else ""
    if not r["documenti"]:
        return _final(f"Non trovo spese{' per ' + per if per else ''}{con}{quando} nei "
                      f"documenti di casa.", ok=False)
    n = r["documenti"]
    intro = (f"Per {per}" if per else "In tutto") + con + quando
    frase = f"{intro}: {nz.euro(r['totale'])} in {n} {'documento' if n == 1 else 'documenti'}"
    if r["primo"] and r["ultimo"] and r["primo"][:7] != r["ultimo"][:7]:
        frase += f", da {nz.mese_detto(r['primo'])} a {nz.mese_detto(r['ultimo'])}"
    frase += "."
    if len(r["per_anno"]) > 1:
        frase += " " + _maiuscola(", ".join(f"nel {a} {nz.euro(v)}"
                                            for a, v in r["per_anno"].items())) + "."
    if r["senza_importo"]:
        frase += f" Altri {r['senza_importo']} senza importo."
    return _final(frase, totale=r["totale"], documenti=n)


def archivio_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="archivio_cerca",
            description=(
                "Cerca nei documenti di casa archiviati (bollette, ricevute e fatture, "
                "contratti, polizze, garanzie, referti, documenti d'identità, manuali) e "
                "risponde con il dato chiesto. cosa: le parole utili («bolletta della luce», "
                "«polizza auto», «lavatrice»): «quanto era l'ultima bolletta della luce?», «fino a "
                "quando è in garanzia la lavatrice?», «qual è il numero della polizza?»; tipo: il "
                "tipo di documento se è chiaro; persona: "
                "di chi è, se detto («mia» = io, «di Giulia»); periodo: come detto («settembre», "
                "«2025», «l'anno scorso»); dato: descrizione (predefinito), importo, scadenza, "
                "numero (della polizza, del contratto…), data, chi (intestatario ed emittente), "
                "dettagli per tutto il resto («quanti kWh?», «quanti metri cubi?», «di che "
                "periodo è?», «che esame era?»). Non per i file del "
                "computer."),
            parameters={"type": "object",
                        "properties": {"cosa": {"type": "string"},
                                       "tipo": {"type": "string", "enum": _TIPI},
                                       "persona": {"type": "string"},
                                       "periodo": {"type": "string"},
                                       "dato": {"type": "string", "enum": _DATI}},
                        "required": ["cosa"]},
            func=_archivio_cerca, risk="lettura", levels=FAMILY, riservato=True),
        ToolSpec(
            name="archivio_scadenze",
            description=("Dice cosa scade nei documenti di casa da oggi in poi: bollette da "
                         "pagare, polizze, garanzie, contratti, documenti d'identità. entro: "
                         "settimana, mese (predefinito), tre_mesi o anno; tipo facoltativo."),
            parameters={"type": "object",
                        "properties": {"entro": {"type": "string", "enum": list(_ENTRO)},
                                       "tipo": {"type": "string", "enum": _TIPI}},
                        "required": []},
            func=_archivio_scadenze, risk="lettura", levels=FAMILY, riservato=True),
        ToolSpec(
            name="archivio_somma",
            description=("Somma quanto si è speso secondo i documenti di casa (bollette, "
                         "ricevute, polizze): «quanto ho speso di luce quest'anno?», «quanto "
                         "abbiamo pagato di gas nel 2026?». categoria, tipo, ente (il "
                         "fornitore), persona e periodo come detti. La somma la fa il "
                         "programma: non rifare i conti."),
            parameters={"type": "object",
                        "properties": {"categoria": {"type": "string", "enum": _CATEGORIE},
                                       "tipo": {"type": "string", "enum": _TIPI},
                                       "ente": {"type": "string"},
                                       "persona": {"type": "string"},
                                       "periodo": {"type": "string"}},
                        "required": []},
            func=_archivio_somma, risk="lettura", levels=FAMILY, riservato=True),
    ]
