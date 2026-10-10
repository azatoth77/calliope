# 0006. Half-duplex, con il barge-in sul nome

- **Stato**: accettata; livello A dal 26/09/2026, livello B leggero dopo; livello B completo
  rimandato
- **Principi**: 8 di [`CLAUDE.md`](../../CLAUDE.md)
- **Area**: [stt-tts](../aree/stt-tts.md)

## Contesto

Su un portatile senza cuffie il microfono sente la voce di Calliope. Se si trascrivesse mentre
parla, Calliope risponderebbe a sé stessa. Togliere l'eco in software (AEC) è possibile ma costa:
senza AEC si contano ~11 falsi barge-in al minuto; un AEC buono li porta a 0–0,7. Allo stesso tempo
la persona deve poterla interrompere.

## Decisione

- **Half-duplex**: mentre Calliope parla non si trascrive nulla.
- **Livello A** (26/09): resta accesa solo la wake word acustica; «Calliope, basta» la interrompe
  (entro 100 ms; la storia tiene solo le frasi dette davvero), ignorando i momenti in cui è lei a
  dire il proprio nome.
- **Livello B leggero**: se durante il saluto il VAD non sente la sua voce (microfono interno del
  portatile che in MME ha già la cancellazione dell'eco di Windows, oppure cuffie), qualunque frase
  di una **persona registrata** la interrompe; non la TV né un ospite.
- Sui satelliti il barge-in è locale (28–83 ms).

## Alternative considerate

- **AEC software DTLN-aec** (con allineamento GCC-PHAT): 0 falsi al minuto, 30/30 interruzioni in
  0,28 s, ~23 % di un core; rimandato (4–6 giorni di lavoro, conversione in ONNX per ARM).
- **AEC3 di WebRTC** (binding livekit): sopprime la voce durante il doppio parlato e non ha wheel
  `win_arm64`. **speexdsp**: 17–19 dB, troppo poco.
- **Satelliti con XMOS** (AEC in hardware): la soluzione giusta per le stanze, quando ci saranno.
- **Modelli voce→voce in full duplex**: guardati il 10/10, nessuno è adatto oggi. Quelli aperti e
  davvero full duplex (Moshi di Kyutai, i suoi derivati, VoiceChat di NVIDIA) parlano inglese.
  Qwen3-Omni (pesi aperti, Apache 2.0) capisce e parla l'italiano in streaming, ma a turni, non in
  full duplex. Tutti sostituirebbero l'intera catena: chi parla, la politica dei tool e la frase di
  sfida stanno tra la trascrizione e il modello. Restano una direzione da tenere d'occhio
  ([0022](0022-macchina-a-stati-del-dialogo.md)).

## Conseguenze

- Niente conversazione sovrapposta: chi parla aspetta la fine della frase o dice il nome.
- La musica nelle stanze (requisito della visione) richiederà l'AEC con il segnale di riferimento.
- Interfaccia proposta per quando servirà: `EchoCanceller.process(mic, ref)`, che sui satelliti
  XMOS non fa nulla.

## Fonti

- [`2026-09-26-cancellazione-eco.md`](../ricerche/2026-09-26-cancellazione-eco.md)
- [roadmap](../roadmap.md), storico
