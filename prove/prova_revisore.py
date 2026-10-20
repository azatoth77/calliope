"""Il revisore a contesto pulito nel ciclo dell'agente, a secco (20/10/2026, issue #190; area
agenti-estensioni; banco #182, ricerca docs/ricerche/2026-10-19-solidita-harness-sviluppo.md
§ 3.6 e § 4).

Con l'agente finto, il revisore finto (le passate con lo schema del revisore hanno le loro
risposte preparate) e la sandbox col docker finto:

1. il modulo: il menu ridotto con la domanda facoltativa (contrario: il menu del banco, parola
   per parola), i fallimenti divisi fra esempi di accettazione e test dell'agente (Python e
   JavaScript), l'esempio tolto con il resto del file intatto, la soglia dello stesso errore, la
   chiave della Config (il true di YAML rifiutato), il pacchetto da un lavoro senza la
   trascrizione né il diario (.calliope), con quali test sono esempi;
2. la consegna con un esempio rosso: giudicato sbagliato → tolto dagli esempi del lavoro, con la
   regola, e la consegna va avanti («fatto», nel rapporto e sulla scheda di revisione);
   giudicato giusto → resta, e all'agente il fatto con file e causa; una sola volta per giro
   per lo stesso esempio; «consegna» senza lo stato consegnabile ignorata (con: tolto); contrari:
   test verdi (nessuna passata), la voce che parla (nessuna passata), spento;
3. l'ombra: il verdetto nel registro e nella riga del banco, all'agente niente, il file degli
   esempi uguale byte per byte e il lavoro com'era;
4. il tetto: l'esempio sbagliato tolto, e il codice chiude il lavoro con gli esempi rimasti
   verdi;
5. la tappa con i test dell'agente rossi: il fatto apre il giro dopo, la domanda va nel rapporto
   della tappa; dopo due giri uguali il momento «giri_uguali»; la consegna rossa che diventa
   tappa il momento «consegna_rossa»;
6. lo stesso errore tre volte di fila nel giro: una passata, il fatto nel risultato del terzo
   esegui_test; contrario: errori diversi;
7. l'esempio di accettazione mai cambiato dall'agente: scrivi_file e modifica_file rifiutati,
   anche dopo che il revisore ne ha tolto uno.

    python prove\\prova_revisore.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

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
    """L'agente finto (ogni passata una lista di chiamate, o un testo) e il revisore finto: una
    passata con lo schema del revisore prende da `revisore` (un dict per il verdetto, None per
    una risposta che non è JSON) e non consuma le passate dell'agente."""

    def __init__(self, passate, revisore=()):
        self.passate, self.revisore = list(passate), list(revisore)
        self.corpi, self.revisioni, self.url = [], [], None

    def chat(self, body, su_pezzo=None, controlla=None, su_flusso=None):
        if '"verdetto"' in json.dumps(body.get("format") or {}):
            self.revisioni.append(body)
            v = self.revisore.pop(0) if self.revisore else None
            return {"content": json.dumps({"file": "", "riga": 0, "test": "", "causa": "c",
                                           "azione": "a", **v}, ensure_ascii=False)
                    if v else "non è JSON", "eval": 300, "prompt": 5000}
        self.corpi.append(json.loads(json.dumps(body["messages"], default=str)))
        p = self.passate.pop(0) if self.passate else "Ho finito."
        out = {"content": "", "thinking": "", "tool_calls": [], "eval": 50, "prompt": 100,
               "s": 0}
        if isinstance(p, str):
            out["content"] = p
        else:
            out["tool_calls"] = p
        return out


def scrivi(percorso, contenuto):
    return {"name": "scrivi_file", "arguments": {"percorso": percorso, "contenuto": contenuto}}


def consegna(esito="fatto", **extra):
    return {"name": "consegna", "arguments": {"riassunto": "Fatto.", "esito": esito, **extra}}


ESEGUI = {"name": "esegui_test", "arguments": {}}
LEGGI = {"name": "leggi_file", "arguments": {"percorso": "estensione.py"}}
GIUSTA = G.CONVERTITORE
ROTTA = GIUSTA.replace('"miglia": 1609.344', '"miglia": 1500.0')
TEST_VERDE = ("import unittest\nfrom calliope_estensione import CalliopeFinta\n"
              "from estensione import esegui\n\n\nclass P(unittest.TestCase):\n"
              "    def test_metri(self):\n"
              "        r = esegui({'valore': 3, 'da': 'metri', 'a': 'metri'}, CalliopeFinta())\n"
              "        self.assertEqual(r['risultato'], 3)\n")
