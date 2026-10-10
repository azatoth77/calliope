"""
L'uscita unica verso la voce (10/10/2026, passo 2 del § 8 di
docs/ricerche/2026-10-10-registro-eventi.md, § 3.2 e § 6).

    python prove/prova_uscita_unica.py

A secco, ~1 s:
- **AST**: fuori da `calliope/eventi/uscita.py` e `calliope/tts.py` nessuna chiamata a `say`,
  `say_cached`, `chime`, `suono`, `suono_ascolto`, `sintetizza`, `start_turn`, né `wait` sulla
  voce (`speaker`, `sp`, `voce`, `….speaker`), né `text_q.put` / `audio_q.put`; lo stream di
  Brain (`stream_reply`, `stream_continuation`) si legge solo in `Ciclo._rispondi` e
  `Ciclo._ricerca_promessa`, che mandano le frasi all'uscita. Il controllo trova un caso finto
  (contrario).
- **Atti**: ogni atto scritto nel codice (`Uscita.di`, `di_e_aspetta`, le frasi d'attesa,
  `Brain._marca`, `Ciclo._autore`) è nell'elenco chiuso `tipi.ATTI`, con una categoria; le
  categorie danno gli insiemi della misura e della proiezione (voluti = fuori dal contesto); ogni
  motivo `non_in_storia:<atto>` atteso è di un atto `fuori_storia`.
- **Turni**: un atto senza un turno aperto (turno 0 di una corsia nuova) o in un turno fermato
  ne apre uno; le parole di una risposta interrotta no; `di_e_aspetta` controlla il satellite.
- **Latenza**: `Uscita.di` non apre file né database (open e sqlite3 sorvegliati) e costa
  microsecondi.
"""
import ast
import builtins
import os
import sqlite3
import sys
import time
import types
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope.eventi import misura, proiezioni  # noqa: E402
from calliope.eventi.tipi import ATTI, ATTI_PASSO_1, CATEGORIE_ATTO, atti_di  # noqa: E402
from calliope.eventi.uscita import Uscita, per_voce  # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
PERMESSI = {Path("calliope/eventi/uscita.py"), Path("calliope/tts.py")}
VIETATI = {"say", "say_cached", "chime", "suono", "suono_ascolto", "sintetizza", "start_turn"}
VOCI = {"speaker", "sp", "voce"}
STREAM = {"stream_reply", "stream_continuation"}
LETTORI_STREAM = {"_rispondi", "_ricerca_promessa"}

errori = 0


def verifica(nome, ok, info=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({info})" if info and not ok else ""),
          flush=True)


def _ricevitore(f: ast.Attribute) -> str:
    v = f.value
    if isinstance(v, ast.Name):
        return v.id
    if isinstance(v, ast.Attribute):
        return v.attr
    return ""


def chiamate_vietate(albero) -> list[tuple[int, str]]:
    """Le chiamate alla voce fuori dall'uscita unica: [(riga, testo)]."""
    out = []
    for n in ast.walk(albero):
        if not isinstance(n, ast.Call) or not isinstance(n.func, ast.Attribute):
            continue
        f = n.func
        r = _ricevitore(f)
        if f.attr in VIETATI:
            out.append((n.lineno, f"{r}.{f.attr}"))
        elif f.attr == "wait" and r in VOCI:
            out.append((n.lineno, f"{r}.wait"))
        elif f.attr == "put" and r in ("text_q", "audio_q"):
            out.append((n.lineno, f"{r}.put"))
    return out


def _funzioni(albero):
    for n in ast.walk(albero):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield n


def prova_ast():
    print("— una sola uscita verso la voce (AST)")
    trovate, stream_fuori = [], []
    for p in sorted((RADICE / "calliope").rglob("*.py")):
        rel = p.relative_to(RADICE)
        albero = ast.parse(p.read_text(encoding="utf-8"))
        if rel not in PERMESSI:
            trovate += [f"{rel}:{r} {t}" for r, t in chiamate_vietate(albero)]
        if rel == Path("calliope/brain.py"):
            continue
        for fn in _funzioni(albero):
            for n in ast.walk(fn):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                        and n.func.attr in STREAM and fn.name not in LETTORI_STREAM:
                    stream_fuori.append(f"{rel}:{n.lineno} {fn.name}")
    verifica("fuori da eventi/uscita.py e tts.py nessuno chiama la voce (say, say_cached, "
             "chime, suono, suono_ascolto, sintetizza, start_turn, wait, code della voce)",
             not trovate, "; ".join(trovate))
    verifica("lo stream di Brain si legge solo in Ciclo._rispondi e Ciclo._ricerca_promessa",
             not stream_fuori, "; ".join(stream_fuori))
    ciclo = (RADICE / "calliope" / "ciclo.py").read_text(encoding="utf-8")
    for nome in LETTORI_STREAM:
        corpo = ciclo[ciclo.index(f"    def {nome}("):]
        fine = corpo.find("\n    def ", 10)
        corpo = corpo if fine < 0 else corpo[:fine]
        verifica(f"…e {nome} manda le frasi all'uscita unica",
                 "_di_frase(" in corpo or ".di(" in corpo, nome)
    finto = ast.parse("def f(self, speaker, sp):\n    speaker.say('x')\n"
                      "    self.speaker.wait()\n    sp.start_turn()\n    self.done.wait()\n"
                      "    self.uscita.di('x', 'saluto')\n")
    verifica("contrario: il controllo trova le chiamate dirette (e non Event.wait né l'uscita)",
             [t for _r, t in chiamate_vietate(finto)] == ["speaker.say", "speaker.wait",
                                                          "sp.start_turn"],
             str(chiamate_vietate(finto)))


