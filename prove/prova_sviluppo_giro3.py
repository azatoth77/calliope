"""Il giro vero della DGX dell'08/10 pomeriggio (14:36–15:47, 26B e qwen3.6), a secco
(08/10/2026, giro 3 della modalità sviluppo; docs/aree/agenti-estensioni.md e
sicurezza-politica.md).

Riscritto con nomi di fantasia: lo sviluppo del meteo per città; l'estensione costruiva l'URL
del geocoder a mano («…/search?name={citta}»), una città di una parola andava e una di due
(«Pratofiorito Maggiore», al posto di quelle vere) no; in cinque versioni l'agente non ha mai
visto la causa (nella sandbox non ha rete, e il collaudo gli passava solo «non ho trovato il
meteo»). Poi «Cerno Maggiore» trascritto e «Cerro Maggiore» nel valore → «viene dal lavoro di
un agente, non da te»; dopo la sfida «Fatto.» senza l'esito; due collaudi nella stessa frase,
il secondo fermato dal primo; un «ok» in coda a una frase storpiata come consenso; la modifica
di un'estensione diventata un'estensione nuova; «ne abbiamo solo una»; «non posso rinominare».

1. la porta rifiuta un URL non codificato con l'errore per chi scrive il codice (anche
   CalliopeFinta e la funzione finta delle prove), il registro delle uscite lo scrive senza il
   percorso; contrari: URL codificati;
2. la traccia di rete del collaudo: nello sviluppo (URL com'era, errore, inizio della risposta,
   durata), mai al modello della voce; in sviluppo_chiedi e nei vincoli di sviluppo_correggi;
   ripulita da dati riservati e, dopo una lettura di dati di casa, dai valori;
3. provenienza: una storpiatura della trascrizione vale come detta; contrari (cifre, parole
   corte, iniziale diversa, un valore davvero dal dato);
4. due collaudi nella stessa frase: il secondo, con i dati detti, non si ferma; contrari;
5. dopo la sfida l'esito vero del tool (lo dice il modello), mai «Fatto.» con un risultato;
6. consenso: un «ok» in coda a un pezzo lungo non vale; contrari;
7. sviluppo_apri con un nome simile e senza modifica: la scelta al modello, niente lavoro;
8. l'elenco vero delle estensioni nei dati del turno quando la frase ne parla;
9. estensione_gestisci rinomina: senza agente, con il titolo detto anche con un dato di mezzo;
   un titolo già di un'altra attiva → la proposta di disattivarla.

    python prove\\prova_sviluppo_giro3.py
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_estensioni as P  # noqa: E402
import prova_sviluppo as S  # noqa: E402
import prova_sviluppo_v2 as V  # noqa: E402
from calliope import politica  # noqa: E402
from calliope import provenienza as prov  # noqa: E402
from calliope.estensioni import _ospite  # noqa: E402
from calliope.estensioni.porta import url_per_traccia  # noqa: E402
from calliope.tools import estensioni as te  # noqa: E402
from calliope.tools.spec import ToolSpec  # noqa: E402
from calliope.web import pagina  # noqa: E402
from calliope.web.rete import RetePubblica  # noqa: E402

errori = 0


# ── una Brain minima con la frase di sfida (come prove/prova_conferme.py) ──
class _Prof:
    def __init__(self, nome, admin=False):
        self.name, self.id, self.admin = nome, nome.lower() + "-id", admin


class _Persone:
    def __init__(self):
        from calliope.config import Config
        self.cfg = Config()
        self.users = {"Dario": _Prof("Dario", True)}

    def get(self, n):
        return self.users.get(n)


class _Backend:
    def __init__(self, copione):
        self.copione, self.visti = list(copione), []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        yield from (self.copione.pop(0) if self.copione else [("text", "Ok.")])


def _brain(copione, tool):
    from calliope.brain import Brain
    from calliope.speaker_id import SpeakerContext
    from calliope.tools.registry import ToolRegistry
    from calliope.tools.spec import ToolContext
    p = _Persone()
    b = Brain.__new__(Brain)
    reg = ToolRegistry()
    reg.register(tool)
    b.cfg, b.tools, b.history = p.cfg, reg, []
    sc = SpeakerContext(p)
    b.tool_ctx = ToolContext(cfg=p.cfg, speakers=p, speaker_ctx=sc, speaker=None)
    b.backend = _Backend(copione)
    sc.identified_by, sc.from_session, sc.current_speaker = "voce", False, "Dario"
    sc.aggiorna_conversazione("Dario", "voce", True, 0.7)
    from calliope import conferme as C
    sf = C.nuova_sfida(b.cfg, "dario-id", tool.name, {"dati": CITTA})
    sf.parole, sf.numero = ("girasole", "treno", "limone"), 42
    sf.scade = time.monotonic() + 60
    sc.sfida = sf
    return b


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


CITTA = "Pratofiorito Maggiore"          # di fantasia, due parole
GEO = {"bergamo": (45.69, 9.67), "pratofiorito maggiore": (45.61, 8.95)}

# La candidata del giro vero: l'URL scritto a mano; un errore della porta diventa «non ho
# trovato il meteo» (per il codice il collaudo riesce: lo giudica la persona)
CODICE_MANO = '''
import json
from calliope_estensione import ErroreCalliope


def esegui(dati, calliope):
    citta = str(dati.get("citta") or "").strip()
    url = ("https://geocoding-api.open-meteo.com/v1/search?name=" + citta
           + "&count=1&language=it&format=json")
    try:
        r = calliope.rete_leggi(url)
        ris = json.loads(r["testo"]).get("results") or []
    except ErroreCalliope:
        return {"da_dire": "Non ho trovato il meteo per " + citta + "."}
    if not ris:
        return {"da_dire": "Non ho trovato " + citta + "."}
    return {"da_dire": "A " + citta + " ci sono 18 gradi."}
'''
# La correzione: i parametri codificati
CODICE_CODIFICATO = CODICE_MANO.replace(
    '''    url = ("https://geocoding-api.open-meteo.com/v1/search?name=" + citta
           + "&count=1&language=it&format=json")''',
    '''    from urllib.parse import urlencode
    url = ("https://geocoding-api.open-meteo.com/v1/search?"
           + urlencode({"name": citta, "count": 1, "language": "it", "format": "json"}))''')


def geocoder_finto(url, **kw):
    """Il geocoder: la query decodificata come farebbe il sito; un URL con uno spazio non
    arriva mai qui (la porta lo ferma prima)."""
    assert " " not in url, "un URL con uno spazio non deve partire"
    q = parse_qs(urlsplit(url).query)
    nome = (q.get("name") or [""])[0].lower()
    ris = [{"latitude": GEO[nome][0], "longitude": GEO[nome][1]}] if nome in GEO else []
    testo = json.dumps({"results": ris})
    return {"url": url, "tipo": "application/json", "byte": len(testo), "rimandi": 0,
            "testo_grezzo": testo}


def ambiente(tmp):
    cfg, reg, ctx, est, svc = V.ambiente(tmp, ISO)
    est.rete = RetePubblica(cfg, tmp / "uscite.jsonl", scarica=geocoder_finto, log=lambda *a: 0)
    ctx.registro = reg
    return cfg, reg, ctx, est, svc


def candidata(est, codice, lav_id="L1"):
    mv = P.valida(S.M2)
    return est.archivio.nuova_candidata(mv, {"estensione.py": codice.encode()}, "Dario",
                                        {"eseguiti": 4, "falliti": 0},
                                        {"rischi": [], "sintassi": []}, lav_id, True)


def apri(ctx, est, svc, codice):
    """La richiesta, il «sì», il lavoro finito con la candidata data: siamo al collaudo."""
    ctx.turno = 1
    S.P.chiama(ctx.registro, ctx, "sviluppo_apri", {
        "tipo": "estensione", "compito": "un'estensione che dica il meteo di una città "
                                          "qualunque", "modifica": "meteo_citta"})
    lav = svc.offerte["u1"]["lavoro"]
    S.P.chiama(ctx.registro, ctx, "sviluppo_apri", {"proposta": lav.id}, turno=2)
    n = candidata(est, codice, lav.id)
    V.contesto_finto(lav)
    svc.sviluppi.conserva(lav)
    svc.finisci(lav, "fatto", estensione={"nome": "meteo_citta", "versione": n},
                test={"eseguiti": 4, "falliti": 0}, messaggio="ho preparato l'estensione")
    return lav


# ═══════════════════════════ 1. URL non codificato ═══════════════════════════

def prova_url():
    print("— 1. la porta rifiuta un URL non codificato")
    casi = {
        "https://geocoding-api.open-meteo.com/v1/search?name=Pratofiorito Maggiore&count=1":
            "parametro «name»",
        "https://sito.it/città/meteo": "nel percorso",
        "https://sito.it/x?q=50%": "«%»",
        "https://sito.it/x?q=a\tb": "carattere di controllo",
    }
    for url, atteso in casi.items():
        m = pagina.url_non_codificato(url)
        verifica(f"rifiutato: {url[:60]!r} → {atteso}", m.startswith("URL non valido")
                 and atteso in m and "urlencode" in m and "Maggiore" not in m, m)
    for url in ("https://geocoding-api.open-meteo.com/v1/search?name=Pratofiorito%20Maggiore",
                "https://sito.it/x?name=Pratofiorito+Maggiore&a=1",
                "https://xn--citt-1ra.it/x?q=%C3%A0", "https://sito.it/a/b;c=1?x=(1)#frammento",
                "https://sito.it"):
        verifica(f"contrario, codificato: {url[:60]}", pagina.url_non_codificato(url) == "")
    verifica("la regola di CalliopeFinta è la stessa della porta",
             all(_ospite.url_non_codificato(u) == pagina.url_non_codificato(u)
                 for u in list(casi) + ["https://a.it/x?q=%41", "https://a.it/x y"]))
    finta = _ospite.CalliopeFinta(risposte={"rete_leggi": {"stato": 200, "testo": "{}"}})
    try:
        finta.rete_leggi("https://sito.it/cerca?name=Pratofiorito Maggiore")
        alzata = ""
    except _ospite.ErroreCalliope as e:
        alzata = str(e)
    verifica("CalliopeFinta: un test dell'agente con «Pratofiorito Maggiore» fallisce come nel "
             "vero", alzata.startswith("rete: URL non valido"), alzata)
    verifica("…e con l'URL codificato risponde come sempre",
             finta.rete_leggi("https://sito.it/cerca?name=Pratofiorito%20Maggiore")["stato"]
             == 200)
    with tempfile.TemporaryDirectory() as d:
        rete = RetePubblica(None, Path(d) / "uscite.jsonl", scarica=geocoder_finto,
                            log=lambda *a: 0)
        try:
            rete.richiesta("https://geocoding-api.open-meteo.com/v1/search?name=Prato Maggiore",
                           {"origine": "agente", "lavoro": "L1"})
            msg = ""
        except pagina.PaginaVietata as e:
            msg = str(e)
        riga = json.loads((Path(d) / "uscite.jsonl").read_text(encoding="utf-8")
                          .splitlines()[-1])
        verifica("RetePubblica (anche per l'agente): rifiutata prima di partire, nel registro "
                 "«bloccata: url_non_codificato» senza percorso né valori",
                 msg.startswith("URL non valido") and riga["esito"] == "bloccata"
                 and riga["motivo"] == "url_non_codificato" and "Maggiore" not in json.dumps(
                     riga), json.dumps(riga, ensure_ascii=False))
    from calliope.estensioni import contratto
    from calliope.estensioni.prompt import SISTEMA_ESTENSIONE as SIS
    cfg = SimpleNamespace(estensioni_rete_max_minuto=30)
    verifica("il contratto (CAPACITA.md) e il prompt dell'agente lo dicono",
             "urlencode" in contratto.testo(cfg) and "urlencode" in SIS
             and "CalliopeFinta" in SIS)


# ═══════════════════════════ 2. traccia di rete del collaudo ═══════════════════════════

def prova_traccia(tmp):
    print("— 2. la traccia di rete del collaudo, per l'agente")
    cfg, reg, ctx, est, svc = ambiente(tmp)
    apri(ctx, est, svc, CODICE_MANO)
    svs = svc.sviluppi
    sv = svs.corrente("u1")
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_collauda", {"dati": "Bergamo"}, turno=5)
    c = sv.collaudi[-1]
    verifica("«Bergamo» (una parola) va: la traccia ha la richiesta con «stato 200» e l'inizio "
             "della risposta", "18 gradi" in json.dumps(out, ensure_ascii=False)
             and c["rete"][0]["esito"] == "stato 200" and "results" in c["rete"][0]["inizio"]
             and c["rete"][0]["metodo"] == "GET", json.dumps(c, ensure_ascii=False)[:400])
    verifica("la traccia non arriva al modello della voce",
             "_traccia_rete" not in json.dumps(out) and "geocoding-api" not in json.dumps(out))
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_collauda", {"dati": CITTA}, turno=6)
    c = sv.collaudi[-1]
    r0 = (c.get("rete") or [{}])[0]
    verifica("«Pratofiorito Maggiore»: per il codice riesce («non ho trovato»), ma la traccia "
             "dice la causa: l'URL com'era, con lo spazio, e l'errore della porta",
             c["ok"] and "Non ho trovato il meteo" in c["esito"]
             and f"name={CITTA}&count=1" in r0.get("url", "") and r0.get("esito") == "errore"
             and "URL non valido: c'è uno spazio nel parametro «name»" in r0.get("errore", ""),
             json.dumps(c, ensure_ascii=False)[:500])
    righe = [json.loads(x) for x in (tmp / "uscite.jsonl").read_text(encoding="utf-8")
             .splitlines()]
    verifica("…nel registro delle uscite «bloccata: url_non_codificato», senza la città",
             any(r.get("motivo") == "url_non_codificato" and r.get("esito") == "bloccata"
                 for r in righe) and "Pratofiorito" not in json.dumps(righe), str(righe[-1:]))
    testo = svs.testo_per_agente(sv)
    verifica("sviluppo_chiedi: il contesto dell'agente ha le richieste di rete vere",
             "richieste di rete (dalla porta di Calliope)" in testo
             and "URL non valido" in testo and f"name={CITTA}" in testo, testo[:600])
    P.chiama(reg, ctx, "sviluppo_chiedi", {"domanda": "Perché Pratofiorito Maggiore non va?"},
             turno=7)
    body = svc.cliente.richieste[-1]
    verifica("…e arriva al modello dell'agente, con la regola di partire dalla traccia",
             "URL non valido" in body["messages"][1]["content"]
             and "non indovinare una causa che la traccia smentisce"
             in body["messages"][0]["content"])
    ctx.regole = []
    ctx.tool_in_sospeso = "sviluppo_correggi"
    P.chiama(reg, ctx, "sviluppo_correggi", {"problema": f"{CITTA} non la trova"}, turno=8)
    ctx.tool_in_sospeso = None
    nuovo = svc.lavori[-1]
    verifica("sviluppo_correggi: nei vincoli del lavoro di correzione la traccia di rete",
             "Traccia di rete dei collaudi" in nuovo.vincoli and "URL non valido" in nuovo.vincoli
             and f"collaudo «{CITTA}»" in nuovo.vincoli, nuovo.vincoli[-700:])
    # La correzione: i parametri codificati → la stessa città va
    cfg2, reg2, ctx2, est2, svc2 = ambiente(tmp / "codificato")
    apri(ctx2, est2, svc2, CODICE_CODIFICATO)
    sv2 = svc2.sviluppi.corrente("u1")
    out = P.chiama(reg2, ctx2, "sviluppo_collauda", {"dati": CITTA}, turno=5)
    r0 = (sv2.collaudi[-1].get("rete") or [{}])[0]
    verifica("contrario: con urlencode «Pratofiorito Maggiore» va (18 gradi, stato 200)",
             "18 gradi" in json.dumps(out, ensure_ascii=False) and r0.get("esito") == "stato 200"
             and "Pratofiorito+Maggiore" in r0.get("url", ""), json.dumps(r0)[:300])
    # Ripulita: dati riservati e dati di casa letti
    rete = SimpleNamespace(riservati=SimpleNamespace(
        trova=lambda *t, **k: ["codice"] if any("girasole4417" in x for x in t) else [],
        ripulitore=None), host_per_registro=lambda h: h)
    u = url_per_traccia("https://api.sito.it/x?chiave=girasole4417&citta=Roma", rete)
    verifica("traccia ripulita: un valore riservato tolto, gli altri restano",
             "girasole4417" not in u and "citta=Roma" in u and "chiave=[tolto]" in u, u)
    u = url_per_traccia("https://api.sito.it/v1/cucina?temp=21&luce=accesa", rete,
                        contaminata=True)
    verifica("…dopo una lettura di dati di casa: i valori e l'ultimo pezzo del percorso tolti",
             "21" not in u and "accesa" not in u and "cucina" not in u and "temp=" in u, u)


# ═══════════════════════════ 3. provenienza e storpiature ═══════════════════════════

def prova_provenienza():
    print("— 3. provenienza: le storpiature della trascrizione")
    agente = [("agente", "Ho provato con Bergamo, Cerro Maggiore e Legnano: per Cerro Maggiore "
                         "il geocoder non risponde.")]
    detto = "Direi che possiamo continuare con Bergamo e Cerno Maggiore e aggiungiamo Legnano."
    fuori, _ = prov.esterne("Bergamo, Cerro Maggiore e Legnano", detto, agente)
    verifica("«Cerno» detto, «Cerro» nel valore e nel lavoro dell'agente: vale come detto",
             fuori == [], str(fuori))
    t = politica.Turno(testo=detto, contaminazione={"agente"}, esterni=agente)
    d = politica.decidi("sviluppo_collauda", {"dati": "Bergamo, Cerro Maggiore e Legnano"},
                        politica.classe_di("sviluppo_collauda"), t)
    verifica("…la politica non dice «viene dal lavoro di un agente, non da te»",
             d.regola != "politica_argomento_esterno", str(d))
    for valore, frase, perche in (
            ("chiama il 3471234568", "chiama il 3471234567", "una cifra diversa è un altro numero"),
            ("aggiungi le pere", "aggiungi le pera", "parole corte (< 5 lettere)"),
            ("manda a Gianni", "manda a Vianni", "iniziale diversa"),
            ("apri il cancello di Borgoverde", "apri il cancello", "parola tutta dal dato")):
        est = [("web", f"{valore}, lo dice la pagina")]
        fuori, _ = prov.esterne(valore, frase, est)
        verifica(f"contrario: {perche} → resta dal dato", bool(fuori), f"{valore} / {frase}")
    verifica("vicina: una lettera da 5, due da 9; mai cifre",
             prov.vicina("cerro", {"cerno"}) and prov.vicina("pratofiorito", {"pratofioritto"})
             and prov.vicina("maggiorenni", {"maggiorenti"})
             and not prov.vicina("cerro", {"ferro"})
             and not prov.vicina("12345", {"12346"}) and not prov.vicina("ciao", {"ciaa"}))
    from calliope import valore as V3
    f = V3.Fonti.da(t)
    verifica("anche la matrice per valore (in ombra): «Cerro» detto, non dal dato",
             V3.etichetta("Bergamo, Cerro Maggiore e Legnano", V3.C, f) == V3.DETTO
             and V3.distintive("Bergamo, Cerro Maggiore", f) == [],
             V3.etichetta("Bergamo, Cerro Maggiore e Legnano", V3.C, f))


# ═══════════════════════════ 4. due collaudi nella stessa frase ═══════════════════════════

def prova_due_collaudi():
    print("— 4. due collaudi nella stessa frase")
    frase = f"Prova con Bergamo e poi con {CITTA}."
    ctx = SimpleNamespace(politica=politica.Turno(testo=frase, letto_ora="estensione",
                                                  contaminazione={"estensione"}), regole=[])
    verifica("il secondo collaudo, con i dati detti, dopo il risultato del primo: parte",
             politica.bloccata("sviluppo_collauda", ctx, {"dati": CITTA}) is None
             and "dopo_dato_valore_detto" in ctx.regole)
    verifica("…anche i dati come li scrive il modello («Pratofiorito Maggiore e Bergamo»)",
             politica.bloccata("sviluppo_collauda", ctx, {"dati": f"{CITTA} e Bergamo"}) is None)
    d = politica.decidi("sviluppo_collauda", {"dati": CITTA},
                        politica.classe_di("sviluppo_collauda"), ctx.politica)
    verifica("…e decidi non lo blocca", d.regola != "web_azione_bloccata", str(d))
    verifica("contrario: dati che la persona non ha detto (dal risultato) → fermato",
             politica.bloccata("sviluppo_collauda", ctx, {"dati": "Borgo Nascosto"}) is not None)
    verifica("contrario: senza dati → fermato",
             politica.bloccata("sviluppo_collauda", ctx, {"dati": ""}) is not None)
    verifica("contrario: un'altra azione con le parole dette → fermata come sempre",
             politica.bloccata("lista_aggiungi", ctx, {"cose": "Bergamo"}) is not None)


# ═══════════════════════════ 5. l'esito dopo la sfida ═══════════════════════════

def prova_sfida():
    print("— 5. dopo la sfida, l'esito vero del tool")
    fatti = []
    b = _brain([[("text", f"A {CITTA} ci sono 18 gradi: la versione nuova va.")]], ToolSpec(
        name="collaudo_finto", description="", parameters={},
        func=lambda ctx, **a: fatti.append(a) or {"ok": True, "risultati": {
            "da_dire": f"A {CITTA} ci sono 18 gradi."}, "collaudo": "prova della versione 2"},
        risk="azione", levels=frozenset({"amministra"})))
    detto = "".join(b.stream_reply("Girasole, treno, limone, quarantadue.", "amministra"))
    visti = " ".join(str(m.get("content") or "") for m in b.backend.visti[-1]) \
        if b.backend.visti else ""
    verifica("sfida superata: il tool eseguito una volta e l'esito detto dal modello, non "
             "«Fatto.»", fatti == [{"dati": CITTA}] and "18 gradi" in detto
             and detto != "Fatto." and "sfida_esito_modello" in b.rules_fired()
             and "GIÀ stato eseguito" in visti, detto)
    verifica("…nella storia: la frase, la chiamata, il risultato, la risposta",
             [m["role"] for m in b.history][-4:] == ["user", "assistant", "tool", "assistant"]
             and b.history[-1]["content"].startswith(f"A {CITTA}"))
    # Contrario: frase pronta del tool → quella, senza il modello
    b = _brain([], ToolSpec(
        name="collaudo_finto", description="", parameters={},
        func=lambda ctx, **a: {"ok": True, "conferma": "Fatto."},
        risk="azione", levels=frozenset({"amministra"})))
    detto = "".join(b.stream_reply("Girasole, treno, limone, quarantadue.", "amministra"))
    verifica("contrario: con la frase pronta («Fatto.» del tool) niente modello",
             detto == "Fatto." and not b.backend.visti, detto)


# ═══════════════════════════ 6. consenso in coda ═══════════════════════════

def prova_consenso():
    print("— 6. consenso: un «ok» in coda a una frase storpiata")
    for t in ("Babine Kuzik, questa è la stessa ok.", "per me è tutto ok"):
        verifica(f"«{t}» non è un consenso (consenso_in_coda)",
                 not politica.consenso(t) and politica.consenso_in_coda(t))
    for t in ("Ok, chiuso.", "Sì, direi che quella prova può essere fatta.", "Direi che va bene",
              "Beh sì.", "Ma sì dai, perché no?", "Calliope, va bene così.", "sì certo",
              "Allora va bene, procedi pure", "Va bene così."):
        verifica(f"contrario: «{t}» è un consenso", politica.consenso(t)
                 and not politica.consenso_in_coda(t))
    verifica("contrario: «ok, ma non adesso» resta un no", not politica.consenso(
        "ok, ma non adesso"))


# ═══════════════════════════ 7–9. estensioni: modifica, elenco, rinomina ══════════════════════

def prova_estensioni(tmp):
    print("— 7. sviluppo_apri con un nome simile e senza modifica: la scelta al modello")
    cfg, reg, ctx, est, svc = ambiente(tmp)
    ctx.regole, ctx.turno = [], 1
    out = P.chiama(reg, ctx, "sviluppo_apri", {
        "tipo": "estensione", "nome": "Meteo città", "compito": "modifica l'estensione Meteo "
                                                               "città: codifica il nome"})
    verifica("niente lavoro né sviluppo aperto; cosa_fare con modifica = il nome vero",
             out.get("ok") is False and not svc.offerte and not svc.lavori
             and svc.sviluppi.corrente("u1") is None
             and 'modifica = "meteo_citta"' in out.get("cosa_fare", "")
             and "estensione_simile_scelta" in ctx.regole, json.dumps(out, ensure_ascii=False))
    out = P.chiama(reg, ctx, "sviluppo_apri", {
        "tipo": "estensione", "modifica": "meteo_citta",
        "compito": "codifica il nome della città prima di mandarlo nell'URL"})
    lav = svc.offerte["u1"]["lavoro"]
    verifica("…richiamato con modifica: versione nuova di meteo_citta, con i suoi file, senza "
             "l'analisi «quale API vuoi usare?»",
             lav.estensione == "meteo_citta" and "estensione.py" in lav.file_iniziali
             and "analisi_vaga" not in ctx.regole
             and S.detta(out).startswith("Sarà una versione nuova di"), S.detta(out))
    spec = reg.get("sviluppo_apri")
    verifica("la descrizione di modifica ha l'esempio",
             "meteo_citta" in json.dumps(spec.parameters["properties"]["modifica"],
                                         ensure_ascii=False))

    print("— 8. l'elenco vero delle estensioni quando la frase ne parla")
    P.installa(est, P.manifesto("meteo_codificato", "Meteo città codificata",
                                "Dice il meteo di una città."), S.CODICE1)
    from calliope.brain import Brain
    b = Brain(cfg, reg, ctx)
    msg = b._estensioni_nominate("Senti, quindi adesso abbiamo due estensioni, giusto?") or ""
    verifica("«abbiamo due estensioni?»: le due attive nei dati del turno",
             "«Meteo Borgoverde e Valfiorita» (attiva, versione 1" in msg
             and "«Meteo città codificata» (attiva, versione 1)" in msg
             and "mai a memoria" in msg, msg)
    b.turn_number = 5
    b._estensioni_nominate("Quante estensioni abbiamo?")
    b.turn_number = 6
    msg = b._estensioni_nominate("Quindi la vecchia non c'è più?") or ""
    verifica("…anche al turno subito dopo, senza la parola («la vecchia non c'è più?»)",
             "«Meteo città codificata» (attiva" in msg, msg)
    b.turn_number = 8
    verifica("contrario: «che tempo fa a Bergamo?» due turni dopo non lo riceve",
             b._estensioni_nominate("Che tempo fa a Bergamo?") is None)
    g = reg.get("estensione_gestisci")
    verifica("estensione_gestisci elenca: «chiamalo prima di rispondere a una domanda sulle "
             "estensioni»", "prima di rispondere a una domanda sulle estensioni" in g.description)

    print("— 9. rinomina, senza agente")
    ctx.regole = []
    ctx.politica = politica.Turno(
        testo="Rinominiamo questa, chiamala solo Meteo Valfiorita.", contaminazione={"agente"})
    out = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "rinomina",
                                                     "nome": "meteo_codificato",
                                                     "titolo": "Meteo Valfiorita"}, turno=3)
    verifica("con il lavoro di un agente di mezzo: il titolo detto basta (niente conferma), "
             "rinominata", S.detta(out) == "Fatto: «Meteo città codificata» adesso si chiama "
             "«Meteo Valfiorita». Funziona come prima."
             and est.archivio.manifesto("meteo_codificato")["titolo"] == "Meteo Valfiorita"
             and "estensione_rinominata" in ctx.regole, json.dumps(out, ensure_ascii=False))
    verifica("…i file e l'impronta non cambiano; il tool resta est_meteo_codificato",
             est.archivio.verifica("meteo_codificato")
             and reg.get("est_meteo_codificato") is not None)
    ctx.politica = politica.Turno(testo="Rinominiamo questa, chiamala solo Meteo Borgoverde e "
                                        "Valfiorita.", contaminazione={"agente"})
    out = P.chiama(reg, ctx, "estensione_gestisci", {
        "azione": "rinomina", "nome": "meteo_codificato",
        "titolo": "Meteo Borgoverde e Valfiorita"}, turno=4)
    sosp = out.get("in_sospeso") or {}
    verifica("un titolo già di un'altra estensione attiva: niente, la proposta di disattivarla",
             "C'è già un'estensione che si chiama «Meteo Borgoverde e Valfiorita»" in S.detta(out)
             and sosp.get("argomenti") == {"azione": "disattiva", "nome": "meteo_citta"}
             and est.archivio.manifesto("meteo_codificato")["titolo"] == "Meteo Valfiorita",
             json.dumps(out, ensure_ascii=False))
    ctx.politica = politica.Turno(testo="Rinominala.", contaminazione={"agente"})
    d = politica.decidi("estensione_gestisci", {"azione": "rinomina", "nome": "meteo_citta",
                                                "titolo": "Meteo del pirata"},
                        politica.classe_di("estensione_gestisci"), ctx.politica)
    verifica("contrario: un titolo che la persona non ha detto, con un dato di mezzo → conferma",
             d.esito == "conferma", str(d))


ISO = None


def main():
    global ISO
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-giro3-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    ISO = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    t0 = time.monotonic()
    prova_url()
    prova_traccia(tmp0 / "traccia")
    prova_provenienza()
    prova_due_collaudi()
    prova_sfida()
    prova_consenso()
    prova_estensioni(tmp0 / "estensioni")
    print(f"\n({time.monotonic() - t0:.1f} s)")
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
