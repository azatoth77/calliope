"""
La mappa concettuale dello Studio, la parte pura (30/10, passo 7, issue #247, epic #251, decisione
0035 punto 35; progetto del 27/10, § 5.4 e Studio 10–11). Niente db e niente modello: la forma dei
testi, la disposizione, le caselle vuote, le parole da mettere e **il controllo**, deterministico.

**Quattro fasi.** (1) Lo **scheletro**: concetti e collegamenti col verbo, ogni concetto con le
pagine; lo propone il lettore (passo 7, seconda parte) o lo scrive a mano la persona o il tutore, e
resta «proposto» finché non lo conferma. (2) **La mia mappa** («con il libro»): la copia dello
scheletro confermato con alcune caselle vuote, che dicono la pagina dove cercare, le parole da
mettere più una di troppo; la persona aggiunge concetti e collegamenti suoi. (3) **A memoria**: la
stessa copia senza pagine. (4) Il **PDF** della mia mappa (`mappa_pdf.py`), mai dello scheletro.

**Il testo è un dato** chiunque l'abbia scritto: sullo schermo solo textContent o testo SVG; **mai
fuori busta**. Nessun tool legge la mappa (`studio` azione `mappa` dà solo conti); il testo di un
concetto arriva al modello solo se la persona ne fa una carta («Fanne carte»), e allora come carta, in
busta (`studio_carte`, fonte «foto», fuori dalla storia a risposta finita). Mai nelle frasi pronte,
nel registro o negli eventi.

**Il controllo** (`controlla`) confronta la mappa della persona con lo scheletro confermato, mai col
giudizio del modello: per ogni casella la parola messa contro il concetto dello scheletro (`uguale`);
i collegamenti dello scheletro che la persona ha tolto sono **mancanti** (con le pagine dove
guardare, senza dire con quale concetto), quelli nuovi fra due concetti dello scheletro che lo
scheletro non ha sono **in più** (da controllare sul libro, non un errore), un verbo cambiato è
«verbo diverso», una freccia rovesciata «verso diverso» (da rivedere: il verso conta); i
collegamenti con i concetti propri della persona non si giudicano.

Un concetto: {id, testo, pagine (id), argomento (id o None), autore («persona», «tutore»,
«modello», «scheletro» per la copia), stato («tenuto», «proposto»: solo nello scheletro), avvisi,
x, y (frazioni della mappa), da (il concetto dello scheletro da cui viene la copia), casella (vuota
da riempire: il testo è ciò che ha messo la persona)}. Un collegamento: {id, da, a, verbo, pagine,
autore, stato, avvisi, origine (il collegamento dello scheletro da cui viene la copia)}.
"""

from __future__ import annotations

import math
import re
import unicodedata

NODO_MAX = 60
VERBO_MAX = 40
# Lo scheletro si conferma con almeno tanti concetti tenuti (meno non fa una mappa con le caselle)
MIN_CONFERMA = 3
# L'aiuto: quante caselle vuote (progetto, Studio 11: «Tanto / Medio / Poco», 2, 3 o 6)
AIUTI = {"tanto": 2, "medio": 3, "poco": 6}
AIUTO_DI_SERIE = "medio"
# I tipi di mappa e i loro stati
SCHELETRO, STUDENTE, MEMORIA = "scheletro", "studente", "memoria"
TIPI = (SCHELETRO, STUDENTE, MEMORIA)
STATI_SCHELETRO = ("proposta", "confermata", "ombra")
STATI_STUDENTE = ("aperta", "controllata")
# Gli esiti di una casella
GIUSTA, SBAGLIATA, VUOTA = "giusta", "sbagliata", "vuota"
# Nella copia (la mia mappa, a memoria) la persona aggiunge al più tanti concetti suoi, oltre a
# quelli dello scheletro (`studio_mappa_nodi_max` vale per lo scheletro)
SUOI_MAX = 6
# Le parole vuote che una casella può avere in più o in meno (articoli, preposizioni, «e»)
VUOTE = frozenset("""il lo la i gli le l un uno una un di a da in con su per tra fra del dello della
dei degli delle al allo alla ai agli alle dal dallo dalla dai dagli dalle nel nello nella nei negli
nelle sul sullo sulla sui sugli sulle col coi e ed d""".split())
# La tolleranza di una lettera vale solo per le parole lunghe (fino a 6 lettere una lettera cambia la
# parola: forma/forza, messa/massa, Marte/Morte)
STORPIATA_DA = 7

