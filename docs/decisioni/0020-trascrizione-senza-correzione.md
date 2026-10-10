# 0020. La trascrizione non si corregge alla cieca

- **Stato**: accettata (07/10/2026); al suo posto le parole incerte negli argomenti (08/10)
- **Area**: [stt-tts](../aree/stt-tts.md)

## Contesto

Whisper sbaglia soprattutto i nomi e le frasi brevi subito dopo la wake word («Che ore sono» diventa
«Chiori sono»). Dal 05/10 sulla DGX una correzione col modello della voce rileggeva le frasi incerte:
cambiava 10 frasi su 44 e costava ~1 s di mediana a ognuna.

## Decisione

Si resta senza correzione (variante **A**). Il confronto del 07/10 sulla DGX:

| Variante | WER frasi vere / di dominio | Costo | Note |
|---|---|---|---|
| A, nessuna correzione | 12,1 % / 20,6 % | — | in uso |
| B, parole incerte al modello | la frase non cambia | — | più domande di chiarimento |
| B2, «capito: …» trattenuto | 11,6 % / 19,0 % | ~0,25 s sulle incerte | sicura, ma quasi non agisce |
| C, correzione col modello | 10,8 % / 17,9 % | 0,47–0,50 s, tetto 1 s | dal vivo 13 su 21 al tetto |

Al posto della correzione cieca, dal 08/10 si guarda la probabilità di Whisper **solo per gli
argomenti che nominano qualcosa** (una città, un file, un dispositivo): il nome noto più vicino si
scrive nel registro, e se il tool non trova niente Calliope chiede «forse intendevi…?».

## Alternative considerate

- **C, correzione col modello**: migliora il banco, ma dal vivo scade al tetto, aggiunge latenza e
  fa correzioni pericolose («teore suono» → «timer suono»). La correzione cieca cambia la frase senza
  che nessuno la veda e non sa distinguere «suona simile» da «è quello che ha detto».
- **STT diversi** (05/10): Voxtral Mini 3B 25,5 %, Parakeet TDT v3 29,2 %, gemma4 e4b con l'audio
  37,8 % (risponde invece di trascrivere), Whisper su vLLM 21 %. Canary non provato (NeMo e torch).
- **Dizionario nel prompt di Whisper**: il prompt di Whisper non va allungato.

## Conseguenze

- La WER resta ~12–13 % sulle frasi vere; i nomi si recuperano dove contano, dopo il tool.
- `verbose_json` (probabilità per parola) costa 0,10 s a ogni turno.
- Da tarare sulla voce vera le soglie delle parole incerte; da decidere la correzione sullo schermo e
  il dizionario come suggerimento (mai sostituzione).

## Fonti

- [stt-tts](../aree/stt-tts.md), «Confronto della trascrizione: A / B / B2 / C (07/10)»
- [`2026-10-05-stt-confronto.md`](../ricerche/2026-10-05-stt-confronto.md)
- [`2026-10-08-parole-incerte.md`](../ricerche/2026-10-08-parole-incerte.md)
