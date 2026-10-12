"""
La specifica viva (12/10/2026, calliope/requisiti.py, calliope/sviluppo.py, tools/sviluppo.py),
dal caso vero dell'11–12/10 riscritto con parole nostre: un gioco di porte stregate. Alla prima
proposta la specifica diceva «gli oggetti danno punti, i mostri fanno perdere un turno»; la
persona l'ha corretta («anche i mostri danno punti»); al collaudo ha chiesto che il numero di
porte e i punti per vincere «li puoi decidere tu», ed è stato capito al contrario («la persona
sceglie…»); poi l'ha corretto («li decide il gioco, non io»). Ogni modifica si accodava con «Con
questa modifica: …», la lettura a voce tagliata a 420 caratteri non la diceva mai, e alla
consegna la revisione onesta ha segnalato come difetto proprio ciò che la persona voleva.

Il modello dell'agente è un client finto che risponde secondo lo schema della richiesta (i
requisiti, le operazioni della modifica, il confronto, l'analisi): le operazioni sono un dato
da un insieme chiuso, applicate dal codice.

1. **Il caso vero, tre modifiche di fila** (una capita al contrario e poi corretta): a voce si
   sente ogni volta solo il cambiamento; la specifica finale non ha contraddizioni né code «Con
   questa modifica»; requisiti, tappe e vincoli dell'agente sono aggiornati; lo storico è a
   parte; alla consegna il confronto usa i requisiti nuovi e niente «manca» per ciò che la
   persona voleva.
2. **«Correggi»**: un comportamento diverso è la stessa operazione di «cambia» (A3); «non
   funziona, correggilo» senza dire cosa → «Cosa non va?» e l'agente non riparte; la risposta si
   guarda di nuovo; un difetto → la correzione, con la specifica intera (niente «NON cambia»);
   il «sì» a «Lo faccio correggere?» non passa dal modello.
3. **Contrari della modifica**: c'era già; vaga; il modello in ritardo o guasto (niente cambia,
   «Riprovo?»); senza i requisiti (`sviluppo_requisiti: false`) come prima.
4. **Le operazioni**: numeri fuori elenco, operazioni sconosciute, tetto; sostituisci tiene la
   tappa, aggiungi con le tappe, togli, anticipa; la frase con più di tre cambi e con «non si
   può».
5. **La prima proposta lunga**: i punti principali e «il resto è sullo schermo»; le scelte
   fatte al posto della persona dette (M5), e l'analisi dopo le risposte che non inventa.
6. **A2, A6, A7, M2, M4**: un gioco confermato dalla politica si propone comunque; il file della
   persona resta nei lavori dopo; niente «riparti dal programma di prima» senza un programma; la
   modifica di un gioco senza gioco=true è un gioco; i requisiti restano con l'estensione
   attivata (la tappa dopo non si perde) e la modifica dopo li eredita; il gioco ha l'analisi.

A secco, ~3 s.

    python prove\\prova_specifica_viva.py
"""

import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


def detta(out) -> str:
    return str((out or {}).get("risposta_finale") or (out or {}).get("conferma") or "")


COMPITO = ("Crea il gioco delle porte stregate: si sceglie una porta, dietro c'è un mostro, un "
           "dolcetto o un oggetto buffo; gli oggetti danno punti, i mostri fanno perdere un "
           "turno; più giocatori a turno, con una musica di paura e delle animazioni.")

REQ = [
    {"testo": "si sceglie una porta", "nucleo": True, "si_puo": True},
    {"testo": "mostri, dolcetti e oggetti buffi dietro le porte", "nucleo": True, "si_puo": True},
    {"testo": "gli oggetti danno punti", "nucleo": True, "si_puo": True},
    {"testo": "i mostri fanno perdere un turno", "nucleo": True, "si_puo": True},
    {"testo": "più giocatori a turno", "nucleo": True, "si_puo": True},
    {"testo": "musica di paura", "nucleo": False, "si_puo": True},
    {"testo": "animazioni di paura", "nucleo": False, "si_puo": True},
]

# Le tre modifiche del caso vero, come le darebbe il modello dell'agente
MOD_MOSTRI = {"tipo": "cambia", "operazioni": [
    {"op": "sostituisci", "numero": 4, "testo": "anche i mostri danno punti", "nucleo": True,
     "si_puo": True, "dettaglio": "più il mostro è vicino alla fine, più punti vale"}]}
MOD_AL_CONTRARIO = {"tipo": "cambia", "operazioni": [
    {"op": "aggiungi", "testo": "la persona sceglie il numero di porte", "nucleo": True,
     "si_puo": True},
    {"op": "aggiungi", "testo": "la persona sceglie i punti per vincere", "nucleo": True,
     "si_puo": True}]}
MOD_CORRETTA = {"tipo": "cambia", "operazioni": [
    {"op": "sostituisci", "numero": 8, "testo": "il gioco decide il numero di porte",
     "nucleo": True, "si_puo": True},
    {"op": "sostituisci", "numero": 9, "testo": "il gioco decide i punti per vincere",
     "nucleo": True, "si_puo": True}]}


