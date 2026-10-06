"""Misura del contesto degli agenti (05/10/2026, fase 2b, docs/ricerche/2026-10-05-contesto-agenti.md).

Un lavoro di codice lungo con il modello vero (qwen3.6 su vLLM sulla DGX, via il tunnel di
dgx.yaml): un parser per tre pagine HTML «scaricate dal sito del comune», ognuna con gli eventi
in un formato diverso e lunga ~25 000 caratteri (leggi_file ne dà 12 000: gli eventi sono anche
in fondo), con i test dell'agente e un test nascosto alla fine (una quarta pagina, doppioni,
ordine, prezzi). I risultati degli strumenti sono lunghi: è il caso che il contesto deve reggere.

    python prove\\misura_contesto_agenti.py                       # finestra «auto»
    python prove\\misura_contesto_agenti.py --finestra 16384      # finestra piccola: file e diario
    python prove\\misura_contesto_agenti.py --minuti 8 --uscita <cartella> --etichetta dopo

Stampa una riga JSON con esito, test nascosto, passate, token (generati, di ragionamento,
letti), picco del contesto, file scaricati e diari, minuti. Funziona anche con il codice di
prima della fase 2b (i campi nuovi mancano): così si misura «prima» con lo stesso compito.
Manuale: non è nel runner delle prove (vuole la DGX).
"""

import argparse
import json
import os
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

COMPITO = (
    "Nella cartella pagine/ ci sono tre pagine HTML scaricate dal sito del comune "
    "(pagina1.html, pagina2.html, pagina3.html): ognuna elenca degli eventi, ma in un formato "
    "diverso. Scrivi eventi.py con due funzioni: estrai_eventi(html) che restituisce la lista "
    "degli eventi della pagina, ognuno un dizionario con titolo, data (stringa AAAA-MM-GG), "
    "luogo e prezzo (float in euro, 0.0 se l'evento è gratuito, libero o gratis); e "
    "unisci(cartella) che legge tutte le pagine .html della cartella e restituisce tutti gli "
    "eventi senza doppioni (stesso titolo e stessa data), ordinati per data e poi per titolo. "
    "Solo la libreria standard (html.parser, re). Guarda le pagine per intero: gli eventi sono "
    "anche in fondo, dopo molto altro testo. Scrivi test_eventi.py con almeno 10 test sui tre "
    "formati e falli passare.")

MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]

# (titolo, (anno, mese, giorno), luogo, prezzo)
EVENTI = {
    1: [("Concerto della banda", (2026, 3, 12), "Piazza Garibaldi", 0.0),
        ("Mostra di acquerelli", (2026, 3, 14), "Sala civica", 5.0),
        ("Teatro per ragazzi", (2026, 3, 20), "Teatro comunale", 7.5),
        ("Mercatino dell'usato", (2026, 3, 22), "Via Roma", 0.0),
        ("Cineforum: Ladri di biciclette", (2026, 3, 26), "Cinema Ariston", 4.0),
        ("Corso di fotografia", (2026, 4, 2), "Biblioteca", 12.5),
        ("Festa di primavera", (2026, 4, 5), "Parco del Castello", 0.0),
        ("Conferenza sul clima", (2026, 4, 9), "Auditorium", 3.0)],
    2: [("Mostra di acquerelli", (2026, 3, 14), "Sala civica", 5.0),
        ("Torneo di scacchi", (2026, 3, 15), "Circolo Arci", 2.0),
        ("Visita guidata al borgo", (2026, 3, 21), "Porta Nuova", 6.0),
        ("Presentazione del libro", (2026, 3, 28), "Libreria Mondo", 0.0),
        ("Corso di fotografia", (2026, 4, 2), "Biblioteca", 12.5),
        ("Laboratorio di ceramica", (2026, 4, 11), "Centro giovani", 15.0),
        ("Coro gospel", (2026, 4, 18), "Chiesa di San Rocco", 8.0)],
    3: [("Festa di primavera", (2026, 4, 5), "Parco del Castello", 0.0),
        ("Maratonina cittadina", (2026, 3, 29), "Stadio comunale", 10.0),
        ("Serata di tango", (2026, 4, 12), "Palazzetto", 9.5),
        ("Lettura di fiabe", (2026, 3, 17), "Biblioteca", 0.0),
        ("Degustazione di vini", (2026, 4, 25), "Cantina sociale", 20.0),
        ("Concerto jazz", (2026, 5, 2), "Piazza Garibaldi", 11.0)],
}
PAGINA4 = [("Fiera del libro", (2026, 5, 9), "Chiostro", 0.0),
           ("Spettacolo di magia", (2026, 5, 10), "Teatro comunale", 6.5),
           ("Gara di torte", (2026, 5, 16), "Oratorio", 0.0)]


