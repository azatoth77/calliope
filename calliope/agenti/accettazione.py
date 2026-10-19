"""
Il flusso dell'agente a fasi, parte 2: l'analisi prima del codice e gli esempi di accettazione
(13/10/2026; ricerca docs/ricerche/2026-10-12-flusso-agente-fasi.md § 5.1 passi 3 e 4,
domande 1, 2 e 4 accettate da chi amministra il 12/10; area agenti-estensioni).

**Perché un'altra passata.** I test che l'agente scrive insieme al codice ereditano le sue
ipotesi (AgentCoder: giusti al 51–61 % contro l'88–90 % di un agente separato) e il 12/10 l'agente
li cambiava per farli tornare. Sul banco della temperatura (12–13/10, il convertitore di
distanze) con presence_penalty 0,25 o 0,5 alcuni lavori hanno consegnato «fatto» con
l'accettazione nascosta rossa: i test dell'agente erano verdi e sbagliati. Qui il modello
dell'agente, in una passata **nuova** (non la conversazione dell'agente; non vede il codice, che
non c'è ancora), legge i requisiti e le parole della persona e compila un JSON chiuso:

- **esempi dato → risultato** (solo per le estensioni, che hanno un contratto stabile:
  `esegui(dati, calliope)` e `CalliopeFinta`): gli input, un numero atteso con la sua tolleranza,
  una parola che la frase deve contenere, «trovato»: false. Il test lo scrive **il codice**
  (`test_python`), non il modello: niente oracoli copiati dall'implementazione. Va nella cartella
  come `test_accettazione.py` **in sola lettura**; alla consegna si esegue con gli altri test
  (`Agente._test_falliti`), e l'agente che lo trova sbagliato lo dice nella consegna, non lo
  cambia. Ogni esempio controlla almeno una cosa che uno scheletro vuoto (`{"da_dire": ""}`)
  non fa: per costruzione fallisce sullo scheletro (lo verifica anche la prova);
- **i valori nominati** (14/10, banco della temperatura L2: «fatto» con 7 esempi verdi e
  l'accettazione nascosta rossa, perché nessun esempio usava «unità astronomiche» al plurale,
  che la richiesta elencava e l'estensione non riconosceva): per ogni input di testo i valori
  che la richiesta nomina (`valori`). Il codice tiene solo quelli che compaiono **alla lettera**
  nella richiesta (requisiti, specifica, parole della persona: senza maiuscole né accenti) e,
  per ognuno che nessun esempio usa già, scrive un controllo in più: i dati di un esempio con
  quel valore al posto del suo, e l'estensione deve riconoscerlo (una frase, niente «trovato»:
  false, il numero se l'esempio lo controllava). Fallisce sullo scheletro come gli esempi;
- **gli esempi contro la richiesta** (14/10 sera, banco: rieseguiti sull'estensione di
  riferimento, quattro convertitori su cinque avevano un esempio che una soluzione giusta non
  passa): per un input con valori nominati un esempio con un valore che la richiesta non dice
  («Km», «centimetri», confrontati al singolare e al plurale) vale solo per il dato sconosciuto;
  il «calcolo» dell'esempio (un conto con soli numeri) lo rifà il codice e, se non torna con il
  numero, l'esempio si toglie; con un altro controllo (il numero, «trovato»: false) «contiene»
  perde le parole che ripetono i dati; con «trovato»: false niente numero;
- **contraddizioni** tra requisiti, o tra i requisiti e le parole della persona (il 12/10
  «giocatori» è diventato «porte»), con al più **due domande** brevi: il lavoro aspetta la
  risposta come una domanda a metà lavoro (`mancano_dati`). Solo in un lavoro nuovo (non una
  correzione né la modifica di una versione che c'è: lì la specifica viva tiene già i requisiti
  senza contrasti). Senza contraddizioni il lavoro parte senza chiedere: è il caso normale
  (HumanEvalComm: un agente che domanda sempre peggiora sui problemi già chiari);
- **scelte** fatte dove la richiesta non dice, scritte all'agente;
- **al collaudo**: i requisiti che si giudicano solo guardando o ascoltando (musica, aspetto,
  «adatto ai bambini»): la revisione li dice «da guardare tu», non fatti né mancanti.

**I programmi** (17/10, issue #10): un programma non ha un'interfaccia fissa, quindi la
dichiara la passata, prima del codice: linguaggio, nome del file e genere d'interfaccia. Solo per
un programma **a riga di comando** in Python (o in JavaScript con Node acceso, #54) scrive gli
esempi `{argomenti, stdin, numero | contiene, codice_uscita}`; il codice li valida come quelli
delle estensioni (il «calcolo» rifatto, una parola che la richiesta non dice solo nel caso
d'errore, ogni esempio con argomenti o stdin e un controllo che lo scheletro non passa) e li
trasforma in `test_accettazione.py` (il programma eseguito con runpy nello stesso processo:
l'audit hook della sandbox non lascia avviare processi) o in `accettazione.test.js` (Node in un
processo figlio, con i permessi di esegui_js). Il programma deve chiamarsi come dice
l'interfaccia: la consegna lo dice all'agente una volta (`controlla_nome`). Restano senza esempi,
come prima, i programmi su file della persona, il C# (niente esegui_test) e gli altri generi:
la passata cerca solo le contraddizioni, e solo nel primo lavoro di uno sviluppo. Fuori da uno
sviluppo un programma nuovo fa la passata per gli esempi, senza domande.

**I giochi** (13/10, dopo la macchina a stati: estensioni/macchina.py, motore_gioco.js): nel primo
lavoro di uno sviluppo di un gioco nuovo la passata scrive anche gli esempi **in forma chiusa**:
i comandi che la macchina deve avere (nome, fase, valori), e per ogni esempio il numero dei
giocatori, le mosse (comando e valore) e lo stato atteso dopo (fase, a chi tocca, punti, comandi
che valgono e che non valgono più, una parola che si legge). Il test lo scrive il codice
(`test_js`, `accettazione.test.js` in sola lettura) e gioca la partita vera con il motore di
Calliope nel DOM finto (`apriGioco`, `g.comando`, `g.stato()`): lo stesso stato che vede la
persona. Un esempio usa sempre almeno un comando del gioco, quindi fallisce su un gioco che non
ce l'ha. Le mosse non devono dipendere dal caso (dove sta il premio): lo dice il prompt.

Il client e la passata sono quelli dei requisiti (`requisiti.chiama`: schema chiuso, temperatura
0, senza ragionamento; dal 17/10 il ragionamento si accende con
`agenti_accettazione_ragionamento`, spento di serie finché il mini-banco non dice che conviene).
Solo libreria standard.
"""

from __future__ import annotations

import json
import math
import re

FILE = "test_accettazione.py"
FILE_GIOCO = "accettazione.test.js"
MAX_ESEMPI = 8
MAX_COMANDI_GIOCO = 6
MAX_MOSSE = 12
STANDARD_GIOCO = ("avanti", "ancora")     # i comandi di Calliope che un esempio può usare
FASI_STANDARD = ("preparazione", "esito", "fine")
MAX_DOMANDE = 2
MAX_SCELTE = 3
MAX_INPUT = 6
MAX_VALORI = 16            # i valori nominati per un input di testo
MAX_RICONOSCIUTI = 12      # i controlli «il valore nominato si riconosce» in tutto
TIPI = ("number", "integer", "string", "boolean")
_NOME = re.compile(r"^[a-z][a-z0-9_]{0,30}$")

SISTEMA = """Sei il progettista dei test di Calliope, un'assistente vocale di casa. Un agente programmatore sta per scrivere {cosa}. Tu NON vedi il codice e non lo scrivi: dai requisiti e dalle parole della persona compili il JSON, prima che il codice esista.

contraddizioni: solo se due requisiti (o un requisito e le parole della persona) dicono cose che non possono valere insieme, oppure se manca un dato senza il quale il risultato cambia del tutto. Per ognuna i numeri dei requisiti e una domanda breve da dire a voce, meglio come esempio da confermare («Quindi con due giocatori le porte restano le stesse per tutti e due?»). Al più 2. Se è tutto chiaro la lista è vuota: è il caso normale, non inventare dubbi.
scelte: le cose che la richiesta non dice e che decideresti da solo, una frase breve ciascuna (al più 3).
al_collaudo: i numeri dei requisiti che si giudicano solo guardando o ascoltando (suoni, aspetto, «adatto ai bambini», «bello»): nessun test li prova.{estensione}"""

