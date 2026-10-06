# Pilotare i PC di casa con la voce: strategie, «Jev» e prove di sola lettura (26/09/2026)

*Ricerca del 26 settembre 2026 per la fase 6 della [visione](../visione.md) («PC: esecutore di
azioni sui PC di casa»). Non modifica Calliope. Prove di **sola lettura** sul portatile
(nessun clic, nessuna digitazione, nessuna impostazione cambiata) con gli script in
[`docs/ricerche/banchi/ricerca_pc/`](banchi/ricerca_pc/), in un venv separato (`docs/ricerche/banchi/ricerca_pc/.venv`, ignorato da git).
Ollama e la GPU non sono stati usati. Parte da
[`2026-09-21-orchestrazione-agenti.md`](2026-09-21-orchestrazione-agenti.md) e
[`2026-09-26-tool-e-agenti.md`](2026-09-26-tool-e-agenti.md), che qui non si ripetono.*

*Legenda: [V] verificato sulla fonte primaria (repository, PyPI, documentazione ufficiale);
[A] da aggregatori o stampa, non riscontrato; [D] mia deduzione; [M] misurato qui.*

## In breve

- **«Jev» esiste**: è **Jev di TypeSafe AI**, annunciato a metà settembre 2026 [V]. Non è un
  agente né un assistente: è un **modello di decisione** («System One») che riceve uno stato
  in JSON e domande tipizzate (`choice`, `score`, `noul` = vero/falso) e restituisce
  probabilità calibrate in 70–500 ms. **È solo cloud, con pesi non pubblicati e licenza
  proprietaria**: viola il principio 9. Il legame con «pilotare il PC a voce» viene da
  progetti della comunità nati questa settimana (`jev-desktop`, `jev-voice-computer-use-windows`),
  giovanissimi (0–1 stelle) e con chiavi cloud obbligatorie. L'equivalente locale è
  **ollaya** (Apache-2.0, ~310 stelle, API compatibile), ma per Calliope non serve: gemma4
  sceglie già il tool giusto nel 99 % dei casi. **Da non adottare**; da ritenere solo l'idea
  (decisioni chiuse invece di testo libero), che Calliope applica già con tool a enum.
- **Per il 90 % di ciò che si chiede a voce a un PC bastano azioni deterministiche**:
  volume, media, luminosità, blocco, spegnimento, aprire un'app o un file, cercare un
  file, stato. Misurati qui: leggere volume, finestre, processi, luminosità e sessione
  multimediale costa **0,1–50 ms**; una ricerca nell'indice di Windows **5–80 ms**; il
  salto HTTP con token verso un esecutore locale **qualche ms** (se il servizio tiene
  aperti gli oggetti COM). Tutto sta ben sotto il budget vocale, e tutte le librerie
  Python necessarie hanno wheel `win_arm64` o sono pure Python [V].
- **Gli agenti «a vista» (UI-TARS, Agent S, UFO, OmniParser…) oggi non sono praticabili**:
  un VLM da 7–9B non ci sta in 8 GB accanto a gemma4 e Whisper, i migliori piccoli aperti
  (UI-Mate-9B, UI-Venus-2-9B) dichiarano il 66–71 % su OSWorld-Verified ma **con numeri
  auto-dichiarati**, i passi durano secondi, e **la prompt injection dallo schermo riesce
  nel 40–86 % dei casi negli studi** (pop-up avversari, EIA, RedTeamCUA). Sullo Spark
  diventano possibili, ma solo come lavoro in secondo piano, confinato e con conferme.
- **La via di mezzo, UI Automation senza visione, funziona già**: leggere l'albero UIA
  di una finestra costa 25–220 ms per 20–370 elementi [M], ed è quello che fanno
  Windows-MCP e jev-desktop. Utile più avanti per poche azioni per app (per esempio «leggi
  la notifica», «clicca Rispondi in Teams»), non come agente generale.
- **Server MCP per Windows**: Windows-MCP (MIT, ~7,3k stelle, vivissimo) è pensato per LLM
  grandi, dà accesso totale (PowerShell, registro) e ha telemetria attiva; non ha ARM64.
  L'MCP di Windows (ODR, connettori Esplora file e Impostazioni) è ancora in **anteprima**.
  Per Calliope **nessuno è adatto come esecutore di base**.
- **HASS.Agent è vivo ma lento** (fork `hass-agent`, 2.2.1 del 07/06/2026 [V]; l'originale
  LAB02 è abbandonato dal 2023): comandi solo via MQTT, nessun build ARM64. **System Bridge**
  (Apache-2.0, 5.9.1 di oggi, riscritto in Go, integrazione ufficiale in Home Assistant) è
  l'alternativa più viva. Entrambi funzionano, ma mettono Home Assistant in mezzo a ogni
  comando al PC e non conoscono i livelli di Calliope.
- **Raccomandazione**: un **esecutore proprio, piccolo** (Python, ~400–600 righe) su ogni
  PC, che gira **nella sessione dell'utente** (app in tray avviata all'accesso, non servizio
  di sistema), **si collega lui al server** con un WebSocket autenticato da un token per PC,
  espone un **catalogo chiuso di capacità** con classe di rischio, e non esegue mai comandi
  liberi. Calliope le vede come **8 tool nativi** con parametri enum e `conferma` pronta.
  Primo passo: le capacità sul portatile stesso, senza rete (sezione 6).

---

## 1. Che cos'è «Jev»

### 1.1 Il candidato che combacia: Jev di TypeSafe AI

