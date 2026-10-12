"""
L'indice del programma ministeriale per gli esercizi (12/10/2026, decisione di Dario: esercizi
e interrogazioni si basano sulle Indicazioni nazionali ufficiali; dove non bastano Calliope
chiede i dettagli, non improvvisa).

I dati sono nei file YAML accanto, letti una volta:
- `fonti.yaml`: le due Indicazioni (DM 221/2025 e DM 254/2012) con URL e data di lettura, e
  quali valgono per una classe in un anno scolastico (art. 1 e 5 del DM 221/2025);
- `matematica.yaml`, `italiano.yaml`: `obiettivi` (testo ufficiale, citazioni letterali, con il
  traguardo: fine della terza e della quinta primaria, fine della terza media) e `mappa`
  (interpolazione: per argomento, classe e periodo dell'anno, entro quale numero, il livello
  del generatore, un esempio, il perché);
- `scienze.yaml`: l'aggancio di logica, fisica e chimica agli obiettivi di matematica e scienze.

Fase A (12/10): solo dati e lettura. Fase B (12/10 sera, decisioni di Dario): l'indice è il
limite STRETTO degli esercizi (`limite`: livello di partenza e di salita, «entro N», con o senza
cambio, per classe e periodo dell'anno); oltre si va solo se la persona lo chiede, per quella
sessione. Dove la classe non ha un livello adatto (livello 0, o una classe prima della mappa)
Calliope lo dice e propone un argomento della classe (`argomenti_adatti`). Ciò che la persona
dice di «a che punto siete» stringe o sposta il limite dentro l'anno (`con_punto`). Le domande
aperte delle interrogazioni stanno in `interrogazioni.yaml` (`domande_aperte`).
"""

from __future__ import annotations

import dataclasses
import datetime
import functools
import pathlib

from ..modello import Classe

QUI = pathlib.Path(__file__).resolve().parent
FILE_MATERIE = ("matematica", "italiano", "scienze")
TRAGUARDI = ("fine_terza_primaria", "fine_quinta_primaria", "fine_primaria",
             "fine_terza_secondaria")
TIPI = ("obiettivo", "competenza", "conoscenza", "traguardo")
PERIODI = ("inizio", "fine")


@functools.lru_cache(maxsize=1)
def carica() -> dict:
    """{"fonti": …, "matematica": …, "italiano": …, "scienze": …} dai file YAML."""
    import yaml
    out = {"fonti": yaml.safe_load((QUI / "fonti.yaml").read_text(encoding="utf-8"))}
    for nome in FILE_MATERIE:
        out[nome] = yaml.safe_load((QUI / f"{nome}.yaml").read_text(encoding="utf-8"))
    out["interrogazioni"] = yaml.safe_load(
        (QUI / "interrogazioni.yaml").read_text(encoding="utf-8"))
    return out


def anno_scolastico(data: datetime.date | None = None) -> int:
    """L'anno in cui comincia l'anno scolastico di quella data: 12/10/2026 → 2026, 01/03/2027 →
    2026. Da settembre a agosto (in estate vale la classe appena finita)."""
    d = data or datetime.date.today()
    return d.year if d.month >= 9 else d.year - 1


def periodo(data: datetime.date | None = None) -> str:
    """«inizio» (settembre–gennaio), «fine» (febbraio–giugno), «estate» (luglio e agosto)."""
    d = data or datetime.date.today()
    per = carica()["fonti"]["periodi"]
    for nome in ("inizio", "fine", "estate"):
        if d.month in per[nome]:
            return nome
    return "inizio"


def indicazioni_per(classe: Classe, anno: int, materia: str = "") -> str | None:
    """Quali Indicazioni valgono per `classe` nell'anno scolastico che comincia in `anno`:
    «2025» (DM 221/2025), «2012» (DM 254/2012), None per le superiori (fuori dal primo ciclo).
    Testo ufficiale (DM 221/2025, art. 1 c. 2 e art. 5): le nuove dalle classi prime del
    2026/27, le classi già avviate restano sulle vecchie fino alla fine del loro corso; la terza
    primaria del 2027/28 anticipa le nuove solo per storia."""
    val = carica()["fonti"]["validita"]
    grado = {"elementari": "primaria", "medie": "secondaria_primo_grado"}.get(classe.scuola)
    if grado is None:
        return None
    for ecc in val.get("eccezioni") or ():
        if (ecc["materia"] == materia and ecc["classe"] == str(classe)
                and int(ecc["anno"]) == int(anno)):
            return str(ecc["indicazioni"])
    prima = int(anno) - (classe.anno - 1)          # l'anno della sua classe prima
    return "2025" if prima >= int(val[grado]["nuove_dalla_prima_del"]) else "2012"


