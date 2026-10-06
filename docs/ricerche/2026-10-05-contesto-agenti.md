# Il contesto degli agenti (05/10/2026)

*Fase 2b del progetto «Contesto di Calliope», approvata da Dario il 05/10. Ramo `contesto-2b`.
Misure sulla DGX Spark (vLLM 0.29.0, `qwen3.6-35b` = Qwen3.6-35B-A3B-NVFP4, `max_model_len`
131 072, parser del ragionamento `qwen3`) dal portatile via il tunnel di `dgx.yaml`, sandbox
«processo» sul portatile; ~18 minuti di GPU in tutto. Strumento: `prove/misura_contesto_agenti.py`;
prova a secco `prove/prova_contesto_agenti.py`.*

*Legenda: **[M]** misurato qui · **[D]** deduzione.*

## In breve

- **Prima** il contesto dell'agente aveva una finestra fissa (`agenti_num_ctx` 32 768, mentre
  vLLM serve 131 072), si teneva sotto i 60 000 caratteri accorciando i risultati vecchi a 60
  caratteri «…[omesso]» (persi), i risultati nuovi si troncavano a 6 000 caratteri (persi
  anche quelli) e un tetto unico (`agenti_max_token`) mescolava tutto: con vLLM una passata
  poteva ragionare fino a metà della finestra (16 384 token).
- **Finestra dal setup**: `agenti_num_ctx: auto` (`contesto.calcola_agenti`): con vLLM il
  minimo tra `max_model_len` e i token della cache (/metrics) divisi per
  `agenti_contesti_paralleli` (2): sulla DGX **131 072** (cache 2,1 milioni di token: qwen3.6 è
  ibrido, la cache costa poco) [M]. Ollama remoto: il suo massimo, al più 32 768. Stesso Ollama
  e stesso modello della voce: la finestra della voce, come prima. Un numero vince.
- **Token veri** a ogni passata (vLLM `usage`, Ollama `prompt_eval_count`) tarano i caratteri
  per token; il ragionamento si conta a parte (vLLM
  `completion_tokens_details.reasoning_tokens`, Ollama stimato) → `token_ragionamento` e
  `contesto` in `lavoro.json`.
- **Niente più «…[omesso]»** (`calliope/agenti/contesto_lavoro.py`): un risultato lungo va per
  intero in `.calliope/passo-N.txt` nella cartella del lavoro (fuori da elenca, risultati e
  versioni delle estensioni), nel contesto resta la parte utile (la coda dell'uscita dei
  test, l'inizio di una pagina) con il rimando; `leggi_file` lo rilegge, anche a pezzi
  (`da_carattere`). Oltre il 50 % della finestra (`agenti_soglia_file`) anche i risultati
  vecchi e il codice dei vecchi `scrivi_file` vanno nei file.
- **Diario del lavoro** oltre il 75 % (`contesto_soglia_morbida`): i passi vecchi diventano un
  riassunto strutturato (piano, fatto, decisioni, test, manca, i file della cartella, i
  risultati salvati) scritto dal modello dell'agente (una passata senza ragionamento, con lo
  schema, che non conta tra le passate) o estrattivo se il tempo non basta, il modello sbaglia
  o l'ultimo diario del modello è di due passate prima. Restano interi prompt, compito e
  ultimi 3 passi. Oltre il 90 % si accorciano anche i risultati recenti, salvo l'ultimo passo.
- **Due budget**: il contesto lo regge la finestra comprimendo; il costo resta
  `agenti_max_token`; per passata `agenti_token_passata` (16 384, al più metà della finestra,
  e mai oltre la finestra con il prompt) e `agenti_ragionamento_passata` (8 192) →
  **`thinking_token_budget` di vLLM, verificato con vLLM 0.29 e qwen3.6** [M]: con budget 100
  il ragionamento si ferma a 99 token e il modello risponde (46 primi tra 1 e 200, giusto) in
  2,1 s, contro 2 507 token e 35,5 s senza.
