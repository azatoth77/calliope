"""
Il contratto delle capacità per l'agente che scrive codice (05/10/2026, richiesta di Dario dopo
il lavoro L1 del 04/10: 66 000 token di ragionamento senza un file, «non sapeva cosa fare»).

Un agente che sviluppa un'estensione deve sapere **prima** cosa può fare da solo, cosa si fa
chiedendo a Calliope (la porta stretta, con lo scope da dichiarare nel manifesto) e cosa è
impossibile, da dire subito. Il testo non è scritto a mano: si genera da
- la tabella della porta stretta e del guardrail (`guardrail.AZIONI`, `guardrail.valuta_porta`:
  per ogni azione si chiede al guardrail stesso che classe ha senza permessi, con lo scope e
  dopo una lettura di dati personali);
- gli scope del manifesto (`manifesto.normalizza_permessi`: la prova controlla che ogni scope
  detto qui sblocchi davvero la sua azione);
- i tetti del codice (quote della porta, rete, tempo e memoria dalla configurazione);
- i linguaggi della sandbox.

Va nel prompt dell'agente e nella cartella del lavoro come `CAPACITA.md`, in sola lettura.
`CAPACITA_IDS` sono le voci che lo strumento `piano` accetta in `capacita_necessarie`.
"""

from __future__ import annotations

from .. import guardrail as gr
from ..testi import APRI_GIOCO_C_E

FILE = "CAPACITA.md"

# Le azioni della porta: metodo da chiamare (esempio), scope del manifesto che la sblocca
# (nella forma di «permessi»), cosa fa. Lo scope si verifica contro il guardrail nella prova
# (prova_estensioni_contratto): se qualcuno cambia la porta, la prova lo dice
PORTA = {
    "casa_stato": ('calliope.casa_stato("temperatura in camera")',
                   {"legge": {"casa": ["camera"]}}, "legge lo stato di luci, sensori, termostati"),
    "casa_comando": ('calliope.casa_comando("accendi la luce della cucina")',
                     {"scrive": {"casa": ["cucina"]}}, "comanda un dispositivo di Home Assistant"),
    "lista_leggi": ('calliope.lista_leggi("spesa")', {"legge": {"liste": ["spesa"]}},
                    "legge una lista della casa → {voci: [...]}"),
    "lista_aggiungi": ('calliope.lista_aggiungi("spesa", ["latte"])',
                       {"scrive": {"liste": ["spesa"]}}, "aggiunge voci a una lista"),
    "lista_togli": ('calliope.lista_togli("spesa", ["latte"])', {"scrive": {"liste": ["spesa"]}},
                    "toglie voci da una lista"),
    "agenda_elenca": ("calliope.agenda_elenca()", {"legge": {"agenda": True}},
                      "timer, promemoria e appuntamenti di chi la usa"),
    "timer_imposta": ('calliope.timer_imposta("10 minuti", "pasta")', {"scrive": {"agenda": True}},
                      "imposta un timer"),
    "schermo_mostra": ('calliope.schermo_mostra("Titolo", "testo")',
                       {"scrive": {"schermi": True}}, "una scheda di testo sullo schermo"),
    "dati_leggi": ('calliope.dati_leggi("stato")', {"scrive": {"dati": True}},
                   "rilegge un testo salvato prima dall'estensione"),
    "dati_scrivi": ('calliope.dati_scrivi("stato", "testo")', {"scrive": {"dati": True}},
                    "salva un testo dell'estensione tra un uso e l'altro"),
    "dati_elenca": ("calliope.dati_elenca()", {"scrive": {"dati": True}},
                    "i nomi dei testi salvati"),
    "dati_cancella": ('calliope.dati_cancella("stato")', {"scrive": {"dati": True}},
                      "cancella un testo salvato"),
    "rete_leggi": ('calliope.rete_leggi("https://www.esempio.it/dati.json")',
                   {"rete": {"pubblica": True}},
                   "GET di una pagina pubblica → {stato, tipo, testo}"),
    "rete_invia": ('calliope.rete_invia("https://api.esempio.it/ordini", {"chiave": "valore"})',
                   {"rete": {"host": ["api.esempio.it"], "post": True}},
                   "POST di dati JSON a un host del manifesto"),
}

