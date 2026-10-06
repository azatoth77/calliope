# Confronto degli LLM per la voce di Calliope (Gemma 4 contro i candidati precedenti)

*Prove svolte il 21 settembre 2026 su RTX 5070 Laptop 8 GB, Ollama 0.34.2, per la decisione D di docs/visione.md.*

## In breve

- **Gemma 4 mantiene la promessa sui tool**: `gemma4:e2b-it-qat` e `gemma4:e4b-it-qat` fanno
  **4/4 sulla sonda, tre volte su tre, con risposte identiche**, e il thinking resta spento
  (prime frasi sempre sotto 1 s).
- **Raccomandazione per oggi (8 GB): `gemma4:e4b-it-qat` a temperatura 0.3.** È l'unico
  modello con i tool che rispetta bene il prompt, non inventa fatti e sta comodo accanto a
  Whisper. Ha però due difetti da tenere d'occhio: **parole malformate** ("museI", "meteos",
  "oppression") e il **femminile rivolto all'utente** ("quando ti senti pronta").
- `gemma4:e2b-it-qat` è il più veloce e leggero e scrive senza refusi, ma ragiona peggio
  (Colosseo "al coperto", parchi e gelaterie sotto la pioggia, "diciassette è superiore a
  sei"). Buona riserva se la VRAM dovesse stringersi.
- Sorpresa sulla VRAM: **`ollama ps` sottostima i modelli Gemma di circa 1 GiB** rispetto a
  `nvidia-smi`. Misurato davvero, e4b occupa più di gemma3:4b.

## Metodo

### Criteri

1. Italiano naturale e corretto in risposte di 1–3 frasi.
2. Tool calling affidabile.
3. VRAM: 8 GB in tutto, di cui ~1,4 GB già usati da altri programmi e ~770 MiB da riservare
   a Whisper large-v3-turbo.
4. Prima frase entro ~1 s.

### Italiano e latenza — `confronto_llm.py`

Lo script usa il prompt di sistema vero di Calliope (`Config.system_prompt`), lo streaming e
la stessa catena `strip_think` → `split_sentences` → `clean_for_speech` del programma. Per
ogni domanda stampa `[tempo della prima frase / tempo totale]`. Contesto 4096, thinking
spento con `reasoning_effort="none"` (suffisso `@none`), temperatura dalla variabile
`CALLIOPE_TEMP`. Le otto domande:

1. Spiegami in parole semplici perché il cielo è azzurro.
2. Dammi un consiglio per fare bene la pasta alla carbonara.
3. Ieri ho litigato con un amico e non so come fare pace. Che mi consigli?
4. Chi ha scritto I promessi sposi e di cosa parla?
5. Che ore sono?
6. Quanto fa diciassette per sei?
7. Se domani piovesse, cosa potrei fare a Roma con due bambini?
8. Raccontami qualcosa sulla musa di cui porti il nome.

Metro di giudizio, lo stesso dei log precedenti: errori di grammatica, parole inventate,
calchi dall'inglese, fatti sbagliati (Promessi sposi: Manzoni, Renzo e Lucia, peste del 1630;
genitori di Calliope: Zeus e Mnemosine), rispetto del prompt (1–3 frasi, niente markdown,
elenchi o emoji, non presentarsi né offrire altro aiuto, ammettere di non sapere l'ora).
**L'errore su 17×6 non viene contato.**

Passate eseguite: per ciascun Gemma 4 una a 0.7 e una a 0.3, più ripetizioni a 0.7 (e2b: tre
in tutto, la prima a freddo; e4b: due). Come riferimento, una passata a 0.3 per `gemma3:4b` e
`qwen3:8b`. Poiché i log mostrano il testo già ripulito da `clean_for_speech`, ho aggiunto un
controllo dell'**output grezzo** (script temporaneo `grezzo_check.py`, 24 risposte per
modello: due giri a 0.7 e uno a 0.3) per verificare markdown, emoji e maiuscole anomale.
In totale: 56 risposte per e2b, 48 per e4b.

### Tool — `sonda_tool.py`