TEST_ROSSO = TEST_VERDE.replace("['risultato'], 3)", "['risultato'], 4)")
# Gli esempi dell'analisi: il primo giusto, il secondo sbagliato (2 km sono 2000 m, non 3000)
ANALISI = {
    "contraddizioni": [], "scelte": [], "al_collaudo": [], "campo_numero": "risultato",
    "input": [{"nome": "valore", "tipo": "number"}, {"nome": "da", "tipo": "string"},
              {"nome": "a", "tipo": "string"}],
    "esempi": [
        {"requisito": 1, "dati": {"valore": 10, "da": "miglia", "a": "chilometri"},
         "numero": 16.09, "tolleranza": 0.01, "contiene": "", "trovato": None},
        {"requisito": 1, "dati": {"valore": 2, "da": "chilometri", "a": "metri"},
         "numero": 3000, "tolleranza": None, "contiene": "", "trovato": None}]}
SBAGLIATO = "test_r1_2"
GIUSTO_ES = "test_r1_1"
MANIFESTO = {"nome": "distanze", "titolo": "Distanze",
             "cosa_fa": {"verbo": "converte", "oggetto": "le distanze"},
             "input": {"type": "object", "properties": {
                 "valore": {"type": "number", "description": "il valore"},
                 "da": {"type": "string", "description": "unità di partenza"},
                 "a": {"type": "string", "description": "unità d'arrivo"}},
                 "required": ["valore", "da", "a"]},
             "permessi": {}, "livello": "familiare", "limiti": {"tempo_s": 10, "memoria_mb": 256}}


def estensione(tmp, nome, codice=GIUSTA, test=TEST_VERDE):
    """La sandbox d'un'estensione con gli esempi dell'analisi in sola lettura e i file già
    scritti (il codice, il test dell'agente, il manifesto)."""
    from calliope.agenti import accettazione as acc
    from calliope.agenti.ciclo import Lavoro
    from calliope.agenti.scheletri import prepara_estensione
    sb = G.sandbox(tmp, nome)
    sb.scrivi("test_estensione.py", test)
    prepara_estensione(sb)
    sb.scrivi("manifesto.json", json.dumps(MANIFESTO))
    sb.scrivi("estensione.py", codice)
    lav = Lavoro(nome, "estensione", "Un convertitore di distanze")
    an = acc.interpreta(ANALISI, 1, True)
    sb.scrivi(acc.FILE, acc.test_python(an))
    sb.sola_lettura |= {acc.FILE}
    lav.accettazione = {"stato": "pronta", "file": True, "nome_file": acc.FILE,
                        "esempi": len(an["esempi"]), "requisiti_provati": [1],
                        "testi_provati": ["convertire"]}
    return lav, sb


class ArbitroVoce:
    """L'arbitro finto con la voce che parla (occupata_ora): il revisore non entra."""

    def __init__(self):
        from calliope.agenti.arbitro import Arbitro
        self._a = Arbitro(False, 0)

    def __getattr__(self, n):
        return getattr(self._a, n)

    def occupata_ora(self):
        return True


def gira(tmp, nome, passate, revisore=(), modo="attivo", lav=None, sb=None, max_passi=12,
         tappe=False, voce=False, **kw):
    """Agente.codice con il copione; (lavoro, risultato o {"eccezione", …}, log, copione, sb)."""
    cli = Copione(passate, revisore)
    log = []
    ag = G.agente(cli, log)
    ag.cfg.agenti_revisore = modo
    ag.max_passi = max_passi
    if voce:
        ag.arbitro = ArbitroVoce()
    if lav is None:
        lav, sb = estensione(tmp, nome, **kw)
    lav.tappe = tappe
    try:
        ris = ag.codice(lav, sb)
    except Exception as e:  # noqa: BLE001 — Limite
        ris = {"eccezione": type(e).__name__, "tipo": getattr(e, "tipo", ""), "motivo": str(e)}
    return lav, ris, log, cli, sb


def regole(lav) -> dict:
    return (lav.segnali or {}).get("regole") or {}


def risultati(lav, nome) -> list[str]:
    return [m["content"] for m in (lav.contesto.get("messages") or [])
            if m.get("role") == "tool" and m.get("tool_name") == nome]


def utenti(cli) -> list[str]:
    return [m["content"] for c in cli.corpi for m in c if m.get("role") == "user"]


def esempi_file(sb) -> list:
    from calliope.agenti import accettazione as acc
    from calliope.agenti.revisore import esempi_del_file
    return esempi_del_file((sb.root / acc.FILE).read_text(encoding="utf-8"))[0]


# ═══════════════════════════ 1. il modulo ═══════════════════════════