SISTEMA_ESEMPI = """
input: gli input dell'estensione (il dict «dati» che riceve esegui), con nome (minuscole e _) e tipo (number, integer, string, boolean). Se la specifica li nomina usa quei nomi, esattamente. Per un input string, valori: TUTTI i valori che la richiesta nomina per quell'input, scritti come nella richiesta (se li scrive al plurale e al singolare, tutte e due le forme); lista vuota se non ne nomina.
campo_numero: il nome del campo numerico del risultato, se l'estensione restituisce un numero (di solito «risultato»); altrimenti vuoto.
esempi: da 3 a 8 esempi dato → risultato, almeno uno per ogni requisito che si controlla con un dato. Per ognuno: requisito (il numero), dati (gli input con valori veri, come li direbbe la persona; per un input con dei valori nominati solo quelli, al singolare o al plurale: un valore che la richiesta non nomina solo nel caso del dato sconosciuto), e cosa deve risultare:
- numero: il valore atteso nel campo numerico, calcolato con cura (se arrotondi metti la tolleranza); se non sei sicuro di un valore non usare quell'esempio;
- calcolo: lo stesso numero come conto con soli numeri e + - * / ( ), per esempio «10 * 1609.344 / 1000»: lo rifà il codice;
- contiene: una o due parole che la frase da_dire deve contenere (un nome detto dalla persona, «non»); mai numeri, mai frasi intere; in un esempio con il numero non serve ripetere i valori dei dati;
- trovato: false se il dato non esiste o non si capisce e l'estensione deve dire che non l'ha trovato; altrimenti null.
Ogni esempio controlla almeno una cosa (numero, contiene o trovato false). Se la richiesta nomina valori di più parole o con l'accento metti un esempio con uno di quelli; metti anche un caso con un dato sconosciuto."""


SISTEMA_GIOCO = """
Il gioco usa la macchina a stati di Calliope: la partita comincia scegliendo il numero dei giocatori (lo fa il test), poi la fase d'inizio del gioco; dopo ogni mossa di solito c'è la fase «esito» (il testo di cosa è successo, poi si va avanti da soli), e alla fine la fase «fine» con la classifica. I turni passano da soli al giocatore dopo; i punti li tiene Calliope. Ogni comando del gioco è un nome breve (minuscole e _), in una fase, con al più un valore: un numero (da, a) o una voce di un elenco (valori).
comandi: i comandi che il gioco DEVE avere perché gli esempi si possano giocare (al più 6), con fase (minuscole, di solito «turno»), nome, e da/a per un numero oppure valori per un elenco; niente valore se il comando non ne ha. Non usare i nomi di Calliope (inizia, avanti, ancora, giocatori).
esempi: da 2 a 6 partite brevi, una per requisito che si controlla giocando. Per ognuna: requisito (il numero), giocatori (quanti), mosse (comando e valore, nell'ordine; «avanti» non serve: il test va avanti da solo dopo l'esito), e atteso, lo stato dopo l'ultima mossa:
- fase: la fase in cui si è (una dei comandi, «esito» o «fine»), se il requisito lo dice;
- tocca: il numero del giocatore a cui tocca dopo (1 è il primo), se conta;
- punti: i punti di ogni giocatore, solo se NON dipendono dal caso;
- attivi e non_attivi: comandi (con il valore) che devono valere ancora o non più (una porta già aperta non si riapre);
- testo: una o due parole che si devono leggere sullo schermo subito dopo l'ultima mossa (un nome detto dalla persona), mai una frase intera.
Ogni esempio usa almeno un comando del gioco nelle mosse e controlla almeno una cosa. Mai controllare ciò che dipende dal caso (cosa c'è dietro una porta, chi vince): controlla le regole (turni, comandi che spariscono, la fine quando le mosse finiscono)."""


SISTEMA_PROGRAMMA = """
programma: come si usa il programma, deciso adesso perché gli esempi lo possano eseguire:
- linguaggio: python, salvo che la richiesta chieda un altro linguaggio{linguaggi};
- file: il nome del file da eseguire, minuscole e _ con l'estensione del linguaggio (per esempio «media_voti.py»), mai «test…»;
- interfaccia: «riga_di_comando» se il programma riceve i valori come argomenti (o righe sullo stdin) e stampa il risultato; «file» se lavora su file o cartelle della persona (foto, documenti, fogli); «altro» per tutto il resto (finestre, rete, programmi che girano a lungo). Gli esempi si scrivono solo per «riga_di_comando».
esempi (solo per «riga_di_comando»): da 3 a 8 esecuzioni, almeno una per ogni requisito che si controlla con un'esecuzione. Per ognuna: requisito (il numero), argomenti (la lista dei valori, come li direbbe la persona: niente opzioni con il trattino) oppure stdin (il testo da dare al programma, una riga per valore), e cosa deve risultare:
- numero: un valore che il programma deve stampare, calcolato con cura (se arrotondi metti la tolleranza); se non sei sicuro non usare quell'esempio; scegli dati con un risultato diverso da ognuno di loro (la media di 5, 8 e 9, non di 6, 7 e 8);
- calcolo: lo stesso numero come conto con soli numeri e + - * / ( ), per esempio «(7 + 8 + 6) / 3»: lo rifà il codice;
- contiene: una o due parole che l'uscita deve contenere (un nome detto dalla persona, «non»); mai numeri, mai frasi intere;
- codice_uscita: 0 se finisce bene, 1 se la richiesta dice che con quei dati deve fermarsi con un errore; null se non conta.
Ogni esempio ha argomenti o stdin e controlla almeno una cosa (numero, contiene o un codice d'uscita diverso da 0). Usa solo valori che la richiesta nomina o numeri; metti anche un caso con un dato sbagliato se la richiesta dice cosa fare."""

INTERFACCE = ("riga_di_comando", "file", "altro")
LINGUAGGI_PROGRAMMA = ("python", "javascript", "csharp", "altro")
_SUFFISSI = {"python": ".py", "javascript": ".js"}
MAX_ARGOMENTI = 10


def _nome_ok(x) -> bool:
    return isinstance(x, str) and bool(re.match(r"^[a-z][a-z0-9_]{0,13}$", x))


def schema(estensione: bool, gioco: bool = False, programma: bool = False) -> dict:
    prop = {
        "contraddizioni": {"type": "array", "maxItems": MAX_DOMANDE, "items": {
            "type": "object", "properties": {
                "requisiti": {"type": "array", "maxItems": 4, "items": {"type": "integer"}},
                "domanda": {"type": "string", "maxLength": 200}},
            "required": ["requisiti", "domanda"]}},
        "scelte": {"type": "array", "maxItems": MAX_SCELTE,
                   "items": {"type": "string", "maxLength": 160}},
        "al_collaudo": {"type": "array", "maxItems": 12, "items": {"type": "integer"}}}
    richiesti = ["contraddizioni", "scelte", "al_collaudo"]
    if estensione:
        prop.update({
            "input": {"type": "array", "maxItems": MAX_INPUT, "items": {
                "type": "object", "properties": {
                    "nome": {"type": "string", "maxLength": 31},
                    "tipo": {"type": "string", "enum": list(TIPI)},
                    "valori": {"type": "array", "maxItems": MAX_VALORI,
                               "items": {"type": "string", "maxLength": 40}}},
                "required": ["nome", "tipo"]}},
            "campo_numero": {"type": "string", "maxLength": 31},
            "esempi": {"type": "array", "maxItems": MAX_ESEMPI, "items": {
                "type": "object", "properties": {
                    "requisito": {"type": "integer"},
                    "dati": {"type": "object"},
                    "numero": {"type": ["number", "null"]},
                    "tolleranza": {"type": ["number", "null"]},
                    "calcolo": {"type": "string", "maxLength": 160},
                    "contiene": {"type": "string", "maxLength": 60},
                    "trovato": {"type": ["boolean", "null"]}},
                "required": ["requisito", "dati"]}}})
        richiesti += ["input", "campo_numero", "esempi"]
    elif gioco:
        coppia = {"type": "object", "properties": {
            "comando": {"type": "string", "maxLength": 14},
            "valore": {"type": ["integer", "string", "null"]}}, "required": ["comando"]}
        prop.update({
            "comandi": {"type": "array", "maxItems": MAX_COMANDI_GIOCO, "items": {
                "type": "object", "properties": {
                    "fase": {"type": "string", "maxLength": 16},
                    "nome": {"type": "string", "maxLength": 14},
                    "da": {"type": ["integer", "null"]}, "a": {"type": ["integer", "null"]},
                    "valori": {"type": "array", "maxItems": 24,
                               "items": {"type": "string", "maxLength": 9}}},
                "required": ["fase", "nome"]}},
            "esempi": {"type": "array", "maxItems": MAX_ESEMPI, "items": {
                "type": "object", "properties": {
                    "requisito": {"type": "integer"},
                    "giocatori": {"type": "integer"},
                    "mosse": {"type": "array", "maxItems": MAX_MOSSE, "items": coppia},
                    "atteso": {"type": "object", "properties": {
                        "fase": {"type": ["string", "null"]},
                        "tocca": {"type": ["integer", "null"]},
                        "punti": {"type": ["array", "null"], "items": {"type": "integer"}},
                        "attivi": {"type": "array", "maxItems": 4, "items": coppia},
                        "non_attivi": {"type": "array", "maxItems": 4, "items": coppia},
                        "testo": {"type": "string", "maxLength": 40}}}},
                "required": ["requisito", "giocatori", "mosse", "atteso"]}}})
        richiesti += ["comandi", "esempi"]
    elif programma:
        # 17/10 (#10): l'interfaccia a riga di comando dichiarata prima del codice
        prop.update({
            "programma": {"type": "object", "properties": {
                "linguaggio": {"type": "string", "enum": list(LINGUAGGI_PROGRAMMA)},
                "file": {"type": "string", "maxLength": 40},
                "interfaccia": {"type": "string", "enum": list(INTERFACCE)}},
                "required": ["linguaggio", "file", "interfaccia"]},
            "esempi": {"type": "array", "maxItems": MAX_ESEMPI, "items": {
                "type": "object", "properties": {
                    "requisito": {"type": "integer"},
                    "argomenti": {"type": "array", "maxItems": MAX_ARGOMENTI,
                                  "items": {"type": "string", "maxLength": 200}},
                    "stdin": {"type": "string", "maxLength": 2000},
                    "numero": {"type": ["number", "null"]},
                    "tolleranza": {"type": ["number", "null"]},
                    "calcolo": {"type": "string", "maxLength": 160},
                    "contiene": {"type": "string", "maxLength": 60},
                    "codice_uscita": {"type": ["integer", "null"]}},
                "required": ["requisito", "argomenti"]}}})
        richiesti += ["programma", "esempi"]
    return {"type": "object", "properties": prop, "required": richiesti}


