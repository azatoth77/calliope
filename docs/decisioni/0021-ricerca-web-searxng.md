# 0021. Ricerca web con un SearXNG locale

- **Stato**: accettata (03/10/2026); aggiornamento quotidiano dal 09/10
- **Area**: [biblioteca](../aree/biblioteca.md)

## Contesto

La conoscenza generale sta nella biblioteca offline, ma notizie, meteo e prezzi cambiano ogni giorno.
La ricerca web è l'unica funzione che esce davvero su internet, e porta dentro testo scritto da
chiunque.

## Decisione

- Motore: **SearXNG** in un container sul server, in ascolto solo su 127.0.0.1, senza chiavi d'accesso
  e senza log (le domande in POST, al più 10 al minuto). È un metamotore libero: interroga i motori
  pubblici senza account.
- Dalle domande si tolgono i **dati personali** (nomi registrati, indirizzo, email, IBAN, codici
  fiscali, numeri lunghi) prima che escano.
- Il testo dei siti è un **dato non fidato** in busta ([0014](0014-politica-unica-dati-in-busta.md)):
  dopo un risultato web, nella stessa risposta, partono solo tool di lettura (0 azioni su 8 tentativi
  nella misura).
- Il tool c'è solo se il servizio risponde; senza rete sparisce.
- Dal 09/10 un **controllo quotidiano** a Calliope inattiva: un tag nuovo (mai `latest`, con digest,
  pubblicato da almeno 3 giorni) si prova accanto e si tiene solo se va almeno come il vecchio, con il
  ritorno indietro; i motori che non rispondono si mettono in pausa.

## Alternative considerate

- Le API di ricerca commerciali sono escluse per principio, non per un confronto (deciso da chi
  amministra il 10/10): richiedono una chiave, un account e un pagamento, e manderebbero ogni domanda
  a un'unica azienda. In un progetto aperto, che ognuno deve poter installare così com'è, non hanno
  posto.
- Dentro SearXNG: Google web spento (captcha), Bing web tolto il 09/10 (ignorava l'italiano).

## Conseguenze

- Ricerca di 1,3 s di mediana sulla DGX, prima frase 1,55 s.
- Limite noto del filtro dei nomi: un nome di casa uguale a quello di un personaggio famoso viene
  tolto anche dove non serviva.

## Fonti

- [`2026-10-03-ricerca-web.md`](../ricerche/2026-10-03-ricerca-web.md)
- [biblioteca](../aree/biblioteca.md), «SearXNG tenuto aggiornato» e «Risultati in italiano per primi»
