"""Banco della temperatura e del presence_penalty dell'agente (12/10/2026 sera, flusso
dell'agente a fasi, parte 1; ricerca docs/ricerche/2026-10-12-flusso-agente-fasi.md § 4.1 e
§ 5.3, domanda 6 accettata da chi amministra; area agenti-estensioni).

La scheda di Qwen3.6-35B-A3B consiglia, con il ragionamento acceso sul codice, temperatura
**0,6** e presence_penalty **0**; da noi `agenti_temperatura` è **0,4** e
`agenti_presence_penalty` 0 per «codice» e 0,5 per «estensione» (misurato l'11/10 su una sola
passata, prove/manuali/misura_presence_penalty.py). Qui si confrontano **lavori interi**, non
una passata: per ogni combinazione di temperatura e presence_penalty, tre casi veri riscritti
con nomi di fantasia, ripetuti:

1. **porte** (gioco, correzione): il gioco delle porte di Borgofiore con il genere di difetto
   del 12/10 (allora logica.js restituiva l'esito annidato e gioco.js lo leggeva al primo
   livello; dal 14/10, con la macchina a stati e senza gioco.js, l'esito mostra il mostro della
   porta accanto), e la segnalazione della persona. Accettazione: un test nascosto che apre il
   gioco nel DOM finto (apriGioco), tocca «2 giocatori» e la prima porta e legge «Fantasmino» e
   «+3 punti».
2. **convertitore** (estensione nuova): un convertitore di distanze con un valore di due parole
   con l'accento («unità astronomiche»). Accettazione: test nascosto con CalliopeFinta, cinque
   esempi dato → risultato (10 miglia in chilometri, un miglio nautico in metri, due unità
   astronomiche in chilometri, 12 pollici in piedi, un'unità che non c'è).
3. **programma** (Python): «rinomina le foto per data» (c01 di prove/prova_lavori.py, con il
   suo test nascosto).
4. **media** (Python a riga di comando, 17/10, issue #10): «media voti» con gli argomenti, la
   virgola decimale e il voto fuori da 1 a 10. È il genere di programma per cui l'analisi prima
   del codice scrive gli esempi (`agenti/accettazione.py`); l'accettazione nascosta cerca da sé
   il programma e lo esegue con tre casi. Il banco accende per questo caso, in memoria,
   `agenti_accettazione_programmi_sempre` (gli esempi anche fuori da uno sviluppo). Non è tra
   i casi di serie: `--casi media` (o `porte,convertitore,programma,media`).
5. **tris2** (gioco nuovo, 18/10, issue #174, tra i casi di serie): il tris per due con
   giocatori min = max = 2, il caso vero su cui l'agente ha girato a vuoto per cinque giri (i
   suoi test non uscivano dalla fase «preparazione»: con min = max se ne esce solo con
   «Inizia»). Accettazione: un test nascosto che parte dalla preparazione, tocca «Inizia», gioca
   1, 4, 2, 5, 3 con il comando «casella» e legge la fine con un punto. Riferimento: il tris
   delle prove dei giochi (`prove/giochi/tris`) con due giocatori fissi. Il criterio di #174:
   chiuso in al più 2 giri (`--casi tris2 --giri 2`). Dal 19/10 (#186) un gioco nuovo parte
   dai file di partenza già verdi (agenti/scheletri.py) con min e max dell'analisi prima del
   codice; il banco, che non apre uno sviluppo, mette nel lavoro i giocatori del caso (2–2)
   come li direbbe l'analisi. Dal 20/10 sera (#198, revisione della PR #199) l'accettazione
   nascosta ha dieci test: i due di prima con lo stesso nome (per il confronto con i banchi di
   prima) e gli otto punti di tris-nudo con lo stesso nome (la partita nuova e a chi tocca, mosse
   alternate, casella occupata o fuori da 1–9 rifiutata, tre in fila in riga e poi niente mosse,
   colonna, diagonale vinta anche dal secondo, pareggio, «ancora» con la partita vuota), giocati
   con apriGioco dalla preparazione; la richiesta e i requisiti dicono anche chi comincia, la
   casella già presa e niente segni a partita finita, come quella di tris-nudo.
6. **tris-nudo** (programma JavaScript, 20/10, issue #198 parte 2, non tra i casi di serie): lo
   stesso tris per due senza la macchina a stati né il contratto dei giochi, il tetto di quanto
   sa fare il modello fuori dal nostro ambiente dei giochi (non un'alternativa: niente voce,
   palco né manifesto). Un lavoro «codice»: `tris.js` in CommonJS con cinque funzioni pure dette
   nella richiesta (`nuovaPartita()`, `mossa(stato, casella)` che restituisce lo stato nuovo e
   lancia un errore sulla casella occupata, fuori da 1–9 o a partita finita, `vincitore`,
   `pareggio`, `aChiTocca`), i test dell'agente con node:test. Accettazione nascosta: gli stessi
   dieci punti di tris2 con lo stesso nome (al posto della preparazione, che qui non c'è, la
   partita nuova), sulle sole funzioni, senza guardare dentro lo stato. Riferimento in
   `prove/programmi/tris`. Senza analisi prima del codice (fuori da uno sviluppo un programma
   non l'ha, come «programma»); «javascript» in `agenti_linguaggi` acceso in memoria per il solo
   caso se il locale non l'ha (sulla DGX è acceso dal 17/10).
7. **tris2-solo-logica** (gioco nuovo, 20/10 sera, issue #198, revisione dell'analisi nella PR
   #200, non tra i casi di serie): tris2 com'è (macchina, contratto e prompt di oggi, requisiti,
   analisi prima del codice, accettazione nascosta), ma la richiesta chiede solo manifesto,
   logica.js e logica.test.js sulle funzioni di GIOCO, niente gioco.test.js né test con
   apriGioco. Separa l'API dei test dei giochi (dove stava quasi ogni fallimento dei banchi dal
   14/10) dall'interfaccia della macchina. Dalla seconda revisione della PR #199 è A′ come nel
   § 7 dell'analisi («prompt, contratto e partenza senza gioco.test.js»), solo nel banco
   (Calliope non cambia): per il caso il banco passa da `solo_logica` il prompt del gioco, il
   contratto (anche CAPACITA.md nella cartella) e il «prossimo» dopo il piano, che senza diceva
   di leggere un gioco.test.js che non c'è. Restano le frasi su apriGioco che non chiedono di
   scriverlo (gli esempi dell'analisi in sola lettura, i rimandi di un errore). La riga ha
   `test_apri_gioco`: i test dell'agente con apriGioco (i *.test.js finali che lo chiamano, più
   un gioco.test.js scritto e poi tolto); **un lavoro di tris2-solo-logica con quel campo pieno
   non misura A′** e va letto a parte.

**Le partenze dei tre casi del tris** (20/10 sera; il banco usa quelle del servizio di main,
quindi dopo #197 cambiano con lui). tris2: i quattro file di partenza del servizio
(`agenti/scheletri.py`, `file_gioco` con 2–2 giocatori: il gioco d'esempio delle porte, con
l'esito a ogni mossa, manifesto, logica.js, logica.test.js e gioco.test.js) e il contratto in
sola lettura (CAPACITA.md); con l'analisi accesa anche i suoi esempi (accettazione.test.js, sola
lettura). tris2-solo-logica: gli stessi senza gioco.test.js. tris-nudo: la cartella vuota, con lo
scheletro del programma JavaScript nel prompt (programma.js con una somma e il suo test). **È uno
scostamento dal § 7**, che vuole tutti i casi dallo stesso gioco d'esempio scritto nella forma del
caso: un tris-nudo che partisse dalle porte riscritte come programma sarebbe un programma di
fantasia che nessuno chiede, e la partenza vera di un programma JavaScript, quella che il
servizio dà a chiunque, è lo scheletro nel prompt; tris-nudo è il tetto del modello con l'harness
dei programmi com'è, non una forma alternativa dei giochi. Le altre differenze sono quelle che il
banco misura: il prompt di un gioco è circa 2,5 volte quello di un programma (revisione della PR
#199).

**Come si confrontano** (20/10 sera, revisioni delle PR #199 e #200). Sulla DGX, solo dopo
l'unione di #197 (il contratto dell'esito e gli esempi del tris) e a DGX libera, 10 ripetizioni
obbligatorie, il comando di decisione:

       … banco_temperatura.py --temperature config --presence 0.5 --accettazione no \\
           --casi tris2,tris2-solo-logica,tris-nudo --giri 2 --ripetizioni 10 \\
           --uscita ~/banco-tris

`--accettazione no`, come il § 7 («in tutti i casi … oppure in nessuno»): senza l'analisi prima
del codice nessuno dei tre casi ha esempi visibili né la chiusura al tetto o alla tappa con gli
esempi verdi, che oggi avrebbero solo i due tris2 (tris-nudo, un programma fuori da uno sviluppo,
non ha l'analisi) e li favorirebbero; e per la decisione di chi amministra del 20/10 sera
(scritta in #190, da fare) gli esempi non bloccano più la consegna né la chiusura al tetto
(quelli del tris scritti a mente erano sbagliati 11 su 11), quindi spegnerli non toglie un
controllo che conti. Lo stesso comando senza `--accettazione no` è
una misura in più, non la decisione. `--presence 0.5` per tutti e tre è uno **scostamento voluto
dal § 7**, che dice «lo stesso presence della Config»: con `--presence config` tris2 avrebbe
quello delle estensioni, 0,5, e tris-nudo quello del codice, 0, cioè non lo stesso.

La metrica è l'**accettazione nascosta** verde (colonna «acc.», 10/10), non «riuscito». I test
verdi («test acc.») aiutano a leggere, ma non partono da zero per tutti: i due tris2 partono da
**2/10** (il motore dà la preparazione con «Inizia» e la partita nuova; e in tris2 il rifiuto di
casella 0 e 10 e niente mosse a partita finita li dà il motore, in tris-nudo li scrive l'agente),
tris-nudo da **0/10**. Le regole usano il 10/10, che non ne risente. Per la regola 5 la riga ha
`firma_primo_errore` (il primo errore dei test dell'agente nel lavoro, come l'ha visto il ciclo,
fra le ultime 12 firme diverse), `firma_errore_finale` e `test_finali_passano` (i test
dell'agente rieseguiti dal banco sui file finali). Le regole di lettura, scritte prima di
girare (§ 7 di docs/ricerche/2026-10-20-giochi-macchina-o-interfaccia.md): alto vuol dire
≥ 8/10, basso ≤ 3/10. Nel caso peggiore, 8/10 contro 3/10, Fisher esatto dà p = 0,070 a due code
(0,035 a una): è una soglia di decisione, non una prova, e basta per scegliere A o A′, che
costano poco e si disfano; per aprire il prototipo di C serve il margine più forte (regola 4).
Le regole si applicano in quest'ordine, e vale la prima che si avvera:
1. tris2 alto: basta A (#197). Gli altri casi restano come misura, senza cambiare formato.
2. tris2-solo-logica alto e tris2 basso: il costo era l'API dei test. Si fa A′ (una PR), niente
   C.
3. tris-nudo basso: il limite è il modello o l'harness generico, non la macchina. Si tiene A e si
   guarda #175.
4. tris-nudo alto, tris2 e tris2-solo-logica bassi, con il margine più forte: tris-nudo a 9/10
   con gli altri due ≤ 3/10, oppure 8/10 con gli altri due ≤ 2/10 (p ≈ 0,02 a due code). Il costo
   è dell'interfaccia: si fa il prototipo e `tris-facciata` a 10 ripetizioni (alto: C, con una
   decisione nuova; basso: il costo sta nelle parti che restano, vista e comandi, e si torna ad A
   sui punti trovati dalle firme degli errori; intermedio: regola 5). Con il margine solo di
   8/10 contro 3/10 vale la regola 5.
5. Il caso intermedio (un caso fra 4/10 e 7/10, o due casi a meno di 5 punti su 10 l'uno
   dall'altro): nessuna decisione. Si leggono le firme del primo errore per classe e si rigirano
   i due casi in dubbio con altre 10 ripetizioni. Il rilancio si somma ai primi 10: si leggono 20
   lavori contro 20, con le stesse soglie in proporzione (alto ≥ 16/20, basso ≤ 6/20). Si rilancia
   una volta sola: se resta intermedio, vale la regola 1 con A.

Misure per lavoro: riuscito (consegna «fatto» e accettazione verde), passate, token (e di
ragionamento), minuti, giri a vuoto (passate fermate per ragionamento ripetuto, passate senza
file né test nuovi), test dell'agente, accettazione verde, e per la correzione l'esito della
riproduzione (agenti/riproduzione.py) e le regole scattate. Alla fine una tabella per
combinazione e caso, e `riepilogo.json` nella cartella d'uscita.

**Giri** (`--giri N`, 13/10; predefinito 1 = un lavoro solo, come prima). Con N > 1 lo stesso
budget di un lavoro si divide in N giri uguali: `agenti_max_passi` (24) diventa
round(24 / N) passate per giro (24 / 2 = 12; il banco stampa il conto e il totale), il tetto di
tempo `--minuti` diventa minuti / N per giro, e il budget dei token per tipo
(`agenti_token_lavoro`, dal 22/10; prima i token al minuto seguivano i minuti) diviso per N,
come `agenti_max_token`, se acceso. Così un lavoro a
giri ha lo stesso budget totale di passate, tempo e token di un lavoro con un giro solo, e il
confronto misura solo l'effetto della ripartenza. Al tetto di un giro il lavoro si ferma alla
**tappa** della modalità sviluppo (`lav.tappe`, `_tappa` in agenti/ciclo.py: il contesto
resta, compattato, e i file vanno nella cartella) e il banco chiama da sé `Lavori.continua`
senza nota («Hai un altro giro di lavoro… Riprendi da dove eri…»); all'ultimo giro le tappe
si spengono e il tetto chiude il lavoro come oggi («limite»). Nessuna modifica a Calliope:
`lav.tappe` è un attributo del lavoro, qui acceso dal banco. Misure in più per lavoro: giri
fatti, passate per giro, l'accettazione nascosta rifatta a ogni tappa sui file del giro, il
giro dell'accettazione verde e quello della consegna, e «sbloccato» (alla prima tappa
accettazione rossa, poi consegna «fatto» o accettazione verde in un giro dopo).

**Sulla DGX quando è libera** (nessun lavoro dell'agente in corso: usa lo stesso vLLM e il
container della sandbox), dalla cartella dei dati, con l'interprete di Calliope. Non cambia la
configurazione di nessuno (i valori si cambiano solo in memoria), i file restano nella cartella
d'uscita:

    cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale) \\
        && $V/.venv/bin/python $V/prove/manuali/banco_temperatura.py \\
           [--temperature 0.4,0.6] [--presence 0,0.5] [--ripetizioni 2] \\
           [--casi porte,convertitore,programma] [--minuti 20] [--giri 1] \\
           [--uscita ~/banco-temperatura]

A secco (nessun modello, anche sul portatile: il docker finto e il Node della macchina), per
controllare il banco stesso: ogni accettazione fallisce sul punto di partenza e passa sulla
soluzione di riferimento; e i giri con un agente finto (prove/ollama_finto.py): il giro 1 si
ferma alla tappa, il banco chiama continua e il giro 2 consegna; senza consegna l'ultimo giro
chiude con «limite»; con un giro solo il tetto chiude come prima; la consegna al tetto con il
servizio vero (13/10 sera): il codice giusto all'ultima passata, senza consegna, si chiude «fatto»
con gli esempi verdi; il contrario «limite» con gli esempi rossi; dal 14/10 le porte corrette
con il test del disegno senza consegna, «fatto» con la riproduzione al posto degli esempi, e il
contrario senza il test «limite».

    python prove/manuali/banco_temperatura.py --secco

**Valori della Config e analisi prima del codice** (13/10, flusso a fasi parte 2). In
`--temperature` e `--presence` la parola `config` prende i valori della Config (per
presence_penalty quelli per tipo di lavoro, `agenti_presence_penalty`): così il banco misura
l'installazione com'è. `--accettazione config|si|no` (predefinito `config`) lascia, accende o
spegne l'analisi prima del codice (`agenti_accettazione`, calliope/agenti/accettazione.py):
le domande prima di cominciare le risponde il banco da sé («Decidi tu, con la scelta più
comune.») e le conta; la riga ha `domande` e `analisi` (esempi di accettazione dell'agente,
verdi o rossi, secondi della passata). Gli esempi dell'agente sono un'altra cosa
dall'accettazione nascosta del banco, che resta il criterio di «riuscito».

**Esempi rieseguiti alla fine** (13/10 sera, L7: l'agente ha sistemato il convertitore
all'ultima delle 24 passate, il riepilogo diceva «esempi 7 rossi» e a mano passavano tutti).
Lo stato «esempi» della riga (`esempi_finali`) è quello rieseguito dal banco sui file finali del
lavoro, in una sandbox nuova, con il file degli esempi preso dalla sandbox del lavoro (è in sola
lettura e non va nella cartella del risultato). La riga ha anche `consegna_al_tetto`: il tetto
toccato quando Calliope ha chiuso il lavoro da sé con gli esempi verdi (agenti/ciclo.py).

**I motivi nella riga** (19/10, issue #9, passo 0 di docs/ricerche/2026-10-19-solidita-harness-
sviluppo.md): prima si contavano a mano dal log. Nell'`analisi` i valori nominati per input
(`nominati`), i controlli «si riconosce» in più (`valori`), gli esempi tolti contro la richiesta
per genere (`tolti`: fuori, numero, contiene; per un programma anche dati) e quanti esempi
tenuti hanno il `calcolo` rifatto dal codice (`con_calcolo`). Poi `regole` (da `lav.segnali`,
con `agente_ragionamento_ripetuto` e `agente_riscrittura_ripetuta`), `segnali_giro` di fine
lavoro (senza_novita, senza_progressi, ripetizioni, riscritti), `limite` (il tipo del Limite di
un lavoro finito «limite»: passate, tempo, token, a_vuoto; dal 19/10 con #180 anche `prosa`,
più di PROSA_MAX passate di fila senza strumenti, e `consegna_rossa`, la consegna con i test
rossi; dal 20/10 con #185 `troncata`, più di TRONCATE_MAX passate di fila con l'uscita troncata a
max_tokens; altro) e, solo per un lavoro finito «limite», `al_tetto_no` con `al_tetto_no_tipo`
(perché al tetto Calliope non l'ha chiuso da sé: «mancano i file che la consegna chiede»,
«esempi di accettazione rossi», «correzione non riprodotta»…). `prosa_no`: l'ultimo no dopo due
passate di sola prosa con lo stato consegnabile (#180), che non ferma il lavoro. Il criterio
«0 "mancano i file" con l'accettazione verde» è `al_tetto_no` contro `accettazione`.

**Le partenze vere** (20/10, issue #192, banco del 20/10 a due giri: 1/6). Le porte partono con
il `gioco.test.js` della forma della partenza (l'apriGioco vero dalla preparazione), come una
versione di un gioco dopo #186. tris2 ha l'analisi prima del codice del servizio come in uno
sviluppo (`SviluppoBanco`, con i requisiti del caso: gli esempi di accettazione e i giocatori),
così al tetto o alla tappa il codice può chiudere il lavoro da sé; con `--accettazione no`
«saltata» e i giocatori del caso, come prima. Dal 20/10 una tappa con lo stato consegnabile si
chiude «fatto» (`consegna_al_tetto` «tappa»); `tappa_no` nella riga dice perché no.

**Il profilo dell'agente** (22/10, #225, per #175): `--agenti-profilo NOME` sceglie in memoria
un profilo di `PROFILI_AGENTE` (calliope/config.py: modello, indirizzo e tetti tarati sulla
velocità), come la riga `agenti_profilo` del locale; senza, quello della configurazione. I tetti
in token sono gli stessi per tutti i profili, quindi due modelli si confrontano a parità di
budget: cambia solo il tetto di tempo, che è di sicurezza. `--minuti` vuoto (di serie dal 22/10;
prima 20) = il tempo del profilo (55 minuti con quello di serie, 375 con il denso da 27B). La
riga di ogni lavoro ha `profilo`, `velocita_profilo` (token/s scritti nel profilo, misurati o
stimati) e `token_s` (token generati / secondi del lavoro); la tabella e `riepilogo.json`
(`per_riuscito`) danno token, minuti e token/s per lavoro riuscito, per variante.

Durata: un lavoro dura 3–15 minuti; con i valori predefiniti 2 × 2 × 2 × 3 = 24 lavori, da 2 a
4 ore. Per una prima idea: --ripetizioni 1 --casi porte,convertitore (8 lavori).
"""

