"""
Calliope sa a che punto è il gioco (14/10/2026, passo 5 del progetto
docs/ricerche/2026-10-12-giochi-macchina-stati.md § 4; area docs/aree/giochi.md).

Dal passo 2 lato server il motore del gioco manda a Calliope l'**istantanea** della partita
(fase, a chi tocca, giocatori e punti, esito, comandi a voce attivi), validata contro il
manifesto (calliope/estensioni/macchina.py). Qui ciò che Calliope ne fa:

- **Le domande standard**, forme chiuse brevi di ogni fase, riconosciute **per intero** (regola
  `gioco_stato_detto` del ciclo, principio 10: una forma chiusa e breve, effetto reversibile,
  una frase detta): «a chi tocca?», «quanti punti ho?», «chi sta vincendo?», «cosa posso
  dire?». La risposta la compone il codice dall'istantanea: nessun modello, nessun calcolo del
  gioco (Calliope legge, non deduce). Dentro una frase più lunga («a chi tocca adesso secondo
  te?») la frase va al giudice di fase o al modello, con l'istantanea nei dati del turno.
- **L'istantanea nei dati del turno** per le altre domande («chi sta perdendo?», «quante porte
  restano?»): una riga per il modello con fase, a chi tocca, punti e comandi. Il testo
  dell'esito è del gioco e non va mai al modello né si dice. I nomi scritti sullo schermo sono
  testo del gioco: con uno di loro la riga va in busta (fonte «gioco», calliope/provenienza.py).

Solo libreria standard; il confronto è quello dei comandi a voce (gioco_voce.normalizza).
"""
from __future__ import annotations

from . import gioco_voce


def _mc():
    from .estensioni import macchina    # qui dentro: macchina.py chiede a questo modulo le forme
    return macchina


# Le domande standard, nella forma scritta (si confrontano normalizzate, per intero)
DOMANDE: dict[str, tuple[str, ...]] = {
    "tocca": ("a chi tocca", "tocca a chi", "chi tocca", "di chi è il turno", "a chi tocca adesso",
              "a chi tocca ora", "chi deve giocare", "chi gioca adesso", "chi gioca ora"),
    "punti": ("quanti punti ho", "quanti punti ho fatto", "quanti punti abbiamo",
              "quanti punti abbiamo fatto", "quanti punti hanno", "il punteggio",
              "qual è il punteggio", "dimmi il punteggio", "dimmi i punti", "come sono i punti",
              "che punteggio ho", "i punti"),
    "vince": ("chi sta vincendo", "chi vince", "chi è in testa", "come siamo messi",
              "chi ha vinto", "chi è primo", "chi è il primo"),
    "comandi": ("cosa posso dire", "che cosa posso dire", "cosa si può dire",
                "che cosa si può dire", "cosa posso fare", "che cosa posso fare",
                "quali sono i comandi", "che comandi ci sono", "quali comandi ci sono"),
    # Chi è quale giocatore (15/10): ogni persona sa quale giocatore è
    "io": ("che giocatore sono", "che giocatore sono io", "quale giocatore sono",
           "quale giocatore sono io", "chi sono nel gioco", "io chi sono nel gioco"),
}
REGOLA = "gioco_stato_detto"


def _tabella(nomi=("Calliope",)) -> dict[str, str]:
    out = {}
    for tipo, forme in DOMANDE.items():
        for f in forme:
            n = gioco_voce.normalizza(f, nomi)
            if n:
                out.setdefault(n, tipo)
    return out


_TABELLA = _tabella()


def forme_normalizzate(nomi=("Calliope",)) -> set[str]:
    """Le forme delle domande standard normalizzate: un gioco non le può dichiarare come
    comandi (macchina.ascolta le rifiuta come doppioni)."""
    return set(_tabella(nomi) if tuple(nomi) != ("Calliope",) else _TABELLA)


def domanda(testo: str, nomi=("Calliope",)) -> str | None:
    """Il tipo di domanda standard («tocca», «punti», «vince», «comandi») se la frase è **per
    intero** una delle forme (il nome davanti, maiuscole, punteggiatura e accenti non contano),
    altrimenti None."""
    n = gioco_voce.normalizza(testo or "", nomi)
    if not n:
        return None
    tab = _TABELLA if tuple(nomi) == ("Calliope",) else _tabella(nomi)
    return tab.get(n)


