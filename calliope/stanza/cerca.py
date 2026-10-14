"""
La ricerca nella conversazione della stanza (14/10, conversazione di stanza, **passo 4**:
progetto docs/ricerche/2026-10-13-conversazione-di-stanza.md § 3.5 ter, § 3.7, § 3.8, § 6 riga
4; decisione 0029 punti 5 e 6). Il tool è `stanza_cerca` (tools/stanza.py); qui la parte che
non dipende dal modello: chi può vedere quali righe, i filtri, il punteggio, il tetto, l'attesa
delle righe ancora in coda e la frase d'attesa.

Serve per ciò che il blocco caldo dei dati del turno (stanza/contesto.py) non ha più: le righe
uscite dagli ultimi `stanza_caldo_min` minuti, o dette in un'altra stanza («di cosa parlavamo
in cucina prima?», «cosa aveva detto Carlo della gita stamattina?»). Cerca nel registro della
stanza **in memoria** (la tenuta del passo 1: al più 24 h, fino al riavvio) e, dal 14/10 con
`stanza_tenuta`, anche **su disco** (stanza/tenuta.py, 60 giorni) con gli stessi permessi: le
presenze di prima del riavvio vengono dal disco, i prefiltri (minore, tutori) li fa la query e
il resto `visibile`, come per la memoria; le righe ancora in memoria non si ripetono.

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
- le proprie righe riconosciute dalla voce si vedono sempre (14/10: dopo un riavvio la presenza
  aperta poteva non essere sul disco);
- le righe di un **conoscente** (14/10, decisione 0030: confermato da chi amministra) si
  cercano come quelle di un adulto di casa: chi c'era; il nome con il cognome («cosa ha detto
  Marco Rossi?») distingue gli omonimi, e la nota è nell'etichetta;
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

Dal 14/10 sera: una riga trovata porta con sé il discorso intorno (lo scambio, `VICINE_RIGHE`);
un `quando` che non è un periodo è una parola cercata (`periodo`); la stessa ricerca, senza
attesa e senza le righe del blocco caldo, la fa Brain prima della risposta (la ricerca
anticipata, tools/stanza.py `anticipa`).
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
# Una riga trovata porta con sé il discorso intorno (14/10, banco della DGX: «a che ora avevamo
# deciso di partire per la gita?» trovava «Sabato andiamo in gita…» ma non «partiamo alle nove
# dalla piazza», detta quattro minuti dopo senza la parola «gita»): fino a VICINE_RIGHE righe
# prima e dopo nello stesso scambio della stessa stanza (lo stesso `scambio` del registro, o
# righe separate da meno di `stanza_scambio_pausa_s`), prima le più vicine
VICINE_RIGHE = 4
PERIODI = ("ultima_ora", "mattina", "pomeriggio", "sera", "notte", "oggi", "ieri")
_FASCE = {"mattina": (6, 12), "pomeriggio": (12, 18), "sera": (18, 24), "notte": (0, 6),
          "oggi": (0, 24)}
# Come il modello scrive i periodi (14/10): «stamattina», «ieri sera». Il resto («sabato», il
# giorno della gita e non della conversazione) non è un periodo: diventa una parola cercata
_SINONIMI = {"stamattina": "mattina", "stamani": "mattina", "mattino": "mattina",
             "stasera": "sera", "stanotte": "notte", "oggi pomeriggio": "pomeriggio",
             "questa mattina": "mattina", "questa sera": "sera", "questo pomeriggio":
             "pomeriggio", "un'ora fa": "ultima_ora", "ultima ora": "ultima_ora",
             "nell'ultima ora": "ultima_ora"}
# Periodi che non restringono niente (il blocco caldo e la ricerca guardano già lì)
_SENZA_LIMITE = frozenset(("", "prima", "poco fa", "adesso", "ora", "di recente", "recente",
                           "recentemente", "tutto", "sempre", "qualsiasi", "nessuno"))
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
dove quanto quanti quanta quante deciso decidere decisione sai sapere sapete ricordi ricordo
ricordare ricordate ore stato stata stati abbiamo avevo avete dirmi dimmi detto sentito
""".split())
# Desinenze tolte per la radice (14/10): «partire», «partiamo» e «partenza» danno «part»
_DESINENZE = ("issimo", "issima", "mente", "zione", "zioni", "iamo", "iate", "ando", "endo",
              "enza", "anza", "ante", "ente", "are", "ere", "ire", "ato", "ata", "ati", "ate",
              "ito", "ita", "iti", "ite", "uto", "uta", "ava", "avo", "eva", "evo", "iva",
              "ivo", "ono", "ano")