import argparse
import datetime
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))
sys.path.insert(0, str(RADICE / "prove"))

# ═══════════════════════════ i casi ═══════════════════════════

# 1. Le porte di Borgofiore (il difetto vero del 12/10, prove/prova_fasi_agente.py)
def _porte():
    import prova_fasi_agente as F
    return F


PROBLEMA_PORTE = ("toccando la prima porta si vede la caramella e «Nessun punto!», ma i punti "
                  "salgono di tre: il mostro che si vede non è quello della porta")
COMPITO_PORTE = ("Il gioco «Le porte di Borgofiore» da 2 a 4 giocatori: si sceglie in quanti, "
                 "poi a turno ogni giocatore tocca una porta; dietro c'è un mostro che vale dei punti "
                 "(il Fantasmino 3, il Pipistrello 2) o una caramella che non ne vale. Dopo ogni "
                 "porta si vede cosa c'era dietro, con il nome, e i punti presi («+3 punti!» o "
                 "«Nessun punto!»), e il punteggio dei giocatori.")
ACCETTAZIONE_PORTE = """const { test } = require("node:test");
const assert = require("node:assert");
test("ACC porte: toccando la prima porta si vedono il mostro e i suoi punti", async () => {
  const g = await apriGioco({ seme: 3 });
  await g.tocca("2 giocatori");
  await g.tocca("Porta 1");
  assert.match(g.testo(), /Fantasmino/);
  assert.match(g.testo(), /\\+\\s*3 punti/);
});
"""
# La partita vera nella versione di prima (20/10, #192): dopo #186 un gioco consegnato ha il suo
# gioco.test.js della forma della partenza (agenti/scheletri.py, TEST_GIOCO_PARTENZA), con
# l'apriGioco vero dalla preparazione. Verde anche sul gioco rotto: guarda i punti e i turni, non
# il mostro che si vede. Prima il banco delle porte partiva senza
TEST_GIOCO_PRIMA_PORTE = """const { test } = require("node:test");
const assert = require("node:assert");
// La partita vera con la macchina di Calliope: apriGioco e creaCaso ci sono già, senza require.
// Ogni partita comincia nella fase «preparazione»: con min < max si sceglie in quanti

test("la partita comincia dalla preparazione", async () => {
  const g = await apriGioco({ seme: 1 });
  assert.strictEqual(g.stato().fase, "preparazione");
  await g.tocca("2 giocatori");
  assert.strictEqual(g.stato().fase, "turno");
  assert.strictEqual(g.stato().giocatori.length, 2);
});

test("una porta aperta: il punto e poi tocca all'altro", async () => {
  const g = await apriGioco({ seme: 1, inizia: true, giocatori: 2 });
  await g.tocca("Porta 1");
  assert.strictEqual(g.stato().fase, "esito");
  await g.comando("avanti");
  const s = g.stato();
  assert.strictEqual(s.fase, "turno");
  assert.strictEqual(s.tocca, "Giocatore 2");
  assert.deepStrictEqual(s.giocatori.map((x) => x.punti), [3, 0]);
  assert.deepStrictEqual(s.comandi.porta, [2, 3]);
});

test("aperte tutte le porte la partita finisce", async () => {
  const g = await apriGioco({ seme: 1, inizia: true, giocatori: 2 });
  for (let k = 0; k < 50 && g.stato().fase !== "fine"; k++) {
    if (g.stato().fase === "esito") await g.comando("avanti");
    else await g.comando("porta", g.stato().comandi.porta[0]);
  }
  const s = g.stato();
  assert.strictEqual(s.fase, "fine");
  assert.strictEqual(s.giocatori.reduce((t, x) => t + x.punti, 0), 5);
});
"""

# 2. Il convertitore (estensione nuova, un valore di due parole con l'accento)
COMPITO_CONVERTITORE = (
    "Un'estensione «Convertitore di distanze» (nome convertitore_distanze): converte un valore "
    "tra unità di lunghezza: metri, chilometri, miglia, miglia nautiche, piedi, pollici e unità "
    "astronomiche, con i nomi in italiano anche al singolare («miglio nautico», «unità "
    "astronomica»), maiuscole o minuscole. Input del manifesto: valore (number), da (string), "
    "a (string). Restituisce da_dire con il risultato in italiano (virgola decimale, al più "
    "quattro cifre decimali) e «risultato» con il numero. Se un'unità non la conosce, "
    "«trovato»: false e da_dire lo dice. Niente rete.")
ACCETTAZIONE_CONVERTITORE = '''import unittest
from calliope_estensione import CalliopeFinta
from estensione import esegui


def conv(valore, da, a):
    return esegui({"valore": valore, "da": da, "a": a}, CalliopeFinta())


class Accettazione(unittest.TestCase):
    def test_acc_miglia_in_chilometri(self):
        self.assertAlmostEqual(conv(10, "miglia", "chilometri")["risultato"], 16.0934, places=2)

    def test_acc_miglio_nautico_in_metri(self):
        self.assertAlmostEqual(conv(1, "miglio nautico", "metri")["risultato"], 1852, places=1)

    def test_acc_unita_astronomiche(self):
        r = conv(2, "Unità astronomiche", "chilometri")["risultato"]
        self.assertAlmostEqual(r / 299195741.4, 1, places=5)

    def test_acc_pollici_in_piedi(self):
        self.assertAlmostEqual(conv(12, "pollici", "piedi")["risultato"], 1, places=3)

    def test_acc_unita_sconosciuta(self):
        out = conv(3, "leghe marine", "metri")
        self.assertIs(out.get("trovato"), False)
        self.assertTrue(str(out.get("da_dire") or "").strip())
'''
RIFERIMENTO_CONVERTITORE = '''import unicodedata

METRI = {"metro": 1.0, "metri": 1.0, "chilometro": 1000.0, "chilometri": 1000.0,
         "miglio": 1609.344, "miglia": 1609.344, "miglio nautico": 1852.0,
         "miglia nautiche": 1852.0, "piede": 0.3048, "piedi": 0.3048, "pollice": 0.0254,
         "pollici": 0.0254, "unita astronomica": 149597870700.0,
         "unita astronomiche": 149597870700.0}


def _norm(s):
    t = unicodedata.normalize("NFD", str(s or "").lower().strip())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


def esegui(dati, calliope):
    da, a = _norm(dati.get("da")), _norm(dati.get("a"))
    if da not in METRI or a not in METRI:
        return {"da_dire": "Non conosco questa unità.", "trovato": False}
    r = float(dati.get("valore") or 0) * METRI[da] / METRI[a]
    return {"da_dire": f"Sono {round(r, 4):g} {a}.".replace(".", ",", 1), "risultato": r}
'''

# 3. Il programma: c01 di prove/prova_lavori.py
RIFERIMENTO_PROGRAMMA = '''import datetime
import os
import re


def rinomina_cartella(cartella):
    nuovi = []
    for n in sorted(os.listdir(cartella)):
        p = os.path.join(cartella, n)
        if not os.path.isfile(p) or not n.lower().endswith(".jpg"):
            continue
        if re.match(r"^\\d{4}-\\d{2}-\\d{2}_", n):
            continue
        d = datetime.date.fromtimestamp(os.path.getmtime(p)).isoformat()
        os.rename(p, os.path.join(cartella, f"{d}_{n}"))
        nuovi.append(f"{d}_{n}")
    return sorted(nuovi)
'''


# 4. Un programma a riga di comando (17/10, #10: gli esempi per i programmi). L'accettazione
# nascosta cerca da sé il programma (il nome lo sceglie l'agente o l'analisi) e lo esegue nello
# stesso processo, come gli esempi (la sandbox non lascia avviare processi)
COMPITO_MEDIA = (
    "Un programma Python «media voti»: riceve i voti come argomenti (numeri da 1 a 10, anche con "
    "la virgola, per esempio 6,5) e stampa la media con due decimali. Se un voto è fuori da 1 a "
    "10 dice che il voto non è valido ed esce con un codice d'errore. Senza argomenti usa dei "
    "voti d'esempio.")
ACCETTAZIONE_MEDIA = r'''import contextlib
import io
import os
import re
import runpy
import sys
import unittest


def programmi():
    for n in sorted(os.listdir(".")):
        if n.endswith(".py") and not n.startswith(("test", "accettazione")):
            if "__name__" in open(n, encoding="utf-8").read():
                yield n


def esegui(prog, args):
    out = io.StringIO()
    vecchi = sys.argv
    sys.argv = [prog, *args]
    codice = 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            runpy.run_path(prog, run_name="__main__")
    except SystemExit as e:
        codice = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception:
        codice = 1
    finally:
        sys.argv = vecchi
    return out.getvalue(), codice


def numeri(t):
    return [float(x.replace(",", ".")) for x in re.findall(r"-?\d+(?:[.,]\d+)?", t)]


def giusto(prog):
    u, c = esegui(prog, ["5", "8", "9"])
    if c != 0 or not any(abs(x - 7.33) < 0.006 for x in numeri(u)):
        return False
    u, c = esegui(prog, ["6,5", "8"])
    if c != 0 or not any(abs(x - 7.25) < 0.006 for x in numeri(u)):
        return False
    u, c = esegui(prog, ["11", "8"])
    return c != 0 and "valid" in u.lower()


class Accettazione(unittest.TestCase):
    def test_acc_media(self):
        self.assertTrue(any(giusto(p) for p in programmi()), "nessun programma calcola la media "
                        "e rifiuta il voto 11")
'''
RIFERIMENTO_MEDIA = '''import sys


def main(argv):
    voti = [float(x.replace(",", ".")) for x in argv] if argv else [7.0, 8.0]
    for v in voti:
        if not 1 <= v <= 10:
            print(f"Il voto {v:g} non è valido: deve essere da 1 a 10.")
            sys.exit(1)
    print(f"La media è {sum(voti) / len(voti):.2f}".replace(".", ","))


if __name__ == "__main__":
    main(sys.argv[1:])
'''


# 5. Il tris per due (18/10, #174): il gioco nuovo con giocatori min = max = 2, su cui il 18/10
# l'agente ha girato a vuoto per cinque giri (i suoi test davano per scontato che la partita
# cominciasse in «turno»; con min = max dalla preparazione si esce solo con «Inizia»)
COMPITO_TRIS2 = (
    "Il gioco del tris per due giocatori sugli schermi (nome tris_due): sempre esattamente due "
    "giocatori, che a turno mettono X e O su una griglia 3×3 toccando una casella o dicendo "
    "«casella N» (il comando si chiama casella, con N da 1 a 9, da sinistra a destra e "
    "dall'alto in basso). Comincia il primo giocatore con X. Una casella già presa non si può "
    "prendere, e a partita finita non si mettono più segni. Chi mette tre segni in fila (riga, "
    "colonna o diagonale) vince e prende un punto; con la griglia piena è pareggio; poi si può "
    "giocare ancora.")
# I requisiti come li scriverebbe l'analisi di uno sviluppo (20/10, #192): con questi l'analisi
# prima del codice scrive gli esempi di accettazione del gioco, e al tetto o alla tappa il codice
# può chiudere il lavoro da sé. Fuori da uno sviluppo un gioco salta l'analisi, e il banco
# metteva «saltata»: «senza esempi di accettazione» sempre
REQUISITI_TRIS2 = [
    {"testo": "Due giocatori, sempre esattamente due", "nucleo": True, "si_puo": True},
    {"testo": "Griglia 3×3: a turno si mette X o O toccando una casella o dicendo «casella N», "
              "con N da 1 a 9 da sinistra a destra e dall'alto in basso", "nucleo": True,
     "si_puo": True},
    # 20/10 sera (#198, revisione della PR #199): come la richiesta di tris-nudo
    {"testo": "Comincia il primo giocatore con X; una casella già presa non si può prendere, e "
              "a partita finita non si mettono più segni", "nucleo": True, "si_puo": True},
    {"testo": "Tre segni in fila (riga, colonna o diagonale) vincono e danno un punto",
     "nucleo": True, "si_puo": True},
    {"testo": "Con la griglia piena senza tre in fila è pareggio", "nucleo": False,
     "si_puo": True},
    {"testo": "Finita la partita si può giocare ancora", "nucleo": False, "si_puo": True}]