def obiettivi(file_materia: str, argomento: str, indicazioni: str | None = None) -> list[dict]:
    """Gli obiettivi ufficiali che toccano l'argomento (di quelle Indicazioni, se date)."""
    return [o for o in carica()[file_materia].get("obiettivi") or ()
            if argomento in (o.get("argomenti") or ())
            and (indicazioni is None or str(o["indicazioni"]) == str(indicazioni))]


def voce(file_materia: str, argomento: str, classe: Classe, quando: str) -> dict | None:
    """La voce interpolata della mappa per argomento, classe e periodo («inizio», «fine»;
    l'estate vale come «fine»), con `obiettivi` e `perche` della classe; None se non c'è."""
    per_classe = ((carica()[file_materia].get("mappa") or {}).get(argomento) or {}).get(
        str(classe))
    if not per_classe:
        return None
    q = "fine" if quando == "estate" else quando
    if q not in per_classe:
        return None
    return dict(per_classe[q], obiettivi=list(per_classe.get("obiettivi") or ()),
                perche=str(per_classe.get("perche") or "").strip())


# ─────────────────────────── fase B: il limite degli esercizi ───────────────────────────

@dataclasses.dataclass(frozen=True)
class Limite:
    """Il limite di un argomento per una classe in un periodo dell'anno (dalla mappa)."""
    argomento: str
    classe: Classe
    periodo: str                       # inizio | fine (l'estate vale come fine)
    indicazioni: str | None            # «2012», «2025»
    livello: int                       # 0 = nessun livello adatto alla classe adesso
    entro: int | None = None           # il numero più grande, risultato compreso
    cambio: bool | None = None         # False: senza riporto o prestito; True: sempre; None: come capita
    livello_anno: int = 0              # il livello più alto dell'anno (inizio e fine)
    entro_anno: int | None = None
    esempio: str = ""
    perche: str = ""
    obiettivi: tuple = ()
    fonte: str = "indice"              # «indice» o «punto» (ciò che la persona ha detto)
    prima_classe: Classe | None = None  # da quale classe la mappa ha l'argomento

    @property
    def adatto(self) -> bool:
        return self.livello > 0


def _file_mappa(argomento: str) -> str | None:
    for nome in FILE_MATERIE:
        if argomento in (carica()[nome].get("mappa") or {}):
            return nome
    return None


def nell_indice(argomento: str) -> bool:
    """L'argomento ha una mappa nell'indice (matematica e italiano)?"""
    return _file_mappa(argomento) is not None


def _materia_di_file(nome: str, argomento: str) -> str:
    """La materia per `indicazioni_per` (le eccezioni sono per materia: storia)."""
    return "italiano" if nome == "italiano" else "matematica"


def livello_da_entro(argomento: str, entro: int) -> int:
    """Il livello del generatore più vicino a «entro N» (i livelli della matematica: entro 20,
    entro 100, oltre; per le tabelline e le divisioni il primo arriva a 50)."""
    piccolo = 50 if argomento in ("moltiplicazioni", "divisioni") else 20
    return 1 if entro <= piccolo else 2 if entro <= 100 else 3


