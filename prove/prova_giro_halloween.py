"""
Il giro vero della DGX dell'11/10/2026 (15:37–16:27, satellite «studio»), riscritto con nomi di
fantasia: lo sviluppo di un gioco di Halloween con le porte. Sei correzioni, a secco (~3 s):

1. **Il collaudo di un gioco è vederlo.** Alla consegna «Con cosa provo?» e a «fammelo vedere e
   fallo girare» `sviluppo_collauda` rispondeva «Un gioco si prova sullo schermo dopo
   l'approvazione: qui non lo eseguo.», e Dario ha approvato senza averlo visto. Ora l'annuncio
   dice che è un gioco e chiede «Lo apro in prova?»; `sviluppo_collauda` apre la versione
   candidata sullo schermo da cui si parla, scheda di gioco con `"prova": true`, nella stessa
   sandbox degli schermi (riquadro, CSP) e senza ponte verso Calliope (salva, leggi, manda,
   chat, di, azione rifiutati); non diventa attiva né un tool est_. Contrari: un'estensione che
   non è un gioco chiede ancora «Con cosa provo?»; dopo l'approvazione o con i file cambiati il
   documento di prova non c'è più; una partita vera non si unisce a quella di prova; una
   familiare non collauda.
2. **sviluppo_correggi su uno sviluppo fermo senza versione** («Qui le estensioni non ci
   sono.», due volte): diventa il lavoro rifatto con il problema detto, il motivo dell'arresto e i
   file già scritti (regola `sviluppo_correggi_rifai`). Contrari: con l'agente al lavoro, in
   analisi, senza sviluppo.
3. **L'avviso di tappa con un conteggio solo** («Finora 21 test su 22 passano. I test passano,
   22 su 22.»). Contrari: test che non passano, nessun test rifatto.
4. **Perché si è fermato**: il motivo dell'arresto deciso da Calliope nel contesto di
   `sviluppo_chiedi` e nel suo esito (`motivo`). Contrari: al collaudo niente motivo; fermato
   dalla persona; tappa.
5. **Il titolo non finisce con «sugli»**. Contrari: i titoli buoni di prima.
6. **Il titolo di un proprio sviluppo è un bersaglio fidato** (`quale` di sviluppo_passo).
   Contrari: lo sviluppo di un'altra persona, un titolo che non è di nessuno sviluppo, le stesse
   parole in un altro tool.

    python prove\\prova_giro_halloween.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


def detta(out) -> str:
    return str((out or {}).get("risposta_finale") or (out or {}).get("conferma") or "")


# Il titolo e il motivo del giro vero
TITOLO = "videogioco a tema Halloween da giocare"
COMPITO = ("Crea un videogioco a tema Halloween da giocare sugli schermi di casa. Il gioco deve "
           "avere un'atmosfera spaventosa ma divertente per bambini, con una musica cupa ma "
           "giocosa.")
MOTIVO = ("ho dovuto fermarlo: ha ripetuto lo stesso ragionamento in 3 passate di fila senza "
          "decidere")
PROBLEMA = ("Correggere la funzione generaPorte in modo che crei il numero corretto di porte in "
            "base al numero di giocatori e al round corrente.")


class AgenteFinto:
    """Il cliente del modello dell'agente per sviluppo_chiedi: registra e risponde a copione."""

    def __init__(self, risposta):
        self.richieste, self.risposta = [], risposta

    def chat(self, body, **_):
        self.richieste.append(body)
        return {"content": json.dumps(self.risposta, ensure_ascii=False)}

    def interrompi(self, *a):
        pass


