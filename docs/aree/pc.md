# PC a voce

*Volume, musica, luminosità, app, file sul portatile; esecutore locale e remoto. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| PC a voce (il portatile stesso, o quello del satellite) | pycaw, WinRT (GSMTC), screen_brightness_control, pywin32 (Windows Search via ADODB), psutil | `calliope/pc/` → `PCExecutor` (`base.py`), `LocalWindowsExecutor` (`windows.py`), `RemotePCExecutor` (`remoto.py`, dal 03/10), `load_pc`; sul satellite `EsecutoreSatellite` (`calliope/satellite/esecutore.py`); tool in `calliope/tools/pc.py`; documenti al satellite con `RemoteDelivery` (`calliope/documenti/consegna.py`) |

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

  - **Esecutore remoto del PC** (03/10, protocollo 2 dei satelliti): con Calliope sulla DGX i
    tool `pc_*` comandano il portatile Windows collegato come satellite, e i documenti si
    salvano nella sua cartella Documenti\Calliope. Provato a secco (`prova_esecutore.py`):
    la prova vera con la DGX e il portatile no.

  - **PC a voce** (26/09, `calliope/pc/`): volume, musica, luminosità, batteria, programmi
    aperti, app del catalogo, blocco dello schermo, ricerca e apertura di file sul portatile
    stesso, con 8 tool `pc_*`.

## Note dalla sezione «Problemi noti» di CLAUDE.md (fino al 06/10)

