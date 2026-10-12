"""
Esercizi di fisica con i numeri (12/10/2026, materie calcolabili, S1 della roadmap): velocità
(moto, conversioni, accelerazione), densità, forze (peso, F = m·a, lavoro e potenza).

Stesso schema della matematica: ogni generatore è deterministico dal seme e costruisce
l'esercizio **dalla soluzione** (prima la velocità, poi lo spazio); la risposta la calcola il
codice e l'espressione del conto, scritta nelle unità di base, la rifà il valutatore a frazioni
esatte (`misure.verifica`): se non torna l'esercizio non nasce. Il modello non vede mai la
risposta. Le unità a voce sono per esteso («metri al secondo»), sulla scheda i simboli
(«m/s»): `calliope/unita.py`.

Valori didattici: g = 9,8 N/kg (si dice nella domanda), densità dei materiali arrotondate come
sui libri delle medie.
"""

from __future__ import annotations

import random
from fractions import Fraction as F

from .. import unita as U
from .misure import controlla as controlla_misura
from .misure import nuovo, ore_dette, q
from .misure import verifica as verifica_misura
from .modello import Classe, Esercizio, Esito, livello_da_classe

MATERIA = "fisica"
VERIFICA = "calcolato"

ARGOMENTI = {
    "velocita": {"nome": "velocità e moto", "alias": ("velocit", "veloc", "moto", "accelerazion",
                                                       "chilometri all", "metri al secondo"),
                 "classi": (Classe("medie", 1), Classe("superiori", 5))},
    "densita": {"nome": "densità", "alias": ("densit", "massa volumica"),
                "classi": (Classe("medie", 1), Classe("superiori", 5))},
    "forze": {"nome": "forze, peso e lavoro", "alias": ("forz", "newton", "peso", "lavoro",
                                                         "joule", "watt"),
              "classi": (Classe("medie", 2), Classe("superiori", 5))},
}

# Chi si muove: (sulla scheda e a voce, velocità in m/s da … a …)
SOGGETTI = (("Un ragazzo che corre", 3, 7), ("Un ciclista", 4, 12),
            ("Un cane che insegue una palla", 5, 12), ("Una pattinatrice", 4, 10))
MEZZI = (("Un'auto", (50, 60, 80, 90, 100, 120)), ("Un treno", (80, 100, 120, 150, 200)),
         ("Un pullman", (40, 50, 60, 80, 90)), ("Una moto", (40, 60, 80, 90)))
# Materiale, densità in g/cm³ (arrotondata come sui libri)
MATERIALI = (("alluminio", F(27, 10)), ("ferro", F(79, 10)), ("rame", F(89, 10)),
             ("piombo", F(113, 10)), ("oro", F(193, 10)), ("argento", F(105, 10)),
             ("vetro", F(5, 2)), ("ghiaccio", F(92, 100)), ("sughero", F(1, 4)),
             ("marmo", F(27, 10)))
OGGETTI = (("una valigia", 8, 25), ("uno zaino", 3, 12), ("un cane", 5, 40),
           ("una bicicletta", 9, 18), ("un sacco di patate", 5, 30), ("un bambino", 20, 45))
G = F(49, 5)                      # 9,8 N/kg


def _del(materiale: str) -> str:
    """«del ferro», «dell'oro»."""
    return ("dell'" if materiale[0] in "aeiou" else "del ") + materiale


def _n(v) -> str:
    """Un numero per la scheda e per la voce: cifre con la virgola («2,5»)."""
    return U.numero_detto(v)


def _m(v, chiave) -> str:
    """Una misura detta («2,5 metri al secondo»)."""
    return U.misura_detta(v, chiave)


def _s(v, chiave) -> str:
    """Una misura scritta per la scheda («2,5 m/s»)."""
    return U.misura_scritta(v, chiave)


def _es(argomento, L, seme, testo, voce, valore, unita, sugg, spieg, espr, **k) -> Esercizio:
    return nuovo(MATERIA, argomento, L, seme, testo, voce, valore, unita, sugg, spieg, espr, **k)


