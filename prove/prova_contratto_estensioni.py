"""Il contratto delle estensioni Python (22/10/2026, issue #228, § 3.5 n. 33, 34 e 36 della
ricerca del 19/10 sulla solidità dell'agente, docs/ricerche/2026-10-19-solidita-harness-sviluppo.md).

1. CalliopeFinta dal manifesto (n. 33): un'azione che i permessi di manifesto.json non lasciano
   passare è un ErroreDelTest «è il test: …» con lo scope da dichiarare, una lettura senza
   risposta preparata pure (prima `{"ok": True}` e il KeyError in estensione.py); un «except
   Exception» dell'estensione non lo nasconde, e `chiama` lo rialza anche se inghiottito.
   Contrari: negate=[…] resta un ErroreCalliope, una scrittura senza risposta riesce, i dati
   propri sono simulati, senza manifest.json o con manifesto=False nessun controllo. La regola
   è la stessa della porta: su una griglia di manifesti e azioni CalliopeFinta nega quello che
   guardrail.valuta_porta vieta per permesso o scope, e solo quello; lo scope suggerito è quello
   del contratto (contratto.PORTA); le parole delle liste come liste.list_key.
2. `valida` con tutti gli errori in una volta (n. 34): tre difetti → tre errori in un messaggio
   e in `errori`; un difetto → il messaggio di prima; i testi che il modello legge tutti
   insieme; il consiglio su «cosa_fa» solo per la descrizione (contrari: titolo, input); le
   parole vietate nel contratto dalla stessa costante del controllo (`PAROLE_VIETATE`).
3. `chiama` in calliope_estensione.py, in sola lettura (n. 36): test_estensione.py di partenza
   senza la sua `chiama`; riscritto senza `chiama` (solo l'import) i test passano ancora nella
   sandbox; l'azione non dichiarata fa fallire il test con «è il test» nell'uscita.
"""

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calliope import guardrail as gr  # noqa: E402
from calliope import liste  # noqa: E402
from calliope.agenti.sandbox import Isolamento, Sandbox  # noqa: E402
from calliope.agenti.scheletri import TEST_ESTENSIONE, prepara_estensione  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.estensioni import _ospite  # noqa: E402
from calliope.estensioni import contratto as ct  # noqa: E402
from calliope.estensioni import manifesto as mf  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass
TMP = Path(tempfile.mkdtemp(prefix="calliope-contratto-est-"))
FINTO = [sys.executable, str(Path(__file__).with_name("docker_finto.py"))]
errori = 0
T0 = time.perf_counter()


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def alza(f):
    """(tipo dell'eccezione o None, messaggio)."""
    try:
        f()
    except BaseException as e:  # noqa: BLE001
        return type(e).__name__, str(e)
    return None, ""


METEO = {"rete": {"host": ["api.esempio.it"]}, "scrive": {"casa": ["cucina"], "dati": True}}
RISPOSTA = {"stato": 200, "tipo": "application/json", "testo": "{}"}


# ═══════════════════════════ 1. CalliopeFinta dal manifesto ═══════════════════════════

