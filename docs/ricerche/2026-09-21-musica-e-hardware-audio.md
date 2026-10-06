# Musica in casa e hardware audio per le stanze (stato al 21 settembre 2026)

*Ricerca svolta da un agente il 21 settembre 2026 per le decisioni F e G di docs/visione.md.*

Parte dalla ricerca precedente ([`2026-09-21-home-assistant-e-satelliti.md`](2026-09-21-home-assistant-e-satelliti.md)) e non la ripete. Nessun altro file è stato modificato.

Affidabilità: versioni, funzioni e limiti vengono da documentazione ufficiale, GitHub e changelog, letti oggi. I prezzi vengono da negozi e comparatori (idealo, pagine prodotto) letti oggi, ma cambiano in fretta. Le esperienze d'uso (wake word con la musica accesa) vengono da forum, issue e recensioni: sono poche, discordanti e le segnalo come tali. Dove scrivo "dedotto" o "da verificare" vuol dire che non ho trovato una fonte diretta.

---

## 0. In breve

1. **Server musicale: Music Assistant (MA) 2.10.x, come app/add-on sul Raspberry Pi dove gira già Home Assistant** (serve un Pi 4 o 5 con almeno 4 GB). La raccolta resta sul server Calliope, esposta come **condivisione SMB** di Windows: MA la monta da solo. Tutto funziona in LAN senza internet.
2. **Musica per persona: si può fare già oggi** con una sorgente "File locali" per ogni cartella personale più il filtro delle sorgenti per utente (MA 2.7+). **Sorpresa positiva:** nelle nightly di MA 2.11 sono già entrate le *sorgenti personali* e le *playlist private* per ogni membro della famiglia (epic "Personal music sources" chiuso a settembre 2026). I *preferiti* (il cuore) restano invece condivisi: i manutentori hanno detto no alle librerie per utente.
3. **Calliope comanda MA come tool** tramite l'API JSON-RPC con token per utente (client Python ufficiale `music-assistant-client`, puro Python) oppure tramite il **server MCP integrato in MA** (plugin "FastMCP Server", su `/mcp/v1`). "Metti la mia musica" = Calliope riconosce chi parla e chiede a MA la playlist o la sorgente di quella persona sul player della stanza del satellite.
4. **Regola d'oro per voce + musica: la musica della stanza deve uscire DAL satellite** (jack del Voice PE, amplificatore del Satellite1, jack dell'XVF3800). Solo così il chip XMOS conosce il segnale riprodotto, lo sottrae (AEC) e sente la wake word sopra la musica; il ducking avviene sul dispositivo, in pochi millisecondi. Con casse di rete separate (Sonos, WiiM, AirPlay, TV) il satellite sente la musica come rumore e si può abbassare il volume solo *dopo* che la wake word è stata sentita.
5. **Per iniziare (una stanza): Voice PE (~65 €) + casse attive Edifier R1280DB (~100–110 €) + alimentatore USB-C (~8 €) ≈ 175–185 €.** Estensione a 5 stanze in fascia "buona": circa **650–800 €**.
6. **Rischi principali:** Sendspin (il nuovo protocollo multi-stanza di MA) è ancora "technical preview"; il Voice PE è "Preview" e nei negozi italiani oggi è esaurito; la RAM dell'ESP32-S3 è stretta con Sendspin + wake word personalizzata; nessuno di questi satelliti sente la wake word a volume "da festa".

---

## 1. Music Assistant nel 2026

### 1.1 Versione e stato

| Voce | Stato al 21/09/2026 |
|---|---|
| Ultima stabile | **2.10.4** (18 settembre 2026). La 2.10 è uscita il 26 agosto 2026. |
| In sviluppo | **2.11.0.dev** (nightly del 21/09/2026): sorgenti musicali personali con condivisione, playlist personali private, ruoli utente personalizzati, volume degli annunci coerente sui gruppi. |
| Ritmo | 2.7 (dic 2025), 2.8 (25 mar 2026), 2.9 (10 giu 2026), 2.10 (26 ago 2026): una versione ogni 2–3 mesi. |
| Chi lo mantiene | Open Home Foundation (la stessa di Home Assistant). Progetto molto attivo. |

Novità rilevanti per Calliope, versione per versione:
- **2.7**: login e **gestione utenti** (anche con single sign-on di Home Assistant), sorgenti e player consentiti per utente, documentazione API generata su `http://<server>:8095/api-docs`.
- **2.8**: *Player Merging* (una sola voce per una cassa vista con più protocolli), **Sendspin Bridges** (dispositivi Cast e AirPlay, quindi anche Sonos, raggruppabili in sincrono con gli altri), modalità festa con ospiti via QR, generi, sorgente "NFS", SomaFM.
- **2.9**: analisi audio locale (Smart Fades, somiglianza sonora, "radio" dalla raccolta locale), scorciatoie per utente, **limiti di volume minimo/massimo per player**, provider player **WiiM** e **MPD**, WebDAV.
- **2.10**: audio Sendspin **cifrato** e protocollo "vicino alla v1", Sendspin bidirezionale, Autoplay e Smart Shuffle, quiz musicale, plugin "AI Radio DJ", nuovi player (Bose SoundTouch, AmpliPi), sorgenti Google Drive/OneDrive.

### 1.2 Libreria locale

- Formati: FLAC, MP3, MP4/AAC, OGG, Opus e altri comuni.
- Sorgente "File locali" su disco locale oppure **condivisione remota SMB/CIFS (1.0–3.1.1), NFS, WebDAV**: MA monta la condivisione da solo, senza configurare nulla in Home Assistant.
- **Si possono aggiungere più sorgenti "File locali"** (documentato): è la base della divisione per persona.
- Tag: MA **pretende il tag Album Artist**; senza, il brano finisce sotto "Various Artists". Consigliati MusicBrainz Picard e gli ID MusicBrainz. Struttura consigliata `artista/album`, nomi di cartella senza caratteri speciali ("AC/DC" → "ACDC"). Su SMB non sono supportati emoji e caratteri strani nei nomi; i nomi non UTF-8 vengono saltati.
- Playlist: i file **M3U** vengono importati; per crearli o modificarli da MA la condivisione deve essere scrivibile.
- Copertine: incorporate oppure `cover.jpg` / `folder.jpg`; per l'artista `artist.jpg`, `fanart.jpg`, `logo.png`.
- **ReplayGain / R128**: se i tag ci sono MA li usa (traccia e album), altrimenti misura da sé.

### 1.3 Streaming e radio

| Tipo | Provider (elenco ufficiale letto oggi) | Costo |
|---|---|---|
| Streaming a pagamento | Spotify, Apple Music, Tidal, Qobuz, Deezer, YouTube Music, Pandora, SiriusXM, Yandex Music | Serve l'abbonamento al servizio |
| Radio | **Radio Browser**, TuneIn, Radio Paradise, SomaFM, BBC Sounds, ARD, ORF, DI.fm, NTS, Mamma Mi Radio, Sveriges Radio, ABC… | Gratis (serve internet) |
| Server propri | **Subsonic/OpenSubsonic (quindi Navidrome)**, Jellyfin, Plex, Emby | Gratis |
| Altro | SoundCloud, Bandcamp, Internet Archive, podcast (RSS, Pocket Casts…), audiolibri (Audiobookshelf, Audible, Storytel) | Vario |

Dalla 2.7 ogni utente può avere il **proprio account** di streaming; con la 2.11 ogni membro potrà gestirselo da solo e decidere con chi condividerlo.

### 1.4 Senza internet

- MA è un server locale: interfaccia su porta 8095, scoperta dei player via mDNS/UPnP in LAN, file letti da disco o SMB. La documentazione dice che internet non è richiesto per il funzionamento di base, mentre sorgenti online e metadati ne beneficiano.
- Senza rete non funzionano: streaming, radio, metadati e copertine scaricati (MusicBrainz, fanart), login dei provider cloud. **Non esiste cache offline dei brani in streaming** (richiesta aperta, non realizzata).
- Non ho trovato un resoconto esplicito di "MA usato per giorni senza internet": va provato staccando il router durante la validazione (vedi §6.1).

