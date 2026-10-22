"""I tetti dell'agente per profilo (22/10/2026, issue #225, passo 7 di
docs/ricerche/2026-10-19-solidita-harness-sviluppo.md), a secco con un agente finto.

- i profili (`PROFILI_AGENTE`, `agenti_profilo`): quello di serie ha esattamente i valori di
  prima del 22/10 (nessun cambiamento sulla DGX); tutti i profili hanno gli stessi budget in
  token; i tempi degli altri profili rispettano la regola scritta (tetti di sicurezza larghi
  rispetto alla velocità); le chiavi sono campi di Config;
- la configurazione: la riga del locale sceglie il profilo; un tetto scritto nel locale vince
  sul profilo, modello e indirizzo del profilo vincono sul locale ma non sull'ambiente; un nome
  sconosciuto si segnala e non cambia niente; senza profilo valgono le chiavi singole;
- il budget dei token per tipo (`agenti_token_lavoro`) non segue più i minuti; il conto di
  prima (`agenti_token_minuto` scritto) vale com'era, e `agenti_max_token` resta il massimo;
- la prova a secco del criterio: lo stesso lavoro finto con il profilo veloce (70 token/s) e
  con quello lento (12 token/s), su un orologio finto che avanza dei token generati diviso la
  velocità: stesso budget in token, stesse fermate (ragionamento senza strumenti alla stessa
  passata, budget dei token alla stessa passata); contrari: il modello lento con i tempi del
  profilo veloce si ferma prima, per il tempo;
- il tempo della voce non conta: i secondi di voce occupata dell'arbitro (`occupata_s`) durante
  una passata congelata dalla pausa di vLLM vanno in `attesa_voce_s`, fuori dalla guardia dei
  minuti senza strumenti e dal tempo del giro.
"""

import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calliope import config as C  # noqa: E402
from calliope.agenti import ciclo  # noqa: E402
from calliope.agenti.arbitro import Arbitro  # noqa: E402
from calliope.agenti.ciclo import Agente, Lavoro, Limite  # noqa: E402
from calliope.agenti.sandbox import Isolamento, Sandbox  # noqa: E402
from calliope.config import Config  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass
TMP = Path(tempfile.mkdtemp(prefix="calliope-tetti-profilo-"))
errori = 0
T0 = time.perf_counter()
SERIE, LENTO = "qwen3.6-35b-a3b-vllm", "denso-27b-vllm"


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


# ═══════════════════════════ i profili ═══════════════════════════

def prova_profili():
    sezione("i profili: quello di serie uguale a prima, budget in token uguali, tempi larghi")
    # I valori di prima del 22/10, scritti qui a mano: il profilo di serie deve riprodurli,
    # tranne il tempo massimo, 55 minuti invece di 30 (scelta di chi amministra del 22/10:
    # 1,5 × 150 000 / 70 = 53,6, così decide il budget in token)
    prima = {"agenti_max_passi": 24, "agenti_token_passata": 16384,
             "agenti_ragionamento_passata": 8192, "agenti_token_senza_strumenti": 12000,
             "agenti_tempo_max_min": 55.0, "agenti_minuti_senza_strumenti": 5.0,
             "agenti_accettazione_s": 90.0, "agenti_revisore_s": 90.0,
             # 5 000 al minuto per codice ed estensioni, 3 000 per gli altri, × 30 minuti
             "agenti_token_lavoro": {"codice": 150000, "estensione": 150000,
                                     "ricerca": 90000, "documento": 90000, "altro": 90000}}
    serie = C.PROFILI_AGENTE[SERIE]
    verifica("di serie il profilo è quello dell'A3B", Config().agenti_profilo == SERIE)
    verifica("il profilo di serie ha i valori di prima del 22/10 (il tempo massimo a 55 "
             "minuti, scelta di chi amministra), nessuno in più o in meno",
             {k: v for k, v in serie.items() if k not in C._NOTE_PROFILO_AGENTE} == prima,
             str(serie))
    nudo = Config()
    nudo.agenti_profilo = None
    da_campi = {f.name: (f.default_factory() if f.default_factory is not C.MISSING
                         else f.default) for f in C.fields(Config)}
    verifica("…e sono anche i predefiniti della dataclass (con il profilo o senza, uguale)",
             all(da_campi[k] == v for k, v in prima.items()),
             str({k: da_campi[k] for k in prima if da_campi[k] != prima[k]}))
    verifica("il profilo di serie non tocca modello e indirizzo (dgx.yaml o agenti_url)",
             "agenti_url" not in serie and "agenti_modello" not in serie)
    nomi = {f.name for f in C.fields(Config)}
    for nome, p in C.PROFILI_AGENTE.items():
        chiavi = set(p) - C._NOTE_PROFILO_AGENTE
        verifica(f"{nome}: le chiavi sono campi di Config", chiavi <= nomi, str(chiavi - nomi))
        verifica(f"{nome}: stessi budget in token del profilo di serie",
                 all(p[k] == serie[k] for k in ("agenti_token_lavoro", "agenti_max_passi",
                                                "agenti_token_passata",
                                                "agenti_ragionamento_passata",
                                                "agenti_token_senza_strumenti")))
        v = float(p["velocita_token_s"])
        verifica(f"{nome}: la velocità è detta misurata o stimata",
                 p.get("velocita") in ("misurata", "stimata") and v > 0)
        senza = p["agenti_minuti_senza_strumenti"] * 60
        verifica(f"{nome}: la guardia dei minuti senza strumenti è larga (≥ 1,75 volte i "
                 f"token della guardia alla sua velocità)",
                 senza >= 1.75 * p["agenti_token_senza_strumenti"] / v - 1e-6,
                 f"{senza:.0f} s contro {1.75 * p['agenti_token_senza_strumenti'] / v:.0f}")
        sec = 90.0 * 70.0 / v
        verifica(f"{nome}: accettazione e revisore hanno i secondi della loro velocità",
                 p["agenti_accettazione_s"] >= sec - 1e-6 and p["agenti_revisore_s"] >= sec - 1e-6)
        tetto = max(p["agenti_token_lavoro"].values())
        verifica(f"{nome}: il tempo massimo è largo (≥ 1,5 volte il lavoro più grande alla sua "
                 "velocità)", p["agenti_tempo_max_min"] * 60 >= 1.5 * tetto / v - 1e-6,
                 f"{p['agenti_tempo_max_min']} min contro {1.5 * tetto / v / 60:.1f}")
    # Senza eccezioni dal 22/10 (scelta di chi amministra): anche per il codice il budget in
    # token arriva prima del tempo, a ogni profilo (P4 della prima revisione della PR #234)
    verifica("a ogni profilo il lavoro più grande sta nel tempo massimo alla sua velocità",
             all(p["agenti_tempo_max_min"] * 60 * p["velocita_token_s"]
                 > max(p["agenti_token_lavoro"].values()) for p in C.PROFILI_AGENTE.values()))


