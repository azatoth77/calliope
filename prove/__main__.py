"""
Tutte le prove in un comando: `python -m prove` (dalla radice del progetto).

    python -m prove              # livello 1 + livello 2 (legate ai file cambiati): ~30–90 s
    python -m prove --completo   # tutte le prove a secco: prima dell'unione su main
    python -m prove --ollama     # anche quelle con il modello vero (qualche minuto)
    python -m prove --help       # le altre opzioni (--hook, --staged, --ramo, -j, --timeout)

Ogni prova è uno script di prove/ che esce con 1 se qualcosa non va e con 77 se si salta
per intero (manca un browser, una voce, un modello…). Dal 06/10 (P5 dell'analisi
complessiva) a livelli: 1 le veloci, sempre, in parallelo; 2 quelle legate ai file cambiati
(LEGAMI), in parallelo; 3 lunghe, con il browser, con Calliope vera o in tempo reale, in
serie, solo con --completo. Ogni prova ha un tempo massimo (300 s) e gira in un job object
(Windows). L'hook (.githooks/pre-commit) lancia `--hook --staged`: livelli 1 e 2 sulla copia
dell'indice. Non tocca speakers.json, memoria.db né registro/: le prove usano file temporanei.
"""

import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent

A_SECCO = [
    ("prova_testo.py", [], "wake word testuale, uscite, pulizia, frasi, calcola"),
    ("prova_runner.py", [], "il runner stesso (06/10, Q7): ogni prova registrata o manuale, legami dei tool d'area, salti parziali segnalati"),
    ("prova_conflitti.py", [], "nessun segno di conflitto di git (<<<<<<<, =======, >>>>>>>) nei file di testo tracciati (09/10: il CHANGELOG letto a voce dalle novità li aveva)"),
    ("prova_dati_privati.py", [], "nessun dato privato nei file tracciati (06/10, pubblicazione): file vietati, segreti, IP privati non d'esempio, DuckDNS, percorsi utente, termini di privato/termini.txt"),
    ("prova_docs_aree.py", [], "documenti d'area (06/10, Q8): i nomi in backtick delle tabelle «Moduli» esistono nel codice"),
    ("prova_e2e_copioni.py", [], "prova end-to-end della DGX (prove/e2e/) a secco: copioni ben fatti, controllo dei passi, sfida, nessun dato personale"),
    ("prova_pronuncia.py", [], "pronuncia degli inglesismi (04/10): «file» → «fàil», contrari, solo il testo per Piper"),
    ("prova_personalita.py", [], "personalità (04/10): toni di voce, wake word cambiata e in testa alla frase, modalità startrek, suoni di ascolto"),
    ("prova_frasi.py", [], "frasi pronte meno monotone (12/10, calliope/frasi.py): catalogo con varianti per tono e forma breve (segnaposto, domanda in fondo, lei nel formale, classi bloccate), ombra/attivo/spento, rotazione per persona, id dall'uscita unica nel registro dei turni, ripetizioni ogni 100 in stato --turni, campione di 30; lingua delle forme (accordo col titolo, forme brevi, lei nel formale) con i contrari (12/10 sera)"),
    ("prova_frasi_rotazione.py", [], "rotazione delle frasi pronte (18/10, #158, calliope/frasi.py): due «grazie» di fila da una voce sconosciuta danno due varianti (attivo e ombra), senza forma breve, e la misura non conta ripetizioni; dopo un riavvio simulato (Frasi.riprendi dai turni di oggi) la stessa persona non riceve la variante appena detta e la forma breve riprende; contrari: niente su disco per una voce sconosciuta (nessun file, turni di ospiti e conoscenti non riletti, registro senza parole), turni di ieri, righe rotte, UTF-8 troncato, valori del tipo sbagliato e guasti senza sollevare (PR #162), conoscente senza livello, cartella assente, id senza tono; main la chiama dopo configura, dentro un try"),
    ("prova_modalita.py", [], "modalità cambiata a voce (05/10): solo chi amministra dalla voce, subito e salvata, cosa è acceso davvero, satellite collegato aggiornato e modello mandato dal server, satellite vecchio, telefono, ritorno alla normale"),
    ("prova_tool.py", [], "tool nativi e permessi per livello"),
    ("prova_sicurezza.py", [], "sicurezza (analisi del 03/10): registrazione della voce, fatti della casa, sandbox, apri, permessi"),
    ("prova_politica.py", [], "politica unica dei tool (05/10): provenienza, dati non fidati in busta, classi, banco d'attacco da web, foto, allegati, estensioni, archivio, agenti"),
    ("prova_conferma_unica.py", [], "una conferma per azione (06/10, caso della DGX): «creiamo…» con una foto di mezzo, conferma della politica e «Procedo?» del tool fusi, sfida, doppioni di una funzione che c'è già, annuncio coerente con la dimostrazione"),
    ("prova_dopo_annunci.py", [], "il turno dopo un annuncio o un risultato (07/10 sera, casi della DGX): «Fammene un PDF» dopo il risultato di un lavoro (dati del turno LAVORO_MSG e contrari, spinta di documento_crea, descrizioni), «Quale apro?» con le date di modifica e i risultati dal più recente, il timer già suonato (riferimento dell'agenda che cade, cambio non chiesto con la conversazione pulita e contrari), la frase del codice in coda a lavoro_risultato che riferire non ferma, il prefisso scaldato dopo un cambio del prompt di sistema"),
    ("prova_risultati.py", [], "risultati dei lavori e consensi (07/10, casi della DGX): lavoro_risultato (quale lavoro, riassunto salvato o dal modello dell'agente, tempo massimo, schermo, codice mai a voce, dopo un riavvio, permessi), dichiarazioni «inizio subito il lavoro», il «sì» di chi non ha la proposta, «Ma sì dai, perché no?» e i contrari; casi del 07/10 mattina: falso allarme di riferire su «installarlo», scheda del risultato nella zona grigia e dopo schermo_mostra, lavoro_stato con i lavori finiti dal disco; del pomeriggio: «Sì, grazie.», «Mostramelo.» nella zona grigia, «ho recuperato il dato» dopo tool falliti; 09/10 sera: un riferimento che non è un lavoro non ripiega mai su un altro (errore con i lavori veri, documento_leggi se è un documento di Calliope)"),
    ("prova_estensioni_versioni.py", [], "versioni di un'estensione a voce (08/10, giro 10, caso della DGX): sviluppo_apri con un nome simile è un'estensione nuova e con modifica una versione nuova, annuncio ed elenco con il titolo di prima e quello nuovo, «attiva» → approva e «riattiva» di una già attiva, cosa fa dopo l'approvazione, dati del turno dell'estensione nominata (EST_NOMINATA_MSG) con i contrari, lavoro_affida che cambia un'estensione → sviluppo_apri, analisi «ESTENSIONE», lavoro_stato con la versione da approvare, registro dei turni di una risposta interrotta (risposta_inviata)"),
    ("prova_sviluppo_v2.py", [], "modalità sviluppo, versione 2 (08/10, il giro vero della DGX): nomi nuovi dei tool e i vecchi che valgono ancora, lavoro_affida di codice allo sviluppo, apertura esplicita con la specifica letta e il titolo leggibile, collaudo fallito → «Lo faccio correggere?», sviluppo_chiedi con il contesto conservato (sola lettura, non fidato, tempo massimo), sviluppo_correggi sui file della versione provata, chiusura con la conferma e sospensione con l'agente al lavoro, lavoro finito che riapre lo sviluppo al collaudo, tappe ai limiti del giro con i segnali di giro a vuoto e «continua» (servizio dei lavori vero, Ollama finto)"),
    ("prova_sviluppo_giro3.py", [], "il giro vero della DGX dell'08/10 pomeriggio (giro 3 della modalità sviluppo): URL non codificato rifiutato dalla porta, da RetePubblica e da CalliopeFinta, traccia di rete del collaudo per sviluppo_chiedi e sviluppo_correggi (ripulita), storpiature della trascrizione nella provenienza, due collaudi nella stessa frase, l'esito dopo la sfida, «ok» in coda non è consenso, nome simile senza modifica → la scelta al modello, l'elenco vero delle estensioni, rinomina"),
    ("prova_sviluppo_giro4.py", [], "il giro vero della DGX dell'08/10 sera (giro 4 della modalità sviluppo): modifica con una descrizione al posto del nome → l'unica estensione nominata, una disattivata non rende ambiguo il titolo di un'attiva, il «sì» breve apre lo sviluppo di un'estensione senza sfida e la sfida tiene la chiamata intera, collaudo con più input (argomenti, «N giorni» nei dati, gli input nei dati del turno, gli argomenti veri per l'agente), analisi senza testo ripetuto e «avanti» che accetta, il titolo della persona nella revisione e nell'approvazione"),
    ("prova_estensione_rimuovi.py", [], "eliminazione definitiva di un'estensione (09/10): «rimuovi» sceglie la disattivata tra due omonime, la domanda dice quale (stato, versione, cosa fa, l'omonima che resta) e che è definitiva, un'attiva prima si disattiva, sviluppo aperto o lavoro in corso la bloccano, dopo spariscono tool, «sempre», elenco, partite e schede che rimandano a lei; cartella in sola lettura cancellata"),
    ("prova_sviluppo_giro5.py", [], "il giro vero della DGX dell'08/10 sera (giro 5 della modalità sviluppo): doppia codifica (quote_plus e poi urlencode) segnalata nella traccia del collaudo, nei vincoli della correzione e dell'analisi, nel registro delle uscite e in CalliopeFinta, mai rifiutata; il secondo collaudo nella stessa frase con `argomenti` detti (anche i numeri a parole) e i contrari, il rifiuto «NON è partito»; «la gente» per «l'agente» nei dati del turno; il lavoro che riparte dall'analisi con i collaudi e la traccia; il giro a vuoto nel ragionamento dell'agente fermato (spinta, segnale, passo sulla scheda) e i contrari (codice, tabelle, frasi corte); presence_penalty per tipo di lavoro solo per vLLM"),
    ("prova_agente_guida.py", [], "la guida dell'agente (11/10, il gioco «Halloween» della DGX, 45 minuti a vuoto): ogni controllo dice dove e perché (prova di fumo con l'elemento, file:riga, la frase sul gestore e i tocchi prima; dichiarazioni doppie con le due righe; test JS e Python con asserzione e riga; programma e C#; registro, diario, consegna rifiutata; l'estensione che si ferma; il manifesto con il valore), scheletri di partenza per tipo che passano i loro test, test_estensione.py di partenza con la firma giusta (13/10; contrari: firma sbagliata, rotta senza input, modifica, gioco), spinta con l'ultimo errore dopo un giro a vuoto e dopo tre riscritture intere, modifica_file e leggi_file con riga; contrari"),
    ("prova_sviluppo_giro6.py", [], "il giro vero della DGX dell'08/10 sera (giro 6 della modalità sviluppo): «ferma» che ferma il lavoro dell'agente e «sospendi» che lo lascia finire (con la domanda), «rifai» che riparte subito con la stessa specifica dopo un lavoro fermato o non andato, un collaudo per valore quando il modello ha separato i valori di un elenco (contrari: un nome solo con «e», un numero, solo dati), i valori della chiamata di prima validi dopo il risultato, i dati del turno"),
    ("prova_giro_ombra.py", [], "il giro vero della DGX del 10/10 mattina (06:09–06:18): un programma diverso con uno sviluppo aperto non conferma quello vecchio (sostituzione di una parola piena del titolo: «moltiplica» per «somma», «parole» per «vocali»), la domanda con i due titoli e il «sì» che sospende e apre il nuovo; contrari: la stessa richiesta con altre parole e il «sì» restano conferma, una modifica resta dello sviluppo aperto; dichiarazioni d'azione sulle fasi dello sviluppo («l'analisi è stata annullata», «procedo allora con lo sviluppo», «siamo passati alla fase di sviluppo») trattenute, con i contrari (lo stato, l'offerta, le domande)"),
    ("prova_giro_chiusura.py", [], "il secondo giro vero della DGX del 10/10 (07:11–07:21): chiudere uno sviluppo a voce (la domanda «… Lo chiudo?» in fondo, registrata come proposta; il sì anche lungo chiude, «sospendi» e «no» no; uno sviluppo sospeso si chiude con la stessa conferma), «chiudo definitivamente lo sviluppo» senza tool trattenuto con i contrari (domande, offerte, condizionali), titoli che tengono la parola che distingue («il numero di vocali» / «di parole»), la storia uguale a ciò che è andato alla voce (turno ricostruito col ciclo; resa per la voce allineata, `storia_come_detta`; frasi d'attesa fuori)"),
    ("prova_giro3.py", [], "il terzo giro vero della DGX del 10/10 (10:37–10:44): un altro compito messo nella modifica dell'analisi diventa la domanda «sospendo e apro?» (`sviluppo_analisi_altro`; contrari: le modifiche vere), una conferma senza parole riconoscibili («CQD») non vale come sì (`consenso_irriconoscibile`, anche con la conferma breve e proposta_rispondi; contrari: sì, ok, va bene, certo, chiudilo, le storpiature), titoli con le parole che distinguono («…Celsius in Fahrenheit», «…chilometri in miglia»), «chiudi tutti gli sviluppi» (quale = tutti, una domanda, il lavoro fermato), «ricominciamo» detto al satellite prima della chiusura (`voce_frase_non_detta` se non lo dice)"),
    ("prova_giro4.py", [], "il quarto giro vero della DGX del 10/10 (11:46–11:51): le frasi dette fuori da una risposta («ricominciamo», «esci», la cortesia, gli annunci) in un turno della voce nuovo, così il satellite non le scarta al turno 0 di una corsia nuova né dopo aver sentito il nome (il satellite finto scarta come il vero), il cambio di sviluppo con la frase di sfida si apre all'analisi e il lavoro parte al «sì» all'analisi (`sviluppo_analisi_prima`), l'elenco degli sviluppi sospesi con tutti nel conto, i più recenti per nome e «e altri N», un argomento di sola punteggiatura vale come vuoto e la risposta «…» dopo i giri di correzione ha il ripiego"),
    ("prova_giro_pomeriggio.py", [], "il giro vero della DGX del 10/10 pomeriggio (15:11–15:58): l'avviso dei segreti di riferire una volta, nel turno del dato (nei turni dopo senza un dato nuovo solo se il dato chiedeva codici, e la frase fissa già detta non si ripete; contrari: la pagina che chiede il codice, un'altra pagina nuova), un gioco chiesto come programma diventa un'estensione-gioco con la proposta «Lo faccio come gioco sugli schermi» (`sviluppo_gioco_schermi`; contrari: finestra per il desktop, terminale in Python), `sviluppo_<azione>` inventati → sviluppo_passo con l'azione prima del nome vicino (`tool_nome_azione`; contrari: tool veri, nomi vecchi, lavoro_ferma), conversazione_nuova che non dice di cancellare"),
    ("prova_giro_sera_gioco.py", [], "il giro vero della DGX del 10/10 sera (17:32–17:33, dopo la correzione del pomeriggio): un gioco chiesto con sviluppo_apri tipo estensione senza il flag riceve il flag (`sviluppo_gioco_schermi`) e non passa dall'analisi delle estensioni (che con le risposte vere dell'agente diceva vaga e poi «impossibile: la richiesta non specifica la sezione scheda»; contrari: un gioco per Windows con una finestra, un'estensione che conta i punti del gioco di carte, gioco=true già detto, una modifica); il testo dell'analisi delle estensioni dice che la scheda e il JavaScript li sceglie l'agente; il titolo di un compito lungo («gioco di Halloween», non l'inizio troncato a 80 caratteri) senza peggiorare i titoli buoni"),
    ("prova_giro_halloween.py", [], "il giro vero della DGX dell'11/10 (15:37–16:27, il gioco di Halloween delle porte): il collaudo di un gioco è vederlo (la versione candidata aperta in prova sullo schermo da cui si parla, scheda con «prova»: true, senza ponte verso Calliope, non attiva né chiedibile; contrari: non un gioco, file cambiati, dopo l'approvazione, partita vera, familiare), sviluppo_correggi su uno sviluppo fermo senza versione rifà il lavoro con il problema e i file già scritti (`sviluppo_correggi_rifai`), l'avviso di tappa con un conteggio dei test solo, il motivo dell'arresto deciso da Calliope nel contesto e nell'esito di sviluppo_chiedi, il titolo che non finisce con una preposizione, il titolo del proprio sviluppo bersaglio fidato (contrari: un'altra persona, nessuno sviluppo, un altro tool)"),
    ("prova_agente_giri_uguali.py", [], "l'agente dei giochi che gira a vuoto (18/10, #174, il tris per due della DGX): il contratto dice che ogni partita comincia nella «preparazione» («Inizia» con min = max, «N giocatori», apriGioco({ inizia: true })), l'errore di apriGioco nella preparazione dice la via d'uscita (contrari: «avanti», senza l'opzione), firma_errore con l'uscita vera (FALLITO e poi «ok … errore»; contrari: Python, test verdi), modifica_file e i numeri dei test come novità e le passate senza un test verde in più nel ciclo vero, la frase a voce vera, la specifica di un gioco riscritta dai requisiti e il lavoro che non parte con il cuore impossibile (`sviluppo_specifica_dai_requisiti`, `sviluppo_nucleo_impossibile`; contrari: un programma, un lavoro senza blocco), due tappe allo stesso punto → «faccio consegnare quello che funziona?» e l'istruzione all'agente (`agente_giri_uguali`, `agente_consegna_dopo_giri`; contrari: la prima tappa, un rosso in meno, test verdi)"),
    ("prova_partenza_gioco.py", [], "il contratto e la partenza dell'agente dei giochi (19/10, #186): i quattro file di partenza generati dal codice passano i test e la prova di fumo per min = max e min < max («Inizia» o «N giocatori»; nome dal titolo, il segnaposto rifiutato alla consegna; contrari: titolo non accettato, manifesto che c'è già, giocatori non validi), l'analisi prima del codice dice min e max e toglie gli esempi fuori, gli errori nuovi del motore ({ esito, fase } e dopo senza esito, con cosa fare; contrari: esito con dopo, fase, dati) e il consiglio della prova di fumo, il contratto (g.stato() esatto senza vincitore, «Inizia» con min < max, turni, il caso, sezioni in ordine, urllib.parse sì), un prompt per tipo con i caratteri e la regola contro le istruzioni nei dati, nel servizio la partenza con min e max e gli strumenti del gioco senza esegui_python né scarica_esempio (contrari: senza analisi, un'estensione Python)"),
    ("prova_porte_consegna.py", [], "le porte oneste della consegna dell'agente (19/10, #180, con le due revisioni della PR #183): un esito fuori dall'enum («completato», vuoto) è un errore con l'elenco, anche per gli strumenti grafo_* della ricerca (`agente_esito_non_valido`; contrari: «Fatto», i tool della voce, «mancano_dati» e «impossibile»); una passata senza chiamate non è una consegna (`agente_prosa_non_consegna`, contata solo dove prima era una consegna): il fatto, poi la consegna decisa dal codice con gli esempi verdi o, senza esempi, con i test rifatti verdi, «limite» o tappa dopo tre di fila (contrari: esempi rossi, il controllo che non va, i test tolti, la consegna vera); la consegna rossa dopo l'ultimo rimando o l'ultimo rifiuto non è «fatto» (`agente_consegna_rossa_tappa`: «limite» fuori, tappa in uno sviluppo; i contatori ripartono a ogni giro dopo una tappa e restano dopo una domanda); la riproduzione solo con un fallimento di comportamento (`agente_riproduzione_asserzione`: ImportError e nomi mancanti nati nel test no; asserzione, errore mentre gira e il ReferenceError nato in logica.js sì); esegui_test rosso col controllo della consegna (file della scheda, nome preso); accettazione.test.js in sola lettura nella correzione di un gioco (contrario: la modifica)"),
    ("prova_esito_giochi.py", [], "l'esito dei giochi e gli esempi del tris (20/10, #197): contratto, progettista dei test, capacità, vincolo della correzione e partenza senza «esito di ogni mossa», il contesto della mossa (tocca, turno, giocatori) spiegato e misurato sul motore; senza turni i punti di chi non si sa non vanno più al Giocatore 1 (contrari: voce, un giocatore, turni); l'avviso della prova di fumo sull'esito a ogni mossa (`gioco_esito_ogni_mossa` nel ciclo, una volta; contrari: il tris giusto, le porte, la partenza, la soglia); gli esempi veri di L1 e L5 filtrati con il conto per causa (testo fuori dalla richiesta, «esito» senza punti alla prima mossa, più di 7 mosse, contraddetti) e giocati sul tris giusto; tutti tolti → `accettazione_esempi_tutti_tolti` (contrari: un testo della richiesta, «esito» con i punti, senza la richiesta, uno tenuto)"),
    ("prova_apri_gioco_tappa.py", [], "apriGioco c'è già, la tappa consegnabile, il segnaposto (20/10, #192): la frase «apriGioco e creaCaso ci sono già» nel contratto del gioco, nei vincoli della correzione e nel rimando della riproduzione (contrari: l'estensione, il programma); un apriGioco o un creaCaso scritto in un *.test.js di un gioco ha il fatto del motore finto in esegui_test (`agente_motore_finto`; contrari: chiamate, commenti, sola lettura, un lavoro che non è un gioco); alla tappa gli esempi verdi o la riproduzione «riprodotto» con i test verdi chiudono «fatto» (`agente_consegna_alla_tappa`, a voce e nell'annuncio dello sviluppo; contrari: i test verdi senza controllo indipendente, un test rosso, gli esempi rossi, la correzione senza test, con il rimando che resta); scrivi_file e modifica_file rifiutano il segnaposto della compattazione (`agente_segnaposto`; contrari: le parentesi quadre, la scrittura vera)"),
    ("prova_revisore.py", [], "il revisore a contesto pulito nel ciclo dell'agente (20/10, #190): il menu ridotto test_sbagliato / codice_sbagliato / consegna con la domanda (contrario: il menu del banco), i fallimenti divisi fra esempi di accettazione e test dell'agente, l'esempio tolto con il resto del file intatto; alla consegna, al tetto e alla tappa l'esempio rosso giudicato sbagliato tolto (`agente_revisore_esempio_tolto`, nel rapporto e sulla scheda di revisione) e quello giusto che resta con il fatto all'agente; la tappa con i test rossi (anche la consegna rossa e i giri uguali) e lo stesso errore tre volte di fila; «consegna» senza lo stato consegnabile ignorata; contrari: test verdi, una volta per giro, la voce che parla, spento, l'ombra senza effetti sull'agente (anche sul tempo del giro e sulle esecuzioni dei test), l'esempio mai cambiato dall'agente; dalla revisione della PR #202 una passata per gli esempi rossi del momento, l'esempio tolto che non è un test tolto, con «consegna» l'esempio resta, il nome in sola lettura dopo l'ultimo"),
    ("prova_strumenti_onesti.py", [], "gli strumenti onesti dell'agente (19/10, #185): lo stato già visto della cartella o del file nel risultato di scrivi_file e modifica_file, con l'esito dei test di allora (`agente_stato_gia_visto`; contrari: gli stati nuovi, la cache dei prefissi); l'uscita troncata detta e non eseguita (`agente_uscita_troncata`: argomenti rotti, finish_reason «length» di vLLM, done_reason di Ollama, la passata senza chiamate, thinking_token_budget che cade nel log; contrari: gli argomenti mancanti veri, la chiamata intera); esegui_test invariato non rieseguito (`agente_test_invariati`; contrari: un file cambiato, un altro file di test, l'esecuzione scaduta); letture contate per file e contenuto, con riga e da_carattere (`agente_rilettura`; contrari: i pezzi nuovi, il file cambiato); modifica_file con le righe vere, le righe delle occorrenze, la modifica nulla e l'inversa rifiutate (`agente_modifica_nulla`, `agente_modifica_inversa`; contrario: una modifica diversa); lo strumento sconosciuto con l'elenco e le chiamate dopo la consegna con la risposta (`agente_strumento_sconosciuto`, `agente_dopo_consegna`; contrario: la consegna da sola); i casi delle tre revisioni della PR #187 (A–N, R4, R6), permanenti, e dalla quarta (#191) V1, il budget del ragionamento, e F, la prosa e il giro a vuoto che non azzerano le troncate; le stesse regole nel ciclo della ricerca (21/10, #189: lo strumento sconosciuto, la consegna seguita da web_leggi, la chiamata e la consegna a metà, la relazione fermata a max_tokens; il solo ragionamento fermato, la relazione tagliata nel parziale del limite, il giro a vuoto che azzera, la chiamata buona con una rotta che non è «di fila», la storia ben formata nei corpi, la consegna tagliata col testo nel parziale, la consegna buona prima di una rotta, a voce la ricerca fermata senza «cartella Lavori» e con la relazione incompleta offerta; contrari: l'argomento davvero mancante, la lettura prima della consegna, la relazione intera)"),
    ("prova_revisione_onesta.py", [], "revisione onesta e tappe (11/10, calliope/requisiti.py; il caso vero del gioco di Halloween consegnato senza voce né musica e rivisto con «tutto sembra in ordine»): all'analisi i requisiti della specifica dal modello dell'agente, ciò che oggi non si può fare e la proposta delle tappe (contrari: richiesta semplice, tutti nel nucleo, «no, tutto insieme», modello guasto); alla consegna e alla revisione il confronto requisito per requisito con i file (manca, in parte con la nota, tappa dopo, non si può), la prova di fumo detta come test di avvio, «attivarla così com'è o continuare», «continua» → completa o tappa 2 (contrari: tutto fatto, confronto non riuscito o non allineato, nota che parla all'assistente, «continua» al collaudo, programma); scheda, vista e disco"),
    ("prova_specifica_viva.py", [], "la specifica viva (12/10, calliope/requisiti.py; il caso vero del gioco delle porte modificato tre volte, una capita al contrario): la modifica è un'operazione sui requisiti (aggiungi, sostituisci, togli, anticipa) dal modello dell'agente, la specifica rigenerata senza code né contraddizioni, a voce solo il cambiamento, tappe e vincoli aggiornati, lo storico a parte, il confronto senza falsi allarmi; «correggi» con un comportamento diverso, «Cosa non va?» prima di far ripartire l'agente, il «sì» a «Lo faccio correggere?» senza il modello (contrari: c'era già, vaga, modello guasto o in ritardo, requisiti spenti); la prima proposta lunga in breve; le scelte al posto della persona; un gioco confermato dalla politica che si propone comunque, il file della persona nei lavori dopo, il gioco in modifica senza il flag, i requisiti con l'estensione attivata, l'analisi del gioco"),
    ("prova_voce_onesta.py", [], "voce onesta e meno parole nella modalità sviluppo (12/10, casi veri della DGX del 06–12/10 con nomi di fantasia): il tipo di un collaudo dal risultato (risposta, «non trovato», errore dell'estensione, fermata) e la frase con le parole dell'estensione, mai «errore di rete» inventato né «Lo faccio correggere?» per un errore voluto; il conteggio delle prove senza «15 riuscite» con sette «non trovato»; la revisione che dice il collaudo saltato; l'annuncio breve con cosa doveva cambiare; la riga del fuori tema una volta per fase; sviluppo_chiedi con la correzione detta per prima; le città dette negli argomenti del collaudo e il nome del proprio sviluppo all'approvazione senza la domanda in più (contrari: valore solo nel dato, un'altra persona, rimuovi, sospeso)"),
    ("prova_flusso_ripresa.py", [], "comandi del flusso e ripresa nella modalità sviluppo (12/10, lavoro 3; casi veri della DGX del 06–12/10 con nomi di fantasia): «chiudi tutti gli sviluppi» per intero con una domanda sola (anche da sviluppo_chiedi), un'azione che non si disfa non parte da una storpiatura («Am nulla il lavoro.», «Chiudin.»: la domanda), «ricominciamo» sospende lo sviluppo aperto, estensione_gestisci «modifica» inventato e «modifica l'estensione X» senza modifica non creano un'estensione nuova, «RINOMINA» all'analisi; A4: «torniamo all'analisi» e la modifica non fermano niente prima del «sì», «lascia com'era» torna al collaudo o al lavoro di prima, al «sì» il nuovo parte dai file del giro; A5: la tappa scaduta messa da parte, la ripresa con il lavoro, «rifallo» dai file del giro (anche dopo un riavvio); la ripresa in una domanda; M7: il programma consegnato si riapre; uscire con il lavoro in corso o fermo a una domanda lo sospende; contrari per ognuno"),
    ("prova_fasi_agente.py", [], "il flusso dell'agente a fasi, parte 1 (12/10 sera): la correzione parte da un test che fallisce (un test nuovo o cambiato rieseguito sulla versione di prima; contrari: codice uguale, nessun test, test che passa anche prima, nessun file di partenza), il ciclo con un cliente finto (rimandata una volta, poi segnata), la frase «non sono riuscita a riprodurre il problema»; i test del disegno dei giochi (apriGioco: il difetto del 12/10 dell'esito annidato preso, il gioco giusto passa; tocchi, errori, disabilitati, seme, comandi; la riproduzione di un gioco); esegui_js nel container di Node e i file prova_*.js fuori dal codice; al ricontrollo i test due volte: un test che cambia esito torna con «fissa il seme» (contrari: sempre verdi, sempre rossi, creaCaso e apriGioco con il seme)"),
    ("prova_fasi_agente_2.py", [], "il flusso dell'agente a fasi, parte 2 (13/10, banco della temperatura): la spinta a consegnare dopo il primo esegui_test tutto verde con i file chiesti, una volta (contrari: test rossi, un solo file di test, estensione senza manifesto o prima del piano); l'avviso di chiusura con i test verdi dice di consegnare (contrari: file cambiato dopo, la tappa); senza esempi di accettazione mai consegna d'ufficio; l'analisi prima del codice: esempi dato → risultato in forma chiusa, test_accettazione.py scritto dal codice e in sola lettura (verde sulla giusta, rosso sullo scheletro e sull'esempio sbagliato), al più due domande prima di cominciare e la risposta alla passata (contrari: correzione, nessuna persona, programma o gioco fuori da uno sviluppo, modello guasto, spento), «da guardare tu» e «provato da un esempio» alla revisione; un file lungo riscritto intero per poche righe ha la nota per modifica_file (contrari); al tetto, con gli esempi di accettazione e i test rieseguiti tutti verdi, il lavoro si chiude «fatto» con il riassunto del codice e la regola agente_consegna_al_tetto (13/10 sera; contrari: esempi rossi, senza esempi, un test dell'agente rosso, la tappa, il controllo della consegna che non passa) e la frase a voce lo dice; banco del 14/10 sera: esempi contro la richiesta (valori non nominati, conto che non torna, parole che ripetono i dati), il manifesto rifiutato detto subito, «avanti» fuori dall'esito; gli esempi per i programmi a riga di comando (17/10, #10): l'interfaccia dichiarata dall'analisi (file, linguaggio), esempi con argomenti e stdin verdi sul programma giusto e rossi sullo scheletro e sul controllo dimenticato, in Python e in JavaScript, il nome controllato alla consegna una volta, al tetto «fatto» con gli esempi verdi, la frase «nessun esempio indipendente li conferma» senza esempi, il ragionamento della passata solo con agenti_accettazione_ragionamento (contrari: programma su file, C#, JavaScript senza Node, nomi non validi, valore non detto, conto che non torna, risultato uguale a un dato, fuori da uno sviluppo di serie niente passata); revisione della PR #141: soli esempi d'errore senza esempi (massimo.py con sys.exit(1) o raise), l'eccezione nell'uscita in Python come in JavaScript, stdin e uscita TextIOWrapper, in JavaScript il tempo scaduto rosso, il nome una volta anche dopo una sospensione; il numero solo dallo stdout e con il codice null una corsa finita bene (int di \"3.5\", «expected 2, got 1», lo stack di Node rossi), la sola parola a codice null non è un risultato"),
    ("prova_giro_porte.py", [], "il giro vero della DGX del 12/10 (il gioco delle porte magiche, nomi di fantasia): una modifica dello stesso gioco non è «un'altra estensione» («un giocatore» non è una cosa nuova; contrari: un altro gioco, un programma); una modifica o una correzione che non dice niente di concreto chiede cosa (una volta; contrari: numeri, modifiche vere, il «sì» a «Lo faccio correggere?»); sviluppo_chiedi senza le risposte di una versione di prima, richiesta di nuovo se ridice la risposta di un'altra domanda, e una segnalazione che va a sviluppo_correggi; la seconda strada della revisione con il suo messaggio, la spinta_sviluppo su una promessa senza tool e il testo taciuto prima della frase del tool (contrari: nessuna domanda, una risposta che non promette, rete spenta); i testi della voce (la prova sullo schermo, «da 2 a 4 giocatori», «un comando», il fuori tema); la seconda correzione sa che la prima non ha funzionato; l'avviso di fine giro in uno sviluppo"),
    ("prova_diagnosi_collaudi.py", [], "diagnosi dei collaudi della modalità sviluppo (08/10 notte): confronto automatico tra collaudi riusciti e falliti verso lo stesso host e percorso (parametri com'erano e decodificati, metodo, corpo, stato, dimensione, chiavi JSON; anche un «non ho trovato» con la risposta più povera; versioni di prima) con i contrari e il tetto; risposte vere dei collaudi come esempi_veri/ per i test dell'agente (solo GET verso host del manifesto, senza dati di casa né riservati, troncate, al più due per esecuzione) nei vincoli di sviluppo_correggi e dell'analisi; CalliopeFinta che risponde con la risposta vera per lo stesso indirizzo (il test che «trova» la città fallisce) e i contrari"),
    ("prova_sonde.py", [], "sonde dell'agente e ricollaudo alla consegna (08/10 notte, § 9 di docs/ricerche/2026-10-08-sonde-agente.md): host noti (approvato, collaudi con risposta, chiedi_permesso; mai rifiuti della porta, candidata, rete.pubblica, reindirizzamenti), vocabolario del caso e contrari del giro 5, come l'ha letto il server, quote per lavoro, passata e giorno, risposta in busta; ricollaudo con il docker finto (la versione del giro 3 rimandata all'agente con la traccia in busta, una volta per lavoro, la giusta che va, frase «ora vanno», manifesto ristretto, nessuna conferma, quando non parte); il giro dell'agente con sonda_rete al posto di scarica_esempio; busta per traccia, confronto, esempi veri e scarica_esempio; nomi pubblici di casa in RetePubblica"),
    ("prova_scheda_sviluppo.py", [], "scheda dello sviluppo e del lavoro in diretta (08/10, il giro vero della DGX): conti dei token per lavoro e dello sviluppo intero (155 708), correzione N, id ripetuti dopo un riavvio, tetti per giro cumulativi e tempo che continua, dati della vista, scheda agli schermi personali di chi sviluppa e mai agli altri, uscita dalla vista a sviluppo chiuso o sospeso, finestra del flusso nella cronologia e «Scarica il registro»"),
    ("prova_sviluppo.py", [], "modalità sviluppo (08/10): estensioni e programmi come iter a fasi (analisi, sviluppo e test, collaudo, revisione, attivazione), su disco; collaudo della candidata prima dell'approvazione nel docker finto, revisione con le differenze, attivazione con la sfida e chiusura; ritorno all'analisi; sviluppi nuovi bloccati; dati del turno e riga del fuori tema; sospensione dopo 30 minuti, ripresa, promemoria del giorno; programma → estensione; passi interni senza la domanda della politica e i contrari"),
    # ~8 s: FakeOllama, hub e server degli schermi veri su 127.0.0.1, satellite e PC finti
    ("prova_markdown.py", [], "Markdown dei testi dell'agente (07/10): blocchi, righe, voce, conversioni in PDF e Word veri e da blocchi, testi ostili (script, javascript:, tabelle enormi, annidamenti, enfasi senza chiusura) in poco tempo; risultato.md, annuncio, scheda del documento con «Scarica», risultato al portatile con «Lo apro?» o sul server; «Scarica» solo per lo schermo personale del proprietario, mai zona grigia né stanza, gettone che scade, Content-Disposition e CSP sandbox; «fammene un PDF»"),
    ("prova_conferme.py", [], "conferme (04/10): «sì» breve di chi amministra, proposta valida 3 turni, frase di sfida"),
    ("prova_valore.py", [], "sicurezza per valore (08/10, fasi 2 e 3): richiesta ripetuta = sì per le pericolose (caso del 07/10 18:52), memoria dell'intento e i contrari, una domanda una volta, politica per valore in ombra nel registro, tabelle di argomenti ed effetti, etichette e matrice, gli 8 attacchi nuovi e il banco di prova_politica con l'interruttore acceso, rigioco dei casi veri del 07/10; casi veri della sera del 09/10 (la taverna: «spegnessi», il «sì» breve per una luce, la domanda con i nomi della casa; «Meteoborgo» detta prima; sviluppo_apri col nome inventato; chiamata identica nella stessa risposta) e i contrari; incongruenze dell'analisi delle regole (sfida della classe come pavimento, rinomina detta, città della casa, il «sì» E3–E4 giudicato dalla nuova, il motivo vero, l'ombra con la decisione finale)"),
    ("prova_valore_dettato.py", [], "le parole dettate a voce non vengono da una pagina né dalla stanza (18/10, issue #169, caso vero della DGX dell'estensione «Posta»): il compito riformulato a elenco puntato si esegue, i numeri dell'elenco non sono distintivi, la fonte della domanda è quella delle parole che fanno chiedere, il blocco della stanza senza la frase del turno; contrari che chiedono ancora: pagina (nome, numero nell'elenco, civico), documento dell'archivio, riga della stanza di un'altra voce, foto con e senza testo"),
    ("prova_intento_no.py", [], "il «no» alla proposta e il «sì» che passa ad altro (09/10, caso vero della DGX dell'08/10 sera con nomi di fantasia): «No, non mi interessa…» chiude la proposta e la sfida, rifiuto nei dati del turno e nella politica fino alla richiesta nuova; «Sì, però ascolta…» e «Sì, non preoccuparti…» non confermano la domanda della politica; contrari («no, aspetta, registralo», «no no, va bene, fallo», un altro bersaglio, la conversazione nuova, «Sì, registralo pure», la domanda del tool che chiede un dato)"),
    ("prova_stato_dialogo.py", [], "lo stato del dialogo, passo 1 in ombra (10/10, calliope/stato_dialogo.py e risposte.py): consenso del progetto, priorità, blocco dello stato; proposta_rispondi(si) uguale alla chiamata diretta e allo spento (stesse esecuzioni e regole della politica), gli altri esiti non fanno niente; difese (prima passata, prima di un dato, id, domande con un dato), storia pulita; due proposte, proposta + sfida, sviluppo, cancello dei minori, conversazione chiusa, frasi decise prima di Brain (caso vero del 09/10 20:39); banco nuovo: il dato che «risponde» alla proposta, 27 attacchi a zero"),
    ("prova_storpiature.py", [], "le forme chiuse brevi storpiate da Whisper (10/10, casi veri della DGX): «ricominciamo» storpiato e con il nome storpiato davanti («Calliope ricominciava.», «E lì appena ricominciamo.») è la conversazione nuova; «Annullahi.», «Am nulla il lavoro.», «Chiudin.», «Spendilo.», «Alla ora, ok.» un dato del turno (e «annulla» da solo «no» nella corsia veloce); la rete della politica per i lavori dell'agente che partono da una frase breve senza le loro parole (politica_avvio_non_chiesto) e il «sì» che li esegue; contrari («ricomincia da capo il programma», «annulla la sveglia delle 7», «chiudi la finestra», «spendi meno», «vai avanti», «riprova»…)"),
    ("prova_conserva.py", [], "conservazione dei dati (12/10, decisione 0028 T1; dal 16/10 decisione 0031, i minori come gli adulti, calliope/conserva.py): il solo posto che decide (adulto e minore sì; ospite e zona grigia no; nel dubbio con un minore il testo sì e la voce no; la voce solo sopra soglia, senza compagnia e con il consenso, chi amministra sì finché non dice no, il minore solo col sì di un tutore), registro dei turni con le parole del minore e senza per i contrari, voce in μ-law che si rilegge e i suoi contrari (minore senza il sì del tutore, ospite, adulto senza consenso, frase breve, compagnia, scritta, ignorata, incerta), consenso e revoca nel profilo, rotazione (giorni, persone, tetto), il registro di prima ripulito una volta senza toccare il minore, svuota una persona e tutto, eventi del minore su disco e ripresi, degli ospiti mai, parole di un turno incerto solo in memoria, dati_del_turno, il tool dati_conservati con domanda e «sì», il tutore per la voce del minore e i rifiuti, il «sì» breve di un tutore che non amministra (16/10, #108; dal 16/10, #114, anche dal ciclo vero e da ToolRegistry.call), la maggiore età (il sì da adulta dal tool), da terminale anche il minore; l'archivio delle conversazioni allineato (adulto e minore su disco e ritrovati dopo un riavvio, ospite e turno incerto no, sessione in memoria, rotazione, 60 giorni, svuota)"),
    ("prova_conserva_valutazione.py", [], "la valutazione (18/10, #173, decisione 0032, conserva_valutazione_fino): la data con e senza virgolette, oggi compreso, scritta male rifiutata; un turno di un ospite e della zona grigia con le parole e il segno della valutazione, una riga di altri; l'audio dell'ospite in voce/_valutazione/ospiti/, della zona grigia e dell'adulto senza consenso sotto il suo id, quello di sempre al suo posto; contrari sempre (frase di sfida, codice, scritto, ignorata, conserva_voce: false); contrari interruttore vuoto, data passata e storta come oggi; la scadenza nel log una volta, la rotazione (giorni, profilo tolto), svuota di una persona e di tutto, la revoca; la stanza dal giro vero (riga dell'ospite nella tenuta che la ricerca non vede, audio nel banco senza stanza_audio_banco_giorni, pausa no, «dimentica», --persona, contrari spenta e passata); l'archivio (ospite su disco con ospite = 2, nessuna ricerca dopo un riavvio, pulizia dei non conservati, svuota, contrario spento); stato, avvio e cruscotto"),
    ("prova_mulaw.py", [], "G.711 μ-law vero (14/10 sera, calliope/conserva.py): codifica uguale al riferimento su tutti i 65 536 valori, decodifica su tutti i 256 byte, un lettore standard (parser scritto nella prova e libsndfile se c'è) rilegge tono e voce di Piper con SNR alto e il formato di prima storto (contrario), il segno del formato e leggi_wav di nuovo e vecchio, audio degli avvisi; --converti-audio: voce, banco della stanza e avvisi del cassetto convertiti (permessi e data tenuti), contrari non toccati (già nuovi, PCM, rotto, audio di una persona nel cassetto), idempotente, interrotta a metà e rilanciata, temporaneo di un crollo tolto, da terminale solo conteggi"),
    ("prova_reti_scatti.py", [], "il rapporto degli scatti delle reti del modello (15/10, E11, calliope/reti_scatti.py, calliope stato --reti): inventario rete → regole con ogni regola scritta nel codice e ogni nome di _net in RETI, scatti e risposte osservate per profilo, accesa da reti_spente del turno o dedotta dal profilo, «tutte», la data d'ingresso nel codice, ultima volta, esito dopo lo scatto (ripiego, giri esauriti, ripetuta e interrotta entro 90 s, con i contrari), aiuto usato, MAI SCATTATA e spenta, spente dal profilo e nel locale, TurnLog con reti_spente, testo e JSON"),
    ("prova_scelta_tool.py", [], "la scelta dei tool come metrica (12/10, calliope/scelta_tool.py): nomi inventati corretti o senza un tool vicino con cosa si voleva, regole dei turni di prima, correzioni riuscite ed esaurite, ripieghi, richieste ripetute della stessa persona entro 90 s e i contrari (altra persona, tardi, altra frase, senza parole), indice e avviso con il contrario, la sezione di calliope stato --turni (testo e JSON), Brain che ricorda il nome inventato"),
    ("prova_attrito.py", [], "attrito della sicurezza (08/10, fase 1 della sicurezza per valore): domande ogni 100 turni per tipo, ripetute, poi eseguite, «già detto», avviso D6, politica per valore in ombra, calliope stato --turni"),
    ("prova_si_breve.py", [], "il «sì» breve per le azioni importanti in ombra (15/10, roadmap 2.6, calliope/si_breve.py): la riga per ogni azione importante o conferma eseguita dal registro dei tool (sì breve compatibile di chi amministra, sì breve di un familiare, sfida superata anche da Brain, voce piena) con i rischi (compagnia, voci sconosciute, voce incerta, senza nome); contrari: E1 chiesta, lettura, chiamata rifiutata, righe di un'altra risposta, misura rotta che non ferma il tool; riassunto, tempo della sfida accoppiata sullo stesso satellite (contrari: altro satellite, oltre 120 s), costo dell'alternativa, calliope stato --turni in testo e JSON"),
    ("prova_documento_proprio.py", [], "aprire il documento appena scritto con una foto di mezzo (07/10, giro 9, caso della DGX): documento proprio senza conferma a voce e i contrari, consenso ripetendo la richiesta e i contrari, un solo file e il numero 2, numero che non c'è detto al modello, sfida superata con il tool fallito, allegato_leggi fallito che non contamina"),
    ("prova_voci_famiglia.py", [], "voci di famiglia (07/10): margine tra primo e secondo profilo, chi amministra con un minore vicino, la frase che chiede chi parla, conferma breve con un'altra voce più vicina, i quattro casi veri con impronte sintetiche; continuità delle frasi cortissime (08/10) con i contrari; il proprietario del telefono (09/10, voce_proprietario): frasi incerte col minore restano sue, con i contrari (minore sicuro, satellite di stanza, finestra scaduta, compagnia)"),
    ("prova_impronte_satellite.py", [], "impronte della voce per satellite (15/10, calliope/impronte_satellite.py): apprendimento solo dalle frasi sicure (contrari: zona grigia, breve, voce corta, margine stretto, compagnia, incerta, minore vicino, continuità), seme dopo 3 frasi, deriva dall'arruolamento e dal seme, ripiego sul canale; spento come prima; ombra (decide quella di oggi, nel registro con e senza) e attivo (il caso del 15/10 in auto riconosciuto); simmetria col minore e protezioni sui punteggi nuovi; i casi del 07/10 di prova_voci_famiglia uguali in ombra e attivo; tenuta (speakers.json, modello diverso, nuova registrazione, rinomina, svuota dal processo e da terminale con la copia); conoscenti (apprendimento, riconoscimento, file, promozione e ritorno, dimentica); stato --turni; dal 18/10 (issue #159) gli scambi divisi fra base sicura e base incerta (contrario: contro una decisione dalla voce resta sicuro)"),
    ("prova_minori.py", [], "minori (05/10): fasce, preset e permessi nel codice, orari, voce incerta, compiti guidati come sola regola nei dati del turno anche con «fammi tu il compito» e calcola col risultato (28/10, #279), avvisi ai tutori, guardiano finto, registrazione con la sfida, privacy"),
    ("prova_studio_piano.py", [], "lo Studio, dati e piano a giorni a secco (29/10, #280, decisione 0035, calliope/studio/): schema che si crea, si riapre e con una versione più nuova si legge senza scrivere; piano deterministico coi materiali di fantasia (verifica domani, fra una settimana e fra un mese, nessun giorno libero, orari di riposo, pagine più dei giorni, data spostata, oggi e passata, giorni fatti, «non ce la faccio oggi», giorni senza scuola, due verifiche negli stessi giorni), tappe e previsione dopo due misure; permessi di minore, tutore, adulto, chi amministra, ospite e conoscente; tenuta a 60 giorni dalla data con l'orologio finto, archiviata per sempre, «dimentica» e svuota; interruttore spento, ombra e attivo"),
    ("prova_studio_pagine.py", [], "le pagine dei materiali dello Studio a secco (29/10, #281, passo 4.2): bordi sulle foto di fantasia (storte e in ombra trovate, pulite intere, quelli del telefono confermati o scartati, impossibili mai), bordi.js uguale al Python con node, raddrizzamento a 1600 e nitidezza, PDF divisi (troppe pagine, malformato, enorme, cifrato), file ostili e link fuori; sul server vero /api/studio/pagina e /api/studio/verifiche (proprietario, tutore, altro adulto, chi amministra, ospite, conoscente, stanza, orari, limiti, spento e ombra), niente nella conversazione; tenuta, dimentica, svuota e togli che tolgono i file"),
    ("prova_studio_banco.py", [], "il banco dello Studio a secco (28/10, #293, revisione della PR #302): la guardia che vede un lavoro dell'agente vivo (in_corso.json col .bak, fermo da più di 15 minuti o con i file in una sottocartella) e i contrari, --senza-guardia rifiutato con la Calliope vera attiva, harness.json uguale alle costanti del banco, pagina scritta due volte, segni della lettura, controllo delle pagine con le radici, verità dei materiali coerente"),
    ("prova_studio_tool.py", [], "i tool dello Studio a secco (30/10, #284, passo 4.5): studio e studio_pagina_leggi con classi, effetti e livelli; proprietario, tutore (anche con «per»), un altro adulto, ospite, zona grigia e minore incerto; «archivia» che chiede; la busta «foto» del testo e dei titoli, mai nel tool fidato; i tocchi nuovi (azione fissa, bersaglio, titolo in busta, stato d'animo mai nella storia); la vista aperta nei dati del turno; le due domande in memoria; piano_non_aggiornato, la frase senza vLLM, «dimentica» che dice lo Studio solo se l'ha tolto; un minore coi compiti guidati"),
    ("prova_studio_argomenti.py", [], "gli argomenti dello Studio a secco (30/10, #283, passo 4.4) con un vLLM finto: l'harness esatto di harness.json (schema guidato, niente tool, una busta coi riferimenti P1…), il controllo delle pagine citate (giusto, pagina sbagliata, inventato, riferimento che non c'è, radice), la forma del titolo, le pagine ostili delle tre verifiche (argomento proposto con l'avviso, fuori dalla conferma e dal piano), il giro del lettore con la firma e la seconda estrazione, la conferma (tieni, togli, rinomina, unisci, aggiungi, conferma) e il piano coi soli tenuti, i permessi, gli interruttori, la guardia, gli errori del server, l'endpoint /api/studio/argomenti e la pagina"),
    ("prova_studio_lettura.py", [], "la lettura delle pagine dello Studio a secco (30/10, #282, passo 4.3) con un vLLM finto: l'harness esatto di harness.json (prompt, parametri, una foto per richiesta a 1600), pagina scritta due volte, length rifatto e poi illeggibile, capovolta girata e riletta, due pagine divise in due righe e due file, numero strano, istruzioni, controlla i numeri, PDF con testo senza modello e PDF immagine con l'OCR, la guardia (lavoro dell'agente nel processo e in in_corso.json, vLLM occupato o in pausa, lavoro che parte durante lo stream, la voce con l'arbitro), la ripresa dopo un riavvio, la pagina tolta durante la lettura, il thread, spento/ombra/attivo, permessi e ogni file con la sua riga"),
    ("prova_controlli_regressione.py", [], "i controlli del banco di regressione a secco (17/10, #70): il ruolo dato come nome (domande e «ma Papà» errori, il rifiuto detto no) e la frase storpiata «Calliope di Michisono.» (il nome o una domanda di chiarimento, non la ricerca)"),
    ("prova_eta_utenti.py", [], "età e compleanni dai profili (07/10, DGX): data di oggi come nascita rifiutata, persona=io o un nome, giorni contati dal programma, privacy (chi amministra e i tutori), impronta della voce in elenca_utenti, rubrica distinta, tool *_cerca con argomenti obbligatori, parole di un ospite nel registro; la propria data di nascita nel profilo con ricorda e la data dai ricordi in data_calcola (07/10 pomeriggio)"),
    # ~25 s: la pagina degli schermi e del telefono in Edge o Chromium senza finestra
    ("prova_vista_sviluppo_pagina.py", [], "vista dello sviluppo e lavoro in diretta nella pagina vera (08/10): fasi, due colonne, flusso che si accumula senza buchi né doppioni anche dopo una riconnessione, scorrimento e «In fondo», schermo intero sul computer, giro 2 e correzione, comandi a tocco innocui, uscita dalla vista, telefono in una colonna, nessun errore JS né CSP"),
    ("prova_minori_pericolo.py", [], "minore in pericolo con la frase spezzata (06/10, e2e): pezzi uniti per il guardiano, protezione senza barge-in con la sola voce e ripetuta se il nome la interrompe, avviso non ripetuto per lo stesso episodio, con i contrari"),
    ("prova_compagnia.py", [], "modalità compagnia (09/10): più voci vicino allo stesso satellite (profilo recente, gruppi tra ospiti, due profili) con i contrari (voce variabile, altro microfono, frasi brevi, finestra scaduta, altro satellite, stesso ospite, spenta), i due episodi veri della DGX in numeri, niente frase breve né continuità, voce non sicura per i due cancelli e l'avviso che lo dice, azioni con la voce nella frase, nome a ogni frase con una voce sconosciuta (il nome passa sempre), famiglia tutta riconosciuta, ombra senza effetti; giudizio «rivolta a Calliope» finto in ombra e acceso (silenzio, protezione sempre, guasto = rivolta, nessun tool, storia ripulita); calliope stato --turni; impronta non aggiornata in compagnia (12/10)"),
    ("prova_console_minori.py", [], "parole dei minori nel terminale e nel journal come quelle degli adulti (16/10, decisione 0031; dal 12/10 sera al 16/10 nascoste, conserva.console_riservata): la frase e la risposta in chiaro anche nel dubbio tra un adulto e un minore, nelle reti di Brain e negli argomenti dei tool; minori.parla_minore per la frase dopo il tool; contrario l'ospite («(una frase di un ospite)», «…»)"),
    ("prova_stanza.py", [], "passo 1 della conversazione di stanza (13/10, decisione 0029): segmentatore del satellite e del telefono (silenzio, tetto corto, min_speech_ms, voce di Calliope, legame col comando), Whisper con la precedenza turno > recupero > stanza, server vero con satelliti finti (protocollo 3, righe con chi parla e minore, niente doppio Whisper per il turno, niente segmenti mentre si parla a Calliope, recupero all'interpellazione, copertura), registro in memoria, presenze e cambi di stanza, pausa, ospiti e ripresa, «dimentica», misure senza parole, sezione di stato --turni; contrari: versione 2, satellite fuori elenco, stanza spenta"),
    ("prova_stanza_voce.py", [], "conversazione di stanza in tempo reale (13/10, passo 1): satellite Python vero (rubinetto senza perdere frame dei comandi, riga senza il nome, segmento legato al turno, half-duplex, ospiti) e telefono nel browser vero (righe senza byte ai comandi, segno, interruttore, banda)"),
    ("prova_stanza_eco.py", [], "passo 5 della conversazione di stanza (14/10, decisione 0029): ascolto durante la voce di Calliope con il filtro dell'eco (stanza/eco.py, regola eco_stanza): sola eco esatta e storpiata scartata, persona sopra tenuta, misto ripulito, i contrari (parola ripetuta nella sua frase, «grazie», «Torino?» fuori tempo, frase citata dopo), Segmentatore del satellite e del telefono (Node) con durante_voce, voce_ora, server vero con le frasi mandate e il suona, cancello dell'eco sul saluto, spento come prima, pausa per ospiti, barge-in legato al turno, misure senza parole e la riga di stato --turni"),
    ("prova_compagnia_passo0.py", [], "passo 0 della conversazione di stanza (13/10, decisione 0029, caso vero del 12/10 in auto): in compagnia senza il nome niente azioni (letture sì, il «sì» della stessa persona alla proposta sì, compagnia_azioni_col_nome), la conversazione anonima del satellite condivisa e non chiusa a ogni cambio di persona con chi ha detto cosa nei dati del turno (compagnia_anonima_continua), il rilevatore di pericolo che non vale sulle frasi giudicate non rivolte (pericolo_non_rivolta; dal 18/10, #29, solo col giudizio attivo, in ombra vale con pericolo_non_rivolta_ombra); contrari: una persona sola, col nome, voce sconosciuta di mezzo, conversazione di una persona, giudizio guasto, interruttori spenti; con eventi: attivo (15/10, issue #12) chi ha detto cosa dall'evento della frase nei dati del turno, contrario senza il nome"),
    ("prova_compagnia_stanza.py", [], "compagnia dai segmenti della stanza (18/10, issue #147, caso vero del 17/10 in cucina; revisioni della PR #161): ombra di serie (la voce non cambia, nel registro voce.compagnia_stanza, regole compagnia_da_stanza_ombra e _ombra_nome, la frase senza il nome passa), attiva (in compagnia con una voce sconosciuta, da_stanza, finestra chiusa, il nome passa), la regola rigida nella sola prova «profilo» (sconosciuta solo sotto 0,20 su tutti i profili di casa: il familiare non riconosciuto, la frase del turno non riconosciuta, la zona grigia e un altro profilo vicino no, il conoscente sì; i gruppi come sempre: l'amico del 09/10 dalla stanza conta), da_stanza solo se cambia l'effetto, solo verso la prudenza (l'assorbimento, niente continuità), i minori (minore registrato in casa, anche lontano e non riconosciuto, o cancello aperto: vale lo stato del turno; pericolo non spento dal «non rivolta» con la compagnia della sola stanza; contrari), lo stato del turno al momento come su main (adapt dopo osserva), il calcolo con la stanza tenuto da parte e il tempo con 80 segmenti, l'istante nel futuro con una seconda voce, le corsie, la stanza vera (l'impronta di chi parla una volta, il segno della zona grigia, mai nella riga), solo in memoria con la tenuta accesa, stato --turni; contrari: spenta, sotto speaker_min_voice_s, più vecchi della finestra, lo stesso ospite, durante la voce, compagnia spenta, dimentica"),
    ("prova_stanza_contesto.py", [], "passo 2 della conversazione di stanza (14/10, decisione 0029): il blocco della stanza nei dati del turno (righe in ordine con chi le ha dette, zona grigia, voce sconosciuta, rivolte a Calliope, righe di Calliope, in busta con la fonte stanza, senza la frase del turno; ultimi 45 s sempre anche oltre il tetto, il resto dalla più nuova senza buchi, niente oltre i minuti), la copertura all'interpellazione (recupero aspettato al più il tetto, nel_contesto, scartate, nota delle righe non trascritte), Brain (dopo la storia e prima della frase, mai nella storia, solo nome e lunghezza, la politica lo vede come dato: un bersaglio dalla stanza chiede, uno detto si esegue), il ciclo (numeri nel registro dei turni, la frase ignorata resta nella stanza con rivolta no, la risposta come riga di Calliope una volta), il giudizio rivolta con le righe della stanza, la sezione Stanza di stato --turni con e senza blocco; contrari: spento, in pausa, nessuna riga, dimentica, satellite fuori elenco, frase scritta"),
    ("prova_stanza_ricorda.py", [], "«ti ricordi…?» con la conversazione di stanza (14/10 notte, terzo caso della seconda prova in auto): parole simili a una lettera (le storpiature di Whisper, «crisima»/«cresima») e nome proprio nella ricerca, ricerca anticipata con due parole della domanda o il nome, prompt e descrizione (stanza prima di archivio e conversazioni), Brain cerca nella stanza dopo una ricerca vuota (stanza_dopo_ricerca_vuota), riapertura fino all'ultimo scambio; contrari: parola diversa, altra persona, parole corte, una parola su due, rete spenta, stanza_cerca già chiamato, archivio che trova, chiacchiere fitte col tetto"),
    ("prova_stanza_storpiata.py", [], "righe della stanza storpiate e domanda insistita (15/10, caso vero in auto col 26B): blocco, primo pezzo, pezzi dopo e prompt dicono di ricostruire con prudenza e che la correzione di chi parla vale subito (righe intatte); domanda che riprende le parole piene di prima dopo una risposta lunga: INSISTE_MSG nei dati del turno (regola domanda_insistita) e la spinta della ripetuta senza «una cosa nuova»; contrari: domanda d'altro, altra città, risposta breve, parole vuote, rete spenta, stessa domanda uguale; dal 16/10 (#134, chi parla da solo) la nota sulle sole righe della stanza, non sulla frase del turno (nome ripetuto o chiesto, mai sostituito), senza la formula «mi è sembrato di sentire», correzione per il resto della conversazione, la nota ferma nel prefisso con una voce e con due, la domanda insistita senza «sembrato», il conteggio del caso da_solo del banco su risposte finte"),
    ("prova_stanza_attesa.py", [], "il pezzo in attesa e il tetto alla riapertura (14/10 notte, dopo la seconda prova in auto): motore finto con la cache del prefisso di Ollama e una conversazione come quella dell'auto (righe fitte, due riaperture), token riletti alla domanda prima e dopo, prefisso scaldato uguale byte per byte alla richiesta dopo, ogni riga una volta e in ordine, la domanda mai in attesa (quiete), contrari: in risposta, in scadenza, sotto soglia, pausa, spento, dimentica; finestra della riapertura fino all'ultimo scambio; misure e configurazione"),
    ("prova_stanza_storia.py", [], "le righe della stanza nella storia in sola aggiunta (14/10 sera, stanza_contesto_in_storia, dopo la prova in auto): su 10 turni finti con righe fra un turno e l'altro il prefisso resta uguale e si rileggono solo le righe nuove (contatore della guardia della cache, --misura per la tabella prima/dopo), ogni riga una volta in ordine e davanti alla frase del suo turno, in busta; mai nella storia salvata, in esporta né nell'archivio; la politica le vede nei turni dopo (un bersaglio da lì chiede); contrari: spento, pausa per ospiti, dimentica, blocco intero con l'interruttore spento, turno tolto dalla storia, tetto con potatura a blocchi e prefisso scaldato; misure; con eventi: attivo (15/10, issue #12) gli stessi token della stanza riletti che con ombra, il segno _stanza dall'evento della frase e mai su disco, contrario senza il segno"),
    ("prova_dati_fissi.py", [], "la cache del prefisso con i dati del turno (16/10, issue #95, dati_stabili_in_storia, dati_turno_tetto_token): motore finto che registra le richieste, 8 turni di chi amministra con ricordi e avvisi; ciò che Ollama deve riavvolgere fra due richieste (dopo il punto di differenza) sotto il tetto da secondo turno, ricordi e avvisi una volta davanti alla frase del turno in cui sono entrati; ricordo nuovo in sola aggiunta, ricordo dimenticato fuori da ogni richiesta (dati_stabili_rifatti, niente rotta); mai su disco; contrari: interruttore spento (oltre il tetto a ogni turno), conversazione condivisa, ospite, turno tolto; il tetto alla ricerca anticipata; misure (foto, stanza_potata, cache persa e dati del turno in stato --turni, ripresi); con eventi: attivo il segno _dati dall'evento e il contrario senza; revisioni della PR #107: avvisi e riassunto della stanza rifatti a ogni cambio, la passata dopo la frase di sfida, la continuazione, un turno con un tool"),
    ("prova_stanza_cerca.py", [], "passo 4 della conversazione di stanza (14/10, decisione 0029): il tool stanza_cerca (chi vede cosa: un adulto dove era presente e gli ultimi minuti della stanza da cui parla, le parole del minore solo i tutori, un minore solo le sue, voci non riconosciute mai; filtri per parole con la radice, persona, stanza, quando e orari, righe vicine, tetti), l'attesa delle righe in coda con la frase d'attesa attesa.stanza solo oltre la soglia, ripieghi per persona e stanza, il discorso intorno (lo scambio), quando che non è un periodo come parola, la ricerca anticipata di Brain con gli stessi permessi (una passata, niente spinta dopo), Brain (in busta con la fonte stanza, riservato, fuori dalla storia, niente azioni dopo, rete spinta_stanza con i contrari), misure senza parole e la riga di stato --turni, configurazione e schemi; contrari: spento, ospite, zona grigia, minore che cerca un adulto, adulto non tutore che cerca il minore, pausa per ospiti, stanza sbagliata, niente trovato, dimentica, periodo sbagliato, attesa sotto soglia o senza righe in coda; l'ora (18/10, #151): gira alle 12:00 con prove.orologio.ora_del_giorno e rifà la scena alle 00:30, 02:59, 12:00 e 23:59, «HH:MM» per oggi e «ieri HH:MM» per il giorno prima, dalle/alle a cavallo della mezzanotte"),
    ("prova_stanza_tenuta.py", [], "tenuta su disco del testo della stanza (14/10, decisione 0029 punto 5, stanza_tenuta): su disco le righe delle persone di casa riconosciute dalla voce, minori compresi, le risposte di Calliope a loro, le presenze; mai voci non riconosciute, zona grigia, pausa per ospiti, audio; dopo un riavvio il blocco caldo vuoto e la ricerca dal disco con gli stessi permessi (chi c'era dalle presenze sul disco, tutori, minore solo le sue, ospite e zona grigia no), niente doppioni con la memoria, scadenza a 60 giorni e profili tolti, «dimentica» del satellite, svuota di tutto, di una persona e da terminale, indice FTS5 pulito, conteggi in stato --turni, calliope conserva e dati_conservati; tempi su 180 000 righe (p90 sotto i 3 s); contrari: spenta"),
    ("prova_stanza_conoscenti.py", [], "conoscenti (14/10, decisione 0030, stanza_conoscenti): la regola conoscente_nome (vocativi, saluti, presentazioni, terza persona) con i contrari; gruppi in memoria delle voci sconosciute, il nome dal vocativo seguito dalla risposta e dalla presentazione, la proposta solo sullo schermo personale di chi amministra (mai di stanza né di un altro familiare), niente su disco prima del sì; il sì con nome diverso, cognome e nota, riconosciuto nelle righe dopo, su disco con la tenuta e cercato come la famiglia; livello ospite; omonimie (familiare e conoscente con lo stesso nome segnalati e mai fusi, doppione esatto rifiutato, «dimentica Marco» chiede quale); no che non ripropone, indizi discordi, terza persona, poca voce, voce di bambino con e senza lo stimatore, proposta che aspetta lo schermo; scadenza a 180 giorni, dimentica, conserva --svuota da un altro processo e dal processo; promozione a familiare e ritorno solo da chi amministra a voce con domanda e sì (minore con nascita e tutori; contrari: familiare, ospite, scritto, zona grigia, breve, chi amministra o minore da declassare, nome già in famiglia), le righe su disco che seguono; /api/conoscenti (404, 401, schermo di stanza e di un familiare 403, 410); misure senza nomi e stato --turni; contrari: spenti; il conoscente che parla a Calliope (14/10 sera, rifiniture): «Marco Rossi (conoscente)» nei dati del turno e nella riga della stanza, livello ospite, nel registro dei turni solo conoscente: true, la famiglia vince sempre (voce netta, zona grigia, parità, frase breve, omonima); presenze dei conoscenti in memoria, su disco e nel blocco della stanza, che passano alla promozione e si tolgono col dimentica"),
    ("prova_banco_rotazione.py", [], "rotazione dell'audio del banco della stanza (17/10, issue #32): la conservazione toglie i giorni oltre turn_log_days anche a eccezione scaduta o spenta e senza corsia lenta, senza salva (all'avvio e al primo turno di un giorno nuovo dal registro dei turni); contrari: i giorni non scaduti, acceso.json, cartelle che non sono date e file sciolti restano, un turno dello stesso giorno non ruota, nessuna cartella, un errore del banco non ferma il resto"),
    ("prova_conoscenti_conserva.py", [], "conservazione dei conoscenti (14/10 sera, decisione 0030 aggiornata da Dario: come un adulto, non come un ospite): nel registro dei turni il suo id, il nome e le parole (contrari: ospite vero senza parole né nome, senza la conservazione collegata, id sconosciuto), la voce registrata no (niente consenso), terminale e journal col nome, la chiave della conversazione (Brain._speaker_key), la sua conversazione persona:<id> anche con una frase breve nella finestra d'ascolto (contrari: fuori finestra, conversazione anonima, famiglia nella zona grigia), archivio su disco col nome ed eventi su disco (ospite nella sessione), pulizia di ogni giorno; chi amministra la ritrova con ospiti=true (contrari: senza ospiti, familiare, zona grigia, il conoscente stesso); dimentica, scadenza dei 180 giorni, svuota di una persona (dati_conservati con domanda e sì, terminale dal file) e di tutto; promozione (stesso id, turni e archivio restano suoi) e ritorno (restano, la voce registrata no); permessi invariati; il dubbio sopra soglia con un minore e la voce di un conoscente (16/10, #108)"),
    ("prova_stanza_guardia.py", [], "guardiano a posteriori della stanza (14/10, passo 6, decisione 0029 punto 4, stanza_guardia): con un giudice finto, le righe di un minore e quelle dette con lui presente, a blocchi col contesto, dopo l'attesa e a stanza quieta, mai Calliope, la TV né le frasi rivolte a Calliope; filtri (scherzo, gioco, TV → niente; zona grigia, parola incerta, righe fuori dal blocco, autolesionismo di un adulto → dubbio); ombra solo misure senza parole né nomi; attiva: avviso al tutore solo sullo schermo personale, senza parole, già «detto», col rimando a cercare, tetto al giorno, categoria non ripetuta, due dubbi in giorni diversi; carico (voce occupata, quiete, tetto all'ora, guasto riprovato); pausa per ospiti e «dimentica» (in coda e a metà giudizio); il giudice vero con un HTTP finto (stesse opzioni del rilevatore, prompt nella finestra); stato --turni e --guardia con --falso/--vero; contrari: spenta, nessun minore, solo adulti, minore in un'altra stanza; ripresa dal disco dopo un riavvio (14/10 sera: righe in coda riprese, già giudicate no, oltre stanza_guardia_ripresa_h contate, dimenticate, non assestate, pausa, prima del diario, ripresa spenta); modalità gioco (gioco dichiarato nel prompt, minaccia di altri → dubbio, autolesionismo serio del minore resta acuto, non chiaro → dubbio o niente, gioco chiuso o in un'altra stanza → come prima, periodi sul diario dopo un riavvio, Giochi.in_corso); dal 18/10 (issue #159) le righe oltre il limite della ripresa contate una volta sola fra i riavvii e senza quelle rivolte a Calliope, le misure di prima col massimo del giorno"),
    ("prova_stanza_lenta.py", [], "passo 3 della conversazione di stanza, la corsia lenta (14/10, decisione 0029, stanza_lenta): ritrascrizione a DGX libera con la precedenza LENTA, il beam e il prompt coi nomi e le parole di prima, versione 2 in sola aggiunta (la 1 resta) o «uguale»; stanza_lenta_ritrascrivi (auto solo con un Whisper suo o un beam che conta; con «no» chi parla, TV e allucinazioni sul testo della corsia veloce, v2 solo per cambi veri); chi parla sullo scambio (zona grigia corretta, mai verso l'alto; blocco con due voci spezzato; voci alternate «più voci»); allucinazioni (famiglia, ripetizione, corta vuota; contrario: lunga vuota resta); TV a strati (stanza vuota e voce lunga senza pause, pubblicità già sentita; contrari: telefonata in vivavoce, ospite con la famiglia, persona di casa che legge, Home Assistant spento), una riga sola nel blocco, fuori da ricerca e disco; storia non riscritta, tenuta che sostituisce la v1 (parti tenute, TV tolta), stanza_cerca sulla v2, guardiano che aspetta la corsia lenta e rigiudica solo un cambio sostanziale; riassunto progressivo in busta solo per uno scambio più vecchio della finestra; DGX occupata, pausa, «dimentica», RAM oltre stanza_audio_min; l'audio del banco (eccezione del 14/10 sera: solo voci di casa, contrari ospite, zona grigia, conoscente, misto, pausa, scaduta, spenta, senza corsia lenta; «dimentica», svuota di tutto e di una persona); misure, stato --turni, piano dei modelli, configurazione"),
    ("prova_stanza_lenta_blocchi.py", [], "ritrascrizione a blocchi della corsia lenta (15/10, stanza_lenta_blocchi, caso vero in auto): segmenti consecutivi della stessa persona uniti con 0,3 s di silenzio e ritrascritti una volta senza prompt con la precedenza LENTA (il turno passa davanti, coda vera di STTCondiviso); chiusure: altra persona, Calliope in mezzo, voce sconosciuta diversa (la stessa impronta sì), pausa lunga della stessa persona (stanza_lenta_blocchi_pausa_s; con 0 no, la pausa più lunga nelle misure), tetto al confine di segmento, satellite scollegato, pausa della stanza, attesa massima, «dimentica»; ombra (righe di prima, testo nel banco) e attivo (versione nuova ridistribuita sui segmenti, 3 sopra una 2, campo blocco, tenuta su disco, stanza_cerca, guardiano che aspetta); contrari: spento, segmento solo, allucinazione, meno parole che segmenti, testo uguale; banco solo per le voci di casa, il banco manuale che salta i testi dei blocchi, lo script di revisione con un Whisper finto (pagina con WAV PCM 16 bit, scelte, blocchi per pausa, tetto, buchi, riconnessione), misure senza parole e la riga di stato --turni, configurazione"),
    ("prova_minori_cancelli.py", [], "minore forse in pericolo, giro a due cancelli (09/10, caso vero della DGX: adulto ospite preso per il ragazzo che saluta): acuto come prima, da verificare → rassicura e chiede, conferma o smentita della risposta, silenzio con avviso non urgente, due segnali ravvicinati (non dopo una smentita né con la voce incerta in compagnia, 12/10), voce incerta, giudizi guasti, avviso «sicurezza» non a voce vicino al minore, con i contrari"),
    ("prova_minore_ospite.py", [], "ospite dove un minore ha parlato da poco (16/10, issue #102, caso vero del 15/10: bambina appena registrata presa per ospite): minore_ospite dal ciclo solo con la voce vicina al minore (primi due profili o ≥ 0,30), «potrebbe essere un minorenne» senza nessun fatto sul minore (ospite_con_minore), parla_minore, minore_sentito_s e la riga di stato --turni; contrari: adulto lontano dal profilo del minore, finestra passata (minori_ospite_vicino_s), altro satellite, voce riconosciuta, conoscente, interruttore spento"),
    ("prova_ospite_riconosciuto.py", [], "da ospite a voce riconosciuta sullo stesso satellite (22/10, issue #171, caso vero del 18/10 dal telefono in auto): due frasi da ospite e poi la persona riconosciuta dalla voce → i dati del turno dicono il cambio una volta per conversazione (voce_ora_riconosciuta); con la stanza le risposte all'ospite «Calliope → voce non riconosciuta» anche nei turni dopo, uguali byte per byte; contrari: riconosciuta dall'inizio, quarto turno, alternanza, conversazione condivisa in compagnia, zona grigia, profilo più protetto, schermo, estensione, ospite troppo vecchio (anche con storia_inattiva_s 0), altro luogo o corsia, conoscente prima e dopo, ospite dopo la persona, interruttore spento"),
    ("prova_avvisi_data.py", [], "avvisi ai tutori con la data e l'origine (14/10, caso vero: un avviso del 12/10 sera arrivato il 14/10 senza data e preso per nuovo): fresco senza data, vecchio con la data («ieri sera», «lunedì 12/10»), scheda sempre con la data, urgente oltre avvisi_urgente_ore detto «non più urgente», segnato falso non detto (guardiano e stato --avvisi --falso), minore vicino, altro adulto non tutore, il tutore che chiede ha nei dati del turno data, tipo, origine e stato, minore_gestisci avvisi, origine dei cancelli dopo un riavvio, database di prima"),
    ("prova_avvisi_audio.py", [], "trascrizione e audio negli avvisi di pericolo al tutore (14/10 sera, decisione di Dario che cambia la 0029 punto 4): anello in memoria (minuti, MB, anello pieno, dimentica, WAV), turni (minore sì, adulto e scritto no), avviso acuto con trascrizione e audio nel cassetto del tutore, scheda «avviso» solo a lui, Scarica l'audio solo dal suo schermo (non altri, nemmeno chi amministra), voce senza parole, spento, senza trascrizione; stanza (minore, adulto con minore presente sì; adulto da solo, ospite, altra stanza no), guardiano attivo con il contesto breve, ombra senza disco con audio_s; scadenza, svuota (tutto, persona, terminale), dimentica della stanza e del tutore; avviso di prima ricostruito o «non c'è più»; dopo un riavvio la scheda ripresa dalla cronologia tiene «Scarica l'audio» (solo l'id del file del cassetto, permessi rifatti al clic; contrari: altro schermo, schermo di stanza, non più tutore, file di un altro, scaduto o tolto con la nota)"),
    ("prova_ciclo_ripetuto.py", [], "la risposta che gira in tondo (14/10, rete ciclo_ripetuto, calliope/ciclo_ripetuto.py): ciclo di una parola, di un gruppo e di una frase fermato nello streaming, stream chiuso verso il motore, il ciclo né detto né nella storia, parte sana o frase pronta scusa.incartata, contrari (no no no, numeri e IBAN dettati, ritornelli, elenchi, la la la), rete spenta, latenza invariata"),
    ("prova_brain.py", [], "filtro del thinking, guardia, ciclo dei tool, storia, nota dichiarata due volte → frase onesta (12/10), per un ospite senza invito (18/10, #28)"),
    ("prova_risposta_sospeso.py", [], "la risposta alla domanda di un tool in sospeso è la richiesta (16/10, #98, caso vero del 15/10: la data di nascita detta dopo la domanda di registra_utente con la stanza accesa presa per «non chiesta», poi una seconda sfida): eseguito senza seconda sfida (valore_risposta_sospeso, valore_sfida_sospeso); contrari: data solo nella stanza, un'altra persona, un altro tool, scaduta, argomenti cambiati, booleano, domanda della politica, foto, voce non riconosciuta, domanda nata senza sfida; pc_guarda con «fai una foto» e i contrari"),
    ("prova_sfida_esito.py", [], "l'esito detto dal modello dopo la frase di sfida superata (16/10, #94, caso vero del 15/10: registra_utente riuscito con cosa_fare e «Non ho salvato niente»): la frase vera detta in una passata, il tool una volta nel registro; contrari: la stessa frase senza tool fermata, dopo un tool di lettura fermata, tool della sfida fallito"),
    ("prova_tempi.py", [], "durate e orari detti a voce"),
    ("prova_stt_correzione.py", [], "correzione delle frasi incerte (05/10, spenta): confidenza da verbose_json, controllo con i contrari, correttore finto, privacy; parole incerte al modello e frase capita trattenuta (07/10)"),
    ("prova_argomenti_incerti.py", [], "parole incerte negli argomenti dei tool (08/10, F0 e F1): argomenti marcati, allineamento alle parole di Whisper, esito vuoto, vocabolario dei nomi noti, probabilità in parallelo al tool, «forse intendeva» con la proposta e il sì senza altre domande, «ripeti o scrivi», contrari (pieno, nome lontano, ospite, zona grigia, casa, frase pronta, la gente), registro e riassunto"),
    ("prova_latenza.py", [], "latenza vera della voce (06/10, P2–P4, P11): guardiano e rilevatore caldi e ricaricati, domanda giudicata in parallelo, conversazione ripresa in cache, mediana e p90 per giorno con le cause e l'avviso, riassunto dell'agente con un tempo massimo; prima frase a pezzi, taratura della voce, Piper sulla CPU o sulla GPU secondo la macchina e dal testo alla voce (07/10)"),
    # ~9 s: microfono e VAD finti in tempo quasi reale, server dei satelliti vero, node se c'è
    ("prova_frase_lunga.py", [], "frase lunga (10/10, caso vero della DGX: dettatura tagliata a 30 s): tetto a 120 s, tempo massimo di whisper-server in proporzione, Listener che al tetto prepara il seguito senza doppioni né buchi, il seguito unito allo stesso turno (`frase_tetto`) con i contrari (nessuno continua, rumore continuo, frase chiusa dal silenzio), giro del ciclo, satellite finto su server vero, niente suono di fine al tetto (satellite e telefono)"),
    ("prova_frase_lunga_voce.py", [], "frase lunga con la voce vera (10/10): dettatura sintetica di ~70 s (Piper) in un Listener con Silero VAD, tetto a 30 s raggiunto due volte, pezzi uniti e trascritti da faster-whisper oltre la finestra di 30 s, con il contrario del primo pezzo tagliato"),
    ("prova_pause.py", [], "pause e fine del turno (07/10, solo misura): pause interne e parlato da Listener, satellite e telefono (voce.js con node), ripresa dopo la frase con i contrari (casse, risposta, oltre 2 s), «aspetta»/«non ho finito» con i contrari, campo «ascolto» del registro, frase_finita e «ripresa» nel protocollo (satellite vecchio), riassunto e soglia stimata in `calliope stato --turni --pause`"),
    ("prova_fine_turno.py", [], "fine del turno System 1 (14/10, Smart Turn in ombra e attiva): Sorvegliato (lento, occupato, guasto → spento), log-mel di Whisper in numpy uguale a faster-whisper e a transformers, ombra con un decisore finto (frase completa, sospesa con «e»/«in»/«poi», numeri dettati, elenco, ripresa dopo una pausa lunga, il nome da solo, decisore guasto o lento → come prima), Listener in «attiva» (chiusura anticipata, attesa lunga che non taglia, incerto, guasto, lento → silenzio fisso), configurazione, catalogo, protocollo del satellite, ciclo e riga di `calliope stato --turni`"),
    ("prova_fine_turno_voce.py", [], "fine del turno System 1 con il modello vero (14/10, livello 3): Smart Turn v3.2, Silero in ONNX e frasi di Piper deterministiche; frasi complete «finito», pause dopo «e poi,» e «poi,» «non finito», Listener in «attiva» a tempo reale che chiude prima dei 700 ms; stampa le frasi sospese che Piper fa sembrare finite e i ms del decisore"),
    ("prova_preselezione.py", [], "preselezione dei tool System 1 (15/10; dal 16/10, #25, misura chiusa come negativa e ombra tolta dal ciclo): prototipi dagli schemi (nome, prima frase, esempi tra «…»), codifica a n-grammi, il banco di 148 frasi coi tool veri (richiamo col margine di serie come avviso, frasi a «nucleo», contrario col margine 0, decisore sotto 30 ms), segnali di struttura (tool recente, tool nei dati o nella proposta, foto → tutti) e i contrari; l'ombra tolta: niente ganci in ciclo, main, stato, nessun campo in Config e in calliope.yaml, un locale con le chiavi di prima segnalato senza fermare l'avvio, il nucleo dello script della DGX da --nucleo; contrario: il decisore resta"),
    ("prova_dopo_tool.py", [], "la frase dopo il tool System 1 (15/10, spenta di serie): il decisore «codice» per gli esiti chiusi (timer, ora, calcolo, lista, volume) con la frase pronta del tool e i contrari col loro perché (più tool, tool fallito, da spiegare, domanda in sospeso, nome incerto, lista letta, memoria, senza frase, testo del modello, minore, tono formale, più frasi, domanda con un'azione, persona lunga, proposta aperta), dal 16/10 (#103) le frasi d'apertura che non contano come richieste e la lista e l'agenda lette fino a due voci coperte, coi contrari (due richieste, «No.» davanti, liste di 3 e 5 voci), la sostanza in ombra, Brain con un motore finto (spento come prima, attivo con una passata e la storia coerente e la regola, contrari in Brain con la seconda passata, decisore guasto, casa_comando già pronta, ombra cronometrata e confrontata in streaming, interrotta che chiude la richiesta), configurazione, ciclo, conservazione e riga di `calliope stato --turni`"),
    ("prova_eventi.py", [], "registro degli eventi a secco (10/10, passo 1 in ombra): ogni tipo proiettato o escluso, controlli e disco (sfida, dati non fidati, riservati, «mai»), proiezioni pure (import, tetto di righe, determinismo anche dopo il rigioco), partizione (adulto, minore e ospite su due satelliti), due corsie della stessa persona, riassegnazione, porte (AST, annuncio, avviso al tutore, coda)"),
    ("prova_eventi_ciclo.py", [], "registro degli eventi sul ciclo della voce (10/10, passi 0–2): contatori del passo 0 e confronto dell'ombra su un giro sintetico (interruzione, stop, cortesia, timer, frase filtrata, «Lo apro?», domanda con il testo dopo, «Sì?»), garanzia detto = proiezione, niente disco prima della prima frase, eventi: spento come prima; passo 2: autore e atto all'invio (frase pronta, ripiego, contenuto), chiamate fra le frasi nella proiezione, risposta scritta dagli eventi, ogni atto classificato, nessuna frase fuori turno"),
    ("prova_eventi_disco.py", [], "registro degli eventi su disco (10/10): riavvio con rigioco, proposta persa, riga rovinata (eventi_troncati), disco in sola lettura o che non scrive; «dimentica» vera (byte di conversazioni.db e del WAL, residui in calliope stato, conversazione in corso chiusa, dal 13/10 col ciclo vero anche con eventi spento); rotazione, ospiti cancellati alla chiusura, sfida e segreti mai su disco"),
    ("prova_uscita_unica.py", [], "l'uscita unica verso la voce (10/10, passo 2 del registro degli eventi): AST (fuori da eventi/uscita.py e tts.py nessuno chiama say, say_cached, chime, suono, sintetizza, start_turn, wait sulla voce; lo stream di Brain letto solo da _rispondi e _ricerca_promessa), atti dell'elenco chiuso con la loro categoria, nessuna frase fuori turno (turno 0, turno interrotto, satellite che non la dice), niente disco e microsecondi per frase"),
    # ~7 s: con i banchi d'attacco di prova_politica e prova_valore rigiocati sul registro
    ("prova_eventi_attivo.py", [], "registro degli eventi acceso (10/10, passo 3 e argomenti del § 13): eventi: attivo sul ciclo vero (parlato diverso 0, garanzia detto = storia, stop e interruzione senza frasi mai dette, annunci e «Sì?» nella storia, storia di Brain = proiezione, correnti senza il turno vivo), ombra come prima; promemoria della parte non detta («ripeti il secondo punto») e dei cosa_fare nel blocco dello stato; cache del prefisso (turni definitivi uguali byte per byte, riletti, cache_rotta in calliope stato --turni); visibilità decisa alla scrittura (banco di prova_politica 99/99 e attacchi di prova_valore rigiocati con attivo, fughe 0, sigilli, proposta_rispondi fuori); argomenti (Celsius → chilometri, sviluppo in pausa e proposta da parte con la mezza frase, indice, ripresa, «ricominciamo» indizio con attivo e comando con ombra, contrari); backend OpenAI"),
    ("prova_eventi_guardia.py", [], "la guardia dei riletti e il criterio di E1 (15/10, issue #11): la base dei giorni d'ombra e l'avviso oltre metà con eventi: attivo su turni finti (contrari: sotto la soglia, pochi turni, base piccola, solo ombra; i riletti stimati), in calliope stato --turni e nella pagina di sempre; eventi_ombra.proiezione_diversa senza i motivi dichiarati; sul ciclo vero in ombra parlato e differenze non a zero per costruzione, la proiezione sì, e lo stesso campo con attivo; dal 18/10 (issue #159) i turni interrotti nel criterio, anche senza nessuna frase sentita per intero, contati a parte col motivo"),
    ("prova_config.py", [], "calliope.yaml, variabili d'ambiente, chiavi sbagliate"),
    ("prova_config_satellite.py", [], "microfono, casse e webcam nella sezione satellite, ripiego con avviso"),
    ("prova_config_modi.py", [], "campi a modi (17/10, #83): ogni campo a modi con il suo validatore, maiuscole, altro genere con l'avviso gentile, valori sbagliati con l'avviso e il valore di serie, «no» di YAML, locale della DGX invariato, Cancelli che non spengono l'avviso ai tutori per un refuso, controllo dei campi nuovi"),
    ("prova_contesto.py", [], "finestra di contesto dal setup (modello, memoria, tempo) e token veri a ogni turno"),
    ("prova_conversazioni.py", [], "conversazione come oggetto, archivio delle conversazioni (ricerca ibrida, visibilità), compressione vicino al limite, fine e ripresa, modo cronologico di conversazione_cerca (08/10)"),
    ("prova_ollama_carico.py", [], "modelli residenti in Ollama (06/10, e2e): limite letto o assunto, avviso quando Calliope ne usa di più, embedding delle conversazioni solo senza scacciare nessuno (inattiva, keep_alive 0, ricerca per parole con Ollama pieno)"),
    ("prova_corsie.py", [], "conversazioni per persona e satelliti insieme (06/10): scelta della conversazione, ospiti per satellite, «sì» breve altrove, doppioni, risposte in parallelo con la coda, smistatore, ciclo e stato della voce per corsia, ripresa; «Sì, grazie.» breve dopo una conversazione chiusa per tempo (07/10)"),
    ("prova_ciclo.py", [], "il ciclo della voce (06/10, P8) giro per giro con tutto finto: primo avvio e registrazione, nome vero, finestra di ascolto, approfondisci, ricerca promessa, ricominciamo, cortesia, frase ignorata, esci, spegniti"),
    ("prova_stati_buchi.py", [], "i dieci stati del dialogo che rischiano di non essere gestiti (10/10, passo 0 della macchina a stati): 1, 2, 4, 5, 7, 8 documentati come buchi attesi da correggere con il passo che li chiude; 3 («no» all'agente), 6 (coda della conversazione), 9 (nome vero), 10 (cancelli dopo un riavvio) corretti, con i contrari"),
    ("prova_dialogo_tool.py", [], "dialogo tra tool e modelli (09/10, caso della DGX web_cerca senza domanda): chiamata vuota a ogni tool con argomenti obbligatori → errore strutturato (campo, argomenti, esempio, correggibile, cosa_fare), obbligatorio mancante con altri argomenti, argomento sconosciuto, conversioni di forma e contrari, eccezioni senza traccia, giro di correzione in Brain (frase non detta, domanda detta, tetto, errore non correggibile, frase d'attesa), strumenti dell'agente"),
    ("prova_nome_da_solo.py", [], "il nome da solo e la modalità Star Trek in uso (06/10, DGX) con un satellite finto: scatto sicuro con testo vuoto o nome storpiato breve → saluto o suono d'inizio e finestra aperta, suono di fine se nessuno parla; contrari; tool senza argomenti obbligatori senza frase d'attesa; risposta di sola punteggiatura"),
    ("prova_agenda.py", ["--secco"], "timer, promemoria, appuntamenti: scadenza, annullo"),
    ("prova_agenda_tutto.py", [], "annullare tutta l'agenda si conferma (16/10, #99): con più voci (non soli timer entro un'ora) la domanda con l'elenco e la proposta in sospeso; al «sì» con una frase di consenso annullate solo le voci nominate; contrari (la richiamata senza consenso, il «sì» per una parte, voce aggiunta dopo anche col sì accettato dalla politica, appuntamento non nominato, sveglia di 8 ore, una voce, il timer della pasta, la proposta di un altro tool); stanza accesa senza sfida; classe d'effetto E2"),
    ("prova_memoria.py", ["--secco"], "memoria per persona"),
    ("prova_liste.py", [], "liste della casa e memoria della casa"),
    ("prova_pc.py", [], "tool pc_* con un PC finto: permessi, valori a voce, blocco"),
    ("prova_documenti.py", [], "documenti Word, Excel e PDF: file, formule, modifiche, permessi; rimasti sul server con il telefono: la scheda con «Scarica» nella frase, documento_leggi (09/10)"),
    ("prova_ufficio.py", [], "ufficio: conti, XML FatturaPA (XSD se c'è), numerazione concorrente, rubrica, modelli Word e PowerPoint, flusso a voce, totale nei dati del numero"),
    ("prova_casa_ha.py", [], "casa via Home Assistant con un HA finto: regole, permessi, TLS, diagnosi"),
    ("prova_meteo_casa.py", [], "meteo di casa (09/10): condizioni di HA in italiano, giorni chiesti, entità weather esposta con l'HA finto (adesso, domani, stasera, cache, solo weather.get_forecasts, ospite), non esposta mai vista, prompt secondo la disponibilità (entità, città, segnaposto, niente, HA spento), città salvata a voce solo da chi amministra (proposta e conferma, luogo.json, configurazione che vince)"),
    ("prova_casa_nomi.py", [], "casa: comando capito da HA ma senza dispositivi (08/10), la candidata tra le esposte per nome o area, domanda, mai allargare, consiglio a chi amministra"),
    ("prova_capacita.py", [], "registro delle capacità: stati, riassunto, prompt, calliope_stato, macchina nuova"),
    ("prova_novita.py", [], "chi è Calliope e cosa c'è di nuovo (09/10, caso vero della DGX): CHANGELOG finto (tabella, sezioni, intervalli, «(notte)»), gestore finto (versione installata, storia, versione di prima), voci per periodo e dall'ultimo aggiornamento, frase breve senza host né percorsi, scheda personale con «Scarica»; «chi sei?» con fatti veri; «cosa sai fare?» per aree e il dettaglio con area; contrari"),
    ("prova_piano.py", [], "taratura della macchina, fasi 1–2 (08/10): inventario con sonde finte (portatile, DGX unificata, senza GPU, registro, GPU fuori catalogo, modello in parte sulla CPU), catalogo con fonti, piano su macchine finte (solo CPU, 8, 16, 24, 32 GB, DGX di oggi ritrovata, Windows su ARM) con i contrari, calliope stato --piano in sola lettura"),
    ("prova_arbitro_memoria.py", [], "arbitro della memoria, passo 1 (14/10): conto della memoria e classi delle attività in sola lettura sulla DGX finta (tempo reale, sfondo, a richiesta, «fuori»), proposta in ombra (sfondo dal meno usato, agente solo dal passo 4), contrari: mai il tempo reale né un modello non di Calliope, memoria non letta; portatile e solo CPU; da_config; calliope stato --memoria senza chiamate esterne; passo 2 (15/10): quiete() unica, confronto in ombra con guardia, corsia lenta, embedding e agente senza cambiare le decisioni, l'arbitro in ombra (coda per precedenza a voce ferma, un caricamento alla volta, buttate, proposta con la memoria vera, a richiesta ogni minuto, tempo reale mai), registro e calliope stato --memoria --storia con il criterio"),
    ("prova_arbitro_quiete.py", [], "la «voce ferma» dell'arbitro della memoria dopo una frase accettata (18/10, #157): main.py e Ciclo veri, satellite finto (AscoltoRemoto vero): libera all'inizio del giro dopo; contrari: frase buttata, un'altra corsia che parla ancora, un turno lungo vero (tetto, tool lento, risposta lunga) senza tenuta, il secondo avvio; tenuta massima con la riga nel log, tenute_voce nella riga del minuto e nella storia"),
    ("prova_installa.py", [], "installazioni con un server HTTP finto: catalogo, permessi, offerta, ripresa"),
    ("prova_schermi.py", [], "schermi: server e SSE veri, abbinamento, visibilità, schede dei tool, log"),
    # ~3 s: server degli schermi vero, registro dei turni finto (anche grande: 28 000 turni)
    ("prova_cruscotto.py", [], "cruscotto di chi amministra (06/10): solo lo schermo personale di chi amministra, nessun testo di persone, latenza, regole, errori, abbinamenti, richieste in attesa, cache e registro grande, prefisso del modello invariato"),
    # ~20 s: la pagina degli schermi e del telefono in Edge o Chromium senza finestra
    ("prova_cruscotto_pagina.py", [], "cruscotto nella pagina vera: pulsante solo per chi amministra, scheda con le sezioni, Aggiorna al suo posto, Chiudi, sul telefono da Io a schermo intero, nessun errore JS"),
    # ~25 s: la pagina del telefono e dello schermo in Edge o Chromium senza finestra
    ("prova_markdown_pagina.py", [], "lettore Markdown nel browser vero (07/10): testo dell'agente ostile (script, HTML con attributi, javascript:, immagini) mai eseguito né come elementi, tabella di 300 righe, annidamenti, sommario, «Scarica» PDF/Word/MD negli scaricamenti, schermo intero del telefono leggibile, nessun errore JS né CSP"),
    ("prova_scheda_intera.py", [], "telefono (06/10): una scheda a schermo intero (cruscotto da Io, lavoro con il codice, documento con una tabella larga) a 3 dimensioni: testo ≥ 16 px, niente di lato, aggiornamento al suo posto senza perdere lo scorrimento, Chiudi, Esc, indietro, nessun errore JS"),
    # ~15 s: la pagina in Edge o Chromium senza finestra; senza browser si salta
    ("prova_schermi_satellite.py", [], "uno schermo per satellite: riusato ai ricollegamenti e dopo i riavvii, token rinnovato se perso, revoca a cascata, abbinamenti inattivi segnalati"),
    ("prova_schermi_pagina.py", [], "pagina degli schermi in un browser vero: si ricollega da sola dopo un riavvio"),
    ("prova_cdp_orfani.py", [], "browser delle prove nel job object della prova (14/10): la prova che muore senza chiudi() non lascia processi msedge con il suo profilo, contrario senza job, chiudi() di sempre"),
    # ~10 s: server degli schermi vero su 127.0.0.1, ufficio con l'estrazione finta
    ("prova_scritto_conversazione.py", [], "la conversazione a voce e lo scritto: regola pura, voce che apre e rinnova, breve e scritto che non rinnovano, altra persona e ospite che chiudono; dal 28/10 (#301) casella, foto e file dello schermo personale sempre, moduli e schermi di stanza ancora in conversazione (evento «scrittura» con `moduli`, 403 senza_conversazione e regola nel registro), modulo chiuso a metà"),
    ("prova_scritto_senza_voce.py", [], "scritto dallo schermo personale senza aver parlato (28/10, #301) nel ciclo vero: familiare al modello, chi amministra al più familiare, ciò che vuole la voce rifiutato, minore fuori orario rifiutato e dentro gli orari col suo livello, foto e file di un minore fuori orario rifiutati, conversazioni_dimentica scritto e poi «sì» scritto mai eseguito, ospite dallo schermo di stanza e modulo rifiutati"),
    ("prova_scritto.py", [], "scrivere invece di parlare: controlli dei codici, moduli dei tool con il server vero, valori al tool senza il modello, permessi, canale, registro"),
    # ~15 s: modulo e casella nella pagina vera (Edge o Chromium senza finestra); senza si salta
    ("prova_rispondi.py", [], "rispondi dove ti ho chiesto: scritto dal telefono con lo studio attivo, schermo senza audio, schermo_mostra, follow-up, annunci"),
    ("prova_scritto_pagina.py", [], "moduli nel browser vero: errore della cifra di controllo mentre si scrive, invio, casella"),
    # ~5 s: Pillow, Brain con un backend finto, server degli schermi vero, PC finto
    ("prova_annunci_foto.py", [], "gli annunci scritti in una foto o in un file arrivano al modello col dubbio (28/10, issue #303, caso del banco dello Studio): etichetta della foto e busta di file e audio con la frase sugli annunci, uguale a ogni turno; contrari web, estensione, agente, archivio; quarantena; dato del turno dei minori; caratteri aggiunti"),
    ("prova_immagini.py", [], "foto (05/10): controllo e riduzione dei byte, album della conversazione, foto nei messaggi, guardia sulle azioni, /api/immagine, pc_guarda e permessi, cattura dal satellite"),
    # ~3 s: Brain con un backend finto, esecutore remoto con un server dei satelliti finto
    ("prova_dispositivo.py", [], "il dispositivo da cui si parla (16/10, issue #100): la spinta di pc_guarda solo col PC raggiungibile e capace (telefono senza portatile no), la riga «dispositivo:» nei dati del turno per telefono, satellite, PC, scritto e locale, Ciclo._dispositivo_turno, i volti non si riconoscono nel prompt"),
    # ~1 s: hub degli schermi vero, i passi veri del ciclo (16/10, #96)
    ("prova_immagini_attesa.py", [], "foto in attesa della domanda con un'altra voce in mezzo (16/10, #96): l'ospite, un'altra persona o un minore non la tolgono né la ricevono, la stessa persona sì; «esci» (anche dopo l'ospite) e la scadenza la tolgono, con il dato «foto persa» una volta (mai come biblioteca); «ricominciamo» e «dimentica» la tolgono senza il dato"),
    # ~8 s: file generati in memoria (anche ostili), Brain finto, server degli schermi vero
    ("prova_allegati.py", [], "allegati (05/10): tipo dai byte, lettura per tipo, file ostili (bomba zip, XXE, macro, PDF rotto, eseguibili), audio, contenuto marcato e guardia, allegato_leggi/archivia, delega, /api/allegato"),
    # ~6 s: cassetto in una cartella temporanea, Brain finto, server degli schermi vero
    ("prova_cassetto.py", [], "cassetto dei file per persona (08/10): entrata (foto, file, audio; mai programmi né ospiti), scadenza e «ho eliminato», revisione una volta al giorno, tieni/elimina/tieni ancora, tetto, minore e tutore, zona grigia, ritrovamento dopo un riavvio, contenuto in busta, /api/cassetto, ciclo finto"),
    # ~15 s: la scheda del cassetto in Edge o Chromium senza finestra; senza browser si salta
    ("prova_cronologia_schede.py", [], "cronologia delle schede per persona e scheda «Conversazione» (08/10): salvataggio solo personale e certo, chiavi, tenuta e tetti, ripresa dopo un riavvio con le schede finali (lavoro interrotto, sviluppo ricostruito, modulo e timer saltati), «Scarica» con un gettone nuovo, pulizia (tool, /api/schede, evento), conversazione dall'archivio (meta, sfida e codici tolti, in diretta solo ai propri schermi, dimentica, tenuta, Markdown), server vero"),
    ("prova_compagnia_pagina.py", [], "segno della compagnia nella pagina vera (09/10): «In compagnia: chiamami per nome» sotto lo stato della voce dello schermo di stanza e sul telefono, resta addormentata, sparisce con una voce sola, mai in un'altra stanza, nessun errore JS né CSP"),
    ("prova_cronologia_pagina.py", [], "cronologia delle schede e conversazione nella pagina vera: riavvio del server, schermo nuovo che ritrova schede e chat, turno nuovo in fondo senza riscrivere, Scarica, stanza vuota, Pulisci con due tocchi, vista dello sviluppo dopo un riavvio, telefono con la conversazione nella sezione (schede piccole, filtri, ricerca, misure), nessun errore JS né CSP"),
    ("prova_cassetto_pagina.py", [], "scheda del cassetto nella pagina vera: carosello (miniatura, sigle), Tieni solo dove si può, Tieni ancora, Tieni, niente Elimina (dal 28/10 sera si elimina a voce), schermo di un'altra persona vuoto, nessun errore JS né CSP"),
    # ~15 s: la pagina in Edge o Chromium senza finestra; senza browser si salta
    ("prova_immagini_pagina.py", [], "foto nella pagina vera: pulsante, file scelto, incolla, trascina, SVG rifiutato, scheda con la miniatura"),
    # ~40 s: Calliope vera con un satellite finto; senza voci di Piper o modelli si salta
    ("prova_scritto_calliope.py", [], "testo scritto, modulo e foto dentro Calliope vera: nome tolto, niente STT, foto in attesa, registro e terminale senza codici né byte"),
    # ~6 s: server degli schermi e dei satelliti veri, client WebSocket finti
    ("prova_telefono.py", [], "telefono (web app): file e CSP, modelli col token, abbinamento e protocollo, prendi/lascia, CA di casa, nomi con Host e Origin, impronta nuova al ponte"),
    # ~60 s: la web app in Edge o Chromium senza finestra con il microfono finto; senza
    # browser, onnxruntime-web, modelli della wake word o voci di Piper si salta
    ("prova_telefono_pagina.py", [], "telefono nel browser vero: wake word e VAD come in Python, niente audio senza il nome, voce e barge-in"),
    # ~12 s: abbinamento del telefono che riprende dopo la pagina sospesa (iOS); con Edge o
    # Chromium anche nel browser vero, senza si fa solo la parte a secco
    ("prova_parla_pc.py", [], "«Parla» sul PC personale (27/10, passo 1b): il satellite legato prende il posto e riceve «tocco», /api/accedi e /api/parla sul server vero (solo schermo personale legato, 403, 409, 401, 429), il satellite allunga la finestra senza il nome (al più 30 s) e il Listener usa la più lontana"),
    ("prova_pc_pagina.py", [], "schermo personale del PC a sezioni nella pagina vera (27/10, passo 1b): stanza invariata, smistamento di sezioni.js, barra e indietro, «Parla» fino al satellite, casella a destra e file trascinato, tre colonne a 1440 e 1100, conversazione dietro il pulsante a 1000, barra in basso a 700, contrasto e clic, pagine Liste e Agenda coi tocchi, Lavori, Cassetto e Giochi, Documenti e Ufficio con la ricerca, conversazione con le schede piccole e i filtri, nessun errore JS né CSP"),
    ("prova_aspetto.py", [], "aspetto dei satelliti personali (27/10, passo 1c): accenti con contrasto AA e il lilla di serie anche nei CSS, sezioni nascoste per età (12 anni, il giorno dei 13, senza data), la preferenza salvata e tolta con «svuota», /api/accedi e /api/aspetto sul server vero (personale sì, stanza no, evento a tutte le pagine della persona)"),
    ("prova_sezioni.py", [], "telefono a sezioni (27/10): SEZIONE_DI_TIPO uguale in schede.py e schermo.js, ogni tipo con la sua casa e il suo elenco, la sezione scritta dal server (anche nella scheda dello sviluppo), la regola «viva» per tipo e il router sul frammento (con node)"),
    ("prova_telefono_consapevole.py", [], "quello che Calliope dice del telefono e dello schermo personale (28/10, #288–#291): la nota del dispositivo con lo schermo personale aperto, chiuso o assente (ospite e zona grigia mai, Casa sotto i 13 anni, Ufficio per chi non amministra, lo scritto dallo schermo personale), il paragrafo delle sezioni nel prompt (token stimati) e il prefisso uguale fra turni e persone, i due casi del 28/10 nel Brain (nota, prompt, schermo_mostra con la pagina, campo dispositivo); schermo_mostra con cosa=pagina (aperto, chiuso, assente, ospite, zona grigia, Ufficio, minore, forme, classe sicura, fuori dai tocchi, Schermi.apri_pagina col solo nome); i lavori e i documenti rimasti in casa senza «server» né «satellite» (Le mie cose › Lavori e programmi con lo schermo abbinato), documento_crea «lo consegna a chi parla»; protocollo e pagina del telefono nella riga «[SATELLITE] collegato» sul server vero, una versione fuori forma no"),
    ("prova_raccolte.py", [], "Le mie cose e il canale «tocco» (28/10, passo 2a): tessere dai servizi (conti, Ufficio solo a chi amministra, servizio mancante o rotto «non disponibile»), pagina Liste, tocchi.prepara (sconosciuto, dati non validi, voce sparita 409, voci ambigue 422), /api/raccolte e /api/tocco sul server vero (personale sì, stanza 403, 401, 429) e il ciclo: ToolRegistry.call col livello del proprietario, registro esito e canale «tocco», la riga nella storia, rifiuti per voce, livello e minore, detto_persona col canale «tocco»; #266: col vincolo e lo ToolSpec del registro, la spunta su un lista_togli non fidato o solo per chi amministra rifiutata; «tutto.» 422"),
    ("prova_conversazione_schede.py", [], "Conversazione con le schede dentro e i filtri (28/10, passo 3, #242): la scheda del turno (copia storica, rimando, niente; tetto), Brain la lega al turno solo con l'identità certa (anche il tocco), turni() con oscura e riservato, i canali voce/scritto/tocco/modulo, il modulo nella storia col canale, chat_filtra (oggi, ieri, solo schede, ricerca con testo ostile, mai turni d'altri), /api/conversazione sul server vero (solo il proprietario, tutore e ragazzo separati, stanza 403, 401, 400, 413, 429); dalla revisione della PR #271 il riservato che non passa da una scheda, la stima dei token, le copie leggere e il dettaglio, foto e file mai legati"),
    ("prova_agenda_pagina.py", [], "pagina Agenda, tasti del timer e vincolo dei tocchi (28/10, passo 2b, #257 e #262): tocchi ammessi solo su tool di classe nota e reversibile (pericoloso, senza classe, dati non fidati, irreversibile, oltre E2, ToolSpec che declassa: no; all'import, in prepara e nel ciclo senza chiamare il tool), contesto del turno di prima azzerato e rimesso, vista per giorno ai bordi (mezzanotte, sesto e settimo giorno, ora legale), pagina coi timer di casa e i promemoria della persona, «+1 minuto» e «Ferma» sul timer toccato (non l'ultimo messo) fino al registro e alla storia, timer suonato nel frattempo, /api/raccolte e /api/tocco sul server vero (409, 429); #266: solo i TOCCABILI, gli ESCLUSI rifiutati (dimentica, catture, rubrica, tutore, agente, voce), la fonte non fidata anche per un'«azione», l'hub vero con due stanze (stanza predefinita, tutti, la sua), livello del mittente, conv_archivio; PR #270: aggiornamento dove la scheda c'è (cucina sì, telefono d'altri no), traccia col tetto, conv_archivio del modulo, timer finito, TOCCHI immutabile; numero degli schermi riusato dopo una revoca da terminale (Ferma, collegamento, sessione)"),
    ("prova_pagine_cose.py", [], "pagine Lavori e programmi, Cassetto e Giochi (28/10, passo 2c, #258): sviluppi, lavori in corso con la scheda in diretta della cronologia (non quella di un avvio di prima), la domanda, i programmi, i finiti in memoria e dalla cartella dei risultati, della persona e, per chi amministra, quelli degli altri (minori compresi) col nome in una sezione a parte (2d, decisione del 28/10; un familiare mai), la frase di lavoro_stato sui soli suoi (anche per chi amministra), schede finali costruite una volta (lock, file riscritto con lo stesso nome), estensione approvata senza «da approvare»; cassetto vuoto del figlio; cassetto della persona e del figlio al tutore in sola lettura (non ad altri adulti), «Tieni» non ai minori, chiave della pagina; giochi di casa col livello del manifesto e quelli abilitati al minore, partite aperte della persona (qui, a chi tocca, punti), giochi spenti; servizi che mancano o sollevano; /api/raccolte sul server vero («Scarica» registrato e tolto dalla pagina, il tasto del cassetto come prima, ospite 403)"),
    ("prova_pagina_documenti.py", [], "pagina Documenti (28/10, passo 2d, #259): fatti da Calliope (i propri; chi amministra anche quelli di Bianca e dei minori col nome; un familiare mai quelli di Dario; un minore i suoi, col preset «documenti: no» nessuno), archivio di casa per tipo coi permessi della voce (chi amministra tutto; un familiare non i personali degli altri; un minore niente), di chi è e «Scarica» del file originale (tipo e nome con gli accenti, permessi rifatti al clic, file tolto 404), ricerca con le stesse regole e testo ostile, servizi che mancano o sollevano, /api/raccolte/cerca sul server vero (20 al minuto, ospite 403, 400), scaricamento vero, annuncio con lo schermo abbinato ma chiuso; dalla revisione della PR #268: più di 8 documenti (nota, ricerca su tutti, tessera), sole parole vuote, tessera di chi amministra, voci di «Scarica» per schermo, originale riletto col tipo vero, file_di mai fuori dalla cartella (.., assoluto, giunzione NTFS) né oltre archivio_max_mb; dalla seconda revisione: parole corte e pertinenza nella ricerca, nome di «Scaricato» uguale al file salvato, voci degli schermi revocati tolte"),
    ("prova_pagina_ufficio.py", [], "pagina Ufficio (28/10, passo 2e, #260), solo chi amministra: fatture, note di credito, preventivi, DDT e serie dei modelli da Numeratore.elenco (numero, data, cliente, importo salvato, emessa o annullata col motivo, in preparazione, al più 20 per serie), «Scarica» del PDF e dell'XML (tipo e nome, permessi rifatti al clic, file tolto o fuori dal registro 404), rubrica (di casa e sua, non i personali degli altri); familiare, minore anche col segno di chi amministra e ospite 404 su pagina, ricerca e «Scarica»; ricerca per numero, cliente, comune, partita IVA, parole corte e vuote, testo ostile; servizio che manca (nota) o che solleva (503); nomi ostili come dato; server vero (200, 404, 403, XML scaricato)"),
    ("prova_telefono_abbina.py", [], "telefono: abbinamento che riprende (ripresa segreta, token una volta sola, niente orfani), sessione che riprende al ritorno in primo piano"),
    # ~70 s: diagnostica e microfono del telefono; con Edge o Chromium e una voce di Piper anche
    # nel browser vero (microfono finto a 44,1 e 48 kHz, contesto forzato), Whisper se in cache
    ("prova_telefono_audio.py", [], "telefono: audio del microfono giusto (durata, contenuto, contesto rifatto), «Prova il microfono» e il suo endpoint"),
    # ~10 s: schermo acceso e vista da guida, in Edge o Chromium (senza si salta) con una
    # Screen Wake Lock API finta che vuole il gesto come WebKit
    ("prova_studio_home_pagina.py", [], "la home dello Studio nella pagina vera (30/10, #284, passo 4.5): telefono a 390×844, 320×693 e col testo grande, PC personale; prossima verifica con data, obiettivo e previsione, oggi, tappe, «Impara» soltanto, «Da decidere» col perché, la pagina da parte; «Tieni», «Riprova» e le due domande come tocchi; la vista aperta al server; nessun errore JS né CSP"),
    ("prova_studio_pagina_telefono.py", [], "lo Studio nella pagina vera del telefono (29/10, #281, passo 4.2): la tessera apre la pagina, galleria con due foto e un PDF (bordi di bordi.js, miniature), fotocamera finta con due scatti, ordine su e giù, togli, rifai, misure a 390×844 e 320×693, invio nell'ordine al server, nessun errore JS né CSP"),
    ("prova_telefono_schermo.py", [], "telefono: schermo tenuto acceso col microfono (richiesta nel tocco, ripresa, avviso se negato o assente, versioni di iOS), sezioni (smistamento, schede vive in Adesso, novità, router, Io, In auto) a 3 dimensioni, Le mie cose (tessere, pagina Liste e spunta, pagina Agenda e tasti del timer, pagine Lavori, Cassetto e Giochi, pagina Documenti con «Scarica» e la ricerca, pagina Ufficio di chi amministra con «Scarica XML» e la ricerca); le schede della pagina Agenda una per una a due dimensioni (#266)"),
    ("prova_agenti.py", [], "agenti: tunnel con ssh finto, sandbox, Ollama finto, arbitro, tool, permessi"),
    ("prova_archivio.py", [], "archivio dei documenti di casa: grafo, deduplicazione, permessi, tool, agente, riprocessamento"),
    # ~12 s: docker finto, container usa-e-getta simulati
    ("prova_estensioni.py", [], "estensioni e guardrail: manifesto, porta stretta, azioni pericolose sospese e confermate, sfida, versioni, impronta"),
    # ~5 s: hub degli schermi vero, server su 127.0.0.1, docker finto con il Node della macchina
    ("prova_giochi.py", [], "giochi e schede interattive (05/10): manifesto con la scheda, documento e CSP del riquadro, approvazione dei giochi puri, partite su uno schermo e condivise, chat e frasi col guardiano, azioni della porta, banco d'attacco dei messaggi, tempo di gioco dei minori, richieste ai tutori, test JavaScript"),
    # ~3 s: i comandi a voce dei giochi (11/10), hub vero, ciclo finto, Node se c'è
    ("prova_gioco_voce.py", [], "comandi a voce dei giochi (11/10; dal 14/10 dalla macchina a stati, niente più ascolta piatto): i comandi delle fasi nel manifesto, sottoinsieme a runtime e mai comandi nuovi, la mossa con il solo comando e il nome di chi gioca, chiuso e partita di prova; nel ciclo la regola gioco_comando con i contrari (frase più lunga, nessun gioco, altro satellite, comando non attivo, domanda in sospeso), la finestra senza nome solo per le forme dell'elenco e il suo tetto, contesto e gioco_comando per il modello, chi gioca solo con la voce riconosciuta; prova di fumo con i comandi"),
    # ~4 s: la macchina a stati dei giochi (13/10), Node per il nucleo e la prova di fumo
    ("prova_gioco_macchina.py", [], "macchina a stati dei giochi (13/10): scheda.macchina nel manifesto (comandi a voce piatti dagli slot, uguali in Python e nel motore, 14 contrari), documento del riquadro con il motore, il nucleo (preparazione, turni, esito, fine, ancora, tela; la forma dei risultati: esito annidato, dati mancanti, fuori da verso, attivi che allarga, vista), prova di fumo per fasi (senza uscita, mai raggiunta, mai attivo, non finisce, mossa che lancia, fuori dominio), apriGioco con g.stato() e i comandi con il valore"),
    # ~3 s: il palco fisso dei giochi (14/10), Node per l'impaginazione e la prova di fumo
    ("prova_gioco_palco.py", [], "il palco fisso dei giochi (14/10): l'impaginazione pura del motore nei due orientamenti (1280×720 e 720×1280) per i sei modelli più la tela, otto giocatori, il tris e le porte, senza niente fuori, sovrapposto o tagliato; i difetti messi apposta detti per l'agente (troppi pulsanti, titolo lunghissimo con la fonte, testo di una casella, esito lungo, griglia 12×12 con troppo testo, tela schiacciata); la prova di fumo che misura il palco di ogni pagina raggiunta (contrari con la fase e la strada) e g.palco(); la diagnosi «palco» anche in prova"),
    ("prova_gioco_stato.py", [], "lo stato della partita che Calliope conosce (14/10, passo 2 del progetto dei giochi): l'istantanea del motore validata dal server contro il manifesto (banco d'attacco di 21 istantanee cattive, nome fuori forma → «Giocatore N», n che non cala), i comandi a voce solo dall'ultima valida, il comando con il numero dell'istantanea, rifiutato nel registro, tetto del messaggio, partita di prova; il motore nel DOM finto: istantanea a ogni disegno, comando vecchio o non attivo rifiutato, andata e ritorno JS → Python; le domande standard (passo 5: «a chi tocca?», i punti, chi vince, cosa posso dire) risposte dal codice senza il modello, anche senza il nome nella finestra del gioco, mai l'esito, l'istantanea nei dati del turno (in busta con un nome scritto), un gioco non può dichiararle; contrari nel ciclo: frase più lunga, nessun gioco, domanda in sospeso, altro satellite; il giudice di fase (passo 6) con un modello finto: prompt scritto da Calliope (enum con «nessuno» in testa, valori che non valgono, ordinale), scelta vincolata (fuori elenco, JSON rotto, scaduto = nessuno), nel ciclo «Calliope, apri la terza» → mossa e «Porta 3.», «nessuno» al modello; contrari: senza il nome nella finestra (e con l'interruttore acceso), domanda in sospeso, giudice spento; «gioco anch'io» (passo 4) nel motore con il nome dalla voce o «Giocatore N», il nome scritto toccando la fascia (cifre e doppioni rifiutati), i nomi detti da Calliope (voce sì, scritti dopo i controlli, guardiano con un minore, mai in prova, il server non si fida del motore), «gioco anch'io, sono Pippo» nel ciclo; la ripresa dopo «Riapri» (decisione 7): lo stato intero con l'istantanea, tenuto solo se accompagna l'ultima valida (numero, fase, 16 000 caratteri), restituito all'avvio dello stesso posto, il motore che riparte da lì (anche dall'esito); contrari: ripresa rotta, partita nuova; la partita condivisa con il motore (decisione 6): autorevole e specchio nel DOM finto (le mosse e i nomi dello specchio, niente istantanee né esito da solo, «autorevole» e «specchio»), sul server il primo «pronto» la tiene, lo stato agli specchi, le loro mosse controllate e mandate a chi la tiene, la voce dello specchio, chiuso chi la tiene passa a un altro; contrari: dati personali, nome fermato con un minore, tela com'era"),
    ("prova_gioco_giocatori.py", [], "chi è quale giocatore e «Gira il telefono» (15/10, roadmap 1.4): nel motore (DOM finto) due schermi e due persone (la mossa dallo schermo dell'altro giocatore non parte, un avviso; quella arrivata da un altro schermo rifiutata), uno schermo e due voci (la mossa dalla voce dell'altro rifiutata, il tocco e la voce non riconosciuta per chi è di turno), un ospite senza nome, chi entra a metà (dalla prossima partita, o subito con GIOCO.entra; la stessa voce due volte no); sul server i legami validati e i contrari, chi_muove, il segno della voce e il numero dello schermo nelle mosse, turno_altrui; le domande («Tocca a te.», lo schermo dell'altro, «che giocatore sono?»); nel ciclo «Tocca a Giocatore 1.» senza modello (regola gioco_turno_altrui); la tela orientata (manifesto, fascia «Gira il telefono», detto a Calliope una volta, PC senza fascia, prova di fumo) e la frase a voce una volta per schermo (regola gioco_gira_telefono), anche in prova"),
    # ~60 s: la pagina degli schermi in Edge o Chromium senza finestra (senza si salta)
    ("prova_giochi_pagina.py", [], "giochi nella pagina vera: il riquadro ostile non legge la pagina né il localStorage, niente rete né WebRTC, messaggi falsi rifiutati, cane da guardia (ciclo infinito, navigazione, inondazione), partita condivisa tra due pagine (dal 14/10 con la tela dei segnali), comandi a voce (la mossa nel motore con il nome, il sottoinsieme a runtime, niente fuori elenco, partita di prova), la macchina a stati nel riquadro vero (13/10: preparazione, turno, esito che va avanti da solo), il palco fisso nel browser vero (14/10: ogni modello misurato sullo schermo a 900×800 e a 390×844 in verticale senza difetti, un difetto messo apposta trovato, il tocco su una casella del tris)"),
    # ~10 s: lo stato della partita nella pagina vera (14/10), Edge o Chromium (senza si salta)
    ("prova_gioco_stato_pagina.py", [], "lo stato della partita nella pagina vera (14/10): l'istantanea dal riquadro al server, il comando con un numero vecchio rifiutato dal motore, «gioco anch'io» di Ada, il nome scritto con un tocco vero sulla fascia e la tastiera («Bea», detta da Calliope), ✕ e «Riapri» che riprendono dall'ultima istantanea, la partita condivisa con il motore su due pagine (tocchi veri sullo specchio, la stessa pagina sulle due); chi è quale giocatore su due pagine (15/10) e «Gira il telefono» con un telefono finto"),
    ("prova_contesto_agenti.py", [], "contesto degli agenti (05/10): finestra dal setup, tetti della passata e del ragionamento, risultati lunghi in .calliope, diario del lavoro alle soglie, domanda a metà lavoro"),
    ("prova_estensioni_piano.py", [], "contratto delle capacità, piano di fattibilità, chiedi_permesso, guardia contro il ragionamento a vuoto (agente finto)"),
    ("prova_estensioni_attacchi.py", [], "banco d'attacco delle estensioni: rete interna, indirizzi travestiti, rebinding, slowloris, dati esca, flussi, contaminazione, scarica_esempio"),
    ("prova_sonde_attacchi.py", [], "banco d'attacco delle sonde e del ricollaudo (08/10 notte): un agente finto che ci casca sempre e un'estensione ostile nel ricollaudo; esfiltrazione nell'URL, nei nomi, nel percorso, a pezzi, host non noti, rebinding, reindirizzamenti verso casa e la rete interna, nomi pubblici di casa, quote, injection dalle risposte, letture e azioni negate nel ricollaudo, registro delle uscite senza esche; obiettivo zero passaggi"),
    ("prova_sandbox.py", [], "sandbox in un container con un docker finto: scelta del motore, docker run, kill, capacità"),
    ("prova_agenti_domande.py", [], "agenti: domande a metà lavoro, file della persona all'agente (anche via satellite)"),
    ("prova_analisi_richiesta.py", [], "agenti: analisi della richiesta prima della proposta (chiara, raffinabile, vaga, c'è già, impossibile qui), ripieghi, fonte web, modulo, motivo del tetto in parole"),
    # ~14 s: Ollama finto (anche l'API OpenAI) e Schermi senza server
    ("prova_avanzamento.py", [], "agenti: avanzamento dei lavori sugli schermi in diretta: ritmo, chiave unica, spostamento, visibilità, pausa"),
    ("prova_esecuzione.py", [], "agenti: il programma finito eseguito in diretta sullo schermo (Python e C# con un docker finto; JavaScript acceso a mano dal 17/10, #54: programma .js con argomenti e stdin, contrari pagina web, gioco, spento, senza immagine), «eseguilo con…», «fermalo», tetti"),
    # ~70 s: Calliope vera in un sottoprocesso, satellite con microfono e casse finti in tempo
    # reale; senza voci di Piper o modelli della wake word fa solo la parte breve
    ("prova_satellite.py", [], "satelliti: abbinamento, token, TLS, wake word, streaming, barge-in, riconnessione, latenza"),
    # ~45 s: Calliope vera, due satelliti finti, CAM++ sulle voci di Piper; senza si salta
    ("prova_corsie_satelliti.py", [], "due satelliti insieme con Calliope vera: la conversazione segue la persona, ospiti e altre persone no, risposte in parallelo e coda oltre il limite, doppione"),
    # ~12 s: server e satellite veri su 127.0.0.1, PC finto sul satellite
    ("prova_esecutore.py", [], "esecutore remoto del PC: pc_* via satellite, maniglie, permessi, tempi massimi, consegna dei documenti"),
    ("prova_web.py", [], "ricerca su internet con SearXNG e siti finti: privacy, SSRF, testo non fidato, azioni bloccate, agente"),
    # ~2 s: feed di fantasia su 127.0.0.1, SearXNG finto, Brain a secco
    ("prova_notizie.py", [], "notizie dai feed RSS (13/10): lettore sicuro, date e fusi, pulizia dei titoli con i contrari, gruppi senza modello, scarico condizionato, fatti, tool, minori, ripiego, i fatti restano nel contesto, la quota delle notizie in stato --turni (16/10, #31), tag HTML lunghi tolti col parser, la rete notizie_sommario_html e le voci vecchie ripulite all'apertura (17/10, #133)"),
    # ~1 s, Brain a secco (17/10, issue #132)
    ("prova_notizie_attesa.py", [], "l'attesa delle notizie (17/10, #132): taglio al «; » delle frasi lunghe nello streaming con i contrari (100 caratteri, virgola, «3; 4», virgolette, parentesi, elenco), reti di Brain che non trattengono la risposta intera, frase d'attesa di notizie senza quella dello scarico, prima voce per tool in stato --turni; le reti (ClaimHold, FraseTolta, riferire, guardiano, annuncio di un tool) giudicano la frase fino al pezzo (PR #139)"),
    # ~1 s: web e biblioteca finti, Brain a secco (16/10, issue #101)
    ("prova_ricerca_fuori_tema.py", [], "risultati della ricerca fuori tema (16/10, #101): nessun «tipo notizie» nei testi di brain.py, la riga delle ricerche con il tool notizie (tema e numero del fatto), i risultati fuori tema da non riferire e niente nomi e cifre a memoria, la misura di pertinenza (Orione e la startup 0 su 2, i contrari) e «pertinenti» in web_cerca e biblioteca_cerca, fuori dalla busta"),
    # ~5 s: SearXNG, registro delle immagini e docker finti; lo script con bash di Git se c'è
    ("prova_searxng_aggiorna.py", [], "SearXNG tenuto aggiornato (09/10): prove e giudizio (degradata), registro delle immagini (mai latest), aggiornamento accanto con ritorno indietro, automatico solo a Calliope ferma e senza lavori, modo manuale, blocchi, capacità «degradata», Windows spento, cruscotto con gettoni a due tocchi solo per chi amministra, script con docker finto"),
    ("prova_lavori_criteri.py", [], "criteri del banco dei documenti: titoli, dati in lettere, numeri ricavati"),
    ("prova_agenti_openai.py", [], "agenti con il motore «openai» (vLLM): traduzione, client, lavori, --prova"),
    ("prova_arbitro_vllm.py", [], "arbitro con l'agente su vLLM sulla GPU della voce: stessa_gpu, uno stream per thread, pausa, archivio e ufficio cedevoli"),
    ("prova_arbitro_pausa.py", [], "arbitro con la pausa di vLLM (modalità sviluppo): congela e riprende, ripieghi, scrittore dell'ufficio, ripresa garantita"),
    ("prova_linux.py", [], "DGX Linux simulata: VAD senza torch, capacità, Whisper su server, voce su vLLM"),
    ("prova_linux_import.py", [], "DGX Linux simulata, solo gli import di tutti i moduli (legata a brain, ciclo, main, config)"),
    ("prova_gestore.py", [], "gestore di Linux: installa, aggiorna, verifica, ritorno automatico e a mano"),
    # ~10 s: Ollama finto, riavvio simulato (servizio dei lavori chiuso e ricreato)
    ("prova_lavori_riavvio.py", [], "agenti: lavori che sopravvivono a un riavvio (stato su disco, interrotti annunciati con «Lo rifaccio?», «sì»/«no», sandbox riusata, scadenze, domande in attesa)"),
    ("prova_robustezza.py", [], "robustezza: i guasti dell'analisi del 03/10 non bloccano più Calliope"),
    # ~20 s (Windows PowerShell e curl.exe veri, uv finto); --vera: uv e Python veri (~1 min)
    ("prova_installa_satellite.py", [], "PC nuovo come satellite con un comando: pacchetto, chiave, installa.ps1, aggiornamento e ritorno indietro"),
    ("prova_zim.py", [],"lettore ZIM in puro Python: formato, redirect, xz/zstd, file rovinati"),
    ("prova_biblioteca_indice.py", [], "indice SQLite FTS5: ricerca, validità, annullo, processi"),
    ("prova_arm_comune.py", [], "script di prove/arm/ (18/10, #64): --dati legge i file di quella cartella anche con CALLIOPE_CONFIG e CALLIOPE_CONFIG_LOCALE nell'ambiente, memoria del processo"),
    # ~5 s; se il file ZIM non c'è (non è in git) salta ed esce con 0
    ("prova_biblioteca.py", [], "biblioteca offline: recall@3 e latenza della ricerca"),
]
CON_OLLAMA = [
    ("prova_calcola.py", [], "conti a voce con il modello"),
    ("prova_agenda.py", [], "timer e promemoria con il modello"),
    ("prova_memoria.py", [], "memoria in più sessioni con il modello"),
    ("prova_casa.py", ["1"], "liste, appuntamenti e memoria della casa con il modello"),
    ("prova_pc_ollama.py", ["1"], "PC a voce con il modello (PC finto)"),
    ("prova_documenti_ollama.py", ["1"], "documenti a voce con il modello (cartella temporanea)"),
    ("prova_ufficio_ollama.py", ["1"], "fatture, preventivi, DDT e rubrica a voce con il modello"),
    ("prova_casa_ha_ollama.py", ["1"], "casa a voce con il modello (HA finto e PC finto)"),
    ("prova_stato_ollama.py", ["1"], "stato e installazioni a voce con il modello (server finto)"),
    ("prova_chi_sei_ollama.py", ["1"], "chi sei, novità, versione e «cosa sai fare?» per aree con il modello (09/10): tool e argomenti giusti, niente invenzioni su di sé, contrari"),
    ("prova_personalita_ollama.py", ["1"], "tono di voce chiesto a voce (cambia_voce con tono, per_tutti) e tool dopo il cambio"),
    ("prova_modalita_ollama.py", ["1"], "modalità Star Trek chiesta a voce (cambia_voce con modalita), «non sento i suoni», tool dopo il cambio, i toni restano toni"),
    ("prova_minori_ollama.py", ["--giri", "1"], "minori (05/10): richieste esplicite, aggiramenti, pericolo, compiti senza la soluzione intera (dal 28/10 solo la regola, #279), tool, contrari per gli adulti, con il guardiano"),
    ("prova_schermi_ollama.py", ["1"], "schermi a voce con il modello e il server vero; latenza"),
    ("prova_agenti_ollama.py", ["1"], "delega, stato e annullo a voce con il modello (agente finto)"),
    ("prova_archivio_ollama.py", ["1"], "documenti di casa a voce con il modello (archivio finto)"),
    ("prova_web_ollama.py", ["1"], "ricerca su internet a voce (SearXNG finto): biblioteca o web, iniezione, privacy"),
    ("prova_studio_ollama.py", ["1"], "lo Studio a voce col modello vero (30/10, #284): crea la verifica di giovedì, «cosa devo studiare oggi?», «non ce la faccio oggi», la vista aperta con «spostala a domani», «spiegami la pagina 114», la pagina ostile senza azioni e col dubbio, i compiti guidati senza soluzioni"),
    ("prova_notizie_ollama.py", ["1"], "notizie a voce (13/10, feed di fantasia): «le notizie», «dimmi di più sulla seconda», la testata dai fatti nel contesto, tecnologia e meteo, iniezione in un sommario"),
    ("prova_ricerche_distanza_ollama.py", ["1"], "ricerche a distanza di turni (09/10, giro vero della DGX): «le ultime notizie» senza chiamate fermate, «prima mi parlavi di un festival» → quello di oggi dalla fonte giusta e non quello di ieri, contrario «ieri … Borgo Lieto», «quella cosa delle proteste» in una conversazione aperta; misure: nuova ricerca sulla stessa fonte, archivio non chiamato"),
    ("prova_ricerca_seguito_ollama.py", ["1"], "approfondire dopo una ricerca (09/10, caso vero della DGX: «Approfondiamo le condizioni [del re]» dopo le notizie, senza cercare): nuova ricerca mirata, contrari (chiacchierata, lista della spesa, internet spento); prima e dopo"),
    ("prova_gioco_giudice_ollama.py", ["1"], "giudice di fase dei giochi (14/10, passo 6) sul modello del rilevatore: le 22 frasi del prototipo (le porte da 1 a 5 con la 2 aperta), almeno 20/22 giuste e nessuna mossa su «a chi tocca?» e «quanti punti ho?», tempo mediano"),
    ("prova_rivolta_ollama.py", ["1"], "giudizio «rivolta a Calliope» (09/10, F2 della compagnia) sul modello del rilevatore: 56 frasi di fantasia, almeno 25/27 rivolte e 26/29 non rivolte giuste, tempo mediano"),
    ("prova_brain_ollama.py", ["1"], "tool di base con il modello"),
    ("prova_sfida_esito_ollama.py", ["1"], "l'esito dopo la frase di sfida con il modello vero (16/10, #94): registra_utente riuscito con cosa_fare → la frase del modello detta, mai «Non ho salvato niente» né una rete delle azioni dichiarate; conta anche «deve parlare» detto"),
    ("prova_rinomina_ollama.py", ["1"], "rinominare chi parla: mai al primo turno, solo dopo il «sì»"),
    ("prova_allegati_ollama.py", ["1"], "allegati con gemma4: bolletta, Excel, PDF lungo, Word, archivia, spesa, vocale; banco di sicurezza (istruzioni nei file e negli audio, esci, sì procedi, sfida): zero azioni"),
    ("prova_risultato_pdf_ollama.py", ["1"], "«Fammene un PDF» dopo il risultato di un lavoro con gemma4 (07/10 sera, caso della DGX «Ho metto un pdf.» → pc_cerca_file): lavoro_risultato pdf o word, i contrari col PDF di un file del PC, e (solo misura) il risultato di un lavoro nominato un po' dopo l'annuncio"),
    ("prova_conversazioni_ollama.py", ["1"], "domande cronologiche sulle conversazioni passate con gemma4 (08/10, caso della DGX): «di cosa stavamo parlando?», «prima di questo?», «più indietro ancora» → cronologico=true con l'argomento giusto; contrari per argomento; spiegazioni su sé stessa (misura)"),
    ("prova_argomenti_ollama.py", ["1"], "gli argomenti con gemma4 e eventi: attivo (10/10, § 13, giri della DGX): «ricominciamo» durante l'analisi → argomento nuovo, «ricominciamo da capo» e una cosa nuova → nuovo e lo sviluppo nuovo, «ricominciamo da dove eravamo» e «torniamo a…» → ripreso; contrari (dettaglio dello stesso sviluppo, «sì», l'ora, «e poi?») mai un cambio; «chilometri» senza parola di cambio misurato"),
    ("prova_ricominciamo_ollama.py", ["1"], "la conversazione con gemma4 (09/10, casi veri della DGX): «voglio che ricominciamo da capo» → conversazione_nuova, contrari (il collaudo, da dove eravamo, la lista) senza ricominciare; dopo una pausa «cos'è che ti ho chiesto esattamente?» → gli ultimi scambi, mai la conversazione vecchia; la risposta uguale alla precedente (misura)"),
    ("prova_risultati_ollama.py", ["1"], "il risultato di un lavoro finito con gemma4 (07/10, caso della DGX): «E il risultato?», «leggili e dammi un bel riassunto» subito dopo l'annuncio, senza programma_esegui né lavoro_rispondi"),
    ("prova_estensione_nominata_ollama.py", ["1"], "l'estensione nominata a voce con gemma4 (08/10, caso della DGX): «invoca l'estensione meteo per città su Bergamo» dopo l'approvazione della versione 2 e nella conversazione pulita → est_, mai web_cerca; «che tempo fa?» contato; con e senza i dati del turno"),
    ("prova_meteo_casa_ollama.py", ["1"], "il meteo di casa con gemma4 (09/10): entità meteo di HA esposta → meteo_leggi (adesso e domani), senza entità la città di casa su internet, né entità né città → chiede dove e chi amministra la fa ricordare; contrari Parigi, «da Ettore», «temperatura in sala», una familiare non la salva"),
    ("prova_citta_casa_ollama.py", ["1"], "la città della casa, le estensioni prima di internet e le notizie per tema con gemma4 (09/10, casi della DGX): «che tempo fa?» → l'estensione con la città, senza estensione internet con la città; contrari Parigi e «da Ettore»; «le notizie di sport» esce come «sport»"),
    ("prova_sviluppo_ollama.py", ["1"], "la modalità sviluppo con gemma4 (08/10): la sessione del meteo per città della DGX come iter (richiesta, sì, fuori tema, collaudo con sviluppo_collauda, sviluppo nuovo che non parte, ritorno all'analisi, revisione, attivazione con la sfida), con i dati del turno e con la rete spenta"),
    ("prova_sviluppo_v2_ollama.py", ["1"], "la modalità sviluppo, versione 2, con gemma4 (08/10, il giro vero della DGX): apertura detta, collaudo che non va e «Lo faccio correggere?», «Perché?» → sviluppo_chiedi, la correzione, «Ok, chiuso a long» che non chiude, la correzione finita che riapre al collaudo, attivazione; chiamate come testo e nomi di tool detti"),
    ("prova_sviluppo_giro3_ollama.py", ["1"], "il giro 3 con gemma4 (08/10, DGX del pomeriggio): la modifica di un'estensione che c'è (mai una nuova accanto), «abbiamo due estensioni?» con l'elenco vero, rinomina senza agente, l'esito del collaudo dopo la sfida, «Cerno Maggiore» detto senza «viene dal lavoro di un agente»"),
    ("prova_giro_porte_ollama.py", ["1"], "il giro del 12/10 con gemma4 (le porte magiche): alla revisione «No, farlo continuare con quello che manca.» → completa, «attivala» mai; «Vorrei modificare…» non fa partire niente; «non porta a nulla» → sviluppo_correggi; --prima per il confronto"),
    ("prova_sviluppo_giro6_ollama.py", ["1"], "il giro 6 con gemma4 (08/10, DGX della sera): «Fermo lo sviluppo» con l'agente al lavoro → il lavoro si ferma, «mettiamo in pausa» no; «Sì, rifallo» dopo il lavoro fermato → riparte subito; «prova con Valfiorita e Borgo Alto» → due collaudi, «E invece X?» → un collaudo, «Bosco e Prato è un paese solo» → uno"),
    ("prova_flusso_ripresa_ollama.py", ["1"], "comandi del flusso e ripresa con gemma4 (12/10, lavoro 3): «Riprendiamo lo sviluppo di…» con il lavoro fermato → una domanda sola e «Sì, rifallo.» lo fa ripartire (2 turni); «Am nulla il lavoro.» non ferma né rifà senza una domanda (contrario: «Ferma il lavoro dell'agente» lo ferma); «Chiudi tutti gli sviluppi.» → una domanda con i due titoli e il «sì» li chiude; la modifica con l'agente al lavoro non lo ferma e «lascia com'era» torna al lavoro di prima"),
    ("prova_sviluppo_giro5_ollama.py", ["1"], "il giro 5 con gemma4 (08/10, DGX della sera): «chiedi alla gente come sceglie la città…» con uno sviluppo aperto → sviluppo_chiedi; contrari: «la gente dice che pioverà», nessuno sviluppo aperto"),
    ("prova_sviluppo_giro4_ollama.py", ["1"], "il giro 4 con gemma4 (08/10, DGX della sera): la modifica con i giorni → versione nuova dell'estensione rinominata, il collaudo con citta e giorni, «l'analisi è corretta» a offerta scaduta → il lavoro parte"),
    ("prova_estensione_rimuovi_ollama.py", ["1"], "l'eliminazione di un'estensione con gemma4 (09/10): «rimuovi l'estensione Meteo città» con «Meteocittà» attiva accanto → la domanda sulla disattivata e il «sì» elimina quella; contrari: «disattiva Meteocittà» spegne l'attiva, «elimina Meteocittà» attiva → prima la disattivo?"),
    ("prova_intento_no_ollama.py", ["1"], "il «no» alla proposta con gemma4 (09/10, DGX dell'08/10 sera con nomi di fantasia): dopo «No, non mi interessa che lo registri…» nessuna registrazione né «registro la voce…» nei quattro turni dopo, prima/senza dati/dopo; contrari «Sì, registralo pure» e la richiesta nuova"),
    ("prova_dialogo_ollama.py", ["1"], "lo stato del dialogo in ombra con gemma4 (10/10): con una proposta aperta il modello chiama proposta_rispondi? con quale esito (frasi strane dei registri e del § 3.5 dell'analisi)? accordo con la decisione di oggi, latenza della prima frase con e senza (spento)"),
    ("prova_conferma_unica_ollama.py", ["1"], "una conferma per azione con gemma4: la sequenza della DGX (foto, «creiamo un'estensione…»), doppione, «come la richiamo?»"),
    ("prova_politica_ollama.py", ["1"], "politica dei tool con gemma4: iniezioni da web, allegati, estensioni, archivio, agenti; zero azioni"),
    ("prova_immagini_ollama.py", ["1"], "foto con gemma4: scontrino e turno dopo, spesa dallo scontrino, istruzione nella foto senza azioni, archivia, schermo e webcam"),
    ("prova_cassetto_ollama.py", ["1"], "cassetto dei file con gemma4 (17/10, #58): «il file di ieri», «la bolletta di <giorno>», «le foto della settimana» → allegato_leggi(cassetto); dopo la revisione «tienili tutti», «elimina quello dello scontrino», «tienili ancora una settimana» → cassetto_gestisci; contrari: file arrivato adesso, «archivia questa bolletta», i file di un'altra adulta"),
    ("prova_scritto_ollama.py", ["1"], "la voce che offre lo schermo per i dati da scrivere (ufficio vero, pagina finta)"),
    ("prova_date_ricordi_ollama.py", ["1"], "conversazione vera della DGX del 05/10 18:10: età e date con data_calcola, ricordi solo quando pertinenti, «fermati con l'ordine» senza stati inventati"),
    ("prova_regressione.py", ["1"], "banco di regressione dalle frasi vere (ora, chi sono, casa, annulla…)"),
    ("prova_prompt_conversazione.py", ["1"], "conversazione a più turni (il «che voci hai?» è un limite noto)"),
    ("prova_biblioteca.py", ["--ollama"], "biblioteca end-to-end, con e senza (~5 minuti)"),
]


