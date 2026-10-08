# Prove

Script di prova e diagnostica, fuori dal percorso principale di Calliope.
Ogni file aggiunge la cartella del progetto a `sys.path` con un piccolo shim in
testa, così si può lanciare dalla radice. Dal 26/09/2026 importano dal package
(`from calliope.brain import Brain`, `from calliope.config import Config`…):

```powershell
$env:PYTHONUTF8=1
.\.venv\Scripts\python.exe -u prove\prova_tool.py
```

## Runner

**Tutte le prove in un comando** (dal 26/09/2026; a livelli dal 06/10, P5 di
`docs/ricerche/2026-10-06-analisi-complessiva.md`), dalla radice del progetto:

```powershell
.\.venv\Scripts\python.exe -m prove              # livelli 1 e 2: ~15–60 s
.\.venv\Scripts\python.exe -m prove --completo   # tutte le prove a secco (~8–9 min): PRIMA DELL'UNIONE SU MAIN
.\.venv\Scripts\python.exe -m prove --ollama     # anche quelle con il modello (qualche minuto)
.\.venv\Scripts\python.exe -m prove --help       # le altre opzioni
```

I **livelli** (in `prove/__main__.py`):

- **1** — le prove veloci (< 5 s da sole, 41 la sera del 06/10; 24 al livello 2, 11 al 3,
  27 con Ollama, 22 manuali): sempre, in parallelo (6 alla volta),
  ~13–15 s. Una prova nuova senza livello è del livello 1; se il riepilogo la segnala come
  lenta va spostata in `LIVELLO_2` o `LIVELLO_3`.
