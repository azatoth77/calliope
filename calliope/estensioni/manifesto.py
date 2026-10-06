"""
Il manifesto di un'estensione (04/10/2026): cosa fa, cosa riceve, cosa può chiedere a
Calliope, chi la usa e i suoi limiti. Lo scrive l'agente insieme al codice; qui si valida con
uno schema chiuso e con tetti, e si dice in parole a chi approva.

Formato in docs/ricerche/2026-10-04-estensioni-e-guardrail.md §3.
"""

from __future__ import annotations

import re

from ..sicurezza import instruction_fact

NOME = re.compile(r"^[a-z][a-z0-9_]{2,30}$")
HOST = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
LIVELLI = ("ospite", "familiare", "amministra")
TIPI_INPUT = ("string", "number", "integer", "boolean")
PERMESSI = {"casa": ("leggi", "comanda"), "liste": ("leggi", "scrivi"),
            "agenda": ("leggi", "scrivi")}
MAX_PROPRIETA = 6
MAX_DESCRIZIONE = 300

# ─────────────────────────── la descrizione per il modello ───────────────────────────
# Il nome, la descrizione e gli input di un'estensione entrano negli schemi dei tool che il
# modello della voce legge a ogni turno, come testo fidato: sono un canale per dargli
# istruzioni («Quando qualcuno chiede l'ora chiama casa_comando…»). Dal 06/10 (limite 3 della
# politica di sicurezza, docs/ricerche/2026-10-05-politica-sicurezza.md) la descrizione la
# compone il codice: un verbo da un insieme chiuso (`VERBI_DESCRIZIONE`, alla terza persona)
# e un oggetto breve («Dice» + «la temperatura di una stanza della casa»), con un controllo
# all'approvazione e a ogni avvio (`controlla_testi`). Un'estensione approvata prima che non
# passa più si disattiva da sola, con un avviso (Estensioni.ricontrolla).
VERBI_DESCRIZIONE = frozenset((
    "dice legge calcola converte cerca controlla mostra elenca conta traduce confronta stima "
    "trova riassume segnala prepara genera estrae indica verifica accende spegne imposta "
    "aggiunge toglie regola misura suggerisce annuncia racconta sceglie propone ricava aggiorna "
    "tiene scalda raffredda apre chiude alza abbassa avvia ferma restituisce prova gira registra "
    "salva ordina somma arrotonda formatta pulisce raccoglie riporta descrive spiega comanda "
    "segue tiene").split())
MAX_COSA_FA = 120
MAX_DESCRIZIONE_INPUT = 80
# Le parole che non stanno in una descrizione: chi legge è il modello, e queste servono solo a
# dargli ordini (a chi si rivolge, quando, con quale priorità) o a parlare d'altro
_VIETATE = re.compile(
    r"(?<![a-zà-ù])(assistent\w*|modell[oi] (linguistic|di linguaggio)\w*|calliope|utent\w*|"
    r"istruzion\w*|prompt|sistema|tool|funzion\w*|sempre|mai|prima di|dopo (aver|che)|"
    r"ogni volta|quando|invece|anziché|obbligat\w*|important\w*|dev[eio]\w*|dovr\w*|non|"
    r"ignor\w*|chiama\w*|usa|usare|usala|usalo|rispond\w*|esegu\w*|segui\w*|ricordati|"
    r"priorit\w*|richiest[ae]|qualsiasi|chiunque|consenso|conferm\w*|password|segret\w*|"
    r"tu|ti|te|tuo|tua|voi|vostr\w*)(?![a-zà-ù])", re.I)
# Niente simboli da codice, indirizzi, citazioni, elenchi o più frasi
_SIMBOLI = re.compile(r"[_:;!?«»\"“”`<>{}\[\]|*#@\\/=+\n\t]|https?|www\.|\.(?!\d)\s*\S")