def ambiente(tmp: Path):
    """Estensioni, hub degli schermi vero, giochi (prova_giochi) e il servizio dei lavori finto
    con gli sviluppi veri (prova_sviluppo); lo schermo dello studio."""
    import prova_giochi as G
    import prova_sviluppo as S
    from calliope.tools import sviluppo as ts
    a = G.Ambiente(tmp)
    for s in ts.sviluppo_specs():
        a.tools.register(s)
    svc = S.Lavori(a.cfg, tmp / "lavori")
    svc.estensioni = a.est
    svc.cfg = a.cfg
    svc.imp = SimpleNamespace(modello="agente-finto")
    svc.cliente = AgenteFinto({"voce": "C'è un errore nel codice che genera le porte.",
                               "dettagli": "generaPorte usa il numero dei giocatori.",
                               "serve_correzione": True,
                               "cosa_correggere": "il numero delle porte"})
    a.est.sviluppi = svc.sviluppi
    a.ctx.lavori = svc
    studio = a.abbina("studio", "studio")
    a.chi("Dario", "voce", studio)
    return a, svc, studio


def gioco_in_sviluppo(a, svc, gioco=True, cartella="tris"):
    """Lo sviluppo di un gioco di Dario, con il lavoro avviato (fase sviluppo)."""
    svs = svc.sviluppi
    sv = svs.apri("dario-id", "Dario", "estensione", COMPITO, gioco=gioco)
    lav = svc.nuovo("estensione", COMPITO, "dario-id", "Dario", "amministra")
    lav.gioco = gioco
    lav.estensione = None
    svc.avvia(lav)
    svs.avviato(lav)
    return sv, lav


def al_collaudo(a, svc):
    """Il lavoro del gioco finito con una versione candidata (il tris delle prove): collaudo."""
    sv, lav = gioco_in_sviluppo(a, svc)
    _, n = a.installa("tris", approva=False)
    item = svc.finisci(lav, "fatto", estensione={"nome": "tris", "versione": n},
                       test={"eseguiti": 22, "falliti": 0},
                       messaggio="ho preparato il gioco «Halloween - Apri le porte».")
    return sv, lav, n, item


# ═══════════════════════════ 1. il collaudo di un gioco è vederlo ═══════════════════════════

