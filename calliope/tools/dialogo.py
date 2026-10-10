"""
Il dialogo tra i tool e i modelli (09/10/2026, docs/ricerche/2026-10-09-dialogo-tool.md).

Un tool che non parte, o che si ferma, risponde al modello con un messaggio che il modello
può leggere e usare: che cosa non va (quale argomento, perché), che cosa si aspettava lo
schema (tipo, valori ammessi, la descrizione dell'argomento), un esempio di chiamata giusta
e che cosa fare adesso (`cosa_fare`: richiamare corretto, oppure chiedere il dato alla
persona se dalla frase non si ricava). Mai una traccia Python.

Caso vero (DGX, 09/10 08:19): «Raccontami le ultime novità della giornata» →
`web_cerca({'tipo': 'notizie'})` → «argomenti non validi: _web_cerca() missing 1 required
positional argument: 'domanda'»; il modello diceva «ho avuto un piccolo intoppo, riprovo
subito» senza riprovare, quattro volte di fila. Nessuna regola per quel caso: la
validazione è dello schema, uguale per tutti i tool (anche le estensioni `est_*` e gli
strumenti dell'agente), e il giro di correzione è in Brain (`correggibile`).

Forma comune di un errore: {ok: false, fatto: NIENTE, errore: <frase chiara>, campo?,
argomenti?, esempio?, correggibile: bool, cosa_fare}.
"""

import inspect
import json
import re
import unicodedata

from ..testi import NIENTE

# Le frasi d'attesa quando i giri di correzione si allungano (Brain, 09/10): una per risposta,
# solo se non si è ancora detto niente. Si sintetizzano all'avvio con gli annunci dei tool
FRASI_CORREZIONE = ("Un attimo, sistemo la richiesta.", "Un momento, ci riprovo.")

# I nomi dei tipi dello schema, come li legge il modello
_TIPI = {"string": "testo", "integer": "numero intero", "number": "numero",
         "boolean": "vero o falso", "array": "elenco", "object": "oggetto"}
_VERO = {"true", "sì", "si", "vero", "1", "yes"}
_FALSO = {"false", "no", "falso", "0"}
# Le eccezioni che sono errori di programmazione del tool: il messaggio non dice niente al
# modello (e può contenere nomi interni), solo che il tool si è fermato
_INTERNE = (TypeError, AttributeError, KeyError, IndexError, NameError, AssertionError,
            ZeroDivisionError, RecursionError, UnboundLocalError, ImportError)
DESCRIZIONE_MAX = 220