class AgenteVivo:
    """Il client del modello dell'agente: risponde secondo lo schema. Le modifiche vengono da
    una coda (un dict, un'eccezione, o «lento» per il tempo massimo)."""

    def __init__(self, requisiti=REQ, stima="grande", voci=None, modifiche=(), analisi=None):
        self.requisiti, self.stima, self.voci = requisiti, stima, voci
        self.modifiche = list(modifiche)
        self.analisi = analisi
        self.richieste = []

    def chat(self, body, **_):
        self.richieste.append(body)
        props = ((body.get("format") or {}).get("properties") or {})
        if "operazioni" in props:
            m = self.modifiche.pop(0) if self.modifiche else {"tipo": "vago", "operazioni": []}
            if isinstance(m, Exception):
                raise m
            if m == "lento":
                time.sleep(3)
                m = {"tipo": "cambia", "operazioni": []}
            return {"content": json.dumps(m, ensure_ascii=False)}
        if "requisiti" in props:
            return {"content": json.dumps({"requisiti": self.requisiti, "stima": self.stima},
                                          ensure_ascii=False)}
        if "voci" in props:
            n = props["voci"].get("minItems", 0)
            voci = self.voci(n) if callable(self.voci) else (self.voci or
                                                             [{"stato": "fatto"}] * n)
            return {"content": json.dumps({"voci": voci}, ensure_ascii=False)}
        if "punti" in props and self.analisi is not None:
            return {"content": json.dumps(self.analisi, ensure_ascii=False)}
        return {"content": json.dumps({"voce": "Non so.", "serve_correzione": False})}

    def interrompi(self, *a):
        pass

    def utente(self, schema: str, i: int = -1) -> str:
        fatte = [r for r in self.richieste
                 if schema in ((r.get("format") or {}).get("properties") or {})]
        return str(fatte[i]["messages"][-1]["content"]) if fatte else ""

    def quante(self, schema: str) -> int:
        return sum(1 for r in self.richieste
                   if schema in ((r.get("format") or {}).get("properties") or {}))


def ambiente(tmp: Path, agente):
    import prova_revisione_onesta as R
    return R.ambiente(tmp, agente)


def chiama(reg, ctx, nome, args, turno, detto=""):
    import prova_revisione_onesta as R
    ctx.tool_in_sospeso = None
    return R.chiama(reg, ctx, nome, args, turno, detto)


def consegna(svc, est, sv):
    import prova_revisione_onesta as R
    return R.consegna(svc, est, sv)


def gioco(tmp, agente):
    cfg, reg, ctx, est, svc = ambiente(tmp, agente)
    out = chiama(reg, ctx, "sviluppo_apri", {"tipo": "estensione", "gioco": True,
                                             "compito": COMPITO}, 1, "Voglio un gioco.")
    return cfg, reg, ctx, est, svc, svc.sviluppi.corrente("u1"), out


def ultimo(svc):
    return svc.offerte["u1"]["lavoro"]


# ═══════════════════════════ 1. il caso vero ═══════════════════════════