| | |
|---|---|
| Cos'è | Modello transformer di **decisione**, non generativo: input = stato (JSON) + domande tipizzate; output = scelta/punteggio/vero-falso con probabilità e confidenza [V] |
| Primitivi | `choice` (fino a 255 opzioni), `score` (livelli ordinati), `noul` (affermazioni vero/falso) [V] |
| Latenza dichiarata | 70–500 ms end-to-end; 0,114 s in un benchmark interno [V, dichiarata dal produttore] |
| Accesso | API `POST https://api.typesafe.ai/v1/systemone`, anche via OpenRouter, Vercel AI Gateway, Cloudflare Workers AI; supporto in Pydantic AI [V] |
| Prezzo | solo token d'ingresso (0,042 $; le fonti divergono tra «per milione» e «per miliardo»), uscita gratuita |
| Pesi / locale | **No**: nessun peso pubblicato, accesso con lista d'attesa, nessuna data per un rilascio [V] |
| Licenza | proprietaria [V] |
| Windows / ARM | irrilevante: è un servizio remoto |

Fonti: [MarkTechPost, 19/09/2026](https://www.marktechpost.com/2026/09/19/typesafe-ai-releases-jev/),
[OpenRouter](https://openrouter.ai/docs/guides/community/jev),
[Pydantic AI](https://pydantic.dev/docs/ai/models/typesafe/),
[«si può eseguire in locale?» (no)](https://www.modemguides.com/blogs/ai-news/jev-typesafe-reality-check-run-locally).

### 1.2 I progetti «Jev per pilotare il PC» (probabile origine della richiesta)

| Progetto | Cosa fa | Stato | Cloud |
|---|---|---|---|
| [jev-voice-computer-use-windows](https://github.com/Ayushmaniar/jev-voice-computer-use-windows) | Push-to-talk (Ctrl destro): legge la finestra in primo piano con UI Automation, Jev decide l'azione. STT anche locale su GPU NVIDIA (~1,3 GB) | 1 stella, 8 commit, licenza non indicata [V] | Chiave TypeSafe o OpenRouter obbligatoria |
| [jev-desktop](https://github.com/ehtan-smaltai/jev-desktop) | Ciclo osserva (UIA) → decide (Jev: CLICK, TYPE_TEXT, PRESS_KEY + bersaglio) → testo (piccolo LLM) → agisce, con ricontrollo del bersaglio prima di agire. Arresto d'emergenza, conferme per cancellazioni/invii/pagamenti, non tocca campi password né terminali | MIT, 0 stelle, 3 commit [V] | TypeSafe + OpenRouter obbligatori; niente Ollama |
| jev-voice (Windows e macOS), jev-voice-browser (Playwright) | Varianti simili | Amatoriali | Jev in cloud |
| [awesome-jev](https://github.com/Amal-David/awesome-jev) | Elenco dei progetti | — | — |

### 1.3 Alternative locali «stile Jev»

- **[ollaya](https://github.com/ollaya-dev/ollaya)**: «Ollama per i modelli di decisione».
  Apache-2.0, ~310 stelle; Windows x64, Linux x86-64/ARM64, macOS; API compatibile
  `/v1/systemone` più `/api/decide`; modelli aperti da 0,8B a 12B (Laya, decider, von,
  Winnow…) [V]. Nessun build Windows ARM64 dichiarato.
- **von** (wfzyx), **jev-local** (tapsin, sopra Ollama): amatoriali [V, stelle 0–1].
- Secondo una classifica di stampa [A]: decider-4b v2 sta in 8 GB, Winnow-12B vuole 16 GB,
  Laya (421M) gira su CPU.

### 1.4 Nomi simili, scartati

- **JEEV** (LWSanju): assistente vocale Windows su Gemini Live e OpenRouter, senza licenza,
  0 stelle: cloud.
- **py-gpt** (szczyglis-dev, ~1,9k stelle): assistente desktop con Ollama, voce, MCP e computer
  use; compare sotto il tag `jev` ma non c'entra.
- «Jarvis», «Jeeves»: nomi generici di centinaia di progetti; nessuno si impone.

### 1.5 Valutazione per Calliope

- **Così com'è: no.** Cloud obbligatorio (principio 9), schermo inviato a terzi (i progetti
  lo dichiarano), progetti di una settimana.
- **Come idea: già dentro Calliope.** Jev vince sulla latenza perché risponde a domande
  *chiuse*. Calliope ottiene lo stesso effetto con tool a parametri `enum` e con le regole
  prima dell'LLM (ricerca del 26/09: 99 % di scelta giusta con 40 tool).
- **ollaya come instradatore locale**: da riconsiderare solo se un giorno il routing
  diventasse il collo di bottiglia (centinaia di tool) e sullo Spark. Un decider-4b occupa
  circa quanto gemma4: oggi non ci sta.
- **jev-desktop come schema**: il ciclo «osserva UIA → decisione chiusa → ricontrolla il
  bersaglio → agisci», con arresto d'emergenza e conferme, è un buon modello per un eventuale
  agente UI futuro (sezione 2.2).

---

## 2. Famiglie di approcci

### 2.1 Tabella comparativa

| | a) Azioni deterministiche | b1) UI Automation senza visione | b2) Agente «a vista» (VLM) | c) Server MCP per Windows | d1) Esecutore proprio | d2) Ponte Home Assistant (HASS.Agent / System Bridge) |
|---|---|---|---|---|---|---|
| Esempi | pycaw, pywin32, winrt, PowerShell | pywinauto, uiautomation, parte UIA di UFO², jev-desktop | UI-TARS, Agent S3, OmniParser, UI-Mate, Fara | Windows-MCP, sbroenne/mcp-windows, Desktop Commander, ODR | servizio Python sul PC, catalogo chiuso | app .NET/Go sul PC + integrazione HA |
| Latenza | 0,1–80 ms [M] | 25–220 ms per leggere una finestra [M], +1 turno LLM per passo | 1–3 s per passo [D], compiti a molti passi | quella del tool sottostante + stdio/HTTP | come a) + pochi ms di rete [M] | a) + MQTT/HA (non misurato, decine di ms [D]) |
| Affidabilità con un 4B | ~100 % (l'LLM sceglie solo tool ed enum) | buona su azioni guidate per app, scarsa come agente libero | inutilizzabile con un 4B; 9B aperti 66–71 % OSWorld-Verified auto-dichiarati | tool generici (Click, Type, PowerShell): pensati per LLM grandi | come a) | come a), ma i nomi delle entità vanno nell'enum |
| Sicurezza | ottima: elenco chiuso | media: può cliccare ovunque nell'app | scarsa: prompt injection dallo schermo 40–86 % | variabile; Windows-MCP e Desktop Commander = accesso totale | ottima: classi di rischio, token per PC, log | buona, ma permessi solo lato HA (non per persona) |
| Offline | sì | sì | sì solo con VLM locale | sì | sì | sì (HA locale) |
| Win x64 | sì | sì | sì | sì | sì | sì |
| Win ARM64 | sì: pywin32 e winrt con wheel, pycaw/comtypes/sbc puri [V] | quasi: pywinauto e comtypes puri; `uiautomation` ha solo DLL x86/x64 (usate per le catture) [V] | dipende dal runtime (vLLM no su Windows; llama.cpp/Ollama sì) | Windows-MCP no (`dxcam`, `cryptography`); sbroenne sì (.NET, zip arm64) [V] | sì, se si evita l'SDK `mcp` | HASS.Agent no (x64/x86); System Bridge non verificato |
| Dipendenze native | poche | poche | torch/vLLM, molta VRAM | fastmcp → `cryptography` | nessuna oltre a pywin32 | runtime .NET o binario Go; broker MQTT |
| Costo di sviluppo | basso | medio | alto | basso da installare, alto da mettere in sicurezza | medio (~400–600 righe) | basso |

### 2.2 a) Azioni deterministiche

| Capacità | Come (Windows) | Libreria | ARM64 |
|---|---|---|---|
| Volume, muto, volume per app | Core Audio (`IAudioEndpointVolume`, sessioni) | pycaw 20260921 su comtypes 1.4.17 | puro Python [V] |
| Media play/pausa/avanti, «cosa sta suonando» | GlobalSystemMediaTransportControls (WinRT); in alternativa tasti multimediali virtuali | winrt-Windows.Media.Control 3.2.1 | wheel arm64 [V] |
| Luminosità | WMI (portatili) / DDC-CI (monitor esterni) | screen_brightness_control 0.27.2 | puro Python [V] |
| Blocco schermo | `LockWorkStation()` | ctypes / pywin32 312 | wheel arm64 [V] |
| Spegni, riavvia, sospendi | `shutdown /s /t 60` (annullabile con `/a`), `SetSuspendState` | subprocess / ctypes | — |
| Aprire app | catalogo per PC: nome parlato → AUMID/percorso; `explorer shell:AppsFolder\<AUMID>` o `os.startfile` | stdlib | — |
| Aprire file / cartelle | `os.startfile` su un risultato di ricerca o su cartelle note | stdlib | — |
| Cercare file | indice di Windows via OLE DB `Search.CollatorDSO` (SQL su `SYSTEMINDEX`); in alternativa Everything (`es.exe`, ha build ARM64) | pywin32 (ADODB) | provider su ARM64 non verificato |
| Appunti | `win32clipboard` | pywin32 | sì |
| Screenshot | `PIL.ImageGrab` / `mss` (non `dxcam`: solo amd64) | pillow | sì [V] |
| Notifiche | toast WinRT | win11toast 0.36.3 | puro, su winrt [V] |
| Stato (programmi aperti, batteria, inattività, blocco) | EnumWindows, psutil, GetLastInputInfo | pywin32, psutil 7.2.2 | sì [V] |

Da evitare: `keyboard` (nessuna release dal 2020) e `pyautogui` (fermo dal 2023) per ciò
che ha un'API dedicata; le API sono più affidabili dei tasti simulati e non dipendono da
quale finestra ha il fuoco. PowerShell va usato **dentro** capacità scritte a mano, mai come
comando libero dettato dal modello.

### 2.3 b) UI Automation e agenti «UI-grounded»

**Senza visione (albero di accessibilità).**
- pywinauto 0.6.9 (BSD-3, ultima release 01/2025, repo vivo) e uiautomation 2.0.29
  (Apache-2.0, 08/2025) sono puri Python su comtypes [V]. `uiautomation` include DLL solo
  x86/x64, usate per le catture bitmap: su ARM64 il nucleo dovrebbe funzionare senza di esse
  [D dal sorgente, non provato].
- È la tecnica di Windows-MCP (0,2–0,5 s per azione dichiarati), di jev-desktop e della
  parte UIA di UFO².
- Limite visto qui [M]: le app Electron/Chromium (VS Code, Edge, Teams) espongono l'albero
  completo solo dopo che un client UIA lo chiede (VS Code: 19 elementi alla prima lettura,
  366 alla seconda); le app UWP sospese o ridotte a icona ne mostrano uno solo. Serve quindi
  una prima lettura «a vuoto» e le finestre devono essere visibili.

**Con visione (VLM sugli screenshot)** — stato a settembre 2026:

| Progetto | Licenza, stato | Modelli locali | Numeri |
|---|---|---|---|
| Microsoft UFO² / UFO³ «Galaxy» | MIT, v3.0.10 del 22/09/2026, vivo [V] | pensato per GPT-4o/o1, Qwen, Gemini; nessuna guida per Ollama | UFO²: ~+10 punti su Operator in WAA (paper 04/2025) |
| Windows Agent Arena | MIT, poco attivo; 154 compiti; umani 74,5 % [V] | è un benchmark | classifica non aggiornata |
| OmniParser v2 (+detector v3) | CC-BY-4.0, lento ma vivo [V] | torch + YOLO; 0,6–0,8 s per schermata su A100/4090 | ScreenSpot-Pro 39,6 |
| Agent S3 (Simular) | Apache-2.0, vivo | grounding locale UI-TARS-1.5-7B, ragionamento in cloud | 72,6 % OSWorld (best-of-N), 56,6 % WAA, **con GPT-5** |
| UI-TARS-1.5-7B / desktop | Apache-2.0; UI-TARS-2 non aperto; desktop poco usabile secondo una recensione [A] | 7B | OSWorld 27,5 %, ScreenSpot-Pro 49,6 |
| OpenCUA 7/32/72B | MIT, vLLM | 32B+ | OSWorld-Verified 34,8 % (32B), 45,0 % (72B) |
| Fara-7B → Fara1.5 (4B/9B/27B) | MIT, pesi 22/07/2026 | **solo browser** (Playwright), GGUF citati | WebVoyager 86,6 (9B) |
| UI-Mate-9B (Tencent) | Apache-2.0, 08/2026 | ~19 GB di memoria [A] | OSWorld-Verified 66,2, WAA 61,7 (auto-dichiarati) |
| UI-Venus-2-9B | licenza «in attesa di conferma» | — | OSWorld-Verified 70,8, ScreenSpot-Pro 73,0 (auto-dichiarati) |
| Qwen3.5-4B / 9B (generalisti, su Ollama) | Apache-2.0 | 4B/9B | OSWorld-Verified 35,6 / 41,8 |
| Open Interpreter | riscritto in Rust, ora agente di coding; `--os` deprecato | via LiteLLM | — |
| self-operating-computer, Bytebot | fermo / archiviato | — | da scartare |
| Claude computer use, OpenAI CUA | cloud, solo riferimento | — | i modelli di frontiera superano ormai gli umani su OSWorld-Verified (72 %) [A] |

Per Calliope oggi:
- **VRAM**: 8 GB meno ~4 GB di gemma4 meno ~0,8 GB di Whisper: un VLM 7–9B in 4 bit
  (5–7 GB [D]) non ci sta, e scambiare modelli costa secondi a ogni cambio.
- **Latenza**: un compito GUI tipico richiede 5–20 passi da 1–3 s [D]: è per forza un
  **lavoro in secondo piano** dietro l'arbitro della GPU («ci penso io, ti avviso»), mai
  il percorso vocale (principio 11).
- **Affidabilità**: anche i migliori 9B falliscono un compito su tre; un'azione sbagliata
  nell'interfaccia (inviare, cancellare, pagare) non si annulla.

**Windows «agentico» di Microsoft.** Agent Workspace e Copilot Actions (anteprima Insider
da 11/2025): account separato non amministratore per ogni agente, accesso a sei cartelle
note, avviso esplicito sulla prompt injection (XPIA) [V]. MCP on Windows / On-device Agent
Registry: ancora «prerelease» (pagina aggiornata il 04/06/2026), server confinati in una
sessione separata, host con identità MSIX, connettori Esplora file e Impostazioni [V].
È il modello concettuale giusto (identità per agente, consenso, registro), ma è in
anteprima, orientato a Copilot+ e, confinato, **non vede il desktop dell'utente**. Da
rivalutare quando sarà stabile.

### 2.4 c) Server MCP per Windows

| Server | Licenza, versione | Tool | Sicurezza | ARM64 | Per Calliope |
|---|---|---|---|---|---|
| [Windows-MCP](https://github.com/CursorTouch/Windows-MCP) (CursorTouch) | MIT, v0.8.6 del 26/09/2026, ~7,3k stelle, Python ≥3.14 | 20+: Click, Type, Snapshot (UIA), App, **PowerShell**, FileSystem, Clipboard, Process, Notification, **Registry**… | token, allowlist IP, TLS/OAuth, selezione dei tool; **nessuna conferma per azione**; **telemetria posthog attiva** di default | no (`dxcam`, `cryptography`) | no come base; utile da studiare |
| [sbroenne/mcp-windows](https://github.com/sbroenne/mcp-windows) | MIT, v1.3.24 del 12/09/2026, 99 stelle, C#/.NET 10 | 18: ui_snapshot/find/click/type, finestre, processi, app, appunti | allowlist/denylist dei tool | **sì, zip arm64 nativo** [V] | l'unico MCP desktop pronto per lo Spark; stessi limiti di sicurezza |
| Desktop Commander | MIT, 0.2.51, ~9,8k stelle, Node | terminale, file, processi, documenti | per ammissione del README la blocklist si aggira; consiglia Docker | Node | no |
| Filesystem ufficiale | 2026.8.31, Node | 13 tool su file | cartelle ammesse | Node | forse per i documenti personali, non per i PC |
| PowerShell.MCP (yotsuda) | MIT, 1.14.2, C# | esegue comandi in una console visibile | nessuna allowlist | non dichiarato | no |
| MCP on Windows (ODR) | Microsoft, anteprima | connettori Esplora file, Impostazioni | confinamento, consenso | non verificato | da rivalutare |

Nota: **ogni server o client MCP in Python porta `cryptography`** (tramite `mcp` 2.2.0 →
`pyjwt[crypto]`, e `fastmcp` 4.0.10), che dalla 46.0.4 non ha wheel `win_arm64`: ancora
nessuna fino alla 50.0.1 del 25/08/2026 [V]. Conferma la scelta dell'architettura dei tool:
i PC entrano come **tool nativi** che parlano all'esecutore con un protocollo proprio; un
ponte MCP scritto a mano (JSON-RPC su HTTP) resta possibile senza l'SDK.

### 2.5 d) Esecutore sui PC contro ponte Home Assistant

**HASS.Agent** ([fork attivo](https://github.com/hass-agent/HASS.Agent), MIT, C#/.NET 8,
~1,3k stelle):
- versioni: 2.2.0 (19/01/2026), **2.2.1 (07/06/2026)**, ultimo push 09/09/2026, 104 issue
  aperte [V]; il progetto originale LAB02-Research è fermo dal 2022–23.
- funzioni: sensori (CPU, webcam in uso, sessione), comandi (app, spegnimento, PowerShell,
  tasti, URL), azioni rapide, notifiche con pulsanti, media player e TTS, servizio
  «Satellite» attivo anche senza utente collegato.
- **i comandi passano solo via MQTT**; l'API locale (porta 5115, token) serve solo a notifiche
  e media player; integrazione da HACS. La 2.2.0 ha tolto LibreHardwareMonitor.
- **nessun build ARM64** (richiesta aperta dal 05/2025).
- **Vivo nel 2026: sì, ma con rilasci lenti.**

**System Bridge** ([timmo001](https://github.com/timmo001/system-bridge), Apache-2.0,
riscritto in Go, **5.9.1 del 26/09/2026**, rilasci frequenti) [V]: API WebSocket/REST con
token, **integrazione ufficiale in Home Assistant** (sensori, media player, notifiche,
apertura di URL e percorsi, tasti e testo, spegnimento, blocco, sospensione, processi).
La v5 richiede di rifare token e integrazione. Build ARM64 non pubblicato (in Go sarebbe
facile [D]).

**IOT Link** è morto (2020–22); **hass-workstation-service** è archiviato; un'app ufficiale
di Home Assistant per Windows **non esiste** (solo app della comunità, x64).

**Confronto per Calliope.**

| | Esecutore proprio | Ponte Home Assistant |
|---|---|---|
| Percorso | Calliope → PC | Calliope → HA (Raspberry) → MQTT/WebSocket → PC |
| Chi parla, livelli | il server manda la persona e il livello a ogni richiesta; il PC può avere regole sue («il PC di Dario accetta solo Dario e chi amministra») | HA vede un solo utente (il token di Calliope): i permessi per persona restano tutti in Calliope |
| Catalogo e rischio | dichiarato dall'esecutore (principio 14) | da mappare a mano su pulsanti/comandi HA |
| Offline | sì | sì (se il Raspberry è acceso) |
| Satellite audio sul PC | lo stesso programma può diventare il satellite (visione, punto 8) | no |
| Costo | ~400–600 righe + installazione | installare e configurare, zero codice |
| Rischi | codice nostro da mantenere | due progetti esterni, x64 soltanto, un punto di guasto in più |

**Conclusione**: esecutore proprio. Home Assistant resta il ponte per la **casa**; per i PC
aggiunge un salto e non sa nulla di chi parla. System Bridge va bene come ripiego rapido
per un PC «di tutti» (per esempio quello del salotto) se si vuole vederlo anche nei
cruscotti di HA.

---

## 3. Sicurezza

1. **Chi può comandare quale PC.** Ogni PC ha un **proprietario** (uno o più
   `UserProfile.id`) e un **livello minimo** per classe di rischio. Esempio:
   - lettura (stato, cosa suona): familiare; sul PC di un altro solo chi amministra;
   - reversibile (volume, media, luminosità, blocco, aprire un'app): familiare, sul PC
     proprio o su quelli «di tutti»; l'ospite solo volume/media del PC della stanza in cui
     parla, se chi amministra lo permette;
   - irreversibile o delicato (spegnere, riavviare, aprire un file, leggere risultati di
     ricerca che rivelano nomi di file): proprietario o chi amministra, **con conferma**.
2. **La voce non basta** per ciò che è irreversibile o tocca i dati di un altro (visione,
   punto 9). Conferma verbale gestita da regole, non dall'LLM (sì/no, il silenzio vale
   «no»), e per le poche azioni davvero sensibili un secondo fattore: presenza fisica
   (l'azione si fa solo se il PC è sbloccato **e** attivo da meno di N secondi), notifica
   sul PC con pulsante «Consenti», oppure PIN detto una sola volta per sessione.
   Spegnimento con ritardo di 60 s e annullabile («Calliope, annulla»).
3. **Elenco consentito, non vietato.** L'esecutore esegue solo capacità scritte nel suo
   codice, con parametri validati (enum, intervalli). Niente PowerShell libero, niente
   percorsi arbitrari: i file si aprono solo come «risultato n dell'ultima ricerca» o
   come cartelle note. Le blocklist si aggirano (lo ammette Desktop Commander).
4. **Account utente, mai amministratore.** L'esecutore gira nella sessione dell'utente con
   i suoi diritti (serve comunque: volume, media e finestre sono per sessione, un servizio
   di sistema in sessione 0 non li vede). Niente UAC, niente registro, niente
   installazioni.
5. **Schermo bloccato.** A schermo bloccato l'esecutore rifiuta tutto ciò che mostra o apre
   contenuti (file, app, stato delle finestre) e ammette solo volume, media, spegnimento
   confermato. Mai sbloccare il PC a voce.
6. **Rete.** È l'esecutore a collegarsi al server (WebSocket in uscita): nessuna porta in
   ascolto sui PC. Token lungo e casuale per PC, generato all'abbinamento e revocabile dal
   server; TLS con il certificato del server fissato nell'esecutore (il certificato si
   genera una volta sul server; l'esecutore usa solo `ssl` della libreria standard, niente
   `cryptography`). Richieste con identificativo e scadenza (niente ripetizioni).
7. **Registro.** Ogni richiesta finisce in un registro su entrambi i lati: chi (persona,
   livello, punteggio della voce), quale PC, quale capacità, argomenti, esito, se c'è
   stata conferma. È lo stesso spirito del registro dei turni.
8. **Agenti UI e prompt injection.** Tutto ciò che si legge dallo schermo è **dato, mai
   istruzione**. Negli studi un pop-up avversario fa deviare l'agente nell'86 % dei casi
   (ACL 2025), EIA ruba dati personali fino al 70 % (ICLR 2025), RedTeamCUA trova agenti che
   *tentano* l'azione malevola fino al 92,5 % delle volte (ICLR 2026); OpenAI scrive che il
   problema «probabilmente non sarà mai risolto del tutto». Quindi un eventuale agente UI:
   solo in secondo piano, solo su app in elenco, mai su email e browser aperti su pagine
   esterne, con conferma prima di ogni azione che invia, cancella o paga, e con un arresto
   d'emergenza («Calliope, fermati»).

---

## 4. Prove di sola lettura sul portatile

Alienware, Windows 11 Enterprise 26200, Python 3.14.6, venv `docs/ricerche/banchi/ricerca_pc/.venv` con
pywin32 312, comtypes 1.4.17, pycaw 20260921, uiautomation 2.0.29, pywinauto 0.6.9,
psutil 7.2.2, screen_brightness_control 0.27.2, winrt 3.2.1, pillow, httpx. Mediane su 3–5
ripetizioni; «primo» = prima chiamata a freddo. Esplora risorse e Blocco note non erano
aperti: l'albero UIA è stato letto sulle finestre presenti (Terminale, VS Code, Edge, Teams).
Nessun nome di file o contenuto di finestra è stato stampato o salvato.

| Prova | Risultato | Mediana | Primo |
|---|---|---|---|
| Finestre visibili con titolo (EnumWindows) | 11 finestre | 0,2 ms | 1,0 ms |
| Programma di ogni finestra (pid → nome) | 9 programmi | 0,1 ms | — |
| Processi (psutil) | 372 | 1,0 ms | 8,4 ms |
| Volume e muto (pycaw, aprendo l'endpoint a ogni lettura) | 58 %, non muto | 41,6 ms | 48 ms |
| Volume con l'endpoint già aperto | — | **0,016 ms** | apertura 57 ms |
| Sessioni audio per programma | 4 programmi | 41 ms | — |
| Luminosità (WMI) | 100 % | 8,6 ms | 41 ms |
| Sessione multimediale corrente (WinRT GSMTC) | nessuna in riproduzione | — | 10 ms |
| Windows Search, nome file `LIKE '%fattura%'` (TOP 10) | 10 risultati | 78 ms | 185 ms |
| Windows Search, PDF modificati negli ultimi 30 giorni | 10 risultati | 8,7 ms | 19,5 ms |
| Windows Search, testo `CONTAINS('"calliope"')` | 1 risultato | 4,9 ms | 9,7 ms |
| Everything (`es.exe`) | non installato | — | — |
| Albero UIA, Windows Terminal | 37 elementi (15 interattivi) | 25 ms | 181 ms |
| Albero UIA, VS Code | 366 elementi (98 interattivi); **19 alla prima lettura** | 178 ms | — |
| Albero UIA, Edge (finestra principale) | 303 elementi (129 interattivi) | 221 ms | — |
| Albero UIA, Teams | 189 elementi (43 interattivi) | 171 ms | — |
| Albero UIA, Impostazioni (ridotta/sospesa) | 1 elemento | 1–7 ms | — |
| Pulsanti della barra delle applicazioni (UIA) | 22 | 34 ms | 53 ms |
| pywinauto (backend UIA), stesso Terminale | 21 discendenti | 11 ms | 13 ms |
| Inattività (GetLastInputInfo) / schermo bloccato (LogonUI) | 8,9 s / no | — | — |
| Cattura dello schermo in memoria (2560×1600, non salvata) | — | 43 ms | 49 ms |
| **Esecutore HTTP locale** con token (stdlib + httpx, connessione tenuta aperta), capacità `volume_leggi` | 401 senza token; volume 58 con token | 54 ms (p90 61) | 115 ms |

Cosa se ne ricava:
- **Tutte le letture di stato stanno sotto i 50 ms**, la maggior parte sotto i 10: si
  possono fare *prima* del turno LLM e mettere nel messaggio di contesto, come la memoria.
- **Tenere aperti gli oggetti COM**: i 54 ms del giro HTTP sono quasi tutti l'apertura
  dell'endpoint audio a ogni richiesta (57 ms); con l'endpoint in cache la lettura costa
  0,016 ms e il salto di rete sul portatile resta nell'ordine dei millisecondi [D dalla
  differenza; da rimisurare con l'endpoint in cache]. In LAN si aggiungono 1–5 ms [D].
- **Windows Search è sufficiente** per «trova il PDF della bolletta»: le query per nome
  con `LIKE '%…%'` costano ~80 ms (185 a freddo), quelle per testo con `CONTAINS` e per
  data meno di 10. Everything sarebbe più veloce sui nomi ma è un'installazione in più.
- **L'albero UIA è abbordabile ma rumoroso**: 100–370 elementi per un'app vera sono
  ~2–8k token se passati a un LLM; un agente UI deve filtrare ai soli elementi interattivi
  con nome (40–130) e deve «svegliare» le app Chromium con una prima lettura.

Script: [`docs/ricerche/banchi/ricerca_pc/sonde.py`](banchi/ricerca_pc/sonde.py) (stato, volume, luminosità, Windows
Search, UIA, cattura), [`docs/ricerche/banchi/ricerca_pc/sonde_uia.py`](banchi/ricerca_pc/sonde_uia.py) (albero UIA per
finestra, sessione multimediale), [`docs/ricerche/banchi/ricerca_pc/sonda_rete.py`](banchi/ricerca_pc/sonda_rete.py)
(esecutore HTTP minimo con token, solo lettura).

---

## 5. Raccomandazione per Calliope

### 5.1 Architettura

```
Calliope (server)                                     PC di casa (uno per PC)
Brain → tool nativi pc_* ──► PCHub ◄══ WebSocket TLS, token per PC ══ Esecutore (app in tray,
        (livello, conferma,   (quali PC sono collegati,               sessione utente, avvio
         registro)             inoltro, scadenze)                      all'accesso)
                                                                       └ catalogo di capacità:
                                                                         nome, parametri, rischio,
                                                                         livello minimo, conferma
```

- **Tool nativi, non MCP** (architettura dei tool, sezione 1): servono i livelli di chi
  parla, le conferme e la stanza; e si evita `cryptography` su ARM.
- **Capacità al centro, marche ai bordi** (principio 14): i tool parlano di `pc_volume`,
  non di pycaw; l'esecutore Windows è il primo adattatore (un domani macOS o Linux).
- **Il catalogo lo dichiara l'esecutore** all'abbinamento (capacità, app installate
  esposte, cartelle note), il server lo trasforma negli `enum` dei tool. Gli enum cambiano
  di rado: l'elenco dei tool resta fisso e la cache del prefisso regge (ricerca del 26/09).
- **Quale PC**: parametro `pc` con enum dei PC collegati, predefinito «quello della stanza
  in cui si parla» (oggi: il portatile stesso). Se un PC è spento, il tool sparisce o
  risponde con un errore chiaro («il PC dello studio è spento»), come i tool che richiedono
  internet (principio 12).
- **Regole prima dell'LLM** per i comandi più frequenti in forma chiusa («alza/abbassa il
  volume», «pausa», «blocca il PC»): < 10 ms, come proposto per la casa.
- **Stesso programma del satellite** (visione, punto 8): l'esecutore è la base del futuro
  satellite audio sui PC.

### 5.2 Primo insieme di capacità (8 tool)

| Tool | Parametri | Rischio | Livello | Conferma pronta (esempio) |
|---|---|---|---|---|
| `pc_stato` | `pc`, `cosa`: enum {volume, musica, batteria, programmi_aperti, bloccato} | lettura | familiare (programmi aperti: proprietario) | «Sul portatile il volume è al 58 % e non suona niente.» |
| `pc_volume` | `pc`, `azione`: enum {alza, abbassa, imposta, muto, riattiva}, `valore` 0–100 (solo per imposta) | reversibile | familiare; ospite solo sul PC della stanza, se abilitato | «Fatto, volume al 40 %.» |
| `pc_media` | `pc`, `comando`: enum {riproduci, pausa, avanti, indietro} | reversibile | familiare | «In pausa.» |
| `pc_luminosita` | `pc`, `azione`: enum {alza, abbassa, imposta}, `valore` | reversibile | familiare | «Luminosità al 70 %.» |
| `pc_apri_app` | `pc`, `app`: enum dal catalogo del PC (nomi parlati: «browser», «posta», «Word», «calcolatrice»…) | reversibile | familiare, sul PC proprio o comune | «Apro Word sul portatile.» |
| `pc_blocca` | `pc` | reversibile (aumenta la sicurezza) | familiare | «PC bloccato.» |
| `pc_cerca_file` | `pc`, `testo`, `tipo`: enum {qualsiasi, documento, pdf, foto, musica, video}, `periodo`: a parole («la settimana scorsa», convertito in Python come `tempi.py`) | lettura (ma rivela nomi) | proprietario del PC | «Ho trovato 3 PDF: Bolletta luce agosto, … Quale apro?» |
| `pc_apri_file` | `pc`, `risultato`: intero (dalla ricerca precedente) | reversibile, delicato | proprietario; rifiutato a schermo bloccato | «Apro Bolletta luce agosto.» |
| *(dopo)* `pc_spegni` | `pc`, `azione`: enum {spegni, riavvia, sospendi, annulla} | irreversibile | proprietario o chi amministra, **conferma** a regole, ritardo 60 s annullabile | «Spengo il PC dello studio tra un minuto. Confermi?» |

Scelte di formato, coerenti con la ricerca del 26/09:
- **un tool per dominio, con un verbo in enum piccolo** (4–5 valori), non un meta-tool
  `pc(azione, …)` generico: il meta-tool per categoria scendeva al 90 %;
- valori **come detti a voce** e convertiti in Python (periodi, «un po' più alto» → +10);
- ogni risultato con `conferma` già pronta e, per gli errori di permesso, il testo
  esplicito «NON è stato eseguito»;
- da provare con il banco di `docs/ricerche/banchi/ricerca_tool/` aggiungendo questi 8 tool al catalogo (48 in
  tutto): la soglia sopra la quale accendere il recupero è ~40–50.

### 5.3 Roadmap

1. **Subito, senza rete** (1–2 giorni): modulo `calliope/pc/` con le capacità della
   tabella sul **portatile stesso** (esecutore «in processo»), dietro un'interfaccia che
   domani passa per il WebSocket. Tool con livelli e conferme; registro. Prova come
   `prove/prova_agenda.py`: richieste vocali → tool e argomenti giusti.
2. **Esecutore separato** (2–3 giorni): lo stesso codice in un'app in tray che si collega
   al server con token per PC, abbinamento («Calliope, aggiungi questo PC» + codice di 6
   cifre mostrato sul PC), revoca, registro lato PC. Avvio all'accesso con l'Utilità di
   pianificazione (non un servizio). Collaudo tra portatile e un secondo PC.
3. **Stato nel contesto**: lo stato dei PC della stanza (cosa suona, volume) letto prima del
   turno e messo nel messaggio variabile, così «abbassa» non chiede «dove?».
4. **UI Automation guidata, per poche app** (quando serve davvero, fase 6+): capacità scritte
   a mano sopra UIA («leggi l'ultima notifica», «rispondi in Teams: …» con conferma), mai un
   agente libero. Schema jev-desktop: leggi → scegli tra elementi numerati → ricontrolla →
   agisci.
5. **Agente UI generale, solo sullo Spark e solo se servirà**: VLM aperto 9–27B (UI-Venus-2,
   UI-Mate, Qwen3.5/3.8) come lavoro in secondo piano dietro l'arbitro, su compiti scritti,
   con conferma prima di ogni azione non annullabile, fuori da email e browser esterni,
   idealmente in un account separato (modello Agent Workspace). Misurare prima con un banco
   proprio: i numeri di OSWorld sono auto-dichiarati.

### 5.4 Sullo Spark e su ARM

- **L'esecutore gira sui PC**, non sul server: l'ARM dello Spark conta solo se lo Spark è
  anche un PC usato da qualcuno. In quel caso: pywin32 (wheel arm64), pycaw, comtypes,
  screen_brightness_control, winrt (wheel arm64), psutil (wheel arm64) sono a posto [V];
  `uiautomation` senza le catture bitmap (sostituibili con pillow/mss); da verificare il
  provider `Search.CollatorDSO` su ARM64; Everything ha build ARM64.
- **Evitare sull'esecutore**: `mcp`/`fastmcp` (`cryptography`), `dxcam` (solo amd64),
  HASS.Agent (solo x64/x86).
- **Sul server** lo Spark rende possibile il punto 5 della roadmap (VLM grandi residenti
  accanto al modello vocale); la banda di memoria è comune, quindi l'arbitro resta.

---

## 6. Rischi e cose non verificate

- **Numeri dei benchmark**: quelli dei modelli 2026 (Qwen3.8, UI-Venus-2, UI-Mate, «sopra
  gli umani su OSWorld-Verified») vengono da aggregatori o sono auto-dichiarati; il sito
  ufficiale di OSWorld non era raggiungibile. La VRAM reale dei VLM 4–9B quantizzati non è
  stata misurata (la GPU era occupata).
- **Jev**: prezzo riportato in modo incoerente dalle fonti; tutti i progetti «jev-*» hanno
  una settimana di vita e potrebbero cambiare o sparire.
- **Latenze**: misurate solo in locale su un PC; la LAN reale (Wi-Fi) e un secondo PC non
  sono stati provati. Il salto HTTP con endpoint audio in cache non è stato rimisurato a
  parte.
- **Esplora risorse e Blocco note** non erano aperti: l'albero UIA di queste app non è
  stato letto.
- **ARM64**: `Search.CollatorDSO`, UIA sotto emulazione x64 contro nativa, build ARM di
  System Bridge e ODR: non verificati.
- **MCP on Windows / Agent Workspace**: in anteprima; requisiti hardware e data di
  disponibilità generale non trovati.
- **Sicurezza della conferma a voce**: una conferma detta dalla stessa voce (magari
  registrata) non è un secondo fattore; per le azioni davvero sensibili serve un canale
  diverso (presenza fisica al PC, notifica, PIN), da decidere con la decisione H della
  visione.
- **Privacy**: «programmi aperti», risultati di ricerca e titoli delle finestre rivelano
  cosa fa una persona; per questo sono letture riservate al proprietario del PC.

## 7. File

| File | Cosa |
|---|---|
| `docs/ricerche/banchi/ricerca_pc/sonde.py` | letture di stato, volume, luminosità, Windows Search, UIA, cattura in memoria |
| `docs/ricerche/banchi/ricerca_pc/sonde_uia.py` | dimensione dell'albero UIA per finestra, sessione multimediale WinRT |
| `docs/ricerche/banchi/ricerca_pc/sonda_rete.py` | esecutore HTTP minimo con token (solo lettura) e tempi del giro |
| `docs/ricerche/banchi/ricerca_pc/.venv/` | venv separato, ignorato da git |
