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
resta quello di `DISEGNA.*`): nel passo 2a le Liste, nel 2b l'Agenda (#257), nel 2c (#258) Lavori e
programmi, Cassetto e Giochi; Documenti e Ufficio arrivano con i passi 2d–2e. Le pagine leggono
soltanto: le azioni sono quelle che le schede hanno già (i tasti del cassetto, i giochi), con le
loro API e i loro controlli.
"""

import datetime

TESSERE = (("liste", "Liste"), ("agenda", "Agenda"), ("lavori", "Lavori e programmi"),
           ("cassetto", "Cassetto"), ("documenti", "Documenti"), ("giochi", "Giochi"),
           ("studio", "Studio"), ("ufficio", "Ufficio"))
# Le pagine già fatte (le altre tessere dicono «presto»): passo 2a le Liste, 2b l'Agenda (#257),
# 2c Lavori e programmi, Cassetto e Giochi (#258)
PAGINE = ("liste", "agenda", "lavori", "cassetto", "giochi")
# Nella pagina Lavori: i lavori finiti più recenti (memoria e, dopo un riavvio, la cartella dei
# risultati) e i programmi; le schede del codice portano i file interi, quindi pochi
LAVORI_FINITI_PAGINA = 6
PROGRAMMI_PAGINA = 4
_ATTIVI = ("in_coda", "in_corso", "in_attesa")


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


def _servizio_lavori(hub):
    """I lavori dell'agente: dai servizi, o quelli dati agli schermi da main.py."""
    return _fonte(hub, "lavori") or getattr(hub, "lavori", None)


def _servizio_cassetto(hub):
    return getattr(hub, "cassetto", None) or _fonte(hub, "cassetto")


def _giorni(cas) -> int:
    try:
        return max(1, int(round(float(getattr(cas, "giorni", 7) or 7))))
    except (TypeError, ValueError):
        return 7


def _sviluppi(svc, prof) -> list:
    """Gli sviluppi della persona da mostrare: quello aperto e i sospesi (come a voce:
    `Sviluppi.corrente` e `sospesi`, solo i suoi)."""
    svs = getattr(svc, "sviluppi", None)
    if svs is None:
        return []
    try:
        c = svs.corrente(prof.id)
        return ([c] if c is not None else []) + [x for x in svs.sospesi(prof.id) if x is not c]
    except Exception:  # noqa: BLE001 — uno sviluppo illeggibile non ferma la tessera
        return []


def _registro_persone(hub, cas=None):
    reg = getattr(cas, "registry", None) if cas is not None else None
    if reg is None:
        ctx = getattr(hub, "tool_ctx", None)
        reg = getattr(ctx, "speakers", None) if ctx is not None else None
    return reg


def _figli(hub, cas, prof) -> list:
    """I minori di casa di cui `prof` è tutore e i cui file può vedere (come a voce:
    `minori.e_tutore` e `conversazioni_visibili_ai_tutori`, tools/allegati._proprietario)."""
    from .. import minori
    reg = _registro_persone(hub, cas)
    utenti = list((getattr(reg, "users", None) or {}).values()) if reg is not None else []
    out = []
    for u in utenti:
        if getattr(u, "id", None) == prof.id:
            continue
        try:
            if (minori.e_minore(u) and minori.e_tutore(prof, u)
                    and minori.conversazioni_visibili_ai_tutori(u)):
                out.append(u)
        except Exception:  # noqa: BLE001 — un profilo strano non apre niente
            continue
    return sorted(out, key=lambda u: str(getattr(u, "name", "")))


def _giochi_di_casa(hub, prof) -> list[tuple[str, dict]] | None:
    """I giochi di casa che questa persona può aprire a voce, [(nome, manifesto)] in ordine di
    titolo; None senza le estensioni. Come a voce: un gioco del formato di oggi (con la macchina
    a stati), il livello del manifesto (un gioco «solo chi amministra» solo a chi amministra) e,
    per un minore, solo quelli che un tutore ha abilitato (`minori.estensione_consentita`)."""
    est = _fonte(hub, "estensioni")
    arch = getattr(est, "archivio", None) if est is not None else None
    if arch is None:
        return None
    from .. import minori
    from ..estensioni import scheda as scheda_est
    from ..testi import RANK
    livello = "amministra" if getattr(prof, "admin", False) else "familiare"
    minore = minori.e_minore(prof)
    out = []
    try:
        attive = list(arch.attive())
    except Exception:  # noqa: BLE001 — un indice illeggibile non ferma la pagina
        attive = []
    for v in attive:
        try:
            m = arch.manifesto(v["nome"])
            if not scheda_est.ha_macchina(m):
                continue
            if RANK.get(m.get("livello") or "familiare", 1) > RANK.get(livello, 1):
                continue
            if minore and not minori.estensione_consentita(prof, v["nome"]):
                continue
        except Exception:  # noqa: BLE001 — un manifesto rotto si salta
            continue
        out.append((v["nome"], m))
    return sorted(out, key=lambda x: str(x[1].get("titolo") or x[0]).casefold())


