"""Prova a secco del flusso dell'agente a fasi, parte 1 (12/10/2026 sera; ricerca
docs/ricerche/2026-10-12-flusso-agente-fasi.md, area agenti-estensioni e giochi; caso vero: il
gioco delle porte del 12/10, qui con nomi di fantasia).

1. **La correzione parte da un test che fallisce** (calliope/agenti/riproduzione.py):
   - a. il controllo sugli artefatti: un test nuovo che fallisce sulla versione di prima →
     «riprodotto»; i contrari: codice uguale (anche con un file di prova in più), nessun test
     nuovo, un test nuovo che passa anche prima, nessun file di partenza;
   - b. il ciclo vero con un cliente finto: la consegna senza test torna all'agente una volta,
     con il test giusto passa; senza mai il test la seconda consegna va avanti segnata; un
     lavoro che non è una correzione non si controlla; senza passate non si rimanda;
   - c. la frase a voce: «non sono riuscita a riprodurre il problema: me lo descrivi in un altro
     modo?» con la correzione in sospeso; il codice uguale lo dice; contrario: riprodotto →
     come sempre.

    python prove/prova_fasi_agente.py
"""

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_agente_guida as G  # noqa: E402

errori = 0
T0 = time.perf_counter()


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


# ═══════════════════════════ 1. la correzione parte da un test rosso ═══════════════════════════

CALCOLA_ROTTO = "def somma(a, b):\n    return a - b\n"
CALCOLA_GIUSTO = "def somma(a, b):\n    return a + b\n"
TEST_VECCHIO = ("import unittest\nfrom calcola import somma\n\n\nclass P(unittest.TestCase):\n"
                "    def test_zero(self):\n        self.assertEqual(somma(0, 0), 0)\n")
# Riproduce il difetto segnalato («due più tre fa meno uno»): fallisce sul codice di prima
TEST_ROSSO = TEST_VECCHIO + ("\n    def test_due_piu_tre(self):\n"
                             "        self.assertEqual(somma(2, 3), 5)\n")
# Un test nuovo che passa anche sul codice di prima: non riproduce niente
TEST_VERDE = TEST_VECCHIO + ("\n    def test_tre_meno_tre(self):\n"
                             "        self.assertEqual(somma(3, 3) - 6 + 6, somma(3, 3))\n")
PRIMA = {"calcola.py": CALCOLA_ROTTO, "test_calcola.py": TEST_VECCHIO}


def _lav(correzione=True, prima=PRIMA, problema="due più tre fa meno uno"):
    from calliope.agenti.ciclo import Lavoro
    lav = Lavoro("C1", "codice", "una funzione che somma")
    lav.correzione = correzione
    lav.problema_correzione = problema
    lav.file_iniziali = dict(prima or {})
    return lav


def _sb(tmp: Path, nome: str, file: dict):
    sb = G.sandbox(tmp, nome)
    for k, v in file.items():
        sb.scrivi(k, v)
    return sb


def prova_riproduzione(tmp: Path):
    sezione("1a. la correzione: il controllo sugli artefatti")
    from calliope.agenti.riproduzione import controlla, messaggio_agente
    casi = [
        ("un test nuovo che fallisce prima e passa adesso → riprodotto", "rosso",
         {"calcola.py": CALCOLA_GIUSTO, "test_calcola.py": TEST_ROSSO}, PRIMA, "riprodotto"),
        ("contrario: il codice uguale (cambiato solo il test) → uguale", "uguale",
         {"calcola.py": CALCOLA_ROTTO, "test_calcola.py": TEST_ROSSO}, PRIMA, "uguale"),
        ("contrario: un file di prova dell'agente non cambia il codice → uguale", "prova",
         {"calcola.py": CALCOLA_ROTTO, "test_calcola.py": TEST_ROSSO,
          "prova_somma.py": "print(1)\n"}, PRIMA, "uguale"),
        ("contrario: il codice corretto ma nessun test nuovo → nessun_test", "senza",
         {"calcola.py": CALCOLA_GIUSTO, "test_calcola.py": TEST_VECCHIO}, PRIMA, "nessun_test"),
        ("contrario: un test nuovo che passa anche prima → passa_prima", "verde",
         {"calcola.py": CALCOLA_GIUSTO, "test_calcola.py": TEST_VERDE}, PRIMA, "passa_prima"),
        ("un file di test nuovo accanto a quello di prima → riprodotto", "nuovo_file",
         {"calcola.py": CALCOLA_GIUSTO, "test_calcola.py": TEST_VECCHIO,
          "test_segnalazione.py": TEST_ROSSO}, PRIMA, "riprodotto"),
        ("nessun file di partenza → saltato (la consegna va avanti)", "vuoto",
         {"calcola.py": CALCOLA_GIUSTO, "test_calcola.py": TEST_ROSSO}, {}, "saltato"),
    ]
    for nome, cart, ora, prima, atteso in casi:
        sb = _sb(tmp, cart, ora)
        e = controlla(_lav(prima=prima), sb, log=lambda *_: None)
        verifica(nome, e["stato"] == atteso, str(e)[:300])
        if cart == "rosso":
            verifica("…solo il file nuovo o cambiato, e la sandbox di prima tolta",
                     e["test"] == ["test_calcola.py"]
                     and not (sb.root.parent / "rosso-prima").exists(), str(e["test"]))
    m = messaggio_agente({"stato": "passa_prima", "test": ["test_calcola.py"]},
                         "due più tre fa meno uno")
    verifica("il rimando dice quale test, «versione di PRIMA» e il problema",
             "test_calcola.py" in m and "versione di PRIMA" in m and "due più tre" in m, m)
    m = messaggio_agente({"stato": "nessun_test"}, "", gioco=True)
    verifica("…senza test: «prima scrivi un test», e per un gioco ciò che gioco.js mostra",
             "prima scrivi un test" in m and "gioco.js" in m, m)