def prova_finta():
    sezione("1. CalliopeFinta dal manifesto (n. 33)")
    F = _ospite.CalliopeFinta
    f = F(risposte={"rete_leggi": RISPOSTA}, manifesto={"permessi": METEO})
    verifica("l'azione dichiarata va, con la risposta preparata",
             f.rete_leggi("https://api.esempio.it/cerca?q=x") == RISPOSTA)
    tipo, msg = alza(lambda: f.casa_stato("temperatura in camera"))
    verifica("un'azione non dichiarata è un errore del test, con lo scope da dichiarare",
             tipo == "ErroreDelTest" and msg.startswith("è il test: l'azione «casa_stato» non "
                                                        "è nel manifesto")
             and "legge.casa" in msg and "chiedi_permesso" in msg, msg)
    verifica("…e resta in errori_test", f.errori_test and f.errori_test[-1] == msg)
    tipo, msg = alza(lambda: f.rete_leggi("https://altro.it/x"))
    verifica("un host fuori da rete.host è un errore del test",
             tipo == "ErroreDelTest" and "altro.it" in msg, msg)
    tipo, msg = alza(lambda: f.casa_comando("accendi la luce del salotto"))
    verifica("una stanza fuori dallo scope è un errore del test",
             tipo == "ErroreDelTest" and "cucina" in msg, msg)
    verifica("contrario: la stanza dello scope va (una scrittura senza risposta riesce)",
             f.casa_comando("accendi la luce della cucina") == {"ok": True})
    f2 = F(negate=["casa_stato"], manifesto={"permessi": METEO})
    tipo, msg = alza(lambda: f2.casa_stato("camera"))
    verifica("contrario: negate=[…] resta un ErroreCalliope (il caso «negato» del test)",
             tipo == "ErroreCalliope", f"{tipo}: {msg}")
    f3 = F(manifesto={"permessi": METEO})
    tipo, msg = alza(lambda: f3.rete_leggi("https://api.esempio.it/x"))
    verifica("una lettura senza risposta preparata è un errore del test con la forma",
             tipo == "ErroreDelTest" and "non ha una risposta preparata" in msg
             and 'risposte={"rete_leggi"' in msg and "negate" in msg, msg)
    f3.dati_scrivi("stato", "uno")
    verifica("contrario: i dati propri sono simulati, senza risposte",
             f3.dati_leggi("stato") == "uno" and f3.dati_elenca() == ["stato"])
    f4 = F(manifesto=False)
    verifica("contrario: con manifesto=False nessun controllo dei permessi",
             f4.casa_comando("accendi tutto") == {"ok": True})
    tipo, _ = alza(lambda: f4.casa_stato("camera"))
    verifica("…ma una lettura senza risposta resta un errore del test", tipo == "ErroreDelTest")
    vecchio = F(manifesto={"permessi": {"casa": ["leggi"]}},
                risposte={"casa_stato": {"testo": "20 gradi"}})
    verifica("il formato del 04/10 dei permessi vale come alla porta",
             vecchio.casa_stato("camera") == {"testo": "20 gradi"}
             and alza(lambda: vecchio.casa_comando("accendi"))[0] == "ErroreDelTest")
    senza = F(manifesto={"nome": "x"}, risposte={"casa_stato": {"testo": "t"}})
    verifica("un manifesto senza «permessi» non dà niente, come alla porta",
             alza(lambda: senza.casa_stato("camera"))[0] == "ErroreDelTest")

    # L'estensione che inghiotte l'errore con «except Exception»
    def esegui_che_inghiotte(calliope):
        try:
            return calliope.casa_stato("camera")
        except Exception:  # noqa: BLE001
            return {"da_dire": "Non riesco."}
    tipo, _ = alza(lambda: esegui_che_inghiotte(F(manifesto={"permessi": {}})))
    verifica("un «except Exception» dell'estensione non nasconde l'errore del test",
             tipo == "ErroreDelTest")
    verifica("ErroreDelTest non è un'Exception, ErroreCalliope sì",
             not issubclass(_ospite.ErroreDelTest, Exception)
             and issubclass(_ospite.ErroreCalliope, Exception))

    # Il manifesto della cartella dove girano i test
    cart = TMP / "cartella"
    cart.mkdir()
    prima = os.getcwd()
    try:
        os.chdir(cart)
        verifica("contrario: senza manifest.json nella cartella nessun controllo",
                 F().casa_comando("accendi") == {"ok": True})
        (cart / "manifesto.json").write_text(json.dumps({"permessi": METEO}), encoding="utf-8")
        verifica("con manifesto.json nella cartella lo segue da sola",
                 alza(lambda: F().casa_comando("accendi la luce del salotto"))[0]
                 == "ErroreDelTest")
        (cart / "manifesto.json").write_text("{rotto", encoding="utf-8")
        g = F()
        verifica("contrario: un manifesto.json che non si legge non ferma i test (avviso)",
                 g.casa_comando("accendi") == {"ok": True} and g.avvisi
                 and "non si legge" in g.avvisi[0], str(g.avvisi))
        (cart / "manifesto.json").write_text(json.dumps({"permessi": {}}), encoding="utf-8")
        (cart / "estensione.py").write_text(
            "def esegui(dati, calliope):\n    try:\n        calliope.casa_stato('camera')\n"
            "    except BaseException:\n        pass\n    return {'da_dire': 'ok'}\n",
            encoding="utf-8")
        sys.modules.pop("estensione", None)
        tipo, msg = alza(lambda: _ospite.chiama({}))
        verifica("chiama rialza l'errore del test anche se l'estensione l'ha inghiottito",
                 tipo == "ErroreDelTest" and "casa_stato" in msg, f"{tipo}: {msg}")
        f5 = F(manifesto={"permessi": {"scrive": {"casa": True}}})
        sys.modules.pop("estensione", None)
        (cart / "estensione.py").write_text(
            "def esegui(dati, calliope):\n    calliope.casa_comando('accendi ' + dati['cosa'])\n"
            "    return {'da_dire': 'fatto'}\n", encoding="utf-8")
        out = _ospite.chiama({"cosa": "la luce"}, calliope=f5)
        verifica("chiama con una CalliopeFinta già fatta: le richieste si guardano dopo",
                 out == {"da_dire": "fatto"}
                 and f5.richieste == [("casa_comando", {"comando": "accendi la luce"})],
                 str(f5.richieste))
    finally:
        os.chdir(prima)
        sys.modules.pop("estensione", None)
        sys.path[:] = [p for p in sys.path if p != str(cart)]