def _partite_di(hub, prof) -> list:
    """Le partite aperte in cui la persona ha un posto (in memoria, schermi/giochi.py)."""
    g = getattr(hub, "giochi", None)
    if g is None:
        return []
    try:
        partite = list(getattr(g, "partite", {}).values())
    except Exception:  # noqa: BLE001
        return []
    return [p for p in partite
            if any(getattr(x, "persona", None) == prof.id for x in list(getattr(p, "posti", {}).values()))]


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
    lavori = _servizio_lavori(hub)
    if lavori is None:
        return None
    mine = [lv for lv in list(getattr(lavori, "lavori", []) or []) if getattr(lv, "persona", None) == prof.id]
    corso = sum(1 for lv in mine if lv.stato in ("in_coda", "in_corso"))
    attesa = sum(1 for lv in mine if lv.stato == "in_attesa")
    fatti = sum(1 for lv in mine if lv.stato == "fatto")
    svil = _sviluppi(lavori, prof)          # gli sviluppi aperti e sospesi (28/10, #258)
    pezzi = [p for p in (f"{corso} in corso" if corso else "", f"{attesa} aspetta te" if attesa else "",
                         _piu(fatti, "finito", "finiti") if fatti else "",
                         _piu(len(svil), "sviluppo", "sviluppi") if svil else "") if p]
    ultimo = max((getattr(lv, "fine", None) or getattr(lv, "inizio", None) or getattr(lv, "creato", None) or 0
                  for lv in mine), default=None) or None
    return {"conto": len(mine) + len(svil), "stato": " · ".join(pezzi) or "nessun lavoro", "ultimo": ultimo}


def _cassetto(hub, prof):
    cas = _servizio_cassetto(hub)
    if cas is None:
        return None
    righe = cas.elenco(prof.id)
    stato = _piu(len(righe), "file", "file") + f" · tengo {_giorni(cas)} giorni"
    ultimo = max((r.get("arrivato") or 0 for r in righe), default=None) or None
    # I file dei ragazzi di cui è tutore (come a voce): nello stato, non nel conto
    for figlio in _figli(hub, cas, prof):
        altri = cas.elenco(figlio.id)
        if altri:
            stato += f" · {len(altri)} di {figlio.name}"
            ultimo = max([ultimo or 0] + [r.get("arrivato") or 0 for r in altri]) or None
    return {"conto": len(righe), "stato": stato, "ultimo": ultimo}


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
    giochi = _giochi_di_casa(hub, prof)
    if giochi is None:
        return None
    aperte = len(_partite_di(hub, prof))
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


def pagina(hub, prof, raccolta: str, schermo: dict | None = None, log=print) -> dict:
    """Le schede di una raccolta: {schede, nota?} o {errore, _stato}. Le Liste (2a), l'Agenda
    (2b), Lavori e programmi, Cassetto e Giochi (2c). `schermo`: quello che chiede (la pagina
    Giochi dice quale partita è su questo schermo). Le schede possono avere le chiavi private
    di «Scarica» (`_scarica`, `_registro`): il server le registra per lo schermo e le toglie."""
    if raccolta not in visibili(prof):
        return {"errore": "raccolta sconosciuta", "_stato": 404}
    if raccolta not in PAGINE:
        return {"schede": [], "nota": "Questa pagina arriva presto: intanto chiedilo a Calliope."}
    altre = {"agenda": lambda: _pagina_agenda(hub, prof), "lavori": lambda: _pagina_lavori(hub, prof),
             "cassetto": lambda: _pagina_cassetto(hub, prof), "giochi": lambda: _pagina_giochi(hub, prof, schermo)}
    if raccolta in altre:
        try:
            return altre[raccolta]()
        except Exception as e:  # noqa: BLE001 — un servizio guasto: la pagina lo dice, il server resta
            log(f"   [SCHERMI] pagina «{raccolta}» non letta: {type(e).__name__}")
            return {"errore": "Non riesco a leggere questa pagina: riprova tra poco.", "_stato": 503}
    from . import schede
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


# ─────────────────────────── 2c: Lavori e programmi, Cassetto, Giochi (#258) ───────────────────────────

