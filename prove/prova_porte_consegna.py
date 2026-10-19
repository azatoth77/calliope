"""Le porte oneste della consegna dell'agente, a secco (19/10/2026, issue #180; area
agenti-estensioni; analisi docs/ricerche/2026-10-19-solidita-harness-sviluppo.md § 3.1).

Nel ciclo dell'agente c'erano porte che si aprivano da sole: un modello piccolo superava il
controllo della consegna senza aver fatto il lavoro. Qui, con l'agente finto e la sandbox col
docker finto:

1. un esito fuori dall'enum («completato») è un errore con l'elenco dei valori (regola
   agente_esito_non_valido) e non chiude il lavoro, anche vuoto; la regola anche per gli
   strumenti grafo_* della ricerca; contrari: «Fatto» con la maiuscola vale, i tool della voce
   decidono loro, «mancano_dati» e «impossibile» invariati;
2. una passata senza chiamate non è mai una consegna (agente_prosa_non_consegna): con lo stato
   consegnabile prima il fatto, poi la consegna decisa dal codice con gli esempi rifatti
   (consegna_al_tetto «prosa»), senza esempi con i test rifatti verdi (contrario: il controllo
   della consegna che non va); dopo PROSA_MAX di fila «limite» o, in uno sviluppo, la tappa;
3. la consegna rossa (i test dopo l'ultimo rimando, il controllo dopo l'ultimo rifiuto) non è
   «fatto» (agente_consegna_rossa_tappa): «limite» fuori da uno sviluppo, tappa dentro; i
   contatori ripartono a ogni giro dopo una tappa (anche dopo «consegna_rossa») e restano
   dopo una domanda; contrario: la consegna verde invariata;
4. la riproduzione vale solo con un fallimento di comportamento (agente_riproduzione_asserzione):
   l'ImportError o «non è una funzione» nati nel test no, l'asserzione, l'errore mentre gira e
   un nome che manca nel codice di prima (il ReferenceError di logica.js) sì;
5. esegui_test rosso con il controllo della consegna (un file della scheda che manca, il nome
   preso); contrari: senza il predicato il solo manifesto, con tutto a posto niente;
6. la correzione di un gioco: accettazione.test.js torna dai file della versione e resta in sola
   lettura; contrari: una modifica, un'estensione che non è un gioco.

    python prove\\prova_porte_consegna.py
"""

import json
import os
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
    """L'agente finto: ogni passata è una lista di chiamate, oppure un testo (una passata di
    sola prosa, senza chiamate)."""

    def __init__(self, passate):
        self.passate, self.corpi, self.url = list(passate), [], None

    def chat(self, body, su_pezzo=None, controlla=None, su_flusso=None):
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
LEGGI = {"name": "leggi_file", "arguments": {"percorso": "programma.py"}}
GIUSTO = "def somma(a, b):\n    return a + b\n"
SBAGLIATO = "def somma(a, b):\n    return a - b\n"
TEST = ("import unittest\nfrom programma import somma\n\n\nclass P(unittest.TestCase):\n"
        "    def test_somma(self):\n        self.assertEqual(somma(2, 3), 5)\n")
SCRIVE_GIUSTO = [scrivi("programma.py", GIUSTO), scrivi("test_programma.py", TEST)]
SCRIVE_SBAGLIATO = [scrivi("programma.py", SBAGLIATO), scrivi("test_programma.py", TEST)]
SCUSE = "Hai ragione, correggo il test."
# Le regole di questa issue, nel registro dei lavori
NUOVE = ("agente_esito_non_valido", "agente_prosa_non_consegna", "agente_consegna_rossa_tappa",
         "agente_riproduzione_asserzione")


def gira(tmp, nome, passate, max_passi=12, tappe=False, controlla=None, lav=None, sb=None):
    """Agente.codice con il copione; (lavoro, risultato o {"eccezione", "tipo", "motivo"},
    log, copione)."""
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
        ris = ag.codice(lav, sb, controlla=controlla)
    except Exception as e:  # noqa: BLE001 — Limite
        ris = {"eccezione": type(e).__name__, "tipo": getattr(e, "tipo", ""), "motivo": str(e),
               "parziale": getattr(e, "parziale", {})}
    return lav, ris, log, cli, sb


def regole(lav) -> dict:
    return (lav.segnali or {}).get("regole") or {}


def risultati(lav, nome) -> list[str]:
    return [m["content"] for m in (lav.contesto.get("messages") or [])
            if m.get("role") == "tool" and m.get("tool_name") == nome]


