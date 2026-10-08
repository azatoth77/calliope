"""La diagnosi dei collaudi della modalità sviluppo (08/10/2026 notte), a secco;
docs/aree/agenti-estensioni.md.

Il caso vero, riscritto con nomi di fantasia: l'agente aveva la traccia giusta
(«name=Pratofiorito%2BMaggiore» → 32 byte), l'ha letta male, e i suoi test passavano «24 su 24»
con un geocoder finto scritto da lui che trovava la città. «E se domani il problema fosse un
altro?»: due meccanismi generali, che non sanno niente della doppia codifica.

1. confronto tra collaudi riusciti e falliti verso lo stesso host e percorso: parametri (com'erano
   scritti e decodificati una volta), metodo, corpo; stato, dimensione, chiavi JSON di primo
   livello. Anche quando il codice dice «riuscito» (un «non ho trovato») ma la risposta è più
   povera; con i soli falliti, i riusciti delle versioni di prima. Contrari: nessun riuscito,
   host diversi, un collaudo solo; tetto di dimensione; tracce di prima senza `chiavi`;
2. risposte vere come esempi per i test: la porta le tiene solo per GET verso gli host del
   manifesto, senza dati di casa letti né dati riservati (un dato personale tolto → «ripulita»),
   troncate oltre ESEMPIO_MAX, al più due indirizzi per esecuzione; `esempi_veri/` con l'indice
   nella cartella dell'agente e nei vincoli di sviluppo_correggi e dell'analisi;
3. CalliopeFinta risponde con la risposta vera per lo stesso indirizzo: il test dell'agente che
   «trova» la città fallisce, quello con la codifica giusta passa; contrari (troncata, ripulita,
   `esempi_veri=False`, indirizzo diverso);
4. il confronto nel contesto di sviluppo_chiedi e in testa alla traccia nei vincoli.

    python prove\\prova_diagnosi_collaudi.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_estensioni as P  # noqa: E402
import prova_sviluppo_giro3 as G3  # noqa: E402
import prova_sviluppo_giro5 as G5  # noqa: E402
from calliope import sviluppo as SV  # noqa: E402
from calliope.estensioni import _ospite  # noqa: E402
from calliope.estensioni import porta as PO  # noqa: E402
from calliope.web.rete import RetePubblica  # noqa: E402

errori = 0
CITTA = "Pratofiorito Maggiore"          # di fantasia, due parole
UNA = "Valfiorita"                       # di fantasia, una parola
GEO = {"valfiorita": (45.7, 9.6), "pratofiorito maggiore": (45.6, 8.9)}
HOST = "geocoding-api.open-meteo.com"


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


def geocoder(url, **kw):
    """Come il geocoder vero: una città trovata ha «results» (con un po' di dati, ~3 kB);
    una non trovata solo «generationtime_ms» (32 byte), senza «results»."""
    q = parse_qs(urlsplit(url).query)
    nome = (q.get("name") or [""])[0].lower()
    if nome in GEO:
        ris = [{"id": 3000 + i, "name": nome.title(), "latitude": GEO[nome][0],
                "longitude": GEO[nome][1], "country": "Italia", "admin1": "Regione di prova",
                "feature_code": "PPL", "population": 1000 * (i + 1)} for i in range(14)]
        testo = json.dumps({"results": ris, "generationtime_ms": 0.61})
    else:
        testo = json.dumps({"generationtime_ms": 0.4321})
    return {"url": url, "tipo": "application/json", "byte": len(testo), "rimandi": 0,
            "testo_grezzo": testo}


def richiesta(url, esito="stato 200", byte=0, chiavi=None, vuote=None, **extra):
    r = {"metodo": "GET", "url": url, "esito": esito, "byte": byte, "ms": 50}
    if chiavi is not None:
        r["chiavi"] = chiavi
    if vuote:
        r["vuote"] = vuote
    r.update(extra)
    return r


def collaudo(dati, ok, rete, versione=2, esito="", **extra):
    return {"quando": time.time(), "dati": dati, "ok": ok, "esito": esito or "…",
            "versione": versione, "rete": rete, **extra}


U_OK = f"https://{HOST}/v1/search?name=Valfiorita&count=10&language=it"
U_DOPPIA = f"https://{HOST}/v1/search?name=Pratofiorito%2BMaggiore&count=10&language=it"
U_GIUSTO = f"https://{HOST}/v1/search?name=Pratofiorito+Maggiore&count=10&language=it"


# ═══════════════════════════ 1. il confronto ═══════════════════════════

def prova_confronto():
    print("— 1. confronto tra collaudi riusciti e falliti")
    ok = collaudo(UNA, True, [richiesta(U_OK, byte=3353, chiavi=["results",
                                                                  "generationtime_ms"])],
                  esito="A Valfiorita ci sono 18 gradi.")
    ko = collaudo(CITTA, False, [richiesta(U_DOPPIA, byte=32, chiavi=["generationtime_ms"])],
                  esito="errore: nessun risultato")
    t = SV.confronto([ok, ko])
    verifica("l'esempio della decisione: riuscito e fallito in fila, con il valore com'è "
             "scritto e decodificato una volta, 3.353 contro 32 byte",
             t.startswith("Confronto automatico tra collaudi riusciti e falliti")
             and f"Riuscito: «{UNA}» → GET {HOST}/v1/search name=Valfiorita → stato 200, "
                 "3.353 byte, chiavi results, generationtime_ms." in t
             and f"Fallito: «{CITTA}» → GET {HOST}/v1/search name=Pratofiorito%2BMaggiore "
                 "(decodificato: «Pratofiorito+Maggiore») → stato 200, 32 byte" in t, t)
    verifica("…le differenze: solo il parametro name (con «%2B» e «+» che nel riuscito non "
             "ci sono), la risposta del fallito non ha results ed è molto più piccola",
             "Differenze: solo il parametro name" in t and "«%2B»" in t and "«+»" in t
             and "la risposta del fallito non ha results" in t
             and "molto più piccola (32 contro 3353 byte)" in t, t)
    verifica("…l'input del collaudo e il valore che il servizio legge: stesso testo, segni "
             "diversi (nel riuscito coincidono)",
             f"l'input dati del fallito era «{CITTA}», ma il servizio legge name = "
             "«Pratofiorito+Maggiore» (nel riuscito input e valore letto coincidono: "
             "«Valfiorita»)" in t, t)
    ok_a = dict(ok, argomenti={"citta": "Borgo Alto"},
                rete=[richiesta(U_OK.replace("Valfiorita", "Borgo%2BAlto"), byte=3000,
                                chiavi=["results", "generationtime_ms"])])
    t2 = SV.confronto([ok_a, dict(ko, argomenti={"citta": CITTA})])
    verifica("contrario: anche nel riuscito l'input cambia allo stesso modo → non lo dice",
             "ma il servizio legge" not in t2 and "Fallito" in t2, t2)
    t2 = SV.confronto([ok, dict(ko, argomenti={"citta": "Borgoverde"})])
    verifica("contrario: un input che non c'entra con il valore letto → non lo dice",
             "ma il servizio legge" not in t2, t2)
    verifica("…generale: niente parole sulla doppia codifica né sulle città",
             "doppia" not in t and "codific" not in t.replace("decodificato", ""), t)

    # Il caso vero: il codice dice «riuscito» a «Non ho trovato…» (lo giudica la persona)
    ko2 = dict(ko, ok=True, esito=f"Non ho trovato {CITTA}.")
    t = SV.confronto([ok, ko2])
    verifica("nessun collaudo segnato fallito: vale come fallito quello con la risposta più "
             "povera dallo stesso indirizzo, detto così",
             f"Fallito: «{CITTA}» (per il codice riuscito: «Non ho trovato {CITTA}.»; la "
             "risposta ha meno dati)" in t and "non ha results" in t
             and f"Fallito: «{UNA}»" not in t, t)
    # Una chiave vuota invece che assente
    ko3 = collaudo(CITTA, True, [richiesta(U_DOPPIA, byte=40, chiavi=["results", "ms"],
                                           vuote=["results"])])
    ok3 = collaudo(UNA, True, [richiesta(U_OK, byte=3000, chiavi=["results", "ms"])])
    t = SV.confronto([ok3, ko3])
    verifica("…anche con «results» vuoto invece che assente", "sono vuote: results" in t
             and "results (vuota)" in t, t)
    # Errore della porta contro risposta
    ko4 = collaudo(CITTA, False, [richiesta(
        f"https://{HOST}/v1/search?name={CITTA}&count=10", esito="errore",
        errore="rete: URL non valido: c'è uno spazio nel parametro «name»")])
    t = SV.confronto([ok, ko4])
    verifica("un errore della porta contro una risposta: l'errore e lo spazio nel valore",
             "errore: rete: URL non valido" in t and "«spazio»" in t
             and "il fallito ha «errore» invece di «stato 200»" in t, t)
    # Il fallito si ferma prima: il riuscito ha fatto anche un'altra richiesta
    meteo = "https://api.open-meteo.com/v1/forecast?latitude=45.7&longitude=9.6"
    ok5 = collaudo(UNA, True, [richiesta(U_OK, byte=3353, chiavi=["results"]),
                               richiesta(meteo, byte=900, chiavi=["daily"])])
    t = SV.confronto([ok5, ko])
    verifica("il riuscito ha fatto anche la richiesta del meteo, il fallito no",
             "Il riuscito ha fatto anche: GET api.open-meteo.com/v1/forecast, il fallito no"
             in t, t)
    # Nessuna richiesta nel fallito
    ko6 = collaudo(CITTA, False, [], esito="errore: KeyError")
    ko6.pop("rete")
    t = SV.confronto([ok, ko6])
    verifica("un fallito senza richieste di rete: lo dice, e mostra quelle del riuscito",
             "→ nessuna richiesta di rete." in t and "name=Valfiorita" in t, t)
    # POST: il corpo
    post = "https://api.prova.example/v1/invia"
    t = SV.confronto([collaudo("a", True, [richiesta(post, metodo="POST", corpo='{"n": 1}',
                                                     chiavi=["ok"], byte=20)]),
                      collaudo("b", False, [richiesta(post, metodo="POST", corpo='{"n": "1"}',
                                                      esito="stato 400", byte=30)])])
    verifica("POST: il corpo mandato tra le differenze, lo stato diverso",
             "il corpo mandato" in t and "corpo: {\"n\": \"1\"}" in t
             and "«stato 400» invece di «stato 200»" in t, t)

    # Solo falliti nella versione provata: i riusciti delle versioni di prima
    v1 = dict(ok, versione=1)
    v2 = dict(ko, versione=2)
    t = SV.confronto([v1, v2])
    verifica("solo falliti nella versione nuova: il confronto con il riuscito della versione 1",
             f"Riuscito: «{UNA}», versione 1 di prima" in t and "Fallito: «" in t, t)

    # Contrari
    verifica("contrario: nessun riuscito (due falliti) → niente confronto",
             SV.confronto([ko, dict(ko, dati="Borgo Alto")]) == "")
    altro = collaudo(UNA, True, [richiesta("https://altro.example/cerca?q=Valfiorita",
                                           byte=500, chiavi=["voci"])])
    verifica("contrario: host diversi → niente confronto", SV.confronto([altro, ko]) == "")
    verifica("contrario: un collaudo solo → niente", SV.confronto([ko]) == "")
    verifica("contrario: due riusciti con la stessa forma di risposta → niente",
             SV.confronto([ok, dict(ok, dati="Borgoverde",
                                    rete=[richiesta(U_OK.replace("Valfiorita", "Borgoverde"),
                                                    byte=3100, chiavi=["results",
                                                                       "generationtime_ms"])])
                           ]) == "")
    # Tetto
    tanti = [ok] + [collaudo(f"Città {i}", False, [richiesta(
        U_DOPPIA.replace("Pratofiorito", f"Prato{i}" * 20), byte=32,
        chiavi=["generationtime_ms"])] * 3) for i in range(6)]
    t = SV.confronto(tanti)
    verifica(f"tetto: al più {SV.MAX_CONFRONTO} caratteri e {SV.CONFRONTO_FALLITI} falliti",
             0 < len(t) <= SV.MAX_CONFRONTO and t.count("Fallito: «") <= SV.CONFRONTO_FALLITI
             * SV.CONFRONTO_RICHIESTE, str(len(t)))
    # Tracce di prima (senza `chiavi`): dall'inizio della risposta se è intera
    vecchio_ok = collaudo(UNA, True, [richiesta(U_OK, byte=40,
                                                inizio='{"results": [1], "x": 2}')])
    vecchio_ok["rete"][0]["byte"] = 24
    vecchio_ko = collaudo(CITTA, False, [richiesta(U_DOPPIA, byte=8, inizio='{"x": 2}')])
    t = SV.confronto([vecchio_ok, vecchio_ko])
    verifica("tracce di prima del confronto (senza `chiavi`): le chiavi dall'inizio intero",
             "non ha results" in t, t)
    # Dati tolti dalla porta restano tolti
    tolto = collaudo(CITTA, False, [richiesta(
        f"https://{HOST}/v1/search?name=[tolto]&count=10", byte=32, chiavi=["x"])])
    t = SV.confronto([ok, tolto])
    verifica("un valore tolto dalla porta resta «[tolto]», non si decodifica",
             "name=[tolto]" in t and "decodificato: «[tolto]" not in t, t)

    pf = PO.forma_json
    verifica("forma_json: oggetto con chiavi e vuote, lista, testo, JSON rotto",
             pf('{"a": [], "b": 1, "c": null}') == ("oggetto JSON", ["a", "b", "c"], ["a", "c"])
             and pf("[1, 2]") == ("lista JSON di 2", [], [])
             and pf("<html>") == ("", [], []) and pf('{"a": ') == ("", [], []))


# ═══════════════════════════ 2. la porta e gli esempi veri ═══════════════════════════

def _es(manifesto_host=(HOST,), contaminata=False, traccia=None):
    return SimpleNamespace(
        manifesto={"permessi": {"rete": {"pubblica": True, "host": list(manifesto_host)}}},
        traccia=[] if traccia is None else traccia,
        storia=SimpleNamespace(contaminazione={"casa"} if contaminata else set()))


def _porta(riservati=None):
    svc = SimpleNamespace(rete=SimpleNamespace(riservati=riservati,
                                               host_per_registro=lambda h: h),
                          nota_regola=lambda *a: None)
    return PO.Porta(svc)


def _ris(testo):
    return {"risultato": {"stato": 200, "tipo": "application/json", "testo": testo}}


def prova_porta():
    print("— 2. la porta: forma della risposta ed esempi veri")
    p = _porta()
    es = _es()
    testo = json.dumps({"results": [{"id": 1}], "generationtime_ms": 0.5})
    p._traccia(es, "rete_leggi", U_OK, _ris(testo), 0)
    r = es.traccia[-1]
    verifica("traccia: forma, chiavi di primo livello e l'esempio intero (host del manifesto)",
             r.get("forma") == "oggetto JSON" and r.get("chiavi") == ["results",
                                                                      "generationtime_ms"]
             and r.get("esempio", {}).get("testo") == testo
             and r["esempio"]["troncato"] is False and r["esempio"]["ripulito"] is False,
             json.dumps(r)[:300])
    es = _es(manifesto_host=())
    p._traccia(es, "rete_leggi", U_OK, _ris(testo), 0)
    verifica("contrario: un host non scritto nel manifesto (solo «pubblica») → niente esempio",
             "esempio" not in es.traccia[-1] and es.traccia[-1].get("chiavi"))
    es = _es(contaminata=True)
    p._traccia(es, "rete_leggi", U_OK, _ris(testo), 0)
    verifica("contrario: dopo una lettura di dati di casa → niente esempio",
             "esempio" not in es.traccia[-1])
    es = _es()
    p._traccia(es, "rete_invia", f"https://{HOST}/v1/x", _ris(testo), 0, corpo={"n": 1})
    verifica("contrario: una POST → niente esempio, il corpo nella traccia",
             "esempio" not in es.traccia[-1] and es.traccia[-1].get("corpo") == '{"n": 1}')
    es = _es(contaminata=True)
    p._traccia(es, "rete_invia", f"https://{HOST}/v1/x", _ris(testo), 0, corpo={"t": 21})
    verifica("…con dati di casa letti il corpo è solo la sua dimensione",
             "21" not in es.traccia[-1].get("corpo", "") and "tolto" in es.traccia[-1]["corpo"])
    # Dati riservati e personali
    ris = SimpleNamespace(trova=lambda *t, **k: ["codice"] if any("girasole4417" in x
                                                                  for x in t) else [],
                          ripulitore=SimpleNamespace(pulisci=lambda t: (
                              t.replace("mario@example.org", "[email]"), [])))
    p = _porta(ris)
    es = _es()
    p._traccia(es, "rete_leggi", U_OK, _ris('{"chiave": "girasole4417"}'), 0)
    verifica("contrario: una risposta con un dato riservato di casa → niente esempio",
             "esempio" not in es.traccia[-1])
    p._traccia(es, "rete_leggi", U_OK + "&a=2", _ris('{"contatto": "mario@example.org"}'), 0)
    e = es.traccia[-1].get("esempio") or {}
    verifica("un dato personale riconosciuto si toglie, e l'esempio è segnato «ripulito»",
             e.get("ripulito") is True and "mario@" not in e.get("testo", ""), json.dumps(e))
    # Grandi: troncate
    p = _porta()
    es = _es()
    grande = json.dumps({"results": ["x" * 100] * 200})
    p._traccia(es, "rete_leggi", U_OK, _ris(grande), 0)
    e = es.traccia[-1]["esempio"]
    verifica(f"una risposta grande si tronca a {PO.ESEMPIO_MAX} caratteri, segnata «troncata»",
             len(e["testo"]) == PO.ESEMPIO_MAX and e["troncato"] is True
             and es.traccia[-1]["chiavi"] == ["results"])
    # Al più due indirizzi per esecuzione, lo stesso una volta
    for i in range(4):
        p._traccia(es, "rete_leggi", U_OK + f"&p={i}", _ris(testo), 0)
    p._traccia(es, "rete_leggi", U_OK, _ris(testo), 0)
    n = len({r["url"] for r in es.traccia if r.get("esempio")})
    verifica(f"al più {PO.ESEMPI_PER_ESECUZIONE} indirizzi con l'esempio per esecuzione, lo "
             "stesso indirizzo una volta sola",
             n == PO.ESEMPI_PER_ESECUZIONE
             and sum(1 for r in es.traccia if r.get("esempio")) == n, str(n))
    # Un URL con un valore tolto: niente esempio (l'URL della traccia non è quello vero)
    p = _porta(ris)
    es = _es()
    p._traccia(es, "rete_leggi", f"https://{HOST}/v1/search?k=girasole4417", _ris(testo), 0)
    verifica("contrario: un URL con un valore tolto → niente esempio",
             "esempio" not in es.traccia[-1] and "[tolto]" in es.traccia[-1]["url"])

    # esempi_veri: file, indice, ordine, tetto
    ok = collaudo(UNA, True, [richiesta(U_OK, byte=10, esempio={
        "stato": 200, "tipo": "application/json", "testo": '{"results": [1]}',
        "troncato": False, "ripulito": False})])
    ko = collaudo(CITTA, True, [richiesta(U_DOPPIA, byte=5, esempio={
        "stato": 200, "tipo": "application/json", "testo": '{"g": 1}', "troncato": False,
        "ripulito": False})], giudizio="non trova la città")
    f = SV.esempi_veri([ok, ko])
    nomi = sorted(f)
    verifica("esempi_veri: un file per indirizzo (<host>_<n>.json) e l'indice",
             nomi == [f"esempi_veri/{HOST}_1.json", f"esempi_veri/{HOST}_2.json",
                      "esempi_veri/indice.json"], str(nomi))
    primo = json.loads(f[f"esempi_veri/{HOST}_1.json"])
    indice = json.loads(f["esempi_veri/indice.json"])
    verifica("…prima il collaudo fallito, con richiesta (URL com'era) e risposta vera",
             primo["richiesta"]["url"] == U_DOPPIA and primo["risposta"]["testo"] == '{"g": 1}'
             and primo["collaudo"]["riuscito"] is False and indice[0]["riuscito"] is False
             and indice[1]["url"] == U_OK, json.dumps(primo)[:300])
    molti = [collaudo(f"c{i}", False, [richiesta(U_OK + f"&i={i}", esempio={
        "stato": 200, "testo": "{}"})]) for i in range(10)] + [ok]
    f = SV.esempi_veri(molti)
    verifica(f"tetto: al più {SV.MAX_ESEMPI} file, e c'è posto per un riuscito",
             len(f) == SV.MAX_ESEMPI + 1 and any(v.get("riuscito") for v in
                                                 json.loads(f["esempi_veri/indice.json"])))
    verifica("contrario: nessun esempio nei collaudi → nessun file",
             SV.esempi_veri([collaudo("x", False, [richiesta(U_OK)])]) == {})


# ═══════════════════════════ 3. CalliopeFinta con le risposte vere ═══════════════════════

TEST_AGENTE = '''
import unittest
from calliope_estensione import CalliopeFinta
import estensione


class Prova(unittest.TestCase):
    def test_citta_di_due_parole(self):
        # Il geocoder finto «dell'agente»: trova qualunque città
        finta = CalliopeFinta(risposte={"rete_leggi": {"stato": 200, "tipo": "application/json",
            "testo": '{"results": [{"latitude": 1, "longitude": 2}]}'}})
        out = estensione.esegui({"citta": "Pratofiorito Maggiore"}, finta)
        self.assertIn("gradi", out["da_dire"])


if __name__ == "__main__":
    unittest.main()
'''


def _cartella(tmp, codice, esempi):
    tmp.mkdir(parents=True, exist_ok=True)
    from calliope.estensioni.servizio import runtime_testo
    (tmp / "calliope_estensione.py").write_text(runtime_testo(), encoding="utf-8")
    (tmp / "estensione.py").write_text(codice, encoding="utf-8")
    (tmp / "test_estensione.py").write_text(TEST_AGENTE, encoding="utf-8")
    for nome, testo in esempi.items():
        (tmp / nome).parent.mkdir(parents=True, exist_ok=True)
        (tmp / nome).write_text(testo, encoding="utf-8")


def _test(tmp):
    r = subprocess.run([sys.executable, "-B", "-m", "unittest", "-q", "test_estensione"],
                       cwd=tmp, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stderr


def prova_finta(tmp):
    print("— 3. CalliopeFinta con le risposte vere dei collaudi")
    vera = geocoder(U_DOPPIA)["testo_grezzo"]
    ko = collaudo(CITTA, True, [richiesta(U_DOPPIA, byte=len(vera), esempio={
        "stato": 200, "tipo": "application/json", "testo": vera, "troncato": False,
        "ripulito": False})], esito=f"Non ho trovato {CITTA}.")
    esempi = SV.esempi_veri([ko])
    _cartella(tmp / "doppia", G5.CODICE_DOPPIA, esempi)
    rc, err = _test(tmp / "doppia")
    verifica("il caso vero: il test dell'agente con il geocoder finto che «trova» la città "
             "fallisce, perché per quell'indirizzo risponde il servizio vero",
             rc != 0 and "risposta vera di un collaudo" in err, err[-400:])
    _cartella(tmp / "giusto", G5.CODICE_GIUSTO, esempi)
    rc, err = _test(tmp / "giusto")
    verifica("contrario: con la codifica giusta l'indirizzo è un altro, vale la risposta del "
             "test (passa)", rc == 0 and "risposta vera" not in err, err[-400:])
    _cartella(tmp / "senza", G5.CODICE_DOPPIA, {})
    rc, err = _test(tmp / "senza")
    verifica("contrario: senza esempi_veri tutto come prima (il test finto passa)", rc == 0,
             err[-300:])

    cwd = os.getcwd()
    os.chdir(tmp / "doppia")
    try:
        f = _ospite.CalliopeFinta(risposte={"rete_leggi": {"stato": 200, "testo": "finto"}})
        uguale_riordinato = (f"https://{HOST}/v1/search?language=it&count=10"
                             "&name=Pratofiorito%2BMaggiore")
        r = f.rete_leggi(uguale_riordinato)
        verifica("lo stesso indirizzo con i parametri in un altro ordine → la risposta vera",
                 r["testo"] == vera and f.vere == [uguale_riordinato], str(r)[:200])
        f = _ospite.CalliopeFinta(risposte={"rete_leggi": {"stato": 200, "testo": "finto"}},
                                  esempi_veri=False)
        verifica("contrario: esempi_veri=False (un guasto simulato) → la risposta del test",
                 f.rete_leggi(U_DOPPIA)["testo"] == "finto")
        f = _ospite.CalliopeFinta(risposte={"rete_leggi": {"stato": 200, "testo": "finto"}},
                                  negate=["rete_leggi"])
        try:
            f.rete_leggi(U_DOPPIA)
            negata = False
        except _ospite.ErroreCalliope:
            negata = True
        verifica("contrario: una rete negata nel test resta negata", negata)
    finally:
        os.chdir(cwd)
    for segno in ("troncato", "ripulito"):
        ko2 = collaudo(CITTA, True, [richiesta(U_DOPPIA, esempio={
            "stato": 200, "testo": vera, "troncato": segno == "troncato",
            "ripulito": segno == "ripulito"})])
        d = tmp / segno
        _cartella(d, G5.CODICE_DOPPIA, SV.esempi_veri([ko2]))
        os.chdir(d)
        try:
            f = _ospite.CalliopeFinta(risposte={"rete_leggi": {"stato": 200, "testo": "finto"}})
            verifica(f"contrario: una risposta vera {segno[:-1]}a non sostituisce quella del "
                     "test",
                     f.rete_leggi(U_DOPPIA)["testo"] == "finto")
        finally:
            os.chdir(cwd)


# ═══════════════════════════ 4. nello sviluppo vero ═══════════════════════════

def prova_sviluppo(tmp):
    print("— 4. nello sviluppo: sviluppo_chiedi, sviluppo_correggi, analisi")
    cfg, reg, ctx, est, svc = G3.ambiente(tmp)
    est.rete = RetePubblica(cfg, tmp / "uscite.jsonl", scarica=geocoder, log=lambda *a: 0)
    G3.apri(ctx, est, svc, G5.CODICE_DOPPIA)
    svs = svc.sviluppi
    sv = svs.corrente("u1")
    P.chiama(reg, ctx, "sviluppo_collauda", {"argomenti": {"citta": UNA}}, turno=5)
    verifica("un collaudo solo: la traccia senza confronto",
             "Confronto automatico" not in svs.testo_traccia(sv))
    out = P.chiama(reg, ctx, "sviluppo_collauda", {"argomenti": {"citta": CITTA}}, turno=6)
    c = sv.collaudi[-1]
    r0 = c["rete"][0]
    verifica("il collaudo con «Pratofiorito Maggiore»: «Non ho trovato» (per il codice "
             "riuscito), nella traccia le chiavi e la risposta vera intera",
             "Non ho trovato" in json.dumps(out, ensure_ascii=False) and c["ok"]
             and r0.get("chiavi") == ["generationtime_ms"]
             and json.loads(r0["esempio"]["testo"]) == {"generationtime_ms": 0.4321},
             json.dumps(c, ensure_ascii=False)[:500])
    verifica("…la risposta vera non arriva al modello della voce",
             "generationtime_ms" not in json.dumps(out, ensure_ascii=False))
    testo = svs.testo_per_agente(sv)
    verifica("sviluppo_chiedi: il confronto nel contesto, prima dei collaudi",
             "Confronto automatico tra collaudi" in testo
             and testo.index("Confronto automatico") < testo.index("Collaudi fatti dalla")
             and "decodificato: «Pratofiorito+Maggiore»" in testo
             and "non ha results" in testo, testo[:1500])
    t = svs.testo_traccia(sv)
    verifica("…e in testa alla traccia, sopra l'avviso della doppia codifica",
             t.startswith("Confronto automatico") and t.index("Confronto") < t.index(
                 "ATTENZIONE, dalla porta di Calliope"), t[:300])
    ctx.tool_in_sospeso = "sviluppo_correggi"
    P.chiama(reg, ctx, "sviluppo_correggi", {"problema": f"{CITTA} non la trova"}, turno=7)
    ctx.tool_in_sospeso = None
    lav = svc.lavori[-1]
    v = lav.vincoli or ""
    fi = lav.file_iniziali or {}
    verifica("sviluppo_correggi: nei vincoli il confronto e come usare gli esempi veri",
             "Confronto automatico tra collaudi" in v and "esempi_veri/" in v
             and "Non inventare risposte del servizio" in v
             and v.index("Confronto automatico") < v.index("ATTENZIONE, dalla porta"), v[-1500:])
    verifica("…nella cartella dell'agente esempi_veri/ con l'indice, accanto ai file della "
             "versione provata",
             f"esempi_veri/{HOST}_1.json" in fi and "esempi_veri/indice.json" in fi
             and "estensione.py" in fi and "calliope_estensione.py" in fi, str(sorted(fi)))
    e = json.loads(fi[f"esempi_veri/{HOST}_1.json"])
    verifica("…il primo è il collaudo con «Pratofiorito Maggiore»: richiesta e risposta vera",
             "Pratofiorito%2BMaggiore" in e["richiesta"]["url"]
             and json.loads(e["risposta"]["testo"]) == {"generationtime_ms": 0.4321})
    # I file entrano davvero nella sandbox (sottocartella)
    from calliope.agenti.sandbox import Sandbox
    sb = Sandbox(tmp / "sb", 5, 256)
    for nome, testo in fi.items():
        if nome.startswith("esempi_veri/"):
            sb.scrivi(nome, testo)
    verifica("…e la sandbox li scrive in esempi_veri/",
             (tmp / "sb" / "esempi_veri" / "indice.json").is_file())
    # Analisi durante il collaudo
    cfg2, reg2, ctx2, est2, svc2 = G3.ambiente(tmp / "analisi")
    est2.rete = RetePubblica(cfg2, tmp / "u2.jsonl", scarica=geocoder, log=lambda *a: 0)
    G3.apri(ctx2, est2, svc2, G5.CODICE_DOPPIA)
    P.chiama(reg2, ctx2, "sviluppo_collauda", {"argomenti": {"citta": UNA}}, turno=5)
    P.chiama(reg2, ctx2, "sviluppo_collauda", {"argomenti": {"citta": CITTA}}, turno=6)
    P.chiama(reg2, ctx2, "sviluppo_passo", {"azione": "analisi",
                                            "cambia": "deve trovare anche le città di due "
                                                      "parole"}, turno=7)
    lav2 = (svc2.offerte.get("u1") or {}).get("lavoro")
    v2 = getattr(lav2, "vincoli", "") or ""
    verifica("il lavoro che riparte dall'analisi: confronto, esempi veri nella cartella e nei "
             "vincoli", "Confronto automatico" in v2 and "esempi_veri/" in v2
             and "esempi_veri/indice.json" in (getattr(lav2, "file_iniziali", None) or {}),
             v2[-800:])
    # Solo gli ultimi collaudi tengono la risposta intera
    for i in range(SV.COLLAUDI_CON_ESEMPI + 2):
        P.chiama(reg2, ctx2, "sviluppo_collauda", {"argomenti": {"citta": UNA}}, turno=20 + i)
    sv2 = svc2.sviluppi.corrente("u1")
    con = [i for i, c in enumerate(sv2.collaudi)
           if any(r.get("esempio") for r in c.get("rete") or ())]
    verifica(f"sviluppi.json piccolo: la risposta intera solo negli ultimi "
             f"{SV.COLLAUDI_CON_ESEMPI} collaudi",
             con and min(con) >= len(sv2.collaudi) - SV.COLLAUDI_CON_ESEMPI, str(con))
    # Il prompt dell'agente
    from calliope.estensioni.prompt import SISTEMA_ESTENSIONE
    verifica("il prompt dell'agente delle estensioni nomina esempi_veri",
             "esempi_veri" in SISTEMA_ESTENSIONE)


ISO = None


def main():
    global ISO
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-diagnosi-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    ISO = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    G3.ISO = ISO
    G3.GEO.update(GEO)
    t0 = time.monotonic()
    prova_confronto()
    prova_porta()
    prova_finta(tmp0 / "finta")
    prova_sviluppo(tmp0 / "sviluppo")
    print(f"\n({time.monotonic() - t0:.1f} s)")
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