ACCETTAZIONE_TRIS2 = """const { test } = require("node:test");
const assert = require("node:assert");
async function mossa(g, n) {
  while (g.stato().fase === "esito") await g.comando("avanti");
  await g.comando("casella", n);
}
test("ACC tris2: si parte dalla preparazione, «Inizia», due giocatori", async () => {
  const g = await apriGioco({ seme: 1 });
  assert.strictEqual(g.stato().fase, "preparazione");
  await g.tocca("Inizia");
  assert.notStrictEqual(g.stato().fase, "preparazione");
  assert.strictEqual(g.stato().giocatori.length, 2);
});
test("ACC tris2: tre in fila vince, la partita finisce con un punto", async () => {
  const g = await apriGioco({ seme: 1 });
  await g.tocca("Inizia");
  for (const n of [1, 4, 2, 5, 3]) await mossa(g, n);
  await g.avanza(20000);
  while (g.stato().fase === "esito") await g.comando("avanti");
  const s = g.stato();
  assert.strictEqual(s.fase, "fine");
  assert.deepStrictEqual(s.giocatori.map((x) => x.punti).sort(), [0, 1]);
});
// Dal 20/10 sera (#198, revisione della PR #199) gli stessi punti dell'accettazione di tris-nudo,
// giocati con apriGioco dalla preparazione: i due test di sopra restano con il loro nome, per il
// confronto con i banchi di prima
async function partita(...caselle) {
  const g = await apriGioco({ seme: 1 });
  await g.tocca("Inizia");
  for (const n of caselle) await mossa(g, n);
  return g;
}
async function finita(g) {
  await g.avanza(20000);
  while (g.stato().fase === "esito") await g.comando("avanti");
  return g.stato();
}
const chi = (s, i) => s.giocatori[i].nome;
test("ACC tris2: la partita nuova: tocca al primo, nessun vincitore", async () => {
  const s = (await partita()).stato();
  assert.strictEqual(s.tocca, chi(s, 0));
  assert.deepStrictEqual(s.giocatori.map((x) => x.punti), [0, 0]);
  assert.notStrictEqual(s.fase, "fine");
});
test("ACC tris2: le mosse si alternano", async () => {
  const g = await partita(5);
  assert.strictEqual(g.stato().tocca, chi(g.stato(), 1));
  await mossa(g, 1);
  assert.strictEqual(g.stato().tocca, chi(g.stato(), 0));
});
test("ACC tris2: la casella occupata o fuori da 1–9 è rifiutata", async () => {
  const g = await partita(5);
  await assert.rejects(() => g.comando("casella", 5));
  await assert.rejects(() => g.comando("casella", 0));
  await assert.rejects(() => g.comando("casella", 10));
  assert.strictEqual(g.stato().tocca, chi(g.stato(), 1));
});
test("ACC tris2: tre in fila in riga vince, poi non si gioca più", async () => {
  const s = await finita(await partita(1, 4, 2, 5, 3));
  assert.strictEqual(s.fase, "fine");
  assert.deepStrictEqual(s.giocatori.map((x) => x.punti), [1, 0]);
  assert.ok(!(s.comandi.casella || []).length);
});
test("ACC tris2: tre in fila in colonna vince", async () => {
  const s = await finita(await partita(1, 2, 4, 5, 7));
  assert.strictEqual(s.fase, "fine");
  assert.deepStrictEqual(s.giocatori.map((x) => x.punti), [1, 0]);
});
test("ACC tris2: tre in fila in diagonale vince anche il secondo", async () => {
  const s = await finita(await partita(2, 1, 3, 5, 4, 9));
  assert.strictEqual(s.fase, "fine");
  assert.deepStrictEqual(s.giocatori.map((x) => x.punti), [0, 1]);
  const t = await finita(await partita(3, 1, 5, 2, 7));
  assert.deepStrictEqual(t.giocatori.map((x) => x.punti), [1, 0]);
});
test("ACC tris2: la griglia piena senza tre in fila è pareggio", async () => {
  const s = await finita(await partita(1, 2, 3, 5, 4, 6, 8, 7, 9));
  assert.strictEqual(s.fase, "fine");
  assert.deepStrictEqual(s.giocatori.map((x) => x.punti), [0, 0]);
  const g = await partita(1, 2, 3);
  assert.notStrictEqual(g.stato().fase, "fine");
});
test("ACC tris2: si può giocare ancora, la partita nuova è vuota", async () => {
  const g = await partita(1, 4, 2, 5, 3);
  await finita(g);
  await g.comando("ancora");
  if (g.stato().fase === "preparazione") await g.tocca("Inizia");
  const s = g.stato();
  assert.strictEqual(s.tocca, chi(s, 0));
  assert.deepStrictEqual([...(s.comandi.casella || [])].sort((a, b) => a - b),
                         [1, 2, 3, 4, 5, 6, 7, 8, 9]);
});
"""


# 6. Il tris nudo (20/10, issue #198, parte 2): lo stesso tris per due, ma come un programma
# JavaScript con funzioni pure e i test dell'agente, senza la macchina a stati né il contratto dei
# giochi. È il tetto di quanto sa fare il modello fuori dal nostro ambiente: dal 20/10 sera
# (revisione della PR #199) l'accettazione ha gli stessi dieci test di quella di tris2, con lo
# stesso nome dopo «ACC tris-nudo:», sulle funzioni e senza guardare dentro lo stato (lo stato
# ricevuto intatto non si prova: in tris2 non ha un equivalente)
COMPITO_TRIS_NUDO = (
    "Un programma JavaScript per Node: il tris per due giocatori, X e O, su una griglia 3×3 con "
    "le caselle numerate da 1 a 9 da sinistra a destra e dall'alto in basso. Il file tris.js "
    "esporta con module.exports cinque funzioni pure: nuovaPartita() restituisce lo stato di una "
    "partita nuova (comincia X); mossa(stato, casella) mette il segno di chi tocca nella casella "
    "(un numero da 1 a 9) e restituisce lo stato nuovo senza cambiare quello che riceve, e se la "
    "casella è occupata, fuori da 1 a 9 o la partita è finita lancia un errore; vincitore(stato) "
    "dice \"X\" o \"O\" se uno dei due ha tre segni in fila (riga, colonna o diagonale), "
    "altrimenti null; pareggio(stato) è true con la griglia piena senza tre in fila; "
    "aChiTocca(stato) dice \"X\" o \"O\", e null a partita finita. Eseguito da solo gioca una "
    "partita d'esempio e stampa la griglia. Con i test.")
ACCETTAZIONE_TRIS_NUDO = """const { test } = require("node:test");
const assert = require("node:assert");
const T = require("./tris.js");
function gioca(...caselle) {
  return caselle.reduce((s, n) => T.mossa(s, n), T.nuovaPartita());
}
test("ACC tris-nudo: si parte dalla partita nuova, due giocatori X e O", () => {
  const s = T.nuovaPartita();
  assert.strictEqual(T.aChiTocca(s), "X");
  assert.strictEqual(T.aChiTocca(T.mossa(s, 1)), "O");
});
test("ACC tris-nudo: tre in fila vince, la partita finisce", () => {
  const s = gioca(1, 4, 2, 5, 3);
  assert.strictEqual(T.vincitore(s), "X");
  assert.ok(!T.aChiTocca(s));
});
test("ACC tris-nudo: la partita nuova: tocca al primo, nessun vincitore", () => {
  const s = T.nuovaPartita();
  assert.strictEqual(T.aChiTocca(s), "X");
  assert.ok(!T.vincitore(s));
  assert.ok(!T.pareggio(s));
});
test("ACC tris-nudo: le mosse si alternano", () => {
  const s1 = gioca(5);
  assert.strictEqual(T.aChiTocca(s1), "O");
  assert.strictEqual(T.aChiTocca(T.mossa(s1, 1)), "X");
});
test("ACC tris-nudo: la casella occupata o fuori da 1–9 è rifiutata", () => {
  const s = gioca(5);
  assert.throws(() => T.mossa(s, 5));
  assert.throws(() => T.mossa(s, 0));
  assert.throws(() => T.mossa(s, 10));
  assert.strictEqual(T.aChiTocca(s), "O");
});
test("ACC tris-nudo: tre in fila in riga vince, poi non si gioca più", () => {
  const s = gioca(1, 4, 2, 5, 3);
  assert.strictEqual(T.vincitore(s), "X");
  assert.ok(!T.pareggio(s));
  assert.ok(!T.aChiTocca(s));
  assert.throws(() => T.mossa(s, 9));
});
test("ACC tris-nudo: tre in fila in colonna vince", () => {
  assert.strictEqual(T.vincitore(gioca(1, 2, 4, 5, 7)), "X");
});
test("ACC tris-nudo: tre in fila in diagonale vince anche il secondo", () => {
  assert.strictEqual(T.vincitore(gioca(2, 1, 3, 5, 4, 9)), "O");
  assert.strictEqual(T.vincitore(gioca(3, 1, 5, 2, 7)), "X");
});
test("ACC tris-nudo: la griglia piena senza tre in fila è pareggio", () => {
  const s = gioca(1, 2, 3, 5, 4, 6, 8, 7, 9);
  assert.ok(!T.vincitore(s));
  assert.strictEqual(T.pareggio(s), true);
  assert.ok(!T.aChiTocca(s));
  assert.ok(!T.pareggio(gioca(1, 2, 3)));
});
test("ACC tris-nudo: si può giocare ancora, la partita nuova è vuota", () => {
  gioca(1, 4, 2, 5, 3);
  for (let n = 1; n <= 9; n++) {
    const s = T.nuovaPartita();
    assert.strictEqual(T.aChiTocca(s), "X");
    assert.doesNotThrow(() => T.mossa(s, n));
  }
});
"""


# 7. Il tris2 della sola logica (20/10 sera, issue #198, revisione dell'analisi nella PR #200):
# la macchina, il contratto, il prompt, i requisiti, l'analisi e l'accettazione nascosta di
# tris2, ma all'agente si chiede solo la logica e i test della logica, niente gioco.test.js con
# apriGioco (la partita intera la provano la prova di fumo e l'accettazione). Separa l'API dei
# test dei giochi (apriGioco, dove stava quasi ogni fallimento dei banchi dal 14/10)
# dall'interfaccia della macchina. La partenza è quella di tris2 senza gioco.test.js
COMPITO_TRIS2_SOLO_LOGICA = (
    COMPITO_TRIS2 + " Scrivi solo la logica: manifesto.json, logica.js e i test della logica in "
    "logica.test.js, sulle funzioni di GIOCO (nuovaPartita, attivi, mosse) chiamate "
    "direttamente; niente gioco.test.js né altri test con apriGioco: la partita intera la "
    "provano la prova di fumo e Calliope.")


def riferimento_tris2_solo_logica() -> dict:
    """Il riferimento di tris2 con i test della sola logica del tris (prove/giochi/tris)."""
    cartella = RADICE / "prove" / "giochi" / "tris"
    return {**riferimento_tris2(),
            "logica.test.js": (cartella / "logica.test.js").read_text(encoding="utf-8")}


def senza_gioco_test(svc):
    """I file di partenza del gioco come li scrive il servizio, poi via gioco.test.js (20/10
    sera, tris2-solo-logica): la stessa partenza di tris2 senza il test con apriGioco. Solo per
    il caso: il caso dopo rimette quella vera (`partenza_vera`)."""
    vera = type(svc)._prepara_cartella_gioco

    def prepara(lav, sb, presi=()):
        vera(svc, lav, sb, presi)
        p = Path(sb.root) / "gioco.test.js"
        if p.is_file():
            p.unlink()
    svc._prepara_cartella_gioco = prepara


def partenza_vera(svc):
    svc.__dict__.pop("_prepara_cartella_gioco", None)
    svc.agente.__dict__.pop("_piano", None)
    import calliope.estensioni.contratto as C
    import calliope.estensioni.prompt as P
    for mod, nome in ((C, "testo"), (P, "sistema_estensione")):
        vera = getattr(getattr(mod, nome), "_banco_vera", None)
        if vera is not None:
            setattr(mod, nome, vera)


def solo_logica(t: str) -> str:
    """Il prompt, il contratto e il suggerimento dopo il piano di un gioco senza gioco.test.js
    (20/10 sera, seconda revisione della PR #199: A′ come nel § 7 dell'analisi, «prompt,
    contratto e partenza senza gioco.test.js»). Solo nel banco: Calliope non cambia. Restano le
    frasi su apriGioco che non chiedono di scriverlo (il seme della prova di fumo, i rimandi di
    un errore)."""
    import re
    t = t.replace("e i test logica.test.js e gioco.test.js.",
                  "e i test della sola logica in logica.test.js (niente test con apriGioco: la "
                  "partita intera la provano la prova di fumo e Calliope).")
    t = re.sub(r" e gioco\.test\.js \(la partita vera con la macchina, apriGioco: [^)]*\)\. "
               r"esegui_test li fa girare", ". esegui_test lo fa girare", t)
    t = re.sub(r"In gioco\.test\.js, dopo apriGioco e prima delle mosse,.*?dalla fase "
               r"d'inizio\. ", "", t, flags=re.S)
    t = "\n".join(r for r in t.split("\n") if not r.startswith("- g.stato() in gioco.test.js"))
    t = t.replace("in apriGioco e nella prova di fumo ha un seme fisso (apriGioco({ seme: 7 }): "
                  "la stessa partita a ogni esecuzione)",
                  "nella prova di fumo ha un seme fisso (la stessa partita a ogni esecuzione)")
    t = t.replace("ci sono già quattro file", "ci sono già tre file")
    t = t.replace("), logica.test.js e gioco.test.js (la partita vera con apriGioco, che comincia "
                  "dalla preparazione).", ") e logica.test.js.")
    return t.replace("logica.js, logica.test.js, gioco.test.js)", "logica.js, logica.test.js)")


def con_solo_logica(svc):
    """tris2-solo-logica: prompt e contratto (anche CAPACITA.md) e il «prossimo» dopo il piano
    passati da `solo_logica`, per il solo caso (`partenza_vera` li rimette)."""
    import calliope.estensioni.contratto as C
    import calliope.estensioni.prompt as P
    for mod, nome in ((C, "testo"), (P, "sistema_estensione")):
        vera = getattr(mod, nome)

        def finta(*a, _vera=vera, **k):
            return solo_logica(_vera(*a, **k))
        finta._banco_vera = vera
        setattr(mod, nome, finta)
    piano = svc.agente._piano

    def piano_finto(*a, **k):
        out, chiusura = piano(*a, **k)
        if isinstance(out, dict) and isinstance(out.get("prossimo"), str):
            out["prossimo"] = solo_logica(out["prossimo"])
        return out, chiusura
    svc.agente._piano = piano_finto


def test_apri_gioco(file: dict, lav) -> list[str]:
    """I test dell'agente con apriGioco (20/10 sera, seconda revisione della PR #199): i
    *.test.js finali che lo chiamano, senza gli esempi dell'analisi e l'accettazione del banco,
    più un gioco.test.js scritto durante il lavoro anche se poi tolto. In tris2-solo-logica un
    lavoro con questo campo pieno non misura A′."""
    import re
    fuori = {"accettazione.test.js", "accettazione_banco.test.js"}
    out = {n for n, t in file.items() if n.endswith(".test.js") and Path(n).name not in fuori
           and re.search(r"\bapriGioco\s*\(", str(t))}
    seg = lav.segnali if isinstance(getattr(lav, "segnali", None), dict) else {}
    out |= {str(p) for p in (seg.get("scritture") or {})
            if Path(str(p)).name == "gioco.test.js"}
    return sorted(out)


def test_finali(sandbox_nuova, file: dict, caso: dict) -> dict:
    """I test dell'agente rieseguiti dal banco sui file finali (20/10 sera, seconda revisione
    della PR #199, § 7 dell'analisi: «i rossi dei test dell'agente alla fine e la firma del primo
    errore»): il conto, i rossi e la firma del primo fallimento (`firma_errore` del ciclo)."""
    from calliope.agenti.ciclo import firma_errore
    fuori = {"accettazione.test.js", "accettazione_banco.test.js", "test_accettazione.py",
             caso["accettazione"][0]}
    sb = sandbox_nuova()
    for rel, testo in file.items():
        if Path(rel).name in fuori:
            continue
        try:
            sb.scrivi(rel, testo)
        except Exception:  # noqa: BLE001 — un nome non ammesso: si salta
            pass
    if caso["tipo"] == "estensione" and not caso.get("gioco"):
        import calliope.estensioni as E
        shutil.copy(Path(E.__file__).parent / "_ospite.py", sb.root / "calliope_estensione.py")
    for rel, testo in (caso.get("aiuto") or {}).items():
        sb.scrivi(rel, testo)
    try:
        r = sb.test()
    except Exception as e:  # noqa: BLE001 — nessun test
        return {"passano": False, "esito": None, "firma": f"{type(e).__name__}: {e}"[:160]}
    return {"passano": bool(r.get("passano")), "esito": r.get("esito"),
            "firma": firma_errore(r)}


def riferimento_tris_nudo() -> dict:
    """Il tris nudo giusto (prove/programmi/tris): tris.js e i test come li scriverebbe l'agente."""
    cartella = RADICE / "prove" / "programmi" / "tris"
    return {n: (cartella / n).read_text(encoding="utf-8") for n in ("tris.js", "tris.test.js")}


# Il contrario del riferimento per --secco: la casella occupata si sovrascrive
TRIS_NUDO_SOVRASCRIVE = ('  if (stato.caselle[casella - 1] !== null) throw new Error(`la casella '
                         '${casella} è occupata`);\n')


TEST_SENZA_INIZIA = """const { test } = require("node:test");
test("ACC tris2 come l'agente: la prima mossa subito", async () => {
  const g = await apriGioco({ seme: 1 });
  await g.comando("casella", 1);
});
"""


def riferimento_tris2() -> dict:
    """Il tris delle prove dei giochi (prove/giochi/tris) con giocatori min = max = 2."""
    cartella = RADICE / "prove" / "giochi" / "tris"
    m = json.loads((cartella / "manifesto.json").read_text(encoding="utf-8"))
    m["nome"], m["titolo"] = "tris_due", "Tris per due"
    m["scheda"]["giocatori"] = {"min": 2, "max": 2}
    return {"logica.js": (cartella / "logica.js").read_text(encoding="utf-8"),
            "manifesto.json": json.dumps(m, ensure_ascii=False, indent=1)}