def utenti(cli) -> list[str]:
    return [m["content"] for m in (cli.corpi[-1] if cli.corpi else [])
            if m.get("role") == "user"]


# ═══════════════════════════ 1. l'esito fuori dall'enum ═══════════════════════════

def prova_enum(tmp: Path):
    sezione("1. consegna(esito=«completato») è un errore con l'elenco")
    from calliope.agenti.ciclo import STRUMENTI_CODICE
    from calliope.tools import dialogo
    args, err = dialogo.controlla_strumento("consegna", STRUMENTI_CODICE,
                                            {"riassunto": "Fatto.", "esito": "completato"})
    verifica("controlla_strumento: «completato» non passa, con l'elenco dei valori",
             err is not None and "completato" in err["errore"]
             and "fatto, mancano_dati, impossibile" in err["errore"]
             and err["argomenti"]["esito"]["valori_ammessi"] == ["fatto", "mancano_dati",
                                                                 "impossibile"], str(err))
    args, err = dialogo.controlla_strumento("consegna", STRUMENTI_CODICE,
                                            {"riassunto": "Fatto.", "esito": "Fatto"})
    verifica("contrario: «Fatto» con la maiuscola è una conversione di forma, vale",
             err is None and args["esito"] == "fatto", str(err))
    _, err = dialogo.controlla_strumento("consegna", STRUMENTI_CODICE,
                                         {"riassunto": "Fatto.", "esito": ""})
    verifica("esito vuoto: un errore con l'elenco (prima valeva «fatto»)",
             err is not None and "fatto, mancano_dati, impossibile" in err["errore"], str(err))
    from calliope.agenti.ciclo import nota_valore_non_ammesso
    from calliope.archivio.esplora import STRUMENTI as GRAFO
    vicini = next(t["function"]["name"] for t in GRAFO if "verso" in json.dumps(
        t["function"]["parameters"]))
    lav_r = SimpleNamespace(id="R1", segnali={})
    a, err = dialogo.controlla_strumento(vicini, GRAFO, {"nodo": 3, "verso": "sopra"})
    verifica(f"ricerca: {vicini}(verso=«sopra») è un errore con l'elenco, e la regola nel "
             "registro (revisione della PR #183)", err is not None and "uscenti" in err["errore"]
             and nota_valore_non_ammesso(lav_r, vicini, err, a)
             and regole(lav_r).get("agente_esito_non_valido") == 1, str(err))
    _, err = dialogo.controlla_strumento(vicini, GRAFO, {})
    verifica("contrario: un obbligatorio che manca non è la regola dell'enum",
             err is not None and not nota_valore_non_ammesso(SimpleNamespace(segnali={}),
                                                              vicini, err, {}), str(err))
    params = {"type": "object", "properties": {"azione": {"type": "string",
                                                          "enum": ["avvia", "ferma"]}}}
    _, _, err = dialogo.controlla("timer", params, {"azione": "stop"})
    verifica("contrario: per i tool della voce un valore fuori dall'enum lo decide il tool",
             err is None, str(err))

    lav, ris, log, cli, _ = gira(tmp, "enum", [SCRIVE_GIUSTO, [ESEGUI],
                                               [consegna("completato")], [consegna()]])
    r = risultati(lav, "consegna")
    verifica("nel ciclo: la consegna «completato» torna all'agente con l'elenco, e la regola",
             r and "fatto, mancano_dati, impossibile" in r[0]
             and regole(lav).get("agente_esito_non_valido") == 1, f"{r[:1]} {regole(lav)}")
    verifica("…e il lavoro si chiude solo con la consegna vera dopo, «fatto» con i test verdi",
             ris.get("esito") == "fatto" and ris.get("test_passano") is True
             and len(cli.corpi) == 4, str(ris)[:300])
    lav, ris, *_ = gira(tmp, "enum-rossa", [SCRIVE_SBAGLIATO, [consegna("completato")]] +
                        [[consegna("completato")]] * 3, max_passi=6)
    verifica("…«completato» con i test rossi non diventa mai «fatto» (prima saltava i test)",
             ris.get("esito") != "fatto" and "eccezione" in ris, str(ris)[:300])
    lav, ris, *_ = gira(tmp, "mancano", [SCRIVE_SBAGLIATO,
                                         [consegna("mancano_dati", domanda="In che unità?")]])
    verifica("contrario: «mancano_dati» invariato, con i test rossi", ris.get("esito") ==
             "mancano_dati" and ris.get("domanda") == "In che unità?", str(ris)[:200])
    lav, ris, *_ = gira(tmp, "impossibile", [SCRIVE_SBAGLIATO, [consegna("impossibile")]])
    verifica("contrario: «impossibile» invariato, senza rifare i controlli",
             ris.get("esito") == "impossibile" and not regole(lav), f"{ris} {regole(lav)}")