def prova_collaudo_gioco(tmp: Path):
    print("— 1. il collaudo di un gioco: aperto in prova sullo schermo, senza ponte")
    a, svc, studio = ambiente(tmp / "collaudo")
    svs = svc.sviluppi
    sv, lav, n, item = al_collaudo(a, svc)
    msg = item["messaggio"]
    verifica("16:25, il lavoro è pronto: «È un gioco… Lo apro in prova?», non «Con cosa "
             "provo?»", sv.fase == "collaudo" and "È un gioco" in msg
             and msg.endswith("Lo apro in prova?") and "Con cosa provo" not in msg, msg)
    sosp = item.get("in_sospeso") or {}
    verifica("…il «sì» va a sviluppo_collauda, senza dati", sosp.get("tool") ==
             "sviluppo_collauda" and sosp.get("argomenti") == {}, str(sosp))
    riga = svs.riga_fase(sv)
    verifica("i dati del turno al collaudo dicono che è un gioco e che si prova guardandolo",
             "È un GIOCO" in riga and "sviluppo_collauda senza dati" in riga
             and "«fammelo vedere»" in riga, riga)

    # 16:25:54 «Fammelo vedere e fallo girare» → sviluppo_collauda con dati inventati
    out = a.chiama("sviluppo_collauda", {"dati": "gioca con porte 1, 2 e 3"}, "Dario",
                   schermo=studio, turno=5)
    f = detta(out)
    p = next((x for x in a.giochi.partite.values() if x.prova), None)
    verifica("«fammelo vedere e fallo girare» → aperto in prova sullo schermo dello studio",
             out.get("ok") is not False and "in prova sullo schermo" in f and p is not None
             and list(p.posti) == [studio["id"]] and "gioco_prova" in a.ctx.regole
             and "sviluppo_collaudo_gioco" in a.ctx.regole, f)
    verifica("…e chiede se va bene o cosa cambiare", f.endswith("dimmi se va bene o cosa "
                                                                 "cambiare."), f)
    card = a.hub.storia(studio["id"])[-1]
    verifica("la scheda di gioco ha «prova»: true (la pagina mostra la cornice PROVA)",
             card.get("tipo") == "gioco" and card.get("prova") is True
             and card.get("doc") == f"/gioco/{p.gettone}" and card.get("condivisa") is False,
             str(card))
    doc = a.giochi.documento(p.gettone)
    verifica("il documento del riquadro è quello della versione candidata, con la CSP di "
             "sempre (sandbox, niente rete né frame)",
             doc is not None and "nuovaPartita" in doc[0]
             and all(x in doc[1] for x in ("sandbox allow-scripts", "default-src 'none'",
                                           "connect-src 'none'", "frame-src 'none'"))
             and "allow-same-origin" not in doc[1], str(doc)[:200])
    verifica("non diventa attiva né chiedibile: nessun tool est_tris, la candidata resta da "
             "approvare", a.tools.get("est_tris") is None
             and a.est.archivio.candidata("tris") == n
             and a.est.archivio.voce("tris").get("stato") != "attiva")
    verifica("il collaudo resta nello sviluppo come anteprima (il giudizio è della persona)",
             sv.collaudi and sv.collaudi[-1].get("anteprima") is True
             and "aperto in prova" in svs.testo_scheda(sv), str(sv.collaudi[-1:]))

    # Il riquadro: gira, ma senza ponte verso Calliope
    r = a.pagina(studio, {"partita": p.id, "tipo": "pronto"})
    verifica("dal riquadro: «pronto» passa (il gioco gira)", r.get("ok") is True, str(r))
    for tipo, extra in (("salva", {"chiave": "record", "valore": 3}),
                        ("leggi", {"chiave": "record"}), ("manda", {"dati": {"mossa": 1}}),
                        ("chat", {"testo": "ciao"}), ("di", {"testo": "Hai vinto!"}),
                        ("azione", {"nome": "casa_stato", "argomenti": {}})):
        r = a.pagina(studio, {"partita": p.id, "tipo": tipo, **extra})
        verifica(f"dal riquadro di prova: «{tipo}» rifiutato (403), nessun ponte",
                 r.get("_stato") == 403 and "prova" in str(r.get("errore")), str(r))
    verifica("…nessuna frase del gioco in coda per la voce", a.giochi.frasi.empty())
    for tipo in ("battito", "fine", "errore"):
        r = a.pagina(studio, {"partita": p.id, "tipo": tipo, "secondi": 5, "testo": "x"})
        verifica(f"contrario: «{tipo}» passa anche in prova", r.get("ok") is True, str(r))

    # Una seconda prova sostituisce la prima
    gett_prima = p.gettone
    a.chiama("sviluppo_collauda", {}, "Dario", schermo=studio, turno=6)
    prove = [x for x in a.giochi.partite.values() if x.prova]
    verifica("una seconda prova sostituisce la prima (l'indirizzo vecchio non vale più)",
             len(prove) == 1 and a.giochi.documento(gett_prima) is None
             and a.giochi.documento(prove[0].gettone) is not None)
    p = prove[0]

    # File cambiati dopo la consegna: niente prova, e il documento sparisce
    cart = a.est.archivio.cartella_versione("tris", n)
    f_js = cart / "gioco.js"
    prima = f_js.read_bytes()
    try:
        os.chmod(f_js, 0o644)
    except OSError:
        pass
    f_js.write_bytes(prima + b"\n// cambiato\n")
    out = a.chiama("sviluppo_collauda", {}, "Dario", schermo=studio, turno=7)
    verifica("contrario: file cambiati dopo la consegna → non lo apre (estensione_impronta), "
             "e il documento di prova non c'è più",
             out.get("ok") is False and "estensione_impronta" in a.ctx.regole
             and a.giochi.documento(p.gettone) is None, detta(out))
    f_js.write_bytes(prima)
    verifica("…tornati i file di prima, il documento c'è di nuovo",
             a.giochi.documento(p.gettone) is not None)

    # Una familiare non collauda
    out = a.chiama("sviluppo_collauda", {}, "Elena", schermo=studio, turno=8)
    verifica("contrario: una familiare non apre la prova (il collaudo è di chi amministra)",
             out.get("ok") is False, detta(out))
    a.chi("Dario", "voce", studio)

    # «Va bene, andiamo avanti» → la revisione lo dice
    out = a.chiama("sviluppo_passo", {"azione": "avanti"}, "Dario", schermo=studio, turno=9)
    verifica("«va bene» → la revisione dice che l'ha visto in prova (non «prove riuscite»)",
             sv.fase == "revisione" and "L'hai visto in prova sullo schermo" in detta(out)
             and "riuscite" not in detta(out), detta(out))

    # Dopo l'approvazione il documento di prova non vale più; una partita vera è un'altra
    a.est.archivio.approva("tris", n, "Dario")
    a.est.aggiorna_tool()
    verifica("dopo l'approvazione la partita di prova non ha più documento",
             a.giochi.documento(p.gettone) is None)
    cam = a.abbina("camera", "camera", proprietario="Dario")
    out = a.chiama("est_tris", {}, "Dario", schermo=cam, turno=10)
    vera = a.giochi.partite.get(out.get("partita"))
    verifica("contrario: la partita vera non si unisce a quella di prova, e non è di prova",
             vera is not None and vera.id != p.id and not vera.prova
             and a.giochi.documento(vera.gettone) is not None, detta(out))
    r = a.pagina(cam, {"partita": vera.id, "tipo": "salva", "chiave": "record", "valore": 1})
    verifica("contrario: nella partita vera salva passa come sempre", r.get("ok") is True, str(r))

    # Contrari dell'annuncio e della revisione
    a2, svc2, studio2 = ambiente(tmp / "non_gioco")
    sv2 = svc2.sviluppi.apri("dario-id", "Dario", "estensione", "un'estensione del meteo",
                             titolo="Meteo")
    lav2 = SimpleNamespace(persona_nome="Dario", risultato={}, ricollaudo=None)
    verifica("contrario: un'estensione che non è un gioco chiede ancora «Con cosa provo?»",
             svc2.sviluppi.frase_pronto(sv2, lav2).endswith("Con cosa provo?")
             and not svc2.sviluppi.e_gioco(sv2))
    a3, svc3, studio3 = ambiente(tmp / "senza_prova")
    sv3, _, _, _ = al_collaudo(a3, svc3)
    out = a3.chiama("sviluppo_passo", {"azione": "avanti"}, "Dario", schermo=studio3, turno=5)
    verifica("contrario: un gioco approvato senza averlo visto → la revisione lo dice",
             "Il collaudo l'hai saltato: non l'hai visto in prova sullo schermo" in detta(out)
             and "sviluppo_revisione_senza_collaudo" in (a3.ctx.regole or []), detta(out))


