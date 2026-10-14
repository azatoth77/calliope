"""Banco della temperatura e del presence_penalty dell'agente (12/10/2026 sera, flusso
dell'agente a fasi, parte 1; ricerca docs/ricerche/2026-10-12-flusso-agente-fasi.md § 4.1 e
§ 5.3, domanda 6 accettata da chi amministra; area agenti-estensioni).

La scheda di Qwen3.6-35B-A3B consiglia, con il ragionamento acceso sul codice, temperatura
**0,6** e presence_penalty **0**; da noi `agenti_temperatura` è **0,4** e
`agenti_presence_penalty` 0 per «codice» e 0,5 per «estensione» (misurato l'11/10 su una sola
passata, prove/manuali/misura_presence_penalty.py). Qui si confrontano **lavori interi**, non
una passata: per ogni combinazione di temperatura e presence_penalty, tre casi veri riscritti
con nomi di fantasia, ripetuti:

1. **porte** (gioco, correzione): il gioco delle porte di Borgofiore con il genere di difetto
   del 12/10 (allora logica.js restituiva l'esito annidato e gioco.js lo leggeva al primo
   livello; dal 14/10, con la macchina a stati e senza gioco.js, l'esito mostra il mostro della
   porta accanto), e la segnalazione della persona. Accettazione: un test nascosto che apre il
   gioco nel DOM finto (apriGioco), tocca «2 giocatori» e la prima porta e legge «Fantasmino» e
   «+3 punti».
2. **convertitore** (estensione nuova): un convertitore di distanze con un valore di due parole
   con l'accento («unità astronomiche»). Accettazione: test nascosto con CalliopeFinta, cinque
   esempi dato → risultato (10 miglia in chilometri, un miglio nautico in metri, due unità
   astronomiche in chilometri, 12 pollici in piedi, un'unità che non c'è).
3. **programma** (Python): «rinomina le foto per data» (c01 di prove/prova_lavori.py, con il
   suo test nascosto).

Misure per lavoro: riuscito (consegna «fatto» e accettazione verde), passate, token (e di
ragionamento), minuti, giri a vuoto (passate fermate per ragionamento ripetuto, passate senza
file né test nuovi), test dell'agente, accettazione verde, e per la correzione l'esito della
riproduzione (agenti/riproduzione.py) e le regole scattate. Alla fine una tabella per
combinazione e caso, e `riepilogo.json` nella cartella d'uscita.

**Giri** (`--giri N`, 13/10; predefinito 1 = un lavoro solo, come prima). Con N > 1 lo stesso
budget di un lavoro si divide in N giri uguali: `agenti_max_passi` (24) diventa
round(24 / N) passate per giro (24 / 2 = 12; il banco stampa il conto e il totale), il tetto di
tempo `--minuti` diventa minuti / N per giro, e con esso il tetto dei token (token al minuto
per i minuti del giro; anche `agenti_max_token`, se acceso, diviso per N). Così un lavoro a
giri ha lo stesso budget totale di passate, tempo e token di un lavoro con un giro solo, e il
confronto misura solo l'effetto della ripartenza. Al tetto di un giro il lavoro si ferma alla
**tappa** della modalità sviluppo (`lav.tappe`, `_tappa` in agenti/ciclo.py: il contesto
resta, compattato, e i file vanno nella cartella) e il banco chiama da sé `Lavori.continua`
senza nota («Hai un altro giro di lavoro… Riprendi da dove eri…»); all'ultimo giro le tappe
si spengono e il tetto chiude il lavoro come oggi («limite»). Nessuna modifica a Calliope:
`lav.tappe` è un attributo del lavoro, qui acceso dal banco. Misure in più per lavoro: giri
fatti, passate per giro, l'accettazione nascosta rifatta a ogni tappa sui file del giro, il
giro dell'accettazione verde e quello della consegna, e «sbloccato» (alla prima tappa
accettazione rossa, poi consegna «fatto» o accettazione verde in un giro dopo).

**Sulla DGX quando è libera** (nessun lavoro dell'agente in corso: usa lo stesso vLLM e il
container della sandbox), dalla cartella dei dati, con l'interprete di Calliope. Non cambia la
configurazione di nessuno (i valori si cambiano solo in memoria), i file restano nella cartella
d'uscita:

    cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale) \\
        && $V/.venv/bin/python $V/prove/manuali/banco_temperatura.py \\
           [--temperature 0.4,0.6] [--presence 0,0.5] [--ripetizioni 2] \\
           [--casi porte,convertitore,programma] [--minuti 20] [--giri 1] \\
           [--uscita ~/banco-temperatura]

A secco (nessun modello, anche sul portatile: il docker finto e il Node della macchina), per
controllare il banco stesso: ogni accettazione fallisce sul punto di partenza e passa sulla
soluzione di riferimento; e i giri con un agente finto (prove/ollama_finto.py): il giro 1 si
ferma alla tappa, il banco chiama continua e il giro 2 consegna; senza consegna l'ultimo giro
chiude con «limite»; con un giro solo il tetto chiude come prima; la consegna al tetto con il
servizio vero (13/10 sera): il codice giusto all'ultima passata, senza consegna, si chiude «fatto»
con gli esempi verdi; il contrario «limite» con gli esempi rossi; dal 14/10 le porte corrette
con il test del disegno senza consegna, «fatto» con la riproduzione al posto degli esempi, e il
contrario senza il test «limite».

    python prove/manuali/banco_temperatura.py --secco

**Valori della Config e analisi prima del codice** (13/10, flusso a fasi parte 2). In
`--temperature` e `--presence` la parola `config` prende i valori della Config (per
presence_penalty quelli per tipo di lavoro, `agenti_presence_penalty`): così il banco misura
l'installazione com'è. `--accettazione config|si|no` (predefinito `config`) lascia, accende o
spegne l'analisi prima del codice (`agenti_accettazione`, calliope/agenti/accettazione.py):
le domande prima di cominciare le risponde il banco da sé («Decidi tu, con la scelta più
comune.») e le conta; la riga ha `domande` e `analisi` (esempi di accettazione dell'agente,
verdi o rossi, secondi della passata). Gli esempi dell'agente sono un'altra cosa
dall'accettazione nascosta del banco, che resta il criterio di «riuscito».

**Esempi rieseguiti alla fine** (13/10 sera, L7: l'agente ha sistemato il convertitore
all'ultima delle 24 passate, il riepilogo diceva «esempi 7 rossi» e a mano passavano tutti).
Lo stato «esempi» della riga (`esempi_finali`) è quello rieseguito dal banco sui file finali del
lavoro, in una sandbox nuova, con il file degli esempi preso dalla sandbox del lavoro (è in sola
lettura e non va nella cartella del risultato). La riga ha anche `consegna_al_tetto`: il tetto
toccato quando Calliope ha chiuso il lavoro da sé con gli esempi verdi (agenti/ciclo.py).

Durata: un lavoro dura 3–15 minuti; con i valori predefiniti 2 × 2 × 2 × 3 = 24 lavori, da 2 a
4 ore. Per una prima idea: --ripetizioni 1 --casi porte,convertitore (8 lavori).
"""

