# Setup su Windows (portatile e satellite)

*Installazione su Windows: Calliope completa, casa, biblioteca, schermi, agenti, satellite, telefono. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

**Stato al 09/10.** Dal 02/10 il target principale è la DGX Linux ([setup-dgx](setup-dgx.md)): su Windows oggi gira soprattutto il **satellite** (portatile e PC di casa, installazione con un comando), mentre Calliope completa sul portatile resta per lo sviluppo e le prove. I passi qui sotto valgono per tutte e due; il satellite nel dettaglio è in [satelliti](satelliti.md), il PC a voce in [pc](pc.md). Non provati sul vero: un PC Windows pulito come satellite e Windows su ARM.

## Setup (Windows)

```powershell
# LLM (quello impostato in Config; scelta motivata in docs/ricerche/2026-09-21-confronto-llm.md)
ollama pull gemma4:e4b-it-qat

# Ambiente Python (provato con 3.14; vanno bene anche 3.11 e 3.12)
python -m venv .venv
.venv\Scripts\activate
pip install faster-whisper silero-vad sounddevice numpy openai httpx piper-tts torchaudio pyyaml
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12   # Whisper su GPU
pip install pycaw comtypes pywin32 psutil screen_brightness_control winrt-Windows.Media.Control   # PC a voce (facoltativo)
pip install python-docx openpyxl fpdf2 pypdf   # documenti Word, Excel, PDF (facoltativo); pypdf legge i PDF dati all'agente
pip install docxtpl python-pptx          # modelli Word e PowerPoint dell'utente (facoltativo, extra «modelli»)
pip install websockets                   # casa via Home Assistant (facoltativo)
pip install pypdfium2                    # archivio dei documenti di casa (facoltativo; Pillow e python-docx ci sono già)
pip install starlette uvicorn            # schermi (facoltativo); MAI uvicorn[standard]
pip install hassil home-assistant-intents   # solo per le prove della casa (HA finto con le frasi vere)

# Voci italiane (nella cartella voices/; il catalogo ufficiale ne ha quattro)
python -m piper.download_voices --download-dir voices it_IT-paola-medium it_IT-serena-medium it_IT-serena-high it_IT-riccardo-x_low
# in alternativa: .onnx + .onnx.json da Hugging Face, repo rhasspy/piper-voices

# Configurazione: calliope.yaml si rigenera e resta uguale all'esempio; i valori di questa
# installazione si scrivono in calliope.locale.yaml (stesse sezioni, solo le chiavi da cambiare)
python -m calliope.config --esempio > calliope.yaml

# Cosa funziona e cosa manca, con il prossimo passo (anche su una macchina appena installata)
python -m calliope.stato                 # tabella; --dettagli, --json per gli script
python -m calliope.stato --catalogo      # cosa si può installare
python -m calliope.stato --installa biblioteca    # proposta, conferma s/N, download verificato

# Avvio
python -m calliope              # oppure: python avvia_calliope.py (webcam C920 e cuffie I52)
```

PyYAML ha wheel `win_arm64` per Python 3.12–3.14 (verificato il 26/09/2026). Per il PC a
voce: pywin32, psutil e winrt hanno wheel `win_arm64`; pycaw, comtypes,
screen_brightness_control (e il suo `wmi`) sono puro Python (ricerca del 26/09). Da
verificare su ARM il provider di Windows Search (`Search.CollatorDSO`). Senza queste librerie
Calliope parte uguale e i tool `pc_*` non ci sono.

Documenti (27/09): python-docx 1.2.0, openpyxl 3.1.5 (con et-xmlfile 2.0.0), fpdf2 2.8.8 (con
fonttools 4.66.0, defusedxml 0.7.1) sono puro Python; le due dipendenze native, lxml 6.1.3 (per
python-docx) e Pillow 12.3.0 (per fpdf2), hanno wheel `win_arm64` per Python 3.10–3.14. Senza una
libreria manca solo quel formato; senza nessuna i tool `documento_*` non ci sono.

Casa via Home Assistant (01/10/2026): in `calliope.locale.yaml`, sezione `casa`, `casa_url` è
l'indirizzo **di casa** (`https://<IP del Raspberry>:8123`, mai il nome DuckDNS). Il
certificato in LAN è quello DuckDNS: `casa_tls_nome` con quel nome (verifica e SNI, ci si
collega comunque all'IP), oppure `casa_tls_impronta` (SHA-256, la stampa
`prove/sonda_ha.py`); `casa_tls_verifica: false` solo come ultima scelta, con un avviso a
ogni avvio. Il token (Profilo → scheda Sicurezza → «Token di accesso a lungo termine» →
«Crea token», di un utente **amministratore**) va **solo** in `segreti.yaml` accanto a
`calliope.yaml` (fuori da git) o nella variabile `CALLIOPE_HA_TOKEN`, che vince:

