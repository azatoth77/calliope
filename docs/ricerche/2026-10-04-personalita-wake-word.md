# Personalità: tono di voce, wake word da cambiare, modalità Star Trek (04/10/2026)

Richiesta dell'utente (04/10): «la possibilità di pilotare il tone of voice di Calliope, oltre
alla possibilità di cambiare la wake word. Mi piacerebbe che avesse, inoltre, una modalità
StarTrek: vorrei che si attivasse con "Computer" e il canonico suono di inizio ascolto e fine
ascolto di StarTrek».

Questo documento è il progetto breve e il rapporto delle misure. Codice: `calliope/config.py`
(TONI, MODALITA, `wake_names`), `calliope/personalita.py`, `calliope/suoni.py`,
`calliope/wakeword.py`, `calliope/tools/builtin.py` (`cambia_voce`), `calliope/brain.py`
(`_tone_note`), satellite e telefono; addestramento in `wakeword/parole.py`. Prove:
`prove/prova_personalita.py` (a secco), `prove/prova_personalita_ollama.py`,
`prove/misura_tono.py`.

## 1. Tono di voce

### Scelta
Sei toni, ognuno tre pezzi del prompt di sistema (stile, lunghezza, tu o lei): `normale`
(il testo di sempre, parola per parola), `formale` (dà del lei), `amichevole`, `ironico`,
`essenziale` (una frase), `computer_di_bordo`. Le regole della voce (principio 5: niente
markdown, elenchi, emoji, URL, numeri in cifre) restano in tutti; nessun tono suggerisce
formule di conferma («Eseguito.», «Fatto.»), che sono dichiarazioni d'azione e il 4B le
direbbe anche senza chiamare il tool (rete `ACTION_CLAIM`).

Due posti, per non rompere la cache del prefisso (tool e prompt uguali per tutti dal 03/10):

- **tono della casa** nel prompt di sistema (`Config.tono`). Cambia di rado: Ollama rilegge il
  prefisso una volta. Si sceglie in `calliope.yaml`/`calliope.locale.yaml`, con la modalità, o
  a voce da chi amministra («da adesso parla a tutti in modo formale»: `cambia_voce` con
  `per_tutti`), salvato in `personalita.json` accanto a `calliope.yaml`; vale il più recente tra
  quel file e i file di configurazione.
- **tono di una persona** nel suo profilo (`speakers.json`, `tono`, come la voce preferita) e
  nei **dati del turno** prima della domanda, come dato su chi parla: «persona: Bianca,
  riconosciuta dalla voce; preferisce il tono formale nelle parole delle risposte (in modo
  cortese e formale, …) (dai del lei).» Mai nel prompt: quando cambia chi parla il prefisso
  resta in cache. Gli ospiti hanno il tono della casa.

Comando a voce: `cambia_voce` ha ora `tono` (enum dei sei) e `per_tutti` oltre a `voce`: il
modello sceglieva già quel tool per «cambia come parli», e un tool nuovo allungava il
prefisso. Conferma con `risposta_finale` già nel tono nuovo. Un tono messo in `voce` («voce
formale») si converte (regola `tono_da_voce`); `per_tutti` solo a chi amministra (nel codice,
oltre al registro); «torna normale» toglie la scelta personale.

### Misure (gemma4:e4b-it-qat, Ollama locale del portatile, 2 giri per prova)

Tool scelti contro il riferimento (stesso modello, tono normale, 3 giri identici: 32/34
riuscite, 0/26 tool mancati in `prova_stato_ollama`; `prova_casa` 41/42).

| Posto del tono | Testo | prova_stato_ollama: riuscite, tool mancati | prova_casa |
|---|---|---|---|
| casa (prompt di sistema) | computer_di_bordo | 32/34, 1/26 | 40/42 (tool sempre chiamati) |
| casa | formale | 30/34, 0/26 | 42/42 |
| persona, messaggio a parte «Con questa persona usa il tono formale, al posto di quello solito: rispondi …» | formale | **14/34, 9/26** | 41/42 |
| persona, stesso messaggio dopo i dati del turno | formale | 12/34, 13/26 | — |
| persona, nei dati del turno «preferisce il tono formale (dai del lei)» | formale | 30–32/34, 2/26 | — |
| persona, nei dati del turno con lo stile («vuole risposte con il tono formale (…)») | formale / cdb / ironico | 26–32/34, 1–4/26 | 40–41/42 |
| **persona, scelta: «preferisce il tono X nelle parole delle risposte (…)»**, 2 serie da 2 giri | formale | 31/34 e 28/34, 2/26 | 40/42 |
| idem | computer_di_bordo | 32/34 e 32/34, 1/26 e 0/26 | 41/42 |
| idem | ironico | 31/34 e 32/34, 2/26 | 42/42 |

