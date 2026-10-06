# Documenti di casa con il grafo (03/10/2026)

Decisione dell'utente del 02/10: i documenti della famiglia (bollette, contratti,
assicurazioni, ricevute, referti, garanzie, documenti d'identità, manuali…) diventano
interrogabili a voce con **indice + schede strutturate + un grafo in SQLite progettato da
subito come grafo completo**, senza doppio lavoro quando arriveranno altri tipi.

Codice: `calliope/archivio/` (grafo, tipi e schede, lettura e OCR, estrattore, servizio,
esplorazione dell'agente), `calliope/tools/archivio.py` (tool della voce), strumenti
dell'agente nelle ricerche delegate (`calliope/agenti/ciclo.py`). Prove: `prove/prova_archivio.py`
(a secco, nel runner), `prove/prova_archivio_ollama.py` (voce con gemma4), misure manuali
`prove/archivio_misura_ocr.py` e `prove/archivio_misura.py`. Documenti di prova:
`prove/archivio_finto.py`, tutti inventati (persone, aziende, numeri); mai documenti veri nel
repository.

## 1. Flusso

```
cartella dei documenti (archivio_cartella, sulla DGX, fuori da git)
  │  thread «archivio», ogni archivio_intervallo_min (10): dimensione, data, SHA-256
  ▼
testo.py   PDF con testo → pypdfium2 · pagina senza testo, foto, TIFF → OCR (modello visivo)
           Word → python-docx · .txt
  ▼
estrattore.py   modello grande (qwen3.6 su vLLM, client degli agenti), senza ragionamento:
                1) tipo (enum)  2) scheda del tipo (schema JSON strict, output strutturati)
  ▼
tipi.pulisci   ogni valore controllato contro il testo: quello che non c'è → null + «scartati»
tipi.calcola   date ricavate dal programma (fine garanzia, fine contratto, disdetta)
  ▼
tipi.nel_grafo + grafo.py   nodi e archi con la fonte, deduplicazione, FTS5, scheda salvata
  ▼
voce: archivio_cerca / archivio_scadenze / archivio_somma (frase pronta, permessi nel codice)
agente: grafo_schema / grafo_trova / grafo_vicini / grafo_cammino / grafo_documenti / grafo_somma
```

La voce non aspetta mai: il thread dell'archivio è l'unico che scrive; le letture usano una
seconda connessione SQLite in sola lettura (`PRAGMA query_only`), con il database in WAL.

## 2. Schema del grafo

Tabelle (`calliope/archivio/grafo.py`, `SCHEMA`):

| Tabella | Contenuto |
|---|---|
| `tipi_nodo`, `tipi_arco` | i tipi ammessi con la descrizione (l'agente li legge con `grafo_schema`); per gli archi anche i tipi di partenza e d'arrivo |
| `nodi` | `id`, `tipo`, `chiave` (unica per tipo), `nome`, `data`, `valore`, `attributi` JSON |
| `archi` | `da`, `rel`, `a`, `attributi` JSON, `fonte` (il documento che lo afferma); unico per (da, rel, a, fonte) |
| `alias` | (tipo, forma) → nodo, con l'origine: `piva`, `cf`, `id`, `nome`, `simile`, `manuale` |
| `file` | percorso relativo → SHA-256, dimensione, data, stato (`ok`, `errore`, `in_attesa`), versione, nodo |
| `schede` | per documento: tipo, versione dell'estrattore, scheda JSON, testo letto, metodo (pdf, ocr, docx), versione della lettura, scartati |
| `testi` | FTS5 (`unicode61 remove_diacritics 2`) su nome e testo, rowid = id del documento |
| viste `v_documenti`, `v_archi` | quelle su cui ragionano gli strumenti (mai SQL scritto dal modello) |

`data` e `valore` sono colonne vere con indice, non attributi: scadenze e somme sono query del
programma. Un tipo nuovo di nodo o di relazione è **una riga** in `TIPI_NODO` o `TIPI_ARCO`
(si aggiorna da sola nelle tabelle all'avvio, con un upsert che non tocca i nodi); un tipo nuovo
di documento è una voce in `tipi.TIPI` con i suoi campi. Lo schema delle tabelle non cambia.

Tipi di nodo: `documento` (data del documento, valore = importo principale), `persona`,
`ente`, `importo` (valore, data, voce), `scadenza` (data, cosa), `bene` (auto con targa,
elettrodomestico con matricola, fornitura con POD o PDR), `luogo`, `categoria` (luce, gas,
acqua, auto, salute…).

Relazioni: `emesso_da` (documento → ente), `intestato_a` (documento → persona), `redatto_da`
(documento → persona o ente: il medico), `riguarda` (documento → bene, luogo, categoria,
persona), `copre` (garanzia o polizza → bene), `ha_importo` (documento → importo),
`scade_il` (documento → scadenza), `paga` (persona → importo, per bollette, ricevute,
contratti e polizze), `fornisce` (ente → bene: la fornitura con quel POD), `si_trova_in`
(bene → luogo), `rinnova` (documento → documento, per i rinnovi: c'è nello schema, non la
riempie ancora nessuno).

**Fonte.** Ogni arco porta il documento che lo afferma. Rielaborare un documento vuol dire
togliere i suoi archi (e gli importi e le scadenze solo suoi, chiave `doc:<id>:…`) e rifarli;
un'entità rimasta senza archi si cancella (salvo un alias messo a mano). La stessa fonte
decide i permessi dell'agente: un arco affermato solo da un documento che non può vedere non
esiste (§6).

**Il modello produce solo la scheda.** Nodi e archi li fa il codice da `tipi.nel_grafo`,
con le regole di deduplicazione: niente relazioni o tipi inventati dal modello. Il prezzo è che
una relazione nuova va scritta nel codice; il guadagno è che il grafo non si sporca.

## 3. OCR: misure e scelta

Requisiti: senza cloud, sulla DGX (ARM, GPU), niente sudo (Tesseract via apt escluso).
Candidati: un OCR leggero in ONNX (RapidOCR 3.9.2 con onnxruntime 1.30, PP-OCRv5
riconoscimento «latin» per gli accenti, rilevamento PP-OCRv6) e un modello visivo già servito.
Il controllo del 03/10 sui server accesi: **qwen3.6-35b** (Qwen3_5MoeForConditionalGeneration,
`vision_config`, vLLM senza `--language-model-only`) accetta le immagini sulla 8000;
**gemma4-26b** (Gemma4ForConditionalGeneration) sulla 8001 (il modello della voce che sta
provando un altro agente: usato solo per questa misura, poche richieste).

Banco (`prove/archivio_misura_ocr.py`, sulla DGX): 6 immagini finte (4 foto storte e rumorose
con luce non uniforme, 2 PDF scansionati disegnati a 144 dpi; una bolletta a due colonne con
testo piccolo), ognuna a piena risoluzione, a metà e «dura» (40 per cento, sfocata, JPEG
qualità 30). CER sul testo vero (minuscole, spazi compressi); «chiavi» = importi, date e codici
letti esatti (30 per versione).

| Motore | Versione | Secondi (mediana) | CER medio | Chiavi esatte |
|---|---|---|---|---|
| qwen3.6-35b (vLLM, GPU) | piena | 4,52 | 0,9 % | 30/30 |
| | metà | 4,11 | 1,0 % | 30/30 |
| | dura | 4,13 | 1,5 % | **29/30** |
| gemma4-26b (vLLM, GPU) | piena | 4,68 | 0,9 % | 30/30 |
| | metà | 4,78 | 0,9 % | 30/30 |
| | dura | 4,68 | 10,3 % | 30/30 |
| RapidOCR latin (CPU) | piena | 0,59 | 0,9 % | 30/30 |
| | metà | 0,45 | 1,0 % | 30/30 |
| | dura | 0,44 | 6,8 % | **17/30** |

Note:
- il CER dello 0,9 % sulle versioni buone è quasi tutto la bolletta a due colonne (5,5 % per
  tutti: l'ordine di lettura delle colonne, non errori di lettura);
- sulla foto dura RapidOCR legge «,» come «.» e «2026» come «2028», e perde 13 valori chiave
  su 30; gemma4-26b sulla bolletta a due colonne dura mette prima tutte le etichette e poi
  tutti gli importi (CER 61,6 %: «Totale fattura» non è più accanto a «79,81», pericoloso per
  l'estrazione); qwen3.6 tiene le righe e sbaglia una cifra sola (il numero della polizza
  «445586» per «445566»);
- RapidOCR porta con sé opencv, shapely, pyclipper, omegaconf, requests e scarica i modelli
  da modelscope al primo uso (285 MB di venv); il modello visivo non aggiunge niente.

**Scelta: il modello visivo, qwen3.6 sulla DGX** (`archivio_ocr_modello` vuoto = lo stesso
dell'estrazione). Più robusto sulle foto peggiori, nessuna dipendenza nativa nuova
(principio 4), già acceso per gli agenti. Costa ~4–5 s a pagina, in secondo piano: non pesa
sulla voce. RapidOCR resta un'alternativa documentata se un giorno servisse un OCR su CPU
(Windows ARM senza DGX). Le pagine di un PDF con testo non passano dall'OCR (pypdfium2:
PDFium, wheel per win_amd64, win_arm64 e manylinux aarch64); le foto si girano con
l'orientamento EXIF e si riducono a 1 600 pixel di lato.

## 4. Estrazione delle schede

Due passate senza ragionamento e a temperatura 0: il tipo (`enum` dei 9 tipi), poi la scheda
del tipo con lo **schema JSON strict** (tutti i campi obbligatori, null se il dato non c'è;
`response_format` di tipo `json_schema` su vLLM, decodifica guidata). Campi comuni: oggetto,
data del documento, numero, emittente, intestatari, importo totale, scadenze, beni,
indirizzi; più i campi del tipo (bolletta: categoria, periodo, consumo, unità, codice cliente,
POD/PDR; contratto: inizio, fine, durata, rinnovo tacito, preavviso, canone; polizza: ramo,
decorrenza, scadenza, premio; garanzia: prodotto, marca, modello, matricola, acquisto,
durata, fine; referto: esame, data, medico; documento d'identità: tipo, nascita, rilascio,
scadenza; manuale: prodotto, marca, modello).

**Mai inventare** (`tipi.pulisci`): un importo, un numero, una data, un codice o un nome si
tengono solo se si ritrovano nel testo, in una delle forme italiane («84,50», «1.234,56»,
«12/03/2025», «12 marzo 2025», «agosto 2025» per i periodi, codici senza spazi). Il resto
diventa null e finisce negli `scartati` della scheda, con il campo e il motivo. Il codice
fiscale di un ente si tiene solo se è di 11 cifre (uno di persona era quello dell'intestatario
messo al posto sbagliato). Le date che servono e non sono scritte (fine della garanzia da
acquisto + durata, fine del contratto, ultimo giorno per la disdetta) le calcola il programma
(`_calcolati`), mai il modello: nella misura qwen3.6 aveva calcolato da solo la fine del
contratto («2028-02-01», non scritta): scartata, poi ricalcolata dal programma e segnata come
calcolata.

Una sola correzione di forma sul testo (principio 10): se il modello scrive il solo nome di
battesimo e il documento ha le etichette «Cognome: … Nome: …» (carte d'identità, moduli), si
uniscono (regola `nome_cognome_uniti`, nelle `_regole` della scheda; l'estrazione non è un
turno, quindi non va nel registro dei turni).

Misure (`prove/archivio_misura.py`, qwen3.6-35b NVFP4 su vLLM 0.29.0, dal portatile con un
tunnel; 10 documenti finti: 3 PDF con testo, 2 scansioni, 4 foto, 1 Word; 102 campi attesi su
2 giri):

| Versione | Campi giusti | Note |
|---|---|---|
| emittente «oggetto oppure null» | 86/102 | l'emittente sempre null (10 su 10), anche con il nome in cima |
| emittente sempre oggetto, nome nullable | 88/102 | persone con il solo nome («Mario») in 8 documenti su 10 |
| campo `nome_e_cognome` per le persone | **100/102** | i 2 errori sono l'OCR («ELETTRDOMESTICI» per «ELETTRODOMESTICI»), e la deduplicazione lo unisce comunque |

Due lezioni sugli output strutturati con qwen3.6: un oggetto facoltativo come `anyOf` con
null viene scelto null quasi sempre; e il nome di un campo conta come una istruzione
(«nome» = nome di battesimo). Tempo per documento: mediana 7,4 s (PDF con testo 5–6 s, foto e
scansioni 7–8 s), fino a 17 s con il server impegnato da altri lavori; per un archivio di
qualche centinaio di documenti, la prima lettura dura meno di un'ora, poi solo i nuovi.

**Riprocessamento.** `tipi.VERSIONE` (estrattore, campi, controlli, grafo) e `testo.VERSIONE`
(lettura e OCR) stanno nella scheda e nei file: a versione nuova il giro dopo rielabora tutto;
se è cambiato solo l'estrattore il testo salvato si riusa (niente OCR di nuovo). Prova a
secco: 10 documenti rielaborati, 0 chiamate all'OCR, 20 al modello, conteggi del grafo
identici. `python -m calliope.archivio --riprocessa` lo forza.

## 5. Deduplicazione

Regole (`normalizza.py`, `Grafo.entita`), in quest'ordine:
1. identificativo forte valido: partita IVA con la cifra di controllo, codice fiscale nella
   forma giusta (anche con omocodia), codice del bene (targa, matricola, POD, PDR) di almeno 5
   caratteri;
2. nome normalizzato: minuscole, senza accenti e punteggiatura, senza forme societarie
   («S.p.A.», «srl», «s.n.c.», «Società per azioni»…) e titoli («dott.ssa», «sig.»); per le
   persone le parole in ordine alfabetico («BIANCHI MARIO» = «Mario Bianchi»); per i luoghi
   senza CAP e sigle;
3. nome molto simile dello stesso tipo (rapporto ≥ 0,92, almeno 6 caratteri): diventa un
   alias `simile` (l'OCR «ELETTRDOMESTICI ROSSI» si è unito a «Elettrodomestici Rossi»);
4. due identificativi forti diversi non si uniscono mai, anche con lo stesso nome (due aziende
   omonime con partite IVA diverse; prova a secco).

Tutte le chiavi di un'entità finiscono nella tabella `alias`: una partita IVA vista dopo il nome
si aggancia allo stesso nodo. A mano: `python -m calliope.archivio --nodi ente` e `--unisci
<tenere> <togliere>` (alias `manuale`, che sopravvive alla pulizia).

## 6. Interrogazione

**A voce** (gemma4, tool chiusi con gli enum, frase pronta in `risposta_finale`):
- `archivio_cerca(cosa, tipo, persona, periodo, dato)`: ricerca FTS5 con le radici (la parola
  senza l'ultima lettera: «bollett», «contratt»; con 5 lettere «contr» prendeva anche
  «Contraente»), più peso alle parole nel nome del documento, alla categoria e al tipo, a
  parità il più recente; `dato` = descrizione, importo, scadenza, numero, data, chi, oppure
  `dettagli` (i campi della scheda al modello, per «quanti kWh?»);
- `archivio_scadenze(entro)`: settimana, mese, tre mesi, anno;
- `archivio_somma(categoria, tipo, ente, persona, periodo)`: le somme le fa il programma
  (bollette, ricevute, polizze; non i canoni dei contratti, che sono mensili), con gli anni
  separati.
I periodi detti («2025», «settembre 2026», «quest'anno», «l'anno scorso») li converte
`servizio.periodo` (anni espliciti, poi `tempi.parse_past_range`). La scheda va sugli schermi
(tipo `documento`, una tabella dei campi) con visibilità «casa» o «personale».

Misura (`prove/prova_archivio_ollama.py`, gemma4:e4b-it-qat sul portatile, con PC finto,
documenti, schermi, agenti e archivio registrati): **25/26** in 2 giri (prima delle correzioni
delle descrizioni 24/26: «fino a quando è in garanzia la lavatrice?» senza tool, «quanti kWh?»
con `dato=importo`); l'errore rimasto è una domanda di chiarimento al posto del tool («a chi è
intestato il contratto di internet?», 1 volta su 4). Prima frase mediana 0,61 s (0,4–0,9 s;
~3 s la prima domanda dopo un cambio di livello, quando Ollama rifà il prefisso). I distrattori
restano dove devono («cerca sul computer il preventivo» → `pc_cerca_file`, la lettera →
`documento_crea`), e la carta d'identità di Giulia chiesta da Laura non esce mai.

**L'agente** (domande complesse delegate con `delega_lavoro` di tipo ricerca): sei strumenti
chiusi in `esplora.py`, argomenti JSON tradotti dal codice in query parametriche; il più
espressivo è `grafo_cammino` (partenza + fino a 4 passi {relazione, verso, tipo}). Le somme e
i raggruppamenti (anno, mese, ente, categoria) li fa `grafo_somma`. Misura con il modello vero:
§9.

## 7. Permessi e privacy

Nel codice (`servizio.Archivio.puo_vedere`), non nel prompt:
- **ospiti**: niente (i tool non ci sono; se il modello ne scrive uno, il registro rifiuta);
- **sensibili** (referti e documenti d'identità, `Tipo.sensibile`): solo la persona interessata
  (intestataria collegata al suo profilo, o la sua cartella) e chi amministra, e mai nella zona
  grigia della conversazione;
- **personali**: un documento in una sottocartella con il nome di un profilo («Giulia/…») lo
  vedono lei e chi amministra;
- **della casa**: tutto il resto, i familiari.
Il legame persona del documento ↔ profilo è esplicito: `archivio_intestatari` ({profilo: "nome
e cognome, codice fiscale"}) o il nome completo del profilo uguale a quello sul documento; il
solo nome di battesimo non basta («Maria» madre e figlia).

**Registro dei turni**: i tool dell'archivio sono `riservati` (`ToolSpec.riservato`): nel
registro e nel terminale solo il nome del tool (argomenti vuoti, risultato «(riservato)»), e la
risposta del turno non si scrive (`risposta: null`, `riservato: true`). Resta la richiesta della
persona, come per gli altri turni.

**Agente**: vede con i permessi di chi ha delegato, ma i documenti sensibili **mai** (anche
l'interessato: quelli si chiedono a voce), e nemmeno gli archi che solo loro affermano (il
medico di un referto non compare cercando «Verdi»).

## 8. Configurazione e comandi

`calliope.locale.yaml` sulla DGX, sezione `archivio`: `archivio_cartella` (obbligatoria; senza,
la capacità «archivio dei documenti di casa» è da configurare e i tool non ci sono),
`archivio_intestatari`, eventualmente `archivio_url` / `archivio_modello` /
`archivio_ocr_modello` (vuoti = il modello degli agenti: con il motore «openai» di vLLM). Il
database è `archivio.db` accanto alla configurazione (fuori da git). Librerie: extra
`archivio` (`pypdfium2`, `pillow`, `python-docx`). Da terminale:

```
python -m calliope.archivio                 # stato
python -m calliope.archivio --giro          # legge subito i file nuovi
python -m calliope.archivio --riprocessa    # rilegge tutto
python -m calliope.archivio --nodi persona  # id per --unisci
```

## 9. Agente sul grafo con il modello vero

`prove/archivio_misura.py --agente`: dopo l'estrazione vera dei 10 documenti, tre domande
delegate al ciclo di ricerca dell'agente (qwen3.6 con il ragionamento, come i lavori veri),
chi chiede amministra:

| Domanda | Tempo | Passate, token | Strumenti | Risposta |
|---|---|---|---|---|
| quanto ho speso di luce nel 2026 rispetto al 2025? | 19 s | 4, 498 | schema, somma ×2, consegna | giusta: 97,20 contro 84,50, risparmio 12,70 |
| quali garanzie ho e quando scadono, e di cosa? | 30 s | 7, 752 | schema, trova, vicini ×2, trova, documenti, consegna | giusta: lavatrice Candor LV800, 12 marzo 2027 |
| quali documenti scadono entro la fine del 2026 e quanto devo pagare in tutto? | 56 s | 4, 1 712 | schema, trova, vicini ×4, consegna | giusta: acqua, luce, gas, 226,61 euro |

3 su 3, ma il totale della terza l'ha sommato il modello (giusto qui; `grafo_somma` con un
periodo l'avrebbe dato pronto) e la scadenza della polizza (fine validità, non un pagamento)
non l'ha citata. Un primo giro con il lavoro senza persona (un errore della misura) non vedeva
nessun documento, come deve: lì una domanda ha fatto girare il ragionamento per 16 692 token e
401 s prima di arrendersi senza risposta. Il tetto per passata degli agenti (metà del contesto)
lo ferma, ma un tetto più basso per le ricerche sui documenti sarebbe meglio.

## 10. Limiti e prossimi passi

- **Errori di cifra dell'OCR** non si vedono: il controllo contro il testo verifica che il
  modello non inventi, non che l'OCR abbia letto giusto («445586»). Rimedio possibile: per i
  codici, una seconda lettura del ritaglio o il confronto tra due documenti.
- **Tabelle lunghe** (estratti conto, bollette con decine di righe): si leggono le prime 12
  pagine e i primi 12 000 caratteri (tre quarti dall'inizio, un quarto dalla fine); le voci di
  dettaglio non entrano nel grafo, solo i totali.
- **HEIC** (foto degli iPhone) non si legge: serve `pillow-heif` (nativo), da verificare su ARM.
  Scrittura a mano non provata.
- Due persone con lo stesso nome e senza codice fiscale diventano una sola; il collegamento ai
  profili è esplicito proprio per questo.
- Le relazioni nuove (`rinnova` tra un rinnovo e la polizza vecchia, il condominio di un
  immobile) vanno scritte in `tipi.nel_grafo`: lo schema le regge già.
- Il risultato di una ricerca delegata è un file Word in `agenti_risultati`, cartella comune:
  per questo l'agente non vede i documenti sensibili.
- L'agente a volte fa da sé le somme invece di chiederle a `grafo_somma`; un ragionamento
  senza dati può girare a lungo (§9).
- Come arrivano i documenti nella cartella della DGX (cartella condivisa, Syncthing,
  scansione dal telefono) non è ancora deciso.
