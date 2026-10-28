"""
Le schede da mostrare sugli schermi, costruite dal codice dei tool (mai dall'LLM).

Una scheda è un dizionario JSON con `tipo`, `titolo`, `visibilita` e i dati del suo tipo; la
pagina (pagina/schermo.js) la disegna con `textContent`, mai come HTML. Tipi:

  lista       voci della lista, con quelle appena aggiunte in evidenza           casa
  timer       timer della casa con la fine (epoch): il conto alla rovescia è
              nella pagina; chi l'ha messo (28/10)                                pubblica
  promemoria  promemoria e appuntamenti di una persona, tutti o di un giorno
              della pagina Agenda (28/10: oggi, domani, in settimana)             personale
  biblioteca  voce, fonte, passaggio usato e un testo più lungo da leggere        pubblica
  documento   anteprima del documento appena creato o cambiato (dal suo JSON), o il
              testo in Markdown di un lavoro dell'agente (07/10: `markdown`, letto dalla
              pagina con il suo lettore, mai come HTML); con «Scarica» (`scarica`)    personale
  casa        dispositivi letti da casa_stato, con lo stato                       casa
  calcolo     espressione e risultato                                             pubblica
  web         risultati di una ricerca su internet: titolo, sito, testo (03/10)   pubblica
  lavoro      un lavoro dell'agente: in diretta mentre lavora (passo, ultimi passi, file,
              testo in arrivo, tetti; 03/10) e poi il risultato: riassunto, test, codice personale
  esecuzione  il programma di un lavoro mentre gira: stdout e stderr in diretta, tempo,
              codice d'uscita (04/10)                                             personale
  testo       una risposta da leggere («fammelo leggere»)                         dipende
  risposta    la risposta a una frase scritta, sullo schermo da cui è arrivata
              (04/10: chi scrive spesso non può ascoltare); solo a quello schermo  dipende
  foto        la miniatura di una foto della conversazione (05/10, calliope/immagini.py):
              mandata dal telefono o dallo schermo, o presa da webcam e schermo    personale
  allegato    un file allegato alla conversazione (05/10, calliope/allegati.py): nome,
              tipo, dimensione, note e l'inizio del testo come anteprima           personale
  cassetto    i file del cassetto della persona (08/10, calliope/cassetto.py): un
              carosello con anteprima, nome, quando e da dove, e i pulsanti Tieni,
              Elimina, Tieni ancora (POST /api/cassetto); la costruisce Cassetto.scheda  personale
  vuota       torna all'orologio («togli dallo schermo»)                          pubblica

Visibilità (docs/ricerche/2026-10-01-mappe-e-schermi.md, §10.4): `pubblica` va su ogni
schermo della stanza, anche per gli ospiti; `casa` solo se chi parla è riconosciuto;
`personale` solo sugli schermi personali di chi parla, mai su quello del soggiorno. La
decide chi costruisce la scheda, qui: il modello non la sceglie.

Le schede sono piccole (testi tagliati): passano su SSE a ogni schermo della stanza.

Sezione (27/10, `sezione`): dove la scheda sta sul telefono a sezioni (`SEZIONE_DI_TIPO`); la
pagina non decide altro che dove mostrarla.

Le chiavi che cominciano con «_» restano sul server (hub.py le toglie prima di mandare la
scheda e di metterla nella cronologia): `_scarica` è la sorgente intera del documento per il
pulsante «Scarica» (schermi/scarica.py), il Markdown o il JSON a blocchi.

Identità (02/10, `chiave`): una scheda legata a un oggetto ha una chiave stabile
(`timer:<id dell'agenda>-<creazione>`, `agenda:<persona>`, `documento:<id del documento>`,
`lista:<chiave della lista>`, `lavoro:<id>`). Una scheda con la stessa chiave **sostituisce**
quella mostrata: niente doppioni nella cronologia (hub.py e la pagina). Di norma si sposta
in cima, come l'ultima arrivata (è cambiata per un'azione o un evento: modifica, annullo,
scadenza); con `sposta: false` resta dov'è e non passa in primo piano (aggiornamenti
automatici e frequenti). Le schede senza oggetto (calcoli, biblioteca, testi) non hanno
chiave: ogni volta una nuova. `id` resta diverso a ogni invio.
"""

