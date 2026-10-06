"""Contratto delle capacità, piano di fattibilità, permessi chiesti e guardia contro il
ragionamento a vuoto (05/10/2026), a secco con un agente finto.

Richiesta di Dario dopo il lavoro L1 del 04/10 (66 000 token di ragionamento senza un file):
«un agente che sviluppa un'estensione deve sapere già cosa non può fare e fermarsi prima,
oppure sapere che per certe cose deve chiedere a Calliope».

- contratto (calliope/estensioni/contratto.py): generato dal codice; ogni azione della porta
  ha lo scope che il guardrail vuole davvero (senza lo scope: vietata; con: no), le azioni
  sono quelle del guardrail, le impossibili ci sono tutte, nella cartella in sola lettura;
- piano: primo passo obbligatorio (scrivi_file prima del piano non scrive), voci sconosciute e
  scope che non copre le capacità tornano all'agente, il piano diventa la bozza del manifesto;
- impossibile (una capacità impossibile, o fattibile=false): il lavoro si chiude alla prima
  passata, con il motivo e l'alternativa;
- chiedi_permesso: il lavoro si sospende con la domanda alla persona (anche dal servizio dei
  lavori, con l'annuncio); alla ripresa la risposta è registrata; un permesso sensibile
  (flussi, POST, comandi della casa) nel manifesto senza chiedi_permesso fa rifiutare la
  consegna; la scheda di revisione dice cosa è stato chiesto e la risposta;
- ragionamento a vuoto: oltre la soglia di token senza strumenti una spinta, alla seconda la
  chiusura con il motivo; dopo una chiamata di strumento il conto riparte.
"""

import json
import os
import queue
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calliope import guardrail as gr  # noqa: E402
from calliope.agenti.arbitro import Arbitro  # noqa: E402
from calliope.agenti.ciclo import Agente, Lavoro, Limite  # noqa: E402
from calliope.agenti.sandbox import Isolamento, Sandbox  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.estensioni import contratto as ct  # noqa: E402
from calliope.estensioni.manifesto import normalizza_permessi  # noqa: E402
from calliope.estensioni.prompt import controlla_consegna, sistema_estensione  # noqa: E402
from calliope.estensioni.servizio import runtime_testo  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass
TMP = Path(tempfile.mkdtemp(prefix="calliope-piano-"))
errori = 0
T0 = time.perf_counter()


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


CONV = '''
def esegui(dati, calliope):
    v = float(dati.get("valore", 0))
    return {"da_dire": f"{v * 0.621371:.2f} miglia.", "valore": round(v * 0.621371, 2)}
'''
TEST = '''
import unittest
from calliope_estensione import CalliopeFinta
from estensione import esegui


class Prova(unittest.TestCase):
    def test_km(self):
        self.assertEqual(esegui({"valore": 10}, CalliopeFinta())["valore"], 6.21)
'''


def manifesto(permessi=None):
    return json.dumps({"nome": "km_miglia", "titolo": "Chilometri in miglia",
                       "descrizione": "Converte i chilometri in miglia.",
                       "input": {"type": "object", "properties": {"valore": {"type": "number"}},
                                 "required": ["valore"]},
                       "permessi": permessi or {}, "livello": "familiare",
                       "limiti": {"tempo_s": 5, "memoria_mb": 128}})


class Cliente:
    """L'agente finto: un copione di passate (chiamate, oppure testo con i token detti)."""

    def __init__(self, copione):
        self.copione = list(copione)
        self.visti = []

    def chat(self, body, controlla=None, **kw):
        self.visti.append(body)
        p = self.copione.pop(0)
        if isinstance(p, dict) and "testo" in p:
            time.sleep(p.get("attesa", 0))
            return {"content": p["testo"], "tool_calls": [], "eval": p.get("eval", 10),
                    "prompt": 10}
        return {"content": "", "tool_calls": [{"name": n, "arguments": a} for n, a in p],
                "eval": 10, "prompt": 10}


def agente(copione, cfg=None):
    cfg = cfg or Config()
    cli = Cliente(copione)
    ag = Agente(cfg, SimpleNamespace(modello="m"), cli, Arbitro(False, 0), log=lambda *a: None)
    return ag, cli


