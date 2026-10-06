# Contribuire

Calliope è un progetto personale e cambia ogni giorno. Segnalazioni e idee sono benvenute.

## Lingua

Codice, commenti, messaggi e documenti sono in **italiano**; i nomi di variabili, funzioni e
classi in inglese, come nel codice esistente. Nelle issue va bene anche l'inglese.

## Prima di proporre una modifica

**Per ora i contributi esterni si discutono prima in una issue**: descrivi il problema o
l'idea, e solo dopo un accordo apri una pull request. Il progetto ha principi precisi (latenza,
tutto locale, dipendenze native minime, regole sul testo ristrette) e un congelamento delle
funzionalità nuove finché la latenza non è stabile: una PR senza discussione rischia di non
poter entrare.

Leggi [`CLAUDE.md`](CLAUDE.md) (principi e mappa dei moduli) e il documento della tua area in
[`docs/aree/`](docs/aree/).

## Prove

```bash
python -m prove              # prove a secco: veloci + quelle legate ai file cambiati
python -m prove --completo   # tutte, prima di una pull request
python -m prove --ollama     # anche quelle con il modello vero, per le modifiche alla voce
```

Attiva l'hook una volta: `git config core.hooksPath .githooks`. Una prova nuova va registrata in
`prove/__main__.py` e descritta in [`prove/elenco.md`](prove/elenco.md).

## Niente dati personali

Il repository è pubblico: nelle prove e nei documenti solo nomi, indirizzi e dati di fantasia;
niente registrazioni, impronte vocali, token, indirizzi della tua rete. La prova
`prove/prova_dati_privati.py`, nell'hook, ferma il commit che li contiene
([`docs/pubblicazione.md`](docs/pubblicazione.md)).

## Licenza

Calliope è sotto [AGPL-3.0-or-later](LICENSE); un contributo accettato si rilascia con la stessa
licenza.

Chi mantiene il progetto si riserva la possibilità di offrire Calliope anche con un'altra licenza
(doppia licenza). Proponendo un contributo dichiari che è opera tua e concedi a chi mantiene il
progetto, oltre all'AGPL, il diritto di rilasciarlo anche con altre licenze. Se non sei d'accordo,
dillo nella issue prima di scrivere il codice: ne parliamo.

## Sicurezza

Le vulnerabilità non si segnalano nelle issue pubbliche: vedi [`SECURITY.md`](SECURITY.md).
