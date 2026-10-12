"""
Prova a secco dell'indice del programma ministeriale (calliope/esercizi/programma/, 12/10/2026).
Niente rete né modelli.

- forma dell'indice (`programma.controlla`): fonti con la data di lettura, id unici, Indicazioni
  e traguardi noti, argomenti che esistono, classi valide, livelli 0–3, obiettivi della mappa che
  esistono e toccano l'argomento, ogni argomento agganciato (o con una nota);
- quali Indicazioni valgono per una classe in un anno scolastico (DM 221/2025, art. 1 e 5), con
  i casi al confine e i contrari: la terza e la quarta elementare del 2026/27 restano sul 2012,
  la prima no; storia in terza nel 2027/28; dal 2030/31 (primaria) e 2028/29 (media) solo le
  nuove; superiori fuori;
- anno scolastico e periodo da una data;
- `generatore_dentro` della mappa di matematica rifatto sul generatore vero (300 semi): dove
  l'indice dice «dentro» il generatore resta entro il limite (e senza cambio, se lo vieta);
  dove dice «fuori» almeno un esercizio esce. Il caso vero del 12/10: in terza a ottobre
  l'addizione è entro il 100, e 675 + 427 è fuori.
"""

import datetime
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from calliope.esercizi import matematica as MAT  # noqa: E402
from calliope.esercizi import programma as P  # noqa: E402
from calliope.esercizi.modello import Classe  # noqa: E402

errori = 0


def verifica(nome, cond, dettaglio=""):
    global errori
    if cond:
        print(f"ok  {nome}")
    else:
        errori += 1
        print(f"ERRORE  {nome}  {dettaglio}")


C = Classe.da_testo

print("── forma dell'indice ──")
err = P.controlla()
verifica("nessun errore di forma", not err, "; ".join(err[:10]))
dati = P.carica()
n_ob = sum(len(dati[m]["obiettivi"]) for m in P.FILE_MATERIE)
verifica("obiettivi delle due Indicazioni", n_ob >= 40 and {
    o["indicazioni"] for m in P.FILE_MATERIE for o in dati[m]["obiettivi"]} == {"2012", "2025"},
    str(n_ob))
verifica("fonti ufficiali con URL", all(
    ("gazzettaufficiale.it" in str(f) or "miur.gov.it" in str(f))
    for f in (dati["fonti"]["fonti"]["in2025"]["url_atto"],
              dati["fonti"]["fonti"]["in2012"]["url"])))

print("── quali Indicazioni valgono ──")
casi = [
    ("elementari-1", 2026, "", "2025"), ("elementari-2", 2026, "", "2012"),
    ("elementari-3", 2026, "", "2012"), ("elementari-4", 2026, "", "2012"),
    ("elementari-2", 2027, "", "2025"), ("elementari-3", 2027, "", "2012"),
    ("elementari-3", 2027, "storia", "2025"), ("elementari-3", 2028, "storia", "2025"),
    ("elementari-4", 2028, "storia", "2012"),
    ("elementari-5", 2029, "", "2012"), ("elementari-5", 2030, "", "2025"),
    ("elementari-1", 2025, "", "2012"),
    ("medie-1", 2026, "", "2025"), ("medie-2", 2026, "", "2012"),
    ("medie-3", 2027, "", "2012"), ("medie-3", 2028, "", "2025"),
]
for cl, anno, mat, atteso in casi:
    got = P.indicazioni_per(C(cl), anno, mat)
    verifica(f"{cl} nel {anno}/{(anno + 1) % 100:02d}{' (' + mat + ')' if mat else ''}: {atteso}",
             got == atteso, str(got))
verifica("superiori: fuori dal primo ciclo", P.indicazioni_per(C("superiori-1"), 2026) is None)
# Le vecchie cessano davvero quando dice l'art. 5 c. 3: dopo, ogni classe è sulle nuove
val = dati["fonti"]["validita"]
for scuola, grado, n in (("elementari", "primaria", 5), ("medie", "secondaria_primo_grado", 3)):
    anno = int(val[grado]["vecchie_cessano"])
    tutte = [P.indicazioni_per(Classe(scuola, k), anno) for k in range(1, n + 1)]
    prima = [P.indicazioni_per(Classe(scuola, k), anno - 1) for k in range(1, n + 1)]
    verifica(f"{grado}: dal {anno} solo le nuove, l'anno prima ancora una classe sulle vecchie",
             set(tutte) == {"2025"} and "2012" in prima, f"{tutte} {prima}")

