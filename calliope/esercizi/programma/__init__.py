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

Fase A (12/10): solo dati e lettura, nessun effetto sugli esercizi. Fase B (da fare): l'indice
come limite per il livello e per la salita di difficoltà, con la data nell'anno scolastico.
"""

from __future__ import annotations

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
    note = dati["scienze"].get("note") or {}
    for a in noti:
        if a not in agganciati and a not in note:
            err.append(f"argomento «{a}» senza obiettivi né nota")
    return err


__all__ = ["carica", "anno_scolastico", "periodo", "indicazioni_per", "obiettivi", "voce",
           "controlla"]