### 1.5 Multi-stanza e player supportati

Elenco ufficiale dei provider player (21/09/2026): AirPlay, Alexa, AmpliPi, Bluesound, Bose SoundTouch, DLNA, Fully Kiosk, Google Cast, HEOS, player di Home Assistant (quindi ESPHome), MPD, MSX Bridge, MusicCast, Roku, Samsung WAM, **Sendspin**, **Snapcast**, **Sonos** (S1 e S2), **Squeezelite**, **WiiM**, Yandex Station. "Local Audio Out" è stato ritirato (sostituito dal client Sendspin locale).

| Famiglia | Sincronia | Note per Calliope |
|---|---|---|
| **Sendspin** (Open Home Foundation) | Sì, molto stretta (gli sviluppatori dichiarano errore mediano ~50 µs tra due ESP32-S3 in Wi-Fi) | "Technical preview", **un solo server MA per rete**, audio a 16 bit. Client: Voice PE (firmware recente), Satellite1 (dal firmware 0.2.0), schede ESP32-S3 con ESPHome ≥ 2026.5, LVA su Raspberry, browser, app desktop Windows/macOS/Linux, bridge per Cast/AirPlay/Bluetooth. |
| ESPHome via Home Assistant (HTTP) | **No** | Funziona sempre, ma senza sincronia e con funzioni limitate: "preferire sempre il provider nativo". |
| Sonos | Sì tra Sonos della stessa serie; con AirPlay anche con altri | Locale, niente cloud. Crossfade non disponibile con FLAC. |
| AirPlay / WiiM | Sì tra AirPlay e WiiM | WiiM: raggruppamento con limiti (brano che riparte, silenzio se il modello non ha AirPlay). WiiM non supporta Sendspin (richiesta aperta sul loro forum). |
| Google Cast | Gruppi Cast; via Sendspin Bridge (sperimentale) anche con altri | I dispositivi Cast senza internet sono inaffidabili (da verificare, vedi §9). |
| Squeezelite / Snapcast | Sì, maturi | Utili per Raspberry e schede ESP32 con firmware squeezelite. |
| **Alexa / Echo** | No | Richiede skill Alexa, account sviluppatore Amazon ed endpoint HTTPS pubblico: **non funziona offline → escluso**. |

### 1.6 API e MCP: come lo comanderebbe Calliope

| Via | Cosa offre | Giudizio |
|---|---|---|
| **API JSON-RPC** (`POST /api`, e WebSocket) | Tutti i comandi (ricerca, `play_media`, code, volume, gruppi). Autenticazione con **token a lunga durata** creato nel profilo utente, header `Authorization: Bearer`. Documentazione su `/api-docs`. | Stabile di fatto, ma non è dichiarata "API pubblica con garanzie". |
| **`music-assistant-client`** (PyPI) | Client Python asincrono ufficiale (aiohttp), tipizzato, con `login_with_token()`. | **Consigliato**: puro Python, nessuna dipendenza nativa, va bene anche su Windows ARM. |
| **Plugin "FastMCP Server"** | MA stesso fa da server MCP su `/mcp/v1` (stesso webserver, nessuna porta in più). Token per client, 29 permessi attivabili (lettura, controllo, modifica, cancellazione, debug, config). | Coerente con la decisione C (MCP come standard dei tool). "Early stage": possibili bug. |
| Server MCP della community | `jakekeeys/music-assistant-mcp`, `shuricksumy/MCP-MusicAssistant`, `davidpadbury/music-assistant-mcp` | Alternativa se il plugin ufficiale non convince. |
| Tramite Home Assistant | Azioni `music_assistant.play_media`, `search`, `play_announcement`… | Utile per automazioni; per Calliope è un giro in più. |

**Identità**: i token appartengono a un utente MA. Calliope può tenere **un token per ogni membro della famiglia** (più uno "ospite") e usare quello di chi sta parlando: i filtri di sorgenti e player di quell'utente valgono allora automaticamente. (Dedotto dalla documentazione; da provare.)

### 1.7 Controllo vocale già esistente in Home Assistant

- Da HA **2025.6** l'intento "Search and Play" è integrato: "riproduci Rumours in cucina". Se non si nomina la stanza, HA usa **l'area del satellite a cui si è parlato**. Parte il primo risultato della ricerca (libreria e provider insieme).
- Le frasi italiane esistono nel repository degli intenti (`HassMediaSearchAndPlay`, `HassMediaPause`, `HassMediaNext`, `HassSetVolume`, `HassMediaPlayerMute` in `sentences/it`).
- Per richieste più ricche ci sono i blueprint di `music-assistant/voice-support` (frasi locali, LLM, script come tool per LLM), tradotti anche in italiano.
- **Limite per Calliope**: gli intenti nativi non sanno *chi* parla e non applicano i permessi di Calliope (ospiti). Conviene lasciare a HA i comandi innocui e veloci (pausa, avanti, volume) e far passare da Calliope tutto ciò che *avvia* la musica.

### 1.8 Più utenti e librerie per persona

