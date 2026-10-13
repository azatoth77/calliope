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
- **contraddizioni** tra requisiti, o tra i requisiti e le parole della persona (il 12/10
  «giocatori» è diventato «porte»), con al più **due domande** brevi: il lavoro aspetta la
  risposta come una domanda a metà lavoro (`mancano_dati`). Solo in un lavoro nuovo (non una
  correzione né la modifica di una versione che c'è: lì la specifica viva tiene già i requisiti
  senza contrasti). Senza contraddizioni il lavoro parte senza chiedere: è il caso normale
  (HumanEvalComm: un agente che domanda sempre peggiora sui problemi già chiari);
- **scelte** fatte dove la richiesta non dice, scritte all'agente;
- **al collaudo**: i requisiti che si giudicano solo guardando o ascoltando (musica, aspetto,
  «adatto ai bambini»): la revisione li dice «da guardare tu», non fatti né mancanti.

Per i giochi e i programmi niente esempi (il contratto del gioco arriva con la macchina a stati,
un programma non ha un'interfaccia fissa): la stessa passata cerca solo le contraddizioni, e solo
nel primo lavoro di uno sviluppo.

Il client e la passata sono quelli dei requisiti (`requisiti.chiama`: schema chiuso, temperatura
0, senza ragionamento). Solo libreria standard.
"""

from __future__ import annotations

import json
import math
import re

FILE = "test_accettazione.py"
MAX_ESEMPI = 8
MAX_DOMANDE = 2
MAX_SCELTE = 3
MAX_INPUT = 6
TIPI = ("number", "integer", "string", "boolean")
_NOME = re.compile(r"^[a-z][a-z0-9_]{0,30}$")

SISTEMA = """Sei il progettista dei test di Calliope, un'assistente vocale di casa. Un agente programmatore sta per scrivere {cosa}. Tu NON vedi il codice e non lo scrivi: dai requisiti e dalle parole della persona compili il JSON, prima che il codice esista.

contraddizioni: solo se due requisiti (o un requisito e le parole della persona) dicono cose che non possono valere insieme, oppure se manca un dato senza il quale il risultato cambia del tutto. Per ognuna i numeri dei requisiti e una domanda breve da dire a voce, meglio come esempio da confermare («Quindi con due giocatori le porte restano le stesse per tutti e due?»). Al più 2. Se è tutto chiaro la lista è vuota: è il caso normale, non inventare dubbi.
scelte: le cose che la richiesta non dice e che decideresti da solo, una frase breve ciascuna (al più 3).
al_collaudo: i numeri dei requisiti che si giudicano solo guardando o ascoltando (suoni, aspetto, «adatto ai bambini», «bello»): nessun test li prova.{estensione}"""

SISTEMA_ESEMPI = """
input: gli input dell'estensione (il dict «dati» che riceve esegui), con nome (minuscole e _) e tipo (number, integer, string, boolean). Se la specifica li nomina usa quei nomi, esattamente.
campo_numero: il nome del campo numerico del risultato, se l'estensione restituisce un numero (di solito «risultato»); altrimenti vuoto.
esempi: da 3 a 8 esempi dato → risultato, almeno uno per ogni requisito che si controlla con un dato. Per ognuno: requisito (il numero), dati (gli input con valori veri, come li direbbe la persona), e cosa deve risultare:
- numero: il valore atteso nel campo numerico, calcolato con cura (se arrotondi metti la tolleranza); se non sei sicuro di un valore non usare quell'esempio;
- contiene: una o due parole che la frase da_dire deve contenere (un nome detto dalla persona, «non»); mai numeri, mai frasi intere;
- trovato: false se il dato non esiste o non si capisce e l'estensione deve dire che non l'ha trovato; altrimenti null.
Ogni esempio controlla almeno una cosa (numero, contiene o trovato false). Se la richiesta nomina valori di più parole o con l'accento metti un esempio con uno di quelli; metti anche un caso con un dato sconosciuto."""


def schema(estensione: bool) -> dict:
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
                    "tipo": {"type": "string", "enum": list(TIPI)}},
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
    return {"type": "object", "properties": prop, "required": richiesti}