import datetime
import re
import time
import uuid

PUBBLICA, CASA, PERSONALE = "pubblica", "casa", "personale"
VISIBILITA = (PUBBLICA, CASA, PERSONALE)
# Quanto resta sullo schermo una scheda prima di tornare all'orologio (la cronologia resta)
DURATA_S = 600.0

_MAX_VOCI = 60
_MAX_TESTO = 4000
# L'uscita di un programma sulla scheda «esecuzione» (la coda: il resto è nel file)
_MAX_USCITA = 12_000


# Il telefono a sezioni (27/10, docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md, 3.2): la
# casa fissa di ogni tipo sul satellite personale, «sezione» o «sezione/raccolta», scritta nella
# scheda (`sezione`). La stessa tabella è in pagina/schermo.js per le schede che non passano da
# `nuova` (chat, cruscotto, sviluppo): prove/prova_sezioni.py le confronta. Un tipo che manca va
# nella conversazione
SEZIONI = ("adesso", "conversazione", "cose", "casa", "io")
SEZIONE_DI_TIPO = {
    "risposta": "conversazione", "calcolo": "conversazione", "biblioteca": "conversazione",
    "web": "conversazione", "testo": "conversazione", "chat": "conversazione",
    "timer": "cose/agenda", "promemoria": "cose/agenda", "lista": "cose/liste",
    "lavoro": "cose/lavori", "esecuzione": "cose/lavori", "sviluppo": "cose/lavori",
    "documento": "cose/documenti", "archivio": "cose/documenti", "ufficio": "cose/ufficio",
    "foto": "cose/cassetto", "allegato": "cose/cassetto",
    "cassetto": "cose/cassetto", "modulo": "cose", "gioco": "cose/giochi", "giochi": "cose/giochi",
    "esercizio": "cose/studio", "esercizi_riepilogo": "cose/studio",
    "casa": "casa", "conoscente": "casa", "avviso": "casa", "cruscotto": "io",
}


def sezione_di(tipo: str) -> str:
    return SEZIONE_DI_TIPO.get(tipo, "conversazione")


def _taglia(testo, n: int) -> str:
    t = re.sub(r"\s+", " ", str(testo or "")).strip()
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def nuova(tipo: str, titolo: str, visibilita: str, durata_s: float | None = DURATA_S,
          chiave: str | None = None, sposta: bool = True, **dati) -> dict:
    if visibilita not in VISIBILITA:
        raise ValueError(f"visibilità sconosciuta: {visibilita}")
    now = time.time()
    return {"id": uuid.uuid4().hex[:12], "tipo": tipo, "titolo": _taglia(titolo, 120),
            "visibilita": visibilita, "creata": now, "sezione": sezione_di(tipo),
            "scade": (now + durata_s) if durata_s else None,
            **({"chiave": str(chiave)} if chiave else {}),
            **({} if sposta else {"sposta": False}), **dati}


def aggiornamento(scheda: dict) -> dict:
    """La stessa scheda come aggiornamento automatico: sostituisce quella con la stessa
    chiave dov'è, senza portarla in cima né in primo piano."""
    return {**scheda, "sposta": False}


# ─────────────────────────── liste ───────────────────────────

def lista(key: str, voci: list[str], aggiunti=(), tolti=()) -> dict:
    """La lista intera (della casa: visibile ai familiari), con le voci appena aggiunte."""
    titolo = "Lista della spesa" if key == "spesa" else f"Lista {key}"
    nuove = {str(a).lower() for a in aggiunti or ()}
    return nuova("lista", titolo, CASA, chiave=f"lista:{key}", lista=key,
                 voci=[{"testo": _taglia(v, 80), "nuova": str(v).lower() in nuove}
                       for v in (voci or [])[:_MAX_VOCI]],
                 altre=max(0, len(voci or []) - _MAX_VOCI),
                 tolti=[_taglia(t, 80) for t in (tolti or [])][:10])


# ─────────────────────────── agenda ───────────────────────────

# Quanto resta in primo piano un timer annullato o scaduto, con lo stato scritto: poi la
# pagina torna all'orologio e la scheda resta nella cronologia. Scelto invece di farla
# sparire: chi guarda lo schermo vede che cosa è successo («annullato alle 23:05»,
# «scaduto alle 23:07»); una scheda che svanisce da sola lascerebbe il dubbio
DURATA_FINITO_S = 60.0