Quattro richieste a temperatura 0 con tre tool (`ora_attuale`, `accendi_luce`,
`chiedi_alla_bibliotecaria`): "Che ore sono?", "Accendi la luce in cucina.", "In che anno è
scoppiata la peste raccontata nei Promessi sposi?" e "Ciao Calliope, come stai?" (qui il
comportamento giusto è *non* chiamare tool). Tre esecuzioni per modello. Il primo caso di
ogni esecuzione include il caricamento del modello e non vale come latenza.

### VRAM

`ollama ps` (SIZE e PROCESSOR) e `nvidia-smi --query-gpu=memory.used,memory.total` prima e
dopo il caricamento. La colonna "VRAM reale" è la differenza misurata da `nvidia-smi`.

## Tabella riassuntiva

| Modello | Temp. | Italiano | Tool (sonda) | VRAM `ollama ps` | VRAM reale (`nvidia-smi`) | Prima frase media (max) | Caratteri/s |
|---|---|---|---|---|---|---|---|
| gemma3:4b | 0.7 | il migliore, naturale; però inventa fatti (mitologia, una volta l'ora) | **non supportati** in Ollama (400 "does not support tools") | 2,9 GB | — | ~0,3 s | ~290 |
| gemma3:4b | 0.3 | sempre il più naturale; ammette di non sapere l'ora, ma inventa ancora sulla mitologia ("la voce di Atena"); "XVII secolo", "DOP" | non supportati | 2,9 GB | +3765 MiB | 0,30 s (0,53) | 285 |
| qwen3.5:4b (thinking spento) | 0.7 | scadente: errori di grammatica, luoghi e fatti inventati | 3/4 | 3,1 GB | — | ~0,4 s | ~290 |
| qwen3:8b (thinking spento) | 0.7 | discreto, qualche sbavatura ("sughio", "Lorenzo e Lucia") | 4/4 | 5,6 GB | — | ~0,6 s | — |
| qwen3:8b (thinking spento) | 0.3 | discreto ma con fatti sbagliati ("Ludovico e Renzo"), luogo inventato ("Parco della Ciociaria"), "Mnemosyne", "musae"; offre altro aiuto; fino a 5 frasi. Unico a citare Zeus e Mnemosine | 4/4 | 5,6 GB | +5451 MiB | 0,60 s (0,98) | 158 |
| llama3.1:8b | 0.7 | debole su lingua e fatti | 4/4 ma saluta in modo strano | 5,3 GB | — | ~0,7 s | — |
| **gemma4:e2b-it-qat** | 0.7 | scorrevole e senza refusi, ma contenuti poveri e a volte illogici; rari errori di grammatica; si presenta ("Sono Calliope…") | **4/4 ×3** | 1,6 GB | +2781 MiB | 0,24–0,26 s (0,40) | 355–386 |
| **gemma4:e2b-it-qat** | 0.3 | come sopra, un po' più stabile e più breve | (sonda a temp. 0) | 1,6 GB | +2781 MiB | 0,24 s (0,39) | 385 |
| **gemma4:e4b-it-qat** | 0.7 | lessico ricco, contenuti corretti, prompt rispettato; **parole malformate** ("meteos", "museI", "oppression", "gli poeti", "guancialino"); femminile rivolto all'utente | **4/4 ×3** | 3,1 GB | +4198 MiB | 0,44–0,45 s (0,80) | 216–231 |
| **gemma4:e4b-it-qat** | 0.3 | come sopra ma restano solo "museI" e il femminile rivolto all'utente | (sonda a temp. 0) | 3,1 GB | +4198 MiB | 0,46 s (0,64) | 218 |

Tutti i modelli misurati oggi risultano **"100% GPU"** in `ollama ps`: nessuna quota su CPU.

### Spazio che resta per Whisper (8151 MiB totali, ~1400 MiB già occupati)

| Modello caricato | VRAM usata in totale | Libera | Libera dopo Whisper (~770 MiB) |
|---|---|---|---|
| gemma4:e2b-it-qat | 4196 MiB (4222 dopo aver generato) | ~3930 MiB | ~3160 MiB |
| gemma3:4b | 5179 MiB | ~2970 MiB | ~2200 MiB |
| gemma4:e4b-it-qat | 5590 MiB (5595 dopo aver generato) | ~2560 MiB | ~1790 MiB |
| qwen3:8b | 6865 MiB | ~1290 MiB | ~520 MiB |

Con qwen3:8b Whisper ci sta, ma restano circa 500 MiB: niente margine per un contesto più
lungo (definizioni dei tool, cronologia, testi della biblioteca) né per un modello di
embedding. Con e4b resta oltre 1,7 GiB.

## Tool: risultati della sonda

Entrambi i Gemma 4: **4/4 in tutte e tre le esecuzioni**, con output identici a ogni giro.

| Caso | gemma4:e2b-it-qat | gemma4:e4b-it-qat |
|---|---|---|
| "Che ore sono?" | `ora_attuale {}` | `ora_attuale {}` (0,33 s a modello già carico) |
| "Accendi la luce in cucina." | `accendi_luce {"stanza":"cucina"}` — 0,22 s | idem — 0,35–0,39 s |
| Peste dei Promessi sposi | `chiedi_alla_bibliotecaria` con la domanda riportata alla lettera — 0,38 s | idem, con "Promessi Sposi" normalizzato in maiuscolo — 0,61–0,70 s |
| "Ciao Calliope, come stai?" | nessun tool: "Ciao! Sono qui e pronta ad assisterti. Come posso aiutarti oggi?" — 0,22 s | nessun tool: "Ciao! Sto bene, grazie per avermelo chiesto. Come posso aiutarti oggi?" — 0,35–0,40 s |

Il saluto è naturale in tutti e due (meglio di llama3.1:8b); quello di e4b risponde davvero
alla domanda "come stai?". Entrambi chiudono con "Come posso aiutarti oggi?", ma il prompt
della sonda non lo vieta. Avvertenza: quattro casi sono pochi. Prima di fidarsi servono prove
con più turni (risultato del tool → risposta a voce), parametri meno ovvi e più richieste che
*non* devono attivare tool.

## Risposte complete — gemma4:e2b-it-qat (temperatura 0.3)

`ollama ps`: 1.6 GB, 100% GPU, contesto 4096. Caricamento 3,8 s.

1. **Cielo** `[0,35 s / 0,57 s]` Il cielo appare azzurro perché la luce del sole interagisce
   con l'atmosfera terrestre. Questa luce si scompone in colori, e il blu è il colore che
   viene diffuso più intensamente dall'aria intorno a noi.
2. **Carbonara** `[0,23 s / 0,40 s]` Per una carbonara perfetta, usa guanciale di buona
   qualità e uova freschissime. Manteca tutto velocemente fuori dal fuoco per ottenere una
   crema vellutata e non troppo asciutta.
3. **Litigio** `[0,19 s / 0,44 s]` Capisco che tu stia attraversando un momento difficile. Ti
   consiglio di darti un po' di tempo per calmarti e poi provare a pensare a come potresti
   esprimere i tuoi sentimenti in modo onesto.
4. **Promessi sposi** `[0,19 s / 0,45 s]` I Promessi Sposi sono stati scritti da Alessandro
   Manzoni. Racconta la storia di due giovani, Renzo e Lucia, che si trovano a dover
   affrontare le difficoltà e le ingiustizie della società del Seicento.
5. **Ora** `[0,19 s / 0,19 s]` Mi dispiace, non ho accesso all'ora in questo momento.
6. **17×6** `[0,16 s / 0,16 s]` Diciassette per sei fa trentatré.
7. **Roma con la pioggia** `[0,39 s / 0,39 s]` A Roma, se piove, potresti visitare i musei,
   come i Musei Capitolini, o goderti un pomeriggio in una delle tante trattorie per
   assaggiare la cucina locale.
8. **Musa** `[0,23 s / 0,32 s]` Sono Calliope, e il mio nome deriva dalla musa della poesia
   epica. Lei è associata alla narrazione e alla voce potente.

Medie: prima frase 0,24 s (max 0,39 s), 385 caratteri/s, risposta media 141 caratteri.

## Risposte complete — gemma4:e4b-it-qat (temperatura 0.3)

`ollama ps`: 3.1 GB, 100% GPU, contesto 4096. Caricamento 6,2 s.

1. **Cielo** `[0,52 s / 0,78 s]` Il cielo appare azzurro perché l'atmosfera terrestre diffonde
   la luce del sole in modo particolare. Questa diffusione, chiamata scattering di Rayleigh,
   sposta la luce blu verso l'occhio umano.
2. **Carbonara** `[0,50 s / 0,85 s]` Per una carbonara perfetta, usa solo guanciale, tuorli
   d'uovo e pecorino romano. La chiave è mantecare la pasta con il calore residuo, senza far
   cuocere l'uovo.
3. **Litigio** `[0,60 s / 0,89 s]` Prova a dargli spazio per rifletterci un po' e poi, quando
   ti senti pronta, cerca un momento tranquillo per parlargli con calma. Ascoltare il suo
   punto di vista è spesso il primo passo per guarire un litigio.
4. **Promessi sposi** `[0,44 s / 0,86 s]` Manzoni ha scritto I Promessi Sposi, un romanzo
   storico ambientato nel Seicento. Racconta la storia di due giovani che cercano di sposarsi
   ma si trovano coinvolti in vicende complesse e drammatiche.
5. **Ora** `[0,26 s / 0,26 s]` Non ho accesso all'ora attuale.
6. **17×6** `[0,28 s / 0,28 s]` Diciassette per sei fa cento e due.
7. **Roma con la pioggia** `[0,64 s / 0,90 s]` Non posso sapere se domani pioverà, ma a Roma
   ci sono molti museI e luoghi coperti perfetti per una giornata piovosa con i bambini.
   Potreste visitare il Museo delle Cere o passeggiare in un grande centro commerciale.
8. **Musa** `[0,46 s / 0,82 s]` Io porto il nome di Calliope, la musa dell'eloquenza e della
   poesia epica. È considerata una delle nove muse della mitologia greca, e la sua influenza
   è legata alla bellezza del linguaggio.

Medie: prima frase 0,46 s (max 0,64 s), 218 caratteri/s, risposta media 154 caratteri.

## Giudizio sull'italiano — gemma4:e2b-it-qat (56 risposte)

**Ortografia e parole inventate.** Nessun refuso e nessuna parola inventata in 56 risposte.
Nessuna maiuscola anomala nell'output grezzo.

**Grammatica.** Errori rari ma presenti, quasi tutti a 0.7:
- "usa guanciale di buona qualità e **mantecati** bene le uova" (forma verbale sbagliata);
- "Ti suggerirei di **darti** un po' di spazio **a entrambi** per **calmarti**" e, a 0.3,
  "dare un po' di tempo a entrambi per calmarti" (accordo singolare/plurale);
- "I Promessi Sposi **sono scritti** da…" (tempo), "**Quello è scritto** da Alessandro
  Manzoni" (innaturale), "I Promessi Sposi sono stati scritti… **Racconta**…" (salto di
  numero, quasi sempre).

