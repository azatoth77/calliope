"""
Le stampe di fatture, note di credito, preventivi e DDT, nel formato a blocchi dei
documenti (calliope/documenti/formato.py): stessa validazione, stesso render (PDF con
fpdf2, o Word) e stessa anteprima sugli schermi. I numeri arrivano già calcolati da
conti.py: qui si impaginano soltanto.

La fattura in PDF è una **copia di cortesia**: il documento fiscale è il file XML. Lo dice
il PDF stesso, in fondo.
"""

import datetime

from .conti import euro
from .rubrica import nome_di
from ..testi import MESI


def data_estesa(d: datetime.date) -> str:
    return f"{d.day} {MESI[d.month - 1]} {d.year}"


def blocco_soggetto(s: dict, intestazione: str = "") -> str:
    righe = [intestazione] if intestazione else []
    righe.append(nome_di(s))
    via = " ".join(x for x in (s.get("indirizzo"), s.get("civico")) if x)
    if via:
        righe.append(via)
    luogo = " ".join(x for x in (s.get("cap"), s.get("comune")) if x)
    if s.get("provincia"):
        luogo += f" ({s['provincia']})"
    if (s.get("nazione") or "IT") != "IT":
        luogo += f" {s['nazione']}"
    if luogo.strip():
        righe.append(luogo.strip())
    if s.get("partita_iva"):
        righe.append(f"P. IVA {s['partita_iva']}")
    if s.get("codice_fiscale") and s.get("codice_fiscale") != s.get("partita_iva"):
        righe.append(f"C.F. {s['codice_fiscale']}")
    for k, nome in (("email", "Email"), ("pec", "PEC"), ("telefono", "Tel.")):
        if s.get(k):
            righe.append(f"{nome} {s[k]}")
    return "\n".join(righe)


def _qta(q) -> str:
    from ..documenti.formato import format_number
    return format_number(float(q) if q != int(q) else int(q))


def _iva(r: dict) -> str:
    return r["natura"] if r.get("natura") else f"{_qta(r['aliquota'])}%"


def tabella_righe(totali: dict) -> dict:
    righe = []
    for r in totali["righe"]:
        desc = r["descrizione"] if len(r["descrizione"]) <= 290 else r["descrizione"][:287] + "…"
        righe.append([desc, _qta(r["quantita"]) + (f" {r['unita']}" if r.get("unita") else ""),
                      euro(r["prezzo"]), _iva(r), euro(r["totale"])])
    return {"tipo": "tabella", "colonne": ["Descrizione", "Quantità", "Prezzo (€)", "IVA",
                                           "Importo (€)"], "righe": righe, "totale": False}


def tabella_totali(totali: dict) -> list[dict]:
    out = []
    riep = [[(f"{_qta(e['aliquota'])}%" if not e["natura"] else e["natura"]),
             euro(e["imponibile"]), euro(e["imposta"])] for e in totali["riepilogo"]]
    out.append({"tipo": "tabella", "colonne": ["Aliquota o natura", "Imponibile (€)",
                                               "Imposta (€)"], "righe": riep, "totale": False})
    t = []
    if totali.get("cassa"):
        c = totali["cassa"]
        t.append([f"Contributo cassa ({c['tipo']}) {_qta(c['aliquota'])}%", euro(c["importo"])])
    t += [["Imponibile", euro(totali["imponibile"])], ["IVA", euro(totali["imposta"])],
          ["Totale documento", euro(totali["totale"])]]
    if totali.get("ritenuta"):
        r = totali["ritenuta"]
        t.append([f"Ritenuta d'acconto {_qta(r['aliquota'])}%", euro(-r["importo"])])
        t.append(["Netto a pagare", euro(totali["da_pagare"])])
    out.append({"tipo": "tabella", "colonne": ["Totali", "Importo (€)"], "righe": t,
                "totale": False})
    return out


def note_fiscali(totali: dict) -> list[str]:
    out = [f"{e['natura']}: {e['riferimento']}" for e in totali["riepilogo"]
           if e["natura"] and e.get("riferimento")]
    if totali.get("bollo"):
        out.append("Imposta di bollo da 2,00 € assolta in modo virtuale ai sensi del DM "
                   "17/06/2014.")
    return out