import argparse
import datetime
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))
sys.path.insert(0, str(RADICE / "prove"))

# ═══════════════════════════ i casi ═══════════════════════════

# 1. Le porte di Borgofiore (il difetto vero del 12/10, prove/prova_fasi_agente.py)
def _porte():
    import prova_fasi_agente as F
    return F


PROBLEMA_PORTE = ("toccando la prima porta si vede la caramella e «Nessun punto!», ma i punti "
                  "salgono di tre: il mostro che si vede non è quello della porta")
COMPITO_PORTE = ("Il gioco «Le porte di Borgofiore» da 2 a 4 giocatori: si sceglie in quanti, "
                 "poi a turno ogni giocatore tocca una porta; dietro c'è un mostro che vale dei punti "
                 "(il Fantasmino 3, il Pipistrello 2) o una caramella che non ne vale. Dopo ogni "
                 "porta si vede cosa c'era dietro, con il nome, e i punti presi («+3 punti!» o "
                 "«Nessun punto!»), e il punteggio dei giocatori.")
ACCETTAZIONE_PORTE = """const { test } = require("node:test");
const assert = require("node:assert");
test("ACC porte: toccando la prima porta si vedono il mostro e i suoi punti", async () => {
  const g = await apriGioco({ seme: 3 });
  await g.tocca("2 giocatori");
  await g.tocca("Porta 1");
  assert.match(g.testo(), /Fantasmino/);
  assert.match(g.testo(), /\\+\\s*3 punti/);
});
"""

# 2. Il convertitore (estensione nuova, un valore di due parole con l'accento)
COMPITO_CONVERTITORE = (
    "Un'estensione «Convertitore di distanze» (nome convertitore_distanze): converte un valore "
    "tra unità di lunghezza: metri, chilometri, miglia, miglia nautiche, piedi, pollici e unità "
    "astronomiche, con i nomi in italiano anche al singolare («miglio nautico», «unità "
    "astronomica»), maiuscole o minuscole. Input del manifesto: valore (number), da (string), "
    "a (string). Restituisce da_dire con il risultato in italiano (virgola decimale, al più "
    "quattro cifre decimali) e «risultato» con il numero. Se un'unità non la conosce, "
    "«trovato»: false e da_dire lo dice. Niente rete.")
ACCETTAZIONE_CONVERTITORE = '''import unittest
from calliope_estensione import CalliopeFinta
from estensione import esegui


def conv(valore, da, a):
    return esegui({"valore": valore, "da": da, "a": a}, CalliopeFinta())


class Accettazione(unittest.TestCase):
    def test_acc_miglia_in_chilometri(self):
        self.assertAlmostEqual(conv(10, "miglia", "chilometri")["risultato"], 16.0934, places=2)

    def test_acc_miglio_nautico_in_metri(self):
        self.assertAlmostEqual(conv(1, "miglio nautico", "metri")["risultato"], 1852, places=1)

    def test_acc_unita_astronomiche(self):
        r = conv(2, "Unità astronomiche", "chilometri")["risultato"]
        self.assertAlmostEqual(r / 299195741.4, 1, places=5)

    def test_acc_pollici_in_piedi(self):
        self.assertAlmostEqual(conv(12, "pollici", "piedi")["risultato"], 1, places=3)

    def test_acc_unita_sconosciuta(self):
        out = conv(3, "leghe marine", "metri")
        self.assertIs(out.get("trovato"), False)
        self.assertTrue(str(out.get("da_dire") or "").strip())
'''
RIFERIMENTO_CONVERTITORE = '''import unicodedata

METRI = {"metro": 1.0, "metri": 1.0, "chilometro": 1000.0, "chilometri": 1000.0,
         "miglio": 1609.344, "miglia": 1609.344, "miglio nautico": 1852.0,
         "miglia nautiche": 1852.0, "piede": 0.3048, "piedi": 0.3048, "pollice": 0.0254,
         "pollici": 0.0254, "unita astronomica": 149597870700.0,
         "unita astronomiche": 149597870700.0}


def _norm(s):
    t = unicodedata.normalize("NFD", str(s or "").lower().strip())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


def esegui(dati, calliope):
    da, a = _norm(dati.get("da")), _norm(dati.get("a"))
    if da not in METRI or a not in METRI:
        return {"da_dire": "Non conosco questa unità.", "trovato": False}
    r = float(dati.get("valore") or 0) * METRI[da] / METRI[a]
    return {"da_dire": f"Sono {round(r, 4):g} {a}.".replace(".", ",", 1), "risultato": r}
'''

# 3. Il programma: c01 di prove/prova_lavori.py
RIFERIMENTO_PROGRAMMA = '''import datetime
import os
import re


def rinomina_cartella(cartella):
    nuovi = []
    for n in sorted(os.listdir(cartella)):
        p = os.path.join(cartella, n)
        if not os.path.isfile(p) or not n.lower().endswith(".jpg"):
            continue
        if re.match(r"^\\d{4}-\\d{2}-\\d{2}_", n):
            continue
        d = datetime.date.fromtimestamp(os.path.getmtime(p)).isoformat()
        os.rename(p, os.path.join(cartella, f"{d}_{n}"))
        nuovi.append(f"{d}_{n}")
    return sorted(nuovi)
'''


def casi():
    """{nome: dict} con tipo, compito, file di partenza, accettazione e riferimento."""
    import prova_lavori as PL
    F = _porte()
    c01 = next(c for c in PL.CODICE if c[0] == "c01")
    prima = {"logica.js": F.GIOCO_ROTTO,
             "logica.test.js": F.TEST_LOGICA_PORTE,
             "manifesto.json": json.dumps(F.MANIFESTO_PORTE, ensure_ascii=False, indent=1)}
    return {
        "porte": {"tipo": "estensione", "gioco": True, "correzione": True,
                  "estensione": F.MANIFESTO_PORTE["nome"], "compito": COMPITO_PORTE,
                  "problema": PROBLEMA_PORTE, "prima": prima,
                  "accettazione": ("accettazione_banco.test.js", ACCETTAZIONE_PORTE),
                  "riferimento": {**prima, "logica.js": F.GIOCO_GIUSTO}},
        "convertitore": {"tipo": "estensione", "gioco": False, "correzione": False,
                         "estensione": None, "compito": COMPITO_CONVERTITORE, "prima": {},
                         "accettazione": ("test_accettazione_banco.py",
                                          ACCETTAZIONE_CONVERTITORE),
                         "riferimento": {"estensione.py": RIFERIMENTO_CONVERTITORE}},
        "programma": {"tipo": "codice", "gioco": False, "correzione": False, "estensione": None,
                      "compito": c01[1], "prima": dict(c01[2]),
                      "accettazione": ("test_nascosto_banco.py", c01[3]),
                      "aiuto": {"pytest_free_raises.py": PL.AIUTO_RAISES},
                      "riferimento": {"rinomina_foto.py": RIFERIMENTO_PROGRAMMA}},
    }