def prova_modulo(tmp: Path):
    sezione("1. il modulo del revisore")
    from calliope.agenti import accettazione as acc
    from calliope.agenti import revisore as rv
    s = rv.schema()
    verifica("il menu ridotto: test_sbagliato, codice_sbagliato, consegna, e la domanda "
             "facoltativa (non tra i campi obbligatori)",
             s["properties"]["verdetto"]["enum"] == ["test_sbagliato", "codice_sbagliato",
                                                     "consegna"]
             and "domanda" in s["properties"] and "domanda" not in s["required"], str(s))
    verifica("…il prompt del ciclo senza cambia_strada né chiedi_persona, con gli esempi di "
             "accettazione e la domanda", "cambia_strada" not in rv.SISTEMA
             and "chiedi_persona" not in rv.SISTEMA and "esempi di accettazione" in rv.SISTEMA
             and "«domanda»" in rv.SISTEMA)
    b = rv.schema(rv.VERDETTI_BANCO)
    verifica("contrario: il menu del banco del 19/10, sei verdetti e nessuna domanda",
             b["properties"]["verdetto"]["enum"] == list(rv.VERDETTI_BANCO)
             and "domanda" not in b["properties"] and "cambia_strada" in rv.SISTEMA_BANCO
             and "esempi di accettazione" not in rv.SISTEMA_BANCO)
    js = ("ok R1 esempio 1: 2 giocatori, casella 1\nFALLITO R2 esempio 3: 2 giocatori, casella 5:"
          " la fase deve essere «fine»\nFALLITO tre in fila vince: atteso 1\n"
          "FALLITO prova di fumo del gioco: errore\n")
    e, altri = rv.fallimenti_divisi(js, acc.FILE_GIOCO, False)
    verifica("JavaScript: l'esempio rosso col suo numero, il test dell'agente e la prova di fumo "
             "fra gli altri", [x[:2] for x in e] == [(3, "R2 esempio 3")] and altri == 2,
             f"{e} {altri}")
    py = ("FAIL: test_r1_2 (test_accettazione.Accettazione.test_r1_2)\n"
          "FAIL: test_somma (test_estensione.P.test_somma)\nRan 3 tests\n")
    e, altri = rv.fallimenti_divisi(py, acc.FILE, False)
    verifica("Python: l'esempio di test_accettazione.py e il test dell'agente",
             [x[:2] for x in e] == [(2, "test_r1_2")] and altri == 1, f"{e} {altri}")
    e, altri = rv.fallimenti_divisi("Traceback: ImportError", acc.FILE, False)
    verifica("contrario: un'uscita rossa senza fallimenti riconosciuti è un fallimento altro",
             e == [] and altri == 1)
    an = acc.interpreta(ANALISI, 1, True)
    testo = acc.test_python(an)
    nuovo, tolto = rv.senza_esempio(testo, 2)
    prima, dopo = testo.split("ESEMPI = json.loads(")[0], nuovo.split("ESEMPI = json.loads(")[0]
    verifica("l'esempio 2 tolto: resta il primo, il resto del file uguale byte per byte",
             rv.esempi_del_file(nuovo)[0] == an["esempi"][:1] and tolto == an["esempi"][1]
             and prima == dopo and testo.split("RICONOSCIUTI = ")[1]
             == nuovo.split("RICONOSCIUTI = ")[1], nuovo[:200])
    js_testo = acc.test_js({"esempi": [{"requisito": 1, "giocatori": 2, "mosse": [],
                                        "atteso": {"fase": "fine"}},
                                       {"requisito": 2, "giocatori": 2, "mosse": [],
                                        "atteso": {"fase": "esito"}}]})
    n2, t2 = rv.senza_esempio(js_testo, 1)
    verifica("…anche in accettazione.test.js (const ESEMPI), con il corpo del gioco intatto",
             t2["requisito"] == 1 and len(rv.esempi_del_file(n2)[0]) == 1
             and n2.endswith(acc.CORPO_JS), n2[-200:])
    verifica("contrario: un numero che non c'è non toglie niente", rv.senza_esempio(testo, 9)
             is None)
    verifica("il nome dell'esempio nel verdetto («R2 esempio 3», «test_r1_2»)",
             rv.esempio_nel_test(acc.FILE_GIOCO, "R2 esempio 3: 2 giocatori") == 3
             and rv.esempio_nel_test(acc.FILE, "test_r1_2") == 2
             and rv.esempio_nel_test(acc.FILE, "tre in fila") is None)
    verifica("lo stesso errore tre volte di fila; contrari: due volte, errori diversi",
             rv.stesso_errore({"errori_test": ["a", "b", "b", "b"]})
             and not rv.stesso_errore({"errori_test": ["b", "b"]})
             and not rv.stesso_errore({"errori_test": ["b", "a", "b"]}))
    from calliope.config import VALIDATORI, Config
    v = VALIDATORI["agenti_revisore"]
    try:
        v(True)
        vero = "accettato"
    except ValueError:
        vero = "rifiutato"
    verifica("la chiave agenti_revisore: di serie «ombra»; false è «spento», il true di YAML "
             "rifiutato", Config().agenti_revisore == "ombra" and v(False) == "spento"
             and v("Attivo") == "attivo" and vero == "rifiutato", vero)
    lav, sb = estensione(tmp, "pacchetto", codice=ROTTA)
    (sb.root / ".calliope").mkdir(exist_ok=True)
    (sb.root / ".calliope" / "passo-3.txt").write_text("TRASCRIZIONE-DELL-AGENTE",
                                                       encoding="utf-8")
    sb.scrivi("estensione.py", ROTTA.replace("METRI = {", "# Musica: fatto\nMETRI = {"))
    lav.segnali = {"errori_test": ["FAIL test_r1_1"], "diario": "DIARIO-DELL-AGENTE"}
    lav.contesto = {"messages": [{"role": "assistant", "content": "RIASSUNTO-DELL-AGENTE"}]}
    ag = G.agente()
    p = rv.pacchetto_lavoro(ag, lav, sb, sb.test())
    m = rv.messaggio(p)
    verifica("il pacchetto da un lavoro: niente trascrizione, diario, conversazione né commenti",
             all(x not in m for x in ("TRASCRIZIONE-DELL-AGENTE", "DIARIO-DELL-AGENTE",
                                       "RIASSUNTO-DELL-AGENTE", "Musica")),
             [x for x in ("TRASCRIZIONE", "DIARIO", "RIASSUNTO", "Musica") if x in m])
    verifica("…con il contratto, la richiesta, i file numerati, l'esito vero, il registro e "
             "quali test sono esempi di accettazione",
             "Contratto delle capacità" in m and "convertitore di distanze" in m
             and "## estensione.py" in m and "  1| " in m and "non passano tutti" in m
             and "esegui_test → FAIL test_r1_1" in m and "# QUALI TEST SONO DI CHI" in m
             and acc.FILE in m.split("# QUALI TEST SONO DI CHI")[1][:300], m[-1500:])