def _cronologia(hub, persona: str, tipi: tuple) -> dict:
    """Le schede di `tipi` nella cronologia della persona, salvate in questo avvio (dopo un
    riavvio gli id dei lavori ricominciano da L1: una chiave vecchia sarebbe un altro lavoro),
    riviste contro lo stato vero come per uno schermo che si collega (cronologia.rivedi); per
    chiave."""
    cron = getattr(hub, "cronologia", None)
    if cron is None:
        return {}
    from .cronologia import rivedi
    out = {}
    try:
        voci = list(cron.ultime(persona))
    except Exception:  # noqa: BLE001 — la cronologia non ferma la pagina
        return {}
    for v in voci:
        c = v.get("scheda") or {}
        if c.get("tipo") not in tipi or v.get("avvio") != getattr(cron, "avvio", None):
            continue
        try:
            r = rivedi(hub, v, persona)
        except Exception:  # noqa: BLE001 — una scheda guasta si salta
            r = None
        if r and r.get("chiave"):
            out[str(r["chiave"])] = r
    return out


def _lavoro_vivo(lv) -> dict:
    """Un lavoro in coda, in corso o fermo a una domanda che non ha la scheda in diretta nella
    cronologia (seguito senza schermi): la scheda `lavoro` con lo stato e il passo."""
    from . import schede
    if lv.stato == "in_attesa":
        riassunto = "Aspetta una tua risposta: rispondi a voce."
    elif lv.stato == "in_corso":
        riassunto = f"Adesso l'agente {lv.passo}." if getattr(lv, "passo", "") else ""
    else:
        riassunto = "In coda: comincia appena può."
    return schede.lavoro(lv.titolo, lv.tipo, lv.stato, riassunto, (), None, "",
                         (lv.domanda or "") if lv.stato == "in_attesa" else "", ident=lv.id)


# Le schede finali dei lavori finiti in memoria, già costruite (revisione della PR #267): la pagina
# si rilegge ogni 60 s, e `Lavori.scheda` rilegge dal disco fino a 8 file interi per lavoro. La
# chiave cambia se cambia il lavoro (stato, fine) o la sua cartella (un file nuovo, «fammene un PDF»)
_FINITI: dict = {}
_FINITI_MAX = 64


def _impronta_finito(lv) -> tuple:
    import os
    c = (getattr(lv, "risultato", None) or {}).get("cartella") or ""
    try:
        m = os.stat(c).st_mtime if c else 0.0
    except OSError:
        m = -1.0
    return (id(lv), str(lv.id), str(lv.stato), getattr(lv, "fine", None), str(c), m)


def _estensione_da_approvare(hub, r: dict) -> bool:
    """Il lavoro ha consegnato una versione di un'estensione ancora da approvare (la candidata
    dell'archivio). Senza le estensioni, nel dubbio no: la scheda di revisione è per decidere a
    voce, e si chiede di nuovo a Calliope."""
    e = r.get("estensione") or {}
    est = _fonte(hub, "estensioni")
    arch = getattr(est, "archivio", None) if est is not None else None
    if arch is None or not e.get("nome"):
        return False
    try:
        voce = arch.voce(e["nome"]) or {}
        ver = arch.versione(e["nome"], e.get("versione")) or {}
    except Exception:  # noqa: BLE001
        return False
    return voce.get("candidata") == e.get("versione") and ver.get("stato") == "da_approvare"


def _lavoro_finito(hub, svc, lv) -> dict | None:
    """La scheda finale di un lavoro finito: quella che Calliope manda alla fine
    (`Lavori.scheda`: il codice, il documento, il testo), tenuta in `_FINITI`; dopo un riavvio
    (dalla cartella dei risultati) quella del lavoro col riassunto salvato, con la chiave della
    cartella (gli id ricominciano). Un'estensione non più da approvare (approvata, rifiutata,
    sostituita) ha la scheda breve, non quella di revisione «Estensione da approvare»."""
    from pathlib import Path
    from . import schede
    from ..agenti import risultato as ar
    r = getattr(lv, "risultato", None) or {}
    revisione = bool(r.get("estensione"))
    if not getattr(lv, "dal_disco", False) and (not revisione or _estensione_da_approvare(hub, r)):
        k = _impronta_finito(lv)
        c = _FINITI.get(k)
        if c is None:
            try:
                c = svc.scheda(lv)
            except Exception:  # noqa: BLE001 — un file sparito: la scheda breve
                c = None
            if c:
                if len(_FINITI) >= _FINITI_MAX:
                    _FINITI.pop(next(iter(_FINITI)))
                _FINITI[k] = c
        if c:
            return dict(c)
    cartella = Path(r.get("cartella") or "").name
    riassunto = ar.riassunto_salvato(lv)
    if revisione and not riassunto:
        riassunto = "Estensione consegnata: la sua revisione è già decisa."
    return schede.lavoro(lv.titolo, lv.tipo, lv.stato, riassunto, (), None, cartella,
                         "", ident=ar.chiave(lv))


