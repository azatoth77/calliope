# Prova end-to-end sulla DGX, senza nessuno che parli (06/10/2026)

*Codice in [`prove/e2e/`](../e2e/), prova a secco `prove/prova_e2e_copioni.py`. I comandi si
lanciano dalla radice del repository, sul portatile, con la VPN accesa.*

## Cosa fa

Una **seconda Calliope** sulla DGX, solo per la prova, dal codice della versione in uso
(`~/.local/share/calliope/versioni/<attuale>`), con:

- **cartella dati sua**, `~/calliope-e2e/istanza/` (700): configurazione generata, `speakers.json`,
  `memoria.db`, registro dei turni, documenti, sandbox; niente `memoria.db`, `speakers.json`,
  `segreti.yaml` veri. Dalla cartella vera `~/calliope/` legge soltanto: le chiavi del modello
  della voce e dei servizi su 127.0.0.1 (profilo, `keep_alive`, Whisper, agente, SearXNG), i file
  di voci, wake word, CAM++ e biblioteca (per percorso o con un collegamento al singolo file),
  e la data dell'ultima riga del suo registro dei turni;
- **porte sue**: satelliti 18771, schermi 18770 (o le prime libere), il lucchetto d'istanza su
  una porta libera; la Calliope vera resta su 8771/8770 e **non si ferma mai**;