def vincoli_correzione(caso: dict) -> str:
    """I vincoli di una correzione come li compone sviluppo_correggi (tools/sviluppo.py)."""
    from calliope.tools.sviluppo import VINCOLO_CORREZIONE_GIOCO, VINCOLO_RIPRODUCI
    return ("È una CORREZIONE dello sviluppo «Le porte di Borgofiore»: cosa deve fare resta "
            "quello del compito. I file della versione che la persona ha provato sono già nella "
            "cartella: riparti da quelli, non riscrivere da zero. Collaudi che non vanno (dati "
            "→ esito): «aperto in prova sullo schermo» → la persona: "
            f"{caso['problema']}. Problema detto dalla persona: «{caso['problema']}»."
            + (VINCOLO_CORREZIONE_GIOCO if caso.get("gioco") else "") + VINCOLO_RIPRODUCI)


# ═══════════════════════════ l'accettazione ═══════════════════════════

def accettazione(sandbox_nuova, file: dict, caso: dict) -> dict:
    """I file del risultato più il test nascosto in una sandbox nuova: {"verde", "esito",
    "uscita"}. Per un'estensione anche il runtime con CalliopeFinta."""
    sb = sandbox_nuova()
    for rel, testo in file.items():
        try:
            sb.scrivi(rel, testo)
        except Exception:  # noqa: BLE001 — un nome non ammesso: si salta
            pass
    if caso["tipo"] == "estensione" and not caso.get("gioco"):
        # Dal pacchetto importato, non accanto al file (13/10: il banco lanciato da una copia
        # fuori dal repository, con PYTHONPATH sulla versione installata)
        import calliope.estensioni as E
        shutil.copy(Path(E.__file__).parent / "_ospite.py", sb.root / "calliope_estensione.py")
    for rel, testo in (caso.get("aiuto") or {}).items():
        sb.scrivi(rel, testo)
    nome, testo = caso["accettazione"]
    sb.scrivi(nome, testo)
    r = sb.test(nome)
    u = str(r.get("uscita") or "")
    if nome.endswith(".js"):
        verde = "ok ACC " in u and "FALLITO ACC " not in u
    else:
        verde = bool(r.get("passano"))
    return {"verde": verde, "esito": r.get("esito"), "uscita": u[-1500:]}


def esempi_finali(sandbox_nuova, file: dict, caso: dict, stato: dict,
                  sandbox_lavoro: Path | None) -> bool | None:
    """Gli esempi di accettazione dell'agente (test_accettazione.py o accettazione.test.js,
    scritti dall'analisi prima del codice) rieseguiti dal banco sui file finali del lavoro, in
    una sandbox nuova (13/10 sera, L7 del banco: il riepilogo diceva «esempi 7 rossi» con lo
    stato di prima della correzione all'ultima passata, e a mano passavano tutti). Il file degli
    esempi è in sola lettura e non va nella cartella del risultato: si prende dalla sandbox del
    lavoro. None se il lavoro non li ha."""
    from calliope.agenti import accettazione as A
    st = dict(stato or {})
    nome = st.get("nome_file") or A.FILE
    p = Path(sandbox_lavoro) / nome if sandbox_lavoro else None
    if st.get("stato") != "pronta" or not st.get("file") or p is None or not p.is_file():
        return None
    sb = sandbox_nuova()
    for rel, testo in {**file, nome: p.read_text(encoding="utf-8")}.items():
        try:
            sb.scrivi(rel, testo)
        except Exception:  # noqa: BLE001 — un nome non ammesso: si salta
            pass
    if caso["tipo"] == "estensione" and not caso.get("gioco"):
        import calliope.estensioni as E
        shutil.copy(Path(E.__file__).parent / "_ospite.py", sb.root / "calliope_estensione.py")
    r = A.esegui(sb, {**st, "nome_file": nome})
    return bool(r and r["passano"])


def detto_esempi(r: dict) -> str:
    """«esempi 7 verdi» dalla riga: lo stato rieseguito alla fine, non l'ultimo dell'agente."""
    n = (r.get("analisi") or {}).get("esempi")
    if not n:
        return ""
    v = r.get("esempi_finali")
    return f", esempi {n} " + ("verdi" if v else "rossi" if v is False else "non eseguiti")


def file_di(cartella: Path) -> dict:
    out = {}
    for p in sorted(Path(cartella).rglob("*")):
        if p.is_file() and p.name != "lavoro.json" and not any(
                x.startswith(".") for x in p.relative_to(cartella).parts):
            try:
                out[p.relative_to(cartella).as_posix()] = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                pass
    return out


# ═══════════════════════════ a secco ═══════════════════════════

def secco() -> int:
    """Il banco controlla sé stesso: ogni accettazione fallisce sul punto di partenza e passa
    sulla soluzione di riferimento (docker finto e Node della macchina, come le prove)."""
    import prova_agente_guida as G
    tmp = Path(tempfile.mkdtemp(prefix="banco-temperatura-secco-"))
    n = [0]

    def nuova():
        n[0] += 1
        return G.sandbox(tmp, f"s{n[0]}")
    errori = 0
    try:
        for nome, caso in casi().items():
            if caso.get("gioco") and not shutil.which("node"):
                print(f"SALTATO {nome}: node non c'è")
                continue
            prima = accettazione(nuova, caso["prima"], caso)
            rif = accettazione(nuova, {**caso["prima"], **caso["riferimento"]}, caso)
            ok = not prima["verde"] and rif["verde"]
            errori += not ok
            print(f"{'ok ' if ok else 'ERR'} {nome}: accettazione rossa alla partenza, verde sul "
                  "riferimento" + ("" if ok else f"  prima={prima['uscita'][-300:]!r} "
                                                 f"riferimento={rif['uscita'][-500:]!r}"))
        vin = vincoli_correzione(casi()["porte"])
        ok = "gioco.test.js" in vin and "deve FALLIRE" in vin and PROBLEMA_PORTE in vin
        errori += not ok
        print(f"{'ok ' if ok else 'ERR'} i vincoli della correzione delle porte: il test che "
              "riproduce in gioco.test.js, prima rosso")
        errori += secco_giri(tmp / "giri")
        errori += secco_analisi(tmp / "analisi")
        errori += secco_tetto(tmp / "tetto")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + ("TUTTO OK" if not errori else f"{errori} ERRORI"))
    return 1 if errori else 0


CASO_SOMMA = {"tipo": "codice", "gioco": False, "correzione": False, "estensione": None,
              "compito": "Scrivi somma.py con somma(a, b) che restituisce la somma.",
              "prima": {}, "accettazione": ("test_nascosto_banco.py",
                                            "from somma import somma\n\n\n"
                                            "def test_somma():\n    assert somma(2, 3) == 5\n")}