# ═══════════════════════════ la configurazione ═══════════════════════════

def carica(base: str, locale: str = "", env: dict | None = None):
    d = Path(tempfile.mkdtemp(dir=TMP))
    (d / "calliope.yaml").write_text(base, encoding="utf-8")
    (d / "locale.yaml").write_text(locale, encoding="utf-8")
    vecchie = {k: os.environ.get(k) for k in
               ["CALLIOPE_CONFIG_LOCALE", "CALLIOPE_AGENTI_URL", "CALLIOPE_AGENTI_PROFILO",
                *(env or {})]}
    os.environ["CALLIOPE_CONFIG_LOCALE"] = str(d / "locale.yaml")
    os.environ.pop("CALLIOPE_AGENTI_URL", None)
    os.environ.pop("CALLIOPE_AGENTI_PROFILO", None)
    os.environ.update(env or {})
    avvisi = []
    w = C._warn
    C._warn = avvisi.append
    try:
        return C.load_config(str(d / "calliope.yaml")), avvisi
    finally:
        C._warn = w
        for k, v in vecchie.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def prova_configurazione():
    sezione("la configurazione: una riga del locale, le chiavi singole vincono, l'ambiente")
    esempio = C.example_yaml()
    cfg, _ = carica(esempio)
    verifica("con calliope.yaml uguale all'esempio: il profilo di serie, valori di prima",
             cfg.agenti_profilo == SERIE and cfg.agenti_tempo_max_min == 55.0
             and cfg.agenti_token_lavoro["codice"] == 150000 and not cfg.agenti_token_minuto
             and cfg.agenti_url is None and cfg.agenti_modello is None)
    cfg, avvisi = carica(esempio, "agenti:\n  agenti_profilo: denso-27b-vllm\n")
    verifica("una riga del locale sceglie il profilo lento: modello, indirizzo e tempi insieme",
             cfg.agenti_modello == "denso-27b" and cfg.agenti_url == "http://127.0.0.1:8000/v1"
             and cfg.agenti_tempo_max_min == 375.0 and cfg.agenti_minuti_senza_strumenti == 35.0
             and cfg.agenti_revisore_s == 630.0
             and cfg.agenti_token_lavoro == Config().agenti_token_lavoro,
             str((cfg.agenti_modello, cfg.agenti_url, cfg.agenti_tempo_max_min)))
    verifica("…e lo dice all'avvio", any("profilo «denso-27b-vllm»" in a for a in avvisi),
             str(avvisi[-3:]))
    cfg, avvisi = carica(esempio, "agenti:\n  agenti_profilo: denso-27b-vllm\n"
                                  "  agenti_max_passi: 10\n  agenti_minuti_senza_strumenti: 45\n"
                                  "  agenti_url: http://127.0.0.1:8100/v1\n"
                                  "  agenti_modello: altro\n")
    verifica("un tetto scritto nel locale vince sul profilo (passate 10, guardia 45 minuti), "
             "gli altri dal profilo", cfg.agenti_max_passi == 10
             and cfg.agenti_minuti_senza_strumenti == 45.0 and cfg.agenti_tempo_max_min == 375.0,
             str((cfg.agenti_max_passi, cfg.agenti_minuti_senza_strumenti)))
    verifica("modello e indirizzo del profilo vincono sul locale (la riga cambia modello)",
             cfg.agenti_modello == "denso-27b" and cfg.agenti_url == "http://127.0.0.1:8000/v1")
    verifica("…e l'avvio dice quali tetti vengono dal file",
             any("dal file: agenti_max_passi, agenti_minuti_senza_strumenti" in a
                 for a in avvisi), str(avvisi[-2:]))
    verifica("…e che modello e indirizzo del locale sono sostituiti dal profilo (P6)",
             any("del file sostituite dal profilo: agenti_url, agenti_modello" in a
                 for a in avvisi), str(avvisi[-1:]))
    cfg, avvisi = carica(esempio, "agenti:\n  agenti_profilo: denso-27b-vllm\n"
                                  "  agenti_url: http://127.0.0.1:8000/v1\n")
    verifica("contrario: lo stesso indirizzo nel locale non è «sostituito»",
             not any("sostituite" in a for a in avvisi), str(avvisi[-1:]))
    # agenti_token_minuto nel locale (P2): convertito con i minuti di allora, mai con quelli
    # del profilo, e l'avvio lo dice
    cfg, avvisi = carica(esempio, "agenti:\n  agenti_profilo: denso-27b-vllm\n"
                                  "  agenti_token_minuto:\n    codice: 5000\n")
    verifica("agenti_token_minuto nel locale con il profilo lento: 5 000 × 30 = 150 000 (non "
             "× 375), gli altri tipi dal profilo, il campo vuoto dopo",
             cfg.agenti_token_lavoro["codice"] == 150000
             and cfg.agenti_token_lavoro["ricerca"] == 90000 and cfg.agenti_token_minuto == {},
             str(cfg.agenti_token_lavoro))
    verifica("…e l'avvio lo dice", any("agenti_token_minuto dal file convertito" in a
                                       and "× 30 minuti" in a for a in avvisi),
             str(avvisi[-1:]))
    cfg, avvisi = carica(esempio, "agenti:\n  agenti_tempo_max_min: 20\n"
                                  "  agenti_token_minuto:\n    codice: 5000\n    altro: 2000\n")
    verifica("…con i minuti scritti nel locale, quelli (5 000 × 20, 2 000 × 20)",
             cfg.agenti_token_lavoro["codice"] == 100000
             and cfg.agenti_token_lavoro["altro"] == 40000
             and any("× 20 minuti" in a for a in avvisi), str(cfg.agenti_token_lavoro))
    # L'ambiente si legge quando calliope.config si importa: in un processo nuovo
    import subprocess
    env = dict(os.environ, CALLIOPE_AGENTI_PROFILO="qwen3-coder-next-vllm",
               CALLIOPE_AGENTI_URL="http://127.0.0.1:9999/v1", PYTHONUTF8="1")
    out = subprocess.run(
        [sys.executable, "-c", "from calliope.config import Config; c = Config(); "
         "print(c.agenti_profilo, c.agenti_url, c.agenti_modello, c.agenti_think, "
         "c.agenti_tempo_max_min)"], env=env, capture_output=True, text=True, timeout=60,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).stdout.split()
    verifica("CALLIOPE_AGENTI_PROFILO sceglie il profilo (Coder-Next: modello, senza thinking, "
             "65 minuti), CALLIOPE_AGENTI_URL vince anche sul profilo",
             out == ["qwen3-coder-next-vllm", "http://127.0.0.1:9999/v1", "qwen3-coder-next",
                     "False", "65.0"], str(out))
    cfg, avvisi = carica(esempio, "agenti:\n  agenti_profilo: denso27\n")
    verifica("un nome sconosciuto si segnala (con il più vicino) e non cambia niente",
             cfg.agenti_tempo_max_min == 55.0 and cfg.agenti_url is None
             and any("sconosciuto" in a and "denso-27b-vllm" in a for a in avvisi),
             str(avvisi[-2:]))
    cfg, _ = carica(esempio, "agenti:\n  agenti_profilo: null\n  agenti_tempo_max_min: 12\n")
    verifica("senza profilo valgono le chiavi singole", cfg.agenti_profilo is None
             and cfg.agenti_tempo_max_min == 12.0 and cfg.agenti_max_passi == 24)