def chiave_timer(item: dict) -> str:
    """`timer:<id>-<creato in ms>`: SQLite riusa l'id più alto dopo una cancellazione (il timer
    annullato e quello nuovo avrebbero la stessa identità); con l'istante di creazione no.
    Non la fine (03/10): un timer cambiato («impostalo di un minuto») resta la stessa scheda,
    aggiornata al suo posto. Senza `created` (voci vecchie) vale la fine."""
    created = item.get("created")
    return f"timer:{item['id']}-{int(created * 1000) if created else int(item['due'])}"


def timer(item: dict, stato: str = "attivo", quando: float | None = None) -> dict:
    """Un timer della casa (una voce dell'agenda), con la sua identità `timer:<id>`: la
    pagina conta alla rovescia fino a `fine` (epoch). `stato` «annullato» o «scaduto»:
    la stessa scheda aggiornata, con l'ora."""
    now = time.time()
    etichetta = _taglia(item["label"], 60)
    voce = {"etichetta": etichetta, "fine": item["due"]}
    if item.get("owner_name"):
        # Chi l'ha messo (28/10, #257): la pagina lo scrive solo sugli schermi personali
        voce["chi"] = _taglia(item["owner_name"], 40)
    if stato != "attivo":
        ora = datetime.datetime.fromtimestamp(quando or now).strftime("%H:%M")
        voce.update(stato=stato, nota=f"{stato} alle {ora}")
        durata = DURATA_FINITO_S
    else:
        durata = max(60.0, item["due"] - now + 60.0)
    return nuova("timer", f"Timer {etichetta}", PUBBLICA, durata_s=durata,
                 chiave=chiave_timer(item), timer=[voce], stato=stato, ora_server=now)


def timer_attivi(agenda) -> list[dict]:
    """Una scheda per ogni timer attivo; nessuno: una scheda «Timer» vuota (senza chiave)."""
    now = time.time()
    voci = [it for it in agenda.items(None) if it["kind"] == "timer" and it["due"] > now - 5]
    if not voci:
        return [nuova("timer", "Timer", PUBBLICA, durata_s=60.0, timer=[], ora_server=now)]
    return [timer(it) for it in voci[:6]]


def _quando(ts: float) -> str:
    d = datetime.datetime.fromtimestamp(ts)
    oggi = datetime.date.today()
    giorno = ("oggi" if d.date() == oggi else "domani" if d.date() == oggi
              + datetime.timedelta(days=1) else d.strftime("%d/%m"))
    return f"{giorno} alle {d.strftime('%H:%M')}"


def promemoria(agenda, persona: str, nome: str | None = None) -> dict:
    """Promemoria e appuntamenti di una persona: personale."""
    voci = []
    for it in agenda.items(persona):
        if it["kind"] in ("promemoria", "appuntamento"):
            voci.append({"testo": _taglia(it["label"], 80), "quando": _quando(it["due"]),
                         "ts": it["due"], "tipo": it["kind"]})
    titolo = f"Agenda di {nome}" if nome else "Agenda"
    return nuova("promemoria", titolo, PERSONALE, chiave=f"agenda:{persona}", voci=voci[:30])


_GIORNI = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")
# La vista per giorno della pagina Agenda (28/10, #257, agenda.per_giorno): titolo e frase del
# vuoto di ogni giorno
GIORNI_AGENDA = (("oggi", "Oggi", "Niente oggi."), ("domani", "Domani", "Niente domani."),
                 ("settimana", "In settimana", "Niente nei prossimi giorni."))