```yaml
home_assistant:
  token: "…"
```

Poi in HA: Impostazioni → Assistenti vocali → scheda «Esponi» → «Esponi le entità».
`python prove\sonda_ha.py` fa solo letture e dice cosa manca. `websockets` 17.1 ha wheel
`win_arm64` (e `py3-none-any`). Senza indirizzo o token Calliope parte uguale: resta solo
`casa_integrazione`, che spiega a voce il passo successivo.

Biblioteca offline (facoltativa, ~12 GB): `sh biblioteca/scarica.sh` scarica Wikipedia italiana
(mini 2,4 GB + completa 9 GB), Vikidia e Wikizionario con il checksum; dal 01/10 anche
`python -m calliope.stato --installa biblioteca` o, a voce, «scarica la biblioteca» (ultima
versione trovata da sola, checksum ufficiale, attivata senza riavvio). Senza i file Calliope
funziona uguale e il tool `biblioteca_cerca` non c'è. **Nessuna libreria da installare** (dal
01/10): i file ZIM si leggono in puro Python (`lzma`, `compression.zstd` di Python 3.14;
con Python 3.11–3.13 serve `pip install zstandard`) e la ricerca per parole usa SQLite FTS5,
tutto nella libreria standard anche su Windows ARM. Dopo il download serve l'**indice di
ricerca** di Wikipedia ridotta e Vikidia (1,3 GB in `biblioteca/indici/`, ~4 minuti con 4
processi): lo prepara da sola l'installazione a voce; per i file scaricati con `scarica.sh`:

```powershell
python -m calliope.biblioteca_indice            # gli indici che mancano; --stato per vederli
python -m calliope.stato --installa biblioteca_indice   # oppure a voce: «prepara l'indice della biblioteca»
```

Senza indice la biblioteca funziona ridotta (solo voci dal titolo esatto) e il registro delle
capacità lo dice. `libzim`, se è installata, non si usa più.

Schermi (02/10/2026, facoltativi): `starlette` 1.7.0 e `uvicorn` 0.54.0 sono wheel
`py3-none-any`, come le loro dipendenze (anyio, h11, click, colorama: già nell'ambiente con
httpx); nessun codice nativo nuovo, quindi vanno anche su Windows ARM. **Niente
`uvicorn[standard]`**: httptools e uvloop non hanno wheel `win_arm64`. Con le librerie la
pagina è su `http://127.0.0.1:8770` (solo questo PC, il predefinito); per tablet e TV di casa
in `calliope.locale.yaml`, sezione `schermi`, `schermi_indirizzo: 0.0.0.0` (mai la porta
inoltrata dal router). Uno schermo nuovo mostra 6 cifre: «Calliope, abbina lo schermo 123 456
al soggiorno» (solo chi amministra), oppure da terminale:

```powershell
python -m calliope.schermi                                   # elenco e indirizzo della pagina
python -m calliope.schermi --abbina 123456 --stanza soggiorno [--personale Dario]
python -m calliope.schermi --revoca soggiorno
python -m calliope.schermi --kiosk soggiorno   # Edge in kiosk: stampa UNA volta l'URL con il token
```

Senza le librerie, o con la porta occupata, Calliope parte uguale e il registro delle
capacità dice «schermi» mancanti o guasti con il prossimo passo.

