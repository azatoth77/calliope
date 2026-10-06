"""
I conti di fatture, note di credito e preventivi: sempre del programma, mai del modello.

Tutto in `Decimal` con l'arrotondamento commerciale (ROUND_HALF_UP) a 2 decimali, come i
controlli dello SdI (specifiche tecniche FatturaPA 1.4, controlli 00422 e 00423):

- PrezzoTotale di una riga = quantità × prezzo unitario, arrotondato a 2 decimali.
- Riepilogo per aliquota (o per natura, se l'IVA è 0): imponibile = somma dei
  PrezzoTotale delle righe con quell'aliquota + il contributo della cassa previdenziale
  con quell'aliquota; imposta = imponibile × aliquota / 100, arrotondata **una volta sola
  per aliquota** (non riga per riga).
- Ritenuta d'acconto: sulla somma delle righe con la ritenuta (più la cassa, se è soggetta),
  × aliquota della ritenuta. Non cambia il totale del documento: cambia quanto si paga.
- Bollo: 2 euro se le operazioni senza IVA (esenti, non imponibili, escluse, forfettario)
  superano 77,47 euro (art. 6 tab. A DPR 642/72; dal 2023 senza esenzione per i forfettari).
  Regola semplificata: non conta le esportazioni (N3.1–N3.4), il reverse charge (N6.x) e
  i fuori campo (N7), che il bollo non lo vogliono. Se `bollo_addebito` è acceso, i 2
  euro diventano una riga N1 a carico del cliente.
- Prezzi detti «IVA inclusa»: lo scorporo tiene 8 decimali nel prezzo unitario (il formato
  li ammette) così il totale torna quello detto.
- Totale del documento = imponibili + imposte (con la riga del bollo, se c'è); da pagare =
  totale − ritenuta.
"""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
SOGLIA_BOLLO = Decimal("77.47")
BOLLO = Decimal("2.00")
ALIQUOTE = (Decimal(4), Decimal(5), Decimal(10), Decimal(22))

# Nature ammesse dallo SdI dal 2021 (i codici generici N2, N3, N6 sono scartati)
NATURE = {
    "N1": "Escluso ex art. 15 DPR 633/72",
    "N2.1": "Non soggetta a IVA ai sensi degli artt. da 7 a 7-septies del DPR 633/72",
    "N2.2": "Operazione effettuata ai sensi dell'art. 1, commi da 54 a 89, della Legge "
            "190/2014 - Regime forfettario",
    "N3.1": "Non imponibile - esportazioni (art. 8 DPR 633/72)",
    "N3.2": "Non imponibile - cessioni intracomunitarie (art. 41 DL 331/93)",
    "N3.3": "Non imponibile - cessioni verso San Marino",
    "N3.4": "Non imponibile - operazioni assimilate alle cessioni all'esportazione",
    "N3.5": "Non imponibile - a seguito di dichiarazioni d'intento",
    "N3.6": "Non imponibile - altre operazioni che non concorrono alla formazione del plafond",
    "N4": "Esente ex art. 10 DPR 633/72",
    "N5": "Regime del margine / IVA non esposta in fattura",
    "N6.1": "Inversione contabile - cessione di rottami e altri materiali di recupero",
    "N6.2": "Inversione contabile - cessione di oro e argento",
    "N6.3": "Inversione contabile - subappalto nel settore edile",
    "N6.4": "Inversione contabile - cessione di fabbricati",
    "N6.5": "Inversione contabile - cessione di telefoni cellulari",
    "N6.6": "Inversione contabile - cessione di prodotti elettronici",
    "N6.7": "Inversione contabile - prestazioni comparto edile e settori connessi",
    "N6.8": "Inversione contabile - operazioni settore energetico",
    "N6.9": "Inversione contabile - altri casi",
    "N7": "IVA assolta in altro stato UE",
}
_SENZA_BOLLO = ("N3.1", "N3.2", "N3.3", "N3.4", "N6", "N7")


class DatiNonValidi(ValueError):
    """Dati della fattura che non vanno: `errori` sono frasi per la voce."""

    def __init__(self, errori: list[str]):
        self.errori = errori
        super().__init__("; ".join(errori))


def dec(x, nome: str = "valore") -> Decimal:
    """Un numero detto o scritto («1.200,50», «12.5», 800) come Decimal."""
    if isinstance(x, Decimal):
        return x
    if isinstance(x, bool) or x is None:
        raise DatiNonValidi([f"{nome}: manca il numero"])
    if isinstance(x, (int, float)):
        return Decimal(str(x))
    from ..documenti.formato import parse_number
    p = parse_number(str(x).replace("%", ""))
    if p is None:
        raise DatiNonValidi([f"{nome}: «{x}» non è un numero"])
    return Decimal(str(p[0]))