- **2** — le prove legate ai file cambiati (`LIVELLO_2` e la mappa `LEGAMI` dai prefissi dei
  percorsi: `calliope/schermi/` → schermi, scritto, giochi, telefono_abbina, inoltro…;
  `calliope/agenti/` → agenti, sandbox, arbitro, esecuzione…; `setup/linux/` → linux,
  gestore), in parallelo. Un file di `prove/` sceglie sé stesso e le prove che lo importano.
  I tool d'area (`tools/casa.py` → casa_ha, `tools/agenti.py` → agenti…, `tools/stato.py` →
  capacita, installa) scelgono le prove della loro area (Q7, 06/10). `brain.py`, `ciclo.py`,
  `main.py` e `config.py` scelgono `prova_linux_import` (gli import di tutto il pacchetto su
  Linux simulato, ~5 s: un import solo-Windows prima passava l'hook). Gli altri file
  trasversali (`politica.py`, `tools/registry.py`, `tools/spec.py`, `tools/builtin.py`…) non
  scelgono niente in più: li coprono il livello 1 e il 3.
- **3** — browser, Calliope vera, tempo reale (`LIVELLO_3`): solo con `--completo`, **in
  serie**, da sole sulla macchina (anche le prove del livello 2 con il browser, `SERIALI`).
  **Obbligatorio prima dell'unione di un ramo su main.** Va lanciato dove ci sono i file
  fuori da git (`voices/`, `models/speaker/`, `wakeword/modelli/`, `biblioteca/`): in un
  worktree come hard link (non junction); senza, quelle prove si saltano e il riepilogo le
  elenca. Eccezione (08/10): `prova_telefono_pagina` trova da sé onnxruntime-web
  (`models/web/`), i modelli della wake word e le voci nel **repository principale** (`git
  rev-parse --git-common-dir`, anche dalla copia dell'hook via `PROVE_ORIGINE`), o nella
  cartella di onnxruntime-web indicata da `CALLIOPE_TELEFONO_MODELLI`: si installano una volta
  sola nel principale con `python -m calliope.stato --installa telefono` (14 MB, ignorati da
  git) e in un worktree non serve nessun link.

L'**hook** (`.githooks/pre-commit`, attivato con `git config core.hooksPath .githooks`)
lancia `python -m prove --hook --staged`: livelli 1 e 2 con i file del commit, sulla **copia
dell'indice** (`git checkout-index` in una cartella temporanea, con i modelli come hard
link): si prova quello che si committa, non l'albero di lavoro, e indice, albero e stash
non si toccano. Misure del 06/10 nel worktree: commit su `brain.py` 14 s, su
`calliope/casa/` 17 s, su `calliope/satellite/` 46 s, su `calliope/schermi/` 52 s, su
`calliope/agenti/` 59 s (prima, tutte in serie: ~775 s nel worktree, ~880 nel principale).

Opzioni: `--ramo` (livello 2 con tutti i file cambiati dal punto in cui il ramo si è staccato
da main), `--staged`, `--seriale` o `-j N`, `--timeout S` (predefinito 300 s per prova; con
`--ollama` 3600), `prova_x.py …` (solo quelle, con il loro livello e il parallelo).

Il **riepilogo** conta a parte le prove **saltate**: una prova che si salta per intero (manca
il browser, una voce, un modello, il file della biblioteca) esce con **77**; una che salta
una sua parte stampa una riga che **comincia** con `SALTATA IN PARTE: <motivo>`. Prima il
«70/70» nascondeva i salti. Dal 06/10 (Q7) `prova_runner` controlla che ogni prova registrata
che stampa un salto lo segnali così (o esca con 77), che ogni `prova_*.py` sia nel runner o in
`MANUALI` (con il perché) e che i tool d'area scelgano le loro prove. Lanciate da sole, le prove saltate escono quindi con 77 anche nella shell.

Ogni prova ha un **tempo massimo** (300 s): oltre, il runner chiude lei e i suoi processi e
la segna fallita («tempo scaduto»). Su Windows ogni prova gira in un **job object** (dal
03/10): se a prova finita resta vivo un suo processo figlio (Calliope vera, Edge, un server
finto) la prova fallisce con «processi lasciati vivi» e il runner lo chiude, così non tiene
porte, file o CPU durante le prove dopo. Di una prova fallita il runner mostra le righe
`ERR`/`NO` e l'ultima riga di ogni traceback (l'eccezione), e salva l'output intero in
`%TEMP%\calliope-prove\` (lì anche `durate.json`: le durate dell'ultima volta, per far
partire prima le prove lunghe). Con `--ollama` (04/10) il runner manda alle prove il
`keep_alive` del modello della voce (`CALLIOPE_LLM_KEEP_ALIVE`, letto da `calliope.yaml`, dal
file locale e dal profilo): una prova non accorcia mai la permanenza in memoria del modello
condiviso con la voce. `python -m prove prova_satellite.py prova_agenti.py` lancia solo
quelle (stesso ambiente dell'hook): serve a ripetere una prova instabile. Le soglie «la voce
non aspetta» delle prove degli agenti valgono 0,15 s (`SUBITO_S`): ciò che non va aspettato
dura da 0,2 s in su, e sotto carico il solo avvio di un thread superava i 50 ms.

Le prove con il **browser** (Edge o Chromium senza finestra) usano `prove/cdp.py` (06/10): la
porta di DevTools la sceglie il browser (`--remote-debugging-port=0`, letta da
`DevToolsActivePort`) e la chiusura passa da `Browser.close`, poi dall'albero dei processi
(prima restavano vivi crashpad e le utility di Edge). Dal 08/10 il browser parte sempre con `--mute-audio`: la voce
che la pagina del telefono riproduce con Web Audio non esce più dalle casse o dalle cuffie
vere del portatile (Web Audio gira lo stesso). Le prove con un satellite in Python usano casse
finte (`apri_uscita`, `apri_flusso`).


## Le prove per area

Ogni prova con la sua descrizione è in [`elenco.md`](elenco.md), raggruppata per area. Una prova
nuova va in `elenco.md` (nella sua area) e in `prove/__main__.py`.

- **Voce, modello e regole sul testo** ([elenco](elenco.md#voce-modello-e-regole-sul-testo), [area](../docs/aree/voce-e-regole.md)): `prova_config.py`, `prova_testo.py`, `prova_tool.py`, `prova_rinomina_ollama.py`, `prova_robustezza.py`, `prova_brain.py`, `prova_brain_ollama.py`, `prova_regressione.py`, `ora_giusta.py`, `prova_llm.py`, `prova_native.py`, `prova_confronto.py`, `prova_ollama_tool.py`, `prova_debug.py`, `prova_prompt.py`, `prova_prompt2.py`, `prova_native2.py`, `prova_prompt3.py`, `prova_latency.py`, `prova_tool_scala.py`
- **Audio: wake word, STT, TTS, chi parla** ([elenco](elenco.md#audio-wake-word-stt-tts-chi-parla), [area](../docs/aree/stt-tts.md)): `prova_pronuncia.py`, `prova_stt_correzione.py`, `prova_whisper.py`, `prova_speaker.py`, `misura_stt.py`, `misura_pronuncia.py`, `prova_wakeword.py`, `prova_aec.py`
- **Memoria, agenda, liste, calcoli** ([elenco](elenco.md#memoria-agenda-liste-calcoli), [area](../docs/aree/memoria-agenda-liste.md)): `prova_tempi.py`, `prova_agenda.py`, `prova_liste.py`, `prova_casa.py`, `prova_date_ricordi_ollama.py`, `prova_calcola.py`, `prova_memoria.py`
- **Contesto e conversazione** ([elenco](elenco.md#contesto-e-conversazione), [area](../docs/aree/contesto-conversazione.md)): `prova_contesto.py`, `prova_conversazioni.py`, `prova_corsie.py`, `prova_ctx.py`, `prova_numctx.py`, `prova_prompt_conversazione.py`, `misura_contesto.py`, `misura_conversazioni.py`, `misura_corsie.py`
- **Sicurezza, politica, conferme** ([elenco](elenco.md#sicurezza-politica-conferme), [area](../docs/aree/sicurezza-politica.md)): `prova_sicurezza.py`, `prova_politica.py`, `prova_conferma_unica.py`, `prova_conferme.py`, `misura_quarantena.py`, `misura_riferire.py`, `prova_conferma_unica_ollama.py`, `prova_politica_ollama.py`, `misura_conferma_breve.py`, `misura_sfida.py`
- **Minori** ([elenco](elenco.md#minori), [area](../docs/aree/minori.md)): `prova_minori.py`, `prova_minori_ollama.py`, `misura_guardiano.py`
- **Casa (Home Assistant)** ([elenco](elenco.md#casa-home-assistant), [area](../docs/aree/casa.md)): `prova_casa_ha.py`, `prova_casa_ha_ollama.py`, `sonda_ha.py`
- **PC a voce** ([elenco](elenco.md#pc-a-voce), [area](../docs/aree/pc.md)): `prova_pc.py`, `prova_pc_ollama.py`
- **Documenti, ufficio, archivio** ([elenco](elenco.md#documenti-ufficio-archivio), [area](../docs/aree/documenti-ufficio.md)): `prova_documenti.py`, `prova_documenti_ollama.py`, `prova_ufficio.py`, `prova_ufficio_ollama.py`, `prova_archivio.py`, `archivio_misura_ocr.py`, `archivio_misura.py`, `prova_archivio_ollama.py`
- **Biblioteca e ricerca web** ([elenco](elenco.md#biblioteca-e-ricerca-web), [area](../docs/aree/biblioteca.md)): `prova_web.py`, `prova_web_ollama.py`, `prova_biblioteca.py`, `prova_zim.py`, `prova_biblioteca_indice.py`, `arm/confronta_lettore.py`, `arm/bench_query.py`
- **Schermi e telefono** ([elenco](elenco.md#schermi-e-telefono), [area](../docs/aree/schermi-telefono.md)): `prova_schermi.py`, `prova_schermi_pagina.py`, `prova_scritto.py`, `prova_rispondi.py`, `prova_scritto_conversazione.py`, `prova_scritto_pagina.py`, `prova_scritto_calliope.py`, `prova_telefono.py`, `prova_telefono_pagina.py`, `prova_telefono_abbina.py`, `prova_telefono_schermo.py`, `prova_telefono_audio.py`, `prova_schermi_ollama.py`, `prova_scritto_ollama.py`
- **Foto e allegati** ([elenco](elenco.md#foto-e-allegati), [area](../docs/aree/immagini-allegati.md)): `prova_immagini.py`, `prova_immagini_pagina.py`, `prova_immagini_ollama.py`, `prova_allegati.py`, `prova_allegati_ollama.py`, `misura_immagini.py`
- **Satelliti** ([elenco](elenco.md#satelliti), [area](../docs/aree/satelliti.md)): `prova_config_satellite.py`, `prova_schermi_satellite.py`, `prova_satellite.py`, `prova_corsie_satelliti.py`, `prova_esecutore.py`, `prova_inoltro.py`, `prova_installa_satellite.py`
- **Agenti ed estensioni** ([elenco](elenco.md#agenti-ed-estensioni), [area](../docs/aree/agenti-estensioni.md)): `prova_estensioni.py`, `prova_estensioni_attacchi.py`, `prova_contesto_agenti.py`, `prova_estensioni_piano.py`, `prova_estensioni_ollama.py`, `prova_estensioni_agente.py`, `prova_agenti.py`, `prova_sandbox.py`, `prova_agenti_domande.py`, `prova_avanzamento.py`, `prova_esecuzione.py`, `prova_agenti_openai.py`, `prova_arbitro_vllm.py`, `prova_arbitro_pausa.py`, `prova_agenti_ollama.py`, `prova_lavori_criteri.py`, `prova_lavori.py`, `misura_contesto_agenti.py`, `misura_arbitro_vllm.py`
- **Giochi** ([elenco](elenco.md#giochi), [area](../docs/aree/giochi.md)): `prova_giochi.py`, `prova_giochi_pagina.py`
- **Capacità e installazioni** ([elenco](elenco.md#capacità-e-installazioni), [area](../docs/aree/capacita-installazioni.md)): `prova_capacita.py`, `prova_installa.py`, `prova_stato_ollama.py`
- **Personalità** ([elenco](elenco.md#personalità), [area](../docs/aree/personalita.md)): `prova_personalita.py`, `prova_personalita_ollama.py`, `misura_tono.py`, `misura_frasi_pronte.py`
- **Linux e DGX** ([elenco](elenco.md#linux-e-dgx), [area](../docs/aree/setup-dgx.md)): `prova_linux.py`, `prova_gestore.py`

## Passi manuali

- [`manuali/schermi.md`](manuali/schermi.md): «Prova manuale degli schermi (da fare a voce)»; «Prova manuale di «scrivere invece di parlare» (03/10)»
- [`manuali/immagini-allegati.md`](manuali/immagini-allegati.md): «Prova manuale delle foto (05/10)»; «Prova manuale degli allegati (05/10)»
- [`manuali/satelliti.md`](manuali/satelliti.md): «Prova manuale del satellite sul portatile»; «Un PC nuovo come satellite con un comando (03/10)»; «Prima prova end-to-end con la DGX (satellite in VPN)»
- [`manuali/telefono.md`](manuali/telefono.md): «Prova manuale del telefono (web app, 03/10)»; «Telefono da fuori casa (WireGuard e inoltro, 03/10)»
- `manuali/risultati-2026-09-23.md` (privato, fuori dal repository): risultati dei test del 23–24/09
- [`manuali/dgx-agenti.md`](manuali/dgx-agenti.md): «Prima prova sulla DGX Spark (agenti, 02/10/2026)»
- [`manuali/dgx-web-estensioni-giochi.md`](manuali/dgx-web-estensioni-giochi.md): «Ricerca su internet sulla DGX (SearXNG, 03/10)»; «Estensioni sulla DGX (04/10)»; «Giochi sulla DGX (05/10)»
- [`manuali/e2e-dgx.md`](manuali/e2e-dgx.md): «Prova end-to-end sulla DGX, senza nessuno che parli (06/10)»: istanza di prova separata, satelliti finti con VAD e wake word veri, voce vera di chi amministra, `python -m prove.e2e.lancia`