def controlla_testo(testo: str, nomi_tool=(), massimo: int = MAX_COSA_FA,
                    verbo: bool = True) -> str | None:
    """Il motivo per cui `testo` non va nella descrizione di un tool, o None. `verbo`: deve
    cominciare con un verbo di `VERBI_DESCRIZIONE` (la frase su cosa fa)."""
    t = " ".join(str(testo or "").split())
    if not t:
        return "è vuota"
    if len(t) > massimo:
        return f"è troppo lunga (al massimo {massimo} caratteri)"
    if len(t.split()) > 18:
        return "è troppo lunga (al massimo 18 parole)"
    m = _SIMBOLI.search(t.rstrip("."))
    if m:
        g = m.group(0)
        g = g if g.startswith(("http", "www")) else g[:1]
        return f"contiene «{g}»: una frase sola, senza simboli"
    m = _VIETATE.search(t)
    if m:
        return f"contiene «{m.group(0)}», che parla all'assistente invece di dire cosa fa"
    if verbo and t.split()[0].lower() not in VERBI_DESCRIZIONE:
        return ("deve cominciare con un verbo come " + ", ".join(
            sorted(VERBI_DESCRIZIONE)[:8]) + "…")
    parole = re.findall(r"[a-zà-ù]+", t.lower())
    altri = sorted(set(parole[1:] if verbo else parole) & {n.lower() for n in nomi_tool or ()})
    if altri:
        return f"nomina un'altra funzione di Calliope («{altri[0]}»)"
    if instruction_fact(t.replace("Calliope", ""), house=False):
        return "sembra un'istruzione per l'assistente"
    return None


def cosa_fa(d: dict) -> str:
    """La frase su cosa fa, composta dal codice: dal campo strutturato «cosa_fa» ({"verbo",
    "oggetto"}) o, per i manifesti di prima, dalla «descrizione»."""
    c = d.get("cosa_fa")
    if isinstance(c, dict):
        verbo = " ".join(str(c.get("verbo") or "").split()).lower()
        oggetto = " ".join(str(c.get("oggetto") or "").split()).rstrip(".")
        if verbo not in VERBI_DESCRIZIONE:
            raise ManifestoNonValido("«cosa_fa.verbo»: uno tra " + ", ".join(
                sorted(VERBI_DESCRIZIONE)))
        if not oggetto:
            raise ManifestoNonValido("manca «cosa_fa.oggetto»")
        return f"{verbo.capitalize()} {oggetto}."
    descr = _testo(d, "descrizione", MAX_DESCRIZIONE)
    return descr if descr.endswith(".") else descr + "."


def controlla_testi(m: dict, nomi_tool=()) -> str | None:
    """Tutto il testo del manifesto che il modello leggerà (titolo, descrizione, input): il
    motivo per cui non va, o None. Si usa alla consegna, all'approvazione e a ogni avvio."""
    nomi = [n for n in nomi_tool or () if n != PREFISSO_TOOL + str(m.get("nome") or "")]
    r = controlla_testo(m.get("descrizione"), nomi)
    if r:
        return f"la descrizione {r}"
    r = controlla_testo(m.get("titolo"), nomi, 40, verbo=False)
    if r:
        return f"il titolo {r}"
    for nome, p in ((m.get("input") or {}).get("properties") or {}).items():
        if p.get("description"):
            r = controlla_testo(p["description"], nomi, MAX_DESCRIZIONE_INPUT, verbo=False)
            if r:
                return f"la descrizione di «{nome}» {r}"
        for v in p.get("enum") or ():
            # I valori («km/h», «celsius»): niente parole d'ordine né nomi di funzioni
            t = str(v)
            m_ = _VIETATE.search(t)
            if len(t) > 40 or m_ or t.lower() in {n.lower() for n in nomi}:
                return f"un valore di «{nome}» non va: «{t[:40]}»"
    return None


