# 0007. Streaming frase per frase e latenza come metrica

- **Stato**: accettata (21/09/2026, streaming); latenza come metrica dal 06/10; latenza
  **accettata** il 09/10/2026
- **Principi**: 5 (output per la voce) e 6 (latenza prima di tutto) di [`CLAUDE.md`](../../CLAUDE.md)
- **Area**: [contesto-conversazione](../aree/contesto-conversazione.md)

## Contesto

In una conversazione a voce conta il tempo tra la fine della frase della persona e la prima parola
di Calliope. Un modello che genera 70 token al secondo impiega diversi secondi per una risposta
intera: aspettarla sarebbe inaccettabile. Tra il 03 e il 05/10, con molte funzioni nuove, la
prima frase nei turni veri è passata da 0,78 s (02/10) a 2,05 s di mediana (05/10) senza che
nessuno se ne accorgesse subito.

## Decisione

- **Streaming ovunque**: il testo del modello va a un divisore di frasi; ogni frase completa va
  subito al TTS, e si sintetizza la successiva mentre si riproduce quella corrente. Dal 07/10 la
  prima frase si spezza in un primo pezzo calibrato sulla velocità misurata di Piper.
- **Risposte brevi pensate per la voce**: niente markdown, elenchi, emoji o URL; 1–3 frasi.
- **La latenza è una metrica**, non un'impressione (06/10): il registro dei turni scrive i tempi di
  ogni fase; `calliope stato --turni` dà per giorno mediana, p75 e p90 della prima frase, la base
  senza tool e le cause. Oltre 1,2 s di mediana (`latenza_avviso_s`) compare un avviso all'avvio e
  nello stato.
- **Prefisso stabile per la cache**: prompt di sistema e schemi dei tool uguali per tutti
  ([0009](0009-tool-uguali-per-ogni-livello.md)); i dati che cambiano vanno subito prima della domanda.

## Alternative considerate

- **Risposta intera poi voce**: scartata dall'inizio.
- **Modelli con il ragionamento acceso per la voce**: con `qwen3:8b` la prima frase passava da
  0,57 s a 4,96 s (fino a 9,75 s) senza risposte migliori. La voce non ragiona a lungo: risponde
  o delega a un agente ([0011](0011-modello-davanti-agenti-dietro.md)).
- **Correggere la trascrizione con il modello**: migliora la WER ma aggiunge 0,4–0,5 s
  ([0020](0020-trascrizione-senza-correzione.md)).

## Conseguenze

- Il 09/10 chi amministra ha dichiarato la latenza «buona e accettata così»: prima frase mediana
  1,42 s l'08/10 (giornata con molti tool, p90 3,82 s) e 1,28 s il 09/10 (p90 2,79 s), base senza
  tool 1,18 s, testo→voce 0,35 s, STT 0,18 s. Niente più lavori dedicati: resta l'avviso come
  sentinella.
- Ogni modifica alla pipeline deve preservare lo streaming frase per frase.
- Ogni funzione nuova che aggiunge un passaggio prima della voce (guardiano, correzioni) si misura
  in ombra prima di accenderla ([0019](0019-ombra-prima-di-accendere.md)).

## Fonti

- [contesto-conversazione](../aree/contesto-conversazione.md), «Latenza vera come metrica (06/10)»
  e «Latenza accettata (09/10)»
- [`2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md) (P1–P4, P11)