# ═══════════════════════════ 2. correggere uno sviluppo fermo ═══════════════════════════

def fermato(a, svc, tmp: Path):
    """Il lavoro del gioco fermato da Calliope (15:52:19) prima di consegnare una versione."""
    sv, lav = gioco_in_sviluppo(a, svc)
    cart = tmp / "Lavori" / "2026-10-11 1540 videogioco"
    cart.mkdir(parents=True, exist_ok=True)
    (cart / "gioco.js").write_text("function generaPorte(n) { return []; }\n", encoding="utf-8")
    (cart / "logica.js").write_text("// logica delle porte\n", encoding="utf-8")
    (cart / "lavoro.json").write_text("{}", encoding="utf-8")
    # Il contesto si conserva prima dell'annuncio, con il lavoro ancora dello sviluppo (come
    # agenti/servizio._conserva)
    lav.risultato = {"esito": "limite", "motivo": MOTIVO, "cartella": str(cart)}
    svc.sviluppi.conserva(lav)
    item = svc.finisci(lav, "errore", esito="limite", motivo=MOTIVO, cartella=str(cart),
                       test={"eseguiti": 19, "falliti": 0}, test_passano=True,
                       messaggio=f"ho fermato «{TITOLO}»: ha ripetuto lo stesso ragionamento.")
    return sv, lav, item


