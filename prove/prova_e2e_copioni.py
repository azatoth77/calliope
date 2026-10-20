"""
La prova end-to-end sulla DGX (prove/e2e/) a secco (06/10/2026): i copioni sono ben fatti
(persone, registrazioni, chiavi delle attese, espressioni regolari), il controllo dei passi
dà gli esiti giusti su turni finti, la frase di sfida si legge, e nei file della prova non ci
sono dati personali (nomi veri, indirizzi, utenti).

    python prove/prova_e2e_copioni.py
"""
import re
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

from prove.e2e import copioni as C  # noqa: E402
from prove.e2e import verifica as V  # noqa: E402
from prove.e2e.voci import ARRUOLA_PIPER, PERSONE, elenco_reale  # noqa: E402

errori = 0
CHIAVI = {"tool", "tool_tutti", "no_tool", "regole", "no_regole", "esito", "livello", "chi",
          "testo", "non_testo", "annuncio", "suoni", "ha", "ha_no", "pc", "giudizio", "muto",
          "voce_studio", "voce_studio_ferma",
          # 20/10 (#75): estensioni, sviluppo e giochi
          "porta", "porta_no", "sviluppo", "sviluppo_stato", "log", "no_log", "scheda", "gioco", "o",
          "annuncio_testo"}
RICHIEDE = {"reale", "agente", "web", "biblioteca", "schermo", "pagina"}
FASI = {"analisi", "sviluppo", "collaudo", "revisione", "attivazione"}
STATI = {"aperta", "sospesa", "chiusa"}


