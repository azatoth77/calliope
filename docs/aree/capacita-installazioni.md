# Registro delle capacità e installazioni

*Cosa funziona e cosa manca (`calliope_stato`, `python -m calliope.stato`), installazioni a voce dal catalogo. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Registro delle capacità | — (controlli rapidi in sola lettura) | `calliope/capacita.py` → `Registro`, `REGISTRO`, `segnala`, `controlla`, `testo_prompt`; terminale `calliope/stato.py` (`python -m calliope.stato`); tool `calliope_stato` in `calliope/tools/stato.py` (con `cosa=macchina` la macchina e i modelli: `calliope/macchina.py`; dal 09/10 le aree `capacita.AREE`/`aree`, `cosa=novita` e `cosa=chi_sei`: `calliope/novita.py`) |
| Piano dei modelli per la macchina, in sola lettura (dal 08/10) | — (nvidia-smi, /proc/meminfo, registro di Windows, Ollama `/api/version` `/api/tags` `/api/ps`, vLLM `/v1/models` `/version` `/metrics`, `systemctl show` in sola lettura) | `calliope/macchina.py` → `inventario`, `Sonde`; catalogo `calliope/modelli.py` → `MODELLI`, `GPU`, `WHISPER`, `VERSIONE`; regole `calliope/piano.py` → `piano`, `da_config`, `testo`, `Funzioni`; terminale `python -m calliope.stato --piano [--json] [--inventario FILE]`; prova `prove/prova_piano.py` |
| Installazioni dal catalogo | httpx (Range, checksum), API `/api/pull` di Ollama | `calliope/installa/` → `catalogo` (`catalogo.py`), `scarica_file` (`scarica.py`), `Installazioni` (`servizio.py`); tool `installa_proponi`, `installa_avvia`, `installa_gestisci` in `calliope/tools/stato.py` |

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

  - **Registro delle capacità e installazioni a voce** (01/10, `calliope/capacita.py`,
    `calliope/installa/`): cosa funziona, cosa manca e il prossimo passo, all'avvio, da
    terminale (`python -m calliope.stato`) e a voce; download solo da un catalogo nel codice
    (fonti italiane di Kiwix, voci di Piper, CAM++, modello di Ollama), solo chi amministra,
    sempre con proposta e «sì».

## Note dalla sezione «Problemi noti» di CLAUDE.md (fino al 06/10)

