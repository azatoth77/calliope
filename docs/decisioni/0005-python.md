# 0005. Python come linguaggio di Calliope

- **Stato**: accettata (21/09/2026); riconfermata il 10/10/2026 dopo una valutazione di C#/.NET con
  Microsoft Agent Framework
- **Principi**: 2 e 4 di [`CLAUDE.md`](../../CLAUDE.md)

## Contesto

Calliope è scritta in Python dal primo prototipo (21/09). Il 10/10 chi amministra ha chiesto, come
esercizio, quanto codice si sarebbe risparmiato scrivendola in C# con **Microsoft Agent Framework**
(l'evoluzione di Semantic Kernel e AutoGen), e se Python reggerà su Windows su ARM, l'obiettivo
futuro (PC con RTX Spark), o su un PC di casa più accessibile della DGX. .NET ha un runtime nativo
per ARM64, un ottimo supporto a Windows e un sistema di tipi più rigido.

Il codice, al 10/10: circa 100.000 righe in `calliope/` (commenti compresi), 6.000 di JavaScript
per le pagine e 91.000 di prove. La parte grossa è logica nostra:

| Parte | Righe |
|---|---|
| Strumenti (`tools/`) | 11.500 |
| Agenti, sviluppo, sandbox (`agenti/`, `sviluppo.py`) | 12.500 |
| Satelliti, schermi, telefono | 12.500 |
| Estensioni, porta, sonde | 4.600 |
| Brain (ciclo del modello, spinte, reti) | 4.800 |
| Politica, valore, provenienza | 3.000 |
| Ciclo della voce | 3.100 |
| Casa, web, documenti, ufficio, archivio, PC, esercizi | 17.700 |

## Decisione

Calliope resta in Python. Il risparmio di codice è piccolo, e ciò che rende Calliope quello che è
resterebbe da scrivere comunque, e in parte **contro** il framework. Per i problemi veri che una
riscrittura risolverebbe (ARM, distribuzione dei satelliti) ci sono risposte più piccole.

### Cosa darebbe un framework per agenti in C#

Agent Framework gestisce bene il **giro conversazionale standard**:

- il ciclo degli strumenti già pronto: chiama il modello, esegue gli strumenti, rimanda il
  risultato; gli strumenti si registrano con un attributo sul metodo e lo schema JSON si genera dal
  tipo;
- i connettori per i modelli (OpenAI, Ollama), la storia della chat, lo streaming;
- i filtri prima e dopo ogni chiamata, che sarebbero il posto naturale per agganciare la politica;
- i flussi tra più agenti (il passaggio voce ↔ agente, le domande a metà lavoro).

Sostituirebbe il ciclo base di `brain.py`, la parte generica di `tools/spec.py` e
`tools/registry.py`, la traduzione verso l'API OpenAI e il ciclo dell'agente in `agenti/ciclo.py`:
circa **5.000–8.000 righe, il 5–8 % del totale**.

### Cosa resterebbe da scrivere comunque, e dove si andrebbe contro il framework

- **La logica che fa Calliope è quasi tutta specifica**: politica per valore e provenienza dei
  dati, conferme e frase di sfida, spinte e reti, frase per frase verso la voce, cancelli dei
  minori, compagnia, chi parla, modalità sviluppo, ricollaudo e sonde, la futura macchina a stati del
  dialogo. Nessun framework la fa: si riscriverebbe uguale, e in C# un po' più lunga per via dei
  tipi.
- **Il giro di Calliope non è il giro standard.** Trattiene una frase già generata, rimanda il
  modello allo strumento giusto, fa i giri di correzione degli errori strutturati
  ([0018](0018-errori-dei-tool-strutturati.md)), manda al TTS lo streaming a pezzi, tiene fuori
  dalla storia gli scambi tecnici, decide la politica per argomento e non solo per strumento. Un
  framework ha un suo ciclo: per ognuno di questi comportamenti si dovrebbe **girare attorno** al
  framework invece di usarlo. Oggi ogni passaggio è nostro e controllabile.
- **La voce** (VAD, wake word, Whisper, Piper, CAM++) vive soprattutto in Python. In C# ci sono
  onnxruntime e Whisper.net, ma faster-whisper, l'addestramento della wake word di openWakeWord e
  Piper andrebbero adattati o chiamati come processi esterni: più codice di raccordo, non meno.

### Dove C# sarebbe stato davvero meglio

- **Windows su ARM**: .NET gira nativo e bene; in Python alcune dipendenze native sono il rischio
  principale per il PC futuro.
- **Tipi statici**: una parte dei bug di questi giorni («argomento sbagliato», «campo mancante»,
  «None dove non te l'aspetti») l'avrebbe presa il compilatore.
- **Server e documenti**: Kestrel e ASP.NET per satelliti, schermi e SSE; OpenXML SDK per Word ed
  Excel e la FatturaPA in XML.
- **Un solo eseguibile da distribuire**, utile per i satelliti.

### In sintesi

- **Codice**: circa pari. Forse il 5 % in meno di codice generico, compensato da più raccordi per la
  voce e da un linguaggio più prolisso.
- **Guadagni di C#**: robustezza dei tipi, ARM, distribuzione.
- **Perdite**: l'ecosistema della voce e dei modelli, e la velocità con cui si provano idee nuove sui
  casi veri, che è stata la forza principale del progetto.

## Python su Windows su ARM e su un PC di casa

Il rischio non è che Python sparisca da Windows ARM, ma che alcuni pezzi nativi arrivino in ritardo.
I PC ARM hanno già portato Python ufficiale ARM64 (dalla 3.11), numpy e gran parte delle librerie
scientifiche, onnxruntime e un'anteprima di PyTorch. Il punto più incerto è CUDA su Windows ARM, che
dipende da NVIDIA. Pezzo per pezzo, grazie ai moduli sostituibili ([0003](0003-moduli-sostituibili.md)):

| Pezzo | Oggi | Su Windows ARM |
|---|---|---|
| LLM | Ollama | Ollama ha già la versione ARM64 per Windows |
| Trascrizione | faster-whisper sul portatile, whisper.cpp sulla DGX | faster-whisper (CTranslate2) non ha pacchetti ARM; whisper.cpp, già usato sulla DGX, si compila su ARM |
| Voce (Piper), VAD, wake word, chi parla | modelli ONNX | onnxruntime per ARM64 c'è |
| Audio, Word ed Excel, server web | librerie Python comuni | quasi tutte disponibili, qualcuna da compilare |
| Agenti con Docker | sandbox Linux | su Windows il codice dell'agente non si esegue già oggi, ARM o no |

Nel caso peggiore il costo è di **qualche giorno** (compilare due o tre pacchetti, scegliere i backend
nella configurazione, misurare), non una riscrittura. Una riscrittura in C# per lo stesso motivo
costerebbe mesi.

Il cervello su un PC di casa con una RTX da 8 GB è lo scenario della taratura secondo la macchina
(`calliope stato --piano`): la voce (gemma4 e4b più Whisper) ci sta, l'agente da 35B no (agente
piccolo, su un'altra macchina, oppure spento); il resto gira uguale. È una questione di modelli, non
di linguaggio.

## Alternative considerate

- **Riscrittura in C#/.NET con Agent Framework**: scartata, per le ragioni sopra.
- **Satellite nativo in C#** (audio, wake word, schermo) per i PC dove Python dà fastidio, con il
  cervello in Python: resta un'opzione, non una necessità. Il protocollo dei satelliti è un
  WebSocket con messaggi JSON e audio PCM ([satelliti](../aree/satelliti.md)), quindi il satellite si
  può riscrivere in qualunque linguaggio senza toccare il server.
- **C# dentro la sandbox dell'agente**: è già possibile e non c'entra con questa decisione (i
  programmi scritti dall'agente possono essere in C#, [agenti-estensioni](../aree/agenti-estensioni.md)).

## Conseguenze

- I limiti del linguaggio si compensano con prove, tipi e struttura: dataclass, prove a livelli
  nell'hook ([prove/LEGGIMI.md](../../prove/LEGGIMI.md)), una prova che controlla i nomi citati nei
  documenti d'area.
- Su Windows ARM resta da misurare la pipeline Python vera (problema aperto); il profilo da 8 GB è
  in coda nella [roadmap](../roadmap.md).

## Fonti

- Valutazione del 10/10/2026 con chi amministra (conversazione di progetto non pubblicata; il
  ragionamento è riportato qui per intero)
- [`2026-10-01-biblioteca-senza-libzim.md`](../ricerche/2026-10-01-biblioteca-senza-libzim.md),
  [`2026-10-02-satellite.md`](../ricerche/2026-10-02-satellite.md)