def prova_caso_vero(tmp: Path):
    print("— 1. il caso vero: tre modifiche di fila, una capita al contrario e corretta")
    from calliope.sviluppo import DOMANDA_PROPOSTA, DOMANDA_TAPPE
    agente = AgenteVivo(modifiche=[MOD_MOSTRI, MOD_AL_CONTRARIO, MOD_CORRETTA])
    cfg, reg, ctx, est, svc, sv, out = gioco(tmp / "vero", agente)
    f = detta(out)
    verifica("la prima proposta: la specifica letta e le tappe (7 requisiti)",
             "Ho capito così:" in f and sv.tappe_stato == "proposte" and f.endswith(
                 DOMANDA_TAPPE), f)
    # Modifica 1, alla proposta: «anche i mostri danno punti»
    out = chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": "no, anche i "
                 "mostri danno punti, più sono vicini alla fine più valgono"}, 2,
                 "No, anche i mostri danno punti.")
    f = detta(out)
    verifica("modifica 1: a voce solo il cambiamento, con le parole dei requisiti",
             f == "Ho cambiato una cosa: «i mostri fanno perdere un turno» diventa «anche i "
                  f"mostri danno punti». {DOMANDA_TAPPE}", f)
    verifica("…niente «Ho capito così», e la regola nel registro",
             "Ho capito così" not in f and "sviluppo_modifica_requisiti" in ctx.regole,
             str(ctx.regole))
    verifica("…la richiesta al modello: i requisiti numerati, la frase, schema chiuso, "
             "temperatura 0", "4. i mostri fanno perdere un turno" in agente.utente(
                 "operazioni") and "anche i mostri danno punti" in agente.utente("operazioni")
             and agente.richieste[-1]["options"]["temperature"] == 0.0
             and agente.richieste[-1]["think"] is False)
    lav = ultimo(svc)
    verifica("…il lavoro proposto ha la specifica rigenerata, senza il requisito vecchio",
             "anche i mostri danno punti: più il mostro è vicino alla fine" in lav.compito
             and "perdere un turno" not in lav.compito and "Con questa modifica" not in
             lav.compito and lav.compito == sv.specifica, lav.compito)
    verifica("…e lo storico a parte, nei vincoli: «prima era X, la persona ha chiesto Y»",
             "Modifiche chieste dalla persona" in lav.vincoli and "«i mostri fanno perdere un "
             "turno» è diventato «anche i mostri danno punti»" in lav.vincoli, lav.vincoli)
    verifica("…la tappa resta quella del requisito sostituito (nucleo: la prima)",
             sv.requisiti[3]["testo"] == "anche i mostri danno punti"
             and sv.requisiti[3]["tappa"] == 1 and "TAPPA 1" in lav.vincoli
             and "anche i mostri danno punti" in lav.vincoli.split("TAPPA 1")[1]
             .split("NON farli ora")[0], lav.vincoli)
    # «Sì, comincia»: la prima tappa
    chiama(reg, ctx, "sviluppo_apri", {"proposta": lav.id}, 3, "Sì, comincia.")
    verifica("«sì» → la prima tappa parte con la specifica nuova",
             sv.fase == "sviluppo" and lav.stato == "in_corso" and sv.tappe_stato == "accettate")
    consegna(svc, est, sv)
    verifica("alla consegna il confronto è sui requisiti nuovi",
             "anche i mostri danno punti" in agente.utente("voci")
             and "perdere un turno" not in agente.utente("voci"), agente.utente("voci")[:400])
    # Modifica 2, al collaudo, con «correggi» (il gioco: «se dice cosa cambiare»), capita al
    # contrario. Dal 12/10 (lavoro 3, A4) la frase dice anche che la versione provata resta
    RESTA = "La versione 2 resta: se lasci com'era, torniamo a provarla. "
    out = chiama(reg, ctx, "sviluppo_correggi", {"problema": "all'inizio il numero di porte e i "
                 "punti per vincere li puoi decidere tu"}, 5, "Il numero di porte e i punti li "
                 "puoi decidere tu.")
    f = detta(out)
    verifica("modifica 2 (al collaudo, «correggi»): la stessa operazione sui requisiti",
             f == RESTA + "Ho cambiato due cose: aggiungo «la persona sceglie il numero di porte»; "
                  "aggiungo «la persona sceglie i punti per vincere». " + DOMANDA_PROPOSTA
             and "sviluppo_correggi_cambia" in ctx.regole and sv.fase == "analisi", f)
    verifica("…la persona sente come è stato capito (qui al contrario), e niente è partito",
             "la persona sceglie" in f and svc.lavori[-1] is lav, f)
    # Modifica 3: la correzione
    out = chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": "no, al contrario: "
                 "li decide il gioco, non io"}, 6, "No, al contrario: li decide il gioco.")
    f = detta(out)
    verifica("modifica 3: la correzione sostituisce i due requisiti sbagliati",
             f == RESTA + "Ho cambiato due cose: «la persona sceglie il numero di porte» diventa «il "
                  "gioco decide il numero di porte»; «la persona sceglie i punti per vincere» "
                  "diventa «il gioco decide i punti per vincere». " + DOMANDA_PROPOSTA, f)
    spec = sv.specifica
    verifica("la specifica finale: niente contraddizioni né code di modifiche",
             "Con questa modifica" not in spec and "perdere un turno" not in spec
             and "la persona sceglie" not in spec and "il gioco decide il numero di porte" in spec
             and "anche i mostri danno punti" in spec and "gli oggetti danno punti" in spec, spec)
    testi = [r["testo"] for r in sv.requisiti]
    verifica("i requisiti: 9, quelli nuovi al posto di quelli sbagliati",
             len(testi) == 9 and testi[7] == "il gioco decide il numero di porte"
             and testi[8] == "il gioco decide i punti per vincere", str(testi))
    verifica("…con le tappe aggiornate: quelli aggiunti nella tappa di adesso",
             sv.requisiti[7]["tappa"] == 1 and sv.requisiti[8]["tappa"] == 1
             and sv.requisiti[5]["tappa"] == 2, str([r["tappa"] for r in sv.requisiti]))
    verifica("lo storico: tre modifiche, con le parole dette", len(sv.modifiche) == 3
             and sv.modifiche[1]["cambi"][0]["op"] == "aggiungi"
             and "li decide il gioco" in sv.modifiche[2]["detto"], str(sv.modifiche))
    lav3 = ultimo(svc)
    verifica("il lavoro nuovo: dai file della versione provata, con la specifica e la tappa "
             "nuove", lav3.compito == spec and "estensione.py" in lav3.file_iniziali
             and "il gioco decide il numero di porte" in lav3.vincoli.split("TAPPA 1")[1]
             .split("NON farli ora")[0] and lav3.gioco is True, lav3.vincoli)
    verifica("…e quello che la versione di prima faceva già non si rompe",
             "la versione di prima li faceva già" in lav3.vincoli
             and "anche i mostri danno punti" in lav3.vincoli.split("faceva già")[1], lav3.vincoli)
    verifica("i dati del turno della voce: i requisiti di adesso (non la coda tagliata)",
             "il gioco decide i punti per vincere" in svc.sviluppi.dati_turno(sv))
    scheda = svc.sviluppi.testo_scheda(sv)
    verifica("la scheda: la specifica intera, i requisiti e le modifiche chieste",
             "## Modifiche chieste" in scheda and "li decide il gioco" in scheda
             and "il gioco decide il numero di porte" in scheda, scheda)
    vista = svc.sviluppi.dati_vista(sv)
    verifica("la vista ha lo storico delle modifiche", len(vista["modifiche"]) == 3
             and "→ «il gioco decide il numero di porte»" in vista["modifiche"][2]["cambi"][0])
    # «Sì» e la consegna: il confronto non segnala come difetto ciò che la persona voleva
    chiama(reg, ctx, "sviluppo_apri", {"proposta": lav3.id}, 7, "Sì.")
    agente.voci = lambda n: [{"stato": "fatto"}] * n
    item = consegna(svc, est, sv)
    verifica("alla consegna: i requisiti nuovi al confronto, nessun falso allarme",
             "il gioco decide il numero di porte" in agente.utente("voci")
             and "la persona sceglie" not in agente.utente("voci")
             and "Attenzione" not in item["messaggio"], item["messaggio"])
    verifica("…e i requisiti non si estraggono di nuovo (le tappe non si riassegnano)",
             agente.quante("requisiti") == 1, str(agente.quante("requisiti")))


