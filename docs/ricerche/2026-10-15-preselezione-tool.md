# System 1: la preselezione dei tool (15/10/2026)

*Secondo caso della richiesta di Dario del 14/10: modelli «System 1» veloci per le decisioni chiuse
che pesano sulla latenza; il primo era la fine del turno
([`2026-10-14-system1-fine-turno.md`](2026-10-14-system1-fine-turno.md)). Qui: **quali tool
servono a questa frase?** Ramo `system1-preselezione`. Codice: `calliope/system1/preselezione.py`,
in ombra e spento di serie.*

## 1. Il problema

Sulla DGX la voce è gemma4 26B su Ollama, e il modello vede a ogni richiesta tutti gli schemi dei
tool: 75 in un'installazione con tutti i servizi, 85 nel registro completo delle prove, ~62 000
caratteri di JSON. Dal registro dei turni del 14/10 (giro in auto) la prima frase dei turni con
tool è 2,71 s contro 1,77 s senza, e la base senza tool è più veloce.

**Attenzione a cosa si confronta.** Il divario 2,71 / 1,77 s **non** viene dagli schemi: tutti i
turni li hanno, con o senza chiamata. Viene dalla seconda passata (la chiamata, il tool, il suo
risultato da leggere, la risposta). Togliere schemi non toglie quella passata. Quello che gli
schemi costano lo pagano **tutti** i turni, e dipende dalla cache del prefisso.

Il renderer di gemma4 in Ollama mette i tool **in testa** al prompt (misurato il 26/09,
[`2026-09-26-tool-e-agenti.md`](2026-09-26-tool-e-agenti.md) § 3.1, e di nuovo qui sotto). Con un
elenco fisso gli schemi stanno nella cache; un elenco che cambia fa rileggere **tutto** il prompt
(sistema, schemi, storia, dati del turno). Il 26/09 il recupero top-k per turno costava 0,6 s di
lettura in più con 30 turni di storia, a parità di accuratezza: per questo dal 03/10 il modello
vede lo stesso elenco a ogni livello (`tools/registry.py`).

## 2. Misure sul portatile (sonde del 15/10)

Ollama 0.40.4, gemma4:e2b-it-qat (piccolo, per non pesare sul portatile condiviso), prompt di
sistema finto e 12 scambi di storia, `num_predict` 1. Le letture sono di `prompt_eval_count` e
`prompt_eval_cached_count`.

