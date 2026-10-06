# Satelliti

*Microfono e casse in rete con Calliope sul server: protocollo, TLS, inoltro, esecutore remoto, uno schermo per satellite. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Satelliti (microfono e casse in rete, Calliope sul server) | `websockets` (API sincrona), PCM 16 kHz, TLS con `ssl` della libreria standard e impronta fissata; sul satellite lo stesso `Listener` (VAD ONNX, wake word) e `tts.UscitaLocale` | `calliope/satellite/` → `ServerSatelliti`, `AscoltoRemoto`, `UscitaRemota` (`server.py`), `Satellite`, `Riproduttore` (`client.py`), `protocollo.py`, `ArchivioSatelliti`, `load_satelliti`; inoltro TCP per il telefono di casa `Inoltro` (`inoltro.py`, dal 03/10); PC nuovo con un comando e aggiornamenti con ritorno indietro (dal 03/10): pagina `/satellite` e `/installa` (`web.py`), pacchetto da `uv.lock` (`pacchetto.py`: `Distributore`), `Aggiornatore` (`aggiorna.py`), `installazione/avvio.py` e `installazione/installa.ps1` (uv 0.12.22, Python 3.14.8); `audio_modo` in `Config`; terminale `python -m calliope.satellite`; avvio `avvia_satellite.py`, `setup/satellite/` |

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

  - **Satelliti** (02/10, `calliope/satellite/`, [`docs/ricerche/2026-10-02-satellite.md`](../ricerche/2026-10-02-satellite.md)):
    con `audio_modo: satellite` microfono, VAD, wake word e casse sono di un satellite in rete
    (il portatile), Whisper, modello, Piper e tool restano sul server; stesso ciclo di
    `main.py`. Provato con Calliope vera e un satellite con microfono e casse finti: la DGX
    vera non è ancora stata provata. *[Storico (02/10): dalla sera del 02/10 Calliope gira sulla DGX come servizio; vedi [setup-dgx](setup-dgx.md).]*
    Dal 03/10 un PC Windows vuoto diventa satellite con un comando dalla pagina `/satellite`
    (chiave del certificato fissata con curl, uv e Python con versioni e SHA-256 fissati) e si
    aggiorna da solo con ritorno indietro (`prova_installa_satellite`; con `--vera` installazione
    vera in ~30 s, aggiornamento preparato dalla cache in ~2,5 s). Provato in locale con un
    satellite vero sotto `avvio.py`: aggiornamento confermato in 6 s, versione che non si
    ricollega tornata indietro. Non provato su un PC pulito né contro la DGX.

## Note dalla sezione «Problemi noti» di CLAUDE.md (fino al 06/10)

- **TLS e thread** (03/10, `calliope/tls_sicuro.py`): websockets sincrono legge da un thread e
  scrive da altri; con l'`SSLSocket` normale sono `SSL_read` e `SSL_write` insieme sullo stesso
  oggetto SSL (OpenSSL non lo ammette) e ogni tanto un messaggio non partiva: 9 aperture su 300
  restavano senza risposta («timed out while waiting for handshake response», la prova del TLS
  in `prova_satellite` sotto carico). `sicuro(ctx)` fa usare `SocketTLS` (operazioni TLS sotto un
  lucchetto, attesa con select fuori): server e client dei satelliti, client di Home Assistant.
  Vale anche per i client e i server finti delle prove: `prova_installa_satellite` apriva il
  WebSocket con un contesto normale e falliva 1 volta su ~5 nell'hook («did not receive a valid
  HTTP response»: il server chiude dopo i suoi 3 s; 17–21 aperture su 400 contro 0 con
  `sicuro`); lo stesso in `ha_finto.py`.
  Lo stesso difetto nel **ponte TLS** degli schermi (due thread sullo stesso SSLSocket: la
  pagina restava bianca 30 s, 1 volta su 3): ora copia i due versi da un thread solo con socket
  non bloccanti. Resta un limite di websockets: con tanti dati nei due versi insieme (MB al
  secondo) `send` tiene il lucchetto del protocollo mentre il socket è pieno e i due lati si
  bloccano; l'audio dei satelliti è molto sotto.