def _costanti(n) -> list[str]:
    """Le stringhe costanti di un argomento (anche dentro un `a if c else b` o un `or`)."""
    if isinstance(n, ast.Constant) and isinstance(n.value, str):
        return [n.value]
    if isinstance(n, ast.IfExp):
        return _costanti(n.body) + _costanti(n.orelse)
    if isinstance(n, ast.BoolOp):
        return [x for v in n.values for x in _costanti(v)]
    return []


def atti_nel_codice() -> dict[str, list[str]]:
    usati: dict[str, list[str]] = {}
    for p in sorted((RADICE / "calliope").rglob("*.py")):
        rel = p.relative_to(RADICE)
        albero = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(albero):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            nome = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(
                f, ast.Name) else ""
            arg = None
            if nome in ("di", "di_e_aspetta", "announce") and len(n.args) >= 2:
                arg = n.args[1]
            elif nome == "_marca" and len(n.args) >= 3:
                arg = n.args[2]
            for k in n.keywords:
                if k.arg == "atto" and nome in ("di", "di_e_aspetta", "announce", "_marca"):
                    arg = k.value
            if nome in ("di", "di_e_aspetta", "announce", "_marca") and arg is not None:
                for a in _costanti(arg):
                    usati.setdefault(a, []).append(f"{rel}:{n.lineno}")
        # Le tuple (autore, atto) restituite da Ciclo._autore
        for fn in _funzioni(albero):
            if fn.name != "_autore":
                continue
            for r in ast.walk(fn):
                if isinstance(r, ast.Return) and isinstance(r.value, ast.Tuple) \
                        and len(r.value.elts) == 2:
                    for a in _costanti(r.value.elts[1]):
                        usati.setdefault(a, []).append(f"{rel}:{r.lineno}")
    return usati


def prova_atti():
    print("— gli atti: elenco chiuso, ognuno con la sua categoria")
    usati = atti_nel_codice()
    fuori = {a: v for a, v in usati.items() if a not in ATTI}
    verifica("ogni atto scritto nel codice è nell'elenco chiuso (tipi.ATTI)", not fuori,
             str(fuori))
    verifica("…e ce ne sono (il controllo li trova: risposta, cortesia, chiusura, attesa_tool…)",
             {"risposta", "cortesia", "chiusura", "attesa_tool", "ripeti", "saluto_avvio",
              "attesa_stt"} <= set(usati), str(sorted(usati)))
    mai = sorted(set(ATTI) - set(usati) - ATTI_PASSO_1)
    verifica("nessun atto dell'elenco senza chi lo dice (tranne i nomi del passo 1, per il "
             "rigioco)", not mai, str(mai))
    verifica("ogni atto ha una categoria nota e la riga del § 1.1",
             all(c in CATEGORIE_ATTO and r for c, _a, r in ATTI.values()))
    verifica("i voluti sono fuori dal contesto del modello (proiezioni.ATTI_FUORI)",
             proiezioni.ATTI_FUORI == atti_di("voluto"))
    verifica("le categorie della misura vengono dall'elenco",
             misura.CONTENUTO == atti_di("risposta") and misura.VOLUTI == atti_di("voluto")
             and misura.REGISTRATI == atti_di("registrato")
             and misura.FUORI_STORIA == atti_di("fuori_storia"))
    verifica("non_in_storia atteso solo per gli atti fuori dalla storia di oggi",
             misura.atteso("non_in_storia:annuncio_agenda") and misura.atteso(
                 "non_in_storia:saluto") and not misura.atteso("non_in_storia:cortesia")
             and not misura.atteso("non_in_storia:sconosciuto"))
    verifica("una domanda di un atto ha sempre un motivo con un nome (mai «altro»)",
             all(misura.motivo_domanda("Va bene?", a, {}) not in (None, "altro")
                 for a in ATTI if a not in misura.CONTENUTO))