def secco_giri(tmp: Path) -> int:
    """I giri (13/10) con l'agente finto di prove/ollama_finto.py e il servizio vero: budget
    diviso, tappa al tetto del giro 1, «continua» chiamato dal banco, consegna al giro 2;
    senza consegna l'ultimo giro chiude con «limite»; con un giro solo il tetto chiude come
    prima (nessuna tappa). Le misure dei giri nella riga."""
    from calliope.agenti import Lavori, carica
    from calliope.config import Config
    from prove.ollama_finto import FakeOllama

    def scrivi(c):
        return {"tool_calls": [{"name": "scrivi_file", "arguments": {
            "percorso": "somma.py", "contenuto": f"def somma(a, b):\n    return {c}\n"}}]}
    consegna = {"tool_calls": [{"name": "consegna", "arguments": {
        "riassunto": "Somma corretta.", "esito": "fatto"}}]}
    errori = 0

    def verifica(nome, ok, dettaglio=""):
        nonlocal errori
        errori += not ok
        print(f"{'ok ' if ok else 'ERR'} giri: {nome}" + ("" if ok else f"  {dettaglio}"))
    tmp.mkdir(parents=True, exist_ok=True)
    fake = FakeOllama(modelli=("agente-finto",)).avvia()
    svc = None
    try:
        def servizio(giri, minuti=20.0):
            cfg = Config()
            cfg.agenti_url = fake.url
            cfg.agenti_modello = "agente-finto"
            cfg.agenti_risultati = str(tmp / "risultati")
            cfg.agenti_sandbox = str(tmp / "sandbox")
            cfg.agenti_sandbox_motore = "processo"
            cfg.agenti_modelli = str(tmp / "modelli")
            cfg.llm_native_url = "http://127.0.0.1:9"
            cfg.agenti_conferma = "mai"
            cfg.agenti_max_passi = 6
            b = dividi_budget(cfg, giri, minuti)
            return cfg, b, Lavori(cfg, carica(cfg), log=lambda *a: None)

        cfg, b, svc = servizio(2)
        verifica("budget diviso: 6 passate in 2 giri = 3 per giro, 20 minuti = 10 per giro",
                 b["passate_giro"] == 3 and b["passate_totali"] == 6
                 and cfg.agenti_max_passi == 3 and cfg.agenti_tempo_max_min == 10.0
                 and svc.agente.max_passi == 3 and svc.agente.tempo_max_s == 600, str(b))
        c2 = SimpleNamespace(agenti_max_passi=24, agenti_max_token=0)
        b2 = dividi_budget(c2, 5, 20)
        verifica("arrotondato: 24 passate in 5 giri = 5 per giro (25 in tutto), 4 minuti",
                 b2["passate_giro"] == 5 and b2["passate_totali"] == 25
                 and c2.agenti_tempo_max_min == 4.0, str(b2))
        # 1. Giro 1 al tetto (3 passate sbagliate) → tappa; giro 2: giusta e consegna
        fake.copione = [scrivi("a - b"), scrivi("a * b"), scrivi("b - a"), scrivi("a + b"),
                        consegna]
        r = un_lavoro(svc, cfg, tmp, "somma", CASO_SOMMA, "secco g=2", giri=2)
        pg = r["per_giro"]
        verifica("giro 1 fermo alla tappa al tetto delle passate, accettazione rossa",
                 len(pg) == 2 and pg[0]["esito"] == "tappa"
                 and pg[0]["tipo_limite"] == "passate" and pg[0]["accettazione"] is False,
                 str(pg))
        verifica("il banco chiama continua: il giro 2 riparte dal contesto e consegna",
                 r["esito"] == "fatto" and r["riuscito"] and r["giri"] == 2
                 and r["passate_giri"] == [3, 2] and r["giro_consegna"] == 2
                 and r["giro_accettazione"] == 2 and r["sbloccato"] is True
                 and any("Hai un altro giro di lavoro" in str(m.get("content"))
                         for q in fake.richieste for m in q.get("messages") or []),
                 json.dumps({k: v for k, v in r.items() if k != "per_giro"},
                            ensure_ascii=False, default=str)[:800])
        # 2. Nessuna consegna: l'ultimo giro chiude il lavoro con «limite», non con una tappa
        fake.copione = [scrivi("a - b")] * 8
        r = un_lavoro(svc, cfg, tmp, "somma", CASO_SOMMA, "secco g=2", giri=2)
        verifica("senza consegna: tappa al giro 1, l'ultimo giro chiude con «limite»",
                 r["giri"] == 2 and r["per_giro"][0]["esito"] == "tappa"
                 and r["esito"] == "limite" and r["giro_consegna"] is None
                 and r["sbloccato"] is False and r["passate_giri"] == [3, 3],
                 f"{r['esito']} {r['per_giro']}")
        svc.close()
        # 3. Contrario: un giro solo, il tetto chiude come prima (nessuna tappa)
        cfg, b, svc = servizio(1)
        fake.copione = [scrivi("a - b")] * 8
        r = un_lavoro(svc, cfg, tmp, "somma", CASO_SOMMA, "secco", giri=1)
        verifica("contrario: con un giro solo 6 passate e «limite», come prima",
                 b["passate_giro"] == 6 and r["esito"] == "limite" and r["giri"] == 1
                 and r["passate"] == 6 and r["sbloccato"] is None
                 and colonna_giri([r]) == "-", f"{r['esito']} {r['per_giro']}")
    finally:
        if svc is not None:
            svc.close()
        fake.ferma()
    return errori


