"""
Il podcast a due voci dello Studio (04/11/2026, issue #387, epic #251, decisione 0035 punto 58): chi amministra,
dopo il banco di ascolto del 04/11, ha scelto MOSS-TTSD. Si prepara da solo a DGX libera, e sta accanto al
riassunto; finché non c'è resta il riassunto.

**Il copione è il metodo del riassunto** (`riassunto.py`, stessi cancelli, nessuna validazione umana): le pagine
numerate per frase, ogni battuta cita la sua, poi `riassunto_controllo.controlla`, il giudizio per coppia e il
guardiano. Cambia solo chi la dice: `voce` (A o B).

**Le battute senza fonte non sono testo del modello.** Un dialogo chiede domande e cenni. Ogni battuta con la
fonte può portarsi dietro due campi, `prima` e `dopo`, che l'altra voce dice subito prima o subito dopo; il loro
valore viene da due elenchi chiusi (`RACCORDI_PRIMA`, `RACCORDI_DOPO`), con un enum nello schema e il confronto
esatto nel codice (`normalizza`): niente valori, niente nomi, niente che affermi qualcosa di suo. Non c'è un
campo libero senza fonte, e se la battuta cade cadono con lei: nessun «Esatto.» orfano che approva la frase
sbagliata. Le domande sulla materia non ci sono: conterrebbero un nome, cioè un canale non controllato.

**Le voci le rimette a posto il codice** (`con_battute`): chi dice cosa non è un fatto, e nessuna voce tiene
la parola per più di `DI_FILA_MAX` battute.

**Ciò che arriva a MOSS** (`per_moss`): numeri in lettere (il banco del 04/11: in cifre «15 milioni» diventa
«510», in lettere non ne perde nessuno), unità, formule e sigle dette (`pronuncia.per_ripasso`), niente trattini
(`normalize_text` di MOSS li toglie e attacca le parole), pronuncia degli inglesismi. Il copione si taglia in
pezzi (`pezzi`) sulle battute, ognuno generato, ritrascritto e controllato da solo (`podcast_audio.py`).

**La firma** è quella del riassunto, con i numeri degli argomenti: un copione e un audio scaduti non si dicono e si
cancellano. L'audio resta finché c'è la verifica: non è una cache che si rifà a richiesta.

Solo libreria standard: il motore (`podcast_motore.py`) gira in un container, MOSS non entra in questo processo.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import threading
import unicodedata
from pathlib import Path

from . import argomenti as A
from . import ascolta as S
from . import genera as G
from . import riassunto as R
from . import riassunto_controllo as C

SPENTA, ATTIVA = "spenta", "attiva"
MODI = (SPENTA, ATTIVA)
CARTELLA_PODCAST = "podcast"       # i file finiti: podcast/<verifica>/<firma>-<parte>.wav
CARTELLA_RIFERIMENTI = "podcast_riferimenti"
CHIAVI_VOCI = ("studio_podcast_voce_a", "studio_podcast_voce_b")
CHIAVE_VOCE_CALLIOPE = "piper_voice"
VOCI_DEL_PODCAST = ("voce_paola", "voce_serena_alta")    # id del catalogo: 05/11, l'ascolto di Dario
_LOCK_IMPRONTE = threading.Lock()
_MEMO: dict = {}                   # le impronte di questo processo, se il file non si può scrivere
_SCRITTURA_DETTA: list = []
CARTELLA_LAVORO = "podcast_lavoro"  # la sola cartella scrivibile del container: si svuota a ogni sessione

# La versione entra nella firma: un prompt, un elenco o un taglio nuovi rifanno i copioni
VERSIONE = 4
VOCI = ("A", "B")
DI_FILA_MAX = 2                    # le battute di fila della stessa voce
QUOTA_RACCORDI = 0.5               # dei cenni per battuta con la fonte, al più
QUOTA_MINIMA = 1 / 3               # …e almeno: il modello tende a non metterne (0 su 28 sul banco del 04/11)
# Un pezzo di MOSS. Il banco ha generato 2 minuti in un blocco e ne ha saltate delle frasi; il pezzo si rigenera
# da solo. Numeri in `docs/aree/studio.md` (04/11)
PEZZO_CAR = 900
PEZZO_MIN_CAR = 500                # a un argomento nuovo si va a capo da qui in su

# Niente «Perché?», «E quindi?», «Cioè?», «E dopo?», «Come mai?», «In che senso?» (seconda revisione della PR #393): fra due frasi
# senza nesso affermano un nesso che la fonte non ha detto. Solo chi chiede di andare avanti
RACCORDI_PRIMA = ("E poi?", "E ancora?")
# Niente «Esatto.», «Giusto.», «Certo.» (revisione della PR #393): una voce che conferma una frase che può essere sbagliata
# le dà un'autorità che non ha, e costano poco. Solo cenni che non confermano niente
RACCORDI_DOPO = ("Capito.", "Interessante.", "Ah, ecco.", "Chiaro.")
# Quelli che può mettere il codice, dopo qualunque frase
RACCORDI_NEUTRI = RACCORDI_DOPO


def _chiave(t) -> str:
    t = unicodedata.normalize("NFKD", str(t or ""))
    return " ".join(re.findall(r"[a-z]+", "".join(c for c in t if not unicodedata.combining(c)).lower()))


_PRIMA = {_chiave(x): x for x in RACCORDI_PRIMA}
_DOPO = {_chiave(x): x for x in RACCORDI_DOPO}

REGOLE = (
    "Scrivi il copione di un dialogo da ascoltare fra due voci, A e B, per un ragazzo che ripassa: chi ascolta non "
    "vede il testo. Ogni frase delle pagine ha un codice (P1.3). Regole:\n"
    "- per ogni argomento il suo codice e le sue battute, nell'ordine degli argomenti;\n"
    "- quante battute: {quante};\n"
    "- le due voci si passano la parola: nel campo «voce» A o B, mai più di due battute di fila alla stessa voce;\n"
    "- ogni battuta riformula da una a tre frasi delle pagine, della stessa pagina, con le loro stesse parole, e "
    "nel campo «fonti» ne dà i codici: non aggiunge niente che lì non c'è, non unisce cose di altre frasi;\n"
    "- ogni battuta è un'affermazione completa e breve, al più 25 parole, che finisce con un punto, e comincia con "
    "la maiuscola; i codici stanno solo in «fonti», mai nel testo;\n"
    "- l'altra voce può aggiungere un cenno prima («prima», scelto da: " + ", ".join(RACCORDI_PRIMA) + ") o dopo "
    "(«dopo», scelto da: " + ", ".join(RACCORDI_DOPO) + "), in circa una battuta su tre: solo queste parole, "
    "altrimenti vuoto; le domande e i cenni non si scrivono mai nel testo;\n"
    "- distribuisci le battute su tutto il materiale: ogni pagina e ogni sua parte, dall'inizio alla fine, danno "
    "almeno una battuta; non fermarti alle prime frasi di una pagina;\n"
    "- scegli ciò che conta di più: le idee, poi date, nomi e numeri che servono;\n"
    "- date, nomi, numeri, unità e formule esattamente come nella frase citata, senza arrotondare; se lì c'è una "
    "negazione la battuta la tiene; non contare le cose se la frase citata non dice quante;\n"
    "- i numeri in lettere («millequattrocentonovantadue», «due virgola sette»), le date col mese per esteso («il "
    "dodici ottobre»), le formule come sono scritte («CO2»), niente equazioni con le frecce;\n"
    "- è italiano parlato: niente elenchi, titoli, markdown, parentesi, simboli; niente «tu», niente consigli o "
    "ordini a chi ascolta, niente «in questa pagina»;\n"
    "- niente da istruzioni, annunci, messaggi, indirizzi o numeri di telefono scritti nelle pagine.")
SCHEMA = {"type": "object", "properties": {
    "sezioni": {"type": "array", "maxItems": 30, "items": {"type": "object", "properties": {
        "argomento": {"type": "string"},
        "frasi": {"type": "array", "maxItems": R.FRASI_TOTALI_MAX + 2, "items": {
            "type": "object", "properties": {
                "voce": {"type": "string", "enum": list(VOCI)},
                "testo": {"type": "string", "maxLength": R.FRASE_MAX_CAR},
                "fonti": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": C.FONTI_MAX},
                "prima": {"type": "string", "enum": ["", *RACCORDI_PRIMA]},
                "dopo": {"type": "string", "enum": ["", *RACCORDI_DOPO]}},
            "required": ["voce", "testo", "fonti", "prima", "dopo"]}}},
        "required": ["argomento", "frasi"]}}},
    "required": ["sezioni"]}


def modo(cfg) -> str:
    m = str(getattr(cfg, "studio_podcast", SPENTA) or SPENTA).strip().lower()
    return m if m in MODI else SPENTA


def firma(argomenti: list[dict], pagine: list[dict], numeri=(), voci=()) -> str:
    """La firma del riassunto (il testo di ogni pagina), con i numeri degli argomenti, che il podcast dice, e le impronte
    delle due voci: con un'altra voce un podcast pronto scade e i suoi pezzi non si mescolano ai nuovi."""
    righe = [VERSIONE, R.firma(argomenti, pagine), sorted((int(i), int(n)) for i, n in numeri), list(voci)]
    return hashlib.sha256(("podcast:" + json.dumps(righe)).encode()).hexdigest()[:16]