# ═══════════════════════════ 2. la consegna con un esempio rosso ═══════════════════════════

def prova_consegna(tmp: Path):
    sezione("2. la consegna con un esempio di accettazione rosso")
    from calliope.agenti import accettazione as acc
    from calliope.agenti.revisore import frase_esempi_tolti
    lav, ris, log, cli, sb = gira(tmp, "tolto", [[ESEGUI], [consegna()]], revisore=[
        {"verdetto": "test_sbagliato", "file": acc.FILE, "test": SBAGLIATO,
         "causa": "2 chilometri sono 2000 metri, non 3000"}])
    r = regole(lav)
    verifica("esempio rosso giudicato sbagliato: una passata del revisore, alla consegna",
             len(cli.revisioni) == 1 and r.get("agente_revisore_test_sbagliato") == 1, f"{r}")
    verifica("…tolto dagli esempi del lavoro con la regola, e la consegna va avanti: «fatto»",
             ris.get("esito") == "fatto" and r.get("agente_revisore_esempio_tolto") == 1
             and esempi_file(sb) == [ANALISI["esempi"][0]] and lav.accettazione["esempi"] == 1,
             f"{ris.get('esito')} {r} {esempi_file(sb)}")
    tolti = ris.get("esempi_tolti") or []
    verifica("…nel rapporto: l'esempio tolto con la causa, e la frase a voce",
             len(tolti) == 1 and tolti[0]["nome"] == SBAGLIATO and "2000" in tolti[0]["causa"]
             and "l'ho tolto" in frase_esempi_tolti(tolti), str(tolti))
    verifica("…il file resta in sola lettura per l'agente",
             acc.FILE in sb.sola_lettura, str(sb.sola_lettura))
    v = (lav.segnali.get("revisore") or [{}])[-1]
    verifica("…e nella riga del banco: momento, verdetto, effetto, token",
             v.get("momento") == "consegna" and v.get("verdetto") == "test_sbagliato"
             and v.get("effetto") == "esempio tolto" and v.get("modo") == "attivo"
             and lav.segnali.get("revisore_token") == 300, str(v))
    m = cli.revisioni[0]["messages"]
    verifica("la passata: solo sistema e pacchetto, con l'esempio da giudicare, senza la "
             "conversazione dell'agente",
             [x["role"] for x in m] == ["system", "user"]
             and "# IL TEST DA GIUDICARE" in m[1]["content"] and SBAGLIATO in m[1]["content"]
             and "Ho finito" not in m[1]["content"]
             and "Hai un altro giro" not in m[1]["content"], m[1]["content"][-400:])
    from calliope.estensioni.servizio import _righe_tolti
    righe = _righe_tolti({"esempi_tolti": tolti})
    verifica("la scheda di revisione mostra l'esempio tolto, con la causa",
             righe and "tolti dal revisore" in righe[0] and SBAGLIATO in righe[1]
             and "2000" in righe[1], str(righe))
    verifica("contrario: senza esempi tolti la scheda non cambia", _righe_tolti({}) == [])

    # Il codice sbagliato: l'esempio giusto resta, all'agente il fatto con file e causa
    lav, sb = estensione(tmp, "codice", codice=ROTTA)
    an_prima = (sb.root / acc.FILE).read_bytes()
    lav, ris, log, cli, sb = gira(tmp, "codice", [[ESEGUI], [consegna()],
                                                  [scrivi("estensione.py", GIUSTA)], [consegna()]],
                                  revisore=[
                                      {"verdetto": "codice_sbagliato", "file": "estensione.py",
                                       "riga": 1, "test": GIUSTO_ES,
                                       "causa": "un miglio è 1609,344 metri, non 1500"},
                                      {"verdetto": "test_sbagliato", "file": acc.FILE,
                                       "test": SBAGLIATO, "causa": "sono 2000 metri"}],
                                  lav=lav, sb=sb)
    c = risultati(lav, "consegna")
    verifica("esempio rosso giudicato giusto: resta, e il rimando all'agente ha il fatto del "
             "revisore con file:riga e causa",
             '"revisore":' in c[0] and "estensione.py:1" in c[0] and "1609,344" in c[0]
             and regole(lav).get("agente_revisore_codice_sbagliato") == 1, c[0][:600])
    verifica("…l'esempio sbagliato è stato tolto, il giusto no; dopo la correzione «fatto»",
             ris.get("esito") == "fatto" and esempi_file(sb) == [ANALISI["esempi"][0]],
             f"{ris.get('esito')} {esempi_file(sb)}")
    verifica("…e il resto del file degli esempi l'ha scritto il codice, uguale a prima",
             (sb.root / acc.FILE).read_bytes().split(b"ESEMPI = ")[0]
             == an_prima.split(b"ESEMPI = ")[0])
    # Una sola volta per giro per lo stesso esempio
    lav, ris, log, cli, sb = gira(tmp, "una-volta", [[ESEGUI], [consegna()], [consegna()],
                                                     [consegna()]], codice=ROTTA, revisore=[
        {"verdetto": "codice_sbagliato", "file": "estensione.py", "test": GIUSTO_ES},
        {"verdetto": "codice_sbagliato", "file": "estensione.py", "test": SBAGLIATO}] * 3)
    verifica("tre consegne con gli stessi esempi rossi: due passate (una per esempio), non sei",
             len(cli.revisioni) == 2, str(len(cli.revisioni)))
    verifica("…e senza un verdetto che toglie, la consegna resta rossa come prima",
             ris.get("tipo") == "consegna_rossa", str(ris)[:200])
    # «consegna» senza lo stato consegnabile: il test dell'agente rosso
    lav, ris, log, cli, sb = gira(tmp, "ignorata", [[ESEGUI], [consegna()]], test=TEST_ROSSO,
                                  max_passi=3, revisore=[
                                      {"verdetto": "consegna", "test": SBAGLIATO}])
    verifica("«consegna» con un test dell'agente rosso: ignorata, l'esempio resta, la regola",
             regole(lav).get("agente_revisore_consegna_ignorata") == 1
             and len(esempi_file(sb)) == 2
             and (lav.segnali.get("revisore") or [{}])[-1].get("effetto")
             == "ignorato: non consegnabile", f"{regole(lav)} {esempi_file(sb)}")
    lav, ris, log, cli, sb = gira(tmp, "consegnabile", [[ESEGUI], [consegna()]], revisore=[
        {"verdetto": "consegna", "test": SBAGLIATO, "causa": "il resto va"}])
    verifica("…con lo stato consegnabile (i test dell'agente verdi): l'esempio messo da parte, "
             "«fatto»", ris.get("esito") == "fatto" and len(esempi_file(sb)) == 1
             and not regole(lav).get("agente_revisore_consegna_ignorata"), f"{ris.get('esito')}")
    # Contrari: test verdi, la voce, spento
    lav, sb = estensione(tmp, "verdi")
    sb.sola_lettura.discard(acc.FILE)
    sb.scrivi(acc.FILE, acc.test_python(acc.interpreta(
        dict(ANALISI, esempi=ANALISI["esempi"][:1]), 1, True)))
    sb.sola_lettura.add(acc.FILE)
    lav, ris, log, cli, sb = gira(tmp, "verdi", [[ESEGUI], [consegna()]], lav=lav, sb=sb,
                                  revisore=[{"verdetto": "test_sbagliato"}])
    verifica("contrario: esempi e test verdi alla consegna, nessuna passata del revisore",
             ris.get("esito") == "fatto" and not cli.revisioni and not lav.segnali.get(
                 "revisore"), f"{ris.get('esito')} {len(cli.revisioni)}")
    lav, ris, log, cli, sb = gira(tmp, "voce", [[ESEGUI], [consegna()]], voce=True, revisore=[
        {"verdetto": "test_sbagliato", "file": acc.FILE, "test": SBAGLIATO}])
    verifica("contrario: con la voce che parla nessuna passata del revisore (regola "
             "agente_revisore_saltato), l'esempio resta", not cli.revisioni
             and regole(lav).get("agente_revisore_saltato", 0) >= 1 and len(esempi_file(sb)) == 2,
             f"{len(cli.revisioni)} {regole(lav)}")
    lav, ris, log, cli, sb = gira(tmp, "spento", [[ESEGUI], [consegna()]], modo="spento",
                                  revisore=[{"verdetto": "test_sbagliato"}])
    verifica("contrario: spento, come prima (nessuna passata, la consegna rossa resta rossa)",
             not cli.revisioni and ris.get("esito") != "fatto"
             and not any(k.startswith("agente_revisore") for k in regole(lav)),
             f"{len(cli.revisioni)} {ris.get('esito')}")
    lav, ris, log, cli, sb = gira(tmp, "non-json", [[ESEGUI], [consegna()]], revisore=[None])
    verifica("contrario: una risposta che non è JSON non cambia niente (agente_revisore_errore)",
             len(cli.revisioni) == 1 and regole(lav).get("agente_revisore_errore") == 1
             and len(esempi_file(sb)) == 2, f"{len(cli.revisioni)} {regole(lav)}")


