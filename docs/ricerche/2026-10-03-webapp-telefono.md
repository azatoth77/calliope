# Il telefono come satellite: una web app servita da Calliope

*03/10/2026. Decisione con l'utente (02/10): una web app installabile (PWA) per iOS e Android,
servita da Calliope stessa, invece di un'app nativa. Codice in `calliope/schermi/telefono.py` e
`calliope/schermi/pagina/telefono/`; prove `prove/prova_telefono.py` (a secco) e
`prove/prova_telefono_pagina.py` (Edge senza finestra con il microfono finto). Legende: **[M]**
misurato qui, **[D]** deduzione, **[V]** da verificare sul telefono.*

## 1. In breve

- **Stesso protocollo del satellite** (`calliope/satellite/protocollo.py`), su un WebSocket del
  server degli schermi (stesso host e porta, HTTPS). Il server avvolge il WebSocket di Starlette
  in una facciata sincrona con l'API di `websockets.sync` (`PonteWs`): abbinamento, token,
  sessione, follow-up, barge-in e annunci sono **lo stesso codice** di `ServerSatelliti`.
- **Nel telefono**: microfono (AudioWorklet, ricampionato a 16 kHz), Silero VAD e la wake word
  «Calliope» (gli stessi ONNX del portatile) con **onnxruntime-web 1.30.0** in WebAssembly, un
  thread, caricato dal server. Da addormentata non esce un byte finché il nome non scatta
  (**0 byte** in 12 s di parlato senza nome [M]). Voce di Piper a pezzi riprodotta con Web Audio,
  «Calliope, basta» ferma la riproduzione nel telefono.
- **Due modi**: «Parla» (tocco: la frase parte subito e vale come il nome; pressione lunga =
  parla finché tieni premuto) e **«Microfono acceso»** (vivavoce con la wake word, schermo tenuto
  acceso con la Screen Wake Lock API, avviso se il browser non la concede).
- **Stessi numeri del Python**: sulla stessa frase la wake word del browser dà gli stessi
  punteggi di `WakeWordDetector` (differenza media 0,0000 [M]) e Silero VAD le stesse
  probabilità (differenza massima 0,0000 [M]).
- **Il telefono è uno schermo personale**: abbinato da chi amministra come un satellite
  (`calliope satellite --abbina <codice> --stanza telefono --personale Dario`: il telefono chiede
  di essere personale, chi abbina conferma). Le schede arrivano con l'SSE degli schermi
  (`schermo.js` incorporato), con il token di schermo che il satellite riceve sulla sua
  connessione.
- **CA di casa per i telefoni**: `calliope schermi --certificato --host <IP>` crea una piccola CA
  (10 anni) e il certificato della pagina firmato da lei (825 giorni, SAN con gli indirizzi,
  serverAuth). Si installa una volta sul telefono; senza, la pagina funziona dietro l'avviso del
  browser, ma niente service worker su Chrome e l'eccezione può non valere nella web app su iOS.

## 2. Perché il server degli schermi e non il WebSocket dei satelliti

Il WebSocket dei satelliti (porta 8771) rifiuta i browser (`origins=[None]`, 02/10) e ha un suo
certificato con l'impronta fissata, che un browser non sa fissare. La pagina degli schermi è già
in HTTPS in rete (02/10), con CSP e controllo dell'Host: il WebSocket del telefono sta lì, solo
con l'**Origin della pagina stessa** e lo stesso controllo dell'Host (DNS rebinding). uvicorn lo
serve con `websockets` in modalità sans-I/O (`ws="websockets-sansio"`): `websockets` è già una
dipendenza dei satelliti, nessun codice nativo nuovo; senza la libreria il WebSocket resta spento
come prima e la pagina lo dice.

| Rotta | Cosa |
|---|---|
| `/telefono/` | la pagina, CSP `default-src 'self'` più `'wasm-unsafe-eval'` (compilare il WebAssembly; niente eval di JavaScript) e il WebSocket per esteso (Safari < 15.4) |
| `/telefono/ort/…` | onnxruntime-web dalla cartella `telefono_web`, gzip (14,2 → 3,7 MB) ed ETag |
| `/telefono/modelli/…` | VAD e wake word, **solo con il token di un satellite abbinato** (il classificatore è addestrato con dati non commerciali) |
| `/telefono/calliope-ca.crt` | la CA di casa da installare |
| `/telefono/ws/abbina`, `/telefono/ws/sessione` | il protocollo del satellite |

## 3. Più satelliti: chi ascolta

Prima l'ultimo satellite collegato toglieva il posto (4409) al precedente: telefono e portatile si
sarebbero sostituiti a vicenda all'infinito (ognuno si ricollega da solo). Ora (`ServerSatelliti`):

- più satelliti collegati insieme, **uno attivo** (ascolta e parla): il primo che arriva;
- il telefono **prende** il posto quando si tocca «Parla» o si accende il microfono (`prendi`):
  il portatile riceve `sveglia` e smette di ascoltare appena nessuno gli parla;
