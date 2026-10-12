"""Banco della temperatura e del presence_penalty dell'agente (12/10/2026 sera, flusso
dell'agente a fasi, parte 1; ricerca docs/ricerche/2026-10-12-flusso-agente-fasi.md § 4.1 e
§ 5.3, domanda 6 accettata da chi amministra; area agenti-estensioni).

La scheda di Qwen3.6-35B-A3B consiglia, con il ragionamento acceso sul codice, temperatura
**0,6** e presence_penalty **0**; da noi `agenti_temperatura` è **0,4** e
`agenti_presence_penalty` 0 per «codice» e 0,5 per «estensione» (misurato l'11/10 su una sola
passata, prove/manuali/misura_presence_penalty.py). Qui si confrontano **lavori interi**, non
una passata: per ogni combinazione di temperatura e presence_penalty, tre casi veri riscritti
con nomi di fantasia, ripetuti:

1. **porte** (gioco, correzione): il gioco delle porte di Borgofiore con il difetto vero del
   12/10 (logica.js restituisce l'esito annidato, gioco.js lo legge al primo livello: niente
   mostro, sempre «Nessun punto!»), e la segnalazione della persona. Accettazione: un test
   nascosto che apre il gioco nel DOM finto (apriGioco), tocca «Inizia» e la prima porta e
   legge «Fantasmino» e «+3 punti».
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

**Sulla DGX quando è libera** (nessun lavoro dell'agente in corso: usa lo stesso vLLM e il
container della sandbox), dalla cartella dei dati, con l'interprete di Calliope. Non cambia la
configurazione di nessuno (i valori si cambiano solo in memoria), i file restano nella cartella
d'uscita:

    cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale) \\
        && $V/.venv/bin/python $V/prove/manuali/banco_temperatura.py \\
           [--temperature 0.4,0.6] [--presence 0,0.5] [--ripetizioni 2] \\
           [--casi porte,convertitore,programma] [--minuti 20] [--uscita ~/banco-temperatura]

A secco (nessun modello, anche sul portatile: il docker finto e il Node della macchina), per
controllare il banco stesso: ogni accettazione fallisce sul punto di partenza e passa sulla
soluzione di riferimento.

    python prove/manuali/banco_temperatura.py --secco

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


PROBLEMA_PORTE = ("toccando una porta non si vede nessun mostro e non si prendono punti: "
                  "esce sempre «Nessun punto!»")
COMPITO_PORTE = ("Il gioco «Le porte di Borgofiore» per 2 giocatori: si tocca Inizia, poi a "
                 "turno ogni giocatore tocca una porta; dietro c'è un mostro che vale dei punti "
                 "(il Fantasmino 3, il Pipistrello 2) o una caramella che non ne vale. Dopo ogni "
                 "porta si vede cosa c'era dietro, con il nome, e i punti presi («+3 punti!» o "
                 "«Nessun punto!»), e il punteggio dei giocatori.")
ACCETTAZIONE_PORTE = """const { test } = require("node:test");
const assert = require("node:assert");
test("ACC porte: toccando la prima porta si vedono il mostro e i suoi punti", async () => {
  const g = await apriGioco({ giocatori: 2, seme: 3 });
  await g.tocca("Inizia");
  const porte = g.trova(".porta");
  if (porte.length) await g.tocca(porte[0]); else await g.tocca("Porta 1");
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
    prima = {"logica.js": F.LOGICA_PORTE, "gioco.js": F.GIOCO_ROTTO,
             "logica.test.js": F.TEST_LOGICA_PORTE,
             "manifesto.json": json.dumps(F.MANIFESTO_PORTE, ensure_ascii=False, indent=1)}
    return {
        "porte": {"tipo": "estensione", "gioco": True, "correzione": True,
                  "estensione": F.MANIFESTO_PORTE["nome"], "compito": COMPITO_PORTE,
                  "problema": PROBLEMA_PORTE, "prima": prima,
                  "accettazione": ("accettazione_banco.test.js", ACCETTAZIONE_PORTE),
                  "riferimento": {**prima, "gioco.js": F.GIOCO_GIUSTO}},
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
        shutil.copy(RADICE / "calliope" / "estensioni" / "_ospite.py",
                    sb.root / "calliope_estensione.py")
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
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + ("TUTTO OK" if not errori else f"{errori} ERRORI"))
    return 1 if errori else 0


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


def un_lavoro(svc, cfg, uscita: Path, nome: str, caso: dict, etichetta: str) -> dict:
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
    t0 = time.time()
    svc.avvia(lav)
    aspetta(svc, lav, cfg.agenti_tempo_max_min * 60 + 180)
    minuti = (time.time() - t0) / 60
    ris = lav.risultato or {}
    # Senza la cartella del risultato non si prende quella del banco (12/10: copiava il banco
    # dentro sé stesso fino a «troppi file»)
    cartella = Path(ris["cartella"]) if ris.get("cartella") else None
    iso = svc.scegli_isolamento()
    k = [0]

    def nuova():
        k[0] += 1
        return Sandbox(uscita / "verifica" / f"{etichetta}-{nome}-{lav.id}-{k[0]}", 30, 1024,
                       isolamento=iso, linguaggi=svc.isolamenti)
    acc = accettazione(nuova, file_di(cartella), caso) if cartella and cartella.is_dir() else {
        "verde": False, "esito": None, "uscita": "nessuna cartella"}
    seg = segnali_giro(lav, cfg.agenti_max_passi)
    fatto = (ris.get("esito") == "fatto" or lav.stato == "fatto")
    riga = {"caso": nome, "variante": etichetta, "lavoro": lav.id, "stato": lav.stato,
            "esito": ris.get("esito"), "motivo": ris.get("motivo"),
            "riuscito": bool(fatto and acc["verde"]), "accettazione": acc["verde"],
            "accettazione_esito": acc["esito"], "passate": lav.passi, "token": lav.token,
            "ragionamento": lav.ragionamento, "minuti": round(minuti, 2),
            "ripetizioni": seg.get("ripetizioni", 0), "senza_novita": seg.get("senza_novita", 0),
            "a_vuoto": seg.get("a_vuoto", False), "test_agente": ris.get("test"),
            "riproduzione": (getattr(lav, "riproduzione", None) or {}).get("stato"),
            "regole": dict(((lav.segnali or {}).get("regole") or {})),
            "cartella": str(cartella)}
    if not acc["verde"]:
        riga["accettazione_uscita"] = acc["uscita"][-600:]
    return riga


def tabella(righe: list[dict]):
    print("\nvariante                caso          riusciti  acc.  passate  token(med)  "
          "giri a vuoto  minuti(med)")
    chiavi = sorted({(r["variante"], r["caso"]) for r in righe})
    for v, c in chiavi:
        rr = [r for r in righe if r["variante"] == v and r["caso"] == c]
        med = lambda k: statistics.median([r[k] for r in rr]) if rr else 0  # noqa: E731
        print(f"{v:<23} {c:<13} {sum(r['riuscito'] for r in rr)}/{len(rr):<7} "
              f"{sum(r['accettazione'] for r in rr)}/{len(rr):<3} {med('passate'):>7} "
              f"{med('token'):>10} {sum(r['ripetizioni'] + (1 if r['a_vuoto'] else 0) for r in rr):>13} "
              f"{med('minuti'):>11}")
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
    ap.add_argument("--temperature", default="0.4,0.6")
    ap.add_argument("--presence", default="0,0.5")
    ap.add_argument("--ripetizioni", type=int, default=2)
    ap.add_argument("--casi", default="porte,convertitore,programma")
    ap.add_argument("--minuti", type=float, default=20.0, help="tetto di tempo per lavoro")
    ap.add_argument("--uscita")
    args = ap.parse_args(argv)
    if args.secco:
        return secco()
    from calliope.agenti import Lavori, carica
    from calliope.config import load_config
    cfg = load_config()
    cfg.agenti_conferma = "mai"
    cfg.agenti_tempo_max_min = args.minuti
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
    temperature = [float(x) for x in args.temperature.split(",")]
    presenze = [float(x) for x in args.presence.split(",")]
    print(f"Banco della temperatura: agente {imp.modello}; temperature {temperature}, "
          f"presence_penalty {presenze}, {args.ripetizioni} ripetizioni, casi {scelti}; "
          f"risultati in {uscita}", flush=True)
    righe = []
    t0 = time.time()
    vecchie = (cfg.agenti_temperatura, dict(cfg.agenti_presence_penalty))
    try:
        for rip in range(args.ripetizioni):
            for t in temperature:
                for pp in presenze:
                    etichetta = f"t={t:g} pp={pp:g}"
                    # Solo in memoria: il servizio e l'agente leggono cfg a ogni passata
                    cfg.agenti_temperatura = t
                    cfg.agenti_presence_penalty = {k: pp for k in vecchie[1]}
                    for nome in scelti:
                        print(f"\n— {etichetta}, {nome}, ripetizione {rip + 1}", flush=True)
                        r = un_lavoro(svc, cfg, uscita, nome, tutti[nome], etichetta)
                        righe.append(r)
                        print(f"{'ok ' if r['riuscito'] else 'NO '} {nome} {etichetta}: "
                              f"accettazione {'verde' if r['accettazione'] else 'rossa'}, "
                              f"{r['passate']} passate, {r['token']} token, "
                              f"{r['minuti']} min, giri a vuoto {r['ripetizioni']}"
                              f"{' (a vuoto)' if r['a_vuoto'] else ''}, esito {r['esito']}"
                              + (f", riproduzione {r['riproduzione']}" if r["riproduzione"]
                                 else ""), flush=True)
                        (uscita / "righe.json").write_text(json.dumps(
                            righe, ensure_ascii=False, indent=1), encoding="utf-8")
    finally:
        cfg.agenti_temperatura, cfg.agenti_presence_penalty = vecchie
        svc.close()
    tabella(righe)
    riepilogo = {"agente": imp.modello, "data": datetime.datetime.now().isoformat(
        timespec="seconds"), "temperature": temperature, "presence": presenze,
        "ripetizioni": args.ripetizioni, "casi": scelti,
        "minuti": round((time.time() - t0) / 60, 1), "righe": righe}
    (uscita / "riepilogo.json").write_text(json.dumps(riepilogo, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    print(f"\nRiepilogo in {uscita / 'riepilogo.json'} ({riepilogo['minuti']} minuti)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