def keep_alive_della_voce():
    """Il keep_alive del modello della voce di questa installazione (calliope.yaml, il file
    locale, il profilo), o None. Le prove con Ollama lo mandano uguale (04/10): con il 30m
    dei predefiniti di Config() una prova toglieva il «sempre caricato» (-1) del modello
    condiviso con la voce, che poi pagava secondi a ricaricarlo dopo una pausa."""
    import contextlib
    import io
    try:
        from calliope.config import load_config
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cfg = load_config(str(RADICE / "calliope.yaml"))
        return cfg.llm_keep_alive
    except Exception:  # noqa: BLE001 — senza configurazione leggibile: quello delle prove
        return None


# ─────────────────────────── livelli (06/10, P5 dell'analisi complessiva) ───────────────────────────
# Livello 1 (ogni prova non elencata qui sotto): veloce, sempre, in parallelo.
# Livello 2: solo se il commit tocca i file legati (LEGAMI), in parallelo.
# Livello 3: lunghe, browser, Calliope vera, tempo reale: solo con --completo, in serie;
# OBBLIGATORIO prima dell'unione su main.
# Le durate tra parentesi sono del 06/10 sul portatile, nel gruppo parallelo.
LIVELLO_2 = {
    "prova_studio_pagine.py",        # ~35 s (29/10, #281: le foto di fantasia, node e il server)
    "prova_casa_ha.py",              # 13 s
    "prova_sfida_esito.py",          # ~1 s (16/10, #94)
    "prova_risposta_sospeso.py",     # ~1 s (16/10, #98)
    "prova_meteo_casa.py",           # ~3 s (09/10)
    "prova_capacita.py",             # 11 s
    "prova_installa.py",             # 6 s
    "prova_schermi.py",              # 13 s
    "prova_cruscotto.py",            # 3 s
    "prova_scritto.py",              # 5 s
    "prova_agenti.py",               # 55–60 s
    "prova_sandbox.py",              # 10 s
    "prova_agenti_domande.py",       # 9 s
    "prova_analisi_richiesta.py",    # 8 s
    "prova_avanzamento.py",          # 16 s
    "prova_esecuzione.py",           # 17 s
    "prova_agenti_openai.py",        # 9 s
    "prova_arbitro_vllm.py",         # 19 s
    "prova_arbitro_pausa.py",        # 21 s
    "prova_estensioni.py",           # 16 s
    "prova_estensioni_attacchi.py",  # 30 s
    "prova_sonde_attacchi.py",       # ~3 s (08/10 notte)
    "prova_giochi.py",               # 7 s
    "prova_gioco_voce.py",           # ~3 s (11/10, Node per la prova di fumo)
    "prova_gioco_macchina.py",       # ~4 s (13/10, Node)
    "prova_gioco_palco.py",          # ~3 s (14/10, Node)
    "prova_gioco_stato.py",          # ~1 s (14/10, Node)
    "prova_gioco_giocatori.py",      # ~2 s (15/10, Node)
    "prova_agente_guida.py",         # ~10 s (11/10)
    "prova_fasi_agente.py",          # ~18 s (12/10 sera)
    "prova_fasi_agente_2.py",        # ~20 s (13/10)
    "prova_agente_giri_uguali.py",   # ~15 s (18/10, #174: Node e l'Ollama finto)
    "prova_porte_consegna.py",       # ~20 s (19/10, #180: Node e il docker finto)
    "prova_partenza_gioco.py",       # ~20 s (19/10, #186: Node e l'Ollama finto)
    "prova_strumenti_onesti.py",     # ~25 s (19/10, #185: il docker finto)
    "prova_apri_gioco_tappa.py",     # ~15 s (20/10, #192: Node e il docker finto)
    "prova_revisore.py",             # ~50 s (20/10, #190: il docker finto)
    "prova_esito_giochi.py",         # ~10 s (20/10, #197: Node e il docker finto)
    "prova_esecutore.py",            # 12 s
    "prova_telefono_abbina.py",      # 12 s, con il browser (seriale)
    "prova_linux.py",                # 13 s
    "prova_linux_import.py",         # 5 s: solo gli import della DGX simulata (Q7, 06/10)
    "prova_gestore.py",              # 10 s
    "prova_lavori_riavvio.py",       # 10 s
    "prova_robustezza.py",           # 15 s (88 s prima del 06/10: aspettava il guardiano)
    "prova_biblioteca.py",           # 6 s, con i file della biblioteca
    "prova_markdown.py",             # 8 s (07/10)
    "prova_pause.py",                # 9 s (07/10)
    "prova_frase_lunga.py",          # ~6 s (10/10)
    "prova_fine_turno.py",           # ~3 s (14/10)
    "prova_preselezione.py",         # ~4 s (15/10)
    "prova_searxng_aggiorna.py",     # 5 s (09/10)
}
LIVELLO_3 = {
    "prova_schermi_pagina.py", "prova_scritto_pagina.py", "prova_immagini_pagina.py",
    "prova_giochi_pagina.py", "prova_scritto_calliope.py", "prova_telefono_pagina.py",
    "prova_telefono_audio.py", "prova_telefono_schermo.py", "prova_satellite.py",
    "prova_corsie_satelliti.py", "prova_installa_satellite.py", "prova_cruscotto_pagina.py",
    "prova_scheda_intera.py", "prova_markdown_pagina.py", "prova_cassetto_pagina.py",
    "prova_vista_sviluppo_pagina.py", "prova_cronologia_pagina.py",
    "prova_compagnia_pagina.py", "prova_frase_lunga_voce.py", "prova_stanza_voce.py",
    "prova_cdp_orfani.py", "prova_gioco_stato_pagina.py", "prova_fine_turno_voce.py",
    "prova_pc_pagina.py", "prova_studio_pagina_telefono.py", "prova_studio_home_pagina.py",
}
# Mai nel gruppo parallelo, anche quando una prova li sceglie nel livello 2: un browser, un
# tempo reale o tanti processi, che sotto carico falliscono a caso. Tutto il livello 3 è
# seriale.
SERIALI = LIVELLO_3 | {"prova_telefono_abbina.py"}
# Prefisso del percorso cambiato → prove del livello 2 (o 3) da lanciare nel hook. I file
# trasversali (brain.py, config.py, politica.py, tools/registry.py, tools/spec.py,
# tools/builtin.py…) scelgono solo prova_linux_import (gli import di tutto il pacchetto su
# Linux, ~5 s): il resto lo coprono il livello 1 e il livello 3 prima dell'unione. I tool
# d'area (tools/casa.py, tools/agenti.py…) scelgono le prove della loro area (Q7 della seconda
# analisi del 06/10: prima tutto tools/ era trasversale). Un file di prove/ sceglie sé stesso
# e le prove che lo importano (scelte da sole: vedi `_importatori`).
LEGAMI = [
    ("calliope/brain.py", ["prova_linux_import.py"]),
    ("calliope/brain.py", ["prova_sfida_esito.py"]),
    ("calliope/conferme.py", ["prova_sfida_esito.py"]),
    # Le parole dettate attribuite a una pagina o alla stanza (18/10, #169)
    ("calliope/valore.py", ["prova_valore_dettato.py"]),
    ("calliope/stanza/contesto.py", ["prova_valore_dettato.py"]),
    # La risposta al dato chiesto da un tool in sospeso (16/10, #98)
    ("calliope/valore.py", ["prova_risposta_sospeso.py"]),
    ("calliope/politica.py", ["prova_risposta_sospeso.py"]),
    ("calliope/tools/registry.py", ["prova_risposta_sospeso.py"]),
    ("calliope/brain.py", ["prova_risposta_sospeso.py"]),
    ("calliope/ciclo.py", ["prova_linux_import.py"]),
    ("calliope/main.py", ["prova_linux_import.py"]),
    ("calliope/config.py", ["prova_linux_import.py"]),
    ("calliope/tools/dialogo.py", ["prova_dialogo_tool.py"]),
    # Lo stato del dialogo (10/10): il tool di risposta, la macchina in ombra, la corsia veloce
    ("calliope/tools/proposta.py", ["prova_stato_dialogo.py"]),
    ("calliope/tools/argomento.py", ["prova_eventi_attivo.py"]),
    ("calliope/stato_dialogo.py", ["prova_stato_dialogo.py"]),
    ("calliope/risposte.py", ["prova_testo.py", "prova_stato_dialogo.py"]),
    ("calliope/tools/casa.py", ["prova_casa_ha.py", "prova_meteo_casa.py"]),
    ("calliope/luogo.py", ["prova_meteo_casa.py"]),
    ("calliope/tools/agenti.py", ["prova_agenti.py", "prova_agenti_domande.py",
                                 "prova_analisi_richiesta.py",
                                 "prova_esecuzione.py", "prova_avanzamento.py"]),
    ("calliope/tools/schermi.py", ["prova_schermi.py", "prova_scritto.py",
                                  "prova_risultati.py"]),
    ("calliope/tools/estensioni.py", ["prova_estensioni.py", "prova_estensioni_attacchi.py",
                                     "prova_analisi_richiesta.py",
                                     "prova_giochi.py"]),
    ("calliope/tools/pc.py", ["prova_esecutore.py", "prova_documento_proprio.py"]),
    ("calliope/tools/stato.py", ["prova_capacita.py", "prova_installa.py", "prova_novita.py"]),
    ("calliope/novita.py", ["prova_novita.py"]),
    ("CHANGELOG.md", ["prova_novita.py"]),
    ("calliope/tools/ufficio.py", ["prova_scritto.py"]),
    ("calliope/tools/web.py", ["prova_web.py", "prova_estensioni_attacchi.py"]),
    ("calliope/tools/notizie.py", ["prova_notizie.py"]),
    # La quota delle notizie in stato --turni (16/10, issue #31)
    ("calliope/stato.py", ["prova_notizie.py"]),
    # I risultati della ricerca fuori tema (16/10, issue #101)
    ("calliope/pertinenza.py", ["prova_ricerca_fuori_tema.py", "prova_web.py"]),
    ("calliope/tools/web.py", ["prova_ricerca_fuori_tema.py"]),
    ("calliope/tools/builtin.py", ["prova_ricerca_fuori_tema.py"]),
    ("calliope/brain.py", ["prova_ricerca_fuori_tema.py", "prova_web.py"]),
    ("calliope/provenienza.py", ["prova_ricerca_fuori_tema.py"]),
    ("calliope/stato.py", ["prova_ricerca_fuori_tema.py"]),
    ("calliope/tools/conversazioni.py", ["prova_ricerca_fuori_tema.py", "prova_conversazioni.py"]),
    # La conversazione di stanza (13/10, passo 1): il tool, il pacchetto, il lato satellite
    ("calliope/tools/stanza.py", ["prova_stanza.py", "prova_stanza_cerca.py",
                                  "prova_stanza_tenuta.py"]),
    ("calliope/stanza/", ["prova_stanza.py", "prova_stanza_contesto.py", "prova_stanza_storia.py",
                          "prova_stanza_cerca.py", "prova_stanza_eco.py", "prova_stanza_tenuta.py",
                          "prova_stanza_guardia.py", "prova_stanza_conoscenti.py",
                          "prova_stanza_lenta.py", "prova_stanza_attesa.py",
                          "prova_stanza_ricorda.py", "prova_stanza_storpiata.py",
                          "prova_stanza_lenta_blocchi.py"]),
    # La corsia lenta (14/10, passo 3): il beam di Whisper, il piano, lo svuota del banco
    ("calliope/stt.py", ["prova_stanza_lenta.py"]),
    ("calliope/piano.py", ["prova_stanza_lenta.py"]),
    ("calliope/conserva.py", ["prova_stanza_lenta.py", "prova_stanza_lenta_blocchi.py"]),
    ("prove/manuali/banco_stanza_lenta.py", ["prova_stanza_lenta.py",
                                             "prova_stanza_lenta_blocchi.py"]),
    ("prove/manuali/blocchi_stanza.py", ["prova_stanza_lenta_blocchi.py"]),
    ("prove/prova_stanza_lenta.py", ["prova_stanza_lenta_blocchi.py"]),
    # I conoscenti (14/10, decisione 0030): i tool, i tasti della proposta, la scheda
    ("calliope/tools/conoscenti.py", ["prova_stanza_conoscenti.py", "prova_politica.py"]),
    ("calliope/schermi/server.py", ["prova_stanza_conoscenti.py"]),
    ("calliope/schermi/cronologia.py", ["prova_stanza_conoscenti.py"]),
    # Il conoscente nei turni rivolti a Calliope (14/10 sera, rifiniture)
    ("calliope/ciclo.py", ["prova_stanza_conoscenti.py"]),
    ("calliope/brain.py", ["prova_stanza_conoscenti.py"]),
    ("calliope/speaker_id.py", ["prova_stanza_conoscenti.py"]),
    # Passo 6 (14/10): il guardiano a posteriori usa il rilevatore e gli avvisi ai tutori
    ("calliope/guardiano.py", ["prova_stanza_guardia.py"]),
    ("calliope/minori.py", ["prova_stanza_guardia.py"]),
    # Passo 6 (14/10 sera): la modalità gioco chiede a Giochi.in_corso; main collega le due
    ("calliope/schermi/giochi.py", ["prova_stanza_guardia.py"]),
    # Avvisi con la data e l'origine (14/10): minori, cancelli, ciclo, stato, tool dei minori
    ("calliope/minori.py", ["prova_avvisi_data.py"]),
    ("calliope/cancelli.py", ["prova_avvisi_data.py"]),
    ("calliope/ciclo.py", ["prova_avvisi_data.py"]),
    ("calliope/stato.py", ["prova_avvisi_data.py"]),
    ("calliope/tools/minori.py", ["prova_avvisi_data.py"]),
    # Trascrizione e audio degli avvisi di pericolo (14/10 sera)
    ("calliope/avvisi_audio.py", ["prova_avvisi_audio.py"]),
    ("calliope/minori.py", ["prova_avvisi_audio.py"]),
    ("calliope/ciclo.py", ["prova_avvisi_audio.py"]),
    # Da ospite a voce riconosciuta (22/10, issue #171)
    ("calliope/brain.py", ["prova_ospite_riconosciuto.py"]),
    ("calliope/corsie.py", ["prova_ospite_riconosciuto.py"]),
    ("calliope/stanza/", ["prova_ospite_riconosciuto.py"]),
    ("calliope/conversazione.py", ["prova_ospite_riconosciuto.py"]),
    ("calliope/ciclo.py", ["prova_ospite_riconosciuto.py"]),
    # L'ospite dove un minore ha parlato da poco (16/10, issue #102)
    ("calliope/ciclo.py", ["prova_minore_ospite.py"]),
    ("calliope/brain.py", ["prova_minore_ospite.py"]),
    ("calliope/minori.py", ["prova_minore_ospite.py"]),
    ("calliope/speaker_id.py", ["prova_minore_ospite.py"]),
    ("calliope/cancelli.py", ["prova_avvisi_audio.py"]),
    ("calliope/stanza/", ["prova_avvisi_audio.py"]),
    ("calliope/cassetto.py", ["prova_avvisi_audio.py"]),
    ("calliope/conserva.py", ["prova_avvisi_audio.py"]),
    ("calliope/schermi/scarica.py", ["prova_avvisi_audio.py"]),
    # «Scarica l'audio» dopo un riavvio (14/10, rifiniture): la scheda ripresa dalla cronologia
    ("calliope/schermi/cronologia.py", ["prova_avvisi_audio.py"]),
    # Passo 2 (14/10): il blocco nei dati del turno, il giudizio «rivolta» con la stanza
    ("calliope/rivolta.py", ["prova_stanza_contesto.py", "prova_compagnia_passo0.py"]),
    ("calliope/satellite/stanza.py", ["prova_stanza.py", "prova_stanza_eco.py"]),
    ("calliope/notizie/", ["prova_notizie.py"]),
    # Lo Studio (29/10, #280): dati, piano e permessi; la tenuta passa da conserva.py
    ("calliope/studio/", ["prova_studio_piano.py", "prova_conserva.py"]),
    # Le pagine dello Studio (29/10, #281): il controllo del server, l'endpoint e la pagina
    ("calliope/studio/", ["prova_studio_pagine.py"]),
    ("calliope/immagini.py", ["prova_studio_pagine.py"]),
    ("calliope/schermi/server.py", ["prova_studio_pagine.py"]),
    ("calliope/schermi/raccolte.py", ["prova_studio_pagine.py"]),
    ("calliope/schermi/pagina/bordi.js", ["prova_studio_pagine.py", "prova_studio_pagina_telefono.py"]),
    ("calliope/schermi/pagina/studio.js", ["prova_studio_pagina_telefono.py", "prova_studio_home_pagina.py"]),
    ("calliope/tools/studio.py", ["prova_studio_tool.py", "prova_politica.py"]),
    ("calliope/studio/vista.py", ["prova_studio_tool.py"]),
    ("calliope/studio/", ["prova_studio_tool.py"]),
    ("calliope/schermi/tocchi.py", ["prova_studio_tool.py"]),
    ("prove/manuali/studio_immagini.py", ["prova_studio_pagine.py"]),
    ("calliope/conserva.py", ["prova_studio_piano.py"]),
    ("calliope/minori.py", ["prova_studio_piano.py"]),
    ("calliope/tools/archivio.py", ["prova_archivio.py"]),
    ("calliope/tools/immagini.py", ["prova_immagini.py"]),
    ("calliope/tools/allegati.py", ["prova_allegati.py", "prova_cassetto.py"]),
    ("calliope/cassetto.py", ["prova_cassetto.py"]),
    ("calliope/tools/minori.py", ["prova_minori.py", "prova_giochi.py"]),
    # Funzioni spostate dagli esercizi tolti (28/10, #279); le tabelle dismesse tolte
    # all'apertura della memoria (revisione della PR #292)
    ("calliope/memory.py", ["prova_conserva.py"]),
    ("calliope/numeri.py", ["prova_stanza_eco.py"]),
    ("calliope/pronuncia.py", ["prova_pronuncia.py"]),
    ("calliope/speaker_id.py", ["prova_voci_famiglia.py", "prova_conferme.py"]),
    # Il «sì» breve dei tutori (16/10, #108): breve_impronta_ok per dati_conservati (#114:
    # anche dal ciclo vero, con minori.piu_protetto, e da ToolRegistry.call)
    ("calliope/speaker_id.py", ["prova_conserva.py"]),
    ("calliope/ciclo.py", ["prova_conserva.py"]),
    ("calliope/minori.py", ["prova_conserva.py"]),
    ("calliope/tools/registry.py", ["prova_conserva.py"]),
    # Impronte per satellite (15/10): il modulo, il registro, il ciclo, i conoscenti, conserva
    ("calliope/impronte_satellite.py", ["prova_impronte_satellite.py", "prova_voci_famiglia.py"]),
    ("calliope/speaker_id.py", ["prova_impronte_satellite.py"]),
    ("calliope/ciclo.py", ["prova_impronte_satellite.py"]),
    ("calliope/stanza/conoscenti.py", ["prova_impronte_satellite.py"]),
    ("calliope/conserva.py", ["prova_impronte_satellite.py"]),
    ("calliope/conferme.py", ["prova_voci_famiglia.py", "prova_conferme.py"]),
    ("calliope/minori.py", ["prova_voci_famiglia.py", "prova_minori.py"]),
    ("calliope/tools/documenti.py", ["prova_documenti.py", "prova_lavori_criteri.py"]),
    ("calliope/tools/conversazioni.py", ["prova_conversazioni.py"]),
    ("calliope/ripetizione.py", ["prova_conversazioni.py", "prova_stanza_storpiata.py"]),
    ("calliope/allucinazioni.py", ["prova_testo.py"]),
    ("calliope/sigle.py", ["prova_testo.py"]),
    ("calliope/casa/", ["prova_casa_ha.py", "prova_meteo_casa.py"]),
    ("calliope/capacita.py", ["prova_capacita.py", "prova_novita.py"]),
    ("calliope/stato.py", ["prova_capacita.py", "prova_piano.py"]),
    ("calliope/macchina.py", ["prova_capacita.py", "prova_piano.py", "prova_stanza_lenta.py"]),
    ("calliope/modelli.py", ["prova_piano.py", "prova_stanza_lenta.py"]),
    ("calliope/piano.py", ["prova_piano.py"]),
    ("calliope/installa/", ["prova_installa.py", "prova_capacita.py"]),
    ("calliope/latenza.py", ["prova_cruscotto.py"]),
    # Il registro degli eventi (10/10): le prove sono del livello 1; qui quelle che lo usano
    ("calliope/eventi/", ["prova_linux_import.py"]),
    # L'uscita unica (10/10, passo 2): le frasi fuori turno sul satellite e la voce vera
    ("calliope/eventi/uscita.py", ["prova_giro3.py", "prova_giro4.py", "prova_robustezza.py"]),
    # La cronologia delle schede per persona e la scheda «Conversazione» (08/10)
    ("calliope/schermi/", ["prova_cronologia_schede.py", "prova_conversazione_schede.py"]),
    ("calliope/conversazioni.py", ["prova_cronologia_schede.py", "prova_conversazioni.py",
                                   "prova_conserva.py", "prova_conversazione_schede.py"]),
    ("calliope/conversazione.py", ["prova_cronologia_schede.py", "prova_conversazioni.py",
                                   "prova_conversazione_schede.py"]),
    ("calliope/brain.py", ["prova_conversazione_schede.py"]),
    ("calliope/tools/schermi.py", ["prova_cronologia_schede.py"]),
    ("calliope/schermi/", ["prova_schermi.py", "prova_cruscotto.py", "prova_scritto.py", "prova_giochi.py",
                           "prova_telefono_abbina.py",
                           "prova_immagini.py", "prova_allegati.py", "prova_cassetto.py"]),
    ("calliope/ufficio/", ["prova_scritto.py"]),
    ("calliope/immagini.py", ["prova_immagini.py"]),
    ("calliope/dispositivo.py", ["prova_dispositivo.py", "prova_telefono_consapevole.py"]),
    ("calliope/brain.py", ["prova_dispositivo.py"]),
    ("calliope/ciclo.py", ["prova_dispositivo.py"]),
    ("calliope/pc/remoto.py", ["prova_dispositivo.py"]),
    ("calliope/allegati.py", ["prova_allegati.py", "prova_cassetto.py"]),
    ("calliope/agenti/", ["prova_agenti.py", "prova_sandbox.py", "prova_agenti_domande.py",
                          "prova_avanzamento.py", "prova_esecuzione.py",
                          "prova_agenti_openai.py", "prova_arbitro_vllm.py",
                          "prova_arbitro_pausa.py", "prova_contesto_agenti.py",
                          "prova_estensioni_piano.py", "prova_analisi_richiesta.py",
                          "prova_agente_guida.py"]),
    ("calliope/estensioni/",
 ["prova_estensioni.py", "prova_estensioni_piano.py",
                              "prova_estensioni_attacchi.py", "prova_giochi.py",
                              "prova_agente_guida.py"]),
    ("calliope/guardrail.py", ["prova_estensioni.py", "prova_estensioni_attacchi.py"]),
    ("calliope/web/", ["prova_web.py", "prova_estensioni_attacchi.py",
                       "prova_searxng_aggiorna.py"]),
    ("setup/linux/motore/searxng.sh", ["prova_searxng_aggiorna.py"]),
    ("calliope/schermi/cruscotto.py", ["prova_searxng_aggiorna.py"]),
    ("calliope/capacita.py", ["prova_searxng_aggiorna.py"]),
    ("calliope/archivio/", ["prova_archivio.py"]),
    ("calliope/documenti/", ["prova_lavori_criteri.py", "prova_markdown.py"]),
    # Il Markdown dell'agente, il lettore e «Scarica» (07/10)
    ("calliope/schermi/", ["prova_markdown.py"]),
    ("calliope/agenti/", ["prova_markdown.py"]),
    ("calliope/tools/agenti.py", ["prova_markdown.py"]),
    ("calliope/satellite/", ["prova_esecutore.py", "prova_telefono_abbina.py"]),
    ("calliope/pc/", ["prova_esecutore.py", "prova_documento_proprio.py"]),
    ("calliope/vad.py", ["prova_linux.py"]),
    ("calliope/stt.py", ["prova_linux.py", "prova_robustezza.py", "prova_frase_lunga.py"]),
    ("setup/linux/", ["prova_linux.py", "prova_gestore.py"]),
    ("prove/e2e/", ["prova_e2e_copioni.py"]),
    # La modalità sviluppo (08/10), e la sua versione 2 (tappe nel ciclo dell'agente, nomi)
    ("calliope/sviluppo.py", ["prova_sviluppo.py", "prova_sviluppo_v2.py"]),
    # Il giro 3 (08/10): porta, traccia di rete, provenienza, consenso, rinomina
    ("calliope/tools/agenti.py", ["prova_sviluppo_giro4.py"]),
    ("calliope/sviluppo.py", ["prova_sviluppo_giro3.py", "prova_sviluppo_giro4.py"]),
    ("calliope/tools/sviluppo.py", ["prova_sviluppo_giro3.py", "prova_sviluppo_giro4.py"]),
    ("calliope/tools/estensioni.py", ["prova_sviluppo_giro3.py", "prova_sviluppo_giro4.py", "prova_estensioni_versioni.py"]),
    ("calliope/estensioni/", ["prova_sviluppo_giro3.py", "prova_sviluppo_giro4.py"]),
    ("calliope/web/pagina.py", ["prova_sviluppo_giro3.py"]),
    ("calliope/web/rete.py", ["prova_sviluppo_giro3.py"]),
    ("calliope/politica.py", ["prova_sviluppo_giro3.py"]),
    ("calliope/provenienza.py", ["prova_sviluppo_giro3.py"]),
    ("calliope/valore.py", ["prova_sviluppo_giro3.py"]),
    ("calliope/brain.py", ["prova_sviluppo_giro3.py"]),
    # Il giro 5 (08/10 sera): doppia codifica, collaudi con argomenti, analisi, giro a vuoto
    ("calliope/sviluppo.py", ["prova_sviluppo_giro5.py"]),
    # Il giro 6 (08/10 sera): ferma e sospendi, rifai, un collaudo per valore
    ("calliope/sviluppo.py", ["prova_sviluppo_giro6.py"]),
    ("calliope/tools/sviluppo.py", ["prova_sviluppo_giro6.py"]),
    ("calliope/politica.py", ["prova_sviluppo_giro6.py"]),
    ("calliope/valore.py", ["prova_sviluppo_giro6.py"]),
    # Il giro del 10/10 mattina: un programma diverso non conferma, fasi dichiarate
    ("calliope/sviluppo.py", ["prova_giro_ombra.py"]),
    ("calliope/tools/sviluppo.py", ["prova_giro_ombra.py"]),
    ("calliope/tools/agenti.py", ["prova_giro_ombra.py"]),
    ("calliope/tools/estensioni.py", ["prova_giro_ombra.py"]),
    ("calliope/brain.py", ["prova_giro_ombra.py"]),
    # Il secondo giro del 10/10: chiudere lo sviluppo, titoli, storia come detta
    ("calliope/tools/sviluppo.py", ["prova_giro_chiusura.py"]),
    ("calliope/brain.py", ["prova_giro_chiusura.py"]),
    ("calliope/ciclo.py", ["prova_giro_chiusura.py"]),
    ("calliope/agenti/servizio.py", ["prova_giro_chiusura.py"]),
    # Il terzo giro del 10/10: altro compito nell'analisi, conferma senza parole, titoli,
    # chiudi tutti, «ricominciamo» sul satellite
    ("calliope/sviluppo.py", ["prova_giro3.py"]),
    ("calliope/tools/sviluppo.py", ["prova_giro3.py"]),
    ("calliope/tools/estensioni.py", ["prova_giro3.py"]),
    ("calliope/tools/registry.py", ["prova_giro3.py"]),
    # Il giro della DGX del 10/10 pomeriggio
    ("calliope/riferire.py", ["prova_giro_pomeriggio.py"]),
    ("calliope/tools/sviluppo.py", ["prova_giro_pomeriggio.py"]),
    ("calliope/sviluppo.py", ["prova_giro_pomeriggio.py"]),
    ("calliope/tools/registry.py", ["prova_giro_pomeriggio.py"]),
    ("calliope/tools/conversazioni.py", ["prova_giro_pomeriggio.py"]),
    ("calliope/agenti/richiesta.py", ["prova_giro_pomeriggio.py"]),
    # Il giro della DGX del 10/10 sera: il gioco con tipo estensione, il titolo
    ("calliope/tools/sviluppo.py", ["prova_giro_sera_gioco.py"]),
    ("calliope/tools/estensioni.py", ["prova_giro_sera_gioco.py"]),
    ("calliope/sviluppo.py", ["prova_giro_sera_gioco.py"]),
    ("calliope/agenti/richiesta.py", ["prova_giro_sera_gioco.py"]),
    ("calliope/agenti/servizio.py", ["prova_giro_sera_gioco.py"]),
    # Il giro della DGX dell'11/10: il collaudo di un gioco, correggi da fermo, tappa,
    # motivo dell'arresto, titolo, provenienza del titolo
    ("calliope/tools/sviluppo.py", ["prova_giro_halloween.py"]),
    ("calliope/sviluppo.py", ["prova_giro_halloween.py"]),
    ("calliope/agenti/servizio.py", ["prova_giro_halloween.py"]),
    ("calliope/schermi/giochi.py", ["prova_giro_halloween.py"]),
    # I comandi a voce dei giochi (11/10): regola sul testo, server, ciclo, riquadro, fumo
    ("calliope/gioco_voce.py", ["prova_testo.py", "prova_gioco_voce.py"]),
    ("calliope/schermi/giochi.py", ["prova_gioco_voce.py"]),
    ("calliope/estensioni/scheda.py", ["prova_gioco_voce.py"]),
    ("calliope/ciclo.py", ["prova_gioco_voce.py"]),
    ("calliope/agenti/fumo_js.mjs", ["prova_gioco_voce.py"]),
    ("calliope/agenti/test_js.mjs", ["prova_gioco_voce.py"]),
    ("calliope/tools/schermi.py", ["prova_gioco_voce.py"]),
    ("calliope/estensioni/servizio.py", ["prova_giro_halloween.py"]),
    ("calliope/valore.py", ["prova_giro_halloween.py"]),
    # La macchina a stati dei giochi (13/10)
    ("calliope/estensioni/macchina.py", ["prova_gioco_macchina.py", "prova_gioco_voce.py"]),
    ("calliope/estensioni/motore_gioco.js", ["prova_gioco_macchina.py"]),
    ("calliope/estensioni/scheda.py", ["prova_gioco_macchina.py"]),
    ("calliope/agenti/fumo_js.mjs", ["prova_gioco_macchina.py"]),
    ("calliope/agenti/test_js.mjs", ["prova_gioco_macchina.py"]),
    ("calliope/agenti/sandbox.py", ["prova_gioco_macchina.py"]),
    ("calliope/gioco_voce.py", ["prova_gioco_macchina.py"]),
    ("prove/giochi/porte_fasi/", ["prova_gioco_macchina.py"]),
    # Il palco fisso e i giochi vecchi tolti (14/10)
    ("calliope/estensioni/motore_gioco.js", ["prova_gioco_palco.py", "prova_gioco_voce.py",
                                             "prova_giochi.py"]),
    ("calliope/estensioni/macchina.py", ["prova_gioco_palco.py", "prova_giochi.py"]),
    ("calliope/estensioni/scheda.py", ["prova_gioco_palco.py", "prova_giochi.py"]),
    ("calliope/agenti/fumo_js.mjs", ["prova_gioco_palco.py", "prova_agente_guida.py",
                                     "prova_fasi_agente.py"]),
    ("calliope/agenti/test_js.mjs", ["prova_gioco_palco.py"]),
    ("calliope/schermi/giochi.py", ["prova_gioco_palco.py", "prova_giochi.py"]),
    ("prove/giochi/", ["prova_giochi.py", "prova_gioco_voce.py", "prova_gioco_macchina.py",
                       "prova_gioco_palco.py"]),
    ("calliope/agenti/accettazione.py", ["prova_gioco_macchina.py"]),
    ("calliope/agenti/servizio.py", ["prova_gioco_macchina.py"]),
    ("calliope/agenti/scheletri.py", ["prova_gioco_macchina.py"]),
    ("calliope/estensioni/contratto.py", ["prova_gioco_macchina.py", "prova_agente_guida.py"]),
    ("calliope/estensioni/prompt.py", ["prova_giochi.py", "prova_agente_guida.py"]),
    # Revisione onesta e tappe (11/10)
    ("calliope/requisiti.py", ["prova_revisione_onesta.py"]),
    ("calliope/sviluppo.py", ["prova_revisione_onesta.py"]),
    ("calliope/tools/sviluppo.py", ["prova_revisione_onesta.py"]),
    # La specifica viva (12/10)
    ("calliope/sviluppo.py", ["prova_giro_porte.py"]),
    ("calliope/tools/sviluppo.py", ["prova_giro_porte.py"]),
    ("calliope/brain.py", ["prova_giro_porte.py"]),
    ("calliope/stato_dialogo.py", ["prova_giro_porte.py"]),
    ("calliope/estensioni/scheda.py", ["prova_giro_porte.py"]),
    ("calliope/agenti/ciclo.py", ["prova_giro_porte.py"]),
    # Il flusso dell'agente a fasi, parte 1 (12/10 sera)
    ("calliope/agenti/", ["prova_fasi_agente.py"]),
    # Il flusso dell'agente a fasi, parte 2 (13/10)
    ("calliope/agenti/", ["prova_fasi_agente_2.py"]),
    ("calliope/estensioni/prompt.py", ["prova_fasi_agente_2.py"]),
    ("calliope/requisiti.py", ["prova_fasi_agente_2.py"]),
    ("calliope/sviluppo.py", ["prova_fasi_agente_2.py"]),
    ("calliope/sviluppo.py", ["prova_fasi_agente.py"]),
    ("calliope/tools/sviluppo.py", ["prova_fasi_agente.py"]),
    ("calliope/agenti/scheletri.py", ["prova_agente_guida.py"]),
    ("calliope/requisiti.py", ["prova_specifica_viva.py"]),
    ("calliope/sviluppo.py", ["prova_specifica_viva.py"]),
    ("calliope/tools/sviluppo.py", ["prova_specifica_viva.py"]),
    ("calliope/tools/estensioni.py", ["prova_specifica_viva.py"]),
    ("calliope/tools/agenti.py", ["prova_specifica_viva.py"]),
    ("calliope/agenti/richiesta.py", ["prova_specifica_viva.py"]),
    # Comandi del flusso e ripresa (12/10, lavoro 3)
    ("calliope/sviluppo.py", ["prova_flusso_ripresa.py"]),
    ("calliope/tools/sviluppo.py", ["prova_flusso_ripresa.py"]),
    ("calliope/tools/estensioni.py", ["prova_flusso_ripresa.py"]),
    ("calliope/tools/registry.py", ["prova_flusso_ripresa.py"]),
    ("calliope/tools/conversazioni.py", ["prova_flusso_ripresa.py"]),
    ("calliope/politica.py", ["prova_flusso_ripresa.py"]),
    ("calliope/agenti/servizio.py", ["prova_flusso_ripresa.py"]),
    ("calliope/agenti/richiesta.py", ["prova_flusso_ripresa.py"]),
    ("calliope/ciclo.py", ["prova_flusso_ripresa.py"]),
    ("calliope/politica.py", ["prova_giro3.py"]),
    ("calliope/risposte.py", ["prova_giro3.py"]),
    ("calliope/brain.py", ["prova_giro3.py"]),
    ("calliope/ciclo.py", ["prova_giro3.py"]),
    ("calliope/agenti/servizio.py", ["prova_giro3.py"]),
    # Il quarto giro del 10/10: frasi fuori turno sul satellite, il cambio all'analisi,
    # l'elenco degli sviluppi, la sola punteggiatura negli argomenti e nella risposta
    ("calliope/ciclo.py", ["prova_giro4.py"]),
    ("calliope/tts.py", ["prova_giro4.py"]),
    ("calliope/satellite/client.py", ["prova_giro4.py"]),
    ("calliope/sviluppo.py", ["prova_giro4.py"]),
    ("calliope/tools/sviluppo.py", ["prova_giro4.py"]),
    ("calliope/tools/agenti.py", ["prova_giro4.py"]),
    ("calliope/tools/dialogo.py", ["prova_giro4.py"]),
    ("calliope/brain.py", ["prova_giro4.py"]),
    ("prove/satellite_finto.py", ["prova_giro4.py"]),
    # La diagnosi dei collaudi (08/10 notte): confronto ed esempi veri
    ("calliope/sviluppo.py", ["prova_diagnosi_collaudi.py"]),
    ("calliope/tools/sviluppo.py", ["prova_diagnosi_collaudi.py"]),
    ("calliope/estensioni/", ["prova_diagnosi_collaudi.py"]),
    # Le sonde dell'agente e il ricollaudo (08/10 notte): il banco d'attacco
    ("calliope/sonde.py", ["prova_sonde_attacchi.py"]),
    ("calliope/sviluppo.py", ["prova_sonde_attacchi.py"]),
    ("calliope/estensioni/", ["prova_sonde_attacchi.py"]),
    ("calliope/web/", ["prova_sonde_attacchi.py"]),
    ("calliope/agenti/ciclo.py", ["prova_sonde_attacchi.py"]),
    ("calliope/agenti/servizio.py", ["prova_sonde_attacchi.py"]),
    ("calliope/guardrail.py", ["prova_sonde_attacchi.py"]),
    ("calliope/provenienza.py", ["prova_sonde_attacchi.py"]),
    ("calliope/tools/sviluppo.py", ["prova_sviluppo_giro5.py"]),
    ("calliope/estensioni/", ["prova_sviluppo_giro5.py"]),
    ("calliope/web/pagina.py", ["prova_sviluppo_giro5.py"]),
    ("calliope/web/rete.py", ["prova_sviluppo_giro5.py"]),
    ("calliope/politica.py", ["prova_sviluppo_giro5.py"]),
    ("calliope/agenti/", ["prova_sviluppo_giro5.py"]),
    ("calliope/tools/sviluppo.py", ["prova_sviluppo.py", "prova_sviluppo_v2.py",
                                   "prova_estensioni.py", "prova_agenti.py"]),
    ("calliope/agenti/", ["prova_sviluppo_v2.py"]),
    ("calliope/tools/agenti.py", ["prova_sviluppo_v2.py"]),
    ("calliope/tools/registry.py", ["prova_sviluppo_v2.py"]),
    # L'agente dei giochi che gira a vuoto (18/10, #174)
    ("calliope/agenti/", ["prova_agente_giri_uguali.py"]),
    ("calliope/estensioni/contratto.py", ["prova_agente_giri_uguali.py"]),
    ("calliope/sviluppo.py", ["prova_agente_giri_uguali.py"]),
    ("calliope/tools/agenti.py", ["prova_agente_giri_uguali.py"]),
    ("calliope/tools/sviluppo.py", ["prova_agente_giri_uguali.py"]),
    ("calliope/requisiti.py", ["prova_agente_giri_uguali.py"]),
    # Le porte oneste della consegna (19/10, #180)
    ("calliope/agenti/", ["prova_porte_consegna.py"]),
    ("calliope/tools/dialogo.py", ["prova_porte_consegna.py"]),
    # Il contratto e la partenza dei giochi (19/10, #186)
    ("calliope/agenti/", ["prova_partenza_gioco.py"]),
    ("calliope/estensioni/", ["prova_partenza_gioco.py"]),
    ("calliope/estensioni/prompt.py", ["prova_porte_consegna.py"]),
    ("calliope/estensioni/servizio.py", ["prova_porte_consegna.py"]),
    ("calliope/sviluppo.py", ["prova_porte_consegna.py"]),
    # Gli strumenti onesti dell'agente (19/10, #185)
    ("calliope/agenti/", ["prova_strumenti_onesti.py"]),
    ("calliope/tools/dialogo.py", ["prova_strumenti_onesti.py"]),
    # apriGioco c'è già, la tappa consegnabile, il segnaposto (20/10, #192)
    ("calliope/agenti/", ["prova_apri_gioco_tappa.py"]),
    ("calliope/estensioni/contratto.py", ["prova_apri_gioco_tappa.py"]),
    ("calliope/tools/sviluppo.py", ["prova_apri_gioco_tappa.py"]),
    ("calliope/sviluppo.py", ["prova_apri_gioco_tappa.py"]),
    ("calliope/testi.py", ["prova_apri_gioco_tappa.py"]),
    # Il revisore a contesto pulito nel ciclo (20/10, #190)
    ("calliope/agenti/", ["prova_revisore.py"]),
    ("calliope/estensioni/servizio.py", ["prova_revisore.py"]),
    ("calliope/requisiti.py", ["prova_revisore.py"]),
    ("prove/ollama_finto.py", ["prova_revisore.py"]),
    # L'esito dei giochi e gli esempi del tris (20/10, #197)
    ("calliope/agenti/", ["prova_esito_giochi.py"]),
    ("calliope/estensioni/contratto.py", ["prova_esito_giochi.py"]),
    ("calliope/requisiti.py", ["prova_esito_giochi.py"]),
    ("calliope/estensioni/motore_gioco.js", ["prova_esito_giochi.py"]),
    ("calliope/tools/sviluppo.py", ["prova_esito_giochi.py"]),
    ("prove/giochi/", ["prova_esito_giochi.py"]),
    # I lavori che sopravvivono a un riavvio (06/10)
    ("calliope/agenti/", ["prova_lavori_riavvio.py"]),
    ("calliope/tools/agenti.py", ["prova_lavori_riavvio.py"]),
    ("calliope/main.py", ["prova_robustezza.py"]),
    ("calliope/ciclo.py", ["prova_robustezza.py"]),
    ("calliope/tts.py", ["prova_robustezza.py"]),
    ("calliope/audio.py", ["prova_robustezza.py"]),
    ("calliope/persistenza.py", ["prova_robustezza.py"]),
    ("calliope/turnlog.py", ["prova_robustezza.py"]),
    # La conservazione dei dati e la metrica della scelta dei tool (12/10): livello 1; qui i
    # tool d'area
    ("calliope/tools/conserva.py", ["prova_conserva.py", "prova_stanza_tenuta.py"]),
    ("calliope/conserva.py", ["prova_conserva.py", "prova_stanza_tenuta.py",
                              "prova_stanza_conoscenti.py", "prova_conoscenti_conserva.py"]),
    # La valutazione (18/10, #173, decisione 0032): livello 1; qui i moduli delle sue scritture
    ("calliope/stanza/banco.py", ["prova_conserva_valutazione.py"]),
    ("calliope/stanza/tenuta.py", ["prova_conserva_valutazione.py"]),
    # La conservazione dei conoscenti (14/10 sera, decisione 0030 aggiornata)
    ("calliope/turnlog.py", ["prova_conoscenti_conserva.py"]),
    ("calliope/conversazioni.py", ["prova_conoscenti_conserva.py"]),
    ("calliope/tools/conversazioni.py", ["prova_conoscenti_conserva.py"]),
    ("calliope/scelta_tool.py", ["prova_scelta_tool.py"]),
    # Il rapporto degli scatti delle reti (15/10, E11): l'inventario rete → regole segue Brain
    ("calliope/reti_scatti.py", ["prova_reti_scatti.py"]),
    ("calliope/brain.py", ["prova_reti_scatti.py"]),
    ("calliope/ciclo.py", ["prova_reti_scatti.py"]),
    ("calliope/config.py", ["prova_reti_scatti.py"]),
    ("calliope/turnlog.py", ["prova_reti_scatti.py"]),
    ("calliope/stato.py", ["prova_reti_scatti.py"]),
    ("calliope/si_breve.py", ["prova_si_breve.py"]),
    ("calliope/zim.py", ["prova_zim.py", "prova_biblioteca.py"]),
    ("calliope/biblioteca", ["prova_biblioteca_indice.py", "prova_biblioteca.py"]),
    ("prove/arm/", ["prova_arm_comune.py"]),
    # Pause e fine del turno (07/10, solo misura): dove sta il VAD e il registro
    ("calliope/pause.py", ["prova_pause.py", "prova_frase_lunga.py", "prova_fine_turno.py"]),
    ("calliope/audio.py", ["prova_pause.py", "prova_frase_lunga.py", "prova_fine_turno.py"]),
    ("calliope/ciclo.py", ["prova_pause.py", "prova_frase_lunga.py", "prova_fine_turno.py"]),
    ("calliope/stato.py", ["prova_pause.py", "prova_fine_turno.py"]),
    ("calliope/satellite/", ["prova_pause.py", "prova_frase_lunga.py", "prova_fine_turno.py"]),
    ("calliope/system1/", ["prova_fine_turno.py", "prova_preselezione.py"]),
    # La preselezione dei tool (15/10): le descrizioni dei tool sono i suoi prototipi. Dal 16/10
    # (#25) il richiamo sul banco è un avviso, ma la copertura dei tool, il nucleo di serie, le
    # frasi a «nucleo» e i casi a «tutti» dipendono ancora dal registro dei tool; in più il
    # controllo che i ganci non tornino nel ciclo, in main, in stato e nella configurazione
    ("calliope/tools/", ["prova_preselezione.py"]),
    ("calliope/ciclo.py", ["prova_preselezione.py"]),
    ("calliope/config.py", ["prova_preselezione.py"]),
    # I campi a modi (17/10, #83): validatori, controllo dei campi nuovi, Cancelli
    ("calliope/config.py", ["prova_config_modi.py"]),
    ("calliope/cancelli.py", ["prova_config_modi.py"]),
    ("prove/manuali/preselezione_dgx.py", ["prova_preselezione.py"]),
    ("calliope/stato.py", ["prova_preselezione.py"]),
    ("calliope/main.py", ["prova_preselezione.py"]),
    ("prove/banco_preselezione.py", ["prova_preselezione.py"]),
    ("calliope/installa/catalogo.py", ["prova_fine_turno.py"]),
    ("calliope/schermi/telefono.py", ["prova_pause.py"]),
    ("calliope/schermi/pagina/telefono/", ["prova_pause.py", "prova_frase_lunga.py"]),
    ("pyproject.toml", ["prova_linux.py", "prova_gestore.py"]),
    ("uv.lock", ["prova_linux.py"]),
    ('calliope/estensioni/macchina.py', ["prova_gioco_stato.py"]),
    ('calliope/estensioni/motore_gioco.js', ["prova_gioco_stato.py"]),
    ('calliope/schermi/giochi.py', ["prova_gioco_stato.py"]),
    ('calliope/agenti/fumo_js.mjs', ["prova_gioco_stato.py"]),
    ('calliope/estensioni/scheda.py', ["prova_gioco_stato.py"]),
    ("calliope/gioco_stato.py", ["prova_gioco_stato.py", "prova_testo.py"]),
    ("calliope/ciclo.py", ["prova_gioco_stato.py"]),
    ("calliope/gioco_giudice.py", ["prova_gioco_stato.py"]),
    # Chi è quale giocatore e «Gira il telefono» (15/10, roadmap 1.4)
    ("calliope/estensioni/motore_gioco.js", ["prova_gioco_giocatori.py"]),
    ("calliope/estensioni/macchina.py", ["prova_gioco_giocatori.py"]),
    ("calliope/schermi/giochi.py", ["prova_gioco_giocatori.py"]),
    ("calliope/agenti/fumo_js.mjs", ["prova_gioco_giocatori.py"]),
    ("calliope/gioco_stato.py", ["prova_gioco_giocatori.py"]),
    ("calliope/ciclo.py", ["prova_gioco_giocatori.py"]),
    ("calliope/tools/schermi.py", ["prova_gioco_giocatori.py"]),
    ("calliope/estensioni/scheda.py", ["prova_gioco_giocatori.py"]),
    # L'arbitro della memoria in ombra (15/10, passo 2): i quattro posti con la «voce ferma» e
    # le richieste di carico, il registro, calliope stato --memoria --storia
    ("calliope/arbitro_ombra.py", ["prova_arbitro_memoria.py"]),
    ("calliope/stanza/guardia.py", ["prova_arbitro_memoria.py"]),
    ("calliope/stanza/lenta.py", ["prova_arbitro_memoria.py"]),
    ("calliope/stanza/misure.py", ["prova_arbitro_memoria.py"]),
    ("calliope/conversazioni.py", ["prova_arbitro_memoria.py"]),
    ("calliope/agenti/servizio.py", ["prova_arbitro_memoria.py"]),
    ("calliope/agenti/arbitro.py", ["prova_arbitro_memoria.py"]),
    ("calliope/stato.py", ["prova_arbitro_memoria.py"]),
    ("calliope/main.py", ["prova_arbitro_memoria.py"]),
    # La «voce ferma» liberata a fine turno e la tenuta massima (18/10, #157)
    ("calliope/arbitro_memoria.py", ["prova_arbitro_quiete.py"]),
    ("calliope/arbitro_ombra.py", ["prova_arbitro_quiete.py"]),
    ("calliope/ciclo.py", ["prova_arbitro_quiete.py"]),
    ("calliope/main.py", ["prova_arbitro_quiete.py"]),
    ("calliope/satellite/server.py", ["prova_arbitro_quiete.py"]),
]
# Prove che il runner non lancia, con il perché (06/10, Q7): prova_runner controlla che ogni
# prove/prova_*.py sia in A_SECCO, in CON_OLLAMA o qui. Una prova nuova dimenticata fallisce.
MANUALI = {
    "prova_aec.py": "fattibilità della cancellazione dell'eco: sottocomandi con audio vero",
    "prova_confronto.py": "misura storica con Ollama (reasoning_effort e tool)",
    "prova_ctx.py": "misura storica con Ollama (token del prompt e num_ctx)",
    "prova_debug.py": "ispezione a mano di schemi, prompt e risposta grezza di Ollama",
    "prova_estensioni_agente.py": "sulla DGX, con l'agente vero e il container vero",
    "prova_estensioni_ollama.py": "con il modello vero della voce, lunga: a mano dopo le "
                                  "modifiche alle estensioni",
    "prova_latency.py": "misura storica con Ollama (thinking acceso contro spento)",
    "prova_lavori.py": "banco degli agenti: decine di minuti con il modello vero (--dgx)",
    "prova_llm.py": "misura storica del ciclo dei tool contro Ollama",
    "prova_native.py": "misura storica dell'API nativa di Ollama",
    "prova_native2.py": "misura storica dell'API nativa di Ollama (think)",
    "prova_native3.py": "misura storica dell'API nativa di Ollama (ciclo completo)",
    "prova_numctx.py": "misura storica di num_ctx sull'endpoint OpenAI (con ollama ps)",
    "prova_ollama_tool.py": "ispezione a mano dei tool_calls di Ollama",
    "prova_prompt.py": "confronto storico di varianti di prompt con Ollama",
    "prova_prompt2.py": "confronto storico di varianti di prompt con Ollama",
    "prova_prompt3.py": "confronto storico di varianti di prompt con Ollama",
    "prova_prompt4.py": "confronto storico di varianti di prompt con Ollama",
    "prova_speaker.py": "confronto dei modelli di chi parla: sottocomandi con dati scaricati",
    "prova_tool_scala.py": "banco «molti tool» con un LLM piccolo (minuti, con Ollama)",
    "prova_wakeword.py": "wake word dal microfono o sulle registrazioni (fuori da git)",
    "prova_whisper.py": "taratura di Whisper sulle registrazioni (fuori da git)",
}
TIMEOUT_S = 300           # per prova; con --ollama TIMEOUT_OLLAMA_S
TIMEOUT_OLLAMA_S = 3600
SALTATA = 77              # codice d'uscita di una prova saltata per intero
PARZIALE = "SALTATA IN PARTE:"   # riga stampata da una prova che salta una sua parte
LENTA_S = 10.0            # una prova del livello 1 oltre questo tempo va spostata


