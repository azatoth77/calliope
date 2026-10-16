"""
La guardia dei riletti e il criterio di E1 (15/10/2026, issue #11; § 10 punto 5 di
docs/ricerche/2026-10-10-registro-eventi.md, voce 2.1 della roadmap).

    python prove/prova_eventi_guardia.py

1. **Guardia dei riletti** su turni finti del registro: la base è la mediana dei token riletti
   dei giorni d'ombra; un giorno con `eventi: attivo` sopra base × 1,5 ha l'ATTENZIONE in
   `calliope stato --turni` e la riga di `calliope stato`; i contrari (sotto la soglia, pochi
   turni, base troppo piccola, nessun turno attivo); i riletti stimati se il motore non li dice;
   in `calliope stato` solo oggi o ieri (un giorno brutto non resta dopo uno buono né dopo il
   ritorno a ombra), leggendo due file se non ci sono turni con `attivo`; il criterio di E1 su
   tutto il registro.
2. **Il criterio di E1** sul campo `eventi_ombra.proiezione_diversa`: i motivi dichiarati
   (`capito`, `canale_scritto`) non contano; la riga e l'ATTENZIONE in `calliope stato --turni`.
3. **Perché in ombra «zero differenze nel parlato» non si ottiene**: sul ciclo vero (giro
   sintetico di prova_eventi_ciclo: interruzione, stop, timer, frase filtrata, «Sì?») in ombra
   `parlato.diverso` e `eventi_ombra.differenze` non sono zero per costruzione, mentre
   `proiezione_diversa` c'è in ogni turno e vale 0; con `attivo` lo stesso campo vale 0.

Nomi di fantasia, niente rete né audio: pochi secondi.
"""
import json
import os
import sys
import tempfile
import time
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calliope.eventi import misura  # noqa: E402

import prova_eventi_ciclo as pe  # noqa: E402  (il ciclo vero con i finti)

errori = 0


def verifica(nome, ok, info=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({info})" if info and not ok else ""),
          flush=True)


def turno(data, riletti=None, stimati=None, attivo=False, **ombra):
    ca = {}
    if riletti is not None:
        ca["riletti"] = riletti
    if stimati is not None:
        ca["riletti_stimati"] = stimati
    return {"inizio": f"{data}T10:00:00", "esito": "risposta", "cache": ca,
            "eventi_ombra": {"eventi": 5, **({"modo": "attivo"} if attivo else {}), **ombra}}


def base_ombra(n=30, centro=600):
    """`n` turni d'ombra su tre giorni, riletti intorno a `centro`."""
    return [turno(f"2026-10-1{2 + i % 3}", riletti=centro - 100 + (i * 7) % 200)
            for i in range(n)]


