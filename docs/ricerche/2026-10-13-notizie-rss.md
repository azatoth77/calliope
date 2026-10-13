# Notizie dai feed RSS: lettura a voce, doppioni, copertura (13/10/2026)

Seguito della ricerca del giorno prima, [`2026-10-12-notizie-rss.md`](2026-10-12-notizie-rss.md)
(elenco dei feed, condizioni d'uso, indice FTS5, scarico ogni 2 ore solo se qualcuno ha chiesto
notizie negli ultimi 7 giorni). Quella misurava i feed **di notte e nel fine settimana**; questa li
rimisura **di giorno, un martedì** (13/10, tre istantanee alle 14:40, 15:40 e 16:40), aggiunge le
fonti che mancavano (meteo e Protezione civile, ragazzi, Il Post) e risponde alle domande nuove della
roadmap (§ 3, punto 5, V4): come si **dice** una notizia, come si **raggruppa** la stessa notizia
data da più testate senza il modello, **quanti feed bastano** per «le notizie di oggi», quale
**lettore XML** e con quale **sicurezza**, e come lo farei in Calliope.

**Risposta breve.**

- **I feed ci sono e sono buoni** [verificato]: una settantina di indirizzi provati, **52 feed veri**
  di 30 fonti (51 RSS 2.0, 1 Atom; il resto erano pagine HTML, 403 o 404); tutti XML ben formati,
  tutti letti con `defusedxml` senza errori. Il Post **funziona** (il 403 del 12/10 veniva dalla
  barra finale: `…/feed` sì, `…/feed/` no). Quasi tutti danno **titolo + 1–2 frasi** (mediana 70–330 caratteri): a voce basta.
- **Doppioni senza modello** [verificato]: un coseno TF-IDF su radici di titolo e inizio del
  sommario, soglia 0,30, raggruppa la stessa notizia da testate diverse con **19–20 gruppi giusti su
  20** controllati a mano, in ~1,1 s di CPU per 1 200 voci. Sotto 0,25 si incatenano notizie diverse.
  Il modello serve per **dire** il gruppo in una frase, non per formarlo.
- **Copertura** [verificato]: con **ANSA (ultima ora e top news), Rainews, Il Post e Sky TG24** si
  trovano **59–76 %** dei fatti che almeno tre testate hanno dato nelle ultime 24 ore e **16 su 17
  (fino a 11 su 11)** di quelli dati da cinque o più. Per «le notizie di oggi» 4 feed generali
  bastano. **Non bastano per lo sport e il locale**: dei 123 fatti dai feed sportivi solo il 5 %
  compare nei generali, dei 147 fatti lombardi il 2 %. Sport, economia, tecnologia e regione vanno presi dai loro feed.
- **Lettore**: libreria standard **più un controllo** delle entità (o `defusedxml`): la
  documentazione di Python dice che Expat prima della **2.7.2** può essere vulnerabile, e sulla DGX
  c'è la 2.6.1 [di seconda mano, misura del 12/10].
- **Proposta**: l'indice del 12/10, più un passo di **raggruppamento** a ogni scarico e un tool di
  lettura `notizie` che restituisce **fatti** (gruppi) numerati, così «dimmi di più sulla seconda»
  risponde dal disco, con tutte le testate di quel fatto, senza internet.

Script e dati (fuori dal repository, nella cartella di lavoro di questa ricerca): `sonda.py` (scarica
e salva i byte, User-Agent `Calliope/0.1 (lettore di feed personale; ricerca)`), `leggi.py` (lettura
con `defusedxml`, misure per feed), `titoli.py` e `pulizia.py` (titoli per la voce), `gruppi.py` e
`gruppi_idf.py` (doppioni), `copertura.py`, `nuove.py` (voci nuove tra istantanee), `robots.py`,
`xmlsicuro.py`. Tutto dal portatile; la DGX non è stata toccata.

## 1. I feed, uno per uno