def livello(script: str) -> int:
    return 3 if script in LIVELLO_3 else 2 if script in LIVELLO_2 else 1


def _git(*args: str, radice: Path = RADICE) -> list[str]:
    try:
        r = subprocess.run(["git", "-C", str(radice), *args], capture_output=True,
                           timeout=30, env=_senza_git(os.environ))
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    return [x for x in r.stdout.decode("utf-8", "replace").split("\0") if x]


def _senza_git(env) -> dict:
    """L'ambiente senza GIT_*: dentro l'hook git passa GIT_DIR, GIT_INDEX_FILE… (in un worktree
    anche per il repository principale), e le prove che creano repository temporanei
    (prova_gestore) finirebbero a scrivere nell'indice del commit in corso (02/10)."""
    return {k: v for k, v in env.items() if not k.startswith("GIT_")}


def file_cambiati(modo: str) -> list[str] | None:
    """I percorsi cambiati, relativi alla radice. `indice`: quello che si sta per committare;
    `ramo`: dal punto in cui il ramo si è staccato da main, più l'albero di lavoro; altrimenti
    l'albero di lavoro e l'indice rispetto a HEAD, più i file nuovi. None fuori da git."""
    if os.environ.get("PROVE_FILE_CAMBIATI") is not None:     # la copia di --staged
        return [x for x in os.environ["PROVE_FILE_CAMBIATI"].split("\n") if x]
    if not (RADICE / ".git").exists():
        return None
    if modo == "indice":
        return _git("diff", "--cached", "--name-only", "-z")
    nomi = _git("diff", "HEAD", "--name-only", "-z")
    nomi += _git("ls-files", "--others", "--exclude-standard", "-z")
    if modo == "ramo":
        base = _git("merge-base", "HEAD", "main")
        if base:
            nomi += _git("diff", base[0].strip(), "HEAD", "--name-only", "-z")
    return sorted(set(nomi))