# ─────────────────────────── velocità ───────────────────────────

def _velocita(rng: random.Random, L: int, seme: int) -> Esercizio:
    if L == 1:
        chi, lo, hi = rng.choice(SOGGETTI)
        v = rng.randint(lo, hi)
        t = rng.choice((5, 10, 15, 20, 25, 30, 40, 50, 60))
        s = v * t
        return _es("velocita", L, seme,
                   f"{chi} percorre {_s(s, 'm')} in {_s(t, 's')}. Qual è la sua velocità media, "
                   f"in m/s?",
                   f"{chi} percorre {_m(s, 'm')} in {_m(t, 's')}. Qual è la sua velocità media, "
                   f"in metri al secondo?", v, "m/s",
                   ["La velocità è lo spazio diviso il tempo.",
                    f"Dividi {s} metri per {t} secondi."],
                   f"Velocità uguale spazio diviso tempo: {s} diviso {t} fa {_m(v, 'm/s')}.",
                   f"{s}/{t}", formula="v = s / t")
    if L == 2:
        chi, velocita = rng.choice(MEZZI)
        v = rng.choice(velocita)
        t = rng.choice((F(1, 2), F(1), F(3, 2), F(2), F(5, 2), F(3), F(4)))
        s = v * t
        if rng.random() < 0.5:
            return _es("velocita", L, seme,
                       f"{chi} viaggia a {_s(v, 'km/h')} per {_s(t, 'h')}. Quanti km percorre?",
                       f"{chi} viaggia a {_m(v, 'km/h')} per {ore_dette(t)}. Quanti chilometri "
                       f"percorre?", s, "km",
                       ["Lo spazio è la velocità per il tempo.",
                        f"Fai {_n(v)} chilometri all'ora per {_n(t)} ore."],
                       f"Spazio uguale velocità per tempo: {_n(v)} per {_n(t)} fa {_m(s, 'km')}.",
                       f"{v}*1000/3600*{q(t)}*3600", formula="s = v · t")
        return _es("velocita", L, seme,
                   f"{chi} percorre {_s(s, 'km')} a {_s(v, 'km/h')}. Quante ore impiega?",
                   f"{chi} percorre {_m(s, 'km')} a {_m(v, 'km/h')}. Quante ore impiega?",
                   t, "h",
                   ["Il tempo è lo spazio diviso la velocità.",
                    f"Dividi {_n(s)} chilometri per {_n(v)} chilometri all'ora."],
                   f"Tempo uguale spazio diviso velocità: {_n(s)} diviso {_n(v)} fa "
                   f"{_m(t, 'h')}, cioè {ore_dette(t)}.",
                   f"{q(s)}*1000/({v}*1000/3600)", formula="t = s / v")
    tipo = rng.choice(("in_ms", "in_kmh", "accelerazione"))
    if tipo in ("in_ms", "in_kmh"):
        ms = rng.choice((5, 10, 15, 20, 25, 30, 35, 40))
        kmh = ms * F(18, 5)
        if tipo == "in_ms":
            return _es("velocita", L, seme, f"Converti {_s(kmh, 'km/h')} in m/s.",
                       f"Quanto fanno {_m(kmh, 'km/h')} in metri al secondo?", ms, "m/s",
                       ["Un chilometro sono 1000 metri e un'ora sono 3600 secondi.",
                        "Per passare da chilometri all'ora a metri al secondo si divide per "
                        "3,6."],
                       f"{_n(kmh)} diviso 3,6 fa {_m(ms, 'm/s')}.", f"{q(kmh)}*1000/3600",
                       obbligatoria=True, formula="v[m/s] = v[km/h] / 3,6")
        return _es("velocita", L, seme, f"Converti {_s(ms, 'm/s')} in km/h.",
                   f"Quanto fanno {_m(ms, 'm/s')} in chilometri all'ora?", kmh, "km/h",
                   ["Un chilometro sono 1000 metri e un'ora sono 3600 secondi.",
                    "Per passare da metri al secondo a chilometri all'ora si moltiplica per "
                    "3,6."],
                   f"{ms} per 3,6 fa {_m(kmh, 'km/h')}.", f"{ms}",
                   obbligatoria=True, formula="v[km/h] = v[m/s] · 3,6")
    a = rng.choice((F(1), F(2), F(3), F(4), F(5), F(1, 2), F(3, 2), F(5, 2)))
    t = rng.choice((2, 4, 5, 6, 8, 10))
    v1 = rng.randint(0, 10)
    v2 = v1 + a * t
    chi = rng.choice(("Un'auto", "Una moto", "Un ciclista"))
    partenza = "partendo da ferma" if v1 == 0 else f"da {_m(v1, 'm/s')}"
    return _es("velocita", L, seme,
               f"{chi} passa da {_s(v1, 'm/s')} a {_s(v2, 'm/s')} in {_s(t, 's')}. Qual è la sua "
               f"accelerazione media, in m/s²?",
               f"{chi}, {partenza}, arriva a {_m(v2, 'm/s')} in {_m(t, 's')}. Qual è la sua "
               f"accelerazione media, in metri al secondo quadrato?", a, "m/s²",
               ["L'accelerazione è quanto cambia la velocità diviso il tempo.",
                f"La velocità cambia di {_n(v2 - v1)} metri al secondo: dividi per {t}."],
               f"La velocità cambia di {_n(v2 - v1)} metri al secondo in {t} secondi: "
               f"{_n(v2 - v1)} diviso {t} fa {_m(a, 'm/s²')}.",
               f"({q(v2)}-{v1})/{t}", formula="a = Δv / t")