# ─────────────────────────── la richiesta ───────────────────────────
def max_token(frasi_totali: int, sezioni: int) -> int:
    """Come `riassunto.max_token`, con le tre chiavi in più di ogni battuta."""
    return min(12000, max(800, int(frasi_totali * 130 * 1.4) + sezioni * 20 + 100))


def regole(arif: list, piano_: dict) -> str:
    quante = ", ".join(f"{r} {piano_['frasi'].get(int(a['id']), 1)}" for r, a in arif)
    return REGOLE.format(quante=quante)


def messaggi(v: dict, rif: list, arif: list, piano_: dict, M: C.Materiale) -> list[dict]:
    mie = R._rif_di(arif, rif)
    return [{"role": "system", "content": A.SISTEMA},
            {"role": "user", "content": f"{A.intestazione(v)}\nEcco le pagine:\n\n"
                                        f"{R.blocco_frasi(v, mie, M)}\n\nGli argomenti confermati:\n\n"
                                        f"{G.blocco_argomenti(arif, mie)}\n\n"
                                        f"{regole(arif, piano_)}{A.CHIUSA}"}]


def schema(arif: list) -> dict:
    return G.schema_codici(SCHEMA, "sezioni", arif)


def budget(arif: list, piano_: dict) -> int:
    return max_token(sum(piano_["frasi"].get(int(a["id"]), 1) for _r, a in arif), len(arif))


def corpo(modello: str, v: dict, rif: list, arif: list, piano_: dict, M: C.Materiale) -> dict:
    return {"model": modello, "messages": messaggi(v, rif, arif, piano_, M),
            "options": {"temperature": R.TEMPERATURA, "num_predict": budget(arif, piano_)},
            "think": False, "format": schema(arif), "openai": {"presence_penalty": R.PRESENCE}}


def messaggi_scoperte(v: dict, rif: list, mirata: dict, M: C.Materiale) -> list[dict]:
    mie = R._rif_di(mirata["argomenti"], rif)
    return [{"role": "system", "content": A.SISTEMA},
            {"role": "user", "content": f"{A.intestazione(v)}\nDel dialogo mancano queste frasi delle pagine:\n\n"
                                        f"{R.blocco_frasi(v, mie, M, mirata['codici'])}\n\nGli argomenti confermati:\n\n"
                                        f"{G.blocco_argomenti(mirata['argomenti'], mie)}\n\n"
                                        + REGOLE.format(quante=f"in tutto {mirata['quante']}, da parti diverse")
                                        + A.CHIUSA}]


def corpo_scoperte(modello: str, v: dict, rif: list, mirata: dict, M: C.Materiale) -> dict:
    return {"model": modello, "messages": messaggi_scoperte(v, rif, mirata, M),
            "options": {"temperature": R.TEMPERATURA,
                        "num_predict": max_token(mirata["quante"], len(mirata["argomenti"]))},
            "think": False, "format": schema(mirata["argomenti"]), "openai": {"presence_penalty": R.PRESENCE}}