- **Diario con qwen3.6 vero** (§4, finestra forzata a 16 384): il modello scrive solo le voci
  nuove con i **dati** (valore e fonte) e il codice le unisce; relazione 16/21 → **19/21** fatti
  (21/21 con la finestra grande), 6–17 s per diario. Corretti: diari che non toglievano niente,
  JSON troncato, passate troncate dal budget del ragionamento, letture ripetute. Con 16 384 il
  codice non regge (riletture di codice e test): per il codice serve almeno 32 768.
- **Tetto dei token per tipo** (§5): codice 2 800–4 300 token al minuto (massimo ~4 470),
  ricerche 1 700–3 600: `agenti_token_minuto` × minuti (codice 5 000, il resto 3 000) invece di
  60 000 per tutti; avviso di chiusura vicino ai tetti, chiusura con motivo, file e test.
- **Misura** (stesso lavoro di codice lungo, 8 minuti): **prima** test nascosto **0/3**, una
  passata da 16 384 token di ragionamento (365 s) e la guardia; **dopo** test nascosto
  **3/3**, nessuna passata oltre 8 192 token di ragionamento [M].

## 1. Cosa c'è nel codice

| Pezzo | Dove |
|---|---|
| Finestra dell'agente | `contesto.calcola_agenti` (senza rete), `contesto.leggi_agenti` (/v1/models, /metrics, /api/show); `Agente.finestra` / `num_ctx` (ricalcolata ogni 10 minuti, dal thread dei lavori); ufficio con `_num_ctx_agente` |
| Tetti della passata | `Agente.passata(contesto=…, servizio=…)`: `num_predict` da `ContestoLavoro.generazione_per`, `thinking_budget` → `thinking_token_budget` (`remoto_openai.traduci_corpo`; tolto per Ollama; un server che lo rifiuta non lo riceve più) |
| Ragionamento a parte | `ciclo.ragionamento(out)`, `Lavoro.ragionamento`, `lavoro.json` (`token_ragionamento`, `contesto`) |
| Contesto del lavoro | `contesto_lavoro.ContestoLavoro` (`risultato`, `prima_della_passata`, `diario_ora`, `per_attesa`, `esporta`), `PassiSandbox` / `PassiMemoria` (ricerca), `estrattivo`, `testo_diario`, `SCHEMA_DIARIO` |
| Ciclo | `Agente.codice` e `Agente.ricerca` (al posto di `_sfoltisci`), `Agente._leggi` (leggi_file con `.calliope/` e `da_carattere`), `Agente._diario_modello` |
| Configurazione | `agenti_num_ctx: auto`, `agenti_contesti_paralleli` 2, `agenti_token_passata` 16 384, `agenti_ragionamento_passata` 8 192, `agenti_soglia_file` 0,5, `agenti_passi_intatti` 3; soglie morbida e dura in comune con la voce |
| Prove | `prove/prova_contesto_agenti.py` (a secco, ~1 s), `prove/misura_contesto_agenti.py` (manuale, DGX); server finto con `max_model_len`, /metrics, `context_length`, `reasoning_tokens` |

**Domande a metà lavoro.** Quando l'agente chiede un dato, la conversazione che resta in
memoria (fino a 120 minuti) è già compattata: i risultati lunghi nei file, salvo l'ultimo
passo. Lo stato del contesto (numerazione dei file, diario, taratura) torna alla ripresa.

**Perché il diario sta nel messaggio del compito.** Così l'alternanza dei messaggi resta
quella di sempre (sistema, utente, assistente…) e il primo messaggio dopo il taglio è una
risposta dell'assistente con le sue chiamate e i loro risultati. Il compito originale si
conserva e si ripete intero a ogni diario.

## 2. La misura