def prova_correggi_fermo(tmp: Path):
    print("— 2. sviluppo_correggi su uno sviluppo fermo senza versione")
    a, svc, studio = ambiente(tmp / "correggi")
    svs = svc.sviluppi
    sv, lav, item = fermato(a, svc, tmp / "correggi")
    verifica("15:52, lo sviluppo resta allo sviluppo, senza lavoro né versione, con il motivo",
             sv.fase == "sviluppo" and sv.lavoro is None and not sv.estensione
             and "ragionamento" in sv.nota, f"{sv.fase} {sv.lavoro} {sv.estensione} {sv.nota}")
    a.ctx.tool_in_sospeso = "sviluppo_correggi"
    out = a.chiama("sviluppo_correggi", {"problema": PROBLEMA}, "Dario", schermo=studio, turno=3)
    a.ctx.tool_in_sospeso = None
    f = detta(out)
    nuovo = svc.lavori[-1]
    verifica("15:53 «Sì» → sviluppo_correggi: niente «Qui le estensioni non ci sono», il lavoro "
             "rifatto con la correzione (sviluppo_correggi_rifai)",
             "estensioni non ci sono" not in f and "sviluppo_correggi_rifai" in a.ctx.regole
             and nuovo is not lav and nuovo.stato == "in_corso" and sv.lavoro == nuovo.id, f)
    verifica("…i vincoli hanno il problema detto e il motivo dell'arresto",
             PROBLEMA[:40] in nuovo.vincoli and "ragionamento" in nuovo.vincoli
             and "senza consegnare" in nuovo.vincoli, nuovo.vincoli)
    verifica("…e riparte dai file che l'agente aveva già scritto (non lavoro.json)",
             "generaPorte" in nuovo.file_iniziali.get("gioco.js", "")
             and "logica.js" in nuovo.file_iniziali
             and "lavoro.json" not in nuovo.file_iniziali, str(list(nuovo.file_iniziali)))
    verifica("…la frase dice che non c'era una versione e che rifà il lavoro",
             "non c'era ancora una versione" in f and "Qui le estensioni" not in f, f)
    # contrari
    out = a.chiama("sviluppo_correggi", {"problema": PROBLEMA}, "Dario", schermo=studio, turno=4)
    verifica("contrario: con l'agente già al lavoro non ne parte un altro",
             out.get("ok") is False and svc.lavori[-1] is nuovo, detta(out))
    a2, svc2, studio2 = ambiente(tmp / "correggi_vuoto")
    fermato(a2, svc2, tmp / "correggi_vuoto")
    out = a2.chiama("sviluppo_correggi", {}, "Dario", schermo=studio2, turno=3)
    verifica("senza problema detto: il lavoro rifatto lo stesso, con la regola",
             "sviluppo_correggi_rifai" in a2.ctx.regole and svc2.lavori[-1].stato == "in_corso"
             and "estensioni non ci sono" not in detta(out), detta(out))
    a3, svc3, studio3 = ambiente(tmp / "correggi_analisi")
    svc3.sviluppi.apri("dario-id", "Dario", "estensione", COMPITO, gioco=True)
    out = a3.chiama("sviluppo_correggi", {"problema": PROBLEMA}, "Dario", schermo=studio3,
                    turno=2)
    verifica("contrario: all'analisi non c'è codice da correggere",
             "prima finiamo l'analisi" in detta(out)
             and "sviluppo_correggi_rifai" not in a3.ctx.regole, detta(out))
    from calliope.tools import sviluppo as ts
    import inspect
    sorgente = inspect.getsource(ts)
    verifica("«Qui le estensioni non ci sono» solo quando le estensioni mancano davvero",
             sorgente.count('"Qui le estensioni non ci sono."') == 4
             and "if est is None or not sv.estensione:" not in sorgente)


# ═══════════════════════════ 3. l'avviso di tappa ═══════════════════════════