def _riempitivo(rng: random.Random, n: int) -> str:
    parole = ("il comune informa che gli uffici resteranno chiusi per lavori di manutenzione "
              "la raccolta differenziata cambia orario nel quartiere nord si ricorda ai "
              "cittadini che le domande per il bonus vanno presentate entro la fine del mese "
              "presso lo sportello unico con un documento di identità valido e il codice "
              "fiscale il consiglio comunale si riunirà in seduta pubblica").split()
    out = []
    for _ in range(n):
        frase = " ".join(rng.choice(parole) for _ in range(rng.randint(18, 40)))
        out.append(f"<p class=\"notizia\">{frase.capitalize()}.</p>")
    return "\n".join(out)


def _testa(titolo: str, rng: random.Random) -> str:
    menu = "\n".join(f"<li><a href=\"/sezione/{i}\">Sezione {i}</a></li>" for i in range(40))
    script = ("<script>\nwindow.dataLayer = window.dataLayer || [];\n"
              + "\n".join(f"function f{i}(a,b){{return a*{i}+b;}}" for i in range(60))
              + "\n</script>")
    return (f"<!doctype html><html lang=\"it\"><head><meta charset=\"utf-8\"><title>{titolo}"
            f"</title>{script}</head><body><nav><ul>{menu}</ul></nav>"
            f"<div class=\"news\">{_riempitivo(rng, 40)}</div>")


def _prezzo1(p):
    return "Gratuito" if not p else f"€ {p:.2f}".replace(".", ",")


def pagina(n: int, eventi: list, rng: random.Random) -> str:
    """Le pagine nei tre formati, con gli eventi divisi tra l'inizio e il fondo."""
    blocchi = []
    for t, (a, m, g), luogo, p in eventi:
        if n == 1:
            blocchi.append(f"<div class=\"evento\"><h3 class=\"titolo\">{t}</h3>"
                           f"<span class=\"data\">{g:02d}/{m:02d}/{a}</span> "
                           f"<span class=\"luogo\">{luogo}</span> "
                           f"<span class=\"prezzo\">{_prezzo1(p)}</span></div>")
        elif n == 2:
            costo = "Ingresso libero" if not p else (
                f"Ingresso {p:g} euro".replace(".", ","))
            blocchi.append(f"<article class=\"ev\" data-data=\"{a}-{m:02d}-{g:02d}\" "
                           f"data-luogo=\"{luogo}\"><h2>{t}</h2><p class=\"costo\">{costo}</p>"
                           f"</article>")
        else:
            costo = "gratis" if not p else f"{p:.2f} €".replace(".", ",")
            blocchi.append(f"<li class=\"evento-lista\"><strong>{t}</strong> — {g} {MESI[m - 1]} "
                           f"{a}, {luogo}. Biglietto: {costo}</li>")
    meta = len(blocchi) // 2
    contenitore = {1: ("<section id=\"eventi\">", "</section>"),
                   2: ("<main class=\"agenda\">", "</main>"),
                   3: ("<ul class=\"calendario\">", "</ul>")}[n]
    return (_testa(f"Eventi — pagina {n}", rng) + contenitore[0] + "\n".join(blocchi[:meta])
            + contenitore[1] + f"<div class=\"altro\">{_riempitivo(rng, 70)}</div>"
            + contenitore[0] + "\n".join(blocchi[meta:]) + contenitore[1]
            + "<footer>Comune di Esempio — tutti i diritti riservati</footer></body></html>")