**Calchi e scelte lessicali goffe.** "non ho accesso all'**orario in tempo reale**" (4 volte
su 7: calco di *real-time*, e "orario" al posto di "ora"), "La chiave è…", "Lei è associata
a…", "le diverse **lunghezze delle onde luminose**", "tutte le diverse **lunghezze di
colore**", "altre **colorazioni**", "l'**aria terrestre**".

**Fatti.** Promessi sposi: Manzoni 7/7, Renzo e Lucia 6/7 (una volta "un gruppo di persone"),
mai un nome o una data sbagliati; la peste compare una volta sola, senza anno. Una frase
senza senso a 0.7: "le loro difficoltà morali e religiose durante **un'intensa campagna in
Lombardia**". Calliope: mai genitori inventati (ma nemmeno quelli giusti: non li cita mai);
"musa della poesia epica" è corretto, il resto è riempitivo vago o inesatto ("musa
dell'inizio delle grandi storie", "della celebrazione", "della musica", "epica e
commovente"). Luoghi di Roma tutti reali — un passo avanti netto rispetto a qwen3.5:4b.

**Buon senso: il vero punto debole.** Con la pioggia propone "il Colosseo, che ha spazi
coperti" (2 volte), "parchi meravigliosi dove i bambini possono correre sotto la pioggia", il
Parco degli Acquedotti, Villa Borghese, una passeggiata a Trastevere, "una gelateria per
rinfrescarti". Sulla moltiplicazione, oltre al risultato sbagliato (non contato), due volte
non capisce la domanda: "Diciassette è superiore a sei" e "Diciassette **meno** sei fa
undici". A 0.3: "la luce del sole, proveniente dal nostro sistema solare".

**Rispetto del prompt.** Sempre 1–3 frasi; mai markdown, elenchi, emoji o ritorni a capo
(verificato sul grezzo). Ammette di non sapere l'ora 7/7. **Si presenta** nella domanda 8 in
7 passate su 7 ("Sono Calliope, e il mio nome deriva da Calliope…", pure ridondante). Offre
altro aiuto una volta su 7 ("Posso aiutarti con qualcos'altro?", a 0.7).

**In sintesi:** italiano pulito e scorrevole, più corretto di qwen3.5:4b e llama3.1:8b, ma
contenuti sottili e a tratti illogici. Lontano dalla naturalezza di gemma3:4b.

## Giudizio sull'italiano — gemma4:e4b-it-qat (48 risposte)

**Ortografia e parole inventate: il difetto principale.** Sette parole malformate in sei
risposte su 48 (circa una risposta su otto):
- "molti **museI**" con la I maiuscola: **3 volte, in passate diverse, sia a 0.7 sia a 0.3**
  (a 0.3 in due passate su due). Confermato nell'output grezzo: è il modello, non la pulizia;
- "Non ho informazioni sul **meteos**" (0.7);
- "un'Italia segnata da carestie e **oppression**." (0.7: parola troncata o inglese);
- "ispirava **gli poeti**" (0.7: articolo sbagliato);
- "**guancialino** croccante" (0.7: diminutivo che non si usa).

Non so dire se dipenda dalla quantizzazione QAT di questo tag o dal modello: servirebbe un
altro tag di e4b per confronto (non scaricato, non era autorizzato).

**Femminile rivolto all'utente.** Nella domanda 3 dà del femminile a chi parla in 4 passate
su 6: "quando ti senti **pronta**" (3 volte), "essere **sincera** sui tuoi sentimenti".
Confonde il proprio genere (il prompt dice "Parli di te al femminile") con quello
dell'utente. e2b non lo fa mai. Probabilmente si corregge con una riga nel prompt, da
verificare.

**Calchi.** "**guarire** un litigio" (2 volte), "La chiave è…", "**scattering** di Rayleigh"
(a 0.3; a 0.7 usa il corretto "diffusione di Rayleigh"), "la **salsa**" per la carbonara.

**Grammatica.** A parte "gli poeti", solo due virgole al posto del punto ("Manzoni ha scritto
I promessi sposi, è un capolavoro che…").

**Fatti.** Promessi sposi: Manzoni 6/6, nessun fatto sbagliato; però resta sul vago: Renzo e
Lucia nominati una sola volta su 6 ("due giovani", "due umili sposi"), la peste mai. Calliope:
"musa dell'eloquenza e della poesia epica", "una delle nove muse": tutto corretto, nessuna
invenzione, ma Zeus e Mnemosine non li cita mai. Roma: solo luoghi reali (Museo delle Cere) o
generici (un museo interattivo, un centro commerciale), mai attività all'aperto sotto la
pioggia. Scienza e cucina più precise di e2b (Rayleigh, tuorli, pecorino romano, calore
residuo). Per inciso è l'unico modello ad aver fatto giusto 17×6, in tutte le passate.

**Rispetto del prompt: il migliore del gruppo.** Sempre 1–3 frasi, di solito due; mai
markdown, elenchi o emoji; **non si presenta mai** ("Io porto il nome di Calliope…" risponde
alla domanda) e **non offre mai altro aiuto** nelle 48 risposte; ammette di non sapere l'ora
6/6. Unico eccesso di zelo: in tutte e 6 le passate, alla domanda ipotetica "se domani
piovesse", premette di non poter sapere se pioverà o di non avere il meteo — coerente con il
prompt, ma pedante.

**In sintesi:** è il modello con i tool che scrive le risposte più corrette e più aderenti
al prompt. Meno caldo e meno ricco di gemma3:4b, ma non inventa. Le parole malformate sono un
difetto reale perché il TTS le pronuncia (vedi sotto).

## Temperatura 0.3 contro 0.7

- **gemma4:e2b**: a 0.3 risposte più brevi (141 caratteri contro 158–168) e più stabili tra
  una passata e l'altra. Le stranezze peggiori sono tutte a 0.7 ("Diciassette è superiore a
  sei", "meno sei", "un'intensa campagna", "mantecati", "Quello è scritto", l'offerta di
  altro aiuto, il Colosseo "coperto"). A 0.3 ne restano di più lievi ("proveniente dal nostro
  sistema solare", Villa Borghese con la pioggia, l'accordo "a entrambi… calmarti").
- **gemma4:e4b**: a 0.3 spariscono i refusi casuali ("meteos", "oppression", "gli poeti",
  "guancialino"), ma **"museI" resta** (2 passate su 2) e così il femminile rivolto
  all'utente: non sono incidenti di campionamento, sono scelte ad alta probabilità del
  modello. A 0.3 compare "scattering" al posto di "diffusione". Le risposte diventano quasi
  identiche tra una passata e l'altra.
- **gemma3:4b a 0.3**: stavolta ammette di non sapere l'ora, ma **inventa ancora sulla
  mitologia** ("Si diceva che fosse la voce di Atena"). Abbassare la temperatura non cura le
  sue invenzioni. Resta il più naturale, con qualche sbavatura ("per il comportamento tuo",
  l'attacco "Oh, che brutta sorpresa!").
- **qwen3:8b a 0.3**: non migliora sui fatti ("la vita di **Ludovico e Renzo**, due giovani
  uomini"; "Parco della Ciociaria" a Roma), usa forme non italiane ("Mnemosyne", "musae"),
  non risponde a 17×6 ("ti do la risposta subito"), offre altro aiuto e arriva a 5 frasi.
- La temperatura non cambia la latenza.

Conclusione: **0.3 conviene** su tutti i modelli — toglie parte degli incidenti senza
rendere le risposte rigide — ma non trasforma un modello che inventa in uno affidabile.

## Cose che un TTS legge male

Ho controllato la fonemizzazione di Piper (`it_IT-paola-medium`) sui casi visti:

| Testo | Come lo legge Piper | Esito |
|---|---|---|
| "molti museI" (e4b) | "mùze ì": accento spostato e "i" staccata | **si sente** |
| "meteos", "oppression." (e4b) | letti come sono scritti | **si sente** |
| "scattering di Rayleigh" (e4b a 0.3) | "skattèring di railèig" | brutto; anche "diffusione di Rayleigh" inciampa sul nome |
| "XVII secolo" (gemma3:4b) | "diciassettesimo secolo" | bene, Piper scioglie i numeri romani |
| "DOP" (gemma3:4b) | "di-o-pi" | accettabile |
| "16:37" (gemma3:4b, log precedente) | "sedici e trentasette" | bene |
| "cento due" (e4b) | "cento due" | bene |

I due Gemma 4 scrivono già "per la voce": "Seicento" in lettere, numeri in lettere, nessuna
sigla, nessun orario, nessun anno in cifre. Il problema di e4b sono solo le parole
malformate. qwen3:8b scrive "1827" in cifre (Piper lo legge bene) e "Mnemosyne", "musae".

Contromisura a costo quasi nullo per "museI": in `clean_for_speech` rendere minuscola ogni
maiuscola che segue una minuscola dentro la stessa parola. Non cura "meteos" né "oppression".

## Raccomandazione

**Oggi, con 8 GB: `gemma4:e4b-it-qat`, temperatura 0.3, thinking spento.**

1. **Tool**: 4/4 stabile, e i tool nativi sono il requisito che esclude gemma3:4b.
2. **Italiano**: tra i modelli che sanno usare i tool è quello che sbaglia meno i fatti e
   rispetta meglio il prompt. qwen3:8b e llama3.1:8b inventano nomi e luoghi, e2b ragiona
   peggio. Con la biblioteca offline dietro un tool, conta più *non inventare* che sapere
   molto: e4b fa esattamente questo.
3. **VRAM**: ~4,1 GiB reali; con Whisper restano ~1,8 GiB per contesto più lungo ed
   embedding. qwen3:8b lascerebbe ~0,5 GiB.
4. **Latenza**: prima frase 0,45 s in media, massimo 0,80 s — dentro l'obiettivo di 1 s,
   più veloce di qwen3:8b (0,60 s, massimo 0,98 s).

Da fare subito dopo l'adozione:
- aggiungere al prompt una riga sul genere dell'utente (o "non dare per scontato il genere
  di chi parla") e verificare che "pronta"/"sincera" spariscano;
- la piccola normalizzazione delle maiuscole in `clean_for_speech`;
- se il proprietario autorizza un altro download, provare un tag di e4b non QAT per capire
  se le parole malformate vengono dalla quantizzazione;
- allargare la sonda dei tool (più turni, più casi negativi).

**Riserva: `gemma4:e2b-it-qat`.** Se la VRAM si stringe (embedding della biblioteca, contesto
lungo, un secondo modello in parallelo) e2b fa gli stessi 4/4 sui tool in 2,7 GiB e con la
prima frase a 0,25 s. Va bene come instradatore di tool o per risposte semplici; non lo
metterei a conversare da solo, per i limiti di buon senso visti sopra.

**gemma3:4b** resta il riferimento per la naturalezza, ma senza tool in Ollama, con le
invenzioni sulla mitologia anche a 0.3 e con 3,7 GiB reali non ha più motivo di essere
scelto. **qwen3:8b** esce dalla rosa: non è migliore sui fatti, è più lento e riempie la
VRAM.

## Problemi incontrati

- **`ollama ps` sottostima la VRAM dei Gemma.** e2b: 1,6 GB dichiarati contro +2781 MiB
  misurati; e4b: 3,1 GB contro +4198 MiB; gemma3:4b: 2,9 GB contro +3765 MiB. Per qwen3:8b
  invece i conti tornano (5,6 GB contro +5451 MiB). Ipotesi non verificata: gli encoder
  multimodali e gli embedding per strato dei Gemma non rientrano nel SIZE. La colonna VRAM
  della tabella in `docs/visione.md` andrebbe letta con questa correzione. Anche la
  dimensione su disco (4,3 e 6,1 GB) dice poco sulla VRAM.
- **Avvio a freddo.** La prima domanda dopo il primissimo caricamento di e2b ha impiegato
  8,29 s (caricamento 25,8 s). Non è thinking: nelle passate successive la stessa domanda
  sta a 0,35 s. Era già successo a gemma3:4b (5,86 s). Il `warmup()` con un solo token non
  basta a scaldare tutto: conviene un riscaldamento con il prompt di sistema vero.
- **Download**: entrambi i tag esistono e sono stati scaricati senza errori (circa 14 e 19
  minuti). Li ho lanciati in background, quindi il limite di 10 minuti non ha richiesto
  riavvii. Le passate di e2b sono avvenute durante il download di e4b; la passata di
  controllo a download finito dà gli stessi tempi (0,26 s contro 0,24 s).
- **`@none` accettato da tutti i modelli**, compreso gemma3:4b che non ha thinking. Nessun
  segno di thinking acceso in nessuna passata.
- **I log di `confronto_llm.py` mostrano il testo già ripulito**, quindi da soli non dicono
  se il modello produce markdown o emoji. Per questo ho aggiunto il controllo sul grezzo
  (script temporaneo nello scratchpad; gli script esistenti non sono stati toccati).
- Nessun file del progetto è stato modificato, a parte questo rapporto.

## File di log

Nella cartella scratchpad della sessione: `gemma4_e2b_t07.log` (a freddo),
`gemma4_e2b_t07_bis.log`, `gemma4_e2b_t07_tris.log`, `gemma4_e2b_t03.log`,
`gemma4_e4b_t07.log`, `gemma4_e4b_t07_bis.log`, `gemma4_e4b_t03.log`, `gemma3_4b_t03.log`,
`qwen3_8b_t03.log`, `gemma4_e2b_tool.log`, `gemma4_e4b_tool.log`, `gemma4_e2b_vram.log`,
`gemma4_e4b_vram.log`, `gemma4_e4b_vram_dopo.log`, `riferimenti_vram.log`,
`gemma4_e2b_grezzo.log`, `gemma4_e4b_grezzo.log`, `piper_fonemi.log`. La cartella è
temporanea: i dati essenziali sono tutti riportati qui sopra.