# ═══════════════════════════ 2. correggi ═══════════════════════════

def prova_correggi(tmp: Path):
    print("— 2. «correggi»: comportamento diverso, vago, difetto, il «sì» alla domanda")
    agente = AgenteVivo(stima="piccolo", requisiti=REQ[:3],
                        modifiche=[{"tipo": "vago", "domanda": "Cosa non va nel gioco?",
                                    "operazioni": []},
                                   {"tipo": "difetto", "operazioni": []}])
    cfg, reg, ctx, est, svc, sv, out = gioco(tmp / "correggi", agente)
    lav = ultimo(svc)
    chiama(reg, ctx, "sviluppo_apri", {"proposta": lav.id}, 2, "Sì.")
    consegna(svc, est, sv)
    n_lavori = len(svc.lavori)
    out = chiama(reg, ctx, "sviluppo_correggi", {"problema": "non ci siamo, ci sono delle cose "
                 "che non funzionano, correggile"}, 4, "Non ci siamo, correggile.")
    verifica("«non funziona, correggilo» senza dire cosa → «Cosa non va?», l'agente non riparte",
             detta(out) == "Cosa non va nel gioco?" and len(svc.lavori) == n_lavori
             and "sviluppo_correggi_chiede" in ctx.regole
             and (out.get("in_sospeso") or {}).get("tool") == "sviluppo_correggi", detta(out))
    ctx.tool_in_sospeso = "sviluppo_correggi"
    import prova_estensioni as P
    ctx.regole, ctx.user_text = [], "Le porte non si aprono quando le tocchi."
    out = P.chiama(reg, ctx, "sviluppo_correggi", {"problema": "le porte non si aprono quando "
                   "le tocchi"}, turno=5)
    nuovo = svc.lavori[-1]
    verifica("la risposta si guarda di nuovo: un difetto → la correzione parte",
             agente.quante("operazioni") == 2 and nuovo is not lav and nuovo.stato == "in_corso"
             and "sviluppo_correzione" in ctx.regole, f"{ctx.regole} {detta(out)}")
    verifica("…con la specifica intera nel compito, e niente «la specifica NON cambia» tagliato",
             "NON cambia" not in nuovo.vincoli and nuovo.compito == sv.specifica
             and "le porte non si aprono" in nuovo.vincoli, nuovo.vincoli)
    # Il «sì» a «Lo faccio correggere?» (un collaudo fallito): niente modello
    agente2 = AgenteVivo(stima="piccolo", requisiti=REQ[:3])
    cfg, reg, ctx, est, svc, sv, out = gioco(tmp / "si", agente2)
    lav = ultimo(svc)
    chiama(reg, ctx, "sviluppo_apri", {"proposta": lav.id}, 2, "Sì.")
    consegna(svc, est, sv)
    ctx.tool_in_sospeso, ctx.regole, ctx.user_text = "sviluppo_correggi", [], "Sì."
    P.chiama(reg, ctx, "sviluppo_correggi", {"problema": "il collaudo si ferma con un errore"},
             turno=4)
    verifica("contrario: il «sì» a «Lo faccio correggere?» è una correzione, senza il modello",
             agente2.quante("operazioni") == 0 and "sviluppo_correzione" in ctx.regole,
             str(ctx.regole))


# ═══════════════════════════ 3. contrari della modifica ═══════════════════════════

