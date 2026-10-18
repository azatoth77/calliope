"""L'agente dei giochi che gira a vuoto, a secco (18/10/2026, issue #174; area
agenti-estensioni e giochi).

Il caso vero della DGX (18/10, lavoro L1, sviluppo S32): il «tris due giocatori», 5 giri, 120
passate. Dalle 17:02 la prova di fumo era verde, restavano rossi tre test di gioco.test.js scritti
dall'agente: davano per scontato che la partita cominciasse in «turno» e non uscivano dalla fase
«preparazione» (con giocatori min = max se ne esce solo con «Inizia»). A voce, a ogni tappa,
«21 passate senza file né test nuovi», mentre l'agente i file li cambiava.

1. il contratto dice come comincia una partita (la preparazione, «Inizia» o «N giocatori»,
   apriGioco({ inizia: true })); il contrario: la frase di prima non c'è più;
2. la prova di fumo (agenti/fumo_js.mjs): un comando o un tocco nella preparazione dice la via
   d'uscita; apriGioco({ inizia: true }) parte dalla fase d'inizio; i contrari («avanti» fuori
   dall'esito com'era; senza l'opzione si parte dalla preparazione);
3. firma_errore con l'uscita vera di questo caso (righe «FALLITO …» e poi righe «ok … errore»):
   la firma è del test fallito, e due esiti diversi hanno firme diverse; prima i fallimenti in
   breve; il contrario: l'errore di Python com'era;
4. le novità nel ciclo vero (servizio dei lavori, Ollama finto): modifica_file è una novità, le
   passate senza un test verde in più si contano, la frase a voce dice quello che è successo;
5. la specifica: un gioco con requisiti che qui non si possono fare ha la specifica riscritta dai
   requisiti (niente «Python con Pygame» per l'agente); con tutti i requisiti principali
   impossibili il lavoro non parte, nemmeno con un «sì»; i contrari;
6. giri uguali: dopo due tappe con gli stessi test rossi la proposta è consegnare ciò che va o
   cambiare la richiesta, e il «sì» manda all'agente l'istruzione di consegnare; i contrari.

    python prove\\prova_agente_giri_uguali.py
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

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


def sezione(t):
    print(f"\n— {t}", flush=True)


# ═══════════════════════════ 1. il contratto ═══════════════════════════

def prova_contratto():
    sezione("1. il contratto dice come comincia una partita")
    from calliope.estensioni.contratto import scheda_testo
    t = " ".join(scheda_testo())
    verifica("ogni partita comincia nella fase «preparazione»",
             "Ogni partita comincia nella fase «preparazione»" in t)
    verifica("…si tocca «Inizia» con min = max, «N giocatori» con min < max, prima delle mosse",
             "«Inizia» se nel manifesto giocatori min = max" in t
             and "«N giocatori» se min < max" in t and "prima delle mosse" in t)
    verifica("…oppure apriGioco({ inizia: true })", "apriGioco({ inizia: true })" in t)
    verifica("contrario: non resta la frase di prima (solo «2 giocatori»)",
             "dopo g.tocca(\"2 giocatori\") si è già nella fase d'inizio" not in t)


# ═══════════════════════════ 2. la prova di fumo ═══════════════════════════

def _tris(minimo: int, massimo: int) -> dict:
    cart = RADICE / "prove" / "giochi" / "tris"
    m = json.loads((cart / "manifesto.json").read_text(encoding="utf-8"))
    m["scheda"]["giocatori"] = {"min": minimo, "max": massimo}
    return {"logica.js": (cart / "logica.js").read_text(encoding="utf-8"),
            "manifesto.json": json.dumps(m, ensure_ascii=False)}


def _esegui_js(tmp: Path, nome: str, file: dict, corpo: str) -> str:
    import prova_agente_guida as G
    sb = G.sandbox(tmp, nome)
    for k, v in {**file, "x.test.js": 'const { test } = require("node:test");\n'
                 'const assert = require("node:assert");\n' + corpo + "\n"}.items():
        sb.scrivi(k, v)
    return str(sb.test("x.test.js").get("uscita") or "")


def prova_fumo(tmp: Path):
    sezione("2. la prova di fumo dice come si esce dalla preparazione")
    if not shutil.which("node"):
        print("SALTATA IN PARTE: la sezione 2, node non c'è")
        return
    due = _tris(2, 2)
    u = _esegui_js(tmp, "comando", due, 'test("x", async () => { const g = await apriGioco('
                   '{ seme: 1 }); await g.comando("casella", 1); });')
    verifica("il caso vero: «casella 1» nella preparazione (min = max) fallisce e dice la fase",
             "FALLITO x" in u and "fase «preparazione»" in u, u[-600:])
    verifica("…e la via d'uscita: «Inizia», o apriGioco({ inizia: true }), correggere il test",
             'g.tocca("Inizia")' in u and "apriGioco({ inizia: true })" in u
             and "correggi il test, non il manifesto" in u, u[-600:])
    u = _esegui_js(tmp, "tocco", due, 'test("x", async () => { const g = await apriGioco('
                   '{ seme: 1 }); await g.tocca("Casella 1"); });')
    verifica("…anche un tocco su una casella che nella preparazione non c'è",
             "nessun elemento da toccare con «Casella 1»" in u and 'g.tocca("Inizia")' in u,
             u[-600:])
    u = _esegui_js(tmp, "quanti", _tris(1, 2), 'test("x", async () => { const g = await '
                   'apriGioco({ seme: 1 }); await g.comando("casella", 1); });')
    verifica("con min < max la via d'uscita è «N giocatori»",
             'g.tocca("2 giocatori")' in u and 'g.tocca("Inizia")' not in u, u[-600:])
    u = _esegui_js(tmp, "inizia", due, 'test("x", async () => { const g = await apriGioco('
                   '{ seme: 1, inizia: true }); assert.strictEqual(g.stato().fase, "turno"); '
                   'await g.comando("casella", 1); assert.strictEqual(g.stato().tocca, '
                   'g.stato().giocatori[1].nome); });')
    verifica("apriGioco({ inizia: true }) parte dalla fase d'inizio e si gioca subito",
             "ok x" in u and "FALLITO" not in u, u[-600:])
    u = _esegui_js(tmp, "inizia_n", _tris(1, 2), 'test("x", async () => { const g = await '
                   'apriGioco({ seme: 1, inizia: true, giocatori: 2 }); '
                   'assert.strictEqual(g.stato().fase, "turno"); '
                   'assert.strictEqual(g.stato().giocatori.length, 2); });')
    verifica("…con min < max e «giocatori: 2» sceglie due giocatori", "ok x" in u, u[-600:])
    u = _esegui_js(tmp, "senza", due, 'test("x", async () => { const g = await apriGioco('
                   '{ seme: 1 }); assert.strictEqual(g.stato().fase, "preparazione"); });')
    verifica("contrario: senza l'opzione si parte dalla preparazione, come prima",
             "ok x" in u, u[-600:])
    u = _esegui_js(tmp, "avanti", due, 'test("x", async () => { const g = await apriGioco('
                   '{ seme: 1, inizia: true }); await g.comando("avanti"); });')
    verifica("contrario: «avanti» fuori dall'esito dice la frase di prima, non la preparazione",
             "«avanti» vale solo nella fase «esito»" in u and "fase «preparazione», da cui"
             not in u, u[-600:])


# ═══════════════════════════ 3. firma_errore ═══════════════════════════

# L'uscita di esegui_test come la scrive test_js.mjs (righe «FALLITO …» e «ok …»), con i nomi dei
# test di gioco.test.js del caso vero: prima i tre rossi, poi i verdi, uno con «errore» nel nome
USCITA_A = (
    "FALLITO vince chi fa tris in riga: il comando «casella_1» adesso non è attivo (fase "
    "«preparazione», attivi: inizia) [in gioco.test.js:12]\n"
    "FALLITO pareggio con la griglia piena: il comando «casella_5» adesso non è attivo (fase "
    "«preparazione», attivi: inizia) [in gioco.test.js:30]\n"
    "FALLITO tocca all'altro dopo la mossa: il comando «casella_2» adesso non è attivo (fase "
    "«preparazione», attivi: inizia) [in gioco.test.js:41]\n"
    "ok casella occupata: errore\n"
    "ok la griglia ha nove caselle\n"
    "ok prova di fumo\n")
USCITA_B = (
    "FALLITO pareggio con la griglia piena: Expected values to be strictly equal: 'turno' !== "
    "'fine' [in gioco.test.js:33]\n"
    "ok vince chi fa tris in riga\n"
    "ok casella occupata: errore\n"
    "ok tocca all'altro dopo la mossa\n"
    "ok prova di fumo\n")


def prova_firma():
    sezione("3. firma_errore con l'uscita vera del caso")
    from calliope.agenti.ciclo import firma_errore
    a = firma_errore({"passano": False, "uscita": USCITA_A})
    b = firma_errore({"passano": False, "uscita": USCITA_B})
    verifica("la firma è del primo test fallito, mai della riga di un test passato",
             a.startswith("FALLITO vince chi fa tris in riga") and "ok casella" not in a, a)
    verifica("…due esiti diversi dei test hanno firme diverse (prima uguali: «ok casella "
             "occupata: errore»)", a != b and b.startswith("FALLITO pareggio"), f"{a!r} {b!r}")
    f = firma_errore({"passano": False, "uscita": USCITA_A,
                      "fallimenti": "vince chi fa tris in riga: il comando «casella_1» adesso "
                                    "non è attivo (in gioco.test.js:12)\npareggio: …"})
    verifica("…con i fallimenti in breve, la loro prima riga, senza numeri",
             f.startswith("vince chi fa tris in riga") and "gioco.test.js:#" in f, f)
    verifica("…solo righe «ok … errore»: nessuna firma da un test passato",
             firma_errore({"passano": False, "uscita": "ok casella occupata: errore\n"
                                                       "ok prova di fumo\n"}) == "")
    verifica("contrario: l'errore di Python com'era (l'ultima riga d'errore, senza numeri)",
             firma_errore({"passano": False, "uscita": "File x.py, line 12\nAssertionError: 3 "
                                                       "!= 5"}) == "AssertionError: # != #")
    verifica("contrario: i test che passano non hanno firma",
             firma_errore({"passano": True, "uscita": USCITA_B}) == "")


# ═══════════════════════════ 4 e 6. il ciclo vero, le tappe ═══════════════════════════

TEST_SOMMA = ("from somma import somma\n\n\ndef test_zero():\n    assert somma(0, 0) == 0\n\n\n"
              "def test_somma():\n    assert somma(2, 3) == 5\n")


def _chiama(*cc):
    return {"tool_calls": [{"name": n, "arguments": a} for n, a in cc]}


def _modifica(vecchio, nuovo):
    return _chiama(("modifica_file", {"percorso": "somma.py", "vecchio": vecchio,
                                      "nuovo": nuovo}))


ESEGUI = _chiama(("esegui_test", {}))


def prova_ciclo(tmp: Path):
    sezione("4 e 6. le novità nel ciclo vero, e i giri finiti allo stesso punto")
    from calliope.agenti import Lavori, carica
    from calliope.agenti.ciclo import CONSEGNA_DOPO_GIRI, segnali_giro
    from calliope.config import Config
    from prove.ollama_finto import FakeOllama
    fake = FakeOllama(modelli=("agente-finto",)).avvia()
    svc = None
    try:
        cfg = Config()
        cfg.agenti_url = fake.url
        cfg.agenti_modello = "agente-finto"
        cfg.agenti_risultati = str(tmp / "risultati")
        cfg.agenti_sandbox = str(tmp / "sandbox")
        cfg.agenti_sandbox_motore = "processo"
        cfg.agenti_modelli = str(tmp / "modelli")
        cfg.llm_native_url = "http://127.0.0.1:9"
        cfg.agenti_conferma = "mai"
        cfg.agenti_max_passi = 4
        cfg.agenti_accettazione = False
        svc = Lavori(cfg, carica(cfg), log=lambda *a: None)
        fake.copione = [
            # giro 1: scrive, prova, corregge con modifica_file, riprova (stesso test rosso)
            _chiama(("scrivi_file", {"percorso": "somma.py",
                                     "contenuto": "def somma(a, b):\n    return a - b\n"}),
                    ("scrivi_file", {"percorso": "test_somma.py", "contenuto": TEST_SOMMA})),
            ESEGUI, _modifica("a - b", "a * b"), ESEGUI,
            # giro 2: la stessa strada, lo stesso punto
            _modifica("a * b", "b - a"), ESEGUI, _chiama(("leggi_file", {"percorso": "somma.py"})),
            ESEGUI,
            # giro 3 (dopo il «sì» a consegnare): corregge e consegna
            _modifica("b - a", "a + b"), ESEGUI,
            _chiama(("consegna", {"riassunto": "La somma è corretta.", "esito": "fatto"}))]
        lav = svc.nuovo("codice", "Scrivi somma.py con somma(a, b) che restituisce la somma.",
                        "ada-id", "Ada", "amministra")
        lav.tappe = True
        svc.avvia(lav)
        item = svc.done.get(timeout=60)
        seg = lav.segnali
        verifica("tappa al tetto del giro 1", svc.in_tappa(lav), f"{lav.stato} {lav.risultato}")
        verifica("4. modifica_file è una novità: 1 passata senza novità (la seconda prova uguale; "
                 "prima 2)", seg.get("senza_novita") == 1, str(seg.get("senza_novita")))
        verifica("4. …e 2 passate senza un test verde in più (dopo il primo esegui_test)",
                 seg.get("senza_progressi") == 2, str(seg.get("senza_progressi")))
        s = segnali_giro(SimpleNamespace(segnali={"senza_novita": 0, "senza_progressi": 6}), 8)
        verifica("4. la frase a voce dice cosa è successo: «6 passate senza far passare test "
                 "nuovi»", "6 passate senza far passare test nuovi" in s["frasi"]
                 and s["a_vuoto"], str(s))
        s = segnali_giro(SimpleNamespace(segnali={"senza_novita": 5, "senza_progressi": 6}), 8)
        verifica("4. …e senza nessuna novità «senza cambiare i file né l'esito dei test», una "
                 "frase sola", s["frasi"] == ["5 passate senza cambiare i file né l'esito dei "
                                              "test"], str(s))
        verifica("4. contrario: «senza file né test nuovi» non si dice più",
                 not any("senza file né test nuovi" in f for f in s["frasi"]))
        s = segnali_giro(SimpleNamespace(segnali={"senza_novita": 1, "senza_progressi": 2}), 8)
        verifica("4. contrario: poche passate ferme, nessun segnale", not s["a_vuoto"], str(s))
        r = lav.risultato
        verifica("6. contrario: alla prima tappa nessun giro uguale, la domanda di sempre",
                 r.get("giri_uguali") == 1 and item["messaggio"].endswith(
                     "Continuo con un altro giro, vuoi cambiare qualcosa prima, o lo fermo?")
                 and item["in_sospeso"]["domanda"] == "Continuo?", item["messaggio"])
        frase = svc.continua(lav)
        verifica("6. contrario: il «sì» alla prima tappa è un giro come prima",
                 frase.startswith("Continuo") and "consegna_dopo_giri" not in lav.segnali, frase)
        item = svc.done.get(timeout=60)
        r = lav.risultato
        verifica("6. seconda tappa con gli stessi test rossi e lo stesso errore: due giri uguali",
                 svc.in_tappa(lav) and r.get("giri_uguali") == 2
                 and (lav.segnali.get("regole") or {}).get("agente_giri_uguali") == 1,
                 f"{r.get('giri_uguali')} {lav.segnali.get('tappe')}")
        verifica("6. …la proposta non è un altro giro uguale: consegnare ciò che va o cambiare",
                 "Due giri di fila sono finiti allo stesso punto" in item["messaggio"]
                 and item["messaggio"].endswith("Faccio consegnare all'agente quello che "
                                                "funziona già, o vuoi cambiare la richiesta?")
                 and "Continuo con un altro giro" not in item["messaggio"], item["messaggio"])
        verifica("6. …e la domanda in sospeso lo dice",
                 item["in_sospeso"]["domanda"] == "Faccio consegnare quello che funziona?",
                 str(item.get("in_sospeso")))
        frase = svc.continua(lav)
        verifica("6. il «sì»: «faccio consegnare all'agente quello che funziona già», con la "
                 "regola", frase.startswith("D'accordo: faccio consegnare all'agente")
                 and (lav.segnali.get("regole") or {}).get("agente_consegna_dopo_giri") == 1,
                 frase)
        item = svc.done.get(timeout=60)
        ultimo_giro = [m for q in fake.richieste for m in q.get("messages") or []
                       if "Hai un altro giro di lavoro" in str(m.get("content"))]
        verifica("6. …all'agente arriva l'istruzione di consegnare (dal codice, non come frase "
                 "della persona), una volta",
                 ultimo_giro and CONSEGNA_DOPO_GIRI in str(ultimo_giro[-1]["content"])
                 and "La persona ha chiesto anche" not in str(ultimo_giro[-1]["content"])
                 and "consegna_dopo_giri" not in lav.segnali, str(ultimo_giro[-1:])[:600])
        verifica("6. …e il lavoro si chiude «fatto»", lav.stato == "fatto", lav.stato)
    finally:
        if svc is not None:
            svc.close()
        fake.ferma()

    from calliope.agenti.ciclo import giri_uguali
    seg = {}
    rosso = {"passano": False, "esito": {"eseguiti": 5, "falliti": 3}, "uscita": USCITA_A}
    n = [giri_uguali(seg, rosso), giri_uguali(seg, rosso)]
    verifica("6. giri_uguali: due tappe con 3 rossi su 5 e lo stesso errore → 1, 2", n == [1, 2],
             str(n))
    n = giri_uguali(seg, {"passano": False, "esito": {"eseguiti": 5, "falliti": 1},
                          "uscita": USCITA_B})
    verifica("6. contrario: un rosso in meno alla tappa dopo → 1", n == 1, str(n))
    verifica("6. contrario: con i test verdi o senza test → 0",
             giri_uguali({}, {"passano": True, "esito": {"eseguiti": 5, "falliti": 0}}) == 0
             and giri_uguali({}, None) == 0)


# ═══════════════════════════ 5. la specifica ═══════════════════════════

class _Lav(SimpleNamespace):
    pass


def prova_specifica(tmp: Path):
    sezione("5. la specifica dopo il cambio di strada, e il lavoro che non parte")
    import calliope.requisiti as rq
    from calliope.config import Config
    from calliope.sviluppo import DOMANDA_NON_SI_PARTE, DOMANDA_PROPOSTA, Sviluppi
    from calliope.tools import agenti as ta
    cfg = Config()
    svs = Sviluppi(cfg, tmp / "sviluppi", None, log=lambda *a: None)
    spec_vera = ("Il tris per due giocatori. Il linguaggio deve essere Python con la libreria "
                 "Pygame, con una finestra sul desktop.")

    def req(testo, nucleo, si_puo, limite=""):
        return {"testo": testo, "dettaglio": "", "nucleo": nucleo, "si_puo": si_puo,
                "limite": limite}
    alcuni = [req("griglia tre per tre", True, True), req("due giocatori a turno", True, True),
              req("chi fa tris vince", True, True),
              req("scritto in Python con Pygame", False, False,
                  "qui un gioco gira nel browser degli schermi")]
    tutti_no = [req("tris in Python con Pygame", True, False, "qui niente Pygame"),
                req("finestra sul desktop", True, False, "niente finestre"),
                req("suoni", False, True)]
    vero = rq.estrai

    def lavoro(gioco=True):
        return _Lav(id="L9", specifica=spec_vera, compito=spec_vera, titolo="Tris due giocatori",
                    gioco=gioco, scelte=[], cambiamento=None, vincoli="", file_utente=None)
    try:
        rq.estrai = lambda *a, **k: ([dict(r) for r in alcuni], "piccolo", "modello")
        sv = svs.apri("ada-id", "Ada", "estensione", spec_vera, titolo="Tris due giocatori",
                      gioco=True)
        sv.specifica = spec_vera
        lav = lavoro()
        frase = svs.frase_proposta(sv, lav)
        verifica("un gioco con un requisito che qui non si può fare: la specifica per l'agente "
                 "è riscritta dai requisiti", "Pygame" not in lav.compito.split("Qui non si può")[0]
                 and "griglia tre per tre" in lav.compito and lav.compito == lav.specifica
                 == sv.specifica, lav.compito)
        verifica("…ciò che non si può fare resta detto a parte, come da non fare",
                 "Qui non si può fare, quindi non va fatto: scritto in Python con Pygame"
                 in lav.compito, lav.compito)
        verifica("…si parte come sempre (la domanda di sempre)",
                 frase.endswith(DOMANDA_PROPOSTA) and not lav.non_si_parte, frase)
        # contrario: un programma (non un gioco) con lo stesso limite tiene la sua specifica
        sv2 = svs.apri("bruno-id", "Bruno", "programma", spec_vera, titolo="Tris")
        sv2.specifica = spec_vera
        lav2 = lavoro(gioco=False)
        svs.frase_proposta(sv2, lav2)
        verifica("contrario: non un gioco, la specifica resta com'era", lav2.compito == spec_vera,
                 lav2.compito)
        # tutti i requisiti principali impossibili: non si parte
        rq.estrai = lambda *a, **k: ([dict(r) for r in tutti_no], "piccolo", "modello")
        sv3 = svs.apri("carla-id", "Carla", "estensione", spec_vera, titolo="Tris finestra",
                       gioco=True)
        sv3.specifica = spec_vera
        lav3 = lavoro()
        frase = svs.frase_proposta(sv3, lav3)
        verifica("tutti i requisiti principali qui non si possono fare: la proposta non chiede "
                 "«Va bene così?» ma cosa cambiare", frase.endswith(DOMANDA_NON_SI_PARTE)
                 and "Oggi qui non si possono fare" in frase and lav3.non_si_parte, frase)
        avviati = []
        svc = SimpleNamespace(avvia=lambda l: avviati.append(l) or "partito",
                              sviluppi=svs)
        ctx = SimpleNamespace(regole=[], schermi=None, cfg=cfg)
        out = ta._avvia(ctx, svc, lav3)
        verifica("…e il «sì» non lo avvia: niente lavoro, la regola, la domanda su cosa cambiare",
                 not avviati and out.get("ok") is False
                 and "sviluppo_nucleo_impossibile" in ctx.regole
                 and (out.get("in_sospeso") or {}).get("tool") == "sviluppo_passo",
                 json.dumps(out, ensure_ascii=False, default=str)[:400])
        lav4 = lavoro()
        lav4.non_si_parte = ""
        ta._schermo = lambda *a, **k: None
        try:
            ta._avvia(ctx, svc, lav4)
        except Exception:  # noqa: BLE001 — su_avvio senza il servizio vero
            pass
        verifica("contrario: un lavoro senza il blocco parte", avviati == [lav4], str(avviati))
    finally:
        rq.estrai = vero


def main():
    tmp = Path(tempfile.mkdtemp(prefix="calliope-giri-uguali-"))
    os.environ.setdefault("CALLIOPE_CONFIG_LOCALE", str(tmp / "nessuno.yaml"))
    try:
        prova_contratto()
        prova_fumo(tmp / "fumo")
        prova_firma()
        prova_ciclo(tmp / "ciclo")
        prova_specifica(tmp / "specifica")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