def giorno(persona: str, quale: str, voci: list[dict], dopo: int = 0) -> dict:
    """Promemoria e appuntamenti di una persona per un giorno della vista (`GIORNI_AGENDA`):
    una scheda `promemoria` (lo stesso disegno), personale, con la sua identità
    `agenda:<persona>:<giorno>` (non sostituisce quella di tutta l'agenda). Oggi e domani con
    la sola ora; in settimana con il giorno («gio 30/10 alle 9:00»). `dopo`: quante voci oltre
    la settimana (solo nell'ultima)."""
    titolo, vuoto = next((t, v) for k, t, v in GIORNI_AGENDA if k == quale)
    righe = []
    for it in voci[:30]:
        d = datetime.datetime.fromtimestamp(it["due"])
        ora = f"alle {d.strftime('%H:%M')}"
        righe.append({"testo": _taglia(it["label"], 80), "ts": it["due"], "tipo": it["kind"],
                      "quando": ora if quale != "settimana"
                      else f"{_GIORNI[d.weekday()]} {d.strftime('%d/%m')} {ora}"})
    altro = {"altre": dopo} if dopo else {}
    return nuova("promemoria", titolo, PERSONALE, durata_s=None,
                 chiave=f"agenda:{persona}:{quale}", voci=righe, vuoto=vuoto,
                 giorno=quale, **altro)


# ─────────────────────────── biblioteca ───────────────────────────

def biblioteca(domanda: str, passaggi: list, testo_lungo: str = "") -> dict:
    """La voce trovata: titolo, fonte, il passaggio migliore e un testo più lungo."""
    p = passaggi[0]
    altre = list(dict.fromkeys(q.titolo for q in passaggi[1:] if q.titolo != p.titolo))
    return nuova("biblioteca", p.titolo, PUBBLICA, fonte=p.fonte,
                 domanda=_taglia(domanda, 160), passaggio=_taglia(p.testo, 900),
                 testo=_taglia(testo_lungo, _MAX_TESTO) if testo_lungo else "",
                 altre=altre[:3])


# ─────────────────────────── documenti ───────────────────────────

def documento(doc: dict, formato: str, nome_file: str, modifica: str = "",
              ident=None) -> dict:
    """Anteprima dal JSON validato del documento (calliope/documenti/formato.py), con i
    totali calcolati dal programma come nel file."""
    from ..documenti.formato import table_total
    blocchi = []
    if formato == "excel":
        for s in doc.get("fogli", [])[:3]:
            righe = [[str(c) for c in r] for r in s.get("righe", [])[:50]]
            tot = table_total(s["colonne"], s["righe"]) if s.get("totale") else None
            blocchi.append({"tipo": "tabella", "nome": _taglia(s.get("nome", ""), 60),
                            "colonne": [str(c) for c in s.get("colonne", [])],
                            "righe": righe, "totale": tot})
    else:
        for b in doc.get("blocchi", [])[:40]:
            t = b.get("tipo")
            if t in ("titolo", "paragrafo"):
                blocchi.append({"tipo": t, "testo": _taglia(b.get("testo", ""), 1500),
                                **({"allinea": b["allinea"]} if b.get("allinea") else {})})
            elif t == "elenco":
                blocchi.append({"tipo": "elenco", "numerato": bool(b.get("numerato")),
                                "voci": [_taglia(v, 300) for v in b.get("voci", [])[:40]]})
            elif t == "tabella":
                tot = table_total(b["colonne"], b["righe"]) if b.get("totale") else None
                blocchi.append({"tipo": "tabella", "colonne": [str(c) for c in b["colonne"]],
                                "righe": [[str(c) for c in r] for r in b["righe"][:50]],
                                "totale": tot})
    # Identità: l'id del documento nell'archivio; senza, il nome del file
    chiave = f"documento:{ident}" if ident is not None else (
        f"file:{nome_file}" if nome_file else None)
    return nuova("documento", doc.get("titolo") or "Documento", PERSONALE, chiave=chiave,
                 formato=formato, file=_taglia(nome_file, 120),
                 modifica=_taglia(modifica, 200), blocchi=blocchi,
                 # «Scarica» (07/10): il file nel suo formato e negli altri, convertito al clic
                 scarica=list(SCARICA_FOGLIO if formato == "excel" else SCARICA_TESTO),
                 _scarica={"documento": doc, "formato": formato,
                           "titolo": doc.get("titolo") or "Documento"})


# I formati del pulsante «Scarica» (schermi/scarica.py)
SCARICA_TESTO = ("md", "pdf", "word")
SCARICA_FOGLIO = ("excel", "md")
# Il Markdown sulla scheda: oltre, la scheda dice che il testo intero è nel file (e «Scarica»
# lo dà intero: la sorgente resta sul server)
MAX_MARKDOWN = 60_000