def casi():
    """{nome: dict} con tipo, compito, file di partenza, accettazione e riferimento."""
    import prova_lavori as PL
    F = _porte()
    c01 = next(c for c in PL.CODICE if c[0] == "c01")
    prima = {"logica.js": F.GIOCO_ROTTO,
             "logica.test.js": F.TEST_LOGICA_PORTE,
             "gioco.test.js": TEST_GIOCO_PRIMA_PORTE,
             "manifesto.json": json.dumps(F.MANIFESTO_PORTE, ensure_ascii=False, indent=1)}
    return {
        "porte": {"tipo": "estensione", "gioco": True, "correzione": True,
                  "estensione": F.MANIFESTO_PORTE["nome"], "compito": COMPITO_PORTE,
                  "problema": PROBLEMA_PORTE, "prima": prima,
                  "accettazione": ("accettazione_banco.test.js", ACCETTAZIONE_PORTE),
                  "riferimento": {**prima, "logica.js": F.GIOCO_GIUSTO}},
        "convertitore": {"tipo": "estensione", "gioco": False, "correzione": False,
                         "estensione": None, "compito": COMPITO_CONVERTITORE, "prima": {},
                         "accettazione": ("test_accettazione_banco.py",
                                          ACCETTAZIONE_CONVERTITORE),
                         "riferimento": {"estensione.py": RIFERIMENTO_CONVERTITORE}},
        "programma": {"tipo": "codice", "gioco": False, "correzione": False, "estensione": None,
                      "compito": c01[1], "prima": dict(c01[2]),
                      "accettazione": ("test_nascosto_banco.py", c01[3]),
                      "aiuto": {"pytest_free_raises.py": PL.AIUTO_RAISES},
                      "riferimento": {"rinomina_foto.py": RIFERIMENTO_PROGRAMMA}},
        "media": {"tipo": "codice", "gioco": False, "correzione": False, "estensione": None,
                  "compito": COMPITO_MEDIA, "prima": {},
                  "accettazione": ("test_nascosto_banco.py", ACCETTAZIONE_MEDIA),
                  "riferimento": {"media_voti.py": RIFERIMENTO_MEDIA},
                  # Fuori da uno sviluppo gli esempi dei programmi si accendono così (17/10)
                  "programmi_sempre": True},
        # Il gioco nuovo (18/10, #174): dal 19/10 (#186) la cartella non è vuota, il servizio
        # ci scrive i file di partenza con i giocatori dell'analisi. Dal 20/10 (#192) l'analisi
        # prima del codice la fa il servizio, come in uno sviluppo, con questi requisiti
        # (`SviluppoBanco`); «giocatori» resta per --accettazione no e per --secco
        "tris2": {"tipo": "estensione", "gioco": True, "correzione": False,
                  "estensione": None, "compito": COMPITO_TRIS2, "prima": {},
                  "requisiti": REQUISITI_TRIS2,
                  "giocatori": {"min": 2, "max": 2},
                  "accettazione": ("accettazione_banco.test.js", ACCETTAZIONE_TRIS2),
                  "riferimento": riferimento_tris2()},
        # Il tris2 della sola logica (20/10 sera, #198): come tris2, la richiesta chiede solo
        # la logica e la partenza è senza gioco.test.js
        "tris2-solo-logica": {"tipo": "estensione", "gioco": True, "correzione": False,
                              "estensione": None, "compito": COMPITO_TRIS2_SOLO_LOGICA,
                              "prima": {}, "requisiti": REQUISITI_TRIS2,
                              "giocatori": {"min": 2, "max": 2}, "senza_gioco_test": True,
                              "accettazione": ("accettazione_banco.test.js", ACCETTAZIONE_TRIS2),
                              "riferimento": riferimento_tris2_solo_logica()},
        # Il tris nudo (20/10, #198): un programma JavaScript, la cartella vuota (lo scheletro
        # del programma è nel prompt), nessuna analisi prima del codice (fuori da uno sviluppo
        # un programma non l'ha, come «programma»). Il JavaScript dei programmi solo in memoria,
        # se il locale non l'ha acceso (sulla DGX acceso dal 17/10)
        "tris-nudo": {"tipo": "codice", "gioco": False, "correzione": False, "estensione": None,
                      "compito": COMPITO_TRIS_NUDO, "prima": {}, "linguaggi": ["javascript"],
                      "accettazione": ("accettazione_banco.test.js", ACCETTAZIONE_TRIS_NUDO),
                      "riferimento": riferimento_tris_nudo()},
    }


def vincoli_correzione(caso: dict) -> str:
    """I vincoli di una correzione come li compone sviluppo_correggi (tools/sviluppo.py)."""
    from calliope.tools.sviluppo import VINCOLO_CORREZIONE_GIOCO, VINCOLO_RIPRODUCI
    return ("È una CORREZIONE dello sviluppo «Le porte di Borgofiore»: cosa deve fare resta "
            "quello del compito. I file della versione che la persona ha provato sono già nella "
            "cartella: riparti da quelli, non riscrivere da zero. Collaudi che non vanno (dati "
            "→ esito): «aperto in prova sullo schermo» → la persona: "
            f"{caso['problema']}. Problema detto dalla persona: «{caso['problema']}»."
            + (VINCOLO_CORREZIONE_GIOCO if caso.get("gioco") else "") + VINCOLO_RIPRODUCI)


# ═══════════════════════════ l'accettazione ═══════════════════════════

def accettazione(sandbox_nuova, file: dict, caso: dict) -> dict:
    """I file del risultato più il test nascosto in una sandbox nuova: {"verde", "esito",
    "uscita"}. Per un'estensione anche il runtime con CalliopeFinta."""
    sb = sandbox_nuova()
    for rel, testo in file.items():
        try:
            sb.scrivi(rel, testo)
        except Exception:  # noqa: BLE001 — un nome non ammesso: si salta
            pass
    if caso["tipo"] == "estensione" and not caso.get("gioco"):
        # Dal pacchetto importato, non accanto al file (13/10: il banco lanciato da una copia
        # fuori dal repository, con PYTHONPATH sulla versione installata)
        import calliope.estensioni as E
        shutil.copy(Path(E.__file__).parent / "_ospite.py", sb.root / "calliope_estensione.py")
    for rel, testo in (caso.get("aiuto") or {}).items():
        sb.scrivi(rel, testo)
    nome, testo = caso["accettazione"]
    sb.scrivi(nome, testo)
    r = sb.test(nome)
    u = str(r.get("uscita") or "")
    # I test verdi su quelli dell'accettazione (20/10 sera, #198, revisione della PR #199): il
    # confronto tra tris2 e tris-nudo guarda quanti punti tornano, non solo verde o rosso. Per
    # JavaScript dai nomi «ACC …» (rossi anche quelli che non sono arrivati a girare: errore di
    # sintassi o di require), per Python dal conto del runner
    if nome.endswith(".js"):
        import re
        tutti = re.findall(r'test\("(ACC [^"]+)"', testo)
        passati = set(re.findall(r"^ok (ACC .+?)\s*$", u, re.M))
        rossi = [x for x in tutti if x not in passati]
        verdi, totali = len(tutti) - len(rossi), len(tutti)
        verde = "ok ACC " in u and "FALLITO ACC " not in u and not rossi
    else:
        e = r.get("esito") or {}
        totali = int(e.get("eseguiti") or 0)
        verdi = max(0, totali - int(e.get("falliti") or 0) - int(e.get("errori") or 0))
        rossi = None
        verde = bool(r.get("passano"))
    return {"verde": verde, "esito": r.get("esito"), "uscita": u[-1500:], "verdi": verdi,
            "totali": totali, "rossi": rossi}


def esempi_finali(sandbox_nuova, file: dict, caso: dict, stato: dict,
                  sandbox_lavoro: Path | None) -> bool | None:
    """Gli esempi di accettazione dell'agente (test_accettazione.py o accettazione.test.js,
    scritti dall'analisi prima del codice) rieseguiti dal banco sui file finali del lavoro, in
    una sandbox nuova (13/10 sera, L7 del banco: il riepilogo diceva «esempi 7 rossi» con lo
    stato di prima della correzione all'ultima passata, e a mano passavano tutti). Il file degli
    esempi è in sola lettura e non va nella cartella del risultato: si prende dalla sandbox del
    lavoro. None se il lavoro non li ha."""
    from calliope.agenti import accettazione as A
    st = dict(stato or {})
    nome = st.get("nome_file") or A.FILE
    p = Path(sandbox_lavoro) / nome if sandbox_lavoro else None
    if st.get("stato") != "pronta" or not st.get("file") or p is None or not p.is_file():
        return None
    sb = sandbox_nuova()
    for rel, testo in {**file, nome: p.read_text(encoding="utf-8")}.items():
        try:
            sb.scrivi(rel, testo)
        except Exception:  # noqa: BLE001 — un nome non ammesso: si salta
            pass
    if caso["tipo"] == "estensione" and not caso.get("gioco"):
        import calliope.estensioni as E
        shutil.copy(Path(E.__file__).parent / "_ospite.py", sb.root / "calliope_estensione.py")
    r = A.esegui(sb, {**st, "nome_file": nome})
    return bool(r and r["passano"])


def detto_esempi(r: dict) -> str:
    """«esempi 7 verdi» dalla riga: lo stato rieseguito alla fine, non l'ultimo dell'agente."""
    n = (r.get("analisi") or {}).get("esempi")
    if not n:
        return ""
    v = r.get("esempi_finali")
    return f", esempi {n} " + ("verdi" if v else "rossi" if v is False else "non eseguiti")


def file_di(cartella: Path) -> dict:
    out = {}
    for p in sorted(Path(cartella).rglob("*")):
        if p.is_file() and p.name != "lavoro.json" and not any(
                x.startswith(".") for x in p.relative_to(cartella).parts):
            try:
                out[p.relative_to(cartella).as_posix()] = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                pass
    return out


# ═══════════════════════════ a secco ═══════════════════════════

def secco() -> int:
    """Il banco controlla sé stesso: ogni accettazione fallisce sul punto di partenza e passa
    sulla soluzione di riferimento (docker finto e Node della macchina, come le prove)."""
    import prova_agente_guida as G
    tmp = Path(tempfile.mkdtemp(prefix="banco-temperatura-secco-"))
    n = [0]

    def nuova():
        n[0] += 1
        return G.sandbox(tmp, f"s{n[0]}")
    errori = 0
    try:
        for nome, caso in casi().items():
            if ((caso.get("gioco") or caso["accettazione"][0].endswith(".js"))
                    and not shutil.which("node")):
                print(f"SALTATO {nome}: node non c'è")
                continue
            partenza = dict(caso["prima"])
            if caso.get("giocatori"):
                # La partenza vera di un gioco nuovo (19/10, #186): i file che scrive il
                # servizio, verdi da soli (test e prova di fumo) ma non il gioco chiesto
                from calliope.agenti.scheletri import file_gioco
                g = caso["giocatori"]
                partenza = file_gioco(g["min"], g["max"])
                if caso.get("senza_gioco_test"):
                    partenza.pop("gioco.test.js")       # tris2-solo-logica (20/10 sera)
                sb = nuova()
                for rel, testo in partenza.items():
                    sb.scrivi(rel, testo)
                r = sb.test()
                ok = bool(r.get("passano")) and "ok prova di fumo" in str(r.get("uscita"))
                errori += not ok
                print(f"{'ok ' if ok else 'ERR'} {nome}: la partenza ({g['min']}–{g['max']} "
                      "giocatori) passa i suoi test e la prova di fumo"
                      + ("" if ok else f"  {str(r.get('uscita'))[-500:]!r}"))
            if "gioco.test.js" in caso["prima"]:
                # La versione di prima di una correzione (20/10, #192): il suo gioco.test.js
                # della forma della partenza passa sul gioco rotto (non guarda il mostro)
                sb = nuova()
                for rel, testo in partenza.items():
                    sb.scrivi(rel, testo)
                r = sb.test()
                u = str(r.get("uscita"))
                ok = (bool(r.get("passano")) and "ok prova di fumo" in u
                      and "la partita comincia dalla preparazione" in u)
                errori += not ok
                print(f"{'ok ' if ok else 'ERR'} {nome}: la versione di prima ha gioco.test.js "
                      "della partenza, verde con la prova di fumo"
                      + ("" if ok else f"  {u[-500:]!r}"))
            if caso.get("senza_gioco_test"):
                # Il riferimento della sola logica: i suoi test (logica.test.js del tris) e la
                # prova di fumo verdi, senza nessun test con apriGioco
                sb = nuova()
                for rel, testo in {**partenza, **caso["riferimento"]}.items():
                    sb.scrivi(rel, testo)
                r = sb.test()
                u = str(r.get("uscita"))
                ok = (bool(r.get("passano")) and "ok prova di fumo" in u
                      and "apriGioco" not in "".join(caso["riferimento"].values())
                      and not (sb.root / "gioco.test.js").exists())
                errori += not ok
                print(f"{'ok ' if ok else 'ERR'} {nome}: il riferimento passa i test della logica "
                      "e la prova di fumo, senza gioco.test.js" + ("" if ok else f"  {u[-500:]!r}"))
            prima = accettazione(nuova, partenza, caso)
            rif = accettazione(nuova, {**partenza, **caso["riferimento"]}, caso)
            ok = not prima["verde"] and rif["verde"]
            errori += not ok
            print(f"{'ok ' if ok else 'ERR'} {nome}: accettazione rossa alla partenza, verde sul "
                  "riferimento" + ("" if ok else f"  prima={prima['uscita'][-300:]!r} "
                                                 f"riferimento={rif['uscita'][-500:]!r}"))
        if shutil.which("node"):
            # Il test che l'agente aveva scritto il 18/10 (#174): la mossa senza «Inizia».
            # Sul riferimento fallisce, e l'errore dice la fase e come se ne esce
            caso = casi()["tris2"]
            r = accettazione(nuova, caso["riferimento"], dict(caso, accettazione=(
                "accettazione_banco.test.js", TEST_SENZA_INIZIA)))
            ok = (not r["verde"] and "fase «preparazione»" in r["uscita"]
                  and 'g.tocca("Inizia")' in r["uscita"])
            errori += not ok
            print(f"{'ok ' if ok else 'ERR'} tris2: la mossa senza «Inizia» fallisce e l'errore "
                  "dice la preparazione e «Inizia»" + ("" if ok else f"  {r['uscita'][-600:]!r}"))
            # Il tris nudo (20/10, #198): i test del riferimento passano da soli, e il contrario
            # che sovrascrive la casella occupata è rosso proprio lì
            caso = casi()["tris-nudo"]
            sb = nuova()
            for rel, testo in caso["riferimento"].items():
                sb.scrivi(rel, testo)
            r = sb.test()
            ok = bool(r.get("passano")) and "ok tre in fila vince" in str(r.get("uscita"))
            errori += not ok
            print(f"{'ok ' if ok else 'ERR'} tris-nudo: i test del riferimento passano"
                  + ("" if ok else f"  {str(r.get('uscita'))[-500:]!r}"))
            rotto = caso["riferimento"]["tris.js"].replace(TRIS_NUDO_SOVRASCRIVE, "")
            r = accettazione(nuova, {**caso["riferimento"], "tris.js": rotto}, caso)
            u = r["uscita"]
            ok = (rotto != caso["riferimento"]["tris.js"] and not r["verde"]
                  and "FALLITO ACC tris-nudo: la casella occupata" in u
                  and "ok ACC tris-nudo: tre in fila in riga" in u)
            errori += not ok
            print(f"{'ok ' if ok else 'ERR'} tris-nudo: contrario, la casella occupata "
                  "sovrascritta fa rossa l'accettazione su quel punto"
                  + ("" if ok else f"  {u[-600:]!r}"))
            # Le due accettazioni uguali (20/10 sera, revisione della PR #199): gli stessi test
            # per nome, tutti verdi sui due riferimenti, e il conto nella riga
            import re
            t2, tn = casi()["tris2"], casi()["tris-nudo"]

            def nomi(c):
                return [x.split(": ", 1)[1] for x in re.findall(r'test\("(ACC [^"]+)"',
                                                                  c["accettazione"][1])]
            r2 = accettazione(nuova, t2["riferimento"], t2)
            rn = accettazione(nuova, tn["riferimento"], tn)
            n2 = [x for x in nomi(t2) if x not in (
                "si parte dalla preparazione, «Inizia», due giocatori",
                "tre in fila vince, la partita finisce con un punto")]
            nn = [x for x in nomi(tn) if x not in (
                "si parte dalla partita nuova, due giocatori X e O",
                "tre in fila vince, la partita finisce")]
            ok = (n2 == nn and len(n2) == 8 and r2["verdi"] == r2["totali"] == 10
                  and rn["verdi"] == rn["totali"] == 10)
            errori += not ok
            print(f"{'ok ' if ok else 'ERR'} tris2 e tris-nudo: la stessa accettazione (gli otto "
                  "punti comuni con lo stesso nome più i due di prima), 10/10 sui riferimenti"
                  + ("" if ok else f"  {n2} {nn} {r2['verdi']}/{r2['totali']} "
                                   f"{rn['verdi']}/{rn['totali']} {r2['uscita'][-600:]!r}"))
            # Il contrario di tris2: la logica che lascia attive anche le caselle prese
            rotto = t2["riferimento"]["logica.js"].replace(
                "turno: (d) => ({ casella: libere(d.celle) }),",
                "turno: (d) => ({ casella: [1, 2, 3, 4, 5, 6, 7, 8, 9] }),")
            r = accettazione(nuova, {**t2["riferimento"], "logica.js": rotto}, t2)
            ok = (rotto != t2["riferimento"]["logica.js"] and not r["verde"]
                  and any("casella occupata" in x for x in r["rossi"] or [])
                  and 0 < r["verdi"] < r["totali"] == 10)
            errori += not ok
            print(f"{'ok ' if ok else 'ERR'} tris2: contrario, la casella presa ancora attiva fa "
                  f"rossa l'accettazione su quel punto ({r['verdi']}/{r['totali']} verdi)"
                  + ("" if ok else f"  {r['rossi']} {r['uscita'][-600:]!r}"))
            p0 = accettazione(nuova, {}, tn)
            ok = p0["verdi"] == 0 and p0["totali"] == 10 and len(p0["rossi"]) == 10
            errori += not ok
            print(f"{'ok ' if ok else 'ERR'} tris-nudo: alla partenza 0/10, anche i test che non "
                  "arrivano a girare contano rossi" + ("" if ok else f"  {p0}"))
            # Le partenze dei tris2 (seconda revisione della PR #199): 2/10, il motore dà la
            # preparazione con «Inizia» e la partita nuova
            from calliope.agenti.scheletri import file_gioco
            for nome_c in ("tris2", "tris2-solo-logica"):
                c = casi()[nome_c]
                part = file_gioco(2, 2)
                if c.get("senza_gioco_test"):
                    part.pop("gioco.test.js")
                pp = accettazione(nuova, part, c)
                ok = pp["verdi"] == 2 and pp["totali"] == 10
                errori += not ok
                print(f"{'ok ' if ok else 'ERR'} {nome_c}: alla partenza {pp['verdi']}/"
                      f"{pp['totali']} (atteso 2/10, come dice la docstring)"
                      + ("" if ok else f"  {pp['rossi']}"))
            # La firma dei test finali (seconda revisione): sul riferimento nessuna, sul tris
            # nudo che sovrascrive la casella occupata il test che fallisce
            rotto = tn["riferimento"]["tris.js"].replace(TRIS_NUDO_SOVRASCRIVE, "")
            ok_rif = test_finali(nuova, tn["riferimento"], tn)
            tr = test_finali(nuova, {**tn["riferimento"], "tris.js": rotto}, tn)
            ok = (ok_rif["passano"] and not ok_rif["firma"] and not tr["passano"]
                  and "casella occupata" in tr["firma"])
            errori += not ok
            print(f"{'ok ' if ok else 'ERR'} test finali: sul riferimento verdi senza firma, sul "
                  f"tris rotto la firma del test rosso ({tr['firma']!r})"
                  + ("" if ok else f"  {ok_rif} {tr}"))
        # I test con apriGioco nella riga (seconda revisione della PR #199)
        finto = SimpleNamespace(segnali={"scritture": {}})
        ok = (test_apri_gioco({"gioco.test.js": "const g = await apriGioco({ seme: 1 });",
                               "logica.test.js": "require('./logica.js')",
                               "accettazione.test.js": "await apriGioco({})"}, finto)
              == ["gioco.test.js"]
              and test_apri_gioco({"logica.test.js": "// niente apriGioco qui\n",
                                   "accettazione.test.js": "await apriGioco({})"}, finto) == []
              and test_apri_gioco({}, SimpleNamespace(segnali={"scritture": {
                  "gioco.test.js": 1}})) == ["gioco.test.js"])
        errori += not ok
        print(f"{'ok ' if ok else 'ERR'} test_apri_gioco: un test dell'agente con apriGioco, "
              "anche scritto e poi tolto; contrari: gli esempi dell'analisi, un commento")
        # A′ come nel § 7: prompt, contratto e suggerimento dopo il piano senza gioco.test.js
        from calliope.config import Config
        from calliope.estensioni.contratto import testo as contratto_vero
        from calliope.estensioni.prompt import sistema_estensione
        prossimo = ("leggi i file nella cartella (manifesto.json, logica.js, logica.test.js, "
                    "gioco.test.js), cambiali nel gioco chiesto con modifica_file e rifai "
                    "esegui_test")
        veri = [sistema_estensione(Config(), gioco=True), contratto_vero(Config(), "gioco"),
                prossimo]
        nuovi = [solo_logica(t) for t in veri]
        ok = (all("gioco.test.js" in t for t in veri)
              and not any("gioco.test.js" in t for t in nuovi)
              and "i test della sola logica in logica.test.js" in nuovi[0]
              and "ci sono già tre file" in nuovi[0]
              and "apriGioco({ seme: 7 })" not in nuovi[1]
              and "esegui_test lo fa girare" in nuovi[1])
        errori += not ok
        print(f"{'ok ' if ok else 'ERR'} tris2-solo-logica: prompt, contratto e «prossimo» "
              "senza gioco.test.js (contrario: quelli veri lo dicono)"
              + ("" if ok else "  " + " | ".join(
                  t[max(0, t.find("gioco.test.js") - 200):t.find("gioco.test.js") + 60]
                  for t in nuovi if "gioco.test.js" in t)))
        vin = vincoli_correzione(casi()["porte"])
        ok = "gioco.test.js" in vin and "deve FALLIRE" in vin and PROBLEMA_PORTE in vin
        errori += not ok
        print(f"{'ok ' if ok else 'ERR'} i vincoli della correzione delle porte: il test che "
              "riproduce in gioco.test.js, prima rosso")
        errori += secco_giri(tmp / "giri")
        errori += secco_analisi(tmp / "analisi")
        errori += secco_tetto(tmp / "tetto")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + ("TUTTO OK" if not errori else f"{errori} ERRORI"))
    return 1 if errori else 0


