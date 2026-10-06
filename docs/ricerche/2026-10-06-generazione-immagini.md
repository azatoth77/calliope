# Generare immagini in locale sulla DGX Spark (06/10/2026)

*Ricerca, non codice: niente installazioni né download. Richiesta di Dario del 06/10 («Calliope
deve saper generare immagini, in locale»). Fonti lette il 06/10/2026 (data di ogni fonte accanto
al link); sulla DGX solo letture di versioni e memoria, GPU non toccata (banco in corso). I numeri
segnati «misurato» vengono da altri sulla stessa macchina (GB10); quelli «stima» sono miei e vanno
rifatti nella fase 1. Decisioni aperte per Dario in § 7.*

## 0. In breve

- **Candidato principale: FLUX.2 [klein] 4B** (Black Forest Labs, gennaio 2026): Apache 2.0
  (anche uso commerciale), genera **e modifica** con lo stesso modello (fino a
  più immagini di riferimento), encoder di testo Qwen3-4B (multilingue), 4 passi, ~13 GB. Sulla
  Spark il fratello 9B fa 1024² in **4,4 s** (BF16) e **3,3 s** (NVFP4), misurato; il 4B
  dovrebbe stare sotto (stima 2–3 s). Abbastanza veloce per un tool **a voce, nella stessa
  risposta**.
- **Candidato «qualità»: Qwen-Image-2512 + Qwen-Image-Edit-2511** (Alibaba, dicembre 2025):
  Apache 2.0, 20B, il migliore per il testo dentro l'immagine; sulla Spark **61 s** a 50 passi
  (misurato), ~60 GB in BF16. Solo come lavoro in secondo piano, e solo se la memoria si libera.
- **Il migliore open in classifica, Qwen-Image-2.1** (20/09/2026, 7B, 1° tra gli open su
  Artificial Analysis), ha la *Qwen Research License*: «solo ricerca o valutazione». Va bene per
  confrontarlo nella fase 1, **non** per l'uso di tutti i giorni (decisione D1).
