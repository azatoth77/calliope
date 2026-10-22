"""La scala delle spinte dell'agente, a secco (22/10/2026, issue #224, epic #86; area
agenti-estensioni; analisi docs/ricerche/2026-10-19-solidita-harness-sviluppo.md § 3.4, n. 23,
24, 26, 27).

1. il vocabolario: ogni testo della scala (spinte e note nei risultati) ha la forma «il fatto,
   poi i passi ammessi», i passi del vocabolario chiuso, nessun passo solo escluso proposto,
   nessuna coppia incompatibile (uno ammette ciò che l'altro esclude); contrario: la nota della
   terza lettura di prima («scrivi la versione corretta con scrivi_file») contro le riscritture
   è incompatibile;
2. il tono: nessun testo con le parole di rimprovero o gli imperativi sul pensiero (l'elenco in
   `spinte.PAROLE_VIETATE`, più le frasi di prima); contrario: i testi di prima le hanno;
3. la scala: al più una spinta per passata, la più alta; l'avviso di chiusura lasciato torna alla
   passata dopo; nel ciclo l'avviso e le riscritture nella stessa passata danno un messaggio solo
   (le riscritture lasciate, contate); in nessun messaggio dell'harness due spinte;
4. il giro a vuoto e il ragionamento senza strumenti in uno sviluppo: tappa «vuoto» e
   «ragionamento», con la frase a voce breve e senza gergo; contrari: fuori da uno sviluppo il
   «limite» di prima;
5. l'attesa della voce non fa scattare la guardia dei minuti senza strumenti; contrario: lo
   stesso tempo passato dall'agente la fa scattare;
6. `senza_novita` è un conto di fila: riparte con una novità (anche un file mai letto), al
   gradino (SENZA_NOVITA_FILA) una spinta sola; contrari: una passata in meno, la fila spezzata,
   sei file mai letti uno per passata.

    python prove\\prova_scala_spinte.py
"""

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
sys.path.insert(0, str(RADICE / "prove"))

import prova_agente_guida as G  # noqa: E402
from prova_strumenti_onesti import (CONSEGNA, ESEGUI, GIUSTO, SBAGLIATO, TEST, Copione,  # noqa: E402
                                    scrivi)

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


def sezione(t):
    print(f"\n— {t}", flush=True)


def gira(tmp, nome, passate, max_passi=14, tappe=False, prepara=None, segnali=None):
    """Agente.codice con il copione: (lavoro, risultato o {"eccezione"…}, log, copione)."""
    from calliope.agenti.ciclo import Lavoro
    cli = Copione(passate)
    log = []
    ag = G.agente(cli, log)
    ag.max_passi = max_passi
    if prepara is not None:
        prepara(ag, cli)
    sb = G.sandbox(tmp, nome)
    lav = Lavoro(nome, "codice", "una funzione che somma")
    lav.tappe = tappe
    if segnali is not None:
        lav.segnali = dict(segnali)
    try:
        ris = ag.codice(lav, sb)
    except Exception as e:  # noqa: BLE001 — Limite
        ris = {"eccezione": type(e).__name__, "tipo": getattr(e, "tipo", ""), "motivo": str(e)}
    return lav, ris, log, cli


def utenti(lav) -> list[str]:
    return [str(m.get("content")) for m in (lav.contesto or {}).get("messages", [])
            if m.get("role") == "user"]


def utenti_corpi(cli) -> list[str]:
    """I messaggi «user» dell'ultima richiesta al modello (la storia intera)."""
    return [str(m.get("content")) for m in (cli.corpi[-1] if cli.corpi else [])
            if m.get("role") == "user"]


# Le frasi di prima (fino al 21/10), per i contrari
VECCHIE = ("Ti ho fermato: stai ripetendo lo stesso ragionamento. Non ripensarci: decidi adesso e "
           "chiama uno strumento.",
           "Hai riscritto a.py per intero 3 volte e i test falliscono ancora allo stesso modo: "
           "riscriverlo non serve.",
           "Stai ragionando da 12000 token senza usare gli strumenti. Smetti di pensare e agisci "
           "adesso con una chiamata di funzione.",
           "Adesso chiudi: non cominciare cose nuove, sistema quello che hai.",
           "Ragiona meno e chiama lo strumento del prossimo passo, o consegna.")


def vietate(testo: str) -> list[str]:
    from calliope.agenti import spinte as sp
    return [p for p in sp.PAROLE_VIETATE if re.search(p, testo, re.I)]


# ═══════════════════════════ 1–2. vocabolario e tono ═══════════════════════════

