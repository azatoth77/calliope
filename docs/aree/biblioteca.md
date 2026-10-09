# Biblioteca offline e ricerca web

*Wikipedia italiana e le altre fonti Kiwix in puro Python con FTS5; ricerca su internet con SearXNG. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

*Stato al 09/10: biblioteca e ricerca web invariate dalla pubblicazione (07/10). Dall'08/10 notte il testo dei siti letto dall'agente (`web_leggi`) arriva in busta come ogni dato non fidato, e i nomi pubblici di casa sono vietati nella rete delle estensioni e dell'agente ([agenti-estensioni](agenti-estensioni.md)). Restano aperti le tabelle delle voci non lette e i «perché…?» che trovano titoli omonimi. Dal 09/10 SearXNG si tiene aggiornato da solo (controllo quotidiano, aggiornamento provato accanto con il ritorno indietro, «Controlla» e «Aggiorna» nel cruscotto: sezione in fondo); la prima prova vera sulla DGX è da fare.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Biblioteca offline | Wikipedia italiana in ZIM di Kiwix, letta in puro Python (solo libreria standard, solo CPU) con un indice SQLite FTS5 accanto; niente `libzim` dal 01/10 | `calliope/biblioteca.py` → `Biblioteca.cerca`, `load_biblioteca`; `calliope/zim.py` → `ZimFile`; `calliope/biblioteca_indice.py` → `costruisci`, `apri`, `stato_indice`; tool `biblioteca_cerca`; file in `biblioteca/` (`scarica.sh`), indici in `biblioteca/indici/` |
| Ricerca su internet (facoltativa, solo con la rete) | SearXNG in un container di Calliope sulla DGX (`calliope-searxng`, 127.0.0.1:8004, niente log; `setup/linux/motore/searxng.sh`), httpx in POST; pagine con http.client e html.parser, senza SSRF | `calliope/web/` → `Web` (`servizio.py`), `Ripulitore` (`privacy.py`: niente dati personali nelle domande), `scarica`, `estrai_testo` (`pagina.py`), `load_web`; tool `web_cerca` in `calliope/tools/web.py`; `web_cerca` e `web_leggi` dell'agente in `calliope/agenti/ciclo.py`; solo letture dopo un risultato web: `politica.DOPO_DATO` (`politica.bloccata`) |
| SearXNG tenuto aggiornato (09/10) | ricerche di prova fisse in POST, registro delle immagini (Docker Hub) con tag e digest, docker tramite lo script | `calliope/web/motore.py` → `MotoreRicerca` (`controlla`, `aggiorna`, `passo`, `avvia_azione`), `giudica`, `almeno_come`, `tag_recenti`; `setup/linux/motore/searxng.sh` (`candidata`, `usa`, `pulisci-immagini`…); `calliope motore searxng controlla|aggiorna|novita|storia` |

## Problemi noti

*Fuse il 09/10 le due sezioni nate dalla divisione di CLAUDE.md (stato e problemi fino al 06/10): ogni voce una volta sola, le superate segnate come storiche.*

  - **Ricerca su internet quando c'è** (03/10, `calliope/web/`, rapporto
    [`docs/ricerche/2026-10-03-ricerca-web.md`](../ricerche/2026-10-03-ricerca-web.md)):
    `web_cerca` per l'attualità (meteo, notizie, risultati, orari, prezzi), la biblioteca resta
    la prima scelta per i fatti stabili; SearXNG sulla DGX (`calliope motore searxng avvia`,
    poi `web_searxng_url: http://127.0.0.1:8004` in `calliope.locale.yaml`); senza, il tool non
    c'è e la capacità «ricerca web» dice il passo. Livello minimo `web_livello` (familiare),
    `web_max_minuto` 10. Le domande escono senza nomi di casa, CF, IBAN, email, telefoni,
    `web_dati_privati` (regola `web_dati_tolti`) e non restano nel registro («******»). Il testo
    dei siti è non fidato: avviso, testo ripulito, **nessuna azione nella stessa risposta**
    dopo un risultato web (`web_azione_bloccata`) e fuori dalla storia a risposta finita;
    estratti con una data vecchia in fondo con «vecchio» (il 03/10 gemma4 diceva come domani il
    meteo di gennaio 2025). Agente: `web_leggi` solo sui risultati del suo lavoro, niente IP
    privati né nomi locali (SSRF), internet spento dopo i documenti di casa. Con Ollama (2
    giri): attualità 10/10, fatti stabili alla biblioteca 12/12, iniezione 0 azioni provate su
    8. Vera sulla DGX: ricerca 0,6–3,1 s (mediana 1,3), prima frase 1,55 s con la frase d'attesa.