def _pagina_lavori(hub, prof) -> dict:
    """La pagina Lavori e programmi (28/10, passo 2c, #258): gli sviluppi aperti e sospesi della
    persona (la scheda `sviluppo`), i suoi lavori in coda, in corso o fermi a una domanda (la
    scheda in diretta dalla cronologia, con il passo e il flusso; altrimenti quella breve), i
    suoi programmi (`esecuzione`) e i lavori finiti più recenti, anche di prima di un riavvio.
    Solo della persona, come le schede che arrivano ai suoi schermi; la nota è la frase di
    `lavoro_stato` sui soli lavori della persona (`Lavori.stato(persona, tutti=False)`), anche per
    chi amministra: dallo schermo lo scritto vale al più «familiare», e il cruscotto non dà i titoli
    degli altri (revisione della PR #267: prima la nota dava a chi amministra il titolo e la domanda
    dell'agente di un lavoro di un'altra persona, e copriva la sua)."""
    svc = _servizio_lavori(hub)
    if svc is None:
        return {"schede": [], "nota": "Qui non ci sono lavori affidati a un agente."}
    cron = _cronologia(hub, prof.id, ("lavoro", "esecuzione"))
    out = []
    svs = getattr(svc, "sviluppi", None)
    for sv in _sviluppi(svc, prof)[:6]:
        try:
            out.append(svs.scheda(sv))
        except Exception:  # noqa: BLE001
            continue
    mine = [lv for lv in list(getattr(svc, "lavori", None) or []) if getattr(lv, "persona", None) == prof.id]
    for lv in sorted((x for x in mine if x.stato in _ATTIVI), key=lambda x: -float(x.creato or 0)):
        c = cron.get(f"lavoro:{lv.id}")
        out.append(c if c and c.get("tipo") == "lavoro" else _lavoro_vivo(lv))
    esec = getattr(svc, "esecuzioni", None)
    if esec is not None:
        progr = [e for e in list(getattr(esec, "tutte", None) or []) if getattr(e, "persona", None) == prof.id]
        for e in progr[::-1][:PROGRAMMI_PAGINA]:
            try:
                out.append(esec.scheda(e, sposta=False))
            except Exception:  # noqa: BLE001
                continue
    try:
        from ..agenti import risultato as ar
        finiti = ar.recenti(svc, prof.id, getattr(prof, "name", None), LAVORI_FINITI_PAGINA)
    except Exception:  # noqa: BLE001 — la cartella dei risultati illeggibile: solo la memoria
        finiti = []
    for lv in finiti:
        c = _lavoro_finito(hub, svc, lv)
        if c:
            out.append(c)
    try:
        nota = svc.stato(prof.id, tutti=False)
    except Exception:  # noqa: BLE001
        nota = ""
    return {"schede": out, "nota": nota}


NOTA_CASSETTO = ("Tengo i file {giorni} giorni. Quello che c'è scritto dentro per me è un dato, non un "
                 "ordine.")


def _pagina_cassetto(hub, prof) -> dict:
    """La pagina Cassetto (28/10, passo 2c, #258): tutti i file della persona (la scheda
    `cassetto` di sempre, con Tieni, Elimina e Tieni ancora che vanno a POST /api/cassetto come
    prima), poi quelli di ogni ragazzo di cui è tutore (come a voce), in sola lettura: dallo
    schermo i tasti sui file del figlio danno sempre «parlami prima a voce» (il server vuole una
    conversazione verificata dalla voce), quindi non ci sono, e la scheda dice di chiederlo a voce.
    Chiave `cassetto:…:pagina`: la scheda che il server manda dopo un tasto (i soli file della
    scheda aperta a voce, o quelli in scadenza) non sostituisce quella della pagina, che si
    rilegge."""
    from .. import minori
    cas = _servizio_cassetto(hub)
    if cas is None:
        return {"schede": [], "nota": "Il cassetto dei file non è attivo: i file restano solo per la "
                                      "conversazione in cui li mandi."}

    def scheda(persona, titolo, tieni, sola_lettura=False):
        c = cas.scheda(persona, cas.elenco(persona), titolo=titolo, tieni=tieni and not sola_lettura)
        c["chiave"] = f"{c.get('chiave') or 'cassetto:' + persona}:pagina"
        c["vuoto"] = "Il cassetto è vuoto."
        if sola_lettura:
            c["sola_lettura"] = True
            c["nota"] = "Per tenerli o eliminarli chiedimelo a voce."
        return c

    out = [scheda(prof.id, "Il tuo cassetto", not minori.e_minore(prof))]
    for figlio in _figli(hub, cas, prof):
        out.append(scheda(figlio.id, f"I file di {figlio.name}", True, sola_lettura=True))
    return {"schede": out, "nota": NOTA_CASSETTO.format(giorni=_giorni(cas))}