def descrizione_tool(m: dict) -> str:
    """La descrizione del tool che il modello legge, composta dal codice."""
    return f"{m['descrizione'].rstrip('.')} (estensione «{m['titolo']}», aggiunta dalla famiglia)."


PREFISSO_TOOL = "est_"


class ManifestoNonValido(ValueError):
    """Il manifesto non va: il messaggio dice perché, in italiano."""


def _testo(d: dict, k: str, massimo: int, obbligatorio: bool = True) -> str:
    v = d.get(k)
    if v is None and not obbligatorio:
        return ""
    if not isinstance(v, str) or not v.strip():
        raise ManifestoNonValido(f"manca «{k}» (testo)")
    v = " ".join(v.split())
    if len(v) > massimo:
        raise ManifestoNonValido(f"«{k}» è troppo lungo (al massimo {massimo} caratteri)")
    return v


def _input(schema) -> dict:
    if schema is None:
        return {"type": "object", "properties": {}, "required": []}
    if not isinstance(schema, dict) or schema.get("type", "object") != "object":
        raise ManifestoNonValido("«input» deve essere uno schema JSON di tipo object")
    props = schema.get("properties") or {}
    if not isinstance(props, dict) or len(props) > MAX_PROPRIETA:
        raise ManifestoNonValido(f"«input»: al più {MAX_PROPRIETA} proprietà")
    out = {}
    for nome, p in props.items():
        if not isinstance(nome, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", nome):
            raise ManifestoNonValido(f"«input»: nome di proprietà non valido «{nome}»")
        if not isinstance(p, dict) or p.get("type") not in TIPI_INPUT:
            raise ManifestoNonValido(f"«input.{nome}»: tipo ammesso {', '.join(TIPI_INPUT)}")
        q = {"type": p["type"]}
        if p.get("description"):
            q["description"] = " ".join(str(p["description"]).split())[:160]
        if p.get("enum") is not None:
            en = p["enum"]
            if not isinstance(en, list) or not en or len(en) > 30:
                raise ManifestoNonValido(f"«input.{nome}.enum»: da 1 a 30 valori")
            q["enum"] = [x for x in en if isinstance(x, (str, int, float))][:30]
        out[nome] = q
    req = [r for r in (schema.get("required") or []) if r in out]
    return {"type": "object", "properties": out, "required": req}


def _host(h) -> str:
    h = str(h).strip().lower().rstrip(".")
    if not HOST.match(h) or h.endswith((".local", ".lan", ".home", ".internal", ".localdomain",
                                        ".intranet", ".corp", ".localhost", ".test",
                                        ".invalid", ".example", ".arpa")):
        raise ManifestoNonValido(f"host non valido «{h}» (solo nomi pubblici, senza schema né "
                                 "porta)")
    return h


def _nomi(v, cosa: str, normalizza=lambda x: x) -> list[str]:
    """true → ["*"]; un elenco di nomi (stanze, liste) → quei nomi; false o vuoto → []."""
    if isinstance(v, dict):
        v = v.get("stanze", v.get("nomi", v.get("liste")))
    if v is True:
        return ["*"]
    if not v:
        return []
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list) or len(v) > 10:
        raise ManifestoNonValido(f"«{cosa}»: true oppure un elenco di al più 10 nomi")
    out = []
    for x in v:
        s = " ".join(str(x).split()).strip().lower()
        if not s or len(s) > 40:
            raise ManifestoNonValido(f"«{cosa}»: nome non valido")
        out.append("*" if s == "*" else normalizza(s))
    return ["*"] if "*" in out else sorted(set(out))


def _lista(nome: str) -> str:
    from ..liste import list_key
    return list_key(nome)