def _numero(v) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if math.isfinite(v) else None


def _primitivo(v) -> bool:
    return v is None or isinstance(v, (str, bool, int, float)) and not (
        isinstance(v, float) and not math.isfinite(v))


def _comandi_gioco(d: dict) -> dict:
    """I comandi che il gioco deve avere, validati: {nome: {"fase", "valori": [...] | None}}."""
    out = {}
    for c in d.get("comandi") or ():
        if not isinstance(c, dict) or not _nome_ok(c.get("nome")) or not _nome_ok(c.get("fase")):
            continue
        nome, fase = c["nome"], c["fase"]
        if nome in ("inizia", "avanti", "ancora", "giocatori", "fine_partita", "anchio") \
                or nome in out \
                or fase in FASI_STANDARD:
            continue
        valori = None
        if isinstance(c.get("valori"), list) and c["valori"]:
            vs = [v for v in c["valori"] if isinstance(v, str)
                  and re.match(r"^[a-z0-9][a-z0-9_]{0,8}$", v)]
            if len(vs) != len(c["valori"]):
                continue
            valori = list(dict.fromkeys(vs))
        elif isinstance(c.get("da"), int) and isinstance(c.get("a"), int) \
                and not isinstance(c["da"], bool) and 0 <= c["da"] <= c["a"] <= 100 \
                and c["a"] - c["da"] < 60:
            valori = list(range(c["da"], c["a"] + 1))
        out[nome] = {"fase": fase, "valori": valori}
        if len(out) >= MAX_COMANDI_GIOCO:
            break
    return out


def _coppia(x, comandi: dict, standard: bool = True):
    """(comando, valore) validato contro i comandi dichiarati, o None."""
    if not isinstance(x, dict) or not isinstance(x.get("comando"), str):
        return None
    c, v = x["comando"].strip().lower(), x.get("valore")
    if isinstance(v, bool) or isinstance(v, float):
        return None
    if standard and c in STANDARD_GIOCO:
        return (c, None) if v in (None, "") else None
    d = comandi.get(c)
    if d is None:
        return None
    if d["valori"] is None:
        return (c, None) if v in (None, "") else None
    if isinstance(v, str) and v.strip().isdigit():
        v = int(v)
    return (c, v) if v in d["valori"] else None


def _esempi_gioco(d: dict, comandi: dict, n_requisiti: int) -> list[dict]:
    from ..requisiti import pulito
    out, chiavi = [], set()
    fasi = {x["fase"] for x in comandi.values()} | set(FASI_STANDARD) - {"preparazione"}
    for e in d.get("esempi") or ():
        if not isinstance(e, dict) or not isinstance(e.get("atteso"), dict):
            continue
        g = e.get("giocatori")
        if not isinstance(g, int) or isinstance(g, bool) or not 1 <= g <= 8:
            continue
        mosse = [_coppia(m, comandi) for m in (e.get("mosse") or ())][:MAX_MOSSE]
        if not mosse or None in mosse or not any(c not in STANDARD_GIOCO for c, _ in mosse):
            continue                       # almeno un comando del gioco: fallisce senza
        a = e["atteso"]
        atteso = {}
        if isinstance(a.get("fase"), str) and a["fase"] in fasi:
            atteso["fase"] = a["fase"]
        t = a.get("tocca")
        if isinstance(t, int) and not isinstance(t, bool) and 1 <= t <= g:
            atteso["tocca"] = t
        p = a.get("punti")
        if isinstance(p, list) and len(p) == g and all(
                isinstance(x, int) and not isinstance(x, bool) for x in p):
            atteso["punti"] = p
        for k in ("attivi", "non_attivi"):
            cs = [_coppia(x, comandi, standard=False) for x in (a.get(k) or ())][:4]
            cs = [list(x) for x in cs if x is not None]
            if cs:
                atteso[k] = cs
        testo = pulito(a.get("testo"), 40)
        if testo and len(testo.split()) <= 3:
            atteso["testo"] = testo
        if not atteso:
            continue
        chiave = json.dumps([g, mosse, atteso], sort_keys=True, ensure_ascii=False)
        if chiave in chiavi:
            continue
        chiavi.add(chiave)
        r = e.get("requisito")
        out.append({"requisito": r if isinstance(r, int) and not isinstance(r, bool)
                    and (n_requisiti <= 0 or 1 <= r <= n_requisiti) else 0,
                    "giocatori": g, "mosse": [list(m) for m in mosse], "atteso": atteso})
        if len(out) >= MAX_ESEMPI:
            break
    return out


def _norm(testo) -> str:
    """Minuscole, senza accenti né punteggiatura, spazi semplici: per i valori nominati."""
    import unicodedata
    t = unicodedata.normalize("NFD", str(testo or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w]+", " ", t).split())


def _valori(i: dict, testo: str) -> list[str]:
    """I valori nominati di un input di testo che compaiono alla lettera nella richiesta."""
    if i.get("tipo") != "string" or not isinstance(i.get("valori"), list) or not testo:
        return []
    detto, out, visti = f" {_norm(testo)} ", [], set()
    for v in i["valori"][:MAX_VALORI]:
        if not isinstance(v, str):
            continue
        v = re.sub(r"\s+", " ", v).strip(" .,;:«»\"'")
        n = _norm(v)
        if not n or len(v) > 40 or n in visti or f" {n} " not in detto:
            continue                       # un valore che la richiesta non dice: fuori
        visti.add(n)
        out.append(v)
    return out


def _radice(parola: str) -> str:
    """La parola senza la vocale finale (e «ch», «gh» come «c», «g»): il singolare e il
    plurale italiani si somigliano così («pollice» e «pollici», «astronomica» e
    «astronomiche», «miglio» e «miglia»). Solo per confrontare valori, mai per capire."""
    if len(parola) > 3 and parola[-1] in "aeiou":
        parola = parola[:-1]
    return parola[:-1] if parola.endswith(("ch", "gh")) else parola


def _radici(testo) -> tuple:
    return tuple(_radice(w) for w in _norm(testo).split())


def _dentro(pezzo: tuple, tutto: tuple) -> bool:
    n = len(pezzo)
    return n > 0 and any(tutto[i:i + n] == pezzo for i in range(len(tutto) - n + 1))


def _calcola(espressione) -> float | None:
    """Il valore di un conto con soli numeri e + - * / ( ) (il «calcolo» di un esempio,
    14/10 sera: il modello sbaglia più spesso il conto a mente che la formula), o None. Niente
    eval: l'albero si visita a mano."""
    import ast
    import operator
    t = str(espressione or "").strip().replace("×", "*").replace("÷", "/")
    if not t or len(t) > 160 or not re.fullmatch(r"[\d\s.+\-*/()eE]+", t):
        return None
    op2 = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv}

    def val(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) \
                and not isinstance(n.value, bool):
            return float(n.value)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = val(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp) and type(n.op) in op2:
            return op2[type(n.op)](val(n.left), val(n.right))
        raise ValueError("non è un conto")
    try:
        v = val(ast.parse(t, mode="eval").body)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, RecursionError):
        return None
    return v if math.isfinite(v) else None


def _togli(contiene: str, frasi, parole) -> str:
    """`contiene` senza le frasi (radici dei valori nominati) e senza le parole (radici dei
    dati dell'esempio): ripetere nella frase i valori che la persona ha detto è uno stile, non
    un requisito; il numero controlla già la conversione."""
    ws = _norm(contiene).split()
    rs = [_radice(w) for w in ws]
    tieni = [True] * len(ws)
    for f in frasi:
        n = len(f)
        for i in range(len(rs) - n + 1):
            if n and tuple(rs[i:i + n]) == f:
                tieni[i:i + n] = [False] * n
    tieni = [t and rs[i] not in parole for i, t in enumerate(tieni)]
    if all(tieni):
        return contiene
    return " ".join(w for w, t in zip(ws, tieni) if t)


