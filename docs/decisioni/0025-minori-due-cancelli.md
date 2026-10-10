# 0025. Minori: un segnale di pericolo poco chiaro passa da due cancelli

- **Stato**: accettata (09/10/2026); alcune soglie da confermare e da rimisurare sulla DGX
- **Area**: [minori](../aree/minori.md)

## Contesto

Con un minore che parla, Calliope ha due controlli: un **guardiano** sui contenuti (Llama Guard 3 8B,
0/18 falsi su domande normali, 12/14 risposte vietate fermate) e un **rilevatore di pericolo** per chi
parla (gemma4 e4b con output strutturato: «lo zio mi picchia» è un pericolo, e Llama Guard non lo
vede). Fino all'08/10 un pericolo voleva dire subito i numeri d'aiuto e un avviso urgente al tutore.
Un caso vero, raccontato con nomi di fantasia in [`docs/analisi.md`](../analisi.md), ha mostrato il
costo: un adulto ospite preso per il ragazzo di casa, una frase di mezzo secondo giudicata pericolo,
un avviso urgente detto a voce mentre il ragazzo non c'era. Il rilevatore, sulle frasi poco chiare
(«Addio.», «Che palle, mi sparo.»), diceva pericolo 10 volte su 12.

## Decisione

Decisione di chi amministra: «un minore venga prima rassicurato, poi si cerca di capire se il
problema è reale; solo superato il secondo cancello si manda la notifica», con prudenza: un falso
negativo su un minore in pericolo è peggio di un falso positivo.

- **Gravità**: un segnale **acuto** (esplicito anche se breve) va come prima: protezione e avviso
  urgente subito. Un giudizio guasto vale acuto.
- **Cancello 1** per un segnale **dubbio**: una frase che rassicura e chiede («Sono qui con te…»),
  senza nominare l'allarme; il segnale resta aperto 300 s.
- **Cancello 2**: la frase dopo va al rilevatore con il primo segnale. Conferma (anche una reticenza)
  → avviso urgente; smentita → nessun avviso; due segnali dubbi in 30 minuti → confermato; silenzio →
  avviso **non urgente**.
- Gli avvisi dicono l'argomento, mai le parole del minore, e non si dicono a voce vicino a lui.
- In **compagnia** (più voci vicino al satellite) la voce del minore non è mai «sicura» e una frase
  sotto 1 s non eredita il minore della conversazione.

## Alternative considerate

- **Avviso subito per ogni segnale** (com'era): falsi allarmi che consumano la fiducia del tutore.
- **Chiedere «chi parla?»**: un nome detto non è una prova, e un ragazzo in difficoltà potrebbe usarlo
  per evitare l'avviso.
- **Ombra prima di accendere**: non usata qui; si è scelto di accendere subito con scelte prudenti.

## Conseguenze

- Misure (portatile): esplicite giudicate acute 13/13, poco chiare giudicate dubbie 11/12 («Aiuto.»
  resta acuto), verifiche 11/11, ~0,45 s; il costo è solo nei turni con un segnale.
- Da confermare: l'avviso sul silenzio, le attese di 300 e 1800 s, il rinvio a voce di 600 s.

## Fonti

- [minori](../aree/minori.md), «Pericolo poco chiaro: il giro a due cancelli (09/10)»
- [`2026-10-05-minori.md`](../ricerche/2026-10-05-minori.md) § 4
- [`2026-10-09-piu-persone.md`](../ricerche/2026-10-09-piu-persone.md)