def prova_ciclo(tmp: Path):
    sezione("1b. il ciclo vero: la consegna di una correzione")
    scrivi = lambda p, c: {"name": "scrivi_file",  # noqa: E731
                           "arguments": {"percorso": p, "contenuto": c}}
    consegna = {"name": "consegna", "arguments": {"riassunto": "Corretto.", "esito": "fatto"}}
    test = {"name": "esegui_test", "arguments": {}}
    # Prima consegna senza test nuovo; il rimando; poi il test rosso e la consegna
    cli = G._Copione([[scrivi("calcola.py", CALCOLA_GIUSTO)], [test], [consegna],
                      [scrivi("test_calcola.py", TEST_ROSSO)], [test], [consegna]])
    log = []
    ag = G.agente(cli, log)
    sb = _sb(tmp, "ciclo1", PRIMA)
    lav = _lav()
    ris = ag.codice(lav, sb)
    tool = [json.loads(m["content"]) for m in lav.contesto["messages"]
            if m.get("role") == "tool" and m.get("tool_name") == "consegna"]
    verifica("la prima consegna senza test torna all'agente: «non hai scritto né cambiato un "
             "test»", len(tool) == 2 and tool[0].get("consegna") == "rifiutata"
             and "non hai scritto né cambiato un test" in tool[0].get("errore", ""),
             str(tool)[:400])
    verifica("…con il test che riproduce, la seconda passa: riprodotto",
             ris.get("esito") == "fatto" and tool[1].get("ok") is True
             and lav.riproduzione.get("stato") == "riprodotto"
             and lav.riproduzione.get("rimandi") == 1, str(lav.riproduzione))
    verifica("…la regola nel log e nei segnali",
             any("correzione_rimandata" in x for x in log)
             and lav.segnali.get("regole", {}).get("correzione_rimandata") == 1, str(log[-4:]))
    # Mai il test: la seconda consegna va avanti, segnata
    cli = G._Copione([[scrivi("calcola.py", CALCOLA_GIUSTO)], [consegna], [consegna]])
    log = []
    ag = G.agente(cli, log)
    sb = _sb(tmp, "ciclo2", PRIMA)
    lav = _lav()
    ris = ag.codice(lav, sb)
    verifica("senza mai il test: rimandata una volta, poi la consegna va avanti segnata "
             "«nessun_test»", ris.get("esito") == "fatto"
             and lav.riproduzione.get("stato") == "nessun_test"
             and lav.segnali.get("regole", {}).get("correzione_non_riprodotta") == 1,
             str(lav.riproduzione))
    # Contrari: non è una correzione; non restano passate
    cli = G._Copione([[scrivi("calcola.py", CALCOLA_GIUSTO)], [consegna]])
    ag = G.agente(cli, [])
    sb = _sb(tmp, "ciclo3", PRIMA)
    lav = _lav(correzione=False)
    ris = ag.codice(lav, sb)
    verifica("contrario: un lavoro che non è una correzione non si controlla",
             ris.get("esito") == "fatto" and not getattr(lav, "riproduzione", None)
             and len(cli.corpi) == 2)
    cli = G._Copione([[scrivi("calcola.py", CALCOLA_GIUSTO)], [consegna]])
    ag = G.agente(cli, [])
    ag.max_passi = 3
    sb = _sb(tmp, "ciclo4", PRIMA)
    lav = _lav()
    ris = ag.codice(lav, sb)
    verifica("contrario: senza passate per correggere non si rimanda (resta segnata)",
             ris.get("esito") == "fatto" and len(cli.corpi) == 2
             and lav.riproduzione.get("stato") == "nessun_test", str(lav.riproduzione))