# ═══════════════════════════ 3. l'ombra ═══════════════════════════

def prova_ombra(tmp: Path):
    sezione("3. l'ombra: il verdetto solo nel registro")
    from calliope.agenti import accettazione as acc
    lav, sb = estensione(tmp, "ombra")
    prima = (sb.root / acc.FILE).read_bytes()
    lav, ris, log, cli, sb = gira(tmp, "ombra", [[ESEGUI], [consegna()], [consegna()],
                                                 [consegna()]], modo="ombra", lav=lav, sb=sb,
                                  revisore=[{"verdetto": "test_sbagliato", "file": acc.FILE,
                                             "test": SBAGLIATO, "causa": "sono 2000 metri"}])
    v = lav.segnali.get("revisore") or []
    verifica("ombra: la passata c'è, il verdetto nel registro con la regola e nella riga",
             len(cli.revisioni) == 1 and regole(lav).get("agente_revisore_test_sbagliato") == 1
             and v and v[-1].get("modo") == "ombra" and v[-1].get("effetto") == "ombra",
             f"{len(cli.revisioni)} {regole(lav)} {v}")
    verifica("…il file degli esempi uguale byte per byte, nessun esempio tolto",
             (sb.root / acc.FILE).read_bytes() == prima
             and not lav.accettazione.get("tolti_revisore")
             and not regole(lav).get("agente_revisore_esempio_tolto"))
    verifica("…all'agente niente: nessun risultato né messaggio con il revisore",
             not any('"revisore":' in x for x in risultati(lav, "consegna") + risultati(
                 lav, "esegui_test")) and not any("Il revisore" in x for x in utenti(cli)))
    verifica("…e il lavoro com'era: la consegna rossa", ris.get("tipo") == "consegna_rossa"
             and "esempi_tolti" not in ris, str(ris)[:200])


