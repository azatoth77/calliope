# 0029. La conversazione di stanza: Calliope sempre in conversazione di gruppo

- **Stato**: accettata (13/10/2026, risposte di chi amministra alle sei domande del progetto),
  realizzazione a passi; **passo 0 fatto** il 13/10, la stanza vera (passi 1–8) da fare
  *[storico: al 14/10 sera fatti i passi 0–2 e 4–6, con la tenuta su disco e i conoscenti
  ([0030](0030-conoscenti.md)), ognuno col suo interruttore, spenti di serie; restano il passo 3
  (corsia lenta, con il filtro della TV), il resto del passo 7 e il passo 8; vedi «Conseguenze»]*
  *[storico: il 14/10 sera fatto anche il passo 3 (corsia lenta, `stanza_lenta`, spenta di
  serie), con l'**eccezione temporanea** dell'audio del banco (sezione qui sotto); restano il
  resto del passo 7 e il passo 8]*
- **Area**: [stt-tts](../aree/stt-tts.md), [contesto-conversazione](../aree/contesto-conversazione.md),
  [voce-e-regole](../aree/voce-e-regole.md), [minori](../aree/minori.md),
  [satelliti](../aree/satelliti.md), [schermi-telefono](../aree/schermi-telefono.md)

## Contesto

