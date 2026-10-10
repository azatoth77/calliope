# 0014. Una politica unica dei tool, con i dati non fidati in busta

- **Stato**: accettata (05/10/2026); guardie doppie tolte il 06/10; raffinata dalla sicurezza per
  valore il 09/10 ([0015](0015-sicurezza-per-valore.md))
- **Area**: [sicurezza-politica](../aree/sicurezza-politica.md), [`architettura-tool.md`](../architettura-tool.md)

## Contesto

Testo d'altri arriva al modello da molti canali: pagine web, scritte in una foto, allegati, audio
trascritto, estensioni, OCR dell'archivio, riassunti degli agenti, stati di Home Assistant. Chi lo
scrive può volere che Calliope **agisca** (accendi, cancella, manda), **faccia uscire** dati o **dica
il falso**. Fino al 05/10 ogni canale aveva le sue guardie, e un canale nuovo poteva dimenticarle.

## Decisione

- **Una porta sola** per i dati non fidati (`Brain.dato_non_fidato`): il testo entra in una
  **busta** con la sua provenienza (`[DATO NON FIDATO (fonte: web)…]`), con i delimitatori
  neutralizzati. La contaminazione della conversazione si ricava dalla storia e si azzera alla
  chiusura della conversazione.
- **Una politica sola** in `ToolRegistry.call`, uguale per ogni canale: ogni tool ha una classe
  (`sicuro`, `azione`, `pericoloso`, `vietato`; **senza classe vale pericoloso**). Con una
  conversazione pulita non cambia nulla; con un dato di mezzo un'azione parte solo se chiesta, una
  pericolosa solo con la conferma a voce o con la frase di sfida.
- **Quarantena** per i dati lunghi (oltre 800 token): un modello senza tool estrae solo ciò che
  serve.
- **Ciò che dice** (06/10, `riferire.py`): con dati non fidati di mezzo ogni frase si controlla
  prima della voce (numeri di pagamento, segreti, soldi, contatti, istruzioni).
- Cinque **confini**: C1 rete, C2 azioni, C3 codice dell'agente, C4 estensioni, C5 uscita.

## Alternative considerate

- **Guardie per canale**: scartate perché si dimenticano; quelle doppie sono state tolte il 06/10
  (P6 dell'analisi complessiva).
- **Un modello come giudice delle frasi d'uscita**: prendeva 10 attacchi su 11 ma con 7 falsi
  allarmi su 25 frasi normali e 514 ms di mediana; le regole prendono tutto il banco a costo zero
  (0,17 ms).
- **Nascondere i tool per livello**: non è un confine ([0009](0009-tool-uguali-per-ogni-livello.md)).

## Conseguenze

- Banco a secco: 9 canali × 9 attacchi con un modello finto che «ci casca» sempre, **81/81 fermati**;
  poi **99/99** con i casi di ciò che dice. Ciò che dice con dati ostili: 22/27 → 0/27 (4B), 9/27 →
  0/27 (26B), 0/36 falsi allarmi. Allegati ostili: 26 casi, 0 azioni.
- **Attrito**: il 07/10 la politica faceva 15,8 domande ogni 100 turni, il 68 % inutili. Da qui la
  sicurezza per valore ([0015](0015-sicurezza-per-valore.md)).
- Fuori dal modello di minaccia: una voce clonata in tempo reale, una macchina compromessa. Il
  secondo fattore per chi amministra è in progetto
  ([`2026-10-06-secondo-fattore.md`](../ricerche/2026-10-06-secondo-fattore.md)).

## Fonti

- [`2026-10-05-politica-sicurezza.md`](../ricerche/2026-10-05-politica-sicurezza.md)
- [`2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md) § 1
- [`2026-10-05-allegati.md`](../ricerche/2026-10-05-allegati.md)