CASO_SOMMA = {"tipo": "codice", "gioco": False, "correzione": False, "estensione": None,
              "compito": "Scrivi somma.py con somma(a, b) che restituisce la somma.",
              "prima": {}, "accettazione": ("test_nascosto_banco.py",
                                            "from somma import somma\n\n\n"
                                            "def test_somma():\n    assert somma(2, 3) == 5\n")}


def secco_giri(tmp: Path) -> int:
    """I giri (13/10) con l'agente finto di prove/ollama_finto.py e il servizio vero: budget
    diviso, tappa al tetto del giro 1, «continua» chiamato dal banco, consegna al giro 2;
    senza consegna l'ultimo giro chiude con «limite»; con un giro solo il tetto chiude come
    prima (nessuna tappa). Le misure dei giri nella riga."""
    from calliope.agenti import Lavori, carica
    from calliope.config import Config
    from prove.ollama_finto import FakeOllama

    def scrivi(c):
        return {"tool_calls": [{"name": "scrivi_file", "arguments": {
            "percorso": "somma.py", "contenuto": f"def somma(a, b):\n    return {c}\n"}}]}
    consegna = {"tool_calls": [{"name": "consegna", "arguments": {
        "riassunto": "Somma corretta.", "esito": "fatto"}}]}
    errori = 0

    def verifica(nome, ok, dettaglio=""):
        nonlocal errori
        errori += not ok
        print(f"{'ok ' if ok else 'ERR'} giri: {nome}" + ("" if ok else f"  {dettaglio}"))
    tmp.mkdir(parents=True, exist_ok=True)
    fake = FakeOllama(modelli=("agente-finto",)).avvia()
    svc = None
    try:
        def servizio(giri, minuti=20.0):
            cfg = Config()
            cfg.agenti_url = fake.url
            cfg.agenti_modello = "agente-finto"
            cfg.agenti_risultati = str(tmp / "risultati")
            cfg.agenti_sandbox = str(tmp / "sandbox")
            cfg.agenti_sandbox_motore = "processo"
            cfg.agenti_modelli = str(tmp / "modelli")
            cfg.llm_native_url = "http://127.0.0.1:9"
            cfg.agenti_conferma = "mai"
            cfg.agenti_max_passi = 6
            b = dividi_budget(cfg, giri, minuti)
            return cfg, b, Lavori(cfg, carica(cfg), log=lambda *a: None)

        cfg, b, svc = servizio(2)
        verifica("budget diviso: 6 passate in 2 giri = 3 per giro, 20 minuti = 10 per giro",
                 b["passate_giro"] == 3 and b["passate_totali"] == 6
                 and cfg.agenti_max_passi == 3 and cfg.agenti_tempo_max_min == 10.0
                 and svc.agente.max_passi == 3 and svc.agente.tempo_max_s == 600, str(b))
        c2 = SimpleNamespace(agenti_max_passi=24, agenti_max_token=0)
        b2 = dividi_budget(c2, 5, 20)
        verifica("arrotondato: 24 passate in 5 giri = 5 per giro (25 in tutto), 4 minuti",
                 b2["passate_giro"] == 5 and b2["passate_totali"] == 25
                 and c2.agenti_tempo_max_min == 4.0, str(b2))
        # Dal 22/10 (#225) i token per tipo si dividono anche loro (prima seguivano i minuti),
        # e senza --minuti vale il tempo del profilo dell'agente
        verifica("i token per lavoro divisi per giro: 150 000 di codice in 2 giri = 75 000",
                 b["token_lavoro"]["codice"] == 150000 and b["token_giro"]["codice"] == 75000
                 and svc.agente.tetto_token(SimpleNamespace(tipo="codice")) == 75000
                 and svc.agente.tetto_token(SimpleNamespace(tipo="ricerca")) == 45000, str(b))
        from calliope.config import apply_agenti_profile
        c3 = Config()
        c3.agenti_profilo = "denso-27b-vllm"
        apply_agenti_profile(c3)
        b3 = dividi_budget(c3, 1)
        verifica("senza --minuti il tempo del profilo (denso: 375 minuti), token uguali",
                 b3["minuti_totali"] == 375.0 and b3["token_lavoro"] == Config().agenti_token_lavoro
                 and b3["profilo"] == "denso-27b-vllm", str(b3))
        pr = per_riuscito([
            {"variante": "v", "riuscito": True, "token": 1000, "minuti": 2.0, "token_s": 8.3},
            {"variante": "v", "riuscito": True, "token": 3000, "minuti": 4.0, "token_s": 12.5},
            {"variante": "v", "riuscito": False, "token": 99999, "minuti": 30.0, "token_s": 55}])
        verifica("per lavoro riuscito: mediane di token, minuti e token/s, i falliti fuori",
                 pr["v"] == {"riusciti": 2, "token_med": 2000, "minuti_med": 3.0,
                             "token_s_med": 10.4, "token_tot": 4000, "minuti_tot": 6.0}, str(pr))
        # 1. Giro 1 al tetto (3 passate sbagliate) → tappa; giro 2: giusta e consegna
        fake.copione = [scrivi("a - b"), scrivi("a * b"), scrivi("b - a"), scrivi("a + b"),
                        consegna]
        r = un_lavoro(svc, cfg, tmp, "somma", CASO_SOMMA, "secco g=2", giri=2)
        pg = r["per_giro"]
        verifica("giro 1 fermo alla tappa al tetto delle passate, accettazione rossa",
                 len(pg) == 2 and pg[0]["esito"] == "tappa"
                 and pg[0]["tipo_limite"] == "passate" and pg[0]["accettazione"] is False,
                 str(pg))
        verifica("il banco chiama continua: il giro 2 riparte dal contesto e consegna",
                 r["esito"] == "fatto" and r["riuscito"] and r["giri"] == 2
                 and r["passate_giri"] == [3, 2] and r["giro_consegna"] == 2
                 and r["giro_accettazione"] == 2 and r["sbloccato"] is True
                 and any("Hai un altro giro di lavoro" in str(m.get("content"))
                         for q in fake.richieste for m in q.get("messages") or []),
                 json.dumps({k: v for k, v in r.items() if k != "per_giro"},
                            ensure_ascii=False, default=str)[:800])
        # 2. Nessuna consegna: l'ultimo giro chiude il lavoro con «limite», non con una tappa
        fake.copione = [scrivi("a - b")] * 8
        r = un_lavoro(svc, cfg, tmp, "somma", CASO_SOMMA, "secco g=2", giri=2)
        verifica("senza consegna: tappa al giro 1, l'ultimo giro chiude con «limite»",
                 r["giri"] == 2 and r["per_giro"][0]["esito"] == "tappa"
                 and r["esito"] == "limite" and r["giro_consegna"] is None
                 and r["sbloccato"] is False and r["passate_giri"] == [3, 3],
                 f"{r['esito']} {r['per_giro']}")
        svc.close()
        # 3. Contrario: un giro solo, il tetto chiude come prima (nessuna tappa)
        cfg, b, svc = servizio(1)
        fake.copione = [scrivi("a - b")] * 8
        r = un_lavoro(svc, cfg, tmp, "somma", CASO_SOMMA, "secco", giri=1)
        verifica("contrario: con un giro solo 6 passate e «limite», come prima",
                 b["passate_giro"] == 6 and r["esito"] == "limite" and r["giri"] == 1
                 and r["passate"] == 6 and r["sbloccato"] is None
                 and colonna_giri([r]) == "-", f"{r['esito']} {r['per_giro']}")
        verifica("la riga dice il profilo dell'agente, la sua velocità e i token al secondo",
                 r["profilo"] == "qwen3.6-35b-a3b-vllm" and r["velocita_profilo"] == 70.0
                 and isinstance(r["token_s"], float), str({k: r.get(k) for k in (
                     "profilo", "velocita_profilo", "token_s")}))
        # 4. Il tris nudo (20/10, #198): il JavaScript dei programmi acceso in memoria solo per
        # il caso, con la Config di serie che non l'ha; il caso dopo torna com'era
        fine = {"tool_calls": [{"name": "consegna", "arguments": {
            "riassunto": "Non lo faccio.", "esito": "impossibile"}}]}
        fake.copione = [fine]
        n0 = len(fake.richieste)
        un_lavoro(svc, cfg, tmp, "tris-nudo", casi()["tris-nudo"], "secco")
        sistema = json.dumps(fake.richieste[n0:], ensure_ascii=False)
        verifica("tris-nudo: «javascript» acceso in memoria per il caso, il prompt del "
                 "programma lo dice", "javascript" in cfg.agenti_linguaggi
                 and "Il JavaScript è previsto" in sistema, str(cfg.agenti_linguaggi))
        fake.copione = [fine]
        un_lavoro(svc, cfg, tmp, "somma", CASO_SOMMA, "secco")
        verifica("…e il caso dopo torna ai linguaggi della Config",
                 cfg.agenti_linguaggi == list(Config().agenti_linguaggi),
                 str(cfg.agenti_linguaggi))
    finally:
        if svc is not None:
            svc.close()
        fake.ferma()
    return errori