def _riconosciuti(out: dict) -> list[dict]:
    """Per ogni valore nominato che nessun esempio usa: i dati di un esempio (che non dice
    «trovato»: false) con quel valore al posto del suo. Un valore che un esempio dà per
    sconosciuto non si controlla (lo decide l'esempio)."""
    controlli = []
    for i in out["input"]:
        nome = i["nome"]
        usati = {_norm(e["dati"].get(nome)) for e in out["esempi"] if nome in e["dati"]}
        base = [e for e in out["esempi"] if nome in e["dati"] and e["trovato"] is not False]
        base.sort(key=lambda e: e["numero"] is None)        # prima chi controlla il numero
        if not base:
            continue
        for v in i.get("valori") or ():
            if _norm(v) in usati:
                continue
            b = base[0]
            controlli.append({"requisito": b["requisito"], "input": nome, "valore": v,
                              "dati": {**b["dati"], nome: v},
                              "numero": b["numero"] is not None})
            if len(controlli) >= MAX_RICONOSCIUTI:
                return controlli
    return controlli


def _file_programma(p: dict, linguaggi) -> tuple[dict, str]:
    """({"file", "linguaggio"}, "") dell'interfaccia dichiarata, o ({}, perché niente esempi).
    Solo un programma a riga di comando in un linguaggio che qui ha i suoi test (Python;
    JavaScript con Node acceso, 17/10 #54): il C# non ha esegui_test, un programma su file
    della persona ha un'interfaccia che gli esempi non sanno dire."""
    if not isinstance(p, dict):
        return {}, "interfaccia non dichiarata"
    lg = str(p.get("linguaggio") or "").strip().lower()
    if p.get("interfaccia") != "riga_di_comando":
        return {}, ("lavora su file della persona" if p.get("interfaccia") == "file"
                    else "non è un programma a riga di comando")
    if lg not in _SUFFISSI:
        return {}, f"linguaggio senza esempi ({lg or '?'})"
    if lg not in set(linguaggi or ("python",)):
        return {}, f"qui il {lg} non si esegue"
    f = str(p.get("file") or "").strip().lower()
    stem = f[:-len(_SUFFISSI[lg])] if f.endswith(_SUFFISSI[lg]) else ""
    if (not _NOME.match(stem) or stem.startswith("test") or stem.endswith(("_test", ".test"))
            or stem in ("accettazione", "estensione", "calliope_estensione")
            or (lg == "python" and stem in __import__("sys").stdlib_module_names)):
        return {}, f"nome del file non valido ({f or '?'})"
    return {"file": f, "linguaggio": lg}, ""


def _parole(testo) -> list[str]:
    """Le parole di lettere di un testo (senza accenti, almeno tre lettere: non «e», «di»),
    per i valori fuori dalla richiesta."""
    return [w for w in _norm(testo).split() if w.isalpha() and len(w) >= 3]


def _numeri_detti(testo) -> list[float]:
    """I numeri di un testo, letti all'italiana e all'inglese (come fa il test)."""
    out = []
    for s in re.findall(r"-?\d+(?:[.,]\d+)*", str(testo or "")):
        for c in {s.replace(",", "."), s.replace(".", "").replace(",", "."), s.replace(",", "")}:
            try:
                out.append(float(c))
            except ValueError:
                pass
    return out


def _esempi_programma(d: dict, n_requisiti: int, testo: str) -> tuple[list[dict], dict, int]:
    """Gli esempi di un programma a riga di comando, validati come quelli delle estensioni:
    argomenti o stdin (sempre: senza argomenti il programma usa valori d'esempio suoi, che la
    richiesta non dice), un controllo che lo scheletro non passa (numero, parola, codice
    d'uscita diverso da 0), il «calcolo» rifatto dal codice; un esempio con una parola che la
    richiesta non dice vale solo se aspetta un errore (codice d'uscita diverso da 0). Il terzo
    valore: quanti degli esempi tenuti hanno un «calcolo» che il codice ha rifatto (19/10, #9:
    la misura del banco)."""
    from ..requisiti import pulito
    out, chiavi, con_calcolo = [], set(), 0
    tolti = {"fuori": 0, "numero": 0, "contiene": 0, "dati": 0}
    detto = _radici(testo)
    for e in d.get("esempi") or ():
        if not isinstance(e, dict):
            continue
        args = e.get("argomenti") if isinstance(e.get("argomenti"), list) else []
        if len(args) > MAX_ARGOMENTI or not all(_primitivo(a) and a is not None
                                                and not isinstance(a, bool) for a in args):
            continue
        args = [str(a) for a in args]
        stdin = e.get("stdin") if isinstance(e.get("stdin"), str) else ""
        if any(len(a) > 200 or "\n" in a or "\x00" in a for a in args) or len(stdin) > 2000 \
                or "\x00" in stdin:
            continue
        if not args and not stdin.strip():
            continue
        cod = e.get("codice_uscita")
        cod = cod if isinstance(cod, int) and not isinstance(cod, bool) and 0 <= cod <= 255 \
            else None
        errore = cod is not None and cod != 0
        if not errore and testo and any(
                not _dentro((_radice(w),), detto) for v in [*args, stdin] for w in _parole(v)):
            tolti["fuori"] += 1
            continue
        numero = _numero(e.get("numero"))
        tol = _numero(e.get("tolleranza"))
        calcolo = _calcola(e.get("calcolo"))
        if calcolo is not None:
            if numero is None:
                numero = calcolo
            elif abs(numero - calcolo) > max(abs(tol or 0), 0.01, abs(calcolo) * 0.002):
                tolti["numero"] += 1
                continue
        contiene = pulito(e.get("contiene"), 60)
        if re.search(r"\d", contiene):
            contiene = ""
        if contiene and numero is not None:
            parole = {_radice(w) for v in args for w in _parole(v)}
            nuovo = _togli(contiene, [], parole)
            if nuovo != contiene:
                tolti["contiene"] += 1
                contiene = nuovo
        if numero is None and not contiene and not errore:
            continue
        # Il risultato uguale a un dato (il massimo di 3 e 9, la media di 7, 8 e 6): il test
        # toglie dall'uscita i numeri che ripetono i dati (lo scheletro che li stampa non deve
        # passare), quindi un programma giusto che stampa «9» non passerebbe; e senza toglierli
        # passerebbe lo scheletro. L'esempio non distingue: si toglie il numero
        if numero is not None and any(
                abs(x - numero) <= max(abs(tol or 0), 0.01, abs(numero) * 0.002)
                for x in _numeri_detti(" ".join([*args, stdin]))):
            tolti["dati"] += 1
            numero = None
            if not contiene and not errore:
                continue
        chiave = json.dumps([args, stdin], ensure_ascii=False)
        if chiave in chiavi:
            continue
        chiavi.add(chiave)
        r = e.get("requisito")
        out.append({"requisito": r if isinstance(r, int) and not isinstance(r, bool)
                    and (n_requisiti <= 0 or 1 <= r <= n_requisiti) else 0,
                    "argomenti": args, "stdin": stdin, "numero": numero,
                    "tolleranza": abs(tol) if tol is not None else None,
                    "contiene": contiene, "codice_uscita": cod})
        # Solo se il numero resta: tolto perché uguale a un dato, il calcolo non controlla più
        # niente (revisione della PR #181)
        con_calcolo += calcolo is not None and numero is not None
        if len(out) >= MAX_ESEMPI:
            break
    return out, tolti, con_calcolo