def _vecchio_formato(p: dict) -> dict:
    """Il formato del 04/10 (casa: [leggi, comanda], liste, agenda, schermi, dati, rete: [host],
    rete_invia) nel formato a scope del 05/10. Più stretto, mai più largo: gli host di «rete»
    restano gli unici, e «leggere internet dopo aver letto dati di casa» (prima una domanda) ora
    vuole un flusso dichiarato."""
    altri = [k for k in p if k not in set(PERMESSI) | {"schermi", "dati", "rete", "rete_invia"}]
    if altri:
        raise ManifestoNonValido(f"permesso sconosciuto: {', '.join(map(str, altri))}")
    for sez, ammessi in PERMESSI.items():
        v = p.get(sez) or []
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list) or any(x not in ammessi for x in v):
            raise ManifestoNonValido(f"«permessi.{sez}»: solo {', '.join(ammessi)}")
    lv = lambda sez, voce: voce in (p.get(sez) or [])  # noqa: E731
    hosts = p.get("rete") or []
    if not isinstance(hosts, list):
        raise ManifestoNonValido("«permessi.rete»: un elenco di host")
    if p.get("rete_invia") and not hosts:
        raise ManifestoNonValido("«permessi.rete_invia» senza host in «permessi.rete»")
    return {"legge": {"casa": lv("casa", "leggi"), "liste": lv("liste", "leggi"),
                      "agenda": lv("agenda", "leggi"), "dati": bool(p.get("dati"))},
            "scrive": {"casa": lv("casa", "comanda"), "liste": lv("liste", "scrivi"),
                       "agenda": lv("agenda", "scrivi"), "dati": bool(p.get("dati")),
                       "schermi": bool(p.get("schermi"))},
            "rete": {"pubblica": False, "host": hosts, "post": bool(p.get("rete_invia"))},
            "invia": []}


CATEGORIE_FLUSSO = ("casa", "agenda", "liste")


