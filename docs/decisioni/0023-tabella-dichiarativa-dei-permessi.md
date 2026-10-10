# 0023. Una tabella dichiarativa dei permessi

- **Stato**: **proposta** (10/10/2026), da fare nel passo 2 della macchina a stati
- **Area**: [sicurezza-politica](../aree/sicurezza-politica.md)

## Contesto

Oggi la decisione «esegui, chiedi, sfida o rifiuta» per una chiamata di tool è il risultato di più
moduli: i livelli in `ToolRegistry.call`, le classi in `politica.py`, la matrice effetto ×
provenienza in `valore.py`, le conferme in `conferme.py`, le regole dei minori. Ognuno è provato, ma
la regola complessiva non si legge in un posto, e due moduli possono contraddirsi senza che una prova
se ne accorga (l'analisi del 09/10 ne ha trovati casi).

## Decisione

Una sola **tabella leggibile**:

`tool o famiglia × effetto E1–E4 × provenienza del valore × chi parla (livello, voce sicura, zona
grigia, ospite, minore) → esegui | chiedi | sfida | rifiuta`

da cui `politica`, `valore` e `consenso.basta()` **leggono e basta**. La verifica una prova automatica:
ogni riga coperta, nessuna contraddizione, il banco d'attacco a 0. Si consulta dal cruscotto di chi
amministra, prima in sola lettura; la modifica dal cruscotto, se mai, dopo e con la frase di sfida.

L'idea viene da strumenti che lo fanno già: i permessi di Claude Code, gli SDK per agenti, NeMo
Guardrails.

## Alternative considerate

- **Regole sparse nel codice** (com'è oggi): ognuna giusta da sola, difficile da vedere insieme.
- **Una politica scritta in un linguaggio dedicato** (motori di policy esterni): una dipendenza in più
  per una tabella che sta in una struttura dati.
- **Modifica libera dal cruscotto**: rinviata; un permesso cambiato è un'azione di sicurezza e vuole
  la sfida.

## Conseguenze

- La tabella diventa il documento dei permessi: le pagine sulla sicurezza potranno rimandare a lei.
- Insieme al consenso unico, prima in ombra e poi accesa sui numeri ([0019](0019-ombra-prima-di-accendere.md)).

## Fonti

- [`2026-10-10-macchina-stati.md`](../ricerche/2026-10-10-macchina-stati.md), «Aggiunte decise dopo il
  progetto»
- [`2026-10-07-sicurezza-per-valore.md`](../ricerche/2026-10-07-sicurezza-per-valore.md) § 5.4