def prova_tappa():
    print("— 3. l'avviso di tappa con un conteggio solo")
    from calliope.agenti.servizio import frase_tappa
    seg = {"frasi": ["ha riscritto gioco.js 9 volte"]}

    def lav(**r):
        base = {"esito": "tappa", "tipo_limite": "passate", "segnali": seg}
        return SimpleNamespace(risultato={**base, **r})
    f = frase_tappa(lav(riassunto="21 test su 22 passano", test={"eseguiti": 22, "falliti": 0},
                        test_passano=True, manca=["far passare i test che falliscono"]), TITOLO)
    verifica("16:19: un solo conteggio, quello rifatto alla tappa (22 su 22); niente «Manca: far "
             "passare i test»", "22 su 22" in f and "21 test su 22" not in f
             and "Manca" not in f and f.count("test") == 1 + f.count("test falliscono"), f)
    f = frase_tappa(lav(riassunto="fatto: scritto gioco.js; esegui_test: 21 test su 22 passano",
                        test={"eseguiti": 22, "falliti": 0}, test_passano=True), TITOLO)
    verifica("il riassunto tiene le cose fatte, senza il conteggio vecchio",
             "scritto gioco.js" in f and "21 test" not in f and "22 su 22" in f, f)
    f = frase_tappa(lav(riassunto="21 test su 22 passano", test={"eseguiti": 22, "falliti": 1},
                        test_passano=False, manca=["far passare i test che falliscono"]), TITOLO)
    verifica("contrario: un test che non passa → «21 su 22» detto una volta, e il «Manca» resta",
             f.count("21 su 22") == 1 and "21 test su 22" not in f
             and "Manca: far passare i test" in f, f)
    f = frase_tappa(lav(riassunto="fatto: scritto gioco.js. 21 test su 22 passano",
                        manca=["far passare i test che falliscono"]), TITOLO)
    verifica("contrario: senza test rifatti alla tappa il conteggio del riassunto resta (è "
             "l'unico)", "21 test su 22 passano" in f and "Manca" in f, f)


# ═══════════════════════════ 4. perché si è fermato ═══════════════════════════

