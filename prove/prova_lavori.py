import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Banco «lavori» per gli agenti (docs/ricerche/2026-10-02-llm-per-spark.md §8.2).

    python prove\\prova_lavori.py                    # locale: agente = gemma4:e4b-it-qat sullo
                                                     #   stesso Ollama della voce (127.0.0.1:11434)
    python prove\\prova_lavori.py --dgx              # la DGX: dgx.yaml accanto a calliope.yaml
                                                     #   (tunnel SSH, modello di dgx.yaml)
    python prove\\prova_lavori.py --url http://192.168.1.50:11434 --modello qwen3.6:35b
    opzioni: --solo codice|documenti|contesa (anche più volte), --compiti c01,d03,
             --uscita <cartella> (dove restano i risultati; predefinita una temporanea),
             --passi N, --minuti M (tetti per compito), --modello X,
             --scrittore Y (modello dei documenti, stesso server dell'agente),
             --rivaluta <cartella> (solo i criteri, sui JSON dei documenti salvati in
             <cartella>/documenti da un banco già fatto: nessun modello)
    variabile d'ambiente equivalente a --dgx: CALLIOPE_LAVORI_DGX=1

Tre parti, con le soglie decise PRIMA di provare (come per la biblioteca):

1. **Codice, 12 compiti** con test nascosti che decidono da soli (script sui file, CSV →
   Excel, PowerShell, pagina web, correzione di un bug, funzione in un modulo con i test,
   un piccolo tool di Calliope, numeri romani, log, IBAN, riga di comando), più uno (c13,
   dal 04/10) che deve **chiedere** un dato della persona (la tariffa della sua azienda)
   prima di scrivere codice, invece di inventarlo. Per ogni compito:
   test nascosti superati al primo tentativo (fotografia del codice alla prima esecuzione
   dell'agente) e alla fine, test dell'agente, passate, token, minuti.
   Soglia per un agente da usare: ≥ 9/12 alla fine.
2. **Documenti, 12 compiti** (3 su modelli: verbale di condominio, preventivo con dati
   mancanti, curriculum): documento valido, dati detti presenti, numeri inventati, lunghezza,
   minuti; il preventivo senza cliente deve **chiedere**, non inventare. L'italiano lo giudica
   una persona (Dario) sui file in --uscita, su una scala fissa da 1 a 5.
   Soglia: ≥ 10/12 validi con i dati al 100 % e nessun dato inventato.
3. **Contesa**: la prima frase della voce (5 domande brevi con gemma4, prompt e tool veri)
   da sola, con un lavoro in corso senza arbitro e con l'arbitro. Con l'agente sullo stesso
   Ollama la contesa è vera; con la DGX la GPU non è condivisa e la voce deve restare
   uguale (nessun lock o coda in comune). Soglia: con l'arbitro, mediana ≤ +0,15 s rispetto
   alla voce da sola.

Con un modello piccolo in locale il punteggio sarà basso: in locale serve a verificare il
banco, non l'agente. Non scarica niente; con --dgx apre il tunnel (lo chiude alla fine).
"""

import argparse
import datetime
import json
import re
import shutil
import statistics
import tempfile
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
MODELLI = RADICE / "prove" / "lavori" / "modelli"

# ═══════════════════════════ compiti di codice ═══════════════════════════
# (id, compito, file iniziali, test nascosto)
CODICE = [
    ("c01",
     "Scrivi il modulo rinomina_foto.py con una funzione rinomina_cartella(cartella) che "
     "rinomina ogni file .jpg della cartella mettendo davanti la data di ultima modifica nel "
     "formato AAAA-MM-GG_ (per esempio 2026-09-14_mare.jpg), lascia stare i file che hanno "
     "già una data davanti e gli altri tipi di file, e restituisce l'elenco dei nuovi nomi in "
     "ordine alfabetico. Con i test.", {},
     """import datetime, os, tempfile, time
from rinomina_foto import rinomina_cartella

def test_rinomina():
    d = tempfile.mkdtemp(dir='.')
    for n in ('mare.jpg', 'gatto.JPG', 'note.txt', '2026-01-02_vecchia.jpg'):
        open(os.path.join(d, n), 'w').write('x')
    t = time.mktime(datetime.datetime(2026, 9, 14, 10, 0).timetuple())
    for n in ('mare.jpg', 'gatto.JPG', 'note.txt'):
        os.utime(os.path.join(d, n), (t, t))
    nuovi = rinomina_cartella(d)
    files = sorted(os.listdir(d))
    assert '2026-09-14_mare.jpg' in files
    assert '2026-09-14_gatto.JPG' in files
    assert 'note.txt' in files
    assert '2026-01-02_vecchia.jpg' in files
    assert sorted(nuovi) == ['2026-09-14_gatto.JPG', '2026-09-14_mare.jpg']
"""),
    ("c02",
     "Scrivi il modulo doppioni.py con una funzione trova_doppioni(cartella) che trova i file "
     "con lo stesso contenuto (anche nelle sottocartelle) e restituisce una lista di gruppi: "
     "ogni gruppo è la lista ordinata dei percorsi relativi alla cartella, con «/» come "
     "separatore; solo i gruppi con almeno due file, ordinati per il primo percorso. Con i "
     "test.", {},
     """import os, tempfile
from doppioni import trova_doppioni

def test_doppioni():
    d = tempfile.mkdtemp(dir='.')
    os.makedirs(os.path.join(d, 'sotto'))
    for n, c in (('a.txt', 'uno'), ('b.txt', 'due'), ('sotto/c.txt', 'uno'), ('d.txt', 'due'),
                 ('e.txt', 'tre')):
        open(os.path.join(d, n), 'w').write(c)
    assert trova_doppioni(d) == [['a.txt', 'sotto/c.txt'], ['b.txt', 'd.txt']]

def test_vuota():
    assert trova_doppioni(tempfile.mkdtemp(dir='.')) == []
"""),
    ("c03",
     "Scrivi il modulo csv_excel.py con una funzione csv_a_excel(percorso_csv, percorso_xlsx) "
     "che legge un CSV con il punto e virgola come separatore e la prima riga di intestazione, "
     "e scrive un file Excel (openpyxl) con un foglio «Dati»: intestazione in grassetto, i "
     "numeri come numeri (anche con la virgola decimale, «12,5» → 12.5), il resto come testo. "
     "Restituisce il numero di righe di dati. Con i test.", {},
     """import tempfile, os, openpyxl
from csv_excel import csv_a_excel

def test_csv():
    d = tempfile.mkdtemp(dir='.')
    c = os.path.join(d, 'spese.csv')
    open(c, 'w', encoding='utf-8').write('voce;importo\\naffitto;800\\nluce;90,5\\n')
    x = os.path.join(d, 'spese.xlsx')
    assert csv_a_excel(c, x) == 2
    ws = openpyxl.load_workbook(x)['Dati']
    assert ws['A1'].value == 'voce' and ws['A1'].font.bold
    assert ws['B2'].value == 800 and ws['B3'].value == 90.5 and ws['A3'].value == 'luce'
"""),
    ("c04",
     "Scrivi lo script PowerShell pulisci_temp.ps1 che cancella i file più vecchi di N giorni "
     "da una cartella: parametri -Cartella (obbligatorio) e -Giorni (predefinito 30), supporto "
     "di -WhatIf (CmdletBinding con SupportsShouldProcess), ricorsivo nelle sottocartelle, e "
     "alla fine scrive quanti file ha cancellato. Non lo puoi eseguire: scrivilo con cura.", {},
     """import re

def test_ps1():
    s = open('pulisci_temp.ps1', encoding='utf-8-sig').read()
    low = s.lower()
    assert 'param' in low and '$cartella' in low and '$giorni' in low
    assert re.search(r'\\$giorni\\s*=\\s*30', low)
    assert 'supportsshouldprocess' in low and 'shouldprocess' in low.replace('supportsshouldprocess', '')
    assert 'get-childitem' in low and '-recurse' in low and 'lastwritetime' in low
    assert 'remove-item' in low and ('adddays' in low)
"""),
    ("c05",
     "Scrivi spesa.html: una pagina web statica per la lista della spesa, tutto in un file "
     "(niente librerie esterne): un campo di testo, un pulsante «Aggiungi», l'elenco delle "
     "voci; ogni voce si toglie con un clic; la lista resta salvata nel browser "
     "(localStorage). In italiano.", {},
     """from html.parser import HTMLParser

class P(HTMLParser):
    def __init__(self):
        super().__init__(); self.tags = []; self.script = ''; self._s = False; self.ext = False
    def handle_starttag(self, t, a):
        self.tags.append(t); self._s = t == 'script'
        a = dict(a)
        if t == 'script' and a.get('src', '').startswith('http'): self.ext = True
        if t == 'link' and a.get('href', '').startswith('http'): self.ext = True
    def handle_endtag(self, t):
        if t == 'script': self._s = False
    def handle_data(self, d):
        if self._s: self.script += d

def test_pagina():
    p = P(); p.feed(open('spesa.html', encoding='utf-8').read())
    assert 'input' in p.tags and 'button' in p.tags and ('ul' in p.tags or 'ol' in p.tags)
    assert 'localStorage' in p.script and not p.ext
    assert 'addEventListener' in p.script or 'onclick' in open('spesa.html', encoding='utf-8').read().lower()
"""),
    ("c06",
     "Il file media.py ha degli errori: correggili. media(valori) deve restituire la media "
     "aritmetica, None per una lista vuota; mediana(valori) la mediana (None se vuota). Non "
     "cambiare i nomi. Aggiungi i test.",
     {"media.py": "def media(valori):\n    return sum(valori) / len(valori) - 1\n\n\n"
                  "def mediana(valori):\n    v = sorted(valori)\n    return v[len(v) // 2]\n"},
     """from media import media, mediana

def test_media():
    assert media([2, 4, 6]) == 4 and media([]) is None and media([1.5, 2.5]) == 2.0

def test_mediana():
    assert mediana([3, 1, 2]) == 2 and mediana([4, 1, 3, 2]) == 2.5 and mediana([]) is None
"""),
    ("c07",
     "Nel modulo testo.py aggiungi la funzione parole_frequenti(testo, n) che restituisce le "
     "n parole più frequenti come lista di coppie (parola, conteggio): parole in minuscolo, "
     "senza punteggiatura, a parità di conteggio in ordine alfabetico. I test che ci sono già "
     "devono continuare a passare.",
     {"testo.py": "import re\n\n\ndef conta_parole(testo):\n"
                  "    return len(re.findall(r\"\\w+\", testo))\n",
      "test_testo.py": "from testo import conta_parole\n\n\ndef test_conta():\n"
                       "    assert conta_parole('Ciao, mondo!') == 2\n"},
     """from testo import conta_parole, parole_frequenti

def test_frequenti():
    t = 'Il gatto e il cane. Il cane dorme, il gatto no!'
    assert parole_frequenti(t, 3) == [('il', 4), ('cane', 2), ('gatto', 2)]
    assert parole_frequenti('', 2) == []

def test_vecchio():
    assert conta_parole('uno due tre') == 3
"""),
    ("c08",
     "Scrivi un piccolo tool per Calliope nel modulo tool_giorni.py: una costante SPEC con lo "
     "schema della funzione nel formato OpenAI ({\"type\": \"function\", \"function\": "
     "{\"name\": \"giorni_mancanti\", \"description\": …, \"parameters\": {…}}}, parametro "
     "obbligatorio «data» di tipo stringa AAAA-MM-GG) e la funzione giorni_mancanti(data, "
     "oggi=None) che restituisce {\"giorni\": n, \"da_dire\": frase}: «mancano 12 giorni», "
     "«manca 1 giorno», «è oggi», «è passato da 3 giorni». oggi è una data AAAA-MM-GG "
     "(predefinita: la data di oggi). Data non valida: {\"errore\": …}. Con i test.", {},
     """from tool_giorni import SPEC, giorni_mancanti

def test_spec():
    f = SPEC['function']
    assert SPEC['type'] == 'function' and f['name'] == 'giorni_mancanti'
    assert 'data' in f['parameters']['properties'] and 'data' in f['parameters']['required']

def test_frasi():
    assert giorni_mancanti('2026-10-14', oggi='2026-10-02') == {'giorni': 12, 'da_dire': 'mancano 12 giorni'}
    assert giorni_mancanti('2026-10-03', oggi='2026-10-02')['da_dire'] == 'manca 1 giorno'
    assert giorni_mancanti('2026-10-02', oggi='2026-10-02')['da_dire'] == 'è oggi'
    assert giorni_mancanti('2026-09-29', oggi='2026-10-02')['da_dire'] == 'è passato da 3 giorni'
    assert 'errore' in giorni_mancanti('ieri', oggi='2026-10-02')
"""),
    ("c09",
     "Scrivi il modulo romani.py con intero_a_romano(n) (1–3999, ValueError fuori) e "
     "romano_a_intero(s) che accetta solo numeri romani scritti correttamente (ValueError per "
     "«IIII», «VX», «MMMM» o lettere sbagliate; maiuscole o minuscole). Con i test.", {},
     """import pytest_free_raises as _r
from romani import intero_a_romano, romano_a_intero

def test_avanti_indietro():
    for n in (1, 4, 9, 14, 40, 90, 400, 1994, 2026, 3999):
        assert romano_a_intero(intero_a_romano(n)) == n
    assert intero_a_romano(1994) == 'MCMXCIV' and romano_a_intero('mmxxvi') == 2026

def test_errori():
    for bad in ('IIII', 'VX', 'MMMM', 'ABC', ''):
        assert _r.solleva(ValueError, romano_a_intero, bad), bad
    for bad in (0, 4000, -1):
        assert _r.solleva(ValueError, intero_a_romano, bad), bad
"""),
    ("c10",
     "Scrivi il modulo riassunto_log.py con una funzione riassunto(percorso) che legge un log "
     "come esempio.log e restituisce un dizionario {data: {\"ERROR\": n, \"WARNING\": m}} con "
     "i conteggi per giorno (date AAAA-MM-GG, solo i giorni con almeno un errore o un avviso; "
     "le righe malformate si saltano). Con i test.",
     {"esempio.log": "2026-09-30 10:00:01 INFO avvio\n2026-09-30 10:00:02 ERROR disco pieno\n"
                     "2026-09-30 11:00:00 WARNING memoria bassa\nriga rotta\n"
                     "2026-10-01 08:00:00 ERROR rete giù\n2026-10-01 09:00:00 ERROR rete giù\n"
                     "2026-10-02 07:00:00 INFO tutto bene\n"},
     """from riassunto_log import riassunto

def test_log():
    r = riassunto('esempio.log')
    assert r == {'2026-09-30': {'ERROR': 1, 'WARNING': 1}, '2026-10-01': {'ERROR': 2, 'WARNING': 0}}
"""),
    ("c11",
     "Scrivi il modulo iban.py con iban_valido(s) per gli IBAN italiani: spazi ammessi, "
     "maiuscole o minuscole, lunghezza 27, «IT», controllo del modulo 97. Restituisce True o "
     "False. Con i test.", {},
     """from iban import iban_valido

def test_iban():
    assert iban_valido('IT60 X054 2811 1010 0000 0123 456')
    assert iban_valido('it60x0542811101000000123456')
    assert not iban_valido('IT61X0542811101000000123456')
    assert not iban_valido('DE89370400440532013000')
    assert not iban_valido('IT60X054281110100000012345')
"""),
    ("c12",
     "Scrivi conta.py, un programma da riga di comando come wc: conta righe, parole e "
     "caratteri di un file di testo (UTF-8) e stampa «righe parole caratteri nomefile»; con "
     "l'opzione -r stampa solo le righe. Usa argparse e una funzione main(argv) che "
     "restituisce 0 (1 se il file non c'è, con un messaggio in italiano su stderr). Con i "
     "test.", {},
     """import io, contextlib, os, tempfile
from conta import main

def test_conta():
    d = tempfile.mkdtemp(dir='.')
    f = os.path.join(d, 'a.txt')
    open(f, 'w', encoding='utf-8').write('ciao mondo\\nè bello\\n')
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert main([f]) == 0
    assert out.getvalue().split()[:3] == ['2', '4', '19']
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert main(['-r', f]) == 0
    assert out.getvalue().split()[0] == '2'
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert main([os.path.join(d, 'non_ce.txt')]) == 1
"""),
    # Un dato della persona che l'agente non può sapere (verifica sulla DGX del 04/10:
    # qwen3.6 usava 0,21 €/km senza chiedere). Nessun test: deve chiedere (consegna con
    # esito mancano_dati) prima di scrivere un .py
    ("c13",
     "Scrivi lo script rimborso.py che legge viaggi.csv (colonne data e km) e stampa il "
     "rimborso chilometrico totale in euro con la tariffa al chilometro che usa la mia azienda.",
     {"viaggi.csv": "data,km\n2026-09-01,120\n2026-09-08,85.5\n2026-09-15,40\n"
                    "2026-09-22,210\n"},
     None),
]
# Un aiuto per i test nascosti senza pytest (c09)
AIUTO_RAISES = ("def solleva(exc, f, *a):\n    try:\n        f(*a)\n    except exc:\n"
                "        return True\n    except Exception:\n        return False\n    return False\n")

# ═══════════════════════════ compiti di documenti ═══════════════════════════
# (id, compito, formato, modello, dati che devono esserci, controllo extra(doc) → bool, attesa)
DOCUMENTI = [
    ("d01", "Prepara una relazione sui consumi di casa nel 2025, con le sezioni introduzione, "
            "luce, gas, acqua e conclusioni: luce 2.400 kWh (nel 2024 erano 2.700), gas 900 metri "
            "cubi (nel 2024 1.050), acqua 110 metri cubi. Il risparmio sulla luce è di 300 kWh.",
     "word", "", ["2.400|2400", "2.700|2700", "900", "1.050|1050", "110", "300"],
     lambda d: _sezioni_nominate(d, ("introduzione", "luce", "gas", "acqua", "conclusioni")) >= 4,
     "fatto"),
    ("d02", "Prepara la scaletta di una presentazione di 8 diapositive sulla raccolta "
            "differenziata per la scuola di Luca: una sezione con un titolo per ogni "
            "diapositiva e 2–4 punti ciascuna; nella diapositiva dei numeri: in Italia il 65 per "
            "cento di differenziata nel 2023.",
     "word", "", ["65"], lambda d: 7 <= _sezioni_piene(d) <= 11, "fatto"),
    ("d03", "Scrivi una lettera formale al Comune per chiedere la manutenzione del marciapiede "
            "di via Roma 12, rotto da marzo; cita la segnalazione del 3 marzo con protocollo 4521 "
            "e chiedi una risposta entro 30 giorni.",
     "word", "", ["4521", "via Roma 12|Via Roma 12", "30"], lambda d: _paragrafi(d) >= 5, "fatto"),
    ("d04", "Prepara un business plan breve per un piccolo forno di quartiere: descrizione, "
            "mercato, una tabella degli investimenti con il totale (forno 12.000 euro, arredi "
            "5.000, licenze 1.500), ricavi previsti il primo anno 85.000 euro e costi 60.000.",
     "word", "", ["12.000|12000", "5.000|5000", "1.500|1500", "85.000|85000", "60.000|60000"],
     # Le sezioni chieste, oltre alla tabella: il 02/10 la bozza con «la domanda di prodotti
     # freschi» lo faceva impaginare come una lettera («Spett.le…», nessuna sezione)
     lambda d: _totale(d, 18500) and _sezioni_nominate(d, ("descrizione", "mercato")) >= 2,
     "fatto"),
    ("d05", "Scrivi il regolamento per l'uso del cortile del condominio: orari dalle 8 alle 20, "
            "biciclette solo nella rastrelliera, niente pallonate contro i muri, cani al "
            "guinzaglio, pulizia a carico di chi sporca. Con un articolo per regola.",
     "word", "", ["8", "20"], lambda d: _paragrafi(d) + _voci(d) >= 5, "fatto"),
    ("d06", "Prepara le istruzioni per la babysitter: Luca ha 6 anni e va a letto alle 21, Sara "
            "ha 3 anni, è allergica alle arachidi e va a letto alle 20; cena alle 19:30; i "
            "numeri utili lasciali come segnaposto.",
     "pdf", "", ["6", "3", "21", "20", "19:30|19.30", "arachidi"],
     lambda d: _paragrafi(d) + _voci(d) >= 4, "fatto"),
    ("d07", "Scrivi il verbale della riunione di famiglia di domenica: decisioni: vacanze al "
            "lago di Garda dal 10 al 17 agosto, paghetta di Luca a 10 euro a settimana, turni "
            "per lavare i piatti (lunedì Luca, martedì Sara, mercoledì papà).",
     "word", "", ["Garda", "10", "17", "Luca", "Sara"], lambda d: _paragrafi(d) + _voci(d) >= 4,
     "fatto"),
    ("d08", "Prepara una relazione tecnica sull'impianto fotovoltaico di casa: 6 kW di potenza, "
            "14 pannelli, inverter da 5 kW, produzione 2025 di 7.800 kWh, autoconsumo 45 per "
            "cento; con le sezioni impianto, produzione, consigli.",
     "pdf", "", ["6", "14", "5", "7.800|7800", "45"],
     lambda d: _sezioni_nominate(d, ("impianto", "produzione", "consigli")) >= 3, "fatto"),
    ("d09", "Fammi un foglio Excel con il piano delle spese del viaggio a Lisbona: volo 320 "
            "euro, hotel 380, trasporti 60, musei 75, cibo 250, con il totale.",
     "excel", "", ["320", "380", "60", "75", "250"], lambda d: _totale(d, 1085), "fatto"),
    ("d10", "Compila il verbale dell'assemblea del condominio Le Querce del 3 ottobre 2026 alle "
            "21: presiede Mario Rossi, verbalizza Elena Bianchi; presenti Rossi, Bianchi, Verdi "
            "e Neri; ordine del giorno: rifacimento della facciata, ascensore; decisioni: "
            "facciata approvata con 3 preventivi da chiedere, ascensore rimandato a gennaio.",
     "word", "verbale_condominio", ["Le Querce", "Mario Rossi", "Elena Bianchi", "Verdi",
                                    "Neri", "facciata", "gennaio"], None, "fatto"),
    ("d11", "Compila un preventivo per l'imbiancatura del soggiorno: imbiancatura 800 euro, "
            "materiali 150 euro, valido 30 giorni.",
     "word", "preventivo", [], None, "mancano_dati"),
    ("d12", "Compila il curriculum di Sara Esposito, di Bologna: profilo: insegnante di "
            "matematica con la passione per la divulgazione; esperienze: 2018–2026 docente al "
            "liceo Galvani, 2015–2018 tutor universitaria; studi: laurea in matematica a Bologna "
            "nel 2014; lingue: inglese C1, francese B1.",
     "word", "curriculum", ["Sara Esposito", "Bologna", "Galvani", "2014", "C1", "B1"], None,
     "fatto"),
]


def _blocchi(d):
    if not d:
        return []
    return d.get("blocchi") or []


def _titoli(d):
    """Titoli come blocchi «titolo» (la forma giusta: in Word diventano «Titolo 2»)."""
    return sum(b.get("tipo") == "titolo" for b in _blocchi(d))


# Una riga che fa da titolo di sezione: breve, senza la punteggiatura di fine frase e con
# l'iniziale maiuscola o un numero («INTRODUZIONE», «Diapositiva 1: Perché separare»,
# «ARTICOLO 2 – Biciclette», «Consigli:»). Il formato di calliope/documenti non ha il
# grassetto: un titolo è un blocco «titolo» oppure, se il modello l'ha messo nel testo,
# un paragrafo di una riga breve seguito da altro, o la prima riga di un paragrafo seguita
# da un a capo (il render la mostra su una riga sua).
_RIGA_TITOLO_MAX = 80


def _riga_titolo(riga: str) -> bool:
    r = riga.strip()
    if not r or len(r) > _RIGA_TITOLO_MAX or len(r.split()) > 10:
        return False
    if r[-1] in ".;,!?…»\"" or r.startswith(("-", "•", "*", "[")):
        return False
    return r[0].isupper() or r[0].isdigit()


def _titoli_testi(d) -> list[str]:
    """I titoli di sezione del documento, in tutte le forme equivalenti (vedi sopra)."""
    out = []
    blocchi = _blocchi(d)
    for i, b in enumerate(blocchi):
        if b.get("tipo") == "titolo":
            out.append(str(b.get("testo") or ""))
        elif b.get("tipo") == "paragrafo":
            righe = str(b.get("testo") or "").split("\n")
            seguito = len(righe) > 1 or (i + 1 < len(blocchi)
                                         and blocchi[i + 1].get("tipo") != "titolo")
            if seguito and _riga_titolo(righe[0]):
                out.append(righe[0].strip())
    return out


def _sezioni(d) -> int:
    return len(_titoli_testi(d))


def _sezioni_piene(d) -> int:
    """Le sezioni con un contenuto: il 02/10 una scaletta aveva 8 titoli e il testo solo
    sotto i primi due."""
    from calliope.documenti.scrittore import empty_sections
    return _sezioni(d) - len(empty_sections(d or {}))


def _sezioni_nominate(d, nomi) -> int:
    """Quante delle sezioni chieste hanno un titolo che le nomina."""
    titoli = [t.lower() for t in _titoli_testi(d)]
    return sum(any(n in t for t in titoli) for n in nomi)


def _paragrafi(d):
    return sum(b.get("tipo") == "paragrafo" for b in _blocchi(d))


def _voci(d):
    return sum(len(b.get("voci") or []) for b in _blocchi(d) if b.get("tipo") == "elenco")


def _totale(d, atteso):
    """La tabella con il totale calcolato dal programma (come nel file)."""
    from calliope.documenti.formato import table_total
    tabelle = [b for b in _blocchi(d) if b.get("tipo") == "tabella"] + list(
        (d or {}).get("fogli") or [])
    for t in tabelle:
        if not t.get("totale"):
            continue
        tot = table_total(t["colonne"], t["righe"])
        if any(re.sub(r"[^\d]", "", str(x or "")) == str(atteso) for x in tot or []):
            return True
    return False


def _testo_doc(d) -> str:
    return json.dumps(d or {}, ensure_ascii=False)


def _norm_num(s: str) -> str:
    return s.replace(".", "").replace(",", "")


_NUMERO = re.compile(r"\d[\d.,]*\d|\d")


def valore(n: str) -> float | None:
    """Il valore di un numero scritto all'italiana («2.400» = 2400, «14,3» = 14.3); il punto
    seguito da 1–2 cifre è un decimale all'inglese (i numeri del JSON: 12.5)."""
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", n):
        return float(n.replace(".", ""))
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})*,\d+", n) or re.fullmatch(r"\d+,\d+", n):
        return float(n.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d+(?:\.\d+)?", n):
        return float(n)
    return None


def _decimali(n: str) -> int:
    m = re.search(r"[.,](\d{1,2})$", n)
    return len(m.group(1)) if m and not re.fullmatch(r"\d{1,3}(?:\.\d{3})+", n) else 0


def _fmt(x: float) -> str:
    return f"{x:g}" if abs(x) < 1e6 else f"{x:.0f}"


def _anno(v: float) -> bool:
    return v == int(v) and 1900 <= v <= 2100


def derivabili(compito: str) -> dict[float, str]:
    """I numeri che si ricavano dai dati della richiesta con UN calcolo semplice e
    verificabile, con la spiegazione: somma, differenza, prodotto, rapporto, percentuale di
    (a × b / 100), quota percentuale (a / b × 100), variazione percentuale ((a − b) / b ×
    100), la somma di dati consecutivi della richiesta (il totale degli investimenti
    elencati), la differenza tra due anni e il complemento a 100 di una percentuale detta
    (solo il numero seguito da «per cento» o «%»: «autoconsumo 45 per cento» → 55 immessi
    in rete). Gli operandi sono i dati maggiori di 10 e non anni: con i numeri
    piccoli d'ordine («8 diapositive», «2–4 punti», «6 anni») le combinazioni coprirebbero
    quasi ogni numero di due cifre. Per lo stesso motivo il rapporto vale solo se supera
    10, la quota percentuale solo su un totale oltre 100 e la variazione solo tra due
    grandezze simili (al più il doppio). Niente catene di calcoli: la produzione per
    pannello in watt (una conversione di unità) restano inventate. Una grandezza oltre 100
    si può anche dividere per un dato piccolo (7.800 kWh / 6 kW)."""
    dati = [v for v in (valore(n) for n in _NUMERO.findall(compito)) if v is not None]
    anni = sorted({v for v in dati if _anno(v)})
    grandi = [v for v in dati if v > 10 and not _anno(v)]
    base = {v: _fmt(v) for v in grandi}
    out: dict[float, str] = {}
    for n in re.findall(r"(\d[\d.,]*)\s*(?:per\s*cento|%)", compito, re.I):
        v = valore(n)
        if v is not None and 0 < v < 100:
            out.setdefault(100 - v, f"100 − {_fmt(v)}")
            if 100 - v > 10:
                base.setdefault(100 - v, f"(100 − {_fmt(v)})")
    for i, a in enumerate(anni):
        for b in anni[i + 1:]:
            out.setdefault(b - a, f"{_fmt(b)} − {_fmt(a)}")
    # Una grandezza divisa per un conteggio piccolo detto: «7.800 kWh / 6 kW = 1.300 ore
    # equivalenti», «7.800 / 14 pannelli». Il risultato è grande: non copre i numeri brevi
    for a in grandi:
        for b in dati:
            if a > 100 and 2 <= b <= 10 and b == int(b):
                out.setdefault(a / b, f"{_fmt(a)} / {_fmt(b)}")
    voci = list(base.items())
    for i, (a, sa) in enumerate(voci):
        for j, (b, sb) in enumerate(voci):
            if i == j:
                continue
            if i < j:
                out.setdefault(a + b, f"{sa} + {sb}")
                out.setdefault(a * b, f"{sa} × {sb}")
                out.setdefault(a * b / 100, f"{sa} × {sb} / 100")
                out.setdefault(abs(a - b), f"{sa} − {sb}" if a >= b else f"{sb} − {sa}")
            if a / b > 10:                            # «7.800 kWh / 6 kW = 1.300»
                out.setdefault(a / b, f"{sa} / {sb}")
            if a < b and b > 100:                     # quota di un totale
                out.setdefault(a / b * 100, f"{sa} / {sb} × 100")
            if max(a, b) <= 2 * min(a, b):            # stessa grandezza: 2024 contro 2025
                out.setdefault(abs(a - b) / b * 100, f"({sa} − {sb}) / {sb} × 100")
    for i in range(len(grandi)):
        for j in range(i + 3, len(grandi) + 1):       # le coppie sono già sopra
            out.setdefault(sum(grandi[i:j]), " + ".join(_fmt(v) for v in grandi[i:j]))
    return out


def _derivato(n: str, calcoli: dict[float, str]) -> str | None:
    """La spiegazione se il numero del documento è uno dei derivabili (arrotondato alle
    cifre con cui è scritto: «14,3» vale per 14,2857…, «89» per 88,89)."""
    v = valore(n)
    if v is None:
        return None
    tol = 0.5 * 10 ** -_decimali(n) + 1e-9
    for x, come in calcoli.items():
        if abs(v - x) <= tol:
            return f"{n} = {come}"
    return None


_UNITA = ("zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove",
          "dieci", "undici", "dodici", "tredici", "quattordici", "quindici", "sedici",
          "diciassette", "diciotto", "diciannove")
_DECINE = ("", "", "venti", "trenta", "quaranta", "cinquanta", "sessanta", "settanta",
           "ottanta", "novanta")


def in_lettere(n: int) -> str | None:
    """0–100 in lettere («trenta», «ventuno», «ventitré»), per i dati detti in cifre e
    scritti in lettere nel documento («entro trenta giorni»)."""
    if not 0 <= n <= 100:
        return None
    if n == 100:
        return "cento"
    if n < 20:
        return _UNITA[n]
    d, u = divmod(n, 10)
    dec = _DECINE[d]
    if u in (1, 8):
        dec = dec[:-1]
    return dec + ("" if u == 0 else "tré" if u == 3 else _UNITA[u])


_LETTERE = {in_lettere(n): n for n in range(11, 101)}


def numeri_in_lettere(testo: str) -> list[str]:
    """I numeri da 11 a 100 scritti in lettere, in cifre: il 02/10 qwen3.6 ha scritto «il
    restante cinquanta per cento» (era 55) e il banco, che guardava solo le cifre, non se
    n'era accorto. «per cento» non è il numero 100."""
    out = []
    for m in re.finditer(r"[a-zàèéìòù]+", testo.lower()):
        n = _LETTERE.get(m.group(0))
        if n is None:
            continue
        if n == 100 and re.search(r"\bper\s*$", testo.lower()[:m.start()]):
            continue
        out.append(str(n))
    return out


def dato_presente(dato: str, testo: str) -> bool:
    """«a|b»: una delle alternative c'è nel testo; un numero fino a 100 anche in lettere."""
    basso = testo.lower()
    for alt in dato.split("|"):
        if alt in testo:
            return True
        if alt.isdigit():
            parola = in_lettere(int(alt))
            if parola and re.search(rf"\b{parola}\b", basso):
                return True
    return False


def numeri_inventati(d, compito: str, derivati: list | None = None) -> list[str]:
    """Numeri nel documento che non sono nella richiesta e non se ne ricavano con un calcolo
    semplice (derivabili); esclusi la data di oggi, gli anni vicini e i numeri piccoli
    d'ordine (1–10). In `derivati` (se c'è) le spiegazioni dei numeri accettati come
    calcolati, da rileggere a mano."""
    testo = _testo_doc(d)
    detti = {_norm_num(n) for n in _NUMERO.findall(compito)}
    oggi = datetime.date.today()
    ok = detti | {str(oggi.year), str(oggi.day), str(oggi.month), str(oggi.year - 1),
                  str(oggi.year + 1)}
    calcoli = derivabili(compito)
    out = []
    for n in _NUMERO.findall(testo) + numeri_in_lettere(testo):
        k = _norm_num(n)
        if k in ok or (k.isdigit() and int(k) <= 10):
            continue
        come = _derivato(n, calcoli)
        if come:
            if derivati is not None and come not in derivati:
                derivati.append(come)
            continue
        out.append(n)
    return sorted(set(out))


# ═══════════════════════════ esecuzione ═══════════════════════════

def prepara(args):
    """(cfg, impostazioni, etichetta) secondo la modalità."""
    from calliope.agenti import carica
    from calliope.config import Config, load_config
    dgx = args.dgx or os.environ.get("CALLIOPE_LAVORI_DGX") == "1"
    if dgx:
        cfg = load_config()               # dgx.yaml accanto a calliope.yaml (o CALLIOPE_AGENTI_CONFIG)
        cfg.agenti_url = None
        if args.modello:
            cfg.agenti_modello = args.modello
        etichetta = "DGX"
    else:
        cfg = Config()                    # niente file: la voce e l'agente di predefinito
        cfg.agenti_url = args.url or cfg.llm_native_url
        cfg.agenti_modello = args.modello or cfg.llm_model
        etichetta = "locale" if not args.url else args.url
    cfg.agenti_conferma = "mai"
    if args.passi:
        cfg.agenti_max_passi = args.passi
    if args.minuti:
        cfg.agenti_tempo_max_min = args.minuti
    if not dgx and not args.passi:
        cfg.agenti_max_passi = 16         # un modello piccolo gira a vuoto: tetti più bassi
    if not dgx and not args.minuti:
        cfg.agenti_tempo_max_min = 6.0
    imp = carica(cfg)
    if imp is None:
        sys.exit("Nessun agente configurato: con --dgx serve dgx.yaml accanto a calliope.yaml.")
    if args.scrittore:
        imp.scrittore = args.scrittore
    return cfg, imp, etichetta


def servizio(cfg, imp, uscita: Path):
    from calliope.agenti import Lavori
    from calliope.agenti.modelli import carica_modelli
    from calliope.documenti.formato import FORMATI
    cfg.agenti_risultati = str(uscita / "risultati")
    cfg.agenti_sandbox = str(uscita / "sandbox")
    return Lavori(cfg, imp, log=lambda m: print(f"   {m}", flush=True), formati=FORMATI,
                  modelli=carica_modelli(MODELLI))


def aspetta_fine(svc, lav, limite_s):
    import queue
    t0 = time.time()
    while time.time() - t0 < limite_s:
        try:
            item = svc.done.get(timeout=1.0)
        except queue.Empty:
            if lav.stato in ("annullato",):
                return None
            continue
        if item["id"] == lav.id:
            return item
    lav.annulla.set()
    return None


def test_nascosto(cartella_risultato: Path, test: str, uscita: Path, nome: str):
    """Copia i file del risultato in una sandbox nuova, aggiunge il test nascosto e lo
    esegue con la stessa sandbox degli agenti. (eseguiti, passano)"""
    from calliope.agenti.sandbox import Sandbox
    dest = uscita / "verifica" / nome
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    sb = Sandbox(dest, tempo_s=30)
    for p in Path(cartella_risultato).rglob("*"):
        if p.is_file() and p.name != "lavoro.json":
            rel = p.relative_to(cartella_risultato).as_posix()
            try:
                sb.scrivi(rel, p.read_text(encoding="utf-8", errors="replace"))
            except Exception:  # noqa: BLE001 — file non di testo o nome non ammesso
                pass
    sb.scrivi("pytest_free_raises.py", AIUTO_RAISES)
    sb.scrivi("test_nascosto_banco.py", test)
    r = sb.test("test_nascosto_banco.py")
    return r["esito"], bool(r["passano"])


def banco_codice(svc, cfg, uscita, scelti):
    righe = []
    for cid, compito, iniziali, test in CODICE:
        if scelti and cid not in scelti:
            continue
        foto = {}

        def osserva(lav, name, sandbox, cid=cid):
            if name in ("esegui_test", "esegui_python") and "primo" not in foto:
                d = uscita / "primo" / cid
                foto["primo"] = d
                sandbox.copia_in(d)
        svc.agente.on_strumento = osserva
        lav = svc.nuovo("codice", compito, "banco", "Banco", "amministra")
        lav.file_iniziali = dict(iniziali)
        t0 = time.time()
        svc.avvia(lav)
        item = aspetta_fine(svc, lav, cfg.agenti_tempo_max_min * 60 + 120)
        minuti = (time.time() - t0) / 60
        cartella = Path((item or {}).get("cartella") or lav.risultato.get("cartella") or uscita)
        if test is None:
            # Deve chiedere prima di scrivere codice: nella cartella del lavoro sospeso
            # (copia della sandbox) non ci devono essere .py
            chiesto = lav.risultato.get("esito") in ("mancano_dati", "domanda")
            py = [f for f in Path(cartella).rglob("*.py")] if chiesto else []
            ok = chiesto and not py
            righe.append({"id": cid, "esito": lav.risultato.get("esito"), "nascosti_primo": ok,
                          "nascosti_fine": ok, "nascosti": "domanda" if chiesto else "nessuna",
                          "domanda": lav.risultato.get("domanda"), "test_agente": {},
                          "passi": lav.passi, "token": lav.token, "minuti": round(minuti, 2),
                          "cartella": str(cartella)})
            print(f"{'ok ' if ok else 'NO '} {cid}  chiede={'sì' if chiesto else 'no'}  "
                  f"codice prima della domanda={'sì' if py else 'no'}  "
                  f"domanda={lav.risultato.get('domanda')!r}  {minuti:.1f} min", flush=True)
            if lav.stato == "in_attesa":
                svc.annulla("banco")
            continue
        esito_fine, ok_fine = test_nascosto(cartella, test, uscita, cid + "_fine")
        ok_primo = False
        if "primo" in foto:
            _, ok_primo = test_nascosto(foto["primo"], test, uscita, cid + "_primo")
        propri = lav.risultato.get("test") or {}
        riga = {"id": cid, "esito": lav.risultato.get("esito"), "nascosti_primo": ok_primo,
                "nascosti_fine": ok_fine, "nascosti": esito_fine, "test_agente": propri,
                "passi": lav.passi, "token": lav.token, "minuti": round(minuti, 2),
                "cartella": str(cartella)}
        righe.append(riga)
        print(f"{'ok ' if ok_fine else 'NO '} {cid}  primo={'sì' if ok_primo else 'no'}  "
              f"fine={'sì' if ok_fine else 'no'}  agente={propri or '—'}  passi={lav.passi}  "
              f"token={lav.token}  {minuti:.1f} min  esito={lav.risultato.get('esito')}",
              flush=True)
    svc.agente.on_strumento = None
    return righe


def valuta_documento(did: str, doc, esito) -> dict:
    """I criteri del banco su un documento (JSON validato) e l'esito del lavoro."""
    _, compito, _, _, dati, extra, attesa = next(x for x in DOCUMENTI if x[0] == did)
    testo = _testo_doc(doc)
    presenti = [x for x in dati if dato_presente(x, testo)]
    derivati: list[str] = []
    inventati = numeri_inventati(doc, compito, derivati) if doc else []
    valido = doc is not None
    struttura = (extra is None or bool(extra(doc))) if valido else None
    if attesa == "mancano_dati":
        # Dal 03/10 il lavoro resta in attesa della risposta (esito «domanda»)
        ok = esito in ("mancano_dati", "domanda")
    else:
        ok = valido and len(presenti) == len(dati) and not inventati and bool(struttura)
    return {"id": did, "esito": esito, "valido": valido, "dati": f"{len(presenti)}/{len(dati)}",
            "mancanti": [x for x in dati if x not in presenti], "inventati": inventati,
            "derivati": derivati, "struttura": struttura,
            # titoli come blocchi «titolo» e in tutte le forme: se differiscono, il modello
            # ha messo i titoli nel testo (si vedono, ma non hanno lo stile di un titolo)
            "titoli_blocco": _titoli(doc) if valido else None,
            "titoli": _sezioni(doc) if valido else None,
            "caratteri": len(testo), "ok": ok}


def _stampa(riga: dict):
    print(f"{'ok ' if riga['ok'] else 'NO '} {riga['id']}  esito={riga['esito']}  "
          f"dati={riga['dati']}  inventati={riga['inventati'] or '—'}  "
          f"struttura={riga['struttura']}  titoli={riga.get('titoli')} "
          f"(blocchi {riga.get('titoli_blocco')})  {riga['caratteri']} car.  "
          f"{riga.get('minuti', 0):.1f} min"
          + (f"  derivati={riga['derivati']}" if riga.get("derivati") else "")
          + (f"  domanda={riga['domanda']!r}" if riga.get("domanda") else ""), flush=True)


def banco_documenti(svc, cfg, uscita, scelti):
    righe = []
    cartella_json = uscita / "documenti"
    cartella_json.mkdir(parents=True, exist_ok=True)
    for did, compito, formato, modello, dati, extra, attesa in DOCUMENTI:
        if scelti and did not in scelti:
            continue
        lav = svc.nuovo("documento", compito, "banco", "Banco", "amministra", formato, modello)
        t0 = time.time()
        svc.avvia(lav)
        aspetta_fine(svc, lav, cfg.agenti_tempo_max_min * 60 + 120)
        minuti = (time.time() - t0) / 60
        r = lav.risultato
        doc = r.get("documento")
        riga = valuta_documento(did, doc, r.get("esito"))
        riga.update({"minuti": round(minuti, 2), "token": lav.token, "file": r.get("file"),
                     "domanda": r.get("domanda"), "cartella": r.get("cartella")})
        # Il JSON resta accanto ai file: si rivaluta senza il modello (--rivaluta)
        (cartella_json / f"{did}.json").write_text(json.dumps(
            {"id": did, "compito": compito, "esito": r.get("esito"), "documento": doc,
             "domanda": r.get("domanda"), "minuti": round(minuti, 2), "token": lav.token},
            ensure_ascii=False, indent=1), encoding="utf-8")
        righe.append(riga)
        _stampa(riga)
    return righe


def rivaluta(cartella: Path) -> int:
    """Ricalcola i criteri dei documenti dai JSON salvati da un banco precedente."""
    righe = []
    for f in sorted((cartella / "documenti").glob("d*.json")):
        x = json.loads(f.read_text(encoding="utf-8"))
        if not any(d[0] == x["id"] for d in DOCUMENTI):
            continue
        riga = valuta_documento(x["id"], x.get("documento"), x.get("esito"))
        riga.update({"minuti": x.get("minuti") or 0, "domanda": x.get("domanda")})
        righe.append(riga)
        _stampa(riga)
    if not righe:
        print(f"Nessun JSON dei documenti in {cartella / 'documenti'}")
        return 1
    print(f"documenti: {sum(r['ok'] for r in righe)}/{len(righe)} giusti (rivalutati)")
    return 0


DOMANDE_VOCE = ["Che ore sono?", "Quanto fa 17 per 23?", "Cos'è la fotosintesi, in una frase?",
                "Che giorno è oggi?", "Dimmi una curiosità sui gatti in una frase."]


def banco_contesa(svc, cfg, giri=2):
    """Prima frase della voce (gemma4, prompt e tool veri) da sola, con un lavoro in corso
    senza arbitro, con l'arbitro."""
    from calliope.brain import Brain
    from calliope.config import Config
    from calliope.documenti.formato import FORMATI
    from calliope.tools.builtin import build_registry
    from calliope.tools.spec import ToolContext

    class SC:
        current_speaker, current_level, from_session, identified_by = None, "amministra", False, None

    vcfg = Config()                        # la voce: sempre l'Ollama locale
    reg = build_registry(documenti=FORMATI, schermi=True, agenti=True)

    def misura(etichetta):
        tempi = []
        for _ in range(giri):
            for q in DOMANDE_VOCE:
                b = Brain(vcfg, reg, ToolContext(cfg=vcfg, speakers=None, speaker_ctx=SC(),
                                                 speaker=None))
                svc.arbitro.voce_occupata()
                t0 = time.perf_counter()
                primo = None
                for pezzo in b.stream_reply(q, "amministra"):
                    if primo is None and pezzo.strip():
                        primo = time.perf_counter() - t0
                svc.arbitro.voce_libera()
                tempi.append(primo or 0.0)
                time.sleep(0.5)
        med = statistics.median(tempi)
        print(f"   {etichetta:38} prima frase mediana {med:.2f}s, massimo {max(tempi):.2f}s",
              flush=True)
        return {"scenario": etichetta, "mediana": round(med, 3), "massimo": round(max(tempi), 3),
                "tempi": [round(t, 3) for t in tempi]}

    out = [misura("voce da sola")]
    lungo = ("Scrivi un racconto per bambini di almeno 1500 parole su un drago che ha paura del "
             "buio, con un titolo e cinque capitoli.")
    for con_arbitro in (False, True):
        svc.arbitro.condiviso = svc.stesso and con_arbitro
        lav = svc.nuovo("altro", lungo, "banco", "Banco", "amministra")
        svc.avvia(lav)
        t0 = time.time()
        while lav.stato != "in_corso" and time.time() - t0 < 30:
            time.sleep(0.2)
        time.sleep(3.0)                    # che stia generando davvero
        out.append(misura("con un lavoro, " + ("con l'arbitro" if con_arbitro
                                                else "senza arbitro")))
        svc.annulla("banco")
        time.sleep(1.0)
    svc.arbitro.condiviso = svc.stesso
    return out


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Banco dei lavori degli agenti")
    ap.add_argument("--dgx", action="store_true")
    ap.add_argument("--url")
    ap.add_argument("--modello")
    ap.add_argument("--solo", action="append", choices=["codice", "documenti", "contesa"])
    ap.add_argument("--compiti", default="")
    ap.add_argument("--uscita")
    ap.add_argument("--passi", type=int)
    ap.add_argument("--minuti", type=float)
    ap.add_argument("--scrittore", help="modello dei documenti, sullo stesso server "
                    "dell'agente (vuoto: quello di dgx.yaml o l'agente)")
    ap.add_argument("--rivaluta", metavar="CARTELLA",
                    help="solo i criteri dei documenti sui JSON di un banco già fatto")
    args = ap.parse_args(argv)
    if args.rivaluta:
        return rivaluta(Path(args.rivaluta))
    parti = args.solo or ["codice", "documenti", "contesa"]
    scelti = {c.strip() for c in args.compiti.split(",") if c.strip()}
    uscita = Path(args.uscita) if args.uscita else Path(tempfile.mkdtemp(prefix="banco_lavori_"))
    uscita.mkdir(parents=True, exist_ok=True)
    cfg, imp, etichetta = prepara(args)
    svc = servizio(cfg, imp, uscita)
    print(f"Banco lavori: agente {imp.modello}, documenti {imp.modello_scrittore} ({etichetta}, "
          f"{svc.descrizione()}); risultati in {uscita}", flush=True)
    d = svc.verifica()
    if d["codice"] != "ok":
        print(f"L'agente non è raggiungibile: {d['motivo']}. {d['passo']}")
        svc.close()
        return 1
    riepilogo = {"agente": imp.modello, "scrittore": imp.modello_scrittore, "modo": etichetta, "data": datetime.datetime.now()
                 .isoformat(timespec="seconds"), "stesso_ollama": svc.stesso}
    t0 = time.time()
    try:
        if "codice" in parti:
            print("\n— codice (13 compiti: 12 con test nascosti, c13 deve chiedere)", flush=True)
            rc = banco_codice(svc, cfg, uscita, scelti)
            riepilogo["codice"] = rc
            if rc:
                print(f"codice: {sum(r['nascosti_fine'] for r in rc)}/{len(rc)} alla fine, "
                      f"{sum(r['nascosti_primo'] for r in rc)}/{len(rc)} al primo tentativo; "
                      f"minuti in tutto {sum(r['minuti'] for r in rc):.1f} (soglia ≥ 9/12 sui 12 con i test, e c13 deve chiedere)")
        if "documenti" in parti:
            print("\n— documenti (12 compiti, 3 su modelli)", flush=True)
            rd = banco_documenti(svc, cfg, uscita, scelti)
            riepilogo["documenti"] = rd
            if rd:
                print(f"documenti: {sum(r['ok'] for r in rd)}/{len(rd)} giusti; validi "
                      f"{sum(bool(r['valido']) for r in rd)}; minuti in tutto "
                      f"{sum(r['minuti'] for r in rd):.1f} (soglia ≥ 10/12). L'italiano va "
                      f"giudicato a mano sui file in {uscita / 'risultati'}.")
        if "contesa" in parti:
            print("\n— contesa (prima frase della voce)", flush=True)
            riepilogo["contesa"] = banco_contesa(svc, cfg)
            base = riepilogo["contesa"][0]["mediana"]
            arb = riepilogo["contesa"][-1]["mediana"]
            print(f"contesa: con l'arbitro {arb - base:+.2f}s sulla mediana (soglia ≤ +0,15 s)")
    finally:
        svc.close()
    riepilogo["minuti"] = round((time.time() - t0) / 60, 1)
    (uscita / "riepilogo.json").write_text(json.dumps(riepilogo, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    print(f"\nRiepilogo in {uscita / 'riepilogo.json'} ({riepilogo['minuti']} minuti)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
