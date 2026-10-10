# 0019. In ombra prima di accendere

- **Stato**: accettata come metodo (dall'08/10/2026); il «percorso corto» del 10/10 lo limita alle
  parti che decidono se un'azione si esegue
- **Area**: tutte; vedi [`docs/analisi.md`](../analisi.md)

## Contesto

Una regola nuova sulla sicurezza o sul dialogo cambia il comportamento su casi che nessuno ha
previsto. Le prove a secco dicono se fa ciò che si voleva sui casi scritti; non dicono quante volte
scatterà sui turni veri, né se fermerà qualcosa che prima andava bene.

## Decisione

Una decisione nuova che può **eseguire o fermare un'azione** gira prima **in ombra**: si calcola
accanto a quella in uso, si scrive nel registro dei turni (mai il testo, solo i campi) e non ha
effetto. Si accende quando i numeri, letti con un criterio **scritto prima**, lo dicono. Dopo
l'accensione l'ombra si rovescia: la decisione di prima resta calcolata, per tornare indietro
sapendo cosa si perde. Si torna indietro sempre con una riga di `calliope.locale.yaml`.

| Dove | Ombra | Esito |
|---|---|---|
| Sicurezza per valore | 08–09/10, `politica_ombra` | accesa il 09/10 ([0015](0015-sicurezza-per-valore.md)) |
| Compagnia, «la frase è rivolta a Calliope?» | dal 09/10 | in ombra, da rileggere |
| Nomi capiti male negli argomenti | misura dall'08/10 | «forse intendevi…?» acceso solo dopo un esito vuoto |
| Interprete della risposta e consenso unico | proposti il 10/10, `dialogo_ombra` | in corso ([0022](0022-macchina-a-stati-del-dialogo.md)) |

## Alternative considerate

- **Accendere e guardare**: un errore di sicurezza si scopre quando è già successo.
- **Ombra per tutto**: rallenta senza motivo le parti che non decidono azioni. Dal 10/10 («percorso
  corto») le parti senza rischio si accendono subito, mentre l'ombra raccoglie i dati delle altre.
- **Ombra per i minori**: i due cancelli del 09/10 sono stati accesi subito con scelte prudenti, perché
  un falso negativo su un minore in pericolo è peggio di un falso positivo
  ([0025](0025-minori-due-cancelli.md)).

## Conseguenze

- Il registro dei turni (`registro/`, JSONL, un file al giorno) è la memoria delle decisioni: ogni
  regola vi scrive il suo nome (campo `regole`), e `calliope stato --turni` riassume latenza, attrito,
  ombra e compagnia per giorno.
- Ogni ombra ha bisogno di giorni d'uso veri: i numeri vanno letti, non solo raccolti.

## Fonti

- [sicurezza-politica](../aree/sicurezza-politica.md), «Sicurezza per valore, fase 4»
- [`2026-10-09-piu-persone.md`](../ricerche/2026-10-09-piu-persone.md)
- [`2026-10-08-parole-incerte.md`](../ricerche/2026-10-08-parole-incerte.md)
- [`2026-10-10-macchina-stati.md`](../ricerche/2026-10-10-macchina-stati.md) § 6