# ─────────────────────────── densità ───────────────────────────

def _densita(rng: random.Random, L: int, seme: int) -> Esercizio:
    mat, d = rng.choice(MATERIALI)
    sugg_d = "La densità è la massa divisa il volume."
    if L == 1:
        V = rng.choice((2, 4, 5, 10, 20, 25, 50, 100))
        m = d * V
        return _es("densita", L, seme,
                   f"Un pezzo di {mat} ha una massa di {_s(m, 'g')} e un volume di "
                   f"{_s(V, 'cm³')}. Qual è la sua densità, in g/cm³?",
                   f"Un pezzo di {mat} ha una massa di {_m(m, 'g')} e un volume di "
                   f"{_m(V, 'cm³')}. Qual è la sua densità, in grammi al centimetro cubo?",
                   d, "g/cm³",
                   [sugg_d, f"Dividi {_n(m)} grammi per {V} centimetri cubi."],
                   f"Densità uguale massa diviso volume: {_n(m)} diviso {V} fa "
                   f"{_m(d, 'g/cm³')}.",
                   f"({q(m)}/1000)/({V}/1000000)", formula="d = m / V")
    if L == 2:
        V = rng.choice((2, 3, 4, 5, 10, 20, 30, 40, 50))
        m = d * V
        if rng.random() < 0.5:
            return _es("densita", L, seme,
                       f"La densità {_del(mat)} è {_s(d, 'g/cm³')}. Quanti grammi pesa un pezzo di "
                       f"{mat} di {_s(V, 'cm³')}?",
                       f"La densità {_del(mat)} è {_m(d, 'g/cm³')}. Che massa ha, in grammi, un "
                       f"pezzo di {mat} di {_m(V, 'cm³')}?", m, "g",
                       ["La massa è la densità per il volume.",
                        f"Fai {_n(d)} per {V}."],
                       f"Massa uguale densità per volume: {_n(d)} per {V} fa {_m(m, 'g')}.",
                       f"{q(d)}*1000*{V}/1000000", formula="m = d · V")
        return _es("densita", L, seme,
                   f"La densità {_del(mat)} è {_s(d, 'g/cm³')}. Che volume ha un pezzo di {mat} "
                   f"di {_s(m, 'g')}, in cm³?",
                   f"La densità {_del(mat)} è {_m(d, 'g/cm³')}. Che volume ha un pezzo di {mat} "
                   f"di {_m(m, 'g')}, in centimetri cubi?", V, "cm³",
                   ["Il volume è la massa divisa la densità.",
                    f"Dividi {_n(m)} per {_n(d)}."],
                   f"Volume uguale massa diviso densità: {_n(m)} diviso {_n(d)} fa "
                   f"{_m(V, 'cm³')}.",
                   f"({q(m)}/1000)/({q(d)}*1000)", formula="V = m / d")
    dk = d * 1000
    if rng.random() < 0.5:
        V = rng.choice((F(1, 10), F(1, 4), F(1, 2), F(2), F(3)))
        m = dk * V
        return _es("densita", L, seme,
                   f"Un blocco di {mat} ha una massa di {_s(m, 'kg')} e un volume di "
                   f"{_s(V, 'm³')}. Qual è la sua densità, in kg/m³?",
                   f"Un blocco di {mat} ha una massa di {_m(m, 'kg')} e un volume di "
                   f"{_m(V, 'm³')}. Qual è la sua densità, in chilogrammi al metro cubo?",
                   dk, "kg/m³",
                   [sugg_d, f"Dividi {_n(m)} chilogrammi per {_n(V)} metri cubi."],
                   f"{_n(m)} diviso {_n(V)} fa {_m(dk, 'kg/m³')}.",
                   f"{q(m)}/{q(V)}", formula="d = m / V")
    return _es("densita", L, seme,
               f"La densità {_del(mat)} è {_s(d, 'g/cm³')}. Quanto vale in kg/m³?",
               f"La densità {_del(mat)} è {_m(d, 'g/cm³')}. Quanto vale in chilogrammi al metro "
               f"cubo?", dk, "kg/m³",
               ["Un chilogrammo sono 1000 grammi e un metro cubo un milione di centimetri cubi.",
                "Da grammi al centimetro cubo a chilogrammi al metro cubo si moltiplica per "
                "1000."],
               f"{_n(d)} per 1000 fa {_m(dk, 'kg/m³')}.", f"{q(d)}*1000",
               obbligatoria=True, formula="d[kg/m³] = d[g/cm³] · 1000")


