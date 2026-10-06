# Biblioteca offline per Calliope — fonti, spazio e strategia di ricerca

*Ricerca svolta da un agente il 21 settembre 2026 per la decisione B di docs/visione.md.*

Legenda dell'affidabilità dei dati, usata in tutto il documento:

- **[L]** letto oggi dal listing ufficiale (`download.kiwix.org`, mirror `ftp.fau.de/kiwix`, catalogo OPDS `library.kiwix.org`, PyPI, API GitHub, `dumps.wikimedia.org`, ecc.).
- **[M]** misurato oggi su questo portatile (RTX 5070 Laptop 8 GB, Windows 11 x64, Python 3.14.6, Ollama con `bge-m3`).
- **[S]** stima mia, ricavata dai dati [L] e [M]: da verificare.
- **[W]** letto sul web da fonte secondaria (pagina di progetto, blog, riassunto di ricerca): plausibile ma non verificato a fondo.

Nota sulle unità: nei listing di Kiwix "G" significa GiB. Esempio: `wikipedia_it_all_maxi` è "30G" nel listing e 31,79 GB (decimali) nel catalogo OPDS.

---

## 0. Sintesi

1. **Kiwix/ZIM è la base giusta.** Tutta la Wikipedia italiana senza immagini sta in **8,4 GB** (agosto 2026), la versione "solo introduzioni + infobox" in **2,3 GB**. Una biblioteca italiana molto ricca (Wikipedia, Wikizionario, Wikisource, Wikibooks, Wikiquote, Wikivoyage, Wikiversità, Vikidia, WikiMed, Gutenberg) sta in **circa 16 GB**.
2. **La ricerca full-text dentro gli ZIM funziona da Python su Windows x64**, in italiano (stemming Snowball, stopword, accenti normalizzati) e costa **2–7 ms a query** [M]. `python-libzim 3.13.0` (7 settembre 2026) ha wheel per Windows x64 ma **non per Windows ARM64**.
3. **La sola ricerca full-text non basta**: trova quasi sempre la voce giusta fra le prime 5–8, ma non sempre per prima, e le voci sono lunghe (300–800 KB di HTML). Serve un secondo passo che scelga il *paragrafo*.
4. **Embeddings di tutto: fattibili ma costosi.** Wikipedia italiana = 1.987.588 voci, 1,11 miliardi di parole, circa 10–11 milioni di paragrafi. Con `bge-m3` via Ollama ho misurato **~56 paragrafi/s**: l'indicizzazione completa richiede **~2,3 giorni di GPU** e 11–45 GB di indice. Embeddings delle **sole introduzioni** (1,99 milioni di vettori): ~10 ore e ~2 GB (int8).
5. **Strategia raccomandata: ibrida (c).** Parole chiave → Xapian (ZIM mini + nopic) → lettura di 6–8 voci → prefiltro lessicale dei paragrafi → rerank con `bge-m3` di ~20 paragrafi. Prototipo misurato: **0,41–0,51 s in tutto** in condizioni normali, quindi dentro il budget di 1 s. Ho però visto picchi di 3–6 s, quasi certamente per contesa della GPU con altri modelli in Ollama: serve un timeout con ripiego sull'ordine lessicale.
6. **Per Windows su ARM** il punto debole è `libzim`. Tre vie d'uscita, tutte compatibili con il principio "moduli sostituibili": servizio separato x64 in emulazione, WSL2 (esistono wheel Linux aarch64), oppure estrarre una volta il testo in **SQLite FTS5** (solo libreria standard di Python; estrazione misurata a ~400 voci/s).

---

## 1. Kiwix / file ZIM: catalogo verificato

Tutti i dati di questa sezione sono **[L]**, letti il 21/09/2026 da `download.kiwix.org/zim/...` e dal mirror `ftp.fau.de/kiwix/zim/...`. La data è quella nel nome del file (mese dello snapshot).

### 1.1 Varianti: maxi, nopic, mini

| Variante | Contenuto | Uso per Calliope |
|---|---|---|
| **maxi** | voci complete con immagini | inutile per la voce; utile solo se un giorno ci sarà uno schermo |
| **nopic** | voci complete senza immagini (~75% in meno) | **la base della biblioteca** |
| **mini** | solo introduzione + infobox (~95% in meno) | **ottima per risposte vocali brevi**: ha l'indice full-text [M], la voce "Monte Bianco" pesa 16 KB invece di 327 KB e la prima frase contiene già l'altitudine |
| **top** | selezione delle voci più importanti (it: 193.819 voci) | utile per prototipi e test |

### 1.2 Wikipedia

| File | Dimensione | Snapshot | Versione precedente |
|---|---|---|---|
| `wikipedia_it_all_maxi` | 30 G | 2026-08 | 2026-02 (28 G) |
| `wikipedia_it_all_nopic` | **8,4 G** | 2026-08 | 2026-05 (8,3 G) |
| `wikipedia_it_all_mini` | **2,3 G** | 2026-08 | 2026-05 (2,2 G) |
| `wikipedia_it_top_maxi` / `nopic` / `mini` | 4,0 G / 836 M / 107 M | 2026-07 | 2026-04 |
| `wikipedia_it_medicine_maxi` / `nopic` (WikiMed italiano, 33.071 voci) | 379 M / 92 M | 2026-07 | 2026-04 |
| `wikipedia_en_all_maxi` | **119 G** | 2026-08 | 2026-02 (115 G) |
| `wikipedia_en_all_nopic` | **49 G** | 2026-06 | 2026-03 (48 G) |
| `wikipedia_en_all_mini` | 13 G | 2026-09 | 2026-06 (12 G) |
| `wikipedia_en_top1m_maxi` / `nopic` / `mini` | 46 G / 16 G / 2,8 G | 2026-04 | 2026-01 |
| `wikipedia_en_top_maxi` / `nopic` / `mini` | 6,5 G / 2,6 G / 283 M | 2026-09 | 2026-06 |
| `wikipedia_en_simple_all_maxi` / `nopic` / `mini` | 3,2 G / 937 M / 447 M | 2026-05 | — |
| `wikipedia_en_medicine_maxi` / `nopic` / `mini` | 2,1 G / 822 M / 155 M | 2026-04 | 2026-01 |
| `wikipedia_en_100` | 318 M | 2026-08 | 2026-07 |

Il catalogo OPDS riporta per `wikipedia_it_all` 3.110.33x "articoli": il numero comprende i redirect. Le voci vere sono 1.987.588 (API di it.wikipedia, oggi).

### 1.3 Progetti fratelli

| Progetto | Italiano (nopic / maxi) | Snapshot it | Inglese (nopic / maxi) | Snapshot en |
|---|---|---|---|---|
| Wikizionario | 384 M (solo nopic, 768.471 lemmi) | 2026-08 | 8,5 G (solo nopic) | 2026-08 |
| Wikisource | 1,8 G / 2,6 G (751.718 pagine) | 2026-03 | 11 G / 18 G | 2026-08 / 2026-05 |
| Wikibooks | 1,6 G / 2,0 G | 2026-07 | 3,3 G / 5,8 G | 2026-04 |
| Wikiquote | 169 M / 554 M | 2026-07 | 315 M / 927 M | 2026-07 |
| Wikivoyage | 105 M / 571 M | 2026-09 | 260 M / 1,0 G | 2026-09 |
| Wikiversità | 41 M / 234 M | 2026-01 | 1,5 G / 2,3 G | 2026-08 / 2026-05 |
| Vikidia (enciclopedia per ragazzi) | 14 M / 104 M (12.208 voci) | 2026-09 | 10 M / 74 M | 2026-09 |

### 1.4 Libri: Project Gutenberg