# ═══════════════════════════ 4. il tetto ═══════════════════════════

def prova_tetto(tmp: Path):
    sezione("4. al tetto: l'esempio sbagliato tolto, il codice chiude con quelli rimasti")
    from calliope.agenti import accettazione as acc
    lav, ris, log, cli, sb = gira(tmp, "tetto", [[ESEGUI], [LEGGI], [LEGGI], [LEGGI]],
                                  max_passi=3, revisore=[
                                      {"verdetto": "test_sbagliato", "file": acc.FILE,
                                       "test": SBAGLIATO, "causa": "sono 2000 metri"}])
    v = (lav.segnali.get("revisore") or [{}])[-1]
    verifica("al tetto delle passate: il revisore toglie l'esempio sbagliato (momento «passate»)",
             v.get("momento") == "passate" and v.get("effetto") == "esempio tolto", str(v))
    verifica("…e il lavoro si chiude «fatto» al tetto con gli esempi rimasti verdi",
             ris.get("esito") == "fatto" and ris.get("consegna_al_tetto") == "passate"
             and regole(lav).get("agente_consegna_al_tetto") == 1, str(ris)[:300])
    lav, ris, log, cli, sb = gira(tmp, "tetto-ombra", [[ESEGUI], [LEGGI], [LEGGI], [LEGGI]],
                                  max_passi=3, modo="ombra", revisore=[
                                      {"verdetto": "test_sbagliato", "file": acc.FILE,
                                       "test": SBAGLIATO}])
    verifica("contrario: in ombra al tetto «limite», come prima",
             ris.get("eccezione") == "Limite", str(ris)[:200])


