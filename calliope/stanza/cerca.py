"""
La ricerca nella conversazione della stanza (14/10, conversazione di stanza, **passo 4**:
progetto docs/ricerche/2026-10-13-conversazione-di-stanza.md § 3.5 ter, § 3.7, § 3.8, § 6 riga
4; decisione 0029 punti 5 e 6). Il tool è `stanza_cerca` (tools/stanza.py); qui la parte che
non dipende dal modello: chi può vedere quali righe, i filtri, il punteggio, il tetto, l'attesa
delle righe ancora in coda e la frase d'attesa.

Serve per ciò che il blocco caldo dei dati del turno (stanza/contesto.py) non ha più: le righe
uscite dagli ultimi `stanza_caldo_min` minuti, o dette in un'altra stanza («di cosa parlavamo
in cucina prima?», «cosa aveva detto Carlo della gita stamattina?»). Cerca nel registro della
stanza **in memoria** (la tenuta del passo 1: al più 24 h, fino al riavvio).

**Chi vede cosa** (decisione 0029; § 3.5 ter, § 3.7, § 3.8):

- solo una persona di casa riconosciuta (la voce, o il suo schermo personale): un ospite e la
  zona grigia no;
- un **adulto** vede le righe delle stanze **dove era presente**, nei tempi in cui c'era
  (`Stanza.presenze`: la voce riconosciuta sopra soglia; un minuto prima della prima frase,
  fino a `stanza_presenza_s` dopo l'ultima o fino a quando la sua voce si è sentita in un'altra
  stanza), più gli ultimi `stanza_caldo_min` minuti della stanza da cui parla (sono quelli del
  blocco caldo, che sente anche lui); mai le righe di un minore, salvo i **tutori** di quel
  minore, che le vedono tutte (risposta 2 di chi amministra: dentro la famiglia i minori non
  hanno privacy verso i genitori);
- un **minore** vede soltanto le proprie righe riconosciute dalla voce;
- le righe di una **voce non riconosciuta** non si cercano mai (decisione 0029 punto 5: «ospiti
  mai nella ricerca»; restano solo nel blocco caldo);
- nella stanza da cui si parla in **pausa per ospiti** non si cerca (si leggerebbe ad alta voce
  davanti a loro); la pausa non registra niente, quindi ciò che si è detto durante non c'è.

**Attesa**: se nelle stanze cercate ci sono righe ancora in coda per Whisper, passano davanti
(`recupero`) e si aspettano al più `stanza_cerca_attesa_max_s`; la frase d'attesa
(`attesa.stanza` in frasi.py, atto `attesa_stanza`) parte solo se l'attesa supera
`stanza_cerca_attesa_s`. Una ricerca senza righe in coda non dice niente: dura millisecondi.

Misure (stanza/misure.py, mai parole né nomi): esito, ms, se c'è stata la frase d'attesa, righe
e caratteri dati, quante stanze, quali filtri.
"""

from __future__ import annotations

import datetime
import re
import time
import unicodedata
from dataclasses import dataclass, field

from .contesto import etichetta

# Prima della prima frase sentita di una persona in una stanza: vi era già (entrata in silenzio)
MARGINE_PRIMA_S = 60.0
# Una riga trovata porta con sé le vicine della stessa stanza entro questi secondi (il senso)
VICINE_S = 90.0
PERIODI = ("ultima_ora", "mattina", "pomeriggio", "sera", "notte", "oggi", "ieri")
_FASCE = {"mattina": (6, 12), "pomeriggio": (12, 18), "sera": (18, 24), "notte": (0, 6),
          "oggi": (0, 24)}
# Parole che dicono la domanda, non l'argomento («cosa aveva detto Carlo della gita»)
_VUOTE = frozenset("""
a ad al alla alle allo agli ai anche avete aveva avevamo avevano avevi abbiamo ha hanno ho
che chi cio come con cosa cose da dal dalla dalle dei del della delle dello degli di dice
diceva dicevamo dicevano dicevate detto detta dette detti dire e ed era erano eravamo gli
ieri il in io la le lei li lo lui ma mi ne nel nella nelle noi non o oggi per perche piu
poi prima qua quale quando quel quella quelle quello questa queste questo qui se sera si
sono sta stamattina stasera stavamo stavano su sua sue sui suo tra tu tua tue tuo un una
uno voi parlato parlavamo parlavano parlavate parlare discorso discorsi conversazione detto
ditto calliope stanza cucina sala salotto camera adesso ora poco fa mattina pomeriggio notte
""".split())