def r2(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def euro(x: Decimal, simbolo: bool = True) -> str:
    """1234.5 → «1.234,50 €»."""
    s = f"{r2(x):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{s} €" if simbolo else s


def euro_detto(x: Decimal) -> str:
    """Per la voce: «1.220 euro», «1.220,50 euro» (Piper legge bene le cifre)."""
    x = r2(x)
    if x == x.to_integral_value():
        return f"{int(x):,}".replace(",", ".") + " euro"
    return euro(x, False) + " euro"


def xml_num(x: Decimal, min_dec: int = 2, max_dec: int = 8) -> str:
    """Il numero per l'XML: punto decimale, da 2 a 8 decimali, senza zeri inutili."""
    q = x.quantize(Decimal(1).scaleb(-max_dec), rounding=ROUND_HALF_UP)
    s = f"{q:.{max_dec}f}".rstrip("0")
    whole, _, frac = s.partition(".")
    frac = frac.ljust(min_dec, "0")
    return f"{whole}.{frac}"


def chiave(riga: dict) -> tuple[Decimal, str]:
    return (riga["aliquota"], riga.get("natura") or "")


def prepara_righe(righe: list[dict], aliquota_predefinita, natura_predefinita: str = "",
                  iva_inclusa: bool = False, ritenuta_predefinita: bool = False) -> list[dict]:
    """Normalizza le righe dette: quantità (1 se non detta), prezzo unitario imponibile
    (scorporato se «IVA inclusa»), aliquota o natura, ritenuta. DatiNonValidi se qualcosa
    non va (descrizione vuota, prezzo mancante, aliquota che non esiste)."""
    errori, out = [], []
    if not righe:
        raise DatiNonValidi(["serve almeno una riga con descrizione e prezzo"])
    for i, r in enumerate(righe, 1):
        desc = str(r.get("descrizione") or "").strip()
        if not desc:
            errori.append(f"riga {i}: manca la descrizione")
            continue
        try:
            q = dec(r["quantita"], f"riga {i}, quantità") if r.get("quantita") not in (
                None, "") else Decimal(1)
            prezzo = dec(r.get("prezzo"), f"riga {i}, prezzo")
        except DatiNonValidi as e:
            errori.extend(e.errori)
            continue
        if q <= 0:
            errori.append(f"riga {i}: la quantità deve essere più di zero")
            continue
        natura = str(r.get("natura") or "").strip().upper()
        if r.get("aliquota") not in (None, ""):
            try:
                aliq = dec(r["aliquota"], f"riga {i}, aliquota")
            except DatiNonValidi as e:
                errori.extend(e.errori)
                continue
        elif natura:
            aliq = Decimal(0)
        else:
            aliq = dec(aliquota_predefinita, "aliquota") if aliquota_predefinita not in (
                None, "") else Decimal(0)
            natura = natura or (natura_predefinita if aliq == 0 else "")
        if aliq == 0:
            natura = natura or natura_predefinita
            if natura not in NATURE:
                errori.append(f"riga {i}: con l'IVA a zero serve la natura (per esempio N2.2 "
                              f"per il forfettario, N4 per le esenti)")
                continue
        else:
            if aliq not in ALIQUOTE:
                errori.append(f"riga {i}: l'IVA al {aliq} per cento non esiste (4, 5, 10 o 22)")
                continue
            natura = ""
        if iva_inclusa and aliq > 0:
            prezzo = (prezzo / (1 + aliq / 100)).quantize(Decimal("0.00000001"),
                                                          rounding=ROUND_HALF_UP)
        rit = r.get("ritenuta")
        out.append({"descrizione": desc[:1000], "quantita": q,
                    "unita": str(r.get("unita") or "").strip()[:10], "prezzo": prezzo,
                    "aliquota": aliq, "natura": natura,
                    "ritenuta": bool(ritenuta_predefinita if rit is None else rit)})
    if errori:
        raise DatiNonValidi(errori)
    return out


def calcola(righe: list[dict], ritenuta: dict | None = None, cassa: dict | None = None,
            bollo: str = "auto", bollo_addebito: bool = False,
            riferimenti: dict | None = None) -> dict:
    """I totali di un documento dalle righe preparate (prepara_righe).

    ritenuta: {"tipo": "RT01", "aliquota": 20, "causale": "A"} o None
    cassa: {"tipo": "TC22", "aliquota": 4, "aliquota_iva": 22, "natura": "",
            "ritenuta": False} o None
    bollo: "auto" (secondo la soglia), "si", "no"
    """
    righe = [dict(r) for r in righe]
    for r in righe:
        r["totale"] = r2(r["quantita"] * r["prezzo"])
    imponibile_righe = sum((r["totale"] for r in righe), Decimal(0))
    out_cassa = None
    if cassa:
        aliq_c = dec(cassa.get("aliquota"), "aliquota della cassa")
        base_c = imponibile_righe
        aliq_iva_c = dec(cassa["aliquota_iva"], "IVA della cassa") if cassa.get(
            "aliquota_iva") not in (None, "") else (righe[0]["aliquota"] if righe else
                                                    Decimal(0))
        natura_c = (cassa.get("natura") or (righe[0]["natura"] if righe and aliq_iva_c == 0
                                            else "")) if aliq_iva_c == 0 else ""
        out_cassa = {"tipo": cassa.get("tipo") or "TC22", "aliquota": aliq_c,
                     "imponibile": r2(base_c), "importo": r2(base_c * aliq_c / 100),
                     "aliquota_iva": aliq_iva_c, "natura": natura_c,
                     "ritenuta": bool(cassa.get("ritenuta"))}
    # Bollo: le operazioni senza IVA che lo vogliono
    senza_iva = sum((r["totale"] for r in righe
                     if r["aliquota"] == 0 and not r["natura"].startswith(_SENZA_BOLLO)),
                    Decimal(0))
    if out_cassa and out_cassa["aliquota_iva"] == 0 and \
            not out_cassa["natura"].startswith(_SENZA_BOLLO):
        senza_iva += out_cassa["importo"]
    dovuto = {"si": True, "no": False}.get(str(bollo).lower(), senza_iva > SOGLIA_BOLLO)
    if dovuto and bollo_addebito and not any(r.get("bollo") for r in righe):
        righe.append({"descrizione": "Imposta di bollo assolta in modo virtuale",
                      "quantita": Decimal(1), "unita": "", "prezzo": BOLLO, "aliquota":
                      Decimal(0), "natura": "N1", "ritenuta": False, "totale": BOLLO,
                      "bollo": True})
    riep: dict[tuple, dict] = {}
    for r in righe:
        k = chiave(r)
        e = riep.setdefault(k, {"aliquota": k[0], "natura": k[1], "imponibile": Decimal(0)})
        e["imponibile"] += r["totale"]
    if out_cassa:
        k = (out_cassa["aliquota_iva"], out_cassa["natura"])
        e = riep.setdefault(k, {"aliquota": k[0], "natura": k[1], "imponibile": Decimal(0)})
        e["imponibile"] += out_cassa["importo"]
    rif = dict(NATURE, **(riferimenti or {}))
    riepilogo = []
    # Dall'aliquota più alta; fra le nature la riga del bollo (N1) per ultima
    for k in sorted(riep, key=lambda k: (-k[0], k[1] == "N1", k[1])):
        e = riep[k]
        e["imponibile"] = r2(e["imponibile"])
        e["imposta"] = r2(e["imponibile"] * e["aliquota"] / 100)
        e["riferimento"] = rif.get(e["natura"], "") if e["natura"] else ""
        riepilogo.append(e)
    out_rit = None
    if ritenuta:
        aliq_r = dec(ritenuta.get("aliquota"), "aliquota della ritenuta")
        base = sum((r["totale"] for r in righe if r["ritenuta"]), Decimal(0))
        if out_cassa and out_cassa["ritenuta"]:
            base += out_cassa["importo"]
        if base > 0:
            out_rit = {"tipo": ritenuta.get("tipo") or "RT01", "aliquota": aliq_r,
                       "base": r2(base), "importo": r2(base * aliq_r / 100),
                       "causale": ritenuta.get("causale") or "A"}
    imponibile = sum((e["imponibile"] for e in riepilogo), Decimal(0))
    imposta = sum((e["imposta"] for e in riepilogo), Decimal(0))
    totale = r2(imponibile + imposta)
    return {"righe": righe, "riepilogo": riepilogo, "cassa": out_cassa, "ritenuta": out_rit,
            "bollo": BOLLO if dovuto else None, "bollo_addebitato": bool(dovuto and
                                                                          bollo_addebito),
            "imponibile": r2(imponibile), "imposta": r2(imposta), "totale": totale,
            "da_pagare": r2(totale - (out_rit["importo"] if out_rit else 0))}


def riassunto_detto(t: dict) -> str:
    """«imponibile 1.000 euro, IVA 220, ritenuta 200, totale 1.220 euro, da pagare 1.020»."""
    parti = []
    if t["imposta"] > 0:
        parti.append(f"imponibile {euro_detto(t['imponibile'])}")
        parti.append(f"IVA {euro_detto(t['imposta'])}")
    if t.get("cassa"):
        parti.append(f"cassa {euro_detto(t['cassa']['importo'])}")
    if t.get("bollo_addebitato"):
        parti.append("bollo 2 euro")
    parti.append(f"totale {euro_detto(t['totale'])}")
    if t.get("ritenuta"):
        parti.append(f"ritenuta {euro_detto(t['ritenuta']['importo'])}")
        parti.append(f"da pagare {euro_detto(t['da_pagare'])}")
    elif t.get("bollo") and not t.get("bollo_addebitato"):
        parti.append("con il bollo da 2 euro a tuo carico")
    return ", ".join(parti)


def serializza(x):
    """Decimal → str per il JSON del registro (e ritorno con dec)."""
    if isinstance(x, Decimal):
        return str(x)
    if isinstance(x, dict):
        return {k: serializza(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [serializza(v) for v in x]
    return x


__all__ = ["ALIQUOTE", "BOLLO", "DatiNonValidi", "NATURE", "SOGLIA_BOLLO", "calcola", "dec",
           "euro", "euro_detto", "prepara_righe", "r2", "riassunto_detto", "serializza",
           "xml_num"]