# ═══════════════════════════ 5. la tappa ═══════════════════════════

def prova_tappa(tmp: Path):
    sezione("5. la tappa con i test dell'agente rossi")
    from calliope.agenti import accettazione as acc
    from calliope.agenti.revisore import FATTI_TAPPA
    from calliope.agenti.servizio import frase_tappa
    lav, sb = estensione(tmp, "tappa", test=TEST_ROSSO)
    # un solo esempio, giusto e verde: rossi solo i test dell'agente
    sb.sola_lettura.discard(acc.FILE)
    sb.scrivi(acc.FILE, acc.test_python(acc.interpreta(
        dict(ANALISI, esempi=ANALISI["esempi"][:1]), 1, True)))
    sb.sola_lettura.add(acc.FILE)
    lav, ris, log, cli, sb = gira(tmp, "tappa", [[ESEGUI], [LEGGI], [LEGGI]], max_passi=3,
                                  tappe=True, lav=lav, sb=sb, revisore=[
                                      {"verdetto": "test_sbagliato", "file":
                                       "test_estensione.py", "riga": 9, "test": "test_metri",
                                       "causa": "3 metri sono 3 metri, il test vuole 4",
                                       "azione": "Correggi l'atteso del test.",
                                       "domanda": "Vuoi gli arrotondamenti a due cifre?"}])
    v = (lav.segnali.get("revisore") or [{}])[-1]
    verifica("alla tappa con un test dell'agente rosso: una passata, momento «tappa_rossa»",
             ris.get("esito") == "tappa" and len(cli.revisioni) == 1
             and v.get("momento") == "tappa_rossa", f"{ris.get('esito')} {v}")
    verifica("…il fatto nel rapporto della tappa, e la domanda a voce con il rapporto",
             "test_estensione.py:9" in " ".join((ris.get("revisore") or {}).get("fatti") or [])
             and "Il revisore chiede: Vuoi gli arrotondamenti" in frase_tappa(
                 SimpleNamespace(risultato=ris, segnali={}), "Distanze"),
             str(ris.get("revisore")))
    lav.risposta, lav.giro, lav.passi0 = "continua", 2, lav.passi
    lav, ris, log, cli, sb = gira(tmp, "tappa", [[LEGGI], [LEGGI], [LEGGI]], max_passi=3,
                                  tappe=True, lav=lav, sb=sb, revisore=[
                                      {"verdetto": "codice_sbagliato", "file": "estensione.py",
                                       "test": "test_metri", "causa": "x"}])
    u = utenti(cli)
    verifica("…il giro dopo si apre con il fatto del revisore (dal codice), una volta",
             sum(FATTI_TAPPA in m["content"] and "test_estensione.py:9" in m["content"]
                 for m in cli.corpi[-1] if m.get("role") == "user") == 1,
             str(u)[-500:])
    v = (lav.segnali.get("revisore") or [{}])[-1]
    verifica("dopo due tappe allo stesso punto il momento è «giri_uguali» (prima della domanda "
             "alla persona)", ris.get("esito") == "tappa" and ris.get("giri_uguali") == 2
             and v.get("momento") == "giri_uguali", f"{ris.get('giri_uguali')} {v}")
    # La consegna rossa che diventa tappa
    lav, ris, log, cli, sb = gira(tmp, "rossa", [[ESEGUI], [consegna()], [consegna()],
                                                 [consegna()]], tappe=True, test=TEST_ROSSO,
                                  revisore=[
                                      {"verdetto": "codice_sbagliato", "test": GIUSTO_ES},
                                      {"verdetto": "test_sbagliato", "file": acc.FILE,
                                       "test": SBAGLIATO, "causa": "sono 2000"},
                                      {"verdetto": "test_sbagliato",
                                       "file": "test_estensione.py", "test": "test_metri",
                                       "causa": "vuole 4"}])
    momenti = [x.get("momento") for x in lav.segnali.get("revisore") or []]
    verifica("la consegna rossa che diventa tappa: gli esempi alla consegna, poi i test "
             "dell'agente con il momento «consegna_rossa»",
             ris.get("tipo_limite") == "consegna_rossa" and momenti[-1] == "consegna_rossa"
             and momenti == ["consegna", "consegna_rossa"], f"{ris.get('tipo_limite')} {momenti}")
    verifica("contrario: l'esempio giudicato giusto alla consegna non torna al revisore alla "
             "tappa dello stesso giro (due passate, non tre)", len(cli.revisioni) == 2, f"{momenti} {len(cli.revisioni)}")


