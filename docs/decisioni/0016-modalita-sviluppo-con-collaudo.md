# 0016. Modalità sviluppo a fasi, con il collaudo prima dell'approvazione

- **Stato**: accettata (08/10/2026); sei giri di correzioni sui casi veri lo stesso giorno
- **Area**: [agenti-estensioni](../aree/agenti-estensioni.md), [schermi-telefono](../aree/schermi-telefono.md) (vista dello sviluppo)

## Contesto

Il 07/10 la creazione a voce di un'estensione del meteo è durata quaranta minuti di tentativi
sparsi: l'estensione si poteva provare solo **dopo** averla approvata con la frase di sfida, e ogni
errore voleva dire riapprovare.

## Decisione

- Uno sviluppo passa per fasi esplicite: **analisi → sviluppo e test → collaudo → revisione →
  attivazione** (quattro per un programma, senza attivazione).
- Il **collaudo** prova la versione candidata con i dati detti dalla persona («prova con Bolzano e
  con San Vito»), **prima** dell'approvazione; un collaudo per ogni valore detto.
- All'agente arriva una **traccia di rete** del collaudo (al più 12 richieste, URL ripuliti) e, dopo
  un fallimento, il **confronto** tra collaudi riusciti e falliti e le risposte vere del servizio
  come esempi per i test.
- La porta rifiuta gli **URL non codificati** e segnala la **doppia codifica** (solo un avviso).
- Un tool in più per lo sviluppo, non due modalità del prompt: il prefisso resta in cache. Il
  risultato del collaudo è un dato non fidato.
- Sugli schermi una vista dello sviluppo (fasi, due colonne, testo dell'agente in diretta).

## Alternative considerate

- **Provare dopo l'approvazione** (com'era): troppi giri e troppe sfide.
- **Una modalità del prompt per lo sviluppo**: cambierebbe il prefisso a ogni passaggio.
- **Rifiutare la doppia codifica**: no, un `%2B` può essere voluto («C++», «1+1»).

## Conseguenze

- Il caso della doppia codifica è raccontato in [`docs/analisi.md`](../analisi.md): con la sola
  traccia un modello di prova correggeva 0 casi su 4, con il confronto completo 4 su 4.
- Prima frase nei turni dello sviluppo 1,32 s contro 1,00–1,18 s.
- Il ricollaudo alla consegna e le sonde vengono da qui ([0017](0017-ricollaudo-e-sonde.md)).
- La macchina a stati darà ai tool dello sviluppo un profilo proprio ([0022](0022-macchina-a-stati-del-dialogo.md)).

## Fonti

- [`2026-10-08-modalita-sviluppo.md`](../ricerche/2026-10-08-modalita-sviluppo.md)
- [agenti-estensioni](../aree/agenti-estensioni.md), giri 3–6 e «Diagnosi dei collaudi»
