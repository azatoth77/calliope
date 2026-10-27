# Il telefono a sezioni e lo Studio: progetto delle schermate (27/10/2026)

*Progetto di design, nessuna modifica al codice. Fatto sul codice di `main` a `e8f5f55f`. Le
schermate sono disegnate e cliccabili nel canvas «Calliope telefono: studio di navigazione»
(artifact privato di chi amministra: <https://claude.ai/artifact/9jHRk1eXpB6jzNXwzkhUHC>); i nomi
tra parentesi quadre, come [Main], sono le tavole del canvas. Fonti: `calliope/schermi/pagina/telefono/`
(`index.html`, `telefono.js`), `calliope/schermi/pagina/schermo.js` (`NOMI_TIPO`, `DISEGNA.*`),
`calliope/schermi/schede.py`, [schermi-telefono](../aree/schermi-telefono.md),
[minori](../aree/minori.md) (esercizi, programma, interrogazioni, tutori), `calliope/tools/esercizi.py`,
`calliope/esercizi/registro.py`, le schermate in `docs/immagini/telefono-*.png`, la roadmap (modulo
studio S2–S5) e il prodotto Astra AI (<https://astra-ai.co>), letto il 27/10 come spunto per lo studio.*

## In breve

**Il problema.** Il telefono oggi è una vista sola (decisione del 04/10, «sempre come la vista da
guida»): lo stato della voce, un carosello di schede che si scorrono di lato, «Parla», microfono,
Scrivi e Allega, e un menu Impostazioni dove finiscono anche la conversazione, il cruscotto e
«Pulisci le mie schede». Tutto ciò che Calliope mostra entra nello stesso binario: una lista, un
timer, un lavoro, un avviso del tutore, un gioco. Non c'è un posto dove ritrovare le cose per tipo,
né una storia oltre i pallini del carosello. Con lo Studio, che porta sessioni lunghe e molte
schermate, la vista unica non regge.

**La proposta.**

1. **Cinque sezioni in una barra in basso**: Adesso, Conversazione, Le mie cose, Casa, Io. La voce
   (stato, microfono, Parla) resta sempre sopra la barra.
2. **Ogni tipo di scheda ha una casa fissa** (la lista in Le mie cose, l'avviso in Casa); in Adesso
   compare solo finché è viva.
3. **Dettagli a pila** con «Indietro» e il gesto indietro, e un indirizzo per ogni vista.
4. **La vista unica di oggi resta come modalità «In auto»**, che nasconde la barra.
5. **Lo Studio** è un flusso di undici schermate: dai materiali e dalla data della verifica a un
   piano a giorni, con esercizi guidati, carte, ripasso da ascoltare, verifica finta,
   interrogazione, mappa concettuale e la vista del tutore. Da Astra AI prende il percorso; le
   regole restano quelle di Calliope (indizi e non soluzioni, conti dal codice, giudizio senza voto,
   domande solo dai materiali, tutore informato).

**Perché.** Con la sola voce, o anche solo soprattutto con la voce, non si arriva a questo grado di
gestione: controllare dieci pagine fotografate, togliere un argomento, vedere un piano a giorni,
completare una mappa, ritrovare la lista di ieri. Il satellite sul telefono diventa uno strumento
di gestione, ma **resta dentro la conversazione con Calliope**: ogni tocco è un turno della
conversazione della persona, e Calliope sa che cosa è sullo schermo (capitolo 0).

**Cosa non cambia.** Il disegno delle schede (`DISEGNA.*` di `schermo.js`), le regole dello scritto
(solo durante una conversazione cominciata a voce), la visibilità per persona, il cruscotto solo a
chi amministra, l'abbinamento, il protocollo dei satelliti.

---

## 0. Perché uno schermo strutturato, e perché resta nella conversazione

**Perché.** Calliope è nata a voce, e la voce resta il modo principale. Ma l'uso vero ha mostrato
cose che a voce non si gestiscono bene, o non si gestiscono affatto:

- **elenchi lunghi e scelte multiple**: dieci pagine da controllare, sette argomenti da tenere o
  togliere, sei voci di una lista. A voce si va per tentativi («togli la terza… no, la quarta»);
- **ordine e posizione**: riordinare le pagine, mettere un concetto nella casella giusta di una mappa;
- **stato che dura giorni**: un piano verso una verifica, le sessioni fatte, la padronanza per
  argomento, un lavoro in corso; a voce si può chiedere, ma non vedere tutto insieme;
- **ritrovare**: «la lista di ieri», «il PDF della settimana scorsa»; a voce bisogna ricordarsi come
  chiederlo;
- **controllare ciò che Calliope ha capito**: una pagina scritta a mano, un argomento dubbio. Leggere è
  più veloce e più sicuro che farselo rileggere.

Il carosello di oggi aiuta a vedere la risposta, non a gestire. Lo Studio, che vive di materiali,
piani e sessioni, con la sola voce non si fa.

**Perché resta nella conversazione.** Lo schermo non è un'app a parte con un suo stato: è un altro
modo di parlare con Calliope, nella stessa conversazione della persona.

1. **Ogni gesto è un turno.** Spuntare il latte, togliere un argomento, consegnare la verifica finta,
   controllare la mappa: il telefono manda l'azione al server, che la esegue con lo stesso tool e la
   stessa politica della voce (`ToolRegistry.call`, canale «tocco» accanto a «voce» e «scritto») e la
   scrive nella conversazione della persona come un turno breve («Sofia ha tolto *La Carboneria*
   dagli argomenti»). Nel registro degli eventi (decisione
   [0027](../decisioni/0027-conversazione-come-registro-di-eventi.md)) è un evento con autore e canale.
2. **Calliope sa cosa c'è sullo schermo.** Nei dati del turno entra una riga breve con la vista aperta
   sul dispositivo da cui si parla («sul telefono: Piano verso la verifica, oggi»). Così «spostala a
   domani», «questa la so» o «cos'è quella in arancio?» si capiscono senza ripetere.
3. **La voce aggiorna lo schermo.** Ciò che si dice cambia le stesse viste («Calliope, togli la
   Carboneria» toglie la spunta); lo schermo non tiene niente che il server non sappia.
4. **Le risposte tornano dove si è chiesto.** Come oggi «rispondi dove ti ho chiesto»: una domanda
   fatta dalla mappa riceve risposta a voce e nella mappa.
5. **Si torna sempre alla conversazione.** Il resoconto di una sessione ha «Nella conversazione»;
   la Conversazione mostra le schede dentro le frasi; la sezione Conversazione è sempre a un tocco.
6. **Le regole sono quelle della conversazione.** Scritto e tocco valgono solo per il proprietario
   dello schermo personale, durante una conversazione cominciata a voce (`scrittura_consentita`); per
   le azioni importanti restano la conferma e la sfida.

---

## 1. Oggi

Dal codice (`telefono/index.html`, `telefono.js`):

| Parte | Cosa c'è | Dove |
|---|---|---|
| Abbinamento | nome, codice, comando per chi amministra | `#abbina-tel`, `apriAbbina`, `chiediCodice` |
| Testa | stato della voce («Dormo · di' «Calliope»»), ingranaggio | `#tel-voce`, `#menu-apri` |
| Carosello | la risposta più le schede, a scorrimento orizzontale, con i pallini | `#carosello`, `sincronizza`, `disponi`, `vaiA`, `disegnaPunti` |
| Scheda a tutto schermo | un tocco o «Espandi» | `#strato-scheda`, `apriIntera`, `chiudiIntera` |
| Fondo | Parla, Microfono, Scrivi, Allega | `#parla`, `#microfono`, `#scrivi-apri`, `#foto-apri` |
| Strati | Scrivi, modulo, menu | `apriStrato`, `chiudiStrato`, `apriModulo` |
| Menu | collegamento, schermo acceso, ascolto della stanza, cruscotto, «La nostra conversazione», «Pulisci le mie schede», prova del microfono, certificato, dimentica | `#menu` |

I tipi di scheda (`NOMI_TIPO` in `schermo.js`): lista, timer, promemoria (Agenda), biblioteca,
documento, casa, calcolo, testo (Da leggere), lavoro, modulo (Da scrivere), web (Internet),
esecuzione (Programma), risposta, foto, allegato (File), gioco, cruscotto, cassetto, esercizio,
esercizi_riepilogo, sviluppo, chat (Conversazione), conoscente (Voce nuova).

**Cosa non funziona** (dalle schermate e dall'uso):

- il carosello mescola cose vive (un timer che scade) e cose da ritrovare (una lista, un documento);
- dopo qualche turno la scheda che serve è «da qualche parte a destra», e i pallini non dicono cosa;
- funzioni importanti (la conversazione, il cruscotto, il cassetto) sono dentro le Impostazioni;
- non c'è un modo di arrivare a una cosa senza chiederla a voce;
- non c'è posto per un percorso a più passi come lo studio.

---

## 2. Principi

1. **La voce prima.** Ogni cosa si fa anche a voce; lo schermo serve a vedere, ritrovare e
   correggere. Microfono e Parla sono raggiungibili da ogni sezione con il pollice.
2. **Un posto per ogni cosa.** Ogni tipo di scheda ha una sezione di casa. Adesso è una vista
   dello stato, non un archivio.
3. **Profondità al massimo tre**: sezione → elenco → dettaglio. Le sessioni (esercizi, carte,
   interrogazione, verifica finta) sono a tutto schermo e si chiudono con la X.
4. **Cosa aspetta te si vede.** Un pallino sulla sezione per un modulo da compilare, un lavoro
   finito, un avviso.
5. **Le regole restano nel server.** La pagina non decide permessi: mostra ciò che il server manda
   e spegne ciò che il server dice spento (come oggi con lo scritto).
6. **Accessibile come disegnata.** Bottoni veri, `aria-*`, contrasto 4,5:1, bersagli da 44 px,
   colori che si distinguono anche per luminosità (blu e arancio, non verde e rosso); ogni mappa o
   grafico ha la sua vista a elenco.
7. **Personale non vuol dire «chi parla è il proprietario».** Il telefono (e il PC personale) è il
   satellite di una persona di casa, chiunque sia: un familiare, un minore, chi amministra. Questo
   lo rende adatto a **ricevere** i dati di quella persona che un satellite condiviso (la cucina, la
   TV) non deve ricevere: le sue liste, i suoi file, il suo studio, gli avvisi che la riguardano. Non
   rende certo **chi sta usando** il telefono: chi parla si riconosce dalla voce come altrove, e le
   azioni passano dalla stessa politica, con conferme e sfida. Nelle tavole il telefono è di Andrea, che
   amministra, e quello dello Studio è di Sofia: sono esempi, e ciò che cambia tra i due (il cruscotto,
   le voci nuove, la vista del tutore) dipende dal livello della persona, non dal telefono.

### 2.1 Palette (proposta: il lilla al posto dell'oro)

Nel canvas: [Palette], [MainLilla], [StudioHomeLilla]. Le schermate restano disegnate con l'oro di
oggi finché la palette non è decisa; il cambio è solo di variabili CSS (`--accento` e famiglia in
`schermo.css` e `telefono.css`).

| Ruolo | Oggi (oro) | Proposta (lilla) |
|---|---|---|
| Accento: pulsanti, etichette, barre | `#cfa760` | `#b9a3e3` |
| Accento chiaro: testo su fondo tinto | `#e2c48a` | `#cdbcf0` |
| Bordo di ciò che aspetta te | `#5a4a2c` | `#5b4a80` |
| Selezione nei selettori | `#2a2316` | `#2a2140` |
| Fondo tinto delle schede in evidenza | `#17140d` | `#15111f` |
| Testo sopra l'accento | `#1a1408` | `#1a1226` |
| Testo / tenue | `#ece6db` / `#a19b91` | `#ece8f2` / `#a8a2b5` |
| Voce «ci penso» | oro | lilla (gli altri stati restano: dormo grigio, ti ascolto verde, parlo blu) |
| Padronanza | la sai blu, quasi oro, da studiare arancio | la sai verde acqua `#6cc3a6`, quasi lilla chiaro `#c4b2ec`, da studiare corallo `#d9876c` (sempre con la parola) |

Contrasto: lilla sul nero circa 9:1, testo scuro sul lilla circa 8:1.

**Decisione del 27/10**: il lilla diventa l'accento **di serie su tutto** (telefono, PC, schermi
condivisi). In più l'accento è un'**opzione personale** in Io › Aspetto (lilla di serie, oro come
oggi, e uno o due altri accenti già controllati per il contrasto): vale sui satelliti personali di
quella persona, mentre gli schermi condivisi restano sul colore di serie. È una preferenza della
persona, salvata come le altre (`esercizi_preferenze` è il modello), e cambia solo le variabili
`--accento*`.

---

## 3. La struttura

### 3.1 Le cinque sezioni

| Sezione | Cosa contiene | Pallino |
|---|---|---|
| **Adesso** [Main] | timer in corso, lavori in corso, ciò che aspetta te (moduli, domande dell'agente), l'ultima risposta | — |
| **Conversazione** [Conversazione] | le frasi della persona con le schede dentro, la casella per scrivere, Allega, i filtri Oggi / Ieri / Solo schede | messaggio non letto |
| **Le mie cose** [Raccolte] | Liste, Agenda, Lavori e programmi, Cassetto, Documenti, Giochi, Studio, Ufficio; «Aperte di recente» | lavoro finito, file nuovo |
| **Casa** [Casa] | avvisi per te, dispositivi per stanza, ascolto della stanza, famiglia e voci nuove | avviso |
| **Io** [Io] | collegamento, schermo acceso, ascolto della stanza, modalità In auto, aiuto e prova del microfono, cruscotto e certificato (solo se il proprietario amministra), dimentica | — |

**Sul satellite personale di un minore** (decisione del 27/10) le sezioni dipendono dall'età
(dal profilo, come le fasce di [minori](../aree/minori.md)):

| Sezione | Meno di 13 anni | Da 13 anni |
|---|---|---|
| Adesso, Conversazione, Io | sì | sì |
| Le mie cose | sì, **senza Ufficio** | sì, **senza Ufficio** |
| Casa | nascosta | sì (con i permessi del minore: comandi e letture che il minore può già fare a voce) |

Ufficio è nascosto ai minori a ogni età. Nascondere una sezione non toglie permessi né li aggiunge:
i permessi restano in `ToolRegistry.call`; la sezione nascosta evita solo di mostrare ciò che non
serve.

### 3.2 Dove va ogni tipo di scheda

| Tipo (`NOMI_TIPO`) | Casa | Compare in Adesso quando |
|---|---|---|
| risposta, calcolo, biblioteca, web, testo | Conversazione | è l'ultima risposta |
| timer, promemoria | Le mie cose › Agenda | il timer corre; il promemoria scade entro un'ora |
| lista | Le mie cose › Liste | appena cambiata (per un turno) |
| lavoro, esecuzione, sviluppo | Le mie cose › Lavori e programmi | in corso o in attesa di risposta |
| documento | Le mie cose › Documenti | appena pronto |
| foto, allegato, cassetto | Le mie cose › Cassetto | — |
| modulo | Le mie cose (dove nasce) | sempre finché è da compilare («Aspetta te») |
| gioco | Le mie cose › Giochi | partita aperta e tocca a te |
| esercizio, esercizi_riepilogo | Le mie cose › Studio | sessione aperta |
| casa | Casa | appena cambiata |
| conoscente, avviso del tutore | Casa | finché non è visto |
| cruscotto | Io › Stato di Calliope | — |
| chat | Conversazione | — |

La regola si scrive una volta sola: una tabella `SEZIONE_DI_TIPO` accanto a `NOMI_TIPO` in
`schermo.js`, e una funzione «viva» per tipo (il timer corre, il lavoro non è finito, il modulo non
è compilato).

### 3.3 La voce sempre sotto il pollice

- In **Adesso**: riga di stato grande (pallino colorato come oggi: dorme, ascolta, pensa, parla,
  spento), Microfono, **Parla** largo, Scrivi.
- Nelle altre sezioni: una riga compatta (stato, Microfono, Parla) sopra la barra.
- Nelle **sessioni dello Studio**: niente barra; il microfono resta, perché si risponde a voce.
- Lo stato e il microfono sono gli stessi di oggi (`statoVista`, `impostaMic`, `tocca`); cambia solo
  dove stanno.

### 3.4 Pila e indirizzi

Ogni vista ha un indirizzo nel frammento: `#/adesso`, `#/conversazione`, `#/cose/liste/spesa`,
`#/cose/lavori/<id>`, `#/casa`, `#/io`, `#/studio/verifica/<id>`. Il gesto indietro del telefono
(`popstate`) torna alla vista di prima, come oggi chiude la scheda a tutto schermo. Una scheda che
arriva dal server porta la sua `chiave` (`chiaveDi`): il server può chiedere di aprirla
(`vaiA(chiave)` diventa `apri("#/cose/…")`).

### 3.5 Modalità In auto [Auto]

La vista unica di oggi, semplificata: stato grande, l'ultima risposta in caratteri grandi, Parla
alto un quinto dello schermo, microfono. Niente barra, niente carosello. **Si accende a mano**
(decisione del 27/10): un tocco su «In auto» (in Io, e come pulsante rapido in Adesso) e la pagina
cambia modo; «Esci» torna ad Adesso. Niente riconoscimento automatico dell'auto.

### 3.6 Sul satellite personale su PC [PcAdesso, PcCose, PcStudio, PcMateriali, PcMappa, PcEsercizio]

Stesse sezioni, stesse schede, stesse regole del telefono; cambia la disposizione, perché sul PC c'è
spazio e ci sono mouse e tastiera. La stessa disposizione, con la barra delle sezioni a sinistra,
vale per tablet e TV (decisione del 27/10). È la pagina degli schermi personali (`schermi/pagina/`) aperta
sul PC che fa da satellite, con la stessa logica di sezioni del telefono (un solo codice, due
disposizioni scelte dalla larghezza).

- **Tre colonne.** A sinistra le sezioni (con le sottosezioni di Le mie cose e, nello Studio, la
  verifica aperta, i materiali e la mappa) e in fondo la voce (stato, microfono, Parla). Al centro il
  contenuto. A destra **la conversazione, sempre aperta**, con la casella per scrivere: qui si vede
  meglio che ogni gesto è un turno («Hai trascinato *Appunti del prof.pdf*», «Hai collegato *Cavour* a
  *Regno d'Italia 1861*») e Calliope risponde accanto a ciò che si sta guardando. Sotto i 1100 px la
  conversazione si chiude in un pulsante; sotto i 760 px vale la disposizione del telefono.
- **Voce.** Parla, microfono e stato come sul telefono; in più un tasto da tenere premuto per parlare
  senza dire il nome (proposta: Ctrl+Spazio, gestito dal satellite su Windows perché valga anche con
  la pagina in secondo piano).
- **Cosa il PC fa meglio:**
  - *Adesso*: i moduli si compilano lì, senza aprire uno strato;
  - *Le mie cose*: tessere e una tabella «Aperte di recente» con tipo, origine e data; la ricerca;
  - *Studio*: piano e argomenti affiancati; il giorno fatto apre il resoconto;
  - *Materiali*: si **trascinano** PDF, foto, Word o una cartella; per le pagine di un libro Calliope
    apre la fotocamera **sul telefono** della stessa persona e le pagine arrivano sul PC; la pagina e
    il testo letto stanno **affiancati**, e il testo si corregge lì («Correggi il testo»);
  - *Mappa*: grande, con «+ Concetto» e «Collega», i concetti si spostano col mouse; a destra il
    concetto scelto con i suoi collegamenti e la pagina da cui viene;
  - *Esercizio guidato*: la pagina del libro accanto alla domanda; l'indizio evidenzia il paragrafo;
    tasti A–D, H per l'indizio, Invio per andare avanti, Esc per uscire; la barra delle sezioni si
    nasconde (sessione).
- **Il telefono e il PC insieme.** Sono due satelliti della stessa persona: ciò che si apre su uno si
  ritrova sull'altro (la cronologia delle schede è per persona), e un'azione può passare dall'uno
  all'altro («apri la fotocamera sul telefono»).

---

## 4. Le schermate, una per una

Per ogni schermata: a cosa serve, cosa mostra, cosa si fa, a voce, regole, codice di oggi da cui
parte, cosa manca.

### 4.1 Adesso [Main]

- **Serve a** vedere cosa sta succedendo e cosa aspetta te, senza cercare.
- **Mostra**: «In corso» (timer con +1 minuto e Ferma; lavoro con passo e barra), «Aspetta te»
  (modulo con Compila), «Ultima risposta» (con la fonte, porta alla Conversazione).
- **A voce**: tutto come oggi; «cosa c'è in corso?» legge questa vista.
- **Codice di oggi**: le schede del carosello (`sincronizza`), `disegnaRisposta`, la scheda del
  modulo, la scheda del lavoro.
- **Manca**: la regola «viva» per tipo (3.2); l'ordine (prima ciò che aspetta te, poi ciò che è in
  corso, poi l'ultima risposta).

### 4.2 Conversazione [Conversazione]

- **Serve a** rileggere e a scrivere.
- **Mostra**: le frasi con ora e canale («a voce, cucina», «scritto», «foto dal telefono»); le
  risposte con la scheda piccola dentro (Biblioteca, Lista…) che apre il dettaglio; filtri Oggi /
  Ieri / Solo schede; cerca.
- **Si fa**: scrivere, allegare, inviare.
- **Regole**: la casella resta spenta fuori da una conversazione cominciata a voce
  (`scrittura_consentita`), con il testo di oggi «Di' «Calliope» per scrivermi».
- **Codice di oggi**: `DISEGNA.chat`, `chatDalServer`, `ArchivioConversazioni.chat`, `/api/scrivi`,
  `/api/immagine`.
- **Manca**: le schede piccole dentro i messaggi (oggi la chat è testo); il filtro per giorno.

### 4.3 Le mie cose [Raccolte]

- **Serve a** ritrovare per tipo.
- **Mostra**: otto tessere con il conto e lo stato in una riga («1 in corso · 1 finito da vedere»),
  il pallino dove c'è una novità; «Aperte di recente».
- **Codice di oggi**: la cronologia delle schede per persona (`CronologiaSchede`, `Schermi.ripresa`)
  è già la fonte: va raggruppata per sezione.
- **Manca**: un `GET /api/raccolte` che dia conti e novità per tessera.

### 4.4 Dettaglio: lista [Lista]

- **Mostra**: titolo, di chi è («Di casa · la vedono tutti»), voci con chi le ha aggiunte, spunta,
  «Aggiungi», «Togli le prese», «Mostra sulla TV».
- **Codice**: `schede.lista`, `liste.py`. La spunta a tocco è nuova: oggi la lista si cambia a voce.
- **Regole**: toccare equivale a dire «ho preso il latte»; passa da `ToolRegistry.call` come la voce.

### 4.5 Dettaglio: lavoro in corso [Lavoro]

- **Mostra**: titolo, tempo, materiali, i passi (fatti, in corso, da fare), il testo dell'agente in
  diretta in sola lettura, «A che punto sei?», «Ferma il lavoro».
- **Codice**: `DISEGNA.esecuzione`, `chatFlusso`, `Avanzamento`, la vista dello sviluppo. Esiste
  quasi tutto; cambia il contenitore.

### 4.6 Agenda [Agenda]

- **Mostra**: timer in corso; Oggi / Domani / Settimana con promemoria e appuntamenti, per chi sono,
  da dove vengono («detto da Giulia»).
- **Codice**: `agenda.py`, `schede.timer`. **Manca**: una vista per giorno lato server.

### 4.7 Cassetto [Cassetto]

- **Mostra**: i file della persona con tipo, origine (telefono, schermo del PC, webcam) e giorni che
  restano; filtri per tipo; «Aggiungi un file», «Scatta una foto»; la nota che ciò che c'è scritto
  nei file è un dato.
- **Codice**: `cassetto.py` (7 giorni, origini `FONTI`), `DISEGNA.cassetto`.

### 4.8 Documenti [Documenti]

- **Mostra**: «Fatti da Calliope per te» (con Leggi e Scarica, quello in preparazione porta al
  lavoro) e «Archivio di casa» per tipo (bollette, salute, garanzie, scuola, contratti); cerca.
- **Codice**: `documenti/`, `scarica.py`, `archivio/` (schede per tipo, grafo).

### 4.9 Ufficio [Ufficio]

- **Mostra**: Fatture / Preventivi / DDT / Rubrica; per ognuno lo stato («Da inviare allo SdI»,
  «Bozza», «Inviata») e le azioni (Scarica XML, Scarica PDF, Rileggi a voce).
- **Regole**: numerazione e totali dal programma; i dati mancanti con un modulo; l'invio allo SdI a
  mano.
- **Codice**: `ufficio/`, `tools/ufficio.py`, `fatturapa/`.

### 4.10 Giochi [Giochi]

- **Mostra**: la partita aperta (punti, turno, a chi tocca, Riprendi, Sulla TV), i giochi di casa,
  quello in sviluppo con il collaudo, «Inventa un gioco nuovo».
- **Codice**: `schermi/giochi.py`, `gioco_stato.py`, la macchina a stati dei giochi.

### 4.11 Casa [Casa]

- **Mostra**: l'avviso per te in cima (quando e dove, «Leggi cosa si è detto», «Visto»); stanze a
  schede; dispositivi (luce con interruttore, termostato, serratura «solo lettura»); ascolto della
  stanza con «Abbiamo ospiti»; la famiglia e «1 voce nuova».
- **Regole**: serrature, allarmi e cancelli restano in sola lettura; l'avviso solo al tutore, sul
  suo schermo personale (come oggi); le voci nuove solo a chi amministra.
- **Codice**: `casa/`, la scheda «avviso» del tutore, `stanza_pausa`, `stanza/conoscenti.py`.

### 4.12 Io [Io]

- Le voci del menu di oggi, in gruppi: Questo telefono, Aiuto, Amministra; «Dimentica questo
  telefono» in fondo, in arancio.

---

## 5. Lo Studio

### 5.1 Da dove viene

Astra AI (<https://astra-ai.co>) è un tutor per lo studio in cloud: lo studente mette la data
dell'esame e carica appunti, slide, compiti vecchi e foto; Astra fa un piano per argomenti, lezioni,
quiz, flashcard, un podcast, verifiche simulate a tempo, interrogazioni orali, misura la padronanza e
tiene i giorni di fila. Non dice quali modelli usa; le cifre che pubblica sono sue.

**Da Astra AI prendiamo** il percorso: la verifica con una data, i materiali che diventano
argomenti, il piano a giorni, le forme di studio diverse sullo stesso contenuto, la padronanza per
argomento, la verifica simulata, i giorni di fila.

**Da Calliope teniamo** le regole che ci sono già (vedi [minori](../aree/minori.md)): indizi e non
soluzioni; conti e correzioni dal codice; giudizio a parole senza voto; il programma ministeriale
della classe e del periodo; «a che punto siete»; la pagina del libro chiesta se manca; il tutore che
vede; orari e tempo; l'audio che non si salva; i materiali caricati come dati non fidati.

**Cosa c'è già nel codice**: il tool `esercizi` con le azioni `inizia`, `interroga`, `rispondi`,
`aiuto`, `salta`, `ripeti`, `segnala`, `soluzione`, `pausa`, `riepilogo`, `a_che_punto`,
`argomenti`; il registro `esercizi_tentativi` (persona, materia, argomento, esercizio, esito,
suggerimenti, secondi, canale), `esercizi_punto` («a che punto siete»), `esercizi_banco`,
`esercizi_segnalazioni`; le materie calcolabili (matematica, italiano, logica, fisica, chimica);
l'indice del programma in `esercizi/programma/`; le schede `esercizio` ed `esercizi_riepilogo`.

**Cosa è nuovo**: la verifica con data e materiali, gli argomenti tratti dai materiali, il piano a
giorni, le carte con il ripasso dilazionato, il ripasso da ascoltare, la verifica finta a tempo, la
mappa concettuale, la padronanza calcolata, la vista del tutore per verifica.

### 5.2 Il percorso

```text
Ho una verifica  →  materiali  →  argomenti (confermati)  →  piano a giorni
      │                                                       │
      │        ┌──────────────── ogni giorno ────────────────┘
      ▼        ▼
  1. Il quadro      lo scheletro della mappa (genera Calliope)           primo giorno
  2. Studio         leggere + allungare la mappa con il libro,           giorni di mezzo
                    esercizi guidati, ripasso da ascoltare, carte
  3. Ripasso        mappa a memoria, carte, verifica finta,              vigilia
                    interrogazione sui punti deboli
  4. La verifica    la mappa di Sofia (PDP), il riepilogo al tutore      il giorno
```

Ogni attività scrive tentativi; dai tentativi si calcola la padronanza per argomento (5.5); la
padronanza decide cosa proporre il giorno dopo e quanto aiuto dare.

### 5.3 Le schermate dello Studio

Esempio in tutte le tavole: Sofia, 2ª media, verifica di storia sul Risorgimento giovedì; Andrea è
il tutore.

#### Studio 1 · La mia scuola [StudioHome]

- **Mostra**: la prossima verifica (materia, argomento, giorni che mancano, «sai il 55%», cosa fare
  oggi in quanti minuti, «Inizia il ripasso», «Il piano»); otto modi di studiare (Esercizi, Carte,
  Mappa, Ascolta, Verifica finta, Interrogami, Foto di un problema, Chiedimi); le materie con
  l'argomento in corso e la padronanza; «Ho una verifica»; i giorni di fila.
- **A voce**: «Calliope, cosa devo studiare oggi?» legge la riga «Oggi».
- **Regole**: i giorni di fila si contano solo dentro gli orari di studio dei tutori; niente premi
  che spingano a usarlo fuori orario.
- **Dati**: verifiche aperte, piano di oggi, padronanza per materia.

#### Studio 2 · Ho una verifica [StudioNuova]

- **Mostra**: materia (dalle materie della classe), argomento, quando; materiali con origine e stato
  («6 foto · lette»), Fotografa / Dal cassetto / Un file; la biblioteca di casa (Vikidia) come
  materiale aggiunto da Calliope; la nota «le domande solo da questi materiali, il tutore vede il
  piano»; «Prepara il piano».
- **A voce**: «Calliope, giovedì ho la verifica di storia sul Risorgimento» apre questa schermata già
  compilata.
- **Cosa succede dopo «Prepara il piano»** (in secondo piano, è un lavoro):
  1. i materiali si leggono come oggi gli allegati (`allegati.py`, OCR col modello visivo per le
     foto), sempre in busta (`provenienza.py`);
  2. il modello propone gli argomenti come JSON con schema, ognuno con le pagine da cui viene;
  3. il codice controlla che ogni argomento citi pagine che esistono e lo confronta con l'indice del
     programma della classe;
  4. Sofia conferma gli argomenti (e il tutore li vede);
  5. il codice fa il piano a giorni (5.6).
- **Regole**: un materiale con istruzioni dentro resta un dato; niente argomenti fuori dai materiali e
  dal programma.

#### Studio 3 · Piano verso la verifica [StudioVerifica]

- **Tre viste**: **Il piano** (i giorni con la fase, l'attività e i minuti; il giorno fatto con la
  spunta; «Inizia» su oggi); **Argomenti** (ogni argomento con la padronanza a parole e colore,
  «la sai / quasi / da studiare», e le pagine); **La mappa** (porta alla mappa, «Completa la
  mappa», la nota sul PDF per il PDP).
- **Si fa**: «Sposta il piano (non ce la faccio oggi)» ridistribuisce i giorni che restano.
- **A voce**: «a che punto sono con la storia?», «spostiamo a domani».
- **Regole**: la padronanza è calcolata dalle risposte, non dal modello; lo si dice sulla schermata.

#### Studio 4 · Esercizio guidato [StudioEsercizi]

- **Mostra**: avanzamento («esercizio 3 di 8», giuste), la pagina di origine, la domanda, le
  risposte (scelta multipla o aperta), «Aiutami» (un indizio, non la risposta), «Avanti»; la
  correzione con la spiegazione e, se sbagliata, il rimando al paragrafo.
- **Foto di un problema**: la stessa schermata, partendo da una foto; la soluzione resta a passi
  guidati.
- **Codice di oggi**: è il tool `esercizi` (`inizia`, `rispondi`, `aiuto`, `salta`) e la scheda
  `esercizio`. **Nuovo**: domande generate dai materiali della verifica per le materie non
  calcolabili, con la riga di origine e il secondo parere del modello dell'agente (S2 della
  roadmap) prima di essere proposte. **Decisione del 27/10**: all'inizio il secondo parere basta,
  senza la revisione di un adulto; in un secondo passo il tutore può chiedere di **controllare lui**
  le domande di una verifica o di una materia prima che arrivino allo studente (un interruttore nella
  vista del tutore, spento di serie).

#### Studio 5 · Ripasso con le carte [StudioFlashcard]

- **Mostra**: la carta (domanda; toccata, la risposta con la pagina); poi «Non la sapevo · fra 10
  minuti», «Quasi · domani», «La sapevo · fra 4 giorni».
- **A voce**: si dice la risposta, Calliope la confronta con la carta.
- **Come funziona**: carte generate dai materiali (domanda, risposta, pagina); ripasso dilazionato
  con un algoritmo semplice e noto (SM-2 o FSRS), tutto nel codice; le carte sbagliate negli
  esercizi e nella mappa diventano carte.

#### Studio 6 · Ripasso da ascoltare [StudioAscolta]

- **Mostra**: titolo, durata, capitoli con l'ora, avanzamento, play/pausa, −15 s, velocità; «Interrompimi
  quando vuoi».
- **Come funziona**: un testo scritto in secondo piano dai materiali (con le pagine), letto da Piper
  in due voci italiane (decisione del 27/10: si parte con Piper), salvato nel cassetto della persona
  come audio. Poiché il ripasso si prepara in secondo piano e non serve in tempo reale, in futuro può
  usare un motore più espressivo di quello della voce dal vivo: vedi «Voci più espressive» in fondo
  a questa sezione. L'interruzione è il barge-in di oggi:
  la domanda va al tutor e poi si riprende.
- **Regole**: il testo passa dal controllo di ciò che si dice con dati non fidati (`riferire`).

#### Studio 7 · Verifica finta [StudioSimulazione]

- **Mostra**: tempo che resta, la mappa delle domande (risposta, da rivedere, vuota), la domanda, la
  casella, «Da rivedere», «Consegna»; «come in classe: niente indizi fino alla consegna».
- **Dopo la consegna**: giudizio a parole per domanda e cosa ripassare; gli errori diventano carte e
  abbassano la padronanza dei loro argomenti.
- **Regole**: niente voto numerico.

#### Studio 8 · Interrogazione [StudioInterroga]

- **Mostra**: le domande e le risposte come una conversazione; «Cosa cerco nella risposta» con i
  criteri spuntati man mano; «Rispondi», «Basta così»; «alla fine un giudizio a parole; la voce non
  la tengo».
- **Codice di oggi**: è `esercizi azione=interroga` con i criteri di `programma/interrogazioni.yaml`.
  **Nuovo**: criteri tratti dai materiali della verifica, mostrati mentre si risponde; l'ascolto
  lungo senza nome (#50) serve qui.

#### Studio 9 · Vista del tutore [StudioTutore]

- **Mostra** (sul telefono del tutore, in Le mie cose › Studio): sessioni, tempo dentro gli orari,
  esercizi giusti; la verifica (piano seguito, padronanza e com'era, argomenti deboli); «Da guardare
  tu» (interrogazione col giudizio incerto, esercizi a campione, argomenti tratti dai materiali);
  Regole (orari, «Soluzioni intere: mai»); «Vedi come la vede Sofia».
- **Codice di oggi**: `esercizi azione=riepilogo`, gli esercizi a campione (`esercizi_campione`),
  le segnalazioni.

#### Studio 10 · Mappa concettuale [StudioMappa]

Vedi 5.4. **Mostra**: in alto «La mia mappa» o «Lo scheletro», con chi l'ha fatta («fatta da
Sofia · controllata oggi» o «di Calliope · dai materiali»); la mappa con i nodi colorati per
padronanza, la legenda e le frecce con il verbo; un nodo toccato apre la spiegazione breve, la
pagina, Carte ed Esercizi su quel concetto; Mappa / Elenco. In fondo, sulla mia: «Scarica PDF» e
«Allungala»; sullo scheletro solo «Parti da qui: fai la tua» (lo scheletro non si scarica).

#### Studio 11 · Costruisci la mappa [StudioMappaCostruisci]

Vedi 5.4. **Mostra**: «Con il libro» (fase di studio: il titolo è «Costruisci la tua mappa», ogni
casella vuota dice la pagina dove cercare, si possono aggiungere concetti propri) o «A memoria»
(fase di ripasso: «Rifai la mappa a memoria», nessuna pagina, gli errori diventano carte); aiuto
Tanto / Medio / Poco, scelto dalla padronanza e cambiabile (2, 3 o 6 caselle vuote, sugli argomenti
più deboli); le parole da mettere, una di troppo; «Controlla» colora giuste e sbagliate e dà un
indizio sulle frecce; «Rifai».

#### Materiali 1 · Fotografa le pagine [StudioFoto]

- **Serve a** portare dentro le pagine di un libro o di una scheda, anche molte, senza fatica.
- **Mostra**: la fotocamera con la cornice della pagina riconosciuta; i segnali «luce ok», «pagina
  intera», «tieni fermo…»; lo scatto automatico quando la pagina è ferma; «Libro aperto» per due
  pagine insieme, che Calliope divide; la fila delle pagine scattate, con il numero letto dal libro e
  il «!» su quelle da rifare; «Dalla galleria»; «Fatto (n)».
- **Come funziona** (decisione del 27/10): la pagina si riconosce **in JavaScript sul telefono**
  (bordi, prospettiva, raddrizzamento, nitidezza) prima di mandarla, così lo scatto automatico e
  l'avviso «sfocata» sono immediati e non viaggiano foto storte; il server **ripete il controllo**
  sull'immagine ricevuta (ritaglio, rotazione, nitidezza, numero di pagina) e vale il suo esito. Le
  foto dalla galleria e i file trascinati sul PC passano solo dal controllo del server. Le foto
  vanno nel cassetto della persona come oggi (`/api/immagine`, `cassetto.py`).
- **A voce**: «Calliope, fotografo le pagine del libro di storia per la verifica» apre la fotocamera
  già legata alla verifica.

#### Materiali 2 · Controlla e ordina [StudioPagine]

- **Mostra**: le pagine per materiale (le foto del libro, il PDF degli appunti dal cassetto diviso in
  pagine), già in ordine con i numeri letti; l'avviso su ciò che non torna («la 113 è sfocata», «dopo
  la 117 manca la 118: era voluto?»); toccata una pagina, il suo stato e Sposta, Ruota, Ritaglia,
  Togli; «+ Altre pagine», «Leggi le n pagine».
- **Regole**: i PDF con testo si leggono senza OCR; i doppioni (stessa pagina due volte) si segnalano;
  una pagina tolta non si legge.

#### Materiali 3 · Lettura [StudioLettura]

- **Mostra**: l'avanzamento («6 di 10 · circa 1 minuto»), ogni pagina con lo stato (letta, in
  lettura, in coda, scritta a mano, poco nitida), e toccata una pagina, cosa Calliope ha letto;
  «Puoi chiudere: è un lavoro, lo trovi in Adesso»; la nota che le istruzioni trovate nelle pagine non
  si eseguono; «Vedi gli argomenti (bozza)».
- **Come funziona**: un lavoro in secondo piano (come gli altri lavori: in Adesso finché gira, avviso a
  fine lavoro), che legge con l'OCR del modello visivo (`immagini.py`, archivio) e mette il testo di
  ogni pagina in busta. Le righe illeggibili restano segnate, non inventate.

#### Materiali 4 · Conferma gli argomenti [StudioArgomenti]

- **Mostra**: «Cosa c'è da sapere»: gli argomenti trovati, ognuno con le pagine da cui viene e gli
  avvisi («poco spazio nel libro: forse non serve», «non è nelle pagine del libro che mi hai dato»,
  «da controllare» per lo scritto a mano), con la spunta; «Controlla» per la pagina scritta a mano;
  «+ Aggiungi un argomento»; «Gli argomenti li vede anche papà»; «Conferma n e fai il piano».
- **Regole**: il piano si fa solo sugli argomenti con la spunta; ogni scelta è un turno della
  conversazione di Sofia e il tutore la vede.

#### Resoconto di una sessione [StudioSessione]

- **Si apre** toccando un giorno fatto nel piano (Studio 3), o dallo storico del riepilogo.
- **Mostra**: giorno, ora, durata, dispositivo e stanza; «Cosa hai fatto», in ordine di tempo, con il
  risultato di ogni attività (lo scheletro guardato, le pagine lette con le domande fatte, gli
  esercizi giusti e con indizio, i concetti aggiunti alla mappa, le carte nate dagli errori), ognuna
  apribile; «Quanto sai, prima e dopo» per gli argomenti toccati; ciò che Calliope ha detto alla fine;
  «Rivedi gli errori», «Nella conversazione» (porta al punto della conversazione di quel giorno).
- **Dati**: è una proiezione dei tentativi e degli eventi della sessione, non un testo scritto dal
  modello; la frase finale è quella detta davvero.

#### Riepilogo della verifica [StudioRiepilogo]

- **Si apre** il giorno dopo la verifica (Calliope chiede «com'è andata?»), o da Studio.
- **Mostra**: «Com'è andata?» (Bene, Così così, Male; il voto, se lo studente vuole, lo scrive lui:
  Calliope non ne dà); i totali (sessioni e tempo, esercizi giusti, carte, concetti in mappa);
  «Da lunedì alla vigilia» con la padronanza per argomento, prima e dopo; «Le sessioni», lo storico,
  ognuna apribile nel resoconto; cosa ha funzionato e cosa continua («le carte del Risorgimento per
  due settimane, poche al giorno»); «Scarica il riepilogo», «Archivia la verifica».
- **Regole**: il riepilogo va anche al tutore; dopo l'archiviazione restano la mappa di Sofia e le
  carte, il resto segue la conservazione dei minori.

### 5.4 La mappa concettuale in quattro fasi

**Perché.** Per i ragazzi con DSA la mappa è uno strumento compensativo (legge 170/2010, PDP) che
spesso si può usare in verifica: una mappa fatta dai propri materiali, controllata e stampabile, è
un aiuto concreto. In più costruire la mappa aiuta a capire la struttura dell'argomento. La
letteratura indica che studiare o costruire mappe aiuta più del solo leggere (Nesbit e Adesope,
2006), e che richiamare a memoria aiuta più che fare la mappa con il testo aperto (Karpicke e Blunt,
2011): per questo il ripasso è «a memoria». *Da ricontrollare sulle fonti prima di citarle nel
prodotto.*

| Fase | Chi la fa | Come | Quando nel piano |
|---|---|---|---|
| 1. Il quadro | **Calliope** | scheletro di 6–10 concetti e relazioni dai materiali, ogni nodo con la pagina; serve a vedere la struttura prima dei dettagli | primo giorno |
| 2. Studio | **lo studente** | allunga lo scheletro con il libro aperto, con parole sue; Calliope controlla la coerenza con i materiali e segnala collegamenti mancanti o sbagliati, senza dare la soluzione | giorni di mezzo |
| 3. Ripasso | **lo studente** | rifà la mappa a memoria; le caselle vuote sono sugli argomenti deboli e aumentano con la padronanza (gli aiuti si ritirano) | vigilia, e ogni volta che serve |
| 4. Verifica | — | si scarica **la mappa dello studente**, controllata e vista dal tutore; mai lo scheletro | il giorno |

**Quando la genera Calliope anche dopo**: se lo studente è bloccato o piccolo (più nodi dati, poi
tolti); se la chiede («fammi la mappa del capitolo»), proponendo subito di completarla insieme. Mai
come unica attività della sera prima.

**Come si genera.** Il modello estrae da materiali e argomenti delle triple *(concetto, relazione,
concetto)* in JSON con schema, ognuna con la pagina; il codice tiene solo quelle con pagine vere,
toglie i doppioni, limita a 10–15 nodi per mappa (le più grandi si dividono per capitolo) e calcola
la disposizione (centro e rami, livelli). La mappa dello studente è la stessa struttura con
l'autore per nodo e per freccia.

**Come si controlla** (fase 2 e 3): per ogni freccia dello studente il codice cerca una tripla dei
materiali compatibile (stessi concetti, relazione simile); se non c'è, il modello giudica sulla
pagina citata e lo dice come domanda («a pagina 117 chi concede lo Statuto?»). Le caselle vuote
del ripasso si scelgono dagli argomenti con la padronanza più bassa.

**PDF**: la mappa dello studente in pagina A4 orizzontale, con il nome, la data e «controllata il …»;
più lo schema a elenco nella seconda pagina. *Decisione del 27/10*: il formato richiesto dalla scuola
(A3, colori, simboli) lo decidono i tutori, ma **resta fuori da questa implementazione**: per ora un
solo formato.

### 5.5 Padronanza

Una cifra da 0 a 100 per (persona, argomento), calcolata nel codice dai tentativi, mai dal modello:

- ogni tentativo pesa per esito (giusto, giusto con indizio, sbagliato), per tipo (esercizio, carta,
  casella della mappa, domanda della verifica finta, criterio dell'interrogazione) e per età
  (i tentativi vecchi contano meno);
- senza ripasso la cifra cala col tempo;
- a parole: «la sai» (≥ 75), «quasi» (45–74), «da studiare» (< 45); i colori blu, oro, arancio.

La formula precisa va tarata sui tentativi veri, in ombra (decisione [0019](../decisioni/0019-ombra-prima-di-accendere.md)):
prima si calcola e si confronta con il giudizio dei tutori, poi si mostra.

### 5.6 Il piano a giorni

Dal codice, non dal modello: giorni da oggi alla verifica, minuti al giorno (dagli orari dei
tutori), argomenti con la loro padronanza. Regole: primo giorno il quadro; gli argomenti deboli
prima; ogni giorno un'attività di studio e una di richiamo; la vigilia solo ripasso (mappa a
memoria, verifica finta, interrogazione sui deboli); «sposta» ridistribuisce senza superare i
minuti al giorno. Il piano si ricalcola ogni sera dalla padronanza.

### 5.7 Dati (proposta)

Nello stesso file SQLite degli esercizi, con `prepara_schema` come `esercizi/registro.py`:

| Tabella | Campi principali |
|---|---|
| `studio_verifiche` | id, persona, materia, argomento, data, stato (aperta, fatta, annullata), creata |
| `studio_materiali` | id, verifica, origine (cassetto, foto, biblioteca), riferimento, pagine, testo estratto, stato |
| `studio_argomenti` | id, verifica, titolo, pagine, confermato_da, ordine |
| `studio_piano` | verifica, giorno, fase (quadro, studio, ripasso), attività, argomenti, minuti, fatto |
| `studio_carte` | id, persona, argomento, domanda, risposta, pagina, stato del ripasso (intervallo, scadenza, facilità) |
| `studio_mappe` | id, verifica, autore (calliope o persona), versione, nodi e frecce in JSON, controllata |
| `studio_tentativi` | come `esercizi_tentativi`, con il tipo di attività e l'argomento della verifica |

La padronanza è una vista calcolata su `esercizi_tentativi` e `studio_tentativi`. Conservazione:
come gli esercizi dei minori (decisione [0031](../decisioni/0031-conservazione-dei-minori.md)).

### 5.8 Tool (proposta)

Un tool `studio` accanto a `esercizi`, con le azioni: `verifica_crea`, `verifica_stato`,
`materiale_aggiungi`, `argomenti_conferma`, `piano`, `piano_sposta`, `carte_inizia`,
`carte_rispondi`, `mappa_mostra`, `mappa_completa`, `mappa_aggiungi`, `ascolta_prepara`,
`simulazione_inizia`, `simulazione_consegna`. Le azioni che esistono restano in `esercizi`
(l'interrogazione e gli esercizi guidati); `studio` le chiama con l'argomento della verifica.
Errori in parole come gli altri tool (decisione [0018](../decisioni/0018-errori-dei-tool-strutturati.md)).

### 5.9 Regole dello Studio

1. **Indizi, non soluzioni.** «Soluzioni intere: mai» è il valore di serie per i minori; lo cambia
   solo il tutore.
2. **Conti e correzioni dal codice** dove si può; per il resto il giudizio del modello con il
   secondo parere e «da guardare tu» per il tutore.
3. **Solo dai materiali e dalla biblioteca**, con la pagina. Niente testo libero del modello come
   fonte.
4. **I materiali sono dati non fidati**: in busta, mai istruzioni.
5. **Giudizio a parole, senza voto.**
6. **L'audio non si salva**; il testo sì, con la conservazione dei minori.
7. **Il tutore vede** piano, padronanza, interrogazioni, mappe.
8. **Orari e tempo dei tutori** valgono anche per lo studio; i giorni di fila non spingono fuori orario.

### 5.10 Voci più espressive per il ripasso da ascoltare

Si parte con Piper (27/10). Il ripasso però si prepara in secondo piano, quando la DGX è libera, e
non ha il vincolo della latenza della voce dal vivo: può usare un motore più lento ma più
espressivo, senza toccare la voce di Calliope. Dalla ricerca
[`2026-09-21-voci-e-tts.md`](2026-09-21-voci-e-tts.md) (§ 7.2), i candidati con licenza libera e
italiano:

1. **Qwen3-TTS** (Apache-2.0) sulla DGX: italiano ufficiale, voce descritta a parole (VoiceDesign) ed
   emozioni; è il più adatto a due voci diverse che si raccontano un argomento.
2. **Chatterbox Multilingual V3** (MIT): italiano, controllo dell'enfasi; già indicato come clonatore
   per i dataset.
3. **Pocket TTS** (Kyutai), con le voci `italian` e `italian_24l`: più leggero, sulla CPU; utile come
   seconda voce se Qwen3-TTS non basta.

XTTS-v2 ha un buon italiano ma pesi non commerciali (CPML) e nessuno vende più la licenza; Kokoro è
stato provato e scartato il 13/10. Proposta: una prova d'ascolto su 3–4 minuti di un ripasso vero,
Piper contro Qwen3-TTS e Chatterbox, giudicata a orecchio come per Kokoro; il motore del ripasso
resta una chiave di configurazione separata da quella della voce.

---

## 6. Cosa cambia nel codice

| Dove | Cosa |
|---|---|
| `schermi/pagina/telefono/index.html` | la barra delle sezioni, le cinque viste, la riga della voce, la modalità In auto; il menu diventa la vista Io |
| `schermi/pagina/telefono/telefono.js` | un piccolo router sul frammento (`#/…`, `popstate`); `sincronizza` smista le schede per sezione invece che nel binario unico; `disponi` e `vaiA` valgono dentro una sezione; i pallini delle sezioni |
| `schermi/pagina/telefono/telefono.css` | barra, righe della voce, elenchi, tessere; i colori di oggi |
| `schermi/pagina/index.html`, `schermo.css` | la disposizione a tre colonne per il PC personale (3.6), con la conversazione a destra; i tasti; il trascinamento dei file verso `/api/immagine` e il cassetto |
| `satellite/client.py` | il tasto da tenere premuto per parlare sul PC (proposta); «apri la fotocamera sul telefono» verso l'altro satellite della persona |
| `schermi/pagina/schermo.js` | `SEZIONE_DI_TIPO` e la funzione «viva» per tipo; le schede piccole dentro la chat; le schede nuove dello studio (`DISEGNA.studio_*`, la mappa) |
| `schermi/schede.py`, `schermi/hub.py` | la sezione nelle schede; `GET /api/raccolte`; le notifiche per sezione |
| `schermi/cronologia.py` | l'indice per sezione e per tipo |
| nuovo `calliope/studio/` | verifiche, materiali, argomenti, piano, carte, mappe, padronanza, ripasso da ascoltare |
| `tools/studio.py` | il tool della 5.8 |
| `esercizi/` | domande dai materiali per le materie non calcolabili; criteri dell'interrogazione dai materiali |
| `config.py` | `studio: spento \| ombra \| attivo` (di serie spento), `studio_minuti_giorno`, `studio_mappa_nodi_max` |
| `prove/` | prove a secco del router e dello smistamento; prove dello studio (piano, padronanza, carte, controllo della mappa, materiali ostili) |
| `docs/aree/` | [schermi-telefono](../aree/schermi-telefono.md) e [minori](../aree/minori.md) aggiornati; una decisione per le sezioni e una per lo Studio |

---

## 7. Piano a passi

Ogni passo si prova da solo; quelli dello studio passano dall'ombra.

1. **Sezioni senza cambiare le schede.** Router, barra, voce sopra la barra, smistamento delle schede
   esistenti per sezione, Io al posto del menu, In auto. Nessun cambio nel server tranne la sezione
   nelle schede.
1b. **La disposizione per il PC personale** sulla pagina degli schermi, con la conversazione a destra;
   la stessa per tablet e TV.
1c. **Accento lilla di serie** e accento come preferenza personale; sezioni per età sul satellite di
   un minore.
2. **Le mie cose e i dettagli.** `GET /api/raccolte`, le pagine per tipo (Liste, Agenda, Lavori,
   Cassetto, Documenti, Ufficio, Giochi), la spunta della lista a tocco.
3. **Conversazione con le schede dentro** e i filtri.
4. **Studio, base.** Verifica, materiali (fotocamera multipagina, controllo e ordine, lettura come
   lavoro, conferma degli argomenti), piano a giorni, la home dello Studio, il canale «tocco» e la
   vista aperta nei dati del turno (capitolo 0); le attività sono quelle di oggi (`esercizi`).
4b. **Resoconto delle sessioni e riepilogo della verifica** come proiezioni dei tentativi e degli
   eventi.
5. **Padronanza in ombra**, poi mostrata.
6. **Carte** con il ripasso dilazionato.
7. **Mappa**: scheletro, mappa dello studente, controllo, a memoria, PDF (un formato solo).
8. **Verifica finta e interrogazione dai materiali.**
9. **Ripasso da ascoltare.**
10. **Vista del tutore** completa.

---

## 8. Decisioni di chi amministra (27/10)

Le domande aperte della prima stesura, con le risposte; ognuna è riportata nel capitolo indicato.

| # | Domanda | Decisione | Dove |
|---|---|---|---|
| 1 | Come si accende la modalità In auto? | **A mano**: un tocco su «In auto» e la pagina cambia modo; nessun riconoscimento automatico | 3.5 |
| 2 | Quali sezioni sul satellite personale di un minore? | Dipende dall'età: **da 13 anni** si vede anche Casa; **Ufficio sempre nascosto** ai minori | 3.1 |
| 3 | Il secondo parere del modello dell'agente basta per le domande delle materie non calcolabili? | **All'inizio sì**; poi il tutore può chiedere di controllare lui le domande (interruttore nella sua vista, spento di serie) | 5.3, Studio 4 |
| 4 | Pesi e calo della padronanza? | **Da tarare sui tentativi veri**, in ombra | 5.5 |
| 5 | Formato della mappa per il PDP? | Lo decidono i tutori, ma **fuori da questa implementazione**: per ora un formato solo | 5.4 |
| 6 | Tablet e TV? | **Stessa struttura, con la barra a sinistra** | 3.6 |
| 7 | Voce del ripasso da ascoltare? | **Piper con le voci italiane**; i motori più espressivi da provare sono in 5.10 | 5.3, 5.10 |
| 8 | Palette? | **Lilla su tutto**, e l'accento come **opzione personale** | 2.1 |
| 9 | Dove si riconoscono i bordi della pagina? | **In JavaScript sul telefono**, e il server ripete il controllo | 5.3, Materiali 1 |
| 10 | Quali tocchi entrano nella conversazione? | Come proposto: **entrano quelli che cambiano qualcosa** (spunta, togli, consegna, collega); non quelli che guardano (apri, scorri) | 0 |

Restano da provare sul vero: la fotocamera della PWA sull'iPhone, il tasto per parlare sul PC con
la pagina in secondo piano, la prova d'ascolto dei motori del ripasso.

## Fonti

- Codice: `calliope/schermi/pagina/telefono/index.html`, `telefono.js`, `calliope/schermi/pagina/schermo.js`,
  `calliope/schermi/schede.py`, `calliope/tools/esercizi.py`, `calliope/esercizi/registro.py`
- Documenti: [schermi-telefono](../aree/schermi-telefono.md), [minori](../aree/minori.md),
  [roadmap](../roadmap.md) (modulo studio S2–S5), decisioni 0018, 0019, 0031
- Canvas delle schermate: <https://claude.ai/artifact/9jHRk1eXpB6jzNXwzkhUHC>
- Astra AI: <https://astra-ai.co> (letto il 27/10/2026)
- J. C. Nesbit, O. O. Adesope, *Learning with concept and knowledge maps: a meta-analysis*,
  Review of Educational Research, 2006
- J. D. Karpicke, J. R. Blunt, *Retrieval practice produces more learning than elaborative studying
  with concept mapping*, Science, 2011
- Legge 8 ottobre 2010, n. 170 (DSA, strumenti compensativi)