def _importatori(modulo: str) -> list[str]:
    """Le prove che importano un modulo di prove/ (import X, from X import, import X as)."""
    import re
    pat = re.compile(rf"^\s*(from\s+(prove\.)?{re.escape(modulo)}\s+import|import\s+(prove\.)?"
                     rf"{re.escape(modulo)}\b)", re.M)
    out = []
    for p in sorted((RADICE / "prove").glob("prova_*.py")):
        try:
            if pat.search(p.read_text(encoding="utf-8", errors="replace")):
                out.append(p.name)
        except OSError:
            pass
    return out


def scelte_dai_file(cambiati: list[str]) -> dict[str, str]:
    """prova → motivo (il primo file che la sceglie)."""
    scelte: dict[str, str] = {}
    for f in cambiati:
        f = f.replace("\\", "/")
        for pref, prove in LEGAMI:
            if f.startswith(pref):
                for p in prove:
                    scelte.setdefault(p, f)
        if f.startswith("prove/") and f.endswith(".py") and "/" not in f[6:]:
            # sé stessa e chi la importa, anche attraverso altre prove (cdp.py →
            # prova_schermi_pagina → prova_scritto_pagina)
            da_fare, visti = [f[6:]], set()
            while da_fare:
                nome = da_fare.pop()
                if nome in visti:
                    continue
                visti.add(nome)
                if nome.startswith("prova_"):
                    scelte.setdefault(nome, f)
                da_fare += _importatori(nome[:-3])
    return scelte