def documento_markdown(titolo: str, testo: str, ident=None, riassunto: str = "",
                       nome_file: str = "", cartella: str = "", chiave: str | None = None,
                       stato: str = "") -> dict:
    """Un testo in Markdown dell'agente (07/10: ricerche, relazioni, riassunti in
    `risultato.md`): la pagina lo legge con il suo lettore (sottoinsieme, createElement e
    textContent, mai innerHTML: il testo dell'agente non è fidato), con il sommario dei titoli
    in alto e «Scarica» in MD, PDF e Word. Chiave `lavoro:<id>` per un lavoro (sostituisce
    la scheda in diretta), personale come il lavoro."""
    t = str(testo or "")
    if chiave is None and ident is not None:
        chiave = f"lavoro:{ident}"
    return nuova("documento", titolo or "Documento", PERSONALE, durata_s=1800.0, chiave=chiave,
                 formato="md", file=_taglia(nome_file, 120), modifica="", blocchi=[],
                 markdown=t[:MAX_MARKDOWN], tagliato=len(t) > MAX_MARKDOWN,
                 riassunto=_taglia(riassunto, 600), cartella=_taglia(cartella, 160),
                 stato=stato, scarica=list(SCARICA_TESTO),
                 _scarica={"markdown": t, "titolo": titolo or "Documento"})


# ─────────────────────────── casa ───────────────────────────

def casa(entita: list, titolo: str = "Casa") -> dict:
    """Dispositivi e sensori con lo stato detto («accesa al 40 per cento»), per stanza."""
    from ..casa.parole import stato_detto
    righe = []
    for e in entita[:40]:
        stato = re.sub(r"^(?:è|sono)\s+", "", stato_detto(e))
        righe.append({"nome": _taglia(e.nome, 60), "stanza": e.area or "",
                      "stato": _taglia(stato, 60),
                      "acceso": e.stato in ("on", "open", "playing", "unlocked")})
    righe.sort(key=lambda r: (r["stanza"] or "~", r["nome"]))
    return nuova("casa", titolo, CASA, righe=righe)


# ─────────────────────────── ricerca su internet ───────────────────────────

def web(domanda: str, risultati: list) -> dict:
    """I risultati di web_cerca (calliope/web/): titolo, sito (il nome, e il dominio per chi
    legge) e testo. Pubblica: la domanda è già senza dati personali (privacy.Ripulitore).
    Testo di siti internet: la pagina lo mostra con textContent, mai come HTML."""
    from urllib.parse import urlsplit
    voci = []
    for r in risultati[:6]:
        host = (urlsplit(getattr(r, "url", "") or "").hostname or "")
        voci.append({"titolo": _taglia(getattr(r, "titolo", ""), 140),
                     "sito": _taglia(getattr(r, "sito", ""), 60),
                     "dominio": _taglia(host.removeprefix("www."), 80),
                     "testo": _taglia(getattr(r, "testo", ""), 420),
                     "data": _taglia(getattr(r, "data", ""), 20)})
    return nuova("web", "Da internet", PUBBLICA, domanda=_taglia(domanda, 160), voci=voci)


def notizie(domanda: str, voci: list[dict]) -> dict:
    """Le notizie dei feed (13/10, calliope/notizie/): la scheda dei risultati web con il
    titolo «Notizie», una voce per fatto (titolo, testate, sommario, quando, dominio del link).
    Pubblica: titoli dei giornali, nessun dato di casa. Mostrata con textContent."""
    from urllib.parse import urlsplit
    out = []
    for v in voci[:6]:
        host = (urlsplit(str(v.get("url") or "")).hostname or "")
        out.append({"titolo": _taglia(v.get("titolo"), 140), "sito": _taglia(v.get("sito"), 60),
                    "dominio": _taglia(host.removeprefix("www."), 80),
                    "testo": _taglia(v.get("testo"), 420), "data": _taglia(v.get("data"), 30)})
    return nuova("web", "Notizie", PUBBLICA, domanda=_taglia(domanda, 160), voci=out)


# ─────────────────────────── calcoli e testi ───────────────────────────