# ─────────────────────────── le risposte ───────────────────────────

def _numero(x) -> str:
    if isinstance(x, float) and not x.is_integer():
        return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return str(int(x))


def _punti(x) -> str:
    return f"{_numero(x)} punto" if abs(x) == 1 else f"{_numero(x)} punti"


def _elenco(voci: list[str], congiunzione: str = "e") -> str:
    voci = [v for v in voci if v]
    if len(voci) <= 1:
        return "".join(voci)
    return ", ".join(voci[:-1]) + f" {congiunzione} " + voci[-1]


def _a(nome: str) -> str:
    """«a Bea», «ad Ada» (la d eufonica davanti alla a)."""
    return ("ad " if str(nome)[:1].lower() == "a" else "a ") + str(nome)


def nomi_detti(ist: dict) -> list[str]:
    """Come Calliope chiama i giocatori: il nome dell'istantanea se si può dire (`detto`, dal
    server: forma chiusa e controlli delle frasi dei giochi), altrimenti «Giocatore N»."""
    out = []
    for i, g in enumerate(ist.get("giocatori") or []):
        d = g.get("detto", g.get("nome"))
        out.append(d if isinstance(d, str) and d else f"Giocatore {i + 1}")
    return out


def _chi_e(ist: dict, chi: str | None, voci: dict | None = None) -> int | None:
    """La posizione del giocatore di chi parla (riconosciuto dalla voce): quello legato alla sua
    voce (15/10, il segno che Calliope gli ha dato nella partita), o quello con il suo nome;
    None."""
    if not chi:
        return None
    v = (voci or {}).get(chi)
    if v:
        for i, g in enumerate(ist.get("giocatori") or []):
            if g.get("voce") == v:
                return i
    k = gioco_voce.normalizza(chi)
    for i, g in enumerate(ist.get("giocatori") or []):
        if gioco_voce.normalizza(str(g.get("nome") or "")) == k:
            return i
    return None


def _classifica(ist: dict) -> list[tuple[str, float]]:
    nomi = nomi_detti(ist)
    righe = [(nomi[i], g.get("punti") or 0, i) for i, g in enumerate(ist.get("giocatori") or [])]
    righe.sort(key=lambda r: (-r[1], r[2]))
    return [(n, p) for n, p, _ in righe]


def comandi_in_parole(flat: list[str], m: dict | None, nomi=("Calliope",)) -> list[str]:
    """I comandi a voce attivi come si dicono: la prima forma di ogni comando, con i valori
    dello slot insieme («porta 1, 3 o 4», «2, 3 o 4 giocatori»)."""
    mc = _mc()
    gruppi: dict[tuple, list] = {}
    ordine: list[tuple] = []
    for c in flat or []:
        d = mc.da_piatto(m or {}, c) if m else None
        if d is None:
            chiave, forma, v = (c, None), c.replace("_", " "), None
        else:
            nome, v, fase = d
            if nome in mc.COMANDI_STANDARD:
                forma = mc.COMANDI_STANDARD[nome][0][0]
            else:
                forma = ((m.get("fasi") or {}).get(fase) or {}).get("comandi", {}).get(
                    nome, {}).get("forme", [nome])[0]
            chiave = (nome, fase)
        if chiave not in gruppi:
            gruppi[chiave] = [forma, []]
            ordine.append(chiave)
        if v is not None:
            gruppi[chiave][1].append(v)
    out = []
    for k in ordine:
        forma, valori = gruppi[k]
        if not valori:
            out.append(forma)
            continue
        dom = None
        if m and k[1]:
            dom = (((m.get("fasi") or {}).get(k[1]) or {}).get("comandi", {}).get(k[0], {})
                   .get("n"))
        detti = [(dom["valori"][v][0] if dom and "valori" in dom and v in dom["valori"]
                  else str(v)) for v in valori]
        out.append(forma.replace("{n}", _elenco(detti, "o")))
    return out