# La griglia del confronto con la porta: manifesti a scope (validi) e richieste
MANIFESTI = [
    {},
    {"legge": {"casa": True}},
    {"legge": {"casa": ["camera", "cucina"]}},
    {"scrive": {"casa": ["cucina"]}},
    {"scrive": {"casa": True, "schermi": True}},
    {"legge": {"liste": ["spesa"]}},
    # I nomi come li scrive l'agente: la porta li normalizza (liste.list_key, host minuscoli)
    {"legge": {"liste": ["La lista della spesa"]}, "scrive": {"liste": ["Regali "]}},
    {"rete": {"host": ["API.Esempio.it"]}},
    {"legge": {"liste": ["cose da fare"]}, "scrive": {"liste": True}},
    {"scrive": {"liste": ["regali"]}},
    {"legge": {"agenda": True}},
    {"scrive": {"agenda": True}},
    {"legge": {"dati": True}},
    {"scrive": {"dati": True}},
    {"rete": {"pubblica": True}},
    {"rete": {"host": ["api.esempio.it"]}},
    {"rete": {"host": ["api.esempio.it"], "post": True}},
    {"legge": {"liste": ["spesa"]}, "invia": [{"dati": "liste:spesa", "host": "api.prezzi.it",
                                                "metodo": "POST"}]},
    {"legge": {"casa": True}, "invia": [{"dati": "casa", "host": "api.esempio.it"}]},
    {"casa": ["leggi", "comanda"], "liste": ["leggi"], "rete": ["api.esempio.it"],
     "rete_invia": True},
    {"agenda": ["leggi", "scrivi"], "dati": True, "schermi": True},
]
RICHIESTE = [
    ("casa_stato", {"cosa": "temperatura in camera"}), ("casa_stato", {"cosa": "il salotto"}),
    ("casa_comando", {"comando": "accendi la luce della cucina"}),
    ("casa_comando", {"comando": "spegni il salotto"}),
    ("lista_leggi", {"lista": "spesa"}), ("lista_leggi", {"lista": "la lista della spesa"}),
    ("lista_leggi", {"lista": "cose da fare"}), ("lista_aggiungi", {"lista": "regali",
                                                                    "voci": ["libro"]}),
    ("lista_aggiungi", {"lista": "spesa", "voci": ["latte"]}),
    ("lista_togli", {"lista": "Regali", "voci": ["libro"]}),
    ("agenda_elenca", {}), ("timer_imposta", {"durata": "10 minuti", "nome": "pasta"}),
    ("schermo_mostra", {"titolo": "t", "testo": "x"}), ("dati_leggi", {"nome": "s"}),
    ("dati_elenca", {}), ("dati_scrivi", {"nome": "s", "testo": "x"}),
    ("dati_cancella", {"nome": "s"}),
    ("rete_leggi", {"url": "https://api.esempio.it/x?q=1"}),
    ("rete_leggi", {"url": "https://www.altro.it/pagina"}),
    ("rete_leggi", {"url": "http://api.prezzi.it/listino"}),
    ("rete_leggi", {"url": "ftp://api.esempio.it/x"}),
    ("rete_invia", {"url": "https://api.esempio.it/ordini", "dati": {}}),
    ("rete_invia", {"url": "http://api.esempio.it/ordini", "dati": {}}),
    ("rete_invia", {"url": "https://api.prezzi.it/ordini", "dati": {}}),
    ("rete_invia", {"url": "https://www.altro.it/ordini", "dati": {}}),
]
# Le regole della porta che dicono «non dichiarato» (il resto dipende dall'esecuzione)
REGOLE_PERMESSO = {"estensione_permesso_negato", "estensione_fuori_scope",
                   "estensione_rete_host", "estensione_rete_schema"}


