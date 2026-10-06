# Calliope come server di casa: cosa offre già l'ecosistema Home Assistant (stato al 21 settembre 2026)

*Ricerca svolta da un agente il 21 settembre 2026 per la decisione A di docs/visione.md.*

Nessun file è stato modificato.

Affidabilità delle fonti: i dati presi da GitHub, PyPI e dalla documentazione ufficiale di HA sono solidi. Molti numeri di latenza e accuratezza vengono invece da blog di qualità incerta e li segnalo caso per caso.

## 1. Voce locale in Home Assistant oggi

**Pipeline Assist**
- Gli stadi sono: wake word, STT, agente di conversazione (intenti locali e/o LLM), TTS.
- Novità 2025: conversazione continuata (se l'LLM fa una domanda il microfono si riapre), due wake word con due pipeline per satellite (2025.10), azione "Ask Question", TTS in streaming.
- Novità 2026.8: integrazioni **llama.cpp / qualsiasi endpoint compatibile OpenAI** e **LiteLLM** come agenti di conversazione.
- L'ultimo "Voice chapter" è l'11 (ottobre 2025). Non ho trovato un capitolo 12 né annunci voce rilevanti nel 2026.
- Il 14 settembre 2026 sono state aperte due PR in bozza (core #182247 e #182248) per lo streaming dell'audio di risposta verso i satelliti Wyoming, VoIP ed ESPHome. La pipeline è quindi in fase di refactoring.

**Wyoming**
- È vivo come protocollo tra i servizi STT, TTS e wake word.
- Versioni: `wyoming` 1.10.2, `wyoming-piper` 2.5.2 (11 settembre 2026), `wyoming-faster-whisper` aggiornato il 14 settembre 2026.
- Ha eventi di streaming per il TTS (`synthesize-start/chunk/stop`) e per le trascrizioni.
- Usa TCP con intestazioni JSONL e payload PCM. Per progetto non ha autenticazione né cifratura: va usato solo su LAN fidata.

**wyoming-satellite è morto**
- Il repository è stato archiviato il 27 gennaio 2026.
- Lo sostituisce **linux-voice-assistant (LVA)** di OHF-Voice, che parla il **protocollo nativo ESPHome**. Versione v1.1.15 del 2 agosto 2026, sviluppo attivo.
- LVA richiede Python 3.11+ e PulseAudio/PipeWire. Supporta microWakeWord e openWakeWord, con soppressione del rumore e controllo del guadagno WebRTC. Richiede HA.
- Oggi tutti i satelliti vivi (Voice PE, Satellite1, schede ESP32-S3, LVA su Raspberry) parlano l'API ESPHome, non Wyoming.

**Piper**
- `rhasspy/piper` è stato archiviato a ottobre 2025. Il successore è **OHF-Voice/piper1-gpl**, v1.8.0 del 4 settembre 2026, con licenza **GPL-3.0** al posto di MIT. Conta solo se Calliope venisse distribuita.
- Il pacchetto pip `piper-tts` ha wheel per win_amd64, linux x86_64/aarch64 e macOS. **Non esiste un wheel win_arm64.**

**Hardware satellite (prezzi indicativi)**

| Dispositivo | Prezzo | Audio | Note |
|---|---|---|---|
| HA Voice Preview Edition | $69 / €59 di listino | ESP32-S3 + XMOS XU316, 2 microfoni, cancellazione dell'eco, soppressione del rumore e controllo del guadagno in hardware. Altoparlante piccolo più jack da 3,5 mm. Interruttore fisico che toglie corrente ai microfoni. | Ancora "Preview". Nessun successore annunciato. Regressioni firmware nel 2026: ESPHome 2026.3.x, issue voice-pe #621. |
| FutureProofHomes Satellite1.1 | $134,99 assemblato (esaurito al momento del controllo) | 4 microfoni, XMOS XU316, amplificatore da 20 W, woofer e tweeter, sensori, radar mmWave opzionale | Stessa architettura del Voice PE, audio migliore |
| Seeed ReSpeaker XVF3800 + XIAO ESP32S3 | circa $50–55 la scheda (su Amazon ho visto un annuncio a circa $186, prezzo non verificato) | 4 microfoni, beamforming, cancellazione dell'eco, dereverberazione, direzione di arrivo, fino a 5 m | Secondo la community è il migliore in campo lontano. Serve un altoparlante esterno. Firmware ESPHome della community. |
| ESP32-S3-BOX-3 | circa $60 | 2 microfoni, cancellazione dell'eco solo software, schermo | Solo campo vicino |
| Raspberry Pi Zero 2 W + ReSpeaker 2-mic HAT + LVA | circa $105 | Cancellazione dell'eco software | Nel 2026 i Raspberry sono rincarati per la crisi delle RAM |
| Speakerphone USB (Jabra Speak, Anker PowerConf circa $130) su Pi o mini PC con LVA | — | Cancellazione dell'eco hardware, full duplex | È l'opzione migliore per il barge-in |

**Barge-in**
- La cancellazione dell'eco XMOS permette di sentire la wake word anche durante la riproduzione.
- Sul Voice PE, dire la wake word mentre parla interrompe la risposta. Alcuni utenti riferiscono che va ripetuta per fare una nuova richiesta.
- Un barge-in conversazionale, cioè interrompere semplicemente parlando, in HA di serie non esiste.

## 2. Wake word "Calliope"

**openWakeWord (gira sul server)**
- L'upstream è fermo alla v0.6.0 di febbraio 2024.
- La guida ufficiale HA propone un notebook Colab da circa 1 ora con campioni sintetici Piper e dichiara "solo inglese". Il notebook originale nel 2026 è rotto.
- Esistono fork riparati. `alfiedennen/openwakeword-colab-2026` richiede 75–90 minuti su Colab Pro con GPU L4, oppure circa 2,5 ore su T4 gratuita, e scarica circa 25 GB di dati negativi. È stato verificato a maggio 2026.
- Un derivato di settembre 2026 aggiunge l'esportazione `.tflite`. L'add-on di HA carica solo `.tflite` e ignora i file `.onnx`.
- In Calliope può girare in-process con onnxruntime.
- Richiede audio continuo verso il server. Va bene per il microfono locale o per LVA, ma non per i satelliti ESP32, che rilevano la wake word sul dispositivo.

**microWakeWord (gira sul satellite)**
- Gira su ESP32-S3 e, tramite `pymicro-wakeword`, anche su LVA.
- Il trainer ufficiale `OHF-Voice/micro-wake-word` usa TensorFlow. Il suo stesso README dice che il notebook base "molto probabilmente non produce un modello usabile".
- Strumenti pratici:
  - **TaterTotterson/microWakeWord-Trainer-Nvidia-Docker**: interfaccia web su localhost, richiede GPU NVIDIA e ha un'immagine **Blackwell per le RTX 50**, quindi gira sul portatile attuale. Genera campioni con più TTS in oltre 600 lingue. Accetta registrazioni proprie e falsi risvegli come esempi negativi. Produce `.tflite` più `.json`.
  - `alfiedennen/microwakeword-trainer`: Colab su A100, circa 45 minuti, circa 30.000 campioni Piper, input in IPA per i nomi non inglesi. La T4 non basta.
- Tempi tipici: 30–90 minuti più i download. Una fonte indica 5,7 GB di negativi, che diventano 26 GB su disco.
- Installazione sul satellite: "take control" in ESPHome Builder, aggiungere `micro_wake_word: models: - model: <URL json>`, ricompilare e flashare via OTA. Un thread della community (aprile–agosto 2026) conferma il successo con "Hey Alan".

**Per "Calliope" in particolare**
- 4 sillabe: la lunghezza va bene.
- I generatori predefiniti producono un accento inglese. Conviene usare voci Piper italiane e fonemi IPA (`--phoneme-input`), più registrazioni reali della famiglia e negativi per le parole simili.
- Metti in conto più iterazioni.

## 3. LLM locale in HA

**Integrazione Ollama**
- Opzioni: modello, contesto (8k di default), keep-alive, interruttore "think".
- Il controllo dei dispositivi passa dall'API Assist (tool calling, ancora "sperimentale") e funziona solo con modelli che supportano i tool.
- La documentazione raccomanda di esporre **meno di 25 entità**. I modelli piccoli sono poco affidabili.

**Streaming frase per frase: sì**
- I delta dell'LLM passano dal `ChatLog` (`async_add_delta_content_stream`) al TTS in streaming (`async_stream_tts_audio`).
- wyoming-piper spezza le frasi e le sintetizza una per una.
- Dati ufficiali HA sul tempo di avvio dell'audio: Piper passa da 5,31 s a **0,56 s**, il TTS cloud da 6,62 s a 0,51 s.
- Limiti: le chiamate ai tool sono atomiche. Le risposte non generate in streaming, per esempio `set_conversation_response`, non vengono trasmesse a pezzi (issue #147727, chiusa come "not planned").
- Un agente personalizzato riceve `device_id` e `satellite_id` in `ConversationInput` (verificato nel sorgente).

**MCP**
- HA come **server** MCP dal 2025.2: endpoint `/api/mcp`, trasporto Streamable HTTP stateless, autenticazione OAuth o token long-lived. Espone tool, prompt e una risorsa.
- HA come **client** MCP: solo trasporto SSE e solo tool. Per i server stdio serve mcp-proxy.

**Modelli**
- Consenso 2026: famiglia Qwen3 (4B-Instruct-2507 per 8 GB di VRAM, 8B, 30B-A3B MoE), gpt-oss-20b, Gemma 4 (aprile 2026, include la variante MoE 26B-A4B), Qwen3.5 piccoli (0,8–9B).
- Con Qwen3.5 su Ollama sono segnalati problemi di tool calling, risolti passando a llama.cpp (forum, marzo 2026).
- I modelli "thinking" sono da evitare per la voce.
- Per lo Spark sono adatti i MoE.

**Misure da una sola fonte (techfuelhq: RTX 5080, llama.cpp)**
- Tempo al primo token a caldo: 126–144 ms per i modelli 3–4B, 585 ms per gpt-oss-20b.
- Accuratezza su 24 comandi: Qwen2.5-14B 95,8%, gpt-oss-20b 91,7%, Qwen3-4B 83,3%, Llama-3.2-3B 70,8% con errori pericolosi.
- Il prompt HA con le entità pesa 1,5–2,5k token, quindi la cache del prompt è decisiva.

**Latenza end-to-end riferita (blog vari)**
- 1–2 s nel caso migliore con GPU.
- 2–4 s nel caso tipico.
- 5–8 s su Raspberry Pi 5.

## 4. Le tre architetture a confronto

| Criterio | (A) HA gestisce audio e pipeline, Calliope è il cervello | (B) Calliope parla direttamente con i satelliti, HA è solo backend dispositivi | (C) Senza HA |
|---|---|---|---|
| Lavoro | **Minimo.** Dal 2026.8 basta esporre un endpoint compatibile OpenAI, senza codice dentro HA. | Medio-alto. Wyoming-satellite è archiviato, quindi bisogna parlare l'**API ESPHome** con `aioesphomeapi`, che espone `subscribe_voice_assistant`, `send_voice_assistant_event` e simili (verificato). Vanno reimplementati macchina a stati, server HTTP per l'audio TTS, timer, annunci, gestione di più satelliti e deduplica. | Enorme: Zigbee, Matter e ogni integrazione da rifare. |
| Latenza e streaming | Lo streaming frase per frase c'è. Endpointing VAD, salti intermedi e buffering sono di HA. Stima: circa 1,5–3 s. | Controllo totale. Il satellite riproduce comunque da URL con un suo buffer. Guadagno stimato rispetto ad A: 100–300 ms più l'endpointing proprio. | Come B |
| Personalità e voce | Ok: prompt proprio, Piper "paola" via Wyoming. | Totale | Totale |
| Riconoscimento di chi parla | Non nativo in HA. È fattibile se Calliope fornisce **anche l'STT via Wyoming**: riceve l'audio, calcola l'embedding e lo correla alla richiesta successiva usando il testo della trascrizione. | Naturale, perché l'audio è in casa. | Naturale |
| Strumenti non domotici | Calliope esegue i propri tool lato server e lascia passare quelli di HA. Oppure si usa HA come client MCP. | Nativi. HA si raggiunge via MCP o WebSocket. | Nativi |
| Robustezza | Se HA cade, la voce si ferma. L'interfaccia però è stabile (chat completions OpenAI, in linea col principio 1). | La voce sopravvive a un guasto di HA. L'API voce ESPHome non è un contratto pubblico per server terzi e il firmware cambia ogni mese. | Meno componenti, ma tutto a carico nostro |
| Dipendenze native / Windows ARM | Il pacchetto `wyoming` è Python puro. I moduli pesanti possono stare in WSL2, in container o su un'altra macchina. | In più servono protobuf, cryptography e zeroconf. | Come B, più lo stack domotico |

Trovato un precedente di tipo B: `isc/voice-assistant`. Usa satelliti ESPHome, una pipeline propria e HA via REST.

## 5. Dove far girare HA con un server Windows su ARM

- I metodi supportati sono solo due: **HAOS e Container**. Core e Supervised sono deprecati dal 2025.12.
- **HAOS su Hyper-V ARM64**: non è documentato. La guida Windows copre solo x86.
  - Esistono immagini `generic-aarch64`, ma senza VHDX.
  - Issue #2256 (2022): "waiting for root device". I driver Hyper-V per ARM64 sono stati aggiunti con la PR #2262, entrata a dicembre 2022.
  - Issue #3900 (febbraio 2025): su un PC Windows su ARM, "boot image not found". Chiusa senza una soluzione visibile.
  - Lo considero non affidabile.
- **Container in WSL2**: funziona, ma la rete è in NAT e mDNS/discovery sono problematici. La modalità mirrored aiuta solo in parte e confligge con Docker Desktop. Non ci sono add-on. L'USB passa solo con `usbipd-win` (la build ARM64 esiste), soluzione fragile. È meglio un coordinatore Zigbee di rete.
- **VM Debian ARM64 in Hyper-V più HA Container**: tecnicamente possibile. Su Snapdragon sono segnalati blocchi con più vCPU. Sullo Spark il comportamento è ignoto.
- **Dispositivo separato (raccomandato)**: HA Green (ora **$199/€179** dopo due rincari nel 2026; lo Yellow è fuori produzione), Raspberry Pi 5, oppure un mini PC N100 con HAOS. Così la domotica non dipende dai riavvii di Windows.
- RTX Spark: annunciato il 31 maggio 2026, in vendita da ottobre 2026 con Windows su ARM e l'emulatore Prism. Non ho trovato nulla su Hyper-V, WSL2 o CUDA in WSL.

**Wheel Python su Windows ARM (scoperta collaterale)**
- `onnxruntime` 1.30.0 **ha** i wheel win_arm64. Silero VAD, openWakeWord e i modelli di embedding in ONNX sono quindi a posto.
- **`ctranslate2` 4.8.2 (da cui dipende faster-whisper), `piper-tts` 1.8.0 e `sherpa-onnx` 1.12.28 non ne hanno.**
- Tutti e tre hanno wheel linux aarch64, quindi possono girare in WSL2 o in container dietro Wyoming.

## 6. Riconoscimento di chi parla

- In HA non c'è nulla di nativo. La discussione #527 (agosto 2025, 25 voti) non ha risposte ufficiali.
- C'è un proof of concept: `EuleMitKeule/speaker-recognition`. Usa Resemblyzer, quindi PyTorch. Il server richiede Python <3.10. È un servizio REST con entità STT e conversazione, 51 stelle.
- openWakeWord ha i "custom verifier models", ma verificano solo la wake word per voci specifiche.
- Opzione leggera raccomandata: modelli di embedding ONNX (WeSpeaker ResNet34/ECAPA, CAM++/ERes2Net, TitaNet) su **onnxruntime**, più numpy per i banchi di filtri, con confronto coseno sui profili registrati della famiglia.
- Librerie disponibili:
  - `sherpa-onnx`: matura, ma con codice nativo e senza wheel win_arm64.
  - `speakeronnx`: solo onnxruntime e numpy, licenza Apache-2.0, ma acerba (0 stelle).
  - `wespeakerruntime`: non verificata.
- Sono da evitare pyannote, SpeechBrain e Resemblyzer perché richiedono PyTorch.
- Progetto consigliato:
  - un modulo `identify(audio) → (chi, punteggio)` che gira in parallelo allo STT;
  - un fallback "sconosciuto";
  - nessun uso per autorizzare azioni sensibili.

## 7. Azioni sui PC Windows

- **HASS.Agent** (fork dell'organizzazione `hass-agent`; l'originale LAB02 è abbandonato):
  - .NET 8, MQTT più API locale, comandi personalizzati e PowerShell.
  - È attivo. Secondo l'API GitHub, release 2.2.0 il 19 gennaio 2026 e 2.2.1 il 7 giugno 2026. Repository aggiornato il 9 settembre 2026.
  - Solo build x64/x86, nessuna ARM64.
  - I comandi diventano entità HA, quindi l'LLM può azionarli con i tool esistenti.
- **IoTLink**: dismesso. Ultima release nel 2020, annuncio di fine progetto ad agosto 2022.
- **System Bridge** (timmo001):
  - Molto attivo, v5.8.2 del 20 settembre 2026. Scritto in Go, per Windows e Linux.
  - API HTTP/WebSocket con token.
  - Integrazione **core** di HA: apertura di file e URL, tasti, testo, comandi di alimentazione, notifiche, media.
  - Usa l'SDK MCP per Go. Poche installazioni (circa 329). Nessun asset ARM64.
- go-hass-agent: solo Linux.
- Alternativa fai-da-te, coerente coi principi: server OpenSSH integrato in Windows con script in allowlist, oppure un mini-agente Calliope con token e allowlist.

## Raccomandazione

**"A+" subito, B come evoluzione, mai C.**

1. **HA su un dispositivo dedicato con HAOS** (mini PC N100, Pi 5 o Green), usato per dispositivi e satelliti. Non va messo sul PC Windows ARM.
2. **Separare il nucleo di Calliope dal trasporto**: un'interfaccia `rispondi(testo, chi, stanza) → flusso di frasi`, esposta in tre modi:
   - un **endpoint compatibile OpenAI**, da collegare a HA 2026.8+ senza codice dentro HA;
   - un **server Wyoming STT** (Whisper più riconoscimento di chi parla);
   - un **server Wyoming TTS in streaming** (Piper "paola").
3. Così HA gestisce satelliti, wake word sul dispositivo, timer e stanze. Calliope tiene cervello, voce, identità di chi parla e strumenti propri. Wyoming diventa il confine fra i moduli, che possono spostarsi in WSL2 o in container dove mancano i wheel win_arm64.
4. **Misurare la latenza reale** contro la base attuale (0,2 s + 0,5 s). Se è inaccettabile, o se HA nel percorso critico pesa troppo, passare a **B con `aioesphomeapi`**. Nucleo e satelliti restano gli stessi, senza hardware da buttare.
5. **Satelliti**: iniziare con 1 Voice PE (€59) per validare. Per stanze grandi o rumorose usare ReSpeaker XVF3800 o Satellite1.
6. **Wake word**: addestrare "Calliope" per microWakeWord con il trainer Docker di TaterTotterson sulla RTX 5070. Nel frattempo usare "Okay Nabu".
7. **PC di casa**: System Bridge o HASS.Agent attraverso HA.

## Cosa NON sono riuscito a verificare

**Pipeline e integrazioni HA**
- La soglia esatta (in caratteri) dopo la quale la pipeline HA avvia lo streaming verso il TTS. Ricordo 60, ma non l'ho confermato.
- Se l'integrazione llama.cpp / compatibile OpenAI di HA trasmette le risposte in streaming. La documentazione non lo dice.
- Se il prompt di HA passa l'area del satellite sulla via compatibile OpenAI.
- Se un satellite ESPHome accetta un client voce diverso da HA mentre è adottato in HA. Ricordo un limite di un solo sottoscrittore.
- Il roadmap voce HA 2026: non ho letto la bacheca Figma né il repository roadmap.

**Hosting e Windows su ARM**
- Lo stato attuale di HAOS aarch64 su Hyper-V: i commenti della issue #3900 non si sono caricati.
- Il supporto di Hyper-V, WSL2 e CUDA-in-WSL su RTX Spark: l'hardware non è ancora in vendita.
- Il funzionamento di HASS.Agent e System Bridge sotto l'emulatore Prism.
- I wheel win_arm64 di cryptography, zeroconf, protobuf e torch.

**Progetti e librerie**
- Le date delle release di HASS.Agent. La pagina HTML indicava il 2024 e l'API il 2026: mi sono fidato dell'API.
- I dettagli del server MCP di System Bridge.
- La cancellazione dell'eco in LVA: ho confermato solo soppressione del rumore e controllo del guadagno WebRTC.

**Hardware e fonti**
- I prezzi di Satellite1 dev kit, ReSpeaker Lite e Atom Echo.
- Il prezzo reale dell'XVF3800 con custodia.
- botmonster.com non era raggiungibile. Il blog Seeed ha risposto 403.
- I numeri di latenza e accuratezza di techfuelhq, smarthomefieldguide e smarthomeexplorer non sono verificabili in modo indipendente.
- Non ho trovato resoconti di wake word con nomi **italiani** addestrate con successo.

## Fonti

**Home Assistant: blog e release**
- https://www.home-assistant.io/blog/2025/09/11/ai-in-home-assistant/
- https://www.home-assistant.io/blog/2025/06/25/voice-chapter-10/
- https://www.home-assistant.io/blog/2025/10/22/voice-chapter-11
- https://www.home-assistant.io/blog/2026/08/05/release-20268/
- https://www.home-assistant.io/blog/2025/05/22/deprecating-core-and-supervised-installation-methods-and-32-bit-systems/
- https://www.home-assistant.io/blog/2025/10/15/yellow-end-of-life/
- https://www.nabucasa.com/news/2026-01-08-green-pricing-change/

**Home Assistant: documentazione**
- https://www.home-assistant.io/integrations/ollama/
- https://www.home-assistant.io/integrations/llama_cpp/
- https://www.home-assistant.io/integrations/mcp_server/
- https://www.home-assistant.io/integrations/mcp/
- https://www.home-assistant.io/integrations/system_bridge/
- https://www.home-assistant.io/voice-pe/
- https://www.home-assistant.io/voice_control/create_wake_word/
- https://www.home-assistant.io/installation/windows
- https://developers.home-assistant.io/docs/core/entity/conversation/
- https://developers.home-assistant.io/docs/core/entity/tts/
- https://developers.home-assistant.io/docs/voice/pipelines/

**Home Assistant: core, issue e discussioni**
- https://raw.githubusercontent.com/home-assistant/core/dev/homeassistant/components/conversation/models.py
- https://github.com/home-assistant/core/pull/182247
- https://github.com/home-assistant/core/pull/182248
- https://github.com/home-assistant/core/pull/139542
- https://github.com/home-assistant/core/issues/147727
- https://github.com/orgs/home-assistant/discussions/527
- https://community.home-assistant.io/t/assist-qwen3-5-35b-a3b-tool-calling/991434
- https://community.home-assistant.io/t/plans-on-successor-of-ha-voice-preview-edition/923109

**OHF-Voice, Wyoming, Piper**
- https://github.com/OHF-Voice
- https://github.com/OHF-Voice/wyoming
- https://github.com/rhasspy/wyoming-satellite
- https://github.com/OHF-Voice/linux-voice-assistant
- https://api.github.com/repos/OHF-Voice/linux-voice-assistant/releases?per_page=3
- https://github.com/OHF-Voice/piper1-gpl
- https://api.github.com/repos/OHF-Voice/piper1-gpl/releases?per_page=3
- https://api.github.com/repos/OHF-Voice/wyoming-piper/releases?per_page=4
- https://github.com/rhasspy/wyoming-openwakeword
- https://github.com/OHF-Voice/pymicro-wakeword
- https://github.com/OHF-Voice/linux-voice-assistant/discussions/281
- https://www.openhomefoundation.org/blog/building-whats-next-state-of-the-open-home-2026/

**Wake word**
- https://github.com/dscripka/openWakeWord
- https://github.com/alfiedennen/openwakeword-colab-2026
- https://github.com/amandamarielux/openwakeword_update_sept_2026
- https://github.com/OHF-Voice/micro-wake-word
- https://github.com/TaterTotterson/microWakeWord-Trainer-Nvidia-Docker
- https://github.com/alfiedennen/microwakeword-trainer
- https://github.com/esphome/micro-wake-word-models/blob/main/models/v2/experiments/README.md
- https://esphome.io/components/micro_wake_word/
- https://community.home-assistant.io/t/home-assistant-voice-preview-and-setting-custom-wakeword/1006719
- https://gist.github.com/jlpouffier/41351187e2f6f94e797382a658702433

**Satelliti e architettura B**
- https://raw.githubusercontent.com/esphome/aioesphomeapi/main/aioesphomeapi/client.py
- https://raw.githubusercontent.com/esphome/aioesphomeapi/main/requirements/base.txt
- https://github.com/isc/voice-assistant
- https://futureproofhomes.net/products/satellite1-smart-speaker
- https://www.cnx-software.com/2025/07/29/respeaker-xmos-xvf3800-4-mic-array-board-features-esp32-s3-module-works-over-usb/
- https://www.smarthomeexplorer.com/guides/best-home-assistant-voice-satellite-2026
- https://github.com/esphome/home-assistant-voice-pe/issues/621

**Latenza e modelli (fonti deboli)**
- https://techfuelhq.com/tutorials/home-assistant-local-llm-voice-2026/
- https://smarthomefieldguide.com/blog/local-voice-assistant-home-assistant-build-log/

**Hosting e Windows su ARM**
- https://github.com/home-assistant/operating-system/issues/2256
- https://github.com/home-assistant/operating-system/issues/3900
- https://github.com/home-assistant/operating-system/pull/2262
- https://github.com/home-assistant/operating-system/releases/latest
- https://learn.microsoft.com/en-us/answers/questions/2156612/hyper-v-compatibility-with-snapdragon-arm64-cpu
- https://github.com/dorssel/usbipd-win
- https://en.wikipedia.org/wiki/Nvidia_RTX_Spark
- https://pypi.org/pypi/onnxruntime/1.30.0/json
- https://pypi.org/pypi/ctranslate2/4.8.2/json
- https://pypi.org/pypi/piper-tts/json
- https://pypi.org/simple/sherpa-onnx/

**Riconoscimento di chi parla**
- https://github.com/EuleMitKeule/speaker-recognition
- https://github.com/TigreGotico/speakeronnx
- https://k2-fsa.github.io/sherpa/onnx/speaker-identification/index.html
- https://arxiv.org/html/2210.17016v2

**Agenti per PC**
- https://github.com/hass-agent/HASS.Agent
- https://api.github.com/repos/hass-agent/HASS.Agent/releases?per_page=5
- https://github.com/orgs/hass-agent/repositories
- https://gitlab.com/iotlink/iotlink/-/issues/194
- https://github.com/timmo001/system-bridge
- https://api.github.com/repos/timmo001/system-bridge/releases?per_page=3
- https://github.com/joshuar/go-hass-agent
