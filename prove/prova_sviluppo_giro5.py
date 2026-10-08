"""Il giro vero della DGX dell'08/10 sera (18:14–19:05, 26B e qwen3.6), a secco (08/10/2026,
giro 5 della modalità sviluppo; docs/aree/agenti-estensioni.md e sicurezza-politica.md).

Riscritto con nomi di fantasia: «Pratofiorito Maggiore» e «Borgo Alto» per le città di due
parole. La versione nuova del meteo faceva quote_plus(nome) e poi urlencode(params) →
«name=Pratofiorito%2BMaggiore», il geocoder cercava un «+» letterale e rispondeva vuoto; la
traccia lo mostrava, ma l'agente l'ha letto come «%2B is correct for space». Il secondo
collaudo nella stessa frase, passato con `argomenti`, è stato fermato e Calliope ha detto «non
ha risposto». «Chiedi all'agente» trascritto «chiedi alla gente». Il lavoro ripartito
dall'analisi senza i collaudi né la traccia. E qwen3.6 che ripete per centinaia di righe gli
stessi paragrafi nel ragionamento.

1. doppia codifica: l'avviso nella traccia del collaudo, nei vincoli della correzione e
   dell'analisi, nel registro delle uscite e in CalliopeFinta, mai un rifiuto; contrari
   (codifica giusta, «C++», «1+1»); il contratto e il prompt dell'agente;
2. due collaudi nella stessa frase con `argomenti`: i valori dentro l'oggetto (anche numeri
   detti a parole); contrari (un valore dal risultato, un numero non detto, oggetto vuoto);
   il rifiuto del collaudo dice che NON è partito;
3. «la gente» nei dati del turno dello sviluppo (contesto, non regola);
4. il lavoro che riparte dall'analisi durante il collaudo riceve i collaudi con gli argomenti
   e la traccia (con l'avviso); contrario: alla prima analisi niente;
5. il giro a vuoto nel ragionamento: il rilevatore ferma la passata, la spinta, il segnale e il
   passo sulla scheda; contrari (codice lungo con righe simili, tabelle, frasi corte, un
   elenco di frasi diverse); il presence_penalty per tipo di lavoro, solo per vLLM.

    python prove\\prova_sviluppo_giro5.py
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_estensioni as P  # noqa: E402
import prova_sviluppo as S  # noqa: E402
import prova_sviluppo_giro3 as G3  # noqa: E402
from calliope import politica  # noqa: E402
from calliope.estensioni import _ospite  # noqa: E402
from calliope.web import pagina  # noqa: E402
from calliope.web.rete import RetePubblica  # noqa: E402

errori = 0
CITTA = "Pratofiorito Maggiore"          # di fantasia, due parole
ALTRA = "Borgo Alto"


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


# La versione del giro vero: quote_plus e poi urlencode (doppia codifica)
CODICE_DOPPIA = '''
import json
from urllib.parse import quote_plus, urlencode


def esegui(dati, calliope):
    citta = str(dati.get("citta") or "").strip()
    params = {"name": quote_plus(citta), "count": 10, "language": "it"}
    r = calliope.rete_leggi("https://geocoding-api.open-meteo.com/v1/search?"
                            + urlencode(params))
    ris = json.loads(r["testo"]).get("results") or []
    if not ris:
        return {"da_dire": "Non ho trovato " + citta + "."}
    return {"da_dire": "A " + citta + " ci sono 18 gradi."}
'''
CODICE_GIUSTO = CODICE_DOPPIA.replace('quote_plus(citta)', 'citta')


# ═══════════════════════════ 1. doppia codifica ═══════════════════════════

def prova_doppia(tmp):
    print("— 1. la doppia codifica: avviso, mai rifiuto")
    doppie = {
        "https://geocoding-api.open-meteo.com/v1/search?name=Pratofiorito%2BMaggiore&count=10":
            "«%2B» è un «+» letterale",
        "https://sito.it/cerca?q=Borgo%2520Alto": "«%25» è un «%» letterale",
    }
    for url, atteso in doppie.items():
        m = pagina.doppia_codifica(url)
        verifica(f"avviso: {url[-40:]}", m.startswith("possibile doppia codifica")
                 and atteso in m and "urlencode" in m and "parametro «" in m
                 and "Pratofiorito" not in m and "Borgo" not in m, m)
    for url in ("https://sito.it/cerca?name=Pratofiorito+Maggiore&count=10",
                "https://sito.it/cerca?name=Pratofiorito%20Maggiore",
                "https://sito.it/cerca?q=C%2B%2B", "https://sito.it/calcola?q=1%2B1",
                "https://sito.it/cerca?q=%C3%A0", "https://sito.it", "https://sito.it/a?b="):
        verifica(f"contrario, nessun avviso: {url[-36:]}", pagina.doppia_codifica(url) == "")
    tutte = list(doppie) + ["https://sito.it/cerca?q=C%2B%2B", "https://a.it/x?n=a%2Bb"]
    verifica("la regola di CalliopeFinta è la stessa della porta",
             all(_ospite.doppia_codifica(u) == pagina.doppia_codifica(u) for u in tutte))
    finta = _ospite.CalliopeFinta(risposte={"rete_leggi": {"stato": 200, "testo": "{}"}})
    r = finta.rete_leggi("https://sito.it/cerca?name=Pratofiorito%2BMaggiore")
    verifica("CalliopeFinta: la richiesta doppia non si rifiuta, l'avviso resta in `avvisi`",
             r["stato"] == 200 and len(finta.avvisi) == 1
             and "doppia codifica" in finta.avvisi[0], str(finta.avvisi))
    finta.rete_leggi("https://sito.it/cerca?name=Pratofiorito+Maggiore")
    verifica("…con la codifica giusta niente avviso", len(finta.avvisi) == 1)

    # Il collaudo vero: la porta, la traccia, il registro delle uscite
    cfg, reg, ctx, est, svc = G3.ambiente(tmp)
    G3.apri(ctx, est, svc, CODICE_DOPPIA)
    svs = svc.sviluppi
    sv = svs.corrente("u1")
    out = P.chiama(reg, ctx, "sviluppo_collauda", {"argomenti": {"citta": CITTA}}, turno=5)
    c = sv.collaudi[-1]
    r0 = (c.get("rete") or [{}])[0]
    verifica("il collaudo con «Pratofiorito Maggiore»: la richiesta parte (stato 200), il "
             "geocoder non trova il «+» letterale, la traccia ha l'avviso",
             "Non ho trovato" in json.dumps(out, ensure_ascii=False)
             and r0.get("esito") == "stato 200" and "%2B" in r0.get("url", "")
             and "doppia codifica" in r0.get("avviso", ""),
             json.dumps(c, ensure_ascii=False)[:600])
    verifica("…l'avviso non arriva al modello della voce",
             "doppia codifica" not in json.dumps(out, ensure_ascii=False))
    righe = [json.loads(x) for x in (tmp / "uscite.jsonl").read_text(encoding="utf-8")
             .splitlines()]
    verifica("…nel registro delle uscite «fatta» con l'avviso e il nome del parametro, senza "
             "la città", any(r.get("esito") == "fatta" and r.get("avviso") ==
                             "possibile doppia codifica nel parametro «name»" for r in righe)
             and "Pratofiorito" not in json.dumps(righe, ensure_ascii=False),
             json.dumps(righe[-1:], ensure_ascii=False))
    testo = svs.testo_per_agente(sv)
    verifica("sviluppo_chiedi: nel contesto dell'agente l'avviso in chiaro",
             "ATTENZIONE: possibile doppia codifica" in testo and "letterale" in testo,
             testo[-600:])
    ctx.tool_in_sospeso = "sviluppo_correggi"
    P.chiama(reg, ctx, "sviluppo_correggi", {"problema": f"{CITTA} non la trova"}, turno=6)
    ctx.tool_in_sospeso = None
    v = svc.lavori[-1].vincoli
    verifica("sviluppo_correggi: nei vincoli l'avviso in testa alla traccia («%2B» è un «+» "
             "letterale, lo spazio è «+» o «%20»)",
             "ATTENZIONE, dalla porta di Calliope: possibile doppia codifica" in v
             and "lo spazio è «+» o «%20»" in v and "quote_plus e poi urlencode" in v, v[-900:])

    # Contrario: con urlencode soltanto, nessun avviso
    cfg2, reg2, ctx2, est2, svc2 = G3.ambiente(tmp / "giusto")
    G3.apri(ctx2, est2, svc2, CODICE_GIUSTO)
    sv2 = svc2.sviluppi.corrente("u1")
    out = P.chiama(reg2, ctx2, "sviluppo_collauda", {"argomenti": {"citta": CITTA}}, turno=5)
    r0 = (sv2.collaudi[-1].get("rete") or [{}])[0]
    verifica("contrario: codificato una volta sola «Pratofiorito Maggiore» va, niente avviso",
             "18 gradi" in json.dumps(out, ensure_ascii=False) and "avviso" not in r0
             and "ATTENZIONE" not in svc2.sviluppi.testo_traccia(sv2), json.dumps(r0)[:300])

    from calliope.estensioni import contratto
    from calliope.estensioni.prompt import SISTEMA_ESTENSIONE as SIS
    cfgc = SimpleNamespace(estensioni_rete_max_minuto=30)
    verifica("il contratto (CAPACITA.md) e il prompt dell'agente: «codifica una volta sola»",
             "Codifica una volta sola" in contratto.testo(cfgc) and "una volta sola" in SIS
             and "%2B" in SIS)


# ═══════════════════════════ 2. due collaudi con `argomenti` ═══════════════════════════

def prova_argomenti():
    print("— 2. due collaudi nella stessa frase, con `argomenti`")
    frase = (f"Direi bene, ora aggiungiamo questa prova. Prova con {CITTA} e poi con {ALTRA} "
             "per due giorni.")
    ctx = SimpleNamespace(politica=politica.Turno(testo=frase, letto_ora="estensione",
                                                  contaminazione={"estensione"}), regole=[])
    ok = politica.bloccata("sviluppo_collauda", ctx, {"argomenti": {"citta": ALTRA}})
    verifica("il caso della DGX (18:21): il secondo collaudo con `argomenti` detti → parte",
             ok is None and "dopo_dato_valore_detto" in ctx.regole)
    verifica("…anche con i giorni detti a parole («per due giorni» → 2)",
             politica.bloccata("sviluppo_collauda", ctx,
                               {"argomenti": {"citta": ALTRA, "giorni": 2}}) is None)
    verifica("…anche `argomenti` come testo JSON e con `dati` uguali",
             politica.bloccata("sviluppo_collauda", ctx,
                               {"argomenti": json.dumps({"citta": ALTRA}),
                                "dati": ALTRA}) is None)
    t2 = politica.Turno(testo=f"Prova con {CITTA} e poi con Borgo Altto.",
                        letto_ora="estensione", contaminazione={"estensione"})
    verifica("…una storpiatura della trascrizione (`provenienza.vicina`) vale come detta",
             politica.bloccata("sviluppo_collauda", SimpleNamespace(politica=t2, regole=[]),
                               {"argomenti": {"citta": "Pratofiorito Maggiore"}}) is None)
    d = politica.decidi("sviluppo_collauda", {"argomenti": {"citta": ALTRA}},
                        politica.classe_di("sviluppo_collauda"), ctx.politica)
    verifica("…e decidi non lo blocca", d.regola != "web_azione_bloccata", str(d))
    for args, perche in (
            ({"argomenti": {"citta": "Borgo Nascosto"}}, "un valore preso dal risultato"),
            ({"argomenti": {"citta": ALTRA, "giorni": 5}}, "un numero non detto"),
            ({"argomenti": {}}, "oggetto vuoto"),
            ({"argomenti": {"citta": ALTRA}, "dati": "Borgo Nascosto"},
             "`argomenti` detti ma `dati` dal risultato")):
        r = politica.bloccata("sviluppo_collauda", ctx, args)
        verifica(f"contrario: {perche} → fermato", r is not None, json.dumps(args))
    r = politica.bloccata("sviluppo_collauda", ctx, {"argomenti": {"citta": "Borgo Nascosto"}})
    verifica("il rifiuto del collaudo dice che NON è partito, e di non dire «non ha risposto»",
             r.get("partito") is False and "NON è partito" in r["motivo"]
             and "non ha risposto" in r["cosa_fare"] and r["motivo"] in politica.MOTIVI_DOPO_DATO,
             json.dumps(r, ensure_ascii=False))
    r = politica.bloccata("lista_aggiungi", ctx, {"cose": ALTRA})
    verifica("contrario: un'altra azione → il rifiuto di sempre (dopo una ricerca…)",
             r is not None and r["motivo"] == politica.BLOCCO_DOPO_DATO["motivo"])


# ═══════════════════════════ 3. «la gente» ═══════════════════════════

def prova_gente(tmp):
    print("— 3. «chiedi alla gente» nei dati del turno dello sviluppo")
    cfg, reg, ctx, est, svc = G3.ambiente(tmp)
    G3.apri(ctx, est, svc, CODICE_GIUSTO)
    sv = svc.sviluppi.corrente("u1")
    msg = svc.sviluppi.dati_turno(sv)
    verifica("SVILUPPO_MSG: «la gente» è spesso «l'agente», le domande sul codice a "
             "sviluppo_chiedi, mai dire di averla registrata senza il tool",
             "«chiedi alla gente…»" in msg and "sviluppo_chiedi" in msg
             and "senza averla fatta con il tool" in msg and "chiedi alla gente" in msg, msg)
    from calliope.sviluppo import SVILUPPO_MSG
    verifica("…è un contesto dei dati del turno (nessuna regola sul testo)",
             "la gente" in SVILUPPO_MSG and "la gente" not in Path(
                 politica.__file__).read_text(encoding="utf-8"))


# ═══════════════════════════ 4. analisi durante il collaudo ═══════════════════════════

def prova_analisi(tmp):
    print("— 4. il lavoro che riparte dall'analisi riceve i collaudi e la traccia")
    cfg, reg, ctx, est, svc = G3.ambiente(tmp)
    lav0 = G3.apri(ctx, est, svc, CODICE_DOPPIA)
    verifica("contrario: alla prima analisi niente collaudi nei vincoli",
             "Collaudi della versione" not in (lav0.vincoli or ""))
    sv = svc.sviluppi.corrente("u1")
    P.chiama(reg, ctx, "sviluppo_collauda", {"argomenti": {"citta": "Bergamo"}}, turno=5)
    P.chiama(reg, ctx, "sviluppo_collauda", {"argomenti": {"citta": CITTA}}, turno=6)
    n = len(svc.lavori)
    out = P.chiama(reg, ctx, "sviluppo_passo", {
        "azione": "analisi", "cambia": "i nomi delle città vanno codificati"}, turno=7)
    lav = (svc.offerte.get("u1") or {}).get("lavoro")
    v = getattr(lav, "vincoli", "") or ""
    verifica("il caso della DGX (18:21:52): la diagnosi passata all'analisi → il lavoro nuovo "
             "ha i collaudi della versione provata, con gli argomenti e gli esiti",
             lav is not None and len(svc.lavori) >= n and "Collaudi della versione che la "
             "persona ha provato" in v and f"«citta: {CITTA}»" in v
             and "argomenti passati" in v and "Non ho trovato" in v,
             json.dumps(out, ensure_ascii=False)[:300] + " / " + v[-900:])
    verifica("…e la traccia di rete con l'avviso della doppia codifica in chiaro",
             "Traccia di rete dei collaudi" in v
             and "ATTENZIONE, dalla porta di Calliope: possibile doppia codifica" in v, v[-900:])
    f = (getattr(lav, "file_iniziali", None) or {}).get("estensione.py", "")
    f = f.decode("utf-8", "replace") if isinstance(f, bytes) else str(f)
    verifica("…e i file della versione provata (la candidata) nella cartella",
             "quote_plus" in f, f[:200])
    verifica("…il cambiamento chiesto resta nei vincoli",
             "i nomi delle città vanno codificati" in v)


# ═══════════════════════════ 5. il giro a vuoto nel ragionamento ═══════════════════════════

PARAGRAFO = ("La soluzione più semplice è:\n"
             "1. Aggiungere il parametro paese nel manifesto\n"
             "2. Modificare la logica di ricerca per dare priorità ai comuni italiani\n"
             "3. Se non trova con il nome completo, provare con la prima parola\n\n"
             "Ma il compito non specifica di aggiungere un altro servizio. Quindi devo "
             "limitarmi a modificare la logica di ricerca.\n\n")


def _scorri(rip, testo, passo=7):
    for k in range(0, len(testo), passo):
        if rip.aggiungi(testo[k:k + passo]):
            return k
    return None


class _ClienteFinto:
    """Uno stream finto: pezzi di ragionamento e di testo, `controlla` a ogni pezzo."""

    def __init__(self, pezzi, chiamate=()):
        self.pezzi, self.chiamate, self.letti, self.corpi = list(pezzi), list(chiamate), 0, []
        self.url = None

    def chat(self, body, su_pezzo=None, controlla=None, su_flusso=None):
        self.corpi.append(body)
        out = {"content": "", "thinking": "", "tool_calls": [], "eval": 0, "prompt": 0, "s": 0}
        for tipo, t in self.pezzi:
            if controlla is not None:
                controlla()
            self.letti += 1
            out["thinking" if tipo == "pensiero" else "content"] += t
            if su_flusso is not None:
                su_flusso(tipo, t)
        out["tool_calls"] = list(self.chiamate)
        out["eval"] = len(out["thinking"] + out["content"]) // 4
        return out


def prova_ripetizioni():
    print("— 5. il giro a vuoto nel ragionamento")
    from calliope.agenti.arbitro import Arbitro
    from calliope.agenti.ciclo import (Agente, Lavoro, RIPETIZIONI_MAX, _spinta_ripetizioni,
                                       segnali_giro)
    from calliope.agenti.remoto_openai import traduci_corpo
    from calliope.agenti.ripetizioni import Ripetizioni, spinta
    from calliope.config import Config

    rip = Ripetizioni(8)
    k = _scorri(rip, "Devo capire il problema.\n\n" + PARAGRAFO * 30)
    verifica("il caso della DGX (la stessa riga 58 volte): scatta all'ottava ripetizione, "
             "molto prima della fine", k is not None and k < len(PARAGRAFO) * 9
             and bool(rip.scattato), f"{k} {rip.scattato!r}")
    rip = Ripetizioni(8)
    riga = ("Ma la persona ha detto che il problema è che il geocoder non trova risultati per i "
            "nomi composti. ")
    verifica("…anche le frasi ripetute di seguito su una riga sola",
             _scorri(rip, riga * 40) is not None, rip.scattato)
    rip = Ripetizioni(8)
    verifica("…sette volte non bastano", _scorri(rip, PARAGRAFO * 7) is None)

    codice = "```python\n" + "".join(
        f'    self.assertEqual(esegui({{"citta": "Borgo {i}"}}, finta)["da_dire"], '
        f'"A Borgo {i} ci sono 18 gradi.")\n' for i in range(40)) * 3 + "```\n"
    codice_nudo = "".join(
        f'risultato = calliope.rete_leggi(url_per_la_citta_numero_{i % 3})  # la stessa\n'
        f"if not risultato: return {{'da_dire': 'Non ho trovato la città richiesta.'}}\n"
        for i in range(60))
    tabella = "| Città | Gradi | Cielo |\n|---|---|---|\n" + "".join(
        "| Borgo Alto | 18 | sereno con qualche nuvola nel pomeriggio |\n" for _ in range(30))
    corte = "Leggo il file.\nOk.\n" * 50
    elenco = "".join(f"Il test numero {i} controlla la città di Borgo {i} con il nome intero.\n"
                     for i in range(60))
    for nome, testo in (("codice lungo con righe simili (in un blocco ```)", codice),
                        ("codice senza blocco, righe uguali", codice_nudo),
                        ("una tabella con righe uguali", tabella),
                        ("frasi corte ripetute", corte),
                        ("un elenco lungo di frasi diverse", elenco)):
        rip = Ripetizioni(8)
        verifica(f"contrario: {nome} → non scatta", _scorri(rip, testo) is None, rip.scattato)

    # La passata vera del ciclo, con uno stream finto che ripete i paragrafi
    cfg = Config()
    cfg.agenti_num_ctx = 32768
    imp = SimpleNamespace(modello="qwen-finto", modello_scrittore="qwen-finto", motore="openai")
    log = []
    pezzi = [("pensiero", PARAGRAFO)] * 60 + [("testo", "fine")]
    cli = _ClienteFinto(pezzi)
    ag = Agente(cfg, imp, cli, Arbitro(False, 0), log=log.append)
    lav = Lavoro("L9", "estensione", "il meteo per città")
    eventi = []
    lav.osservatore = lambda lv, ev, dati: eventi.append((ev, dict(dati)))
    strumenti = [{"type": "function", "function": {"name": "scrivi_file", "parameters": {}}}]
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "Compito: x"}]
    out = ag.passata(lav, msgs, tools=strumenti)
    verifica("la passata si ferma presto (lo stream chiuso), torna come giro a vuoto",
             out.get("giro_a_vuoto") and cli.letti < 15 and out["tool_calls"] == []
             and lav.passi == 1 and lav.token > 0, f"letti {cli.letti}, {out}")
    verifica("…il segnale, la regola nel log, il passo sulla scheda",
             lav.segnali.get("ripetizioni") == 1
             and any("agente_ragionamento_ripetuto" in x for x in log)
             and any(ev == "flusso" and "girava a vuoto" in d.get("testo", "")
                     for ev, d in eventi)
             and any(ev == "spinta" and d.get("regola") == "agente_ragionamento_ripetuto"
                     for ev, d in eventi), f"{log} {eventi[-3:]}")
    _spinta_ripetizioni(msgs, out["giro_a_vuoto"])
    verifica("…la spinta in coda al messaggio della persona (mai due «user» di fila)",
             len(msgs) == 2 and "stai ripetendo lo stesso ragionamento" in msgs[-1]["content"]
             and "chiama uno strumento" in msgs[-1]["content"], msgs[-1]["content"][-300:])
    msgs.append({"role": "tool", "tool_name": "leggi_file", "content": "{}"})
    _spinta_ripetizioni(msgs, "")
    verifica("…dopo il risultato di uno strumento, un messaggio nuovo",
             msgs[-1]["role"] == "user" and msgs[-1]["content"] == spinta(""))
    seg = segnali_giro(lav, 24)
    verifica("…e alla tappa «sembra girare a vuoto: ha ripetuto lo stesso ragionamento»",
             seg["a_vuoto"] and any("ripetuto lo stesso ragionamento" in f for f in seg["frasi"]),
             str(seg))
    verifica("alla terza passata fermata di fila il lavoro si chiude", RIPETIZIONI_MAX == 3)

    cli = _ClienteFinto([("pensiero", "Scrivo il file adesso.\n")] * 5,
                        chiamate=[{"name": "scrivi_file", "arguments": {}}])
    ag = Agente(cfg, imp, cli, Arbitro(False, 0), log=log.append)
    out = ag.passata(Lavoro("L10", "estensione", "x"), msgs[:2], tools=strumenti)
    verifica("contrario: una passata normale torna intera, con la chiamata",
             not out.get("giro_a_vuoto") and out["tool_calls"] and cli.letti == 5)
    cli = _ClienteFinto([("pensiero", PARAGRAFO)] * 20)
    ag = Agente(cfg, imp, cli, Arbitro(False, 0), log=log.append)
    out = ag.passata(Lavoro("L11", "altro", "x"), msgs[:2])
    verifica("contrario: senza strumenti (il testo è il risultato) il rilevatore è spento",
             not out.get("giro_a_vuoto") and cli.letti == 20)
    cfg0 = Config()
    cfg0.agenti_num_ctx = 32768
    cfg0.agenti_ripetizioni_max = 0
    cli = _ClienteFinto([("pensiero", PARAGRAFO)] * 20)
    out = Agente(cfg0, imp, cli, Arbitro(False, 0), log=log.append).passata(
        Lavoro("L12", "codice", "x"), msgs[:2], tools=strumenti)
    verifica("contrario: agenti_ripetizioni_max = 0 lo spegne", not out.get("giro_a_vuoto"))

    print("— 5b. presence_penalty per tipo di lavoro")
    pp = cfg.agenti_presence_penalty
    verifica("Config: 0 per codice ed estensioni (scheda di Qwen3.6, «precise coding»), 1,5 "
             "per ricerche, documenti e altro",
             pp.get("codice") == 0 and pp.get("estensione") == 0 and pp.get("ricerca") == 1.5
             and pp.get("documento") == 1.5 and pp.get("altro") == 1.5, str(pp))
    cli = _ClienteFinto([("testo", "ok")])
    ag = Agente(cfg, imp, cli, Arbitro(False, 0), log=log.append)
    ag.passata(Lavoro("L13", "ricerca", "x"), msgs[:2])
    ag.passata(Lavoro("L14", "codice", "x"), msgs[:2])
    verifica("una ricerca lo manda (1,5), il codice no",
             cli.corpi[0].get("presence_penalty") == 1.5
             and "presence_penalty" not in cli.corpi[1], str([c.get("presence_penalty")
                                                              for c in cli.corpi]))
    req = traduci_corpo(dict(cli.corpi[0]))
    verifica("vLLM (API OpenAI): presence_penalty nella richiesta",
             req.get("presence_penalty") == 1.5, str(req.get("presence_penalty")))
    from calliope.agenti.remoto import ClienteOllama
    visti = []
    co = ClienteOllama.__new__(ClienteOllama)
    co.senza_think = set()
    co._chat = lambda body, *a, **k: visti.append(body) or {}
    co.chat(dict(cli.corpi[0]))
    verifica("Ollama: non si manda (stesso modello della voce, niente ricarichi)",
             visti and "presence_penalty" not in visti[0], str(visti[:1])[:200])


ISO = None


def main():
    global ISO
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-giro5-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    ISO = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    G3.ISO = ISO
    t0 = time.monotonic()
    prova_doppia(tmp0 / "doppia")
    prova_argomenti()
    prova_gente(tmp0 / "gente")
    prova_analisi(tmp0 / "analisi")
    prova_ripetizioni()
    print(f"\n({time.monotonic() - t0:.1f} s)")
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