def _numero(v) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if math.isfinite(v) else None


def _primitivo(v) -> bool:
    return v is None or isinstance(v, (str, bool, int, float)) and not (
        isinstance(v, float) and not math.isfinite(v))


def interpreta(dati, n_requisiti: int = 0, estensione: bool = True) -> dict:
    """L'analisi validata dal JSON del modello: forme chiuse, testi puliti, tetti. Un esempio
    senza niente da controllare (né numero, né parola, né «trovato»: false) si scarta: non
    fallirebbe sullo scheletro."""
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
           "esempi": []}
    if not estensione:
        return out
    visti = set()
    for i in d.get("input") or ():
        if isinstance(i, dict) and isinstance(i.get("nome"), str):
            nome = i["nome"].strip().lower()
            if _NOME.match(nome) and nome not in visti and i.get("tipo") in TIPI:
                visti.add(nome)
                out["input"].append({"nome": nome, "tipo": i["tipo"]})
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


class Accettazione(unittest.TestCase):
    pass


for _i, _caso in enumerate(ESEMPI, 1):
    def _t(self, _caso=_caso):
        _prova(self, _caso)
    setattr(Accettazione, f"test_r{_caso['requisito']}_{_i}", _t)
'''


def test_python(an: dict) -> str:
    """Il file test_accettazione.py dagli esempi (scritto dal codice, non dal modello)."""
    esempi = json.dumps(an.get("esempi") or [], ensure_ascii=False, indent=1)
    return (TESTA + f"ESEMPI = json.loads({esempi!r})\n"
            + f"CAMPO = {str(an.get('campo_numero') or 'risultato')!r}\n" + CORPO)


def domanda(an: dict) -> str:
    """Le domande da fare prima di cominciare (al più due), in una frase da dire."""
    ds = [c["domanda"] for c in (an.get("contraddizioni") or [])][:MAX_DOMANDE]
    if not ds:
        return ""
    if len(ds) == 1:
        return "Prima di cominciare: " + ds[0][:1].lower() + ds[0][1:]
    return ("Prima di cominciare, due cose: " + ds[0][:1].lower() + ds[0][1:] + " E "
            + ds[1][:1].lower() + ds[1][1:])


def vincolo(an: dict, file: bool) -> str:
    """Il testo per l'agente in coda ai vincoli."""
    parti = []
    if file:
        ins = ", ".join(f"{i['nome']} ({i['tipo']})" for i in an.get("input") or [])
        parti.append(
            f"Gli esempi di accettazione sono in {FILE}, IN SOLA LETTURA: li ha scritti dai "
            "requisiti un'altra passata, prima del codice, e alla consegna si eseguono con i tuoi "
            "test. Il codice deve farli passare tutti; non puoi cambiarli: se uno ti sembra "
            "sbagliato dillo nel riassunto della consegna."
            + (f" Input del manifesto, con questi nomi: {ins}." if ins else "")
            + (f" Il numero del risultato va nel campo «{an['campo_numero']}»."
               if an.get("campo_numero") else ""))
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
    sistema = SISTEMA.format(cosa=cosa, estensione=SISTEMA_ESEMPI if estensione else "")
    dati, esito = chiama(svc, sistema, utente(cosa, compito, requisiti, parole, risposta),
                         schema(estensione), tempo_s, dalla_voce=False, num_predict=2000)
    if dati is None:
        return None, esito
    return interpreta(dati, len(requisiti), estensione), esito


def rossi(uscita: str) -> list[int]:
    """I requisiti con un esempio rosso, dall'uscita di unittest («FAIL: test_r3_2 …»)."""
    return sorted({int(m) for m in re.findall(r"(?:FAIL|ERROR): test_r(\d+)_\d+",
                                               str(uscita or ""))})


def numeri_esempi(an: dict) -> list[int]:
    return sorted({e["requisito"] for e in an.get("esempi") or [] if e.get("requisito")})
