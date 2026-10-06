import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della correzione delle frasi incerte (05/10, calliope/stt_correzione.py):
parole e confidenza da verbose_json di whisper-server, soglia, controllo della correzione con i
casi contrari, correttore con un server finto (Ollama e OpenAI, tempo scaduto, JSON rotto),
ServerTranscriber con verbose_json solo se acceso, vocabolario della casa, privacy nel
registro dei turni; parole incerte al modello della voce (variante B, 07/10) e frase capita
trattenuta (B2). Niente rete né modello."""

import json
import time
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from calliope import stt_correzione as sc

ERRORI = []


def check(cond, msg):
    print(("OK  " if cond else "NO  ") + msg)
    if not cond:
        ERRORI.append(msg)


# Risposta vera di whisper-server (05/10, «Oggi è proprio una bella giornata.»), ridotta
VERBOSE = {"text": " Oggi è proprio una bella giornata.\n", "segments": [{
    "text": " Oggi è proprio una bella giornata.", "avg_logprob": -0.016, "no_speech_prob": 8e-11,
    "words": [{"word": " O", "probability": 0.98}, {"word": "ggi", "probability": 0.99},
              {"word": " è", "probability": 0.97}, {"word": " proprio", "probability": 0.94},
              {"word": " una", "probability": 0.99}, {"word": " be", "probability": 0.99},
              {"word": "lla", "probability": 0.31}, {"word": " giorn", "probability": 0.99},
              {"word": "ata", "probability": 0.99}, {"word": ".", "probability": 0.05}]}]}


def prova_confidenza():
    parole = sc.parole_whisper(VERBOSE)
    check([w for w, _ in parole] == ["Oggi", "è", "proprio", "una", "bella", "giornata"],
          f"token uniti in parole, punteggiatura esclusa: {parole}")
    check(dict(parole)["bella"] == 0.31, "la parola vale il suo token più debole")
    c = sc.confidenza(VERBOSE)
    check(c.min_parola == 0.31 and c.incerte == ["bella"], f"confidenza: {c}")
    check(sc.incerta(c, SimpleNamespace(stt_correzione_soglia=0.5)), "0,31 < 0,5: incerta")
    check(not sc.incerta(c, SimpleNamespace(stt_correzione_soglia=0.3)), "0,31 ≥ 0,3: sicura")
    check(not sc.incerta(None, SimpleNamespace(stt_correzione_soglia=0.9)),
          "senza confidenza (faster-whisper, CPU) non si corregge mai")
    check(sc.confidenza({"text": "x"}).min_parola == 1.0, "verbose senza segmenti: sicura")
    check(c.deboli == [("bella", 0.31)], f"parole deboli con la probabilità: {c.deboli}")
    # Il nome non conta (05/10 sera): «Calliope» dopo una pausa è spesso incerto e giusto
    cfg = SimpleNamespace(stt_correzione_soglia=0.4, wake_names=["Calliope"])
    solo_nome = sc.Confidenza(0.11, incerte=["Calliope"], deboli=[("Calliope", 0.11)])
    check(not sc.incerta(solo_nome, cfg) and sc.min_utile(solo_nome, cfg) == 0.5,
          "solo il nome incerto: la frase non va al secondo passaggio")
    nome_e_altro = sc.Confidenza(0.09, incerte=["Calliope", "eshi"],
                                 deboli=[("Calliope,", 0.09), ("eshi", 0.33)])
    check(sc.incerta(nome_e_altro, cfg) and sc.min_utile(nome_e_altro, cfg) == 0.33,
          "il nome e un'altra parola debole: vale l'altra (0,33 < 0,4)")
    check(sc.incerta(sc.Confidenza(0.2, incerte=["Calliope"], deboli=[("Calliope", 0.2)]),
                     SimpleNamespace(stt_correzione_soglia=0.4, wake_names=["Computer"])),
          "contrario: con un'altra parola che sveglia, «Calliope» conta come le altre")
    check(not sc.incerta(sc.Confidenza(0.45, incerte=["Quanto"], deboli=[("Quanto", 0.45)]),
                         cfg), "0,45 ≥ 0,4 (predefinito di adesso): sicura")
    check(sc.incerta(sc.Confidenza(0.3, incerte=["x"]), cfg),
          "dati senza le parole deboli: vale min_parola come prima")
    # A capo di whisper-server a metà parola (05/10 sera, taglio dei segmenti a 60 caratteri)
    from calliope.stt import unisci_righe
    for prima, dopo in (("di fis\nica, astrofisica", "di fisica, astrofisica"),
                        ("di un\n software chiamato", "di un software chiamato"),
                        ("Gra\nzie.", "Grazie."), ("dall'ind\neterminazione", "dall'indeterminazione"),
                        ("Ciao.\nCome stai?", "Ciao. Come stai?"), ("senza a capo", "senza a capo")):
        check(unisci_righe(prima) == dopo, f"a capo tolto: {prima!r} → {unisci_righe(prima)!r}")


# (prima, dopo, accettata): i casi veri del 05/10 e delle misure, con i contrari
CASI = [
    ("Mi riferivo allo schermo del mio seppellito.", "Mi riferivo allo schermo del mio satellite.", True),
    ("Calliope di Michisono.", "Calliope dimmi chi sono.", True),
    ("Di mikro sonu.", "Dimmi chi sono.", True),
    ("Calliope e Milostrato delle Luci", "Calliope dimmi lo stato delle luci", True),
    ("Calliope spegni la luce in tabella.", "Calliope spegni la luce in taverna.", True),
    ("Calliope eshi.", "Calliope esci.", True),
    ("Annulla il pro memoria.", "Annulla il promemoria.", True),
    ("Dammi una citazione da Vici Quote.", "Dammi una citazione da Wikiquote.", True),
    # contrari: senso cambiato, suono diverso, negazioni, numeri, aggiunte
    ("Mi riferivo allo schermo del mio satellite.", "Mi riferivo allo schermo del mio studio.", False),
    ("Mi riferivo allo schermo del mio seppellito.", "Mi riferivo allo schermo del mio telefono.", False),
    ("Calliope. Chiori sono.", "Calliope. Chi sono.", False),
    ("Appuino sul potatilo.", "Appuntamento sul portatile.", False),
    ("Calliope è così.", "Calliope, chiama Dario.", False),
    ("C'è un dio pesci.", "C'è un timer pesci.", False),
    ("Accendi la luce in taverna.", "Non accendi la luce in taverna.", False),
    ("Sì, procedi pure.", "No, procedi pure.", False),
    ("Metti un timer di 10 minuti.", "Metti un timer di 20 minuti.", False),
    ("Spegni la luce.", "Spegni la luce e la caldaia.", False),
    ("Cerca su internet il meteo di domani avanzate.", "Cerca su internet il meteo di domani", False),
    ("Che ore sono?", "Che ore sono?", False),
    ("Che ore sono?", "", False),
    ("Accendi la luce del bagno taverna.", "Accendi la luce del Bagno Taverna.", False),
]


def prova_accettabile():
    for prima, dopo, atteso in CASI:
        ok, perche = sc.accettabile(prima, dopo)
        check(ok == atteso, f"{'accetta' if atteso else 'rifiuta'} «{prima}» → «{dopo}»"
              + (f" ({perche})" if perche else ""))


class Risposta:
    def __init__(self, dati, status=200):
        self._d, self.status_code = dati, status

    def json(self):
        if isinstance(self._d, Exception):
            raise self._d
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    @property
    def text(self):
        return str(self._d)


class HttpFinto:
    def __init__(self, risposta=None, errore=None):
        self.risposta, self.errore, self.chiamate = risposta, errore, []

    def post(self, url, json=None, files=None, data=None, timeout=None):
        self.chiamate.append(dict(url=url, json=json, data=data, timeout=timeout))
        if self.errore:
            raise self.errore
        return self.risposta(json, data) if callable(self.risposta) else self.risposta


def cfg_voce(**kw):
    base = dict(name="Calliope", llm_backend="ollama", llm_native_url="http://127.0.0.1:11434",
                llm_base_url="http://127.0.0.1:8000/v1", llm_model="gemma4:26b-a4b-it-qat",
                llm_num_ctx=28672, llm_keep_alive=-1, stt_correzione_soglia=0.5,
                stt_correzione_timeout_s=1.5)
    base.update(kw)
    return SimpleNamespace(**base)


def prova_correttore():
    voc = sc.vocabolario_casa(None, ["studio"], ["studio di Dario"], ["Dario"], ["Taverna"])
    check(voc[:5] == ["Calliope", "Dario", "studio", "studio di Dario", "Taverna"]
          and "satellite" in voc and len(voc) == len({v.lower() for v in voc}),
          f"vocabolario: nome, persone, satelliti, schermi, casa, tool, senza doppioni ({voc[:6]})")
    conf = sc.Confidenza(0.1, -1.0, 0.0, ["seppellito"])
    # Ollama, modello della voce: num_ctx e keep_alive della voce (niente ricarica)
    http = HttpFinto(Risposta({"message": {"content": json.dumps(
        {"giusta": False, "testo": "Mi riferivo allo schermo del mio satellite."})}}))
    c = sc.Correttore(cfg_voce(), http=http)
    es = c.correggi("Mi riferivo allo schermo del mio seppellito.", conf, voc,
                    ["Non vedevo più le mie schede.", "Calliope: Mi dispiace."])
    body = http.chiamate[0]["json"]
    check(es.cambiata and es.testo.endswith("satellite."), f"correzione accettata: {es}")
    check(http.chiamate[0]["url"] == "http://127.0.0.1:11434/api/chat", "Ollama: /api/chat")
    check(body["options"]["num_ctx"] == 28672 and body["keep_alive"] == -1
          and body["think"] is False and body["format"] == sc.SCHEMA,
          f"stesso num_ctx e keep_alive della voce, thinking spento, schema: {body['options']}")
    p = body["messages"][0]["content"]
    check("satellite" in p and "seppellito" in p and "Non vedevo più" in p and "Dario" in p,
          "il prompt ha vocabolario, parole incerte, frasi precedenti e trascrizione")
    check(sc.SCHEMA["required"] == ["giusta"] and "giusta" in p,
          "si chiede «giusta» prima e il testo solo se va corretto (05/10 sera)")
    # «giusta: true»: nessuna correzione, e il modello non ha ricopiato la frase
    for risposta in ('{"giusta": true}', '{"giusta": true, "testo": "Calliope, chiama Dario."}',
                     '{"giusta": false, "testo": ""}', '{"giusta": false}'):
        es = sc.Correttore(cfg_voce(), http=HttpFinto(Risposta(
            {"message": {"content": risposta}}))).correggi("Calliope è così.", conf, voc)
        check(not es.cambiata and es.testo == "Calliope è così." and es.motivo == "identica",
              f"{risposta}: resta Whisper ({es.motivo})")
    # Un modello diverso: la sua finestra, non quella della voce
    http = HttpFinto(Risposta({"message": {"content": '{"testo": "Calliope esci."}'}}))
    c = sc.Correttore(cfg_voce(stt_correzione_modello="gemma4:e4b-it-qat"), http=http)
    es = c.correggi("Calliope eshi.", conf, voc)
    check(es.cambiata and http.chiamate[0]["json"]["options"]["num_ctx"] == 4096,
          "un altro modello su Ollama: finestra sua (4096)")
    # OpenAI (vLLM): response_format json_schema, thinking spento
    http = HttpFinto(Risposta({"choices": [{"message": {"content": '{"testo": "Calliope esci."}'}}]}))
    c = sc.Correttore(cfg_voce(stt_correzione_motore="openai", stt_correzione_modello="qwen3.6-35b"),
                      http=http)
    es = c.correggi("Calliope eshi.", conf, voc)
    b = http.chiamate[0]["json"]
    check(es.cambiata and http.chiamate[0]["url"] == "http://127.0.0.1:8000/v1/chat/completions"
          and b["response_format"]["type"] == "json_schema"
          and b["chat_template_kwargs"] == {"enable_thinking": False},
          "OpenAI: /chat/completions con json_schema e thinking spento")
    # Proposta che cambia il senso: rifiutata, resta Whisper
    http = HttpFinto(Risposta({"message": {"content": '{"testo": "Calliope, chiama Dario."}'}}))
    es = sc.Correttore(cfg_voce(), http=http).correggi("Calliope è così.", conf, voc)
    check(not es.cambiata and es.testo == "Calliope è così." and es.proposta,
          f"proposta rifiutata dal controllo: resta Whisper ({es.motivo})")
    # Tempo scaduto, JSON rotto, frase vuota: resta Whisper, mai un'eccezione
    es = sc.Correttore(cfg_voce(), http=HttpFinto(errore=TimeoutError())).correggi(
        "Calliope eshi.", conf, voc)
    check(not es.cambiata and es.testo == "Calliope eshi." and es.motivo == "tempo",
          f"tempo scaduto: resta Whisper ({es.motivo})")
    # Tempo massimo vero (P1, 06/10): 0,4 s di predefinito, passato a httpx come tempo di
    # ogni fase (connessione al più 0,2 s); una risposta arrivata oltre vale Whisper lo stesso
    from calliope.config import Config
    check(Config().stt_correzione_timeout_s == 0.4,
          f"tempo massimo predefinito 0,4 s ({Config().stt_correzione_timeout_s})")
    http = HttpFinto(Risposta({"message": {"content": '{"testo": "Calliope esci."}'}}))
    es = sc.Correttore(cfg_voce(stt_correzione_timeout_s=0.4), http=http).correggi(
        "Calliope eshi.", conf, voc)
    t = http.chiamate[0]["timeout"]
    check(es.cambiata and getattr(t, "read", None) == 0.4 and getattr(t, "connect", None) == 0.2,
          f"a tempo: corretta; tempo a httpx lettura 0,4 e connessione 0,2 ({t})")

    class Lento(HttpFinto):
        def post(self, *a, **kw):
            time.sleep(0.35)
            return super().post(*a, **kw)
    es = sc.Correttore(cfg_voce(stt_correzione_timeout_s=0.2), http=Lento(Risposta(
        {"message": {"content": '{"testo": "Calliope esci."}'}}))).correggi(
        "Calliope eshi.", conf, voc)
    check(not es.cambiata and es.testo == "Calliope eshi." and es.motivo == "tempo"
          and es.ms >= 300, f"risposta arrivata oltre il tempo massimo: vale Whisper ({es})")
    es = sc.Correttore(cfg_voce(), http=HttpFinto(Risposta({"message": {"content": "boh"}}))
                       ).correggi("Calliope eshi.", conf, voc)
    check(not es.cambiata and es.testo == "Calliope eshi.", "JSON rotto: resta Whisper")
    http = HttpFinto(errore=AssertionError("non doveva chiamare"))
    es = sc.Correttore(cfg_voce(), http=http).correggi("", conf, voc)
    check(not es.cambiata and not http.chiamate, "frase vuota: nessuna richiesta")


def prova_server_transcriber():
    from calliope.config import Config
    from calliope.stt import ServerTranscriber
    for acceso in (False, True):
        cfg = Config()
        cfg.stt_url, cfg.stt_correzione = "http://127.0.0.1:9/v1", acceso
        http = HttpFinto(lambda j, d: Risposta(VERBOSE if d["response_format"] == "verbose_json"
                                               else {"text": VERBOSE["text"]}))
        st = ServerTranscriber(cfg, http=http)
        testo = st.transcribe(np.zeros(16000, np.float32))
        fmt = http.chiamate[-1]["data"]["response_format"]
        if acceso:
            check(fmt == "verbose_json" and st.ultima_confidenza is not None
                  and st.ultima_confidenza.min_parola == 0.31 and testo.startswith("Oggi"),
                  "correzione accesa: verbose_json e confidenza dell'ultima frase")
        else:
            check(fmt == "json" and st.ultima_confidenza is None,
                  "correzione spenta (predefinito): json come sempre, nessuna confidenza")
    check(Config().stt_correzione is False, "stt_correzione spenta di predefinito")
    cfg = Config()
    cfg.stt_url, cfg.stt_correzione = "http://127.0.0.1:9/v1", True
    v = dict(VERBOSE, text=" Io sono appassionato di fis\nica, astrofisica più che fisica.\n")
    st = ServerTranscriber(cfg, http=HttpFinto(lambda j, d: Risposta(v)))
    testo = st.transcribe(np.zeros(16000, np.float32))
    check(testo == "Io sono appassionato di fisica, astrofisica più che fisica.",
          f"testo del server senza gli a capo a metà parola: {testo!r}")


def prova_vocabolario_e_registro():
    class Arch:
        def __init__(self, righe):
            self.righe = righe

        def elenco(self):
            return self.righe

    class Casa:
        def entita(self):
            return [SimpleNamespace(nome="Luce taverna", area="Taverna", alias=["Tave"])]

        def aree(self):
            return {"Cucina": [], "Taverna": []}

    class Rotto:
        def elenco(self):
            raise RuntimeError("database chiuso")

    voc = sc.vocabolario_calliope(SimpleNamespace(name="Calliope"),
                                  SimpleNamespace(users={"Dario": 1, "Bianca": 2}),
                                  SimpleNamespace(archivio=Arch([{"nome": "studio", "stanza": "studio"}])),
                                  SimpleNamespace(archivio=Rotto()), Casa())
    check(all(w in voc for w in ("Dario", "Bianca", "studio", "Luce taverna", "Tave", "Cucina")),
          f"vocabolario dalle fonti di Calliope, una rotta saltata: {voc[:9]}")
    brain = SimpleNamespace(history=[{"role": "user", "content": "Che ore sono?"},
                                     {"role": "assistant", "content": "Sono le 12."},
                                     {"role": "tool", "content": "{}"}])
    check(sc.storia_recente(brain) == ["Che ore sono?", "Calliope: Sono le 12."],
          "storia recente: persona e Calliope, niente tool")
    lunga = SimpleNamespace(history=[{"role": "user", "content": "x" * 300},
                                     {"role": "assistant", "content": "y" * 300}])
    st = sc.storia_recente(lunga)
    check(len(st[0]) == 200 and st[1] == "Calliope: " + "y" * 120,
          "risposte di Calliope corte nel prompt della correzione (120 caratteri)")
    from calliope.turnlog import TurnLog
    with tempfile.TemporaryDirectory() as d:
        log = TurnLog(d)
        for livello in ("ospite", "familiare"):
            log._write({"inizio": "2026-10-05T10:00:00", "livello": livello, "testo": "x",
                        "regole": ["stt_corretta"],
                        "stt_corretta": {"prima": "seppellito", "dopo": "satellite"}})
        righe = [json.loads(x) for f in Path(d).glob("*.jsonl") for x in open(f, encoding="utf-8")]
        osp = [r for r in righe if r["livello"] == "ospite"][0]
        fam = [r for r in righe if r["livello"] == "familiare"][0]
        check(osp["stt_corretta"] == {} and osp["regole"] == ["stt_corretta"],
              "ospite: la regola resta, prima e dopo no")
        check(fam["stt_corretta"]["dopo"] == "satellite", "familiare: prima e dopo nel registro")


def prova_incerte_al_modello():
    """Variante B (07/10, stt_incerte_al_modello): le parole incerte nei dati del turno, mai
    nel prompt di sistema; verbose_json anche senza la correzione; nessuna parola cambiata."""
    from calliope.config import Config
    from calliope.stt import ServerTranscriber
    cfg = SimpleNamespace(stt_correzione_soglia=0.4, wake_names=["Calliope"])
    conf = sc.Confidenza(0.1, deboli=[("Calliope,", 0.12), ("Dimitra", 0.1), ("città", 0.45),
                                      ("Isenbelb.", 0.3), ("Dimitra", 0.2)])
    testo = "Dimitra tre città della Toscana, Isenbelb."
    check(sc.parole_incerte(conf, cfg, testo) == ["Dimitra", "Isenbelb"],
          "parole sotto la soglia, nome escluso, senza punteggiatura né doppioni, più deboli prima")
    check(sc.parole_incerte(conf, cfg, "tre città della Toscana") == [],
          "contrario: parole non rimaste nella frase (nome tolto, correzione) non si dicono")
    check(sc.parole_incerte(None, cfg, testo) == [],
          "contrario: senza confidenza (faster-whisper, scritto) nessuna parola")
    check(sc.parole_incerte(sc.Confidenza(0.12, deboli=[("Calliope", 0.12)]), cfg,
                            "Calliope che ore sono") == [], "contrario: solo il nome incerto")
    molte = sc.Confidenza(0.1, deboli=[(f"p{i}", 0.1 + i / 100) for i in range(8)])
    check(sc.parole_incerte(molte, cfg, " ".join(f"p{i}" for i in range(8))) ==
          ["p0", "p1", "p2", "p3"], "al più 4 parole, le più deboli")
    # Il trascrittore chiede verbose_json anche con la sola variante B
    c = Config()
    c.stt_url, c.stt_incerte_al_modello = "http://127.0.0.1:9/v1", True
    http = HttpFinto(lambda j, d: Risposta(VERBOSE if d["response_format"] == "verbose_json"
                                           else {"text": VERBOSE["text"]}))
    st = ServerTranscriber(c, http=http)
    st.transcribe(np.zeros(16000, np.float32))
    check(http.chiamate[-1]["data"]["response_format"] == "verbose_json"
          and st.ultima_confidenza is not None, "variante B: verbose_json e confidenza")
    check(Config().stt_incerte_al_modello is False, "stt_incerte_al_modello spenta di predefinito")
    # Brain: la riga nei dati del turno, nessuna senza parole, mai nel prompt di sistema
    from calliope import brain as B
    from calliope.tools.registry import ToolRegistry
    br = B.Brain(Config(), ToolRegistry(), SimpleNamespace(speaker_ctx=SimpleNamespace(
        current_speaker=None, identified_by=None)))
    br.last_rules = []
    br._incerte_turno = ["Dimitra", "Isenbelb"]
    msg = br._turn_context()[0]["content"]
    check(msg.startswith("Dati del turno") and "«Dimitra», «Isenbelb»" in msg
          and msg.endswith("Per tutto il resto chiama i tool come sempre."),
          f"riga delle parole incerte nei dati del turno, «chiama i tool» in fondo: {msg!r}")
    check(br.last_rules == ["stt_incerte"], f"nome nel registro, mai le parole: {br.last_rules}")
    br._turn_context()
    check(br.last_rules == ["stt_incerte"], "una volta sola anche con più passate")
    sistema = json.dumps(br._system_messages(), ensure_ascii=False)
    check("Dimitra" not in sistema and "parole incerte" not in sistema,
          "il prompt di sistema non cambia (prefisso in cache)")
    br.last_rules, br._incerte_turno = [], []
    msg = br._turn_context()[0]["content"]
    check("incerte" not in msg and br.last_rules == [],
          "contrario: senza parole incerte nessuna riga e nessuna regola")
    check(B.nota_incerte([]) == "" and B.nota_incerte([" "]) == "", "nota vuota senza parole")


def prova_capito():
    """Variante B2 (07/10, stt_incerte_riscrivi): la riga «⟦capito: …⟧» in testa alla
    risposta si trattiene (anche spezzata), vale per la politica e la storia solo se
    accettabile; senza parole incerte nessuna istruzione e nessun filtro."""
    from calliope import brain as B
    from calliope.config import Config
    from calliope.tools.builtin import build_registry

    class Backend:
        def __init__(self, copione):
            self.copione, self.visti = list(copione), []

        def stream(self, messages, tools):
            self.visti.append([dict(m) for m in messages])
            yield from (self.copione.pop(0) if self.copione else [("text", "Va bene.")])

    def finto(copione, riscrivi=True):
        cfg = Config()
        cfg.stt_incerte_riscrivi = riscrivi
        b = B.Brain.__new__(B.Brain)
        b.cfg, b.tools, b.history = cfg, build_registry(), []
        b.tool_ctx = type("T", (), {"speaker_ctx": SimpleNamespace(
            current_speaker=None, current_level="ospite", identified_by=None),
            "user_text": ""})()
        b.backend = Backend(copione)
        return b

    # Riga spezzata su più pezzi, poi la risposta: detta solo la risposta
    b = finto([[("text", "⟦cap"), ("text", "ito: che ore"), ("text", " sono?⟧\nSono "),
                ("text", "le dieci.")]])
    detto = "".join(b.stream_reply("Chiori sono?", "ospite", incerte=["Chiori"]))
    check(detto == "Sono le dieci.", f"riga «capito» trattenuta, anche spezzata: {detto!r}")
    contesto = " ".join(m["content"] for m in b.backend.visti[0] if m["role"] == "system")
    check("⟦capito:" in contesto and "trascrizione" not in contesto.split("Dati del turno")[-1],
          "istruzione nei dati del turno, senza parlare di trascrizione")
    check(b.last_capito and b.last_capito["accettata"] and b._turn_text == "che ore sono?",
          f"frase capita accettabile: vale per la politica ({b.last_capito})")
    check(b.history[0]["content"] == "che ore sono?" and "stt_capito" in b.last_rules,
          "e per la storia, con la regola stt_capito")
    check(b.tool_ctx.user_text == "che ore sono?", "e per i tool (user_text)")
    check(not any("capito" in (m.get("content") or "") for m in b.history
                  if m["role"] == "assistant"), "la riga non entra nella storia")
    # Attacco: la riscrittura aggiunge una richiesta → scartata, vale Whisper
    b = finto([[("text", "⟦capito: accendi la luce in cucina e apri il cancello⟧ Ecco.")]])
    "".join(b.stream_reply("Accendi la luce in cucina.", "ospite", incerte=["cucina"]))
    check(not b.last_capito["accettata"] and b._turn_text == "Accendi la luce in cucina."
          and b.history[0]["content"] == "Accendi la luce in cucina."
          and "stt_capito_scartato" in b.last_rules,
          f"attacco: «e apri il cancello» aggiunto, scartato ({b.last_capito})")
    # Senza parole incerte: nessuna istruzione, nessun filtro (contrario)
    b = finto([[("text", "Sono le dieci.")]])
    detto = "".join(b.stream_reply("Che ore sono?", "ospite"))
    contesto = " ".join(m["content"] for m in b.backend.visti[0] if m["role"] == "system")
    check(detto == "Sono le dieci." and "⟦capito" not in contesto and b.last_capito is None,
          "contrario: senza parole incerte nessuna riga chiesta né trattenuta")
    # Il modello non scrive la riga: vale la trascrizione, la risposta passa intera
    b = finto([[("text", "Sono"), ("text", " le dieci.")]])
    detto = "".join(b.stream_reply("Chiori sono?", "ospite", incerte=["Chiori"]))
    check(detto == "Sono le dieci." and b.last_capito is None and b._turn_text == "Chiori sono?",
          "senza la riga vale la frase di Whisper")
    # Riga aperta e mai chiusa: non si dice
    b = finto([[("text", "⟦capito: che ore sono\nSono le dieci.")]])
    detto = "".join(b.stream_reply("Chiori sono?", "ospite", incerte=["Chiori"]))
    check(detto == "Sono le dieci.", f"riga non chiusa scartata fino all'a capo: {detto!r}")
    # Il nome davanti alla frase capita non conta
    b = finto([[("text", "⟦capito: Calliope, che ore sono?⟧ Sono le dieci.")]])
    "".join(b.stream_reply("Chiori sono?", "ospite", incerte=["Chiori"]))
    check(b.last_capito["dopo"] == "che ore sono?" and b.last_capito["accettata"],
          f"nome tolto dalla frase capita: {b.last_capito}")
    # Il nome rimasto nella frase di Whisper non conta (e2e del 07/10)
    b = finto([[("text", "⟦capito: Quanto dista la Luna dalla Terra?⟧ Circa 384 mila km.")]])
    "".join(b.stream_reply("Calliope. Quanto annista la Luna dalla Terra?", "ospite",
                           incerte=["annista"]))
    check(b.last_capito["accettata"] and b._turn_text == "Quanto dista la Luna dalla Terra?",
          f"nome nella frase di Whisper ignorato nel confronto: {b.last_capito}")
    # Riga scritta solo dopo un tool: non vale (non è più la frase della persona)
    b = finto([[("calls", [{"id": "c0", "name": "ora_attuale", "arguments": {}}])],
               [("text", "⟦capito: Sono le dieci?⟧ Sono le dieci.")]])
    detto = "".join(b.stream_reply("Chiori sono?", "ospite", incerte=["Chiori"]))
    check(detto == "Sono le dieci." and not b.last_capito["accettata"]
          and b._turn_text == "Chiori sono?", f"riga dopo un tool trattenuta e scartata: {b.last_capito}")
    # Con B2 spenta la riga non si trattiene (e non si chiede)
    b = finto([[("text", "Sono le dieci.")]], riscrivi=False)
    "".join(b.stream_reply("Chiori sono?", "ospite", incerte=["Chiori"]))
    contesto = " ".join(m["content"] for m in b.backend.visti[0] if m["role"] == "system")
    check("⟦capito" not in contesto and "parole incerte" in contesto,
          "B2 spenta: la riga di B, nessuna richiesta della riga")
    check(Config().stt_incerte_riscrivi is False, "stt_incerte_riscrivi spenta di predefinito")


if __name__ == "__main__":
    prova_capito()
    prova_incerte_al_modello()
    prova_confidenza()
    prova_accettabile()
    prova_correttore()
    prova_server_transcriber()
    prova_vocabolario_e_registro()
    print(f"\n{'TUTTO OK' if not ERRORI else f'{len(ERRORI)} ERRORI'}")
    sys.exit(1 if ERRORI else 0)