def risposta(tipo: str, info: dict, chi: str | None = None) -> str:
    """La frase per una domanda standard, composta dall'istantanea del gioco aperto
    (`info`: Giochi.ascolto). Solo campi del motore validati dal server; mai l'esito."""
    ist = info.get("istantanea") or {}
    fase = ist.get("fase")
    gs = ist.get("giocatori") or []
    nomi = nomi_detti(ist)
    if tipo == "comandi":
        voci = comandi_in_parole(ist.get("comandi") or [], info.get("macchina"))
        if not voci:
            return "Adesso il gioco non aspetta comandi a voce."
        if len(voci) == 1:
            return f"Puoi dire: {voci[0]}."
        return f"Puoi dire: {', '.join(voci[:-1])}, oppure {voci[-1]}."
    if fase == "preparazione" or not gs:
        return "La partita non è ancora cominciata: prima si sceglie quanti giocano."
    io = _chi_e(ist, chi, info.get("voci"))
    if tipo == "io":
        return _chi_sono(ist, info, io, nomi)
    if tipo == "tocca":
        if fase == "fine":
            return "La partita è finita." + (" Per giocarne un'altra di' «ancora»."
                                             if "ancora" in (ist.get("comandi") or []) else "")
        if len(gs) == 1:
            return "Giochi da solo: tocca sempre a te."
        t = ist.get("tocca")
        if t is None or not (0 <= t < len(nomi)):
            return "Adesso non tocca a nessuno in particolare."
        if fase == "esito":
            return f"Ha appena giocato {nomi[t]}."
        return "Tocca a te." if io == t else f"Tocca {_a(nomi[t])}{_dove(gs[t], info)}."
    if tipo == "punti":
        if io is not None:
            return f"Hai {_punti(gs[io].get('punti') or 0)}."
        if len(gs) == 1:
            return f"{nomi[0]} ha {_punti(gs[0].get('punti') or 0)}."
        return _elenco([f"{nomi[i]} {_punti(g.get('punti') or 0)}"
                        for i, g in enumerate(gs)]) + "."
    if tipo == "vince":
        cl = _classifica(ist)
        if len(cl) == 1:
            return f"Giochi da solo: hai {_punti(cl[0][1])}."
        primo = cl[0][1]
        pari = [n for n, p in cl if p == primo]
        finita = fase == "fine"
        if len(pari) == len(cl):
            return ("È finita pari" if finita else "Per ora siete pari") + f", a {_punti(primo)}."
        if len(pari) > 1:
            return ("Sono arrivati primi a pari merito " if finita else "Sono in testa pari ") \
                + _elenco(pari) + f", con {_punti(primo)}."
        verbo = "Ha vinto" if finita else "Sta vincendo"
        return f"{verbo} {pari[0]}, con {_punti(primo)}."
    return ""


def _dove(g: dict, info: dict) -> str:
    """«, sullo schermo «Cucina»» se il giocatore gioca da un altro schermo della partita."""
    sch, qui = g.get("schermo"), info.get("posto")
    if not sch or not qui or sch == qui:
        return ""
    nome = (info.get("schermi") or {}).get(sch) or ""
    return f", sullo schermo «{nome}»" if nome else ", sull'altro schermo"


def _chi_sono(ist: dict, info: dict, io: int | None, nomi: list[str]) -> str:
    """«Che giocatore sono?» (15/10): dalla voce riconosciuta, altrimenti dallo schermo."""
    if io is not None:
        return f"Sei {nomi[io]}."
    qui = info.get("posto")
    miei = [nomi[i] for i, g in enumerate(ist.get("giocatori") or [])
            if qui and g.get("schermo") == qui]
    if len(miei) == 1:
        return f"Su questo schermo gioca {miei[0]}."
    if miei:
        return f"Su questo schermo giocano {_elenco(miei)}."
    if "anchio" in (ist.get("comandi") or []):
        return "Non ti riconosco tra i giocatori: per entrare di' «gioco anch'io»."
    return "Non ti riconosco tra i giocatori."


# ─────────────────────────── i dati del turno ───────────────────────────

