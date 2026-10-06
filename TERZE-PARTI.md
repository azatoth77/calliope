# Componenti di terzi e attribuzioni

Calliope è distribuita con licenza AGPL-3.0-or-later (vedi [`LICENSE`](LICENSE)). Questo file
elenca ciò che nel repository viene da altri, le dipendenze con le loro licenze e i modelli e
i contenuti che Calliope usa ma **non** contiene. Stato al 06/10/2026; le licenze delle
dipendenze sono quelle dichiarate nei metadati dei pacchetti alla versione di `uv.lock`.

## 1. Testo o dati di terzi dentro il repository

| Dove | Che cosa | Origine e licenza | Obbligo |
|---|---|---|---|
| `calliope/casa/errori.py` (`ERRORI_HA`) | 29 modelli delle risposte d'errore italiane di Home Assistant, copiati tali e quali | repository `home-assistant/intents`, `responses/it/_common.yaml`, pacchetto `home-assistant-intents` 2026.9.30 (licenza dichiarata nel pacchetto: Apache-2.0) | attribuzione (questa riga); compatibile con l'AGPL |
| `calliope/guardiano.py` | i modelli di prompt dei classificatori di sicurezza (elenco delle categorie di Llama Guard 3, formato delle domande di ShieldGemma e Granite Guardian), riscritti come stringhe per chiamare quei modelli | schede dei modelli di Meta (Llama 3.1 Community License), Google (Gemma Terms of Use), IBM (Apache-2.0) | sono istruzioni d'uso dei modelli, non i modelli; i modelli si scaricano a parte con la loro licenza |
| `setup/linux/motore/gemma4_template.py` | aggiunge una riga al modello di chat di Gemma 4 **letto dal checkpoint** al momento dell'installazione | il modello di chat resta nel checkpoint (licenza del modello Gemma 4) | nessuno nel repository: lo script contiene solo la riga aggiunta |
| `calliope/wakeword.py`, `wakeword/` | codice proprio che usa i modelli di feature di openWakeWord v0.5.1 (melspettrogramma ed embedding) | openWakeWord, Apache-2.0; i modelli si scaricano con `wakeword/scarica_modelli.py` | attribuzione |
| `calliope/schermi/pagina/telefono/icona*` | icone della web app | proprie del progetto | — |
| `docs/ricerche/*.md` | brevi citazioni e numeri da documentazione, pagine e schede di progetti terzi, con il link alla fonte | citazione | — |
| `prove/*` | frasi d'esempio, dati finti (persone, codici fiscali e IBAN di prova come `IT60X0542811101000000123456`), modelli di documento | propri del progetto | — |

## 2. Esclusi dal repository (non vanno mai aggiunti)

| Che cosa | Perché |
|---|---|
| Modello acustico della wake word (`wakeword/modelli/calliope.onnx`) e dati di addestramento (`wakeword/dati/`) | il classificatore è addestrato con feature derivate da **ACAV100M** (CC BY-NC-SA 4.0): uso non commerciale e condivisione con la stessa licenza, incompatibile con la ridistribuzione insieme a codice AGPL senza restrizioni. Chi lo vuole lo addestra da sé. |
| Schema XSD della FatturaPA (`fatturapa/`) | pubblicato dall'Agenzia delle Entrate senza una licenza dichiarata: si scarica con `python -m calliope.ufficio --scarica-xsd` |
| Voci di Piper (`voices/*.onnx`), modelli (`models/`), Whisper, CAM++, Silero, onnxruntime-web | si scaricano dal catalogo (`calliope/installa/catalogo.py`) o a mano, ognuno con la sua licenza (sezione 4) |
| File ZIM della biblioteca e indici (`biblioteca/`) | contenuti dei progetti Wikimedia via Kiwix (sezione 4) |

## 3. Dipendenze Python (da `uv.lock`) e compatibilità con l'AGPL-3.0

Tutte le dipendenze sono installate dall'utente con pip o uv: il repository non ne contiene il
codice. Nessuna ha una licenza incompatibile con l'AGPL-3.0 per questo uso.