# ═══════════════════════════ il budget dei token ═══════════════════════════

def prova_budget():
    sezione("il budget dei token per tipo non segue più i minuti; il conto di prima scritto")
    cfg = Config()
    ag = Agente(cfg, SimpleNamespace(modello="m"), SimpleNamespace(), Arbitro(False, 0),
                log=lambda *a: None)
    t = {tipo: ag.tetto_token(Lavoro("t", tipo, "x"))
         for tipo in ("codice", "estensione", "ricerca", "documento", "altro", "strano")}
    verifica("di serie: 150 000 per codice ed estensioni, 90 000 per gli altri (un tipo che "
             "manca come «altro»)", t == {"codice": 150000, "estensione": 150000,
                                         "ricerca": 90000, "documento": 90000, "altro": 90000,
                                         "strano": 90000}, str(t))
    cfg.agenti_tempo_max_min = 315.0
    ag = Agente(cfg, SimpleNamespace(modello="m"), SimpleNamespace(), Arbitro(False, 0),
                log=lambda *a: None)
    verifica("con più minuti il budget resta lo stesso (prima: 5 000 × 315 = 1 575 000)",
             ag.tetto_token(Lavoro("t", "codice", "x")) == 150000)
    cfg = Config()
    cfg.agenti_token_minuto = {"codice": 5000, "altro": 2000}
    cfg.agenti_tempo_max_min = 375.0
    ag = Agente(cfg, SimpleNamespace(modello="m"), SimpleNamespace(), Arbitro(False, 0),
                log=lambda *a: None)
    verifica("il ciclo non moltiplica mai i token al minuto per i minuti (li converte la "
             "Config all'avvio)", ag.tetto_token(Lavoro("t", "codice", "x")) == 150000)
    cfg = Config()
    cfg.agenti_max_token = 60000
    ag = Agente(cfg, SimpleNamespace(modello="m"), SimpleNamespace(), Arbitro(False, 0),
                log=lambda *a: None)
    verifica("agenti_max_token resta il massimo per tutti",
             ag.tetto_token(Lavoro("t", "codice", "x")) == 60000
             and ag.tetto_token(Lavoro("t", "ricerca", "x")) == 60000)


# ═══════════════════════════ la prova a secco del criterio ═══════════════════════════

