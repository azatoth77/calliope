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
          "voce_studio", "voce_studio_ferma"}


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
            for k in p.attese:
                if k not in CHIAVI:
                    problemi.append(f"{dove}: attesa sconosciuta {k}")
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
    ok("copioni ben fatti (persone, registrazioni, attese, regex)", not problemi,
       "; ".join(problemi[:8]))
    ok("un copione per ogni area chiesta", {"voce-vera", "casa", "agenda", "minori",
                                            "satelliti", "immagini", "allegati", "agenti",
                                            "estensioni", "personalita", "permessi",
                                            "biblioteca", "web"} <= {c.area for c in C.COPIONI})
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
    ferma = {"tool": [{"nome": "lavori_annulla"}], "esito": "risposta"}
    ok("fermati-ordine: lavori_annulla che non ferma niente va bene", not V.controlla(
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
