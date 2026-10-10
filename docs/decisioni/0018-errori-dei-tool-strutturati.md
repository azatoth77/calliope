# 0018. Errori dei tool strutturati per il dialogo tra modelli e codice

- **Stato**: accettata (09/10/2026)
- **Area**: [voce-e-regole](../aree/voce-e-regole.md), [`architettura-tool.md`](../architettura-tool.md) § 6

## Contesto

Un caso vero del 09/10: il modello chiama la ricerca web con il solo tipo «notizie» e senza la
domanda; il tool risponde con la traccia di un `TypeError` di Python. Il modello dice «riprovo subito»
e non riprova, quattro volte di fila. Il problema non era quel tool: un modello non sa che farsene di
una traccia, e nessuno gli dice cosa correggere.

## Decisione

Nessuna regola per «notizie senza domanda»: un **protocollo generale** per tutti i tool (anche delle
estensioni e degli agenti), in `calliope/tools/dialogo.py`:

- gli argomenti si controllano contro lo schema **prima** della chiamata, con le conversioni di forma
  ammesse (un numero scritto come testo);
- un errore torna al modello **in parole** e sempre nella stessa forma: `ok: false`, `fatto: NIENTE`,
  quale argomento, i valori ammessi, un esempio, se è correggibile e **cosa fare**; mai una traccia;
- **giro di correzione**: se l'errore è correggibile e il modello risponde «riprovo» senza richiamare
  il tool, il testo si trattiene e si chiede di richiamarlo; al più 2 correzioni, con una frase
  d'attesa dopo 2 s.

## Alternative considerate

- **Una regola per il caso visto**: pilota i casi, non risolve la classe.
- **Esempi scritti a mano per ogni tool**: stesso difetto; l'esempio si ricava dallo schema.

## Conseguenze

- Col modello da 4B le chiamate sbagliate corrette passano da 2/21 a **18/21**; ogni passata di
  correzione costa 0,4–0,7 s.
- Resta da fare il contratto unico dei risultati **riusciti** (§ 6.1 di `architettura-tool.md`).
- La macchina a stati userà lo stesso canale per i suoi tool di servizio, fuori dalla storia della
  conversazione ([0022](0022-macchina-a-stati-del-dialogo.md)).

## Fonti

- [`2026-10-09-dialogo-tool.md`](../ricerche/2026-10-09-dialogo-tool.md)