# ═══════════════════════════ 2. la prosa non è una consegna ═══════════════════════════

def _estensione_con_esempi(tmp, nome):
    """Una sandbox d'estensione con gli esempi di accettazione in sola lettura (come
    prova_fasi_agente_2._gira_tetto)."""
    import prova_fasi_agente_2 as F2
    from calliope.agenti import accettazione as acc
    from calliope.agenti.ciclo import Lavoro
    from calliope.agenti.scheletri import prepara_estensione
    sb = G.sandbox(tmp, nome)
    prepara_estensione(sb)
    sb.scrivi("manifesto.json", json.dumps(F2.MANIFESTO))
    lav = Lavoro(nome, "estensione", "Un convertitore di distanze")
    an = acc.interpreta(F2.ANALISI, 3, True)
    sb.scrivi(acc.FILE, acc.test_python(an))
    sb.sola_lettura |= {acc.FILE}
    lav.accettazione = {"stato": "pronta", "file": True, "nome_file": acc.FILE,
                        "esempi": len(an["esempi"])}
    return lav, sb, F2


def prova_prosa(tmp: Path):
    sezione("2. una passata senza chiamate non è mai una consegna")
    from calliope.agenti.ciclo import PROSA_FATTUALE, PROSA_MAX, SPINTA_STRUMENTI
    from calliope.estensioni.prompt import controlla_consegna
    # Il caso della issue: le scuse dopo una spinta, con i test rossi
    lav, ris, log, cli, _ = gira(tmp, "scuse", [SCRIVE_SBAGLIATO] + [SCUSE] * (PROSA_MAX + 1))
    verifica("le scuse («Hai ragione, correggo il test») con i test rossi non chiudono il "
             "lavoro: «limite» col motivo dopo PROSA_MAX di fila; la regola conta solo le "
             "passate che prima erano una consegna (dopo la prima spinta)",
             ris.get("eccezione") == "Limite" and ris.get("tipo") == "prosa"
             and "senza usare gli strumenti" in ris.get("motivo", "")
             and regole(lav).get("agente_prosa_non_consegna") == PROSA_MAX, f"{ris}")
    verifica("…con la spinta di sempre, mai il fatto dello stato consegnabile",
             SPINTA_STRUMENTI in utenti(cli) and PROSA_FATTUALE not in utenti(cli),
             str(utenti(cli))[-300:])
    lav, ris, log, cli, _ = gira(tmp, "scuse-tappa", [SCRIVE_SBAGLIATO] + [SCUSE] * 6,
                                 tappe=True)
    verifica("…in uno sviluppo è una tappa, col motivo",
             ris.get("esito") == "tappa" and ris.get("tipo_limite") == "prosa", str(ris)[:300])
    from calliope.agenti.servizio import frase_tappa
    f = frase_tappa(SimpleNamespace(risultato=ris, segnali={}), "Somma")
    verifica("…e a voce la tappa dice perché", "senza usare gli strumenti" in f, f)
    # Lo stato consegnabile, un programma senza esempi: il fatto, poi la consegna con i
    # controlli di una consegna «fatto» (revisione della PR #183)
    lav, ris, log, cli, _ = gira(tmp, "verde", [SCRIVE_GIUSTO, [ESEGUI]] + ["Ho finito."] * 5)
    verifica("test verdi e un testo: la prima volta il fatto «nessuno strumento chiamato»",
             PROSA_FATTUALE in utenti(cli), str(utenti(cli))[-300:])
    verifica("…senza esempi né riproduzione, alla seconda consegna il codice con i test rifatti "
             "verdi (consegna_al_tetto_con «test»)", ris.get("esito") == "fatto"
             and ris.get("consegna_al_tetto") == "prosa"
             and ris.get("consegna_al_tetto_con") == "test" and len(cli.corpi) == 4
             and "passano i suoi test" in ris.get("riassunto", ""), str(ris)[:300])
    from calliope.agenti.servizio import AL_TETTO_TEST
    verifica("…e la frase a voce non parla di esempi", "esempi" not in AL_TETTO_TEST)
    lav, ris, *_ = gira(tmp, "verde-controllo", [SCRIVE_GIUSTO, [ESEGUI]] + ["Ho finito."] * 5,
                        controlla=lambda x: "manca il programma dichiarato")
    verifica("contrario: il controllo della consegna che non va, niente consegna d'ufficio: "
             "«limite»", ris.get("eccezione") == "Limite" and ris.get("tipo") == "prosa",
             str(ris)[:300])
    # Con gli esempi di accettazione verdi: consegna il codice, alla seconda
    lav, sb, F2 = _estensione_con_esempi(tmp, "verde-esempi")
    lav, ris, log, cli, _ = gira(tmp, "verde-esempi", [[scrivi("estensione.py", F2.GIUSTA)],
                                                       [ESEGUI], "Ho finito.", "Ho finito."],
                                 lav=lav, sb=sb, controlla=lambda x: controlla_consegna(x))
    verifica("con gli esempi verdi: alla seconda prosa consegna il codice, con i controlli "
             "rifatti", ris.get("esito") == "fatto" and ris.get("consegna_al_tetto") == "prosa"
             and regole(lav).get("agente_consegna_al_tetto") == 1 and len(cli.corpi) == 4,
             f"{ris} {regole(lav)}")
    verifica("…il riassunto lo dice il codice", "ha smesso di usare gli strumenti senza "
             "consegnare" in ris.get("riassunto", ""), ris.get("riassunto"))
    lav, sb, F2 = _estensione_con_esempi(tmp, "rosso-esempi")
    lav, ris, *_ = gira(tmp, "rosso-esempi", [[scrivi("estensione.py", F2.SBAGLIATA)], [ESEGUI]]
                        + ["Ho finito."] * 5, lav=lav, sb=sb,
                        controlla=lambda x: controlla_consegna(x))
    verifica("contrario: esempi rossi, il codice non consegna", ris.get("esito") != "fatto",
             str(ris)[:300])
    lav, ris, *_ = gira(tmp, "vera", [SCRIVE_GIUSTO, [ESEGUI], [consegna()]])
    verifica("contrario: la consegna vera con i test verdi resta «fatto», senza regole nuove",
             ris.get("esito") == "fatto" and ris.get("test_passano") is True
             and not set(regole(lav)) & set(NUOVE), f"{ris} {regole(lav)}")