def prova_perche(tmp: Path):
    print("— 4. perché si è fermato: il motivo deciso da Calliope")
    a, svc, studio = ambiente(tmp / "perche")
    svs = svc.sviluppi
    sv, lav, item = fermato(a, svc, tmp / "perche")
    verifica("il motivo dell'arresto per l'agente e per la voce",
             "ha ripetuto lo stesso ragionamento in 3 passate" in svs.motivo_arresto(sv)
             and svs.motivo_arresto(sv, voce=True).startswith("Il lavoro l'ho fermato io: ha "
                                                               "ripetuto"),
             svs.motivo_arresto(sv))
    out = a.chiama("sviluppo_chiedi", {"domanda": "Qual è il motivo per cui è rimasto "
                                                  "bloccato?"}, "Dario", schermo=studio, turno=3)
    testo = svc.cliente.richieste[-1]["messages"][1]["content"]
    sistema = svc.cliente.richieste[-1]["messages"][0]["content"]
    verifica("15:52:40, il contesto della domanda ha il motivo dell'arresto deciso da Calliope",
             "PERCHÉ IL LAVORO SI È FERMATO (lo ha deciso Calliope)" in testo
             and "ragionamento in 3 passate" in testo
             and "motivo dell'arresto: ho dovuto fermarlo" in testo, testo[:600])
    verifica("…e il sistema dice all'agente di dirlo per primo",
             "PERCHÉ IL LAVORO SI È FERMATO" in sistema and "per primo" in sistema)
    verifica("…l'esito del tool porta il motivo fuori dalla busta (`motivo`) e dice di dirlo "
             "prima della risposta dell'agente",
             "ha ripetuto lo stesso ragionamento" in str(out.get("motivo"))
             and "PRIMA il «motivo»" in str(out.get("cosa_fare"))
             and "sviluppo_chiedi_arresto" in a.ctx.regole, json.dumps(out, ensure_ascii=False))
    from calliope import provenienza
    verifica("«motivo» è un campo di controllo (resta fuori dalla busta del dato)",
             "motivo" in provenienza.CONTROLLO)
    # contrari
    a2, svc2, studio2 = ambiente(tmp / "perche_collaudo")
    sv2, _, _, _ = al_collaudo(a2, svc2)
    out = a2.chiama("sviluppo_chiedi", {"domanda": "Come funziona?"}, "Dario", schermo=studio2,
                    turno=3)
    testo = svc2.cliente.richieste[-1]["messages"][1]["content"]
    verifica("contrario: al collaudo nessun motivo d'arresto (né nel contesto né nell'esito)",
             "motivo" not in out and "PERCHÉ IL LAVORO" not in testo
             and "sviluppo_chiedi_arresto" not in a2.ctx.regole, str(out))
    sv2.fase, sv2.nota = "sviluppo", "annullato"
    verifica("contrario: fermato dalla persona → «l'hai fermato tu», non un errore",
             svc2.sviluppi.motivo_arresto(sv2, voce=True) == "Il lavoro l'hai fermato tu.")
    a3, svc3, _ = ambiente(tmp / "perche_tappa")
    sv3, lav3 = gioco_in_sviluppo(a3, svc3)
    lav3.stato = "in_attesa"
    lav3.risultato = {"esito": "tappa", "tipo_limite": "passate",
                      "segnali": {"frasi": ["ha riscritto gioco.js 9 volte"]}}
    m = svc3.sviluppi.motivo_arresto(sv3)
    verifica("una tappa: il tetto del giro e i segnali di giro a vuoto",
             m.startswith("è fermo a una tappa: ha finito le passate del giro")
             and "riscritto gioco.js 9 volte" in m, m)
    lav3.stato = "in_corso"
    verifica("contrario: con l'agente al lavoro nessun motivo", svc3.sviluppi.motivo_arresto(sv3)
             == "")


# ═══════════════════════════ 5. il titolo ═══════════════════════════

def prova_titoli():
    print("— 5. il titolo non finisce con una preposizione, un articolo o una congiunzione")
    from calliope.agenti.servizio import _CODA, titolo_da
    from calliope.sviluppo import titolo_richiesta
    verifica("15:38: «…da giocare sugli» → «videogioco a tema Halloween da giocare»",
             titolo_da(COMPITO) == TITOLO and titolo_richiesta("estensione", COMPITO) == TITOLO,
             titolo_da(COMPITO))
    casi = ["Crea un gioco con le carte da usare negli schermi della casa",
            "Fammi un quiz sulla storia da fare dopo cena ed altro ancora",
            "Scrivi uno script che legga le foto nei dischi esterni",
            "Crea un gioco di carte veloce e semplice ma divertente per tutti",
            "Fammi un gioco sulle capitali da giocare coi bambini piccoli"]
    for c in casi:
        t = titolo_da(c)
        ultima = t.split()[-1].lower()
        verifica(f"«{c[:45]}…» → «{t}»: non finisce con «{ultima}»", ultima not in _CODA
                 and not ultima.endswith(("'", "’")), t)
    buoni = [("Scrivi un programma in Python che converte i gradi Celsius in Fahrenheit",
              "programma in Python che converte i gradi Celsius in Fahrenheit"),
             ("Scrivi un programma in Python che conti il numero di vocali presenti in una "
              "stringa", "programma in Python che conti il numero di vocali"),
             ("Scrivi uno script che rinomina le foto per data", "script che rinomina le foto "
              "per data"),
             ("Fammi un gioco memory da giocare sullo schermo",
              "gioco memory da giocare sullo schermo"),
             ("Crea un gioco di Halloween per schermi dove i giocatori devono scegliere tra "
              "diverse porte", "gioco di Halloween")]
    for c, atteso in buoni:
        verifica(f"contrario: il titolo buono resta «{atteso}»", titolo_da(c) == atteso,
                 titolo_da(c))


