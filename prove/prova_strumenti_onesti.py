"""Gli strumenti onesti dell'agente, a secco (19/10/2026, issue #185; area agenti-estensioni;
analisi docs/ricerche/2026-10-19-solidita-harness-sviluppo.md § 3.2).

Il codice calcolava molto durante il giro (impronte dei file, firme degli errori, conti dei
test) ma quasi nulla arrivava all'agente. Qui, con l'agente finto e la sandbox col docker finto,
che ciò che il codice sa arrivi nel risultato dello strumento, come fatto:

1. lo stato già visto (agente_stato_gia_visto): la cartella che torna come N passate fa, con
   l'esito dei test di allora; il file tornato com'era; la riscrittura uguale; contrari: gli
   stati nuovi senza nota;
2. l'uscita troncata (agente_uscita_troncata): la chiamata a metà non si esegue e il risultato
   dice «troncata», non «manca percorso»; la passata fermata senza chiamate; i client (vLLM:
   finish_reason e argomenti rotti; Ollama: done_reason) e thinking_token_budget che cade nel
   log; contrari: gli argomenti mancanti veri, la chiamata intera;
3. esegui_test invariato (agente_test_invariati): senza file cambiati non si riesegue, e l'esito
   è quello; contrari: un file cambiato, un altro file di test, un'esecuzione scaduta;
4. le letture contate per file e contenuto (agente_rilettura): con riga e con da_carattere;
   contrari: i pezzi nuovi di un file lungo, il file cambiato;
5. modifica_file: le righe vere del punto più simile, le righe delle occorrenze, la modifica
   nulla (agente_modifica_nulla) e quella inversa di una precedente (agente_modifica_inversa)
   rifiutate; contrario: una modifica diversa accettata;
6. lo strumento sconosciuto con l'elenco (agente_strumento_sconosciuto) e le chiamate dopo la
   consegna con la loro risposta (agente_dopo_consegna); contrario: la consegna da sola.

    python prove\\prova_strumenti_onesti.py
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
sys.path.insert(0, str(RADICE / "prove"))

import prova_agente_guida as G  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


def sezione(t):
    print(f"\n— {t}", flush=True)


class Copione:
    """L'agente finto: ogni passata è una lista di chiamate, un testo (sola prosa) o un dizionario
    con i campi in più del client («rotti», «fine», «budget_tolto»)."""

    def __init__(self, passate):
        self.passate, self.corpi, self.url = list(passate), [], None

    def chat(self, body, su_pezzo=None, controlla=None, su_flusso=None):
        self.corpi.append(json.loads(json.dumps(body["messages"], default=str)))
        p = self.passate.pop(0) if self.passate else "Ho finito."
        out = {"content": "", "thinking": "", "tool_calls": [], "eval": 50, "prompt": 100,
               "s": 0}
        if isinstance(p, str):
            out["content"] = p
        elif isinstance(p, dict):
            out.update(json.loads(json.dumps(p)))
        else:
            out["tool_calls"] = json.loads(json.dumps(p))
        return out


def scrivi(percorso, contenuto):
    return {"name": "scrivi_file", "arguments": {"percorso": percorso, "contenuto": contenuto}}


def modifica(percorso, vecchio, nuovo):
    return {"name": "modifica_file", "arguments": {"percorso": percorso, "vecchio": vecchio,
                                                   "nuovo": nuovo}}


CONSEGNA = {"name": "consegna", "arguments": {"riassunto": "Fatto.", "esito": "fatto"}}
ESEGUI = {"name": "esegui_test", "arguments": {}}
GIUSTO = "def somma(a, b):\n    return a + b\n"
SBAGLIATO = "def somma(a, b):\n    return a - b\n"
ALTRO = "def somma(a, b):\n    return a * b\n"
TEST = ("import unittest\nfrom programma import somma\n\n\nclass P(unittest.TestCase):\n"
        "    def test_somma(self):\n        self.assertEqual(somma(2, 3), 5)\n")
NUOVE = ("agente_stato_gia_visto", "agente_uscita_troncata", "agente_test_invariati",
         "agente_rilettura", "agente_modifica_nulla", "agente_modifica_inversa",
         "agente_strumento_sconosciuto", "agente_dopo_consegna")


def gira(tmp, nome, passate, max_passi=14):
    """Agente.codice con il copione: (lavoro, risultato o {"eccezione"…}, log, copione, sandbox)."""
    from calliope.agenti.ciclo import Lavoro
    cli = Copione(passate)
    log = []
    ag = G.agente(cli, log)
    ag.max_passi = max_passi
    sb = G.sandbox(tmp, nome)
    lav = Lavoro(nome, "codice", "una funzione che somma")
    try:
        ris = ag.codice(lav, sb)
    except Exception as e:  # noqa: BLE001 — Limite
        ris = {"eccezione": type(e).__name__, "tipo": getattr(e, "tipo", ""), "motivo": str(e)}
    return lav, ris, log, cli, sb


def regole(lav) -> dict:
    return (lav.segnali or {}).get("regole") or {}


def risultati(lav, nome) -> list[dict]:
    return [json.loads(m["content"]) for m in (lav.contesto.get("messages") or [])
            if m.get("role") == "tool" and m.get("tool_name") == nome
            and m["content"].lstrip().startswith("{")]


# ═══════════════════════════ 1. lo stato già visto ═══════════════════════════

def prova_gia_visto(tmp: Path):
    sezione("1. lo stato già visto, detto nel risultato di scrivi_file e modifica_file")
    lav, ris, log, cli, sb = gira(tmp, "aba", [
        [scrivi("programma.py", SBAGLIATO), scrivi("test_programma.py", TEST)],   # passata 1
        [ESEGUI],                                                                 # 2
        [scrivi("programma.py", ALTRO)],                                          # 3
        [ESEGUI],                                                                 # 4
        [scrivi("programma.py", SBAGLIATO)],                                      # 5: torna A
        [scrivi("programma.py", SBAGLIATO)],                                      # 6: uguale
        [scrivi("programma.py", GIUSTO)], [ESEGUI], [CONSEGNA]])
    sc = risultati(lav, "scrivi_file")
    verifica("contrario: gli stati nuovi senza nota (A, il test, B)",
             len(sc) == 6 and not any("gia_visto" in r for r in sc[:3]), str(sc)[:400])
    a = sc[3].get("gia_visto", "") if len(sc) > 3 else ""
    # I test su quello stato sono della passata 2: «3 passate fa» (revisione della PR #187:
    # prima la passata in cui lo stato era apparso, la 1, con l'esito della 2)
    verifica("A, B, A: la cartella identica a quella su cui esegui_test, 3 passate fa, dava…",
             "identica a quella su cui esegui_test, 3 passate fa, dava: 1 test su 1 non "
             "passavano" in a and "AssertionError" in a, a)
    u = sc[4].get("gia_visto", "") if len(sc) > 4 else ""
    verifica("la riscrittura uguale: non è cambiato niente", "non è cambiato niente" in u, u)
    verifica("contrario: il file giusto, mai visto, senza nota",
             len(sc) > 5 and "gia_visto" not in sc[5], str(sc[5:]))
    verifica("…la regola nel registro e nel log, e il lavoro finisce «fatto»",
             regole(lav).get("agente_stato_gia_visto") == 2
             and any("agente_stato_gia_visto" in x for x in log)
             and ris.get("esito") == "fatto", str(regole(lav)) + str(ris)[:200])
    verifica("…la nota è nel risultato nuovo: i messaggi vecchi non cambiano (cache dei prefissi)",
             all(cli.corpi[i + 1][:len(cli.corpi[i])] == cli.corpi[i]
                 for i in range(len(cli.corpi) - 1)))

    # Il file tornato com'era mentre un altro file è cambiato: la cartella è nuova, il file no
    lav, ris, log, cli, sb = gira(tmp, "file", [
        [scrivi("programma.py", SBAGLIATO)], [modifica("programma.py", "a - b", "a * b")],
        [scrivi("note.txt", "uno\n")], [scrivi("programma.py", SBAGLIATO)],
        [scrivi("programma.py", GIUSTO), scrivi("test_programma.py", TEST)], [ESEGUI],
        [CONSEGNA]])
    sc = risultati(lav, "scrivi_file")
    f = sc[2].get("gia_visto", "") if len(sc) > 2 else ""
    verifica("il file tornato com'era 3 passate fa (la cartella no: note.txt è nuovo)",
             "«programma.py» è tornato identico a com'era 3 passate fa" == f, f)

    # Le funzioni da sole: stato iniziale ritrovato, e senza impronta solo il file
    from calliope.agenti.ciclo import nota_stato_gia_visto, segna_cartella
    seg = {}
    segna_cartella(seg, "S0", 1)
    verifica("la cartella tornata allo stato di partenza, mai testato: senza esito",
             nota_stato_gia_visto(seg, "a.py", "x", "S0", "S1", 3)
             == "questa versione della cartella è identica a quella di 2 passate fa")
    seg = {}
    verifica("contrario: senza impronta e con un file nuovo nessuna nota",
             nota_stato_gia_visto(seg, "a.py", "x", None, None, 1) == "")


# ═══════════════════════════ 2. l'uscita troncata ═══════════════════════════

class _Risposta:
    def __init__(self, righe, stato=200, testo=""):
        self.righe, self.status_code, self.text = righe, stato, testo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b""

    def iter_lines(self):
        return iter(self.righe)

    def close(self):
        pass


class _Http:
    def __init__(self, risposte):
        self.risposte, self.corpi = list(risposte), []

    def stream(self, metodo, percorso, json=None):
        self.corpi.append(dict(json or {}))
        return self.risposte.pop(0)


def _sse(*oggetti):
    return [f"data: {json.dumps(o)}" for o in oggetti] + ["data: [DONE]"]


def _pezzo(args, fine=None):
    ch = {"delta": {"tool_calls": [{"index": 0, "function": {"name": "scrivi_file",
                                                             "arguments": args}}]}}
    if fine:
        ch["finish_reason"] = fine
    return {"choices": [ch]}


def prova_troncata(tmp: Path):
    sezione("2. l'uscita troncata detta, non «manca percorso»")
    from calliope.agenti.ciclo import USCITA_TRONCATA_TESTO, SPINTA_STRUMENTI
    lav, ris, log, cli, sb = gira(tmp, "tronca", [
        {"tool_calls": [{"name": "scrivi_file", "arguments": {}}], "rotti": [0],
         "fine": "length"},
        [{"name": "scrivi_file", "arguments": {}}],
        {"content": "Scrivo il file: <tool_call>{\"name\": \"scrivi", "fine": "length"},
        "Ora lo scrivo.",
        [scrivi("programma.py", GIUSTO), scrivi("test_programma.py", TEST)], [ESEGUI],
        [CONSEGNA]])
    sc = risultati(lav, "scrivi_file")
    t = sc[0] if sc else {}
    verifica("la chiamata a metà: non eseguita, «troncata (fermata a max_tokens)»",
             t.get("ok") is False and "troncata (fermata a max_tokens)" in t.get("errore", "")
             and "modifica_file" in t.get("errore", "") and "percorso" not in t.get("errore", ""),
             str(t))
    m = sc[1] if len(sc) > 1 else {}
    verifica("contrario: gli argomenti mancanti veri dicono cosa manca",
             "percorso" in str(m) and "troncata" not in str(m), str(m)[:300])
    utenti = [x["content"] for x in lav.contesto["messages"] if x.get("role") == "user"]
    verifica("la passata fermata senza chiamate: il fatto al posto della spinta di sempre",
             USCITA_TRONCATA_TESTO in utenti and utenti.count(SPINTA_STRUMENTI) == 1, str(utenti))
    verifica("…la regola due volte, e il lavoro finisce «fatto»",
             regole(lav).get("agente_uscita_troncata") == 2 and ris.get("esito") == "fatto",
             str(regole(lav)) + str(ris)[:200])

    # Con i token veri (revisione della PR #187): una passata fermata a max_tokens ne ha 16 384,
    # sopra la guardia dei token senza strumenti (12 000). Il fatto viene prima, e non conta lì
    from calliope.config import Config
    cfg = Config()
    piena = int(cfg.agenti_token_passata)
    verifica("i valori di serie: la passata piena supera la guardia",
             piena > int(cfg.agenti_token_senza_strumenti), str(piena))
    lav, ris, log, cli, sb = gira(tmp, "tronca_vera", [
        {"content": "", "fine": "length", "eval": piena},
        {"content": "", "fine": "length", "eval": piena},
        {"content": "", "fine": "length", "eval": piena},
        [scrivi("programma.py", GIUSTO), scrivi("test_programma.py", TEST)], [ESEGUI],
        [CONSEGNA]])
    utenti = [x["content"] for x in lav.contesto.get("messages", []) if x.get("role") == "user"]
    verifica("tre passate piene troncate di fila: il fatto tre volte, niente «ha ragionato»",
             ris.get("esito") == "fatto" and utenti.count(USCITA_TRONCATA_TESTO) == 3
             and regole(lav).get("agente_uscita_troncata") == 3
             and not any("token senza strumenti" in x for x in log), str(ris)[:200] + str(log))
    verifica("…e nemmeno la prosa: nessuna spinta «usa gli strumenti»",
             SPINTA_STRUMENTI not in utenti and "agente_prosa_non_consegna" not in regole(lav),
             str(regole(lav)))

    # Il client di vLLM: finish_reason, argomenti rotti, budget che cade
    from calliope.agenti.remoto_openai import ClienteOpenAI
    cl = ClienteOpenAI("http://127.0.0.1:9")
    cl.http.close()
    corpo = {"model": "m", "messages": [{"role": "user", "content": "x"}],
             "options": {"num_predict": 100}, "thinking_budget": 50, "think": True}
    cl.http = _Http([_Risposta(_sse(_pezzo('{"percorso": "a.py", "contenuto": "def'),
                                    {"choices": [{"delta": {}, "finish_reason": "length"}]}))])
    out = cl.chat(dict(corpo))
    verifica("vLLM: JSON a metà e finish_reason «length» → la chiamata è tra le rotte",
             out.get("fine") == "length" and out.get("rotti") == [0]
             and out["tool_calls"][0]["arguments"] == {}, str(out))
    cl.http = _Http([_Risposta(_sse(_pezzo('{"percorso": "a.py", "contenuto": "x"}'),
                                    {"choices": [{"delta": {}, "finish_reason": "length"}]}))])
    out = cl.chat(dict(corpo))
    # Revisione della PR #187: prima l'ultima chiamata a max_tokens era sempre rotta
    verifica("contrario: a max_tokens l'ultima chiamata col JSON intero si esegue",
             not out.get("rotti") and out.get("fine") == "length", str(out))
    cl.http = _Http([_Risposta(_sse(_pezzo('{"percorso": "a.py", "contenuto": "x"}',
                                           "tool_calls")))])
    out = cl.chat(dict(corpo))
    verifica("contrario: la chiamata intera non è rotta",
             not out.get("rotti") and out.get("fine") == "tool_calls"
             and out["tool_calls"][0]["arguments"] == {"percorso": "a.py", "contenuto": "x"},
             str(out))
    cl.http = _Http([_Risposta([], 400, "unknown field thinking_token_budget"),
                     _Risposta(_sse({"choices": [{"delta": {"content": "ciao"},
                                                  "finish_reason": "stop"}]}))])
    out = cl.chat(dict(corpo))
    verifica("vLLM: thinking_token_budget rifiutato → tolto e detto (budget_tolto)",
             out.get("budget_tolto") is True and "thinking_token_budget" in cl.http.corpi[0]
             and "thinking_token_budget" not in cl.http.corpi[1], str(out))
    cl.http = _Http([_Risposta(_sse({"choices": [{"delta": {"content": "ciao"},
                                                  "finish_reason": "stop"}]}))])
    out = cl.chat(dict(corpo))
    verifica("contrario: la volta dopo il budget non si manda e non c'è niente da dire",
             not out.get("budget_tolto") and "thinking_token_budget" not in cl.http.corpi[0],
             str(out))
    log = []
    ag = G.agente(Copione([{"content": "ok", "budget_tolto": True}]), log)
    from calliope.agenti.ciclo import Lavoro
    ag.passata(Lavoro("B", "codice", "x"), [{"role": "user", "content": "x"}])
    verifica("…e il ciclo lo scrive nel log",
             any("non accetta thinking_token_budget" in x for x in log), str(log))

    # Il client di Ollama: done_reason e argomenti in stringa rotti
    from calliope.agenti.remoto import ClienteOllama
    co = ClienteOllama("http://127.0.0.1:9")
    co.http.close()
    righe = [json.dumps({"message": {"tool_calls": [{"function": {
        "name": "scrivi_file", "arguments": '{"percorso": "a.py", "cont'}}]}}),
        json.dumps({"done": True, "done_reason": "length", "eval_count": 9})]
    co.http = _Http([_Risposta(righe)])
    out = co.chat({"model": "m", "messages": []})
    verifica("Ollama: argomenti rotti e done_reason «length»",
             out.get("rotti") == [0] and out.get("fine") == "length", str(out))
    righe = [json.dumps({"message": {"tool_calls": [{"function": {
        "name": "scrivi_file", "arguments": {"percorso": "a.py", "contenuto": "x"}}}]}}),
        json.dumps({"done": True, "done_reason": "length", "eval_count": 9})]
    co.http = _Http([_Risposta(righe)])
    out = co.chat({"model": "m", "messages": []})
    verifica("contrario: con Ollama la chiamata arriva intera, anche a max_tokens",
             not out.get("rotti"), str(out))


# ═══════════════════════════ 3. esegui_test invariato ═══════════════════════════

def prova_invariati(tmp: Path):
    sezione("3. esegui_test senza file cambiati non si riesegue")
    lav, ris, log, cli, sb = gira(tmp, "invariati", [
        [scrivi("programma.py", SBAGLIATO), scrivi("test_programma.py", TEST)],
        [ESEGUI], [ESEGUI],
        [modifica("programma.py", "a - b", "a + b")], [ESEGUI],
        [{"name": "esegui_test", "arguments": {"percorso": "test_programma.py"}}],
        [CONSEGNA]])
    et = risultati(lav, "esegui_test")
    verifica("quattro esecuzioni chieste", len(et) == 4, str(et)[:300])
    if len(et) < 4:
        return
    verifica("la seconda, senza file cambiati: l'esito di prima, detto «invariato»",
             "nessun file è cambiato dall'esecuzione di una passata fa" in et[1].get("invariato",
                                                                                  "")
             and et[1].get("passano") is False and et[1].get("esito") == et[0].get("esito")
             and "AssertionError" in str(et[1].get("fallimenti")), str(et[1])[:300])
    verifica("contrario: dopo la modifica si riesegue, ed è verde",
             "invariato" not in et[2] and et[2].get("passano") is True, str(et[2])[:200])
    verifica("contrario: un solo file di test è un'altra esecuzione",
             "invariato" not in et[3], str(et[3])[:200])
    verifica("…la regola una volta, e la consegna rifà i test lo stesso («fatto», verdi)",
             regole(lav).get("agente_test_invariati") == 1 and ris.get("esito") == "fatto"
             and ris.get("test_passano") is True, str(regole(lav)) + str(ris)[:200])

    # L'esito ricordato non passa a un altro giro o a una ripresa (revisione della PR #187): il
    # motore, i controlli di Calliope e il controllo della consegna non sono nella cartella
    from calliope.agenti.ciclo import Lavoro, impronta_cartella
    sb = G.sandbox(tmp, "ripresa")
    sb.scrivi("programma.py", GIUSTO)
    sb.scrivi("test_programma.py", TEST)
    lav = Lavoro("R", "codice", "x")
    lav.segnali = {"ultimo_test": {"chiave": [impronta_cartella(sb), "", False], "passo": 0,
                                   "risultato": {"esito": {"eseguiti": 9}, "passano": False,
                                                 "uscita": "vecchio"}}}
    ag = G.agente(Copione([[ESEGUI], [CONSEGNA]]), [])
    ris = ag.codice(lav, sb)
    et = risultati(lav, "esegui_test")
    verifica("contrario: all'inizio del ciclo l'esito ricordato si butta, e i test si rifanno",
             et and "invariato" not in et[0] and et[0].get("passano") is True
             and ris.get("esito") == "fatto", str(et)[:200])

    # L'impronta che non si legge: detto nel log, una volta
    log = []
    ag = G.agente(Copione([]), log)
    lav = Lavoro("I", "codice", "x")

    def rotta():
        raise PermissionError("file del container")
    sb.impronta = rotta
    ag._strumento(lav, sb, "esegui_test", {})
    ag._strumento(lav, sb, "esegui_test", {})
    righe = [x for x in log if "impronta della cartella non letta" in x]
    verifica("l'impronta che non si legge: una riga nel log, una volta per lavoro",
             len(righe) == 1 and "PermissionError" in righe[0], str(log))

    # Un'esecuzione scaduta non si ricorda: si rifà
    from calliope.agenti.ciclo import Lavoro
    ag = G.agente(Copione([]), [])
    sb = G.sandbox(tmp, "scaduto")
    sb.scrivi("programma.py", GIUSTO)
    sb.scrivi("test_programma.py", TEST)
    lav = Lavoro("S", "codice", "x")
    vero = sb.test
    sb.test = lambda rel=None, fumo=True: {**vero(rel), "scaduto": True, "errore": "tempo scaduto"}
    ag._strumento(lav, sb, "esegui_test", {})
    sb.test = vero
    r = ag._strumento(lav, sb, "esegui_test", {})
    verifica("contrario: dopo un'esecuzione scaduta i test si rifanno",
             "invariato" not in r and r.get("passano") is True, str(r)[:200])


# ═══════════════════════════ 4. le letture ═══════════════════════════

def prova_letture(tmp: Path):
    sezione("4. le letture contate per file e contenuto")
    from calliope.agenti.ciclo import Lavoro
    ag = G.agente(Copione([]), [])
    sb = G.sandbox(tmp, "letture")
    sb.scrivi("programma.py", "".join(f"riga {i}\n" for i in range(1, 80)))
    lav = Lavoro("L", "codice", "x")
    r = [ag._leggi(lav, sb, a) for a in ({"percorso": "programma.py"},
                                         {"percorso": "programma.py", "riga": 10},
                                         {"percorso": "programma.py", "riga": 40})]
    verifica("con riga: le letture contano, la terza ha la nota",
             "nota" not in r[0] and "nota" not in r[1]
             and "letto questo file 3 volte" in r[2].get("nota", "")
             and r[2]["contenuto"].startswith("15: riga 15"), str(r[2])[:200])
    sb.scrivi("programma.py", "x = 1\n")
    r = ag._leggi(lav, sb, {"percorso": "programma.py", "riga": 1})
    verifica("contrario: il file cambiato riparte da capo", "nota" not in r, str(r))

    lungo = "".join(f"# commento lungo numero {i:05d}\n" for i in range(1500))   # ~45 000
    sb.scrivi("lungo.py", lungo)
    lav = Lavoro("L2", "codice", "x")
    pezzi = [ag._leggi(lav, sb, {"percorso": "lungo.py", "da_carattere": d})
             for d in (0, 12000, 24000, 36000)]
    verifica("contrario: i pezzi nuovi di un file lungo non sono riletture",
             not any("nota" in p for p in pezzi), str([p.get("nota") for p in pezzi]))
    di_nuovo = [ag._leggi(lav, sb, {"percorso": "lungo.py", "da_carattere": d})
                for d in (0, 12000)]
    verifica("da_carattere alternato non azzera più il conto: la terza lettura già fatta ha "
             "la nota", "nota" not in di_nuovo[0] and "letto questo file 3 volte"
             in di_nuovo[1].get("nota", ""), str([p.get("nota") for p in di_nuovo]))
    verifica("…la regola nel registro", regole(lav).get("agente_rilettura") == 1,
             str(regole(lav)))


# ═══════════════════════════ 5. modifica_file ═══════════════════════════

def prova_modifica(tmp: Path):
    sezione("5. modifica_file: errori utili, la modifica nulla e quella inversa")
    from calliope.agenti.ciclo import Lavoro
    log = []
    ag = G.agente(Copione([]), log)
    sb = G.sandbox(tmp, "modifica")
    sb.scrivi("programma.py", "import math\n\n\ndef area(r):\n    return math.pi * r ** 2\n\n\n"
                              "def doppio(x):\n    return x * 2\n")
    lav = Lavoro("M", "codice", "x")
    r = ag._modifica(lav, sb, {"percorso": "programma.py",
                               "vecchio": "def area(raggio):\n    return math.pi * r * r",
                               "nuovo": "def area(r):\n    return 3"})
    verifica("il testo che non c'è: il punto più simile con le righe vere, numerate",
             r.get("ok") is False and "alla riga 4" in r.get("errore", "")
             and "4: def area(r):" in r.get("righe_vere", "")
             and "5:     return math.pi * r ** 2" in r.get("righe_vere", ""), str(r))
    r = ag._modifica(lav, sb, {"percorso": "programma.py", "vecchio": "class Niente:",
                               "nuovo": "x"})
    verifica("contrario: niente di simile, nessuna riga inventata",
             r.get("ok") is False and "nessuna riga gli somiglia" in r.get("errore", "")
             and "righe_vere" not in r, str(r))
    r = ag._modifica(lav, sb, {"percorso": "programma.py", "vecchio": "    return",
                               "nuovo": "    return 0 +"})
    verifica("ambiguo: le righe delle occorrenze",
             r.get("ok") is False and "compare 2 volte, alle righe 5, 9" in r.get("errore", ""),
             str(r))
    r = ag._modifica(lav, sb, {"percorso": "programma.py", "vecchio": "x * 2",
                               "nuovo": "x * 2"})
    verifica("vecchio = nuovo: rifiutata (prima riusciva)",
             r.get("ok") is False and "uguali" in r.get("errore", ""), str(r))
    lav.passi = 3
    r = ag._modifica(lav, sb, {"percorso": "programma.py", "vecchio": "x * 2", "nuovo": "x + x"})
    verifica("una modifica vera riesce", r.get("ok") is True, str(r))
    lav.passi = 5
    r = ag._modifica(lav, sb, {"percorso": "programma.py", "vecchio": "x + x", "nuovo": "x * 2"})
    verifica("l'inversa di quella di 2 passate fa: rifiutata, col passo",
             r.get("ok") is False and "modifica_file di 2 passate fa aveva tolto" in
             r.get("errore", "") and "x + x" in sb.leggi("programma.py"), str(r))
    r = ag._modifica(lav, sb, {"percorso": "programma.py", "vecchio": "x + x", "nuovo": "2 * x"})
    verifica("contrario: una modifica diversa è accettata",
             r.get("ok") is True and "2 * x" in sb.leggi("programma.py"), str(r))
    verifica("…le regole nel registro",
             regole(lav).get("agente_modifica_nulla") == 1
             and regole(lav).get("agente_modifica_inversa") == 1, str(regole(lav)))

    # Revisione della PR #187: si rifiuta solo l'oscillazione pura. Dopo un altro cambiamento
    # nella cartella tornare indietro è una correzione; dopo scrivi_file lo storico riparte
    sb.scrivi("somma.py", "def somma(a, b):\n    return a + b\n\n\ndef doppio(x):\n"
                          "    return x * 2\n")
    lav.passi = 6
    r1 = ag._modifica(lav, sb, {"percorso": "somma.py", "vecchio": "a + b", "nuovo": "a - b"})
    lav.passi = 7
    r2 = ag._modifica(lav, sb, {"percorso": "somma.py", "vecchio": "x * 2", "nuovo": "x + x"})
    lav.passi = 8
    r3 = ag._modifica(lav, sb, {"percorso": "somma.py", "vecchio": "a - b", "nuovo": "a + b"})
    verifica("contrario: a+b → a-b, poi doppio cambiato, poi di nuovo a+b: accettata",
             r1.get("ok") and r2.get("ok") and r3.get("ok") is True
             and "a + b" in sb.leggi("somma.py"), str(r3))
    verifica("…_modifica dà al ciclo le due impronte della cartella (una lettura in meno)",
             "_impronte" in r3 and len(r3["_impronte"]) == 2, str(r3))

    # L'inversa con i test di allora, nel ciclo
    lav, ris, log, cli, sb = gira(tmp, "inversa", [
        [scrivi("programma.py", SBAGLIATO), scrivi("test_programma.py", TEST)], [ESEGUI],
        [modifica("programma.py", "a - b", "a * b")],
        [modifica("programma.py", "a * b", "a - b")],
        [modifica("programma.py", "a * b", "a + b")], [ESEGUI], [CONSEGNA]])
    mf = risultati(lav, "modifica_file")
    inv = mf[1].get("errore", "") if len(mf) > 1 else ""
    verifica("nel ciclo: l'inversa rifiutata con l'esito dei test prima di quella modifica",
             "una passata fa aveva tolto" in inv and "esegui_test dava: 1 test su 1 non "
             "passavano" in inv, inv)
    verifica("…e il lavoro finisce «fatto»", ris.get("esito") == "fatto", str(ris)[:200])

    # Nel ciclo, i contrari della revisione: la correzione dopo un altro cambiamento, e
    # l'inversa dopo uno scrivi_file dello stesso file
    due = "def somma(a, b):\n    return a + b\n\n\ndef doppio(x):\n    return x * 2\n"
    test2 = TEST + "\n    def test_doppio(self):\n        from programma import doppio\n" \
                   "        self.assertEqual(doppio(3), 6)\n"
    lav, ris, log, cli, sb = gira(tmp, "correzione", [
        [scrivi("programma.py", due), scrivi("test_programma.py", test2)], [ESEGUI],
        [modifica("programma.py", "a + b", "a - b")],
        [modifica("programma.py", "x * 2", "x + x")], [ESEGUI],
        [modifica("programma.py", "a - b", "a + b")],
        [modifica("programma.py", "x + x", "x + x + 0")],
        [scrivi("programma.py", due.replace("x * 2", "x + x + 0"))],
        [modifica("programma.py", "x + x + 0", "x + x")], [ESEGUI], [CONSEGNA]])
    mf = risultati(lav, "modifica_file")
    verifica("nel ciclo: tornare ad a+b dopo aver cambiato doppio è accettato",
             len(mf) == 5 and mf[2].get("ok") is True
             and not any("_impronte" in m for m in mf), str(mf)[:400])
    verifica("nel ciclo: l'inversa dopo scrivi_file dello stesso file è accettata",
             len(mf) == 5 and mf[4].get("ok") is True and ris.get("esito") == "fatto"
             and "agente_modifica_inversa" not in regole(lav), str(mf[-1:]) + str(regole(lav)))


# ═══════════════════════ 6. strumento sconosciuto, dopo la consegna ═══════════════════════

def prova_sconosciuto(tmp: Path):
    sezione("6. lo strumento sconosciuto e le chiamate dopo la consegna")
    lav, ris, log, cli, sb = gira(tmp, "sconosciuto", [
        [{"name": "cancella_file", "arguments": {"percorso": "x.py"}}],
        [scrivi("programma.py", GIUSTO), scrivi("test_programma.py", TEST)], [ESEGUI],
        [CONSEGNA, scrivi("dopo.py", "x = 1\n"), ESEGUI]])
    msgs = [m for m in lav.contesto["messages"] if m.get("role") == "tool"]
    sc = json.loads(msgs[0]["content"]) if msgs else {}
    verifica("lo strumento che non c'è: ok False con l'elenco dei veri",
             sc.get("ok") is False and "«cancella_file» non c'è" in sc.get("errore", "")
             and "scrivi_file" in sc.get("errore", "") and "consegna" in sc.get("errore", ""),
             str(sc))
    dopo = [json.loads(m["content"]) for m in msgs[-2:]]
    verifica("le due chiamate dopo la consegna: ognuna con «già consegnato», non eseguite",
             ris.get("esito") == "fatto" and len(msgs) == 7
             and all(d.get("nota") == "non eseguita: il lavoro era già consegnato" for d in dopo)
             and not (sb.root / "dopo.py").exists(), str(dopo) + str(ris)[:200])
    ultimo = [m for m in lav.contesto["messages"] if m.get("role") == "assistant"][-1]
    verifica("…la storia è ben formata: tante risposte quante chiamate",
             len(ultimo.get("tool_calls") or []) == 3
             and [m["tool_name"] for m in msgs[-3:]] == ["consegna", "scrivi_file",
                                                         "esegui_test"],
             str([m["tool_name"] for m in msgs]))
    verifica("…le regole nel registro",
             regole(lav).get("agente_strumento_sconosciuto") == 1
             and regole(lav).get("agente_dopo_consegna") == 2, str(regole(lav)))
    lav, ris, log, cli, sb = gira(tmp, "sola", [
        [scrivi("programma.py", GIUSTO), scrivi("test_programma.py", TEST)], [ESEGUI],
        [CONSEGNA]])
    verifica("contrario: la consegna da sola, niente risposte in più",
             ris.get("esito") == "fatto" and "agente_dopo_consegna" not in regole(lav)
             and [m["tool_name"] for m in lav.contesto["messages"]
                  if m.get("role") == "tool"][-1] == "consegna", str(regole(lav)))
    verifica("nessuna regola nuova scattata dove non doveva",
             not any(r in regole(lav) for r in NUOVE), str(regole(lav)))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="calliope-onesti-"))
    os.environ.setdefault("CALLIOPE_CONFIG_LOCALE", str(tmp / "nessuno.yaml"))
    try:
        prova_gia_visto(tmp / "gia")
        prova_troncata(tmp / "tronca")
        prova_invariati(tmp / "invariati")
        prova_letture(tmp / "letture")
        prova_modifica(tmp / "modifica")
        prova_sconosciuto(tmp / "sconosciuto")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
