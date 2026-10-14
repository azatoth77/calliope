"""
La macchina a stati dei giochi fornita da Calliope (13/10/2026; progetto
docs/ricerche/2026-10-12-giochi-macchina-stati.md, decisioni di chi amministra del 12/10; area
docs/aree/giochi.md).

Un gioco nuovo è una **dichiarazione** (la sezione `scheda.macchina` del manifesto: fasi, comandi
per fase con al più uno slot, pagina, fasi verso cui si va) più una **logica pura** (`GIOCO` in
logica.js: partita nuova, mosse per fase e comando, quali comandi valgono adesso, cosa mostrare).
Il resto è del **motore** (calliope/estensioni/motore_gioco.js), che gira nel riquadro prima del
codice del gioco e, uguale, nella prova di fumo e nei test: le fasi standard (preparazione con il
numero dei giocatori, esito della mossa che va avanti da solo dopo qualche secondo, fine con la
classifica e «ancora»), i turni, i punti, il disegno, i pulsanti (ogni comando è anche un
pulsante) e i comandi a voce.

    "macchina": {
      "inizio": "turno",
      "fasi": {
        "turno": {"pagina": "scelte", "turni": true, "verso": ["esito"],
                  "comandi": {"porta": {"forme": ["porta {n}", "la porta {n}", "{n}"],
                                        "n": {"da": 1, "a": 6}, "etichetta": "Porta {n}"}}}
      },
      "esito_s": 4
    }

Qui la validazione (all'approvazione e alla consegna) e l'elenco **piatto** dei comandi a voce
che ne viene: lo slot è un'abbreviazione di un elenco («porta {n}» con n da 1 a 6 sono i
comandi `porta_1` … `porta_6`, ognuno con le sue forme intere), così il riconoscimento della voce
resta quello dell'11/10 (gioco_voce.trova, principio 10 alla lettera: un insieme finito di frasi
brevi riconosciute per intero) e il motore dice a runtime quali valgono adesso (dal 14/10
nell'istantanea della partita, sotto). Con la macchina il manifesto non ha `ascolta`: lo scrive
Calliope.

Dal 14/10 (passo 4, il palco fisso) ogni fase sceglie uno dei modelli di pagina di Calliope
(`PAGINE`: titolo, scelte, griglia, messaggio, punteggi, classifica, più la tela), disegnati dal
motore su un palco di 1280×720 o 720×1280; la prova di fumo misura che ogni pagina ci stia. Dal
14/10 è anche l'unico modo di scrivere un gioco (niente più `gioco.js` né `ascolta` piatto:
scheda.normalizza). `"giocatore": true` porta alla mossa il nome di chi è riconosciuto dalla
voce (`ctx.giocatore`), come l'`ascolta.giocatore` dell'11/10.

Dal 14/10 (passo 2 lato server) il motore manda dopo ogni disegno l'**istantanea** numerata
della partita (fase, a chi tocca, giocatori e punti, esito, comandi a voce attivi): qui
`valida_istantanea` la controlla contro la macchina approvata (`per_fase`: i comandi che ogni
fase può avere) e il server la tiene come stato della partita (schermi/giochi.py).
"""

from __future__ import annotations

import re

from .. import gioco_voce

# Le fasi di Calliope: il gioco non le dichiara (le può nominare in «verso»)
STANDARD = ("preparazione", "esito", "fine")
# I modelli di pagina del motore (motore_gioco.js, impagina): il disegno è di Calliope
PAGINE = ("titolo", "scelte", "griglia", "messaggio", "punteggi", "classifica", "tela")
MAX_FASI = 8
MAX_COMANDI_FASE = 8
MAX_VALORI = 24          # un elenco chiuso di valori
MAX_NUMERI = 60          # uno slot numerico (i numeri in parole di gioco_voce arrivano a 100)
MAX_SOLO_SLOT = 12       # «{n}» da solo: solo con un dominio piccolo
MAX_PIATTI = 64          # i comandi a voce in tutto (come MAX_ATTIVI di schermi/giochi.py)
ESITO_S = 4.0            # decisione 8 del 12/10: l'esito va avanti da solo dopo ~4 s
_NOME_FASE = re.compile(r"^[a-z][a-z0-9_]{0,15}$")
_NOME_COMANDO = re.compile(r"^[a-z][a-z0-9_]{0,13}$")
_ID_VALORE = re.compile(r"^[a-z0-9][a-z0-9_]{0,8}$")
SLOT = "{n}"

