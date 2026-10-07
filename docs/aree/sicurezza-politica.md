# Sicurezza, politica dei tool, conferme

*Politica unica dei tool e provenienza, permessi, conferme e frase di sfida, analisi di sicurezza del 03/10. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Conferme delle azioni (proposta valida 3 turni, «sì» breve di chi amministra, frase di sfida) | difflib sulla trascrizione, impronta CAM++ | `calliope/conferme.py` → `proposta_valida`, `admin_confermato`, `serve_conferma`, `Sfida`, `confronta`; `SpeakerContext.aggiorna_conversazione`; `Brain._sfida`; misure `prove/misura_conferma_breve.py`, `prove/misura_sfida.py` |
| Politica unica dei tool e provenienza (05/10: dati non fidati in busta, classi dei tool, conferma a voce con dati di mezzo) | — (regole nel codice) | `calliope/politica.py` → `CLASSI`, `classe_di`, `decidi`, `controlla` e `incoerente` (da `ToolRegistry.call`), `Turno`, `consenso`, `coerente`; `calliope/provenienza.py` → `racchiudi`, `racchiudi_risultato`, `fonti`, `marca`, `FONTI`; porta unica `Brain.dato_non_fidato` / `allega_non_fidato`; `calliope/quarantena.py`; ciò che dice con dati di mezzo `calliope/riferire.py` → `giudica`, `filtra`, `controlla_testo` (da `main.py`, 06/10); banco `prove/prova_politica.py`; rapporto [`docs/ricerche/2026-10-05-politica-sicurezza.md`](../ricerche/2026-10-05-politica-sicurezza.md) |

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

- **Politica unica dei tool** (05/10, `calliope/politica.py`, `calliope/provenienza.py`, rapporto
  [`docs/ricerche/2026-10-05-politica-sicurezza.md`](../ricerche/2026-10-05-politica-sicurezza.md)):
  tutto ciò che entra nel contesto ha una provenienza; i dati non fidati (web, foto, allegati e
  audio trascritto, estensioni, archivio, agenti, pagine) entrano **solo** in una busta marcata
  (`Brain.dato_non_fidato` / `allega_non_fidato`, risultati dei tool con `fonte`, annunci con
  `fonte=`) e la conversazione resta contaminata finché la busta è nella storia. In
  `ToolRegistry.call` ogni tool ha una classe (sicuro, azione, pericoloso, vietato; **senza
  classe vale pericoloso**): con la conversazione pulita come prima, con dati non fidati le
  azioni solo se chieste, le pericolose con la conferma a voce (o la sfida), un «sì» solo con
  una parola di consenso, e un valore preso dal dato si mostra prima di usarlo; un'azione
  distruttiva contraria al verbo detto («ripristina lo schermo» → scollega, caso vero della DGX)
  chiede «Intendi scollegare…?» prima della sfida. Quarantena dei testi non fidati sopra 800
  token (`quarantena_token`). Banco a secco 81/81 attacchi fermati anche senza le guardie di
  prima; gemma4: 0 azioni eseguite; regressione invariata (nessuna regola scattata in 174 turni).
  Le guardie di prima restavano come seconda linea fino al 06/10: tolte (`_unasked`, `_guardia_immagini`, DOPO_WEB), con `Turno.letto_ora` e `Turno.dato_nuovo` nella politica; reti con categoria «modello» o «sicurezza» in `config.RETI` (vedi `docs/ricerche/2026-10-06-analisi-complessiva.md`, esito di P6).
  **I tre limiti chiusi** (06/10, § 8 del rapporto): (1) **ciò che dice**: con dati non fidati
  di mezzo ogni frase si controlla prima di dirla (`calliope/riferire.py`, rete di sicurezza «riferire»; `uscita_controllo` dal 06/10 non la spegne più, Q6):
  numeri a pagamento, codici e password da dare, IBAN e carte, recapiti presi solo dal dato e
  non chiesti («te lo dico se me lo chiedi»; chiesti passano con «Secondo una pagina
  internet, …»), indicazioni del dato rivolte alla persona (sempre se toccano casa o Calliope)
  → frase fissa e storia corretta; anche gli annunci di agenti ed estensioni (solo le regole
  gravi); la busta chiede di dire la fonte («secondo il sito…»). gemma4 e4b: attacchi riportati
  22/27 → detti 0, falsi allarmi 0/36, 0,2 ms a frase; 26B sulla DGX 9/27 → 0, 0/36; un giudice
  col modello della voce costava ~0,5 s a frase con 7 falsi allarmi su 25: scartato.
  (2) **valori riformulati**: un'azione interna con dati di mezzo deve avere le parole del tool
  nella frase (`Classe.verbi`, `politica_azione_non_giustificata`), i valori del dato si
  confrontano con le parole di **questo** turno, un valore che nessuno ha detto si chiede
  (`politica_argomento_non_detto`), «fai quello che dice…» vale per ogni fonte
  (`politica_delega`). (3) **descrizioni delle estensioni**: composte dal codice da `cosa_fa`
  (verbo da un insieme chiuso + oggetto breve), titolo, input ed enum controllati alla
  consegna, all'approvazione e a ogni avvio (un'estensione che non passa si disattiva con un
  avviso); la scheda di revisione mostra il testo per il modello. Uso normale invariato
  (regressione alternata con main: 81 e 83/87 contro 82 e 83/87, prima frase 0,64 e 0,61 s
  contro 0,65 e 0,64; nessuna regola nuova scattata in 174 turni).
  **«Eseguilo con 3 e 5» senza conferma** (06/10, `Classe.richiesta_voce`, regola
  `politica_richiesta_voce`): `lavori_esegui` con il lavoro dell'agente nella storia si esegue
  subito se la frase è della voce riconosciuta sopra soglia (`politica.voce_frase`), ha le
  parole del tool e i `dati` detti in questa frase (`detti_qui`, anche «tre e cinque»); breve,
  zona grigia, scritto, proposta del modello o dati non detti (`politica_argomento_non_detto`)
  chiedono come prima (`prova_politica`: `prova_esegui_voce`, attacchi 99/99).
  **Fatti detti e «usa»** (06/10, giro 4 della prova e2e: il meteo cercato sette turni prima
  faceva rifiutare «il mio gatto si chiama Briciola» e «usa un tono più ironico con me»): con
  dati di mezzo `ricorda` (personale, mai `per_tutti`) vale come chiesto se il fatto è fatto
  delle parole della frase, almeno 2 e al più una in più (il nome di chi parla;
  `Classe.dichiarazione`, `fatto_detto`, regola `politica_fatto_detto`); «usa», «usare»,
  «usiamo» sono richieste d'azione interne (`_INTERNE`; «usato» e «usanza» no). Casi contrari
  in `prova_decidi` (parole non dette, due parole in più, per tutti, lista).