def prova_vocabolario():
    sezione("1–2. la forma, il vocabolario, le coppie incompatibili, il tono")
    from calliope.agenti import ciclo as C
    from calliope.agenti import spinte as sp
    insiemi = {"fuori da uno sviluppo e ricerca": sp.tutte(), "sviluppo": sp.tutte(tappe=True)}
    tutte = [s for v in insiemi.values() for s in v]
    verifica("ogni testo della scala: un fatto e una volta «Passi possibili:»",
             all(s.testo.count("Passi possibili:") == 1 and s.fatto
                 and not s.testo.startswith("Passi possibili") for s in tutte),
             str([s.testo for s in tutte if s.testo.count("Passi possibili:") != 1]))
    verifica("i passi ammessi sono del vocabolario, mai uno solo escluso",
             all(set(s.ammessi) <= set(sp.PASSI) and not set(s.ammessi) & sp.SOLO_ESCLUSI
                 for s in tutte), str([(s.nome, s.ammessi) for s in tutte]))
    for nome, ins in insiemi.items():
        coppie = [(a.nome, b.nome, sorted(sp.incompatibili(a, b))) for i, a in enumerate(ins)
                  for b in ins[i + 1:] if sp.incompatibili(a, b)]
        verifica(f"{nome}: nessuna coppia incompatibile fra i {len(ins)} testi", not coppie,
                 str(coppie[:5]))
    vecchia = sp.Spinta("agente_rilettura", "hai letto questo file 3 volte senza cambiarlo.",
                        "Scrivi adesso la versione corretta con scrivi_file", ("riscrivi",))
    verifica("contrario: la nota della terza lettura di prima («scrivi_file») contro le "
             "riscritture è incompatibile",
             sp.incompatibili(vecchia, sp.riscritture("a.py", 3)) == {"riscrivi"})
    verifica("contrario: in uno sviluppo la consegna senza condizione (P4) contro l'avviso della "
             "tappa è incompatibile, e con le tappe si dice con la condizione",
             sp.incompatibili(sp.prosa(), sp.fine("tappa")) == {"consegna"}
             and sp.incompatibili(sp.senza_novita(6), sp.fine("tappa")) == {"consegna"}
             and "se il lavoro è finito" in sp.senza_novita(6, tappe=True).testo
             and "se il lavoro è finito" in sp.ripetizioni("x", tappe=True).testo)
    verifica("ogni gradino della scala ha un posto diverso (l'ordine è uno solo)",
             len({g.posto for g in sp.GRADINI.values()}) == len(sp.GRADINI))

    testi = [s.testo for s in tutte] + list(C.AVVISO_FINE.values()) + [
        C.SPINTA_CONSEGNA, C.PROSA_FATTUALE, C.SPINTA_STRUMENTI, C.USCITA_TRONCATA,
        C.USCITA_TRONCATA_TESTO, C.USCITA_TRONCATA_RICERCA, C.USCITA_TRONCATA_STRUMENTO,
        C.USCITA_TRONCATA_TESTO_RICERCA, C.USCITA_TRONCATA_PENSIERO,
        C.nota_riscrittura("a = 1\n" * 40, "a = 1\n" * 39 + "a = 2\n", "a.py")]
    # I fatti della fotografia dei test (#232) nei risultati degli strumenti: fatti, non spinte,
    # ma con lo stesso tono (unione con epic-86-harness)
    from calliope.agenti import fotografia_test as ft
    due = ("import unittest\n\n\nclass P(unittest.TestCase):\n    def test_a(self):\n"
           "        self.assertEqual(1 + 1, 2)\n\n    def test_b(self):\n"
           "        self.assertEqual(2 + 2, 4)\n")
    uno = due.split("\n\n    def test_b")[0] + "\n"
    foto = [ft.fatto_per_agente([{"file": "test_a.py", "tolto": False, "test_meno": 1,
                                  "asserzioni_meno": 1, "skip_piu": 0, "banali_piu": 0}]),
            ft.nota_scrittura("test_a.py", due, uno)]
    verifica("i fatti della fotografia dei test (#232) ci sono, da controllare col tono",
             all(foto), str(foto))
    testi += foto
    brutti = [(t[:60], vietate(t)) for t in testi if vietate(t)]
    verifica("nessun testo con le parole di rimprovero o gli imperativi sul pensiero",
             not brutti, str(brutti))
    verifica("contrario: le frasi di prima le hanno tutte",
             all(vietate(v) for v in VECCHIE), str([v[:30] for v in VECCHIE if not vietate(v)]))
    s = sp.ripetizioni("La soluzione più semplice è riscrivere tutto",
                       {"test": "t", "errore": "AssertionError: -1 != 5",
                        "dove": "test_programma.py:7"})
    verifica("la spinta dopo il giro a vuoto: il fatto (la frase, l'errore) e i passi sul punto",
             "ripeteva la stessa frase" in s.testo and "AssertionError: -1 != 5" in s.fatto
             and "test_programma.py:7" in s.fatto
             and "leggi_file con percorso «test_programma.py» e riga 7" in s.passi
             and "modifica_file su quel punto" in s.passi, s.testo)
    s = sp.senza_strumenti(12000, ["scrivi_file", "esegui_test", "consegna"])
    verifica("senza strumenti: i passi solo fra gli strumenti offerti (né piano né "
             "scarica_esempio a un programma)",
             "12.000 token" in s.testo and "scrivi_file" in s.testo and "piano" not in s.testo
             and "scarica_esempio" not in s.testo, s.testo)
    s = sp.ripetizioni("x", ricerca=True, nomi=["grafo_cammino", "grafo_documenti",
                                                "grafo_schema", "grafo_trova", "consegna"])
    verifica("la ricerca coi documenti di casa parte da grafo_trova e grafo_schema (Q3)",
             "Passi possibili: grafo_trova o grafo_schema" in s.passi
             and "grafo_cammino" not in s.passi, s.passi)
    s = sp.ripetizioni("x", prima_il_piano=True)
    p = sp.prosa(prima_il_piano=True)
    verifica("prima del piano il giro a vuoto e la prosa propongono solo piano (Q6)",
             s.passi == "Passi possibili: piano." and p.passi == "Passi possibili: piano.",
             s.passi + " " + p.passi)
    s = sp.ripetizioni("x", ricerca=True, nomi=["biblioteca_cerca", "web_cerca", "consegna"])
    verifica("il giro a vuoto nella ricerca (P3): i suoi strumenti e la relazione, mai "
             "scrivi_file né esegui_test",
             "biblioteca_cerca o web_cerca" in s.passi and "relazione" in s.passi
             and not re.search(r"scrivi_file|esegui_test|modifica_file|cosa funziona", s.testo)
             and "leggi_file" not in s.passi, s.testo)