| File | Dimensione | Snapshot |
|---|---|---|
| `gutenberg_it_all` (1.453 libri) | 1,0 G | 2026-01 (precedente 2025-10) |
| `gutenberg_en_all` | **206 G** | 2025-11 (il precedente, 2023-08, era 72 G) |
| `gutenberg_mul_all` (tutte le lingue, 100.909 libri) | 253 GB | 2025-11 |
| `gutenberg_en_lcc-*` (per classe della Library of Congress) | da 13 M a 37 G ciascuno | 2026-03 |

Classi utili come "manuali": `lcc-q` scienze 17 G, `lcc-t` tecnologia 12 G, `lcc-s` agricoltura 4,2 G, `lcc-r` medicina 1,9 G.

### 1.5 Stack Exchange (licenza CC BY-SA)

Snapshot 2026-08 per quasi tutti i siti (precedente 2026-02): cadenza circa semestrale.

| Sito | Dim. | Sito | Dim. |
|---|---|---|---|
| stackoverflow.com | **107 G** (2026-07) | math | 6,9 G |
| tex | 4,2 G | electronics | 3,9 G |
| superuser | 3,7 G | askubuntu | 2,6 G |
| blender | 2,6 G | gis | 2,0 G |
| diy (fai da te) | 1,9 G | physics | 1,7 G |
| serverfault | 1,5 G | stats | 1,5 G |
| unix | 1,2 G | apple | 1,1 G |
| gardening | 882 M | mathoverflow | 808 M |
| worldbuilding | 797 M | english | 730 M |
| dba | 669 M | aviation | 482 M |
| bicycles | 467 M | travel | 439 M |
| photo | 431 M | security | 420 M |
| biology | 403 M | chemistry | 397 M |
| space | 380 M | mechanics | 323 M |
| music | 323 M | history | 304 M |
| raspberrypi | 285 M | arduino | 247 M |
| money | 242 M | **cooking** | 226 M |
| astronomy | 187 M | law | 176 M |
| skeptics | 174 M | outdoors | 136 M |
| earthscience | 126 M | woodworking | 100 M |
| pets | 83 M | medicalsciences | 58 M |
| parenting | 57 M | lifehacks | 46 M |
| **italian** (lingua italiana, multilingue) | 24 M | | |

Totale dell'intera cartella `stack_exchange` (181 siti, ultime versioni): **178,5 GB**, di cui 107 di Stack Overflow.

### 1.6 Medicina, primo soccorso, sopravvivenza