def calcolo(espressione: str, risultato: str) -> dict:
    bella = (str(espressione or "").replace("**", "^").replace("*", "×").replace("/", "÷")
             .replace(".", ","))
    return nuova("calcolo", "Calcolo", PUBBLICA, espressione=_taglia(bella, 200),
                 risultato=_taglia(risultato, 80))


def lavoro(titolo: str, tipo: str, stato: str, riassunto: str, file=(), test=None,
           cartella: str = "", domanda: str = "", ident=None) -> dict:
    """Il risultato di un lavoro dell'agente (calliope/agenti/): riassunto, esito dei test e i
    file, con il codice **intero** (a capo e rientri conservati: qui non si comprimono gli
    spazi). Personale: è di chi l'ha chiesto. A voce il codice non si legge mai."""
    voci = []
    for f in list(file or [])[:8]:
        t = str(f.get("testo") or "")
        if len(t) > 12000:
            t = t[:12000] + "\n…"
        voci.append({"nome": _taglia(f.get("nome"), 120), "testo": t})
    esito = None
    if isinstance(test, dict):
        esito = {k: int(test.get(k) or 0) for k in ("eseguiti", "falliti", "errori", "saltati")}
    return nuova("lavoro", titolo or "Lavoro", PERSONALE, durata_s=1800.0,
                 chiave=f"lavoro:{ident}" if ident is not None else None, lavoro=tipo,
                 stato=stato, riassunto=_taglia(riassunto, 600), test=esito,
                 cartella=_taglia(cartella, 160), domanda=_taglia(domanda, 300), file=voci)


def lavoro_avanzamento(titolo: str, tipo: str, stato: str, av: dict, ident=None,
                       sposta: bool = False) -> dict:
    """Il lavoro dell'agente **mentre** lavora (calliope/agenti/avanzamento.py): stessa
    chiave `lavoro:<id>` della scheda finale, che la sostituirà. `av`: passo, pausa, passi
    recenti, file scritti (nomi e righe), anteprima breve del codice, testo in arrivo, test,
    passate/token/secondi con i tetti. Di norma `sposta: false` (aggiornamento automatico);
    la prima scheda del lavoro va in cima. Personale come la finale."""
    a = dict(av or {})
    a["passo"] = _taglia(a.get("passo"), 160)
    a["passi"] = [{"ora": p.get("ora"), "testo": _taglia(p.get("testo"), 160)}
                  for p in (a.get("passi") or [])][-8:]
    a["file"] = [{"nome": _taglia(f.get("nome"), 120), "righe": int(f.get("righe") or 0)}
                 for f in (a.get("file") or [])][:12]
    if a.get("anteprima"):
        a["anteprima"] = {"nome": _taglia(a["anteprima"].get("nome"), 120),
                          "testo": str(a["anteprima"].get("testo") or "")[:1600]}
    if isinstance(a.get("flusso"), dict) and "pezzi" in a["flusso"]:
        # Il flusso a sequenza (08/10, avanzamento.py): i pezzi nuovi, numerati; la pagina li
        # accumula. Qui solo la forma (il testo resta dell'agente: la pagina usa textContent)
        f = a["flusso"]
        a["flusso"] = {"id": str(f.get("id") or ""), "fino": int(f.get("fino") or 0),
                       "pezzi": [{"n": int(p["n"]), "s": int(p.get("s") or 0),
                                  "t": str(p.get("t") or "testo"), "x": str(p.get("x") or ""),
                                  **({"f": _taglia(p["f"], 160)} if p.get("f") else {})}
                                 for p in (f.get("pezzi") or [])],
                       **({"finestra": True, "taglio": bool(f.get("taglio"))}
                          if f.get("finestra") else {})}
    elif a.get("flusso"):
        t = str(a["flusso"].get("testo") or "")
        a["flusso"] = {"tipo": str(a["flusso"].get("tipo") or "testo"), "testo": t[-800:]}
    return nuova("lavoro", titolo or "Lavoro", PERSONALE, durata_s=1800.0,
                 chiave=f"lavoro:{ident}" if ident is not None else None, sposta=sposta,
                 lavoro=tipo, stato=stato, riassunto="", test=a.get("test"), cartella="",
                 domanda="", file=[], avanzamento=a)