# ═══════════════════════════ 3. la consegna rossa ═══════════════════════════

def prova_rossa(tmp: Path):
    sezione("3. la consegna rossa non è «fatto»")
    from calliope.agenti.ciclo import RIMANDI_MAX
    lav, ris, log, cli, _ = gira(tmp, "rossa", [SCRIVE_SBAGLIATO] + [[consegna()]] * 4)
    verifica(f"dopo {RIMANDI_MAX} rimandi la consegna con i test rossi è «limite» (prima «fatto»)",
             ris.get("eccezione") == "Limite" and ris.get("tipo") == "consegna_rossa"
             and "test che non passano" in ris.get("motivo", "")
             and regole(lav).get("agente_consegna_rossa_tappa") == 1
             and len(cli.corpi) == RIMANDI_MAX + 2, f"{ris} {regole(lav)}")
    verifica("…con l'errore dei test nel risultato",
             "5" in str((ris.get("parziale") or {}).get("errore_consegna")), str(ris)[:400])
    lav, ris, *_ = gira(tmp, "rossa-tappa", [SCRIVE_SBAGLIATO] + [[consegna()]] * 4, tappe=True)
    verifica("…in uno sviluppo è una tappa con il motivo, e i test rossi",
             ris.get("esito") == "tappa" and ris.get("tipo_limite") == "consegna_rossa"
             and ris.get("test_passano") is False, str(ris)[:300])
    from calliope.agenti.servizio import frase_tappa
    f = frase_tappa(SimpleNamespace(risultato=ris, segnali={}), "Somma")
    verifica("…e la frase della tappa dice che la consegna non va",
             "la consegna non va" in f, f)
    lav, ris, *_ = gira(tmp, "senza-tempo", [SCRIVE_SBAGLIATO, [consegna()]], max_passi=3)
    verifica("…anche senza più passate per un rimando (prima passava senza rifare i test)",
             ris.get("tipo") == "consegna_rossa", str(ris)[:300])

    def no(sb):
        return "mancano i file della scheda: stile.css"
    lav, ris, log, cli, _ = gira(tmp, "rifiuti", [SCRIVE_GIUSTO] + [[consegna()]] * 5,
                                 controlla=no)
    verifica("il controllo della consegna ancora in errore dopo 3 rifiuti: «limite», non "
             "«fatto» con i test verdi (prima l'errore era ignorato)",
             ris.get("tipo") == "consegna_rossa" and len(cli.corpi) == 5
             and "controllo della consegna" in ris.get("motivo", ""), str(ris)[:300])
    # I contatori dopo una tappa: due rifiuti nel primo giro, uno solo resta nel secondo
    lav, ris, log, cli, sb = gira(tmp, "giri", [SCRIVE_GIUSTO, [consegna()], [consegna()],
                                                [LEGGI]], max_passi=4, tappe=True,
                                  controlla=no)
    verifica("contatori: alla tappa del tetto il contesto ha rifiuti_consegna = 2",
             ris.get("esito") == "tappa" and lav.contesto.get("rifiuti_consegna") == 2,
             f"{ris.get('esito')} {lav.contesto.get('rifiuti_consegna')}")
    lav.risposta = "continua"
    lav.passi0 = lav.passi
    lav, ris, log, cli, _ = gira(tmp, "giri", [[consegna()]] * 4 + [[LEGGI]] * 3,
                                 max_passi=20, lav=lav, sb=sb, controlla=no)
    verifica("…nel giro dopo i rifiuti ripartono: tre rifiuti nuovi, poi la tappa rossa "
             "(revisione della PR #183)", ris.get("esito") == "tappa"
             and ris.get("tipo_limite") == "consegna_rossa" and len(cli.corpi) == 4
             and lav.contesto.get("rifiuti_consegna") == 3,
             f"{ris.get('tipo_limite')} {len(cli.corpi)} {lav.contesto.get('rifiuti_consegna')}")
    lav, ris, log, cli, sb = gira(tmp, "giri-rossi", [SCRIVE_SBAGLIATO] + [[consegna()]] * 3,
                                  tappe=True)
    verifica("tappa «consegna_rossa» dopo i due rimandi", ris.get("tipo_limite") ==
             "consegna_rossa" and lav.contesto.get("rimandi") == RIMANDI_MAX, str(ris)[:200])
    lav.risposta = "continua"
    lav.passi0 = lav.passi
    lav, ris, log, cli, _ = gira(tmp, "giri-rossi", [[consegna()], [scrivi("programma.py",
                                                                         GIUSTO)], [consegna()]],
                                 lav=lav, sb=sb)
    r = risultati(lav, "consegna")
    verifica("…«continua»: il primo test rosso del giro nuovo ha di nuovo i suoi rimandi, "
             "l'agente corregge e consegna", ris.get("esito") == "fatto"
             and "correggi" in r[-2] and "si ferma qui" not in r[-2], f"{ris} {r[-2:]}")
    lav, ris, log, cli, sb = gira(tmp, "domanda", [SCRIVE_SBAGLIATO, [consegna()],
                                                   [consegna("mancano_dati",
                                                             domanda="In che unità?")]])
    verifica("ripresa dopo una domanda: il rimando resta nel contesto",
             ris.get("esito") == "mancano_dati" and lav.contesto.get("rimandi") == 1,
             f"{ris.get('esito')} {lav.contesto.get('rimandi')}")
    lav.risposta = "in metri"
    lav, ris, log, cli, _ = gira(tmp, "domanda", [[consegna()], [consegna()]], lav=lav, sb=sb)
    verifica("…e dopo la risposta resta un rimando solo, poi la consegna rossa",
             ris.get("tipo") == "consegna_rossa" and len(cli.corpi) == 2, str(ris)[:300])
    lav, ris, *_ = gira(tmp, "verde-dopo", [SCRIVE_SBAGLIATO, [consegna()],
                                            [scrivi("programma.py", GIUSTO)], [consegna()]])
    verifica("contrario: corretto dopo un rimando, la consegna verde è «fatto»",
             ris.get("esito") == "fatto" and ris.get("test_passano") is True
             and not regole(lav).get("agente_consegna_rossa_tappa"), str(ris)[:300])


