"""Il giro vero della DGX dell'08/10 sera (19:06–20:13, 26B e qwen3.6), a secco (08/10/2026,
giro 6 della modalità sviluppo; docs/aree/agenti-estensioni.md).

Riscritto con nomi di fantasia («Valfiorita», «Borgo Alto», «Pratofiorito»). Tre problemi:

1. «Fermo lo sviluppo» con l'agente al lavoro → `sviluppo_passo azione=sospendi` e «l'agente
   intanto finisce il suo lavoro»; Dario: «Ti ho detto di stopparlo… non deve più continuare».
   Ora c'è l'azione `ferma` (il lavoro si ferma, lo sviluppo resta), distinta da `sospendi` (una
   pausa: l'agente finisce), e `sospendi` con l'agente al lavoro chiede «Vuoi che fermi anche il
   lavoro dell'agente?». La scelta resta al modello (descrizioni, dati del turno);
2. «Sì, rifallo» dopo il lavoro fermato → `analisi` senza modifica → «cosa vuoi cambiare?», poi
   la specifica riletta e un altro «va bene così». Ora l'azione `rifai` riparte subito con la
   stessa specifica, e la domanda «lo rifaccio così com'è?» ha l'azione in sospeso giusta;
3. «Prova con Borgoverde Maggiore e Pratofiorito» → UNA chiamata con argomenti = {citta: il
   primo} e dati = i due, e la voce «per Pratofiorito non ho ancora ricevuto i dati». Ora, se il
   modello ha separato i valori (argomenti con uno solo di quelli dell'elenco nei dati), un
   collaudo per valore (`collaudo_piu_valori`); contrari: «Bosco e Prato» come nome solo,
   «Pratofiorito, 3 giorni», un programma con «3 e 5»; e nei dati del turno la spinta «un
   collaudo per valore, mai dire che aspetti dati di un collaudo non fatto, «e invece X?» è un
   collaudo».

    python prove\\prova_sviluppo_giro6.py
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_estensioni as P  # noqa: E402
import prova_sviluppo as S  # noqa: E402
import prova_sviluppo_giro3 as G3  # noqa: E402
from calliope import politica, valore  # noqa: E402
from calliope import sviluppo as SV  # noqa: E402
from calliope.tools import sviluppo as ts  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


def detta(r) -> str:
    return str((r or {}).get("risposta_finale") or (r or {}).get("conferma") or "")


def al_lavoro(tmp):
    """Lo sviluppo di un'estensione aperto con il lavoro dell'agente in corso."""
    cfg, reg, ctx, est, svc = G3.ambiente(tmp)
    ctx.turno = 1
    P.chiama(reg, ctx, "sviluppo_apri", {
        "tipo": "estensione", "compito": "un'estensione che dica il meteo di una città "
                                          "qualunque", "modifica": "meteo_citta"})
    lav = svc.offerte["u1"]["lavoro"]
    P.chiama(reg, ctx, "sviluppo_apri", {"proposta": lav.id}, turno=2)
    sv = svc.sviluppi.corrente("u1")
    return cfg, reg, ctx, est, svc, sv, lav


# ═══════════════════════════ 1. ferma e sospendi ═══════════════════════════

def prova_ferma(tmp):
    print("— 1. «ferma» ferma il lavoro dell'agente, «sospendi» lo lascia finire")
    cfg, reg, ctx, est, svc, sv, lav = al_lavoro(tmp / "a")
    verifica("preparazione: sviluppo allo sviluppo, lavoro in corso",
             sv.fase == "sviluppo" and sv.lavoro == lav.id and lav.stato == "in_corso",
             f"{sv.fase} {sv.lavoro} {lav.stato}")
    riga = svc.sviluppi.riga_fase(sv)
    verifica("dati del turno con l'agente al lavoro: «ferma/stoppa/blocca» → ferma, «sospendi»"
             " → sospendi (l'agente finisce), nel dubbio la domanda",
             "azione ferma" in riga and "azione sospendi" in riga
             and "fermo anche il lavoro dell'agente?" in riga, riga)
    msg = svc.sviluppi.dati_turno(sv)
    verifica("…e la riga finale dei dati del turno: pausa = sospendi, fermare = ferma",
             "azione ferma" in msg and "un lavoro dell'agente in corso continua" in msg, msg[-400:])

    # Il giro vero: sospendi con l'agente al lavoro → la domanda, poi «sì» → ferma
    r = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "sospendi"}, turno=3)
    sosp = r.get("in_sospeso") or {}
    verifica("sospendi con l'agente al lavoro: lo dice e chiede «Vuoi che fermi anche il lavoro "
             "dell'agente?» (in sospeso: sviluppo_passo ferma); il lavoro continua",
             "finisce il suo lavoro" in detta(r) and "fermi anche il lavoro" in detta(r)
             and sosp.get("tool") == "sviluppo_passo"
             and sosp.get("argomenti") == {"azione": "ferma"} and lav.stato == "in_corso"
             and sv.stato == "sospesa", json.dumps(r, ensure_ascii=False)[:400])
    ds = svc.sviluppi.dati_sospesi("u1") or ""
    verifica("dati del turno con lo sviluppo sospeso e l'agente al lavoro: «fermalo» → ferma",
             "l'agente lavora ancora" in ds and "azione ferma" in ds, ds)
    ctx.regole = []
    r = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "ferma"}, turno=4)
    verifica("…«sì» (ferma) con lo sviluppo sospeso: il lavoro si ferma, lo sviluppo resta "
             "sospeso, senza lavoro",
             lav.stato == "annullato" and lav.id in svc.annullati and sv.lavoro is None
             and sv.stato == "sospesa" and sv.nota == "annullato"
             and "Ho fermato il lavoro dell'agente" in detta(r)
             and "sviluppo_fermato" in ctx.regole, detta(r))
    r = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "riprendi"}, turno=5)
    verifica("ripreso dopo il lavoro fermato: «l'hai fermato tu: lo rifaccio così com'è…» con "
             "l'azione in sospeso rifai (DGX 20:04: «siamo allo sviluppo» e basta)",
             "l'hai fermato tu" in detta(r) and "lo rifaccio così com'è" in detta(r)
             and "azione = rifai" in str((r.get("in_sospeso") or {}).get("argomenti")),
             json.dumps(r, ensure_ascii=False)[:400])

    # Direttamente: «Fermo lo sviluppo» → ferma, lo sviluppo resta aperto
    cfg, reg, ctx, est, svc, sv, lav = al_lavoro(tmp / "b")
    ctx.regole = []
    r = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "ferma"}, turno=3)
    verifica("ferma con l'agente al lavoro: il lavoro si ferma, lo sviluppo resta aperto allo "
             "sviluppo, senza lavoro", lav.stato == "annullato" and sv.stato == "aperta"
             and sv.fase == "sviluppo" and sv.lavoro is None and "non continua" in detta(r)
             and "lo rifaccio così com'è" in detta(r), detta(r))
    verifica("…un'azione in più nell'enum (ferma, rifai) e i sinonimi «stop», «rifallo»",
             {"ferma", "rifai"} <= set(ts.AZIONI))
    r = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "ferma"}, turno=4)
    verifica("contrario: ferma senza un lavoro in corso → una pausa (lo sviluppo si sospende), "
             "nessun annullo", sv.stato == "sospesa" and "non sta lavorando" in detta(r)
             and svc.annullati == [lav.id], detta(r))

    cfg, reg, ctx, est, svc, sv, lav = al_lavoro(tmp / "c")
    r = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "stop"}, turno=3)
    verifica("«stop» come azione vale ferma", lav.stato == "annullato", detta(r))

    cfg, reg, ctx, est, svc, sv, lav = al_lavoro(tmp / "d")
    r = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "chiudi"}, turno=3)
    verifica("chiudi con l'agente al lavoro: sospende (come prima) e chiede se fermare il "
             "lavoro", sv.stato == "sospesa" and lav.stato == "in_corso"
             and (r.get("in_sospeso") or {}).get("argomenti") == {"azione": "ferma"}, detta(r))

    cfg, reg, ctx, est, svc, sv, lav = al_lavoro(tmp / "e")
    r = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "sospendi"}, turno=3)
    verifica("contrario: «mettiamo in pausa» (sospendi) non ferma il lavoro",
             lav.stato == "in_corso" and not svc.annullati)

    # La politica e il valore dell'azione
    cl = politica.classe_di("sviluppo_passo")
    for frase in ("Fermo lo sviluppo.", "Stoppalo, non deve più continuare.",
                  "Blocca lo sviluppo.", "Interrompi l'agente."):
        verifica(f"politica: «{frase}» ha le parole di ferma",
                 politica.chiesto_con_verbi(cl, frase, {"azione": "ferma"}))
    for frase in ("Mettiamo in pausa.", "Te lo confermo."):
        verifica(f"contrario: «{frase}» non ha le parole di ferma",
                 not politica.chiesto_con_verbi(cl, frase, {"azione": "ferma"}))
    for frase in ("Sì, rifallo.", "Riprova così com'è.", "Partiamo così com'è."):
        verifica(f"politica: «{frase}» ha le parole di rifai",
                 politica.chiesto_con_verbi(cl, frase, {"azione": "rifai"}))
    verifica("valore: ferma E2 come lavoro_annulla, rifai E3 come avanti",
             valore.effetto("sviluppo_passo", {"azione": "ferma"}) == valore.E2
             and valore.effetto("sviluppo_passo", {"azione": "rifai"}) == valore.E3)


# ═══════════════════════════ 2. rifai ═══════════════════════════

def prova_rifai(tmp):
    print("— 2. «sì, rifallo» riparte subito con la stessa specifica")
    cfg, reg, ctx, est, svc, sv, lav = al_lavoro(tmp / "a")
    lav.vincoli = "vincoli del primo lavoro"
    lav.file_iniziali = {"estensione.py": "print(1)"}
    P.chiama(reg, ctx, "sviluppo_passo", {"azione": "ferma"}, turno=3)
    r = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "stato"}, turno=4)
    sosp = r.get("in_sospeso") or {}
    verifica("stato dopo il lavoro fermato: la domanda «lo rifaccio così com'è?» e l'azione in "
             "sospeso dice rifai (prima: «analisi, cambia vuota per rifarlo così»)",
             "lo rifaccio così com'è" in detta(r) and sosp.get("tool") == "sviluppo_passo"
             and "azione = rifai" in str(sosp.get("argomenti"))
             and "cambia = la modifica" in str(sosp.get("argomenti")), json.dumps(r)[:400])
    riga = svc.sviluppi.riga_fase(sv)
    verifica("dati del turno: «sì», «rifallo», «partiamo così com'è» → rifai, senza rileggere "
             "la specifica", "azione rifai" in riga and "senza rilegger" in riga, riga)
    n = len(svc.lavori)
    ctx.regole = []
    r = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "rifai"}, turno=5)
    nuovo = svc.lavori[-1] if len(svc.lavori) > n else None
    verifica("rifai: un lavoro nuovo avviato subito, uguale all'ultimo (compito, vincoli, file, "
             "estensione), senza «Ho capito così»",
             nuovo is not None and nuovo.stato == "in_corso" and nuovo.compito == lav.compito
             and nuovo.vincoli == lav.vincoli and nuovo.file_iniziali == lav.file_iniziali
             and nuovo.estensione == lav.estensione and sv.lavoro == nuovo.id
             and sv.fase == "sviluppo" and sv.nota == "" and "Ho capito così" not in detta(r)
             and "stessa specifica" in detta(r) and "sviluppo_rifai" in ctx.regole,
             json.dumps(r, ensure_ascii=False)[:400])
    svc.finisci(lav, "annullato", messaggio="ho fermato «x».")
    verifica("l'annuncio del lavoro fermato, arrivato dopo il «rifallo», non tocca il lavoro "
             "nuovo", sv.lavoro == nuovo.id and sv.nota == "", f"{sv.lavoro} {sv.nota}")
    n = len(svc.lavori)
    r = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "rifai"}, turno=6)
    verifica("contrario: rifai con l'agente al lavoro → nessun lavoro nuovo (dice a che punto è)",
             len(svc.lavori) == n and "Stiamo sviluppando" in detta(r), detta(r))

    # Il lavoro dell'agente non è andato: «avanti» senza lavoro → la stessa domanda
    nuovo.stato = "errore"
    svc.finisci(nuovo, "errore", motivo="tetto delle passate",
                messaggio="non sono riuscita a finire «x».")
    r = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=7)
    verifica("avanti dopo un lavoro non andato: «non è andato: lo rifaccio così com'è…» con "
             "l'azione in sospeso rifai", "non è andato" in detta(r)
             and "azione = rifai" in str((r.get("in_sospeso") or {}).get("argomenti")), detta(r))
    # Senza l'ultimo lavoro in memoria (un riavvio): dalla specifica dello sviluppo
    svc.lavori.clear()
    r = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "rifai"}, turno=8)
    verifica("rifai dopo un riavvio (nessun lavoro in memoria): un lavoro nuovo dalla specifica "
             "dello sviluppo, avviato", svc.lavori and svc.lavori[-1].stato == "in_corso"
             and sv.lavoro == svc.lavori[-1].id, json.dumps(r, ensure_ascii=False)[:300])

    # Contrario: al collaudo non c'è niente da rifare
    cfg, reg, ctx, est, svc = G3.ambiente(tmp / "b")
    G3.apri(ctx, est, svc, CODICE)
    sv = svc.sviluppi.corrente("u1")
    n = len(svc.lavori)
    r = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "rifai"}, turno=5)
    verifica("contrario: rifai al collaudo → nessun lavoro, «non c'è un lavoro da rifare»",
             len(svc.lavori) == n and sv.fase == "collaudo"
             and "Non c'è un lavoro da rifare" in detta(r), detta(r))


# ═══════════════════════════ 3. più collaudi in una frase ═══════════════════════════

CODICE = '''
def esegui(dati, calliope):
    citta = str(dati.get("citta") or "").strip()
    if citta.lower() == "atlantide":
        raise ValueError("città impossibile")
    return {"da_dire": "A " + citta + " ci sono 18 gradi."}
'''


def prova_collaudi(tmp):
    print("— 3. più valori detti insieme: un collaudo per valore")
    voci = {"Valfiorita e Borgo Alto": ["Valfiorita", "Borgo Alto"],
            "con Valfiorita, Borgo Alto e poi con Pratofiorito":
                ["Valfiorita", "Borgo Alto", "Pratofiorito"],
            "Valfiorita oppure Borgo Alto": ["Valfiorita", "Borgo Alto"],
            "Pratofiorito e Borgo Alto per 3 giorni": ["Pratofiorito", "Borgo Alto per 3 giorni"]}
    for s, atteso in voci.items():
        verifica(f"elenco: «{s}»", ts.valori_elenco(s) == atteso, str(ts.valori_elenco(s)))
    for s in ("Reggio Emilia", "Pratofiorito, 3 giorni", "3 e 5", "Pratofiorito Maggiore",
              "A, B, C, D, E", ""):
        verifica(f"contrario, non è un elenco: «{s}»", ts.valori_elenco(s) == [])

    m = {"input": {"properties": {"citta": {"type": "string"}, "giorni": {"type": "integer"}},
                   "required": ["citta"]}}
    v = ts.piu_valori(m, {"citta": "Valfiorita"}, "Valfiorita e Borgo Alto",
                      {"citta": "Valfiorita"})
    verifica("il caso vero: argomenti con il primo, dati con i due → due collaudi",
             v == [("Valfiorita", {"citta": "Valfiorita"}),
                   ("Borgo Alto", {"citta": "Borgo Alto"})], str(v))
    v = ts.piu_valori(m, {"citta": "Pratofiorito", "giorni": 3},
                      "Pratofiorito e Borgo Alto per 3 giorni",
                      {"citta": "Pratofiorito", "giorni": 3})
    verifica("…con i giorni: valgono per tutti", v and v[1][1] == {"citta": "Borgo Alto",
                                                                   "giorni": 3}, str(v))
    v = ts.piu_valori(m, {"citta": "Borgo Alto"}, "Valfiorita e Borgo Alto",
                      {"citta": "Borgo Alto"})
    verifica("…anche se il modello ha messo il secondo", v and [x[0] for x in v] ==
             ["Valfiorita", "Borgo Alto"], str(v))
    for args, dati, perche in (
            ({"citta": "Bosco e Prato"}, "Bosco e Prato", "il nome intero negli argomenti "
                                                          "(un comune «Bosco e Prato»)"),
            (None, "Bosco e Prato", "solo dati: decide il modello, un collaudo"),
            ({"citta": "Borgo Nuovo"}, "Valfiorita e Borgo Alto", "il valore non è nell'elenco"),
            ({"citta": "Pratofiorito", "giorni": 3}, "Pratofiorito, 3 giorni", "un numero"),
            ({"citta": "Reggio Emilia"}, "Reggio Emilia", "un nome di due parole")):
        passati = ts._argomenti(m, args if args is not None else dati)
        verifica(f"contrario: {perche} → un collaudo solo",
                 ts.piu_valori(m, args, dati, passati) is None)

    # Il collaudo vero, nel docker finto
    cfg, reg, ctx, est, svc = G3.ambiente(tmp / "a")
    G3.apri(ctx, est, svc, CODICE)
    sv = svc.sviluppi.corrente("u1")
    riga = svc.sviluppi.riga_fase(sv)
    verifica("dati del turno al collaudo: un collaudo per valore, mai «aspetto i dati», «e "
             "invece X?» è un collaudo", "un collaudo per valore" in riga
             and "mai che aspetti i dati" in riga and "e invece X?" in riga, riga)
    ctx.regole = []
    r = P.chiama(reg, ctx, "sviluppo_collauda", {"argomenti": {"citta": "Valfiorita"},
                                                 "dati": "Valfiorita e Borgo Alto"}, turno=5)
    testo = json.dumps(r, ensure_ascii=False)
    verifica("il giro vero (20:10): due collaudi, due risultati in fila per il modello",
             len(sv.collaudi) == 2 and [c.get("argomenti") for c in sv.collaudi] ==
             [{"citta": "Valfiorita"}, {"citta": "Borgo Alto"}]
             and "A Valfiorita ci sono 18 gradi" in testo and "A Borgo Alto ci sono 18 gradi"
             in testo and "collaudo_piu_valori" in ctx.regole and "OGNUNA" in testo,
             testo[:600])
    verifica("…ogni collaudo resta a sé nello sviluppo (dati detti, esito)",
             [c.get("dati") for c in sv.collaudi] == ["Valfiorita", "Borgo Alto"]
             and all(c.get("ok") for c in sv.collaudi))
    r = P.chiama(reg, ctx, "sviluppo_collauda", {"argomenti": {"citta": "Valfiorita"},
                                                 "dati": "Valfiorita e Atlantide"}, turno=6)
    testo = json.dumps(r, ensure_ascii=False)
    verifica("uno dei due non va: il riuscito si dice, per l'altro «Lo faccio correggere?» "
             "(in sospeso sviluppo_correggi)", (r.get("in_sospeso") or {}).get("tool") ==
             "sviluppo_correggi" and "Atlantide" in str(r.get("cosa_fare"))
             and "A Valfiorita" in testo and sv.collaudi[-1].get("ok") is False, testo[:600])
    n = len(sv.collaudi)
    ctx.regole = []
    P.chiama(reg, ctx, "sviluppo_collauda", {"dati": "Bosco e Prato"}, turno=7)
    verifica("contrario: solo dati «Bosco e Prato» → un collaudo con il nome intero",
             len(sv.collaudi) == n + 1 and sv.collaudi[-1].get("argomenti") ==
             {"citta": "Bosco e Prato"} and "collaudo_piu_valori" not in ctx.regole)
    P.chiama(reg, ctx, "sviluppo_collauda", {"argomenti": {"citta": "Bosco e Prato"},
                                             "dati": "Bosco e Prato"}, turno=8)
    verifica("contrario: argomenti con il nome intero → un collaudo",
             len(sv.collaudi) == n + 2 and "collaudo_piu_valori" not in ctx.regole)
    # La politica: la chiamata unica ha i dati detti, come sempre
    frase = "Allora, io direi di provare con Valfiorita e Borgo Alto."
    t = politica.Turno(testo=frase)
    d = politica.decidi("sviluppo_collauda", {"argomenti": {"citta": "Valfiorita"},
                                              "dati": "Valfiorita e Borgo Alto"},
                        politica.classe_di("sviluppo_collauda"), t)
    verifica("politica: la chiamata del giro vero, con la conversazione pulita, parte",
             d.esito == "esegui", str(d))
    # Due chiamate (gemma4): la seconda con un valore non detto ma già passato alla prima
    from types import SimpleNamespace
    t = politica.Turno(testo=frase, risposta={})
    c1 = SimpleNamespace(politica=t, regole=[])
    verifica("politica: la prima chiamata (nessun dato ancora) passa e i suoi valori restano",
             politica.bloccata("sviluppo_collauda", c1, {"argomenti": {
                 "citta": "Valfiorita", "giorni": 3}}) is None
             and "3" in t.risposta.get("valori_prima", {}).get("sviluppo_collauda", ()))
    t.letto_ora, t.contaminazione = "estensione", frozenset({"estensione"})
    c2 = SimpleNamespace(politica=t, regole=[])
    verifica("…la seconda con giorni = 3 (non detto, ma della prima) e Borgo Alto detto → parte",
             politica.bloccata("sviluppo_collauda", c2, {"argomenti": {
                 "citta": "Borgo Alto", "giorni": 3}}) is None
             and "dopo_dato_valore_di_prima" in c2.regole, str(c2.regole))
    t.risposta["valori_prima"]["sviluppo_collauda"].add("Valfiorita per 3 giorni")
    verifica("…anche `dati` «Borgo Alto per 3 giorni» con «per 3 giorni» della prima → parte",
             politica.bloccata("sviluppo_collauda", SimpleNamespace(politica=t, regole=[]),
                               {"dati": "Borgo Alto per 3 giorni", "argomenti": {
                                   "citta": "Borgo Alto", "giorni": 3}}) is None)
    t.esterni = [("estensione", "A Valfiorita per 3 giorni: sole.")]
    cl = politica.classe_di("sviluppo_collauda")
    args2 = {"dati": "Borgo Alto per 3 giorni", "argomenti": {"citta": "Borgo Alto", "giorni": 3}}
    d = politica.decidi("sviluppo_collauda", args2, cl, t)
    verifica("…e decidi non lo prende per un argomento dal risultato («per 3 giorni» era della "
             "chiamata di prima)", d.regola != "politica_argomento_esterno", str(d))
    t3 = politica.Turno(testo=frase, risposta={},
                        contaminazione=frozenset({"estensione"}), esterni=list(t.esterni))
    d = politica.decidi("sviluppo_collauda", args2, cl, t3)
    verifica("contrario: senza la chiamata di prima (un turno dopo) «per 3 giorni» viene dal risultato → domanda",
             d.regola == "politica_argomento_esterno", str(d))
    for args, perche in (({"argomenti": {"citta": "Borgo Alto", "giorni": 5}},
                          "un numero né detto né della prima"),
                         ({"argomenti": {"citta": "Borgo Nascosto", "giorni": 3}},
                          "una città presa dal risultato")):
        verifica(f"contrario: {perche} → fermato",
                 politica.bloccata("sviluppo_collauda", SimpleNamespace(politica=t, regole=[]),
                                   args) is not None)
    t2 = politica.Turno(testo=frase, risposta={}, letto_ora="estensione",
                        contaminazione=frozenset({"estensione"}))
    verifica("contrario: senza una chiamata prima del dato, il 3 non detto → fermato",
             politica.bloccata("sviluppo_collauda", SimpleNamespace(politica=t2, regole=[]),
                               {"argomenti": {"citta": "Borgo Alto", "giorni": 3}}) is not None)
    verifica("descrizione di sviluppo_collauda: una chiamata per valore",
             "una chiamata per valore" in next(s for s in ts.sviluppo_specs()
                                               if s.name == "sviluppo_collauda").description)
    verifica("la spinta è nel modulo dello sviluppo (PIU_COLLAUDI)",
             "un collaudo per valore" in SV.PIU_COLLAUDI)


def main():
    global errori
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-giro6-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    G3.ISO = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    t0 = time.monotonic()
    prova_ferma(tmp0 / "ferma")
    prova_rifai(tmp0 / "rifai")
    prova_collaudi(tmp0 / "collaudi")
    print(f"\n({time.monotonic() - t0:.1f} s)")
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