| Richiesta (in quest'ordine) | Token del prompt | In cache | Lettura |
|---|---|---|---|
| tutti gli 85 schemi, domanda nuova (stesso prefisso) | 8195 | 8190 | 39 ms |
| stessa domanda, **6 tool** al posto di 85 | 2370 | **0** | 467 ms |
| domanda nuova, ancora 6 tool | 2367 | 2358 | 48 ms |
| di nuovo **tutti** | 8195 | **8193** | 25 ms |
| nessun tool | 1512 | 0 | 265 ms |

- **Cambiare l'insieme azzera la cache**: i tool sono in testa al prompt (confermato).
- **Tornare all'insieme di prima la ritrova**: Ollama ha tenuto il prefisso di «tutti» in un
  altro posto della cache mentre si usava quello piccolo. Due insiemi stabili possono quindi
  tenere ciascuno la sua cache, se il server ha almeno due posti. Sulla DGX è da misurare (lo
  script, scenario «tutti, ritorno»).
- **Il server lavora fuori dal modello**: a cache calda, con 85 schemi, la richiesta costava
  ~1,3 s di server oltre a lettura (25 ms) e generazione (0), contro ~0,1 s con un prompt di 2,3k
  token. Il costo cresce più che in proporzione alla lunghezza del prompt: probabilmente il
  modello del prompt e la sua conversione in token, che Ollama rifà a ogni richiesta. Questo è
  un costo che la cache **non** nasconde, e dipende dal numero di schemi. **Da verificare sulla
  DGX** (colonna «fuori dal modello» dello script): se c'è anche lì, l'insieme piccolo conviene
  anche a cache calda.
- **Riserve**: il portatile era condiviso con altri agenti, che caricavano altri modelli. Due
  giri su tre hanno ricaricato il modello a ogni richiesta (23 s): i tempi assoluti valgono poco,
  le colonne di cache sì. 8195 token con `num_ctx` 16384 sono quasi certamente un **prompt
  tagliato** (gli schemi da soli sono ~62k caratteri: 15k token o più). Sul portatile la finestra
  è divisa fra due posti, il che spiegherebbe anche la cache «di ritorno». Lo script della DGX
  avvisa quando il prompt è tagliato.

**Peso degli schemi.** Il nucleo di serie (28 tool, § 4) è il 32 % dei caratteri degli 85 schemi:
con l'insieme piccolo restano fuori due terzi degli schemi, ~10k token stimati.

## 3. Le opzioni

Versioni verificate il 15/10 dove è scritto; il resto, dalla mia conoscenza, è segnato **[c]**.

| | Classificatore a n-grammi (scelto per l'ombra) | Embedding già disponibili (qwen3-embedding 0.6B, bge-m3 su Ollama) | Modello piccolo che sceglie (FunctionGemma 270M, gemma4 e2b/e4b) | Regole sulle parole |
|---|---|---|---|---|
| Cosa fa | somiglianza tf-idf fra la frase e i **prototipi** presi dagli schemi | coseno fra vettori della frase e dei prototipi | genera il nome dei tool, o una categoria | parole chiave → tool |
| Costo per turno | **1,5–2 ms** (p90 < 3 ms sul banco), libreria standard | 75 ms (bge-m3) e 180 ms (qwen3) sulla CPU del portatile carico; 21–34 ms il 26/09 su un portatile libero | una generazione in più: +0,48 s il 26/09 per la categoria scelta da gemma4:e4b, 94 % | ~0 |
| Memoria | nessuna | un modello residente in più su Ollama (0,6–1,2 GB), da contare in `ollama_max_modelli`; il primo embedding del 06/10 scacciava il guardiano | un altro modello su Ollama | nessuna |
| Banco del 15/10 (148 frasi) | **richiamo 100 % a margine 0,10**, 46/148 a «nucleo» | richiamo 100 % solo da margine 0,10, con 31 (bge-m3) e 22 (qwen3) frasi a «nucleo» | non misurato: troppo lento per una decisione da millisecondi | — |
| Principio 10 | statistica sui testi del codice (le descrizioni), in ombra non decide niente | come a sinistra | il significato lo decide un modello | **escluso**: decide il significato con una regola |

- **FunctionGemma** (verificato il 15/10): Gemma 3 270M addestrato per le chiamate di funzione,
  su Ollama come `functiongemma` (serve Ollama ≥ 0.13.5), 32k di contesto, ~0,8 GB. La scheda
  stessa dice che non è fatto per il dialogo e che rende davvero solo **dopo un addestramento
  sul proprio insieme di tool**. Servirebbero quindi dati etichettati dei nostri 75 tool, e
  resterebbe una generazione in più per turno. È un candidato per il caso «comandi semplici
  senza il modello grande» (ricerca del 14/10, § 9), non per la preselezione.
- **gemma4 e4b sulla DGX**: oggi non è caricato accanto al 26B (la voce è il 26B, il guardiano e
  l'agente sono altri modelli). Caricarlo per scegliere i tool vuol dire più memoria e una
  passata in più a ogni turno: no.
- **Embedding**: sul banco vanno **peggio** delle parole. I prototipi sono le frasi delle
  descrizioni, scritte con le parole che si dicono («cosa c'è nella lista della spesa?»), e le
  parafrasi del banco ne ripetono molte. Il 26/09 bge-m3 era migliore, ma con due frasi d'esempio
  scritte apposta per ogni tool. Restano un'opzione (`preselezione_codifica: embedding`) da
  misurare sui turni veri con `--registro --embedding`.

## 4. Il progetto: due insiemi stabili, nel dubbio «tutti»

Non un sottoinsieme per turno: **due insiemi stabili**, «nucleo» e «tutti».

- **Il nucleo** (`preselezione.NUCLEO`, 28 tool, configurabile con `preselezione_nucleo`):
  - ora e date, calcoli;
  - timer, promemoria, appuntamenti, agenda;
  - liste, ricordi, `chi_parla`;
  - casa e meteo;
  - biblioteca, web e notizie;
  - `schermo_mostra`, `calliope_stato`;
  - la conversazione (`conversazione_nuova`, `argomento`, `conversazione_cerca`,
    `proposta_rispondi`).
- **La scelta**: per ogni tool la somiglianza più alta fra la frase (e la frase di prima con
  questa, per «E in camera?») e i suoi prototipi. I prototipi sono il nome, la prima frase
  della descrizione e le frasi d'esempio tra «…» che le descrizioni hanno già (443 prototipi
  sugli 85 schemi). Si sceglie «nucleo» solo se ogni tool fuori dal nucleo resta sotto il
  migliore del nucleo di almeno `preselezione_margine` (0,10). Altrimenti «tutti».
- **Segnali di struttura**, che non leggono il testo. Portano a «tutti»:
  - un tool fuori dal nucleo usato nella conversazione (così la conversazione resta su «tutti»
    e la cache non salta avanti e indietro);
  - un nome di tool fuori dal nucleo nei dati del turno o nella proposta aperta;
  - una foto o un file con la frase;
  - un indice che non c'è.
- **La cache**:
  - al più un cambio per conversazione, da «nucleo» a «tutti»;
  - con due posti di cache nel server, ogni insieme tiene il suo prefisso;
  - con un posto solo, ogni cambio costa una rilettura intera (~0,5–1 s col 26B e 20k token).
  Per questo la variante «per famiglie» (i tool più vicini a ogni turno) si **misura** soltanto:
  il registro ha i `top` 8, e `calliope stato` dice il richiamo che avrebbe avuto.
- **Il rischio**: togliere il tool giusto vuol dire un «non posso», un tool sbagliato vicino, o
  un tool ripescato dalla storia che il modello non vede più (26/09). Per questo:
  - il richiamo deve essere ~100 %, e nel dubbio si sceglie «tutti»;
  - un'eventuale accensione avrebbe anche una rete: con un nome sconosciuto o un «non posso»
    nella risposta si rifà la passata con tutti.

### Il banco del 15/10 (a secco)

`prove/banco_preselezione.py`: 148 frasi scritte apposta, parafrasi e non gli esempi tra «…»,
con i tool veri. Ci sono tutti gli 85 tool del registro completo, 14 frasi senza tool e 12
seguiti con la frase di prima o i tool usati. Una frase è presa se l'insieme contiene almeno uno
dei tool accettati.

| Margine | «nucleo» | Mancati |
|---|---|---|
| −0,10 | 93/148 | 13 |
| 0,00 | 70/148 | 4 (`elenca_utenti`, `pc_stato`, `modello_compila`, `archivio_scadenze`) |
| 0,05 | 59/148 | 1 («Cosa sta suonando?» → `pc_stato`) |
| **0,10** (di serie) | **46/148** | **0** |
| 0,15 | 39/148 | 0 |

- 63 frasi su 148 vogliono un tool fuori dal nucleo. Delle 85 che si risolvono col nucleo o senza
  tool, 46 vanno a «nucleo» (54 %).
- Variante «nucleo + i k più vicini», solo come misura: k = 8 prende 140/148. Perde i seguiti
  senza segnale di struttura: da sola non regge.
- **Riserva**: il banco l'ho scritto io, conoscendo le descrizioni. Il margine di serie va
  confermato sui turni veri (`--registro`, sotto) prima di qualunque accensione.

## 5. Come è fatto (15/10)

- `calliope/system1/preselezione.py`:
  - `Preselettore.decide(Richiesta) -> Scelta`, una `Decisione` con insieme, perché, schemi,
    punteggi e i tool più vicini; è la stessa interfaccia della fine del turno;
  - `CodificaParole` (n-grammi di caratteri 3–5 e parole, tf-idf, solo libreria standard) e
    `CodificaEmbedding` (`conversazioni.Embedder`);
  - `OmbraPreselezione`, `riassunto`, `testo`.
- **Ombra** (`preselezione_tool: ombra`): nel ciclo, prima di `stream_reply`, `valuta` copia la
  conversazione (0,3 ms nel thread del ciclo). Il resto avviene nel thread del decisore
  (`Sorvegliato`) mentre il modello risponde: gli schemi di oggi, l'indice (rifatto solo se
  l'elenco cambia), la scelta. Dopo la risposta `chiudi` scrive nel registro dei turni
  `preselezione`:
  - insieme e perché;
  - schemi e schemi di tutti, ms;
  - `mancati`: i tool usati fuori dall'insieme;
  - `mancati_top`: quelli della variante «per famiglie»;
  - `top`, i due punteggi e la codifica.
  Solo nomi di tool e numeri. Ciò che va al modello **non cambia**. Lento: «in_ritardo»;
  guasto: «errore», e dopo 5 guasti di fila il decisore si spegne.
- `calliope stato --turni`, sotto la scelta dei tool, mostra:
  - le risposte e la quota a «nucleo»;
  - gli schemi in meno in media e i cambi d'insieme;
  - il richiamo sui turni con tool, con i mancati per nome;
  - il richiamo della variante;
  - i ms del decisore.
  Avvisa se il richiamo scende sotto il 99 % con almeno 20 turni con tool.
- Configurazione (sezione llm): `preselezione_tool` (spenta|ombra, di serie spenta),
  `preselezione_codifica` (parole|embedding), `preselezione_embedding`, `preselezione_nucleo`,
  `preselezione_margine` (0,10).
- Prove: `prove/prova_preselezione.py` (livello 2), `prove/manuali/preselezione_dgx.py`.

## 6. Da lanciare sulla DGX

```
cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale)
$V/.venv/bin/python $V/prove/manuali/preselezione_dgx.py --registro --giorni 14
$V/.venv/bin/python $V/prove/manuali/preselezione_dgx.py --latenza --limite 24   # a Calliope inattiva
```

- `--registro`: richiamo, quota a «nucleo», mancati e cambi d'insieme sui **turni veri** degli
  ultimi giorni, per una griglia di margini. Si legge solo il registro, senza modello;
  `--embedding` aggiunge la codifica a embedding. Dà subito i numeri che l'ombra darebbe in una
  settimana.
- `--latenza`: le quattro richieste per frase («tutti, caldo», «nucleo, cambio», «nucleo,
  caldo», «tutti, ritorno») col 26B, il prompt di sistema vero e il `num_ctx` del modello già
  caricato. Per ognuna: primo pezzo, token in cache, lettura, server fuori dal modello e tool
  giusto.

**Criteri proposti per un modo «attiva»** (da scrivere solo dopo queste misure):

1. richiamo ≥ 99,5 % su almeno 300 turni con tool (registro più ombra);
2. «nucleo, caldo» almeno 150 ms più veloce di «tutti, caldo» in mediana, con lo stesso numero
   di tool giusti;
3. «tutti, ritorno» con la cache: se la cache non c'è, la conversazione deve restare su un
   insieme solo dall'inizio alla fine (si decide alla prima frase);
4. la rete: un nome sconosciuto o un «non posso» rifanno la passata con tutti.

Se il punto 2 non regge, perché sulla DGX il server non costa niente fuori dal modello e la
cache nasconde gli schemi, la preselezione resta una misura e la si chiude lì.

## 7. Misure sulla DGX (15/10 mattina): la preselezione non conviene

Lanciati i due comandi del § 6 sulla DGX (gemma4 26B, 85 schemi, Calliope inattiva).

**Registro dei turni veri** (`--registro --giorni 14`: 1421 risposte con le parole, 863 con tool):
il richiamo è **84 %** a margine 0,10 (83–84,5 % fra 0 e 0,20), lontanissimo dal 100 % del banco a
secco; «nucleo» solo nel 9 % dei turni. I mancati sono quasi tutti dell'agente e della modalità
sviluppo (`delega_lavoro` 46, `estensioni_gestisci` 20, `lavori_stato` 11, `estensione_crea` 10,
`sviluppo_prova` 8, `lavori_esegui` 7): le frasi vere sono seguiti di una conversazione lunga, che
il registro non dà al decisore come la conversazione viva. Il banco scritto conoscendo le descrizioni
era ottimista, come temuto.

**Latenza** (`--latenza --limite 24`, primo pezzo mediana / p90):

| Scenario | Primo pezzo | Prompt | Fuori dal modello |
|---|---|---|---|
| tutti, cache calda | 0,50 / 0,72 s | 18 862 | 148 ms |
| nucleo subito dopo il cambio | 0,90 / 1,08 s | 7 444 | 500 ms |
| nucleo, cache calda | 0,46 / 0,65 s | 7 444 | 36 ms |
| ritorno a tutti | 1,04 / 1,27 s | 18 862 | 442 ms |

A cache calda il nucleo guadagna **~40 ms**; ogni cambio d'insieme costa **+0,4–0,5 s** (all'andata e
al ritorno: la cache di «tutti» si ritrova solo in parte, 18 350 su 18 860). Con 111 cambi su 1421
turni il saldo è negativo. Il costo «fuori dal modello» degli schemi visto sul portatile (~1,3 s) sulla
DGX è 148 ms a cache calda.

**Conclusione**: nessuno dei criteri del § 6 è vicino (richiamo, ≥ 150 ms); la preselezione resta solo
una misura in ombra e non va accesa. *[16/10, issue #25: l'ombra è tolta dal ciclo con i campi
`preselezione_*` e la sezione di `calliope stato`; resta il decisore, rimisurabile con
`prove/manuali/preselezione_dgx.py --registro`.]* Il divario dei turni con tool (2,71 contro 1,77 s del 14/10) è la
**seconda passata** dopo il tool: è lì che va cercato il prossimo caso System 1.

## Fonti

- FunctionGemma su Ollama: https://registry.ollama.ai/library/functiongemma (Gemma 3 270M per le
  chiamate di funzione, Ollama ≥ 0.13.5, «not intended for use as a direct dialogue model»,
  da specializzare); LM Studio: https://lmstudio.ai/models/google/functiongemma-270m (32k di
  contesto, ~786 MB); GGUF: https://huggingface.co/unsloth/functiongemma-270m-it-GGUF.
- Posti di cache e `OLLAMA_NUM_PARALLEL` (fonti secondarie, da confermare con lo script):
  https://www.ssdnodes.com/learn/ollama-num-parallel-and-max-queue,
  https://leanpub.com/read/ollama/prompt-caching.
- Le misure del 26/09 sui tool e sul recupero: [`2026-09-26-tool-e-agenti.md`](2026-09-26-tool-e-agenti.md).
