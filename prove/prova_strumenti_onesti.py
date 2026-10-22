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
   consegna con la loro risposta (agente_dopo_consegna); contrario: la consegna da sola;
7. i casi delle tre revisioni della PR #187;
8. le stesse regole nel ciclo della ricerca (21/10, #189): lo strumento sconosciuto, la consegna
   seguita da una web_leggi (la consegna vale, la lettura no, detta), la chiamata e la consegna a
   metà contro l'argomento davvero mancante, la relazione fermata a max_tokens contro quella
   intera, il tetto delle troncate di fila.

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
        self.revisioni = []

    def chat(self, body, su_pezzo=None, controlla=None, su_flusso=None):
        if G.e_revisore(body):
            # Il revisore a contesto pulito (#190) non si prende le passate del copione
            self.revisioni.append(body)
            return {"content": "", "eval": 0, "prompt": 0}
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


def gira(tmp, nome, passate, max_passi=14, tappe=False, lav=None, sb=None, controlla=None,
         piano=False):
    """Agente.codice con il copione: (lavoro, risultato o {"eccezione"…}, log, copione, sandbox)."""
    from calliope.agenti.ciclo import Lavoro
    cli = Copione(passate)
    log = []
    ag = G.agente(cli, log)
    ag.max_passi = max_passi
    sb = sb or G.sandbox(tmp, nome)
    if lav is None:
        lav = Lavoro(nome, "codice", "una funzione che somma")
        lav.tappe = tappe
    try:
        ris = ag.codice(lav, sb, controlla=controlla, piano=piano)
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
    a_meta = {"content": "Scrivo il programma:\ndef somma(a, b):\n    return", "fine": "length",
              "eval": piena, "ragionamento": piena // 2}
    lav, ris, log, cli, sb = gira(tmp, "tronca_vera", [
        a_meta, a_meta, a_meta,
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

    # Seconda revisione della PR #187. Il solo ragionamento troncato (il contenuto vuoto) non è
    # un'uscita troncata: la guardia dei token senza strumenti chiude alla seconda soglia, come
    # prima, e non il tetto dei token del lavoro dopo 30 passate
    # Un ragionamento vero di 16 384 token sono ~50 000 caratteri (terza revisione: la
    # discriminante è sui token, non sul contenuto)
    pensa = {"content": "", "thinking": "penso " * 11000, "fine": "length", "eval": piena}
    lav, ris, log, cli, sb = gira(tmp, "tronca_pensiero", [dict(pensa) for _ in range(30)],
                                  max_passi=24)
    verifica("contrario: 30 passate di solo ragionamento troncato chiudono alla seconda soglia",
             ris.get("eccezione") == "Limite" and "ha ragionato per" in ris.get("motivo", "")
             and len(cli.corpi) == 2 and "agente_uscita_troncata" not in regole(lav),
             str(ris)[:200] + f" passate {len(cli.corpi)}")
    # Il tetto delle troncate di fila, con il motivo suo
    lav, ris, log, cli, sb = gira(tmp, "tronca_tetto", [dict(a_meta) for _ in range(8)])
    verifica("oltre TRONCATE_MAX troncate di fila: «limite» col motivo suo, non il tetto dei token",
             ris.get("eccezione") == "Limite" and ris.get("tipo") == "troncata"
             and "fermata 4 volte al tetto dei token" in ris.get("motivo", "")
             and "senza una chiamata eseguita" in ris.get("motivo", "")
             and len(cli.corpi) == 4, str(ris)[:200])
    # La troncata azzera la prosa di fila (N3): quattro prose alternate a tre troncate, nessun
    # «4 volte di fila senza usare gli strumenti». Dal 21/10 (#191) la prosa non azzera le
    # troncate: le quattro troncate alternate sono nella sezione 7, caso F
    lav, ris, log, cli, sb = gira(tmp, "tronca_prosa", [
        "Ci penso.", a_meta, "Ci penso.", a_meta, "Ci penso.", a_meta, "Ci penso.",
        [scrivi("programma.py", GIUSTO), scrivi("test_programma.py", TEST)], [ESEGUI],
        [CONSEGNA]], max_passi=14)
    verifica("troncate e prosa alternate: nessuna delle due oltre il tetto, il lavoro finisce",
             ris.get("esito") == "fatto" and regole(lav).get("agente_uscita_troncata") == 3,
             str(ris)[:200] + str(regole(lav)))

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
    verifica("vLLM: il budget mandato torna nell'uscita (#191)", out.get("budget") == 50, str(out))
    cl.http = _Http([_Risposta(_sse(_pezzo('{"percorso": "a.py", "contenuto": "x"}'),
                                    {"choices": [{"delta": {}, "finish_reason": "length"}]}))])
    out = cl.chat(dict(corpo))
    # Seconda revisione della PR #187: a fine stream vLLM chiude il JSON con la stringa a metà
    verifica("vLLM: a max_tokens l'ultima chiamata è rotta anche col JSON che si legge",
             out.get("rotti") == [0] and out.get("fine") == "length", str(out))
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
             and "thinking_token_budget" not in cl.http.corpi[1] and "budget" not in out,
             str(out))
    cl.http = _Http([_Risposta(_sse({"choices": [{"delta": {"content": "ciao"},
                                                  "finish_reason": "stop"}]}))])
    out = cl.chat(dict(corpo))
    verifica("contrario: la volta dopo il budget non si manda e non c'è niente da dire",
             not out.get("budget_tolto") and "thinking_token_budget" not in cl.http.corpi[0]
             and "budget" not in out, str(out))
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
    out = co.chat({"model": "m", "messages": [], "think": True, "thinking_budget": 50})
    verifica("Ollama: argomenti rotti e done_reason «length»",
             out.get("rotti") == [0] and out.get("fine") == "length", str(out))
    verifica("contrario: Ollama non applica il budget e non lo dice (#191)",
             "budget" not in out, str(out))
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


# ═══════════════ 7. i casi delle tre revisioni della PR #187, permanenti ═══════════════
# Ogni tornata di correzioni aveva rotto un caso di quella prima: qui restano tutti, con i
# contrari, con il nome che avevano nei copioni della revisione

LAVORO = [[scrivi("programma.py", GIUSTO), scrivi("test_programma.py", TEST)], [ESEGUI],
          [CONSEGNA]]
PIENA = 16384
A_META = {"content": "Scrivo il programma:\ndef somma(a, b):\n    return", "fine": "length",
          "eval": PIENA}


def _storia_ben_formata(lav) -> bool:
    """Ogni messaggio dell'agente con N chiamate ha dopo di sé N risposte."""
    msgs = (lav.contesto or {}).get("messages") or []
    for i, m in enumerate(msgs):
        n = len(m.get("tool_calls") or []) if m.get("role") == "assistant" else 0
        if n and sum(1 for x in msgs[i + 1:i + 1 + n] if x.get("role") == "tool") != n:
            return False
    return True


class _Orologio:
    """time.monotonic finto: una passata troncata del copione dura 330 s (16 384 token a ~50
    token/s, oltre i 5 minuti della guardia del tempo senza strumenti), le altre 120 s."""
    t = 1000.0

    def monotonic(self):
        return _Orologio.t

    def __getattr__(self, n):
        import time
        return getattr(time, n)


def prova_revisioni(tmp: Path):
    sezione("7. i casi delle tre revisioni della PR #187")
    from calliope.agenti import ciclo as C
    from calliope.agenti.ciclo import USCITA_TRONCATA_TESTO, TRONCATE_MAX
    # A, L0 e L1 (prima e terza revisione, R3): contenuto vuoto, poco o niente ragionamento,
    # eval al tetto. È l'uscita trattenuta dal parser dei tool (Ollama, una chiamata a metà):
    # una troncata, non «ha ragionato per 32 768 token»
    for tag, th in (("A", ""), ("L1", "Devo scrivere programma.py con somma. " * 10)):
        p = {"content": "", "thinking": th, "fine": "length", "eval": PIENA}
        lav, ris, log, cli, sb = gira(tmp, "rev" + tag, [p, p, p] + LAVORO)
        verifica(f"{tag}: contenuto vuoto e poco ragionamento a {PIENA} token → troncata, «fatto»",
                 ris.get("esito") == "fatto" and regole(lav).get("agente_uscita_troncata") == 3
                 and not any("token senza strumenti" in x for x in log), str(ris)[:200])
    # E (seconda): solo ragionamento, contato dal motore (vLLM) o stimato dai caratteri
    for tag, p in (("E-vLLM", {"content": "", "ragionamento": PIENA - 10, "fine": "length",
                               "eval": PIENA}),
                   ("E-Ollama", {"content": "", "thinking": "penso " * 11000, "fine": "length",
                                 "eval": PIENA})):
        lav, ris, log, cli, sb = gira(tmp, "rev" + tag, [dict(p) for _ in range(30)],
                                      max_passi=24)
        verifica(f"{tag}: il solo ragionamento troncato chiude alla seconda soglia, come prima",
                 ris.get("eccezione") == "Limite" and "ha ragionato per" in ris.get("motivo", "")
                 and len(cli.corpi) == 2 and "agente_uscita_troncata" not in regole(lav),
                 str(ris)[:200])
    # F (seconda; #191 dal 21/10): troncate a contenuto vuoto alternate a prosa. Prima arrivavano
    # a un tetto del lavoro (i token, sulla DGX i 30 minuti); ora la prosa non azzera le troncate
    # e alla quarta il lavoro si ferma col motivo suo, senza «di fila»
    vuota = {"content": "", "fine": "length", "eval": PIENA}
    lav, ris, log, cli, sb = gira(tmp, "revF", [vuota, "Ci penso."] * 12, max_passi=24)
    verifica("F: quattro troncate alternate a prosa → «limite» «troncata» alla settima passata",
             ris.get("eccezione") == "Limite" and ris.get("tipo") == "troncata"
             and "senza una chiamata eseguita" in ris.get("motivo", "")
             and "di fila" not in ris.get("motivo", "") and len(cli.corpi) == 7
             and regole(lav).get("agente_uscita_troncata") == TRONCATE_MAX, str(ris)[:200])
    lav, ris, log, cli, sb = gira(tmp, "revF2", [vuota, "Ci penso."] * 12, max_passi=24,
                                  tappe=True)
    verifica("…in uno sviluppo la tappa «troncata», la storia ben formata",
             ris.get("esito") == "tappa" and ris.get("tipo_limite") == "troncata"
             and _storia_ben_formata(lav), str(ris)[:200])
    # Q4 (seconda revisione della PR #219): la tappa detta a voce, senza gergo
    from types import SimpleNamespace
    from calliope.agenti.servizio import PERCHE_TAPPA, frase_tappa
    f = frase_tappa(SimpleNamespace(risultato=ris, segnali={}), "La somma")
    verifica("Q4: la tappa «troncata» a voce, breve e senza gergo",
             "risposte troppo lunghe, interrotte a metà" in f
             and not any(g in f for g in ("token", "chiamata", "max_tokens", "passata")),
             f[:300])
    # Contrario: una chiamata eseguita in mezzo azzera le troncate (tre, la chiamata, tre)
    lav, ris, log, cli, sb = gira(tmp, "revF3", [vuota, "Ci penso.", vuota, "Ci penso.", vuota,
                                                 [scrivi("note.txt", "x")], vuota, "Ci penso.",
                                                 vuota, vuota] + LAVORO, max_passi=24)
    verifica("contrario F: una chiamata eseguita in mezzo azzera le troncate, «fatto»",
             ris.get("esito") == "fatto" and regole(lav).get("agente_uscita_troncata") == 6,
             str(ris)[:200])
    # …e il ragionamento troncato in mezzo (nella guardia) non le azzera
    pensa = {"content": "", "ragionamento": PIENA - 10, "fine": "length", "eval": PIENA}
    lav, ris, log, cli, sb = gira(tmp, "revF4", [vuota, vuota, vuota, pensa, vuota] + LAVORO,
                                  max_passi=24)
    verifica("F: il ragionamento troncato in mezzo non azzera le troncate: la quarta ferma",
             ris.get("eccezione") == "Limite" and ris.get("tipo") == "troncata"
             and len(cli.corpi) == 5, str(ris)[:200])
    # V1 (quarta revisione, #191): vLLM con il budget applicato (8 192 su 16 384, quota 0,5) e il
    # resto trattenuto dal parser: oltre il budget il ragionamento non va, è una troncata
    # Senza il conto esatto del motore (vLLM che non riempie reasoning_tokens): la stima dai
    # caratteri, 27 000 / 3 = 9 000 token, sopra la quota, direbbe «ragionamento»
    v1 = {"content": "", "thinking": "penso " * 4500, "budget": 8192, "fine": "length",
          "eval": PIENA}
    lav, ris, log, cli, sb = gira(tmp, "revV1", [dict(v1) for _ in range(3)] + LAVORO)
    verifica("V1: budget applicato, eval oltre budget + 1024, contenuto vuoto → troncata, «fatto»",
             ris.get("esito") == "fatto" and regole(lav).get("agente_uscita_troncata") == 3
             and not any("token senza strumenti" in x for x in log), str(ris)[:200])
    # Contrari: E con il budget tolto dal server resta nella guardia; e i bordi della funzione
    e_tolto = dict(v1, ragionamento=PIENA - 10, budget_tolto=True)
    e_tolto.pop("budget")
    lav, ris, log, cli, sb = gira(tmp, "revV1E", [dict(e_tolto) for _ in range(30)],
                                  max_passi=24)
    verifica("contrario V1: E col budget tolto chiude alla seconda soglia, come prima",
             ris.get("eccezione") == "Limite" and "ha ragionato per" in ris.get("motivo", "")
             and len(cli.corpi) == 2 and "agente_uscita_troncata" not in regole(lav),
             str(ris)[:200])
    # P1 (revisione della PR #219): il budget non rifiutato non vuol dire applicato (llama.cpp
    # lo ignora); col conto esatto del ragionamento decide quello, come E
    e_budget = {"content": "", "ragionamento": PIENA - 10, "budget": 8192, "fine": "length",
                "eval": PIENA}
    lav, ris, log, cli, sb = gira(tmp, "revV1P1", [dict(e_budget) for _ in range(30)],
                                  max_passi=24)
    verifica("contrario V1 (P1): budget non rifiutato e 16 374 di ragionamento esatto → come E",
             ris.get("eccezione") == "Limite" and "ha ragionato per" in ris.get("motivo", "")
             and len(cli.corpi) == 2 and "agente_uscita_troncata" not in regole(lav),
             str(ris)[:200])
    # Q1 (seconda revisione della PR #219): col conto esatto decide il residuo. V1 col conto di
    # vLLM (8 192 su 16 384) è una troncata, con il budget e senza
    v1_conto = {"content": "", "ragionamento": 8192, "budget": 8192, "fine": "length",
                "eval": PIENA}
    lav, ris, log, cli, sb = gira(tmp, "revV1conto", [dict(v1_conto) for _ in range(3)] + LAVORO)
    verifica("Q1: V1 col conto esatto di vLLM → troncata, «fatto»",
             ris.get("esito") == "fatto" and regole(lav).get("agente_uscita_troncata") == 3
             and not any("token senza strumenti" in x for x in log), str(ris)[:200])
    # Q2: senza conto e col budget ignorato (llama.cpp), il solo ragionamento lungo: la stima
    # (54 000 caratteri, 18 000 token) è oltre 1,5 volte il budget, decide la quota come E
    q2 = {"content": "", "thinking": "x" * 54000, "budget": 8192, "fine": "length",
          "eval": PIENA}
    lav, ris, log, cli, sb = gira(tmp, "revQ2", [dict(q2) for _ in range(30)], max_passi=24)
    verifica("Q2: budget ignorato e solo ragionamento lungo → come E, niente «scrivi in pezzi»",
             ris.get("eccezione") == "Limite" and "ha ragionato per" in ris.get("motivo", "")
             and len(cli.corpi) == 2 and "agente_uscita_troncata" not in regole(lav),
             str(ris)[:200])
    t = C.troncata_nell_uscita
    soglia = int(C.RAGIONAMENTO_BUDGET_MAX * 8192 * C.TOKEN_CARATTERI)
    verifica("Q1 e Q2: i bordi col conto esatto, il conto 0 e la stima oltre il budget",
             t(v1_conto) and t(dict(v1_conto, budget=0)) and t(dict(v1_conto, budget_tolto=True))
             and t(dict(v1_conto, ragionamento=PIENA - C.BUDGET_MARGINE - 1))
             and not t(dict(v1_conto, ragionamento=PIENA - C.BUDGET_MARGINE))
             and not t(dict(v1_conto, ragionamento=PIENA - 10))
             # il conto 0 smentito dal ragionamento scritto: vale la stima (E con Ollama)
             and not t(dict(q2, ragionamento=0, budget=0))
             and t(dict(v1_conto, ragionamento=0))
             # la stima fino a 1,5 volte il budget sì, oltre no
             and t(dict(q2, thinking="x" * soglia)) and not t(dict(q2, thinking="x" * (soglia + 3)))
             and not t(q2), "")
    verifica("V1: i bordi di troncata_nell_uscita",
             t(v1) and not t(dict(v1, eval=8192 + C.BUDGET_MARGINE))
             and t(dict(v1, eval=8192 + C.BUDGET_MARGINE + 1))
             and not t(dict(v1, budget_tolto=True)) and not t(dict(v1, budget=0))
             and not t(dict(v1, fine="stop")) and not t(e_budget)
             and t(dict(e_budget, ragionamento=2000))
             and not t({"content": "", "ragionamento": PIENA - 10, "fine": "length",
                        "eval": PIENA}), "")
    # J e J2 (terza, R2): il tempo delle troncate esce dalla guardia del tempo senza strumenti
    vero, vero_time = Copione.chat, C.time

    def lenta(self, *a, **k):
        prossima = self.passate[0] if self.passate else None
        _Orologio.t += 330 if isinstance(prossima, dict) and prossima.get("fine") else 120
        return vero(self, *a, **k)
    C.time, Copione.chat = _Orologio(), lenta
    try:
        lav, ris, log, cli, sb = gira(tmp, "revJ", [A_META, "Ci penso.", A_META, "Ci penso."]
                                      + LAVORO, max_passi=14)
        verifica("J: passate troncate da 330 s alternate a prosa: «fatto», niente «ha ragionato»",
                 ris.get("esito") == "fatto" and not any("senza strumenti" in x for x in log),
                 str(ris)[:200] + str(log[-3:]))
        lav, ris, log, cli, sb = gira(tmp, "revJ2", [A_META, "Ci penso."] + LAVORO, max_passi=14)
        ut = [str(m.get("content")) for m in lav.contesto.get("messages", [])
              if m.get("role") == "user"]
        verifica("J2: una troncata e una prosa: nessuna spinta «stai ragionando»",
                 ris.get("esito") == "fatto" and not any("Stai ragionando" in u for u in ut),
                 str(ut)[-300:])
        lav, ris, log, cli, sb = gira(tmp, "revJ3", ["Ci penso."] * 4, max_passi=8)
        verifica("contrario J: la prosa vera, 120 s a passata, fa ancora scattare la guardia",
                 any("senza strumenti" in x for x in log), str(log[-3:]))
    finally:
        C.time, Copione.chat = vero_time, vero
    # M (terza): con vLLM e «length» una chiamata intera e l'ultima rotta, quattro di fila:
    # l'agente va avanti (un file per passata), le intere si eseguono, non è «di fila»
    pp = [{"tool_calls": [scrivi(f"f{i}.py", "x = 1\n"), scrivi("programma.py", "def s")],
           "rotti": [1], "fine": "length", "eval": PIENA} for i in range(4)]
    lav, ris, log, cli, sb = gira(tmp, "revM", pp + LAVORO)
    verifica("M: chiamate intere eseguite e l'ultima rotta, quattro volte: «fatto», i file scritti",
             ris.get("esito") == "fatto" and all((sb.root / f"f{i}.py").exists() for i in range(4))
             and regole(lav).get("agente_uscita_troncata") == 4, str(ris)[:200])
    # N (terza, R1): in uno sviluppo, solo chiamate rotte oltre TRONCATE_MAX → tappa, e ogni
    # chiamata ha la sua risposta nella storia
    rotte = [{"tool_calls": [scrivi("programma.py", "def s"), scrivi("altro.py", "def t")],
              "rotti": [0, 1], "fine": "length", "eval": PIENA} for _ in range(TRONCATE_MAX + 1)]
    lav, ris, log, cli, sb = gira(tmp, "revN", rotte, tappe=True)
    verifica("N: tappa «troncata» dopo il giro sulle chiamate: la storia è ben formata",
             ris.get("esito") == "tappa" and ris.get("tipo_limite") == "troncata"
             and _storia_ben_formata(lav), str(ris)[:200])
    lav, ris, log, cli, sb = gira(tmp, "revN2", rotte)
    verifica("…fuori da uno sviluppo «limite» col motivo suo, la storia ben formata",
             ris.get("eccezione") == "Limite" and ris.get("tipo") == "troncata"
             and _storia_ben_formata(lav), str(ris)[:200])
    # R4 (terza): fuori da uno sviluppo, con gli esempi di accettazione verdi, le troncate oltre
    # il tetto passano da _consegna_al_tetto come gli altri tetti
    import prova_porte_consegna as PC
    from calliope.estensioni.prompt import controlla_consegna
    lav, sb, F2 = PC._estensione_con_esempi(tmp, "revR4")
    lav, ris, log, cli, sb = gira(tmp, "revR4", [[scrivi("estensione.py", F2.GIUSTA)], [ESEGUI]]
                                  + [dict(A_META) for _ in range(TRONCATE_MAX + 1)],
                                  lav=lav, sb=sb, controlla=lambda x: controlla_consegna(x))
    verifica("R4: esempi verdi e troncate oltre il tetto: «fatto» consegnato dal codice",
             ris.get("esito") == "fatto" and ris.get("consegna_al_tetto") == "troncata",
             str(ris)[:300])
    # R6 (terza; dalla revisione della PR #219, #191): il giro a vuoto in mezzo alle troncate.
    # Non è una chiamata eseguita e non le azzera più: tre troncate, un giro a vuoto e una
    # troncata sono la quarta. Il giro a vuoto non rompe il conto: con una chiamata eseguita dopo
    # di lui si riparte e il lavoro finisce «fatto»
    vuoto = {"giro_a_vuoto": "penso penso"}
    lav, ris, log, cli, sb = gira(tmp, "revR6", [A_META] * TRONCATE_MAX + [vuoto, A_META] + LAVORO)
    verifica("R6: tre troncate, un giro a vuoto, una troncata: la quarta, «limite» «troncata»",
             ris.get("eccezione") == "Limite" and ris.get("tipo") == "troncata"
             and len(cli.corpi) == TRONCATE_MAX + 2, str(ris)[:200])
    lav, ris, log, cli, sb = gira(tmp, "revR6b", [A_META] * TRONCATE_MAX
                                  + [vuoto, [scrivi("note.txt", "x")], A_META] + LAVORO)
    verifica("contrario R6: il giro a vuoto e poi una chiamata eseguita: si riparte, «fatto»",
             ris.get("esito") == "fatto"
             and regole(lav).get("agente_uscita_troncata") == TRONCATE_MAX + 1, str(ris)[:200])
    # Troncate alternate a giri a vuoto: prima il tetto dei token dopo 19 passate
    lav, ris, log, cli, sb = gira(tmp, "revR6c", [dict(vuota), dict(vuoto)] * 20, max_passi=40)
    verifica("R6: troncate e giri a vuoto alternati → «troncata» alla settima passata",
             ris.get("eccezione") == "Limite" and ris.get("tipo") == "troncata"
             and len(cli.corpi) == 7, str(ris)[:200] + f" passate {len(cli.corpi)}")
    # Q3 (seconda revisione della PR #219): piano e chiedi_permesso sono chiamate eseguite anche
    # con un esito non ok (il codice le ha guardate e ha risposto); il «prima chiama piano» no
    piano_no = {"name": "piano", "arguments": {"capacita_necessarie": ["inesistente"],
                                               "fattibile": True, "motivo": "x"}}
    permesso_no = {"name": "chiedi_permesso", "arguments": {"cosa": "x", "motivo": "y"}}
    for tag, c in (("piano", piano_no), ("chiedi_permesso", permesso_no)):
        lav, ris, log, cli, sb = gira(tmp, "revQ3" + tag, [dict(vuota), [c]] * 5, max_passi=40,
                                      piano=True)
        verifica(f"Q3: troncate alternate a {tag} (esito non ok): azzerano, niente «troncata»",
                 ris.get("tipo") != "troncata"
                 and regole(lav).get("agente_uscita_troncata") == 5,
                 str(ris)[:200] + str(regole(lav)))
    lav, ris, log, cli, sb = gira(tmp, "revQ3prima", [dict(vuota), [scrivi("programma.py",
                                                                        GIUSTO)]] * 6,
                                  max_passi=40, piano=True)
    verifica("Q3: troncate e scrivi_file rifiutato con «prima chiama piano» → «troncata»",
             ris.get("eccezione") == "Limite" and ris.get("tipo") == "troncata"
             and len(cli.corpi) == 7, str(ris)[:200] + f" passate {len(cli.corpi)}")
    # P3 (revisione della PR #219): una chiamata che non parte (strumento sconosciuto, argomenti
    # contro lo schema) non è una chiamata eseguita e non azzera le troncate
    for tag, c in (("sconosciuto", {"name": "inesistente", "arguments": {}}),
                   ("argomenti", {"name": "scrivi_file", "arguments": {}})):
        lav, ris, log, cli, sb = gira(tmp, "revP3" + tag, [dict(vuota), [c]] * 12, max_passi=40)
        verifica(f"P3: troncate alternate a una chiamata che non parte ({tag}) → «troncata»",
                 ris.get("eccezione") == "Limite" and ris.get("tipo") == "troncata"
                 and len(cli.corpi) == 7, str(ris)[:200] + f" passate {len(cli.corpi)}")
    # I (seconda) e N2: col client di vLLM l'ultima chiamata a max_tokens è rotta anche col JSON
    # che si legge (sezione 2); qui il contrario del ciclo: senza `rotti` (Ollama, chiamate
    # intere) la chiamata si esegue
    lav, ris, log, cli, sb = gira(tmp, "revI", [
        {"tool_calls": [scrivi("programma.py", GIUSTO)], "fine": "length", "eval": PIENA},
        [scrivi("test_programma.py", TEST)], [ESEGUI], [CONSEGNA]])
    verifica("I: contrario, senza `rotti` la chiamata intera si esegue (Ollama)",
             ris.get("esito") == "fatto" and "agente_uscita_troncata" not in regole(lav),
             str(regole(lav)))
    # B, C, D, G, H (prima e seconda): la modifica inversa e il già visto
    due = "def somma(a, b):\n    return a + b\n\n\ndef doppio(x):\n    return x\n"
    lav, ris, *_ = gira(tmp, "revB", [
        [scrivi("programma.py", due), scrivi("test_programma.py", TEST)],
        [modifica("programma.py", "return a + b", "return a - b")],
        [modifica("programma.py", "return x", "return 2 * x")], [ESEGUI],
        [modifica("programma.py", "return a - b", "return a + b")], [ESEGUI], [CONSEGNA]])
    mf = risultati(lav, "modifica_file")
    verifica("B: la correzione vera dopo un altro cambiamento è accettata",
             [m.get("ok") for m in mf] == [True, True, True] and ris.get("esito") == "fatto",
             str(mf)[:300])
    lav, ris, *_ = gira(tmp, "revC", [
        [scrivi("programma.py", GIUSTO), scrivi("test_programma.py", TEST)],
        [modifica("programma.py", "a + b", "b + a")],
        [scrivi("programma.py", "def somma(a, b):\n    # nuova versione\n    return b + a\n")],
        [modifica("programma.py", "b + a", "a + b")], [ESEGUI], [CONSEGNA]])
    mf = risultati(lav, "modifica_file")
    verifica("C: dopo uno scrivi_file la modifica che rimette un testo tolto prima è accettata",
             [m.get("ok") for m in mf] == [True, True], str(mf)[:300])
    lav, ris, *_ = gira(tmp, "revD", [
        [scrivi("programma.py", SBAGLIATO), scrivi("test_programma.py", TEST)],
        [scrivi("programma.py", ALTRO)], [scrivi("programma.py", SBAGLIATO)], [ESEGUI],
        [scrivi("programma.py", ALTRO)], [scrivi("programma.py", SBAGLIATO)],
        [scrivi("programma.py", GIUSTO)], [ESEGUI], [CONSEGNA]])
    sc = [r.get("gia_visto") or "" for r in risultati(lav, "scrivi_file")]
    verifica("D: A, B, A, test, B, A: la passata detta è quella del test (2 passate fa)",
             "su cui esegui_test, 2 passate fa, dava" in sc[5], str(sc))
    lav, ris, *_ = gira(tmp, "revG", [
        [scrivi("programma.py", GIUSTO), scrivi("test_programma.py", TEST)],
        [modifica("programma.py", "a + b", "b + a")], [ESEGUI],
        [modifica("programma.py", "b + a", "a + b")], [CONSEGNA]])
    mf = risultati(lav, "modifica_file")
    verifica("G: l'oscillazione pura con un esegui_test in mezzo è rifiutata",
             [m.get("ok") for m in mf] == [True, False], str(mf)[:300])
    lav, ris, *_ = gira(tmp, "revH", [
        [scrivi("programma.py", GIUSTO), scrivi("test_programma.py", TEST)],
        [modifica("programma.py", "a + b", "b + a")], [scrivi("note.txt", "x")],
        [modifica("programma.py", "b + a", "a + b")], [CONSEGNA]])
    mf = risultati(lav, "modifica_file")
    verifica("H: l'inversa dopo lo scrivi_file di un altro file è accettata",
             [m.get("ok") for m in mf] == [True, True], str(mf)[:300])
    verifica("il fatto della troncata è quello di sempre", "max_tokens" in USCITA_TRONCATA_TESTO)


# ═══════════════ 8. gli strumenti onesti nel ciclo della ricerca (21/10, #189) ═══════════════

class _Biblioteca:
    def __init__(self):
        self.domande = []

    def cerca(self, domanda):
        from types import SimpleNamespace
        self.domande.append(domanda)
        return [SimpleNamespace(titolo="Borgo", fonte="wikipedia", testo="Il borgo è antico.")]


class _Web:
    pronta = True
    URL = "https://esempio.invalid/borgo"

    def __init__(self):
        self.lette = []

    def cerca(self, domanda, n=6):
        from types import SimpleNamespace
        return {"ok": True, "risultati": [SimpleNamespace(
            titolo="Il borgo", sito="esempio.invalid", url=self.URL, testo="Antico.", data=None)]}

    def leggi(self, url):
        self.lette.append(url)
        return {"ok": True, "sito": "esempio.invalid", "url": url, "titolo": "Il borgo",
                "testo": "Il borgo fu fondato nel Trecento."}


def ricerca(passate):
    """Agente.ricerca con il copione, la biblioteca e la rete finte: (lavoro, risultato o
    {"eccezione"…}, copione, web, esiti) con gli esiti di tutti gli strumenti, anche quelli
    dell'ultima passata (che non tornano all'agente)."""
    from calliope.agenti.ciclo import Lavoro
    cli = Copione(passate)
    ag = G.agente(cli, [])
    ag.biblioteca, ag.web = _Biblioteca(), _Web()
    lav = Lavoro("R", "ricerca", "la storia del borgo")
    esiti = []
    lav.osservatore = lambda _l, ev, d: esiti.append(d) if ev == "esito" else None
    try:
        ris = ag.ricerca(lav)
    except Exception as e:  # noqa: BLE001 — Limite
        ris = {"eccezione": type(e).__name__, "tipo": getattr(e, "tipo", ""), "motivo": str(e),
               "parziale": dict(getattr(e, "parziale", None) or {})}
    return lav, ris, cli, ag.web, esiti


def _ben_formata_corpo(msgs) -> bool:
    """La storia mandata al modello (revisione della PR #218): ogni messaggio dell'agente con N
    chiamate ha dopo di sé N messaggi tool, con i nomi delle chiamate e nello stesso ordine."""
    for i, m in enumerate(msgs):
        chiamate = m.get("tool_calls") or [] if m.get("role") == "assistant" else []
        if not chiamate:
            continue
        dopo = msgs[i + 1:i + 1 + len(chiamate)]
        if [x.get("role") for x in dopo] != ["tool"] * len(chiamate) or \
                [x.get("tool_name") for x in dopo] != [c["function"]["name"] for c in chiamate]:
            return False
    return True


def _tool_nel_corpo(cli, nome) -> list:
    """I risultati dello strumento `nome` nell'ultima richiesta mandata al modello."""
    return [json.loads(m["content"]) for m in (cli.corpi[-1] if cli.corpi else [])
            if m.get("role") == "tool" and m.get("tool_name") == nome
            and m["content"].lstrip().startswith("{")]


def _consegna_r(testo="Il borgo è antico.", riassunto="Il borgo è antico."):
    return {"name": "consegna", "arguments": {"testo": testo, "riassunto": riassunto}}


def prova_ricerca():
    sezione("8. gli strumenti onesti nel ciclo della ricerca (#189)")
    from calliope.agenti.ciclo import (RELAZIONE_TAGLIATA, TRONCATE_MAX, USCITA_TRONCATA_PENSIERO,
                                       USCITA_TRONCATA_RICERCA, USCITA_TRONCATA_STRUMENTO,
                                       USCITA_TRONCATA_TESTO_RICERCA)
    cerca = {"name": "web_cerca", "arguments": {"domanda": "storia del borgo"}}
    leggi = {"name": "web_leggi", "arguments": {"url": _Web.URL}}

    # Lo strumento sconosciuto: l'elenco c'era già, ora anche la regola
    lav, ris, cli, web, esiti = ricerca([[{"name": "cancella_file", "arguments": {}}],
                                         [_consegna_r()]])
    sc = esiti[0] if esiti else {}
    sc = sc.get("esito") or {}
    verifica("ricerca, lo strumento che non c'è: l'elenco dei veri e la regola",
             sc.get("ok") is False and "cancella_file" in sc.get("errore", "")
             and "web_cerca" in sc.get("cosa_fare", "")
             and regole(lav).get("agente_strumento_sconosciuto") == 1
             and ris.get("esito") == "fatto", str(sc) + str(regole(lav)))

    # La consegna prima di una web_leggi: la consegna vale (come nel codice, #185), la lettura
    # non si esegue e ha la regola. Sugli schermi niente, come nel codice (revisione della PR
    # #218: l'esito senza la riga della sua chiamata finiva sotto la chiamata di prima)
    lav, ris, cli, web, esiti = ricerca([[cerca], [_consegna_r(), leggi]])
    dopo = [e for e in esiti if e.get("nome") == "web_leggi"]
    verifica("ricerca, consegna seguita da web_leggi: consegnata, la lettura non eseguita e detta",
             ris.get("esito") == "fatto" and ris.get("testo") == "Il borgo è antico."
             and not web.lette and not dopo
             and regole(lav).get("agente_dopo_consegna") == 1, str(esiti) + str(regole(lav)))
    lav, ris, cli, web, esiti = ricerca([[cerca], [leggi], [_consegna_r()]])
    verifica("contrario: la lettura prima della consegna si esegue, nessuna regola",
             ris.get("esito") == "fatto" and web.lette == [_Web.URL]
             and not any(r in regole(lav) for r in NUOVE), str(regole(lav)))

    # La chiamata a metà contro l'argomento davvero mancante
    lav, ris, cli, web, esiti = ricerca([
        {"tool_calls": [{"name": "biblioteca_cerca", "arguments": {}}], "rotti": [0],
         "fine": "length"},
        [{"name": "biblioteca_cerca", "arguments": {}}],
        [_consegna_r()]])
    # Sui messaggi tool mandati al modello, non solo sugli schermi (revisione della PR #218)
    bib = _tool_nel_corpo(cli, "biblioteca_cerca")
    t = bib[0] if bib else {}
    verifica("ricerca, la chiamata a metà: non eseguita, «troncata», non «manca domanda»",
             t.get("errore") == USCITA_TRONCATA_STRUMENTO and "domanda" not in str(t)
             and "relazione" not in str(t)
             and not cli.passate and regole(lav).get("agente_uscita_troncata") == 1, str(t))
    m = bib[1] if len(bib) > 1 else {}
    verifica("contrario: l'argomento davvero mancante dice cosa manca",
             "domanda" in str(m) and "troncata" not in str(m), str(m)[:300])
    # La consegna a metà non chiude con la relazione vuota
    lav, ris, cli, web, esiti = ricerca([
        {"tool_calls": [{"name": "consegna", "arguments": {}}], "rotti": [0], "fine": "length"},
        [_consegna_r("Relazione più breve.")]])
    cons = _tool_nel_corpo(cli, "consegna")
    verifica("ricerca, la consegna a metà: non chiude, la seconda sì",
             ris.get("testo") == "Relazione più breve." and len(cli.corpi) == 2
             and [c.get("errore") for c in cons] == [USCITA_TRONCATA_RICERCA]
             and regole(lav).get("agente_uscita_troncata") == 1, str(ris)[:200] + str(cons))

    # La relazione troncata contro quella intera
    lav, ris, cli, web, esiti = ricerca([
        {"content": "# Il borgo\nIl borgo fu fondato nel", "fine": "length"},
        "Il borgo fu fondato nel Trecento."])
    utenti = [x["content"] for x in cli.corpi[-1] if x.get("role") == "user"] if cli.corpi else []
    verifica("ricerca, la relazione fermata a max_tokens: il fatto e si continua",
             ris.get("testo") == "Il borgo fu fondato nel Trecento." and len(cli.corpi) == 2
             and USCITA_TRONCATA_TESTO_RICERCA in utenti
             and regole(lav).get("agente_uscita_troncata") == 1, str(ris)[:200] + str(utenti))
    # Il solo ragionamento fermato, col testo vuoto: non è «un testo a metà» (revisione PR #218)
    lav, ris, cli, web, esiti = ricerca([
        {"content": "", "thinking": "Devo cercare la storia del borgo. " * 20, "fine": "length"},
        "Il borgo fu fondato nel Trecento."])
    utenti = [x["content"] for x in cli.corpi[-1] if x.get("role") == "user"] if cli.corpi else []
    verifica("ricerca, il solo ragionamento fermato: il fatto senza «testo a metà», si continua",
             ris.get("testo") == "Il borgo fu fondato nel Trecento."
             and USCITA_TRONCATA_PENSIERO in utenti and USCITA_TRONCATA_TESTO_RICERCA not in utenti,
             str(ris)[:200] + str(utenti))
    lav, ris, cli, web, esiti = ricerca([{"content": "Il borgo fu fondato nel Trecento.",
                                          "fine": "stop"}])
    verifica("contrario: la relazione intera senza consegna resta la relazione",
             ris.get("testo") == "Il borgo fu fondato nel Trecento." and len(cli.corpi) == 1
             and not any(r in regole(lav) for r in NUOVE), str(ris)[:200])
    # Il tetto delle troncate di fila, con il motivo suo
    a_meta = {"content": "Il borgo fu fondato nel", "fine": "length"}
    lav, ris, cli, web, esiti = ricerca([dict(a_meta) for _ in range(8)])
    verifica("ricerca, oltre TRONCATE_MAX troncate di fila: «limite» col motivo suo",
             ris.get("eccezione") == "Limite" and ris.get("tipo") == "troncata"
             and f"fermata {TRONCATE_MAX + 1} volte di fila" in ris.get("motivo", "")
             and len(cli.corpi) == TRONCATE_MAX + 1, str(ris)[:200])
    # L'ultima relazione tagliata resta nel parziale, detta come tagliata (revisione PR #218)
    par = ris.get("parziale") or {}
    verifica("…e l'ultima relazione tagliata nel risultato, detta come tagliata",
             "relazione_tagliata" not in par
             and str(par.get("testo", "")).startswith(RELAZIONE_TAGLIATA)
             and "Il borgo fu fondato nel" in par.get("testo", ""),
             str(par)[:300])
    # Le chiamate tutte rotte, due per passata: ognuna ha la sua risposta nella storia mandata al
    # modello (revisione della PR #218), e nel parziale nessuna relazione inventata
    rotta = {"tool_calls": [{"name": "biblioteca_cerca", "arguments": {}},
                            {"name": "web_leggi", "arguments": {}}], "rotti": [0, 1],
             "fine": "length"}
    lav, ris, cli, web, esiti = ricerca([dict(rotta) for _ in range(8)])
    corpo = cli.corpi[-1] if cli.corpi else []
    verifica("…anche con le chiamate tutte rotte, ognuna con la sua risposta",
             ris.get("eccezione") == "Limite" and ris.get("tipo") == "troncata"
             and len(cli.corpi) == TRONCATE_MAX + 1 and _ben_formata_corpo(corpo)
             and sum(1 for m in corpo if m.get("role") == "tool") == 2 * TRONCATE_MAX
             and len(esiti) == 2 * (TRONCATE_MAX + 1), str(ris)[:200] + f" esiti {len(esiti)}")
    verifica("contrario: senza testo tagliato il parziale non ha una relazione",
             "testo" not in (ris.get("parziale") or {}), str(ris)[:300])
    # La consegna fermata a max_tokens col testo che si legge (seconda revisione della PR #218:
    # vLLM la segna rotta anche col JSON leggibile): la relazione fino al taglio non si perde,
    # e le consegne rifiutate non sono fra le cose fatte
    tagliata = {"tool_calls": [{"name": "consegna", "arguments": {
        "testo": "# Il borgo\nIl borgo fu fondato nel Trecento e poi"}}], "rotti": [0],
        "fine": "length"}
    lav, ris, cli, web, esiti = ricerca([[cerca]] + [dict(tagliata) for _ in range(8)])
    par = ris.get("parziale") or {}
    verifica("ricerca, quattro consegne tagliate: «limite» col testo della consegna nel parziale",
             ris.get("tipo") == "troncata" and str(par.get("testo", "")).startswith(
                 RELAZIONE_TAGLIATA) and "fondato nel Trecento e poi" in par.get("testo", "")
             and len(cli.corpi) == TRONCATE_MAX + 2, str(ris)[:300])
    verifica("…e nel riassunto le cose fatte, senza le consegne rifiutate",
             "web_cerca" in par.get("riassunto", "") and "consegna" not in par.get("riassunto", ""),
             str(par.get("riassunto")))
    from calliope.agenti.contesto_lavoro import estrattivo
    d = estrattivo([{"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "consegna", "arguments": {"riassunto": "Fatto."}}}]},
        {"role": "tool", "tool_name": "consegna", "content": json.dumps({"ok": True})}], None)
    verifica("contrario: la consegna accettata resta fra le cose fatte", d["fatto"] == ["consegna"],
             str(d["fatto"]))
    # La consegna buona e poi una chiamata rotta: è «dopo la consegna», non «troncata» (seconda
    # revisione della PR #218: l'ordine dei due controlli, come nel codice)
    lav, ris, cli, web, esiti = ricerca([[cerca], {"tool_calls": [
        _consegna_r(), {"name": "web_leggi", "arguments": {}}], "rotti": [1], "fine": "length"}])
    verifica("ricerca, consegna buona e una chiamata rotta dopo: consegnata, «dopo la consegna»",
             ris.get("esito") == "fatto" and regole(lav).get("agente_dopo_consegna") == 1
             and "agente_uscita_troncata" not in regole(lav)
             and not [e for e in esiti if e.get("nome") == "web_leggi"], str(regole(lav)))

    # A voce (seconda revisione della PR #218): la ricerca fermata non ha un file nella cartella
    # Lavori, e la relazione tagliata si offre
    from calliope.agenti.ciclo import Lavoro
    from calliope.agenti.servizio import RICERCA_INCOMPLETA, Lavori
    from types import SimpleNamespace
    s = SimpleNamespace(female=True, in_tappa=lambda lv: False)
    motivo = "ho dovuto fermarlo: " + "la sua uscita si è fermata 4 volte di fila"
    lv = Lavoro("R1", "ricerca", "la storia del borgo", titolo="La storia del borgo")
    lv.stato = "errore"
    lv.risultato = {"esito": "limite", "motivo": motivo, "riassunto": "fatto: web_cerca",
                    "testo": RELAZIONE_TAGLIATA + "\n\nIl borgo fu fondato nel"}
    f = Lavori.frase_finale(s, lv)
    verifica("a voce: la ricerca fermata con la relazione tagliata la offre, senza «cartella»",
             f.endswith(RICERCA_INCOMPLETA) and "cartella" not in f and "fermata 4 volte" in f, f)
    lv.risultato = {"esito": "limite", "motivo": motivo, "riassunto": "fatto: web_cerca"}
    f = Lavori.frase_finale(s, lv)
    verifica("contrario: senza relazione tagliata niente offerta, e nemmeno la «cartella»",
             RICERCA_INCOMPLETA not in f and "cartella" not in f, f)
    lc = Lavoro("C1", "codice", "una funzione", titolo="La somma")
    lc.stato = "errore"
    lc.risultato = {"esito": "limite", "motivo": motivo, "file": ["somma.py"]}
    f = Lavori.frase_finale(s, lc)
    verifica("contrario: il codice fermato ha i file nella cartella Lavori, come prima",
             "cartella Lavori" in f and RICERCA_INCOMPLETA not in f, f)
    # Il giro a vuoto azzera le troncate di fila (revisione della PR #218): qui il conto è davvero
    # di fila. Nel codice dal 21/10 (#191, R6 della sezione 7) non le azzera più
    vuoto = {"giro_a_vuoto": "penso penso"}
    lav, ris, cli, web, esiti = ricerca([dict(a_meta) for _ in range(TRONCATE_MAX)]
                                        + [vuoto, dict(a_meta), [_consegna_r()]])
    verifica("ricerca, tre troncate, un giro a vuoto, una troncata: non è la quarta di fila",
             ris.get("esito") == "fatto" and ris.get("testo") == "Il borgo è antico.",
             str(ris)[:200])
    # Chiamate rotte e buone nella stessa passata: non «di fila», come M nel codice
    misto = {"tool_calls": [{"name": "biblioteca_cerca", "arguments": {"domanda": "borgo"}},
                            {"name": "web_leggi", "arguments": {}}], "rotti": [1],
             "fine": "length"}
    lav, ris, cli, web, esiti = ricerca([dict(misto) for _ in range(TRONCATE_MAX + 3)]
                                        + [[_consegna_r()]])
    verifica("ricerca, una chiamata buona e una rotta per passata: il lavoro avanza, «fatto»",
             ris.get("esito") == "fatto" and len(cli.corpi) == TRONCATE_MAX + 4
             and sum(1 for e in esiti if e.get("nome") == "biblioteca_cerca")
             == TRONCATE_MAX + 3 and _ben_formata_corpo(cli.corpi[-1])
             and regole(lav).get("agente_uscita_troncata") == TRONCATE_MAX + 3,
             str(ris)[:200] + str(regole(lav)))


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
        prova_revisioni(tmp / "revisioni")
        prova_ricerca()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