def limite(argomento: str, classe: Classe | None, data: datetime.date | None = None
           ) -> Limite | None:
    """Il limite dell'indice per `argomento`, `classe` e la data (oggi). None se l'indice non
    lo copre: argomento senza mappa (logica, fisica, chimica), classe dopo l'ultima della mappa
    (l'argomento è già dietro), superiori. Una classe prima della mappa ha livello 0."""
    if classe is None:
        return None
    nome = _file_mappa(argomento)
    if nome is None:
        return None
    mappa = carica()[nome]["mappa"][argomento]
    classi = sorted((Classe.da_testo(k) for k in mappa), key=lambda c: c.indice)
    q = periodo(data)
    q = "fine" if q == "estate" else q
    ind = indicazioni_per(classe, anno_scolastico(data), _materia_di_file(nome, argomento))
    if classe.indice > classi[-1].indice:
        return None
    if classe.indice < classi[0].indice:
        return Limite(argomento, classe, q, ind, 0, prima_classe=classi[0],
                      perche=f"nell'indice comincia in {classi[0].detta()}")
    per_classe = mappa.get(str(classe))
    if per_classe is None:            # un buco nella mappa: vale la classe prima
        prima = max((c for c in classi if c.indice < classe.indice), key=lambda c: c.indice)
        per_classe = mappa[str(prima)]
    v = per_classe[q]
    entri = [x.get("entro") for x in (per_classe["inizio"], per_classe["fine"])
             if x.get("entro")]
    camb = v.get("cambio")
    return Limite(argomento, classe, q, ind, int(v.get("livello") or 0),
                  entro=v.get("entro"), cambio=(False if camb is False else None),
                  livello_anno=max(int(per_classe["inizio"].get("livello") or 0),
                                   int(per_classe["fine"].get("livello") or 0)),
                  entro_anno=max(entri) if entri else None, esempio=str(v.get("esempio") or ""),
                  perche=str(per_classe.get("perche") or "").strip(),
                  obiettivi=tuple(o["id"] for o in obiettivi(nome, argomento, ind)
                                  if o["id"] in (per_classe.get("obiettivi") or ())),
                  prima_classe=classi[0])


def con_punto(lim: Limite | None, punto: dict | None) -> Limite | None:
    """Il limite stretto o spostato da ciò che la persona ha detto («siamo alle addizioni col
    riporto entro il 100»), sempre dentro l'anno della classe: mai oltre il livello e l'«entro»
    più alti dell'anno, mai per un argomento che quella classe non fa."""
    if lim is None or not punto or punto.get("argomento") != lim.argomento:
        return lim
    if lim.livello_anno <= 0:
        return lim
    entro = punto.get("entro")
    livello = lim.livello
    if isinstance(entro, int) and entro > 0:
        if lim.entro_anno:
            entro = min(entro, lim.entro_anno)
        livello = max(1, min(lim.livello_anno, livello_da_entro(lim.argomento, entro)))
    else:
        entro = lim.entro
        livello = max(1, livello)
    cambio = punto.get("cambio") if isinstance(punto.get("cambio"), bool) else lim.cambio
    return dataclasses.replace(lim, livello=livello, entro=entro, cambio=cambio, fonte="punto")


def argomenti_adatti(argomenti_materia, classe: Classe | None,
                     data: datetime.date | None = None) -> list[str]:
    """Gli argomenti (di quelli dati) che l'indice ammette per la classe adesso: livello
    almeno 1, o fuori dall'indice (None)."""
    out = []
    for a in argomenti_materia:
        lim = limite(a, classe, data)
        if lim is None or lim.adatto:
            out.append(a)
    return out


def domande_aperte(argomento: str, classe: Classe | None) -> list[dict]:
    """Le domande aperte delle interrogazioni per argomento e classe (interrogazioni.yaml)."""
    out = []
    for d in carica()["interrogazioni"].get("domande") or ():
        if d.get("argomento") != argomento:
            continue
        da, a = (Classe.da_testo(x) for x in d.get("classi") or ("", ""))
        if classe is not None and da is not None and a is not None \
                and not da.indice <= classe.indice <= a.indice:
            continue
        out.append(dict(d))
    return out


def _controlla_interrogazioni(visti: dict, noti) -> list[str]:
    """La forma di interrogazioni.yaml: id unici, argomento noto, classi valide, domanda con
    «?», da 2 a 4 criteri, obiettivi che esistono e toccano l'argomento."""
    err: list[str] = []
    ids: set = set()
    for d in carica()["interrogazioni"].get("domande") or ():
        did = str(d.get("id") or "")
        if not did or did in ids:
            err.append(f"interrogazioni: id vuoto o ripetuto «{did}»")
        ids.add(did)
        arg = d.get("argomento")
        if arg not in noti:
            err.append(f"{did}: argomento sconosciuto «{arg}»")
        cl = d.get("classi") or ()
        if len(cl) != 2 or any(Classe.da_testo(x) is None for x in cl):
            err.append(f"{did}: classi «{cl}»")
        if not str(d.get("domanda") or "").strip().endswith("?"):
            err.append(f"{did}: la domanda non finisce con «?»")
        if not 2 <= len(d.get("criteri") or ()) <= 4:
            err.append(f"{did}: servono da 2 a 4 criteri")
        if not d.get("obiettivi"):
            err.append(f"{did}: nessun obiettivo ufficiale")
        for oid in d.get("obiettivi") or ():
            o = visti.get(oid)
            if o is None:
                err.append(f"{did}: obiettivo sconosciuto «{oid}»")
            elif arg not in (o.get("argomenti") or ()):
                err.append(f"{did}: l'obiettivo {oid} non tocca {arg}")
    return err