def interpreta(dati, n_requisiti: int = 0, estensione: bool = True,
               gioco: bool = False, testo: str = "", programma: bool = False,
               linguaggi=("python",)) -> dict:
    """L'analisi validata dal JSON del modello: forme chiuse, testi puliti, tetti. Un esempio
    senza niente da controllare (né numero, né parola, né «trovato»: false) si scarta: non
    fallirebbe sullo scheletro. `testo`: la richiesta (requisiti, specifica, parole della
    persona), per tenere solo i valori nominati che ci sono davvero (14/10)."""
    from ..requisiti import _ORDINE, pulito
    d = dati if isinstance(dati, dict) else {}

    def numeri(xs):
        return sorted({int(x) for x in xs or () if isinstance(x, int) and not isinstance(x, bool)
                       and (n_requisiti <= 0 or 1 <= x <= n_requisiti)})
    contr = []
    for c in d.get("contraddizioni") or ():
        if not isinstance(c, dict):
            continue
        dom = pulito(c.get("domanda"), 200)
        if not dom or _ORDINE.search(dom):
            continue
        contr.append({"requisiti": numeri(c.get("requisiti")),
                      "domanda": dom[:1].upper() + dom[1:].rstrip("?.!") + "?"})
        if len(contr) >= MAX_DOMANDE:
            break
    # Le scelte vanno solo all'agente (non a voce): basta ripulirle
    scelte = [s for s in (pulito(x, 160) for x in (d.get("scelte") or ())
                          if isinstance(x, str)) if s][:MAX_SCELTE]
    out = {"contraddizioni": contr, "scelte": scelte,
           "al_collaudo": numeri(d.get("al_collaudo")), "input": [], "campo_numero": "",
           "esempi": [], "riconosciuti": []}
    if not estensione and gioco:
        comandi = _comandi_gioco(d)
        out["esempi"] = _esempi_gioco(d, comandi, n_requisiti)
        usati = {c for e in out["esempi"] for c, _ in e["mosse"]} | {
            x[0] for e in out["esempi"] for k in ("attivi", "non_attivi")
            for x in e["atteso"].get(k, [])}
        out["comandi"] = {k: v for k, v in comandi.items() if k in usati}
        return out
    if not estensione and programma:
        # 17/10 (#10): un programma a riga di comando con l'interfaccia dichiarata
        prog, perche = _file_programma(d.get("programma"), linguaggi)
        out["programma"], out["senza_esempi"] = prog, perche
        if prog:
            out["esempi"], out["tolti"], out["con_calcolo"] = _esempi_programma(
                d, n_requisiti, testo)
            if not out["esempi"]:
                out["programma"], out["senza_esempi"] = {}, "nessun esempio valido"
            elif not any(e["codice_uscita"] == 0 and (e["numero"] is not None or e["contiene"])
                         or e["codice_uscita"] is None and e["numero"] is not None
                         for e in out["esempi"]):
                # Revisione della PR #141: con i soli esempi d'errore (il massimo, dove i numeri
                # uguali a un dato si tolgono) un programma con sys.exit(1) o con un raise
                # passerebbe tutto, e al tetto sarebbe «fatto». Serve un risultato controllato
                # su una corsa che finisce bene: un numero (che il test legge solo dallo stdout,
                # con la corsa finita bene), o una parola con il codice 0. Una parola con il
                # codice che non conta no: «print('Il massimo è'); raise …» la stampa (seconda
                # revisione)
                out["programma"], out["esempi"] = {}, []
                out["senza_esempi"] = "nessun esempio che controlla un risultato"
        return out
    if not estensione:
        return out
    visti = set()
    for i in d.get("input") or ():
        if isinstance(i, dict) and isinstance(i.get("nome"), str):
            nome = i["nome"].strip().lower()
            if _NOME.match(nome) and nome not in visti and i.get("tipo") in TIPI:
                visti.add(nome)
                valori = _valori(i, testo)
                out["input"].append({"nome": nome, "tipo": i["tipo"],
                                     **({"valori": valori} if valori else {})})
    out["input"] = out["input"][:MAX_INPUT]
    campo = str(d.get("campo_numero") or "").strip().lower()
    out["campo_numero"] = campo if _NOME.match(campo) else ""
    chiavi = set()
    # Gli esempi contro la richiesta (14/10 sera, banco: rieseguiti sull'estensione di
    # riferimento, 4 convertitori su 5 avevano un esempio che una soluzione giusta non passa).
    # Per un input con dei valori nominati, un valore che la richiesta non dice (né tra i
    # valori né nel testo, al singolare o al plurale: «centimetri», «Km») va bene solo nel caso
    # del dato sconosciuto. Le frasi dei valori nominati, per togliere da «contiene»
    nominati = {i["nome"]: {_radici(v) for v in i["valori"]} for i in out["input"]
                if i.get("valori")}
    frasi = sorted({f for fs in nominati.values() for f in fs if f}, key=len, reverse=True)
    detto = _radici(testo)
    tolti = {"fuori": 0, "numero": 0, "contiene": 0}
    # Gli esempi tenuti con un «calcolo» rifatto dal codice (19/10, #9: si vedeva solo quando
    # non tornava, nei «tolti»)
    con_calcolo = 0
    for e in d.get("esempi") or ():
        if not isinstance(e, dict) or not isinstance(e.get("dati"), dict):
            continue
        dati_e = {}
        for k, v in e["dati"].items():
            if isinstance(k, str) and _NOME.match(k.strip().lower()) and _primitivo(v):
                dati_e[k.strip().lower()] = v
        if len(dati_e) != len(e["dati"]) or len(dati_e) > MAX_INPUT:
            continue                       # un input con un nome o un valore strano: fuori
        numero = _numero(e.get("numero"))
        tol = _numero(e.get("tolleranza"))
        contiene = pulito(e.get("contiene"), 60)
        if re.search(r"\d", contiene):
            contiene = ""                  # i numeri si controllano con «numero», non nel testo
        trovato = e.get("trovato") if isinstance(e.get("trovato"), bool) else None
        if trovato is not False and any(
                isinstance(v, str) and k in nominati and _radici(v) not in nominati[k]
                and not _dentro(_radici(v), detto) for k, v in dati_e.items()):
            tolti["fuori"] += 1
            continue
        # Il conto rifatto dal codice: se non torna con il numero l'esempio non si usa, come
        # chiede il prompt quando non si è sicuri (nel banco 1 unità astronomica = 80 776,4
        # miglia nautiche: mille volte meno)
        calcolo = _calcola(e.get("calcolo"))
        if calcolo is not None and trovato is not False:
            if numero is None:
                numero = calcolo
            elif abs(numero - calcolo) > max(abs(tol or 0), 0.01, abs(calcolo) * 0.002):
                tolti["numero"] += 1
                continue
        if trovato is False and numero is not None:
            numero = None                  # un dato sconosciuto non ha un risultato
            tolti["numero"] += 1
        if contiene and (numero is not None or trovato is False):
            # Con un altro controllo (il numero, «trovato»: false) le parole che ripetono i
            # dati dell'esempio e i valori nominati non servono; da sole («Bologna») restano
            parole = {_radice(w) for v in dati_e.values() if isinstance(v, str)
                      for w in _norm(v).split()}
            nuovo = _togli(contiene, frasi, parole)
            if nuovo != contiene:
                tolti["contiene"] += 1
                contiene = nuovo
        if numero is None and not contiene and trovato is not False:
            continue
        chiave = json.dumps(dati_e, sort_keys=True, ensure_ascii=False)
        if chiave in chiavi:
            continue
        chiavi.add(chiave)
        r = e.get("requisito")
        out["esempi"].append({
            "requisito": r if isinstance(r, int) and not isinstance(r, bool)
            and (n_requisiti <= 0 or 1 <= r <= n_requisiti) else 0,
            "dati": dati_e, "numero": numero, "tolleranza": abs(tol) if tol is not None else None,
            "contiene": contiene, "trovato": trovato})
        con_calcolo += calcolo is not None and trovato is not False
        if len(out["esempi"]) >= MAX_ESEMPI:
            break
    if any(e["numero"] is not None for e in out["esempi"]) and not out["campo_numero"]:
        out["campo_numero"] = "risultato"
    out["riconosciuti"] = _riconosciuti(out)
    out["tolti"] = tolti
    out["con_calcolo"] = con_calcolo
    return out


TESTA = '''"""Esempi di accettazione: IN SOLA LETTURA. Li ha scritti dai requisiti un'altra passata,
prima del codice (calliope/agenti/accettazione.py); alla consegna si eseguono con gli altri test.
Se uno ti sembra sbagliato non cambiarlo: dillo nel riassunto della consegna."""
import json
import unicodedata
import unittest

from calliope_estensione import CalliopeFinta
from estensione import esegui

'''

CORPO = '''

def _norm(testo):
    t = unicodedata.normalize("NFD", str(testo or "").lower())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


def _prova(self, caso):
    dati = caso["dati"]
    detto = f"R{caso['requisito']}, con i dati {json.dumps(dati, ensure_ascii=False)}"
    out = esegui(dict(dati), CalliopeFinta())
    self.assertIsInstance(out, dict, f"{detto}: esegui deve restituire un dict")
    if caso.get("numero") is not None:
        valore = out.get(CAMPO)
        self.assertTrue(isinstance(valore, (int, float)) and not isinstance(valore, bool),
                        f"{detto}: manca il numero nel campo «{CAMPO}» (uscito {valore!r})")
        atteso = caso["numero"]
        tol = max(caso.get("tolleranza") or 0, 0.01, abs(atteso) * 0.002)
        self.assertLessEqual(abs(valore - atteso), tol,
                             f"{detto}: atteso {atteso:g} (± {tol:g}), uscito {valore:g}")
    if caso.get("contiene"):
        # Le parole anche non vicine («chilometri metri» in «1 chilometro sono 1000 metri»)
        frase = _norm(out.get("da_dire"))
        if _norm(caso["contiene"]) not in frase:
            for parola in _norm(caso["contiene"]).split():
                self.assertIn(parola, frase,
                              f"{detto}: la frase deve contenere «{caso['contiene']}»")
    if caso.get("trovato") is False:
        self.assertIs(out.get("trovato"), False, f"{detto}: deve dire «trovato»: false")
    elif caso.get("trovato") is True:
        self.assertIsNot(out.get("trovato"), False, f"{detto}: qui il dato c'è")


def _riconosce(self, caso):
    dati = caso["dati"]
    detto = (f"R{caso['requisito']}: la richiesta nomina «{caso['valore']}» per "
             f"«{caso['input']}»; con i dati {json.dumps(dati, ensure_ascii=False)}")
    out = esegui(dict(dati), CalliopeFinta())
    self.assertIsInstance(out, dict, f"{detto}: esegui deve restituire un dict")
    self.assertTrue(str(out.get("da_dire") or "").strip(), f"{detto}: manca la frase da_dire")
    self.assertIsNot(out.get("trovato"), False,
                     f"{detto}: l'estensione deve riconoscerlo (uscito «trovato»: false)")
    if caso.get("numero"):
        valore = out.get(CAMPO)
        self.assertTrue(isinstance(valore, (int, float)) and not isinstance(valore, bool),
                        f"{detto}: manca il numero nel campo «{CAMPO}» (uscito {valore!r})")


class Accettazione(unittest.TestCase):
    pass


for _i, _caso in enumerate(ESEMPI, 1):
    def _t(self, _caso=_caso):
        _prova(self, _caso)
    setattr(Accettazione, f"test_r{_caso['requisito']}_{_i}", _t)

for _i, _caso in enumerate(RICONOSCIUTI, len(ESEMPI) + 1):
    def _t(self, _caso=_caso):
        _riconosce(self, _caso)
    setattr(Accettazione, f"test_r{_caso['requisito']}_{_i}", _t)
'''