def prova_contrari(tmp: Path):
    print("— 3. contrari: c'era già, vaga, guasto, senza requisiti")
    from calliope.sviluppo import DOMANDA_PROPOSTA
    agente = AgenteVivo(stima="piccolo", requisiti=REQ[:3], modifiche=[
        {"tipo": "cambia", "operazioni": []},
        {"tipo": "vago", "domanda": "Cosa vuoi cambiare delle porte", "operazioni": []},
        ConnectionError("agente spento")])
    cfg, reg, ctx, est, svc, sv, out = gioco(tmp / "contrari", agente)
    spec0, lav0 = sv.specifica, ultimo(svc)
    out = chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": "dietro le porte "
                 "ci sono mostri, dolcetti e oggetti buffi"}, 2)
    verifica("c'era già → «non cambio niente», la proposta di prima resta, la sua domanda",
             detta(out) == f"Questo nella richiesta c'è già: non cambio niente. "
                           f"{DOMANDA_PROPOSTA}" and sv.specifica == spec0
             and (out.get("in_sospeso") or {}).get("argomenti") == {"proposta": lav0.id}
             and not sv.modifiche, detta(out))
    out = chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": "cambia le porte"},
                 3)
    verifica("vaga → la domanda del modello, niente cambia",
             detta(out) == "Cosa vuoi cambiare delle porte?" and sv.specifica == spec0
             and "sviluppo_modifica_vaga" in ctx.regole, detta(out))
    out = chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": "anche i fantasmi"},
                 4)
    verifica("modello guasto → «Riprovo?», la richiesta NON cambia",
             detta(out).endswith("Riprovo?") and sv.specifica == spec0 and not sv.modifiche
             and (out.get("in_sospeso") or {}).get("argomenti") == {
                 "azione": "analisi", "cambia": "anche i fantasmi"}, detta(out))
    # Il tempo massimo
    agente = AgenteVivo(stima="piccolo", requisiti=REQ[:3], modifiche=["lento"])
    cfg, reg, ctx, est, svc, sv, out = gioco(tmp / "lento", agente)
    cfg.sviluppo_requisiti_s = 1.0
    t0 = time.monotonic()
    out = chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": "anche i "
                 "fantasmi"}, 2)
    verifica("il modello in ritardo: si risponde entro il tempo massimo, «ci mette troppo»",
             time.monotonic() - t0 < 2.5 and "ci mette troppo" in detta(out), detta(out))
    # Senza i requisiti: come prima
    agente = AgenteVivo(stima="piccolo", requisiti=REQ[:3])
    cfg, reg, ctx, est, svc = ambiente(tmp / "senza", agente)
    cfg.sviluppo_requisiti = False
    chiama(reg, ctx, "sviluppo_apri", {"tipo": "estensione", "gioco": True, "compito": COMPITO},
           1)
    sv = svc.sviluppi.corrente("u1")
    out = chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": "anche i "
                 "fantasmi"}, 2)
    verifica("contrario: sviluppo_requisiti false → come prima del 12/10, senza il modello",
             agente.quante("operazioni") == 0 and "Con questa modifica: anche i fantasmi"
             in sv.specifica, sv.specifica)


# ═══════════════════════════ 4. le operazioni ═══════════════════════════

