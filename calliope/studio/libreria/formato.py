"""
Il formato dei contenuti della libreria dello Studio (31/10, issue #297, epic #251, decisione 0035):
un file JSON per contenuto in `contenuti/<materia>/<id>.json`, scritto e rivisto da noi (con
Claude), originale e AGPL. Qui solo le regole e il caricamento: il testo dei contenuti sta nei file,
mai nel codice.

**I tipi**
- `scheda`: un argomento, con `scheda` = {introduzione, sezioni [{titolo, testo}], ricorda [testo],
  esempi [{testo, calcolo?}], errori [testo], prova_tu [{domanda, risposta, calcolo?}]};
- `mazzo`: le carte di una scheda, con `scheda` (l'id) e `carte` [{domanda, risposta, sbagliata?,
  calcolo?}]: `sbagliata` è l'errore tipico, che il codice delle carte non deve dare per giusto;
- `miniapp` (la parte 2 della #297): `estensione` (la cartella del gioco), `tipo_app` (esplora,
  quiz, percorso), `schede` (gli argomenti che serve) e i `comandi` a voce, non vuoti.

**I metadati**, per tutti: `formato`, `id` (uguale al nome del file), `tipo`, `titolo`, `materia`
(dall'elenco dello Studio), `classe` {grado, anno, percorso, indirizzo}, `argomento`, `chiavi` (le
forme con cui un titolo di argomento lo nomina: `indice.py`), `prerequisiti` (id di altre schede,
senza cicli), `durata` (minuti), `comandi` (forme chiuse brevi), `licenza`, `revisione` (la data
dell'ultima revisione). Un mazzo eredita argomento, chiavi e prerequisiti dalla sua scheda se non
li scrive.

**I conti** (`calcolo`): {formula, dati, risultato}. Qui c'è solo l'elenco dei nomi; i conti li rifà
la prova di verità (`prove/prova_studio_libreria.py`) con una sua tabella, scritta a parte.

**Le regole del testo** (forma, non significato): una riga di testo semplice, niente caratteri di
controllo, niente link, niente markdown, niente emoji, lunghezze massime. Un file che non va si
salta con una riga nel registro (mai un errore all'avvio); la prova vuole zero errori.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

FORMATO = 1
SCHEDA, MAZZO, MINIAPP = "scheda", "mazzo", "miniapp"
TIPI = (SCHEDA, MAZZO, MINIAPP)
TIPI_APP = ("esplora", "quiz", "percorso")
LICENZA = "AGPL-3.0-or-later"
GRADI = ("primaria", "media", "superiore")
CARTELLA = Path(__file__).resolve().parent / "contenuti"

# I conti che la prova di verità sa rifare (i nomi; il conto è nella prova)
FORMULE = ("densita", "massa_da_densita", "volume_da_densita", "velocita", "spazio", "tempo",
           "moli", "massa_da_moli", "massa_molare", "conversione", "binario_in_decimale",
           "decimale_in_binario", "neutroni", "ph", "bilanciata", "elettroni_per_livello",
           "notazione_scientifica", "byte_in_bit", "esadecimale_in_decimale")

# Le lunghezze massime (caratteri)
ID_MAX = 60
TITOLO_MAX = 60
ARGOMENTO_MAX = 120
CHIAVE_MAX = 40
CHIAVE_PAROLE = 4
CHIAVI_MAX = 20
PREREQUISITI_MAX = 6
COMANDO_MAX = 30
COMANDO_PAROLE = 4
COMANDI_MAX = 24
INTRO_MAX = 500
SEZIONI_MAX = 6
SEZIONE_MAX = 900
RICORDA_MAX = 8
RIGA_MAX = 240
ESEMPI_MAX = 4
ESEMPIO_MAX = 500
ERRORI_MAX = 5
PROVA_TU_MAX = 5
CARTE_MIN, CARTE_MAX = 4, 20
DURATA_MIN, DURATA_MAX = 3, 60

_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CONTROLLO = re.compile(r"[\x00-\x1f\x7f ​-‏‪-‮⁦-⁩]")
_LINK = re.compile(r"(?i)(https?://|www\.|\b[\w-]+\.(?:it|com|org|net|eu|io|info)\b|@\w)")
# Markdown: enfasi, codice, titoli, elenchi all'inizio, link fra parentesi
_MARKDOWN = re.compile(r"(\*\*|__|`|^\s*#|^\s*[-*+]\s|\]\(|^\s*\d+\.\s)")
# Emoji e pittogrammi (i simboli delle unità e le frecce restano)
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")
# Una forma chiusa a voce: parole in minuscolo, lettere italiane, apostrofo e spazi
_COMANDO = re.compile(r"^[a-zàèéìòù']+(?: [a-zàèéìòù']+)*$")


class Errore(ValueError):
    """Un contenuto che non rispetta il formato: `str()` dice dove e perché."""


def _testo(dove: str, x, massimo: int, errori: list, vuoto: bool = False,
           a_capo: bool = False) -> str:
    """Un testo semplice; `a_capo`: una riga vuota separa i paragrafi (il testo di una sezione)."""
    if not isinstance(x, str):
        errori.append(f"{dove}: serve un testo")
        return ""
    t = x.strip()
    if not t and not vuoto:
        errori.append(f"{dove}: vuoto")
    if len(t) > massimo:
        errori.append(f"{dove}: più di {massimo} caratteri ({len(t)})")
    if _CONTROLLO.search(x.replace("\n", "") if a_capo else x):
        errori.append(f"{dove}: caratteri di controllo o di direzione")
    if _LINK.search(t):
        errori.append(f"{dove}: un link o un indirizzo")
    if _MARKDOWN.search(t):
        errori.append(f"{dove}: markdown")
    if _EMOJI.search(t):
        errori.append(f"{dove}: emoji")
    return t


def _elenco(dove: str, x, minimo: int, massimo: int, errori: list) -> list:
    if not isinstance(x, list):
        errori.append(f"{dove}: serve un elenco")
        return []
    if not minimo <= len(x) <= massimo:
        errori.append(f"{dove}: da {minimo} a {massimo} voci ({len(x)})")
    return x


def _calcolo(dove: str, c, errori: list):
    if c is None:
        return
    if not isinstance(c, dict) or set(c) - {"formula", "dati", "risultato"}:
        errori.append(f"{dove}: il calcolo è {{formula, dati, risultato}}")
        return
    if c.get("formula") not in FORMULE:
        errori.append(f"{dove}: formula sconosciuta «{c.get('formula')}»")
    if not isinstance(c.get("dati"), dict):
        errori.append(f"{dove}: i dati del calcolo sono un oggetto")
    r = c.get("risultato")
    if not isinstance(r, (int, float, str)) or isinstance(r, bool):
        errori.append(f"{dove}: il risultato è un numero o un testo breve")


def _comandi(dove: str, x, errori: list, obbligatori: bool) -> list[str]:
    cc = _elenco(dove, x, 1 if obbligatori else 0, COMANDI_MAX, errori)
    visti = set()
    for i, c in enumerate(cc):
        if not isinstance(c, str) or not _COMANDO.match(c) or len(c) > COMANDO_MAX \
                or len(c.split()) > COMANDO_PAROLE:
            errori.append(f"{dove}[{i}]: una forma chiusa in minuscolo, al più "
                          f"{COMANDO_PAROLE} parole")
        elif c in visti:
            errori.append(f"{dove}[{i}]: «{c}» due volte")
        visti.add(c)
    return [c for c in cc if isinstance(c, str)]


def valida(dati, nome: str | None = None) -> list[str]:
    """Gli errori di formato di un contenuto (vuoto se va). `nome`: il nome del file senza
    estensione, che deve essere l'id. Le regole fra contenuti (id che esistono, cicli) sono di
    `Libreria.controlla`."""
    e: list[str] = []
    if not isinstance(dati, dict):
        return ["il contenuto è un oggetto JSON"]
    if dati.get("formato") != FORMATO:
        e.append(f"formato: serve {FORMATO}")
    cid = dati.get("id")
    if not isinstance(cid, str) or not _ID.match(cid) or len(cid) > ID_MAX:
        e.append("id: minuscole, cifre e trattini")
    elif nome is not None and cid != nome:
        e.append(f"id: «{cid}» diverso dal nome del file «{nome}»")
    tipo = dati.get("tipo")
    if tipo not in TIPI:
        e.append(f"tipo: uno di {', '.join(TIPI)}")
    _testo("titolo", dati.get("titolo"), TITOLO_MAX, e)
    from ..servizio import MATERIE
    if dati.get("materia") not in MATERIE:
        e.append("materia: una dell'elenco dello Studio")
    cl = dati.get("classe")
    if not isinstance(cl, dict) or set(cl) != {"grado", "anno", "percorso", "indirizzo"}:
        e.append("classe: {grado, anno, percorso, indirizzo}")
    else:
        if cl["grado"] not in GRADI:
            e.append(f"classe.grado: uno di {', '.join(GRADI)}")
        if not isinstance(cl["anno"], int) or isinstance(cl["anno"], bool) or \
                not 1 <= cl["anno"] <= 5:
            e.append("classe.anno: da 1 a 5")
        _testo("classe.percorso", cl["percorso"], ARGOMENTO_MAX, e, vuoto=True)
        _testo("classe.indirizzo", cl["indirizzo"], ARGOMENTO_MAX, e, vuoto=True)
    eredita = tipo in (MAZZO, MINIAPP)
    if "argomento" in dati or not eredita:
        _testo("argomento", dati.get("argomento"), ARGOMENTO_MAX, e)
    if "chiavi" in dati or not eredita:
        ch = _elenco("chiavi", dati.get("chiavi"), 1, CHIAVI_MAX, e)
        for i, k in enumerate(ch):
            t = _testo(f"chiavi[{i}]", k, CHIAVE_MAX, e)
            if t and len(t.split()) > CHIAVE_PAROLE:
                e.append(f"chiavi[{i}]: al più {CHIAVE_PAROLE} parole")
    if "prerequisiti" in dati or not eredita:
        pr = _elenco("prerequisiti", dati.get("prerequisiti"), 0, PREREQUISITI_MAX, e)
        for i, p in enumerate(pr):
            if not isinstance(p, str) or not _ID.match(p):
                e.append(f"prerequisiti[{i}]: un id")
    d = dati.get("durata")
    if not isinstance(d, int) or isinstance(d, bool) or not DURATA_MIN <= d <= DURATA_MAX:
        e.append(f"durata: minuti interi da {DURATA_MIN} a {DURATA_MAX}")
    _comandi("comandi", dati.get("comandi"), e, obbligatori=tipo == MINIAPP)
    if dati.get("licenza") != LICENZA:
        e.append(f"licenza: {LICENZA}")
    rv = dati.get("revisione")
    try:
        if not isinstance(rv, str) or not _DATA.match(rv):
            raise ValueError
        datetime.date.fromisoformat(rv)
    except ValueError:
        e.append("revisione: una data AAAA-MM-GG")
    note = {"formato", "id", "tipo", "titolo", "materia", "classe", "argomento", "chiavi",
            "prerequisiti", "durata", "comandi", "licenza", "revisione"}
    if tipo == SCHEDA:
        _scheda(dati.get("scheda"), e)
        note.add("scheda")
    elif tipo == MAZZO:
        if not isinstance(dati.get("scheda"), str) or not _ID.match(dati["scheda"]):
            e.append("scheda: l'id della scheda del mazzo")
        _carte(dati.get("carte"), e)
        note.update({"scheda", "carte"})
    elif tipo == MINIAPP:
        if dati.get("tipo_app") not in TIPI_APP:
            e.append(f"tipo_app: uno di {', '.join(TIPI_APP)}")
        if not isinstance(dati.get("estensione"), str) or not _ID.match(dati["estensione"]):
            e.append("estensione: il nome della cartella del gioco")
        ss = _elenco("schede", dati.get("schede"), 1, PREREQUISITI_MAX, e)
        for i, s in enumerate(ss):
            if not isinstance(s, str) or not _ID.match(s):
                e.append(f"schede[{i}]: un id")
        note.update({"tipo_app", "estensione", "schede"})
    altre = set(dati) - note
    if altre:
        e.append("chiavi sconosciute: " + ", ".join(sorted(altre)))
    return e


def _scheda(s, e: list):
    if not isinstance(s, dict):
        e.append("scheda: un oggetto")
        return
    altre = set(s) - {"introduzione", "sezioni", "ricorda", "esempi", "errori", "prova_tu"}
    if altre:
        e.append("scheda: chiavi sconosciute " + ", ".join(sorted(altre)))
    _testo("scheda.introduzione", s.get("introduzione"), INTRO_MAX, e)
    for i, x in enumerate(_elenco("scheda.sezioni", s.get("sezioni"), 1, SEZIONI_MAX, e)):
        if not isinstance(x, dict) or set(x) != {"titolo", "testo"}:
            e.append(f"scheda.sezioni[{i}]: {{titolo, testo}}")
            continue
        _testo(f"scheda.sezioni[{i}].titolo", x["titolo"], TITOLO_MAX, e)
        _testo(f"scheda.sezioni[{i}].testo", x["testo"], SEZIONE_MAX, e, a_capo=True)
    for i, x in enumerate(_elenco("scheda.ricorda", s.get("ricorda"), 1, RICORDA_MAX, e)):
        _testo(f"scheda.ricorda[{i}]", x, RIGA_MAX, e)
    for i, x in enumerate(_elenco("scheda.esempi", s.get("esempi", []), 0, ESEMPI_MAX, e)):
        if not isinstance(x, dict) or not {"testo"} <= set(x) <= {"testo", "calcolo"}:
            e.append(f"scheda.esempi[{i}]: {{testo, calcolo?}}")
            continue
        _testo(f"scheda.esempi[{i}].testo", x["testo"], ESEMPIO_MAX, e)
        _calcolo(f"scheda.esempi[{i}].calcolo", x.get("calcolo"), e)
    for i, x in enumerate(_elenco("scheda.errori", s.get("errori", []), 0, ERRORI_MAX, e)):
        _testo(f"scheda.errori[{i}]", x, RIGA_MAX, e)
    for i, x in enumerate(_elenco("scheda.prova_tu", s.get("prova_tu", []), 0, PROVA_TU_MAX, e)):
        if not isinstance(x, dict) or not {"domanda", "risposta"} <= set(x) <= {
                "domanda", "risposta", "calcolo"}:
            e.append(f"scheda.prova_tu[{i}]: {{domanda, risposta, calcolo?}}")
            continue
        _testo(f"scheda.prova_tu[{i}].domanda", x["domanda"], RIGA_MAX, e)
        _testo(f"scheda.prova_tu[{i}].risposta", x["risposta"], RIGA_MAX, e)
        _calcolo(f"scheda.prova_tu[{i}].calcolo", x.get("calcolo"), e)


def _carte(cc, e: list):
    from .. import carte as C
    visti = set()
    for i, c in enumerate(_elenco("carte", cc, CARTE_MIN, CARTE_MAX, e)):
        if not isinstance(c, dict) or not {"domanda", "risposta"} <= set(c) <= {
                "domanda", "risposta", "sbagliata", "calcolo"}:
            e.append(f"carte[{i}]: {{domanda, risposta, sbagliata?, calcolo?}}")
            continue
        d = _testo(f"carte[{i}].domanda", c["domanda"], C.DOMANDA_MAX, e)
        _testo(f"carte[{i}].risposta", c["risposta"], C.RISPOSTA_MAX, e)
        if "sbagliata" in c:
            _testo(f"carte[{i}].sbagliata", c["sbagliata"], C.RISPOSTA_MAX, e)
        _calcolo(f"carte[{i}].calcolo", c.get("calcolo"), e)
        k = " ".join(C.normale(d))
        if k in visti:
            e.append(f"carte[{i}]: la stessa domanda due volte")
        visti.add(k)


def leggi_file(percorso: Path) -> tuple[dict | None, list[str]]:
    """(contenuto, errori) di un file: il JSON e il suo formato."""
    try:
        dati = json.loads(Path(percorso).read_text("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as ex:
        return None, [f"non si legge: {type(ex).__name__}"]
    errori = valida(dati, Path(percorso).stem)
    return (dati if not errori else None), errori