def ok(nome, cond, extra=""):
    global errori
    if not cond:
        errori += 1
    print(("ok  " if cond else "ERR ") + nome + (f"  ({extra})" if extra else ""), flush=True)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    reale = elenco_reale()
    ok("voce_reale.tsv: chiavi uniche, testo e uso", len(reale) >= 30 and all(
        r["testo"] and r["uso"] in ("arruola", "frase") for r in reale.values()))
    ok("almeno 6 frasi d'arruolamento della voce vera",
       sum(r["uso"] == "arruola" for r in reale.values()) >= 6)
    ok("frasi d'arruolamento delle voci di Piper senza il nome",
       all("calliope" not in t.lower() for t in ARRUOLA_PIPER))
    ids, problemi = set(), []
    for c in C.COPIONI:
        if c.id in ids:
            problemi.append(f"{c.id}: id doppio")
        ids.add(c.id)
        for i, p in enumerate(c.passi):
            dove = f"{c.id}#{i}"
            if p.chi not in PERSONE:
                problemi.append(f"{dove}: persona {p.chi}")
            if p.tipo == "voce":
                if p.reale:
                    if p.reale not in reale or reale[p.reale]["uso"] != "frase":
                        problemi.append(f"{dove}: registrazione {p.reale}")
                    if "reale" not in c.richiede:
                        problemi.append(f"{dove}: registrazione senza richiede=reale")
                elif not p.testo or PERSONE[p.chi].voce is None:
                    problemi.append(f"{dove}: frase di Piper mancante o persona senza voce")
            if p.tipo in ("foto", "allegato", "scrivi") and "schermo" not in c.richiede:
                problemi.append(f"{dove}: passo dallo schermo senza richiede=schermo")
            for k in [*p.attese, *(k for alt in p.attese.get("o") or [] for k in alt)]:
                if k not in CHIAVI or k == "o" and not isinstance(p.attese["o"], list):
                    problemi.append(f"{dove}: attesa sconosciuta {k}")
            if "est_*" in (p.attese.get("tool") or []) and c.area in ("estensioni", "sviluppo"):
                problemi.append(f"{dove}: «est_*» accetta ogni estensione: «est_@»")
            k = p.dati.get("log_dal_passo")
            if k is not None and not (isinstance(k, int) and -i <= k < 0):
                problemi.append(f"{dove}: log_dal_passo {k!r}")
            for rx in (p.attese.get("testo") or []) + (p.attese.get("non_testo") or []):
                try:
                    re.compile(rx)
                except re.error as e:
                    problemi.append(f"{dove}: regex {rx!r} ({e})")
            if "annuncio" in p.attese:
                rx, s = p.attese["annuncio"]
                re.compile(rx)
                if not 10 <= s <= 3600:
                    problemi.append(f"{dove}: attesa dell'annuncio {s}")
            for rx in (p.attese.get("log") or []) + (p.attese.get("no_log") or []) + (
                    p.attese.get("scheda") or []) + list((p.attese.get("gioco") or {}).values()):
                try:
                    re.compile(str(rx))
                except re.error as e:
                    problemi.append(f"{dove}: regex {rx!r} ({e})")
            if p.dati.get("se_domanda"):
                try:
                    re.compile(p.dati["se_domanda"])
                except re.error as e:
                    problemi.append(f"{dove}: se_domanda {e}")
            for k, ammessi in (("sviluppo", FASI), ("sviluppo_stato", STATI)):
                if k in p.attese and not set(V._lista(p.attese[k])) <= ammessi:
                    problemi.append(f"{dove}: {k} {p.attese[k]!r}")
            for v in (p.attese.get("porta") or []) + (p.attese.get("porta_no") or []):
                if not re.fullmatch(r"[a-z_]+\*?(:[a-z_]+)?", v):
                    problemi.append(f"{dove}: porta {v!r} (regola o regola:esito)")
            usa_agente = any(t in ("sviluppo_apri", "lavoro_affida")
                             for t in p.attese.get("tool") or [])
            if usa_agente and p.attese.get("annuncio") and "agente" not in c.richiede:
                problemi.append(f"{dove}: lavoro dell'agente senza richiede=agente")
        if not set(c.richiede) <= RICHIEDE:
            problemi.append(f"{c.id}: richiede {c.richiede}")
        if "agente" in c.richiede and not c.lento:
            problemi.append(f"{c.id}: agente vero senza lento=True")
    ok("copioni ben fatti (persone, registrazioni, attese, regex)", not problemi,
       "; ".join(problemi[:8]))
    ok("un copione per ogni area chiesta", {"voce-vera", "casa", "agenda", "minori",
                                            "satelliti", "immagini", "allegati", "agenti",
                                            "estensioni", "personalita", "permessi",
                                            "biblioteca", "web", "sviluppo", "giochi"}
       <= {c.area for c in C.COPIONI})
    # 20/10 (#75): le serie del copione manuale (prove/manuali/copione-estensioni-giochi.md)
    est = {c.id for c in C.COPIONI if c.area in ("estensioni", "sviluppo", "giochi")}
    ok("copioni di estensioni, sviluppo e giochi: lavori, contrari e partite",
       {"est-cambio", "est-bacheca", "est-notte", "est-notte-contrari", "est-nutriscore",
        "svil-differenziata", "svil-versioni", "svil-miglia", "imp-orari", "imp-gioco-modello",
        "est-minore", "est-ospite", "gioco-porte", "gioco-tris", "gioco-spesa",
        "partita-porte"} <= est, str(sorted(est))[:200])
    ok("le partite chiedono la pagina vera e i loro giochi si creano prima nello stesso file",
       all("pagina" in c.richiede for c in C.COPIONI if c.id.startswith("partita-"))
       and [c.id for c in C.COPIONI].index("gioco-porte")
       < [c.id for c in C.COPIONI].index("partita-porte"))
    ok("i copioni nuovi stanno prima della chiusura («esci»)", C.COPIONI[-1].id == "esci-andrea")
    ok("scegli per area: estensioni, sviluppo e giochi a parte, lenti esclusi con --senza-lenti",
       all(c.area == "giochi" for c in C.scegli({"giochi"}))
       and {c.id for c in C.scegli({"estensioni"}, lenti=False)} >= {"est-minore", "est-ospite",
                                                                   "est-elenco"}
       and not any(c.lento for c in C.scegli({"sviluppo", "giochi"}, lenti=False)))
    ok("scegli: aree, id, lenti e requisiti", (
        all(c.area == "casa" for c in C.scegli({"casa"}))
        and not any(c.lento for c in C.scegli(lenti=False))
        and not any("reale" in c.richiede for c in C.scegli(senza={"reale"}))
        and [c.id for c in C.scegli(ids={"eta"})] == ["eta"]))

    # Il controllo di un passo
    turno = {"tool": [{"nome": "casa_comando"}], "regole": ["riferimento_casa",
                                                           "guardiano_pericolo"],
             "esito": "risposta", "livello": "amministra",
             "voce": {"nome": "Andrea", "punteggio": 0.8}, "risposta": "Ho acceso la luce."}
    att = {"tool": ["casa_comando"], "regole": ["guardiano_*"], "chi": "Andrea",
           "livello": "amministra", "testo": [r"acces"], "ha": ["light.turn_on:light.cucina"]}
    ok("passo riuscito: nessuno scostamento", V.controlla(
        att, turno, "Ho acceso la luce.", {"ha": ["light.turn_on:light.cucina"]}) == [])
    e = V.controlla(att, turno, "Ho acceso la luce.", {"ha": []})
    ok("servizio dell'HA mancante segnalato", len(e) == 1 and "HA finto" in e[0], str(e))
    e = V.controlla({"no_tool": True, "chi": None}, turno, "x")
    ok("tool non voluti e ospite riconosciuto segnalati", len(e) == 2, str(e))
    e = V.controlla({"esito": ["dormi"], "non_testo": [r"acces"]}, turno, "Ho acceso.")
    ok("esito e testo vietato segnalati", len(e) == 2, str(e))
    e = V.controlla({"annuncio": ("timer", 60), "suoni": True}, turno, "ok", {})
    ok("annuncio e suoni mancanti segnalati", len(e) == 2, str(e))
    e = V.controlla({"voce_studio_ferma": True}, turno, "x", {"voce_studio": ["pensa", "parla"]})
    f = V.controlla({"voce_studio": True}, turno, "x", {"voce_studio": ["ascolta"]})
    ok("stato della voce sullo schermo dello studio controllato", len(e) == 1 and len(f) == 1,
       str(e + f))
    ok("muto: una risposta è uno scostamento",
       V.controlla({"muto": True}, {}, "Eccomi") and not V.controlla({"muto": True}, {}, ""))
    ok("frase di sfida letta", V.parole_sfida(
        "Per conferma ripeti: girasole, matita, candela, quarantadue.")
       == "girasole, matita, candela, quarantadue")
    ok("frase senza sfida: None", V.parole_sfida("Fatto, ho acceso la luce.") is None)
    ok("somiglianza dei testi (accenti e punteggiatura non contano)",
       V.somiglianza("Sono le 3:46.", "sono le 3 46") == 1.0
       and V.somiglianza("Mi dispiace, non posso.", "Calliope.") < 0.3)
    # Le attese corrette dopo il giro 4 del 06/10, con le risposte vere di quel giro
    passo = {(c.id, i): p for c in C.COPIONI for i, p in enumerate(c.passi)}
    luna = "La Luna si trova mediamente a una distanza di circa 385.000 km dal centro della Terra."
    ok("luna: 385.000 km è giusto", not V.controlla(
        passo["reale-biblioteca", 1].attese, {"tool": [{"nome": "biblioteca_cerca"}]}, luna))
    ok("luna: una distanza sbagliata no", V.controlla(
        passo["reale-biblioteca", 1].attese, {}, "La Luna dista 150 milioni di km."))
    ferma = {"tool": [{"nome": "lavoro_annulla"}], "esito": "risposta"}
    ok("fermati-ordine: lavoro_annulla che non ferma niente va bene", not V.controlla(
        passo["fermati-ordine", 0].attese, ferma, "Non ho lavori in corso da fermare."))
    ok("fermati-ordine: «ho fermato» no", V.controlla(
        passo["fermati-ordine", 0].attese, ferma, "Ho fermato l'ordine."))
    gatto = {"tool": [{"nome": "ricorda"}], "regole": ["spinta_dichiarata",
                                                      "dichiarata_taciuta",
                                                      "politica_azione_non_chiesta"]}
    ok("corsie: «Non ci sono riuscita» dopo ricorda rifiutato è uno scostamento", V.controlla(
        passo["corsie", 0].attese, gatto, "Non ci sono riuscita: puoi ripetere la richiesta?",
        {"voce_studio": ["pensa", "parla"]}))
    ok("corsie: ricorda eseguito va bene", not V.controlla(
        passo["corsie", 0].attese, {"tool": [{"nome": "ricorda"}], "regole": []},
        "Ho segnato che il tuo gatto si chiama Briciola.", {"voce_studio": ["pensa", "parla"]}))
    ok("fisica: «intendevi Heisenberg?» va bene", not V.controlla(
        passo["fisica", 1].attese, {}, "Forse intendevi il principio di indeterminazione di "
                                       "Heisenberg?"))
    # Le attese nuove del 20/10 (#75): porta stretta, fase dello sviluppo, log, schede, gioco
    est = {"tool": [{"nome": "est_cambio_valute"}], "regole": [], "esito": "risposta"}
    extra = {"porta": ["estensione_rete_pubblica:eseguita", "estensione_quota_casa:rifiutata"],
             "sviluppo": {"fase": "collaudo", "stato": "aperta"},
             "log": "[AGENTI] L3: analisi prima del codice (12.3 s): 5 esempi di accettazione",
             "schede": ['{"titolo": "Bacheca", "testo": "pacco giovedì"}']}
    att = {"tool": ["est_*"], "no_tool": ["web_*"], "porta": ["estensione_rete_*:eseguita",
                                                             "estensione_quota_casa"],
           "porta_no": ["estensione_casa_comando:confermata"], "sviluppo": ["collaudo"],
           "sviluppo_stato": "aperta", "log": [C.ANALISI], "no_log": [r"piano impossibile"],
           "scheda": [r"pacco"]}
    ok("estensioni: tool con il prefisso, porta, sviluppo, log e scheda giusti",
       V.controlla(att, est, "Sono 1.234 yen.", extra) == [],
       str(V.controlla(att, est, "x", extra)))
    e = V.controlla(att, {"tool": [{"nome": "web_cerca"}]}, "x",
                    {"porta": ["estensione_casa_comando:confermata"],
                     "sviluppo": {"fase": "sviluppo", "stato": "sospesa"},
                     "log": "piano impossibile (orari_fissi)", "schede": []})
    ok("estensioni: ogni attesa mancata segnalata (contrari)", len(e) == 10, str(e))
    ok("porta: «regola» senza esito e prefisso",
       V._porta_ok("estensione_dati_scrivi", ["estensione_dati_scrivi:eseguita"])
       and not V._porta_ok("estensione_dati_scrivi:eseguita",
                           ["estensione_dati_scrivi:rifiutata"])
       and V._porta_ok("estensione_*", ["estensione_flusso:eseguita"])
       and not V._porta_ok("estensione_flusso", ["estensione_flusso_negato:rifiutata"]))
    g = {"esito": "gioco_comando", "gioco": {"partita": "p1", "comando": "porta:3", "ms": 80}}
    ok("gioco: il comando del turno controllato",
       not V.controlla({"esito": "gioco_comando", "gioco": {"comando": "porta"}}, g, "")
       and V.controlla({"gioco": {"comando": "anchio"}}, g, "")
       and V.controlla({"gioco": {"comando": "porta"}}, {"esito": "risposta"}, ""))
    # Revisione della PR #196: l'ordine vero del log (i file di partenza prima del piano,
    # agenti/servizio.py), i secondi con i decimali, le due strade dell'impossibile
    vero = ("[AGENTI] L4: nella cartella di partenza calliope_estensione.py, "
            "test_estensione.py\n[AGENTI] L4: analisi prima del codice (12.3 s): 4 esempi di "
            "accettazione\n[AGENTI] L4: piano impossibile (orari_fissi)")
    imp1, imp2 = passo["imp-orari", 0], passo["imp-orari", 1]
    ok("ANALISI: i secondi con i decimali (12.3 s), e non un'altra riga",
       re.search(C.ANALISI, vero) and not re.search(C.ANALISI, "analisi prima del codice non "
                                                              "fatta: scaduta"))
    ok("impossibile dal piano: con i file di partenza prima nel log va bene",
       not V.controlla(imp2.attese, {}, "", {"annuncio": "Non si può fare: …", "log": vero}))
    ok("impossibile dal piano: senza «piano impossibile» nel log è uno scostamento",
       V.controlla(imp2.attese, {}, "", {"annuncio": "Non si può fare: …",
                                         "log": vero.rsplit("\n", 1)[0]}))
    propo = "Ho capito così: … Va bene così, o la cambiamo?"
    blocco = "Così non la faccio partire: cosa vuoi cambiare?"
    t_apri = {"tool": [{"nome": "sviluppo_apri"}]}
    ok("impossibile, primo passo: la proposta o il blocco all'analisi col suo log",
       not V.controlla(imp1.attese, t_apri, propo, {"log": ""})
       and not V.controlla(imp1.attese, t_apri, blocco,
                           {"log": "[SVILUPPO] S3: il lavoro non parte (regola "
                                   "sviluppo_nucleo_impossibile)"}))
    ok("impossibile, primo passo: il blocco senza la regola nel log, o un'altra risposta, no",
       V.controlla(imp1.attese, t_apri, blocco, {"log": ""})
       and V.controlla(imp1.attese, t_apri, "Fatto, l'ho creata.", {"log": ""}))
    se = imp2.dati["se_domanda"]
    ok("impossibile: il secondo passo solo dopo la proposta, non dopo il blocco",
       re.search(se, propo, re.I) and not re.search(se, blocco, re.I))
    no_prova = next(p for p in C.COPIONI if p.id == "gioco-porte").passi[2]
    seguito = ("Andrea, il lavoro di «Le porte» è pronto: siamo al collaudo. Ho controllato i "
               "requisiti. Lo apro in prova?")
    ok("«Lo apro in prova?» trovato anche se non è la prima frase dell'annuncio",
       re.search(no_prova.dati["se_domanda"], seguito, re.I)
       and not re.search(no_prova.dati["se_domanda"],
                         "Andrea, il lavoro di «Le porte» è pronto: siamo al collaudo.", re.I))
    ok("«est_@»: solo il tool dell'estensione del copione",
       not V.controlla({"tool": ["est_@"]}, {"tool": [{"nome": "est_cambio_valute"}]}, "",
                       {"estensione": "cambio_valute"})
       and V.controlla({"tool": ["est_@"]}, {"tool": [{"nome": "est_bacheca"}]}, "",
                       {"estensione": "cambio_valute"})
       and V.controlla({"tool": ["est_@"]}, {"tool": [{"nome": "est_bacheca"}]}, "", {}))
    # Seconda revisione della PR #196: se_domanda solo sulle domande; l'annuncio intero
    ann = ("Andrea, il lavoro di «Calendario della carta» è pronto: siamo al collaudo. Manca "
           "ancora il giorno del vetro. Con cosa provo?")
    calendario = next(p for p in C.COPIONI if p.id == "svil-differenziata").passi[3]
    ok("se_domanda: una parola nel titolo o in una mancanza detta non basta",
       not re.search(calendario.dati["se_domanda"], V.domande(ann), re.I)
       and re.search(calendario.dati["se_domanda"],
                     V.domande("Una domanda dell'agente. Che giorno passa la carta?"), re.I))
    permesso = next(p for p in C.COPIONI if p.id == "est-notte").passi[3]
    ok("se_domanda: il permesso solo nella frase della domanda",
       re.search(permesso.dati["se_domanda"], V.domande(
           "Per la funzione mi servirebbe comandare le luci. Posso metterlo tra i permessi "
           "della funzione?"), re.I)
       and not re.search(permesso.dati["se_domanda"], V.domande(
           "Il lavoro è pronto: i permessi sono quelli detti. Con cosa provo?"), re.I))
    lascia = next(p for p in C.COPIONI if p.id == "svil-differenziata").passi[9]
    ok("ricollaudo riuscito: detto nell'annuncio intero, non la sola regola nel log",
       not V.controlla({"annuncio_testo": lascia.attese["annuncio_testo"]}, {}, "",
                       {"annuncio": "Andrea, il lavoro è pronto.",
                        "seguito": "L'ho già riprovata con «le pile»: ora va. Con cosa provo?"})
       and V.controlla({"annuncio_testo": lascia.attese["annuncio_testo"]}, {}, "",
                       {"annuncio": "Andrea, il lavoro è pronto.",
                        "seguito": "L'ho riprovata: con «le pile» non va ancora."}))
    cre = {c.id: C.apre_sviluppo(c) for c in C.COPIONI}
    ok("est_@: azzerata nei copioni che aprono uno sviluppo, tenuta in quelli che usano",
       cre["est-cambio"] and cre["gioco-porte"] and cre["svil-versioni"]
       and not cre["est-notte-contrari"] and not cre["partita-porte"])
    ok("la frase di chi non amministra: «il gioco» solo per un gioco",
       "il gioco" in C.attiva("Giulia", gioco=True)[1].testo
       and "il gioco" not in C.attiva("Giulia")[1].testo
       and C.attiva("Andrea")[1].testo == "Attivala, per favore.")
    from prove.e2e.__main__ import Runner

    class SatFinto:
        def __init__(self, ev):
            self.ev = ev

        def eventi_dopo(self, t, tipo):
            return [(x, k, d) for x, k, d in self.ev if x > t and k == tipo]
    finto = type("R", (), {"sat": {"studio": SatFinto([
        (1.0, "frase", "Va bene, comincio."), (2.0, "fine_turno", None),
        (500.0, "frase", "Andrea, il lavoro è pronto: siamo al collaudo."),
        (501.0, "frase", "Lo apro in prova?")])}})()
    dopo = Runner._frasi_dopo(finto, 0.5)
    ok("runner: le frasi dopo la fine del turno, tutte e non la risposta",
       "Lo apro in prova?" in dopo and "comincio" not in dopo, dopo)
    q = V.quantili([1.0, 2.0, 3.0, 4.0])
    ok("quantili", q["n"] == 4 and q["mediana"] == 3.0 and q["max"] == 4.0, str(q))

    # Niente dati personali nei file della prova
    # Nome di chi amministra nei registri veri, nomi DuckDNS, percorsi con l'utente, indirizzi
    # IP che non siano 127.0.0.1 (gli altri nomi veri li controlla prova_dati_privati)
    vietati = re.compile(r"\bDario\b|duckdns|/home/\w|"
                         r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", re.I)
    trovati = []
    for f in sorted((RADICE / "prove" / "e2e").glob("*")):
        if f.suffix not in (".py", ".tsv"):
            continue
        for n, riga in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            m = vietati.search(riga)
            if m and "127.0.0.1" not in m.group(0):
                trovati.append(f"{f.name}:{n}: {m.group(0)}")
    ok("nessun nome vero, utente o indirizzo nei file della prova", not trovati,
       "; ".join(trovati[:5]))
    from prove.e2e import lancia
    cmd = lancia.comando_runner(["--aree", "casa"])
    ok("comando sulla DGX: solo percorsi relativi alla home", "~/" in cmd
       and "/home/" not in cmd and "--aree casa" in cmd, cmd[:120])
    print(f"\n{'Tutto bene.' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
