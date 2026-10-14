# Misura dell'eco della stanza (passo 5, 14/10/2026)

Progetto: [`docs/ricerche/2026-10-13-conversazione-di-stanza.md`](../../docs/ricerche/2026-10-13-conversazione-di-stanza.md)
§ 5.3 e § 6 (riga 5), decisione 0029. Interruttore: `stanza_durante_voce` (di serie `false`).
Obiettivi: **eco residua < 2 parole ogni 100** dette da Calliope, **righe false 0** (righe di
persone quando nessuno parlava), **parole recuperate** (quanto si sente di una persona che parla
sopra la sua voce). Solo adulti che lo sanno; registrazioni e trascrizioni, se si tengono, in
`privato/` (fuori da git).

## A. Portatile (microfono interno in MME, casse interne)

Lo script fa sul portatile lo stesso giro del satellite (rubinetto e VAD della stanza con
`durante_voce`, frasi di Calliope suonate dal `Riproduttore`, Whisper senza prompt, filtro
`eco.filtra` del server). Non serve il server. Chiudere il satellite del portatile (o almeno non
parlargli) durante la misura.

1. Volume delle casse a metà, poi alto. Stessa stanza silenziosa.
2. Senza nessuno che parla:
   `python prove/manuali/misura_eco_stanza.py --scenario muto --salva privato/eco-stanza`
   Si leggono `eco_residua_100` (obiettivo < 2), `righe_false` (obiettivo 0) e, per confronto,
   `eco_senza_filtro_100`.
3. Una persona legge il testo stampato a schermo mentre Calliope parla:
   `… --scenario lettura --salva privato/eco-stanza`, poi la stessa lettura a Calliope muta:
   `… --scenario lettura --senza-voce`. Le parole recuperate sono `wer_lettura` contro quella
   a voce spenta (la differenza è ciò che la voce di Calliope fa perdere).
4. Due persone chiacchierano: `… --scenario chiacchiera`.
5. Con `--campp` si rilegge anche la similitudine CAM++ dei segmenti con le sue frasi: se l'eco
   vera la tiene alta (oltre ~0,6) e le persone restano sotto ~0,35, il segnale (b) del § 5.3 si
   può aggiungere al filtro (oggi no: la misura simulata del 14/10 dice di no).
6. **Contrario**: casse esterne e microfono USB senza cancellazione. Al collegamento del
   satellite il log dice «eco sul saluto oltre 0,05, la stanza non ascolta mentre parlo»: il
   cancello (c) deve chiudersi da solo. Con lo script, `muto` mostra quanta eco passerebbe.

`--testi` stampa le righe (e con `--salva` le scrive nel file): solo per capire un caso, poi
cancellare.

## B. Telefono in auto (e in casa)

Il telefono non esegue lo script: si misura con il sistema vero.

1. Nel `calliope.locale.yaml` del server: `stanza: ombra`, `stanza_durante_voce: true`
   (`stanza_satelliti` col nome del telefono, o vuoto). Aggiornare il server e riaprire la
   pagina del telefono (lo stato `durante_voce` arriva nel benvenuto).
2. In auto in vivavoce, motore spento e poi acceso, volume medio e alto. Far parlare Calliope a
   lungo («Calliope, raccontami la storia di Torino», «leggimi le notizie») mentre:
   (1) nessuno parla, (2) una persona legge un testo noto, (3) due persone chiacchierano.
   Annotare l'ora di ogni prova.
3. `calliope stato --turni`, sezione «Stanza», riga «durante la voce (passo 5)» del telefono:
   segmenti, righe tenute, parole recuperate, scartate per eco, parole di Calliope tolte, **eco
   residua stimata ogni 100 parole dette** (stima per eccesso: conta anche chi ripete una sua
   parola). Nella prova (1) ogni riga tenuta durante la voce è una **riga falsa**.
4. Ripetere in casa (telefono sul tavolo, volume alto).
5. Spegnere con `stanza_durante_voce: false` se l'eco residua resta oltre 2 o le righe false non
   sono 0, e scrivere i numeri in `docs/aree/stt-tts.md` (voce datata).