class Orologio:
    """L'orologio finto del ciclo: avanza solo quando il modello finto genera (token / velocità
    del modello) e quando qualcuno dorme."""

    def __init__(self):
        self.t = 1_000_000.0

    def time(self):
        return self.t

    def monotonic(self):
        return self.t

    def perf_counter(self):
        return self.t

    def sleep(self, s):
        self.t += max(0.0, float(s))


class Modello:
    """Il modello finto: un copione di passate; ogni passata «dura» eval / velocità secondi
    sull'orologio finto (più un secondo di prefill)."""

    def __init__(self, copione, velocita: float, orologio: Orologio):
        self.copione = list(copione)
        self.v = float(velocita)
        self.o = orologio
        self.visti = []

    def chat(self, body, controlla=None, **kw):
        self.visti.append(body)
        p = self.copione.pop(0) if self.copione else {"testo": "", "eval": 10}
        ev = int(p.get("eval", 10))
        self.o.sleep(1.0 + ev / self.v)
        return {"content": p.get("testo", ""), "eval": ev, "prompt": 10,
                "tool_calls": [{"name": n, "arguments": a} for n, a in p.get("chiamate", ())]}


def con_profilo(nome: str, **sopra) -> Config:
    cfg = Config()
    cfg.agenti_profilo = nome
    C.apply_agenti_profile(cfg)
    cfg.agenti_accettazione = False
    cfg.agenti_revisore = "spento"
    for k, v in sopra.items():
        setattr(cfg, k, v)
    return cfg


def lavora(cfg: Config, velocita: float, copione, nome: str):
    """Il lavoro finto di codice con `cfg`, il modello a `velocita` token/s sull'orologio finto.
    → (esito o tipo del limite, passate, token, minuti dell'orologio)."""
    o = Orologio()
    vero = ciclo.time
    ciclo.time = o
    try:
        cli = Modello(copione, velocita, o)
        ag = Agente(cfg, SimpleNamespace(modello="m"), cli, Arbitro(False, 0), log=lambda *a: None)
        sb = Sandbox(TMP / nome, 30, 512, isolamento=Isolamento("processo", "prova"))
        lav = Lavoro(nome, "codice", "scrivi i moduli")
        lav.inizio = o.time()
        try:
            ris = ag.codice(lav, sb)
            fine = ris.get("esito")
        except Limite as e:
            # La guardia senza strumenti chiude fuori da uno sviluppo senza il tipo (come prima
            # del 22/10): la si riconosce dal motivo
            fine = e.tipo or ("ragionamento" if "senza usare gli strumenti" in str(e)
                              else "limite")
        return fine, lav.passi, lav.token, round((o.t - 1_000_000.0) / 60, 1)
    finally:
        ciclo.time = vero


def scrivi(i: int, ev: int) -> dict:
    return {"eval": ev, "chiamate": [("scrivi_file", {
        "percorso": f"modulo{i}.py", "contenuto": f"VALORE = {i}\n"})]}


def prova_secco():
    sezione("a secco: lo stesso lavoro con il profilo veloce e con quello lento")
    serie, lento = C.PROFILI_AGENTE[SERIE], C.PROFILI_AGENTE[LENTO]
    vs, vl = serie["velocita_token_s"], lento["velocita_token_s"]
    # 1. Il ragionamento a vuoto: 7 000 token senza strumenti a passata. La guardia dei token
    # (12 000) dà la spinta alla seconda e chiude alla terza, con tutti e due
    vuoto = [{"eval": 7000}, {"eval": 7000}, {"eval": 3000}]
    a = lavora(con_profilo(SERIE), vs, vuoto, "vuoto-veloce")
    b = lavora(con_profilo(LENTO), vl, vuoto, "vuoto-lento")
    verifica("ragionamento a vuoto: la stessa fermata (guardia dei token, terza passata, "
             "17 000 token) a 70 e a 10 token/s",
             a[:3] == b[:3] == ("ragionamento", 3, 17000) and b[3] > a[3], f"{a} {b}")
    c = lavora(con_profilo(LENTO, agenti_minuti_senza_strumenti=5.0), vl, vuoto, "vuoto-contrario")
    verifica("contrario: il modello lento con i 5 minuti del profilo veloce si ferma prima, "
             "per il tempo (seconda passata, 14 000 token)", c[:3] == ("ragionamento", 2, 14000),
             str(c))
    # 2. Il budget dei token: 6 000 token a passata con una chiamata, tetto di 60 000 per tutti
    # e due (agenti_max_token). Fermata alla stessa passata, per i token
    lungo = [scrivi(i, 6000) for i in range(20)]
    a = lavora(con_profilo(SERIE, agenti_max_token=60000), vs, lungo, "token-veloce")
    b = lavora(con_profilo(LENTO, agenti_max_token=60000), vl, lungo, "token-lento")
    verifica("budget dei token: la stessa fermata (tetto dei token, 10 passate, 60 000 token)",
             a[:3] == b[:3] == ("token", 10, 60000), f"{a} {b}")
    verifica("…il lento ci mette più minuti, sotto il suo tetto di sicurezza (375)",
             a[3] < 30 and 30 < b[3] < 375, f"{a[3]} {b[3]} minuti")
    c = lavora(con_profilo(LENTO, agenti_max_token=60000, agenti_tempo_max_min=30.0), vl, lungo,
               "token-contrario")
    verifica("contrario: con i 30 minuti del profilo veloce il lento si ferma per il tempo, "
             "con meno token", c[0] == "tempo" and c[2] < 60000, str(c))
    # 3. Le passate: 24 per tutti e due
    corto = [scrivi(i, 500) for i in range(30)]
    a = lavora(con_profilo(SERIE), vs, corto, "passate-veloce")
    b = lavora(con_profilo(LENTO), vl, corto, "passate-lento")
    verifica("tetto delle passate: la stessa fermata (24 passate, 12 000 token)",
             a[:3] == b[:3] == ("passate", 24, 12000), f"{a} {b}")