# Cosa da sola un'estensione fa senza chiedere niente
DA_SOLA = {
    "calcolo": "conti, conversioni, date, testo: con la libreria standard di Python",
    "parser": "estrarre dati dal testo di una pagina avuta da rete_leggi (html.parser, "
              "BeautifulSoup, json, csv, xml)",
    # 05/10: un gioco (o una scheda che si usa toccando) nel browser degli schermi; dal 19/10
    # (#186) ha il suo prompt e il suo contratto (`testo(cfg, "gioco")`)
    "scheda": "una scheda interattiva sugli schermi (un gioco): JavaScript nel browser, in un "
              "riquadro isolato, con la sezione «scheda» del manifesto",
}
# Dove la voce «scheda» rimanda, secondo il contratto
_SCHEDA_DOVE = {"estensione": " (non qui: per un gioco piano con fattibile=false e il motivo "
                              "«è un gioco: va chiesto come gioco»)",
                "gioco": " (§2)"}
# Le voci degli impossibili dette per un gioco (20/10, revisione della PR #188): quelle scritte
# per Python (pip, la libreria standard, la porta stretta, «dentro l'estensione») e quella sulle
# pagine fatte in JavaScript, che in un gioco in JavaScript confondeva. None: la voce non c'è
_IMPOSSIBILI_GIOCO = {
    "pacchetti": ("installare librerie o programmi", "il JavaScript del riquadro, senza "
                  "librerie esterne"),
    "javascript": None,
    "modello": ("usare un modello linguistico o l'IA dentro il gioco", "regole deterministiche"),
    "altri_tool": ("chiamare altre estensioni o altri tool di Calliope", "solo le azioni del "
                   "§3"),
}

# Impossibile per costruzione: la porta non ha un metodo per farlo. Ogni voce: cosa, e
# l'alternativa da proporre a chi l'ha chiesto
IMPOSSIBILI = {
    "email": ("mandare email, SMS, messaggi o notifiche fuori casa",
              "mostrare il testo sullo schermo o metterlo in una lista"),
    "telefono": ("telefonare, leggere chiamate o messaggi del telefono", "nessuna"),
    "file_persona": ("leggere o scrivere i file del PC o i documenti della persona",
                     "un lavoro di codice sul file («correggi lo script …»), non un'estensione"),
    "rete_locale": ("collegarsi a dispositivi della rete di casa o dell'ufficio (router, "
                    "stampante, NAS, telecamere, indirizzi 192.168…, 10…, localhost)",
                    "i dispositivi di Home Assistant con casa_stato e casa_comando"),
    "orari_fissi": ("partire da sola a orari fissi o restare accesa in secondo piano",
                    "si usa a voce quando serve; per ricordarsi, un timer"),
    "pacchetti": ("installare pacchetti (pip) o programmi", "la libreria standard e quelle "
                  "già presenti"),
    "memoria": ("leggere i ricordi di Calliope, la rubrica, l'archivio dei documenti, la "
                "biblioteca", "i dati che servono li passa chi la usa, come input"),
    "microfono_camera": ("usare microfono, webcam, schermo o tastiera del PC", "nessuna"),
    "altri_tool": ("chiamare altre estensioni o altri tool di Calliope", "solo i metodi della "
                   "porta stretta"),
    "credenziali": ("accedere a siti con utente e password, token, chiavi o cookie (login)",
                    "solo pagine e API pubbliche senza accesso"),
    "javascript": ("leggere dati che una pagina mostra solo con JavaScript nel browser",
                   "un'API pubblica o una pagina con i dati nell'HTML"),
    "modello": ("usare un modello linguistico o l'IA dentro l'estensione",
                "codice deterministico"),
}

CAPACITA_IDS = tuple(DA_SOLA) + tuple(PORTA) + tuple(IMPOSSIBILI)

_TUTTI = {"legge": {"casa": True, "liste": True, "agenda": True, "dati": True},
          "scrive": {"casa": True, "liste": True, "agenda": True, "dati": True,
                     "schermi": True},
          "rete": {"pubblica": True, "host": ["api.esempio.it"], "post": True}, "invia": []}
_ARGS = {"casa_stato": {"cosa": "temperatura in camera"},
         "casa_comando": {"comando": "accendi la luce della cucina"},
         "lista_leggi": {"lista": "spesa"}, "lista_aggiungi": {"lista": "spesa", "voci": ["latte"]},
         "lista_togli": {"lista": "spesa", "voci": ["latte"]}, "timer_imposta": {"durata": "1"},
         "dati_leggi": {"nome": "x"}, "dati_scrivi": {"nome": "x", "testo": "1"},
         "dati_cancella": {"nome": "x"}, "rete_leggi": {"url": "https://www.esempio.it/x"},
         "rete_invia": {"url": "https://api.esempio.it/x"}}


