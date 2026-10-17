# Biblioteca offline e ricerca web

*Wikipedia italiana e le altre fonti Kiwix in puro Python con FTS5; ricerca su internet con SearXNG. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

**Stato al 16/10.** Come al 14/10 (sotto), più la **pertinenza dei risultati** verso la conversazione (`calliope/pertinenza.py`, #101, PR #115): una misura in `web_cerca` e `biblioteca_cerca`, in ombra di serie (`ricerca_pertinenza`), mai un filtro, riassunta in `calliope stato --turni`; con «attiva» il risultato fuori tema arriva al modello con la frase da dire (sezione «Risultati fuori tema», in fondo). La quota delle risposte dai feed dal 17/10 è nella riga «Notizie» di `calliope stato --turni` (#31, PR #128; prima lettura del 17/10 in fondo); *[storico, 16/10: era solo nel registro dei turni]*.

*Stato al 14/10 (storico dal 16/10: la quota dei feed non era ancora in `--turni`, vedi sopra).* Biblioteca e ricerca web come al 09/10 (sotto). Dal 13/10 le notizie hanno un tool loro, `notizie` (sola lettura, livello `notizie_livello`, di serie ospite): feed RSS delle testate scaricati in casa (`calliope/notizie/`, solo libreria standard), 5 fatti per elenco (`notizie_fatti`), i fatti detti restano nella storia in busta, minori solo sport, tecnologia e ragazzi, SearXNG come ripiego; con lui `web_cerca` non ha più il tipo «notizie» (sezione in fondo). Notizie è la diciannovesima capacità del registro. Da guardare sulla DGX: la quota delle risposte dai feed, dal 17/10 nella riga «Notizie» di `calliope stato --turni` (issue #31, sezione in fondo, con la prima lettura del 17/10).

*Stato al 09/10 (storico): biblioteca e ricerca web invariate dalla pubblicazione (07/10). Dall'08/10 notte il testo dei siti letto dall'agente (`web_leggi`) arriva in busta come ogni dato non fidato, e i nomi pubblici di casa sono vietati nella rete delle estensioni e dell'agente ([agenti-estensioni](agenti-estensioni.md)). Restano aperti le tabelle delle voci non lette e i «perché…?» che trovano titoli omonimi. Dal 09/10 SearXNG si tiene aggiornato da solo (controllo quotidiano, aggiornamento provato accanto con il ritorno indietro, «Controlla» e «Aggiorna» nel cruscotto: sezione in fondo); la prima prova vera sulla DGX è da fare.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Biblioteca offline | Wikipedia italiana in ZIM di Kiwix, letta in puro Python (solo libreria standard, solo CPU) con un indice SQLite FTS5 accanto; niente `libzim` dal 01/10 | `calliope/biblioteca.py` → `Biblioteca.cerca`, `load_biblioteca`; `calliope/zim.py` → `ZimFile`; `calliope/biblioteca_indice.py` → `costruisci`, `apri`, `stato_indice`; tool `biblioteca_cerca`; file in `biblioteca/` (`scarica.sh`), indici in `biblioteca/indici/` |
| Ricerca su internet (facoltativa, solo con la rete) | SearXNG in un container di Calliope sulla DGX (`calliope-searxng`, 127.0.0.1:8004, niente log; `setup/linux/motore/searxng.sh`), httpx in POST; pagine con http.client e html.parser, senza SSRF | `calliope/web/` → `Web` (`servizio.py`), `Ripulitore` (`privacy.py`: niente dati personali nelle domande), `scarica`, `estrai_testo` (`pagina.py`), `load_web`; tool `web_cerca` in `calliope/tools/web.py`; `web_cerca` e `web_leggi` dell'agente in `calliope/agenti/ciclo.py`; solo letture dopo un risultato web: `politica.DOPO_DATO` (`politica.bloccata`) |
| Notizie dai feed RSS (13/10) | feed delle testate scaricati in casa ogni 2 ore (solo se qualcuno chiede notizie), xml.etree, SQLite; la domanda non esce; SearXNG come ripiego | `calliope/notizie/` → `Notizie` (`servizio.py`), `elenco` (`feed.py`), `scarica`, `leggi` (`lettore.py`), `titolo_per_voce` (`pulizia.py`), `raggruppa` (`gruppi.py`), `riduci` (`contesto.py`); tool `notizie` in `calliope/tools/notizie.py` (sezione in fondo) |
| SearXNG tenuto aggiornato (09/10) | ricerche di prova fisse in POST, registro delle immagini (Docker Hub) con tag e digest, docker tramite lo script | `calliope/web/motore.py` → `MotoreRicerca` (`controlla`, `aggiorna`, `passo`, `avvia_azione`), `giudica`, `almeno_come`, `tag_recenti`; `setup/linux/motore/searxng.sh` (`candidata`, `usa`, `pulisci-immagini`…); `calliope motore searxng controlla|aggiorna|novita|storia` |
| Pertinenza dei risultati verso la conversazione (16/10, #101) | parole piene in comune con la frase e con gli ultimi messaggi, solo libreria standard; un dato, mai un filtro; `ricerca_pertinenza` ombra di serie | `calliope/pertinenza.py` → `misura`, `applica`, `modo`, `riassunto`; chiamato da `web_cerca` (`calliope/tools/web.py`) e `biblioteca_cerca` (`calliope/tools/builtin.py`); riassunto in `calliope stato --turni` (sezione «Risultati fuori tema») |

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

**Prima prova vera sulla DGX (da fare, non fatta il 09/10).** *(16/10, #82: il controllo
quotidiano gira, l'ultimo controllo della DGX in `motore/searxng.json` è citato sotto in «Ricerche
lente»; dei passi 1–5 e di «Aggiorna» dal cruscotto non c'è traccia nei documenti: restano da
fare, o da segnare fatti con la data da chi amministra.)* Dopo `calliope aggiorna` con
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
  non cambiano). *Storico (09/10 pomeriggio):* «da valutare con Dario: togliere Bing».
  **Deciso da Dario il 09/10: Bing web tolto** dai motori (`setup/linux/motore/searxng.sh`,
  `ENGINES`; Bing News resta per le notizie). Si applica al prossimo avvio del container
  (`calliope motore searxng avvia` o un aggiornamento dell'immagine, che riscrive le impostazioni).

## Notizie senza tema, ricerche con la loro fonte, motori in pausa (09/10 sera, ramo `sera-ricerca`)

Tre casi veri della DGX del 09/10 sera (registro e journal).

**Notizie a tema senza tema** (21:04:34): «Le notizie di sport» → `web_cerca({'tipo':
'notizie'})` senza `domanda` (facoltativa dal ramo `ricerche-distanza`) → notizie generali e
«le notizie sportive non sono arrivate tramite la ricerca». Ora, con tipo notizie e senza
domanda, `web_cerca` prende il tema dalla frase di chi parla (`servizio.tema_dalla_frase`): le
parole dopo «notizie» (o news, novità, aggiornamenti) fino alla fine dell'enunciato (punto,
virgola, «e poi»), senza preposizioni ai bordi (mai gli articoli dei nomi: «Notizie su La
Spezia» → «La Spezia»), senza «ci sono», «c'è» in testa né il tempo («di oggi», «del giorno»,
«recenti», «per favore»); più di sei parole non è un tema. Regola `notizie_tema_frase`; se non
resta niente, notizie generali come prima (`notizie_generali`). Conversione della forma di una
scelta già fatta dal modello (principio 10). Contrari a secco in `prova_web` («Calliope. Le
ultime notizie.», «notizie di oggi», «le notizie più recenti», «Leggimi le notizie, per favore»,
«Che si dice nello sport?» → generali) e `prova_dialogo_tool` (con la domanda del modello vale
quella).

**«Dimmi di più» sulla fonte sbagliata** (21:06:06): notizie della tromba marina con `web_cerca`
(21:04:57), poi timer, ora e la Torre di Pisa con `biblioteca_cerca`; «Torniamo alla notizia del
trapanese di prima. Dimmi di più.» → `biblioteca_cerca` e una risposta vaga. `RICERCA_MSG` diceva
solo l'ultima ricerca, quella della biblioteca. Ora elenca le ricerche della conversazione con la
loro fonte; e la descrizione dei due tool e il risultato della biblioteca con passaggi fuori tema
dicono il criterio «biblioteca per i fatti da enciclopedia, internet per guide pratiche, consigli,
prodotti e cose recenti» (caso delle 18:47: tre `biblioteca_cerca` per «tecniche di produzione
casalinga della birra», passaggi su un film di Chaplin, internet solo dopo averlo proposto).
Dettagli in [voce-e-regole](voce-e-regole.md) (stessa data).

**Ricerche lente** (notizie 7,9 s, approfondimento 5,5 s, web 5–6 s alla prima frase, 18:49–18:52 e
20:37). La prima frase comprende due passate del modello; la parte di SearXNG è al più il suo
timeout: SearXNG aspetta il motore più lento fino a `request_timeout`. Ultimo controllo della DGX
(`motore/searxng.json`): «meteo Roma domani» **3006 ms**, risultati solo da DuckDuckGo, Brave «too
many requests» e Wikidata in timeout; «Serie A risultati» 3006 ms con ANSA in timeout; «notizie
Italia oggi» 513 ms (Google News «access denied» risponde subito). Misura in sola lettura sul
SearXNG della DGX (tre richieste a 20 s l'una dall'altra, «meteo Roma domani», 09/10 sera): così
com'è 1428 ms; con `timeout_limit` 2,0 655 ms; con 2,0 e senza Brave e Wikidata 520 ms. In
tutte e tre i risultati venivano solo da DuckDuckGo: Brave «Suspended: too many requests», Qwant
«CAPTCHA», Startpage e Mojeek niente. Correzioni (`calliope/web/motore.py`,
`setup/linux/motore/searxng.sh`):
- **Motori in pausa** (`aggiorna_motori`): per ogni motore il conto dei controlli di fila in cui
  non risponde mentre nella stessa prova un altro dà risultati (se nessuno risponde manca
  internet: non conta); chi dà risultati azzera il conto. A `web_searxng_pausa_controlli` (2)
  il motore va in pausa: `searxng.sh pausa MOTORE…` scrive `~/calliope-motore/searxng/in-pausa`,
  rifà le impostazioni senza di lui (anche nelle voci delle notizie: un motore nominato lì e non
  in `keep_only` sarebbe un errore) e rifà il container, in automatico solo a Calliope ferma
  (altrimenti al prossimo controllo); se SearXNG non riparte si torna alle pause di prima, con
  l'errore nella storia. Dopo `web_searxng_pausa_giorni` (3) si riprova; un altro controllo
  fallito lo rimette subito in pausa. Con meno di `web_searxng_min_motori` (3) motori che danno
  risultati e qualcuno in pausa la ricerca è «degradata» (il motivo dice chi è in pausa). Stato
  (`motori`, `in_pausa`), storia (evento «motori»: «metto in pausa brave (too many requests)»,
  «riprovo …») e vista del cruscotto (`in_pausa` con il perché). Su Windows o senza docker
  niente pause. `0` controlli = mai. Le pause le gestisce il controllo: una pausa messa a mano
  con `calliope motore searxng pausa …` vale fino al prossimo cambio deciso dal controllo.
- **Timeout**: `request_timeout` 2,0 s per i generali (DuckDuckGo risponde in 0,5–1,4 s), le
  notizie (Bing News, DuckDuckGo News, Google News, ANSA) a 3,0 s con `timeout` per motore: ANSA
  a volte è lenta e senza di lei le notizie italiane sono più povere. Guadagno atteso: fino a 1 s
  per ricerca generale quando un motore non risponde, tutto il tempo d'attesa quando quel motore
  è in pausa (sulla DGX, con Brave e Wikidata in pausa, ~0,5 s invece di 3 s).
- **Si applica** al prossimo avvio del container (`calliope motore searxng avvia`, un
  aggiornamento dell'immagine o la prima pausa decisa dal controllo): `calliope aggiorna` da solo
  non rifà SearXNG.
- **Prove** a secco in `prova_searxng_aggiorna` (conto, pausa, ripresa, contrari: tutti giù,
  risultati in un'altra prova, 0 controlli; degradata con pochi motori; automatico in uso; script
  che non riesce; Windows; lo script con il docker finto: `in-pausa`, impostazioni, timeout,
  motore sconosciuto rifiutato, pause tolte).

**«Forse intendevi…?» non scattato** (20:47–20:48, collaudo di Meteocittà): in
[stt-tts](stt-tts.md) (stessa data).

**Misura col modello** (gemma4 e4b sul portatile, SearXNG e biblioteca finti,
`prove/misura_ricerche_fonte.py 3`, 3 giri per lato, «prima» col codice di main): «torniamo alla notizia del trapanese di prima» dopo
notizie, ora, un conto e la Torre di Pisa nella biblioteca → `web_cerca` con «tromba
marina/Marsala» **3/3 prima e 3/3 dopo** (il 4B ci arrivava già: il guasto del caso vero è del
26B, da riguardare sulla DGX), prima frase mediana 2,9 s prima e 2,0 s dopo; «Quali sono le
tecniche per fare la birra in casa?» → `web_cerca` **0/3 prima** (sempre `biblioteca_cerca` e una
risposta a memoria) **e 3/3 dopo**.

## Notizie dai feed RSS: il tool `notizie` (13/10, ramo `notizie-rss`)

Dalle due ricerche [`2026-10-12-notizie-rss.md`](../ricerche/2026-10-12-notizie-rss.md) e
[`2026-10-13-notizie-rss.md`](../ricerche/2026-10-13-notizie-rss.md) (§ 6, la proposta) e dalle
**decisioni di Dario del 13/10**: si tengono le testate che chiudono il `robots.txt` agli agenti
delle IA (ANSA, Rainews…); Il Post e Il Sole 24 Ore **spenti di serie**, accesi per nome nel
locale; un tool nuovo `notizie` di sola lettura al posto del tipo «notizie» di `web_cerca`, con
SearXNG come ripiego; feed regionale ANSA dalla città di casa; minori solo sport, tecnologia e
Focus Junior; ospiti sì; le notizie le dice **il modello**, e ciò che ha detto **resta nel
contesto**; lettore con la libreria standard; scarico in secondo piano ogni 2 ore.

- **Pacchetto** `calliope/notizie/` (solo libreria standard, niente da verificare su ARM, nessuna
  riga in `TERZE-PARTI.md`): `feed.py` (righe «testata | tema | indirizzo | opzioni», testate
  spente e accese, regione ANSA dalla città: capoluoghi di provincia e qualche città grande, per
  intero, «no» per nessuna; i 20 indirizzi regionali provati il 13/10), `lettore.py` (scarico con
  i controlli delle pagine dell'agente, `Accept-Encoding: identity` e una risposta compressa
  rifiutata, 2 MB al più, ETag e Last-Modified, User-Agent `Calliope/0.3 (lettore di feed
  personale)`, certificato sempre verificato; lettura RSS 2.0 e Atom con `xml.etree` e i feed con
  `<!ENTITY` rifiutati prima del parser; date RFC 822, ISO 8601 e in italiano, l'ora italiana
  marcata GMT con `fuso=Europe/Rome` del feed, l'ora legale calcolata senza tzdata), `pulizia.py`,
  `gruppi.py`, `servizio.py` (`Notizie`: indice SQLite `notizie_db`, scarico, fatti, stato),
  `contesto.py` (la forma ridotta dei fatti nei turni vecchi). Tool in `calliope/tools/notizie.py`.
- **Quando si scarica**: ogni `notizie_intervallo_min` (120) solo se qualcuno ha chiesto notizie
  negli ultimi `notizie_attesa_giorni` (7); i feed `veloce` (Adnkronos, AGI: il primo cambia 20
  voci in un'ora) ogni ora nei giorni in cui qualcuno le chiede; la prima richiesta dopo una
  pausa (indice più vecchio dell'intervallo e mezz'ora) scarica subito, al più 4 s, con «Un
  attimo, guardo i giornali» se ci vuole. Sei feed alla volta, il `robots.txt` di ogni sito letto
  una volta al giorno (per `Calliope`; se non si legge, il feed resta permesso), un feed che
  fallisce non ferma gli altri. Voci oltre `notizie_conserva_giorni` (7) cancellate a ogni scarico.
- **Pulizia** (principio 10: conversioni della forma, ogni regola col suo nome sulla voce e nel
  registro dei turni quando la voce è detta, casi contrari in `prova_notizie`):
  `notizie_titolo_virgolette` (dritte, curve, apici come virgolette → «», mai l'apostrofo),
  `notizie_titolo_agenzia` («++ … ++», «>ANSA-FOCUS/»), `notizie_titolo_marcatore` (VIDEO, LIVE…
  in maiuscolo, solo in testa o in coda), `notizie_titolo_doppio` («… in diretta | il fatto»),
  `notizie_titolo_troncato` (AGI: la prima frase del sommario), `notizie_sommario_coda`
  (WordPress), `notizie_sommario_sigla` (la testata in testa, mai una città),
  `notizie_non_notizia` (episodi, newsletter, «Puntata del…»; un link /video/ di Rainews resta).
- **Fatti** (`gruppi.py`): coseno TF-IDF sulle radici (6 lettere) di titolo e 200 caratteri del
  sommario, solo testate diverse entro 24 ore, soglia 0,30, e il tetto contro le catene (due
  gruppi si uniscono solo se almeno metà delle coppie è simile almeno 0,20). Per «le notizie di
  oggi» i fatti dei feed generali delle ultime 24 ore, ordinati per **testate generali** (una
  notizia di calcio data da cinque testate sportive non apre più le notizie del giorno), poi per
  testate in tutto e recenti; il titolo più corto del gruppo (almeno 25 caratteri), il sommario
  più recente. Per un argomento le radici della biblioteca («scioperi» → «sciopero»), tutte le
  parole (una meno da tre in su). I fatti già detti a quella persona in fondo (6 ore).
- **Il tool** `notizie(tema?, fatto?)`: senza argomenti tre fatti numerati (titolo, testate,
  quando a parole: «stamattina alle 9:40», «ieri sera», «sabato»; «di recente» senza data;
  «vecchio» oltre 3 giorni), mai indirizzi; `tema` una sezione (sport, economia, tecnologia,
  locale, ragazzi, allerta; altre parole per le sezioni: regola `notizie_sezione`) o le parole di
  un argomento; vuoto, il tema dalla frase di chi parla come per `web_cerca`
  (`notizie_tema_frase`); `fatto` = il numero detto («dimmi di più sulla seconda»), risolto
  sull'ultimo elenco di **quella persona**: tutte le testate del fatto, ognuna con il suo sommario
  (`notizie_seguito`). Regole nel registro: `notizie_feed`, `notizie_ripiego`, `notizie_seguito`,
  `notizie_sezione`, `notizie_tema_frase`, `minore_notizie`, `web_notizie_al_tool` e le pulizie
  delle voci dette. Il tema non va nel registro (`segreti`, come la domanda di `web_cerca`).
- **Ripiego su SearXNG** (`notizie_ripiego`, categoria news come prima): meno di 2 voci
  sull'argomento nelle ultime 72 ore, nessun fatto, indice più vecchio di 6 ore. Solo per chi può
  usare `web_cerca` (`web_livello`) e mai per un minore; altrimenti si dice ciò che c'è con la sua
  data, o che nei giornali scaricati non c'è niente.
- **`web_cerca` senza il tipo «notizie»** quando c'è il tool `notizie` (schema con la sola
  `domanda`, obbligatoria; la descrizione rimanda a `notizie`); una chiamata con il tipo rimasta
  nell'abitudine del modello va alle notizie dei feed (`web_notizie_al_tool`). Senza il tool
  (notizie spente) `web_cerca` resta com'era. Gli schemi passano da 77 a **78** (togliere il tipo
  non toglie uno schema; *storico: vero il 13/10, dal 14/10 i tool sono 75 contati sul registro,
  CLAUDE.md*). Prompt: «Per le notizie (di oggi, di sport, di economia, della zona o
  su un argomento) chiama notizie…», e le notizie escono dalla frase di `web_cerca` e da «Non puoi
  sapere…»; senza il tool, il prompt di prima parola per parola.
- **Capacità** «notizie dai giornali» (19 nel registro): spente, senza rete, configurate, attiva
  con le voci, i feed fermi (età dell'ultima voce per tema: generali e sport 2 giorni, tecnologia
  7, ragazzi e allerta 14) e guasti; «degradata» con metà dei feed che non si leggono, «guasta»
  se nessuno risponde. Nell'area «le ricerche» di «cosa sai fare?».
- **Feed di serie** (file d'esempio): ANSA ultima ora e top news, Rainews, Sky TG24 (fuso), AGI,
  Adnkronos (generali); Gazzetta, ANSA sport, Corriere dello Sport; ANSA ed Adnkronos economia;
  HDblog, Punto Informatico, ANSA tecnologia; Focus Junior (ragazzi); i due bollettini della
  Protezione civile (allerta); Il Post e i due feed del Sole 24 Ore nell'elenco ma spenti.
  **Per accenderli**, in `calliope.locale.yaml`, sezione `notizie`:
  `notizie_accese: [Il Post, Il Sole 24 Ore]`. Una testata della città: `notizie_feed_extra`.
- **Misure** (portatile, 13/10): sull'istantanea della ricerca (52 feed, 1 857 voci) lettura,
  inserimento e gruppi in 0,62 s, ricarica dell'indice con i gruppi 0,39 s, una ricerca
  0,6–0,8 ms; sui feed veri (21 di serie con Il Post, il Sole e la Lombardia) primo scarico
  2,5 s, il secondo condizionato 1,1 s (Adnkronos una volta «certificato non valido», poi a posto;
  il Sole 24 Ore 503 in quel momento). Col modello (`prova_notizie_ollama`, gemma4 e4b, 2 giri):
  12/12, «dimmi di più sulla seconda» con `notizie` fatto 2, «e quale giornale lo dice?» dalle
  testate rimaste nel contesto senza tool, un sommario con istruzioni 0 azioni; prima frase
  mediana 1,45 s.

**I fatti restano nel contesto** (decisione 7, il punto delicato). Il risultato di `notizie` è
un dato non fidato come quello di `web_cerca`: busta della fonte «web» (avviso, contenuto dentro,
`cosa_fare` e `nota` fuori), `politica.DOPO_DATO` (nella stessa risposta, dopo il risultato, solo
letture; `notizie` è anche tra quelle), provenienza (la conversazione resta contaminata finché la
busta c'è: la politica per valore chiede per un argomento preso dalle notizie). Ma **non esce
dalla storia** a risposta finita: `ToolSpec.resta_in_storia` (Brain `_togli_non_fidati` lo salta;
nelle proiezioni del registro degli eventi il campo `resta` di `esito_tool`). Il turno dopo ha il
risultato intero (come ogni tool: `_compact_old_results` riduce solo i risultati dei turni prima
del precedente); dal secondo turno dopo, invece della traccia generica «richiama il tool», la
**forma ridotta** di `contesto.py`: numero, titolo, testate e quando di ogni fatto, sempre in
busta (`nota`: «per i dettagli richiama notizie con fatto = il suo numero»). Su disco, nel
registro degli eventi, il contenuto resta ridotto ai caratteri come per ogni non fidato: dopo un
riavvio i fatti non ci sono più e il modello richiama il tool. Provato a secco in `prova_notizie`
(§ 8: la seconda domanda arriva al modello con titoli, testate e sommari; due e quattro turni
dopo la forma ridotta; le proiezioni uguali).

**Minori** ([minori](minori.md)): solo i feed di sport, tecnologia e ragazzi; le notizie
«generali» per loro sono quelle di questi temi, e un fatto dato anche dai generali ha solo le
voci dei loro feed; il filtro dei contenuti per adulti (`minore_contenuto_adulto`); una sezione
per adulti («economia») ha la frase pronta «Per te ho le notizie di sport, di tecnologia e
quelle per ragazzi» (`minore_notizie`); niente ripiego su internet. Il preset «internet» non
c'entra: la domanda non esce.

**Da guardare sulla DGX**: la quota delle risposte dai feed (`notizie_feed` contro
`notizie_ripiego`: dal 16/10 la riga «Notizie» di `calliope stato --turni`, issue #31; *[storico,
fino al 16/10: il comando non la stampava]*), l'età della notizia più recente detta, i feed
fermi nella capacità, la durata dello scarico nel log (`[NOTIZIE] scarico: …`). Restano dalla
ricerca: la lettura senza modello (proposta § 6.4, non fatta: le dice il modello), la scheda con
le immagini (no), i bollettini della Protezione civile detti solo con data e ora (il contenuto è
nel PDF, che non si scarica).

**13/10 sera — 5 fatti invece di 3.** Su richiesta di Dario l'elenco di «che notizie ci sono?» dà
5 fatti unici (ognuno con tutte le testate che lo riportano: i doppioni sono già raggruppati),
dalla Config `notizie_fatti` (5 di serie, tenuto tra 1 e 10). Prova in `prova_notizie`.

## Risultati fuori tema: dirlo invece di riferirli (16/10, issue #101)

Tre casi veri della DGX del 15/10 sera (problema 9 dell'analisi del 16/10): dopo un racconto sul
mito di Orione, «approfondiamo questo argomento» → `web_cerca` con una domanda storpiata, risultati
su una startup dal nome simile a una parola della conversazione, riferiti per intero nonostante il
`cosa_fare` (prima frase 4,33 s); `biblioteca_cerca('mito di Orione e la sua storia
astronomica')` → voci omonime, e il modello rispondeva da sé sbagliando il mito; tre minuti dopo
una lettura con `notizie`, dichiarazioni attribuite a un altro politico (i sommari non erano più
nella storia). Fatto:

- **`RICERCA_MSG` senza «web_cerca tipo notizie»** (brain.py): dal 13/10 le notizie hanno il loro
  tool e `web_cerca` non ha più il tipo; la riga diceva ancora di usarlo. Con il tool notizie
  dice «(le notizie con notizie)», e un `web_cerca` col tipo rimasto nella storia vale come
  `notizie` (la spinta richiama quello); senza il tool notizie la fonte è «web_cerca (notizie)».
  Due frasi in più: «se i risultati non riguardano ciò di cui parlavate, non riferirli: dillo e
  chiedi cosa cercare», e dei risultati che non ha più davanti non citare nomi, cifre o
  dichiarazioni a memoria.
- **`notizie` nell'elenco delle ricerche** (`RICERCA_TOOLS`, con il tema o «notizia N»): la riga
  delle ricerche c'è anche dopo le notizie, e «approfondisci» dopo le notizie va al modello
  (`approfondisci_al_modello`) invece di rifare la biblioteca con la domanda di prima. Il criterio
  biblioteca/internet resta sulle due fonti (`RICERCA_FONTI`).
- **Misura di pertinenza** (`calliope/pertinenza.py`, solo libreria standard): un dato, mai un
  filtro (principio 10), con l'interruttore `ricerca_pertinenza` (sezione web): **ombra di serie**
  (revisione della PR #115), «attiva» o «spenta». Un risultato è «pertinente» se ha almeno una
  parola piena in comune con la frase di chi parla, o con gli ultimi quattro messaggi della
  conversazione (`ToolContext.storia`): due, o una sola quando la frase è breve (fino a cinque
  parole) e ha parole sue («e domani?» dopo il meteo, «e adesso chi è primo?»). La domanda
  composta dal modello non conta, perché è quella che può uscire storpiata. Parole piene: da
  quattro lettere fuori da un elenco di parole vuote e di cornice («approfondiamo», «argomento»,
  «dimmi»…), più le sigle («PIL», «NBA», «F1») e i nomi brevi con la maiuscola («Eco»). Stessa
  parola: senza le vocali finali («gatti» e «gatto», «Orione» e «Orion»), una che continua l'altra
  con una vocale («Roma» e «romano», non «Orione» e «Orionyx»), l'ultima lettera della radice
  («vinto» e «vince»), una lettera di differenza da cinque lettere («Siner» di Whisper e
  «Sinner»). Restano falsi «fuori tema» che per parole non si vedono: sinonimi («macchina» e
  «vetture»), sigle sciolte nei risultati («IVA» e «imposta sul valore aggiunto»), l'inglese senza
  nomi in comune, un seguito senza nomi («e domani?» con risultati che non nominano la città),
  «e ieri chi ha vinto?» con «il campione italiano batte lo spagnolo». Per questo resta in ombra
  finché non si rileggono i turni veri.
  - **In ombra**: niente al modello; il registro dei turni ha `ricerca_pertinenza_misurata` a ogni
    ricerca misurata e `ricerca_fuori_tema_ombra` quando è 0. **Attiva**: in più `web_cerca` e
    `biblioteca_cerca` scrivono `pertinenti: "0 su 2 (nessun risultato ha parole in comune con ciò
    di cui state parlando: probabilmente parlano d'altro)"`, fuori dalla busta dei dati non fidati
    (`provenienza.CONTROLLO`), con la regola `ricerca_fuori_tema`, e il `cosa_fare` rimanda a quel
    campo. Senza niente con cui confrontare (frase di sole parole vuote, nessun turno prima) non si
    misura.
  - **`calliope stato --turni`**: la riga «Pertinenza delle ricerche (ombra): N «fuori tema» su M
    turni con ricerche misurate (… %; in ombra …, detti al modello …)». Prima di «attiva»:
    rileggere i turni con `ricerca_fuori_tema_ombra`.
  - **Tempo** (portatile, revisione): 0,29 ms con 5 risultati di ~290 caratteri e la storia, ~3 ms
    con 10 testi di ~3000 caratteri.
  - Il `cosa_fare` dei due tool dice sempre di non riferire i risultati fuori tema e di chiedere
    cosa cercare; quello della biblioteca risponde a memoria solo se è sicura (il caso del lago di
    Garda del 26/09 resta), altrimenti dice che non ha trovato.
- **Cosa resta nella storia** (revisione): la riga delle ricerche non dice più «non sono più qui»
  delle notizie, che restano in busta (intere il turno dopo, poi titoli e testate): «le notizie
  appena lette sono ancora qui sopra» o «delle notizie restano qui sopra titoli e testate». La
  spinta su «non ho altre informazioni» verso `notizie` chiede il tema o il numero del fatto, non
  «una domanda» (`RICERCA_COME`). La fonte dei turni archiviati con `web_cerca` delle notizie
  (`conversazioni.FONTI_TIPO`) nomina `notizie`, o `web_cerca` dove notizie non c'è.
- Alternative scartate come prima mossa: togliere in codice i risultati fuori tema (decide il
  modello cosa è pertinente; si può fare dopo le misure); embedding sulla DGX (latenza e un
  modello in più; da riconsiderare se l'ombra mostra troppi falsi «fuori tema» per sinonimi).

**Prove.** `prova_ricerca_fuori_tema` (a secco, ~1 s; su main non parte, manca `pertinenza.py`):
testi senza «tipo notizie», la riga con e senza il tool notizie, notizie nell'elenco e in
`ricerca_recente`, «restano qui sopra» con le notizie e i casi misti, la spinta verso notizie, la
misura (Orione e la startup 0 su 2, il mito 2 su 2, misti, una parola della frase basta, argomento
nuovo, niente con cui confrontare, una parola sola della storia non basta) e, come contrari dei
falsi «fuori tema» della revisione, «e domani?», «e adesso chi è primo?», PIL, NBA, Eco, F1,
gatti/gatto, Roma/romano, vinto/vince, Siner/Sinner, Orion/Orione; i tre modi (ombra di serie: solo
regole; spenta: niente; attiva: `pertinenti` fuori dalla busta), la riga di `stato --turni`, la
fonte delle notizie nell'archivio. `prova_web` aggiornata al nuovo testo.

**Banco col modello** (`prove/manuali/banco_ricerca_fuori_tema.py`, scenari `fuori`, `dentro` e
`notizie`, criterio della issue ≥ 9/10 ciascuno). Sul portatile con **gemma4 e4b** (non il 26B
dei casi veri), 5 giri, prima (main) e dopo con la misura attiva (`--pertinenza attiva`):

| Scenario | Prima | Dopo |
|---|---|---|
| `fuori` (risultati fuori tema) | 0/5 riferiti come risposta («Secondo Wikipedia, … un incrociatore della Regia Marina…») | 2/2 «non ho trovato… vuoi che cerchi su internet?», 3 senza ricerca («dimmi cosa ti interessa») |
| `dentro` (il contrario, risultati sul mito) | 4/4, 1 senza ricerca | 4/4, 1 senza ricerca |
| `notizie` (il nome solo nel sommario uscito) | 0/5 richiami, risposta con le testate rimaste, nessuna persona inventata | uguale (0/3 richiami, «a memoria» con le testate) |

Col 4B le notizie restano senza richiamo ma senza invenzioni: il 26B è quello del caso vero, da
misurare sulla DGX (comando nel file) prima di chiudere il criterio 3 della issue.

## La quota delle notizie in `calliope stato --turni` (16/10, issue #31)

Il documento chiedeva dal 13/10 di guardare sulla DGX «la quota delle risposte dai feed in
`calliope stato --turni`», ma il comando non stampava niente sulle notizie (incongruenza 1 del
gruppo casa-biblioteca dell'analisi del 15/10): senza aprire a mano il registro dei turni non si
sapeva se le notizie arrivano dai giornali scaricati o quasi sempre da internet (decisione 0024),
né quante volte un minore chiede una sezione non sua.

- **Tre regole nuove** in `calliope/tools/notizie.py`, solo nel registro dei turni (niente al
  modello, la risposta non cambia): `notizie_vuote` (risposta senza fatti: niente sul tema, una
  sezione senza giornali in casa, i feed mai scaricati); `notizie_ripiego_fallito` (serviva il
  ripiego e SearXNG non ha trovato niente, o è giù dall'ultima prova: allora `Web.pronta` è falso e
  il ripiego non si tenta nemmeno, ma conta come fallito, non come negato);
  `notizie_ripiego_negato` (serviva il ripiego ma chi parla è un minore o non ha `web_livello`).
  Con SearXNG **non configurato** (`Web.diagnosi` «non_configurato», o senza il servizio web)
  né fallito né negato: il ripiego non c'è mai stato. Fallito e negato non sono una parte delle
  vuote: una risposta dai feed con l'indice vecchio e SearXNG senza risultati ha `notizie_feed`
  **e** `notizie_ripiego_fallito`. Correzione dell'analisi della issue: il caso «SearXNG giù» non passa
  da `_ripiego` (si ferma prima, in `_ripiego_possibile`), quindi andava contato a parte.
- **`calliope/notizie/misura.py`** (solo libreria standard, come `pertinenza.riassunto`):
  `riassunto(turni)` per giorno e in totale (richieste = turni con una chiamata `notizie` o una
  delle regole), `testo(r)`; **quota dai feed** = feed / (feed + ripiego), nessuna quota senza
  nessuno dei due. Legge solo `regole` e i nomi in `tool`: nessun tema, nessun titolo.
- **La riga** in `calliope stato --turni` dopo la pertinenza delle ricerche, e la chiave
  `notizie` nel `--json`: «Notizie: 12 richieste, 6 dai giornali (86 %), 1 da internet, 2 vuote;
  ripiego fallito 1, negato 1; seguiti 1; minori: 1 sezione rifiutata; web_cerca girato a
  notizie 1.», poi una riga per giorno; senza notizie «Notizie: nessuna richiesta nel registro
  dei turni.».
- **Prove** (`prova_notizie`, § 7): le tre regole con i contrari (dai feed e il ripiego riuscito
  non le hanno; l'ospite e il minore sono «negato», non «fallito»; SearXNG giù due volte di fila
  resta «fallito»), il conto su un registro finto di due giorni (record senza `regole`, `regole`
  non lista, un elemento che non è un turno), la riga e il `--json` da `stato.main` su una
  cartella temporanea. Su main 10 controlli falliscono (le regole e la riga non c'erano).
- **Da fare sulla DGX** (criterio 4 della issue): dopo `calliope aggiorna`,
  `calliope stato --turni --giorni 7` e `--json`, e scrivere qui la prima lettura con la data e la
  quota. I turni prima dell'aggiornamento hanno solo `notizie_feed`, `notizie_ripiego`,
  `notizie_seguito`, `minore_notizie` e `web_notizie_al_tool`: le vuote e i ripieghi falliti si
  contano da lì in avanti. L'età della notizia più recente detta resta fuori (misura diversa, un
  campo nuovo nel record del turno).

**Prima lettura sulla DGX (17/10, versione 2864b3f).** `calliope stato --turni --giorni 7`: 17 richieste dal 14/10, 11 dai giornali (79 %), 3 da internet, 0 vuote; ripiego fallito 0, negato 0; seguiti 3; nessuna sezione rifiutata ai minori; nessun `web_cerca` girato a notizie. Per giorno: 14/10 67 %, 15/10 0 % (una sola richiesta, da internet), 16/10 100 %. I turni di prima del 17/10 non hanno le regole `notizie_vuote` e `notizie_ripiego_*`: vuote e ripieghi falliti si contano da qui in avanti.

## Tag HTML lunghi nei feed: il sommario era il testo del tag (17/10, issue #133)

Caso vero delle prove a voce del 16/10 sulla DGX: una testata di tecnologia mette in testa alla
`description` di ogni voce un `<img … srcset="…">` con una decina di indirizzi, lungo oltre 500
caratteri. Il lettore toglieva i tag con `<[^>]{0,500}>`: quel tag restava intero, la pulizia di
`web.servizio.ripulisci_testo` ne toglieva solo i segni e il taglio a 600 caratteri lasciava fuori
il paragrafo. Il sommario era «img width=… src="https://…" class=… srcset=…», il modello aveva
solo il titolo e ne ha inventato il senso; alle 23:05 dello stesso giorno 2 voci su 5 della
sezione erano così.

- **`lettore.testo_semplice` con `html.parser`** della libreria standard (nessuna dipendenza
  nuova): tiene solo i dati di testo con le entità risolte, salta `script` e `style`, ogni tag
  diventa uno spazio come prima («<b>Ro</b>ma» → «Ro ma»). Un «<» che non apre un tag resta
  testo («temperature <5 gradi e venti > 30 km/h» intero: la regola di prima ne mangiava un pezzo).
  Il secondo passaggio per l'HTML scritto come `&lt;p&gt;` si fa con le «&» già risolte protette,
  così le entità si risolvono una volta sola come prima («AT&amp;amp;T» → «AT&amp;T»).
  `close()` non si chiama: la coda non chiusa la decide `_TAG_TRONCO` (un tag con attributi o un
  commento troncati si buttano, «x<y» senza «>» resta), uguale in ogni versione di Python.
- **Dato non fidato**: ogni campo si legge per i primi `HTML_MAX` 10 000 caratteri (il sommario
  ne tiene 600; un `srcset` di trenta immagini ne fa ~3 000), così anche un caso peggiore del
  parser resta breve; se il parser solleva un'eccezione, ripiego su `<[^<>]*>`, lineare anche con
  molti «<» senza «>» (`<[^>]*>` non lo è). Misura sul portatile (Python 3.14): 2 MB di «<», di
  «<a » ripetuto, di un attributo aperto e di `&lt;a ` ripetuto in meno di 0,02 s col tetto; il
  parser senza tetto su 200 000 caratteri in meno di 0,15 s (il caso peggiore, tutti «<»).
- **Rete in `pulizia.sommario_per_voce`**: regola `notizie_sommario_html`, un sommario che dopo il
  lettore porta ancora `src=`, `srcset=`, `href=` o `class="…"` si scarta intero (la voce resta col
  titolo, il modello sa che non c'è altro), contata come le altre `notizie_sommario_*` (entra nel
  conto di #31). Contrari: «La classe di Ada vince…», «src e href» senza «=».
- **Le voci già salvate**: l'indice inserisce con `INSERT OR IGNORE`, quindi non si sarebbero
  riscritte per 7 giorni. All'apertura di `notizie.db` (`Notizie._togli_sommari_html`) le voci col
  sommario che passa la stessa rete si cancellano e ETag e Last-Modified dei loro feed si
  dimenticano: lo scarico successivo le riporta col paragrafo vero, se sono ancora nel feed.
  Scelta perché è idempotente (nessun segno di versione, nessun effetto con il disco pulito) e
  ridà il sommario, invece di lasciarlo vuoto fino alla scadenza; costa una scansione con `LIKE`.
- **Non toccato**: `web.servizio._TAG` (`{0,200}`) per i risultati di SearXNG, che arrivano già
  senza HTML dal motore (come dice la issue); per le notizie non conta più, il lettore toglie i
  tag prima.
- **Prove** (`prova_notizie`, § 2b): l'`<img>` di fantasia di 965 caratteri con un paragrafo in
  CDATA, scritto come `&lt;img…&gt;` e in un Atom `summary type="html"` → solo il paragrafo; i
  contrari («<5 gradi», `&lt;p&gt;`, `script` e `style` col contenuto, entità una volta sola,
  coda troncata); quattro input malevoli da 2 MB a tempo; la rete con i contrari e la regola
  contata da `_inserisci`; un `notizie.db` con una voce sporca, una pulita e un contrario
  riaperto due volte. Su main 7 controlli falliscono e la prova si ferma (`_senza_tag` non c'è).
- **Da fare sulla DGX** (criterio della issue): dopo `calliope aggiorna` e lo scarico successivo,
  `sqlite3 notizie.db "select count(*) from voci where sommario like '%src=%' or sommario like
  '%srcset%'"` deve dare 0; il log dice `[NOTIZIE] tolte N voci col sommario fatto di HTML` alla
  prima apertura.
