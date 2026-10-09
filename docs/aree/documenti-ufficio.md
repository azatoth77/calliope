# Documenti, ufficio, archivio

*Documenti Word/Excel/PDF a voce, ufficio (modelli, rubrica, fatture, DDT), archivio dei documenti di casa. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

*Stato al 09/10: documenti, ufficio e archivio invariati nella sostanza dalla pubblicazione; dal 07/10 i testi dell'agente si consegnano in Markdown (sezione sotto) e il file offerto dopo una modifica ha il suo nome vero. Il contatto cercato in rubrica (`anagrafica_cerca`) rientra dall'08/10 nella misura delle parole incerte ([stt-tts](stt-tts.md)).*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Documenti Word, Excel, PDF | python-docx, openpyxl, fpdf2 (puro Python); il contenuto è JSON chiesto a Ollama con lo schema degli output strutturati | `calliope/documenti/` → `Documenti` (`servizio.py`), `Writer` (`scrittore.py`), `validate` (`formato.py`), `render` (`render.py`), `LocalDelivery` (`consegna.py`); tool in `calliope/tools/documenti.py` |
| Markdown dei testi dell'agente (07/10) | scritto in proprio (niente librerie), lo stesso sottoinsieme del lettore della pagina | `calliope/documenti/markdown.py` → `analizza`, `in_linea`, `per_voce`, `descrivi`, `a_blocchi` (verso `render` per PDF e Word), `da_blocchi` (MD di un documento a blocchi), `con_titolo`, `senza_recinto`, `sembra_markdown` |
| Archivio dei documenti di casa (bollette, contratti, polizze, garanzie, referti…) | cartella osservata; pypdfium2, Pillow, python-docx; OCR ed estrazione con il modello grande (qwen3.6 su vLLM, client degli agenti, output strutturati); grafo in SQLite (nodi e archi tipizzati con la fonte, alias, FTS5) | `calliope/archivio/` → `Archivio` (`servizio.py`: coda, permessi, interrogazioni), `Grafo` (`grafo.py`), `tipi.py` (schede, controllo contro il testo, `nel_grafo`), `testo.py` (`leggi`, `OcrVisivo`), `Estrattore`, `esplora.py` (strumenti dell'agente), `load_archivio`; tool in `calliope/tools/archivio.py`; terminale `python -m calliope.archivio` |
| Ufficio: modelli di documento, rubrica, numerazione, fatture e DDT | docxtpl (Word) e python-pptx (PowerPoint) per i modelli dell'utente con un `.yaml` di descrizione; SQLite (stesso file della memoria); `Decimal` per i conti; XML FatturaPA FPR12 1.2.3 con la libreria standard, XSD ufficiale con lxml se scaricato; PDF con i documenti | `calliope/ufficio/` → `Ufficio` (`servizio.py`), `modelli.py`, `Rubrica`, `Numeratore`, `conti.py`, `fatturapa.py`, `stampe.py`; tool `modello_compila`, `anagrafica_cerca`, `anagrafica_salva` in `calliope/tools/ufficio.py`; terminale `python -m calliope.ufficio`; vedi [`docs/ricerche/2026-10-03-template.md`](../ricerche/2026-10-03-template.md) |

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

- **Ufficio** (03/10, `calliope/ufficio/`, [`docs/ricerche/2026-10-03-template.md`](../ricerche/2026-10-03-template.md)):
  fatture elettroniche (PDF di cortesia + XML FPR12 da caricare a mano: Calliope non invia
  allo SdI), note di credito, preventivi, DDT e modelli Word/PowerPoint/JSON dell'utente
  (`ufficio_modelli`, predefinita Documenti/Calliope/Modelli), compilati a voce con
  `modello_compila`: estrazione dei campi con lo schema, domande sui dati mancanti, proposta
  «La preparo?» e numero assegnato solo al «sì» (turno dopo, stessa persona), conti del
  programma. Rubrica con `anagrafica_cerca`/`anagrafica_salva` (proposta e «sì»). Chi emette
  in `calliope.locale.yaml`, `fatture_emittente`; schema XSD con `python -m calliope.ufficio
  --scarica-xsd` (non in git: licenza non dichiarata). Fatture solo a chi amministra.

  - **Archivio dei documenti di casa** (03/10, `calliope/archivio/`, rapporto
    [`docs/ricerche/2026-10-03-documenti-grafo.md`](../ricerche/2026-10-03-documenti-grafo.md)):
    una cartella (`archivio_cartella`, sulla DGX) letta in secondo piano; OCR di scansioni e
    foto con il modello visivo (qwen3.6: sulle foto peggiori 29/30 valori chiave contro 17/30 di
    RapidOCR, nessuna libreria nativa nuova), scheda per tipo con gli output strutturati (100/102
    campi sui documenti finti; con «oggetto oppure null» l'emittente era sempre null, con il
    campo «nome» le persone avevano il solo nome di battesimo), ogni valore tenuto solo se è nel
    testo, date ricavate dal programma; grafo completo in SQLite (8 tipi di nodo, 11 relazioni,
    fonte su ogni arco, alias per la deduplicazione), rielaborato da solo a versione nuova senza
    rifare l'OCR. A voce `archivio_cerca`, `archivio_scadenze`, `archivio_somma` (frase pronta,
    somme del programma; 25/26 con gemma4, prima frase mediana 0,61 s), riservati: nel registro
    dei turni solo il nome del tool (dal 07/10 anche i nomi degli argomenti dati, senza i
    valori). Sensibili (referti, identità) solo all'interessato e a chi
    amministra, mai nella zona grigia né all'agente; cartella con il nome di un profilo =
    personale. L'agente esplora il grafo con sei strumenti chiusi (`grafo_*`) nelle ricerche
    delegate.

  - **Documenti a voce** (27/09, `calliope/documenti/`): lettere, tabelle ed elenchi in Word,
    Excel o PDF, creati e modificati a voce, salvati in Documenti\Calliope; «aprilo» li apre.