def prova_stessa_regola():
    sezione("1b. la stessa regola della porta")
    diversi = []
    n = 0
    for perm in MANIFESTI:
        for azione, args in RICHIESTE:
            n += 1
            v = gr.valuta_porta(azione, args, perm, gr.StatoEsecuzione())
            porta_nega = v.classe == gr.VIETATA and v.regola in REGOLE_PERMESSO
            finta_nega = bool(_ospite.permesso_mancante(azione, args, perm))
            if porta_nega != finta_nega:
                diversi.append((perm, azione, args, v.regola,
                                _ospite.permesso_mancante(azione, args, perm)))
    verifica(f"CalliopeFinta nega quello che la porta vieta per permesso e scope ({n} casi)",
             not diversi, str(diversi[:3]))
    negati = sum(bool(_ospite.permesso_mancante(a, x, p)) for p in MANIFESTI for a, x in RICHIESTE)
    verifica("…e la griglia ha casi dei due tipi", 0 < negati < n, f"{negati} su {n}")
    verifica("le azioni della finta sono quelle della porta",
             set(_ospite._SCOPE_AZIONE) == set(gr.AZIONI),
             str(set(_ospite._SCOPE_AZIONE) ^ set(gr.AZIONI)))
    sbagliati = []
    for az, (_, scope, _) in ct.PORTA.items():
        voci = re.findall(r"(legge|scrive|rete)\.(\w+)", _ospite._SCOPE_AZIONE[az])
        if not any((scope.get(s) or {}).get(k) is not None for s, k in voci):
            sbagliati.append((az, _ospite._SCOPE_AZIONE[az], scope))
    verifica("lo scope detto nell'errore è quello del contratto (contratto.PORTA)",
             not sbagliati, str(sbagliati))
    verifica("le parole delle liste sono quelle di liste.list_key",
             _ospite._PAROLE_LISTA == liste._LIST_WORDS.pattern
             and all(_ospite._lista(x) == liste.list_key(x) for x in
                     ("la lista della spesa", "Spesa", "nella lista delle cose da fare",
                      "regali", "")))


# ═══════════════════════════ 2. valida con tutti gli errori ═══════════════════════════