- **stessi servizi**: Ollama (stesso modello e **stesso `num_ctx`** letto da `/api/ps`, stesso
  `keep_alive`: Ollama non ricarica niente), Whisper (`calliope-whisper`), vLLM dell'agente
  (senza la pausa dell'arbitro: `agenti_pausa_vllm: false`), SearXNG. Nessun servizio si
  riavvia né si riconfigura;
- **Home Assistant finto** (`prove/ha_finto.py`, con in più la luce «Taverna») e **PC finto**
  (`prove/pc_finto.py`) dietro l'esecutore del satellite dello studio (ruolo «pc»);
- **due satelliti veri** (`calliope/satellite/client.py`: VAD Silero, wake word acustica,
  protocollo, riproduzione) con microfono e casse finti, nello «studio» e in «cucina»; le frasi
  arrivano al microfono in tempo reale, la voce di Calliope si registra dalle casse e si
  **ritrascrive con il Whisper vero** per vedere che si capisca;
- **persone** (nomi inventati): Carlo, chi amministra, con le **registrazioni vere** di chi
  amministra (`prove/e2e/voce_reale.tsv`: 8 frasi per l'impronta, 37 frasi dei test vocali del
  21/09–01/10); Andrea, chi amministra con la voce di Piper (frasi qualunque: sfide, comandi
  nuovi); Giulia, familiare adulta; Sofia, minore (2017, tutori Andrea e Carlo); un ospite
  (voce non registrata);
- uno **schermo personale** di Andrea nello studio, per scritto, foto e allegati.

I **copioni** (`prove/e2e/copioni.py`) sono conversazioni ricavate dai registri dei turni veri
del 02–05/10 (anonimizzate) più i casi nuovi del 05–06/10; ogni passo ha le sue attese (tool,
regole, esito, livello, chi parla, testo della risposta, servizi dell'HA finto, azioni del PC
finto, annunci, suoni), controllate da sole. Dove serve un giudizio il rapporto stampa la
risposta sotto «Da giudicare a mano».

## Quando parla

L'istanza usa la GPU della voce vera: **ogni copione parte solo se la Calliope vera tace da
180 s** (data dell'ultima riga di `~/calliope/registro/turni-*.jsonl`); se compare un turno
nuovo il runner finisce il copione in corso e aspetta. A fine lavoro si fermano istanza,
satelliti e HA finto, e `~/calliope-e2e/` resta con i soli `risultati/<data>/` (rapporto, passi,
log dell'istanza senza percorsi con l'utente; **niente audio**). Le registrazioni vere stanno
sulla DGX solo durante la prova, in `~/calliope-e2e/voce-reale/` (600/700), e si cancellano con
l'istanza.

Effetto sulla Calliope vera: il prefisso nella cache di Ollama è quello dell'istanza fino al suo
primo turno dopo la prova (una rilettura, ~1–3 s una volta sola).

## Comandi

```powershell
python -m prove.e2e.lancia                        # tutto (~60–90 min con l'agente vero)
python -m prove.e2e.lancia --senza-lenti          # senza i copioni dell'agente (~40 min)
python -m prove.e2e.lancia --aree casa,minori     # solo alcune aree
python -m prove.e2e.lancia --copioni eta,fisica   # solo alcuni copioni
python -m prove.e2e.lancia --non-aspettare        # lancia e torna; poi --stato
python -m prove.e2e.lancia --stato                # coda del log della prova in corso
python -m prove.e2e.lancia --pulisci              # ferma un'istanza rimasta, tiene i risultati
python -m prove.e2e.lancia --senza-voce-vera      # solo voci di Piper
python -m prove.e2e.lancia --telefono             # alla fine anche la pagina del telefono (Edge qui)
python -m prove.e2e.lancia --stt B2 --codice-qui   # variante della trascrizione (A|B|B2|C,
                                                  # docs/aree/stt-tts.md) e codice di questo ramo
```

Sulla DGX, dopo l'unione e `calliope aggiorna`, anche `calliope prova-e2e [--aree …]` (senza le
registrazioni vere, che arrivano solo dal portatile).

Risultati: `~/calliope-e2e/risultati/<data>/rapporto.txt` (per area, passi falliti con frase
detta, trascrizione e risposta, latenza, ritrascrizione, wake word, chi parla, errori del log),
`passi.jsonl` (un passo per riga), `istanza.log`.

## Cosa non prova

- il telefono sulla DGX (Chromium non c'è e installarlo vuole sudo): con `--telefono` la pagina vera si apre in Edge **sul portatile**, attraverso un tunnel SSH verso la porta degli schermi dell'istanza, con il microfono finto di Edge, muto (`--mute-audio`: niente dalle casse del portatile) (una frase sola: abbinamento, wake word e VAD nel browser, risposta); niente iPhone vero;
- le voci vere di altre persone (solo quella di chi amministra) e la cancellazione dell'eco;
- Home Assistant e PC veri (strada prudente: finti).

## Primi giri (06/10/2026, 03:54–05:27, Calliope vera ferma dalle 21:15 del 05/10)

Versione 20261006-0255-7ea1d984, voce `gemma4:26b-a4b-it-qat` su Ollama 0.35 con `num_ctx`
24 576. Tre giri: tutto (95 passi), tutto con il telefono (97), un giro mirato (31).

| | giro 1 | giro 2 |
|---|---|---|
| passi riusciti | 87/95 | 85/97 |
| chi parla riconosciuto giusto | 90/90 | 91/91 |
| frasi perse da wake word o VAD (voce vera al primo colpo) | 0 (36/36) | 0 (36/36) |
| prima voce sentita dal satellite, mediana / p90 | 2,28 / 5,30 s | 2,40 / 5,25 s |
| `prima_frase_s` del registro, mediana / p90 | 1,42 / 4,16 s | 1,49 / 4,98 s |
| turni senza tool né guardiano (`base`) | 0,87 s | 0,89 s |
| turni con il guardiano (minori, ospiti), mediana | 7,3 s | 7,1 s (2 guasti) |
| voce di Calliope ritrascritta (somiglianza mediana) | 1,00 | 1,00 |

Impronta della voce vera (soglia 0,48): 0,69–0,70 di mediana, voci di Piper 0,79–0,88,
ospite 0,21–0,24. Telefono (Edge sul portatile, microfono finto): abbinato, VAD e wake word
nel browser, «Sono le 5:15.» in 2 giri su 2.

Difetti trovati (da correggere a parte):

1. **Ollama tiene 3 modelli, Calliope ne usa 4** (voce 26B, `llama-guard3:8b`,
   `gemma4:e4b-it-qat` del rilevatore, `qwen3-embedding:0.6b` dell'archivio delle
   conversazioni). Il primo embedding scaccia il guardiano; i turni di minori e ospiti lo
   ricaricano e a volte scacciano **il modello della voce** (visto nel giro 3: `/api/ps` senza
   il 26B dopo il turno di un ospite): turni da 10–17 s, «guardiano guasto» (risposta negata al
   minore), turno di un adulto subito dopo a 11–14 s. Vale anche per la Calliope vera.
2. **Ciò che dice con dati di mezzo** (`calliope/riferire.py`, regola 5,
   `uscita_istruzione`): con una foto o una pagina web ancora nella conversazione risposte
   normali diventano «Una foto contiene anche delle indicazioni che non vengono da te: non le
   ripeto.» («Calliope, ti mando un documento.», «Cosa sai fare?» dopo il meteo: 2 giri su 2).
3. **«Il mio gatto si chiama Briciola» non si ricorda** (`calliope/sicurezza.py`, riga 40:
   «chiama» tra gli ordini; regola `ricordo_istruzione`).
4. **Richiesta di un minore ai tutori**: «posso giocare mezz'ora in più?» va a
   `minore_gestisci` (rifiuto «le decide un loro tutore», `calliope/tools/minori.py` riga 254)
   in 2 giri su 3; «Sofia mi ha chiesto qualcosa?» detto dal tutore non chiama mai
   `minore_gestisci` (0 su 3).
5. **«Scollega lo schermo della cucina» senza schermi in cucina**: «Intendi scollegare lo
   schermo della cucina?» (`politica_azione_incoerente`) invece di «non c'è» (2 su 2).
6. **«Cosa sai fare?» legge i nomi delle chiavi**: «spento (archivioenabled)»
   (`calliope/capacita.py`, motivi «spento (…_enabled)»).
7. **Estensione approvata che non risponde alla prima chiamata**: «Converti gradi» (codice
   giusto, 4 righe) si è fermata a 5,46 s con il tetto del manifesto a 5 s; da indagare
   (avvio del container a freddo?).
8. La voce sentita arriva 0,2–0,5 s (mediana) e fino a 3–6 s dopo `prima_frase_s`: il
   registro non misura sintesi, rete e riproduzione del satellite.

Da sapere per leggere i risultati: le frasi di Piper con la voce «ugo» si trascrivono peggio
di quelle vere («barbecue» → «Babica», «hardware» → «ardu», «Spegnila» → «Sprenila», che la
politica tratta come azione non chiesta); «Calliope, dimmi tre città della Toscana» registrata
diventa sempre «Dimitra» (3 su 3). La frase di sfida con Piper passa solo con le parole
staccate. Il PC finto resta bloccato dopo «Blocca il PC» (il «Sì» del PDF dopo trova lo
schermo bloccato).

## Giri 4 e 5 (06/10/2026, dopo le correzioni dei primi giri)

Stessa istanza separata, voce gemma4 26B-A4B su Ollama, satelliti finti. Giro 4 con Ollama a 3
modelli residenti; giro 5 con `OLLAMA_MAX_LOADED_MODELS=4` e `OLLAMA_NUM_PARALLEL=2`. Rapporti
sulla DGX in `~/calliope-e2e/risultati/` (20261006-0642 e 20261006-0753).

| | giro 4 | giro 5 |
|---|---|---|
| passi riusciti | 89/96 | 91/96 |
| chi parla riconosciuto giusto | 91/91 | 91/91 |
| prima voce sentita dal satellite, mediana / p75 / p90 | 1,94 / 2,34 / 3,11 s | 2,03 / 2,40 / 3,25 s (massimo 6,41) |
| prima voce sentita, turni senza tool | 1,78 s | 1,84 s |
| `prima_frase_s` del registro, mediana / p90 | 1,25 / 2,43 s | 1,30 / 2,75 s (p75 1,88) |
| `fine_parlato_s` (mediana) e voce sentita − fine parlato | 1,95 s; 0,16 s | 2,00 s (p75 2,58, p90 3,47); 0,18 s (p90 0,59) |
| turni senza tool né guardiano (`base`) | 0,87 s | 0,915 s |
| con tool contro senza (`prima_frase_s`) | 1,315 contro 0,915 s | 1,35 contro 0,955 s |
| turni con il guardiano: quanti, prima frase, guasti | 8; 1,205 s; 0 (rilevatore 531 ms) | 8; 1,155 s; 0 |
| errori nel log | 0 | 0 |

Rispetto ai giri 1–2: prima voce sentita da 2,28–2,40 s a 1,94–2,03 s di mediana, p90 da
~5,3 s a 3,1–3,25 s; i turni col guardiano da ~7 s a ~1,2 s, senza guasti (il guardiano non
viene più scacciato da Ollama).

**Turni veri dopo le correzioni** (06/10 mattina, aggregato di 20 risposte del registro dei
turni): prima frase mediana 1,31 s (p90 3,33), base 0,91 s, turni col guardiano 1,47 s con il
rilevatore a 0,47 s, STT 0,19 s.