# ═══════════════════════════ 3. la scala ═══════════════════════════

def prova_scala(tmp: Path):
    sezione("3. al più una spinta per passata, la più alta; i fatti arrivano sempre")
    from calliope.agenti import spinte as sp
    from calliope.agenti.ciclo import AVVISO_FINE, Lavoro
    sc = sp.Scala()
    sc.proponi(sp.consegna())
    sc.proponi(sp.riscritture("a.py", 3))
    sc.proponi(sp.troncata("codice"))
    sc.proponi(sp.fine("codice"))
    sc.proponi(None)
    s, lasciate = sc.scegli()
    verifica("quattro proposte: esce l'avviso di chiusura (in cima, anche sopra la troncata), "
             "le altre lasciate",
             s.nome == "agente_avviso_fine" and [x.nome for x in lasciate] ==
             ["agente_uscita_troncata", "agente_riscrittura_ripetuta", "agente_spinta_consegna"]
             and not sc, f"{s.nome} {[x.nome for x in lasciate]}")

    log = []
    ag = G.agente(Copione([]), log)
    lav = Lavoro("S1", "codice", "x")
    msgs = [{"role": "user", "content": "Compito: x"}]
    err = {"test": "t", "errore": "AssertionError: -1 != 5", "dove": "test_programma.py:7"}
    sc.proponi(sp.fine("codice"))
    sc.proponi(sp.troncata("codice"))
    sc.proponi(sp.ripetizioni("una frase", err))
    ag._dici(lav, msgs, sc)
    m = msgs[-1]["content"]
    verifica("i fatti delle lasciate arrivano (la troncata, l'errore col suo punto), i passi "
             "solo dell'avviso, una volta «Passi possibili»",
             lav.avvisato is True and m.endswith(AVVISO_FINE["codice"])
             and sp.TRONCATA_TESTO in m and "test_programma.py:7" in m
             and m.count("Passi possibili:") == 1 and "leggi_file con percorso" not in m
             and (lav.segnali.get("spinte_lasciate") or {}).get("agente_uscita_troncata") == 1,
             m)
    verifica("…l'avviso con la sua regola; la troncata non conta la regola una seconda volta",
             (lav.segnali.get("regole") or {}).get("agente_avviso_fine") == 1
             and "agente_uscita_troncata" not in (lav.segnali.get("regole") or {})
             and any("spinta agente_avviso_fine" in x for x in log), str(log[-2:]))

    # P1: i fatti del revisore «ora» non competono: la prosa lasciata, i fatti arrivano
    lav = Lavoro("S2", "codice", "x")
    lav.tappe = True
    msgs = [{"role": "user", "content": "Compito: x"}]
    sc.proponi(sp.prosa(True))
    sc.fatto("Il revisore ha guardato il test rosso: è giusto, sbaglia somma in programma.py:2.")
    sc.proponi(sp.fine("tappa"))
    ag._dici(lav, msgs, sc)
    m = msgs[-1]["content"]
    verifica("la prosa con i fatti del revisore contro l'avviso: esce l'avviso, i fatti del "
             "revisore arrivano lo stesso (P1)",
             "programma.py:2" in m and m.count("Passi possibili:") == 1
             and AVVISO_FINE["tappa"] in m, m)
    msgs.append({"role": "tool", "tool_name": "leggi_file", "content": "{}"})
    sc.fatto("Il revisore: un fatto da solo.")
    ag._dici(lav, msgs, sc)
    verifica("…e un fatto senza nessuna spinta arriva da solo",
             msgs[-1]["role"] == "user" and msgs[-1]["content"] == "Il revisore: un fatto da solo.",
             str(msgs[-1]))

    # Le «una volta per lavoro» lasciate: senza il fatto, tornano, e dopo LASCIATE_MAX passano
    lav = Lavoro("S3", "codice", "x")
    msgs = [{"role": "user", "content": "Compito: x"}]
    for i in range(sp.LASCIATE_MAX):
        sc.proponi(sp.consegna())
        sc.proponi(sp.riscritture("a.py", 3))
        ag._dici(lav, msgs, sc)
        msgs.append({"role": "tool", "tool_name": "leggi_file", "content": "{}"})
    verifica("la spinta a consegnare lasciata: senza il suo fatto, non segnata detta",
             not lav.segnali.get("spinta_consegna")
             and not any("I tuoi test passano" in str(x.get("content")) for x in msgs)
             and lav.segnali["spinte_lasciate"]["agente_spinta_consegna"] == sp.LASCIATE_MAX,
             str(lav.segnali))
    sc.proponi(sp.consegna())
    sc.proponi(sp.riscritture("a.py", 3))
    ag._dici(lav, msgs, sc)
    verifica(f"…lasciata {sp.LASCIATE_MAX} volte passa davanti (P5), con il fatto delle "
             "riscritture", lav.segnali.get("spinta_consegna") is True
             and msgs[-1]["content"].endswith(sp.consegna().testo)
             and "Hai riscritto a.py" in msgs[-1]["content"], msgs[-1]["content"])

    # Il log dell'avviso proposto e lasciato (la spinta a consegnare promossa) non si ripete
    from calliope.agenti.ciclo import Agente
    log_f = []
    finto = SimpleNamespace(tetto_token=lambda lav: 100_000, trascorso=lambda lav: 10,
                            passi_giro=lambda lav: 22, max_passi=24, token_giro=lambda lav: 10,
                            tempo_max_s=1800, log=log_f.append)
    lav = Lavoro("S4", "codice", "x")
    lav.segnali = {}
    for _ in range(3):
        Agente._avviso_fine(finto, lav)
    verifica("l'avviso proposto tre volte senza uscire: nel log una volta (P5)",
             sum("avviso di chiusura" in x for x in log_f) == 1, str(log_f))

    # Nel ciclo: tre riscritture intere del file lungo con lo stesso errore, e alla passata dopo
    # l'avviso di chiusura (restano 2 passate). Prima uscivano nello stesso messaggio
    lungo = "".join(f"# riga {i}\n" for i in range(70))
    passate = ([[scrivi("programma.py", lungo + SBAGLIATO), scrivi("test_programma.py", TEST)],
                [ESEGUI]]
               + [[scrivi("programma.py", lungo + f"# versione {i}\n" + SBAGLIATO)]
                  for i in range(3)]
               + [[scrivi("programma.py", lungo + GIUSTO), ESEGUI, CONSEGNA]])
    lav, ris, log, cli = gira(tmp, "insieme", passate, max_passi=7)
    ut = utenti_corpi(cli)
    doppie = [u[:200] for u in ut if u.count("Passi possibili:") > 1]
    insieme = [u for u in ut if u.endswith(sp.fine("codice").testo)]
    verifica("riscritture e avviso nella stessa passata: un messaggio, i passi dell'avviso, il "
             "fatto delle riscritture",
             ris.get("esito") == "fatto" and not doppie and len(insieme) == 1
             and "Hai riscritto programma.py per intero 3 volte" in insieme[0]
             and "leggi_file con percorso" not in insieme[0]
             and (lav.segnali.get("spinte_lasciate") or {}).get("agente_riscrittura_ripetuta")
             == 1, str(ris)[:200] + str(doppie) + str(insieme))
    verifica("…le regole: l'avviso contato, la riscrittura no (non detta come spinta)",
             (lav.segnali.get("regole") or {}).get("agente_avviso_fine") == 1
             and "agente_riscrittura_ripetuta" not in (lav.segnali.get("regole") or {}),
             str(lav.segnali.get("regole")))
    verifica("…il log dell'avviso una volta, e nessuna «regola» della riscrittura lasciata (Q2)",
             sum("avviso di chiusura (" in x for x in log) == 1
             and not any("regola agente_riscrittura_ripetuta" in x for x in log),
             str(log)[-300:])
    brutti = [u[:60] for u in ut if vietate(u.replace("Compito:", ""))]
    verifica("…e in nessun messaggio dell'harness le parole di rimprovero", not brutti,
             str(brutti))
    lav, ris, log, cli = gira(tmp, "sole", passate, max_passi=14)
    ut = utenti_corpi(cli)
    verifica("contrario: lontano dal tetto la spinta delle riscritture esce, da sola",
             any("Hai riscritto programma.py per intero 3 volte" in u
                 and "leggi_file con percorso" in u for u in ut)
             and not any(u.count("Passi possibili:") > 1 for u in ut)
             and (lav.segnali.get("regole") or {}).get("agente_riscrittura_ripetuta") == 1,
             str(ut)[-400:])

    # M11: la spinta a consegnare lasciata dall'avviso torna alla passata dopo, nel ciclo
    lav, ris, log, cli = gira(tmp, "consegna-torna", [
        [scrivi("programma.py", GIUSTO), scrivi("test_programma.py", TEST)], [ESEGUI],
        [{"name": "elenca_file", "arguments": {}}], [CONSEGNA]], max_passi=4)
    ut = utenti_corpi(cli)
    verifica("nel ciclo la spinta a consegnare lasciata dall'avviso torna, una volta",
             ris.get("esito") == "fatto" and sum(sp.consegna().testo in u for u in ut) == 1
             and sum(AVVISO_FINE["verde"] in u for u in ut) == 1
             and lav.segnali.get("spinta_consegna") is True, str(ut)[-500:])

    # Q1 (seconda revisione): nel ciclo vero, i fatti del revisore «ora» dopo la seconda prosa
    # con lo stato consegnabile arrivano alla passata dopo, insieme all'avviso di chiusura.
    # `_consegna_dalla_prosa` dice no come quando il revisore giudica gli esempi rossi: scrive i
    # suoi fatti con `_fatti_revisore(ora=True)` (#190) e non consegna
    fatto_rev = "Il revisore: l'esempio 2 è giusto, sbaglia la conversione in estensione.py:4."

    def revisore_no(ag, cli):
        def no(lav, *a, **k):
            ag._fatti_revisore(lav, {"fatti": [fatto_rev], "domande": []}, ora=True)
            return None
        ag._consegna_dalla_prosa = no
    lav, ris, log, cli = gira(tmp, "revisore-ora", [
        [scrivi("programma.py", GIUSTO), scrivi("test_programma.py", TEST)], [ESEGUI],
        "Ho finito.", "Ho finito davvero.", [CONSEGNA]], max_passi=6, prepara=revisore_no)
    ut = utenti_corpi(cli)
    con = [u for u in ut if fatto_rev in u]
    verifica("nel ciclo i fatti del revisore «ora» dopo la prosa arrivano alla passata dopo, con "
             "l'avviso di chiusura (Q1)",
             ris.get("esito") == "fatto" and len(con) == 1 and AVVISO_FINE["verde"] in con[0]
             and not lav.segnali.get("revisore_fatti_ora"), str(ut)[-600:])
    verifica("…e nel log nessuna «regola» di una spinta lasciata (Q2)",
             not any("(regola agente_" in x for x in log), str([x for x in log
                                                                if "(regola" in x]))
    lav, ris, log, cli = gira(tmp, "avviso-giro", [
        [scrivi("programma.py", GIUSTO), scrivi("test_programma.py", TEST)], [ESEGUI],
        [CONSEGNA]], max_passi=4, segnali={"avviso_fine_log": True})
    verifica("l'avviso proposto e mai detto nel giro di prima va nel log del giro dopo (Q2)",
             sum("avviso di chiusura (" in x for x in log) == 1, str(log)[-300:])

    # P3 nel ciclo della ricerca: il giro a vuoto con i passi della ricerca
    import prova_strumenti_onesti as S
    cerca = {"name": "web_cerca", "arguments": {"domanda": "storia del borgo"}}
    lav, ris, cli, web, esiti = S.ricerca([[cerca], {"giro_a_vuoto": "Devo cercare ancora"},
                                           [S._consegna_r()]])
    ut = utenti_corpi(cli)
    detta = [u for u in ut if "ripeteva la stessa frase" in u]
    verifica("nella ricerca il giro a vuoto propone gli strumenti della ricerca e la relazione",
             ris.get("esito") == "fatto" and len(detta) == 1 and "web_cerca" in detta[0]
             and "relazione" in detta[0]
             and not re.search(r"scrivi_file|esegui_test", detta[0]), str(detta))