# ═══════════════════════════ 4. la riproduzione ═══════════════════════════

def _riproduci(tmp, nome, prima, ora):
    from calliope.agenti.riproduzione import controlla
    sb = G.sandbox(tmp, nome)
    for k, v in ora.items():
        sb.scrivi(k, v)
    lav = SimpleNamespace(id=nome, file_iniziali=dict(prima), segnali={})
    return controlla(lav, sb, lambda *a: None), lav


def prova_riproduzione(tmp: Path):
    sezione("4. la riproduzione vale solo con un fallimento di comportamento")
    from calliope.agenti.riproduzione import NON_RIPRODOTTO, messaggio_agente, strutturale
    prima = {"calcola.py": "def somma(a, b):\n    return a - b\n"}
    nuova = {"calcola.py": "def somma(a, b):\n    return a + b\n\n\ndef doppio(a):\n"
                           "    return 2 * a\n"}
    es, lav = _riproduci(tmp, "import", prima, {**nuova, "test_calcola.py": (
        "from calcola import doppio\n\n\ndef test_doppio():\n    assert doppio(2) == 4\n")})
    verifica("il test importa una funzione che prima non c'era: «struttura», non riprodotto",
             es["stato"] == "struttura" and es["stato"] in NON_RIPRODOTTO
             and "ImportError" in es.get("perche", "")
             and regole(lav).get("agente_riproduzione_asserzione") == 1, str(es)[:300])
    m = messaggio_agente(es, "la somma è sbagliata")
    verifica("…il rimando all'agente dice perché", "non per un'asserzione" in m
             and "ImportError" in m, m)
    es, lav = _riproduci(tmp, "assert", prima, {**nuova, "test_calcola.py": (
        "from calcola import somma\n\n\ndef test_somma():\n    assert somma(2, 3) == 5\n")})
    verifica("contrario: un'asserzione sul codice di prima: riprodotto",
             es["stato"] == "riprodotto" and not regole(lav), str(es)[:300])
    es, _ = _riproduci(tmp, "misto", prima, {**nuova, "test_calcola.py": (
        "from calcola import somma\nimport calcola\n\n\ndef test_somma():\n"
        "    assert somma(2, 3) == 5\n\n\ndef test_doppio():\n    assert calcola.doppio(2) == 4\n")})
    verifica("contrario: un'asserzione e un nome mancante insieme: riprodotto",
             es["stato"] == "riprodotto", str(es)[:300])
    es, _ = _riproduci(tmp, "crash", {"calcola.py": "def media(v):\n    return sum(v) / len(v)\n"},
                       {"calcola.py": "def media(v):\n    return sum(v) / len(v) if v else 0\n",
                        "test_calcola.py": "from calcola import media\n\n\ndef test_vuota():\n"
                                           "    assert media([]) == 0\n"})
    verifica("contrario: un errore del codice di prima mentre gira (ZeroDivisionError): "
             "riprodotto", es["stato"] == "riprodotto", str(es)[:300])
    verifica("strutturale(): un nome o una firma che mancano nati nel codice di prima no "
             "(revisione della PR #183); nel test sì",
             not any(strutturale(f) for f in (
                 {"test": "r", "errore": "ReferenceError: punteggio is not defined",
                  "dove": "logica.js:12"},
                 {"test": "m", "errore": "TypeError: stato.giocatori.map is not a function",
                  "dove": "logica.js:40"},
                 {"test": "t", "errore": "UnboundLocalError: cannot access local variable 'tot'",
                  "dove": "media.py:7"},
                 {"test": "t", "errore": "NameError: name 'totale' is not defined",
                  "dove": "conti.py:9 ← test_conti.py:5"},
                 {"test": "t", "errore": "AttributeError: 'str' object has no attribute "
                                         "'append'", "dove": "conti.py:9"}))
             and all(strutturale(f) for f in (
                 {"test": "t", "errore": "NameError: name 'doppio' is not defined",
                  "dove": "test_conti.py:5"},
                 {"test": "n", "errore": "TypeError: l.g is not a function",
                  "dove": "logica.test.js:2"},
                 {"test": "t", "errore": "ImportError: cannot import name 'doppio'",
                  "dove": "conti.py:1"})))
    verifica("strutturale(): import, sintassi, NameError, AttributeError e argomenti sì; "
             "asserzione, NoneType e divisione no",
             all(strutturale(f) for f in (
                 {"test": "import di test_x.py", "errore": "ImportError: x"},
                 {"test": "t", "errore": "NameError: name 'doppio' is not defined"},
                 {"test": "t", "errore": "AttributeError: module 'calcola' has no attribute 'x'"},
                 {"test": "t", "errore": "TypeError: somma() got an unexpected keyword argument "
                                         "'c'"},
                 {"test": "n", "errore": "TypeError: l.g is not a function [in l.test.js:2]"},
                 {"test": "n", "errore": "ReferenceError: nuova is not defined"},
                 {"test": "sintassi", "errore": "logica.js: Unexpected token"}))
             and not any(strutturale(f) for f in (
                 {"test": "t", "errore": "AssertionError: 0 != 2"},
                 {"test": "t", "errore": "AttributeError: 'NoneType' object has no attribute 'x'"},
                 {"test": "t", "errore": "ZeroDivisionError: division by zero"},
                 {"test": "t", "errore": "UnboundLocalError: cannot access local variable 'x'"},
                 {"test": "a", "errore": "Expected values to be strictly equal: 1 !== 2"},
                 {"test": "r", "errore": "TypeError: Cannot read properties of undefined"},
                 {"test": "g", "errore": "nessun elemento da toccare con «Ricomincia»"})))
    if not shutil.which("node"):
        print("SALTATA IN PARTE: JavaScript, node non c'è")
        return
    js = "function f() { return 1; }\nif (typeof module !== \"undefined\") module.exports = { f };\n"
    js2 = js.replace("module.exports = { f }", "module.exports = { f, g: () => 2 }")
    testa = ('const { test } = require("node:test");\nconst assert = require("node:assert");\n'
             'const l = require("./logica.js");\n')
    es, _ = _riproduci(tmp, "js-nome", {"logica.js": js}, {"logica.js": js2, "logica.test.js":
                       testa + 'test("g", () => { assert.strictEqual(l.g(), 2); });\n'})
    verifica("JavaScript: «l.g is not a function» sulla versione di prima: «struttura»",
             es["stato"] == "struttura" and "is not a function" in es.get("perche", ""),
             str(es)[:300])
    es, _ = _riproduci(tmp, "js-assert", {"logica.js": js},
                       {"logica.js": js.replace("return 1", "return 2"), "logica.test.js":
                        testa + 'test("f", () => { assert.strictEqual(l.f(), 2); });\n'})
    verifica("contrario: JavaScript con un'asserzione: riprodotto", es["stato"] == "riprodotto",
             str(es)[:300])
    rotto = ("function ricomincia() {\n  return punteggio;\n}\n"
             "if (typeof module !== \"undefined\") module.exports = { ricomincia };\n")
    giusto = rotto.replace("  return punteggio;", "  const punteggio = 0;\n  return punteggio;")
    es, _ = _riproduci(tmp, "js-ref", {"logica.js": rotto}, {"logica.js": giusto,
                       "logica.test.js": testa.replace("const l =", "const l =")
                       + 'test("ricomincia", () => { assert.strictEqual(l.ricomincia(), 0); });\n'})
    verifica("contrario: il ReferenceError nato in logica.js (il difetto segnalato): riprodotto",
             es["stato"] == "riprodotto", str(es)[:300])