def _piano(s) -> str:
    """Minuscolo, senza accenti né spazi ai lati («Età » → «eta»)."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return s.strip().lower()


def _vuoto(v) -> bool:
    """Assente, vuoto, o un testo senza una lettera né una cifra («…», «.», «?»): un testo di
    sola punteggiatura non è un valore (10/10, quarto giro della DGX: una ricerca con «…» al
    posto del nome; il campo vuoto ha l'errore strutturato, non arriva al tool come testo)."""
    return v is None or (isinstance(v, str) and not any(c.isalnum() for c in v))


def firma(func):
    """(parametri con nome, quelli senza valore predefinito, accetta **kw?) della funzione
    di un tool, senza il primo (il contesto) né quelli privati («_n» delle estensioni).
    None se la firma non si legge."""
    try:
        params = list(inspect.signature(func).parameters.values())[1:]
    except (TypeError, ValueError):
        return None
    varkw = any(p.kind == p.VAR_KEYWORD for p in params)
    nominati = [p for p in params if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
                and not p.name.startswith("_")]
    return ({p.name for p in nominati}, {p.name for p in nominati if p.default is p.empty},
            varkw)


def descrizione_argomento(nome: str, prop: dict, descrizione_tool: str = "") -> str:
    """La descrizione di un argomento: quella dello schema o, se manca, il pezzo della
    descrizione del tool che comincia con «nome:» (molti tool la scrivono lì)."""
    d = (prop or {}).get("description")
    if isinstance(d, str) and d.strip():
        return d.strip()[:DESCRIZIONE_MAX]
    m = re.search(r"(?<![\w])" + re.escape(nome) + r"\s*:\s*(.+)", descrizione_tool or "",
                  re.S)
    if not m:
        # Senza «nome:», la frase della descrizione che nomina l'argomento («Cose separate da
        # virgola o «e»…» per `cose`)
        for frase in re.split(r"(?<=[.;])\s+", descrizione_tool or ""):
            if re.search(r"(?<![\w])" + re.escape(nome) + r"(?![\w])", frase, re.I):
                frase = re.sub(r"\s+", " ", frase).strip()
                return (frase[:DESCRIZIONE_MAX].rsplit(" ", 1)[0] + "…"
                        if len(frase) > DESCRIZIONE_MAX else frase)
        return ""
    testo = m.group(1)
    # Fino al prossimo «altro_argomento:» o alla fine della frase
    fine = re.search(r"\.\s+[a-z_]{2,30}\s*:|\.\s+[A-ZÀ-Ü]", testo)
    testo = testo[:fine.start() + 1] if fine else testo
    testo = re.sub(r"\s+", " ", testo).strip()
    if len(testo) > DESCRIZIONE_MAX:
        testo = testo[:DESCRIZIONE_MAX].rsplit(" ", 1)[0] + "…"
    return testo


def _scheda(nome: str, prop: dict, descrizione_tool: str, obbligatorio: bool) -> dict:
    out = {"tipo": _TIPI.get((prop or {}).get("type"), (prop or {}).get("type") or "testo")}
    if obbligatorio:
        out["obbligatorio"] = True
    if (prop or {}).get("enum"):
        out["valori_ammessi"] = list(prop["enum"])
    d = descrizione_argomento(nome, prop, descrizione_tool)
    if d:
        out["cosa"] = d
    return out


def _segnaposto(nome: str, prop: dict):
    if (prop or {}).get("enum"):
        return "<" + "|".join(str(a) for a in prop["enum"]) + ">"
    t = (prop or {}).get("type")
    if t == "integer":
        return 1
    if t == "number":
        return 1.0
    if t == "boolean":
        return True
    if t == "array":
        return [f"<{nome}>"]
    return f"<{nome}>"


def _forma(valore, prop: dict):
    """(valore convertito, convertito?, valido?) secondo il tipo e i valori ammessi dello
    schema. Solo conversioni di forma (principio 10): maiuscole e spazi, un inizio che
    individua un solo valore ammesso («notiz» → «notizie»), numeri e vero/falso scritti come
    testo. Testi, elenchi e oggetti restano come sono (i tool li completano da sé)."""
    if not isinstance(prop, dict):
        return valore, False, True
    tipo, ammessi = prop.get("type"), prop.get("enum")
    if ammessi and valore is not None:
        if valore in ammessi:
            return valore, False, True
        s = _piano(valore)
        uguali = [a for a in ammessi if _piano(a) == s]
        if not uguali and len(s) >= 3:
            uguali = [a for a in ammessi if _piano(a).startswith(s)
                      or (len(_piano(a)) >= 3 and s.startswith(_piano(a)))]
        if len(uguali) == 1:
            return uguali[0], True, True
        # Fuori dai valori ammessi: decide il tool (molti hanno sinonimi e risposte loro,
        # «stop» → ferma, cambia «nessuno» → un timer nuovo)
        return valore, False, True
    if valore is None:
        return valore, False, True
    if tipo == "integer" and not isinstance(valore, bool):
        if isinstance(valore, int):
            return valore, False, True
        try:
            f = float(str(valore).strip().replace(",", "."))
        except ValueError:
            return valore, False, True       # non è un numero: decide il tool
        return (int(f), True, True) if f == int(f) else (valore, False, True)
    if tipo == "number" and not isinstance(valore, bool):
        if isinstance(valore, (int, float)):
            return valore, False, True
        try:
            return float(str(valore).strip().replace(",", ".")), True, True
        except ValueError:
            return valore, False, True
    if tipo == "boolean" and not isinstance(valore, bool):
        s = str(valore).strip().lower()
        if s in _VERO:
            return True, True, True
        if s in _FALSO:
            return False, True, True
        return valore, False, True
    return valore, False, True


def mancanti(params: dict, argomenti, func=None, contratto: bool = False) -> list[str]:
    """Gli argomenti obbligatori che impediscono la chiamata: tutti quelli dello schema se la
    chiamata non ha nessun argomento (06/10, `conversazione_cerca({})`); altrimenti quelli
    assenti o vuoti che la funzione non sa completare da sola (niente valore predefinito: una
    proposta in sospeso o un esercizio in corso li completano, e lì la funzione ne ha uno).
    Una funzione con soli **kw non dice niente: vale lo schema solo se è il contratto del tool
    (`contratto`: le estensioni, dove lo schema è il manifesto)."""
    required = list((params or {}).get("required") or [])
    args = argomenti if isinstance(argomenti, dict) else {}
    if not any(not _vuoto(v) for v in args.values()):
        return required
    f = firma(func) if func is not None else None
    if f is None:
        return [r for r in required if _vuoto(args.get(r))] if func is None else []
    nominati, senza_default, varkw = f
    return [r for r in required if _vuoto(args.get(r))
            and (r in senza_default or (r not in nominati and varkw and contratto))]


def controlla(nome: str, params: dict, argomenti, func=None, descrizione: str = "",
              contratto: bool = False, frase: str = ""):
    """Gli argomenti di una chiamata contro lo schema (e la firma della funzione, se c'è).
    Restituisce (argomenti in forma, conversioni fatte, errore o None). L'errore è già il
    risultato da dare al modello (`errore_argomenti`)."""
    params = params if isinstance(params, dict) else {}
    props = params.get("properties") or {}
    args = dict(argomenti) if isinstance(argomenti, dict) else {}
    f = firma(func) if func is not None else None
    # Argomenti che la funzione non conosce: con una firma senza **kw sarebbero un TypeError
    sconosciuti = []
    if f is not None and not f[2]:
        sconosciuti = [k for k in args if k not in f[0]]
    elif f is None and func is None and props:
        sconosciuti = [k for k in args if k not in props]
    manca = mancanti(params, args, func, contratto)
    convertiti, sbagliati = [], []
    for k, v in list(args.items()):
        if k in sconosciuti or _vuoto(v):
            continue
        nuovo, conv, ok = _forma(v, props.get(k))
        if not ok:
            sbagliati.append(k)
        elif conv:
            args[k] = nuovo
            convertiti.append(k)
    if not (sconosciuti or manca or sbagliati):
        return args, convertiti, None
    return args, convertiti, errore_argomenti(nome, params, args, descrizione, manca=manca,
                                              sbagliati=sbagliati, sconosciuti=sconosciuti,
                                              frase=frase)


def errore_argomenti(nome: str, params: dict, args: dict, descrizione: str = "",
                     manca=(), sbagliati=(), sconosciuti=(), frase: str = "") -> dict:
    """L'errore strutturato di una chiamata con argomenti mancanti, sbagliati o sconosciuti:
    che cosa non va, lo schema degli argomenti coinvolti, un esempio e che cosa fare."""
    props = (params or {}).get("properties") or {}
    required = set((params or {}).get("required") or [])
    parti = []
    if manca:
        parti.append(("manca l'argomento obbligatorio «" if len(manca) == 1
                      else "mancano gli argomenti obbligatori «") + "», «".join(manca) + "»")
    for k in sbagliati:
        p = props.get(k) or {}
        if p.get("enum"):
            parti.append(f"«{k}» vale «{args.get(k)}», che non è tra i valori ammessi")
        else:
            parti.append(f"«{k}» vale «{args.get(k)}», ma deve essere "
                         f"{_TIPI.get(p.get('type'), p.get('type') or 'testo')}")
    if sconosciuti:
        parti.append(("l'argomento «" if len(sconosciuti) == 1 else "gli argomenti «")
                     + "», «".join(sconosciuti) + "» " + ("non esiste" if len(sconosciuti) == 1
                                                         else "non esistono")
                     + (": gli argomenti di " + nome + " sono " + ", ".join(props)
                        if props else ""))
    coinvolti = [k for k in list(manca) + list(sbagliati) if k in props or k in manca]
    out = {"ok": False, "fatto": NIENTE,
           "errore": f"{nome} non è partito: " + "; ".join(parti) + ".",
           "correggibile": True}
    if coinvolti:
        out["campo"] = coinvolti[0]
        out["argomenti"] = {k: _scheda(k, props.get(k) or {}, descrizione, k in required)
                            for k in coinvolti}
    # L'esempio: la chiamata del modello, senza gli argomenti sconosciuti, con i mancanti e
    # gli sbagliati al loro posto
    esempio = {k: v for k, v in args.items() if k not in sconosciuti and k not in sbagliati
               and not _vuoto(v)}
    for k in list(sbagliati) + list(manca):
        esempio[k] = _segnaposto(k, props.get(k) or {})
    out["esempio"] = {"tool": nome, "argomenti": esempio}
    da_dedurre = ", ".join(list(manca) + list(sbagliati)) or ", ".join(props)
    frase = re.sub(r"\s+", " ", str(frase or "")).strip()[:200]
    detto = f" («{frase}»)" if frase else ""
    out["cosa_fare"] = (f"Richiama subito {nome} con gli argomenti giusti, come nell'esempio, "
                        f"ricavando {da_dedurre} da quello che ha detto la persona{detto} e "
                        f"dalla conversazione: va bene anche una forma generale, con le sue "
                        f"stesse parole. Chiedi alla persona solo se lì non c'è niente che "
                        f"serva. Non dire che riprovi: richiamalo.")
    return out


def errore_interno(nome: str, e: BaseException) -> dict:
    """L'eccezione di un tool, per il modello: mai la traccia. Un errore di programmazione
    (TypeError, KeyError…) è solo «si è fermato»; un ValueError o un guasto (rete, file)
    tiene la sua prima riga, breve. Un ValueError riguarda di solito un valore dato: si può
    correggere."""
    if isinstance(e, _INTERNE):
        frase, correggibile = f"{nome} si è fermato per un errore interno", False
    else:
        msg = str(e).strip().splitlines()[0][:200] if str(e).strip() else ""
        if "Traceback" in msg or 'File "' in msg:
            msg = ""
        frase = f"{nome} non è riuscito" + (f": {msg}" if msg else "")
        correggibile = isinstance(e, ValueError)
    return {"ok": False, "fatto": NIENTE, "errore": frase + ".", "correggibile": correggibile,
            "cosa_fare": ("Se l'errore riguarda un valore che hai dato, richiama "
                          f"{nome} con il valore corretto; altrimenti" if correggibile
                          else "Non richiamarlo con gli stessi argomenti:")
                         + " di' in breve alla persona che adesso non ci sei riuscita, "
                           "senza inventare il risultato."}


def uniforma(risultato):
    """Un risultato con «errore» ma senza «ok» (forma vecchia di alcuni tool) diventa
    {ok: false, errore…}: il modello e Brain leggono un solo formato."""
    if isinstance(risultato, dict) and "errore" in risultato and "ok" not in risultato:
        return {"ok": False, **risultato}
    return risultato


def controlla_strumento(nome: str, strumenti, argomenti):
    """Gli argomenti di uno strumento dell'agente (agenti/ciclo.py) contro il suo schema:
    (argomenti in forma, errore o None). Più indulgente dei tool della voce: manca solo un
    obbligatorio **assente** (un file vuoto si scrive con contenuto «»), e gli argomenti in più
    si lasciano (gli strumenti leggono solo i loro). Stessa forma dell'errore, con `cosa_fare`
    per l'agente."""
    schema = next((t.get("function") or {} for t in strumenti or ()
                   if (t.get("function") or {}).get("name") == nome), None)
    if schema is None:
        return argomenti, None
    params = schema.get("parameters") or {}
    props = params.get("properties") or {}
    args = dict(argomenti) if isinstance(argomenti, dict) else {}
    manca = [r for r in params.get("required") or () if args.get(r) is None]
    convertiti, sbagliati = [], []
    for k, v in list(args.items()):
        if v is None or k not in props:
            continue
        nuovo, conv, ok = _forma(v, props.get(k))
        if not ok:
            sbagliati.append(k)
        elif conv:
            args[k] = nuovo
    if not (manca or sbagliati):
        return args, None
    err = errore_argomenti(nome, params, args, schema.get("description") or "", manca=manca,
                           sbagliati=sbagliati)
    err.pop("fatto", None)
    err["cosa_fare"] = (f"Richiama {nome} con gli argomenti giusti, come nell'esempio; non "
                        f"ripetere la stessa chiamata.")
    return args, err


def errore_strumento(nome: str, e: BaseException) -> dict:
    """L'eccezione di uno strumento dell'agente: all'agente, che scrive codice, servono tipo e
    messaggio (una riga, mai la traccia), con che cosa fare."""
    msg = str(e).strip().splitlines()[0][:300] if str(e).strip() else ""
    return {"ok": False, "errore": f"{nome} non è riuscito: {type(e).__name__}"
                                   + (f": {msg}" if msg else ""),
            "cosa_fare": "leggi l'errore e cambia gli argomenti o il codice; non ripetere la "
                         "stessa chiamata"}


def come_json(risultato) -> str:
    return json.dumps(risultato, ensure_ascii=False, default=str)
