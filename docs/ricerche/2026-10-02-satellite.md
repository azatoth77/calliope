# Il portatile come satellite: protocollo, dove gira cosa, sicurezza

*Analisi e scelte del 02/10/2026, con le misure delle prove a secco (`prove/prova_satellite.py`).
Calliope andrà sulla DGX Spark (in ufficio, raggiunta in VPN; domani a casa, in LAN) e il
portatile Windows diventa un satellite: microfono, casse e schermo. Prima il satellite minimo;
l'esecutore remoto del PC (`pc_*`, consegna dei documenti) viene dopo, e il protocollo gli lascia
posto. Legende come nelle altre ricerche: **[M]** misurato qui, **[V]** verificato su una fonte
il 02/10, **[D]** deduzione.*

## 1. In breve

- **Protocollo**: un **WebSocket aperto dal satellite** verso il server (`websockets` 17.1, API
  sincrona, già dipendenza per la casa), messaggi JSON per i comandi e messaggi binari per
  l'audio (`calliope/satellite/protocollo.py`). Nessuna porta in ascolto sul portatile.
- **Audio**: **PCM 16 bit mono**, 16 kHz verso il server, la frequenza della voce di Piper verso il
  satellite (22 050 Hz con serena-high). Niente Opus.
- **Sul satellite**: microfono, **Silero VAD** (ONNX), **wake word acustica**, pre-roll,
  riproduzione con le attenzioni per le cuffie Bluetooth, **barge-in locale**, misura dell'eco.
  **Sul server**: Whisper, chi parla (CAM++), modello, Piper, tool, registro dei turni.
- **Privacy**: da addormentata l'audio **non lascia il satellite** finché non scatta la wake word;
  la frase parte allora, con il pre-roll che contiene il nome. Provato: 0 byte su una frase senza
  nome [M].
- **Sicurezza**: abbinamento a codice come gli schermi (device flow), sul server solo lo SHA-256
  del token; **TLS obbligatorio in rete** con un certificato autofirmato fatto da `openssl` e
  l'**impronta fissata** dal satellite (niente CA, niente `cryptography`); il token parte solo
  dopo il controllo dell'impronta. Su 127.0.0.1 TLS facoltativo.
- **Latenza aggiunta** da una rete tipo VPN (50 ms di giro simulati): **+30–93 ms**, mediana circa
  un giro (+50 ms) [M]. Il barge-in non la paga: si ferma sul satellite, entro un blocco da 100 ms
  (ultima scrittura 28–83 ms dopo lo scatto) [M].
- **CPU del satellite**: VAD + wake word **1,4 % di un core** [M]; il processo intero della prova,
  con microfono e casse finti in Python, 5–9 % [M]. **Banda**: 256 kbit/s verso il server solo
  mentre si parla a Calliope (~74 kB per «Calliope, che ore sono?» con il pre-roll) [M], ~353
  kbit/s verso il satellite mentre parla.

## 2. Protocollo: le alternative