# I comandi standard: nome, forme (con {n} il numero dei giocatori), etichetta del pulsante.
# Le forme sono di Calliope: un gioco non le può dichiarare per un altro comando (doppioni)
COMANDI_STANDARD = {
    "giocatori": (["{n} giocatori", "siamo in {n}"], "{n} giocatori"),
    "inizia": (["inizia", "via", "cominciamo"], "Inizia"),
    "avanti": (["avanti", "continua"], "Avanti"),
    "ancora": (["ancora", "un'altra partita", "ricomincia", "rigioca"], "Ancora"),
    "fine_partita": (["fine partita"], "Fine partita"),
}
# I comandi standard della preparazione che vengono dopo (passo 4 del progetto, «gioco anch'io»):
# vuoto finché non ci sono
STANDARD_PREPARAZIONE: tuple[str, ...] = ()


class MacchinaNonValida(ValueError):
    pass


def _err(dove: str, cosa: str):
    raise MacchinaNonValida(f"«scheda.macchina{dove}»: {cosa}")


def _bool(v, predefinito: bool) -> bool:
    if v is None:
        return predefinito
    return v is True or (isinstance(v, str) and v.strip().lower() in ("true", "sì", "si", "1"))


def _dominio(dove: str, n) -> dict:
    """Lo slot {n}: {"da": 1, "a": 6} oppure {"valori": {"rosso": ["rosso"], …}}."""
    if not isinstance(n, dict):
        _err(dove, "{\"da\": 1, \"a\": 6} per un numero, {\"valori\": {\"rosso\": [\"rosso\"]}} "
                   "per una scelta")
    if "valori" in n:
        v = n["valori"]
        if isinstance(v, list):
            v = {str(x): [str(x)] for x in v}
        if not isinstance(v, dict) or not v or len(v) > MAX_VALORI:
            _err(dove, f"«valori»: da 1 a {MAX_VALORI}")
        out = {}
        for vid, sin in v.items():
            if not isinstance(vid, str) or not _ID_VALORE.match(vid):
                _err(dove, f"valore «{vid}» non valido (minuscole e cifre, al più 9)")
            if isinstance(sin, str):
                sin = [sin]
            if not isinstance(sin, list) or not sin or len(sin) > 3 or any(
                    not isinstance(s, str) or not s.strip() or len(s.split()) > 2 for s in sin):
                _err(dove, f"«valori.{vid}»: da 1 a 3 parole o coppie di parole")
            out[vid] = [s.strip() for s in sin]
        return {"valori": out}
    try:
        da, a = int(n.get("da")), int(n.get("a"))
    except (TypeError, ValueError):
        _err(dove, "{\"da\": 1, \"a\": 6}")
    if not (0 <= da <= a <= 100) or a - da + 1 > MAX_NUMERI:
        _err(dove, f"da 0 a 100, al più {MAX_NUMERI} numeri")
    return {"da": da, "a": a}


def valori(dom: dict | None) -> list:
    """I valori dello slot: numeri o id dell'elenco ([] senza slot)."""
    if not dom:
        return []
    if "valori" in dom:
        return list(dom["valori"])
    return list(range(dom["da"], dom["a"] + 1))


def piatto(nome: str, valore=None) -> str:
    """Il nome del comando a voce piatto: «porta» con 3 → «porta_3»."""
    return nome if valore is None else f"{nome}_{valore}"