def classe_detta(azione: str) -> str:
    """Come la tratta il guardrail, chiesto al guardrail stesso."""
    v = gr.valuta_porta(azione, _ARGS.get(azione, {}), _TUTTI, gr.StatoEsecuzione())
    if v.classe == gr.SICURA:
        out = "da sola"
    elif v.classe == gr.PERICOLOSA:
        out = "si ferma e chiede il «sì» a chi la usa" + (" con la frase di sfida"
                                                          if v.sfida else "")
    else:
        out = "vietata"
    sporca = gr.StatoEsecuzione()
    sporca.contamina("liste:spesa")
    if azione in ("rete_leggi", "rete_invia"):
        w = gr.valuta_porta(azione, _ARGS[azione], _TUTTI, sporca)
        if w.classe == gr.VIETATA:
            out += ("; dopo aver letto dati personali (casa, liste, agenda, dati salvati) "
                    "VIETATA, salvo un flusso dichiarato in «invia» verso quell'host (https)")
    if azione in ("lista_aggiungi", "timer_imposta"):
        w = gr.valuta_porta(azione, {**_ARGS[azione], "lista": "cose"}, _TUTTI, sporca)
        if w.classe == gr.PERICOLOSA:
            out += "; con dati letti da altrove chiede il «sì»"
        if azione == "lista_aggiungi":
            molte = gr.valuta_porta(azione, {"lista": "spesa",
                                             "voci": [str(i) for i in range(gr.MAX_VOCI_LISTA + 1)]},
                                    _TUTTI, gr.StatoEsecuzione())
            if molte.classe == gr.PERICOLOSA:
                out += f"; più di {gr.MAX_VOCI_LISTA} voci insieme chiede il «sì»"
    return out