def prova_operazioni():
    print("— 4. le operazioni sui requisiti")
    from calliope import requisiti as rq
    m = rq.interpreta_modifica({"tipo": "cambia", "operazioni": [
        {"op": "sostituisci", "numero": 9, "testo": "x"},          # fuori elenco
        {"op": "riscrivi", "numero": 1, "testo": "x"},             # sconosciuta
        {"op": "aggiungi", "testo": ""},                           # senza testo
        {"op": "togli", "numero": "2"},
        {"op": "aggiungi", "testo": "**fantasmi** https://x.it", "nucleo": False}]}, 3)
    verifica("validazione: numeri fuori elenco, operazioni sconosciute e testi vuoti non contano",
             [o["op"] for o in m["operazioni"]] == ["togli", "aggiungi"]
             and m["operazioni"][0]["numero"] == 2 and m["operazioni"][1]["testo"] == "fantasmi",
             str(m))
    verifica("un tipo sconosciuto senza operazioni vale «vago»; con «difetto» niente operazioni",
             rq.interpreta_modifica({"tipo": "boh"}, 3)["tipo"] == "vago"
             and rq.interpreta_modifica({"tipo": "difetto", "operazioni": [
                 {"op": "togli", "numero": 1}]}, 3)["operazioni"] == [])
    tante = rq.interpreta_modifica({"tipo": "cambia", "operazioni": [
        {"op": "aggiungi", "testo": f"cosa {i}"} for i in range(10)]}, 1)
    verifica("al più MAX_OPERAZIONI operazioni", len(tante["operazioni"]) == rq.MAX_OPERAZIONI)
    req = [{"testo": "a", "nucleo": True, "si_puo": True, "tappa": 1},
           {"testo": "b", "nucleo": False, "si_puo": True, "tappa": 2},
           {"testo": "c", "nucleo": False, "si_puo": True, "tappa": 2}]
    ops = rq.interpreta_modifica({"tipo": "cambia", "operazioni": [
        {"op": "sostituisci", "numero": 2, "testo": "b nuovo"},
        {"op": "togli", "numero": 2},                               # già toccato: non conta
        {"op": "togli", "numero": 1},
        {"op": "anticipa", "numero": 3},
        {"op": "aggiungi", "testo": "d", "nucleo": True},
        {"op": "aggiungi", "testo": "e", "nucleo": False},
        {"op": "aggiungi", "testo": "C"}]}, 3)["operazioni"]        # doppione di c
    nuovi, cambi = rq.applica(req, ops, lambda r: 1 if r.get("nucleo") else 2, 1)
    verifica("applica: sostituisci tiene la tappa, togli, anticipa, aggiungi con la tappa, "
             "niente doppioni né un requisito toccato due volte",
             [(r["testo"], r["tappa"]) for r in nuovi]
             == [("b nuovo", 2), ("c", 1), ("d", 1), ("e", 2)]
             and [c["op"] for c in cambi] == ["sostituisci", "togli", "anticipa", "aggiungi",
                                               "aggiungi"], str(nuovi))
    f = rq.frase_cambi(cambi)
    verifica("la frase con più di tre cambi: i primi tre, poi «sullo schermo»",
             f == "Ho cambiato cinque cose: «b» diventa «b nuovo»; tolgo «a»; «c» lo facciamo "
                  "adesso; e altre 2, sullo schermo.", f)
    f = rq.frase_cambi([{"op": "aggiungi", "dopo": "classifica su internet", "si_puo": False,
                         "limite": "Un gioco non va su internet"},
                        {"op": "aggiungi", "dopo": "musica", "dopo_tappa": True,
                         "si_puo": True}])
    verifica("…ciò che qui non si può fare si dice, e la tappa dopo",
             f == "Ho cambiato due cose: aggiungo «classifica su internet»; aggiungo «musica» "
                  "per la tappa dopo. Però «classifica su internet» oggi qui non si può fare: "
                  "un gioco non va su internet.", f)
    ops = rq.interpreta_modifica({"tipo": "cambia", "operazioni": [
        {"op": "sostituisci", "numero": 1, "testo": "A", "dettaglio": "da 3 a 5, a caso"},
        {"op": "sostituisci", "numero": 2, "testo": "b"}]}, 3)["operazioni"]
    prec, cambi = rq.applica(req, ops, lambda r: 1, 1)
    verifica("lo stesso requisito con un dettaglio nuovo è «precisato»; uguale non conta",
             [c["op"] for c in cambi] == ["precisa"] and prec[0]["dettaglio"] == "da 3 a 5, a caso"
             and rq.frase_cambi(cambi) == "Ho cambiato una cosa: per «A», da 3 a 5, a caso.",
             rq.frase_cambi(cambi))
    spec = rq.specifica_da_requisiti(nuovi + [{"testo": "x", "si_puo": False, "limite": "no"}],
                                     "Un gioco", "Porte")
    verifica("la specifica rigenerata: un requisito per riga, i limiti a parte, niente tetto",
             spec.splitlines()[0].startswith("Un gioco «Porte»: deve fare")
             and "1. b nuovo." in spec and "4. e." in spec
             and "Qui non si può fare, quindi non va fatto: x (no)." in spec, spec)


# ═══════════════════════════ 5. la prima proposta e le scelte ═══════════════════════════

def prova_proposta(tmp: Path):
    print("— 5. la prima proposta lunga, le scelte dove la persona non ha risposto")
    lunga = COMPITO + " " + " ".join(f"Regola {i}: dietro la porta {i} c'è una sorpresa diversa "
                                      "con un suono suo." for i in range(1, 9))
    agente = AgenteVivo(stima="piccolo", requisiti=REQ[:4])
    cfg, reg, ctx, est, svc = ambiente(tmp / "lunga", agente)
    out = chiama(reg, ctx, "sviluppo_apri", {"tipo": "estensione", "gioco": True,
                                             "compito": lunga}, 1)
    f = detta(out)
    sv = svc.sviluppi.corrente("u1")
    verifica("specifica lunga: a voce i punti principali e «il resto è sullo schermo»",
             "Ho capito così: in breve, si sceglie una porta, mostri, dolcetti e oggetti buffi "
             "dietro le porte, gli oggetti danno punti e i mostri fanno perdere un turno. Il "
             "resto è sullo schermo." in f and "Regola 8" in sv.specifica, f)
    agente = AgenteVivo(stima="piccolo", requisiti=REQ[:4])
    cfg, reg, ctx, est, svc = ambiente(tmp / "corta", agente)
    out = chiama(reg, ctx, "sviluppo_apri", {"tipo": "estensione", "gioco": True,
                                             "compito": "un gioco delle porte"}, 1)
    verifica("contrario: una specifica corta si dice intera",
             "Ho capito così: un gioco delle porte." in detta(out)
             and "sullo schermo" not in detta(out), detta(out))
    # Le scelte (M5): l'analisi dopo le risposte non inventa
    from calliope.agenti import richiesta as ar
    e = ar.interpreta(json.dumps({"punti": {"input": "detto", "output": "detto",
                                            "dati_persona": "manca", "linguaggio": "detto"},
                                  "specifica": "calcola la bolletta con 0,20 euro al kWh, da "
                                               "cambiare", "domande": [{"domanda": "Che tariffa?",
                                                                       "senza_risposta": "sbaglia"}],
                                  "scelte": ["la tariffa non me l'hai detta: metto 0,20 euro "
                                             "al chilowattora, da cambiare"]}),
                      "codice", senza_domande=True)
    verifica("dopo le risposte un punto senza risposta resta «manca», con la scelta detta, "
             "e niente altre domande", e.mancano == ["dati_persona"] and not e.domande
             and e.esito == "raffinabile" and e.scelte and e.stati["dati_persona"] == "manca",
             str(e))
    s = ar.schema("codice", senza_domande=True)
    verifica("…lo schema lo permette («manca» c'è) e chiede le scelte",
             "manca" in s["properties"]["punti"]["properties"]["dati_persona"]["enum"]
             and "scelte" in s["required"], str(s["required"]))
    msgs = ar.messaggi(None, "codice", "bolletta", senza_domande=True)
    verifica("…e il prompt dice di non inventare in silenzio",
             "MAI un valore inventato in silenzio" in msgs[-1]["content"])
    # La proposta dice le scelte
    from calliope.sviluppo import Sviluppi
    svs = Sviluppi(cfg, tmp / "scelte", None, log=lambda *a: None)
    sv = svs.apri("u1", "Dario", "programma", "la bolletta")
    lav = SimpleNamespace(id="L9", tipo="codice", persona="u1", specifica="calcola la bolletta",
                          compito="bolletta", titolo="Bolletta", vincoli="", estensione=None,
                          scelte=["la tariffa non me l'hai detta: metto 0,20 euro, da cambiare"])
    svs.proposto(lav)
    cfg.sviluppo_requisiti = False
    f = svs.frase_proposta(sv, lav)
    verifica("la proposta dice la scelta fatta al posto della persona",
             "Dove non mi hai risposto ho scelto io: la tariffa non me l'hai detta: metto 0,20 "
             "euro, da cambiare." in f, f)