# ─────────────────────────── esecuzione ───────────────────────────
def lancia(script: str, args: list[str], timeout: float = TIMEOUT_S) -> dict:
    # Le prove non leggono calliope.locale.yaml: con l'indirizzo di casa impostato,
    # una prova (anche prima di un commit) contatterebbe Home Assistant. Né dgx.yaml: una
    # prova non deve mai aprire un tunnel verso la DGX vera (02/10)
    env = dict(_senza_git(os.environ), PYTHONUTF8="1",
               CALLIOPE_CONFIG_LOCALE=str(RADICE / "prove" / "nessun-file-locale.yaml"),
               CALLIOPE_AGENTI_CONFIG=str(RADICE / "prove" / "nessun-file-dgx.yaml"),
               # Niente taratura della voce all'avvio (07/10): con Calliope vera proverebbe i
               # thread di Piper a ogni prova, CPU tolta alle altre in parallelo
               CALLIOPE_TTS_TARATURA="false")
    env.pop("CALLIOPE_AGENTI_URL", None)
    env.pop("CALLIOPE_SSH", None)
    env.pop("PROVE_FILE_CAMBIATI", None)
    cmd = [sys.executable, "-u", str(RADICE / "prove" / script), *args]
    t0 = time.perf_counter()
    rc, out, vivi, scaduta = _esegui(cmd, env, timeout)
    dt = time.perf_counter() - t0
    if scaduta:
        out += f"\nERR tempo scaduto: più di {timeout:.0f} s (prova chiusa dal runner)\n"
        rc = 1
    elif vivi:
        # Un figlio rimasto vivo (Calliope, un browser, un server finto) tiene porte, file e
        # CPU durante le prove dopo e le fa fallire a caso: è un errore di questa prova (03/10)
        out += ("\nERR processi lasciati vivi dalla prova (chiusi dal runner): "
                + "; ".join(vivi) + "\n")
        rc = rc or 1
    esito = "saltata" if rc == SALTATA else "ok" if rc == 0 else "fallita"
    parziali = [r[len(PARZIALE):].strip() for r in out.splitlines() if r.startswith(PARZIALE)]
    return {"script": script, "args": args, "esito": esito, "dt": dt, "out": out,
            "parziali": parziali}


