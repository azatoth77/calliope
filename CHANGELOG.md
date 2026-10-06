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