BUONO = {"nome": "meteo_domani", "titolo": "Meteo di domani",
         "cosa_fa": {"verbo": "dice", "oggetto": "il meteo di domani in una città"},
         "input": {"type": "object", "properties": {"citta": {"type": "string",
                                                              "description": "la città"}}},
         "permessi": {"rete": {"host": ["api.esempio.it"]}}, "livello": "familiare",
         "limiti": {"tempo_s": 10, "memoria_mb": 256}}


def _errore(m):
    try:
        mf.valida(m)
    except mf.ManifestoNonValido as e:
        return str(e), list(getattr(e, "errori", [str(e)]))
    return None, []


def prova_valida():
    sezione("2. valida con tutti gli errori in una volta (n. 34)")
    verifica("il manifesto buono passa", _errore(BUONO)[0] is None, str(_errore(BUONO)[0]))
    tre = dict(BUONO, nome="Meteo!", livello="tutti", limiti={"tempo_s": 999})
    msg, lista = _errore(tre)
    verifica("tre difetti → tre errori in una volta", len(lista) == 3
             and msg.startswith("il manifesto ha 3 errori: 1) «nome»") and "2) «livello»" in msg
             and "3) «limiti.tempo_s»" in msg, msg)
    uno = dict(BUONO, livello="tutti")
    msg, lista = _errore(uno)
    verifica("contrario: un difetto solo → il messaggio di prima",
             msg == "«livello» «tutti» non va: uno tra ospite, familiare, amministra"
             and lista == [msg], msg)
    altri = dict(BUONO, permessi={"rete": {"host": ["casa.local"]}},
                 input={"type": "object", "properties": {"x": {"type": "lista"}}})
    msg, lista = _errore(altri)
    verifica("anche input e permessi insieme", len(lista) == 2 and "input.x" in msg
             and "casa.local" in msg, msg)
    testi = dict(BUONO, titolo="Meteo sempre",
                 cosa_fa={"verbo": "dice", "oggetto": "il meteo quando serve"})
    msg, lista = _errore(testi)
    verifica("i testi che il modello legge tutti insieme (descrizione e titolo)",
             len(lista) == 2 and "«quando»" in lista[0] and "«sempre»" in lista[1], msg)
    verifica("il consiglio su «cosa_fa» per la descrizione",
             "«cosa_fa» è un verbo e un oggetto breve" in lista[0], lista[0])
    verifica("contrario: non per il titolo", "cosa_fa" not in lista[1]
             and lista[1].endswith("(è un testo che il modello legge)"), lista[1])
    msg, lista = _errore(dict(BUONO, input={"type": "object", "properties": {
        "citta": {"type": "string", "description": "la città che vuoi tu"}}}))
    verifica("contrario: non per la descrizione di un input", len(lista) == 1
             and "«citta»" in msg and "cosa_fa" not in msg, msg)
    msg, lista = _errore(dict(BUONO, cosa_fa={"verbo": "fa", "oggetto": "il meteo"},
                              titolo=None))
    verifica("un campo che manca ha il suo errore, senza un doppione dal controllo dei testi",
             len(lista) == 2 and "«titolo»" in lista[0] and "cosa_fa.verbo" in lista[1], msg)
    verifica("controlla_testi resta il primo motivo",
             mf.controlla_testi(mf.valida(BUONO)) is None
             and mf.controlla_testi({"descrizione": "Dice il meteo.", "titolo": ""})
             == "il titolo è vuota", str(mf.controlla_testi({"descrizione": "Dice il meteo.",
                                                             "titolo": ""})))
    # Le parole vietate: dalla stessa costante nel controllo e nel contratto
    t = ct.testo(Config(), "estensione")
    mancano = [p for p in mf.PAROLE_VIETATE if p.replace("*", "…") not in t]
    verifica("ogni parola vietata è nel contratto delle estensioni", not mancano, str(mancano))
    sfuggite = [p for p in mf.PAROLE_VIETATE
                if not mf._VIETATE.search("Dice " + p.replace("*", "ino") + " oggi")]
    verifica("…e ognuna la ferma il controllo", not sfuggite, str(sfuggite))
    verifica("contrario: le parole che contengono una vietata no («tutto», «tetto», «nonna»)",
             not any(mf._VIETATE.search(x) for x in ("tutto", "tetto", "nonna", "mailing")))