## Note dalla sezione «Problemi noti» di CLAUDE.md (fino al 06/10)

- **Documenti Word, Excel, PDF** (27/09, `calliope/documenti/`, `calliope/tools/documenti.py`,
  prove `prove/prova_documenti.py` e `prove/prova_documenti_ollama.py`):
  - Il modello chiama `documento_crea(formato, richiesta)` con i dati come detti; il testo lo
    scrive una **seconda richiesta a Ollama** (stesso modello e `num_ctx`, `format` = schema
    JSON, non in streaming), poi validazione, file e consegna. Negli argomenti del tool il
    testo sarebbe senza schema, senza nuovo tentativo e con la voce ferma.
  - Schema: un `anyOf` per tipo di blocco. Con uno schema piatto il modello metteva la
    tabella in markdown dentro «testo». Le celle sono testo **o numero**: con le sole
    stringhe gemma4, che voleva scrivere 800, apriva la stringa e ci metteva «},{». JSON
    compatto: con il rientro i token raddoppiano (lettera 447 contro 222). L'esempio
    «Importo (€)» nel prompt faceva scrivere «Importocosto (€)» anche senza schema: ora è
    «Spesa (€)». «Oggi è…» e il nome di chi chiede facevano aggiungere righe «Data:» e
    «Richiesto da:» a ogni documento: il prompt dice che servono solo alle lettere.
  - Controlli oltre allo schema: limiti di lunghezza, righe con più valori delle colonne,
    formule solo da un elenco (SUM, AVERAGE, MIN, MAX, COUNT, COUNTA, ROUND, IF, ABS,
    PRODUCT, AND, OR, NOT, anche all'italiana: SOMMA, `;`), riferimenti dentro la tabella,
    niente `!`, `[`, `|` (altri fogli, altri file, DDE). Il testo che comincia con + - @
    si scrive come testo puro (`data_type="s"`, `quotePrefix`): formula injection. Una
    lettera con meno di 4 paragrafi è incompleta (1 volta su 8 il modello si fermava al
    primo). Una modifica che perde più di metà del contenuto senza «togli»/«elimina» è
    rifiutata. Un solo nuovo tentativo con gli errori, poi «Non sono riuscita…».
  - Il **totale lo fa il programma**: `"totale": true` diventa `=SUM(B2:Bn)` in Excel e
    una somma in Word e PDF, e si ricalcola dopo «aggiungi una riga». Il modello conta male
    le righe dei riferimenti.
  - **Tempi** (gemma4:e4b-it-qat, ~65 token/s): tabella Excel 1,1–1,6 s, PDF con elenco
    0,8–1,1 s, lettera 2,9–3,8 s (210–260 token); modifiche: Excel 1,1–1,7 s, lettera
    2,9–4,1 s (il modello riscrive tutto il JSON). Prima frase del turno (tool, attesa del
    file, conferma): mediana 1,2–1,4 s, lettere ~3,5–4,7 s; «Subito.» (`announce`) copre
    l'attesa dopo ~0,5 s. Il tool aspetta `documenti_attesa_s` = 4 s: le lettere arrivano
    quasi sempre in una frase sola invece di tre («te la preparo», segnale, «è pronta»).
    Oltre, `risposta_finale` «Te la preparo…» e l'annuncio a file pronto
    (`Documenti.done` + `due_event`, come l'agenda, con `Speaker.chime`), che entra nella
    storia (`Brain.record_announcement`) così «sì, aprila» funziona.
  - **Ollama è uno solo**: una domanda fatta mentre genera un documento aspetta la fine
    della generazione. Misura: «che ore sono?» 0,25 s con Ollama libero, 2,9–3,3 s durante
    una lettera. È il problema dell'arbitro di
    [`docs/ricerche/2026-09-26-tool-e-agenti.md`](../ricerche/2026-09-26-tool-e-agenti.md):
    misurato, non risolto. *[Superato: arbitro dal 02/10 e pausa di vLLM dal 04/10, vedi [agenti-estensioni](agenti-estensioni.md).]* Per questo `risposta_finale` chiude il turno senza un'altra
    passata del modello: la conferma non aspetta Ollama.
  - Il modello scrive spesso la chiamata a `documento_crea` come testo (con argomenti
    lunghi): la esegue `TextCallGuard`. Il formato detto a voce («un PDF») vince su quello
    passato dal modello.
  - File: nome dal titolo ripulito (niente `\ / : * ? " < > |`, nomi riservati), mai
    sovrascritto («Nome (2)»), scritto con file temporaneo e `os.replace`. La modifica
    riscrive lo stesso file (una sola copia in Documenti), e la versione precedente del
    JSON resta in `documenti_versioni`; ma se il file è stato **cambiato a mano** (data di
    modifica diversa) o è **aperto in Word** (`PermissionError`) la nuova versione va in
    «Nome (2)» e Calliope lo dice. Cartella: known folder `FOLDERID_Documents` via ctypes
    (segue OneDrive) + «Calliope». JSON in `memoria.db` (tabella `documenti`), per persona.
  - «Aprilo»: il file appena scritto diventa l'«ultima ricerca» della persona nel
    `PCExecutor` (`offri_file`), segnata come sua: `pc_apri_file(1)` lo apre anche a chi non
    è proprietario del PC, mentre ricerche e altri file restano del proprietario. Senza PC
    il documento si crea uguale e la conferma non chiede «lo apro?».
  - PDF: fpdf2 con un font TrueType di sistema (`documenti_font`, primo trovato: Arial su
    Windows) per «€», accenti e virgolette; senza, Helvetica con «EUR».
  - Con i tool nuovi le prove esistenti restano uguali: `prova_pc_ollama` 62/62,
    `prova_casa` 42/42 (prima frase mediana 0,45 e 0,51 s). `prova_documenti_ollama` 17/17.
  - Backend `openai`: lo scrittore usa `response_format` di tipo `json_schema` su `/v1`
    (provato; lì Ollama ricarica il modello a 4096 token).

- **Ufficio a voce** (03/10, `prova_ufficio_ollama` 27/30 in 2 giri, estrazione dei campi
  ~2,2 s): senza «chiamalo subito, senza chiedere i dati» nella descrizione gemma4 chiedeva
  partita IVA e indirizzi invece di chiamare `modello_compila`; la stessa frase nel prompt
  faceva chiedere dettagli anche alle lettere (il prompt dice che le lettere restano a
  `documento_crea` «anche se mancano dei dettagli»). Il «sì» chiama il tool solo se l'azione in
  sospeso ha tutti gli argomenti obbligatori. `ACTION_CLAIM` ora prende anche «ho
  preparato/emesso» e il passivo («è stata preparata»). Restano: «Prepara una fattura.» senza
  dati → il modello chiede da sé, e la risposta dopo a volte non chiama il tool.

## Markdown per i testi dell'agente (07/10)

Decisione di Dario del 07/10: **ricerche, relazioni e riassunti dell'agente si consegnano in
Markdown** (`risultato.md`: titoli, sezioni, elenchi, tabelle). Il formato a blocchi di
`formato.py` resta per lettere, fatture, modelli e per la conversione. Prima la ricerca
diventava un Word di soli paragrafi (i titoli delle sezioni persi, nessuna tabella) e gli altri
lavori un `.txt`.

- **`calliope/documenti/markdown.py`**, senza librerie (principio 4): un sottoinsieme uguale a
  quello del lettore della pagina (`schermo.js`, `leggiMarkdown`): titoli `#`…`######` e
  sottolineati, paragrafi, elenchi puntati e numerati con i rientri, tabelle con la riga dei
  trattini (e `\|` nelle celle), codice tra ``` o ~~~, citazioni, righe; nelle righe grassetto,
  corsivo, barrato, codice, collegamenti (testo, con l'indirizzo tra parentesi nei file e senza a
  voce), immagini come «[immagine: …]». Niente HTML: un tag resta testo.
- **Limiti contro i testi ostili** (il testo dell'agente non è fidato): 200 000 caratteri,
  2000 blocchi, 500 righe e 20 colonne per tabella, 6 livelli di rientro, 4 citazioni
  annidate; caratteri di controllo e di direzione del testo tolti; grassetto e corsivo al più
  di 400 caratteri su una riga e indirizzi al più di 600 (con `.+?` senza limiti «*a »
  ripetuto 60 000 volte costava minuti: tempo quadratico). Misura: 11 testi ostili, ognuno
  analizzato, detto e convertito in meno di 3 s (`prova_markdown.py`).
- **Conversione** (`a_blocchi`): titoli → `titolo`, paragrafi, elenchi (i livelli annidati con
  «– » davanti), tabelle (al più 12 colonne: le altre unite nell'ultima; oltre 200 righe in più
  tabelle), codice e citazioni come paragrafi; poi `render` com'è (fpdf2, python-docx), senza
  i limiti di un documento detto a voce (`validate` non serve: un rapporto è più lungo).
  `da_blocchi` fa il contrario per «Scarica» in MD di una lettera o di un foglio (il testo resta
  testo: `#`, `*`, `|` con la barra).
- **`render_docx` era quadratico sulle tabelle**: `table.cell(r, c)` ricostruisce la griglia a
  ogni chiamata; una tabella di 200 righe × 12 colonne superava il minuto, ora 0,2 s (le celle
  riga per riga, `table.rows[r].cells`).
- **Voce**: il Markdown si toglie prima di Piper con le funzioni di pulizia che c'erano:
  `agenti/ciclo.per_la_voce` e `agenti/risultato.per_voce` passano da `markdown.per_voce` se il
  testo sembra Markdown (`sembra_markdown`), e il codice tra apici resta riconoscibile per
  essere scartato come prima.
- **Conversioni a richiesta** («fammene un PDF», «lo voglio in Word»): `risultato_lavoro` con
  `modo` pdf o word *[dall'08/10 il tool si chiama `lavoro_risultato`; il vecchio nome resta valido nel registro]* (`agenti/risultato.converti`, area agenti-estensioni) e «Scarica» nella
  scheda (`schermi/scarica.py`, area schermi-telefono).

## Il nome del file offerto dopo una modifica (07/10 sera, ramo `correzioni-giro9`)

`Documenti._offer` (`documenti/servizio.py`) offre al PC il file con il suo nome vero (lo stem di `nome_file`): dopo
una modifica salvata come «Titolo (2)» perché l'originale era aperto, «Apro Titolo (2).»; il
`cosa_fare` di `documento_modifica` dice che il risultato 1 è la versione nuova e che il numero
tra parentesi del nome non è il risultato (caso vero della DGX: il modello chiamava
`pc_apri_file(2)`). Il resto in [pc](pc.md) e [sicurezza-politica](sicurezza-politica.md).