# ─────────────────────────── 1. la guardia dei riletti ───────────────────────────
def prova_guardia():
    print("— 1. guardia dei riletti su turni finti")
    turni = base_ombra()
    turni += [turno("2026-10-18", riletti=1000 + i, attivo=True) for i in range(12)]
    turni += [turno("2026-10-19", riletti=850 + i, attivo=True) for i in range(12)]
    turni += [turno("2026-10-20", riletti=2000, attivo=True) for _ in range(5)]
    g = misura.guardia_riletti(turni)
    base = g["base"]
    verifica("la base è la mediana dei giorni d'ombra (riletti dal motore, tre giorni)",
             g["campo"] == "riletti" and base["n"] == 30 and 550 <= base["mediana"] <= 650
             and base["giorni"] == ["2026-10-12", "2026-10-13", "2026-10-14"]
             and g["soglia"] == round(base["mediana"] * 1.5, 1), str(g))
    verifica("un giorno con attivo oltre metà della base: avviso",
             g["giorni"]["2026-10-18"].get("avviso") and "2026-10-18" in g["avvisi"], str(g))
    verifica("contrario: sotto la soglia (850 < 1,5 × base) nessun avviso",
             not g["giorni"]["2026-10-19"].get("avviso") and "2026-10-19" not in g["avvisi"])
    verifica("contrario: pochi turni con attivo nel giorno (5) nessun avviso",
             not g["giorni"]["2026-10-20"].get("avviso"))
    testo = misura.testo(misura.riassunto(turni), guardia=g)
    verifica("calliope stato --turni: la riga della base e l'ATTENZIONE del giorno",
             "Guardia dei riletti" in testo and "avviso oltre" in testo
             and testo.count("ATTENZIONE: con eventi: attivo la mediana dei token riletti") == 1
             and "2026-10-18  con eventi: attivo 12 turni" in testo, testo)
    # Base troppo piccola: nessun confronto, anche con un giorno attivo altissimo
    g2 = misura.guardia_riletti(base_ombra(10) + [turno("2026-10-18", riletti=9000,
                                                         attivo=True) for _ in range(12)])
    verifica("contrario: base d'ombra troppo piccola (10 turni) → nessun avviso, lo dice",
             not g2["avvisi"] and "mediana" not in g2["base"]
             and "ancora nessun confronto" in "\n".join(misura.testo_guardia(g2)), str(g2))
    # Pochi riletti del motore e niente stimati: la riga conta i turni veri
    g5 = misura.guardia_riletti(base_ombra(10))
    t5 = "\n".join(misura.testo_guardia(g5))
    verifica("base piccola senza stimati: la riga dice i turni che ci sono (non «0 turni»)",
             g5["campo"] == "riletti" and "10 turni, 10 con i riletti dal motore" in t5, t5)
    # Solo ombra: la base c'è, nessun giorno attivo, nessun avviso
    g3 = misura.guardia_riletti(base_ombra())
    verifica("solo giorni d'ombra: la base scritta prima dell'accensione, niente avvisi",
             g3["base"].get("mediana") and not g3["giorni"] and not g3["avvisi"]
             and "ATTENZIONE" not in "\n".join(misura.testo_guardia(g3)))
    # Il motore che non dice i riletti: gli stimati
    st = [turno("2026-10-12", stimati=400 + i) for i in range(25)]
    st += [turno("2026-10-18", stimati=700, attivo=True) for _ in range(10)]
    g4 = misura.guardia_riletti(st)
    verifica("senza i riletti del motore: la guardia sui riletti stimati",
             g4["campo"] == "stimati" and g4["avvisi"] == ["2026-10-18"]
             and "riletti stimati" in misura.testo_guardia(g4)[0], str(g4))
    verifica("turni senza eventi_ombra o senza cache: ignorati",
             misura.guardia_riletti([{"inizio": "2026-10-12T10:00", "cache": {"riletti": 5}},
                                     {"inizio": "2026-10-12T10:00",
                                      "eventi_ombra": {}}])["base"]["n"] == 0)
    # `calliope stato` senza opzioni: l'avviso dal registro dei turni su disco
    tmp = tempfile.mkdtemp(prefix="eventi-guardia-")
    per_file: dict = {}
    for t in turni:
        per_file.setdefault(t["inizio"][:10], []).append(t)
    for data, tt in per_file.items():
        with open(os.path.join(tmp, f"turni-{data}.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(t) for t in tt) + "\n")
    cfg = types.SimpleNamespace(turn_log_dir=tmp)
    import datetime
    from calliope import latenza
    a = misura.avviso_riletti(cfg, oggi=datetime.date(2026, 10, 18))
    verifica("calliope stato: la riga dell'avviso di oggi",
             a is not None and "oggi la mediana" in a and "supera di più di metà" in a, str(a))
    a = misura.avviso_riletti(cfg, oggi=datetime.date(2026, 10, 19))
    verifica("contrario: il giorno dopo, buono (oggi con abbastanza turni), l'avviso di ieri "
             "non c'è più", a is None, str(a))
    a = misura.avviso_riletti(cfg, oggi=datetime.date(2026, 10, 25))
    verifica("contrario: una settimana dopo (o tornati a ombra) nessuna riga", a is None, str(a))
    letture = []
    leggi, leggi_file = latenza.leggi, latenza.leggi_file
    latenza.leggi = lambda c, g=None: letture.append("tutto") or leggi(c, g)
    latenza.leggi_file = lambda f: letture.append(os.path.basename(f)) or leggi_file(f)
    try:
        misura.avviso_riletti(cfg, oggi=datetime.date(2026, 10, 14))
        solo_ombra = list(letture)
        letture.clear()
        misura.avviso_riletti(cfg, oggi=datetime.date(2026, 10, 18))
    finally:
        latenza.leggi, latenza.leggi_file = leggi, leggi_file
    verifica("calliope stato: senza turni con attivo oggi o ieri si leggono solo i due file",
             solo_ombra == ["turni-2026-10-14.jsonl", "turni-2026-10-13.jsonl"]
             and letture[:2] == ["turni-2026-10-18.jsonl", "turni-2026-10-17.jsonl"]
             and "tutto" in letture, f"{solo_ombra} {letture[:3]}")
    verifica("contrario: cartella vuota o assente → nessuna riga",
             misura.avviso_riletti(types.SimpleNamespace(turn_log_dir=None)) is None
             and misura.avviso_riletti(types.SimpleNamespace(
                 turn_log_dir=tempfile.mkdtemp(prefix="eventi-vuoto-"))) is None)
    import calliope.stato as stato_mod
    src = open(stato_mod.__file__, encoding="utf-8").read()
    verifica("calliope stato: la guardia in --turni (testo e JSON) e nella pagina di sempre",
             "guardia_riletti(" in src and '"riletti_guardia"' in src
             and "avviso_riletti(cfg)" in src)


# ─────────────────────────── 2. il criterio di E1 ───────────────────────────
def prova_criterio():
    print("— 2. il criterio di E1: eventi_ombra.proiezione_diversa")
    verifica("i motivi dichiarati (capito, canale scritto) non fanno la proiezione diversa",
             misura.proiezione_diversa({"motivi": {"capito": 1, "canale_scritto": 1}})[0] == 0)
    verifica("…una frase sentita diversa sì (filtri_frase, stop_non_detto, non_in_storia)",
             all(misura.proiezione_diversa({"motivi": {m: 1}})[0] == 1
                 for m in ("filtri_frase", "stop_non_detto", "non_in_storia:saluto",
                           "storia_non_detta")))
    turni = [turno("2026-10-15", riletti=500, proiezione_diversa=0) for _ in range(4)]
    turni.append(turno("2026-10-15", riletti=500, proiezione_diversa=0,
                       proiezione_motivi={"canale_scritto": 1}))
    testo = misura.testo(misura.riassunto(turni))
    verifica("calliope stato --turni: «criterio di E1 … in 0 turni su 5», senza ATTENZIONE",
             "criterio di E1: proiezione degli eventi diversa da ciò che si è sentito in 0 "
             "turni su 5 (motivi: canale_scritto 1)" in testo
             and "eventi_ombra.proiezione_diversa" not in testo, testo)
    turni.append(turno("2026-10-15", riletti=500, proiezione_diversa=1,
                       proiezione_motivi={"filtri_frase": 1}))
    r = misura.riassunto(turni)
    testo = misura.testo(r)
    verifica("…con una proiezione diversa l'ATTENZIONE col nome del campo",
             r["2026-10-15"]["proiezione_diversa"] == 1
             and "ATTENZIONE: in 1 turni la proiezione degli eventi non dice" in testo
             and "eventi_ombra.proiezione_diversa: deve restare 0" in testo, testo)
    e1 = misura.criterio_e1(turni + [turno("2026-10-11")])
    t = misura.testo(misura.riassunto(turni), e1=e1)
    verifica("il criterio di E1 su tutto il registro: turni col campo e quanti diversi",
             e1 == {"turni": 6, "diversi": 1, "dal": "2026-10-15"}
             and "6 turni col campo eventi_ombra.proiezione_diversa (dal 2026-10-15), di cui 1"
             in t, t)
    verifica("turni di prima, senza il campo: non contati nel criterio",
             misura.riassunto([turno("2026-10-11")])["2026-10-11"]["proiezione"] == 0)


# ─────────────────── 3. sul ciclo vero: perché in ombra non va a zero ───────────────────
def _giro(modo):
    tmp = tempfile.mkdtemp(prefix=f"eventi-e1-{modo}-")
    copione = [
        [("text", "Sono le dieci.")],
        [("text", "Venezia è sulla laguna. Ha più di cento isole. È bellissima.")],
        [("text", "Ecco: **sole**.")],
        [("text", "Va bene.")], [("text", "Va bene.")],
    ]
    b, c, voce, stt, turni, annunci, registri = pe.prepara(tmp, copione, modo=modo)
    pe.giro(c, stt, "Calliope, che ore sono?")
    voce.interrompi_dopo = 1
    pe.giro(c, stt, "Calliope, raccontami di Venezia.")
    voce.interrompi_dopo = None
    pe.giro(c, stt, "Calliope, basta.")               # stop: «Va bene, mi fermo» mai detto
    annunci.agenda.put({"kind": "timer", "label": "della pasta", "due": time.time(),
                        "owner_name": None, "id": 1})
    c.sveglia.set()
    pe.giro(c, stt)                                  # timer scaduto: fuori dalla storia
    if modo == "ombra":
        b.allinea_detto = None                       # la frase filtrata non allineata
    pe.giro(c, stt, "Calliope, scrivi in grassetto la parola sole.")
    if modo == "ombra":
        del b.allinea_detto
    pe.giro(c, stt, "Calliope.")                     # il nome da solo: «Sì?»
    pe.giro(c, stt, "Calliope, e adesso?")
    c._scrivi_turno(c.rec)
    c.rec = None
    registri.disco.db.close()
    return turni


def prova_ciclo():
    print("— 3. sul ciclo vero: in ombra il parlato non va a zero, la proiezione sì")
    turni = _giro("ombra")
    eo = [r["eventi_ombra"] for r in turni if isinstance(r.get("eventi_ombra"), dict)]
    diversi = sum(1 for r in turni if (r.get("parlato") or {}).get("diverso"))
    diff = {k for o in eo for k in o.get("differenze") or {}}
    verifica("ombra: parlato.diverso non è zero per costruzione (la storia di Brain)",
             diversi >= 3, str(diversi))
    verifica("ombra: nemmeno eventi_ombra.differenze (conta proprio quei meccanismi)",
             {"stop_non_detto", "filtri_frase"} <= diff, str(diff))
    misurati = [o for o in eo if "proiezione_diversa" in o]
    verifica("ombra: proiezione_diversa in ogni turno con frasi sentite, sempre 0",
             len(misurati) >= 5 and not any(o["proiezione_diversa"] for o in misurati),
             str([(o.get("proiezione_diversa"), o.get("proiezione_motivi")) for o in eo]))
    testo = misura.testo(misura.riassunto(turni))
    verifica("ombra: calliope stato --turni dice il criterio a 0 accanto al parlato diverso",
             f"in 0 turni su {len(misurati)}" in testo
             and "la storia del modello non dice" in testo
             and "eventi_ombra.proiezione_diversa" not in testo, testo)
    turni = _giro("attivo")
    eo = [r["eventi_ombra"] for r in turni if isinstance(r.get("eventi_ombra"), dict)]
    misurati = [o for o in eo if "proiezione_diversa" in o]
    verifica("attivo: lo stesso campo, sempre 0, e il parlato a 0",
             len(misurati) >= 5 and not any(o["proiezione_diversa"] for o in misurati)
             and not any((r.get("parlato") or {}).get("diverso") for r in turni),
             str([o.get("proiezione_motivi") for o in eo]))


def main():
    prova_guardia()
    prova_criterio()
    prova_ciclo()
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