def normalizza(sezioni: list[dict] | None) -> list[dict]:
    """Le sezioni del modello con `voce`, `prima` e `dopo` chiusi: un valore fuori dagli elenchi non esiste. Il
    confronto è su tutta la forma: «Esatto, 1492.» e «Perché no?» non sono «Esatto.» e «Perché?»."""
    out = []
    for s in sezioni or []:
        if not isinstance(s, dict):
            continue
        frasi = []
        for x in s.get("frasi") or [] if isinstance(s.get("frasi"), list) else []:
            if not isinstance(x, dict):
                frasi.append(x)
                continue
            y = {k: x[k] for k in ("testo", "fonti", "aggiunta") if k in x}
            voce = str(x.get("voce") or "").strip().upper()
            if voce in VOCI:
                y["voce"] = voce
            for campo, ammessi in (("prima", _PRIMA), ("dopo", _DOPO)):
                k = _chiave(x.get(campo))
                if k in ammessi and _forma_chiusa(x.get(campo), ammessi[k]):
                    y[campo] = ammessi[k]
            frasi.append(y)
        out.append({**s, "frasi": frasi})
    return out


def _forma_chiusa(detto, ammesso: str) -> bool:
    """Solo lettere e la punteggiatura dell'elenco: «Esatto. 1492» ha la stessa chiave senza le cifre."""
    return not re.search(r"\d", str(detto or "")) and len(str(detto or "")) <= len(ammesso) + 2


def leggi(testo) -> list[dict] | None:
    s = R.leggi(testo)
    return None if s is None else normalizza(s)


def parziale(testo) -> list[dict]:
    return normalizza(R.parziale(testo))


# ─────────────────────────── le battute ───────────────────────────
def _altra(voce: str) -> str:
    return "B" if voce == "A" else "A"


def con_battute(ris: dict) -> dict:
    """Le voci e i cenni di ogni sezione del copione rimasto dopo i cancelli: `battute`, nell'ordine in cui si
    dicono. Si fa qui, alla fine: una battuta caduta si è portata via i suoi cenni. Le frasi tenute sono
    nell'ordine della pagina (`valida`)."""
    prec, di_fila = None, 0
    cenni_tot = frasi_viste = dal_codice = 0
    for s in ris["sezioni"]:
        battute = []
        infedeli = [f for f in s["frasi"] if not fedele(f["testo"])]
        if infedeli:
            mot = ris["conti"].setdefault("motivi", {})
            mot["pulizia"] = mot.get("pulizia", 0) + len(infedeli)
            s["frasi"] = [f for f in s["frasi"] if f not in infedeli]
        tetto = math.ceil(len(s["frasi"]) * QUOTA_RACCORDI)
        cenni, ultimo = 0, None
        for i, f in enumerate(s["frasi"]):
            voce = f.get("voce") if f.get("voce") in VOCI else (_altra(prec) if prec else "A")
            if voce == prec and di_fila >= DI_FILA_MAX:
                voce = _altra(voce)
            # La forma chiusa la controlla `normalizza` all'ingresso, e di nuovo qui: da altrove non passa niente
            prima = f.get("prima") if f.get("prima") in RACCORDI_PRIMA else None
            dopo = f.get("dopo") if f.get("dopo") in RACCORDI_DOPO else None
            # In testa all'argomento niente «E poi?»: c'è il suo titolo. Due cenni di fila suonano finti
            if prima and i and cenni < tetto and not (battute and battute[-1]["tipo"] == "cenno"):
                # Chiede l'altra voce, e risponde chi stava parlando: mai una voce che si fa una domanda da sola
                voce, di_fila = prec, 0
                battute.append({"voce": _altra(voce), "testo": prima, "tipo": "cenno"})
                cenni, ultimo = cenni + 1, prima
            di_fila = di_fila + 1 if voce == prec else 1
            prec = voce
            f["voce"] = voce
            battute.append({"voce": voce, "testo": f["testo"], "tipo": "frase"})
            frasi_viste += 1
            # Il modello non ne ha messi abbastanza: i neutri, a giro (qualunque frase ci sta)
            if (not dopo and cenni_tot + cenni < frasi_viste * QUOTA_MINIMA
                    and not (len(battute) > 1 and battute[-2]["tipo"] == "cenno")):
                dopo = RACCORDI_NEUTRI[dal_codice % len(RACCORDI_NEUTRI)]
                dal_codice += 1
            if dopo and cenni < tetto and dopo != ultimo:
                battute.append({"voce": _altra(voce), "testo": dopo, "tipo": "cenno"})
                cenni, ultimo = cenni + 1, dopo
        s["battute"] = battute
        cenni_tot += cenni
    ris["sezioni"] = [s for s in ris["sezioni"] if s["frasi"]]
    ris["conti"]["cenni"] = cenni_tot
    ris["conti"]["cenni_del_codice"] = dal_codice
    voci = [b["voce"] for s in ris["sezioni"] for b in s["battute"] if b["tipo"] == "frase"]
    ris["conti"]["voce_a"] = sum(v == "A" for v in voci)
    ris["conti"]["voce_b"] = sum(v == "B" for v in voci)
    return ris


# ─────────────────────────── ciò che si dà a MOSS ───────────────────────────
_NUMERO = re.compile(r"(?<![\w,.])(\d{1,3}(?:[. ]\d{3})+|\d+)(?:,(\d+))?(?![\w])(?![.,]\d)")
# Il trattino, a regola rovesciata (seconda revisione della PR #393): si dice o si toglie **solo** in queste forme; ogni altro resta,
# e `fedele` scarta la battuta. Prima si toglieva ovunque, e «Cl-», «OH-», «d=a-b» perdevano il meno senza che nessuno lo vedesse.
_TERMINE = r"(?:\d*[A-Za-z]|\d+(?:[.,]\d+)?)"
_OPERAZIONE = re.compile(rf"(?<![\w,.])({_TERMINE})\s*[-−–]\s*(?={_TERMINE}(?![A-Za-z0-9]))")
# Algebra senza uguale: «3x-5», «n-1», «a-b». Una maiuscola col numero («T-34», un carro) o due («C-H», un legame) non si sa cos'è: si
# scarta, e «T-5» è «T meno cinque» solo in un'operazione con l'uguale
_ALGEBRA = re.compile(r"(?<![\w,.])(?:\d*[a-z]-(?:\d*[a-z]|\d+)|\d*[a-z]\s+[-−–]\s+\d*[a-z]|[b-df-hj-np-z]\s+[-−–]\s+\d+)"
                      r"(?![A-Za-z0-9])")      # non «a -196» né «a - 196»: lì «a» è una preposizione
