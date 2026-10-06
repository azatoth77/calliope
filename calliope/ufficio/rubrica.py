"""
Rubrica di clienti, fornitori e contatti, in SQLite (stesso file della memoria).

- Ambito: «casa» (di tutta la famiglia, il predefinito: i clienti della ditta di casa) o
  personale (UserProfile.id: solo quella persona la vede e la cambia). Gli ospiti niente:
  i tool sono per i familiari, e il registro ricontrolla il livello.
- I dati fiscali si controllano nel codice (vincoli di forma, principio 10): partita IVA
  con la cifra di controllo, codice fiscale (16 caratteri con il carattere di controllo,
  oppure 11 cifre come una partita IVA), CAP di 5 cifre, provincia di 2 lettere, codice
  destinatario SdI di 7 caratteri. Cosa vuol dire la frase lo decide il modello (che
  estrae i campi), la forma la controlla il programma.
- La ricerca per nome confronta le forme ridotte (senza «srl», «spa», punteggiatura e
  maiuscole), poi le parole contenute, poi la somiglianza: «Rossi» trova «Rossi Srl»; con
  due candidati vicini chiede quale.
"""

import difflib
import re
import sqlite3
import threading
import time

from ..persistenza import apri_db, prepara_schema

CAMPI = ("tipo", "denominazione", "nome", "cognome", "partita_iva", "codice_fiscale",
         "indirizzo", "civico", "cap", "comune", "provincia", "nazione", "email", "pec",
         "codice_destinatario", "telefono", "note")
TIPI = ("cliente", "fornitore", "contatto")
CASA = "casa"

# Come si dicono i campi a voce (domande e conferme)
NOMI_CAMPI = {"denominazione": "la ragione sociale", "nome": "il nome", "cognome": "il cognome",
              "partita_iva": "la partita IVA", "codice_fiscale": "il codice fiscale",
              "indirizzo": "l'indirizzo", "civico": "il numero civico", "cap": "il CAP",
              "comune": "il comune", "provincia": "la provincia", "nazione": "la nazione",
              "email": "l'email", "pec": "la PEC", "codice_destinatario":
              "il codice destinatario", "telefono": "il telefono", "note": "le note",
              "tipo": "il tipo"}


# ─────────────────────────── controlli di forma ───────────────────────────

def solo_cifre(s) -> str:
    """«012 345 678 90», «IT01234567890» → «01234567890» (conversione della trascrizione)."""
    s = re.sub(r"[\s.\-/]", "", str(s or "")).upper()
    return s[2:] if s.startswith("IT") and len(s) == 13 else s


def partita_iva_ok(piva: str) -> bool:
    """Partita IVA italiana: 11 cifre con la cifra di controllo (algoritmo di Luhn
    dell'Agenzia delle Entrate)."""
    if not re.fullmatch(r"\d{11}", piva or ""):
        return False
    if piva == "0" * 11:
        return False
    s = 0
    for i, ch in enumerate(piva[:10]):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        s += d
    return (10 - s % 10) % 10 == int(piva[10])


_CF_DISPARI = {**{str(i): v for i, v in enumerate((1, 0, 5, 7, 9, 13, 15, 17, 19, 21))},
               **dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                          (1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14,
                           16, 10, 22, 25, 24, 23)))}


def codice_fiscale_ok(cf: str) -> bool:
    """Codice fiscale di una persona (16 caratteri, con il carattere di controllo; vale anche
    con le sostituzioni per omocodia) o di una società (11 cifre, come la partita IVA)."""
    cf = (cf or "").upper()
    if re.fullmatch(r"\d{11}", cf):
        return partita_iva_ok(cf)
    if not re.fullmatch(r"[A-Z]{6}[0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{2}[A-Z]"
                        r"[0-9LMNPQRSTUV]{3}[A-Z]", cf):
        return False
    s = 0
    for i, ch in enumerate(cf[:15]):
        if i % 2 == 0:
            s += _CF_DISPARI[ch]
        else:
            s += int(ch) if ch.isdigit() else ord(ch) - 65
    return chr(65 + s % 26) == cf[15]


