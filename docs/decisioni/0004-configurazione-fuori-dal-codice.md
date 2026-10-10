# 0004. Configurazione fuori dal codice

- **Stato**: accettata (26/09/2026, `calliope.yaml`); file locale dal 01/10
- **Principi**: 3 di [`CLAUDE.md`](../../CLAUDE.md)
- **Area**: [voce-e-regole](../aree/voce-e-regole.md)

## Contesto

Calliope gira su macchine diverse (portatile, DGX, satelliti) e il repository è pubblico: i valori
di una casa (indirizzi, cartelle, dispositivi audio, token) non possono stare nel codice né in un
file tracciato. Allo stesso tempo ogni valore predefinito ha un motivo che va scritto da qualche
parte, vicino al valore.

## Decisione

- I **predefiniti**, ognuno con il commento che lo motiva, stanno nella dataclass `Config` di
  `calliope/config.py`.
- `calliope.yaml` (a sezioni) **si rigenera** dai commenti con
  `python -m calliope.config --esempio > calliope.yaml`, non si scrive a mano.
- I valori di **questa installazione** vanno in `calliope.locale.yaml`, fuori da git (dal 01/10);
  i segreti in `segreti.yaml`.
- Priorità: predefinito < `calliope.yaml` < `calliope.locale.yaml` < variabili d'ambiente
  `CALLIOPE_*`; `CALLIOPE_CONFIG` sceglie un altro file.
- Chiavi sconosciute e tipi sbagliati si segnalano senza fermare l'avvio. Niente percorsi scritti
  nel codice.

## Alternative considerate

- **Un solo file modificato a mano** (fino al 30/09): `calliope.yaml` divergeva dall'esempio e la
  prova `prova_config` falliva a ogni campo nuovo; i valori di casa rischiavano di finire in git.
- **Configurazione solo da variabili d'ambiente**: poco leggibile per ~centinaia di campi, e senza
  un posto per i commenti.

## Conseguenze

- Aggiungere un campo vuol dire scriverlo nella dataclass con il suo commento; il file d'esempio
  segue da solo.
- Le prove non leggono il file locale (`CALLIOPE_CONFIG_LOCALE` puntato altrove dal runner).
- I campi sono tanti: ridurli è una proposta aperta (Q12 dell'analisi del 06/10,
  [roadmap](../roadmap.md)).
- Il modello della voce si cambia con una riga, `llm_profilo` ([0002](0002-llm-dietro-api-intercambiabile.md)).

## Fonti

- [`CLAUDE.md`](../../CLAUDE.md), principio 3
- [`docs/pubblicazione.md`](../pubblicazione.md) (cosa resta fuori da git)