def _comando(dove: str, nome, c) -> dict:
    if not isinstance(nome, str) or not _NOME_COMANDO.match(nome):
        _err(dove, f"nome del comando «{nome}» non valido (minuscole, cifre e _, al più 14)")
    if nome in COMANDI_STANDARD:
        _err(dove, f"«{nome}» è un comando di Calliope: scegli un altro nome")
    if isinstance(c, list):
        c = {"forme": c}
    if not isinstance(c, dict):
        _err(f"{dove}.{nome}", "{\"forme\": [\"porta {n}\"], \"n\": {\"da\": 1, \"a\": 6}}")
    altri = [k for k in c if k not in ("forme", "n", "etichetta")]
    if altri:
        _err(f"{dove}.{nome}", f"sconosciuto {', '.join(map(str, altri))} (solo forme, n, "
                               "etichetta)")
    forme = c.get("forme")
    if isinstance(forme, str):
        forme = [forme]
    if not isinstance(forme, list) or not forme or len(forme) > gioco_voce.MAX_FORME or any(
            not isinstance(f, str) or not f.strip() for f in forme):
        _err(f"{dove}.{nome}.forme", f"da 1 a {gioco_voce.MAX_FORME} frasi brevi")
    forme = [f.strip() for f in forme]
    dom = _dominio(f"{dove}.{nome}.n", c["n"]) if c.get("n") is not None else None
    for f in forme:
        k = f.count(SLOT)
        if dom is None and k:
            _err(f"{dove}.{nome}.forme", f"«{f}» ha {SLOT} ma il comando non ha «n»")
        if dom is not None and k != 1:
            _err(f"{dove}.{nome}.forme", f"«{f}»: con «n» ogni forma ha {SLOT} una volta")
        if dom is not None and f == SLOT and len(valori(dom)) > MAX_SOLO_SLOT:
            _err(f"{dove}.{nome}.forme", f"{SLOT} da solo solo con al più {MAX_SOLO_SLOT} "
                                         "valori")
    et = c.get("etichetta")
    if et is not None and (not isinstance(et, str) or not et.strip() or len(et) > 30):
        _err(f"{dove}.{nome}.etichetta", "un testo breve (al più 30 caratteri)")
    return {"forme": forme, **({"n": dom} if dom else {}),
            **({"etichetta": et.strip()} if et else {})}


def normalizza(m, giocatori: dict) -> dict:
    """La sezione «macchina» validata. Solleva MacchinaNonValida con un messaggio per chi scrive
    il manifesto."""
    if not isinstance(m, dict):
        _err("", "un oggetto {\"inizio\": \"turno\", \"fasi\": {…}}")
    altri = [k for k in m if k not in ("inizio", "fasi", "esito_s", "giocatore")]
    if altri:
        _err("", f"sconosciuto {', '.join(map(str, altri))} (solo inizio, fasi, esito_s, "
                 "giocatore)")
    fasi = m.get("fasi")
    if not isinstance(fasi, dict) or not fasi or len(fasi) > MAX_FASI:
        _err(".fasi", f"da 1 a {MAX_FASI} fasi del gioco (preparazione, esito e fine sono di "
                      "Calliope)")
    out_fasi = {}
    for nome, f in fasi.items():
        if not isinstance(nome, str) or not _NOME_FASE.match(nome):
            _err(".fasi", f"nome di fase «{nome}» non valido (minuscole, cifre e _)")
        if nome in STANDARD:
            _err(".fasi", f"«{nome}» è una fase di Calliope: non si dichiara (si nomina in "
                          "«verso»)")
        if not isinstance(f, dict):
            _err(f".fasi.{nome}", "un oggetto {\"pagina\", \"turni\", \"verso\", \"comandi\"}")
        altri = [k for k in f if k not in ("pagina", "turni", "verso", "comandi")]
        if altri:
            _err(f".fasi.{nome}", f"sconosciuto {', '.join(map(str, altri))} (solo pagina, "
                                  "turni, verso, comandi)")
        pagina = str(f.get("pagina") or "scelte").strip().lower()
        if pagina not in PAGINE:
            _err(f".fasi.{nome}.pagina", f"una tra {', '.join(PAGINE)}")
        verso = f.get("verso") or []
        if isinstance(verso, str):
            verso = [verso]
        if not isinstance(verso, list):
            _err(f".fasi.{nome}.verso", "un elenco di fasi")
        comandi = f.get("comandi") or {}
        if not isinstance(comandi, dict) or len(comandi) > MAX_COMANDI_FASE:
            _err(f".fasi.{nome}.comandi", f"al più {MAX_COMANDI_FASE} comandi")
        out_fasi[nome] = {"pagina": pagina, "turni": _bool(f.get("turni"), True),
                          "verso": [str(v) for v in verso],
                          "comandi": {k: _comando(f".fasi.{nome}.comandi", k, v)
                                      for k, v in comandi.items()}}
        if not out_fasi[nome]["comandi"] and pagina != "tela":
            _err(f".fasi.{nome}.comandi", "almeno un comando (una fase senza comandi non ha "
                                          "uscita; per un gioco libero c'è la pagina «tela»)")
    for nome, f in out_fasi.items():
        fuori = [v for v in f["verso"] if v not in out_fasi and v not in ("esito", "fine")]
        if fuori:
            _err(f".fasi.{nome}.verso", f"fasi che non ci sono: {', '.join(fuori)}")
    inizio = m.get("inizio") or next(iter(out_fasi))
    if inizio not in out_fasi:
        _err(".inizio", f"una delle fasi dichiarate ({', '.join(out_fasi)})")
    try:
        esito_s = float(m.get("esito_s", ESITO_S))
    except (TypeError, ValueError):
        _err(".esito_s", "secondi (0 = solo con «avanti»)")
    if not (0 <= esito_s <= 30):
        _err(".esito_s", "da 0 a 30 secondi (0 = solo con «avanti»)")
    out = {"inizio": inizio, "fasi": out_fasi, "esito_s": esito_s,
           **({"giocatore": True} if _bool(m.get("giocatore"), False) else {})}
    ascolta(out, giocatori)            # i doppioni e i tetti della voce, già qui
    return out


