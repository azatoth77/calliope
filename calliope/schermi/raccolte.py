"""
Le raccolte di «Le mie cose» sugli schermi personali (28/10, passo 2a di
docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md § 4.3, issue #256).

Otto tessere, ognuna con il conto, lo stato in una riga e l'ora dell'ultimo cambiamento (la
pagina accende il pallino se è più recente dell'ultima visita). I conti si leggono dai servizi,
non dalla cronologia delle schede, che tiene solo le schede personali (la lista è di casa, il
timer è pubblico: non ci entrano mai). Ogni lettura è protetta: un servizio che manca o che non
risponde dà una tessera senza conto, mai un errore alla pagina.

Chi vede cosa (le regole sono le stesse della voce):
- le liste sono di casa: tutte le persone di casa;
- l'agenda: i timer di casa e i promemoria e gli appuntamenti della persona;
- lavori, cassetto, documenti fatti da Calliope, studio: della persona;
- i giochi: quelli di casa;
- l'ufficio (fatture, preventivi, DDT, rubrica): **solo chi amministra** (decisione del 28/10).

`pagina(…)` dà le schede di una raccolta, costruite dai `schede.*` che esistono già (il disegno
resta quello di `DISEGNA.*`): nel passo 2a le Liste, nel 2b l'Agenda (#257); le altre pagine
arrivano con i passi 2c–2e.
"""

import datetime

TESSERE = (("liste", "Liste"), ("agenda", "Agenda"), ("lavori", "Lavori e programmi"),
           ("cassetto", "Cassetto"), ("documenti", "Documenti"), ("giochi", "Giochi"),
           ("studio", "Studio"), ("ufficio", "Ufficio"))
# Le pagine già fatte (le altre tessere dicono «presto»): passo 2a le Liste, 2b l'Agenda (#257)
PAGINE = ("liste", "agenda")


def _fonte(hub, nome):
    """Un servizio: dai servizi della voce (main.py) o dal contesto dei tool."""
    s = getattr(hub, "servizi", None)
    v = getattr(s, nome, None) if s is not None else None
    if v is None:
        ctx = getattr(hub, "tool_ctx", None)
        v = getattr(ctx, nome, None) if ctx is not None else None
    return v


def _piu(n: int, una: str, tante: str) -> str:
    return f"{n} {una if n == 1 else tante}"


def _liste(hub, prof):
    liste = _fonte(hub, "liste")
    if liste is None:
        return None
    nomi = liste.names()
    stato = ", ".join(nomi[:3]) + ("…" if len(nomi) > 3 else "")
    return {"conto": len(nomi), "stato": (_piu(len(nomi), "lista", "liste") + (" · " + stato if stato else "")),
            "ultimo": liste.ultimo_cambio() if hasattr(liste, "ultimo_cambio") else None}


def _agenda(hub, prof):
    agenda = _fonte(hub, "agenda")
    if agenda is None:
        return None
    from ..agenda import per_giorno
    voci = list(agenda.items(prof.id))
    g = per_giorno(voci)              # la stessa vista della pagina (28/10, #257)
    timer, oggi = g["timer"], g["oggi"]
    pezzi = []
    if timer:
        pezzi.append(_piu(len(timer), "timer", "timer"))
    pezzi.append(_piu(len(oggi), "cosa oggi", "cose oggi") if oggi else "niente oggi")
    return {"conto": len(timer) + len(oggi), "stato": " · ".join(pezzi),
            "ultimo": max((v.get("created") or 0 for v in voci), default=None) or None}


def _lavori(hub, prof):
    lavori = _fonte(hub, "lavori")
    if lavori is None:
        return None
    mine = [lv for lv in list(getattr(lavori, "lavori", []) or []) if getattr(lv, "persona", None) == prof.id]
    corso = sum(1 for lv in mine if lv.stato in ("in_coda", "in_corso"))
    attesa = sum(1 for lv in mine if lv.stato == "in_attesa")
    fatti = sum(1 for lv in mine if lv.stato == "fatto")
    pezzi = [p for p in (f"{corso} in corso" if corso else "", f"{attesa} aspetta te" if attesa else "",
                         _piu(fatti, "finito", "finiti") if fatti else "") if p]
    ultimo = max((getattr(lv, "fine", None) or getattr(lv, "inizio", None) or getattr(lv, "creato", None) or 0
                  for lv in mine), default=None) or None
    return {"conto": len(mine), "stato": " · ".join(pezzi) or "nessun lavoro", "ultimo": ultimo}


def _cassetto(hub, prof):
    cas = getattr(hub, "cassetto", None) or _fonte(hub, "cassetto")
    if cas is None:
        return None
    righe = cas.elenco(prof.id)
    return {"conto": len(righe), "stato": _piu(len(righe), "file", "file") + " · tengo 7 giorni",
            "ultimo": max((r.get("arrivato") or 0 for r in righe), default=None) or None}


def _documenti(hub, prof):
    doc = _fonte(hub, "documenti")
    if doc is None:
        return None
    recenti = doc.recenti(prof.id, 50)
    formati = sorted({str(r.get("formato") or "").upper() for r in recenti if r.get("formato")})
    ultimo = None
    for r in recenti:
        try:
            t = datetime.datetime.fromisoformat(str(r.get("modificato"))).timestamp()
        except (TypeError, ValueError):
            continue
        ultimo = max(ultimo or 0, t)
    return {"conto": len(recenti), "stato": _piu(len(recenti), "documento", "documenti")
            + (" · " + ", ".join(formati[:3]) if formati else ""), "ultimo": ultimo}