def scheda_testo(cfg=None) -> list[str]:
    """La scheda interattiva (05/10, scheda.py e schermi/giochi.py), generata dai valori del
    codice: formato, interfaccia del riquadro, tetti, test, chi approva. Dal 13/10 un gioco
    nuovo usa la macchina a stati di Calliope (estensioni/macchina.py, motore_gioco.js):
    l'agente scrive solo la dichiarazione delle fasi e la logica pura. Dal 14/10 (il palco
    fisso) sceglie per ogni fase un modello di pagina, e la prova di fumo misura il palco.
    Dal 19/10 (#186) è il §2 del contratto del gioco, una regola per argomento: la forma esatta
    di g.stato(), la preparazione con «Inizia» anche con min < max, le tre forme di una mossa
    (gli errori nuovi del motore), turni di serie e il caso. Le righe senza l'intestazione."""
    from . import macchina as mc
    from . import scheda as sc
    from ..schermi import giochi as gi
    c = lambda k, d: getattr(cfg, k, d) if cfg is not None else d  # noqa: E731
    std = ", ".join(f"«{f}»" for n in ("inizia", "avanti", "ancora", "anchio")
                    for f in mc.COMANDI_STANDARD[n][0])
    return [
        "Un gioco gira nel BROWSER degli schermi (PC, tablet, telefono), in un riquadro isolato "
        "(iframe sandbox, origine opaca): niente rete, niente localStorage, niente pagina "
        "intorno. Calliope dà la MACCHINA A STATI del gioco: preparazione (quanti giocatori), "
        "turni, punti, il testo dell'esito quando una mano finisce, fine con la classifica e "
        "«ancora», il disegno della "
        "pagina su un palco fisso (1280×720, e 720×1280 sul telefono in verticale, scalato alla "
        "finestra, mai scroll), un pulsante per ogni comando e i comandi a voce. Tu scrivi solo "
        "la dichiarazione delle fasi nel manifesto e la logica pura in logica.js. Niente "
        "gioco.js, niente DOM, niente CSS di posizioni o misure, niente turni o punti fatti a "
        "mano.",
        "- file: logica.js con `const GIOCO = {…}` e in fondo `if (typeof module !== "
        "\"undefined\") module.exports = { GIOCO, … };`; facoltativi tema.css (solo le "
        "variabili del tema: --sfondo, --testo, --primario, --accento, --carattere, --raggio, "
        "--casella, --bordo) e disegni .svg; i test logica.test.js (node:test e node:assert, "
        "`const { GIOCO } = require(\"./logica.js\")`: le regole) e gioco.test.js (la partita "
        f"vera con la macchina, apriGioco: {APRI_GIOCO_C_E}). esegui_test li fa girare con "
        "Node insieme alla prova "
        "di fumo per fasi: ogni fase con ogni comando e ogni valore, partite intere fino alla "
        "fine, e ogni pagina misurata sul palco nei due orientamenti (niente fuori, niente "
        "sovrapposto, testo che ci sta)",
        "- manifesto: \"scheda\": {\"tipo\": \"gioco\", \"file\": [\"logica.js\"], \"stile\": "
        "\"tema.css\" (facoltativo), \"risorse\": [disegni .svg], \"giocatori\": {\"min\", "
        "\"max\"}, \"salva\": false, \"voce\": false, \"azioni\": [], \"condivisa\": false, "
        "\"macchina\": {\"inizio\": la prima fase, \"fasi\": {…}, \"esito_s\": "
        f"{mc.ESITO_S:g}}}}} (la forma intera è nel manifesto.json di partenza); cosa_fa per "
        "esempio {\"verbo\": \"propone\", \"oggetto\": \"una partita a tris sullo schermo\"}; "
        "input di solito nessuno",
        "- la partita. Ogni partita comincia nella fase «preparazione», di Calliope. «Inizia» "
        "c'è sempre e parte con min giocatori (o con quanti hanno detto «gioco anch'io», se sono "
        "di più); con min < max ci sono anche i pulsanti «N giocatori», da min a max. In "
        "gioco.test.js, dopo apriGioco e prima delle mosse, si tocca «Inizia» se nel manifesto "
        "giocatori min = max o «N giocatori» se min < max (g.tocca(\"2 giocatori\")); oppure "
        "apriGioco({ inizia: true }) con min = max, o apriGioco({ inizia: true, giocatori: 2 }) "
        "con min < max (lì giocatori serve sempre, da min a max), che parte già dalla fase "
        "d'inizio. Dopo l'ultima mossa si va a «fine» (classifica e «ancora»); "
        "«avanti» vale solo nella fase «esito»",
        f"- fasi: al più {mc.MAX_FASI} del gioco (nomi in minuscolo); preparazione, esito e fine "
        "sono di Calliope e non si dichiarano. Per ogni fase: pagina; turni (di serie true: dopo "
        "la mossa tocca al giocatore dopo; false: muove chiunque, e un numero di punti va a "
        "chi ha mosso, se si sa: con più giocatori e chi non si sa (una voce non riconosciuta, "
        "lo stesso schermo) non va a nessuno e chi è null, e la prova di fumo lo avvisa. Se i "
        "punti vanno a chi muove, usa una fase con i turni); verso (le fasi dove una mossa può portare; esito e fine valgono "
        f"sempre); comandi (al più {mc.MAX_COMANDI_FASE}). Le pagine sono di Calliope (scegli "
        "quella che serve, il disegno lo fa lei): scelte (titolo, testo e un pulsante per comando "
        "e valore, quanti ne stanno: una ventina in orizzontale); griglia (una scacchiera fino a "
        "12×12: vista dà «caselle»); messaggio (un testo grande e i pulsanti in fondo); punteggi "
        "(i giocatori con i punti); titolo (un titolo grande e un pulsante); classifica; tela "
        "(sotto)",
        "- comandi: forme da dire per intero (1–5 parole; il nome davanti e i numeri in cifre o "
        "in parole valgono già), al più uno slot {n} per forma con \"n\": {\"da\": 1, \"a\": 6} "
        f"(un numero, al più {mc.MAX_NUMERI}) o \"n\": {{\"valori\": {{\"rosso\": [\"rosso\"], "
        f"\"blu\": [\"blu\", \"azzurro\"]}}}} (al più {mc.MAX_VALORI}); {{n}} da solo solo con "
        f"al più {mc.MAX_SOLO_SLOT} valori; etichetta del pulsante. In tutto, con i valori, al "
        f"più {mc.MAX_PIATTI} comandi a voce. Non si usano «basta», «stop», «esci» né le forme "
        f"di Calliope ({std}, «N giocatori», «siamo in N»), né le domande che Calliope "
        "risponde da sé («a chi tocca?», «quanti punti ho?», «chi sta vincendo?», «cosa posso "
        "dire?»)",
        "- giocatori: i nomi sono di Calliope («gioco anch'io» a voce, o scritti toccando il nome "
        "nella fascia dei punti) e arrivano in nuovaPartita({ nomi }) e in ctx.giocatori. Con "
        "\"condivisa\": true nella scheda la stessa partita si gioca da più schermi di casa (un "
        "motore solo; chi è quale giocatore lo decide Calliope, niente da scrivere in più). Chi "
        "dice «gioco anch'io» a partita cominciata entra dalla prossima partita; con "
        "GIOCO.entra(dati, ctx) → i dati con il giocatore nuovo (ctx.nuovo è la sua posizione) "
        "entra subito. Con \"giocatore\": true nella macchina la mossa riceve anche giocatore (il "
        "nome di chi l'ha detta, se la voce è riconosciuta; spesso manca: il gioco va anche "
        "senza)",
        "- GIOCO: nuovaPartita({ giocatori, nomi }) → i dati della partita (un oggetto JSON): "
        "qui giocatori è il NUMERO dei giocatori (2), nomi l'elenco dei loro nomi; i punti li "
        "tiene Calliope, non vanno nei dati; "
        "attivi[fase](dati, ctx) → { comando: true | false | [valori] } (restringe, mai fuori dal "
        "manifesto; senza: tutti; una fase che non è la fine ha sempre almeno un comando "
        "attivo); vista[fase](dati, ctx) → { titolo, sottotitolo, testo } (solo testi brevi: il "
        "titolo sta in due righe, il testo in tre) e, nella pagina griglia, «caselle»: un elenco "
        "di righe uguali, ogni casella un testo o { testo, colore, risorsa, comando, valore } "
        "(colore: rosso, verde, blu, giallo, arancio, viola, azzurro, rosa, marrone, grigio, "
        "nero, bianco o #rrggbb; risorsa: un .svg di «risorse»; con comando e valore attivi la casella "
        "è il pulsante della mossa, gli altri comandi attivi vanno in fondo)",
        "- mosse[fase][comando](dati, { valore, tocca, chi, giocatori, turno }) → { dati, punti, "
        "esito, "
        "fase, dopo, ancora } e NIENT'ALTRO: dati è lo stato del gioco dopo la mossa (tutto lì "
        "dentro); punti un numero a chi ha mosso o un elenco, uno per giocatore; ancora: true se "
        "lo stesso giocatore muove di nuovo. Il contesto della mossa: valore (il numero o la "
        "voce del comando), tocca la POSIZIONE di chi muove (0 il primo, 1 il secondo: nel tris "
        "il segno è [\"X\", \"O\"][tocca]; in una fase senza turni resta quella di prima), "
        "chi il suo nome, giocatori l'ELENCO [{ nome, "
        "punti }] (qui non è un numero), turno il GIRO (1, 1, 2, 2… con due giocatori: cresce "
        "quando tutti hanno mosso, non dice chi muove; con un giocatore solo resta 1: per "
        "contare le mosse tienile nei dati). In g.stato() invece tocca è il NOME di "
        "chi muove («Giocatore 1»). Chi muove lo tiene Calliope: non tenerlo anche nei dati "
        "(un indice tuo non passa mai al giocatore dopo). Dove si va, in una di tre forme: { dati, esito: "
        "\"…\", dopo: \"turno\" } mostra il testo nella fase «esito» e poi va a «dopo» (senza "
        "dopo: la stessa fase; dopo: \"fine\" per finire la partita); { dati, fase: \"fine\" } "
        "va subito lì, senza testo; { dati } resta nella fase. L'ESITO C'È SOLO QUANDO UNA "
        "MANO FINISCE (una vittoria, un pareggio, un punto fatto): una mossa normale (una "
        "casella segnata, una carta girata) restituisce { dati } (e i punti, se ci sono) e "
        "resta nella fase, senza esito. «esito» insieme a «fase» e "
        "«dopo» senza «esito» sono errori del motore (l'esito non si vedrebbe, dopo non farebbe "
        f"niente). L'esito va avanti da solo dopo esito_s secondi (0: solo con «avanti» o il "
        "tocco)",
        "- g.stato() in gioco.test.js dà esattamente { n, fase, tocca, turno, "
        "giocatori: [{ nome, punti }], esito, comandi }: tocca è il nome di chi muove "
        "(\"Giocatore 1\" senza nomi; null nella preparazione), esito il testo dell'esito "
        "(null fuori dalla fase «esito»), comandi un OGGETTO dei comandi che valgono adesso { porta: [1, 3], avanti: "
        "true } (non una lista: g.stato().comandi.porta, \"avanti\" in g.stato().comandi). Non "
        "c'è il vincitore: chi vince si legge dai punti di giocatori. Le altre: g.tocca(\"testo "
        "del pulsante\"), g.comando(\"porta\", 3) (come la voce), g.avanza(ms), g.testo() (il "
        "testo visibile), g.palco() → [] se la pagina di adesso sta nel palco",
        "- il caso: Math.random() in logica.js va bene; in apriGioco e nella prova di fumo ha un "
        "seme fisso (apriGioco({ seme: 7 }): la stessa partita a ogni esecuzione). In "
        "logica.test.js un risultato che dipende dal caso si prova con i dati fatti a mano (il "
        "premio dietro la porta 2), non con nuovaPartita; creaCaso(seme) → una funzione come "
        "Math.random, con il seme (c'è già nei test, senza require)",
        "- giochi in tempo reale o senza turni (memory a tempo, abilità, disegno): una fase con "
        "\"pagina\": \"tela\" e GIOCO.tela[fase](area, dati, tela): disegni dentro area (DOM o "
        "canvas, eventi con addEventListener; misura tela.larghezza × tela.altezza px del "
        "palco, niente fuori) e ne esci con tela.esci({ dati, punti, fase: \"fine\" }); «fine "
        "partita» vale sempre. Una tela che vuole un orientamento solo lo dichiara nella fase "
        "(\"orientamento\": \"orizzontale\" o \"verticale\"): sul telefono girato "
        "dall'altra parte Calliope dice di girarlo. Nella tela c'è l'oggetto calliope: "
        "calliope.salva(chiave, valore) e calliope.leggi(chiave) → Promise (con «salva», "
        f"valore JSON fino a {gi.MAX_SALVA // 1000} kB), calliope.di(testo) → Promise (con "
        f"«voce»: al più {c('giochi_frasi_minuto', 3)} frasi al minuto, {gi.MAX_FRASE} "
        "caratteri), calliope.risorsa(\"carta.svg\") → indirizzo data: del disegno, "
        "calliope.azione(nome, argomenti) → Promise (§3)",
        f"- tetti: un messaggio fino a {c('giochi_messaggio_max', 4096)} byte, "
        f"{c('giochi_messaggi_secondo', 10)} al secondo; se il riquadro non risponde per "
        f"{c('giochi_watchdog_s', 6.0):g} s (un ciclo infinito) si chiude; script "
        f"{sc.MAX_JS_BYTE // 1000} kB in tutto, al più {sc.MAX_FILE_JS} file",
        "- vietato nel codice del gioco (il riquadro lo blocca e chi approva lo vede): fetch, "
        "XMLHttpRequest, WebSocket, WebRTC, Worker, eval e new Function, localStorage e "
        "cookie, window.open, location, top/parent/opener, postMessage diretto, onclick=\"…\" "
        "nell'HTML (usa addEventListener), iframe, script o link creati a mano; require, import "
        "ed export nei file della scheda (si caricano uno dopo l'altro come i <script>: solo "
        "module.exports in fondo, per i test)",
        "- GIOCO PURO: «permessi» vuoti e «azioni» vuote (solo il riquadro, i dati suoi, la "
        "voce): lo usano tutti, anche gli ospiti e sugli schermi di stanza, e lo approva un "
        "adulto di casa. Con permessi o azioni lo approva solo chi amministra: per un gioco "
        "chiedi il minimo",
    ]