print("── anno scolastico e periodo ──")
d = datetime.date
verifica("12/10/2026 → 2026, inizio", P.anno_scolastico(d(2026, 10, 12)) == 2026
         and P.periodo(d(2026, 10, 12)) == "inizio")
verifica("01/03/2027 → 2026, fine", P.anno_scolastico(d(2027, 3, 1)) == 2026
         and P.periodo(d(2027, 3, 1)) == "fine")
verifica("31/01 inizio, 01/02 fine", P.periodo(d(2027, 1, 31)) == "inizio"
         and P.periodo(d(2027, 2, 1)) == "fine")
verifica("luglio: estate, vale come fine", P.periodo(d(2027, 7, 15)) == "estate"
         and P.voce("matematica", "addizioni", C("elementari-3"), "estate")["entro"] == 999)
verifica("01/09/2026 → 2026, 31/08/2026 → 2025", P.anno_scolastico(d(2026, 9, 1)) == 2026
         and P.anno_scolastico(d(2026, 8, 31)) == 2025)

print("── il caso vero del 12/10 ──")
v = P.voce("matematica", "addizioni", C("elementari-3"), P.periodo(d(2026, 10, 12)))
verifica("terza a ottobre: addizioni entro 100, livello 2", v and v["entro"] == 100
         and v["livello"] == 2, str(v))
verifica("…con gli obiettivi 2012 (le Indicazioni di quella classe)", v and any(
    o.startswith("in2012") for o in v["obiettivi"]) and P.indicazioni_per(
    C("elementari-3"), 2026) == "2012")
verifica("675 + 427 e 277 + 121 fuori dal limite della terza a ottobre",
         675 + 427 > v["entro"] and 277 + 121 > v["entro"])
verifica("contrario: 45 + 38 dentro", 45 + 38 <= v["entro"])
verifica("frazioni in terza: nessun livello adatto oggi",
         P.voce("matematica", "frazioni", C("elementari-3"), "inizio")["livello"] == 0)
verifica("contrario: un argomento senza mappa per quella classe → None",
         P.voce("matematica", "equazioni", C("elementari-3"), "inizio") is None)
verifica("obiettivi ufficiali per argomento", len(P.obiettivi("matematica", "addizioni", "2012"))
         >= 3 and all(o["indicazioni"] == "2025"
                      for o in P.obiettivi("matematica", "addizioni", "2025")))

print("── generatore_dentro rifatto sul generatore ──")


def esce(argomento, livello, entro, cambio, semi=300):
    """Il primo esercizio del generatore che esce dal limite (o ha il cambio vietato), o None."""
    for s in range(semi):
        es = MAT.genera(argomento, livello, s)
        nums = [int(x) for x in re.findall(r"\d+", es.espressione)] + [int(es.risposta)]
        if max(nums) > entro:
            return es.testo
        if cambio is False and argomento in ("addizioni", "sottrazioni"):
            a, b = nums[0], nums[1]
            if (argomento == "addizioni" and a % 10 + b % 10 >= 10) or (
                    argomento == "sottrazioni" and a % 10 < b % 10):
                return es.testo
    return None


controllate = 0
for arg, classi in dati["matematica"]["mappa"].items():
    for cl, voci in classi.items():
        for q in ("inizio", "fine"):
            x = voci[q]
            if "entro" not in x or not x.get("livello"):
                continue
            controllate += 1
            fuori = esce(arg, x["livello"], x["entro"], x.get("cambio"))
            verifica(f"{arg} {cl} {q}: generatore_dentro={x['generatore_dentro']}",
                     (fuori is None) == x["generatore_dentro"], f"esce: {fuori}")
verifica("voci controllate sul generatore", controllate >= 30, str(controllate))

print()
print("ESITO: " + ("tutto ok" if not errori else f"{errori} errori"))
sys.exit(1 if errori else 0)