# ═══════════════════════════ 5. esegui_test consegnabile ═══════════════════════════

def _tris(tmp, nome, **scheda):
    cart = RADICE / "prove" / "giochi" / "tris"
    m = json.loads((cart / "manifesto.json").read_text(encoding="utf-8"))
    m["scheda"].update(scheda)
    sb = G.sandbox(tmp, nome)
    sb.scrivi("manifesto.json", json.dumps(m, ensure_ascii=False))
    for f in ("logica.js", "logica.test.js"):
        sb.scrivi(f, (cart / f).read_text(encoding="utf-8"))
    return sb, m


def prova_esegui_test(tmp: Path):
    sezione("5. «tutto verde» in esegui_test vuol dire consegnabile")
    from calliope.agenti.ciclo import Lavoro, _con_manifesto
    from calliope.agenti.servizio import Lavori
    from calliope.estensioni.prompt import controlla_consegna
    base = {"esito": {"eseguiti": 3, "falliti": 0, "errori": 0, "saltati": 0},
            "passano": True, "uscita": "ok a\nok b\nok prova di fumo del gioco\n"}
    sb, m = _tris(tmp, "stile", stile="stile.css")
    r = _con_manifesto(dict(base), sb, lambda x: controlla_consegna(x))
    verifica("un file della scheda che manca (stile.css): esegui_test rosso, in testa",
             r["passano"] is False and r["esito"]["falliti"] == 1
             and r["uscita"].startswith("FALLITO controllo della consegna: mancano i file della "
                                        "scheda: stile.css"), r["uscita"][:200])
    verifica("contrario: senza il predicato il solo manifesto, come prima (verde)",
             _con_manifesto(dict(base), sb) == base)
    sb2, m2 = _tris(tmp, "tutto")
    verifica("contrario: con tutto a posto niente cambia",
             _con_manifesto(dict(base), sb2, lambda x: controlla_consegna(x)) == base)
    svc = SimpleNamespace(sviluppi=None, log=lambda *a: None)
    controlla = Lavori._controlla_estensione(svc, SimpleNamespace(id="L1"), (m2["nome"],), None)
    verifica("il controllo dei lavori ha il predicato senza effetti, con i nomi: il nome preso",
             "è già di un'altra estensione" in str(controlla.consegnabile(sb2)),
             str(controlla.consegnabile(sb2)))
    if not shutil.which("node"):
        print("SALTATA IN PARTE: esegui_test vero, node non c'è")
        return
    ag = G.agente()
    lav = Lavoro("G1", "estensione", "il tris")
    lav.gioco = True
    res = ag._strumento(lav, sb, "esegui_test", {}, lambda x: controlla_consegna(x))
    verifica("esegui_test vero: rosso con la scheda, e il motivo nei fallimenti in breve",
             res["passano"] is False and "stile.css" in str(res.get("fallimenti")),
             str(res)[:400])
    from calliope.agenti.ciclo import nomi_test
    verifica("…il controllo non conta come un test dell'agente (test tolti)",
             not any(n.startswith("controllo") for n in nomi_test(res["uscita"])))
    res = ag._strumento(lav, sb, "esegui_test", {})
    verifica("contrario: senza il predicato la prova di fumo non guarda lo stile, verde",
             res["passano"] is True, str(res)[:300])