- **PC a voce** (26/09, `calliope/pc/`, `calliope/tools/pc.py`, prove `prove/prova_pc.py` e
  `prove/prova_pc_ollama.py`):
  - `PCExecutor` prende e restituisce solo dati JSON: domani passa per un WebSocket. Le
    regole comuni stanno nella classe base: app solo dal catalogo `pc_app`, file solo
    come «risultato n dell'ultima ricerca» della stessa persona (valida 15 minuti, i
    percorsi non escono mai dall'esecutore), a schermo bloccato niente app, file, ricerca
    né programmi aperti.
  - `LocalWindowsExecutor` fa tutte le chiamate native da un solo thread con COM
    inizializzato: oggetti COM e WinRT restano aperti. Volume letto in ~0,5 ms (l'endpoint
    si riattiva solo se cambia l'uscita predefinita, per le cuffie Bluetooth); impostarlo
    costa ~180 ms. Ricerca in Windows Search 20–100 ms, limitata alla cartella dell'utente:
    prima sui nomi con la radice («bollett»), poi sul contenuto con `CONTAINS`.
  - **Schermo bloccato** (provato a mano il 27/09): vale il flag `SessionFlags` di WTS,
    **a scostamento 16** di `WTSINFOEXW` (0 = bloccato, 1 = sbloccato). A 12 c'è lo
    stato della connessione, sempre 0, che il 26/09 era stato scambiato per il flag. Il
    nome del desktop di input **non basta**: la schermata di blocco di Windows 11
    (LockApp) gira sul desktop «Default», che diventa «Winlogon» solo per un secondo,
    e Calliope ha aperto il blocco note a schermo bloccato. Come riserva, con il flag
    sconosciuto: LockApp.exe in primo piano o desktop diverso da «Default».
    LogonUI.exe resta vivo nella sessione 0 dopo lo sblocco: non è un indizio.
  - Permessi: programmi aperti, ricerca e apertura di file solo a `pc_proprietari` (nome
    o id del profilo) o a chi amministra, e mai nella zona grigia della conversazione. I
    tool restano visibili a tutti i familiari (il prefisso non cambia) e il codice rifiuta
    con «NON è stata eseguita». L'ospite non ha nessun tool `pc_*`, a meno di
    `pc_ospite_volume_media` (solo volume e musica).
  - Valori come detti: «un po'» = `pc_passo`, «un pochino» la metà, «molto» il doppio, «al
    massimo» 100, sempre tra 0 e 100. Per «alza il volume a 50» il modello manda a volte
    azione=alza, valore=50: decide la frase dell'utente («a 50» = assoluto). I periodi
    guardano indietro con `tempi.parse_past_range` («la settimana scorsa», «ad agosto»).
  - Prompt: senza PC la frase sui limiti diceva «non usi file né dispositivi»; con il PC
    cambia, e i tool `pc_*` si nominano solo se ci sono. Nominarli conta poco (58/58
    contro 57/58 senza): le descrizioni con gli enum fanno quasi tutto.
  - Prova su Ollama con il PC finto: 58/58 in 2 giri, prima frase mediana 0,40 s. Nei
    rifiuti il modello dice «non ho i permessi» invece di «solo il proprietario può».
    Con i tool `pc_*` registrati le prove esistenti restano uguali (prova_casa 21/21);
    `cambia_voce`, che non ha una `conferma`, ha dato una volta su cinque una risposta vuota.
  - **Prova a voce del 27/09** (microfono e altoparlanti del portatile): volume, musica
    senza lettore aperto, app dentro e fuori elenco giusti, prima frase 0,45–1,14 s.
    Tre difetti corretti:
    1. nessun file si apriva: `System.ItemPathDisplay` è il percorso come lo mostra
       Esplora file (cartelle tradotte) e non esiste sul disco, 8 su 8; si usa
       `System.ItemUrl`;
    2. i nomi uguali si dicono con tipo, data e ora («timelog xlsx del 6 agosto»);
    3. con il nome del file detto il modello chiamava `pc_apri_file` senza ricerca;
       descrizione ed errore ora dicono di cercare prima.
    Il PC si prepara **prima** di `Speaker`: il precaricamento delle voci teneva occupato
    l'interprete per ~7 s, la preparazione del volume superava il tempo massimo e il
    controllo del PC restava spento. Prova su Ollama dopo le correzioni: 60/60.
  - **Azioni promesse e non fatte** (27/09, `brain.ACTION_PROMISE`, vale per tutti i tool):
    «Per aprire il file "chiavi", devo prima cercarlo.» e il turno finiva lì. Se una
    risposta senza tool promette un'azione, o la domanda chiede un file
    (`TOOL_REQUEST`), il modello riceve **una** spinta fuori dalla storia e chiama il
    tool. Il difetto: la frase detta prima resta («…puoi dirmi qualche dettaglio?» e poi
    «Ho trovato…»). «Apri il file preventivo» senza spinta: 3 su 4. Con una risposta
    vuota dopo un tool riuscito si dice la sua `conferma`. Una ricerca vuota non elenca
    più file, e i file di sistema e le cartelle nascoste sono esclusi. Dal 01/10 la spinta
    non scatta su una risposta che finisce con «?» («Lo apro?»: decide la persona) né su
    «non la apro».
  - Config: `pc_proprietari` e `pc_app` sono i primi campi lista e mappa;
    `_literal_default` legge `field(default_factory=…)`, `_type_ok` controlla gli
    elementi e il file d'esempio li scrive su più righe.

## «Quale apro?» con le date (07/10 sera, ramo `correzioni-giro8`)

Caso vero della DGX (15:50): dopo `pc_cerca_file(tipo=pdf)` «Ho trovato 5 PDF: … Quale apro?»,
«L'ultimo che hai creato.» → `pc_apri_file(1)`, giusto per caso: l'azione in sospeso dava al
modello solo «1 = nome, 2 = nome…». Ora la proposta dice, per ogni file trovato (anche quelli
non detti), la data e l'ora di modifica («1 = visura (modificato oggi alle 15:23); 2 = diagnosi
(modificato ieri alle 18:02); 3 = contratto (modificato il 6 agosto alle 9:05)», l'anno se non è
questo) e che il numero 1 è il più recente (`tools/pc._elenco_sospeso`). Le date non si dicono a
voce: la frase resta «Ho trovato 5 PDF: …». Così «l'ultimo», «quello di ieri», «quello di
stamattina» li risolve il modello al turno dopo.

Ordine: Windows Search ordina già per `System.DateModified` (anche la ricerca nel contenuto) e il
satellite usa lo stesso esecutore; non c'è un punteggio di pertinenza (il nome o il contenuto
filtrano, la data ordina). Da ora `PCExecutor.cerca_file` riordina comunque dal più recente
(senza data in fondo) per ogni esecutore. ~~`pc_apri_file` con «ultimo» converte in -1, l'ultimo
dell'elenco (il più vecchio)~~ (storico): dal 07/10 sera «ultimo»/«ultima» valgono 1, il più
recente (decisione di Dario: «apri l'ultimo che hai fatto» è l'ultima attività svolta); «l'ultimo
della lista» lo traduce il modello in un numero. Prove: `prove/prova_dopo_annunci.py`,
`prove/prova_pc.py`.

Con un lavoro dell'agente appena detto, «un PDF» va a `risultato_lavoro` e non a
`pc_cerca_file`: vedi [agenti-estensioni](agenti-estensioni.md).
