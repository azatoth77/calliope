# 0029. La conversazione di stanza: Calliope sempre in conversazione di gruppo

- **Stato**: accettata (13/10/2026, risposte di chi amministra alle sei domande del progetto),
  realizzazione a passi; **passo 0 fatto** il 13/10, la stanza vera (passi 1–8) da fare
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
   va mai su disco**: resta in RAM al più `stanza_audio_min` per la corsia lenta.
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
- Passi 2–8 del piano, ognuno con il suo interruttore e la sua misura sulla DGX; la prima misura
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