| | WebSocket proprio | TCP grezzo | Wyoming (Rhasspy/HA) | API nativa ESPHome |
|---|---|---|---|---|
| Inquadramento dei messaggi | sì (testo e binario) | da scrivere | JSONL + payload | protobuf |
| Ping, caduta della connessione | nel protocollo (ping/pong) | da scrivere | no | sì |
| TLS | standard (`wss://`, `ssl` della libreria standard) | `ssl` a mano | no (TCP in chiaro) | Noise, chiave per dispositivo |
| Autenticazione | nostra (token nel primo messaggio) | nostra | nessuna | chiave per dispositivo |
| Barge-in, follow-up, half-duplex di Calliope | li definiamo noi | idem | eventi generici (audio-start/stop, detect): andrebbero estesi | legati alla pipeline di HA |
| Dipendenze | `websockets` (c'è già, wheel ovunque) | nessuna | `wyoming` | `aioesphomeapi` e un firmware |
| Stato | — | — | `wyoming-satellite` archiviato a gennaio 2026 (visione) | contratto di HA, non pubblico per terzi |

Scelta: **WebSocket proprio**. Wyoming non dà sicurezza né la semantica che a Calliope serve
(una frase intera rivolta a lei, barge-in con la frase che continua, frasi «dette per intero»
per la storia), e i satelliti commerciali non lo parlano più; un adattatore Wyoming o ESPHome per
i satelliti di stanza resta possibile più avanti, dietro la stessa `AscoltoRemoto`. Il TCP
grezzo costerebbe proprio le parti che `websockets` dà già. Un browser non può aprire il
WebSocket del satellite: il server accetta solo connessioni **senza** intestazione `Origin`
(provato: 403 [M]).

`websockets` 17.1 (26/08/2026): wheel `win_amd64`, `win_arm64`, `manylinux2014_aarch64` e
`musllinux_aarch64` per cp312–cp313 e oltre, più il sorgente puro Python [V, uv.lock]. API
sincrona (`websockets.sync`): un thread per connessione, come il resto di Calliope, niente asyncio.

### 2.1 Messaggi

Testo (JSON con `tipo`): dal satellite `abbina`, `ciao` (versione, token, `primo`), `pronto`
(eco misurata), `scartata`, `frase_finita` (da quanto è iniziata, scatto della wake word),
`nessuna_frase`, `interruzione`, `veglia_finita`, `turno_finito` (frasi dette per intero),
`schermo`; dal server `codice`, `abbinato`, `benvenuto` (parametri di taratura), `ascolta`
(wake sì/no, quanto resta della finestra di follow-up, seed), `sveglia` (un timer è scaduto:
torna appena nessuno parla), `veglia`/`fine_veglia` (barge-in durante una risposta),
`esito_voce`, `frase` (turno, testo, frequenza, byte), `fine_turno`, `ferma`, `schermo`.

Binario: un byte di tipo, 4 byte di identificativo, PCM int16: `A` frase dal microfono, `V`
parlato da controllare con l'impronta (livello B), `T` pezzo di una frase da dire, `S` saluto.

**Posto per l'esecutore del PC** (ricerca del 26/09, §5): stessa connessione autenticata e
stessa direzione; basteranno tipi nuovi (`pc_richiesta`/`pc_esito` con identificativo e
scadenza, `file` per la consegna dei documenti) e una dichiarazione delle capacità nel `ciao`.
Il campo `versione` del protocollo c'è per quando un lato cambierà.

## 3. Formato dell'audio

- **PCM 16 kHz × 16 bit = 256 kbit/s** verso il server, solo mentre si parla a Calliope (una
  frase dopo lo scatto, o la finestra di follow-up). In VPN e in LAN la banda è abbondante.
- **Opus** ridurrebbe a ~24–32 kbit/s ma: `opuslib` 3.0.1 (2018) è solo un legame ctypes e
  vuole `libopus` di sistema [V]; PyAV porta FFmpeg intero (~25–35 MB) e la pagina PyPI non
  elenca wheel `win_arm64` [V]; ogni pacchetto da 20 ms aggiunge ritardo e la compressione può
  peggiorare Whisper. Da riconsiderare solo per un satellite su rete mobile.
- La voce verso il satellite viaggia in **pezzi da 0,2 s** mandati appena Piper ha la frase: il
  satellite comincia a suonare al primo pezzo. Dopo una pausa TCP riparte con una finestra piccola
  (Linux `tcp_slow_start_after_idle`) e una frase intera da ~110 kB arriverebbe in 3–4 giri [D].

## 4. Dove gira cosa

| Pezzo | Dove | Perché |
|---|---|---|
| Microfono sempre aperto, pre-roll | satellite | come in locale (CLAUDE.md: riaprirlo tagliava l'attacco) |
| Silero VAD | satellite (onnxruntime, niente torch) | 0,23 % di un core [M]; senza, servirebbe mandare tutto |
| Wake word acustica | satellite | privacy: da addormentata non esce niente; 1,2 % di un core [M] |
| Fine frase (silenzio), finestra di follow-up | satellite, con i tempi decisi dal server | il server manda «quanto resta» in secondi relativi: niente orologi da allineare |
| Secondo stadio della wake word (nome nel testo) | server | serve la trascrizione |
| Whisper, chi parla, modello, tool | server | GPU e memoria della DGX |
| Piper | server | la voce non dipende dal PC; il satellite resta leggero |
| Riproduzione, lead/tail/keepalive Bluetooth | satellite | dipende dal dispositivo (`UscitaLocale`, la stessa di Calliope in locale) |
| Barge-in livello A (nome) | satellite | si ferma subito, senza il giro di rete |
| Barge-in livello B (voce di chi è registrato) | VAD sul satellite, impronta sul server | CAM++ e `speakers.json` stanno sul server; il satellite manda il parlato solo mentre Calliope parla (conversazione già aperta) |
| Misura dell'eco | satellite, sul saluto della prima connessione | come in locale; dalle cuffie o dal microfono MME dipende il livello B |

La logica di ascolto non è stata riscritta: il satellite usa lo stesso `audio.Listener` di
Calliope in locale (VAD, wake word, pre-roll, barge-in, eco), con due aggiunte piccole: la
sorgente del microfono iniettabile (le prove) e `on_audio`, che riceve i frame della frase appena
è rivolta a Calliope (sveglia o wake word scattata) per mandarli mentre si parla. Sul server
`AscoltoRemoto` ha lo stesso contratto di `Listener` e `UscitaRemota` è l'uscita di `Speaker`:
`main.py` ha lo stesso ciclo, con streaming frase per frase, follow-up e annunci (timer,
documenti, lavori) con il segnale acustico.

**Half-duplex**: invariato. Mentre Calliope parla il satellite ascolta solo la wake word (e il
livello B se non sente l'eco); i frame restano nel pre-roll.

**Annunci a satellite spento**: il ciclo aspetta un satellite collegato prima di annunciare;
un timer scaduto a portatile spento si annuncia quando torna. Una frase mandata mentre il
satellite cade si perde (lo dice il registro); il satellite si ricollega da solo (1, 2, 5, 10,
15 s) e alla riconnessione non ripete il saluto.

**Avvio**: la porta si apre subito (una porta occupata si scopre all'avvio), ma il satellite
viene accolto solo a Calliope pronta (modelli caricati, saluto sintetizzato): prima non c'è
nessuno che ascolti.

## 5. Più satelliti

L'archivio ha nome e **stanza** per satellite, e la stanza del satellite attivo va agli schermi
(`Schermi.stanza_corrente` → `Mittente.stanza`). Oggi è attivo **un satellite alla volta**:
quello collegato per ultimo, che sostituisce il precedente (chiusura 4409). Così una
riconnessione dopo un taglio di rete prende il posto della connessione vecchia anche se il
sistema non l'ha ancora vista cadere. Per più stanze insieme servirà una conversazione per
satellite (storia, follow-up, chi parla) o un arbitro su chi ha sentito meglio il nome (come
l'«announce» di HA): è il passo successivo, non serve con il portatile solo.

*Aggiornamento del 03/10 (il telefono, docs/ricerche/2026-10-03-webapp-telefono.md §3)*: più
satelliti restano collegati insieme e uno solo è attivo; un satellite nuovo non toglie più il
posto a quello attivo (portatile e telefono si sarebbero sostituiti all'infinito): lo prende
con `prendi` e lo restituisce con `lascia`. La sostituzione con 4409 vale solo per lo stesso
satellite che si ricollega.

## 6. Sicurezza

1. **Abbinamento**: il satellite chiede un codice (6 cifre, 10 minuti) a `/abbina`; chi
   amministra lo scrive sul server (`python -m calliope.satellite --abbina 123456 --stanza
   studio`, sulla DGX `calliope satellite …`); la richiesta segreta del satellite diventa il suo
   token. Sul server solo l'hash; 5 codici sbagliati in 10 minuti annullano tutti quelli in
   attesa. È l'archivio degli schermi con tabelle sue (`satelliti*`, stesso file). Revoca con
   `--revoca`: la connessione si chiude entro 5 s.
2. **Token**: nel primo messaggio, non nell'URL né in un'intestazione: così parte solo dopo il
   controllo dell'impronta TLS. Token assente, sbagliato o revocato chiudono con 4401, senza dire
   quale dei tre. Sul satellite il token sta in `satellite.json` (fuori da git, 600 su Linux).
3. **TLS: cosa serve davvero**.
   - In **VPN** la cifratura arriva al concentratore dell'ufficio; da lì alla DGX l'audio di casa
     e il token passerebbero in chiaro sulla LAN dell'ufficio, condivisa con altri: **TLS sì**.
   - In **LAN di casa** il Wi-Fi è WPA2/3 ma ogni dispositivo della rete (TV, prese smart)
     vedrebbe il traffico: TLS consigliato; costa una stretta di mano per connessione e una
     frazione di punto di CPU a 256 kbit/s.
   - Su **127.0.0.1** (satellite e Calliope sulla stessa macchina) non serve.
   - Scelta: in rete il server **non parte senza certificato**, salvo `satellite_senza_tls: true`
     (avviso a ogni avvio), come `casa_tls_verifica`. Certificato EC P-256 autofirmato di 10 anni
     fatto con `openssl` (`--certificato`), niente CA: il satellite fissa l'**impronta SHA-256**
     vista all'abbinamento, che stampa accanto al codice e che `--abbina` stampa sul server, da
     confrontare (chi fosse in mezzo proprio durante l'abbinamento si vedrebbe lì); oppure la si
     scrive a mano in `satellite_impronta`. Un'impronta diversa ferma il satellite prima di
     mandare il token (provato [M]).
4. **La pagina degli schermi**: perché il satellite la apra, sul server serve
   `schermi_indirizzo: 0.0.0.0`. Dal 02/10 in rete è in **HTTPS** con lo stesso certificato
   dei satelliti (`calliope/schermi/tls.py`); senza certificato il server della pagina non
   parte (salvo `schermi_senza_tls: true`, con un avviso). Il satellite riceve sulla
   connessione cifrata il token e l'impronta del certificato della pagina, e apre il browser
   su `http://127.0.0.1:<porta>` del suo **ponte TLS** (`calliope/schermi/ponte.py`), che
   verifica l'impronta e inoltra i byte: in rete solo TLS, nel browser un contesto sicuro,
   nessuna opzione del browser. `--ignore-certificate-errors-spki-list` con un profilo
   dedicato era la prima idea, ma Edge 154 la ignora («Errore di privacy», provato). Un tablet
   qualunque mostra l'avviso del certificato la prima volta. Il satellite riceve uno schermo
   suo, nella sua stanza, al primo collegamento, e lo riusa.

## 7. Misure (prove a secco, stessa macchina)

Calliope vera in un sottoprocesso (`audio_modo: satellite`), Ollama e Whisper finti (risposta in
~0,05 s), Piper vero (paola-medium); satellite vero con microfono finto (frasi di Piper con la
voce riccardo, 32 ms per frame in tempo reale) e casse finte (ogni scrittura dura quanto il suo
audio). Tre giri:

| Misura | Valore |
|---|---|
| Fine della frase → prima voce di Calliope sul satellite, in locale | 0,67–0,80 s (comprende la pausa di fine frase, silence_ms 700 ms, meno il silenzio finale della frase di Piper) |
| Stesso, con 25 ms per verso (giro di 50 ms) | +30–93 ms (≈ un giro: la fine della frase va al server, la prima frase torna) |
| Barge-in: scatto → ultima scrittura sulle casse | 28–83 ms (entro un blocco da 100 ms) |
| Audio mandato per «Calliope, che ore sono?» (1,5 s) | 68–76 kB (frase + pre-roll + pausa finale) |
| Da addormentata, frase senza nome | 0 byte, nessuna trascrizione |
| VAD + wake word sul satellite | 0,23 % + 1,2 % di un core |
| Venv del satellite leggero | ~120 MB (numpy, onnxruntime, sounddevice, websockets, pyyaml, silero-vad senza dipendenze) contro ~3,5 GB del venv completo |

Con la voce sintetica la wake word salta una frase ogni tanto (1–4 frasi ripetute su ~10 in
alcuni giri; 75/75 frasi giuste quando lo stesso audio passa da `Listener` fuori dal tempo
reale): non è un effetto del satellite ma della soglia di produzione (2 blocchi da 80 ms sopra
0,5) su questa voce; la prova ripete la frase come farebbe una persona.

## 8. Cosa resta

- La prova end-to-end con la DGX vera (passi in `prove/LEGGIMI.md`): latenza della VPN reale,
  TCP dopo le pause, satellite con microfono e cuffie veri.
- Più satelliti attivi insieme (una conversazione per stanza, arbitro sul nome).
- HTTPS per gli schermi (fase 4) e, di conseguenza, la pagina dal satellite senza token in chiaro.
- L'esecutore remoto del PC sulla stessa connessione.
- Un satellite di stanza senza PC (Raspberry, ESP32 con chip audio): stesso protocollo da Python,
  oppure un adattatore Wyoming/ESPHome dietro `AscoltoRemoto`.