def controlla(dati: dict) -> tuple[dict, dict]:
    """(campi normalizzati, errori {campo: frase}). Normalizza solo la forma: cifre senza
    spazi, maiuscole, provincia e nazione in sigla."""
    out, errori = {}, {}
    for k in CAMPI:
        v = dati.get(k)
        if v is None:
            continue
        v = re.sub(r"\s+", " ", str(v)).strip()
        if not v:
            continue
        out[k] = v
    if "tipo" in out:
        t = out["tipo"].lower()
        out["tipo"] = t if t in TIPI else ("fornitore" if t.startswith("fornit") else
                                           "cliente" if t.startswith("client") else "contatto")
    if "partita_iva" in out:
        p = solo_cifre(out["partita_iva"])
        out["partita_iva"] = p
        if not partita_iva_ok(p):
            errori["partita_iva"] = (f"la partita IVA {spaziata(p)} non torna (servono 11 "
                                     f"cifre con quella di controllo giusta)")
    if "codice_fiscale" in out:
        c = solo_cifre(out["codice_fiscale"])
        out["codice_fiscale"] = c
        if not codice_fiscale_ok(c):
            errori["codice_fiscale"] = f"il codice fiscale {spaziata(c)} non torna"
    if "cap" in out:
        c = solo_cifre(out["cap"])
        out["cap"] = c
        if not re.fullmatch(r"\d{5}", c) and out.get("nazione", "IT").upper() in ("IT",
                                                                                  "ITALIA"):
            errori["cap"] = f"il CAP {c} non va bene: servono 5 cifre"
    if "provincia" in out:
        p = out["provincia"].upper().strip(" ()")
        p = PROVINCE.get(p.lower(), p)
        out["provincia"] = p
        if not re.fullmatch(r"[A-Z]{2}", p):
            errori["provincia"] = f"la provincia «{out['provincia']}» va detta con la sigla"
    if "nazione" in out:
        n = out["nazione"].strip().upper()
        out["nazione"] = {"ITALIA": "IT", "ITALY": "IT"}.get(n, n)
        if not re.fullmatch(r"[A-Z]{2}", out["nazione"]):
            errori["nazione"] = "la nazione va detta con la sigla di due lettere"
    if "codice_destinatario" in out:
        c = solo_cifre(out["codice_destinatario"])
        out["codice_destinatario"] = c
        if not re.fullmatch(r"[A-Z0-9]{7}", c):
            errori["codice_destinatario"] = "il codice destinatario ha 7 caratteri"
    for k in ("email", "pec"):
        if k in out:
            e = out[k].replace(" chiocciola ", "@").replace(" punto ", ".").replace(" ", "")
            out[k] = e.lower()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", out[k]):
                errori[k] = f"{NOMI_CAMPI[k]} «{out[k]}» non sembra un indirizzo email"
    return out, errori


def spaziata(codice: str) -> str:
    """Un codice detto carattere per carattere («0 1 2 …»): letto come numero intero Piper
    direbbe «un miliardo…»."""
    return " ".join(str(codice or ""))


def nome_di(c: dict) -> str:
    if c.get("denominazione"):
        return c["denominazione"]
    return " ".join(x for x in (c.get("nome"), c.get("cognome")) if x) or "senza nome"


def mancanti_per_fattura(c: dict) -> list[str]:
    """I campi che servono a una fattura elettronica (FatturaPA, cessionario/committente)."""
    out = []
    if not (c.get("denominazione") or (c.get("nome") and c.get("cognome"))):
        out.append("denominazione")
    if not (c.get("partita_iva") or c.get("codice_fiscale")):
        out.append("partita_iva")
    for k in ("indirizzo", "cap", "comune"):
        if not c.get(k):
            out.append(k)
    if (c.get("nazione") or "IT") == "IT" and not c.get("provincia"):
        out.append("provincia")
    return out


_FORMA = re.compile(r"\b(s\.?\s?r\.?\s?l\.?s?|s\.?\s?p\.?\s?a\.?|s\.?\s?n\.?\s?c\.?|"
                    r"s\.?\s?a\.?\s?s\.?|soc(?:ietà)?\.?\s+coop(?:erativa)?|ditta|studio|"
                    r"dott(?:\.|ssa|or)?|sig(?:\.|nora|nor)?|ing\.?|avv\.?)\b", re.I)