def fattura(f: dict, totali: dict, titolo: str = "Fattura") -> dict:
    """La copia di cortesia di una fattura o nota di credito."""
    blocchi = [{"tipo": "titolo", "testo": f"{titolo} n. {f['numero']} del "
                                           f"{data_estesa(f['data'])}"},
               {"tipo": "paragrafo", "testo": blocco_soggetto(f["emittente"])},
               {"tipo": "paragrafo", "testo": blocco_soggetto(f["cliente"], "Spett.le"),
                "allinea": "destra"}]
    if f.get("collegata"):
        c = f["collegata"]
        blocchi.append({"tipo": "paragrafo", "testo": f"Rettifica della fattura n. {c['numero']}"
                        + (f" del {data_estesa(c['data'])}" if c.get("data") else "") + "."})
    if f.get("causale"):
        blocchi.append({"tipo": "paragrafo", "testo": f"Causale: {f['causale']}"})
    blocchi.append(tabella_righe(totali))
    blocchi += tabella_totali(totali)
    note = note_fiscali(totali)
    pag = f.get("pagamento")
    if pag:
        p = "Pagamento con bonifico bancario"
        if pag.get("iban"):
            p += f" sull'IBAN {pag['iban']}"
        if pag.get("scadenza"):
            p += f" entro il {data_estesa(pag['scadenza'])}"
        note.append(p + f": {euro(totali['da_pagare'])}.")
    if note:
        blocchi.append({"tipo": "paragrafo", "testo": "\n".join(note)})
    blocchi.append({"tipo": "paragrafo", "testo": "Copia di cortesia. Il documento valido ai "
                    "fini fiscali è il file XML trasmesso tramite il Sistema di Interscambio."})
    return {"titolo": f"{titolo} {f['numero']} {nome_di(f['cliente'])}"[:110], "blocchi": blocchi}


def preventivo(p: dict, totali: dict) -> dict:
    blocchi = [{"tipo": "titolo", "testo": f"Preventivo n. {p['numero']} del "
                                           f"{data_estesa(p['data'])}"},
               {"tipo": "paragrafo", "testo": blocco_soggetto(p["emittente"])},
               {"tipo": "paragrafo", "testo": blocco_soggetto(p["cliente"], "Spett.le"),
                "allinea": "destra"},
               {"tipo": "paragrafo", "testo": f"Oggetto: {p['oggetto']}"}]
    for par in [x.strip() for x in str(p.get("descrizione") or "").split("\n\n") if x.strip()]:
        blocchi.append({"tipo": "paragrafo", "testo": par[:2900]})
    blocchi.append(tabella_righe(totali))
    blocchi += tabella_totali(totali)
    note = note_fiscali(totali)
    if p.get("validita_giorni"):
        note.append(f"Validità dell'offerta: {p['validita_giorni']} giorni dalla data del "
                    f"preventivo.")
    if p.get("note"):
        note.append(str(p["note"]))
    if note:
        blocchi.append({"tipo": "paragrafo", "testo": "\n".join(note)})
    blocchi.append({"tipo": "paragrafo", "testo": "Per accettazione\n\n"
                    "______________________________", "allinea": "destra"})
    return {"titolo": f"Preventivo {p['numero']} {nome_di(p['cliente'])}"[:110],
            "blocchi": blocchi}


def ddt(d: dict) -> dict:
    blocchi = [{"tipo": "titolo", "testo": f"Documento di trasporto n. {d['numero']} del "
                                           f"{data_estesa(d['data'])}"},
               {"tipo": "paragrafo", "testo": blocco_soggetto(d["emittente"], "Mittente")},
               {"tipo": "paragrafo", "testo": blocco_soggetto(d["cliente"], "Destinatario"),
                "allinea": "destra"}]
    if d.get("luogo_destinazione"):
        blocchi.append({"tipo": "paragrafo", "testo": f"Luogo di destinazione: "
                                                      f"{d['luogo_destinazione']}"})
    blocchi.append({"tipo": "paragrafo", "testo": f"Causale del trasporto: "
                                                  f"{d.get('causale_trasporto') or 'vendita'}"})
    righe = [[r["descrizione"][:290], _qta(r["quantita"]), r.get("unita") or ""]
             for r in d["righe"]]
    blocchi.append({"tipo": "tabella", "colonne": ["Descrizione dei beni", "Quantità",
                                                   "Unità"], "righe": righe, "totale": False})
    info = []
    for k, nome in (("colli", "Numero di colli"), ("peso", "Peso"),
                    ("aspetto", "Aspetto esteriore dei beni"),
                    ("trasporto_a_cura", "Trasporto a cura del"), ("vettore", "Vettore")):
        if d.get(k):
            info.append(f"{nome}: {d[k]}")
    info.append(f"Inizio del trasporto: {data_estesa(d['data'])}"
                + (f", ore {d['ora']}" if d.get("ora") else ""))
    blocchi.append({"tipo": "paragrafo", "testo": "\n".join(info)})
    blocchi.append({"tipo": "paragrafo", "testo": "Firma del mittente ____________________\n\n"
                    "Firma del vettore ____________________\n\n"
                    "Firma del destinatario ____________________"})
    return {"titolo": f"DDT {d['numero']} {nome_di(d['cliente'])}"[:110], "blocchi": blocchi}
