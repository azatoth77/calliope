# 0005. Python come linguaggio di Calliope

- **Stato**: accettata (21/09/2026); riconfermata il 10/10/2026 dopo una valutazione di C#/.NET
- **Principi**: 2 e 4 di [`CLAUDE.md`](../../CLAUDE.md)

## Contesto

Calliope è scritta in Python dal primo prototipo (21/09). Il 10/10, guardando a Windows su ARM e
alla dimensione del codice, ci si è chiesti se convenisse riscriverla in C#/.NET: .NET ha un
runtime nativo per ARM64, un buon supporto a Windows e un sistema di tipi più rigido. La
valutazione è stata fatta in una conversazione di progetto (non pubblicata); qui ne resta il
ragionamento.

## Decisione

Calliope resta in Python. Per i problemi che una riscrittura dovrebbe risolvere ci sono risposte
più piccole:

- **ARM**: i moduli sostituibili ([0003](0003-moduli-sostituibili.md)) già isolano le librerie
  native; dove una libreria non gira si cambia quel modulo (come per libzim e faster-whisper).
- **Satellite nativo come opzione**: se un giorno il satellite su un PC Windows ARM o su un
  dispositivo piccolo avesse bisogno di un programma nativo, il protocollo è un WebSocket con
  messaggi JSON e audio PCM ([satelliti](../aree/satelliti.md)): si può riscrivere solo il
  satellite, in qualunque linguaggio, senza toccare il server.

## Alternative considerate

- **Riscrittura in C#/.NET**: scartata.
  - Il **risparmio di codice** sarebbe piccolo: la gran parte del codice è logica di dialogo,
    politica e integrazione, che resterebbe della stessa dimensione in un altro linguaggio.
  - L'**ecosistema della voce** è in Python: faster-whisper, Piper, Silero, openWakeWord, i
    client di Ollama e vLLM, le librerie per i documenti (docxtpl, python-pptx), gli strumenti di
    addestramento della wake word. In .NET molte di queste andrebbero chiamate via ONNX o
    riscritte.
  - Una riscrittura fermerebbe per settimane un progetto che cambia ogni giorno sui casi veri.
- **C# dentro la sandbox dell'agente**: è già possibile e non c'entra con questa decisione (i
  programmi scritti dall'agente possono essere in C#, [agenti-estensioni](../aree/agenti-estensioni.md)).

## Conseguenze

- Le prove, i tipi e la struttura compensano i limiti del linguaggio: dataclass, prove a livelli
  nell'hook ([prove/LEGGIMI.md](../../prove/LEGGIMI.md)), una prova che controlla i nomi citati
  nei documenti d'area.
- Su Windows ARM resta da misurare la pipeline Python vera (problema aperto).

## Fonti

- Valutazione del 10/10/2026 con chi amministra (non pubblicata)
- [`2026-10-01-biblioteca-senza-libzim.md`](../ricerche/2026-10-01-biblioteca-senza-libzim.md),
  [`2026-10-02-satellite.md`](../ricerche/2026-10-02-satellite.md)
