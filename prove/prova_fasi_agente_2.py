"""Prova a secco del flusso dell'agente a fasi, parte 2 (13/10/2026; ricerca
docs/ricerche/2026-10-12-flusso-agente-fasi.md § 5.1, area agenti-estensioni; misure del banco
della temperatura sulla DGX del 12–13/10, caso del convertitore di distanze).

1. **Consegna quando i suoi test passano** (calliope/agenti/ciclo.py):
   - a. dopo il primo esegui_test tutto verde, con i file che il lavoro chiede, una volta per
     lavoro la spinta «i tuoi test passano: se il lavoro è finito chiama consegna ora…»
     (regola agente_spinta_consegna); contrari: test rossi, un solo file di test eseguito,
     un'estensione senza manifesto, un'estensione prima del piano, la spinta che non si ripete;
   - b. l'avviso di chiusura con l'ultimo esegui_test verde dice di consegnare; contrari: un
     file cambiato dopo il test verde (l'avviso di sempre), una tappa di uno sviluppo (la sua
     variante);
   - c. la consegna resta dell'agente: senza consegna il lavoro finisce al tetto («limite»), mai
     «fatto» d'ufficio.

    python prove/prova_fasi_agente_2.py
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


# ═══════════════════════════ 1. consegna quando i test passano ═══════════════════════════

PROGRAMMA = "def somma(a, b):\n    return a + b\n"
SBAGLIATO = "def somma(a, b):\n    return a - b\n"
TEST = ("import unittest\nfrom programma import somma\n\n\nclass P(unittest.TestCase):\n"
        "    def test_somma(self):\n        self.assertEqual(somma(2, 3), 5)\n")


def scrivi(percorso, contenuto):
    return {"name": "scrivi_file", "arguments": {"percorso": percorso, "contenuto": contenuto}}


ESEGUI_TEST = {"name": "esegui_test", "arguments": {}}
CONSEGNA = {"name": "consegna", "arguments": {"riassunto": "Fatto.", "esito": "fatto"}}
LEGGI = {"name": "leggi_file", "arguments": {"percorso": "programma.py"}}


def _utenti(lav) -> list[str]:
    return [m["content"] for m in (lav.contesto.get("messages") or [])
            if m.get("role") == "user"]


def _gira(tmp, nome, passate, tipo="codice", file=None, max_passi=None, piano=False,
          tappe=False):
    from calliope.agenti.ciclo import Lavoro
    cli = G._Copione(passate)
    log = []
    ag = G.agente(cli, log)
    if max_passi:
        ag.max_passi = max_passi
    sb = G.sandbox(tmp, nome)
    for k, v in (file or {}).items():
        sb.scrivi(k, v)
    lav = Lavoro(nome, tipo, "una funzione che somma")
    lav.tappe = tappe
    try:
        ris = ag.codice(lav, sb, piano=piano)
    except Exception as e:  # noqa: BLE001 — Limite: il tetto delle passate
        ris = {"eccezione": type(e).__name__, "motivo": str(e)}
    return lav, ris, log, cli


def prova_spinta_consegna(tmp: Path):
    sezione("1a. la spinta a consegnare dopo il primo esegui_test verde")
    from calliope.agenti.ciclo import SPINTA_CONSEGNA
    lav, ris, log, cli = _gira(tmp, "verde", [
        [scrivi("programma.py", PROGRAMMA), scrivi("test_programma.py", TEST)],
        [ESEGUI_TEST], [LEGGI], [ESEGUI_TEST], [CONSEGNA]])
    u = _utenti(lav)
    n = sum(SPINTA_CONSEGNA in x for x in u)
    verifica("dopo i test verdi la spinta, una volta sola anche con un secondo test verde",
             n == 1 and ris.get("esito") == "fatto", f"{n} {ris}")
    verifica("…nella passata subito dopo il test verde",
             SPINTA_CONSEGNA in json.dumps(cli.corpi[2], ensure_ascii=False)
             and SPINTA_CONSEGNA not in json.dumps(cli.corpi[1], ensure_ascii=False))
    verifica("…la regola nel log e nei segnali",
             any("agente_spinta_consegna" in x for x in log)
             and (lav.segnali.get("regole") or {}).get("agente_spinta_consegna") == 1,
             str(lav.segnali.get("regole")))
    lav, ris, log, cli = _gira(tmp, "rosso", [
        [scrivi("programma.py", SBAGLIATO), scrivi("test_programma.py", TEST)],
        [ESEGUI_TEST], [LEGGI], [CONSEGNA], [CONSEGNA], [CONSEGNA]])
    verifica("contrario: test rossi, nessuna spinta",
             not any(SPINTA_CONSEGNA in x for x in _utenti(lav)))
    lav, ris, log, cli = _gira(tmp, "unfile", [
        [scrivi("programma.py", PROGRAMMA), scrivi("test_programma.py", TEST)],
        [{"name": "esegui_test", "arguments": {"percorso": "test_programma.py"}}], [CONSEGNA]])
    verifica("contrario: un solo file di test eseguito non basta",
             not any(SPINTA_CONSEGNA in x for x in _utenti(lav)))
    est_test = ("import unittest\n\n\nclass P(unittest.TestCase):\n"
                "    def test_x(self):\n        self.assertTrue(True)\n")
    lav, ris, log, cli = _gira(tmp, "senza-manifesto", [
        [scrivi("estensione.py", "def esegui(dati, calliope):\n    return {}\n"),
         scrivi("test_estensione.py", est_test)],
        [ESEGUI_TEST], [{"name": "consegna", "arguments": {"riassunto": "x",
                                                           "esito": "impossibile"}}]],
        tipo="estensione")
    verifica("contrario: un'estensione senza manifesto non riceve la spinta",
             not any(SPINTA_CONSEGNA in x for x in _utenti(lav)))
    from calliope.agenti.ciclo import Agente
    from types import SimpleNamespace
    sb = G.sandbox(tmp, "pronto")
    sb.scrivi("estensione.py", "def esegui(dati, calliope):\n    return {}\n")
    sb.scrivi("test_estensione.py", est_test)
    sb.scrivi("manifesto.json", json.dumps(MANIFESTO))
    lav_e = SimpleNamespace(tipo="estensione")
    verifica("il controllo dei file: un'estensione con manifesto, codice e test è pronta, "
             "prima del piano no", Agente._pronto_da_consegnare(lav_e, sb, True, {"x": 1})
             and not Agente._pronto_da_consegnare(lav_e, sb, True, None))


MANIFESTO = {"nome": "somma_prova", "titolo": "Somma prova",
             "cosa_fa": {"verbo": "calcola", "oggetto": "la somma di due numeri"},
             "input": {"type": "object", "properties": {"a": {"type": "number",
                                                              "description": "primo numero"}},
                       "required": ["a"]},
             "permessi": {}, "livello": "familiare",
             "limiti": {"tempo_s": 10, "memoria_mb": 256}}


def prova_avviso_verde(tmp: Path):
    sezione("1b. l'avviso di chiusura con i test verdi")
    from calliope.agenti.ciclo import AVVISO_FINE
    # max_passi 4: l'avviso arriva prima della passata 3 (passi + 2 >= 4)
    lav, ris, log, cli = _gira(tmp, "avviso-verde", [
        [scrivi("programma.py", PROGRAMMA), scrivi("test_programma.py", TEST)],
        [ESEGUI_TEST], [LEGGI], [CONSEGNA]], max_passi=4)
    u = _utenti(lav)
    verifica("l'ultimo esegui_test verde, niente cambiato: «I tuoi test passano: chiama "
             "consegna adesso»", any(AVVISO_FINE["verde"] in x for x in u)
             and not any(AVVISO_FINE["codice"] in x for x in u)
             and any("con i test verdi" in x for x in log), str(log[-4:]))
    lav, ris, log, cli = _gira(tmp, "avviso-cambiato", [
        [scrivi("programma.py", PROGRAMMA), scrivi("test_programma.py", TEST), ESEGUI_TEST],
        [scrivi("programma.py", PROGRAMMA + "# altro\n")], [LEGGI], [CONSEGNA]], max_passi=4)
    u = _utenti(lav)
    verifica("contrario: un file cambiato dopo il test verde, l'avviso di sempre",
             any(AVVISO_FINE["codice"] in x for x in u)
             and not any(AVVISO_FINE["verde"] in x for x in u))
    lav, ris, log, cli = _gira(tmp, "avviso-tappa", [
        [scrivi("programma.py", PROGRAMMA), scrivi("test_programma.py", TEST)],
        [ESEGUI_TEST], [LEGGI], [CONSEGNA]], max_passi=4, tappe=True)
    u = _utenti(lav)
    verifica("in uno sviluppo (tappa): la variante con «se il lavoro è finito»",
             any(AVVISO_FINE["verde_tappa"] in x for x in u)
             and not any(AVVISO_FINE["tappa"] in x for x in u))


def prova_niente_ufficio(tmp: Path):
    sezione("1c. la consegna resta dell'agente")
    lav, ris, log, cli = _gira(tmp, "ufficio", [
        [scrivi("programma.py", PROGRAMMA), scrivi("test_programma.py", TEST)],
        [ESEGUI_TEST]] + [[LEGGI]] * 6, max_passi=5)
    verifica("test verdi ma nessuna consegna: il lavoro si ferma al tetto, non «fatto»",
             ris.get("eccezione") == "Limite" and "passate" in ris.get("motivo", ""), str(ris))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    radice = Path(tempfile.mkdtemp(prefix="calliope-fasi2-"))
    try:
        prova_spinta_consegna(radice / "spinta")
        prova_avviso_verde(radice / "avviso")
        prova_niente_ufficio(radice / "ufficio")
    finally:
        shutil.rmtree(radice, ignore_errors=True)
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'} "
          f"[{time.perf_counter() - T0:.1f}s]")
    sys.exit(1 if errori else 0)
