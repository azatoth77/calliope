# Notizie dai feed RSS delle testate italiane (12/10/2026)

Domanda: le notizie possono arrivare dai feed RSS delle testate, scaricati in un indice locale, invece
che da SearXNG a ogni domanda? Quali feed, con quali condizioni, quanto rispondono, e come si
costruisce la funzione senza tradire la decisione [0024](../decisioni/0024-niente-internet-se-non-serve.md)
(«niente internet quando se ne può fare a meno»)? Punto 7 della [roadmap](../roadmap.md), approfondito
dopo il rapporto di prontezza (B, § 2).

**Decisione già presa da chi amministra (12/10)**: prima questa ricerca; poi uno scarico dei feed
**ogni 2 ore, solo se negli ultimi 7 giorni qualcuno ha chiesto notizie** (il compromesso con la 0024).

**Risposta breve: sì.** 28 feed di 15 testate si scaricano in **0,7–1,1 s** (6 in parallelo, 1,8 MB),
si leggono e si indicizzano in meno di un secondo di CPU, e una ricerca nell'indice costa **0,04 ms** di
mediana (SearXNG: 0,5–3 s, sulla DGX). Su 22 domande di notizie realistiche l'indice risponde bene a
**15**, in parte a **4**, per niente a **3** (borsa a mercati chiusi, scioperi, un tennista che non
gioca). La domanda non esce più di casa: esce solo lo scarico, uguale per tutti. Serve poco codice,
**nessuna dipendenza nuova** (tutti i feed provati sono RSS 2.0 ben formati e si leggono con la libreria
standard), e la funzione si comporta uguale nel profilo da 8 GB di VRAM (non usa la GPU). SearXNG resta
il ripiego. Da decidere: quali testate di serie (le condizioni d'uso dicono «uso personale», e molte
testate chiudono i `robots.txt` agli agenti delle IA), e se i minori sentono le notizie.

Script di misura (fuori dal repository, nella cartella di lavoro di questa ricerca): `sonda.py`
(scarica e misura ogni feed), `robots.py` (permessi di `robots.txt`), `misura.py` (indice FTS5 e
domande), `extra.py`, `parallelo.py`, `et.py` (lettura con `xml.etree`). Misure fatte dal portatile
nella notte tra domenica 11 e lunedì 12/10: di notte e nel fine settimana i feed corrono meno, e i
numeri di frequenza qui sotto sono un minimo.

## 1. I feed: quali funzionano oggi

Provati 47 indirizzi di 25 testate (agenzie, quotidiani nazionali, TV, economia, sport, tecnologia,
locali, istituzionali). Tutti i feed funzionanti sono **RSS 2.0** (nessun Atom). Colonne: voci nel
feed, voci delle ultime 24 ore, ore coperte tra la voce più nuova e la più vecchia, caratteri del
sommario (mediana), se c'è il testo intero (`content:encoded`), se il server risponde 304 a una
richiesta condizionata (ETag o Last-Modified).