def _pagina_giochi(hub, prof, schermo: dict | None) -> dict:
    """La pagina Giochi (28/10, passo 2c, #258): le partite aperte della persona (dove, a chi
    tocca, i punti dell'ultima istantanea validata) e i giochi di casa che può aprire a voce,
    in schede `giochi` di sola lettura. Il gioco vero resta la sua scheda `gioco`, che la
    pagina mostra sotto (una copia sola del riquadro: due avrebbero due stati); un gioco si apre
    e ci si unisce a voce, come prima."""
    from . import schede
    from .. import minori
    if not getattr(getattr(hub, "cfg", None), "giochi_enabled", True):
        return {"schede": [], "nota": "I giochi sugli schermi sono spenti."}
    giochi = _giochi_di_casa(hub, prof)
    qui = (schermo or {}).get("id")
    partite = [_partita(hub, p, qui, prof.id) for p in
               sorted(_partite_di(hub, prof), key=lambda x: -float(getattr(x, "ultimo", 0) or 0))]
    out = []
    if partite:
        out.append(schede.giochi(f"giochi:partite:{prof.id}", "Partite aperte", partite=partite))
    if giochi is None:
        return {"schede": out, "nota": "Le estensioni non sono attive: qui non ci sono giochi di casa."}
    voci = []
    for nome, m in giochi:
        titolo = str(m.get("titolo") or nome)
        g = (m.get("scheda") or {}).get("giocatori") or {}
        try:
            lo, hi = int(g.get("min", 1) or 1), int(g.get("max", 1) or 1)
        except (TypeError, ValueError):
            lo = hi = 1
        voci.append({"titolo": titolo, "descrizione": str(m.get("descrizione") or ""),
                     "giocatori": ("1 giocatore" if hi == lo == 1 else f"{lo} giocatori" if hi == lo
                                   else f"da {lo} a {hi} giocatori"),
                     "dire": f"«Calliope, giochiamo a {titolo}»"})
    nota = "Gli altri giochi di casa li sblocca chi si occupa di te." if minori.e_minore(prof) else ""
    out.append(schede.giochi(f"giochi:casa:{prof.id}", "Giochi di casa", giochi=voci, nota=nota,
                             vuoto="In casa non ci sono ancora giochi: chiedi a Calliope di inventarne uno."))
    return {"schede": out}


def _partita(hub, p, qui, persona) -> dict:
    """Una partita aperta per la scheda `giochi`: titolo, schermi, a chi tocca e i punti (i nomi
    sono quelli già controllati dall'istantanea: macchina.valida_istantanea). L'istantanea è quella
    del posto della persona (su questo schermo, se c'è), o del posto che tiene la partita con un
    motore solo: in una partita condivisa con la tela ogni riquadro ha il suo motore, e quella di
    un altro schermo direbbe altro (revisione della PR #267)."""
    posti = list(getattr(p, "posti", {}).items())
    dove = []
    for sid, _ in posti:
        s = (hub.schermo(sid) if hasattr(hub, "schermo") else None) or {}
        dove.append(str(s.get("nome") or "uno schermo"))
    ist = None
    suoi = [(sid, x) for sid, x in posti if getattr(x, "persona", None) == persona]
    suo = next((x for sid, x in suoi if sid == qui), None) or (suoi[0][1] if suoi else None)
    try:
        if suo is not None:
            ist = getattr(p.tiene(suo), "istantanea", None) or getattr(suo, "istantanea", None)
    except Exception:  # noqa: BLE001
        ist = None
    gs = list((ist or {}).get("giocatori") or [])
    tocca = (ist or {}).get("tocca")
    return {"titolo": str(getattr(p, "titolo", "") or "Gioco"), "dove": dove,
            "qui": qui is not None and any(sid == qui for sid, _ in posti),
            "prova": bool(getattr(p, "prova", False)),
            "tocca": gs[tocca]["nome"] if isinstance(tocca, int) and 0 <= tocca < len(gs) else "",
            "punti": [{"nome": g.get("nome"), "punti": g.get("punti")} for g in gs],
            "esito": str((ist or {}).get("esito") or "")}


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