Compito: un parser `eventi.py` per tre pagine HTML «del comune» (~27 000 caratteri l'una,
gli eventi in tre formati diversi, metà dopo 12 000 caratteri di menu, script e notizie),
`unisci` senza doppioni e ordinato, almeno 10 test. Test nascosto: conteggio e campi su tutte le
pagine e una quarta pagina con i tre formati insieme. Tetto 8 minuti, 24 passate.

| | Prima (main, 5d45485) | Dopo (finestra «auto») |
|---|---|---|
| Finestra | 32 768 (fissa) | 131 072 (il massimo del modello) |
| Esito | fermato a 8 minuti | fermato a 8 minuti (l'ultima passata finita a 10) |
| **Test nascosto** | **0/3** | **3/3** |
| Passate | 12 | 13 |
| Token generati / di ragionamento | 23 817 / non contati | 39 339 / 19 533 |
| Passata più lunga | 16 384 token, 365 s (tetto = metà della finestra), poi la guardia | 11 901 token di cui 8 191 di ragionamento (il budget), 179 s |
| Picco del prompt | 22 523 (i risultati troncati a 6 000 caratteri) | 44 247 (34 %: leggi_file da 12 000, uscite dei test intere) |
| Risultati nei file / diari | — | 1 (subito, un'uscita lunga) / 0 |

Prima, l'agente ha passato 6 minuti in una passata sola a ragionare (16 384 token, il tetto di
vLLM era metà della finestra) e il lavoro è finito senza un parser che funzioni. Dopo, il budget
di ragionamento l'ha fermato due volte a 8 191 token: il modello ha chiuso il ragionamento e ha
scritto il codice, e alla fine del tempo il parser passava il test nascosto. Il lavoro resta
lungo (13 passate, ~45 token/s a 30–44k di contesto): con il tetto di 30 minuti di Calliope
sarebbe arrivato alla consegna [D]. Una misura sola per parte: la varianza del modello è alta.

Con 131 072 di finestra questo lavoro non arriva alle soglie (34 %): file e diario li prova la
prova a secco con finestre piccole (8 192 e 32 768). **Non misurato col modello vero**: il
diario scritto da qwen3.6 (resta da fare con `--finestra 16384`, ~10 minuti di GPU; non fatto
per restare sotto i 20 minuti autorizzati). Il riassunto della conversazione della voce con
qwen3.6 (fase 2, stesso tipo di richiesta) costava 4,2–4,9 s per 12 fatti su 12 [M, fase 2].

## 3. Limiti e cose da fare

- ~~Il diario dal modello: misurarlo sulla DGX~~: fatto il 05–06/10, §4.
- Con 131 072 un lavoro può arrivare a ~65k di contesto prima della soglia dei file: la
  generazione rallenta con il contesto (45 token/s a 30–44k qui). Se i lavori lunghi diventano
  lenti, `agenti_soglia_file` più bassa (0,3) o `agenti_num_ctx` 65 536 [D].
- Il budget del ragionamento vale solo con vLLM; con Ollama il tetto è `num_predict` (che
  prima non c'era: ora una passata non va oltre `agenti_token_passata`).
- ~~`agenti_max_token` (60 000)~~: tetto per tipo dal 06/10, §5.

## 4. Il diario con il modello vero (05–06/10)

*Misure sulla DGX (stesso vLLM e qwen3.6 del §2), finestra forzata a 16 384 con
`misura_contesto_agenti.py --finestra 16384` (8 192 per i messaggi, 8 192 per la passata:
diario oltre ~6 100 token), tre compiti: `eventi` (il parser del §2: pagine grandi),
`validatori` (codice fiscale, partita IVA, IBAN, numeri romani, date: molti test, test nascosto
con 5 gruppi), `relazione` (ricerca: 11 fonti finte con 21 fatti da ritrovare, 2 distrattori).
~38 minuti di GPU in tutto (12 di un primo giro interrotto, 26 qui). Una corsa per caso: la
varianza del modello è alta.*

| Compito | Finestra | Codice | Esito | Passate | Diari (dal modello) | Token | Minuti |
|---|---|---|---|---|---|---|---|
| relazione | 131 072 | 05/10 | **21/21 fatti** | 7 | 0 | 1 758 | 1,0 |
| relazione | 16 384 | prima | 16/21 | 13 | 5 (2: 8,8 e 6,0 s) | 4 187 | 1,2 |
| relazione | 16 384 | dati + unione | **19/21** | 7 | 1 (1: 27 s, 820 token) | 10 376 | 4,7 |
| eventi | 131 072 | 05/10 (§2) | **3/3** | 13 | 0 | 39 339 | ~10 |
| eventi | 16 384 | dati + unione | 0/3, fermato a 24 passate | 24 | 3 (3: 17, 12, 13 s) | 21 306 | 7,7 |
| validatori | 16 384 | 05/10 | 1/5 gruppi, fermato a 5 minuti | 6 | 0 | 21 606 | 5,0 |
| validatori | 16 384 | dati + unione | 2/5, fermato a 24 passate | 24 | 2 (0: JSON troncato) | 42 497 | 9,9 |
| validatori | 16 384 | correzioni finali | 2/5, fermato a 24 passate | 24 | 1 (estrattivo: tempo) | 37 371 | 8,8 |

**Qualità del riassunto** [M]. Con lo schema di prima («riscrivi tutto il diario») il primo
diario della relazione diceva «trovato il documento con info sulla fondazione» senza il dato,
il secondo aveva perso le scoperte del primo: l'agente ha rifatto 4 ricerche e la relazione
aveva 16/21 fatti. Ora il modello scrive solo le **voci nuove** e il codice le unisce
(`contesto_lavoro.unisci`), con il campo **«dati»** (valore e fonte: «Perdite rete 2025: 31,4 per
cento (Bilancio di sostenibilità 2025)»), e la trascrizione per il diario ha i risultati salvati
per intero (3 000 caratteri l'uno), non i riassunti da 400: 13 dati su 13 giusti nel diario,
19/21 nella relazione, nessuna ricerca rifatta (le due mancanti, il depuratore, l'agente non le
ha cercate). Nel parser i diari sono buoni: i tre formati delle pagine con esempi, i 9 eventi,
la firma delle funzioni, le decisioni (doppioni per titolo e data), l'esito dei test («17 test,
3 FAIL, 7 ERROR», con quali) e cosa manca. Dopo il primo diario l'agente ha riletto `eventi.py`
una volta (serve: il codice non è nel diario) e ha scritto i test, senza rifare le letture delle
pagine.

**Costo** [M]: 6–17 s e 420–960 token generati per diario (27 s con 3 900 token di trascrizione);
la passata non ragiona e non conta tra le passate.

**Cosa non andava, corretto** [M]:
- *Diari che non tolgono niente*: nel parser gli ultimi 3 passi (tre pagine da 12 000 caratteri)
  da soli superavano la soglia, e tre diari da 12–17 s hanno tolto 321, 422 e 533 token. Ora il
  diario si fa solo se i passi vecchi superano il 15 % dello spazio **più** la crescita del
  diario stesso (`DIARIO_CRESCITA`, 900 token, al più il 10 % dello spazio).
- *Il modello ragionava dentro il JSON*: nei validatori «piano» era un ragionamento («Aspetta,
  il risultato dice che… Verifico: RSSMRA80M01H501…») fino ai 2 000 token della passata, JSON
  troncato, diario estrattivo. Ora lo schema ha le lunghezze massime (400 caratteri il piano,
  200–250 le voci), che vLLM (xgrammar) rispetta (verificato: una stringa con `maxLength` 40
  esce di 40), e il prompt dice «sono note, non un ragionamento».
- *Passate troncate*: con 16 384 la passata ha 8 192 token e il budget del ragionamento ne
  lasciava 1 024 alla risposta: tre passate di fila da 110 s finite con `scrivi_file` vuota
  (il file era ~4 000 token). Ora il ragionamento ha al più metà della passata (con 131 072
  resta 8 192). Dopo la correzione nessuna passata troncata e i test eseguiti 3 volte entro la
  15ª passata (prima 1 volta in 24).
- *Letture ripetute*: una passata con 9 `leggi_file` degli stessi due file (~25 000 token di
  risultati, oltre la finestra). Ora la stessa lettura nella stessa passata non si rifà, e se
  l'ultimo passo da solo non lascia spazio alla passata si accorciano anche i suoi risultati,
  tranne l'ultimo (picco 24 782 → 9 755).
- *Rilettura a turno di codice e test* (8–10 passate a fine lavoro, in tutte le corse di codice
  a 16 384): alla soglia dura si accorciavano tutti i risultati recenti tranne l'ultimo passo, e
  con codice e test da ~4 500 token l'uno lo spazio ne tiene uno: l'agente rileggeva l'altro,
  all'infinito. Ora si accorciano dal più vecchio e solo finché serve, e dalla terza lettura
  uguale dello stesso file `leggi_file` aggiunge «il contenuto è qui, non rileggerlo… scrivi
  adesso la versione corretta». La nota non è ancora misurata col modello (finiti i minuti di
  GPU autorizzati).

**Ripiego estrattivo** [M]: è scattato due volte (JSON troncato; tempo quasi finito): tiene i
file scritti, l'esito dei test, le risposte della persona e cosa manca, non i «dati».

**Esito rispetto alla finestra grande** [M]: la ricerca regge (19/21 contro 21/21); il codice
no: con 8 192 token per i messaggi un lavoro con due file da 11–15 000 caratteri non tiene codice
e test insieme, e le passate se ne vanno in riletture (0/3 contro 3/3 nel parser). Non è il
diario: è la finestra. **Per il codice serve almeno 32 768** [D]; sulla DGX la finestra è
131 072 e il diario scatta solo nei lavori molto lunghi. Il caso reale di una finestra piccola è
l'agente sullo **stesso Ollama della voce** (la finestra della voce, 16 384 sul portatile): lì i
lavori di codice lunghi resteranno deboli. Da fare dopo: una modifica a pezzi (sostituire un
brano del file) invece di riscrivere il file intero, che costerebbe meno contesto e meno token.

## 5. Il tetto dei token (06/10)

`agenti_max_token` 60 000 era uno per tutti: un lavoro di codice genera ~4 000 token al minuto e
si sarebbe fermato verso il quindicesimo dei 30 minuti. Token generati al minuto, misurati [M]:

| Tipo | Corse | Token al minuto |
|---|---|---|
| codice | parser (16 384, 131 072), validatori ×3 | 2 780 · 3 900 · 4 320 · 4 300 · 4 240 |
| ricerca | relazione ×3 | 1 720 · 3 580 · 2 230 |
| massimo del modello | una passata da 8 192 token in 110 s | ~4 470 (74 token/s) |

Ora il tetto è **per tipo**: `agenti_token_minuto` × `agenti_tempo_max_min`, codice ed
estensioni 5 000 (150 000 in 30 minuti), ricerche, documenti e altro 3 000 (90 000);
`agenti_max_token` (0 = nessuno) resta come massimo comune. Per il codice conta il tempo (il
modello non arriva a 5 000 al minuto); una ricerca che genera a vuoto si ferma verso i 20
minuti. Vicino a un tetto (le ultime 2 passate, l'85 % dei token o del tempo) l'agente riceve
**una volta** l'avviso di chiudere (`AVVISO_FINE`: sistemare, rifare i test, consegnare con un
riassunto onesto): scattato nelle misure, per le passate e per il tempo. Un lavoro fermato si
chiude con il motivo detto bene («ha fatto tutte le 24 passate del lavoro»), i file, l'esito dei
test rifatti dal programma («Dei test che ha scritto ne passano 1 su 2») e un riassunto
estrattivo di cosa era stato fatto (`Limite.parziale`). La scheda dell'avanzamento usa il tetto
del tipo.
