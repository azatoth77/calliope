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
    # 05/10: un gioco (o una scheda che si usa toccando) nel browser degli schermi
    "scheda": "una scheda interattiva sugli schermi (un gioco): JavaScript nel browser, in un "
              "riquadro isolato, con la sezione «scheda» del manifesto (vedi §5)",
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
                   "porta qui sotto"),
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
    codice: formato, interfaccia del riquadro, tetti, test, chi approva."""
    from . import scheda as sc
    from ..schermi import giochi as gi
    c = lambda k, d: getattr(cfg, k, d) if cfg is not None else d  # noqa: E731
    return [
        "", "## 5. Scheda interattiva (giochi)",
        "Un gioco gira nel BROWSER degli schermi (PC, tablet, telefono), in un riquadro isolato "
        "(iframe sandbox, origine opaca): niente rete, niente localStorage, niente pagina "
        "intorno. Non serve estensione.py: solo JavaScript.",
        "- file: logica.js (le regole del gioco, funzioni pure senza DOM, in fondo `if (typeof "
        "module !== \"undefined\") module.exports = {…};`), gioco.js (disegno e tocchi: DOM, "
        "canvas o SVG dentro <div id=\"gioco\">, eventi con addEventListener), facoltativi "
        "gioco.css e disegni .svg; i test logica.test.js con node:test e node:assert "
        "(`const { … } = require(\"./logica.js\")`), che esegui_test fa girare con Node, "
        "insieme a una prova di fumo: gli script della scheda con un DOM finto e trecento "
        "tocchi a caso (dichiara ogni variabile con let o const, \"use strict\" in cima). Nel "
        "riquadro gli script si caricano uno dopo l'altro nello stesso spazio globale, come i "
        "<script> del browser: gioco.js usa le funzioni di logica.js direttamente, senza "
        "require né import (require solo nei test)",
        "- manifesto: \"scheda\": {\"tipo\": \"gioco\", \"file\": [\"logica.js\", \"gioco.js\"], "
        "\"stile\": \"gioco.css\", \"risorse\": [], \"giocatori\": {\"min\": 1, \"max\": 2}, "
        "\"condivisa\": false, \"chat\": false, \"salva\": true, \"voce\": false, "
        "\"azioni\": []}; cosa_fa per esempio {\"verbo\": \"propone\", \"oggetto\": \"una "
        "partita a tris sullo schermo\"}; input di solito nessuno",
        "- nel riquadro c'è l'oggetto calliope: calliope.quandoPronto(f) (f riceve {giocatore, "
        "giocatori, massimo, condivisa, storia}); calliope.salva(chiave, valore) e "
        "calliope.leggi(chiave) → Promise (record e partite, chiave di lettere e cifre, valore "
        f"JSON fino a {gi.MAX_SALVA // 1000} kB, {gi.MAX_DATI // 1_000_000} MB in tutto); "
        "calliope.manda(dati) e calliope.quandoMessaggio(f) (con «condivisa»: le mosse agli "
        "altri schermi della partita, f riceve {n, da, dati}); calliope.chat(testo) e "
        "calliope.quandoChat(f) (con «chat»); calliope.di(testo) → Promise (con «voce»: "
        f"una frase breve detta da Calliope, al più {c('giochi_frasi_minuto', 3)} al minuto, "
        f"{gi.MAX_FRASE} caratteri); calliope.azione(nome, argomenti) → Promise (solo i metodi "
        "della porta elencati in «azioni» e con lo scope in «permessi»); calliope.fine(esito); "
        "calliope.risorsa(\"carta.svg\") → indirizzo data: del disegno; "
        "calliope.quandoGiocatori(f), calliope.quandoFineTempo(f)",
        f"- tetti: un messaggio fino a {c('giochi_messaggio_max', 4096)} byte, "
        f"{c('giochi_messaggi_secondo', 10)} al secondo; se il riquadro non risponde per "
        f"{c('giochi_watchdog_s', 6.0):g} s (un ciclo infinito) si chiude; script "
        f"{sc.MAX_JS_BYTE // 1000} kB in tutto, al più {sc.MAX_FILE_JS} file",
        "- vietato nel codice del gioco (il riquadro lo blocca e chi approva lo vede): fetch, "
        "XMLHttpRequest, WebSocket, WebRTC, Worker, eval e new Function, localStorage e "
        "cookie, window.open, location, top/parent/opener, postMessage diretto, onclick=\"…\" "
        "nell'HTML (usa addEventListener), iframe, script o link creati a mano",
        "- con un bambino o un ospite nella partita i messaggi di calliope.manda portano solo "
        "valori brevi senza spazi (mosse, coordinate): il testo libero va con calliope.chat",
        "- GIOCO PURO: «permessi» vuoti e «azioni» vuote (solo il riquadro, i dati suoi, la "
        "voce, la partita condivisa): lo usano tutti, anche gli ospiti e sugli schermi di "
        "stanza, e lo approva un adulto di casa. Con permessi o azioni lo approva solo chi "
        "amministra: per un gioco chiedi il minimo",
    ]


def _scope_detto(s: dict) -> str:
    import json
    return json.dumps(s, ensure_ascii=False)


def testo(cfg=None, tipo: str = "estensione", linguaggi=("python",)) -> str:
    """Il contratto, in Markdown semplice (anche nel prompt). `tipo`: «estensione» o
    «codice» (un programma qualunque nella sandbox)."""
    from ..web import rete as _rete
    from . import porta as _porta
    tmax = float(getattr(cfg, "estensioni_tempo_max_s", 30) or 30)
    mmax = int(getattr(cfg, "estensioni_memoria_max_mb", 512) or 512)
    # «gioco» (05/10): il contratto delle estensioni con la scheda interattiva per intero
    est = tipo in ("estensione", "gioco")
    righe = [f"# Contratto delle capacità ({ {'gioco': 'gioco', 'estensione': 'estensione'}.get(tipo, 'programma')})",
             "Generato dal codice di Calliope. Leggilo prima di decidere: il primo passo è "
             "lo strumento «piano»." if est else
             "Generato dal codice di Calliope: cosa può fare un programma nella sandbox."]
    if est:
        righe += ["", "## 1. Da sola (nessun permesso)"]
        righe += [f"- {k}: {v}" for k, v in DA_SOLA.items()]
        righe += ["- linguaggio: Python 3.12, libreria standard, BeautifulSoup (bs4), "
                  "json/csv/xml; niente pip, niente rete diretta (socket, urllib: vietati), "
                  "niente disco (solo /tmp)",
                  "", "## 2. Chiedendo a Calliope (porta stretta): metodo, scope da "
                  "dichiarare in «permessi» del manifesto, come lo tratta il guardrail"]
        for az, (es, scope, cosa) in PORTA.items():
            righe.append(f"- `{es}`: {cosa}. Scope: `{_scope_detto(scope)}`. "
                         f"{classe_detta(az).capitalize()}.")
        righe += ["- Ogni metodo può alzare ErroreCalliope (permesso negato, «no» della "
                  "persona, quota): gestiscila e restituisci un da_dire che lo spiega.",
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
                  f"- dati propri: {_porta.MAX_DATO_BYTE // 1000} kB per testo, "
                  f"{_porta.MAX_DATI_BYTE // 1000} kB in tutto",
                  "- input: al più 6 proprietà (string, number, integer, boolean), testi fino "
                  "a 500 caratteri"]
    else:
        from ..agenti.linguaggi import LINGUAGGI
        righe += ["", "## 1. Da solo",
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
    righe += scheda_testo(cfg) if tipo == "gioco" else [
        "", "## 5. Scheda interattiva (giochi)",
        "- un gioco sullo schermo (tris, memory, quiz) è un'estensione con una «scheda» in "
        "JavaScript nel browser, non in Python: si chiede con estensione_crea gioco=true, e il "
        "contratto per i giochi lo spiega"]
    righe +=["", "## 4. Impossibile (dillo subito con piano(fattibile=false), con "
              "l'alternativa)"]
    righe += [f"- {k}: {cosa}. Alternativa: {alt}." for k, (cosa, alt) in IMPOSSIBILI.items()]
    righe += ["", "Voci per piano.capacita_necessarie: " + ", ".join(CAPACITA_IDS) + "."]
    return "\n".join(righe) + "\n"