- **Il vincolo vero è la memoria, non la GPU**: oggi sulla DGX sono *disponibili* **14 GB** su
  119 (vLLM dell'agente 47 GB, Ollama ~28 GB, whisper.cpp 2 GB, il resto altri container). Un
  modello da 13 GB residente non ci sta con margine: o si toglie spazio a vLLM, o il modello si
  carica a richiesta (§ 3.3).
- **Integrazione proposta**: un servizio a parte `calliope-immagini` (container, 127.0.0.1,
  API **compatibile OpenAI Images** come vLLM-Omni, così si cambia motore cambiando l'URL), tool
  `immagine_genera` / `immagine_modifica`, scheda `immagine` sugli schermi dell'origine, file
  nella cartella personale solo con «salvala», pausa tra un passo e l'altro quando si parla
  (stesso arbitro di vLLM), filtri su richiesta **e** immagine, regole più strette per i minori.

## 1. Modelli open-weights (stato al 06/10/2026)

Classifica: *AA-Image-T2I v2.0* di Artificial Analysis (rifatta a settembre 2026, scala con
FLUX.2 [dev] = 1000; punteggi non confrontabili con quelli di prima).

| Modello (uscita) | Parametri | Elo AA | Testo nell'immagine | Prompt in italiano | Modifica | Licenza | Sulla Spark (1024²) |
|---|---|---|---|---|---|---|---|
| **Qwen-Image-2.1** (20/09/2026) | 7B DiT + Qwen3-VL 8B | **1036** (1° open) | ottimo (cinese e latino) | encoder VLM multilingue; italiano non dichiarato | sì, fino a 10 riferimenti, maschere, RGBA | **Qwen Research License: solo ricerca/valutazione**, commerciale a parte | 28,3 s a 20 passi, 54,1 s a 40; picco 31,6 GB; avvio ~3 min (misurato) |
| Ideogram 4 (03/06/2026) | 9,3B + Qwen3-VL 8B | 1011 | il migliore per tipografia (JSON di impaginazione) | encoder VLM | no (solo generazione) | **non commerciale**, accesso a richiesta | non misurato |
| **FLUX.2 [dev]** (25/11/2025) | 32B + Mistral Small 3.x 24B | 1000 | buono | encoder LLM multilingue | sì, multi-riferimento | **FLUX Non-Commercial** (uso personale/hobby ammesso; immagini usabili anche commercialmente; obbligo di filtri) | 45 s a 28 passi NVFP4 W4A4, 66 GB; BF16 ~2,3 min, 112 GB (misurato) |
| FLUX.2 [dev] Turbo (fal, 12/2025) | come sopra, distillato | 997 | | | | come FLUX.2 [dev] | non misurato |
| HunyuanImage 3.0 / Instruct (09/2025, 01/2026) | 80B MoE (13B attivi) | 944 / 995 | buono | sì | Instruct sì | **Tencent Community: esclusa l'Unione europea** | — (escluso) |
| Cosmos3-Nano (NVIDIA, 2026) | ~15B «omni» | (Super 995, non ci sta: 4–8 H100) | ? | ? | — | OpenMDW 1.1 (permissiva) | 960², 35 passi: 22 s, ~30 GB (misurato) |
| **Z-Image-Turbo** (26/11/2025) | 6B, encoder Qwen3-4B | 941 | buono (inglese e cinese) | encoder LLM; italiano non dichiarato | **no** (Z-Image-Edit annunciato, pesi mai usciti) | **Apache 2.0** | 9 passi: 12,1 s; compilato 7,2–8,1 s; NVFP4 5,6 s (misurato) |
| ERNIE-Image-Turbo (Baidu, 04/2026) | ? | 923 | ? | ? | ? | da verificare | 8 passi: 11,2 s; ottimizzato 8,8 s (misurato) |
| Qwen-Image (08/2025) → **Qwen-Image-2512** (31/12/2025) | 20B MMDiT + Qwen2.5-VL 7B | 889 (versione di agosto) | **ottimo**, anche paragrafi | encoder VLM multilingue | **Qwen-Image-Edit-2511** (23/12/2025), stessa licenza | **Apache 2.0** | 2512, 50 passi: 61 s (FP32! misurato) o 212 s (BF16 in un notebook, misurato); ~60 GB |
| **FLUX.2 [klein] 4B** (15/01/2026) | 4B + Qwen3-4B | (9B non in tabella; sotto [dev]) | discreto | encoder LLM multilingue | **sì, multi-riferimento** | **Apache 2.0** | 9B: 4 passi 4,4 s BF16, 3,3 s NVFP4 (misurato); 4B stima 2–3 s, ~13 GB |
| FLUX.2 [klein] 9B (15/01/2026) | 9B + Qwen3-8B | — | discreto+ | sì | sì | **non commerciale** | come sopra, 66 GB nel notebook a 50 passi (misura senza senso per un distillato) |
| Stable Diffusion 3.5 Medium/Large (10/2024) | 2,5B / 8B | sotto | debole | CLIP+T5, inglese | no | Stability Community (gratis sotto 1 M$ di ricavi) | 34 s / 82 s a 50 passi (misurato) |
| HiDream-I1 (04/2025) | 17B MoE | sotto | discreto | Llama 3.1 8B | E1 a parte | MIT | non misurato |

Note:
- **Italiano**: nessuna scheda dichiara l'italiano. I modelli recenti hanno un LLM o un VLM
  come encoder (Qwen3, Qwen2.5-VL, Mistral), quindi capiscono una descrizione in italiano; il
  **testo da scrivere dentro** l'immagine (accenti: «città», «è») è da provare. Opzione: la voce
  passa al tool la descrizione già in inglese (decide il modello, come oggi per gli argomenti dei
  tool) e il testo da scrivere tra virgolette, tale e quale. Da misurare nella fase 1.
- **Quantizzazione**: le versioni «4 bit» che girano in rete sono quasi sempre *solo pesi*: meno
  memoria ma nessun guadagno di tempo, a volte peggio (FLUX.2 [dev] 4 bit: 397 s contro 111 s di
  FLUX.1). Il guadagno vero sulla Spark viene da **NVFP4 pesi e attivazioni** (torchao W4A4):
  3× su FLUX.2 [dev]. Per i modelli piccoli BF16 basta.
- Sotto Elo 900 la differenza con i primi si vede; tra 940 e 1000 molto meno per un uso di casa.

## 2. Come farli girare sulla DGX

### 2.1 La DGX oggi (letture del 06/10)

| | Valore |
|---|---|
| GPU, driver, CUDA | GB10, driver 580.178.04, CUDA 13.0; DGX OS (build 2025-10-04), aarch64, 20 core |
| Memoria | 119 GiB totali, 104 usati, **14 disponibili** |
| Sulla GPU | vLLM (qwen3.6, agente) 47 GB; Ollama: gemma4 26B 18 GB, llama-guard3 8B 5,2 GB, gemma4 e4b 4,3 GB (tutti `Forever`); whisper.cpp 2,1 GB |
| Docker | 29.6.2; immagini di Calliope: vLLM 0.29.0 (22 GB), sandbox (Python, C#, Node) |
| Disco | 2,3 TB liberi |

Altri container non di Calliope (open-webui, database, CRM…) tengono il resto: la memoria è
condivisa con tutto.

### 2.2 Motori

| Motore | Su aarch64 + CUDA 13 | API | Pro | Contro |
|---|---|---|---|---|
| **diffusers** (PyTorch) | sì: wheel `torch 2.13.0+cu130` aarch64 dall'indice ufficiale di PyTorch (usato per Qwen-Image-2.1 sulla Spark, 30/09/2026); oppure container NGC PyTorch | nessuna: la scriviamo noi (~200 righe) | ogni modello il giorno dell'uscita; controllo dei passi (pausa), filtri, seed | PyTorch ~ diversi GB nel container |
| **vLLM-Omni** | immagini arm64 viste solo per Ascend e per Cosmos3 (`vllm/vllm-omni:cosmos3`); per GB10 da verificare | **OpenAI** `/v1/images/generations` (b64_json, `size`, `n`, `seed`, passi, negativo) | stessa famiglia di vLLM che già usiamo; Qwen-Image, Z-Image, Qwen-Image-2.1 il giorno zero | un altro container vLLM da 20 GB; niente pausa tra i passi |
| **stable-diffusion.cpp** | sì (CUDA, compila come whisper.cpp) | server con interfaccia web (dal 04/2026); API OpenAI da verificare | C++ senza Python, GGUF, supporta FLUX.2/klein, Qwen-Image (anche 2.1), Z-Image, Qwen-Image-Edit | GGUF = di solito solo pesi quantizzati: niente NVFP4 vero; meno ottimizzato per Blackwell |
| **ComfyUI** | playbook ufficiale NVIDIA per la Spark (venv + torch cu130, porta 8188, «immagine in meno di 30 s», «zero → prima immagine in ~10 minuti») | JSON dei flussi via HTTP | tutti i modelli, editor visivo | pensato per una persona davanti alla UI; dipendenze e nodi della comunità (rischio di sicurezza); niente API stabile |
| TensorRT (NVIDIA) | sì | — | FLUX.1 schnell FP4: **2,6 s** a 1024² (23 immagini/min), SDXL 7 al minuto (blog NVIDIA, 24/10/2025) | conversione per modello; non segue i modelli nuovi |

Un server **OpenAI Images-compatibile** con FLUX.2 [dev] NVFP4 esiste già come PR di
`spark-vllm-docker` (forum NVIDIA, 08/07/2026): conferma che l'interfaccia giusta è quella.

### 2.3 Memoria, banda, convivenza

- Un passo di diffusione è **calcolo**, non banda come la generazione di token: disturba meno la
  voce di un secondo LLM, ma la disturba (stessa GPU). Da misurare (§ 6, fase 1).
- **Memoria unificata**: «scaricare sulla CPU» (offload di diffusers, sleep livello 1 di vLLM)
  **non libera niente**, è la stessa memoria. Si libera solo togliendo pesi (sleep livello 2 di
  vLLM, `keep_alive` di Ollama) o riducendo la cache KV di vLLM.
- Il playbook NVIDIA avverte di errori «out of memory» anche sotto la capacità: la cache dei
  file del kernel va svuotata. Con 14 GB disponibili un picco di 13–22 GB **non** è sicuro.
- **Avvio a freddo**: Qwen-Image-2.1 ~3 minuti (33 GB di pesi); per klein 4B (~8 GB di pesi +
  ~8 GB di encoder) stima 5–15 s dal disco, meno dalla cache dei file. Il primo `torch.compile`
  costa di più (da misurare; si può tenere la cache della compilazione).

## 3. Integrazione in Calliope (proposta)

### 3.1 Il servizio

- Container `calliope-immagini` (immagine costruita da un Dockerfile nostro, versione di
  diffusers e torch fissate come il resto del lock), unità systemd utente come
  `calliope-whisper`, **solo 127.0.0.1:8005**, `--network none` a parte il download dei pesi
  (fatto una volta da `calliope motore immagini scarica`, con SHA-256 come Whisper), pesi in
  sola lettura.
- API: `POST /v1/images/generations` e `/v1/images/edits` (formato OpenAI, `b64_json`), più
  `POST /pausa`, `/riprendi`, `GET /stato` (modello caricato, memoria). Con un motore diverso
  (vLLM-Omni, sd.cpp) cambia solo `immagini_url` (principio 1).
- **Caricamento a richiesta** con `immagini_keep_alive` (es. 10 min, come Ollama) e scaricamento
  quando scade; prima di caricare controlla la memoria disponibile (`/proc/meminfo`) e, se non
  basta, rifiuta con una frase chiara invece di rischiare l'OOM (che sulla Spark può far cadere
  vLLM o Ollama).
- Pausa: diffusers chiama una funzione **a ogni passo** (`callback_on_step_end`); lì il servizio
  aspetta finché è in pausa. L'arbitro di Calliope la chiama come chiama `/pause` di vLLM
  (`PausaServer`): la voce non aspetta, l'immagine perde solo il tempo della risposta.

### 3.2 I tool

| Tool | Livelli | Cosa fa | Tempo |
|---|---|---|---|
| `immagine_genera(descrizione, testo?, formato?)` | familiare (e minori secondo il preset, § 4) | genera, manda la scheda, mette l'immagine nell'`Album` della conversazione (così «cambiala…» e «cosa c'è scritto?» funzionano) | klein: frase d'attesa («Un attimo, la disegno.», `announce`) e `risposta_finale` «È sullo schermo.» nella stessa risposta |
| `immagine_modifica(foto, richiesta)` | familiare, solo foto della conversazione (mandate o generate), mai di un'altra persona | `edits` con la foto dell'`Album` | come sopra, ~2× |

- Se il modello è lento (Qwen-Image) o va caricato: stesso schema dei documenti
  (`documenti_attesa_s`): si aspetta qualche secondo, poi «Te la preparo, ti avviso» e
  l'annuncio col segnale a immagine pronta (`Documenti.done` come modello).
- **Non un lavoro dell'agente**: non serve un ciclo a più passi né qwen3.6; il «disegnami…» è
  una richiesta sola. L'agente potrà usarlo come strumento più avanti (illustrazioni di una
  relazione), dalla porta delle estensioni.
- Prompt e descrizioni: «disegna», «fammi un'immagine», «crea un'illustrazione», «un logo»;
  i distrattori da provare: «disegnami la strada» (mappa), «fammi vedere le foto» (schermo),
  «descrivimi questa foto» (la vede già).
- Politica dei tool: classe **azione** (si fa solo se chiesta: un sito o un allegato non
  devono far partire generazioni); il testo da scrivere preso da un dato non fidato si mostra
  prima (regola di sempre).

### 3.3 Memoria: tre strade (decisione D3)

| Strada | Memoria | Prima immagine | Costo |
|---|---|---|---|
| A. klein 4B **sempre caricato** | ~13 GB fissi | ~2–3 s | togliere ~10 GB a vLLM (cache KV: meno lavori paralleli o contesto più corto) |
| B. klein 4B **a richiesta**, scaricato dopo 10 min | 0 a riposo, ~13 GB per 10 min | +5–15 s alla prima (stima) | rischio OOM se la memoria è occupata in quel momento: controllo prima |
| C. modello grande (Qwen-Image) **a richiesta** con vLLM addormentato (sleep livello 2, la modalità sviluppo è già accesa per la pausa) | ~35–60 GB per la durata | 1–3 min + risveglio dell'agente | i lavori dell'agente si fermano; solo come lavoro in secondo piano |

Proposta: **B** subito (nessun impatto a riposo), **A** se le misure dicono che si usa spesso.

### 3.4 Schermi e file

- Scheda nuova `immagine` (personale per chi l'ha chiesta): prima allo **schermo dell'origine**
  (`Mittente.schermo`, «rispondi dove ti ho chiesto»), poi agli schermi personali di chi parla;
  sugli schermi di stanza solo se chiesto («mettila sulla TV»). Sul telefono si apre a schermo
  intero (già c'è). Senza schermi: «L'ho fatta, ma non ho uno schermo dove mostrartela».
- La voce non descrive l'immagine (output per la voce): una frase.
- Su disco **solo con «salvala»** (come le foto: `immagine_archivia`), PNG nella cartella
  personale (sul portatile con `RemoteDelivery`, in Documenti\Calliope\Immagini), con i metadati
  «generata da Calliope con <modello>, <data>» (trasparenza in stile AI Act art. 50; non un
  obbligo per l'uso in casa, ma utile se l'immagine gira).
- Registro dei turni: tool, modello, passi, seed, durata, esito dei filtri; la descrizione **non**
  per gli ospiti né per i riservati, sì per i minori (visibile ai tutori come le conversazioni).

## 4. Sicurezza e minori

| Strato | Con cosa | Per chi | Costo stimato |
|---|---|---|---|
| Permessi nel codice | `ToolRegistry.call`, `minori.permesso` | ospiti **no** (D4); familiari sì; minori dal preset | 0 |
| Richiesta (testo) | **Llama Guard 3 8B** già caricato (S4 minori, S12 sesso, S10 odio, S11 autolesionismo, S1 violenza; italiano supportato) | **tutti**, non solo minori e ospiti | ~0,15–0,3 s (come oggi per i minori) |
| Persone reali | rilevatore come quello di pericolo (gemma4 e4b, output strutturato): «nomina una persona reale o chiede di modificare il volto di qualcuno?» | tutti | ~0,3 s |
| Immagine prodotta | **ShieldGemma 2** (4B, Apache 2.0: sesso esplicito, violenza, pericolo; F1 85–94 % sul banco di Google) oppure gemma4 e4b che guarda l'immagine (già caricato, 0 GB in più, precisione da misurare); Llama Guard 4 12B (immagini, italiano) è più pesante (~24 GB) | tutti; per i minori soglia più bassa | ~0,3–1 s |
| Filtri del modello | klein: dati di addestramento filtrati per CSAM (IWF), filtri NSFW nel codice di BFL (da riportare nel servizio: in diffusers non ci sono) | tutti | — |

Regole proposte (casi contrari nelle prove, nomi nel registro come da principio 10: sono vincoli
di sicurezza o di permesso):

- **Minori, preset per fascia** (campo `immagini` nel preset, ritoccabile dai tutori):
  piccoli < 7 **no**; bambini 7–10 sì, solo illustrazioni, niente modifica di foto, filtri a
  soglia stretta; ragazzi e adolescenti sì con le soglie dei minori, modifica solo di foto
  senza persone. Voce incerta = profilo più protetto. Tentativi rifiutati ripetuti (es. 3 in un
  giorno) → avviso ai tutori, come il rilevatore di pericolo. Il guardiano guasto = niente
  immagine (come oggi per le risposte).
- **Persone reali e deepfake**: niente immagini fotorealistiche di persone reali nominate, niente
  modifiche del volto o del corpo di una persona in una foto (anche della famiglia) salvo stili
  evidenti (cartone, acquerello) e solo per chi amministra (D5). In Italia la **diffusione** senza
  consenso di immagini falsificate con l'IA che causa un danno è reato (art. 612-*quater* c.p.,
  L. 132/2025, da 1 a 5 anni): Calliope non pubblica nulla, ma il file salvato può girare.
- **Mai** a schermo di stanza un'immagine chiesta da un minore senza un adulto; le schede dei
  minori aspettano il giudizio come oggi (`trattieni_schede`).
- Rifiuto con una frase fissa, senza dire quale filtro («Questa non la disegno.»); regola
  `immagine_rifiutata` con la categoria nel registro.

## 5. Raccomandazione

1. **FLUX.2 [klein] 4B** come modello di tutti i giorni: licenza pulita, generazione e modifica in
   un modello solo, abbastanza veloce per la voce, poca memoria. Riserva: **Z-Image-Turbo**
   (Apache 2.0, qualità più alta in classifica, 5,6–8 s, ma niente modifica).
2. **Qwen-Image-2512 + Edit-2511** come seconda fase, se servono testi lunghi dentro le immagini
   (inviti, cartelli, volantini) e si accetta il minuto d'attesa in secondo piano.
3. Qwen-Image-2.1 e FLUX.2 [dev]/Ideogram 4 solo nel confronto della fase 1 (licenze).
4. Motore: **diffusers in un container nostro** con API OpenAI Images (pausa tra i passi, filtri,
   controllo della memoria); vLLM-Omni o stable-diffusion.cpp come alternative dietro lo stesso
   URL.

## 6. Piano a fasi

**Fase 0 (ora, decisioni)**: D1–D6 qui sotto.

**Fase 1 — prova di fattibilità sulla DGX (1–2 giorni, a banco fermo, con il consenso per i
download)**. Misure da riportare in un rapporto:
- tempo per immagine 1024² a freddo e a caldo, picco di memoria (`/proc/meminfo`, non solo
  `nvidia-smi`), per klein 4B BF16 e NVFP4, Z-Image-Turbo, Qwen-Image-2512 (con e senza
  distillazione a pochi passi), Qwen-Image-2.1 solo per valutazione;
- 20 descrizioni in italiano contro le stesse in inglese, 10 con testo italiano da scrivere
  (accenti), giudicate da Dario;
- prima frase della voce (26B) durante una generazione: senza pausa e con la pausa tra i passi
  (la soglia di sempre: +0,15 s di mediana);
- filtri: ShieldGemma 2 contro gemma4 e4b che guarda, su un insieme etichettato pubblico (non
  generando noi contenuti illeciti); Llama Guard 3 sulle richieste in italiano (falsi rifiuti su
  50 richieste normali: «un drago che sputa fuoco», «una battaglia medievale»).

Comandi (solo proposta, da lanciare con il consenso; percorsi sotto `~/calliope-motore/immagini/`):

```bash
# pesi (Hugging Face; klein 4B e Z-Image senza accesso a richiesta, da verificare al momento)
hf download black-forest-labs/FLUX.2-klein-4B --local-dir ~/calliope-motore/immagini/modelli/flux2-klein-4b
hf download Tongyi-MAI/Z-Image-Turbo        --local-dir ~/calliope-motore/immagini/modelli/z-image-turbo
hf download Qwen/Qwen-Image-2512             --local-dir ~/calliope-motore/immagini/modelli/qwen-image-2512
hf download google/shieldgemma-2-4b-it       --local-dir ~/calliope-motore/immagini/modelli/shieldgemma-2   # licenza Gemma da accettare

# misura in un container usa-e-getta, rete spenta, pesi in sola lettura
docker build -t calliope-immagini-prova -f setup/linux/motore/immagini.Dockerfile .   # torch cu130 aarch64 + diffusers fissati
docker run --rm --gpus all --network none --ipc=host \
  -v ~/calliope-motore/immagini/modelli:/modelli:ro -v ~/calliope-misure/immagini:/uscita \
  calliope-immagini-prova python /prova/misura_immagini.py --modello flux2-klein-4b --passi 4 --n 10
```

**Fase 2 — integrazione** (dopo la fase 1, fuori dal congelamento solo su richiesta di Dario):
servizio `calliope-immagini` con systemd e `calliope motore immagini scarica|avvia|ferma|stato`,
capacità «immagini» nel registro, tool, scheda, preset dei minori, filtri, arbitro, prove a secco
(server finto) e con Ollama (scelta del tool, distrattori, rifiuti), poi prova e2e.

**Fase 3 — più avanti**: modello «qualità» in secondo piano, l'agente che illustra relazioni e
documenti, immagini nelle estensioni (dalla porta).

## 7. Decisioni per Dario

| | Domanda | Proposta |
|---|---|---|
| D1 | Qwen-Image-2.1 (il migliore, licenza «ricerca o valutazione») solo per il confronto? | sì, solo fase 1 |
| D2 | FLUX.2 [klein] 4B come modello principale, Z-Image-Turbo come riserva? | sì |
| D3 | Memoria: a richiesta (B) o sempre caricato togliendo ~10 GB a vLLM (A)? | B, poi si vede |
| D4 | Ospiti: possono generare? | no |
| D5 | Modifica di foto con persone: solo chi amministra, solo stili non fotorealistici? | sì |
| D6 | Minori: preset per fascia del § 4 (piccoli no, bambini solo illustrazioni)? | sì |
| D7 | Download (~40–80 GB in tutto per la fase 1) e quando, a banco fermo | da decidere |

## 8. Fonti (lette il 06/10/2026)

- Artificial Analysis, AA-Image-T2I v2.0, solo open weights (settembre 2026):
  https://artificialanalysis.ai/image/leaderboard/text-to-image?open-weights=true
- Qwen-Image-2.1, scheda e licenza (20/09/2026): https://huggingface.co/Qwen/Qwen-Image-2.1 ,
  https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE
- Qwen-Image, Qwen-Image-2512, Qwen-Image-Edit-2511 (Apache 2.0; 2025):
  https://github.com/QwenLM/Qwen-Image
- Qwen-Image-2.1 sulla DGX Spark, 54 s / 40 passi, 31,6 GB (forum NVIDIA, 30/09/2026):
  https://forums.developer.nvidia.com/t/qwen-image-2-1-on-dgx-spark-54-s-per-1024-image-40-steps-31-6-gb-and-a-fix-for-the-pink-vertical-line/384774
- Tempi di diffusione sulla Spark, Z-Image, klein 9B, ERNIE, Qwen-Image-2512 (forum NVIDIA,
  05–07/2026): https://forums.developer.nvidia.com/t/image-diffusion-speeds/369095
- Banco di 11 modelli sulla Spark, diffusers BF16 a 50 passi (gennaio 2026):
  https://www.haruni.net/en/blog/dgx-spark
- FLUX.2 [dev] NVFP4 sulla Spark, server OpenAI Images (forum NVIDIA, 08/07/2026):
  https://forums.developer.nvidia.com/t/flux-2-on-the-spark-3x-faster-with-real-nvfp4-compute-not-just-weight-only-pr-to-spark-vllm-docker/376106
- Blog NVIDIA sulle prestazioni della Spark (24/10/2025):
  https://developer.nvidia.com/blog/how-nvidia-dgx-sparks-performance-enables-intensive-ai-tasks
- Playbook ComfyUI per la Spark: https://github.com/NVIDIA/dgx-spark-playbooks/tree/main/nvidia/comfy-ui
- FLUX.2 [dev] (25/11/2025): https://huggingface.co/black-forest-labs/FLUX.2-dev ,
  https://bfl.ai/blog/flux-2 ; licenza non commerciale (definizioni, uscite, filtri) sul modello
  di FLUX.1 [dev]: https://huggingface.co/black-forest-labs/FLUX.1-dev/blob/main/LICENSE.md
- FLUX.2 [klein] 4B (15/01/2026): https://huggingface.co/black-forest-labs/FLUX.2-klein-4B
- Z-Image-Turbo (26/11/2025): https://huggingface.co/Tongyi-MAI/Z-Image-Turbo
- Ideogram 4 (03/06/2026): https://huggingface.co/ideogram-ai/ideogram-4-fp8
- HunyuanImage 3.0 e licenza (territorio senza UE): https://huggingface.co/tencent/HunyuanImage-3.0 ,
  https://huggingface.co/tencent/HunyuanImage-3.0/blob/main/LICENSE
- Cosmos3 Text2Image (20/07/2026): https://huggingface.co/nvidia/Cosmos3-Super-Text2Image-4Step ;
  Cosmos3-Nano sulla Spark: https://dev.classmethod.jp/en/articles/dgx-spark-cosmos3-omni-world-model-policy/
- vLLM-Omni, API immagini: https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/image_generation_api/
- stable-diffusion.cpp: https://github.com/leejet/stable-diffusion.cpp
- Llama Guard 4 (05/04/2025): https://huggingface.co/meta-llama/Llama-Guard-4-12B
- ShieldGemma 2: https://ai.google.dev/gemma/docs/shieldgemma/model_card_2 ,
  https://arxiv.org/abs/2504.01081
- Art. 612-*quater* c.p. (L. 23/09/2025 n. 132):
  https://www.agendadigitale.eu/documenti/giustizia-digitale/legge-italiana-sullai-tutti-i-profili-penali-ecco-cosa-cambia/

Da riverificare al momento della fase 1: licenza di ERNIE-Image, API OpenAI del server di
stable-diffusion.cpp, immagine arm64/CUDA di vLLM-Omni per GB10, accesso libero o a richiesta dei
pesi di klein 4B, tempo vero di klein 4B sulla Spark.
