# Mappe offline e schermi: valutazione della funzione (01/10/2026)

*Ricerca del 1° ottobre 2026 su richiesta dell'utente: «Vorrei che anche le mappe fossero
disponibili offline… Calliope potrebbe mostrare le informazioni su una pagina web, sullo
schermo di un PC che fa da satellite». Il perimetro è stato poi allargato a **tutto il
mondo** (non solo l'Italia) per i dati delle mappe. Solo analisi: Calliope non è stato
toccato né avviato. Le prove sono state fatte nella scratchpad (venv separato con Python
3.14.6, JDK portatile, nessuna installazione di sistema), su un'area piccola: **la Toscana**
(PBF da 184 MB) e la **provincia di Siena** per le tile. Niente download del pianeta.
Collegata a [`2026-09-21-home-assistant-e-satelliti.md`](2026-09-21-home-assistant-e-satelliti.md),
[`2026-09-26-controllo-pc.md`](2026-09-26-controllo-pc.md),
[`2026-09-26-tool-e-agenti.md`](2026-09-26-tool-e-agenti.md) e alla [visione](../visione.md).*

*Legenda: [M] misurato qui · [V] verificato su fonte primaria (repository, PyPI, sito
ufficiale, header HTTP) · [A] da aggregatori, forum o stampa · [D] mia deduzione o stima.
Dimensioni in GB/MB decimali dove vengono da header HTTP, MiB dove misurate sul disco.*

## In breve

- **Si può fare tutto offline, e costa poco in latenza.** Sulla Toscana, sul portatile:
  «la farmacia più vicina» **4 ms**, un indirizzo **1–6 ms**, «quali strade passano vicino
  a casa» **0,6 ms** (indice SQLite proprio) [M]; un percorso Siena → Firenze in auto
  **8–25 ms**, a piedi o in bici fino a 80 ms, un'isocrona 55 ms, «la farmacia più vicina
  a piedi» come matrice 1×5 in **6,6 ms** (Valhalla nello stesso processo Python) [M]. La
  mappa vettoriale si apre in un browser **senza internet** in 0,36 s e una «scheda»
  spinta dal server arriva alla pagina in **0,4 ms** (mediana, in locale) [M]. Nulla di tutto
  questo si avvicina al budget della voce.
- **Mappa da mostrare: Protomaps/PMTiles + MapLibre.** Un file per area, estratto dalla build
  giornaliera del pianeta senza scaricarla (138,5 GB a z15, build del 01/10/2026) [V].
  Misurati con `pmtiles extract --dry-run` [M]: **mondo a z8 556 MB**, a z10 3,8 GB;
  **Italia a z15 4,5 GB** (z14 2,3 GB, z12 580 MB); Europa a z14 25 GB, a z15 49 GB;
  Toscana a z15 358 MB. La prova end-to-end (mondo z6 + Siena z15, stile Protomaps in
  italiano, font e sprite locali) ha fatto **20 richieste, tutte a 127.0.0.1**, con la rete
  esterna bloccata [M].
- **Ricerca di luoghi: due livelli leggeri, niente Nominatim.** Per il mondo, **GeoNames
  cities1000** (171.094 località, 43 MiB in SQLite FTS5, costruito in 1,7 s, ricerca in
  0,05 ms, trova «Lione», «Monaco di Baviera», «Pechino» grazie ai nomi alternativi) [M]. Per
  l'Italia, un **indice SQLite FTS5 + R*Tree costruito dal PBF con pyosmium** (wheel
  `win_arm64` [V]): Toscana in 58 s, 456 MiB di picco, 84 MiB su disco, 373.632 luoghi di cui
  326.833 civici, 971 farmacie, 953 supermercati [M]; Italia stimata ~1 GB e ~12 minuti [D].
  Photon (Java, dump Italia 595 MB [V]) resta il ripiego se servirà la tolleranza ai refusi.
- **Percorsi: Valhalla sul portatile, GraphHopper come riserva ARM.** Entrambi provati sulla
  Toscana con auto, piedi e bici [M]:
  - **Valhalla 3.9.0** via `pip install pyvalhalla` (wheel `win_amd64`, niente server, gira
    nel processo Python): costruzione **24 s**, 1,1 GB di picco, **175 MB** di tile per tutti e
    tre i mezzi, istruzioni in italiano già pensate per la voce, isocrone e matrici. Difetti
    trovati: la costruzione in un colpo solo **si chiude con un errore** (0xC0000409), a
    stadi va; manca il wheel `win_arm64`.
  - **GraphHopper 11.1** (Java, gira **nativo su Windows ARM64** con il JDK Microsoft):
    costruzione **34 s**, 2,6 GB di picco, 156 MB, query **5–11 ms**, istruzioni in italiano,
    server da 585 MiB. Niente matrice nella versione libera.
  - OSRM è il più veloce ma vuole un grafo per mezzo e non ha nulla per Windows ARM.
- **Il mondo intero non serve tutto al massimo dettaglio.** Pianeta: PBF 95,1 GB [V], tile
  z15 138,5 GB [V], geocoding Photon ~95 GB con 64 GB di RAM consigliati [V], routing
  Valhalla ~100 GB di tile con ~24 h di costruzione su 16 core/64 GB [V]. Sul portatile no;
  sullo Spark in parte, ma ruberebbe memoria all'LLM. Proposta: **«mondo base» leggero
  (tile z8 + città GeoNames, ~0,6 GB), «dettaglio Italia» completo (~8 GB tra tile, luoghi e
  percorsi), «Europa» solo sullo Spark e solo a richiesta** (tile z14 25 GB + percorsi ~33 GB).
- **Lo schermo è utile anche senza mappe.** Un piccolo server **Starlette + uvicorn** (puro
  Python, nessuna dipendenza nativa nuova: `uvicorn[standard]` no, perché httptools non ha
  `win_arm64` [V]) serve la pagina, i file PMTiles con le **HTTP Range** (provate [M]) e un
  canale **SSE** verso la pagina. Le schede (mappa, timer, lista, voce della biblioteca,
  anteprima del documento, stato della casa, testo lungo) partono **dal codice dei tool, non
  dall'LLM**, nel momento in cui il tool finisce: arrivano insieme alla prima frase, e la voce
  non le aspetta mai.
- **Raccomandazione.** Si fa, a fasi. **Prima fase consigliata: il server delle schede con
  la pagina in kiosk sul portatile (3–4 giorni)**, utile subito per liste, timer, biblioteca
  e documenti, e base di tutto il resto. Poi mappa + luoghi (4–5 giorni), poi percorsi (3–4
  giorni), poi schermi multipli e satelliti (3–5 giorni). Totale ~13–18 giorni.

---

## 1. Le domande a voce e cosa serve per rispondere

