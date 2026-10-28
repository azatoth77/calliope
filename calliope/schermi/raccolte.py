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
- lavori, cassetto, documenti fatti da Calliope, studio: della persona; dal 28/10 (passo 2d,
  decisione di Dario) chi amministra vede nelle pagine Lavori e Documenti anche quelli degli
  altri, e tutto l'archivio di casa;
- l'archivio di casa (pagina Documenti): coi permessi della voce (`Archivio.puo_vedere`), mai ai
  minori;
- i giochi: quelli di casa;
- l'ufficio (fatture, preventivi, DDT, rubrica): **solo chi amministra** (decisione del 28/10).

`pagina(…)` dà le schede di una raccolta, costruite dai `schede.*` che esistono già (il disegno
resta quello di `DISEGNA.*`): nel passo 2a le Liste, nel 2b l'Agenda (#257), nel 2c (#258) Lavori e
programmi, Cassetto e Giochi, nel 2d (#259) i Documenti con la ricerca (`cerca`), nel 2e (#260)
l'Ufficio con la sua ricerca, solo a chi amministra. Le pagine leggono
soltanto: le azioni sono quelle che le schede hanno già (i tasti del cassetto, i giochi), con le
loro API e i loro controlli.
"""

import datetime
import threading

TESSERE = (("liste", "Liste"), ("agenda", "Agenda"), ("lavori", "Lavori e programmi"),
           ("cassetto", "Cassetto"), ("documenti", "Documenti"), ("giochi", "Giochi"),
           ("studio", "Studio"), ("ufficio", "Ufficio"))
# Le pagine già fatte (le altre tessere dicono «presto»): passo 2a le Liste, 2b l'Agenda (#257),
# 2c Lavori e programmi, Cassetto e Giochi (#258), 2d i Documenti (#259), 2e l'Ufficio (#260)
PAGINE = ("liste", "agenda", "lavori", "cassetto", "giochi", "documenti", "ufficio")
# Nella pagina Documenti: i documenti fatti da Calliope per persona (le schede portano il testo
# intero per «Leggi»), e le righe dell'archivio di casa per tipo
DOCUMENTI_PAGINA = 8
ARCHIVIO_PER_TIPO = 20
# La ricerca: testo cercato al più così lungo, risultati al più tanti
CERCA_MAX = 120
CERCA_RISULTATI = 20
# Le pagine con la ricerca (le stesse di CON_RICERCA in sezioni.js)
CON_RICERCA = ("documenti", "ufficio")
# La ricerca guarda tutti i documenti fatti da Calliope della persona (di tutti per chi amministra),
# fino a questo tetto: la pagina ne mostra gli ultimi DOCUMENTI_PAGINA, gli altri si trovano così
# (revisione della PR #268: «lo trovi in Le mie cose» deve essere vero)
CERCA_TRA = 5000
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
    doc = _servizio_documenti(hub)
    if doc is None:
        return None
    ammessi = _documenti_ammessi(prof)
    recenti = doc.recenti(prof.id, 50) if ammessi else []
    formati = sorted({str(r.get("formato") or "").upper() for r in recenti if r.get("formato")})
    ultimo = None
    for r in recenti:
        t = _quando_doc(r.get("modificato"))
        if t:
            ultimo = max(ultimo or 0, t)
    if ammessi and hasattr(doc, "conta"):
        # Il conto vero (non al più 50); per chi amministra la pagina mostra anche quelli degli
        # altri: lo stato dice «tuoi» e quanti degli altri (revisione della PR #268)
        n = doc.conta(prof.id)
        stato = _piu(n, "documento", "documenti")
        if getattr(prof, "admin", False):
            altri = doc.conta(None) - n
            stato = _piu(n, "documento tuo", "documenti tuoi") + (f" · {altri} degli altri" if altri else "")
        return {"conto": n, "stato": stato + (" · " + ", ".join(formati[:3]) if formati else ""),
                "ultimo": ultimo}
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
    # Lo Studio si rifà da capo (28/10, decisione 0035): la tessera resta al suo posto e dice
    # «arriva presto» finché il passo 4.5 non la riscrive. *[storico: fino al 28/10 leggeva la
    # sessione degli esercizi, tolti con la #279]*
    return {"conto": None, "stato": "arriva presto", "ultimo": None}


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
             "documenti": lambda: _pagina_documenti(hub, prof), "ufficio": lambda: _pagina_ufficio(hub, prof),
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
# (dal 2d, seconda revisione della PR #267: con un lock, perché due letture insieme potevano
# togliere la stessa voce e la pagina dava 503; e la chiave guarda i file, non solo la cartella)
_FINITI: dict = {}
_FINITI_MAX = 64
_FINITI_LOCK = threading.Lock()


def _impronta_finito(lv) -> tuple:
    """La chiave della scheda tenuta: il lavoro, la cartella e la data e la dimensione di ogni
    file che `Lavori.scheda` legge (i primi 8 del risultato). La data della cartella da sola non
    cambia quando un file viene riscritto con lo stesso nome."""
    import os
    r = getattr(lv, "risultato", None) or {}
    c = r.get("cartella") or ""
    try:
        m = os.stat(c).st_mtime_ns if c else 0
    except OSError:
        m = -1
    nomi = tuple(str(n) for n in (r.get("file") or [])[:8])
    file = []
    for n in nomi:
        try:
            st = os.stat(os.path.join(c, n)) if c else None
            file.append((n, st.st_mtime_ns, st.st_size) if st else (n, 0, 0))
        except OSError:
            file.append((n, -1, -1))
    return (id(lv), str(lv.id), str(lv.stato), getattr(lv, "fine", None), str(c), m, tuple(file))


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
        with _FINITI_LOCK:
            c = _FINITI.get(k)
        if c is None:
            try:
                c = svc.scheda(lv)         # fuori dal lock: legge i file dal disco
            except Exception:  # noqa: BLE001 — un file sparito: la scheda breve
                c = None
            if c:
                with _FINITI_LOCK:
                    while len(_FINITI) >= _FINITI_MAX:
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
    Della persona, come le schede che arrivano ai suoi schermi; per chi amministra, in coda, anche
    quelli delle altre persone di casa con il loro nome (`_lavori_degli_altri`, decisione di Dario
    del 28/10). La nota è la frase di `lavoro_stato` sui soli lavori della persona
    (`Lavori.stato(persona, tutti=False)`), anche per chi amministra, così la sua domanda non
    viene coperta da quelle degli altri. *[storico: dalla revisione della PR #267 al 28/10 chi
    amministra non vedeva nella pagina né il titolo né la domanda dei lavori degli altri, perché
    nessuno l'aveva deciso]*"""
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
    if getattr(prof, "admin", False):
        # Chi amministra vede anche i lavori degli altri (decisione di Dario del 28/10), in coda
        try:
            out += _lavori_degli_altri(hub, svc, prof)
        except Exception:  # noqa: BLE001 — i lavori degli altri non fermano i suoi
            pass
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
        righe = cas.elenco(persona)
        c = cas.scheda(persona, righe, titolo=titolo, tieni=tieni and not sola_lettura)
        c["chiave"] = f"{c.get('chiave') or 'cassetto:' + persona}:pagina"
        c["vuoto"] = "Il cassetto è vuoto."
        if sola_lettura:
            c["sola_lettura"] = True
            # Solo con dei file (2d, seconda revisione della PR #267): la scheda mostra la nota
            # al posto di «vuoto», e un cassetto vuoto diceva «chiedimelo a voce»
            if righe:
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


# ─────────────────────────── 2d: Documenti (#259) ───────────────────────────

# Come si chiama ogni tipo dell'archivio di casa nella pagina (archivio/tipi.py)
TIPI_PAGINA = {"bolletta": "Bollette", "ricevuta": "Ricevute e fatture", "contratto": "Contratti",
               "assicurazione": "Polizze", "garanzia": "Garanzie", "referto": "Referti",
               "identita": "Documenti d'identità", "manuale": "Manuali", "altro": "Altri documenti"}


def _servizio_documenti(hub):
    """L'archivio dei documenti fatti da Calliope (`Documenti.archive`, documenti/servizio.py).
    Fino al 2d la tessera chiamava `recenti` sul servizio `Documenti`, che non l'ha: con il
    servizio vero la tessera diceva sempre «non disponibile»."""
    d = _fonte(hub, "documenti")
    if d is None:
        return None
    a = getattr(d, "archive", None)
    if a is not None and hasattr(a, "recenti"):
        return a
    return d if hasattr(d, "recenti") else None


def _quando_doc(v) -> float | None:
    """`modificato` dell'archivio dei documenti: un tempo in secondi (o una data ISO)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v) or None
    try:
        return datetime.datetime.fromisoformat(str(v)).timestamp()
    except (TypeError, ValueError):
        return None


def _documenti_ammessi(prof) -> bool:
    """I documenti fatti da Calliope come a voce (`minori.permesso` su `documento_leggi`): un
    minore col preset «documenti: no» non li ha."""
    from .. import minori
    try:
        p = minori.preset(prof)
    except Exception:  # noqa: BLE001 — nel dubbio, come un adulto senza preset
        p = None
    return p is None or p.get("documenti") != "no"


def _chi_archivio(prof):
    """Chi guarda l'archivio di casa dalla pagina. Come a voce per i familiari (`Chi`, livello
    «familiare», mai la zona grigia: lo schermo personale è suo) e mai per un minore (i tool
    dell'archivio sono di `minori._UFFICIO`). Chi amministra lo vede **tutto**, senza il filtro
    dei documenti personali degli altri (decisione di Dario del 28/10): a voce invece resta
    `puo_vedere` com'è (dallo schermo lo scritto vale al più «familiare»)."""
    from .. import minori
    from ..archivio import Chi
    if not getattr(prof, "id", None) or minori.e_minore(prof):
        return None
    return Chi("amministra" if getattr(prof, "admin", False) else "familiare", prof.id,
               getattr(prof, "name", None), False)


def _profilo_ora(hub, prof):
    """Il profilo com'è adesso nel registro (per i permessi rifatti al clic su «Scarica»); senza
    registro quello della pagina."""
    reg = _registro_persone(hub)
    if reg is None or not hasattr(reg, "by_id"):
        return prof
    try:
        return reg.by_id(prof.id)
    except Exception:  # noqa: BLE001
        return None


def _nomi_persone(hub) -> dict:
    reg = _registro_persone(hub)
    utenti = list((getattr(reg, "users", None) or {}).values()) if reg is not None else []
    return {u.id: str(getattr(u, "name", "") or "") for u in utenti if getattr(u, "id", None)}


def _scheda_documento(arch, r: dict, gruppo: str, di: str = "") -> dict | None:
    """La scheda `documento` di sempre (anteprima per «Leggi», «Scarica» nei suoi formati) di un
    documento fatto da Calliope, rifatta dal JSON dell'archivio: si scarica anche se il file è
    finito sul portatile o è rimasto sul server."""
    from . import schede
    try:
        d = arch.get(r["id"])
        if not d:
            return None
        c = schede.documento(d["contenuto"], d["formato"], str(d.get("nome_file") or ""), ident=d["id"])
    except Exception:  # noqa: BLE001 — un documento illeggibile si salta
        return None
    c["gruppo"] = gruppo
    if di:
        c["di"] = di
    return c


def _file_visibile(hub, prof, arch, doc_id: int):
    """Il file vero di un documento dell'archivio, se la persona com'è adesso può vederlo."""
    ora = _profilo_ora(hub, prof)
    chi = _chi_archivio(ora) if ora is not None else None
    if chi is None or arch.documento_visibile(chi, doc_id) is None:
        return None
    return arch.file_di(doc_id)


def _leggi_file(hub, prof, arch, doc_id: int):
    """La funzione che «Scarica» chiama al clic (scarica.converti): i permessi rifatti adesso,
    sul profilo com'è adesso, poi i byte del file vero dentro la cartella dell'archivio."""
    def leggi():
        p = _file_visibile(hub, prof, arch, doc_id)
        if p is None:
            return None
        try:
            return p.read_bytes(), p.suffix.lstrip(".").lower()
        except OSError:
            return None
    return leggi


def _estensione_file(hub, prof, arch, doc_id: int):
    """L'estensione del file che `_leggi_file` leggerà, senza leggerlo: il nome in «Scaricato: …»
    uguale a quello del file salvato (seconda revisione della PR #268, #260)."""
    def estensione():
        p = _file_visibile(hub, prof, arch, doc_id)
        return p.suffix.lstrip(".").lower() if p is not None else None
    return estensione


def _di_chi(arch, d: dict, nomi_nodi: dict) -> str:
    """Di chi è un documento dell'archivio: la persona della cartella, gli intestatari, o la
    casa."""
    a = d.get("attributi") or {}
    cart = str(a.get("cartella") or "")
    try:
        profili = {n.casefold(): n for n in arch.profili()}
    except Exception:  # noqa: BLE001
        profili = {}
    if cart and cart.casefold() in profili:
        return f"Di {profili[cart.casefold()]}"
    nomi = sorted({nomi_nodi[p] for p in d.get("persone") or () if p in nomi_nodi})
    if nomi:
        return "Di " + " e ".join(nomi[:2]) + (" e altri" if len(nomi) > 2 else "")
    return "Di casa"


def _nomi_nodi(arch, docs: list) -> dict:
    ids = sorted({p for d in docs for p in d.get("persone") or ()})
    out = {}
    for i in range(0, len(ids), 500):
        pezzo = ids[i:i + 500]
        for r in arch.grafo.leggi(f"SELECT id, nome FROM nodi WHERE id IN ({','.join('?' * len(pezzo))})",
                                  tuple(pezzo)):
            out[r["id"]] = str(r["nome"] or "")
    return out


def _schede_archivio(hub, prof, arch, docs: list, chiave: str, titolo: str = "", per_tipo: bool = True,
                     nota_fn=None) -> list:
    """Le schede `archivio`: una per tipo (`per_tipo`, chiave `<chiave>:<tipo>`) o una sola
    (`titolo`, `chiave`), con una riga per documento e «Scarica» del file originale (la
    sorgente in `_scarica_voci`, che resta sul server)."""
    from pathlib import Path
    from ..archivio import normalizza as nz
    from . import schede
    from .scarica import ORIGINALI
    gruppi: dict = {}
    for d in docs:
        k = ((d.get("attributi") or {}).get("tipo_doc") or "altro") if per_tipo else ""
        gruppi.setdefault(k, []).append(d)
    # I nomi delle persone solo per le righe mostrate (revisione della PR #268)
    nomi_nodi = _nomi_nodi(arch, [d for g in gruppi.values() for d in g[:ARCHIVIO_PER_TIPO]])
    ordine = [t for t in TIPI_PAGINA if t in gruppi] + [t for t in gruppi if t not in TIPI_PAGINA]
    out = []
    for tipo in ordine:
        tutti = gruppi[tipo]
        voci, sorgenti = [], []
        for d in tutti[:ARCHIVIO_PER_TIPO]:
            a = d.get("attributi") or {}
            nome_file = str(a.get("file") or "")
            ext = Path(nome_file).suffix.lstrip(".").lower()
            ok = ext in ORIGINALI
            ck = f"archivio:file:{d['id']}"
            try:
                data = nz.data_detta(d["data"]) if d.get("data") else ""
            except Exception:  # noqa: BLE001
                data = str(d.get("data") or "")
            try:
                importo = nz.euro(d["totale"]) if d.get("totale") is not None else ""
            except Exception:  # noqa: BLE001
                importo = ""
            nome = str(d.get("nome") or "Documento")
            voci.append({"nome": nome[:1].upper() + nome[1:], "data": data, "importo": importo,
                         "di": _di_chi(arch, d, nomi_nodi), "chiave": ck if ok else "",
                         "estensione": ext if ok else ""})
            if ok:
                sorgenti.append({"chiave": ck, "formati": ["originale"],
                                 "sorgente": {"file_fn": _leggi_file(hub, prof, arch, d["id"]),
                                              "estensione_fn": _estensione_file(hub, prof, arch, d["id"]),
                                              "titolo": Path(nome_file).stem or nome, "estensione": ext}})
        altri = len(tutti) - len(voci)
        nota = (nota_fn() if nota_fn else "") or (f"E altri {altri}: chiedimeli a voce." if altri > 0 else "")
        c = schede.archivio(f"{chiave}:{tipo}" if per_tipo else chiave,
                            TIPI_PAGINA.get(tipo, "Altri documenti") if per_tipo else titolo, voci, nota=nota)
        c["_scarica_voci"] = sorgenti
        out.append(c)
    return out


def _pagina_documenti(hub, prof) -> dict:
    """La pagina Documenti (28/10, passo 2d, #259): «Fatti da Calliope per te» (`Archive.recenti`,
    la scheda `documento` con «Leggi» e «Scarica») e l'«Archivio di casa» per tipo (`Archivio.
    documenti`, una scheda `archivio` per tipo con «Scarica» del file originale). Chi amministra
    vede anche i documenti fatti per le altre persone di casa, minori compresi, e tutto l'archivio
    (decisione di Dario del 28/10); ognuno dice di chi è. I familiari vedono i propri e l'archivio
    coi permessi della voce; un minore i propri (se il suo preset li ammette) e niente archivio.
    Ogni scheda ha `gruppo`: la pagina scrive il titolo del gruppo sopra la prima."""
    out, note = [], []
    admin = bool(getattr(prof, "admin", False))
    doc = _servizio_documenti(hub)
    if doc is None:
        note.append("I documenti fatti da Calliope qui non ci sono.")
    elif not _documenti_ammessi(prof):
        note.append("Documenti e file per te non li preparo: chiedi a un adulto.")
    else:
        mie = [c for c in (_scheda_documento(doc, r, "Fatti da Calliope per te")
                           for r in doc.recenti(prof.id, DOCUMENTI_PAGINA)) if c]
        out += mie
        if not mie:
            note.append("Calliope non ha ancora preparato documenti per te: chiedimeli a voce.")
        elif hasattr(doc, "conta") and doc.conta(prof.id) > DOCUMENTI_PAGINA:
            # Gli altri ci sono, e si trovano con «Cerca» (la ricerca li guarda tutti)
            note.append(f"Qui ci sono i tuoi ultimi {DOCUMENTI_PAGINA} documenti: gli altri li trovi con «Cerca».")
        if admin and hasattr(doc, "recenti_di_tutti"):
            nomi = _nomi_persone(hub)
            altri: dict = {}
            for r in doc.recenti_di_tutti(DOCUMENTI_PAGINA):
                if r.get("owner") != prof.id:
                    altri.setdefault(r.get("owner"), []).append(r)

            def nome_di(o):
                return nomi.get(o) or altri[o][0].get("owner_name") or "un'altra persona"
            for owner in sorted(altri, key=lambda o: nome_di(o).casefold()):
                nome = nome_di(owner)
                out += [c for c in (_scheda_documento(doc, r, f"Fatti da Calliope per {nome}", nome)
                                    for r in altri[owner]) if c]
    arch = _fonte(hub, "archivio")
    chi = _chi_archivio(prof)
    if arch is not None and chi is not None:
        docs = arch.documenti(chi)
        schede_a = _schede_archivio(hub, prof, arch, docs, f"archivio:{prof.id}")
        for c in schede_a:
            c["gruppo"] = "Archivio di casa"
        out += schede_a
        if not docs:
            note.append("Nell'archivio di casa non ci sono documenti che puoi vedere.")
    elif arch is not None:
        note.append("L'archivio dei documenti di casa per te no.")
    return {"schede": out, "nota": " ".join(note)}


def cerca(hub, prof, raccolta: str, testo: str, log=print) -> dict:
    """La ricerca di una pagina (28/10, passo 2d, #259: i Documenti; 2e, #260: l'Ufficio): {schede, nota} o
    {errore, _stato}. Gli stessi permessi della pagina: i documenti fatti da Calliope della
    persona (di tutti per chi amministra) per parole del titolo, e l'archivio di casa con
    `Archivio.cerca` e il `Chi` della pagina. Il testo cercato non va nel registro."""
    if raccolta not in CON_RICERCA or raccolta not in visibili(prof):
        return {"errore": "qui non si cerca", "_stato": 404}
    t = " ".join(str(testo or "").split())[:CERCA_MAX]
    if not t:
        return {"schede": [], "nota": "Scrivi cosa cercare."}
    try:
        return (_cerca_ufficio if raccolta == "ufficio" else _cerca_documenti)(hub, prof, t)
    except Exception as e:  # noqa: BLE001 — un servizio guasto: la pagina lo dice, il server resta
        log(f"   [SCHERMI] ricerca nella pagina «{raccolta}» non riuscita: {type(e).__name__}")
        return {"errore": "Non riesco a cercare adesso: riprova tra poco.", "_stato": 503}


def _punti_titolo(utili: list, titolo: str) -> float:
    """La pertinenza di un titolo per la ricerca (dalla revisione della PR #268, #260): una parola
    cercata uguale a una del titolo vale 1, una che ne è l'inizio (almeno 3 lettere: «fatt» →
    «fattura») mezzo punto. Parole corte comprese («CV», «Tre re»): basta che non siano vuote."""
    from ..archivio import normalizza as nz
    sue = set(nz.piatto(titolo).split())
    punti = 0.0
    for w in utili:
        if w in sue:
            punti += 1.0
        elif len(w) >= 3 and any(x.startswith(w) for x in sue):
            punti += 0.5
    return punti


def _parole_utili(t: str) -> list:
    """Le parole della ricerca che non sono vuote («di», «è», una lettera sola), senza doppioni,
    nell'ordine dette (come `Archivio.cerca`). Una cifra sola vale: «fattura 3»."""
    from ..archivio import normalizza as nz
    from ..archivio.servizio import _VUOTE
    out = []
    for w in nz.piatto(t).split():
        if w not in _VUOTE and (len(w) > 1 or w.isdigit()) and w not in out:
            out.append(w)
    return out


def _cerca_documenti(hub, prof, t: str) -> dict:
    from pathlib import Path
    out = []
    # Solo parole vere (revisione della PR #268): con «di», «è» o una lettera sola l'archivio non
    # filtra e darebbe i più recenti come «trovati». Dalla seconda revisione (#260) anche le parole
    # corte che non sono vuote («CV», «Tre re»): prima il titolo si confrontava solo sulle parole
    # di 4 lettere o più (`provenienza.parole`) e un titolo fatto di parole corte non si trovava
    utili = _parole_utili(t)
    if not utili:
        return {"schede": [], "nota": "Non c'è niente da cercare: scrivi una parola più lunga."}
    admin = bool(getattr(prof, "admin", False))
    doc = _servizio_documenti(hub)
    trovati = 0
    if doc is not None and _documenti_ammessi(prof):
        righe = (doc.recenti_di_tutti(CERCA_TRA) if admin and hasattr(doc, "recenti_di_tutti")
                 else doc.recenti(prof.id, CERCA_TRA))
        nomi = _nomi_persone(hub)
        # Per pertinenza, poi dal più recente (seconda revisione della PR #268): prima si fermava
        # ai primi 20 dal più recente, e con una parola comune il documento cercato restava fuori
        candidati = []
        for i, r in enumerate(righe):
            if not admin and r.get("owner") != prof.id:
                continue                        # mai di un altro, qualunque cosa dia il servizio
            punti = _punti_titolo(utili, f"{r.get('titolo') or ''} {Path(str(r.get('nome_file') or '')).stem}")
            if punti > 0:
                candidati.append((-punti, i, r))
        candidati.sort(key=lambda x: (x[0], x[1]))
        for _, _, r in candidati:
            nome = "" if r.get("owner") == prof.id else (nomi.get(r.get("owner")) or r.get("owner_name") or "")
            c = _scheda_documento(doc, r, "Fatti da Calliope", nome)
            if c:
                out.append(c)
                trovati += 1
            if trovati >= CERCA_RISULTATI:
                break
    arch = _fonte(hub, "archivio")
    chi = _chi_archivio(prof)
    # All'archivio solo con una parola che usa davvero (revisione della PR #269): `Archivio.cerca`
    # tiene le parole di 2 lettere o più, e con la sola cifra («3», «di 3») non filtrava e dava i
    # 20 documenti più recenti come «trovati»
    if arch is not None and chi is not None and any(len(w) > 1 for w in utili):
        res = arch.cerca(chi, t, limite=CERCA_RISULTATI)
        docs = list(res.get("documenti") or [])
        if docs:
            resto = int(res.get("totale") or 0) - len(docs)
            sch = _schede_archivio(hub, prof, arch, docs, f"archivio:cerca:{prof.id}",
                                   titolo="Trovati nell'archivio di casa", per_tipo=False,
                                   nota_fn=lambda: f"E altri {resto}." if resto > 0 else "")
            for c in sch:
                c["gruppo"] = "Archivio di casa"
            out += sch
            trovati += len(docs)
    nota = (f"Trovati {trovati} documenti." if trovati > 1 else "Trovato un documento." if trovati == 1
            else "Non trovo documenti con queste parole.")
    return {"schede": out, "nota": nota}


# ─────────────────────── 2d: i lavori degli altri, per chi amministra ───────────────────────

def _lavori_degli_altri(hub, svc, prof) -> list:
    """Per chi amministra (decisione di Dario del 28/10, come per i documenti): in coda alla
    pagina Lavori e programmi, per ogni altra persona di casa (minori compresi) i suoi sviluppi,
    i lavori in coda, in corso o fermi a una domanda, i programmi e gli ultimi finiti, in schede
    `lavoro` brevi con titolo, stato, domanda e `di` (il nome), sotto il gruppo «Lavori di …».
    Chiavi `altrui:…`: le schede in diretta degli altri non arrivano a questo schermo, e nessuna
    scheda mandata dopo sostituisce queste; la pagina si rilegge. Gli altri non le vedono mai."""
    import types as _types
    from . import schede
    from ..agenti import risultato as ar
    nomi = _nomi_persone(hub)
    tutti = list(getattr(svc, "lavori", None) or [])
    persone = (set(nomi) | {getattr(lv, "persona", None) for lv in tutti}) - {prof.id, None}
    esec = getattr(svc, "esecuzioni", None)
    programmi = [e for e in list(getattr(esec, "tutte", None) or [])
                 if getattr(e, "persona", None) in persone]
    out = []
    for pid in sorted(persone, key=lambda p: (nomi.get(p) or str(p)).casefold()):
        nome = nomi.get(pid) or next((getattr(lv, "persona_nome", "") for lv in tutti
                                      if getattr(lv, "persona", None) == pid), "") or "un'altra persona"

        def breve(titolo, tipo, stato, riassunto, domanda, chiave, nome=nome):
            c = schede.lavoro(titolo, tipo, stato, riassunto, (), None, "", domanda)
            c["chiave"], c["di"], c["gruppo"] = chiave, nome, f"Lavori di {nome}"
            return c
        for sv in _sviluppi(svc, _types.SimpleNamespace(id=pid))[:4]:
            out.append(breve(f"Sviluppo: {getattr(sv, 'titolo', '') or 'programma'}", "sviluppo",
                             str(getattr(sv, "stato", "") or ""), "", "", f"altrui:sviluppo:{sv.id}"))
        suoi = [lv for lv in tutti if getattr(lv, "persona", None) == pid]
        for lv in sorted((x for x in suoi if x.stato in _ATTIVI), key=lambda x: -float(x.creato or 0)):
            passo = f"Adesso l'agente {lv.passo}." if lv.stato == "in_corso" and getattr(lv, "passo", "") else ""
            out.append(breve(lv.titolo, lv.tipo, lv.stato, passo,
                             (lv.domanda or "") if lv.stato == "in_attesa" else "", f"altrui:lavoro:{lv.id}"))
        for e in [x for x in programmi if x.persona == pid][::-1][:2]:
            titolo = (getattr(e, "titolo", None) or getattr(getattr(e, "lavoro", None), "titolo", "")
                      or getattr(e, "programma", "") or "programma")
            out.append(breve(f"Programma: {titolo}", "esecuzione", str(e.stato), "", "",
                             f"altrui:esecuzione:{e.id}"))
        try:
            finiti = ar.recenti(svc, pid, nomi.get(pid), 3)
        except Exception:  # noqa: BLE001 — la cartella dei risultati illeggibile: niente finiti
            finiti = []
        for lv in finiti:
            out.append(breve(lv.titolo, lv.tipo, lv.stato, ar.riassunto_salvato(lv) or "", "",
                             f"altrui:lavoro:{ar.chiave(lv)}"))
    return out


# ─────────────────────────── 2e: Ufficio, solo chi amministra (#260) ───────────────────────────

# Le serie dell'ufficio nella pagina, in quest'ordine (ufficio/numerazione.FORMATI): il nome del
# gruppo e quello di un documento; le serie dei modelli Word e PowerPoint vengono dopo
SERIE_PAGINA = {"fatture": ("Fatture", "Fattura"), "note_credito": ("Note di credito", "Nota di credito"),
                "preventivi": ("Preventivi", "Preventivo"), "ddt": ("DDT", "DDT")}
UFFICIO_PER_SERIE = 20          # i numeri più recenti di ogni serie; gli altri con «Cerca»
RUBRICA_PAGINA = 60             # i contatti nella pagina, per nome; gli altri con «Cerca»
# I file di un documento dell'ufficio che si scaricano (il PDF, l'XML della FatturaPA, i modelli
# Word e PowerPoint), al più tanti per riga e mai oltre questa dimensione
UFFICIO_FILE = 3
UFFICIO_MAX_BYTE = 50 * 1024 * 1024
CHIAVE_MAX = 80                 # come il taglio della chiave in schede.ufficio


def _servizio_ufficio(hub):
    """Il servizio dell'ufficio (ufficio/servizio.Ufficio) con la numerazione, o None."""
    uff = _fonte(hub, "ufficio")
    if uff is None or getattr(uff, "numeri", None) is None:
        return None
    return uff


def _ufficio_ammesso(prof) -> bool:
    """Solo chi amministra (decisione del 28/10), mai un minore (come `visibili`)."""
    from .. import minori
    return bool(getattr(prof, "admin", False)) and not minori.e_minore(prof)


def _cliente_di(dati: dict) -> str:
    """Il cliente (o il destinatario) di un documento dell'ufficio: il contatto della rubrica
    salvato nei dati all'emissione (`cliente`, o il primo campo anagrafica). Un dato non fidato:
    la pagina lo scrive come testo."""
    from ..ufficio.rubrica import nome_di
    c = dati.get("cliente")
    if not isinstance(c, dict):
        c = next((v for v in dati.values() if isinstance(v, dict) and "nome_completo" in v), c)
    if isinstance(c, dict):
        return str(c.get("nome_completo") or nome_di(c))
    return str(c or "")


def _importo_di(dati: dict) -> str:
    """Il totale salvato all'emissione (`_totale`, dal 28/10) all'italiana; niente per i numeri
    emessi prima e per i DDT (nessun importo): la pagina non rifà i conti."""
    from ..ufficio import conti
    v = dati.get("_totale")
    if v in (None, ""):
        return ""
    try:
        out = conti.euro(conti.dec(v))
        if dati.get("_da_pagare") not in (None, ""):
            out += f", da pagare {conti.euro(conti.dec(dati['_da_pagare']))}"
        return out
    except Exception:  # noqa: BLE001 — un valore strano: niente importo
        return ""


def _data_doc(iso) -> str:
    try:
        return datetime.date.fromisoformat(str(iso)).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return str(iso or "")


def _nomi_serie(serie: str, modello: str = "") -> tuple[str, str]:
    """(nome del gruppo, nome di un documento) di una serie."""
    if serie in SERIE_PAGINA:
        return SERIE_PAGINA[serie]
    nome = str(modello or serie).replace("_", " ").strip() or "Documenti"
    nome = nome[:1].upper() + nome[1:]
    return nome, nome


def _stato_doc(r: dict, femminile: bool) -> tuple[str, bool]:
    """(stato detto, annullato): emesso, annullato col motivo, o in preparazione. L'invio allo SdI
    resta a mano e non si registra: la pagina non dice mai «inviata»."""
    from ..ufficio.numerazione import PRENOTATO
    stato = str(r.get("stato") or "")
    if stato == "annullato":
        nota = " ".join(str(r.get("nota") or "").split())[:160]
        return ("Annullata" if femminile else "Annullato") + (f": {nota}" if nota else ""), True
    if stato == PRENOTATO:
        return "In preparazione", False
    return ("Emessa" if femminile else "Emesso"), False


def _leggi_file_ufficio(hub, prof, uff, serie: str, anno: int, numero: int, percorso: str):
    """Le funzioni che «Scarica» chiama (file_fn, estensione_fn): chi guarda è ancora chi
    amministra (il profilo com'è adesso), il file è ancora uno di quelli registrati per quel
    numero, è un file vero e non è troppo grande; poi i byte. Il percorso viene dal registro dei
    numeri (scritto da Calliope all'emissione), mai da chi chiede."""
    from pathlib import Path

    def percorso_ok():
        ora = _profilo_ora(hub, prof)
        if ora is None or not _ufficio_ammesso(ora):
            return None
        try:
            righe = uff.numeri.elenco(serie, anno)
        except Exception:  # noqa: BLE001 — il registro illeggibile: niente file
            return None
        r = next((x for x in righe if x.get("numero") == numero), None)
        if r is None or percorso not in [str(f) for f in r.get("file") or ()]:
            return None
        try:
            p = Path(percorso)
            if not p.is_file() or p.stat().st_size > UFFICIO_MAX_BYTE:
                return None
        except (OSError, ValueError):
            return None
        return p

    def leggi():
        p = percorso_ok()
        if p is None:
            return None
        try:
            return p.read_bytes(), p.suffix.lstrip(".").lower()
        except OSError:
            return None

    def estensione():
        p = percorso_ok()
        return p.suffix.lstrip(".").lower() if p is not None else None
    return leggi, estensione


def _chiave_file(serie, anno, numero, i) -> str:
    """La chiave di «Scarica» di un file dell'ufficio, al più CHIAVE_MAX caratteri: `schede.ufficio`
    taglia la chiave a 80, e una chiave tagliata non sarebbe più quella registrata (404; revisione
    della PR #269). Le serie dei modelli sono di 30 lettere al più (modelli.py), ma qui non ci si
    conta: oltre il tetto la serie diventa un'impronta."""
    import hashlib
    ck = f"ufficio:file:{serie}:{anno}:{numero}:{i}"
    if len(ck) > CHIAVE_MAX:
        h = hashlib.sha256(str(serie).encode("utf-8")).hexdigest()[:12]
        ck = f"ufficio:file:{h}:{anno}:{numero}:{i}"[:CHIAVE_MAX]
    return ck


def _voce_documento(hub, prof, uff, r: dict) -> tuple[dict, list]:
    """Una riga della scheda `ufficio` per un numero, con le sorgenti di «Scarica»."""
    from pathlib import Path
    from .scarica import ORIGINALI
    _, uno = _nomi_serie(r["serie"], r.get("modello") or "")
    dati = r.get("dati") if isinstance(r.get("dati"), dict) else {}
    stato, annullato = _stato_doc(r, uno.lower().startswith(("fattura", "nota")))
    dettagli = [x for x in (_data_doc(r.get("data")), _cliente_di(dati), _importo_di(dati)) if x]
    file, sorgenti = [], []
    for i, f in enumerate([str(x) for x in r.get("file") or ()][:UFFICIO_FILE]):
        ext = Path(f).suffix.lstrip(".").lower()
        if ext not in ORIGINALI:
            continue
        ck = _chiave_file(r["serie"], r["anno"], r["numero"], i)
        leggi, estensione = _leggi_file_ufficio(hub, prof, uff, r["serie"], int(r["anno"]), int(r["numero"]), f)
        file.append({"chiave": ck, "estensione": ext})
        sorgenti.append({"chiave": ck, "formati": ["originale"],
                         "sorgente": {"file_fn": leggi, "estensione_fn": estensione,
                                      "titolo": Path(f).stem or f"{uno} {r.get('testo') or ''}", "estensione": ext}})
    voce = {"nome": f"{uno} {r.get('testo') or r.get('numero')}", "dettagli": dettagli, "stato": stato,
            "annullato": annullato, "file": file}
    return voce, sorgenti


def _schede_numeri(hub, prof, uff, righe: list, chiave: str, per_serie: bool = True, titolo: str = "",
                   nota_fn=None) -> list:
    """Le schede `ufficio` dei documenti: una per serie (`per_serie`, i più recenti per primi, al
    più UFFICIO_PER_SERIE) o una sola (`titolo`, per la ricerca)."""
    from . import schede
    gruppi: dict = {}
    for r in righe:
        gruppi.setdefault(r["serie"] if per_serie else "", []).append(r)
    ordine = [k for k in SERIE_PAGINA if k in gruppi] + sorted(k for k in gruppi if k not in SERIE_PAGINA)
    out = []
    for serie in ordine:
        tutte = gruppi[serie]
        voci, sorgenti = [], []
        for r in tutte[:UFFICIO_PER_SERIE]:
            v, s = _voce_documento(hub, prof, uff, r)
            voci.append(v)
            sorgenti += s
        altri = len(tutte) - len(voci)
        nota = (nota_fn() if nota_fn else "") or (f"E altri {altri}: cercali con «Cerca»." if altri > 0 else "")
        nome = _nomi_serie(serie, tutte[0].get("modello") or "")[0] if per_serie else titolo
        c = schede.ufficio(f"{chiave}:{serie}" if per_serie else chiave, nome, voci, nota=nota)
        c["gruppo"] = "Documenti dell'ufficio"
        c["_scarica_voci"] = sorgenti
        out.append(c)
    return out


def _voce_contatto(c: dict) -> dict:
    """Una riga della rubrica: nome, tipo, partita IVA o codice fiscale, luogo, recapiti, e di chi
    è (di casa o solo sua). Dati non fidati: la pagina li scrive come testo."""
    from ..ufficio.rubrica import CASA
    luogo = " ".join(str(x) for x in (c.get("cap"), c.get("comune")) if x)
    if c.get("provincia") and luogo:
        luogo += f" ({c['provincia']})"
    codice = (f"P. IVA {c['partita_iva']}" if c.get("partita_iva")
              else f"CF {c['codice_fiscale']}" if c.get("codice_fiscale") else "")
    tipo = str(c.get("tipo") or "")
    dettagli = [x for x in (tipo[:1].upper() + tipo[1:], codice, luogo, c.get("email"), c.get("pec"),
                            c.get("telefono")) if x]
    return {"nome": str(c.get("nome_completo") or "Senza nome"), "dettagli": [str(x) for x in dettagli],
            "stato": "Di casa" if c.get("ambito") == CASA else "Solo tua", "annullato": False, "file": []}


def _scheda_rubrica(contatti: list, chiave: str, titolo: str = "Rubrica", nota: str = "") -> dict:
    from . import schede
    c = schede.ufficio(chiave, titolo, [_voce_contatto(x) for x in contatti], nota=nota,
                       vuoto="La rubrica è vuota: i contatti si aggiungono a voce.")
    c["gruppo"] = "Rubrica"
    return c


def _numeri_recenti(uff) -> list:
    """Tutti i numeri con i dati, dal più recente (quando è stato preso il numero; a parità anno e
    numero all'indietro)."""
    righe = uff.numeri.elenco(con_dati=True)
    return sorted(righe, key=lambda r: (-float(r.get("creato") or 0), -int(r.get("anno") or 0),
                                        -int(r.get("numero") or 0)))


def _contatti(uff, prof) -> list | None:
    rub = getattr(uff, "rubrica", None)
    if rub is None:
        return None
    return sorted(rub.visibili(prof.id), key=lambda c: str(c.get("nome_completo") or "").casefold())


def _pagina_ufficio(hub, prof) -> dict:
    """La pagina Ufficio (28/10, passo 2e, #260; progetto § 4.9): solo sugli schermi personali di
    chi amministra (decisione del 28/10; `visibili` la nasconde agli altri, e qui si ricontrolla).
    Fatture, note di credito, preventivi e DDT (e le serie dei modelli) da `Numeratore.elenco`, una
    scheda `ufficio` per serie: numero, data, cliente, importo, stato (emesso o annullato col
    motivo) e «Scarica» dei file generati (PDF, XML della FatturaPA); poi la rubrica
    (`Rubrica.visibili`: di casa e sua). In sola lettura: emettere, annullare e cambiare la rubrica
    si fa a voce, e l'invio allo SdI resta a mano."""
    if not _ufficio_ammesso(prof):
        return {"errore": "raccolta sconosciuta", "_stato": 404}
    uff = _servizio_ufficio(hub)
    if uff is None:
        return {"schede": [], "nota": "L'ufficio non è attivo qui: fatture, preventivi e DDT non ci sono."}
    out = _schede_numeri(hub, prof, uff, _numeri_recenti(uff), f"ufficio:{prof.id}")
    note = [] if out else ["Non ci sono ancora fatture, preventivi né DDT: si preparano a voce."]
    contatti = _contatti(uff, prof)
    if contatti is not None:
        altri = len(contatti) - RUBRICA_PAGINA
        out.append(_scheda_rubrica(contatti[:RUBRICA_PAGINA], f"ufficio:rubrica:{prof.id}",
                                   nota=f"E altri {altri}: cercali con «Cerca»." if altri > 0 else ""))
    note.append("L'invio allo SdI lo fai tu, a mano: io preparo i file.")
    return {"schede": out, "nota": " ".join(note)}


def _cerca_ufficio(hub, prof, t: str) -> dict:
    """La ricerca nella pagina Ufficio, con le regole di quella dei Documenti: le parole che non
    sono vuote, per pertinenza e poi dal più recente, al più CERCA_RISULTATI documenti e altrettanti
    contatti. Un documento si trova per numero («12», «2026»), tipo, cliente e titolo; un contatto
    per nome, comune, partita IVA o codice fiscale."""
    if not _ufficio_ammesso(prof):
        return {"errore": "qui non si cerca", "_stato": 404}
    utili = _parole_utili(t)
    if not utili:
        return {"schede": [], "nota": "Non c'è niente da cercare: scrivi una parola più lunga."}
    uff = _servizio_ufficio(hub)
    if uff is None:
        return {"schede": [], "nota": "L'ufficio non è attivo qui."}
    candidati = []
    for i, r in enumerate(_numeri_recenti(uff)):
        _, uno = _nomi_serie(r["serie"], r.get("modello") or "")
        dati = r.get("dati") if isinstance(r.get("dati"), dict) else {}
        # Il tipo e il numero contano il doppio: «fattura 1» è la fattura numero 1, non quella di
        # un cliente con un «1» nel nome
        p = (2 * _punti_titolo(utili, f"{uno} {r.get('testo') or ''}")
             + _punti_titolo(utili, f"{_cliente_di(dati)} {r.get('titolo') or ''}"))
        if p > 0:
            candidati.append((-p, i, r))
    candidati.sort(key=lambda x: (x[0], x[1]))
    numeri = [r for _, _, r in candidati[:CERCA_RISULTATI]]
    out = []
    if numeri:
        resto = len(candidati) - len(numeri)
        out += _schede_numeri(hub, prof, uff, numeri, f"ufficio:cerca:{prof.id}", per_serie=False,
                              titolo="Trovati fra i documenti",
                              nota_fn=lambda: f"E altri {resto}." if resto > 0 else "")
    trovati = []
    cand = []
    for i, c in enumerate(_contatti(uff, prof) or []):
        p = _punti_titolo(utili, " ".join(str(c.get(k) or "") for k in
                                          ("nome_completo", "comune", "partita_iva", "codice_fiscale")))
        if p > 0:
            cand.append((-p, i, c))
    cand.sort(key=lambda x: (x[0], x[1]))
    trovati = [c for _, _, c in cand[:CERCA_RISULTATI]]
    if trovati:
        out.append(_scheda_rubrica(trovati, f"ufficio:rubrica:cerca:{prof.id}", "Trovati in rubrica"))
    n = len(numeri) + len(trovati)
    nota = (f"Trovati {n} risultati." if n > 1 else "Trovato un risultato." if n == 1
            else "Non trovo documenti né contatti con queste parole.")
    return {"schede": out, "nota": nota}