def secco_analisi(tmp: Path) -> int:
    """L'analisi prima del codice nel banco (13/10, flusso a fasi parte 2), con l'agente finto
    e il servizio vero: la domanda prima di cominciare riceve la risposta del banco, la
    passata dopo la risposta scrive gli esempi di accettazione nella cartella, la riga conta
    le domande e l'analisi; «config» in --temperature e --presence."""
    from calliope.agenti import Lavori, carica
    from calliope.config import Config
    from prove.ollama_finto import FakeOllama
    errori = 0

    def verifica(nome, ok, dettaglio=""):
        nonlocal errori
        errori += not ok
        print(f"{'ok ' if ok else 'ERR'} analisi: {nome}" + ("" if ok else f"  {dettaglio}"))
    t = valori("config,0.6", 0.4)
    pp = valori("config", CONFIG)
    verifica("«config» in --temperature e --presence", t == [0.4, 0.6] and pp == [CONFIG])
    esempio = {"requisito": 1, "dati": {"valore": 1, "da": "miglia", "a": "metri"},
               "numero": 1609.344, "tolleranza": None, "contiene": "", "trovato": None}
    con_dubbio = {"contraddizioni": [{"requisiti": [1], "domanda": "Le miglia sono terrestri"}],
                  "scelte": [], "al_collaudo": [], "input": [{"nome": "valore", "tipo": "number"}],
                  "campo_numero": "risultato", "esempi": [esempio]}
    senza = dict(con_dubbio, contraddizioni=[])
    tmp.mkdir(parents=True, exist_ok=True)
    fake = FakeOllama(modelli=("agente-finto",)).avvia()
    svc = None
    try:
        cfg = Config()
        cfg.agenti_url = fake.url
        cfg.agenti_modello = "agente-finto"
        cfg.agenti_risultati = str(tmp / "risultati")
        cfg.agenti_sandbox = str(tmp / "sandbox")
        cfg.agenti_sandbox_motore = "processo"
        cfg.agenti_modelli = str(tmp / "modelli")
        cfg.llm_native_url = "http://127.0.0.1:9"
        cfg.agenti_conferma = "mai"
        cfg.agenti_max_passi = 4
        svc = Lavori(cfg, carica(cfg), log=lambda *a: None)
        svc.estensioni = EstensioniFinte()
        fake.copione = [{"content": json.dumps(con_dubbio)}, {"content": json.dumps(senza)},
                        {"tool_calls": [{"name": "consegna", "arguments": {
                            "riassunto": "Non lo faccio.", "esito": "impossibile"}}]}]
        r = un_lavoro(svc, cfg, tmp, "convertitore", casi()["convertitore"], "secco")
        verifica("la domanda prima di cominciare ha la risposta del banco, una volta",
                 r["domande"] == ["Prima di cominciare: le miglia sono terrestri?"]
                 and any(RISPOSTA_BANCO in json.dumps(q, ensure_ascii=False)
                         for q in fake.richieste), str(r["domande"]))
        verifica("…dopo la risposta l'analisi è pronta, con l'esempio; il lavoro finisce",
                 r["analisi"].get("stato") == "pronta" and r["analisi"].get("esempi") == 1
                 and r["esito"] == "impossibile", json.dumps(r["analisi"]) + str(r["esito"]))
        sb = next((x for x in Path(cfg.agenti_sandbox).glob("*") if x.is_dir()), None)
        verifica("…e test_accettazione.py era nella cartella dell'agente con il runtime e i "
                 "test di partenza", sb is not None and all(
                     (sb / n).is_file() for n in ("test_accettazione.py",
                                                  "calliope_estensione.py",
                                                  "test_estensione.py")),
                 str(sorted(x.name for x in sb.iterdir())) if sb else "nessuna sandbox")
    finally:
        if svc is not None:
            svc.close()
        fake.ferma()
    return errori


def secco_tetto(tmp: Path) -> int:
    """La consegna al tetto (13/10 sera, L7 del banco) con l'agente finto e il servizio vero:
    l'agente scrive il convertitore giusto all'ultima passata e non chiama consegna; al tetto
    gli esempi di accettazione e i test si rieseguono, sono verdi e il lavoro si chiude
    «fatto» (regola agente_consegna_al_tetto). Il riepilogo dice gli esempi rieseguiti alla
    fine. Contrario: l'ultima passata scrive quello sbagliato, «limite» ed esempi rossi."""
    from calliope.agenti import Lavori, carica
    from calliope.config import Config
    from prove.ollama_finto import FakeOllama
    errori = 0

    def verifica(nome, ok, dettaglio=""):
        nonlocal errori
        errori += not ok
        print(f"{'ok ' if ok else 'ERR'} tetto: {nome}" + ("" if ok else f"  {dettaglio}"))

    def chiama(*cc):
        return {"tool_calls": [{"name": n, "arguments": a} for n, a in cc]}
    analisi = {"contraddizioni": [], "scelte": [], "al_collaudo": [],
               "input": [{"nome": "valore", "tipo": "number"}, {"nome": "da", "tipo": "string"},
                         {"nome": "a", "tipo": "string"}], "campo_numero": "risultato",
               "esempi": [{"requisito": 1, "dati": {"valore": 1, "da": "miglia", "a": "metri"},
                           "numero": 1609.344, "tolleranza": 0.01, "contiene": "",
                           "trovato": None}]}
    manifesto = {"nome": "convertitore_distanze", "titolo": "Convertitore di distanze",
                 "cosa_fa": {"verbo": "converte", "oggetto": "una distanza tra due unità"},
                 "input": {"type": "object", "properties": {
                     "valore": {"type": "number", "description": "il valore"},
                     "da": {"type": "string", "description": "l'unità di partenza"},
                     "a": {"type": "string", "description": "l'unità d'arrivo"}},
                     "required": ["valore", "da", "a"]},
                 "permessi": {}, "livello": "familiare",
                 "limiti": {"tempo_s": 10, "memoria_mb": 256}}
    sbagliata = RIFERIMENTO_CONVERTITORE.replace('"miglia": 1609.344', '"miglia": 1500.0')

    def copione(ultima):
        return [{"content": json.dumps(analisi)},
                chiama(("piano", {"capacita_necessarie": [], "fattibile": True,
                                  "motivo": "una conversione, senza rete", "scope": {}})),
                chiama(("scrivi_file", {"percorso": "manifesto.json",
                                        "contenuto": json.dumps(manifesto, ensure_ascii=False)}),
                       ("scrivi_file", {"percorso": "estensione.py", "contenuto": sbagliata})),
                chiama(("esegui_test", {})),
                chiama(("scrivi_file", {"percorso": "estensione.py", "contenuto": ultima}))]
    tmp.mkdir(parents=True, exist_ok=True)
    fake = FakeOllama(modelli=("agente-finto",)).avvia()
    svc = None
    try:
        cfg = Config()
        cfg.agenti_url = fake.url
        cfg.agenti_modello = "agente-finto"
        cfg.agenti_risultati = str(tmp / "risultati")
        cfg.agenti_sandbox = str(tmp / "sandbox")
        cfg.agenti_sandbox_motore = "processo"
        cfg.agenti_modelli = str(tmp / "modelli")
        cfg.llm_native_url = "http://127.0.0.1:9"
        cfg.agenti_conferma = "mai"
        cfg.agenti_max_passi = 4
        svc = Lavori(cfg, carica(cfg), log=lambda *a: None)
        svc.estensioni = EstensioniFinte()
        fake.copione = copione(RIFERIMENTO_CONVERTITORE)
        r = un_lavoro(svc, cfg, tmp, "convertitore", casi()["convertitore"], "secco")
        verifica("codice giusto all'ultima passata, nessuna consegna: al tetto «fatto» con la "
                 "regola, accettazione nascosta verde",
                 r["esito"] == "fatto" and r["consegna_al_tetto"] == "passate"
                 and r["regole"].get("agente_consegna_al_tetto") == 1 and r["riuscito"]
                 and r["passate"] == 4,
                 json.dumps({k: r.get(k) for k in ("esito", "motivo", "consegna_al_tetto",
                                                   "regole", "passate", "analisi")},
                            ensure_ascii=False, default=str))
        verifica("…il riepilogo dice gli esempi rieseguiti alla fine: verdi",
                 r["esempi_finali"] is True and r["analisi"].get("passano") is True
                 and detto_esempi(r) == ", esempi 1 verdi", f"{r['esempi_finali']} {r['analisi']}")
        fake.copione = copione(sbagliata)
        r = un_lavoro(svc, cfg, tmp, "convertitore", casi()["convertitore"], "secco")
        verifica("contrario: l'ultima passata scrive quello sbagliato, «limite» ed esempi rossi",
                 r["esito"] == "limite" and not r["consegna_al_tetto"]
                 and "agente_consegna_al_tetto" not in r["regole"]
                 and r["esempi_finali"] is False and r["analisi"].get("passano") is False
                 and detto_esempi(r) == ", esempi 1 rossi",
                 json.dumps({k: r.get(k) for k in ("esito", "esempi_finali", "analisi")},
                            ensure_ascii=False, default=str))
        # Le porte (14/10, banco L7 e L10): una correzione di un gioco non ha esempi, al tetto
        # vale il test che riproduce il problema. L'agente corregge logica.js e scrive il test
        # del disegno, poi non consegna
        if not shutil.which("node"):
            print("SALTATO tetto: le porte (node non c'è)")
            return errori
        F = _porte()
        # Node nella sandbox: il docker finto delle prove (la sandbox «processo» esegue solo
        # Python), come nella verifica a secco dell'accettazione
        import prova_agente_guida as G
        modello = G.sandbox(tmp, "isolamento-finto")

        def finto():
            svc.isolamento, svc.isolamenti = modello.isolamento, dict(modello.linguaggi)
            return svc.isolamento
        svc.scegli_isolamento = finto

        def porte(con_test):
            return [chiama(("piano", {"capacita_necessarie": [], "fattibile": True,
                                      "motivo": "una correzione del gioco", "scope": {}})),
                    chiama(("scrivi_file", {"percorso": "logica.js",
                                            "contenuto": F.GIOCO_GIUSTO})),
                    chiama(("scrivi_file", {"percorso": "gioco.test.js",
                                            "contenuto": F.TEST_GIOCO_PORTE})
                           if con_test else ("leggi_file", {"percorso": "logica.js"})),
                    chiama(("esegui_test", {}))]
        fake.copione = porte(True)
        r = un_lavoro(svc, cfg, tmp, "porte", casi()["porte"], "secco")
        verifica("le porte corrette e il test del disegno, nessuna consegna: al tetto «fatto» "
                 "con la riproduzione, accettazione nascosta verde",
                 r["esito"] == "fatto" and r["consegna_al_tetto"] == "passate"
                 and r["consegna_al_tetto_con"] == "riproduzione"
                 and r["riproduzione"] == "riprodotto" and r["riuscito"],
                 json.dumps({k: r.get(k) for k in ("esito", "motivo", "consegna_al_tetto",
                                                   "consegna_al_tetto_con", "riproduzione",
                                                   "accettazione", "regole")},
                            ensure_ascii=False, default=str))
        fake.copione = porte(False)
        r = un_lavoro(svc, cfg, tmp, "porte", casi()["porte"], "secco")
        verifica("contrario: le porte corrette senza il test che riproduce, «limite» (anche con "
                 "l'accettazione nascosta verde)",
                 r["esito"] == "limite" and not r["consegna_al_tetto"] and r["accettazione"],
                 json.dumps({k: r.get(k) for k in ("esito", "riproduzione", "accettazione")},
                            ensure_ascii=False, default=str))
    finally:
        if svc is not None:
            svc.close()
        fake.ferma()
    return errori