def _espandi(forme: list[str], dom: dict | None, valore) -> list[str]:
    if dom is None:
        return list(forme)
    sinonimi = dom["valori"][valore] if "valori" in dom else [str(valore)]
    out = []
    for f in forme:
        for s in sinonimi:
            e = f.replace(SLOT, s)
            if e not in out:
                out.append(e)
    return out[:gioco_voce.MAX_FORME]


def ascolta(m: dict, giocatori: dict) -> dict:
    """L'elenco piatto dei comandi a voce della macchina (la sezione «ascolta» che il gioco non
    scrive più): i comandi standard e quelli del gioco espansi sul dominio dichiarato,
    validati da gioco_voce (forme intere, riservate, doppioni)."""
    piatti: dict[str, list[str]] = {}
    gmin, gmax = int(giocatori.get("min", 1)), int(giocatori.get("max", 1))
    forme, _ = COMANDI_STANDARD["giocatori"]
    for n in range(gmin, gmax + 1) if gmin < gmax else ():
        piatti[piatto("giocatori", n)] = (["un giocatore", "gioco da solo"] if n == 1
                                          else [f.replace(SLOT, str(n)) for f in forme])
    for nome in ("inizia", "avanti", "ancora"):
        piatti[nome] = list(COMANDI_STANDARD[nome][0])
    if any(f["pagina"] == "tela" for f in m["fasi"].values()):
        piatti["fine_partita"] = list(COMANDI_STANDARD["fine_partita"][0])
    for fnome, f in m["fasi"].items():
        for cnome, c in f["comandi"].items():
            dom = c.get("n")
            for v in (valori(dom) or [None]):
                chiave = piatto(cnome, v)
                if chiave in piatti:
                    # Lo stesso comando in due fasi: un comando solo, attivo dove serve
                    if piatti[chiave] != _espandi(c["forme"], dom, v):
                        _err(f".fasi.{fnome}.comandi.{cnome}", "lo stesso comando in un'altra "
                             "fase ha forme diverse: usa le stesse o un altro nome")
                    continue
                piatti[chiave] = _espandi(c["forme"], dom, v)
    if len(piatti) > MAX_PIATTI:
        _err("", f"troppi comandi a voce: {len(piatti)} con i valori degli slot (al più "
                 f"{MAX_PIATTI}); restringi i domini")
    # Le domande standard di Calliope («a chi tocca?», «quanti punti ho?»: gioco_stato.py) valgono
    # in ogni fase: un comando del gioco non le può coprire
    from .. import gioco_stato
    domande = gioco_stato.forme_normalizzate()
    for cid, forme in piatti.items():
        for f in forme:
            if gioco_voce.normalizza(f) in domande:
                _err("", f"«{f}» è una domanda di Calliope sul gioco (a chi tocca, i punti, chi "
                         "vince, cosa si può dire): scegli un'altra forma")
    try:
        comandi = gioco_voce.valida_elenco(piatti, massimo=MAX_PIATTI)
    except gioco_voce.ElencoNonValido as e:
        _err("", f"i comandi a voce che ne vengono: {e}")
    return {"comandi": comandi, "giocatore": bool(m.get("giocatore"))}