def sandbox(nome):
    sb = Sandbox(TMP / nome, 30, 512, isolamento=Isolamento("processo", "prova"))
    sb.scrivi("calliope_estensione.py", runtime_testo())
    sb.scrivi(ct.FILE, ct.testo(Config(), "estensione"))
    sb.sola_lettura |= {ct.FILE, "calliope_estensione.py"}
    return sb


def esegui(copione, nome, cfg=None, lav=None):
    ag, cli = agente(copione, cfg)
    sb = sandbox(nome)
    lav = lav or Lavoro(nome, "estensione", "converti chilometri in miglia")
    t = time.perf_counter()
    try:
        ris = ag.codice(lav, sb, sistema=sistema_estensione(Config()),
                        controlla=controlla_consegna, esempi=True, piano=True)
    except Limite as e:
        ris = {"esito": "limite", "motivo": str(e)}
    return ris, lav, sb, cli, time.perf_counter() - t


def risposte_strumenti(cli, nome):
    """I risultati degli strumenti `nome` che l'agente ha visto (dall'ultima richiesta)."""
    msgs = cli.visti[-1]["messages"] if cli.visti else []
    return [json.loads(m["content"]) for m in msgs
            if m.get("role") == "tool" and m.get("tool_name") == nome]


PIANO_OK = ("piano", {"capacita_necessarie": ["calcolo"], "scope": {}, "fattibile": True,
                      "motivo": "è solo un conto"})
SCRIVI = [("scrivi_file", {"percorso": "estensione.py", "contenuto": CONV}),
          ("scrivi_file", {"percorso": "test_estensione.py", "contenuto": TEST})]


def prova_contratto():
    sezione("contratto delle capacità: generato dal codice e coerente col guardrail")
    verifica("le azioni del contratto sono quelle della porta", set(ct.PORTA) == set(gr.AZIONI),
             str(set(ct.PORTA) ^ set(gr.AZIONI)))
    for az, (es, scope, _) in ct.PORTA.items():
        senza = gr.valuta_porta(az, ct._ARGS.get(az, {}), {}, gr.StatoEsecuzione())
        con = gr.valuta_porta(az, ct._ARGS.get(az, {}), normalizza_permessi(scope),
                              gr.StatoEsecuzione())
        verifica(f"{az}: senza scope vietata, con lo scope del contratto no",
                 senza.classe == gr.VIETATA and con.regola != "estensione_permesso_negato"
                 and con.regola != "estensione_fuori_scope", f"{senza.regola} / {con.regola}")
    t = ct.testo(Config(), "estensione")
    verifica("ogni metodo con un esempio, ogni impossibile con l'alternativa",
             all(v[0] in t for v in ct.PORTA.values())
             and all(f"- {k}:" in t for k in ct.IMPOSSIBILI) and "Alternativa" in t)
    verifica("la classe la dice il guardrail (comando della casa: sfida; POST: sfida)",
             "frase di sfida" in ct.classe_detta("casa_comando")
             and "frase di sfida" in ct.classe_detta("rete_invia")
             and ct.classe_detta("casa_stato") == "da sola"
             and "VIETATA" in ct.classe_detta("rete_leggi"))
    verifica("i tetti del codice nel testo", f"{gr.MAX_RETE} di rete" in t
             and f"{gr.MAX_COMANDI_CASA} comandi" in t, "")
    verifica("breve: meno di 8000 caratteri", len(t) < 8000, f"{len(t)} caratteri")
    p = sistema_estensione(Config())
    verifica("nel prompt, con il primo passo obbligatorio", "CONTRATTO DELLE CAPACITÀ" in p
             and "PRIMO PASSO, OBBLIGATORIO" in p and "piano(" in p)
    tc = ct.testo(Config(), "codice")
    verifica("versione per i programmi (senza porta né piano)", "## 4. Non si prova qui" in tc
             and "calliope.casa_stato" not in tc)
    sb = sandbox("sola_lettura")
    try:
        sb.scrivi(ct.FILE, "niente")
        ok = False
    except Exception:  # noqa: BLE001
        ok = True
    from calliope.estensioni.servizio import _solo_usati
    f = {"estensione.py": b"import aiuto\nfrom pkg.mod import x\n", "aiuto.py": b"",
         "pkg/mod.py": b"", "esplora.py": b"open('x')", "test_estensione.py": b"import aiuto",
         "esempi/a.html": b"", "manifesto.json": b"{}"}
    verifica("nella versione solo i file usati (niente script d'esplorazione: prova vera)",
             sorted(_solo_usati(f)) == sorted(set(f) - {"esplora.py"}), str(sorted(_solo_usati(f))))
    verifica("CAPACITA.md in sola lettura e fuori dai risultati",
             ok and ct.FILE not in sb.copia_in(TMP / "ris_sl"), "")