Le prime misure di `prova_stato_ollama` con il tono della casa davano 19/34: era un download
finto ancora in corso da un caso precedente («Sto già scaricando Wikiquote»), con gli stessi
tool del riferimento; ripetute, 30–32/34.

Conclusione: il tono della casa nel prompt non toglie chiamate; un ordine di tono come
messaggio a parte sì (fino a 9 su 26: «Cosa sai fare?» e «Scarica la biblioteca» risposti a
parole). Detto come dato su chi parla, dentro i dati del turno che finiscono con «Per tutto il
resto chiama i tool come sempre», il costo resta nel rumore (0–2 su 26). `prova_personalita_ollama`
(14 frasi: formale, ironica, essenziale, torna normale, per tutti da un familiare e da chi
amministra, e i contrari «usa la voce di Paola», «che voci hai?», una barzelletta): 42/42 in 3
giri dopo una correzione della guardia (sotto), prima frase mediana 0,62 s.

Campioni di stile (`misura_tono.py … --campioni`): con `computer_di_bordo` «Ciao, come stai?» →
«Sono Calliope. Funzionamento ottimale.», «Grazie per l'aiuto» → «Non c'è di che.»; con
`formale` «È un piacere esserle stata d'aiuto.»; `ironico` è leggero.

Trovato strada facendo: una volta su due il 4B scriveva
`calliope_cambia_voce(tono="computer_di_bordo", per_tutti=true)` come testo, che si sarebbe
detto ad alta voce: `TextCallGuard` riconosce ora anche il qualificatore `calliope_`.
`per_tutti` arriva a volte come stringa («true»): si legge come booleano vero solo se lo è.

## 2. Wake word da cambiare

