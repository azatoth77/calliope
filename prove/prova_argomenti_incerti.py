import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Parole incerte negli argomenti dei tool (08/10/2026, fasi F0 e F1 di
docs/ricerche/2026-10-08-parole-incerte.md). A secco, nell'hook.

I casi veri dell'08/10 con i nomi di fantasia del documento: «Pradello Dugnasco» trascritto
«Patello Giugnasco» e non trovato; «Mantua»; «metricità» per Meteocittà; «la gente».

1. I pezzi: forme e somiglianza, argomenti marcati (anche dentro `argomenti`), tipo dal nome
   dell'input, allineamento del valore alle parole di Whisper (con il modello che ha già
   corretto), esito del tool (vuoto, pieno, errore, fermato), vocabolario dei nomi noti per
   tipo (anche dal registro), correzione spontanea.
2. I trascrittori: `parole` di whisper-server (verbose_json, senza tempi per token) e di
   faster-whisper (word_timestamps), finti; l'ascolto riusa le parole già chieste.
3. Con Brain (modello a copione): F0 nel registro (valore, probabilità, nome noto, esito; solo
   numeri per ospiti e zona grigia; mai il valore di un tool riservato), il tool non aspetta
   Whisper; F1 dopo un esito vuoto («forse intendeva» con la proposta in sospeso, il «sì» che
   richiama il tool senza domande della politica, «ripeti o scrivi») e i contrari (esito pieno,
   nome lontano e Whisper sicuro, ospite, zona grigia, la casa con i suoi nomi vicini, frase
   pronta, risposta alla proposta stessa, rete spenta, «la gente» in senso vero).
4. Il riassunto di `calliope stato --turni`.

    python prove\\prova_argomenti_incerti.py