def secco_analisi(tmp: Path) -> int:
    """L'analisi prima del codice nel banco (13/10, flusso a fasi parte 2), con l'agente finto
    e il servizio vero: la domanda prima di cominciare riceve la risposta del banco, la
    passata dopo la risposta scrive gli esempi di accettazione nella cartella, la riga conta
    le domande e l'analisi; «config» in --temperature e --presence."""
    from calliope.agenti import Lavori, carica
    from calliope.config import Config
    from prove.ollama_finto import FakeOllama
    errori = 0

    def verifica(nome, ok, dettaglio=""):
        nonlocal errori
        errori += not ok
        print(f"{'ok ' if ok else 'ERR'} analisi: {nome}" + ("" if ok else f"  {dettaglio}"))
    t = valori("config,0.6", 0.4)
    pp = valori("config", CONFIG)
    verifica("«config» in --temperature e --presence", t == [0.4, 0.6] and pp == [CONFIG])
    esempio = {"requisito": 1, "dati": {"valore": 1, "da": "miglia", "a": "metri"},
               "numero": 1609.344, "tolleranza": None, "contiene": "", "trovato": None}
    con_dubbio = {"contraddizioni": [{"requisiti": [1], "domanda": "Le miglia sono terrestri"}],
                  "scelte": [], "al_collaudo": [], "input": [{"nome": "valore", "tipo": "number"}],
                  "campo_numero": "risultato", "esempi": [esempio]}
    senza = dict(con_dubbio, contraddizioni=[])
    tmp.mkdir(parents=True, exist_ok=True)
    fake = FakeOllama(modelli=("agente-finto",)).avvia()
    svc = None
    try:
        cfg = Config()
        cfg.agenti_url = fake.url
        cfg.agenti_modello = "agente-finto"
        cfg.agenti_risultati = str(tmp / "risultati")
        cfg.agenti_sandbox = str(tmp / "sandbox")
        cfg.agenti_sandbox_motore = "processo"
        cfg.agenti_modelli = str(tmp / "modelli")
        cfg.llm_native_url = "http://127.0.0.1:9"
        cfg.agenti_conferma = "mai"
        cfg.agenti_max_passi = 4
        svc = Lavori(cfg, carica(cfg), log=lambda *a: None)
        svc.estensioni = EstensioniFinte()
        fake.copione = [{"content": json.dumps(con_dubbio)}, {"content": json.dumps(senza)},
                        {"tool_calls": [{"name": "consegna", "arguments": {
                            "riassunto": "Non lo faccio.", "esito": "impossibile"}}]}]
        r = un_lavoro(svc, cfg, tmp, "convertitore", casi()["convertitore"], "secco")
        verifica("la domanda prima di cominciare ha la risposta del banco, una volta",
                 r["domande"] == ["Prima di cominciare: le miglia sono terrestri?"]
                 and any(RISPOSTA_BANCO in json.dumps(q, ensure_ascii=False)
                         for q in fake.richieste), str(r["domande"]))
        verifica("…dopo la risposta l'analisi è pronta, con l'esempio; il lavoro finisce",
                 r["analisi"].get("stato") == "pronta" and r["analisi"].get("esempi") == 1
                 and r["esito"] == "impossibile", json.dumps(r["analisi"]) + str(r["esito"]))
        sb = next((x for x in Path(cfg.agenti_sandbox).glob("*") if x.is_dir()), None)
        verifica("…e test_accettazione.py era nella cartella dell'agente con il runtime e i "
                 "test di partenza", sb is not None and all(
                     (sb / n).is_file() for n in ("test_accettazione.py",
                                                  "calliope_estensione.py",
                                                  "test_estensione.py")),
                 str(sorted(x.name for x in sb.iterdir())) if sb else "nessuna sandbox")
        # tris2 (20/10, #192): l'analisi come in uno sviluppo, con i requisiti del caso. Prima
        # il banco metteva «saltata» e il tetto non poteva mai chiudere il lavoro da sé
        es = {"requisito": 1, "giocatori": 2, "mosse": [{"comando": "casella", "valore": 1}],
              "atteso": {"tocca": 2}}
        gioco = {"contraddizioni": [], "scelte": [], "al_collaudo": [],
                 "giocatori": {"min": 2, "max": 2}, "esempi": [es],
                 "comandi": [{"fase": "turno", "nome": "casella", "da": 1, "a": 9}]}
        fake.copione = [{"content": json.dumps(gioco)},
                        {"tool_calls": [{"name": "consegna", "arguments": {
                            "riassunto": "Non lo faccio.", "esito": "impossibile"}}]}]
        prima = set(Path(cfg.agenti_sandbox).glob("*"))
        r = un_lavoro(svc, cfg, tmp, "tris2", casi()["tris2"], "secco")
        sb = next((x for x in set(Path(cfg.agenti_sandbox).glob("*")) - prima if x.is_dir()),
                  None)
        m = (json.loads((sb / "manifesto.json").read_text(encoding="utf-8"))
             if sb and (sb / "manifesto.json").is_file() else {})
        verifica("tris2: l'analisi come in uno sviluppo, pronta con l'esempio; i requisiti nel "
                 "messaggio dell'analisi",
                 r["analisi"].get("stato") == "pronta" and r["analisi"].get("esempi") == 1
                 and any("Tre segni in fila" in json.dumps(q, ensure_ascii=False)
                         for q in fake.richieste), json.dumps(r["analisi"]))
        verifica("…accettazione.test.js nella cartella, e la partenza con i giocatori "
                 "dell'analisi (2–2)", sb is not None and (sb / "accettazione.test.js").is_file()
                 and (m.get("scheda") or {}).get("giocatori") == {"min": 2, "max": 2},
                 str(sorted(x.name for x in sb.iterdir())) if sb else "nessuna sandbox")
        verifica("…e il servizio è tornato com'era: niente sviluppo finto fuori dall'analisi",
                 getattr(svc, "sviluppi", None) is None)
        # tris2-solo-logica (20/10 sera, #198): la stessa analisi e la stessa partenza, senza
        # gioco.test.js; la richiesta chiede solo la logica. Il caso dopo ha la partenza intera
        for nome_caso, con_test in (("tris2-solo-logica", False), ("tris2", True)):
            fake.copione = [{"content": json.dumps(gioco)},
                            {"tool_calls": [{"name": "piano", "arguments": {
                                "capacita_necessarie": [], "fattibile": True,
                                "motivo": "un gioco a turni", "scope": {}}}]},
                            {"tool_calls": [{"name": "consegna", "arguments": {
                                "riassunto": "Non lo faccio.", "esito": "impossibile"}}]}]
            prima = set(Path(cfg.agenti_sandbox).glob("*"))
            n0 = len(fake.richieste)
            r = un_lavoro(svc, cfg, tmp, nome_caso, casi()[nome_caso], "secco")
            sb = next((x for x in set(Path(cfg.agenti_sandbox).glob("*")) - prima
                       if x.is_dir()), None)
            nomi_sb = sorted(x.name for x in sb.iterdir()) if sb else []
            detto = json.dumps(fake.richieste[n0:], ensure_ascii=False)
            # Il prompt di sistema, il contratto nella cartella e il «prossimo» dopo il piano
            # (seconda revisione della PR #199: A′ come nel § 7)
            sistema = next((m.get("content") or "" for q in fake.richieste[n0:]
                            for m in q.get("messages") or [] if m.get("role") == "system"
                            and "CONTRATTO DEL GIOCO" in str(m.get("content"))), "")
            dopo_piano = [str(m.get("content")) for q in fake.richieste[n0:]
                          for m in q.get("messages") or [] if m.get("role") == "tool"
                          and "prossimo" in str(m.get("content"))]
            cap = next((p.read_text(encoding="utf-8") for p in (sb.glob("CAPACITA*") if sb
                                                                 else [])), "")
            verifica(f"{nome_caso}: l'analisi pronta, la partenza con logica.test.js e "
                     + ("gioco.test.js" if con_test else "senza gioco.test.js, la richiesta "
                        "della sola logica"),
                     r["analisi"].get("stato") == "pronta" and "logica.test.js" in nomi_sb
                     and "accettazione.test.js" in nomi_sb
                     and ("gioco.test.js" in nomi_sb) == con_test
                     and ("Scrivi solo la logica" in detto) != con_test, str(nomi_sb))
            verifica(f"{nome_caso}: prompt, contratto in cartella e «prossimo» dopo il piano "
                     + ("con gioco.test.js" if con_test else "senza gioco.test.js"),
                     bool(sistema) and bool(cap) and bool(dopo_piano)
                     and all(("gioco.test.js" in t) == con_test
                             for t in (sistema, cap, dopo_piano[0])),
                     f"sistema {bool(sistema)}, contratto {bool(cap)}, piano {dopo_piano[:1]}")
            verifica(f"{nome_caso}: la riga ha la firma, i test finali e test_apri_gioco",
                     all(k in r for k in ("firma_primo_errore", "firma_errore_finale",
                                          "test_finali_passano", "test_apri_gioco")),
                     str(sorted(r)))
        import calliope.estensioni.contratto as C
        import calliope.estensioni.prompt as P
        verifica("…e dopo il caso prompt, contratto e piano veri", not hasattr(
            C.testo, "_banco_vera") and not hasattr(P.sistema_estensione, "_banco_vera")
            and "_piano" not in svc.agente.__dict__)
        fake.copione = [{"tool_calls": [{"name": "consegna", "arguments": {
            "riassunto": "Non lo faccio.", "esito": "impossibile"}}]}]
        cfg.agenti_accettazione = False
        try:
            r = un_lavoro(svc, cfg, tmp, "tris2", casi()["tris2"], "secco")
        finally:
            cfg.agenti_accettazione = True
        verifica("contrario: con l'analisi spenta «saltata», i giocatori del caso",
                 r["analisi"].get("stato") == "saltata", json.dumps(r["analisi"]))
    finally:
        if svc is not None:
            svc.close()
        fake.ferma()
    return errori


def secco_tetto(tmp: Path) -> int:
    """La consegna al tetto (13/10 sera, L7 del banco) con l'agente finto e il servizio vero:
    l'agente scrive il convertitore giusto all'ultima passata e non chiama consegna; al tetto
    gli esempi di accettazione e i test si rieseguono, sono verdi e il lavoro si chiude
    «fatto» (regola agente_consegna_al_tetto). Il riepilogo dice gli esempi rieseguiti alla
    fine. Contrario: l'ultima passata scrive quello sbagliato, «limite» ed esempi rossi."""
    from calliope.agenti import Lavori, carica
    from calliope.config import Config
    from prove.ollama_finto import FakeOllama
    errori = 0

    def verifica(nome, ok, dettaglio=""):
        nonlocal errori
        errori += not ok
        print(f"{'ok ' if ok else 'ERR'} tetto: {nome}" + ("" if ok else f"  {dettaglio}"))

    def chiama(*cc):
        return {"tool_calls": [{"name": n, "arguments": a} for n, a in cc]}
    # 19/10 (#9): un valore nominato che la richiesta non dice («leghe»: fuori dai valori, e
    # il suo esempio tolto) e il «calcolo» dell'esempio tenuto, per i campi nuovi della riga
    analisi = {"contraddizioni": [], "scelte": [], "al_collaudo": [],
               "input": [{"nome": "valore", "tipo": "number"},
                         {"nome": "da", "tipo": "string", "valori": ["miglia", "leghe"]},
                         {"nome": "a", "tipo": "string"}], "campo_numero": "risultato",
               "esempi": [{"requisito": 1, "dati": {"valore": 1, "da": "miglia", "a": "metri"},
                           "numero": 1609.344, "tolleranza": 0.01, "contiene": "",
                           "trovato": None, "calcolo": "1 * 1609.344"},
                          {"requisito": 1, "dati": {"valore": 1, "da": "leghe", "a": "metri"},
                           "numero": 4828.0, "tolleranza": None, "contiene": "",
                           "trovato": None}]}
    manifesto = {"nome": "convertitore_distanze", "titolo": "Convertitore di distanze",
                 "cosa_fa": {"verbo": "converte", "oggetto": "una distanza tra due unità"},
                 "input": {"type": "object", "properties": {
                     "valore": {"type": "number", "description": "il valore"},
                     "da": {"type": "string", "description": "l'unità di partenza"},
                     "a": {"type": "string", "description": "l'unità d'arrivo"}},
                     "required": ["valore", "da", "a"]},
                 "permessi": {}, "livello": "familiare",
                 "limiti": {"tempo_s": 10, "memoria_mb": 256}}
    sbagliata = RIFERIMENTO_CONVERTITORE.replace('"miglia": 1609.344', '"miglia": 1500.0')

    def copione(ultima):
        return [{"content": json.dumps(analisi)},
                chiama(("piano", {"capacita_necessarie": [], "fattibile": True,
                                  "motivo": "una conversione, senza rete", "scope": {}})),
                chiama(("scrivi_file", {"percorso": "manifesto.json",
                                        "contenuto": json.dumps(manifesto, ensure_ascii=False)}),
                       ("scrivi_file", {"percorso": "estensione.py", "contenuto": sbagliata})),
                chiama(("esegui_test", {})),
                chiama(("scrivi_file", {"percorso": "estensione.py", "contenuto": ultima}))]
    tmp.mkdir(parents=True, exist_ok=True)
    fake = FakeOllama(modelli=("agente-finto",)).avvia()
    svc = None
    try:
        cfg = Config()
        cfg.agenti_url = fake.url
        cfg.agenti_modello = "agente-finto"
        cfg.agenti_risultati = str(tmp / "risultati")
        cfg.agenti_sandbox = str(tmp / "sandbox")
        cfg.agenti_sandbox_motore = "processo"
        cfg.agenti_modelli = str(tmp / "modelli")
        cfg.llm_native_url = "http://127.0.0.1:9"
        cfg.agenti_conferma = "mai"
        cfg.agenti_max_passi = 4
        svc = Lavori(cfg, carica(cfg), log=lambda *a: None)
        svc.estensioni = EstensioniFinte()
        fake.copione = copione(RIFERIMENTO_CONVERTITORE)
        r = un_lavoro(svc, cfg, tmp, "convertitore", casi()["convertitore"], "secco")
        verifica("codice giusto all'ultima passata, nessuna consegna: al tetto «fatto» con la "
                 "regola, accettazione nascosta verde",
                 r["esito"] == "fatto" and r["consegna_al_tetto"] == "passate"
                 and r["regole"].get("agente_consegna_al_tetto") == 1 and r["riuscito"]
                 and r["passate"] == 4,
                 json.dumps({k: r.get(k) for k in ("esito", "motivo", "consegna_al_tetto",
                                                   "regole", "passate", "analisi")},
                            ensure_ascii=False, default=str))
        verifica("…il riepilogo dice gli esempi rieseguiti alla fine: verdi",
                 r["esempi_finali"] is True and r["analisi"].get("passano") is True
                 and detto_esempi(r) == ", esempi 1 verdi", f"{r['esempi_finali']} {r['analisi']}")
        # 19/10 (#9): la riga dice l'analisi (valori nominati, tolti, calcolo), le regole e i
        # segnali di giro; consegnato al tetto, niente limite né motivo del no
        an = r["analisi"]
        verifica("…la riga ha i valori nominati, i tolti per genere e gli esempi col calcolo",
                 an.get("nominati") == {"da": ["miglia"]} and an.get("valori") == 0
                 and an.get("tolti") == {"fuori": 1, "numero": 0, "contiene": 0}
                 and an.get("con_calcolo") == 1, json.dumps(an, ensure_ascii=False))
        verifica("…i segnali di giro di fine lavoro, nessun limite né no al tetto",
                 set(r["segnali_giro"]) == {"senza_novita", "senza_progressi", "ripetizioni",
                                            "riscritti"}
                 and r["limite"] is None and r["al_tetto_no"] is None,
                 json.dumps({k: r.get(k) for k in ("segnali_giro", "limite", "al_tetto_no")},
                            ensure_ascii=False))
        fake.copione = copione(sbagliata)
        r = un_lavoro(svc, cfg, tmp, "convertitore", casi()["convertitore"], "secco")
        verifica("contrario: l'ultima passata scrive quello sbagliato, «limite» ed esempi rossi",
                 r["esito"] == "limite" and not r["consegna_al_tetto"]
                 and "agente_consegna_al_tetto" not in r["regole"]
                 and r["esempi_finali"] is False and r["analisi"].get("passano") is False
                 and detto_esempi(r) == ", esempi 1 rossi",
                 json.dumps({k: r.get(k) for k in ("esito", "esempi_finali", "analisi")},
                            ensure_ascii=False, default=str))
        verifica("…la riga dice il limite delle passate e perché al tetto non l'ha chiuso",
                 r["limite"] == "passate" and r["al_tetto_no_tipo"] == "passate"
                 and str(r["al_tetto_no"]).startswith("esempi di accettazione rossi"),
                 json.dumps({k: r.get(k) for k in ("limite", "al_tetto_no", "al_tetto_no_tipo")},
                            ensure_ascii=False))
        # Le porte (14/10, banco L7 e L10): una correzione di un gioco non ha esempi, al tetto
        # vale il test che riproduce il problema. L'agente corregge logica.js e scrive il test
        # del disegno, poi non consegna
        if not shutil.which("node"):
            print("SALTATO tetto: le porte (node non c'è)")
            return errori
        F = _porte()
        # Node nella sandbox: il docker finto delle prove (la sandbox «processo» esegue solo
        # Python), come nella verifica a secco dell'accettazione
        import prova_agente_guida as G
        modello = G.sandbox(tmp, "isolamento-finto")

        def finto():
            svc.isolamento, svc.isolamenti = modello.isolamento, dict(modello.linguaggi)
            return svc.isolamento
        svc.scegli_isolamento = finto

        def porte(con_test):
            return [chiama(("piano", {"capacita_necessarie": [], "fattibile": True,
                                      "motivo": "una correzione del gioco", "scope": {}})),
                    chiama(("scrivi_file", {"percorso": "logica.js",
                                            "contenuto": F.GIOCO_GIUSTO})),
                    chiama(("scrivi_file", {"percorso": "gioco.test.js",
                                            "contenuto": F.TEST_GIOCO_PORTE})
                           if con_test else ("leggi_file", {"percorso": "logica.js"})),
                    chiama(("esegui_test", {}))]
        fake.copione = porte(True)
        r = un_lavoro(svc, cfg, tmp, "porte", casi()["porte"], "secco")
        verifica("le porte corrette e il test del disegno, nessuna consegna: al tetto «fatto» "
                 "con la riproduzione, accettazione nascosta verde",
                 r["esito"] == "fatto" and r["consegna_al_tetto"] == "passate"
                 and r["consegna_al_tetto_con"] == "riproduzione"
                 and r["riproduzione"] == "riprodotto" and r["riuscito"],
                 json.dumps({k: r.get(k) for k in ("esito", "motivo", "consegna_al_tetto",
                                                   "consegna_al_tetto_con", "riproduzione",
                                                   "accettazione", "regole")},
                            ensure_ascii=False, default=str))
        fake.copione = porte(False)
        r = un_lavoro(svc, cfg, tmp, "porte", casi()["porte"], "secco")
        verifica("contrario: le porte corrette senza il test che riproduce, «limite» (anche con "
                 "l'accettazione nascosta verde)",
                 r["esito"] == "limite" and not r["consegna_al_tetto"] and r["accettazione"],
                 json.dumps({k: r.get(k) for k in ("esito", "riproduzione", "accettazione")},
                            ensure_ascii=False, default=str))
        verifica("…e la riga dice il no al tetto: correzione non riprodotta",
                 r["limite"] == "passate"
                 and str(r["al_tetto_no"]).startswith("correzione non riprodotta"),
                 json.dumps({k: r.get(k) for k in ("limite", "al_tetto_no")},
                            ensure_ascii=False))
        # Revisione della PR #181: dopo due passate di sola prosa (#180) decide
        # _consegna_al_tetto con il tipo «prosa»; il suo no non è un no al tetto (il lavoro
        # continua), e se poi l'agente consegna la riga non dice «al tetto no»
        fake.copione = porte(False) + [
            {"content": "Ho corretto il gioco."}, {"content": "Il gioco ora funziona."},
            chiama(("scrivi_file", {"percorso": "gioco.test.js",
                                    "contenuto": F.TEST_GIOCO_PORTE})),
            chiama(("esegui_test", {})),
            chiama(("consegna", {"riassunto": "Corretto: la porta mostra il suo mostro.",
                                 "esito": "fatto"}))]
        passi = cfg.agenti_max_passi, svc.agente.max_passi
        cfg.agenti_max_passi = svc.agente.max_passi = 12
        try:
            r = un_lavoro(svc, cfg, tmp, "porte", casi()["porte"], "secco")
        finally:
            cfg.agenti_max_passi, svc.agente.max_passi = passi
        verifica("contrario: il no dopo la prosa (correzione non riprodotta), poi il test e la "
                 "consegna: «fatto», niente «al tetto no» né limite nella riga, il motivo a parte",
                 r["esito"] == "fatto" and not r["consegna_al_tetto"]
                 and r["al_tetto_no"] is None and r["al_tetto_no_tipo"] is None
                 and r["limite"] is None
                 and str(r["prosa_no"]).startswith("correzione non riprodotta"),
                 json.dumps({k: r.get(k) for k in ("esito", "motivo", "consegna_al_tetto",
                                                   "al_tetto_no", "prosa_no", "limite",
                                                   "regole")},
                            ensure_ascii=False, default=str))
        # 20/10 (#192, porte L6 del banco): a due giri le porte corrette con il test del disegno
        # alla tappa del giro 1 si chiudono «fatto» lì; prima la tappa non chiudeva mai
        fake.copione = porte(True)
        r = un_lavoro(svc, cfg, tmp, "porte", casi()["porte"], "secco g=2", giri=2)
        verifica("a due giri, le porte corrette e il test del disegno alla tappa del giro 1: "
                 "«fatto» lì, con la riproduzione, il tetto del giro e la regola "
                 "agente_consegna_alla_tappa",
                 r["esito"] == "fatto" and r["consegna_al_tetto"] == "tappa"
                 and r["consegna_al_tetto_giro"] == "passate"
                 and r["consegna_al_tetto_con"] == "riproduzione" and r["giri"] == 1
                 and r["regole"].get("agente_consegna_alla_tappa") == 1 and r["riuscito"],
                 json.dumps({k: r.get(k) for k in ("esito", "consegna_al_tetto",
                                                   "consegna_al_tetto_giro", "giri",
                                                   "riproduzione", "regole", "tappa_no")},
                            ensure_ascii=False, default=str))
        fake.copione = porte(False)
        r = un_lavoro(svc, cfg, tmp, "porte", casi()["porte"], "secco g=2", giri=2)
        verifica("contrario: senza il test che riproduce la tappa del giro 1 resta (il motivo in "
                 "tappa_no), anche con l'accettazione nascosta verde",
                 r["per_giro"][0]["esito"] == "tappa" and r["consegna_al_tetto"] != "tappa"
                 and str(r["tappa_no"]).startswith("correzione non riprodotta")
                 and r["per_giro"][0]["accettazione"] is True
                 and "agente_consegna_alla_tappa" not in r["regole"],
                 json.dumps({k: r.get(k) for k in ("esito", "per_giro", "tappa_no", "regole")},
                            ensure_ascii=False, default=str))
    finally:
        if svc is not None:
            svc.close()
        fake.ferma()
    return errori