def _norm(s: str) -> str:
    s = _FORMA.sub(" ", str(s or "").lower())
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class Rubrica:
    def __init__(self, path: str):
        self._lock = threading.Lock()
        self.db = apri_db(path)
        cols = ", ".join(f"{k} TEXT" for k in CAMPI)
        self.db.execute(f"""CREATE TABLE IF NOT EXISTS rubrica (
                               id INTEGER PRIMARY KEY,
                               ambito TEXT NOT NULL,         -- 'casa' o UserProfile.id
                               {cols},
                               autore TEXT,
                               creato REAL NOT NULL,
                               modificato REAL NOT NULL)""")
        self.db.commit()
        # Versione dello schema (03/10, persistenza.prepara_schema): la 1 è quello qui sopra;
        # le prossime si aggiungono in fondo all'elenco, solo colonne con NULL o un
        # predefinito. Dati di una versione più nuova: sola lettura
        self.scrivibile = prepara_schema(self.db, "rubrica", [lambda db: None])

    def _rows(self, where: str = "1", args=()) -> list[dict]:
        with self._lock:
            cur = self.db.execute(f"SELECT id, ambito, {', '.join(CAMPI)} FROM rubrica "
                                  f"WHERE {where} ORDER BY id", args)
            rows = cur.fetchall()
        out = []
        for r in rows:
            d = {k: v for k, v in zip(("id", "ambito", *CAMPI), r) if v not in (None, "")}
            d["nome_completo"] = nome_di(d)
            out.append(d)
        return out

    def visibili(self, owner: str) -> list[dict]:
        """Quelli della casa e quelli personali di `owner`."""
        return self._rows("ambito = ? OR ambito = ?", (CASA, owner))

    def get(self, cid: int, owner: str) -> dict | None:
        rows = self._rows("id = ? AND (ambito = ? OR ambito = ?)", (cid, CASA, owner))
        return rows[0] if rows else None

    def cerca(self, testo: str, owner: str, limite: int = 5) -> list[tuple[float, dict]]:
        """[(punteggio, contatto)] dal più vicino. Punteggio 1 = nome uguale (forma ridotta),
        0,95 = partita IVA o codice fiscale uguale, 0,9 = tutte le parole dette nel nome."""
        q = _norm(testo)
        cod = solo_cifre(testo)
        if not q and not cod:
            return []
        out = []
        for c in self.visibili(owner):
            n = _norm(c["nome_completo"])
            if cod and cod in (c.get("partita_iva"), c.get("codice_fiscale")):
                s = 0.95
            elif q and q == n:
                s = 1.0
            elif q and set(q.split()) <= set(n.split()):
                s = 0.9
            else:
                s = difflib.SequenceMatcher(None, q, n).ratio() if q else 0.0
                if q and n.startswith(q) and len(q) >= 3:
                    s = max(s, 0.85)
            if s >= 0.6:
                out.append((round(s, 3), c))
        out.sort(key=lambda x: -x[0])
        return out[:limite]

    def trova(self, testo: str, owner: str) -> tuple[dict | None, list[dict]]:
        """(contatto sicuro, alternative). Sicuro: uno solo sopra 0,85 o il primo staccato
        di almeno 0,1 dal secondo; altrimenti None e i candidati da proporre."""
        res = self.cerca(testo, owner)
        if not res:
            return None, []
        if res[0][0] >= 0.85 and (len(res) == 1 or res[0][0] - res[1][0] >= 0.1):
            return res[0][1], []
        if res[0][0] >= 0.85 or len(res) > 1:
            return None, [c for s, c in res if s >= 0.75][:3] or [res[0][1]]
        return None, [res[0][1]]

    def aggiungi(self, dati: dict, ambito: str, autore: str | None) -> int:
        dati, err = controlla(dati)
        if err:
            raise ValueError("; ".join(err.values()))
        now = time.time()
        keys = [k for k in CAMPI if k in dati]
        with self._lock:
            cur = self.db.execute(
                f"INSERT INTO rubrica (ambito, {', '.join(keys)}, autore, creato, modificato) "
                f"VALUES (?, {', '.join('?' * len(keys))}, ?, ?, ?)",
                (ambito, *[dati[k] for k in keys], autore, now, now))
            self.db.commit()
        return cur.lastrowid

    def modifica(self, cid: int, dati: dict, owner: str) -> dict:
        if self.get(cid, owner) is None:
            raise ValueError("contatto non trovato")
        dati, err = controlla(dati)
        if err:
            raise ValueError("; ".join(err.values()))
        keys = [k for k in CAMPI if k in dati]
        if keys:
            with self._lock:
                self.db.execute(f"UPDATE rubrica SET {', '.join(f'{k} = ?' for k in keys)}, "
                                f"modificato = ? WHERE id = ?",
                                (*[dati[k] for k in keys], time.time(), cid))
                self.db.commit()
        return self.get(cid, owner)

    def elimina(self, cid: int, owner: str) -> bool:
        if self.get(cid, owner) is None:
            return False
        with self._lock:
            self.db.execute("DELETE FROM rubrica WHERE id = ?", (cid,))
            self.db.commit()
        return True

    def duplicato(self, dati: dict, owner: str) -> dict | None:
        """Un contatto già presente con la stessa partita IVA, lo stesso codice fiscale o lo
        stesso nome (forma ridotta)."""
        n = _norm(nome_di(dati)) if (dati.get("denominazione") or dati.get("nome")) else ""
        for c in self.visibili(owner):
            if dati.get("partita_iva") and dati["partita_iva"] == c.get("partita_iva"):
                return c
            if dati.get("codice_fiscale") and dati["codice_fiscale"] == c.get("codice_fiscale"):
                return c
            if n and n == _norm(c["nome_completo"]):
                return c
        return None