"""

import dataclasses
import json
import tempfile
import time
from pathlib import Path

import numpy as np

from calliope import argomenti_incerti as ai
from calliope.stt_correzione import confidenza
from calliope.tools.spec import ToolSpec
from prove.prova_politica import ChiParla, Copione, chiama, prepara, testo

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    if not ok:
        errori += 1
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                               else ""), flush=True)


# ─────────────────────────── 1. i pezzi ───────────────────────────
def prova_pezzi():
    verifica("lettere: spazi, doppie e accenti non contano",
             ai.lettere("Prato Fiorito Magiore") == ai.lettere("Pratofiorito Maggiore")
             and ai.lettere("Meteocittà") == "meteocita")
    verifica("uguali: «Luca» e «Lucca» sono nomi diversi", not ai.uguali("Luca", "Lucca")
             and ai.uguali("Pradello  Dugnasco", "pradello dugnasco"))
    verifica("somiglianza dei casi veri ≥ 0,7",
             all(ai.somiglianza(a, b) >= 0.7 for a, b in (
                 ("Patello Giugnasco", "Pradello Dugnasco"), ("Mantua", "Mantova"),
                 ("metricità", "Meteocittà"), ("Pradello Duniasco", "Pradello Dugnasco"),
                 ("Luca", "Lucca"))))
    verifica("somiglianza: nomi diversi sotto 0,7",
             ai.somiglianza("Roccalba", "Pradello Dugnasco") < 0.7
             and ai.somiglianza("Bergamo", "Brescia") < 0.7)
    verifica("tipo dal nome dell'input", ai.tipo_da_campo("citta") == "luogo"
             and ai.tipo_da_campo("comune") == "luogo" and ai.tipo_da_campo("file") == "file"
             and ai.tipo_da_campo("giorni") == "valore")
    verifica("nomi di un'estensione: testo libero sì, enum e numeri no",
             ai.nomi_estensione({"properties": {"citta": {"type": "string"},
                                                "unita": {"type": "string", "enum": ["c", "f"]},
                                                "giorni": {"type": "integer"}}})
             == {"citta": "luogo"})
    spec = ToolSpec(name="sviluppo_collauda", description="", parameters={}, func=None,
                    nomi={"dati": "valore", "argomenti": "valore"})
    m = ai.argomenti_marcati(spec, {"argomenti": {"citta": "Patello Giugnasco", "giorni": 3,
                                                  "numero": "12"}})
    verifica("argomenti marcati: dentro l'oggetto, con il tipo dal campo, senza numeri",
             m == [("argomenti.citta", "Patello Giugnasco", "luogo")], str(m))
    verifica("argomenti marcati: dati come testo", ai.argomenti_marcati(
        spec, {"dati": "Pradello Dugnasco"}) == [("dati", "Pradello Dugnasco", "valore")])
    verifica("argomenti marcati: un tool senza nomi non si misura",
             ai.argomenti_marcati(ToolSpec(name="x", description="", parameters={}, func=None),
                                  {"testo": "Mantua"}) == [])
    verifica("sostituisci: dentro l'oggetto, il resto uguale",
             ai.sostituisci({"argomenti": {"citta": "Mantua", "giorni": 3}},
                            "argomenti.citta", "Mantova")
             == {"argomenti": {"citta": "Mantova", "giorni": 3}})

    # Allineamento
    parole = [("Calliope", 0.31), ("prova", 0.97), ("con", 0.99), ("Patello", 0.22),
              ("Giugnasco", 0.41)]
    a = ai.allinea("Patello Giugnasco", parole, ["Calliope"])
    verifica("allinea: le parole del valore, minima e media", a and a["p_min"] == 0.22
             and a["p_media"] == 0.315 and a["uguale"] and a["parole"] == 2, str(a))
    a = ai.allinea("Pradello Dugnasco", parole, ["Calliope"])
    verifica("allinea: il modello ha già corretto il nome → stesse parole, non uguale",
             a and a["p_min"] == 0.22 and not a["uguale"], str(a))
    verifica("allinea: un valore che non è nella frase → None",
             ai.allinea("Roccalba", [("sì", 0.9), ("grazie", 0.95)]) is None)
    a = ai.allinea("prova", [("Calliope", 0.1), ("prova", 0.9)], ["Calliope"])
    verifica("allinea: il nome che sveglia non conta", a and a["p_min"] == 0.9, str(a))

    # Esito
    casi = [
        ({"ok": True, "risultati": {"citta": "Pratofiorito", "temperatura": 18}}, "pieno"),
        ({"ok": True, "risultati": {"errore": "Località non trovata: Mantua"}}, "vuoto"),
        ({"ok": True, "risultati": {"messaggio": "Nessun risultato per Mantua"}}, "vuoto"),
        ({"ok": True, "risultati": {"trovato": False}}, "vuoto"),
        ({"ok": True, "risultati": []}, "vuoto"),
        ({"ok": True, "risultati": {"previsioni": []}}, "vuoto"),
        ({"ok": False, "errore": "l'estensione «Meteo» non è riuscita: city not found"}, "vuoto"),
        ({"ok": False, "errore": "l'estensione «Meteo» non è riuscita: timeout"}, "errore"),
        ({"ok": True, "risultati": {"errore": "HTTP 500"}}, "errore"),
        ({"ok": False, "fatto": "NIENTE", "errore": "Home Assistant non ha capito",
          "nomi_vicini": ["Lampada soppalco"]}, "vuoto"),
        ({"ok": True, "risultati": [], "conferma": "Sul portatile non ho trovato file «chiavi»."},
         "vuoto"),
        ({"ok": False, "motivo": "chi sta parlando non ha il permesso"}, "fermato"),
        ({"ok": False, "conferma": "Vuoi che…?", "in_sospeso": {"tool": "x"}}, "fermato"),
        ({"ok": True, "risultati": {"testo": "Il sole non è trovato da nessuna parte: piove "
                                    "tutto il giorno, " + "x" * 400}}, "pieno"),
    ]
    sbagliati = [(r, e, ai.esito(r)) for r, e in casi if ai.esito(r) != e]
    verifica(f"esito del tool: {len(casi)} casi", not sbagliati, str(sbagliati))

    # Vocabolario
    v = ai.Vocabolario()
    v.ricorda("luogo", "Pradello Dugnasco")
    v.ricorda("valore", "Pratofiorito Maggiore")
    v.ricorda("file", "bolletta luce")
    verifica("vocabolario: «Patello Giugnasco» → Pradello Dugnasco",
             v.vicino("Patello Giugnasco", "luogo")[0] == "Pradello Dugnasco")
    verifica("vocabolario: luogo e valore insieme, file a parte",
             v.vicino("Pratofiorito Magiore", "luogo")[0] == "Pratofiorito Maggiore"
             and v.vicino("Pradello", "file")[0] != "Pradello Dugnasco")

    class Arch:
        def nomi(self):
            return ["meteo_citta"]

        def manifesto(self, n):
            return {"titolo": "Meteocittà"}

    class Est:
        archivio = Arch()

    class Ctx:
        estensioni = Est()
    n, s = v.vicino("metricità", "estensione", Ctx())
    verifica("vocabolario: le estensioni per titolo e nome («metricità» → Meteocittà)",
             n == "Meteocittà" and s >= 0.7, f"{n} {s}")

    class E:
        def __init__(self, nome, area, alias=()):
            self.nome, self.area, self.alias = nome, area, list(alias)

    class Casa:
        def entita(self):
            return [E("Lampada soppalco", "Soppalco"), E("Luce cucina", "Cucina", ["Cucina"])]

        def aree(self):
            return {"Soppalco": [], "Cucina": []}

    class CtxCasa:
        casa = Casa()
    n, s = v.vicino("accendi la lampara del sottalco", "casa", CtxCasa())
    verifica("vocabolario della casa: i pezzi della frase («lampara del sottalco»)",
             n in ("Lampada soppalco", "Soppalco") and s >= 0.7, f"{n} {s}")
    with tempfile.TemporaryDirectory() as d:
        Path(d, "turni-2026-10-08.jsonl").write_text("\n".join(json.dumps(r) for r in [
            {"stt_argomento": [{"tool": "est_meteo", "tipo": "luogo", "valore": "Roccalba",
                                "esito": "pieno"}]},
            {"stt_argomento": [{"tool": "est_meteo", "tipo": "luogo", "valore": "Mantua",
                                "esito": "vuoto"}]},
            {"livello": "ospite", "stt_argomento": [{"tool": "est_meteo", "tipo": "luogo",
                                                     "esito": "pieno"}]},
        ]), encoding="utf-8")
        v2 = ai.Vocabolario()
        v2.carica_dal_registro(d)
        verifica("vocabolario dal registro: solo i valori con esito pieno",
                 v2.riusciti("luogo") == ["Roccalba"], str(v2.riusciti("luogo")))

    verifica("correzione spontanea: Duniasco → Dugnasco, Luca → Lucca",
             ai.correzione("Pradello Duniasco", "Pradello Dugnasco")
             and ai.correzione("Luca", "Lucca"))
    verifica("correzione, contrari: uguale, un altro nome, una parola corta",
             not ai.correzione("Lucca", "lucca") and not ai.correzione("Bergamo", "Brescia")
             and not ai.correzione("Via Roma 3", "Via Roma 5"))


# ─────────────────────────── 2. i trascrittori ───────────────────────────
def prova_trascrittori():
    from calliope.config import Config
    from calliope.stt import ServerTranscriber, Transcriber

    class Risposta:
        def __init__(self, d):
            self.d = d

        def raise_for_status(self):
            pass

        def json(self):
            return self.d

    class Http:
        def __init__(self):
            self.dati = []

        def post(self, url, files=None, data=None):
            self.dati.append(dict(data))
            if data["response_format"] == "verbose_json":
                return Risposta({"text": " Prova con Patello Giugnasco", "segments": [{
                    "words": [{"word": " Prova", "probability": 0.97},
                              {"word": " con", "probability": 0.99},
                              {"word": " Pat", "probability": 0.4},
                              {"word": "ello", "probability": 0.22},
                              {"word": " Giugnasco", "probability": 0.41},
                              {"word": ".", "probability": 0.9}]}]})
            return Risposta({"text": " ciao"})

    cfg = Config()
    cfg.stt_motore, cfg.stt_url = "server", "http://127.0.0.1:1/v1"
    http = Http()
    st = ServerTranscriber(cfg, http=http)
    p = st.parole(np.zeros(16000, dtype=np.float32))
    verifica("whisper-server: verbose_json senza tempi per token, parole riunite",
             http.dati[-1]["response_format"] == "verbose_json"
             and http.dati[-1].get("token_timestamps") == "false"
             and p == [("Prova", 0.97), ("con", 0.99), ("Patello", 0.22), ("Giugnasco", 0.41)],
             str(p))
    verifica("whisper-server: la trascrizione normale resta json",
             http.dati[0]["response_format"] == "json")

    class Parola:
        def __init__(self, w, p):
            self.word, self.probability = w, p

    class Seg:
        text = " Prova con Mantua"
        words = [Parola(" Prova", 0.98), Parola(" con", 0.99), Parola(" Mantua", 0.52),
                 Parola(".", 0.9)]

    class Modello:
        def __init__(self):
            self.kw = None

        def transcribe(self, audio, **kw):
            self.kw = kw
            return [Seg()], None

    fw = Transcriber.__new__(Transcriber)
    fw.cfg, fw._prompt_fisso, fw.model = cfg, None, Modello()
    p = fw.parole(np.zeros(16000, dtype=np.float32))
    verifica("faster-whisper: word_timestamps e le stesse opzioni della trascrizione",
             fw.model.kw.get("word_timestamps") is True and fw.model.kw.get("beam_size")
             == cfg.whisper_beam_size and p == [("Prova", 0.98), ("con", 0.99),
                                                 ("Mantua", 0.52)], str(p))

    conf = confidenza({"segments": [{"words": [{"word": " Mantua", "probability": 0.52}]}]})
    chiamate = []

    class STT:
        def parole(self, audio):
            chiamate.append(1)
            return []
    asc = ai.Ascolto(np.ones(10, dtype=np.float32), STT(), conf)
    asc.avvia()
    verifica("ascolto: con il verbose_json già chiesto non si richiede",
             asc.parole() == [("Mantua", 0.52)] and not chiamate)
    verifica("ascolto: senza audio (frase scritta) non si chiede niente",
             not ai.Ascolto(None, STT()).possibile)


# ─────────────────────────── 3. con Brain ───────────────────────────
class STTFinto:
    """Le parole della frase con le probabilità, dopo `ritardo` secondi."""

    def __init__(self, parole, ritardo=0.0):
        self.p, self.ritardo, self.chiamate = parole, ritardo, 0

    def parole(self, audio):
        self.chiamate += 1
        time.sleep(self.ritardo)
        return list(self.p)


NOTE = {"pradello dugnasco": {"citta": "Pradello Dugnasco", "temperatura": 17},
        "pratofiorito maggiore": {"citta": "Pratofiorito Maggiore", "temperatura": 19},
        "roccalba": {"citta": "Roccalba", "temperatura": 15}}


def meteo(ctx, citta="", **_):
    time.sleep(0.25)                       # il tool dura: le probabilità arrivano intanto
    d = NOTE.get(" ".join(str(citta).lower().split()))
    if d is None:
        return {"ok": True, "risultati": {"errore": f"Località non trovata: {citta}"}}
    return {"ok": True, "risultati": d}


class Spia(Copione):
    """Il modello a copione che si ricorda i messaggi ricevuti: i risultati dei tool non fidati
    escono dalla storia a risposta finita, ma il modello li ha visti."""

    def __init__(self):
        super().__init__()
        self.visti = []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        yield from super().stream(messages, tools)


def prepara_brain():
    b, eseguiti, _ = prepara()
    b.backend = Spia()
    reg = b.tools
    for nome, classe in (("est_meteo_citta", "sicuro"), ("est_prenota", "azione")):
        def f(ctx, _n=nome, **a):
            eseguiti.append((_n, dict(a)))
            return meteo(ctx, **a)
        reg.register(ToolSpec(
            name=nome, description="estensione", parameters={
                "type": "object", "properties": {"citta": {"type": "string"}}},
            func=f, levels=frozenset({"familiare", "amministra"}), classe=classe,
            fonte="estensione", non_fidato=True, chiave=("citta",),
            nomi=ai.nomi_estensione({"properties": {"citta": {"type": "string"}}})))
    reg.register(ToolSpec(name="est_riservata", description="", parameters={},
                          func=lambda ctx, **a: {"ok": True, "risultati": []},
                          levels=frozenset({"familiare", "amministra"}), classe="sicuro",
                          riservato=True, nomi={"testo": "contatto"}))
    reg.register(ToolSpec(name="est_pronta", description="", parameters={},
                          func=lambda ctx, **a: {"ok": False, "risposta_finale":
                                                 "Non ho trovato niente.",
                                                 "errore": "non trovato"},
                          levels=frozenset({"familiare", "amministra"}), classe="sicuro",
                          nomi={"citta": "luogo"}))
    # La casa: il «non trovato» ha già i suoi nomi vicini
    reg.register(dataclasses.replace(reg.get("casa_stato"), func=lambda ctx, cosa="": {
        "ok": False, "fatto": "NIENTE", "errore": "non trovato",
        "nomi_vicini": ["Lampada soppalco"], "stanze": ["Soppalco"]}))
    reg.register(dataclasses.replace(reg.get("pc_cerca_file"), func=lambda ctx, **a: {
        "ok": True, "risultati": [{"nome": "x"}], "conferma": "Ho trovato x. Lo apro?",
        "in_sospeso": {"domanda": "Lo apro?", "cosa": "il file x", "tool": "pc_apri_file",
                       "argomenti": {"risultato": 1}}}))
    ai.VOCABOLARIO = ai.Vocabolario()
    ai.VOCABOLARIO._caricato.add("niente registro")
    b.cfg.turn_log_dir = "niente registro"
    return b, eseguiti


def parla(b, frase, *risposte, parole=None, ritardo=0.0, chi=None):
    asc = None
    if parole is not None:
        asc = ai.Ascolto(np.ones(1600, dtype=np.float32), STTFinto(parole, ritardo),
                         nomi_sveglia=["Calliope"])
    if chi is not None:
        b.tool_ctx.speaker_ctx = chi
    b.backend.risposte = list(risposte)
    detto = "".join(b.stream_reply(frase, b.tool_ctx.speaker_ctx.current_level, ascolto=asc))
    return detto, b.argomenti_per_registro(), asc


def ultimo_risultato(b):
    for m in reversed(b.backend.visti[-1] if b.backend.visti else []):
        if m.get("role") == "tool":
            try:
                return json.loads(m["content"])
            except (json.JSONDecodeError, TypeError):
                return {}
    return {}


P_PATELLO = [("Calliope", 0.3), ("prova", 0.97), ("con", 0.99), ("Patello", 0.22),
             ("Giugnasco", 0.41)]


def prova_brain():
    b, eseguiti = prepara_brain()
    # Turno 1: il nome giusto, trovato → nel vocabolario
    t0 = time.perf_counter()
    _, reg1, asc = parla(b, "Calliope, prova con Pradello Dugnasco",
                         chiama("est_meteo_citta", {"citta": "Pradello Dugnasco"}),
                         testo("A Pradello Dugnasco 17 gradi."),
                         parole=[("prova", 0.98), ("con", 0.99), ("Pradello", 0.93),
                                 ("Dugnasco", 0.88)], ritardo=0.2)
    durata = time.perf_counter() - t0
    r = reg1[0] if reg1 else {}
    verifica("F0: esito pieno, valore, probabilità, nel registro",
             r.get("esito") == "pieno" and r.get("valore") == "Pradello Dugnasco"
             and r.get("p_min") == 0.88 and r.get("tipo") == "luogo"
             and r.get("argomento") == "citta", str(reg1))
    verifica("F0: le probabilità in parallelo al tool (0,25 + 0,2 s → meno di 0,4 s)",
             durata < 0.4 and asc.stt.chiamate == 1, f"{durata:.2f} s")
    verifica("F0: nessun suggerimento con esito pieno", "nome_incerto" not in
             json.dumps(ultimo_risultato(b)) and "argomento_forse" not in b.rules_fired())
    verifica("F0: il valore riuscito entra nel vocabolario",
             ai.VOCABOLARIO.riusciti("luogo") == ["Pradello Dugnasco"])

    # Turno 2: «Patello Giugnasco» non trovato → «forse intendeva Pradello Dugnasco?»
    detto, reg2, _ = parla(b, "Calliope, prova con Patello Giugnasco",
                           chiama("est_meteo_citta", {"citta": "Patello Giugnasco"}),
                           testo("Non trovo Patello Giugnasco: intendevi Pradello Dugnasco?"),
                           parole=P_PATELLO)
    res = ultimo_risultato(b)
    ni = res.get("nome_incerto") or {}
    verifica("F1: «forse intendeva» nel risultato, fuori dalla busta",
             ni.get("forse") == "Pradello Dugnasco" and ni.get("detto") == "Patello Giugnasco"
             and "Pradello Dugnasco" in ni.get("cosa_fare", "")
             and "dato_non_fidato" in res, json.dumps(res, ensure_ascii=False)[:300])
    verifica("F1: regola argomento_forse e proposta in sospeso con il nome suggerito",
             "argomento_forse" in b.rules_fired() and b.pending
             and b.pending.get("tool") == "est_meteo_citta"
             and (b.pending.get("args") or {}).get("citta") == "Pradello Dugnasco",
             str(b.pending))
    r = reg2[0] if reg2 else {}
    verifica("F0: esito vuoto, nome noto vicino, probabilità bassa, forma del suggerimento",
             r.get("esito") == "vuoto" and r.get("noto") == "Pradello Dugnasco"
             and r.get("somiglianza", 0) >= 0.7 and r.get("p_min") == 0.22
             and r.get("forse") == "forse", str(r))
    verifica("F0: il valore detto dalla persona non è stato cambiato",
             eseguiti[-1] == ("est_meteo_citta", {"citta": "Patello Giugnasco"}))

    # Turno 3: «Sì.» → il tool con il nome suggerito, senza domande della politica
    n = len(eseguiti)
    detto, reg3, _ = parla(b, "Sì.", chiama("est_meteo_citta", {"citta": "Pradello Dugnasco"}),
                           testo("A Pradello Dugnasco 17 gradi."),
                           parole=[("Sì", 0.95)])
    verifica("F1: il «sì» richiama il tool con il nome suggerito, eseguito",
             eseguiti[n:] == [("est_meteo_citta", {"citta": "Pradello Dugnasco"})]
             and "?" not in detto, f"{eseguiti[n:]} {detto!r}")
    r = reg3[0] if reg3 else {}
    verifica("F1: argomento_forse_usato e correzione spontanea nel registro",
             r.get("da_suggerimento") and "argomento_forse_usato" in b.rules_fired()
             and (r.get("correzione") or {}).get("esito_prima") == "vuoto"
             and "correzione_argomento" in b.rules_fired() and r.get("allineato") is False,
             str(r))

    # Un'azione (classe «azione»): il «sì» alla proposta non chiede altro
    b, eseguiti = prepara_brain()
    ai.VOCABOLARIO.ricorda("luogo", "Pradello Dugnasco")
    parla(b, "Calliope, prenota a Patello Giugnasco",
          chiama("est_prenota", {"citta": "Patello Giugnasco"}),
          testo("Non trovo Patello Giugnasco: intendevi Pradello Dugnasco?"), parole=P_PATELLO)
    n = len(eseguiti)
    detto, _, _ = parla(b, "Sì, esatto.", chiama("est_prenota", {"citta": "Pradello Dugnasco"}),
                        testo("Fatto."), parole=[("Sì", 0.95), ("esatto", 0.9)])
    verifica("F1, politica: il «sì» a «intendevi…?» per un'azione esegue senza conferme",
             eseguiti[n:] == [("est_prenota", {"citta": "Pradello Dugnasco"})]
             and "conferma" not in " ".join(b.rules_fired()), f"{eseguiti[n:]} {detto!r} "
             f"{b.rules_fired()}")

    # Il collaudo vero (classe pericolosa, dati da un'estensione nella conversazione): «prova
    # con Pradello Dugnasco» trovato, poi «Patello Giugnasco» (la domanda della politica, il sì,
    # non trovato, «intendevi…?»), poi «sì» → eseguito senza un'altra domanda
    b, eseguiti = prepara_brain()

    def collauda(ctx, dati="", argomenti=None, **_):
        citta = dati or (argomenti or {}).get("citta", "")
        eseguiti.append(("sviluppo_collauda", citta))
        return meteo(ctx, citta=citta)
    b.tools.register(ToolSpec(
        name="sviluppo_collauda", description="", parameters={
            "type": "object", "properties": {"dati": {"type": "string"},
                                             "argomenti": {"type": "object"}}},
        func=collauda, risk="azione", levels=frozenset({"familiare", "amministra"}),
        non_fidato=True, fonte="estensione", nomi={"dati": "valore", "argomenti": "valore"}))
    dario = ChiParla(name="Dario", level="amministra")
    parla(b, "Calliope, prova con Pradello Dugnasco",
          chiama("sviluppo_collauda", {"dati": "Pradello Dugnasco"}), testo("17 gradi."),
          parole=[("prova", 0.98), ("con", 0.99), ("Pradello", 0.9), ("Dugnasco", 0.9)],
          chi=dario)
    _, reg, _ = parla(b, "Calliope, prova con Patello Giugnasco",
                      chiama("sviluppo_collauda", {"dati": "Patello Giugnasco"}),
                      parole=P_PATELLO)
    verifica("collaudo: la domanda della politica è un esito «fermato», niente «forse»",
             reg and reg[0].get("esito") == "fermato"
             and "argomento_forse" not in b.rules_fired(), str(reg))
    parla(b, "Sì.", chiama("sviluppo_collauda", {"dati": "Patello Giugnasco"}),
          testo("Non trovo Patello Giugnasco: intendevi Pradello Dugnasco?"),
          parole=[("Sì", 0.9)])
    verifica("collaudo: dopo il sì alla politica, non trovato → «forse intendeva»",
             "argomento_forse" in b.rules_fired()
             and (b.pending or {}).get("args") == {"dati": "Pradello Dugnasco"},
             f"{b.rules_fired()} {b.pending}")
    n = len(eseguiti)
    detto, _, _ = parla(b, "Sì.", chiama("sviluppo_collauda", {"dati": "Pradello Dugnasco"}),
                        testo("A Pradello Dugnasco 17 gradi."), parole=[("Sì", 0.9)])
    verifica("collaudo: il «sì» esegue con il nome suggerito (la proposta in sospeso), senza "
             "«viene dal risultato di un'estensione»",
             eseguiti[n:] == [("sviluppo_collauda", "Pradello Dugnasco")]
             and "argomento_forse_usato" in b.rules_fired()
             and "politica_argomento_esterno" not in b.rules_fired(),
             f"{eseguiti[n:]} {detto!r} {b.rules_fired()}")

    # Il «sì» che non trova di nuovo: niente secondo «forse»
    b2, _ = prepara_brain()
    ai.VOCABOLARIO.ricorda("luogo", "Pradello Dugnaschi")
    parla(b2, "Calliope, prova con Patello Giugnasco",
          chiama("est_meteo_citta", {"citta": "Patello Giugnasco"}), testo("Intendevi…?"),
          parole=P_PATELLO)
    parla(b2, "Sì.", chiama("est_meteo_citta", {"citta": "Pradello Dugnaschi"}),
          testo("Non la trovo."), parole=[("Sì", 0.9)])
    verifica("F1, contrario: la risposta alla proposta stessa non riceve un altro «forse»",
             "nome_incerto" not in json.dumps(ultimo_risultato(b2))
             and "argomento_forse" not in b2.rules_fired(), str(b2.rules_fired()))

    # Nome lontano e Whisper incerto → «ripeti o scrivi»
    b3, _ = prepara_brain()
    ai.VOCABOLARIO.ricorda("luogo", "Pradello Dugnasco")
    parla(b3, "Calliope, prova con Rocca Barba",
          chiama("est_meteo_citta", {"citta": "Rocca Barba"}), testo("Non la trovo."),
          parole=[("prova", 0.98), ("con", 0.99), ("Rocca", 0.35), ("Barba", 0.6)])
    ni = ultimo_risultato(b3).get("nome_incerto") or {}
    verifica("F1: nome noto lontano e parola incerta → «ripeti o scrivi», nessun nome",
             ni and "forse" not in ni and "ripeter" in ni.get("cosa_fare", "")
             and b3.pending is None, str(ni))
    # Nome lontano e Whisper sicuro → niente (il posto non c'è davvero)
    parla(b3, "Calliope, prova con Borgo Alto",
          chiama("est_meteo_citta", {"citta": "Borgo Alto"}), testo("Non la trovo."),
          parole=[("prova", 0.98), ("con", 0.99), ("Borgo", 0.95), ("Alto", 0.97)])
    verifica("F1, contrario: nome lontano e Whisper sicuro → nessun suggerimento",
             "nome_incerto" not in json.dumps(ultimo_risultato(b3)))
    # Scritto dallo schermo: niente Whisper, solo il nome vicino
    parla(b3, "prova con Rocca Barba", chiama("est_meteo_citta", {"citta": "Rocca Barba"}),
          testo("Non la trovo."), chi=ChiParla(how="schermo"))
    verifica("F1, scritto: senza nome vicino nessun «ripeti»",
             "nome_incerto" not in json.dumps(ultimo_risultato(b3)))
    parla(b3, "prova con Pradelo Dugnasco", chiama("est_meteo_citta",
                                                   {"citta": "Pradelo Dugnasco"}),
          testo("Intendevi Pradello Dugnasco?"), chi=ChiParla(how="schermo"))
    verifica("F1, scritto: con un nome vicino il «forse» c'è",
             (ultimo_risultato(b3).get("nome_incerto") or {}).get("forse")
             == "Pradello Dugnasco")

    # Ospite e zona grigia: mai F1, nel registro solo numeri
    b4, _ = prepara_brain()
    ai.VOCABOLARIO.ricorda("luogo", "Pradello Dugnasco")
    b4.tools.register(dataclasses.replace(b4.tools.get("est_meteo_citta"),
                                          levels=frozenset({"ospite", "familiare",
                                                            "amministra"})))
    _, reg, _ = parla(b4, "Calliope, prova con Patello Giugnasco",
                      chiama("est_meteo_citta", {"citta": "Patello Giugnasco"}),
                      testo("Non la trovo."), parole=P_PATELLO,
                      chi=ChiParla(name=None, level="ospite", how=None))
    r = reg[0] if reg else {}
    verifica("ospite: nessun suggerimento, nel registro né valore né nome noto",
             "nome_incerto" not in json.dumps(ultimo_risultato(b4)) and r
             and "valore" not in r and "noto" not in r and r.get("esito") == "vuoto"
             and r.get("p_min") == 0.22, str(r))
    _, reg, _ = parla(b4, "Calliope, prova con Patello Giugnasco",
                      chiama("est_meteo_citta", {"citta": "Patello Giugnasco"}),
                      testo("Non la trovo."), parole=P_PATELLO,
                      chi=ChiParla(how="conversazione"))
    r = reg[0] if reg else {}
    verifica("zona grigia: nessun suggerimento, solo numeri",
             "nome_incerto" not in json.dumps(ultimo_risultato(b4)) and "valore" not in r
             and "somiglianza" in r, str(r))
    verifica("ospite: il vocabolario non impara dai suoi valori",
             ai.VOCABOLARIO.riusciti("luogo") == ["Pradello Dugnasco"])

    # La casa (nomi_vicini già suoi), una frase pronta, un tool riservato, rete spenta
    b5, _ = prepara_brain()
    _, reg, _ = parla(b5, "Calliope, com'è la lampara del sottalco?",
                      chiama("casa_stato", {"cosa": "lampara del sottalco"}),
                      testo("Non la trovo."), parole=[("lampara", 0.84), ("del", 0.99),
                                                      ("sottalco", 0.97)],
                      chi=ChiParla(name="Dario", level="amministra"))
    verifica("casa: misura sì (esito vuoto), suggerimento no (ha i suoi nomi vicini)",
             reg and reg[0].get("esito") == "vuoto" and reg[0].get("tipo") == "casa"
             and "nome_incerto" not in json.dumps(ultimo_risultato(b5)), str(reg))
    ai.VOCABOLARIO.ricorda("luogo", "Pradello Dugnasco")
    parla(b5, "Calliope, prova con Patello Giugnasco",
          chiama("est_pronta", {"citta": "Patello Giugnasco"}), parole=P_PATELLO)
    verifica("frase pronta (risposta_finale): nessun suggerimento",
             "argomento_forse" not in b5.rules_fired())
    _, reg, _ = parla(b5, "Calliope, cerca Rossi", chiama("est_riservata", {"testo": "Rossi"}),
                      testo("Niente."), parole=[("cerca", 0.9), ("Rossi", 0.9)])
    verifica("tool riservato: nel registro mai il valore",
             reg and "valore" not in reg[0] and "noto" not in reg[0], str(reg))
    b5.cfg.llm_reti_spente = ["argomento_forse"]
    parla(b5, "Calliope, prova con Patello Giugnasco",
          chiama("est_meteo_citta", {"citta": "Patello Giugnasco"}), testo("Non la trovo."),
          parole=P_PATELLO)
    verifica("rete argomento_forse spenta: nessun suggerimento, la misura resta",
             "argomento_forse" not in b5.rules_fired() and b5.last_argomenti)
    b5.cfg.llm_reti_spente = []
    b5.cfg.stt_argomenti_misura = False
    _, reg, _ = parla(b5, "Calliope, prova con Patello Giugnasco",
                      chiama("est_meteo_citta", {"citta": "Patello Giugnasco"}),
                      testo("Non la trovo."), parole=P_PATELLO)
    verifica("misura spenta: niente nel registro, niente suggerimento",
             reg == [] and "argomento_forse" not in b5.rules_fired())
    b5.cfg.stt_argomenti_misura = True

    # Un'altra domanda già fatta in questa risposta (un tool con la sua proposta): niente
    b6, _ = prepara_brain()
    ai.VOCABOLARIO.ricorda("luogo", "Pradello Dugnasco")
    b6.backend.risposte = []
    parla(b6, "Calliope, cerca il file chiavi e prova con Patello Giugnasco",
          [("calls", [{"id": "c0", "name": "pc_cerca_file", "arguments": {"testo": "chiavi"}},
                      {"id": "c1", "name": "est_meteo_citta",
                       "arguments": {"citta": "Patello Giugnasco"}}])],
          testo("Ho trovato x. Lo apro?"), parole=P_PATELLO,
          chi=ChiParla(name="Dario", level="amministra"))
    verifica("F1, contrario: con un'altra domanda nella stessa risposta, niente «forse»",
             "argomento_forse" not in b6.rules_fired(), str(b6.rules_fired()))

    # «La gente» in senso vero: nessun argomento marcato, nessuna regola, frase com'è
    b7, _ = prepara_brain()
    _, reg, _ = parla(b7, "Calliope, cosa dice la gente del meteo di oggi?",
                      testo("Non lo so, ma posso guardare il meteo."),
                      parole=[("la", 0.99), ("gente", 0.98)])
    verifica("«la gente» in senso vero: niente misura, nessuna regola, la frase non cambia",
             reg == [] and not any("argoment" in r for r in b7.rules_fired())
             and b7.history[-2]["content"].endswith("cosa dice la gente del meteo di oggi?"),
             str(b7.history[-2:]))

    # Whisper lento: il registro aspetta al più un secondo e poi lo dice
    b8, _ = prepara_brain()
    asc = ai.Ascolto(np.ones(1600, dtype=np.float32), STTFinto(P_PATELLO, 1.5))
    b8.backend.risposte = [chiama("est_meteo_citta", {"citta": "Pradello Dugnasco"}),
                           testo("17 gradi.")]
    "".join(b8.stream_reply("prova con Pradello Dugnasco", "familiare", ascolto=asc))
    t0 = time.perf_counter()
    reg = b8.argomenti_per_registro(0.2)
    verifica("Whisper lento: il registro non aspetta oltre il tempo dato, «p_tardi»",
             time.perf_counter() - t0 < 0.5 and reg and reg[0].get("p_tardi"), str(reg))


def prova_ciclo():
    """Il ciclo passa l'ascolto solo per una frase detta, con la misura accesa."""
    from types import SimpleNamespace
    from calliope.ciclo import Ciclo
    from calliope.config import Config
    cfg = Config()
    finto = SimpleNamespace(s=SimpleNamespace(cfg=cfg, stt=STTFinto([])))
    t = SimpleNamespace(scritto=None, audio=np.ones(10, dtype=np.float32), conf_stt=None)
    a = Ciclo._ascolto_turno(finto, t)
    verifica("ciclo: frase detta → ascolto con l'audio e il nome che sveglia",
             a is not None and a.possibile and cfg.name in a.nomi_sveglia)
    t.scritto = {"testo": "ciao"}
    verifica("ciclo: frase scritta → nessun ascolto", Ciclo._ascolto_turno(finto, t) is None)
    t.scritto = None
    cfg.stt_argomenti_misura = False
    verifica("ciclo: misura spenta → nessun ascolto", Ciclo._ascolto_turno(finto, t) is None)
    src = (Path(__file__).resolve().parent.parent / "calliope" / "ciclo.py").read_text("utf-8")
    verifica("ciclo: stt_argomento nel registro dei turni, oscurato se scritto",
             'rec["stt_argomento"] = oscura_tutto(misure) if t.scritto' in src)