# ═══════════════════════════ sulla DGX ═══════════════════════════

class EstensioniFinte:
    """Le estensioni per il banco: nessun archivio vero, la versione «candidata» è il lavoro."""
    archivio = SimpleNamespace(nomi=lambda: [])

    def candidata_da_lavoro(self, lav, sb, ris):
        # Con la «frase» che il servizio vero dà sempre (12/10: senza, KeyError in
        # servizio.py e i lavori riusciti finivano «errore»)
        nome = getattr(lav, "estensione", None) or "banco"
        return {"nome": nome, "versione": 1, "frase": f"«{nome}» è pronta da provare."}

    def pronto(self):
        return False


# La risposta del banco a una domanda prima o durante il lavoro (13/10): lascia decidere
RISPOSTA_BANCO = "Decidi tu, con la scelta più comune."


def aspetta(svc, lav, limite_s: float):
    import queue
    t0 = time.time()
    while time.time() - t0 < limite_s:
        try:
            item = svc.done.get(timeout=1.0)
        except queue.Empty:
            if lav.stato in ("annullato", "errore", "fatto") and lav.fine:
                return None
            continue
        if item.get("id") == lav.id:
            return item
    lav.annulla.set()
    return None


def dividi_budget(cfg, giri: int, minuti: float | None = None) -> dict:
    """Il budget di un lavoro diviso in `giri` giri uguali, solo in memoria (13/10): passate
    arrotondate (24 / 2 = 12; 24 / 5 = 5, 25 in tutto: il conto lo stampa main), minuti / giri
    per giro e, dal 22/10 (#225), i token per tipo di lavoro (agenti_token_lavoro) / giri;
    agenti_max_token, se acceso, diviso anche lui. `minuti` None = il tempo del profilo
    dell'agente (agenti_tempo_max_min). Con giri = 1 tutto come prima."""
    giri = max(1, int(giri))
    passate = int(cfg.agenti_max_passi)
    per_giro = max(1, int(passate / giri + 0.5))
    if minuti is None:
        minuti = float(cfg.agenti_tempo_max_min)
    cfg.agenti_max_passi = per_giro
    cfg.agenti_tempo_max_min = float(minuti) / giri
    token = dict(getattr(cfg, "agenti_token_lavoro", None) or {})
    cfg.agenti_token_lavoro = {k: max(1, int(int(v) / giri + 0.5)) for k, v in token.items()}
    if int(getattr(cfg, "agenti_max_token", 0) or 0) > 0:
        cfg.agenti_max_token = max(1, int(cfg.agenti_max_token / giri + 0.5))
    return {"giri": giri, "passate_lavoro": passate, "passate_giro": per_giro,
            "passate_totali": per_giro * giri, "minuti_giro": round(float(minuti) / giri, 2),
            "minuti_totali": float(minuti), "token_lavoro": token,
            "token_giro": dict(cfg.agenti_token_lavoro),
            "profilo": getattr(cfg, "agenti_profilo", None)}


def per_riuscito(righe: list[dict]) -> dict:
    """Token, minuti e token al secondo per lavoro riuscito, per variante (22/10, #225): le
    mediane e i totali, per confrontare due profili dell'agente a parità di budget."""
    out = {}
    for v in sorted({r["variante"] for r in righe}):
        rr = [r for r in righe if r["variante"] == v and r.get("riuscito")]
        if not rr:
            out[v] = {"riusciti": 0}
            continue
        out[v] = {"riusciti": len(rr),
                  "token_med": statistics.median([r["token"] for r in rr]),
                  "minuti_med": statistics.median([r["minuti"] for r in rr]),
                  "token_s_med": statistics.median([r.get("token_s") or 0 for r in rr]),
                  "token_tot": sum(r["token"] for r in rr),
                  "minuti_tot": round(sum(r["minuti"] for r in rr), 2)}
    return out


class SviluppoBanco:
    """Lo sviluppo che il banco non apre (20/10, #192), visto solo dall'analisi prima del codice
    del servizio (`Lavori._analisi_prima_`): i requisiti e la richiesta del caso. Nient'altro del
    servizio lo vede: `con_sviluppo` lo mette solo durante l'analisi."""

    def __init__(self, caso: dict):
        self.sv = SimpleNamespace(requisiti=[dict(r) for r in caso["requisiti"]],
                                  richiesta=caso["compito"])

    def di_lavoro(self, *a, **k):
        return self.sv

    def segna_accettazione(self, *a, **k):
        """Nessuna revisione da segnare (20/10, #197: senza, il log del banco diceva «requisiti
        al collaudo non segnati: 'SviluppoBanco' object has no attribute …»)."""


def con_sviluppo(svc, caso: dict):
    """L'analisi prima del codice di `svc` vede `SviluppoBanco` del caso, come in uno sviluppo;
    il resto del servizio (fine del lavoro, sonde) vede `svc.sviluppi` com'è. Un lavoro alla
    volta, come fa il banco; il caso dopo rimette l'analisi vera (`senza_sviluppo`)."""
    vera = type(svc)._analisi_prima_
    finto = SviluppoBanco(caso)

    def analisi(lav, sb, gioco):
        prima = getattr(svc, "sviluppi", None)
        svc.sviluppi = finto
        try:
            return vera(svc, lav, sb, gioco)
        finally:
            svc.sviluppi = prima
    svc._analisi_prima_ = analisi


def senza_sviluppo(svc):
    svc.__dict__.pop("_analisi_prima_", None)


def un_lavoro(svc, cfg, uscita: Path, nome: str, caso: dict, etichetta: str,
              giri: int = 1) -> dict:
    from calliope.agenti.ciclo import segnali_giro
    from calliope.config import velocita_agente
    from calliope.agenti.sandbox import Sandbox
    lav = svc.nuovo(caso["tipo"], caso["compito"], "banco", "Ottavio", "amministra",
                    vincoli=vincoli_correzione(caso) if caso.get("correzione") else "")
    lav.file_iniziali = dict(caso["prima"])
    if caso["tipo"] == "estensione":
        lav.estensione = caso.get("estensione")
        lav.gioco = bool(caso.get("gioco"))
    senza_sviluppo(svc)              # quella di un caso di prima
    partenza_vera(svc)
    if caso.get("senza_gioco_test"):
        senza_gioco_test(svc)        # tris2-solo-logica (20/10 sera, #198)
        con_solo_logica(svc)
    analisi_vera = bool(caso.get("requisiti")) and getattr(cfg, "agenti_accettazione", True)
    if analisi_vera:
        # L'analisi prima del codice come in uno sviluppo (20/10, #192): il servizio la fa con i
        # requisiti del caso e scrive gli esempi di accettazione; i giocatori li dice lei
        con_sviluppo(svc, caso)
    elif caso.get("giocatori"):
        # Quanti giocano, come li direbbe l'analisi prima del codice in uno sviluppo (19/10,
        # #186): i file di partenza del gioco li usano. Con l'analisi spenta (--accettazione no)
        lav.accettazione = {"stato": "saltata", "giocatori": dict(caso["giocatori"])}
    if caso.get("correzione"):
        lav.correzione = True
        lav.problema_correzione = caso["problema"]
    # Con più giri (13/10) il tetto di un giro è una tappa, come in un lavoro della modalità
    # sviluppo (sviluppo.py lo accende così); con un giro solo resta spento, come prima
    lav.tappe = giri > 1
    # Gli esempi di un programma fuori da uno sviluppo (17/10, #10): solo in memoria, per caso
    cfg.agenti_accettazione_programmi_sempre = bool(caso.get("programmi_sempre"))
    # I linguaggi dei programmi che il caso vuole (20/10, #198: il JavaScript del tris nudo),
    # solo in memoria e solo per quel caso: gli altri casi restano con quelli della Config
    if not hasattr(svc, "banco_linguaggi"):
        svc.banco_linguaggi = list(getattr(cfg, "agenti_linguaggi", None) or ["python"])
    in_piu = [x for x in caso.get("linguaggi") or () if x not in svc.banco_linguaggi]
    if in_piu:
        print(f"   (acceso in memoria per il caso: {', '.join(in_piu)} in agenti_linguaggi)",
              flush=True)
    cfg.agenti_linguaggi = svc.banco_linguaggi + in_piu
    iso = svc.scegli_isolamento()
    k = [0]

    def nuova():
        k[0] += 1
        return Sandbox(uscita / "verifica" / f"{etichetta}-{nome}-{lav.id}-{k[0]}", 30, 1024,
                       isolamento=iso, linguaggi=svc.isolamenti)
    t0 = time.time()
    svc.avvia(lav)
    per_giro = []
    domande = []
    for g in range(1, max(1, giri) + 1):
        tg, p0, k0 = time.time(), lav.passi, lav.token
        while True:
            aspetta(svc, lav, cfg.agenti_tempo_max_min * 60 + 180)
            r = lav.risultato or {}
            # Una domanda (13/10: l'analisi prima del codice, o l'agente a metà lavoro): il
            # banco risponde da sé, come una persona che lascia decidere, e la conta
            if lav.stato == "in_attesa" and r.get("esito") == "domanda" and len(domande) < 5:
                domande.append(str(r.get("domanda") or ""))
                svc.rispondi(lav, RISPOSTA_BANCO)
                continue
            break
        info = {"giro": g, "passate": lav.passi - p0, "token": lav.token - k0,
                "minuti": round((time.time() - tg) / 60, 2), "esito": r.get("esito"),
                "tipo_limite": r.get("tipo_limite"), "test_passano": r.get("test_passano")}
        per_giro.append(info)
        if not svc.in_tappa(lav):
            break
        # La tappa: l'accettazione nascosta sui file del giro, poi un giro nuovo senza nota
        cart = Path(r["cartella"]) if r.get("cartella") else None
        info["accettazione"] = bool(cart and cart.is_dir()
                                    and accettazione(nuova, file_di(cart), caso)["verde"])
        if g + 1 >= giri:
            lav.tappe = False        # l'ultimo giro: il tetto chiude il lavoro come oggi
        svc.continua(lav)
    if svc.in_tappa(lav):            # non dovrebbe succedere: si chiude comunque
        lav.annulla.set()
    minuti = (time.time() - t0) / 60
    ris = lav.risultato or {}
    # Senza la cartella del risultato non si prende quella del banco (12/10: copiava il banco
    # dentro sé stesso fino a «troppi file»)
    cartella = Path(ris["cartella"]) if ris.get("cartella") else None
    acc = accettazione(nuova, file_di(cartella), caso) if cartella and cartella.is_dir() else {
        "verde": False, "esito": None, "uscita": "nessuna cartella"}
    per_giro[-1]["accettazione"] = acc["verde"]
    partenza_vera(svc)               # prompt, contratto e partenza veri per il caso dopo
    # I test dell'agente alla fine, la firma del primo errore e i test con apriGioco (20/10
    # sera, seconda revisione della PR #199, § 7 dell'analisi)
    finali = file_di(cartella) if cartella and cartella.is_dir() else {}
    tf = test_finali(nuova, finali, caso) if finali else {"passano": None, "esito": None,
                                                          "firma": ""}
    firme = list((lav.segnali if isinstance(lav.segnali, dict) else {}).get("errori_test") or [])
    # Gli esempi dell'agente rieseguiti dal banco sui file finali (13/10 sera)
    from calliope.agenti.servizio import cartella_sandbox
    sbl = sorted(cartella_sandbox(cfg).glob(f"{lav.id}-*"))
    es_finali = (esempi_finali(nuova, file_di(cartella), caso, getattr(lav, "accettazione", None),
                               sbl[-1] if sbl else None)
                 if cartella and cartella.is_dir() else None)
    seg = segnali_giro(lav, cfg.agenti_max_passi)
    segnali = lav.segnali if isinstance(lav.segnali, dict) else {}
    limite = ris.get("esito") == "limite"
    fatto = (ris.get("esito") == "fatto" or lav.stato == "fatto")
    giro_acc = next((x["giro"] for x in per_giro if x.get("accettazione")), None)
    giro_consegna = per_giro[-1]["giro"] if fatto else None
    sbloccato = None
    if giri > 1:
        sbloccato = bool(len(per_giro) > 1 and not per_giro[0].get("accettazione")
                         and (fatto or acc["verde"]))
    riga = {"caso": nome, "variante": etichetta, "lavoro": lav.id, "stato": lav.stato,
            "esito": ris.get("esito"), "motivo": ris.get("motivo"),
            "riuscito": bool(fatto and acc["verde"]), "accettazione": acc["verde"],
            "accettazione_esito": acc["esito"],
            # I test verdi dell'accettazione su quelli totali e i nomi dei rossi (20/10 sera, #198)
            "accettazione_verdi": acc.get("verdi", 0), "accettazione_totali": acc.get("totali", 0),
            "accettazione_rossi": acc.get("rossi"),
            # 20/10 sera (seconda revisione della PR #199): i test dell'agente rieseguiti sui
            # file finali, la firma del primo errore (dei test di tutto il lavoro, come li ha
            # visti il ciclo: le ultime 12 diverse) e quella del primo rosso alla fine; i test
            # con apriGioco (in tris2-solo-logica un lavoro con questo campo non misura A′)
            "test_finali_passano": tf["passano"], "test_finali_esito": tf["esito"],
            "firma_primo_errore": firme[0] if firme else "",
            "firma_errore_finale": tf["firma"],
            "test_apri_gioco": test_apri_gioco(finali, lav),
            "passate": lav.passi, "token": lav.token,
            "ragionamento": lav.ragionamento, "minuti": round(minuti, 2),
            # Il profilo dell'agente e la velocità (22/10, #225): quella scritta nel profilo e
            # quella del lavoro (token generati / secondi)
            "profilo": getattr(cfg, "agenti_profilo", None),
            "velocita_profilo": velocita_agente(cfg)[0],
            "token_s": round(lav.token / (minuti * 60), 1) if minuti > 0 else None,
            "ripetizioni": seg.get("ripetizioni", 0), "senza_novita": seg.get("senza_novita", 0),
            "a_vuoto": seg.get("a_vuoto", False), "test_agente": ris.get("test"),
            "riproduzione": (getattr(lav, "riproduzione", None) or {}).get("stato"),
            # Chiuso dal codice al tetto con gli esempi verdi (13/10 sera, ciclo.py)
            "consegna_al_tetto": ris.get("consegna_al_tetto"),
            # …con gli esempi o con la riproduzione di una correzione senza esempi (14/10)
            "consegna_al_tetto_con": ris.get("consegna_al_tetto_con"),
            # …e con «tappa» (20/10, #192) il tetto del giro che l'ha chiesta
            "consegna_al_tetto_giro": ris.get("consegna_al_tetto_giro"),
            "esempi_finali": es_finali,
            # Le regole scattate nel lavoro, da lav.segnali (sonde.nota): dal 19/10 (#9) anche
            # agente_ragionamento_ripetuto e agente_riscrittura_ripetuta
            "regole": dict(segnali.get("regole") or {}),
            # I segnali di giro a vuoto di fine lavoro (19/10, #9; con più giri senza_novita e
            # senza_progressi sono dell'ultimo giro: ripartono a ogni continua)
            "segnali_giro": {k: seg.get(k) for k in ("senza_novita", "senza_progressi",
                                                      "ripetizioni", "riscritti")},
            # Un lavoro finito a un limite (19/10, #9): il tipo del Limite («passate», «tempo»,
            # «token», «a_vuoto», dal 19/10 con #180 «prosa» e «consegna_rossa», dal 20/10 con
            # #185 «troncata», «altro»), e
            # perché al tetto Calliope non l'ha chiuso da sé (la funzione no di
            # _consegna_al_tetto), con il tetto che l'ha chiesto: solo con l'esito «limite»
            # (revisione della PR #181). `prosa_no`: l'ultimo no dopo due passate di sola
            # prosa (#180), che non ferma il lavoro
            "limite": segnali.get("limite") if limite else None,
            "al_tetto_no": segnali.get("al_tetto_no") if limite else None,
            "al_tetto_no_tipo": segnali.get("al_tetto_tipo") if limite else None,
            "prosa_no": segnali.get("prosa_no"),
            # 20/10 (#192): l'ultimo no alla consegna d'ufficio di una tappa, che resta tappa
            "tappa_no": segnali.get("tappa_no"),
            # 20/10 (#190): il revisore a contesto pulito, con il modo (agenti_revisore), i
            # verdetti del lavoro (momento, verdetto, file, causa, effetto, secondi, token), i
            # suoi token e gli esempi di accettazione che ha tolto
            "revisore_modo": str(getattr(cfg, "agenti_revisore", "") or ""),
            "revisore": list(segnali.get("revisore") or []),
            "revisore_token": int(segnali.get("revisore_token") or 0),
            "esempi_tolti": list((getattr(lav, "accettazione", None) or {}).get(
                "tolti_revisore") or []),
            "cartella": str(cartella),
            "giri": len(per_giro), "giri_max": giri, "giro_accettazione": giro_acc,
            "giro_consegna": giro_consegna, "sbloccato": sbloccato,
            "passate_giri": [x["passate"] for x in per_giro], "per_giro": per_giro,
            # L'analisi prima del codice (13/10, flusso a fasi parte 2): le domande a cui il
            # banco ha risposto, gli esempi di accettazione dell'agente e il loro esito
            "domande": domande, "analisi": {k: v for k, v in (
                getattr(lav, "accettazione", None) or {}).items()
                if k in ("stato", "esempi", "passano", "rossi", "al_collaudo", "secondi",
                         "perche",
                         # 19/10 (#9): i controlli dei valori nominati, i valori per input,
                         # gli esempi tolti per genere e quanti hanno il «calcolo»
                         "valori", "nominati", "tolti", "con_calcolo",
                         # 20/10 (#197): quanti esempi aveva scritto il modello
                         "esempi_modello")}}
    if not acc["verde"]:
        riga["accettazione_uscita"] = acc["uscita"][-600:]
    return riga