- **Registro delle capacità** (01/10, `calliope/capacita.py`, `calliope/stato.py`, tool
  `calliope_stato` in `calliope/tools/stato.py`; prove `prova_capacita.py`,
  `prova_stato_ollama.py`):
  - 11 capacità *[storico, 01/10: il 06/10 sono 18, `capacita.DEFINIZIONI`]*, quattro stati (`attiva`, `da_configurare`, `mancante`, `guasta`), con
    motivo, prossimo passo per la voce e dettagli. I caricamenti (`load_biblioteca`,
    `load_pc`, `load_documenti`, `load_casa`, `load_wake_detector`, `Transcriber`,
    `check_audio_devices`) segnalano nel registro invece di stampare; all'avvio una riga
    `[CAPACITÀ] Capacità: 10 attive su 11; …`, le note delle attive (modello e dispositivo
    di Whisper restano visibili: è la riga da controllare dopo il primo download) e i
    passi di quelle che non vanno. La casa è «dinamica»: le viste chiedono lo stato fresco,
    il prompt no.
  - `python -m calliope.stato` regge una macchina nuova: con 20 librerie bloccate
    (numpy, onnxruntime, httpx, yaml…) esce con 0 e segna «mancante»; senza PyYAML
    usa i predefiniti. Controlli in sola lettura, ~1 s (Ollama locale con 1,5 s di tempo
    massimo; su Windows una porta chiusa non rifiuta subito). Attenzione: il controllo
    della casa legge `segreti.yaml` per sapere se il token c'è (mai stampato).
  - Prompt: un elenco breve e stabile («funzionano: …; non disponibili qui: …; non sai
    mandare messaggi o email…») più una frase che manda ai tool. Con il **solo** elenco il
    modello rispondeva «non posso collegarmi alla domotica» senza chiamare
    `casa_integrazione` (42/46 in `prova_casa_ha_ollama`): serve dire che perché manca e
    come averla lo dicono `calliope_stato` e `casa_integrazione`, e che «scarica…» è
    `installa_proponi` (senza, 1 volta su 2 chiamava `calliope_stato`). Prompt +600
    caratteri, schemi +4000 (i 4 tool nuovi, soprattutto l'enum delle 21 azioni). «Puoi
    mandare un'email?» e «cercami su internet le notizie» → «non posso» 4 su 4. Con il
    prompt finale, 2 giri: `prova_pc_ollama` 62/62 (prima frase mediana 0,46 s),
    `prova_casa` 42/42 (0,52), `prova_documenti_ollama` 34/34 (1,39),
    `prova_casa_ha_ollama` 46/46 (0,38), `prova_stato_ollama` 34/34 (0,36): come prima.
  - Livelli: chi amministra sente motivo e passo, i familiari cosa funziona e «chiedi a chi
    amministra», gli ospiti solo cosa possono chiedere loro. La frase è pronta
    (`risposta_finale`). Dopo «cosa sai fare?» il modello risponde a «e cosa manca?» dalla
    storia (giusto, il risultato del tool è lì).
  - **Cosa si può aggiungere** (02/10, `capacita.aggiungibili`): a «cosa manca?» diceva solo
    «Funziona tutto quello che è installato». Ora `calliope_stato(cosa=manca)` dice anche
    cosa c'è nel catalogo e non è installato: le fonti della ricerca che mancano con a cosa
    servono («Vikidia, per le spiegazioni semplici», «Wikiquote, per le citazioni»), le voci
    (una per nome: Serena alta o media conta una), le altre fonti contate («6 fonti della
    biblioteca, come Wikisource e Wikibooks, che per ora non uso nelle risposte»), e chiude con
    «Dimmi quale installare, per esempio «scarica Vikidia»» (senza installazioni: il comando da
    terminale). Con `cosa=sa_fare` una frase sola in fondo; i familiari sentono solo «Chi
    amministra può aggiungere altre fonti alla biblioteca e altre voci»; gli ospiti niente.
    Sola lettura dei file, nessuna rete. Il modello sceglie `cosa` giusto 8 volte su 8 in
    `prova_stato_ollama`. Dopo le correzioni del 02/10, 2 giri: `prova_pc_ollama` 62/62
    (0,46 s), `prova_casa` 42/42 (0,51), `prova_documenti_ollama` 34/34 (1,30),
    `prova_casa_ha_ollama` 58/58 con i 12 casi nuovi (0,39), `prova_stato_ollama` 34/34
    (0,38).
  - **Riassunto dell'avvio e casa** (02/10): diceva «casa (Home Assistant) (collegamento in
    corso)» sotto la riga «[CASA] Collegata…». Le capacità dinamiche ora si rileggono quando si
    stampa il riassunto, e `main` aspetta al più 0,3 s la fine del primo tentativo
    (`HomeBackend.attendi_primo_tentativo`): di solito è già finito (Whisper e le voci si
    caricano in qualche secondo), con HA muto costa 0,31 s.