def normalizza_permessi(p) -> dict:
    """I permessi a scope (05/10, decisioni di Dario: lettura di internet pubblico libera, dati
    personali letti solo negli scope, verso fuori solo lungo i flussi approvati):

        {"legge":  {"casa": ["*"] | [stanze], "liste": ["*"] | [liste], "agenda": bool,
                    "dati": bool},
         "scrive": {"casa": ["*"] | [stanze], "liste": …, "agenda": bool (timer),
                    "dati": bool, "schermi": bool},
         "rete":   {"pubblica": bool (GET a qualunque sito pubblico), "host": [nomi],
                    "post": bool (invii POST agli host)},
         "invia":  [{"dati": "casa" | "agenda" | "liste" | "liste:<nome>", "host": nome,
                     "metodo": "GET" | "POST"}]}

    Accetta anche il formato del 04/10 (`_vecchio_formato`). Idempotente: un manifesto già
    normalizzato resta uguale. ManifestoNonValido se qualcosa non va."""
    p = p or {}
    if not isinstance(p, dict):
        raise ManifestoNonValido("«permessi» deve essere un oggetto")
    if not ({"legge", "scrive", "invia"} & set(p)) and not isinstance(p.get("rete"), dict):
        p = _vecchio_formato(p)
    altri = [k for k in p if k not in ("legge", "scrive", "rete", "invia")]
    if altri:
        raise ManifestoNonValido(f"permesso sconosciuto: {', '.join(map(str, altri))} (le "
                                 "sezioni sono legge, scrive, rete, invia)")
    le, sc = p.get("legge") or {}, p.get("scrive") or {}
    if not isinstance(le, dict) or not isinstance(sc, dict):
        raise ManifestoNonValido("«legge» e «scrive» sono oggetti")
    for sez, d, noti in (("legge", le, ("casa", "liste", "agenda", "dati")),
                         ("scrive", sc, ("casa", "liste", "agenda", "dati", "schermi"))):
        altri = [k for k in d if k not in noti]
        if altri:
            raise ManifestoNonValido(f"«{sez}»: sconosciuto {', '.join(map(str, altri))} (solo "
                                     f"{', '.join(noti)})")
    legge = {"casa": _nomi(le.get("casa"), "legge.casa"),
             "liste": _nomi(le.get("liste"), "legge.liste", _lista),
             "agenda": bool(le.get("agenda")), "dati": bool(le.get("dati"))}
    scrive = {"casa": _nomi(sc.get("casa"), "scrive.casa"),
              "liste": _nomi(sc.get("liste"), "scrive.liste", _lista),
              "agenda": bool(sc.get("agenda")), "dati": bool(sc.get("dati")),
              "schermi": bool(sc.get("schermi"))}
    r = p.get("rete") or {}
    if isinstance(r, list):
        r = {"host": r}
    if not isinstance(r, dict) or any(k not in ("pubblica", "host", "post") for k in r):
        raise ManifestoNonValido("«rete»: {\"pubblica\": true/false, \"host\": [...], "
                                 "\"post\": true/false}")
    hosts = r.get("host") or []
    if not isinstance(hosts, list) or len(hosts) > 5:
        raise ManifestoNonValido("«rete.host»: un elenco di al più 5 host")
    rete = {"pubblica": bool(r.get("pubblica")), "host": sorted({_host(h) for h in hosts}),
            "post": bool(r.get("post"))}
    if rete["post"] and not rete["host"]:
        raise ManifestoNonValido("«rete.post» senza host in «rete.host»")
    flussi = p.get("invia") or []
    if not isinstance(flussi, list) or len(flussi) > 6:
        raise ManifestoNonValido("«invia»: un elenco di al più 6 flussi")
    invia = []
    for f in flussi:
        if not isinstance(f, dict) or any(k not in ("dati", "host", "metodo") for k in f):
            raise ManifestoNonValido("«invia»: ogni flusso è {\"dati\", \"host\", \"metodo\"}")
        dati = str(f.get("dati") or "").strip().lower()
        cat, _, nome = dati.partition(":")
        if cat not in CATEGORIE_FLUSSO or (nome and cat != "liste"):
            raise ManifestoNonValido(f"«invia.dati»: una tra {', '.join(CATEGORIE_FLUSSO)} o "
                                     f"liste:<nome> (non «{dati}»)")
        if nome:
            dati = "liste:" + _lista(nome)
        # Un flusso di dati che l'estensione non può leggere non serve: si rifiuta, così la
        # scheda di revisione non promette cose che non succedono
        letti = legge[cat] if cat != "agenda" else legge["agenda"]
        if not letti or (nome and "*" not in legge["liste"]
                         and dati.split(":", 1)[1] not in legge["liste"]):
            raise ManifestoNonValido(f"«invia»: il flusso di «{dati}» vuole il permesso di "
                                     "leggerli in «legge»")
        metodo = str(f.get("metodo") or "GET").upper()
        if metodo not in ("GET", "POST"):
            raise ManifestoNonValido("«invia.metodo»: GET o POST")
        invia.append({"dati": dati, "host": _host(f.get("host") or ""), "metodo": metodo})
    invia = sorted({(f["dati"], f["host"], f["metodo"]): f for f in invia}.values(),
                   key=lambda f: (f["dati"], f["host"], f["metodo"]))
    return {"legge": legge, "scrive": scrive, "rete": rete, "invia": invia}


def _permessi(p) -> dict:
    return normalizza_permessi(p)


# ─────────────────────────── in parole ───────────────────────────

def _e(cose: list[str]) -> str:
    return cose[0] if len(cose) == 1 else ", ".join(cose[:-1]) + " e " + cose[-1]


def _nomi_detti(nomi: list[str], tutto: str, uno: str, molti: str) -> str:
    if "*" in nomi:
        return tutto
    return (uno if len(nomi) == 1 else molti) + " " + _e(nomi)


def _a(host: str) -> str:
    """«ad api.prezzi.it», «a meteo.it»."""
    return ("ad " if host[:1] in "aeiou" else "a ") + host