# ═══════════════════════════ 3. chiama in sola lettura ═══════════════════════════

CONVERTITORE = '''def esegui(dati, calliope):
    v = float(dati.get("valore") or 0)
    return {"da_dire": f"Sono {v * 1000:g} metri.", "risultato": v * 1000}
'''
CON_CASA = '''def esegui(dati, calliope):
    t = calliope.casa_stato("temperatura in camera")
    return {"da_dire": t["testo"]}
'''
RISCRITTO = '''import unittest
from calliope_estensione import chiama


class Prove(unittest.TestCase):
    def test_chilometri(self):
        self.assertEqual(chiama({"valore": 2})["risultato"], 2000)
'''


def sandbox(nome: str) -> Sandbox:
    os.environ["DOCKER_FINTO_IMMAGINI"] = "img-py,img-node"
    os.environ["DOCKER_FINTO_DIR"] = str(TMP / "docker")
    iso_py = Isolamento("docker", "finto", True, "", "img-py", FINTO)
    return Sandbox(TMP / nome, 30, 256, isolamento=iso_py)


def prova_chiama():
    sezione("3. chiama in calliope_estensione, in sola lettura (n. 36)")
    verifica("test_estensione.py di partenza senza la sua chiama, presa da calliope_estensione",
             "def chiama" not in TEST_ESTENSIONE
             and "from calliope_estensione import CalliopeFinta, ErroreCalliope, chiama"
             in TEST_ESTENSIONE)
    sb = sandbox("partenza")
    prepara_estensione(sb)
    verifica("calliope_estensione.py (con chiama) in sola lettura",
             "calliope_estensione.py" in sb.sola_lettura
             and "def chiama(" in (sb.root / "calliope_estensione.py").read_text(encoding="utf-8"))
    sb.scrivi("estensione.py", CONVERTITORE)
    sb.scrivi("manifesto.json", json.dumps({"permessi": {}}))
    r = sb.test()
    verifica("il test di partenza passa nella sandbox", r["passano"]
             and r["esito"]["eseguiti"] == 1, str(r["esito"]) + r["uscita"][-300:])
    sb.scrivi("test_estensione.py", RISCRITTO)
    r = sb.test()
    verifica("test_estensione.py riscritto senza chiama: i test passano da "
             "calliope_estensione.chiama", r["passano"] and r["esito"]["eseguiti"] == 1,
             str(r["esito"]) + r["uscita"][-300:])
    sb.scrivi("estensione.py", CON_CASA)
    sb.scrivi("test_estensione.py", RISCRITTO.replace(
        '["risultato"], 2000', '["da_dire"], "20 gradi"').replace(
        'chiama({"valore": 2})', 'chiama({}, risposte={"casa_stato": {"testo": "20 gradi"}})'))
    r = sb.test()
    verifica("un'azione non dichiarata nel manifesto: il test fallisce con «è il test»",
             not r["passano"] and "ErroreDelTest: è il test: l'azione «casa_stato»" in r["uscita"],
             r["uscita"][-400:])
    sb.scrivi("manifesto.json", json.dumps({"permessi": {"legge": {"casa": True}}}))
    r = sb.test()
    verifica("contrario: dichiarata nel manifesto, il test passa", r["passano"],
             r["uscita"][-300:])


if __name__ == "__main__":
    prova_finta()
    prova_stessa_regola()
    prova_valida()
    prova_chiama()
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)