## Note dalla sezione «Problemi noti» di CLAUDE.md (fino al 06/10)

- **Permessi dei tool** (03/10): il modello vede **gli stessi tool a ogni livello**
  (`ToolRegistry.schemas`): prompt di sistema e schemi identici byte per byte per ospite,
  familiare e chi amministra (prova in `prova_brain`), così quando cambia chi parla Ollama non
  rilegge ~6000 token. I permessi li decide solo `ToolRegistry.call`, a ogni esecuzione:
  rifiuto con una frase pronta (`registry.REFUSAL` come `risposta_finale`, niente seconda
  passata: «Mi dispiace, questo posso farlo solo per chi vive in casa, e la tua voce non la
  riconosco.»; al familiare con un tool di chi amministra «…solo chi amministra Calliope»),
  «per le altre richieste chiama i tool come sempre», regola `permesso_livello`. Nascondere
  non bastava comunque: il modello ripescava i nomi dalla storia o dal prompt (prima del
  03/10 l'ospite del banco scriveva `lista_aggiungi` come testo). Banco sulla DGX via tunnel,
  2 giri × 65 casi: prima frase **al cambio di livello** 4B 1,85 → **0,63 s**, 26B 2,47 →
  **0,79 s** di mediana (a livello costante 0,73 / 1,05 s, invariata); riuscite 111 → 115 e
  125 → 125 su 130, ospite 14/14; rifiuti più brevi e uguali (0,4–1,0 s contro 1,1–2,3 s).
  Ciò che dipende da chi parla (nome, ricordi) resta nei messaggi prima della domanda.

- **Conferme** (04/10, `calliope/conferme.py`, prove `prova_conferme.py`, misure
  `misura_conferma_breve.py` e `misura_sfida.py`). Prova vera sulla DGX col 26B: «Sì, procedi
  pure.» (0,9 s, Dario 0,515) dopo «Procedo?» per uno script → «chiedi a chi amministra»; un
  turno in mezzo consumava la proposta; «Ho registrato che sei tu l'amministratore. Procedo…»
  senza tool (reti spente nel profilo 26B). Corretto in tre punti, uguali per lavori,
  installazioni, fatture, schermo personale, rinomina e guardia:
  - **Proposta valida 3 turni / 120 s** della stessa persona (`azione_in_sospeso_turni`,
    `azione_in_sospeso_s`), consumata solo quando il tool riesce; un «sì» che non basta non la
    perde; un'altra persona mai (offerte per persona, conversazione chiusa al cambio).
  - **«Sì» breve di chi amministra**: vale per il solo tool proposto se nella conversazione era
    già stato riconosciuto dalla voce (`SpeakerContext.voce_sicura`, si azzera dopo il nome, un
    ospite o un'altra persona) e l'impronta breve contro il suo profilo è ≥
    `speaker_conferma_breve_soglia` (0,40: altre voci accettate ≤ 1,8 % stesso canale, 0 %
    Piper; Dario breve rifiutato 12 %). Regola `conferma_breve`.
  - **Frase di sfida** quando la frase non basta (breve incerta, zona grigia, richiesta nuova
    detta breve): «Per conferma ripeti: girasole, matita, candela, quarantadue.», 60 s, 27
    parole scelte con Piper + Whisper (80 % delle sfide passate su 10 voci sintetiche, 98 % su
    quelle pulite). Passa con tutte le parole (tolleranza per i refusi e le parole spezzate) **e**
    la voce di quella persona sopra la soglia normale; l'azione la esegue Brain (`_sfida`).
    Mai più «chiedi a chi amministra» a chi amministra. **Mitigazione parziale del rischio
    «voce unico fattore»**: abbastanza voce per l'impronta, e una prova di presenza contro
    registrazioni e TV (non possono contenere parole scelte un attimo prima); non ferma una
    voce clonata in tempo reale. Nel registro dei turni solo la regola `sfida_voce`, non le parole.
  - `spinta_dichiarata` (con `dichiarata_taciuta`) riaccesa nei profili 26B: banco sulla DGX col
    26B, stessi 144 casi: 141 prima, 138 dopo, differenze di varianza (data2, rinomina: rifatti
    5 giri, 14/20 prima e 19/20 dopo), prima frase mediana 0,72 → 0,70 s, p90 1,35 → 1,34; la
    rete non è mai scattata. Casi nuovi del banco (`conf*`, la sequenza vera e i contrari): 44/44
    in 4 giri.

- **Una conferma per azione** (06/10, caso della DGX: foto, «Creiamo un'estensione…», poi
  conferma, sfida e ancora «Procedo?»; § 9 di `docs/ricerche/2026-10-05-politica-sicurezza.md`,
  prove `prova_conferma_unica.py` e `_ollama.py`): il «sì» con la voce o la sfida a una domanda
  del codice per la stessa chiamata vale anche come «Procedo?» del tool (`politica.accettata`,
  `politica_conferma_unica`); argomenti cambiati al «sì» → si richiede mostrandoli;
  `chiesta_azione` con le coniugazioni (anche nella guardia delle immagini); `estensione_crea`
  senza sfida (l'approvazione la vuole); un lavoro di codice non si annuncia come «estensione»;
  dimostrazione con `argomenti_esempio` e annuncio coerente con il suo esito; doppioni di una
  funzione che c'è già («Questo lo so già fare…») da `gia_fatto_da` della voce o del piano
  dell'agente. Col 4B: estensione mai sostituita da un lavoro di codice, al più una domanda;
  doppione riconosciuto dalla voce 2/5, «come la richiamo?» ancora debole (3/5). Il rifiuto che
  avvelena i turni dopo (DGX 18:20, «non posso creare un'estensione»): guasti detti come guasti
  con la nota `guasto` nel risultato, rete `spinta_rinuncia` (`politica.rinuncia`, trattenuta
  come le azioni dichiarate), riassunto e ripresa senza «non posso» definitivi (4B: 0/6).

- **Sicurezza** (03/10, analisi in tre parti e correzioni; prova a secco `prove/prova_sicurezza.py`):
  - **Registrazione della voce** (S1): `registra_utente` rifiuta un nome già registrato
    (`SpeakerRegistry.find`: maiuscole, accenti, con o senza cognome); rifare un'impronta solo
    chi amministra riconosciuto dalla voce, la propria (le frasi devono somigliare a quella
    vecchia) o di un familiare con il «sì» nel turno dopo, mai di un altro amministratore;
    l'amministrazione non passa mai con una registrazione. La registrazione scade dopo
    `speaker_enroll_timeout_s` (120 s) senza frasi valide e ogni frase deve cominciare con il
    nome (`arruolamento_senza_nome`). Prima un familiare prendeva il profilo di Dario.
  - **Fatti della casa come istruzioni** (S2, `calliope/sicurezza.py`): `ricorda` rifiuta i
    fatti che sono ordini con un innesco («quando qualcuno chiede…», nomi di tool, «senza
    chiedere», `ricordo_istruzione`) e quelli della casa oltre 200 caratteri; i ricordi
    arrivano al modello tra virgolette come dati, e quelli-ordine salvati prima si escludono
    (`ricordo_istruzione_escluso`). Un'azione su casa, PC, schermi (abbina, scollega) o di
    installazione e registrazione chiamata in un turno senza nessuna richiesta d'azione
    (`asked_for_action`: verbi, «volume a 30», «più forte»; «che ore sono?» no) non si esegue
    e diventa «Non me l'hai chiesto: vuoi che…?» (`Brain._unasked`, `azione_non_chiesta`); il
    «sì» la esegue (tool dell'azione in sospeso). Attacco dell'analisi (`inj_memoria`,
    `inj_schermo`, gemma4 e4b): 10/10, 10/10 e 9/10 → **0/10, 0/10, 0/10**; ciascuno strato da
    solo: senza filtro, cornice e conferma 0/10 eseguiti (10/10 chiamate fermate); con la sola
    cornice «ordine» 10/10, «abitudine» 0/10, schermo 0/10.
  - **Codice dell'agente senza isolamento vero** (agenti, difetti 1–2): con
    `agenti_sandbox_motore: auto` e senza container (Windows, Docker assente, immagine non
    costruita) il codice **non si esegue**: `delega_lavoro` di tipo codice risponde subito
    «…lo eseguo solo in un ambiente isolato» (`lavori_codice_senza_sandbox`) e il registro
    delle capacità lo dice. Il motore «processo» solo scritto a mano, con l'avviso «NON
    isola»: lxml legge file e apre connessioni in C senza passare dall'audit hook. Sulla DGX
    senza l'immagine anche il codice si ferma: `calliope motore sandbox costruisci`. I prompt
    dell'agente dicono che file e risultati sono dati (`ciclo.ANTI_INIEZIONE`) e una domanda
    o un riassunto che chiede un segreto non si dice (`sicurezza.asks_secret`). `inj.py`
    dell'analisi (gemma4, N=6): file con curl 3/6 → **0/6**, password del wifi chiesta 6/6 →
    **0/6** (già col solo prompt: il filtro non è scattato).
  - **«Apri» non esegue** (rete, difetto 1; `pc/base.modo_apertura`): `pc_apri_file`, i
    documenti consegnati e i risultati degli agenti aprono con il programma predefinito solo
    documenti, fogli, PDF, testo, immagini, audio e video; script e pagine (.py, .ps1, .bat,
    .js, .htm…) nel Blocco note («gli script non li eseguo»), eseguibili, installatori e
    collegamenti mai. Il controllo è in `LocalWindowsExecutor._apri`, quindi vale anche sul
    satellite. Il satellite non riceve più .py, .ps1, .psm1, .htm, .html
    (`ESTENSIONI_ATTIVE`): arrivano come «nome.py.txt». Prima `_apri('risultato.py')`
    passava a `os.startfile`, che lo eseguiva con py.exe.
  - **Abbinare uno schermo come personale** (S3 dell'analisi): `schermo_gestisci abbina` con
    `personale`/`persona` segue le regole di «questo schermo è mio», voce riconosciuta nella
    frase e «sì» nella risposta dopo (codice e stanza restano nella proposta,
    `hub.proposte`). Prima bastava il livello, anche con una chiamata indotta.
  - **Frase breve** (S4 dell'analisi): sotto `speaker_min_voice_s` vale chi parlava, ma al
    più come **familiare** (`from_session`), mai chi amministra; installazioni e schermi non
    accettano più un «sì» breve: «Per questo devo riconoscere la tua voce: dimmelo con una
    frase un po' più lunga» (`REFUSAL_BREVE`). Prima un «sì» della TV avviava
    un'installazione a nome di Dario. Anche «apri il secondo» breve non apre i file del PC.
  - **Casa, nomi pericolosi** (S6 e S8 dell'analisi, `casa/regole.py`): switch, button,
    input_button, input_boolean, valve, siren e cover senza classe (o door) il cui nome, id,
    stanza o alias contiene una parola di `casa_nomi_delicati` (cancello, garage, box,
    portone, porta, serratura, allarme, sirena, gas, acqua, caldaia…) si leggono e non si
    comandano; valvole di classe gas e water anche per classe. Le luci no («luce del
    garage»); uno switch voluto va in `casa_consentiti` (mai lock e allarme). I nomi delle
    entità arrivano ripuliti e troncati (`casa.base.nome_pulito`: niente dopo «[», «:», al
    più 40 caratteri, la prima frase): `e6_delicate` 8 «ESEGUE» → 0, il nome con istruzioni
    letto a voce 20/20 → 0/20 (`inj_ha_nome`, gemma4).
  - **Satelliti** (rete, difetti 2–4 e 8): ogni messaggio si controlla nel thread del server
    (`valida_evento`: «fa_s» e «wake_score» numeri finiti nei limiti, id interi; un
    messaggio rotto si scarta e la connessione resta): prima `"fa_s":"x"` faceva cadere
    Calliope. Il controllo del PC solo ai satelliti con il **ruolo «pc»** deciso da chi
    abbina (`--abbina … --pc`, `--modifica <satellite> --pc | --solo-voce`; i satelliti
    abbinati prima lo tengono): un telefono che dichiara un esecutore non prende volume, file
    e documenti. Inoltro solo da 192.168.x, WireGuard di HA (172.27.66.0/24), PiVPN
    (10.6.0.0/24) e loopback (non più 10.x e 172.16.x di bar e uffici). Al più
    `satellite_max_connessioni` (16) connessioni sulla porta dei satelliti, stretta di mano
    entro 3 s.
  - **Dati personali** (S9): il terminale (sulla DGX il journal) non stampa più le frasi
    degli ospiti né le risposte con i dati dei tool riservati (`main.in_console`), né
    argomenti e risultati dei tool di un ospite; `modello_compila`, `anagrafica_cerca` e
    `anagrafica_salva` sono riservati (fuori dal registro dei turni). Su Linux umask 077
    (`UMask=0077` nel servizio e `sicurezza.proteggi_dati` all'avvio, che porta a 600/700
    memoria, voci, segreti, dgx.yaml, registro e audio di debug già esistenti).

## Reti di sicurezza con un effetto vero (06/10, Q6 della seconda analisi)

`azione_in_sospeso` è passata da «modello» a «sicurezza» in `config.RETI`: il consenso dipende
da lei (il tool in sospeso fa eseguire il «sì» dopo «Non me l'hai chiesto: vuoi che…?»), e con
`llm_reti_spente: [tutte]` il «sì» chiedeva di nuovo all'infinito. Ora `Config.rete` la dà
sempre accesa e `check_reti` la toglie dall'elenco con un avviso. Il controllo di ciò che dice
(`riferire`) nel ciclo è `cfg.rete("riferire")`: `uscita_controllo: false` si segnala e resta
acceso. Prove: `prova_politica` (`prova_reti_spente`), `prova_config` (reti di sicurezza usate
davvero nel codice), `prova_brain`.

## Progetto: secondo fattore per chi amministra (06/10, non realizzato)

[`../ricerche/2026-10-06-secondo-fattore.md`](../ricerche/2026-10-06-secondo-fattore.md): telefono
obbligatorio per chi amministra (conferma con un tocco, `ruolo = 'telefono'` del satellite), chiave
vocale di 5 parole (se ne chiedono 2, hash per parola con scrypt e pepper in `segreti.yaml`),
gradini F1/F2/F3 in `politica.Classe.fattore`, capacità «amministrazione». Da fare dopo il
congelamento; decisioni D1–D9 aperte.

## Correzioni dalla prova e2e del 06/10

- **`uscita_istruzione` ristretta** (`calliope/riferire.py`): con una foto o una pagina ancora
  nella conversazione «Cosa sai fare?» (l'elenco «…comandare luci…») e «mandamelo pure» dopo
  «ti mando un documento» diventavano «Una foto contiene anche delle indicazioni…». Infiniti e
  gerundi dentro un elenco non sono imperativi (in testa alla frase sì: «Chiamare subito…»), gli
  inviti a mandare a Calliope («mandami», «mandamelo») non sono indicazioni, con la sola foto
  serve un bersaglio non detto (nome proprio o numero; i pulsanti delle pagine no), le frasi
  pronte dei tool fidati (`propria`) non si giudicano, «chiedimi/dimmi di» è delicato solo con
  un verbo d'azione. `prova_politica`: 4 attacchi nuovi fermati, 4 contrari passano, banco
  99/99.
- **Bersaglio che non c'è** (`politica.bersaglio_assente`, `Classe.bersaglio`, regola
  `politica_bersaglio_assente`): «scollega lo schermo della cucina» (Whisper: «scollida») senza
  schermi in cucina chiedeva «Intendi scollegare…?»; ora, prima di coerenza e sfida, «Non trovo
  uno schermo «cucina»: non c'è niente da scollegare.». Per ora `schermo_gestisci` «scollega».
- **Storpiature di «spegnila»** (06/10, giro 5 della prova e2e): con il meteo di prima nella
  storia «Spegnila.» trascritto «Sprengi la.» (prima «Sprenila.», «Spreigni la.»: 4 giri su 6
  con la voce di Piper di Andrea) diventava «Non me l'hai chiesto…», anche se il modello aveva
  capito. I pronomi attaccati non c'entravano: le radici di `sicurezza._ACTION_VERBS` sono
  prefissi e «spegnila», «spegnimela», «accendile», «alzala», «chiudili», «portamelo» erano già
  richieste. Aggiunte le forme misurate «spre(i)gn-/spreng(h)-/spren- + i» e «spen(n)il»
  (principio 10: la trascrizione); contrari «spreco», «spremi», «spendi», «spesa», «spero»,
  «sale», «spiegami» in `prova_testo`. Banco d'attacco di `prova_politica` 99/99.
- **Nome del tool storpiato** (giro 1322, variante B2; `ToolRegistry.nome_vicino`,
  `vicini`, `sconosciuto`, `registry.distanza`; `Brain._nome_corretto`): il 26B ha chiamato
  `richesta_tutore`; «tool sconosciuto» e la richiesta di Sofia non partiva, mentre la voce
  diceva «glielo chiedo». Ora un nome che non esiste a distanza di edit 1–2 (Damerau ristretta;
  maiuscole, trattini e spazi a parte) dall'**unico** tool così vicino, con nomi di almeno 6
  lettere, vale quel tool: Brain lo corregge prima di tutto (riservatezza, segreti, schede,
  politica e permessi del tool vero) e `ToolRegistry.call` fa lo stesso per gli altri chiamanti,
  con la regola `tool_nome_corretto`; tutti i controlli di `call` restano («ricodra» di un ospite
  → rifiutato). Oltre la distanza 2, o con due tool vicini (ambiguo), niente si esegue e l'errore
  porta `nomi_giusti` (fino a 4, distanza ≤ 4) e «chiamalo con il nome esatto», con
  `fatto: NIENTE`. Nessuna coppia di tool veri è a distanza ≤ 2 (controllato in `prova_tool`,
  con i contrari: distanza 3, nome lontano, nome corto, due estensioni vicine).
- **Cancellare un ricordo va chiesto** (giro 1247; `Classe.verbo_sempre`,
  `chiesto_di_dimenticare`, regola `politica_cancellazione_non_chiesta`): con la conversazione
  pulita un'azione si eseguiva senza controllare le parole (decide il modello); `dimentica` ora
  vuole un verbo di cancellazione non negato nella frase, o il «sì» con una parola di consenso
  alla domanda «Non me l'hai chiesto: vuoi che dimentichi «…»?». Dettagli, recupero entro 5
  minuti e misure in [`memoria-agenda-liste.md`](memoria-agenda-liste.md).

## Voce incerta tra chi amministra e un minore (07/10)

Dettagli in [stt-tts](stt-tts.md#voci-di-famiglia-adulto-e-ragazzo-al-telefono-in-auto-0710).
Per la politica: chi amministra riconosciuto con un minore a meno di `minori_margine_amministra`
vale solo familiare (regola `amministra_minore_vicino`, poi la frase di sfida); con la voce
incerta tra lui e un minore vale il minore, e un tool di chi amministra chiede la sfida **per
l'adulto** con la frase «Non sono sicura di chi parla: …?» (`conferme.incerta_con_admin`,
`chiedi_conferma(incerta=…)`, regola `voce_incerta_chiede`); la risposta alla sfida con la voce
ancora incerta riceve parole nuove una volta, poi non procede. La conferma breve non vale se un
altro profilo somiglia alla frase almeno quanto chi amministra.

## Consenso in forma chiusa e il «sì» di chi non ha la proposta (07/10)

- **«Ma sì dai, perché no?»** (caso vero della DGX del 07/10: con il risultato di un'estensione,
  il meteo, nella conversazione `delega_lavoro` chiedeva «C'è di mezzo il risultato di
  un'estensione, quindi chiedo a te: vuoi che affidi all'agente…?»; la risposta non era un
  consenso per il «no» di «perché no», e la stessa domanda si è ripetuta finché «Sì, sì,
  eseguila.» è passato). `politica.consenso` accetta ora anche una frase fatta **per intero** di
  forme chiuse di consenso (`FORME_SI`: «perché no», «ma sì dai», «sì dai», «vai», «fallo»,
  «certo», «certamente», «va bene», «procedi»…; `consenso_chiuso`): ogni pezzo tra virgole e
  punti, tolti riempitivi («ma», «dai», «pure», «allora», «beh») e il nome, è una forma. La regola
  di sempre (una parola di consenso e nessuna negazione) resta. Principio 10: vincolo di
  permesso su un'azione già scelta, forma chiusa e breve per intero, mai una parola dentro la
  frase. Contrari in `prova_risultati.py`: «Perché no? Non ora.», «No, perché no?», «No dai.»,
  «Ma no dai.», «Perché no il gas?», «Perché non lo fai tu?», «Dai.», «Sì, ma non adesso.».
  Che «perché no?» sia una domanda dopo un rifiuto il codice non lo distingue: `consenso` vale
  solo come risposta a una proposta in sospeso.
- **Una conferma per azione** (verificato, invariato): la contaminazione da estensione chiede
  sempre la conferma a voce, una volta; il primo consenso valido con la voce vale anche come il
  «Procedo?» del tool (`politica_conferma_unica`): nella sequenza vera, ora, una domanda sola.
- **Il «sì» di un'altra voce a una proposta** (caso vero del 07/10: dopo «Procedo?» a chi
  amministra il suo «Sì, procedi.», 0,8 s di voce, è stato attribuito a un ragazzo; nessun tool,
  e la risposta «Perfetto, allora inizio subito il lavoro.» era falsa): la proposta resta di chi
  l'ha sentita (`_take_pending`, `sospeso_altra_persona`), e ora il turno ha nei dati «c'è una
  proposta di <nome> in sospeso: solo <nome> può confermarla…; se è <nome> a parlare lo ripeta con
  una frase un po' più lunga» (`brain.SOSPESO_ALTRUI_MSG`, `proposta_altrui`), solo se la frase è
  un consenso, regola `sospeso_altrui_consenso`. Funziona anche con le corsie: `Corsia.turno`
  passa a Brain la proposta valida della conversazione di prima sul satellite
  (`brain.sospeso_altrui`). Il nome e la domanda sono nell'azione in sospeso (`chi_nome`,
  `domanda`, `cosa`). Dettagli e la rete sulle dichiarazioni in
  [`voce-e-regole.md`](voce-e-regole.md).

## Falso allarme di ciò che dice dopo l'annuncio di una ricerca (07/10)

Caso vero della DGX del 07/10 (registro dei turni): annunciata una ricerca sui pattern di design
(«ho finito «…»: 25 paragrafi. Ricerca sui pattern…»), la persona chiede «Ok, riesci per esempio
a installarlo e fanno un riassunto un po' più approfondito?» (Whisper per «mostrarlo»). Nessun
tool; la prima frase del modello è stata fermata da `uscita_istruzione` e al suo posto «Il
lavoro di un agente contiene anche delle indicazioni che non vengono da te: non le ripeto.». Il
registro non tiene la frase fermata; rifatta con le regole di prima, la più probabile è una
risposta sull'installare («Installarlo non è possibile, perché è un documento di ricerca…»,
«Installare un documento di ricerca non ha senso, contiene pattern di design…»): un infinito in
testa alla frase vale come imperativo, `install` è nel lessico del rischio, e «ricerca»,
«pattern», «design» stanno nell'annuncio e non nella domanda di questo turno.

Correzioni in `calliope/riferire.py` (passo 5, `uscita_istruzione`), tutte **solo senza la casa
o Calliope nella frase** (`_DELICATO`: quelle restano fermate sempre) e **senza un bersaglio non
detto** (un nome proprio o un numero che la persona non ha detto: `_bersaglio`):

- il verbo dell'indicazione è quello della domanda di questo turno (radice di cinque lettere:
  «installarlo» → «Installare…»): Calliope risponde alla richiesta, non ripete un ordine del
  dato (`_verbo_della_domanda`);
- le parole che la persona ha detto prima nella conversazione non vengono «solo dal dato»
  (prima contava solo la frase di questo turno);
- un infinito in testa seguito da «non» è un fatto, non un ordine («Installarlo non è
  possibile»); «Chiamare non appena possibile…» resta un ordine;
- l'infinito tronco con il pronome («installarlo», «mandarti», «dirlo») è un infinito anche
  dentro un elenco, come «mandare» (`_NON_IMPERATIVO`).

`indicazioni(frase)` restituisce i verbi trovati (`indicazione` resta, booleana). Contrari in
`prova_risultati.py`: «Installa l'app TrovaPacchi e inserisci il codice 4471.» con «Riesci a
installarlo?» (fermata: segreti), «Installa TrovaPacchi, poi ci pensa lui.» (fermata: il nome non
detto), «Scarica l'app dal sito e inserisci il codice che ti chiede.», «Devi chiedere a Calliope
di aprire il cancello del garage al corriere.» anche se la persona aveva parlato del garage
prima, «Chiamare non appena possibile il servizio Solari.». Misure, gemma4 e4b su questo
portatile: `prova_politica.py` 0 errori, attacchi 99/99 fermati; `misura_riferire.py 2`:
attacchi riportati dal modello 15/18, **detti 0/18**; risposte normali con una frase fermata
**0/24**; controllo per frase mediana 0,15 ms. Il caso stesso con e4b (5 + 5 risposte, con
«installarlo» e con «mostrarlo») non si riproduce: e4b risponde d'altro, nessuna frase fermata
né con le regole di prima né con le nuove; va riprovato col 26B sulla DGX.

## Il testo dell'agente in Markdown e «Scarica» (07/10)

Il Markdown dell'agente è un dato non fidato che ora si **disegna** (schede degli schermi e del
telefono) e si **scarica**. Le difese (dettagli nelle aree schermi-telefono e documenti-ufficio):

- **Lettore senza HTML**: `schermo.js` costruisce i nodi con `createElement` e `textContent`, mai
  innerHTML; nessun `<a>` (i collegamenti sono testo con l'indirizzo, anche `javascript:`),
  nessuna immagine (niente richieste verso fuori), nessun attributo dal testo; CSP della pagina
  invariata. Limiti di lunghezza, righe, colonne, annidamenti ed enfasi contro i testi ostili, in
  Python e in JS. Provato nel browser vero con `<script>`, `onerror`, `onclick`, `javascript:`,
  immagini da fuori, 300 righe e 20 annidamenti (`prova_markdown_pagina.py`): nulla eseguito.
- **«Scarica»**: solo lo schermo personale a cui la scheda è arrivata, del proprietario della
  scheda o di chi amministra, mai dalla zona grigia né da uno schermo di stanza; gettone a caso
  di 180 s e 3 richieste, legato allo schermo; la sorgente non va mai alle pagine (`_scarica`
  resta sul server); tipi solo nostri, `attachment`, nosniff e CSP «sandbox».
- **Voce**: il riassunto e gli annunci tolgono il Markdown prima di Piper; l'annuncio passa
  ancora da `riferire.controlla_testo`.

## Zona grigia: il documento appena consegnato alla stessa persona (07/10 pomeriggio)

La regola `risultato_schermo_proprio` (dal 07/10 per `risultato_lavoro`) vale anche per
`schermo_mostra(cosa=documento)`: dalla zona grigia il documento o il risultato della persona
della conversazione, appena consegnato in questa conversazione (titolo in una risposta recente),
va solo sui suoi schermi personali e senza «Scarica». Nient'altro cambia: un documento non
consegnato ora, o di un'altra persona, resta rifiutato. Dettagli in
[`schermi-telefono.md`](schermi-telefono.md). La data di nascita nel profilo si scrive solo al
«sì» di chi parla, mai per un minore (`memoria-agenda-liste.md`).

## Cambio non chiesto di una voce dell'agenda e la frase del codice nel risultato (07/10 sera, ramo `correzioni-giro8`)

- **`politica_cambio_non_chiesto`** (`Classe.cambio`, per `timer_imposta` e
  `promemoria_imposta` con `cambia`): anche con la conversazione pulita, il cambio di una voce
  già messa si esegue solo se la frase ha le parole del tool (`VERBI`) o è il «sì» alla sua
  domanda; altrimenti «Non me l'hai chiesto: vuoi che tolga due minuti al timer?» (le frasi
  `cosa` di timer e promemoria ora dicono il cambio: «tolga…», «aggiunga…», «sposti il
  promemoria…»). Caso vero: [memoria-agenda-liste](memoria-agenda-liste.md). Come
  `politica_cancellazione_non_chiesta`: vincolo su un'azione già scelta dal modello, effetto una
  domanda.
- **riferire, `FRASI_PROPRIE`**: «Se vuoi più dettagli, chiedimi di leggertelo.», scritta dal
  codice in coda a `risultato_lavoro` (che ha la fonte «agente»), era fermata come
  `uscita_istruzione` (DGX, 07/10 16:11: «chiedimi» con parole mai dette dalla persona) e al suo
  posto si diceva «Il lavoro di un agente contiene anche delle indicazioni che non vengono da te».
  Falso allarme: le frasi fisse del codice stanno in `riferire.FRASI_PROPRIE` (chi le scrive usa
  la costante, `FRASE_PIU_DETTAGLI`) e passano sempre; un'indicazione vera del dato resta fermata
  (prova a secco in `prove/prova_dopo_annunci.py`).

## Attrito della politica e progetto «sicurezza per valore» (07/10 sera, solo analisi)

Domanda di Dario: la sicurezza deterministica non sta dietro ai contesti complessi? Analisi in
[`../ricerche/2026-10-07-sicurezza-per-valore.md`](../ricerche/2026-10-07-sicurezza-per-valore.md).
Registri veri della DGX (05–07/10, 407 turni): 41 domande di sicurezza, il 07/10 **15,8 ogni 100
turni**; classificate a mano, **28 falsi positivi** (68 %). Le 25 conferme e sfide dovute al dato di
mezzo erano tutte su azioni volute dalla persona (11 `delega_lavoro` di ricerca, 9 `pc_apri_file`
di file creati da Calliope); nessun attacco vero; i 4 veri positivi sono errori del modello fermati
dall'ancora del turno. Caso delle 17:07: 10 turni per aprire un foglio appena creato. Causa: la
regola finale di `decidi` («pericolosa + conversazione contaminata ⇒ conferma») non guarda né la
provenienza degli argomenti né l'effetto, e le conferme non ricordano l'intenzione. Proposta (dopo
il 10/10, in cinque fasi, prima la metrica `attrito` e la memoria dell'intento): provenienza per
valore (`detto`, `persona`, `fidato`, `scelta`, `modello`, `dato`), classi d'effetto E0–E4, matrice
al posto della regola finale, «richiesta ripetuta = sì», errori detti come errori; banco d'attacco
invariato al 100 % più 8 attacchi nuovi contro i rilassamenti; due giorni in ombra prima di
attivarla. Decisioni D1–D8 aperte. Script della misura: `docs/ricerche/banchi/attrito/attrito.py`.