def descrivi(c: dict, completo: bool = True) -> str:
    """Il contatto detto a voce: «Rossi Srl, cliente, partita IVA 0 1 2…, via Roma 3, 20121
    Milano (MI)». I codici lettera per lettera."""
    parti = [nome_di(c)]
    if c.get("tipo"):
        parti.append(c["tipo"])
    if completo:
        if c.get("partita_iva"):
            parti.append(f"partita IVA {spaziata(c['partita_iva'])}")
        elif c.get("codice_fiscale"):
            parti.append(f"codice fiscale {spaziata(c['codice_fiscale'])}")
    via = " ".join(x for x in (c.get("indirizzo"), c.get("civico")) if x)
    luogo = " ".join(x for x in (c.get("cap"), c.get("comune")) if x)
    if c.get("provincia") and luogo:
        luogo += f" ({c['provincia']})"
    if completo and via:
        parti.append(via)
    if luogo:
        parti.append(luogo)
    if completo:
        for k, detto in (("email", "email"), ("pec", "PEC"), ("telefono", "telefono"),
                         ("codice_destinatario", "codice destinatario")):
            if c.get(k):
                v = spaziata(c[k]) if k == "codice_destinatario" else c[k]
                parti.append(f"{detto} {v}")
    return ", ".join(parti)


# Province: dal nome alla sigla (le più dette; la sigla detta vale sempre)
PROVINCE = {
    "agrigento": "AG", "alessandria": "AL", "ancona": "AN", "aosta": "AO", "arezzo": "AR",
    "ascoli piceno": "AP", "asti": "AT", "avellino": "AV", "bari": "BA", "barletta": "BT",
    "belluno": "BL", "benevento": "BN", "bergamo": "BG", "biella": "BI", "bologna": "BO",
    "bolzano": "BZ", "brescia": "BS", "brindisi": "BR", "cagliari": "CA", "caltanissetta": "CL",
    "campobasso": "CB", "caserta": "CE", "catania": "CT", "catanzaro": "CZ", "chieti": "CH",
    "como": "CO", "cosenza": "CS", "cremona": "CR", "crotone": "KR", "cuneo": "CN",
    "enna": "EN", "fermo": "FM", "ferrara": "FE", "firenze": "FI", "foggia": "FG",
    "forlì": "FC", "forli": "FC", "frosinone": "FR", "genova": "GE", "gorizia": "GO",
    "grosseto": "GR", "imperia": "IM", "isernia": "IS", "l'aquila": "AQ", "aquila": "AQ",
    "la spezia": "SP", "latina": "LT", "lecce": "LE", "lecco": "LC", "livorno": "LI",
    "lodi": "LO", "lucca": "LU", "macerata": "MC", "mantova": "MN", "massa": "MS",
    "matera": "MT", "messina": "ME", "milano": "MI", "modena": "MO", "monza": "MB",
    "napoli": "NA", "novara": "NO", "nuoro": "NU", "oristano": "OR", "padova": "PD",
    "palermo": "PA", "parma": "PR", "pavia": "PV", "perugia": "PG", "pesaro": "PU",
    "pescara": "PE", "piacenza": "PC", "pisa": "PI", "pistoia": "PT", "pordenone": "PN",
    "potenza": "PZ", "prato": "PO", "ragusa": "RG", "ravenna": "RA", "reggio calabria": "RC",
    "reggio emilia": "RE", "rieti": "RI", "rimini": "RN", "roma": "RM", "rovigo": "RO",
    "salerno": "SA", "sassari": "SS", "savona": "SV", "siena": "SI", "siracusa": "SR",
    "sondrio": "SO", "sud sardegna": "SU", "taranto": "TA", "teramo": "TE", "terni": "TR",
    "torino": "TO", "trapani": "TP", "trento": "TN", "treviso": "TV", "trieste": "TS",
    "udine": "UD", "varese": "VA", "venezia": "VE", "verbania": "VB", "vercelli": "VC",
    "verona": "VR", "vibo valentia": "VV", "vicenza": "VI", "viterbo": "VT"}
