# Personalità

*Toni di voce, modalità startrek, suoni d'ascolto, wake word diversa dal nome. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Personalità: tono di voce, modalità startrek, suoni di ascolto (dal 04/10) | testo nel prompt (`TONI`) o nei dati del turno; suoni sintetici con numpy, WAV con `wave` | `calliope/config.py` → `TONI`, `nome_tono`, `frase_tono`, `MODALITA`, `apply_modalita`; `calliope/personalita.py` (tono della casa, `personalita.json`); `Brain._tone_note`; tool `cambia_voce` (`tono`, `per_tutti`); `calliope/suoni.py` → `SuoniAscolto`, `sintetico`; `Listener.on_wake`; addestramento di un'altra parola `wakeword/parole.py` (`WW_PAROLA`); vedi [`docs/ricerche/2026-10-04-personalita-wake-word.md`](../ricerche/2026-10-04-personalita-wake-word.md) |

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

- **Personalità** (04/10, [`docs/ricerche/2026-10-04-personalita-wake-word.md`](../ricerche/2026-10-04-personalita-wake-word.md),
  prove `prova_personalita.py`, `prova_personalita_ollama.py`, misura `misura_tono.py`): sei
  toni (`normale` parola per parola come prima, `formale` col lei, `amichevole`, `ironico`,
  `essenziale`, `computer_di_bordo`). Quello della casa nel prompt (`tono`, o a voce da chi
  amministra con `cambia_voce(tono, per_tutti)`, salvato in `personalita.json`: vale il più
  recente tra lui e i file di configurazione); quello di una persona nel profilo e nei dati del
  turno come dato su chi parla («preferisce il tono formale nelle parole delle risposte…»):
  detto come messaggio a parte toglieva fino a 9 tool su 26, così resta nel rumore (misure nel
  rapporto). `wake_word` (null = il nome) e `wake_anche_nome`: tutti i posti che cercavano
  «Calliope» nel testo (wake word, uscite, stop, nome detto, registrazione, prompt e hotwords
  di Whisper, barge-in sulla propria voce, satellite, telefono, schermi) usano
  `Config.wake_names`. Per una parola comune `wake_posizione: inizio` (solo in testa o dopo una
  virgola: «il computer è lento» non sveglia, regola `wake_fuori_posizione`), e «spegni
  computer» non spegne Calliope (`exit_names`). `modalita: startrek` = «Computer», tono
  computer di bordo, suoni di inizio e fine ascolto sintetici (mai quelli di Paramount/CBS;
  un WAV proprio in `suono_inizio_ascolto`/`suono_fine_ascolto`), suonati da chi ha il
  microfono (casse locali; satellite e telefono li ricevono nel benvenuto); il nome resta
  Calliope. [Storico, superato il 05/10: il modello c'è] **Manca il modello acustico di «computer»**: senza si usa la testuale; quello
  pubblico della comunità (inglese) sulle voci italiane di Piper scatta 18 volte su 40.
  Addestramento pronto sul portatile (`WW_PAROLA=computer`, ~30 min, niente download), da
  lanciare su decisione dell'utente (comandi nel rapporto).
  Calliope. Il modello acustico di «computer» (`wakeword/modelli/computer.onnx`) c'è sul
  portatile e sulla DGX, non nel repository; senza si usa la testuale.
  **A voce, intera e subito** (05/10, `calliope/modalita.py`, prove `prova_modalita.py`,
  `prova_modalita_ollama.py`): sulla DGX «la proviamo la modalità Star Trek» cambiava solo il
  tono e a «non sento i suoni» il modello inventava «Limitazione hardware rilevata». Ora
  `cambia_voce(modalita=startrek|normale)`: solo chi amministra riconosciuto dalla voce nella
  frase (breve: sfida; scritto: «me lo chiedi a voce?»; regola `modalita_permesso`), salvata
  in `personalita.json` con il tono di prima (vale il più recente), applicata senza riavvio:
  rilevatore locale ricaricato, suoni, barge-in, prompt e hotwords di Whisper (calcolati a
  ogni frase), saluto, satelliti. Con `wake_anche_nome` (resta sì) il rilevatore ha due
  classificatori sulle stesse feature, «Computer» e «Calliope» (`Config.wake_models`), anche
  sul satellite e nel telefono: da addormentata si torna alla normale chiamandola per nome. I
  satelliti nuovi dicono `modalita: true` e i modelli che hanno nel «ciao», ricevono il
  messaggio «modalita» (gli stessi campi del benvenuto) e chiedono il classificatore che manca
  (`wake_richiesta`: solo quelli in uso, ≤ 4 MB, SHA-256 controllato, scritto accanto agli
  altri); i vecchi ignorano il tipo nuovo e la risposta dice «va riavviato». La risposta dice
  cosa è acceso davvero (wake word testuale se manca il modello). Prompt: in fondo una frase
  sola con la modalità accesa (suoni e cosa dire se non si sentono, «per tutto il resto chiama
  i tool come sempre»), **senza la parola che sveglia**: con «Computer» nel prompt o nella
  descrizione gemma4 e4b, cambiata la modalità a metà conversazione, rispondeva «Computer,
  timer impostato.» senza più tool (6/15 contro 15/15). Senza modalità il prompt è uguale a
  prima; schema di `cambia_voce` +174 caratteri. gemma4 e4b, 3 giri: 32/33 (modalità a voce
  da chi amministra 6/6, ritorno 6/6, da un familiare mai accesa 3/3, «non sento i suoni» 3/3
  senza capacità inventate, ora e timer dopo il cambio 6/6, toni 8/9: Bianca una volta
  «Cambierò il mio tono…» senza tool); `prova_personalita_ollama`
  123/126 in 3 esecuzioni (main 42/42 in una). Il pacchetto dei satelliti porta anche
  `computer.onnx`. Da provare: DGX col satellite vero e il telefono vero.

## Voci: «scarica» non cambia, frase pronta (06/10, prova e2e)

«Scarica la voce di Ugo» detto da una familiare faceva chiamare `cambia_voce` (26B) e la voce
cambiava; «Torna alla voce di Serena» diventava «Ho tornato alla voce di Serena.» (frase del
modello). Ora `cambia_voce` con «scarica/installa» nella frase (e niente «usa/metti/cambia/
torna») non cambia la voce (regola `voce_scarica_non_cambia`): alla familiare «Scaricare voci
nuove lo può fare solo chi amministra. La voce di Ugo però c'è già: vuoi che la usi?», con una
voce non installata lo dice; non finge mai un cambio con una voce che non c'è sul disco; dopo il
cambio la frase è pronta («Va bene, da adesso parlo con la voce di Serena.»). gemma4 e4b sceglie
già `installa_proponi` (6/6 prima e dopo); il 26B da riprovare.

Giro 5 della prova e2e (06/10): a «scarica la voce di Leonardo dal catalogo» il 26B chiamava
`elenca_voci` e diceva a una familiare «Ho trovato la voce di Leonardo nel catalogo. Procedo con
l'installazione.» senza installare. Ora `elenca_voci`, con «scarica»/«installa» e nessun
«usa/metti/cambia» nella frase, risponde a chi non amministra «Scaricare voci nuove lo può fare
solo chi amministra: chiediglielo.» (regola `voce_scarica_elenco`) e a chi amministra dà l'elenco
con «NON ho scaricato niente» e `installa_proponi` da chiamare; la rete sulle azioni dichiarate
prende anche «Procedo con…» (vedi voce-e-regole). Prova in `prova_modalita`.
