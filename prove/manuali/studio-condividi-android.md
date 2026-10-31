# «Condividi» verso Calliope da Android (31/10/2026, issue #298 parte 3)

Decisione [0035](../../docs/decisioni/0035-studio.md) punto 52; documento d'area
[studio](../../docs/aree/studio.md) («La condivisione dal telefono»). Il «Condividi» del sistema non
si emula nelle prove: questo è il giro a mano. File di fantasia o di scuola, mai nel repository; le
note con dati veri in `privato/`.

Serve lo Studio acceso per la persona e una verifica aperta; il telefono già abbinato.

## A. Telefono Android di un adulto

1. In Chrome aprire `https://<calliope>/telefono/`, poi menu ⋮ → «Installa app» (o «Aggiungi a
   schermata Home»). Aprire Calliope dall'icona almeno una volta (il service worker parte).
2. Da Classroom, Drive, Gmail o File: un PDF → «Condividi» → «Calliope». Si apre Calliope su Le mie
   cose con «Condiviso con Calliope» e il nome del file.
3. «Aggiungi ai materiali» è spento: scegliere la verifica, poi toccarlo. La riga dice «Mando 1 di
   1: 25 %… 100 %», poi «Mandato». «Apri lo Studio»: «Aggiungi materiali» della verifica con
   l'importazione che avanza.
4. Ripetere con più file insieme (foto e un docx), con uno ZIP, con un file non ammesso (un APK:
   Calliope non deve comparire fra le app).
5. Condividere e poi «Annulla»: niente sul server (`calliope stato`, nessuna importazione nuova).
6. Condividere, non scegliere, chiudere l'app; riaprirla dopo più di un'ora: niente riquadro.
7. Disinstallare la PWA, reinstallarla e condividere **subito** prima di aprirla: annotare se arriva
   «La condivisione non è arrivata…» e se dopo un'apertura funziona.
8. Il riquadro dice «Arrivati da una condivisione: controlla che siano i file che hai condiviso tu».
9. Una pagina di un altro sito (revisione della PR #369): dal telefono aprire in Chrome una pagina
   di prova di casa (non di Calliope) con un modulo che manda un file con POST a
   `https://<calliope>/telefono/condividi`. Inviarlo: Calliope **non** deve mostrare «Condiviso con
   Calliope» con quel file (si apre Le mie cose senza riquadro). Annotare cosa succede anche se il
   modulo ha `rel="noreferrer"`: lì il file può comparire, e il riquadro deve chiedere di controllare.

## B. iPhone

1. Da File o da Classroom «Condividi»: Calliope **non** deve comparire (Safari non ha lo share target
   per le PWA). Annotare.
2. Da Calliope: Studio → la verifica → «Aggiungi materiali» → «Scegli i file» → File o Drive: il
   file arriva come sopra.

## C. Il telefono del minore con Family Link

1. Con Chrome bloccato: annotare che Calliope non si apre e non compare in «Condividi».
2. Se il genitore permette in Family Link solo l'indirizzo di Calliope: installare la PWA e
   ripetere A.2–A.3. Fuori dagli orari del minore l'invio deve dire che è l'ora di riposare (403).
3. In ogni caso: dal telefono del tutore, condividere nella verifica del minore (la verifica compare
   con «di <nome>»).

## D. Cosa annotare (in `privato/`, nella #298 solo l'esito)

Modello del telefono e versione di Android e di Chrome; se Calliope compare in «Condividi» e per
quali tipi; i tempi dall'invio a «Estratto»; cosa succede con Family Link.