# Il nome col numero: un nome intero di almeno due lettere («carbonio-14», «Na-23»), o una sigla di un elenco chiuso. Con una lettera
# sola è una sottrazione (terza revisione della PR #393)
_SIGLE_NUMERO = re.compile(r"(?<![\w-])(B-(?:[1-9]|12)|[DK]-[123]|C-1[234]|U-23[58])(?![\w-])")
_NOME_NUMERO = re.compile(r"(?<![\w-])([A-Za-zÀ-ÿ]{2,})[-–](?=\d+(?![\w-]))")
_NEGATIVO = re.compile(r"(?<![\w)\]])[-−–](?=\d)")             # «-196», «a -2», «(-5»
_INTERVALLO = re.compile(r"(?<![\w,.-])(\d+)[-–](\d+)(?![\w-])")  # «1519-1521», «pag. 3-5»
# Ciò che dice che è un intervallo: senza, «il risultato di 3-5» non è «tre a cinque»
_PRIMA_INTERVALLO = re.compile(r"(?:\b(?:pag|pagg|pagina|pagine|dal|dai|dalle|anni|anno|fra|tra|circa|secoli)\b\.?\s*(?:i|gli|le|il)?\s*)$", re.I)
_DOPO_INTERVALLO = re.compile(r"\s*(?:anni|mesi|giorni|secoli|ore|minuti|volte)\b", re.I)
_COMPOSTA = re.compile(r"(?<=[A-Za-zÀ-ÿ]{3})[-–](?=[A-Za-zÀ-ÿ]{3})")   # «anni-luce», «nord-est»: la sola forma che si toglie
_RESTA = re.compile(r"[-−–]")


def _ione(m: re.Match) -> str:
    from ..pronuncia import ELEMENTI, _PEZZO_FORMULA
    f = m.group(1)
    pezzi = _PEZZO_FORMULA.findall(f)
    if "".join(a + b for a, b in pezzi) != f or any(a not in ELEMENTI for a, _ in pezzi):
        return m.group(0)
    return f"{f}{m.group(2) or ''}⁻"


_IONE = re.compile(r"(?<![\w-])((?:[A-Z][a-z]?\d*)+)(\s\d)?-(?=[\s.,;:)]|$)")


def e_operazione(testo: str) -> bool:
    """Una frase con un'operazione: il trattino è un meno fra due termini, e il valore dopo non ha il suo segno da solo."""
    t = _SIGLE_NUMERO.sub("", str(testo or ""))
    return ("=" in t and bool(_OPERAZIONE.search(t))) or bool(_ALGEBRA.search(t))


def _segni(testo: str) -> str:
    """Il segno e il trattino, prima di ogni altra pulizia. Gli ioni come i positivi («Cl-» come «Na+»), il meno di un'operazione,
    il nome col numero, il numero negativo, l'intervallo, la parola composta. Il resto non si tocca."""
    t = _IONE.sub(_ione, str(testo or ""))
    t = _SIGLE_NUMERO.sub(lambda m: m.group(1).replace("-", " "), t)
    if e_operazione(t):
        for _i in range(6):      # «a-b-c»: i termini si sovrappongono
            nuovo = _OPERAZIONE.sub(r"\1 − ", t)
            if nuovo == t:
                break
            t = nuovo
    t = _NOME_NUMERO.sub(lambda m: m.group(1) + " ", t)
    t = _NEGATIVO.sub("meno ", t)

    def intervallo(m: re.Match) -> str:
        a, b = int(m.group(1)), int(m.group(2))
        anni = all(1000 <= x <= 2100 for x in (a, b))
        segnale = _PRIMA_INTERVALLO.search(m.string[:m.start()]) or _DOPO_INTERVALLO.match(m.string[m.end():])
        return f"{a} a {b}" if a < b and (anni or segnale) else m.group(0)
    t = _INTERVALLO.sub(intervallo, t)
    return _COMPOSTA.sub(" ", t)


def intero_detto(n: int) -> str:
    """Un intero in lettere, anche oltre i milioni («quindici milioni», «un miliardo duecento milioni»)."""
    from ..numeri import in_lettere

    def piccolo(x: int) -> str:
        p = in_lettere(x)
        return p[:-3] + "tré" if p.endswith("tre") and x > 20 else p
    if n < 1_000_000:
        return piccolo(n)
    parti = []
    for valore, una, tante in ((10**9, "un miliardo", "miliardi"), (10**6, "un milione", "milioni")):
        q, n = divmod(n, valore)
        if q:
            parti.append(una if q == 1 else f"{intero_detto(q)} {tante}")
    if n:
        parti.append(piccolo(n))
    return " ".join(parti)


_NON_UN_NOME = frozenset("in di a da su per con tra fra e o ma che se nel nella al alla del della dal dalla sul sulla".split())


def numeri_in_lettere(testo: str) -> str:
    """I numeri in cifre di una frase, in lettere: «4,6» → «quattro virgola sei», «100 000» → «centomila»."""
    def sost(m: re.Match) -> str:
        n = int(re.sub(r"[. ]", "", m.group(1)))
        if m.group(2) is not None:
            d = m.group(2)
            dopo = " ".join(intero_detto(int(c)) for c in d) if d.startswith("0") else intero_detto(int(d))
            return f"{intero_detto(n)} virgola {dopo}"
        if n == 1:
            # «1 metro» è «un metro»; a fine frase, dopo un segno o davanti a «in» resta «uno»
            w = re.match(r"\s+([a-zà-ÿ]+)", m.string[m.end():])
            prima = m.string[:m.start()].rstrip().rsplit(" ", 1)[-1].lower()
            if w and prima not in ("meno", "più") and w.group(1).lower() not in _NON_UN_NOME:
                return "una" if w.group(1).endswith("a") else "un"
            return "uno"
        return intero_detto(n)
    return _NUMERO.sub(sost, testo)


def detto(testo: str) -> str:
    """La frase come va detta: il segno e il trattino (`_segni`), unità, formule, sigle e simboli a parole, numeri in lettere. Un
    trattino che non si sa dire resta qui, e `fedele` scarta la battuta: `normalize_text` di MOSS lo toglierebbe in silenzio."""
    from ..pronuncia import per_ripasso
    return " ".join(numeri_in_lettere(per_ripasso(_segni(testo))).split())


