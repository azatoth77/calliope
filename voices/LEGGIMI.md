# Voci Piper italiane di Calliope

*Aggiornato il 21 settembre 2026. Uso previsto: domestico e privato, non commerciale,
senza redistribuzione dei file.*

## Come si cambia voce

In `calliope.py`, nella dataclass `Config`, il campo `piper_voice` contiene il percorso del
modello. Basta cambiarlo con uno dei file elencati sotto:

```python
piper_voice: str = "voices/it_IT-leonardo-medium.onnx"
```

Piper cerca accanto al modello il file con lo stesso nome e suffisso `.onnx.json`: le due
metà di ogni voce vanno sempre tenute (e spostate) insieme. La frequenza di uscita viene
letta dal JSON, quindi voci a 16 kHz e a 22,05 kHz convivono senza altre modifiche.
Attenzione: il prompt di sistema di Calliope è scritto al femminile; con una voce maschile
il personaggio continuerà a parlare di sé al femminile finché il prompt non viene adattato.

## Dove sono i campioni

In `voices/campioni/` c'è un file WAV per ogni voce (`<nome del modello>.wav`), tutti con la
stessa frase: *"Ciao, sono Calliope. Oggi a Milano ci sono ventidue gradi e il cielo è
sereno. Vuoi che ti legga le notizie, o preferisci un po' di musica?"*. Si rigenerano con lo
script `campioni_voci.py` (sintetizza con ogni `.onnx` presente in questa cartella).
Nessuno ha ancora ascoltato i campioni: **la scelta va fatta a orecchio**.

## Tabella delle voci

Tempi misurati il 21/09/2026 sulla CPU del portatile (nessuna GPU), una sola esecuzione,
mentre sulla macchina girava un altro benchmark: sono indicativi. Il tempo comprende la
prima inferenza dopo il caricamento. La durata dell'audio cambia da voce a voce perché
ogni voce ha il suo ritmo (e UGO ha `length_scale` 1,2 nel JSON).