- **Installazioni a voce** (01/10, `calliope/installa/`, tool `installa_proponi`,
  `installa_avvia`, `installa_gestisci`; prove `prova_installa.py` con un server HTTP finto,
  `prova_stato_ollama.py`):
  - Solo dal catalogo nel codice: le 12 fonti italiane di Kiwix (le 4 della ricerca più
    Wikisource, Wikibooks, Wikiquote, Wikivoyage, Wikiversità, WikiMed, Gutenberg e, segnata
    come facoltativa, Wikipedia con le immagini), le 4 voci ufficiali di Piper, CAM++, il
    modello di Ollama in `llm_model` e la pulizia. Per Kiwix **niente versioni, dimensioni o
    checksum nel codice**: l'ultima versione si trova nell'indice di
    `download.kiwix.org/zim/<cartella>/` (solo i nomi esattamente `<prefisso>_AAAA-MM.zim`),
    il checksum dal `.sha256` ufficiale, la dimensione dal `Content-Length` del mirror
    ftp.fau.de. Kiwix tiene solo le ultime due versioni: una versione fissa sparirebbe.
  - Due turni, nel codice: `installa_proponi` (solo chi amministra, riconosciuto dalla voce
    **in quella frase**: `SpeakerContext.identified_by == "voce"`) controlla libreria,
    spazio (`installa_margine_gb`), file già presenti, e chiude con «Procedo?» (azione in
    sospeso); `installa_avvia` (livello `amministra`, anche il «sì» breve) parte solo se
    c'è un'offerta della stessa persona per la stessa azione fatta nella **risposta
    precedente** (`Brain.turn_number` → `ToolContext.turno`). Proposta e avvio nella stessa
    risposta, un turno in mezzo, un'altra persona o un'altra azione: rifiutati, con
    `installa_senza_offerta` nel registro dei turni. Il modello decide se «sì» è un consenso
    (con «No, lascia stare.» non ha mai avviato).
  - Download in secondo piano: `.part` con ripresa (`Range`, 206; un server che risponde 200
    fa ripartire da capo), checksum, `os.replace`; reindirizzamenti seguiti a mano solo
    verso host del catalogo, https (http solo verso 127.0.0.1 delle prove). `iter_bytes`
    con un blocco di 1 MB teneva i dati in memoria: con la connessione caduta a metà il
    `.part` restava vuoto, ora si scrive appena arriva. I file sopra 200 MB già presenti con
    la dimensione giusta si danno per integri (rifare lo SHA di 9 GB costerebbe ~20 s a
    voce); quelli piccoli si riverificano.
  - Fine: annuncio con il segnale acustico (come documenti e agenda) e riga nel registro
    dei turni (chi, cosa, quando, esito); la biblioteca si riapre e `biblioteca_cerca`
    compare senza riavvio (`main.activate_library`). Un ZIM verificato ha accanto
    `<nome>.verificato` e `risolvi_zim` lo preferisce a quello di `calliope.yaml`, che non si
    tocca. Per Wikipedia ridotta e Vikidia dopo la verifica c'è il passo **«indice»**
    (01/10): l'indice FTS5 si costruisce in un processo a parte e il file nuovo entra in uso
    solo con l'indice completo; se non riesce, «Ho i file, ma non sono riuscita a preparare
    l'indice» e resta in uso il vecchio. L'azione `biblioteca_indice` (solo locale, «prepara
    l'indice della biblioteca», `--installa biblioteca_indice`) rifà gli indici mancanti, a
    metà o di una versione vecchia; «scarica la biblioteca» con i file già presenti ma senza
    indice propone l'indice. La pulizia cancella anche gli indici dei file superati, quelli
    orfani e i `.tmp` di più di un'ora. Le fonti in più si scaricano e si verificano; la
    ricerca usa quelle con `Fonte.richiesta` accese in `biblioteca_fonti_extra` (dal 01/10
    solo Wikiquote, `catalogo.fonti_usate`), le altre restano «scaricate, non ancora usate
    nella ricerca» nel registro (`catalogo.fonti_scaricate`).
  - Mai pip, mai `calliope.yaml`/`calliope.locale.yaml`: lì Calliope dice cosa fare.
    `requires_internet`: senza rete i tool d'installazione spariscono. Senza CAM++ o senza
    il modello di Ollama Calliope non parte: quei due si installano da terminale
    (`python -m calliope.stato --installa modello_chi_parla`).
  - **Non provato con internet vero** (vincolo del 01/10): reindirizzamenti di Hugging Face
    e GitHub (host ammessi elencati in `catalogo.py`), `.sha256` e indice di
    download.kiwix.org (formato letto il 01/10), `/api/pull` di Ollama vero.

## Motivi a voce senza nomi di chiavi (06/10, prova e2e)

«Cosa sai fare?» diceva «perché spento (archivioenabled)». `capacita.a_voce` toglie la chiave
tra parentesi («spento nella configurazione») e legge a parole le altre («casa url»);
`calliope_stato` la usa per motivo e passo. Terminale e dettagli invariati. Dal 06/10 la
capacità «llm» dice anche quando Calliope usa più modelli di quanti Ollama ne tiene
(`calliope/ollama_carico.py`, vedi contesto-conversazione).

## Taratura sulla macchina: ricerca (07/10)

Richiesta di Dario: che Calliope suggerisca modelli, contesto e numero di modelli secondo la
macchina su cui gira (una GPU da 32 GB non è una DGX). Ricerca, niente codice:
[`../ricerche/2026-10-07-taratura-macchina.md`](../ricerche/2026-10-07-taratura-macchina.md).
Inventario di ciò che c'è (`macchina.py`, `contesto.py`, `ollama_carico.py`, catalogo, latenza),
classi di macchine con le bande dichiarate, catalogo dei modelli con dati dichiarati e misurati,
cache per token dai `/api/show` (tre sovrastime di `contesto.kv_ollama`: qwen3.6, gpt-oss,
Gemma 3), regole del piano con le priorità (voce, Whisper, guardiano mai spento in silenzio…),
tre piani completi (portatile, RTX 5090, DGX), verifica con `size_vram` di `/api/ps`, stato in
`taratura.json`, `calliope stato --piano`, fasi (~12–15 giorni; prima la velocità di generazione
nel registro dei turni, che oggi manca).

## Taratura sulla macchina, fasi 0–2: inventario, catalogo e piano in sola lettura (08/10)

Ramo `taratura-fasi-0-2`, fasi 0–2 della [ricerca del 07/10](../ricerche/2026-10-07-taratura-macchina.md).
Niente si applica: il piano si legge e basta, e le sei decisioni aperte del documento sono
scritte nel piano come opzioni.

- **Fase 0** (vedi contesto-conversazione): la velocità di generazione di ogni turno nel
  registro (`generati`, `generazione_tps`) e in `calliope stato --turni`; `kv_ollama` corretto
  per qwen3.6, gpt-oss e Gemma 3.
- **Inventario** (`macchina.inventario`, solo libreria standard, solo 127.0.0.1): GPU da
  nvidia-smi (MiB → GB; «[N/A]» = memoria unificata, il pool è la RAM di /proc/meminfo; senza
  nvidia-smi la VRAM dal registro di Windows), banda dalla tabella del catalogo, memoria libera
  adesso, Ollama (versione, installati, caricati con `size_vram`: un modello **in parte sulla
  CPU** è un avviso), variabili di Ollama da `systemctl show` (sola lettura), vLLM sulle porte
  8000/8001 con `gpu_memory_utilization` e i token della cache da /metrics, server di Whisper,
  CUDA per onnxruntime (Piper) e CTranslate2 (faster-whisper). Le sonde sono una classe
  (`Sonde`): le prove ne passano una finta.
- **Catalogo** (`calliope/modelli.py`, `VERSIONE = "2026-10-08"`): solo dati, con fonte e data
  accanto a ogni numero (legenda [M]/[V]/[A]/[Agg]/[D] della ricerca). Modelli della §3 con i
  pesi in memoria (misurati con `/api/ps` dove li abbiamo caricati, tolte cache e buffer: 26B
  14,6 GB, e4b 2,67, guardiano 8B 4,4), byte letti a token, cache per token, licenza, posto
  nella scala del banco e misure nostre per GPU (26B 76 token/s e lettura 3 164 sulla DGX, e4b
  76 sul portatile, Qwen3.6 76 su vLLM). Nella scala della voce solo e2b, e4b e 26B;
  `gemma4:12b` e `qwen3.5:9b` sono candidati «da provare» (decisione 2), mai scelti. Tabella
  delle GPU per nome (banda, memoria, unificata, lettura relativa [D]), Whisper (faster-whisper
  sulla GPU 1,27 GB, whisper.cpp 2,1 GB, small sulla CPU ~1 s [D]), Piper 1,5 GB, immagini
  13 GB.
- **Piano** (`piano.piano`, funzione pura): le priorità della §4.1 con la memoria sommata
  (pesi + buffer 0,35 GB + cache × posti di `OLLAMA_NUM_PARALLEL` + contesto CUDA per processo
  sulla GPU dedicata, 0,9 GB su Windows e 0,5 su Linux [D]; vLLM = `gpu_memory_utilization` ×
  memoria). La voce entra con la finestra minima (16 384) e la finestra cresce **dopo**
  guardiano, rilevatore ed embedding (punto 7 della §4.1), fin dove tempo e memoria lo
  permettono; la misura di `contesto.json` vince sulla stima. Velocità: misurata da noi su
  quella GPU, altrimenti η × banda / byte letti (η 0,55, o quello delle misure della macchina),
  al più 250 token/s; lettura misurata, o scalata dai parametri attivi e dalla GPU [D]. La
  memoria «di adesso» si guarda a parte: se altri programmi tengono più della riserva il piano
  lo dice, e le funzioni a richiesta (immagini, Piper sulla GPU) diventano «non adesso».
- `calliope stato --piano` (tabella con «come oggi» o «oggi X» accanto a ogni ruolo, variabili
  di Ollama proposte come comando, candidati, avvisi, decisioni aperte), `--json` (inventario
  e piano), `--inventario FILE` (una macchina salvata).

**Sulla DGX vera (08/10, sola lettura).** Eseguire codice sulla DGX non è stato permesso: le
letture permesse (nvidia-smi, /proc/meminfo, Ollama `/api/version` `/api/tags` `/api/ps`,
`systemctl show ollama`, vLLM `/v1/models` `/version` `/metrics`, il server di Whisper che
risponde, `contesto.json`; onnxruntime con CUDA e CTranslate2 senza GPU nel Python del servizio)
sono state ripassate a `macchina.inventario` con sonde che le rileggono, e il piano è stato
calcolato sul portatile con la configurazione della DGX (`llm_profilo: gemma4-26b-ollama`,
`contesto_rilettura_max_s: 3`, `stt_motore: server`). Ritrova **tutte** le scelte fatte a mano:
26B su Ollama (76 token/s, prima frase pulita ~0,73 s), whisper.cpp sulla GPU, guardiano 8B,
rilevatore e4b separato, embedding sulla CPU, Qwen3.6 su vLLM (0,4 × 128 GB), 28 672 token, 4
residenti e 2 posti già impostati; in più Piper sulla GPU (c'è posto) e immagini «a richiesta,
non adesso»: MemAvailable era 10,5 GB, cioè ~40 GB tenuti da altri programmi oltre ai modelli
di Calliope (la riserva del piano è 14). Senza `contesto.json` la finestra stimata è 24–28k.

**Macchine finte** (`prove/prova_piano.py`): solo CPU → voce e2b sulla CPU fuori soglia
(~4,4 s), decisione 5; 8 GB (il portatile) → e4b, Whisper sulla GPU, guardiano 1B sulla CPU
con la decisione 3, rilevatore = voce; 16 GB → e4b con il guardiano 8B sulla GPU; 24 GB → 26B,
guardiano 8B, rilevatore = voce, agente = il 26B sul secondo posto (decisione 4,
`OLLAMA_NUM_PARALLEL=2` proposto); 32 GB → 26B, guardiano 8B, rilevatore e4b separato, agente
sul secondo posto (~32 GB su 34); Windows su ARM 128 GB → 80 % alla GPU, whisper.cpp, Qwen3.6
separato su Ollama. Diverso dall'esempio della ricerca: sui 24 GB il guardiano **8B ci sta**
(la ricerca metteva la voce a 28k con due posti prima del guardiano; qui la finestra cresce
dopo, come vuole la §4.1). Contrari: guardiano «nessun modello» con avviso, mai sparito; la
voce non scende per far posto a un ruolo più in basso; un candidato «da provare» mai scelto;
nessun file scritto.

Resta (fasi 3–6 della ricerca): la prova breve con `size_vram` e la generazione misurata,
`taratura.json`, i campi «auto», il catalogo per ruolo, `calliope_stato(cosa=piano)`, gli
installatori. Da misurare prima (§7.2): η su più modelli, il rapporto vero/pulita dai nuovi
`generazione_tps`, Whisper e guardiano 1B sulla CPU.

## «Cosa sai fare?» per aree, novità e «chi sei?» (09/10)

Caso vero sulla DGX (09/10, 08:16–08:18): «Hai modo di sapere quali sono state le ultime
novità sul tuo aggiornamento?» → `calliope_stato{"capacita":"tutte","cosa":"sa_fare"}` →
l'elenco intero delle capacità, così lungo che chi parlava l'ha interrotta; poi «non ho un
registro delle versioni» (falso: c'è CHANGELOG.md) e «il mio codice risiede… distribuito su
diversi server» (falso: gira in locale). Tre cambiamenti:

- **Aree.** `capacita.AREE` raggruppa le capacità del registro e i tool senza capacità propria
  (ora e conti, foto e file, sviluppo, esercizi) in 11 aree; `capacita.aree(registro,
  tool_names)` dice quali ci sono per chi parla (una capacità attiva o un suo tool ammesso a
  quel livello, da `ToolRegistry.schemas_for`). «Cosa sai fare?» dice solo i nomi brevi («la
  casa, l'agenda, le ricerche, i documenti, il computer…», senza «e» né virgole dentro un
  nome), per chi amministra i nomi di ciò che non va («il perché con "cosa manca?"»), un
  esempio di domanda sull'area e, se c'è uno schermo personale collegato, «l'elenco completo è
  sullo schermo»: la scheda personale «Cosa so fare» in Markdown, con «Scarica», ha le aree con
  il dettaglio. Il parametro `area` (elenco chiuso, lo sceglie il modello anche detto a parole
  diverse) dà il dettaglio: «Con la casa posso comandare luci, tapparelle e termostato di
  casa.»; chi amministra sente il perché delle capacità dell'area che non vanno, i familiari
  «chiedi a chi amministra». «Cosa manca?» e l'ospite restano com'erano.
- **Novità** (`cosa=novita`, `periodo` = ultimo_aggiornamento, oggi, da_ieri, settimana, mese):
  `calliope/novita.py` legge la versione (numero da pyproject.toml, commit e data del codice
  da `cruscotto.versione_in_uso`, cioè VERSIONE.json del gestore o il git del portatile;
  quando è stata messa in uso e la versione di prima dalla `storia` di
  `gestione.json`, due cartelle sopra `versioni/<id>/`: il gestore non cambia) e le righe di
  CHANGELOG.md **della versione installata**: di norma quelle dopo la data del codice della
  versione di prima, senza gestore le ultime due date, con un periodo quelle del periodo (se
  non c'è niente lo dice e dà le ultime). Mai voci oltre la data del codice. A voce ~40 parole
  di novità, al più tre date, ogni voce tagliata a 18 parole; tolte le parentesi e il codice
  tra apici, e **tolti interi** i pezzi con un indirizzo, un host o un percorso (anche se il
  CHANGELOG è pubblico). La scheda «Novità di Calliope» ha versione, commit, date e le righe
  intere (link ridotti al testo). Per tutti i livelli: il registro è pubblico. Regola
  `stato_periodo_novita`: col solo `periodo` (gemma4 e4b, «cosa è cambiato da ieri?» →
  `{periodo: da_ieri}` senza `cosa`) si completa la forma della scelta del modello (principio
  10, conversione); contrario: con `cosa=sa_fare` il periodo non cambia niente.
- **Chi sei** (`cosa=chi_sei`): nome, «gira in casa, su questo computer» con il tipo di
  macchina dall'inventario (mai il nome host), il modello della voce (sullo stesso computer o
  «su un altro computer della casa», mai l'indirizzo) e dell'agente, niente cloud (internet
  solo per le ricerche, se la ricerca web è attiva), versione, «il mio codice è libero, con
  licenza AGPL, ed è pubblico; qui mi installa e mi aggiorna chi amministra». Nessun URL del
  repository: non è né nel README né nella configurazione, e la `sorgente` del gestore può
  essere un indirizzo privato. La spinta del prompt (`capacita.testo_prompt`, accanto a quella
  dell'08/10 sulle spiegazioni inventate) manda a `calliope_stato` anche le domande su di sé.

Misure col modello locale (gemma4 e4b, `prove/prova_chi_sei_ollama.py 2`, portatile): 29/32;
caso vero, «quali sono le novità?», «da ieri», «che versione sei?» (chi_sei), «dove gira il
tuo codice?», «chi ti ha programmato?», «cosa sai fare?» (solo aree), «e con la casa?» 2/2;
«chi sei?» senza tool «Sono Calliope…» (vero, accettato); «cosa sai fare con i documenti?» 1/2
e «cosa puoi fare per appuntamenti e promemoria?» 0/2 a conversazione appena aperta:
risponde dalle descrizioni dei tool (vero, ma senza `area`); dopo «cosa sai fare?» `area` c'è
sempre. Prima della frase «sempre, mai a memoria» nella descrizione le domande d'area a freddo
erano 0/3. Contrari («chi sono?», «che ore sono?», la lista della spesa, «chi ha inventato il
telefono?») 8/8 senza novità né chi sei. Prima frase mediana 0,52 s. Da rimisurare sulla DGX
col 26B. Prova a secco `prove/prova_novita.py`.