# ═══════════════════════════ 6. A2, A6, A7, M2, M4 ═══════════════════════════

def prova_flussi(tmp: Path):
    print("— 6. un gioco non parte senza la specifica letta, il file resta, il gioco in "
          "modifica, i requisiti con l'estensione")
    from calliope.tools import estensioni as te
    import prova_estensioni as P
    # A2: il «sì» della politica è già arrivato, ma lo sviluppo è all'analisi
    agente = AgenteVivo(stima="piccolo", requisiti=REQ[:3])
    cfg, reg, ctx, est, svc = ambiente(tmp / "a2", agente)
    ctx.regole, ctx.turno, ctx.user_text = [], 1, "Voglio un gioco."
    ctx.politica_accettata = True
    out = te._estensione_crea(ctx, compito=COMPITO, gioco=True)
    ctx.politica_accettata = False
    sv = svc.sviluppi.corrente("u1")
    verifica("A2: un gioco già confermato alla politica si propone (specifica letta), non parte",
             "Ho capito così:" in detta(out) and not svc.lavori and sv.fase == "analisi"
             and "sviluppo_analisi_prima" in ctx.regole, detta(out))

    # A7: la versione nuova di un gioco senza gioco=true
    agente = AgenteVivo(stima="piccolo", requisiti=REQ[:3])
    cfg, reg, ctx, est, svc = ambiente(tmp / "a7", agente)
    vero = est.archivio.manifesto

    def con_scheda(nome, n=None):
        m = vero(nome, n)
        return dict(m, scheda={"titolo": "Porte"}) if m else m
    est.archivio.manifesto = con_scheda
    out = chiama(reg, ctx, "sviluppo_apri", {"tipo": "estensione", "modifica": "meteo_citta",
                                             "compito": "metti sette porte"}, 1,
                 "Nel gioco metti sette porte.")
    lav = ultimo(svc)
    sv = svc.sviluppi.corrente("u1")
    verifica("A7: la modifica di un gioco senza gioco=true è un gioco (contratto e scheletro)",
             lav.gioco is True and te.VINCOLO_GIOCO in lav.vincoli and sv.gioco
             and "estensione_gioco_dal_manifesto" in ctx.regole, f"{ctx.regole} {lav.vincoli}")
    est.archivio.manifesto = vero

    # A6: il file della persona resta, «riparti dal programma di prima» solo con un programma
    from calliope.tools import sviluppo as ts
    agente = AgenteVivo(stima="piccolo", requisiti=[{"testo": "rinomina le foto", "nucleo": True,
                                                     "si_puo": True}],
                        modifiche=[{"tipo": "cambia", "operazioni": [
                            {"op": "aggiungi", "testo": "ordina per data", "nucleo": True}]}])
    cfg, reg, ctx, est, svc = ambiente(tmp / "a6", agente)
    svs = svc.sviluppi
    sv = svs.apri("u1", "Dario", "programma", "rinomina le foto del file", titolo="Rinomina")
    sv.specifica = "rinomina le foto elencate nel file"
    sv.ingressi["vincoli"] = "Le date sono nel formato giorno, mese, anno."
    primo = svc.nuovo("codice", sv.specifica, "u1", "Dario", "amministra")
    primo.input = {"nome": "foto.csv", "estensione": "csv", "dati": b"a;b\n",
                   "percorso": "foto.csv"}
    svc.avvia(primo)
    svs.avviato(primo)
    svc.finisci(primo, "errore", motivo="un errore")
    verifica("il file della persona si tiene da parte alla fine del lavoro (per un riavvio)",
             (sv.ingressi.get("file") or {}).get("nome") == "foto.csv")
    out = chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": "e ordinale per "
                 "data"}, 2)
    lav = ultimo(svc)
    verifica("A6: la modifica di un programma tiene il file e i vincoli della persona",
             getattr(lav, "input", None) and lav.input["nome"] == "foto.csv"
             and "giorno, mese, anno" in lav.vincoli, f"{detta(out)} {lav.vincoli}")
    verifica("…e senza un programma di prima niente «riparti dal programma di prima»",
             "Riparti dal programma di prima" not in lav.vincoli, lav.vincoli)
    primo.input = None                         # dopo un riavvio: da disco
    svc.lavori.remove(primo)
    lav2 = ts._lavoro_dello_sviluppo(ctx, svs, sv, P.Profili().get("Dario"), sv.specifica)
    verifica("…anche dopo un riavvio (la copia su disco)", getattr(lav2, "input", None)
             and lav2.input["dati"] == b"a;b\n")
    svs.chiudi(sv, "uscita")
    verifica("…e la copia se ne va con lo sviluppo chiuso", svs.file_persona(sv) is None)

    # M2: i requisiti restano con l'estensione attivata, la tappa dopo non si perde
    agente = AgenteVivo(voci=[{"stato": "fatto"}] * 5 + [{"stato": "manca"}] * 2,
                        modifiche=[{"tipo": "cambia", "operazioni": [
                            {"op": "anticipa", "numero": 6}]}])
    cfg, reg, ctx, est, svc, sv, out = gioco(tmp / "m2", agente)
    lav = ultimo(svc)
    chiama(reg, ctx, "sviluppo_apri", {"proposta": lav.id}, 2, "Sì, comincia.")
    consegna(svc, est, sv)
    svs = svc.sviluppi
    svs.estensione_approvata(sv.estensione, sv.versione)
    verifica("M2: attivata la tappa 1, i requisiti restano con l'estensione e la tappa 2 è da "
             "fare", svs.restano_dopo(sv.estensione) == ["musica di paura",
                                                         "animazioni di paura"],
             str(svs.restano_dopo(sv.estensione)))
    from calliope.sviluppo import Sviluppi
    di_nuovo = Sviluppi(cfg, svs.percorso.parent, svc, log=lambda *a: None)
    verifica("…anche dopo un riavvio", di_nuovo.restano_dopo(sv.estensione)
             == ["musica di paura", "animazioni di paura"])
    nome = sv.estensione
    out = chiama(reg, ctx, "sviluppo_apri", {"tipo": "estensione", "modifica": nome,
                                             "compito": "fai anche la musica di paura",
                                             "gioco": True}, 5, "Fai anche la musica.")
    sv2 = svs.corrente("u1")
    lav = ultimo(svc)
    verifica("la modifica dopo eredita i requisiti e la anticipa (niente estrazione da capo)",
             sv2 is not sv and len(sv2.requisiti) == 7 and agente.quante("requisiti") == 1
             and "«musica di paura» lo facciamo adesso" in detta(out)
             and "musica di paura" in lav.vincoli.split("TAPPA 1")[1].split("NON farli")[0],
             detta(out))
    verifica("…e quello che la versione attiva fa già non si deve rompere",
             "la versione di prima li faceva già" in lav.vincoli, lav.vincoli)

    # M4: un gioco ha l'analisi, con la sua lista di controllo
    from calliope.agenti.richiesta import Analizzatore
    agente = AgenteVivo(stima="piccolo", requisiti=REQ[:3], analisi={
        "impossibile": "", "punti": {"giocatori": "detto", "regole": "manca",
                                     "come_si_vince": "scelta_ragionevole",
                                     "voce": "scelta_ragionevole"},
        "dal_contesto": [], "domande": [{"domanda": "Cosa succede quando esce il mostro?",
                                         "senza_risposta": "sbaglia"}],
        "specifica": "", "nome": "porte", "fonte_url": "", "gia_fatto": "",
        "come_chiederlo": ""})
    cfg, reg, ctx, est, svc = ambiente(tmp / "m4", agente)
    svc.analizzatore = Analizzatore(cfg, svc, log=lambda *a: None)
    out = chiama(reg, ctx, "sviluppo_apri", {"tipo": "estensione", "gioco": True,
                                             "compito": "un gioco delle porte: se esce il "
                                                        "mostro…"}, 1)
    analisi = agente.utente("punti")
    sistema = next((r["messages"][0]["content"] for r in agente.richieste
                    if "punti" in ((r.get("format") or {}).get("properties") or {})), "")
    verifica("M4: il gioco ha l'analisi (giocatori, regole, come si vince, voce) e la domanda",
             "giocatori = quanti giocano" in sistema and "riceve solo i comandi" in sistema
             and detta(out).endswith("Cosa succede quando esce il mostro?")
             and "analisi_vaga" in ctx.regole and not svc.lavori, f"{detta(out)} {analisi}")


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        prova_caso_vero(tmp)
        prova_correggi(tmp)
        prova_contrari(tmp)
        prova_operazioni()
        prova_proposta(tmp)
        prova_flussi(tmp)
    print()
    print("Tutto bene." if not errori else f"{errori} errori.")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