def prova_piano():
    sezione("piano: primo passo obbligatorio")
    ris, lav, sb, cli, dt = esegui([
        SCRIVI[:1],
        [("piano", {"capacita_necessarie": ["teletrasporto"], "fattibile": True,
                    "motivo": "x"})],
        [("piano", {"capacita_necessarie": ["lista_leggi"], "scope": {}, "fattibile": True,
                    "motivo": "legge la spesa"})],
        [PIANO_OK], SCRIVI,
        [("scrivi_file", {"percorso": "manifesto.json", "contenuto": manifesto()})],
        [("consegna", {"riassunto": "Fatto.", "esito": "fatto"})]], "obbligo")
    prima = risposte_strumenti(cli, "scrivi_file")[0]
    piani = risposte_strumenti(cli, "piano")
    verifica("scrivi_file prima del piano: non scrive, torna l'errore",
             prima.get("ok") is False and "prima chiama piano" in prima.get("errore", ""),
             str(prima))
    verifica("voce sconosciuta: torna all'agente con l'elenco",
             piani[0].get("ok") is False and "teletrasporto" in piani[0]["errore"]
             and "rete_leggi" in piani[0]["errore"], piani[0].get("errore", "")[:80])
    verifica("scope che non copre lista_leggi: torna all'agente con lo scope giusto",
             piani[1].get("ok") is False and "legge" in piani[1]["errore"], piani[1].get("errore"))
    verifica("piano registrato, bozza del manifesto", piani[2].get("ok") and "bozza" in piani[2],
             str(piani[2])[:100])
    verifica("poi il lavoro finisce con il piano nel risultato", ris["esito"] == "fatto"
             and ris.get("test_passano") and ris["piano"]["capacita"] == ["calcolo"],
             str(ris.get("esito")))

    sezione("piano impossibile: chiusura alla prima passata")
    for nome, piano in [
        ("capacità impossibile", {"capacita_necessarie": ["rete_leggi", "email"], "scope": {},
                                  "fattibile": True, "motivo": "manda la spesa per email"}),
        ("fattibile=false", {"capacita_necessarie": ["javascript"], "fattibile": False,
                             "motivo": "il sito carica i dati con JavaScript",
                             "alternativa": "usare l'API pubblica del comune"}),
        ("fattibile=false senza voce impossibile",
         {"capacita_necessarie": ["rete_leggi"], "fattibile": False,
          "motivo": "il sito chiede di accedere con un account",
          "alternativa": "una pagina pubblica con gli stessi dati"})]:
        ris, lav, sb, cli, dt = esegui([[("piano", piano)]], "imp")
        verifica(f"{nome}: impossibile in una passata, con motivo e alternativa",
                 ris["esito"] == "impossibile" and lav.passi == 1
                 and "Non si può fare" in ris["riassunto"] and "alternativa" in ris["riassunto"]
                 and dt < 2, f"{dt:.2f}s «{ris.get('riassunto')}»")