def per_fase(m: dict, giocatori: dict) -> dict[str, list[str]]:
    """I comandi a voce piatti che possono valere in ogni fase (le standard comprese): il server
    ci controlla l'istantanea del motore (passo 2 del progetto, 14/10), che può solo
    restringerli. {fase: [piatti]}."""
    gmin, gmax = int(giocatori.get("min", 1)), int(giocatori.get("max", 1))
    prep = [piatto("giocatori", n) for n in range(gmin, gmax + 1)] if gmin < gmax else []
    out = {"preparazione": prep + ["inizia"] + list(STANDARD_PREPARAZIONE),
           "esito": ["avanti"], "fine": ["ancora"]}
    for fnome, f in (m.get("fasi") or {}).items():
        lista = []
        for cnome, c in f["comandi"].items():
            for v in (valori(c.get("n")) or [None]):
                lista.append(piatto(cnome, v))
        if f["pagina"] == "tela":
            lista.append("fine_partita")
        out[fnome] = lista
    return out


def da_piatto(m: dict, nome: str):
    """Il comando a voce piatto → (comando, valore, fase del gioco o None). «porta_3» →
    ("porta", 3, "turno"); None se non è della macchina."""
    nome = str(nome or "")
    if nome in ("inizia", "avanti", "ancora", "fine_partita") or nome in STANDARD_PREPARAZIONE:
        return (nome, None, None)
    if nome.startswith("giocatori_") and nome[10:].isdigit():
        return ("giocatori", int(nome[10:]), None)
    for fnome, f in (m.get("fasi") or {}).items():
        for cnome, c in f["comandi"].items():
            for v in (valori(c.get("n")) or [None]):
                if piatto(cnome, v) == nome:
                    return (cnome, v, fnome)
    return None


# ─────────────── l'istantanea della partita, validata dal server (passo 2, 14/10) ───────────────
# Il motore nel riquadro è l'unico che scrive lo stato; dopo ogni mossa (e all'avvio, e dopo
# «Riapri») manda a Calliope l'istantanea numerata. Il server la valida contro il manifesto
# approvato e la tiene come stato della partita: i comandi a voce attivi, a chi tocca, i punti
# (domande standard), il numero che accompagna ogni comando a voce (un comando su
# un'istantanea vecchia il motore lo rifiuta). Una non valida si scarta e il gioco resta senza
# comandi a voce finché non ne manda una buona (regola gioco_stato_non_valido)
MAX_ESITO = 160
MAX_PUNTI = 1_000_000_000
NOME_DEFAULT = re.compile(r"^Giocatore [1-9]$")
# Il nome scritto (o detto) di chi gioca, nella forma chiusa del § 2.2 del progetto: lettere,
# spazi e apostrofo, al più 20 caratteri, al più due parole
NOME_CHIUSO = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ']+( [A-Za-zÀ-ÖØ-öø-ÿ']+)?$")
CHIAVI_ISTANTANEA = {"n", "fase", "tocca", "turno", "giocatori", "esito", "comandi"}


class IstantaneaNonValida(ValueError):
    pass


def nome_chiuso(nome) -> bool:
    """Il nome è nella forma chiusa (lettere, spazi, apostrofo; al più 20 caratteri e due
    parole) o è quello di Calliope («Giocatore 3»)."""
    return isinstance(nome, str) and len(nome) <= 20 and bool(
        NOME_CHIUSO.match(nome) or NOME_DEFAULT.match(nome))