| Licenza | Pacchetti | Compatibilità |
|---|---|---|
| MIT, MIT-0, MIT-CMU | annotated-types, anyio, cffi, comtypes, ctranslate2, et-xmlfile, faster-whisper, filelock, fonttools, h11, jiter, onnxruntime, openpyxl, pathvalidate, pillow, pycaw, pydantic, pydantic-core, python-docx, python-pptx, pyyaml, screen-brightness-control, setuptools, silero-vad, sniffio, sounddevice, truststore, typing-inspection, unicode-rbnf, winrt-runtime, winrt-windows-media-control, wmi | permissive: compatibili |
| BSD (2 e 3 clausole) | av, click, colorama, fsspec, httpcore, httpcore2, httpx, httpx2, idna, jinja2, lxml, markupsafe, mpmath, networkx, numpy (con parti 0BSD, MIT, Zlib, CC0), protobuf, psutil, pycparser, pypdf, pypdfium2 (BSD-3 / Apache-2.0, con PDFium), starlette, sympy, torch, uvicorn, websockets, xlsxwriter, zstandard | permissive: compatibili |
| Apache-2.0 | flatbuffers, hassil, hf-xet, home-assistant-intents, huggingface-hub, openai, packaging (o BSD-2), tokenizers | compatibile con la GPLv3 e quindi con l'AGPLv3 (non con la GPLv2) |
| PSF | defusedxml, pywin32, pypiwin32, typing-extensions | permissiva: compatibile |
| MPL-2.0 | certifi, tqdm (MPL-2.0 e MIT) | compatibile (MPL-2.0 consente la combinazione con le licenze GNU) |
| LGPL-2.1-only | docxtpl (extra `modelli`) | compatibile: libreria usata come dipendenza, non modificata |
| LGPL-3.0-only | fpdf2 (extra `documenti`) | compatibile |
| GPL-3.0-or-later | piper-tts | compatibile: la GPLv3 e l'AGPLv3 si possono combinare (sezione 13 di entrambe); è una delle ragioni della scelta di una licenza GNU v3 |
| Proprietaria NVIDIA | nvidia-cublas-cu12, nvidia-cuda-nvrtc-cu12, nvidia-cudnn-cu12 (extra `gpu`, solo Windows x86-64) | librerie di sistema per la GPU, facoltative, installate dall'utente e mai distribuite con Calliope: non entrano nel lavoro coperto dall'AGPL. Chi ridistribuisse un pacchetto con queste DLL dentro dovrebbe rispettare la licenza NVIDIA. |

Strumenti esterni usati come programmi separati (non librerie): Ollama (MIT), vLLM (Apache-2.0),
whisper.cpp (MIT), SearXNG (AGPL-3.0, in un container suo), OpenSSH, Docker, openssl, uv
(MIT/Apache-2.0).

## 4. Modelli e contenuti usati da Calliope (scaricati, non nel repository)

| Che cosa | Licenza (da verificare alla versione scaricata) | Note |
|---|---|---|
| Whisper large-v3-turbo (OpenAI) | MIT | via faster-whisper o whisper.cpp |
| Silero VAD | MIT | |
| CAM++ (3D-Speaker, Alibaba) | Apache-2.0 | |
| Feature di openWakeWord v0.5.1 | Apache-2.0 | i modelli di wake word preaddestrati di openWakeWord sono CC BY-NC-SA 4.0: non usati |
| Gemma 4 (voce) | termini di Google per i modelli Gemma (verificare la licenza della versione usata) | |
| Qwen3.6 (agente) | Apache-2.0 (verificare alla versione usata) | |
| Llama Guard 3 8B (guardiano dei minori) | Llama 3.1 Community License (attribuzione «Built with Llama», condizioni d'uso di Meta) | facoltativo |
| qwen3-embedding:0.6b | Apache-2.0 | |
| Voci di Piper | serena: CC BY 4.0 (attribuzione); paola: CC0-1.0 nel repository dell'autrice; riccardo: dati M-AILABS (permissiva); le voci della comunità hanno licenze diverse, alcune non commerciali (miro, dii: CC BY-NC-ND 4.0): vedi [`voices/LEGGIMI.md`](voices/LEGGIMI.md) | |
| Wikipedia, Vikidia, Wikizionario, Wikiquote (file ZIM di Kiwix) | CC BY-SA 4.0 (testi dei progetti Wikimedia; Vikidia CC BY-SA) | Calliope cita la fonte a voce quando usa un passaggio |
| onnxruntime-web 1.30 (web app del telefono) | MIT | scaricato con `calliope stato --installa telefono` |