def pagina4(rng: random.Random) -> str:
    """Una pagina nuova con i tre formati insieme: per il test nascosto."""
    e1, e2, e3 = PAGINA4
    return (pagina(1, [e1], rng).replace("</body></html>", "")
            + pagina(2, [e2], rng).split("<body>", 1)[1].replace("</body></html>", "")
            + pagina(3, [e3], rng).split("<body>", 1)[1])


def file_iniziali() -> dict:
    rng = random.Random(5102026)
    return {f"pagine/pagina{n}.html": pagina(n, EVENTI[n], rng) for n in (1, 2, 3)}


def atteso() -> list:
    visti, out = set(), []
    for n in (1, 2, 3):
        for t, (a, m, g), luogo, p in EVENTI[n]:
            d = f"{a}-{m:02d}-{g:02d}"
            if (t, d) not in visti:
                visti.add((t, d))
                out.append((d, t, luogo, p))
    return sorted(out)


TEST_NASCOSTO = '''
import json, unittest
from eventi import estrai_eventi, unisci

ATTESO = json.loads(%r)
P4 = json.loads(%r)


class Nascosto(unittest.TestCase):
    def test_unisci_conta(self):
        self.assertEqual(len(unisci("pagine")), len(ATTESO))

    def test_unisci_ordine_e_campi(self):
        ev = unisci("pagine")
        got = [(e["data"], e["titolo"].strip(), e["luogo"].strip(), float(e["prezzo"])) for e in ev]
        self.assertEqual(got, [tuple(x) for x in ATTESO])

    def test_pagina4_tre_formati(self):
        html = open("nascosto/pagina4.html", encoding="utf-8").read()
        ev = sorted((e["data"], e["titolo"].strip(), float(e["prezzo"])) for e in estrai_eventi(html))
        self.assertEqual(ev, sorted(tuple(x) for x in P4))
'''


def test_nascosto(cartella: Path, uscita: Path) -> tuple[str, bool]:
    from calliope.agenti.sandbox import Isolamento, Sandbox
    dest = uscita / "verifica"
    shutil.rmtree(dest, ignore_errors=True)
    sb = Sandbox(dest, tempo_s=60, isolamento=Isolamento("processo", "misura"))
    for p in Path(cartella).rglob("*"):
        if p.is_file() and p.name != "lavoro.json" and ".calliope" not in p.parts:
            try:
                sb.scrivi(p.relative_to(cartella).as_posix(),
                          p.read_text(encoding="utf-8", errors="replace"))
            except Exception:  # noqa: BLE001
                pass
    rng = random.Random(99)
    sb.scrivi("nascosto/pagina4.html", pagina4(rng))
    p4 = [[f"{a}-{m:02d}-{g:02d}", t, p] for t, (a, m, g), _, p in PAGINA4]
    sb.scrivi("test_nascosto_misura.py", TEST_NASCOSTO % (json.dumps(atteso()), json.dumps(p4)))
    r = sb.test("test_nascosto_misura.py")
    return r["esito"], bool(r["passano"])


# ─────────────── compito «validatori»: codice con molti test (06/10) ───────────────
COMPITO_VALIDATORI = (
    "Scrivi validatori.py con queste funzioni, solo la libreria standard: "
    "codice_fiscale_valido(cf) → bool (16 caratteri: 6 lettere, 2 cifre, la lettera del mese, "
    "2 cifre, una lettera e 3 cifre, e il carattere di controllo giusto; maiuscole o "
    "minuscole); partita_iva_valida(piva) → bool (11 cifre con la cifra di controllo); "
    "iban_valido(iban) → bool (spazi ammessi, controllo mod 97; per gli IBAN che cominciano "
    "con IT anche la lunghezza 27); intero_a_romano(n) e romano_a_intero(s) (da 1 a 3999, "
    "ValueError fuori intervallo e per i numeri romani non validi come IIII, VX o IC); "
    "data_italiana(testo) che restituisce la stringa AAAA-MM-GG da «3 marzo 2026», "
    "«03/03/2026» o «3-3-26» (anni di due cifre: 20xx), oppure None se non è una data vera "
    "(anche 31/02/2026). Scrivi test_validatori.py con almeno 30 test. Lavora una funzione "
    "alla volta: scrivi la funzione e i suoi test, esegui i test, poi passa alla successiva. "
    "Alla fine tutti i test devono passare.")

