"""La verità dei contenuti della libreria dello Studio (31/10, issue #297; calliope/studio/libreria/).

Una tabella degli elementi e i conti scritti qui, a parte dai contenuti e dal codice di Calliope:
la prova di verità (`prova_studio_libreria.py`) rifà ogni `calcolo` dichiarato in una scheda o in
una carta e controlla che il risultato scritto nel testo sia quello giusto. Si usa anche da sola,
mentre si scrive un contenuto (`prove/manuali/libreria-studio.md`):

    python prove/verita_libreria.py            # tutti i contenuti, con gli errori
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI.parent))

# Simbolo → (Z, massa atomica in u), dalle tavole di uso scolastico
ELEMENTI = {
    "H": (1, 1.008), "He": (2, 4.003), "Li": (3, 6.94), "Be": (4, 9.012), "B": (5, 10.81),
    "C": (6, 12.011), "N": (7, 14.007), "O": (8, 15.999), "F": (9, 18.998), "Ne": (10, 20.180),
    "Na": (11, 22.990), "Mg": (12, 24.305), "Al": (13, 26.982), "Si": (14, 28.085),
    "P": (15, 30.974), "S": (16, 32.06), "Cl": (17, 35.45), "Ar": (18, 39.948), "K": (19, 39.098),
    "Ca": (20, 40.078), "Fe": (26, 55.845), "Cu": (29, 63.546), "Zn": (30, 65.38),
    "Ag": (47, 107.87), "I": (53, 126.90), "Au": (79, 196.97), "Pb": (82, 207.2),
}
# Tolleranza dei conti: i contenuti usano le masse arrotondate della scuola (H 1, C 12, Cl 35,5)
TOLLERANZA = 0.015

# Le unità per grandezza, col fattore verso l'unità di base
UNITA = {
    "lunghezza": {"km": 1e3, "hm": 1e2, "dam": 1e1, "m": 1.0, "dm": 1e-1, "cm": 1e-2, "mm": 1e-3,
                  "um": 1e-6, "nm": 1e-9},
    "massa": {"t": 1e3, "kg": 1.0, "hg": 1e-1, "dag": 1e-2, "g": 1e-3, "dg": 1e-4, "cg": 1e-5,
              "mg": 1e-6},
    "volume": {"m3": 1.0, "dm3": 1e-3, "L": 1e-3, "dL": 1e-4, "cL": 1e-5, "mL": 1e-6,
               "cm3": 1e-6, "mm3": 1e-9},
    "superficie": {"km2": 1e6, "m2": 1.0, "dm2": 1e-2, "cm2": 1e-4, "mm2": 1e-6},
    "tempo": {"h": 3600.0, "min": 60.0, "s": 1.0, "ms": 1e-3},
    "velocita": {"m/s": 1.0, "km/h": 1000 / 3600},
    "densita": {"kg/m3": 1.0, "g/cm3": 1000.0, "g/mL": 1000.0, "kg/L": 1000.0, "g/L": 1.0},
    "informazione": {"bit": 1.0, "B": 8.0, "kB": 8e3, "MB": 8e6, "GB": 8e9, "TB": 8e12,
                     "KiB": 8 * 1024.0, "MiB": 8 * 1024.0 ** 2, "GiB": 8 * 1024.0 ** 3},
    "temperatura": {},
}


class NonSo(ValueError):
    """Un calcolo con dati che la prova non sa leggere."""


def formula_in_atomi(f: str) -> dict:
    """«Ca(OH)2» → {Ca: 1, O: 2, H: 2}."""
    pila = [{}]
    i = 0
    while i < len(f):
        c = f[i]
        if c == "(":
            pila.append({})
            i += 1
        elif c == ")":
            i += 1
            m = re.match(r"\d+", f[i:])
            k = int(m.group()) if m else 1
            i += len(m.group()) if m else 0
            dentro = pila.pop()
            for el, n in dentro.items():
                pila[-1][el] = pila[-1].get(el, 0) + n * k
        else:
            m = re.match(r"([A-Z][a-z]?)(\d*)", f[i:])
            if not m or m.group(1) not in ELEMENTI:
                raise NonSo(f"formula «{f}»")
            el, k = m.group(1), int(m.group(2) or 1)
            pila[-1][el] = pila[-1].get(el, 0) + k
            i += len(m.group())
    if len(pila) != 1:
        raise NonSo(f"parentesi in «{f}»")
    return pila[0]


def massa_molare(f: str) -> float:
    return sum(ELEMENTI[el][1] * n for el, n in formula_in_atomi(f).items())


def _lato(lato: str) -> dict:
    tot: dict = {}
    for pezzo in lato.split("+"):
        m = re.match(r"\s*(\d*)\s*([A-Za-z0-9()]+)\s*$", pezzo)
        if not m:
            raise NonSo(f"reazione «{lato}»")
        k = int(m.group(1) or 1)
        for el, n in formula_in_atomi(m.group(2)).items():
            tot[el] = tot.get(el, 0) + k * n
    return tot


def bilanciata(reazione: str) -> bool:
    if "->" not in reazione:
        raise NonSo("la reazione vuole «->»")
    a, b = reazione.split("->")
    return _lato(a) == _lato(b)


def livelli(z: int) -> list[int]:
    """Gli elettroni per livello coi soli 2, 8, 8, 2 dei primi venti elementi."""
    if not 1 <= z <= 20:
        raise NonSo("livelli solo per Z da 1 a 20")
    out, resta = [], z
    for cap in (2, 8, 8, 2):
        if resta <= 0:
            break
        out.append(min(cap, resta))
        resta -= cap
    return out


def converti(valore: float, da: str, a: str) -> float:
    for g, u in UNITA.items():
        if da in u and a in u:
            return valore * u[da] / u[a]
    raise NonSo(f"unità «{da}» e «{a}»")


def _num(x) -> float:
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    raise NonSo(f"numero «{x}»")


def calcola(formula: str, d: dict):
    """Il risultato vero di un calcolo dichiarato: un numero, un testo («1011», «2-8-1») o un
    booleano (bilanciata)."""
    def M():
        return _num(d["M"]) if "M" in d else massa_molare(d["formula"])
    if formula == "densita":
        return _num(d["m"]) / _num(d["V"])
    if formula == "massa_da_densita":
        return _num(d["d"]) * _num(d["V"])
    if formula == "volume_da_densita":
        return _num(d["m"]) / _num(d["d"])
    if formula == "velocita":
        return _num(d["s"]) / _num(d["t"])
    if formula == "spazio":
        return _num(d["v"]) * _num(d["t"])
    if formula == "tempo":
        return _num(d["s"]) / _num(d["v"])
    if formula == "moli":
        return _num(d["m"]) / M()
    if formula == "massa_da_moli":
        return _num(d["n"]) * M()
    if formula == "massa_molare":
        return massa_molare(d["formula"])
    if formula == "conversione":
        return converti(_num(d["valore"]), d["da"], d["a"])
    if formula == "binario_in_decimale":
        return int(str(d["binario"]), 2)
    if formula == "decimale_in_binario":
        return bin(int(d["decimale"]))[2:]
    if formula == "esadecimale_in_decimale":
        return int(str(d["esadecimale"]), 16)
    if formula == "neutroni":
        return int(d["A"]) - int(d["Z"])
    if formula == "ph":
        return -math.log10(_num(d["H"]))
    if formula == "bilanciata":
        return bilanciata(d["reazione"])
    if formula == "elettroni_per_livello":
        lv = livelli(int(d["Z"]))
        if "livello" in d:
            return lv[int(d["livello"]) - 1] if int(d["livello"]) <= len(lv) else 0
        return "-".join(str(x) for x in lv)
    if formula == "notazione_scientifica":
        return _num(d["valore"])
    if formula == "byte_in_bit":
        return _num(d["byte"]) * 8
    raise NonSo(f"formula «{formula}»")


_NUMERI = re.compile(r"(?<![\w,.])-?\d+(?:[.,]\d+)?(?:\s?[×x]\s?10\^?\s?-?\d+)?")


def numeri_nel_testo(testo: str) -> list[float]:
    """I numeri scritti in un testo, con la virgola o il punto decimale, anche «4,2 × 10^-4»."""
    out = []
    for m in _NUMERI.finditer(str(testo)):
        t = m.group().replace(" ", "")
        esp = 0
        if "10" in t and ("×" in t or "x" in t):
            base, _, e = re.split(r"([×x])", t, maxsplit=1)
            t = base
            esp = int(e.replace("10", "", 1).replace("^", "") or 0)
        try:
            out.append(float(t.replace(",", ".")) * 10 ** esp)
        except ValueError:
            continue
    return out


def vicino(a: float, b: float) -> bool:
    return abs(a - b) <= max(abs(b) * TOLLERANZA, 1e-9)


def controlla_calcolo(calcolo: dict, testo: str) -> list[str]:
    """Gli errori di un calcolo: il risultato dichiarato contro quello vero, e il risultato scritto
    nel testo che lo accompagna (l'esempio, la risposta)."""
    try:
        vero = calcola(calcolo["formula"], calcolo["dati"])
    except (NonSo, KeyError, ValueError, ZeroDivisionError) as ex:
        return [f"non so rifare il calcolo: {ex}"]
    dich = calcolo["risultato"]
    f = calcolo["formula"]
    if isinstance(vero, bool):
        atteso = "bilanciata" if vero else "non bilanciata"
        return [] if dich == atteso else [f"risultato «{dich}», il vero è «{atteso}»"]
    if isinstance(vero, str):
        if str(dich) != vero:
            return [f"risultato «{dich}», il vero è «{vero}»"]
        if f == "elettroni_per_livello":
            cifre = [int(x) for x in vero.split("-")]
            nel = [int(x) for x in re.findall(r"\d+", testo)]
            # Le cifre dei livelli, nell'ordine, dentro i numeri del testo
            it = iter(nel)
            if not all(any(c == x for x in it) for c in cifre):
                return [f"nel testo non trovo {vero} nell'ordine"]
            return []
        return [] if vero in re.sub(r"\s", "", testo) else [f"nel testo non trovo «{vero}»"]
    try:
        d = float(dich)
    except (TypeError, ValueError):
        return [f"risultato «{dich}» non è un numero"]
    err = []
    if not vicino(d, vero):
        err.append(f"risultato {dich}, il vero è {vero:.6g}")
    if f == "notazione_scientifica":
        return err
    if not any(vicino(x, d) for x in numeri_nel_testo(testo)):
        err.append(f"nel testo non trovo il risultato {dich}")
    return err


def contenuti():
    """(nome del file, dati) di tutti i file JSON della libreria, anche quelli che non vanno."""
    import json
    from calliope.studio.libreria import formato as F
    for p in sorted(F.CARTELLA.rglob("*.json")):
        try:
            yield p.relative_to(F.CARTELLA).as_posix(), json.loads(p.read_text("utf-8"))
        except ValueError as ex:
            yield p.relative_to(F.CARTELLA).as_posix(), {"_errore": str(ex)}


def errori_di_verita(lib) -> list[str]:
    """Tutti gli errori di verità della libreria caricata (`indice.Libreria`):
    - ogni calcolo dichiarato, rifatto qui;
    - ogni carta con la risposta chiusa: la risposta detta è giusta per il codice delle carte, la
      «sbagliata» (obbligatoria per le risposte chiuse) no;
    - ogni risposta chiusa che non è un calcolo sta nella sua scheda (le stesse parole)."""
    from calliope.studio import carte as C
    from calliope.studio.libreria import formato as F
    out = []
    for cid, v in sorted(lib.contenuti.items()):
        if v["tipo"] == F.SCHEDA:
            s = v["scheda"]
            for i, e in enumerate(s.get("esempi", [])):
                if e.get("calcolo"):
                    out += [f"{cid} esempi[{i}]: {x}" for x in controlla_calcolo(e["calcolo"],
                                                                                 e["testo"])]
            for i, q in enumerate(s.get("prova_tu", [])):
                if q.get("calcolo"):
                    out += [f"{cid} prova_tu[{i}]: {x}" for x in controlla_calcolo(
                        q["calcolo"], q["risposta"])]
        elif v["tipo"] == F.MAZZO:
            sc = lib.contenuti[v["scheda"]]["scheda"]
            testo_scheda = " ".join([sc["introduzione"]] + [x["titolo"] + " " + x["testo"]
                                                           for x in sc["sezioni"]]
                                    + sc["ricorda"] + [x["testo"] for x in sc.get("esempi", [])]
                                    + sc.get("errori", [])
                                    + [x["domanda"] + " " + x["risposta"]
                                       for x in sc.get("prova_tu", [])])
            # I gettoni della forma chiusa (#361: i numeri restano numeri, «#2»), non le parole
            # di `normale` (i numeri in lettere)
            parole_scheda = set(C._gettoni(testo_scheda))
            for i, c in enumerate(v["carte"]):
                dove = f"{cid} carte[{i}]"
                if c.get("calcolo"):
                    out += [f"{dove}: {x}" for x in controlla_calcolo(c["calcolo"], c["risposta"])]
                ch = C.chiusa(c["risposta"])
                if ch is None:
                    continue
                if not C.risposta_giusta(ch, c["risposta"]):
                    out.append(f"{dove}: la risposta detta così non è giusta per il codice")
                if "sbagliata" not in c:
                    out.append(f"{dove}: una risposta chiusa vuole la «sbagliata» tipica")
                elif C.risposta_giusta(ch, c["sbagliata"]):
                    out.append(f"{dove}: la «sbagliata» vale giusta per il codice")
                if not c.get("calcolo") and not set(ch.split()) <= parole_scheda:
                    out.append(f"{dove}: «{c['risposta']}» non sta nella scheda")
    return out


def main() -> int:
    from calliope.studio.libreria import Libreria
    lib = Libreria.carica()
    err = lib.errori + errori_di_verita(lib)
    for e in err:
        print("ERR", e)
    print(f"{len(lib)} contenuti, {len(err)} errori")
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main())