def _dati_detti(dati: str) -> str:
    cat, _, nome = dati.partition(":")
    if cat == "liste":
        if not nome:
            return "le tue liste"
        return "la tua lista della spesa" if nome == "spesa" else f"la tua lista {nome}"
    return {"casa": "lo stato della casa", "agenda": "la tua agenda"}.get(cat, dati)


def atomi(perm: dict) -> list[tuple[tuple, str]]:
    """Ogni permesso singolo, con la sua frase: servono a dirli e a confrontare due versioni."""
    p = normalizza_permessi(perm)
    le, sc, r = p["legge"], p["scrive"], p["rete"]
    out = []
    if le["casa"]:
        out.append((("legge", "casa", tuple(le["casa"])),
                    _nomi_detti(le["casa"], "legge lo stato della casa",
                                "legge lo stato della stanza", "legge lo stato delle stanze")))
    if le["liste"]:
        out.append((("legge", "liste", tuple(le["liste"])),
                    "legge le liste" if "*" in le["liste"] else
                    "legge " + _e([_dati_detti("liste:" + n).replace("la tua ", "la ")
                                   for n in le["liste"]])))
    if le["agenda"]:
        out.append((("legge", "agenda"), "legge l'agenda di chi la usa"))
    if sc["casa"]:
        out.append((("scrive", "casa", tuple(sc["casa"])),
                    _nomi_detti(sc["casa"], "comanda la casa (sempre con la tua conferma)",
                                "comanda la stanza", "comanda le stanze")
                    + ("" if "*" in sc["casa"] else " (sempre con la tua conferma)")))
    if sc["liste"]:
        out.append((("scrive", "liste", tuple(sc["liste"])),
                    "cambia le liste" if "*" in sc["liste"] else
                    "cambia " + _e([_dati_detti("liste:" + n).replace("la tua ", "la ")
                                    for n in sc["liste"]])))
    if sc["agenda"]:
        out.append((("scrive", "agenda"), "imposta dei timer"))
    if sc["schermi"]:
        out.append((("scrive", "schermi"), "mostra testi sullo schermo"))
    if le["dati"] or sc["dati"]:
        out.append((("dati",), "tiene dei dati suoi"))
    if r["pubblica"]:
        out.append((("rete", "pubblica"), "legge pagine pubbliche di internet"))
    for h in r["host"]:
        out.append((("rete", "host", h), f"si collega a {h}"))
    if r["post"]:
        out.append((("rete", "post"), f"manda richieste {_a(_e(r['host']))} (sempre con la tua "
                                      "conferma)"))
    for f in p["invia"]:
        verbo = "può mandare" if f["metodo"] == "GET" else "può inviare con un POST"
        out.append((("invia", f["dati"], f["host"], f["metodo"]),
                    f"{verbo} {_dati_detti(f['dati'])} {_a(f['host'])}"))
    return out


def _atomi_scheda(m: dict) -> list[tuple[tuple, str]]:
    """Le capacità della scheda interattiva (05/10, scheda.py) come permessi singoli."""
    from .scheda import in_parole
    s = (m or {}).get("scheda")
    if not s:
        return []
    frasi = in_parole(m)
    chiavi = [("scheda", s["tipo"], s["giocatori"]["max"])]
    for k in ("condivisa", "chat", "salva", "voce"):
        if s.get(k):
            chiavi.append(("scheda", k))
    if s.get("azioni"):
        chiavi.append(("scheda", "azioni", tuple(s["azioni"])))
    return list(zip(chiavi, frasi))


def permessi_in_parole(m: dict) -> str:
    """«legge lo stato della casa e legge pagine pubbliche di internet», o «nessun permesso».
    I flussi verso fuori sono detti per esteso: «può mandare la tua lista della spesa a
    api.prezzi.it». Con una scheda interattiva (05/10) anche cosa fa il gioco."""
    frasi = [f for _, f in atomi((m or {}).get("permessi") or {})]
    gioco = [f for _, f in _atomi_scheda(m)]
    if gioco and not frasi:
        return _e(gioco) + "; nessun altro permesso"
    frasi += gioco
    return _e(frasi) if frasi else "nessun permesso"