# ─────────────────────────── forze ───────────────────────────

def _forze(rng: random.Random, L: int, seme: int) -> Esercizio:
    if L == 1:
        cosa, lo, hi = rng.choice(OGGETTI)
        m = rng.randint(lo, hi)
        P = m * G
        return _es("forze", L, seme,
                   f"Qual è il peso, in newton, di {cosa} di {_s(m, 'kg')}? Usa g = 9,8 N/kg.",
                   f"Qual è il peso, in newton, di {cosa} di {_m(m, 'kg')}? Usa "
                   f"un'accelerazione di gravità di 9,8 newton al chilogrammo.", P, "N",
                   ["Il peso è la massa per l'accelerazione di gravità.",
                    f"Fai {m} per 9,8."],
                   f"Peso uguale massa per g: {m} per 9,8 fa {_m(P, 'N')}.",
                   f"{m}*{q(G)}", formula="P = m · g")
    if L == 2:
        m = rng.choice((2, 4, 5, 8, 10, 12, 15, 20, 25, 40, 50))
        a = rng.choice((F(1), F(2), F(3), F(4), F(5), F(6), F(1, 2), F(3, 2)))
        Fz = m * a
        chi = rng.choice(("un carrello", "una slitta", "una cassa", "un pattino"))
        if rng.random() < 0.5:
            return _es("forze", L, seme,
                       f"Che forza serve per dare a {chi} di {_s(m, 'kg')} un'accelerazione di "
                       f"{_s(a, 'm/s²')}? Rispondi in newton.",
                       f"Che forza serve per dare a {chi} di {_m(m, 'kg')} un'accelerazione di "
                       f"{_m(a, 'm/s²')}? Rispondi in newton.", Fz, "N",
                       ["Per il secondo principio della dinamica, la forza è la massa per "
                        "l'accelerazione.", f"Fai {m} per {_n(a)}."],
                       f"Forza uguale massa per accelerazione: {m} per {_n(a)} fa {_m(Fz, 'N')}.",
                       f"{m}*{q(a)}", formula="F = m · a")
        return _es("forze", L, seme,
                   f"Una forza di {_s(Fz, 'N')} spinge {chi} di {_s(m, 'kg')}. Qual è la sua "
                   f"accelerazione, in m/s²?",
                   f"Una forza di {_m(Fz, 'N')} spinge {chi} di {_m(m, 'kg')}. Qual è la sua "
                   f"accelerazione, in metri al secondo quadrato?", a, "m/s²",
                   ["Dal secondo principio: l'accelerazione è la forza divisa la massa.",
                    f"Dividi {_n(Fz)} per {m}."],
                   f"Accelerazione uguale forza diviso massa: {_n(Fz)} diviso {m} fa "
                   f"{_m(a, 'm/s²')}.",
                   f"{q(Fz)}/{m}", formula="a = F / m")
    if rng.random() < 0.5:
        Fz = rng.choice((10, 20, 25, 40, 50, 100, 150, 200, 500))
        s = rng.choice((F(1, 2), F(2), F(3), F(4), F(5), F(10)))
        Lv = Fz * s
        chi = rng.choice(("Una gru", "Un ragazzo", "Un argano", "Una carrucola"))
        return _es("forze", L, seme,
                   f"{chi} esercita una forza di {_s(Fz, 'N')} e sposta un oggetto di "
                   f"{_s(s, 'm')} nella stessa direzione. Quanto lavoro compie, in joule?",
                   f"{chi} esercita una forza di {_m(Fz, 'N')} e sposta un oggetto di "
                   f"{_m(s, 'm')} nella stessa direzione. Quanto lavoro compie, in joule?",
                   Lv, "J",
                   ["Il lavoro è la forza per lo spostamento.",
                    f"Fai {Fz} per {_n(s)}."],
                   f"Lavoro uguale forza per spostamento: {Fz} per {_n(s)} fa {_m(Lv, 'J')}.",
                   f"{Fz}*{q(s)}", formula="L = F · s")
    P = rng.choice((10, 20, 25, 40, 50, 60, 75, 100, 200, 500))
    t = rng.choice((2, 4, 5, 10, 20, 30))
    Lv = P * t
    chi = rng.choice(("Un motore", "Una lampadina", "Un frullatore", "Una pompa"))
    return _es("forze", L, seme,
               f"{chi} compie un lavoro di {_s(Lv, 'J')} in {_s(t, 's')}. Qual è la sua "
               f"potenza, in watt?",
               f"{chi} compie un lavoro di {_m(Lv, 'J')} in {_m(t, 's')}. Qual è la sua "
               f"potenza, in watt?", P, "W",
               ["La potenza è il lavoro diviso il tempo.", f"Dividi {Lv} per {t}."],
               f"Potenza uguale lavoro diviso tempo: {Lv} diviso {t} fa {_m(P, 'W')}.",
               f"{Lv}/{t}", formula="P = L / t")


GENERATORI = {"velocita": _velocita, "densita": _densita, "forze": _forze}


def genera(argomento: str, livello: int, seme: int) -> Esercizio:
    """L'esercizio di quel seme; ValueError se il ricalcolo non torna (mai, se i generatori
    sono giusti: lo controlla prova_materie su migliaia di semi)."""
    rng = random.Random(f"{MATERIA}:{argomento}:{livello}:{seme}")
    es = GENERATORI[argomento](rng, max(1, min(3, int(livello))), seme)
    if not verifica(es):
        raise ValueError(f"esercizio {argomento}/{livello}/{seme}: il ricalcolo non torna")
    es.verifica = {"tipo": "calcolato", "ricalcolo": True}
    return es


def verifica(es: Esercizio) -> bool:
    return verifica_misura(es)


def controlla(es: Esercizio, risposta) -> Esito:
    return controlla_misura(es, risposta)


def livello_per(argomento: str, classe: Classe) -> int:
    return livello_da_classe(ARGOMENTI[argomento]["classi"], classe)