# ═══════════════════════════ 4. il vuoto e il ragionamento come tappe ═══════════════════════════

def prova_tappe(tmp: Path):
    sezione("4. il giro a vuoto e il ragionamento senza strumenti: tappe in uno sviluppo")
    from calliope.agenti.servizio import PERCHE_TAPPA, frase_tappa, segnali_detti
    vuoto = [{"giro_a_vuoto": "La soluzione più semplice è riscrivere tutto"}] * 3
    lav, ris, log, cli = gira(tmp, "vuoto", [[scrivi("programma.py", SBAGLIATO)]] + vuoto,
                              tappe=True)
    verifica("in uno sviluppo tre giri a vuoto di fila: tappa «vuoto», non «limite»",
             ris.get("esito") == "tappa" and ris.get("tipo_limite") == "vuoto", str(ris)[:300])
    lav.risultato = ris
    frase = frase_tappa(lav, "la somma")
    verifica("…a voce il perché, breve e senza gergo",
             PERCHE_TAPPA["vuoto"] in frase and not re.search(
                 r"token|passat|a_vuoto|max_tokens|strument", frase.split(".")[0]), frase)
    r = {"tipo_limite": "vuoto", "segnali": {"frasi": [
        "ha ripetuto lo stesso ragionamento (3 passate fermate)", "ha riscritto a.py 3 volte"]}}
    verifica("…e il segnale che il perché dice già non si ripete",
             segnali_detti(r) == ["ha riscritto a.py 3 volte"]
             and len(segnali_detti(dict(r, tipo_limite="passate"))) == 2, str(segnali_detti(r)))
    import prova_apri_gioco_tappa as A
    import prova_fasi_agente_2 as F2
    lav, ris, log, sb = A._estensione(tmp, "vuoto-verde", [
        [F2.scrivi("estensione.py", F2.GIUSTA)], [F2.ESEGUI_TEST], "ripete", "ripete", "ripete"],
        max_passi=12)
    verifica("alla tappa «vuoto» con gli esempi di accettazione e i test verdi: «fatto» d'ufficio "
             "(TAPPA_CONSEGNABILE, #192)",
             ris.get("esito") == "fatto" and ris.get("consegna_al_tetto") == "tappa"
             and ris.get("consegna_al_tetto_giro") == "vuoto"
             and (lav.segnali.get("regole") or {}).get("agente_consegna_alla_tappa") == 1,
             str(ris)[:300])
    lav, ris, log, sb = A._estensione(tmp, "vuoto-rosso", [
        [F2.scrivi("estensione.py", F2.SBAGLIATA)], [F2.ESEGUI_TEST], "ripete", "ripete",
        "ripete"], max_passi=12)
    verifica("contrario: gli esempi rossi, la tappa «vuoto» resta",
             ris.get("esito") == "tappa" and ris.get("tipo_limite") == "vuoto"
             and str(lav.segnali.get("tappa_no")).startswith("esempi di accettazione rossi"),
             str(ris)[:300] + str(lav.segnali.get("tappa_no")))
    lav, ris, log, cli = gira(tmp, "vuoto-fuori", [[scrivi("programma.py", SBAGLIATO)]] + vuoto)
    verifica("contrario: fuori da uno sviluppo il «limite» di prima («a_vuoto»)",
             ris.get("eccezione") == "Limite" and ris.get("tipo") == "a_vuoto", str(ris))

    pensa = [{"content": "", "eval": 13000}] * 2
    lav, ris, log, cli = gira(tmp, "pensa", [[scrivi("programma.py", SBAGLIATO)]] + pensa,
                              tappe=True)
    verifica("in uno sviluppo il ragionamento senza strumenti due volte: tappa «ragionamento»",
             ris.get("esito") == "tappa" and ris.get("tipo_limite") == "ragionamento"
             and "ha ragionato per" in ris.get("motivo", ""), str(ris)[:300])
    lav.risultato = ris
    frase = frase_tappa(lav, "la somma")
    verifica("…a voce il perché, senza gergo (P8: né token né strumenti)",
             PERCHE_TAPPA["ragionamento"] in frase and not re.search(
                 r"token|passat|max_tokens|strument", frase.split(".")[0]), frase)
    ut = utenti(lav)
    verifica("…e prima la spinta, una, nella forma della scala",
             sum("non è partita nessuna chiamata di funzione" in u for u in ut) == 1, str(ut))
    lav, ris, log, cli = gira(tmp, "pensa-fuori", [[scrivi("programma.py", SBAGLIATO)]] + pensa)
    verifica("contrario: fuori da uno sviluppo il «limite» di prima",
             ris.get("eccezione") == "Limite" and "ha ragionato per" in ris.get("motivo", "")
             and not ris.get("tipo"), str(ris))


