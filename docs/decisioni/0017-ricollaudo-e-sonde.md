# 0017. Ricollaudo alla consegna e sonde solo verso host noti

- **Stato**: accettata (08/10/2026, notte)
- **Area**: [agenti-estensioni](../aree/agenti-estensioni.md), [sicurezza-politica](../aree/sicurezza-politica.md)

## Contesto

Durante lo sviluppo l'agente faceva richieste di prova al servizio esterno (`scarica_esempio`, 15
volte in un giorno), ma con l'URL scritto bene da lui: la prova non diceva nulla del codice, che
costruiva l'URL in un altro modo. E l'agente annunciava «è pronto» senza aver riprovato i casi
falliti della persona. D'altra parte, lasciare all'agente richieste libere verso internet apre una
via d'uscita ai dati.

## Decisione

- **Ricollaudo alla consegna**: prima di «è pronto», una volta per lavoro, la versione consegnata si
  riprova con i casi della persona che erano falliti.
- **Sonde** (`sonda_rete` al posto di `scarica_esempio`): solo verso **host già noti** dal collaudo,
  con valori presi solo dal caso; al più 4 per lavoro, 2 per passata, 12 per sviluppo al giorno, 256
  kB e 8 s ciascuna. Il testo dei siti arriva all'agente in busta.

## Alternative considerate

- **Nessuna sonda**: l'agente lavora alla cieca.
- **Approvazione a voce di ogni sonda**: non funziona nella pratica («3 richieste a X» non si giudica
  a voce).
- **Risposte in busta senza altri limiti**: necessarie, da sole non bastano.

## Conseguenze

- Banco d'attacco (conversazione esca, host non noti, casa, rebinding, estensione ostile): **0
  passaggi su 59**, a secco; da rifare sulla DGX con il container vero.
- Il nome pubblico di casa è vietato in `RetePubblica`.

## Fonti

- [`2026-10-08-sonde-agente.md`](../ricerche/2026-10-08-sonde-agente.md)