class VoceFinta:
    def __init__(self):
        self.detto, self.played, self.turno, self.interrupted = [], [], 0, False
        self.muto, self.remota, self.pronte = False, None, []

    def say(self, t):
        self.detto.append(t)
        if not self.interrupted:
            self.played.append(t)

    def say_cached(self, t):
        self.pronte.append(t)

    def start_turn(self):
        self.played, self.interrupted = [], False
        self.turno += 1

    def wait(self, *a):
        return True


def prova_turni():
    print("— i turni della voce: nessuna frase fuori turno")
    v = VoceFinta()
    u = per_voce(v)
    verifica("una uscita per voce (per_voce)", per_voce(v) is u and per_voce(VoceFinta()) is not u)
    visti = []
    u.osservatore = visti.append
    u.di("Ciao Ginevra.", "saluto")
    verifica("turno 0: l'atto apre un turno prima di andare alla voce",
             v.turno == 1 and v.detto == ["Ciao Ginevra."], f"{v.turno} {v.detto}")
    verifica("…e l'ombra sente la fine del pezzo di prima e la frase con atto e autore",
             visti[0][0] == "fine" and visti[1][0] == "frase"
             and visti[1][1]["atto"] == "saluto" and visti[1][1]["autore"] == "atto", str(visti))
    u.di("Vediamo.", "attesa_tool", pronta=True)
    verifica("una frase d'attesa va a say_cached, fuori dallo schermo",
             v.pronte == ["Vediamo."] and u.testo_scritto() == "Ciao Ginevra.",
             f"{v.pronte} {u.testo_scritto()!r}")
    v.interrupted = True
    u.di("Scusa, ho avuto un problema.", "errore")
    verifica("turno fermato: l'atto ne apre uno nuovo", v.turno == 2 and not v.interrupted)
    v.interrupted = True
    u.di("Continuo la risposta.", "risposta")
    verifica("contrario: la risposta interrotta resta nel suo turno", v.turno == 2)
    v.interrupted = False
    v.remota = object()
    v.played = []
    ok = u.di_e_aspetta("Va bene, ricominciamo da capo.", "chiusura")
    verifica("di_e_aspetta: un turno suo, e con il satellite controlla che l'abbia detta",
             ok and v.turno == 3, str(v.turno))
    v.say = lambda t: v.detto.append(t)         # il satellite la scarta
    log = []
    u.log = log.append
    ok = u.di_e_aspetta("A presto!", "chiusura")
    verifica("contrario: il satellite non la dice → False e la riga nel log",
             not ok and any("non ha detto" in r for r in log), str(log))
    u.di("Una frase con un atto inventato.", "atto_inventato")
    verifica("un atto fuori dall'elenco: la voce parla lo stesso e il log lo dice una volta",
             v.detto[-1].startswith("Una frase") and sum("fuori dall'elenco" in r
                                                         for r in log) == 1, str(log))
    u.di("Ancora.", "atto_inventato")
    verifica("…una volta sola", sum("fuori dall'elenco" in r for r in log) == 1)
    u.persona(scritto=True)
    u.di("Ecco la risposta scritta.", "risposta")
    verifica("frase scritta: canale «scritto», e sullo schermo solo le frasi di questa persona",
             visti[-1][1]["canale"] == "scritto"
             and u.testo_scritto() == "Ecco la risposta scritta.", str(visti[-1]))
    v.muto = True
    u.di("Muta.", "risposta")
    verifica("voce muta: canale «muta»", visti[-1][1]["canale"] == "muta")


def prova_latenza():
    print("— latenza: l'uscita non tocca il disco e costa microsecondi")
    v = VoceFinta()
    u = Uscita(v)
    u.osservatore = lambda item: None
    u.cervello = types.SimpleNamespace(last_tools=[{"nome": "ora_attuale"}])
    aperture = []
    vero_open, vero_connect = builtins.open, sqlite3.connect

    def open_sorvegliato(*a, **k):
        aperture.append(a[:1])
        return vero_open(*a, **k)

    def connect_sorvegliato(*a, **k):
        aperture.append(("sqlite3",) + a[:1])
        return vero_connect(*a, **k)
    builtins.open, sqlite3.connect = open_sorvegliato, connect_sorvegliato
    try:
        n = 5000
        t0 = time.perf_counter()
        for i in range(n):
            u.di("Una frase della risposta, di prova.", "risposta")
        us = (time.perf_counter() - t0) / n * 1e6
    finally:
        builtins.open, sqlite3.connect = vero_open, vero_connect
    verifica("Uscita.di non apre file né database", not aperture, str(aperture[:3]))
    print(f"    misura: Uscita.di {us:.1f} µs per frase (voce finta)")
    verifica("Uscita.di costa meno di 50 µs per frase", us < 50, f"{us:.1f} µs")


def main():
    prova_ast()
    prova_atti()
    prova_turni()
    prova_latenza()
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