def norm(testo: str) -> str:
    t = unicodedata.normalize("NFKD", str(testo or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def parole(testo: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", norm(testo))


def radice(w: str) -> str:
    """Una radice grossolana per l'italiano: «gita» trova «gite», «panini» trova «panino»."""
    if len(w) >= 6:
        return w[:5]
    if len(w) >= 4:
        return w[:-1]
    return w


def chiavi(domanda: str) -> list[str]:
    out = []
    for w in parole(domanda):
        if len(w) < 3 or w in _VUOTE or w.isdigit():
            continue
        r = radice(w)
        if r not in out:
            out.append(r)
    return out


def punteggio(testo: str, radici: list[str]) -> int:
    ws = parole(testo)
    return sum(1 for r in radici if any(w.startswith(r) for w in ws))


@dataclass
class Chi:
    """Chi cerca: `pid` (id del profilo), `nome`, `minore`, `tutore_di` (gli id dei minori di
    cui è tutore), `sat` (il satellite da cui parla, o None)."""
    pid: str
    nome: str
    minore: bool = False
    tutore_di: set = field(default_factory=set)
    sat: object = None


@dataclass
class Esito:
    esito: str                      # trovato, niente, negato, spento, pausa, stanza_ignota
    righe: list = field(default_factory=list)      # (sat, riga) nell'ordine
    testo: str = ""                 # le righe per il modello (senza busta)
    tagliate: int = 0
    stanze: list = field(default_factory=list)     # nomi delle stanze delle righe date
    attesa_ms: int = 0              # righe in coda aspettate
    mancano: int = 0                # righe ancora in coda dopo l'attesa
    attesa_detta: bool = False
    motivo: str = ""
    senza_parole: bool = False      # con la persona: le parole non c'erano, le sue frasi
    allargata: bool = False         # persona e stanza scelte non c'entravano: tutte le stanze


def _giorno(epoch: float, oggi: datetime.date) -> str:
    d = datetime.datetime.fromtimestamp(epoch)
    ora = d.strftime("%H:%M")
    if d.date() == oggi:
        return ora
    if d.date() == oggi - datetime.timedelta(days=1):
        return f"ieri {ora}"
    return d.strftime("%d/%m %H:%M")


def intervallo(quando: str | None, dalle: str | None, alle: str | None,
               adesso: float | None = None) -> tuple[float | None, float | None]:
    """(da, a) in epoch dal periodo detto e dagli orari «HH:MM» (oggi; un orario ancora da
    venire vale ieri). None = senza limite. Conversione della forma di una scelta del modello
    (principio 10)."""
    adesso = time.time() if adesso is None else adesso
    oggi = datetime.datetime.fromtimestamp(adesso)
    mezzanotte = oggi.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    da = a = None
    q = str(quando or "").strip().lower()
    if q == "ultima_ora":
        da = adesso - 3600
    elif q == "ieri":
        da, a = mezzanotte - 86400, mezzanotte
    elif q in _FASCE:
        h0, h1 = _FASCE[q]
        da, a = mezzanotte + h0 * 3600, mezzanotte + h1 * 3600
        if da > adesso:                      # «stasera» detto stamattina: quella di ieri
            da, a = da - 86400, a - 86400
    for nome, valore in (("dalle", dalle), ("alle", alle)):
        m = re.fullmatch(r"\s*(\d{1,2})(?:[:.](\d{2}))?\s*", str(valore or ""))
        if not m or int(m.group(1)) > 23:
            continue
        t = mezzanotte + int(m.group(1)) * 3600 + int(m.group(2) or 0) * 60
        if t > adesso + 60:
            t -= 86400
        if nome == "dalle":
            da = t
        else:
            a = t
    if da is not None and a is not None and a < da:
        da, a = a, da
    return da, a


def finestre(stanza, chi: Chi, cfg, adesso: float) -> dict:
    """{sat: [(da, a)]}: dove e quando la persona c'era (più gli ultimi minuti della stanza da
    cui parla)."""
    presenza_s = float(getattr(cfg, "stanza_presenza_s", 600.0) or 600.0)
    inter = sorted(stanza.presenze(chi.pid), key=lambda x: x[1])
    out: dict = {}
    for i, (sat, ini, fin) in enumerate(inter):
        dopo = inter[i + 1][1] if i + 1 < len(inter) else None
        fine = fin + presenza_s
        if dopo is not None and inter[i + 1][0] != sat:
            fine = min(fine, dopo)
        out.setdefault(sat, []).append((ini - MARGINE_PRIMA_S, fine))
    if chi.sat is not None:
        caldo = float(getattr(cfg, "stanza_caldo_min", 8.0) or 8.0) * 60
        out.setdefault(chi.sat, []).append((adesso - caldo, adesso + 1))
    return out


def _dentro(t: float, fin: list) -> bool:
    return any(a <= t <= b for a, b in fin)


def visibile(r: dict, sat, chi: Chi, fin: dict) -> bool:
    """La riga `r` della stanza `sat` si può dare a `chi`?"""
    sic = r.get("sicurezza")
    if r.get("chi") != "calliope" and sic not in ("voce", "grigia"):
        return False                           # voce non riconosciuta: mai nella ricerca
    pid = str(r.get("chi") or "")[len("persona:"):] if str(r.get("chi") or "").startswith(
        "persona:") else None
    if chi.minore:
        return pid == chi.pid and sic == "voce"
    if r.get("minore"):
        return pid is not None and pid in chi.tutore_di
    t = float(r.get("fine") or r.get("t") or 0)
    return _dentro(t, fin.get(sat, ()))


def _sat_per_nome(stanza, nome: str) -> list:
    n = norm(nome).strip()
    if not n:
        return []
    out = []
    for sat, info in list(stanza._info.items()):
        for v in (info.get("stanza"), info.get("nome")):
            v = norm(v or "").strip()
            if v and (v == n or n in v.split() or v in n.split() or n in v):
                out.append(sat)
                break
    return out


def nome_stanza(stanza, sat) -> str:
    info = stanza._info.get(sat) or {}
    return str(info.get("stanza") or info.get("nome") or sat)


def _attendi(stanza, sats: set, cfg, attesa=None) -> tuple[int, int, bool]:
    """Le righe delle stanze cercate ancora in coda: passano davanti e si aspettano al più
    `stanza_cerca_attesa_max_s`; oltre `stanza_cerca_attesa_s` la frase d'attesa (una volta).
    (ms aspettati, quante mancano ancora, frase detta)."""
    tetto = float(getattr(cfg, "stanza_cerca_attesa_max_s", 3.0) or 0.0)
    soglia = float(getattr(cfg, "stanza_cerca_attesa_s", 0.7) or 0.0)
    t0 = time.monotonic()
    detta = False

    def pendenti():
        return [s for sat in sats for s in stanza._recenti.get(sat, ())
                if s.ascolto is None and s.stato != "fatto"]
    with stanza._cond:
        segs = pendenti()
        if not segs:
            return 0, 0, False
        for s in segs:
            s.recupero = True
        stanza._cond.notify_all()
    while True:
        with stanza._cond:
            resto = [s for s in segs if s.stato != "fatto"]
            ora = time.monotonic()
            if not resto or ora - t0 >= tetto:
                break
            limite = t0 + (soglia if not detta and soglia < tetto else tetto)
            if ora < limite:
                stanza._cond.wait(min(limite - ora, 0.1))
                continue
        # Oltre la soglia, fuori dal lock: la frase d'attesa va alla voce
        if not detta:
            detta = True
            if attesa is not None:
                try:
                    attesa()
                except Exception:  # noqa: BLE001 — la frase d'attesa non cambia il risultato
                    pass
    return int((time.monotonic() - t0) * 1000), len(resto), detta


def cerca(stanza, cfg, chi: Chi, parole_cercate: str = "", persona: str = "",
          dove: str = "", quando: str = "", dalle: str = "", alle: str = "",
          attesa=None, adesso: float | None = None) -> Esito:
    """La ricerca, con i permessi già decisi per `chi` (vedi il modulo)."""
    adesso = time.time() if adesso is None else adesso
    # Le stanze: quella detta, o tutte quelle che il registro conosce
    if dove:
        sats = _sat_per_nome(stanza, dove)
        if not sats:
            return Esito("stanza_ignota", motivo=dove)
    else:
        sats = list(stanza._info)
    if chi.sat is not None and (stanza.stato_pausa(chi.sat) or {}).get("motivo") == "ospiti":
        return Esito("pausa")
    attesa_ms, mancano, detta = _attendi(stanza, set(sats), cfg, attesa)
    da, a = intervallo(quando, dalle, alle, adesso)
    fin = finestre(stanza, chi, cfg, adesso)
    radici = chiavi(parole_cercate)
    pers = norm(persona).strip()
    candidate = []                             # (sat, riga) visibili e nel periodo
    for sat in list(stanza._info):
        for r in stanza.registro(sat).righe():
            if not str(r.get("testo") or "").strip():
                continue
            t = float(r.get("fine") or r.get("t") or 0)
            if (da is not None and t < da) or (a is not None and t > a):
                continue
            if not visibile(r, sat, chi, fin):
                continue
            candidate.append((sat, r))
    dentro = set(sats)

    def scegli(radici, filtri=True):
        out = []
        for sat, r in candidate:
            if filtri and sat not in dentro:
                continue
            nome = norm(r.get("nome") or ("calliope" if r.get("chi") == "calliope" else ""))
            if filtri and pers and (not nome or (nome != pers and pers not in nome.split())):
                continue
            # Il nome di chi parla conta come una parola della riga: «cosa ha detto Nicola?»
            # cercato con la frase intera trova le righe di Nicola
            p = punteggio(f"{r.get('testo') or ''} {nome}", radici) if radici else 0
            if radici and p == 0:
                continue
            out.append((p, sat, r))
        return out
    trovate = scegli(radici)
    out = Esito("niente", attesa_ms=attesa_ms, mancano=mancano, attesa_detta=detta)
    if not trovate and pers and radici and pers != norm(chi.nome):
        # «Cosa ha detto Nicola della gita?» e Nicola non ha detto «gita» («sabato non vengo»):
        # le sue frasi nel periodo, e il modello giudica
        trovate = scegli([])
        out.senza_parole = bool(trovate)
        if trovate:
            radici = []
    if not trovate and radici and (dove or pers):
        # La persona o la stanza scelte dal modello non c'entravano («a che ora avevamo deciso di
        # partire?» → persona = chi parla, stanza = quella di adesso, e se n'era parlato in
        # cucina): le stesse parole in tutte le stanze che chi chiede può vedere
        trovate = scegli(radici, filtri=False)
        out.allargata = bool(trovate)
    if not trovate:
        return out
    tetto_righe = int(getattr(cfg, "stanza_cerca_righe", 20) or 20)
    tetto_car = int(getattr(cfg, "stanza_cerca_caratteri", 2400) or 2400)
    # Le più pertinenti, poi le più recenti
    trovate.sort(key=lambda x: (-x[0], -float(x[2].get("fine") or x[2].get("t") or 0)))
    # Le vicine danno il senso («io porto i panini» dopo «chi porta da mangiare?»): la riga
    # prima e quella dopo nella stessa stanza, entro VICINE_S, solo per una ricerca di parole
    posto = {(sat, r["seq"]): i for i, (sat, r) in enumerate(candidate)}
    scelte: dict = {}
    for _, sat, r in trovate:
        if len(scelte) >= tetto_righe:
            break
        scelte.setdefault((sat, r["seq"]), (sat, r))
        if not radici:
            continue
        i = posto[(sat, r["seq"])]
        t = float(r.get("fine") or r.get("t") or 0)
        for j in (i - 1, i + 1):
            if 0 <= j < len(candidate) and len(scelte) < tetto_righe:
                s2, r2 = candidate[j]
                if s2 == sat and abs(float(r2.get("fine") or r2.get("t") or 0) - t) <= VICINE_S:
                    scelte.setdefault((s2, r2["seq"]), (s2, r2))
    elenco = sorted(scelte.values(),
                    key=lambda x: (float(x[1].get("inizio") or x[1].get("t") or 0), x[1]["seq"]))
    oggi = datetime.date.fromtimestamp(adesso)
    righe_txt, usati, prese = [], 0, []
    for sat, r in reversed(elenco):             # dalla più nuova, finché sta nel tetto
        testo = " ".join(str(r.get("testo") or "").split())
        riga = f"{_giorno(float(r.get('inizio') or r.get('t') or 0), oggi)} {etichetta(r)}: {testo}"
        if usati + len(riga) + 1 > tetto_car and prese:
            break
        usati += len(riga) + 1
        prese.append((sat, r, riga))
    prese.reverse()
    date = {(sat, r["seq"]) for sat, r, _ in prese}
    out.tagliate = sum(1 for _, sat, r in trovate if (sat, r["seq"]) not in date)
    blocchi, ultimo = [], object()
    for sat, r, riga in prese:
        if sat != ultimo:
            blocchi.append(f"In {nome_stanza(stanza, sat)}:")
            ultimo = sat
        blocchi.append(riga)
    out.esito = "trovato"
    out.righe = [(sat, r) for sat, r, _ in prese]
    out.testo = "\n".join(blocchi)
    out.stanze = list(dict.fromkeys(nome_stanza(stanza, sat) for sat, _, _ in prese))
    return out