def valori_di(testo: str) -> list[float]:
    """I valori di un testo, col segno, da come è scritto: quelli che nessuna pulizia può cambiare."""
    from . import unita as U
    from . import riassunto_controllo as C
    t = re.sub(r"(?<!\d)(\d{1,3})((?:\.\d{3})+)(?!\d)", lambda m: m.group(1) + m.group(2).replace(".", ""),
               str(testo or "").replace("%", " per cento "))
    # La carica di uno ione («SO4 2-») e il numero di una sigla («B-12») stanno con la formula: Whisper li scrive attaccati («SO42-»,
    # «B12»), e non sono valori della frase. «carbonio-14» è un nome col suo numero, non un quattordici negativo
    t = _IONE.sub(lambda m: m.group(1), t)
    t = _SIGLE_NUMERO.sub(lambda m: m.group(1).replace("-", ""), t)
    return [round(v, 9) for v, _u in U.leggi(C._normale(_NOME_NUMERO.sub(lambda m: m.group(1) + " ", t)))]


def fedele(testo: str) -> bool:
    """Ciò che si dice ha tutti i valori della frase controllata, col loro segno, e nessun trattino di cui non si sa niente. Se no la
    battuta non si dice. Una rete sotto `detto`, che questa frase non l'ha mai vista."""
    d = detto(testo)
    if _RESTA.search(d):
        return False
    dopo = valori_di(d)
    op = e_operazione(testo)
    for v in valori_di(testo):
        c = next((x for x in dopo if x == v or (op and abs(x) == abs(v))), None)
        if c is None:
            return False
        dopo.remove(c)
    return True


def per_moss(battuta_detta: str, pronuncia=None) -> str:
    """Il testo della battuta per MOSS: con la pronuncia degli inglesismi, in grafia italiana (mai fonemi)."""
    if pronuncia is None:
        return battuta_detta
    return pronuncia.applica(battuta_detta, fonemi=False)


def tag(voce: str) -> str:
    return "[S1]" if voce == "A" else "[S2]"


def pezzi(sezioni: list[dict], argomenti: list[dict], nomi=(), pronuncia=None, massimo: int = PEZZO_CAR) -> list[dict]:
    """Il copione in pezzi da generare uno alla volta: [{n, battute: [{voce, testo, detto, tipo}], argomenti, moss}].
    Una battuta non si stacca dai suoi cenni. Un titolo del piano si dice come nel riassunto, se passa le stesse
    regole; il numero lo scrive il codice."""
    per_id = {int(a["id"]): a for a in argomenti}
    blocchi: list[tuple[int, bool, list[dict]]] = []
    for s in sezioni:
        aid = int(s["argomento"])
        a = per_id.get(aid) or {}
        # Solo il titolo che ha passato il codice, il giudice e il guardiano (`Lettore._copione_controllato`):
        # senza, resta il numero, che lo scrive il codice
        titolo, _s = (S.frasi_pagina(s.get("titolo"), nomi, True) if s.get("titolo") and fedele(s["titolo"]) else ([], {}))
        testa = f"Argomento {a.get('numero', '')}.".replace(" .", ".")
        testi = [testa] + [f for pp in titolo for f in pp]
        prima = s["battute"][0]["voce"] if s["battute"] else "A"
        # Il titolo non si stacca dalla prima battuta: un pezzo senza niente da controllare non si può controllare
        corrente: list[dict] = [{"voce": prima, "testo": t, "tipo": "titolo"} for t in testi]
        nuovo = True
        for b in s["battute"]:
            # Un blocco finisce con una battuta e il suo cenno: il «prima» sta con la battuta che segue
            if (any(x["tipo"] == "frase" for x in corrente)
                    and (b["tipo"] == "frase" or corrente[-1]["tipo"] == "cenno")):
                blocchi.append((aid, nuovo, corrente))
                corrente, nuovo = [], False
            corrente.append(b)
        if corrente:
            blocchi.append((aid, nuovo, corrente))
    out: list[dict] = []
    cur: list[dict] = []
    args: list[int] = []
    car = 0

    def chiudi():
        nonlocal cur, args, car
        if cur:
            out.append(_pezzo(len(out) + 1, cur, args, pronuncia))
        cur, args, car = [], [], 0

    for aid, nuovo, bl in blocchi:
        lung = sum(len(b["testo"]) for b in bl)
        if cur and (car + lung > massimo or (nuovo and car >= PEZZO_MIN_CAR)):
            chiudi()
        cur += bl
        car += lung
        if aid not in args:
            args.append(aid)
    chiudi()
    return out


def _pezzo(n: int, battute: list[dict], args: list[int], pronuncia) -> dict:
    righe = [{"voce": b["voce"], "testo": b["testo"], "detto": detto(b["testo"]), "tipo": b["tipo"]} for b in battute]
    moss = " ".join(f"{tag(b['voce'])} {per_moss(b['detto'], pronuncia)}" for b in righe)
    return {"n": n, "battute": righe, "argomenti": list(args), "moss": moss,
            "firma": hashlib.sha256(moss.encode()).hexdigest()[:12]}


# ─────────────────────────── i file ───────────────────────────
def cartella_podcast(cfg, vid) -> Path | None:
    from . import dati as D
    base = D.cartella_di(cfg)
    return base / CARTELLA_PODCAST / str(int(vid)) if base is not None else None


def cartella_lavoro(cfg) -> Path | None:
    from . import dati as D
    base = D.cartella_di(cfg)
    return base / CARTELLA_LAVORO if base is not None else None


def togli_lavoro(base) -> None:
    """La cartella scrivibile del container: copione e audio di una sessione a metà, mai fuori da `base`."""
    if not base:
        return
    d = Path(base) / CARTELLA_LAVORO
    if d.is_dir() and not d.is_symlink():
        shutil.rmtree(d, ignore_errors=True)


# ─────────────────────────── le voci ───────────────────────────
class VoceNonUsabile(Exception):
    """Una delle voci non c'è o non vale: il podcast non parte e non ne cerca un'altra. `motivo` è l'esito del giro."""

    def __init__(self, motivo: str, nome: str, messaggio: str):
        super().__init__(messaggio)
        self.motivo, self.nome = motivo, nome


def percorso_voce(cfg, chiave: str) -> str:
    """La voce di Piper di una chiave della configurazione: mai una persona reale (`studio_podcast_voce_a`, `_b`)."""
    p = str(getattr(cfg, chiave, "") or "")
    if p and not os.path.isabs(p):
        p = os.path.join(str(getattr(cfg, "config_dir", "") or os.getcwd()), p)
    return p