# «config» in --presence: i valori della Config per tipo di lavoro (13/10)
CONFIG = object()


def valori(testo: str, config):
    """I valori di --temperature o --presence: numeri, o «config» per quello della Config."""
    out = []
    for x in str(testo or "").split(","):
        x = x.strip().lower()
        if x:
            out.append(config if x in ("config", "cfg") else float(x))
    return out


def colonna_giri(rr: list[dict]) -> str:
    """Per un gruppo di lavori a giri (13/10): le accettazioni verdi per giro («g1+g2»: 2+3 =
    due verdi al primo giro, tre al secondo) e gli sbloccati («s2»). «-» con un giro solo."""
    n = max([int(r.get("giri_max") or 1) for r in rr] or [1])
    if n <= 1:
        return "-"
    verdi = [sum(1 for r in rr if r.get("giro_accettazione") == g) for g in range(1, n + 1)]
    return "+".join(map(str, verdi)) + f" s{sum(1 for r in rr if r.get('sbloccato'))}"


def test_acc(rr: list[dict]) -> str:
    """I test verdi dell'accettazione nascosta su quelli totali, sommati sui lavori del gruppo
    (20/10 sera, #198): «41/50» per cinque lavori da dieci test."""
    return (f"{sum(int(r.get('accettazione_verdi') or 0) for r in rr)}/"
            f"{sum(int(r.get('accettazione_totali') or 0) for r in rr)}")


def tabella(righe: list[dict]):
    print("\nvariante                    caso          riusciti  acc.  test acc.  passate  "
          "token(med)  giri a vuoto  minuti(med)  giri")
    chiavi = sorted({(r["variante"], r["caso"]) for r in righe})
    for v, c in chiavi:
        rr = [r for r in righe if r["variante"] == v and r["caso"] == c]
        med = lambda k: statistics.median([r[k] for r in rr]) if rr else 0  # noqa: E731
        print(f"{v:<27} {c:<13} {sum(r['riuscito'] for r in rr)}/{len(rr):<7} "
              f"{sum(r['accettazione'] for r in rr)}/{len(rr):<3} "
              f"{test_acc(rr):>9} {med('passate'):>7} "
              f"{med('token'):>10} {sum(r['ripetizioni'] + (1 if r['a_vuoto'] else 0) for r in rr):>13} "
              f"{med('minuti'):>11}  {colonna_giri(rr)}")
    if any(int(r.get("giri_max") or 1) > 1 for r in righe):
        print("giri: accettazioni verdi per giro (giro 1 + giro 2 …) e sN = sbloccati dopo la "
              "ripartenza")
    pr = per_riuscito(righe)
    for v in sorted({r["variante"] for r in righe}):
        rr = [r for r in righe if r["variante"] == v]
        p = pr.get(v) or {}
        print(f"TOTALE {v}: {sum(r['riuscito'] for r in rr)}/{len(rr)} riusciti, "
              f"token in tutto {sum(r['token'] for r in rr)}, "
              f"minuti in tutto {sum(r['minuti'] for r in rr):.1f}"
              + (f"; per lavoro riuscito token {p['token_med']:g}, minuti {p['minuti_med']:g}, "
                 f"{p['token_s_med']:g} token/s (mediane)" if p.get("riusciti") else ""))


def main(argv) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Banco della temperatura dell'agente")
    ap.add_argument("--secco", action="store_true", help="solo il controllo del banco, senza "
                    "modello")
    ap.add_argument("--temperature", default="0.4,0.6", help="valori separati da virgole; "
                    "«config» = quello della Config (agenti_temperatura)")
    ap.add_argument("--presence", default="0,0.5", help="valori separati da virgole; «config» = "
                    "quelli della Config per tipo di lavoro (agenti_presence_penalty)")
    ap.add_argument("--accettazione", default="config", choices=("config", "si", "no"),
                    help="l'analisi prima del codice con gli esempi di accettazione "
                    "(agenti_accettazione, 13/10): come nella Config, accesa o spenta")
    ap.add_argument("--ripetizioni", type=int, default=2)
    ap.add_argument("--casi", default="porte,convertitore,programma,tris2")
    ap.add_argument("--minuti", type=float, default=None, help="tetto di tempo per lavoro "
                    "(con --giri N diviso per N: lo stesso tempo in tutto); vuoto = quello del "
                    "profilo dell'agente (dal 22/10; prima 20)")
    ap.add_argument("--agenti-profilo", help="il profilo dell'agente (PROFILI_AGENTE di "
                    "calliope/config.py: modello, indirizzo e tetti), solo in memoria; vuoto = "
                    "quello della configurazione (22/10, #225)")
    ap.add_argument("--giri", type=int, default=1, help="giri per lavoro: le passate e il "
                    "tempo divisi in N giri uguali, con la tappa e «continua» tra un giro e "
                    "l'altro (1 = come prima)")
    ap.add_argument("--uscita")
    args = ap.parse_args(argv)
    if args.secco:
        return secco()
    if args.giri < 1:
        ap.error("--giri vuole un numero da 1 in su")
    from calliope.agenti import Lavori, carica
    from calliope.config import (PROFILI_AGENTE, apply_agenti_profile, load_config,
                                 velocita_agente)
    cfg = load_config()
    cfg.agenti_conferma = "mai"
    if args.agenti_profilo:
        if args.agenti_profilo not in PROFILI_AGENTE:
            ap.error(f"profilo dell'agente sconosciuto: {args.agenti_profilo} (profili: "
                     f"{', '.join(PROFILI_AGENTE)})")
        # Solo in memoria, prima del servizio: l'agente legge i tetti quando nasce. Un
        # agenti_token_minuto del locale, già convertito all'avvio, qui lo sostituisce il budget
        # del profilo (seconda revisione della PR #234, Q6): il banco lo dice
        convertito = "agenti_token_minuto" in (getattr(cfg, "_agenti_tenute", None) or [])
        cfg.agenti_profilo = args.agenti_profilo
        apply_agenti_profile(cfg, log=True)
        if convertito:
            print("Attenzione: agenti_token_minuto del locale (convertito all'avvio) non vale nel "
                  f"banco: i token per lavoro sono quelli del profilo {args.agenti_profilo} "
                  f"({cfg.agenti_token_lavoro})", flush=True)
    # Prima di creare il servizio: l'agente legge passate e tempo da cfg quando nasce
    budget = dividi_budget(cfg, args.giri, args.minuti)
    print(f"Profilo dell'agente: {cfg.agenti_profilo or 'nessuno'} "
          f"(velocità {velocita_agente(cfg)[1] or '?'} {velocita_agente(cfg)[0] or '?'} token/s); "
          f"token per lavoro {budget['token_lavoro']}, tempo di sicurezza "
          f"{budget['minuti_totali']:g} minuti", flush=True)
    if args.giri > 1:
        print(f"Giri: {budget['passate_lavoro']} passate in {args.giri} giri = "
              f"{budget['passate_giro']} per giro ({budget['passate_totali']} in tutto), "
              f"{budget['minuti_giro']} minuti per giro ({budget['minuti_totali']:g} in tutto)",
              flush=True)
    imp = carica(cfg)
    if imp is None:
        print("Nessun agente configurato in questa cartella (serve la configurazione di "
              "Calliope con l'agente).")
        return 1
    uscita = Path(args.uscita).expanduser() if args.uscita else Path(
        tempfile.mkdtemp(prefix="banco-temperatura-"))
    uscita.mkdir(parents=True, exist_ok=True)
    cfg.agenti_risultati = str(uscita / "risultati")
    cfg.agenti_sandbox = str(uscita / "sandbox")
    svc = Lavori(cfg, imp, log=lambda m: print(f"   {m}", flush=True))
    svc.estensioni = EstensioniFinte()
    d = svc.verifica()
    if d["codice"] != "ok":
        print(f"L'agente non è raggiungibile: {d['motivo']}. {d['passo']}")
        svc.close()
        return 1
    scelti = [c.strip() for c in args.casi.split(",") if c.strip()]
    tutti = casi()
    temperature = valori(args.temperature, cfg.agenti_temperatura)
    presenze = valori(args.presence, CONFIG)
    if args.accettazione != "config":
        cfg.agenti_accettazione = args.accettazione == "si"
    acc = "" if args.accettazione == "config" else f" acc={args.accettazione}"
    print(f"Banco della temperatura: agente {imp.modello}; temperature {temperature}, "
          f"presence_penalty {['config' if p is CONFIG else p for p in presenze]} "
          f"(nella Config {cfg.agenti_presence_penalty}), analisi prima del codice "
          f"{'accesa' if cfg.agenti_accettazione else 'spenta'}, {args.ripetizioni} "
          f"ripetizioni, casi {scelti}; risultati in {uscita}", flush=True)
    righe = []
    t0 = time.time()
    vecchie = (cfg.agenti_temperatura, dict(cfg.agenti_presence_penalty))
    try:
        for rip in range(args.ripetizioni):
            for t in temperature:
                for pp in presenze:
                    etichetta = (f"t={t:g} pp={'cfg' if pp is CONFIG else f'{pp:g}'}"
                                 + (f" g={args.giri}" if args.giri > 1 else "") + acc)
                    # Solo in memoria: il servizio e l'agente leggono cfg a ogni passata
                    cfg.agenti_temperatura = t
                    cfg.agenti_presence_penalty = (dict(vecchie[1]) if pp is CONFIG
                                                   else {k: pp for k in vecchie[1]})
                    for nome in scelti:
                        print(f"\n— {etichetta}, {nome}, ripetizione {rip + 1}", flush=True)
                        r = un_lavoro(svc, cfg, uscita, nome, tutti[nome], etichetta,
                                      giri=args.giri)
                        righe.append(r)
                        print(f"{'ok ' if r['riuscito'] else 'NO '} {nome} {etichetta}: "
                              f"accettazione {'verde' if r['accettazione'] else 'rossa'} "
                              f"({r['accettazione_verdi']}/{r['accettazione_totali']} test), "
                              f"{r['passate']} passate, {r['token']} token, "
                              f"{r['minuti']} min, giri a vuoto {r['ripetizioni']}"
                              f"{' (a vuoto)' if r['a_vuoto'] else ''}, esito {r['esito']}"
                              + (f", riproduzione {r['riproduzione']}" if r["riproduzione"]
                                 else "")
                              + (f", domande {len(r['domande'])}" if r["domande"] else "")
                              + (f", primo errore «{r['firma_primo_errore']}»"
                                 if r["firma_primo_errore"] else "")
                              + (f", test con apriGioco {r['test_apri_gioco']}"
                                 if r["test_apri_gioco"] else "")
                              + detto_esempi(r)
                              + (f", consegna al tetto ({r['consegna_al_tetto']}, con "
                                 f"{r.get('consegna_al_tetto_con') or 'esempi'})"
                                 if r.get("consegna_al_tetto") else "")
                              + (f", limite {r['limite']}" if r.get("limite") else "")
                              + (f", al tetto no: {r['al_tetto_no']}" if r.get("al_tetto_no")
                                 else "")
                              + (f"; giri {r['giri']} (passate {r['passate_giri']}), "
                                 f"accettazione verde al giro {r['giro_accettazione']}, "
                                 f"consegna al giro {r['giro_consegna']}, "
                                 f"sbloccato {r['sbloccato']}" if args.giri > 1 else ""),
                              flush=True)
                        (uscita / "righe.json").write_text(json.dumps(
                            righe, ensure_ascii=False, indent=1), encoding="utf-8")
    finally:
        cfg.agenti_temperatura, cfg.agenti_presence_penalty = vecchie
        svc.close()
    tabella(righe)
    riepilogo = {"agente": imp.modello, "data": datetime.datetime.now().isoformat(
        timespec="seconds"), "temperature": temperature,
        "presence": ["config" if p is CONFIG else p for p in presenze],
        "presence_config": vecchie[1], "accettazione": bool(cfg.agenti_accettazione),
        "ripetizioni": args.ripetizioni, "casi": scelti, "giri": args.giri, "budget": budget,
        # Il profilo dell'agente e i numeri per lavoro riuscito (22/10, #225)
        "profilo": cfg.agenti_profilo, "velocita_profilo": list(velocita_agente(cfg)),
        "per_riuscito": per_riuscito(righe),
        "minuti": round((time.time() - t0) / 60, 1), "righe": righe}
    (uscita / "riepilogo.json").write_text(json.dumps(riepilogo, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    print(f"\nRiepilogo in {uscita / 'riepilogo.json'} ({riepilogo['minuti']} minuti)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
