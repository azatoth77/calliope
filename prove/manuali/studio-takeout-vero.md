# Prova col Takeout vero di Classroom e coi file scaricati (31/10/2026, issue #298)

Decisione [0035](../../docs/decisioni/0035-studio.md) punti 48–51, documento d'area
[studio](../../docs/aree/studio.md) («L'importazione dei materiali scaricati»). La fa **chi
amministra**: un'esportazione vera contiene nomi, compiti e materiali di persone vere. Tutto ciò che
viene da lì (l'archivio, gli elenchi dei file, le note, gli screenshot) va in `privato/` (fuori da
git), mai nel repository; nelle issue e nei documenti solo conti e strutture senza nomi.

Serve lo Studio acceso per la persona (`studio_modo: attivo`, o `ombra` per chi amministra, che
vede «Prova») e una verifica in bozza o aperta.

## A. L'archivio di Takeout (per la seconda parte della #298)

1. Su takeout.google.com, con l'account scolastico, scegliere **Classroom** e **Drive** (i file
   allegati ai compiti stanno nella cartella «Classroom» di Drive), formato ZIP, 2 GB per parte.
   Scaricare l'archivio in `privato/takeout/` (più parti: `takeout-…-001.zip`, `-002.zip`…).
2. Senza aprirlo con Calliope, scrivere in `privato/takeout/struttura.txt` l'albero delle
   cartelle e i nomi dei file JSON e HTML di Classroom (con `python -I -m zipfile -l <archivio>`),
   e di un corso: il file del corso, dove stanno post, compiti e materiali, i campi delle scadenze
   (`dueDate`, `dueTime` o altro), come sono citati gli allegati di Drive (titolo, id, link) e in
   che formato arrivano i documenti Google (docx, pdf, pptx). Questo serve a scrivere la seconda
   parte: oggi il Takeout entra come uno ZIP qualunque.
3. Controllare la dimensione delle parti contro i tetti (`studio_importa_max_mb` 100,
   `studio_importa_file_max` 500, `studio_importa_totale_max_mb` 300): se un'esportazione di soli
   Classroom e Drive li supera, annotarlo (quanti MB, quanti file) per tararli nel file locale.

## B. L'importazione dei file com'è oggi

1. Dal telefono (390 px) e dal PC personale: home dello Studio → la verifica → «Aggiungi
   materiali» → «Scegli i file». Provare, uno alla volta e poi insieme:
   - un PDF scaricato da Classroom e un documento Google esportato in PDF;
   - lo stesso documento esportato in docx e in pptx (o la presentazione in pptx);
   - una foto della galleria;
   - uno ZIP di Drive con due o tre file;
   - una parte dell'archivio di Takeout (anche se oggi è uno ZIP qualunque: i JSON diventano «non
     letto: formato che non importo», gli allegati di Drive entrano).
2. Guardare la scheda: le fasi che avanzano da sole, i conti («N file, N pagine»), «I file» con le
   righe «non letto» e il loro motivo. Chiudere la pagina a metà e riaprirla: il lavoro è andato
   avanti. Provare «Ferma» e «Riprendi» su uno ZIP grande.
3. Sulla DGX, `calliope stato` e il registro: nessun errore `[STUDIO] importazione`, i tempi.
   Durante un'importazione grande parlare con Calliope: la voce non deve rallentare (la prima
   frase come al solito).
4. Le pagine: quelle di testo già lette, i PDF e le foto letti dal lettore quando la DGX è libera,
   poi gli argomenti proposti. Il piano dice «materiale N» e non il nome del file.
5. Dal telefono del minore con **Family Link**: aprire la pagina dello Studio e «Scegli i file»;
   annotare se il selettore si apre e da dove (galleria, File, Drive). Se il browser è bloccato,
   provare dal telefono del tutore nella verifica del minore.

## C. Cosa annotare (in `privato/`, e i soli conti nella #298)

- Formati e dimensioni dei file veri; quanti «non letti» e perché.
- I tempi: dall'invio a «Estratto», e fino agli argomenti.
- Su Android, se la PWA installata compare fra le app di «Condividi» (oggi non deve: lo share target
  è la terza parte); su iPhone, da dove si arriva al file.
- Cosa funziona e cosa no col telefono del minore con Family Link.