### Testuale (subito, per qualunque parola)
`wake_word` (null = il nome) e `wake_anche_nome` (il nome sveglia ancora, nel testo):
`Config.wake_names` = [parola, nome]. Tutti i posti che cercavano «Calliope» nel testo usano
la configurazione: `find_wake_word` (anche la parola più vicina all'inizio quando sono due),
uscite e stop, `said_name`, il controllo del nome nelle frasi di registrazione, il prompt di
Whisper («Conversazione con Computer.», sempre corto: taratura del 24/09) e le hotwords
(`whisper_hotwords` più le parole che svegliano), il barge-in che ignora la propria voce
(`tts.dice_nome`, anche sul satellite e nel telefono), il saluto («Di' «Computer» quando hai
bisogno»), la fascia «Dormo · di' «…»» di schermi e telefono.

Le regole anti-falsi di sempre restano (soglia `wake_match`, niente parole molto più corte).
Per una parola **comune** serve di più: `wake_posizione: inizio` (regola nuova, sulla
trascrizione: principio 10) fa valere la parola solo in testa alla frase (dopo «ehi», «ok»,
«allora»…) o subito dopo una virgola o un punto, cioè quando chiama qualcuno. «Il computer è
lento», «Accendi il computer», «Ho comprato un computer nuovo» non svegliano; «Computer, che
ore sono?», «Ehi computer…», «Sì, computer, spegni la luce», «Che ore sono, computer?» sì. Con
la wake word acustica un risveglio con la parola nel posto sbagliato si scarta anche a
punteggio alto (regola `wake_fuori_posizione`). Con `startrek` la tolleranza sale a 0,85:
«computo» (0,80) non sveglia. «Spegni computer» non spegne Calliope: in «spegni <nome>» vale
solo il nome dell'assistente quando la parola è comune (`Config.exit_names`).

### Acustica: serve un modello per la parola
Senza il file (`wake_model`) si torna da soli alla testuale (Whisper sempre acceso), e il
registro delle capacità lo dice con la parola. Sul **satellite** il server manda nel benvenuto
il nome del file del suo modello: se il satellite lo ha (accanto al suo, o nel pacchetto
d'installazione, che ora lo include), lo usa; altrimenti resta su «Calliope» e lo scrive, e il
server accetta comunque il nome (`wake_anche_nome`). Il **telefono** prende il modello dal
server; se manca usa `calliope.onnx`.

**Modello pubblico per «computer»**: c'è, nella collezione della comunità di Home Assistant
(github.com/fwartner/home-assistant-wakewords-collection, `en/computer/computer_v2.onnx`,
208 kB, licenza del repository MIT; addestrato con il notebook di openWakeWord, quindi con i
negativi ACAV100M CC-BY-NC-SA come il nostro, e con i campioni di Picovoice e Mycroft
Precise). Formato compatibile (ingresso 1×16×96: gira con il nostro `WakeWordDetector` senza
cambiare nulla). Ma è inglese: i suoi numeri dichiarati sono richiamo 0,57 e 5,2 falsi/ora, e
sulle 10 voci italiane di Piper (prova del 04/10, in streaming come Calliope, 2 blocchi sopra
0,5) scatta su **18/40** frasi «Computer, …» (aurora, leonardo, paola quasi mai), 0/80 sulle
frasi senza la parola, 1/30 su «computer» in mezzo alla frase. Non lo scarico né lo metto nel
codice: per l'italiano va addestrato il nostro.

**Addestrare «computer»**: gli script di `wakeword/` ora accettano `WW_PAROLA=computer`
(`wakeword/parole.py`: fonemi di espeak per l'italiano `kompjˈuteɾ` e varianti, testi, parole
simili da non confondere — computo, compito, compleanno, router, scooter… —, pezzi della
parola) e scrivono in cartelle loro; riusano i negativi già calcolati per «Calliope»
(`dati/feat/neg.npy`, il parlato MLS in `dati/feat/mls_seq.npy`, l'ACAV100M parziale), così
**non serve scaricare nulla** sul portatile. Provata la catena intera in piccolo (40 clip,
200 passi): genera, feature, addestramento, ONNX.

Dove: **sul portatile**, non sulla DGX. Lì manca tutto: torch per aarch64 da PyPI è quello
con CUDA 13 (GB), l'ACAV parziale (3 GB) e la validazione andrebbero copiati, LibriTTS-R (79
MB) e le voci scaricati. Sul portatile c'è già `wakeword\.venv` (torch per CPU, piper,
onnxruntime) e i dati.

Comandi (PowerShell, dalla radice del repository, ~25–35 minuti, ~1,2 GB in `wakeword\dati`):

```powershell
$env:WW_PAROLA = "computer"
wakeword\.venv\Scripts\python wakeword\genera.py 8000 8000 6000 0 12   # ~15 min: positivi e simili
wakeword\.venv\Scripts\python wakeword\feature.py                       # ~5 min
wakeword\.venv\Scripts\python wakeword\train.py 30000 computer 128 30.0 0.3   # ~6 min
# → wakeword\modelli\computer.onnx; poi modalita: startrek in calliope.locale.yaml
```

(Il quarto numero di `genera.py` è 0: le frasi generiche servono solo con le trascrizioni di
MLS, che sul portatile non ci sono più; i negativi generici vengono da `neg.npy`.) Il file va
copiato sulla DGX in `~/calliope/wakeword/modelli/`: lo usano il server, il pacchetto dei
satelliti e il telefono. **Non l'ho lanciato**: decide l'utente.

### Falsi risvegli con «Computer»
«Computer» è una parola di tutti i giorni (in casa, alla TV, al telefono), «Calliope» no. Il
modello acustico scatterà su ogni «computer» detto chiaramente, anche in mezzo alla frase:
quella frase passa a Whisper (non si registra, non resta nel registro) e il secondo stadio la
scarta perché la parola non è un richiamo. Il costo è privacy e un po' di GPU, non risposte
sbagliate. I risvegli veri da evitare restano le frasi che **cominciano** con «Computer» o lo
hanno dopo una virgola senza essere rivolte a Calliope («Computer nuovo: quanto costa?»,
dialoghi alla TV — e gli episodi di Star Trek, dove «Computer, …» è la battuta tipica). Senza
modello acustico (testuale) Whisper trascrive tutto il tempo: stesso filtro, ma ogni frase
della stanza passa da Whisper. Da misurare in casa dopo l'addestramento, come per «Calliope»
(~1 falso all'ora sugli audiolibri).

## 3. Modalità Star Trek

`modalita: startrek` (in `calliope.locale.yaml`) imposta wake word «Computer», posizione
`inizio`, tolleranza 0,85, `wake_model: wakeword/modelli/computer.onnx`, tono
`computer_di_bordo` e i suoni di ascolto. Le chiavi scritte in `calliope.locale.yaml` vincono
sulla modalità (per esempio un altro tono); quelle di `calliope.yaml` no (è il file d'esempio).

**Come si presenta**: resta **Calliope** (nome, memoria, profili, «Sei Calliope…» nel prompt,
saluto «Ciao, sono Calliope. Di' «Computer» quando hai bisogno.»); cambia la parola per
chiamarla e il modo di parlare. «Calliope, …» funziona ancora nel testo. Chi vuole un altro
nome cambia `name` (e la voce), come sempre.

**Suoni**: quelli originali di Star Trek sono di Paramount/CBS e non entrano nel repository né
si scaricano. `calliope/suoni.py` genera due segnali **ispirati**: inizio ascolto tre note che
salgono (mi6, la6, do7, 0,23 s), fine ascolto due che scendono (do7, sol6, 0,18 s), toni puri
con un'armonica leggera e inviluppo morbido, sopra 1,3 kHz, volume `suoni_volume` (0,35). Un
WAV dell'utente si mette in `suono_inizio_ascolto` / `suono_fine_ascolto` (percorso in
`calliope.locale.yaml`, fuori da git; letto con `wave`, mono, ricampionato, al più 1,5 s).

Chi li suona: chi ha il microfono, in locale, per la latenza.
- **Locale**: l'inizio dentro `Listener.listen` allo scatto della wake word acustica a
  Calliope addormentata (`on_wake`), la fine quando la frase è presa (con la testuale dopo il
  nome trovato nella trascrizione: lì l'inizio non c'è, il nome si sa solo dopo Whisper).
- **Satellite**: il server manda i due PCM nel benvenuto (`suoni`, base64, alla frequenza
  della voce); il satellite li suona da sé allo scatto e a fine frase, prima di mandarla.
- **Telefono**: stesso benvenuto, Web Audio (`Riproduttore.segnale`).

Half-duplex: la fine suona a frase chiusa, quando il microfono non registra per Whisper.
L'inizio suona mentre la persona parla ancora («Computer, che ore sono?»), quindi finisce
nella frase: è corto, acuto e piano. Misura (`whisper_bip.py`, fuori dal repository): 9 voci
di Piper × 4 richieste «Computer, …», bip messo 160 ms dopo la fine di «Computer» (dove
scatta la wake word), Whisper large-v3-turbo con beam 5, hotwords e prompt come in Calliope.
Trascrizione identica a quella senza bip: 24/36 con il bip forte quanto la voce, 27/36 a
−10 dB; quasi tutte le differenze sono minime e vanno nei due sensi (che ore/che ora,
«Computer e accendi», a volte il bip *corregge* la frase), ma 1 frase su 36 per livello perde
la parola «Computer» (con la wake word acustica, sotto 0,9 di punteggio, si scarterebbe) e
una diventa «Computer 3. Accendi la luce». Il microfono interno del portatile in MME e il
browser del telefono tolgono l'eco delle casse, quindi in casa conterà meno; chi lo trova di
troppo mette `suono_inizio_ascolto: nessuno` e tiene solo quello di fine.

## 4. Cosa resta
- Addestrare `computer.onnx` (comandi sopra) e misurare risvegli e falsi in casa.
- I satelliti già installati ricevono `computer.onnx` con il prossimo aggiornamento del
  pacchetto; il satellite del repository va copiato a mano.
- Toni nuovi: una riga in `TONI` e una frase in `_TONO_DETTO`, con la misura di
  `misura_tono.py`.