def contesto(info: dict) -> tuple[str, bool]:
    """(la riga dell'istantanea per i dati del turno, se contiene testi del gioco). Testi del
    gioco = nomi scritti sullo schermo (né «Giocatore N» né il nome di chi è riconosciuto dalla
    voce): con loro la riga va in busta. L'esito non c'è mai. Circa 60 token."""
    ist = info.get("istantanea") or {}
    titolo = str(info.get("titolo") or "")[:60]
    fase = ist.get("fase") or ""
    nomi = nomi_detti(ist)
    gs = ist.get("giocatori") or []
    parti = [f"Sullo schermo c'è il gioco «{titolo}»"
             + (f", fase {fase.replace('_', ' ')}" if fase else "")]
    if fase == "preparazione" or not gs:
        parti.append("la partita non è ancora cominciata")
    else:
        t = ist.get("tocca")
        if fase == "fine":
            parti.append("la partita è finita")
        elif len(gs) > 1 and t is not None and 0 <= t < len(nomi):
            parti.append(f"ha appena giocato {nomi[t]}" if fase == "esito"
                         else f"tocca {_a(nomi[t])}")
        parti.append("punti: " + ", ".join(f"{nomi[i]} {_numero(g.get('punti') or 0)}"
                                            for i, g in enumerate(gs)))
    voci = comandi_in_parole(ist.get("comandi") or [], info.get("macchina"))
    parti.append("comandi a voce adesso: " + ("; ".join(voci) if voci else "nessuno"))
    testo = ". ".join(p[:1].upper() + p[1:] if k else p for k, p in enumerate(parti)) + "."
    # Testi del gioco: i nomi scritti che Calliope dice (quelli fermati sono «Giocatore N»)
    scritti = any(g.get("scritto") and g.get("detto", g.get("nome")) == g.get("nome")
                  for g in gs)
    return testo, scritti


# ─────────────────────────── «gioco anch'io, sono Pippo» ───────────────────────────
# Un ospite (o chi non è riconosciuto dalla voce) si dà un nome nella preparazione: la forma
# chiusa intera «(gioco) anch'io, sono / mi chiamo <nome>», con il nome di una o due parole di
# sole lettere (regola `gioco_anchio_nome`, principio 10: forma chiusa e breve, per intero,
# effetto reversibile, un nome sullo schermo). Il nome non è della voce riconosciuta: Calliope lo
# dice solo dopo i controlli delle frasi dei giochi, come uno scritto (schermi/giochi.py)
import re as _re  # noqa: E402

_ANCHIO = _re.compile(r"^(?:gioco |ci sono )?anch(?:e io| io|io) (?:sono|mi chiamo|e sono|e mi "
                      r"chiamo) ([a-zà-öø-ÿ']+(?: [a-zà-öø-ÿ']+)?)$")
REGOLA_ANCHIO = "gioco_anchio_nome"


def anchio_nome(testo: str, nomi=("Calliope",)) -> str | None:
    """Il nome in «gioco anch'io, sono Pippo» detto per intero (il nome di Calliope davanti
    non conta), con le iniziali maiuscole; None se la frase non è questa forma."""
    t = str(testo or "").lower().replace("’", "'")
    t = _re.sub(r"[^\wà-öø-ÿ' ]", " ", t)
    t = _re.sub(r"\s+", " ", t).strip()
    parole = t.split(" ")
    if parole and gioco_voce.ha_il_nome(parole[0], nomi):
        t = " ".join(parole[1:])
    t = t.replace("anch' io", "anch io").replace("anch'io", "anch io")
    m = _ANCHIO.match(t)
    if not m:
        return None
    nome = " ".join(p[:1].upper() + p[1:] for p in m.group(1).split(" "))
    if len(nome) > 20 or nome.lower().split(" ")[0] in _NON_NOMI:
        return None
    return nome


# Le parole che dopo «anch'io sono» non sono un nome («anch'io sono pronto»)
_NON_NOMI = {"io", "qui", "qua", "pronto", "pronta", "pronti", "stanco", "stanca", "contento",
             "contenta", "d'accordo", "daccordo", "pure", "dentro", "in", "un", "una", "il", "la",
             "lo", "le", "i", "gli", "di", "del", "della", "con", "per", "bravo", "brava",
             "capace", "felice", "curioso", "curiosa", "anch'io"}


__all__ = ["DOMANDE", "REGOLA", "domanda", "risposta", "contesto", "comandi_in_parole",
           "nomi_detti", "forme_normalizzate", "anchio_nome", "REGOLA_ANCHIO"]