- **restituisce** il posto (`lascia`) quando si spegne il microfono, quando la pagina va in
  secondo piano o, con il solo «Parla», quando la finestra di follow-up è finita; chiudere la
  connessione fa lo stesso;
- la stessa connessione due volte (riconnessione, due schede) chiude ancora la vecchia (4409);
- volume, file e documenti restano al satellite con l'**esecutore del PC** (`per_pc`), anche
  con il telefono attivo.

Una conversazione per stanza (due persone in due stanze insieme) resta il passo successivo
(docs/ricerche/2026-10-02-satellite.md, §5).

## 4. Nel browser

- **Microfono**: `getUserMedia` con `echoCancellation`, `noiseSuppression`, `autoGainControl`
  (vivavoce: la cancellazione dell'eco del telefono tiene fuori la voce di Calliope); un
  AudioWorklet filtra (sinc con finestra di Blackman a ~7,2 kHz) e ricampiona a 16 kHz, blocchi da
  512 campioni come Silero.
- **Ascolto**: la logica di `audio.Listener` riscritta in JavaScript (pre-roll, fine frase dal
  VAD, follow-up con il tempo mandato dal server, wake word solo da addormentata, scarto delle
  frasi non rivolte a Calliope). Dopo un tocco il silenzio conta solo da quando si è sentita la
  voce (serve un attimo per cominciare); 6 s senza voce = niente frase.
- **Riproduzione**: ogni pezzo PCM diventa un AudioBuffer alla frequenza di Piper, in coda al
  precedente; l'arresto ferma le sorgenti programmate. «Dette per intero» = arrivate tutte e
  suonate fino in fondo, come sul satellite. Il nome detto da Calliope (e 0,8 s dopo) non sveglia
  la wake word.
- **Cache**: i modelli e il WebAssembly in Cache Storage con la versione nell'URL (alla seconda
  apertura non si riscarica niente [M]); il service worker tiene solo i file della pagina
  (prima la rete: un aggiornamento di Calliope arriva subito). Nessuna notifica push
  (principio 9).
- **Limiti dei browser**: bloccando il telefono o cambiando app il microfono si spegne (la
  pagina lo dice e restituisce il posto); iOS vuole un tocco per far partire l'audio; la Screen
  Wake Lock API c'è da Safari 16.4 e Chrome 84, nella web app aggiunta alla Home di iOS [V]
  (aggiornato il 04/10, §9: nella web app e in Edge per iOS solo da 18.4). Su
  Safari 17 la pagina usa l'Audio Session API (`play-and-record` col microfono, `playback`
  senza), che decide l'uscita [V].

## 5. Misure (portatile, Edge 154 senza finestra, microfono finto)

| Misura | Valore |
|---|---|
| Pagina (HTML, JS, CSS, icone, schermo.js) | ~92 kB [M] |
| onnxruntime-web e modelli, la prima volta (gzip) | ~8,0 MB [M]: WebAssembly 3,7 MB compresso (14,2 senza), i quattro modelli ~4,3 MB compressi (5,6 senza: VAD 2,3, wake word 3,3); dopo, 0 |
| Preparazione dei modelli (scarico in locale + sessioni + riscaldamento) | 1,1–1,35 s [M] |
| Inferenza: VAD per blocco da 32 ms / wake word per blocco da 80 ms | 0,35 ms / 3,5 ms [M] (Python nativo: ~0,07 / ~1 ms) |
| CPU dell'inferenza con il microfono acceso | ~5,5 % di un core in teoria, 10–12 % misurato nel ciclo [M]; sul telefono [V] (WebAssembly a un thread: 2–3 volte il portatile [D]) |
| Audio verso il server | 256 kbit/s solo dopo il nome o il tocco (come il satellite) |

Il costo è quasi tutto nell'embedding della wake word (rete convoluzionale, ~3,5 ms ogni 80 ms).
Se sul telefono pesa sulla batteria: saltare embedding e classificatore quando il VAD non sente
voce da più di un secondo (i buffer restano quelli del silenzio), da misurare contro i risvegli
persi.

## 6. In auto

Con CarPlay o Android Auto collegati il sistema manda l'audio del telefono alle casse dell'auto;
il microfono di solito è quello dell'auto quando una chiamata o l'assistente sono attivi, ma per
una pagina web con `getUserMedia` dipende dal sistema [V]. Passi della prova in
`prove/LEGGIMI.md` («Prova manuale del telefono»): uscita, microfono dell'auto o del telefono,
falsi risvegli con la radio, leggibilità di pulsante e stato con lo schermo acceso. La pagina ha
pulsanti grandi (il «Parla» occupa un terzo dello schermo), contrasto alto e tema chiaro o scuro
come il telefono; i tocchi vanno fatti da fermi.

## 8. Da fuori casa (03/10)