# ═══════════════════════════ il tempo della voce ═══════════════════════════

def prova_voce():
    sezione("il tempo della voce non conta: arbitro, stream congelato, tempo del giro")
    arb = Arbitro(True, ripresa_s=0.0)
    verifica("arbitro nuovo: 0 secondi di voce", arb.occupata_s() == 0.0)
    arb.voce_occupata()
    time.sleep(0.15)
    a = arb.occupata_s()
    arb.voce_libera(0.1)
    time.sleep(0.4)
    b = arb.occupata_s()
    time.sleep(0.15)
    b2 = arb.occupata_s()
    verifica("i secondi della voce: il turno in corso e la ripresa dopo (0,15 + 0,1), poi fermi",
             0.12 <= a <= 0.3 and 0.22 <= b <= 0.4 and abs(b2 - b) < 0.02,
             f"{a:.2f} {b:.2f} {b2:.2f}")
    arb.voce_occupata()
    time.sleep(0.05)
    arb.voce_libera(0.0)
    c = arb.occupata_s()
    verifica("un secondo turno si somma", 0.05 <= c - b <= 0.3, f"{c - b:.2f}")
    verifica("non condiviso: sempre 0", Arbitro(False, 0).occupata_s() == 0.0)
    # La tenuta massima (la voce che non dice mai «libera»): il conto si ferma lì, e il turno
    # dopo apre un periodo nuovo (mutazioni sopravvissute alla prima revisione della PR #234)
    arb = Arbitro(True, ripresa_s=0.0, tenuta_max_s=0.1)
    arb.voce_occupata()
    time.sleep(0.3)
    x = arb.occupata_s()
    verifica("senza «libera» la voce conta al più la tenuta massima (0,1 s, non 0,3)",
             0.08 <= x <= 0.15, f"{x:.2f}")
    arb.in_pausa()                         # la tenuta scade: l'agente riparte
    arb.voce_occupata()
    time.sleep(0.05)
    arb.voce_libera(0.0)
    y = arb.occupata_s()
    verifica("…e il turno dopo è un periodo nuovo (0,1 + 0,05, non dal primo turno)",
             0.13 <= y <= 0.22, f"{y:.2f}")

    class Congelato:
        """Il modello che resta congelato dalla pausa di vLLM mentre parla la voce: lo stream non
        si chiude (niente controlla), la voce occupa 0,3 s della passata."""

        def __init__(self, arb, n):
            self.arb, self.n = arb, n

        def chat(self, body, controlla=None, **kw):
            self.n -= 1
            self.arb.voce_occupata()
            time.sleep(0.3)
            self.arb.voce_libera(0.0)
            return {"content": "", "eval": 10, "prompt": 10, "tool_calls": []}

    def con_voce(conta: bool):
        cfg = Config()
        cfg.agenti_accettazione = False
        cfg.agenti_revisore = "spento"
        # 0,25 s di guardia: ogni passata ne dura 0,3, tutta della voce
        cfg.agenti_minuti_senza_strumenti = 0.25 / 60
        arb = Arbitro(True, ripresa_s=0.0)
        if not conta:
            arb.occupata_s = lambda: 0.0          # la mutazione: il conto della voce spento
        ag = Agente(cfg, SimpleNamespace(modello="m"), Congelato(arb, 3), arb,
                    log=lambda *a: None)
        sb = Sandbox(TMP / f"voce-{conta}", 30, 512, isolamento=Isolamento("processo", "prova"))
        lav = Lavoro(f"voce-{conta}", "codice", "scrivi")
        lav.inizio = time.time()
        segnali = {}
        try:
            ag.codice(lav, sb)
        except Limite as e:
            segnali["limite"] = e.tipo
        except IndexError:
            pass
        return lav, segnali, ag
    lav, seg, ag = con_voce(True)
    verifica("passate congelate dalla voce: i secondi in attesa_voce_s",
             lav.attesa_voce_s >= 0.6, f"{lav.attesa_voce_s:.2f}")
    verifica("…e la guardia dei minuti senza strumenti non scatta per la voce (nessuna "
             "spinta «senza strumenti»)",
             not (lav.segnali.get("regole") or {}).get("agente_ragionamento_senza_strumenti")
             and seg.get("limite") != "ragionamento", str(lav.segnali.get("regole")))
    verifica("…e il tempo del giro non conta la voce",
             ag.trascorso(lav) < time.time() - lav.inizio - 0.5,
             f"{ag.trascorso(lav):.2f} contro {time.time() - lav.inizio:.2f}")
    lav2, seg2, _ = con_voce(False)
    verifica("contrario (senza il conto della voce): la guardia scatta per il tempo della voce",
             (lav2.segnali.get("regole") or {}).get("agente_ragionamento_senza_strumenti")
             or seg2.get("limite") == "ragionamento", str((lav2.segnali.get("regole"), seg2)))
    # Il giro nuovo di uno sviluppo: la voce del giro di prima resta fuori (attesa_voce0)
    lav3 = Lavoro("g", "codice", "x")
    lav3.inizio = time.time() - 100
    lav3.attesa_voce_s, lav3.attesa_voce0 = 40.0, 0.0
    t1 = Agente.trascorso(lav3)
    lav3.attesa_voce0 = 40.0
    t2 = Agente.trascorso(lav3)
    verifica("il tempo del giro toglie solo la voce del giro (attesa_voce0)",
             59 <= t1 <= 61 and 99 <= t2 <= 101, f"{t1:.1f} {t2:.1f}")
    # «continua» (Lavori.continua) apre il giro nuovo con la voce di prima già fuori
    import queue
    import threading
    from calliope.agenti.servizio import Lavori
    finto = SimpleNamespace(_lock=threading.Lock(), in_tappa=lambda lav: True, corrente=None,
                            log=lambda *a: None, _coda=queue.Queue(), _salva_stato=lambda: None,
                            agente=SimpleNamespace(tempo_max_s=1800))
    lav4 = Lavoro("c", "codice", "x")
    lav4.inizio, lav4.attesa_voce_s, lav4.segnali = time.time() - 500, 120.0, {}
    frase = Lavori.continua(finto, lav4)
    verifica("«continua» non dice il tetto di sicurezza come durata (P6: «un altro giro di "
             "5 ore»)", "un altro giro di lavoro" in frase and "minut" not in frase
             and " ore" not in frase, frase)
    verifica("«continua»: il giro nuovo parte con la voce del giro di prima fuori",
             lav4.attesa_voce0 == 120.0 and -1 < Agente.trascorso(lav4) < 2,
             f"{lav4.attesa_voce0} {Agente.trascorso(lav4):.1f}")