def norm(testo: str) -> str:
    t = unicodedata.normalize("NFKD", str(testo or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def parole(testo: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", norm(testo))


def radice(w: str) -> str:
    """Una radice grossolana per l'italiano: «gita» trova «gite», «panini» trova «panino»,
    «partenza» trova «partiamo» (una desinenza comune tolta, se resta una radice di almeno
    quattro lettere). Al più cinque lettere: la riga trova chi comincia così."""
    if len(w) >= 7:
        for d in _DESINENZE:
            if w.endswith(d) and len(w) - len(d) >= 4:
                return w[:len(w) - len(d)][:5]
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


def nome_combacia(pers: str, nome: str) -> bool:
    """La persona cercata è il nome della riga: uguale, una sua parola («Carlo»), o dal 14/10
    (conoscenti, decisione 0030) le sue parole di seguito («Marco Rossi» nel nome «Marco
    Rossi»). `pers` e `nome` già normalizzati."""
    p, n = pers.split(), nome.split()
    if not p or not n:
        return False
    return any(n[i:i + len(p)] == p for i in range(len(n) - len(p) + 1))


def rare(domanda: str) -> dict[str, str]:
    """{radice: parola} per le parole lunghe della domanda (almeno 6 lettere, non vuote): quelle
    che Whisper storpia di una lettera e che si cercano anche simili (`simile`)."""
    out = {}
    for w in parole(domanda):
        if len(w) >= 6 and w not in _VUOTE and not w.isdigit():
            out.setdefault(radice(w), w)
    return out


def simile(a: str, b: str) -> bool:
    """Due parole lunghe a una modifica di distanza (una lettera cambiata, tolta o aggiunta), con
    la stessa iniziale: «crisima» e «cresima» (Whisper, caso vero del 14/10 sera), non «crisima» e
    «cristina» (due) né «Rachele» e «Raffaele». Solo parole di almeno 6 lettere: le corte sono
    troppe a una lettera di distanza."""
    if a == b:
        return True
    if not a or not b or a[0] != b[0] or abs(len(a) - len(b)) > 1 or min(len(a), len(b)) < 6:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    if len(a) == len(b):
        return a[i + 1:] == b[i + 1:]
    return a[i:] == b[i + 1:]


def combacia(radici: list[str], ws: list[str], simili: dict | None = None) -> set[str]:
    """Le radici della domanda che una riga (le sue parole `ws`) contiene: comincia così, o
    (dal 14/10 notte, `simili` = `rare(domanda)`) è simile alla parola lunga della domanda."""
    out = set()
    for r in radici:
        if any(w.startswith(r) for w in ws):
            out.add(r)
        elif simili and r in simili and any(simile(w, simili[r]) for w in ws):
            out.add(r)
    return out


def punteggio(testo: str, radici: list[str], simili: dict | None = None) -> int:
    return len(combacia(radici, parole(testo), simili))


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


def periodo(quando: str | None) -> tuple[str | None, bool, str]:
    """Il `quando` scritto dal modello: (fascia o «ultima_ora» o None, ieri?, parole). Un
    periodo riconosciuto filtra; «prima», «poco fa» non restringono; tutto il resto («sabato»,
    il giorno della gita e non della conversazione: banco della DGX del 14/10) torna come
    parole da cercare, mai come filtro. Conversione della forma di una scelta del modello
    (principio 10)."""
    q = " ".join(norm(quando).replace("_", " ").split())
    q = q.replace("’", "'")
    if q in _SENZA_LIMITE:
        return None, False, ""
    if q.replace(" ", "_") in PERIODI:
        q = q.replace(" ", "_")
    q = _SINONIMI.get(q, q)
    if q == "ieri":
        return None, True, ""
    if q.startswith("ieri "):
        resto = _SINONIMI.get(q[5:], q[5:])
        if resto in _FASCE and resto != "oggi":
            return resto, True, ""
    if q in _FASCE or q == "ultima_ora":
        return q, False, ""
    return None, False, str(quando or "").strip()


def intervallo(quando: str | None, dalle: str | None, alle: str | None,
               adesso: float | None = None) -> tuple[float | None, float | None]:
    """(da, a) in epoch dal periodo detto e dagli orari «HH:MM» (oggi; un orario ancora da
    venire vale ieri). None = senza limite. Conversione della forma di una scelta del modello
    (principio 10). Un `quando` che non è un periodo non limita (vedi `periodo`)."""
    adesso = time.time() if adesso is None else adesso
    oggi = datetime.datetime.fromtimestamp(adesso)
    mezzanotte = oggi.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    da = a = None
    q, ieri, _ = periodo(quando)
    if q == "ultima_ora":
        da = adesso - 3600
    elif ieri and q is None:
        da, a = mezzanotte - 86400, mezzanotte
    elif q in _FASCE:
        h0, h1 = _FASCE[q]
        da, a = mezzanotte + h0 * 3600, mezzanotte + h1 * 3600
        if ieri:
            da, a = da - 86400, a - 86400
        elif da > adesso:                    # «stasera» detto stamattina: quella di ieri
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
    if pid is not None and pid == chi.pid and sic == "voce":
        return True                            # le proprie parole
    t = float(r.get("fine") or r.get("t") or 0)
    return _dentro(t, fin.get(sat, ()))


def info_stanze(stanza) -> dict:
    """{sat: {nome, stanza}}: i satelliti che il registro conosce e, con la tenuta su disco
    (14/10), quelli che hanno righe sul disco anche se adesso non sono collegati."""
    out = {k: dict(v or {}) for k, v in list(stanza._info.items())}
    t = getattr(stanza, "tenuta", None)
    if t is not None:
        try:
            disco = t.stanze()
        except Exception:  # noqa: BLE001 — senza il disco, quelle della memoria
            disco = {}
        chiave = getattr(stanza, "chiave_sat", lambda s: s)
        for s, v in disco.items():
            out.setdefault(chiave(s), {"nome": v.get("nome"), "stanza": v.get("stanza")})
    return out


def _sat_per_nome(stanza, nome: str, info: dict | None = None) -> list:
    n = norm(nome).strip()
    if not n:
        return []
    out = []
    for sat, i in list((info if info is not None else stanza._info).items()):
        for v in (i.get("stanza"), i.get("nome")):
            v = norm(v or "").strip()
            if v and (v == n or n in v.split() or v in n.split() or n in v):
                out.append(sat)
                break
    return out


def nome_stanza(stanza, sat, info: dict | None = None) -> str:
    i = (info if info is not None else stanza._info).get(sat) or {}
    return str(i.get("stanza") or i.get("nome") or sat)


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


def _scambi(candidate: list, cfg) -> list:
    """Per ogni riga candidata il numero del suo scambio: stessa stanza, stesso `scambio` del
    registro (se le due righe lo hanno) e meno di `stanza_scambio_pausa_s` di silenzio."""
    pausa = float(getattr(cfg, "stanza_scambio_pausa_s", 300.0) or 300.0)
    out, n, prima = [], 0, None
    for sat, r in candidate:
        if prima is not None:
            ps, pr = prima
            ini = float(r.get("inizio") or r.get("t") or 0)
            fin = float(pr.get("fine") or pr.get("t") or 0)
            if (ps != sat or ini - fin > pausa
                    or (r.get("scambio") is not None and pr.get("scambio") is not None
                        and r.get("scambio") != pr.get("scambio"))):
                n += 1
        out.append(n)
        prima = (sat, r)
    return out


def cerca(stanza, cfg, chi: Chi, parole_cercate: str = "", persona: str = "",
          dove: str = "", quando: str = "", dalle: str = "", alle: str = "",
          attesa=None, adesso: float | None = None, escludi_testo: str = "",
          escludi=frozenset(), tetto_righe: int | None = None, tetto_car: int | None = None,
          aspetta: bool = True, minimo: int = 1, propri=frozenset()) -> Esito:
    """La ricerca, con i permessi già decisi per `chi` (vedi il modulo). `escludi_testo`: la
    frase del turno (la sua riga nella stanza non si dà). `escludi`: le (stanza, seq) già nel
    blocco caldo (la ricerca anticipata non le ripete). `aspetta=False`: niente attesa delle
    righe in coda (la ricerca anticipata non fa aspettare la voce). `minimo` (la ricerca
    anticipata, 14/10 notte): una riga vale se ha almeno tante radici della domanda, o una di
    `propri` (i nomi propri detti nella domanda: «Rachele» basta da solo). Le parole lunghe della
    domanda trovano anche le parole simili a una lettera (`simile`: le storpiature di Whisper)."""
    adesso = time.time() if adesso is None else adesso
    tenuta = getattr(stanza, "tenuta", None)
    info = info_stanze(stanza) if tenuta is not None else stanza._info
    # Le stanze: quella detta, o tutte quelle che il registro conosce (e il disco, 14/10)
    if dove:
        sats = _sat_per_nome(stanza, dove, info)
        if not sats:
            return Esito("stanza_ignota", motivo=dove)
    else:
        sats = list(info)
    if chi.sat is not None and (stanza.stato_pausa(chi.sat) or {}).get("motivo") == "ospiti":
        return Esito("pausa")
    attesa_ms, mancano, detta = (_attendi(stanza, set(sats), cfg, attesa) if aspetta
                                 else (0, 0, False))
    da, a = intervallo(quando, dalle, alle, adesso)
    fin = finestre(stanza, chi, cfg, adesso)
    # Un `quando` che non è un periodo («sabato») è una parola in più, non un filtro
    _, _, in_piu = periodo(quando)
    # Il nome della stanza cercata non è una parola dell'argomento («cosa si diceva in
    # taverna?» con stanza=taverna: le righe non dicono «taverna»)
    togli = set(parole(dove)) | {w for s in (sats if dove else ())
                                 for w in parole(nome_stanza(stanza, s, info))}
    testo_cercato = " ".join(w for w in parole(f"{parole_cercate} {in_piu}") if w not in togli)
    radici = chiavi(testo_cercato)
    simili = rare(testo_cercato)
    pers = norm(persona).strip()
    # La domanda stessa è già nella stanza (ciclo: turno_testo, «→ Calliope»): non è una
    # risposta, e con le sue parole sarebbe sempre la prima trovata
    domanda = " ".join(parole(escludi_testo)) if escludi_testo else ""
    candidate = []                             # (sat, riga) visibili e nel periodo

    def ammessa(sat, r) -> bool:
        if not str(r.get("testo") or "").strip():
            return False
        t = float(r.get("fine") or r.get("t") or 0)
        if (da is not None and t < da) or (a is not None and t > a):
            return False
        if not visibile(r, sat, chi, fin):
            return False
        return not (domanda and r.get("rivolta") == "si"
                    and " ".join(parole(r["testo"])) == domanda)
    for sat in list(stanza._info):
        for r in stanza.registro(sat).righe():
            if ammessa(sat, r):
                candidate.append((sat, r))
    if tenuta is not None:
        # Il disco (14/10): le stesse regole, senza le righe ancora in memoria
        candidate += [(sat, r) for sat, r in _dal_disco(stanza, tenuta, chi, radici, sats, da,
                                                         a, norm(persona).strip())
                      if ammessa(sat, r)]
        ordine_sat = {s: i for i, s in enumerate(info)}
        candidate.sort(key=lambda x: (ordine_sat.get(x[0], len(ordine_sat)),
                                      float(x[1].get("inizio") or x[1].get("t") or 0),
                                      x[1]["seq"]))
    dentro = set(sats)

    def scegli(radici, filtri=True):
        out = []
        for sat, r in candidate:
            if filtri and sat not in dentro:
                continue
            nome = norm(r.get("nome") or ("calliope" if r.get("chi") == "calliope" else ""))
            if filtri and pers and (not nome or not nome_combacia(pers, nome)):
                continue
            # Il nome di chi parla conta come una parola della riga: «cosa ha detto Nicola?»
            # cercato con la frase intera trova le righe di Nicola
            prese = (combacia(radici, parole(f"{r.get('testo') or ''} {nome}"), simili)
                     if radici else set())
            p = len(prese)
            if radici and p == 0:
                continue
            if radici and p < min(minimo, len(radici)) and not (prese & set(propri)):
                continue
            if (sat, r["seq"]) in escludi:
                continue                       # già nel blocco caldo (ricerca anticipata)
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
    tetto_righe = int(tetto_righe or getattr(cfg, "stanza_cerca_righe", 20) or 20)
    tetto_car = int(tetto_car or getattr(cfg, "stanza_cerca_caratteri", 2400) or 2400)
    # Le più pertinenti, poi le più recenti
    trovate.sort(key=lambda x: (-x[0], -float(x[2].get("fine") or x[2].get("t") or 0)))
    oggi = datetime.date.fromtimestamp(adesso)

    def testo_riga(r) -> str:
        testo = " ".join(str(r.get("testo") or "").split())
        return f"{_giorno(float(r.get('inizio') or r.get('t') or 0), oggi)} {etichetta(r)}: {testo}"
    # L'ordine in cui le righe entrano nei tetti: prima le trovate; poi, per una ricerca di
    # parole, il discorso intorno a ciascuna («partiamo alle nove dalla piazza» quattro minuti
    # dopo «Sabato andiamo in gita»), dalla più vicina, dentro lo stesso scambio
    ordine = [(sat, r) for _, sat, r in trovate]
    if radici:
        posto = {(sat, r["seq"]): i for i, (sat, r) in enumerate(candidate)}
        scambio = _scambi(candidate, cfg)
        for d in range(1, VICINE_RIGHE + 1):
            for _, sat, r in trovate:
                i = posto[(sat, r["seq"])]
                for j in (i - d, i + d):
                    if 0 <= j < len(candidate) and scambio[j] == scambio[i]:
                        ordine.append(candidate[j])
    scelte: dict = {}
    usati = 0
    for sat, r in ordine:
        k = (sat, r["seq"])
        if k in scelte or k in escludi:
            continue
        if len(scelte) >= tetto_righe:
            break
        riga = testo_riga(r)
        if usati + len(riga) + 1 > tetto_car and scelte:
            continue                           # non ci sta: magari una più corta sì
        usati += len(riga) + 1
        scelte[k] = (sat, r, riga)
    prese = sorted(scelte.values(),
                   key=lambda x: (float(x[1].get("inizio") or x[1].get("t") or 0), x[1]["seq"]))
    out.tagliate = sum(1 for _, sat, r in trovate if (sat, r["seq"]) not in scelte)
    blocchi, ultimo = [], object()
    for sat, r, riga in prese:
        if sat != ultimo:
            blocchi.append(f"In {nome_stanza(stanza, sat, info)}:")
            ultimo = sat
        blocchi.append(riga)
    out.esito = "trovato"
    out.righe = [(sat, r) for sat, r, _ in prese]
    out.testo = "\n".join(blocchi)
    out.stanze = list(dict.fromkeys(nome_stanza(stanza, sat, info) for sat, _, _ in prese))
    return out


def _dal_disco(stanza, tenuta, chi: Chi, radici: list, sats: list, da, a, pers: str) -> list:
    """Le righe candidate dal disco (stanza/tenuta.py) come (sat, riga), con i prefiltri dei
    permessi nella query (un minore solo le sue, un adulto i minori solo da tutore), senza
    quelle ancora nel registro in memoria di questo avvio. Le regole fini restano `visibile`."""
    escludi = {str(s): r.seq_vivi() for s, r in list(getattr(stanza, "_registri", {}).items())
               if hasattr(r, "seq_vivi")}
    nomi = []
    if pers:
        try:
            nomi = [n for n in tenuta.nomi() if nome_combacia(pers, " ".join(parole(n)))]
        except Exception:  # noqa: BLE001
            nomi = []
    try:
        righe = tenuta.cerca(radici=radici, sats=sats, da=da, a=a, nomi=nomi,
                             minore_pid=chi.pid if chi.minore else None,
                             tutore_di=chi.tutore_di, recenti=not radici, escludi=escludi)
    except Exception:  # noqa: BLE001 — il disco non ferma la ricerca in memoria
        return []
    chiave = getattr(stanza, "chiave_sat", lambda s: s)
    return [(chiave(r["sat"]), r) for r in righe]