def prova_frase(tmp: Path):
    sezione("1c. la frase a voce dopo una correzione che non riproduce")
    import prova_giro_porte as GP
    import prova_specifica_viva as S
    agente = S.AgenteVivo(requisiti=GP.REQ, stima="piccolo",
                          modifiche=[{"tipo": "difetto", "operazioni": []}] * 3)
    cfg, reg, ctx, est, svc, sv = GP.al_collaudo(tmp / "frase", agente)
    problema = "toccando una porta non si vede nessun mostro e non si prendono punti"
    S.chiama(reg, ctx, "sviluppo_correggi", {"problema": problema}, 4,
             "Toccando una porta non si vede nessun mostro e non si prendono punti.")
    lav = svc.lavori[-1]
    from calliope.tools.sviluppo import VINCOLO_RIPRODUCI
    verifica("i vincoli della correzione: prima il test che fallisce",
             lav.correzione and VINCOLO_RIPRODUCI.strip() in lav.vincoli
             and "deve FALLIRE" in lav.vincoli, lav.vincoli[-400:])
    lav.riproduzione = {"stato": "passa_prima", "test": ["gioco.test.js"], "rimandi": 1}
    item = S.consegna(svc, est, sv)
    m = item["messaggio"]
    verifica("non riprodotta: «non sono riuscita a riprodurre il problema: me lo descrivi in "
             "un altro modo?»", "non sono riuscita a riprodurre il problema: me lo descrivi in "
             "un altro modo?" in m and "pronto" not in m.lower(), m)
    verifica("…con la correzione in sospeso (la risposta è il problema detto di nuovo)",
             (item.get("in_sospeso") or {}).get("tool") == "sviluppo_correggi"
             and "problema" in str(item["in_sospeso"].get("argomenti")), str(item))
    # Il codice uguale (il caso delle 08:46) con il controllo fatto: lo dice
    S.chiama(reg, ctx, "sviluppo_correggi", {"problema": problema}, 6,
             "Non si vede ancora nessun mostro.")
    lav = svc.lavori[-1]
    lav.riproduzione = {"stato": "uguale", "rimandi": 1}
    item = S.consegna(svc, est, sv)
    verifica("codice uguale e controllo fatto: «il codice è uguale a prima, e non sono riuscita "
             "a riprodurre…»", "il codice è uguale a prima, e non sono riuscita a riprodurre"
             in item["messaggio"], item["messaggio"])
    # Contrario: riprodotta → la frase di sempre (si prova)
    S.chiama(reg, ctx, "sviluppo_correggi", {"problema": problema}, 8,
             "Non si vede ancora nessun mostro.")
    lav = svc.lavori[-1]
    lav.riproduzione = {"stato": "riprodotto", "test": ["gioco.test.js"], "rimandi": 0}
    import prova_estensioni as P
    import prova_sviluppo as SS
    import prova_sviluppo_v2 as V
    n = est.archivio.nuova_candidata(P.valida(SS.M2), {"estensione.py": (
        V.CODICE_GEO + "# corretto\n").encode()}, "Dario", {"eseguiti": 4, "falliti": 0},
        {"rischi": [], "sintassi": []}, lav.id, True)
    item = svc.finisci(lav, "fatto", estensione={"nome": "meteo_citta", "versione": n},
                       test={"eseguiti": 4, "falliti": 0}, messaggio="ho corretto il gioco.")
    verifica("contrario: riprodotta → «riprovala», niente «non sono riuscita»",
             "non sono riuscita" not in item["messaggio"]
             and (item.get("in_sospeso") or {}).get("tool") == "sviluppo_collauda",
             item["messaggio"])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    radice = Path(tempfile.mkdtemp(prefix="calliope-fasi-"))
    try:
        prova_riproduzione(radice / "riproduzione")
        prova_ciclo(radice / "ciclo")
        prova_frase(radice / "frase")
    finally:
        shutil.rmtree(radice, ignore_errors=True)
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'} "
          f"[{time.perf_counter() - T0:.1f}s]")
    sys.exit(1 if errori else 0)