def _azioni_gioco() -> list[str]:
    """Le azioni della porta che un riquadro può chiedere (scheda.AZIONI), con il loro scope
    dalla tabella della porta: il §3 del contratto del gioco (19/10, #186)."""
    from .scheda import AZIONI
    righe = ["- Solo da una tela: calliope.azione(nome, argomenti) → Promise, con il nome in "
             "«scheda.azioni» e lo scope in «permessi» del manifesto (lo chiedi con "
             "chiedi_permesso). Il gioco smette di essere puro: lo approva solo chi amministra."]
    for az in AZIONI:
        es, scope, cosa = PORTA[az]
        righe.append(f"- {az}: {cosa}. Scope: `{_scope_detto(scope)}`.")
    return righe


def _scope_detto(s: dict) -> str:
    import json
    return json.dumps(s, ensure_ascii=False)


def impossibili(gioco: bool = False) -> dict:
    """{voce: (cosa, alternativa)} degli impossibili; per un gioco con le voci dette per un
    gioco e senza quelle che lì non valgono (`_IMPOSSIBILI_GIOCO`). Li usano il contratto e
    lo strumento piano (agenti/ciclo.py), così il piano dice le stesse cose del contratto."""
    voci = {k: (_IMPOSSIBILI_GIOCO.get(k, v) if gioco else v) for k, v in IMPOSSIBILI.items()}
    return {k: v for k, v in voci.items() if v}


