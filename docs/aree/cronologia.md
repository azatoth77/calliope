# Cronologia, primi test e prove automatiche

*Il riassunto della v0.3, il primo test reale del 21/09, i modelli scelti, le prove automatiche. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

*Questo file copre i primi giorni (fino al 06/10). Dal 06/10 in poi le tappe, una riga per giorno fino al 09/10, sono nella tabella «Tappe dello sviluppo» di [`../../CHANGELOG.md`](../../CHANGELOG.md); i dettagli nei documenti d'area.*

## Problemi noti

*Dalla divisione di CLAUDE.md (note fino al 06/10); dal 09/10 una sola sezione per area.*

- **v0.3 (22–26/09/2026)**: il codice è il package `calliope/` (26/09), con la
  configurazione in `calliope.yaml`; si avvia con `python -m calliope`.
  *[Le sotto-voci della v0.3 (impacchettamento, tool, satelliti, archivio, telefono, agenti, schermi, casa, documenti, PC, liste, biblioteca, timer, chi parla…) sono nei documenti d'area, ciascuna nella sua.]*

  - Prove e misure in `prove/` (vedi `prove/LEGGIMI.md`); test vocali 6–9 del 24/09 in
    `docs/test-vocale.md`.

- **Primo test reale superato il 21/09/2026** sull'Alienware (Python 3.14,
  faster-whisper 1.2.1, ctranslate2 4.8.2, piper-tts 1.8.0, silero-vad 6.2.2, torch 2.9.1,
  Ollama 0.34.2): conversazione completa con microfono della webcam e cuffie Bluetooth,
  VAD con i valori predefiniti senza falsi inneschi.

- Misure del primo test: STT 0,11–0,24 s (Whisper `small` su GPU), prima frase dell'LLM
  ~0,4 s (`llama3.1:8b`), Piper ~0,3 s per frase.

- **Modelli predefiniti dopo i confronti del 21/09/2026**: LLM `gemma4:e4b-it-qat` a
  temperatura 0,3 (tool calling, prima frase 0,25–0,55 s, ~4,1 GiB reali di VRAM),
  Whisper `large-v3-turbo` (~770 MiB). Non ancora riprovati insieme a voce.

- **La direzione del progetto è cambiata**: da assistente su un PC a server di casa con
  satelliti, famiglia, ospiti, musica, biblioteca offline e agenti. Leggere
  [`docs/visione.md`](../visione.md) (bozza) e le ricerche in `docs/ricerche/` prima
  di toccare l'architettura. Roadmap e principi qui sotto verranno riallineati quando
  la visione sarà confermata. *[storico: la visione è la direzione del progetto, principi e stato sono in CLAUDE.md e la roadmap in [`../roadmap.md`](../roadmap.md)]*

- **Prove automatiche** (26/09): `python -m prove` lancia le prove a secco (~4 s) e gira
  anche prima di ogni commit (`.githooks/pre-commit`); `python -m prove --ollama` aggiunge
  quelle con il modello. Dopo ogni modifica vanno fatte girare; una prova nuova si
  aggiunge in `prove/__main__.py`. Repository git dal 26/09 (autore
  2598296+azatoth77@users.noreply.github.com): un commit per ogni passo. Dal 03/10 ogni prova gira in un job
  object di Windows: un processo figlio lasciato vivo (Calliope, Edge, un server finto) fa
  fallire la prova e il runner lo chiude; l'output intero di una prova fallita resta in
  `%TEMP%\calliope-prove\`; `python -m prove prova_x.py …` lancia solo quelle.