def _esegui(cmd: list[str], env: dict, timeout: float) -> tuple[int, str, list[str], bool]:
    """Lancia una prova. Su Windows dentro un job object (03/10): a prova finita si vede se
    ha lasciato processi vivi (su Windows i figli non muoiono con il padre) e il runner li
    chiude; allo scadere del tempo massimo si chiude tutto il job. Altrove un gruppo di
    processi suo. L'output si legge in un thread: un figlio rimasto vivo con la pipe
    ereditata non tiene fermo il runner (con `subprocess.run` aspettava la sua fine)."""
    job = None
    if sys.platform == "win32":
        try:
            from calliope.agenti import winjob
            job = winjob.JobObject()
        except Exception:  # noqa: BLE001
            job = None
    kw = dict(cwd=RADICE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if job is None and sys.platform != "win32":
        kw["start_new_session"] = True
    proc = winjob.avvia_nel_job(cmd, job, **kw) if job is not None else subprocess.Popen(cmd, **kw)
    pezzi: list[bytes] = []

    def leggi():
        for blocco in iter(lambda: proc.stdout.read1(65536), b""):
            pezzi.append(blocco)
    lettore = threading.Thread(target=leggi, daemon=True)
    lettore.start()
    scaduta = False
    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        scaduta = True
        if job is not None:
            job.termina()
        elif sys.platform != "win32":
            import signal
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
        else:
            proc.kill()
        rc = proc.wait(timeout=30)
    vivi: list[str] = []
    if job is not None:
        if not scaduta:
            fine = time.monotonic() + 2.0   # un figlio che si sta chiudendo da solo proprio ora
            while (vivi := _processi_nel_job(job)) and time.monotonic() < fine:
                time.sleep(0.1)
        job.termina()
        job.close()
    lettore.join(10)
    out = b"".join(pezzi).decode("utf-8", "replace").replace("\r\n", "\n")
    return rc, out, vivi, scaduta


def _processi_nel_job(job) -> list[str]:
    """I processi ancora vivi nel job (JobObjectBasicProcessIdList), con nome e comando."""
    import ctypes
    from ctypes import wintypes

    class _Elenco(ctypes.Structure):
        _fields_ = [("assegnati", wintypes.DWORD), ("nell_elenco", wintypes.DWORD),
                    ("pid", ctypes.c_size_t * 512)]
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.QueryInformationJobObject.restype = wintypes.BOOL
    k32.QueryInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                              wintypes.DWORD, ctypes.c_void_p)
    el = _Elenco()
    if not k32.QueryInformationJobObject(job.handle, 3, ctypes.byref(el), ctypes.sizeof(el),
                                         None):
        return []
    nomi = []
    for pid in el.pid[:el.nell_elenco]:
        try:
            import psutil
            p = psutil.Process(pid)
            nomi.append(f"{p.name()} ({pid}): " + " ".join(p.cmdline())[:200])
        except Exception:  # noqa: BLE001
            nomi.append(f"pid {pid}")
    return nomi


