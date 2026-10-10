# 0027. La conversazione come registro degli eventi

- **Stato**: **proposta** (10/10/2026)
- **Area**: [voce-e-regole](../aree/voce-e-regole.md), [contesto-conversazione](../aree/contesto-conversazione.md)

## Contesto

Le parole di Calliope hanno oggi tre copie con vite diverse: la storia del modello, mantenuta a mano
da Brain con una trentina di punti che aggiungono, tolgono e riscrivono messaggi; il registro dei
turni; ciò che va alla voce, da 48 chiamate sparse nel ciclo più lo stream del modello. Di quelle 48,
26 sono parole sentite in una conversazione viva che il modello non vede (annunci dell'agenda, avvisi,
registrazione della voce, «chi parla?»…), e in sei meccanismi la storia dice altro da ciò che si è
sentito (per esempio «Va bene, mi fermo» scritto dopo uno stop che non ha detto niente). Le domande
del codice diventano una proposta solo se il testo finisce con «?»: il 10/10 alle 07:17 la stessa
domanda sulla chiusura di uno sviluppo è tornata sei volte, e il modello non sapeva che cosa avesse
chiesto. Il passo 1-bis della macchina a stati ([0022](0022-macchina-a-stati-del-dialogo.md),
«una voce sola») aveva due strade: incrementale o registro degli eventi.

## Decisione

Dario, 10/10: la **versione forte**, senza la versione intermedia.

- **Un registro degli eventi per conversazione** (per persona o per corsia, come le conversazioni di
  oggi), in sola aggiunta: detto dalla persona, detto da Calliope frase per frase (autore: contenuto
  del modello, atto di dialogo, esito di un tool; interruzione), chiamate ed esiti dei tool, proposte
  aperte e chiuse con il motivo, compressioni, chiusure. Nessun registro globale.
- **Tutto il resto è una proiezione**, funzione pura degli eventi: il contesto del modello (con la
  garanzia che l'ultimo messaggio dell'assistente è ciò che la persona ha sentito, frasi d'attesa
  escluse), lo stato della macchina, il registro dei turni (indice globale), l'archivio e la scheda
  «Conversazione», la risposta scritta.
- **Un'uscita unica verso la voce**, che scrive l'evento e manda la frase al TTS; lo streaming frase
  per frase resta, e nessuna scrittura su disco sta nel percorso della prima frase.
- **Le domande sono oggetti**: una frase pronta non chiede; la macchina rende la domanda in fondo e
  apre la proposta quando la domanda è stata sentita.
- **Visibilità decisa alla scrittura** per ogni evento (modello, turno, schermo, registro, mai), e
  porte esplicite per ciò che attraversa le conversazioni (annunci a una persona, avvisi ai tutori,
  coda della conversazione, archivio).
- Ogni costo ha una **guardia misurabile** in `calliope stato` (dimentica vera, tempo di costruzione
  del contesto, crescita, cache del prefisso, tipi senza proiezione).

## Alternative considerate

- **Incrementale** (uscita unica che aggiunge alla storia; Brain continua a mantenerla): ~1 giorno,
  ma lascia tre copie e i punti che modificano la storia; scartata.
- **Solo il modello parla**: coerenza senza atti, ma +1 s circa sui turni con una frase pronta, e i
  testi che devono essere fissi (protezione dei minori, sfida, politica) non lo sarebbero; scartata.
- **Un registro globale** o una libreria di event sourcing: isolamento fra persone da ricostruire con
  filtri, dipendenze in più; scartati.

## Conseguenze

- Sei passi con l'interruttore `eventi: spento | ombra | attivo`; il primo scrive gli eventi accanto
  alla storia di oggi e confronta. Stima 4–5 giorni.
- Il passo 3 e il passo 5 della macchina a stati si semplificano (la proposta nasce quando la domanda
  è sentita; la conversazione di una persona è il suo flusso), il passo 6 è assorbito.
- Rischi dichiarati: un difetto del filtro della proiezione è una fuga (visibilità alla scrittura,
  banco d'attacco rigiocato sul registro); compressione e corsie in parallelo (lock e `seq` per
  conversazione); backend OpenAI (stessi messaggi di oggi); crescita del disco (rotazione nell'archivio).

## Fonti

- [`2026-10-10-registro-eventi.md`](../ricerche/2026-10-10-registro-eventi.md)
- [`2026-10-10-macchina-stati.md`](../ricerche/2026-10-10-macchina-stati.md) § 10
