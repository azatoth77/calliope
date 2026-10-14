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
- **contraddizioni** tra requisiti, o tra i requisiti e le parole della persona (il 12/10
  «giocatori» è diventato «porte»), con al più **due domande** brevi: il lavoro aspetta la
  risposta come una domanda a metà lavoro (`mancano_dati`). Solo in un lavoro nuovo (non una
  correzione né la modifica di una versione che c'è: lì la specifica viva tiene già i requisiti
  senza contrasti). Senza contraddizioni il lavoro parte senza chiedere: è il caso normale
  (HumanEvalComm: un agente che domanda sempre peggiora sui problemi già chiari);
- **scelte** fatte dove la richiesta non dice, scritte all'agente;
- **al collaudo**: i requisiti che si giudicano solo guardando o ascoltando (musica, aspetto,
  «adatto ai bambini»): la revisione li dice «da guardare tu», non fatti né mancanti.

Per i programmi niente esempi (un programma non ha un'interfaccia fissa): la stessa passata cerca
solo le contraddizioni, e solo nel primo lavoro di uno sviluppo.

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
0, senza ragionamento). Solo libreria standard.
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
esempi: da 3 a 8 esempi dato → risultato, almeno uno per ogni requisito che si controlla con un dato. Per ognuno: requisito (il numero), dati (gli input con valori veri, come li direbbe la persona), e cosa deve risultare:
- numero: il valore atteso nel campo numerico, calcolato con cura (se arrotondi metti la tolleranza); se non sei sicuro di un valore non usare quell'esempio;
- contiene: una o due parole che la frase da_dire deve contenere (un nome detto dalla persona, «non»); mai numeri, mai frasi intere;
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


def _nome_ok(x) -> bool:
    return isinstance(x, str) and bool(re.match(r"^[a-z][a-z0-9_]{0,13}$", x))


def schema(estensione: bool, gioco: bool = False) -> dict:
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
        if nome in ("inizia", "avanti", "ancora", "giocatori", "fine_partita") or nome in out \
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


def interpreta(dati, n_requisiti: int = 0, estensione: bool = True,
               gioco: bool = False, testo: str = "") -> dict:
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
        if len(out["esempi"]) >= MAX_ESEMPI:
            break
    if any(e["numero"] is not None for e in out["esempi"]) and not out["campo_numero"]:
        out["campo_numero"] = "risultato"
    out["riconosciuti"] = _riconosciuti(out)
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
        self.assertIn(_norm(caso["contiene"]), _norm(out.get("da_dire")),
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
                      if i.get("valori")))
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
             tempo_s: float = 90.0) -> tuple[dict | None, str]:
    """(analisi, "modello") o (None, esito): la passata del progettista dei test. Mai
    un'eccezione."""
    from ..requisiti import chiama
    cosa = ("un gioco sugli schermi di Calliope" if gioco else
            "un'estensione di Calliope (la funzione esegui(dati, calliope) -> dict con «da_dire»)"
            if estensione else "un programma")
    esempi_gioco = gioco and not estensione and bool(requisiti)
    sistema = SISTEMA.format(cosa=cosa, estensione=SISTEMA_ESEMPI if estensione else
                             SISTEMA_GIOCO if esempi_gioco else "")
    dati, esito = chiama(svc, sistema, utente(cosa, compito, requisiti, parole, risposta),
                         schema(estensione, esempi_gioco), tempo_s, dalla_voce=False,
                         num_predict=2000)
    if dati is None:
        return None, esito
    testo = " ".join([str(compito or ""), str(parole or "")]
                     + [f"{r.get('testo') or ''} {r.get('dettaglio') or ''}" for r in requisiti])
    return interpreta(dati, len(requisiti), estensione, esempi_gioco, testo), esito


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