def test_python(an: dict) -> str:
    """Il file test_accettazione.py dagli esempi (scritto dal codice, non dal modello)."""
    esempi = json.dumps(an.get("esempi") or [], ensure_ascii=False, indent=1)
    riconosciuti = json.dumps(an.get("riconosciuti") or [], ensure_ascii=False, indent=1)
    return (TESTA + f"ESEMPI = json.loads({esempi!r})\n"
            + f"RICONOSCIUTI = json.loads({riconosciuti!r})\n"
            + f"CAMPO = {str(an.get('campo_numero') or 'risultato')!r}\n" + CORPO)


TESTA_JS = """// Esempi di accettazione: IN SOLA LETTURA. Li ha scritti dai requisiti un'altra passata,
// prima del codice (calliope/agenti/accettazione.py); alla consegna si eseguono con gli altri
// test. Giocano la partita vera con la macchina di Calliope (apriGioco). Se uno ti sembra
// sbagliato non cambiarlo: dillo nel riassunto della consegna.
"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
"""

CORPO_JS = r"""
const norm = (t) => String(t || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim();
const nome = (c, v) => (v === null ? c : `${c} ${v}`);
const vale = (s, c, v) => c in s.comandi && (s.comandi[c] === true ? v === null : s.comandi[c].includes(v));

async function partita(e) {
  const g = await apriGioco({ seme: 1 });
  if (g.stato().comandi.giocatori) await g.comando("giocatori", e.giocatori);
  else await g.comando("inizia");
  for (const [c, v] of e.mosse) {
    // L'esito di una mossa va avanti da solo: il test non aspetta i secondi
    while (c !== "avanti" && g.stato().fase === "esito") await g.comando("avanti");
    await (v === null ? g.comando(c) : g.comando(c, v));
  }
  return g;
}

ESEMPI.forEach((e, i) => {
  const mosse = e.mosse.map(([c, v]) => nome(c, v)).join(", ");
  test(`R${e.requisito} esempio ${i + 1}: ${e.giocatori} giocatori, ${mosse}`, async () => {
    const detto = `R${e.requisito}, con ${e.giocatori} giocatori e le mosse ${mosse}`;
    const g = await partita(e);
    const a = e.atteso;
    if (a.testo) {
      assert.ok(norm(g.testo()).includes(norm(a.testo)),
        `${detto}: dopo l'ultima mossa sullo schermo deve esserci «${a.testo}»; si legge «${g.testo().slice(0, 200)}»`);
    }
    let s = g.stato();
    if (a.fase !== "esito") {
      for (let k = 0; k < 3 && s.fase === "esito"; k++) { await g.comando("avanti"); s = g.stato(); }
    }
    if (a.fase) assert.strictEqual(s.fase, a.fase, `${detto}: la fase deve essere «${a.fase}», è «${s.fase}»`);
    if (a.tocca) {
      const chi = (s.giocatori[a.tocca - 1] || {}).nome;
      assert.strictEqual(s.tocca, chi, `${detto}: deve toccare a ${chi}, tocca a ${s.tocca}`);
    }
    if (a.punti) {
      assert.deepStrictEqual(s.giocatori.map((x) => x.punti), a.punti,
        `${detto}: i punti devono essere ${a.punti.join(", ")}`);
    }
    for (const [c, v] of a.attivi || []) {
      assert.ok(vale(s, c, v), `${detto}: «${nome(c, v)}» deve valere ancora (adesso: ${JSON.stringify(s.comandi)})`);
    }
    for (const [c, v] of a.non_attivi || []) {
      assert.ok(!vale(s, c, v), `${detto}: «${nome(c, v)}» non deve valere più (adesso: ${JSON.stringify(s.comandi)})`);
    }
  });
});
"""


def test_js(an: dict) -> str:
    """Il file accettazione.test.js dagli esempi di un gioco (scritto dal codice)."""
    esempi = json.dumps(an.get("esempi") or [], ensure_ascii=False, indent=1)
    return TESTA_JS + f"const ESEMPI = {esempi};\n" + CORPO_JS


# I programmi a riga di comando (17/10, #10). In Python il programma gira nello stesso processo
# del test (runpy, con argv, stdin e uscita sostituiti): nella sandbox l'audit hook di _avvio.py
# non lascia avviare processi, e così il test vale anche con il motore «processo»
TESTA_PROGRAMMA = '''"""Esempi di accettazione: IN SOLA LETTURA. Li ha scritti dai requisiti un'altra passata,
prima del codice (calliope/agenti/accettazione.py); alla consegna si eseguono con gli altri test.
Eseguono il programma con gli argomenti e lo stdin di ogni esempio e leggono quello che stampa.
Se uno ti sembra sbagliato non cambiarlo: dillo nel riassunto della consegna."""
import contextlib
import io
import json
import re
import runpy
import sys
import unicodedata
import unittest

'''

CORPO_PROGRAMMA = '''

def _norm(testo):
    t = unicodedata.normalize("NFD", str(testo or "").lower())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


def _numeri(testo, dati=""):
    """I numeri stampati, letti all'italiana e all'inglese (3,5 / 3.5 / 1.234,5 / 1,234.5),
    senza quelli che ripetono i dati (una volta per dato): ripetere gli argomenti non è un
    risultato, e lo scheletro che li stampa non deve passare."""
    import collections
    trova = re.compile(r"-?\\d+(?:[.,]\\d+)*")
    resto = collections.Counter(trova.findall(testo))
    resto.subtract(collections.Counter(trova.findall(dati)))
    out = []
    for s, n in resto.items():
        if n <= 0:
            continue
        for c in {s.replace(",", "."), s.replace(".", "").replace(",", "."), s.replace(",", "")}:
            try:
                out.append(float(c))
            except ValueError:
                pass
    return out


def _esegui(argomenti, stdin):
    """(stdout, stderr, codice d'uscita, errore) del programma, come se lo si lanciasse. Stdin,
    stdout e stderr sono file di testo veri sopra dei byte (reconfigure, .buffer); un'eccezione,
    come in Python, finisce nello stderr con il suo tipo e il messaggio e il codice è 1. Il
    numero si legge solo dallo stdout; lo stderr serve alle parole di «contiene»."""
    def scrivibile():
        return io.TextIOWrapper(io.BytesIO(), encoding="utf-8", errors="replace",
                                write_through=True)
    out, err = scrivibile(), scrivibile()
    entrata = io.TextIOWrapper(io.BytesIO(str(stdin or "").encode("utf-8")), encoding="utf-8")
    vecchi = sys.argv, sys.stdin
    sys.argv, sys.stdin = [PROGRAMMA, *argomenti], entrata
    codice, errore = 0, ""
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            runpy.run_path(PROGRAMMA, run_name="__main__")
    except SystemExit as e:
        if isinstance(e.code, int):
            codice = e.code
        elif e.code is not None:
            codice = 1
            err.write(str(e.code) + "\\n")
    except Exception as e:  # noqa: BLE001 — come Python: il programma si ferma con 1
        codice, errore = 1, f"{type(e).__name__}: {e}"
        err.write(errore + "\\n")
    finally:
        sys.argv, sys.stdin = vecchi

    def testo(f):
        try:
            f.flush()
        except (ValueError, OSError):
            pass
        return f.buffer.getvalue().decode("utf-8", "replace")
    return testo(out), testo(err), codice, errore


def _prova(self, caso):
    detto = (f"R{caso['requisito']}: {PROGRAMMA} con gli argomenti "
             f"{json.dumps(caso['argomenti'], ensure_ascii=False)}"
             + (f" e lo stdin {json.dumps(caso['stdin'], ensure_ascii=False)}" if caso["stdin"]
                else ""))
    uscita, errori, codice, errore = _esegui(caso["argomenti"], caso["stdin"])
    breve = (uscita + errori).strip()[-300:]
    atteso = caso.get("codice_uscita")
    if atteso is not None and atteso != 0:
        self.assertNotEqual(codice, 0, f"{detto}: deve fermarsi con un errore (codice d'uscita "
                            f"diverso da 0), è finito bene; ha stampato «{breve}»")
    elif atteso == 0 or caso.get("numero") is not None:
        # Un risultato si controlla su una corsa che finisce bene: con il codice 0, e anche con
        # quello che non conta (null) se l'esempio controlla un numero. Senza numero e con null
        # decidono le parole, che leggono anche lo stderr (come in JavaScript)
        self.assertFalse(errore, f"{detto}: il programma si è fermato con {errore}")
        self.assertEqual(codice, 0, f"{detto}: deve finire bene, codice d'uscita {codice}; "
                         f"ha stampato «{breve}»")
    if caso.get("numero") is not None:
        n = caso["numero"]
        tol = max(caso.get("tolleranza") or 0, 0.01, abs(n) * 0.002)
        dati = " ".join([*caso["argomenti"], caso["stdin"] or ""])
        # Solo dallo stdout: i messaggi d'errore hanno numeri che non sono risultati
        self.assertTrue(any(abs(x - n) <= tol for x in _numeri(uscita, dati)),
                        f"{detto}: deve stampare {n:g} (± {tol:g}); ha stampato «{breve}»")
    if caso.get("contiene"):
        frase = _norm(uscita + "\\n" + errori)
        if _norm(caso["contiene"]) not in frase:
            for parola in _norm(caso["contiene"]).split():
                self.assertIn(parola, frase, f"{detto}: l'uscita deve contenere "
                              f"«{caso['contiene']}»; ha stampato «{breve}»")


class Accettazione(unittest.TestCase):
    def test_programma_c_e(self):
        import os
        self.assertTrue(os.path.isfile(PROGRAMMA), f"manca il programma {PROGRAMMA}: gli esempi "
                        "lo eseguono con questo nome")


for _i, _caso in enumerate(ESEMPI, 1):
    def _t(self, _caso=_caso):
        _prova(self, _caso)
    setattr(Accettazione, f"test_r{_caso['requisito']}_{_i}", _t)
'''


