"""Dati del banco delle richieste di lavoro (06/10, analisi della richiesta prima di partire,
calliope/agenti/richiesta.py). Etichette proposte e corrette da Dario il 06/10: chiara,
raffinabile, vaga, gia_fatto («c'è già»), impossibile («impossibile qui»); E11 è chiara solo se
la verifica rapida trova una fonte pubblica, altrimenti vaga (`chiara_o_vaga`). I casi veri: E1
(06/10, L1 della DGX), E2 (05/10), E3, C1 (04/10), C2 (04/10). Solo nomi e dati di fantasia.
Li usa prove/misura_analisi_richiesta.py.

Ogni caso: (id, tipo, richiesta, contesto [(ruolo, testo)], etichetta, nota)."""

E, C = "estensione", "codice"

CASI = [
    # ── estensioni ──
    ("E1", E, "Creami un'estensione che mi fa una ricerca sulle città di una regione "
              "prendendole da Wikipedia", [], "vaga",
     "quali città (comuni, capoluoghi, sopra quanti abitanti), cosa dire, quale pagina"),
    ("E2", E, "Leggi la tabella delle regioni da Wikipedia e dimmi capoluogo e abitanti", [],
     "chiara", ""),
    ("E3", E, "Fammi un'estensione che converte i gradi Celsius", [], "chiara", ""),
    ("E4", E, "Fammi un'estensione che mi dice che tempo farà domani",
     [("user", "Sono appena tornata a Borgo Fantasia"),
      ("assistant", "Ben tornata a casa!")], "raffinabile",
     "il meteo di domani per Borgo Fantasia da un servizio pubblico"),
    ("E5", E, "Fammi un'estensione che mi dice quando passa il prossimo autobus", [], "vaga",
     "linea, fermata, azienda e orari pubblici"),
    ("E6", E, "Un'estensione che tira un dado da venti facce", [], "chiara", ""),
    ("E7", E, "Fammi un'estensione che mi dice il cambio euro dollaro", [], "chiara",
     "fonte BCE, verificata dall'analizzatore"),
    ("E8", E, "Fammi un'estensione per la lista della spesa condivisa", [], "gia_fatto",
     "le liste ci sono già"),
    ("E9", E, "Fammi un'estensione che mi legge le notizie", [], "vaga",
     "quale testata o feed, quante, che argomento"),
    ("E10", E, "Un'estensione che mi dice il prezzo della benzina", [], "vaga",
     "dove, self o servito, fonte"),
    ("E11", E, "Un'estensione che dato il CAP mi dice il comune", [], "chiara_o_vaga",
     "chiara solo con una fonte pubblica verificata"),
    ("E12", E, "Allora fammi un'estensione che lo sappia fare",
     [("user", "Quanti abitanti ha Valfiorita?"),
      ("assistant", "Non lo so, non ho una fonte per questo.")], "raffinabile",
     "abitanti di un comune dalla sua voce di Wikipedia"),
    ("E13", E, "Fanne una uguale per le province",
     [("user", "Usa l'estensione regioni d'Italia: dimmi capoluogo e abitanti della Toscana"),
      ("assistant", "La Toscana ha come capoluogo Firenze e 3 657 716 abitanti, dalla tabella "
                    "delle regioni di Wikipedia.")], "raffinabile",
     "dalla tabella delle province di Wikipedia, capoluogo, regione e abitanti"),
    ("E14", E, "Fammi un'estensione che mi avvisa quando c'è un'offerta", [], "vaga",
     "offerta di cosa, dove; niente orari fissi"),
    ("E15", E, "Un'estensione che mi dice quanti giorni mancano a una data", [], "gia_fatto",
     "data_calcola"),
    # ── codice ──
    ("C1", C, "Calcolami il rimborso con la tariffa al chilometro che usa la mia azienda", [],
     "vaga", "la tariffa dell'azienda, i chilometri"),
    ("C2", C, "Scrivi un software in C# che fa un calcolo, inventa gli input casuali e mostrami "
              "input e output", [], "chiara", ""),
    ("C3", C, "Scrivi un programma che ordina un file CSV", [], "vaga",
     "quale file, quale colonna"),
    ("C4", C, "Fammi un programma che mi somma le spese per voce",
     [("user", "Ti ho mandato il file spese_settembre.csv dal telefono, ha le colonne data, "
               "voce e importo"),
      ("assistant", "Ho ricevuto spese_settembre.csv.")], "raffinabile",
     "spese_settembre.csv, totale per voce"),
    ("C5", C, "Scrivi un programma in Python che trova i numeri primi fino a mille", [],
     "chiara", ""),
    ("C6", C, "Fammi un programma per la contabilità di casa", [], "vaga",
     "da dove arrivano i dati, cosa deve fare"),
    ("C7", C, "Scrivi una funzione che controlla se un IBAN italiano è valido", [], "chiara", ""),
    ("C8", C, "Calcolami lo stipendio netto di Luca", [], "vaga",
     "lordo, contratto, regione e comune, carichi di famiglia"),
    ("C9", C, "Scrivimi un programma che mi fa il piano di ammortamento",
     [("user", "Il mutuo è di 120 000 euro a 20 anni al 3,1 % fisso"),
      ("assistant", "Va bene, 120 000 euro a 20 anni al 3,1 %.")], "raffinabile",
     "120 000 euro, 20 anni, 3,1 % fisso"),
    ("C10", C, "Un programma che converte i numeri romani in arabi e viceversa", [], "chiara", ""),
    ("C11", C, "Fammi un programma che legge i dati del mio inverter", [], "impossibile",
     "la sandbox non raggiunge la rete di casa"),
    ("C12", C, "Scrivi in C# un programma che lancia due dadi mille volte e mostra quante volte "
               "esce ogni somma", [], "chiara", ""),
    ("C13", C, "Fai un programma che estrae a sorte chi porta i dolci ogni venerdì del mese",
     [("user", "In ufficio siamo io, Ottavia, Bruno, Carla e Dino"),
      ("assistant", "Siete in cinque, allora.")], "raffinabile",
     "Giulia, Ottavia, Bruno, Carla, Dino; i venerdì del mese"),
    ("C14", C, "Scrivimi un programma che calcola l'IMU della casa", [], "vaga",
     "rendita catastale, comune, abitazione principale"),
    ("C15", C, "Fammi lo script per il backup", [], "impossibile",
     "la sandbox non tocca i file del PC"),
    ("C16", C, "Scrivi un programma che genera password di sedici caratteri", [], "chiara", ""),
]

# Fuori ambito: l'analizzatore non è chiamato (delega_lavoro di tipo ricerca o documento)
FUORI = [
    ("F1", "ricerca", "Cercami le differenze tra pompa di calore e caldaia a condensazione"),
    ("F2", "documento", "Scrivimi una lettera all'amministratore del condominio per il rumore "
                        "del cantiere"),
]