# ═══════════════════════════ 6. lo stesso errore ═══════════════════════════

def prova_stesso_errore(tmp: Path):
    sezione("6. lo stesso errore tre volte di fila nel giro")
    from calliope.agenti import accettazione as acc
    lav, sb = estensione(tmp, "stesso", test=TEST_ROSSO)
    sb.sola_lettura.discard(acc.FILE)
    sb.scrivi(acc.FILE, acc.test_python(acc.interpreta(
        dict(ANALISI, esempi=ANALISI["esempi"][:1]), 1, True)))
    sb.sola_lettura.add(acc.FILE)
    commento = "estensione.py", GIUSTA
    lav, ris, log, cli, sb = gira(tmp, "stesso", [
        [ESEGUI], [scrivi(*commento)], [ESEGUI], [scrivi(commento[0], commento[1] + "\n")],
        [ESEGUI], [LEGGI]], max_passi=6, tappe=True, lav=lav, sb=sb, revisore=[
            {"verdetto": "test_sbagliato", "file": "test_estensione.py", "test": "test_metri",
             "causa": "il test vuole 4 metri da 3"}])
    e = risultati(lav, "esegui_test")
    verifica("al terzo esegui_test con lo stesso errore: una passata, il fatto nel suo "
             "risultato (non un messaggio a parte)", len(cli.revisioni) == 1
             and '"revisore":' not in e[0] and '"revisore":' not in e[1] and '"revisore":' in e[2]
             and "vuole 4 metri" in e[2], f"{len(cli.revisioni)} {[x[max(0, x.find('revisore') - 80):x.find('revisore') + 80] for x in e]}")
    verifica("…e alla tappa dello stesso giro nessuna passata in più (una volta per giro)",
             ris.get("esito") == "tappa" and len(cli.revisioni) == 1, str(len(cli.revisioni)))
    lav, sb = estensione(tmp, "diversi", test=TEST_ROSSO)
    lav, ris, log, cli, sb = gira(tmp, "diversi", [
        [ESEGUI], [scrivi("test_estensione.py", TEST_ROSSO.replace("4)", "5)"))], [ESEGUI],
        [scrivi("test_estensione.py", TEST_ROSSO.replace("4)", "6)"))], [ESEGUI]],
        max_passi=5, lav=lav, sb=sb, revisore=[{"verdetto": "test_sbagliato"}])
    verifica("contrario: errori diversi a ogni esecuzione, nessuna passata a metà giro",
             not any('"revisore":' in x for x in risultati(lav, "esegui_test")),
             str(len(cli.revisioni)))


# ═══════════════════════════ 7. mai cambiato dall'agente ═══════════════════════════

def prova_sola_lettura(tmp: Path):
    sezione("7. l'esempio di accettazione mai cambiato dall'agente")
    from calliope.agenti import accettazione as acc
    lav, ris, log, cli, sb = gira(tmp, "sola", [
        [scrivi(acc.FILE, "import unittest\n")],
        [{"name": "modifica_file", "arguments": {"percorso": acc.FILE, "vecchio": "3000",
                                                 "nuovo": "2000"}}],
        [ESEGUI], [consegna()],
        [scrivi(acc.FILE, "import unittest\n")]], revisore=[
            {"verdetto": "test_sbagliato", "file": acc.FILE, "test": SBAGLIATO,
             "causa": "sono 2000"}])
    s, mo = risultati(lav, "scrivi_file"), risultati(lav, "modifica_file")
    verifica("scrivi_file e modifica_file sull'esempio di accettazione rifiutati (sola lettura)",
             s and "sola lettura" in s[0] and mo and "sola lettura" in mo[0], f"{s} {mo}")
    verifica("…il revisore toglie l'esempio sbagliato (lo scrive il codice), il resto resta",
             ris.get("esito") == "fatto" and esempi_file(sb) == [ANALISI["esempi"][0]]
             and acc.FILE in sb.sola_lettura, f"{ris.get('esito')} {esempi_file(sb)}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    tmp = Path(tempfile.mkdtemp(prefix="calliope-rev-"))
    try:
        prova_modulo(tmp)
        prova_consegna(tmp)
        prova_ombra(tmp)
        prova_tetto(tmp)
        prova_tappa(tmp)
        prova_stesso_errore(tmp)
        prova_sola_lettura(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