# ═══════════════════════════ il ripiego senza la pausa di vLLM ═══════════════════════════

class Ripiego:
    """Il modello senza la pausa di vLLM (P1 della prima revisione della PR #234): genera
    `gen_s` secondi, poi la voce si sveglia, lo stream resta ancora `prima_s` secondi fino al
    pezzo dopo, dove `controlla` lo chiude (Interrotto); la voce dice «libera» dopo `voce_s`."""

    def __init__(self, arb, gen_s, prima_s, voce_s):
        self.arb, self.gen_s, self.prima_s, self.voce_s = arb, gen_s, prima_s, voce_s
        self.giri = 0

    def interrompi(self, tid=None):
        pass

    def chat(self, body, controlla=None, **kw):
        import threading
        self.giri += 1
        time.sleep(self.gen_s)
        self.arb.voce_occupata()
        threading.Timer(self.voce_s, lambda: self.arb.voce_libera(0.0)).start()
        time.sleep(self.prima_s)
        controlla()
        raise AssertionError("controlla doveva fermare lo stream")


def ripiego(nome, gen_s, prima_s, voce_s, minuti, tappe=False, cli=None, arb=None,
            max_passi=None):
    import threading
    cfg = Config()
    cfg.agenti_accettazione = False
    cfg.agenti_revisore = "spento"
    cfg.agenti_tempo_max_min = minuti
    if max_passi:
        cfg.agenti_max_passi = max_passi
    arb = arb or Arbitro(True, ripresa_s=0.0)
    cli = cli or Ripiego(arb, gen_s, prima_s, voce_s)
    ag = Agente(cfg, SimpleNamespace(modello="m"), cli, arb, log=lambda *a: None)
    sb = Sandbox(TMP / nome, 30, 512, isolamento=Isolamento("processo", "prova"))
    lav = Lavoro(nome, "codice", "scrivi")
    lav.tappe = tappe
    lav.inizio = time.time()
    # Un lavoro che non si ferma da sé (la mutazione) lo ferma la prova
    guardia = threading.Timer(12.0, lav.annulla.set)
    guardia.start()
    t0 = time.monotonic()
    try:
        ris = ag.codice(lav, sb)
        fine = (f"tappa {ris.get('tipo_limite')}: {ris.get('motivo')}"
                if ris.get("esito") == "tappa" else "consegnato")
    except Limite as e:
        fine = str(e)
    except Exception as e:  # noqa: BLE001 — Annullato
        fine = type(e).__name__
    finally:
        guardia.cancel()
    return fine, cli.giri, lav, time.monotonic() - t0


