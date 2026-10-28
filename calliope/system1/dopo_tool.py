"""
Il terzo decisore System 1: **dopo un tool, la frase la può dire il codice?** (15/10/2026,
roadmap 3.12; misure da cui nasce nel § 7 di docs/ricerche/2026-10-15-preselezione-tool.md).

Sulla DGX (gemma4 26B su Ollama) un turno con un tool ha la prima frase a ~2,71 s contro ~1,77 s
di un turno senza tool (14/10): la differenza è quasi tutta la **seconda passata** del modello,
che rimette in parole il risultato del tool. Per gli esiti semplici e chiusi la frase c'è già:
il tool la scrive nel risultato (`conferma` di timer, promemoria, liste, volume; `da_dire` di
ora, data e calcoli), ed è la stessa che Brain dice da settimane al posto di una risposta vuota
(`conferma_al_posto_del_vuoto`). Qui si decide quando quella frase basta, senza la seconda
passata.

Interfaccia comune (`calliope/system1/__init__.py`): `decide(Esito) -> Scelta(scelta,
sicurezza)`, con `scelta` «codice» o «modello»; Brain lo chiede attraverso `Sorvegliato` (un
thread suo, un tempo massimo): lento, guasto o spento → il modello, come prima.

**Principio 10.** La scelta del tool e degli argomenti l'ha già fatta il modello; il decisore non
decide nessun significato, converte un esito già deciso nella frase che il tool stesso ha
scritto (correzione della forma). Ogni dubbio rimanda al modello, cioè a ciò che succedeva
prima: più tool nella stessa risposta, un tool fallito o da spiegare (`cosa_fare`, una domanda
in sospeso, un nome incerto), un tool che non è nell'elenco chiuso (`COPERTI`: i risultati con
dati da riassumere, come una ricerca, non ci sono; la lista e l'agenda lette solo fino a due
voci, dal 16/10), testo del modello già detto, una persona minore, un tono che il codice non sa
fare, segnali di struttura del turno (proposta aperta, spinte, giri di correzione, dati del turno
in più, foto e sviluppo; fino al 28/10 anche gli esercizi, tolti con la #279), e la frase della
persona con più richieste, lunga, o con una domanda quando il tool è un'azione. I controlli sulla frase della persona guardano solo la forma
(quante frasi, quante parole, il punto di domanda) e mandano al modello; l'unica eccezione
(16/10, issue #103) è una frase d'apertura in forma chiusa e per intero («Perfetto.», «Allora,
iniziamo con un calcolo.»), che non conta come una richiesta in più. In «attivo» la regola scrive il suo
nome nel registro dei turni (`dopo_tool_codice`); casi e contrari in `prove/prova_dopo_tool.py`.

Modi (`system1_dopo_tool`): «spento» (di serie), «ombra» (si calcola la frase, si fa comunque la
seconda passata e il registro scrive cosa avrebbe detto il codice, il tempo risparmiabile e se
il modello ha detto la stessa cosa nella sostanza), «attivo» (niente seconda passata per i casi
coperti; la frase del codice entra nella storia come messaggio dell'assistente).

Solo libreria standard.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import Decisione, Sorvegliato

SPENTO, OMBRA, ATTIVO = "spento", "ombra", "attivo"
MODI = (SPENTO, OMBRA, ATTIVO)
CODICE, MODELLO = "codice", "modello"
SOGLIA = 0.9            # «codice» vale solo da qui in su (il decisore a regole dà 1,0)
ATTESA_S = 0.05         # il decisore risponde in µs: oltre questo tempo, il modello
PAROLE_MAX = 16         # la frase della persona, al più (di più: forse chiede altro)
FRASE_MAX = 220         # la frase del tool, al più (caratteri): di più è da riassumere
# I toni in cui la frase del tool suona giusta (il «tu», senza ironia né «computer di bordo»):
# negli altri la seconda passata la dice col tono suo
TONI = ("normale", "amichevole", "essenziale")


@dataclass(frozen=True)
class Copertura:
    """Un tool coperto: i campi della sua frase pronta, in ordine, e se la frase della persona
    può essere una domanda («Che ore sono?» sì; un'azione con una domanda forse chiede altro).
    `forma`: come diventa frase il campo (il `da_dire` di calcola è solo il numero: «102»)."""
    campi: tuple
    domanda: bool
    forma: str = "{}"
    # Le letture brevi (16/10, issue #103): il risultato ha la lista `voci`, e la frase del codice
    # vale solo fino a `voci_max` voci (anche nessuna); oltre, i dati sono da riassumere e si
    # torna al modello («non_coperto», come prima). -1: nessun limite (i tool senza voci)
    voci_max: int = -1
    # Una lettura senza frase pronta nel risultato (agenda_elenca): la frase composta dalle voci,
    # senza scegliere niente (tutte, nell'ordine del tool). None: la frase dai `campi`
    componi: object = None
    # La portata della lettura (revisione della PR #118): se la frase della persona nomina un
    # tempo che il risultato non copre (agenda_elenca dà gli appuntamenti dei soli due giorni),
    # al modello («fuori_portata»). None: nessun limite
    portata: object = None


_LETTURA = Copertura(("da_dire",), True)
_AZIONE = Copertura(("conferma",), False)
VOCI_MAX = 2            # le letture brevi: al più tante voci (16/10, issue #103)


_DI_ARTICOLO = (("il ", "del "), ("lo ", "dello "), ("la ", "della "), ("i ", "dei "),
                ("gli ", "degli "), ("le ", "delle "), ("l'", "dell'"), ("l’", "dell’"))


def _di(label: str) -> str:
    """«di» davanti a ciò che dice il promemoria, con la preposizione articolata: «di chiamare
    Ugo», «della medicina», «dell'acqua» (non «di la medicina»)."""
    low = label.lower()
    for art, prep in _DI_ARTICOLO:
        if low.startswith(art) and len(label) > len(art):
            return prep + label[len(art):]
    return "di " + label


def _voce_agenda(v: dict) -> str:
    """Una voce di agenda_elenca detta a voce (come _voce_detta di tools/builtin.py)."""
    if not isinstance(v, dict):
        return ""
    if "timer" in v:
        label = str(v.get("timer") or "").strip()
        mancano = str(v.get("mancano") or "").strip()
        if re.match(r"0\s", mancano):        # «fra 0 secondi»
            resto = ", che sta per scadere"
        else:
            resto = f", che scade fra {mancano}" if mancano else ""
        return f"il timer {label}".strip() + resto
    quando = f", {v['quando']}" if v.get("quando") else ""
    if "promemoria" in v:
        label = str(v.get("promemoria") or "").strip()
        return (f"il promemoria {_di(label)}" if label else "il promemoria") + quando
    if "appuntamento" in v:
        label = str(v.get("appuntamento") or "").strip()
        return (f"l'appuntamento «{label}»" if label else "l'appuntamento") + quando
    return ""


def frase_agenda(res: dict) -> str:
    """La frase di agenda_elenca (al più VOCI_MAX voci, lo controlla il decisore); "" se una
    voce non si sa dire. Gli appuntamenti nel risultato sono solo dei prossimi due giorni: la
    frase lo dice sempre, anche con le voci (revisione della PR #118)."""
    voci = res.get("voci")
    if not isinstance(voci, list):
        return ""
    if not voci:
        return ("Non c'è niente: nessun timer, nessun promemoria e nessun appuntamento nei "
                "prossimi due giorni.")
    dette = [_voce_agenda(v) for v in voci]
    if not all(dette):
        return ""
    if len(dette) == 1:
        frase = f"C'è {dette[0]}"
    else:
        frase = "Ci sono " + ", ".join(dette[:-1]) + ", e " + dette[-1]
    if any(isinstance(v, dict) and "appuntamento" in v for v in voci):
        return frase + ". Gli appuntamenti sono quelli dei prossimi due giorni."
    return frase + ", e nessun appuntamento nei prossimi due giorni."


# Un tempo oltre domani nella frase della persona (revisione della PR #118): un giorno della
# settimana, la settimana, il mese, un mese per nome, «dopodomani», «prossimi giorni», una data
# o un numero. Vincolo verso il modello (nel dubbio la seconda passata, come prima)
_OLTRE_DOMANI = re.compile(
    r"\b(?:(?:lune|marte|mercole|giove|vener)d[iì]|sabat[oi]|domenic[ah]e?|settiman\w*|"
    r"mes[ei]|weekend|week-end|dopodomani|giorni|anno|prossim\w*|gennaio|febbraio|marzo|"
    r"aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\b|\d", re.I)


# La lista letta ha già la sua `conferma` («Nella lista della spesa ci sono 2 cose: latte e
# uova.»); l'agenda no, la frase si compone dalle voci
_LISTA_BREVE = Copertura(("conferma",), True, voci_max=VOCI_MAX)
_AGENDA_BREVE = Copertura((), True, voci_max=VOCI_MAX, componi=frase_agenda,
                          portata=_OLTRE_DOMANI)

# L'elenco chiuso (15/10): esiti semplici, con una frase scritta dal tool. `casa_comando` non c'è
# perché ha già la sua `risposta_finale` (la frase di Home Assistant, senza seconda passata dal
# 27/09): nel registro è «gia_pronta». Fuori, di proposito: le letture con dati da riassumere
# (appuntamenti_elenca, casa_stato, meteo; lista_leggi e agenda_elenca oltre due voci), la
# memoria (ricorda, dimentica: il modello sceglie cosa dire del fatto), le voci e i toni
# (cambia_voce). Dal 16/10 (issue #103) la lista e l'agenda lette fino a due voci o vuote: nel
# caso vero della prima sera in ombra la `conferma` della lista era uguale a ciò che ha detto
# il modello
COPERTI: dict[str, Copertura] = {
    "ora_attuale": _LETTURA,
    "data_oggi": _LETTURA,
    "calcola": Copertura(("da_dire",), True, "Fa {}."),
    "data_calcola": _LETTURA,
    "timer_imposta": _AZIONE,
    "promemoria_imposta": _AZIONE,
    "appuntamento_aggiungi": _AZIONE,
    "agenda_annulla": _AZIONE,
    "lista_aggiungi": _AZIONE,
    "lista_togli": _AZIONE,
    "pc_volume": _AZIONE,
    "pc_media": _AZIONE,
    "pc_luminosita": _AZIONE,
    "lista_leggi": _LISTA_BREVE,
    "agenda_elenca": _AGENDA_BREVE,
}

# Campi di un risultato riuscito che chiedono al modello di fare o spiegare altro
_DA_SPIEGARE = ("cosa_fare", "cosa_dire", "in_sospeso", "nome_incerto", "errore",
                "risposta_finale")


@dataclass(frozen=True)
class Esito:
    """Ciò che serve al decisore, preparato da Brain dopo l'esecuzione dei tool della prima
    passata: la frase della persona, i tool chiamati e i loro risultati (dizionari, già senza le
    schede), il testo del modello già detto o tenuto in questa risposta, se parla un minore, il
    tono del turno e i dubbi di struttura che Brain conosce (nomi brevi)."""
    testo: str
    chiamate: tuple = ()
    risultati: tuple = ()
    detto_prima: str = ""
    minore: bool = False
    tono: str = "normale"
    dubbi: tuple = ()


@dataclass(frozen=True)
class Scelta(Decisione):
    perche: str = ""
    tool: str = ""
    frase: str = ""


def _ok(res) -> bool:
    return isinstance(res, dict) and "errore" not in res and res.get("ok") is not False


def frasi_della_persona(testo: str) -> int:
    """Quante frasi ha la frase della persona (dal segno di fine seguito da altro testo)."""
    parti = re.split(r"(?<=[.!?…;])\s+", str(testo or "").strip())
    return sum(1 for p in parti if re.search(r"[^\W\d_]", p))


# Le frasi d'apertura che non chiedono niente (16/10, issue #103): riconosciute solo in forma
# chiusa e per intero (principio 10). Una frase fatta solo di queste parole («Perfetto.»,
# «Grazie.», «Allora, Calliope.»), oppure l'annuncio di ciò che segue con l'oggetto anch'esso
# chiuso («Allora, iniziamo con un calcolo.»; non «Iniziamo con un timer da dieci minuti.», che
# chiede già). Le parole d'assenso («sì», «certo», «esatto», «giusto», «va bene», «d'accordo»,
# «ok») non ci sono, come «no»: possono rispondere a una domanda del turno prima (revisione
# della PR #118)
_APERTURE = frozenset("""allora perfetto perfetta bene benissimo ottimo ottima grazie ecco
dunque bravo brava bravissima bravissimo calliope ciao senti ascolta quindi beh mah ehm uhm eh
oh""".split())
_ANNUNCIO = re.compile(
    r"(?:(?:allora|bene|dunque|ecco|perfetto|calliope)[\s,]+)*(?:ora\s+|adesso\s+)?"
    r"(?:iniziamo|cominciamo|partiamo|ricominciamo)\s+con\s+"
    r"(?:un\s+calcolo|un\s+conto|un\s+esercizio|un\s+problema|una\s+domanda|"
    r"il\s+primo(?:\s+esercizio|\s+calcolo)?|la\s+prima(?:\s+domanda)?)", re.I)


def senza_richiesta(frase: str) -> bool:
    """Una frase della persona che non chiede niente: nessun punto di domanda, nessuna cifra, e
    tutta fatta di parole d'apertura oppure un annuncio chiuso («Allora, iniziamo con un
    calcolo.»). Solo la forma, per intero: una parola d'apertura dentro una frase non basta."""
    f = str(frase or "").strip().rstrip(".!…;").strip()
    if not f or "?" in f or re.search(r"\d", f):
        return False
    w = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", f.lower())
    if w and all(x in _APERTURE for x in w):
        return True
    return bool(_ANNUNCIO.fullmatch(f))


def richieste_della_persona(testo: str) -> int:
    """Quante frasi della persona chiedono qualcosa: le frasi (come frasi_della_persona) meno
    quelle d'apertura (senza_richiesta)."""
    parti = re.split(r"(?<=[.!?…;])\s+", str(testo or "").strip())
    return sum(1 for p in parti if re.search(r"[^\W\d_]", p) and not senza_richiesta(p))


def parole(testo: str) -> int:
    return len(re.findall(r"[^\W_]+(?:'[^\W_]+)?", str(testo or "")))


class DopoTool:
    """Il decisore a regole: «codice» solo quando tutto è chiuso, altrimenti «modello»."""
    nome = "dopo_tool"
    scelte = (CODICE, MODELLO)

    def __init__(self, parole_max: int = PAROLE_MAX, coperti: dict | None = None):
        self.parole_max = int(parole_max)
        self.coperti = dict(COPERTI if coperti is None else coperti)

    def _modello(self, perche: str, tool: str = "") -> Scelta:
        return Scelta(MODELLO, 1.0, perche=perche, tool=tool)

    def decide(self, e: Esito) -> Scelta:
        if e.dubbi:
            return self._modello(f"dubbio_{e.dubbi[0]}")
        if not e.chiamate:
            return self._modello("nessun_tool")
        if len(e.chiamate) > 1:
            return self._modello("piu_tool", e.chiamate[0])
        tool = e.chiamate[0]
        cop = self.coperti.get(tool)
        if cop is None:
            return self._modello("non_coperto", tool)
        res = e.risultati[0] if e.risultati else None
        if not _ok(res):
            return self._modello("tool_fallito", tool)
        if any(k in res for k in _DA_SPIEGARE):
            return self._modello("da_spiegare", tool)
        if cop.voci_max >= 0:
            # Una lettura breve (16/10): senza la lista delle voci, o con più voci, al modello
            voci = res.get("voci")
            if not isinstance(voci, list) or len(voci) > cop.voci_max:
                return self._modello("non_coperto", tool)
        if cop.portata is not None and cop.portata.search(str(e.testo or "")):
            return self._modello("fuori_portata", tool)
        if cop.componi is not None:
            frase = str(cop.componi(res) or "").strip()
        else:
            frase = next((res[k].strip() for k in cop.campi
                          if isinstance(res.get(k), str) and res[k].strip()), "")
        if not frase:
            return self._modello("senza_frase", tool)
        frase = cop.forma.format(frase)
        if not re.search(r"[.!?…]$", frase):
            frase += "."
        if len(frase) > FRASE_MAX:
            return self._modello("frase_lunga", tool)
        if (e.detto_prima or "").strip():
            return self._modello("testo_del_modello", tool)
        if e.minore:
            return self._modello("minore", tool)
        if e.tono not in TONI:
            return self._modello("tono", tool)
        testo = str(e.testo or "")
        # Più richieste (16/10, issue #103: prima più frasi, anche con «Perfetto.» davanti)
        if richieste_della_persona(testo) > 1:
            return self._modello("piu_frasi", tool)
        if parole(testo) > self.parole_max:
            return self._modello("persona_lunga", tool)
        if "?" in testo and not cop.domanda:
            return self._modello("domanda", tool)
        return Scelta(CODICE, 1.0, perche="esito_chiuso", tool=tool, frase=frase)


def modo(cfg) -> str:
    m = str(getattr(cfg, "system1_dopo_tool", SPENTO) or SPENTO).strip().lower()
    return m if m in MODI else SPENTO


def crea(cfg, log=print) -> Sorvegliato:
    return Sorvegliato(DopoTool(int(getattr(cfg, "system1_dopo_tool_parole_max", PAROLE_MAX)
                                    or PAROLE_MAX)), log=log)


# ─────────────────────────── la sostanza (ombra) ───────────────────────────
_UNITA = {"zero": 0, "un": 1, "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4,
          "cinque": 5, "sei": 6, "sette": 7, "otto": 8, "nove": 9, "dieci": 10, "undici": 11,
          "dodici": 12, "tredici": 13, "quattordici": 14, "quindici": 15, "sedici": 16,
          "diciassette": 17, "diciotto": 18, "diciannove": 19, "cento": 100, "mille": 1000,
          "mezzogiorno": 12, "mezzanotte": 0}
_DECINE = {"venti": 20, "trenta": 30, "quaranta": 40, "cinquanta": 50, "sessanta": 60,
           "settanta": 70, "ottanta": 80, "novanta": 90}
_COD_UNITA = {"uno": 1, "due": 2, "tre": 3, "tré": 3, "quattro": 4, "cinque": 5, "sei": 6,
              "sette": 7, "otto": 8, "nove": 9}
_VUOTE = frozenset("""fatto bene sono della delle dello degli dell nella nelle negli alla alle
allo agli dalla dalle dagli questo questa quello quella quindi ancora perché come cosa
c'era c'erano ecco certo""".split())


def _numero_parola(w: str) -> int | None:
    if w in _UNITA:
        return _UNITA[w]
    for d, v in _DECINE.items():
        radice = d[:-1]                       # «vent», «trent»: ventuno, trentotto
        if w == d:
            return v
        for pref in (d, radice):
            if w.startswith(pref) and w[len(pref):] in _COD_UNITA:
                return v + _COD_UNITA[w[len(pref):]]
    return None


def numeri(testo: str) -> set:
    """I numeri di una frase, in cifre o (fino a 99, più cento e mille) in parole."""
    t = str(testo or "").lower()
    out = {int(x) for x in re.findall(r"\d+", t)}
    for w in re.findall(r"[a-zàèéìòù]+", t):
        n = _numero_parola(w)
        if n is not None:
            out.add(n)
    return out


def _parole_piene(testo: str) -> set:
    t = str(testo or "").lower().replace("%", " per cento")
    return {w[:5] for w in re.findall(r"[a-zàèéìòù']+", t)
            if len(w) >= 4 and w not in _VUOTE and _numero_parola(w) is None}


def sostanza(frase_codice: str, testo_modello: str) -> dict:
    """La frase del modello dice la stessa cosa del codice? Un'approssimazione per la misura,
    non una regola: tutti i numeri della frase del codice nella frase del modello (in cifre o in
    parole) e almeno metà delle sue parole piene (prime 5 lettere). {numeri, copertura, uguale}."""
    nc = numeri(frase_codice)
    nm = numeri(str(testo_modello or "").replace("%", " per cento"))
    num_ok = nc <= nm
    pc = _parole_piene(frase_codice)
    pm = _parole_piene(testo_modello)
    cop = 1.0 if not pc else len(pc & pm) / len(pc)
    return {"numeri": num_ok, "copertura": round(cop, 2), "uguale": bool(num_ok and cop >= 0.5)}


FINE_FRASE = re.compile(r"[.!?…](\s|$)")


# ─────────────────────────────── riassunto ───────────────────────────────
def _p(valori, q):
    v = sorted(valori)
    return v[min(len(v) - 1, int(q * len(v)))] if v else None


def riassunto(turni: list[dict]) -> dict:
    """Dai turni con `dopo_tool`: risposte con tool viste, quante «codice» (ombra e attivo),
    quante già pronte, i perché del modello, e per l'ombra il tempo risparmiabile (prima frase
    della seconda passata), quante uguali nella sostanza, quante con una domanda o un altro tool
    del modello nella seconda passata."""
    n = codice = attivo = pronte = 0
    perche, tool_c = {}, {}
    risp, uguali, diverse, domande, altri, ms = [], 0, 0, 0, 0, []
    for t in turni:
        d = t.get("dopo_tool")
        if not isinstance(d, dict) or "esito" not in d:
            continue
        n += 1
        es = d["esito"]
        if es == "gia_pronta":
            pronte += 1
            continue
        if isinstance(d.get("ms"), (int, float)):
            ms.append(d["ms"])
        if es != CODICE:
            k = str(d.get("perche") or es)
            perche[k] = perche.get(k, 0) + 1
            continue
        codice += 1
        tool_c[d.get("tool") or "?"] = tool_c.get(d.get("tool") or "?", 0) + 1
        if d.get("modo") == ATTIVO:
            attivo += 1
            continue
        if isinstance(d.get("prima_frase_ms"), (int, float)):
            risp.append(d["prima_frase_ms"])
        if d.get("uguale") is True and not d.get("domanda") and not d.get("altro_tool"):
            uguali += 1
        elif "uguale" in d:
            diverse += 1
        domande += bool(d.get("domanda"))
        altri += bool(d.get("altro_tool"))
    return {"risposte": n, "codice": codice, "attivo": attivo, "gia_pronte": pronte,
            "perche": sorted(perche.items(), key=lambda kv: -kv[1])[:8],
            "tool": sorted(tool_c.items(), key=lambda kv: -kv[1])[:8],
            "ombra": codice - attivo, "uguali": uguali, "diverse": diverse,
            "domande": domande, "altri_tool": altri,
            "risparmio_p50_ms": _p(risp, .5), "risparmio_p90_ms": _p(risp, .9),
            "risparmio_s": round(sum(risp) / 1000, 1) if risp else 0.0,
            "ms_p50": _p(ms, .5), "ms_p90": _p(ms, .9)}


def testo(r: dict) -> str:
    if not r.get("risposte"):
        return ("Frase dopo il tool (System 1): nessuna risposta con tool misurata "
                "(system1_dopo_tool: spento).")
    righe = [f"Frase dopo il tool (System 1): {r['risposte']} risposte con tool, frase del codice "
             f"in {r['codice']} ({100 * r['codice'] / r['risposte']:.0f} %; attivo {r['attivo']}, "
             f"ombra {r['ombra']}), già pronte dal tool {r['gia_pronte']}"
             + (f"; tool: " + ", ".join(f"{k} ×{v}" for k, v in r["tool"]) if r["tool"] else "")]
    if r["perche"]:
        righe.append("    al modello: " + ", ".join(f"{k} ×{v}" for k, v in r["perche"]))
    if r["ombra"]:
        righe.append(
            f"    ombra: uguali nella sostanza {r['uguali']}, diverse {r['diverse']} (con una "
            f"domanda {r['domande']}, con un altro tool {r['altri_tool']}); seconda passata "
            f"risparmiabile p50 {r['risparmio_p50_ms'] if r['risparmio_p50_ms'] is not None else '—'} ms, "
            f"p90 {r['risparmio_p90_ms'] if r['risparmio_p90_ms'] is not None else '—'} ms, "
            f"{r['risparmio_s']} s in tutto; decisore p50 "
            f"{r['ms_p50'] if r['ms_p50'] is not None else '—'} ms")
        conf = r["uguali"] + r["diverse"]
        if conf >= 20 and r["diverse"] / conf > 0.05:
            righe.append("    ATTENZIONE: oltre il 5 % delle frasi del codice diverse da quelle del "
                         "modello (da rileggere prima di «attivo»)")
        if r["altri_tool"]:
            righe.append(f"    ATTENZIONE: in {r['altri_tool']} risposte il modello ha chiamato "
                         f"un altro tool dopo: in «attivo» quell'azione non sarebbe partita")
    return "\n".join(righe)
