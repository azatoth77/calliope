"""Il contratto e la partenza dell'agente dei giochi, a secco (19/10/2026, issue #186; area
agenti-estensioni e giochi; § 3.5 della ricerca del 19/10 sulla solidità dell'agente).

Prima del 19/10 un gioco partiva da una cartella vuota e l'agente ricopiava dal prompt
manifesto, logica e test (la parte rotta nel tris per due del 18/10, #174); il prompt prometteva
un «vincitore» che g.stato() non ha; { esito, fase: "fine" } perdeva l'esito e «dopo» senza esito
era ignorato, senza errore; il 45 % del prompt di un gioco era delle estensioni Python.

1. la partenza: i quattro file generati dal codice per min = max (1, 2) e min < max (1–4, 2–4,
   3–8) passano i test e la prova di fumo per fasi; «Inizia» con min = max, «N giocatori» con
   min < max; il nome del titolo del lavoro, il segnaposto che la consegna rifiuta; contrari:
   un titolo che il controllo dei testi non accetta, un manifesto che c'è già (modifica,
   correzione, ripresa), giocatori non validi → quelli di serie;
2. l'analisi prima del codice dice quanti giocano (min e max) e toglie gli esempi fuori;
   contrari: giocatori non validi, niente da togliere;
3. gli errori nuovi del motore: { esito, fase } e { dopo } senza esito, con cosa fare; contrari:
   { esito, dopo }, { fase }, { esito, fase: "esito" }, { dati }; la prova di fumo li trova e dice
   «esito con dopo: "fine", oppure fase: "fine"»;
4. il contratto: g.stato() esatto (comandi un oggetto, niente vincitore), «Inizia» anche con
   min < max, turni di serie, il caso; sezioni in ordine; urllib.parse sì, la rete diretta no;
5. un prompt per tipo: il gioco senza le regole delle estensioni Python né i loro strumenti,
   l'estensione senza il gioco e con la regola contro le istruzioni nei dati; i caratteri;
6. nel servizio dei lavori (Ollama finto): un gioco nuovo riceve la partenza con min e max
   dell'analisi, senza esegui_python né scarica_esempio; contrari: senza l'analisi i giocatori
   di serie; un'estensione Python li ha.

    python prove\\prova_partenza_gioco.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

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


def _sandbox(tmp: Path, nome: str):
    import prova_agente_guida as G
    return G.sandbox(tmp, nome)


# ═══════════════════════════ 1. la partenza ═══════════════════════════

def prova_partenza(tmp: Path):
    sezione("1. i file di partenza di un gioco nuovo, verdi per costruzione")
    from calliope.agenti.scheletri import (GIOCATORI_PARTENZA, NOME_PARTENZA, file_gioco,
                                           giocatori_partenza, prepara_gioco)
    from calliope.estensioni.manifesto import valida
    from calliope.estensioni.prompt import controlla_consegna
    for gmin, gmax in ((1, 1), (2, 2), (1, 4), (2, 4), (3, 8)):
        f = file_gioco(gmin, gmax)
        m = valida(json.loads(f["manifesto.json"]))
        g = m["scheda"]["giocatori"]
        apre = "Inizia" if gmin == gmax else f"{max(2, gmin)} giocatori"
        verifica(f"{gmin}–{gmax}: manifesto valido con i giocatori della richiesta, gioco.test.js "
                 f"apre con «{apre}»", g == {"min": gmin, "max": gmax}
                 and f'g.tocca("{apre}")' in f["gioco.test.js"], json.dumps(g))
        if not shutil.which("node"):
            continue
        sb = _sandbox(tmp, f"partenza-{gmin}-{gmax}")
        scritti = prepara_gioco(sb, {"min": gmin, "max": gmax})
        r = sb.test()
        verifica(f"{gmin}–{gmax}: i test e la prova di fumo per fasi passano sulla partenza",
                 sorted(scritti) == sorted(f) and r["passano"] and r["esito"]["eseguiti"] == 6
                 and "ok prova di fumo del gioco" in r["uscita"],
                 str(r["esito"]) + r["uscita"][-600:])
        e = str(controlla_consegna(sb))
        verifica(f"{gmin}–{gmax}: la consegna rifiuta la partenza d'esempio non cambiata",
                 "gioco d'esempio delle porte" in e, e)
        sb.scrivi("logica.js", sb.leggi("logica.js", 100_000).replace("Quale porta apri?",
                                                                     "Quale porta?"))
        verifica(f"{gmin}–{gmax}: …e con la logica cambiata chiede un nome suo (il segnaposto)",
                 NOME_PARTENZA in str(controlla_consegna(sb)), str(controlla_consegna(sb)))
    if not shutil.which("node"):
        print("SALTATA IN PARTE: node non c'è")
    f = file_gioco(2, 2, "Il tris per due")
    m = json.loads(f["manifesto.json"])
    verifica("il nome e il titolo dal titolo del lavoro", m["nome"] == "il_tris_per_due"
             and m["titolo"] == "Il tris per due", f"{m['nome']} {m['titolo']}")
    f = file_gioco(2, 2, "Il tris per due", presi=("il_tris_per_due",))
    verifica("contrario: un nome già preso → il segnaposto",
             json.loads(f["manifesto.json"])["nome"] == NOME_PARTENZA)
    f = file_gioco(2, 2, "Quando ti pare")
    m = json.loads(f["manifesto.json"])
    verifica("contrario: un titolo che il controllo dei testi non accetta → il segnaposto",
             m["nome"] == NOME_PARTENZA and m["titolo"] != "Quando ti pare", m["titolo"])
    # Nomi e titoli tagliati a parola intera, con le cifre, senza simboli (20/10, revisione
    # della PR #188)
    casi = {"un gioco del memory con le carte di Halloween per tutta la famiglia":
            ("un_gioco_del_memory", "un gioco del memory con le carte"),
            "Tic-tac-toe 3x3": ("tic_tac_toe_3x3", "Tic tac toe 3x3"),
            "quiz sulle capitali d'Europa con 10 domande":
            ("quiz_sulle_capitali_d_europa", "quiz sulle capitali d'Europa con 10"),
            "Tris 3×3": ("tris_3_3", "Tris 3 3"), "3 in fila": ("gioco_3_in_fila", "3 in fila")}
    sbagliati = []
    for t, atteso in casi.items():
        m = json.loads(file_gioco(1, 1, t)["manifesto.json"])
        if (m["nome"], m["titolo"]) != atteso:
            sbagliati.append((t, m["nome"], m["titolo"]))
    verifica("nome e titolo a parola intera, con le cifre, senza × né trattini", not sbagliati,
             str(sbagliati))
    if shutil.which("node"):
        sb = _sandbox(tmp, "partenza-titolo")
        prepara_gioco(sb, {"min": 2, "max": 2}, "Il tris per due")
        # La revisione della PR #188: prima questa partenza, con un nome suo, si consegnava
        # così com'era (le porte col nome del tris, fuori da uno sviluppo)
        e = str(controlla_consegna(sb))
        verifica("la partenza d'esempio non cambiata non si consegna, nemmeno con un nome suo",
                 "gioco d'esempio delle porte" in e and "da sostituire" in e, e)
        logica = sb.leggi("logica.js", 100_000).replace("Quale porta apri?", "Quale casella?")
        sb.scrivi("logica.js", logica)
        verifica("contrario: con logica.js cambiato la consegna va", controlla_consegna(sb) is None,
                 str(controlla_consegna(sb)))
        verifica("contrario: con il nome già preso no",
                 "già di un'altra" in str(controlla_consegna(sb, nomi_presi=("il_tris_per_due",))))
        sb2 = _sandbox(tmp, "partenza-modifica-porte")
        prepara_gioco(sb2, {"min": 2, "max": 2}, "Il tris per due")
        verifica("contrario: la modifica di un gioco con quella logica (nome atteso) non è "
                 "fermata da questo controllo",
                 controlla_consegna(sb2, nome_atteso="il_tris_per_due") is None,
                 str(controlla_consegna(sb2, nome_atteso="il_tris_per_due")))
    sb = _sandbox(tmp, "partenza-modifica")
    sb.scrivi("manifesto.json", '{"nome": "tris"}')
    verifica("contrario: con un manifesto (modifica, correzione, ripresa) nessun file",
             prepara_gioco(sb, {"min": 2, "max": 2}) == []
             and sb.leggi("manifesto.json", 100) == '{"nome": "tris"}')
    for cattivi in (None, {}, {"min": 3, "max": 2}, {"min": 0, "max": 2}, {"min": 1, "max": 9},
                    {"min": True, "max": 2}, {"min": "2", "max": "2"}):
        if giocatori_partenza(cattivi) != GIOCATORI_PARTENZA:
            verifica(f"contrario: giocatori {cattivi} → quelli di serie", False)
            break
    else:
        verifica("contrari: giocatori mancanti o non validi → quelli di serie "
                 f"{GIOCATORI_PARTENZA}", True)
    verifica("giocatori validi dall'analisi", giocatori_partenza({"min": 2, "max": 2}) == (2, 2))


# ═══════════════════════════ 2. l'analisi ═══════════════════════════

def prova_analisi():
    sezione("2. l'analisi prima del codice dice quanti giocano")
    from calliope.agenti import accettazione as A
    s = A.schema(False, gioco=True)
    verifica("lo schema del gioco chiede giocatori min e max", "giocatori" in s["required"]
             and s["properties"]["giocatori"]["required"] == ["min", "max"])
    verifica("…e il prompt lo spiega", "giocatori: quanti possono giocare" in A.SISTEMA_GIOCO)

    def es(g):
        return {"requisito": 1, "giocatori": g, "mosse": [{"comando": "casella", "valore": 1}],
                "atteso": {"tocca": 2 if g > 1 else 1}}
    dati = {"comandi": [{"fase": "turno", "nome": "casella", "da": 1, "a": 9}],
            "esempi": [es(2), es(3)], "giocatori": {"min": 2, "max": 2}}
    an = A.interpreta(dati, 3, estensione=False, gioco=True)
    verifica("min e max validati; l'esempio con 3 giocatori in un gioco per due si toglie",
             an["giocatori"] == {"min": 2, "max": 2}
             and [e["giocatori"] for e in an["esempi"]] == [2]
             and an["tolti"] == {"giocatori": 1}, json.dumps(an)[:300])
    an = A.interpreta({**dati, "esempi": [es(3), es(4)]}, 3, estensione=False, gioco=True)
    verifica("tutti fuori: min e max non si tengono, gli esempi restano (contati in tolti)",
             an["giocatori"] is None and len(an["esempi"]) == 2
             and an["tolti"] == {"giocatori_scartati": 1}, json.dumps(an)[:300])
    an = A.interpreta({**dati, "giocatori": {"min": 3, "max": 1}}, 3, estensione=False, gioco=True)
    verifica("contrario: giocatori non validi → None, gli esempi restano",
             an["giocatori"] is None and len(an["esempi"]) == 2)
    an = A.interpreta({**dati, "giocatori": {"min": 1, "max": 4}}, 3, estensione=False, gioco=True)
    verifica("contrario: nessun esempio fuori, niente da togliere", len(an["esempi"]) == 2)


# ═══════════════════════════ 3. il motore ═══════════════════════════

MANIFESTO = {"nome": "porte_prova", "titolo": "Porte di prova",
             "cosa_fa": {"verbo": "propone", "oggetto": "una partita sullo schermo"},
             "permessi": {},
             "scheda": {"tipo": "gioco", "file": ["logica.js"], "giocatori": {"min": 1, "max": 1},
                        "macchina": {"inizio": "turno", "fasi": {"turno": {
                            "pagina": "scelte", "verso": ["esito", "fine"],
                            "comandi": {"porta": {"forme": ["porta {n}"], "n": {"da": 1, "a": 3},
                                                  "etichetta": "Porta {n}"}}}}}}}


def _logica(ritorno: str) -> str:
    return ("const GIOCO = {\n"
            "  nuovaPartita() { return { mosse: 0 }; },\n"
            "  mosse: { turno: { porta(d, { valore }) {\n"
            "    const n = d.mosse + 1;\n"
            f"    return {ritorno};\n"
            "  } } },\n"
            "  vista: { turno: (d) => ({ titolo: \"Quale porta?\" }) },\n"
            "};\n"
            "if (typeof module !== \"undefined\") module.exports = { GIOCO };\n")


TEST_UNA_MOSSA = """const { test } = require("node:test");
const assert = require("node:assert");
test("una mossa", async () => {
  const g = await apriGioco({ seme: 1, inizia: true });
  await g.comando("porta", 1);
  const s = g.stato();
  console.log("STATO " + JSON.stringify({ fase: s.fase, esito: s.esito }));
});
"""


def prova_motore(tmp: Path):
    sezione("3. gli errori nuovi del motore e la prova di fumo")
    if not shutil.which("node"):
        print("SALTATA IN PARTE: node non c'è")
        return

    def gioca(nome, ritorno):
        sb = _sandbox(tmp, nome)
        sb.scrivi("manifesto.json", json.dumps(MANIFESTO))
        sb.scrivi("logica.js", _logica(ritorno))
        sb.scrivi("gioco.test.js", TEST_UNA_MOSSA)
        return sb.test()

    r = gioca("esito-fase", '{ dati: { mosse: n }, esito: "Aperta!", fase: "fine" }')
    u = r["uscita"]
    verifica("{ esito, fase: \"fine\" }: errore con fase e comando, e cosa fare",
             not r["passano"] and "GIOCO.mosse.turno.porta" in u
             and "«esito» con «fase»" in u and 'dopo: \\"fine\\"' in u.replace('dopo: "fine"',
                                                                              'dopo: \\"fine\\"'),
             u[-700:])
    r = gioca("dopo-solo", '{ dati: { mosse: n }, dopo: "fine" }')
    u = r["uscita"]
    verifica("{ dopo: \"fine\" } senza esito: errore che dice { fase: \"fine\" }",
             not r["passano"] and "senza «esito» non fa niente" in u and 'fase: "fine"' in u,
             u[-700:])
    r = gioca("esito-vuoto", '{ dati: { mosse: n }, esito: "", dopo: "fine" }')
    verifica("{ esito: \"\", dopo } è come senza esito: errore",
             not r["passano"] and "senza «esito» non fa niente" in r["uscita"], r["uscita"][-400:])
    for nome, ritorno, fase in (
            ("esito-dopo", '{ dati: { mosse: n }, esito: "Aperta!", dopo: "fine" }', "esito"),
            ("solo-fase", '{ dati: { mosse: n }, fase: "fine" }', "fine"),
            ("esito-fase-esito", '{ dati: { mosse: n }, esito: "Aperta!", fase: "esito", '
                                 'dopo: "fine" }', "esito")):
        r = gioca(nome, ritorno)
        verifica(f"contrario: {ritorno[22:].rstrip(' }')} va (fase «{fase}»), anche la prova "
                 "di fumo", r["passano"] and f'"fase":"{fase}"' in r["uscita"],
                 r["uscita"][-500:])
    r = gioca("resta", '{ dati: { mosse: n } }')
    verifica("contrario: { dati } resta nella fase (la prova di fumo dice che non finisce)",
             '"fase":"turno"' in r["uscita"] and "non arriva alla fine" in r["uscita"]
             and 'esito con dopo: "fine", oppure fase: "fine" senza esito' in r["uscita"],
             r["uscita"][-600:])


# ═══════════════════════════ 4. il contratto ═══════════════════════════

def prova_contratto():
    sezione("4. il contratto del gioco e quello dell'estensione")
    from calliope.config import Config
    from calliope.estensioni import contratto as ct
    tg, te = ct.testo(Config(), "gioco"), ct.testo(Config(), "estensione")
    verifica("g.stato() con la forma esatta: comandi un oggetto, niente vincitore",
             "{ n, fase, tocca, turno, giocatori: [{ nome, punti }], esito, comandi }" in tg
             and "comandi un OGGETTO" in tg and "Non c'è il vincitore" in tg)
    verifica("«Inizia» c'è anche con min < max e parte con min giocatori",
             "«Inizia» c'è sempre e parte con min giocatori" in tg)
    verifica("turni vero di serie, il caso con il seme", "turni (di serie true" in tg
             and "Math.random() in logica.js va bene" in tg and "apriGioco({ seme: 7 })" in tg)
    verifica("le tre forme di una mossa e i due errori",
             "in una di tre forme" in tg and "«esito» insieme a «fase»" in tg)

    def sezioni(t):
        return [r.split(".")[0][3:] for r in t.splitlines() if r.startswith("## ")]
    verifica("sezioni in ordine (gioco 1–4, estensione 1–4)",
             sezioni(tg) == ["1", "2", "3", "4"] and sezioni(te) == ["1", "2", "3", "4"],
             f"{sezioni(tg)} {sezioni(te)}")
    verifica("il gioco senza la porta Python né i limiti del contenitore",
             "calliope.rete_leggi(" not in tg and "limiti.tempo_s" not in tg
             and "urlencode" not in tg and "## 2. La scheda" in tg)
    # 20/10 (revisione della PR #188): i residui Python degli impossibili
    verifica("gli impossibili del gioco senza pip, libreria standard, porta stretta, «dentro "
             "l'estensione» né la voce sulle pagine in JavaScript",
             all(x not in tg for x in ("(pip)", "libreria standard", "porta stretta",
                                       "dentro l'estensione", "- javascript:"))
             and "- javascript:" in te and "(pip)" in te)
    voci_g = [r for r in tg.splitlines() if r.startswith("Voci per piano")][0]
    voci_e = [r for r in te.splitlines() if r.startswith("Voci per piano")][0]
    verifica("…e «javascript» fuori dalle voci del piano del gioco (in quelle dell'estensione no)",
             " javascript" not in voci_g and " javascript," in voci_e, voci_g)
    verifica("l'estensione senza il contratto del gioco; un gioco chiesto qui → piano("
             "fattibile=false), non un tool della voce",
             "macchina a stati" not in te.lower() and "sviluppo_apri" not in te
             and "«è un gioco: va chiesto come gioco»" in te)
    verifica("urllib.parse sì, la rete diretta no (prima «urllib: vietati»)",
             "urllib: vietati" not in te and "urllib.parse per scrivere gli indirizzi sì" in te
             and "urllib.request" in te)
    from calliope.estensioni.analisi import analizza
    a = analizza({"estensione.py": "import urllib.parse\nimport urllib.request\n"})
    cose = [x["cosa"] for x in a["rischi"]]
    verifica("l'analisi statica non segna urllib.parse; urllib.request sì",
             cose == ["import urllib.request"], str(cose))


# ═══════════════════════════ 5. i prompt ═══════════════════════════

def prova_prompt():
    sezione("5. un prompt per tipo")
    from calliope.agenti.ciclo import ANTI_INIEZIONE
    from calliope.config import Config
    from calliope.estensioni.prompt import SISTEMA_ESTENSIONE, SISTEMA_GIOCO, sistema_estensione
    pg, pe = sistema_estensione(Config(), gioco=True), sistema_estensione(Config())
    print(f"   caratteri: gioco {len(pg)} (prima 26 437), estensione {len(pe)} (prima 17 068)")
    verifica("il gioco senza le regole delle estensioni Python",
             all(x not in pg for x in ("test_estensione.py", "urlencode", "scarica_esempio",
                                       "esegui_python", "BeautifulSoup", "SE È UN GIOCO")),
             str([x for x in ("test_estensione.py", "urlencode", "scarica_esempio",
                              "esegui_python", "BeautifulSoup") if x in pg]))
    verifica("…e senza il vincitore promesso (prima «punti, esito e vincitore»)",
             "esito e vincitore" not in pg)
    verifica("l'estensione senza il gioco", "SE È UN GIOCO" not in pe
             and "accettazione.test.js" not in pe and "LA PARTENZA (gioco)" not in pe)
    verifica("la regola contro le istruzioni nei dati in fondo a tutti e due (l'estensione ha "
             "scarica_esempio)", pe.endswith(ANTI_INIEZIONE.strip())
             and pg.endswith(ANTI_INIEZIONE.strip()))
    verifica("la codifica degli indirizzi una volta sola nel prompt dell'estensione",
             pe.count("urlencode (o quote") == 1 and "urlencode" not in SISTEMA_ESTENSIONE)
    verifica("gli strumenti detti nel prompt del gioco: esegui_js, niente esegui_python",
             "esegui_js" in SISTEMA_GIOCO and "esegui_python" not in SISTEMA_GIOCO)
    verifica("più corto: il gioco sotto i 18 000 caratteri, l'estensione sotto i 17 068",
             len(pg) < 18000 and len(pe) < 17068, f"{len(pg)} {len(pe)}")


# ═══════════════════════════ 6. nel servizio ═══════════════════════════

def prova_servizio(tmp: Path):
    sezione("6. nel servizio dei lavori: la partenza e gli strumenti del gioco")
    if not shutil.which("node"):
        print("SALTATA IN PARTE: node non c'è")
        return
    from calliope.agenti import Lavori, carica
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
        cfg.agenti_max_passi = 3
        cfg.agenti_accettazione = False
        righe = []
        svc = Lavori(cfg, carica(cfg), log=righe.append)

        def lavoro(gioco, giocatori=None):
            fake.richieste.clear()
            fake.copione = [{"tool_calls": [{"name": "piano", "arguments": {
                "capacita_necessarie": ["scheda" if gioco else "calcolo"], "scope": {},
                "fattibile": True, "motivo": "prova"}}]},
                {"tool_calls": [{"name": "elenca_file", "arguments": {}},
                                {"name": "esegui_python", "arguments": {"percorso": "x.py"}}]}]
            lav = svc.nuovo("estensione", "Il tris per due giocatori sugli schermi.", "ada-id",
                            "Ada", "amministra")
            lav.gioco = gioco
            if giocatori:
                # Come l'analisi prima del codice di uno sviluppo (qui spenta)
                lav.accettazione = {"stato": "saltata", "giocatori": giocatori}
            svc.avvia(lav)
            svc.done.get(timeout=90)
            nomi = {t["function"]["name"] for r in fake.richieste for t in r.get("tools") or ()}
            sb_root = next((Path(cfg.agenti_sandbox).glob(f"{lav.id}-*")), None)
            m = (json.loads((sb_root / "manifesto.json").read_text(encoding="utf-8"))
                 if sb_root and (sb_root / "manifesto.json").is_file() else None)
            # Gli esiti degli strumenti che l'agente ha visto (l'ultima richiesta)
            esiti = " ".join(str(x.get("content")) for x in (fake.richieste[-1].get("messages")
                                                            if fake.richieste else [])
                             if x.get("role") == "tool")
            return lav, nomi, m, sb_root, esiti
        lav, nomi, m, root, esiti = lavoro(True, {"min": 2, "max": 2})
        verifica("un gioco nuovo: la partenza con min e max dell'analisi (2–2)",
                 m is not None and m["scheda"]["giocatori"] == {"min": 2, "max": 2}
                 and (root / "gioco.test.js").is_file()
                 and 'g.tocca("Inizia")' in (root / "gioco.test.js").read_text(encoding="utf-8"),
                 str(m and m.get("scheda", {}).get("giocatori")))
        verifica("…detto nel registro", any("cartella di partenza" in r and "da 2 a 2" in r
                                            for r in righe), str(righe[-6:]))
        verifica("…senza esegui_python né scarica_esempio, con esegui_test e consegna",
                 nomi and "esegui_python" not in nomi and "scarica_esempio" not in nomi
                 and {"esegui_test", "consegna", "piano"} <= nomi, str(sorted(nomi)))
        # 20/10 (revisione della PR #188): chiamato lo stesso, non si esegue
        verifica("…ed esegui_python chiamato lo stesso non parte: «non è disponibile», con gli "
                 "strumenti offerti", "«esegui_python» non è disponibile in questo lavoro"
                 in esiti and "senza Python né rete" in esiti and "\"esegui_test\"" in esiti,
                 esiti[-400:])
        lav, nomi, m, root, esiti = lavoro(True)
        verifica("contrario: senza l'analisi i giocatori di serie (1–4), «2 giocatori»",
                 m is not None and m["scheda"]["giocatori"] == {"min": 1, "max": 4}
                 and 'g.tocca("2 giocatori")' in (root / "gioco.test.js").read_text(
                     encoding="utf-8"), str(m and m.get("scheda")))
        lav, nomi, m, root, esiti = lavoro(False)
        verifica("contrario: un'estensione Python ha esegui_python e scarica_esempio, e niente "
                 "partenza del gioco", "esegui_python" in nomi and "scarica_esempio" in nomi
                 and root is not None and not (root / "logica.js").exists()
                 and "scheda" not in (m or {}) and (root / "test_estensione.py").is_file(),
                 f"{sorted(nomi)} {m} {root} "
                 f"{sorted(p.name for p in root.iterdir()) if root else ''}")
        # Il piano di un gioco (20/10, seconda revisione della PR #188): «javascript» chiudeva
        # il gioco come impossibile («un'estensione non può leggere dati che una pagina mostra
        # solo con JavaScript»), e «pacchetti» diceva pip
        def piano(gioco, caps):
            lv = svc.nuovo("estensione", "Il tris per due.", "ada-id", "Ada", "amministra")
            lv.gioco = gioco
            sb = _sandbox(tmp, f"piano-{lv.id}")
            return svc.agente._piano(lv, sb, {"capacita_necessarie": caps, "scope": {},
                                              "fattibile": True, "motivo": "prova"}, None)
        out, chiusura = piano(True, ["scheda", "javascript"])
        verifica("il piano di un gioco con «javascript» va avanti (la voce si ignora)",
                 chiusura is None and out.get("ok") is True, f"{out} {chiusura}")
        out, chiusura = piano(True, ["scheda", "pacchetti"])
        frase = str((chiusura or {}).get("riassunto"))
        verifica("…«pacchetti» in un gioco: impossibile, detto per un gioco (niente pip)",
                 (chiusura or {}).get("esito") == "impossibile"
                 and "un gioco non può installare librerie" in frase and "pip" not in frase,
                 frase)
        out, chiusura = piano(False, ["javascript"])
        verifica("contrario: in un'estensione «javascript» resta impossibile, con la sua frase",
                 (chiusura or {}).get("esito") == "impossibile"
                 and "un'estensione non può" in str(chiusura.get("riassunto")), str(chiusura))
    finally:
        if svc is not None:
            svc.chiudi() if hasattr(svc, "chiudi") else None
        fake.ferma()


def main():
    tmp = Path(tempfile.mkdtemp(prefix="calliope-partenza-gioco-"))
    try:
        prova_partenza(tmp / "partenza")
        prova_analisi()
        prova_motore(tmp / "motore")
        prova_contratto()
        prova_prompt()
        prova_servizio(tmp / "servizio")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + ("TUTTO OK" if not errori else f"{errori} ERRORI"))
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
