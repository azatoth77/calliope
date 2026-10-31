"""
La libreria caricata, l'indice per argomento e la scelta del codice (31/10, issue #297, epic #251,
decisione 0035 punto 46).

**L'indice** lega un titolo di argomento (un dato non fidato: viene dalle pagine e dalla conferma
della persona) alle schede della libreria (dati fidati). Le parole del titolo si riducono a radici
(`parole`): minuscole, senza accenti, senza articoli né parole di servizio («capitolo»,
«esercizi»), con le vocali finali tolte («atomo» e «atomi», «reazione» e «reazioni» sono la stessa
radice). Una chiave della scheda vale se **tutte** le sue radici stanno nel titolo; il punteggio è
la somma delle parole delle chiavi trovate. È una regola sul testo che sceglie fra contenuti
fidati, senza azioni, con un effetto che la persona vede e decide (principio 10): i casi contrari
sono nelle prove. La materia filtra (`MATERIE_VICINE`).

**La scelta** (`scegli`) la fa il codice, mai il modello: per ogni argomento del piano le schede
trovate e i loro mazzi (in parte 2 le mini-app), al più `PER_ARGOMENTO` schede per argomento e
`PROPOSTE_MAX` proposte. La padronanza conta solo se chi chiama la passa («mostrata»): gli argomenti
sotto l'obiettivo vengono prima, dal più debole, e portano le schede dei loro prerequisiti. Senza
padronanza l'ordine è quello degli argomenti (un ordine diverso direbbe la padronanza nascosta).
"""

from __future__ import annotations

import unicodedata
import re
from pathlib import Path

from . import formato as F

# Le materie dello Studio che valgono per una materia della libreria: la stessa, «Scienze» per le
# scienze, «Tecnologia» per l'informatica. Una materia fuori dall'elenco dello Studio («altro»)
# vale per tutte
MATERIE_VICINE = {
    "Chimica": ("Chimica", "Scienze"),
    "Fisica": ("Fisica", "Scienze"),
    "Biologia": ("Biologia", "Scienze"),
    "Informatica": ("Informatica", "Tecnologia"),
}
PER_ARGOMENTO = 2
PROPOSTE_MAX = 12
# I motivi di una proposta (la pagina li dice in parole)
ARGOMENTO, LACUNA, PREREQUISITO = "argomento", "lacuna", "prerequisito"

# Articoli, preposizioni, congiunzioni e parole di servizio dei titoli: non contano
_VUOTE = frozenset("""
il lo la i gli le l un uno una un' di del dello della dei degli delle d a al allo alla ai agli
alle ad da dal dallo dalla dai dagli dalle in nel nello nella nei negli nelle con col coi su sul
sullo sulla sui sugli sulle per tra fra e ed o od che come cosa cos sono e' è non ne si
capitolo capitoli cap paragrafo pagina pagine pag p modulo lezione lezioni parte esercizi
esercizio ripasso introduzione verifica generale generali argomento argomenti
""".split())


def radice(parola: str) -> str:
    """La radice di una parola già normalizzata: le vocali finali tolte, finché restano almeno
    tre lettere («atomo» → «atom», «mole» e «moli» → «mol», «binario» e «binari» →
    «binar»); i numeri restano."""
    if parola.isdigit():
        return parola
    r = parola
    while len(r) > 3 and r[-1] in "aeiou":
        r = r[:-1]
    return r