_CONTROLLO = re.compile(r"[\x00-\x1f\x7f  -‏ - ⁦-⁩]")


def nodi_max(cfg) -> int:
    try:
        n = int(getattr(cfg, "studio_mappa_nodi_max", 12) or 12)
    except (TypeError, ValueError):
        n = 12
    return max(4, min(30, n))


def testo_normale(testo, massimo: int = NODO_MAX, vuoto: bool = False) -> str:
    """Il testo di un concetto o di un verbo: una riga, senza caratteri di controllo né di
    direzione, al più `massimo` caratteri. Vuoto → ValueError (o "" con `vuoto`)."""
    t = unicodedata.normalize("NFC", str(testo if testo is not None else ""))
    t = " ".join(_CONTROLLO.sub(" ", t).split())[:massimo].strip()
    if not t and not vuoto:
        raise ValueError("manca il testo")
    return t


def chiave(testo) -> str:
    """Per confrontare due testi: senza maiuscole, accenti e punteggiatura."""
    t = unicodedata.normalize("NFKD", str(testo or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return " ".join(re.findall(r"[a-z0-9]+", t))


def _piene(t: str) -> list[str]:
    return [w for w in chiave(t).split() if w not in VUOTE]


def _storpiata(a: str, d: str) -> bool:
    """Una lettera di differenza (cambiata, in più o in meno), solo fra parole di lettere di almeno
    `STORPIATA_DA` lettere e mai sulla prima."""
    from ..provenienza import _distanza
    if a == d:
        return True
    if (min(len(a), len(d)) < STORPIATA_DA or not a.isalpha() or not d.isalpha()
            or a[0] != d[0]):
        return False
    return _distanza(a, d, 1) <= 1


def uguale(atteso, dato, altri=()) -> bool:
    """La parola messa in una casella vale il concetto dello scheletro. Forma, non significato (un
    sinonimo non vale: il controllo lo dice e la persona guarda la pagina):
    - uguale senza maiuscole, accenti e punteggiatura: giusta;
    - uguale a un **altro** concetto dello scheletro o alla parola di troppo (`altri`): sbagliata;
    - altrimenti le stesse parole piene (senza articoli e preposizioni, che possono mancare o essere
      in più), nessuna in più né in meno, ognuna uguale o storpiata di una lettera solo se lunga
      almeno `STORPIATA_DA` lettere e mai sulla prima."""
    a, d = chiave(atteso), chiave(dato)
    if not d:
        return False
    if a == d:
        return True
    if d in {chiave(x) for x in altri or ()} - {a}:
        return False
    pa, pd = _piene(atteso), _piene(dato)
    if not pa or len(pa) != len(pd):
        return False
    resto = list(pd)
    for w in pa:
        k = next((i for i, x in enumerate(resto) if _storpiata(w, x)), None)
        if k is None:
            return False
        resto.pop(k)
    return True


def verbo_simile(a, b) -> bool:
    """Due verbi di un collegamento si somigliano: uguali, o metà delle parole significative in
    comune (uguali o storpiate). Senza parole significative («è», «di») solo uguali."""
    from ..provenienza import parole, vicina
    if chiave(a) == chiave(b):
        return True
    pa, pb = parole(a), parole(b)
    if not pa or not pb:
        return False
    comuni = [w for w in pa if w in pb or vicina(w, pb)]
    return len(comuni) * 2 >= max(len(pa), len(pb))


# ─────────────────────────── la disposizione ───────────────────────────

def disposizione(nodi: list[dict], collegamenti: list[dict]) -> dict[int, tuple[float, float]]:
    """id → (x, y) in frazioni della mappa (0,08–0,92): al centro il concetto con più collegamenti
    (a parità il primo), attorno quelli collegati a lui, poi gli altri su un giro più largo, in
    ordine di vicinanza (una visita in ampiezza). Deterministica: la stessa mappa ha sempre la
    stessa disposizione."""
    ids = [int(n["id"]) for n in nodi]
    if not ids:
        return {}
    vicini: dict[int, list[int]] = {i: [] for i in ids}
    for c in collegamenti:
        a, b = int(c["da"]), int(c["a"])
        if a in vicini and b in vicini and a != b:
            vicini[a].append(b)
            vicini[b].append(a)
    centro = max(ids, key=lambda i: (len(vicini[i]), -ids.index(i)))
    livelli: dict[int, int] = {centro: 0}
    coda = [centro]
    while coda:
        x = coda.pop(0)
        for y in vicini[x]:
            if y not in livelli:
                livelli[y] = livelli[x] + 1
                coda.append(y)
    for i in ids:
        livelli.setdefault(i, max(livelli.values()) + 1 if len(livelli) > 1 else 1)
    out = {centro: (0.5, 0.5)}
    giri: dict[int, list[int]] = {}
    for i in ids:
        if i != centro:
            giri.setdefault(livelli[i], []).append(i)
    n_giri = max(giri) if giri else 1
    for k, membri in sorted(giri.items()):
        # Il primo giro a 0,28 dal centro, gli altri più larghi fino a 0,44: i riquadri sono larghi
        # (un terzo della mappa sul telefono) e un giro stretto li sovrappone
        r = 0.28 + (0.16 * (k - 1) / (n_giri - 1) if n_giri > 1 else 0.0)
        for j, i in enumerate(membri):
            ang = 2 * math.pi * j / len(membri) - math.pi / 2 + (0.35 * (k - 1))
            x = 0.5 + r * math.cos(ang) * 1.15
            y = 0.5 + r * math.sin(ang) * 1.05
            out[i] = (min(0.92, max(0.08, x)), min(0.92, max(0.08, y)))
    return {i: (round(x, 3), round(y, 3)) for i, (x, y) in _separa(out, ids).items()}


# I riquadri, in frazioni della mappa: sul telefono un concetto è largo un terzo della mappa e alto
# un decimo (sul PC, in orizzontale, un sesto); due riquadri più vicini di così si sovrappongono
_LARGO, _ALTO = 0.34, 0.17


def _separa(pos: dict, ordine: list[int], giri: int = 80) -> dict:
    """Allontana i riquadri che si sovrappongono, lungo l'asse dove si sovrappongono meno, sempre
    dentro la mappa; il centro non si muove. Deterministica (l'ordine degli id)."""
    p = {i: list(pos[i]) for i in ordine}
    fermo = ordine[0] if ordine else None
    for i in ordine:
        if pos[i] == (0.5, 0.5):
            fermo = i
    for _ in range(giri):
        mosso = False
        for ia, a in enumerate(ordine):
            for b in ordine[ia + 1:]:
                dx, dy = p[b][0] - p[a][0], p[b][1] - p[a][1]
                ox, oy = _LARGO - abs(dx), _ALTO - abs(dy)
                if ox <= 0 or oy <= 0:
                    continue
                mosso = True
                asse, quanto, segno = ((0, ox, 1 if dx >= 0 else -1) if ox / _LARGO < oy / _ALTO
                                       else (1, oy, 1 if dy >= 0 else -1))
                passo = quanto / 2 + 0.005
                for k, verso in ((a, -segno), (b, segno)):
                    if k == fermo:
                        continue
                    p[k][asse] = min(0.92, max(0.08, p[k][asse] + verso * passo
                                               * (2 if fermo in (a, b) else 1)))
        if not mosso:
            break
    return {i: (x, y) for i, (x, y) in p.items()}


def libero(nodi: list[dict]) -> tuple[float, float]:
    """Un posto per un concetto nuovo: la casella della griglia 5×5 più lontana dagli altri."""
    pos = [(float(n.get("x") or 0.5), float(n.get("y") or 0.5)) for n in nodi]
    migliore, dist = (0.5, 0.5), -1.0
    for gy in range(5):
        for gx in range(5):
            x, y = 0.1 + gx * 0.2, 0.1 + gy * 0.2
            d = min(((x - a) ** 2 + (y - b) ** 2 for a, b in pos), default=1.0)
            if d > dist + 1e-9:
                migliore, dist = (round(x, 3), round(y, 3)), d
    return migliore


# ─────────────────────────── le caselle e le parole ───────────────────────────

def tenuti(scheletro: dict) -> tuple[list[dict], list[dict]]:
    """I concetti e i collegamenti tenuti di uno scheletro (i proposti con un avviso no; un
    collegamento solo se i suoi due concetti sono tenuti)."""
    nodi = [n for n in scheletro.get("nodi") or () if n.get("stato", "tenuto") == "tenuto"]
    ids = {int(n["id"]) for n in nodi}
    coll = [c for c in scheletro.get("collegamenti") or ()
            if c.get("stato", "tenuto") == "tenuto" and int(c["da"]) in ids
            and int(c["a"]) in ids]
    return nodi, coll


def scegli_caselle(nodi: list[dict], quante: int, deboli: list[int] | None = None,
                   giro: int = 0, collegamenti: list[dict] | None = None) -> list[int]:
    """Gli id dei concetti da lasciare vuoti: al più `quante` e mai tutti (almeno due restano per
    orientarsi). Prima quelli degli argomenti più deboli (`deboli`, dal più debole: solo con la
    padronanza mostrata), poi a giro sugli altri (`giro`, il numero del tentativo, così «Rifai»
    cambia le caselle), mai a caso. Il concetto con più collegamenti (il centro) resta visibile
    finché ce ne sono altri da scegliere."""
    ids = [int(n["id"]) for n in nodi]
    quante = max(0, min(int(quante), len(ids) - 2))
    if not quante:
        return []
    per_arg: dict = {}
    for n in nodi:
        per_arg.setdefault(n.get("argomento"), []).append(int(n["id"]))
    grado = {i: 0 for i in ids}
    for c in collegamenti or ():
        for k in (int(c["da"]), int(c["a"])):
            if k in grado:
                grado[k] += 1
    centro = max(ids, key=lambda i: (grado[i], -ids.index(i))) if any(grado.values()) else None
    scelti: list[int] = []
    for a in deboli or ():
        for i in per_arg.get(a, ()):
            if i not in scelti and i != centro and len(scelti) < quante:
                scelti.append(i)
    resto = [i for i in ids if i not in scelti and i != centro]
    if resto:
        k = (int(giro) * max(1, quante)) % len(resto)
        resto = resto[k:] + resto[:k]
        # Sparse: una ogni tanto, così le caselle non sono tutte vicine
        passo = max(1, -(-len(resto) // max(1, quante - len(scelti))))
        for i in resto[::passo] + resto:
            if len(scelti) >= quante:
                break
            if i not in scelti:
                scelti.append(i)
    if len(scelti) < quante and centro is not None:
        scelti.append(centro)
    return scelti


def parole_da_mettere(attese: list[str], altre: list[str]) -> list[str]:
    """Le parole delle caselle più una di troppo (la prima di `altre` che non è già fra quelle),
    in ordine alfabetico: l'ordine non dice dove va quale."""
    viste = {chiave(x) for x in attese}
    out = list(dict.fromkeys(x for x in attese if x))
    for x in altre:
        if x and chiave(x) not in viste:
            out.append(x)
            break
    return sorted(out, key=chiave)


def copia(scheletro: dict, caselle: list[int], con_pagine: bool) -> tuple[list[dict], list[dict]]:
    """La copia dello scheletro confermato per la persona: i concetti tenuti (le caselle vuote,
    `casella`, col testo vuoto e, con il libro, le pagine dove cercare) e i collegamenti tenuti.
    Il testo atteso delle caselle **non** è nella copia: lo tiene lo scheletro. La pagina lo
    riceverebbe con lo scheletro e con la mia mappa: per questo, mentre una mappa a memoria è
    aperta, `mappe.vista_mappe` manda a chi la fa lo scheletro e la mia mappa **senza i testi**, e la
    pagina nasconde le loro schede fino a «Controlla»."""
    nodi, coll = tenuti(scheletro)
    vuote = set(int(x) for x in caselle)
    out_n = []
    for n in nodi:
        c = int(n["id"]) in vuote
        out_n.append({"id": int(n["id"]), "testo": "" if c else n["testo"],
                      "pagine": list(n.get("pagine") or ()) if con_pagine else [],
                      "argomento": n.get("argomento"), "autore": SCHELETRO, "avvisi": [],
                      "x": n.get("x"), "y": n.get("y"), "da": int(n["id"]), "casella": c})
    out_c = [{"id": int(c["id"]), "da": int(c["da"]), "a": int(c["a"]), "verbo": c["verbo"],
              "pagine": list(c.get("pagine") or ()) if con_pagine else [],
              "autore": SCHELETRO, "avvisi": [], "origine": int(c["id"])} for c in coll]
    return out_n, out_c


# ─────────────────────────── il controllo ───────────────────────────

def _coppia(a, b) -> frozenset:
    return frozenset((int(a), int(b)))


def controlla(scheletro: dict, mappa: dict) -> dict:
    """Il confronto deterministico della mappa della persona con lo scheletro confermato.
    {caselle: {id del concetto: giusta|sbagliata|vuota}, mancanti: [{nodo, pagine}], in_piu:
    [{collegamento, pagine}], verbo_diverso: [id], tuoi: n, conti: {…}}. I concetti si legano allo
    scheletro con `da`; quelli senza (propri della persona) e i loro collegamenti non si giudicano."""
    s_nodi, s_coll = tenuti(scheletro)
    s_per_id = {int(n["id"]): n for n in s_nodi}
    # Le parole che non valgono una casella anche se scritte bene: gli altri concetti e le parole da
    # mettere (la parola di troppo compresa)
    tutte = [n["testo"] for n in s_nodi] + list((mappa.get("aiuto") or {}).get("parole") or ())
    nodi = list(mappa.get("nodi") or ())
    # il concetto dello scheletro → il concetto della persona
    mio = {int(n["da"]): int(n["id"]) for n in nodi
           if n.get("da") is not None and int(n["da"]) in s_per_id}
    da_di = {int(n["id"]): int(n["da"]) for n in nodi
             if n.get("da") is not None and int(n["da"]) in s_per_id}
    caselle = {}
    for n in nodi:
        if not n.get("casella") or int(n.get("da") or -1) not in s_per_id:
            continue
        atteso = s_per_id[int(n["da"])]["testo"]
        t = str(n.get("testo") or "").strip()
        caselle[int(n["id"])] = (VUOTA if not t else GIUSTA if uguale(atteso, t, tutte)
                                 else SBAGLIATA)
    s_coppie = {_coppia(c["da"], c["a"]): c for c in s_coll}
    mie_coppie = {}
    tuoi = 0
    in_piu, verbo_diverso, verso_diverso = [], [], []
    for c in mappa.get("collegamenti") or ():
        a, b = int(c["da"]), int(c["a"])
        if a not in da_di or b not in da_di:
            tuoi += 1
            continue
        k = _coppia(da_di[a], da_di[b])
        mie_coppie[k] = c
        sc = s_coppie.get(k)
        if sc is None:
            # Non è nel quadro: da controllare sul libro (le pagine dei due concetti)
            pag = list(dict.fromkeys(list(s_per_id[da_di[a]].get("pagine") or ())
                                     + list(s_per_id[da_di[b]].get("pagine") or ())))
            in_piu.append({"collegamento": int(c["id"]), "pagine": pag})
        elif (int(sc["da"]), int(sc["a"])) != (da_di[a], da_di[b]):
            # La freccia rovesciata: il verso conta («Colombo scopre l'America», non il contrario)
            verso_diverso.append(int(c["id"]))
        elif not verbo_simile(sc.get("verbo"), c.get("verbo")):
            verbo_diverso.append(int(c["id"]))
    mancanti = []
    for k, sc in s_coppie.items():
        if k in mie_coppie:
            continue
        a, b = int(sc["da"]), int(sc["a"])
        if a not in mio and b not in mio:
            continue
        # L'indizio dice un capo solo (quello che la persona ha) e le pagine, mai l'altro capo
        nodo = mio.get(a, mio.get(b))
        pag = list(sc.get("pagine") or ()) or list(s_per_id[a].get("pagine") or ())
        mancanti.append({"nodo": nodo, "pagine": pag})
    conti = {"caselle": len(caselle), GIUSTA: sum(v == GIUSTA for v in caselle.values()),
             SBAGLIATA: sum(v == SBAGLIATA for v in caselle.values()),
             VUOTA: sum(v == VUOTA for v in caselle.values()),
             "mancanti": len(mancanti), "in_piu": len(in_piu),
             "verbo_diverso": len(verbo_diverso), "verso_diverso": len(verso_diverso),
             "tuoi": tuoi}
    return {"caselle": caselle, "mancanti": mancanti, "in_piu": in_piu,
            "verbo_diverso": verbo_diverso, "verso_diverso": verso_diverso, "tuoi": tuoi,
            "conti": conti}


def esito_tentativo(esito_casella: str, tipo: str) -> str | None:
    """L'esito del tentativo «mappa» di una casella: con il libro una casella giusta vale
    «indizio» (le pagine erano aperte), a memoria «giusto»; sbagliata «sbagliato»; vuota niente
    (la persona può non aver finito)."""
    if esito_casella == GIUSTA:
        return "giusto" if tipo == MEMORIA else "indizio"
    if esito_casella == SBAGLIATA:
        return "sbagliato"
    return None