def prova_ripiego():
    sezione("il ripiego senza la pausa di vLLM: il tempo massimo resta un tetto")
    # 1. Ogni passata genera 0,3 s, poi la voce la ferma (0,2 s prima del pezzo dopo, 0,25 di
    # voce in tutto): il tempo massimo di 1 s conta i secondi generati, e il lavoro si ferma
    fine, giri, lav, dt = ripiego("ripiego", 0.3, 0.2, 0.25, 1 / 60)
    verifica("passate fermate dalla voce senza la pausa: il lavoro si ferma al tempo massimo "
             "(conta la generazione persa)", "minuti del lavoro" in fine and 3 <= giri <= 6,
             f"{fine} dopo {giri} passate, {dt:.1f} s")
    verifica("…della passata fermata è della voce solo la parte con la voce (~0,25 s a passata, "
             "non tutta la passata, non due volte)",
             0.15 * giri <= lav.attesa_voce_s <= 0.4 * giri, f"{lav.attesa_voce_s:.2f} su {giri}")
    verifica("…e la generazione persa resta fuori dalla sola guardia senza strumenti "
             "(`rifatte_s` ~0,3 s a passata)", 0.25 * giri <= lav.rifatte_s <= 0.5 * giri,
             f"{lav.rifatte_s:.2f}")
    # 2. Quasi tutta voce: 0,02 s generati, 0,3 di voce. Il tempo dell'agente non avanza, ma
    # all'orologio vero il giro si ferma al doppio del tempo massimo
    fine, giri, lav, dt = ripiego("orologio", 0.02, 0.15, 0.3, 1 / 60)
    verifica("quasi tutta voce: il tetto all'orologio vero (2 × 1 s, voce compresa) ferma il "
             "lavoro, con la frase per la persona (Q3)", fine == ciclo.MOTIVO_OROLOGIO and dt < 4,
             f"{fine} dopo {giri} passate, {dt:.1f} s")
    # 3. Il massimo delle rifatte: con tempi larghi la stessa passata al più 10 volte
    fine, giri, lav, dt = ripiego("rifatte", 0.01, 0.01, 0.02, 10.0)
    verifica("la stessa passata fermata dalla voce al più 10 volte, poi il lavoro si ferma, "
             "con la frase per la persona (Q3)", fine == ciclo.MOTIVO_RIFATTE and giri == 10,
             f"{fine} dopo {giri} passate")
    verifica("le frasi per la persona senza parole interne («passata», «la voce», "
             "«orologio»)", not any(p in m for m in (ciclo.MOTIVO_RIFATTE, ciclo.MOTIVO_OROLOGIO)
                                    for p in ("passata", "la voce", "orologio")))
    # 4. Le rifatte si contano per passata (Q5): 6 fermate per passata, due passate riuscite,
    # e il lavoro arriva al tetto delle passate, non a quello delle rifatte
    class SeiPerPassata(Ripiego):
        def chat(self, body, controlla=None, **kw):
            self.giri += 1
            if self.giri % 7:
                self.arb.voce_occupata()
                self.arb.voce_libera(0.0)
                raise ciclo.Interrotto()
            return {"content": "", "eval": 10, "prompt": 10, "tool_calls": [
                {"name": "scrivi_file", "arguments": {"percorso": f"m{self.giri}.py",
                                                      "contenuto": "X = 1\n"}}]}
    arb = Arbitro(True, ripresa_s=0.0)
    fine, giri, lav, dt = ripiego("rifatte-passata", 0, 0, 0, 10.0, arb=arb,
                                  cli=SeiPerPassata(arb, 0, 0, 0), max_passi=2)
    verifica("le rifatte per passata: 6 a passata in due passate (12 in tutto) non fermano il "
             "lavoro, che arriva al tetto delle passate", "passate" in fine and giri == 14,
             f"{fine} dopo {giri}")
    # 5. In uno sviluppo i due tetti sono una tappa «tempo» (Q2), con il perché vero (Q3)
    for nome, args, perche, motivo in (
            ("tappa-orologio", (0.02, 0.15, 0.3, 1 / 60), "orologio", ciclo.MOTIVO_OROLOGIO),
            ("tappa-rifatte", (0.01, 0.01, 0.02, 10.0), "voce", ciclo.MOTIVO_RIFATTE)):
        fine, giri, lav, dt = ripiego(nome, *args, tappe=True)
        tp = (lav.segnali or {}).get("tempo_perche") or {}
        verifica(f"in uno sviluppo il tetto ({perche}) è una tappa «tempo»",
                 fine.startswith("tappa tempo") and tp.get("perche") == perche
                 and tp.get("giro") == 1, f"{fine} {tp}")
        from calliope.sviluppo import Sviluppi
        lav.stato = "in_attesa"
        lav.risultato = {"esito": "tappa", "tipo_limite": "tempo"}
        finto = SimpleNamespace(lavoro_attivo=lambda sv: False, _lavoro=lambda i, lav=lav: lav)
        sv = SimpleNamespace(fase="sviluppo", lavoro=lav.id, nota="")
        frase = Sviluppi.motivo_arresto(finto, sv, voce=True)
        verifica(f"…e a voce il perché vero ({perche}), non «è finito il tempo del giro»",
                 motivo in frase and "tempo del giro" not in frase, frase)
    lav.risultato = {"esito": "tappa", "tipo_limite": "tempo"}
    lav.giro = 2
    frase = Sviluppi.motivo_arresto(finto, sv, voce=True)
    verifica("contrario: il perché di un giro di prima non vale (al giro 2 «tempo del giro»)",
             "tempo del giro" in frase, frase)


