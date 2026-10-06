# Biblioteca senza libzim: lettore ZIM in puro Python e indice SQLite FTS5

*1 ottobre 2026. Segue [`2026-09-26-biblioteca-prova.md`](2026-09-26-biblioteca-prova.md).
Ricerca e prototipo: il progetto non è stato toccato. Prototipi, indici e misure stanno
nello scratchpad della sessione, cartella `biblioteca_arm\`:*
- *`zimpy.py`: il lettore;*
- *`fts_index.py`: il costruttore dell'indice;*
- *`biblioteca_arm.py`: `calliope/biblioteca.py` del commit 946bdc3 con `_Archivio` riscritto;*
- *`prova_arm.py`, `banco_nuovo.py`, `confronta_lettore.py`, `bench_query.py`: le prove.*

## In breve

- **Il problema è reale e non si risolverà da solo.** `libzim` 3.13.0 (PyPI, 07/09/2026) non ha
  wheel `win_arm64`. Non esiste nemmeno una libzim, un kiwix-serve o un Kiwix Desktop per
  Windows ARM64. Il `setup.py` di python-libzim scarica una libzim già compilata e per Windows
  conosce solo `amd64`.
- **Un lettore ZIM in puro Python basta.** Bastano `struct`, `mmap`, `lzma` e
  `compression.zstd`, che in Python 3.14 è nella libreria standard (verificato anche nel
  pacchetto ARM64 di python.org). Il prototipo, ~350 righe:
  - restituisce le **stesse voci e lo stesso HTML byte per byte** di libzim su 600 voci prese a
    caso nei 4 file (600/600);
  - si apre in **<1 ms** (libzim 90–130 ms) e legge una voce in 3–4 ms di mediana (libzim
    1,5–3,2 ms);
  - usa metà della memoria privata.
- **La ricerca senza Xapian si fa con SQLite FTS5**, che c'è nel `sqlite3` di python.org anche
  su ARM64. Le parole si indicizzano già ridotte a radice con la stessa `_stem` della biblioteca.
  - Costruzione: **2,7 minuti per il mini** (indice da 1,3 GiB) e 11 minuti per il file completo
    (4,7 GiB), con 6–12 processi.
  - Qualità: **recall@3 49/56** contro 50/56 di libzim sul banco di
    `prove/prova_biblioteca.py`, e **36/46 contro 36/46** su un banco nuovo scritto senza
    guardare i risultati. Le altre 16 prove (Wikizionario, Vikidia, significati ambigui) sono
    15/16 in tutti e due i casi.
  - Latenza di `cerca`: mediana 32–34 ms contro 52–58 ms.
- **Il file completo non serve indicizzarlo.** La ricerca full-text sul completo non cambia
  nessuna risposta: 48/56 e 36/46, con e senza. Il completo si legge per titolo, come oggi.
  Nemmeno il Wikizionario ha bisogno di un indice, perché si legge per percorso esatto.
  L'indice necessario è quindi **~1,3 GiB** (mini + Vikidia), costruito in ~3 minuti dopo il
  download.
- **Raccomandazione: puro Python + FTS5, al posto di libzim su tutte le piattaforme**, non solo
  sullo Spark. Le alternative:
  - Prism e WSL2 funzionano, ma portano un secondo interprete, un processo in più e latenza in
    più;
  - compilare libzim per win_arm64 è fattibile (vcpkg la compila già), ma è manutenzione GPL a
    ogni versione.

  Stima: **3–4 giorni** per l'integrazione e **+2–3** per le altre fonti di Kiwix.

## 1. Stato attuale (verificato il 01/10/2026)

| Cosa | Stato | Fonte |
|---|---|---|
| `libzim` su PyPI | 3.13.0 del 07/09/2026 (libzim 9.8.2), GPL-3.0+. Wheel per macOS (arm64, x86_64), manylinux e musllinux (x86_64, **aarch64**), `win_amd64`. **Niente `win_arm64`**, né in questa versione né nelle 3.10–3.12 | pypi.org/pypi/libzim/json; `setup.py` di openzim/python-libzim (`"Windows": ["amd64"]`) |
| Segnalazioni aperte su win_arm64 | nessuna trovata in python-libzim, libzim e kiwix-build (ricerca non esaustiva per i limiti dell'API di GitHub). La #164 «Add support for arm64» (2023) riguardava solo Linux e macOS | github.com/openzim/python-libzim/issues/164 |
| libzim compilata | download.openzim.org: win-x86_64 9.8.2-1 (11/09/2026), android, linux aarch64/armhf, macOS. **Niente win-arm64** | download.openzim.org/release/libzim/ |
| kiwix-tools / kiwix-serve | 3.8.2 (02/03/2026): Linux x86_64/aarch64/armv8/armv6, macOS, Windows **solo x86_64**. Kiwix Desktop 2.5.1 (04/01/2026): solo windows_x64 | download.kiwix.org/release/kiwix-tools/, …/kiwix-desktop/ |
| Kiwix JS (Electron) | l'installer dichiara il supporto di Windows on ARM64 (letto solo in un risultato di ricerca). È un lettore e non ha un'API da usare da Python | github.com/kiwix/kiwix-js-windows/releases |
| libzim con vcpkg | port `libzim` 9.8.1 (14/07/2026), dipendenze icu, liblzma, zstd; Xapian facoltativo e spento di predefinito. La PR #1017 di libzim (25/11/2025) mostra una compilazione `arm64-windows` con MSVC. Il port `xapian` 1.4.22 supporta arm64 | github.com/microsoft/vcpkg/tree/master/ports/libzim; github.com/openzim/libzim/pull/1017 |
| conda-forge | nessun libzim; `xapian-core` senza build Windows | anaconda.org |
| Prism (emulazione x64 su ARM) | incluso in Windows 11 24H2. Un processo **ARM64 non può caricare DLL o `.pyd` x64**: serve un Python x64 intero, emulato. Microsoft non pubblica percentuali di prestazione. L'Arm Learning Path misura NumPy x64 emulato ~2,5× più lento del nativo | learn.microsoft.com/windows/arm/apps-on-arm-x86-emulation (06/11/2025); …/arm64ec (24/03/2026); learn.arm.com/learning-paths/laptops-and-desktops/win_python/how-to-2/ |
| `compression.zstd` (PEP 784) | Python 3.14, PEP Final. La build Windows ha `_zstd.vcxproj` con la configurazione ARM64 (zstd 1.5.7). **`_zstd.pyd` ARM64 (PE 0xAA64) c'è** in `python-3.14.8-embed-arm64.zip` (30/09/2026). Qui (3.14.6 x64): `zstd_version_info (1, 5, 7)` | peps.python.org/pep-0784/; CPython `PCbuild/` 3.14 |
| `zstandard` su PyPI (ripiego per Python < 3.14) | 0.25.0 (14/09/2025) con wheel `win_arm64` cp311–cp314. `backports.zstd` 1.7.0 (15/08/2026) win_arm64 per cp310–cp313 | pypi.org/pypi/zstandard/json |
| FTS5 nel `sqlite3` di python.org | `PCbuild/sqlite3.vcxproj` definisce `SQLITE_ENABLE_FTS5` (SQLite 3.50.4). Il `sqlite3.dll` ARM64 del pacchetto embed contiene `ENABLE_FTS5`. Qui: `ENABLE_FTS5` nelle compile_options | CPython `PCbuild/sqlite3.vcxproj` |
| WSL2 su ARM64 | supportato, con Ubuntu e Debian arm64 | learn.microsoft.com/windows/wsl/install-manual (02/06/2026) |
| Letture via `/mnt/c` (9P) in WSL2 | lente: un blog misura 125 MB/s in scrittura contro 850 MB/s su ext4, e pubblica solo dati di scrittura | brainwagon.org, 11/07/2026 |

**Lettori ZIM in puro Python già esistenti** (nessuno adatto così com'è):
- **ZIMply** 1.1.4 (2021) e **ZIMply-core** 1.0.7 (2022): abbandonati, senza cluster estesi
  (offset a 64 bit). ZIMply suppone il namespace «A».
- **pyzim** (PyPI `python-zim` 0.1.2, 30/06/2025, ultimo commit 01/2026): il più completo
  (cluster estesi, `X/listing/titleOrdered/v1`). Usa però `zstandard`/`pyzstd`, ha un solo
  autore e per la ricerca vuole `xapian-bindings` (non installabili con pip).

Un lettore nostro costa ~350 righe e nessuna dipendenza: conviene scriverlo.

### Il formato ZIM, quello che serve

Fonti: [wiki.openzim.org/wiki/ZIM_file_format](https://wiki.openzim.org/wiki/ZIM_file_format)
(revisione del 30/03/2026), [Search_indexes](https://wiki.openzim.org/wiki/Search_indexes),
`src/fileimpl.cpp` e `src/suggestion.cpp` di libzim.

- **Header** di 80 byte, little-endian:

  | Offset | Campo |
  |---|---|
  | 0 | magic 72173914 |
  | 4, 6 | versione major e minor |
  | 8 | uuid (16 byte) |
  | 24, 28 | entryCount, clusterCount |
  | 32 | pathPtrPos |
  | 40 | titlePtrPos (0xFFFF… se assente) |
  | 48 | clusterPtrPos |
  | 56 | mimeListPos |
  | 64, 68 | mainPage, layoutPage |
  | 72 | checksumPos (MD5 negli ultimi 16 byte) |

  I nostri 4 file sono tutti **6.3** senza `titlePtrPos`. Il mini ha 3 123 183 voci e 9 708
  cluster; il completo 3 248 371 voci e 30 605 cluster.
- **Tipi MIME**: stringhe terminate da zero subito dopo l'header, chiuse da una stringa vuota.
- **Dirent**: `u16 mime`, `u8 parameterLen`, `char namespace`, `u32 revision`, poi
  `u32 cluster` + `u32 blob` per un contenuto oppure `u32 redirectIndex` per un redirect
  (mime 0xFFFF), poi percorso e titolo terminati da zero. Un titolo vuoto vale quanto il
  percorso.
- **Liste di puntatori**:
  - lista dei percorsi: `u64` ordinati per `namespace+percorso`, quindi ricerca binaria;
  - elenco per titolo, dalla 6.1 in `X/listing/titleOrdered/v1`: `u32` delle sole voci
    «front», cioè articoli e loro redirect, ordinate per titolo. La v0 con tutte le voci è
    stata tolta nella 6.3;
  - puntatori ai cluster: `u64`.
- **Cluster**:
  - un byte d'informazione: 4 bit bassi per la compressione (1 nessuna, 4 xz, 5 zstd) e il
    bit 0x10 per gli offset a 64 bit;
  - poi i dati, compressi o no: n+1 offset seguiti dai blob.

  Nel mini un cluster è ~118 KB compresso e ~2,09 MB decompresso, con circa 200 voci.
- **Namespace nuovi**: `C` contenuti, `M` metadati, `W` voci note (`W/mainPage`), `X` indici
  (`X/fulltext/xapian`, `X/title/xapian`, `X/listing/titleOrdered/v1`). Gli indici stanno in
  cluster non compressi.
- **Cosa non si legge senza Xapian**:
  - la ricerca full-text (`Searcher`);
  - i suggerimenti ordinati, con radici e parole in qualunque posizione (`SuggestionSearcher`).

  Senza Xapian libzim stessa ripiega su un intervallo di prefisso del titolo nell'elenco
  ordinato, che il prototipo riproduce (`titles_with_prefix`). Tutto il resto si legge.

## 2. Lettore ZIM in puro Python (`zimpy.py`)

Il lettore apre il file con `mmap` in sola lettura e legge subito solo i puntatori ai cluster
(8 byte ciascuno). L'elenco per titolo si legge direttamente dalla mappatura, senza copia.
Funzioni:
- dirent con cache;
- ricerca binaria per percorso e per titolo;
- redirect;
- metadati;
- `iter_entries`.

Due scelte contano per le prestazioni:
- **decompressione a pezzi**: si decomprime solo fino al blob che serve, a passi di 256 KB. Un
  cluster intero costa ~4,4 ms di mediana;
- **cache LRU** di 8 cluster.

Espone la stessa API di libzim che usa `biblioteca.py`: `has_entry_by_path`,
`get_entry_by_path`, `entry.is_redirect`, `get_redirect_entry`, `get_item().content`,
`mimetype`, `title`, `get_entry_by_title`, `get_metadata`. Il ripiego senza Python 3.14 è il
pacchetto `zstandard`.

**Correttezza**: su 150 voci a caso del namespace C per ciascuno dei 4 file, si confrontano
titolo, redirect e destinazione, tipo MIME, SHA-1 del contenuto, ricerca per titolo,
percorsi inesistenti e metadati.

| File | Voci | Uguali | di cui redirect |
|---|---|---|---|
| wikipedia mini | 150 | 150 | 57 |
| wikipedia completa (nopic) | 150 | 150 | 52 |
| vikidia | 150 | 150 | 20 |
| wikizionario | 150 | 150 | 0 |
| **Totale** | **600** | **600** | |

**Tempi** (300 voci a caso, un processo per misura, secondo giro con la cache del disco calda;
Alienware x64):

| File | | Apertura | Percorso, mediana / p95 | Titolo, mediana / p95 | Lettura voce, mediana / p95 | Memoria privata del processo |
|---|---|---|---|---|---|---|
| mini | libzim | 98 ms | 0,13 / 0,26 ms | 0,12 / 0,26 ms | 2,3 / 5,0 ms | 202 MB |
| | zimpy | **0,6 ms** | 0,09 / 0,13 ms | 0,11 / 0,18 ms | 3,1 / 6,1 ms | **103 MB** |
| completa | libzim | 130 ms | 0,15 / 0,23 ms | 0,15 / 0,26 ms | 3,2 / 6,3 ms | 211 MB |
| | zimpy | **1,0 ms** | 0,09 / 0,12 ms | 0,11 / 0,16 ms | 3,7 / 6,5 ms | **114 MB** |
| vikidia | libzim | 91 ms | 0,05 / 0,09 ms | 0,03 / 0,07 ms | 1,8 / 4,0 ms | 177 MB |
| | zimpy | 0,3 ms | 0,03 / 0,06 ms | 0,04 / 0,08 ms | 3,0 / 5,8 ms | 96 MB |
| wikizionario | libzim | 109 ms | 0,11 / 0,16 ms | 0,09 / 0,17 ms | 1,5 / 3,2 ms | 172 MB |
| | zimpy | 0,7 ms | 0,06 / 0,11 ms | 0,07 / 0,13 ms | 3,0 / 5,5 ms | 93 MB |

Con la cache del disco fredda (primo giro) zimpy legge in 3,9–4,8 ms e libzim in 5,0–7,4 ms.
Una ricerca della biblioteca legge ~6–10 voci, quindi la lettura un po' più lenta pesa
~5–10 ms per ricerca, e la recuperano l'apertura e la ricerca per percorso più rapide.

**Rischi del lettore**:
- la versione 6.2 ammette gli «alias»: dirent con lo stesso cluster e blob, letti
  correttamente senza codice in più;
- un file 5.x con namespace vecchi («A») richiederebbe 10 righe in più (oggi Kiwix pubblica
  solo 6.x);
- su Windows la mappatura di un file da 9 GB non costa RAM: entrano in memoria solo le pagine
  toccate.

## 3. Indice SQLite FTS5 (`fts_index.py`)

**Schema**: un file SQLite per file ZIM, con il rowid uguale all'indice del dirent. Il percorso
non si salva: si rilegge dal file ZIM.

```sql
CREATE VIRTUAL TABLE testi  USING fts5(titolo, testo, content='', detail=full,
                                       tokenize='unicode61 remove_diacritics 2');
