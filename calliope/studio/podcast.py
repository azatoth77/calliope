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
import re
import shutil
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
CARTELLA_LAVORO = "podcast_lavoro"  # la sola cartella scrivibile del container: si svuota a ogni sessione

# La versione entra nella firma: un prompt, un elenco o un taglio nuovi rifanno i copioni
VERSIONE = 1
VOCI = ("A", "B")
DI_FILA_MAX = 2                    # le battute di fila della stessa voce
QUOTA_RACCORDI = 0.5               # dei cenni per battuta con la fonte, al più
QUOTA_MINIMA = 1 / 3               # …e almeno: il modello tende a non metterne (0 su 28 sul banco del 04/11)
# Un pezzo di MOSS. Il banco ha generato 2 minuti in un blocco e ne ha saltate delle frasi; il pezzo si rigenera
# da solo. Numeri in `docs/aree/studio.md` (04/11)
PEZZO_CAR = 900
PEZZO_MIN_CAR = 500                # a un argomento nuovo si va a capo da qui in su

RACCORDI_PRIMA = ("E poi?", "Perché?", "Come mai?", "In che senso?", "E quindi?", "Cioè?", "E dopo?")
RACCORDI_DOPO = ("Esatto.", "Capito.", "Giusto.", "Interessante.", "Ah, ecco.", "Certo.", "Chiaro.")
# Quelli che può mettere il codice: non confermano e non chiedono niente, vanno dopo qualunque frase
RACCORDI_NEUTRI = ("Capito.", "Interessante.", "Chiaro.", "Ah, ecco.")


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


def firma(argomenti: list[dict], pagine: list[dict], numeri=()) -> str:
    """La firma del riassunto (il testo di ogni pagina), con i numeri degli argomenti, che il podcast dice."""
    righe = [VERSIONE, R.firma(argomenti, pagine), sorted((int(i), int(n)) for i, n in numeri)]
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
    ris["conti"]["cenni"] = cenni_tot
    ris["conti"]["cenni_del_codice"] = dal_codice
    voci = [b["voce"] for s in ris["sezioni"] for b in s["battute"] if b["tipo"] == "frase"]
    ris["conti"]["voce_a"] = sum(v == "A" for v in voci)
    ris["conti"]["voce_b"] = sum(v == "B" for v in voci)
    return ris


# ─────────────────────────── ciò che si dà a MOSS ───────────────────────────
_NUMERO = re.compile(r"(?<![\w,.])(\d{1,3}(?:[. ]\d{3})+|\d+)(?:,(\d+))?(?![\w])(?![.,]\d)")
_TRATTINO = re.compile(r"(?<=\w)\s*[-–—]\s*(?=\w)")


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


def numeri_in_lettere(testo: str) -> str:
    """I numeri in cifre di una frase, in lettere: «4,6» → «quattro virgola sei», «100 000» → «centomila»."""
    def sost(m: re.Match) -> str:
        n = int(re.sub(r"[. ]", "", m.group(1)))
        if m.group(2) is not None:
            d = m.group(2)
            dopo = " ".join(intero_detto(int(c)) for c in d) if d.startswith("0") else intero_detto(int(d))
            return f"{intero_detto(n)} virgola {dopo}"
        if n == 1:
            # «1 metro» è «un metro»; a fine frase resta «uno»
            w = re.match(r"\s+([a-zà-ÿ]+)", m.string[m.end():])
            if w:
                return "una" if w.group(1).endswith("a") else "un"
        return intero_detto(n)
    return _NUMERO.sub(sost, testo)


def detto(testo: str) -> str:
    """La frase come va detta: unità, formule, sigle e simboli a parole, numeri in lettere, niente trattini
    (`normalize_text` di MOSS li toglie e attacca le parole: «anniluce»). È anche ciò con cui si confronta
    l'audio."""
    from ..pronuncia import per_ripasso
    return " ".join(_TRATTINO.sub(" ", numeri_in_lettere(per_ripasso(testo))).split())


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
        titolo, _s = S.frasi_pagina(a.get("titolo"), nomi, True)
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

    def _firma_podcast(self, vid) -> str:
        return firma(self._argomenti_per_carte(vid), self._pagine_di(vid),
                     [(a["id"], a["numero"]) for a in self._argomenti_numerati(vid)])

    def _riga_podcast(self, vid) -> dict | None:
        return self.dati.uno("SELECT * FROM studio_podcast WHERE verifica = ?", (int(vid),))

    def verifiche_per_podcast(self) -> list[dict]:
        """Come il riassunto: le verifiche aperte, a pagine lette, senza una prova aperta, con una firma diversa
        dall'ultimo copione. Vuoto da spenta, col ripasso spento, in sola lettura, con lo Studio non «attivo»."""
        if (self.podcast_modo() != ATTIVA or not self.per_modello() or not self.ascolto_acceso()
                or not self.dati.scrivibile):
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
        if (a or {}).get("esito") == "scarso":
            return "Il podcast non ha passato i miei controlli: resta il riassunto."
        if r is not None and r["esito"] not in (R.PRONTO, G.ERRORE):
            return None
        # Dire «si prepara» è vero solo se qualcuno lo sta preparando (come il riassunto, #386)
        if (self.podcast_preparatore is None or not self.per_modello() or v.get("stato") != "aperta"
                or str(v.get("data")) < self._oggi().isoformat()):
            return None
        return "Il podcast a due voci si prepara da solo, quando la macchina è libera: intanto c'è il riassunto."

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
        if per_voce:
            cp.voci.append(S.Voce(S.CALLIOPE, S.PODCAST_INTRO, parti[0]["n"], cp.nuovo_par()))
        for p in parti:
            cp.voci.append(S.Voce(S.AUDIO, f"podcast {a['firma']} parte {p['n']}", p["n"], cp.nuovo_par(),
                                  secondi=float(p["secondi"]), file=str(cartella / S.nome_file(a["firma"], p["n"])),
                                  salta=float(p.get("intro_s") or 0) if per_voce else 0.0))
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