- **Biblioteca offline** (26/09, [`docs/ricerche/2026-09-26-biblioteca-prova.md`](../ricerche/2026-09-26-biblioteca-prova.md)):
  Wikipedia italiana per i fatti precisi, con la fonte citata a voce; dal 01/10 senza `libzim`
  (sotto) e con Wikiquote per le citazioni. La ricerca è lessicale, su CPU, in ~30 ms (massimo ~110). Usa i titoli esatti presi dalla
  frase, le parole di attributo con i sinonimi delle infobox, l'infobox per le domande sui
  dati, la voce completa se nel mini manca il dato e le voci-elenco per i superlativi.
  Recall@3 50/56. Il rerank con bge-m3 non migliorava (stesso recall, +169 ms, +0,76 GB):
  scartato. End-to-end 59/61 contro 56/61 senza (il 02/10, con l'indice FTS5 e `opzioni`
  corretta: 58–59/61 contro 52–53/61); senza biblioteca il 4B sbaglia con
  sicurezza (Manzoni «1812», Tevere «430 km»). Costo: **+0,5 s sulla prima frase** delle
  domande sui fatti. Tre regole nate dagli errori:
  1. il prompt nomina `biblioteca_cerca` solo se il tool c'è (`Config.prompt_for`); con un
     tool nominato ma assente il modello rispondeva «non ho accesso» a tutto;
  2. nel confronto dei titoli la parte tra parentesi non conta, e per i superlativi valgono
     solo i passaggi con un primato nell'ambito chiesto; senza, «il lago più grande d'Italia
     è il lago di Vico, secondo Wikipedia»;
  3. `cosa_fare` dice di ignorare i passaggi fuori tema e di non citare Wikipedia quando la
     risposta viene dalla memoria del modello.
  Le tabelle delle voci (classifiche, elenchi) non si leggono.