| Testata (tema) | Indirizzo | Voci | 24 h | Copre | Sommario | Testo intero | 304 |
|---|---|---|---|---|---|---|---|
| ANSA ultima ora | `https://www.ansa.it/sito/ansait_rss.xml` | 28 | 24 | 45 h | 80 | no | no |
| ANSA cronaca | `…/sito/notizie/cronaca/cronaca_rss.xml` | 129 | 39 | 63 h | 75 | no | no |
| ANSA politica | `…/sito/notizie/politica/politica_rss.xml` | 11 | 11 | 11 h | 80 | no | no |
| ANSA economia | `…/sito/notizie/economia/economia_rss.xml` | 12 | 12 | 11 h | 80 | no | no |
| ANSA sport | `…/sito/notizie/sport/sport_rss.xml` | 41 | 41 | 14 h | 73 | no | no |
| ANSA mondo | `…/sito/notizie/mondo/mondo_rss.xml` | 36 | 35 | 23 h | 65 | no | no |
| ANSA tecnologia | `…/canale_tecnologia/notizie/tecnologia_rss.xml` | 35 | 5 | 147 h | 82 | no | no |
| ANSA regioni (es. Lombardia, Sicilia) | `…/lombardia/notizie/lombardia_rss.xml` | 25–33 | 8–14 | 33–41 h | 72 | no | no |
| AGI | `https://www.agi.it/rss` | 20 | 20 | 10 h | **3266** | nel sommario | sì |
| Adnkronos ultima ora | `https://www.adnkronos.com/RSS_Ultimora.xml` | 20 | 20 | 7 h | 157 | no | no (ETag ignorato) |
| Adnkronos economia, sport | `…/RSS_Economia.xml`, `…/RSS_Sport.xml` | 20 | 6–20 | 15–52 h | 91–123 | no | — |
| la Repubblica | `https://www.repubblica.it/rss/homepage/rss2.0.xml` | 30 | 29 | 47 h | 137 | no | no |
| Corriere della Sera (sezioni) | `https://www.corriere.it/dynamic-feed/rss/section/Cronache.xml` (anche `Politica`, `Economia`, `Esteri`, `Sport`) | 100 | — | — | — | — | — |
| La Stampa | `https://www.lastampa.it/rss/copertina.xml` | 53 | 32 | (voci vecchie in coda) | 154 | no | — |
| Il Messaggero | `https://www.ilmessaggero.it/rss/home.xml` | 20 | 19 | 34 h | 184 | no | no |
| Open | `https://www.open.online/feed/` | 12 | 12 | 14 h | 292 | no | sì |
| Sky TG24 | `https://tg24.sky.it/rss/tg24.xml` | 100 | 100 | 15 h | 291 | no | no (ETag ignorato) |
| TGCom24 | `https://www.tgcom24.mediaset.it/rss/homepage.xml` | 30 | 30 | 9 h | 161 | no | — |
| Rainews | `https://www.rainews.it/rss/tutti` | 40 | 40 | 11 h | 146 | no | sì |
| Il Sole 24 Ore (Italia, Mondo, Finanza, Economia, Tecnologia) | `https://www.ilsole24ore.com/rss/italia.xml` … | 8–12 | 0–8 | 28–74 h | 160–185 | no | sì |
| La Gazzetta dello Sport | `https://www.gazzetta.it/dynamic-feed/rss/section/last.xml` (anche `…/section/Calcio.xml`) | 30 | 30 | **5 h** | 150 | no | — |
| Corriere dello Sport | `https://www.corrieredellosport.it/rss/calcio` | 30 | 30 | 12 h | 135 | no | no |
| Tuttosport | `https://www.tuttosport.com/rss/calcio` | 30 | 30 | 15 h | 118 | no | no |
| HDblog (tecnologia) | `https://www.hdblog.it/feed/` | 20 | 10 | 30 h | 95 | sì (1,5k) | sì |
| Punto Informatico | `https://www.punto-informatico.it/feed/` | 20 | 9 | 51 h | 253 | no | sì |
| Il Giorno (locale, Lombardia) | `https://www.ilgiorno.it/rss` | 100 | 100 | 23 h | 142 | sì (2,2k) | — |
| MilanoToday (locale) | `https://www.milanotoday.it/rss` | 25 | 20 | 39 h | 104 | breve | — |
| Governo (istituzionale) | `https://www.governo.it/it/rss.xml` | 10 | 4 | 49 h | 619 | no | sì |

**Da non usare** (provati il 12/10):