# ═══════════════════════════ 6. la correzione di un gioco ═══════════════════════════

def prova_correzione_gioco(tmp: Path):
    sezione("6. nella correzione di un gioco accettazione.test.js resta in sola lettura")
    from calliope.agenti import accettazione as acc
    from calliope.agenti.ciclo import Lavoro
    from calliope.agenti.sandbox import ErroreSandbox
    from calliope.agenti.servizio import Lavori
    from calliope.config import Config
    from calliope.estensioni.archivio import ESTENSIONI_FILE
    from calliope.estensioni.servizio import _solo_usati
    file = {"manifesto.json": b"{}", "logica.js": b"x", "logica.test.js": b"x",
            acc.FILE_GIOCO: b"x"}
    verifica("la premessa: la versione di un gioco tiene accettazione.test.js "
             "(candidata_da_lavoro, poi file_per_modifica la ridà)",
             acc.FILE_GIOCO.endswith(ESTENSIONI_FILE) and acc.FILE_GIOCO in _solo_usati(file))
    cfg = Config()
    cfg.agenti_accettazione = True
    svc = SimpleNamespace(cfg=cfg, sviluppi=None, log=lambda *a: None)

    def lavoro(correzione=True, gioco=True):
        lav = Lavoro("C1", "estensione", "il tris", "ada-id", "Ada")
        lav.gioco, lav.correzione = gioco, correzione
        lav.file_iniziali = {"logica.js": "x", acc.FILE_GIOCO: "// esempi\n"}
        return lav

    def prepara(nome, lav):
        sb = G.sandbox(tmp, nome)
        for k, v in lav.file_iniziali.items():
            sb.scrivi(k, v)
        out = Lavori._analisi_prima_(svc, lav, sb, lav.gioco)
        return sb, out
    sb, out = prepara("corr", lavoro())
    verifica("correzione: accettazione.test.js in sola lettura, l'analisi saltata come prima",
             acc.FILE_GIOCO in sb.sola_lettura and out is None
             and lavoro().accettazione is not None, str(sb.sola_lettura))
    try:
        sb.scrivi(acc.FILE_GIOCO, "// cambiati\n")
        scritto = True
    except ErroreSandbox:
        scritto = False
    verifica("…e l'agente non lo riscrive", not scritto)
    sb, _ = prepara("modifica", lavoro(correzione=False))
    verifica("contrario: una modifica (le regole possono cambiare) lo lascia scrivibile",
             acc.FILE_GIOCO not in sb.sola_lettura, str(sb.sola_lettura))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="calliope-porte-"))
    os.environ.setdefault("CALLIOPE_CONFIG_LOCALE", str(tmp / "nessuno.yaml"))
    try:
        prova_enum(tmp / "enum")
        prova_prosa(tmp / "prosa")
        prova_rossa(tmp / "rossa")
        prova_riproduzione(tmp / "riproduzione")
        prova_esegui_test(tmp / "esegui")
        prova_correzione_gioco(tmp / "gioco")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