def _riassunto(out: str) -> list[str]:
    """Le righe d'errore della prova; di ogni traceback anche l'ultima riga (l'eccezione):
    prima si vedeva solo «Traceback (most recent call last):» (03/10)."""
    scelte, in_tb = [], False
    for r in (r for r in out.splitlines() if r.strip()):
        if r.startswith("Traceback"):
            in_tb = True
            scelte.append(r)
        elif in_tb and not r.startswith((" ", "\t")):
            in_tb = False
            scelte.append("  " + r)
        elif not in_tb and r.startswith(("ERR", "NO ")):
            scelte.append(r)
    return scelte or [r for r in out.splitlines() if r.strip()]


_STAMPA = threading.Lock()
CARTELLA_LOG = Path(tempfile.gettempdir()) / "calliope-prove"
FILE_DURATE = CARTELLA_LOG / "durate.json"


def _durate() -> dict:
    import json
    try:
        return json.loads(FILE_DURATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _salva_durate(esiti: list[dict]):
    import json
    d = _durate()
    for e in esiti:
        if e["esito"] == "ok":
            d[e["script"]] = round(e["dt"], 1)
    try:
        CARTELLA_LOG.mkdir(parents=True, exist_ok=True)
        FILE_DURATE.write_text(json.dumps(d, indent=1, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def stampa(e: dict, cosa: str, liv: int):
    nome = " ".join([e["script"], *e["args"]])
    segno = {"ok": "ok ", "saltata": "-- ", "fallita": "ERR"}[e["esito"]]
    righe = [f"{segno} {e['dt']:5.1f}s  L{liv} {nome:38} {cosa}"]
    if e["esito"] == "saltata":
        motivo = next((r for r in reversed(e["out"].splitlines()) if r.strip()), "")
        righe.append(f"      │ SALTATA: {motivo[:150]}")
    for p in e["parziali"]:
        righe.append(f"      │ {PARZIALE} {p[:150]}")
    if e["esito"] == "fallita":
        for r in _riassunto(e["out"])[-12:]:
            righe.append(f"      │ {r}")
        # L'output intero resta in un file: una prova instabile fallisce di rado, e le
        # righe qui sopra di solito non bastano a capire perché (03/10)
        log = CARTELLA_LOG / f"{e['script']}.{os.getpid()}.log"
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(e["out"], encoding="utf-8")
            righe.append(f"      │ (output intero in {log})")
        except OSError:
            pass
    with _STAMPA:
        print("\n".join(righe), flush=True)


def esegui_tutte(prove: list[tuple], paralleli: int, timeout: float) -> list[dict]:
    """Le prove non seriali in parallelo (le più lunghe prima, dalle durate dell'ultima
    volta), poi le seriali una alla volta, da sole sulla macchina."""
    from concurrent.futures import ThreadPoolExecutor
    durate = _durate()
    gruppo = [p for p in prove if p[0] not in SERIALI]
    serie = [p for p in prove if p[0] in SERIALI]
    gruppo.sort(key=lambda p: -durate.get(p[0], 5.0))
    esiti = []

    def una(p):
        script, args, cosa = p
        e = lancia(script, args, timeout)
        stampa(e, cosa, livello(script))
        return e
    if gruppo:
        if paralleli > 1 and len(gruppo) > 1:
            with ThreadPoolExecutor(max_workers=paralleli) as ex:
                esiti += list(ex.map(una, gruppo))
        else:
            esiti += [una(p) for p in gruppo]
    if serie and gruppo:
        print(f"── in serie: {len(serie)} prove (browser, Calliope vera, tempo reale)", flush=True)
    esiti += [una(p) for p in serie]
    return esiti


# ─────────────────────────── --staged: la copia dell'indice ───────────────────────────
def con_indice(argv: list[str]) -> int:
    """Rilancia il runner su una copia dell'indice di git (git checkout-index in una cartella
    temporanea): si prova quello che si sta per committare, non l'albero di lavoro (un file
    cambiato e non aggiunto non conta). Non tocca indice, albero di lavoro né stash
    dell'utente. I file grossi fuori da git (voices/, models/, wakeword/modelli/,
    biblioteca/) entrano nella copia come hard link (`_risorse`); dove non si può (un altro
    disco) le prove che li vogliono si saltano."""
    import shutil
    if not (RADICE / ".git").exists():
        print("--staged: non è un repository git", flush=True)
        return 1
    copia = Path(tempfile.mkdtemp(prefix="calliope-indice-"))
    try:
        r = subprocess.run(["git", "-C", str(RADICE), "checkout-index", "-a",
                            f"--prefix={copia.as_posix()}/"], capture_output=True,
                           env=_senza_git(os.environ), timeout=300)
        if r.returncode != 0:
            print("--staged: copia dell'indice non riuscita: "
                  + r.stderr.decode("utf-8", "replace")[-300:], flush=True)
            return 1
        _risorse(copia)
        modo = "ramo" if "--ramo" in argv else "indice" if "--hook" in argv else "albero"
        cambiati = file_cambiati(modo) or []
        # PROVE_ORIGINE: da dove viene la copia (prova_dati_privati vi cerca privato/termini.txt)
        env = dict(os.environ, PROVE_FILE_CAMBIATI="\n".join(cambiati), PROVE_ORIGINE=str(RADICE))
        resto = [a for a in argv if a != "--staged"]
        print(f"Prove sulla copia dell'indice di git ({copia})", flush=True)
        return subprocess.run([sys.executable, "-m", "prove", *resto], cwd=copia,
                              env=env).returncode
    finally:
        shutil.rmtree(copia, ignore_errors=True)


RISORSE = ("voices/*.onnx", "voices/*.onnx.json", "models/speaker/*.onnx", "models/web/**/*",
           "models/fine_turno/*.onnx",
           "wakeword/modelli/*.onnx", "biblioteca/*.zim", "biblioteca/*.sha256",
           "biblioteca/*.verificato", "biblioteca/indici/*.sqlite")


def _risorse(copia: Path):
    """I modelli e i file grossi fuori da git nella copia, come hard link: niente byte copiati,
    e cancellare la copia toglie solo i link."""
    for pat in RISORSE:
        for f in RADICE.glob(pat):
            d = copia / f.relative_to(RADICE)
            if not f.is_file() or d.exists():
                continue
            try:
                d.parent.mkdir(parents=True, exist_ok=True)
                os.link(f, d)
            except OSError:
                return              # un altro disco, o un file system senza hard link


AIUTO = """Uso: python -m prove [opzioni] [prova_x.py …]

    (niente)        livello 1 (veloci, in parallelo) + livello 2 (legate ai file cambiati
                    rispetto a HEAD, compresi quelli nuovi)
    --hook          come sopra con i file dell'indice (lo usa .githooks/pre-commit)
    --ramo          livello 2 con tutti i file cambiati dal punto in cui il ramo si è staccato da main
    --completo      TUTTE le prove a secco: livelli 1 e 2 in parallelo, poi il 3 in serie
                    (browser, Calliope vera, tempo reale). Obbligatorio prima dell'unione su main
    --staged        prova la copia dell'indice di git, non l'albero di lavoro
    --ollama        anche le prove con il modello vero (in serie, dopo)
    --seriale       una prova alla volta (-j 1); -j N: N prove insieme
    --timeout S     tempo massimo per prova (predefinito 300 s)
    prova_x.py …    solo queste (con il livello e il parallelo di sempre)
    --leggimi       rigenera l'elenco per area di prove/LEGGIMI.md da prove/elenco.md (16/10, #82)
Codici: 0 tutto bene, 1 qualche prova fallita. Una prova che esce con 77 è SALTATA (contata a parte)."""


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")    # «│» e accenti anche nella console cp1252
    except (AttributeError, ValueError):
        pass
    if "-h" in argv or "--help" in argv:
        print(AIUTO)
        return 0
    if "--leggimi" in argv:       # l'elenco di LEGGIMI.md non si scrive a mano (16/10, #82)
        sys.path.insert(0, str(RADICE / "prove"))
        import leggimi
        return leggimi.scrivi()
    if "--staged" in argv and os.environ.get("PROVE_FILE_CAMBIATI") is None:
        return con_indice(argv)
    paralleli = min(6, os.cpu_count() or 2)
    if "--seriale" in argv:
        paralleli = 1
    if "-j" in argv:
        paralleli = max(1, int(argv[argv.index("-j") + 1]))
    timeout = float(argv[argv.index("--timeout") + 1]) if "--timeout" in argv else TIMEOUT_S
    t_tot = time.perf_counter()

    nomi = [a for a in argv if a.endswith(".py")]
    completo = "--completo" in argv
    if nomi:
        # `python -m prove prova_satellite.py prova_agenti.py`: solo quelle (03/10)
        scelte = [p for p in A_SECCO if p[0] in nomi]
        print(f"Solo {len(scelte)} prove scelte", flush=True)
    elif completo:
        scelte = list(A_SECCO)
        print(f"Completo: {len(scelte)} prove a secco (livelli 1, 2 e 3), {paralleli} alla "
              f"volta, poi le seriali una alla volta", flush=True)
    else:
        modo = "indice" if "--hook" in argv else "ramo" if "--ramo" in argv else "albero"
        cambiati = file_cambiati(modo)
        legate = scelte_dai_file(cambiati) if cambiati is not None else {}
        if cambiati is None:
            print("Fuori da git: livello 2 con tutte le sue prove", flush=True)
            legate = {p[0]: "fuori da git" for p in A_SECCO if livello(p[0]) == 2}
        legate = {k: v for k, v in legate.items() if livello(k) >= 2}
        scelte = [p for p in A_SECCO if livello(p[0]) == 1 or p[0] in legate]
        uno = sum(1 for p in scelte if livello(p[0]) == 1)
        print(f"Livello 1: {uno} prove veloci, {paralleli} alla volta", flush=True)
        if legate:
            print("Livello 2 (file cambiati): " + ", ".join(
                f"{p[:-3].removeprefix('prova_')} ← {legate[p]}"
                for p in sorted(legate, key=lambda x: legate[x])), flush=True)
        saltate3 = [p[0] for p in A_SECCO if livello(p[0]) == 3 and p[0] not in legate]
        if saltate3:
            print(f"Livello 3 non lanciato ({len(saltate3)} prove): prima dell'unione su main "
                  f"python -m prove --completo", flush=True)
    esiti = esegui_tutte(scelte, paralleli, timeout)
    _salva_durate(esiti)

    if "--ollama" in argv:
        if "CALLIOPE_LLM_KEEP_ALIVE" not in os.environ:
            ka = keep_alive_della_voce()
            if ka is not None:
                # Le prove lo ereditano (lancia copia os.environ): Config() lo legge da qui
                os.environ["CALLIOPE_LLM_KEEP_ALIVE"] = str(ka)
                print(f"keep_alive delle prove con Ollama: {ka} (quello della voce)", flush=True)
        oll = [p for p in CON_OLLAMA if not nomi or p[0] in nomi]
        for script, args, cosa in oll:
            e = lancia(script, args, max(timeout, TIMEOUT_OLLAMA_S))
            stampa(e, cosa, 0)
            esiti.append(e)

    fallite = [" ".join([e["script"], *e["args"]]) for e in esiti if e["esito"] == "fallita"]
    saltate = [e["script"] for e in esiti if e["esito"] == "saltata"]
    parziali = [e["script"] for e in esiti if e["parziali"]]
    lente = [f"{e['script']} {e['dt']:.0f} s" for e in esiti
             if livello(e["script"]) == 1 and e["esito"] == "ok"
             and e["dt"] > LENTA_S * (1 if paralleli == 1 else 2)
             and e["script"] in {p[0] for p in A_SECCO}]
    superate = sum(1 for e in esiti if e["esito"] == "ok")
    print(f"\n{superate}/{len(esiti)} prove superate, {len(saltate)} saltate, "
          f"{len(fallite)} fallite in {time.perf_counter() - t_tot:.1f}s", flush=True)
    if saltate:
        print("   saltate: " + ", ".join(saltate))
    if parziali:
        print("   saltate in parte: " + ", ".join(parziali))
    if lente:
        print("   lente per il livello 1 (spostale al 2 o al 3 in prove/__main__.py): "
              + ", ".join(lente))
    if fallite:
        print("   fallite: " + ", ".join(fallite))
    return 1 if fallite else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