def hash_ammessi() -> set[str]:
    """L'elenco è per contenuto: un elenco di nomi lasciava passare `giorgio.onnx`, una copia rinominata, un'altra qualità.
    Per le due voci solo gli SHA-256 del catalogo di paola e serena-high, scelte all'ascolto. Una voce nuova va aggiunta qui."""
    from ..installa.catalogo import VOCI as CATALOGO
    return {v[3][1] for v in CATALOGO if v[0] in VOCI_DEL_PODCAST}


def hash_catalogo() -> set[str]:
    """Le voci ufficiali: quelle che possono dire l'avviso e i pezzi a una voce."""
    from ..installa.catalogo import VOCI as CATALOGO
    return {v[3][1] for v in CATALOGO}


def _come_installarla(nome: str) -> str:
    from ..installa.catalogo import VOCI as CATALOGO
    for v in CATALOGO:
        if nome == f"it_IT-{v[1]}-{v[2]}":
            return f" (`calliope stato --installa {v[0]}`)"
    return ""


def _file_impronte(cfg) -> Path | None:
    from . import dati as D
    base = D.cartella_di(cfg)
    return base / CARTELLA_RIFERIMENTI / "impronte.json" if base is not None else None


def leggi_impronte(cfg) -> dict:
    """{percorso: {sha, dim, ora, riferimento}}: niente di personale, le voci di questa macchina."""
    f = _file_impronte(cfg)
    try:
        d = json.loads(f.read_text(encoding="utf-8")) if f is not None else {}
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def scrivi_impronte(cfg, d: dict) -> None:
    f = _file_impronte(cfg)
    if f is None:
        return
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        t = f.with_name(f"{f.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        t.write_text(json.dumps(d), encoding="utf-8")
        os.replace(t, f)
    except OSError as e:      # il disco pieno, la cartella in sola lettura: resta `_MEMO`, e dopo un riavvio si rifà l'hash
        if not _SCRITTURA_DETTA:
            _SCRITTURA_DETTA.append(True)
            print(f"   [STUDIO] podcast: impronte delle voci non scritte ({type(e).__name__}): il riferimento si rifarà a ogni sessione", flush=True)


def impronta_voce(cfg, percorso: str) -> str | None:
    """Lo SHA-256 del modello, ricalcolato solo se cambiano dimensione o data. Una voce tolta tiene l'ultima impronta vista,
    così la firma non cambia e un podcast già pronto non si butta. None: mai vista."""
    with _LOCK_IMPRONTE:
        d = leggi_impronte(cfg)
        x = d.get(percorso) or {}
        try:
            st = os.stat(percorso)
        except OSError:
            return x.get("sha") or (_MEMO.get(percorso) or {}).get("sha")
        for y in (x, _MEMO.get(percorso) or {}):
            if y.get("sha") and y.get("dim") == st.st_size and y.get("ora") == st.st_mtime_ns:
                return y["sha"]
        h = hashlib.sha256()
        try:
            with open(percorso, "rb") as fh:
                for pezzo in iter(lambda: fh.read(1 << 20), b""):
                    h.update(pezzo)
        except OSError:
            return x.get("sha")
        d[percorso] = {**x, "sha": h.hexdigest(), "dim": st.st_size, "ora": st.st_mtime_ns}
        _MEMO[percorso] = d[percorso]
        scrivi_impronte(cfg, d)
        return d[percorso]["sha"]


def riferimento_fatto(cfg, percorso: str, sha: str) -> None:
    """Il riferimento su disco viene da questa voce."""
    with _LOCK_IMPRONTE:
        d = leggi_impronte(cfg)
        d[percorso] = {**(d.get(percorso) or {}), "riferimento": sha}
        scrivi_impronte(cfg, d)


def controlla_voce(cfg, chiave: str) -> str:
    """Il percorso della voce, o `VoceNonUsabile`. Anche con il riferimento già su disco: una voce tolta si dice, sempre."""
    percorso = percorso_voce(cfg, chiave)
    nome = Path(percorso).stem
    if not (os.path.isfile(percorso) and os.path.isfile(percorso + ".json")):
        raise VoceNonUsabile("voce_mancante", nome, f"manca la voce {nome}{_come_installarla(nome)}: il podcast non parte")
    if impronta_voce(cfg, percorso) not in hash_ammessi():
        raise VoceNonUsabile("voce_non_ammessa", nome, f"la voce {nome} (`{chiave}`) non è fra quelle ammesse: il podcast non parte")
    return percorso


def controlla_voci(cfg) -> None:
    for chiave in CHIAVI_VOCI:
        controlla_voce(cfg, chiave)


def voce_di_servizio(cfg) -> tuple[str, bool]:
    """(la voce dell'avviso e dei pezzi a una voce, se è quella di Calliope). Una voce di Calliope sana fuori dal catalogo non ferma il
    podcast, ma dentro il podcast non entra: quel poco lo dice la voce A, così nessuna voce esclusa ci finisce sotto un altro nome."""
    p = percorso_voce(cfg, CHIAVE_VOCE_CALLIOPE)
    if os.path.isfile(p) and impronta_voce(cfg, p) in hash_catalogo():
        return str(getattr(cfg, CHIAVE_VOCE_CALLIOPE)), True
    return percorso_voce(cfg, CHIAVI_VOCI[0]), False


# ─────────────────────────── i metodi di Studio ───────────────────────────
class Podcast:
    """Il podcast a due voci (mixin di `servizio.Studio`). L'audio lo prepara `podcast_audio.Preparatore`."""

    podcast_preparatore = None       # `podcast_audio.Preparatore`: lo mette main.py
    podcast_pronuncia = None         # `pronuncia.Pronuncia` dello Speaker: lo mette `podcast_audio.prepara`

    def podcast_modo(self) -> str:
        return modo(self.cfg)

    def _misure_podcast(self) -> dict:
        return self.misure.setdefault("podcast", {
            "pronti": 0, "scarsi": 0, "corti": 0, "lunghi": 0, "scaduti": 0, "detti": 0})

    def _impronte_voci(self) -> list[str | None]:
        return [impronta_voce(self.cfg, percorso_voce(self.cfg, k)) for k in CHIAVI_VOCI]

    def _voci_ok(self) -> bool:
        try:
            controlla_voci(self.cfg)
        except VoceNonUsabile:
            return False
        return True

    def _firma_podcast(self, vid) -> str:
        return firma(self._argomenti_per_carte(vid), self._pagine_di(vid),
                     [(a["id"], a["numero"]) for a in self._argomenti_numerati(vid)], self._impronte_voci())

    def _riga_podcast(self, vid) -> dict | None:
        return self.dati.uno("SELECT * FROM studio_podcast WHERE verifica = ?", (int(vid),))

    def verifiche_per_podcast(self) -> list[dict]:
        """Come il riassunto: le verifiche aperte, a pagine lette, senza una prova aperta, con una firma diversa
        dall'ultimo copione. Vuoto da spenta, col ripasso spento, in sola lettura, con lo Studio non «attivo»."""
        if (self.podcast_modo() != ATTIVA or not self.per_modello() or not self.ascolto_acceso()
                or not self.dati.scrivibile):
            return []
        if not self._voci_ok():      # un copione che nessuno può dire: il modello non si scomoda
            return []
        out = []
        for v in self.dati.tutti("SELECT * FROM studio_verifiche WHERE stato = 'aperta' AND "
                                 "data >= ? ORDER BY data, id", (self._oggi().isoformat(),)):
            d = self.podcast_richiesta(v["id"], v)
            if d is not None:
                out.append(d)
        return out

    def podcast_richiesta(self, vid, v: dict | None = None) -> dict | None:
        v = v or self.dati.uno("SELECT * FROM studio_verifiche WHERE id = ? AND stato = 'aperta'", (int(vid),))
        if v is None or self._libreria_chiusa(v):
            return None
        args, pagine = self._argomenti_per_carte(v["id"]), self._pagine_di(v["id"])
        if any(p.get("stato") in ("da_leggere", "in_lettura") for p in pagine):
            return None
        lette = {int(p["id"]) for p in A.lette(pagine)}
        if not any(set(a["pagine"]) & lette for a in args):
            return None
        f = self._firma_podcast(v["id"])
        r = self._riga_podcast(v["id"]) or {}
        if not G.da_generare(r.get("firma"), r.get("esito"), r.get("quando"), f, self.adesso()):
            return None
        return {**v, "_pagine": pagine, "_argomenti": args, "_firma": f, "_nomi": self._nomi_ascolto()}

    def proponi_podcast(self, vid, firma_: str, ris: dict | None, esito: str) -> int | None:
        """Scrive l'esito di un copione, come `proponi_riassunto`, con i suoi pezzi: il testo solo con «pronto»;
        se intanto le pagine sono cambiate o c'è una prova aperta, niente (None). Un copione nuovo toglie l'audio
        di quello di prima."""
        with self.dati.lock:
            db = self.dati.db
            try:
                if db.in_transaction:
                    db.commit()
                db.execute("BEGIN IMMEDIATE")
                v = db.execute("SELECT * FROM studio_verifiche WHERE id = ? AND stato = 'aperta'",
                               (int(vid),)).fetchone()
                if v is None or self._firma_podcast(vid) != firma_ or self._prova_aperta(int(vid)):
                    db.rollback()
                    return None
                prima = db.execute("SELECT firma FROM studio_podcast WHERE verifica = ?", (int(vid),)).fetchone()
                scritta, errori = G.firma_da_scrivere(prima["firma"] if prima else None, firma_, esito)
                sezioni = (ris or {}).get("sezioni") if esito == R.PRONTO else None
                contenuto = None
                if sezioni:
                    p = pezzi(sezioni, self._argomenti_numerati(vid), self._nomi_ascolto(), self.podcast_pronuncia)
                    contenuto = json.dumps({"sezioni": sezioni, "pezzi": p}, ensure_ascii=False)
                db.execute("INSERT OR REPLACE INTO studio_podcast (verifica, persona, firma, esito, quando, contenuto, "
                           "conti, audio) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                           (int(vid), str(v["persona"]), scritta, esito,
                            self.adesso().isoformat(timespec="seconds"), contenuto,
                            json.dumps((ris or {}).get("conti") or {})))
                db.commit()
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
        self._togli_audio_podcast(vid)
        conta = {R.PRONTO: "pronti", R.SCARSO: "scarsi", R.CORTO: "corti", R.LUNGO: "lunghi"}.get(esito)
        if conta:
            self._misure_podcast()[conta] += 1
        if errori >= G.ERRORI_MAX:
            self._registra(f"verifica {vid}: podcast fermo dopo {errori} errori con le stesse pagine: riparte "
                           "quando cambiano")
        return len(sezioni or ())

    def _togli_audio_podcast(self, vid):
        from . import dati as D
        S.togli_audio(D.cartella_di(self.cfg), solo=[int(vid)], sotto=CARTELLA_PODCAST)

    def _scarta_podcast(self, vid) -> bool:
        """Toglie copione e audio di una verifica (le pagine sono cambiate). In sola lettura resta, e non si dice
        lo stesso."""
        if not self.dati.scrivibile:
            return False
        n = self.dati.scrivi("DELETE FROM studio_podcast WHERE verifica = ?", (int(vid),))
        self._togli_audio_podcast(vid)
        if n:
            self._misure_podcast()["scaduti"] += 1
        return bool(n)

    def podcast_pagine_cambiate(self, vid):
        self._scarta_podcast(vid)

    def _podcast_valido(self, v: dict) -> tuple[dict | None, dict | None]:
        """(la riga, l'audio finito) della firma di adesso. Un copione scaduto si cancella appena visto."""
        if self.podcast_modo() != ATTIVA:
            return None, None
        r = self._riga_podcast(v["id"])
        if r is None:
            return None, None
        if None in self._impronte_voci():    # una voce mai vista qui: non si può dire che il podcast sia scaduto, né buono
            return None, None
        base, _e = G.firma_e_errori(r.get("firma"))
        if base != self._firma_podcast(v["id"]):
            self._scarta_podcast(v["id"])
            return None, None
        try:
            return r, json.loads(r["audio"]) if r.get("audio") else None
        except (ValueError, TypeError):
            return r, None

    def podcast_pronto(self, v: dict) -> bool:
        return self._copione_podcast(v) is not None

    def podcast_nota(self, v: dict) -> str | None:
        """La frase del codice sullo schermo finché il podcast non c'è. None: niente da dire."""
        r, a = self._podcast_valido(v)
        if self.podcast_modo() != ATTIVA or (a or {}).get("esito") == "pronto":
            return None
        # «intanto c'è il riassunto» solo se c'è davvero (revisione della PR #393)
        c_e = self._riassunto_vivo(v)[1] == R.PRONTO
        if (a or {}).get("esito") == "scarso":
            return "Il podcast non ha passato i miei controlli" + (": resta il riassunto." if c_e else ".")
        if r is not None and r["esito"] not in (R.PRONTO, G.ERRORE):
            return None
        # Dire «si prepara» è vero solo se qualcuno lo sta preparando (come il riassunto, #386)
        if (self.podcast_preparatore is None or not self.per_modello() or v.get("stato") != "aperta"
                or str(v.get("data")) < self._oggi().isoformat()):
            return None
        if not self._voci_ok():      # non si prepara, e va detto: né «da solo» né silenzio
            return "Il podcast a due voci adesso non si può preparare: non ha le sue voci" + (". Intanto c'è il riassunto." if c_e else ".")
        return ("Il podcast a due voci si prepara da solo, quando la macchina è libera"
                + (": intanto c'è il riassunto." if c_e else "."))

    def _copione_podcast(self, v: dict, per_voce: bool = False) -> S.Copione | None:
        """Il copione con le parti già pronte, se c'è un audio finito di adesso, con le parole che svegliano di
        adesso: in startrek una battuta può dire «computer» e fermare la lettura. In quel caso resta il
        riassunto, e l'audio non si butta."""
        r, a = self._podcast_valido(v)
        if a is None or a.get("esito") != "pronto" or not r.get("contenuto"):
            return None
        cartella = cartella_podcast(self.cfg, v["id"])
        if cartella is None:
            return None
        nomi = self._nomi_ascolto()
        try:
            cont = json.loads(r["contenuto"])
            if any(b["tipo"] == "frase" and S.nome_dentro(b["testo"], nomi)
                   for p in cont["pezzi"] for b in p["battute"]):
                return None
            parti = a["parti"]
        except (ValueError, KeyError, TypeError):
            return None
        if not parti or not all((cartella / S.nome_file(a["firma"], p["n"])).is_file() for p in parti):
            return None
        cp = S.Copione("tutto")
        cp.fonte, cp.cartella, cp.firma_file = "podcast", cartella, a["firma"]
        # A voce l'avviso lo dice Calliope, solo se la sua voce è ammessa: altrimenti resta quello in testa alla prima parte, già
        # detto dalla voce A, e dalle altre si salta
        calliope_ammessa = voce_di_servizio(self.cfg)[1]
        if per_voce and calliope_ammessa:
            cp.voci.append(S.Voce(S.CALLIOPE, S.PODCAST_INTRO, parti[0]["n"], cp.nuovo_par()))
        for i, p in enumerate(parti):
            cp.voci.append(S.Voce(S.AUDIO, f"podcast {a['firma']} parte {p['n']}", p["n"], cp.nuovo_par(),
                                  secondi=float(p["secondi"]), file=str(cartella / S.nome_file(a["firma"], p["n"])),
                                  salta=float(p.get("intro_s") or 0) if per_voce and (calliope_ammessa or i > 0) else 0.0))
            cp.parti.append({"n": p["n"], "tipo": "podcast", "argomento": None, "titolo": "", "pagine": [],
                             "frasi": p.get("frasi"), "secondi": int(round(p["secondi"])),
                             "argomenti": list(p.get("argomenti") or ()), "una_voce": bool(p.get("una_voce")),
                             "continua": False})
        return cp

    # ── per il preparatore dell'audio ──
    def podcast_da_preparare(self) -> list[dict]:
        """Le verifiche con un copione pronto di adesso e senza un audio finito, nell'ordine delle date: {id, persona,
        firma, pezzi}. Vuoto da spenta, in sola lettura e con lo Studio non «attivo»."""
        if (self.podcast_modo() != ATTIVA or not self.per_modello() or not self.ascolto_acceso()
                or not self.dati.scrivibile):
            return []
        out = []
        for v in self.dati.tutti("SELECT * FROM studio_verifiche WHERE stato = 'aperta' AND data >= ? "
                                 "ORDER BY data, id", (self._oggi().isoformat(),)):
            if self._libreria_chiusa(v):
                continue
            r, a = self._podcast_valido(v)
            if r is None or r["esito"] != R.PRONTO or not r["contenuto"] or a is not None:
                continue
            try:
                cont = json.loads(r["contenuto"])
            except ValueError:
                continue
            out.append({"id": int(v["id"]), "persona": v["persona"], "firma": G.firma_e_errori(r["firma"])[0],
                        "pezzi": cont["pezzi"], "sezioni": cont["sezioni"]})
        return out

    def podcast_ancora(self, vid, firma_: str) -> bool:
        """Durante la sessione, prima di ogni pezzo: la verifica c'è, è la stessa firma, nessuna prova aperta."""
        try:
            with self.dati.lock:
                v = self.dati.uno("SELECT * FROM studio_verifiche WHERE id = ?", (int(vid),))
                return (v is not None and not self._libreria_chiusa(v)
                        and self._firma_podcast(vid) == firma_ and self.podcast_modo() == ATTIVA)
        except Exception:  # noqa: BLE001 — nel dubbio ci si ferma
            return False

    def podcast_audio_finito(self, vid, firma_: str, audio: dict) -> bool:
        """Lo stato finale dell'audio ({esito, firma, parti, conti}: solo numeri). False se la firma è cambiata."""
        with self.dati.lock:
            if not self.podcast_ancora(vid, firma_):
                return False
            self.dati.scrivi("UPDATE studio_podcast SET audio = ? WHERE verifica = ?",
                             (json.dumps(audio), int(vid)))
        return True

    def podcast_stato(self, vid) -> dict:
        """Per il banco e il registro: {esito, conti, audio}, solo conti."""
        r = self._riga_podcast(vid)
        if r is None:
            return {"esito": None, "conti": {}, "audio": None}
        try:
            return {"esito": r["esito"], "conti": json.loads(r["conti"] or "{}"),
                    "audio": json.loads(r["audio"]) if r["audio"] else None}
        except ValueError:
            return {"esito": r["esito"], "conti": {}, "audio": None}
