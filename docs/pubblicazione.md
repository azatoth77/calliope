# Pubblicazione del sorgente: cosa entra in git e cosa no (07/10/2026)

Il repository è pubblico dal 07/10/2026, preparato il 06/10 (licenza AGPL-3.0-or-later,
[`LICENSE`](../LICENSE); componenti di terzi in [`TERZE-PARTI.md`](../TERZE-PARTI.md)).
Calliope però gira in una casa vera, con persone vere: questo documento dice come si tiene
separato ciò che si pubblica da ciò che resta privato, e cosa controlla la prova nell'hook.

## 1. La regola

- Nel codice, nelle prove, nei copioni e nei documenti solo **nomi, indirizzi e dati di
  fantasia**: familiari d'esempio (Bianca, Matteo, Elena, Luca, Sara…), indirizzi privati
  d'esempio, codici fiscali e IBAN di prova, `casa-mia.duckdns.org`, `C:\Users\x`. Il nome
  di chi amministra nelle prove è quello dell'autore.
- I valori di **questa** installazione stanno fuori da git come sempre (principio 3):
  `calliope.locale.yaml`, `segreti.yaml`, `dgx.yaml`, `satellite.json`, `speakers.json`,
  `memoria.db`, `registro/`, `registrazioni/`… (vedi `.gitignore`).
- I **documenti privati** (sessioni e test vocali veri, impianti e rete della casa,
  risultati con le persone vere) stanno in `privato/`, cartella ignorata da git dentro il
  repository: restano la memoria del progetto sul disco di chi ci lavora, ma non si
  pubblicano. Un documento utile con qualche riferimento alla casa si **generalizza** invece
  di spostarlo; dove una sezione intera descrive la casa vera, la sezione va in `privato/` e
  nel documento resta un riassunto senza i dettagli.
- La storia di git prima della pubblicazione non è pubblica: è conservata a parte, in un
  archivio (`git bundle`) dentro `privato/`.

## 2. La prova nell'hook: `prove/prova_dati_privati.py`

Livello 1, a ogni commit, sulla copia dell'indice (~2 s). Ferma il commit se un file tracciato
contiene:

| Cosa | Come |
|---|---|
| file che non vanno mai in git | estensioni (database, audio, chiavi e certificati, modelli, ZIM, bundle) e nomi (`segreti.yaml`, `dgx.yaml`, `satellite.json`, `speakers.json`, `calliope.locale.yaml`…) |
| segreti riconoscibili | chiavi private PEM, JWT, token di GitHub, Hugging Face, OpenAI, AWS, Slack, Google, chiavi SSH |
| indirizzi IP privati | ogni indirizzo privato non tra quelli d'esempio (`ESEMPI_IP` nella prova, ognuno inventato o predefinito di un prodotto); in `uv.lock` i numeri a quattro parti sono versioni |
| nomi DuckDNS | tutti tranne i segnaposto |
| percorsi con un nome utente | `C:\Users\<nome>`, `/home/<nome>`, tranne i segnaposto |
| termini privati | le righe di `privato/termini.txt` (nomi veri della famiglia, dominio e nome dell'azienda, indirizzi veri…): senza il file questa parte si salta e la prova lo dice |

I messaggi non stampano mai il valore trovato intero (solo le prime lettere). Prima del
controllo vero la prova si controlla su un albero finto, con i casi contrari.

Formato di `privato/termini.txt` (una riga per termine):

```
# commento
Parola                     parola intera, maiuscole come scritte
i:parola                   parola intera, senza distinguere maiuscole e minuscole
re:espressione             espressione regolare
Termine || eccezione       una riga che contiene l'eccezione non conta (es. una voce di Piper)
```

Il file si cerca in `CALLIOPE_TERMINI_PRIVATI`, poi in `privato/` del repository da cui parte
la prova e della cartella principale (un worktree usa quella).

## 3. Prima di un push su GitHub

1. `python -m prove --completo` (con `privato/termini.txt` presente).
2. `git log --format="%an <%ae>"` dei commit nuovi: l'autore è l'indirizzo «noreply» di
   GitHub.
3. Niente di `privato/` è tracciato (`git ls-files privato` non stampa nulla).
