# Aggiungere un contenuto alla libreria dello Studio

*31/10/2026, issue #297, epic #251, decisione [0035](../../docs/decisioni/0035-studio.md) punto 45.
Codice in `calliope/studio/libreria/`, contenuti in `calliope/studio/libreria/contenuti/<materia>/`,
area [studio](../../docs/aree/studio.md).*

La libreria è fatta di file JSON scritti con Claude, provati dal codice e rivisti da una persona
prima dell'unione. Sono dati fidati: entrano nello Studio senza busta, quindi la revisione conta
quanto quella del codice. Il repository è pubblico: niente nomi veri di scuole, docenti o studenti,
solo la descrizione della classe; esempi con dati di fantasia; testi originali, mai copiati.

## 1. Scegliere cosa scrivere

- Una **scheda** per argomento e il suo **mazzo** di carte (8–10). Le mini-app arrivano con la
  parte 2 della #297 e hanno il loro passo.
- Guarda le schede che ci sono (`ls calliope/studio/libreria/contenuti/*/`): un argomento nuovo,
  non un doppione. Decidi i prerequisiti fra le schede esistenti.

## 2. Farlo scrivere a Claude

Da una sessione di Claude Code nel repository, una richiesta come questa:

> Scrivi per la libreria dello Studio la scheda e il mazzo dell'argomento «…» (materia …, prima
> superiore, tecnico tecnologico, Chimica, materiali e biotecnologie). Leggi prima
> `calliope/studio/libreria/formato.py`, `indice.py`, due contenuti della stessa materia come
> esempio e `prove/verita_libreria.py`. Prerequisiti: … Scrivi solo i due file in
> `contenuti/<materia>/`, poi lancia `prove/verita_libreria.py` finché dice 0 errori.

Quello che Claude deve rispettare, e che la persona ricontrolla:
- **Formato** (`formato.py`): testo semplice, niente markdown, link o emoji; paragrafi separati da
  una riga vuota solo nel testo delle sezioni; le lunghezze massime.
- **Chiavi**: le forme con cui il titolo di un argomento (dal libro, dalla verifica) nomina
  l'argomento. Ogni parola della chiave deve stare nel titolo, quindi niente chiavi di una parola
  generica («soluzioni», «misura», «moto» da sole: «Soluzioni degli esercizi» non è chimica).
- **Carte**: una risposta chiusa (un numero o al più tre parole) ha la `sbagliata`, l'errore tipico;
  le sue parole stanno nella scheda. Attenzione al confronto delle carte: i numeri diventano parole
  e «uno» vale come articolo, quindi una risposta chiusa con «1» o «1,5» non si controlla bene (meglio
  una risposta lunga o un altro numero).
- **Conti**: ogni esempio, «prova tu» e carta con un conto dichiara il `calcolo`, che la prova rifà
  con la sua tabella; il risultato scritto nel testo deve essere quello.

## 3. Provarlo

```
.venv\Scripts\python.exe prove\verita_libreria.py
.venv\Scripts\python.exe -m prove prova_studio_libreria.py prova_studio_libreria_pagina.py
```

- `verita_libreria.py` dice gli errori file per file: formato, prerequisiti che non ci sono, cicli,
  conti, risposte chiuse e sbagliate, risposte fuori dalla scheda. Deve dire **0 errori**.
- Prova l'indice con i titoli che un libro userebbe, e con qualche titolo che **non** deve trovare
  la scheda:

```
.venv\Scripts\python.exe -c "from calliope.studio.libreria import Libreria; L = Libreria.carica(); print(L.trova('Il titolo del libro', 'Chimica'))"
```

  Se un titolo vero non trova niente, aggiungi la chiave; se un titolo d'altro la trova, togli la
  chiave troppo larga. I casi buoni vanno nelle prove (`VERI` e `CONTRARI` di
  `prova_studio_libreria.py`) quando l'argomento è nuovo.
- Nella pagina vera: uno Studio di prova con una verifica di quella materia e un argomento col
  titolo del libro, poi Le mie cose › Studio › «Dalla libreria»: «Apri» e «Aggiungi le carte».

## 4. Rivederlo

Una persona legge la scheda e le carte **intere** prima dell'unione (la PR verso il ramo
dell'epic), con queste domande:
- è giusto? (fatti, unità, conti, definizioni del primo anno; niente di più difficile del
  programma della classe);
- è chiaro per un ragazzo di quattordici anni, e si capisce anche letto ad alta voce?
- le carte chiedono una cosa sola e la risposta è una sola? La «sbagliata» è davvero l'errore
  tipico?
- niente di copiato, niente nomi veri, niente marchi.

Quando è rivisto, `revisione` prende la data della revisione. Un contenuto corretto dopo si rivede
di nuovo e cambia la data.