Agenti per i lavori lunghi (02/10/2026, facoltativi): nessuna libreria nuova (httpx c'è già;
ctypes e il resto sono della libreria standard). La **DGX Spark in ufficio** si raggiunge
solo in VPN: Calliope apre da sola un tunnel SSH con l'**OpenSSH di Windows** (`ssh -N -L
11436:127.0.0.1:8000 <alias>`, `BatchMode=yes`: mai password né domande) e il server del
modello sulla DGX resta su 127.0.0.1. Dal 02/10 l'agente sulla DGX usa **vLLM** (motore
«openai», container `calliope-vllm`, script in `~/calliope-motore/` sulla DGX: vedi
`prove/LEGGIMI.md`), non Ollama: Ollama 0.35.0 della DGX va in errore CUDA con le richieste
dell'agente (Problemi noti). Utente, indirizzo e chiave stanno **solo** in
`%USERPROFILE%\.ssh\config`, sotto l'alias; Calliope non legge quel file e non li stampa mai.
Il resto in `dgx.yaml` accanto a `calliope.yaml` (fuori da git; percorso in
`agenti_config_file`, variabile `CALLIOPE_AGENTI_CONFIG`):

```yaml
dgx:
  ssh_alias: "dgx"            # Host di .ssh\config (HostName, User, IdentityFile)
  motore: "openai"            # vLLM (API compatibile OpenAI); "ollama" = API nativa
  collegamento: "tunnel"      # "diretto" con url_diretto: una DGX in casa, in LAN
  porta_remota: 8000          # predefinita: 8000 con "openai", 11434 con "ollama"
  porta_locale: 11436         # 11434 è l'Ollama locale della voce
  agente_modello: "qwen3.6-35b"   # con vLLM il nome servito (--served-model-name)
  scrittore_modello: ""       # vuoto = lo stesso
  timeout_collegamento_s: 5
```

Una volta a mano, con la VPN: `ssh dgx` (accetta l'impronta, verifica la chiave; con una
passphrase, `ssh-add` e il servizio «OpenSSH Authentication Agent»); sulla DGX
`~/calliope-motore/avvia.sh` (vLLM; con il motore «ollama» invece `ollama pull qwen3.6:35b`).
Poi:

```powershell
python -m calliope.agenti --prova    # SOLO: apre il tunnel, versione e modelli, chiude
```

Senza `dgx.yaml` (né `agenti_url`) i tool `delega_lavoro`, `lavori_stato`, `lavori_annulla`
*[nomi superati il 08/10: oggi `lavoro_affida`, `lavoro_stato`, `lavoro_annulla` e gli altri tool dei lavori e della modalità sviluppo, vedi [agenti-estensioni](agenti-estensioni.md)]*
non ci sono e la capacità «agenti» è da configurare; con la VPN spenta Calliope parte uguale,
la delega dice «la DGX non risponde (VPN spenta?)» e riprova al lavoro dopo. Per un Ollama
raggiungibile senza tunnel (una DGX in casa): `agenti_url: http://<IP>:11434` in
`calliope.locale.yaml` (con `/v1` in fondo, `http://<IP>:8000/v1`, un server OpenAI come vLLM). Passi della prima prova e banco: `prove/LEGGIMI.md`.

Satellite (02/10/2026, [`docs/ricerche/2026-10-02-satellite.md`](../ricerche/2026-10-02-satellite.md)):
Calliope gira su un server (la DGX) e il portatile fa da microfono, casse e schermo. Sul
server, in `calliope.locale.yaml` sezione `server_satelliti` (dal 05/10; le sezioni servono solo
a leggere, una chiave vale in qualunque sezione): `audio_modo: satellite` e, in rete,
`satellite_indirizzo: 0.0.0.0` con il certificato (`python -m calliope.satellite --certificato`,
sulla DGX `calliope satellite --certificato`: usa `openssl`, stampa l'impronta). Sul portatile
`satellite_server: wss://<IP del server>:8771` nella sezione `satellite` (stesso file, mai nel
codice), con i suoi dispositivi (05/10): `satellite_microfono`, `satellite_casse` (numero o parole
del nome, «C920 MME») e `satellite_webcam` (per `pc_guarda`), variabili
`CALLIOPE_SATELLITE_MICROFONO`/`_CASSE`/`_WEBCAM`. `input_device`, `output_device` e `pc_webcam`
sono di Calliope completa: al satellite valgono solo da ripiego, con l'avviso «spostala nella
sezione satellite» (`config.dispositivi_satellite`); C920 e I52 di `avvia_satellite.py` solo se
la configurazione tace. L'installatore dei PC nuovi scrive le chiavi nuove. Poi:

```powershell
python avvia_satellite.py               # C920 e I52 per nome; oppure python -m calliope.satellite
# la prima volta stampa un codice e l'impronta del server; sul server:
python -m calliope.satellite --abbina 123456 --stanza studio [--personale Dario]   # sulla DGX: calliope satellite …
python -m calliope.satellite --modifica studio --personale Dario | --condiviso
python -m calliope.satellite --elenco | --revoca studio
powershell -ExecutionPolicy Bypass -File setup\satellite\avvio_automatico.ps1   # all'accesso (-Togli)
```

**Schermo personale del satellite** (02/10): il portatile di Dario è suo, quindi lo schermo che
il satellite apre può ricevere le schede personali (promemoria, appuntamenti, documenti) di
Dario. Sul portatile `satellite_schermo_personale: Dario` in `calliope.locale.yaml` è solo
una **richiesta**, mandata con il codice: il server la stampa e non la applica. Vale solo
`--personale <nome>` di chi abbina (o `--modifica` dopo, senza riabbinare: il satellite
collegato e il suo schermo cambiano entro ~5 s); così un satellite non può dichiararsi
personale di un altro. Valgono le regole di visibilità di sempre (zona grigia esclusa). A voce
non c'è ancora un tool per abbinare i satelliti. **Dal 03/10 a voce** («questo satellite è il
mio schermo personale», «rendilo condiviso»: `schermo_gestisci` con azione `personale` o
`condiviso`): solo chi amministra, riconosciuto dalla voce in quella frase; vale per il satellite
da cui si parla o per lo schermo nominato, prima la domanda («Lo schermo dello studio riceverà
anche promemoria, appuntamenti e documenti: lo rendo personale tuo?», azione in sospeso) e solo
dopo il «sì», nella risposta dopo, il cambiamento (subito, senza i ~5 s del controllo).
`prova_schermi_ollama`: 54/54 in 2 giri con 8 frasi nuove (sì, no, familiare, ospite).