def esecuzione(titolo: str, programma: str, linguaggio: str, stato: str, dati, righe,
               omessi: int, codice_uscita, inizio: float, trascorso_s: float, max_s: float,
               ident=None, sposta: bool = True, file: str = "",
               ora_server: float | None = None) -> dict:
    """Il programma di un lavoro dell'agente **mentre gira** (04/10, agenti/esecuzione.py):
    `righe` sono pezzi dell'uscita [{tipo: out|err, testo}] (la coda: il testo intero è nel
    file), `omessi` i caratteri tagliati, `dati` gli argomenti dati. Il tempo che scorre lo
    conta la pagina da `dal` finché lo stato è «in_corso». Chiave `esecuzione:<lavoro>-<n>`:
    gli aggiornamenti la sostituiscono al suo posto. Personale come il lavoro."""
    pezzi = []
    for r in list(righe or [])[-400:]:
        tipo = "err" if r.get("tipo") == "err" else "out"
        pezzi.append({"tipo": tipo, "testo": str(r.get("testo") or "")[-_MAX_USCITA:]})
    return nuova("esecuzione", titolo or "Programma", PERSONALE, durata_s=1800.0,
                 chiave=f"esecuzione:{ident}" if ident is not None else None, sposta=sposta,
                 programma=_taglia(programma, 120), linguaggio=_taglia(linguaggio, 20),
                 stato=stato, dati=[_taglia(d, 80) for d in list(dati or [])[:20]],
                 righe=pezzi, omessi=int(omessi or 0), codice_uscita=codice_uscita,
                 dal=round(inizio, 3) if stato == "in_corso" else None,
                 trascorso_s=round(float(trascorso_s or 0), 2), max_s=round(float(max_s or 0)),
                 file=_taglia(file, 120), ora_server=ora_server or time.time())


def giochi(chiave: str, titolo: str, giochi=(), partite=(), nota: str = "", vuoto: str = "") -> dict:
    """Le partite aperte e i giochi di casa nella pagina Giochi di Le mie cose (28/10, passo 2c,
    #258, schermi/raccolte.py): solo testo, nessun tasto (un gioco si apre a voce, e il riquadro
    vero è la scheda `gioco`). `giochi`: [{titolo, descrizione, giocatori, dire}]; `partite`:
    [{titolo, dove, qui, prova, tocca, punti: [{nome, punti}], esito}]. Personale: è la pagina
    di chi la guarda."""
    def num(x):
        return x if isinstance(x, (int, float)) and not isinstance(x, bool) else 0
    return nuova("giochi", titolo, PERSONALE, durata_s=None, chiave=chiave,
                 giochi=[{"titolo": _taglia(g.get("titolo"), 60), "descrizione": _taglia(g.get("descrizione"), 200),
                          "giocatori": _taglia(g.get("giocatori"), 40), "dire": _taglia(g.get("dire"), 100)}
                         for g in list(giochi or ())[:_MAX_VOCI]],
                 partite=[{"titolo": _taglia(p.get("titolo"), 60),
                           "dove": [_taglia(d, 60) for d in list(p.get("dove") or ())[:8]],
                           "qui": bool(p.get("qui")), "prova": bool(p.get("prova")),
                           "tocca": _taglia(p.get("tocca"), 30), "esito": _taglia(p.get("esito"), 160),
                           "punti": [{"nome": _taglia(x.get("nome"), 30), "punti": num(x.get("punti"))}
                                     for x in list(p.get("punti") or ())[:8]]}
                          for p in list(partite or ())[:12]],
                 nota=_taglia(nota, 300), vuoto=_taglia(vuoto, 200))


def archivio(chiave: str, titolo: str, voci=(), nota: str = "", vuoto: str = "") -> dict:
    """Un gruppo di documenti dell'archivio di casa nella pagina Documenti di Le mie cose (28/10,
    passo 2d, #259, schermi/raccolte.py): una riga per documento con nome, data, importo, di chi è
    (`di`, solo nella pagina di chi amministra) e «Scarica» del file originale (`chiave` della
    riga, `estensione`). Solo testo: il nome viene dai dati estratti dal documento, un dato non
    fidato. Le sorgenti di «Scarica» stanno in `_scarica_voci` e restano sul server. Personale:
    è la pagina di chi la guarda."""
    out = []
    for v in list(voci or ())[:_MAX_VOCI]:
        out.append({"nome": _taglia(v.get("nome"), 160), "data": _taglia(v.get("data"), 40),
                    "importo": _taglia(v.get("importo"), 40), "di": _taglia(v.get("di"), 60),
                    "chiave": _taglia(v.get("chiave"), 80), "estensione": _taglia(v.get("estensione"), 8)})
    return nuova("archivio", titolo, PERSONALE, durata_s=None, chiave=chiave, voci=out,
                 nota=_taglia(nota, 300), vuoto=_taglia(vuoto, 200))