Istantanea delle 14:40 di martedì 13/10 (UTC+2). Colonne: **formato**; **encoding** dichiarato
(«—» = nessuna dichiarazione, quindi UTF-8); **voci** nel feed; voci delle **ultime 24 h**; **ore
coperte** tra la voce più vecchia e la più nuova; **sommario** (mediana dei caratteri dopo aver tolto
l'HTML); **testo** = testo intero o quasi (`content:encoded`, campi propri, sommario lunghissimo);
**HTML** = voci con marcatura nel sommario; **img** = voci con immagine (enclosure, `media:content`,
`<img>`); **data** = formato della data; **304** = il server dà ETag o Last-Modified (richiesta
condizionata possibile; chi risponde davvero 304 è nel § 6.1). Le voci nuove per ora sono nel
§ 1.4. Tutto [verificato].

### 1.1 Generali nazionali

| Testata | Indirizzo | Formato, encoding | Voci | 24 h | Ore coperte | Sommario | Testo | HTML | img | Data | 304 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ANSA ultima ora | `https://www.ansa.it/sito/ansait_rss.xml` | RSS 2.0, UTF-8 | 27 | 27 | 19 | 87 | no | 0 | 0 | RFC 822 | no |
| ANSA top news | `https://www.ansa.it/sito/notizie/topnews/topnews_rss.xml` | RSS 2.0, — | 10 | 10 | 2,6 | 69 | no | 0 | 0 | RFC 822 | no |
| ANSA cronaca, politica, economia, mondo | `https://www.ansa.it/sito/notizie/<sezione>/<sezione>_rss.xml` | RSS 2.0, — | 19–145 | 18–58 | 23–71 | 67–76 | no | 0 | 0 | RFC 822 | no |
| Rainews (tutti) | `https://www.rainews.it/rss/tutti` | RSS 2.0, — | 40 | 40 | **6** | 144 | no | 0 | 40 | RFC 822 | LM |
| Rainews ultima ora, cronaca, esteri | `https://www.rainews.it/rss/ultimora` (`cronaca`, `esteri`, `politica`) | RSS 2.0, — | 41 | 3–29 | 41–280 | 61–172 | no | 0 | 41 | RFC 822 | LM |
| Il Post | `https://www.ilpost.it/feed` (**senza** barra finale) | RSS 2.0, UTF-8 | 90 | 50 | 46 | 117 (44 voci senza) | no | 79 | 79 | RFC 822 | sì |
| la Repubblica | `https://www.repubblica.it/rss/homepage/rss2.0.xml` | RSS 2.0, — | 30 | 30 | 16 | 139 | no | 0 | 0 | RFC 822 | no |
| Corriere (Cronache, Politica, Esteri) | `https://www.corriere.it/dynamic-feed/rss/section/<Sezione>.xml` | RSS 2.0, — (`<!DOCTYPE xml>`) | 100 | 8–28 | 87–444 | 83–155 | no | 0 | 100 | RFC 822 | no |
| AGI | `https://www.agi.it/rss` | RSS 2.0, UTF-8 | 20 | 20 | **2,9** | **2 229** | nel sommario | 20 | 20 | RFC 822 | sì |
| Adnkronos ultima ora | `https://www.adnkronos.com/RSS_Ultimora.xml` | RSS 2.0, UTF-8 | 20 | 20 | **2,3** | 150 | no | 0 | 18 | RFC 822 | sì |
| Sky TG24 | `https://tg24.sky.it/rss/tg24.xml` | RSS 2.0, UTF-8 | 100 | 100 | 16 | 324 | 41 su 100 (`skyit:article_text`) | 59 | 100 | **italiana** | sì |
| TGCom24 | `https://www.tgcom24.mediaset.it/rss/homepage.xml` | RSS 2.0, — | 30 | 30 | 3,6 | 148 | no | 0 | 30 | RFC 822 | ETag |
| Il Messaggero | `https://www.ilmessaggero.it/rss/home.xml` | RSS 2.0, **ISO-8859-1** | 20 | 20 | 22 | 182 | no | 0 | 20 | **italiana** | no |
| La Stampa | `https://www.lastampa.it/rss/copertina.xml` | RSS 2.0, UTF-8 | 73 | 43 | (voci vecchie in coda) | 168 | no | 71 | 73 | RFC 822 | LM |
| Open | `https://www.open.online/feed/` | RSS 2.0, UTF-8 | 12 | 12 | 2,4 | 328 | no | 0 | 12 | RFC 822 | sì |
| Agenzia Dire | `https://www.dire.it/feed/` | RSS 2.0, UTF-8 | 10 | 10 | 1,8 | 196 | sì (2,7k) | 10 | 10 | RFC 822 | sì |

### 1.2 Temi, locale, meteo, ragazzi

| Testata (tema) | Indirizzo | Formato | Voci | 24 h | Ore coperte | Sommario | Testo | Note |
|---|---|---|---|---|---|---|---|---|
| ANSA sport | `https://www.ansa.it/sito/notizie/sport/sport_rss.xml` | RSS 2.0 | 41 | 41 | 24 | 78 | no | |
| La Gazzetta dello Sport | `https://www.gazzetta.it/dynamic-feed/rss/section/last.xml` | RSS 2.0 | 30 | 30 | **2,5** | 158 | no | il più veloce |
| Corriere dello Sport, Tuttosport | `https://www.corrieredellosport.it/rss/calcio`, `https://www.tuttosport.com/rss/calcio` | RSS 2.0 | 30 | 30 | 15 | 126–139 | no | solo calcio |
| Rainews sport | `https://www.rainews.it/rss/sport` | RSS 2.0 | 41 | **2** | 557 | 139 | no | quasi fermo (come il 12/10) |
| ANSA economia, Adnkronos economia | (sopra), `https://www.adnkronos.com/RSS_Economia.xml` | RSS 2.0 | 20–58 | 20–58 | 21–24 | 69–133 | no | |
| Il Sole 24 Ore (Italia, Economia) | `https://www.ilsole24ore.com/rss/italia.xml`, `…/economia.xml` | RSS 2.0 | 12 | 9–12 | 6–25 | 179–200 | no | condizioni dubbie (§ 2) |
| ANSA tecnologia | `https://www.ansa.it/canale_tecnologia/notizie/tecnologia_rss.xml` | RSS 2.0 | 37 | 8 | 166 | 79 | no | lento |
| HDblog, Punto Informatico | `https://www.hdblog.it/feed/`, `https://www.punto-informatico.it/feed/` | RSS 2.0 | 20 | 20 | 3–5 | 129–249 | HDblog sì (1,7k) | |
| DDay | `https://www.dday.it/rss` | **Atom** | 50 | 14 | 120 | — (solo `content`, 206) | no | l'unico Atom |
| ANSA regionali (Lombardia, Lazio, Sicilia) | `https://www.ansa.it/<regione>/notizie/<regione>_rss.xml` | RSS 2.0 | 28–69 | 13–45 | 46–48 | 72–74 | no | una per regione |
| Il Giorno, MilanoToday (locale) | `https://www.ilgiorno.it/rss`, `https://www.milanotoday.it/rss` | RSS 2.0 | 100 / 25 | 100 / 25 | 9 / 4 | 131 / 108 | Il Giorno sì (2k) | esempio di una città |
| Protezione civile, bollettino di **vigilanza** meteo | `https://api.protezionecivile.it/default/dpcPortalGenerateRss?categoria=bollettino_vigilanza` | RSS 2.0 | 2 | 2 | — | **vuoto** | no | solo il titolo «Bollettino … del 13 ottobre 2026»; il contenuto è nel PDF del link; la voce è doppia |
| Protezione civile, bollettino di **criticità** | `…?categoria=bollettino_criticita` | RSS 2.0 | 2 | 2 | — | vuoto | no | idem, con l'ora |
| Protezione civile, notizie e comunicati | `…?categoria=notizia`, `…?categoria=comunicato_stampa` | RSS 2.0 | 100 | 0 | anni | 84–102 | no | ultima voce di 4 giorni prima; **ogni voce due volte**, anche in inglese |
| Aeronautica Militare (meteo) | `https://www.meteoam.it/it/rss` | RSS 2.0 | 156 | ? | ? | 172 | no | **nessuna data**; notizie dell'ente, non previsioni né avvisi |
| MeteoWeb | `https://www.meteoweb.eu/feed/` | RSS 2.0 | 30 | 30 | 8,5 | 382 | sì (2,9k) | testata privata, non un'allerta ufficiale |
| **Focus Junior** (ragazzi) | `https://www.focusjunior.it/feed/` | RSS 2.0 | 10 | 7 | 26 | 292 | sì (3,5k) | coda «The post … appeared first on Focus Junior» nel sommario; anche promozioni per le scuole |
| Focus, Le Scienze (scienza) | `https://www.focus.it/rss`, `https://www.lescienze.it/rss` | RSS 2.0 | 30 / 39 | 4 / ? | 115 / ? | 158 / 195 | Focus sì | Le Scienze **senza date** |
| Governo | `https://www.governo.it/it/rss.xml` | RSS 2.0 | 10 | 7 | 5,5 | 1 919 | no | voci ripetute, anche in inglese |

**Non funzionano o da non usare** (13/10): iLMeteo e 3bmeteo (nessun feed trovato: 404 o pagine
HTML), Rainews TGR regionale (`/rss/tgr/…`, 404), Rainews economia e tecnologia (404), ANSA scienza
(404), Popotus e Rai Scuola (404), Wired Italia (risponde, ma l'ultima voce è di **104 giorni** prima),
Fanpage (403 «Access Denied»), Il Fatto Quotidiano (il feed risponde, ma il `robots.txt` chiude
`/feed/` a tutti, come il 12/10). Il sito della Protezione civile (`/it/rss/`) è una pagina che si
costruisce in JavaScript: gli indirizzi veri dei feed (`api.protezionecivile.it`) si trovano solo nel
codice della pagina.

### 1.3 Osservazioni utili per il lettore

- **Formato**: tutti RSS 2.0 tranne DDay (Atom). Il lettore deve capire RSS 2.0 e Atom; RDF/RSS 1.0
  non serve. Rainews e ANSA cominciano con spazi prima di `<rss>` (accettati da Expat); Corriere e
  Gazzetta con `<!DOCTYPE xml>` (accettato anche da `defusedxml`, che vieta le entità, non il
  DOCTYPE). Lettura di un feed: 0,1–5 ms.
- **Encoding**: tutti UTF-8 tranne Il Messaggero (ISO-8859-1, dichiarato sia nell'XML sia
  nell'intestazione HTTP). Basta passare i **byte** al parser, mai una stringa decodificata a mano.
- **Date**: RFC 822 quasi ovunque, ISO 8601 nell'Atom. **Sky TG24** e **Il Messaggero** le scrivono in
  italiano (`mar, 13 ott 2026 13:10:00 GMT`), e **Sky TG24 scrive l'ora italiana con «GMT»**: 6 voci
  risultavano fino a 32 minuti **nel futuro**, e la voce più recente è di poco precedente al
  `Last-Modified` del server solo se letta come ora italiana (§ 1.4). Il
  lettore delle date italiane del 12/10 va completato con un **fuso per testata** nella
  configurazione dei feed (per Sky: `Europe/Rome`), e le date future vanno riportate ad adesso.
  Aeronautica Militare e Le Scienze **non hanno date**: si usa la data del primo scarico in cui la
  voce compare (e per la voce si dice «di recente», mai «oggi»).
- **Testo**: titolo + 1–2 frasi è la norma; AGI mette quasi l'articolo nel sommario (2 200
  caratteri, troncato a metà parola nel titolo: «…biglietti sopra i l...»); Sky TG24 dà il testo intero
  in un campo proprio per 41 voci su 100; Dire, HDblog, Il Giorno, MeteoWeb e Focus Junior in
  `content:encoded`. Si tiene l'inizio (600 caratteri, come il 12/10).
- **HTML e immagini**: HTML nel sommario in Il Post, AGI, Sky TG24, La Stampa, Punto Informatico,
  Dire, Focus Junior, Governo; immagini (enclosure o `media:content`) in quasi tutti tranne ANSA e
  Repubblica. Per la voce le immagini non servono; la scheda sugli schermi potrebbe mostrarle, ma
  sarebbe un carico verso il sito della testata a ogni visualizzazione (meglio di no).
- **Voci che non sono notizie**: episodi di podcast e newsletter del Post (`/episodes/`,
  `/newsletter/`), la striscia «Peanuts», le puntate dei TG di Rainews («Tg2 Medicina 33 del…»,
  «Puntata del…»): **19 voci su 2 304**, si riconoscono dal link e da poche forme chiuse. Attenzione:
  metà delle voci di Rainews (119 su 245) hanno un link `/video/` ma sono notizie vere.
- **Doppioni nella stessa testata**: 84 su 1 300 nelle ultime 36 ore (stessa voce in più sezioni);
  Protezione civile e Governo ripetono la stessa voce due o tre volte nello stesso feed.
- **Corriere**: le sezioni `dynamic-feed` mescolano le edizioni locali («Roma/Politica»,
  «Trentino/Politica»): 100 voci che coprono da 4 a 18 giorni, solo 8–28 delle ultime 24 ore. Per le
  notizie nazionali serve il filtro sulla categoria (senza «/»).
- **Il Post**: 44 voci su 90 senza sommario (le brevi, dove il titolo è già una frase intera: va bene
  così a voce).

### 1.4 Frequenza osservata (voci nuove tra le istantanee)

Tre istantanee a un'ora di distanza (14:40, 15:40, 16:40 ora italiana), voci nuove contate per link
[verificato, `nuove.py`]. La «finestra» è quante ore di notizie tiene il feed a quel ritmo (voci nel
feed diviso voci nuove all'ora): se è sotto le 2 ore, con lo scarico ogni 2 ore qualcosa si perde.

| Feed | Nuove all'ora | Voci nel feed | Finestra |
|---|---|---|---|
| **Adnkronos ultima ora** | **15** (20 nella prima ora: il feed era cambiato per intero) | 20 | **1,3 h** |
| Gazzetta «last» | 9 | 30 | 3,3 h |
| ANSA economia | 9 | 58 | 6 h |
| MilanoToday | 8,5 | 25 | 2,9 h |
| ANSA Lombardia | 7,5 | 69 | 9 h |
| AGI | 7 | 20 | 2,9 h |
| ANSA cronaca | 6,5 | 145 | 22 h |
| Rainews «tutti» | 6 | 40 | 6,7 h |
| **Open** | 5,5 | 12 | **2,2 h** |
| ANSA sport, Il Messaggero, ANSA Lazio | 5–5,5 | 20–41 | 4–7,5 h |
| HDblog, TGCom24, Dire | 3,5–4,5 | 10–30 | 2,9–8,6 h |
| ANSA ultima ora, top news; Repubblica; Il Post; Corriere dello Sport | 1,5–2,5 | 10–90 | 7–45 h |
| Corriere sezioni, Il Sole 24 Ore, Rainews esteri e cronaca | 0,5–1 | 12–100 | giorni |
| **Sky TG24** | **0** in due ore | 100 | — |
| Focus, Focus Junior, Governo, Aeronautica, Protezione civile, Rainews sport, Wired | 0–0,5 | | |

- **Adnkronos** cambia l'intero feed in poco più di un'ora: con lo scarico ogni 2 ore si perde circa
  un terzo delle sue voci. Non è grave (le agenzie si ripetono), ma per le fonti veloci conviene uno
  scarico **ogni ora finché qualcuno chiede notizie in giornata**, o accettare la perdita. Open è al
  limite.
- **Sky TG24 non si è mosso per oltre tre ore**: `Last-Modified` fermo a `11:17:34 GMT` (le 13:17
  italiane) dalle 14:40 alle 16:40, nessuna voce nuova. La sua voce più recente è datata «13:10 GMT»:
  sette minuti **prima** del `Last-Modified` solo se l'ora del feed è italiana. È la prova che Sky
  scrive l'**ora italiana con l'etichetta GMT** (a mezzogiorno UTC sei voci risultavano nel futuro).
  E un feed da 100 voci può restare fermo per ore di pomeriggio: non va considerato «rotto» subito.
- Il Post: nessuna voce nuova tra le 14:40 e le 15:40, 4 nell'ora dopo (CloudFront, cache di 1–7
  minuti).
- Di giorno i ritmi sono 2–3 volte quelli della notte di domenica misurati il 12/10 (Adnkronos 20
  voci in 7 ore allora, 20 in un'ora oggi).

## 2. Condizioni d'uso e `robots.txt`

Le condizioni del 12/10 restano valide (ANSA: «finalità d'informazione personale» con un lettore di
feed; Repubblica e Corriere: lettura con un aggregatore; Il Sole 24 Ore: riserva sul text and data
mining e sull'uso per «alimentare» sistemi di IA). Le novità di oggi:

| Fonte | Cosa dice | Per Calliope |
|---|---|---|
| **Il Post** | condizioni generali: i servizi si usano «esclusivamente a scopo personale»; «Qualsiasi copia, distribuzione, modifica ed elaborazione dei contenuti e dei Servizi è proibita»; nessuna riga sui feed né sull'IA [verificato, ilpost.it/condizioni-generali, 13/10]. `robots.txt`: `/feed` permesso a tutti, chiusi solo GPTBot e PerplexityBot [verificato] | **dubbio** come Il Sole: leggere il feed per sé è l'uso previsto, ma un modello che riassume è un'«elaborazione». Da decidere (§ 7) |
| **Protezione civile** | contenuti del sito con licenza **CC BY 4.0**, con la fonte «Sito del Dipartimento della Protezione Civile - Presidenza del Consiglio dei Ministri» [di seconda mano: risultato di ricerca sulla pagina «Note legali», che il 13/10 rispondeva 404 al download diretto]. `robots.txt` di `api.protezionecivile.it`: 503 | **sì**, dicendo la fonte |
| **Il Messaggero** | nel feed: «Copyright 2026 Il Messaggero S.P.A. – FOR PERSONAL USE ONLY» [verificato] | sì per uso personale; il `robots.txt` chiude anche `Claude-User` e `ChatGPT-User` |
| **Focus Junior, Focus** (Mondadori) | nessuna condizione sui feed trovata; `robots.txt` chiude GPTBot, ClaudeBot, anthropic-ai, PerplexityBot, CCBot [verificato] | sì come lettore, stesso segnale delle testate grandi |
| Aeronautica Militare, MeteoWeb, Dire, DDay, Sky TG24, TGCom24, AGI, Adnkronos | nessuna condizione trovata per i feed; `robots.txt` senza chiusure per gli agenti IA (DDay solo GPTBot) [verificato] | sì, con la fonte detta |

**Lettura a voce in casa.** Nessuna delle condizioni lette vieta di **ascoltare** un titolo letto da
un programma: il caso previsto dai fornitori è il «reader» personale, e Calliope lo è (in casa, per
chi abita lì, senza ripubblicare). Le due zone grigie sono le stesse del 12/10, ora con un nome in più:
(a) il **riassunto fatto da un modello** (Il Sole 24 Ore lo esclude per il text and data mining, Il
Post vieta l'«elaborazione»); (b) i `robots.txt` che chiudono gli **agenti delle aziende di IA**
(ANSA, Rainews, Corriere, Repubblica, Il Messaggero, Focus: Calliope non è nessuno di loro, ma il
segnale è chiaro). Mitigazione proposta: per le testate in zona grigia Calliope **legge il titolo e
il sommario così come sono** (una conversione, non un riassunto), dicendo la testata; il riassunto
del modello solo per le fonti senza riserve. Non è un parere legale.

`robots.txt` [verificato con `urllib.robotparser`, 13/10]: **tutti** i feed raccomandati sono
permessi a `*` e a un agente `Calliope`. Chiusi agli agenti IA con nome: ANSA e Rainews (7 agenti su
8, non `Claude-User`), Corriere e Il Sole (6), Il Messaggero (tutti e 8), Repubblica e La Stampa (5),
MilanoToday (7), Il Giorno (3), Gazzetta (4); nessuna chiusura per AGI, Adnkronos, Sky TG24, TGCom24,
Open, Dire, Corriere dello Sport, Tuttosport, HDblog, Punto Informatico, Governo, Aeronautica Militare,
MeteoWeb.

**Paywall.** Nei feed non c'è nessun segno dell'abbonamento (né categoria né percorso del link:
cercati `/rep/`, `premium`, `plus`, `abbonati`): il titolo e il sommario sono liberi anche quando
l'articolo è a pagamento. Per Calliope non cambia niente, perché **non apre mai l'articolo** (niente
scraping): «dimmi di più» risponde con ciò che hanno scritto le altre testate sullo stesso fatto
(§ 3.2), oppure con la ricerca su internet che c'è già.

## 3. Come si legge una notizia a voce

Il testo dei feed non va al TTS così com'è: va al **modello** dentro la busta di `web_cerca` (§ 6.6),
che ne fa 1–3 frasi (principio 5). La pulizia serve a dare al modello titoli già «dicibili», e a una
eventuale lettura senza modello (§ 6.4). Misure su 2 304 voci dell'istantanea delle 14:40 [verificato].

### 3.1 Titoli puliti

Cosa c'è nei titoli (`titoli.py`), in ordine di frequenza:

| Forma | Voci | Testate | Cosa farne |
|---|---|---|---|
| «Tema: …» o «Persona: 'citazione'» | 639 (28 %) | tutte, ANSA soprattutto | **lasciare**: a voce «Manovra: …» si dice con una pausa, il modello lo rigira |
| virgolette dritte `"…"` | 181 (8 %) | Rainews, Il Giorno, Sky TG24 | uniformare a «» (una forma sola nel testo dato al modello) |
| virgolette basse «» | 158 (7 %) | Corriere quasi solo | già giuste |
| apici come virgolette `'…'` | 112 (5 %) | ANSA (102) | convertire in «» solo a parola intera, mai l'apostrofo («dell'Irpef») |
| virgolette curve “” | 83 (4 %) | La Stampa, Il Giorno, Repubblica | uniformare |
| sigle e parole tutte maiuscole | 42 (2 %) oltre le sigle comuni | Protezione civile, Aeronautica, DDay, HDblog | lasciare (FIAT, ILVA, OPPO): è un problema di pronuncia di Piper, già fuori da questo lavoro |
| marcatori VIDEO, FOTO, LIVE, «IL VIDEO» | **12 (0,5 %)** | Sky TG24 (6), Rainews, Adnkronos, ANSA | togliere in fondo o in testa, mai in mezzo |
| titolo troncato «…» o «...» | 6 | AGI (a metà parola), Tuttosport (voluto) | AGI: prendere la prima frase del sommario al posto del titolo |
| «++ … ++» e «>ANSA-FOCUS/» (marcature d'agenzia) | 5 | ANSA | togliere |
| due titoli con « \| » | 8 | Corriere, TGCom24 | Corriere «…le notizie in diretta \| Fatto»: tenere **la seconda** parte (il fatto); TGCom24: la prima |
| numeri con % e € | 44 | ANSA | lasciare: li converte già il modello |
| emoji | 0 | — | — |

Il prototipo (`pulizia.py`, cinque espressioni regolari e le virgolette) cambia **381 titoli su 2 304
(17 %)**, quasi tutti per le virgolette. Il resto (marcatori, agenzia, troncati) è sotto l'1 %: il
problema dei titoli «urlati» che ci si poteva aspettare (VIDEO, FOTO, LIVE in maiuscolo) **nei feed
italiani quasi non c'è** [verificato]. Sono conversioni della forma (principio 10): ognuna con i
suoi casi contrari («Il video del ministro» resta, «Live Aid» resta).

Lunghezza dei titoli: mediana 60–90 caratteri, più lunghi Open (126), Il Messaggero (111) e Corriere
(100, fino a 226). A voce un titolo di 100 caratteri dura ~6 s con Piper [stima]: per tre notizie in una
risposta conviene il titolo più corto del gruppo (§ 3.2), non quello della testata più verbosa.

Sommari: in 30 voci (WordPress: Focus Junior, Punto Informatico, MeteoWeb) c'è la coda «The post …
appeared first on …», da togliere; 16 cominciano con la sigla dell'agenzia («AGI - »); 16 ripetono il
titolo. 195 voci non hanno sommario.

### 3.2 La stessa notizia da più testate: raggruppare senza modello

Domanda: la stessa notizia data da 4–13 testate si può riconoscere con la sola similarità dei testi?
Prova sulle 1 222 voci di notizie (generali, temi e locale; esclusi meteo, istituzionali, scienza e
ragazzi) delle ultime 36 ore, dopo aver tolto i doppioni nella stessa testata. Si collegano solo voci
di **testate diverse** a meno di 24 ore l'una dall'altra; i gruppi si formano per unione (legame
singolo). Radici: le prime 6 lettere della parola senza accenti, senza parole vuote.

| Metodo | Gruppi con ≥ 2 testate | ≥ 3 testate | Gruppo più grande | Giusti a mano (campione) | Tempo |
|---|---|---|---|---|---|
| Jaccard sulle radici del titolo (o di titolo + 200 caratteri del sommario), soglia 0,35 | 73 | 32 | 26 voci | 24 su 25 | < 1 s |
| **TF-IDF coseno, titolo + 200 caratteri, soglia 0,30** | **86** | **44** | 30 voci | **19–20 su 20** | 1,1 s |
| TF-IDF coseno, soglia 0,22 | 97 | 51 | **65 voci** (tre fatti diversi incatenati) | 16 su 20 | 1,1 s |

Note dal controllo a mano:

- Con 0,30 i gruppi sbagliati non ci sono; i dubbi sono **stesso tema, angolo diverso** (una
  sconfitta di un tennista e la polemica sulle palline dello stesso torneo; un articolo «cos'è un
  nodulo al polmone» nel gruppo del ricovero di una persona pubblica). A voce va bene: è «lo stesso
  argomento».
- Il **legame singolo incatena**: sotto 0,25 un fatto di politica estera, un salvataggio in una grotta
  e un attacco con droni finiscono in un gruppo di 65 voci; coppie false come «Le previsioni del tempo
  per martedì» con l'annuncio di un videogioco. Serve un **tetto** (per esempio: una voce entra nel
  gruppo solo se è simile ad almeno metà delle voci già dentro, o al centroide) oppure la soglia 0,30.
- Ciò che resta fuori sono gli **sviluppi**: sulla vertenza di un'acciaieria, 8 voci su 12 restano da
  sole con Jaccard e 4 con TF-IDF (titoli come «al via la mobilitazione», «atteso il CdM»). Sul
  ricovero di una persona pubblica, 18 voci da sole con Jaccard, 12 con TF-IDF 0,30 (retroscena,
  sicurezza, agenda). Per il racconto a voce non è grave: il gruppo principale c'è sempre.
- Costo: confronti a coppie, O(n²); 1,1 s di CPU per 1 222 voci in Python puro sul portatile. Ogni 2
  ore è trascurabile; per stare larghi si confrontano solo le voci delle ultime 36 ore, e si
  ricalcolano solo i gruppi con voci nuove.

**Quando serve il modello.** Non per formare i gruppi: per (a) dire un gruppo in **una frase**
mettendo insieme i sommari di più testate; (b) scegliere, tra tre fatti con lo stesso numero di
testate, quale dire per primo, se si vuole qualcosa di meglio di «quante testate e quanto recente»;
(c) gli **sviluppi** dello stesso fatto in giorni diversi («novità sul caso di ieri»). Un modello di
embedding (che girerebbe sulla GPU, accanto alla voce) migliorerebbe c), ma con 8 GB di VRAM non vale
il posto: TF-IDF basta per a) e b) [stima].

**Ordine dei fatti** per «le notizie di oggi»: numero di testate distinte nel gruppo (un fatto dato da
12 testate è «la notizia»), poi la voce più recente. Nella prova delle 14:40 i primi cinque per
testate erano: un ricovero in ospedale di una persona pubblica (13–15 testate), un caso giudiziario di
una parlamentare europea (12), un attacco a navi nel Mar Nero (7–8), un caso di cronaca nel Milanese
(7), la morte di un attore (6). È esattamente l'apertura dei notiziari del giorno.

### 3.3 Notizie vecchie

- Le date ci sono (tranne Aeronautica Militare e Le Scienze), ma con i due difetti del § 1.3 (date in
  italiano, Sky TG24 con l'ora italiana marcata GMT).
- Un feed «copre» da **2 ore** (Adnkronos, Gazzetta, Dire, AGI, Open nelle ore di punta) a **2–18
  giorni** (Corriere, Rainews politica e sport, ANSA tecnologia). Per «le notizie di oggi» si usano
  solo le voci delle **ultime 24 ore**; una voce di più di 3 giorni ha `vecchio` come in `web_cerca`,
  e a voce si dice la data («sabato», «la settimana scorsa»).
- **Feed fermi**: Wired (104 giorni), Rainews sport (13 ore di giorno, già quasi fermo il 12/10),
  Protezione civile notizie (4 giorni, ma pubblica poco). Il controllo dell'età dell'ultima voce,
  proposto il 12/10, va fatto per feed e con una soglia **per tema** (una testata sportiva ferma da
  12 ore di giorno è rotta; la Protezione civile ferma da 4 giorni no).
- **Allerte**: un bollettino di criticità «del 12 ottobre ore 14:43» letto il 13 è già vecchio; il
  bollettino si dice solo con data e ora («l'ultimo bollettino della Protezione civile, di ieri alle
  14:43, …»), e il contenuto vero sta nel PDF, che Calliope non scarica: a voce si dice **che c'è** e
  dove guardarlo. Per «c'è un'allerta qui?» la fonte giusta resta la regione o Home Assistant.

## 4. Copertura: quanti feed bastano

Prova sull'istantanea delle 14:40, ultime 24 ore, gruppi TF-IDF 0,30 [verificato]. «Fatto del
giorno» = gruppo dato da almeno 3 testate (41 fatti); «fatto grande» = almeno 5 testate (11).

| Feed | Fatti del giorno coperti | Fatti grandi | Voci nel periodo |
|---|---|---|---|
| ANSA ultima ora + top news | 13 / 41 (32 %) | 7 / 11 | 27 |
| ANSA, tutte le sezioni nazionali | 27 / 41 (66 %) | 10 / 11 | 221 |
| Rainews (tutti) | 11 / 41 (27 %) | 7 / 11 | 40 |
| Il Post | 14 / 41 (34 %) | 6 / 11 | 50 |
| Sky TG24 | 24 / 41 (59 %) | **11 / 11** | 98 |
| la Repubblica | 9 / 41 (22 %) | 6 / 11 | 30 |
| AGI | 7 / 41 (17 %) | 6 / 11 | 20 |
| ANSA ultima+top, Rainews, Il Post | 24 / 41 (59 %) | 10 / 11 | 117 |
| **ANSA ultima+top, Rainews, Il Post, Sky TG24** | **31 / 41 (76 %)** | **11 / 11** | 215 |
| ANSA sezioni, Rainews, Il Post, Sky TG24 | 32 / 41 (78 %) | 11 / 11 | 362 |
| ANSA ultima+top, Rainews, Repubblica, AGI | 20 / 41 (49 %) | 9 / 11 | 117 |

Attenzione: è **una** istantanea. I feed con poche ore dentro (Rainews «tutti» 6 h, AGI 3 h,
Adnkronos 2 h) in un indice che accumula le voci ogni 2 ore coprono molto di più di quanto dica la
tabella. Rifatto sulle **tre istantanee unite** (come un indice che accumula, 14:40–16:40): 51 fatti
del giorno e 17 grandi; i quattro feed ne coprono **30 su 51 (59 %)** e **16 grandi su 17** (manca
una squalifica di Serie A, data solo da testate sportive e agenzie). Sull'ultima istantanea da sola:
25 su 41 e 12 su 13. La quota dei fatti di seconda fila oscilla (59–76 %), quella dei fatti grandi
no (94–100 %). Pesa anche Sky TG24 fermo dalle 13:17 (§ 1.4): un feed generale che si ferma toglie
fino a un quarto della copertura, per questo ne servono almeno tre o quattro.

I fatti mancati dai quattro feed sono di seconda fila: un incidente in un parco divertimenti
all'estero, una partita di Champions della sera, un'udienza in un processo storico, un premio a un
allenatore, un'esposizione di moto, un caso giudiziario di cronaca.

**Cosa non coprono i generali** (stesso calcolo, «nei generali» = ANSA ultima ora e top news,
Rainews, Il Post, Sky TG24, Repubblica, AGI):

| Tema | Fatti dai feed del tema | Anche nei generali |
|---|---|---|
| Sport (ANSA sport, Gazzetta, Corriere dello Sport, Tuttosport) | 123 | 6 (**5 %**) |
| Locale, Lombardia (ANSA Lombardia, Il Giorno, MilanoToday) | 147 | 3 (**2 %**) |
| ANSA Lazio, ANSA Sicilia | 12, 10 | 2, 1 |
| Tecnologia (ANSA tecnologia, HDblog, Punto Informatico, DDay) | 56 | 3 (5 %) |
| Economia (ANSA ed Adnkronos economia, Il Sole) | 85 | 7 (8 %) |

**Conclusione.** Per «che notizie ci sono?» bastano **3–4 feed generali** (ANSA ultima ora e top
news, Rainews, Il Post, Sky TG24): i fatti grandi del giorno ci sono quasi tutti (94–100 %). Per «notizie di sport»,
«di tecnologia», «di economia» e «della mia zona» servono i **feed del tema**, perché i generali ne
portano il 2–8 %. Lo sport poi va su più testate (Gazzetta per tutto, ANSA sport, una tra Corriere
dello Sport e Tuttosport per il calcio). Il locale vuol dire una **regione ANSA** (ce n'è una per
regione, stesso formato) più, a mano, una testata della città.

## 5. Librerie e sicurezza dell'XML

### 5.1 feedparser

feedparser **6.0.14** (30/07/2026), BSD-2-Clause, Python ≥ 3.10, una ruota sola
`py3-none-any` (quindi win_amd64, **win_arm64** e **aarch64** senza compilare), una dipendenza:
feedparser-sgmllib 2.1.0 (02/08/2026, PSF-2.0, anch'essa `py3-none-any`) [verificato su PyPI, 13/10].
Pro: legge anche i feed rotti, normalizza RSS, Atom e RDF, ripulisce l'HTML. Contro: non legge le
date italiane né il fuso di Sky TG24 (serve comunque un gestore); va usato **solo su byte già
scaricati** (con un URL farebbe da sé le richieste HTTP); una dipendenza in più in
`TERZE-PARTI.md`. Il 12/10 non ha segnato nessun feed «bozo» su 41; oggi `defusedxml` ha letto senza
errori 52 feed su 52: la robustezza di feedparser non serve con questi feed.

### 5.2 Libreria standard e defusedxml

`xmlsicuro.py`, con Expat 2.8.1 (Python 3.14.6 del portatile) [verificato]:

| XML ostile (sintetico) | `xml.etree.ElementTree` | `defusedxml.ElementTree` |
|---|---|---|
| entità interna innocua | letta | **rifiutata** (`EntitiesForbidden`) |
| «billion laughs» (10⁹ caratteri) | rifiutato da Expat dopo 102 ms («limit on input amplification factor») | rifiutato subito (0,1 ms) |
| entità esterna verso un file | non risolta (errore) | rifiutata |
| DTD esterna (`SYSTEM "http://…"`) | letta, **senza** scaricarla | letta, senza scaricarla |
| `<!DOCTYPE xml>` come Corriere e Gazzetta | letta | letta |

La documentazione di Python avverte che **Expat prima della 2.7.2** può essere vulnerabile a
«billion laughs», «quadratic blowup» e «large tokens» [verificato, docs.python.org/3/library/xml.html,
13/10]. Sulla DGX il Python di sistema (3.12) ha Expat **2.6.1** [di seconda mano: misura del 12/10,
non rifatta per non toccare la DGX]: lì la difesa di Expat non basta.

defusedxml **0.7.1** (marzo 2021; 0.8.0rc2 del 2023 mai uscita), PSF, puro Python, `py2.py3-none-any`
[verificato su PyPI]: fa una cosa sola (vieta le entità e le DTD con entità) ed è ferma da anni.

**Proposta**: libreria standard con **tre difese in poche righe**, senza dipendenze nuove:
1. tetto di dimensione (2 MB letti, come il 12/10: il feed più grande oggi è Il Giorno con 379 kB, la
   Protezione civile «notizia» 51 kB) e `Accept-Encoding: identity` (niente bombe di decompressione);
2. **rifiuto del feed** se i primi kB contengono `<!ENTITY` (quello che fa `defusedxml`: nessun feed
   vero ne ha);
3. parser senza risoluzione delle entità esterne (ElementTree già non le risolve).
In alternativa `defusedxml` (puro Python, nessun problema su ARM): stesso effetto, una riga in
`TERZE-PARTI.md`. Va bene anche questa; la prima evita una dipendenza ferma dal 2021.

Il **contenuto** resta non fidato anche dopo il parser: titoli e sommari passano da
`ripulisci_testo` (`calliope/web/servizio.py`) ed entrano nella busta come i risultati di SearXNG
(§ 6.6).

## 6. Proposta per Calliope

Base: il progetto del 12/10 (indice SQLite con FTS5 e radici, conservazione 7 giorni, scarico ogni 2
ore solo se qualcuno ha chiesto notizie negli ultimi 7 giorni, richieste condizionate, 6 in parallelo,
User-Agent onesto, rispetto del `robots.txt`, niente pagine degli articoli). Cosa cambia o si aggiunge
dopo le misure di oggi.

### 6.1 Allo scarico (sulla DGX, CPU, ogni 2 ore)

1. Scarico condizionato e lettura (§ 5.2); data con fuso per testata; voci non notizie scartate
   (podcast, newsletter, rubriche: link e forme chiuse); titolo pulito (§ 3.1) salvato **accanto** al
   titolo originale (la scheda mostra l'originale).
2. Doppioni nella stessa testata (link o titolo).
3. **Raggruppamento** TF-IDF 0,30 con tetto contro le catene (§ 3.2) sulle voci delle ultime 36 ore:
   ogni voce ha un `fatto` (id del gruppo). Per ogni fatto: numero di testate, voce più recente,
   titolo più corto tra quelli puliti, temi. ~1 s di CPU.
4. Età dell'ultima voce per feed, soglia per tema; «fermo» nel registro delle capacità e nel
   cruscotto (Sky TG24 fermo tre ore di pomeriggio non è rotto: la soglia va in giorni per i feed
   grandi, in ore solo per quelli veloci).
5. Ritmo: ogni 2 ore come deciso il 12/10; i feed con finestra sotto le 2 ore (Adnkronos, Open, §
   1.4) perdono voci. Proposta: per loro **ogni ora**, solo nei giorni in cui qualcuno ha chiesto
   notizie, oppure accettare la perdita (le agenzie si ripetono). Richieste condizionate provate alle
   16:45 [verificato]: **19 feed rispondono 304** senza corpo (Rainews, Il Post, Il Sole, Sky TG24,
   La Stampa, Open, Dire, Punto Informatico, Il Giorno, Governo, Focus, Focus Junior, Le Scienze);
   AGI, Adnkronos, TGCom24, Corriere dello Sport, Tuttosport, HDblog, DDay, Aeronautica e MeteoWeb
   mandano ETag o Last-Modified ma rispondono sempre per intero (Aeronautica anche se non cambia
   mai); ANSA, Repubblica, Corriere, Gazzetta, Il Messaggero non li mandano. Uno scarico completo è
   ~3,4 MB per i 52 feed provati (1,8 MB per i 28 del 12/10); l'elenco di serie del § 6.2 ne pesa
   circa la metà.
6. Durante le prove una richiesta è fallita una volta per un certificato TLS scaduto, poi non più
   (un nodo della rete di distribuzione, probabilmente): un feed che fallisce si salta e si riprova
   al giro dopo, **mai** disattivare la verifica del certificato.

Tempo totale stimato: ~1 s di rete in parallelo + ~1,5 s di CPU ogni 2 ore. Nessuna GPU: uguale nel
profilo da 8 GB.

### 6.2 Feed predefiniti (file d'esempio) e locali

Nel file d'esempio (`notizie_feed`, generato dai commenti di `Config`), solo fonti nazionali, ognuna
con testata, tema e fuso:

| Tema | Feed di serie |
|---|---|
| generale | ANSA ultima ora, ANSA top news, Rainews «tutti», Sky TG24 (fuso `Europe/Rome`), AGI, Adnkronos ultima ora |
| generale, in zona grigia (§ 2) | Il Post, Il Sole 24 Ore: **spenti** di serie, si accendono nel locale con una riga |
| sport | Gazzetta «last», ANSA sport, Corriere dello Sport calcio |
| economia | ANSA economia, Adnkronos economia |
| tecnologia | HDblog, Punto Informatico, ANSA tecnologia |
| allerta | Protezione civile, bollettino di vigilanza e di criticità (solo per dire che c'è e di quando) |

Nel **locale** (`calliope.locale.yaml`): la **regione ANSA** di casa (proposta: suggerita da
`casa_citta` nel setup, scritta da chi amministra, mai indovinata a ogni avvio), una testata della
città, i feed in zona grigia se chi amministra li vuole, e un eventuale feed per i ragazzi (§ 6.7).
Da non mettere da nessuna parte: Wired (fermo), Rainews sport (quasi fermo), Aeronautica Militare
(niente date, niente avvisi), Protezione civile «notizie» (rara e doppia), Corriere senza il filtro
delle edizioni locali.

### 6.3 Il tool: `notizie`, di sola lettura

Il 12/10 la proposta era una fonte dentro `web_cerca` senza tool nuovi. Le misure di oggi spostano la
bilancia verso un **tool proprio**, per due motivi: il risultato non è più una lista di pagine ma una
lista di **fatti** (con quante e quali testate), e il seguito «dimmi di più sulla seconda» ha bisogno
di un riferimento stabile al fatto, che dal disco si risolve senza internet.

`notizie(tema?, fatto?)`, lettura, permesso familiare (ospite da decidere):
- senza argomenti: i 3 fatti più grandi delle ultime 24 ore dai feed generali, numerati;
- `tema`: «sport», «economia», «tecnologia», «locale», oppure una parola libera («Juventus»,
  «Ucraina»), cercata nell'indice FTS5 con le radici; i fatti che la contengono;
- `fatto` (il numero detto prima, o l'id): tutte le voci del gruppo, una per testata, con sommario,
  testata e quando.

Il risultato dice per ogni fatto: numero, titolo pulito, sommario di una testata, testate (nomi
dalla configurazione), quando in parole, `vecchio`. È in busta (§ 6.6). L'elenco numerato dell'ultima
chiamata resta nei dati del turno per due turni (come `RICERCA_MSG` per le ricerche), così «la
seconda» si risolve. **`web_cerca` tipo notizie** resta: passa all'indice quando c'è, e SearXNG
resta il ripiego come proposto il 12/10 (meno di 2 voci sul tema in 72 ore, indice vecchio, scarico
fermo). Gli schemi passano da 77 a 78; in alternativa si toglie il tipo «notizie» da `web_cerca` e
restano 77 (decisione di chi amministra, § 7).

### 6.4 Cosa si dice

Esempi (testate e fatti inventati, forma vera):

- «**Che notizie ci sono?**» → `notizie()` → «Tre notizie di oggi. Il ministro dell'economia ha
  presentato il documento di bilancio alla Camera, secondo l'ANSA e altre otto testate. A Genova un
  peschereccio è stato soccorso al largo, lo riporta Rainews. E Sky TG24 dice che domani c'è sciopero
  dei treni. Vuoi saperne di più su una?» Tre frasi corte più una domanda; la testata detta una volta
  per fatto; mai l'indirizzo.
  - Variante **senza modello** (corsia veloce): la stessa risposta montata dal codice con i titoli
    puliti («Prima: …. Seconda: …. Terza: ….») risparmierebbe il secondo giro del modello (~0,5–1 s, [stima]).
    È una conversione della forma (principio 10), ma i titoli scritti per l'occhio a voce suonano
    peggio di una frase del modello: da provare all'ascolto prima di sceglierla.
- «**Notizie di sport**» → `notizie(tema="sport")` → i 3 fatti sportivi più dati, risultati
  compresi; se ci sono solo voci vecchie, con la data.
- «**Dimmi di più sulla seconda**» → `notizie(fatto=2)` → 2–3 frasi dai sommari di tutte le testate
  del gruppo («Secondo Rainews …; l'ANSA aggiunge che …»). Se il gruppo ha una voce sola e un
  sommario corto: «Il titolo dice soltanto questo; posso cercare su internet» (e la ricerca c'è già).
- «**Ci sono allerte meteo?**» → bollettini della Protezione civile con data e ora, più il meteo di
  casa (decisione 0024) se c'è.
- **Mai la stessa notizia due volte** nella stessa conversazione senza dirlo: il tool sa quali fatti ha
  già dato (dati del turno) e li mette in fondo con `gia_detto`.

### 6.5 Registro e misure

Regole nel registro dei turni: `notizie_feed`, `notizie_ripiego`, `notizie_seguito` (numero
risolto). Da guardare: quota delle risposte dall'indice, età della notizia più recente detta,
quante volte «dimmi di più» trova più di una testata, feed fermi, durata dello scarico e del
raggruppamento.

### 6.6 Sicurezza

Come il 12/10: busta di `web_cerca` (`attenzione`, `non_fidato`), provenienza «web» per la politica
per valore, `DOPO_DATO` (dopo un risultato, nella stessa risposta, solo letture), `ripulisci_testo`
su titoli e sommari, nessun link aperto. In più: il raggruppamento non deve permettere a una testata
di «parlare per» le altre (ogni voce mantiene la sua testata; il modello cita chi ha scritto cosa), e
un titolo con un'istruzione dentro resta un dato (caso già provato per SearXNG, 0 azioni su 8).

### 6.7 Minori e ragazzi

Oggi `web_cerca` è chiuso ai minori. Per i feed generali la cronaca del giorno (nella prova: un
neonato abbandonato, una violenza domestica, un avvelenamento) non è adatta senza filtro. Un feed per
ragazzi esiste e funziona (**Focus Junior**: 10 voci, ~7 al giorno, sommari di 300 caratteri,
argomenti adatti), ma mescola notizie e promozioni per le scuole, e il `robots.txt` di Mondadori chiude
gli agenti IA. Proposta: chiuso ai minori come oggi; se chi amministra apre, solo Focus Junior e lo
sport, con `filtra_per_minore`.

### 6.8 Rischi

| Rischio | Quanto | Mitigazione |
|---|---|---|
| condizioni d'uso (riassunto da un modello, agenti IA nei `robots.txt`) | medio, legale | lettore personale, nessuna ripubblicazione, testata detta, zona grigia spenta di serie, lettura del titolo e sommario così come sono per quelle testate |
| feed che cambiano indirizzo o si fermano (Wired, Rainews sport, Corriere vecchio, Il Post con la barra) | alto nel tempo | controllo dell'età per feed, capacità «degradata», mai togliere da solo |
| date sbagliate (fuso di Sky, date in italiano, senza data) | medio | fuso per testata, date future riportate ad adesso, «di recente» senza data |
| gruppi sbagliati (catene) | basso con 0,30 e il tetto | prove con casi contrari (due fatti con parole comuni) |
| notizia vecchia detta come nuova | medio | solo 24 ore per «oggi», `vecchio` oltre 3 giorni, data detta |
| cronaca dura a un minore o a un ospite | medio | chiuso ai minori; per l'ospite da decidere |
| contenuto ostile nei titoli | basso | busta, `ripulisci_testo`, `DOPO_DATO` |
| latenza | basso | lettura dal disco (0,04 ms la ricerca il 12/10); solo il giro del modello |
| privacy | migliora | nessuna domanda esce: lo scarico è uguale per tutte le case |

## 7. Domande per chi amministra

Restano aperte le cinque del 12/10 (testate e IA, regione di casa, minori, attesa alla prima
richiesta, lettore). In più:

1. **Il Post** e **Il Sole 24 Ore** (zona grigia: «elaborazione» e text and data mining): spenti di
   serie e accesi a mano nel locale, oppure fuori del tutto?
2. **Tool nuovo** `notizie` (78 schemi) o tipo «notizie» di `web_cerca` sostituito (77)?
3. **Lettura senza modello** delle tre notizie (più veloce, meno naturale): da provare all'ascolto?
4. **Ospiti**: possono chiedere le notizie (oggi `web_cerca` sì)?
5. **Lettore**: libreria standard con il rifiuto di `<!ENTITY` (proposta) o `defusedxml`?

## Fonti (consultate il 13/10/2026)

- Feed scaricati il 13/10 alle 14:40, 15:40 e 16:40 dagli indirizzi delle tabelle del § 1; `robots.txt`
  dei relativi siti letti con `urllib.robotparser`.
- Protezione civile, pagina dei feed RSS: <https://www.protezionecivile.gov.it/it/rss/> (indirizzi dei
  feed nel codice JavaScript della pagina); note legali (CC BY 4.0, di seconda mano):
  <https://www.protezionecivile.gov.it/en/approfondimento/note-legali/>
- Il Post, condizioni generali: <https://www.ilpost.it/condizioni-generali/>; `robots.txt`:
  <https://www.ilpost.it/robots.txt>
- Python, «XML processing modules», vulnerabilità e versioni di Expat:
  <https://docs.python.org/3/library/xml.html>
- PyPI: feedparser <https://pypi.org/project/feedparser/> (6.0.14), feedparser-sgmllib
  <https://pypi.org/project/feedparser-sgmllib/> (2.1.0), defusedxml
  <https://pypi.org/project/defusedxml/> (0.7.1)
- Interni: [`2026-10-12-notizie-rss.md`](2026-10-12-notizie-rss.md) (condizioni di ANSA, Repubblica,
  Corriere, Il Sole 24 Ore; misure di notte; indice), [`2026-10-03-ricerca-web.md`](2026-10-03-ricerca-web.md),
  [biblioteca](../aree/biblioteca.md), [sicurezza-politica](../aree/sicurezza-politica.md),
  decisioni [0021](../decisioni/0021-ricerca-web-searxng.md) e
  [0024](../decisioni/0024-niente-internet-se-non-serve.md)