Oggi Calliope sente solo ciò che le è rivolto: da addormentata l'audio non lascia il satellite se
la wake word non scatta, e dopo una risposta resta aperta 8 s (`followup_s`) per qualunque frase.
Il 12/10 sera, in auto (telefono come satellite, chi amministra e il ragazzo di 14 anni registrati),
questo ha dato quattro difetti insieme: risposte alle chiacchiere dentro gli 8 s, anche con delle
azioni possibili; blocchi a due voci attribuiti a una persona sola; la conversazione anonima del
satellite chiusa a ogni cambio di voce («conversazione chiusa: parla un'altra persona»); una frase
breve e storpiata presa dal rilevatore per un pericolo, fino a Telefono Azzurro e 112 nell'auto. Il
giudizio «rivolta a Calliope?» era giusto sui blocchi lunghi e sbagliato sui brevi, perché non ha
mai visto le chiacchiere. Chi amministra ha deciso che Calliope stia **sempre in conversazione di
gruppo**; il progetto è [`2026-10-13-conversazione-di-stanza.md`](../ricerche/2026-10-13-conversazione-di-stanza.md),
e il 13/10 ha risposto alle sue sei domande.

## Decisione

1. **Ascolto e trascrizione continui vicino a un satellite**, per sapere chi ha detto cosa e
   rispondere con cognizione quando Calliope è interpellata. Ogni frase si trascrive appena il VAD
   la chiude, in una corsia a bassa priorità; in secondo piano si ritrascrive, si riattribuisce chi
   parla sull'intero scambio, si segnano TV e radio e si scartano le allucinazioni. **L'audio non
   va mai su disco**: resta in RAM al più `stanza_audio_min` per la corsia lenta. *[14/10 sera:
   salvo l'eccezione temporanea e dichiarata del banco del passo 3, sezione «Eccezione: l'audio
   del banco».]*
2. **Azioni solo per ciò che è sicuramente rivolto a Calliope**: il nome e la voce riconosciuta
   con i permessi, come oggi. Senza il nome si risponde soltanto (e si legge per rispondere),
   solo se il giudizio «rivolta», con le righe della stanza, dice sì. Il «sì» della stessa voce a
   una proposta nata da una richiesta col nome resta una conferma. I permessi restano per frase;
   la stanza è un dato in busta, mai un'autorità.
3. **Quando la interpellano, Calliope recupera prima**: le frasi della stanza di quel satellite
   ancora in coda passano davanti a tutto, con un tetto (~1,5 s) oltre il quale c'è la frase
   d'attesa; gli ultimi 30–60 s della stanza sono sempre alla lettera nel contesto. I comandi
   diretti restano nella corsia veloce di oggi, senza frase d'attesa.
4. **Il guardiano non giudica in diretta le chiacchiere**: resta sulle frasi rivolte a Calliope;
   sulle altre guarda **dopo**, sulla trascrizione corretta e con lo scambio intero. Un segnale
   acuto dà **solo un avviso al tutore sullo schermo personale**, senza parole, mai un «Va tutto
   bene?» al ragazzo.
   **Cambiato il 14/10 sera da chi amministra** (ed è tutore): un avviso di pericolo al tutore
   (questo e quelli dei cancelli dei turni) porta **sulla sua scheda personale** la trascrizione
   delle righe del segnale con un po' di contesto, chi ha detto cosa, e, con `avvisi_audio`, il
   file audio di quelle frasi. Il motivo: un avviso «senza parole» arrivato giorni dopo è stato
   preso per un allarme nuovo, e il tutore non aveva modo di capire che cosa fosse successo. Il
   testo dell'avviso (a voce e in cima alla scheda) resta senza parole; trascrizione e audio solo
   sullo schermo personale del tutore, mai a voce, mai su altri schermi, mai a un adulto non
   tutore. L'audio è l'unica eccezione a «l'audio non va mai su disco»: un anello **in memoria**
   con i soli segmenti in cui parla un minore (e il contesto breve degli adulti di casa con lui),
   e su disco, nel cassetto del tutore, solo i segmenti di un segnale quando nasce un avviso,
   per `avvisi_audio_giorni` (30). Mai degli ospiti; in ombra niente su disco.
5. **Tenuta del testo della stanza**: nell'installazione di chi amministra **su disco per 60
   giorni per tutti, famiglia e minori compresi**; i **tutori possono cercare** a posteriori anche
   ciò che ha detto il ragazzo, gli altri adulti no. Ospiti mai su disco né nella ricerca.
   Confermato il 14/10 da chi amministra: per la stanza **a ogni età del minore**, senza la
   soglia dei 14 anni che vale per l'archivio delle conversazioni.
6. **Ospiti**: «Calliope, abbiamo ospiti» (detto da chiunque: spegne, non accende) ferma l'ascolto
   della stanza su quel satellite per **4 ore**.
7. **Telefono**: un interruttore «ascolto la stanza» sul telefono, **acceso di serie** anche sui
   dati mobili; lo stato è sempre visibile sugli schermi.
8. **Default del repository prudenti**: `stanza: spenta`, nessun satellite; la stanza si accende
   per satellite nel `calliope.locale.yaml`; tenuta di serie `memoria` (fino al riavvio, al più
   24 h) con minori e ospiti mai su disco. Spenta, il codice nuovo non apre flussi né carica
   niente.

Il contesto delle scelte, nelle parole di chi amministra: la privacy dentro la famiglia è relativa
(Calliope gira in casa; i minori non hanno privacy verso i genitori); la DGX oggi è in ufficio, ma
è temporaneo e si progetta come se fosse in casa ([0028](0028-decisioni-roadmap-12-10.md) punto 4).

## Eccezione: l'audio del banco (14/10 sera, temporanea)

Decisa da chi amministra il 14/10 sera, per misurare la corsia lenta (passo 3) sulla voce vera: il
progetto chiede WER e attribuzione «su un set di scambi registrati da adulti consenzienti», e un
set registrato apposta non c'è ancora.

- **Cosa**: con `stanza_audio_banco_giorni: N` nel file locale (di serie **0 = mai**; chi
  amministra: 7) e la corsia lenta accesa (`stanza_lenta`), l'audio dei segmenti della stanza va
  su disco con le trascrizioni della corsia veloce (v1) e della lenta (v2), in
  `<turn_log_dir>/stanza_banco/` (file 600, cartelle 700, fuori da git), per il banco
  `prove/manuali/banco_stanza_lenta.py --banco` (il riferimento lo scrive a mano chi
  amministra).
- **Solo quando tutte le voci del segmento sono persone di casa riconosciute dalla voce sopra
  soglia**, in tutte e due le versioni della riga, e nessuna finestra CAM++ del segmento è di una
  voce non riconosciuta: adulti di casa e **minori della famiglia**, che chi amministra, loro
  tutore, autorizza esplicitamente per questo banco. **Mai** ospiti, conoscenti, zona grigia
  (anche se la corsia lenta la corregge), voci sconosciute, «più voci», TV; mai in pausa
  («abbiamo ospiti»).
- **Scadenza**: N giorni dalla prima accensione (il segno `acceso.json` nella cartella); poi
  smette da sé e lo dice nel log e in `calliope stato --turni`. I file restano per il banco al più
  `turn_log_days` (rotazione per giorno). Per ricominciare serve una scelta nuova: svuotare la
  cartella e riaccendere.
- **Cancellazione**: «dimentica» toglie i file del satellite; `calliope conserva --svuota` tutto
  (anche il segno dell'accensione), `--persona` i segmenti con la sua voce.
- **Perché un'eccezione e non una regola nuova**: il punto 1 («l'audio non va mai su disco») resta
  il valore della stanza; questa è una misura a tempo, con un fine solo (il riferimento per la
  WER), dichiarata nel file locale come la tenuta dei minori.

## Cosa cambia nelle decisioni di prima

- **[0028](0028-decisioni-roadmap-12-10.md) T1** («turni e audio dei soli adulti per 60 giorni;
  di minori e ospiti mai»): resta per turni, eventi, voce e archivio delle conversazioni. Per il
  **testo della stanza**, nell'installazione che la accende con `stanza_tenuta: {giorni: 60}`,
  vale per tutta la famiglia, minori compresi; mai gli ospiti. Il testo della stanza **non è un
  dato per le misure**: il banco e la regressione non lo leggono. `conserva.decidi` ha una cosa
  nuova, `stanza`.
- **[0027](0027-conversazione-come-registro-di-eventi.md)** («un registro per persona più uno
  anonimo per satellite»): si aggiunge un **terzo tipo di registro**, `stanza:<corsia>`, del
  canale come l'anonimo, in sola aggiunta, con le revisioni come eventi nuovi. Una porta sola verso
  le persone: il blocco caldo nei dati del turno (visibilità «turno»), mai copiato nel registro
  della persona.
- **Visione** («nessuna registrazione continua in condizioni normali, stato sempre visibile»):
  resta vera per l'**audio**; si aggiunge «trascrizione continua solo con la modalità stanza
  accesa, segnalata sugli schermi e fermabile a voce».
- **Principio 8 e [0006](0006-half-duplex-e-barge-in.md)** (half-duplex): **non cambiano adesso**.
  Se il passo 5 del piano accende l'ascolto della stanza mentre Calliope parla (con il filtro
  dell'eco), l'eccezione vale per la sola trascrizione della stanza, mai per i comandi, e la
  scrive quel passo.
- **Compagnia** ([stt-tts](../aree/stt-tts.md), 09/10): il passo 0 stringe la compagnia anche con le
  voci tutte riconosciute (niente azioni senza il nome, conversazione anonima condivisa, rilevatore
  solo sulle frasi rivolte).

## Alternative considerate

- **Restare come prima** (solo ciò che è rivolto a Calliope, la finestra di 8 s): è proprio il
  difetto del 12/10, scartata.
- **Le proposte prudenti del progetto** sulla tenuta (solo in memoria), sulla ricerca (nessuna
  ricerca delle parole del ragazzo), sul telefono (solo in Wi-Fi o spento di serie) e sugli ospiti
  (nessun comando): restano i valori del repository, ma non quelli dell'installazione di chi
  amministra.
- **Il «Va tutto bene?» al ragazzo** per un segnale sentito nelle chiacchiere: scartato; il
  momento è passato e dirlo a minuti di distanza spaventa senza aiutare.
- **Il nome sempre**, anche per rispondere: scartato; i seguiti senza il nome restano utili quando
  il giudizio «rivolta» li vede, e non fanno niente.

## Conseguenze

- **Passo 0, fatto il 13/10** (utile già senza la stanza, ramo `stanza-passo-0`): in compagnia
  niente azioni senza il nome (`compagnia_azioni_col_nome`), la conversazione anonima del satellite
  condivisa e non più chiusa a ogni cambio di persona (`compagnia_anonima_condivisa`), il
  rilevatore di pericolo che non vale sulle frasi giudicate non rivolte anche col giudizio in ombra
  (`compagnia_pericolo_solo_rivolte`). Un interruttore per punto, accesi di serie; prova
  `prove/prova_compagnia_passo0.py`.
- **Passo 1, fatto il 13/10 sera** (ramo `stanza-passo-1`, `stanza: ombra` nel file locale, di serie
  spenta): protocollo 3 con il flusso della stanza, VAD della stanza sul satellite Python e sul
  telefono (interruttore acceso di serie), Whisper con la precedenza turno > recupero > stanza,
  registro della stanza **in memoria** con le presenze per persona, segno sugli schermi,
  `stanza_pausa` («abbiamo ospiti»: 4 ore), «dimentica»; niente al modello, solo misure
  (`calliope stato --turni`, sezione «Stanza»). La tenuta su disco (`stanza_tenuta`) è del passo
  dopo.
- **Tenuta su disco, fatta il 14/10** (ramo `stanza-tenuta`, `stanza_tenuta: true` nel file locale,
  di serie spenta; `calliope/stanza/tenuta.py`, `prove/prova_stanza_tenuta.py`): punto 5 con un file
  suo (`stanza.db`, FTS5), la ricerca su disco con gli stessi permessi, «dimentica» e
  `calliope conserva --svuota` anche lì, il blocco caldo solo dalla memoria.
- **Passo 6 in ombra, fatto il 14/10** (ramo `stanza-guardia`, `stanza_guardia: ombra` nel file
  locale, di serie spenta; `calliope/stanza/guardia.py`, `prove/prova_stanza_guardia.py`): punto 4
  con il rilevatore di oggi a posteriori sulle chiacchiere con un minore; in ombra solo misure
  senza parole (`calliope stato --guardia`), «attiva» solo l'avviso al tutore sullo schermo
  personale, da accendere con meno di un acuto falso a settimana.
- **Trascrizione e audio negli avvisi, 14/10 sera** (ramo `avvisi-data`, `avvisi_trascrizione`
  di serie accesa, `avvisi_audio` di serie spento; `calliope/avvisi_audio.py`,
  `prove/prova_avvisi_audio.py`): il punto 4 cambiato come sopra; `calliope conserva --svuota`,
  «dimentica» della stanza e la scadenza tolgono trascrizione e audio, l'avviso resta.
- **Passo 2, fatto il 14/10** (ramo `stanza-passo-2`, `stanza_contesto`, di serie spento;
  `calliope/stanza/contesto.py`): le righe della stanza nei dati del turno in busta (fonte
  `stanza`, ultimi 45 s sempre alla lettera), la copertura all'interpellazione, il giudizio
  «rivolta» con le righe (in ombra). Il 14/10 sera (ramo `stanza-caldo-cache`,
  `stanza_contesto_in_storia`) le righe entrano nella storia in sola aggiunta, per la cache del
  prefisso.
- **Passo 4, fatto il 14/10** (ramo `stanza-passo-4`, poi `stanza-cerca-2`; `stanza_cerca`, di
  serie spento): il tool `stanza_cerca` con i permessi del punto 5, la frase d'attesa e la ricerca
  anticipata con le parole della frase.
- **Passo 5, fatto il 14/10** (ramo `stanza-durante-voce`, `stanza_durante_voce`, di serie
  spento): la stanza si ascolta anche mentre Calliope parla, con il filtro dell'eco sul testo;
  solo la trascrizione della stanza, i comandi restano half-duplex. Si accende solo dopo la
  misura vera (`prove/manuali/misura-eco-stanza.md`).
- **Passo 6, ripresa e gioco, 14/10 sera** (ramo `stanza-guardia-2`): il guardiano riprende dal
  disco le righe non giudicate dopo un riavvio e giudica col gioco aperto dichiarato.
- **Passo 3, fatto il 14/10 sera** (ramo `stanza-passo-3`, `stanza_lenta`, di serie spento;
  `calliope/stanza/lenta.py`, `prove/prova_stanza_lenta.py`, banco
  `prove/manuali/banco_stanza_lenta.py`): a DGX libera la ritrascrizione (con un Whisper suo se il
  piano lo consente), chi parla sullo scambio con le finestre CAM++ (blocchi con due voci
  spezzati), la TV a strati senza Home Assistant, le allucinazioni, il riassunto progressivo;
  righe di versione 2 in sola aggiunta, la storia del modello non riscritta, il guardiano che
  rigiudica solo un cambio sostanziale. Con l'eccezione temporanea dell'audio del banco (sopra).
- *[Storico al 14/10: dei passi 2–8 qui sotto restano il 3, il 7 oltre i conoscenti e l'8.]*
  *[Storico al 14/10 sera: il 3 è fatto.]*
  Passi 2–8 del piano, ognuno con il suo interruttore e la sua misura sulla DGX; la prima misura
  (passo 1) non cambia nulla di ciò che Calliope dice. Misure nuove: ritardo della coda della
  stanza, banda del telefono, **copertura all'interpellazione** (tutte le frasi dette prima della
  domanda nel contesto della risposta).
- Il profilo ridotto da 8 GB ([0028](0028-decisioni-roadmap-12-10.md) punto 3) ha la stanza in
  forma minore; se la memoria non basta resta spenta e `calliope stato --piano` lo dice.
- Rischi dichiarati: la trascrizione continua di un minore su disco (scelta di chi amministra,
  dichiarata nel file locale); un comando detto dalla TV letto come riga (la busta e il contatore
  «ESEGUITE con un bersaglio dal dato» devono restare a 0); la latenza dei turni con la coda
  della stanza (`stt_s` invariato è una misura obbligatoria del passo 1).

## Fonti

- [`2026-10-13-conversazione-di-stanza.md`](../ricerche/2026-10-13-conversazione-di-stanza.md)
  (§ 7 con le risposte, § 3.11 il recupero all'interpellazione, § 6 il piano)
- [`2026-10-09-piu-persone.md`](../ricerche/2026-10-09-piu-persone.md) (compagnia, misure A–E)
- Decisioni [0006](0006-half-duplex-e-barge-in.md), [0025](0025-minori-due-cancelli.md),
  [0027](0027-conversazione-come-registro-di-eventi.md), [0028](0028-decisioni-roadmap-12-10.md);
  [`visione.md`](../visione.md)
