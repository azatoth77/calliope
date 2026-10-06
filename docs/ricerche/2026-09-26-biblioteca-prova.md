# Biblioteca offline — implementazione e misure

*26 settembre 2026. Segue [`2026-09-21-biblioteca-offline.md`](2026-09-21-biblioteca-offline.md)
(scelta di Kiwix/ZIM e della strategia). Codice: `calliope/biblioteca.py`, tool
`biblioteca_cerca` in `calliope/tools/builtin.py`, banco `prove/prova_biblioteca.py`.*

## File scaricati

Dal mirror `ftp.fau.de/kiwix` (~10–13 MB/s da qui), con `biblioteca/scarica.sh`. SHA-256
verificati contro `download.kiwix.org`.

| File | Dimensione | Uso |
|---|---|---|
| `wikipedia_it_all_mini_2026-08.zim` | 2,42 GB | **principale**: introduzioni e infobox di tutte le voci |
| `wikipedia_it_all_nopic_2026-08.zim` | 9,03 GB | voci complete, lette solo se nel mini manca il dato |
| `vikidia_it_all_nopic_2026-09.zim` | 15 MB | enciclopedia per ragazzi: scaricata, **non attiva** (`biblioteca_ragazzi`) |
| `wiktionary_it_all_nopic_2026-08.zim` | 403 MB | definizioni: scaricato, **non integrato** |
| `wikipedia_it_top_mini_2026-07.zim` | 112 MB | solo per lo sviluppo, cancellato |

Dipendenza: `libzim` 3.13.0 (wheel `cp314-win_amd64`, GPL-3.0). Niente wheel `win_arm64`:
sullo Spark serve un'alternativa (servizio x64 in emulazione, WSL2 o estrazione in SQLite FTS5).

## Come funziona

Tutto su CPU, niente VRAM. Apertura dei due archivi: 40–80 ms.

1. **Parole chiave** dalla domanda. Si tolgono stopword e parole di richiesta («quanto»,
   «dimmi», «dell'»). Le parole di attributo («alto», «abitanti», «simbolo», «fondata»)
   non servono a scegliere la voce, ma pesano sui paragrafi e richiamano le etichette delle
   infobox («dista» → «Semiasse maggiore»).
2. **Voci candidate**:
   - voci-elenco per i superlativi («Laghi d'Italia»);
   - titoli esatti presi dalla frase («il Po» → `Po`, «del sodio» → `Sodio`);
   - suggerimenti sui titoli;
   - ricerca Xapian, che è in AND: se non trova nulla si toglie una parola alla volta.
3. **Lettura** di ~6 voci nel mini (paragrafi e infobox). Le intestazioni di sezione delle
   infobox si conservano («Superficie totale: 302 069 km²»).
4. **Punteggio lessicale**. Pesano le parole in comune, con il titolo considerato parte del
   passaggio, e la coincidenza del titolo con l'entità cercata (Jaccard, parentesi di
   disambiguazione escluse). L'infobox ha un bonus quando la domanda chiede un dato.
5. **Voce completa** (nopic) se la domanda chiede un dato e nei passaggi del mini manca
   l'etichetta collegata.
6. **Superlativi**: si tengono solo i passaggi che esprimono un primato («più grande»)
   nell'ambito chiesto («d'Italia»); altrimenti niente, e il modello risponde con ciò che sa.
7. Al massimo 3 passaggi (2 per voce), tagliati a 450 caratteri attorno alle frasi utili.

Il tool restituisce i passaggi e un campo `cosa_fare`:
- usa un passaggio solo se risponde proprio alla domanda, e cita «secondo Wikipedia»;
- se i passaggi parlano d'altro, rispondi con quello che sai e **non** citare Wikipedia.

Il tool si registra solo se i file ci sono, e il prompt lo nomina solo in quel caso.

## Misure

Banco: 61 domande realistiche dette a voce.
- **43 da manuale**, di cui 5 a cui la biblioteca non serve: barzelletta, ora, conto, «come
  stai», film.
- **18 su fatti meno noti**.
- Alcune domande hanno errori di trascrizione tipici di Whisper.

La risposta attesa è un'espressione regolare sul testo detto.