def ufficio(chiave: str, titolo: str, voci=(), nota: str = "", vuoto: str = "") -> dict:
    """Un gruppo della pagina Ufficio di Le mie cose (28/10, passo 2e, #260, schermi/raccolte.py),
    solo per chi amministra: i documenti di una serie (fatture, preventivi, DDT) o la rubrica. Una
    riga per voce con il nome, i dettagli (data, cliente, importo; o tipo, partita IVA, luogo,
    recapiti), lo stato (emesso, annullato col motivo; di casa o solo sua), `annullato` e i file da
    scaricare (`file`: chiave ed estensione, al più 3). Solo testo: nomi e recapiti dei clienti sono
    dati non fidati. Le sorgenti di «Scarica» stanno in `_scarica_voci` e restano sul server."""
    out = []
    for v in list(voci or ())[:_MAX_VOCI]:
        file = [{"chiave": _taglia(f.get("chiave"), 80), "estensione": _taglia(f.get("estensione"), 8)}
                for f in list(v.get("file") or ())[:3] if isinstance(f, dict) and f.get("chiave")]
        out.append({"nome": _taglia(v.get("nome"), 160),
                    "dettagli": [_taglia(d, 120) for d in list(v.get("dettagli") or ())[:6] if d],
                    "stato": _taglia(v.get("stato"), 200), "annullato": bool(v.get("annullato")), "file": file})
    return nuova("ufficio", titolo, PERSONALE, durata_s=None, chiave=chiave, voci=out,
                 nota=_taglia(nota, 300), vuoto=_taglia(vuoto, 200))


def testo(titolo: str, contenuto: str, visibilita: str) -> dict:
    return nuova("testo", titolo, visibilita, testo=_taglia(contenuto, _MAX_TESTO))


def risposta(domanda: str, contenuto: str, visibilita: str, chiave: str | None = None) -> dict:
    """La risposta a una frase scritta, con la domanda sopra (calliope/rispondi.py). Va solo
    allo schermo da cui è stata scritta (Schermi.invia_a), mai agli altri."""
    return nuova("risposta", "Risposta", visibilita, chiave=chiave, domanda=_taglia(domanda, 300),
                 testo=_taglia(contenuto, _MAX_TESTO))


def foto(img, didascalia: str = "") -> dict:
    """La miniatura (data URL JPEG, ~20 kB) di una foto della conversazione: solo agli schermi
    personali di chi parla. Resta solo nella cronologia in memoria degli schermi."""
    from ..immagini import FONTI, miniatura
    return nuova("foto", f"Foto {img.n}", PERSONALE, chiave=f"foto:{id(img)}",
                 src=miniatura(img.jpeg), fonte=FONTI.get(img.fonte, img.fonte),
                 lato=max(img.larghezza, img.altezza), didascalia=_taglia(didascalia, 200))


def allegato(att) -> dict:
    """Un file della conversazione: nome, tipo, dimensione, note e l'inizio del testo (solo
    testo: la pagina lo mette in textContent). Solo agli schermi personali di chi parla."""
    from ..allegati import _dimensione, nome_pulito
    testo = att.testo if att.parti else ""
    return nuova("allegato", f"File {att.n}", PERSONALE, chiave=f"allegato:{id(att)}",
                 nome=nome_pulito(att.nome), tipo_file=att.tipo(), categoria=att.categoria,
                 dimensione=_dimensione(att.dimensione), struttura=att.struttura,
                 note=[_taglia(n, 120) for n in att.note[:4]],
                 anteprima=_taglia(testo, 600))


def vuota() -> dict:
    """Torna all'orologio."""
    return nuova("vuota", "Orologio", PUBBLICA, durata_s=None)