| Domanda | Cosa serve | Risposta a voce (breve) | Sullo schermo |
|---|---|---|---|
| «Dov'è la farmacia più vicina?» | posizione di casa, indice dei luoghi per categoria (R*Tree), orari `opening_hours` se ci sono | «La più vicina è la Farmacia Gori, in Banchi di Sopra 18, a 90 metri. Oggi chiude alle 19:30.» | mappa con 3 marker numerati, il primo evidenziato |
| «Quanto ci metto in macchina a Firenze?» | geocoding della città, percorso auto | «Circa un'ora senza traffico: 72 chilometri.» | percorso sulla mappa, durata e distanza |
| «Come arrivo al supermercato a piedi?» | luogo per categoria + percorso a piedi (meglio: matrice a piedi sui 3–5 più vicini) | «Il più comodo è il Conad di Via di Città, a 2 minuti a piedi: esci e gira a destra in Via di Città.» | percorso a piedi e le prime indicazioni |
| «Che strade passano vicino a casa?» | tratti di strada con nome attorno al punto di casa | «Le più vicine sono Via delle Terme, Via di Città e Vicolo di San Paolo.» | mappa centrata sulla casa |
| «Mostrami la mappa di Siena» | geocoding + schermo | «Ecco Siena, sullo schermo dello studio.» (o «qui non c'è uno schermo») | la mappa |
| «Dove si trova Lione? Quanto dista?» | città del mondo (GeoNames) | «Lione è in Francia, a circa 580 chilometri in linea d'aria.» | mappa del mondo a zoom basso |
| «Che ore sono a Tokyo?» | città del mondo con fuso orario (GeoNames ha la colonna) | già dentro le capacità di oggi, con un dato in più | — |

Regole per la voce, coerenti con il principio 5 e con le lezioni dei tool di oggi:
- **I numeri li prepara il codice**: distanze arrotondate («90 metri», «72 chilometri»),
  durate parlate («circa un'ora», «2 minuti»), come `da_dire` di `calcola` e la `conferma`
  dei tool. Il modello non fa conti sulle coordinate.
- **Le indicazioni passo passo non si leggono**, oltre la prima o le prime due: a voce si dà
  il riassunto e il resto va sullo schermo. Valhalla fornisce anche la frase «verbale» di
  ogni manovra (`verbal_pre_transition_instruction`, «Svolta a destra su Via di
  Fontebranda») [M].
- **Senza traffico, e lo si dice**: la durata offline è teorica (sezione 8).
- **La posizione di casa** è configurazione (`calliope.locale.yaml`, come `casa_url`), mai
  nel codice: latitudine e longitudine, o l'indirizzo geocodificato una volta
  all'installazione. Home Assistant conosce già la posizione di casa (impostazioni generali,
  zona «Casa»): con la casa collegata la si può leggere da lì [D, da verificare sull'API
  WebSocket]. Niente GPS. Per un satellite in un'altra casa (seconda casa) servirà una
  posizione per stanza o per satellite [D].

## 2. I dati: OpenStreetMap

### 2.1 Dimensioni e aggiornamenti

| Estratto | Dimensione | Data dei dati | Aggiornamento | Fonte |
|---|---|---|---|---|
| Pianeta (planet.openstreetmap.org) | **95,1 GB** (`planet-260928.osm.pbf`) | 28/09/2026 | settimanale | header HTTP [V] |
| Europa (Geofabrik) | **35,1 GB** | 30/09/2026 | giornaliero | header HTTP [V] |
| Italia (Geofabrik) | **2,24 GB**, con file `.md5` | 30/09/2026 | giornaliero | [V] |
| Italia nord-ovest (Geofabrik) | 564 MB | — | giornaliero | [V]; le altre 4 macro-aree (centro, isole, nord-est, sud) non hanno risposto |
| Regioni italiane (Wikimedia Italia, osmit-estratti.wmcloud.org) | da 17 MB (Molise, Valle d'Aosta) a 294 MB (Lombardia); Toscana **184 MB** | 30/09/2026 | giornaliero | indice HTTP [V] |
| Province (stesso sito) | es. Siena 24 MB | 30/09/2026 | giornaliero | [V] |

Tempo di scaricamento misurato dal sito di Wikimedia Italia: 184 MB in 83 s (~2,2 MB/s) [M].
Geofabrik reindirizza a mirror (per l'Europa `ftp5.gwdg.de`) [V]: nel catalogo vanno
ammessi anche quegli host, come per Kiwix.

Geofabrik divide l'Italia solo in **5 macro-aree**; gli estratti per regione e provincia
vengono da Wikimedia Italia (progetto `osmItalia/estratti_OSM_Italia`) [V]. Per una casa
basta l'Italia intera: 2,24 GB sono pochi.

### 2.2 Licenza ODbL in casa

- I dati OSM sono sotto **ODbL 1.0**. Gli obblighi (attribuzione, condivisione allo stesso
  modo dei database derivati) scattano con l'**uso pubblico** del database o di un «Produced
  Work» [D, dal testo della licenza e dalle FAQ della OSM Foundation]. Un indice SQLite o un
  grafo di percorsi usati in casa non sono uso pubblico: nessun obbligo di pubblicarli.
- **Attribuzione comunque visibile** sulla mappa («© OpenStreetMap»): è nello stile e non
  costa nulla [M, presente nella prova].
- **Se un giorno Calliope venisse distribuita**: non mettere dati o indici derivati nel
  pacchetto; li scarica e costruisce l'installazione stessa (è già il modello del catalogo).
  Stesso discorso per Piper (GPL) nella visione.
- Le altre fonti: **GeoNames CC-BY 4.0** [V] (attribuzione), **ANNCSU** (civici
  dell'Agenzia delle Entrate e ISTAT) CC-BY 4.0 [A]; i font Noto **SIL OFL**, gli sprite
  Protomaps **MIT**, MapLibre e pmtiles **BSD-3** [V].

## 3. La mappa da mostrare

### 3.1 Protomaps / PMTiles

- **PMTiles** è un archivio di tile in un file unico, letto con richieste HTTP Range: niente
  server di tile, basta un server di file statici che gestisca le Range [V].
- **Build giornaliera del pianeta**: `https://build.protomaps.com/AAAAMMGG.pmtiles`, elenco con
  dimensione e hash (md5, b3sum) in `build-metadata.protomaps.dev/builds.json` [V]. Ultima:
  `20261001.pmtiles`, **138.507.309.367 byte**, schema basemaps **v4.15.2**, Planetiler 0.10.2,
  z0–15 [V]. Si tiene l'ultima settimana di build [V]. Servita da Cloudflare con
  `Accept-Ranges: bytes` [V].
- **CLI `pmtiles` (go-pmtiles) 1.31.2** del 22/07/2026, binari anche **Windows_arm64**
  (15,8 MB) [V]. `pmtiles extract <url> out.pmtiles --bbox=… --maxzoom=N` scarica dalla
  build remota **solo le tile dell'area**; `--region` accetta un poligono GeoJSON; `verify`
  controlla l'archivio (60 ms sull'estratto di Siena) [M]; `serve` fa anche da server di tile.
- Il dettaglio di z15 regge l'ingrandimento fino a z18 e oltre (overzoom) [V].

### 3.2 Dimensioni per area e zoom massimo

Misurate con `--dry-run` sulla build del 01/10/2026 (scarica solo le directory) [M]; quelle
con ↓ sono state anche scaricate davvero.

| Area | z6 | z7 | z8 | z9 | z10 | z12 | z13 | z14 | z15 |
|---|---|---|---|---|---|---|---|---|---|
| Mondo | **45 MB** ↓ | 188 MB | **556 MB** | 1,6 GB | 3,8 GB | 18 GB [V, altro agente] | — | — | **138,5 GB** |
| Europa (−25,34 → 45,72) | — | — | — | — | — | 6,6 GB | — | 25 GB | 49 GB |
| Italia (box 6,6/35,4 → 18,6/47,1) | — | — | — | — | — | 580 MB | 1,2 GB | 2,3 GB | **4,5 GB** |
| Toscana (box) | — | — | — | — | — | — | — | — | 358 MB |
| Provincia di Siena (box) | — | — | — | — | — | — | — | — | **58 MB** ↓ |

- Il box dell'Italia comprende anche Svizzera, Slovenia e pezzi di paesi vicini: con il
  poligono dei confini (`--region`) il file scende un po' [D].
- Tempi di estrazione misurati: Siena z15 in 24 s, mondo z6 in 15 s (~2,5–3 MB/s) [M]. Italia
  z15 (4,7 GB trasferiti) ≈ **25–35 minuti** a quella velocità [D].
- **Aggiornare = riestrarre**: non ci sono diff tra build [V]. Per una mappa di casa basta
  ogni 1–3 mesi [D].
- Terreno e ombreggiatura (facoltativi, Mapterhorn): Italia a z10 154 MB, a z12 1,5 GB [V,
  altro agente]. Non servono alla voce.

### 3.3 Cosa serve davvero per funzionare senza internet (provato)

La prova [M]: pagina `index.html` + `style.json` generato con `@protomaps/basemaps` 5.7.2
(tema `light`, **`lang: "it"`**), due sorgenti vettoriali nello stesso stile (mondo z6 sotto
z7,5, Siena z15 sopra z7: 142 livelli, 132 KB), MapLibre GL JS **6.11.2** (solo ESM:
`maplibre-gl.mjs` 580 KB, `-shared.mjs` 504 KB, `-worker.mjs` 20 KB, css 84 KB) e `pmtiles`
4.5.0 (20 KB), serviti da Starlette. Edge headless con la risoluzione dei nomi bloccata per
tutto tranne 127.0.0.1, guidato via DevTools Protocol:

| Misura | Valore |
|---|---|
| Richieste totali | **20, tutte a 127.0.0.1:8765** (più un `data:`) |
| di cui Range sul `.pmtiles` | 7 |
| di cui glifi | 4 |
| Mappa pronta (`idle`) dalla navigazione | **361 ms** (rendering WebGL su CPU, SwiftShader) |
| Avvisi | un'icona dello sprite mancante («townhall»): stile e sprite vanno presi dalla stessa versione |

Lista di controllo (tutte cose che lo stile predefinito **non** fa da solo):
1. `glyphs` e `sprite` puntano al server di Calliope; lo stile generato punta per difetto a
   `protomaps.github.io` [V]. I font (4 famiglie Noto × 256 intervalli) occupano **19 MiB**
   scompattati [M]; tenendo solo Regular, Medium e Italic e gli intervalli latini bastano
   pochi MB [D].
2. MapLibre 6 è **solo ESM** e **richiede WebGL2** [V]: `import * as maplibregl from
   "/lib/maplibre-gl.mjs"` (l'import «default» fallisce: errore trovato nella prova [M]).
3. Il server deve rispondere alle **Range** (Starlette `StaticFiles`: `206 Partial Content`
   con `content-range` corretto [M]); niente compressione gzip sui `.pmtiles` [D].
4. Nessun terreno o sorgente remota nello stile; attribuzione scritta nello stile.
5. Tutto (librerie, font, sprite, stile) è ~3–20 MB e si può **tenere nel repository o in un
   pacchetto del catalogo** con SHA-256 fissi, come le voci.

### 3.4 Alternative

- **OpenMapTiles/MBTiles**: schema e stili (OSM Bright, Positron, Liberty) BSD + CC-BY con
  attribuzione in più; tile del pianeta già pronte solo a pagamento (MapTiler) [V/A];
  costruirle con Planetiler. Nessun vantaggio rispetto a Protomaps per noi [D].
- **VersaTiles** (schema Shortbread, Rust, binari `windows-aarch64`): pianeta z14 ~62 GB,
  ultima build di giugno 2026 [V, altro agente]. Valida, ma aggiornata più di rado.
- **Raster pre-renderizzati**: pianeta a z18 nell'ordine di decine di TB, Italia a z15–16
  decine o centinaia di GB [A/D]. Solo come ripiego a zoom bassi per **TV e tablet senza
  WebGL2** (MapLibre 6 non disegna nulla senza): Leaflet 1.9.4 + poche migliaia di PNG.
- **Costruire le tile da sé con Planetiler** (Java 21+): pianeta in 42 minuti su 64 core,
  ~3,5 h con 8 GB di RAM [V, documentazione]. Non serve: `extract` dalla build pubblica è
  più semplice. Resterebbe l'unica strada se Protomaps smettesse di pubblicare le build.

## 4. Ricerca di luoghi e indirizzi (geocoding)

### 4.1 Le opzioni

| | Indice SQLite proprio (prova) | GeoNames cities1000 (prova) | Photon 1.3.0 | Nominatim 5.3.2 | Pelias |
|---|---|---|---|---|---|
| Cosa | POI per categoria, civici, strade, località | città e paesi del mondo con nomi alternativi e fuso | geocoder completo (OpenSearch dentro) | il geocoder di OSM | geocoder completo |
| Licenza | codice nostro, dati ODbL | CC-BY 4.0 [V] | Apache-2.0 [V] | GPL-2.0 [A] | MIT [A] |
| Dipendenze | **pyosmium 4.3.1** (wheel `win_amd64` e **`win_arm64`** [V]), sqlite3 della libreria standard | nessuna | Java 21+ [V] (JDK Microsoft per Windows AArch64 [V]) | PostgreSQL + PostGIS, solo Ubuntu ufficialmente [V] | Elasticsearch + Node; «Windows currently not supported» [V] |
| Italia | Toscana [M]: 58 s, 456 MiB di picco, **84 MiB**; Italia ~1 GB e ~12 min [D] | file IT 4,2 MB [V] | dump JSONL **595 MB** (28/09/2026) [V], indice di qualche GB [D] | 30–60 GB, ore [D] | sproporzionato [D] |
| Europa | ~17 GB e 3–4 h; con soli POI e località 2–4 GB [D] | — | database pronto **32,3 GB** [V] | centinaia di GB [D] | — |
| Mondo | sconsigliato (vedi 6) | **43 MiB**, 1,7 s [M] | ~95 GB, 64 GB di RAM consigliati, dump 62,6 GB [V] | ≥1 TB, 128 GB di RAM, 2,5–5 giorni [V] | ~450 GB in Elasticsearch, 16 h su 36 core [V] |
| Latenza | **0,1–15 ms** (casi tipici 1–8 ms) [M] | **0,05 ms** [M] | 5–30 ms [D] | decine di ms [D] | decine di ms [D] |
| Refusi | da aggiungere (trigrammi o difflib sui candidati, come `wakeword.py`) | idem | sì [V] | scarsa [D] | sì [A] |
| Aggiornamento | rigenerazione mensile dal PBF | giornaliero, con diff [V] | dump settimanale, cambio di cartella [V] | diff incrementali [V] | reimport |

### 4.2 La prova dell'indice leggero (Toscana) [M]

`indice.py` legge il PBF con pyosmium (cache delle posizioni dei nodi in memoria), tiene i
nodi e le way con un nome **e** una categoria nota (42 categorie parlate: farmacia,
supermercato, distributore, ospedale, bancomat, tabaccheria…) o con un civico, più i tratti
di strada con nome; poi crea una tabella FTS5 (`unicode61 remove_diacritics 2`) e due R*Tree.

| | Valore |
|---|---|
| Lettura del PBF e inserimento | 54,5 s |
| Indici FTS5 + R*Tree + VACUUM | 3,3 s |
| Picco di memoria | 456 MiB |
| File | 84 MiB |
| Luoghi | 373.632, di cui 326.833 con civico, 57.589 POI e località |
| Farmacie / supermercati / distributori | 971 (324 con orari) / 953 / 1.264 |
| Tratti di strada con nome | 162.207 |

Domande con casa di prova in piazza del Campo a Siena (mediane su 20 ripetizioni):

| Domanda | Tempo | Primo risultato |
|---|---|---|
| farmacia più vicina | 4,3 ms | Farmacia Gori, Banchi di Sopra 18, 87 m, orari Mo-Fr 09:00-19:30 |
| supermercato più vicino | 4,1 ms | Conad City, Via di Città 99, 206 m |
| distributore più vicino | 8,2 ms | Eni, Strada di Pescaia, 1,2 km |
| «Montepulciano» | 0,8 ms | la città, a 44 km |
| «Firenze» | 59 ms | la città (molti luoghi contengono «Firenze»: va limitato prima di ordinare) |
| «Banchi di Sopra 20» | 5,7 ms | il civico giusto |
| «ospedale Scotte» | 0,1 ms | Policlinico Santa Maria alle Scotte |
| «via Banchi di Sopra» | 15 ms | **niente**: a Siena la strada si chiama solo «Banchi di Sopra» |
| strade vicino a casa | 0,6 ms | Via delle Terme, Via di Città, Vicolo di San Paolo… |

Cosa insegna:
- per «la più vicina» un R*Tree batte qualunque motore di ricerca testuale, ed è il caso più
  frequente in casa;
- servono **parole vuote per le vie** («via», «piazza», «viale» opzionali) e le **strade come
  luoghi cercabili**, non solo i civici;
- la vicinanza deve pesare di più: «Coop» restituiva Coop a 14–19 km perché il punteggio
  testuale prevaleva; in casa conta quella vicina [M];
- il comune mancante nei POI (molti non hanno `addr:city`) si ricava dal confine
  amministrativo o dalla località più vicina [D].

### 4.3 Il mondo: GeoNames [M]

`cities1000.zip` (11 MB, aggiornato il 01/10/2026 [V]): 171.094 località con più di 1.000
abitanti o capoluoghi, con coordinate, paese, popolazione e **fuso orario**. In SQLite FTS5
sui nomi alternativi: 43 MiB, costruzione 1,7 s, ricerca 0,04–0,06 ms. Risultati, ordinati
per popolazione: «Lione» → Lyon (FR), «Monaco di Baviera» → Munich, «Pechino» → Beijing,
«Nuova York» → New York City, «Parigi» → Paris (prima di una Parigi in Indonesia). Per
risposte del tipo «Lione è in Francia, a 580 km» basta questo; per le vie di una città
estera no (sezione 6).

### 4.4 Civici in Italia: OSM ne ha circa uno su sei

OSM Italia ha **4.636.396** oggetti con `addr:housenumber` (taginfo, 30/09/2026) [V]; ANNCSU
ne censisce ~27,4 milioni, ~20,7 milioni con coordinate [A]. La copertura OSM è molto
disomogenea (in Toscana, 326.833 civici [M]). L'import di ANNCSU in OSM è stato negato tra
dicembre 2025 e gennaio 2026 [A], ma **in casa** il CSV ANNCSU (CC-BY 4.0) si può aggiungere
all'indice locale per i civici, senza ridistribuirlo [D]. Da valutare solo se «portami in via
X numero Y» diventa una richiesta frequente.

## 5. Percorsi (routing)

### 5.1 Confronto

| | **Valhalla 3.9.0** | **GraphHopper 11.1** | OSRM 26.10.0 | BRouter 1.7.10 |
|---|---|---|---|---|
| Data, licenza | 19/09/2026, MIT [V] | 29/09/2026, Apache-2.0 [V] | 01/10/2026, BSD-2 [V] | 17/07/2026, MIT [V] |
| Su Windows x64 | **`pip install pyvalhalla`** (wheel `win_amd64` con gli eseguibili) [V][M] | JAR + JDK 21 [M] | «sperimentale», binari Node [V] | JAR |
| Windows ARM64 | **no** (solo Linux aarch64, Docker arm64) [V] | **sì, nativo** (JDK Microsoft `windows-aarch64` 21.0.12.1, 196 MB [V]) | no [V] | sì (Java) |
| Auto, piedi, bici | **un solo set di tile** | un grafo + una preparazione per profilo | un grafo per profilo | un set |
| Isocrone / matrice | sì / **sì** | sì / no (solo nella versione commerciale) [A] | no / sì | no / no |
| Istruzioni in italiano | `it-IT`, anche frasi «verbali» [M] | `it` [M] | libreria JS a parte [V] | non verificato |
| Italia [D] | tile ~2 GB, ~5 min | grafo ~2 GB, ~7–15 min | ~15 GB di RAM per costruire, 4–5 GB a regime per profilo | 0,71 GB già pronti [V] |
| Europa | tile ~33–40 GB, 8–10 h con 64 GB [D] | base ~22 GB + CH ~45 GB [D] | ~240 GiB per costruire [D] | pochi GB [D] |
| Pianeta | ~100 GB di tile, ~24 h su 16 core/64 GB, ~350 GB di disco al picco [V/A] | CH: ~120 GB di RAM, 25 h con i costi di svolta [V] | ~123 GiB di RAM a regime per l'auto [V] | ~17,9 GB pronti [A] |
| Aggiornamento | ricostruzione | ricostruzione | ricostruzione | segmenti settimanali pronti [V] |

### 5.2 Prova di Valhalla sulla Toscana [M]

- `pyvalhalla` 3.9.0 (29 MB installato) porta `valhalla_build_tiles.exe` e le DLL in
  `pyvalhalla.libs`; il comando `python -m valhalla …` non trovava l'eseguibile, e gli
  eseguibili vanno lanciati con quella cartella nel `PATH` (altrimenti 0xC0000135).
- **La costruzione in un colpo solo si interrompe** (0xC0000409, nessun messaggio) dopo
  13 s, due volte su due; **lanciata a stadi** (`-s X -e X`, 15 stadi) va a buon fine:

| | Valore |
|---|---|
| Tempo totale a stadi | **24 s** (`parseways` 4,9 s, `parsenodes` 4,6 s, `hierarchy` 2,7 s…) |
| Picco di memoria | 1,1 GB (`enhance`) |
| Disco | **175 MB** di tile; ~735 MB al picco con i file intermedi |
| Costruita senza | `admin.sqlite` e `tz_world.sqlite` (regole di accesso per paese, fusi): da aggiungere |

Domande, con `Actor` di Valhalla **dentro il processo Python** (caricamento 8 ms, processo a
216 MiB):

| Mezzo → meta | Distanza, durata | Mediana | Prima |
|---|---|---|---|
| auto → Firenze (Duomo) | 72,6 km, 56 min | 24,6 ms | 156 ms |
| auto → Pisa | 126,1 km, 97 min | 19,3 ms | 41 ms |
| auto → Montepulciano | 67,2 km, 54 min | 8,0 ms | 11 ms |
| piedi → supermercato vicino | 0,2 km, 2 min | 0,9 ms | 1,4 ms |
| piedi → Firenze | 60,9 km, 12 h | 51,5 ms | 57 ms |
| bici → Firenze | 69,3 km, 4 h 10 | 81,5 ms | 100 ms |
| isocrona auto 10 e 20 minuti | — | 55 ms | — |
| matrice a piedi 1 → 5 farmacie | 1,6 / 2,6 / 5,5 / 20 / 36 min | **6,6 ms** | — |

Le istruzioni arrivano in italiano («Svolta a destra su Via di Fontebranda.»). Due difetti
visibili sul punto di partenza in centro storico: un «Fai un'inversione di marcia» e l'auto
che **entra nella ZTL** (senza il database amministrativo e senza regole sulle zone a
traffico limitato) [M]. Il punto di partenza per l'auto va agganciato alla prima strada
percorribile, non a piazza del Campo [D].

### 5.3 Prova di GraphHopper sulla Toscana [M]

JDK Microsoft 21.0.12.1 portatile (zip da 201 MB) + `graphhopper-web-11.1.jar` (47 MB);
profili auto, piedi e bici con Contraction Hierarchies. Per la 11.1 la configurazione vuole
`import.osm.ignored_highways` e i valori `hike_rating`, `country`, `mtb_rating` dichiarati.

| | Valore |
|---|---|
| Importazione + 3 preparazioni CH | **34 s**, picco 2,6 GB (con `-Xmx6g`) |
| Grafo | 854.471 nodi, 1.063.909 archi, **156 MB** su disco |
| Server (`-Xmx1g`) | 585 MiB, avvio in ~1 s |
| Auto Siena → Firenze | 72,2 km, 63 min, **9,9 ms** (prima 154 ms) |
| Auto Siena → Massa | 153 km, 135 min, 9,4 ms |
| Piedi / bici, distanze regionali | 5–11 ms |
| Auto verso il supermercato in centro | 3,6 km, 7 min: **evita la ZTL** (a piedi 0,2 km) |
| Istruzioni | «Continua su Viale Curtatone», «Gira a destra su Via Ricasoli» |

Siena → Firenze in auto: Valhalla 56 min, GraphHopper 63 min; per esperienza il tempo
reale senza traffico è circa un'ora [D]. Le durate vanno dette come stime («circa un'ora»).

### 5.4 Scelta

- **Portatile: Valhalla nel processo** (nessun processo Java, una sola base per tre mezzi,
  matrice per «il più vicino in tempo», isocrone, frasi per la voce). Prima di adottarlo:
  costruzione a stadi (o capire il crash), `valhalla_build_admins` per le regole di accesso
  italiane, prova di qualità sulle ZTL.
- **Riserva per ARM: GraphHopper**, già misurato qui, nativo con il JDK Microsoft per
  AArch64. La «più vicina in tempo» si fa con 3–5 richieste da ~10 ms.
- Entrambi dietro `percorso(da, a, mezzo) → Percorso` e `matrice(da, mete, mezzo)`, come la
  biblioteca è dietro `cerca(domanda)`: sullo Spark si cambia l'adattatore (Valhalla in
  WSL2/Docker arm64, o pyvalhalla x64 in emulazione — da provare —, o GraphHopper).
- OSRM no: un grafo per mezzo e niente per Windows ARM. BRouter no per l'auto; utile solo
  se un giorno servisse la bici su tutto il mondo con dati già pronti.
- **Mezzi pubblici (nota)**: servono i GTFS delle aziende e OpenTripPlanner 2.10 (Java 25)
  [V]. Fuori da questa ricerca; gli orari offline invecchiano in fretta.

## 6. Il mondo intero: cosa costa e come ridurlo

### 6.1 Per componente

Macchina di oggi: 24 thread, 32 GB, ~443 GB liberi [M]. Spark: fino a 128 GB unificati,
ARM64, condivisi con l'LLM. Tempi sullo Spark stimati a parità di potenza per core [D].

| Componente | Disco | RAM (costruzione / uso) | Costruzione oggi | Sullo Spark | Aggiornamento |
|---|---|---|---|---|---|
| PBF pianeta | 95,1 GB [V] | — | download | idem | settimanale |
| PBF Europa | 35,1 GB [V] | — | download | idem | giornaliero |
| PBF Italia | 2,24 GB [V] | — | download | idem | giornaliero |
| **Tile mondo z8** | **0,56 GB** [M] | — / pochi MB per pagina | estrazione ~4 min [D] | idem | 1–3 mesi |
| Tile mondo z10 | 3,8 GB [M] | idem | ~25 min [D] | idem | idem |
| Tile pianeta z15 | 138,5 GB [V] | idem | ~13 h a 3 MB/s [D] | idem | idem |
| **Tile Italia z15** | **4,5 GB** [M] | idem | ~30 min [D] | idem | idem |
| Tile Europa z14 / z15 | 25 / 49 GB [M] | idem | 2,5 / 5 h [D] | idem | idem |
| **Città del mondo (GeoNames)** | **43 MiB** [M] | <100 MB | 2 s [M] | idem | mensile |
| **Luoghi Italia (SQLite)** | ~1 GB [D] | ~3–5 GB / ~50 MB | ~12 min [D] | idem, nativo ARM | mensile |
| Luoghi Europa (SQLite, solo POI e località) | 2–4 GB [D] | cache dei nodi su disco / ~50 MB | 2–4 h [D] | 1–2 h [D] | mensile |
| Photon Europa / pianeta | 32,3 / ~95 GB [V] | — / 8–16 GB e ≥64 GB [V/D] | dump pronti | Europa sì; pianeta toglie spazio all'LLM | settimanale |
| **Percorsi Italia (Valhalla)** | ~2 GB [D] | ~2–4 GB / ~200–500 MB [D] | ~5 min [D] | WSL2 o emulazione | mensile |
| Percorsi Europa (Valhalla) | ~33–40 GB [D] | 32–64 GB / mmap [D] | 12–20 h a concorrenza ridotta, al limite [D] | 6–10 h [D] | 1–3 mesi |
| Percorsi pianeta (Valhalla) | ~100 GB, 350 GB al picco [V/A] | ≥64 GB [V] | no | 1–2 giorni, sconsigliato [D] | raro |
| Percorsi pianeta (GraphHopper CH) | — | ~120 GB [V] | no | no (l'LLM resta senza memoria) | — |

### 6.2 Strategie per ridurre

1. **Zoom a strati**: mondo a z8 (o z9–10 se si vuole leggere le strade principali delle
   città estere) + dettaglio pieno solo dove si vive e si viaggia (Italia z15, poi Europa
   z12–14 sullo Spark). Due sorgenti nello stesso stile: provato [M].
2. **Geocoding a due livelli**: nel mondo solo città e località (GeoNames, 43 MiB); in Italia
   tutto (POI, strade, civici). Sullo Spark l'Europa con soli POI e località.
3. **Percorsi solo dove servono**: Italia (con i paesi confinanti, se serve, con un poligono
   più largo); l'Europa sullo Spark, **a richiesta**. Una domanda di percorso su Lisbona →
   Porto senza dati: «Non ho le strade del Portogallo; in linea d'aria sono circa 280 km.»
4. **Pacchetti separati nel catalogo** (sezione 12), ognuno con la sua dimensione detta
   nella proposta, come per la biblioteca.
5. **Niente pianeta in dettaglio**: 138,5 + ~100 + ~95 GB e giorni di costruzione per
   domande rare. Se un giorno servirà, l'unica combinazione sensata è sullo Spark con
   Valhalla in mmap e senza Photon.

## 7. Integrazione con Calliope

### 7.1 Tool

Oggi i tool sono 34 (con PC, documenti e casa); la soglia oltre cui conviene il recupero dei
tool è 40–50 ([`2026-09-26-tool-e-agenti.md`](2026-09-26-tool-e-agenti.md)). Proposta, 3 tool
in più (37):

| Tool | Parametri (come detti) | Risultato |
|---|---|---|
| `luoghi_cerca` | `cosa` (testo libero o categoria in enum: farmacia, supermercato, distributore…), `vicino_a` (facoltativo: «casa» predefinito, o un luogo) | 1–3 luoghi con distanza, orari se ci sono, `da_dire` pronto; **scheda** mappa |
| `percorso` | `destinazione`, `mezzo` enum {auto, piedi, bici}, `partenza` facoltativa | durata e distanza parlate, prima indicazione, avviso «senza traffico»; **scheda** percorso |
| `mappa_mostra` | `luogo` | la scheda; a voce solo «Ecco Siena sullo schermo» o «qui non c'è uno schermo» |

- Categorie e mezzi in **enum** (scelta 99 % con gemma4 nella ricerca del 26/09);
  conversione delle distanze in Python.
- «Più vicino» a piedi o in auto = R*Tree per i candidati (5–10) + matrice o richieste
  singole per il tempo vero [M: 6,6 ms per 1×5].
- Si nominano nel prompt solo se ci sono (lezione della biblioteca, `Config.prompt_for`).
- `risposta_finale` come per la casa: la frase la prepara il codice, niente seconda passata
  del modello [D, coerente con 0,34 s di prima frase misurati sulla casa].

### 7.2 Capacità

Nuova voce in `calliope/capacita.py` (`DEFINIZIONI`), per esempio:

- `mappe`: «le mappe offline», dipende da «i file in mappe/ (mondo, Italia)», «pyosmium per
  costruire l'indice», «Valhalla o GraphHopper per i percorsi»; `sa_fare` «cercare luoghi
  vicini, calcolare percorsi e mostrare mappe»; `ospite` «i luoghi vicini e i percorsi»
  (non personali); `installa` = le azioni della sezione 12.
- Stati con le stesse regole: `mancante` senza file, `da_configurare` senza posizione di
  casa, `attiva` parziale («le mappe ci sono, i percorsi no»: il dettaglio lo dice il
  motivo).
- `schermi`: «gli schermi», dipende da «il server delle schede», «almeno uno schermo
  abbinato»; `da_configurare` se il server c'è ma nessuno schermo è abbinato.

## 8. Cosa si perde offline, e la rete come extra

| Si perde | Effetto | Rimedio offline |
|---|---|---|
| **Traffico in tempo reale**, incidenti, cantieri, chiusure | le durate sono teoriche | dirlo («senza traffico»); profili orari medi non esistono gratis per l'Italia [D] |
| Orari dei negozi aggiornati, festività, chiusure temporanee | `opening_hours` c'è per una parte dei POI (324 farmacie toscane su 971 [M]) e può essere vecchio | «secondo la mappa chiude alle 19:30» |
| Farmacie di turno | non sono in OSM | nessuno: è un dato del giorno [D] |
| Mezzi pubblici in tempo reale | — | GTFS statici, fuori ambito |
| Foto satellitari, Street View, recensioni | — | nessuno |
| Nuove strade e negozi | dati vecchi di 1–3 mesi | aggiornamento mensile dal catalogo |

Integrazione facoltativa «se c'è rete», coerente con il principio 9 e con il punto 5 della
visione («ogni tool dichiara se richiede internet»):
- **«Apri sul telefono»**: la scheda mostra un **QR code** con un link `geo:` o di una mappa
  web; il telefono ha la sua rete. Calliope non chiama nessun servizio [D]. È il modo più
  semplice di avere traffico e navigazione vera.
- Un adattatore «traffico» (API di terzi con chiave) è possibile ma porta un servizio cloud
  in esecuzione: da non fare finché non lo chiede qualcuno [D].

---

## 9. Calliope che mostra cose su uno schermo

### 9.1 Architettura

```
 Calliope (server)                                           Schermi (PC, tablet, TV)
 Brain → tool ─► risultato con `scheda` ─► SchermiHub ── SSE ──► pagina /schermo (kiosk)
                                           (quali schermi, quale     ├ MapLibre + PMTiles locali
                                            stanza, livello)         ├ timer, liste, testi
 Starlette + uvicorn:  /schermo  /eventi (SSE)  /mappe/*.pmtiles (Range)  /lib /fonts /sprites
                       /abbina (codice)   /dati/… (contenuti delle schede, con token)
```

- **Un solo processo**, dentro Calliope o accanto: Starlette 1.7.0 + uvicorn 0.54.0 senza
  extra (anyio, h11, click: puri) [V][M]. Nessuna dipendenza nativa nuova; il progetto ha
  già `websockets` 17.1 se serve il WebSocket. Alternative misurate dall'altro agente:
  aiohttp ha tutti i wheel `win_arm64` ma 5 pacchetti nativi; `http.server` della libreria
  standard non fa le Range; Litestar non fa le Range; FastAPI aggiunge pydantic-core e
  opentelemetry [V].
- **SSE** per spingere le schede (riconnessione automatica del browser, una sola direzione,
  passa ovunque); latenza misurata in locale **0,4 ms di mediana, 2,2 ms al massimo** su 20
  invii [M]. WebSocket solo se un giorno lo schermo dovrà rispondere (tocco: «apri il
  secondo risultato») [D].
- **La pagina è sempre aperta** e già carica MapLibre, stile e font: una scheda «mappa» è un
  `flyTo` e qualche Range locale, non un caricamento.
- **Le schede le crea il codice dei tool**, non l'LLM: `luoghi_cerca` restituisce
  `{da_dire, scheda: {tipo: "mappa", marker: [...]}}`; il cervello inoltra la scheda allo
  schermo della stanza **appena il tool finisce**, prima che il modello scriva la risposta.
  Per le richieste esplicite («mettilo sullo schermo», «fammelo leggere») un tool
  `schermo_mostra(cosa: enum {ultima_risposta, lista, agenda, documento, casa})` [D].

### 9.2 Le schede

| Scheda | Da dove viene | Contenuto | Visibilità |
|---|---|---|---|
| Mappa / luoghi / percorso | `luoghi_cerca`, `percorso`, `mappa_mostra` | marker, linea del percorso, durata, indicazioni | pubblica |
| Timer | agenda | conto alla rovescia grande | casa |
| Promemoria, appuntamenti | agenda | elenco del giorno | **personale** |
| Lista della spesa | `liste` | voci spuntabili (sola lettura all'inizio) | casa |
| Biblioteca | `biblioteca_cerca` | il passaggio, la fonte, il titolo della voce | pubblica |
| Documento appena creato | `documenti` | **anteprima HTML dal JSON del documento** (già strutturato: titolo, paragrafi, tabelle) | **personale** |
| Stato della casa | `casa_stato` | luci accese, temperature | casa |
| Testo lungo | qualsiasi risposta | il testo intero, invece di ascoltarlo | dipende dalla fonte |

### 9.3 Stanze e scelta dello schermo

- **Abbinamento come per i PC** ([`2026-09-26-controllo-pc.md`](2026-09-26-controllo-pc.md),
  §5.3 punto 2): la pagina `/schermo` senza token mostra **6 cifre e un QR**, valide 10
  minuti e 5 tentativi; chi amministra dice «Calliope, abbina lo schermo della cucina, codice
  4 8 1…» (le cifre si trascrivono bene); il server lega il codice alla stanza e consegna un
  **token lungo per schermo**, salvato solo come hash e revocabile. Lo stesso schema del
  device flow RFC 8628 e del Quick Connect di Jellyfin [V].
- **Lo schermo apre lui la connessione** (SSE in uscita): niente porte in ascolto su tablet e
  TV, come l'esecutore dei PC.
- **Quale schermo**: quello della stanza in cui si parla. Oggi la stanza è una sola (il
  portatile, da configurazione); con i satelliti la stanza viene dal satellite che ha sentito
  la frase. Più schermi nella stessa stanza: tutti; nessuno: **solo voce**, e il tool lo dice
  nel risultato perché la frase non prometta «te lo mostro» [D].
- **Nessuno schermo collegato**: le schede si scartano in silenzio (nessuna coda), la voce
  non cambia. Una richiesta esplicita («mostramelo») riceve «qui non c'è uno schermo; in
  cucina sì, lo mostro lì?» [D].
- **Un PC con l'esecutore è anche uno schermo**: il programma in tray apre Edge in kiosk
  sull'URL con il token, e nel catalogo del PC compare la capacità «schermo». Unisce le due
  strade della roadmap [D].

### 9.4 Kiosk

- **PC Windows**: `msedge.exe --kiosk URL --edge-kiosk-type=fullscreen --no-first-run`;
  gira InPrivate, quindi cookie e `localStorage` si perdono a ogni avvio: il token va
  nell'URL di avvio [V/D].
- **Tablet Android, Google TV, Fire TV**: Fully Kiosk Browser (licenza PLUS una tantum per
  dispositivo, ~6 € [A]): schermo sempre acceso, spegnimento a orario, rilevamento del
  movimento. Attenzione: gira su WebView, che **non si fida delle CA personali** [V].
- **Raspberry con Chromium in kiosk**: possibile, ma non un Pi piccolo con Home Assistant (HAOS non
  ha browser, e una mappa vettoriale lo metterebbe in crisi) [D].
- **WebGL2 obbligatorio** per MapLibre 6 [V]: TV e tablet vecchi vanno provati; senza WebGL2
  le schede di testo funzionano, la mappa no (ripiego raster, §3.4).

### 9.5 Latenza

- La voce **non aspetta mai** lo schermo: l'invio è `put_nowait` su una coda per schermo
  [M]; se lo schermo è lento o spento, la scheda si perde, non la frase.
- La scheda parte alla fine del tool: con `risposta_finale` arriva **prima o insieme alla
  prima frase** (tool di mappa: 1–25 ms; push: <3 ms in LAN [M/D]; disegno su una pagina già
  aperta: decine o centinaia di ms secondo la GPU del dispositivo [D]).
- Il primo caricamento della pagina (361 ms in headless su CPU [M]) avviene una volta sola,
  all'accensione dello schermo.

## 10. Sicurezza e permessi

1. **Solo LAN**: il server ascolta sull'indirizzo di casa, mai inoltrato dal router.
2. **Token per schermo**, hash sul server, revoca a voce («Calliope, scollega lo schermo
   della cucina») o da `python -m calliope.stato`. Le richieste di dati delle schede
   (`/dati/…`) e il canale `/eventi` richiedono il token; i file pubblici (librerie, font,
   tile) no.
3. **Lo schermo non esegue nulla**: riceve solo dati da mostrare. Il rischio è la
   **riservatezza**, cioè chi è davanti allo schermo, che Calliope non sa.
4. **Classe di visibilità per scheda** (tabella 9.2), decisa nel codice:
   - *pubblica* (mappa, biblioteca, timer, meteo): su ogni schermo, anche per gli ospiti;
   - *casa* (lista della spesa, stato della casa): sugli schermi di casa, solo se chi parla
     è familiare;
   - *personale* (promemoria, documenti, risultati di ricerca sui file): **solo su uno
     schermo marcato come personale di quella persona** (lo schermo del suo PC), mai sugli
     schermi comuni, anche se lo chiede lei. Lo schermo del soggiorno non mostra mai un
     documento privato.
   - Ospite: solo schede pubbliche. Zona grigia del riconoscimento: come familiare al
     massimo, mai personale (stessa regola dei PC).
5. **Nessun dato personale nella pagina senza scheda**: la pagina vuota mostra ora e mappa
   di casa, niente nomi, niente agenda.
6. **HTTP o HTTPS in LAN**:
   - Su `http://IP` funzionano SSE, WebSocket, fetch con Range, schermo intero; **non**
     funzionano Screen Wake Lock, service worker, notifiche, geolocalizzazione,
     `crypto.subtle` [V, MDN].
   - Una dashboard di Home Assistant in HTTPS **non può incorporare** una pagina HTTP
     (contenuto misto) [V, documentazione della card Webpage].
   - Il token viaggia in chiaro sul Wi-Fi di casa (protetto da WPA2/3): accettabile
     all'inizio, non per sempre [D].
   - Strada consigliata quando serve: un **secondo nome DuckDNS** che punta all'IP privato di
     Calliope, certificato Let's Encrypt con la sfida DNS-01 (nessuna porta aperta), come già
     per Home Assistant. Vale su TV e tablet senza installare CA [D]. Da sapere: rinnovi più
     frequenti (profilo a 45 giorni dal 2026 [V]), servono internet al rinnovo e
     un'eccezione nei router che bloccano le risposte DNS con IP privati [A]. `mkcert` va
     bene sui PC ma non sulle WebView Android [V].
   - Proposta: **HTTP nella fase 1** (solo il portatile, in kiosk sullo stesso PC dove
     `127.0.0.1` è già un contesto sicuro); **HTTPS dalla fase 4**, quando arrivano tablet,
     TV e la card di Home Assistant.

## 11. Legame con gli altri pezzi

- **Esecutore dei PC**: stesso abbinamento a codice, stesso registro, stessa direzione della
  connessione; l'esecutore in tray apre il kiosk e dichiara la capacità «schermo». Un
  `SchermiHub` gemello di `PCHub`, o un hub unico dei dispositivi con capacità dichiarate
  [D].
- **Satelliti**: oggi Voice PE e simili non hanno schermo. **View Assist** (integrazione
  2026.7.0 e app Android VACA 0.13.4 del 28/09/2026 [V]) trasforma un tablet in satellite
  Assist con schermo: è legato alla pipeline di HA, quindi un riferimento più che una
  dipendenza. Un tablet in cucina con Fully + la pagina di Calliope fa lo stesso lavoro per le
  schede [D].
- **Home Assistant come superficie (alternativa)**:
  - la **card Webpage** (iframe) può contenere la pagina di Calliope, **solo se in HTTPS**;
    per il wake lock dentro l'iframe serve `allow: "screen-wake-lock"` [V/D];
  - **browser_mod** 3.2.3 (07/09/2026, HACS) registra ogni browser e permette
    `browser_mod.navigate` e `popup` su un browser preciso [V]: Calliope, che ha già il
    WebSocket amministratore verso HA, potrebbe usarlo per pilotare i pannelli HA esistenti;
  - il pannello mappa di HA mostra solo entità (persone, zone), non percorsi o punti
    arbitrari [D].
  - Conclusione: **la pagina propria è il centro**; HA è un contenitore facoltativo dove c'è
    già un pannello HA alla parete. Mettere le schede *dentro* HA (card generate) vorrebbe
    dire scrivere card Lovelace e passare dai permessi di HA, che non conosce chi parla.
- **«Stream» verso la TV**:
  - **Google Cast**: il ricevitore si scarica da internet e un ricevitore proprio va
    registrato presso Google [V]; `catt cast_site` usa DashCast a 1280×720 [V]. Non è locale:
    **no** per le schede (principio 9).
  - **DLNA/UPnP**: locale, ma solo per immagini e video statici (una foto della mappa,
    generata dal server, sarebbe possibile) [D].
  - **Miracast / AirPlay**: duplicano uno schermo o servono librerie non ufficiali [D].
  - Meglio un **browser sempre aperto** sulla TV (Fully su Google TV o Fire TV, oppure un
    mini PC con Edge in kiosk) collegato al server [D].

## 12. Catalogo delle installazioni

Il catalogo (`calliope/installa/catalogo.py`) ha oggi i tipi `file`, `kiwix`, `ollama`,
`aggiorna_zim`, `pulizia`, con origine fissa, dimensione, checksum, host ammessi e
`capacita`. Le mappe ci entrano con due tipi nuovi:

| Azione | Origine e verifica | Dimensione detta | Cosa fa |
|---|---|---|---|
| `mappe_base` (librerie, font, sprite, stile) | file fissi con **SHA-256 scritti nel codice** (MapLibre 6.11.2, pmtiles 4.5.0, basemaps-assets), oppure direttamente nel repository | ~5–20 MB | — |
| `mappa_mondo` | tipo nuovo **`pmtiles`**: la build si risolve a ogni proposta da `builds.json` (la più recente), come le versioni di Kiwix; estrazione con lo zoom massimo; verifica con `pmtiles verify` e intestazione (versione dello schema, data) | 556 MB (z8) | tile del mondo |
| `mappa_mondo_dettagli` | idem, z10 | 3,8 GB | facoltativa |
| `mappa_italia` | idem, poligono dell'Italia, z15 | ~4,5 GB, ~30 min | tile dell'Italia |
| `mappa_regione` (enum delle 20 regioni) | idem, poligono della regione | 17 MB–0,4 GB | per chi ha poco spazio |
| `mappa_europa` | idem, z14 | 25 GB | solo Spark |
| `citta_mondo` | `download.geonames.org`, `cities1000.zip`; GeoNames non pubblica checksum: dimensione + controllo del contenuto [D] | 11 MB → 43 MiB | indice delle città |
| `luoghi_italia` | tipo nuovo **`osm`**: PBF di Geofabrik con il suo `.md5` ufficiale [V] → costruzione dell'indice (~12 min) → verifica (conteggi minimi: comuni, farmacie, civici) → il PBF resta per i percorsi o si cancella | 2,24 GB + ~1 GB | indice dei luoghi |
| `percorsi_italia` | stesso PBF → `valhalla_build_tiles` a stadi → verifica con 3 percorsi noti (es. capoluogo → capoluogo, durata in un intervallo) | ~2 GB, ~5–10 min | grafo dei percorsi |
| `percorsi_europa` | PBF Europa 35,1 GB → costruzione notturna | ~35 GB + 35 GB temporanei | solo Spark |
| `mappe_aggiorna` | rifà le azioni installate con l'ultima build e l'ultimo PBF, nella cartella nuova, poi scambio (come Photon e la biblioteca) | — | mensile |
| `mappe_pulizia` | cancella le versioni vecchie dopo l'aggiornamento | — | — |

Note per l'implementazione:
- **Host ammessi**: `build.protomaps.com` (Cloudflare, Range) [V]; `download.geofabrik.de`
  e i suoi mirror (visto `ftp5.gwdg.de`) [V]; `osmit-estratti.wmcloud.org` per le regioni
  [V]; `download.geonames.org` [V].
- **Estrazione PMTiles**: o il binario `pmtiles` (go, anche `windows_arm64`, 15,8 MB, da
  scaricare con SHA-256 fisso), o un estrattore in Python sul pacchetto `pmtiles` 3.8.1
  (puro Python, BSD-3) [V]: ~150 righe per directory e intervalli [D]. Il secondo evita un
  eseguibile in più ed è coerente con il principio 4.
- **Costruzioni lunghe** (indice, percorsi): lavoro in secondo piano con annuncio a fine
  lavoro, come l'installatore di oggi; CPU, non GPU: non toccano l'LLM [D]. Spazio
  controllato prima, con il margine del PBF temporaneo.
- **Dimensione detta prima**: «La mappa dell'Italia occupa 4 gigabyte e mezzo e ci vuole
  mezz'ora: la scarico?», come le proposte della biblioteca.
- **Pacchetto consigliato per l'Italia**: `mappe_base` + `mappa_mondo` + `citta_mondo` +
  `mappa_italia` + `luoghi_italia` + `percorsi_italia` ≈ **8 GB** a regime (+2,24 GB
  temporanei), circa un'ora tra scaricamento e costruzione [D].

## 13. Valutazione

### 13.1 Opzioni a confronto

| Opzione | Disco (Italia / mondo base) | RAM in uso | Costruzione | Latenza | ARM64 Windows | Licenza | Manutenzione |
|---|---|---|---|---|---|---|---|
| **Tile Protomaps + MapLibre** | 4,5 GB / 0,56 GB | nel browser | nessuna (estrazione) | 0,36 s il primo caricamento, poi `flyTo` [M] | binario `pmtiles` arm64; o Python puro | ODbL + BSD/OFL/MIT | riestrarre ogni 1–3 mesi |
| Raster pre-renderizzati | decine di GB | — | ore o giorni, codice nativo | rapida | no | ODbL | pesante |
| **Indice SQLite proprio** | ~1 GB | ~50 MB | ~12 min | 1–15 ms [M] | pyosmium `win_arm64` [V] | nostro + ODbL | rigenerare ogni mese |
| **GeoNames** | 43 MiB (mondo) | <100 MB | 2 s [M] | 0,05 ms [M] | sì | CC-BY | mensile |
| Photon | qualche GB / 32 GB Europa | 2–4 GB / 8–16 GB | dump pronti | 5–30 ms [D] | JDK sì, OpenSearch incorporato da provare | Apache-2.0 | dump settimanale |
| Nominatim | 30–60 GB | 16–32 GB | ore | decine di ms | solo WSL2/Docker | GPL-2.0 | diff incrementali, PostgreSQL |
| **Valhalla (pyvalhalla)** | ~2 GB | ~0,2–0,5 GB nel processo | ~5 min | 1–80 ms [M] | no (WSL2, Docker o emulazione) | MIT | ricostruire ogni mese |
| **GraphHopper** | ~2 GB | ~0,6–3 GB (Java) | ~7–15 min | 5–11 ms [M] | **sì** | Apache-2.0 | ricostruire ogni mese |
| OSRM | ~5 GB per profilo | 4–5 GB per profilo | ~15 GB di RAM | 1–10 ms | no | BSD-2 | ricostruire |
| **Starlette + uvicorn + SSE** | <1 MB | ~30–50 MB [D] | — | 0,4 ms di push [M] | sì (puro Python) | BSD | aggiornamenti pip |
| Card di Home Assistant / browser_mod | — | — | — | — | — | — | dipende da HA e HACS |
| Chromecast / DashCast | — | — | — | — | — | — | richiede internet: no |

### 13.2 Proposta a fasi

| Fase | Contenuto | Giorni | Cosa diventa possibile a voce |
|---|---|---|---|
| **1. Server delle schede** | `calliope/schermi/`: Starlette + uvicorn, `/schermo` con SSE, abbinamento a codice, token, classi di visibilità; schede **timer, lista, biblioteca, documento (anteprima dal JSON), stato della casa, testo lungo**; kiosk Edge sul portatile; capacità `schermi`; prove a secco (scheda giusta, livello giusto, nessuno schermo = nessun effetto sulla voce) | **3–4** | «Mettimi la lista della spesa sullo schermo», «fammelo leggere», il timer visibile, «mostrami la lettera che hai preparato», «che luci sono accese?» con la lista a schermo |
| **2. Mappa e luoghi** | `calliope/mappe/`: posizione di casa in configurazione, PMTiles mondo z8 + Italia z15 (o la regione), stile in italiano con font locali, indice SQLite dei luoghi, GeoNames; tool `luoghi_cerca`, `mappa_mostra`; azioni del catalogo `mappe_base`, `mappa_*`, `citta_mondo`, `luoghi_italia`; prova su Ollama come `prova_casa` | **4–5** | «Dov'è la farmacia più vicina?», «c'è un distributore qui vicino?», «che strade passano vicino a casa?», «mostrami Siena», «dov'è Lione?» |
| **3. Percorsi** | adattatore Valhalla (costruzione a stadi, regole italiane, ZTL) dietro `percorso()`/`matrice()`; GraphHopper come seconda implementazione da tenere viva per lo Spark; tool `percorso`; scheda con la linea; azione `percorsi_italia` | **3–4** | «Quanto ci metto in macchina a Firenze?», «come arrivo al supermercato a piedi?», «la farmacia più vicina a piedi», «fin dove arrivo in bici in mezz'ora?» (isocrona) |
| **4. Più schermi, stanze, satelliti** | HTTPS con DuckDNS, tablet con Fully, TV con browser, abbinamento per stanza, schermo personale sul PC tramite l'esecutore, card di HA in iframe facoltativa; sullo Spark `mappa_europa` e `percorsi_europa` | **3–5** | «Mostralo in cucina», le schede che seguono la stanza in cui si parla, i documenti solo sullo schermo del proprio PC |

Totale **13–18 giorni**. La fase 1 non dipende dalle mappe ed è utile da sola; le fasi 2 e 3
non dipendono dallo schermo (a voce funzionano anche senza) e possono andare in parallelo
alla fase 1.

### 13.3 Raccomandazione

Sì alla funzione, con questo ordine: **schede prima, mappe poi, percorsi dopo**. Sul
portatile: Protomaps/PMTiles (mondo z8 + Italia z15), indice SQLite proprio + GeoNames,
Valhalla nel processo, Starlette con SSE. Sullo Spark: stessi file e stessi indici (SQLite e
pyosmium sono nativi ARM), GraphHopper o Valhalla in WSL2 per i percorsi, Europa a richiesta.
Mai Nominatim, Pelias, OSRM, Chromecast.

## 14. Rischi e cose non verificate

- **Crash di Valhalla in un colpo solo** (0xC0000409) sul wheel Windows: aggirato a stadi, non
  capito. Da riprovare con la configurazione completa (admin, fusi) e da segnalare
  upstream se si ripete.
- **Valhalla su Windows ARM64**: nessun wheel; l'emulazione x64 (Prism) di `pyvalhalla` non è
  provata; WSL2/Docker arm64 sì sulla carta. GraphHopper è la riserva provata qui, ma solo su
  x64: il JDK `windows-aarch64` esiste [V], la prova su ARM no.
- **Estrapolazioni da Toscana a Italia ed Europa**: lineari sulla dimensione del PBF [D]; le
  preparazioni CH crescono più che linearmente. Le misure sull'Italia intera vanno rifatte
  prima di fissare le cifre del catalogo.
- **Qualità dei dati**: ZTL e accessi in centro storico (visto con Valhalla), POI senza
  comune, vie senza «Via» nel nome, civici al ~17 % di ANNCSU, orari a volte vecchi. Va fatto
  un banco di 30–50 domande vere sulla zona di casa (come per la biblioteca).
- **Whisper e i nomi di luogo**: «Montepulciano», «Poggibonsi», i nomi delle vie sono il
  terreno dove Whisper sbaglia di più (taratura del 24/09). Servono tolleranza ai refusi
  nell'indice e forse i nomi dei luoghi vicini nelle `hotwords` [D].
- **Rendering su dispositivi veri**: misurato solo in Edge headless su CPU. TV e tablet
  economici vanno provati (WebGL2, memoria, fluidità di `flyTo`).
- **Spark**: core, prestazioni per core e memoria realmente libera accanto all'LLM sono
  ignoti; i tempi indicati sono stime.
- **Protomaps**: le build pubbliche sono un servizio di terzi gratuito; se sparissero,
  Planetiler (Java) costruisce le stesse tile dal PBF [V].
- **ODbL**: lettura della licenza, non parere legale; conta solo se Calliope venisse
  distribuita.
- **Posizione di casa da Home Assistant**: plausibile, non verificata sull'API.
- **HTTPS con DuckDNS sull'IP privato**: non provato in questa casa (router, rinnovo).

## 15. File delle prove

Tutto nella scratchpad della sessione (`…\scratchpad\mappe\`), fuori dal repository:

| File | Cosa |
|---|---|
| `indice.py`, `cerca.py` | indice SQLite FTS5 + R*Tree dal PBF (pyosmium) e domande tipiche |
| `geonames.py` | indice delle città del mondo |
| `gh.yml`, `percorsi.py` | GraphHopper 11.1: configurazione a tre profili e misure |
| `valhalla4.json`, `valh.py` | Valhalla 3.9.0: costruzione a stadi e misure (percorsi, isocrona, matrice) |
| `gen_style.cjs`, `web/`, `server.py` | stile in italiano con due sorgenti, pagina, server Starlette con SSE e Range |
| `cdp.mjs`, `cdp2.mjs` | Edge headless via DevTools Protocol: richieste, tempo di caricamento, latenza SSE |
| `mappa_siena.png` | schermata della mappa offline |
| `misura.py` | tempo e picco di memoria di un processo |

Versioni: Python 3.14.6, pyosmium 4.3.1, SQLite 3.50.4, pyvalhalla 3.9.0, GraphHopper 11.1 su
Microsoft OpenJDK 21.0.12.1, go-pmtiles 1.31.2, Protomaps basemaps v4.15.2 (build
20261001), @protomaps/basemaps 5.7.2, MapLibre GL JS 6.11.2, pmtiles JS 4.5.0, Starlette
1.7.0, uvicorn 0.54.0, Edge (headless, SwiftShader), Node 24.18.0.

## 16. Fonti principali

- Dati OSM: [Geofabrik Italia](https://download.geofabrik.de/europe/italy.html),
  [planet.openstreetmap.org](https://planet.openstreetmap.org/pbf/),
  [estratti di Wikimedia Italia](https://osmit-estratti.wmcloud.org/),
  [taginfo Italia, civici](https://taginfo.geofabrik.de/europe:italy/api/4/key/stats?key=addr:housenumber),
  [ODbL](https://opendatacommons.org/licenses/odbl/1-0/),
  [discussione ANNCSU](https://community.openstreetmap.org/t/database-csv-numeri-civici-italiani-anncsu/141540)
- Tile: [build Protomaps](https://build-metadata.protomaps.dev/builds.json),
  [documentazione](https://docs.protomaps.com/basemaps/downloads),
  [CLI pmtiles](https://docs.protomaps.com/pmtiles/cli),
  [go-pmtiles](https://github.com/protomaps/go-pmtiles/releases),
  [localizzazione](https://docs.protomaps.com/basemaps/localization),
  [basemaps-assets](https://github.com/protomaps/basemaps-assets),
  [MapLibre 6.0.0](https://github.com/maplibre/maplibre-gl-js/releases/tag/v6.0.0),
  [Planetiler](https://github.com/onthegomap/planetiler),
  [VersaTiles](https://download.versatiles.org/)
- Geocoding: [Photon](https://github.com/komoot/photon),
  [dump Photon](https://download1.graphhopper.com/public/),
  [Nominatim, installazione](https://nominatim.org/release-docs/latest/admin/Installation/),
  [Nominatim, import](https://nominatim.org/release-docs/latest/admin/Import/),
  [Pelias, pianeta](https://github.com/pelias/documentation/blob/master/full_planet_considerations.md),
  [GeoNames](https://download.geonames.org/export/dump/),
  [pyosmium su PyPI](https://pypi.org/project/osmium/)
- Percorsi: [Valhalla](https://github.com/valhalla/valhalla/releases),
  [pyvalhalla](https://pypi.org/project/pyvalhalla/),
  [Valhalla, costruzione del pianeta](https://github.com/valhalla/valhalla/issues/5099),
  [GraphHopper](https://github.com/graphhopper/graphhopper/releases),
  [GraphHopper, requisiti](https://github.com/graphhopper/graphhopper/blob/master/docs/core/deploy.md),
  [OSRM, memoria e disco](https://github.com/Project-OSRM/osrm-backend/wiki/Disk-and-Memory-Requirements),
  [BRouter, segmenti](https://brouter.de/brouter/segments4/),
  [JDK Microsoft](https://learn.microsoft.com/en-us/java/openjdk/download)
- Schermi: [Starlette](https://starlette.dev/release-notes/),
  [MDN, contesti sicuri](https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts/features_restricted_to_secure_contexts),
  [Edge in kiosk](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-configure-kiosk-mode),
  [Fully Kiosk](https://www.fully-kiosk.com/en/),
  [card Webpage di HA](https://www.home-assistant.io/dashboards/iframe/),
  [browser_mod](https://github.com/thomasloven/hass-browser_mod),
  [View Assist](https://github.com/dinki/view_assist_integration),
  [catt](https://github.com/skorokithakis/catt),
  [RFC 8628](https://www.rfc-editor.org/rfc/rfc8628.txt),
  [Let's Encrypt a 45 giorni](https://letsencrypt.org/2025/12/02/from-90-to-45)