### Ricerca (a secco, recall@3 = la risposta è nei passaggi restituiti)

| Versione | Recall@3 | Latenza |
|---|---|---|
| prima versione | 30/38 (solo manuale) | 7–80 ms |
| + titoli esatti, parole di attributo, titolo nel passaggio | 33/38 | mediana 30 ms |
| + banco difficile, bonus infobox, intestazioni, superlativi | **50/56** | mediana 33 ms, massimo 111 ms; prima ricerca dopo l'apertura ~60 ms |

I 6 mancati sono di tre tipi:
- **2 nomi storpiati** («monte bianko», «Spana»): nell'uso reale la domanda al tool la scrive
  il modello, che li corregge.
- **Voce senza il dato**: la torre di Pisa non ha l'altezza nel testo né nell'infobox.
- **3 casi deboli**: montagna più alta del mondo, primo presidente della Repubblica, lago più
  grande d'Italia. End-to-end il modello risponde comunque bene, perché il filtro sui
  superlativi lo rimanda a ciò che sa.

**Rerank con bge-m3 (via Ollama): scartato.** Stesso recall (33/38 contro 33/38), +169 ms di
mediana (massimo 556 ms), +0,76 GB di VRAM e contesa della GPU con gemma4.

### End-to-end (Brain su Ollama, gemma4:e4b-it-qat)

| | Con biblioteca | Senza |
|---|---|---|
| Domande da manuale (43) | 42/43 | 41/43 |
| Fatti meno noti (18) | 17/18 | 15/18 |
| Tool giusto (biblioteca quando serve, niente quando non serve) | 61/61 | 61/61 |
| Prima frase, mediana | 0,56–0,66 s | 0,10–0,11 s |
| Prima frase, massimo | 0,85 s | 0,39 s |

Il controllo con le espressioni regolari è indulgente, e il conteggio da solo sottostima la
differenza. Senza biblioteca il modello sbaglia **con sicurezza**:
- Manzoni nato nel 1812 o nel 1817 (è il 1785);
- il Tevere lungo 430 o 492 km (sono 405);
- il Po lungo 1200 km in un giro (sono 652);
- «non ho accesso a dati» sugli abitanti di Milano e Matera.

Con la biblioteca gli errori rimasti sono la torre di Pisa (dato assente, e il modello lo
dice) e Colombo senza l'anno.

**Errori trovati e corretti durante le misure** (restano come regole nel codice):
- Nominare nel prompt un tool che non esiste è dannoso. Senza file ZIM il modello chiamava
  `biblioteca_cerca`, riceveva un errore e rispondeva «non ho accesso» anche sulla Divina
  Commedia. Ora il prompt dipende dai tool registrati (`Config.prompt_for`).
- Passaggi fuori tema su un superlativo facevano **inventare con la fonte**: «il lago più
  grande d'Italia è il lago di Vico, in Calabria, secondo Wikipedia». Le cause erano due. Il
  comune calabrese «Lago (Italia)» vinceva per il titolo, e «il più grande lago delle valli di
  Lanzo» veniva esteso a tutta Italia. I rimedi sono tre: parentesi escluse dal titolo,
  filtro sui primati con l'ambito, istruzione di ignorare i passaggi fuori tema.

**VRAM**: invariata, 5,4 GB totali con gemma4 carico. La biblioteca non usa la GPU.

## Problemi aperti

- **Latenza**: +0,5 s sulla prima frase per le domande sui fatti. Il modello chiama la
  biblioteca anche per fatti che sa, come la capitale della Francia. Si potrebbe chiamarla
  solo per numeri, date e fatti meno noti, ma è difficile da far decidere a un 4B.
- **Conversazione lunga** (`prove/prova_prompt_conversazione.py --biblioteca`): 17/20 contro
  18/20 senza. In un giro su due «che ore sono?» a fine conversazione ha risposto senza tool,
  inventando l'ora. «Che voci hai?» resta debole in entrambi i casi.
- **Tabelle**: le tabelle delle voci non si leggono, e lì stanno classifiche ed elenchi
  («Laghi d'Italia»). Solo le infobox sono estratte.
- **Wikizionario e Vikidia** scaricati ma non usati.
- **Windows ARM**: libzim senza wheel.
