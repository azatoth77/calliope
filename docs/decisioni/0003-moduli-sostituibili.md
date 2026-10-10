# 0003. Moduli sostituibili e dipendenze native minime

- **Stato**: accettata (21/09/2026), sempre in vigore
- **Principi**: 2 (moduli sostituibili), 4 (dipendenze native minime) e 7 (ripiego su CPU) di
  [`CLAUDE.md`](../../CLAUDE.md)
- **Area**: [stt-tts](../aree/stt-tts.md), [setup-windows](../aree/setup-windows.md)

## Contesto

Una macchina obiettivo è un PC con Windows **su ARM**. Molte librerie della voce hanno codice
nativo e pubblicano wheel solo per x86-64: ctranslate2 (faster-whisper), piper-tts, libzim,
onnxruntime-gpu, `cryptography` dalla 46. L'ecosistema cambia in fretta, e una libreria che oggi
va bene domani può non essere più mantenuta.

## Decisione

- STT, TTS, VAD e wake word stanno dietro interfacce piccole (`transcribe(audio) → str`,
  `say(text)`…). Se una libreria non gira su una piattaforma si sostituisce **solo quel modulo**.
- Ogni dipendenza con codice nativo si verifica (wheel per `win_amd64`, `win_arm64` e manylinux
  aarch64) prima di entrare in `pyproject.toml`.
- Whisper ha sempre un ripiego su CPU, anche durante l'uso (con una frase d'attesa).

## Alternative considerate

- **Una pipeline voce già pronta** (per esempio Wyoming di Rhasspy/Home Assistant come confine tra
  i moduli): scartata per i satelliti il 02/10 (nessuna sicurezza, `wyoming-satellite` archiviato);
  resta possibile come adattatore dietro `AscoltoRemoto`.
- **Emulazione x64 su Windows ARM** (Prism) o **WSL2**: un processo ARM64 non carica moduli
  nativi x64, e NumPy emulato è ~2,5 volte più lento; WSL2 contraddice il principio 4.

## Conseguenze

Sostituzioni già fatte, ognuna senza toccare il resto della pipeline:

| Da | A | Quando | Perché |
|---|---|---|---|
| libzim | lettore ZIM in puro Python (`calliope/zim.py`) + FTS5 | 01/10 | niente libzim per ARM64; 600/600 voci identiche, apertura < 1 ms |
| faster-whisper | whisper.cpp come server sulla DGX, faster-whisper su CPU come ripiego | 02/10 | ctranslate2 senza wheel aarch64 CUDA; WER 12,4 % |
| impronta MFCC | CAM++ in ONNX | 24/09 | EER dal 10 % allo 0,4 % |
| Silero in PyTorch | Silero in ONNX | — | niente torch sui satelliti |
| Piper su CPU | Piper sulla GPU secondo la macchina | 07/10 | latenza dal testo alla voce |
| `uvicorn[standard]` | uvicorn senza extra | — | httptools e uvloop senza wheel `win_arm64` |

Le misure vere su Windows ARM restano da fare (problema aperto in `CLAUDE.md`).

## Fonti

- [`2026-10-01-biblioteca-senza-libzim.md`](../ricerche/2026-10-01-biblioteca-senza-libzim.md)
- [`2026-10-02-impacchettamento-dgx-linux.md`](../ricerche/2026-10-02-impacchettamento-dgx-linux.md) § 1.1
- [`2026-09-24-riconoscimento-parlante.md`](../ricerche/2026-09-24-riconoscimento-parlante.md)
- [`2026-10-02-satellite.md`](../ricerche/2026-10-02-satellite.md) § 2
- [setup-windows](../aree/setup-windows.md) (wheel verificati)