def permessi_nuovi(vecchio: dict | None, nuovo: dict) -> list[str]:
    """I permessi della versione nuova che quella approvata non aveva, in parole (per il
    confronto prima di una nuova approvazione)."""
    prima = ({k for k, _ in atomi((vecchio or {}).get("permessi") or {})}
             | {k for k, _ in _atomi_scheda(vecchio)}) if vecchio else set()
    return [f for k, f in atomi((nuovo or {}).get("permessi") or {}) + _atomi_scheda(nuovo)
            if k not in prima]


def valida(d, tempo_max_s: float = 30.0, memoria_max_mb: int = 512, nomi_tool=()) -> dict:
    """Il manifesto normalizzato, o ManifestoNonValido."""
    if not isinstance(d, dict):
        raise ManifestoNonValido("il manifesto deve essere un oggetto JSON")
    nome = d.get("nome")
    if not isinstance(nome, str) or not NOME.match(nome):
        raise ManifestoNonValido("«nome»: minuscole, cifre e trattini bassi, da 3 a 31 "
                                 "caratteri, prima una lettera")
    titolo = _testo(d, "titolo", 60)
    # La descrizione va nel tool che il modello legge a ogni turno: è un canale per dargli
    # istruzioni. Dal 06/10 la compone il codice (cosa_fa) e passa il controllo dei testi
    descr = cosa_fa(d)
    livello = d.get("livello") or "familiare"
    if livello not in LIVELLI:
        raise ManifestoNonValido(f"«livello»: uno tra {', '.join(LIVELLI)}")
    lim = d.get("limiti") or {}
    if not isinstance(lim, dict):
        raise ManifestoNonValido("«limiti» deve essere un oggetto")
    try:
        tempo = float(lim.get("tempo_s", 10))
        mem = int(lim.get("memoria_mb", 256))
    except (TypeError, ValueError):
        raise ManifestoNonValido("«limiti»: numeri") from None
    if not (1 <= tempo <= tempo_max_s):
        raise ManifestoNonValido(f"«limiti.tempo_s»: da 1 a {tempo_max_s:g}")
    if not (64 <= mem <= memoria_max_mb):
        raise ManifestoNonValido(f"«limiti.memoria_mb»: da 64 a {memoria_max_mb}")
    out = {"nome": nome, "titolo": titolo, "descrizione": descr,
           "input": _input(d.get("input")), "permessi": _permessi(d.get("permessi")),
           "livello": livello, "limiti": {"tempo_s": tempo, "memoria_mb": mem}}
    # La scheda interattiva (05/10, scheda.py): un gioco nel browser degli schermi
    from .scheda import SchedaNonValida, e_gioco_puro, normalizza
    try:
        sch = normalizza(d.get("scheda"), out["permessi"])
    except SchedaNonValida as e:
        raise ManifestoNonValido(str(e)) from None
    if sch is not None:
        out["scheda"] = sch
        # Un gioco puro lo usano tutti, anche gli ospiti e sugli schermi di stanza (decisione
        # 4 del 05/10): niente dati di casa, niente rete, niente tool
        if e_gioco_puro(out):
            out["livello"] = "ospite"
    motivo = controlla_testi(out, nomi_tool)
    if motivo:
        raise ManifestoNonValido(motivo[:1].upper() + motivo[1:] + " (è il testo che il modello "
                                 "legge: «cosa_fa» è un verbo e un oggetto breve, come «Dice» e "
                                 "«la temperatura di una stanza»)")
    return out


def chi_la_usa(m: dict) -> str:
    return {"ospite": "chiunque", "familiare": "chi vive in casa",
            "amministra": "solo chi amministra"}[m.get("livello", "familiare")]