- **feed fermi da mesi o anni** ma ancora in risposta, con voci vecchie e nessun errore:
  `corriere.it/rss/homepage.xml` (ultima voce maggio 2024), i vecchi `xml2.corriereobjects.it`,
  `gazzetta.it/rss/home.xml` (novembre 2023), `ansa.it/sito/notizie/tecnologia/…` (maggio 2023), Wired
  Italia (luglio 2026), Rainews sport (quasi fermo), Adnkronos politica (aprile 2024). Un elenco di
  feed va **controllato da solo** (età dell'ultima voce), non solo all'installazione;
- **chiusi dal `robots.txt` per tutti**: Il Fatto Quotidiano (`Disallow: /feed/`) e il feed completo
  del Corriere `corriere.it/feed-hp/homepage.xml`; le sezioni `dynamic-feed` del Corriere invece sono
  permesse esplicitamente (`Allow: /dynamic-feed/*.xml`);
- **403 a un client che non è un browser**: Il Post, Fanpage (non si aggira: niente scraping, niente
  finti browser); **404**: Milano Finanza; Corriere dello Sport e Tuttosport `/rss` sono pagine HTML
  (i feed veri sono le sezioni, sopra).

Osservazioni per il lettore:

- **Date in italiano**: Sky TG24 e Il Messaggero scrivono `lun, 12 ott 2026 00:09:57 GMT`, che né
  feedparser né `email.utils` leggono: senza un lettore delle date italiane 120 voci su 1 200 restano
  senza data. MilanoToday dichiara un fuso sbagliato (voci «tra 4 ore»): le date nel futuro vanno
  riportate ad adesso.
- **Testo**: quasi tutti danno **titolo + 1–2 frasi** (65–300 caratteri), abbastanza per dire una
  notizia in una o due frasi a voce. AGI mette quasi l'articolo intero nel sommario (3 000 caratteri),
  alcune (Il Giorno, HDblog) il testo intero: si tiene solo l'inizio (600 caratteri).
- **Doppioni**: la stessa voce compare in più sezioni della stessa testata (44 su 1 195 nella misura);
  la stessa notizia da testate diverse ha titoli diversi.
- **Frequenza**: un feed «copre» da 5 ore (Gazzetta, di notte) a 2–3 giorni. Con lo scarico ogni 2 ore
  si perde qualcosa solo dai feed più veloci nelle ore di punta (Gazzetta, Adnkronos, AGI), cioè
  notizie che le altre testate ripetono.
- **Richieste condizionate**: metà dei feed risponde 304 (zero byte) con ETag o Last-Modified; gli
  altri vanno riscaricati interi. Volume: ~1,8 MB a giro, ~22 MB al giorno a scarico acceso.

## 2. Condizioni d'uso

| Testata | Cosa dice (fonte) | Per Calliope |
|---|---|---|
| ANSA | «per fini non commerciali da individui e organizzazioni no-profit», «alla sola visualizzazione mediante programmi software di lettura e aggregazione di documenti RSS, detti Readers»; vietato pubblicare i titoli su siti o blog; ANSA può dismettere il servizio ([ansa_rss.html](https://www.ansa.it/sito/static/ansa_rss.html)). I contenuti «possono essere consultati esclusivamente per finalità d'informazione personale» ([disclaimer](https://www.ansa.it/sito/static/disclaimer.html), citato nel campo `copyright` di ogni feed) | è il caso di Calliope (un lettore privato, in casa, senza ripubblicare): **sì** |
| la Repubblica | i feed si usano con «un apposito programma chiamato "aggregatore" o "reader"»; anche chi ha un blog può «diffondere» le notizie ([servizi/rss](https://www.repubblica.it/servizi/rss/index.html)) | **sì** |
| Corriere della Sera | «Il servizio è gratuito e non richiede nessuna registrazione»; i feed comprendono «il titolo, il sommario e l'indirizzo internet» per un lettore ([corriere.it/rss](https://www.corriere.it/rss/)) | **sì**, solo le sezioni permesse dal `robots.txt` |
| Il Sole 24 Ore | pagina dei feed senza condizioni ([ilsole24ore.com/rss](https://www.ilsole24ore.com/rss)); il [TDM Disclaimer](https://st.ilsole24ore.com/st/tdm-disclaimer/TDM_Disclaimer_ita.html) riserva ogni «estrazione» automatica, il text and data mining (art. 70-quater L. 633/1941) e l'uso per «alimentare algoritmi … ivi inclusi sistemi di intelligenza artificiale» senza consenso scritto | **dubbio**: leggere il feed in un lettore è l'uso previsto, ma Calliope passa il sommario a un modello. Da decidere (§ 6) |
| AGI, Adnkronos, Sky TG24, TGCom24, Rainews, Gazzetta, Corriere dello Sport, Tuttosport, HDblog, Punto Informatico, Il Giorno, Governo | nessuna condizione trovata per i feed (pagina di AGI in errore 500 il 12/10); il campo `copyright` del feed dove c'è | uso personale come un lettore: **sì**, con la fonte detta |

**`robots.txt` e agenti delle IA** (letti il 12/10 con `urllib.robotparser`). Nessuno dei feed
raccomandati è chiuso a un agente generico (`*`), ma molte testate chiudono il sito agli agenti con
nome delle aziende di IA, anche a quelli che leggono una pagina su richiesta di una persona:
`ChatGPT-User` è escluso da ANSA, Corriere, Il Messaggero, Rainews, Il Sole 24 Ore, MilanoToday;
`Claude-User` da Il Messaggero e Wired; `anthropic-ai` o `ClaudeBot` da quasi tutte. Nessuna nomina
Calliope (che non è nessuno di quegli agenti), ma il segnale è chiaro: le testate non vogliono che i
loro testi alimentino i sistemi di IA delle aziende. Calliope è diversa (in casa, nessun addestramento,
nessuna ripubblicazione, la fonte detta), ma è comunque un modello che legge e riassume.

Proposta: Calliope si presenta con un User-Agent onesto (`Calliope/<versione> (lettore di feed
personale)`), rispetta il `robots.txt` per `*` e per `Calliope`, legge **solo i feed** (mai le pagine
degli articoli: niente scraping), dice sempre la testata, non conserva oltre 7 giorni e non mostra
mai i testi fuori di casa. L'elenco di serie si limita alle testate che non hanno condizioni contrarie
(§ 6, domanda 1). Non è un parere legale: chi pubblica il progetto valuta.

## 3. Misura: quante domande trovano risposta nei feed

**SearXNG non è raggiungibile dal portatile** (ascolta solo su 127.0.0.1 della DGX): il confronto
diretto non c'è, misurati solo i feed. Per SearXNG valgono le misure già scritte in
[biblioteca](../aree/biblioteca.md): ricerca 0,5–3 s (mediana 1,3), ANSA a volte in timeout, Google
News «access denied», Brave «too many requests», prima frase delle notizie fino a 7,9 s (09/10 sera).

Indice: 28 feed di 15 testate (ANSA nazionale, sezioni e due regioni, AGI, Adnkronos, Repubblica,
Corriere sezioni, La Stampa, Sky TG24, Rainews, Il Sole 24 Ore, Gazzetta, Corriere dello Sport,
Tuttosport, HDblog, Punto Informatico, Il Giorno), voci degli ultimi 7 giorni, doppioni tolti: **1 081
voci**. SQLite FTS5 in memoria (`unicode61 remove_diacritics 2`, titolo con peso doppio, un po' di
vantaggio alle voci recenti); il tema è quello che `tema_notizie` e `tema_dalla_frase` già ricavano
oggi per SearXNG. Giudizio a mano sui primi 3 risultati: «sì» se dicono la risposta e sono recenti.

| Domanda | Esito | Note |
|---|---|---|
| Cosa è successo oggi in Italia? | sì, con una correzione | i primi 3 erano tutti di una testata locale con 100 voci a mezzanotte: per le notizie generali serve una voce per testata nazionale, a turno (con quella: ANSA, Rainews, Repubblica, Sky TG24) |
| Dimmi le ultime notizie | sì, con la stessa correzione | |
| Notizie sulla Juventus | sì | risultato della partita, 4–10 h |
| Com'è andata la borsa? | **no** | notte di domenica: nessuna seduta; «borsa» trova anche una borsa rubata. Ripiego |
| Novità sul governo | in parte | primo risultato sul governo di un altro paese: manca la preferenza per l'Italia (sezione politica, «Meloni») |
| Che notizie ci sono sull'Inter? | sì | |
| Cosa succede in Ucraina? | sì | 4–9 h, due testate |
| Notizie da Gaza | in parte | solo i cortei in Italia di 1–2 giorni prima |
| Notizie di Milano | sì | |
| Cosa succede a Palermo? | sì | sport e cronaca |
| C'è un'allerta maltempo? | in parte | un'allerta «per domani» di 62 ore prima: va detta con la data, mai come attuale |
| Ci sono scioperi dei treni? | **no** | «scioperi» non trova «sciopero» senza le radici delle parole (`_stem` della biblioteca), e gli scioperi annunciati non sono nei feed: ripiego |
| Quanto costa la benzina? | sì | 20 h |
| Novità sull'intelligenza artificiale | in parte | voci di 3–5 giorni |
| Notizie su Apple | sì | |
| Com'è andato il Gran Premio di Formula 1? | sì | tre testate |
| Novità sulla manovra | sì | |
| Risultati della Serie A | sì | |
| Come sta andando Sinner? | **no** | nessuna voce nei feed (giusto dirlo, o ripiego) |
| Cosa ha detto il Papa? | sì | tre testate concordi |
| Notizie su Trump | sì | |
| Novità su un caso di cronaca nazionale | sì | |

**15 sì, 4 in parte, 3 no su 22.** I «no» e i «in parte» sono quasi tutti risolvibili: radici delle
parole, notizie generali a turno per testata, preferenza per le voci italiane nelle domande sulla
politica; il resto (borsa nel fine settimana, scioperi annunciati, un tema che non c'è) è il caso del
ripiego su SearXNG o di un «nelle notizie di oggi non c'è niente su…».

**Tempi** (portatile, CPU): scarico dei 28 feed in serie 4,5 s, **in parallelo (6) 0,74–1,14 s**;
lettura con feedparser 11 ms di mediana per feed, 0,74 s per tutti i 41 feed della sonda; inserimento
nell'indice 13 ms; **ricerca 0,04 ms di mediana, massimo 0,17 ms**. Con la libreria standard
(`xml.etree.ElementTree`) tutti i 41 feed si leggono senza errori (feedparser: nessun `bozo`).

## 4. Progetto

### 4.1 Lettore: libreria standard, feedparser come alternativa

- **feedparser** 6.0.14 (30/07/2026): BSD-2-Clause, **puro Python** (`py3-none-any`, quindi win_amd64,
  win_arm64 e aarch64 senza compilare), Python ≥ 3.10, una dipendenza: **feedparser-sgmllib** 2.1.0
  (PSF-2.0, anch'essa `py3-none-any`). Toglie il `DOCTYPE` prima di leggere, ripulisce l'HTML, legge
  anche i feed rotti. Non legge le date italiane (serve comunque un gestore,
  `registerDateHandler`); va usato **solo su byte già scaricati** (`feedparser.parse(bytes)`), mai
  con un URL: farebbe da sé le richieste HTTP con urllib.
- **Libreria standard** (`xml.etree.ElementTree` + il `ripulisci_testo` di `web/servizio.py`):
  tutti i feed provati sono XML ben formati e RSS 2.0; un lettore per RSS 2.0 e Atom con le date
  italiane è un centinaio di righe. expat 2.8.1 sul portatile e 2.6.1 sulla DGX (Python di sistema
  3.12) limitano l'espansione delle entità («billion laughs», da expat 2.4), ElementTree non legge
  entità esterne; in più un tetto di dimensione (2 MB: il feed più grande è 0,7 MB).

**Proposta: libreria standard**, come il lettore ZIM e le pagine web (principio 4: niente da
verificare su ARM, niente da aggiungere a `TERZE-PARTI.md`). Se un feed scelto risultasse mal formato,
lo si toglie dall'elenco o si passa a feedparser in un secondo momento.

### 4.2 Indice e conservazione

- Un file SQLite nella cartella dei dati di Calliope (`notizie.sqlite`): una tabella delle voci (id,
  testata, sezione, titolo, sommario di al più 600 caratteri, data, link tenuto solo per i doppioni e
  per la scheda) e una tabella FTS5 con il contenuto (non `content=''` come la biblioteca: qui si
  cancella e si mostra il testo). Stesso tokenizer della biblioteca e stesse radici (`_stem` di
  `biblioteca.py`: «scioperi» → «sciop»), `detail=full`. **Non** si riusa `biblioteca_indice.py`
  (legato ai file ZIM, costruito una volta e mai modificato): si riusano le sue scelte.
- **Conservazione 7 giorni** (come `PERIODO_NOTIZIE` = settimana di SearXNG): ~1 500 voci nuove al
  giorno, ~10 000 voci, pochi MB. Pulizia a ogni scarico.
- **Doppioni**: stessa testata, stesso titolo o stesso link → una voce. Testate diverse sulla stessa
  notizia restano due voci (e la risposta può dire «lo riportano ANSA e Sky TG24»).
- **Feed fermi**: dopo ogni scarico, l'età dell'ultima voce di ogni feed; oltre 7 giorni il feed è
  «fermo» nel registro delle capacità (e nel cruscotto), senza toglierlo da solo.

### 4.3 Quando si scarica (decisione del 12/10)

- **Ogni 2 ore, solo se negli ultimi 7 giorni qualcuno ha chiesto notizie.** La data dell'ultima
  richiesta di notizie (una qualunque chiamata con tipo notizie) si salva su disco; un thread come
  quello del controllo di SearXNG (`web/motore.py`) guarda ogni pochi minuti se è ora.
- **Prima richiesta dopo una pausa** (indice vuoto o più vecchio di 6 ore): si risponde subito con
  SearXNG se c'è, e lo scarico parte in background; senza SearXNG si scarica subito (circa 1 s in
  parallelo, dietro la frase d'attesa che c'è già).
- Richieste condizionate (ETag, Last-Modified), 6 feed alla volta, timeout di 10 s per feed, un
  feed che fallisce non ferma gli altri. Nessuna domanda esce: solo lo scarico, uguale per ogni casa.
  È un vantaggio di privacy rispetto a SearXNG, dove ogni domanda esce (ripulita).

### 4.4 Interfaccia: una fonte dentro `web_cerca`, non un tool nuovo

- `web_cerca` con tipo «notizie» cerca **prima nell'indice**; i 76 schemi restano 76, il modello
  sceglie già quel tool per le notizie (casi veri del 09/10), e le regole di oggi (`notizie_tema`,
  `notizie_tema_frase`, `notizie_generali`) danno già il tema.
- Il tool c'è se c'è SearXNG **oppure** l'indice delle notizie; con il solo indice, tipo «web»
  risponde «la ricerca su internet non c'è» (frase pronta) e la descrizione lo dice.
- Notizie senza tema: le voci più recenti dei feed «generali» (agenzie e prime pagine), una per
  testata a turno, mai tutte dalla stessa.
- **Ripiego su SearXNG** (regola `notizie_ripiego` nel registro dei turni) quando: meno di 2 voci
  sul tema nelle ultime 72 ore; ultimo scarico riuscito più vecchio di 6 ore; scarico fermo
  (decisione: nessuno chiedeva). Senza SearXNG, si dice ciò che c'è con la sua data, o che nelle
  notizie scaricate non c'è niente.
- Registro dei turni: `notizie_feed` (risposta dall'indice) o `notizie_ripiego`, quante voci, età
  della più recente. Misure da guardare: quota dall'indice, prima frase, età delle notizie dette.

### 4.5 Come si dice la fonte

Ogni risultato ha la **testata** (nome dall'elenco della configurazione, mai dal feed né dall'URL), il
titolo, il sommario e **quando** in parole («stamattina», «ieri sera», «sabato»): «Secondo l'ANSA,
stamattina…». Mai l'indirizzo. Il `cosa_fare` è quello di `web_cerca` (1–3 frasi, la testata per
nome, niente inventato); notizie di più di 3 giorni con `vecchio`, come oggi. La scheda sugli schermi
può mostrare titolo, testata e link.

### 4.6 Sicurezza: il testo dei feed è un dato non fidato

Anche se sta su disco, il testo viene da internet: stessa **busta** di `web_cerca` (`attenzione`,
testo ripulito, `non_fidato`), stessa **provenienza** («web» per la politica per valore) e la stessa
regola `DOPO_DATO` (dopo un risultato, nella stessa risposta, solo letture). Titoli e sommari passano
da `ripulisci_testo` (tag, caratteri di controllo, lunghezza). Un titolo con un'istruzione dentro è
il caso già provato per SearXNG (0 azioni su 8).

### 4.7 Minori

Oggi `web_cerca` è chiuso ai minori (preset «internet»: «Su internet per te non cerco»). Con l'indice
la domanda non esce, ma il contenuto è cronaca (delitti, guerre, incidenti). Proposta: **resta come
oggi** (chiuso) finché chi amministra non decide; se si apre, con `filtra_per_minore` sui titoli e
sommari e magari solo le sezioni sport, tecnologia e scienza (domanda 3).

### 4.8 Senza internet

Lo scarico fallisce in silenzio (una riga nel registro, capacità «notizie: degradata, ultimo scarico
alle …»), l'indice resta e invecchia: Calliope dice ciò che ha **con la sua data** («l'ultima notizia
che ho è di ieri sera: …») e dopo 7 giorni l'indice è vuoto: «Non ho notizie recenti: internet non
c'è». Nessuna attesa: la ricerca locale non dipende dalla rete.

### 4.9 Profilo da 8 GB di VRAM

**Nessuna differenza.** Lo scarico e l'indice usano solo CPU e disco (meno di 1 s di CPU ogni 2 ore,
pochi MB), nessun modello, nessuna VRAM. Il risultato dato al modello ha la stessa misura di quello di
SearXNG (3–5 voci, ~200 caratteri l'una): stessi token nel contesto. Sul portatile, anzi, è più
veloce di SearXNG, che di solito non c'è (gira sulla DGX): con il profilo ridotto le notizie
diventano disponibili anche senza SearXNG.

### 4.10 Configurazione: 5 campi

| Campo | Predefinito | Cosa |
|---|---|---|
| `notizie_enabled` | `true` | l'indice delle notizie (con `online` vero) |
| `notizie_feed` | elenco di serie (§ 5) | testata, URL, tema («generale», «sport», «economia», «tecnologia», «locale»); chi amministra ne aggiunge o ne toglie in `calliope.locale.yaml` |
| `notizie_intervallo_min` | `120` | ogni quanto si scarica |
| `notizie_attesa_giorni` | `7` | si scarica solo se qualcuno ha chiesto notizie in questi giorni |
| `notizie_conserva_giorni` | `7` | dopo, le voci si cancellano |

Il resto (6 in parallelo, 2 MB, 600 caratteri, 72 ore e 2 voci per il ripiego) sono costanti nel
codice, come per SearXNG.

## 5. Elenco di serie proposto (13 testate, ~22 feed)

ANSA (ultima ora, cronaca, politica, economia, mondo, sport, tecnologia; più la regione di casa, da
scegliere), AGI, Adnkronos ultima ora, la Repubblica, Corriere della Sera (sezioni `dynamic-feed`),
Il Messaggero, Sky TG24, TGCom24, Rainews, La Gazzetta dello Sport, Corriere dello Sport, HDblog,
Punto Informatico. **Il Sole 24 Ore solo se chi amministra lo accetta** (TDM Disclaimer). Locali
(Il Giorno, MilanoToday, ANSA regionali) solo dalla configurazione locale: dipendono dalla casa e non
vanno nel file d'esempio.

## 6. Domande per chi amministra

1. **Testate di serie e IA**: si tengono le testate che chiudono il `robots.txt` agli agenti delle IA
   con nome (ANSA, Corriere, Il Messaggero, Rainews), visto che le loro condizioni permettono la lettura
   personale in un lettore? E Il Sole 24 Ore, che vieta l'uso per «alimentare» sistemi di IA?
2. **Regione di casa**: un feed regionale ANSA dalla città di casa (`casa_citta` → regione), o solo
   a mano?
3. **Minori**: restano senza notizie (come oggi), oppure solo sport e tecnologia, oppure tutte con il
   filtro dei contenuti per adulti?
4. **Prima richiesta dopo la pausa** senza SearXNG: va bene aspettare ~1 s di scarico?
5. **Lettore**: libreria standard (proposta) o feedparser (una dipendenza in più, più robusto con i
   feed rotti)?

## Fonti (consultate il 12/10/2026)

- ANSA, «I feed RSS di ANSA.it» (condizioni ed elenco): <https://www.ansa.it/sito/static/ansa_rss.html>;
  disclaimer: <https://www.ansa.it/sito/static/disclaimer.html>
- la Repubblica, feed RSS: <https://www.repubblica.it/servizi/rss/index.html>
- Corriere della Sera, RSS: <https://www.corriere.it/rss/>; `robots.txt`: <https://www.corriere.it/robots.txt>
- Il Sole 24 Ore, RSS: <https://www.ilsole24ore.com/rss>; TDM Disclaimer:
  <https://st.ilsole24ore.com/st/tdm-disclaimer/TDM_Disclaimer_ita.html>
- `robots.txt` di ansa.it, repubblica.it, ilsole24ore.com, rainews.it, gazzetta.it, adnkronos.com,
  ilfattoquotidiano.it, ilmessaggero.it, wired.it, milanotoday.it, ilgiorno.it (letti il 12/10)
- feedparser su PyPI: <https://pypi.org/project/feedparser/> (6.0.14, BSD-2-Clause);
  feedparser-sgmllib: <https://pypi.org/project/feedparser-sgmllib/> (2.1.0, PSF-2.0); sorgenti:
  <https://github.com/kurtmckee/feedparser>
- Legge 633/1941, art. 70-quater (estrazione di testo e dati, riserva dei titolari)
- Interni: [`2026-10-03-ricerca-web.md`](2026-10-03-ricerca-web.md),
  [biblioteca](../aree/biblioteca.md), decisioni [0021](../decisioni/0021-ricerca-web-searxng.md) e
  [0024](../decisioni/0024-niente-internet-se-non-serve.md)