CREATE VIRTUAL TABLE titoli USING fts5(t, content='', prefix='2 3 4',
                                       tokenize='unicode61 remove_diacritics 2');
CREATE TABLE meta(chiave TEXT PRIMARY KEY, valore TEXT);  -- uuid e dimensione dello ZIM, versione, conteggi
```

- `testi`: una riga per voce HTML.
  - Il titolo comprende anche i titoli dei redirect, cioè gli alias («Giulio Cesare» →
    «Gaio Giulio Cesare»).
  - Il testo è quello del `<body>` senza tag, script, stili e `<sup>` (note).
  - Le parole sono ridotte a radice con `biblioteca._stem`, la stessa funzione che il punteggio
    usa già. Al posto dello stemmer italiano di Xapian si usa questa radice rozza, applicata
    allo stesso modo a domanda e testo.
- `titoli`: una riga per voce «front», redirect compresi, con le parole del titolo senza radice
  e l'indice dei prefissi, per i suggerimenti.
- Estrazione del testo con le espressioni regolari, non con `HTMLParser` (~10× più veloce):
  all'indice serve solo trovare le voci candidate, i paragrafi poi li legge `extract()` come
  oggi.

**Errore trovato**: con `content=''` e `detail=column` (o `none`) **bm25 vale sempre 0** e i
risultati escono in ordine di rowid, cioè alfabetico («'Adi ibn Hatim», «...altrimenti ci
arrabbiamo!»). Nelle tabelle senza contenuto serve `detail=full`, che costa +64 % di spazio
sul mini (799 → 1 308 MiB).

**Costruzione** (Alienware, 24 thread logici, 6–12 processi). L'inserimento in FTS5 avviene in
un solo processo ed è lui il collo di bottiglia. Senza lavorare a lotti il processo principale
è arrivato a 8,4 GB di RAM: ora i lotti sono limitati e il picco è 2,2 GB.

| File | ZIM | Voci indicizzate | Testo estratto | Tempo | Indice | Indice / ZIM |
|---|---|---|---|---|---|---|
| vikidia | 15 MB | 10 425 | 19 M caratteri | 1 s | 10 MiB | 0,67 |
| wikizionario | 403 MB | 763 889 | 795 M | 29 s | 280 MiB | 0,70 |
| **wikipedia mini** | 2,42 GB | 2 037 870 (+1 072 465 redirect come alias) | 2 680 M | **161 s** | **1 308 MiB** | 0,54 |
| wikipedia completa | 9,03 GB | 2 037 864 | 11 355 M | 649 s (6 processi) | 4 835 MiB | 0,54 |
| (mini con `detail=column`, bm25 inutilizzabile) | | | | 134 s | 799 MiB | |

Altre misure:
- velocità: ~23–25 M caratteri di testo al secondo, ~70 s per GB di ZIM;
- `PRAGMA quick_check`: 23 s sul mini, 45 s sul completo;
- spazio libero sul disco C prima delle prove: 446 GB.

**Tempi delle query** (102 domande, secondo giro; `bench_query.py`):

| | full-text, mediana / p95 / massimo | suggerimenti sui titoli (`titles`), mediana / p95 / massimo |
|---|---|---|
| mini, Xapian (libzim) | 1,0 / 7,1 / 16 ms | 10,1 / 42 / 58 ms |
| mini, FTS5 | 3,9 / 40 / 57 ms | **3,3 / 20 / 46 ms** |
| completa, Xapian | 5,8 / 14 / 36 ms | 11,5 / 38 / 56 ms |
| completa, FTS5 | 17 / 71 / 262 ms | 3,3 / 18 / 55 ms |

FTS5 è più lento sulle parole frequenti, perché bm25 con `ORDER BY … LIMIT` deve dare un
punteggio a tutte le righe che corrispondono. È più veloce sui suggerimenti. Nel complesso
`cerca` è più veloce (sezione 4).

## 4. Qualità: la pipeline di `cerca` sopra zimpy + FTS5

`biblioteca_arm.py` è `calliope/biblioteca.py` (commit 946bdc3) in cui cambia **solo**
`_Archivio`:
- `fulltext`: FTS5 in AND con bm25 e il peso del titolo; se non trova nulla toglie la parola
  più corta, come oggi con Xapian;
- `titles` / `suggest`: `titoli MATCH`, con l'ultima parola come prefisso se ha almeno 3
  lettere. Vengono prima il titolo identico, poi quello che comincia con la domanda, poi bm25,
  poi i titoli più corti.

`exact`, `superlative`, `disambiguation`, `read`, `definisci`, i punteggi e i filtri sono
invariati: usano l'API in stile libzim di zimpy.

**Banchi**:
- le 56 domande di fatto di `prove/prova_biblioteca.py`, su cui la pipeline è stata tarata;
- un **banco nuovo di 46 domande** (`banco_nuovo.py`), scritto prima di guardare i risultati,
  per non tarare FTS5 sulle stesse domande;
- 16 prove sul resto: 4 di dizionario, 3 di Vikidia, 3 ambigue, 5 non ambigue.

| Configurazione | Banco 56 | Banco nuovo 46 | Altre 16 | `cerca`, mediana / p95 / massimo (banco 56) | Apertura |
|---|---|---|---|---|---|
| **libzim + Xapian** (oggi) | **50/56** | **36/46** | 15/16 | 58 / 154 / 468 ms | 62–280 ms |
| zimpy + FTS5, peso del titolo 5 | 48/56 | 36/46 | 15/16 | 49 / 146 / 331 ms | 11–14 ms |
| **zimpy + FTS5, peso del titolo 1** | **49/56** | **36/46** | 15/16 | **34 / 124 / 246 ms** | 12 ms |
| zimpy + FTS5, peso 10 | 48/56 | 36/46 | 15/16 | 32 / 112 / 250 ms | 12 ms |
| zimpy + FTS5 solo sul mini (completo letto per titolo) | 48/56 | 36/46 | 15/16 | **32 / 93 / 177 ms** | 13 ms |

Nota: le misure con libzim di questa tabella hanno 50/56 come il 26/09, ma latenze un po' più
alte del rapporto di allora (mediana 33 ms). Ci sono più file aperti (Vikidia e Wikizionario
sono attivi dal 26/09) e la macchina lavorava ad altro.

Sui due banchi insieme: **85/102 contro 86/102**. Sul banco nuovo i mancati sono quasi tutti
gli stessi, e sono limiti della pipeline, non dell'indice:
- Galileo, Dante e Verdi: la data non è nel passaggio scelto;
- «la moglie di Napoleone»;
- «l'uomo sulla Luna»;
- «un anno su Marte».

Sul banco vecchio la differenza è una domanda, «In che anno Cristoforo Colombo arrivò in
America?». Con libzim il 1492 arriva dalla voce «America»; con FTS5 la voce «Quarto viaggio di
Cristoforo Colombo» la scavalca. Con il peso 5 si perde anche «Chi ha scoperto la penicillina?»,
che con il peso 1 torna giusta.

Ranking provati: pesi del titolo 1, 5, 10, 20, 50. Sopra 5 non cambia nulla. Vale il peso 1, con
le radici di `_stem` e gli alias dei redirect nel titolo. Non ho provato oltre per non tarare il
banco: la differenza di una domanda su 102 è sotto il rumore del banco.

**L'indice del file completo non serve**: senza, recall identico (48/56 e 36/46) e latenza
migliore, p95 93 ms contro 124 ms. Il completo resta utile, ma letto **per titolo**: «nel mini
manca il dato → leggi la stessa voce nel completo». Si risparmiano 4,8 GiB e 11 minuti di
costruzione per ogni aggiornamento mensile. Il Wikizionario si legge per percorso esatto
(`definisci`) e non ha bisogno nemmeno lui di un indice (−280 MiB).

## 5. Alternative

| Strada | Come | Costo stimato | Problemi |
|---|---|---|---|
| (a) **Servizio x64 in emulazione Prism** | un Python x64 a parte (python.org amd64) con `libzim` win_amd64 e un piccolo server su pipe o localhost; Calliope ARM64 gli manda `cerca(domanda)` | 1–1,5 giorni | un processo ARM64 non può caricare `.pyd` x64, quindi serve un secondo interprete con i suoi pacchetti, aggiornato a parte. Nessun dato ufficiale sulle prestazioni: con il ~2,5× di NumPy emulato, 33–58 ms diventano ~80–150 ms, più l'IPC (~1 ms). Memoria +150–250 MB. Avvio del servizio e controllo che sia vivo. Licenza GPL di libzim in un processo separato: nessun problema nuovo |
| (b) **WSL2** con libzim aarch64 (wheel manylinux) o kiwix-serve linux-aarch64 | servizio dentro una distribuzione arm64 | 1,5–2 giorni | macchina virtuale da avviare (secondi a freddo; si spegne da sola quando è inattiva), RAM della VM (~1–2 GB), 12 GB di ZIM da copiare nel disco ext4 (via `/mnt/c` le letture casuali in 9P sono lente), rete localhost tra Windows e WSL, aggiornamenti in due mondi. Per un assistente vocale sempre acceso è la strada più fragile |
| (c) **Compilare libzim + python-libzim per win_arm64** | vcpkg (libzim 9.8.1, xapian 1.4.22, icu, zstd, liblzma: tutti con target arm64-windows), poi l'estensione Cython di python-libzim contro quella libzim (il `setup.py` va modificato: oggi scarica solo binari già pronti) | 3–5 giorni la prima volta, poi ~0,5–1 giorno a ogni versione di libzim o Python | non c'è una macchina ARM su cui provare (la compilazione incrociata da x64 si può fare, i test no). Xapian con ICU su MSVC ARM64 non è provato da nessuno di pubblico. Un wheel GPL nostro da mantenere. Il vantaggio è che restano Xapian e il codice di oggi |
| (d) **Puro Python + FTS5** (questo prototipo) | sezioni 2–4 | 3–4 giorni (sezione 6) | indice da costruire dopo ogni download (~3 min, ~1,3 GiB). Ricerca full-text un po' diversa da Xapian (1 domanda su 102). Il codice del lettore è nostro (~350 righe, formato stabile dal 2021) |

## 6. Raccomandazione e piano

**Adottare (d) su tutte le piattaforme**, togliendo la dipendenza da `libzim`.
- Una sola strada per Alienware e Spark, provata ogni giorno da `python -m prove`.
- Niente dipendenze native in più (principio 4): `lzma`, `compression.zstd` e `sqlite3` con
  FTS5 sono nella libreria standard di Python 3.14, anche ARM64.
- Niente GPL nel processo: libzim è GPL-3.0+, il lettore è nostro.
- Apertura in 1 ms invece di 100–280 ms.

Il costo è un indice da costruire. Tenere libzim come ripiego facoltativo (se l'indice manca e
libzim c'è) solo per la transizione.

### Interfaccia e file da toccare

1. **`calliope/zim.py`** (nuovo): `zimpy.py` ripulito (`ZimFile`, `Entry`, `Item`, ricerca per
   percorso e titolo, `iter_entries`, `titles_with_prefix`), ~350 righe. Ripiego zstd:
   `compression.zstd`, poi `zstandard`.
2. **`calliope/biblioteca_indice.py`** (nuovo): `costruisci(zim, indice, processi)`,
   `apri(indice, zim) → Indice | None` (controlla `meta`), `Indice.fulltext(parole, n)`,
   `Indice.suggerisci(testo, n)`. Lo usa anche il catalogo delle installazioni. Va anche come
   comando: `python -m calliope.biblioteca_indice <file.zim>`.
3. **`calliope/biblioteca.py`**: solo `_Archivio`, cioè `__init__`, `fulltext`, `titles` e il
   nuovo `suggest`. `Biblioteca`, `cerca`, `opzioni`, `definisci` e tutto il punteggio restano
   uguali, così come l'interfaccia `cerca(domanda) → [Passaggio]`. Senza indice l'archivio
   resta utilizzabile per percorso e titolo (`exact`, `superlative`, lettura), che da soli
   valgono una buona parte del recall; la ricerca full-text e i suggerimenti tornano vuoti.
4. **`calliope/capacita.py`** → `check_biblioteca`: non controlla più `importa("libzim")` ma
   «file ZIM presenti» e «indice presente e corrispondente». Stato «degradata» con il prossimo
   passo «dimmi "prepara la biblioteca"» se l'indice manca o è vecchio. Il messaggio «libzim non
   ha ancora una versione per Windows su ARM» sparisce.
5. **`calliope/installa/catalogo.py`**: per le azioni `biblioteca` e `biblioteca_aggiorna`,
   `librerie=("libzim",)` → `()`. Dopo download e verifica SHA-256, un **passo «indice»**
   chiama `biblioteca_indice.costruisci` con l'avanzamento a voce. Il file `<nome>.verificato`
   resta quello di oggi. `risolvi_zim` sceglie il file; l'indice si cerca accanto con lo stesso
   nome. L'azione `pulizia` cancella anche gli indici dei file vecchi.
6. **`calliope/config.py`**:
   - `biblioteca_indici: str | None = None` (predefinito: accanto agli ZIM, in
     `biblioteca/indici/`);
   - `biblioteca_indice_processi: int = 4`;
   - `biblioteca_peso_titolo: float = 1.0`.

   `calliope.yaml` si rigenera con `--esempio`.
7. **Prove**:
   - `prove/prova_zim.py` a secco: un file ZIM minuscolo costruito nella prova stessa con
     `struct` (un cluster zstd, uno xz, uno esteso, un redirect, l'elenco v1), così la prova
     non dipende dai 12 GB;
   - `prove/prova_biblioteca.py` invariata, più il banco nuovo da 46 domande;
   - un confronto con libzim se è installato.
8. **CLAUDE.md**: le righe su libzim (setup, «non ha wheel win_arm64», tabella
   dell'architettura).

### L'indice nella vita della biblioteca

- **Dove**: `biblioteca/indici/<nome dello zim senza .zim>.fts.sqlite`, fuori da git come gli
  ZIM.
- **Integrità**: tabella `meta` con:
  - `zim_uuid` (header, byte 8–24) e `zim_dimensione`, controllati all'apertura in <1 ms;
  - `versione` dell'estrattore e dello schema, alzata quando cambia `_stem` o l'estrazione, e
    allora l'indice si ricostruisce;
  - `completo=1` scritto per ultimo.

  Un indice senza `completo=1` o con l'uuid diverso non si usa. La costruzione scrive in
  `….fts.sqlite.tmp` e poi fa `os.replace`, come i documenti. `PRAGMA quick_check` (23 s) non
  serve a ogni avvio: al massimo dopo una costruzione.
- **Quando**: subito dopo download e verifica di un file, nell'azione del catalogo.
  - Mini: ~3 minuti, che con 4 processi invece di 12 diventano ~5–6.
  - Vikidia: 1 s.
  - Wikizionario e completo: niente indice full-text. Per il completo, se un giorno servisse,
    basta la sola tabella `titoli` (~12 s).

  Mentre si costruisce, la biblioteca vecchia resta in uso.
- **Aggiornamento mensile**: un nuovo `<prefisso>_AAAA-MM.zim` dà un nuovo indice accanto.
  `risolvi_zim` passa al file nuovo solo quando esiste anche il suo indice completo, poi la
  pulizia cancella file e indice vecchi. Spazio di picco: due versioni del mini e del suo indice
  (~7,5 GB).
- **Spazio**:
  - fonti di oggi: **~1,3 GiB** (mini 1 308 MiB + Vikidia 10 MiB), contro i 12 GB degli ZIM;
  - con l'indice del completo: +4,8 GiB, non consigliato.

### Le altre fonti italiane di Kiwix (richiesta del 01/10)

Wikisource, Wikibooks, Wikiquote, Wikivoyage, Wikiversità, WikiMed e Gutenberg, in nopic dove
esiste.

**Struttura: un indice per file ZIM**, non uno solo per tutte le fonti:
- si aggiornano in modo indipendente (date diverse su Kiwix);
- si cancellano insieme al loro ZIM;
- un indice danneggiato spegne una fonte sola;
- il rowid resta l'indice del dirent di quel file.

La query interroga gli indici delle fonti pertinenti (in parallelo o in sequenza, ~5–40 ms
l'uno) e fonde i risultati: il bm25 di FTS5 non è confrontabile tra indici diversi, quindi si
fonde per **rango** (prime n di ciascuna fonte, con un peso per fonte), e la decisione resta al
punteggio lessicale sui paragrafi, come oggi.

Pesi e instradamento proposti, da `Config.biblioteca_fonti_extra`:

| Fonte | Peso | Quando |
|---|---|---|
| Wikipedia | 1,0 | sempre |
| WikiMed | 1,2 | domande mediche, cioè parole del lessico medico o la voce trovata in WikiMed |
| Wikivoyage | 1,2 | viaggi e luoghi («cosa vedere a…», «come si arriva…») |
| Wikiquote | — | solo su richiesta («una citazione di…», «chi ha detto…») |
| Wikisource e Gutenberg | — | solo su richiesta di testi («recitami…», «il testo di…»): non sono fonti di fatti |
| Wikibooks e Wikiversità | 0,8 | spiegazioni |

**Testi lunghi** (Wikisource, Gutenberg, Wikibooks): una voce può essere un libro intero. Si
indicizzano **a pezzi** di ~2 000 caratteri, con una tabella
`pezzi(rowid, dirent, inizio, fine)`; senza, bm25 e la lettura dei paragrafi non funzionano.
Lo stesso codice serve per la tabella delle voci, che oggi non si legge.

Stime: indice 0,55–0,7 × lo ZIM se il testo pesa come in Wikipedia, fino a ~1,2× per le fonti
quasi solo testo (Wikisource); tempo ~70–150 s per GB. Su Gutenberg c'è molta incertezza:
contiene anche gli EPUB, che non si indicizzano.

| Fonte | ZIM | Indice stimato | Costruzione stimata (12 processi) |
|---|---|---|---|
| Wikisource | ~1,8 GB | 1,0–2,2 GB | 2–5 min |
| Wikibooks | ~1,6 GB | 0,9–1,9 GB | 2–4 min |
| Gutenberg italiano | ~1,0 GB | 0,3–1,2 GB | 1–3 min |
| WikiMed italiano | ~379 MB | 0,2–0,45 GB | 25–60 s |
| Wikiquote | ~169 MB | 90–200 MB | 12–25 s |
| Wikivoyage | ~105 MB | 60–130 MB | 8–16 s |
| Wikiversità | ~41 MB | 25–50 MB | 3–6 s |
| **Totale fonti in più** | ~5,1 GB | **~2,6–6,1 GB** | **~6–14 min** |

### Rischi

- **Qualità della ricerca full-text** leggermente diversa da Xapian (85/102 contro 86/102 sui
  due banchi). Mitigazione: banco nuovo nelle prove, peso del titolo in configurazione. Uno
  stemmer italiano vero (Snowball in puro Python, ~300 righe) resta un'opzione se compaiono
  errori sistematici.
- **Latenza sulle parole frequenti**: p95 di 40 ms sul mini, massimo 57; sul completo fino a
  262 ms, ragione in più per non indicizzarlo. Se servisse: `LIMIT` su una sotto-query per
  rowid, oppure togliere dalla ricerca full-text le parole presenti in più del 5 % delle voci.
- **Costruzione dell'indice sul Pi o su macchine deboli**: richiede CPU (~25 M caratteri al
  secondo con 6–12 processi). Sullo Spark (20 core ARM) va bene. Sull'Alienware con Calliope
  accesa conviene usare 4 processi, e il picco di memoria del processo principale va limitato
  (oggi 2,2 GB con la cache di SQLite a 256 MB, riducibile).
- **Prestazioni su ARM non misurate**: niente macchina ARM qui. Tutto è Python più C della
  libreria standard (zstd, lzma, sqlite), compilato nativo ARM64 da python.org, senza
  emulazione: ci si aspettano tempi simili o migliori. **Da misurare sullo Spark** con
  `confronta_lettore.py tempi` e `prova_arm.py`.
- **Formato ZIM che cambia**: è stabile dalla 6.1 (2021), e la 6.2–6.3 ha solo aggiunto alias e
  tolto l'elenco v0. Prova a secco con un file costruito ad hoc più un confronto con libzim su
  x64 quando c'è.
- **Disco**: +1,3 GiB oggi, +2,6–6,1 GiB con le fonti in più, e il doppio durante un
  aggiornamento.

### Stima

| Lavoro | Giorni |
|---|---|
| `calliope/zim.py` dal prototipo, con la prova a secco su un file ZIM sintetico | 1 |
| `biblioteca_indice.py` (costruzione a lotti, meta, scrittura atomica, CLI) e `_Archivio` | 1 |
| Catalogo (passo «indice», pulizia, `risolvi_zim` legato all'indice), capacità, config, CLAUDE.md | 1 |
| Prove: banco nuovo, confronto con libzim, misure; sullo Spark quando arriva | 0,5–1 |
| **Totale integrazione** | **3,5–4** |
| Fonti in più: indice a pezzi per i testi lunghi, fusione per rango, pesi e instradamento | +2–3 |