def _giochi(hub, prof):
    est = _fonte(hub, "estensioni")
    arch = getattr(est, "archivio", None) if est is not None else None
    if arch is None:
        return None
    try:
        from ..estensioni import scheda as scheda_est
        giochi = [v for v in arch.attive() if scheda_est.ha_macchina(arch.manifesto(v["nome"]))]
    except Exception:  # noqa: BLE001 — un indice illeggibile non ferma la pagina
        giochi = []
    aperte = 0
    g = getattr(hub, "giochi", None)
    for p in list(getattr(g, "partite", {}).values()) if g is not None else ():
        if any(getattr(x, "persona", None) == prof.id for x in getattr(p, "posti", {}).values()):
            aperte += 1
    stato = _piu(len(giochi), "gioco", "giochi") + (f" · {_piu(aperte, 'partita aperta', 'partite aperte')}" if aperte else "")
    return {"conto": len(giochi), "stato": stato, "ultimo": None}


def _studio(hub, prof):
    es = getattr(hub, "esercizi", None)
    if es is None:
        return None
    s = es.sessione(prof.id) if hasattr(es, "sessione") else None
    if s is not None and getattr(s, "aperta", False):
        return {"conto": 1, "stato": "esercizi in corso", "ultimo": None}
    return {"conto": 0, "stato": "niente in corso", "ultimo": None}


def _ufficio(hub, prof):
    uff = _fonte(hub, "ufficio")
    numeri = getattr(uff, "numeri", None) if uff is not None else None
    if numeri is None:
        return None
    anno = datetime.date.today().year
    righe = numeri.elenco(anno=anno)
    emessi = [r for r in righe if r.get("stato") == "emesso"]
    return {"conto": len(emessi), "stato": f"{len(emessi)} nel {anno} · fatture, preventivi, DDT", "ultimo": None}


LETTURE = {"liste": _liste, "agenda": _agenda, "lavori": _lavori, "cassetto": _cassetto,
           "documenti": _documenti, "giochi": _giochi, "studio": _studio, "ufficio": _ufficio}


def visibili(prof) -> list[str]:
    """Le tessere di questa persona: l'ufficio solo a chi amministra (decisione del 28/10) e mai
    ai minori (il satellite di un minore nasconde anche la raccolta, aspetto.nascoste)."""
    from .aspetto import nascoste
    via = set(nascoste(prof)["raccolte"])
    if not getattr(prof, "admin", False):
        via.add("ufficio")
    return [k for k, _ in TESSERE if k not in via]


def tessere(hub, prof, log=print) -> list[dict]:
    """Le tessere di `prof`: [{id, nome, conto, stato, ultimo, pagina}]. Un servizio che manca o
    non risponde dà la tessera senza conto (stato «non disponibile»)."""
    nomi = dict(TESSERE)
    out = []
    for k in visibili(prof):
        try:
            d = LETTURE[k](hub, prof)
        except Exception as e:  # noqa: BLE001 — una tessera non ferma le altre
            log(f"   [SCHERMI] raccolta «{k}» non letta: {type(e).__name__}")
            d = None
        d = d or {"conto": None, "stato": "non disponibile", "ultimo": None}
        out.append({"id": k, "nome": nomi[k], "conto": d["conto"], "stato": d["stato"],
                    "ultimo": d.get("ultimo"), "pagina": k in PAGINE})
    return out


def pagina(hub, prof, raccolta: str) -> dict:
    """Le schede di una raccolta: {schede} o {errore, _stato}. Le Liste (2a) e l'Agenda (2b)."""
    if raccolta not in visibili(prof):
        return {"errore": "raccolta sconosciuta", "_stato": 404}
    if raccolta not in PAGINE:
        return {"schede": [], "nota": "Questa pagina arriva presto: intanto chiedilo a Calliope."}
    from . import schede
    if raccolta == "agenda":
        return _pagina_agenda(hub, prof)
    if raccolta == "liste":
        liste = _fonte(hub, "liste")
        if liste is None:
            return {"schede": [], "nota": "Le liste non sono disponibili."}
        out = []
        for nome in liste.names():
            key, voci = liste.read(nome)
            out.append(schede.lista(key, voci))
        return {"schede": out}
    return {"schede": []}


def _pagina_agenda(hub, prof) -> dict:
    """La pagina Agenda (28/10, passo 2b, #257): una scheda `timer` per ogni timer di casa ancora
    da suonare (con chi l'ha messo; sugli schermi personali con «+1 minuto» e «Ferma»), poi i
    promemoria e gli appuntamenti della persona per oggi, domani e in settimana
    (`agenda.per_giorno`), tre schede `promemoria`."""
    from . import schede
    from ..agenda import per_giorno
    agenda = _fonte(hub, "agenda")
    if agenda is None:
        return {"schede": [], "nota": "L'agenda non è disponibile."}
    g = per_giorno(agenda.items(prof.id))
    out = [schede.timer(it) for it in g["timer"][:12]]
    for quale, _, _ in schede.GIORNI_AGENDA:
        out.append(schede.giorno(prof.id, quale, g[quale],
                                 dopo=g["dopo"] if quale == "settimana" else 0))
    return {"schede": out}
