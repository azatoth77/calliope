# 0013. Estensioni con porta stretta e approvazione con la sfida

- **Stato**: accettata (04/10/2026); rete delle estensioni dal 05/10; le estensioni che leggono
  soltanto sono letture dal 09/10
- **Area**: [agenti-estensioni](../aree/agenti-estensioni.md)

## Contesto

Un'estensione è un tool nuovo scritto dall'agente su richiesta («voglio sapere il cambio
euro-dollaro»), che resta in Calliope per sempre. È **codice non fidato per sempre**: nessuno lo
rilegge riga per riga, e può essere stato scritto sotto l'influenza di un testo ostile.

## Decisione

- Ogni chiamata gira in un **container** proprio (stessa sandbox degli agenti), senza segreti e
  senza rete diretta; tetti di 30 s e 512 MB; impronta SHA-256 ricontrollata a ogni esecuzione;
  al più 8 estensioni attive.
- Tutto passa dalla **porta stretta**: JSON-RPC su stdin/stdout verso i tool veri di Calliope, al
  più con i permessi di un familiare. Il protocollo prende la cornice di MCP **senza l'SDK** (~150
  righe per parte).
- **Rete** (05/10): l'internet pubblico si legge liberamente attraverso `RetePubblica` (porte 80 e
  443, niente indirizzi privati né rebinding); verso fuori solo lungo i flussi approvati; dopo una
  lettura di dati personali l'estensione è contaminata. Dal 08/10 anche i nomi pubblici della casa
  sono vietati.
- **Approvare** un'estensione o tornare a una versione vuole **sempre la frase di sfida** (tre parole
  e un numero scelti sul momento: una registrazione o la TV non li contengono).
- Un tool per estensione (`est_*`), con argomenti vincolati dallo schema: il prefisso del prompt
  cambia solo all'approvazione (+1,1–1,5 s una volta).

## Alternative considerate

- **SDK MCP**: dipende da `cryptography` (senza wheel `win_arm64`) ed è solo asincrono.
- **Protocollo tutto proprio**: nessun riuso.
- **Un tool generico `estensione_usa`**: argomenti non vincolati dallo schema.
- **Secondo parere di un modello** sul codice: tenuto solo come controllo che può **alzare** la classe
  di rischio, mai abbassarla.

## Conseguenze

- Banco d'attacco (SSRF, rebinding, dati esca, tetti aggirati a pezzi…): **0 passaggi su 76**, anche
  con il container vero sulla DGX; il banco ha trovato e fatto correggere tre difetti.
- Una richiesta alla porta costa 0,16 s di mediana.
- Dal 08/10 un'estensione nasce nella modalità sviluppo, con il collaudo prima dell'approvazione
  ([0016](0016-modalita-sviluppo-con-collaudo.md)).

## Fonti

- [`2026-10-04-estensioni-e-guardrail.md`](../ricerche/2026-10-04-estensioni-e-guardrail.md)