_DISPARI = dict(zip("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                    [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4,
                     18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23]))


def _cf_controllo(c15: str) -> str:
    tot = 0
    for i, ch in enumerate(c15):
        if i % 2 == 0:
            tot += _DISPARI[ch]
        else:
            tot += int(ch) if ch.isdigit() else ord(ch) - 65
    return chr(65 + tot % 26)


def _piva_controllo(d10: str) -> str:
    x = sum(int(d10[i]) for i in range(0, 10, 2))
    y = 0
    for i in range(1, 10, 2):
        v = 2 * int(d10[i])
        y += v - 9 if v > 9 else v
    return str((10 - (x + y) % 10) % 10)


def _iban_mod(s: str) -> int:
    r = s[4:] + s[:4]
    return int("".join(str(int(ch, 36)) for ch in r)) % 97


def _romano(n: int) -> str:
    out = ""
    for v, s in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
                 (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out, n = out + s, n - v
    return out


def casi_validatori() -> dict:
    rng = random.Random(6102026)
    L = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    cf_ok, cf_ko = [], []
    for _ in range(8):
        c15 = ("".join(rng.choice(L) for _ in range(6)) + f"{rng.randint(0, 99):02d}"
               + rng.choice("ABCDEHLMPRST") + f"{rng.choice([rng.randint(1, 31), rng.randint(41, 71)]):02d}"
               + rng.choice(L) + f"{rng.randint(0, 999):03d}")
        cf = c15 + _cf_controllo(c15)
        cf_ok.append(cf)
        sbagliata = chr(65 + (ord(cf[-1]) - 65 + rng.randint(1, 25)) % 26)
        cf_ko.append(c15 + sbagliata)
    cf_ok.append(cf_ok[0].lower())
    cf_ko += [cf_ok[1][:15], cf_ok[2] + "X"]
    piva_ok, piva_ko = [], []
    for _ in range(8):
        d10 = "".join(str(rng.randint(0, 9)) for _ in range(10))
        p = d10 + _piva_controllo(d10)
        piva_ok.append(p)
        piva_ko.append(d10 + str((int(p[-1]) + rng.randint(1, 9)) % 10))
    piva_ko += [piva_ok[0][:10], piva_ok[1] + "0", "ABCDEFGHIJK"]
    iban_ok, iban_ko = [], []
    for _ in range(6):
        corpo = (rng.choice(L) + "".join(str(rng.randint(0, 9)) for _ in range(10))
                 + "".join(rng.choice("0123456789") for _ in range(12)))
        k = 98 - _iban_mod("IT00" + corpo)
        iban = f"IT{k:02d}{corpo}"
        assert _iban_mod(iban) == 1
        iban_ok.append(iban)
        iban_ko.append(iban[:4] + corpo[:-1] + str((int(corpo[-1]) + 1) % 10))
    iban_ok.append(" ".join(iban_ok[0][i:i + 4] for i in range(0, 27, 4)))
    iban_ok.append("GB82WEST12345698765432")          # l'esempio ufficiale inglese
    iban_ko += [iban_ok[1][:26], "GB82WEST12345698765431"]
    romani = sorted(rng.sample(range(1, 4000), 25) + [4, 9, 14, 40, 90, 400, 900, 1994, 3999])
    date = [("3 marzo 2026", "2026-03-03"), ("03/03/2026", "2026-03-03"),
            ("3-3-26", "2026-03-03"), ("29 febbraio 2024", "2024-02-29"),
            ("12 dicembre 1999", "1999-12-12"), ("1/1/2030", "2030-01-01"),
            ("31/02/2026", None), ("29/02/2025", None), ("ciao", None),
            ("31 aprile 2026", None), ("15 agosto 2026", "2026-08-15")]
    return {"cf_ok": cf_ok, "cf_ko": cf_ko, "piva_ok": piva_ok, "piva_ko": piva_ko,
            "iban_ok": iban_ok, "iban_ko": iban_ko,
            "romani": [[n, _romano(n)] for n in romani],
            "romani_ko": ["IIII", "VX", "IC", "MMMM", "", "XM"], "interi_ko": [0, 4000, -3],
            "date": date}


TEST_VALIDATORI = '''
import json, unittest
import validatori as v

C = json.loads(%r)


class Nascosto(unittest.TestCase):
    def test_cf(self):
        self.assertEqual([v.codice_fiscale_valido(x) for x in C["cf_ok"]], [True] * len(C["cf_ok"]))
        self.assertEqual([v.codice_fiscale_valido(x) for x in C["cf_ko"]], [False] * len(C["cf_ko"]))

    def test_piva(self):
        self.assertEqual([v.partita_iva_valida(x) for x in C["piva_ok"]], [True] * len(C["piva_ok"]))
        self.assertEqual([v.partita_iva_valida(x) for x in C["piva_ko"]], [False] * len(C["piva_ko"]))

    def test_iban(self):
        self.assertEqual([v.iban_valido(x) for x in C["iban_ok"]], [True] * len(C["iban_ok"]))
        self.assertEqual([v.iban_valido(x) for x in C["iban_ko"]], [False] * len(C["iban_ko"]))

    def test_romani(self):
        for n, s in C["romani"]:
            self.assertEqual(v.intero_a_romano(n), s)
            self.assertEqual(v.romano_a_intero(s), n)
        for s in C["romani_ko"]:
            with self.assertRaises(ValueError):
                v.romano_a_intero(s)
        for n in C["interi_ko"]:
            with self.assertRaises(ValueError):
                v.intero_a_romano(n)

    def test_date(self):
        for t, atteso in C["date"]:
            self.assertEqual(v.data_italiana(t), atteso, t)
'''


# ─────────────── compito «relazione»: ricerca da più fonti (06/10) ───────────────
COMPITO_RELAZIONE = (
    "Prepara una relazione completa sul Consorzio idrico della Val Morena: la storia "
    "(fondazione, chi lo fondò, gli eventi importanti), la rete e gli impianti (sorgenti, "
    "acquedotto, bacini, depurazione, laboratorio), i numeri dell'acqua (comuni e abitanti "
    "serviti, consumi, perdite, controlli), le tariffe e gli aiuti alle famiglie, chi lo guida "
    "oggi, quante persone ci lavorano e i progetti futuri. Riporta tutti i dati precisi che "
    "trovi (anni, quantità, importi, nomi), ognuno con la sua fonte. Cerca un argomento alla "
    "volta.")

_RIEMPI = ("Il documento è conservato nell'archivio storico del consorzio e riporta anche "
           "osservazioni generali sul territorio, sui rapporti con le amministrazioni locali e "
           "sulla manutenzione ordinaria, che qui non interessano. ")

# (titolo, testo con i fatti, fonte). I fatti sono inventati: il modello non li sa a memoria
FONTI_RELAZIONE = [
    ("Consorzio idrico della Val Morena — storia",
     "Il Consorzio idrico della Val Morena fu fondato nel 1923 a Borgo Lieto per iniziativa "
     "dell'ingegner Ettore Valsecchi, che progettò la prima condotta. Nel 1966 un'alluvione "
     "distrusse la presa di Ponte Scuro, ricostruita in due anni. Nel 1978 il consorzio passò "
     "sotto la gestione pubblica dei comuni della valle.", "Annali della Val Morena, 2019"),
    ("Sorgenti e acquedotto della Val Morena",
     "La sorgente principale del consorzio è la sorgente del Pizzo Grigio, con una portata "
     "media di 412 litri al secondo. L'acquedotto consortile è lungo 386 chilometri e serve "
     "14 comuni. Una sorgente minore, la Fonte Bassa, è usata solo d'estate.",
     "Piano d'ambito 2024"),
    ("Bacino di Lago Nero",
     "Il bacino artificiale di Lago Nero, costruito nel 1958, trattiene 2,1 milioni di metri "
     "cubi d'acqua e garantisce le riserve nei mesi secchi. La diga è alta 31 metri.",
     "Scheda tecnica del bacino, 2023"),
    ("Depuratore di Canneto",
     "Il depuratore di Canneto, inaugurato nel 2011, tratta gli scarichi di tutta la valle e "
     "ha una capacità di 60.000 abitanti equivalenti. Prima del 2011 gli scarichi di tre "
     "comuni finivano nel torrente.", "Relazione ambientale 2022"),
    ("Laboratorio e qualità dell'acqua in Val Morena",
     "Il laboratorio del consorzio a Villa Serena analizza circa 1.900 campioni d'acqua "
     "l'anno. Nel 2025 tutti i parametri sono rimasti nei limiti di legge.",
     "Rapporto sulla qualità dell'acqua 2025"),
    ("Utenti, consumi e perdite della rete",
     "Il consorzio serve 52.300 abitanti. Il consumo medio è di 168 litri per abitante al "
     "giorno. Nel 2025 le perdite della rete sono state del 31,4 per cento; l'obiettivo è "
     "scendere al 22 per cento entro il 2030.", "Bilancio di sostenibilità 2025"),
    ("Tariffe del servizio idrico della Val Morena",
     "La tariffa base è di 1,37 euro al metro cubo, con una quota fissa di 48 euro l'anno per "
     "utenza. Il bonus idrico del consorzio aiuta 1.150 famiglie con un reddito basso.",
     "Delibera tariffaria 2026"),
    ("Organizzazione del consorzio",
     "Dal 2022 il consorzio è presieduto da Marta Ferraris. Ci lavorano 74 dipendenti, divisi "
     "tra la sede di Borgo Lieto e gli impianti.", "Statuto e organigramma 2026"),
    ("Progetti futuri: Rete Viva",
     "Il progetto «Rete Viva», finanziato con 18,6 milioni di euro di fondi PNRR, sostituirà "
     "le condotte più vecchie e installerà 9.400 contatori intelligenti entro il 2027.",
     "Piano degli investimenti 2026–2030"),
    # distrattori: un'altra valle
    ("Acquedotto della Val Serena",
     "L'acquedotto della Val Serena, fondato nel 1931, serve 9 comuni con 21.000 abitanti; le "
     "perdite sono del 27 per cento. Non ha legami con il consorzio della Val Morena.",
     "Annuario provinciale 2025"),
    ("Tariffe idriche della provincia",
     "Nella provincia la tariffa media è di 1,62 euro al metro cubo; la quota fissa media è di "
     "55 euro l'anno.", "Osservatorio provinciale 2025"),
]

# I fatti da ritrovare nella relazione (espressioni regolari sul testo in minuscolo)
FATTI_RELAZIONE = {
    "fondazione 1923": r"1923", "Valsecchi": r"valsecchi", "alluvione 1966": r"1966",
    "Pizzo Grigio 412 l/s": r"412", "acquedotto 386 km": r"386", "14 comuni": r"\b14\b|quattordici",
    "Lago Nero 2,1 milioni m³": r"2[,.]1\s*milion", "Canneto 2011": r"2011",
    "60.000 abitanti equivalenti": r"60[.\s]?000|sessantamila",
    "1.900 campioni": r"1[.\s]?900|millenovecento", "52.300 abitanti": r"52[.\s]?300",
    "168 litri": r"168", "perdite 31,4 %": r"31[,.]4", "obiettivo 22 % al 2030": r"\b22\b",
    "tariffa 1,37": r"1[,.]37", "quota fissa 48": r"\b48\b", "bonus 1.150 famiglie": r"1[.\s]?150",
    "Ferraris": r"ferraris", "74 dipendenti": r"\b74\b", "Rete Viva 18,6 milioni": r"18[,.]6",
    "9.400 contatori": r"9[.\s]?400",
}


class BibliotecaFinta:
    """La biblioteca della misura: le fonti qui sopra, per parole in comune con la domanda."""

    def cerca(self, domanda: str):
        import math
        import re as _re
        from types import SimpleNamespace as NS
        parole = {w[:5] for w in _re.findall(r"\w+", domanda.lower()) if len(w) > 3}
        corpi = [(t + " " + testo).lower() for t, testo, _ in FONTI_RELAZIONE]
        # Le parole comuni a tutte le fonti (consorzio, Val Morena…) pesano poco
        peso = {w: math.log((len(corpi) + 1) / (1 + sum(w in c for c in corpi)))
                for w in parole}
        punti = []
        for i, (t, testo, fonte) in enumerate(FONTI_RELAZIONE):
            s = sum(peso[w] * (1 + (w in t.lower())) for w in parole if w in corpi[i])
            punti.append((s, -i, t, testo, fonte))
        punti.sort(reverse=True)
        return [NS(titolo=t, fonte=f, testo=testo + " " + _RIEMPI * 7)
                for s, _, t, testo, f in punti[:4] if s > 0.3]


def fatti_trovati(testo: str) -> dict:
    import re as _re
    t = (testo or "").lower()
    return {k: bool(_re.search(rx, t)) for k, rx in FATTI_RELAZIONE.items()}


COMPITI = {"eventi": ("codice", COMPITO), "validatori": ("codice", COMPITO_VALIDATORI),
           "relazione": ("ricerca", COMPITO_RELAZIONE)}


def verifica_codice(compito: str, cartella: Path, uscita: Path) -> tuple[str, bool]:
    if compito == "eventi":
        return test_nascosto(cartella, uscita)
    from calliope.agenti.sandbox import Isolamento, Sandbox
    dest = uscita / "verifica"
    shutil.rmtree(dest, ignore_errors=True)
    sb = Sandbox(dest, tempo_s=60, isolamento=Isolamento("processo", "misura"))
    p = Path(cartella) / "validatori.py"
    if p.is_file():
        sb.scrivi("validatori.py", p.read_text(encoding="utf-8", errors="replace"))
    sb.scrivi("test_nascosto_misura.py", TEST_VALIDATORI % json.dumps(casi_validatori()))
    r = sb.test("test_nascosto_misura.py")
    return r["esito"], bool(r["passano"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compito", choices=sorted(COMPITI), default="eventi")
    ap.add_argument("--finestra", type=int, default=0, help="agenti_num_ctx (0 = auto/predefinito)")
    ap.add_argument("--minuti", type=float, default=8.0)
    ap.add_argument("--passi", type=int, default=24)
    ap.add_argument("--uscita", default="")
    ap.add_argument("--etichetta", default="")
    args = ap.parse_args()

    from calliope.agenti import carica
    from calliope.agenti import contesto_lavoro as cl
    from calliope.agenti.arbitro import Arbitro
    from calliope.agenti.ciclo import Agente, Annullato, Lavoro, Limite
    from calliope.agenti.impostazioni import ssh_eseguibile
    from calliope.agenti.remoto import crea_cliente
    from calliope.agenti.sandbox import Isolamento, Sandbox
    from calliope.agenti.tunnel import Tunnel
    from calliope.config import load_config

    tipo, testo_compito = COMPITI[args.compito]
    cfg = load_config()
    cfg.agenti_url = None
    cfg.agenti_tempo_max_min = args.minuti
    cfg.agenti_max_passi = args.passi
    if args.finestra:
        cfg.agenti_num_ctx = args.finestra
    imp = carica(cfg)
    if imp is None:
        sys.exit("Nessun agente: serve dgx.yaml accanto a calliope.yaml.")
    uscita = Path(args.uscita or tempfile.mkdtemp(prefix="calliope-ctxag-"))
    uscita.mkdir(parents=True, exist_ok=True)
    tunnel = None
    if imp.tunnel:
        tunnel = Tunnel(imp.ssh_alias, imp.porta_locale, imp.porta_remota, imp.timeout_s,
                        ssh=ssh_eseguibile(), log=lambda m: None)
        code = tunnel.assicura(imp.timeout_s)
        if code != "ok":
            sys.exit(f"tunnel: {code}")
    cliente = crea_cliente(imp)
    righe_log = []

    def log(m):
        righe_log.append(m)
        print("   " + m, flush=True)

    ag = Agente(cfg, imp, cliente, Arbitro(False), log=log)
    lav = Lavoro("ctx1", tipo, testo_compito, persona_nome="Dario", livello="amministra")
    lav.inizio = time.time()
    # La cronologia: ogni passata (con le chiamate) e ogni diario (con il testo), per vedere
    # se dopo il diario l'agente rifà cose già fatte o perde decisioni
    cronologia = []
    orig = cliente.chat

    def chat(body, **kw):
        out = orig(body, **kw)
        diario = body.get("format") is not None and "fatto" in json.dumps(body.get("format"))
        voce = {"tipo": "diario" if diario else "passata", "prompt": out.get("prompt"),
                "eval": out.get("eval"), "ragionamento": out.get("ragionamento"),
                "s": out.get("s"), "max_tokens": (body.get("options") or {}).get("num_predict"),
                "budget": body.get("thinking_budget")}
        if diario:
            voce["contenuto"] = out.get("content")
        else:
            voce["chiamate"] = [
                {"nome": c.get("name"), **{k: (str(v)[:80] if k != "contenuto" else len(str(v)))
                                           for k, v in (c.get("arguments") or {}).items()
                                           if k in ("percorso", "domanda", "contenuto", "esito",
                                                    "da_carattere")}}
                for c in (out.get("tool_calls") or [])]
        cronologia.append(voce)
        return out
    cliente.chat = chat
    orig_diario = cl.ContestoLavoro.diario_ora

    def diario_ora(self, messages, elenco_file=None, diario_modello=None):
        prima = int(self.uso.get("diari_modello") or 0)
        t = time.perf_counter()
        ok = orig_diario(self, messages, elenco_file, diario_modello)
        if ok:
            cronologia.append({"tipo": "diario_fatto", "giro": self.giri,
                               "dal_modello": int(self.uso.get("diari_modello") or 0) > prima,
                               "s": round(time.perf_counter() - t, 2),
                               "testo": messages[1]["content"][len(self.compito or ""):]})
        return ok
    cl.ContestoLavoro.diario_ora = diario_ora
    sb = None
    t0 = time.time()
    try:
        if tipo == "codice":
            sb = Sandbox(uscita / "sandbox", 60, 1024, isolamento=Isolamento("processo", "misura"))
            if args.compito == "eventi":
                for nome, testo in file_iniziali().items():
                    sb.scrivi(nome, testo)
            ris = ag.codice(lav, sb)
        else:
            ag.biblioteca = BibliotecaFinta()
            ris = ag.ricerca(lav)
    except (Limite, Annullato) as e:
        ris = {"esito": "limite", "motivo": str(e)}
    minuti = (time.time() - t0) / 60
    if tipo == "codice":
        dest = uscita / "risultato"
        sb.copia_in(dest)
        esito_n, ok_n = verifica_codice(args.compito, dest, uscita)
        qualita = {"nascosto": esito_n, "nascosto_ok": ok_n, "test_agente": ris.get("test")}
    else:
        trovati = fatti_trovati(ris.get("testo"))
        (uscita / "relazione.txt").write_text(str(ris.get("testo") or ""), encoding="utf-8")
        qualita = {"fatti": f"{sum(trovati.values())}/{len(trovati)}",
                   "mancano": [k for k, v in trovati.items() if not v],
                   "caratteri": len(str(ris.get("testo") or ""))}
    passate = [c for c in cronologia if c["tipo"] == "passata"]
    diari = [c for c in cronologia if c["tipo"] == "diario"]
    uso = getattr(lav, "uso_contesto", {}) or {}
    riga = {"etichetta": args.etichetta, "compito": args.compito,
            "finestra_chiesta": args.finestra or "predefinita",
            "esito": ris.get("esito"), "motivo": ris.get("motivo"), **qualita,
            "passi": lav.passi, "token": lav.token,
            "ragionamento": getattr(lav, "ragionamento", None),
            "letti": lav.prompt_token,
            "picco_prompt": max((p["prompt"] or 0) for p in passate) if passate else 0,
            "contesto": uso, "minuti": round(minuti, 2),
            "gpu_s": round(sum(float(c.get("s") or 0) for c in cronologia
                               if c["tipo"] in ("passata", "diario")), 1),
            "diari_modello": {"n": len(diari), "s": [c["s"] for c in diari],
                              "token": [c["eval"] for c in diari],
                              "prompt": [c["prompt"] for c in diari]},
            "uscita": str(uscita)}
    print(json.dumps(riga, ensure_ascii=False), flush=True)
    riga["cronologia"] = cronologia
    (uscita / "misura.json").write_text(json.dumps(riga, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    cliente.close()
    if tunnel is not None:
        tunnel.chiudi()


if __name__ == "__main__":
    main()