def voci_piano(gioco: bool = False) -> tuple:
    """Le voci che lo strumento piano accetta in capacita_necessarie (per un gioco senza quelle
    che lì non valgono: 20/10, seconda revisione della PR #188, «javascript» chiudeva un gioco
    come impossibile)."""
    tolte = {k for k, v in _IMPOSSIBILI_GIOCO.items() if v is None} if gioco else set()
    return tuple(x for x in CAPACITA_IDS if x not in tolte)


def _impossibili(n: int, gioco: bool = False) -> list[str]:
    """La sezione degli impossibili, numerata `n`, e le voci per il piano. `gioco`: con le voci
    dette per un gioco (`_IMPOSSIBILI_GIOCO`)."""
    righe = ["", f"## {n}. Impossibile (dillo subito con piano(fattibile=false), con "
             "l'alternativa)"]
    righe += [f"- {k}: {v[0]}. Alternativa: {v[1]}." for k, v in impossibili(gioco).items()]
    righe += ["", "Voci per piano.capacita_necessarie: " + ", ".join(voci_piano(gioco)) + "."]
    return righe


def testo(cfg=None, tipo: str = "estensione", linguaggi=("python",)) -> str:
    """Il contratto, in Markdown semplice (anche nel prompt). `tipo`: «estensione», «gioco»
    (dal 19/10, #186, un contratto suo: la scheda, le azioni del riquadro, gli impossibili;
    niente porta Python né limiti del contenitore) o «codice» (un programma qualunque nella
    sandbox). Le sezioni sono in ordine e una regola sta in una sezione sola."""
    from ..web import rete as _rete
    from . import porta as _porta
    tmax = float(getattr(cfg, "estensioni_tempo_max_s", 30) or 30)
    mmax = int(getattr(cfg, "estensioni_memoria_max_mb", 512) or 512)
    titolo = {"gioco": "gioco", "estensione": "estensione"}.get(tipo, "programma")
    righe = [f"# Contratto delle capacità ({titolo})"]
    if tipo == "gioco":
        righe += ["Generato dal codice di Calliope. Leggilo prima di decidere: il primo passo è "
                  "lo strumento «piano».", "", "## 1. Da sola (nessun permesso)",
                  f"- scheda: {DA_SOLA['scheda']}{_SCHEDA_DOVE['gioco']}",
                  "- linguaggio: JavaScript nel riquadro del browser; i test con Node (node:test "
                  "e node:assert). Niente Python, niente estensione.py",
                  "", "## 2. La scheda e la macchina a stati"]
        righe += scheda_testo(cfg)
        righe += ["", "## 3. Chiedendo a Calliope (di solito non serve)"] + _azioni_gioco()
        righe += _impossibili(4, gioco=True)
        return "\n".join(righe) + "\n"
    if tipo == "estensione":
        righe += ["Generato dal codice di Calliope. Leggilo prima di decidere: il primo passo è "
                  "lo strumento «piano».", "", "## 1. Da sola (nessun permesso)"]
        righe += [f"- {k}: {v}{_SCHEDA_DOVE['estensione'] if k == 'scheda' else ''}"
                  for k, v in DA_SOLA.items()]
        # urllib.parse sì, la rete diretta no (19/10, #186: il contratto vietava «urllib» e il
        # prompt chiedeva urllib.parse.urlencode)
        righe += ["- linguaggio: Python 3.12, libreria standard, BeautifulSoup (from bs4 import "
                  "BeautifulSoup, con \"html.parser\"), json/csv/xml; niente pip, niente rete "
                  "diretta (socket, urllib.request, http.client: vietati; urllib.parse per "
                  "scrivere gli indirizzi sì), niente disco (solo /tmp)",
                  "", "## 2. Chiedendo a Calliope (porta stretta): metodo, scope da "
                  "dichiarare in «permessi» del manifesto, come lo tratta il guardrail"]
        for az, (es, scope, cosa) in PORTA.items():
            righe.append(f"- `{es}`: {cosa}. Scope: `{_scope_detto(scope)}`. "
                         f"{classe_detta(az).capitalize()}.")
        righe += ["- Ogni metodo può alzare ErroreCalliope (permesso negato, «no» della "
                  "persona, quota): gestiscila e restituisci un da_dire che lo spiega.",
                  "- Se non trovi quello che ti è stato chiesto (una città, un nome, un "
                  "file), restituisci anche «trovato»: false accanto al da_dire che lo dice: "
                  "così Calliope può chiedere se intendeva un nome simile.",
                  "- Non te li dai da sola: flussi in «invia», rete.post, scrive.casa. Mettili "
                  "nel manifesto solo dopo chiedi_permesso (con lo scope): lo chiedo io alla "
                  "persona.",
                  "- Flussi verso fuori: `\"invia\": [{\"dati\": \"liste:spesa\", \"host\": "
                  "\"api.prezzi.it\", \"metodo\": \"GET\"}]` (dati: casa, agenda, liste, "
                  "liste:<nome>). Senza flusso, dopo una lettura di dati personali la rete è "
                  "chiusa: fai le letture di internet PRIMA.",
                  "", "## 3. Limiti",
                  f"- tempo: limiti.tempo_s fino a {tmax:g} s; memoria: limiti.memoria_mb da 64 "
                  f"a {mmax} MB",
                  f"- per esecuzione: {gr.MAX_RICHIESTE} richieste alla porta, "
                  f"{gr.MAX_RETE} di rete, {gr.MAX_COMANDI_CASA} comandi della casa",
                  f"- rete: solo internet pubblico, porte 80 e 443, risposta fino a "
                  f"{_porta.MAX_RETE_BYTE // 1000} kB, testo/HTML/JSON/CSV/XML "
                  f"({', '.join(_rete.TIPI_DATI[:5])}…), "
                  f"{int(getattr(cfg, 'estensioni_rete_max_minuto', 30) or 30)} richieste al "
                  "minuto per tutto Calliope; mai dati riservati di casa nell'indirizzo",
                  "- indirizzi: i valori dei parametri (una città, un nome, una ricerca) si "
                  "codificano con urllib.parse.urlencode (o quote per un pezzo del percorso), "
                  "mai a mano come f\"...?name={citta}\": un URL con spazi, accenti o apostrofi "
                  "non codificati la porta lo rifiuta («URL non valido…»), e anche CalliopeFinta "
                  "nei test. Codifica una volta sola: con urlencode passa il testo com'è, mai "
                  "quote_plus prima («name=Borgo%2BAlto» cerca un + letterale e non trova "
                  "niente; la traccia lo segna come possibile doppia codifica). Nei test prova "
                  "anche un valore di due parole con un accento e controlla l'URL che arriva a "
                  "CalliopeFinta (in richieste)",
                  # Le sonde e il ricollaudo (08/10 notte, calliope/sonde.py, § 9.5)
                  "- sonde (solo nelle correzioni): sonda_rete fa una GET vera al posto di "
                  "scarica_esempio, solo verso i siti già usati nei collaudi o approvati, solo "
                  "con i valori dei collaudi e della specifica (numeri, date, codici di lingua "
                  f"e paese), al più {int(getattr(cfg, 'sviluppo_sonde_max', 4) or 0)} per "
                  f"lavoro e {int(getattr(cfg, 'sviluppo_sonde_passata', 2) or 0)} per "
                  "passata; un sito nuovo solo con chiedi_permesso. Alla consegna di una "
                  "correzione Calliope riprova la tua versione con i casi della persona: se non "
                  "va, te la rimanda con la traccia",
                  f"- dati propri: {_porta.MAX_DATO_BYTE // 1000} kB per testo, "
                  f"{_porta.MAX_DATI_BYTE // 1000} kB in tutto",
                  "- input: al più 6 proprietà (string, number, integer, boolean), testi fino "
                  "a 500 caratteri"]
        righe += _impossibili(4)
        return "\n".join(righe) + "\n"
    from ..agenti.linguaggi import LINGUAGGI
    righe += ["Generato dal codice di Calliope: cosa può fare un programma nella sandbox.",
              "", "## 1. Da solo",
              "- " + "; ".join(LINGUAGGI[n].per_agente for n in linguaggi if n in LINGUAGGI),
              "- leggere e scrivere i file della cartella del lavoro; eseguire e testare",
              "", "## 2. Chiedendo a chi ha chiesto il lavoro",
              "- un dato che manca (suo, della sua casa o azienda): consegna con esito "
              "mancano_dati e la domanda, prima di scrivere il codice",
              "", "## 3. Limiti",
              f"- niente rete, niente shell, niente pip; tempo per esecuzione "
              f"{float(getattr(cfg, 'agenti_esecuzione_s', 30) or 30):g} s, memoria "
              f"{int(getattr(cfg, 'agenti_memoria_mb', 1024) or 1024)} MB",
              "", "## 4. Non si prova qui",
              "- rete, altri programmi, interfacce grafiche, file fuori dalla cartella: se "
              "il compito li vuole, scrivi il codice con i test sulle parti che si provano "
              "e dillo nel riassunto",
              "- se il compito non si può fare affatto, consegna SUBITO con esito "
              "impossibile e un'alternativa, senza ragionarci a lungo"]
    return "\n".join(righe) + "\n"