# ═══════════════════════════ sulla DGX ═══════════════════════════

class EstensioniFinte:
    """Le estensioni per il banco: nessun archivio vero, la versione «candidata» è il lavoro."""
    archivio = SimpleNamespace(nomi=lambda: [])

    def candidata_da_lavoro(self, lav, sb, ris):
        # Con la «frase» che il servizio vero dà sempre (12/10: senza, KeyError in
        # servizio.py e i lavori riusciti finivano «errore»)
        nome = getattr(lav, "estensione", None) or "banco"
        return {"nome": nome, "versione": 1, "frase": f"«{nome}» è pronta da provare."}

    def pronto(self):
        return False


# La risposta del banco a una domanda prima o durante il lavoro (13/10): lascia decidere
RISPOSTA_BANCO = "Decidi tu, con la scelta più comune."


def aspetta(svc, lav, limite_s: float):
    import queue
    t0 = time.time()
    while time.time() - t0 < limite_s:
        try:
            item = svc.done.get(timeout=1.0)
        except queue.Empty:
            if lav.stato in ("annullato", "errore", "fatto") and lav.fine:
                return None
            continue
        if item.get("id") == lav.id:
            return item
    lav.annulla.set()
    return None


def dividi_budget(cfg, giri: int, minuti: float) -> dict:
    """Il budget di un lavoro diviso in `giri` giri uguali, solo in memoria (13/10): passate
    arrotondate (24 / 2 = 12; 24 / 5 = 5, 25 in tutto: il conto lo stampa main), minuti / giri
    per giro (il tetto dei token segue i minuti; agenti_max_token, se acceso, diviso anche
    lui). Con giri = 1 tutto come prima."""
    giri = max(1, int(giri))
    passate = int(cfg.agenti_max_passi)
    per_giro = max(1, int(passate / giri + 0.5))
    cfg.agenti_max_passi = per_giro
    cfg.agenti_tempo_max_min = float(minuti) / giri
    if int(getattr(cfg, "agenti_max_token", 0) or 0) > 0:
        cfg.agenti_max_token = max(1, int(cfg.agenti_max_token / giri + 0.5))
    return {"giri": giri, "passate_lavoro": passate, "passate_giro": per_giro,
            "passate_totali": per_giro * giri, "minuti_giro": round(float(minuti) / giri, 2),
            "minuti_totali": float(minuti)}