def controlla() -> list[str]:
    """Gli errori di forma dell'indice (per prova_programma): id unici, Indicazioni e traguardi
    noti, argomenti che esistono in calliope/esercizi, classi valide, livelli 0–3, obiettivi
    della mappa che esistono e toccano l'argomento, ogni argomento agganciato a un obiettivo."""
    from .. import argomenti as tutti_argomenti
    noti = tutti_argomenti()
    dati = carica()
    err: list[str] = []
    fonti = dati["fonti"].get("fonti") or {}
    for k in ("in2025", "in2012"):
        if k not in fonti or not str(fonti[k].get("letto") or ""):
            err.append(f"fonte {k} mancante o senza data di lettura")
    visti: dict[str, dict] = {}
    agganciati: set[str] = set()
    for nome in FILE_MATERIE:
        for o in dati[nome].get("obiettivi") or ():
            oid = str(o.get("id") or "")
            if not oid or oid in visti:
                err.append(f"{nome}: id vuoto o ripetuto «{oid}»")
            visti[oid] = o
            if str(o.get("indicazioni")) not in ("2012", "2025"):
                err.append(f"{oid}: indicazioni «{o.get('indicazioni')}»")
            elif not oid.startswith("in" + str(o["indicazioni"])):
                err.append(f"{oid}: l'id non dice le Indicazioni giuste")
            if o.get("traguardo") not in TRAGUARDI:
                err.append(f"{oid}: traguardo «{o.get('traguardo')}»")
            if o.get("tipo", "obiettivo") not in TIPI:
                err.append(f"{oid}: tipo «{o.get('tipo')}»")
            if len(str(o.get("citazione") or "").strip()) < 20:
                err.append(f"{oid}: citazione mancante o troppo corta")
            for a in o.get("argomenti") or ():
                if a not in noti:
                    err.append(f"{oid}: argomento sconosciuto «{a}»")
                agganciati.add(a)
            if not o.get("argomenti"):
                err.append(f"{oid}: nessun argomento")
        for arg, classi in (dati[nome].get("mappa") or {}).items():
            if arg not in noti:
                err.append(f"{nome}: mappa per un argomento sconosciuto «{arg}»")
                continue
            for cl, v in classi.items():
                if Classe.da_testo(cl) is None:
                    err.append(f"{arg}: classe «{cl}»")
                for q in PERIODI:
                    if q not in v:
                        err.append(f"{arg}/{cl}: manca «{q}»")
                        continue
                    liv = v[q].get("livello")
                    if not isinstance(liv, int) or not 0 <= liv <= 3:
                        err.append(f"{arg}/{cl}/{q}: livello «{liv}»")
                    if not isinstance(v[q].get("generatore_dentro"), bool):
                        err.append(f"{arg}/{cl}/{q}: generatore_dentro mancante")
                if not str(v.get("perche") or "").strip():
                    err.append(f"{arg}/{cl}: perche mancante")
                if not v.get("obiettivi"):
                    err.append(f"{arg}/{cl}: nessun obiettivo ufficiale")
                for oid in v.get("obiettivi") or ():
                    o = visti.get(oid)
                    if o is None:
                        err.append(f"{arg}/{cl}: obiettivo sconosciuto «{oid}»")
                    elif arg not in (o.get("argomenti") or ()):
                        err.append(f"{arg}/{cl}: l'obiettivo {oid} non tocca {arg}")
    err.extend(_controlla_interrogazioni(visti, noti))
    note = dati["scienze"].get("note") or {}
    for a in noti:
        if a not in agganciati and a not in note:
            err.append(f"argomento «{a}» senza obiettivi né nota")
    return err


__all__ = ["carica", "anno_scolastico", "periodo", "indicazioni_per", "obiettivi", "voce",
           "controlla", "Limite", "limite", "argomenti_adatti", "con_punto", "livello_da_entro",
           "domande_aperte", "nell_indice"]