# ─────────────────────────── 4. il riassunto ───────────────────────────
def prova_riassunto():
    turni = [
        {"stt_argomento": [{"tool": "est_meteo", "esito": "vuoto", "p_min": 0.22,
                            "somiglianza": 0.8, "forse": "forse"}]},
        {"stt_argomento": [{"tool": "est_meteo", "esito": "pieno", "p_min": 0.9,
                            "somiglianza": 1.0, "e_noto": True, "da_suggerimento": True,
                            "correzione": {"turni": 1, "esito_prima": "vuoto"}}]},
        {"stt_argomento": [{"tool": "casa_stato", "esito": "vuoto", "p_min": 0.45,
                            "somiglianza": 0.5}]},
        {"stt_argomento": [{"tool": "sviluppo_collauda", "esito": "pieno",
                            "allineato": False, "somiglianza": 0.3}]},
        {"testo": "che ore sono"},
    ]
    r = ai.riassunto(turni)
    verifica("riassunto: chiamate, esiti, soglie, nomi vicini, correzioni, suggerimenti",
             r["chiamate"] == 4 and r["esiti"] == {"vuoto": 2, "pieno": 2}
             and r["sotto"]["0.5"] == 2 and r["sotto_vuoti"]["0.3"] == 1
             and r["noto_vicino"] == 1 and r["noto_vicino_vuoti"] == 1 and r["noto_uguale"] == 1
             and r["correzioni"] == 1 and r["correzioni_riuscite"] == 1
             and r["forse"] == {"forse": 1} and r["da_suggerimento"] == 1
             and r["non_allineati"] == 1, json.dumps(r))
    t = ai.testo(r)
    verifica("riassunto: il testo per il terminale", "4 chiamate" in t and "vuoto 2" in t
             and "correzioni spontanee 1" in t, t)
    verifica("riassunto: registro vuoto", "nessuna" in ai.testo(ai.riassunto([])))
    src = (Path(__file__).resolve().parent.parent / "calliope" / "stato.py").read_text("utf-8")
    verifica("calliope stato --turni stampa il riassunto",
             "argomenti_incerti.riassunto(turni)" in src)


if __name__ == "__main__":
    prova_pezzi()
    prova_trascrittori()
    prova_brain()
    prova_ciclo()
    prova_riassunto()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    sys.exit(1 if errori else 0)