Il token sta in `satellite.json` accanto a `calliope.yaml` (fuori da git, come
`satellite.crt` e `satellite.key` sul server). Su un PC senza Calliope completa:
`setup\satellite\installa.ps1` (venv da ~120 MB: numpy, sounddevice, onnxruntime, websockets,
pyyaml, silero-vad senza torch; tutte con wheel `win_arm64` e Linux aarch64) e i tre modelli di
`wakeword/modelli/`. Senza wake word il satellite non parte (manderebbe tutto al server).

**Un PC nuovo come satellite con un comando** (03/10, `calliope/satellite/web.py`; prova
manuale in `prove/LEGGIMI.md`): `https://<server>:8770/satellite` (o `:8771/installa`) mostra un
comando per PowerShell con la **chiave** del certificato dei satelliti (`sha256//…`, la stessa
di `calliope satellite --elenco`, da confrontare a occhio). Ogni download dal server passa da
`curl.exe -k --pinnedpubkey` (curl di Windows: con un'altra chiave si ferma, codice 90).
Installa uv (SHA-256 fissato) e Python, scarica il pacchetto del satellite (codice, wake word,
requisiti con gli SHA-256 di `uv.lock`), prepara la configurazione e l'avvio all'accesso, tutto in
`%LOCALAPPDATA%\Calliope\satellite`, senza amministratore. Poi si aggiorna da solo: il server
annuncia la versione nel benvenuto, il satellite la prepara accanto e si riavvia quando nessuno
parla; se non si ricollega entro 180 s `avvio.py` torna alla precedente e non la riprova per 6
ore. Il satellite del repository non si aggiorna mai. `satellite_installazione` e
`satellite_aggiornamenti` lo spengono. Linux: solo il posto nella pagina.

Telefono (03/10, [`docs/ricerche/2026-10-03-webapp-telefono.md`](../ricerche/2026-10-03-webapp-telefono.md)):
con Calliope sul server (`audio_modo: satellite`) e la pagina in rete, `https://<IP>:8770/telefono`
è una web app (PWA) che fa del telefono un satellite: «Parla» o «Microfono acceso» con la wake
word nel telefono. Sul server una volta `calliope stato --installa telefono` (onnxruntime-web e i
modelli generici; `calliope.onnx` va copiato dal portatile) e `calliope schermi --certificato
--host <IP>` (CA di casa da installare sul telefono e certificato della pagina, `schermi.crt`,
che vince su quello dei satelliti); si abbina come un satellite (`calliope satellite --abbina
<codice> --stanza telefono --personale <nome>`). Passi e prova in auto: `prove/LEGGIMI.md`.

Utili: `python -m sounddevice` elenca i dispositivi audio, da impostare in
`input_device` / `output_device`. «Esci», «arrivederci» o «addio» la rimettono a dormire
(torna ad aspettare il nome e la conversazione riparte da capo); per chiudere il programma
si dice «spegniti» (o «spegni Calliope», «chiudi il programma»); con l'audio di un
satellite anche queste la addormentano soltanto (il server si ferma con `calliope ferma`).