- **Biblioteca senza libzim** (01/10, [`docs/ricerche/2026-10-01-biblioteca-senza-libzim.md`](../ricerche/2026-10-01-biblioteca-senza-libzim.md)).
  `libzim` non ha wheel `win_arm64` (né libzim, kiwix-serve o Kiwix Desktop per Windows ARM):
  la biblioteca ora non la usa più, su nessuna piattaforma.
  - **Lettore ZIM in puro Python** (`calliope/zim.py`, ~590 righe): `mmap`, `struct`, `lzma`,
    `compression.zstd` (con Python < 3.14 il pacchetto `zstandard`, provato). Stesse voci e
    stesso HTML di libzim su 600 voci a caso dei 4 file (600/600,
    `prove/arm/confronta_lettore.py corretto`); apertura 0,2–0,5 ms contro ~100 ms; lettura
    di una voce 1,6–2,6 ms di mediana, p95 3–4 ms (decompressione a pezzi, cache di 8
    cluster); ~100 MB di memoria privata contro ~200. Thread-safe. Solo formato 6.x. Un file
    troncato o rovinato dà `ZimError`, non un crash.
  - **Indice SQLite FTS5** (`calliope/biblioteca_indice.py`) solo per Wikipedia ridotta e
    Vikidia: la completa si legge per titolo, il Wikizionario per percorso (indicizzarle non
    cambiava nessuna risposta). Parole ridotte con la stessa `_stem` del punteggio, alias
    dei redirect nel titolo, bm25 con peso del titolo 1 (`biblioteca_peso_titolo`).
    **`detail=full` è obbligatorio**: con `content=''` e `detail=column` bm25 vale sempre 0.
  - Costruzione misurata qui: mini **240 s con 4 processi, 1 308 MiB**, picco del processo
    principale ~1 GB (scansione 26 s); Vikidia 1 s, 10 MiB. Indice valido solo se completo,
    della stessa versione dell'estrattore (`VERSIONE` e firma di `_stem`) e dello stesso ZIM
    (uuid e dimensione); si scrive in `.tmp` e si rinomina. L'installazione lo costruisce
    dopo la verifica SHA-256, in un processo a parte a priorità bassa (`--stdin`: chiudendo
    lo stdin si ferma pulito). `risolvi_zim` passa a un file nuovo di quelle famiglie solo
    con il suo indice completo; la pulizia cancella anche gli indici dei file superati.
  - Qualità e tempi (`prove/prova_biblioteca.py`, stessa macchina e stessa ora): banco
    **49/56** (libzim 50/56: Colombo «1492» arriva dalla voce «America» solo con Xapian),
    banco nuovo da 46 domande **36/46** (uguale), altre prove 15/15; `cerca` mediana
    **28 ms**, p95 73, massimo 152, prima domanda 46 ms (libzim 41 / 116 / 406 ms, prima
    680 ms); apertura della biblioteca ~75 ms con gli indici. Full-text più lento di Xapian
    sulle parole frequenti (p95 36 ms contro 7), suggerimenti più veloci (p95 18 contro 40).
  - Su una macchina senza libzim (venv nudo, solo libreria standard) lettore, indice e banco
    danno gli stessi numeri. Da misurare sullo Spark: `prove/arm/` (vedi `prove/LEGGIMI.md`).
  - Con `processi` > 1 la costruzione usa `multiprocessing` «spawn»: va chiamata da un main
    protetto (`python -m calliope.biblioteca_indice`), mai da uno script senza
    `if __name__ == "__main__"` (i figli lo rieseguirebbero all'infinito).
  - **End-to-end con Ollama** (`prova_biblioteca.py --ollama`, stessa sera, stesso modello):
    nuovo 55/61 e 53/61 in due giri, HEAD con libzim 52/61. Il 59/61 del 26/09 non torna né
    con libzim né senza: colpa di `opzioni` (significati ambigui, 26/09), che prende la
    prima parola singola con una disambiguazione quando il modello riformula la domanda
    («caduta del **muro** di Berlino», «**profondità** del lago di Garda», «chi ha
    **composto** la Traviata», «**punto** più profondo», «**fine** della seconda guerra
    mondiale») e risponde «ha più significati». `Muro_di_Berlino` non si trova perché
    `exact` prova solo «Muro di berlino» e «Muro Di Berlino» (resta così: la ricerca la trova
    comunque).
  - **Corretto il 02/10** (`Biblioteca.opzioni`): la disambiguazione vale solo se la domanda è
    proprio su quel nome, cioè oltre al nome ci sono solo parole di richiesta o di attributo
    (`_NOT_SUBJECT`: «parlami di Venere», «cos'è un'iperbole?», «quanto è grande Venere?»).
    I 5 casi sopra non sono più ambigui (casi contrari in `prova_biblioteca`, altre prove
    22/22). End-to-end, 2 giri: **58/61 e 59/61** (manuale 41/43 e 43/43, difficili 17/18 e
    16/18), senza biblioteca 53/61 e 52/61; citazioni 3/4. Restano: «punto più profondo degli
    oceani» (risponde con l'abisso Vitjaz'), Colombo «1492», torre di Pisa, Kilimangiaro una
    volta senza tool. A secco invariato: banco 49/56, nuovo 36/46.
  - **Wikiquote nella ricerca** (prima fonte in più, `biblioteca_fonti_extra`, predefinita
    accesa): indice 144 MiB in 18 s; si apre solo con l'indice e si usa solo quando la
    domanda chiede una citazione (`biblioteca.RICHIESTE`: «citazione», «aforisma», «chi ha
    detto…», «proverbio»), con un vantaggio di +5 sul punteggio. Sulla voce dell'autore
    («una citazione di Einstein») il suo nome nel testo non conta: le righe che lo nominano
    sono frasi su di lui o fonti bibliografiche (`_NON_CITAZIONE`: traduzione, ISBN,
    editore e anno), e quelle con un'altra attribuzione in fondo («(Niels Bohr)») perdono.
    Con Wikiquote la descrizione di `biblioteca_cerca` nomina le citazioni e `opzioni` non
    si chiede. A secco 4/4, con Ollama 3/4 contro 0/4 senza (la «bellezza salverà il mondo»
    la attribuisce a un saggio omonimo); i banchi dei fatti non cambiano (49/56, 36/46).

- **Biblioteca: più fonti e significati ambigui** (26/09, `calliope/biblioteca.py`):
  - **Wikizionario** per «cosa significa…», «sinonimi/contrari di…» e «cos'è un…»
    (estrattore dedicato: sezione Italiano, definizioni per parte del discorso), 1–5 ms.
  - **Vikidia** con la precedenza per le spiegazioni semplici: profilo `giovane`
    (`arruola.py --giovane`) o richiesta «in modo semplice»; il tool chiede allora al
    modello parole adatte a un ragazzo.
  - **Ambiguità**: solo se la voce principale del nome è una disambiguazione per
    Wikipedia stessa (marcatore `mw:PageProp/disambiguation`: iperbole, Venere, Mercurio).
    Allora il tool dà 2–3 significati principali e il modello risponde sul più probabile e
    offre gli altri, o sceglie dal contesto. Quasi ogni nome ha una disambiguazione («Tevere»:
    fiume, dipartimento, nave…): se la voce principale è un articolo non si chiede nulla.
  - Le pagine di disambiguazione non si usano come passaggi. Limite noto: le domande con
    «perché» su fenomeni («perché piove?») trovano titoli omonimi (canzoni) invece della
    voce giusta.

## SearXNG tenuto aggiornato (09/10, ramo `searxng-aggiornamento`)

Decisione di Dario del 09/10: i motori a cui SearXNG si appoggia (DuckDuckGo, Brave, Bing,
Google News…) cambiano spesso le loro pagine e un'immagine di SearXNG vecchia di qualche
settimana smette di trovare; l'immagine di Calliope era fissata al 03/10 (`2026.10.2-…`), il 09/10 sul
registro c'erano già tag più nuovi (2026.10.4 e 2026.10.7). Codice in `calliope/web/motore.py`, script in
`setup/linux/motore/searxng.sh`, prova `prove/prova_searxng_aggiorna.py` (a secco) e
`prova_cruscotto_pagina.py` (pagina vera).

- **Controllo** (sempre, in tutti e due i modi): `web_searxng_prove` («categoria:domanda»,
  predefinite «meteo Roma domani», «notizie Italia oggi», «Serie A risultati»: frasi fisse,
  nessun dato di nessuno) in POST contro il SearXNG locale, come le ricerche vere ma fuori dal
  tetto al minuto; per ciascuna risultati, motori che hanno dato risultati, motori che non
  rispondono con il motivo di SearXNG (CAPTCHA, timeout, accesso negato), errori e tempo.
  Giudizio: «giù» se nessuna risponde (la capacità diventa «guasta», come dopo una ricerca
  fallita); «degradata» se una prova ha meno di `web_searxng_min_risultati` (3) risultati, o
  se motori o risultati scendono sotto `web_searxng_soglia` (0,6) dell'**ultimo controllo
  buono della stessa immagine**; «buona» altrimenti (diventa il nuovo buono). Una volta ogni
  `web_searxng_controllo_ore` (24), solo con Calliope ferma da `web_searxng_inattivita_min`
  (30: nessun turno su nessuna corsia, `Avvio.inattivita_s`) e nessun lavoro dell'agente in
  coda o in corso; un thread che guarda ogni 5 minuti.
- **Registro delle capacità**: stato nuovo **«degradata»** (funziona, ma peggio: `Capacita.funziona`);
  la ricerca web lo diventa con il motivo del controllo e il passo («Aggiorna» nel cruscotto, o
  «provo da sola» in automatico). «Cosa sai fare?» e chi non amministra la contano come
  funzionante; a chi amministra «funziona, ma peggio del solito: …».
- **Aggiornamento** (`web_searxng_aggiorna`: «automatico», predefinito, oppure «manuale»; un
  valore sconosciuto vale manuale): tag dal registro delle immagini (`web_searxng_registro`,
  Docker Hub), solo «AAAA.M.G-hash», attivi, con il digest dell'indice e arm64 e amd64: **mai
  `latest`**, l'immagine è sempre `searxng/searxng:TAG@sha256:…`. In automatico il più
  recente pubblicato da almeno `web_searxng_giorni` (3) giorni, o il più recente in assoluto
  se la ricerca è degradata; un tag già scartato non si riprova da solo. Poi: prove sulla
  vecchia **adesso**; la nuova scaricata e avviata **accanto** (`searxng.sh candidata`,
  container `calliope-searxng-candidata` su 127.0.0.1:10004, stesse regole del vero, senza
  riavvio automatico) e le stesse prove; la copia di prova si toglie. Se va peggio
  (`almeno_come`: prove riuscite non meno, motori non meno di uno in meno, risultati almeno
  l'80 %) **la vecchia resta e non si è fermato niente**, il tag è scartato. Se va almeno come
  la vecchia: in automatico si ricontrolla che nessuno abbia cominciato a parlare intanto
  (altrimenti «rinviato»), poi `searxng.sh usa` sceglie l'immagine (`~/calliope-motore/searxng/immagine`)
  e rifà il container vero (pochi secondi senza ricerca), le prove di nuovo; se non risponde
  o va peggio `usa` con la vecchia: **ritorno indietro**. Dopo un cambio riuscito
  `pulisci-immagini` toglie solo le immagini scaricate da qui (`scaricate`), tenute quella in
  uso e la precedente, senza `-f` (un'immagine usata da un container, anche fermo, resta):
  mai quelle di altri progetti (sulla DGX c'è un altro SearXNG, che non si tocca).
- **Lo script** sceglie l'immagine così: `IMMAGINE` dall'ambiente; altrimenti quella in
  `DIR/immagine` se non è più vecchia (per data del tag) di quella fissata nello script;
  altrimenti la fissata. Così `calliope motore searxng avvia` dopo un aggiornamento non torna
  indietro, e una versione di Calliope che fissa un tag più nuovo vince. `dimentica` torna alla
  fissata. Le forme sbagliate (latest, senza digest, altro repository, caratteri in più) si
  rifiutano prima di qualunque comando docker.
- **Registro delle decisioni**: `web_searxng_stato` (`motore/searxng.json` nella cartella dei
  dati): ultimo controllo, ultimo buono, giudizio, immagine, tag più recente visto, tag
  scartati, ultimo esito e la **storia** (ultime 40: controlli, aggiornamenti, chi: automatico,
  terminale, `cruscotto:<id>`), più le righe `[WEB] SearXNG: …` nel log. L'esito di un
  aggiornamento automatico (aggiornata, tenuta, tornata indietro, errore) e il passaggio a
  «degradata» arrivano come scheda «Da leggere» sugli **schermi personali di chi amministra**
  (`Cruscotto.avvisa`), mai a voce né sugli schermi di stanza.
- **Poche ricerche, distanziate** (09/10: una ventina di fila fa smettere ANSA e DuckDuckGo per
  qualche minuto): 4 s tra una prova e l'altra (`PAUSA_PROVE_S`), 20 s prima del cambio
  (`PAUSA_GIRI_S`), e per la vecchia valgono le prove del controllo appena fatto (stessa
  immagine, meno di 15 minuti): un controllo con aggiornamento fa 9 ricerche in ~1–2 minuti.
- **Un'operazione alla volta**: un lock nel processo e un file di blocco accanto allo stato
  (Calliope e il terminale insieme: «occupato»); un blocco di un processo morto o più vecchio di
  3 ore si ignora.
- **Manuale**: «Controlla» e «Aggiorna» nel cruscotto di chi amministra
  ([schermi-telefono](schermi-telefono.md)); da terminale sulla DGX
  `calliope motore searxng controlla | aggiorna | novita | storia` (in Python, nella cartella
  dei dati, con lo stesso stato e lo stesso blocco). «Aggiorna» a mano prende il tag più
  recente qualunque età abbia, anche uno scartato; con lavori dell'agente in corso no.
- **Dove non c'è il container**: su Windows, con SearXNG su un'altra macchina o senza docker il
  controllo resta (se SearXNG è raggiungibile) e l'aggiornamento si spegne con il suo perché
  (nel cruscotto niente «Aggiorna»); senza `web_searxng_url` o con `online: false` niente.
- **Non a voce**: non c'è un tool per cambiare le impostazioni; il modo si cambia in
  `calliope.locale.yaml` (sezione web) con un riavvio.
- **Prove** (09/10): `prova_searxng_aggiorna` 5 s, tutto finto (SearXNG, registro, docker; lo
  script con il bash di Git e un `docker` finto che registra i comandi), livello 2 legato a
  `calliope/web/`, allo script, al cruscotto e alle capacità; `prova_cruscotto_pagina` con i
  due pulsanti nella pagina vera. Niente rete vera.

**Prima prova vera sulla DGX (da fare, non fatta il 09/10).** Dopo `calliope aggiorna` con
questo ramo, da terminale:

1. `calliope motore searxng stato` (container, immagine in uso, JSON acceso);
2. `calliope motore searxng novita` (solo il registro delle immagini: i tag e la loro età);
3. `calliope motore searxng controlla` (le tre ricerche di prova: risultati, motori, motori
   giù con il motivo; esce con 3 se degradata);
4. `calliope motore searxng aggiorna` (scarica il tag più recente, lo prova accanto sulla
   porta 10004, cambia o resta; durata attesa 1–3 minuti, pochi secondi senza ricerca);
5. `calliope motore searxng storia` e `calliope motore searxng stato`; in caso di guai
   `calliope motore searxng dimentica` e `calliope motore searxng avvia` tornano all'immagine
   fissata nello script.
Poi il cruscotto dal telefono di chi amministra: sezione «Ricerca web (SearXNG)», «Controlla»
con due tocchi. Da verificare sul vero: tempo del `docker pull` sulla DGX, che `docker image rm`
non tocchi l'immagine dell'altro SearXNG, i motivi veri di `unresponsive_engines`, e se le
soglie (3 risultati, 0,6) reggono un giorno normale senza falsi «degradata».

## Approfondire dopo una ricerca (09/10, ramo `approfondisci-notizie`)

Caso vero della DGX (09/10, 10:21): dopo le notizie con `web_cerca`, «Approfondiamo le
condizioni [del re]» → «non ho informazioni più dettagliate» senza cercare: la regola
`approfondisci` cercava nella biblioteca la frase di prima («altre news…») e il testo dei siti era
già uscito dalla storia. Ora, dopo una ricerca (web o biblioteca) nei due turni prima, il modello
ha nei dati del turno l'ultima ricerca e l'indicazione di cercare di nuovo con una domanda mirata
(`RICERCA_MSG`, rete `ricerca_recente`), la spinta su «non ho altre informazioni» senza cercare
(`spinta_ricerca`), e `approfondisci` non rifà la biblioteca (`approfondisci_al_modello`). Con la
ricerca su internet non disponibile, i dati del turno dicono di ammetterlo. Dettagli e misure:
[voce-e-regole](voce-e-regole.md); prove `prova_web` (6b) e `prova_ricerca_seguito_ollama`.

## Le notizie per tema e il meteo della casa (09/10, ramo `citta-casa-notizie`)

Due casi veri della DGX (09/10, 10:30): «Sentimi le notizie di sport» → `web_cerca` tipo
notizie → «le notizie che ho trovato non contengono aggiornamenti sportivi»; «Che tempo fa?»
senza città → ricerca generica, «non so dove ti trovi… se mi dici la tua città».

- **Cosa arrivava a SearXNG** (`Web.cerca`): la domanda del modello com'era («notizie sport»,
  «ultime notizie»), categoria `news`, nessun periodo. Misura in sola lettura sul SearXNG della
  DGX (richieste HTTP dalla DGX stessa, 09/10 mattina): nella categoria news la parola «notizie»
  non filtra niente e pesa come un tema. «notizie di economia» → titoli con «notizia» dentro
  (Nobel, il Brasile, «ottima notizia» per lo sport di Foggia), «economia» → solo economia;
  «notizie sport» → 13 risultati, ANSA con «buone notizie per Allegri» e articoli vecchi in
  testa, «sport» con una settimana → 40 risultati, tutti di sport e recenti; «Torino» con una
  settimana → cronaca di Torino. Senza periodo DuckDuckGo News metteva tra i primi pagine del
  2021 e 2022; con `day` Bing News dava titoli in portoghese e spagnolo («economia») e per
  temi piccoli quasi niente. Attenzione: una ventina di ricerche di fila fa smettere ANSA e
  DuckDuckGo per qualche minuto (risultati da 40 a 1–5): le misure vanno fatte con poche
  richieste.
- **Correzione** (`calliope/web/servizio.py`): con tipo notizie la domanda perde le parole che
  dicono «notizie» (`tema_notizie`: notizie, news, novità, ultime notizie, ultim'ora,
  aggiornamenti, in tempo reale) e le preposizioni rimaste in testa o in coda, mai gli articoli
  dei nomi («La Spezia», «Il Sole 24 Ore»); senza tema resta «notizie». In più
  `time_range=week` (`PERIODO_NOTIZIE`). Conversione della forma di una scelta del modello
  (principio 10), regola `notizie_tema` nel registro dei turni; il tipo `web` non cambia.
  La descrizione di `web_cerca` chiede il tema o il luogo nella domanda delle notizie.
  Contrari a secco in `prova_web.py` (tipo web, «sport» già senza la parola, «Ultime parole
  famose», «le ultime dal fronte», «notiziario», «Newsweek», «ultime notizie su» dopo il filtro
  della privacy → «notizie»).
- **Il meteo della casa**: il campo nuovo `casa_citta` e le estensioni prima di internet, in
  [voce-e-regole](voce-e-regole.md) (stessa data). Con gemma4 e4b: `prova_citta_casa_ollama`.

## Le notizie senza tema (09/10, ramo `ricerche-distanza`)

Giro di prova vero della DGX (09/10, 11:03): «Le ultime notizie» → tre
`web_cerca({'tipo': 'notizie'})` fermati per «domanda» mancante (`tool_argomenti_mancanti`) e la
quarta giusta, prima frase 5,1 s. Il contratto chiedeva il tema nella domanda anche quando non
c'è.

- **Contratto**: nello schema di `web_cerca` (`calliope/tools/web.py`, `PARAMETRI`) `domanda`
  non è più obbligatoria; la descrizione dice che per le notizie è facoltativa («senza, le ultime
  notizie generali») e obbligatoria per tipo «web». Con tipo «notizie» e senza domanda si cerca
  «notizie» (che `tema_notizie` lascia com'è, dell'ultima settimana), regola `notizie_generali`.
  Con tipo «web» (o senza tipo) e senza domanda la funzione risponde con lo stesso errore dello
  schema (`dialogo.errore_argomenti`, correggibile, fuori dalla busta dei dati non fidati),
  regola `tool_argomenti_mancanti`. Unico costo: per `web_cerca({})` la frase d'attesa «Cerco su
  internet» si dice prima dell'errore (il registro non vede più l'obbligo nello schema).
- **Il tetto dei giri di correzione** che non aveva fermato i tre giri:
  [voce-e-regole](voce-e-regole.md) (stessa data).
- **Misura** con gemma4 e4b locale (`prova_ricerche_distanza_ollama`, SearXNG finto): il 4B
  mette sempre una domanda («ultime notizie»), quindi il caso vero non si riproduce qui; 3/3
  senza chiamate fermate, prima frase mediana 1,9 s. Il caso senza domanda è a secco in
  `prova_dialogo_tool`.
- **Fonte nell'archivio**: le conversazioni ritrovate dicono se l'informazione veniva dalle
  notizie su internet o dalla biblioteca, così «dimmi di più» può cercare di nuovo nello stesso
  posto: [contesto-conversazione](contesto-conversazione.md) (stessa data).

## Risultati in italiano per primi (09/10 pomeriggio, ramo `meteo-casa`)

Caso vero della DGX (09/10, 12:54): «cercami qual è la miglior salsa di pomodoro» → risultati da
un sito spagnolo e da uno in un'altra lingua. La lingua a SearXNG c'era già (`language=it-IT`,
`web_lingua`, per web e notizie): con la stessa domanda sulla DGX (una richiesta, in sola
lettura) DuckDuckGo dava solo siti italiani, **Bing li ignorava** e metteva in mezzo pagine di
Baidu e Zhihu in cinese, forum di Taiwan, forum francesi e tedeschi (Brave era fermo per «too
many requests»).

- **Preferenza** (`calliope/web/servizio.py`: `lingua_risultato`, `Web.cerca`): ogni risultato è
  «it», «altra» o incerto dalle parole più comuni di titolo ed estratto (italiane contro inglesi,
  spagnole, francesi, tedesche, portoghesi), dal dominio `.it` e dalle scritture non latine. I
  vecchi restano in fondo; a pari età prima gli italiani, poi gli incerti, poi le altre lingue.
  Nessun risultato si toglie: se gli italiani mancano restano gli altri. Vale per web e notizie,
  solo con `web_lingua` italiana. Sui 15 risultati veri della DGX: i 7 di DuckDuckGo «it», 4 di
  Bing «altra» (Baidu, in cinese), 4 incerti (forum francesi e tedeschi con titoli brevi): i primi 5 dati al modello sono tutti
  italiani.
- **Un'altra lingua chiesta** (`ALTRA_LINGUA`, sulla domanda già scritta dal modello): «in
  inglese», «english», «site:…», «siti spagnoli», «giornali stranieri» → `language=all` e
  l'ordine di SearXNG. Contrari: «ristorante inglese», «calciatori stranieri», «notizie
  internazionali», «lavorare all'estero», «lezioni di spagnolo».
- **Configurazione**: `web_preferisci_lingua` (predefinito true; false = l'ordine di SearXNG).
  Registro dei turni: `web_lingua_preferita` (qualcosa è finito in fondo), `web_altra_lingua`.
- **Prove** a secco in `prova_web` (SearXNG finto suo, così i conteggi delle richieste di sopra
  non cambiano). Da valutare con Dario: togliere Bing dai motori di SearXNG (`settings.yml`),
  visto che con `it-IT` dà risultati fuori lingua e fuori tema.