# ═══════════════════════════ 5. l'attesa della voce ═══════════════════════════

class _Orologio:
    t = 1000.0

    def monotonic(self):
        return _Orologio.t

    def __getattr__(self, n):
        import time
        return getattr(time, n)


def prova_attesa_voce(tmp: Path):
    sezione("5. l'attesa della voce fuori dalla guardia dei minuti senza strumenti")
    from calliope.agenti import ciclo as C
    vero_time = C.time
    lavoro = [[scrivi("programma.py", GIUSTO), scrivi("test_programma.py", TEST)], [ESEGUI],
              [CONSEGNA]]

    def voce(ag, cli):
        # L'arbitro fa aspettare la voce 200 s prima di ogni passata
        def attendi(annulla):
            _Orologio.t += 200
            return 200.0
        ag.arbitro.attendi = attendi

    def agente_lento(ag, cli):
        # Gli stessi 200 s, ma passati dall'agente nella passata
        vero = cli.chat

        def chat(body, **k):
            _Orologio.t += 200
            return vero(body, **k)
        cli.chat = chat
    def interrotta(ag, cli):
        # La voce prende la precedenza a metà della passata, dopo 200 s: si rifà
        from calliope.agenti.remoto import Interrotto
        vero = cli.chat
        stato = {"prima": True}

        def chat(body, **k):
            from prova_agente_guida import e_revisore
            if not e_revisore(body) and stato["prima"]:
                stato["prima"] = False
                _Orologio.t += 200
                raise Interrotto()
            stato["prima"] = True
            return vero(body, **k)
        cli.chat = chat
    C.time = _Orologio()
    try:
        lav, ris, log, cli = gira(tmp, "voce", ["Ci penso.", "Ci penso."] + lavoro,
                                  prepara=voce)
        verifica("due passate senza chiamate dopo 200 s d'attesa della voce ciascuna: niente "
                 "guardia", ris.get("esito") == "fatto"
                 and not any("senza strumenti" in x for x in log)
                 and lav.attesa_voce_s >= 400, str(ris)[:200] + str(log[-3:]))
        lav, ris, log, cli = gira(tmp, "lento", ["Ci penso.", "Ci penso."] + lavoro,
                                  prepara=agente_lento)
        verifica("contrario: gli stessi 400 s passati dall'agente fanno scattare la guardia",
                 any("senza strumenti" in x for x in log), str(log[-3:]))
        # P7: la passata troncata con l'attesa della voce, poi 300 s di prosa dell'agente: la
        # voce si toglie una volta sola, e la guardia scatta
        from prova_strumenti_onesti import A_META

        def troncata_voce(ag, cli):
            prima = {"si": True}

            def attendi(annulla):
                if prima["si"]:
                    prima["si"] = False
                    _Orologio.t += 200
                    return 200.0
                return 0.0
            ag.arbitro.attendi = attendi
            vero = cli.chat

            def chat(body, **k):
                if cli.passate and isinstance(cli.passate[0], str):
                    _Orologio.t += 150
                return vero(body, **k)
            cli.chat = chat
        lav, ris, log, cli = gira(tmp, "tronca-voce", [A_META, "Ci penso.", "Ci penso."] + lavoro,
                                  prepara=troncata_voce)
        verifica("la troncata dopo 200 s di voce e 300 s di prosa: la guardia scatta (la voce "
                 "tolta una volta, P7)", any("senza strumenti" in x for x in log), str(log[-3:]))
        lav, ris, log, cli = gira(tmp, "interrotta", ["Ci penso.", "Ci penso."] + lavoro,
                                  prepara=interrotta)
        # Dal 22/10 (#225, P1 della prima revisione della PR #234) la passata fermata va in
        # `rifatte_s` (fuori dalla sola guardia), e in `attesa_voce_s` solo la voce vera
        verifica("due passate fermate per la voce dopo 200 s, poi rifatte: niente guardia (M4)",
                 ris.get("esito") == "fatto" and lav.cedimenti >= 2
                 and not any("senza strumenti" in x for x in log)
                 and lav.rifatte_s >= 400, str(ris)[:200] + str(log[-3:]))
    finally:
        C.time = vero_time