Il telefono fuori casa raggiunge Calliope entrando con una VPN nella rete di casa e
passando dall'inoltro TCP del satellite (`calliope/satellite/inoltro.py`, `satellite_inoltro`,
reti ammesse in `satellite_inoltro_reti`, TLS da capo a capo con la CA di casa). La
descrizione della rete di questa installazione non è pubblicata. Prova a secco:
`prove/prova_inoltro.py`.

## 7. Cosa resta

- La prova sui telefoni veri (iPhone e Android, in VPN e a casa) e in auto, con le annotazioni
  qui sopra segnate [V]; CPU e batteria con il microfono acceso per un'ora.
- La prova da fuori casa con WireGuard e l'inoltro del portatile (§8).
- Una conversazione per satellite (telefono in auto e portatile a casa insieme).
- Un satellite sempre in ascolto in tasca non è possibile con una pagina web: servirebbe un'app
  nativa (servizio in primo piano su Android), fuori da questa decisione.

## 9. Schermo acceso col microfono (04/10)

**Problema** (iPhone 13 mini, Edge, anche come web app sulla schermata Home): in auto con
«Microfono acceso», appena lo schermo si spegne iOS sospende la pagina e Calliope smette di
ascoltare. Nessun browser lascia ascoltare una pagina a schermo spento o bloccato: l'unica
strada è tenere acceso lo schermo finché il microfono è acceso.

**Screen Wake Lock API in WebKit** (su iPhone e iPad Edge e Chrome sono WebKit):

| Dove | Da | Note |
|---|---|---|
| Safari, nel browser | iOS 16.4 | [V] MDN, note di WebKit |
| Edge e Chrome per iOS (WKWebView) | iOS 18.4 | prima `navigator.wakeLock` non c'è (dati di compatibilità di MDN: «WebView on iOS 18.4») |
| Web app sulla schermata Home | iOS 18.4 | da 16.4 a 18.3 `request()` riesce e restituisce una sentinella valida, ma lo schermo si spegne lo stesso: WebKit bug 254545, corretto in 18.4 (marzo 2025) |
| Prima richiesta | sempre | WebKit vuole un gesto in corso (transient activation), a differenza di Chromium e Firefox; dopo una riuscita le richieste successive non lo vogliono (bug 255363, 263382@main, aprile 2023), per esempio al ritorno in primo piano |
| Risparmio energetico | ? | la specifica ammette il rifiuto (`NotAllowedError`) con la batteria scarica o il risparmio acceso; su iOS da provare [V] |

**Il difetto**: la pagina chiedeva il wake lock dopo `getUserMedia`, la creazione del contesto
audio e il caricamento dell'AudioWorklet: a quel punto il gesto era finito e WebKit poteva dire
no (l'avviso c'era, ma nella riga degli avvisi che altri messaggi sovrascrivono). Su iOS < 18.4
in Edge o nella web app non c'era comunque niente da fare.

**Ora** (`calliope/schermi/pagina/telefono/schermo-acceso.js`, `SchermoAcceso`):
- la richiesta parte **subito nel tocco** su «Microfono acceso» (prima di ogni attesa); un
  blocco tolto dal sistema a pagina visibile si richiede da solo, uno negato al tocco dopo
  (qualunque punto della pagina); col microfono spento si lascia;
- `diagnosi` riconosce dall'user agent i casi in cui non può funzionare (niente API su iOS <
  18.4, web app su iOS < 18.4 che «riesce» senza tenere) e l'indicatore lo dice con il perché e
  il rimedio (aggiornare iOS, aprire in Safari o nel browser, Blocco automatico «Mai»);
- indicatore discreto sotto l'interruttore: «Schermo acceso» o «Lo schermo può spegnersi, e
  allora Calliope smetterà di ascoltare: …»; opzione per non tenerlo acceso;
- **vista da guida**: con lo schermo sempre acceso conviene consumare e abbagliare poco. Fondo
  nero (sugli OLED come l'iPhone 13 mini i pixel neri sono spenti), colori spenti, solo lo stato
  della voce grande (forma e colore), l'ultima risposta (coda di ~300 caratteri), «Parla» su
  ~30 % dello schermo, «Microfono» ed «Esci»; nessuna animazione (anche quelle degli stati) e il
  resto della pagina in `display: none`. Si apre con il pulsante o da sola dopo 90 s di
  microfono acceso senza tocchi (spegnibile).

**Ripiego non fatto**: il video muto in loop in `playsinline` (il trucco di NoSleep.js) per
WebKit senza wake lock. Non si è potuto misurare se serve né se funziona ancora (servirebbe un
iPhone con iOS < 18.4); con iOS 18.4 o successivo, il caso dell'iPhone 13 mini aggiornato, non
serve. Se la prova sull'iPhone (`prove/LEGGIMI.md`, «Prova manuale del telefono» 9) mostra lo
schermo che si spegne con «Schermo acceso», è il passo successivo: un file video servito dalla
pagina (la CSP vieta i `data:` per i media).