# ═══════════════════════════ 6. il titolo del proprio sviluppo ═══════════════════════════

def prova_provenienza(tmp: Path):
    print("— 6. il titolo di un proprio sviluppo è un bersaglio fidato")
    from calliope import politica as pol
    from calliope import valore
    a, svc, studio = ambiente(tmp / "valore")
    svs = svc.sviluppi
    sv, lav, item = fermato(a, svc, tmp / "valore")
    sv.titolo = TITOLO
    annuncio = item["messaggio"]
    frase = "Fallo continuare all'ora."

    def decidi(name, args, ctx, esterni=annuncio):
        t = pol.Turno(testo=frase, contaminazione=frozenset({"agente"}), persona_txt=frase,
                      esterni=[("agente", esterni)], persona="dario-id")
        cl = pol.classe_di(name)
        base = pol.decidi(name, args, cl, valore.copia_turno(t), True, True)
        return valore.decidi_valore(name, args, cl, t, base, True, True, None, ctx, None, ())
    a.chi("Dario", "voce", studio)
    args = {"azione": "avanti", "quale": TITOLO}
    nuova, det = decidi("sviluppo_passo", args, a.ctx)
    verifica("15:53:13 «Fallo continuare» → quale = il titolo del suo sviluppo: bersaglio "
             "fidato, niente «viene dal lavoro di un agente»",
             det["argomenti"].get("quale") == "bersaglio/fidato"
             and "dato" not in det["bersagli"] and nuova.regola != "valore_bersaglio_dato",
             f"{det} {nuova}")
    verifica("…anche con l'id («S1») o parte del titolo («il videogioco di Halloween»)",
             valore.sviluppo_suo("sviluppo_passo", "quale", sv.id, a.ctx)
             and valore.sviluppo_suo("sviluppo_passo", "quale", "videogioco Halloween", a.ctx))
    # contrari
    altro = svs.apri("elena-id", "Elena", "estensione", "un videogioco di Natale sugli schermi",
                     titolo="videogioco di Natale")
    args2 = {"azione": "avanti", "quale": "videogioco di Natale"}
    nuova, det = decidi("sviluppo_passo", args2, a.ctx,
                        esterni=annuncio + " Elena: «videogioco di Natale» è pronto.")
    verifica("contrario: il titolo di uno sviluppo di un'altra persona resta dato",
             det["argomenti"].get("quale") == "bersaglio/dato"
             and nuova.regola == "valore_bersaglio_dato", f"{det} {nuova}")
    svs.chiudi(altro, "uscita")
    nuova, det = decidi("sviluppo_passo", {"azione": "avanti", "quale": "gioco del Ponte"},
                        a.ctx, esterni=annuncio + " Pronto anche «gioco del Ponte».")
    verifica("contrario: un titolo che non è di nessuno sviluppo resta dato",
             det["argomenti"].get("quale") == "bersaglio/dato", str(det))
    verifica("contrario: le stesse parole in un altro tool non diventano fidate",
             not valore.sviluppo_suo("lista_aggiungi", "lista", TITOLO, a.ctx)
             and not valore.sviluppo_suo("sviluppo_passo", "cambia", TITOLO, a.ctx))
    a.chi("Elena", "voce", studio)
    verifica("contrario: lo stesso titolo detto da un'altra persona non è suo",
             not valore.sviluppo_suo("sviluppo_passo", "quale", TITOLO, a.ctx))
    a.chi(None, None, studio)
    verifica("contrario: senza una persona riconosciuta niente",
             not valore.sviluppo_suo("sviluppo_passo", "quale", TITOLO, a.ctx))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="calliope-giro-halloween-"))
    os.environ.setdefault("DOCKER_FINTO_DIR", str(tmp / "docker"))
    prova_collaudo_gioco(tmp)
    prova_correggi_fermo(tmp)
    prova_tappa()
    prova_perche(tmp)
    prova_titoli()
    prova_provenienza(tmp)
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