- **Satelliti** (02/10, `calliope/satellite/`; prova a secco `prove/prova_satellite.py`, prova
  manuale e passi per la DGX in `prove/LEGGIMI.md`). Il portatile come satellite di Calliope
  sulla DGX. **La DGX vera non è ancora stata contattata.** *[Storico (02/10): dalla sera del 02/10 Calliope gira sulla DGX come servizio; vedi [setup-dgx](setup-dgx.md).]*
  - **WebSocket aperto dal satellite** (`websockets` 17.1, API sincrona), JSON per i comandi,
    binario per l'audio: PCM 16 kHz verso il server, la voce di Piper a pezzi da 0,2 s verso il
    satellite (comincia a suonare al primo). Niente Opus (librerie native senza wheel
    `win_arm64`), niente Wyoming (nessuna sicurezza, semantica diversa, `wyoming-satellite`
    archiviato). Posto per l'esecutore del PC: stessa connessione, tipi di messaggio nuovi.
  - **Inoltro per il telefono di casa** (03/10, `calliope/satellite/inoltro.py`, prova
    `prove/prova_inoltro.py`, passi in `prove/LEGGIMI.md`, §8 di
    `docs/ricerche/2026-10-03-webapp-telefono.md`): con `satellite_inoltro: "0.0.0.0:8770"` il
    satellite copia i byte (TCP grezzo, TLS da capo a capo con la CA di casa) verso la pagina
    degli schermi della DGX, per il telefono che entra a casa con una VPN. Solo
    da indirizzi in `satellite_inoltro_reti` (dal 03/10 solo casa e VPN: vedi Sicurezza), 32 connessioni, 300 s d'inattività.
    `calliope schermi --certificato --host IP1,IP2`. Il satellite chiede lo schermo a ogni
    connessione: dopo un certificato rifatto il ponte prende l'impronta nuova (prima la
    rifiutava fino al riavvio).
  - **Esecutore remoto del PC** (03/10, `calliope/pc/remoto.py`, `calliope/satellite/esecutore.py`,
    `RemoteDelivery`; prova `prove/prova_esecutore.py`). Protocollo **2**: il satellite su
    Windows (`satellite_esecutore`, predefinito acceso) annuncia nel «ciao» nome, capacità, app
    del suo catalogo e la consegna dei file; il server manda `pc_richiesta` (id, metodo da un
    elenco chiuso, argomenti, `scadenza_s`) e riceve `pc_esito`; i documenti vanno come `file`
    + pezzi binari `F` da 64 KB (tra un pezzo e l'altro passa la voce) con lo SHA-256, risposta
    `file_esito`. Il server accetta anche la versione 1 (satellite vecchio: niente esecutore);
    un satellite nuovo davanti a un server vecchio (4426) torna da solo alla 1. Le regole comuni
    restano sul server nella classe base (permessi e `pc_proprietari` nei tool, ultima ricerca
    della stessa persona, schermo bloccato), ricontrollate sul satellite. **I percorsi non
    escono dal satellite**: una ricerca torna con «maniglie» casuali (valide ~20 minuti, solo
    in quel processo), un documento ha il riferimento `sat:<nome del file>` dentro la cartella
    dei documenti. **I comandi delle app non partono dal server**: va solo il nome, il comando è
    del catalogo `pc_app` del portatile. Tempo massimo `pc_remoto_timeout_s` (2 s) per
    richiesta, e dopo un tempo scaduto le chiamate dei 5 s successivi falliscono subito (un tool
    ne fa 1–3); una richiesta rimasta in coda oltre la sua scadenza sul satellite non si esegue
    più (niente azioni in ritardo). **I tool `pc_*` ci sono sempre** con `audio_modo:
    satellite` e `pc_enabled` (tutte le capacità, enum delle app da `pc_app` del server): se il
    satellite non è collegato, è vecchio o gli manca una capacità lo dicono loro («il portatile
    non è collegato», NON eseguita), così il prefisso del prompt resta in cache quando il
    satellite va e viene (scelta come per `casa_integrazione` e gli agenti; nel prompt il PC
    conta come presente se i tool ci sono). Documenti: `RemoteDelivery` li manda al satellite e
    passa la maniglia a `offri_file` («Lo apro?» → `pc_apri_file(1)` sul portatile); senza
    satellite, o se cade durante l'invio, il file resta sul server e la frase lo dice («…, sul
    server, perché il portatile non è collegato.», niente «Lo apro?»). Misure in locale: giro di
    una richiesta 0,3–0,4 ms di mediana, consegna 20 MB in 0,25 s (~80 MB/s). Restano: più
    satelliti con esecutore (oggi vale quello attivo), i risultati degli agenti
    (`agenti/servizio.py` scrive ancora con `LocalDelivery`), il registro delle richieste sul
    satellite oltre al log.
  - **Sul satellite** lo stesso `audio.Listener` (VAD ONNX senza torch, wake word, pre-roll,
    `watch_for_name`, `measure_echo`) con due aggiunte: la sorgente del microfono iniettabile e
    `on_audio`, che riceve la frase appena è rivolta a Calliope per mandarla mentre si parla.
    Da addormentata l'audio non esce: 0 byte su una frase senza nome. Riproduzione con
    `tts.UscitaLocale` (estratta da `Speaker`: lead, tail, keepalive per le cuffie Bluetooth).
    **Barge-in sul satellite**: si ferma da solo entro un blocco da 100 ms (28–83 ms misurati),
    poi avvisa il server; un turno interrotto si scarta anche se arrivano altre frasi. Il
    livello B manda al server il parlato (l'impronta CAM++ è lì) solo se il satellite non ha
    sentito l'eco sul saluto della prima connessione.
  - **Sul server** `AscoltoRemoto` (contratto di `Listener`: `listen`, `watch_for_name`,
    `started_at`, `woke`, `wake_score`, avvisi all'arbitro) e `UscitaRemota` (l'uscita di
    `Speaker`: `fine_turno` aspetta le frasi «dette per intero» dal satellite). La finestra di
    follow-up passa come secondi che restano (niente orologi da allineare). Un satellite alla
    volta (l'ultimo collegato sostituisce il precedente); la sua stanza va agli schermi
    (`Schermi.stanza_corrente`). Senza satellite collegato gli annunci aspettano. Il server
    accoglie i satelliti solo a Calliope avviata (prima non c'è il saluto). Ogni connessione
    ha i suoi turni: un server riavviato ripartiva da 1 e il satellite scartava tutto (trovato
    dalla prova).
  - **Sicurezza**: abbinamento a codice come gli schermi (stesso archivio, tabelle
    `satelliti*`, solo l'hash del token; `ArchivioSchermi.TABELLA`), token nel primo messaggio
    e non nell'URL, 4401 senza dettagli, niente connessioni con `Origin` (un browser riceve
    403). In rete il server non parte senza certificato (salvo `satellite_senza_tls`, con un
    avviso); certificato autofirmato di `openssl`, impronta SHA-256 fissata dal satellite
    all'abbinamento (stampata dai due lati da confrontare), token mandato solo dopo il
    controllo. La pagina degli schermi resta in http: in ufficio il suo token viaggerebbe in
    chiaro (`satellite_schermo: no` per non aprirla).
  - **Misure a secco** (Calliope vera, Ollama e Whisper finti, Piper vero, satellite con
    microfono e casse finti in tempo reale): fine frase → prima voce 0,67–0,80 s, con 50 ms di
    giro simulati +30–93 ms (≈ un giro); VAD + wake word 1,4 % di un core; ~74 kB verso il
    server per «Calliope, che ore sono?». Con la voce sintetica la wake word salta una frase
    ogni tanto (soglia di produzione, 2 blocchi sopra 0,5): la prova la ripete.
  - `prove/__main__.py` toglie le variabili `GIT_*` alle prove: nell'hook di un worktree
    `prova_gestore` scriveva un suo commit nel ramo del commit in corso (02/10).

- **Uno schermo per satellite** (05/10, `ServerSatelliti._schermo`, prova
  `prova_schermi_satellite.py`): sulla DGX ogni ricollegamento dopo un aggiornamento faceva
  nascere un abbinamento di schermo nuovo («studio di dario 2» mai collegato, «telefono di
  dario» doppio) appena il token conservato dal satellite non valeva più (pagina riabbinata a
  mano con un codice, schermo revocato, telefono riabbinato). Ora lo schermo sa di chi è
  (colonna `satellite` di `schermi`, fuori dalle versioni dello schema): vale il token
  ripresentato se è suo (uno schermo di prima si lega), altrimenti il suo schermo con un token
  **rinnovato** (`rinnova_token`; il satellite riapre la pagina solo se il token cambia), e
  uno nuovo solo se non ne ha. `calliope satellite --revoca` toglie anche il suo schermo.
  Abbinamenti (schermi e satelliti) senza collegamento da più di `schermi_inattivi_giorni` (7)
  si segnalano all'avvio, in `calliope stato` e negli elenchi da terminale (con l'ultimo
  collegamento), mai tolti da soli.

## Prima voce sentita (06/10, prova e2e)

La voce arrivava 0,2–0,5 s dopo `prima_frase_s` (p90 1–2,8 s). Il satellite manda `suona` (id
della frase, ritardo dell'uscita) quando comincia a riprodurre una frase
(`Riproduttore.suonata`); il server la segna (`Collegamento.suonate`), `UscitaRemota.prima_voce`
dà la prima del turno, `Speaker.prima_voce` anche con le casse locali, e il registro dei turni
ha `prima_voce_s` (da `t0`, comprende la frase d'attesa). `calliope/latenza.py` e il cruscotto
mostrano la prima voce sentita e la stessa dalla fine del parlato. Compatibile nei due sensi.
Il telefono (pagina web) non lo manda ancora.