def prova_permessi():
    sezione("chiedi_permesso: domanda alla persona, mai concesso da solo")
    flusso = {"legge": {"liste": ["spesa"]}, "rete": {"pubblica": True},
              "invia": [{"dati": "liste:spesa", "host": "api.prezzi.it"}]}
    piano = ("piano", {"capacita_necessarie": ["lista_leggi", "rete_leggi"],
                       "scope": flusso, "fattibile": True, "motivo": "prezzi della spesa"})
    # Senza chiedere: il flusso nel manifesto fa rifiutare la consegna
    ris, lav, sb, cli, dt = esegui([
        [piano], SCRIVI,
        [("scrivi_file", {"percorso": "manifesto.json", "contenuto": manifesto(flusso)})],
        [("consegna", {"riassunto": "Fatto.", "esito": "fatto"})],
        [("consegna", {"riassunto": "Fatto.", "esito": "fatto"})],
        [("consegna", {"riassunto": "Fatto.", "esito": "fatto"})],
        [("consegna", {"riassunto": "Fatto.", "esito": "impossibile"})]], "senza_chiedere")
    piani = risposte_strumenti(cli, "piano")
    cons = risposte_strumenti(cli, "consegna")
    verifica("il piano avverte: il flusso va chiesto con chiedi_permesso",
             "chiedi_permesso" in piani[0].get("da_chiedere", ""), str(piani[0])[:120])
    verifica("consegna con un flusso non chiesto: rifiutata (non sono nel piano)",
             cons and cons[0].get("ok") is False and "non sono nel piano" in cons[0]["errore"]
             and "api.prezzi.it" in cons[0]["errore"], str(cons[:1])[:160])

    # Chiedendo: il lavoro si sospende con la domanda, poi riprende
    copione = [[piano],
               [("chiedi_permesso", {"cosa": "mandare la lista della spesa ad api.prezzi.it",
                                     "motivo": "il sito dei prezzi la vuole nella query",
                                     "scope": {"legge": {"liste": ["spesa"]},
                                               "invia": flusso["invia"]}})]]
    ris, lav, sb, cli, dt = esegui(copione, "chiedi")
    verifica("chiedi_permesso: il lavoro aspetta la persona, con la domanda",
             ris["esito"] == "mancano_dati" and ris["domanda"].endswith("?")
             and "api.prezzi.it" in ris["domanda"], ris.get("domanda"))
    verifica("il permesso è registrato come chiesto, senza risposta",
             lav.contesto["piano"]["chiesti"][0]["risposta"] is None)
    lav.domande.append([ris["domanda"], "sì, va bene"])
    lav.risposta = "sì, va bene"
    ag, cli2 = agente([SCRIVI,
                       [("scrivi_file", {"percorso": "manifesto.json",
                                         "contenuto": manifesto(flusso)})],
                       [("consegna", {"riassunto": "Fatto.", "esito": "fatto"})]])
    ris2 = ag.codice(lav, sb, sistema=sistema_estensione(Config()),
                     controlla=controlla_consegna, esempi=True, piano=True)
    ultimo_utente = [m for m in cli2.visti[0]["messages"] if m["role"] == "user"][-1]["content"]
    verifica("alla ripresa l'agente riceve la risposta, con cosa fare se è no",
             "sì, va bene" in ultimo_utente and "Se ha detto di no" in ultimo_utente)
    verifica("con il permesso chiesto il flusso nel manifesto passa",
             ris2["esito"] == "fatto" and ris2["piano"]["chiesti"][0]["risposta"] == "sì, va bene",
             str(ris2.get("esito")))
    from calliope.estensioni.servizio import Estensioni
    est = Estensioni(Config(), TMP / "est", log=lambda *a: None)
    from calliope.estensioni.manifesto import valida
    c = est._presenta(valida(json.loads(manifesto(flusso))), 1, {"eseguiti": 1}, True,
                      {"rischi": [], "sintassi": []}, None, ris2["piano"])
    verifica("la scheda di revisione dice cosa è stato chiesto e la risposta",
             "durante il lavoro ho chiesto mandare la lista della spesa" in c["frase"]
             and "«sì, va bene»" in c["frase"] and "Piano:" in c["scheda_testo"], c["frase"][-160:])


def prova_vuoto():
    sezione("ragionamento a vuoto: spinta, poi chiusura")
    cfg = Config()
    cfg.agenti_token_senza_strumenti = 12000
    ris, lav, sb, cli, dt = esegui([{"testo": "", "eval": 7000}, {"testo": "", "eval": 7000},
                                    {"testo": "", "eval": 3000}], "vuoto", cfg)
    spinte = [m["content"] for m in cli.visti[-1]["messages"] if m["role"] == "user"
              and "senza usare gli strumenti" in m["content"]]
    verifica("alla soglia una spinta («chiama piano o scarica_esempio o scrivi_file»)",
             len(spinte) == 1 and "piano" in spinte[0] and "scrivi_file" in spinte[0], "")
    verifica("alla seconda: chiusura con il motivo, senza consumare altro",
             ris["esito"] == "limite" and "senza usare gli strumenti" in ris["motivo"]
             and lav.passi == 3 and lav.token == 17000, f"{ris} passi={lav.passi}")
    ris, lav, sb, cli, dt = esegui([{"testo": "", "eval": 13000}, [PIANO_OK],
                                    {"testo": "", "eval": 13000}, SCRIVI,
                                    [("scrivi_file", {"percorso": "manifesto.json",
                                                      "contenuto": manifesto()})],
                                    [("consegna", {"riassunto": "Fatto.", "esito": "fatto"})]],
                                   "vuoto_poi_lavora", cfg)
    verifica("dopo una chiamata di strumento il conto riparte (una spinta per volta)",
             ris["esito"] == "fatto", str(ris.get("esito")))
    cfg.agenti_minuti_senza_strumenti = 0.0001
    ris, lav, sb, cli, dt = esegui([{"testo": "", "eval": 10, "attesa": 0.05},
                                    {"testo": "", "eval": 10, "attesa": 0.05}],
                                   "vuoto_tempo", cfg)
    verifica("anche a tempo (minuti senza strumenti)", ris["esito"] == "limite"
             and lav.passi == 2, str(ris))