def test_programma(an: dict) -> str:
    """Il file test_accettazione.py di un programma Python a riga di comando (17/10, #10)."""
    esempi = json.dumps(an.get("esempi") or [], ensure_ascii=False, indent=1)
    return (TESTA_PROGRAMMA + f"PROGRAMMA = {str((an.get('programma') or {}).get('file'))!r}\n"
            + f"ESEMPI = json.loads({esempi!r})\n" + CORPO_PROGRAMMA)


# In JavaScript il programma si lancia con Node in un processo figlio (spawnSync), con lo stesso
# modello dei permessi di esegui_js: i test JavaScript girano senza --permission
CORPO_PROGRAMMA_JS = r"""
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const norm = (t) => String(t || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim();
// I numeri stampati, senza quelli che ripetono i dati (una volta per dato)
function numeri(t, dati) {
  const out = [];
  const resto = String(t).match(/-?\d+(?:[.,]\d+)*/g) || [];
  for (const d of String(dati).match(/-?\d+(?:[.,]\d+)*/g) || []) {
    const k = resto.indexOf(d);
    if (k >= 0) resto.splice(k, 1);
  }
  for (const s of resto) {
    for (const c of new Set([s.replace(/,/g, "."), s.replace(/\./g, "").replace(",", "."), s.replace(/,/g, "")])) {
      const n = Number(c);
      if (Number.isFinite(n)) out.push(n);
    }
  }
  return out;
}
function esegui(e) {
  const qui = process.cwd();
  const r = spawnSync(process.execPath, ["--permission", `--allow-fs-read=${qui}`,
    `--allow-fs-write=${qui}`, PROGRAMMA, ...e.argomenti],
    { input: e.stdin || "", encoding: "utf8", timeout: 10000 });
  // Tempo scaduto o processo che non parte (revisione della PR #141): non è «si ferma con un
  // errore», l'esempio è rosso
  const guasto = r.error ? `non è partito o non ha finito in 10 s (${r.error.code || r.error.message})`
    : r.signal ? `non ha finito in 10 s (fermato con ${r.signal})` : "";
  // Il numero solo dallo stdout (seconda revisione della PR #141: lo stack di Node ha i numeri di
  // riga e «Node.js v24»); lo stderr serve alle parole di «contiene»
  return { uscita: r.stdout || "", tutto: (r.stdout || "") + (r.stderr || ""),
           codice: r.status === null ? 1 : r.status, guasto };
}
test(`R0 esempio 0: c'è il programma ${PROGRAMMA}`, () => {
  assert.ok(fs.existsSync(PROGRAMMA), `manca il programma ${PROGRAMMA}: gli esempi lo eseguono con questo nome`);
});
ESEMPI.forEach((e, i) => {
  const detto = `R${e.requisito}: ${PROGRAMMA} con gli argomenti ${JSON.stringify(e.argomenti)}` +
    (e.stdin ? ` e lo stdin ${JSON.stringify(e.stdin)}` : "");
  test(`R${e.requisito} esempio ${i + 1}: argomenti ${JSON.stringify(e.argomenti)}`, () => {
    const { uscita, tutto, codice, guasto } = esegui(e);
    const breve = tutto.trim().slice(-300);
    assert.ok(!guasto, `${detto}: il programma ${guasto}; ha stampato «${breve}»`);
    if (e.codice_uscita !== null && e.codice_uscita !== 0) {
      assert.notStrictEqual(codice, 0, `${detto}: deve fermarsi con un errore (codice d'uscita diverso da 0), è finito bene; ha stampato «${breve}»`);
    } else if (e.codice_uscita === 0 || e.numero !== null) {
      // Un risultato si controlla su una corsa che finisce bene (con il numero anche a codice null)
      assert.strictEqual(codice, 0, `${detto}: deve finire bene, codice d'uscita ${codice}; ha stampato «${breve}»`);
    }
    if (e.numero !== null) {
      const tol = Math.max(e.tolleranza || 0, 0.01, Math.abs(e.numero) * 0.002);
      assert.ok(numeri(uscita, [...e.argomenti, e.stdin || ""].join(" ")).some((x) => Math.abs(x - e.numero) <= tol),
        `${detto}: deve stampare ${e.numero} (± ${tol}); ha stampato «${breve}»`);
    }
    if (e.contiene && !norm(tutto).includes(norm(e.contiene))) {
      for (const p of norm(e.contiene).split(" ")) {
        assert.ok(norm(tutto).includes(p), `${detto}: l'uscita deve contenere «${e.contiene}»; ha stampato «${breve}»`);
      }
    }
  });
});
"""


def test_programma_js(an: dict) -> str:
    """Il file accettazione.test.js di un programma JavaScript (17/10, #10 e #54)."""
    esempi = json.dumps(an.get("esempi") or [], ensure_ascii=False, indent=1)
    file = json.dumps(str((an.get("programma") or {}).get("file")))
    return (TESTA_JS.replace("Giocano la partita vera con la macchina di Calliope (apriGioco).",
                             "Eseguono il programma con argomenti e stdin di ogni esempio.")
            + f"const PROGRAMMA = {file};\nconst ESEMPI = {esempi};\n" + CORPO_PROGRAMMA_JS)


def file_programma(an: dict) -> tuple[str, str]:
    """(nome del file degli esempi, testo) di un programma con l'interfaccia dichiarata."""
    if (an.get("programma") or {}).get("linguaggio") == "javascript":
        return FILE_GIOCO, test_programma_js(an)
    return FILE, test_programma(an)


def controlla_nome(sandbox, stato: dict) -> str | None:
    """Il programma con il nome dichiarato dall'analisi (17/10, #10, come il manifesto delle
    estensioni): l'errore per l'agente, o None."""
    a = stato or {}
    f = a.get("programma") if a.get("stato") == "pronta" and a.get("file") else None
    if not f:
        return None
    try:
        if (sandbox.root / f).is_file():
            return None
    except Exception:  # noqa: BLE001
        return None
    return (f"il programma deve chiamarsi «{f}»: gli esempi di accettazione "
            f"({a.get('nome_file') or FILE}) lo eseguono con quel nome. Rinominalo (scrivi il file "
            f"con quel nome) e in consegna metti programma = «{f}».")


def comandi_detti(an: dict) -> str:
    """I comandi che la macchina deve avere, per l'agente: «porta (fase turno, da 1 a 6)»."""
    out = []
    for nome, d in (an.get("comandi") or {}).items():
        v = d.get("valori")
        if v is None:
            dom = ""
        elif all(isinstance(x, int) for x in v):
            dom = f", da {v[0]} a {v[-1]}"
        else:
            dom = ", valori " + ", ".join(map(str, v))
        out.append(f"«{nome}» (fase «{d['fase']}»{dom})")
    return ", ".join(out)


def esito_js(uscita: str) -> tuple[bool, list[int]]:
    """(passano tutti, requisiti rossi) dall'uscita di test_js.mjs per accettazione.test.js."""
    u = str(uscita or "")
    rossi = sorted({int(m) for m in re.findall(r"^FALLITO R(\d+) esempio", u, re.M)})
    verdi = re.findall(r"^ok R\d+ esempio", u, re.M)
    # I test dell'agente girano insieme (test_js.mjs li prende tutti): contano solo gli esempi
    errore = re.search(r"^errore di sintassi", u, re.M)
    return bool(verdi) and not rossi and not errore, rossi


