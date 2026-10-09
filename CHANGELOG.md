# Cambiamenti

La storia pubblica del repository parte da un solo commit (la prima pubblicazione): la storia
di sviluppo precedente non è pubblica. Qui le tappe principali, per data; i dettagli, con le
misure, sono nei documenti d'area ([`docs/aree/`](docs/aree/)) e nelle ricerche
([`docs/ricerche/`](docs/ricerche/)).

## 0.3 — prima pubblicazione (07/10/2026)

- Codice sotto licenza AGPL-3.0-or-later; README tecnico, procedura d'installazione
  ([`docs/installazione.md`](docs/installazione.md)), componenti di terzi, politica di sicurezza.
- Nessun dato personale nel repository: nomi e indirizzi di fantasia nelle prove e nei
  documenti, documenti privati fuori da git, una prova nell'hook (`prova_dati_privati`).

## Tappe dello sviluppo

| Data | Tappa |
|---|---|
| 21/09/2026 | Progettazione; primo test a voce completo (Whisper, LLM su Ollama, Piper); confronto dei modelli: gemma4 e4b e Whisper large-v3-turbo |
| 22–24/09 | Tool calling nativo, riconoscimento di chi parla (CAM++), wake word acustica dedicata, taratura di Whisper, registro dei turni |
| 26/09 | Package `calliope/` e `calliope.yaml`; prove automatiche e hook; barge-in con il nome; memoria per persona; timer e promemoria; liste; biblioteca offline; PC a voce |
| 27/09 | Documenti Word, Excel, PDF a voce |
| 01/10 | Casa con Home Assistant; registro delle capacità e installazioni a voce dal catalogo; biblioteca senza libzim (lettore ZIM in puro Python, indice FTS5); regole sul testo ristrette ai casi stretti |
| 02/10 | Installazione e aggiornamento su Linux (DGX Spark, uv, systemd, ritorno automatico); Whisper su whisper.cpp; satelliti; schermi; agenti in secondo piano su vLLM |
| 03/10 | Telefono come satellite (PWA); esecutore del PC sul satellite; archivio dei documenti di casa con OCR e grafo; ricerca web con SearXNG; ufficio e FatturaPA; scrivere invece di parlare; sandbox Docker; analisi di sicurezza e correzioni |
| 04/10 | Estensioni permanenti con guardrail e porta stretta; personalità e modalità Star Trek; conferme e frase di sfida; arbitro e pausa di vLLM; programmi in diretta e C# |
| 05/10 | Finestra di contesto dal setup, compressione e archivio delle conversazioni; minori e guardiano; foto e allegati; politica unica dei tool con la provenienza dei dati; giochi sugli schermi |
| 06/10 | Una conversazione per persona con più satelliti; analisi complessive e correzioni (latenza, ciclo come classe, hook a livelli); cruscotto di chi amministra; prova end-to-end |
| 07/10 | Confronto delle varianti di trascrizione (si resta senza correzione); preparazione della pubblicazione |
| 07/10 (dopo la pubblicazione) | Età e compleanni dai profili; voci di famiglia al telefono (margine tra i profili, «chi parla?» solo per un'azione); risultato dei lavori a voce e sullo schermo; testi dell'agente in Markdown con «Scarica»; dal testo alla voce: prima frase a pezzi, taratura di Piper all'avvio e con l'uso, Piper sulla GPU; misura delle pause; correzioni dai giri veri (turno dopo un annuncio, esito dopo la sfida, documento proprio con una foto di mezzo); ricerche sulla taratura secondo la macchina e sulla sicurezza per valore |
| 08/10 | Fine del congelamento delle funzionalità nuove; sicurezza per valore, fasi 1–3 (attrito, memoria dell'intento, matrice in ombra); taratura della macchina (inventario, catalogo, `calliope stato --piano`); cassetto dei file per persona (anche il tutore sui file del figlio); esercizi generati (matematica, italiano); versioni, modifica e approvazione delle estensioni a voce; modalità sviluppo a fasi e la sua versione 2 (nomi nuovi dei tool `lavoro_*` e `sviluppo_*`, domande all'agente, tappe ai limiti); giri 3 e 4 dai casi veri (traccia di rete nel collaudo, URL non codificati rifiutati, modifica e rinomina delle estensioni, collaudo con più input); vista dello sviluppo sugli schermi (schermo intero, due colonne, testo dell'agente come chat in sola lettura); la prova del telefono nel browser non si salta più |
| 08/10 (sera) | Modalità sviluppo, giri 5 e 6 (avviso di doppia codifica, giro a vuoto dell'agente fermato; «ferma» che ferma il lavoro dell'agente e «sospendi» che lo lascia finire, «rifallo» che riparte con la stessa specifica, un collaudo per ogni valore detto insieme); confronto tra collaudi riusciti e falliti e risposte vere come esempi per i test dell'agente; casa: il dispositivo trovato per nome quando Home Assistant non lo trova nella stanza detta, con il consiglio a chi amministra; cronologia delle schede per persona e scheda «Conversazione»; ricerca cronologica nelle conversazioni («più indietro»), frasi cortissime riconosciute per continuità sullo stesso satellite, niente spiegazioni inventate su sé stessa; analisi delle frasi pronte dei tool, delle parole incerte di Whisper e delle sonde dell'agente |
| 08/10 (notte) | Modalità sviluppo: ricollaudo della versione consegnata con i casi della persona prima di «è pronto», sonde dell'agente solo verso host noti e con i valori del caso, testo dei siti in busta per l'agente; nomi pubblici di casa vietati nella rete delle estensioni; nomi capiti male negli argomenti dei tool: probabilità di Whisper e nome noto più vicino nel registro dei turni; dopo un esito vuoto «forse intendevi…?» con la proposta in sospeso, o «me lo ripeti o scrivi?» |
| 09/10 | Un «no» alla proposta la chiude e Calliope non la ripropone finché non le si chiede di nuovo; «Sì, però ascolta…» non vale più come consenso. Minori: un segnale di pericolo poco chiaro (una parola, un saluto, la voce incerta) passa da due cancelli, prima una frase che rassicura e chiede, poi l'avviso al tutore solo se la risposta conferma (o un avviso non urgente se tace); avvisi «sicurezza» non a voce vicino al minore. Analisi di quando parlano più persone e «modalità compagnia»: con una voce sconosciuta vicino allo stesso satellite Calliope vuole il nome a ogni frase e lo schermo lo dice; in compagnia niente frase breve né continuità, azioni solo con la voce nella frase, l'avviso dei minori dice che c'erano altre voci; giudizio «la frase è rivolta a me?» in ombra. Dialogo tra tool e modelli: argomenti controllati contro lo schema, errori in parole con esempio e «cosa fare», giro di correzione quando il modello dice «riprovo» senza richiamare il tool; stessa forma per gli strumenti dell'agente |