def un_lavoro(svc, cfg, uscita: Path, nome: str, caso: dict, etichetta: str,
              giri: int = 1) -> dict:
    from calliope.agenti.ciclo import segnali_giro
    from calliope.agenti.sandbox import Sandbox
    lav = svc.nuovo(caso["tipo"], caso["compito"], "banco", "Ottavio", "amministra",
                    vincoli=vincoli_correzione(caso) if caso.get("correzione") else "")
    lav.file_iniziali = dict(caso["prima"])
    if caso["tipo"] == "estensione":
        lav.estensione = caso.get("estensione")
        lav.gioco = bool(caso.get("gioco"))
    if caso.get("correzione"):
        lav.correzione = True
        lav.problema_correzione = caso["problema"]
    # Con più giri (13/10) il tetto di un giro è una tappa, come in un lavoro della modalità
    # sviluppo (sviluppo.py lo accende così); con un giro solo resta spento, come prima
    lav.tappe = giri > 1
    iso = svc.scegli_isolamento()
    k = [0]

    def nuova():
        k[0] += 1
        return Sandbox(uscita / "verifica" / f"{etichetta}-{nome}-{lav.id}-{k[0]}", 30, 1024,
                       isolamento=iso, linguaggi=svc.isolamenti)
    t0 = time.time()
    svc.avvia(lav)
    per_giro = []
    domande = []
    for g in range(1, max(1, giri) + 1):
        tg, p0, k0 = time.time(), lav.passi, lav.token
        while True:
            aspetta(svc, lav, cfg.agenti_tempo_max_min * 60 + 180)
            r = lav.risultato or {}
            # Una domanda (13/10: l'analisi prima del codice, o l'agente a metà lavoro): il
            # banco risponde da sé, come una persona che lascia decidere, e la conta
            if lav.stato == "in_attesa" and r.get("esito") == "domanda" and len(domande) < 5:
                domande.append(str(r.get("domanda") or ""))
                svc.rispondi(lav, RISPOSTA_BANCO)
                continue
            break
        info = {"giro": g, "passate": lav.passi - p0, "token": lav.token - k0,
                "minuti": round((time.time() - tg) / 60, 2), "esito": r.get("esito"),
                "tipo_limite": r.get("tipo_limite"), "test_passano": r.get("test_passano")}
        per_giro.append(info)
        if not svc.in_tappa(lav):
            break
        # La tappa: l'accettazione nascosta sui file del giro, poi un giro nuovo senza nota
        cart = Path(r["cartella"]) if r.get("cartella") else None
        info["accettazione"] = bool(cart and cart.is_dir()
                                    and accettazione(nuova, file_di(cart), caso)["verde"])
        if g + 1 >= giri:
            lav.tappe = False        # l'ultimo giro: il tetto chiude il lavoro come oggi
        svc.continua(lav)
    if svc.in_tappa(lav):            # non dovrebbe succedere: si chiude comunque
        lav.annulla.set()
    minuti = (time.time() - t0) / 60
    ris = lav.risultato or {}
    # Senza la cartella del risultato non si prende quella del banco (12/10: copiava il banco
    # dentro sé stesso fino a «troppi file»)
    cartella = Path(ris["cartella"]) if ris.get("cartella") else None
    acc = accettazione(nuova, file_di(cartella), caso) if cartella and cartella.is_dir() else {
        "verde": False, "esito": None, "uscita": "nessuna cartella"}
    per_giro[-1]["accettazione"] = acc["verde"]
    # Gli esempi dell'agente rieseguiti dal banco sui file finali (13/10 sera)
    from calliope.agenti.servizio import cartella_sandbox
    sbl = sorted(cartella_sandbox(cfg).glob(f"{lav.id}-*"))
    es_finali = (esempi_finali(nuova, file_di(cartella), caso, getattr(lav, "accettazione", None),
                               sbl[-1] if sbl else None)
                 if cartella and cartella.is_dir() else None)
    seg = segnali_giro(lav, cfg.agenti_max_passi)
    fatto = (ris.get("esito") == "fatto" or lav.stato == "fatto")
    giro_acc = next((x["giro"] for x in per_giro if x.get("accettazione")), None)
    giro_consegna = per_giro[-1]["giro"] if fatto else None
    sbloccato = None
    if giri > 1:
        sbloccato = bool(len(per_giro) > 1 and not per_giro[0].get("accettazione")
                         and (fatto or acc["verde"]))
    riga = {"caso": nome, "variante": etichetta, "lavoro": lav.id, "stato": lav.stato,
            "esito": ris.get("esito"), "motivo": ris.get("motivo"),
            "riuscito": bool(fatto and acc["verde"]), "accettazione": acc["verde"],
            "accettazione_esito": acc["esito"], "passate": lav.passi, "token": lav.token,
            "ragionamento": lav.ragionamento, "minuti": round(minuti, 2),
            "ripetizioni": seg.get("ripetizioni", 0), "senza_novita": seg.get("senza_novita", 0),
            "a_vuoto": seg.get("a_vuoto", False), "test_agente": ris.get("test"),
            "riproduzione": (getattr(lav, "riproduzione", None) or {}).get("stato"),
            # Chiuso dal codice al tetto con gli esempi verdi (13/10 sera, ciclo.py)
            "consegna_al_tetto": ris.get("consegna_al_tetto"),
            # …con gli esempi o con la riproduzione di una correzione senza esempi (14/10)
            "consegna_al_tetto_con": ris.get("consegna_al_tetto_con"),
            "esempi_finali": es_finali,
            "regole": dict(((lav.segnali or {}).get("regole") or {})),
            "cartella": str(cartella),
            "giri": len(per_giro), "giri_max": giri, "giro_accettazione": giro_acc,
            "giro_consegna": giro_consegna, "sbloccato": sbloccato,
            "passate_giri": [x["passate"] for x in per_giro], "per_giro": per_giro,
            # L'analisi prima del codice (13/10, flusso a fasi parte 2): le domande a cui il
            # banco ha risposto, gli esempi di accettazione dell'agente e il loro esito
            "domande": domande, "analisi": {k: v for k, v in (
                getattr(lav, "accettazione", None) or {}).items()
                if k in ("stato", "esempi", "passano", "rossi", "al_collaudo", "secondi",
                         "perche")}}
    if not acc["verde"]:
        riga["accettazione_uscita"] = acc["uscita"][-600:]
    return riga


# «config» in --presence: i valori della Config per tipo di lavoro (13/10)
CONFIG = object()


def valori(testo: str, config):
    """I valori di --temperature o --presence: numeri, o «config» per quello della Config."""
    out = []
    for x in str(testo or "").split(","):
        x = x.strip().lower()
        if x:
            out.append(config if x in ("config", "cfg") else float(x))
    return out


def colonna_giri(rr: list[dict]) -> str:
    """Per un gruppo di lavori a giri (13/10): le accettazioni verdi per giro («g1+g2»: 2+3 =
    due verdi al primo giro, tre al secondo) e gli sbloccati («s2»). «-» con un giro solo."""
    n = max([int(r.get("giri_max") or 1) for r in rr] or [1])
    if n <= 1:
        return "-"
    verdi = [sum(1 for r in rr if r.get("giro_accettazione") == g) for g in range(1, n + 1)]
    return "+".join(map(str, verdi)) + f" s{sum(1 for r in rr if r.get('sbloccato'))}"


def tabella(righe: list[dict]):
    print("\nvariante                    caso          riusciti  acc.  passate  token(med)  "
          "giri a vuoto  minuti(med)  giri")
    chiavi = sorted({(r["variante"], r["caso"]) for r in righe})
    for v, c in chiavi:
        rr = [r for r in righe if r["variante"] == v and r["caso"] == c]
        med = lambda k: statistics.median([r[k] for r in rr]) if rr else 0  # noqa: E731
        print(f"{v:<27} {c:<13} {sum(r['riuscito'] for r in rr)}/{len(rr):<7} "
              f"{sum(r['accettazione'] for r in rr)}/{len(rr):<3} {med('passate'):>7} "
              f"{med('token'):>10} {sum(r['ripetizioni'] + (1 if r['a_vuoto'] else 0) for r in rr):>13} "
              f"{med('minuti'):>11}  {colonna_giri(rr)}")
    if any(int(r.get("giri_max") or 1) > 1 for r in righe):
        print("giri: accettazioni verdi per giro (giro 1 + giro 2 …) e sN = sbloccati dopo la "
              "ripartenza")
    for v in sorted({r["variante"] for r in righe}):
        rr = [r for r in righe if r["variante"] == v]
        print(f"TOTALE {v}: {sum(r['riuscito'] for r in rr)}/{len(rr)} riusciti, "
              f"token in tutto {sum(r['token'] for r in rr)}, "
              f"minuti in tutto {sum(r['minuti'] for r in rr):.1f}")