def prova_servizio():
    sezione("dal servizio dei lavori: contratto nella cartella, domanda annunciata, impossibile")
    from calliope.agenti import Lavori, carica
    from ollama_finto import FakeOllama
    fake = FakeOllama(modelli=("m",)).avvia()
    cfg = Config()
    cfg.agenti_url, cfg.agenti_modello = fake.url, "m"
    cfg.agenti_risultati, cfg.agenti_sandbox = str(TMP / "risultati"), str(TMP / "sb_svc")
    cfg.agenti_sandbox_motore = "processo"
    cfg.llm_native_url = "http://127.0.0.1:9"
    svc = Lavori(cfg, carica(cfg), log=lambda m: None)
    try:
        def visto(body):
            visto.sistema = body["messages"][0]["content"]
            return {"tool_calls": [{"name": "piano", "arguments": {
                "capacita_necessarie": ["file_persona"], "fattibile": True,
                "motivo": "legge i documenti del PC"}}]}
        fake.copione = [visto]
        lav = svc.nuovo("estensione", "leggi i miei documenti", "u1", "Dario", "amministra")
        lav.estensione, lav.file_iniziali = None, {"calliope_estensione.py": runtime_testo()}
        t = time.perf_counter()
        svc.avvia(lav)
        item = svc.done.get(timeout=15)
        dt = time.perf_counter() - t
        verifica("impossibile: annunciato in pochi secondi, con l'alternativa",
                 item["stato"] == "errore" and "lavoro di codice sul file" in item["messaggio"]
                 and dt < 10, f"{dt:.1f}s {item['messaggio'][:140]}")
        verifica("il contratto era nel prompt", "CONTRATTO DELLE CAPACITÀ" in visto.sistema)
        fake.copione = [{"tool_calls": [{"name": "piano", "arguments": {
                            "capacita_necessarie": ["rete_leggi", "parser"],
                            "scope": {"rete": {"pubblica": True}}, "fattibile": True,
                            "motivo": "legge una pagina"}}]},
                        {"tool_calls": [{"name": "elenca_file", "arguments": {}}]},
                        {"tool_calls": [{"name": "chiedi_permesso", "arguments": {
                            "cosa": "il tuo codice cliente del sito", "motivo": "il sito lo "
                            "vuole nell'indirizzo"}}]}]
        lav = svc.nuovo("estensione", "i miei consumi dal sito", "u1", "Dario", "amministra")
        lav.estensione, lav.file_iniziali = None, {"calliope_estensione.py": runtime_testo()}
        svc.avvia(lav)
        item = svc.done.get(timeout=15)
        elenco = [m for m in fake.richieste[-1]["messages"] if m.get("role") == "tool"]
        verifica("chiedi_permesso dal servizio: lavoro in attesa e domanda annunciata",
                 item["stato"] == "in_attesa" and "codice cliente" in item["messaggio"]
                 and item["messaggio"].endswith("?"), item["messaggio"][:160])
        verifica("CAPACITA.md nella cartella del lavoro (elenca_file)",
                 any(ct.FILE in m["content"] for m in elenco))
    except queue.Empty:
        verifica("il servizio ha risposto", False)
    finally:
        svc.close()
        fake.ferma()


if __name__ == "__main__":
    prova_contratto()
    prova_piano()
    prova_permessi()
    prova_vuoto()
    prova_servizio()
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)