# ═══════════════════════════ 6. senza novità di fila ═══════════════════════════

def prova_senza_novita(tmp: Path):
    sezione("6. le passate senza novità, di fila, con il loro gradino")
    from calliope.agenti import spinte as sp
    leggi = {"name": "elenca_file", "arguments": {}}
    n = sp.SENZA_NOVITA_FILA
    inizio = [[scrivi("programma.py", SBAGLIATO), scrivi("test_programma.py", TEST)], [ESEGUI]]
    fine = [[scrivi("programma.py", GIUSTO)], [ESEGUI], [CONSEGNA]]
    lav, ris, log, cli = gira(tmp, "novita", inizio + [[leggi]] * n + fine, max_passi=20)
    ut = utenti_corpi(cli)
    detta = [u for u in ut if f"Le ultime {n} passate non hanno cambiato" in u]
    verifica(f"{n} passate di fila senza novità: la spinta, una volta, con l'ultimo errore",
             len(detta) == 1 and "AssertionError" in detta[0] and "modifica_file" in detta[0]
             and (lav.segnali.get("regole") or {}).get("agente_senza_novita") == 1,
             str(ut)[-500:])
    verifica("…e il conto riparte con la novità (di fila, non un totale)",
             ris.get("esito") == "fatto" and lav.segnali.get("senza_novita") == 0,
             str(lav.segnali.get("senza_novita")))
    lav, ris, log, cli = gira(tmp, "novita-meno", inizio + [[leggi]] * (n - 1) + fine,
                              max_passi=20)
    verifica(f"contrario: {n - 1} passate senza novità, nessuna spinta",
             not any("Le ultime" in u for u in utenti_corpi(cli))
             and "agente_senza_novita" not in (lav.segnali.get("regole") or {}),
             str(utenti_corpi(cli))[-300:])
    meta = (n - 1) // 2 or 1
    lav, ris, log, cli = gira(tmp, "novita-spezzata", inizio + [[leggi]] * meta
                              + [[scrivi("altro.py", "x = 1\n")]] + [[leggi]] * meta + fine,
                              max_passi=20)
    verifica("contrario: le passate senza novità spezzate da una novità non fanno una fila",
             not any("Le ultime" in u for u in utenti_corpi(cli)), str(utenti_corpi(cli))[-300:])
    note = [scrivi(f"note/n{i}.txt", f"nota {i}\n") for i in range(n)]
    nuove = [[{"name": "leggi_file", "arguments": {"percorso": f"note/n{i}.txt"}}]
             for i in range(n)]
    lav, ris, log, cli = gira(tmp, "novita-letture", [inizio[0] + note] + inizio[1:] + nuove
                              + fine, max_passi=30)
    detta = [u for u in utenti_corpi(cli) if "Le ultime" in u]
    verifica(f"contrario: {n} file mai letti, letti uno per passata, non sono un giro a vuoto",
             not detta and ris.get("esito") == "fatto", str(detta)[:300])
    rilegge = [[{"name": "leggi_file", "arguments": {"percorso": "note/n0.txt"}}]] * (n + 1)
    lav, ris, log, cli = gira(tmp, "novita-riletture", [inizio[0] + note] + inizio[1:] + rilegge
                              + fine, max_passi=30)
    verifica(f"…lo stesso file riletto {n} volte dopo la prima sì",
             sum("Le ultime" in u for u in utenti_corpi(cli)) == 1, str(utenti_corpi(cli))[-300:])
    lav, ris, log, cli = gira(tmp, "novita-tante", inizio + [[leggi]] * (2 * n + 1) + fine,
                              max_passi=40)
    verifica(f"{2 * n + 1} passate di fila senza novità: la spinta una volta sola per fila (M9)",
             sum("Le ultime" in u for u in utenti_corpi(cli)) == 1, str(utenti_corpi(cli))[-300:])
    # P2: l'oscillazione A, B, A, B con le riletture arriva al gradino (prima ogni lettura di un
    # contenuto diverso dall'ultimo letto faceva ripartire la fila)
    lunga = "x = 1\n" * 30
    a, b = lunga + SBAGLIATO, lunga + "def somma(a, b):\n    return a * b\n"
    leggi_p = {"name": "leggi_file", "arguments": {"percorso": "programma.py"}}
    osc = [[scrivi("programma.py", a if i % 2 else b), leggi_p] for i in range(n + 3)]
    lav, ris, log, cli = gira(tmp, "oscilla", inizio[:1] + [[scrivi("programma.py", a)]]
                              + [[ESEGUI]] + osc + fine, max_passi=40)
    verifica("A, B, A, B con le riletture: la spinta delle passate senza novità arriva (P2)",
             sum("Le ultime" in u for u in utenti_corpi(cli)) == 1
             and (lav.segnali.get("regole") or {}).get("agente_senza_novita") == 1,
             str(utenti_corpi(cli))[-300:] + str(lav.segnali.get("senza_novita")))
    from calliope.agenti.ciclo import segnali_giro
    s = segnali_giro(SimpleNamespace(segnali={"senza_novita": 7}), 24)
    verifica("a voce la tappa lo dice «di fila»",
             "7 passate di fila senza cambiare i file né l'esito dei test" in s["frasi"],
             json.dumps(s["frasi"], ensure_ascii=False))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="calliope-scala-"))
    os.environ.setdefault("CALLIOPE_CONFIG_LOCALE", str(tmp / "nessuno.yaml"))
    try:
        prova_vocabolario()
        prova_scala(tmp / "scala")
        prova_tappe(tmp / "tappe")
        prova_attesa_voce(tmp / "voce")
        prova_senza_novita(tmp / "novita")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