def domanda(an: dict) -> str:
    """Le domande da fare prima di cominciare (al più due), in una frase da dire."""
    ds = [c["domanda"] for c in (an.get("contraddizioni") or [])][:MAX_DOMANDE]
    if not ds:
        return ""
    if len(ds) == 1:
        return "Prima di cominciare: " + ds[0][:1].lower() + ds[0][1:]
    return ("Prima di cominciare, due cose: " + ds[0][:1].lower() + ds[0][1:] + " E "
            + ds[1][:1].lower() + ds[1][1:])


def vincolo(an: dict, file: bool, gioco: bool = False) -> str:
    """Il testo per l'agente in coda ai vincoli."""
    parti = []
    if file and gioco:
        parti.append(
            f"Gli esempi di accettazione sono in {FILE_GIOCO}, IN SOLA LETTURA: li ha scritti dai "
            "requisiti un'altra passata, prima del codice, e alla consegna si eseguono con i tuoi "
            "test; giocano la partita vera con la macchina di Calliope. Il gioco deve farli "
            "passare tutti; non puoi cambiarli: se uno ti sembra sbagliato dillo nel riassunto "
            "della consegna. La macchina nel manifesto deve avere questi comandi, con questi "
            f"nomi, fasi e valori: {comandi_detti(an)}.")
    elif file and (an.get("programma") or {}).get("file"):
        # Un programma a riga di comando (17/10, #10): il nome e il modo di usarlo
        p = an["programma"]
        nome_file, _ = file_programma(an)
        stdin = any(e.get("stdin") for e in an.get("esempi") or [])
        parti.append(
            f"Gli esempi di accettazione sono in {nome_file}, IN SOLA LETTURA: li ha scritti dai "
            "requisiti un'altra passata, prima del codice, e alla consegna si eseguono con i tuoi "
            f"test. Eseguono il programma «{p['file']}» con gli argomenti"
            + (" (e lo stdin)" if stdin else "") + " di ogni "
            "esempio e leggono quello che stampa: il programma deve chiamarsi così (in consegna "
            f"programma = «{p['file']}»), leggere i valori dagli argomenti"
            + (" o, se un esempio li dà così, dallo stdin" if stdin else "")
            + ", stampare il risultato e farli passare tutti. Non puoi cambiarli: se uno ti "
              "sembra sbagliato dillo nel riassunto della consegna.")
    elif file:
        ins = ", ".join(f"{i['nome']} ({i['tipo']})" for i in an.get("input") or [])
        parti.append(
            f"Gli esempi di accettazione sono in {FILE}, IN SOLA LETTURA: li ha scritti dai "
            "requisiti un'altra passata, prima del codice, e alla consegna si eseguono con i tuoi "
            "test. Il codice deve farli passare tutti; non puoi cambiarli: se uno ti sembra "
            "sbagliato dillo nel riassunto della consegna."
            + (f" Input del manifesto, con questi nomi: {ins}." if ins else "")
            + (f" Il numero del risultato va nel campo «{an['campo_numero']}»."
               if an.get("campo_numero") else "")
            + "".join(f" Valori nominati dalla richiesta per «{i['nome']}», da riconoscere "
                      f"tutti: {', '.join(i['valori'])}." for i in an.get("input") or []
                      if i.get("valori"))
            # 14/10 sera, banco L8: l'elenco finiva nella descrizione dell'input (98
            # caratteri, il manifesto non passava e il lavoro restava al tetto)
            + (" Li riconosce il codice: nel manifesto la descrizione dell'input resta di poche "
               "parole, senza l'elenco." if any(i.get("valori") for i in an.get("input") or [])
               else ""))
    if an.get("scelte"):
        parti.append("Scelte già fatte dove la richiesta non dice: "
                     + "; ".join(an["scelte"]) + ".")
    return " ".join(parti)


def utente(cosa: str, compito: str, requisiti: list[dict], parole: str = "",
           risposta: tuple[str, str] | None = None) -> str:
    """Il messaggio della passata: requisiti numerati, specifica, parole della persona."""
    righe = [f"Cosa si sviluppa: {cosa}."]
    if requisiti:
        righe.append("Requisiti (numerati):")
        righe += [f"{i}. {r.get('testo')}" + (f" — {r['dettaglio']}" if r.get("dettaglio")
                                              else "") for i, r in enumerate(requisiti, 1)]
    spec = re.sub(r"\s+", " ", str(compito or "")).strip()[:2000]
    righe.append(f"Specifica: «{spec}»")
    if str(parole or "").strip():
        righe.append(f"Le parole della persona, per capire cosa intendeva: "
                     f"«{str(parole).strip()[:1200]}»")
    if risposta:
        righe.append(f"Alla domanda «{risposta[0]}» la persona ha risposto: «{risposta[1]}». "
                     "Tienine conto; contraddizioni: lista vuota.")
    return "\n".join(righe)


def analizza(svc, compito: str, requisiti: list[dict], parole: str = "",
             estensione: bool = True, gioco: bool = False,
             risposta: tuple[str, str] | None = None,
             tempo_s: float = 90.0, programma: bool = False, linguaggi=("python",),
             ragionamento: int = 0, uso: dict | None = None) -> tuple[dict | None, str]:
    """(analisi, "modello") o (None, esito): la passata del progettista dei test. Mai
    un'eccezione. `programma` (17/10, #10): un programma per cui dichiarare l'interfaccia e
    scrivere gli esempi (non un programma su file della persona: lì solo le contraddizioni);
    `linguaggi`: quelli dei programmi che qui si eseguono. `ragionamento`: i token di
    ragionamento della passata (0 = spento, come sempre; Config.agenti_accettazione_ragionamento);
    `uso`: riceve token e secondi della passata (il mini-banco del ragionamento)."""
    from ..requisiti import chiama
    cosa = ("un gioco sugli schermi di Calliope" if gioco else
            "un'estensione di Calliope (la funzione esegui(dati, calliope) -> dict con «da_dire»)"
            if estensione else "un programma")
    esempi_gioco = gioco and not estensione and bool(requisiti)
    programma = programma and not estensione and not gioco
    altri = [lg for lg in (linguaggi or ()) if lg in _SUFFISSI and lg != "python"]
    sistema = SISTEMA.format(cosa=cosa, estensione=SISTEMA_ESEMPI if estensione else
                             SISTEMA_GIOCO if esempi_gioco else
                             SISTEMA_PROGRAMMA.format(linguaggi=(
                                 " tra " + ", ".join(["python", *altri]) if altri else
                                 " (qui si eseguono solo programmi Python)"))
                             if programma else "")
    dati, esito = chiama(svc, sistema, utente(cosa, compito, requisiti, parole, risposta),
                         schema(estensione, esempi_gioco, programma), tempo_s, dalla_voce=False,
                         num_predict=2000, ragionamento=ragionamento, uso=uso)
    if dati is None:
        return None, esito
    testo = " ".join([str(compito or ""), str(parole or "")]
                     + [f"{r.get('testo') or ''} {r.get('dettaglio') or ''}" for r in requisiti])
    return interpreta(dati, len(requisiti), estensione, esempi_gioco, testo, programma,
                      linguaggi), esito


def rossi(uscita: str) -> list[int]:
    """I requisiti con un esempio rosso, dall'uscita di unittest («FAIL: test_r3_2 …») o di
    test_js.mjs per un gioco («FALLITO R3 esempio 2: …»)."""
    u = str(uscita or "")
    return sorted({int(m) for m in re.findall(r"(?:FAIL|ERROR): test_r(\d+)_\d+", u)}
                  | {int(m) for m in re.findall(r"^FALLITO R(\d+) esempio", u, re.M)})


def numeri_esempi(an: dict) -> list[int]:
    return sorted({e["requisito"] for e in (an.get("esempi") or [])
                   + (an.get("riconosciuti") or []) if e.get("requisito")})


def esegui(sb, stato: dict) -> dict | None:
    """Gli esempi di accettazione sui file di adesso (13/10 sera): {"passano", "esito",
    "rossi", "uscita"}; None se il lavoro non li ha (analisi non pronta o file non scritto).
    Per un gioco Node fa girare anche i test dell'agente: contano solo gli esempi. Lo usano la
    fine del lavoro (servizio._esito_accettazione) e la consegna al tetto
    (ciclo.Agente._consegna_al_tetto). Le eccezioni della sandbox passano a chi chiama."""
    a = stato or {}
    if a.get("stato") != "pronta" or not a.get("file"):
        return None
    nome_file = a.get("nome_file") or FILE
    r = sb.test(nome_file, fumo=False)
    passano = bool(r.get("passano"))
    if nome_file.endswith(".js"):
        passano, _ = esito_js(r.get("uscita"))
    return {"passano": passano, "esito": r.get("esito"), "rossi": rossi(r.get("uscita")),
            "uscita": str(r.get("uscita") or "")}