def valida_istantanea(ist, m: dict, giocatori: dict, ultimo_n: int = -1) -> dict:
    """L'istantanea mandata dal motore, controllata contro la macchina approvata: `n` che non
    cala, fase dichiarata (o standard), comandi tra quelli che la fase può avere, giocatori al
    più `max`, nomi nella forma chiusa (un nome fuori forma resta sullo schermo e qui diventa
    «Giocatore N»), punti numeri limitati, `tocca` dentro i giocatori, esito al più 160
    caratteri. Restituisce la copia pulita; solleva IstantaneaNonValida."""
    def no(cosa):
        raise IstantaneaNonValida(cosa)
    if not isinstance(ist, dict):
        no("non è un oggetto")
    altri = set(ist) - CHIAVI_ISTANTANEA
    if altri:
        no(f"campi sconosciuti: {', '.join(sorted(map(str, altri)))[:80]}")
    n = ist.get("n")
    if not isinstance(n, int) or isinstance(n, bool) or not (0 <= n <= 10_000_000):
        no("«n» non è un numero della partita")
    if n < ultimo_n:
        no(f"«n» cala ({n} dopo {ultimo_n})")
    fase = ist.get("fase")
    fasi = per_fase(m, giocatori)
    if not isinstance(fase, str) or fase not in fasi:
        no(f"fase «{str(fase)[:24]}» non dichiarata")
    comandi = ist.get("comandi")
    if not isinstance(comandi, list) or len(comandi) > MAX_PIATTI or any(
            not isinstance(c, str) for c in comandi):
        no("«comandi»: un elenco di nomi")
    fuori = [c for c in comandi if c not in fasi[fase]]
    if fuori:
        no(f"comandi che la fase «{fase}» non ha: {', '.join(x[:24] for x in fuori[:5])}")
    gs = ist.get("giocatori")
    gmax = int(giocatori.get("max", 1))
    if not isinstance(gs, list) or len(gs) > gmax:
        no(f"«giocatori»: un elenco di al più {gmax}")
    puliti = []
    for i, g in enumerate(gs):
        if not isinstance(g, dict) or set(g) - {"nome", "punti"}:
            no("un giocatore è {nome, punti}")
        p = g.get("punti", 0)
        if isinstance(p, bool) or not isinstance(p, (int, float)) or p != p \
                or abs(p) > MAX_PUNTI:
            no("punti non validi")
        nome = g.get("nome")
        chiuso = nome_chiuso(nome)
        puliti.append({"nome": nome if chiuso else f"Giocatore {i + 1}",
                       "punti": int(p) if float(p).is_integer() else round(float(p), 2),
                       **({} if chiuso else {"fuori_forma": True})})
    tocca = ist.get("tocca")
    if tocca is not None and (not isinstance(tocca, int) or isinstance(tocca, bool)
                              or not (0 <= tocca < max(1, len(puliti)))):
        no("«tocca» fuori dai giocatori")
    if tocca is not None and not puliti:
        tocca = None
    turno = ist.get("turno", 0)
    if not isinstance(turno, int) or isinstance(turno, bool) or not (0 <= turno <= 1_000_000):
        no("«turno» non valido")
    esito = ist.get("esito")
    if esito is not None and (not isinstance(esito, str) or len(esito) > MAX_ESITO):
        no(f"«esito»: un testo di al più {MAX_ESITO} caratteri")
    return {"n": n, "fase": fase, "tocca": tocca, "turno": turno, "giocatori": puliti,
            "esito": esito, "comandi": list(dict.fromkeys(comandi))}


def in_parole(m: dict) -> str:
    """Per chi approva: «si gioca a voce o toccando, con 2 fasi e 3 comandi»."""
    fasi = m.get("fasi") or {}
    n = sum(len(f["comandi"]) for f in fasi.values())
    tela = any(f["pagina"] == "tela" for f in fasi.values())
    return ("si gioca a voce o toccando, con " + ("una fase" if len(fasi) == 1
                                                 else f"{len(fasi)} fasi")
            + " e " + ("un comando" if n == 1 else f"{n} comandi")
            + (", con una parte in tempo reale" if tela else "")
            + (" e il nome di chi gioca" if m.get("giocatore") else ""))