def parole(testo) -> list[str]:
    """Le radici delle parole che contano di un testo, nell'ordine."""
    t = unicodedata.normalize("NFKD", str(testo or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [radice(w) for w in re.findall(r"[a-z0-9]+", t) if w not in _VUOTE]


def materia_vale(materia_libreria: str, materia_verifica) -> bool:
    """Una scheda di `materia_libreria` vale per una verifica di `materia_verifica`."""
    from ..servizio import MATERIE
    mv = str(materia_verifica or "").strip()
    nota = next((m for m in MATERIE if m.lower() == mv.lower()), None)
    if nota is None:
        return True
    return nota in MATERIE_VICINE.get(materia_libreria, (materia_libreria,))


class Libreria:
    """I contenuti caricati e controllati. `contenuti`: id → dict (coi metadati ereditati del
    mazzo già scritti), `errori`: «file: errore» dei file saltati."""

    def __init__(self, contenuti: dict[str, dict] | None = None, errori: list[str] | None = None,
                 app: dict | None = None):
        self.contenuti = dict(contenuti or {})
        self.errori = list(errori or [])
        # Le mini-app caricate (parte 2 della #297, `miniapp.py`): id del contenuto → MiniApp
        self.app = dict(app or {})
        self._chiavi: dict[str, list[list[str]]] = {}
        self._indicizza()

    # ── caricamento ──
    @classmethod
    def carica(cls, cartella=None, log=None, cartella_app=None) -> "Libreria":
        """Tutti i file `*.json` sotto `cartella` (di serie i contenuti nel repository). Un file
        che non va si salta con una riga nel registro (`log`), come un contenuto che punta a un id
        che non c'è o un ciclo di prerequisiti. Le mini-app (`tipo: miniapp`) si caricano da
        `cartella_app` (di serie `miniapp/`, `miniapp.carica`): una che non va resta fuori."""
        base = Path(cartella) if cartella else F.CARTELLA
        contenuti, errori = {}, []
        for p in sorted(base.rglob("*.json")) if base.is_dir() else ():
            dati, ee = F.leggi_file(p)
            nome = p.relative_to(base).as_posix()
            if ee:
                errori.extend(f"{nome}: {x}" for x in ee)
                continue
            if dati["id"] in contenuti:
                errori.append(f"{nome}: id «{dati['id']}» già usato")
                continue
            contenuti[dati["id"]] = dati
        buoni, errori = cls.controlla(contenuti, errori)
        from . import miniapp as MA
        app, nomi = {}, {}
        for k, v in sorted(buoni.items()):
            if v["tipo"] != F.MINIAPP:
                continue
            a, ee = MA.carica(v["estensione"], v["comandi"],
                              Path(cartella_app) if cartella_app else None)
            if a is not None and a.nome in nomi:
                ee = [f"la cartella «{v['estensione']}» è già di «{nomi[a.nome]}»"]
            if ee:
                errori.extend(f"{k} (miniapp/{v['estensione']}): {x}" for x in ee)
                del buoni[k]
                continue
            app[k], nomi[a.nome] = a, k
        lib = cls(buoni, errori, app)
        if log and lib.errori:
            log(f"   [STUDIO] libreria: {len(lib.errori)} errori, quei contenuti restano fuori "
                f"(il primo: {lib.errori[0]})")
        return lib

    @staticmethod
    def controlla(contenuti: dict, errori: list) -> tuple[dict, list]:
        """Le regole fra contenuti: la scheda di un mazzo c'è ed è una scheda (il mazzo ne eredita
        argomento, chiavi e prerequisiti), le schede di una mini-app ci sono, i prerequisiti sono
        schede e non fanno cicli. Chi non va esce, con l'errore."""
        out = {k: dict(v) for k, v in contenuti.items()}
        errori = list(errori)
        schede = {k for k, v in out.items() if v["tipo"] == F.SCHEDA}
        for k, v in list(out.items()):
            if v["tipo"] == F.MAZZO:
                s = out.get(v["scheda"])
                if v["scheda"] not in schede:
                    errori.append(f"{k}: la scheda «{v['scheda']}» non c'è")
                    del out[k]
                    continue
                if v["materia"] != s["materia"]:
                    errori.append(f"{k}: materia diversa dalla sua scheda")
                    del out[k]
                    continue
                for campo in ("argomento", "chiavi", "prerequisiti"):
                    v.setdefault(campo, s[campo])
            elif v["tipo"] == F.MINIAPP:
                manca = [s for s in v["schede"] if s not in schede]
                if manca:
                    errori.append(f"{k}: schede che non ci sono: {', '.join(manca)}")
                    del out[k]
                    continue
                v.setdefault("chiavi", [])
                v.setdefault("argomento", out[v["schede"][0]]["argomento"])
                v.setdefault("prerequisiti", [])
        for k, v in list(out.items()):
            manca = [p for p in v["prerequisiti"] if p not in schede or p == k]
            if manca:
                errori.append(f"{k}: prerequisiti che non sono schede: {', '.join(manca)}")
                del out[k]
        # I cicli fra le schede (A vuole B, B vuole A): escono tutte quelle del ciclo
        stato: dict[str, int] = {}

        def visita(k, strada):
            if stato.get(k) == 2 or k not in out:
                return False
            if stato.get(k) == 1:
                return True
            stato[k] = 1
            ciclo = any(visita(p, strada + [k]) for p in out[k]["prerequisiti"])
            stato[k] = 2
            if ciclo:
                stato[k] = 3
            return ciclo

        for k in sorted(out):
            if out[k]["tipo"] == F.SCHEDA:
                visita(k, [])
        for k in [k for k, s in stato.items() if s == 3]:
            errori.append(f"{k}: un ciclo di prerequisiti")
            out.pop(k, None)
        # Un mazzo o una mini-app di una scheda tolta escono con lei
        for k, v in list(out.items()):
            dipende = [v["scheda"]] if v["tipo"] == F.MAZZO else v.get("schede", [])
            if any(d not in out for d in dipende):
                errori.append(f"{k}: la sua scheda è uscita")
                del out[k]
        return out, errori

    def _indicizza(self):
        self._chiavi = {k: [ps for ps in (parole(c) for c in v.get("chiavi") or ()) if ps]
                        for k, v in self.contenuti.items() if v["tipo"] == F.SCHEDA}

    # ── letture ──
    def __len__(self):
        return len(self.contenuti)

    def get(self, cid) -> dict | None:
        return self.contenuti.get(str(cid)) if isinstance(cid, str) else None

    def schede(self) -> list[dict]:
        return [v for v in self.contenuti.values() if v["tipo"] == F.SCHEDA]

    def materie(self) -> list[str]:
        return sorted({v["materia"] for v in self.contenuti.values()})

    def di_scheda(self, sid: str) -> list[dict]:
        """I mazzi e le mini-app di una scheda, nell'ordine dei tipi e poi degli id."""
        out = [v for v in self.contenuti.values()
               if (v["tipo"] == F.MAZZO and v["scheda"] == sid)
               or (v["tipo"] == F.MINIAPP and sid in v["schede"])]
        return sorted(out, key=lambda v: (F.TIPI.index(v["tipo"]), v["id"]))

    def trova(self, titolo, materia=None) -> list[tuple[str, int]]:
        """Le schede che un titolo di argomento nomina, (id, punteggio) dal punteggio più alto
        (a pari punteggio l'id). Vuoto se nessuna chiave c'è per intero."""
        ps = set(parole(titolo))
        if not ps:
            return []
        out = []
        for sid, chiavi in self._chiavi.items():
            if materia is not None and not materia_vale(self.contenuti[sid]["materia"], materia):
                continue
            punti = sum(len(c) for c in chiavi if set(c) <= ps)
            if punti:
                out.append((sid, punti))
        out.sort(key=lambda x: (-x[1], x[0]))
        return out


def scegli(lib: Libreria, argomenti: list[dict], materia, padronanza: dict | None = None,
           obiettivo: int = 75) -> list[dict]:
    """Le proposte della libreria per una verifica, scelte dal codice.

    `argomenti`: [{id, numero, titolo}] (il numero è quello detto a voce; per l'argomento generale
    della verifica id e numero None); `padronanza`: {id dell'argomento: valore o None}, solo se
    «mostrata» (None altrimenti). Ogni proposta: {contenuto, tipo, titolo, durata, materia,
    argomento, numero, motivo, scheda}."""
    ordine = list(argomenti)
    lacune: set = set()
    if padronanza is not None:
        def chiave(a):
            v = padronanza.get(a["id"])
            if v is None:
                return (1, 0.0)
            return (0, float(v)) if v < obiettivo else (2, 0.0)
        ordine.sort(key=chiave)
        lacune = {a["id"] for a in ordine
                  if padronanza.get(a["id"]) is not None and padronanza[a["id"]] < obiettivo}
    out: list[dict] = []
    visti: set = set()

    def metti(v: dict, a: dict, motivo: str, scheda: str):
        if v["id"] in visti or len(out) >= PROPOSTE_MAX:
            return
        visti.add(v["id"])
        out.append({"contenuto": v["id"], "tipo": v["tipo"], "titolo": v["titolo"],
                    "durata": v["durata"], "materia": v["materia"], "argomento": a["id"],
                    "numero": a["numero"], "motivo": motivo, "scheda": scheda})

    for a in ordine:
        for sid, _p in lib.trova(a["titolo"], materia)[:PER_ARGOMENTO]:
            motivo = LACUNA if a["id"] in lacune else ARGOMENTO
            metti(lib.contenuti[sid], a, motivo, sid)
            for v in lib.di_scheda(sid):
                metti(v, a, motivo, sid)
            if a["id"] in lacune:
                for p in lib.contenuti[sid]["prerequisiti"]:
                    if p in lib.contenuti:
                        metti(lib.contenuti[p], a, PREREQUISITO, p)
    return out