| File (`.onnx` + `.onnx.json`) | Genere | Qualità / frequenza | Sintesi della frase di prova | Origine | Dataset / metodo | Licenza | Note |
|---|---|---|---|---|---|---|---|
| `it_IT-paola-medium` | F | medium, 22 050 Hz | 0,18 s per 7,3 s di audio (x41) | Catalogo ufficiale: [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main/it/it_IT/paola/medium) (autrice: [paolapersico1](https://huggingface.co/paolapersico1/Piper-TTS-Italian)) | Dataset `paolapersico1/Voice-Dataset-Italian`; fine-tuning dalla voce inglese *lessac* | "vedi URL" nella scheda; il repository dell'autrice è CC0-1.0 | Voce predefinita di Calliope. |
| `it_IT-serena-medium` | F | medium, 22 050 Hz | 0,34 s per 7,9 s (x23) | Catalogo ufficiale: [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main/it/it_IT/serena/medium) (autore: [committa](https://huggingface.co/committa/it_IT-serena-medium)) | Dataset **sintetico** `committa/serena-synthetic-it-27h/28h`, generato con Qwen3-TTS-1.7B; addestrata da zero | CC-BY-4.0 | Il JSON contiene già `noise_scale` 0,6 e `noise_w` 0,4 consigliati dall'autore. |
| `it_IT-serena-high` | F | high, 22 050 Hz | 1,27 s per 7,9 s (x6) | Come sopra, cartella [serena/high](https://huggingface.co/rhasspy/piper-voices/tree/main/it/it_IT/serena/high) | Come sopra | CC-BY-4.0 | Modello da 114 MB: circa 4 volte più lento di serena-medium. Da valutare rispetto al principio "latenza prima di tutto". |
| `it_IT-riccardo-x_low` | M | x_low, 16 000 Hz | 0,19 s per 7,4 s (x39) | Catalogo ufficiale: [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main/it/it_IT/riccardo/x_low) | M-AILABS (audiolibri), addestrata da zero | "vedi URL" nella scheda (M-AILABS: licenza permissiva, non riverificata) | Unica maschile ufficiale; qualità bassa, banda audio limitata a 8 kHz. |
| `it_IT-leonardo-medium` | M (dedotto dal nome, **non dichiarato**) | medium, 22 050 Hz (vedi nota 1) | 0,35 s per 10,3 s (x29) | Community: [kirys79/piper_italiano](https://huggingface.co/kirys79/piper_italiano), cartella `Leonardo`, file originale `leonardo-epoch=2024-step=996300.onnx` / `.json` | MLS (Multilingual LibriSpeech, audiolibri LibriVox), speaker 1595; **da zero**, 2 024 epoche | **Ambigua**: CC-BY-4.0 su Hugging Face, ma la pagina del progetto su kirys.it riporta CC BY-NC-SA 4.0 (vedi nota 3) | L'autore: "probabile voce di Riccardo ma a una maggiore qualità". Prosodia da audiolibro, parlato lento. MLS è a 16 kHz: banda audio probabilmente limitata. |
| `it_IT-giorgio-medium` | M (dedotto dal nome, **non dichiarato**) | medium, 22 050 Hz (vedi nota 1) | 0,43 s per 9,4 s (x22) | Community: [kirys79/piper_italiano](https://huggingface.co/kirys79/piper_italiano), cartella `Giorgio`, file originale `giorgio-epoch=5028-step=1098436.onnx` / `.json` | MLS speaker 8181; **fine-tuning di Leonardo**, 5 028 epoche | Come Leonardo (ambigua) | L'autore lo definisce "esperimento di fine-tuning". |
| `it_IT-aurora-medium` | F | medium, 22 050 Hz | 0,53 s per 10,6 s (x20) | Community: [kirys79/piper_italiano](https://huggingface.co/kirys79/piper_italiano), cartella `Aurora`, file originale `it_IT-aurora-medium.onnx` | MLS speaker 6807; da zero, 2 093 epoche | Come Leonardo (ambigua) | L'autore: "marcato accento" e "pause enfatiche" (effetto audiolibro). |
| `it_IT-ugo-medium` | M (presumibile dal nome, **non dichiarato**) | medium, 22 050 Hz | 0,24 s per 9,5 s (x40) | Community: [Einrich99/PiperTTS-UGO-Italian](https://huggingface.co/Einrich99/PiperTTS-UGO-Italian), cartella `medium`, file originale `it_IT-ugo-medium.onnx` | **Dati non dichiarati**; fine-tuning dalla voce inglese *lessac*, 5 199 epoche | CC-BY-4.0 (su Hugging Face) | Scheda quasi vuota: non si sa di chi sia la voce né con quale consenso. Il JSON imposta `length_scale` 1,2 (parla più lentamente), `noise_scale` 0,7, `noise_w` 0,5. |
| `it_IT-miro-medium` | M (dichiarato) | medium, 22 050 Hz (vedi nota 2) | 0,44 s per 11,4 s (x26) | Community: [OpenVoiceOS/pipertts_it-IT_miro](https://huggingface.co/OpenVoiceOS/pipertts_it-IT_miro), file originale `miro_it-IT.onnx` | Dataset **sintetico** `TigreGotico/tts-train-synthetic-miro_it-IT`; fine-tuning dalla voce **portoghese** `pt-PT_miro` | **CC BY-NC-ND 4.0**: solo uso non commerciale, attribuzione a TigreGotico Lda, **niente derivati** (non usarla per addestrare altre voci) | Voce di una persona reale, di proprietà di TigreGotico Lda. Possibile accento portoghese residuo. |
| `it_IT-dii-medium` | F (dichiarato) | medium, 22 050 Hz (vedi nota 2) | 0,42 s per 11,4 s (x27) | Community: [OpenVoiceOS/pipertts_it-IT_dii](https://huggingface.co/OpenVoiceOS/pipertts_it-IT_dii), file originale `dii_it-IT.onnx` | Dataset sintetico `TigreGotico/tts-train-synthetic-dii_it-IT`; fine-tuning dalla voce portoghese `pt-PT_dii` | **CC BY-NC-ND 4.0**, come Miro | Come Miro. |

Tutte e dieci le voci si caricano e sintetizzano correttamente con `piper-tts` 1.8.0; la
cartella `voices/non-funzionanti/` non è stata necessaria.

## Note sulla qualità dichiarata

1. **Leonardo e Giorgio**: il JSON dichiara `audio.quality = "High"`, ma il modello pesa
   63 511 038 byte, esattamente come paola-medium (una voce *high* pesa circa 114 MB), e la
   ricerca li cataloga come *medium*. Il nome del file usa quindi `medium`. Il campo del
   JSON è stato lasciato com'era: non influisce sulla sintesi.
2. **Miro e Dii**: il JSON dichiara `audio.quality = "training"` (un segnaposto rimasto
   dall'addestramento) e sherpa-onnx le cataloga come *high*. Dimensione (63,5 MB) e
   frequenza (22 050 Hz) indicano l'architettura *medium*: il nome del file usa `medium`.
3. **Licenza delle voci kirys79** (Leonardo, Giorgio, Aurora): su Hugging Face la scheda
   dichiara CC-BY-4.0; la pagina del progetto
   (<https://kirys.it/projects/piper_italiano.html>) riporta invece CC BY-NC-SA 4.0, forse
   riferita ai soli contenuti del sito. Per l'uso domestico privato le due letture non
   cambiano nulla; va chiarito con l'autore **prima di qualsiasi redistribuzione o uso
   commerciale**.

## Provenienza e integrità dei file scaricati

Scaricati il 21/09/2026 da huggingface.co (solo `.onnx` e JSON; nessun checkpoint `.ckpt`,
nessun dataset). I JSON sono stati solo rinominati, senza modifiche al contenuto. Gli hash
SHA-256 dei modelli coincidono con quelli pubblicati da Hugging Face.

| File | SHA-256 (primi 12 caratteri) | Revisione del repository | Ultima modifica del repository |
|---|---|---|---|
| `it_IT-leonardo-medium.onnx` | `e693ab78e137` | `37020d3892` | 22/01/2025 |
| `it_IT-giorgio-medium.onnx` | `6bfc837a53dd` | `37020d3892` | 22/01/2025 |
| `it_IT-aurora-medium.onnx` | `15528ee12e6c` | `37020d3892` | 22/01/2025 |
| `it_IT-ugo-medium.onnx` | `8be36a89f0f1` | `3d165b2a45` | 09/11/2025 |
| `it_IT-miro-medium.onnx` | `c9a76d67e0fd` | `687b8fff3b` | 10/09/2026 |
| `it_IT-dii-medium.onnx` | `82655841707f` | `a263c1f9f5` | 10/09/2026 |

Altre voci Piper italiane cercate e **non trovate**: una ricerca sull'API di Hugging Face
(`piper it_IT`, `piper italian`, `piper italiano`, `pipertts it-IT`, `vits-piper-it`) ha
restituito solo copie o conversioni delle voci già elencate (`speaches-ai/piper-it_IT-*`,
`csukuangfj/vits-piper-it_IT-*` per sherpa-onnx, `qualcomm/PiperTTS-IT` per le NPU
Snapdragon). Non risultano altre voci italiane compatibili con Piper.

## Avvertenze

- I file dei modelli **non vanno nel repository** (vedi `CLAUDE.md`): `voices/` deve
  restare fuori dal controllo di versione, tranne eventualmente questo file.
- Le voci ricavate da audiolibri LibriVox (Leonardo, Giorgio, Aurora, riccardo) hanno una
  prosodia da lettura, meno adatta a risposte brevi da assistente.
- Miro e Dii sono voci di persone reali con licenza "niente derivati": non vanno usate come
  base per fine-tuning, clonazione o generazione di dataset.
- Dettagli, fonti e alternative: `docs/ricerche/2026-09-21-voci-e-tts.md`.