| File | Dim. | Snapshot | Note |
|---|---|---|---|
| `wikipedia_it_medicine_maxi` (WikiMed it) | 379 M | 2026-07 | **in italiano** |
| `wikipedia_en_medicine_maxi` | 2,1 G | 2026-04 | |
| `mdwiki_en_all` | 10 G | 2025-11 | enciclopedia medica di Wiki Project Med |
| `wikem_en_all_maxi` (medicina d'urgenza) | 357 M | 2026-07 | |
| `medlineplus.gov_en_all` | 1,8 G | 2025-01 | NIH, pubblico dominio USA |
| `nhs.uk_en_medicines` | 15 M | 2026-09 | schede dei farmaci |
| `wwwnc.cdc.gov_en_all` | 170 M | 2024-11 | |
| `zimgit-medicine_en` | 67 M | 2024-08 | raccolta di manuali di primo soccorso |
| `zimgit-post-disaster_en` | 615 M | 2024-05 | |
| `zimgit-water_en` / `zimgit-knots_en` / `zimgit-food-preparation_en` | 20 M / 27 M / 93 M | 2024-08 / 2025-04 | |
| `irp.fas.org_en_military-medicine` | 72 M | 2026-05 | |
| `www.ready.gov_en` | 2,3 G | 2024-12 | protezione civile USA |
| `trueprepper.com_en_all` | 1,3 G | 2026-05 | |
| `survivorlibrary.com_en_all` | **205 G** | 2026-09 | scansioni PDF di manuali storici |
| `appropedia_en_all_maxi` / `energypedia_en_all_maxi` | 555 M / 763 M | 2026-02 / 2026-06 | tecnologie appropriate, energia |
| `solar.lowtechmagazine.com_mul_all` | 0,7 GB | 2025-01 | |

In italiano su questi temi esiste solo WikiMed. Tutto il resto è in inglese.

### 1.7 iFixit, Khan Academy, TED, corsi, mappe, altro

| File | Dim. | Snapshot | Note |
|---|---|---|---|
| `ifixit_it_all` (105.101 pagine) | 3,4 G | 2026-03 (prec. 2025-06) | **in italiano**, CC BY-NC-SA |
| `ifixit_en_all` | 3,3 G | 2025-12 | |
| `khanacademy_en_all` | **168 G** | **2023-03** | fermo da tre anni; esistono solo en, es (150 G), fr (94 G); **niente italiano**; sono video |
| `ted_mul_all` | 85 G | 2026-09 | video con sottotitoli multilingue; esistono anche ~350 ZIM per argomento |
| `libretexts.org_en_*` (13 ZIM: chem, bio, math, phys, med, eng…) | 16,1 GB in tutto | 2025-01 / 2026-07 | manuali universitari aperti |
| `devdocs_en_*` (231 ZIM) | 0,6 GB in tutto | 2026 | documentazione per programmatori |
| `freecodecamp_*` (45 ZIM, anche `_it_`) | 0,3 GB in tutto | 2026-08 | |
| `phet_*` | 7,6 GB in tutto | — | simulazioni interattive: inutili per la voce |
| **`maps_en_italy`** | 2,5 G | 2026-06 | **novità 2026**: mappe OSM in ZIM (progetto `openzim/maps`), con ricerca delle città |
| `maps_en_europe` / `maps_en_all` | 25 G / 72 G | 2026-08 / 2026-06 | |
| `based.cooking` / `foss.cooking` / `publicdomainrecipes.com` | 15 M / 23 M / 16 M | 2026-05…08 | ricettari liberi (inglese) |
| `scoutwiki.org_it_all` | 16 M | 2026-07 | in italiano |
| `phzh_core-italian-one_it` | 79 M | 2022-01 | corso di italiano per stranieri |

**Totale dell'intero catalogo Kiwix** (tutte le lingue, tutte le varianti, solo le ultime versioni): **circa 5,2 TB** [L, somma calcolata da me sui listing]. Le cartelle più grandi: wikipedia 1,6 TB, gutenberg 680 GB, ted 632 GB, other 632 GB, zimit 572 GB, maps 309 GB, videos 265 GB, stack_exchange 179 GB, wikisource 166 GB. La somma conta più volte gli stessi contenuti (maxi+nopic+mini, raccolte tematiche di TED e Gutenberg).

### 1.8 Frequenza e modalità di aggiornamento

Cadenze osservate nei listing [L]:

| Contenuto | Cadenza osservata |
|---|---|
| Wikipedia it nopic / mini | trimestrale (2026-05 → 2026-08) |
| Wikipedia it maxi, en maxi | semestrale (2026-02 → 2026-08) |
| Wikipedia en nopic | trimestrale (2026-03 → 2026-06) |
| Progetti fratelli | circa trimestrale; Wikisource e Wikiversità it più lenti |
| Stack Exchange | semestrale |
| Gutenberg, iFixit | irregolare (3–9 mesi) |
| Khan Academy | fermo al 2023 |

- **L'aggiornamento incrementale non esiste.** La FAQ ufficiale di Kiwix dice: «Incremental updates for ZIM files are not currently available, but this feature is being explored for the future». Gli strumenti `zimdiff`/`zimpatch` esistono dal 2013 ma non sono mai entrati nella distribuzione. Ogni aggiornamento è un nuovo download completo del file.
- Il server conserva le **ultime due versioni** di ogni ZIM; il nome contiene `_AAAA-MM`.
- Per sapere se c'è una versione nuova: catalogo OPDS `https://library.kiwix.org/catalog/v2/entries?lang=ita&count=-1` (o `?name=wikipedia_it_all`), che dà nome, variante, data, dimensione in byte e URL. Uno script di aggiornamento in Python è di poche decine di righe: leggi il catalogo, confronta la data, scarica con ripresa (`Range`) da un mirror, verifica, sostituisci, cancella il vecchio.
- Strumenti esistenti: `jojo2357/kiwix-zim-updater` (bash, solo Linux); **Zimi** (vedi §5) ha l'aggiornamento automatico integrato e gira su Windows.
- Conseguenza per gli indici derivati (FTS5, embeddings): vanno rigenerati a ogni nuovo ZIM. Conviene identificare ogni paragrafo con un hash del testo e ricalcolare gli embeddings solo dei paragrafi cambiati.

### 1.9 Velocità di download [M]

Da questa rete: `download.kiwix.org` diretto **~0,5 MB/s** (il primo tentativo è andato in timeout), mirror `ftp.fau.de` **~5–6 MB/s**, `mirror.accum.se` ~5 MB/s, `dumps.wikimedia.org/other/kiwix` ~4,7 MB/s. A 5 MB/s: Wikipedia it nopic in ~30 minuti, en nopic in ~3 ore, en maxi in ~7 ore. Usare i mirror (o i torrent).

---

## 2. Accesso da Python

### 2.1 python-libzim

| Voce | Stato al 21/09/2026 |
|---|---|
| Versione | **3.13.0** del 2026-09-07, basata su libzim 9.8.2 [L: PyPI, changelog] |
| Python | 3.10 – 3.14 |
| Wheel Windows x64 (`win_amd64`) | **sì** (cp310…cp314, ~16 MB, DLL di libzim/ICU/Xapian incluse); supporto Windows dalla 3.5.0 (2024) |
| Wheel Windows ARM64 (`win_arm64`) | **no** |
| Wheel Linux aarch64 (manylinux e musl) | sì → utilizzabile in WSL2 sullo Spark |
| Wheel macOS arm64 | sì (quindi il codice C++ compila su ARM; manca solo la build Windows ARM64) |
| Licenza | GPL-3.0 (libzim GPL-2.0): conta solo se Calliope venisse distribuita; usando un servizio HTTP separato il problema non si pone |
| Ritmo di sviluppo | 5 rilasci nel 2026 (3.9 marzo, 3.10 maggio, 3.11 e 3.12 luglio, 3.13 settembre) |

API essenziale: `Archive(path)`, `archive.get_entry_by_path(p).get_item().content`, `Searcher(archive).search(Query().set_query(q)).getResults(0, n)`, `SuggestionSearcher(archive).suggest(prefisso)`, `archive.has_fulltext_index`, `archive.get_metadata("Language")`.

### 2.2 Prove fatte oggi sul portatile [M]

Ambiente: venv temporaneo con `libzim 3.13.0` su Python 3.14.6, Windows 11 x64. File: `wikipedia_it_top_nopic_2026-07.zim` (836 MB, 193.819 voci), `wikipedia_it_top_mini_2026-07.zim` (107 MB), `vikidia_it_all_nopic_2026-09.zim` (14 MB).

| Prova | Risultato |
|---|---|
| Installazione `pip install libzim` e import di `libzim.search` | funziona senza compilare nulla |
| Apertura dell'archivio | 5–12 ms |
| `has_fulltext_index` su nopic, mini e Vikidia | `True` per tutti (metadato `Language = ita`) |
| Ricerca full-text, 20 query diverse, primi 10 risultati | **mediana 2,1 ms, massimo 6,4 ms** (cache del file calda); prima query dopo l'apertura: 21 ms |
| Lettura di una voce (decompressione) | 1–10 ms (voci da 30–800 KB di HTML) |
| Suggerimenti sui titoli (`suggest "vulc"`) | 0–1 ms |
| Stemming italiano | attivo: `terremoto`/`terremoti` e `mangiare`/`mangiavano` danno gli stessi risultati; non perfetto (`vulcano`/`vulcani` differiscono) |
| Accenti | normalizzati: `città` = `citta` |
| Stopword | gestite: `il terremoto` ≈ `terremoto` |
| Operatore implicito | **AND**: una parola che non compare azzera i risultati (`zzzxqy Roma` → 0). La sintassi `OR` non è interpretata |
| Estrazione del testo (regex sui `<p>`) | **~400 voci/s** su un solo core, con voci lunghe (17,5 paragrafi per voce) |

Conseguenze pratiche:

1. **La domanda parlata va ridotta a parole chiave** prima della ricerca (basta togliere stopword e interrogativi: non serve una chiamata all'LLM). Con l'AND implicito, se la query dà pochi risultati conviene riprovare togliendo un termine alla volta: a 2 ms l'una, dieci query costano nulla.
2. **La voce giusta è quasi sempre nelle prime 5–8, non sempre prima.** Esempi reali sul file nopic: «quanto è alto il Monte Bianco» → Monte Bianco quinto; «altezza Monte Bianco» → assente dai primi 5; «capitale Australia» → Canberra seconda. Sul file **mini** le stesse query vanno meglio («Monte Bianco altezza» → Monte Bianco primo), perché l'indice contiene solo le introduzioni.
3. Le voci sono enormi rispetto al contesto utile per un LLM da 4–8B: serve scegliere i paragrafi (vedi §4).

Non misurato: latenza a cache fredda sui file grandi (8,4 GB e 49 GB). La issue #617 di libzim riportava, prima della 9.4.0, 3,7 s a freddo e 1,5 s a caldo su archivi molto grandi; dalla 9.4.0 (novembre 2025) gli indici vengono precaricati. Va misurato col file vero: è la prima cosa da fare dopo il download.

### 2.3 kiwix-serve (alternativa HTTP)

| Voce | Stato |
|---|---|
| Ultima versione | 3.8.2 del 2026-03-02 [L] |
| Build Windows x64 | **3.8.1** (2025-12-02, zip da 17 MB) + nightly `kiwix-tools_win-x86_64-2026-09-21.zip`; la 3.8.2 non ha lo zip per Windows |
| Build Windows ARM64 | **no** |
| Build Linux aarch64 / armv8 / musl, macOS arm64 | sì |
| Licenza | GPL-3.0 |

API HTTP (dalla documentazione ufficiale nel repository):

- `GET /search?pattern=TESTO&books.name=NOME_ZIM&format=xml&pageLength=N&start=S` — risultati con titolo, link e **snippet**; `books.filter.lang=ita` cerca in **tutti gli ZIM italiani insieme** (ricerca multi-ZIM, limitabile con `--searchLimit`).
- `GET /suggest?content=NOME_ZIM&term=PREFISSO&count=N` — suggerimenti sui titoli, in JSON.
- `GET /raw/NOME_ZIM/content/PERCORSO` — contenuto grezzo della voce, senza riscritture.
- `GET /catalog/v2/entries` — catalogo OPDS locale.

Latenza: stessa libreria (libzim/Xapian) più il giro HTTP locale, quindi pochi millisecondi in più [S]; non l'ho misurata. Vantaggi: processo separato (isolamento della GPL, emulazione x64 sullo Spark, riavvio indipendente), ricerca multi-ZIM già pronta. Svantaggi: un binario in più da gestire, XML da analizzare, nessun controllo sul ranking.

### 2.4 Windows su ARM (RTX Spark): che cosa regge

| Componente | `win_arm64` oggi [L: PyPI] | Note |
|---|---|---|
| `libzim` 3.13.0 | **no** | x64 in emulazione, WSL2, oppure via FTS5 (sotto) |
| kiwix-serve | **no** | idem |
| `sqlite3` della libreria standard con **FTS5** | sì (fa parte di CPython; verificato qui: `ENABLE_FTS5`, SQLite 3.50.4) | zero dipendenze |
| `numpy` 2.5.3 | **sì** | |
| `usearch` 2.26.2 | **sì** | |
| `faiss-cpu` 1.15.1 | **sì** | |
| `duckdb` 1.5.5 | **sì** | |
| `onnxruntime` 1.30.0 | **sì** | |
| `PyStemmer` 3.1.0 (Snowball) | **sì**; `snowballstemmer` è puro Python | |
| `lxml`, `selectolax`, `zstandard` | **sì** | |
| `sqlite-vec` 0.1.9 | no (solo `win_amd64`), ma è un singolo file C senza dipendenze | |
| `lancedb` 0.38 / `pylance` | no (solo `win_amd64`; la 0.39.0 di quattro giorni fa non ha ancora wheel Windows) | Rust |
| `chromadb` 1.5.9 | no (solo `win_amd64`) | |
| `tantivy` 0.26.2 | no (solo `win_amd64`) | Rust, ha lo stemmer italiano |
| `torch` 2.14.0 (PyPI) | no | NVIDIA indica un proprio repository per Windows on Arm [W] |
| `ctranslate2` 4.8.2 (faster-whisper) | no | fuori tema, ma riguarda lo STT |

Tre strade per la biblioteca sullo Spark:

1. **Servizio x64 separato in emulazione.** NVIDIA stessa scrive «Run existing x86 software without modification» e «Start with emulation, then port components» [W]. La ricerca negli ZIM è lavoro di I/O e CPU leggera: un Python x64 con `libzim`, o `kiwix-serve.exe` x64, in un processo a parte che espone HTTP locale. Non verificato su hardware reale.
2. **WSL2** con le wheel `manylinux aarch64` di `libzim` o con kiwix-serve `linux-aarch64`.
3. **Niente libzim a runtime**: si estrae il testo una volta (sul portatile x64, o ovunque) in un database **SQLite FTS5** e a runtime si usa solo `sqlite3`. Misure di oggi: estrazione ~400 voci/s (tutta la Wikipedia italiana in meno di 2 ore su un core), database ≈ 2 volte il testo (71 MB di testo → 144 MB), quindi ~14 GB per Wikipedia it [S]. FTS5 non ha lo stemmer italiano: o si indicizza una colonna già passata da Snowball, o si accetta `unicode61 remove_diacritics` con ricerca per prefisso. Latenza a piena scala non misurata (sul campione da 140.000 paragrafi: 0,3 ms).

Qualunque strada si scelga, la biblioteca deve stare dietro un'interfaccia minima, in linea con il principio 2 del progetto: `cerca(domanda, k) → [Passaggio(testo, titolo, fonte, punteggio)]`.

---

## 3. Altre fonti offline oltre a Kiwix

### 3.1 Dump di Wikipedia e Wikidata [L: dumps.wikimedia.org, 2–18 settembre 2026]

| Fonte | Dimensione | Licenza | Commento |
|---|---|---|---|
| `itwiki-latest-pages-articles.xml.bz2` | 4,24 GB | CC BY-SA 4.0 | wikitesto grezzo: va ripulito da template e tabelle (mwparserfromhell, wikiextractor). Lo ZIM nopic dà HTML già renderizzato: **meglio lo ZIM** |
| `itwiki-…-multistream.xml.bz2` | 4,44 GB | idem | accesso casuale per voce |
| `enwiki-latest-pages-articles.xml.bz2` | 25,7 GB | idem | |
| Wikidata `latest-all.json.bz2` | **103 GB** | CC0 | tutto il grafo; pesantissimo da caricare |
| Wikidata `latest-truthy.nt.bz2` | 43,5 GB | CC0 | solo le asserzioni "vere"; serve un triple store (QLever, Oxigraph) |
| Hugging Face `wikimedia/wikipedia` | it: 1,83 M voci | CC BY-SA | testo pulito ma fermo al **2023-11** |
| Hugging Face `wikimedia/structured-wikipedia` | 44 GiB | CC BY-SA 4.0 | abstract + infobox + sezioni già strutturati, snapshot 2026-05, ma **solo inglese e francese** |
| Hugging Face `Upstash/wikipedia-2024-06-bge-m3` | 633 GB in tutto; **italiano: ~10,1 milioni di paragrafi già vettorizzati con bge-m3 (1024 dim.)**, ~44 GB [S] | Apache-2.0 | scorciatoia per saltare l'indicizzazione, ma è del **giugno 2024** e va verificata la compatibilità con il `bge-m3` GGUF di Ollama |

Wikidata è la fonte ideale per i fatti secchi (date, altitudini, popolazioni, capitali), ma il costo d'ingresso è alto. Per cominciare, l'infobox contenuto nello ZIM **mini** copre gran parte di quei fatti.

### 3.2 OpenStreetMap e geocodifica ("dov'è…")

| Soluzione | Dimensione | Dipendenze | Giudizio |
|---|---|---|---|
| **GeoNames** `allCountries.zip` | 402 MB (`IT.zip` 4,2 MB; `cities500.zip` 13 MB; `alternateNamesV2.zip` 195 MB con i nomi in italiano) — aggiornati ogni giorno [L] | nessuna: TSV → SQLite | **prima scelta**: città, monti, laghi, fiumi con coordinate, popolazione, altitudine. CC BY 4.0 |
| **Photon, dump JSON dell'Italia** `photon-dump-italy-1.0-latest.jsonl.zst` | **595 MB**, aggiornato il 2026-09-21 [L] | per usarlo con Photon: Java 21+; ma il JSONL si può caricare direttamente in SQLite FTS5 | **seconda scelta**: indirizzi, vie, punti d'interesse. Dati ODbL |
| Photon, database pronti | pianeta 62,6 GB (v1.x, 2026-09-15), Europa 31,8 GB; il DB pronto per la sola Italia è fermo al 2025-07 (3 GB, formato vecchio) [L] | Java 21+, OpenSearch integrato | server HTTP completo, tollerante agli errori di battitura; pesante |
| Nominatim | decine di GB per l'Italia [non verificato] | PostgreSQL + PostGIS, non nativo su Windows | **sconsigliato** per questo progetto |
| Geofabrik `italy-latest.osm.pbf` | 2,1 GB, aggiornato ogni giorno [L] | serve un programma che lo interpreti | dato grezzo; utile solo per routing (GraphHopper, Valhalla) |
| Kiwix `maps_en_italy` | 2,5 G | libzim | mappa da guardare, con ricerca delle città; per la voce aggiunge poco |
| Coordinate dentro Wikipedia | già negli ZIM | — | per «dov'è X» spesso basta l'introduzione della voce |

### 3.3 Biblioteche italiane, dizionari, ricettari

| Fonte | Dimensione | Licenza | Note |
|---|---|---|---|
| **Wikisource it** (ZIM) | 1,8 G | CC BY-SA / pubblico dominio | classici, Costituzione, testi storici; già indicizzato |
| **Gutenberg it** (ZIM) | 1,0 G | pubblico dominio (USA) | 1.453 libri |
| **Liber Liber** (progetto Manuzio) | ~5.000 titoli [W]; l'intero catalogo è scaricabile «con archivi ISO» da `liberliber.it/prodotto/download-libri/` | testi in pubblico dominio; impaginazione e copertine CC BY-NC-SA 4.0 [W] | **non ho potuto verificare** dimensione, formato e condizioni (la pagina è una scheda prodotto: probabile donazione). Va trasformato in testo indicizzabile a mano |
| **Wikizionario it** (ZIM) | 384 M | CC BY-SA | definizioni, etimologie, sinonimi |
| **kaikki.org** (Wiktextract) | lemmi italiani dal Wikizionario inglese: 589.335 forme, JSONL 728 MB; estrazione del Wikizionario *italiano*: JSONL 490 MB (38 MB compresso). Estratti il 2026-09-20 [L] | quella di Wiktionary (CC BY-SA), non indicata esplicitamente nella pagina | **dizionario strutturato** (JSON: definizioni, flessioni, pronuncia IPA, traduzioni): ideale per un tool `definisci(parola)` senza passare dalla ricerca |
| Ricette | Wikibooks it (dentro 1,6 G) con il «Libro di cucina»; Artusi in Wikisource/Gutenberg/Liber Liber; `cooking.stackexchange` 226 M; ricettari liberi 15–23 M (inglese) | varie, libere | i grandi siti italiani di ricette sono protetti da copyright |
| Treccani, De Mauro, Zanichelli | — | **protetti**: non scaricabili | |

### 3.4 Dati meteo-climatici storici

| Fonte | Licenza | Dimensione / forma | Note |
|---|---|---|---|
| **Meteostat** (stazioni, serie giornaliere e orarie, normali climatiche) | **CC BY 4.0** [L: pagina della licenza] | file per stazione (CSV/Parquet); per le stazioni italiane pochi MB–centinaia di MB [S] | libreria Python; la più semplice per «che tempo fa di solito a Palermo in ottobre» |
| **Open-Meteo** (ERA5 dal 1940 a ~25 km, ERA5-Land dal 1950 a ~9 km) | dati CC BY 4.0; il server si può ospitare in casa [W] | una variabile ERA5-Land ≈ 9 GiB; dati aperti su AWS [W] | API locale identica a quella online: ottima come tool «con o senza rete» |
| NOAA GHCN-Daily | pubblico dominio USA | non verificata | |
| Copernicus ERA5 originale | licenza Copernicus | centinaia di GB–TB | eccessivo |

Il meteo *in tempo reale* resta un tool che richiede internet (coerente con docs/visione.md): offline si può rispondere solo con la climatologia.

---

## 4. Strategia di recupero

### 4.1 I numeri di base

| Grandezza | Valore | Fonte |
|---|---|---|
| Voci di Wikipedia in italiano | 1.987.588 | API it.wikipedia, oggi [L] |
| Parole | 1.112.395.433 | idem [L] |
| Paragrafi ≥ 100 caratteri | ~10,1 milioni a giugno 2024 (dataset Upstash) → ~10,5–11 milioni oggi | [L] + [S] |
| Wikipedia in inglese | 7.242.581 voci, 5,29 miliardi di parole, ~47–50 milioni di paragrafi | [L] + [S] |
| `bge-m3` via Ollama su questa GPU: una query | **21–33 ms** | [M] |
| `bge-m3` via Ollama: throughput in batch (paragrafi da ~630 caratteri, ~85–170 token) | **52–58 paragrafi/s**, stabile da 16 a 1024 paragrafi | [M] |
| `bge-m3` via Ollama: 20 paragrafi in una richiesta | **0,29–0,47 s** (costo fisso di ~0,28 s per richiesta) | [M] |
| VRAM di `bge-m3` in Ollama | 0,66 GB (`ollama ps`) | [M] |
| Riferimento esterno: bge-m3 con TEI, passaggi da 512 token | RTX A5000 ~190 testi/s, RTX 6000 Ada ~275, H100 ~1.240 | [W: benchmark RunPod] |

### 4.2 Confronto

| | (a) Solo full-text | (b) Embeddings di tutto | (c) Ibrido: full-text + rerank al volo |
|---|---|---|---|
| Preparazione | nessuna: l'indice Xapian è già nello ZIM | **~2,3 giorni di GPU** via Ollama (11 M ÷ 56/s ≈ 55 ore); ~14–18 ore con un runtime ottimizzato (sentence-transformers/TEI fp16) [S]; GPU occupata: Calliope ferma o degradata | nessuna |
| Spazio in più | 0 | 11 M × 1024 dim.: fp32 **45 GB**, fp16 22,5 GB, int8 **11 GB**, binario 1,4 GB; più grafo HNSW ~2 GB; più il testo dei paragrafi (~7 GB) o i puntatori allo ZIM | 0 (cache facoltativa) |
| RAM a runtime | trascurabile | con HNSW in memoria: 13+ GB in int8 su 32 GB; meno con indice su disco o mappato in memoria | trascurabile |
| Latenza di ricerca | 2–7 ms + lettura 30–40 ms | query 25 ms + ricerca ANN 5–30 ms ≈ **50 ms** [S] | **0,41–0,51 s** misurati (7 + 35 + 370–470 ms) |
| Qualità | buona sui nomi propri, debole sulle parafrasi («di cosa è fatta» ≠ «composizione»); restituisce voci, non paragrafi | la migliore sulle parafrasi e sulle domande vaghe; debole su nomi rari e numeri | buona: la parte lessicale trova l'entità, gli embeddings scelgono il paragrafo |
| Aggiornamento dello ZIM | gratis | va rifatto (incrementale solo con hash dei paragrafi) | gratis |
| Inglese (49 GB nopic) | gratis | ~10 giorni di GPU e ~50–100 GB: **non sul portatile** | gratis |
| Windows ARM | dipende da libzim (vedi §2.4) | `usearch`/`faiss`/`numpy` hanno wheel ARM64 | come (a) |

**Variante intermedia consigliata per la fase 2 — embeddings delle sole introduzioni**: 1,99 milioni di vettori, **~10 ore** via Ollama, **2 GB** in int8 (4 GB in fp16, 250 MB in binario). Con un indice così piccolo non serve nemmeno un database vettoriale: un prodotto matrice-vettore con `numpy` su 2 GB di int8 richiede ~0,1–0,2 s su CPU [S]; con `usearch` pochi millisecondi. Dà la ricerca semantica "per argomento" (trova la voce giusta anche con parole diverse) e lascia al full-text e al rerank la scelta del paragrafo.

### 4.3 Prototipo ibrido misurato oggi [M]

Pipeline (script `e2e.py`, ~60 righe, nessuna dipendenza oltre a `libzim`):

```
domanda → togli stopword → Xapian su ZIM mini + ZIM nopic (6 voci ciascuno)
        → leggi le voci, estrai i paragrafi → prefiltro lessicale (20 paragrafi)
        → bge-m3: domanda + 20 paragrafi in una sola richiesta → coseno → primi 2–3
```

| Domanda | ricerca | lettura + prefiltro | embeddings | totale | Primo paragrafo |
|---|---|---|---|---|---|
| Chi era Giulio Cesare? | 2 ms | 40 ms | 470 ms | **511 ms** | corretto (incipit di «Gaio Giulio Cesare») |
| Perché il cielo è blu? | 2 ms | 30 ms | 374 ms | **407 ms** | corretto (diffusione della luce blu) |
| Quando è nato Dante Alighieri? | 3 ms | 40 ms | 393 ms | **436 ms** | corretto (Firenze, maggio–giugno 1265) |
| Di cosa è composta la Luna? | 2 ms | 40 ms | 369 ms | **411 ms** | parziale (regolite, da «Superficie della Luna») |
| Quanto è alto il Monte Bianco? | 7 ms | 29 ms | 6.092 ms | 6.127 ms | corretto (4.808 m, dalla voce «Alpi») — **picco** |
| Qual è la capitale dell'Australia? | 2 ms | 30 ms | 2.708 ms | 2.740 ms | **sbagliato** (Perth, «capitale dell'Australia Occidentale») — **picco** |
| Come si chiamano i protagonisti dei Promessi Sposi? | 2 ms | 31 ms | 2.979 ms | 3.012 ms | **insufficiente** (incipit generico della voce) — **picco** |

Che cosa insegna:

- **Il budget di 1 s è rispettato in condizioni normali** (0,4–0,5 s), e la ricerca vera e propria è trascurabile: il costo è tutto nel rerank.
- **I picchi di 3–6 s** non si sono ripetuti nelle prove isolate (stessa richiesta ×5: 334–352 ms). In quei minuti sul portatile giravano altre prove con Ollama: la causa più probabile è la **contesa della GPU o lo scambio di modelli in 8 GB di VRAM**, cioè esattamente lo scenario reale di Calliope (LLM + embedder + Whisper). Contromisure: tenere `bge-m3` sempre caricato (`keep_alive`, `OLLAMA_MAX_LOADED_MODELS ≥ 2`), **timeout di ~600 ms sul rerank con ripiego sull'ordine lessicale**, e in prospettiva un embedder più piccolo o su CPU. Con `qwen3:8b` (5,6 GB) + Whisper + `bge-m3` (0,66 GB) gli 8 GB non bastano; con un LLM da 4B sì.
- **5 risposte buone su 7 con un prototipo di un'ora.** I due errori indicano i miglioramenti da fare: (1) quando la domanda nomina un'entità («Australia»), risolvere il titolo con `SuggestionSearcher` e dare precedenza all'**introduzione e all'infobox di quella voce** (lo ZIM mini serve a questo: lì c'è «Capitale: Canberra»); (2) passare all'LLM **3 passaggi**, non 1; (3) prefiltro lessicale con un vero BM25 al posto del conteggio delle parole.
- **Soglia di astensione**: se il punteggio migliore è basso (nei test le risposte buone avevano coseno 0,70–0,81, quelle sbagliate o insufficienti 0,59–0,65: la soglia va tarata su un banco di prova più ampio) Calliope deve dire «non lo trovo nella biblioteca» invece di inventare. L'idea viene da `tensor-serve` (§5).
- **Cache**: salvare in SQLite gli embeddings dei paragrafi già calcolati (chiave: hash del testo). Le voci consultate più spesso diventano gratis, e la biblioteca "impara" senza un'indicizzazione preventiva.

### 4.4 Database vettoriali con poche dipendenze native

| Libreria | Versione [L] | `win_amd64` | `win_arm64` | Note |
|---|---|---|---|---|
| **numpy** (forza bruta) | 2.5.3 | sì | **sì** | basta fino a ~2 milioni di vettori int8; zero dipendenze nuove |
| **usearch** | 2.26.2 (2026-08-31) | sì | **sì** | HNSW in C++ header-only, quantizzazione f16/int8/binaria, indice su file mappato in memoria. **Prima scelta se serve un ANN** |
| faiss-cpu | 1.15.1 (2026-09-16) | sì | **sì** | completo ma più pesante |
| duckdb (+ estensione `vss`) | 1.5.5 | sì | **sì** | comodo se si vuole SQL; persistenza HNSW ancora sperimentale [non verificato] |
| sqlite-vec | 0.1.9 (2026-03-31) | sì | no (compilabile: un solo file C) | solo forza bruta: bene sotto ~1 milione di vettori |
| LanceDB | 0.38/0.39 | sì (0.38) | no | Rust, indice su disco IVF-PQ |
| Chroma | 1.5.9 | sì | no | |
| Qdrant | client 1.19.1 (puro Python) | server a parte | server: no | eccessivo per una casa |

Per la parte lessicale: SQLite **FTS5** (libreria standard), `bm25s` 0.3.11 (puro Python + numpy), `tantivy` 0.26.2 (Rust, stemmer italiano, niente ARM64), Xapian dentro gli ZIM.

---

## 5. Progetti esistenti da riusare

Dati da API GitHub e PyPI, oggi [L]; descrizioni dalle pagine dei progetti [W]. Nessuno è stato provato.

| Progetto | Stelle | Ultima attività | Licenza | Che cos'è | Riuso per Calliope |
|---|---|---|---|---|---|
| **cameronrye/openzim-mcp** | 133 | oggi; v3.3.4 del 2026-09-18 | MIT | server MCP in Python (≥ 3.12) sopra `libzim`. Modalità «semplice» con un solo tool `zim_query` pensato per modelli ≤ 13B; modalità avanzata con 8 tool (`zim_search`, `zim_get`, `zim_get_section`, `zim_browse`, `zim_metadata`, `zim_links`…). Trasporto stdio e **HTTP streamable**. Wheel puro Python | **Il candidato più serio** se la decisione C sceglie MCP come standard dei tool: la «bibliotecaria» potrebbe nascere come suo client. In ogni caso è un buon riferimento per `get_section` e per la ricerca multi-archivio. Nessuna ricerca semantica |
| **epheterson/Zimi** | 69 | oggi; v1.9.6 del 2026-09-19 | MIT | server moderno per ZIM in Python: **API REST JSON** (ricerca, lettura, suggerimenti, *chunking*), server MCP, ricerca su più ZIM, **catalogo e aggiornamento automatico degli ZIM**, app nativa Windows | **Da valutare come servizio già pronto**: risolve da solo download, aggiornamento e API. Dipende da `libzim` (e `libtorrent` per la condivisione) |
| mozanunal/llm-tools-kiwix | 95 | 2025-06 (un solo commit) | Apache-2.0 | plugin per la CLI `llm`: `kiwix_search_and_collect` | fermo; solo come esempio |
| 3M1RY33T/tensor-serve | 5 | 2026-09-18 | MIT | **proxy compatibile OpenAI** che inserisce nel prompt i passaggi trovati negli ZIM: FAISS + BM25 fusi con RRF, reranker cross-encoder facoltativo, **«abstention gate»** | architettura interessante (coerente con il principio 1), ma docs/visione.md ha già scelto «tutto è un tool». Da copiare: fusione RRF e soglia di astensione |
| macromeer/offline-wikipedia-rag | 5 | 2026-02 | MIT | kiwix-serve + Ollama; parole chiave estratte dall'LLM, selezione delle voci con Mistral-7B, sintesi con Llama-3.1-8B; solo Linux/macOS | due chiamate LLM prima della risposta: **troppo lento per la voce** |
| immortalbob/Mnemolis | 21 | 2026-09-13 | — | «knowledge broker» per homelab: smista le query tra Kiwix e altre fonti | idea simile alla «bibliotecaria» |
| psyb0t/offgrid-tools | 58 | 2026-08 | — | ambiente offline completo (chat locale + Kiwix + altro) | spunti per l'elenco dei contenuti |
| roanpy/kiwix-mcp, OscillateLabsLLC/kiwix-mcp, bouldinnathan/lm-studio-kiwix-mcp, RubenVP2/kiwix-agent, kohlhofer/offline-knowledge (Rust), Rome-NotBeepBoop/mcp-offline-wikipedia, tommyschnabel/local-wiki-ai | 0–6 | estate 2026 | varie | piccoli server MCP sopra libzim o kiwix-serve | segnalano un ecosistema vivo; nessuno è maturo |
| openzim/maps | 19 | 2026-09-07 | GPL-3.0 | produce gli ZIM delle mappe | — |
| Upstash/wikipedia-2024-06-bge-m3 (dataset) | — | 2024-06 | Apache-2.0 | 10,1 M di paragrafi italiani già vettorizzati con bge-m3 | scorciatoia per la strategia (b), con i limiti detti in §3.1 |

Osservazione: **nessuno di questi progetti fa il rerank dei paragrafi con embeddings entro un budget di latenza vocale, e nessuno è pensato per l'italiano.** Il pezzo specifico di Calliope (parole chiave italiane → candidati → paragrafo migliore in < 1 s → 1–3 frasi) va scritto, ma è piccolo: il prototipo di oggi è di 60 righe.

---

## 6. Tre livelli di biblioteca

Dimensioni dai listing (G = GiB). Gli indici derivati sono stime [S].

### Livello 1 — «essenziale» (~33 GB di download, < 50 GB con gli indici)

| Contenuto | Dim. |
|---|---|
| `wikipedia_it_all_nopic` | 8,4 |
| `wikipedia_it_all_mini` (introduzioni + infobox: la corsia veloce) | 2,3 |
| `wiktionary_it_all_nopic` | 0,38 |
| `wikisource_it_all_nopic` | 1,8 |
| `wikibooks_it_all_nopic` | 1,6 |
| `wikiquote_it` + `wikivoyage_it` + `wikiversity_it` (nopic) + `vikidia_it` (maxi) | 0,42 |
| `wikipedia_it_medicine_maxi` (WikiMed) | 0,38 |
| `gutenberg_it_all` | 1,0 |
| **Subtotale italiano** | **~16,3** |
| `wikipedia_en_all_mini` (introduzioni di 7,2 M di voci: copre ciò che manca in italiano) | 13 |
| `wikipedia_en_medicine_nopic` + `wikem` + raccolte `zimgit` (medicina, acqua, nodi, cibo, post-disastro) | 2,0 |
| `cooking.stackexchange` + `italian.stackexchange` | 0,25 |
| GeoNames (`allCountries` + `alternateNamesV2`) + dump Photon dell'Italia | 1,2 |
| kaikki.org: dizionario italiano strutturato (JSONL) | 0,5–0,7 |
| **Totale download** | **~33 GB** |
| Indici derivati facoltativi: embeddings delle introduzioni in int8 (~2 GB); database FTS5 dei paragrafi per il piano ARM (~14 GB) | +2…16 |

### Livello 2 — «ampia» (~210 GB di download, < 300 GB con gli indici)

Tutto il livello 1, più:

| Contenuto | Dim. |
|---|---|
| `wikipedia_en_all_nopic` | 49 |
| `wiktionary_en` 8,5 + `wikisource_en` nopic 11 + `wikibooks_en` nopic 3,3 + `wikiquote`/`wikivoyage`/`wikiversity` en nopic 2,1 | 24,9 |
| Gutenberg inglese per classi: scienze (q) 17, tecnologia (t) 12, agricoltura (s) 4,2, medicina (r) 1,9 | 35 |
| Stack Exchange non di programmazione + informatica di base (diy, gardening, mechanics, outdoors, travel, physics, chemistry, biology, astronomy, history, math, electronics, superuser, askubuntu, unix, raspberrypi, arduino, pets, parenting, law, money, english, ell…) | ~29 |
| `ifixit_it_all` | 3,4 |
| `mdwiki_en_all` 10 + `medlineplus` 1,8 + `ready.gov` 2,3 + `trueprepper` 1,3 + `appropedia` 0,56 + `energypedia` 0,76 + `lowtechmagazine` 0,7 | 17,4 |
| LibreTexts (tutti i 13 ZIM) | 16,1 |
| DevDocs + freeCodeCamp | 0,9 |
| `maps_en_italy` | 2,5 |
| **Totale download** | **~211 GB** |
| Facoltativi: `wikipedia_it_all_maxi` (+30, solo se ci sarà uno schermo); embeddings di tutti i paragrafi italiani in int8 (+11) e database FTS5 (+14) | fino a ~266 |

Sta sul disco del portatile (524 GB liberi), ma ne occupa metà.

### Livello 3 — «tutto il possibile» (~1,4 TB, ~1,7 TB con i video)

Tutto il livello 2, più:

| Contenuto | Dim. |
|---|---|
| `wikipedia_en_all_maxi` | 119 |
| `wikipedia_it_all_maxi` | 30 |
| `gutenberg_mul_all` (al posto delle classi) | +218 |
| Tutto Stack Exchange, compreso Stack Overflow | +150 |
| `ted_mul_all` | 85 |
| `khanacademy_en_all` (2023) | 168 |
| `survivorlibrary.com` | 205 |
| `maps_en_all` (mondo) | +70 |
| Photon pianeta | 62,6 |
| Wikidata `latest-all.json.bz2` (o `truthy` 43,5) | 103 |
| `wikisource_en` maxi, `ifixit_en` | +10 |
| **Totale** | **~1,43 TB** |
| Altre Wikipedie (fr, de, es…), cartella `videos` (265 GB), resto del catalogo | fino a **5,2 TB** (tutto Kiwix) |

Non sta sul portatile: richiede un disco esterno o un NAS, e ha senso solo con lo Spark. Avvertenza: video (TED, Khan Academy) e scansioni PDF (Survivor Library) **sono quasi inutili per una RAG vocale** se non se ne indicizza il testo; se i sottotitoli di TED siano ricercabili nello ZIM non l'ho verificato.

Licenze, in breve: Wikimedia CC BY-SA 4.0 (Wikidata CC0); Gutenberg pubblico dominio negli USA; Stack Exchange CC BY-SA; iFixit e Khan Academy CC BY-NC-SA; TED CC BY-NC-ND; OSM/Photon/Geofabrik ODbL; GeoNames e Meteostat CC BY 4.0; MedlinePlus e ready.gov pubblico dominio USA. Per l'uso privato in casa nessuna pone problemi; le clausole NC e SA conterebbero solo se la biblioteca venisse ridistribuita.

---

## 7. Raccomandazione finale

### Che cosa scaricare per primo (11 GB, mezz'ora da un mirror)

1. `wikipedia_it_all_nopic_2026-08.zim` (8,4 G)
2. `wikipedia_it_all_mini_2026-08.zim` (2,3 G)
3. `wiktionary_it_all_nopic_2026-08.zim` (384 M)
4. `wikipedia_it_medicine_maxi_2026-07.zim` (379 M)

Da `https://ftp.fau.de/kiwix/zim/...` (dieci volte più veloce di `download.kiwix.org` da questa rete), in una cartella fuori dal repository e indicata nella configurazione (`*.zim` in `.gitignore`). Poi il resto del livello 1. Il livello 2 può aspettare lo Spark o un disco dedicato.

**Prima misura da fare** con i file veri: latenza della ricerca Xapian su `wikipedia_it_all_nopic` a cache fredda e calda. Se a freddo fosse lenta, basta una query di riscaldamento all'avvio.

### Con quale strategia di ricerca

**Ibrida (c), in tre fasi incrementali**, ognuna utilizzabile da sola:

- **Fase 1 — solo full-text, subito.** Modulo `biblioteca` con interfaccia `cerca(domanda, k) → [Passaggio]` sopra `python-libzim`: parole chiave senza stopword; risoluzione dell'entità con `SuggestionSearcher`; ricerca sul **mini** e poi sul **nopic**; se i risultati sono pochi, riprova con meno termini; prefiltro BM25 dei paragrafi; introduzione e infobox della voce-entità sempre fra i candidati. Latenza attesa < 100 ms. Già così Calliope smette di inventare gran parte dei fatti.
- **Fase 2 — rerank con `bge-m3`** di ~20 paragrafi in una sola richiesta a Ollama, con timeout a 600 ms e ripiego sull'ordine lessicale, soglia di astensione, cache degli embeddings in SQLite. Latenza misurata: 0,4–0,5 s. Richiede che `bge-m3` resti caricato insieme all'LLM: **vincolo in più per la decisione D** (con 8 GB, LLM da 4B sì, `qwen3:8b` no).
- **Fase 3 — embeddings delle sole introduzioni** (1,99 M di vettori, una notte di GPU, 2 GB in int8, `numpy` o `usearch`): aggiunge la ricerca per significato quando le parole chiave falliscono. Gli embeddings di *tutti* i paragrafi (2,3 giorni, 11–22 GB) conviene rimandarli allo Spark, dove diventano sensati anche per l'inglese.

Perché non (b) subito: costa giorni di GPU, va rifatta a ogni ZIM trimestrale, occupa RAM che sul portatile serve ad altro, e da sola è debole proprio dove il full-text è forte (nomi propri, numeri). Perché non solo (a): restituisce voci da centinaia di KB, e un modello da 4B ha bisogno del *paragrafo* giusto.

### Come si incastra nell'architettura

- La biblioteca è **un tool** (`cerca_in_biblioteca(domanda)`), dichiarato «non richiede internet». Il risultato è strutturato: passaggi, titolo della voce, nome e data dello ZIM (per poter dire «secondo Wikipedia…» e sapere quanto è vecchia l'informazione).
- Preferibilmente è **un processo a parte con una piccola API HTTP locale**: isola la GPL di libzim, permette l'emulazione x64 o WSL2 sullo Spark, e si può sostituire con kiwix-serve, Zimi o il database FTS5 senza toccare il resto (principi 2 e 4).
- Lo streaming frase per frase non cambia: il recupero avviene **prima** della generazione e aggiunge 0,1–0,5 s alla prima frase. Conviene che Calliope dica subito un breve «vediamo…» solo se il recupero supera una soglia.
- Percorsi degli ZIM, elenco degli archivi, `k`, soglie e timeout: nella configurazione, non nel codice (principio 3).

---

## 8. Che cosa NON sono riuscito a verificare

1. **Latenza di Xapian sui file grandi** (8,4 GB it, 49 GB en), soprattutto a cache fredda: ho misurato solo sul file «top» da 836 MB appena scaricato (cache calda).
2. **Causa dei picchi di 3–6 s** nel rerank: l'ipotesi è la contesa con altri modelli in Ollama, ma non l'ho dimostrata. Avviso: ho usato GPU e Ollama fra le 12:52 e le 12:58 circa; se in quei minuti giravano altre misure, possono essersi disturbate a vicenda.
3. **Throughput degli embeddings con un runtime ottimizzato** (sentence-transformers o TEI in fp16): le 14–18 ore sono una stima; i ~56 paragrafi/s via Ollama sono misurati.
4. **python-libzim o kiwix-serve x64 in emulazione su Windows ARM**, e WSL2 sullo Spark: nessun hardware per provarli. Le notizie su RTX Spark / N1X (uscita a ottobre 2026, CUDA 13.4 nativo per Windows on Arm dal 9 settembre 2026) vengono da fonti secondarie.
5. **Liber Liber**: dimensione, formato e condizioni del download completo in ISO; numero esatto di titoli.
6. **Compatibilità dei vettori Upstash** (bge-m3 originale) con quelli del `bge-m3` GGUF di Ollama.
7. **FTS5 a piena scala** (11 milioni di paragrafi) e con parole molto frequenti: misurato solo su 140.000 paragrafi.
8. **Zimi e openzim-mcp** non sono stati installati né provati, tanto meno su Windows.
9. **Sottotitoli di TED** ricercabili o no dentro lo ZIM; utilità reale dei contenuti video per la voce.
10. **Licenza del codice di Open-Meteo**, dimensioni dei dataset ERA5 e GHCN, spazio richiesto da Nominatim per l'Italia.
11. La pagina `kiwix-tools.readthedocs.io` non era raggiungibile: l'API di kiwix-serve l'ho letta dal sorgente della documentazione su GitHub. La cartella `wikinews` del mirror risultava vuota.
12. La **qualità delle risposte** è stata valutata su 7 domande soltanto: serve un piccolo banco di prova (50–100 domande in italiano con risposta nota) prima di tarare soglie e `k`.

Materiale lasciato nella cartella temporanea della sessione (`…\scratchpad\`), riutilizzabile per il primo prototipo: `wp_it_top_nopic_fau.zim` (836 MB), `wp_it_top_mini.zim` (107 MB), `vikidia_it.zim` (14 MB), il venv `zimtest` con `libzim`, e gli script `zim_probe.py`, `stem_test.py`, `emb_bench.py`, `spike.py`, `e2e.py`, `fts_bench.py`. Nessun file del progetto è stato modificato, a parte la creazione di questo documento.

---

## 9. Fonti

Kiwix e openZIM
- https://download.kiwix.org/zim/ (cartelle `wikipedia`, `wiktionary`, `wikisource`, `wikibooks`, `wikiquote`, `wikivoyage`, `wikiversity`, `gutenberg`, `stack_exchange`, `ifixit`, `ted`, `other`, `zimit`, `maps`, `mooc`, `vikidia`, `libretexts`, `devdocs`, `freecodecamp`, `phet`, `videos`)
- https://ftp.fau.de/kiwix/zim/ (mirror usato per i listing e i download)
- https://library.kiwix.org/catalog/v2/entries?lang=ita&count=500 (catalogo OPDS)
- https://get.kiwix.org/en/faq-items/can-i-update-zim-files-incrementally/
- https://get.kiwix.org/en/faq-items/what-do-mini-nopic-and-maxi-mean-in-the-wikipedia-zim-files/
- https://www.mediawiki.org/wiki/Kiwix/ZIM_incremental_updates
- https://github.com/jojo2357/kiwix-zim-updater
- https://github.com/openzim/python-libzim — https://github.com/openzim/python-libzim/blob/main/CHANGELOG.md — https://pypi.org/project/libzim/
- https://github.com/openzim/libzim — https://github.com/openzim/libzim/issues/617
- https://github.com/kiwix/kiwix-tools — https://raw.githubusercontent.com/kiwix/kiwix-tools/main/docs/kiwix-serve.rst
- https://download.kiwix.org/release/kiwix-tools/ — https://download.kiwix.org/nightly/
- https://github.com/openzim/maps/

Progetti LLM + ZIM
- https://github.com/cameronrye/openzim-mcp — https://pypi.org/project/openzim-mcp/
- https://github.com/epheterson/Zimi — https://pypi.org/project/zimi/
- https://github.com/mozanunal/llm-tools-kiwix
- https://github.com/3M1RY33T/tensor-serve
- https://github.com/macromeer/offline-wikipedia-rag
- https://github.com/roanpy/kiwix-mcp — https://github.com/kohlhofer/offline-knowledge — https://github.com/immortalbob/Mnemolis — https://github.com/psyb0t/offgrid-tools
- https://huggingface.co/datasets/Upstash/wikipedia-2024-06-bge-m3

Dump e dataset
- https://dumps.wikimedia.org/itwiki/latest/ — https://dumps.wikimedia.org/enwiki/latest/ — https://dumps.wikimedia.org/wikidatawiki/entities/
- https://it.wikipedia.org/w/api.php?action=query&meta=siteinfo&siprop=statistics
- https://huggingface.co/datasets/wikimedia/wikipedia — https://huggingface.co/datasets/wikimedia/structured-wikipedia
- https://kaikki.org/dictionary/rawdata.html — https://kaikki.org/dictionary/Italian/index.html

Geografia
- https://download.geonames.org/export/dump/
- https://download1.graphhopper.com/public/ — https://download1.graphhopper.com/public/europe/italy/ — https://github.com/komoot/photon
- https://download.geofabrik.de/europe/italy.html

Biblioteche italiane e meteo
- https://liberliber.it/prodotto/download-libri/ — https://liberliber.it/opere/libri/licenze/
- https://dev.meteostat.net/license — https://open-meteo.com/en/docs/historical-weather-api — https://github.com/open-meteo/open-data

Embeddings, database vettoriali, Windows su ARM
- https://www.runpod.io/blog/gpu-embedding-workloads-benchmark
- https://ollama.com/library/bge-m3 — https://ollama.com/library/embeddinggemma — https://ollama.com/library/qwen3-embedding
- PyPI (versioni e wheel, 21/09/2026): `usearch`, `faiss-cpu`, `sqlite-vec`, `lancedb`, `pylance`, `chromadb`, `duckdb`, `qdrant-client`, `tantivy`, `bm25s`, `numpy`, `onnxruntime`, `PyStemmer`, `snowballstemmer`, `torch`, `ctranslate2`
- https://alexgarcia.xyz/sqlite-vec/compiling.html
- https://developer.nvidia.com/topics/ai/local-ai/port-apps
- https://tech-insider.org/nvidia-cuda-13-4-windows-on-arm-2026/ — https://www.tomshardware.com/laptops/nvidias-rtx-spark-n1x-launches-in-october-for-laptops-and-desktops-18-or-20-cpu-cores-paired-with-5-120-or-6-144-cuda-cores-up-to-128gb-of-unified-memory