def main(argv) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Banco della temperatura dell'agente")
    ap.add_argument("--secco", action="store_true", help="solo il controllo del banco, senza "
                    "modello")
    ap.add_argument("--temperature", default="0.4,0.6", help="valori separati da virgole; "
                    "«config» = quello della Config (agenti_temperatura)")
    ap.add_argument("--presence", default="0,0.5", help="valori separati da virgole; «config» = "
                    "quelli della Config per tipo di lavoro (agenti_presence_penalty)")
    ap.add_argument("--accettazione", default="config", choices=("config", "si", "no"),
                    help="l'analisi prima del codice con gli esempi di accettazione "
                    "(agenti_accettazione, 13/10): come nella Config, accesa o spenta")
    ap.add_argument("--ripetizioni", type=int, default=2)
    ap.add_argument("--casi", default="porte,convertitore,programma")
    ap.add_argument("--minuti", type=float, default=20.0, help="tetto di tempo per lavoro "
                    "(con --giri N diviso per N: lo stesso tempo in tutto)")
    ap.add_argument("--giri", type=int, default=1, help="giri per lavoro: le passate e il "
                    "tempo divisi in N giri uguali, con la tappa e «continua» tra un giro e "
                    "l'altro (1 = come prima)")
    ap.add_argument("--uscita")
    args = ap.parse_args(argv)
    if args.secco:
        return secco()
    if args.giri < 1:
        ap.error("--giri vuole un numero da 1 in su")
    from calliope.agenti import Lavori, carica
    from calliope.config import load_config
    cfg = load_config()
    cfg.agenti_conferma = "mai"
    # Prima di creare il servizio: l'agente legge passate e tempo da cfg quando nasce
    budget = dividi_budget(cfg, args.giri, args.minuti)
    if args.giri > 1:
        print(f"Giri: {budget['passate_lavoro']} passate in {args.giri} giri = "
              f"{budget['passate_giro']} per giro ({budget['passate_totali']} in tutto), "
              f"{budget['minuti_giro']} minuti per giro ({budget['minuti_totali']:g} in tutto)",
              flush=True)
    imp = carica(cfg)
    if imp is None:
        print("Nessun agente configurato in questa cartella (serve la configurazione di "
              "Calliope con l'agente).")
        return 1
    uscita = Path(args.uscita).expanduser() if args.uscita else Path(
        tempfile.mkdtemp(prefix="banco-temperatura-"))
    uscita.mkdir(parents=True, exist_ok=True)
    cfg.agenti_risultati = str(uscita / "risultati")
    cfg.agenti_sandbox = str(uscita / "sandbox")
    svc = Lavori(cfg, imp, log=lambda m: print(f"   {m}", flush=True))
    svc.estensioni = EstensioniFinte()
    d = svc.verifica()
    if d["codice"] != "ok":
        print(f"L'agente non è raggiungibile: {d['motivo']}. {d['passo']}")
        svc.close()
        return 1
    scelti = [c.strip() for c in args.casi.split(",") if c.strip()]
    tutti = casi()
    temperature = valori(args.temperature, cfg.agenti_temperatura)
    presenze = valori(args.presence, CONFIG)
    if args.accettazione != "config":
        cfg.agenti_accettazione = args.accettazione == "si"
    acc = "" if args.accettazione == "config" else f" acc={args.accettazione}"
    print(f"Banco della temperatura: agente {imp.modello}; temperature {temperature}, "
          f"presence_penalty {['config' if p is CONFIG else p for p in presenze]} "
          f"(nella Config {cfg.agenti_presence_penalty}), analisi prima del codice "
          f"{'accesa' if cfg.agenti_accettazione else 'spenta'}, {args.ripetizioni} "
          f"ripetizioni, casi {scelti}; risultati in {uscita}", flush=True)
    righe = []
    t0 = time.time()
    vecchie = (cfg.agenti_temperatura, dict(cfg.agenti_presence_penalty))
    try:
        for rip in range(args.ripetizioni):
            for t in temperature:
                for pp in presenze:
                    etichetta = (f"t={t:g} pp={'cfg' if pp is CONFIG else f'{pp:g}'}"
                                 + (f" g={args.giri}" if args.giri > 1 else "") + acc)
                    # Solo in memoria: il servizio e l'agente leggono cfg a ogni passata
                    cfg.agenti_temperatura = t
                    cfg.agenti_presence_penalty = (dict(vecchie[1]) if pp is CONFIG
                                                   else {k: pp for k in vecchie[1]})
                    for nome in scelti:
                        print(f"\n— {etichetta}, {nome}, ripetizione {rip + 1}", flush=True)
                        r = un_lavoro(svc, cfg, uscita, nome, tutti[nome], etichetta,
                                      giri=args.giri)
                        righe.append(r)
                        print(f"{'ok ' if r['riuscito'] else 'NO '} {nome} {etichetta}: "
                              f"accettazione {'verde' if r['accettazione'] else 'rossa'}, "
                              f"{r['passate']} passate, {r['token']} token, "
                              f"{r['minuti']} min, giri a vuoto {r['ripetizioni']}"
                              f"{' (a vuoto)' if r['a_vuoto'] else ''}, esito {r['esito']}"
                              + (f", riproduzione {r['riproduzione']}" if r["riproduzione"]
                                 else "")
                              + (f", domande {len(r['domande'])}" if r["domande"] else "")
                              + detto_esempi(r)
                              + (f", consegna al tetto ({r['consegna_al_tetto']}, con "
                                 f"{r.get('consegna_al_tetto_con') or 'esempi'})"
                                 if r.get("consegna_al_tetto") else "")
                              + (f"; giri {r['giri']} (passate {r['passate_giri']}), "
                                 f"accettazione verde al giro {r['giro_accettazione']}, "
                                 f"consegna al giro {r['giro_consegna']}, "
                                 f"sbloccato {r['sbloccato']}" if args.giri > 1 else ""),
                              flush=True)
                        (uscita / "righe.json").write_text(json.dumps(
                            righe, ensure_ascii=False, indent=1), encoding="utf-8")
    finally:
        cfg.agenti_temperatura, cfg.agenti_presence_penalty = vecchie
        svc.close()
    tabella(righe)
    riepilogo = {"agente": imp.modello, "data": datetime.datetime.now().isoformat(
        timespec="seconds"), "temperature": temperature,
        "presence": ["config" if p is CONFIG else p for p in presenze],
        "presence_config": vecchie[1], "accettazione": bool(cfg.agenti_accettazione),
        "ripetizioni": args.ripetizioni, "casi": scelti, "giri": args.giri, "budget": budget,
        "minuti": round((time.time() - t0) / 60, 1), "righe": righe}
    (uscita / "riepilogo.json").write_text(json.dumps(riepilogo, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    print(f"\nRiepilogo in {uscita / 'riepilogo.json'} ({riepilogo['minuti']} minuti)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