def prova_attesa_scadenza():
    sezione("l'attesa della voce ha la scadenza dell'orologio; il diario; l'avviso")
    # Q1: la voce occupata per 3 s, tempo massimo 1 s (orologio 2 s): l'attesa smette a 2 s e
    # nessuna passata parte
    import threading
    arb = Arbitro(True, ripresa_s=0.0)

    class Pronto:
        giri = 0

        def chat(self, body, controlla=None, **kw):
            Pronto.giri += 1
            return {"content": "", "eval": 10, "prompt": 10, "tool_calls": []}
    arb.voce_occupata()
    threading.Timer(3.0, lambda: arb.voce_libera(0.0)).start()
    fine, giri, lav, dt = ripiego("scadenza", 0, 0, 0, 1 / 60, cli=Pronto(), arb=arb)
    verifica("la voce occupata oltre l'orologio: l'attesa smette alla scadenza e nessuna passata "
             "parte (Q1)", fine == ciclo.MOTIVO_OROLOGIO and Pronto.giri == 0 and dt < 2.7,
             f"{fine} passate {Pronto.giri}, {dt:.1f} s")
    time.sleep(1.2)
    arb2 = Arbitro(True, ripresa_s=0.0)
    arb2.voce_occupata()
    t0 = time.monotonic()
    w = arb2.attendi(None, fino=time.monotonic() + 0.2)
    verifica("Arbitro.attendi con la scadenza: smette anche con la voce occupata",
             0.15 <= w <= 0.4 and time.monotonic() - t0 < 0.5, f"{w:.2f}")
    arb2.voce_libera(0.0)
    # Q2: il diario con il tetto «tempo» torna estrattivo; un altro tetto passa oltre
    cfg = Config()
    ag = Agente(cfg, SimpleNamespace(modello="m"), SimpleNamespace(), Arbitro(False, 0),
                log=lambda *a: None)
    lav = Lavoro("d", "codice", "x")
    lav.inizio = time.time()
    scrivi = ag._diario_modello(lav)

    def tempo(*a, **k):
        raise Limite(ciclo.MOTIVO_RIFATTE, tipo="tempo")
    ag.passata = tempo
    verifica("il diario fermato dal tetto «tempo» torna estrattivo (None, Q2)",
             scrivi("passi", None) is None and lav.passo != "riordina gli appunti del lavoro")

    def token(*a, **k):
        raise Limite("token finiti", tipo="token")
    ag.passata = token
    try:
        scrivi("passi", None)
        alzato = False
    except Limite:
        alzato = True
    verifica("contrario: il tetto dei token nel diario passa oltre, come prima", alzato)
    # Q4: l'avviso di chiusura vicino al tetto all'orologio
    cfg = Config()
    cfg.agenti_tempo_max_min = 1.0              # orologio a 120 s
    ag = Agente(cfg, SimpleNamespace(modello="m"), SimpleNamespace(), Arbitro(False, 0),
                log=lambda *a: None)
    vicino = Lavoro("a", "codice", "x")
    vicino.inizio, vicino.attesa_voce_s = time.time() - 108, 100.0   # trascorso 8 s
    lontano = Lavoro("b", "codice", "x")
    lontano.inizio, lontano.attesa_voce_s = time.time() - 60, 55.0
    verifica("l'avviso di chiusura all'85 % del tetto all'orologio (Q4; contrario: a metà)",
             ag._avviso_fine(vicino) is not None and ag._avviso_fine(lontano) is None)
    quasi = Lavoro("q", "codice", "x")
    quasi.inizio, quasi.attesa_voce_s = time.time() - 115, 110.0
    verifica("…e vicino al tetto all'orologio niente più diario dal modello (_resta_tempo; "
             "contrario: a metà)", not ag._resta_tempo(quasi) and ag._resta_tempo(lontano))
    # Q5: l'orologio senza l'attesa della persona, e dal giro
    lav = Lavoro("o", "codice", "x")
    lav.inizio, lav.attesa_s, lav.attesa0 = time.time() - 1000, 600.0, 0.0
    o1 = Agente.orologio(lav)
    lav.giro_inizio, lav.attesa0 = time.time() - 100, 600.0
    o2 = Agente.orologio(lav)
    verifica("l'orologio non conta l'attesa di una risposta della persona (1000 − 600) e "
             "riparte dal giro nuovo (100)", 398 <= o1 <= 402 and 98 <= o2 <= 102,
             f"{o1:.0f} {o2:.0f}")
    lav.attesa_voce_s = 5000.0
    try:
        ag._tetti(lav)
        fermo = False
    except Limite:
        fermo = True
    verifica("…e un giro nuovo dopo un lavoro lungo non si ferma subito (contrario dell'orologio "
             "dall'inizio)", not fermo)


def prova_frase_giro():
    sezione("la frase all'agente al giro nuovo: le passate, non i minuti")
    cfg = Config()
    cfg.agenti_accettazione = False
    cfg.agenti_revisore = "spento"
    cfg.agenti_max_passi = 2
    o = Orologio()
    copione = [scrivi(i, 100) for i in range(6)]
    cli = Modello(copione, 70.0, o)
    ag = Agente(cfg, SimpleNamespace(modello="m"), cli, Arbitro(False, 0), log=lambda *a: None)
    sb = Sandbox(TMP / "frase-giro", 30, 512, isolamento=Isolamento("processo", "prova"))
    lav = Lavoro("fg", "codice", "scrivi i moduli")
    lav.tappe, lav.inizio = True, time.time()
    ris = ag.codice(lav, sb)
    lav.passi0, lav.token0, lav.giro, lav.giro_inizio = lav.passi, lav.token, 2, time.time()
    lav.risposta, lav.avvisato = "continua", False
    try:
        ag.codice(lav, sb)
    except Limite:
        pass
    testi = [m.get("content") or "" for b in cli.visti for m in b.get("messages", [])
             if m.get("role") == "user"]
    verifica("al giro nuovo «Hai un altro giro di lavoro (2 passate).», senza i minuti (P6)",
             ris.get("esito") == "tappa"
             and any("Hai un altro giro di lavoro (2 passate). Riprendi" in t for t in testi)
             and not any("minuti). Riprendi" in t for t in testi),
             str([t[:80] for t in testi if "altro giro" in t]))


def prova_scheda():
    sezione("la scheda: i minuti senza la voce")
    from calliope.agenti.avanzamento import Avanzamento, _Segue
    lav = Lavoro("s", "codice", "x")
    lav.inizio = time.time() - 100
    lav.stato, lav.attesa_voce_s = "in_corso", 40.0
    finto = SimpleNamespace(tetti=lambda lav=None: (24, 150000, 3300))
    try:
        av = Avanzamento._istantanea(finto, _Segue(lav), False)
        t = av["trascorso_s"]
    except Exception as e:  # noqa: BLE001
        t = repr(e)
    verifica("la scheda mostra i minuti che contano per il tetto (100 s meno 40 di voce)",
             isinstance(t, float) and 59 <= t <= 61, str(t))


if __name__ == "__main__":
    prova_profili()
    prova_configurazione()
    prova_budget()
    prova_secco()
    prova_voce()
    prova_ripiego()
    prova_attesa_scadenza()
    prova_frase_giro()
    prova_scheda()
    print("\n" + ("TUTTO OK" if not errori else f"{errori} ERRORI"))
    sys.exit(1 if errori else 0)