Cosa c'è **oggi (2.10.x)**:
- Utenti con ruoli, login, token; per ogni utente si può **limitare l'elenco delle sorgenti musicali e dei player**. Con il filtro attivo, quell'utente vede e usa solo quelle sorgenti.
- Scorciatoie per utente; progressi di podcast/audiolibri per utente.
- **Libreria unica**: preferiti, elementi "in libreria" e raccomandazioni sono condivisi. Alla richiesta "preferiti separati per utente" (discussione #5444, maggio–giugno 2026) il manutentore ha risposto che il capo progetto **ha deciso di non fare librerie per utente**; il ripiego ufficiale è "più istanze di MA" — che però **non è compatibile con Sendspin** (un solo server per rete).
- Attenzione: se si rimuove una sorgente e un utente resta senza filtri, quell'utente **vede di nuovo tutto** (documentato).

Cosa **sta arrivando (2.11, già nelle nightly)**:
- **Sorgenti musicali personali**: ogni sorgente ha un proprietario e una condivisione (nessuno / alcuni membri / tutti i membri / chiunque); la riproduzione usa prima l'account di chi chiede e mai una sorgente non condivisa (epic backlog #84, 10 sotto-attività su 10 chiuse).
- **Playlist personali**: "una playlist che crei è tua: privata per impostazione predefinita, condivisibile con la famiglia" (backlog #90; PR server #6325 unita il 14/09/2026).

**Come ottenere "la mia musica" — ricetta consigliata (funziona già con la 2.10):**
1. Sul server Calliope: `Musica\comune`, `Musica\dario`, `Musica\elena`… (vedi §7).
2. In MA: una sorgente "File locali (condivisione remota)" **per ogni cartella**, con nome parlante ("Musica di Dario").
3. In MA: un utente per ogni persona, limitato a *la sua sorgente + comune*; un utente "ospite" limitato a *comune* e ai player delle zone giorno; un utente di servizio "calliope" che vede tutto.
4. Per i gusti personali usare **playlist** ("Preferiti di Dario", file M3U nella cartella personale oppure playlist private dalla 2.11), non il cuore.
5. Calliope traduce "metti la mia musica" in: *token della persona riconosciuta* + *playlist predefinita di quella persona* (o "riproduci a caso dalla sorgente X") + *player dell'area del satellite*.

Alternative scartate: più istanze di MA (rompe Sendspin, raddoppia tutto); solo tag/genere per persona (fragile); Navidrome come archivio per utente dietro MA (possibile e pulito, ma è un componente in più: vedi §3).

### 1.9 Dove gira e requisiti

- **App/add-on di Home Assistant OS** (via consigliata e pienamente supportata, anche in VM) oppure **container Docker con `--network host`**. In rete bridge la scoperta dei player non funziona ed è "non supportato".
- Deve stare **sulla stessa rete di livello 2 dei player** (niente VLAN in mezzo): usa multicast (mDNS, UPnP).
- Hardware: 64 bit; **Raspberry Pi 4 o superiore** (il Pi 3 è escluso); **minimo 2 GB di RAM, 4 GB o più se sulla macchina gira altro** (cioè Home Assistant); le funzioni di analisi audio (Smart Fades) chiedono almeno 4 GB.
- Non dipende da Home Assistant: ha la sua interfaccia web sulla porta 8095.

---

## 2. Dove far girare il server musicale: Raspberry Pi o server Calliope?

Caso tipico: Home Assistant già in casa su un Raspberry Pi con HAOS (modello e RAM da verificare).

| Criterio | **A. App/add-on sul Raspberry Pi accanto a HA** | B. Sul server Calliope (Windows oggi, Windows su ARM domani) |
|---|---|---|
| Supporto ufficiale | Pieno (HAOS è la via raccomandata) | Nessuno: la documentazione non cita Windows, Docker Desktop o WSL |
| Rete | Host networking nativo: scoperta mDNS/UPnP, Sendspin, AirPlay, Sonos funzionano | **Docker Desktop su Windows ha un "host networking" solo di livello 4 (TCP/UDP), senza accesso alle interfacce**: niente livello 2, quindi scoperta dei player compromessa. Un utente nel 2024 non raggiungeva nemmeno l'interfaccia web. WSL2 "mirrored" dichiara il multicast ma ha issue aperte. Unica via solida: **VM Hyper-V con switch esterno** (in bridge). |
| Windows su ARM (Spark) | Indifferente | Docker Desktop ARM64 esiste; Hyper-V su ARM accetta solo guest ARM64 ed è meno maturo. Un'incognita in più proprio dove ce ne sono già tante. |
| Risorse | MA smista flussi audio: carico modesto. L'analisi audio è pesante: sul Pi va disattivata o lasciata lavorare di notte | Ruberebbe poco, ma aggiunge una VM sempre accesa accanto a LLM, STT e TTS |
| Sempre acceso | Sì, il Pi lo è già | Il portatile di oggi no |
| Guasti | Se il Pi muore, cadono HA e musica insieme (ma cadrebbero comunque i satelliti) | Se il server è spento, niente musica *e* niente Calliope |
| Costo | 0 € se il Pi è adeguato | 0 €, ma molte ore di lavoro |

**Scelta consigliata: A, Music Assistant come app sul Raspberry Pi, con la raccolta sul server Calliope montata via SMB.**

Perché: è l'unica configurazione supportata, mette MA sulla stessa macchina e sulla stessa rete di HA e dei satelliti, non dipende dalle stranezze di rete di Windows/WSL2 (che sullo Spark sarebbero un'incognita ulteriore) e non tocca la GPU. Calliope parla con MA via rete (API/MCP): spostare Calliope sullo Spark non cambia nulla per la musica.

**Requisiti minimi del Pi**
- **Pi 4 o Pi 5 con 4 GB** (o più). Con 2 GB è il minimo dichiarato ma, con HA sopra, ci sono segnalazioni di riproduzione a scatti (discussione #3857, Pi 4 da 2 GB). **Pi 3 o meno di 2 GB: da sostituire** (Pi 5 4 GB ≈ 110 € oggi, dopo i rincari delle RAM; in alternativa un mini PC N100).
- Meglio **SSD** che scheda SD (database e cache di MA scrivono spesso — buona pratica, non requisito documentato).
- HA ≥ 2026.8 per l'agente compatibile OpenAI (dalla ricerca precedente). Se sul Pi gira "HA Container" anziché HAOS, MA si installa come container Docker con `--network host` (su Linux funziona).

**Dove mettere gli MP3**

| Opzione | Pro | Contro |
|---|---|---|
| **Condivisione SMB dal server Calliope** (consigliata) | La raccolta sta dove il proprietario la vuole; condivisione nativa di Windows (anche su ARM), nessun software in più; MA la monta da sé; backup in un posto solo | Se il server è spento non c'è musica locale (oggi il server è un portatile). Usare IP fisso o prenotazione DHCP e un account locale di sola lettura per MA (più una cartella scrivibile per le playlist). |
| Disco USB sul Pi | Musica disponibile anche a server spento | In HAOS le app vedono solo `/media`; per un disco USB serve l'app community "Samba NAS" o spostare il disco dati: più macchinoso. La raccolta "vera" non starebbe più sul server. |
| Copia sincronizzata (server → disco del Pi) | Il meglio dei due | Complessità; da considerare solo se il portatile spento diventa un problema reale prima dell'arrivo dello Spark |

Tutto il percorso (satellite → HA → Calliope → MA → SMB → player) resta in LAN: **nessun passaggio richiede internet**.

---

## 3. Alternative a Music Assistant

| | Versione (2026) | Librerie per utente | API | Multi-stanza | Leggerezza | Stato | Adatto a Calliope? |
|---|---|---|---|---|---|---|---|
| **Music Assistant** | 2.10.4 (18 set) | Filtri sorgenti per utente; sorgenti e playlist personali in 2.11; preferiti condivisi | JSON-RPC/WebSocket, client Python, **MCP integrato** | **Sì**, su quasi tutto (Sendspin, Sonos, AirPlay, Cast, Squeezelite, Snapcast…) | Media (Python; Pi 4 con 4 GB) | Molto attivo (OHF) | **Sì: è l'unico che unisce satelliti, streaming, radio e multi-stanza** |
| **Navidrome** | 0.64.0 (12 set) | **Sì, vere**: multi-libreria con accesso per utente (da 0.58); playlist, preferiti e conteggi per utente | Subsonic/OpenSubsonic; API Jellyfin sperimentale | No (è un server di libreria; i client riproducono) | **Molto leggero** (un binario Go) | Molto attivo | Come **archivio per persona dietro MA** (provider Subsonic) e per ascoltare dal telefono (app Subsonic). Piano B elegante. |
| **Jellyfin** | 12.0 (7 set; nuova numerazione) | Sì (accesso alle librerie e playlist per utente) | REST | No per le casse | Pesante (.NET + ffmpeg) | Molto attivo | Solo se in casa serve già per i video. MA lo legge come provider. |
| **Lyrion (ex LMS)** + squeezelite | 9.1.0 (feb), 9.2 in anteprima | No utenti; "librerie virtuali" per player (a memoria, non riverificato) | JSON-RPC / CLI | **Sì, maturo e solido** | Leggero (Perl); gira anche su Windows 64 bit | Attivo (community) | Alternativa seria se Sendspin deludesse; ma niente satelliti vocali, niente streaming moderno integrato come in MA |
| **MPD + Snapcast** | Snapcast 0.35.0 (mar) | No (un'istanza MPD per persona) | Protocollo MPD + JSON-RPC Snapcast | Sì, ottima sincronia | Leggerissimo | Attivo | Fai-da-te puro: tutto il collante sarebbe a carico di Calliope |
| **OwnTone** | 29.1.1 (15 apr) | No | JSON + MPD | Sì via AirPlay 1/2 e Chromecast | Leggero; solo Linux | Attivo | Solo per case tutte AirPlay |
| **Plex / Plexamp** | non verificato | Sì (utenti gestiti) | REST proprietaria | Limitato | Medio | Commerciale | **No**: autenticazione legata a plex.tv, in contrasto con "prima di tutto offline" |

Conclusione: **Music Assistant resta la scelta**. Navidrome è il complemento naturale se si vorranno preferiti davvero personali o l'ascolto dal telefono; Lyrion è il piano di riserva per la sola sincronia multi-stanza.

---

## 4. Voce e musica insieme (il punto delicato)

### 4.1 Due architetture, due risultati

| | **Caso 1 — la musica esce dal satellite** | **Caso 2 — la musica esce da un player di rete separato** |
|---|---|---|
| Esempi | Voice PE → jack → casse attive; Satellite1 (ampli interno o jack); XVF3800 → jack o altoparlante; Raspberry con LVA + XVF3800 USB | Sonos, WiiM, AirPlay, Chromecast, soundbar/TV, cassa Bluetooth; microfono/satellite a parte |
| Il DSP conosce il segnale riprodotto? | **Sì**: l'audio passa dal chip XMOS prima del DAC, che lo usa come riferimento per l'AEC | **No**: per i microfoni la musica è rumore qualunque |
| Wake word con musica accesa | Possibile a volume moderato; degrada a volume alto | Degrada molto prima; il beamforming a 4 microfoni aiuta poco perché la musica non è rumore stazionario |
| Ducking | **Sul dispositivo, immediato**: il firmware ESPHome abbassa il canale "media" di 20 dB quando parte l'assistente e lo rialza alla fine; la risposta TTS è mixata sopra la musica abbassata | Solo **dopo** la wake word, via rete: blueprint HA "Satellite to media_player volume ducking" (si attiva quando il satellite passa a "listening", abbassa il player della stessa area, ripristina a fine dialogo; un solo player per area) oppure Calliope stessa via API di MA |
| Barge-in (wake word mentre Calliope parla) | Sì (già nel firmware; esiste anche un firmware community che riapre il microfono a eventi) | Sì solo se la voce esce dal satellite e la musica è abbassata |

**Conseguenza di progetto:** nelle stanze dove si ascolta musica, le casse vanno **collegate via cavo al satellite**. I player di rete (Sonos, WiiM) si usano dove esistono già o dove l'hi-fi conta più della voce, sapendo che lì la wake word con la musica alta funzionerà male.

### 4.2 Limiti del caso 1 da conoscere

- **Casse sul jack: solo via cavo e senza ritardi.** Un trasmettitore Bluetooth o una soundbar con elaborazione digitale dopo il jack introducono 100–300 ms e distorsioni che l'AEC non compensa (principio generale dell'AEC; il valore massimo tollerato dal firmware XMOS non l'ho trovato).
- **La manopola del volume delle casse** cambia il percorso acustico: la documentazione XMOS dice che se il volume degli altoparlanti cambia senza che cambi il riferimento, l'AEC deve riconvergere. Meglio fissare la manopola e regolare il volume da MA (che agisce *prima* del riferimento).
- **Sul Voice PE, inserendo il jack l'altoparlante interno si spegne** (comportamento hardware): anche la voce di Calliope esce dalle casse esterne. Servono quindi casse **sempre accese, senza auto-standby aggressivo**, altrimenti si perdono le prime sillabe. Da controllare prima dell'acquisto.
- Cavo jack scadente o alimentatore debole → fruscii e clic sincronizzati con i LED (forum HA, dicembre 2024: risolto cambiando cavo).
- **RAM dell'ESP32-S3**: con ESPHome 2026.3.x il nuovo stack audio/Sendspin ha lasciato senza memoria `micro_wake_word` su alcuni Voice PE (core #167989). I firmware 26.4.0 e 26.6.0 hanno migliorato stabilità e sincronia di Sendspin. Un modello personalizzato "Calliope" + "stop" + VAD + Sendspin + due flussi FLAC è un carico al limite: **da provare presto**.

### 4.3 Esperienze reali trovate (poche e discordanti)

| Fonte | Dispositivo | Cosa dice |
|---|---|---|
| Recensione Botmonster, 16/07/2026 | Voice PE | Mancati riconoscimenti "sotto il 5 % a tre metri" in stanza quieta; **20–25 % con la cappa a media velocità**. Altoparlante interno "sottodimensionato per la musica". |
| Forum HA, thread "Very low wake word detection…", gen–feb 2025 | Voice PE | Esperienze opposte: chi deve stare entro 1,5 m e alzare la voce, chi ha troppi falsi positivi; Alexa giudicata nettamente migliore sopra l'audio della TV. Un contributo tecnico attribuisce il problema ai dati di addestramento del modello, non all'hardware. |
| Issue Satellite1-ESPHome #551, 04/09/2026 (aperta, senza risposta) | Satellite1 (4 unità) | Con TV, podcast o ventilatori non trova una soglia: o bisogna urlare o scattano falsi risvegli; deve mettere in pausa per farsi sentire. |
| Smart Home Circle, 22/01/2026 | ReSpeaker XVF3800 | Wake word affidabile da ~3 m senza guardare il dispositivo, meglio del Voice PE; **vicino alla TV accesa le prestazioni calano** (è il caso 2: nessun riferimento). |
| Creating Smart Home, 12/04/2026 | ReSpeaker XVF3800 | Cattura fino a 5 m, perfino nascosto nel controsoffitto; 4 microfoni "molto meglio" del Voice PE; altoparlantino da 5 W "non adatto alla musica". |
| How-To Geek, 14/06/2026 | LVA su portatile, wake word personalizzata addestrata in ~1 ora | "Ha funzionato praticamente sempre, **anche con la musica accesa**". |
| Pagina prodotto FutureProofHomes | Satellite1 | Dichiara di "sentire sopra la musica" grazie all'XMOS (affermazione del produttore). |

Lettura onesta: con la musica a volume di sottofondo e le casse sul jack ci si può aspettare che funzioni; **nessuna di queste soluzioni è al livello di un Echo**, e a volume alto bisogna avvicinarsi, alzare la voce o usare il tasto del satellite. Una wake word personalizzata ben addestrata (voci italiane, campioni con musica di sottofondo tra i negativi) pesa più dell'hardware.

### 4.4 Cosa deve fare Calliope

- **Annunci spontanei** (timer, lavoro in secondo piano finito): `assist_satellite.announce` sul satellite, che abbassa da solo la propria musica. Sui player di rete: `music_assistant.play_announcement` (abbassa o mette in pausa e poi riprende; la 2.11 sistema il volume degli annunci sui gruppi).
- **Caso 2**: appena arriva l'audio allo STT, Calliope (o il blueprint) abbassa il player dell'area; a fine risposta lo ripristina. Impostare in MA un **volume massimo per player** (2.9) nelle stanze con microfono separato.
- **Multi-stanza**: se un gruppo suona in sincrono e si parla al satellite della cucina, si abbassa solo la cucina (il ducking è locale). Va bene così.
- Il principio 8 (half-duplex) resta vero: l'interruzione avviene con la wake word o con "stop", non parlando sopra.
- **Sapere chi parla e dove**: l'identità nasce nello STT di Calliope (che riceve l'audio via Wyoming), ma HA manda poi il testo all'agente di conversazione con una chiamata separata. Calliope dovrà **correlare trascrizione e richiesta** (stesso testo, pochi istanti dopo) per sapere chi ha parlato; l'area del satellite va ricavata da ciò che HA passa all'agente. Entrambe le cose sono da verificare nella fase 4.

---

## 5. Hardware per stanza

### 5.1 Componenti e prezzi rilevati oggi

**Satelliti e microfoni**

| Prodotto | Prezzo | Dove (Italia/UE) | Note |
|---|---|---|---|
| **HA Voice Preview Edition** | 57,95 € HomeBrainz (IT) **esaurito**; 59,00 € DinamoTech (IT) **esaurito**; **64,90 € BerryBase (DE), disponibile, 5–10 giorni per l'Italia** | anche Domo-Supply (FR), Seeed | Alimentatore USB-C 5 V/2 A **non incluso** (~8 €). 2 microfoni, XMOS XU316, jack con DAC dedicato. |
| **ReSpeaker XVF3800 + XIAO ESP32S3** | 64,90 $ con custodia (Seeed, disponibile, magazzino anche in Germania); 72,48 € IVA inclusa da Antratek (NL); a listino anche Reichelt e Botland | — | 4 microfoni, beamforming, fino a 5 m. Uscite: jack 3,5 mm e connettore JST per altoparlante 5 W. Esiste anche la versione solo USB (per Raspberry/PC). |
| **FutureProofHomes Satellite1.1 Smart Speaker** | 134,99 $ assemblato, con alimentatore USB-C PD 30 W (spina UE) e cavo; "spedizione a tariffa fissa, nessun costo alla consegna" | futureproofhomes.net (USA) | 4 microfoni, XU316, ampli 20 W, woofer 3" + tweeter, 11×11×18 cm. Spesso in arretrato. |
| Satellite1.1 Dev Kit | 69,99 $, **in arretrato fino al 15/11/2026** | idem | Ampli mono 25 W + **uscita linea su jack (DAC PCM5122)**; custodia e altoparlante a parte. |
| Raspiaudio **Muse Luxe v2** | 59,90 € | raspiaudio.com (FR), Amazon | Cassa portatile ESP32 con batteria, 2×5,5 W, **un solo microfono, nessun AEC hardware**; firmware ESPHome (assistente vocale, Sendspin) e squeezelite dalla community. |
| Jabra Speak 510 (USB/Bluetooth) | 80–86 € (idealo) | Amazon, idealo | Vivavoce con AEC hardware. Audio mono da conferenza: non per la musica. |
| Raspberry Pi | 1–2 GB: circa 30–57 €; **Pi 5 4 GB: ~110 €** dopo i rincari delle RAM (tre aumenti tra dicembre 2025 e aprile 2026) | rivenditori ufficiali | Per satelliti LVA o come nuovo host di HA. |
| Schede Sonocotta (Louder/Amped/HiFi-ESP32) | non verificato (circa 25–60 $) | Tindie, Elecrow, Lectronz | Player-amplificatori ESP32 con ESPHome/Sendspin, **senza microfoni** (caso 2). |

**Casse e player**

| Prodotto | Prezzo | Note |
|---|---|---|
| **Edifier R1280DB** | 99–109 € (idealo) | Coppia attiva 42 W, 2 ingressi AUX + ottico + Bluetooth. Buona resa per stanza media. |
| **Edifier R1280DBs** | 129 € (idealo, 17/09/2026) | Come sopra + uscita subwoofer. |
| Casse da scrivania compatte (tipo Creative Pebble) | ~35–45 € (non verificato oggi) | Per camera/studio, molto meglio dell'altoparlantino del Voice PE. |
| **Sonos Era 100** | 175–229 € (idealo; listino 279 €); Era 100 SL (senza microfoni) ~197 € | Player locale ben supportato da MA. Caso 2. |
| WiiM Mini / Pro | 97–99 € / ~163 € | Streamer da collegare a un impianto esistente. Caso 2. |
| WiiM Amp / Amp Pro / Ultra / Amp Ultra | 369 € / 419 € / 385 € / 526 € | Amplificatori di rete per diffusori passivi. Caso 2. |
| WiiM Sound Lite | 234–269 € | Cassa di rete. Segnalati problemi con il bridge Sendspin→Cast (MA support #5247). |

### 5.2 Proposte in tre fasce

Legenda: **AEC** = il satellite conosce il segnale riprodotto (caso 1). Difficoltà: ★ pronto all'uso · ★★ firmware da caricare via USB/browser · ★★★ Linux o assemblaggio.

#### Stanza piccola (camera, studio)

| Fascia | Componenti | Costo | Ascolto da lontano | Musica | AEC / barge-in | Alimentazione | Difficoltà | Rischi |
|---|---|---|---|---|---|---|---|---|
| Economica | Voice PE + casse compatte da scrivania sul jack + alimentatore USB-C | ~110–120 € | Buono fino a 3 m in silenzio | Discreta | Sì / sì con wake word | USB-C 5 V + presa casse | ★ (★★ per la wake word "Calliope") | "Preview", scorte; casse con auto-standby |
| Ultra-economica, con riserva | Raspiaudio Muse Luxe | ~60 € | **Solo da vicino** (1 microfono, niente AEC) | Da cassa portatile | No | USB-C / batteria | ★★ | Firmware community; adatta a una cameretta, non come riferimento |
| Buona | Voice PE + Edifier R1280DB | ~175–185 € | Come sopra | **Buona** | Sì | Come sopra | ★ | Come sopra |
| Ottima | Satellite1.1 Smart Speaker (tutto in uno) | 134,99 $ + spedizione (≈ 125–150 €, non verificato) | Molto buono (4 microfoni) | Buona "da smart speaker" (20 W, 2 vie) | Sì | USB-C PD 30 W incluso | ★ (firmware già pronto; Sendspin dal fw 0.2.0) | Piccola azienda USA, arretrati frequenti, firmware 0.2.x, issue #551 sulla wake word nel rumore |

#### Stanza grande o rumorosa (soggiorno, cucina)

| Fascia | Componenti | Costo | Ascolto da lontano | Musica | AEC / barge-in | Difficoltà | Rischi |
|---|---|---|---|---|---|---|---|
| Economica | Voice PE + Edifier R1280DB | ~175–185 € | Sufficiente; con cappa/TV 20–25 % di mancati risvegli | Buona | Sì | ★ | 2 soli microfoni in ambiente rumoroso |
| **Buona** | **ReSpeaker XVF3800 + XIAO (con custodia) + Edifier R1280DBs sul jack** | ~200–210 € | **Il migliore** (4 microfoni, beamforming, 5 m) | Buona | Sì (audio attraverso il codec della scheda) | ★★ (flash ESPHome + aggiornamento firmware XMOS; nessuna saldatura con lo XIAO già montato) | Firmware della community (formatBCE / YAML Seeed): media player con ducking sì, **supporto Sendspin/MA non verificato**; nessun tasto fisico; vicino alla TV rende meno |
| Ottima | Satellite1 (Smart Speaker usato come microfoni + uscita linea, oppure Dev Kit con custodia) → **impianto hi-fi esistente o casse attive di livello** (ingresso AUX) | ~150 € + casse (150–400 €) | Molto buono | **Ottima** (dipende dalle casse; DAC PCM5122) | Sì, purché il collegamento sia via cavo | ★–★★ | Dev Kit in arretrato fino a metà novembre; vedi sopra |
| Ottima, alternativa "Linux" | Raspberry Pi 5 (2 GB) + ReSpeaker XVF3800 USB + LVA (fork con Sendspin, ducking e AEC PipeWire) → casse attive sul jack della scheda | ~130–150 € + casse | Il migliore | Ottima | Sì; è la via migliore per il barge-in e permette openWakeWord "Calliope" senza addestrare microWakeWord | ★★★ | LVA è "sperimentale"; più manutenzione |

**Soundbar/TV**: l'audio della TV non è mai noto al satellite (caso 2). Mettere il satellite lontano dalla TV e vicino al divano, abbassare la TV via HA dopo la wake word (blueprint), accettare che con la TV alta serva il tasto o la voce più forte. Non usare la soundbar come cassa del satellite se introduce ritardo.

#### Postazione PC

| Fascia | Componenti | Costo | Note |
|---|---|---|---|
| Economica | Cuffie con microfono già in uso + Calliope client sul PC + **app desktop di Music Assistant** (player Sendspin nativo per Windows, .msi) | 0 € | In cuffia non c'è eco: barge-in gratis. La musica esce dalle cuffie o dalle casse del PC come player MA "PC di Dario". |
| Buona | Jabra Speak 510 via USB per la voce + casse del PC per la musica (app MA) | ~80–86 € | AEC hardware per la voce; la musica del PC non è nel riferimento, ma alla scrivania si parla a 50 cm. |
| Ottima | Voice PE sulla scrivania + Edifier R1280DB condivise (un ingresso AUX al Voice PE, l'altro al PC: i due ingressi sono attivi insieme — da confermare sul modello acquistato) | ~175–185 € | Si comporta come ogni altra stanza e funziona anche a PC spento. L'audio del PC non entra nell'AEC. |

Nota: `linux-voice-assistant` non gira su Windows; sul PC conviene il client proprio di Calliope (quello di oggi) oppure un Voice PE.

### 5.3 Riusare casse esistenti solo come player

| Dispositivo | Con MA | Offline | Giudizio |
|---|---|---|---|
| **Sonos** | Provider nativo, sincronia tra Sonos, AirPlay per gruppi misti | Sì in LAN (da provare) | **Sì**, come caso 2: satellite separato lontano dalla cassa, voce dal satellite, ducking via blueprint o Calliope, volume massimo limitato |
| **WiiM / Arylic / ampli di rete** | WiiM nativo dalla 2.9; Arylic via DLNA/AirPlay (non verificato) | Sì | Sì per l'hi-fi del soggiorno, con i limiti del caso 2 |
| **Nest / Chromecast** | Cast nativo; gruppi misti via Sendspin Bridge (sperimentale) | **Dubbio** (non verificato) | Solo come ripiego |
| **Echo** | Richiede skill Alexa + cloud Amazon + endpoint pubblico | **No** | **Escluso** |

---

## 6. Configurazione consigliata per iniziare, e come estenderla

### 6.1 Prima stanza (validazione) — cucina o soggiorno

| Voce | Prezzo |
|---|---|
| HA Voice Preview Edition (BerryBase, disponibile) | 64,90 € + spedizione |
| Alimentatore USB-C 5 V / 2–3 A | ~8 € |
| Edifier R1280DB (cavo jack–RCA di solito incluso: da controllare) | 99–109 € |
| Music Assistant sul Raspberry Pi esistente | 0 € (se Pi 4/5 con ≥ 4 GB; altrimenti Pi 5 4 GB ≈ 110 € + alimentatore, custodia, SSD) |
| **Totale** | **≈ 175–185 €** (più eventuale sostituzione del Pi) |

Perché il Voice PE per primo: è il più economico, è pronto all'uso, è il dispositivo su cui OHF sviluppa per primo (firmware 26.x con Sendspin), ha la comunità più grande ed è quello su cui provare subito la wake word microWakeWord "Calliope". Le Edifier danno alla musica una resa dignitosa e restano utili qualunque satellite si scelga dopo.

**Cosa validare, in ordine:**
1. MA sul Pi + condivisione SMB dal portatile + una sorgente per persona + utenti con filtri.
2. Voice PE come player Sendspin in MA; musica dal jack; ducking e risposta mixata.
3. **Wake word con la musica a tre volumi** (sottofondo, normale, alto) da 1, 3 e 5 m; con cappa o TV accesa. Annotare i mancati risvegli.
4. Wake word personalizzata "Calliope" insieme a Sendspin: tiene la RAM?
5. **Staccare internet dal router** per un'ora: voce, musica locale, playlist per persona devono continuare.
6. Calliope → MA via `music-assistant-client` con due token di persone diverse: "metti la mia musica" dà risultati diversi?
7. Correlazione tra STT (chi parla) e richiesta dell'agente di conversazione; area del satellite.

Se al punto 3 il Voice PE delude nella stanza rumorosa, il secondo acquisto è un **ReSpeaker XVF3800** (~70 €) da confrontare nella stessa posizione con le stesse casse.

### 6.2 Estensione a 4–5 stanze

| Stanza | Fascia economica | Fascia buona (consigliata) | Fascia ottima |
|---|---|---|---|
| Cucina (già fatta) | 180 € | 180 € | 180 € |
| Soggiorno | Voice PE + R1280DB: 180 € | XVF3800 + R1280DBs: ~205 € | Satellite1 + casse/hi-fi: ~150 € + 250 € |
| Camera matrimoniale | Voice PE + casse compatte: ~115 € | idem ~115 € | Satellite1.1: ~150 € |
| Camera ragazzi | Muse Luxe: 60 € | Voice PE + casse compatte: ~115 € | Satellite1.1: ~150 € |
| Studio / PC | cuffie + app MA: 0 € | Voice PE (casse condivise col PC): ~75 € | Voice PE + R1280DB: ~180 € |
| **Totale indicativo** | **≈ 535 €** | **≈ 690 €** | **≈ 1.060 €** |

Aggiungere circa 30–50 € di spedizioni e cavi, e l'eventuale sostituzione del Raspberry Pi (≈ 130–150 € completo). Conviene **comprare una stanza alla volta**: l'ecosistema cambia ogni trimestre (Sendspin v1, possibile successore del Voice PE, Satellite1 che torna disponibile) e ogni stanza insegna qualcosa sulla successiva.

Rete: tutti i satelliti sono Wi-Fi a 2,4 GHz; MA consiglia di scendere a MP3/AAC sui player con Wi-Fi debole. Nessuna VLAN tra MA e i player.

---

## 7. La raccolta offline: aspetti pratici e legali

### 7.1 Struttura di cartelle consigliata

```
\\calliope-server\Musica\
├── comune\                     ← sorgente MA "Musica di casa" (tutti, anche gli ospiti)
│   ├── Lucio Battisti\
│   │   └── Una donna per amico\
│   │       ├── 01 - Prendila così.flac
│   │       └── cover.jpg
│   └── _playlist\
│       └── Cena.m3u8
├── dario\                      ← sorgente MA "Musica di Dario" (solo Dario)
│   ├── <Artista>\<Album>\NN - Titolo.ext
│   └── _playlist\
│       ├── Preferiti di Dario.m3u8
│       └── Corsa.m3u8
└── elena\ …
```

- Un album che piace a più persone va in `comune`; nelle cartelle personali stanno gli album "solo miei" e le playlist. Se uno stesso brano compare in due sorgenti, MA lo tratta come un solo elemento con due origini (comportamento atteso, da provare).
- Playlist in **M3U8 (UTF-8) con percorsi relativi**, dentro la sorgente a cui appartengono. Se una playlist personale possa puntare a file di `comune` dipende da come MA risolve i percorsi tra sorgenti diverse: **da provare**; nel dubbio usare le playlist native di MA (private dalla 2.11).
- Nomi di file e cartelle: UTF-8, niente emoji, niente `/ \ : * ? " < > |`; cartelle uguali ai tag.
- Condivisione SMB in **sola lettura** per l'utente di MA, con una sola cartella scrivibile per le playlist se le si vuole modificare da MA.
- **Backup**: la raccolta è l'unica cosa non ricostruibile: almeno una copia su un altro disco.

### 7.2 Formati

- **FLAC** per ciò che si rippa da CD; gli **MP3** esistenti (meglio 256–320 kbps o V0) vanno benissimo. AAC/M4A senza DRM è letto. Evitare WMA e qualunque file con DRM.
- L'alta risoluzione è inutile qui: Sendspin trasporta 16 bit e i satelliti ESP32 lavorano a 16 bit/44,1–48 kHz; MA converte al volo per ogni player, quindi il formato di origine non vincola le casse.

### 7.3 Tag e copertine (da fare una volta, con internet)

- **MusicBrainz Picard**: Titolo, Artista, Album, **Album Artist (obbligatorio per MA)**, numero traccia e disco, anno, genere (dalla 2.8 MA naviga per genere), ID MusicBrainz e ISRC.
- Compilation: Album Artist sempre uguale ("Various Artists").
- **Copertine incorporate** (JPEG 600–1000 px) **e** `cover.jpg` nella cartella dell'album; `artist.jpg` nella cartella dell'artista. Così offline non manca nulla: MA scarica immagini e biografie solo quando c'è rete.

### 7.4 Volume uniforme (ReplayGain)

- Scrivere i tag **ReplayGain 2.0** (traccia e album) con `rsgain` (`rsgain easy` sull'intera raccolta), foobar2000 o beets. MA usa questi tag se li trova (anche R128), altrimenti misura da sé con un costo di CPU sul Pi: meglio taggare prima.
- In MA la normalizzazione si attiva per player; nelle stanze con satellite conviene tenerla accesa: un volume prevedibile aiuta anche l'AEC e la wake word.

### 7.5 Aspetti legali (Italia) — non è un parere legale

- **Copia privata**, art. 71-sexies L. 633/1941: è consentita la riproduzione di fonogrammi "effettuata da una persona fisica per uso esclusivamente personale, purché senza scopo di lucro e senza fini direttamente o indirettamente commerciali, **nel rispetto delle misure tecnologiche**" (art. 102-quater). La copia **non può essere fatta da terzi** e presuppone il possesso legittimo dell'originale. Il compenso agli autori è già pagato nell'"equo compenso" su dischi e memorie (art. 71-septies).
- In pratica **va bene**: rippare i propri CD (i CD audio non hanno di norma protezioni efficaci); file acquistati senza DRM (Bandcamp, store di download di Qobuz, iTunes Store, 7digital…); musica con licenze libere.
- **Non va bene**: registrare o "scaricare" dai servizi di streaming (Spotify, YouTube, Tidal…: si aggirano protezioni e si violano i termini d'uso); file da fonti illecite (l'eccezione di copia privata non copre le copie da fonte illecita, secondo la giurisprudenza UE — a memoria, non riverificato oggi); distribuire la raccolta fuori casa.
- L'ascolto in famiglia sulla rete di casa è l'uso domestico per cui la norma è pensata. Conservare CD e ricevute.

---

## 8. Raccomandazione finale

**Decisione G (musica):** adottare **Music Assistant** come server musicale, installato come **app sul Raspberry Pi di Home Assistant** (Pi 4/5 con ≥ 4 GB), con la raccolta sul server Calliope in **condivisione SMB** divisa in `comune` + una cartella per persona, ciascuna come sorgente separata con filtro per utente. Calliope lo usa come **tool** tramite `music-assistant-client` (o il server MCP integrato), con un token per persona, e traduce "la mia musica" in base a chi parla. Aggiornare alla 2.11 quando esce, per sorgenti e playlist personali native. Tenere **Navidrome** come complemento futuro (preferiti personali veri, ascolto dal telefono) e **Lyrion + squeezelite** come piano di riserva per la sola sincronia.

**Decisione F (hardware):** regola generale **"le casse della stanza si collegano via cavo al satellite"**. Prima stanza: **Voice PE + Edifier R1280DB (≈ 180 €)**. Stanze grandi o rumorose: **ReSpeaker XVF3800 + casse attive**, da confermare con un confronto diretto. Tutto-in-uno di qualità: **Satellite1.1** quando disponibile. PC: cuffie + app desktop di MA. Sonos/WiiM solo dove già presenti o dove l'hi-fi prevale, accettando una wake word peggiore con la musica alta. **Echo escluso; Nest sconsigliato.** Comprare una stanza alla volta.

**Aggiornamento proposto ai principi:** il principio 8 (half-duplex per satellite) si precisa così: *un satellite può ascoltare mentre suona solo se l'audio riprodotto passa dal suo DSP*.

---

## 9. Cosa non sono riuscito a verificare

- **MA senza internet per periodi lunghi**: la documentazione dice che internet non serve al funzionamento di base, ma non ho trovato resoconti diretti. Da provare (§6.1, punto 5).
- **Token per utente → filtri applicati anche via API/MCP** e parametri esatti per "riproduci a caso dalla sorgente X": dedotto dalla documentazione, non provato. La documentazione API completa è solo sull'istanza installata (`/api-docs`).
- **Playlist M3U che attraversano due sorgenti** e trattamento dei brani duplicati tra sorgenti.
- **Data di uscita di MA 2.11** e forma finale di sorgenti/playlist personali (oggi solo nightly).
- **Supporto Sendspin/Music Assistant del firmware ESPHome per ReSpeaker XVF3800** (formatBCE/Seeed): documentati media player e ducking, non Sendspin.
- **Stato di Sendspin sul Voice PE con firmware stabile 26.9.0**: la documentazione MA dice "supportato con firmware recente"; un thread del forum (aprile–maggio 2026) riportava Voice PE che non comparivano come player Sendspin. Le note di rilascio 26.4.0 e 26.6.0 parlano di Sendspin, quindi presumo risolto.
- **Limite numerico del ritardo tollerato dall'AEC XMOS** (casse con DSP, Bluetooth): non trovato.
- **Wake word con musica**: nessuna misura sistematica; solo aneddoti discordanti (§4.3). Nessuna esperienza trovata specifica per "Voice PE + casse sul jack + musica alta".
- **Prezzi non verificati oggi**: casse compatte tipo Creative Pebble, Anker PowerConf, schede Sonocotta, spedizione e prezzo finale in euro del Satellite1 verso l'Italia, spedizione BerryBase. Il cambio dollaro/euro usato è indicativo.
- **Auto-standby e ingressi AUX simultanei delle Edifier R1280DB/DBs**, e presenza del cavo jack–RCA nella confezione: da controllare sulla scheda del modello.
- **Chromecast/Nest e Sonos in LAN senza internet**: non verificato.
- **IKEA Symfonisk** (disponibilità 2026), **Arylic**, **Plex/Plexamp 2026**, **librerie virtuali di Lyrion**, **modalità jukebox di Navidrome**, **build Windows ARM64 di Navidrome**: non verificati (budget di ricerche web della sessione esaurito).
- **Giurisprudenza UE sulla fonte illecita** (causa ACI Adam): citata a memoria.
- **Come HA passa all'agente compatibile OpenAI l'area/dispositivo** da cui arriva la richiesta, e la correlazione STT → conversazione per l'identità di chi parla.
- **Nuovo hardware vocale Nabu Casa**: nessun annuncio trovato, ma la ricerca non è stata esaustiva.
- Alcune pagine GitHub riassunte dallo strumento riportavano l'anno "2024" per rilasci che dal contesto (ESPHome 2026.x, numerazione 2.10/2.11) sono del 2026: ho usato il 2026.

---

## 10. Fonti

**Music Assistant**
- Blog 2.10: https://www.music-assistant.io/blog/2026/08/26/music-assistant-2-10/
- Blog 2.9: https://www.music-assistant.io/blog/2026/06/10/music-assistant-2-9/
- Blog 2.8: https://www.music-assistant.io/blog/2026/03/25/music-assistant-2-8/
- Blog 2.7: https://www.music-assistant.io/blog/2025/12/17/music-assistant-2-7/
- Rilasci del server (2.10.4, nightly 2.11): https://github.com/music-assistant/server/releases
- Installazione e requisiti: https://www.music-assistant.io/installation/
- Gestione utenti: https://www.music-assistant.io/settings/user-management/
- File locali: https://www.music-assistant.io/music-providers/filesystem/ e https://www.music-assistant.io/music-providers/local-files/
- Provider musicali: https://www.music-assistant.io/music-providers/
- Player supportati: https://www.music-assistant.io/player-support/
- Sendspin: https://www.music-assistant.io/player-support/sendspin/
- Player di Home Assistant/ESPHome: https://www.music-assistant.io/player-support/ha/
- Sonos: https://www.music-assistant.io/player-support/sonos/
- WiiM: https://www.music-assistant.io/player-support/wiim/
- Alexa: https://www.music-assistant.io/player-support/alexa/
- API: https://www.music-assistant.io/api/
- Plugin FastMCP Server: https://www.music-assistant.io/plugins/fastmcp-server/
- Controllo vocale: https://www.music-assistant.io/integration/voice/
- Blueprint vocali: https://github.com/music-assistant/voice-support
- App desktop: https://www.music-assistant.io/companion-app/ e https://github.com/music-assistant/desktop-app
- Client Python: https://github.com/music-assistant/client e https://pypi.org/project/music-assistant-client/
- Server MCP community: https://github.com/jakekeeys/music-assistant-mcp · https://github.com/shuricksumy/MCP-MusicAssistant · https://github.com/davidpadbury/music-assistant-mcp
- Preferiti per utente (no dei manutentori): https://github.com/orgs/music-assistant/discussions/5444
- Epic "Personal music sources": https://github.com/music-assistant/backlog/issues/84
- Playlist personali: https://github.com/music-assistant/backlog/issues/90 e https://github.com/music-assistant/server/pull/6325
- Scelta della cartella musicale (HAOS vede solo /media): https://github.com/music-assistant/backlog/issues/156
- Sendspin, discussione generale: https://github.com/orgs/music-assistant/discussions/4200
- Sendspin Bluetooth Bridge: https://github.com/orgs/music-assistant/discussions/5061
- Cache offline non disponibile: https://github.com/orgs/music-assistant/discussions/3912
- Pi 4 da 2 GB a scatti: https://github.com/orgs/music-assistant/discussions/3857
- Perché serve la rete host: https://github.com/orgs/music-assistant/discussions/2734
- MA in Docker su Windows 11 non funziona: https://community.home-assistant.io/t/music-assistant-container-on-docker-under-windows-11-not-working/742875
- WiiM Sound e bridge Sendspin: https://github.com/music-assistant/support/issues/5247
- Richiesta Sendspin sul forum WiiM: https://forum.wiimhome.com/threads/sendspin-music-assistant-sync-support.8977/

**Rete su Windows**
- Docker, driver host (Docker Desktop: solo livello 4): https://docs.docker.com/engine/network/drivers/host/
- WSL2 mirrored e multicast: https://github.com/microsoft/WSL/issues/12344 · https://github.com/microsoft/WSL/discussions/10614

**Home Assistant e voce**
- HA 2026.9: https://www.home-assistant.io/blog/2026/09/02/release-20269/
- Voice PE: https://www.home-assistant.io/voice-pe/
- Firmware Voice PE (26.4.0, 26.6.0, 26.9.0): https://github.com/esphome/home-assistant-voice-pe/releases
- YAML del Voice PE (ducking 20 dB): https://github.com/esphome/home-assistant-voice-pe/blob/dev/home-assistant-voice.yaml
- Wake word sparita per RAM (ESPHome 2026.3.x): https://github.com/home-assistant/core/issues/167989
- Musica a scatti su Voice PE (25.9.0): https://github.com/esphome/home-assistant-voice-pe/issues/455
- Voice PE e Sendspin (forum): https://community.home-assistant.io/t/ha-voice-assistant-pe-sendspin/1003504
- Casse esterne sul jack del Voice PE: https://community.home-assistant.io/t/connect-speaker-to-voice-assistant-pe/816948
- Bassa resa della wake word sul Voice PE: https://community.home-assistant.io/t/very-low-wake-word-detection-and-speech-recognition-rate-on-voice-pe/834067
- Blueprint di ducking tra satellite e media player: https://community.home-assistant.io/t/satellite-to-media-player-volume-ducking/841381
- Firmware community con barge-in: https://github.com/ganiushin/voice-pe-firmware
- Intenti in italiano: https://github.com/OHF-Voice/intents/tree/main/sentences/it
- Wake word personalizzate (guida HA): https://www.home-assistant.io/voice_control/create_wake_word/
- linux-voice-assistant: https://github.com/OHF-Voice/linux-voice-assistant
- Fork LVA con Sendspin, AEC e ducking: https://github.com/imonlinux/linux-voice-assistant
- Recensione Voice PE (Botmonster, 16/07/2026): https://botmonster.com/smart-home/home-assistant-voice-preview-edition-review/
- Wake word personalizzata con musica accesa (How-To Geek, 14/06/2026): https://www.howtogeek.com/ditched-okay-nabu-after-training-home-assistant-wake-word/

**Satelliti e schede**
- Satellite1.1 Smart Speaker: https://futureproofhomes.net/products/satellite1-smart-speaker
- Satellite1.1 Dev Kit: https://futureproofhomes.net/products/satellite1-pcb-dev-kit
- Firmware Satellite1 (0.2.0 Sendspin, 0.2.1): https://github.com/FutureProofHomes/Satellite1-ESPHome/releases
- Issue wake word nel rumore: https://github.com/FutureProofHomes/Satellite1-ESPHome/issues/551
- Recensione Satellite1: https://localsmarthomeguide.com/products/futureproofhomes-satellite1/
- ReSpeaker XVF3800 con custodia (Seeed): https://www.seeedstudio.com/ReSpeaker-XVF3800-With-Case-XIAO-ESP32S3-p-6628.html
- ReSpeaker XVF3800 (Antratek): https://www.antratek.com/respeaker-xvf3800-with-xiao-esp32s3
- ReSpeaker XVF3800 (Reichelt): https://www.reichelt.com/de/en/shop/product/respeaker_xmos_xvf3800_ai-powered_4_mic_with_esp32-416307
- Guida Seeed per Home Assistant: https://wiki.seeedstudio.com/respeaker_xvf3800_xiao_home_assistant/
- Firmware formatBCE: https://github.com/formatBCE/Respeaker-XVF3800-ESPHome-integration
- Recensione XVF3800 (Creating Smart Home, 12/04/2026): https://www.creatingsmarthome.com/index.php/2026/04/12/home-assistant-diy-voice-assistant-with-seeed-studio-respeaker-xvf3800/
- Recensione XVF3800 (Smart Home Circle, 22/01/2026): https://smarthomecircle.com/respeaker-xvf3800-home-assistant-voice-assistant
- Documentazione XMOS (AEC e riferimento): https://www.xmos.com/documentation/XM-014888-PC/html/modules/fwk_xvf/doc/datasheet/03_audio_pipeline.html · https://www.xmos.com/documentation/XM-014506-UG-3/latest/html/doc/user_guide/audio/1_Automatic%20Echo%20Cancellation%20(AEC).html
- Raspiaudio Muse Luxe: https://raspiaudio.com/product/esp-muse-luxe/ · https://forum.raspiaudio.com/t/esphome-sendspin/1443
- Sonocotta: https://sonocotta.com/louder-esp32/ · https://www.cnx-software.com/2026/06/25/louder-esp32-mini-board-adds-wifi-and-bluetooth-to-old-speakers-for-squeezelite-snapclient-or-esphome-support/
- SendspinZero: https://www.cnx-software.com/2026/04/21/diy-sendspin-audio-receiver-supports-multi-room-audio-synchronization-integrates-with-home-assistant/

**Prezzi**
- Voice PE: https://www.homebrainz.it/p/home-assistant-voice-preview-edition · https://dinamotech.it/products/home-assistant-voice · https://www.berrybase.de/en/home-assistant-voice-preview-edition
- Edifier R1280DBs / R1280DB: https://www.idealo.it/confronta-prezzi/201509635/edifier-r1280dbs.html · https://www.idealo.it/confronta-prezzi/5525620/edifier-r1280db.html
- Sonos Era 100: https://www.idealo.it/confronta-prezzi/202397849/sonos-era-100.html · https://www.idealo.it/confronta-prezzi/209709397/sonos-era-100-sl.html
- Jabra Speak 510: https://www.idealo.it/confronta-prezzi/4183307/jabra-speak-510-ms.html
- WiiM: https://www.idealo.it/confronta-prezzi/202940208/wiim-mini.html · https://www.idealo.it/confronta-prezzi/204129691/wiim-amp.html · https://www.idealo.it/confronta-prezzi/205135257/wiim-amp-pro.html · https://www.avmagazine.it/news/diffusori/wiim-sound-lite-ora-disponibile-in-italia_24734.html
- Rincari Raspberry Pi: https://www.tomshw.it/hardware/prezzi-ram-in-aumento-raspberry-pi-colpita-ancora-2026-04-01 · https://www.hwupgrade.it/news/periferiche/raspberry-pi-ritocca-ancora-i-prezzi-la-carenza-di-memoria-legata-all-ai-pesa-su-tutta-la-gamma_149527.html

**Alternative**
- Navidrome, rilasci: https://github.com/navidrome/navidrome/releases
- Navidrome multi-libreria: https://www.navidrome.org/docs/usage/features/multi-library/
- Jellyfin 12.0: https://jellyfin.org/posts/jellyfin-release-12.0/
- Lyrion: https://lyrion.org/reference/lyrion-music-server/ · https://forums.lyrion.org/forum/user-forums/logitech-media-server/1812262-lyrion-music-server-lms-version-9-1-is-officially-released
- Snapcast: https://github.com/snapcast/snapcast/releases
- OwnTone: https://github.com/owntone/owntone-server/releases

**Diritto d'autore**
- Art. 71-sexies L. 633/1941: https://www.brocardi.it/legge-diritto-autore/titolo-i/capo-v/sezione-ii/art71sexies.html
- Art. 71-septies: https://www.brocardi.it/legge-diritto-autore/titolo-i/capo-v/sezione-ii/art71septies.html
- Guida alla copia privata: https://www.dirittodautore.it/la-guida-al-diritto-dautore/eccezioni-e-limitazioni/la-riproduzione-per-uso-personale-di-fonogrammi-e-videogrammi/
